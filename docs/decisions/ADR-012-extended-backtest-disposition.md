# ADR-012: Disposition of run_extended_backtest.py Signal Divergence

**Status:** Accepted
**Date:** 2026-05-13
**Deciders:** Operator (solo-founder)
**Phase:** 05 (ml-cleanup-post-v0), Plan 04 (MLCL-04)
**Supersedes:** None — first formal decision on `run_extended_backtest.py` signal alignment.

> Note: This ADR is filed under `docs/decisions/` following the convention established by
> ADR-011 (also in `docs/decisions/`). The wiki copy is optional and deferred.

---

## Context

`services/trading-engine/run_extended_backtest.py` runs 90–180 day backtests over all active
trading symbols. Its signal generation path uses `HybridStrategyRouter` (trend-following +
mean-reversion fallback), while the live auto-trader uses `CoreAggregator`
(`app/aggregation/aggregator_core.py`) — a 9-indicator voting aggregator with:
- `TrendGatekeeper`: blocks counter-trend trades
- `VolumeValidator`: applies volume confidence penalty
- `SignalVoter`: weighted vote aggregation across 9 indicators
- `MarketRegimeDetector`: ADX-based regime confidence adjustment

These two decision surfaces diverge by design. A backtest "win rate" produced by
`run_extended_backtest.py` does NOT predict live win rate — the signal logic is different.

The original module docstring (lines 16-30, before this ADR) acknowledged this but used punt
language: "Fixing requires importing the live aggregator into the backtest path (high effort,
separate change)." That sentence was the SC-4 ambiguity violation per Phase 5 ROADMAP. SC-4
requires: "`run_extended_backtest.py` either uses the live `CoreAggregator` or its module
docstring + runtime warning permanently states the divergence with no further ambiguity."

Two options were analysed in `.planning/phases/05-ml-cleanup-post-v0/05-04-DECISION.md`:
- **Option A** — Rewrite to use `CoreAggregator` (medium-to-high effort, ~60% risk of
  sub-divergences from stateful dependencies: vol estimator, funding cache, maker queue).
- **Option B** — Document the divergence permanently + runtime warning (low effort, SC-4
  satisfied, no new code paths introduced).

---

## Decision

**Chosen disposition: `document_divergence_permanently`**

**Option B is chosen: document the divergence permanently.**

The divergence between `run_extended_backtest.py` and the live `CoreAggregator` is accepted
as a permanent architectural characteristic, not a temporary defect. The script is explicitly
designated as a **strategy regime characterisation tool**, not an edge-claim or live-PnL
forecasting tool.

Specific changes enacted (Phase 05, Plan 04):
1. The module docstring's "KNOWN LIMITATION" block is replaced with a "PERMANENT DIVERGENCE"
   block naming `CoreAggregator` by path, citing this ADR, and explicitly stating the
   divergence will not be fixed.
2. A `_emit_divergence_warning()` module-level function emits the mandatory runtime warning
   at the top of `main()`, before any expensive setup:
   `"RUN_EXTENDED_BACKTEST: signal logic diverges from live CoreAggregator — do NOT treat
   output as live-PnL forecast. See ADR-012."`
3. A pytest test (`test_run_extended_backtest_divergence_warning.py`, 5 tests) pins these
   invariants against future regression.

---

## Consequences

**Operator guidance — when to use each tool:**

| Use case | Tool |
|----------|------|
| Understand how HybridStrategyRouter behaves across market regimes | `run_extended_backtest.py` |
| Validate a strategy change before deploying to paper trading | `run_extended_backtest.py` |
| Measure edge (DSR/CPCV, bootstrap p-values, PSR gate) | Tournament harness (`scripts/tournament/`) |
| Pre-deploy sanity check: does the strategy produce profitable signals? | Tournament harness |
| Generate authoritative edge claims | Tournament harness ONLY |

**Positive consequences:**
- SC-4 is met: no further ambiguity about the script's purpose or limitations.
- The runtime warning ensures any operator running the script sees the limitation immediately.
- The pytest invariant prevents silent regression (e.g., a future contributor removing the
  warning or docstring marker without updating this ADR).
- Low effort: no new module dependencies, no new code paths.

**Accepted limitations:**
- The script's output remains NOT a reliable live-PnL forecast.
- If a future operator requires a live-aligned offline backtest, they must invest in option A
  (wire `CoreAggregator` offline with truthful or mocked stateful inputs) and supersede this
  ADR with a new decision document.

**Reversibility:** High. If option A is later chosen, edit the module docstring, update the
warning, replace `HybridStrategyRouter` invocations, and supersede this ADR.

---

## References

- Decision analysis: `.planning/phases/05-ml-cleanup-post-v0/05-04-DECISION.md`
- Tournament harness (authoritative evaluation path): `scripts/tournament/`
- Pytest invariant: `services/trading-engine/tests/test_run_extended_backtest_divergence_warning.py`
- SC-4 requirement source: `.planning/ROADMAP.md` Phase 05, Success Criteria SC-4
- Prior ADR: `docs/decisions/ADR-011-monitoring-disposition.md`
