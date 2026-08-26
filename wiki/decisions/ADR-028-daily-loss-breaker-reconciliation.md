---
type: decision
title: "ADR-028: Reconcile the Daily-Loss Breaker with the ADR-010 Per-Trade Cap"
status: accepted
created: 2026-08-03
updated: 2026-08-25
tags: [decision, adr, risk, trading-engine, kill-switch, capital]
---

# ADR-028: Reconcile the Daily-Loss Breaker with the ADR-010 Per-Trade Cap

> [!note] Re-affirmed by [[ADR-029-account-size-10k-research-scale|ADR-029]] at $10,000 (2026-08-25)
> The 12%-day / 10%-trade geometry carries over unchanged to the new research scale: **$1,200/day against $1,000/trade** — the same one-full-loss-arms-the-breaker shape, deliberately kept. This ADR's closing line ("Revisit this ADR at whatever equity LIVE is actually attempted") is satisfied by ADR-029. Body text below is the historical record at $100 — do not update its figures.

**Status:** Accepted
**Date:** 2026-08-03
**Deciders:** Operator (solo-founder)
**Context:** Quick task `260803-4mt`, recovery-plan P1 step 5
**Evidence:** [[../../.planning/audits/2026-08-03-capital-audit|Capital audit 2026-08-03]] (Verification Addendum §A5)
**Relates to:** ADR-010 (paper per-trade cap relaxed to 10%)

## Context

The capital audit found the daily-loss circuit breaker and the per-trade cap were never reconciled after [[ADR-010-max-risk-per-trade-paper-bump|ADR-010]] raised the paper per-trade cap from 2% to 10% to clear Bybit's minimum notional on a $100 balance.

Effective configuration as found:

| Field | `config.py` | Unit | Env key read | Effective |
|---|---|---|---|---|
| `max_risk_per_trade` | :321 default `0.10` | **fraction** | `MAX_RISK_PER_TRADE` | 10% = **$10/trade** |
| `max_daily_loss_pct` | :364 default `5.0` | **percent** | `MAX_DAILY_LOSS_PCT` | 5% = **$5/day** |

A single maximally-sized losing trade (−$10) exceeded the whole daily allowance ($5). The breaker therefore measured **one trade**, not a day.

Two independent config faults compounded this:

1. **`.env` set `MAX_DAILY_LOSS=0.10`, which was dead twice over.** The field reads `MAX_DAILY_LOSS_PCT`, not `MAX_DAILY_LOSS`, so `extra="ignore"` swallowed it; and `0.10` would have failed the field's `ge=1.0` bound even under the correct name. **The operator's intended 10% daily limit had never been in effect at any point.**
2. **`docker-compose.unified.yml` did not pass `MAX_DAILY_LOSS_PCT` to trading-engine at all.** The container fell back to the `config.py` default regardless of `.env`. `MAX_TOTAL_EXPOSURE_PCT` was likewise unpassed (default `80.0`), while the incomplete `docker-compose.yml:325` said `70.0` — a divergence that made the newly-derived kill-switch `max_position_value` depend on which compose file and which working directory were in play.

## Decision

**Raise the daily-loss limit to 12% and keep the per-trade cap at 10%.**

- `Settings.max_daily_loss_pct` default `5.0` → `12.0` (`config.py`)
- `shared.account.DEFAULTS["MAX_DAILY_LOSS_PCT"]` `5.0` → `12.0`
- `KillSwitchConfig.max_daily_loss_pct` default `5.0` → `12.0` (bare-construction path only; `auto_trader.py:343` passes the Settings value)
- `docker-compose.unified.yml` now passes `MAX_DAILY_LOSS_PCT=${MAX_DAILY_LOSS_PCT:-12.0}` and pins `MAX_TOTAL_EXPOSURE_PCT=${MAX_TOTAL_EXPOSURE_PCT:-80.0}`

On the $100 paper account this is **$12/day against $10/trade** — the breaker fires on roughly two full losers rather than one, and the $10 per-trade budget still clears the ~$5 Bybit minimum notional.

## Consequences

**This ALLOWS MORE daily loss than before ($5 → $12). It is a coherence fix, not a tightening.** The prior 5% behaved as an over-conservative single-trade stop rather than as a daily budget. That was not unsafe — it halted early — but it did not do the job a daily breaker exists to do, and it made the breaker's stated purpose untrue.

Positive:
- The daily breaker now measures a day.
- `shared.account.capital_config_warnings()` no longer reports `RISK CAP CONFLICT` (`0.10 > 0.12` is False), so the warning channel stays meaningful instead of always-on.
- The container's effective values no longer depend on which compose file or working directory is used.

Negative / accepted risk:
- Maximum modelled daily drawdown on the paper account rises from 5% to 12%.
- 12% remains far above the LIVE-strict 2% per-trade cap. **This decision is scoped to paper mode only.**

## Pre-LIVE requirement

`LIVE_MAX_RISK_PER_TRADE = 0.02` is unchanged and non-negotiable. Before `TRADING_MODE=LIVE`, both caps must be re-derived together — a 2% per-trade cap on a $100 account is $2, which cannot clear Bybit's minimum notional at any sane stop distance, so **live trading is not mechanically viable at this account size regardless of edge.** Revisit this ADR at whatever equity LIVE is actually attempted.

## Operator action still outstanding

`.env` is gitignored and operator-owned; this session's sandbox blocks writes to `.env*`, so it was not modified. Remove the dead key and set the real one:

```diff
- MAX_DAILY_LOSS=0.10
+ MAX_DAILY_LOSS_PCT=12.0
```

Without this the code default (`12.0`) applies anyway — the edit exists to stop the dead key misleading the next reader. `.env.example` still carries the same dead `MAX_DAILY_LOSS` key for the same sandbox reason.
