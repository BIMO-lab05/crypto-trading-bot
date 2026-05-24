---
phase: 18-bybit-adapter-contract-fix
reviewed: 2026-05-24T13:30:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - services/trading-engine/app/exchanges/bybit_adapter.py
  - services/bybit-connector/app/tape_replay_client.py
  - services/bybit-connector/tests/test_tape_replay_client.py
  - services/trading-engine/tests/test_bybit_adapter_contract.py
findings:
  critical: 3
  warning: 6
  info: 4
  total: 13
status: issues_found
---

# Phase 18: Code Review Report

## Summary

Phase 18 boundary held in the obvious dimensions — `live_trading.py`, `paper_trading.py`, `auto_trader.py`, and connector `main.py` not in the `a30e57b..HEAD` diff. Phase 17 broad-except rewrites preserved. URL-string corrections + contract test introspection mechanics are correct.

**However:** the wallet-balance write-path is broken in container runtime (write to `:ro` bind mount), the committed fixture lives at the wrong path (no runtime code reads it), the D-05 "deterministic FILLED" promise dies at the adapter boundary (status hardcoded to NEW), and two pre-existing camelCase/snake_case wire-format mismatches are now newly load-bearing because Plan 18-01 unblocked the URL paths.

## BL-01: Wallet fixture write to read-only bind mount crashes in container

**File:** `services/bybit-connector/app/tape_replay_client.py:159-176`

`_load_wallet_balance()` writes to `self.fixtures_path / "wallet_balance.json"` when the file is missing. In container, `Settings.tape_fixtures_path` defaults to `/app/tests/fixtures/tape`, which `docker-compose.unified.yml:409` bind-mounts as **read-only** (`:ro`). First call to `place_order` or `get_wallet_balance` in tape mode will raise `OSError: [Errno 30] Read-only file system`.

