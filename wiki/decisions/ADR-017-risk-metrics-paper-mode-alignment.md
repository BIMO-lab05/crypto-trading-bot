---
type: decision
status: accepted
date: 2026-05-19
context: "risk-metrics CB false-tripped every loop in paper mode because its position/exposure thresholds were sized for the pre-ADR-010 2%/trade era"
deciders: [operator]
tags: [decision, adr, risk, paper-trading, circuit-breaker]
created: 2026-05-19
updated: 2026-08-25
---

# ADR-017: risk-metrics-service defaults aligned with paper-mode operating range

> [!note] Restated ADR-010 rationale superseded by [[ADR-029-account-size-10k-research-scale|ADR-029]] (2026-08-25)
> This ADR's context restates ADR-010's min-notional-on-$100 justification, which is obsolete at the declared $10,000 research scale. The threshold alignment it decided (position 0.10, exposure 0.50) is percent-based and carries over unchanged. Body text below is the historical record at $100 — do not update its figures.

## Context

`ADR-010` (2026-05-06) relaxed trading-engine paper-mode `max_risk_per_trade`
from 2% to 10% so a $100 paper balance could clear Bybit's per-symbol minimum
notionals and produce a measurable PnL distribution. `ADR-015` (2026-05-07)
documented the ensemble sizing cascade that produces 5–10% positions per
symbol given the new per-trade cap. With 5 validated symbols
(BTC/ETH/SOL/BNB/ADA) active, expected paper-mode gross exposure under
normal operation is 25–50%.

risk-metrics-service was never aligned to this. It kept the pre-ADR-010
defaults:

| Setting | Old default | Implied limit | Aligned with |
|---|---|---|---|
| `max_position_size` | 0.02 | 2%/position alerts as concentrated | pre-ADR-010 per-trade cap |
| `max_exposure` | 0.20 | 20% gross | pre-ADR-010 risk budget |
| `circuit_breaker_exposure_multiplier` | 1.2 | CB trips at 24% gross | (unchanged) |

Observed on 2026-05-19: with the bot un-paused and 5 ensemble-sized positions
open (~6.4% each, 32.5% gross), the CB tripped every loop with reason
`Exposure 32.52% critically high (limit: 24%)`. Each individual position
also flagged as "concentrated" (6.4% > 2% alert threshold). Both alerts were
real-but-misleading: the positions were within the per-trade cap that
trading-engine and ADR-010 explicitly allow.

The fix for the daily-loss leg of the same CB trip was committed
separately (commit `ba39507`, scale + metric correction on the
`/circuit-breaker` route handler). This ADR covers the **policy** half:
which numeric thresholds the CB should enforce.

## Decision

`services/risk-metrics-service/app/config.py` defaults bumped to match the
paper-mode operating range:

| Setting | Old | New | Rationale |
|---|---|---|---|
| `max_position_size` | 0.02 | **0.10** | Concentration alert at the same 10% per-trade cap trading-engine enforces. Anything ≤ cap is "not concentrated" by policy. |
| `max_exposure` | 0.20 | **0.50** | Supports normal 5-symbol × 10% per-trade operation with headroom. CB trips at `max_exposure * 1.2 = 0.60` (60% gross). |

`circuit_breaker_exposure_multiplier` stays at 1.2 — the safety-net buffer
between "operating range" and "runaway exposure" should still allow ~20%
slack before the CB fires. Settings remain in `pydantic_settings.BaseSettings`
so they read `MAX_POSITION_SIZE` and `MAX_EXPOSURE` from the environment
case-insensitively.

For **LIVE mode**, the pre-live operational checklist must set the env vars
back to the pre-relaxation values (matching ADR-010's LIVE per-trade cap):

```bash
MAX_POSITION_SIZE=0.02    # 2% per-position alert (matches LIVE per-trade cap)
MAX_EXPOSURE=0.20         # 20% gross (matches tighter live risk budget)
```

These belong on the same checklist row as `MAX_RISK_PER_TRADE=0.02` from
ADR-010. The trading-engine LIVE-boot guard (`LIVE_TRADING_ACK`,
`PAPER_TRADING_MODE=false`, `TRADING_MODE=LIVE`) does not currently enforce
risk-metrics env overrides, so this is operator discipline until a
dedicated LIVE-boot validator is wired up across services.

## Consequences

- CB no longer false-trips on normal paper-mode operation
  (verified 2026-05-19 14:55 UTC: CB CLOSED, can_trade=true, exposure 32.4%
  well below new 60% trip threshold). Auto-trader can now run uninterrupted
  during a single armed session.
- Safety net is preserved: 70% gross still trips the CB
  (regression test in `tests/test_circuit_breaker_route.py`).
- Tests anchored to the old literal thresholds were updated in the same
  change (`tests/test_risk_engine.py`,
  `tests/test_circuit_breaker_state_machine.py`).
- LIVE-mode operators **must** override these env vars when flipping to
  LIVE; otherwise risk-metrics will treat a $1000 single position as
  acceptable on a $10k live account, which violates the 2% LIVE cap. This
  is a new pre-live checklist line.

## Related

- `services/risk-metrics-service/app/config.py:23-39`
- `services/risk-metrics-service/app/risk_engine.py:80-148` (capital + exposure metrics)
- `services/risk-metrics-service/app/risk_engine.py:715-731` (CB trip logic)
- `services/risk-metrics-service/tests/test_circuit_breaker_route.py` (regression coverage)
- ADR-010 max-risk-per-trade-paper-bump (trigger for this realignment)
- ADR-015 ensemble-sizing-cascade (defines the sizing formula whose output
  determines normal gross exposure)
- CLAUDE.md § Project rules (per-trade caps + pre-LIVE checklist)
