"""SQLite audit store for Agent-driven trading runs.

This store is intentionally small and stdlib-only. It gives the Agent Run
pipeline durable, queryable records without changing the existing file/jsonl
runtime stores yet.
"""

from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from pathlib import Path
from typing import Any

from config.settings import AUDIT_DIR
from market_utils import lookup_company_listing

DEFAULT_AGENT_DB_PATH = AUDIT_DIR / "agent_trading.db"


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, separators=(",", ":"))


def _json_loads(value: Any) -> Any:
    if value in (None, ""):
        return {}
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return {}


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    for key in ("payload", "summary"):
        if key in payload:
            payload[key] = _json_loads(payload[key])
    schema_valid = payload.get("schema_valid")
    if schema_valid is not None:
        payload["schema_valid"] = bool(schema_valid)
    approved = payload.get("approved")
    if approved is not None:
        payload["approved"] = bool(approved)
    return payload


def _with_symbol_identity(row: dict[str, Any]) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "").strip().upper()
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    market = str(row.get("market") or payload.get("market") or "").strip().upper()
    name = str(row.get("name") or payload.get("name") or "").strip()
    if symbol and (not name or name.upper() == symbol):
        try:
            listing = lookup_company_listing(code=symbol, market=market, scope="core") or {}
            name = str(listing.get("name") or name).strip()
            market = market or str(listing.get("market") or "").strip().upper()
        except Exception:
            pass
    row["symbol"] = symbol or row.get("symbol")
    row["name"] = name
    row["market"] = market
    return row


class AgentAuditStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_AGENT_DB_PATH)

    def _schema_ready(self) -> bool:
        if not self.db_path.exists():
            return True
        try:
            with self._connect() as conn:
                run_columns = {row["name"] for row in conn.execute("PRAGMA table_info(agent_runs)").fetchall()}
                order_columns = {row["name"] for row in conn.execute("PRAGMA table_info(trade_orders)").fetchall()}
        except sqlite3.DatabaseError:
            return False
        if not run_columns and not order_columns:
            return True
        return "execution_channel" in run_columns and "execution_channel" in order_columns

    def _reset_incompatible_db(self) -> None:
        for path in (self.db_path, self.db_path.with_name(f"{self.db_path.name}-wal"), self.db_path.with_name(f"{self.db_path.name}-shm")):
            try:
                path.unlink()
            except FileNotFoundError:
                continue

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        if self.db_path.exists() and not self._schema_ready():
            self._reset_incompatible_db()
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trigger TEXT NOT NULL DEFAULT 'manual',
                    execution_channel TEXT NOT NULL DEFAULT 'runtime',
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS trade_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    market TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES agent_runs(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS market_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    candidate_id INTEGER,
                    symbol TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
                    FOREIGN KEY(candidate_id) REFERENCES trade_candidates(id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS trade_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    candidate_id INTEGER,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0,
                    payload TEXT NOT NULL DEFAULT '{}',
                    raw_response TEXT NOT NULL DEFAULT '',
                    schema_valid INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
                    FOREIGN KEY(candidate_id) REFERENCES trade_candidates(id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS risk_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    decision_id INTEGER,
                    symbol TEXT NOT NULL,
                    approved INTEGER NOT NULL DEFAULT 0,
                    reason_code TEXT NOT NULL DEFAULT '',
                    payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
                    FOREIGN KEY(decision_id) REFERENCES trade_decisions(id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS trade_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    decision_id INTEGER,
                    risk_event_id INTEGER,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    execution_channel TEXT NOT NULL DEFAULT 'runtime',
                    status TEXT NOT NULL DEFAULT 'skipped',
                    payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
                    FOREIGN KEY(decision_id) REFERENCES trade_decisions(id) ON DELETE SET NULL,
                    FOREIGN KEY(risk_event_id) REFERENCES risk_events(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_agent_runs_started_at ON agent_runs(started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_trade_decisions_symbol ON trade_decisions(symbol, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_trade_orders_symbol ON trade_orders(symbol, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_trade_orders_execution_channel ON trade_orders(execution_channel, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_market_evidence_symbol ON market_evidence(symbol, created_at DESC);
                """
            )

    def create_run(self, *, trigger: str, execution_channel: str, status: str = "running", summary: dict[str, Any] | None = None) -> int:
        self.initialize()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO agent_runs(trigger, execution_channel, status, started_at, summary) VALUES (?, ?, ?, ?, ?)",
                (trigger, execution_channel, status, _now_iso(), _json_dumps(summary)),
            )
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, *, status: str, summary: dict[str, Any] | None = None) -> None:
        self.initialize()
        with self._connect() as conn:
            conn.execute(
                "UPDATE agent_runs SET status=?, finished_at=?, summary=? WHERE id=?",
                (status, _now_iso(), _json_dumps(summary), int(run_id)),
            )

    def add_candidate(self, run_id: int, *, symbol: str, market: str = "", name: str = "", source: str = "", payload: dict[str, Any] | None = None) -> int:
        self.initialize()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO trade_candidates(run_id, symbol, market, name, source, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (int(run_id), symbol, market, name, source, _json_dumps(payload), _now_iso()),
            )
            return int(cur.lastrowid)

    def add_evidence(self, run_id: int, *, candidate_id: int | None, symbol: str, evidence_type: str, payload: dict[str, Any] | None = None) -> int:
        self.initialize()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO market_evidence(run_id, candidate_id, symbol, evidence_type, payload, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (int(run_id), candidate_id, symbol, evidence_type, _json_dumps(payload), _now_iso()),
            )
            return int(cur.lastrowid)

    def add_decision(self, run_id: int, *, candidate_id: int | None, symbol: str, action: str, confidence: float, payload: dict[str, Any] | None = None, raw_response: str = "", schema_valid: bool = False) -> int:
        self.initialize()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO trade_decisions(run_id, candidate_id, symbol, action, confidence, payload, raw_response, schema_valid, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (int(run_id), candidate_id, symbol, action, float(confidence or 0.0), _json_dumps(payload), raw_response, 1 if schema_valid else 0, _now_iso()),
            )
            return int(cur.lastrowid)

    def add_risk_event(self, run_id: int, *, decision_id: int | None, symbol: str, approved: bool, reason_code: str, payload: dict[str, Any] | None = None) -> int:
        self.initialize()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO risk_events(run_id, decision_id, symbol, approved, reason_code, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (int(run_id), decision_id, symbol, 1 if approved else 0, reason_code, _json_dumps(payload), _now_iso()),
            )
            return int(cur.lastrowid)

    def add_order(self, run_id: int, *, decision_id: int | None, risk_event_id: int | None, symbol: str, action: str, execution_channel: str, status: str, payload: dict[str, Any] | None = None) -> int:
        self.initialize()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO trade_orders(run_id, decision_id, risk_event_id, symbol, action, execution_channel, status, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (int(run_id), decision_id, risk_event_id, symbol, action, execution_channel, status, _json_dumps(payload), _now_iso()),
            )
            return int(cur.lastrowid)

    def _list(self, table: str, *, limit: int = 50, where: str = "", params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        self.initialize()
        safe_limit = max(1, min(int(limit or 50), 500))
        sql = f"SELECT * FROM {table} {where} ORDER BY id DESC LIMIT ?"
        with self._connect() as conn:
            return [_row_to_dict(row) for row in conn.execute(sql, (*params, safe_limit)).fetchall()]

    def list_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return self._list("agent_runs", limit=limit)

    def list_decisions(self, *, limit: int = 50) -> list[dict[str, Any]]:
        self.initialize()
        safe_limit = max(1, min(int(limit or 50), 500))
        sql = """
            SELECT
                d.*,
                c.name AS name,
                c.market AS market,
                c.source AS candidate_source
            FROM trade_decisions d
            LEFT JOIN trade_candidates c ON c.id = d.candidate_id
            ORDER BY d.id DESC
            LIMIT ?
        """
        with self._connect() as conn:
            return [_with_symbol_identity(_row_to_dict(row)) for row in conn.execute(sql, (safe_limit,)).fetchall()]

    def list_orders(self, *, limit: int = 50) -> list[dict[str, Any]]:
        self.initialize()
        safe_limit = max(1, min(int(limit or 50), 500))
        sql = """
            SELECT
                o.*,
                c.name AS name,
                c.market AS market,
                c.source AS candidate_source
            FROM trade_orders o
            LEFT JOIN trade_candidates c ON c.id = (
                SELECT d.candidate_id FROM trade_decisions d WHERE d.id = o.decision_id
            )
            ORDER BY o.id DESC
            LIMIT ?
        """
        with self._connect() as conn:
            return [_with_symbol_identity(_row_to_dict(row)) for row in conn.execute(sql, (safe_limit,)).fetchall()]

    def list_evidence(self, *, symbol: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if symbol:
            return self._list("market_evidence", limit=limit, where="WHERE symbol = ?", params=(symbol,))
        return self._list("market_evidence", limit=limit)

    def get_run_detail(self, run_id: int) -> dict[str, Any]:
        self.initialize()
        with self._connect() as conn:
            run = conn.execute("SELECT * FROM agent_runs WHERE id=?", (int(run_id),)).fetchone()
            if run is None:
                return {"run": None, "candidates": [], "evidence": [], "decisions": [], "risk_events": [], "orders": []}
            result: dict[str, Any] = {"run": _row_to_dict(run)}
            for key, table in (
                ("candidates", "trade_candidates"),
                ("evidence", "market_evidence"),
                ("decisions", "trade_decisions"),
                ("risk_events", "risk_events"),
                ("orders", "trade_orders"),
            ):
                rows = conn.execute(f"SELECT * FROM {table} WHERE run_id=? ORDER BY id ASC", (int(run_id),)).fetchall()
                result[key] = [_row_to_dict(row) for row in rows]
            return result


def default_store() -> AgentAuditStore:
    return AgentAuditStore()
