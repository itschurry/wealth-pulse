from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.sizing_service import recommend_position_size


class SizingServiceTests(unittest.TestCase):
    def test_recommend_position_size_reports_risk_budget_limit_when_risk_qty_is_zero(self):
        result = recommend_position_size(
            account={
                "equity_krw": 25_219_000.0,
                "cash_krw": 10_000_000.0,
                "cash_usd": 10_000.0,
                "fx_rate": 1522.0,
            },
            market="KOSPI",
            unit_price_local=445_500.0,
            stop_loss_pct=9.0,
            expected_value=1.2023,
            reliability="insufficient",
            risk_guard_state={
                "exposure_caps": {
                    "max_symbol_weight_pct": 10.0,
                    "max_sector_weight_pct": 35.0,
                    "max_market_exposure_pct": 35.0,
                },
                "exposure": {
                    "equity_krw": 25_219_000.0,
                    "market_pct": {},
                    "symbol_pct": {},
                    "sector_pct": {},
                },
            },
            cfg={"risk_per_trade_pct": 0.175},
            symbol_key="KOSPI:000810",
            sector="미분류",
        )

        self.assertEqual(0, result["quantity"])
        self.assertEqual("risk_budget_limit", result["reason"])
        self.assertEqual(0, result["qty_by_risk"])
        self.assertGreater(result["qty_by_cash"], 0)
        self.assertGreater(result["qty_by_caps"], 0)


if __name__ == "__main__":
    unittest.main()
