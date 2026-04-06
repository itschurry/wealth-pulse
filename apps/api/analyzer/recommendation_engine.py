"""Hanna commentary-aware investment recommendation engine."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List
from zoneinfo import ZoneInfo

from analyzer.technical_snapshot import evaluate_technical_snapshot, fetch_technical_snapshot
from analyzer.utils import normalize_lower as _normalize
from collectors.models import DailyData
from config.portfolio import HOLDINGS
from market_utils import lookup_company_listing, resolve_market
from services.hanna_commentary_service import build_hanna_candidate_commentary

_KST = ZoneInfo("Asia/Seoul")
_ALLOWED_HORIZONS = {"short_term", "mid_term"}

_SECTOR_KEYWORDS = {
    "반도체": ["반도체", "HBM", "메모리", "파운드리", "엔비디아", "nvidia", "chip"],
    "자동차": ["자동차", "전기차", "배터리", "자율주행", "robotaxi", "sdv", "현대차", "기아", "테슬라", "피지컬 ai"],
    "금융/벤처캐피탈": ["금리", "은행", "벤처", "ipo", "상장", "투자"],
    "코스닥 지수": ["코스닥", "중소형주", "바이오", "성장주"],
    "자동차부품": ["자동차부품", "모듈", "부품", "모비스", "공급망"],
    "로봇": ["로봇", "로보틱스", "협동로봇", "humanoid", "휴머노이드", "physical ai", "피지컬 ai"],
}


def _safe_text(value: str | None) -> str:
    return (value or "").strip()


def _normalize_code(value: str) -> str:
    return (value or "").split(".")[0].strip().upper()


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


def _risk_level(data: DailyData, sector_weight: float, gate_status: str = "passed") -> str:
    m = data.market
    swings = [abs(x) for x in [m.kospi_change_pct, m.kosdaq_change_pct,
                               m.sp100_change_pct, m.nasdaq_change_pct] if x is not None]
    vol = (sum(swings) / len(swings)) if swings else 0.0
    vix = m.vix or 18
    risk_score = vol * 8 + max(vix - 18, 0) * 1.2 + \
        max(sector_weight - 45, 0) * 0.2
    if gate_status == "blocked":
        risk_score += 15
    elif gate_status == "caution":
        risk_score += 8
    if risk_score >= 35:
        return "높음"
    if risk_score >= 20:
        return "중간"
    return "낮음"


def _signal(score: float, gate_status: str = "passed") -> str:
    if gate_status == "blocked":
        return "회피"
    if gate_status == "caution":
        return "중립" if score >= 52 else "회피"
    if score >= 62:
        return "추천"
    if score >= 48:
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


def _candidate_key(code: str | None, name: str | None) -> str:
    normalized_code = _normalize_code(code or "")
    if normalized_code:
        return f"code:{normalized_code}"
    return f"name:{_normalize(name or '')}"


def _infer_ticker(code: str, market: str) -> str:
    normalized_market = (market or "").upper()
    if normalized_market == "KOSPI" and code.isdigit():
        return f"{code}.KS"
    if normalized_market == "KOSDAQ" and code.isdigit():
        return f"{code}.KQ"
    return code


def _resolve_catalog_entry(code: str, name: str, market: str) -> dict:
    normalized_code = _normalize_code(code)
    listing = lookup_company_listing(
        code=normalized_code, name=name, scope="core")
    if listing:
        return {
            "name": str(listing.get("name") or name or normalized_code),
            "code": str(listing.get("code") or normalized_code or code),
            "market": str(listing.get("market") or market).upper(),
            "sector": str(listing.get("sector") or "미분류"),
        }
    return {
        "name": name or normalized_code or code,
        "code": normalized_code or code,
        "market": resolve_market(code=normalized_code, name=name, market=market, scope="core"),
        "sector": "미분류",
    }


def _build_evidence_maps(data: DailyData) -> tuple[dict, dict]:
    disclosure_map: dict[str, list] = {}
    flow_map: dict[str, object] = {}

    for item in data.disclosures:
        disclosure_map.setdefault(item.stock_code, []).append(item)
        disclosure_map.setdefault(item.company_name, []).append(item)

    for flow in data.investor_flows:
        flow_map[flow.code] = flow
        flow_map[flow.name] = flow
    return disclosure_map, flow_map


def _event_risk_note(playbook: dict, sector: str) -> str | None:
    if not playbook.get("event_watchlist"):
        return None
    sector_lower = _normalize(sector)
    risk_text = " ".join(str(item.get("note", ""))
                         for item in playbook.get("event_watchlist", []))
    if any(keyword in risk_text.lower() for keyword in ("cpi", "fomc", "금리", "고용", "인플레이션")) and sector_lower in {"반도체", "플랫폼", "자동차", "로봇"}:
        return "핵심 이벤트 전후 변동성 확대 가능성"
    return None


def _merge_gate_status(left: str, right: str) -> str:
    order = {"passed": 0, "caution": 1, "blocked": 2}
    return left if order.get(left, 0) >= order.get(right, 0) else right


def _gate_candidate(
    candidate: dict,
    horizon: str,
    playbook: dict,
    data: DailyData,
    evidence: dict,
    technical_assessment: dict | None = None,
) -> tuple[str, list[str], float]:
    gate_reasons: list[str] = []
    alignment = 50.0
    sector = str(candidate.get("sector", "")).strip()
    action = str(candidate.get("action", "watch")).strip().lower()
    thesis_blob = " ".join([str(candidate.get("thesis", ""))] + [str(v)
                           for v in candidate.get("reasons", [])]).lower()
    favored = {_normalize(item)
               for item in playbook.get("favored_sectors", [])}
    avoided = {_normalize(item)
               for item in playbook.get("avoided_sectors", [])}
    invalid_setups = [str(item).strip().lower() for item in playbook.get(
        "invalid_setups", []) if str(item).strip()]

    if evidence["evidence_score"] <= 0:
        gate_reasons.append("근거 부족")
    if action == "avoid":
        gate_reasons.append("플레이북에서 회피 후보로 분류")
    if _normalize(sector) in favored:
        alignment += 12
    if _normalize(sector) in avoided:
        alignment -= 15
        gate_reasons.append("불리한 섹터로 분류")

    bias = str(playbook.get("short_term_bias" if horizon ==
               "short_term" else "mid_term_bias", "neutral")).lower()
    if bias == "defensive" and action == "buy":
        alignment -= 10
        gate_reasons.append("현재 시장 바이어스와 역행")
    elif bias == "bullish" and action == "buy":
        alignment += 8

    matched_invalid = [
        item for item in invalid_setups if item and item in thesis_blob]
    if matched_invalid:
        gate_reasons.append("플레이북 금지 셋업과 충돌")
        alignment -= 20

    if data.market_context and data.market_context.risk_level == "높음" and horizon == "short_term" and action == "buy":
        gate_reasons.append("단기 리스크 수준이 높음")
        alignment -= 10

    if evidence["negative_flow"]:
        gate_reasons.append("최근 수급이 약세")
        alignment -= 10

    event_risk = _event_risk_note(playbook, sector)
    if event_risk:
        gate_reasons.append(event_risk)
        alignment -= 6

    gate_status = "passed"
    if "근거 부족" in gate_reasons or "플레이북 금지 셋업과 충돌" in gate_reasons or "플레이북에서 회피 후보로 분류" in gate_reasons:
        gate_status = "blocked"
    elif gate_reasons:
        gate_status = "caution"

    if technical_assessment:
        alignment += float(technical_assessment.get("alignment_adjustment") or 0.0)
        gate_status = _merge_gate_status(gate_status, str(
            technical_assessment.get("gate_status") or "passed"))
        gate_reasons.extend(str(item).strip() for item in technical_assessment.get(
            "gate_reasons", []) if str(item).strip())

        if action == "buy" and horizon == "short_term":
            negatives = set(technical_assessment.get("negatives", []))
            if {"추세 역배열", "MACD 모멘텀이 약세"} & negatives:
                gate_status = _merge_gate_status(gate_status, "blocked")
            elif {"RSI 과열 구간", "ATR 기준 변동성 확대 구간"} & negatives:
                gate_status = _merge_gate_status(gate_status, "caution")

    gate_reasons = list(dict.fromkeys(gate_reasons))[:4]
    if gate_status == "passed":
        alignment += 10.0
    return gate_status, gate_reasons, max(5.0, min(95.0, alignment))


def _build_playbook_candidates(playbook: dict | None) -> list[dict]:
    if not playbook:
        return []
    candidates = []
    for horizon in ("short_term", "mid_term"):
        key = f"stock_candidates_{horizon}"
        for item in playbook.get(key, []):
            if not isinstance(item, dict):
                continue
            normalized_horizon = horizon if horizon in _ALLOWED_HORIZONS else "short_term"
            merged = dict(item)
            merged["horizon"] = normalized_horizon
            candidates.append(merged)
    return candidates


def _legacy_recommendations(data: DailyData) -> Dict:
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
        # Phase 2-2: generate_recommendations와 가중치 통일
        score += min(hits, 8) * 3.0
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
            "horizon": "mid_term",
            "gate_status": "passed",
            "gate_reasons": [],
            "playbook_alignment": round(score, 1),
            "ai_thesis": macro_note,
            "playbook_ref": None,
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
        "rejected_candidates": [],
        "backtest": {
            "window": "placeholder",
            "hit_rate": None,
            "avg_return": None,
            "max_drawdown": None,
            "note": "백테스트는 다음 단계에서 연결됩니다.",
        },
        "recommendations": recommendations,
    }


def generate_recommendations(data: DailyData, playbook: dict | None = None) -> Dict:
    """Generate playbook-aware recommendations payload for API/UI consumption."""
    if not playbook or not _build_playbook_candidates(playbook):
        return _legacy_recommendations(data)

    now = datetime.now(_KST)
    market_bias = _market_bias(data)
    chunks = _collect_text_chunks(data)
    disclosure_map, flow_map = _build_evidence_maps(data)
    sector_weights: Dict[str, float] = {}
    for h in HOLDINGS:
        sector_weights[h.sector] = sector_weights.get(
            h.sector, 0.0) + float(h.weight_pct)

    recommendations: list[dict] = []
    rejected_candidates: list[dict] = []
    seen_keys: set[str] = set()
    playbook_candidates = _build_playbook_candidates(playbook)

    for candidate in playbook_candidates:
        catalog_entry = _resolve_catalog_entry(
            str(candidate.get("code", "")),
            str(candidate.get("name", "")),
            str(candidate.get("market", "")),
        )
        key = _candidate_key(catalog_entry["code"], catalog_entry["name"])
        if key in seen_keys:
            continue
        seen_keys.add(key)

        sector = str(candidate.get("sector")
                     or catalog_entry["sector"] or "미분류")
        keywords = _SECTOR_KEYWORDS.get(
            sector, [catalog_entry["name"], sector])
        hits = _keyword_hits(chunks, keywords)
        disclosures = disclosure_map.get(
            catalog_entry["code"], []) or disclosure_map.get(catalog_entry["name"], [])
        flow = flow_map.get(catalog_entry["code"]) or flow_map.get(
            catalog_entry["name"])
        negative_flow = bool(
            flow
            and getattr(flow, "foreign_net_5d", 0) < 0
            and getattr(flow, "institution_net_5d", 0) < 0
        )
        evidence = {
            "news_hits": hits,
            "disclosure_count": len(disclosures),
            "flow_present": bool(flow),
            "negative_flow": negative_flow,
            "evidence_score": hits + len(disclosures) * 2 + (1 if flow else 0),
        }
        technical_snapshot = candidate.get("technical_snapshot") or fetch_technical_snapshot(
            catalog_entry["code"],
            catalog_entry["market"],
        )
        technical_assessment = evaluate_technical_snapshot(
            technical_snapshot,
            horizon=str(candidate.get("horizon", "short_term")),
            has_event_risk=bool(_event_risk_note(playbook, sector)),
        )
        gate_status, gate_reasons, alignment = _gate_candidate(
            {
                **candidate,
                "sector": sector,
            },
            str(candidate.get("horizon", "short_term")),
            playbook,
            data,
            evidence,
            technical_assessment,
        )

        confidence = max(
            35, min(95, int(round(float(candidate.get("confidence", 60))))))
        base_score = 46.0
        base_score += (confidence - 50) * 0.45
        base_score += market_bias * 4.0
        base_score += min(hits, 8) * 3.0
        base_score += min(len(disclosures), 3) * 5.0
        if flow:
            base_score += 3.0
        if _normalize(sector) in {_normalize(item) for item in playbook.get("favored_sectors", [])}:
            base_score += 4.0
        if _normalize(sector) in {_normalize(item) for item in playbook.get("avoided_sectors", [])}:
            base_score -= 6.0
        if str(candidate.get("action", "watch")).lower() == "buy":
            base_score += 6.0
        elif str(candidate.get("action", "watch")).lower() == "avoid":
            base_score -= 12.0
        base_score += float(technical_assessment.get("score_adjustment") or 0.0)
        if gate_status == "blocked":
            base_score -= 12.0
        elif gate_status == "caution":
            base_score -= 4.0
        score = round(max(20.0, min(95.0, base_score)), 1)
        signal = _signal(score, gate_status)
        sector_weight = sector_weights.get(sector, 0.0)
        risk_level = _risk_level(data, sector_weight, gate_status)
        thesis = str(candidate.get("thesis", "")).strip()

        reasons = [thesis] if thesis else []
        reasons.extend(str(value).strip() for value in candidate.get(
            "reasons", []) if str(value).strip())
        reasons.extend(str(value).strip() for value in technical_assessment.get(
            "positives", []) if str(value).strip())
        if hits:
            reasons.append(f"{sector} 관련 뉴스 키워드 매칭 {hits}건")
        if disclosures:
            reasons.append(f"관련 공시 {len(disclosures)}건 반영")
        if flow:
            reasons.append("수급 데이터 확인")

        risks = [str(value).strip()
                 for value in candidate.get("risks", []) if str(value).strip()]
        risks.extend(str(value).strip() for value in technical_assessment.get(
            "negatives", []) if str(value).strip())
        risks.extend(gate_reasons)
        if data.market_context and data.market_context.risks:
            risks.extend(data.market_context.risks[:2])

        deduped_reasons = list(dict.fromkeys(reasons))[:4]
        deduped_risks = list(dict.fromkeys(risks))[:4]
        commentary = build_hanna_candidate_commentary(
            name=catalog_entry["name"],
            market=catalog_entry["market"],
            signal=signal,
            gate_status=gate_status,
            reasons=deduped_reasons,
            risks=deduped_risks,
            technical_view=str(candidate.get("technical_view") or technical_assessment.get("technical_view") or "").strip(),
            base_thesis=thesis or "",
        )

        item = {
            "rank": 0,
            "name": catalog_entry["name"],
            "ticker": _infer_ticker(catalog_entry["code"], catalog_entry["market"]),
            "sector": sector,
            "signal": signal,
            "score": score,
            "confidence": confidence,
            "risk_level": risk_level,
            "reasons": deduped_reasons,
            "risks": deduped_risks,
            "horizon": str(candidate.get("horizon", "short_term")),
            "gate_status": gate_status,
            "gate_reasons": gate_reasons,
            "playbook_alignment": round(alignment, 1),
            "ai_thesis": commentary["ai_thesis"],
            "playbook_ref": playbook.get("generated_at") or playbook.get("date"),
            "market": catalog_entry["market"],
            "code": catalog_entry["code"],
            "technical_snapshot": technical_snapshot,
            "technical_view": commentary["technical_view"],
            "setup_quality": str(candidate.get("setup_quality") or technical_assessment.get("setup_quality") or "mixed").strip(),
            "commentary_owner": commentary["commentary_owner"],
            "risk_note": commentary["risk_note"],
        }
        if gate_status == "blocked":
            rejected_candidates.append(item)
        else:
            recommendations.append(item)

    recommendations.sort(
        key=lambda item: (
            {"passed": 2, "caution": 1, "blocked": 0}.get(
                item["gate_status"], 0),
            item["score"],
            item["playbook_alignment"],
        ),
        reverse=True,
    )
    for idx, item in enumerate(recommendations, start=1):
        item["rank"] = idx

    signal_counts = {"추천": 0, "중립": 0, "회피": 0}
    for item in recommendations:
        signal_counts[item["signal"]] = signal_counts.get(
            item["signal"], 0) + 1

    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M KST"),
        "date": now.strftime("%Y-%m-%d"),
        "strategy": "hanna-commentary-hybrid-v1",
        "universe": "news-expanded",
        "signal_counts": signal_counts,
        "playbook_ref": playbook.get("generated_at") or playbook.get("date"),
        "rejected_candidates": rejected_candidates[:12],
        "backtest": {
            "window": "placeholder",
            "hit_rate": None,
            "avg_return": None,
            "max_drawdown": None,
            "note": "백테스트는 다음 단계에서 연결됩니다.",
        },
        "recommendations": recommendations[:20],
    }
