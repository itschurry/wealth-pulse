"""KOSPI100 + S&P100 3년 가상 매매 백테스트 실행."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analyzer.candidate_selector import normalize_candidate_selection_config
from analyzer.kospi_backtest import BacktestConfig, run_kospi_backtest
from analyzer.shared_strategy import build_strategy_profile, default_strategy_profiles
from config.settings import REPORT_OUTPUT_DIR


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--initial-cash", type=float, default=10_000_000)
    parser.add_argument("--max-positions", type=int)
    parser.add_argument("--max-holding-days", type=int)
    parser.add_argument("--lookback-days", type=int, default=1095)
    parser.add_argument("--market-scope", choices=["all", "kospi", "nasdaq"], default="all")
    parser.add_argument("--rsi-min", type=float)
    parser.add_argument("--rsi-max", type=float)
    parser.add_argument("--volume-ratio-min", type=float)
    parser.add_argument("--stop-loss-pct", type=float)
    parser.add_argument("--take-profit-pct", type=float)
    parser.add_argument("--candidate-selection-enabled", dest="candidate_selection_enabled", action="store_true")
    parser.add_argument("--candidate-selection-disabled", dest="candidate_selection_enabled", action="store_false")
    # Historical report/news candidate filtering must be explicitly enabled.
    parser.set_defaults(candidate_selection_enabled=False)
    parser.add_argument("--min-score", type=float, default=50.0)
    parser.add_argument("--include-neutral", dest="include_neutral", action="store_true")
    parser.add_argument("--exclude-neutral", dest="include_neutral", action="store_false")
    parser.set_defaults(include_neutral=True)
    parser.add_argument("--theme-gate-enabled", dest="theme_gate_enabled", action="store_true")
    parser.add_argument("--theme-gate-disabled", dest="theme_gate_enabled", action="store_false")
    parser.set_defaults(theme_gate_enabled=True)
    parser.add_argument("--theme-min-score", type=float, default=2.5)
    parser.add_argument("--theme-min-news", type=int, default=1)
    parser.add_argument("--theme-priority-bonus", type=float, default=2.0)
    parser.add_argument(
        "--output",
        default=str(REPORT_OUTPUT_DIR / "kospi_backtest_latest.json"),
        help="결과 JSON 저장 경로",
    )
    args = parser.parse_args()
    markets = ("KOSPI",) if args.market_scope == "kospi" else ("NASDAQ",) if args.market_scope == "nasdaq" else ("KOSPI", "NASDAQ")
    overrides = {
        key: value
        for key, value in {
            "max_positions": args.max_positions,
            "max_holding_days": args.max_holding_days,
            "rsi_min": args.rsi_min,
            "rsi_max": args.rsi_max,
            "volume_ratio_min": args.volume_ratio_min,
            "stop_loss_pct": args.stop_loss_pct,
            "take_profit_pct": args.take_profit_pct,
        }.items()
        if value is not None
    }
    market_profiles = tuple(
        build_strategy_profile(profile.market, **overrides)
        for profile in default_strategy_profiles(markets)
    )
    primary_profile = market_profiles[0]
    candidate_selection = normalize_candidate_selection_config(
        {
            "min_score": args.min_score,
            "include_neutral": args.include_neutral,
            "theme_gate_enabled": args.theme_gate_enabled,
            "theme_min_score": args.theme_min_score,
            "theme_min_news": args.theme_min_news,
            "theme_priority_bonus": args.theme_priority_bonus,
        }
    )

    result = run_kospi_backtest(
        BacktestConfig(
            initial_cash=args.initial_cash,
            max_positions=primary_profile.max_positions,
            max_holding_days=primary_profile.max_holding_days,
            lookback_days=args.lookback_days,
            markets=markets,
            rsi_min=primary_profile.rsi_min,
            rsi_max=primary_profile.rsi_max,
            volume_ratio_min=primary_profile.volume_ratio_min,
            stop_loss_pct=primary_profile.stop_loss_pct,
            take_profit_pct=primary_profile.take_profit_pct,
            market_profiles=market_profiles,
            candidate_selection_enabled=args.candidate_selection_enabled,
            candidate_selection=candidate_selection,
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
