#!/usr/bin/env bash
set -euo pipefail

cd /home/user/wealth-pulse
exec .venv/bin/python apps/api/scripts/hanna_enrich_runner.py --provider openclaw --market NASDAQ --limit 30 --mode missing_or_stale
