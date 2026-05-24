---
phase: 17-execution-cap-hard-enforcement
reviewed: 2026-05-24T05:10:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - services/trading-engine/app/handlers/orchestration.py
  - services/trading-engine/app/auto_trader.py
  - services/trading-engine/tests/test_orchestration_emergency_stop_removed.py
  - services/trading-engine/tests/test_te_cap_05_log_survival.py
  - services/trading-engine/tests/test_te_cap_05_metric_emit_survival.py
findings:
  critical: 0
  warning: 0
  info: 1
  total: 1
status: issues_found
---

# Phase 17: Code Review Report (Iteration 2)

**Reviewed:** 2026-05-24T05:10:00Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found (one Info item carried forward from iteration 1)

## Summary

Iteration 2 re-review of the four WARNING fixes (WR-01..WR-04) and the two INFO items (IN-01, IN-02) from iteration 1. All four WARNINGs are resolved:

- **WR-01 RESOLVED.** `import httpx` at `auto_trader.py:29` was replaced with `import aiohttp` at `:30` — the dead import is gone. Both Category-R typed-except sites at `auto_trader.py:2515-2520` (max-hold critical-error branch) and `:3230-3235` (limit-stop both-orders-failed branch) now catch `(AttributeError, aiohttp.ClientError, asyncio.TimeoutError, RuntimeError)`. `AttributeError` covers the current latent `send_notification` missing-method bug (confirmed by inspection of `services/trading-engine/app/services/notification_client.py` — only `notify_trade_open`, `notify_trade_close`, `notify_error`, `notify_startup`, `notify_daily_summary`, `test_notification` exist; no `send_notification`). `aiohttp.ClientError` aligns with the transport layer the client is actually built on (`notification_client.py:6: import aiohttp`). Confirmed via `grep -rn "import httpx" services/trading-engine/app/` that `httpx` remains used in 18 unrelated files but no longer in `auto_trader.py`.

- **WR-02 RESOLVED.** Both Category-M typed-except sites at `auto_trader.py:1594` (min_qty branch) and `:1618` (min_notional branch) now catch `(ImportError, ValueError, AttributeError)`. `OSError` correctly dropped (Prometheus counters are in-process; no I/O). `ValueError` now covers the realistic `prometheus_client.Counter.labels()` label-name-mismatch failure. `AttributeError` covers Counter→Histogram metric-type swaps that remove `.labels()` / `.inc()`. The expanded inline comments at `:1595-1602` and `:1619-1626` accurately explain the rationale for each exception class.

- **WR-03 RESOLVED.** New file `tests/test_te_cap_05_metric_emit_survival.py` directly exercises both Category-M sites. Two `@pytest.mark.asyncio` tests inject a `MagicMock` Counter whose `.labels(...).inc()` raises `ValueError("Incorrect label names")` and assert: (a) the function still returns `(False, "min_qty")` / `(False, "min_notional")` (safety-rail integrity — metric-emit failure must NOT skip rejection), (b) the inline `logger.warning("metrics emit failed (...)")` fires, (c) `fake_counter.labels.assert_called_once_with(...)` confirms the test reaches the metric site and isn't bypassed upstream. The `_force_live_mode` autouse fixture correctly sets `trading_mode="LIVE"` so the PAPER short-circuit at `:1540` doesn't bypass the gate. The deferred-import pattern (`monkeypatch.setattr("app.core.metrics.trades_rejected_min_notional_total", fake_counter)` + `from app.core.metrics import trades_rejected_min_notional_total` inside `_passes_min_notional`) is sound — the deferred import re-resolves the name at each call site. The test will RED on a future narrowing of the typed tuple (e.g. back to `(ImportError,)` only): the injected `ValueError` would propagate uncaught past `_passes_min_notional`, killing the test at the call site. Honest framing in the docstring (lines 21-28) acknowledges the test PASSes on current code — it ships as a forward-going regression guarantee, not a current-bug-RED.

- **WR-04 RESOLVED.** The expanded comments at `auto_trader.py:2521-2528` and `:3236-3244` now explicitly describe (a) the typed-except family rationale, (b) the latent `NotificationClient.send_notification` missing-method bug, (c) why `AttributeError` is in the tuple (catches the current latent-bug behavior), (d) why `aiohttp.ClientError` is in the tuple (catches the post-fix transport behavior). No more "observable failure" claim contradicted by internal-swallow — the comment now correctly notes that the outer except at `:2499` / `:3252` stays as-is per D-08 explicit text and already logs `exc_info=True`.

Plan-01 deliverables (route deletion + RED 404 test) remain clean — unchanged by iteration 2 fixes.

**One INFO item carries forward:** IN-02 from iteration 1 (bare `try/except Exception: pass` around the SUT call in the negative-complement test at `tests/test_te_cap_05_log_survival.py:284-289`) was not addressed by the iteration-2 fixer. The lines are unchanged. Carrying forward verbatim below.

**Out of iteration-2 file scope:** IN-01 (stale `services/trading-engine/app/main.py:129` comment mentioning `emergency-stop`) is not addressed and not flagged here — `main.py` is not in iteration-2's `files` list. Item should be picked up in a separate doc-rot pass, not here.

**Boundary check passed.** `git diff HEAD~3 HEAD -- services/trading-engine/app/auto_trader.py` shows exactly 54 changed lines confined to the 5 typed-except sites + the import swap. No unrelated sites touched. No dead imports re-introduced. No other-module modifications under `app.services.*`, `app.handlers.*`, etc.

## Info

### IN-01 (carried from iteration 1, unchanged): Negative complement test uses `try/except Exception: pass` around the unit-under-test call

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

This was originally filed as IN-02 in iteration 1; renumbered to IN-01 here since the iteration-1 IN-01 (stale `main.py:129` comment) is out of iteration-2's file scope.

**Fix:** Narrow the swallow to the exceptions actually expected from post-FILLED branches (`AttributeError, KeyError, TypeError` from un-stubbed services), or add a defensive assertion that at least the sizing log line emitted before the swallow (proving we got through cap-check and into the order branch).

---

_Reviewed: 2026-05-24T05:10:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
_Iteration: 2 (auto re-review of iteration-1 fixes)_
