# 05-04-DECISION.md: Disposition of run_extended_backtest.py Signal Divergence

**Plan:** 05-04 (MLCL-04)
**Date:** 2026-05-13
**Status:** Decided — `document_divergence_permanently` (pre-confirmed by operator)
**Binding on:** Task 2 execution

---

## Context

`services/trading-engine/run_extended_backtest.py` runs 90–180 day backtests over all active
symbols. Its module docstring (lines 16-30) already acknowledges a "KNOWN LIMITATION": the
script uses `HybridStrategyRouter` (trend-follow + mean-reversion fallback) as its signal
source, while the live auto-trader uses `CoreAggregator` (9-indicator voting aggregator with
`TrendGatekeeper`, `VolumeValidator`, `SignalVoter`, and ADX-based `MarketRegimeDetector`).
The two are different decision surfaces — backtest PnL here does NOT predict live win rate.

**SC-4 (Phase 5 ROADMAP):** "`run_extended_backtest.py` either uses the live `CoreAggregator`
or its module docstring + runtime warning permanently states the divergence with no further
ambiguity."

**The SC-4 ambiguity violation is explicit:** line 26-27 currently reads:
> "Fixing requires importing the live aggregator into the backtest path (high effort, separate
> change)."

This punt language ("Fixing requires ... separate change") is the precise violation. It implies
the divergence is a temporary TODO rather than a deliberate architectural choice, leaving any
operator reading the output uncertain whether the numbers will eventually become trustworthy
for live-PnL forecasting.

**Alternate honest-evaluation path exists:** Phase 3+4 shipped the tournament harness
(`scripts/tournament/`, `tests/integration/test_tournament_harness.py`). The harness runs
walk-forward CPCV backtests with bootstrap p-values, PSR/DSR gates, and Sharpe corrected for
multiple testing. It is the authoritative edge-measurement tool. Any operator who needs a
reliable live-PnL forecast should use the tournament harness, not `run_extended_backtest.py`.

---

## Options Analysis

### Option A — Rewrite run_extended_backtest.py to use CoreAggregator

**What specifically gets edited:**
- Replace `from app.strategies.hybrid_strategy_router import HybridStrategyRouter, MarketRegime`
  with `from app.aggregation.aggregator_core import CoreAggregator` plus `Settings`.
- Replace the per-bar `self.hybrid_strategy.generate_signal(...)` call with
  `CoreAggregator(settings).aggregate(indicators)`.
- Wire all stateful inputs `CoreAggregator` expects: vol estimator state, funding rate cache,
  maker quote queue, historical signal voter state — either replayed from historical data or
  mocked with explicit comments.

**Cost in implementation effort:**
Medium-to-high. `CoreAggregator.__init__` instantiates `TrendGatekeeper`, `VolumeValidator`,
`SignalVoter`, `MarketRegimeDetector`, `Phase1MetricsProvider`, and `SignalCache`. Several of
these have implicit live dependencies (e.g., `get_settings()` pulls env vars from running
services). The offline backtest has no funding rate history and no maker order queue. Wiring
those offline is 100–200 lines of additional scaffolding that would need its own tests and
would be the most complex code in the backtest harness.

**Value to the operator:**
High — if completed correctly, the backtest output would finally be comparable to live
trading behaviour. Every `run_extended_backtest.py` run would serve as a genuine pre-deploy
sanity check.

**Risk of follow-up plans:**
Medium. `CoreAggregator` has a `Phase1MetricsProvider` dependency that writes to PostgreSQL.
Offline operation would require mock injection. If funding-gate or vol-estimator state
cannot be faithfully replicated offline, a residual sub-divergence emerges that needs its own
DECISION.md. Probability of sub-divergence: ~60%.

**Reversibility:**
Low reversibility — once the rewrite lands, rolling back means reinstating `HybridStrategyRouter`
as the primary path, which would re-create the current documentation confusion.

---

### Option B — Document the divergence permanently + runtime warning + sharper docstring

**What specifically gets edited:**
- Replace the punt language at lines 16-30 of `run_extended_backtest.py` with an explicit
  `PERMANENT DIVERGENCE` framing that names `CoreAggregator` by path, cites `ADR-012`, and
  states the divergence is intentional and will not be fixed.
- Replace the existing `logger.warning(...)` in `main()` with the mandated message:
  `"RUN_EXTENDED_BACKTEST: signal logic diverges from live CoreAggregator — do NOT treat
  output as live-PnL forecast. See ADR-012."`
- Write `docs/decisions/ADR-012-extended-backtest-disposition.md` to codify the choice.
- Write a pytest invariant (5 tests) that asserts the marker strings are present and the
  runtime warning fires — pinning the contract against future regression.

**Cost in implementation effort:**
Low. ~30-40 lines of docstring edit + 1 log statement + ADR + test file. Estimated 45 minutes
of work total. No new module dependencies.

