# WS1-A: Technical-Analysis Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix six correctness defects in the technical-analysis service — a phantom directional signal on zero information, sub-$1 price precision destroyed by `round(x, 2)`, endpoint parameters that ignore their own Settings, and two indicators that are computed every cycle but never consulted — then lock the precision class shut with an AST guard.

**Architecture:** Six independent, surgical changes to an existing FastAPI service. No new modules except one test file and one AST-guard test. Each task is test-first: write a test that fails against current code, make it pass with the minimal edit, commit. Nothing here changes the trading-engine.

**Tech Stack:** Python 3.12, FastAPI, pandas, pytest (`asyncio_mode = auto`), `unittest.mock.patch`.

## Global Constraints

These apply to **every** task. They are not optional and they are not repeated in each step.

- **The account is $100.** Never write an account-size literal in any file, including tests. Host-run tests may `from shared.account import ACCOUNT_EQUITY_USD`.
- **Run every test from the service directory:** `cd services/technical-analysis`. The service `pytest.ini` sets `pythonpath = .` relative to its own directory; running from the repo root will not import `app`.
- **Always pass `--no-cov`.** The repo-root `pytest.ini` injects `--strict-config` and coverage reporting.
- **This service has NO `conftest.py` anywhere** — not in `tests/`, not in `tests/unit/`, not at the service root. Test files under `tests/unit/` self-insert the service root on `sys.path` with:
  ```python
  import sys
  sys.path.insert(
      0, str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent)
  )
  ```
  Files directly in `tests/` need one fewer `.parent`. Copy the shim; do not create a `conftest.py`.
- **`asyncio_mode = auto`** and `--strict-markers` are set. Do not register new markers. Do not write an `event_loop` fixture.
- **Known-failure baseline for this service: 3 failures out of 481 collected** — 2 × `test_comprehensive_80` (DataFrame issues) and 1 × `test_signal_aggregator_confidence_zero::test_empty_signal_list_returns_neutral_fallback`. Task 1 fixes the third, taking the baseline to **2**. Any failure outside that list is a regression you caused.
- **Never round a price-domain value.** `round(x, 2)` on ADA (~$0.60, tick 0.0001) destroys precision and caused 30+ flip-flop losses (commit `487d1bd`). The established fix in this repo is `float(x)` — full precision — NOT tick quantization. Tick quantization belongs at order time in the trading-engine (`app/costs.py`, `limit_order_executor`), never in indicator or strategy math. Dimensionless values (RSI 0–100, confidence 0–1, volume ratios) may stay rounded.
- **The format hook runs ruff at 88 columns while the repo uses 100, and has stripped imports before.** Make surgical single-line edits. After any edit touching an import block, run `git diff` and check for import churn before committing.
- **`git status` exceeds 60 seconds on this NTFS/WSL mount.** Never run bare `git status` or `git add -A`. Commit with explicit pathspecs: `git commit -- <path> <path>`.
- **Commit one task per commit**, conventional message, `fix(technical-analysis): …` or `test(technical-analysis): …`.

---

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `app/handlers/analysis.py` | The TA-side aggregator: an async **function** `get_aggregated_signal`, not a class. Builds `(label, confidence)` tuples, weighted-sums them, returns the response dict. | 1, 5 |
| `app/strategies/squeeze_momentum_strategy.py` | LIVE strategy served at `/api/v1/strategies/sqzmom/signal/{symbol}`. Returns entry/stop/TP. | 2 |
| `app/indicators/sqzmom_enhanced.py` | `SqueezeMetadata.to_dict()` serializes bands and price. Library-contract rot — not on the live route. | 3 |
| `app/main.py` | Route definitions. `Query(default=…)` literals duplicate Settings values. | 4 |
| `tests/test_signal_aggregator_confidence_zero.py` | Existing; holds the currently-red test that Task 1 turns green. | 1 |
| `tests/unit/test_sqzmom_strategy_precision.py` | **NEW** — ADA-scale precision assertions. | 2, 3 |
| `tests/test_endpoint_defaults_from_settings.py` | **NEW** — route defaults track Settings. | 4 |
| `tests/test_aggregator_new_legs.py` | **NEW** — ADX/SQZMOM vote, Volume multiplier. | 5 |
| `tests/test_price_rounding_invariant.py` (repo root `tests/`) | **NEW** — AST guard banning `round(x, 2)` over a bounded file list. | 6 |

---

## Task 1: Empty vote returns neutral HOLD, not phantom BUY (LIVE)

The single highest-value change in this plan. When every indicator fails, the handler currently returns `{"signal": "BUY", "confidence": 0.0}` — a directional label asserted on zero information, served live at `GET /api/v1/indicators/signal/{symbol}`.

Mechanism: with an empty `signals` list, all three entries of `signal_weights` are `0.0`. `max({"BUY": 0, "SELL": 0, "HOLD": 0}, key=...)` returns `"BUY"` — first-inserted key wins ties in CPython. `"BUY"` takes the directional branch, where `directional_weight == 0` selects the `else 0.0` arm. The `else 0.5` neutral fallback is only reachable when `final_signal == "HOLD"`, which argmax can never produce for an empty vote.

**Files:**
- Modify: `services/technical-analysis/app/handlers/analysis.py:112`
- Test: `services/technical-analysis/tests/test_signal_aggregator_confidence_zero.py` (already exists, already red)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: no signature change. `get_aggregated_signal(symbol, interval)` keeps returning a dict with keys `symbol, interval, signal, confidence, rsi, macd_signal, trend, timestamp`. Task 5 adds keys to this same dict.

- [ ] **Step 1: Run the existing failing test and read its failure**

The test already exists and already fails. Do not write a new one.

```bash
cd services/technical-analysis && python3 -m pytest tests/test_signal_aggregator_confidence_zero.py --no-cov -q
```

Expected: `2 passed, 1 failed`. The failure is:

```
FAILED tests/test_signal_aggregator_confidence_zero.py::test_empty_signal_list_returns_neutral_fallback
AssertionError: Expected neutral-fallback confidence=0.5; got 0.0
```

That test is the specification. Its assertions are:

```python
    # With total_weight == 0, confidence must fall back to 0.5.
    assert result["confidence"] == 0.5, (
        f"Expected neutral-fallback confidence=0.5; got {result['confidence']}"
    )

    assert result["signal"] in ("BUY", "SELL", "HOLD"), (
        f"Unexpected signal value: {result['signal']}"
    )
```

- [ ] **Step 2: Add a second assertion pinning the label, then re-run**

The existing test permits any label. The defect is *specifically* a phantom `BUY`, so pin it. Append to the end of `test_empty_signal_list_returns_neutral_fallback`:

