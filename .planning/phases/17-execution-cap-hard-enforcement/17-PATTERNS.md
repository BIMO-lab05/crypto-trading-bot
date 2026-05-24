# Phase 17: Execution-Cap Hard Enforcement — Pattern Map

**Mapped:** 2026-05-24
**Files analyzed:** 4 (1 DELETE + 1 MODIFY block in `orchestration.py`, 1 MODIFY block in `auto_trader.py`, 2 new test files)
**Analogs found:** 4 / 4 (all in-repo, exact-match)

---

## File Classification

| File | Change | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|---|
| `services/trading-engine/app/handlers/orchestration.py:591-622` | **DELETE** route handler | controller (route) | request-response | n/a (deletion — no analog needed) | n/a |
| `services/trading-engine/app/handlers/orchestration.py:725-727` | **MODIFY** comment | docstring/comment | n/a | `handlers/orchestration.py:823-837` (force-signal "Auth note" header) | exact |
| `services/trading-engine/app/auto_trader.py:1500-3210` | **MODIFY** broad-except sites per M/P/R/default taxonomy | service (order pipeline) | event-driven | self (`auto_trader.py:1541-1574, 1586-1610` already show the M/P pattern in-file) | exact (in-file precedent) |
| `services/trading-engine/tests/test_orchestration_emergency_stop_deleted.py` (suggested name) | **CREATE** negative 404 test | test | request-response | `services/trading-engine/tests/test_force_signal.py:42-67, 118-167` | exact |
| `services/trading-engine/tests/test_te_cap_05_log_survival.py` | **CREATE** caplog regression test | test | event-driven | `services/trading-engine/tests/test_auto_trader_min_notional.py:240-378` + caplog idiom from `test_force_signal.py:203-230` | exact |

---

## Pattern Assignments

### 1. `handlers/orchestration.py:591-622` — DELETE the unauthenticated `emergency_stop` route

**No analog needed.** D-02 locks "delete, no 410-Gone shim, no 403-always stub." The deletion is a clean removal.

**Surface to delete (verbatim, lines 591-622):**

```python
@router.post("/emergency-stop", summary="Emergency stop all strategies")
async def emergency_stop(
    reason: str = Query("Manual emergency stop", description="Reason for stop"),
):
    """
    Trigger emergency stop for all trading

    Immediately pauses all strategies and can optionally
    close all open positions.
    """
    try:
        # Stop via risk coordinator
        coordinator = get_risk_coordinator()
        result = coordinator.emergency_stop(reason)

        # Also pause all strategies via orchestrator
        orchestrator = get_strategy_orchestrator()
        orchestrator.pause_all(reason)

        logger.critical(f"EMERGENCY STOP triggered: {reason}")

        return {
            "success": True,
            "message": "Emergency stop activated",
            "reason": reason,
            **result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Error triggering emergency stop: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**Import-cleanup callout (memory file `feedback_main_imports_autoflake.md`):**
After deletion, `coordinator.emergency_stop` and `orchestrator.pause_all` become the only call-sites in the file. If `get_risk_coordinator` / `get_strategy_orchestrator` become unused **inside this single route block only**, autoflake on the next refactor pass may strip them — but `orchestration.py:22-30` shows they're used by many other routes (`get_strategy_orchestrator` at `:587, :703`, etc.), so no `# noqa: F401` is needed. **Verify with grep before commit.**

---

### 2. `handlers/orchestration.py:725-727` — UPDATE auth-note comment (D-12)

**Analog (pattern to mirror):** `services/trading-engine/app/handlers/orchestration.py:835-837`

```python
# Auth note: trading-engine has no auth middleware; admin routes are protected
# upstream at the api-gateway. Phase 2 host-side suite talks directly to :8005,
# but the TRADING_MODE gate prevents any non-test invocation in real-money mode.
```

**Current text at `:725-727` (false claim about emergency-stop):**

```python
# Auth note: trading-engine has no auth middleware; all admin routes are
# protected upstream at the api-gateway. We name the prefix `/admin/...` for
# routing convention, but enforce nothing at this layer.
```

**Rewrite goal (D-12):** acknowledge emergency-stop now lives gateway-only, drop the dangling "all admin routes" claim. Mirror the force-signal-style comment that names what *this* router does protect (rolling-confidence gate for indicator router; "no surface" for the deleted emergency-stop).

---

### 3. `auto_trader.py:1500-3210` — MODIFY broad-except sites per D-08 taxonomy

**No analog file needed — `auto_trader.py` already contains the M and P patterns inline.** The planner reads the range end-to-end in step 8 (per D-09) and emits the M/P/R/default classification table directly into PLAN.md.

