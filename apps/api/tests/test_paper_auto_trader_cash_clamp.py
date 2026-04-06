from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from broker.execution_engine import EngineConfig, PaperExecutionEngine


class PaperExecutionCashClampTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmpdir.name) / "paper_state.json"

        def quote_provider(code: str, market: str) -> dict:
            return {
                "price": 100.0,
                "name": code,
                "market": market,
                "volume": 1_000_000,
                "volume_avg20": 1_000_000,
                "source": "test",
                "fetched_at": "2026-04-01T00:00:00+00:00",
                "is_stale": False,
            }

        self.engine = PaperExecutionEngine(
            config=EngineConfig(
                state_path=self.state_path,
                default_initial_cash_krw=0.0,
                default_initial_cash_usd=0.0,
                default_paper_days=7,
            ),
            quote_provider=quote_provider,
            fx_provider=lambda: 1300.0,
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_sequential_buys_clamp_second_order_to_affordable_quantity(self):
        self.engine.reset(initial_cash_krw=1000.0, initial_cash_usd=0.0, paper_days=7)

        first = self.engine.place_order(
            side="buy",
            code="AAA",
            market="KOSPI",
            quantity=7,
            order_type="market",
        )
        second = self.engine.place_order(
            side="buy",
            code="BBB",
            market="KOSPI",
            quantity=4,
            order_type="market",
        )

        self.assertTrue(first.get("ok"))
        self.assertTrue(second.get("ok"))
        self.assertEqual(7, (first.get("event") or {}).get("quantity"))
        self.assertEqual(2, (second.get("event") or {}).get("quantity"))

        account = self.engine.get_account(refresh_quotes=False)
        self.assertEqual(2, len(account.get("positions", [])))
        self.assertEqual(99.14, account.get("cash_krw"))

    def test_buy_fails_cleanly_when_even_one_share_is_unaffordable(self):
        self.engine.reset(initial_cash_krw=50.0, initial_cash_usd=0.0, paper_days=7)

        result = self.engine.place_order(
            side="buy",
            code="AAA",
            market="KOSPI",
            quantity=3,
            order_type="market",
        )

        self.assertFalse(result.get("ok"))
        self.assertEqual("원화 주문 가능 현금이 부족합니다.", result.get("error"))

        account = self.engine.get_account(refresh_quotes=False)
        self.assertEqual([], account.get("positions", []))
        self.assertEqual(50.0, account.get("cash_krw"))


if __name__ == "__main__":
    unittest.main()
