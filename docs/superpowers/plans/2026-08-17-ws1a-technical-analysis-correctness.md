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
- **Never round a price-domain value.** `round(x, 2)` on ADA (~$0.60, tick 0.0001) destroys precision and caused 30+ flip-flop losses (commit `487d1bd`). The established fix in this repo is `float(x)` — full precision — NOT tick quantization. Tick quantization belongs at order time in the trading-engine (`app/costs.py`, `limit_order_executor`), never in indicator or strategy math. Dimensionless values (RSI 0–100, confidence 0–1, volume ratios, normalized strength scores) may stay rounded.
- **The dimensionless opt-out marker is `# non-price-round`.** Task 6 builds an AST guard that bans `round(x, 2)` and `round(x, 4)` anywhere inside a bounded file list, and honours a trailing `# non-price-round` comment as a line-level exemption. Every dimensionless rounding that survives in a guarded file must carry that exact marker. Tasks 2 and 3 write the markers as part of their own edits; Task 6 writes the guard that reads them. Do not invent a second spelling — WS1-B extends the same marker.
- **The format hook runs ruff at 88 columns while the repo uses 100, and has stripped imports before.** Make surgical single-line edits. After any edit touching an import block, run `git diff` and check for import churn before committing.
- **`git status` exceeds 60 seconds on this NTFS/WSL mount.** Never run bare `git status` or `git add -A`. Commit with explicit pathspecs: `git commit -- <path> <path>`.
- **Commit one task per commit**, conventional message, `fix(technical-analysis): …` or `test(technical-analysis): …`.

---

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `app/handlers/analysis.py` | The TA-side aggregator: an async **function** `get_aggregated_signal`, not a class. Builds `(label, confidence)` tuples, weighted-sums them, returns the response dict. | 1, 5 |
| `app/strategies/squeeze_momentum_strategy.py` | LIVE strategy served at `/api/v1/strategies/sqzmom/signal/{symbol}`. Returns entry/stop/TP. Task 2 also marks its one surviving dimensionless round. | 2 |
| `app/indicators/sqzmom_enhanced.py` | `SqueezeMetadata.to_dict()` serializes bands and price. Library-contract rot — not on the live route. Task 3 also marks its three surviving dimensionless rounds. | 3 |
| `app/main.py` | Route definitions. `Query(default=…)` literals duplicate Settings values. | 4 |
| `tests/test_signal_aggregator_confidence_zero.py` | Existing; holds the currently-red test that Task 1 turns green. | 1 |
| `tests/unit/test_sqzmom_strategy_precision.py` | **NEW** — ADA-scale precision assertions. | 2, 3 |
| `tests/test_endpoint_defaults_from_settings.py` | **NEW** — route defaults track Settings. | 4 |
| `tests/test_aggregator_new_legs.py` | **NEW** — ADX/SQZMOM vote, Volume multiplier. | 5 |
| `tests/test_price_rounding_invariant.py` (repo root `tests/`) | **NEW** — AST guard banning `round(x, 2\|4)` over a bounded file list, with a line-level `# non-price-round` opt-out. | 6 |

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
git commit -m "fix(technical-analysis): no usable votes aggregates to HOLD, not phantom BUY

With an empty signals list every weight is 0.0 and argmax returns \"BUY\"
(first-inserted key wins ties in CPython), which took the directional
confidence branch and its else-0.0 arm. The 0.5 neutral fallback was only
reachable for HOLD, which argmax could never produce. The live endpoint
therefore answered {signal: BUY, confidence: 0.0} whenever every indicator
failed - a directional label asserted on zero information.

Turns test_empty_signal_list_returns_neutral_fallback green; the TA
known-failure baseline drops from 3 to 2." -- services/technical-analysis/app/handlers/analysis.py services/technical-analysis/tests/test_signal_aggregator_confidence_zero.py
```

---

## Task 2: Squeeze-momentum strategy stops rounding prices to 2dp (LIVE)

`analyze()` returns `entry_price`, `stop_loss`, and `take_profit` rounded to 2 decimals. For ADAUSDT (~$0.60, Bybit tick 0.0001) this collapses every level onto a 1-cent grid: a 2% stop at 0.588 becomes 0.59. The values are served at `GET /api/v1/strategies/sqzmom/signal/{symbol}` via `handlers/sqzmom.py`, which re-wraps them with `float(...)` — and `float()` cannot restore precision that rounding already destroyed.

**Files:**
- Modify: `services/technical-analysis/app/strategies/squeeze_momentum_strategy.py:203-205`, `:207`, `:171`
- Test: `services/technical-analysis/tests/unit/test_sqzmom_strategy_precision.py` (**NEW**)

**Interfaces:**
- Consumes: nothing.
- Produces: `SqueezeMomentumStrategy.analyze(df) -> Dict` — same keys, unchanged types (`float`), full precision. Task 6 adds this file to the AST guard's `SCANNED_FILES`, so the one dimensionless rounding that survives here (`confidence`) must carry the `# non-price-round` marker — Step 3 writes it.
- Produces: `tests/unit/test_sqzmom_strategy_precision.py` with the helper `_ada_ohlc(n: int = 80, seed: int = 7) -> pd.DataFrame`. **`seed` is the second parameter on purpose** — Task 3 calls `_ada_ohlc(120)` positionally and must keep working.

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


