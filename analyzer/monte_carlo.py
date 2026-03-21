"""몬테카를로 파라미터 최적화 엔진.

부트스트랩 또는 GBM 방식으로 미래 가격 경로를 시뮬레이션하고,
RSI·거래량 조건부 부트스트랩으로 실제 진입 조건을 반영한
손절/익절/기간만료 전략의 최적 파라미터를 탐색한다.
"""
from __future__ import annotations

import datetime
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from loguru import logger


@dataclass
class SimulationConfig:
    """몬테카를로 시뮬레이션 설정"""
    n_simulations: int = 5000
    lookback_days: int = 252
    validation_days: int = 63
    simulation_days: int = 20
    method: str = "bootstrap"   # "bootstrap" | "gbm"
    random_seed: int = 42


@dataclass
class ParamGrid:
    """최적화할 파라미터 탐색 범위"""
    stop_loss_pct: list[float] = field(default_factory=lambda: [3.0, 5.0, 7.0, 10.0, 13.0])
    take_profit_pct: list[float] = field(default_factory=lambda: [6.0, 10.0, 15.0, 20.0, 25.0])
    max_holding_days: list[int] = field(default_factory=lambda: [5, 10, 15, 20, 30])
    rsi_min: list[float] = field(default_factory=lambda: [30.0, 40.0, 50.0])
    rsi_max: list[float] = field(default_factory=lambda: [60.0, 70.0, 80.0])
    volume_ratio_min: list[float] = field(default_factory=lambda: [0.8, 1.2, 2.0])


@dataclass
class OptimizationResult:
    """최적화 결과"""
    symbol: str
    market: str
    best_params: dict
    sharpe_ratio: float
    win_rate: float
    avg_return_pct: float
    max_drawdown_pct: float
    n_trades: float
    validation_sharpe: float
    optimized_at: str
    is_reliable: bool


# 클램핑 범위
_STOP_LOSS_RANGE = (2.0, 15.0)
_TAKE_PROFIT_RANGE = (4.0, 30.0)
_HOLDING_DAYS_RANGE = (3, 60)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# 조건부 부트스트랩에서 유효 진입 신호가 이 값 미만이면 해당 조합을 스킵
_MIN_ENTRY_SIGNALS = 10


