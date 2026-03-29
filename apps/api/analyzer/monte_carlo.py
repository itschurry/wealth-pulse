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
    stop_loss_pct: list[float] = field(
        default_factory=lambda: [5.0, 8.0, 11.0, 14.0])
    take_profit_pct: list[float] = field(
        default_factory=lambda: [12.0, 18.0, 24.0, 30.0])
    max_holding_days: list[int] = field(
        default_factory=lambda: [15, 25, 35, 45])
    rsi_min: list[float] = field(default_factory=lambda: [32.0, 40.0])
    rsi_max: list[float] = field(default_factory=lambda: [68.0, 76.0])
    volume_ratio_min: list[float] = field(
        default_factory=lambda: [0.8, 1.2])
    adx_min: list[float] = field(default_factory=lambda: [15.0, 20.0])
    mfi_min: list[float] = field(default_factory=lambda: [25.0, 35.0])
    mfi_max: list[float] = field(default_factory=lambda: [65.0, 75.0])
    bb_pct_min: list[float] = field(default_factory=lambda: [0.1, 0.2])
    bb_pct_max: list[float] = field(default_factory=lambda: [0.8, 0.9])
    stoch_k_min: list[float] = field(default_factory=lambda: [15.0, 25.0])
    stoch_k_max: list[float] = field(default_factory=lambda: [75.0, 85.0])


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
    avg_holding_days: float  # 평균 보유 기간 (이전 n_trades 필드명 수정)
    trade_count: int = 0  # 실제 거래 횟수
    validation_sharpe: float = 0.0
    validation_trades: int = 0  # 검증 구간 진입 신호 수
    optimized_at: str = ""
    is_reliable: bool = False
    # "passed", "insufficient_signals", "low_sharpe"
    reliability_reason: str = "unknown"


# ============================================================
# 파라미터 탐색 범위 (몬테카를로 최적화)
# ============================================================
_STOP_LOSS_RANGE = (2.0, 15.0)  # 손절 범위
_TAKE_PROFIT_RANGE = (4.0, 30.0)  # 익절 범위
_HOLDING_DAYS_RANGE = (3, 60)  # 최대 보유 기간 범위


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ============================================================
# 검증 신뢰도 기준
# ============================================================
# - 훈련 구간 진입 필터 콤보 스킵 기준: 너무 희소한 진입 조건 제거
# - 검증 구간 신뢰도는 _MIN_VALIDATION_SIGNALS 기준 사용 (별도 분리)
_MIN_ENTRY_SIGNALS = 5        # 훈련 구간 진입 신호 최소값 (조건을 너무 좁히지 않도록)
_MIN_VALIDATION_SIGNALS = 3   # 검증 구간 최소 신호 수 (단기 검증 구간 대응)
_MIN_SHARPE_RELIABLE = 0.1    # Sharpe Ratio > 0.1일 때만 is_reliable=True


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


def _compute_bollinger_pct(closes: np.ndarray, period: int = 20) -> np.ndarray:
    bb_pct = np.full(len(closes), np.nan)
    if len(closes) < period:
        return bb_pct
    from numpy.lib.stride_tricks import sliding_window_view
    windows = sliding_window_view(closes.astype(float), period)
    means = windows.mean(axis=1)
    stds = windows.std(axis=1)
    upper = means + 2.0 * stds
    lower = means - 2.0 * stds
    denom = upper - lower
    valid = denom > 1e-12
    bb_pct[period - 1:][valid] = (closes[period - 1:]
                                  [valid] - lower[valid]) / denom[valid]
    return bb_pct


