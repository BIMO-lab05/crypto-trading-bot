# Phase 13: Bybit-Connector Market-Data Centralization - Context

**Gathered:** 2026-05-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Make `services/bybit-connector/` the **sole Bybit-facing service** in the codebase. Refactor every direct Bybit API call (`pybit` imports, hardcoded `api.bybit.com` / `wss://stream.bybit` URLs) and alternate market-data source outside `services/bybit-connector/` to route through bybit-connector REST endpoints. CI grep gate locks the new contract.

Adjacent scope (per operator policy, captured 2026-05-21): drop the dormant Binance exchange adapter (`services/trading-engine/app/exchanges/binance.py`) — operator stated "I will not use binance just bybit". Phase 13 archives it so the codebase matches the policy.

**In scope (operator-confirmed):**
- All Python files outside `services/bybit-connector/` that import `pybit`, hit `api.bybit.com` directly, or open `wss://stream.bybit` directly
- `scripts/` standalone operator-run scripts
- `backtesting/bybit_data_fetcher.py`
- `services/market-data-service/tests/test_pagination_fix.py` and similar test bypasses
- `infrastructure/scripts/rotate_secrets.py` (key-rotation auth ping → bybit-connector `/api/v1/account/balance`)
- `services/trading-engine/app/exchanges/binance.py` archive
- CI grep gate (`tests/ci/test_no_bybit_bypass.py`) banning the patterns above in `**/*.py` outside `services/bybit-connector/`
- RUNBOOK symptom documenting the chain
- `services/market-data-service/app/config.py:58` port-default defect fix (`localhost:8002` → `:8001`)

**Out of scope (deferred):**
- Order-placement code path (`services/trading-engine/app/exchanges/bybit_adapter.py`) — already clean per audit; trading-engine-direct Bybit *would be* a separate centralization, but adapter is wrapper-only, no direct Bybit URLs/pybit
- Sentiment service's `cryptocompare` news fetch — sentiment ≠ market-data
- `scripts/monitoring/tier1_monitor.py` CoinGecko ping — intentional cross-source price-divergence check (load-bearing safety guard)
- WS-01..04 (original phase 13 scope) — deferred to v2

</domain>

<decisions>
## Implementation Decisions

### Scope boundary
- **D-01:** Full scope — every Python file in the repo with direct Bybit access is refactored: `services/`, `scripts/`, `backtesting/`, `infrastructure/scripts/`, tests. No partial-scope shortcuts. Operator's call (2026-05-21): "Everything code-pathed to Bybit".
- **D-02:** Binance exchange adapter (`services/trading-engine/app/exchanges/binance.py`) is archived as part of this phase per operator policy ("I will not use binance just bybit"). Move under `_archive_exchanges/binance.py` similar to the LSTM archival pattern; remove from `services/trading-engine/app/exchanges/factory.py` (line 62, 189) and `services/trading-engine/app/exchanges/__init__.py` (lines 23, 213, 329, 330, 513); remove `services/trading-engine/tests/test_multi_exchange.py` Binance branches.

### Refactor target
- **D-03:** Bypass sites consume **bybit-connector REST directly** (via `httpx` to `http://bybit-connector:8001/api/v1/market/...`). No intermediary through `market-data-service`. Rationale: simpler dependency graph, mirrors `market-data-service.fetcher.py` pattern already in place, avoids coupling ml-prediction → market-data uptime.

### Operator friction
- **D-04:** Scripts require bybit-connector container running. `scripts/collect_*.py`, `scripts/fetch_real_historical_data.py`, `scripts/collect_ml_training_data_simple.py`, `backtesting/bybit_data_fetcher.py` fail-fast if `BYBIT_CONNECTOR_URL` unreachable; explicit error message tells operator to run `docker compose up bybit-connector`. No `--direct-bybit` escape hatch — keeps the gate honest. Friction documented in RUNBOOK symptom.

### CI grep gate
- **D-05:** Gate scope is **`**/*.py` files outside `services/bybit-connector/`**. Patterns banned: `from pybit`, `import pybit`, `api.bybit.com`, `wss://stream.bybit`, `api-testnet.bybit`. Config YAML (helm values, network-policy comments), markdown docs, and any non-Python file legitimately referencing Bybit URLs for bybit-connector's own provisioning are NOT gated. Spirit: no-code-bypass, not no-mention.
- **D-06:** Gate test (`tests/ci/test_no_bybit_bypass.py`) is a grep + AST check. Green on `main` post-refactor. Fails the CI workflow if a new violation lands in a PR. Required in `.github/workflows/` so PRs that re-introduce bypass cannot merge.

