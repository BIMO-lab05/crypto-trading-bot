---
phase: 21-ta-aggregator-widening-leakage-net
reviewed: 2026-08-27T13:15:23Z
depth: standard
files_reviewed: 31
files_reviewed_list:
  - services/technical-analysis/app/config.py
  - services/technical-analysis/app/handlers/analysis.py
  - services/technical-analysis/app/indicators/ichimoku.py
  - services/technical-analysis/app/indicators/rsi_divergence.py
  - services/technical-analysis/app/indicators/sqzmom_enhanced.py
  - services/technical-analysis/app/main.py
  - services/technical-analysis/app/strategies/squeeze_momentum_strategy.py
  - services/technical-analysis/.dockerignore
  - services/trading-engine/app/aggregation/market_regime.py
  - services/trading-engine/app/auto_trader.py
  - services/trading-engine/app/config.py
  - services/trading-engine/app/handlers/signals.py
  - services/trading-engine/app/signal_aggregator.py
  - services/trading-engine/app/strategies/hybrid_strategy_router.py
  - services/trading-engine/app/strategies/multi_strategy_ensemble.py
  - services/trading-engine/app/strategies/simple_rsi_strategy.py
  - services/trading-engine/app/strategies/sqzmom_strategy_integration.py
  - services/trading-engine/app/trading_enhancements/advanced_position_sizing.py
  - services/trading-engine/scripts/ablation_ensemble_admission.py
  - services/technical-analysis/tests/test_aggregator_new_legs.py
  - services/technical-analysis/tests/test_build_context_hygiene.py
  - services/technical-analysis/tests/test_endpoint_defaults_from_settings.py
  - services/technical-analysis/tests/test_leakage_regression.py
  - services/trading-engine/tests/aggregation/test_mirror_literals.py
  - services/trading-engine/tests/strategies/test_ensemble_atr_levels.py
  - services/trading-engine/tests/strategies/test_ensemble_confidence_units.py
  - services/trading-engine/tests/strategies/test_ensemble_diversity_guard.py
  - services/trading-engine/tests/strategies/test_ensemble_leg_wiring.py
  - services/trading-engine/tests/test_engine_param_omission.py
  - services/trading-engine/tests/test_mtf_confidence_consolidation.py
findings:
  critical: 0
  warning: 2
  info: 5
  total: 7
status: issues_found
---

# Phase 21: Code Review Report

**Reviewed:** 2026-08-27T13:15:23Z
**Depth:** standard
**Files Reviewed:** 31 (diffs since `80e6074`, read in whole-file context)
**Status:** issues_found

## Narrative Findings (AI reviewer)

## Summary

Reviewed every file in scope against its diff since `80e6074`, tracing the new
code into its cross-file consumers (voter taxonomy, mean-reversion sub-signal
tokens, TA ATR producer, TA endpoint Query defaults, funnel wiring, and the
`_ensemble_stops_are_consistent` pre-fill guard). Verified independently, not
assumed:

- **Unit contract holds end-to-end.** `atr.py:91` emits `atr_pct` as a percent;
  `_atr_indicator` divides by 100 into `atr_fraction`;
  `SimpleRSIStrategy._resolve_atr_fraction` enforces the open (0, 1) interval
  and falls back to the named 2% default. The old `> 1.0` unit guess and the
  `or`-chain fall-through to the absolute reading are both gone. The failure
  payload (`_default_response`, atr/atr_pct 0.0 with populated 3% stops) is
  reproduced verbatim in the test fixtures and treated as ABSENT on every path.
- **Locked constraint intact.** `MIN_AGREEING_LEGS = 1`
  (multi_strategy_ensemble.py:351), `AGGREGATION_THRESHOLD = 0.10` (:348),
  `min_signal_confidence = 0.30` (engine config untouched by the diff). The two
  new engine Settings fields default to the exact literals they replace (20.0,
  1.2).
- **`last_rejection` singleton hazard is contained.** The only production
  reader is `auto_trader.py:4783`, immediately after the synchronous
  `generate_signal` call with no `await` between call and read; `get_ensemble`
  is imported function-locally (:4656), so the funnel test's patch point is
  valid. The reset at the top of `generate_signal` (:736) plus the explicit
  clear before a successful return (:1045) close the cross-symbol staleness.
- **MTF demote flag is narrow and correctly ordered.** `demoted_to_hold` is
  computed from `consensus_action != HOLD and consolidated_action == HOLD`
  before the metadata write, and the regime hard-block runs after it; the
  narrowness guard test (`test_regime_hard_block_hold_is_not_recorded_as_an_mtf_demotion`)
  pins exactly that ordering. The ensemble gate is an identity check against
  `True` with malformed-value and non-dict degradation tests.
