# Storage Layout

`storage` is local runtime data, not application source.

Docker maps these folders into the API container:

- `storage/logs` -> `/logs`
- `storage/reports` -> `/reports`

Application code should use `LOGS_DIR` and `REPORT_OUTPUT_DIR` from
`apps/api/config/settings.py`, not hard-coded repository-relative paths.

## `storage/logs`

Runtime data is grouped by role. New code should not write files directly under
`storage/logs`.

- `runtime/`: active engine/account state, runtime event streams, optimizer state.
- `audit/`: durable audit databases, including Agent run/order/risk records.
- `config/`: operator-controlled settings such as strategy registry, guardrail policy, watchlist, and validation settings.
- `cache/`: reproducible or refreshable cache data such as research snapshots, universe snapshots, strategy scan outputs, and broker token cache.

This layout keeps the future DB migration straightforward:

- `runtime/runtime.db` for engine/account/events/quant ops.
- `audit/agent.db` or `audit/trading_audit.db` for audit trails.
- `config/config.db` for operator settings and version history.
- `cache/cache.db` for refreshable snapshots.

SQLite `*.db-wal` and `*.db-shm` files are normal sidecar files while the API is
running. Do not manually delete them while containers are up.

## `storage/reports`

Generated report storage.

- `market_brief.db`: SQLite report cache used by report routes.

## Cleanup Rule

Keep active runtime files in the role-specific paths above. Delete old one-off
dumps, schema backup files, or ad hoc experiment artifacts once they are no
longer referenced by code.
