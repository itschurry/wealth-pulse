# Agent Auto Trading MVP Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Convert WealthPulse toward an auditable Korean stock auto-trading agent where Hermes returns BUY/SELL/HOLD JSON, the server validates/risk-gates it, and Paper/Live executors handle orders.

**Architecture:** Keep the existing `apps/api` and `apps/web` structure. Add an Agent Run layer over the existing candidate/research/portfolio/risk/execution pieces instead of creating a new `backend/app` tree. Phase 1 is paper-only and DB/audit-first; live execution remains blocked until the two-key guard (`TRADING_MODE=live` and `ENABLE_LIVE_TRADING=true`) is implemented and tested.

**Tech Stack:** Python stdlib HTTP server routes, unittest, SQLite audit store under `storage/logs/agent_trading.db`, existing `PaperExecutionEngine`/`LiveBrokerExecutionEngine`, existing Hermes runner/research snapshot contracts, React frontend later.

---

## Phase 1: Backend Paper-Only Agent Run MVP

### Task 1: Add Agent audit SQLite store

**Objective:** Create a small migration-on-open SQLite store for `agent_runs`, `trade_candidates`, `market_evidence`, `trade_decisions`, `risk_events`, and `trade_orders`.

**Files:**
- Create: `apps/api/services/agent_store.py`
- Test: `apps/api/tests/test_agent_store.py`

**Step 1: Write failing tests**
- Test schema initialization creates all six tables.
- Test creating a run, candidate, evidence, decision, risk event, and order can be read back by run id.

**Step 2: Run RED**
```bash
cd ~/wealth-pulse
PYTHONPATH=apps/api python -m unittest apps/api/tests/test_agent_store.py
```
Expected: FAIL because `services.agent_store` does not exist.

**Step 3: Implement minimal store**
- Use `sqlite3` and `LOGS_DIR / "agent_trading.db"` by default.
- Support test-injected path.
- Store JSON payload columns as text.
- Use ISO timestamps.

**Step 4: Run GREEN**
```bash
PYTHONPATH=apps/api python -m unittest apps/api/tests/test_agent_store.py
```
Expected: PASS.

---

### Task 2: Add Hermes decision schema validation

**Objective:** Validate Hermes BUY/SELL/HOLD JSON and convert invalid/parse-failed output to HOLD with a persisted failure reason.

**Files:**
- Create: `apps/api/services/agent_schemas.py`
- Test: `apps/api/tests/test_agent_schemas.py`

**Required schema:**
```json
{
  "action": "BUY | SELL | HOLD",
  "symbol": "string",
  "confidence": 0.0,
  "reason_summary": "string",
  "evidence": ["string"],
  "risk": {
    "entry_price": 0,
    "stop_loss": 0,
    "take_profit": 0,
    "max_position_ratio": 0.0
  }
}
```

**Step 1: Write failing tests**
- Valid BUY parses with normalized uppercase action/symbol.
- Invalid JSON returns HOLD with `parse_error`.
- Missing stop loss remains parsed but later risk gate should reject.
- Confidence is clamped to `[0.0, 1.0]` or invalid values become 0.

**Step 2: Run RED**
```bash
PYTHONPATH=apps/api python -m unittest apps/api/tests/test_agent_schemas.py
```

**Step 3: Implement validator**
- No pydantic dependency; use stdlib for compatibility.
- Return dict with `valid`, `decision`, `errors`, `raw_text`.

**Step 4: Run GREEN**
```bash
PYTHONPATH=apps/api python -m unittest apps/api/tests/test_agent_schemas.py
```

---

### Task 3: Add Agent Risk Gate v1

**Objective:** Implement deterministic server-side risk gate for Hermes decisions.

**Files:**
- Create: `apps/api/services/agent_risk_gate.py`
- Test: `apps/api/tests/test_agent_risk_gate.py`

**Risk checks v1:**
- `trading_mode` must be `paper` or `live`.
- `live` requires `enable_live_trading=True`.
- `confidence >= min_confidence`, otherwise HOLD/reject.
- BUY/SELL requires `stop_loss > 0`.
- BUY requires reward/risk ratio >= `min_reward_risk_ratio`.
- BUY requires sufficient cash.
- BUY must not exceed `max_symbol_position_ratio`.
- Same-symbol cooldown blocks repeat orders.
- Existing position add-buy policy blocks additional BUY by default.

**Step 1: Write failing tests**
- BUY approved when all checks pass in paper mode.
- LIVE rejected when `enable_live_trading=False`.
- Low confidence returns rejected with reason `confidence_below_minimum`.
- Missing stop loss returns rejected with reason `stop_loss_required`.
- Poor reward/risk returns rejected with reason `reward_risk_below_minimum`.
- Insufficient cash returns rejected.
- Existing same-symbol position rejects additional buy.

**Step 2: Run RED**
```bash
PYTHONPATH=apps/api python -m unittest apps/api/tests/test_agent_risk_gate.py
```