**Pattern anchor — Category P (Decimal/parse/cache-lookup) already in-file at `:1541-1574`:**

```python
        # Normalise call-site types (Decimal vs float vs int) to Decimal once.
        try:
            qty_d = _Decimal(str(quantity))
            price_d = _Decimal(str(price))
            balance_d = _Decimal(str(balance))
        except Exception:                                       # ← REWRITE TARGET (:1551)
            # Defensive — bad inputs shouldn't crash the gate.
            logger.warning(
                f"min-notional gate: could not parse qty/price/balance for {symbol}, allowing"
            )
            return True, None

        # Deferred import: avoids a circular at module load and lets tests
        # monkeypatch app.main.get_instruments_cache cleanly.
        try:
            from app.main import get_instruments_cache
        except Exception as e:                                  # ← already log+continue
            logger.warning(
                f"min-notional gate: instruments cache import failed for {symbol} ({e!r}), allowing"
            )
            return True, None

        try:
            spec = await get_instruments_cache().get(symbol)
        except Exception as e:                                  # ← already log+continue
            logger.warning(
                f"min-notional gate: cache.get({symbol}) raised {e!r}, allowing"
            )
            return True, None
```

**The `:1551` rewrite must follow D-08 Category P verbatim:**
```python
except (InvalidOperation, ValueError, TypeError) as e:
    # Defensive — bad inputs shouldn't crash the gate (preserves comment).
    logger.warning(
        "min-notional gate: parse failed for %s: %r — allowing", symbol, e
    )
    return True, None
```
Required new import at top of file: `from decimal import Decimal, InvalidOperation` (verify if already present).

**Pattern anchor — Category M (metrics-emit silent swallow) already in-file at `:1586-1610`:**

```python
        if qty_d < spec.min_order_qty:
            try:
                from app.core.metrics import trades_rejected_min_notional_total

                trades_rejected_min_notional_total.labels(
                    symbol=symbol, reason="min_qty"
                ).inc()
            except Exception:                                   # ← REWRITE TARGET (:1593)
                pass                                            # ← silent — must add logger.warning
            ...

        if spec.min_notional is not None and notional < spec.min_notional:
            try:
                from app.core.metrics import trades_rejected_min_notional_total

                trades_rejected_min_notional_total.labels(
                    symbol=symbol, reason="min_notional"
                ).inc()
            except Exception:                                   # ← REWRITE TARGET (:1609)
                pass                                            # ← silent — must add logger.warning
```

**`:1593` and `:1609` rewrite per D-08 Category M:**
```python
except (OSError, ImportError) as e:
    logger.warning("metrics emit failed (min_qty): %r", e)
```
The CLAUDE.md rule is explicit: "Must NOT silently `pass` — `logger.warning` is mandatory so the swallow is observable."

**Pattern anchor — Category R (notification-path bare except) at `:2482-2501`:**

```python
        except Exception as e:
            logger.error(
                f"[MAX_HOLD] ❌ Exception closing {position.symbol} after {hours_held:.1f}h: {e}",
                exc_info=True,
            )

            # Send critical alert about failure
            try:
                notification_client = get_notification_client()
                await notification_client.send_notification(
                    title="🚨 CRITICAL - Failed to Force Close Position",
                    message=f"Failed to close {position.symbol} after {hours_held:.1f}h\n"
                    f"Error: {str(e)}\n"
                    f"MANUAL INTERVENTION REQUIRED",
                    severity="critical",
                )
            except:                                             # ← REWRITE TARGET (:2498)
                pass                                            # ← bare except + silent
```

**`:2498` and `:3196` rewrite per D-08 Category R:**
```python
except (httpx.HTTPError, asyncio.TimeoutError, RuntimeError) as e:
    logger.error("notif emit failed inside critical-error branch: %r", e)
```
Notice the **outer** `except Exception as e:` at `:2482` already logs with `exc_info=True` — that one **stays as-is** per D-08. The INNER notification swallow is the unsafe one; tightening it surfaces the real outer error instead of mask-cascading.

**Default if uncertain (D-08 tie-breaker):**
```python
except Exception as e:
    logger.exception("...site-specific context...")
    raise
```

**Cap-enforcement region (`:1962-1986`) is READ-ONLY — DO NOT MODIFY:**

