from __future__ import annotations

import json
from typing import Any

from config.settings import RUNTIME_DIR
from helpers import _now_iso

ACCOUNT_STATE_DIR = RUNTIME_DIR / "accounts"
LIVE_ACCOUNT_STATE_PATH = ACCOUNT_STATE_DIR / "live_account_state.json"
LIVE_POSITION_ENTRY_PATH = ACCOUNT_STATE_DIR / "live_position_entries.json"


def account_positions_updated_at(account: dict[str, Any]) -> str:
    positions = account.get("positions") if isinstance(account.get("positions"), list) else []
    timestamps = [
        str(item.get("updated_at") or "").strip()
        for item in positions
        if isinstance(item, dict) and str(item.get("updated_at") or "").strip()
    ]
    return max(timestamps) if timestamps else _now_iso()


def read_cached_live_runtime_account() -> dict[str, Any]:
    try:
        payload = json.loads(LIVE_ACCOUNT_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    if str(payload.get("mode") or "").strip().lower() == "real" and "ok" not in payload:
        payload["ok"] = True
    if not str(payload.get("updated_at") or "").strip():
        payload["updated_at"] = account_positions_updated_at(payload)
    return payload


def persist_live_runtime_account(account: dict[str, Any]) -> None:
    if not isinstance(account, dict):
        return
    if str(account.get("mode") or "").strip().lower() != "real":
        return
    if account.get("ok") is False or account.get("error"):
        return
    payload = dict(account)
    payload["ok"] = True
    if not str(payload.get("updated_at") or "").strip():
        payload["updated_at"] = account_positions_updated_at(payload)
    LIVE_ACCOUNT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIVE_ACCOUNT_STATE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