**Fix:** Either decouple wallet state from `fixtures_path` (RW path), drop disk persistence (in-memory only), or refuse-init when fixture missing (mirror kline/ticker loader's `FileNotFoundError` policy).

## BL-02: Committed fixture at wrong path — runtime never reads it

**File:** `services/bybit-connector/tests/fixtures/tape_replay/wallet_balance.json`

Seed file at `services/bybit-connector/tests/fixtures/tape_replay/wallet_balance.json`. Runtime lookup at `/app/tests/fixtures/tape/wallet_balance.json` (`tape`, NOT `tape_replay`, NOT under `services/bybit-connector/`). Container bind-mounts the repo-root `tests/fixtures/tape/`, not the per-service one.

Interlocks with BL-01.

**Fix:** Move fixture to `tests/fixtures/tape/wallet_balance.json` (repo root). Delete orphan under `services/bybit-connector/tests/fixtures/tape_replay/`.

## BL-03: Adapter camelCase body vs connector snake_case Pydantic — `place_order` 422

**File:** `services/trading-engine/app/exchanges/bybit_adapter.py:693-718` × `services/bybit-connector/app/models.py:47-63`

`_order_to_bybit` builds body with `orderType`, `timeInForce`, `reduceOnly`, `orderLinkId`. `PlaceOrderRequest` declares `order_type`, `time_in_force`, `reduce_only`, `order_link_id` with no aliases/populate_by_name. FastAPI/Pydantic returns 422 (required field missing).

Pre-existing — but Plan 18-01 made `/api/v1/order/place` a real route from adapter's perspective. Any future integration test that goes adapter → HTTP → connector → tape will fail.

**Fix:** Add `populate_by_name=True` + `alias=...` to PlaceOrderRequest fields, OR flip adapter to snake_case. Add integration test exercising adapter→HTTP→connector→tape.

## WR-01: D-05 "deterministic FILLED" dies at adapter boundary

**File:** `services/trading-engine/app/exchanges/bybit_adapter.py:638-654` × `services/bybit-connector/app/tape_replay_client.py:330-343`

Tape returns `orderStatus="Filled"`, `avgPrice`, `cumExecQty`. Adapter ignores all — line 646 hardcodes `order.status = OrderStatus.NEW`. Unit tests assert against raw tape output, not `UnifiedOrder`, so gap is invisible.

**Fix:** Lift `orderStatus`/`avgPrice`/`cumExecQty` into returned `UnifiedOrder`, OR document that `live_trading.py` polls `get_order_status` and `place_order` always returns NEW in v1.

## WR-02: `accountType` (camelCase) query → snake_case `account_type` route

**File:** `services/trading-engine/app/exchanges/bybit_adapter.py:458` × `services/bybit-connector/app/main.py:534-554`

Adapter sends `params = {"accountType": ...}`. Connector route declares `account_type: str = "UNIFIED"`. FastAPI silently uses default. By accident default matches today, but override fails silently.

**Fix:** Use `params = {"account_type": ...}`.

## WR-03: Rejected order silently becomes successful NEW

**File:** `services/bybit-connector/app/tape_replay_client.py:307-313` × `services/trading-engine/app/exchanges/bybit_adapter.py:638-660`

Unknown-symbol-no-price returns `{"orderId": "", "orderStatus": "Rejected"}`. Adapter sets `exchange_order_id=""`, hardcodes status NEW. Later `cancel_order(order_id="")` will silently fail; Phase 19 recon will lookup non-existent order.

**Fix:** Raise OrderRejectedError when response has empty orderId or status=Rejected.

## WR-04: `get_order_status` returns wrong order with multiple open

**File:** `services/trading-engine/app/exchanges/bybit_adapter.py:807-816`

POSTs `orderId`/`orderLinkId` as query params to `/api/v1/order/open`. Route ignores extra params — `_parse_order(order_list[0])` returns first item unfiltered. Multiple open orders → wrong status.

Pre-existing — Plan 18-01 made path live. D-11 deferred query-schema drift to a future phase.

**Fix:** Filter client-side after response, OR extend connector route to accept order_id/order_link_id filters.

## WR-05: `_kline_cursor`/`_ticker_cursor` declared, reset, tested, never read

**File:** `services/bybit-connector/app/tape_replay_client.py:61-62, 189-201`

Cursor dicts populated at `__init__`, zeroed by `reset()`, asserted on by D-04 tests — but `get_kline`/`get_ticker` never read or advance them. Either dead state or consumer-side advance forgotten.

**Fix:** Delete cursors (and update D-04 tests), OR implement cursor-advance — pick one, document.

## WR-06: `test_phase_18_corrections_locked_in` guards 4 of 5 reported corrections

**File:** `services/trading-engine/tests/test_bybit_adapter_contract.py:253-278`

Plan claims "5 corrections"; test has 4 forbidden/required pairs (because `/order/realtime` → `/order/open` replaced one OLD at two call sites). Misalignment with narrative; future executor reverting only one of the two `/order/open` sites still passes if forbidden re-appears once.

**Fix:** Add count assertion next to substring lock-in: `{'/api/v1/order/open': 2, ...}`.

## IN-01: `notional = float(fill_price_d * qty_d)` loses Decimal precision

**File:** `services/bybit-connector/app/tape_replay_client.py:324`

Cast to float discards precision before balance decrement. Functionally fine at $100/SOLUSDT precision, but defeats Decimal use.

**Fix:** Keep arithmetic in Decimal end-to-end; cast once at storage time.

## IN-02: Negative wallet balance allowed — no margin check

**File:** `services/bybit-connector/app/tape_replay_client.py:325-328`

BUY for more notional than wallet decrements to negative balance. Real Bybit + paper-sim would reject. Erases "would exchange refuse?" signal.

**Fix:** Reject when `notional > self._wallet_balance["USDT"]` (mirror unknown-symbol Rejected path).

## IN-03: `_request` JSON-parses non-2xx responses

**File:** `services/trading-engine/app/exchanges/bybit_adapter.py:382`

`response.json()` unconditional. HTML 502 → JSONDecodeError → ConnectionError. Cosmetic.

**Fix:** Skip JSON parse when status≥400 and content-type isn't application/json.

## IN-04: contract-test subprocess doesn't guard empty stdout

**File:** `services/trading-engine/tests/test_bybit_adapter_contract.py:155-156`

Exit 0 + empty stdout → JSONDecodeError. Belt-and-braces.

**Fix:** `pytest.skip` on empty stdout.

---

## Boundary checks (per request)

- Phase 18 boundary held — auto_trader.py, live_trading.py, paper_trading.py, connector main.py NOT in diff.
- Autoflake didn't strip in-use imports.
- Contract test namespace handling correct (subprocess `cwd=CONNECTOR_DIR`).
- $100 wallet default consistent (no $10k leftover).
- 5 adapter endpoint corrections spot-checked: 4 forbidden absent, 4 new present, 5 unchanged intact. All 10 `self._request(...)` URLs exist in connector route table.

_Reviewer: gsd-code-reviewer_
