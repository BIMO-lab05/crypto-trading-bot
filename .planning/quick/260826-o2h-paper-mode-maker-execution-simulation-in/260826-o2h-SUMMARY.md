---
phase: quick-260826-o2h
plan: 01
subsystem: trading-engine
tags: [paper-trading, maker-orders, postonly, bybit, execution-metadata, jsonb, fees]

# Dependency graph
requires:
  - phase: quick-260820 wait-window (prefer_maker isolation run)
    provides: motivation — the 2026-08-20..26 isolation run produced ZERO maker evidence because auto_trader gated maker on trading_mode=="LIVE"
provides:
  - PaperTradingEngine.execute_maker_order_with_fallback (simulated PostOnly, LIVE contract mirror)
  - paper_maker_commission_pct Settings field (0.02 %/side Bybit linear-perp maker)
  - execution-path stamping on EVERY paper trade row (maker_attempted / execution_path / fallback_reason / fee_rate_applied) in trades.metadata JSONB
  - "[PAPER][MAKER]" log lines grep-compatible with "[LIVE][MAKER]"
  - auto_trader maker gate no longer LIVE-only (prefer_maker_orders + hasattr)
affects: [maker-share measurement window, edge-search v2 maker-halves-costs question, trading-engine harvest tooling]

# Tech tracking
tech-stack:
  added: []  # no new packages; httpx already a dependency (lazy import)
  patterns:
    - "execution_meta plumbed through execute_market_order to all three log_trade sites"
    - "fee rate as explicit Decimal-fraction override (rate is not None, never `or`)"
    - "_fetch_last_price as the deliberate test seam (tests patch it, never httpx)"

key-files:
  created:
    - services/trading-engine/tests/unit/test_paper_trading_maker.py
  modified:
    - services/trading-engine/app/config.py
    - services/trading-engine/app/paper_trading.py
    - services/trading-engine/app/repositories.py
    - services/trading-engine/app/auto_trader.py

key-decisions:
  - "Simulation fill rule: sleep-then-single-refetch, first-touch at limit, no partial fills, no queue model (documented in the method docstring)"
  - "Wait cap 10s (< LIVE 30s) bounds trading-loop stall; biases simulated maker fill share DOWN — conservative"
  - "Limit price estimator reuses PaperSlippageModel with the OPPOSITE side; one-way bps overstates pure half-spread, so maker fills are UNDER-simulated — conservative, documented"
  - "Fallback-disabled error string kept byte-identical to LIVE (live_trading.py:420) so harvest tooling reads both engines the same"
  - "prefer_maker_orders stays default-false; enabling it is a separate operator decision for a measurement window"

patterns-established:
  - "Execution-path stamping: taker_direct vs taker_fallback vs maker distinguishes 'never tried' from 'tried and fell back' in the DB"

requirements-completed: [MAKER-SIM-01]

# Metrics
duration: 24min
completed: 2026-08-26
---

# Quick 260826-o2h: Paper-Mode Maker Execution Simulation Summary

**Simulated PostOnly maker path in the paper engine (fill-at-limit + 0.02%/side maker fee, 10s-capped wait, single-refetch first-touch rule, taker fallback) with execution-path metadata stamped into every trade row's JSONB — and the LIVE-only conjunct removed from the auto_trader maker gate so paper can finally attempt maker.**

## Performance

- **Duration:** ~24 min
- **Started:** 2026-08-26T16:42:52Z
- **Completed:** 2026-08-26T17:07:08Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- `PaperTradingEngine.execute_maker_order_with_fallback` mirrors the LIVE signature/return contract (`live_trading.py:321`): maker fill AT the limit with the maker fee and NO taker slippage; timeout honours `maker_fallback_to_taker`; fallback-disabled returns LIVE's exact error string.
- Every paper trade row now stamps `maker_attempted` / `execution_path` / `fallback_reason` / `fee_rate_applied` into `trades.metadata` (JSONB merge in `log_trade`), including plain `taker_direct` fills — a future isolation-window harvest can compute maker share and realized fee mix from DB + `[MAKER]` log lines alone.
- Maker/taker fee split: `paper_maker_commission_pct` (0.02 %/side) beside the existing taker `paper_commission_pct` (0.055 %/side); the effective rate applies to every commission in the call, entry AND close leg.
- `auto_trader` `use_maker` gate no longer tests `trading_mode == "LIVE"`; `prefer_maker_orders` + `hasattr` retained. LIVE behavior byte-identical (`live_trading.py` untouched); paper behavior unchanged at current runtime config (flag default-false → everything stamps `taker_direct`).
- 10 new tests + full targeted regression green (184 passed total across the runs below, 0 failures).

