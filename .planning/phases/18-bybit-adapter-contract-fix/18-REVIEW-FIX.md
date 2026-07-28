---
phase: 18-bybit-adapter-contract-fix
fixed_at: 2026-07-28T20:55:00Z
review_path: .planning/phases/18-bybit-adapter-contract-fix/18-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 18: Code Review Fix Report

**Fixed at:** 2026-07-28T20:55:00Z
**Source review:** `.planning/phases/18-bybit-adapter-contract-fix/18-REVIEW.md`
**Iteration:** 1
**Fix scope:** `critical_warning` — Info findings (IN-01..IN-04) out of scope, not attempted.

**Summary:**
- Findings in scope: 9 (3 Critical + 6 Warning)
- Fixed: 9
- Skipped: 0
- Info findings out of scope: 4 (not attempted per `fix_scope: critical_warning`)

## Fixed Issues

### BL-02: Committed fixture at wrong path — runtime never reads it

**Files modified:** `services/bybit-connector/tests/fixtures/tape_replay/wallet_balance.json` -> `tests/fixtures/tape/wallet_balance.json`
**Commit:** `3683dab`
**Applied fix:** `git mv` of `wallet_balance.json` from the per-service fixtures dir to `tests/fixtures/tape/` at the repo root, matching the runtime bind-mount source in `docker-compose.unified.yml:409`. Removed the now-empty orphan `services/bybit-connector/tests/fixtures/tape_replay/` directory. Landed first so BL-01's refuse-init-if-missing policy has a valid seed file at runtime.

### BL-01: Wallet fixture write to read-only bind mount crashes in container

**Files modified:** `services/bybit-connector/app/tape_replay_client.py`, `services/bybit-connector/tests/test_tape_replay_client.py`
**Commit:** `5faa32e`
**Applied fix:** Rewrote `_load_wallet_balance()` to raise `FileNotFoundError` when the on-disk fixture is missing, instead of lazy-writing a default. The runtime bind-mount is `:ro`, so the previous auto-write behaviour would raise `OSError: Read-only file system` inside the first tape-mode request. Mirrors the `_load_fixtures()` policy for kline/ticker fixtures — fail loud at first use. Inverted the `test_get_wallet_balance_writes_default_if_fixture_missing` test into `test_get_wallet_balance_raises_when_fixture_missing` (asserts `FileNotFoundError` + confirms nothing was written to disk). All 18 `test_tape_replay_client.py` tests pass.

### BL-03: Adapter camelCase body vs connector snake_case Pydantic — `place_order` 422

**Files modified:** `services/bybit-connector/app/models.py`
**Commit:** `1797bbb`
**Applied fix:** Added Pydantic v2 `ConfigDict(populate_by_name=True)` and per-field camelCase `alias=...` values to `PlaceOrderRequest` for `order_type`, `time_in_force`, `reduce_only`, `order_link_id`, `take_profit`, `stop_loss`, `tpsl_mode`, `trigger_price`, `trigger_direction`. Model now accepts BOTH the Bybit V5 wire format (`orderType`, `timeInForce`, etc.) sent by the trading-engine `bybit_adapter` AND snake_case kwargs used by existing internal callers/tests. Verified via round-trip: adapter body dict and internal snake_case kwargs both construct successfully. All 46 `test_models.py` tests still pass. No integration test exercising adapter->HTTP->connector->tape was added — that belongs in the integration-test wave (out of scope for this fix pass).

### WR-01: D-05 "deterministic FILLED" dies at adapter boundary

**Files modified:** `services/trading-engine/app/exchanges/bybit_adapter.py`
**Commit:** `5031186`
**Status:** `fixed: requires human verification`
**Applied fix:** Replaced the hardcoded `order.status = OrderStatus.NEW` in `place_order` with a status-map lookup on `result["orderStatus"]` (same map `_parse_order` uses: `Filled -> OrderStatus.FILLED`, `Rejected -> OrderStatus.REJECTED`, etc.). Lifted `avgPrice` -> `order.filled_price` and `cumExecQty` -> `order.filled_quantity` into the returned `UnifiedOrder`. Log line now includes `status={order.status.value}`. **Human verification required:** this is a semantics change — `live_trading.py`, `paper_trading.py`, `auto_trader.py` were out of Phase 18 edit scope but may branch on `OrderStatus.NEW` vs `OrderStatus.FILLED`. Confirm no downstream regression before flipping `TRADING_MODE=LIVE`.

### WR-02: `accountType` (camelCase) query -> snake_case `account_type` route

**Files modified:** `services/trading-engine/app/exchanges/bybit_adapter.py`
**Commit:** `564b717`
**Applied fix:** Renamed `{"accountType": self._account_type}` to `{"account_type": self._account_type}` in `get_balance()` so the query key matches the connector route parameter at `services/bybit-connector/app/main.py:536`. Previously any override (e.g. CONTRACT account type) silently fell through to the FastAPI default.

### WR-03: Rejected order silently becomes successful NEW

