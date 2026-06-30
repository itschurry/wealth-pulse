from __future__ import annotations

import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from services.research_agent_payload import build_agent_research_ingest_payload
from services.research_store import DEFAULT_RESEARCH_TTL_MINUTES


class ResearchAgentPayloadTests(unittest.TestCase):
    def test_buy_intent_zero_risk_prices_are_normalized_from_current_price(self) -> None:
        payload = {
            "generated_at": "2026-06-22T09:30:00+09:00",
            "items": [
                {
                    "symbol": "000660",
                    "market": "KOSPI",
                    "confidence": 0.88,
                    "rating": "overweight",
                    "action": "buy_watch",
                    "summary": "상승 추세와 최근 뉴스가 같이 확인된다.",
                    "bull_case": ["거래대금 증가와 추세 확인"],
                    "bear_case": ["단기 급등 부담"],
                    "catalysts": ["최근 업황 뉴스 재평가"],
                    "risks": ["수급 반전"],
                    "invalidation_trigger": {
                        "condition": "현재가가 주요 지지선을 이탈하면 매수 논리가 깨진다.",
                        "stop_loss": 0,
                    },
                    "trade_plan": {
                        "size_intent_pct": 18,
                        "entry": "runtime_and_risk_guard_only",
                        "stop_loss": 0,
                        "take_profit": 0,
                    },
                    "technical_features": {
                        "close": 100000,
                        "close_vs_sma20": 1.08,
                        "volume_ratio": 1.4,
                    },
                    "news_inputs": [
                        {
                            "source": "google-news-rss",
                            "url": "https://www.hankyung.com/finance/article/202606220001",
                            "published_at": "2026-06-22T09:00:00+09:00",
                            "title": "SK하이닉스 상승",
                        }
                    ],
                    "evidence": [
                        {
                            "source": "krx",
                            "url": "https://kind.krx.co.kr/disclosure/details.do",
                            "title": "KRX 공시",
                        }
                    ],
                    "data_quality": {
                        "has_news": True,
                        "has_recent_price": True,
                        "has_technical_features": True,
                    },
                }
            ],
        }

        normalized = build_agent_research_ingest_payload(payload)
        item = normalized["items"][0]

        self.assertEqual(item["invalidation_trigger"]["stop_loss"], 95000)
        self.assertEqual(item["trade_plan"]["stop_loss"], 95000)
        self.assertEqual(item["trade_plan"]["take_profit"], 112000)
        self.assertEqual(item["ttl_minutes"], DEFAULT_RESEARCH_TTL_MINUTES)


if __name__ == "__main__":
    unittest.main()