**Value to the operator:**
Medium. The divergence is made unambiguous and loud. Any operator who runs the script sees
the warning immediately. The SC-4 requirement is satisfied. However, the output of the script
is still NOT a reliable live-PnL forecast — that limitation is documented but not fixed.

**Risk of follow-up plans:**
Low. No new code paths; no new external dependencies. The pytest invariant prevents silent
regression. The tournament harness remains the authoritative evaluation path.

**Reversibility:**
High reversibility — if the operator later decides to invest in the option A rewrite, the
docstring is edited again, the warning is updated, and ADR-012 is superseded.

---

## Decision: document_divergence_permanently

**Option B is chosen.** The divergence will be documented permanently with an unambiguous
`PERMANENT DIVERGENCE` marker, a named reference to `CoreAggregator` at
`app/aggregation/aggregator_core.py`, a runtime `logger.warning(...)` that fires on every
script execution, and an ADR codifying the disposition.

---

## Rationale

1. **The tournament harness already exists as the honest-evaluation path.** Phase 3+4 shipped
   walk-forward CPCV evaluation with bootstrap p-values and PSR/DSR gates. That is the
   tool operators should use for edge claims. Rewriting `run_extended_backtest.py` to use
   `CoreAggregator` would duplicate this evaluation path at significant cost.

2. **SC-4 is about eliminating ambiguity, not about fixing the divergence.** The requirement
   is: "either uses the live CoreAggregator OR its module docstring + runtime warning
   permanently states the divergence with no further ambiguity." Option B fully satisfies
   SC-4 at low cost, while option A satisfies it at high cost with non-trivial risk of
   introducing sub-divergences that generate new ambiguity.

3. **The current script's use case is strategy regime characterisation, not edge measurement.**
   Operators running it want to understand how `HybridStrategyRouter` behaves across market
   regimes — trending vs ranging, win rate distribution by strategy type. This is a legitimate
   use case that does not require `CoreAggregator` alignment. Making that use case explicit
   (rather than an implicit consequence of a divergence) is the correct framing.

4. **Cost/risk discipline.** CLAUDE.md "Verification standards" disallows declaring a feature
   "working end-to-end" on shallow evidence. Option A's ~60% risk of sub-divergence would
   produce a script that falsely signals live alignment while hiding residual mismatches in
   mocked state — a worse outcome than the current honest divergence.

---

## Implementation Notes (Task 2 will execute these)

**File: `services/trading-engine/run_extended_backtest.py` — docstring replacement**

Replace the `KNOWN LIMITATION` block (lines 16-30) with:

```
============================================================================
!!! PERMANENT DIVERGENCE — READ BEFORE TRUSTING ANY PnL OUTPUT !!!
============================================================================

This script intentionally uses HybridStrategyRouter (trend-follow +
mean-reversion fallback), NOT the live CoreAggregator
(app/aggregation/aggregator_core.py). The live auto-trader routes signals
through CoreAggregator with TrendGatekeeper, VolumeValidator, SignalVoter,
and ADX-based MarketRegimeDetector. The two decision surfaces diverge by
design.

PERMANENT DIVERGENCE — This will not be fixed. See ADR-012 for rationale.

Use this script for: strategy regime characterisation only (how does
HybridStrategyRouter behave across trending vs ranging markets?).
Do NOT use this script for: live-PnL forecasting, edge-claim validation,
or pre-deploy sanity checks. Use the tournament harness
(scripts/tournament/) for authoritative edge measurement.
============================================================================
```

**File: `services/trading-engine/run_extended_backtest.py` — runtime warning**

At the TOP of `main()`, before any setup or loop, replace the existing `logger.warning(...)`:

```python
logger.warning(
    "RUN_EXTENDED_BACKTEST: signal logic diverges from live CoreAggregator "
    "— do NOT treat output as live-PnL forecast. See ADR-012."
)
```

**File: `docs/decisions/ADR-012-extended-backtest-disposition.md`**

Standard ADR: Title, Status (Accepted 2026-05-13), Context, Decision, Consequences,
Reference to this DECISION.md and the tournament harness.

**File: `services/trading-engine/tests/test_run_extended_backtest_divergence_warning.py`**

5 tests:
1. No SC-4 punt language: `grep -E "Fixing requires|separate change"` returns zero matches.
2. Permanence marker present: `grep -F "PERMANENT DIVERGENCE"` returns >= 1 match.
3. CoreAggregator referenced: `grep -F "CoreAggregator"` returns >= 1 match.
4. ADR reference present: `grep -F "ADR-012"` returns >= 1 match.
5. Runtime warning fires: import `_emit_divergence_warning` helper from the module; call it
   under `caplog` fixture; assert "RUN_EXTENDED_BACKTEST" and "diverges from live CoreAggregator"
   appear in captured log output.
