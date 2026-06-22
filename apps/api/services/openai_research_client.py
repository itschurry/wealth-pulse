from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from config.settings import OPENAI_API_KEY, OPENAI_RESEARCH_MAX_OUTPUT_TOKENS, OPENAI_RESEARCH_MODEL


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_OPENAI_RESEARCH_MODEL = "gpt-4.1"
DEFAULT_MAX_OUTPUT_TOKENS = 6000


RESEARCH_SNAPSHOT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
    "required": [
        "symbol",
        "market",
        "confidence",
        "rating",
        "action",
        "summary",
        "bull_case",
        "bear_case",
        "catalysts",
        "risks",
        "invalidation_trigger",
        "trade_plan",
        "technical_features",
        "news_inputs",
        "evidence",
        "data_quality",
    ],
    "properties": {
        "symbol": {"type": "string"},
        "market": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "research_score": {"type": "number", "minimum": 0, "maximum": 1},
        "rating": {"type": "string", "enum": ["strong_buy", "overweight", "hold", "underweight", "sell"]},
        "action": {"type": "string", "enum": ["buy", "buy_watch", "hold", "reduce", "sell", "block"]},
        "summary": {"type": "string"},
        "bull_case": {"type": "array", "items": {"type": "string"}},
        "bear_case": {"type": "array", "items": {"type": "string"}},
        "catalysts": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "invalidation_trigger": {
            "type": "object",
            "additionalProperties": True,
            "required": ["condition", "stop_loss"],
            "properties": {
                "condition": {"type": "string"},
                "stop_loss": {"type": "number"},
                "reason": {"type": "string"},
            },
        },
        "trade_plan": {
            "type": "object",
            "additionalProperties": True,
            "required": ["size_intent_pct", "entry", "stop_loss", "take_profit"],
            "properties": {
                "size_intent_pct": {"type": "number", "minimum": 0, "maximum": 40},
                "entry": {"type": "string"},
                "stop_loss": {"type": "number"},
                "take_profit": {"type": "number"},
            },
        },
        "technical_features": {"type": "object", "additionalProperties": True},
        "news_inputs": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        "evidence": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        "data_quality": {"type": "object", "additionalProperties": True},
        "components": {"type": "object", "additionalProperties": True},
        "tags": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "time_horizon_days": {"type": "integer"},
    },
}


