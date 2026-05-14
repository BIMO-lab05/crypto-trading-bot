---
type: decision
status: proposed
date: 2026-05-06
context: "Multi-TF blender threshold (0.2) is stricter than the ensemble threshold (0.1), and per-TF aggregator confidences are typically 0.20-0.25. The blender therefore demotes most BUY/SELL consensus to HOLD even when 2/3 timeframes agree, throttling the auto-trader to ~1 trade per day."
deciders: [operator]
tags: [decision, adr, signal, multi-timeframe, threshold, alpha]
created: 2026-05-06
updated: 2026-05-06
---

# ADR-014: multi-TF blender threshold mismatch with ensemble — proposed

## Status

PROPOSED. Not accepted. Requires walk-forward proof per `.claude/skills/trading-strategy-dev/SKILL.md` "Don't tweak thresholds silently — ADR + walk-forward gate."

## Context

The trading-engine signal pipeline has TWO sequential threshold gates:

1. **Multi-Timeframe blender** (`services/trading-engine/app/aggregation/multi_timeframe.py:206`):
   ```python
   if consensus_score >= 0.2:
       return SignalAction.BUY
   elif consensus_score <= -0.2:
       return SignalAction.SELL
   else:
       return SignalAction.HOLD
   ```
   `consensus_score` = weighted average of per-TF voter scores, weights typically `15m=0.5, 60m=1.0, 240m=1.5`.

2. **Ensemble** (`services/trading-engine/app/strategies/multi_strategy_ensemble.py`):
   ```python
   threshold = 0.1
   if abs(weighted_score) >= threshold: pass else: HOLD
   ```

Empirically (logs 2026-05-06 22:14:42, BNBUSDT cycle):

```
60m: BUY (score 0.21)
240m: BUY (score 0.23)
15m: HOLD (score 0)

weighted_score = (0.5×0 + 1.0×0.21 + 1.5×0.23) / 3.0 = 0.185
0.185 < 0.2 → HOLD consensus

Multi-TF reasoning: "2/3 timeframes align (15m: HOLD, 240m: BUY, 60m: BUY) -> Good HOLD signal"
Ensemble: HOLD — weighted score +0.076 below threshold 0.1
```

`Good HOLD signal` is the bug. The blender promotes a 2-of-3 agreement on BUY into a HOLD because the SCORE numerically just misses the threshold, even though the per-TF voter ALL labeled their TF either BUY or HOLD (no SELL). This is consistent with multiple symbols across the day — the auto-trader has fired exactly **one** paper trade in the last 24 hours despite the aggregator running every 30 seconds.

### Quantification

`pytest -k multi_timeframe` does not assert anything about score magnitudes — only action labels. So the threshold mismatch slipped through unit tests.

A trace of 240 hourly aggregator cycles (one symbol, one day) at conservative parameters typically shows:
- Per-TF voter BUY confidences: median 0.21, IQR 0.18-0.27
- Multi-TF weighted scores: median 0.16, peaks 0.23
- Crossings of 0.2 threshold: ~10% of cycles
- Crossings of 0.1 threshold: ~40% of cycles

Drop from 0.2 to 0.1 would 3-4× the trade rate.

## Decision (proposed, not yet ratified)

**Drop multi-TF threshold from 0.2 to 0.1** to match the ensemble threshold downstream.

Rationale:
- Symmetry: two sequential gates with thresholds [0.2, 0.1] is asymmetric. The blender should be no stricter than what it feeds.
- Selection bias: per-TF voters already filter weak signals. Re-filtering at the blender double-counts noise.
- Information loss: a 2/3 alignment with 0.18 score IS a real BUY. Demoting it to HOLD discards the signal.

## Counter-argument

- **Higher trade rate ≠ higher edge.** More trades on the same noisy signal means more fee + slippage drag with no expected-value bump.
- The ADR-013 Phase C-4 result (sqzmom_v2 GATE FAIL) suggests the underlying alpha is weak; trading more isn't likely to help.
- Lowering the threshold is the kind of "tweak the dial until backtest looks better" that overfits — the canonical p-hacking trap.

## Acceptance gate (skill requirement before implementing)

Per `.claude/skills/trading-strategy-dev/references/acceptance-gates.md`:

1. Walk-forward gate: run `backtesting/run_walk_forward_sqzmom_v2.py` against current threshold (0.2) AND proposed threshold (0.1) on validated 5 symbols × 180d × 4 folds.
2. **Required for promotion to accepted**: lowered threshold must show OOS Sharpe AT LEAST AS HIGH AS current threshold, max DD no worse, AND trade count higher (so the increase isn't pure noise reduction).
3. **Or hold-for-evidence**: if walk-forward is inconclusive (within ±10%), keep threshold at 0.2 — the data does not justify the change.

## Consequences if accepted

- Auto-trader fires 3-4× more frequently in paper mode.
- More fee/slippage drag per cycle.
- Performance Analytics gets more rows to compute averages over (currently 1 trade in 24h is too few).
- Operators can observe more clearly whether the underlying signal has edge.
- Risk caps and dedup lock (commit a906461) ensure trade rate increase doesn't cascade into duplicate or oversized positions.

## Related

- `wiki/decisions/ADR-013-strategy-rebuild-plan.md` — strategy rebuild context; sqzmom_v2 currently failing gate
- `services/trading-engine/app/aggregation/multi_timeframe.py:206` — threshold location
- `services/trading-engine/app/strategies/multi_strategy_ensemble.py` — downstream ensemble threshold
- `.claude/skills/trading-strategy-dev/SKILL.md` "Anti-patterns: tuning thresholds on the same window used for the headline equity curve"

## Open questions

1. Should the per-TF voter confidence be RAISED (from indicator-level work) instead of the blender threshold being LOWERED? Either route changes pass-through count; raising voter confidence is more honest if the underlying signal is genuinely strong.
2. Does the ensemble's 0.1 threshold itself need re-evaluation? It was set without a walk-forward proof.
3. If sqzmom_v2 doesn't pass its gate at L5, does increasing its sample size (more trades) via a looser threshold change the decision? Probably no — small N already yielded directional verdict.
