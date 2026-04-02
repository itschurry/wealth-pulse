from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "loguru" not in sys.modules:
    sys.modules["loguru"] = types.SimpleNamespace(
        logger=types.SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None, warning=lambda *a, **k: None)
    )

settings_stub = types.ModuleType("config.settings")
settings_stub.LOGS_DIR = Path(tempfile.gettempdir()) / "daily-market-brief-research-store-tests"
settings_stub.LOGS_DIR.mkdir(parents=True, exist_ok=True)
settings_stub.REPORT_OUTPUT_DIR = settings_stub.LOGS_DIR

with patch.dict(sys.modules, {"config.settings": settings_stub}):
    from routes.research import handle_research_ingest_bulk, handle_research_latest_snapshot, handle_research_status
    from services import research_store as store


class ResearchStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        base = Path(self.tmpdir.name)
        self.path_patches = [
            patch.object(store, "RESEARCH_DIR", base / "research_snapshots"),
            patch.object(store, "RESEARCH_LATEST_DIR", base / "research_snapshots" / "latest"),
            patch.object(store, "RESEARCH_INGEST_LOG_PATH", base / "research_snapshots" / "ingest_history.jsonl"),
            patch.object(store, "RESEARCH_PROVIDER_STATE_PATH", base / "research_snapshots" / "provider_state.json"),
        ]
        for item in self.path_patches:
            item.start()
            self.addCleanup(item.stop)

    def test_ingest_bulk_persists_latest_snapshot_and_status(self):
        status_code, payload = handle_research_ingest_bulk({
            "provider": "openclaw",
            "schema_version": "v1",
            "run_id": "cron-1",
            "generated_at": "2026-04-03T09:30:05+09:00",
            "items": [
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": "2026-04-03T09:30:00+09:00",
                    "research_score": 0.61,
                    "components": {"freshness_score": 0.8},
                    "warnings": ["already_extended_intraday"],
                    "tags": ["earnings"],
                    "summary": "ok",
                    "ttl_minutes": 120,
                }
            ],
        })

        self.assertEqual(200, status_code)
        self.assertEqual(1, payload["accepted"])
        latest = store.load_latest_research_snapshot("005930", "KR", provider="openclaw")
        self.assertIsNotNone(latest)
        self.assertEqual(0.61, latest["research_score"])

        status_code, status_payload = handle_research_status({"provider": ["openclaw"]})
        self.assertEqual(200, status_code)
        self.assertEqual("healthy", status_payload["status"])
        self.assertEqual("fresh", status_payload["freshness"])

    def test_latest_snapshot_route_returns_404_when_missing(self):
        status_code, payload = handle_research_latest_snapshot({"symbol": ["005930"], "market": ["KR"]})

        self.assertEqual(404, status_code)
        self.assertEqual("snapshot_not_found", payload["error"])

    def test_status_route_marks_missing_provider(self):
        status_code, payload = handle_research_status({})

        self.assertEqual(200, status_code)
        self.assertEqual("missing", payload["status"])
        self.assertEqual("missing", payload["freshness"])

    def test_load_research_snapshots_returns_bucket_filtered_descending(self):
        status_code, payload = handle_research_ingest_bulk({
            "provider": "openclaw",
            "schema_version": "v1",
            "run_id": "cron-window",
            "items": [
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": "2026-04-03T09:00:00+09:00",
                    "generated_at": "2026-04-03T09:00:00+09:00",
                    "research_score": 0.35,
                    "components": {"freshness_score": 0.9},
                    "warnings": ["already_extended_intraday"],
                    "tags": ["news"],
                    "summary": "window a",
                    "ttl_minutes": 120,
                },
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": "2026-04-03T10:00:00+09:00",
                    "generated_at": "2026-04-03T10:01:00+09:00",
                    "research_score": 0.61,
                    "components": {"freshness_score": 0.8},
                    "warnings": ["already_extended_intraday"],
                    "tags": ["earnings"],
                    "summary": "window b",
                    "ttl_minutes": 120,
                },
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": "2026-04-03T11:00:00+09:00",
                    "generated_at": "2026-04-03T11:01:00+09:00",
                    "research_score": 0.72,
                    "components": {"freshness_score": 0.7},
                    "warnings": ["already_extended_intraday"],
                    "tags": ["macro"],
                    "summary": "window c",
                    "ttl_minutes": 120,
                },
            ],
        })

        self.assertEqual(200, status_code)
        self.assertEqual(3, payload["accepted"])
        rows = store.load_research_snapshots(
            "005930",
            "KR",
            provider="openclaw",
            bucket_start="2026-04-03T09:30:00+09:00",
            bucket_end="2026-04-03T10:30:00+09:00",
            descending=True,
            limit=10,
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("window b", rows[0]["summary"])

    def test_load_research_snapshots_returns_ascending_when_descending_false(self):
        handle_research_ingest_bulk({
            "provider": "openclaw",
            "schema_version": "v1",
            "items": [
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": "2026-04-03T09:00:00+09:00",
                    "generated_at": "2026-04-03T09:00:00+09:00",
                    "research_score": 0.11,
                },
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": "2026-04-03T10:00:00+09:00",
                    "generated_at": "2026-04-03T10:00:00+09:00",
                    "research_score": 0.22,
                },
            ],
        })
        rows = store.load_research_snapshots("005930", "KR", provider="openclaw", descending=False, limit=10)

        self.assertEqual(2, len(rows))
        self.assertEqual(0.11, rows[0]["research_score"])
        self.assertEqual(0.22, rows[1]["research_score"])

    def test_load_research_snapshot_for_timestamp_aligns_bucket(self):
        handle_research_ingest_bulk({
            "provider": "openclaw",
            "schema_version": "v1",
            "items": [
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": "2026-04-03T09:00:00+09:00",
                    "generated_at": "2026-04-03T09:00:00+09:00",
                    "research_score": 0.44,
                },
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": "2026-04-03T10:00:00+09:00",
                    "generated_at": "2026-04-03T10:00:00+09:00",
                    "research_score": 0.55,
                },
            ],
        })
        row = store.load_research_snapshot_for_timestamp("005930", "KR", "2026-04-03T09:45:12+09:00", provider="openclaw")

        self.assertIsNotNone(row)
        self.assertEqual(0.44, row["research_score"])
