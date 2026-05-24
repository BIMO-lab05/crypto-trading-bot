# Phase 18: Bybit-Adapter Contract Fix - Context

**Gathered:** 2026-05-24
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous batch — user accepted all recommended defaults)

<domain>
## Phase Boundary

LIVE trading is dead-on-arrival because `services/trading-engine/app/exchanges/bybit_adapter.py` calls Bybit-connector REST endpoints that no longer exist at the named paths. Phase 18 corrects every adapter-side endpoint path to match what `services/bybit-connector/app/main.py` actually serves, extends `TapeReplayClient` with the three order-path methods the adapter requires, and lands a contract test that mechanically re-validates the adapter↔connector route table on every run so the contract cannot drift again.

**In scope:**
- Adapter endpoint corrections in `services/trading-engine/app/exchanges/bybit_adapter.py`
- TapeReplayClient stubs in `services/bybit-connector/app/tape_replay_client.py`
- New contract test in `services/trading-engine/tests/test_bybit_adapter_contract.py`

**Out of scope:**
- Adding NEW helper methods on the adapter for connector routes the adapter doesn't already call (e.g. `/order/history`, `/order/open` if not currently consumed by adapter).
- Refactoring the adapter to expose URL constants (test reads file directly).
- Connector-side route renames (connector is source of truth).
- Live trading flip — paper-only milestone.

</domain>

<decisions>
## Implementation Decisions

### Area 1: Endpoint Correction Scope

- **D-01 (LOCKED): Audit ALL adapter endpoints, not just the 2 roadmap-named.** Pre-discuss scout found 4 actual mismatches against `services/bybit-connector/app/main.py`:
  - `place_order` adapter:665 calls `/api/v1/order/create` → connector serves `/api/v1/order/place` (main.py:587)
  - `get_positions` adapter:568 calls `/api/v1/position/list` → connector serves `/api/v1/account/positions` (main.py:557)
  - `get_order_status` adapter:843 + `get_open_orders` adapter:963 call `/api/v1/order/realtime` → connector serves `/api/v1/order/open` (main.py:676) and `/api/v1/order/history` (main.py:704)
  - `get_ticker` adapter:1003 calls `/api/v1/market/tickers` (plural) → connector serves `/api/v1/market/ticker` (main.py:739, singular)
  - Already-matching endpoints (no change owed): `/api/v1/account/balance` (adapter:483 ↔ connector:532), `/api/v1/order/cancel` (adapter:785 ↔ connector:638), `/api/v1/market/orderbook` (adapter:1059 ↔ connector:853), `/api/v1/market/kline` (adapter:1191 ↔ connector:761).
- **D-02 (LOCKED): Source of truth is the bybit-connector FastAPI router table.** Adapter must conform; connector wins on any conflict. Rationale: the connector abstracts Bybit's public API and is the canonical internal contract surface for trading-engine.
- **D-03 (LOCKED): Connector-side routes UNCHANGED.** No renames, no compat shims, no 308 redirects. Same-repo, no third-party consumers, clean cut.
- **D-04 (LOCKED): No new adapter helpers added.** Only fix existing mismatches. Any new connector routes (e.g. dedicated `/order/history` consumer) stay unimplemented on the adapter side until a future phase requires them.

### Area 2: TapeReplayClient Order Methods

- **D-05 (LOCKED): `TapeReplayClient.place_order` returns a deterministic fake FILLED order** so strategies can progress through tape-mode integration tests. Order ID derived from `f"TAPE_{symbol}_{side}_{int(timestamp*1000)}"` (monotonic per session). Filled price = current tape-replay ticker, filled qty = requested qty, status = `FILLED` immediately. No partial-fill simulation in v1.3.
- **D-06 (LOCKED): `TapeReplayClient.cancel_order` returns no-op success** (`{"success": True, "order_id": <id>}`). Cancellation makes no sense in deterministic replay.
- **D-07 (LOCKED): `TapeReplayClient.get_wallet_balance` reads from fixture file with default $100 USDT.** Fixture path: `tests/fixtures/tape_replay/wallet_balance.json` (created if missing with `{"USDT": 100.0}`). $100 matches the operator's actual paper-trading balance per CLAUDE.md / ADR-010 (paper-mode 10% per-trade cap relaxation exists specifically to clear Bybit min-notional on a $100 wallet). In-memory balance updates as fake FILLED orders consume notional — required for strategies that gate on balance. Operator amendment 2026-05-24: original spec was $10k; corrected to match real-world fixture.
- **D-08 (LOCKED): In-memory state persists across calls within one tape-replay session.** Open orders, positions, balance — all tracked in `TapeReplayClient` instance state, cleared on `close()` / `reset()`. Required so strategies that re-query position/balance after submitting an order get consistent answers within a single backtest run.

### Area 3: Contract Test Approach

