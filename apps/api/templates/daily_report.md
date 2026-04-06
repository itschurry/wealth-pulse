# 📊 일일 경제 리포트 {{ report_date }}
생성: {{ generated_at }} | 뉴스: {{ news_count }}건

---

## 📈 시장 현황
{% if market.kospi %}- **KOSPI**: {{ "%.2f"|format(market.kospi) }} ({{ "%+.2f%%"|format(market.kospi_change_pct) }}){% else %}- KOSPI: 데이터 없음{% endif %}
{% if market.kosdaq %}- **KOSDAQ**: {{ "%.2f"|format(market.kosdaq) }} ({{ "%+.2f%%"|format(market.kosdaq_change_pct) }}){% else %}- KOSDAQ: 데이터 없음{% endif %}
{% if market.sp100 %}- **S&P100**: {{ "%.2f"|format(market.sp100) }} ({{ "%+.2f%%"|format(market.sp100_change_pct) }}){% else %}- S&P100: 데이터 없음{% endif %}
{% if market.nasdaq %}- **NASDAQ**: {{ "%.2f"|format(market.nasdaq) }} ({{ "%+.2f%%"|format(market.nasdaq_change_pct) }}){% else %}- NASDAQ: 데이터 없음{% endif %}
{% if market.usd_krw %}- **USD/KRW**: {{ "%.2f"|format(market.usd_krw) }}{% endif %}
{% if market.wti_oil %}- **WTI**: ${{ "%.2f"|format(market.wti_oil) }}{% endif %}
{% if market.gold %}- **금**: ${{ "%.2f"|format(market.gold) }}{% endif %}
{% if market.vix %}- **VIX**: {{ "%.2f"|format(market.vix) }}{% endif %}

---

## 🌐 거시 환경
{% if market_context %}- **시장 국면**: {{ market_context.regime }} / 리스크 {{ market_context.risk_level }}
- **요약**: {{ market_context.summary }}
{% if market_context.risks %}{% for risk in market_context.risks %}- **리스크**: {{ risk }}
{% endfor %}{% endif %}
{% if market_context.supports %}{% for support in market_context.supports %}- **우호 요인**: {{ support }}
{% endfor %}{% endif %}
{% else %}- 시장 컨텍스트 데이터 없음
{% endif %}

---

## 🧭 주요 거시 지표
{% if macro %}{% for item in macro %}- **{{ item.label }}**: {{ item.display_value if item.display_value else "데이터 없음" }}{% if item.summary %} — {{ item.summary }}{% endif %}
{% endfor %}{% else %}- 거시 지표 데이터 없음
{% endif %}

---

## 💼 보유 종목
{% if holdings %}{% for h in holdings %}- **{{ h.name }}**: {{ "{:,.0f}".format(h.current_price) }}원 (전일비 {{ "%+.2f%%"|format(h.change_pct) }}, 수익률 {{ "%+.2f%%"|format(h.unrealized_return_pct) }})
{% endfor %}{% else %}- 보유 종목 데이터 없음
{% endif %}

---

## 🤖 AI 분석

{{ analysis }}

---

⚠️ 본 리포트는 투자 참고용 정보이며, 최종 투자 판단과 손익의 책임은 투자자 본인에게 있습니다.
