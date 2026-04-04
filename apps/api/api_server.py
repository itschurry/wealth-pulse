#!/usr/bin/env python3
"""FastAPI API server launcher and app definition."""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from server import dispatch_get, dispatch_post


app = FastAPI(title="WealthPulse API", version="2.0.0")
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
    result = dispatch_get(f"/api/{full_path}", _query_params_from_request(request))
    if result is None:
        return JSONResponse(status_code=404, content={})
    status, payload = result
    return JSONResponse(status_code=status, content=payload)


@app.post("/api/{full_path:path}")
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


def main() -> None:
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8001"))
    uvicorn.run("api_server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