- **D-09 (LOCKED): Route discovery via FastAPI introspection.** Test imports `from app.main import app` (the connector's FastAPI instance), iterates `app.routes` to build a `Set[Tuple[method, path]]` of declared routes. No hardcoded route tables.
- **D-10 (LOCKED): Adapter endpoint extraction via simple grep/regex on the source file.** Test reads `services/trading-engine/app/exchanges/bybit_adapter.py` as text, regex-matches `"/api/v[0-9]+/[a-z_/]+"` (and `/api/v5/...` if any Bybit-v5 paths leaked in) inside method bodies. No adapter refactor to expose URL constants.
- **D-11 (LOCKED): Path-only matching for the contract assertion.** Method (GET/POST/etc.) is also part of the tuple. Query params (handled by FastAPI `Query()` on connector side, formatted by adapter into the URL) are NOT part of the contract — drift there is a separate concern and out of scope for this phase. Path + HTTP method is the contract.
- **D-12 (LOCKED): Test placement at `services/trading-engine/tests/test_bybit_adapter_contract.py`.** Adapter-side (trading-engine) drives the contract assertion because the adapter is the consumer and any drift in the connector should fail the adapter's test (not the connector's). Test imports the connector app via the `services/bybit-connector` path or test fixture.

### Area 4: Migration Safety

- **D-13 (LOCKED): No 308 redirect shim on connector for old paths.** Clean cut.
- **D-14 (LOCKED): No env-var fallback to old paths.** Paper mode bypasses bybit_adapter entirely (paper_trading.py is the active code path); endpoint fixes do not disrupt paper trading. Live-mode adapter callers will start hitting correct paths immediately on merge.
- **D-15 (LOCKED): Risk assessment — low.** bybit_adapter is consumed only in LIVE mode (per audit at `services/trading-engine/app/live_trading.py:290-360`). Paper mode (`paper_trading.py`) uses an entirely separate code path. Phase 18 changes the LIVE adapter contract while LIVE remains gated by 4 explicit flags — no operator can hit broken paths until a future LIVE-flip phase.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `services/bybit-connector/app/main.py` — FastAPI `app` object with declarative `@app.post/get` decorators (lines 471, 491, 502, 532, 557, 587, 638, 676, 704, 739, 761, 853, 1026). Direct introspection via `app.routes` returns `APIRoute` objects with `.path` and `.methods`.
- `services/bybit-connector/app/tape_replay_client.py` — existing class structure (218 lines) with `_load_fixtures`, `reset`, `close`, and 6 market-data methods. Phase 18 adds 3 order-path methods to this class.
- `services/trading-engine/app/exchanges/bybit_adapter.py` — 11 endpoint call sites already follow the same URL-string-inline pattern (`f"{base_url}/api/v1/{path}"`). Mechanical replacement at lines 568, 665, 843, 963, 1003.
- `services/bybit-connector/tests/test_tape_replay_client.py` — existing pytest pattern for TapeReplayClient. Follow the fixtures + monkeypatch + AsyncMock idiom for the 3 new methods.

### Established Patterns
- Endpoint constants are inline string literals (`"/api/v1/order/create"`), not module-level constants. D-10 honors this — test extracts via regex on file text.
- Test convention: pytest-asyncio with `@pytest.mark.asyncio`, AsyncMock for httpx/aiohttp transports, deferred imports inside test bodies to dodge prometheus_client registry-duplication issues (CLAUDE.md memory note).
- Risk-cap rules from PROJECT.md and CLAUDE.md: 5% daily-loss CB, 2% LIVE per-trade, 10% paper per-trade (ADR-010). Phase 18 does not touch these.
- Conventional commits: `fix(trading-engine): ...`, `feat(bybit-connector): ...`, `test(trading-engine): ...`.

### Integration Points
- Adapter↔connector: HTTP REST in LIVE; direct in-process `TapeReplayClient` calls in tape mode. Phase 18 fixes both surfaces.
- Tape mode wiring: trading-engine instantiates `TapeReplayClient` when `BYBIT_CLIENT_MODE=tape` env var is set (verify wiring during plan phase).
- Existing test suites that exercise the adapter: `services/trading-engine/tests/test_exchanges.py` — must remain green after rewrites.

</code_context>

<specifics>
## Specific Ideas

- The 4 mismatches list above came from a live scout of both files at Phase 18 discuss time; planner should re-verify with fresh grep before drafting plans (line numbers may shift by the time execution lands).
- Contract test must run as part of trading-engine pytest (not bybit-connector), so import path needs care: the test should add bybit-connector to sys.path or use a test fixture that loads the connector app via importlib without polluting the trading-engine import graph. Planner to decide implementation; the constraint is "test lives in trading-engine, imports connector app".
- TapeReplayClient fixture file at `tests/fixtures/tape_replay/wallet_balance.json` — if the planner finds an existing fixtures directory under bybit-connector, place it there for consistency; otherwise create the path.

</specifics>

<deferred>
## Deferred Ideas

- Method/query-schema-level contract matching (not just path+method). Useful but separate phase — Phase 18 establishes path+method floor.
- Query-string contract matching (e.g. `category=linear` required by Bybit v5 unified-account). If adapter omits a required query param, FastAPI on the connector should 422; deferred to a future "Bybit v5 unified-account migration" phase.
- Partial-fill simulation in tape replay (`place_order` returning PARTIALLY_FILLED with reduced qty). Useful for testing partial-fill strategy logic but out of scope for v1.3.
- Refactoring adapter to expose URL constants as module-level dict (would simplify D-10 test). Defer to a future cleanup phase.
- Removing the connector's old `/api/v1/order/create` etc. routes — these never existed, so nothing to remove. Recorded so a future audit doesn't try to find/remove them.

</deferred>
