from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routes.candidate_monitor import (  # noqa: E402
    handle_candidate_monitor_promotions,
    handle_candidate_monitor_status,
    handle_candidate_monitor_watchlist,
)
from routes.research import (  # noqa: E402
    handle_research_ingest_bulk,
    handle_research_latest_snapshot,
    handle_research_snapshots,
    handle_research_status,
)


def _print_payload(status_code: int, payload: dict) -> int:
    print(json.dumps({"status_code": status_code, **payload}, ensure_ascii=False, indent=2))
    return 0 if 200 <= status_code < 300 else 1


def _market_query(markets: list[str], *, limit: int | None = None, refresh: bool | None = None, mode: str | None = None) -> dict[str, list[str]]:
    query: dict[str, list[str]] = {}
    if markets:
        query["market"] = list(markets)
    if limit is not None:
        query["limit"] = [str(limit)]
    if refresh is not None:
        query["refresh"] = ["1" if refresh else "0"]
    if mode:
        query["mode"] = [mode]
    return query


def cmd_status(args: argparse.Namespace) -> int:
    return _print_payload(*handle_research_status({}))


def cmd_monitor_status(args: argparse.Namespace) -> int:
    return _print_payload(*handle_candidate_monitor_status(_market_query(args.market, refresh=args.refresh)))


def cmd_watchlist(args: argparse.Namespace) -> int:
    return _print_payload(*handle_candidate_monitor_watchlist(_market_query(args.market, limit=args.limit, refresh=args.refresh, mode=args.mode)))


def cmd_pending(args: argparse.Namespace) -> int:
    status_code, payload = handle_candidate_monitor_watchlist(_market_query(args.market, limit=args.limit, refresh=args.refresh, mode=args.mode))
    if status_code != 200:
        return _print_payload(status_code, payload)
    return _print_payload(status_code, {
        "ok": payload.get("ok", True),
        "markets": payload.get("markets") or list(args.market),
        "mode": args.mode,
        "count": payload.get("pending_count") or 0,
        "items": payload.get("pending_items") or [],
        "source": payload.get("source") or "candidate_monitor_sqlite",
        "refresh": payload.get("refresh"),
    })


def cmd_promotions(args: argparse.Namespace) -> int:
    return _print_payload(*handle_candidate_monitor_promotions(_market_query(args.market, limit=args.limit, refresh=args.refresh)))


def cmd_latest(args: argparse.Namespace) -> int:
    query = {
        "symbol": [args.symbol],
        "market": [args.market],
    }
    return _print_payload(*handle_research_latest_snapshot(query))


def cmd_snapshots(args: argparse.Namespace) -> int:
    query = {
        "limit": [str(args.limit)],
        "descending": ["true" if args.descending else "false"],
    }
    if args.symbol:
        query["symbol"] = [args.symbol]
    if args.market:
        query["market"] = [args.market]
    if args.bucket_start:
        query["bucket_start"] = [args.bucket_start]
    if args.bucket_end:
        query["bucket_end"] = [args.bucket_end]
    return _print_payload(*handle_research_snapshots(query))


def _load_json_payload(input_path: str | None) -> dict:
    if input_path:
        return json.loads(Path(input_path).read_text(encoding="utf-8"))
    return json.load(sys.stdin)


def cmd_ingest_bulk(args: argparse.Namespace) -> int:
    payload = _load_json_payload(args.input)
    return _print_payload(*handle_research_ingest_bulk(payload))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Research ops helper for WealthPulse candidate-monitor research flows")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="Show research ingest/storage status")
    status.set_defaults(func=cmd_status)

    monitor_status = sub.add_parser("monitor-status", help="Show market-level candidate-monitor summary")
    monitor_status.add_argument("--market", action="append", default=[])
    monitor_status.add_argument("--refresh", action="store_true")
    monitor_status.set_defaults(func=cmd_monitor_status)

    watchlist = sub.add_parser("watchlist", help="Show candidate-monitor watchlists with pending research subset")
    watchlist.add_argument("--market", action="append", default=[])
    watchlist.add_argument("--limit", type=int, default=30)
    watchlist.add_argument("--refresh", action="store_true")
    watchlist.add_argument(
        "--mode",
        choices=["missing_or_stale", "missing_only", "stale_only"],
        default="missing_or_stale",
    )
    watchlist.set_defaults(func=cmd_watchlist)

    pending = sub.add_parser("pending", help="Show only pending monitor-slot research targets")
    pending.add_argument("--market", action="append", default=[])
    pending.add_argument("--limit", type=int, default=30)
    pending.add_argument("--refresh", action="store_true")
    pending.add_argument(
        "--mode",
        choices=["missing_or_stale", "missing_only", "stale_only"],
        default="missing_or_stale",
    )
    pending.set_defaults(func=cmd_pending)

    promotions = sub.add_parser("promotions", help="Show recent watchlist enter/leave events")
    promotions.add_argument("--market", action="append", default=[])
    promotions.add_argument("--limit", type=int, default=50)
    promotions.add_argument("--refresh", action="store_true")
    promotions.set_defaults(func=cmd_promotions)

    latest = sub.add_parser("latest", help="Show latest snapshot for one symbol")
    latest.add_argument("symbol")
    latest.add_argument("market")
    latest.set_defaults(func=cmd_latest)

    snapshots = sub.add_parser("snapshots", help="Show snapshot history or latest directory listing")
    snapshots.add_argument("--symbol")
    snapshots.add_argument("--market")
    snapshots.add_argument("--bucket-start")
    snapshots.add_argument("--bucket-end")
    snapshots.add_argument("--limit", type=int, default=50)
    snapshots.add_argument("--descending", action="store_true")
    snapshots.set_defaults(func=cmd_snapshots)

    ingest = sub.add_parser("ingest-bulk", help="Ingest bulk research snapshots from file or stdin")
    ingest.add_argument("--input", help="JSON file path. If omitted, read stdin")
    ingest.set_defaults(func=cmd_ingest_bulk)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
