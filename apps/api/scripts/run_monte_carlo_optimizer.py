"""몬테카를로 파라미터 최적화 실행 스크립트.

실행 방법:
  python3 scripts/run_monte_carlo_optimizer.py
  python3 scripts/run_monte_carlo_optimizer.py --market KOSPI --top-n 20
  python3 scripts/run_monte_carlo_optimizer.py --market NASDAQ --top-n 20
  python3 scripts/run_monte_carlo_optimizer.py --symbols 005930,000660,NVDA,MSFT
"""
from __future__ import annotations
from config.backtest_universe import get_kospi100_universe, get_sp100_nasdaq_universe
from analyzer.monte_carlo import (
    OptimizationResult,
    ParamGrid,
    SimulationConfig,
    run_portfolio_optimization,
)
from loguru import logger

import argparse
import datetime
import json
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


_OPTIMIZED_PARAMS_PATH = _PROJECT_ROOT / "config" / "optimized_params.json"

# 파라미터 클램핑 범위
_STOP_LOSS_RANGE = (2.0, 15.0)
_TAKE_PROFIT_RANGE = (4.0, 30.0)
_HOLDING_DAYS_RANGE = (3, 60)
_VOLUME_RATIO_RANGE = (0.5, 3.0)
_ADX_RANGE = (5.0, 40.0)
_MFI_RANGE = (0.0, 100.0)
_BB_PCT_RANGE = (0.0, 1.0)
_STOCH_K_RANGE = (0.0, 100.0)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _fetch_kis_history(code: str, market: str, days: int) -> list[dict]:
    """KIS API로 일봉 히스토리를 가져온다. 실패 시 빈 리스트 반환."""
    try:
        from broker.kis_client import KISClient
        if not KISClient.is_configured():
            return []
        client = KISClient.from_env()
        end = datetime.date.today().strftime("%Y%m%d")
        start = (datetime.date.today() -
                 datetime.timedelta(days=days)).strftime("%Y%m%d")
        if market == "KOSPI":
            return client.get_domestic_daily_history(code, start_date=start, end_date=end)
        else:
            return client.get_overseas_daily_history(code, exchange=market, start_date=start, end_date=end)
    except Exception as exc:
        logger.debug("{}/{}: KIS 조회 실패 — {}", code, market, exc)
        return []


