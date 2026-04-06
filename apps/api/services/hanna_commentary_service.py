from __future__ import annotations

from typing import Any


def _clean_list(values: list[Any] | None, limit: int = 4) -> list[str]:
    items = [str(value).strip() for value in (values or []) if str(value).strip()]
    deduped: list[str] = []
    for item in items:
        if item not in deduped:
            deduped.append(item)
    return deduped[:limit]


def build_hanna_candidate_commentary(
    *,
    name: str,
    market: str,
    signal: str,
    gate_status: str,
    reasons: list[Any] | None = None,
    risks: list[Any] | None = None,
    technical_view: str | None = None,
    base_thesis: str | None = None,
) -> dict[str, str]:
    clean_reasons = _clean_list(reasons, limit=3)
    clean_risks = _clean_list(risks, limit=2)
    technical = str(technical_view or "").strip()
    thesis = str(base_thesis or "").strip()
    market_label = str(market or "").upper() or "UNKNOWN"

    if not thesis:
        if gate_status == "blocked":
            thesis = f"{name}은 {market_label} 후보 중 신호는 보였지만 지금은 차단 사유를 먼저 해소해야 하는 종목이야."
        elif signal == "추천":
            thesis = f"{name}은 {market_label} 후보 중 지금 가장 먼저 볼 이유가 생긴 종목이야."
        elif signal == "중립":
            thesis = f"{name}은 {market_label}에서 가능성은 있지만 아직 확신까지는 부족한 후보야."
        else:
            thesis = f"{name}은 {market_label}에서 당장 밀어붙이기보다 관찰 우선인 후보야."

    if clean_reasons:
        thesis = f"{thesis} 근거는 {clean_reasons[0]}"
        if len(clean_reasons) > 1:
            thesis += f", 그리고 {clean_reasons[1]} 쪽이야."
        else:
            thesis += "."

    if not technical:
        if clean_reasons:
            technical = " / ".join(clean_reasons[:2])
        elif clean_risks:
            technical = clean_risks[0]
        else:
            technical = "정량 지표와 보조 신호를 함께 보는 단계야."

    risk_line = clean_risks[0] if clean_risks else ("차단 사유를 먼저 확인해." if gate_status == "blocked" else "리스크 가드는 그대로 보수적으로 적용해.")

    return {
        "ai_thesis": thesis.strip(),
        "technical_view": technical.strip(),
        "risk_note": risk_line.strip(),
        "commentary_owner": "hanna",
    }