- **Diversity guard cross-references check out.** `RSI`, `BOLLINGER_BANDS`,
  `SMA` are exact members of `voter.INDICATOR_CATEGORIES` (identity-asserted,
  not copied); all eleven `mean_reversion` sub-signal tokens map under the
  three prefixes (the RSI branch is an `elif`, so two RSI tokens cannot
  co-occur and the "cannot be single-source" claim holds at
  `MIN_INDICATORS_ALIGNED = 2`).
- **Parameter single-sourcing is wired, not just de-literalled.** TA endpoints
  resolve Query defaults from Settings (main.py:344/362/467-470/568-570);
  constructor kwargs in `handlers/analysis.py` match the real constructor
  signatures (`bb_length`/`momentum_length` mapping verified); the
  moved-setting tests prove routing, not numeric agreement. The engine's
  `data.get("parameters", {})` echo is real — `MovingAverageResponse` carries
  `parameters={"period": period}`. No engine consumer read the removed
  `period`/`tenkan_period` metadata keys.
- **The causal-max fix is genuine and pinned.** `expanding().max()` is causal,
  `.iloc[-1]` consumers are unaffected, and `LEAK_PROBE_T = 242` keeps the
  measured defect visible. The tier-3 AST guard's fixtures prove both
  directions (no false positives, all six banned shapes, per-line marker).
- **Ablation harness is sound.** `_ensemble_stops_are_consistent` is a
  `@staticmethod`, so the unbound call is correct; `STATE_PATH` is repointed
  before any weights object is constructed; per-arm `importlib.reload` resets
  the patches; the patch-took assertions make a silently-unpatched arm fail
  loudly.
- Deploy coupling between the engine's param omission and TA's new defaults
  was handled — 21-09 rebuilt and force-recreated both services together.

No Critical findings. Two Warnings (a re-seeded stale balance literal in a new
test file; a NaN edge in the new ATR confidence clamp) and five Info items.

## Warnings

### WR-01: New test file re-seeds the stale `capital=100.0` balance literal the phase itself removed

**File:** `services/trading-engine/tests/strategies/test_ensemble_confidence_units.py:103,122,138,155,171,185,197`
**Issue:** Seven `generate_signal(..., capital=100.0)` call sites hardcode the
pre-ADR-029 $100 account size in a file created by this phase.
`.claude/rules/testing.md` is categorical ("Never write a test whose fixture
hardcodes **any** balance literal"), and P21-8 in this same phase deleted the
`capital: float = 100.0` production defaults for exactly this reason. Sibling
files written in the same phase do it right —
`test_ensemble_atr_levels.py:236` omits the argument with the comment
"Never write a balance literal", and `test_ensemble_diversity_guard.py` passes
`capital=None` throughout. The literal does not corrupt any current assertion
(capital does not enter the confidence math), but it is precisely the unrouted
value the account-size invariant exists to keep out, and it silently goes
stale on the next re-scale.
**Fix:**
```python
# In each of the seven call sites, replace
out = ens.generate_signal(_agg_signal(...), current_price=100.0, capital=100.0)
# with the Settings-resolved default, as the sibling tests do:
out = ens.generate_signal(_agg_signal(...), current_price=100.0, capital=None)
```

### WR-02: NaN wire confidence clamps to 1.0, not neutral, in the synthetic ATR indicator

**File:** `services/trading-engine/app/strategies/multi_strategy_ensemble.py:501-505`
**Issue:** `_atr_indicator` resolves `confidence = 0.5` when the wire value is
absent, then clamps with `confidence = max(0.0, min(1.0, confidence))`. If the
TA payload carries `"confidence": NaN` (a float, so `float(raw_confidence)`
does not raise), the clamp resolves to **1.0**: `min(1.0, nan)` returns `1.0`
because `nan < 1.0` is `False`, and `max(0.0, 1.0)` is `1.0`. A NaN reading —
the module's own doctrine treats NaN as "failed fetch" (`_atr_is_usable`:
"NaN fails both comparisons, which is the intended answer") — therefore
produces a full-confidence IndicatorSignal instead of the 0.5 neutral used for
absence. No current consumer reads the synthetic ATR's confidence (legs read
`.value` and metadata), so the impact today is latent, but the field is on the
signal path and the comment beside it claims the clamp exists so the wire is
not trusted.
**Fix:**
```python
raw_confidence = atr_data.get("confidence")
try:
    confidence = float(raw_confidence)
except (TypeError, ValueError):
    confidence = 0.5
if not (0.0 <= confidence <= 1.0):  # NaN fails this and takes the neutral path
    confidence = 0.5
```