```python
            cap_fraction = self.settings.max_risk_per_trade
            cap_value = float(balance) * cap_fraction
            if position_value > cap_value:
                from app.core.metrics import risk_limit_breaches_total

                risk_limit_breaches_total.labels(breach_type="position_size").inc()
                logger.critical(
                    f"[RISK_GATE] PER_TRADE_CAP BREACH | symbol={symbol} "
                    f"attempted=${position_value:.2f} cap=${cap_value:.2f} "
                    f"({cap_fraction:.1%} of ${float(balance):.2f}) "
                    f"leverage={leverage:.1f}x allocation={symbol_allocation:.0%} "
                    f"- REJECTING. Reduce symbol_allocations[{symbol}] or leverage."
                )
                self.total_trades_rejected += 1
                return
```

This is the D-10 assertion target. Phase 17 protects it from being swallowed — does not touch it.

---

### 4. `tests/test_orchestration_emergency_stop_deleted.py` — CREATE 404 negative test

**Analog:** `services/trading-engine/tests/test_force_signal.py:42-67, 118-167`

This is the canonical "trading-engine has no auth middleware → mount just the router on a fresh `FastAPI()` → drive via `TestClient`" pattern.

**App-construction pattern to copy (`test_force_signal.py:42-52`):**

```python
@pytest.fixture
def app() -> FastAPI:
    """Build a minimal FastAPI app exposing only the force-signal router."""
    app = FastAPI()
    app.include_router(admin_force_signal_router)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)
```

**Adapted for the 404 test (use `orchestration_router`, the one whose prefix is `/api/v1/orchestrator`):**

```python
from app.handlers.orchestration import router as orchestration_router

@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(orchestration_router)
    return app
```

**Response-assertion pattern (`test_force_signal.py:149-167`) for the 404 case:**

```python
def test_emergency_stop_route_deleted_returns_404(client: TestClient):
    """POST to the deleted trading-engine emergency-stop route → 404.

    Phase 17 D-01: route removed; api-gateway at /api/portfolio/emergency-stop
    is the sole admin-guarded entry. Any direct caller to :8005 must see a
    visible failure (404), not silent swallow.
    """
    resp = client.post("/api/v1/orchestrator/emergency-stop")
    assert resp.status_code == 404, (
        f"Expected 404 after route deletion, got {resp.status_code}: {resp.text}"
    )
```

**TDD anchor (D-specifics §1, line 164):** write this test BEFORE the deletion. Watch it fail (current 200/500). Delete the route. Watch it pass (404).

**Note:** This single new test file replaces any need to extend api-gateway tests — the positive path at `services/api-gateway/tests/test_gateway_80_coverage.py:265-279` and `services/api-gateway/tests/test_main.py:281-290` already covers admin → 200 + `Path.write_text` invoked + 500 on OSError. Phase 17 runs both suites in-container (CLAUDE.md gotcha) and confirms green.

---

### 5. `tests/test_te_cap_05_log_survival.py` — CREATE the D-10 caplog regression test

**Primary analog:** `services/trading-engine/tests/test_auto_trader_min_notional.py:240-378` (drives `_execute_trade_with_setup` via stubbed dependencies; mutates `total_trades_rejected` as the success/fail axis).

**Secondary analog (caplog idiom):** `services/trading-engine/tests/test_force_signal.py:203-230` (`caplog.at_level` + `caplog.text` substring + `caplog.records` iteration).

**Tertiary analog (counter introspection):** `test_auto_trader_min_notional.py:210-231`:

```python
counter = metrics.trades_rejected_min_notional_total.labels(
    symbol="BTCUSDT", reason="min_qty"
)
before = counter._value.get()  # type: ignore[attr-defined]
...
after = counter._value.get()  # type: ignore[attr-defined]
assert after == before + 1
```

This is the project's blessed pattern for asserting `prometheus_client.Counter` increments without mocking the metric module. **Use it for D-10's secondary assertion** (`risk_limit_breaches_total.labels(breach_type="position_size").inc()` called).

**Imports-pattern to mirror (`test_auto_trader_min_notional.py:26-34`):**

```python
# Pre-import app.main so the deferred `from app.main import get_instruments_cache`
# inside the helper finds the module already in sys.modules. Importing it lazily
# during a test re-runs prometheus_client.Counter() registrations and trips
# `Duplicated timeseries in CollectorRegistry` against the default registry.
import app.main  # noqa: F401
import app.core.metrics  # noqa: F401  # pre-load so helper's deferred import succeeds

from app.auto_trader import AutoTrader
```

**The `# noqa: F401` is load-bearing.** Per memory file `feedback_main_imports_autoflake.md` — autoflake will strip these otherwise and break Counter re-registration ordering.

**Trader fixture (`test_auto_trader_min_notional.py:72-76`):**

```python
@pytest.fixture
def trader():
    """Fresh AutoTrader for each test (no _trading_loop running)."""
    t = AutoTrader(symbols=["BTCUSDT"])
    return t
```