### rotate_secrets.py treatment
- **D-07:** `infrastructure/scripts/rotate_secrets.py` is in scope — refactor `from pybit.unified_trading import HTTP` + manual URL switching (lines 232-234) to use `bybit-connector /api/v1/account/balance` for the post-rotation auth ping. Even though it's auth-utility (not market-data), keeping it under the gate prevents the only documented exception from becoming the loophole that grows.

### Tape-mode preservation
- **D-08:** Bybit-connector's tape-replay mode (`MARKET_DATA_SOURCE=tape`, fixtures at `tests/fixtures/tape/`, `POST /admin/tape/reset`) MUST work unchanged after refactor. Every refactored consumer hitting bybit-connector REST inherits tape-mode for free (bypass sites lose the ability to bypass tape — a feature, not a bug).

### Config defect
- **D-09:** Fix `services/market-data-service/app/config.py:58` default `bybit_connector_url="http://localhost:8002"` → `"http://localhost:8001"`. Currently overridden by compose env so production is unaffected; default-only fix prevents accidental misroute when scripts read the config without compose env.

### Open question for plan-phase
- **D-10:** `INTEGRATIONS.md:231` claims `wss://stream.bybit.com/*` is consumed by `market-data` — audit shows this is stale (only bybit-connector). Codebase-map refresh is implicit in phase 13 close; planner adds a note to update INTEGRATIONS.md.

### Claude's Discretion
- Refactor ordering across services/scripts/backtesting/infra — planner sequencing decision
- Whether tape-mode coverage tests need additional fixtures (e.g., orderbook tape data for the `ml-prediction-service/handlers/orderbook.py:262` refactor) — researcher to investigate
- Whether bybit-connector needs new REST endpoints (likely not — existing surface covers all known bypass-site patterns)
- Wave grouping for parallel execution — planner

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project policy + planning
- `CLAUDE.md` — project rules; risk caps, paper/live mode boundaries, conventional commits, "Bybit-first; no other exchange" constraint
- `.planning/PROJECT.md` — milestone goal (v1.2 rescoped 2026-05-21), validated requirements, key decisions
- `.planning/ROADMAP.md` §"Phase 13" — rescope notice + initial audit table (anchor for all bypass sites)
- `.planning/REQUIREMENTS.md` §"Bybit-Connector Market-Data Centralization (BC)" — placeholder for BC-NN requirement IDs (populated by `/gsd-plan-phase`)

### Codebase maps (use for context, refresh post-phase)
- `.planning/codebase/INTEGRATIONS.md` §"Bybit" + §"External Egress Catalog" — service-level integration matrix; note stale claim on market-data WS (D-10)
- `.planning/codebase/CONCERNS.md` — pre-existing operational gotchas; market-data-cache-in-Timescale note matters for D-03 rationale
- `.planning/codebase/STRUCTURE.md` — repo layout, `services/`/`scripts/`/`backtesting/` boundary
- `.planning/codebase/STACK.md` — `pybit==5.6.2`, `httpx`, `websockets==12.0` library pins

### Bybit-connector surface (target of every refactor)
- `services/bybit-connector/app/main.py:739-944` — market-data REST endpoints (ticker/kline/orderbook/recent-trade/funding-rate/instruments-info)
- `services/bybit-connector/app/main.py:532-557` — account endpoints (balance/positions) — target for `rotate_secrets.py` refactor (D-07)
- `services/bybit-connector/app/main.py:1026` — `/admin/tape/reset` — preserve tape-mode (D-08)
- `services/bybit-connector/app/config.py` — `BYBIT_TESTNET` flag, mainnet/testnet URL selection

### Initial audit (anchor for plan tasks)
- `.planning/ROADMAP.md` §"Phase 13" — "Initial audit (2026-05-21)" bullet list — 9 in-scope code paths + 1 config defect + 1 archival action

### Reference: reusable httpx-to-bybit-connector pattern
- `services/market-data-service/app/fetcher.py:69-105` — `BybitDataFetcher` class — model for how to call bybit-connector REST with retry decorator (`@bybit_connector_retry`)
- `services/market-data-service/app/circuit_breaker.py:18-21` — shared retry policy

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `services/market-data-service/app/fetcher.py` (`BybitDataFetcher`) — direct template for new consumers; copy/adapt for ml-prediction-service orderbook handler + scripts
- `services/market-data-service/app/circuit_breaker.py` (`bybit_connector_retry`) — shared retry decorator; new consumers import or duplicate the pattern
- `services/bybit-connector/app/main.py` REST endpoints — already cover every market-data shape needed (`/api/v1/market/{ticker,kline,orderbook,recent-trade,funding-rate/history,instruments-info}`)
- `services/bybit-connector/app/main.py:532-557` `/api/v1/account/balance` + `/api/v1/account/positions` — auth ping target for `rotate_secrets.py`