def _ada_ohlc(n: int = 80, seed: int = 7) -> pd.DataFrame:
    """ADA-scale OHLCV frame: prices near $0.60, ranges near $0.003.

    `seed` is the SECOND parameter deliberately: Task 3 calls _ada_ohlc(120)
    positionally, so inserting seed first would silently change its frame.
    """
    rng = np.random.default_rng(seed)
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
    # seed=0 leaves the last bar in a released squeeze with rising positive
    # momentum, so a BUY actually fires. min_momentum_threshold must also be
    # scaled down: the 0.5 default is in PRICE units, and ADA-scale
    # sqz_momentum is ~1e-3, which can never clear it. The default seed=7
    # fixture returns HOLD ("Momentum too weak (-0.0026 < 0.5)") and HOLD
    # hard-sets stop_loss/take_profit to 0.0, so it cannot cover this.
    df = _ada_ohlc(seed=0)
    strategy = SqueezeMomentumStrategy(min_momentum_threshold=1e-9)

    result = strategy.analyze(df)
    assert result["action"] in ("BUY", "SELL"), (
        f"fixture produced no directional entry (action={result['action']}, "
        f"momentum={result['momentum']}); analyze() hard-sets stop_loss and "
        "take_profit to 0.0 on HOLD, so every assertion below would be vacuous"
    )

    entry = result["entry_price"]
    stop = result["stop_loss"]
    target = result["take_profit"]
    sign = 1 if result["action"] == "BUY" else -1

    realized_stop_pct = abs(entry - stop) / entry * 100
    assert realized_stop_pct == pytest.approx(strategy.stop_loss_pct, rel=1e-9), (
        f"stop is {realized_stop_pct:.4f}% from entry, configured "
        f"{strategy.stop_loss_pct}% - rounding moved the stop"
    )

    realized_tp_pct = abs(target - entry) / entry * 100
    assert realized_tp_pct == pytest.approx(strategy.take_profit_pct, rel=1e-9), (
        f"target is {realized_tp_pct:.4f}% from entry, configured "
        f"{strategy.take_profit_pct}% - rounding moved the target"
    )
    assert sign * (target - entry) > 0 and sign * (entry - stop) > 0, (
        "rounding put stop or target on the wrong side of entry"
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

Expected: **3 failed** — all three tests, not just one. Every failure is real; do not debug any of them as a broken test:

- `test_entry_price_keeps_full_precision` — the served value equals its own 2dp rounding.
- `test_stop_and_target_keep_their_percentage_distance` — on `_ada_ohlc(seed=0)` the raw last close is `0.6144410483109704` and `analyze()` returns `action='BUY'`, but today it serves `entry_price=0.61, stop_loss=0.6, take_profit=0.64`: the realized stop distance is **1.6393%** against a configured 2.0%, and the take-profit distance is **4.918%** against a configured 4.0%. After Step 3 they become **2.0000000000000013%** and **4.000000000000003%**, both inside `rel=1e-9`.
- `test_momentum_keeps_precision_at_ada_scale` — raw momentum on the seed-7 fixture is `-0.0025750385684731427`, but the served value is `round(_, 4) == -0.0026`, which equals its own 4dp rounding.

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
                # confidence is dimensionless 0-1, so it legitimately stays
                # rounded; the marker is the AST guard's line-level opt-out.
                'confidence': round(float(confidence), 2),  # non-price-round
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

`confidence` stays rounded — it is dimensionless 0–1, not price-domain. It **must** carry the trailing `# non-price-round` marker exactly as written above: Task 6 adds this file to an AST guard that bans every `round(x, 2)` and `round(x, 4)` in it, and that marker is the guard's line-level opt-out. Without it Task 6 lands red. This is the only surviving banned-ndigits call in this file after the edits below.

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
git commit -m "fix(technical-analysis): SQZMOM strategy serves full-precision price levels

entry_price, stop_loss and take_profit were rounded to 2dp before being
served at /api/v1/strategies/sqzmom/signal/{symbol}. On ADA (~\$0.60, tick
0.0001) that snaps every level onto a 1-cent grid: a 2% stop moves by up to
40% of its own distance and can land on the wrong side of entry. The
handler re-wraps with float(), which cannot restore destroyed precision.

Same defect class as 487d1bd. Dimensionless confidence stays rounded and
carries the # non-price-round marker that the WS1-A Task 6 AST guard reads
as a line-level opt-out." -- services/technical-analysis/app/strategies/squeeze_momentum_strategy.py services/technical-analysis/tests/unit/test_sqzmom_strategy_precision.py
```

---

## Task 3: `SqueezeMetadata.to_dict` stops quantizing bands and price

`to_dict()` serializes Bollinger and Keltner band edges plus `current_price` at 4 decimals. 4dp equals ADA's tick exactly, so it is borderline-lossy for ADA today and outright lossy for any sub-cent listing.

**Reachability note — state this in the commit, do not overstate the severity.** `to_dict()` is consumed only by `get_signal()` → `analyze()` → the module-level `calculate_squeeze_momentum()` convenience function. The LIVE HTTP route `/api/v1/indicators/enhanced-sqzmom` calls `calculator.calculate(df)` and never touches `to_dict`. This is library-contract rot in the same family, not a live-signal bug.

**Files:**
- Modify: `services/technical-analysis/app/indicators/sqzmom_enhanced.py:115`, `:118-125`, `:738`
- Test: `services/technical-analysis/tests/unit/test_sqzmom_strategy_precision.py` (extend the file created in Task 2)

This file has **three** dimensionless `round(x, 4|2)` calls that legitimately survive — `momentum_strength` (`:115`), `band_width_ratio` (`:125`) and `EnhancedSqueezeMomentum._calculate_confidence`'s `return round(confidence, 2)` (`:738`, def at `:653`). Task 6 adds this file to an AST guard that bans both ndigits values file-wide, so all three must be annotated with the trailing `# non-price-round` marker in this task. That is why the edit range is wider than the price-domain block. `momentum_value` / `momentum_acceleration` / `histogram` round to 6dp and are not affected.

**Interfaces:**
- Consumes: the `_ada_ohlc` helper from Task 2's test file, called positionally as `_ada_ohlc(120)`.
- Produces: `SqueezeMetadata.to_dict() -> Dict[str, Any]` — same keys, price-domain values now full-precision floats; the three dimensionless values keep their rounding and gain the `# non-price-round` marker Task 6's guard honours.

- [ ] **Step 1: Write the failing test**

First add the `math` import the new test needs. At the top of `services/technical-analysis/tests/unit/test_sqzmom_strategy_precision.py`, replace:

```python
import sys
```

with:

```python
import math
import sys
```

Add it in **this** commit, not Task 2's — `math` is unused until the test below exists, and the repo's format hook has stripped unused imports before.

Then append to the same file:

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
        # NOT `value == pytest.approx(value)` - that compares a binding to
        # itself and discriminates nothing. isfinite is the real guard: if the
        # fixture ever yields fewer bars than the 20-period BB/KC warmup the
        # bands come back NaN, and `nan != round(nan, 4)` is True, so the 4dp
        # check alone would pass vacuously.
        assert math.isfinite(value), f"{field}={value} is not a finite number"
        assert value != round(value, 4) or value == 0.0, (
            f"{field}={value} is still quantized to 4dp"
        )
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd services/technical-analysis && python3 -m pytest tests/unit/test_sqzmom_strategy_precision.py::test_metadata_bands_keep_full_precision --no-cov -q
```

Expected: FAIL — every band equals its own 4dp rounding.

- [ ] **Step 3: Drop the rounding on price-domain fields, mark the dimensionless ones**

In `app/indicators/sqzmom_enhanced.py`, inside `SqueezeMetadata.to_dict()`, replace lines 115–125:

```python
            "momentum_strength": round(self.momentum_strength, 4),
            "histogram": [round(h, 6) for h in self.histogram[-10:]],  # Last 10 values
            "histogram_color": self.histogram_color,
            "bb_upper": round(self.bb_upper, 4),
            "bb_basis": round(self.bb_basis, 4),
            "bb_lower": round(self.bb_lower, 4),
            "kc_upper": round(self.kc_upper, 4),
            "kc_basis": round(self.kc_basis, 4),
            "kc_lower": round(self.kc_lower, 4),
            "current_price": round(self.current_price, 4),
            "band_width_ratio": round(self.band_width_ratio, 4)
```

with:

```python
            "momentum_strength": round(self.momentum_strength, 4),  # non-price-round
            "histogram": [round(h, 6) for h in self.histogram[-10:]],  # Last 10 values
            "histogram_color": self.histogram_color,
            # Price-domain: 4dp is exactly ADA's tick and lossy below it.
            # Full precision here; quantization belongs at order time.
            "bb_upper": float(self.bb_upper),
            "bb_basis": float(self.bb_basis),
            "bb_lower": float(self.bb_lower),
            "kc_upper": float(self.kc_upper),
            "kc_basis": float(self.kc_basis),
            "kc_lower": float(self.kc_lower),
            "current_price": float(self.current_price),
            "band_width_ratio": round(self.band_width_ratio, 4)  # non-price-round
```

`momentum_strength` (normalized 0–1) and `band_width_ratio` (a ratio) keep their rounding — both are dimensionless. Their **values do not change**; only the trailing `# non-price-round` marker is added, which is the opt-out Task 6's AST guard reads. `histogram` and the 6dp fields are untouched and need no marker: only ndigits 2 and 4 are banned.

- [ ] **Step 4: Mark the third dimensionless rounding, outside `to_dict`**

`EnhancedSqueezeMomentum._calculate_confidence` (def at `app/indicators/sqzmom_enhanced.py:653`) ends by returning a clamped 0.1–1.0 score. It is dimensionless, its value must not change, and it is the last banned-ndigits call left in this file. Replace line 738:

```python
        return round(confidence, 2)
```

with:

```python
        return round(confidence, 2)  # non-price-round
```

Do not convert this one to `float()` — the 2dp rounding is part of the confidence contract every SQZMOM consumer already reads. Skipping this line leaves Task 6's guard red with exactly one violation.

- [ ] **Step 5: Verify**

```bash
cd services/technical-analysis && python3 -m pytest tests/unit/test_sqzmom_strategy_precision.py tests/test_enhanced_sqzmom_service.py --no-cov -q
```

Expected: all pass.

Then confirm the file has no unmarked banned rounding left — this is what Task 6's guard will check:

```bash
cd services/technical-analysis && grep -n "round(.*, *[24])" app/indicators/sqzmom_enhanced.py
```

Expected: exactly three lines, and **every one of them ends in `# non-price-round`** (`momentum_strength`, `band_width_ratio`, and the `_calculate_confidence` return). Any unmarked hit is a miss — go back to Step 3 or Step 4.

- [ ] **Step 6: Commit**

```bash
git commit -m "fix(technical-analysis): SqueezeMetadata.to_dict keeps band precision

Bands and current_price were serialized at 4dp, which is exactly ADA's tick
size and lossy for anything below it. Same PRICE-01 family as the strategy
fix.

Dimensionless momentum_strength, band_width_ratio and the
_calculate_confidence return keep their rounding, unchanged in value, and
now carry the # non-price-round marker that the WS1-A Task 6 AST guard
reads as a line-level opt-out.

Scope note: to_dict is not on the live /api/v1/indicators/enhanced-sqzmom
route (that path calls calculate()); this is library-contract rot, not a
live-signal defect." -- services/technical-analysis/app/indicators/sqzmom_enhanced.py services/technical-analysis/tests/unit/test_sqzmom_strategy_precision.py
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


def test_rsi_bounds_and_description_survive_the_settings_rewire():
    """Only default= may move. ge/le and description are a live contract.

    Narrowing RSI's le from 200 to 100 turns ?period=150 from HTTP 200 into
    HTTP 422, and dropping description= rewrites the published OpenAPI schema.
    Neither is caught by the two route-default tests above, so pin them here.
    """
    schema = client.get("/openapi.json").json()
    rsi_params = {
        p["name"]: p
        for p in schema["paths"]["/api/v1/indicators/rsi/{symbol}"]["get"]["parameters"]
    }
    period = rsi_params["period"]["schema"]

    assert period["default"] == settings.default_rsi_period
    assert period["minimum"] == 2, f"RSI ge moved: {period}"
    assert period["maximum"] == 200, (
        f"RSI le narrowed to {period.get('maximum')} - it is 200; 100 is the "
        "Bollinger endpoint's bound"
    )
    assert period["description"] == "RSI period (optimized for crypto)", (
        f"RSI description changed: {period.get('description')!r}"
    )
```

Note: `test_openapi_schema_defaults_track_settings` passes both before and after the change, because the literals currently equal the Settings values. It is a **drift guard** — it goes red the day someone changes a Settings default without touching `main.py`. Keep it. `test_rsi_bounds_and_description_survive_the_settings_rewire` also passes before and after for the same reason; its job is to fail if the Step 3 edit narrows a bound or drops a description.

- [ ] **Step 2: Run it and prove the tests have teeth**

```bash
cd services/technical-analysis && python3 -m pytest tests/test_endpoint_defaults_from_settings.py --no-cov -q
```

Expected: **4 passed** on current, unmodified code — because the hardcoded literals coincidentally equal the Settings values. **This is expected and is why the change is a drift fix, not a value fix.** To prove the tests have teeth, temporarily change `default_macd_fast` in `app/config.py` to `6`, re-run, and confirm `test_macd_route_defaults_come_from_settings` now FAILS. Then revert `config.py` to `5` before proceeding.

- [ ] **Step 3: Wire the Query defaults to Settings**

`settings` is already a module-level instance at `app/main.py:75`, so these references are import-safe.

Line 271 (RSI endpoint). The current line is `period: int = Query(default=9, ge=2, le=200, description="RSI period (optimized for crypto)"),` — note `le=200`, **not** `le=100`; the Bollinger endpoint is the one with `le=100`. Replace it with:

```python
    period: int = Query(default=settings.default_rsi_period, ge=2, le=200, description="RSI period (optimized for crypto)"),
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

Keep the existing `ge`/`le` bounds and descriptions exactly as they are — only the `default=` expression changes. Before editing, diff each replacement line against the file it replaces and confirm the only textual difference is `default=`. A narrowed bound is a live contract change with no test in this plan to catch it: dropping RSI's `le` from 200 to 100 would flip `GET /api/v1/indicators/rsi/BTCUSDT?period=150` from HTTP 200 to HTTP 422, and dropping a `description=` silently rewrites the published OpenAPI schema.

- [ ] **Step 4: Verify, including the teeth check**

```bash
cd services/technical-analysis && python3 -m pytest tests/test_endpoint_defaults_from_settings.py tests/test_indicator_handlers.py tests/test_config.py --no-cov -q
```

Expected: all pass. Repeat the temporary-edit teeth check from Step 2 once more and confirm the route test now fails *for the right reason* (the route default moved with Settings). Revert.

- [ ] **Step 5: Commit**

```bash
git commit -m "fix(technical-analysis): route defaults read Settings instead of duplicating them

MACD 5/35/5, BB 20/2.5 and RSI 9 were hardcoded as Query(default=...)
literals while identical Settings fields sat unread. The trading-engine
deliberately omits MACD params so this service's endpoint defaults are its
single source of truth, so an operator's DEFAULT_MACD_FAST reached the
/analyze path but not /indicators/macd - a silent split-brain.

Query defaults evaluate at import time: env overrides need a service
restart, and the OpenAPI schema defaults now track Settings." -- services/technical-analysis/app/main.py services/technical-analysis/tests/test_endpoint_defaults_from_settings.py
```

---

## Task 5: ADX and SQZMOM enter the vote; Volume becomes a confidence multiplier (LIVE)

`get_aggregated_signal` votes exactly three legs: RSI, MACD, TrendFilter. ADX, Enhanced SQZMOM, and Volume Confirmation are fully implemented in this same service, orchestrated by `IndicatorService`, and exposed as REST endpoints — and none of them is consulted by the aggregate.

**Volume must NOT become a voting leg.** Its labels are `CONFIRM`/`REJECT`, and appending either raw would `KeyError` at `signal_weights[sig] += weight` and surface as an HTTP 500 through the generic `except` at line 145. It is also directionally agnostic — high volume confirms a breakdown exactly as much as a breakout. The trading-engine already models this correctly: volume is excluded from its vote and applied as a post-vote confidence multiplier in `aggregation/validator.py`. Mirror that design here.

**Files:**
- Modify: `services/technical-analysis/app/handlers/analysis.py` — `:12-13` (imports), after `:45` (computation), after `:88` (vote legs), after `:130` (volume multiplier), `:132-141` (response). All line numbers are **pre-edit**; each step shifts the ones below it, so every step anchors on text as well.
- Test: `services/technical-analysis/tests/test_aggregator_new_legs.py` (**NEW**)

**Interfaces:**
- Consumes: Task 1's `final_signal` short-circuit. This task inserts legs *before* the weighted sum, so **it can destroy that fix** — Task 1's `if total_weight > 0 else "HOLD"` only fires when `signals` is genuinely empty. Steps 5 and 6 exist to keep it reachable; do not relax their guards.
- Produces: the response dict gains three additive keys — `adx`, `sqzmom`, `volume`. Existing keys are unchanged; nothing may be renamed. The route that serves this (`app/main.py:782`, `@app.get("/api/v1/indicators/signal/{symbol}", tags=["Analysis"])`) declares **no `response_model`** — verified — so the three new keys reach the wire unfiltered and the completion checklist's `curl` proof is achievable. Do not add a `response_model` here; the sibling RSI/MACD/Bollinger routes have one, and adding one would silently strip these keys while every unit test stayed green.
- Calculator APIs and their **failure defaults** (verified against the source — none of them is a 0.0 confidence, which is why Steps 5 and 6 need explicit guards):
  - `ADXCalculator().calculate_with_signal(highs: List[float], lows: List[float], closes: List[float]) -> Tuple[Dict, str, float]` — the `str` is already `"BUY"`/`"SELL"`/`"HOLD"`. **Failure default: `("HOLD", 0.3)`.** Insufficient data returns `_default_response()` with `regime = RANGING` (`adx.py:383`), and every RANGING read falls to `signal = "HOLD"; confidence = 0.3` (`adx.py:436-439`). The `"confidence": 0.0` field inside `_default_response()` is never read by `calculate_with_signal`.
  - `EnhancedSqueezeMomentum().calculate(df: pd.DataFrame) -> Optional[pd.DataFrame]` — last row carries `sqz_signal` (BUY/SELL/HOLD) and `sqz_confidence` (0–1). **Failure default: `None`** on fewer than 25 bars (`sqzmom_enhanced.py:857-861`); on sufficient data a HOLD carries a flat `0.25` (`sqzmom_enhanced.py:687-688`).
  - `VolumeConfirmation().calculate(volumes: List[float], signal_type: str = "breakout") -> Dict` — keys include `confirmed` (bool), `strength` (`STRONG`/`MODERATE`/`WEAK`/`INSUFFICIENT`), `volume_ratio`, `confidence`. **Failure default: `_reject_response()`** (`volume_confirmation.py:111-121`) — `confirmed False`, `strength "INSUFFICIENT"`, `volume_ratio 0.0` — returned on fewer than 20 bars or on any exception.

- [ ] **Step 1: Write the failing test**

The mock trap here is real: existing tests build a 10-row DataFrame, which is below ADX's 29-bar minimum (`adx.py:147`, `period * 2 + 1` with `period=14`), SQZMOM's 25-bar minimum (`sqzmom_enhanced.py:857`, `max(bb_length, kc_length, momentum_length) + 5` = `max(20, 20, 12) + 5`) and VolumeConfirmation's 20-bar period (`volume_confirmation.py:27`). Unpatched real calculators return their **failure defaults, which are not neutral** — ADX gives `("HOLD", 0.3)`, SQZMOM gives `None`, Volume gives `_reject_response()` — so the test would silently exercise those instead of the values it thinks it set. Patch the calculators at the handler's module namespace.

*(Do not "correct" the 25 back to 32. 32 is `indicator_service.py:381`'s different gate, `max(bb_period, kc_period) + mom_period`, which guards the `/api/v1/indicators/enhanced-sqzmom` REST route. Step 4 calls `EnhancedSqueezeMomentum().calculate(df)` directly and bypasses `IndicatorService`, so the applicable minimum is the calculator's own 25.)*

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
29-bar minimum, SQZMOM's 25-bar minimum and Volume's 20-bar period, and
those failure defaults are NOT neutral: ADX returns ("HOLD", 0.3) and
VolumeConfirmation returns _reject_response() with volume_ratio 0.0. An
unpatched leg would therefore cast a real vote / apply a real penalty and
the test would be measuring the wrong thing.
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

Anchor by text: insert directly after the line `trend = trend_result.get("trend") if trend_result else None` (originally line 45, now ~51 because Step 3 grew the import block by six lines). Insert **after** the `trend_result` / `trend` pair, not between them:

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

Anchor by text, not by line number — Step 4 already inserted ~11 lines and shifted everything below it. Insert **after** the closing `)` of the trend `signals.append(...)` block (originally line 88) and **before** the comment `# Drop confidence=0 entries before aggregation (INFRA-06 Bug 2).` (originally line 90):

