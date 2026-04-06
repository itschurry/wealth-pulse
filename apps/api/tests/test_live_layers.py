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
settings_stub.LOGS_DIR = Path(tempfile.gettempdir()) / "daily-market-brief-test-logs"
settings_stub.LOGS_DIR.mkdir(parents=True, exist_ok=True)
settings_stub.REPORT_OUTPUT_DIR = settings_stub.LOGS_DIR

with patch.dict(sys.modules, {"config.settings": settings_stub}):
    from services.live_layers import build_layer_d_snapshot, build_layer_e_snapshot
    import services.research_scoring as research_scoring
    from services.research_scoring import NullResearchScorer, ResearchScoreRequest, StoredResearchScorer


class LiveLayerTests(unittest.TestCase):
    def test_null_research_scorer_marks_unavailable_without_order_command(self):
        scorer = NullResearchScorer()
        result = scorer.score(ResearchScoreRequest(symbol="AAA", market="KOSPI", timestamp="2026-04-02T17:00:00+09:00"))

        self.assertFalse(result.available)
        self.assertEqual("research_unavailable", result.status)
        self.assertIn("research_unavailable", result.warnings)
        self.assertNotIn("buy", result.summary.lower())
        self.assertNotIn("sell", result.summary.lower())
        self.assertNotIn("order", result.summary.lower())

    def test_stored_research_scorer_reads_fresh_snapshot(self):
        scorer = StoredResearchScorer(provider="openclaw")
        with patch.object(
            research_scoring,
            "load_research_snapshot_for_timestamp",
            return_value={
                "research_score": 0.61,
                "components": {"freshness_score": 0.8},
                "warnings": ["already_extended_intraday"],
                "tags": ["earnings"],
                "summary": "snapshot ok",
                "ttl_minutes": 120,
                "generated_at": "2026-04-02T17:00:00+09:00",
            },
        ):
            result = scorer.score(ResearchScoreRequest(symbol="AAA", market="KOSPI", timestamp="2026-04-02T17:30:00+09:00"))

        self.assertTrue(result.available)
        self.assertEqual("healthy", result.status)
        self.assertEqual(0.61, result.research_score)
        self.assertEqual(["already_extended_intraday"], result.warnings)
        self.assertEqual("openclaw", result.source)

    def test_stored_research_scorer_marks_stale_snapshot_unavailable(self):
        scorer = StoredResearchScorer(provider="openclaw")
        with patch.object(
            research_scoring,
            "load_research_snapshot_for_timestamp",
            return_value={
                "research_score": 0.77,
                "components": {"freshness_score": 0.8},
                "warnings": ["already_extended_intraday"],
                "tags": ["earnings"],
                "summary": "snapshot stale",
                "ttl_minutes": 5,
                "generated_at": "2026-04-02T09:00:00+09:00",
            },
        ):
            result = scorer.score(ResearchScoreRequest(symbol="AAA", market="KOSPI", timestamp="2026-04-02T17:30:00+09:00"))

        self.assertFalse(result.available)
        self.assertEqual("stale_ingest", result.status)
        self.assertIsNone(result.research_score)
        self.assertEqual(["research_unavailable"], result.warnings)

    def test_final_action_uses_required_semantics(self):
        risk = build_layer_d_snapshot(
            risk_check={"passed": True, "reason_code": "OK", "message": "ok", "checks": []},
            size_recommendation={"quantity": 3, "reason": "ok"},
            risk_guard_state={"entry_allowed": True, "reasons": []},
            research={"research_unavailable": True, "warnings": ["research_unavailable"]},
        )
        review = build_layer_e_snapshot(
            signal_state="entry",
            quant_score=82.0,
            research={"research_unavailable": True, "research_score": None, "warnings": ["research_unavailable"]},
            risk=risk,
            timestamp="2026-04-02T17:00:00+09:00",
            source_context={"symbol": "AAA"},
        )
        blocked = build_layer_e_snapshot(
            signal_state="entry",
            quant_score=82.0,
            research={"research_unavailable": False, "research_score": 0.7, "warnings": []},
            risk={"blocked": True},
            timestamp="2026-04-02T17:00:00+09:00",
            source_context={"symbol": "AAA"},
        )
        watch = build_layer_e_snapshot(
            signal_state="entry",
            quant_score=61.0,
            research={"research_unavailable": False, "research_score": 0.51, "warnings": ["low_evidence_density"]},
            risk=risk,
            timestamp="2026-04-02T17:00:00+09:00",
            source_context={"symbol": "AAA"},
        )
        no_touch = build_layer_e_snapshot(
            signal_state="watch",
            quant_score=31.0,
            research={"research_unavailable": False, "research_score": 0.2, "warnings": []},
            risk=risk,
            timestamp="2026-04-02T17:00:00+09:00",
            source_context={"symbol": "AAA"},
        )

        self.assertEqual("review_for_entry", review["final_action"])
        self.assertEqual("blocked", blocked["final_action"])
        self.assertEqual("watch_only", watch["final_action"])
        self.assertEqual("do_not_touch", no_touch["final_action"])


if __name__ == "__main__":
    unittest.main()
