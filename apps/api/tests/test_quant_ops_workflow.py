from __future__ import annotations

import datetime as dt
import json
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
            })

        self.assertTrue(result["ok"])
        candidate = result["candidate"]
        self.assertEqual("optimizer_global_overlay", candidate["source"])
        self.assertEqual("adopt", candidate["decision"]["status"])
        self.assertTrue(candidate["guardrails"]["can_save"])
        self.assertIn("stop_loss_pct: 5.0 → 6.0", candidate["patch_lines"])
        self.assertEqual(18, candidate["candidate_query"]["max_holding_days"])
        self.assertTrue(result["workflow"]["search_result"]["available"])
        self.assertEqual("adopt", result["workflow"]["stage_status"]["revalidation"])
        self.assertTrue(self.state_path.exists())
        self.assertIn("symbol_candidates", result["workflow"])

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
                "settings": {"strategy": "운영 전략", "minTrades": 8},
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
        self.assertEqual("validated_candidate", self.runtime_store["payload"]["meta"]["validation_baseline_source"])
        self.assertEqual(18, self.runtime_store["payload"]["validation_baseline"]["validation_trades"])
        self.assertAlmostEqual(0.93, self.runtime_store["payload"]["validation_baseline"]["validation_sharpe"])

    def test_symbol_candidate_requires_approval_then_saved_and_applied(self):
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
                "query": {"market_scope": "kospi", "lookback_days": 365},
                "settings": {"strategy": "운영 전략", "minTrades": 8},
            })
            revalidate_symbol = svc.revalidate_symbol_candidate({
                "symbol": "AAA",
                "query": {"market_scope": "kospi", "lookback_days": 365},
                "settings": {"strategy": "운영 전략", "minTrades": 8},
            })
            blocked_save = svc.save_symbol_candidate({"symbol": "AAA"})
            approval = svc.set_symbol_candidate_approval({"symbol": "AAA", "status": "approved", "note": "operator ok"})
            saved_symbol = svc.save_symbol_candidate({"symbol": "AAA"})
            saved_global = svc.save_validated_candidate({"note": "global 저장"})
            apply_result = svc.apply_saved_candidate_to_runtime({})

        self.assertTrue(revalidate_symbol["ok"])
        self.assertFalse(blocked_save["ok"])
        self.assertEqual("symbol_save_guardrail_blocked", blocked_save["error"])
        self.assertIn("operator_approval_required", blocked_save["guardrails"]["reasons"])
        self.assertTrue(approval["ok"])
        self.assertEqual("approved", approval["approval"]["status"])
        self.assertTrue(saved_symbol["ok"])
        self.assertEqual("AAA", saved_symbol["symbol"])
        self.assertTrue(saved_global["ok"])
        self.assertTrue(apply_result["ok"])
        self.assertEqual(1, self.runtime_store["payload"]["meta"]["approved_symbol_count"])
        self.assertEqual(["AAA"], self.runtime_store["payload"]["meta"]["approved_symbols"])
        self.assertIn("AAA", self.runtime_store["payload"]["per_symbol"])
        self.assertNotIn("BBB", self.runtime_store["payload"]["per_symbol"])
        workflow = apply_result["workflow"]
        self.assertEqual("applied", workflow["stage_status"]["symbol_runtime_apply"])
        self.assertEqual(1, workflow["symbol_summary"]["runtime_applied_count"])


if __name__ == "__main__":
    unittest.main()