```python
        # ADX's failure default is HOLD at confidence 0.3 (adx.py:436-439), not
        # 0.0, so the weight > 0.0 filter below cannot tell a dead ADX from a
        # genuine ranging read. Only its directional labels may vote.
        if adx_signal in ("BUY", "SELL") and float(adx_conf) > 0.0:
            signals.append((str(adx_signal), float(adx_conf)))

        # Same for SQZMOM: HOLD is a flat 0.25 (sqzmom_enhanced.py:687-688).
        if sqz_df is not None and not sqz_df.empty:
            last_row = sqz_df.iloc[-1]
            if str(last_row["sqz_signal"]) in ("BUY", "SELL"):
                signals.append(
                    (str(last_row["sqz_signal"]), float(last_row["sqz_confidence"]))
                )
```

**The `weight > 0.0` filter at line 95 does not save you here — gate both legs to `BUY`/`SELL` exactly as written.** ADX's insufficient-data path returns `_default_response()` with `regime == RANGING`, and `calculate_with_signal` maps every RANGING/weak read to `signal = "HOLD"`, `confidence = 0.3` (`adx.py:436-441`). SQZMOM's `_calculate_confidence` returns a flat `0.25` for HOLD (`sqzmom_enhanced.py:687-688`). Neither is 0.0, so neither is filtered: an ungated ADX leg makes `total_weight` effectively never zero, Task 1's `if total_weight > 0 else "HOLD"` short-circuit becomes dead code, and `test_empty_signal_list_returns_neutral_fallback` goes red again at `confidence = 0.3 / 0.3 = 1.0`.

