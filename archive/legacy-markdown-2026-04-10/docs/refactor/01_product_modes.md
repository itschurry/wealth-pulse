# WealthPulse Product Modes

## Canonical modes

### operations
- Purpose: automatic trading execution, order decision review, fill tracking, runtime health
- Canonical routes:
  - `/operations/overview`
  - `/operations/strategies`
  - `/operations/scanner`
  - `/operations/orders`
  - `/operations/performance`
- Allowed actions:
  - refresh runtime data
  - start/stop/pause paper engine
  - inspect approved or applied strategy state
  - inspect blocked reasons and fills
- Forbidden actions:
  - edit strategy parameters
  - create, clone, or delete strategy presets
  - run backtest or walk-forward validation directly from operations

### lab
- Purpose: backtest, parameter search, strategy experiments, revalidation
- Canonical routes:
  - `/lab/validation`
  - `/lab/strategies`
  - `/lab/universe`
- Allowed actions:
  - edit draft settings
  - save candidate configuration
  - clone or delete presets
  - run validation and experiment flows
- Promotion rule:
  - `saved -> approved -> applied`

### analysis
- Purpose: research, market data inspection, AI insight review
- Canonical routes:
  - `/analysis/brief`
  - `/analysis/alerts`
  - `/analysis/watch-decisions`
  - `/analysis/watchlist`
  - `/analysis/research`
- Allowed actions:
  - inspect reports and market context
  - manage watchlist for analysis
  - query research snapshots
- Forbidden actions:
  - place or approve orders
  - mutate runtime configuration

## Legacy route handling
- `/console/*`, `/reports/*`, `/backtest`, `/signals`, `/paper`, `/overview` remain redirect-only aliases.
- Navigation, breadcrumbs, and user-facing links must use only the canonical mode routes above.
