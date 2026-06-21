from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any

import orjson

_JSON_FILE_CACHE: dict[str, tuple[tuple[int, int], Any]] = {}
_JSON_FILE_CACHE_LOCK = RLock()


def json_load_bytes(raw: bytes) -> Any:
    return orjson.loads(raw)


def json_dump_text(payload: Any, *, indent: int | None = None) -> str:
    option = orjson.OPT_INDENT_2 if indent else 0
    return orjson.dumps(payload, option=option).decode("utf-8")


def json_dump_compact(payload: Any) -> str:
    return orjson.dumps(payload).decode("utf-8")


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