This is not a blanket ban on HOLD votes — RSI deliberately votes HOLD at a flat 0.3 in this same aggregator (`rsi.py:185-187`) and that stays. The narrow problem is that ADX's *failure* default is textually identical to a genuine ranging read, so a dead calculator would cast a weighted vote.

- [ ] **Step 6: Apply the volume multiplier and extend the response**

Again anchor by text: insert after the closing `)` of the `else:` branch's `confidence = (...)` assignment (the `else 0.5` arm, originally line 130) and immediately before the `return {` (originally line 132):

```python
        # Volume validation: scale a directional signal's confidence by how
        # well volume confirms it. Tiers mirror the trading-engine's
        # aggregation/validator.py so the two services agree.
        volume_penalty = 1.0
        # volume_ratio == 0.0 is VolumeConfirmation._reject_response()
        # (volume_confirmation.py:115) - fewer than `period` bars, or an
        # exception. That is ABSENCE of information, not disconfirmation, and
        # validator.py's ladder documents it as "No volume data: 1.0x (pass
        # through)". A genuine sub-1.0x reading still takes the 0.5 penalty.
        volume_has_data = float(volume_result.get("volume_ratio") or 0.0) > 0.0
        if final_signal in ("BUY", "SELL") and volume_has_data:
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

**Gate on `volume_ratio`, never on `len(df)` and never on any attribute of the calculator instance.** Two reasons, both load-bearing:

- Under this task's own `patch.multiple`, `VolumeConfirmation()` is a `MagicMock`, so `vol_calc.period` is a `MagicMock` and `len(df) < vol_calc.period` raises `TypeError` inside the handler's `try`, which the generic `except` at `analysis.py:145-147` converts to an HTTP 500 — every new test fails at once. Keep the call inline as Step 4 writes it; do **not** hoist a `vol_calc = VolumeConfirmation()` binding.
- Gating on `strength != "INSUFFICIENT"` would also make the tests pass, so the tests do not discriminate — but the source does. `volume_confirmation.py:89` emits `INSUFFICIENT` for a *real* below-average reading (`volume_ratio < 1.0`, confidence 0.1), while `:117` emits the same string from `_reject_response` for the data-failure path (`volume_ratio 0.0`). Gating on the string silently deletes a legitimate low-volume penalty; gating on the ratio does not.

Without this guard, `tests/test_signal_aggregator_confidence_zero.py::test_all_positive_confidence_unchanged` goes red: it patches only RSI/MACD/Trend, so the real `VolumeConfirmation` sees a 10-row frame, returns `_reject_response()`, falls through the ladder to `else: volume_penalty = 0.5`, and halves a confidence the test asserts is exactly `1.0`.

Then replace the whole `return { ... }` block (originally lines 132–141) with the version below — three additive keys; do not rename or remove any existing key:

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

Expected: all pass — **26 passed**, including all three of `test_signal_aggregator_confidence_zero.py`. Those three are the load-bearing ones and neither of them patches ADX or Volume, so they are what actually proves Steps 5 and 6's guards:

- `test_empty_signal_list_returns_neutral_fallback` — red at `confidence == 1.0` if the ADX leg is not gated to BUY/SELL (an unpatched ADX votes `("HOLD", 0.3)`, so `total_weight = 0.3` and Task 1's short-circuit never fires).
- `test_all_positive_confidence_unchanged` — red at `confidence == 0.5` if the volume multiplier is not gated on `volume_has_data` (an unpatched VolumeConfirmation on a 10-row frame returns `_reject_response()` and the ladder halves a confidence the test pins at `1.0`).

If either is red, do not adjust the test — the guard is missing or wrong.

Non-vacuity check — comment out the two `signals.append` blocks you just added and re-run. `test_adx_alone_can_carry_the_signal` and `test_sqzmom_alone_can_carry_the_signal` must both FAIL. Restore.

Then the full suite:

```bash
cd services/technical-analysis && python3 -m pytest tests/ --no-cov -q
```

Expected: **2 failed**, and both of them `tests/test_comprehensive_80.py::TestMarketDataFetcherDataFrame` — `test_get_klines_as_dataframe_success` and `test_get_klines_as_dataframe_empty`. That matches the post-Task-1 baseline. Judge on the failure names, not the pass count: the pass count climbs task by task as Tasks 2–5 each add a test file, so a fixed number here would be wrong by the time you read it.

- [ ] **Step 8: Commit**

```bash
git commit -m "feat(technical-analysis): ADX and SQZMOM vote; volume scales confidence

