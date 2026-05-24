---
phase: 17-execution-cap-hard-enforcement
reviewed: 2026-05-24T03:25:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - services/trading-engine/app/handlers/orchestration.py
  - services/trading-engine/app/auto_trader.py
  - services/trading-engine/tests/test_orchestration_emergency_stop_removed.py
  - services/trading-engine/tests/test_te_cap_05_log_survival.py
findings:
  critical: 0
  warning: 4
  info: 2
  total: 6
status: issues_found
---

# Phase 17: Code Review Report

**Reviewed:** 2026-05-24T03:25:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Two Plan-01 deliverables (delete `POST /api/v1/orchestrator/emergency-stop`, add RED 404 test) are clean — deletion is complete, test correctly asserts 404 on both bare and `?reason=` query shapes, no stale callers, no sibling test breakage. The auth-note comment in `handlers/orchestration.py:692-700` accurately reflects the post-deletion state.

The cap-check block at `auto_trader.py:1972-1989` is **confirmed UNCHANGED** by Phase 17 — no regression of Phase 16 RISK-04/RISK-06. The new regression test `test_te_cap_05_log_survival.py` correctly catches the three wrap-scenarios analysed in the user's question: it RED-s on `try/except Exception: pass` around `:1978-1984` (via both the caplog and counter assertions), RED-s on a wrap around the whole `if` body `:1977-1989` (via the `execute_market_order` AssertionError side-effect), and RED-s on wrapping a wider region containing `total_trades_rejected += 1` (via the tertiary state assertion).

Plan-02 (TE-CAP-05) is where the issues cluster. The five typed-except rewrites land in three buckets:

- **Category P parse-failure at `:1552`** — `(InvalidOperation, ValueError, TypeError)`: correct.
- **Category M metric-emit at `:1594` and `:1611`** — `(OSError, ImportError)`: partially wrong, misses the realistic failure (`ValueError` from prometheus label-name mismatch).
- **Category R notif-emit at `:2501` and `:3205`** — `(httpx.HTTPError, asyncio.TimeoutError, RuntimeError)`: **completely off-target**. The call site (`notification_client.send_notification`) invokes a method that **does not exist on `NotificationClient`**, so the only exception actually raised is `AttributeError` — which none of the listed types catches. Compounding: `NotificationClient` is built on `aiohttp`, not `httpx`, so the `httpx` import added at `auto_trader.py:29` is effectively unused. The Plan's stated D-08 objective ("Category R observable notif-emit failure") is not achieved by the chosen clauses.

Flow is still recoverable (outer broad-excepts at `:2731` and `:3216` catch the AttributeError), but the new `logger.error("notif emit failed ...")` line will never fire in current code, and a future fix to `NotificationClient` (e.g., adding `send_notification` that internally raises `aiohttp.ClientError`) will still bypass the typed clause.

The new test (`test_te_cap_05_log_survival.py`) covers the cap-check breach path only — it gives **zero coverage** for the typed-except correctness at the Category-M and Category-R sites (cap-check `return`s at `:1989` before any notification or min-notional metric call).

## Warnings

### WR-01: Category-R typed-except does not match the actual exception raised; `httpx` import is dead code

**File:** `services/trading-engine/app/auto_trader.py:2501` and `services/trading-engine/app/auto_trader.py:3205` (also `:29` for the import)
**Issue:** Both Category-R rewrites catch `(httpx.HTTPError, asyncio.TimeoutError, RuntimeError)`. However:

1. **`NotificationClient` has no `send_notification` method.** `grep "def send_notification" services/trading-engine/app/services/notification_client.py` returns nothing — only `notify_trade_open`, `notify_trade_close`, `notify_error`, `notify_startup`, `notify_daily_summary` exist. The call `await notification_client.send_notification(...)` raises **`AttributeError`** every time it is reached. This is a pre-existing latent bug (visible in `auto_trader.py` since at least `9ab1e2f`), but Phase 17's typed-except now load-bears on the exception type.
2. **`NotificationClient` is built on `aiohttp`, not `httpx`** (`services/trading-engine/app/services/notification_client.py:6`). Even if `send_notification` existed and made HTTP calls, the relevant exception family would be `aiohttp.ClientError`, not `httpx.HTTPError`.
3. **`NotificationClient._post` already catches `except Exception` broadly** (`notification_client.py:83`) and returns `{"success": False, ...}` — so no HTTP-layer exception ever escapes the client even when the method exists.

