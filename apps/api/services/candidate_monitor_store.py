from __future__ import annotations

import datetime
import json
import sqlite3
from pathlib import Path
from typing import Any

from config.settings import RUNTIME_DIR

DB_PATH = RUNTIME_DIR / "candidate_monitor.db"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS market_state (
            market TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            source TEXT NOT NULL,
            session_date TEXT NOT NULL,
            core_limit INTEGER NOT NULL,
            promotion_limit INTEGER NOT NULL,
            candidate_pool_count INTEGER NOT NULL,
            active_count INTEGER NOT NULL,
            held_count INTEGER NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS candidate_pool (
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            strategy_id TEXT,
            strategy_name TEXT,
            candidate_rank INTEGER,
            final_action TEXT,
            signal_state TEXT,
            entry_allowed INTEGER NOT NULL DEFAULT 0,
            score REAL,
            confidence REAL,
            last_scanned_at TEXT,
            research_status TEXT,
            snapshot_fresh INTEGER NOT NULL DEFAULT 0,
            snapshot_generated_at TEXT,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (market, symbol)
        );
        CREATE INDEX IF NOT EXISTS idx_candidate_pool_market_rank ON candidate_pool(market, candidate_rank, score DESC);

        CREATE TABLE IF NOT EXISTS active_slots (
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            slot_type TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0,
            reason TEXT NOT NULL,
            strategy_id TEXT,
            payload_json TEXT NOT NULL,
            selected_at TEXT NOT NULL,
            PRIMARY KEY (market, symbol)
        );
        CREATE INDEX IF NOT EXISTS idx_active_slots_market_type_priority ON active_slots(market, slot_type, priority DESC);

        CREATE TABLE IF NOT EXISTS promotion_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            event_type TEXT NOT NULL,
            reason TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_promotion_events_market_created ON promotion_events(market, created_at DESC);
        """
    )
    conn.commit()


def _normalize_market(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _json_blob(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _from_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    for key in ("payload_json", "metadata_json"):
        if key in payload:
            try:
                decoded = json.loads(payload[key]) if payload[key] else {}
            except Exception:
                decoded = {}
            mapped_key = key[:-5] if key.endswith('_json') else key
            payload[mapped_key] = decoded
            if mapped_key == "payload" and isinstance(decoded, dict):
                for inner_key, inner_value in decoded.items():
                    payload.setdefault(inner_key, inner_value)
            payload.pop(key, None)
    if "entry_allowed" in payload:
        payload["entry_allowed"] = bool(payload.get("entry_allowed"))
    if "snapshot_fresh" in payload:
        payload["snapshot_fresh"] = bool(payload.get("snapshot_fresh"))
    if payload.get("candidate_rank") is not None:
        try:
            rank = int(payload.get("candidate_rank"))
            payload["candidate_rank"] = None if rank >= 999999 else rank
        except (TypeError, ValueError):
            payload["candidate_rank"] = None
    return payload


def replace_candidate_pool(market: str, rows: list[dict[str, Any]], *, updated_at: str | None = None) -> int:
    normalized_market = _normalize_market(market)
    timestamp = updated_at or _now_iso()
    with _connect() as conn:
        conn.execute("DELETE FROM candidate_pool WHERE market=?", (normalized_market,))
        inserted = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = _normalize_symbol(row.get("code") or row.get("symbol"))
            if not symbol:
                continue
            conn.execute(
                """
                INSERT INTO candidate_pool (
                    market, symbol, strategy_id, strategy_name, candidate_rank, final_action,
                    signal_state, entry_allowed, score, confidence, last_scanned_at,
                    research_status, snapshot_fresh, snapshot_generated_at, payload_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_market,
                    symbol,
                    str(row.get("strategy_id") or ""),
                    str(row.get("strategy_name") or ""),
                    row.get("candidate_rank"),
                    str(row.get("final_action") or ""),
                    str(row.get("signal_state") or ""),
                    1 if bool(row.get("entry_allowed")) else 0,
                    row.get("score"),
                    row.get("confidence"),
                    str(row.get("last_scanned_at") or row.get("fetched_at") or ""),
                    str(row.get("research_status") or ""),
                    1 if bool(row.get("snapshot_fresh")) else 0,
                    str(row.get("snapshot_generated_at") or row.get("generated_at") or ""),
                    _json_blob(row),
                    timestamp,
                ),
            )
            inserted += 1
        conn.commit()
    return inserted