```python
    # The defect was a phantom directional label on zero information:
    # argmax over an all-zero weight dict returns "BUY" (first-inserted key
    # wins ties in CPython), which then took the directional branch and its
    # `else 0.0` arm. No votes must mean HOLD.
    assert result["signal"] == "HOLD", (
        f"No usable votes must aggregate to HOLD, got {result['signal']!r} "
        "on zero information"
    )
```

Run again:

```bash
cd services/technical-analysis && python3 -m pytest tests/test_signal_aggregator_confidence_zero.py::test_empty_signal_list_returns_neutral_fallback --no-cov -q
```

Expected: still FAIL, now on the confidence assertion (0.0 != 0.5) which comes first.

- [ ] **Step 3: Make the minimal fix**

In `app/handlers/analysis.py`, replace line 112:

```python
        # Determine final signal
        final_signal = max(signal_weights, key=signal_weights.get)
```

with:

```python
        # Determine final signal. With no usable votes every weight is 0.0 and
        # argmax returns "BUY" (first-inserted key wins ties), which then took
        # the directional branch below and its `else 0.0` arm — a phantom
        # directional label at zero confidence. No votes means HOLD, which
        # reaches the `else 0.5` neutral fallback.
        final_signal = (
            max(signal_weights, key=signal_weights.get) if total_weight > 0 else "HOLD"
        )
```

This is the smaller of the two viable shapes: it needs no re-indentation of lines 114–130, and the existing `HOLD` branch already yields exactly `0.5` via its `else 0.5` arm.

- [ ] **Step 4: Verify the test passes and the suite baseline improved**

```bash
cd services/technical-analysis && python3 -m pytest tests/test_signal_aggregator_confidence_zero.py --no-cov -q
```

Expected: `3 passed`.

```bash
cd services/technical-analysis && python3 -m pytest tests/ --no-cov -q
```

Expected: **2 failed** (both `test_comprehensive_80`), down from 3. Record the new baseline — every later task in this plan is measured against 2, not 3.

- [ ] **Step 5: Commit**

```bash
git commit -- services/technical-analysis/app/handlers/analysis.py services/technical-analysis/tests/test_signal_aggregator_confidence_zero.py -m "fix(technical-analysis): no usable votes aggregates to HOLD, not phantom BUY

With an empty signals list every weight is 0.0 and argmax returns \"BUY\"
(first-inserted key wins ties in CPython), which took the directional
confidence branch and its else-0.0 arm. The 0.5 neutral fallback was only
reachable for HOLD, which argmax could never produce. The live endpoint
therefore answered {signal: BUY, confidence: 0.0} whenever every indicator
failed - a directional label asserted on zero information.

Turns test_empty_signal_list_returns_neutral_fallback green; the TA
known-failure baseline drops from 3 to 2."
```

---

## Task 2: Squeeze-momentum strategy stops rounding prices to 2dp (LIVE)

`analyze()` returns `entry_price`, `stop_loss`, and `take_profit` rounded to 2 decimals. For ADAUSDT (~$0.60, Bybit tick 0.0001) this collapses every level onto a 1-cent grid: a 2% stop at 0.588 becomes 0.59. The values are served at `GET /api/v1/strategies/sqzmom/signal/{symbol}` via `handlers/sqzmom.py`, which re-wraps them with `float(...)` — and `float()` cannot restore precision that rounding already destroyed.

**Files:**
- Modify: `services/technical-analysis/app/strategies/squeeze_momentum_strategy.py:203-205`, `:207`, `:171`
- Test: `services/technical-analysis/tests/unit/test_sqzmom_strategy_precision.py` (**NEW**)

**Interfaces:**
- Consumes: nothing.
- Produces: `SqueezeMomentumStrategy.analyze(df) -> Dict` — same keys, unchanged types (`float`), full precision. Task 6 adds this file to the AST guard's `SCANNED_FILES`.

- [ ] **Step 1: Write the failing test**

Create `services/technical-analysis/tests/unit/test_sqzmom_strategy_precision.py`:

```python
"""
Precision regression for the SQZMOM strategy's served price levels.

round(x, 2) on a sub-$1 asset is the 487d1bd defect class: ADA trades near
$0.60 with a 0.0001 tick, so two decimals quantize entry/stop/TP onto a
1-cent grid. A 2% stop lands 1.2 cents from entry, so rounding moves it by
up to 40% of the stop distance - and can put it on the wrong side of entry.

These assertions are two-sided: the served value must equal the computed
value exactly, and must NOT equal its 2dp rounding.
"""

import sys

sys.path.insert(
    0, str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent)
)

import numpy as np
import pandas as pd
import pytest

from app.strategies.squeeze_momentum_strategy import SqueezeMomentumStrategy


def _ada_ohlc(n: int = 80) -> pd.DataFrame:
    """ADA-scale OHLCV frame: prices near $0.60, ranges near $0.003."""
    rng = np.random.default_rng(7)
    close = 0.60 + np.cumsum(rng.normal(0, 0.0015, n))
    return pd.DataFrame(
        {
            "open": close + rng.normal(0, 0.0005, n),
            "high": close + np.abs(rng.normal(0.0015, 0.0005, n)),
            "low": close - np.abs(rng.normal(0.0015, 0.0005, n)),
            "close": close,
            "volume": rng.uniform(900, 1100, n),
        }
    )


def test_entry_price_keeps_full_precision():
    """entry_price is latest close; 2dp erases four significant digits on ADA."""
    df = _ada_ohlc()
    strategy = SqueezeMomentumStrategy()

    result = strategy.analyze(df)

    expected_entry = float(df["close"].iloc[-1])
    assert result["entry_price"] == pytest.approx(expected_entry, rel=1e-12), (
        f"entry_price {result['entry_price']} != close {expected_entry}; "
        "round(price, 2) destroyed ADA precision"
    )
    assert result["entry_price"] != round(expected_entry, 2), (
        "entry_price is still quantized to 2dp"
    )


def test_stop_and_target_keep_their_percentage_distance():
    """A 2% stop must stay 2% away, not snap to the nearest cent."""
    df = _ada_ohlc()
    strategy = SqueezeMomentumStrategy()

    result = strategy.analyze(df)
    if result["action"] == "HOLD":
        pytest.skip("no directional entry on this fixture; covered by the BUY case")

    entry = result["entry_price"]
    stop = result["stop_loss"]
    realized_stop_pct = abs(entry - stop) / entry * 100

    assert realized_stop_pct == pytest.approx(strategy.stop_loss_pct, rel=1e-9), (
        f"stop is {realized_stop_pct:.4f}% from entry, configured "
        f"{strategy.stop_loss_pct}% - rounding moved the stop"
    )


def test_momentum_keeps_precision_at_ada_scale():
    """ADA-scale sqz_momentum is ~1e-4; 4dp leaves it one significant digit."""
    df = _ada_ohlc()
    strategy = SqueezeMomentumStrategy()

    result = strategy.analyze(df)

    assert result["momentum"] != round(result["momentum"], 4) or result[
        "momentum"
    ] == 0.0, "momentum is still quantized to 4dp"
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd services/technical-analysis && python3 -m pytest tests/unit/test_sqzmom_strategy_precision.py --no-cov -q
```

