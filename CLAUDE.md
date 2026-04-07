# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WealthPulse is a full-stack investment operations platform combining quantitative trading and AI-driven research. It runs a continuous Research → Validation → Execution → Observability loop.

- **Backend**: Python/FastAPI (async) at `apps/api/`
- **Frontend**: React 19 + TypeScript + Vite at `apps/web/`
- **Storage**: SQLite + JSON files in `storage/`

## Commands

### Backend (Python/FastAPI)

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp apps/api/.env.example apps/api/.env  # then fill in API keys

# Run
cd apps/api
python3 api_server.py          # API server on http://127.0.0.1:8001

# Tests
cd apps/api
python -m unittest discover -s tests                          # All tests
python -m unittest tests.test_quant_ops_workflow              # Single file
python -m unittest tests.test_quant_ops_workflow.TestQuantOpsWorkflow.test_create_and_track_candidate  # Single test
```

### Frontend (Node.js/React)

```bash
cd apps/web
npm install
npm run dev      # Dev server on http://127.0.0.1:5173 (proxies to API)
npm run build    # Production build to dist/
npm run preview  # Preview production build
npm run lint     # ESLint
```

### Docker

```bash
docker compose up -d --build   # API at :8001, Web at :8081
```

## Architecture

### Backend Layer Structure

**`apps/api/`**:
- `api_server.py` — FastAPI app entry point
- `server.py` — Route dispatcher mapping
- `routes/` — 15+ route handlers (reports, trading, research, validation, quant_ops, etc.)
- `services/` — Business logic layer (35+ services); the main logic lives here
- `domains/report/` — Report generation context
- `collectors/` — External data feed collectors
- `broker/` — KIS broker integration
- `tests/` — 40+ unittest files

### Frontend Layer Structure

**`apps/web/src/`**:
- `App.tsx` — Main router (6 pages + tabs)
- `pages/` — Full-page views (Reports, Backtest/Validation, Strategies, PaperPortfolio, Performance, Home)
- `components/` — Reusable UI components
- `hooks/` — Custom React hooks
- `api/` — API client calls
- `domains/` — Client-side domain/business logic
- `adapters/` — Data transformers
- `lib/` — Feature flags, validation config storage

### Two Operating Modes

- **Quant path**: Backtest → Walk-forward → Monte Carlo optimization → Re-validate → Candidates
- **Research/AI path**: Daily picks → LLM recommendations → Candidates

These paths **do not converge**; they are **union-merged** at runtime. The `runtime_candidate_source_mode` setting controls which paths are active: `quant_only` (default), `research_only`, or `hybrid`.

### Candidate Lifecycle

Candidates flow through states tracked in `storage/logs/quant_ops_state.json`:
`latest` → `candidate` → `approved` → `saved` → `runtime-applied`

### Key Stateful Files

- `storage/logs/quant_ops_state.json` — Candidate lifecycle state
- `storage/logs/backtest_validation_settings.json` — Shared baseline backtest settings
- `optimized_params.json` / `runtime_optimized_params.json` — Optimizer results vs. applied params
- `storage/reports/` — SQLite + cached JSON reports

### API Response Convention

Routes do not follow strict REST conventions. Always check three things:
1. HTTP status code
2. Presence of `ok` field
3. Presence of `error` field

### Execution Modes

`EXECUTION_MODE=paper` (default, internal virtual account) vs. `EXECUTION_MODE=live` (real KIS broker — review `docs/live-trading-checklist.md` before enabling).

## Key Environment Variables

Configured in `apps/api/.env` (copy from `.env.example`):

| Variable | Purpose |
|---|---|
| `FRED_API_KEY`, `ECOS_API_KEY`, `DART_API_KEY` | Market data sources |
| `KIS_APP_KEY`, `KIS_APP_SECRET`, etc. | Korean Investment Securities broker |
| `LLM_PROVIDER` | `openai` or `ollama` |
| `OPENAI_API_KEY` / `OLLAMA_HOST`, `OLLAMA_MODEL` | LLM backend |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Notifications |
| `EXECUTION_MODE` | `paper` or `live` |

Frontend: `apps/web/.env` — set `VITE_PROXY_API_TARGET=http://127.0.0.1:8001`

## Documentation

- `docs/api.md` — Full API reference with curl examples
- `docs/usage.md` — Product and operation manual
- `docs/01-end-to-end-manual.md` — Full workflow walkthrough
- `docs/02-architecture-and-roles.md` — Architecture deep-dive
- `docs/09-guardrail-policy-and-ui-guide.md` — Risk guardrail policy