Net effect: the new `logger.error(...)` "observable notif-emit failure" line is dead in current code. The AttributeError that actually fires propagates past the typed clause and is swallowed by the outer broad-except (`:2731` for the max-hold path via `_monitor_positions`, `:3216` for the limit-stop path which falls back to `_close_position`). Flow recovers, but the D-08 Category R "observable" objective is not achieved.

The `import httpx` at `auto_trader.py:29` is now effectively unused — `httpx` is referenced only in these two typed-except clauses that never match.

**Fix:**
```python
# Option A (preferred): match what is actually thrown today AND what would be
# thrown after a NotificationClient fix.
except (AttributeError, aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as notif_err:
    logger.error(
        "notif emit failed inside max-hold critical-error branch for %s: %r",
        position.symbol, notif_err,
    )

# Option B: keep typed list narrow, but FIRST fix the latent bug — add the
# missing send_notification method on NotificationClient (or change the call
# sites to use an existing method like notify_error).
```
Also remove the unused `import httpx` at `auto_trader.py:29` if the typed clauses no longer reference it. If httpx is genuinely needed elsewhere in the trading-engine, leave a follow-up comment pointing to the real usage so future autoflake passes don't strip it.

### WR-02: Category-M typed-except misses the realistic prometheus failure mode

**File:** `services/trading-engine/app/auto_trader.py:1594` and `services/trading-engine/app/auto_trader.py:1611`
**Issue:** The Category-M rewrite catches `(OSError, ImportError)`. The actual surface of `prometheus_client.Counter.labels(...).inc()` does not raise `OSError` (counters are in-process; no I/O). The realistic failure modes are:

- `ImportError` from the deferred `from app.core.metrics import trades_rejected_min_notional_total` — covered.
- `ValueError` if `breach_type=` or label names are renamed on the Counter definition in `app/core/metrics.py` without updating call sites — **not covered**, will propagate uncaught.
- `KeyError` / `AttributeError` if a refactor swaps the Counter for a different metric type — **not covered**.

The previous bare-except swallowed all of these (over-broad). The new typed list swings too narrow in the opposite direction: a Prometheus refactor that previously could go unnoticed will now crash the min-notional gate and skip the order-rejection path — meaning a real min-notional violation would be allowed through. The min-notional gate is a safety-relevant rail (sub-cap sizing on small balances), so silent skipping on a metric refactor is a regression.

**Fix:**
```python
except (ImportError, ValueError, AttributeError) as e:
    # Phase 17 TE-CAP-05 D-08 Category M — observable metric-emit failure.
    # OSError dropped (prometheus counters are in-process). ValueError + AttributeError
    # cover label-name mismatch / metric-type refactor.
    logger.warning("metrics emit failed (min_qty): %r", e)
```

### WR-03: New regression test does not exercise the Category-M or Category-R sites

**File:** `services/trading-engine/tests/test_te_cap_05_log_survival.py:174-235`
**Issue:** The test only exercises the cap-check breach path. The breach path `return`s at `auto_trader.py:1989` before any min-notional check (`_passes_min_notional` at `:1996`) or any notification call (`notification_client.send_notification` at `:2494`, `:3198`). So the test provides **zero coverage** for the four other typed-except rewrites in Plan 17-02 (`:1552`, `:1594`, `:1611`, `:2501`, `:3205`).

In particular, neither test detects:
- A bare `except:` re-introduced around the min-notional metric inc at `:1591-1593` or `:1608-1610`.
- A bare `except:` re-introduced around the critical notification at `:2494-2500` or `:3198-3204`.
- A regression where the typed Category-M except is changed to swallow `ValueError` silently (the gate would skip rejection on a Prometheus refactor without any test going red).