**Dep-stubbing helper to extend (`test_auto_trader_min_notional.py:250-279`)** — this gives `_execute_trade_with_setup` what it needs (balance, position_sizer.quantity, position_sizer.position_value) without standing up the real services. **D-10 setup must force `position_value > cap_value`:** set `paper_engine.get_balance(...)` to e.g. `100.0` so `cap_value = 100 * 0.02 = $2`, then pick `position_sizer_qty` and `entry_price` such that `quantity * entry_price > $2` (e.g. qty=`0.001`, price=`60000` → position_value=$60 >> $2).

**Caplog-assertion pattern from `test_force_signal.py:203-220`:**

```python
def test_per_trade_cap_breach_log_survives_to_caplog(trader, monkeypatch, caplog):
    """D-10: force position_value > cap_value; assert the
    `[RISK_GATE] PER_TRADE_CAP BREACH` CRITICAL log line at
    auto_trader.py:1978-1984 reaches caplog (no broad-except swallow)."""
    _patch_execute_trade_deps(
        monkeypatch,
        balance=100.0,            # cap = $2 at default max_risk_per_trade=0.02
        paper_engine=...,
        position_sizer_qty=Decimal("0.001"),  # position_value = 0.001 * 60000 = $60 >> $2
    )

    import app.core.metrics as metrics
    counter = metrics.risk_limit_breaches_total.labels(breach_type="position_size")
    before = counter._value.get()  # type: ignore[attr-defined]

    with caplog.at_level(logging.CRITICAL, logger="app.auto_trader"):
        await trader._execute_trade_with_setup(symbol="BTCUSDT", trade_setup=<setup>)

    # Primary D-10 assertion: log line reached caplog.
    assert any(
        "[RISK_GATE] PER_TRADE_CAP BREACH" in rec.message
        for rec in caplog.records
    ), f"BREACH log swallowed; got: {[r.message for r in caplog.records]!r}"

    # Secondary D-10 assertion: counter incremented.
    after = counter._value.get()  # type: ignore[attr-defined]
    assert after == before + 1, "risk_limit_breaches_total not incremented"
```

**Note on `_execute_trade_with_setup` entry shape:** the cap-check at `:1962-1986` is inside `_execute_trade_with_setup` (not the older `_execute_trade` at `:3468`). The test must drive `_execute_trade_with_setup(symbol, trade_setup=TradeSetup(...))`. Inspect `_execute_trade_with_setup` arg shape during plan-phase reading (the `_claim_open_slot` gate at `:1674` must be either bypassed or no-op'd via `trader._claim_open_slot = AsyncMock(return_value=True)`).

---

## Shared Patterns

### Trading-engine FastAPI test bootstrap (no auth middleware)

**Source:** `services/trading-engine/tests/test_force_signal.py:42-52` and `tests/test_handler_endpoints.py:12-19`
**Apply to:** all trading-engine route tests in Phase 17

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.handlers.orchestration import router as orchestration_router

@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(orchestration_router)
    return app

@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)
```

Trading-engine has zero auth middleware (per `handlers/orchestration.py:725-727`), so the gateway's `admin_client` fixture pattern is **NOT** ported here — plain `TestClient` suffices.

### Prometheus counter introspection (no metric mocking needed)

**Source:** `services/trading-engine/tests/test_auto_trader_min_notional.py:210-231`
**Apply to:** the D-10 secondary assertion on `risk_limit_breaches_total`

```python
import app.core.metrics as metrics
counter = metrics.<counter>.labels(<labels>)
before = counter._value.get()  # type: ignore[attr-defined]
# ... exercise code ...
after = counter._value.get()   # type: ignore[attr-defined]
assert after == before + 1
```

### Caplog assertion at CRITICAL level

**Source:** `services/trading-engine/tests/test_ml_gate_auto_flip.py:165-172` and `test_force_signal.py:203-230`
**Apply to:** the D-10 primary assertion (`[RISK_GATE] PER_TRADE_CAP BREACH` survives)

```python
with caplog.at_level(logging.CRITICAL, logger="app.auto_trader"):
    await ...

