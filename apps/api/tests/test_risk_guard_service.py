from __future__ import annotations

import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from services.risk_guard_service import build_risk_guard_state


class RiskGuardServiceTests(unittest.TestCase):
    def test_total_drawdown_blocks_new_entries(self) -> None:
        state = build_risk_guard_state(
            account={"equity_krw": 3_750_000, "positions": [], "orders": []},
            cfg={
                "performance_starting_equity_krw": 5_000_000,
                "max_total_drawdown_pct": 10.0,
            },
            regime="neutral",
            risk_level="normal",
        )

        self.assertFalse(state["entry_allowed"])
        self.assertIn("total_drawdown_limit_reached", state["reasons"])
        self.assertEqual(state["total_drawdown_pct"], 25.0)

    def test_total_drawdown_below_limit_allows_entry(self) -> None:
        state = build_risk_guard_state(
            account={"equity_krw": 4_750_000, "positions": [], "orders": []},
            cfg={
                "performance_starting_equity_krw": 5_000_000,
                "max_total_drawdown_pct": 10.0,
            },
            regime="neutral",
            risk_level="normal",
        )

        self.assertTrue(state["entry_allowed"])
        self.assertNotIn("total_drawdown_limit_reached", state["reasons"])


if __name__ == "__main__":
    unittest.main()
