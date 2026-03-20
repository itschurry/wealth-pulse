"""KOSPI100 + S&P100 3년 가상 매매 백테스트 실행."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analyzer.kospi_backtest import BacktestConfig, run_kospi_backtest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--initial-cash", type=float, default=10_000_000)
    parser.add_argument("--max-positions", type=int, default=5)
    parser.add_argument("--max-holding-days", type=int, default=30)
    parser.add_argument("--lookback-days", type=int, default=1095)
    parser.add_argument("--market-scope", choices=["all", "kospi", "nasdaq"], default="all")
    parser.add_argument("--rsi-min", type=float, default=45.0)
    parser.add_argument("--rsi-max", type=float, default=68.0)
    parser.add_argument("--volume-ratio-min", type=float, default=1.2)
    parser.add_argument("--stop-loss-pct", type=float)
    parser.add_argument("--take-profit-pct", type=float)
    parser.add_argument(
        "--output",
        default="report/kospi_backtest_latest.json",
        help="결과 JSON 저장 경로",
    )
    args = parser.parse_args()

    result = run_kospi_backtest(
        BacktestConfig(
            initial_cash=args.initial_cash,
            max_positions=args.max_positions,
            max_holding_days=args.max_holding_days,
            lookback_days=args.lookback_days,
            markets=("KOSPI",) if args.market_scope == "kospi" else ("NASDAQ",) if args.market_scope == "nasdaq" else ("KOSPI", "NASDAQ"),
            rsi_min=min(args.rsi_min, args.rsi_max),
            rsi_max=max(args.rsi_min, args.rsi_max),
            volume_ratio_min=args.volume_ratio_min,
            stop_loss_pct=args.stop_loss_pct,
            take_profit_pct=args.take_profit_pct,
        )
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    metrics = result["metrics"]
    print(
        "[KOSPI100+SP100 backtest]",
        f"final_equity={metrics['final_equity']}",
        f"total_return_pct={metrics['total_return_pct']}",
        f"cagr_pct={metrics['cagr_pct']}",
        f"max_drawdown_pct={metrics['max_drawdown_pct']}",
        f"trade_count={metrics['trade_count']}",
        f"win_rate_pct={metrics['win_rate_pct']}",
        f"sharpe={metrics['sharpe']}",
        f"output={output_path}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
