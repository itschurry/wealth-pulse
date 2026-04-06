from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import execution_service as execution_svc
from services import optimized_params_store as optimized_store
from services import strategy_engine as strategy_svc


class OptimizedParamsExecutionApprovalTests(unittest.TestCase):
    def test_execution_loader_ignores_unapproved_search_payload(self):
        search_payload = {
            "optimized_at": "2026-04-01T21:00:00+09:00",
            "global_params": {"stop_loss_pct": 2.0, "take_profit_pct": 40.0},
            "meta": {"global_overlay_source": "all_results_fallback"},
        }

        with patch.object(optimized_store, "load_runtime_optimized_params", return_value=None), \
             patch.object(optimized_store, "load_search_optimized_params", return_value=search_payload):
            self.assertIsNone(optimized_store.load_execution_optimized_params())

    def test_execution_loader_prefers_runtime_validated_payload(self):
        runtime_payload = {
            "optimized_at": "2026-04-01T22:00:00+09:00",
            "global_params": {"stop_loss_pct": 6.0, "take_profit_pct": 18.0},
            "meta": {
                "global_overlay_source": "validated_candidate",
                "applied_candidate_id": "cand-001",
                "applied_from": "quant_ops_saved_candidate",
            },
        }
        search_payload = {
            "optimized_at": "2026-04-01T21:00:00+09:00",
            "global_params": {"stop_loss_pct": 2.0, "take_profit_pct": 40.0},
            "meta": {"global_overlay_source": "all_results_fallback"},
        }

        with patch.object(optimized_store, "load_runtime_optimized_params", return_value=runtime_payload), \
             patch.object(optimized_store, "load_search_optimized_params", return_value=search_payload):
            loaded = optimized_store.load_execution_optimized_params()

        self.assertEqual(runtime_payload, loaded)


class RuntimeValidationGateTests(unittest.TestCase):
    def test_validation_gate_falls_back_to_runtime_global_baseline(self):
        signal = {
            "code": "005930",
            "validation_snapshot": {
                "trade_count": 0,
                "validation_trades": 0,
                "validation_sharpe": 0.0,
                "strategy_reliability": "insufficient",
            },
            "ev_metrics": {},
        }
        cfg = {
            "validation_gate_enabled": True,
            "validation_min_trades": 8,
            "validation_min_sharpe": 0.8,
            "validation_block_on_low_reliability": True,
            "validation_require_optimized_reliability": True,
        }
        optimized_payload = {
            "global_params": {"stop_loss_pct": 6.0},
            "validation_baseline": {
                "trade_count": 18,
                "validation_trades": 18,
                "validation_sharpe": 0.93,
                "max_drawdown_pct": -12.4,
                "strategy_reliability": "high",
                "reliability_reason": "validated_candidate",
                "passes_minimum_gate": True,
                "is_reliable": True,
            },
            "per_symbol": {},
        }

        with patch.object(execution_svc, "_load_optimized_params", return_value=optimized_payload):
            allowed, reasons, meta = execution_svc._apply_validation_gate(signal, cfg)

        self.assertTrue(allowed)
        self.assertEqual([], reasons)
        self.assertEqual("global", meta["source"])
        self.assertEqual(18, meta["trades"])
        self.assertAlmostEqual(0.93, meta["sharpe"])
        self.assertEqual("high", meta["reliability"])

    def test_validation_gate_ignores_unreliable_symbol_snapshot_when_global_baseline_exists(self):
        signal = {
            "code": "000810",
            "validation_snapshot": {
                "trade_count": 0,
                "validation_trades": 0,
                "validation_sharpe": 0.0,
                "strategy_reliability": "insufficient",
            },
            "ev_metrics": {},
        }
        cfg = {
            "validation_gate_enabled": True,
            "validation_min_trades": 8,
            "validation_min_sharpe": 0.2,
            "validation_block_on_low_reliability": True,
            "validation_require_optimized_reliability": True,
        }
        optimized_payload = {
            "validation_baseline": {
                "trade_count": 61,
                "validation_trades": 61,
                "validation_sharpe": 0.4,
                "max_drawdown_pct": -7.28,
                "strategy_reliability": "high",
                "reliability_reason": "validated_candidate",
                "passes_minimum_gate": True,
                "is_reliable": True,
            },
            "per_symbol": {
                "000810": {
                    "trade_count": 79,
                    "validation_trades": 6,
                    "validation_sharpe": 0.0,
                    "max_drawdown_pct": -17.8626,
                    "strategy_reliability": "insufficient",
                    "reliability_reason": "insufficient_validation_signals",
                    "passes_minimum_gate": False,
                    "is_reliable": False,
                }
            },
        }

        with patch.object(execution_svc, "_load_optimized_params", return_value=optimized_payload):
            allowed, reasons, meta = execution_svc._apply_validation_gate(signal, cfg)

        self.assertTrue(allowed)
        self.assertEqual([], reasons)
        self.assertEqual("global", meta["source"])
        self.assertEqual(61, meta["trades"])
        self.assertAlmostEqual(0.4, meta["sharpe"])
        self.assertEqual("high", meta["reliability"])


