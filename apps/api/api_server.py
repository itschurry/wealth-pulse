#!/usr/bin/env python3
"""FastAPI API server launcher."""

import os

import uvicorn


def main() -> None:
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8001"))
    uvicorn.run("app.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
