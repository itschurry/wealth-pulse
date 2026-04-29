from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.regime_service import build_market_regime_snapshot


class RegimeServiceTests(unittest.TestCase):
    def test_market_regime_snapshot_aggregates_normalized_price_ratios(self):
        snapshot = build_market_regime_snapshot([
            {
                "close": 1100.0,
                "current_price": 1100.0,
                "trade_price": 1100.0,
                "sma20": 1000.0,
                "sma60": 900.0,
                "volume_ratio": 1.0,
                "rsi14": 55.0,
                "atr14_pct": 1.0,
            },
            {
                "close": 10.0,
                "current_price": 10.0,
                "trade_price": 10.0,
                "sma20": 20.0,
                "sma60": 30.0,
                "volume_ratio": 1.0,
                "rsi14": 55.0,
                "atr14_pct": 1.0,
            },
        ], market="KOSPI")

        self.assertEqual("market_regime_aggregate", snapshot["source"])
        self.assertEqual(2, snapshot["sample_count"])
        self.assertAlmostEqual((1100.0 / 900.0 + 10.0 / 30.0) / 2.0, snapshot["close_sma60_ratio"], places=6)
        self.assertAlmostEqual((1000.0 / 900.0 + 20.0 / 30.0) / 2.0, snapshot["sma20_sma60_ratio"], places=6)
        self.assertAlmostEqual((1100.0 / 1000.0 + 10.0 / 20.0) / 2.0, snapshot["close_sma20_ratio"], places=6)
        self.assertAlmostEqual(snapshot["close_sma60_ratio"] * 100.0, snapshot["close"], places=6)
        self.assertAlmostEqual(snapshot["sma20_sma60_ratio"] * 100.0, snapshot["sma20"], places=6)
        self.assertEqual(100.0, snapshot["sma60"])
        self.assertLess(snapshot["close"], snapshot["sma20"])


if __name__ == "__main__":
    unittest.main()
