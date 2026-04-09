# WealthPulse Domain Map

## Backend domains
- `market_data`: market, macro, live quotes
- `research`: research snapshots, research status, enrichment
- `signal`: signal book construction and candidate selection
- `ai_analysis`: Hanna and derived AI summaries
- `validation`: backtest, walk-forward, diagnostics
- `order_decision`: final buy/sell/hold/block decision contract
- `execution`: paper engine, order execution, fills, portfolio state
- `report`: report composition and market context
- `config`: strategy registry, runtime settings, guardrail policy
- `lab`: optimizer, quant-ops handoff, experiment workflow

## Frontend domains
- `operations`: overview, strategies status, scanner, orders, performance
- `lab`: validation, strategy presets, universe experiments
- `analysis`: reports, alerts, watch decisions, watchlist, research snapshots

## Transition notes
- `apps/api/services/strategy_engine.py` no longer imports private helpers from `routes.reports`; market context is provided by `domains.report.market_context_service`.
- Existing route files remain entrypoints for now, but domain ownership should move away from route-centric organization in later refactor bundles.
- Existing page files remain in `pages/` during this bundle, but canonical ownership already follows the domain split above.
