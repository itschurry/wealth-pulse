"""OpenAI 기반 종목 보조신호 생성기."""
from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger
from openai import APIError, OpenAI, RateLimitError

from analyzer.market_context_builder import summarize_macro_for_prompt, summarize_market_context_for_prompt
from analyzer.utils import (
    has_notable_flow as _has_notable_flow,
    normalize_lower as _normalize,
    safe_json_loads as _safe_json_loads,
)
from collectors.models import DailyData
from config.company_catalog import CompanyCatalogEntry, get_company_catalog
from config.settings import OPENAI_API_KEY, OPENAI_SIGNAL_MODEL

_KST = ZoneInfo("Asia/Seoul")


def _collect_candidates(data: DailyData, limit: int) -> list[dict]:
    disclosure_map: dict[str, list] = {}
    flow_map: dict[str, dict] = {}
    candidates: list[dict] = []

    for item in data.disclosures:
        disclosure_map.setdefault(item.stock_code, []).append(item)
        disclosure_map.setdefault(item.company_name, []).append(item)

    for flow in data.investor_flows:
        flow_payload = {
            "as_of": flow.as_of,
            "source": flow.source,
            "foreign_net_1d": flow.foreign_net_1d,
            "foreign_net_5d": flow.foreign_net_5d,
            "institution_net_1d": flow.institution_net_1d,
            "institution_net_5d": flow.institution_net_5d,
        }
        flow_map[flow.code] = flow_payload
        flow_map[flow.name] = flow_payload

    for entry in get_company_catalog(scope="core"):
        aliases = tuple(_normalize(alias) for alias in entry.aliases)
        related_articles = []
        for article in data.news:
            text = " ".join([article.title, article.summary, article.body]).lower()
            if any(alias in text for alias in aliases):
                related_articles.append(article)

        disclosures = disclosure_map.get(entry.code, []) or disclosure_map.get(entry.name, [])
        flow = flow_map.get(entry.code) or flow_map.get(entry.name)
        if not related_articles and not disclosures and not _has_notable_flow(flow):
            continue

        candidates.append(
            {
                "entry": entry,
                "articles": related_articles[:3],
                "disclosures": disclosures[:2],
                "flow": flow,
                "priority": len(related_articles) * 4 + len(disclosures) * 5 + (3 if _has_notable_flow(flow) else 0),
            }
        )

    candidates.sort(key=lambda item: (item["priority"], item["entry"].name), reverse=True)
    return candidates[:limit]


def _format_candidate(item: dict) -> str:
    entry: CompanyCatalogEntry = item["entry"]
    lines = [f"- 종목: {entry.name} ({entry.code}, {entry.market}, {entry.sector})"]

    if item["articles"]:
        lines.append("  뉴스:")
        for article in item["articles"]:
            lines.append(f"  - [{article.source}] {article.title}")

    if item["disclosures"]:
        lines.append("  공시:")
        for disclosure in item["disclosures"]:
            lines.append(f"  - [{disclosure.importance}/{disclosure.category}] {disclosure.title}")

    flow = item["flow"]
    if flow:
        lines.append(
            "  수급: "
            f"외국인 1일 {flow['foreign_net_1d']:+,}, 5일 {flow['foreign_net_5d']:+,}; "
            f"기관 1일 {flow['institution_net_1d']:+,}, 5일 {flow['institution_net_5d']:+,}"
        )

    return "\n".join(lines)


def _build_prompt(data: DailyData, candidates: list[dict]) -> str:
    market_lines = []
    if data.market.kospi is not None:
        market_lines.append(f"KOSPI {data.market.kospi:,.2f} ({data.market.kospi_change_pct:+.2f}%)")
    if data.market.kosdaq is not None:
        market_lines.append(f"KOSDAQ {data.market.kosdaq:,.2f} ({data.market.kosdaq_change_pct:+.2f}%)")
    if data.market.nasdaq is not None:
        market_lines.append(f"NASDAQ {data.market.nasdaq:,.2f} ({data.market.nasdaq_change_pct:+.2f}%)")
    if data.market.sp100 is not None:
        market_lines.append(f"S&P100 {data.market.sp100:,.2f} ({data.market.sp100_change_pct:+.2f}%)")

    candidate_blocks = "\n\n".join(_format_candidate(item) for item in candidates)
    return f"""당신은 국내외 주식 단기 이벤트 해석 보조 엔진입니다.

아래 시장/뉴스/공시/수급 근거만 사용해서 종목별 보조신호를 JSON으로 반환하세요.
점수의 주 엔진은 이미 별도로 존재하므로, 당신은 미세 보정만 수행합니다.

규칙:
- 반드시 JSON object만 반환
- signals 배열만 포함
- score_adjustment 는 -4.0 이상 4.0 이하 숫자
- action_bias 는 추천, 중립, 회피 중 하나
- risk_level 는 낮음, 중간, 높음 중 하나
- reasons 와 risks 는 각 0~2개 문자열
- summary 는 120자 이내
- 입력에 없는 사실을 만들지 말 것
- 강한 근거가 없으면 score_adjustment 는 0에 가깝게 유지

시장 요약:
{chr(10).join(market_lines) or "시장 데이터 없음"}

거시 요약:
{summarize_macro_for_prompt(data.macro)}

시장 컨텍스트:
{summarize_market_context_for_prompt(data.market_context)}

대상 종목:
{candidate_blocks}

반환 예시:
{{
  "signals": [
    {{
      "code": "005930",
      "name": "삼성전자",
      "market": "KOSPI",
      "score_adjustment": 2.0,
      "action_bias": "추천",
      "risk_level": "중간",
      "confidence": 74,
      "summary": "공시와 수급이 동시에 우호적이다.",
      "reasons": ["최근 공급계약 공시", "외국인·기관 동반 순매수"],
      "risks": ["주요 거시 이벤트 전후 변동성"]
    }}
  ]
}}
"""


