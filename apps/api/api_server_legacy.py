#!/usr/bin/env python3
"""Legacy HTTP server launcher preserved during FastAPI migration."""

from api.server import run


def main() -> None:
    run()


if __name__ == "__main__":
    main()
