#!/usr/bin/env python3
"""Compatibility wrapper for the relocated API server entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path


API_DIR = Path(__file__).resolve().parent / "apps" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from api_server import main  # type: ignore  # noqa: E402


if __name__ == "__main__":
    main()