### Established Patterns
- httpx async client with circuit-breaker retry (tenacity) for inter-service calls
- `*_url` settings field with compose-env override (`BYBIT_CONNECTOR_URL`, `MARKET_DATA_URL`) — every consumer follows this contract
- `MARKET_DATA_SOURCE=tape|live` env switch with bind-mounted fixtures — preserve for refactored consumers
- Conventional commits (`feat(svc):`, `fix(svc):`, `refactor(svc):`, `test(svc):`) — TDD mode on means RED→GREEN cycle per task
- LSTM archival precedent (`_archive_lstm/` from May 2026 cleanup) — model for `_archive_exchanges/binance.py` (D-02)

### Integration Points
- `services/ml-prediction-service/app/handlers/orderbook.py:262` — direct `api.bybit.com` call; replace with httpx to `BYBIT_CONNECTOR_URL/api/v1/market/orderbook`
- `services/ml-prediction-service/download_missing_symbols_data.py:43` — `BYBIT_API_URL` constant; replace constant with `BYBIT_CONNECTOR_URL` env + call `/api/v1/market/kline`
- `scripts/collect_180_days_data.py:56`, `scripts/collect_6months_for_ml.py:28`, `scripts/fetch_real_historical_data.py:31` — same pattern: replace `BYBIT_API_URL` constant + direct httpx → bybit-connector REST
- `scripts/collect_ml_training_data_simple.py:18` — `from pybit.unified_trading import HTTP` → bybit-connector REST
- `backtesting/bybit_data_fetcher.py:36-38` — testnet/mainnet URL switch → bybit-connector REST (bybit-connector handles testnet/mainnet via `BYBIT_TESTNET` env)
- `services/market-data-service/tests/test_pagination_fix.py:36` — refactor or mock at bybit-connector boundary
- `infrastructure/scripts/rotate_secrets.py:232-234` — `from pybit.unified_trading import HTTP` + URL switch → `bybit-connector /api/v1/account/balance`
- `services/market-data-service/app/config.py:58` — port-default defect (`8002` → `8001`)
- `services/trading-engine/app/exchanges/binance.py` + `factory.py:62,189` + `__init__.py:23,213,329,330,513` + `tests/test_multi_exchange.py:54,161,165` — archive Binance adapter
- `tests/ci/test_no_bybit_bypass.py` — NEW CI grep gate (does not exist; planner creates)
- `RUNBOOK.md` — NEW Symptom #N "market-data stale because bybit-connector down" — Diagnose/Action/Verification chain (planner creates)

</code_context>

<specifics>
## Specific Ideas

- Use existing `BybitDataFetcher` pattern from `services/market-data-service/app/fetcher.py` as the template for new consumers — don't reinvent
- CI grep gate test should be Python (not bash) — matches `tests/ci/test_no_new_setinterval_polling.py` precedent that was dropped from the WS-push scope; reuse that file's grep+report idiom
- Operator wants no escape hatches: scripts that bypass bybit-connector should fail explicitly with a clear error pointing at `docker compose up bybit-connector`, not silently fall back
- Binance archival must not break trading-engine startup — `factory.py` will need a "binance: removed per Phase 13 policy" branch (or just delete the registration)

</specifics>

<deferred>
## Deferred Ideas

- WS-01..04 original phase 13 scope (server-side `/ws/metrics` push + client `useWsSubscription` hook) — rejected by operator 2026-05-21; v2 candidate at earliest
- Trading-engine order placement centralization (`services/trading-engine/app/exchanges/bybit_adapter.py` currently uses bybit-connector indirectly?) — audit indicated no direct Bybit but full review-and-lock is its own phase
- INTEGRATIONS.md codebase-map refresh (stale claim on market-data WS, line 231) — planner notes this; can be a single ROADMAP-tracked cleanup or rolled into phase 13 close commit
- Sentiment service's cryptocompare news fetch — sentiment ≠ market-data; if "no-non-Bybit anywhere" becomes policy in a later milestone, this is the place to look
- `tier1_monitor.py` CoinGecko cross-source divergence — load-bearing safety guard; should NEVER be migrated (it's a deliberate non-Bybit source)

</deferred>

---

*Phase: 13-Bybit-Connector Market-Data Centralization*
*Context gathered: 2026-05-21*
