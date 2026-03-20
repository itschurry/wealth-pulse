#!/usr/bin/env python3
"""기존 report/*.json 파일들을 SQLite DB로 마이그레이션하는 1회성 스크립트.

실행 방법:
    python3 scripts/migrate_json_to_sqlite.py

- report/ 디렉토리의 모든 *.json 파일을 순회한다.
- 파일명 패턴: {date}_{key}.json 또는 {date}_{key}_cache.json
- date와 key를 파싱해서 storage.save_report() 호출
- 이미 DB에 존재하면 스킵 (INSERT OR IGNORE)
- 마이그레이션 완료 후 기존 JSON 파일들을 report/archive/ 로 이동
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import REPORT_OUTPUT_DIR
from reporter.storage import _connect


ARCHIVE_DIR = REPORT_OUTPUT_DIR / "archive"
# {date}_{key}.json 또는 {date}_{key}_cache.json
_PATTERN = re.compile(r'^(\d{4}-\d{2}-\d{2})_(.+?)(?:_cache)?\.json$')


def _insert_if_missing(conn, date: str, key: str, data_str: str, created_at: str) -> bool:
    """이미 존재하면 False(스킵), 삽입 시 True 반환."""
    existing = conn.execute(
        "SELECT id FROM reports WHERE date=? AND key=?", (date, key)
    ).fetchone()
    if existing:
        return False
    conn.execute(
        "INSERT INTO reports (date, key, data, created_at) VALUES (?, ?, ?, ?)",
        (date, key, data_str, created_at),
    )
    return True


def main() -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    json_files = sorted(REPORT_OUTPUT_DIR.glob("*.json"))
    if not json_files:
        print("마이그레이션할 JSON 파일이 없습니다.")
        return

    migrated = 0
    skipped = 0
    errors = 0

    conn = _connect()
    try:
        for path in json_files:
            m = _PATTERN.match(path.name)
            if not m:
                print(f"  [SKIP] 패턴 불일치: {path.name}")
                skipped += 1
                continue

            date, key = m.group(1), m.group(2)
            try:
                raw = path.read_text(encoding="utf-8")
                # JSON 유효성 검사
                json.loads(raw)
            except Exception as exc:
                print(f"  [ERROR] {path.name}: JSON 파싱 실패 — {exc}")
                errors += 1
                continue

            import datetime as _dt
            created_at = _dt.datetime.fromtimestamp(
                path.stat().st_mtime, tz=_dt.timezone.utc
            ).isoformat(timespec="seconds")

            inserted = _insert_if_missing(conn, date, key, raw, created_at)
            if inserted:
                print(f"  [OK]   {path.name} → {date}/{key}")
                migrated += 1
            else:
                print(f"  [SKIP] 이미 존재: {date}/{key}")
                skipped += 1

            # archive로 이동
            dest = ARCHIVE_DIR / path.name
            shutil.move(str(path), str(dest))

        conn.commit()
    finally:
        conn.close()

    print(f"\n완료: 마이그레이션={migrated}, 스킵={skipped}, 오류={errors}")
    print(f"원본 파일 이동 위치: {ARCHIVE_DIR}")


if __name__ == "__main__":
    main()