def _compute_stoch_k(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    stoch = np.full(len(close), np.nan)
    if len(close) < period:
        return stoch
    from numpy.lib.stride_tricks import sliding_window_view
    high_w = sliding_window_view(high.astype(float), period)
    low_w = sliding_window_view(low.astype(float), period)
    highest = high_w.max(axis=1)
    lowest = low_w.min(axis=1)
    denom = highest - lowest
    valid = denom > 1e-12
    stoch[period - 1:][valid] = ((close[period - 1:]
                                 [valid] - lowest[valid]) / denom[valid]) * 100.0
    return stoch


def _compute_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    adx = np.full(n, np.nan)
    if n <= period + 1:
        return adx

    up_move = high[1:] - high[:-1]
    down_move = low[:-1] - low[1:]
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) &
                        (down_move > 0), down_move, 0.0)

    tr = np.maximum.reduce([
        high[1:] - low[1:],
        np.abs(high[1:] - close[:-1]),
        np.abs(low[1:] - close[:-1]),
    ])

    atr = np.full(len(tr), np.nan)
    plus_di = np.full(len(tr), np.nan)
    minus_di = np.full(len(tr), np.nan)
    dx = np.full(len(tr), np.nan)

    atr[period - 1] = np.mean(tr[:period])
    plus_sum = np.sum(plus_dm[:period])
    minus_sum = np.sum(minus_dm[:period])

    plus_di[period - 1] = 100.0 * \
        (plus_sum / atr[period - 1]) if atr[period - 1] > 1e-12 else 0.0
    minus_di[period - 1] = 100.0 * \
        (minus_sum / atr[period - 1]) if atr[period - 1] > 1e-12 else 0.0
    denom = plus_di[period - 1] + minus_di[period - 1]
    dx[period - 1] = 100.0 * abs(plus_di[period - 1] -
                                 minus_di[period - 1]) / denom if denom > 1e-12 else 0.0

    for i in range(period, len(tr)):
        atr[i] = ((atr[i - 1] * (period - 1)) + tr[i]) / period
        plus_sum = ((plus_sum * (period - 1)) + plus_dm[i]) / period
        minus_sum = ((minus_sum * (period - 1)) + minus_dm[i]) / period
        plus_di[i] = 100.0 * (plus_sum / atr[i]) if atr[i] > 1e-12 else 0.0
        minus_di[i] = 100.0 * (minus_sum / atr[i]) if atr[i] > 1e-12 else 0.0
        di_sum = plus_di[i] + minus_di[i]
        dx[i] = 100.0 * abs(plus_di[i] - minus_di[i]) / \
            di_sum if di_sum > 1e-12 else 0.0

    first_adx_idx = period * 2 - 2
    if first_adx_idx < len(dx):
        adx[first_adx_idx + 1] = np.nanmean(dx[period - 1:first_adx_idx + 1])
        for i in range(first_adx_idx + 2, len(adx)):
            dx_idx = i - 1
            adx[i] = ((adx[i - 1] * (period - 1)) + dx[dx_idx]) / period

    return adx


