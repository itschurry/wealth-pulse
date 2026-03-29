from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import router as legacy_api_router


app = FastAPI(title="daily-market-brief API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(legacy_api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
