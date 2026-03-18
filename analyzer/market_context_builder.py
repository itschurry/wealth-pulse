"""거시 지표와 시장 데이터를 바탕으로 시장 컨텍스트를 생성한다."""
from __future__ import annotations

from collectors.models import MacroIndicator, MarketContext, MarketSnapshot


def _macro_map(macro: list[MacroIndicator]) -> dict[str, MacroIndicator]:
    return {item.key: item for item in macro}


def summarize_macro_for_prompt(macro: list[MacroIndicator]) -> str:
    if not macro:
        return "거시 지표 데이터 없음"
    lines = []
    for item in macro:
        if not item.display_value:
            continue
        line = f"- {item.label}: {item.display_value}"
        if item.summary:
            line += f" ({item.summary})"
        lines.append(line)
    return "\n".join(lines) if lines else "거시 지표 데이터 없음"


def summarize_market_context_for_prompt(context: MarketContext | None) -> str:
    if context is None:
        return "시장 컨텍스트 데이터 없음"
    lines = [
        f"- 시장 국면: {context.regime}",
        f"- 리스크 수준: {context.risk_level}",
        f"- 인플레이션: {context.inflation_signal}",
        f"- 고용: {context.labor_signal}",
        f"- 정책: {context.policy_signal}",
        f"- 장단기금리: {context.yield_curve_signal}",
        f"- 달러: {context.dollar_signal}",
        f"- 종합: {context.summary}",
    ]
    if context.risks:
        lines.append("- 주요 리스크: " + ", ".join(context.risks))
    if context.supports:
        lines.append("- 우호 요인: " + ", ".join(context.supports))
    return "\n".join(lines)


def build_market_context(market: MarketSnapshot, macro: list[MacroIndicator]) -> MarketContext:
    if not macro:
        return MarketContext(summary="거시 지표 데이터가 없어 시장 컨텍스트를 보수적으로 해석합니다.")

    items = _macro_map(macro)
    cpi = items.get("cpi_yoy")
    ppi = items.get("ppi_yoy")
    nfp = items.get("nfp_change")
    unrate = items.get("unemployment")
    fed = items.get("fed_funds")
    us2y = items.get("us2y")
    us10y = items.get("us10y")
    dxy = items.get("dxy")

    spread = None
    if us10y and us2y and us10y.value is not None and us2y.value is not None:
        spread = us10y.value - us2y.value

    inflation_signal = "중립"
    if cpi and cpi.value is not None:
        if cpi.value <= 3.0 and (ppi is None or ppi.value is None or ppi.value <= 3.0):
            inflation_signal = "둔화"
        elif cpi.value >= 3.5:
            inflation_signal = "재가열"

    labor_signal = "중립"
    if unrate and unrate.value is not None and nfp and nfp.value is not None:
        if unrate.value <= 4.2 and nfp.value >= 150:
            labor_signal = "견조"
        elif unrate.value >= 4.5 or nfp.value < 100:
            labor_signal = "둔화"

    policy_signal = "중립"
    if fed and fed.value is not None:
        if fed.value >= 4.5 and inflation_signal != "둔화":
            policy_signal = "긴축 지속"
        elif inflation_signal == "둔화":
            policy_signal = "완화 기대"

    yield_curve_signal = "중립"
    if spread is not None:
        if spread < 0:
            yield_curve_signal = "역전"
        elif spread > 0.5:
            yield_curve_signal = "정상화"

    dollar_signal = "중립"
    if dxy and dxy.value is not None and dxy.previous is not None:
        if dxy.value - dxy.previous >= 0.5:
            dollar_signal = "강세"
        elif dxy.value - dxy.previous <= -0.5:
            dollar_signal = "약세"

    risks: list[str] = []
    supports: list[str] = []

    if inflation_signal == "재가열":
        risks.append("물가 재가열로 금리 인하 기대 약화")
    if labor_signal == "둔화":
        risks.append("고용 둔화로 경기 민감주 부담")
    if yield_curve_signal == "역전":
        risks.append("장단기 금리 역전 지속")
    if dollar_signal == "강세":
        risks.append("달러 강세로 위험자산 변동성 확대")

    if inflation_signal == "둔화":
        supports.append("물가 둔화로 완화 기대 확대")
    if labor_signal == "견조":
        supports.append("고용 견조로 경기 방어력 유지")
    if yield_curve_signal == "정상화":
        supports.append("장단기 금리 스프레드 정상화")
    if market.nasdaq_change_pct and market.nasdaq_change_pct > 0:
        supports.append("미국 성장주 심리 개선")

    if len(risks) >= 3:
        regime = "risk_off"
        risk_level = "높음"
    elif len(supports) >= 2 and len(risks) <= 1:
        regime = "risk_on"
        risk_level = "낮음"
    else:
        regime = "neutral"
        risk_level = "중간"

    summary_parts = [
        f"인플레이션은 {inflation_signal}",
        f"고용은 {labor_signal}",
        f"정책 환경은 {policy_signal}",
    ]
    if spread is not None:
        summary_parts.append(
            f"10Y-2Y 스프레드는 {spread:+.2f}%p로 {yield_curve_signal}")
    if dollar_signal != "중립":
        summary_parts.append(f"달러는 {dollar_signal}")

    return MarketContext(
        regime=regime,
        risk_level=risk_level,
        inflation_signal=inflation_signal,
        labor_signal=labor_signal,
        policy_signal=policy_signal,
        yield_curve_signal=yield_curve_signal,
        dollar_signal=dollar_signal,
        summary=", ".join(summary_parts),
        risks=risks,
        supports=supports,
    )
