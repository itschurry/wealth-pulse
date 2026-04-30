from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


ApiPayload = dict[str, Any]

_WRAPPED_PREFIXES: tuple[str, ...] = (
    "/api/signals",
    "/api/validation",
    "/api/quant-ops",
    "/api/runtime",
    "/api/performance/summary",
    "/api/reports/operations",
)


def should_wrap_response(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _WRAPPED_PREFIXES)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _trace_id_from_payload(payload: ApiPayload) -> str | None:
    trace_id = payload.get("trace_id")
    if isinstance(trace_id, str) and trace_id.strip():
        return trace_id.strip()
    return None


def build_meta(payload: ApiPayload, *, source: str) -> ApiPayload:
    version = payload.get("version")
    updated_at = payload.get("updated_at")
    meta_source = payload.get("source")
    return {
        "version": str(version or "2026-04-bundle-c1"),
        "updated_at": str(updated_at or _utc_now_iso()),
        "source": str(meta_source or source),
        "trace_id": _trace_id_from_payload(payload) or str(uuid4()),
    }


def is_enveloped_payload(payload: Any) -> bool:
    return isinstance(payload, dict) and isinstance(payload.get("meta"), dict) and (
        "data" in payload or "error" in payload
    )


def build_success_envelope(payload: ApiPayload, *, source: str) -> ApiPayload:
    if is_enveloped_payload(payload):
        return payload
    body = dict(payload)
    for key in ("version", "updated_at", "source", "trace_id"):
        body.pop(key, None)
    return {
        "data": body,
        "meta": build_meta(payload, source=source),
    }


def _normalize_error_details(payload: ApiPayload) -> ApiPayload:
    details = payload.get("details")
    if isinstance(details, dict):
        return details
    error_value = payload.get("error")
    if isinstance(error_value, dict):
        return error_value
    body = dict(payload)
    body.pop("error_code", None)
    body.pop("message", None)
    body.pop("error", None)
    body.pop("version", None)
    body.pop("updated_at", None)
    body.pop("source", None)
    body.pop("trace_id", None)
    return body


def build_error_envelope(payload: ApiPayload, *, source: str, status_code: int) -> ApiPayload:
    if is_enveloped_payload(payload):
        return payload
    error_code = payload.get("error_code")
    message = payload.get("message") or payload.get("error")
    if not isinstance(message, str) or not message.strip():
        message = "request_failed"
    if not isinstance(error_code, str) or not error_code.strip():
        error_code = f"http_{status_code}"
    return {
        "error": {
            "error_code": error_code,
            "message": message,
            "details": _normalize_error_details(payload),
        },
        "meta": build_meta(payload, source=source),
    }


def normalize_api_response(path: str, status_code: int, payload: Any) -> Any:
    if not should_wrap_response(path) or not isinstance(payload, dict):
        return payload
    source = path.removeprefix("/api/").replace("/", "_") or "api"
    if status_code >= 400:
        return build_error_envelope(payload, source=source, status_code=status_code)
    return build_success_envelope(payload, source=source)
