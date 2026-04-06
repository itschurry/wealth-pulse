from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routes.research import (  # noqa: E402
    handle_research_ingest_bulk,
    handle_research_latest_snapshot,
    handle_research_scanner_enrich_targets,
    handle_research_scanner_targets,
    handle_research_snapshots,
    handle_research_status,
)


def _print_payload(status_code: int, payload: dict) -> int:
    print(json.dumps({"status_code": status_code, **payload}, ensure_ascii=False, indent=2))
    return 0 if 200 <= status_code < 300 else 1


def cmd_status(args: argparse.Namespace) -> int:
    query = {"provider": [args.provider]}
    return _print_payload(*handle_research_status(query))


def cmd_scanner_targets(args: argparse.Namespace) -> int:
    query: dict[str, list[str]] = {
        "provider": [args.provider],
        "limit": [str(args.limit)],
    }
    if args.market:
        query["market"] = list(args.market)
    return _print_payload(*handle_research_scanner_targets(query))


def cmd_enrich_targets(args: argparse.Namespace) -> int:
    query: dict[str, list[str]] = {
        "provider": [args.provider],
        "limit": [str(args.limit)],
        "mode": [args.mode],
    }
    if args.market:
        query["market"] = list(args.market)
    return _print_payload(*handle_research_scanner_enrich_targets(query))


def cmd_latest(args: argparse.Namespace) -> int:
    query = {
        "provider": [args.provider],
        "symbol": [args.symbol],
        "market": [args.market],
    }
    return _print_payload(*handle_research_latest_snapshot(query))


def cmd_snapshots(args: argparse.Namespace) -> int:
    query = {
        "provider": [args.provider],
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
    parser = argparse.ArgumentParser(description="Research ops helper for WealthPulse Hanna/OpenClaw flows")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="Show provider status")
    status.add_argument("--provider", default="openclaw")
    status.set_defaults(func=cmd_status)

    scanner_targets = sub.add_parser("scanner-targets", help="List scanner-linked research targets")
    scanner_targets.add_argument("--provider", default="openclaw")
    scanner_targets.add_argument("--market", action="append", default=[])
    scanner_targets.add_argument("--limit", type=int, default=100)
    scanner_targets.set_defaults(func=cmd_scanner_targets)

    enrich_targets = sub.add_parser("enrich-targets", help="List missing/stale scanner research targets")
    enrich_targets.add_argument("--provider", default="openclaw")
    enrich_targets.add_argument("--market", action="append", default=[])
    enrich_targets.add_argument("--limit", type=int, default=30)
    enrich_targets.add_argument(
        "--mode",
        choices=["missing_or_stale", "missing_only", "stale_only"],
        default="missing_or_stale",
    )
    enrich_targets.set_defaults(func=cmd_enrich_targets)

    latest = sub.add_parser("latest", help="Show latest snapshot for one symbol")
    latest.add_argument("symbol")
    latest.add_argument("market")
    latest.add_argument("--provider", default="openclaw")
    latest.set_defaults(func=cmd_latest)

    snapshots = sub.add_parser("snapshots", help="Show snapshot history or latest directory listing")
    snapshots.add_argument("--provider", default="openclaw")
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