Expected: FAIL on `test_entry_price_keeps_full_precision` with the served value equal to the 2dp rounding.

- [ ] **Step 3: Remove the price-domain rounding**

In `app/strategies/squeeze_momentum_strategy.py`, replace lines 200–211:

```python
            return {
                'action': action,
                'confidence': round(float(confidence), 2),
                'entry_price': round(entry_price, 2),
                'stop_loss': round(stop_loss, 2),
                'take_profit': round(take_profit, 2),
                'reason': reason,
                'momentum': round(float(momentum), 4),
                'squeeze_state': squeeze_state,
                'color': color,
                'timestamp': datetime.now().isoformat()
            }
```

with:

```python
            return {
                'action': action,
                # Price-domain fields carry full precision. round(x, 2) on ADA
                # (~$0.60, tick 0.0001) snaps entry/stop/TP onto a 1-cent grid
                # and moves a 2% stop by up to 40% of its own distance
                # (487d1bd / PRICE-01). Tick quantization is the trading
                # engine's job at order time, not this layer's.
                'confidence': round(float(confidence), 2),
                'entry_price': float(entry_price),
                'stop_loss': float(stop_loss),
                'take_profit': float(take_profit),
                'reason': reason,
                'momentum': float(momentum),
                'squeeze_state': squeeze_state,
                'color': color,
                'timestamp': datetime.now().isoformat()
            }
```

`confidence` stays rounded — it is dimensionless 0–1, not price-domain.

Then fix the volume-gate early return at line 171. Replace:

```python
                        'momentum': round(float(momentum), 4),
```

with:

```python
                        'momentum': float(momentum),
```

- [ ] **Step 4: Verify**

```bash
cd services/technical-analysis && python3 -m pytest tests/unit/test_sqzmom_strategy_precision.py tests/test_squeeze_momentum.py tests/test_sqzmom_api.py --no-cov -q
```

Expected: all pass. `tests/test_squeeze_momentum.py::test_analyze_method_structure` asserts only key presence, types, and `entry_price > 0` — it must stay green.

- [ ] **Step 5: Commit**

```bash
git commit -- services/technical-analysis/app/strategies/squeeze_momentum_strategy.py services/technical-analysis/tests/unit/test_sqzmom_strategy_precision.py -m "fix(technical-analysis): SQZMOM strategy serves full-precision price levels

entry_price, stop_loss and take_profit were rounded to 2dp before being
served at /api/v1/strategies/sqzmom/signal/{symbol}. On ADA (~\$0.60, tick
0.0001) that snaps every level onto a 1-cent grid: a 2% stop moves by up to
40% of its own distance and can land on the wrong side of entry. The
handler re-wraps with float(), which cannot restore destroyed precision.

Same defect class as 487d1bd. Dimensionless confidence stays rounded."
```

---

## Task 3: `SqueezeMetadata.to_dict` stops quantizing bands and price

`to_dict()` serializes Bollinger and Keltner band edges plus `current_price` at 4 decimals. 4dp equals ADA's tick exactly, so it is borderline-lossy for ADA today and outright lossy for any sub-cent listing.

**Reachability note — state this in the commit, do not overstate the severity.** `to_dict()` is consumed only by `get_signal()` → `analyze()` → the module-level `calculate_squeeze_momentum()` convenience function. The LIVE HTTP route `/api/v1/indicators/enhanced-sqzmom` calls `calculator.calculate(df)` and never touches `to_dict`. This is library-contract rot in the same family, not a live-signal bug.

**Files:**
- Modify: `services/technical-analysis/app/indicators/sqzmom_enhanced.py:118-124`
- Test: `services/technical-analysis/tests/unit/test_sqzmom_strategy_precision.py` (extend the file created in Task 2)

**Interfaces:**
- Consumes: the `_ada_ohlc` helper from Task 2's test file.
- Produces: `SqueezeMetadata.to_dict() -> Dict[str, Any]` — same keys, price-domain values now full-precision floats.

- [ ] **Step 1: Write the failing test**

Append to `services/technical-analysis/tests/unit/test_sqzmom_strategy_precision.py`:

```python
def test_metadata_bands_keep_full_precision():
    """to_dict serialized bands at 4dp - exactly ADA's tick, lossy below it."""
    from app.indicators import calculate_squeeze_momentum

    df = _ada_ohlc(120)
    result = calculate_squeeze_momentum(df)

    metadata = result["metadata"]
    for field in ("bb_upper", "bb_basis", "bb_lower", "kc_upper", "kc_basis",
                  "kc_lower", "current_price"):
        value = metadata[field]
        assert value == pytest.approx(value, rel=1e-12)
        assert value != round(value, 4) or value == 0.0, (
            f"{field}={value} is still quantized to 4dp"
        )
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd services/technical-analysis && python3 -m pytest tests/unit/test_sqzmom_strategy_precision.py::test_metadata_bands_keep_full_precision --no-cov -q
```

Expected: FAIL — every band equals its own 4dp rounding.

- [ ] **Step 3: Drop the rounding on price-domain fields only**

In `app/indicators/sqzmom_enhanced.py`, replace lines 118–124:

```python
            "bb_upper": round(self.bb_upper, 4),
            "bb_basis": round(self.bb_basis, 4),
            "bb_lower": round(self.bb_lower, 4),
            "kc_upper": round(self.kc_upper, 4),
            "kc_basis": round(self.kc_basis, 4),
            "kc_lower": round(self.kc_lower, 4),
            "current_price": round(self.current_price, 4),
```

with:

```python
            # Price-domain: 4dp is exactly ADA's tick and lossy below it.
            # Full precision here; quantization belongs at order time.
            "bb_upper": float(self.bb_upper),
            "bb_basis": float(self.bb_basis),
            "bb_lower": float(self.bb_lower),
            "kc_upper": float(self.kc_upper),
            "kc_basis": float(self.kc_basis),
            "kc_lower": float(self.kc_lower),
            "current_price": float(self.current_price),
```

Leave `momentum_strength` (line 115, normalized 0–1) and `band_width_ratio` (line 125, a ratio) rounded — both are dimensionless.

- [ ] **Step 4: Verify**