**Step 3: Implement minimal gate**
- Input: decision dict, account snapshot, config dict, recent orders list, now timestamp.
- Output: `approved`, `final_action`, `reason_code`, `checks`, `order_intent`.
- Never call broker/KIS here.

**Step 4: Run GREEN**
```bash
PYTHONPATH=apps/api python -m unittest apps/api/tests/test_agent_risk_gate.py
```

---

### Task 4: Add Agent Runner paper-only skeleton

**Objective:** Wire candidate -> evidence -> Hermes decision placeholder/optional injected decision -> validation -> risk gate -> paper order record into a single run.

**Files:**
- Create: `apps/api/services/agent_runner.py`
- Test: `apps/api/tests/test_agent_runner.py`

**Scope:**
- Paper-only execution in this task.
- Do not call live KIS order API.
- Allow tests to inject candidates, evidence, decisions, account, and executor.

**Step 1: Write failing tests**
- A BUY decision passing risk creates a run, candidate, evidence, decision, approved risk event, and paper order record.
- A rejected decision creates all audit rows but no submitted order.
- Invalid Hermes JSON stores HOLD decision and risk rejection/failure reason.

**Step 2: Run RED**
```bash
PYTHONPATH=apps/api python -m unittest apps/api/tests/test_agent_runner.py
```

**Step 3: Implement runner**
- Create run status `running`, finish as `completed`.
- Record one row per candidate.
- Use injected executor in tests; production executor can be paper wrapper in later task.

**Step 4: Run GREEN**
```bash
PYTHONPATH=apps/api python -m unittest apps/api/tests/test_agent_runner.py
```

---

### Task 5: Add `/api/agent/*` read/write routes

**Objective:** Expose manual trigger and read APIs.

**Files:**
- Create: `apps/api/routes/agent.py`
- Modify: `apps/api/server.py`
- Test: `apps/api/tests/test_agent_routes.py`

**Endpoints:**
- `POST /api/agent/run`
- `GET /api/agent/runs`
- `GET /api/agent/runs/{id}`
- `GET /api/agent/decisions`
- `GET /api/agent/orders`
- `GET /api/agent/evidence/{symbol}`

**Step 1: Write failing route tests**
- Route handlers return expected status/payload shape.
- Server dispatch includes the new paths.

**Step 2: Run RED/GREEN**
```bash
PYTHONPATH=apps/api python -m unittest apps/api/tests/test_agent_routes.py
```

---

### Task 6: Add risk config and KIS status read-only APIs

**Objective:** Add operator-visible config/status APIs without enabling live orders.

**Files:**
- Create: `apps/api/services/agent_config.py`
- Create/modify: `apps/api/routes/risk.py`
- Create/modify: `apps/api/routes/broker.py`
- Modify: `apps/api/server.py`
- Tests: `apps/api/tests/test_agent_config_routes.py`

**Endpoints:**
- `GET /api/risk/config`
- `PUT /api/risk/config`
- `GET /api/portfolio` as alias of `/api/portfolio/state`
- `GET /api/broker/kis/status`

**Safety:**
- `TRADING_MODE` default `paper`.
- `ENABLE_LIVE_TRADING` default `false`.
- KIS status must be read-only.

---

## Phase 2: Frontend Observer UI

### Task 7: Agent Dashboard read-only
- Add summary cards: run count, candidates, BUY/SELL/HOLD counts, orders, risk rejects.
- Add mode banner: PAPER/LIVE and live disabled warning.

### Task 8: Decision Timeline and Evidence Viewer
- Show symbol, action, confidence, reason, risk result, order status.
- Evidence viewer lists news/chart/portfolio evidence.

### Task 9: Risk Config UI
- Edit max position ratio, daily loss limit, min confidence, min reward/risk, cooldown.
- Never expose secrets.

---

## Phase 3: Live Readiness and Limited Live Execution

### Task 10: Live read-only KIS verification
- Check KIS auth, account, cash, holdings, market data.
- Keep live order disabled.

### Task 11: Two-key live execution
- Allow live executor only if `TRADING_MODE=live` and `ENABLE_LIVE_TRADING=true` and risk gate passes.
- Persist full request/response audit.

### Task 12: Scheduler and alerts
- Scheduled Agent Run.
- Telegram/UI alerts for orders and risk rejects.

---

## Verification Commands

Run after each backend phase:
```bash
cd ~/wealth-pulse
docker compose run --rm -v "$PWD/apps/api:/app/apps/api" api python -m unittest \
  tests.test_agent_store \
  tests.test_agent_schemas \
  tests.test_agent_risk_gate \
  tests.test_agent_runner \
  tests.test_agent_routes

docker compose run --rm -v "$PWD/apps/api:/app/apps/api" api python -m compileall -q services routes tests

git diff --check
```

## Non-negotiable Safety Rules

- Hermes never calls KIS APIs.
- Live order default is disabled.
- Risk Gate failure means no order.
- Every decision/risk/order outcome is recorded.
- Paper MVP comes before live.
