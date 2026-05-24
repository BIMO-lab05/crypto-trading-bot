---
phase: 17-execution-cap-hard-enforcement
fixed_at: 2026-05-24T03:55:00Z
review_path: .planning/phases/17-execution-cap-hard-enforcement/17-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 17: Code Review Fix Report

**Fixed at:** 2026-05-24T03:55:00Z
**Source review:** `.planning/phases/17-execution-cap-hard-enforcement/17-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope (Critical + Warning): 4
- Fixed: 4
- Skipped: 0
- Info findings (IN-01, IN-02): out of scope this iteration (fix_scope=critical_warning)

All fixes were applied inside an isolated git worktree (`/tmp/sv-17-reviewfix-VDDpbC` on branch `gsd-reviewfix/17-121815`) and fast-forwarded into `gsd/v1.3-ta-engine-correctness` by the cleanup tail. Each commit is independently verifiable; the file-level diff for each is small and surgical. The full Phase 17 gate-test suite (`test_te_cap_05_log_survival.py`, `test_auto_trader_min_notional.py`, `test_orchestration_emergency_stop_removed.py`) was run after the changes and is GREEN — 15 passed, 0 failed.

## Fixed Issues

### WR-01: Category-R typed-except does not match the actual exception raised; `httpx` import is dead code

**Files modified:** `services/trading-engine/app/auto_trader.py`
**Commit:** `d9b7619`
**Also resolves:** WR-04 (the "observable" claim in the inline comments at :2502-2508 / :3206-3214 is now accurate because the typed family catches the `AttributeError` that current code actually raises and the `logger.error("notif emit failed ...")` line now fires).

**Applied fix:**
- Replaced `import httpx` at `auto_trader.py:29` with `import aiohttp`. Confirmed `httpx` was referenced ONLY in the two dead typed-except clauses inside `auto_trader.py` (the unrelated comment at :377 referring to `funding_gate.py`'s httpx session is untouched and accurate). `httpx==0.27.0` remains in `services/trading-engine/requirements.txt` because `app/risk/funding_gate.py` still imports it for its own AsyncClient — out of D-06 scope.
- At `auto_trader.py:2501` (max-hold critical-error branch) and `auto_trader.py:3205` (limit-stop both-orders-failed critical branch), replaced the typed tuple `(httpx.HTTPError, asyncio.TimeoutError, RuntimeError)` with `(AttributeError, aiohttp.ClientError, asyncio.TimeoutError, RuntimeError)`.
- Extended inline comments at both sites to document why `AttributeError` is in the list (covers the current `send_notification` missing-method latent bug) and why `aiohttp.ClientError` replaced `httpx.HTTPError` (NotificationClient is built on aiohttp, not httpx).

**Rationale:** `services/trading-engine/app/services/notification_client.py` was inspected end-to-end. NotificationClient exposes only `notify_trade_open`, `notify_trade_close`, `notify_error`, `notify_startup`, `notify_daily_summary`, `test_notification` — NO `send_notification`. The Phase 17 typed clauses caught exception families that the call sites literally cannot raise. The inner `logger.error("notif emit failed ...")` was dead. After this fix, the AttributeError raised by every reachable execution of the branch is caught by the new tuple, the inline log fires, and the D-08 Category-R "observable" objective is achieved. The fix is forward-compatible: once the latent `send_notification` bug is fixed (separately — see "Issues Not Fixed" below), the new family also catches the realistic aiohttp transport exceptions.

### WR-02: Category-M typed-except misses the realistic Prometheus failure mode

**Files modified:** `services/trading-engine/app/auto_trader.py`
**Commit:** `dec42a8`

**Applied fix:**
- At `auto_trader.py:1594` (min_qty rejection branch) and `auto_trader.py:1611` (min_notional rejection branch), replaced the typed tuple `(OSError, ImportError)` with `(ImportError, ValueError, AttributeError)`.
- Extended inline comments to document each member of the new tuple:
  - `ImportError` covers the deferred `from app.core.metrics import trades_rejected_min_notional_total` at `:1589` / `:1606`.
  - `ValueError` covers `prometheus_client.Counter.labels(...)` raising on label-name mismatch — the realistic refactor risk when the Counter definition in `app.core.metrics` is renamed without updating the call sites here.
  - `AttributeError` covers a Counter→Histogram metric-type swap that removes `.labels()` or `.inc()`.
  - `OSError` was dropped per REVIEW.md rationale (Prometheus counters are in-process; no I/O).

**Rationale:** The min-notional gate is a safety-relevant rail. Under the original tuple, a future Prometheus refactor would propagate `ValueError` uncaught past `_passes_min_notional`, skipping the rejection log and `(False, reason)` return — allowing a real min-notional violation through the gate. The new tuple preserves the observable-warning + reject-decision contract on a wider, realistic refactor surface.

### WR-03: New regression test does not exercise the Category-M or Category-R sites

**Files modified:** `services/trading-engine/tests/test_te_cap_05_metric_emit_survival.py` (new sibling test file)
**Commit:** `fa78e51`

**Applied fix:**
Added two focused regression tests for the Category-M sites widened in WR-02:

- `test_min_qty_reject_survives_value_error_from_counter_inc`: forces the qty < min_order_qty rejection path. Patches `app.core.metrics.trades_rejected_min_notional_total` with a MagicMock whose `.labels().inc()` raises `ValueError` (label-name mismatch). Asserts:
  - `_passes_min_notional` returns `(False, "min_qty")` — safety rail preserved on metric failure.
  - The fake counter's `.labels()` was called with `(symbol="BTCUSDT", reason="min_qty")` (proves we reached the metric site and didn't bypass it upstream).
  - The inline `logger.warning("metrics emit failed (min_qty): ...")` fires.
- `test_min_notional_reject_survives_value_error_from_counter_inc`: analogous coverage for `:1611`, forcing `notional < min_notional` with `qty ≥ min_qty`.

Both tests use the existing patterns from `test_auto_trader_min_notional.py` (LIVE-mode autouse fixture, `_StubInstrumentsCache`, `# noqa: F401` import preloads for `app.main` + `app.core.metrics` to avoid prometheus `Duplicated timeseries` errors on re-import).

