from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


validation_stub = types.ModuleType("services.validation_service")
validation_stub.run_validation_diagnostics = lambda payload: {"ok": True, "validation": {}, "diagnosis": {}, "research": {}}
settings_stub = types.ModuleType("config.settings")
settings_stub.LOGS_DIR = Path(tempfile.gettempdir()) / "daily-market-brief-test-logs"
settings_stub.LOGS_DIR.mkdir(parents=True, exist_ok=True)

with patch.dict(sys.modules, {
    "services.validation_service": validation_stub,
    "config.settings": settings_stub,
}):
    from services import quant_ops_service as svc  # noqa: E402


_NOW = dt.datetime(2026, 3, 31, 12, 0, tzinfo=dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _adopt_diagnostics() -> dict:
    return {
        "ok": True,
        "validation": {
            "ok": True,
            "segments": {
                "oos": {
                    "total_return_pct": 8.4,
                    "profit_factor": 1.26,
                    "max_drawdown_pct": -12.4,
                    "trade_count": 18,
                    "sharpe": 0.93,
                    "win_rate_pct": 56.0,
                    "strategy_scorecard": {
                        "composite_score": 32.0,
                        "tail_risk": {
                            "expected_shortfall_5_pct": -9.4,
                            "return_p05_pct": -6.8,
                        },
                    },
                },
            },
            "summary": {
                "windows": 6,
                "positive_window_ratio": 0.67,
                "oos_reliability": "high",
                "reliability_diagnostic": {
                    "target_reached": True,
                    "current": {
                        "label": "high",
                        "reason": "validated_candidate",
                        "trade_count": 18,
                        "validation_signals": 18,
                        "validation_sharpe": 0.93,
                        "max_drawdown_pct": -12.4,
                        "passes_minimum_gate": True,
                        "is_reliable": True,
                    },
                },
            },
            "scorecard": {
                "composite_score": 32.0,
                "tail_risk": {
                    "expected_shortfall_5_pct": -9.4,
                    "return_p05_pct": -6.8,
                },
            },
        },
        "diagnosis": {
            "label": "high",
            "summary_lines": ["OOS 표본과 PF가 모두 안정권입니다."],
        },
        "research": {
            "target_label": "medium",
            "best_label": "high",
            "suggestions": [],
        },
    }


def _reject_diagnostics() -> dict:
    payload = _adopt_diagnostics()
    payload["validation"]["segments"]["oos"].update({
        "total_return_pct": -4.8,
        "profit_factor": 0.82,
        "max_drawdown_pct": -35.0,
        "trade_count": 4,
    })
    payload["validation"]["summary"].update({
        "positive_window_ratio": 0.2,
        "oos_reliability": "low",
    })
    payload["validation"]["scorecard"]["tail_risk"]["expected_shortfall_5_pct"] = -25.0
    return payload


def _limited_adopt_diagnostics() -> dict:
    payload = _adopt_diagnostics()
    payload["validation"]["segments"]["oos"].update({
        "total_return_pct": 3.1,
        "profit_factor": 1.05,
        "max_drawdown_pct": -22.5,
        "trade_count": 16,
    })
    payload["validation"]["summary"].update({
        "positive_window_ratio": 0.57,
        "oos_reliability": "high",
    })
    payload["validation"]["scorecard"]["tail_risk"].update({
        "expected_shortfall_5_pct": -12.8,
        "return_p05_pct": -10.2,
    })
    payload["validation"]["segments"]["oos"]["strategy_scorecard"]["tail_risk"].update({
        "expected_shortfall_5_pct": -12.8,
        "return_p05_pct": -10.2,
    })
    return payload


class QuantOpsWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.state_path = Path(self.tmpdir.name) / "quant_ops_state.json"
        self.runtime_store: dict[str, dict] = {"payload": {}}
        self.search_payload = {
            "optimized_at": _NOW,
            "version": "search-2026-03-31T12:00:00+09:00",
            "global_params": {
                "stop_loss_pct": 6.0,
                "take_profit_pct": 18.0,
                "max_holding_days": 18,
                "rsi_min": 38.0,
                "rsi_max": 72.0,
            },
            "strategy_candidates": [
                {
                    "key": "sc-high",
                    "label": "고신뢰 추세 후보",
                    "summary": "표본과 PF가 모두 안정적인 대표 전략 후보",
                    "source": "optimizer_strategy_candidate",
                    "reliability": "high",
                    "is_reliable": True,
                    "reliability_reason": "stable",
                    "metrics": {
                        "composite_score": 32.0,
                        "profit_factor": 1.26,
                        "validation_sharpe": 0.93,
                        "trade_count": 18,
                        "max_drawdown_pct": -12.4,
                    },
                    "patch": {
                        "stop_loss_pct": 4.2,
                        "take_profit_pct": 15.8,
                        "max_holding_days": 14,
                    },
                    "patch_lines": [
                        "stop_loss_pct: 4.2",
                        "take_profit_pct: 15.8",
                        "max_holding_days: 14",
                    ],
                },
                {
                    "key": "sc-low",
                    "label": "저신뢰 역추세 후보",
                    "summary": "표본이 부족해 운영 후보로 쓰기 어려운 전략 후보",
                    "source": "optimizer_strategy_candidate",
                    "reliability": "low",
                    "is_reliable": False,
                    "reliability_reason": "insufficient_samples",
                    "metrics": {
                        "composite_score": 7.0,
                        "profit_factor": 0.82,
                        "validation_sharpe": -0.1,
                        "trade_count": 4,
                        "max_drawdown_pct": -31.2,
                    },
                    "patch": {
                        "stop_loss_pct": 7.0,
                    },
                    "patch_lines": [
                        "stop_loss_pct: 7.0",
                    ],
                },
            ],
            "per_symbol": {
                "AAA": {
                    "is_reliable": True,
                    "strategy_reliability": "high",
                    "reliability_reason": "stable",
                    "trade_count": 22,
                    "validation_trades": 22,
                    "validation_sharpe": 0.78,
                    "max_drawdown_pct": -13.1,
                    "stop_loss_pct": 4.2,
                    "take_profit_pct": 15.8,
                    "max_holding_days": 14,
                },
                "BBB": {
                    "is_reliable": False,
                    "strategy_reliability": "low",
                    "reliability_reason": "insufficient_samples",
                    "trade_count": 4,
                    "validation_trades": 4,
                    "validation_sharpe": -0.1,
                    "max_drawdown_pct": -31.2,
                    "stop_loss_pct": 7.0,
                },
            },
            "meta": {
                "n_symbols_optimized": 1,
                "n_reliable": 1,
                "n_medium": 0,
                "global_overlay_source": "high_only",
            },
        }

    def _runtime_writer(self, payload: dict) -> Path:
        self.runtime_store["payload"] = json.loads(json.dumps(payload))
        return Path(self.tmpdir.name) / "runtime_optimized_params.json"

    def test_revalidate_builds_candidate_and_workflow_summary(self):
        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None), \
             patch.object(svc, "run_validation_diagnostics", return_value=_adopt_diagnostics()):
            result = svc.revalidate_optimizer_candidate({
                "query": {
                    "market_scope": "kospi",
                    "lookback_days": 365,
                },
                "settings": {
                    "strategy": "퀀트 운영 전략",
                    "trainingDays": 180,
                    "validationDays": 60,
                    "walkForward": True,
                    "minTrades": 8,
                },
            })

        self.assertTrue(result["ok"])
        candidate = result["candidate"]
        self.assertEqual("optimizer_global_overlay", candidate["source"])
        self.assertEqual("quant_only", candidate["runtime_candidate_source_mode"])
        self.assertEqual("adopt", candidate["decision"]["status"])
        self.assertTrue(candidate["guardrails"]["can_save"])
        self.assertIn("stop_loss_pct: 5.0 → 6.0", candidate["patch_lines"])
        self.assertEqual(18, candidate["candidate_query"]["max_holding_days"])
        self.assertTrue(result["workflow"]["search_result"]["available"])
        self.assertEqual(2, result["workflow"]["search_result"]["strategy_candidate_count"])
        self.assertEqual("sc-high", result["workflow"]["search_result"]["strategy_candidates"][0]["key"])
        self.assertEqual("adopt", result["workflow"]["stage_status"]["revalidation"])
        self.assertTrue(self.state_path.exists())
        self.assertNotIn("symbol_candidates", result["workflow"])

    def test_revalidate_selected_strategy_candidate_uses_explicit_candidate_key(self):
        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None), \
             patch.object(svc, "run_validation_diagnostics", return_value=_adopt_diagnostics()):
            result = svc.revalidate_optimizer_candidate({
                "query": {
                    "market_scope": "kospi",
                    "lookback_days": 365,
                    "stop_loss_pct": 5.0,
                    "take_profit_pct": 15.0,
                    "max_holding_days": 21,
                },
                "settings": {
                    "strategy": "퀀트 운영 전략",
                    "trainingDays": 180,
                    "validationDays": 60,
                    "walkForward": True,
                    "minTrades": 8,
                },
                "candidate_key": "sc-high",
            })

        self.assertTrue(result["ok"])
        candidate = result["candidate"]
        self.assertEqual("optimizer_search_candidate", candidate["source"])
        self.assertEqual("sc-high", candidate["search_candidate_key"])
        self.assertEqual("고신뢰 추세 후보", candidate["search_candidate_label"])
        self.assertEqual("표본과 PF가 모두 안정적인 대표 전략 후보", candidate["search_candidate_summary"])
        self.assertEqual(5.0, candidate["candidate_query"]["stop_loss_pct"])
        self.assertEqual(21, candidate["candidate_query"]["max_holding_days"])
        self.assertIn("max_holding_days: 14", candidate["patch_lines"])

    def test_optimizer_handoff_promotes_latest_candidate_from_search(self):
        payload = {
            "query": {
                "market_scope": "nasdaq",
                "lookback_days": 365,
                "stop_loss_pct": 4.5,
                "take_profit_pct": 11.0,
            },
            "settings": {
                "strategy": "자동 handoff 전략",
                "trainingDays": 200,
                "validationDays": 50,
                "walkForward": True,
                "minTrades": 8,
            },
        }

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None), \
             patch.object(svc, "run_validation_diagnostics", return_value=_adopt_diagnostics()):
            registered = svc.register_optimizer_search_handoff(payload)
            result = svc.finalize_optimizer_search_handoff(success=True)
            workflow = svc.get_quant_ops_workflow()

        self.assertIsNotNone(registered)
        self.assertTrue(result["ok"])
        self.assertEqual("candidate_updated", result["handoff"]["status"])
        self.assertEqual("adopt", result["candidate"]["decision"]["status"])
        self.assertEqual(self.search_payload["version"], result["candidate"]["search_version"])
        self.assertEqual("candidate_updated", workflow["search_handoff"]["status"])
        self.assertEqual(self.search_payload["version"], workflow["latest_candidate"]["search_version"])
        self.assertEqual("adopt", workflow["stage_status"]["revalidation"])


    def test_workflow_recovers_pending_handoff_when_search_finished_but_callback_was_missed(self):
        requested_at = (
            dt.datetime.fromisoformat(_NOW).astimezone(dt.timezone.utc) - dt.timedelta(minutes=5)
        ).astimezone().isoformat(timespec="seconds")
        state = {
            "pending_search_handoff": {
                "query": {
                    "market_scope": "nasdaq",
                    "lookback_days": 365,
                    "stop_loss_pct": 4.5,
                    "take_profit_pct": 11.0,
                },
                "settings": {
                    "strategy": "자동 handoff 전략",
                    "trainingDays": 200,
                    "validationDays": 50,
                    "walkForward": True,
                    "minTrades": 8,
                },
                "requested_at": requested_at,
                "status": "pending",
            }
        }
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None), \
             patch.object(svc, "run_validation_diagnostics", return_value=_adopt_diagnostics()):
            workflow = svc.get_quant_ops_workflow()

        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual("candidate_updated", workflow["search_handoff"]["status"])
        self.assertIsNone(persisted["pending_search_handoff"])
        self.assertEqual("candidate_updated", persisted["last_search_handoff"]["status"])
        self.assertIsNotNone(workflow["latest_candidate"])
        self.assertEqual(self.search_payload["version"], workflow["latest_candidate"]["search_version"])
        self.assertEqual("adopt", workflow["stage_status"]["revalidation"])

    def test_finalize_handoff_marks_revalidation_exception_without_leaving_pending(self):
        payload = {
            "query": {
                "market_scope": "nasdaq",
                "lookback_days": 365,
                "stop_loss_pct": 4.5,
                "take_profit_pct": 11.0,
            },
            "settings": {
                "strategy": "자동 handoff 전략",
                "trainingDays": 200,
                "validationDays": 50,
                "walkForward": True,
                "minTrades": 8,
            },
        }

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None), \
             patch.object(svc, "run_validation_diagnostics", side_effect=RuntimeError("boom")):
            svc.register_optimizer_search_handoff(payload)
            result = svc.finalize_optimizer_search_handoff(success=True)
            workflow = svc.get_quant_ops_workflow()

        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertFalse(result["ok"])
        self.assertEqual("boom", result["error"])
        self.assertEqual("revalidate_failed", result["handoff"]["status"])
        self.assertEqual("revalidate_failed", workflow["search_handoff"]["status"])
        self.assertEqual("boom", workflow["search_handoff"]["error"])
        self.assertIsNone(persisted["pending_search_handoff"])

    def test_workflow_surfaces_empty_search_artifact_as_present(self):
        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path),              patch.object(svc, "load_search_optimized_params", return_value={}),              patch.object(svc, "load_runtime_optimized_params", return_value=None):
            workflow = svc.get_quant_ops_workflow()

        self.assertTrue(workflow["search_available"])
        self.assertEqual("ready", workflow["candidate_search"])
        self.assertTrue(workflow["search_result"]["available"])
        self.assertFalse(workflow["search_result"]["has_materialized_payload"])
        self.assertEqual({}, workflow["search_result"]["global_params"])
        self.assertEqual("missing", workflow["stage_status"]["revalidation"])

    def test_workflow_recovers_search_artifact_from_disk_when_loader_returns_none(self):
        search_path = Path(self.tmpdir.name) / "optimized_params.json"
        search_path.write_text(json.dumps(self.search_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "SEARCH_OPTIMIZED_PARAMS_PATH", search_path), \
             patch.object(svc, "load_search_optimized_params", return_value=None), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None), \
             patch.object(svc, "run_validation_diagnostics", return_value=_adopt_diagnostics()):
            result = svc.revalidate_optimizer_candidate({
                "query": {"market_scope": "kospi", "lookback_days": 365},
                "settings": {
                    "strategy": "디스크 복구 전략",
                    "trainingDays": 180,
                    "validationDays": 60,
                    "walkForward": True,
                    "minTrades": 8,
                },
            })

        self.assertTrue(result["ok"])
        self.assertTrue(result["workflow"]["search_available"])
        self.assertEqual(self.search_payload["version"], result["workflow"]["search_result"]["version"])
        self.assertNotIn("optimizer_search_missing", result["workflow"]["latest_candidate_state"]["reasons"])

    def test_optimizer_job_active_clears_stale_flag_when_search_artifact_is_newer(self):
        search_path = Path(self.tmpdir.name) / "optimized_params.json"
        search_path.write_text(json.dumps(self.search_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        flag_path = Path(self.tmpdir.name) / "optimization_running"
        flag_path.write_text("34567", encoding="utf-8")

        flag_ts = dt.datetime.now().timestamp() - 30
        search_ts = flag_ts + 10
        os.utime(flag_path, (flag_ts, flag_ts))
        os.utime(search_path, (search_ts, search_ts))

        with patch.object(svc, "_OPT_RUNNING_FLAG", flag_path), \
             patch.object(svc, "SEARCH_OPTIMIZED_PARAMS_PATH", search_path), \
             patch.object(svc.os, "kill", return_value=None):
            self.assertFalse(svc._optimizer_job_active())

        self.assertFalse(flag_path.exists())

    def test_workflow_self_heals_missing_state_file_when_search_artifact_exists(self):
        self.assertFalse(self.state_path.exists())

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None):
            workflow = svc.get_quant_ops_workflow()

        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertTrue(workflow["search_available"])
        self.assertEqual("ready", workflow["candidate_search"])
        self.assertTrue(workflow["search_result"]["available"])
        self.assertIsNone(workflow["latest_candidate"])
        self.assertIsNone(workflow["saved_candidate"])
        self.assertEqual("missing", workflow["stage_status"]["revalidation"])
        self.assertEqual("missing", workflow["stage_status"]["save"])
        self.assertIn("runtime_apply", persisted)

    def test_workflow_reconstructs_runtime_apply_from_runtime_artifact_without_state_file(self):
        runtime_payload = {
            "optimized_at": _NOW,
            "applied_at": _NOW,
            "version": "runtime-cand-runtime-001",
            "global_params": {
                "stop_loss_pct": 6.0,
                "take_profit_pct": 18.0,
            },
            "per_symbol": {
                "AAA": {
                    "approved_candidate_id": "symcand-aaa-runtime-001",
                    "approved_saved_at": _NOW,
                    "approved_by_quant_ops": True,
                },
            },
            "meta": {
                "applied_candidate_id": "cand-runtime-001",
                "approved_symbol_count": 1,
                "approved_symbols": ["AAA"],
                "search_version": self.search_payload["version"],
                "search_optimized_at": self.search_payload["optimized_at"],
            },
        }

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", return_value=runtime_payload):
            workflow = svc.get_quant_ops_workflow()

        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual("applied", workflow["runtime_apply"]["status"])
        self.assertTrue(workflow["runtime_apply"]["active"])
        self.assertEqual("cand-runtime-001", workflow["runtime_apply"]["candidate_id"])
        self.assertEqual(1, workflow["runtime_apply"]["applied_symbol_count"])
        self.assertEqual("applied", workflow["stage_status"]["runtime_apply"])
        self.assertEqual("cand-runtime-001", persisted["runtime_apply"]["candidate_id"])

    def test_workflow_hides_orphan_candidates_when_search_file_is_missing(self):
        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None), \
             patch.object(svc, "run_validation_diagnostics", return_value=_adopt_diagnostics()):
            svc.revalidate_optimizer_candidate({
                "query": {"market_scope": "kospi", "lookback_days": 365},
                "settings": {"strategy": "운영 전략", "minTrades": 8},
            })
            save_result = svc.save_validated_candidate({"note": "saved"})

        self.assertTrue(save_result["ok"])

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "SEARCH_OPTIMIZED_PARAMS_PATH", Path(self.tmpdir.name) / "missing-search.json"), \
             patch.object(svc, "load_search_optimized_params", return_value=None), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None):
            workflow = svc.get_quant_ops_workflow()

        self.assertFalse(workflow["search_available"])
        self.assertEqual("missing", workflow["candidate_search"])
        self.assertFalse(workflow["search_result"]["available"])
        self.assertIsNone(workflow["latest_candidate"])
        self.assertEqual("stale", workflow["latest_candidate_state"]["status"])
        self.assertIn("optimizer_search_missing", workflow["latest_candidate_state"]["reasons"])
        self.assertIsNone(workflow["saved_candidate"])
        self.assertEqual("stale", workflow["saved_candidate_state"]["status"])
        self.assertEqual("missing", workflow["stage_status"]["revalidation"])
        self.assertEqual("missing", workflow["stage_status"]["save"])

    def test_workflow_invalidates_candidates_when_saved_validation_settings_change(self):
        query = {
            "market_scope": "kospi",
            "lookback_days": 365,
            "stop_loss_pct": 5.0,
            "take_profit_pct": 15.0,
        }
        settings = {
            "strategy": "운영 전략",
            "trainingDays": 180,
            "validationDays": 60,
            "walkForward": True,
            "minTrades": 8,
        }
        baseline_payload = {"query": query, "settings": settings, "saved_at": _NOW}
        changed_payload = {
            "query": {**query, "lookback_days": 730},
            "settings": {**settings, "validationDays": 90},
            "saved_at": _NOW,
        }

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None), \
             patch.object(svc, "load_persisted_validation_settings", return_value=baseline_payload), \
             patch.object(svc, "run_validation_diagnostics", return_value=_adopt_diagnostics()):
            svc.revalidate_optimizer_candidate({"query": query, "settings": settings})
            save_result = svc.save_validated_candidate({"note": "saved"})

        self.assertTrue(save_result["ok"])

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None), \
             patch.object(svc, "load_persisted_validation_settings", return_value=changed_payload):
            workflow = svc.get_quant_ops_workflow()

        self.assertTrue(workflow["search_available"])
        self.assertEqual("ready", workflow["candidate_search"])
        self.assertIsNone(workflow["latest_candidate"])
        self.assertIn("validation_settings_changed", workflow["latest_candidate_state"]["reasons"])
        self.assertIsNone(workflow["saved_candidate"])
        self.assertIn("validation_settings_changed", workflow["saved_candidate_state"]["reasons"])
        self.assertEqual("missing", workflow["stage_status"]["revalidation"])
        self.assertEqual("missing", workflow["stage_status"]["save"])

    def test_revalidate_preserves_explicit_manual_overrides_over_search_overlay(self):
        diagnostics = _adopt_diagnostics()
        captured_query = {}

        def fake_run_validation(service_query):
            nonlocal captured_query
            captured_query = {key: values[0] for key, values in service_query.items()}
            return diagnostics

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path),              patch.object(svc, "load_search_optimized_params", return_value=self.search_payload),              patch.object(svc, "load_runtime_optimized_params", return_value=None),              patch.object(svc, "run_validation_diagnostics", side_effect=fake_run_validation):
            result = svc.revalidate_optimizer_candidate({
                "query": {
                    "market_scope": "kospi",
                    "lookback_days": 365,
                    "stop_loss_pct": 9.0,
                    "take_profit_pct": 16.0,
                    "max_holding_days": 12,
                },
                "settings": {
                    "strategy": "수동 후보 검증",
                    "trainingDays": 180,
                    "validationDays": 60,
                    "walkForward": True,
                    "minTrades": 8,
                },
            })

        self.assertTrue(result["ok"])
        self.assertEqual("9.0", captured_query["stop_loss_pct"])
        self.assertEqual("16.0", captured_query["take_profit_pct"])
        self.assertEqual("12", captured_query["max_holding_days"])
        self.assertEqual(9.0, result["candidate"]["candidate_query"]["stop_loss_pct"])
        self.assertEqual(16.0, result["candidate"]["candidate_query"]["take_profit_pct"])
        self.assertEqual(12, result["candidate"]["candidate_query"]["max_holding_days"])
        self.assertNotIn("max_holding_days: 20 → 12", result["candidate"]["patch_lines"])
        self.assertEqual(self.search_payload["global_params"]["rsi_min"], result["candidate"]["candidate_query"]["rsi_min"])

    def test_revalidate_uses_current_saved_validation_baseline_for_sparse_payload(self):
        baseline_query = {
            "market_scope": "nasdaq",
            "lookback_days": 540,
            "initial_cash": 250000,
            "max_positions": 7,
            "max_holding_days": 27,
            "rsi_min": 41,
            "rsi_max": 69,
            "volume_ratio_min": 1.4,
            "stop_loss_pct": 4.5,
            "take_profit_pct": 16.0,
            "adx_min": 12.0,
            "mfi_min": 24.0,
            "mfi_max": 74.0,
            "bb_pct_min": 0.08,
            "bb_pct_max": 0.88,
            "stoch_k_min": 16.0,
            "stoch_k_max": 84.0,
        }
        baseline_settings = {
            "strategy": "현재 저장 전략",
            "trainingDays": 240,
            "validationDays": 80,
            "walkForward": False,
            "minTrades": 11,
            "objective": "안정성 우선",
        }
        baseline_payload = {
            "query": baseline_query,
            "settings": baseline_settings,
            "saved_at": _NOW,
        }

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None), \
             patch.object(svc, "load_persisted_validation_settings", return_value=baseline_payload), \
             patch.object(svc, "run_validation_diagnostics", return_value=_adopt_diagnostics()):
            result = svc.revalidate_optimizer_candidate({
                "query": {"market_scope": "nasdaq", "stop_loss_pct": 4.5},
                "settings": {"strategy": "현재 저장 전략", "minTrades": 11},
            })

        self.assertTrue(result["ok"])
        self.assertEqual(svc._normalize_saved_query(baseline_query), result["candidate"]["base_query"])
        self.assertEqual(svc._normalize_saved_settings(baseline_settings), result["candidate"]["settings"])
        self.assertEqual("active", result["workflow"]["latest_candidate_state"]["status"])
        self.assertTrue(result["workflow"]["latest_candidate_state"]["active"])
        self.assertNotIn("validation_settings_changed", result["workflow"]["latest_candidate_state"]["reasons"])

    def test_workflow_marks_expired_pending_handoff_as_optimizer_failed(self):
        stale_requested_at = (
            dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
        ).astimezone().isoformat(timespec="seconds")
        state = {
            "pending_search_handoff": {
                "query": {"market_scope": "kospi", "lookback_days": 365},
                "settings": {"strategy": "handoff", "trainingDays": 180, "validationDays": 60, "walkForward": True, "minTrades": 8},
                "requested_at": stale_requested_at,
                "status": "pending",
            }
        }
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "SEARCH_OPTIMIZED_PARAMS_PATH", Path(self.tmpdir.name) / "missing-search.json"), \
             patch.object(svc, "load_search_optimized_params", return_value=None), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None):
            workflow = svc.get_quant_ops_workflow()

        self.assertEqual("optimizer_failed", workflow["search_handoff"]["status"])
        self.assertEqual("optimizer_handoff_expired", workflow["search_handoff"]["error"])
        self.assertFalse(workflow["search_handoff"]["active"])

    def test_workflow_clears_pending_when_optimizer_not_running_and_search_missing(self):
        requested_at = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
        state = {
            "pending_search_handoff": {
                "query": {"market_scope": "kospi", "lookback_days": 365},
                "settings": {"strategy": "handoff", "trainingDays": 180, "validationDays": 60, "walkForward": True, "minTrades": 8},
                "requested_at": requested_at,
                "status": "pending",
            }
        }
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "SEARCH_OPTIMIZED_PARAMS_PATH", Path(self.tmpdir.name) / "missing-search.json"), \
             patch.object(svc, "load_search_optimized_params", return_value=None), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None), \
             patch.object(svc, "_optimizer_job_active", return_value=False):
            workflow = svc.get_quant_ops_workflow()

        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual("optimizer_failed", workflow["search_handoff"]["status"])
        self.assertEqual("optimizer_not_running", workflow["search_handoff"]["error"])
        self.assertFalse(workflow["search_handoff"]["active"])
        self.assertIsNone(persisted["pending_search_handoff"])

    def test_workflow_marks_pending_as_obsolete_when_search_is_older_than_request(self):
        requested_at = (
            dt.datetime.fromisoformat(_NOW).astimezone(dt.timezone.utc) + dt.timedelta(minutes=5)
        ).astimezone().isoformat(timespec="seconds")
        state = {
            "pending_search_handoff": {
                "query": {"market_scope": "kospi", "lookback_days": 365},
                "settings": {"strategy": "handoff", "trainingDays": 180, "validationDays": 60, "walkForward": True, "minTrades": 8},
                "requested_at": requested_at,
                "status": "pending",
            }
        }
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None), \
             patch.object(svc, "_optimizer_job_active", return_value=False):
            workflow = svc.get_quant_ops_workflow()

        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual("optimizer_failed", workflow["search_handoff"]["status"])
        self.assertEqual("optimizer_result_obsolete", workflow["search_handoff"]["error"])
        self.assertFalse(workflow["search_handoff"]["active"])
        self.assertIsNone(persisted["pending_search_handoff"])

    def test_medium_reliability_candidate_can_now_be_limited_adopt_when_tail_risk_is_controlled(self):
        medium_diag = _adopt_diagnostics()
        medium_diag["validation"]["segments"]["oos"].update({
            "total_return_pct": 2.78,
            "profit_factor": 1.38,
            "max_drawdown_pct": -6.09,
            "trade_count": 60,
        })
        medium_diag["validation"]["summary"].update({
            "positive_window_ratio": 1.0,
            "oos_reliability": "medium",
            "reliability_diagnostic": {
                "target_reached": True,
                "current": {
                    "label": "medium",
                    "reason": "borderline_validation_sharpe",
                    "trade_count": 60,
                    "validation_signals": 60,
                    "validation_sharpe": 0.31,
                    "max_drawdown_pct": -6.09,
                    "passes_minimum_gate": True,
                    "is_reliable": False,
                },
            },
        })
        medium_diag["validation"]["scorecard"]["tail_risk"].update({
            "expected_shortfall_5_pct": -15.45,
            "return_p05_pct": -14.8445,
        })
        medium_diag["validation"]["segments"]["oos"]["strategy_scorecard"]["tail_risk"].update({
            "expected_shortfall_5_pct": -15.45,
            "return_p05_pct": -14.8445,
        })

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None), \
             patch.object(svc, "run_validation_diagnostics", return_value=medium_diag):
            result = svc.revalidate_optimizer_candidate({
                "query": {"market_scope": "all", "lookback_days": 365},
                "settings": {"strategy": "완화된 운영 전략", "minTrades": 12},
            })

        self.assertTrue(result["ok"])
        self.assertEqual("limited_adopt", result["candidate"]["decision"]["status"])
        self.assertEqual(["expected_shortfall_5_pct"], result["candidate"]["decision"]["near_miss_metrics"])
        self.assertTrue(result["candidate"]["guardrails"]["can_save"])

    def test_limited_adopt_candidate_can_be_saved_with_probationary_metadata(self):
        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path),              patch.object(svc, "load_search_optimized_params", return_value=self.search_payload),              patch.object(svc, "load_runtime_optimized_params", return_value=None),              patch.object(svc, "run_validation_diagnostics", return_value=_limited_adopt_diagnostics()):
            result = svc.revalidate_optimizer_candidate({
                "query": {"market_scope": "kospi", "lookback_days": 365},
                "settings": {"strategy": "제한 운영 전략", "minTrades": 8},
            })
            save_result = svc.save_validated_candidate({"note": "probationary save"})

        self.assertTrue(result["ok"])
        self.assertEqual("limited_adopt", result["candidate"]["decision"]["status"])
        self.assertEqual("probationary", result["candidate"]["decision"]["approval_level"])
        self.assertEqual(
            ["profit_factor", "max_drawdown_pct"],
            result["candidate"]["decision"]["near_miss_metrics"],
        )
        self.assertTrue(result["candidate"]["guardrails"]["can_save"])
        self.assertTrue(save_result["ok"])
        self.assertEqual("limited_adopt", save_result["candidate"]["decision"]["status"])

    def test_apply_limited_adopt_runtime_clamps_risk_and_positions(self):
        execution_stub = types.ModuleType("services.execution_service")
        execution_stub.apply_quant_candidate_runtime_config = lambda candidate: {
            "ok": True,
            "state": {
                "engine_state": "stopped",
                "next_run_at": "",
                "config": {
                    "risk_per_trade_pct": 0.2,
                    "max_positions_per_market": 2,
                },
            },
        }

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path),              patch.object(svc, "load_search_optimized_params", return_value=self.search_payload),              patch.object(svc, "load_runtime_optimized_params", side_effect=lambda: self.runtime_store.get("payload") or None),              patch.object(svc, "write_runtime_optimized_params", side_effect=self._runtime_writer),              patch.object(svc, "run_validation_diagnostics", return_value=_limited_adopt_diagnostics()),              patch.dict(sys.modules, {"services.execution_service": execution_stub}):
            svc.revalidate_optimizer_candidate({
                "query": {"market_scope": "kospi", "lookback_days": 365},
                "settings": {"strategy": "제한 운영 전략", "minTrades": 8, "runtime_candidate_source_mode": "hybrid"},
            })
            save_result = svc.save_validated_candidate({"note": "limited adopt save"})
            apply_result = svc.apply_saved_candidate_to_runtime({})

        self.assertTrue(save_result["ok"])
        self.assertTrue(apply_result["ok"])
        self.assertEqual("limited_adopt", self.runtime_store["payload"]["meta"]["decision_status"])
        self.assertEqual("probationary", self.runtime_store["payload"]["meta"]["approval_level"])
        self.assertTrue(self.runtime_store["payload"]["runtime_restrictions"]["enabled"])
        self.assertEqual(2, self.runtime_store["payload"]["runtime_restrictions"]["max_positions_per_market_cap"])
        self.assertEqual(0.2, self.runtime_store["payload"]["runtime_restrictions"]["risk_per_trade_pct_cap"])
        self.assertEqual("probationary", self.runtime_store["payload"]["validation_baseline"]["approval_level"])
        self.assertEqual("runtime", apply_result["workflow"]["runtime_apply"]["effective_source"])

    def test_save_blocks_when_revalidation_failed_guardrails(self):
        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None), \
             patch.object(svc, "run_validation_diagnostics", return_value=_reject_diagnostics()):
            svc.revalidate_optimizer_candidate({
                "query": {"market_scope": "kospi", "lookback_days": 365},
                "settings": {"strategy": "실패 전략", "minTrades": 8},
            })
            result = svc.save_validated_candidate({})

        self.assertFalse(result["ok"])
        self.assertEqual("save_guardrail_blocked", result["error"])
        self.assertEqual("reject", result["candidate"]["decision"]["status"])
        self.assertFalse(result["candidate"]["guardrails"]["can_save"])
        self.assertTrue(result["candidate"]["guardrails"]["reasons"])

    def test_candidate_guardrails_synthesize_reason_when_hold_blocks_without_hard_failures(self):
        decision, guardrails = svc._candidate_decision(
            {
                "trade_count": 12,
                "reliability": "high",
                "profit_factor": 1.02,
                "oos_return_pct": 0.5,
                "max_drawdown_pct": -12.0,
                "positive_window_ratio": 0.4,
                "expected_shortfall_5_pct": -10.0,
            },
            min_trades=8,
            search_is_stale=False,
            search_version_changed=False,
        )

        self.assertEqual("hold", decision["status"])
        self.assertFalse(guardrails["can_save"])
        self.assertEqual(["decision_hold"], guardrails["reasons"])

    def test_hold_candidate_cannot_become_runtime_effective_via_search_fallback(self):
        hold_diag = _adopt_diagnostics()
        hold_diag["validation"]["segments"]["oos"].update({
            "total_return_pct": 0.5,
            "profit_factor": 1.02,
            "max_drawdown_pct": -12.0,
        })
        hold_diag["validation"]["summary"].update({
            "positive_window_ratio": 0.4,
        })
        hold_diag["validation"]["scorecard"]["tail_risk"].update({
            "expected_shortfall_5_pct": -10.0,
        })

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None), \
             patch.object(svc, "run_validation_diagnostics", return_value=hold_diag):
            revalidate_result = svc.revalidate_optimizer_candidate({
                "query": {"market_scope": "kospi", "lookback_days": 365},
                "settings": {"strategy": "운영 전략", "minTrades": 8},
            })
            workflow = svc.get_quant_ops_workflow()

        self.assertTrue(revalidate_result["ok"])
        self.assertEqual("hold", revalidate_result["candidate"]["decision"]["status"])
        self.assertFalse(revalidate_result["candidate"]["guardrails"]["can_apply"])
        self.assertEqual("missing", workflow["stage_status"]["runtime_apply"])
        self.assertEqual("search", workflow["runtime_apply"]["effective_source"])
        self.assertFalse(workflow["runtime_apply"]["available"])

    def test_apply_runtime_writes_runtime_overlay_and_updates_state(self):
        execution_stub = types.ModuleType("services.execution_service")
        execution_stub.apply_quant_candidate_runtime_config = lambda candidate: {
            "ok": True,
            "state": {
                "engine_state": "stopped",
                "next_run_at": "",
                "config": {"stop_loss_pct": candidate.get("patch", {}).get("stop_loss_pct")},
            },
        }

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", side_effect=lambda: self.runtime_store.get("payload") or None), \
             patch.object(svc, "write_runtime_optimized_params", side_effect=self._runtime_writer), \
             patch.object(svc, "run_validation_diagnostics", return_value=_adopt_diagnostics()), \
             patch.dict(sys.modules, {"services.execution_service": execution_stub}):
            svc.revalidate_optimizer_candidate({
                "query": {"market_scope": "kospi", "lookback_days": 365, "stop_loss_pct": 5.0},
                "settings": {"strategy": "운영 전략", "minTrades": 8, "runtime_candidate_source_mode": "hybrid"},
            })
            save_result = svc.save_validated_candidate({"note": "operator 승인"})
            apply_result = svc.apply_saved_candidate_to_runtime({})

        self.assertTrue(save_result["ok"])
        self.assertTrue(apply_result["ok"])
        self.assertEqual("runtime", apply_result["workflow"]["runtime_apply"]["effective_source"])
        self.assertEqual("applied", apply_result["workflow"]["runtime_apply"]["status"])
        self.assertTrue(self.runtime_store["payload"])
        self.assertEqual("validated_candidate", self.runtime_store["payload"]["meta"]["global_overlay_source"])
        self.assertEqual(save_result["candidate"]["id"], self.runtime_store["payload"]["meta"]["applied_candidate_id"])
        self.assertEqual("hybrid", self.runtime_store["payload"]["meta"]["runtime_candidate_source_mode"])
        self.assertEqual("hybrid", apply_result["workflow"]["runtime_apply"]["runtime_candidate_source_mode"])
        self.assertEqual("validated_candidate", self.runtime_store["payload"]["meta"]["validation_baseline_source"])
        self.assertEqual(18, self.runtime_store["payload"]["validation_baseline"]["validation_trades"])
        self.assertAlmostEqual(0.93, self.runtime_store["payload"]["validation_baseline"]["validation_sharpe"])

    def test_apply_quant_only_runtime_without_symbol_candidates(self):
        execution_stub = types.ModuleType("services.execution_service")
        execution_stub.apply_quant_candidate_runtime_config = lambda candidate: {
            "ok": True,
            "state": {
                "engine_state": "stopped",
                "next_run_at": "",
                "config": {},
            },
        }

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", side_effect=lambda: self.runtime_store.get("payload") or None), \
             patch.object(svc, "write_runtime_optimized_params", side_effect=self._runtime_writer), \
             patch.object(svc, "run_validation_diagnostics", return_value=_adopt_diagnostics()), \
             patch.dict(sys.modules, {"services.execution_service": execution_stub}):
            svc.revalidate_optimizer_candidate({
                "query": {"market_scope": "kospi", "lookback_days": 365},
                "settings": {"strategy": "운영 전략", "minTrades": 8, "runtime_candidate_source_mode": "quant_only"},
            })
            save_result = svc.save_validated_candidate({"note": "operator 승인"})
            apply_result = svc.apply_saved_candidate_to_runtime({})

        self.assertTrue(save_result["ok"])
        self.assertTrue(apply_result["ok"])
        self.assertEqual("runtime", apply_result["workflow"]["runtime_apply"]["effective_source"])
        self.assertTrue(self.runtime_store["payload"])

    def test_policy_override_can_promote_candidate_to_full_adopt(self):
        custom_policy = {
            "policy": {
                "version": 7,
                "thresholds": {
                    "reject": {
                        "blocked_reliability_levels": ["insufficient", "low"],
                        "min_profit_factor": 0.95,
                        "min_oos_return_pct": -2.0,
                        "max_drawdown_pct": 30.0,
                        "min_expected_shortfall_5_pct": -20.0,
                    },
                    "adopt": {
                        "required_reliability": "high",
                        "min_oos_return_pct": 0.0,
                        "min_profit_factor": 1.04,
                        "max_drawdown_pct": 23.0,
                        "min_positive_window_ratio": 0.55,
                        "min_expected_shortfall_5_pct": -13.0,
                    },
                    "limited_adopt": {
                        "allowed_reliability_levels": ["high", "medium"],
                        "min_oos_return_pct": 0.0,
                        "min_profit_factor": 1.0,
                        "max_drawdown_pct": 25.0,
                        "min_positive_window_ratio": 0.45,
                        "min_expected_shortfall_5_pct": -16.0,
                        "min_near_miss_count": 1,
                        "max_near_miss_count": 2,
                    },
                    "limited_adopt_runtime": {
                        "risk_per_trade_pct_multiplier": 0.5,
                        "risk_per_trade_pct_cap": 0.2,
                        "max_positions_per_market_cap": 2,
                        "max_symbol_weight_pct_cap": 10.0,
                        "max_market_exposure_pct_cap": 35.0,
                    },
                },
            },
            "saved_at": _NOW,
            "source": str(Path(self.tmpdir.name) / "quant_guardrail_policy.json"),
        }

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", return_value=None), \
             patch.object(svc, "load_quant_guardrail_policy", return_value=custom_policy), \
             patch.object(svc, "run_validation_diagnostics", return_value=_limited_adopt_diagnostics()):
            result = svc.revalidate_optimizer_candidate({
                "query": {"market_scope": "kospi", "lookback_days": 365},
                "settings": {"strategy": "정책 완화 전략", "minTrades": 8},
            })

        self.assertTrue(result["ok"])
        self.assertEqual("adopt", result["candidate"]["decision"]["status"])
        self.assertEqual(7, result["candidate"]["guardrail_policy"]["version"])
        self.assertEqual(7, result["workflow"]["guardrail_policy"]["version"])

    def test_apply_runtime_includes_guardrail_policy_snapshot(self):
        execution_stub = types.ModuleType("services.execution_service")
        execution_stub.apply_quant_candidate_runtime_config = lambda candidate: {
            "ok": True,
            "state": {
                "engine_state": "stopped",
                "next_run_at": "",
                "config": {},
            },
        }
        custom_policy = {
            "policy": {
                "version": 9,
                "thresholds": {
                    "reject": {
                        "blocked_reliability_levels": ["insufficient", "low"],
                        "min_profit_factor": 0.95,
                        "min_oos_return_pct": -2.0,
                        "max_drawdown_pct": 30.0,
                        "min_expected_shortfall_5_pct": -20.0,
                    },
                    "adopt": {
                        "required_reliability": "high",
                        "min_oos_return_pct": 0.0,
                        "min_profit_factor": 1.08,
                        "max_drawdown_pct": 22.0,
                        "min_positive_window_ratio": 0.5,
                        "min_expected_shortfall_5_pct": -15.0,
                    },
                    "limited_adopt": {
                        "allowed_reliability_levels": ["high", "medium"],
                        "min_oos_return_pct": 0.0,
                        "min_profit_factor": 1.0,
                        "max_drawdown_pct": 25.0,
                        "min_positive_window_ratio": 0.45,
                        "min_expected_shortfall_5_pct": -16.0,
                        "min_near_miss_count": 1,
                        "max_near_miss_count": 2,
                    },
                    "limited_adopt_runtime": {
                        "risk_per_trade_pct_multiplier": 0.4,
                        "risk_per_trade_pct_cap": 0.15,
                        "max_positions_per_market_cap": 1,
                        "max_symbol_weight_pct_cap": 8.0,
                        "max_market_exposure_pct_cap": 25.0,
                    },
                },
            },
            "saved_at": _NOW,
            "source": str(Path(self.tmpdir.name) / "quant_guardrail_policy.json"),
        }

        with patch.object(svc, "_QUANT_OPS_STATE_PATH", self.state_path), \
             patch.object(svc, "load_search_optimized_params", return_value=self.search_payload), \
             patch.object(svc, "load_runtime_optimized_params", side_effect=lambda: self.runtime_store.get("payload") or None), \
             patch.object(svc, "write_runtime_optimized_params", side_effect=self._runtime_writer), \
             patch.object(svc, "load_quant_guardrail_policy", return_value=custom_policy), \
             patch.object(svc, "run_validation_diagnostics", return_value=_limited_adopt_diagnostics()), \
             patch.dict(sys.modules, {"services.execution_service": execution_stub}):
            svc.revalidate_optimizer_candidate({
                "query": {"market_scope": "kospi", "lookback_days": 365},
                "settings": {"strategy": "제한 운영 전략", "minTrades": 8, "runtime_candidate_source_mode": "hybrid"},
            })
            svc.save_validated_candidate({"note": "policy snapshot save"})
            apply_result = svc.apply_saved_candidate_to_runtime({})

        self.assertTrue(apply_result["ok"])
        self.assertEqual(9, self.runtime_store["payload"]["guardrail_policy"]["version"])
        self.assertEqual(9, self.runtime_store["payload"]["meta"]["guardrail_policy_version"])
        self.assertEqual(0.15, self.runtime_store["payload"]["runtime_restrictions"]["risk_per_trade_pct_cap"])


if __name__ == "__main__":
    unittest.main()
