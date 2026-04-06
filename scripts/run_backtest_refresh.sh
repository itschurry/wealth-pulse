#!/usr/bin/env bash
set -euo pipefail

cd /home/user/wealth-pulse
exec .venv/bin/python apps/api/scripts/build_backtest_universes.py