def _normalize_signal_item(item: dict, allowed: dict[str, CompanyCatalogEntry]) -> dict | None:
    code = str(item.get("code", "")).strip()
    if code not in allowed:
        return None
    entry = allowed[code]
    try:
        score_adjustment = float(item.get("score_adjustment", 0.0))
    except (TypeError, ValueError):
        score_adjustment = 0.0
    score_adjustment = max(-4.0, min(4.0, round(score_adjustment, 1)))

    action_bias = str(item.get("action_bias", "중립")).strip()
    if action_bias not in {"추천", "중립", "회피"}:
        action_bias = "중립"

    risk_level = str(item.get("risk_level", "중간")).strip()
    if risk_level not in {"낮음", "중간", "높음"}:
        risk_level = "중간"

    try:
        confidence = int(round(float(item.get("confidence", 60))))
    except (TypeError, ValueError):
        confidence = 60
    confidence = max(35, min(95, confidence))

    reasons = [str(value).strip() for value in item.get("reasons", []) if str(value).strip()][:2]
    risks = [str(value).strip() for value in item.get("risks", []) if str(value).strip()][:2]
    summary = str(item.get("summary", "")).strip()[:120]

    return {
        "code": entry.code,
        "name": entry.name,
        "market": entry.market,
        "score_adjustment": score_adjustment,
        "action_bias": action_bias,
        "risk_level": risk_level,
        "confidence": confidence,
        "summary": summary,
        "reasons": reasons,
        "risks": risks,
        "source": "openai-aux-signal-v1",
    }


async def generate_stock_aux_signals(data: DailyData, limit: int = 10) -> dict:
    """종목별 OpenAI 보조신호를 생성한다."""
    now = datetime.now(_KST)
    candidates = _collect_candidates(data, limit=limit)
    if not OPENAI_API_KEY or not candidates:
        return {
            "generated_at": now.strftime("%Y-%m-%d %H:%M %Z"),
            "date": now.strftime("%Y-%m-%d"),
            "model": OPENAI_SIGNAL_MODEL,
            "signals": [],
        }

    client = OpenAI(api_key=OPENAI_API_KEY)
    allowed = {item["entry"].code: item["entry"] for item in candidates}
    prompt = _build_prompt(data, candidates)

    for attempt in range(3):
        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=OPENAI_SIGNAL_MODEL,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "JSON만 반환하는 종목 보조신호 엔진이다."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_completion_tokens=2200,
            )
            content = response.choices[0].message.content or "{}"
            payload = _safe_json_loads(content) or {}
            normalized = []
            for item in payload.get("signals", []):
                parsed = _normalize_signal_item(item, allowed)
                if parsed is not None:
                    normalized.append(parsed)

            return {
                "generated_at": now.strftime("%Y-%m-%d %H:%M %Z"),
                "date": now.strftime("%Y-%m-%d"),
                "model": OPENAI_SIGNAL_MODEL,
                "signals": normalized,
            }
        except RateLimitError as exc:
            wait = 15 + attempt * 10
            logger.warning(f"OpenAI 보조신호 RateLimit (시도 {attempt + 1}): {exc} — {wait}초 대기")
            if attempt < 2:
                await asyncio.sleep(wait)
        except APIError as exc:
            logger.warning(f"OpenAI 보조신호 APIError (시도 {attempt + 1}): {exc}")
            if attempt < 2:
                await asyncio.sleep(5)
        except Exception as exc:
            logger.warning(f"OpenAI 보조신호 생성 실패 (시도 {attempt + 1}): {exc}")
            if attempt < 2:
                await asyncio.sleep(5)

    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M %Z"),
        "date": now.strftime("%Y-%m-%d"),
        "model": OPENAI_SIGNAL_MODEL,
        "signals": [],
    }
