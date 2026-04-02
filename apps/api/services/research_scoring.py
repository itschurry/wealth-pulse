from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from services.research_contract import normalize_components, normalize_tags, normalize_warning_codes
from services.research_store import load_research_snapshot_for_timestamp


def _parse_datetime(value: Any):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = __import__("datetime").datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=__import__("datetime").timezone.utc)
    return parsed.astimezone(__import__("datetime").timezone.utc)


@dataclass
class ResearchScoreRequest:
    symbol: str
    market: str
    timestamp: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchScoreResult:
    symbol: str
    market: str
    research_score: float | None
    components: dict[str, float]
    warnings: list[str]
    tags: list[str]
    summary: str
    ttl_minutes: int
    generated_at: str
    status: str = "healthy"
    source: str = "null"
    available: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResearchScorer(Protocol):
    def score(self, request: ResearchScoreRequest) -> ResearchScoreResult:
        ...


class NullResearchScorer:
    def score(self, request: ResearchScoreRequest) -> ResearchScoreResult:
        return ResearchScoreResult(
            symbol=request.symbol,
            market=request.market,
            research_score=None,
            components={},
            warnings=["research_unavailable"],
            tags=[],
            summary="연구 점수 제공자가 설정되지 않아 quant+risk 기준으로 계속 진행합니다.",
            ttl_minutes=5,
            generated_at=request.timestamp,
            status="research_unavailable",
            source="null",
            available=False,
        )


class StoredResearchScorer:
    def __init__(self, *, provider: str = "openclaw") -> None:
        self.provider = str(provider or "openclaw").strip().lower() or "openclaw"

    def score(self, request: ResearchScoreRequest) -> ResearchScoreResult:
        snapshot = load_research_snapshot_for_timestamp(request.symbol, request.market, request.timestamp, provider=self.provider)
        if not isinstance(snapshot, dict):
            return ResearchScoreResult(
                symbol=request.symbol,
                market=request.market,
                research_score=None,
                components={},
                warnings=["research_unavailable"],
                tags=[],
                summary="OpenClaw research snapshot이 없어 quant+risk 기준으로 계속 진행합니다.",
                ttl_minutes=5,
                generated_at=request.timestamp,
                status="missing",
                source=self.provider,
                available=False,
            )

        ttl_minutes = max(1, min(1440, int(snapshot.get("ttl_minutes") or 120)))
        generated_at = str(snapshot.get("generated_at") or request.timestamp)
        generated_dt = _parse_datetime(generated_at)
        reference_dt = _parse_datetime(request.timestamp)
        if generated_dt is None or reference_dt is None or reference_dt > generated_dt + __import__("datetime").timedelta(minutes=ttl_minutes):
            return ResearchScoreResult(
                symbol=request.symbol,
                market=request.market,
                research_score=None,
                components={},
                warnings=["research_unavailable"],
                tags=[],
                summary="OpenClaw research snapshot이 오래되어 quant+risk 기준으로 계속 진행합니다.",
                ttl_minutes=ttl_minutes,
                generated_at=generated_at,
                status="stale_ingest",
                source=self.provider,
                available=False,
            )

        return ResearchScoreResult(
            symbol=request.symbol,
            market=request.market,
            research_score=snapshot.get("research_score"),
            components=normalize_components(snapshot.get("components")),
            warnings=normalize_warning_codes(snapshot.get("warnings")),
            tags=normalize_tags(snapshot.get("tags")),
            summary=str(snapshot.get("summary") or ""),
            ttl_minutes=ttl_minutes,
            generated_at=generated_at,
            status="healthy",
            source=self.provider,
            available=True,
        )


_SCORER_CACHE_KEY: str | None = None
_SCORER_INSTANCE: ResearchScorer | None = None


def get_research_scorer() -> ResearchScorer:
    global _SCORER_CACHE_KEY, _SCORER_INSTANCE

    provider = "openclaw"
    cache_key = provider

    if _SCORER_INSTANCE is not None and _SCORER_CACHE_KEY == cache_key:
        return _SCORER_INSTANCE

    _SCORER_INSTANCE = StoredResearchScorer(provider=provider)
    _SCORER_CACHE_KEY = cache_key
    return _SCORER_INSTANCE
