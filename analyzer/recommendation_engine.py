"""Rule-based investment recommendation engine (MVP)."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List

import pytz

from collectors.models import DailyData
from config.portfolio import HOLDINGS

_KST = pytz.timezone("Asia/Seoul")

_SECTOR_KEYWORDS = {
    "반도체": ["반도체", "HBM", "메모리", "파운드리", "엔비디아", "nvidia", "chip"],
    "자동차": ["자동차", "전기차", "배터리", "자율주행", "현대차", "기아"],
    "금융/벤처캐피탈": ["금리", "은행", "벤처", "ipo", "상장", "투자"],
    "코스닥 지수": ["코스닥", "중소형주", "바이오", "성장주"],
    "자동차부품": ["자동차부품", "모듈", "부품", "모비스", "공급망"],
}


def _safe_text(value: str | None) -> str:
    return (value or "").strip()


def _market_bias(data: DailyData) -> float:
    m = data.market
    changes = [
        m.kospi_change_pct,
        m.kosdaq_change_pct,
        m.sp100_change_pct,
        m.nasdaq_change_pct,
    ]
    valid = [c for c in changes if c is not None]
    if not valid:
        return 0.0
    avg = sum(valid) / len(valid)
    return max(min(avg, 3.0), -3.0)


def _risk_level(data: DailyData, sector_weight: float) -> str:
    m = data.market
    swings = [abs(x) for x in [m.kospi_change_pct, m.kosdaq_change_pct,
                               m.sp100_change_pct, m.nasdaq_change_pct] if x is not None]
    vol = (sum(swings) / len(swings)) if swings else 0.0
    vix = m.vix or 18

    risk_score = vol * 8 + max(vix - 18, 0) * 1.2 + \
        max(sector_weight - 45, 0) * 0.2
    if risk_score >= 35:
        return "높음"
    if risk_score >= 20:
        return "중간"
    return "낮음"


def _signal(score: float) -> str:
    if score >= 66:
        return "추천"
    if score >= 52:
        return "중립"
    return "회피"


def _collect_text_chunks(data: DailyData) -> List[str]:
    chunks: List[str] = []
    for n in data.news:
        chunks.append(" ".join([
            _safe_text(getattr(n, "title", "")),
            _safe_text(getattr(n, "summary", "")),
            _safe_text(getattr(n, "body", "")),
        ]).lower())
    return chunks


def _keyword_hits(chunks: List[str], keywords: List[str]) -> int:
    if not chunks:
        return 0
    hits = 0
    for kw in keywords:
        kw_l = kw.lower()
        if any(kw_l in c for c in chunks):
            hits += 1
    return hits


def generate_recommendations(data: DailyData) -> Dict:
    """Generate daily recommendations payload for API/UI consumption."""
    now = datetime.now(_KST)
    market_bias = _market_bias(data)
    chunks = _collect_text_chunks(data)
    macro_adjustment = 0.0
    macro_note = "거시 컨텍스트 데이터 없음"
    if data.market_context:
        macro_note = data.market_context.summary
        if data.market_context.regime == "risk_on":
            macro_adjustment += 3.0
        elif data.market_context.regime == "risk_off":
            macro_adjustment -= 4.0
        if data.market_context.risk_level == "높음":
            macro_adjustment -= 2.0

    sector_weights: Dict[str, float] = {}
    for h in HOLDINGS:
        sector_weights[h.sector] = sector_weights.get(
            h.sector, 0.0) + float(h.weight_pct)

    recommendations = []
    for rank, h in enumerate(HOLDINGS, start=1):
        keywords = _SECTOR_KEYWORDS.get(h.sector, [h.name, h.sector])
        hits = _keyword_hits(chunks, keywords)

        score = 50.0
        score += market_bias * 4.0
        score += macro_adjustment
        score += min(hits, 6) * 3.5
        score += min(h.weight_pct / 10.0, 4.0)
        score = max(0.0, min(score, 100.0))

        sector_weight = sector_weights.get(h.sector, 0.0)
        signal = _signal(score)
        risk = _risk_level(data, sector_weight)

        reasons = [
            f"{h.sector} 관련 데이터 키워드 매칭 {hits}건",
            f"시장 모멘텀 지표 평균 {market_bias:+.2f}% 반영",
            f"거시 환경 반영: {macro_note}",
            f"보유 비중 {h.weight_pct:.2f}% 기반 우선순위 적용",
        ]
        risks = [
            f"섹터 집중도 {sector_weight:.2f}%",
            "단기 변동성 확대 가능성",
        ]
        if data.market_context and data.market_context.risks:
            risks.extend(data.market_context.risks[:2])

        recommendations.append({
            "rank": rank,
            "name": h.name,
            "ticker": h.ticker_kr or h.ticker_us or "",
            "sector": h.sector,
            "signal": signal,
            "score": round(score, 1),
            "confidence": int(round(score)),
            "risk_level": risk,
            "reasons": reasons,
            "risks": risks,
        })

    recommendations.sort(key=lambda x: x["score"], reverse=True)
    for idx, item in enumerate(recommendations, start=1):
        item["rank"] = idx

    signal_counts = {"추천": 0, "중립": 0, "회피": 0}
    for item in recommendations:
        signal_counts[item["signal"]] = signal_counts.get(
            item["signal"], 0) + 1

    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M KST"),
        "date": now.strftime("%Y-%m-%d"),
        "strategy": "aggressive-mvp-v1",
        "universe": "holdings",
        "signal_counts": signal_counts,
        "backtest": {
            "window": "placeholder",
            "hit_rate": None,
            "avg_return": None,
            "max_drawdown": None,
            "note": "백테스트는 다음 단계에서 연결됩니다.",
        },
        "recommendations": recommendations,
    }
