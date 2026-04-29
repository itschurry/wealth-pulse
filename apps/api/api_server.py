#!/usr/bin/env python3
"""FastAPI API server launcher and app definition."""

from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from api_contract import normalize_legacy_response
from server import dispatch_get, dispatch_post


def dispatch_put(path: str, payload: dict) -> tuple[int, dict] | None:
    return dispatch_post(path, payload)


app = FastAPI(title="WealthPulse API", version="2.0.0")
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _query_params_from_request(request: Request) -> dict[str, list[str]]:
    query: dict[str, list[str]] = {}
    for key, value in request.query_params.multi_items():
        query.setdefault(key, []).append(value)
    return query


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/{full_path:path}")
async def legacy_get(full_path: str, request: Request) -> JSONResponse:
    path = f"/api/{full_path}"
    query = _query_params_from_request(request)
    result = await asyncio.to_thread(dispatch_get, path, query)
    if result is None:
        return JSONResponse(status_code=404, content={})
    status, payload = result
    return JSONResponse(status_code=status, content=normalize_legacy_response(path, status, payload))


@app.post("/api/{full_path:path}")
async def legacy_post(full_path: str, request: Request) -> JSONResponse:
    return await _legacy_body_dispatch(full_path, request, dispatch_post)


@app.put("/api/{full_path:path}")
async def legacy_put(full_path: str, request: Request) -> JSONResponse:
    return await _legacy_body_dispatch(full_path, request, dispatch_put)


async def _legacy_body_dispatch(full_path: str, request: Request, dispatcher) -> JSONResponse:
    path = f"/api/{full_path}"
    try:
        raw_body = await request.body()
        body = {} if not raw_body.strip() else await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content=normalize_legacy_response(path, 400, {"ok": False, "error": "invalid_json"}),
        )
    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content=normalize_legacy_response(path, 400, {"ok": False, "error": "json_object_required"}),
        )
    result = await asyncio.to_thread(dispatcher, path, body)
    if result is None:
        return JSONResponse(status_code=404, content={})
    status, response = result
    return JSONResponse(status_code=status, content=normalize_legacy_response(path, status, response))


def main() -> None:
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8001"))
    uvicorn.run("api_server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