The test docstring itself is honest about its scope ("D-10 regression guarantee that the CRITICAL BREACH log line survives") so this isn't deception, but the PR-level commit message `123991f` claims "5 REQ-named broad-except sites" are rewritten with no corresponding test for 4 of the 5.

**Fix:** Add follow-on tests in the same file or a sibling, each forcing the relevant branch:
- Force `min_qty` reject path → assert `trades_rejected_min_notional_total.labels(reason="min_qty")` increments (mirror the metric pattern from the cap test).
- Force the max-hold force-close exception branch (mock `trading_engine.execute_market_order` to raise) → assert the outer `logger.error` at `:2486-2489` fires AND the inner notif path either succeeds or surfaces a logged warning. As written today, the inner path will raise AttributeError; the test would need to either fix the latent `send_notification` bug or assert on the outer-except log emission.

### WR-04: D-08 Category R "observable" claim contradicted by NotificationClient's internal swallow

**File:** `services/trading-engine/app/auto_trader.py:2502-2508` and `services/trading-engine/app/auto_trader.py:3206-3214` (comments)
**Issue:** Both new comments cite "D-08 Category R — observable notif-emit failure". But the chosen typed list `(httpx.HTTPError, asyncio.TimeoutError, RuntimeError)` cannot make a notification failure observable when:

1. The notification client's own `_post` catches everything broadly (`notification_client.py:83`) and returns `{"success": False}` — so the auto_trader sees a return value, not an exception.
2. The only exception that actually escapes the call (`AttributeError` from the missing method) is not in the typed list.

So neither the "observable failure" claim in the comment nor the D-08 plan objective is achieved by the diff. This is a documentation/intent gap that will mislead future readers — when the underlying `send_notification` is fixed, someone will assume Phase 17 already covered it.

**Fix:** Either (a) fix the underlying `NotificationClient` so it actually surfaces failures to the caller (raise on `success=False` or expose a typed exception), then update the auto_trader typed-except list to match the new exception family; or (b) demote the comment to "best-effort notif emit; current NotificationClient swallows internally, this except remains a forward-going guard for future refactors that surface failures upward".

## Info

### IN-01: Stale comment in `services/trading-engine/app/main.py:129` references the deleted route

**File:** `services/trading-engine/app/main.py:127-130`
**Issue:** Comment reads:
```
# Import Multi-Strategy Orchestration router (Phase 9). Was defined in
# handlers/orchestration.py but never actually mounted — every endpoint
# under /api/v1/orchestrator/* (incl. emergency-stop, risk/utilization,
# strategies/*) was dead. Wired up 2026-04-29.
```
After Phase 17 D-01 deletion, `emergency-stop` is no longer under `/api/v1/orchestrator/*`. The comment is mildly misleading but the file was not listed in Phase 17's changed files, so this is doc-rot, not a regression.

**Fix:** Update the comment to drop `emergency-stop` from the example list, or replace with `incl. risk/utilization, strategies/*, signals/*`.

### IN-02: Negative complement test uses `try/except Exception: pass` around the unit-under-test call

**File:** `services/trading-engine/tests/test_te_cap_05_log_survival.py:284-289`
**Issue:**
```python
try:
    await trader._execute_trade_with_setup(
        symbol="BTCUSDT", trade_setup=trade_setup
    )
except Exception:
    pass
```
The comment justifies it ("post-FILLED branches touch lots of services we haven't stubbed; we only assert about caplog, not the call's outcome"), but a bare `except Exception` around the SUT call is a test-smell pattern — if the cap-check path itself somehow raised before reaching the under-cap branch, the test would silently pass with a false-negative. The assertion (`no BREACH log emitted`) would still be a tautology over zero records.

**Fix:** Narrow the swallow to the exceptions actually expected from post-FILLED branches (`AttributeError, KeyError, TypeError` from un-stubbed services), or add a defensive assertion that at least the sizing log line emitted before the swallow (proving we got through cap-check and into the order branch).

---

_Reviewed: 2026-05-24T03:25:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
