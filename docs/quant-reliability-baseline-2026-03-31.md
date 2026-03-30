# Quant / backtest / reliability baseline update — 2026-03-31

## What changed

### 1) Report generation now points at the real template directory
- Fixed `apps/api/reporter/report_generator.py` to load templates from `apps/api/templates` first.
- Kept a fallback to the old repo-level path so the change stays low-risk.
- Added a regression test that actually renders HTML from the app template.

### 2) Report fallback now reads optimized params from the correct path
- Fixed `apps/api/routes/reports.py` to load `apps/api/config/optimized_params.json` correctly.
- Removed the previous broken path logic that could silently skip optimization metadata.
- Fallback today-picks candidates now consistently expose:
  - `reliability`
  - `strategy_reliability`
  - `validation_trades`
  - `validation_sharpe`
  - `train_trade_count`
  - `max_drawdown_pct`
  - `reliability_reason`
  - `strategy_scorecard`

### 3) Report signal mapping is more consistent
- `_map_strategy_signal()` now prefers explicit `validation_snapshot` values when they exist, instead of falling back too early to EV calibration fields.
- This prevents report rows from showing weaker or stale validation metadata when fresher snapshot data is available.

### 4) Report cache logic was extracted into a lightweight shared helper
- Added `apps/api/services/report_cache.py`.
- `routes/reports.py` now uses the helper instead of carrying its own cache implementation.
- This makes cache behavior easier to test and reduces route import coupling.

### 5) Report-related imports are lighter and safer
- `routes/reports.py` now lazily imports storage and live-market dependencies.
- `apps/api/cache.py` no longer imports the KIS client just for type hints.
- Result: report/cache tests no longer drag in unrelated runtime configuration during import.

## Why it mattered
- The report generator could fail at runtime simply because it was looking in the wrong template directory.
- Today-picks fallback could quietly miss optimizer output because it was checking the wrong file path.
- Report rows were not fully consistent about where reliability/validation fields came from.
- Import-heavy report modules made regression tests brittle and hid simple failures behind unrelated dependency errors.

## Current reliability policy
The shared reliability gate remains conservative and centralized in `services/reliability_policy.py` / `services/reliability_service.py`.

### Validation thresholds
- Minimum train trades: **20**
- Reliable train trades: **30**
- Minimum validation signals: **8**
- Filter Sharpe floor: **0.20**
- Reliable Sharpe floor: **0.35**
- Hard drawdown filter: **-30%**
- Reliable drawdown ceiling: **-25%**

### Labels
- **high**: fully reliable
- **medium**: borderline but still passes minimum gate
- **low**: fails due to weak Sharpe or excessive drawdown
- **insufficient**: too little training or validation evidence

### Overlay policy
- Per-symbol overlay: **high only**
- Global overlay fallback priority:
  1. `high_only`
  2. `medium_fallback`
  3. `all_results_fallback`

## Test coverage added / verified
### Newly added or integrated coverage
- `apps/api/tests/test_optimizer_pipeline_regression.py`
  - optimizer global overlay source
  - saved output structure
  - scorecard / tail-risk / overlay metadata preservation
- `apps/api/tests/test_validation_pipeline_regression.py`
  - extended backtest scorecard structure
  - walk-forward segment and summary structure
- `apps/api/tests/test_reports_regression.py`
  - fallback today-picks enrichment from optimized params
  - report signal mapping preference for validation snapshot data
- `apps/api/tests/test_report_generator.py`
  - real HTML rendering against app template directory
- `apps/api/tests/test_reports_cache.py`
  - cache helper behavior after extraction

### Verification run
- `PYTHONPATH=apps/api .venv-test/bin/python -m pytest apps/api/tests -q`
- Result: **61 passed**

## Docker verification
- Ran `docker compose build`
- Result: **api Built / web Built**

## Still risky / not solved yet
- This pass improves offline reliability and reporting consistency, but it does **not** prove live market-data quality.
- No new live trading behavior was introduced or validated.
- Report fallback still depends on optimizer output existing; if optimization was never run, fallback remains recommendation-only.
- Walk-forward and optimizer tests are regression-oriented; they do not guarantee strategy edge in future market regimes.
- The repo still relies on runtime environment correctness for external providers (KIS, OpenAI, Ollama, Telegram, etc.).

## Recommended next steps for a non-expert owner
1. Keep this baseline and avoid widening scope before using it for a few cycles.
2. Add one small end-to-end smoke test that renders a report from saved fixtures and checks the main API payload shape.
3. Add a scheduled check that warns when `optimized_params.json` is missing or stale.
4. Add one UI-level regression check for the report page consuming the reliability fields now exposed more consistently.
5. If live usage increases, add explicit stale-data markers to report payloads so fallback output is harder to over-trust.