```bash
cd services/technical-analysis && python3 -m pytest tests/unit/test_sqzmom_strategy_precision.py tests/test_enhanced_sqzmom_service.py --no-cov -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git commit -- services/technical-analysis/app/indicators/sqzmom_enhanced.py services/technical-analysis/tests/unit/test_sqzmom_strategy_precision.py -m "fix(technical-analysis): SqueezeMetadata.to_dict keeps band precision

Bands and current_price were serialized at 4dp, which is exactly ADA's tick
size and lossy for anything below it. Same PRICE-01 family as the strategy
fix. Dimensionless momentum_strength and band_width_ratio stay rounded.

Scope note: to_dict is not on the live /api/v1/indicators/enhanced-sqzmom
route (that path calls calculate()); this is library-contract rot, not a
live-signal defect."
```

---

## Task 4: Endpoint parameter defaults read Settings instead of duplicating them (LIVE)

`app/main.py` hardcodes MACD 5/35/5, BB period 20 / std-dev 2.5, and RSI period 9 as `Query(default=…)` literals. The Settings fields already exist and already hold those exact values — but the routed endpoints never read them.

Why this matters concretely: the trading-engine deliberately omits MACD parameters when calling this service, treating the endpoint defaults as the single source of truth (`signal_aggregator.py:117-122`, comment: *"No fast/slow/signal here on purpose — use TA service defaults (Kang 2021: 5-35-5) instead of drifting local overrides"*). So an operator who sets `DEFAULT_MACD_FAST` in the environment today changes the `/analyze` aggregation path (which does read Settings) but **not** the `/indicators/macd` endpoint the engine actually calls. Silent split-brain.

**The Settings field names are `default_macd_fast`, `default_macd_slow`, `default_macd_signal`, `default_bb_period`, `default_bb_std`, `default_rsi_period`** — not `macd_fast` or `bollinger_std_dev`. Do not rename them; `handlers/analysis.py` depends on the current names.

**Files:**
- Modify: `services/technical-analysis/app/main.py:271` (RSI), `:291-293` (MACD), `:312`, `:314` (Bollinger)
- Test: `services/technical-analysis/tests/test_endpoint_defaults_from_settings.py` (**NEW**)

**Interfaces:**
- Consumes: nothing.
- Produces: no signature change; the OpenAPI schema's default values now track Settings.

- [ ] **Step 1: Write the failing test**

`Query` defaults are evaluated at import time, so assert at the route level with `TestClient` and a mocked service, checking what the handler actually received.

Create `services/technical-analysis/tests/test_endpoint_defaults_from_settings.py`:

```python
"""
Route defaults must come from Settings, not from duplicated literals.

The trading-engine calls /api/v1/indicators/macd with NO fast/slow/signal
params on purpose, treating this service's endpoint defaults as the single
source of truth (signal_aggregator.py:117-122). While main.py hardcodes
5/35/5, an operator's DEFAULT_MACD_FAST reaches the /analyze path but not the
endpoint the engine calls - the two disagree silently.
"""

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app, raise_server_exceptions=False)
settings = get_settings()


def test_macd_route_defaults_come_from_settings():
    payload = {
        "timestamp": 1234567890000,
        "macd_line": 1.0,
        "signal_line": 0.5,
        "histogram": 0.5,
        "signal": "BUY",
        "confidence": 0.7,
    }
    with patch("app.handlers.indicators.IndicatorService") as mock_service:
        mock_service.calculate_macd = AsyncMock(return_value=payload)

        response = client.get("/api/v1/indicators/macd/BTCUSDT")

        assert response.status_code == 200, response.text
        kwargs = mock_service.calculate_macd.call_args.kwargs
        args = mock_service.calculate_macd.call_args.args
        received = kwargs if kwargs else dict(
            zip(("symbol", "interval", "fast", "slow", "signal", "limit"), args)
        )
        assert received["fast"] == settings.default_macd_fast
        assert received["slow"] == settings.default_macd_slow
        assert received["signal"] == settings.default_macd_signal


def test_bollinger_route_defaults_come_from_settings():
    payload = {
        "timestamp": 1234567890000,
        "upper_band": 2.0,
        "middle_band": 1.0,
        "lower_band": 0.5,
        "current_price": 1.0,
        "bandwidth": 1.5,
        "percent_b": 0.5,
        "signal": "HOLD",
        "confidence": 0.5,
    }
    with patch("app.handlers.indicators.IndicatorService") as mock_service:
        mock_service.calculate_bollinger_bands = AsyncMock(return_value=payload)

        response = client.get("/api/v1/indicators/bollinger/BTCUSDT")

        assert response.status_code == 200, response.text
        kwargs = mock_service.calculate_bollinger_bands.call_args.kwargs
        args = mock_service.calculate_bollinger_bands.call_args.args
        received = kwargs if kwargs else dict(
            zip(("symbol", "interval", "period", "std_dev", "limit"), args)
        )
        assert received["period"] == settings.default_bb_period
        assert received["std_dev"] == settings.default_bb_std


def test_openapi_schema_defaults_track_settings():
    """The literal is gone from the schema, not merely shadowed at runtime."""
    schema = client.get("/openapi.json").json()
    macd_params = {
        p["name"]: p
        for p in schema["paths"]["/api/v1/indicators/macd/{symbol}"]["get"]["parameters"]
    }
    assert macd_params["fast"]["schema"]["default"] == settings.default_macd_fast
    assert macd_params["slow"]["schema"]["default"] == settings.default_macd_slow
```

Note: `test_openapi_schema_defaults_track_settings` passes both before and after the change, because the literals currently equal the Settings values. It is a **drift guard** — it goes red the day someone changes a Settings default without touching `main.py`. Keep it.

- [ ] **Step 2: Run it and watch the first two fail**

```bash
cd services/technical-analysis && python3 -m pytest tests/test_endpoint_defaults_from_settings.py --no-cov -q
```

Expected: the two `*_route_defaults_come_from_settings` tests may PASS on current code, because the hardcoded literals coincidentally equal the Settings values. **This is expected and is why the change is a drift fix, not a value fix.** To prove the tests have teeth, temporarily change `default_macd_fast` in `app/config.py` to `6`, re-run, and confirm `test_macd_route_defaults_come_from_settings` now FAILS. Then revert `config.py` to `5` before proceeding.

- [ ] **Step 3: Wire the Query defaults to Settings**

`settings` is already a module-level instance at `app/main.py:75`, so these references are import-safe.

Line 271 (RSI endpoint):

```python
    period: int = Query(default=settings.default_rsi_period, ge=2, le=100),
```

Lines 291–293 (MACD endpoint):