class StrategyEngineRuntimePathTests(unittest.TestCase):
    def test_build_signal_book_attaches_layer_c_metadata_for_runtime_candidates(self):
        candidate = {
            "code": "000810",
            "name": "삼성화재",
            "market": "KOSPI",
            "sector": "보험",
            "score": 33.02,
            "confidence": 50.0,
            "price": 445000.0,
            "technical_snapshot": {
                "current_price": 445000.0,
                "volume_ratio": 1.0,
                "atr14_pct": 0.8,
            },
            "reasons": ["volume_breakout"],
            "gate_status": "passed",
            "gate_reasons": [],
            "ai_thesis": "runtime quant validated candidate",
        }
        optimized_payload = {
            "validation_baseline": {
                "trade_count": 61,
                "validation_trades": 61,
                "validation_sharpe": 0.4,
                "max_drawdown_pct": -7.28,
                "strategy_reliability": "high",
                "reliability_reason": "validated_candidate",
                "passes_minimum_gate": True,
                "is_reliable": True,
                "stop_loss_pct": 11.0,
                "composite_score": 3.77,
            },
            "per_symbol": {},
        }

        with patch.object(strategy_svc, "collect_pick_candidates", return_value=[candidate]), \
             patch.object(strategy_svc, "_context_snapshot", return_value=("neutral", "중간")), \
             patch.object(strategy_svc, "_load_optimized_params", return_value=optimized_payload), \
             patch.object(strategy_svc, "build_risk_guard_state", return_value={"entry_allowed": True, "reasons": []}), \
             patch.object(strategy_svc, "determine_strategy_type", return_value="mean-reversion"), \
             patch.object(strategy_svc, "allocator_weight", return_value={"enabled": True}), \
             patch.object(
                 strategy_svc,
                 "compute_ev_metrics",
                 return_value={
                     "expected_value": 1.2023,
                     "reliability": "high",
                     "reliability_detail": {
                         "label": "high",
                         "reason": "validated_candidate",
                         "passes_minimum_gate": True,
                         "is_reliable": True,
                     },
                     "calibration": {},
                 },
             ), \
             patch.object(strategy_svc, "recommend_position_size", return_value={"quantity": 1, "reason": "ok"}), \
             patch.object(
                 strategy_svc,
                 "build_layer_c_snapshot",
                 return_value={
                     "layer": "C",
                     "provider": "openclaw",
                     "provider_status": "healthy",
                     "research_unavailable": False,
                     "research_score": 0.68,
                     "components": {"freshness_score": 0.96},
                     "warnings": ["already_extended_intraday"],
                     "tags": ["insurance"],
                     "summary": "layer c attached",
                     "ttl_minutes": 120,
                     "generated_at": "2026-04-03T10:31:00+09:00",
                 },
             ):
            book = strategy_svc.build_signal_book(
                markets=["KOSPI"],
                cfg={},
                account={"equity_krw": 25_223_000, "cash_krw": 10_000_000, "orders": [], "positions": [], "fx_rate": 1522.3},
            )

        signal = book["signals"][0]
        self.assertEqual("openclaw", signal["candidate_research_source"])
        self.assertEqual("healthy", signal["research_status"])
        self.assertFalse(signal["research_unavailable"])
        self.assertAlmostEqual(0.68, signal["research_score"])
        self.assertIsInstance(signal["layer_events"], list)
        self.assertTrue(any(item.get("layer") == "C" for item in signal["layer_events"]))

    def test_build_signal_book_falls_back_to_global_validation_when_symbol_overlay_is_unreliable(self):
        candidate = {
            "code": "000810",
            "name": "삼성화재",
            "market": "KOSPI",
            "sector": "미분류",
            "score": 33.02,
            "confidence": 50.0,
            "price": 445000.0,
            "technical_snapshot": {
                "current_price": 445000.0,
                "volume_avg20": 119978,
                "volume_ratio": 1.0,
                "atr14_pct": 0.8,
            },
            "reasons": [],
            "risks": [],
            "gate_status": "passed",
            "gate_reasons": [],
            "ai_thesis": "runtime quant validated candidate",
        }
        optimized_payload = {
            "validation_baseline": {
                "trade_count": 61,
                "validation_trades": 61,
                "validation_sharpe": 0.4,
                "max_drawdown_pct": -7.28,
                "strategy_reliability": "high",
                "reliability_reason": "validated_candidate",
                "passes_minimum_gate": True,
                "is_reliable": True,
                "stop_loss_pct": 11.0,
                "composite_score": 3.77,
            },
            "per_symbol": {
                "000810": {
                    "trade_count": 79,
                    "validation_trades": 6,
                    "validation_sharpe": 0.0,
                    "max_drawdown_pct": -17.8626,
                    "strategy_reliability": "insufficient",
                    "reliability_reason": "insufficient_validation_signals",
                    "passes_minimum_gate": False,
                    "is_reliable": False,
                    "stop_loss_pct": 9.0,
                    "composite_score": 33.02,
                }
            },
        }

        with patch.object(strategy_svc, "collect_pick_candidates", return_value=[candidate]), \
             patch.object(strategy_svc, "_context_snapshot", return_value=("neutral", "중간")), \
             patch.object(strategy_svc, "_load_optimized_params", return_value=optimized_payload), \
             patch.object(strategy_svc, "build_risk_guard_state", return_value={"entry_allowed": True, "reasons": []}), \
             patch.object(strategy_svc, "determine_strategy_type", return_value="mean-reversion"), \
             patch.object(strategy_svc, "allocator_weight", return_value={"enabled": True}), \
             patch.object(
                 strategy_svc,
                 "compute_ev_metrics",
                 return_value={
                     "expected_value": 1.2023,
                     "reliability": "high",
                     "reliability_detail": {
                         "label": "high",
                         "reason": "validated_candidate",
                         "passes_minimum_gate": True,
                         "is_reliable": True,
                     },
                     "calibration": {},
                 },
             ), \
             patch.object(strategy_svc, "recommend_position_size", return_value={"quantity": 1, "reason": "ok"}):
            book = strategy_svc.build_signal_book(
                markets=["KOSPI"],
                cfg={},
                account={"equity_krw": 25_223_000, "cash_krw": 10_000_000, "orders": [], "positions": [], "fx_rate": 1522.3},
            )

        signal = book["signals"][0]
        self.assertEqual("global", signal["validation_snapshot"]["validation_source"])
        self.assertEqual(61, signal["validation_snapshot"]["validation_trades"])
        self.assertAlmostEqual(11.0, signal["risk_inputs"]["stop_loss_pct"])
        self.assertTrue(signal["entry_allowed"])

    def test_build_signal_book_uses_global_validation_baseline_and_technical_snapshot(self):
        candidate = {
            "code": "005930",
            "name": "삼성전자",
            "market": "KOSPI",
            "sector": "반도체",
            "score": 78.0,
            "confidence": 82.0,
            "technical_snapshot": {
                "current_price": 71200,
                "volume_avg20": 2500000,
                "volume_ratio": 1.5,
                "atr14_pct": 1.8,
            },
            "reasons": ["volume_breakout"],
            "risks": ["earnings_week"],
            "gate_status": "passed",
            "gate_reasons": [],
            "ai_thesis": "테마/수급/기술 조건이 동시에 맞음",
        }
        optimized_payload = {
            "validation_baseline": {
                "trade_count": 18,
                "validation_trades": 18,
                "validation_sharpe": 0.93,
                "max_drawdown_pct": -12.4,
                "strategy_reliability": "high",
                "reliability_reason": "validated_candidate",
                "passes_minimum_gate": True,
                "is_reliable": True,
                "composite_score": 32.0,
            },
            "per_symbol": {},
        }

        with patch.object(strategy_svc, "collect_pick_candidates", return_value=[candidate]), \
             patch.object(strategy_svc, "_context_snapshot", return_value=("neutral", "중간")), \
             patch.object(strategy_svc, "_load_optimized_params", return_value=optimized_payload), \
             patch.object(strategy_svc, "build_risk_guard_state", return_value={"entry_allowed": True, "reasons": []}), \
             patch.object(strategy_svc, "determine_strategy_type", return_value="trend"), \
             patch.object(strategy_svc, "allocator_weight", return_value={"enabled": True}), \
             patch.object(
                 strategy_svc,
                 "compute_ev_metrics",
                 return_value={
                     "expected_value": 1.24,
                     "reliability": "high",
                     "reliability_detail": {
                         "label": "high",
                         "reason": "validated_candidate",
                         "passes_minimum_gate": True,
                         "is_reliable": True,
                     },
                     "calibration": {},
                 },
             ), \
             patch.object(strategy_svc, "recommend_position_size", return_value={"quantity": 1, "reason": "ok"}):
            book = strategy_svc.build_signal_book(
                markets=["KOSPI"],
                cfg={},
                account={"equity_krw": 10_000_000, "orders": [], "positions": [], "fx_rate": 1300.0},
            )

        self.assertEqual(1, book["count"])
        signal = book["signals"][0]
        self.assertTrue(signal["entry_allowed"])
        self.assertEqual("ok", signal["execution_realism"]["liquidity_gate_status"])
        self.assertEqual("global", signal["validation_snapshot"]["validation_source"])
        self.assertEqual(18, signal["validation_snapshot"]["validation_trades"])
        self.assertAlmostEqual(0.93, signal["validation_snapshot"]["validation_sharpe"])
        self.assertEqual("high", signal["validation_snapshot"]["strategy_reliability"])


if __name__ == "__main__":
    unittest.main()
