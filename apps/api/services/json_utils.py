from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any

try:
    import orjson as _orjson  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional fast path
    _orjson = None

_JSON_FILE_CACHE: dict[str, tuple[tuple[int, int], Any]] = {}
_JSON_FILE_CACHE_LOCK = RLock()


def json_load_bytes(raw: bytes) -> Any:
    if _orjson is not None:
        return _orjson.loads(raw)
    return json.loads(raw.decode("utf-8"))


def json_dump_text(payload: Any, *, indent: int | None = None) -> str:
    if _orjson is not None:
        option = 0
        if indent:
            option |= _orjson.OPT_INDENT_2
        return _orjson.dumps(payload, option=option).decode("utf-8")
    return json.dumps(payload, ensure_ascii=False, indent=indent)


def json_dump_compact(payload: Any) -> str:
    if _orjson is not None:
        return _orjson.dumps(payload).decode("utf-8")
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def read_json_file_cached(path: Path) -> Any:
    cache_key = str(path)
    try:
        stat = path.stat()
    except OSError:
        with _JSON_FILE_CACHE_LOCK:
            _JSON_FILE_CACHE.pop(cache_key, None)
        raise

    signature = (int(stat.st_mtime_ns), int(stat.st_size))
    with _JSON_FILE_CACHE_LOCK:
        cached = _JSON_FILE_CACHE.get(cache_key)
        if cached and cached[0] == signature:
            return cached[1]

    raw = path.read_bytes()
    payload = json_load_bytes(raw)
    with _JSON_FILE_CACHE_LOCK:
        _JSON_FILE_CACHE[cache_key] = (signature, payload)
    return payload


def clear_json_file_cache(path: Path | None = None) -> None:
    with _JSON_FILE_CACHE_LOCK:
        if path is None:
            _JSON_FILE_CACHE.clear()
            return
        _JSON_FILE_CACHE.pop(str(path), None)
