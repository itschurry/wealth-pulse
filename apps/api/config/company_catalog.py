"""Snapshot-backed company catalog used across API lookups."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from config.settings import LOGS_DIR


@dataclass(frozen=True)
class CompanyCatalogEntry:
    name: str
    code: str
    market: str
    sector: str
    aliases: tuple[str, ...]


_ALLOWED_MARKETS = {"KOSPI", "KOSDAQ", "NASDAQ", "NYSE", "AMEX", "US"}
_CATALOG_CACHE: dict[str, list[CompanyCatalogEntry]] = {}
_UNIVERSE_ROOT = LOGS_DIR / "universe_snapshots"
_SNAPSHOT_SOURCES: tuple[tuple[str, Path], ...] = (
    ("kospi", _UNIVERSE_ROOT / "kospi" / "latest.json"),
    ("sp500", _UNIVERSE_ROOT / "sp500" / "latest.json"),
)

_US_SUFFIX_PATTERN = re.compile(
    r"\b(incorporated|inc|corp|corporation|company|co|holdings|holding|group|class\s+[a-z])\b",
    re.IGNORECASE,
)


def _normalize_market(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"US", "NASDAQ", "NYSE", "AMEX"}:
        return "NASDAQ"
    if normalized == "KRX":
        return "KOSPI"
    return normalized


def _read_snapshot(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"snapshot payload must be an object: {path}")
    return payload


def _normalize_alias(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _derive_aliases(name: str, code: str) -> tuple[str, ...]:
    raw_candidates = {
        name,
        name.lower(),
        _US_SUFFIX_PATTERN.sub("", name).strip(" ,.-"),
        _US_SUFFIX_PATTERN.sub("", name).strip(" ,.-").lower(),
        code,
        code.lower(),
    }
    aliases: list[str] = []
    for candidate in raw_candidates:
        alias = _normalize_alias(candidate)
        if alias and alias not in aliases:
            aliases.append(alias)
    return tuple(aliases)


def _normalize_sector(value: str | None, market: str) -> str:
    sector = str(value or "").strip()
    if sector:
        return sector
    return "국내주식" if market in {"KOSPI", "KOSDAQ"} else "미국주식"


def _load_catalog_entries() -> list[CompanyCatalogEntry]:
    entries: list[CompanyCatalogEntry] = []
    seen: set[tuple[str, str]] = set()
    missing_sources: list[str] = []

    for source_name, path in _SNAPSHOT_SOURCES:
        if not path.exists():
            missing_sources.append(str(path))
            continue

        payload = _read_snapshot(path)
        symbols = payload.get("symbols") if isinstance(payload.get("symbols"), list) else []
        for row in symbols:
            if not isinstance(row, dict):
                continue
            code = str(row.get("code") or "").strip().upper()
            name = str(row.get("name") or code).strip()
            market = _normalize_market(str(row.get("market") or payload.get("market") or "").strip())
            if not code or not name or market not in _ALLOWED_MARKETS:
                continue
            key = (market, code)
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                CompanyCatalogEntry(
                    name=name,
                    code=code,
                    market=market,
                    sector=_normalize_sector(row.get("sector"), market),
                    aliases=_derive_aliases(name, code),
                )
            )

    if entries:
        return entries

    raise FileNotFoundError(
        "Universe snapshot catalog is unavailable. Expected snapshot JSON files under: "
        + ", ".join(missing_sources or [str(path) for _, path in _SNAPSHOT_SOURCES])
    )


def get_company_catalog(scope: str = "core") -> list[CompanyCatalogEntry]:
    normalized_scope = str(scope or "core").strip().lower()
    if normalized_scope not in {"core", "live"}:
        normalized_scope = "core"

    cached = _CATALOG_CACHE.get(normalized_scope)
    if cached is not None:
        return list(cached)

    catalog = _load_catalog_entries()
    _CATALOG_CACHE["core"] = list(catalog)
    _CATALOG_CACHE["live"] = list(catalog)
    return list(_CATALOG_CACHE[normalized_scope])
