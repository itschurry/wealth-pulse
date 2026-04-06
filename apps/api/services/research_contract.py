from __future__ import annotations

from typing import Any


ALLOWED_WARNING_CODES = {
    "headline_stronger_than_body",
    "already_extended_intraday",
    "low_evidence_density",
    "theme_recycled",
    "contrarian_flow_risk",
    "policy_uncertainty",
    "liquidity_mismatch",
    "too_many_similar_news",
}


def clamp_normalized_score(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def normalize_components(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, float] = {}
    for key, item in value.items():
        score = clamp_normalized_score(item)
        if score is None:
            continue
        normalized[str(key)] = score
    return normalized


def normalize_warning_codes(value: Any) -> list[str]:
    warnings: list[str] = []
    for item in value or []:
        code = str(item).strip()
        if code and code in ALLOWED_WARNING_CODES:
            warnings.append(code)
    return list(dict.fromkeys(warnings))


def normalize_and_validate_warning_codes(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("warnings_must_be_list")

    normalized: list[str] = []
    for item in value:
        code = str(item).strip()
        if not code:
            raise ValueError("warning_code_empty")
        if code not in ALLOWED_WARNING_CODES:
            raise ValueError("warning_code_unsupported")
        normalized.append(code)

    return list(dict.fromkeys(normalized))


def normalize_tags(value: Any) -> list[str]:
    tags: list[str] = []
    for item in value or []:
        tag = str(item).strip()
        if tag:
            tags.append(tag)
    return list(dict.fromkeys(tags))
