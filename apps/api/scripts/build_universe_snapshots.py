#!/usr/bin/env python3
"""Universe snapshot builder for KOSPI/SP500.

Usage:
  python3 apps/api/scripts/build_universe_snapshots.py
  python3 apps/api/scripts/build_universe_snapshots.py --universe kospi
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


_KST = datetime.timezone(datetime.timedelta(hours=9))
_SCRIPT_PATH = Path(__file__).resolve()
_API_ROOT = _SCRIPT_PATH.parents[1]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from config.settings import LOGS_DIR


UNIVERSE_TARGETS = {
    "kospi": {
        "listing_key": "KOSPI",
        "market": "KOSPI",
    },
    "sp500": {
        "listing_key": "S&P500",
        "market": "US",
    },
}

_UNIVERSE_ROOT = LOGS_DIR / "universe_snapshots"


def _market_date() -> str:
    return datetime.datetime.now(_KST).date().isoformat()


def _now_iso() -> str:
    return datetime.datetime.now(_KST).isoformat(timespec="seconds")


def _normalize_symbol(value: str) -> str:
    return str(value or "").strip().upper()


def _load_listing_rows(listing_key: str) -> list[dict[str, Any]]:
    try:
        import FinanceDataReader  # type: ignore[import-not-found]
    except Exception as exc:
        raise RuntimeError(
            "FinanceDataReader is required. Install it with `pip install finance-datareader`."
        ) from exc

    frame = FinanceDataReader.StockListing(listing_key)
    if frame is None:
        return []

    symbols = []
    to_dict = getattr(frame, "to_dict", None)
    if callable(to_dict):
        try:
            rows = to_dict("records")
            if isinstance(rows, list):
                symbols = [row for row in rows if isinstance(row, dict)]
        except Exception:
            symbols = []

    if symbols:
        return symbols

    records: list[dict[str, Any]] = []
    iterator = frame.iterrows() if hasattr(frame, "iterrows") else []
    for _, row in iterator:
        if not hasattr(row, "to_dict"):
            continue
        record = row.to_dict()
        if isinstance(record, dict):
            records.append(record)
    return records


def _extract_symbol(row: dict[str, Any]) -> tuple[str, str]:
    symbol_key_candidates = ("Symbol", "Code", "Ticker", "stock_code", "StockCode")
    name_key_candidates = ("Name", "name", "CompanyName", "company_name", "종목명")
    raw_symbol = ""
    for key in symbol_key_candidates:
        raw_symbol = str(row.get(key) or "").strip()
        if raw_symbol:
            break
    raw_name = ""
    for key in name_key_candidates:
        raw_name = str(row.get(key) or "").strip()
        if raw_name:
            break
    return _normalize_symbol(raw_symbol), raw_name


def _build_payload(rule: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    target = UNIVERSE_TARGETS[rule]
    entries: list[dict[str, Any]] = []
    seen = set[str]()
    for row in rows:
        symbol, name = _extract_symbol(row)
        if not symbol:
            continue
        if symbol in seen:
            continue
        seen.add(symbol)
        entries.append({
            "code": symbol,
            "name": str(name or symbol).strip() or symbol,
            "market": target["market"],
            "sector": row.get("Sector") or None,
            "source": "FinanceDataReader",
        })

    entries.sort(key=lambda item: str(item.get("code") or ""))
    return {
        "schema_version": 1,
        "rule_name": rule,
        "as_of_date": _market_date(),
        "generated_at": _now_iso(),
        "updated_at": _now_iso(),
        "source": "FinanceDataReader",
        "universe": rule,
        "market": target["market"],
        "symbol_count": len(entries),
        "excluded_count": 0,
        "symbols": entries,
        "excluded": [],
        "meta": {
            "listing_key": target["listing_key"],
        },
    }


def _build_summary_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": payload.get("schema_version", 1),
        "rule_name": payload.get("rule_name") or payload.get("universe") or "",
        "universe": payload.get("universe") or payload.get("rule_name") or "",
        "market": payload.get("market") or "",
        "as_of_date": payload.get("as_of_date") or "",
        "generated_at": payload.get("generated_at") or "",
        "updated_at": payload.get("updated_at") or payload.get("generated_at") or "",
        "created_at": payload.get("created_at") or "",
        "source": payload.get("source") or "",
        "symbol_count": int(payload.get("symbol_count") or len(payload.get("symbols") or [])),
        "excluded_count": int(payload.get("excluded_count") or len(payload.get("excluded") or [])),
        "meta": payload.get("meta") if isinstance(payload.get("meta"), dict) else {},
        "symbols": [],
        "excluded": [],
    }


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as tmp:
        tmp.write(json.dumps(payload, ensure_ascii=False, indent=2))
        tmp.flush()
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _snapshot_paths(rule: str, as_of_date: str) -> tuple[Path, Path, Path]:
    directory = _UNIVERSE_ROOT / rule
    return directory / "latest.json", directory / "latest.summary.json", directory / f"{as_of_date}.json"


def build_snapshot(rule: str, *, dry_run: bool = False) -> tuple[dict[str, Any], dict[str, Any] | None]:
    target = UNIVERSE_TARGETS[rule]
    rows = _load_listing_rows(target["listing_key"])
    payload = _build_payload(rule, rows)
    previous = None
    previous_payload: dict[str, Any] | None = None
    latest_path, summary_path, archive_path = _snapshot_paths(rule, payload["as_of_date"])
    if latest_path.exists():
        try:
            loaded = json.loads(latest_path.read_text(encoding="utf-8"))
            previous_payload = loaded if isinstance(loaded, dict) else None
            previous = previous_payload if isinstance(previous_payload, dict) else None
            if isinstance(previous, dict):
                previous = {
                    "count": int(previous.get("count", 0)),
                    "generated_at": str(previous.get("generated_at") or ""),
                }
        except (OSError, json.JSONDecodeError):
            previous = None
            previous_payload = None

    if not payload["symbols"]:
        if dry_run:
            raise RuntimeError(
                f"[{rule}] No symbols were produced from {target['listing_key']} ; keeping existing latest snapshot."
            )
        if previous_payload is not None:
            return previous_payload, previous
        raise RuntimeError(
            f"[{rule}] No symbols were produced from {target['listing_key']} and no previous snapshot exists."
        )

    if dry_run:
        return payload, previous

    _write_payload(archive_path, payload)
    _write_payload(latest_path, payload)
    _write_payload(summary_path, _build_summary_payload(payload))
    return payload, previous


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build universe snapshots for backtest/live runtimes.")
    parser.add_argument(
        "--universe",
        choices=["all", "kospi", "sp500"],
        default="all",
        help="Build snapshot for a specific universe rule.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build payload and print diff summary without writing files.")
    args = parser.parse_args(argv)

    targets = list(UNIVERSE_TARGETS.keys()) if args.universe == "all" else [args.universe]
    for rule in targets:
        try:
            payload, previous = build_snapshot(rule, dry_run=args.dry_run)
            prev_count = int(previous.get("count", 0)) if isinstance(previous, dict) else 0
            print(
                f"[{rule}] symbols={payload['symbol_count']} generated_at={payload['generated_at']} "
                f"previous={bool(previous)} prev_count={prev_count} delta={payload['symbol_count'] - prev_count}"
            )
        except Exception as exc:
            print(f"[{rule}] failed: {exc}")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
