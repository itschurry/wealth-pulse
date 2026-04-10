from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

if "holidays" not in sys.modules:
    sys.modules["holidays"] = types.SimpleNamespace(KR=lambda *args, **kwargs: set(), US=lambda *args, **kwargs: set())

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routes import market as market_route


class MarketRouteTests(unittest.TestCase):
    def test_build_market_uses_yahoo_for_nasdaq_index(self):
        def fake_yahoo_chart(symbol: str):
            if symbol == "^IXIC":
                return 22822.42, 0.83
            if symbol == "^OEX":
                return 3333.40, 0.82
            raise AssertionError(f"unexpected yahoo symbol: {symbol}")

        with patch.object(market_route, "_naver_index", side_effect=[(5858.87, 1.4), (1093.63, 1.64)]), \
             patch.object(market_route, "_usd_krw", return_value=1483.2), \
             patch.object(market_route, "_yahoo_chart", side_effect=fake_yahoo_chart) as yahoo_mock, \
             patch.object(market_route, "_stooq_spot", return_value=(98.0, 0.13)):
            payload = market_route._build_market()

        self.assertEqual(22822.42, payload["nasdaq"])
        self.assertEqual(0.83, payload["nasdaq_pct"])
        self.assertNotIn("nasdaq_err", payload)
        self.assertEqual([("^OEX",), ("^IXIC",)], [call.args for call in yahoo_mock.call_args_list])


if __name__ == "__main__":
    unittest.main()