## Info

### IN-01: Duplicate-label robustness claim in the causal-max fix is only half true

**File:** `services/technical-analysis/app/indicators/sqzmom_enhanced.py:980-985 (duration slice) vs :963-967, :1007-1010 (comments)`
**Issue:** The new comments justify positional indexing with "a label lookup
returns a Series rather than a scalar when the frame carries duplicate index
labels ... positional indexing has no index-shape dependency at all" — but two
lines above the fixed lookup, `calculate_row_confidence` still slices
`result_df.loc[:row.name, 'squeeze_on']` (and Step 6's `sqz_color` still does
`prev_momentum.loc[row.name]`). On a non-unique index the `.loc[:label]` slice
raises, the broad `except Exception` at the end of `calculate()` catches it,
and the whole indicator degrades to `None`. Pre-existing behavior, unique
indexes in practice — but the comment overstates the property the change
actually delivers.
**Fix:** Either convert the duration slice to positional
(`result_df['squeeze_on'].iloc[: position + 1]` — the position is already in
scope) or soften the comment to say the *momentum normaliser* is
index-shape-independent.

### IN-02: AST forward-read detector misses commutative index shapes

**File:** `services/technical-analysis/tests/test_leakage_regression.py:969-989`
**Issue:** `_forward_index_violation` matches only `ast.BinOp(Add)` with an
`ast.Name` on the **left** (`i + 1`). `series.iloc[1 + i]` and
`series.iloc[i - (-1)]` are the same forward read and pass the guard. Tier 3
is defense-in-depth behind tiers 1/2, and the six covered shapes are pinned by
fixtures, so this is a coverage note, not a hole in the live claim.
**Fix:** Also match `Add` with a `Name` on the right
(`isinstance(inner.right, ast.Name)`), and optionally `Sub` with a negative
constant operand.

### IN-03: UNKNOWN regime from an unmapped TA label still reports confidence 0.7

**File:** `services/trading-engine/app/handlers/signals.py:200-212`
**Issue:** When TA emits a label absent from `TA_REGIME_TO_ENGINE_REGIME`, the
handler logs and reports `regime="UNKNOWN"` — but returns it inside
`{"regime": regime, "adx": adx_value, "confidence": 0.7}`, the same 0.7 a real
classification gets, while the exception path uses 0.5. Downstream
`risk_confidence = market_regime.get("confidence", 0.5)` then weights an
unclassified read as a moderately confident one. Same doctrine as the
`adx: None` fix in the same function: an unknown should not carry a
measurement-grade confidence.
**Fix:** Return `confidence: 0.5` (or a named UNKNOWN constant) when the label
did not map.

### IN-04: Zero-score cancellation tests depend on the absolute weights file being absent

**File:** `services/trading-engine/tests/strategies/test_ensemble_confidence_units.py:132-141`; `services/trading-engine/tests/strategies/test_ensemble_diversity_guard.py:259-288,480-505`
**Issue:** The equal-and-opposite tests ("weights are deliberately NOT
pinned") require both legs at the 0.5 default win rate so the weighted score
nets to exactly zero. `StrategyPerformanceWeights.STATE_PATH` is the absolute
`/app/data/ensemble_weights.json`; the fixtures never repoint it (the ablation
script does). On any host where that path exists with drifted rates, the score
is nonzero and the tests fail — loudly, not silently, and trading-engine tests
are host-only per `.claude/rules/testing.md`, so this is environmental
fragility, not a correctness gap.
**Fix:** Repoint `StrategyPerformanceWeights.STATE_PATH` to a tmp_path in the
`ensemble_module` fixture, mirroring `ablation_ensemble_admission.py:378`.

### IN-05: "Errs strict" docstring does not cover the all-tokens-unmapped case

**File:** `services/trading-engine/app/strategies/multi_strategy_ensemble.py:89-95 (docstring) vs :581 (`return names or None`)`
**Issue:** `_mean_reversion_source`'s docstring says an unrecognised token is
dropped, "which is the safe direction" (strict). True for partial unmapping —
the category union shrinks. But when **every** token is unmapped,
`_leg_indicator_names` returns `names or None` → `None`, and the caller fails
**open**, skipping the guard entirely. That outcome is consistent with the
operator-ratified fail-open-on-unresolvable semantics and is caught at CI time
by `test_every_sub_signal_in_the_source_file_is_mapped`, but the docstring's
"errs strict" claim is not accurate for the total-unmapped edge.
**Fix:** One sentence in the docstring: "if no token maps, the leg's sources
are unresolvable and the caller fails open (see `_check_leg_source_diversity`)."

---

_Reviewed: 2026-08-27T13:15:23Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
