"""SQLite 기반 리포트 저장소.

report/market_brief.db 파일 하나로 기존 report/*.json 파일들을 대체한다.
연결은 함수 호출마다 열고 닫아 라즈베리파이 메모리를 절약한다.
"""
import datetime
import json
import sqlite3
from typing import Any

from config.settings import REPORT_OUTPUT_DIR

_DB_PATH = REPORT_OUTPUT_DIR / "market_brief.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            date       TEXT NOT NULL,
            key        TEXT NOT NULL,
            data       TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(date, key)
        )
    """)
    conn.commit()
    return conn


def save_report(date: str, key: str, data: Any) -> None:
    """data를 JSON으로 직렬화해 INSERT OR REPLACE로 저장한다."""
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    blob = json.dumps(data, ensure_ascii=False, default=_json_default)
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO reports (date, key, data, created_at) VALUES (?, ?, ?, ?)",
            (date, key, blob, created_at),
        )
        conn.commit()


def load_report(date: str, key: str) -> Any | None:
    """해당 date+key의 데이터를 반환한다. 없으면 None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT data FROM reports WHERE date=? AND key=?", (date, key)
        ).fetchone()
    return json.loads(row[0]) if row else None


def load_latest_report(key: str) -> Any | None:
    """해당 key에서 가장 최근 date의 데이터를 반환한다. 없으면 None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT data FROM reports WHERE key=? ORDER BY date DESC LIMIT 1", (key,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def list_report_dates(key: str) -> list[str]:
    """해당 key가 존재하는 date 목록을 내림차순으로 반환한다."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT date FROM reports WHERE key=? ORDER BY date DESC", (key,)
        ).fetchall()
    return [r[0] for r in rows]


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    raise TypeError(f"JSON serializable unsupported type: {type(value)!r}")
