from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectors.models import DailyData, MarketContext, MarketSnapshot
from reporter.report_generator import generate_html


class ReportGeneratorRegressionTests(unittest.TestCase):
    def test_generate_html_uses_app_template_directory_and_renders_summary(self):
        data = DailyData(
            collected_at=datetime(2026, 3, 31, 7, 0, 0),
            market=MarketSnapshot(timestamp=datetime(2026, 3, 31, 7, 0, 0), kospi=2500.0, kospi_change_pct=1.2),
            market_context=MarketContext(regime="risk_on", risk_level="중간", summary="유동성 우호적"),
        )
        analysis = """
⚠️ 테스트 면책 문구

## 3줄 요약
1. 반도체 강세
2. 달러 안정
3. 변동성 완화

## 본문
- 체크 포인트
""".strip()

        html = generate_html(analysis, data)

        self.assertIn("오늘의 시장 요약", html)
        self.assertIn("반도체 강세", html)
        self.assertIn('<div class="header-title">📊 일일 경제 리포트</div>', html)
        self.assertIn("disclaimer-inline", html)


if __name__ == "__main__":
    unittest.main()
