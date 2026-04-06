from __future__ import annotations

from typing import Any


_ALLOWED_MODE_LABELS = {"낮음": "공격", "중간": "선별", "높음": "축소"}


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default



def build_hanna_brief_from_runtime(
    *,
    signal_book: dict[str, Any],
    market_context: dict[str, Any] | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    market_context = market_context if isinstance(market_context, dict) else {}
    context = market_context.get("context") if isinstance(market_context.get("context"), dict) else {}
    summary = str(
        market_context.get("summary")
        or context.get("summary")
        or context.get("market_view")
        or ""
    ).strip()
    risk_level = str(
        signal_book.get("risk_level")
        or (signal_book.get("risk_guard_state") if isinstance(signal_book.get("risk_guard_state"), dict) else {}).get("risk_level")
        or context.get("risk_level")
        or "중간"
    )
    regime = str(
        signal_book.get("regime")
        or (signal_book.get("risk_guard_state") if isinstance(signal_book.get("risk_guard_state"), dict) else {}).get("regime")
        or context.get("regime")
        or "neutral"
    )
    entry_allowed_count = _to_int(signal_book.get("entry_allowed_count"), 0)
    blocked_count = _to_int(signal_book.get("blocked_count"), 0)
    count = _to_int(signal_book.get("count"), 0)
    stance = _ALLOWED_MODE_LABELS.get(risk_level, "선별")
    guard_state = signal_book.get("risk_guard_state") if isinstance(signal_book.get("risk_guard_state"), dict) else {}
    guard_reasons = [str(item).strip() for item in (guard_state.get("reasons") or []) if str(item).strip()]
    context_risks = [str(item).strip() for item in (market_context.get("risks") or context.get("risks") or []) if str(item).strip()]

    summary_lines: list[str] = []
    if summary:
        summary_lines.append(summary)
    summary_lines.append(f"현재 장세는 {regime}, 위험도는 {risk_level} 기준으로 읽고 있어.")
    summary_lines.append(f"실행 후보 {count}건 중 진입 가능 {entry_allowed_count}건, 차단 {blocked_count}건 상태야.")
    if guard_reasons:
        summary_lines.append(f"리스크 가드 핵심 사유: {guard_reasons[0]}")
    elif blocked_count > 0:
        summary_lines.append("차단 후보는 리스크 가드나 유동성 조건부터 먼저 확인하면 돼.")
    else:
        summary_lines.append("지금은 차단 사유보다 허용 후보 우선순위 정리에 집중하면 돼.")
    if context_risks:
        summary_lines.append(f"시장 주의 포인트: {context_risks[0]}")

    summary_lines = summary_lines[:5]
    generated_at = str(signal_book.get("generated_at") or market_context.get("generated_at") or date or "")
    report_reasoning = {
        "source": "runtime_signal_book",
        "regime": regime,
        "risk_level": risk_level,
        "stance": stance,
        "guard_reasons": guard_reasons[:3],
        "context_risks": context_risks[:3],
    }
    analysis = {
        "date": str(date or market_context.get("date") or ""),
        "generated_at": generated_at,
        "summary_lines": summary_lines,
        "source": "hanna_runtime_brief",
    }

    return {
        "ok": True,
        "brief_type": "hanna_operator_brief_v2",
        "owner": "hanna",
        "date": str(date or market_context.get("date") or ""),
        "generated_at": generated_at,
        "summary_lines": summary_lines,
        "analysis": analysis,
        "report_reasoning": report_reasoning,
        "migration": {
            "backend_owner": "hanna",
            "legacy_source_retained": False,
            "stage": "phase_2_runtime_brief",
        },
    }


def build_hanna_daily_report_text(*, daily_data: Any) -> str:
    market = getattr(daily_data, "market", None)
    market_context = getattr(daily_data, "market_context", None)
    summary = str(getattr(market_context, "summary", "") or "").strip() or "시장 컨텍스트 요약이 아직 충분하지 않아."
    risks = [str(item).strip() for item in (getattr(market_context, "risks", None) or []) if str(item).strip()]
    supports = [str(item).strip() for item in (getattr(market_context, "supports", None) or []) if str(item).strip()]

    lines = ["## 한나 투자 브리프", "", "### 3줄 요약"]
    lines.append(f"1. {summary}")
    lines.append(f"2. 오늘은 {' / '.join(supports[:2]) if supports else '정량 신호 우선 확인'} 쪽이 먼저야.")
    lines.append(f"3. 주의할 건 {' / '.join(risks[:2]) if risks else '과한 추격 진입과 유동성 부족'}이야.")
    lines.append("")
    lines.append("### 시장 체크")
    if market is not None:
        if getattr(market, "kospi", None) is not None:
            lines.append(f"- KOSPI {market.kospi:,.2f} ({float(getattr(market, 'kospi_change_pct', 0.0)):+.2f}%)")
        if getattr(market, "kosdaq", None) is not None:
            lines.append(f"- KOSDAQ {market.kosdaq:,.2f} ({float(getattr(market, 'kosdaq_change_pct', 0.0)):+.2f}%)")
        if getattr(market, "nasdaq", None) is not None:
            lines.append(f"- NASDAQ {market.nasdaq:,.2f} ({float(getattr(market, 'nasdaq_change_pct', 0.0)):+.2f}%)")
        if getattr(market, "usd_krw", None) is not None:
            lines.append(f"- USD/KRW {market.usd_krw:,.2f}")
    lines.append("")
    lines.append("### 운영 메모")
    lines.append("- 설명은 한나가 맡고, 진입 여부와 리스크 가드는 정량 엔진 기준으로 본다.")
    lines.append("- 오늘 브리프는 장세 요약과 우선순위 정리용이지, 주문 명령문이 아니다.")
    if risks:
        lines.append(f"- 핵심 리스크: {risks[0]}")
    return "\n".join(lines)