```python
    fast: int = Query(default=settings.default_macd_fast, ge=2, le=50, description="Fast EMA period (research: 5)"),
    slow: int = Query(default=settings.default_macd_slow, ge=10, le=200, description="Slow EMA period (research: 35)"),
    signal: int = Query(default=settings.default_macd_signal, ge=2, le=50, description="Signal line period (research: 5)"),
```

Lines 312 and 314 (Bollinger endpoint):

```python
    period: int = Query(default=settings.default_bb_period, ge=5, le=100),
    # RESEARCH-OPTIMIZED: 2.5 SD better for crypto volatility (reduces false breakouts)
    std_dev: float = Query(default=settings.default_bb_std, ge=1.0, le=4.0, description="Std dev (research: 2.5)"),
```

Keep the existing `ge`/`le` bounds and descriptions exactly as they are — only the `default=` expression changes. Preserve the RSI endpoint's existing bounds; read them from the file rather than assuming, and change only the `default=`.

- [ ] **Step 4: Verify, including the teeth check**

```bash
cd services/technical-analysis && python3 -m pytest tests/test_endpoint_defaults_from_settings.py tests/test_indicator_handlers.py tests/test_config.py --no-cov -q
```

Expected: all pass. Repeat the temporary-edit teeth check from Step 2 once more and confirm the route test now fails *for the right reason* (the route default moved with Settings). Revert.

- [ ] **Step 5: Commit**

```bash
git commit -- services/technical-analysis/app/main.py services/technical-analysis/tests/test_endpoint_defaults_from_settings.py -m "fix(technical-analysis): route defaults read Settings instead of duplicating them

MACD 5/35/5, BB 20/2.5 and RSI 9 were hardcoded as Query(default=...)
literals while identical Settings fields sat unread. The trading-engine
deliberately omits MACD params so this service's endpoint defaults are its
single source of truth, so an operator's DEFAULT_MACD_FAST reached the
/analyze path but not /indicators/macd - a silent split-brain.

Query defaults evaluate at import time: env overrides need a service
restart, and the OpenAPI schema defaults now track Settings."
```

---

## Task 5: ADX and SQZMOM enter the vote; Volume becomes a confidence multiplier (LIVE)

`get_aggregated_signal` votes exactly three legs: RSI, MACD, TrendFilter. ADX, Enhanced SQZMOM, and Volume Confirmation are fully implemented in this same service, orchestrated by `IndicatorService`, and exposed as REST endpoints — and none of them is consulted by the aggregate.

**Volume must NOT become a voting leg.** Its labels are `CONFIRM`/`REJECT`, and appending either raw would `KeyError` at `signal_weights[sig] += weight` and surface as an HTTP 500 through the generic `except` at line 145. It is also directionally agnostic — high volume confirms a breakdown exactly as much as a breakout. The trading-engine already models this correctly: volume is excluded from its vote and applied as a post-vote confidence multiplier in `aggregation/validator.py`. Mirror that design here.

**Files:**
- Modify: `services/technical-analysis/app/handlers/analysis.py:12` (imports), after `:44` (computation), after `:88` (vote legs), after `:130` (volume multiplier), `:132-141` (response)
- Test: `services/technical-analysis/tests/test_aggregator_new_legs.py` (**NEW**)

**Interfaces:**
- Consumes: Task 1's `final_signal` short-circuit (this task inserts legs *before* the weighted sum, so the empty-vote path still reaches HOLD).
- Produces: the response dict gains three additive keys — `adx`, `sqzmom`, `volume`. Existing keys are unchanged; nothing may be renamed.
- Calculator APIs (verified):
  - `ADXCalculator().calculate_with_signal(highs: List[float], lows: List[float], closes: List[float]) -> Tuple[Dict, str, float]` — the `str` is already `"BUY"`/`"SELL"`/`"HOLD"`.
  - `EnhancedSqueezeMomentum().calculate(df: pd.DataFrame) -> Optional[pd.DataFrame]` — last row carries `sqz_signal` (BUY/SELL/HOLD) and `sqz_confidence` (0–1).
  - `VolumeConfirmation().calculate(volumes: List[float], signal_type: str = "breakout") -> Dict` — keys include `confirmed` (bool), `strength` (`STRONG`/`MODERATE`/`WEAK`/`INSUFFICIENT`), `volume_ratio`, `confidence`.

- [ ] **Step 1: Write the failing test**

The mock trap here is real: existing tests build a 10-row DataFrame, which is below ADX's 29-bar and SQZMOM's 32-bar minimums. Unpatched real calculators would return their 0.0-confidence failure defaults, get dropped by the `weight > 0.0` filter, and the test would pass **vacuously**. Patch the calculators at the handler's module namespace.

Create `services/technical-analysis/tests/test_aggregator_new_legs.py`:

```python
"""
ADX and Enhanced SQZMOM must vote; Volume must NOT vote.

All three are computed in this service and exposed as endpoints, but
get_aggregated_signal consulted only RSI, MACD and TrendFilter.

Volume is deliberately not a voter: its labels are CONFIRM/REJECT, which
would KeyError signal_weights[sig] into an HTTP 500, and it is directionally
agnostic - high volume confirms a breakdown as much as a breakout. The
trading-engine models it as a post-vote confidence multiplier
(aggregation/validator.py); this mirrors that.

Patching note: these tests MUST patch the calculators in the
app.handlers.analysis namespace. The fixture frame is 10 rows, below ADX's
29-bar and SQZMOM's 32-bar minimums, so unpatched calculators return their
0.0-confidence defaults, get dropped by the weight > 0.0 filter, and the
test would pass vacuously.
"""

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest


def _make_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100.0] * 10,
            "high": [101.0] * 10,
            "low": [99.0] * 10,
            "close": [100.0] * 10,
            "volume": [1000.0] * 10,
        },
        index=pd.DatetimeIndex([datetime(2026, 1, 1, i) for i in range(10)]),
    )


def _signal_enum(value: str):
    m = MagicMock()
    m.value = value
    return m


def _sqz_frame(signal: str, confidence: float) -> pd.DataFrame:
    return pd.DataFrame(
        {"sqz_signal": [signal], "sqz_confidence": [confidence]}
    )


def _patched(adx=("BUY", 0.8), sqz=("BUY", 0.9), volume_confirmed=True,
             volume_strength="STRONG"):
    """Patch every leg so only the ones under test carry weight."""
    fetcher = AsyncMock()
    fetcher.get_klines_as_dataframe = AsyncMock(return_value=_make_df())

    rsi_inst = MagicMock()
    rsi_inst.calculate.return_value = None
    macd_inst = MagicMock()
    macd_inst.calculate.return_value = None
    trend_inst = MagicMock()
    trend_inst.calculate.return_value = None

    adx_inst = MagicMock()
    adx_inst.calculate_with_signal.return_value = ({"adx": 30.0}, adx[0], adx[1])
    sqz_inst = MagicMock()
    sqz_inst.calculate.return_value = _sqz_frame(sqz[0], sqz[1])
    vol_inst = MagicMock()
    vol_inst.calculate.return_value = {
        "confirmed": volume_confirmed,
        "strength": volume_strength,
        "volume_ratio": 1.6,
        "confidence": 1.0,
    }

    return patch.multiple(
        "app.handlers.analysis",
        get_fetcher=MagicMock(return_value=fetcher),
        RSICalculator=MagicMock(return_value=rsi_inst),
        MACDCalculator=MagicMock(return_value=macd_inst),
        TrendFilter=MagicMock(return_value=trend_inst),
        ADXCalculator=MagicMock(return_value=adx_inst),
        EnhancedSqueezeMomentum=MagicMock(return_value=sqz_inst),
        VolumeConfirmation=MagicMock(return_value=vol_inst),
    )


@pytest.mark.asyncio
async def test_adx_alone_can_carry_the_signal():
    """With RSI/MACD/trend dead, an ADX BUY must still produce BUY."""
    from app.handlers.analysis import get_aggregated_signal

    with _patched(adx=("BUY", 0.8), sqz=("HOLD", 0.0)):
        result = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    assert result["signal"] == "BUY", (
        f"ADX did not reach the vote; got {result['signal']!r}"
    )
    assert result["adx"]["signal"] == "BUY"


@pytest.mark.asyncio
async def test_sqzmom_alone_can_carry_the_signal():
    from app.handlers.analysis import get_aggregated_signal

    with _patched(adx=("HOLD", 0.0), sqz=("SELL", 0.9)):
        result = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    assert result["signal"] == "SELL", (
        f"SQZMOM did not reach the vote; got {result['signal']!r}"
    )
    assert result["sqzmom"]["signal"] == "SELL"


@pytest.mark.asyncio
async def test_unconfirmed_volume_penalizes_but_does_not_vote():
    """Volume must move confidence, never the label - and never KeyError."""
    from app.handlers.analysis import get_aggregated_signal

    with _patched(adx=("BUY", 0.8), sqz=("BUY", 0.9), volume_confirmed=True,
                  volume_strength="STRONG"):
        confirmed = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    with _patched(adx=("BUY", 0.8), sqz=("BUY", 0.9), volume_confirmed=False,
                  volume_strength="WEAK"):
        unconfirmed = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    assert confirmed["signal"] == unconfirmed["signal"] == "BUY", (
        "volume changed the direction - it must only scale confidence"
    )
    assert unconfirmed["confidence"] < confirmed["confidence"], (
        f"unconfirmed volume did not penalize confidence: "
        f"{unconfirmed['confidence']} vs {confirmed['confidence']}"
    )
    assert unconfirmed["volume"]["confirmed"] is False


@pytest.mark.asyncio
async def test_empty_vote_still_holds_with_the_new_legs_present():
    """Task 1's neutral fallback must survive the added legs."""
    from app.handlers.analysis import get_aggregated_signal

    with _patched(adx=("HOLD", 0.0), sqz=("HOLD", 0.0)):
        result = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    assert result["signal"] == "HOLD"
    assert result["confidence"] == 0.5
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd services/technical-analysis && python3 -m pytest tests/test_aggregator_new_legs.py --no-cov -q
```

Expected: FAIL at `patch.multiple` with `AttributeError: <module 'app.handlers.analysis'> does not have the attribute 'ADXCalculator'` — the imports do not exist yet. That is the correct first failure.

- [ ] **Step 3: Add the imports**

In `app/handlers/analysis.py`, replace lines 12–13:

```python
from app.indicators import RSICalculator, MACDCalculator
from app.indicators.trend_filter import TrendFilter
```

with:

```python
from app.indicators import (
    RSICalculator,
    MACDCalculator,
    ADXCalculator,
    EnhancedSqueezeMomentum,
)
from app.indicators.trend_filter import TrendFilter
from app.indicators.volume_confirmation import VolumeConfirmation
```

`ADXCalculator` and `EnhancedSqueezeMomentum` are exported from `app/indicators/__init__.py`; `VolumeConfirmation` is not, so it is imported from its module — the same way `indicator_service.py` imports it. **Module-level imports are required** so the tests can patch them in this namespace.

- [ ] **Step 4: Compute the new legs**

After line 44 (`trend_result = trend_filter.calculate(df["close"].tolist())`), add:

```python
        # ADX (trend strength + direction) and Enhanced SQZMOM (breakout) are
        # computed in this service and served as endpoints, but were never
        # consulted here. Both already emit BUY/SELL/HOLD with their own
        # confidence, so they drop straight into the (label, confidence) shape.
        adx_data, adx_signal, adx_conf = ADXCalculator().calculate_with_signal(
            df["high"].tolist(), df["low"].tolist(), df["close"].tolist()
        )
        sqz_df = EnhancedSqueezeMomentum().calculate(df)
        # Volume is NOT a voter: its labels are CONFIRM/REJECT (which would
        # KeyError the weight dict) and it is directionally agnostic. It scales
        # confidence after the vote, mirroring the trading-engine's validator.
        volume_result = VolumeConfirmation().calculate(
            df["volume"].tolist(), "breakout"
        )
```

- [ ] **Step 5: Add the voting legs**

After line 88 (the closing `)` of the trend `signals.append(...)` block) and **before** the zero-confidence filter, add:

```python
        # ADX: HOLD below the weak-trend threshold, so noise self-filters via
        # the confidence gate below.
        if adx_signal:
            signals.append((str(adx_signal), float(adx_conf)))

        # Enhanced SQZMOM: last row carries the signal and its confidence.
        if sqz_df is not None and not sqz_df.empty:
            last_row = sqz_df.iloc[-1]
            signals.append(
                (str(last_row["sqz_signal"]), float(last_row["sqz_confidence"]))
            )
```

The existing `weight > 0.0` filter at line 95 automatically discards each calculator's 0.0-confidence failure default, so no extra guards are needed.

- [ ] **Step 6: Apply the volume multiplier and extend the response**