ADX, Enhanced SQZMOM and Volume Confirmation are computed in this service
and served as endpoints, but get_aggregated_signal consulted only RSI, MACD
and TrendFilter.

ADX and SQZMOM already emit BUY/SELL/HOLD with their own confidence, so they
drop into the existing (label, confidence) shape. Only their DIRECTIONAL
labels vote: ADX's failure default is HOLD at confidence 0.3 (adx.py:436-439)
and SQZMOM's is HOLD at 0.25, so the weight > 0 filter cannot tell a dead
calculator from a genuine ranging read, and an ungated leg would make the
neutral-HOLD fallback added in the previous commit unreachable.

Volume deliberately does NOT vote: its labels are CONFIRM/REJECT, which
would KeyError the weight dict into an HTTP 500, and it is directionally
agnostic. It scales post-vote confidence with the same tiers the
trading-engine's validator uses, so the two services agree - including that
validator's \"No volume data -> 1.0x pass through\" rule, keyed here on
volume_ratio == 0.0 so a _reject_response is read as absence of information
rather than as disconfirmation.

Response gains adx/sqzmom/volume keys; no existing key changed." -- services/technical-analysis/app/handlers/analysis.py services/technical-analysis/tests/test_aggregator_new_legs.py
```

---

## Task 6: AST guard banning `round(x, 2)` over the files this plan fixed

Lock the class shut. Model the guard on `tests/test_account_size_invariant.py`, the `$100` invariant added by quick task `260803-4mt`.

**Critical scoping rule:** `SCANNED_FILES` may list only files already fixed. There are roughly 17 further `round(..., 2)` sites in `app/indicators/*.py` that this plan does not touch — including them would make the guard permanently red. Plan B has an explicit step to append the trading-engine files it fixes.

**Second scoping rule — the guard is file-scoped, so it needs a line-level escape hatch.** The two files in `SCANNED_FILES` legitimately keep four dimensionless `round(x, 2|4)` calls after Tasks 2 and 3: `confidence` in the strategy, and `momentum_strength`, `band_width_ratio` and `_calculate_confidence`'s return in the indicator. Tasks 2 and 3 annotate each of them with a trailing `# non-price-round` comment. This task builds the mechanism that honours it: `ALLOW_MARKER = "# non-price-round"`, skipped per source line inside `find_violations`. Without both halves — marker *and* skip — the guard lands red on the very commit that creates it.

**Files:**
- Create: `tests/test_price_rounding_invariant.py` (repo root `tests/`, **not** the service's tests directory)
- Read-only: `services/technical-analysis/app/strategies/squeeze_momentum_strategy.py` and `services/technical-analysis/app/indicators/sqzmom_enhanced.py` — this task scans them; Tasks 2 and 3 already edited them. Step 2 says what to do if a marker is missing.

**Interfaces:**
- Consumes: the files fixed in Tasks 2 and 3, including the `# non-price-round` markers they wrote.
- Produces: `find_violations(source: str, filename: str) -> list[str]` and the module constants `SCANNED_FILES: tuple[str, ...]`, `BANNED_NDIGITS: frozenset[int]` and `ALLOW_MARKER: str`. **Plan B appends to `SCANNED_FILES` and reuses `ALLOW_MARKER`** — keep `SCANNED_FILES` a module-level tuple of repo-relative path strings, and keep the marker spelled exactly `"# non-price-round"`. Plan B does not redefine it.

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
Scope is per-file, so those sites are exempted per LINE: a round() call whose
source line ends in the ALLOW_MARKER comment below is skipped. Four such
sites survive in the two files scanned today - the strategy's `confidence`,
and the indicator's `momentum_strength`, `band_width_ratio` and
_calculate_confidence return. Marking a line is a claim that the value is
dimensionless; do not use it to silence a price.
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
#   the OTHER services/technical-analysis/app/indicators/*.py modules
#                                                     (~17 sites, PRICE-02)
#   services/technical-analysis/app/handlers/sqzmom.py (4dp momentum)
#   trading-engine strategy + detector files           (added by WS1-B)

BANNED_NDIGITS = frozenset({2, 4})

# Line-level opt-out. A banned round() whose own source line carries this
# comment is a declared dimensionless value. WS1-B reuses this exact string -
# do not respell it, and do not add a second escape mechanism.
ALLOW_MARKER = "# non-price-round"


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
    """One human-readable violation string per banned rounding call.

    A call is exempt when its own source line carries ALLOW_MARKER. The check
    is per-line, not per-file: marking one site never silences another.
    """
    tree = ast.parse(source, filename=filename)
    source_lines = source.splitlines()
    violations: list[str] = []

    for node in ast.walk(tree):
        if not _is_round_call(node):
            continue
        ndigits = _ndigits_of(node)
        if ndigits in BANNED_NDIGITS:
            line = (
                source_lines[node.lineno - 1]
                if node.lineno <= len(source_lines)
                else ""
            )
            if ALLOW_MARKER in line:
                continue
            violations.append(
                f"{filename}:{node.lineno}: round(..., {ndigits}) in a file "
                "declared free of price-domain rounding. Crypto prices need "
                "full precision here (float(x)); quantize at order time. If "
                f"the value really is dimensionless, append '{ALLOW_MARKER}' "
                "to that line."
            )

    return sorted(set(violations))


NEGATIVE_FIXTURE = '''
value = round(pct_change, 3)
ratio = round(current_volume / avg_volume, 1)
scaled = round(fraction, 6)
dynamic = round(price, tick_decimals)
bare = round(x)
marked = round(current_volume / avg_volume, 2)  # non-price-round
'''

POSITIVE_FIXTURE = '''
entry = round(entry_price, 2)
stop = round(sl, ndigits=2)
band = np.round(bb_upper, 4)
col = series.round(2)
'''

# One marked line and one unmarked violation in the same source. The marker
# must exempt its own line only - a file-wide or first-match-wins skip would
# report 0 here.
MARKER_LEAK_FIXTURE = '''
allowed = round(rsi_value, 2)  # non-price-round
leaked = round(entry_price, 2)
'''


def test_negative_cases_do_not_trip():
    """Zero false positives on legitimate rounding, including a marked site.
    Parsed in-memory so the guarantee cannot drift when live repo files
    change."""
    violations = find_violations(NEGATIVE_FIXTURE, "negative_fixture.py")
    assert violations == [], "false positives:\n" + "\n".join(violations)


def test_positive_cases_do_trip():
    """All four call shapes are detected. No line here carries the marker."""
    violations = find_violations(POSITIVE_FIXTURE, "positive_fixture.py")
    rendered = "\n".join(violations)
    assert len(violations) == 4, (
        f"expected 4 violations, got {len(violations)}:\n{rendered}"
    )
    for expected in ("round(..., 2)", "round(..., 4)"):
        assert expected in rendered, f"missing {expected} in:\n{rendered}"


def test_marker_does_not_leak_to_other_lines():
    """The opt-out is per-line. Marking one site must not silence the next."""
    violations = find_violations(MARKER_LEAK_FIXTURE, "leak_fixture.py")
    rendered = "\n".join(violations)
    assert len(violations) == 1, (
        f"expected exactly 1 violation, got {len(violations)}:\n{rendered}"
    )
    assert "leak_fixture.py:3" in rendered, (
        f"the unmarked round on line 3 must be the one reported:\n{rendered}"
    )


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
        f"and quantize at order time - or, if the value is dimensionless, "
        f"append '{ALLOW_MARKER}' to that line. Never remove a file from "
        "SCANNED_FILES to make this pass:\n" + "\n".join(violations)
    )
```

- [ ] **Step 2: Prove the guard has teeth before trusting it green**

```bash
python3 -m pytest tests/test_price_rounding_invariant.py --no-cov -q
```

Expected: **6 passed** — three fixture tests, `test_scanned_file_exists` parametrized over the two paths, and the invariant itself. It is green because Task 2 removed the price-domain rounding from the strategy and marked its one dimensionless site, and Task 3 did the same for the indicator's three.

**If `test_no_price_rounding_in_scanned_files` is red, a marker is missing — do not touch `SCANNED_FILES` and do not delete a rounding.** These four lines, and only these four, must exist verbatim. Match by call text, not by line number: Tasks 2 and 3 inserted comment lines that shifted the originals.

| File | Required line |
|---|---|
| `services/technical-analysis/app/strategies/squeeze_momentum_strategy.py` | `                'confidence': round(float(confidence), 2),  # non-price-round` |
| `services/technical-analysis/app/indicators/sqzmom_enhanced.py` | `            "momentum_strength": round(self.momentum_strength, 4),  # non-price-round` |
| `services/technical-analysis/app/indicators/sqzmom_enhanced.py` | `            "band_width_ratio": round(self.band_width_ratio, 4)  # non-price-round` |
| `services/technical-analysis/app/indicators/sqzmom_enhanced.py` | `        return round(confidence, 2)  # non-price-round` |

Append the missing marker (value unchanged), re-run, and use the extended pathspec in Step 3 so the repair ships with this commit.

A green guard proves nothing unless you have seen it go red. Temporarily reintroduce one rounding — change `'entry_price': float(entry_price),` back to `'entry_price': round(entry_price, 2),` in `squeeze_momentum_strategy.py` — and re-run. `test_no_price_rounding_in_scanned_files` must FAIL naming that exact file and line. Then, separately, delete `  # non-price-round` from that file's `confidence` line and confirm the guard also goes red there — that proves the marker is what is holding the line, not an accident of the AST walk. Restore both and confirm green again.

- [ ] **Step 3: Commit**

```bash
git commit -m "test(price): AST guard banning round(x, 2|4) in cleaned files

round(price, 2) destroyed ADA precision and caused 30+ flip-flop losses
(487d1bd, PRICE-01/02). This guard makes reintroduction fail loudly.

Modeled on tests/test_account_size_invariant.py: a pure find_violations()
over in-memory fixtures, a bounded SCANNED_FILES tuple, and a parametrized
existence check so a rename cannot silently shrink coverage.

Scope is bounded on purpose - ~17 further sites in app/indicators/*.py are
not yet fixed, and a permanently-red guard gets disabled rather than obeyed.
WS1-B appends the trading-engine files it cleans.

Detects all four call shapes: round(x, 2), round(x, ndigits=2),
np.round(x, 4), series.round(2).

Because scope is per-file, dimensionless survivors get a per-LINE opt-out:
a call whose source line carries '# non-price-round' is skipped. The two
scanned files' four such sites were annotated by the preceding two commits.
Fixtures cover both that the marker works and that it does not leak to the
next line. WS1-B reuses the same constant." -- tests/test_price_rounding_invariant.py
```

Only if Step 2 sent you back to add a missing marker, use this pathspec instead so the repair is part of the same commit:

```bash
git commit -m "test(price): AST guard banning round(x, 2|4) in cleaned files

round(price, 2) destroyed ADA precision and caused 30+ flip-flop losses
(487d1bd, PRICE-01/02). This guard makes reintroduction fail loudly.

Because scope is per-file, dimensionless survivors get a per-LINE opt-out:
a call whose source line carries '# non-price-round' is skipped. This commit
also backfills a marker Tasks 2/3 left off, so no served value changes." -- tests/test_price_rounding_invariant.py services/technical-analysis/app/strategies/squeeze_momentum_strategy.py services/technical-analysis/app/indicators/sqzmom_enhanced.py
```

---

## Plan A completion checklist

- [ ] TA suite baseline is **2 failed**, down from 3 — and both are `tests/test_comprehensive_80.py::TestMarketDataFetcherDataFrame::test_get_klines_as_dataframe_success` and `::test_get_klines_as_dataframe_empty`. Judge on names, not on the pass count, which grows as each task adds a test file.
- [ ] `tests/test_signal_aggregator_confidence_zero.py` is **3 passed** after Task 5, not just after Task 1 — that file patches neither ADX nor VolumeConfirmation, so it is the real proof that Task 5's two guards hold.
- [ ] `python3 -m pytest tests/test_price_rounding_invariant.py --no-cov -q` passes from the repo root (**6 passed**), and has been *seen* to fail both when a rounding is reintroduced and when a `# non-price-round` marker is removed.
- [ ] All four dimensionless survivors carry the marker. From the repo root:
  ```bash
  grep -rn "round(.*, *[24])" services/technical-analysis/app/strategies/squeeze_momentum_strategy.py services/technical-analysis/app/indicators/sqzmom_enhanced.py
  ```
  Expected: exactly four lines, every one ending in `# non-price-round`.
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
