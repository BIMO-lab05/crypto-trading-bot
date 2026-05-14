---
type: decision
status: accepted
date: 2026-05-08
context: "Hardcoded ensemble sizing constants ignored ADR-010 paper risk bump; live trades clustered at 1-3% of capital instead of approaching the 10% cap operator approved."
deciders: [operator]
tags: [decision, adr, sizing, ensemble, paper-trading]
created: 2026-05-08
updated: 2026-05-08
---

# ADR-015: ensemble sizing cascade bound to settings

## Context

Live DB (2026-05-07) shows 31 paper trades / 14h with notional clustered at 1.5–1.7 % of the $98 cash balance — far below the 10 % per-trade cap [[ADR-010-max-risk-per-trade-paper-bump|ADR-010]] approved.

Root cause: `services/trading-engine/app/strategies/multi_strategy_ensemble.py` carried three hardcoded constants that shadowed the operator-set cap:

```python
MAX_POSITION_PCT = 0.10   # class constant — frozen at 10%
position_size_pct = max(0.01, min(MAX_POSITION_PCT, confidence * MAX_POSITION_PCT * 1.5))
                         ^^^^                                                  ^^^
                         floor                                              multiplier
```

With observed ensemble confidence (0.05 – 0.20) and the documented ceiling at ~0.27 (per [[ADR-013-strategy-rebuild-plan|ADR-013]] §7), the formula required confidence ≥ 0.67 to reach the cap — a value the ensemble cannot produce. The ceiling therefore ALWAYS bound at the floor (1 %) or just above.

Cap was operator-tunable via `MAX_RISK_PER_TRADE` env, but ensemble didn't read it. Cascade was invisible.

## Decision

1. Remove `MAX_POSITION_PCT` class constant. Replace with a property bound to `settings.max_risk_per_trade`.
2. Expose floor and confidence multiplier as settings:
   - `ensemble_min_position_pct: float = 0.05` (was hardcoded 0.01)
   - `ensemble_confidence_size_multiplier: float = 3.7` (was hardcoded 1.5)
3. Default multiplier 3.7 chosen so confidence at the documented ensemble ceiling (≈ 0.27) sizes the trade at the cap: `0.27 × 0.10 × 3.7 ≈ 0.10`.
4. Default floor 0.05 ensures a fired trade is meaningful at $100 paper balance ($5 not $1) and clears Bybit per-symbol min-notional for validated symbols.

Resulting sizing curve at default settings:

| Confidence | Size |
|------------|------|
| ≤ 0.135 | 5.00 % (floor) |
| 0.15 | 5.55 % |
| 0.20 | 7.40 % |
| 0.25 | 9.25 % |
| 0.27 | 9.99 % |
| ≥ 0.27 | 10.00 % (cap) |

LIVE-mode honour confirmed: setting `max_risk_per_trade=0.02` returns trades at 2 % cap (test `test_ensemble_cap_from_settings_overrides_class_constant`).

## Consequences

- **Auto-trader paper trades will size 5–10 % notional going forward.** Daily-loss-rate per losing trade rises ~3-5×.
- **5 % daily-loss circuit-breaker [[Risk-Model|Risk Model]] is now load-bearing**, since it bounds the worst-case session loss. A run of losing trades at 5–10 % size will hit the circuit-breaker materially faster than at 1 % — *which is the design*, not a bug.
- **Per [[ADR-013-strategy-rebuild-plan|ADR-013]] Phase C, the live ensemble has no proven edge** (sqzmom_v2 walk-forward FAIL 5/5). Sizing up an unedged strategy bleeds faster. Operator accepted this tradeoff for paper-mode signal density per ADR-010.
- **Pre-LIVE checklist must restore `max_risk_per_trade ≤ 0.02` AND verify `ensemble_min_position_pct ≤ 0.005`** (else floor would breach the 2 % LIVE cap).
- **No walk-forward gate run** for this change. Justification: this is an architectural binding fix that makes operator-approved cap actually take effect, not a sizing alpha experiment. The behavioural effect (5 %, not 1 %, floor) IS the operator's stated intent in ADR-010.

## Alternatives considered

- **Just bump the class constant.** Rejected — same shadowing problem next time the operator changes the cap.
- **Remove the floor.** Rejected — at typical conf 0.10, sizing would land at 3.7 %, which is meaningful but inconsistent. A 5 % floor on every fired trade is cleaner.
- **Walk-forward gate before shipping.** Rejected for this change: no edge known to exist either way (ADR-013 Phase C established the negative result). Walk-forward would only confirm faster bleed, not unlock alpha. Architectural correctness ships now; further sizing-knob experiments stay gated by the skill rule.

## Files touched

- `services/trading-engine/app/config.py` — added `ensemble_min_position_pct`, `ensemble_confidence_size_multiplier`.
- `services/trading-engine/app/strategies/multi_strategy_ensemble.py` — removed `MAX_POSITION_PCT` constant, replaced with property reading `settings.max_risk_per_trade`; sizing formula reads all three knobs from settings.
- `services/trading-engine/tests/strategies/test_multi_strategy_ensemble_sizing.py` — TDD coverage of cap, floor, multiplier, default-calibration, LIVE cap-honour.

## Related

- [[ADR-010-max-risk-per-trade-paper-bump]] — cap value (10 % paper, 2 % LIVE)
- [[ADR-011-paper-deterministic-execution]] — paper P&L caveat (no slippage / fees / funding)
- [[ADR-013-strategy-rebuild-plan]] — no-edge result that contextualises this change
- [[ADR-014-multi-tf-blender-threshold-mismatch]] — unrelated MTF gate (still proposed)
- [[../concepts/Risk-Model]]
- [[../modules/trading-engine]]

## Open questions

1. Should `ensemble_confidence_size_multiplier` be auto-calibrated from observed confidence percentiles instead of hardcoded 3.7? Defer until indicator-confidence-calibration audit completes (ADR-013 Phase B item).
2. Should LIVE mode auto-clamp `ensemble_min_position_pct` to `0.5 × max_risk_per_trade` to avoid pre-live-checklist drift? File a separate ADR if/when LIVE is enabled.