## Task Commits

1. **Task 1 (RED): failing maker-simulation tests** — `3125fbb` (test)
2. **Task 1 (GREEN): maker simulation + fee split + metadata plumbing** — `d8e90c8` (feat)
3. **Task 2: remove LIVE-only conjunct from auto_trader maker gate** — `8e9873f` (feat)
4. **Task 3: gate-routing tests (PAPER enters maker path)** — `4f821b9` (test)

## Files Created/Modified

- `services/trading-engine/app/config.py` — `paper_maker_commission_pct` Field (default 0.02, ge=0, le=1); fee RATE as config default, sanctioned per money.md.
- `services/trading-engine/app/paper_trading.py` — maker simulation (`execute_maker_order_with_fallback`, `_maker_limit_price`, `_fetch_last_price` seam, `_PAPER_MAKER_WAIT_CAP_SECONDS=10.0`); `execute_market_order` gains `fill_price_override` / `commission_rate_override` / `execution_meta`; `calculate_commission(order_value, rate=None)` with `is not None` check (Decimal("0") is falsy); metadata passed at all three `_spawn_trade_log` sites (close / scale-in / open).
- `services/trading-engine/app/repositories.py` — `log_trade(..., execution_metadata=None)` merged into the `metadata` JSONB insert (keys disjoint by construction; no schema change).
- `services/trading-engine/app/auto_trader.py` — `use_maker = (prefer_maker_orders and hasattr(...))`; comment rewritten to match reality. Single diff hunk.
- `services/trading-engine/tests/unit/test_paper_trading_maker.py` — 10 tests: BUY/SELL maker fill at limit with maker fee, timeout→taker fallback with metadata, fallback-disabled reject with no mutation, refetch-failure=no-fill, taker_direct stamping, maker metadata, Decimal money types, and two gate-routing tests reusing the `_execute_trade_with_setup` harness from `tests/test_te_cap_05_log_survival.py`.

## Chosen Simulation Fill Rule and Conservative Biases

- **Fill rule:** virtual PostOnly at the estimated best bid (BUY) / ask (SELL); sleep once (`min(maker_quote_timeout_seconds, 10.0)`); re-fetch last price ONCE via bybit-connector; fill AT the limit iff refetched touched it (BUY ≤ limit, SELL ≥ limit). No queue-position modeling, no partial maker fills.
- **Bias 1 — wait cap 10s vs LIVE 30s:** less wall-clock for the market to move → maker fill share biased DOWN (and the trading loop is stalled at most 10s/symbol).
- **Bias 2 — spread estimate = full one-way slippage bps:** the limit estimator reuses `PaperSlippageModel.fill_price` with the opposite side; its bps carry a taker-impact allowance on top of the half-spread floor, so the limit sits further from mid than a real quote → maker fills UNDER-simulated. Deliberately not a new spread model.
- When `paper_slippage_enabled=false`, the limit degrades to the reference price — consistent with the explicit frictionless A/B mode.
- **A failed price re-fetch is never a fill** (threat T-o2h-01): any HTTP/parse error → None → no-fill path.

## Operator Note

**`prefer_maker_orders` remains OFF** (compose/.env untouched, no container restarted, default false). At current runtime config every fill stamps `taker_direct`. Enabling the flag for a measurement window is a separate, operator-decided step.

## Decisions Made