After the confidence computation (after line 130's closing `)`) and before the `return`, add:

```python
        # Volume validation: scale a directional signal's confidence by how
        # well volume confirms it. Tiers mirror the trading-engine's
        # aggregation/validator.py so the two services agree.
        volume_penalty = 1.0
        if final_signal in ("BUY", "SELL"):
            strength = str(volume_result.get("strength", "UNKNOWN"))
            if volume_result.get("confirmed"):
                volume_penalty = 1.0 if strength == "STRONG" else 0.9
            elif strength == "MODERATE":
                volume_penalty = 0.8
            elif strength == "WEAK":
                volume_penalty = 0.75
            else:
                volume_penalty = 0.5
            confidence *= volume_penalty
```

Then extend the response dict (lines 132–141) with three additive keys — do not rename or remove any existing key:

```python
        return {
            "symbol": symbol,
            "interval": interval,
            "signal": final_signal,
            "confidence": round(confidence, 3),
            "rsi": round(rsi_value, 2) if rsi_value else None,
            "macd_signal": macd_signal_label,
            "trend": trend,
            "adx": {
                "signal": str(adx_signal),
                "confidence": round(float(adx_conf), 3),
                "adx": adx_data.get("adx") if adx_data else None,
            },
            "sqzmom": (
                {
                    "signal": str(sqz_df.iloc[-1]["sqz_signal"]),
                    "confidence": round(float(sqz_df.iloc[-1]["sqz_confidence"]), 3),
                }
                if sqz_df is not None and not sqz_df.empty
                else None
            ),
            "volume": {
                "confirmed": bool(volume_result.get("confirmed", False)),
                "strength": volume_result.get("strength"),
                "ratio": volume_result.get("volume_ratio"),
                "penalty": round(volume_penalty, 3),
            },
            "timestamp": int(df.index[-1].timestamp() * 1000),
        }
```

- [ ] **Step 7: Verify, and confirm the tests are not vacuous**

```bash
cd services/technical-analysis && python3 -m pytest tests/test_aggregator_new_legs.py tests/test_signal_aggregator_confidence_zero.py tests/test_analysis_handlers.py tests/test_analysis_edge_cases.py --no-cov -q
```

Expected: all pass, including Task 1's three tests.

Non-vacuity check — comment out the two `signals.append` blocks you just added and re-run. `test_adx_alone_can_carry_the_signal` and `test_sqzmom_alone_can_carry_the_signal` must both FAIL. Restore.

Then the full suite:

```bash
cd services/technical-analysis && python3 -m pytest tests/ --no-cov -q
```

Expected: **2 failed** (the two `test_comprehensive_80`), matching the post-Task-1 baseline.

- [ ] **Step 8: Commit**

```bash
git commit -- services/technical-analysis/app/handlers/analysis.py services/technical-analysis/tests/test_aggregator_new_legs.py -m "feat(technical-analysis): ADX and SQZMOM vote; volume scales confidence

ADX, Enhanced SQZMOM and Volume Confirmation are computed in this service
and served as endpoints, but get_aggregated_signal consulted only RSI, MACD
and TrendFilter.

ADX and SQZMOM already emit BUY/SELL/HOLD with their own confidence, so they
drop into the existing (label, confidence) shape and the zero-confidence
filter discards their failure defaults automatically.

Volume deliberately does NOT vote: its labels are CONFIRM/REJECT, which
would KeyError the weight dict into an HTTP 500, and it is directionally
agnostic. It scales post-vote confidence with the same tiers the
trading-engine's validator uses, so the two services agree.

Response gains adx/sqzmom/volume keys; no existing key changed."
```

---

## Task 6: AST guard banning `round(x, 2)` over the files this plan fixed

Lock the class shut. Model the guard on `tests/test_account_size_invariant.py`, the `$100` invariant added by quick task `260803-4mt`.

**Critical scoping rule:** `SCANNED_FILES` may list only files already fixed. There are roughly 17 further `round(..., 2)` sites in `app/indicators/*.py` that this plan does not touch — including them would make the guard permanently red. Plan B has an explicit step to append the trading-engine files it fixes.

**Files:**
- Create: `tests/test_price_rounding_invariant.py` (repo root `tests/`, **not** the service's tests directory)

**Interfaces:**
- Consumes: the files fixed in Tasks 2 and 3.
- Produces: `find_violations(source: str, filename: str) -> list[str]` and the module constant `SCANNED_FILES: tuple[str, ...]`. **Plan B appends to `SCANNED_FILES`** — keep it a module-level tuple of repo-relative path strings.

- [ ] **Step 1: Write the guard with its own fixtures**

Create `tests/test_price_rounding_invariant.py`:

```python
"""
THE PRICE-PRECISION INVARIANT.

round(price, 2) destroyed ADA precision and caused 30+ flip-flop losses
(commit 487d1bd; tracked as PRICE-01/02). Crypto prices span nine orders of
magnitude and every symbol has its own tick size; two decimals is correct for
none of them. The established fix is full precision - float(x) - with tick
quantization left to the trading-engine at order time (app/costs.py
quantize_price, limit_order_executor._round_to_tick).

Scope is a BOUNDED file tuple, deliberately: roughly 17 further sites live in
services/technical-analysis/app/indicators/*.py and are not yet fixed.
Adding a file here is a commitment that it is clean NOW. Grow the tuple as
files are fixed - never add a file you have not just cleaned, or this guard
lands red and gets disabled instead of obeyed.

Dimensionless quantities (RSI 0-100, confidence 0-1, volume ratios, position
fractions, strength scores) are legitimately rounded and must not trip this.
That is why scope is per-file rather than per-name: the fixed files contain
no dimensionless round(_, 2) calls.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Files cleaned of price-domain rounding. Append only alongside a fix.
SCANNED_FILES: tuple[str, ...] = (
    "services/technical-analysis/app/strategies/squeeze_momentum_strategy.py",
    "services/technical-analysis/app/indicators/sqzmom_enhanced.py",
)

# Not yet covered, tracked deliberately:
#   services/technical-analysis/app/indicators/*.py  (~17 sites, PRICE-02)
#   services/technical-analysis/app/handlers/sqzmom.py (4dp momentum)
#   trading-engine strategy + detector files          (added by WS1-B)

BANNED_NDIGITS = frozenset({2, 4})


def _ndigits_of(node: ast.Call) -> int | None:
    """The ndigits argument of a round() call, whatever shape it takes.

    Handles builtin `round(x, 2)` (ndigits is args[1]), the method form
    `series.round(2)` / `np.round(x, 2)` (ndigits is args[1] for np.round but
    args[0] for the bound-method form), and `round(x, ndigits=2)`.
    """
    for keyword in node.keywords:
        if keyword.arg == "ndigits":
            return _int_constant(keyword.value)

    func = node.func
    if isinstance(func, ast.Name) and func.id == "round":
        return _int_constant(node.args[1]) if len(node.args) == 2 else None
    if isinstance(func, ast.Attribute) and func.attr == "round":
        if len(node.args) == 2:  # np.round(x, 2)
            return _int_constant(node.args[1])
        if len(node.args) == 1:  # series.round(2)
            return _int_constant(node.args[0])
    return None


def _int_constant(node: ast.AST | None) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        if isinstance(node.value, bool):
            return None
        return node.value
    return None


def _is_round_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "round"
    if isinstance(func, ast.Attribute):
        return func.attr == "round"
    return False


def find_violations(source: str, filename: str = "<fixture>") -> list[str]:
    """One human-readable violation string per banned rounding call."""
    tree = ast.parse(source, filename=filename)
    violations: list[str] = []

    for node in ast.walk(tree):
        if not _is_round_call(node):
            continue
        ndigits = _ndigits_of(node)
        if ndigits in BANNED_NDIGITS:
            violations.append(
                f"{filename}:{node.lineno}: round(..., {ndigits}) in a file "
                "declared free of price-domain rounding. Crypto prices need "
                "full precision here (float(x)); quantize at order time."
            )

    return sorted(set(violations))


NEGATIVE_FIXTURE = '''
value = round(pct_change, 3)
ratio = round(current_volume / avg_volume, 1)
scaled = round(fraction, 6)
dynamic = round(price, tick_decimals)
bare = round(x)
'''

POSITIVE_FIXTURE = '''
entry = round(entry_price, 2)
stop = round(sl, ndigits=2)
band = np.round(bb_upper, 4)
col = series.round(2)
'''


def test_negative_cases_do_not_trip():
    """Zero false positives on legitimate rounding. Parsed in-memory so the
    guarantee cannot drift when live repo files change."""
    violations = find_violations(NEGATIVE_FIXTURE, "negative_fixture.py")
    assert violations == [], "false positives:\n" + "\n".join(violations)


def test_positive_cases_do_trip():
    """All four call shapes are detected."""
    violations = find_violations(POSITIVE_FIXTURE, "positive_fixture.py")
    rendered = "\n".join(violations)
    assert len(violations) == 4, (
        f"expected 4 violations, got {len(violations)}:\n{rendered}"
    )
    for expected in ("round(..., 2)", "round(..., 4)"):
        assert expected in rendered, f"missing {expected} in:\n{rendered}"


@pytest.mark.parametrize("relative_path", SCANNED_FILES)
def test_scanned_file_exists(relative_path: str):
    """A rename must not silently shrink this guard's coverage."""
    assert (REPO_ROOT / relative_path).is_file(), (
        f"{relative_path} is in SCANNED_FILES but does not exist. Update the "
        "tuple deliberately - do not let a rename quietly reduce coverage."
    )


def test_no_price_rounding_in_scanned_files():
    """THE INVARIANT."""
    violations: list[str] = []
    for relative_path in SCANNED_FILES:
        path = REPO_ROOT / relative_path
        if not path.is_file():
            continue
        violations.extend(
            find_violations(path.read_text(encoding="utf-8"), relative_path)
        )

    assert not violations, (
        f"{len(violations)} banned rounding call(s) in files declared clean. "
        "round(price, 2) destroyed ADA precision (487d1bd). Use float(x) here "
        "and quantize at order time:\n" + "\n".join(violations)
    )
```

- [ ] **Step 2: Prove the guard has teeth before trusting it green**

```bash
python3 -m pytest tests/test_price_rounding_invariant.py --no-cov -q
```

Expected: all pass (Tasks 2 and 3 already cleaned both files).

A green guard proves nothing unless you have seen it go red. Temporarily reintroduce one rounding — change `'entry_price': float(entry_price),` back to `'entry_price': round(entry_price, 2),` in `squeeze_momentum_strategy.py` — and re-run. `test_no_price_rounding_in_scanned_files` must FAIL naming that exact file and line. Restore the fix and confirm green again.

- [ ] **Step 3: Commit**

```bash
git commit -- tests/test_price_rounding_invariant.py -m "test(price): AST guard banning round(x, 2|4) in cleaned files

round(price, 2) destroyed ADA precision and caused 30+ flip-flop losses
(487d1bd, PRICE-01/02). This guard makes reintroduction fail loudly.

Modeled on tests/test_account_size_invariant.py: a pure find_violations()
over in-memory fixtures, a bounded SCANNED_FILES tuple, and a parametrized
existence check so a rename cannot silently shrink coverage.

Scope is bounded on purpose - ~17 further sites in app/indicators/*.py are
not yet fixed, and a permanently-red guard gets disabled rather than obeyed.
WS1-B appends the trading-engine files it cleans.

Detects all four call shapes: round(x, 2), round(x, ndigits=2),
np.round(x, 4), series.round(2)."
```

---

## Plan A completion checklist

- [ ] TA suite baseline is **2 failed** (both `test_comprehensive_80`), down from 3.
- [ ] `python3 -m pytest tests/test_price_rounding_invariant.py --no-cov -q` passes from the repo root, and has been *seen* to fail when a rounding is reintroduced.
- [ ] Six commits, one per task, each with an explicit pathspec.
- [ ] `git diff` on every commit checked for ruff/autoflake import churn.
- [ ] **Deployment proof before claiming anything works:** rebuild and restart the service, then verify against the live route — an HTTP 200 alone is not proof.
  ```bash
  DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml up -d --build technical-analysis
  curl -sf http://localhost:8004/health
  curl -s "http://localhost:8004/api/v1/indicators/signal/ADAUSDT" | python3 -m json.tool
  ```
  The response must now carry `adx`, `sqzmom`, and `volume` keys. Confirm the service was actually restarted — stale in-memory state is this repo's most common false pass.

## Out of scope, recorded so nobody re-derives it

- `services/technical-analysis/app/main.py.bak` is a dead pre-refactor file (977 lines, superseded, unimported). It is **untracked and gitignored** (`*.bak`), so deleting it has no git recovery path. Not a task here — surface it to the operator separately rather than folding an unrecoverable filesystem delete into a correctness commit. `services/market-data-service/app/` carries the same rot (`main.py.bak`, `main_original.py`).
- The per-timeframe mini-vote inside `get_multi_timeframe_analysis` (`analysis.py:222-241`) is a third, separate, unweighted voter that also lacks ADX/SQZMOM/Volume. Fixing `get_aggregated_signal` alone leaves it inconsistent. Deliberately deferred — it feeds the dormant engine MTF leg that WS1-B repairs.
- `handlers/sqzmom.py` carries further 4dp momentum rounding (`:109`, `:364-370`), and `indicator_service.py:58` rounds RSI to 2dp (harmless — RSI is dimensionless).
- TA Settings has no ADX/SQZMOM/Volume parameter fields; Task 5 uses each calculator's constructor defaults (ADX 14/20/25/30; SQZMOM 20/2.0/20/1.5/12; Volume 20/1.2/1.5).