**Tier-3 runtime verification:** Both tests PASSED on host pytest. The wider Phase 17 gate test suite (`test_te_cap_05_log_survival.py`, `test_auto_trader_min_notional.py`, `test_orchestration_emergency_stop_removed.py`) remained 15/15 green after the changes.

**Rationale:** Forward-going regression guarantee. If a future refactor narrows the typed-except tuple back to `(ImportError,)` or `(OSError, ImportError)` — the original Phase 17 mistake — these tests RED loudly because `ValueError` would propagate uncaught past the metric site and skip the rejection log + return.

### WR-04: D-08 Category R "observable" claim contradicted by NotificationClient's internal swallow

**Files modified:** (covered in WR-01 commit `d9b7619`)
**Commit:** `d9b7619`

**Applied fix:** Self-resolves once WR-01 fixes the typed-except family. The inline comments at `:2501-2517` and `:3205-3225` were extended to document precisely which exception each tuple member covers (AttributeError for the current missing-method latent bug, aiohttp.ClientError for the transport family once that bug is fixed). The "observable notif-emit failure" claim is now accurate because the typed family catches the `AttributeError` that current code raises, making the inner `logger.error(...)` reachable and observable.

## Issues Not Fixed (Out of Scope / Forward-Going)

### Pre-existing latent bug — `NotificationClient.send_notification` does not exist

**Files involved:** `services/trading-engine/app/auto_trader.py:2494`, `services/trading-engine/app/auto_trader.py:3198` (also `:3181`)
**Severity:** Latent — flow recovers via outer broad-except (`:2731` for max-hold, `:3216` for limit-stop). No silent data corruption; but the *intended* critical-alert notification on max-hold force-close failure and on limit-stop both-orders-failed failure has been undeliverable since the call site was introduced.

**Root cause:** `services/trading-engine/app/services/notification_client.py` exposes `notify_trade_open`, `notify_trade_close`, `notify_error`, `notify_startup`, `notify_daily_summary`, `test_notification` — no `send_notification` method. Every `await notification_client.send_notification(...)` raises `AttributeError`.

**Why not fixed in this iteration:**
- Out of D-06 scope: the constraint explicitly prohibited touching `notification_client.py` or anything outside `auto_trader.py` + `tests/test_te_cap_05_log_survival.py` (plus the sibling test file added under WR-03).
- A "real" fix is one of:
  - (a) Add a `send_notification(title, message, severity)` method on `NotificationClient` that maps to `_post("/api/v1/notify/critical", ...)` or routes by severity, AND verify the notification-service endpoint accepts that schema.
  - (b) Change both call sites to use the existing `notify_error(error_message, context)` method. This is the simpler scope-confined fix, but the semantics differ (notify_error is for non-critical error reports; the call sites here are deliberately marked "🚨 CRITICAL - MANUAL INTERVENTION REQUIRED" and severity="critical" — the receiver schema and downstream Telegram alert routing should be re-examined).

**Recommended follow-up:** File as a separate quick-task or Phase 18 work item titled "trading-engine: implement NotificationClient.send_notification or migrate critical-alert callsites to notify_error". Include verification that the downstream notification-service `/api/v1/notify/*` endpoint matches whichever option is chosen.

**Mitigation in place:**
- WR-01 commit (`d9b7619`) ensures the AttributeError is now CAUGHT by the typed except inside the inner block and emits a `logger.error(...)` warning — so operators get observability that the critical-alert path failed (via stdout/log aggregation) even though Telegram delivery doesn't happen. Without WR-01, the AttributeError silently fell through to the outer broad-except's `exc_info=True` log under the original exception's traceback, conflating two distinct failure modes.

### Category-R notification-emit path test coverage (subset of WR-03)

**Files involved:** `services/trading-engine/app/auto_trader.py:2501`, `services/trading-engine/app/auto_trader.py:3205`
**Severity:** Test-coverage gap, not a code defect.

**Why not added in this iteration:** The Category-R notif-emit path is awkward to test directly because the underlying call site (`send_notification`) is the pre-existing latent bug documented above. A test added today would assert "AttributeError reaches the inner logger.error" — which becomes stale immediately once the latent bug is filed and fixed (because the call site will raise `aiohttp.ClientError` or return `{"success": False}` instead). Per WR-03 fix guidance + advisor recommendation, the more durable target is the Category-M sites (which I did cover).

**Recommended follow-up:** When the latent `send_notification` bug is fixed in the separate phase, add the Category-R test alongside that fix — test would mock `NotificationClient.send_notification` to raise `aiohttp.ClientError` and assert the inner `logger.error("notif emit failed ...")` fires AND the outer broad-except's recovery path runs.

### Info findings (out of scope this iteration)

- **IN-01**: Stale comment in `services/trading-engine/app/main.py:127-130` references the deleted `/api/v1/orchestrator/emergency-stop` route. fix_scope=critical_warning excluded Info findings; documenting here so it doesn't get lost.
- **IN-02**: Negative complement test at `test_te_cap_05_log_survival.py:284-289` uses `try/except Exception: pass` around the SUT call. Same reason.

Both can be folded into a small `chore(17): post-review polish` follow-up commit or the next phase's hygiene wave.

---

_Fixed: 2026-05-24T03:55:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
