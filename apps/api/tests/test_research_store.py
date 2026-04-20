from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path
import sys
import datetime
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
        now = datetime.datetime.now(datetime.timezone.utc).astimezone()
        bucket_ts = now.replace(second=0, microsecond=0)
        generated_at = (bucket_ts + datetime.timedelta(seconds=5)).isoformat()
        status_code, payload = handle_research_ingest_bulk({
            "provider": "openclaw",
            "schema_version": "v1",
            "run_id": "cron-1",
            "generated_at": generated_at,
            "items": [
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": bucket_ts.isoformat(),
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
        self.assertEqual(1, payload["received_valid"])
        self.assertEqual(0, payload["deduped_count"])
        latest = store.load_latest_research_snapshot("005930", "KR", provider="openclaw")
        self.assertIsNotNone(latest)
        self.assertEqual(0.61, latest["research_score"])
        self.assertEqual("fresh", latest["freshness"])
        self.assertFalse(latest["is_stale"])
        self.assertEqual("C", latest["validation"]["grade"])
        self.assertEqual("warning_codes_present", latest["validation"]["reason"])

        with patch.dict(handle_research_status.__globals__, {
            "handle_candidate_monitor_watchlist": lambda _query: (200, {"ok": True, "items": []}),
        }):
            status_code, status_payload = handle_research_status({"provider": ["openclaw"]})
        self.assertEqual(200, status_code)
        self.assertEqual("healthy", status_payload["status"])
        self.assertEqual("fresh", status_payload["freshness"])
        self.assertEqual("latest_snapshot_directory", status_payload["source_of_truth"])
        self.assertEqual("latest_snapshot_directory", status_payload["source"])
        self.assertEqual(1, status_payload["accepted_last_run"])
        self.assertEqual(0, status_payload["rejected_last_run"])
        self.assertEqual(1, status_payload["received_valid_last_run"])
        self.assertEqual(0, status_payload["deduped_count_last_run"])

    def test_market_alias_lookup_uses_canonical_market(self):
        status_code, payload = handle_research_ingest_bulk({
            "provider": "openclaw",
            "schema_version": "v1",
            "run_id": "cron-alias",
            "generated_at": "2026-04-03T10:10:00+09:00",
            "items": [
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": "2026-04-03T10:10:00+09:00",
                    "research_score": 0.66,
                    "components": {"freshness_score": 0.9},
                    "warnings": ["already_extended_intraday"],
                    "tags": ["earnings"],
                    "summary": "alias-normalized",
                    "ttl_minutes": 120,
                }
            ],
        })

        self.assertEqual(200, status_code)
        self.assertEqual(1, payload["accepted"])
        latest_kospi = store.load_latest_research_snapshot("005930", "KOSPI", provider="openclaw")
        latest_kr = store.load_latest_research_snapshot("005930", "KR", provider="openclaw")
        self.assertIsNotNone(latest_kospi)
        self.assertIsNotNone(latest_kr)
        self.assertEqual("KOSPI", latest_kospi["market"])
        self.assertEqual("KOSPI", latest_kr["market"])
        self.assertEqual(latest_kospi["summary"], latest_kr["summary"])
        self.assertEqual("alias-normalized", latest_kospi["summary"])

        rows_kospi = store.load_research_snapshots("005930", "KOSPI", provider="openclaw", limit=10)
        rows_kr = store.load_research_snapshots("005930", "KR", provider="openclaw", limit=10)
        self.assertEqual(1, len(rows_kospi))
        self.assertEqual(1, len(rows_kr))
        self.assertEqual(rows_kospi[0]["summary"], rows_kr[0]["summary"])

    def test_latest_snapshot_route_returns_404_when_missing(self):
        status_code, payload = handle_research_latest_snapshot({"symbol": ["005930"], "market": ["KR"]})

        self.assertEqual(404, status_code)
        self.assertEqual("snapshot_not_found", payload["error"])

    def test_status_route_marks_missing_provider(self):
        status_code, payload = handle_research_status({})

        self.assertEqual(200, status_code)
        self.assertEqual("missing", payload["status"])
        self.assertEqual("missing", payload["freshness"])

    def test_status_route_prefers_active_monitor_slot_freshness_over_storage_backlog(self):
        now = datetime.datetime.now(datetime.timezone.utc).astimezone().replace(second=0, microsecond=0)
        stale_generated = (now - datetime.timedelta(hours=6)).isoformat()
        fresh_generated = (now - datetime.timedelta(minutes=10)).isoformat()
        fresh_bucket = now.isoformat()
        stale_bucket = (now - datetime.timedelta(hours=6)).isoformat()

        handle_research_ingest_bulk({
            "provider": "openclaw",
            "schema_version": "v1",
            "run_id": "cron-stale",
            "generated_at": stale_generated,
            "items": [
                {
                    "symbol": "000660",
                    "market": "KR",
                    "bucket_ts": stale_bucket,
                    "generated_at": stale_generated,
                    "research_score": 0.42,
                    "components": {"freshness_score": 0.4},
                    "warnings": ["already_extended_intraday"],
                    "tags": [],
                    "summary": "stale backlog",
                    "ttl_minutes": 60,
                },
            ],
        })
        handle_research_ingest_bulk({
            "provider": "openclaw",
            "schema_version": "v1",
            "run_id": "cron-fresh",
            "generated_at": fresh_generated,
            "items": [
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": fresh_bucket,
                    "generated_at": fresh_generated,
                    "research_score": 0.78,
                    "components": {"freshness_score": 0.9},
                    "warnings": ["already_extended_intraday"],
                    "tags": [],
                    "summary": "active fresh",
                    "ttl_minutes": 180,
                },
            ],
        })

        fake_watchlist = (200, {
            "ok": True,
            "items": [
                {
                    "market": "KOSPI",
                    "state": {"generated_at": now.isoformat()},
                    "active_slots": [
                        {"symbol": "005930", "market": "KOSPI"},
                    ],
                },
            ],
        })
        with patch.dict(handle_research_status.__globals__, {
            "handle_candidate_monitor_watchlist": lambda _query: fake_watchlist,
        }):
            status_code, payload = handle_research_status({"provider": ["openclaw"]})

        self.assertEqual(200, status_code)
        self.assertEqual("healthy", payload["status"])
        self.assertEqual("fresh", payload["freshness"])
        self.assertEqual("candidate_monitor_active_slots", payload["source_of_truth"])
        self.assertEqual("candidate_monitor_active_slots", payload["source"])
        self.assertEqual(1, payload["active_slot_count"])
        self.assertEqual(1, payload["active_fresh_symbol_count"])
        self.assertEqual(0, payload["active_stale_symbol_count"])
        self.assertEqual(0, payload["active_missing_symbol_count"])

    def test_status_route_reads_current_watchlist_without_forcing_refresh(self):
        captured_query = {}

        def _fake_watchlist(query):
            captured_query.update(query)
            return 200, {"ok": True, "items": []}

        with patch.dict(handle_research_status.__globals__, {
            "handle_candidate_monitor_watchlist": _fake_watchlist,
        }):
            status_code, payload = handle_research_status({"provider": ["openclaw"]})

        self.assertEqual(200, status_code)
        self.assertEqual(["0"], captured_query["refresh"])
        self.assertEqual(["200"], captured_query["limit"])
        self.assertEqual(["missing_or_stale"], captured_query["mode"])

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

    def test_same_bucket_reingest_can_replace_latest_when_newer_generated(self):
        handle_research_ingest_bulk({
            "provider": "openclaw",
            "schema_version": "v1",
            "run_id": "cron-replace-1",
            "generated_at": "2026-04-03T10:01:00+09:00",
            "items": [
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": "2026-04-03T10:00:00+09:00",
                    "research_score": 0.55,
                    "components": {"freshness_score": 0.8},
                    "warnings": ["already_extended_intraday"],
                    "tags": ["news"],
                    "summary": "older_generation",
                    "ttl_minutes": 120,
                }
            ],
        })
        status_code, payload = handle_research_ingest_bulk({
            "provider": "openclaw",
            "schema_version": "v1",
            "run_id": "cron-replace-2",
            "generated_at": "2026-04-03T10:05:00+09:00",
            "items": [
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": "2026-04-03T10:00:00+09:00",
                    "research_score": 0.72,
                    "components": {"freshness_score": 0.9},
                    "warnings": ["already_extended_intraday"],
                    "tags": ["news"],
                    "summary": "newer_generation",
                    "ttl_minutes": 120,
                }
            ],
        })

        self.assertEqual(200, status_code)
        self.assertEqual(1, payload["accepted"])
        self.assertEqual(1, payload["received_valid"])
        self.assertEqual(0, payload["deduped_count"])
        latest = store.load_latest_research_snapshot("005930", "KR", provider="openclaw")
        self.assertIsNotNone(latest)
        self.assertEqual("newer_generation", latest["summary"])

    def test_load_research_snapshot_for_timestamp_is_bucket_lookup_only(self):
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
                    "ttl_minutes": 1,
                }
            ],
        })
        row = store.load_research_snapshot_for_timestamp(
            "005930",
            "KR",
            "2099-01-01T00:00:00+09:00",
            provider="openclaw",
        )

        self.assertIsNotNone(row)
        self.assertEqual(0.44, row["research_score"])

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

    def test_ingest_rejects_research_unavailable_warning(self):
        status_code, payload = handle_research_ingest_bulk({
            "provider": "openclaw",
            "schema_version": "v1",
            "run_id": "cron-warning",
            "generated_at": "2026-04-03T09:30:00+09:00",
            "items": [
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": "2026-04-03T09:30:00+09:00",
                    "research_score": 0.4,
                    "components": {"freshness_score": 0.7},
                    "warnings": ["research_unavailable"],
                    "tags": ["earnings"],
                    "summary": "invalid warning",
                    "ttl_minutes": 120,
                }
            ],
        })

        self.assertEqual(400, status_code)
        self.assertEqual(0, payload["accepted"])
        self.assertEqual(1, payload["rejected"])
        self.assertEqual("warning_code_unsupported", payload["errors"][0]["error"])

    def test_same_bucket_payload_is_deduped_in_history(self):
        handle_research_ingest_bulk({
            "provider": "openclaw",
            "schema_version": "v1",
            "run_id": "cron-dup-1",
            "generated_at": "2026-04-03T10:00:00+09:00",
            "items": [
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": "2026-04-03T10:00:00+09:00",
                    "research_score": 0.55,
                    "components": {"freshness_score": 0.8},
                    "warnings": ["already_extended_intraday"],
                    "tags": ["news"],
                    "summary": "first",
                    "ttl_minutes": 120,
                }
            ],
        })
        status_code, payload = handle_research_ingest_bulk({
            "provider": "openclaw",
            "schema_version": "v1",
            "run_id": "cron-dup-2",
            "generated_at": "2026-04-03T09:00:00+09:00",
            "items": [
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": "2026-04-03T10:00:00+09:00",
                    "research_score": 0.60,
                    "components": {"freshness_score": 0.9},
                    "warnings": ["already_extended_intraday"],
                    "tags": ["news"],
                    "summary": "duplicate",
                    "ttl_minutes": 120,
                }
            ],
        })

        self.assertEqual(200, status_code)
        self.assertEqual(0, payload["accepted"])
        self.assertEqual(1, payload["received_valid"])
        self.assertEqual(1, payload["deduped_count"])
        rows = store.load_research_snapshots("005930", "KR", provider="openclaw", limit=20, descending=True)
        self.assertEqual(1, len(rows))

    def test_older_bucket_does_not_override_latest(self):
        first_at = "2026-04-03T11:00:00+09:00"
        first_generated_at = first_at
        older_at = "2026-04-03T09:00:00+09:00"
        older_generated_at = older_at
        first_bucket_utc = "2026-04-03T02:00:00+00:00"
        handle_research_ingest_bulk({
            "provider": "openclaw",
            "schema_version": "v1",
            "run_id": "cron-recent",
            "generated_at": "2026-04-03T11:00:00+09:00",
            "items": [
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": first_at,
                    "generated_at": first_generated_at,
                    "research_score": 0.72,
                    "components": {"freshness_score": 0.6},
                    "warnings": ["already_extended_intraday"],
                    "tags": ["macro"],
                    "summary": "recent",
                    "ttl_minutes": 120,
                }
            ],
        })
        handle_research_ingest_bulk({
            "provider": "openclaw",
            "schema_version": "v1",
            "run_id": "cron-older",
            "generated_at": "2026-04-03T09:00:00+09:00",
            "items": [
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": older_at,
                    "generated_at": older_generated_at,
                    "research_score": 0.35,
                    "components": {"freshness_score": 0.5},
                    "warnings": ["already_extended_intraday"],
                    "tags": ["macro"],
                    "summary": "older",
                    "ttl_minutes": 120,
                }
            ],
        })
        latest = store.load_latest_research_snapshot("005930", "KR", provider="openclaw")

        self.assertIsNotNone(latest)
        self.assertEqual(first_bucket_utc, latest["bucket_ts"])
        self.assertEqual("recent", latest["summary"])

        older = store.load_research_snapshot_for_timestamp("005930", "KR", "2026-04-03T09:30:00+09:00", provider="openclaw")
        self.assertIsNotNone(older)
        self.assertEqual("older", older["summary"])

    def test_status_flags_stale_when_any_symbol_stale(self):
        now = datetime.datetime.now(datetime.timezone.utc).astimezone()
        stale_timestamp = (now - datetime.timedelta(hours=3)).astimezone().isoformat()
        fresh_timestamp = (now - datetime.timedelta(minutes=5)).astimezone().isoformat()

        handle_research_ingest_bulk({
            "provider": "openclaw",
            "schema_version": "v1",
            "items": [
                {
                    "symbol": "005930",
                    "market": "KR",
                    "bucket_ts": stale_timestamp,
                    "generated_at": stale_timestamp,
                    "research_score": 0.2,
                    "components": {"freshness_score": 0.3},
                    "warnings": ["already_extended_intraday"],
                    "summary": "stale",
                    "ttl_minutes": 30,
                },
                {
                    "symbol": "035420",
                    "market": "KR",
                    "bucket_ts": fresh_timestamp,
                    "generated_at": fresh_timestamp,
                    "research_score": 0.8,
                    "components": {"freshness_score": 0.9},
                    "warnings": ["already_extended_intraday"],
                    "summary": "fresh",
                    "ttl_minutes": 120,
                },
            ],
        })

        with patch.dict(handle_research_status.__globals__, {
            "handle_candidate_monitor_watchlist": lambda _query: (200, {"ok": True, "items": []}),
        }):
            status_code, status_payload = handle_research_status({"provider": ["openclaw"]})
        self.assertEqual(200, status_code)
        self.assertEqual("stale_ingest", status_payload["status"])
        self.assertEqual("stale", status_payload["freshness"])
        self.assertEqual(2, status_payload["coverage_count"])
        self.assertEqual(1, status_payload["stale_symbol_count"])

        stale_snapshot = store.load_latest_research_snapshot("005930", "KR", provider="openclaw")
        self.assertIsNotNone(stale_snapshot)
        self.assertEqual("stale", stale_snapshot["freshness"])
        self.assertTrue(stale_snapshot["is_stale"])
        self.assertEqual("C", stale_snapshot["validation"]["grade"])
        self.assertEqual("stale_snapshot", stale_snapshot["validation"]["reason"])
        self.assertEqual(1, status_payload["fresh_symbol_count"])
