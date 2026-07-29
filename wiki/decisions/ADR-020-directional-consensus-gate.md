---
type: decision
status: accepted
date: 2026-07-28
context: "min_consensus counted HOLD votes toward a directional trade; MACD params drifted from the TA service default"
deciders: [operator]
tags: [decision, adr, signal, aggregator, consensus]
created: 2026-07-29
updated: 2026-07-29
---

# ADR-020: directional-consensus gate + MACD default aligned to TA 5-35-5

## Context

The `CoreAggregator` consensus gate (`min_consensus=3`) used `consensus_count = max(buy_count, sell_count, hold_count)` returned by the voter. For a directional (BUY/SELL) trade, HOLD votes were being counted toward "consensus" — a BUY backed by only 2 indicators could pass the 3-indicator requirement because 3 *other* indicators voted HOLD. The gate meant to protect against thin agreement was letting thin agreement through.

Separately, the trading-engine's MACD client forced `8/17/9` while the technical-analysis service default is the Kang-2021 `5/35/5`, so the aggregator scored MACD on different parameters than the TA service published — silent parameter drift.

## Decision

- **Consensus counts only indicators voting the CHOSEN direction.** After the action is determined, `consensus_count` is reassigned to `buy_count` for BUY or `sell_count` for SELL before the `>= min_consensus` check. HOLD votes no longer count toward a directional trade. `aggregation/aggregator_core.py:314-332`.
- **Confidence is agreement-based, not `|weighted_score|`.** BUY/SELL confidence is overridden with `compute_agreement_confidence` = (Σ weight·conf of *agreeing* indicators) / (Σ weight of all voting indicators), a value in `[0,1]` with a realistic 0.3–0.8 spread. The legacy `|weighted_score|` metric was structurally capped by average indicator confidence, making the 0.30 floor unreachable (5+ months of zero fills). `aggregation/voter.py:298-359`, override at `aggregator_core.py:228-245`.
- **MACD uses the TA service default.** The MACD client stops sending `fast/slow/signal`, deferring to the TA service's research-optimized `5/35/5` as the single source of truth. `signal_aggregator.py:104-140`; TA default `technical-analysis/app/config.py:71-81`.

## Consequences

- A directional signal now requires ≥ 3 indicators actually voting *that* direction, plus ≥ 0.30 agreement-weighted confidence, plus category diversity and the trend/regime blocks.
- The confidence floor is finally meaningful (quality gate that bites without being unreachable).
- MACD scoring matches published TA output; no more parameter drift between services.

## Related

- `services/trading-engine/app/aggregation/aggregator_core.py:290-376`
- `services/trading-engine/app/aggregation/voter.py:145-359`
- `services/trading-engine/app/signal_aggregator.py:104-140`
- `services/technical-analysis/app/config.py:66-81`
- [[ADR-014-multi-tf-blender-threshold-mismatch]]
- [[ADR-015-ensemble-sizing-cascade]]
- [[../flows/Signal-Pipeline]]