def _fetch_yahoo_history(code: str, market: str, days: int) -> list[dict]:
    """Yahoo Finance Chart API로 일봉 OHLCV를 가져온다. 실패 시 빈 리스트 반환.

    KOSPI 종목은 '{code}.KS' 형식으로 조회한다.
    """
    try:
        import urllib.request
        import urllib.parse
        import json as _json

        ticker = f"{code}.KS" if market == "KOSPI" else code
        # days → Yahoo range 문자열 (6mo ≈ 126일, 1y ≈ 252일, 2y ≈ 504일)
        if days <= 130:
            range_str = "6mo"
        elif days <= 260:
            range_str = "1y"
        else:
            range_str = "2y"

        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}"
            f"?range={range_str}&interval=1d&includeAdjustedClose=false"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = _json.loads(resp.read().decode())

        result = payload["chart"]["result"][0]
        timestamps = result.get("timestamp", [])
        quote = result["indicators"]["quote"][0]
        opens = quote.get("open", [])
        highs = quote.get("high", [])
        lows = quote.get("low", [])
        closes = quote.get("close", [])
        volumes = quote.get("volume", [])

        rows: list[dict] = []
        for i, ts in enumerate(timestamps):
            c = closes[i] if i < len(closes) else None
            if c is None:
                continue
            rows.append({
                "close": float(c),
                "high": float(highs[i]) if i < len(highs) and highs[i] is not None else float(c),
                "low": float(lows[i]) if i < len(lows) and lows[i] is not None else float(c),
                "volume": float(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0.0,
            })
        return rows
    except Exception as exc:
        logger.debug("{}/{}: Yahoo Finance 조회 실패 — {}", code, market, exc)
        return []


def _fetch_price_history(code: str, market: str, days: int, min_rows: int = 80) -> list[dict]:
    """KIS API로 가격 데이터를 가져온다. 부족하면 Yahoo Finance로 폴백한다."""
    rows = _fetch_kis_history(code, market, days)
    if len(rows) >= min_rows:
        return rows
    logger.debug("{}/{}: KIS {} 건 (필요 {} 건) — Yahoo Finance 폴백 시도",
                 code, market, len(rows), min_rows)
    rows = _fetch_yahoo_history(code, market, days)
    if len(rows) >= min_rows:
        logger.debug("{}/{}: Yahoo Finance {} 건 수집 성공", code, market, len(rows))
        return rows
    logger.debug("{}/{}: Yahoo Finance {} 건 (필요 {} 건) — 데이터 부족",
                 code, market, len(rows), min_rows)
    return []


def _collect_price_data(
    symbols: list[tuple[str, str]],
    days: int,
    min_rows: int = 80,
) -> dict[str, list[dict]]:
    """종목 목록의 가격 데이터를 수집한다."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    price_data: dict[str, list[dict]] = {}
    total = len(symbols)

    def _task(code: str, market: str) -> tuple[str, list[dict]]:
        return code, _fetch_price_history(code, market, days, min_rows=min_rows)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_task, code, mkt): (
            code, mkt) for code, mkt in symbols}
        done = 0
        for future in as_completed(futures):
            code, mkt = futures[future]
            done += 1
            rows = future.result()[1]
            price_data[code] = rows
            logger.debug("[{}/{}] {} ({}) — {}건 수집", done,
                         total, code, mkt, len(rows))

    return price_data


def _compute_global_params(results: list[OptimizationResult]) -> dict:
    """신뢰 종목들의 파라미터 중앙값으로 글로벌 파라미터를 계산한다."""
    import numpy as np
    reliable = [r for r in results if r.is_reliable]
    if not reliable:
        reliable = results  # 모두 신뢰 없으면 전체 사용

    return {
        "stop_loss_pct": round(float(np.median([r.best_params["stop_loss_pct"] for r in reliable])), 1),
        "take_profit_pct": round(float(np.median([r.best_params["take_profit_pct"] for r in reliable])), 1),
        "max_holding_days": int(round(float(np.median([r.best_params["max_holding_days"] for r in reliable])))),
        "rsi_min": round(float(np.median([r.best_params["rsi_min"] for r in reliable])), 1),
        "rsi_max": round(float(np.median([r.best_params["rsi_max"] for r in reliable])), 1),
        "volume_ratio_min": round(float(np.median([r.best_params.get("volume_ratio_min", 1.0) for r in reliable])), 2),
        "adx_min": round(float(np.median([r.best_params.get("adx_min", 15.0) for r in reliable])), 1),
        "mfi_min": round(float(np.median([r.best_params.get("mfi_min", 25.0) for r in reliable])), 1),
        "mfi_max": round(float(np.median([r.best_params.get("mfi_max", 75.0) for r in reliable])), 1),
        "bb_pct_min": round(float(np.median([r.best_params.get("bb_pct_min", 0.1) for r in reliable])), 3),
        "bb_pct_max": round(float(np.median([r.best_params.get("bb_pct_max", 0.9) for r in reliable])), 3),
        "stoch_k_min": round(float(np.median([r.best_params.get("stoch_k_min", 15.0) for r in reliable])), 1),
        "stoch_k_max": round(float(np.median([r.best_params.get("stoch_k_max", 85.0) for r in reliable])), 1),
    }


def _save_results(
    results: list[OptimizationResult],
    sim_config: SimulationConfig,
    name_map: dict[str, str] | None = None,
) -> None:
    """결과를 config/optimized_params.json에 저장한다."""
    reliable = [r for r in results if r.is_reliable]
    global_params = _compute_global_params(results) if results else {}

    # 클램핑
    if global_params:
        global_params["stop_loss_pct"] = _clamp(
            global_params["stop_loss_pct"], *_STOP_LOSS_RANGE)
        global_params["take_profit_pct"] = _clamp(
            global_params["take_profit_pct"], *_TAKE_PROFIT_RANGE)
        global_params["max_holding_days"] = int(
            _clamp(global_params["max_holding_days"], *_HOLDING_DAYS_RANGE))
        global_params["volume_ratio_min"] = round(
            _clamp(global_params["volume_ratio_min"], *_VOLUME_RATIO_RANGE), 2)
        global_params["adx_min"] = round(
            _clamp(global_params["adx_min"], *_ADX_RANGE), 1)
        global_params["mfi_min"] = round(
            _clamp(global_params["mfi_min"], *_MFI_RANGE), 1)
        global_params["mfi_max"] = round(
            _clamp(global_params["mfi_max"], *_MFI_RANGE), 1)
        global_params["bb_pct_min"] = round(
            _clamp(global_params["bb_pct_min"], *_BB_PCT_RANGE), 3)
        global_params["bb_pct_max"] = round(
            _clamp(global_params["bb_pct_max"], *_BB_PCT_RANGE), 3)
        global_params["stoch_k_min"] = round(
            _clamp(global_params["stoch_k_min"], *_STOCH_K_RANGE), 1)
        global_params["stoch_k_max"] = round(
            _clamp(global_params["stoch_k_max"], *_STOCH_K_RANGE), 1)

    per_symbol = {}
    for r in results:
        params = {k: _clamp(v, *_STOP_LOSS_RANGE) if k == "stop_loss_pct"
                  else _clamp(v, *_TAKE_PROFIT_RANGE) if k == "take_profit_pct"
                  else int(_clamp(v, *_HOLDING_DAYS_RANGE)) if k == "max_holding_days"
                  else round(_clamp(v, *_VOLUME_RATIO_RANGE), 2) if k == "volume_ratio_min"
                  else round(_clamp(v, *_ADX_RANGE), 1) if k == "adx_min"
                  else round(_clamp(v, *_MFI_RANGE), 1) if k in {"mfi_min", "mfi_max"}
                  else round(_clamp(v, *_BB_PCT_RANGE), 3) if k in {"bb_pct_min", "bb_pct_max"}
                  else round(_clamp(v, *_STOCH_K_RANGE), 1) if k in {"stoch_k_min", "stoch_k_max"}
                  else v
                  for k, v in r.best_params.items()}
        # Phase 5: 신뢰도 정보 확대 저장
        per_symbol[r.symbol] = {
            "name": (name_map or {}).get(r.symbol, r.symbol),
            "market": r.market,
            **params,
            "sharpe_ratio": float(round(r.sharpe_ratio, 4)),
            "win_rate": float(round(r.win_rate, 4)),
            "avg_return_pct": float(round(r.avg_return_pct, 4)),
            "max_drawdown_pct": float(round(r.max_drawdown_pct, 4)),
            "avg_holding_days": float(round(r.avg_holding_days, 2)),
            "trade_count": int(r.trade_count),
            "validation_sharpe": float(round(r.validation_sharpe, 4)),
            "validation_trades": int(r.validation_trades),
            "is_reliable": bool(r.is_reliable),
            "reliability_reason": str(r.reliability_reason),
        }

    output = {
        "optimized_at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds"),
        "global_params": global_params,
        "per_symbol": per_symbol,
        "meta": {
            "n_simulations": sim_config.n_simulations,
            "method": sim_config.method,
            "n_symbols_optimized": len(results),
            "n_reliable": len(reliable),
        },
    }
    _OPTIMIZED_PARAMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OPTIMIZED_PARAMS_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("결과 저장: {}", _OPTIMIZED_PARAMS_PATH)


def _build_symbol_list(args: argparse.Namespace) -> list[tuple[str, str, str]]:
    """CLI 인자에 따라 최적화 대상 종목 목록을 반환한다. (code, market, name)"""
    if args.symbols:
        result = []
        for s in args.symbols.split(","):
            s = s.strip().upper()
            if not s:
                continue
            market = "KOSPI" if s.isdigit() else "NASDAQ"
            result.append((s, market, s))
        return result

    top_n = args.top_n
    markets = [args.market] if args.market else ["KOSPI", "NASDAQ"]
    symbols: list[tuple[str, str, str]] = []

    if "KOSPI" in markets:
        entries = get_kospi100_universe()[:top_n]
        symbols += [(e["code"], "KOSPI", e["name"]) for e in entries]
    if "NASDAQ" in markets:
        entries = get_sp100_nasdaq_universe()[:top_n]
        symbols += [(e["code"], "NASDAQ", e["name"]) for e in entries]

    return symbols


def main() -> None:
    parser = argparse.ArgumentParser(description="몬테카를로 파라미터 최적화")
    parser.add_argument("--market", choices=["KOSPI", "NASDAQ"], default=None,
                        help="특정 시장만 실행 (기본: 양쪽)")
    parser.add_argument("--top-n", type=int, default=20,
                        help="시장별 상위 N개 종목 (기본: 20)")
    parser.add_argument("--symbols", type=str, default=None,
                        help="쉼표 구분 종목 코드 (예: 005930,NVDA)")
    parser.add_argument("--simulations", type=int, default=5000,
                        help="시뮬레이션 횟수 (기본: 5000)")
    parser.add_argument(
        "--method", choices=["bootstrap", "gbm"], default="bootstrap")
    parser.add_argument("--lookback-days", type=int, default=None,
                        help="학습 기간 일수 (기본: SimulationConfig 기본값 252)")
    parser.add_argument("--validation-days", type=int, default=None,
                        help="검증 기간 일수 (기본: SimulationConfig 기본값 63)")
    args = parser.parse_args()

    symbols = _build_symbol_list(args)
    if not symbols:
        logger.error("최적화할 종목이 없습니다.")
        sys.exit(1)

    name_map = {code: name for code, _, name in symbols}
    sym_pairs = [(code, market) for code, market, _ in symbols]

    logger.info("=== 몬테카를로 최적화 시작: {}개 종목 ===", len(sym_pairs))

    sim_kwargs: dict = {
        "n_simulations": args.simulations, "method": args.method}
    if args.lookback_days is not None:
        sim_kwargs["lookback_days"] = args.lookback_days
    if args.validation_days is not None:
        sim_kwargs["validation_days"] = args.validation_days
    sim_config = SimulationConfig(**sim_kwargs)

    # 실제로 필요한 최소 데이터 건수 = 학습 + 검증 기간
    min_rows = sim_config.lookback_days + sim_config.validation_days
    required_days = min_rows + 50
    logger.info("가격 데이터 수집 중 (최근 {}일, 최소 {}건)...", required_days, min_rows)
    price_data = _collect_price_data(
        sym_pairs, required_days, min_rows=min_rows)

    logger.info("파라미터 최적화 실행 중...")
    results = run_portfolio_optimization(
        sym_pairs, price_data, sim_config=sim_config)

    if not results:
        logger.warning("1차 최적화 결과가 없습니다. 완화된 필터로 재시도합니다.")
        relaxed_grid = ParamGrid(
            stop_loss_pct=[5.0, 10.0],
            take_profit_pct=[12.0, 20.0],
            max_holding_days=[15, 25],
            rsi_min=[30.0],
            rsi_max=[80.0],
            volume_ratio_min=[0.6],
            adx_min=[5.0],
            mfi_min=[0.0],
            mfi_max=[100.0],
            bb_pct_min=[0.0],
            bb_pct_max=[1.0],
            stoch_k_min=[0.0],
            stoch_k_max=[100.0],
        )
        results = run_portfolio_optimization(
            sym_pairs, price_data, param_grid=relaxed_grid, sim_config=sim_config
        )

    if not results:
        logger.error("최적화 결과가 없어 빈 결과 파일을 저장합니다.")
        _save_results([], sim_config, name_map=name_map)
        return

    reliable = [r for r in results if r.is_reliable]
    logger.info("최적화 완료: {}개 종목, 신뢰할 수 있는 결과: {}개",
                len(results), len(reliable))

    if reliable:
        gp = _compute_global_params(results)
        logger.info(
            "글로벌 최적 파라미터 (신뢰 종목 중앙값): "
            "stop_loss={stop_loss_pct}%, take_profit={take_profit_pct}%, "
            "max_holding={max_holding_days}일, rsi={rsi_min}~{rsi_max}, "
            "adx>={adx_min}, mfi={mfi_min}~{mfi_max}, bb%={bb_pct_min}~{bb_pct_max}, stoch={stoch_k_min}~{stoch_k_max}",
            **gp,
        )

    _save_results(results, sim_config, name_map=name_map)


if __name__ == "__main__":
    main()
