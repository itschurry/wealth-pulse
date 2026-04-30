from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from config.settings import CACHE_DIR, RUNTIME_DIR
from services.json_utils import json_dump_compact, json_dump_text, read_json_file_cached


ENGINE_STATE_PATH = RUNTIME_DIR / "engine_state.json"
ENGINE_CYCLES_DIR = RUNTIME_DIR / "engine_cycles"
EVENTS_DIR = RUNTIME_DIR / "events"
ORDER_EVENTS_PATH = EVENTS_DIR / "order_events.jsonl"
EXECUTION_EVENTS_PATH = EVENTS_DIR / "execution_events.jsonl"
SIGNAL_SNAPSHOTS_PATH = EVENTS_DIR / "signal_snapshots.jsonl"
ACCOUNT_SNAPSHOTS_PATH = EVENTS_DIR / "account_snapshots.jsonl"
RUNTIME_EVENTS_PATH = EVENTS_DIR / "runtime_events.jsonl"
UNIVERSE_SNAPSHOTS_DIR = CACHE_DIR / "universe_snapshots"
STRATEGY_SCANS_DIR = CACHE_DIR / "strategy_scans"

# 서버 시작 시 execution event stream이 없으면 빈 파일로 초기화한다.
EXECUTION_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
if not EXECUTION_EVENTS_PATH.exists():
    EXECUTION_EVENTS_PATH.touch()


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def _json_serialize(value: Any) -> str:
    return json_dump_compact(value)


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_lines(path: Path) -> list[str]:
    try:
        return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return []


def _clear_file(path: Path) -> int:
    _ensure_parent(path)
    removed = len(_read_lines(path))
    path.write_text("", encoding="utf-8")
    return removed