- `fee_rate_applied` stamped in percent-per-side units matching Settings (0.055 taker / 0.02 maker), derived from the engine's coerced Decimal rate (`float(rate * 100)`) so the stamped value is exactly what was charged — value-equivalent to the plan's `float(<settings pct>)` wording, robust against Mock-settings fixtures.
- A maker order that closes a position pays the maker rate on that leg (effective rate resolved once per call) — per plan.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `getattr` default does not protect against Mock settings**
- **Found during:** Task 1 (engine `__init__`)
- **Issue:** The plan specified `getattr(settings, "paper_maker_commission_pct", 0.02)` "because test fixtures pass bare Mocks" — but `getattr` on a Mock returns an auto-created Mock, so `Decimal(str(Mock))` raises `InvalidOperation` in `__init__`, breaking every pre-existing suite that builds the engine with a bare-Mock Settings.
- **Fix:** Wrapped the coercion in `try/except (InvalidOperation, ValueError, TypeError)` falling back to `Decimal("0.02")/Decimal("100")` (a fee rate, sanctioned) — same defensive philosophy as `build_slippage_model`. Preserves the plan's intent exactly.
- **Files modified:** services/trading-engine/app/paper_trading.py
- **Verification:** full targeted regression green, including the pre-existing bare-Mock suites
- **Committed in:** d8e90c8

**2. [Rule 3 - Blocking] Format hook stripped not-yet-used imports and reflows whole files**
- **Found during:** Tasks 1 and 2
- **Issue:** The PostToolUse format hook autoflake-stripped `import httpx` and `InvalidOperation` when added before their usage existed, and reflows entire files — which would have violated Task 2's "no other diff hunks in auto_trader.py" done-criterion.
- **Fix:** Used a lazy `import httpx` inside `_fetch_last_price` (mirrors the FundingRateClient precedent in the same file), re-added `InvalidOperation` after its usage existed, and patched auto_trader.py via a surgical Bash+pathlib script (established repo workaround) so its diff is the gate + comment only. Note: the hook's whole-file reflow of paper_trading.py/repositories.py (content-neutral line re-wrapping) is included in the Task 1 commit.
- **Files modified:** services/trading-engine/app/paper_trading.py, services/trading-engine/app/auto_trader.py
- **Verification:** `git diff` import-churn check on every touched file; Task 2 diff is a single hunk
- **Committed in:** d8e90c8, 8e9873f

---

**Total deviations:** 2 auto-fixed (both Rule 3 - blocking)
**Impact on plan:** Both fixes required to keep pre-existing suites green and to satisfy the plan's own done-criteria. No scope creep; no behavior differences vs the plan's specification.

## Verification Results

All from `services/trading-engine` on host, `--no-cov` (testing.md):

| Run | Result |
|---|---|
| tests/unit/test_paper_trading_maker.py (new) | 10 passed |
| Targeted regression (test_paper_trading x2, test_paper_funding, test_paper_slippage, test_repositories, test_min_notional_fail_closed_paper) | 43 passed, 38 skipped (pre-existing PR #86 stale marks), 0 failed — identical to pre-change baseline |
| auto_trader-adjacent (te_cap_05, heat_gate, exit_kind_routing, auto_trader_min_notional, unit/test_auto_trader) | 70 passed |
| Accounting invariants (cash_conservation, accounting_invariants_phase1, restart_balance_restore, exit_kind_persistence) | 31 passed |
| Account-size invariant + config sync (repo root) | 30 passed |

- `use_maker` block contains no `trading_mode == "LIVE"` (regex-verified); auto_trader.py parses clean.
- Diff range touches ONLY the 5 planned files — no docker-compose*, no .env*, no `prefer_maker_orders` default change, `live_trading.py` untouched.
- Reject-never-clamp, sizing, and exit paths untouched (exit/close orders go through `execute_market_order` directly and stamp `taker_direct`, per plan).

## Known Stubs

None — the maker path is a documented simulation, not a stub; no placeholder values or unwired data introduced.

## Threat Flags

None beyond the plan's own threat model: the only new network surface is the `_fetch_last_price` ticker re-fetch, which is T-o2h-01 (mitigated: any error → None → no-fill; 5s client timeout).

## Next Steps / Readiness

- Ready for an operator-decided `prefer_maker_orders=true` paper measurement window; harvest can split maker share via `trades.metadata->>'execution_path'` and `[MAKER]` log grep.
- Requires trading-engine container rebuild/restart to take effect at runtime (deliberately NOT done in this task per plan constraints).

## Self-Check: PASSED

- All 5 code files + SUMMARY exist on disk (verified via ls)
- All 4 task commits present on `worktree-agent-a2d78d5186038e4d5`: 3125fbb, d8e90c8, 8e9873f, 4f821b9

---
*Phase: quick-260826-o2h*
*Completed: 2026-08-26*
