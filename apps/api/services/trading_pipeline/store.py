from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from config.settings import CACHE_DIR
from services.json_utils import json_dump_text, json_load_bytes, read_json_file_cached

PIPELINE_DIR = CACHE_DIR / "trading_pipeline"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def latest_path(kind: str, market: str) -> Path:
    return PIPELINE_DIR / kind / f"{market.lower()}__latest.json"


def events_path(kind: str, market: str) -> Path:
    return PIPELINE_DIR / "events" / f"{market.lower()}__{kind}.jsonl"


def write_latest(kind: str, market: str, payload: Mapping[str, Any]) -> Path:
    path = latest_path(kind, market)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dump_text(dict(payload)), encoding="utf-8")
    return path


def read_latest(kind: str, market: str) -> dict[str, Any]:
    path = latest_path(kind, market)
    if not path.exists():
        return {}
    data = read_json_file_cached(path)
    if not isinstance(data, dict):
        raise ValueError(f"pipeline snapshot is not an object: {path}")
    return data


def append_event(kind: str, market: str, payload: Mapping[str, Any]) -> Path:
    path = events_path(kind, market)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json_dump_text({"recorded_at": utc_now_iso(), **dict(payload)})
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{line}\n")
    return path


def read_events(kind: str, market: str, *, limit: int = 50) -> list[dict[str, Any]]:
    path = events_path(kind, market)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        if not line.strip():
            continue
        item = json_load_bytes(line.encode("utf-8"))
        if isinstance(item, dict):
            rows.append(item)
    return rows