def _api_key() -> str:
    key = str(os.getenv("OPENAI_API_KEY") or OPENAI_API_KEY or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY_required")
    return key


def _model() -> str:
    return str(os.getenv("OPENAI_RESEARCH_MODEL") or OPENAI_RESEARCH_MODEL or DEFAULT_OPENAI_RESEARCH_MODEL).strip() or DEFAULT_OPENAI_RESEARCH_MODEL


def _max_output_tokens() -> int:
    raw = os.getenv("OPENAI_RESEARCH_MAX_OUTPUT_TOKENS") or OPENAI_RESEARCH_MAX_OUTPUT_TOKENS
    try:
        return max(DEFAULT_MAX_OUTPUT_TOKENS, min(12000, int(raw or DEFAULT_MAX_OUTPUT_TOKENS)))
    except ValueError:
        raise ValueError("OPENAI_RESEARCH_MAX_OUTPUT_TOKENS_invalid") from None


def _extract_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return str(response["output_text"]).strip()
    fragments: list[str] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                fragments.append(text)
    return "\n".join(fragment.strip() for fragment in fragments if fragment.strip()).strip()


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = str(text or "").strip()
    if not cleaned:
        raise RuntimeError("openai_response_empty_text")
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("openai_response_json_missing") from None
        parsed = json.loads(cleaned[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("openai_response_must_be_object")
    return parsed


def build_openai_research_prompt(feature_pack: dict[str, Any]) -> str:
    return (
        "너는 WealthPulse의 공격형 한국 주식 리서치 판단 엔진이다.\n"
        "Python이 이미 뉴스, 공시, 공식 링크, 후보 점수, 기술 지표를 수집했다. 너는 새 데이터를 찾지 말고 입력된 source_inputs와 target만 해석해.\n"
        "목표는 너무 보수적으로 hold만 내는 게 아니라, 근거가 충분한 종목을 빠르게 buy 또는 buy_watch로 승격하는 것이다.\n"
        "단, 뉴스 URL, published_at, 공식 evidence, 기술 지표가 없으면 buy/buy_watch를 내지 마라.\n"
        "최근 72시간 뉴스가 긍정적이고, 기술 지표가 과열이 아니며, 공식 evidence가 있으면 overweight/buy_watch 이상을 적극 검토해라.\n"
        "close_vs_sma20 또는 close_vs_sma60이 1보다 크고 volume_ratio가 1 이상이면 추세 확인으로 본다.\n"
        "rsi14가 88 이상이면 신규 buy는 피하고 buy_watch 이하로 낮춰라.\n"
        "catalysts는 앞으로 1~20거래일 안에 실제 가격 재평가를 만들 수 있는 이벤트만 적어라. 뉴스 반복, 막연한 업황 기대, 이미 가격에 반영된 재료는 catalyst가 아니다.\n"
        "bear_case는 bull_case의 반대편을 실제로 공격해야 한다. 수요 둔화, 마진 훼손, 밸류에이션 부담, 수급 반전, 정책/공시 불확실성 중 입력 근거로 확인되는 약점을 적어라.\n"
        "invalidation_trigger.condition은 매수 논리가 깨지는 단일 조건을 써라. invalidation_trigger.stop_loss는 현재가보다 낮은 숫자로 적어라.\n"
        "trade_plan은 size_intent_pct, entry, stop_loss, take_profit을 반드시 포함해라. 현재가가 있으면 stop_loss는 현재가 대비 -5%, take_profit은 +12% 기준 가격으로 둬라.\n"
        "현재가나 기술 지표가 없으면 buy/buy_watch를 내지 마라.\n"
        "주문 실행은 하지 마라. trade_plan.size_intent_pct는 의도만 적고 실제 수량은 WealthPulse risk guard가 다시 계산한다.\n"
        "출력은 짧게 써라. summary는 한 문장, bull_case/bear_case/catalysts/risks는 각각 최대 3개만 써라.\n"
        "news_inputs와 evidence는 Python이 ingest 직전에 source_inputs를 다시 붙인다. 출력 JSON에서는 빈 배열 []로 둬라.\n"
        "technical_features는 핵심 숫자만 복사해라. source_inputs 전체를 JSON 출력에 반복하지 마라.\n"
        "반드시 Research Snapshot v2 JSON 하나만 반환해.\n\n"
        f"{json.dumps(feature_pack, ensure_ascii=False, sort_keys=True)}"
    )


def call_openai_research(feature_pack: dict[str, Any], *, timeout: int = 300) -> dict[str, Any]:
    payload = {
        "model": _model(),
        "instructions": (
            "너는 자동매매 시스템의 리서치 분석기다. 입력 데이터 밖의 사실을 만들지 말고, "
            "근거가 충분하면 공격적으로 판단하되 JSON schema를 지켜라."
        ),
        "input": build_openai_research_prompt(feature_pack),
        "max_output_tokens": _max_output_tokens(),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "wealthpulse_research_snapshot_v2",
                "schema": RESEARCH_SNAPSHOT_SCHEMA,
                "strict": False,
            }
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=max(1, int(timeout))) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, dict):
        raise RuntimeError("openai_response_invalid")
    if parsed.get("error"):
        raise RuntimeError(f"openai_response_error:{parsed['error']}")
    if str(parsed.get("status") or "").lower() == "incomplete":
        details = parsed.get("incomplete_details") if isinstance(parsed.get("incomplete_details"), dict) else {}
        raise RuntimeError(f"openai_response_incomplete:{details.get('reason') or 'unknown'}")
    return _parse_json(_extract_text(parsed))
