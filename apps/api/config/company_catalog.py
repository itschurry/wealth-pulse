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

_STATIC_FALLBACK_ROWS: tuple[dict[str, object], ...] = (
    {
        "name": "IBK기업은행",
        "code": "024110",
        "market": "KOSPI",
        "sector": "은행",
        "aliases": ("IBK", "Industrial Bank of Korea", "기업은행"),
    },
    {
        "name": "LS ELECTRIC",
        "code": "010120",
        "market": "KOSPI",
        "sector": "전기장비",
        "aliases": ("LS", "LS Electric", "엘에스일렉트릭"),
    },
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


def _append_entry(entries: list[CompanyCatalogEntry], seen: set[tuple[str, str]], row: dict[str, object], default_market: str = "") -> None:
    code = str(row.get("code") or "").strip().upper()
    name = str(row.get("name") or code).strip()
    market = _normalize_market(str(row.get("market") or default_market or "").strip())
    if not code or not name or market not in _ALLOWED_MARKETS:
        return
    key = (market, code)
    extra_aliases = tuple(_normalize_alias(alias) for alias in (row.get("aliases") or ()) if _normalize_alias(str(alias)))
    derived_aliases = _derive_aliases(name, code)
    aliases: list[str] = []
    for alias in (*derived_aliases, *extra_aliases):
        if alias and alias not in aliases:
            aliases.append(alias)
    if key in seen:
        for index, existing in enumerate(entries):
            if (existing.market, existing.code) != key:
                continue
            merged_aliases: list[str] = list(existing.aliases)
            for alias in aliases:
                if alias and alias not in merged_aliases:
                    merged_aliases.append(alias)
            entries[index] = CompanyCatalogEntry(
                name=existing.name,
                code=existing.code,
                market=existing.market,
                sector=existing.sector,
                aliases=tuple(merged_aliases),
            )
            return
        return
    seen.add(key)
    entries.append(
        CompanyCatalogEntry(
            name=name,
            code=code,
            market=market,
            sector=_normalize_sector(str(row.get("sector") or ""), market),
            aliases=tuple(aliases),
        )
    )



def _load_catalog_entries() -> list[CompanyCatalogEntry]:
    entries: list[CompanyCatalogEntry] = []
    seen: set[tuple[str, str]] = set()
    missing_sources: list[str] = []

    for _source_name, path in _SNAPSHOT_SOURCES:
        if not path.exists():
            missing_sources.append(str(path))
            continue

        payload = _read_snapshot(path)
        symbols = payload.get("symbols") if isinstance(payload.get("symbols"), list) else []
        for row in symbols:
            if isinstance(row, dict):
                _append_entry(entries, seen, row, str(payload.get("market") or ""))

    for row in _STATIC_FALLBACK_ROWS:
        _append_entry(entries, seen, row)

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