def _clear_jsonl_files(directory: Path) -> int:
    if not directory.exists():
        return 0
    total = 0
    for path in directory.glob("*.jsonl"):
        total += _clear_file(path)
    return total


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = read_json_file_cached(path)
    except (OSError, json.JSONDecodeError):
        return dict(default)
    except Exception:
        return dict(default)
    return payload if isinstance(payload, dict) else dict(default)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _ensure_parent(path)
    path.write_text(json_dump_text(payload, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    _ensure_parent(path)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(f"{_json_serialize(payload)}\n")


def _read_latest_jsonl(path: Path, limit: int | None) -> list[dict[str, Any]]:
    capped = None if limit is None else max(1, int(limit or 50))
    rows: list[dict[str, Any]] = []
    for line in reversed(_read_lines(path)):
        if capped is not None and len(rows) >= capped:
            break
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _cycle_log_path(timestamp: str) -> Path:
    date_key = datetime.date.today().isoformat()
    try:
        date_key = datetime.datetime.fromisoformat(timestamp).date().isoformat()
    except Exception:
        pass
    return ENGINE_CYCLES_DIR / f"{date_key}.jsonl"


def load_engine_state(default: dict[str, Any] | None = None) -> dict[str, Any]:
    return _read_json(ENGINE_STATE_PATH, default or {})


def save_engine_state(payload: dict[str, Any]) -> None:
    _write_json(ENGINE_STATE_PATH, payload)


def append_engine_cycle(payload: dict[str, Any]) -> None:
    record = {"logged_at": _now_iso(), **payload}
    _append_jsonl(_cycle_log_path(str(payload.get("finished_at") or payload.get("started_at") or _now_iso())), record)


def read_engine_cycles(limit: int = 50) -> list[dict[str, Any]]:
    capped = max(1, min(500, int(limit or 50)))
    ENGINE_CYCLES_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(ENGINE_CYCLES_DIR.glob("*.jsonl"), reverse=True)
    rows: list[dict[str, Any]] = []
    for path in files:
        for line in reversed(_read_lines(path)):
            if len(rows) >= capped:
                return rows
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def clear_engine_cycles() -> int:
    return _clear_jsonl_files(ENGINE_CYCLES_DIR)


def clear_order_events() -> int:
    return _clear_file(ORDER_EVENTS_PATH)


def clear_execution_events() -> int:
    return _clear_file(EXECUTION_EVENTS_PATH)


def clear_signal_snapshots() -> int:
    return _clear_file(SIGNAL_SNAPSHOTS_PATH)


def clear_account_snapshots() -> int:
    return _clear_file(ACCOUNT_SNAPSHOTS_PATH)


def append_order_event(payload: dict[str, Any]) -> None:
    record = {"logged_at": _now_iso(), **payload}
    _append_jsonl(ORDER_EVENTS_PATH, record)


def read_order_events(limit: int | None = 100) -> list[dict[str, Any]]:
    return _read_latest_jsonl(ORDER_EVENTS_PATH, limit)


def append_execution_event(payload: dict[str, Any]) -> None:
    record = {"logged_at": _now_iso(), **payload}
    _append_jsonl(EXECUTION_EVENTS_PATH, record)


def append_execution_events(payloads: list[dict[str, Any]]) -> None:
    if not payloads:
        return
    _ensure_parent(EXECUTION_EVENTS_PATH)
    with EXECUTION_EVENTS_PATH.open("a", encoding="utf-8") as fp:
        logged_at = _now_iso()
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            fp.write(f"{_json_serialize({'logged_at': logged_at, **payload})}\n")


def read_execution_events(limit: int = 200) -> list[dict[str, Any]]:
    return _read_latest_jsonl(EXECUTION_EVENTS_PATH, limit)


def append_signal_snapshot(payload: dict[str, Any]) -> None:
    record = {"logged_at": _now_iso(), **payload}
    _append_jsonl(SIGNAL_SNAPSHOTS_PATH, record)


def append_signal_snapshots(payloads: list[dict[str, Any]]) -> None:
    if not payloads:
        return
    _ensure_parent(SIGNAL_SNAPSHOTS_PATH)
    with SIGNAL_SNAPSHOTS_PATH.open("a", encoding="utf-8") as fp:
        logged_at = _now_iso()
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            fp.write(f"{_json_serialize({'logged_at': logged_at, **payload})}\n")


def read_signal_snapshots(limit: int = 200) -> list[dict[str, Any]]:
    return _read_latest_jsonl(SIGNAL_SNAPSHOTS_PATH, limit)


def append_account_snapshot(payload: dict[str, Any]) -> None:
    record = {"logged_at": _now_iso(), **payload}
    _append_jsonl(ACCOUNT_SNAPSHOTS_PATH, record)


def read_account_snapshots(limit: int = 100) -> list[dict[str, Any]]:
    return _read_latest_jsonl(ACCOUNT_SNAPSHOTS_PATH, limit)


def _safe_key(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in str(value or "").strip()) or "default"


def save_universe_snapshot(rule_name: str, payload: dict[str, Any]) -> None:
    path = UNIVERSE_SNAPSHOTS_DIR / f"{_safe_key(rule_name)}.json"
    _write_json(path, payload)


def load_universe_snapshot(rule_name: str) -> dict[str, Any]:
    path = UNIVERSE_SNAPSHOTS_DIR / f"{_safe_key(rule_name)}.json"
    return _read_json(path, {})


def list_universe_snapshots() -> list[dict[str, Any]]:
    UNIVERSE_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for path in sorted(UNIVERSE_SNAPSHOTS_DIR.glob("*.json")):
        item = _read_json(path, {})
        if item:
            rows.append(item)
    rows.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return rows


def save_strategy_scan(strategy_id: str, payload: dict[str, Any]) -> None:
    path = STRATEGY_SCANS_DIR / f"{_safe_key(strategy_id)}.json"
    _write_json(path, payload)


def load_strategy_scan(strategy_id: str) -> dict[str, Any]:
    path = STRATEGY_SCANS_DIR / f"{_safe_key(strategy_id)}.json"
    return _read_json(path, {})


def list_strategy_scans() -> list[dict[str, Any]]:
    STRATEGY_SCANS_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for path in sorted(STRATEGY_SCANS_DIR.glob("*.json")):
        item = _read_json(path, {})
        if item:
            rows.append(item)
    rows.sort(key=lambda item: str(item.get("last_scan_at") or item.get("scanned_at") or ""), reverse=True)
    return rows


def append_runtime_event(payload: dict[str, Any]) -> None:
    record = {"logged_at": _now_iso(), **payload}
    _append_jsonl(RUNTIME_EVENTS_PATH, record)


def read_runtime_events(limit: int = 200) -> list[dict[str, Any]]:
    return _read_latest_jsonl(RUNTIME_EVENTS_PATH, limit)
