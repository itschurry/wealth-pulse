from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.server import dispatch_get, dispatch_post


router = APIRouter()


def _query_params_from_request(request: Request) -> dict[str, list[str]]:
    query: dict[str, list[str]] = {}
    for key, value in request.query_params.multi_items():
        query.setdefault(key, []).append(value)
    return query


@router.get("/api/{full_path:path}")
async def legacy_get(full_path: str, request: Request) -> JSONResponse:
    result = dispatch_get(f"/api/{full_path}", _query_params_from_request(request))
    if result is None:
        return JSONResponse(status_code=404, content={})
    status, payload = result
    return JSONResponse(status_code=status, content=payload)


@router.post("/api/{full_path:path}")
async def legacy_post(full_path: str, request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    result = dispatch_post(f"/api/{full_path}", payload)
    if result is None:
        return JSONResponse(status_code=404, content={})
    status, response = result
    return JSONResponse(status_code=status, content=response)