def _compute_rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder의 평활 이동 평균 방식으로 RSI를 계산한다.

    Returns:
        shape (n,) — 처음 period개는 nan
    """
    rsi = np.full(len(closes), np.nan)
    if len(closes) <= period:
        return rsi
    deltas = np.diff(closes.astype(float))
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss < 1e-12:
            rsi[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i + 1] = 100.0 - 100.0 / (1.0 + rs)
    return rsi


def _compute_volume_ratio(volumes: np.ndarray, period: int = 20) -> np.ndarray:
    """각 날의 거래량 / 과거 period일 평균 거래량을 반환한다.

    Returns:
        shape (n,) — 처음 period-1개는 nan
    """
    vols = volumes.astype(float)
    vol_ratio = np.full(len(vols), np.nan)
    if len(vols) < period:
        return vol_ratio
    from numpy.lib.stride_tricks import sliding_window_view
    windows = sliding_window_view(vols, period)
    avgs = windows.mean(axis=1)
    mask = avgs > 0
    vol_ratio[period - 1:][mask] = vols[period - 1:][mask] / avgs[mask]
    return vol_ratio


def generate_price_paths(
    returns: np.ndarray,
    n_simulations: int,
    simulation_days: int,
    method: str = "bootstrap",
    seed: int = 42,
) -> np.ndarray:
    """과거 수익률로 미래 가격 경로를 생성한다.

    Returns:
        shape (n_simulations, simulation_days) — 시작가 1.0 기준 누적 경로
    """
    rng = np.random.default_rng(seed)
    if method == "bootstrap":
        sampled = rng.choice(returns, size=(n_simulations, simulation_days), replace=True)
        paths = np.cumprod(1.0 + sampled, axis=1)
    else:  # gbm
        mu = float(np.mean(returns))
        sigma = float(np.std(returns))
        dt = 1.0
        Z = rng.standard_normal((n_simulations, simulation_days))
        daily_rets = np.exp((mu - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * Z)
        paths = np.cumprod(daily_rets, axis=1)
    return paths


def simulate_strategy(
    paths: np.ndarray,
    stop_loss_pct: float,
    take_profit_pct: float,
    max_holding_days: int,
) -> dict:
    """가격 경로에 매매 전략을 적용하고 성과 지표를 반환한다.

    진입: 경로 시작점(= 1.0)에서 매수
    청산: 익절 / 손절 / 기간만료 중 먼저 충족되는 조건
    """
    n_sim, n_days = paths.shape
    sl = 1.0 - stop_loss_pct / 100.0
    tp = 1.0 + take_profit_pct / 100.0
    hold_cap = min(max_holding_days, n_days)

    p = paths[:, :hold_cap]  # (n_sim, hold_cap)
    hit_sl = p <= sl
    hit_tp = p >= tp

    # 첫 번째 충족 인덱스를 numpy 벡터 연산으로 계산
    def _first_hit(mask: np.ndarray) -> np.ndarray:
        """mask에서 첫 True 인덱스, 없으면 hold_cap."""
        any_hit = mask.any(axis=1)
        idx = np.where(any_hit, np.argmax(mask, axis=1), hold_cap)
        return idx

    sl_idx = _first_hit(hit_sl)
    tp_idx = _first_hit(hit_tp)

    exit_days = np.minimum(sl_idx, tp_idx)
    exit_days = np.where(exit_days >= hold_cap, hold_cap - 1, exit_days)

    exit_returns = paths[np.arange(n_sim), exit_days] - 1.0
    holding_days_arr = exit_days + 1.0

    avg_holding = float(np.mean(holding_days_arr))
    win_mask = exit_returns > 0
    win_rate = float(win_mask.mean())
    avg_return = float(np.mean(exit_returns)) * 100.0
    std_return = float(np.std(exit_returns))

    # 연율화 샤프지수
    if std_return > 1e-9 and avg_holding > 0:
        sharpe = (float(np.mean(exit_returns)) / std_return) * np.sqrt(252.0 / avg_holding)
    else:
        sharpe = 0.0

    # 최대낙폭: 경로별 고점 대비 최저점
    cummax = np.maximum.accumulate(p, axis=1)
    drawdowns = (p - cummax) / cummax
    max_dd = float(np.min(drawdowns)) * 100.0

    return {
        "win_rate": win_rate,
        "avg_return_pct": avg_return,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": max_dd,
        "avg_holding_days": avg_holding,
        "n_profitable": int(win_mask.sum()),
        "n_total": n_sim,
    }


def optimize_params(
    symbol: str,
    market: str,
    price_history: list[dict[str, Any]],
    param_grid: ParamGrid,
    sim_config: SimulationConfig,
) -> OptimizationResult | None:
    """단일 종목에 대해 파라미터 그리드 탐색을 수행한다.

    진입 조건(RSI 범위, 거래량 배수)을 만족하는 날의 수익률만 부트스트랩 샘플로
    사용하는 조건부 몬테카를로 방식으로 실제 전략 진입 조건을 반영한다.
    """
    records = [(r["close"], r.get("volume") or 0.0)
               for r in price_history if r.get("close") is not None]
    if len(records) < sim_config.lookback_days + sim_config.validation_days:
        logger.debug("{}/{}: 데이터 부족 ({} < {})", symbol, market, len(records),
                     sim_config.lookback_days + sim_config.validation_days)
        return None

    closes_full = np.array([r[0] for r in records], dtype=float)
    volumes_full = np.array([r[1] for r in records], dtype=float)

    # 지표를 전체 기간으로 계산 (훈련 시작 전까지 워밍업 포함)
    rsi_full = _compute_rsi(closes_full)
    vol_ratio_full = _compute_volume_ratio(volumes_full)

    returns_full = np.diff(closes_full) / closes_full[:-1]  # shape (n-1,)

    n_train = sim_config.lookback_days
    n_val = sim_config.validation_days

    # 훈련/검증 분리 (returns 배열 기준)
    train_ret = returns_full[-n_train - n_val:-n_val]   # (n_train,)
    val_ret = returns_full[-n_val:]                      # (n_val,)

    # 진입 조건 판별에 쓸 지표 (returns[i]와 동일 인덱스인 closes[i]의 지표)
    # closes_full의 인덱스: returns_full[i] = (closes[i+1]-closes[i])/closes[i]
    # 훈련 구간 closes 인덱스: -n_train-n_val-1 ... -n_val-1
    train_rsi = rsi_full[-n_train - n_val - 1:-n_val - 1]       # (n_train,)
    train_vol = vol_ratio_full[-n_train - n_val - 1:-n_val - 1] # (n_train,)
    val_rsi = rsi_full[-n_val - 1:-1]                            # (n_val,)
    val_vol = vol_ratio_full[-n_val - 1:-1]                      # (n_val,)

    if len(train_ret) < 30:
        return None

    best_sharpe = -np.inf
    best_params: dict = {}
    best_metrics: dict = {}

    # 진입 필터 조합별로 paths를 1회만 생성한 뒤 exit params를 반복
    for rsi_lo, rsi_hi, vol_min in itertools.product(
        param_grid.rsi_min,
        param_grid.rsi_max,
        param_grid.volume_ratio_min,
    ):
        if rsi_lo >= rsi_hi:
            continue

        entry_mask = (
            ~np.isnan(train_rsi) & ~np.isnan(train_vol) &
            (train_rsi >= rsi_lo) & (train_rsi <= rsi_hi) &
            (train_vol >= vol_min)
        )
        entry_idx = np.where(entry_mask)[0]
        if len(entry_idx) < _MIN_ENTRY_SIGNALS:
            continue

        entry_returns = train_ret[entry_idx]
        train_paths = generate_price_paths(
            entry_returns, sim_config.n_simulations, sim_config.simulation_days,
            sim_config.method, sim_config.random_seed,
        )

        for sl, tp, hd in itertools.product(
            param_grid.stop_loss_pct,
            param_grid.take_profit_pct,
            param_grid.max_holding_days,
        ):
            if tp < sl * 1.5:
                continue

            metrics = simulate_strategy(train_paths, sl, tp, hd)
            if metrics["sharpe_ratio"] > best_sharpe:
                best_sharpe = metrics["sharpe_ratio"]
                best_params = {
                    "stop_loss_pct": _clamp(sl, *_STOP_LOSS_RANGE),
                    "take_profit_pct": _clamp(tp, *_TAKE_PROFIT_RANGE),
                    "max_holding_days": int(_clamp(hd, *_HOLDING_DAYS_RANGE)),
                    "rsi_min": rsi_lo,
                    "rsi_max": rsi_hi,
                    "volume_ratio_min": vol_min,
                }
                best_metrics = metrics

    if not best_params:
        return None

    # 검증: 동일 진입 필터를 검증 기간에 적용해 과적합 체크
    val_entry_mask = (
        ~np.isnan(val_rsi) & ~np.isnan(val_vol) &
        (val_rsi >= best_params["rsi_min"]) & (val_rsi <= best_params["rsi_max"]) &
        (val_vol >= best_params["volume_ratio_min"])
    )
    val_entry_idx = np.where(val_entry_mask)[0]
    if len(val_entry_idx) >= _MIN_ENTRY_SIGNALS:
        val_entry_returns = val_ret[val_entry_idx]
    else:
        val_entry_returns = val_ret  # 진입 신호 부족 시 전체 수익률로 fallback

    val_paths = generate_price_paths(
        val_entry_returns, sim_config.n_simulations, sim_config.simulation_days,
        sim_config.method, sim_config.random_seed + 1,
    )
    val_metrics = simulate_strategy(
        val_paths,
        best_params["stop_loss_pct"],
        best_params["take_profit_pct"],
        best_params["max_holding_days"],
    )
    validation_sharpe = val_metrics["sharpe_ratio"]

    return OptimizationResult(
        symbol=symbol,
        market=market,
        best_params=best_params,
        sharpe_ratio=best_sharpe,
        win_rate=best_metrics.get("win_rate", 0.0),
        avg_return_pct=best_metrics.get("avg_return_pct", 0.0),
        max_drawdown_pct=best_metrics.get("max_drawdown_pct", 0.0),
        n_trades=best_metrics.get("avg_holding_days", 0.0),
        validation_sharpe=validation_sharpe,
        optimized_at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        is_reliable=validation_sharpe > 0,
    )


def run_portfolio_optimization(
    symbols: list[tuple[str, str]],
    price_data: dict[str, list[dict[str, Any]]],
    param_grid: ParamGrid | None = None,
    sim_config: SimulationConfig | None = None,
) -> list[OptimizationResult]:
    """여러 종목에 대해 병렬로 optimize_params를 실행한다."""
    if param_grid is None:
        param_grid = ParamGrid()
    if sim_config is None:
        sim_config = SimulationConfig()

    results: list[OptimizationResult] = []
    total = len(symbols)

    def _task(code: str, market: str) -> OptimizationResult | None:
        history = price_data.get(code) or []
        if not history:
            logger.debug("{}/{}: 가격 데이터 없음, 스킵", code, market)
            return None
        try:
            return optimize_params(code, market, history, param_grid, sim_config)
        except Exception as exc:
            logger.warning("{}/{}: 최적화 실패 — {}", code, market, exc)
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(_task, code, market): (code, market)
                   for code, market in symbols}
        done = 0
        for future in as_completed(futures):
            code, market = futures[future]
            done += 1
            result = future.result()
            if result is not None:
                results.append(result)
                logger.info("[{}/{}] {} ({}) — 샤프={:.2f}, 신뢰={}",
                            done, total, code, market,
                            result.sharpe_ratio, result.is_reliable)
            else:
                logger.info("[{}/{}] {} ({}) — 스킵", done, total, code, market)

    return results