def _compute_mfi(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    mfi = np.full(n, np.nan)
    if n <= period:
        return mfi
    typical = (high + low + close) / 3.0
    raw_flow = typical * volume

    pos_flow = np.zeros(n)
    neg_flow = np.zeros(n)
    delta_tp = typical[1:] - typical[:-1]
    pos_flow[1:] = np.where(delta_tp > 0, raw_flow[1:], 0.0)
    neg_flow[1:] = np.where(delta_tp < 0, raw_flow[1:], 0.0)

    from numpy.lib.stride_tricks import sliding_window_view
    pos_sum = sliding_window_view(pos_flow, period).sum(axis=1)
    neg_sum = sliding_window_view(neg_flow, period).sum(axis=1)

    money_ratio = np.divide(pos_sum, neg_sum, out=np.full_like(
        pos_sum, np.inf), where=neg_sum > 1e-12)
    mfi_values = 100.0 - (100.0 / (1.0 + money_ratio))
    mfi[period - 1:] = mfi_values
    return mfi


def generate_price_paths(
    returns: np.ndarray,
    n_simulations: int,
    simulation_days: int,
    method: str = "bootstrap",
    seed: int = 42,
) -> np.ndarray:
    """과거 수익률로 미래 가격 경로를 생성한다.

    Phase 4: Block Bootstrap 추가
    - "bootstrap": 단순 복원 샘플링 (기존)
    - "block_bootstrap": 연속 블록 샘플링 (시장 구간 특성 보존)
    - "gbm": 기하 브라운 운동 (기존)

    Returns:
        shape (n_simulations, simulation_days) — 시작가 1.0 기준 누적 경로
    """
    rng = np.random.default_rng(seed)

    if method == "block_bootstrap":
        # Phase 4: Block Bootstrap 구현
        # 목적: 시장의 연속성(클러스터)을 보존하여 현실성 향상
        block_size = max(2, int(np.sqrt(len(returns))))  # 블록 크기: sqrt(n)
        n_blocks = simulation_days // block_size + 1
        sampled_list = []

        for _ in range(n_simulations):
            path_returns = []
            for _ in range(n_blocks):
                # 랜덤 블록 위치 선택
                block_start = rng.integers(0, len(returns) - block_size + 1)
                block = returns[block_start:block_start + block_size]
                path_returns.extend(block)
            sampled_list.append(path_returns[:simulation_days])

        sampled = np.array(sampled_list)
        paths = np.cumprod(1.0 + sampled, axis=1)

    elif method == "bootstrap":
        # 단순 복원 샘플링 (기존)
        sampled = rng.choice(returns, size=(
            n_simulations, simulation_days), replace=True)
        paths = np.cumprod(1.0 + sampled, axis=1)

    else:  # gbm
        mu = float(np.mean(returns))
        sigma = float(np.std(returns))
        dt = 1.0
        Z = rng.standard_normal((n_simulations, simulation_days))
        daily_rets = np.exp((mu - 0.5 * sigma ** 2) *
                            dt + sigma * np.sqrt(dt) * Z)
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
        sharpe = (float(np.mean(exit_returns)) / std_return) * \
            np.sqrt(252.0 / avg_holding)
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


def _compute_composite_score(metrics: dict[str, float]) -> float:
    """
    다중 지표 기반 복합 점수 계산 (Phase 3 - 최적화 목적함수 개선)

    목표: Sharpe만이 아니라 견고성(낙폭, 승률, 거래 수)도 함께 고려해서
    과적합 가능성이 낮은 전략을 우선한다.

    계산식:
    - 기본 점수: sharpe_ratio * 100
    - 낙폭 페널티: max_drawdown <= -30% 이면 -50점  
    - 승률 보너스: win_rate >= 50% 이면 +20점
    - 거래 수 요구: n_total < 30이면 -10점 (표본 부족)
    """
    sharpe = metrics.get("sharpe_ratio", 0.0)
    max_dd = metrics.get("max_drawdown_pct", 0.0)
    win_rate = metrics.get("win_rate", 0.0)
    n_total = int(metrics.get("n_total", 1))

    score = sharpe * 100.0  # 기본: Sharpe 점수화

    # 낙폭 페널티: -30% 초과는 크게 감점
    if max_dd < -30.0:
        score -= 50.0
    elif max_dd < -20.0:
        score -= 20.0

    # 승률 보너스: 50% 이상이면 추가
    if win_rate >= 50.0:
        score += 20.0
    elif win_rate >= 40.0:
        score += 10.0

    # 거래 표본 페널티: 너무 적으면 감점 (과적합 위험)
    if n_total < 20:
        score -= 10.0

    return score


def _should_use_result(result: OptimizationResult) -> bool:
    """
    최적화 결과의 신뢰도 필터 (Phase 3)

    자동 탈락 조건:
    - validation_trades < _MIN_VALIDATION_SIGNALS (검증 신호 부족)
    - validation_sharpe <= 0 (검증 구간에서 음수 Sharpe)
    - max_drawdown_pct < -40% (과도한 낙폭)
    - trade_count < 10 (훈련 구간 거래 표본 부족)
    """
    if result.validation_trades < _MIN_VALIDATION_SIGNALS:
        return False  # 검증 신호 부족
    if result.validation_sharpe <= 0.0:
        return False  # 검증 구간 부정적
    if result.max_drawdown_pct < -40.0:
        return False  # 과도한 낙폭
    if result.trade_count < 10:
        return False  # 훈련 표본 부족
    return True


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
    records: list[dict[str, float]] = []
    for row in price_history:
        close = row.get("close")
        if close is None:
            continue
        close_f = float(close)
        high_f = float(row.get("high") or row.get("high_price") or close_f)
        low_f = float(row.get("low") or row.get("low_price") or close_f)
        vol_f = float(row.get("volume") or 0.0)
        records.append({"close": close_f, "high": high_f,
                       "low": low_f, "volume": vol_f})

    if len(records) < sim_config.lookback_days + sim_config.validation_days:
        logger.debug("{}/{}: 데이터 부족 ({} < {})", symbol, market, len(records),
                     sim_config.lookback_days + sim_config.validation_days)
        return None

    closes_full = np.array([r["close"] for r in records], dtype=float)
    highs_full = np.array([r["high"] for r in records], dtype=float)
    lows_full = np.array([r["low"] for r in records], dtype=float)
    volumes_full = np.array([r["volume"] for r in records], dtype=float)

    # 지표를 전체 기간으로 계산 (훈련 시작 전까지 워밍업 포함)
    rsi_full = _compute_rsi(closes_full)
    vol_ratio_full = _compute_volume_ratio(volumes_full)
    adx_full = _compute_adx(highs_full, lows_full, closes_full)
    mfi_full = _compute_mfi(highs_full, lows_full, closes_full, volumes_full)
    bb_pct_full = _compute_bollinger_pct(closes_full)
    stoch_k_full = _compute_stoch_k(highs_full, lows_full, closes_full)

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
    train_vol = vol_ratio_full[-n_train - n_val - 1:-n_val - 1]  # (n_train,)
    train_adx = adx_full[-n_train - n_val - 1:-n_val - 1]
    train_mfi = mfi_full[-n_train - n_val - 1:-n_val - 1]
    train_bb = bb_pct_full[-n_train - n_val - 1:-n_val - 1]
    train_stoch = stoch_k_full[-n_train - n_val - 1:-n_val - 1]
    val_rsi = rsi_full[-n_val - 1:-1]                            # (n_val,)
    val_vol = vol_ratio_full[-n_val - 1:-1]                      # (n_val,)
    val_adx = adx_full[-n_val - 1:-1]
    val_mfi = mfi_full[-n_val - 1:-1]
    val_bb = bb_pct_full[-n_val - 1:-1]
    val_stoch = stoch_k_full[-n_val - 1:-1]

    if len(train_ret) < 30:
        return None

    best_score = -np.inf  # 복합 점수 기반 선택 (Phase 3)
    best_params: dict = {}
    best_metrics: dict = {}

    # 진입 필터 조합별로 paths를 1회만 생성한 뒤 exit params를 반복
    for rsi_lo, rsi_hi, vol_min, adx_min, mfi_lo, mfi_hi, bb_lo, bb_hi, stoch_lo, stoch_hi in itertools.product(
        param_grid.rsi_min,
        param_grid.rsi_max,
        param_grid.volume_ratio_min,
        param_grid.adx_min,
        param_grid.mfi_min,
        param_grid.mfi_max,
        param_grid.bb_pct_min,
        param_grid.bb_pct_max,
        param_grid.stoch_k_min,
        param_grid.stoch_k_max,
    ):
        if rsi_lo >= rsi_hi or mfi_lo >= mfi_hi or bb_lo >= bb_hi or stoch_lo >= stoch_hi:
            continue

        entry_mask = (
            ~np.isnan(train_rsi) & ~np.isnan(train_vol) & ~np.isnan(train_adx) &
            ~np.isnan(train_mfi) & ~np.isnan(train_bb) & ~np.isnan(train_stoch) &
            (train_rsi >= rsi_lo) & (train_rsi <= rsi_hi) &
            (train_vol >= vol_min) &
            (train_adx >= adx_min) &
            (train_mfi >= mfi_lo) & (train_mfi <= mfi_hi) &
            (train_bb >= bb_lo) & (train_bb <= bb_hi) &
            (train_stoch >= stoch_lo) & (train_stoch <= stoch_hi)
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
            # Phase 3: Sharpe만이 아니라 다중 지표 복합 점수로 비교
            composite_score = _compute_composite_score(metrics)
            if composite_score > best_score:
                best_score = composite_score
                best_params = {
                    "stop_loss_pct": _clamp(sl, *_STOP_LOSS_RANGE),
                    "take_profit_pct": _clamp(tp, *_TAKE_PROFIT_RANGE),
                    "max_holding_days": int(_clamp(hd, *_HOLDING_DAYS_RANGE)),
                    "rsi_min": rsi_lo,
                    "rsi_max": rsi_hi,
                    "volume_ratio_min": vol_min,
                    "adx_min": adx_min,
                    "mfi_min": mfi_lo,
                    "mfi_max": mfi_hi,
                    "bb_pct_min": bb_lo,
                    "bb_pct_max": bb_hi,
                    "stoch_k_min": stoch_lo,
                    "stoch_k_max": stoch_hi,
                }
                best_metrics = metrics

    if not best_params:
        return None

    # 검증: 동일 진입 필터를 검증 기간에 적용해 과적합 체크
    val_entry_mask = (
        ~np.isnan(val_rsi) & ~np.isnan(val_vol) & ~np.isnan(val_adx) &
        ~np.isnan(val_mfi) & ~np.isnan(val_bb) & ~np.isnan(val_stoch) &
        (val_rsi >= best_params["rsi_min"]) & (val_rsi <= best_params["rsi_max"]) &
        (val_vol >= best_params["volume_ratio_min"]) &
        (val_adx >= best_params["adx_min"]) &
        (val_mfi >= best_params["mfi_min"]) & (val_mfi <= best_params["mfi_max"]) &
        (val_bb >= best_params["bb_pct_min"]) & (val_bb <= best_params["bb_pct_max"]) &
        (val_stoch >= best_params["stoch_k_min"]) & (
            val_stoch <= best_params["stoch_k_max"])
    )
    val_entry_idx = np.where(val_entry_mask)[0]
    validation_signals = len(val_entry_idx)
    reliability_reason = "passed"

    # 검증 구간 신호가 _MIN_VALIDATION_SIGNALS 미만이면 신뢰도 부족으로 처리
    if validation_signals < _MIN_VALIDATION_SIGNALS:
        validation_sharpe = 0.0
        reliability_reason = "insufficient_signals"
    else:
        val_entry_returns = val_ret[val_entry_idx]
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
        if validation_sharpe <= 0.1:
            reliability_reason = "low_sharpe"

    return OptimizationResult(
        symbol=symbol,
        market=market,
        best_params=best_params,
        sharpe_ratio=best_metrics.get("sharpe_ratio", 0.0),
        win_rate=best_metrics.get("win_rate", 0.0),
        avg_return_pct=best_metrics.get("avg_return_pct", 0.0),
        max_drawdown_pct=best_metrics.get("max_drawdown_pct", 0.0),
        avg_holding_days=best_metrics.get("avg_holding_days", 0.0),
        trade_count=best_metrics.get("n_total", 0),
        validation_sharpe=validation_sharpe,
        validation_trades=validation_signals,
        optimized_at=datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds"),
        is_reliable=(validation_sharpe >
                     0.1 and validation_signals >= _MIN_VALIDATION_SIGNALS),
        reliability_reason=reliability_reason,
    )


def run_portfolio_optimization(
    symbols: list[tuple[str, str]],
    price_data: dict[str, list[dict[str, Any]]],
    param_grid: ParamGrid | None = None,
    sim_config: SimulationConfig | None = None,
) -> list[OptimizationResult]:
    """여러 종목에 대해 병렬로 optimize_params를 실행한다.

    Phase 3: 신뢰도 필터 추가
    - 신뢰도가 낮은 결과는 자동으로 제외 (검증 신호 부족, 과도한 낙폭 등)
    """
    if param_grid is None:
        param_grid = ParamGrid()
    if sim_config is None:
        sim_config = SimulationConfig()

    results: list[OptimizationResult] = []
    filtered_results: list[OptimizationResult] = []  # Phase 3: 신뢰도 필터링 후 결과
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
                # Phase 3: 신뢰도 필터 적용
                if _should_use_result(result):
                    filtered_results.append(result)
                    logger.info("[{}/{}] {} ({}) — 샤프={:.2f}, VAL신호={}, 신뢰=✓",
                                done, total, code, market,
                                result.sharpe_ratio, result.validation_trades)
                else:
                    logger.info("[{}/{}] {} ({}) — 신뢰도 부족 (reason:{})",
                                done, total, code, market, result.reliability_reason)
            else:
                logger.info("[{}/{}] {} ({}) — 최적화 실패",
                            done, total, code, market)

    logger.info("최종 결과: 전체 {}개 중 신뢰 가능 {}개 (필터율: {:.1f}%)",
                len(results), len(filtered_results),
                (1 - len(filtered_results) / max(1, len(results))) * 100)

    # 신뢰 가능 결과가 없어도 전체 결과를 반환한다.
    # is_reliable 필드가 각 결과에 포함되어 있으므로 호출자가 필터링할 수 있고,
    # _save_results()가 빈 리스트로 조기 종료되는 것을 방지한다.
    return results