assert any(
    "[RISK_GATE] PER_TRADE_CAP BREACH" in rec.message
    for rec in caplog.records
), f"expected critical log not found in {[r.message for r in caplog.records]!r}"
```

Note the `logger=` keyword pins the caplog filter to the module the log line is emitted from. `auto_trader.py` uses `logger = logging.getLogger(__name__)` so the logger name is `"app.auto_trader"`.

### Conventional-commit shapes (CLAUDE.md project rule)

**Apply to all Phase 17 commits:**

| Change | Commit prefix |
|---|---|
| Delete the trading-engine `/emergency-stop` route + update `:725-727` comment | `fix(trading-engine):` (single commit, comment piggy-backs per specifics §1) |
| Rewrite the `auto_trader.py` broad-except sites | `fix(trading-engine):` per M/P/R taxonomy commit, grouped logically (≤10 unstaged files at a time per CLAUDE.md) |
| New 404 test | `test(trading-engine):` |
| New caplog regression test | `test(trading-engine):` |

**Caveman voice rule (CLAUDE.md user instructions):** caveman voice is for *prose* in chat with the operator — commit messages, code, and PR descriptions stay in normal English. All commit messages above are normal English.

### `# noqa: F401` on test-patched / pre-load imports

**Source:** `services/trading-engine/tests/test_auto_trader_min_notional.py:30-31` (and memory file `feedback_main_imports_autoflake.md`)
**Apply to:** `test_te_cap_05_log_survival.py` if it pre-imports `app.main` or `app.core.metrics` for the same Counter-registration reason

### `pathlib.Path.write_text` mocking — does NOT apply to Phase 17

Per CLAUDE.md gotcha, `Path.write_text` bypasses `builtins.open`. The api-gateway tests already use the correct `patch("pathlib.Path.write_text")` pattern at `test_gateway_80_coverage.py:267, 277` and `test_main.py:283, 296` — Phase 17 does NOT touch these tests, just verifies they still pass after running. **Callout retained here so the planner does not accidentally introduce a parallel kill-switch writer in trading-engine that would need this mock (D-04 forbids dual writers).**

### api-gateway tests run in-container (CLAUDE.md gotcha)

**Apply to:** the verification step that confirms `test_gateway_80_coverage.py:262-279` and `test_main.py:277-296` still green after Phase 17 ships.

```bash
docker exec crypto-bot-api-gateway pytest services/api-gateway/tests/test_gateway_80_coverage.py::TestErrorHandling -v
docker exec crypto-bot-api-gateway pytest services/api-gateway/tests/test_main.py::TestEmergencyStop -v
```

Host-side pytest gives spurious 401 (fastapi 0.136); container pins 0.109 (returns 403 as tests assert).

### trading-strategy-dev SKILL — verify-stack alignment

**Relevant for Phase 17 because TE-CAP-05's "log line survives to caplog" is a verification concern**, not a feature claim. The `.claude/skills/verify-stack/SKILL.md` PASS gates apply only to **runtime** features (live prices, notifications, DB rows, restarts) — Phase 17 ships a log-line guarantee verified by unit-level `caplog`, so the verify-stack 4-gate checklist is **not** applicable. The blessed signal that Phase 17 ships green is: both new tests pass + the two existing api-gateway tests pass in-container + a one-shot manual `curl :8005/api/v1/orchestrator/emergency-stop` returns 404 against the redeployed container.

---

## No Analog Found

All files in Phase 17 have exact in-repo analogs. None require RESEARCH.md fallback (Phase 17 ran skip-research per the orchestrator note).

---

## Metadata

**Analog search scope:**
- `services/trading-engine/app/handlers/`
- `services/trading-engine/app/`
- `services/trading-engine/tests/`
- `services/api-gateway/app/main.py` (cross-service comparison)
- `services/api-gateway/tests/` (cross-service comparison)
- `services/trading-engine/app/core/metrics.py`

**Files scanned (Read calls):**
- `services/trading-engine/app/handlers/orchestration.py` (3 non-overlapping ranges: `:1-60`, `:580-639`, `:700-859`)
- `services/api-gateway/app/main.py` (`:1740-1814`)
- `services/api-gateway/tests/conftest.py` (full)
- `services/api-gateway/tests/test_gateway_80_coverage.py` (`:255-289`)
- `services/api-gateway/tests/test_main.py` (`:270-294`)
- `services/trading-engine/tests/conftest.py` (full)
- `services/trading-engine/tests/test_auto_trader_min_notional.py` (full)
- `services/trading-engine/tests/test_force_signal.py` (`:1-230`)
- `services/trading-engine/tests/test_handler_endpoints.py` (`:1-100`)
- `services/trading-engine/app/auto_trader.py` (4 non-overlapping ranges: `:325-355`, `:1540-1629`, `:1656-1745`, `:1955-2044`, `:2480-2519`, `:3180-3219`)
- `services/trading-engine/app/core/metrics.py` (`:220-244`)
- `.claude/skills/verify-stack/SKILL.md` (full)

**Pattern extraction date:** 2026-05-24