def list_candidate_pool(market: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    normalized_market = _normalize_market(market)
    query = "SELECT * FROM candidate_pool WHERE market=? ORDER BY COALESCE(candidate_rank, 999999) ASC, COALESCE(score, 0) DESC, symbol ASC"
    params: list[Any] = [normalized_market]
    if limit is not None and int(limit) > 0:
        query += " LIMIT ?"
        params.append(int(limit))
    with _connect() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [_from_row(row) for row in rows if _from_row(row) is not None]


def replace_active_slots(market: str, rows: list[dict[str, Any]], *, selected_at: str | None = None) -> int:
    normalized_market = _normalize_market(market)
    timestamp = selected_at or _now_iso()
    with _connect() as conn:
        conn.execute("DELETE FROM active_slots WHERE market=?", (normalized_market,))
        inserted = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = _normalize_symbol(row.get("code") or row.get("symbol"))
            slot_type = str(row.get("slot_type") or "").strip().lower()
            if not symbol or not slot_type:
                continue
            conn.execute(
                """
                INSERT INTO active_slots (market, symbol, slot_type, priority, reason, strategy_id, payload_json, selected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_market,
                    symbol,
                    slot_type,
                    int(row.get("priority") or 0),
                    str(row.get("reason") or slot_type),
                    str(row.get("strategy_id") or ""),
                    _json_blob(row),
                    timestamp,
                ),
            )
            inserted += 1
        conn.commit()
    return inserted


def list_active_slots(market: str, *, slot_type: str | None = None) -> list[dict[str, Any]]:
    normalized_market = _normalize_market(market)
    query = "SELECT * FROM active_slots WHERE market=?"
    params: list[Any] = [normalized_market]
    if slot_type:
        query += " AND slot_type=?"
        params.append(str(slot_type).strip().lower())
    query += " ORDER BY priority DESC, symbol ASC"
    with _connect() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [_from_row(row) for row in rows if _from_row(row) is not None]


def save_market_state(
    market: str,
    *,
    source: str,
    session_date: str,
    core_limit: int,
    promotion_limit: int,
    candidate_pool_count: int,
    active_count: int,
    held_count: int,
    generated_at: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    normalized_market = _normalize_market(market)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO market_state (
                market, generated_at, source, session_date, core_limit, promotion_limit,
                candidate_pool_count, active_count, held_count, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market) DO UPDATE SET
                generated_at=excluded.generated_at,
                source=excluded.source,
                session_date=excluded.session_date,
                core_limit=excluded.core_limit,
                promotion_limit=excluded.promotion_limit,
                candidate_pool_count=excluded.candidate_pool_count,
                active_count=excluded.active_count,
                held_count=excluded.held_count,
                metadata_json=excluded.metadata_json
            """,
            (
                normalized_market,
                generated_at or _now_iso(),
                str(source or "candidate_monitor"),
                str(session_date or ""),
                int(core_limit),
                int(promotion_limit),
                int(candidate_pool_count),
                int(active_count),
                int(held_count),
                _json_blob(metadata or {}),
            ),
        )
        conn.commit()


def load_market_state(market: str) -> dict[str, Any] | None:
    normalized_market = _normalize_market(market)
    with _connect() as conn:
        row = conn.execute("SELECT * FROM market_state WHERE market=?", (normalized_market,)).fetchone()
    return _from_row(row)


def append_promotion_event(market: str, symbol: str, event_type: str, reason: str, payload: dict[str, Any] | None = None, *, created_at: str | None = None) -> None:
    normalized_market = _normalize_market(market)
    normalized_symbol = _normalize_symbol(symbol)
    if not normalized_market or not normalized_symbol:
        return
    with _connect() as conn:
        conn.execute(
            "INSERT INTO promotion_events (market, symbol, event_type, reason, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                normalized_market,
                normalized_symbol,
                str(event_type or "event"),
                str(reason or ""),
                _json_blob(payload or {}),
                created_at or _now_iso(),
            ),
        )
        conn.commit()


def list_promotion_events(market: str, *, limit: int = 50) -> list[dict[str, Any]]:
    normalized_market = _normalize_market(market)
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM promotion_events WHERE market=? ORDER BY created_at DESC, id DESC LIMIT ?",
            (normalized_market, max(1, int(limit or 50))),
        ).fetchall()
    return [_from_row(row) for row in rows if _from_row(row) is not None]