**Files modified:** `services/trading-engine/app/exchanges/bybit_adapter.py`
**Commit:** `2b88dd7`
**Applied fix:** Added a post-`_request` guard in `place_order` that raises `OrderRejectedError` when the exchange response has an empty `orderId` OR `orderStatus == "Rejected"` (case-insensitive). Previously these responses were silently coerced to `OrderStatus.NEW` with an empty `exchange_order_id`, which meant downstream `cancel_order` / `get_order_status` no-op'd against a nonexistent order and Phase 19 reconciliation would look up phantoms. Verified the existing `except ExchangeError: raise` clause propagates the new raise correctly (`OrderRejectedError` -> `OrderError` -> `ExchangeError` per `errors.py`).

### WR-04: `get_order_status` returns wrong order with multiple open

**Files modified:** `services/trading-engine/app/exchanges/bybit_adapter.py`
**Commit:** `8b80a31`
**Status:** `fixed: requires human verification`
**Applied fix:** Added client-side post-response filtering in `get_order_status` that discards entries not matching the caller's `order_id` / `client_order_id`. Params still sent to the connector (harmless, future-compatible per D-11's deferral of connector query-schema drift). Raises `OrderNotFoundError` when no entry matches. **Human verification required:** no in-scope test exercises multi-open-orders semantics; correct behaviour was validated by inspection only, not by a regression test.

### WR-05: `_kline_cursor`/`_ticker_cursor` declared, reset, tested, never read

**Files modified:** `services/bybit-connector/app/tape_replay_client.py`, `services/bybit-connector/tests/test_tape_replay_client.py`
**Commit:** `4ab98f2`
**Applied fix:** Deleted the unused `_kline_cursor` / `_ticker_cursor` fields (populated at `__init__`, zeroed by `reset()`, asserted by tests, but never read by `get_kline` / `get_ticker`). Simplified `reset()` to only handle the order-path session state (D-08) plus a wallet lazy-reload arm. Preserved the grep-able `TAPE_REPLAY: cursors reset` log-line prefix (used by `test_reset_emits_grep_able_log_line` and RUNBOOK triage). Rewrote the three obsolete D-04 cursor tests as: `test_reset_clears_session_state_after_init`, `test_reset_rewinds_session_state_after_activity`, `test_reset_does_not_touch_fixture_dicts`. All 18 tests pass.

### WR-06: `test_phase_18_corrections_locked_in` guards 4 of 5 reported corrections

**Files modified:** `services/trading-engine/tests/test_bybit_adapter_contract.py`
**Commit:** `b47fdff`
**Applied fix:** Added a `Counter` over `_extract_adapter_endpoints()` to lock the per-endpoint call-site counts inside `test_phase_18_corrections_locked_in`. Uses the regex-extracted endpoint list (not raw `source.count()`) so comment-only mentions don't double-count. Locked counts: `POST /api/v1/order/place` = 1, `GET /api/v1/account/positions` = 1, `GET /api/v1/order/open` = 2 (the two sites Plan 18-01 targeted: `get_order_status` + `get_open_orders`), `GET /api/v1/market/ticker` = 1. A future partial revert of just one of the two `/order/open` sites will now fail this test. All 3 contract tests pass.

## Skipped Issues

None — all 9 in-scope findings were fixed.

## Info Findings (Out of Scope)

Per `fix_scope: critical_warning`, the following 4 Info findings were **not attempted**. Their remediation is deferred to a follow-up pass with `fix_scope: all` if desired.

- **IN-01:** `notional = float(fill_price_d * qty_d)` loses Decimal precision (`services/bybit-connector/app/tape_replay_client.py:324`)
- **IN-02:** Negative wallet balance allowed — no margin check (`services/bybit-connector/app/tape_replay_client.py:325-328`)
- **IN-03:** `_request` JSON-parses non-2xx responses (`services/trading-engine/app/exchanges/bybit_adapter.py:382`)
- **IN-04:** contract-test subprocess doesn't guard empty stdout (`services/trading-engine/tests/test_bybit_adapter_contract.py:155-156`)

## Verification Summary

| Fix | Syntax check (Tier 2) | Test suite run |
|-----|----------------------|----------------|
| BL-02 | N/A (file move only) | Downstream tests still pass (BL-01) |
| BL-01 | `ast.parse` OK | `pytest test_tape_replay_client.py` — 18/18 pass |
| BL-03 | `ast.parse` OK | `pytest test_models.py` — 46/46 pass + manual round-trip |
| WR-01 | `ast.parse` OK | Tier 1 re-read only (integration test out of scope) |
| WR-02 | `ast.parse` OK | Tier 1 re-read only |
| WR-03 | `ast.parse` OK | Tier 1 re-read only |
| WR-04 | `ast.parse` OK | Tier 1 re-read only |
| WR-05 | `ast.parse` OK | `pytest test_tape_replay_client.py` — 18/18 pass |
| WR-06 | `ast.parse` OK | `pytest test_bybit_adapter_contract.py` — 3/3 pass |

Final combined `ast.parse` check across all 5 touched `.py` files: OK.

---

_Fixed: 2026-07-28T20:55:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
