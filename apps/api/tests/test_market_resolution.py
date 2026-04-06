import unittest
from datetime import datetime

from analyzer.today_picks_engine import _alias_in_text, _extract_dynamic_us_ticker_entries
from collectors.models import NewsArticle
from market_utils import lookup_company_listing, resolve_market, resolve_quote_market


class MarketResolutionTests(unittest.TestCase):
    def test_lookup_company_listing_resolves_domestic_english_alias(self):
        listing = lookup_company_listing(code="IBK", scope="core")
        self.assertIsNotNone(listing)
        self.assertEqual("024110", listing["code"])
        self.assertEqual("KOSPI", listing["market"])

    def test_resolve_market_keeps_ambiguous_alpha_unresolved(self):
        self.assertEqual("", resolve_market(code="IB", scope="core"))

    def test_resolve_quote_market_maps_domestic_alias_to_krx_quote_bucket(self):
        self.assertEqual("KOSPI", resolve_quote_market(code="LS", scope="core"))

    def test_ascii_alias_matching_uses_word_boundaries(self):
        self.assertFalse(_alias_in_text("ls", "sales momentum improved"))
        self.assertTrue(_alias_in_text("ls", "ls electric order backlog increased"))

    def test_dynamic_us_ticker_extractor_skips_known_domestic_alias(self):
        article = NewsArticle(
            title="LS 실적 개선",
            summary="LS 수주 증가와 LS valuation 재평가",
            body="기관은 LS를 국내 전력 인프라 대표주로 평가했다.",
            url="https://example.com/ls",
            source="unit-test",
            published=datetime(2026, 3, 20),
        )
        entries = _extract_dynamic_us_ticker_entries([article], existing_codes=set())
        self.assertEqual([], entries)

    def test_dynamic_us_ticker_extractor_requires_strong_us_signal_for_unknown_short_symbol(self):
        article = NewsArticle(
            title="IB 사업 재편",
            summary="IB 부문 확대와 IB 역량 강화",
            body="국내 금융사들이 IB 조직 개편에 나섰다.",
            url="https://example.com/ib",
            source="unit-test",
            published=datetime(2026, 3, 20),
        )
        entries = _extract_dynamic_us_ticker_entries([article], existing_codes=set())
        self.assertEqual([], entries)


if __name__ == "__main__":
    unittest.main()
