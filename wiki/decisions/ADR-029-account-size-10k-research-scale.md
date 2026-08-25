---
type: decision
title: "ADR-029: Account Size $10,000 (Research Scale); Risk Knobs Retained"
status: accepted
created: 2026-08-25
updated: 2026-08-25
tags: [decision, adr, capital, risk, trading-engine, backtesting]
---

# ADR-029: Account Size $10,000 (Research Scale); Risk Knobs Retained

**Status:** Accepted
**Date:** 2026-08-25
**Deciders:** Operator (solo-founder)
**Context:** Operator-approved design `docs/superpowers/specs/2026-08-25-account-10k-flip-design.md`
**Relates to:** ADR-010 (supersedes its rationale), ADR-015 (floor rationale obsolete), ADR-017 (restated rationale obsolete), ADR-028 (re-affirmed at the new size)

## Context

The account was declared **$100 USDT** (2026-08 campaign; `shared/account.py` as declaration of record). At that size:

- Bybit's ~$5 minimum notional forced ADR-010 to relax the paper per-trade cap from 2% to 10% just to make trades executable ($10 > $5).
- BTC/ETH were structurally untradeable (BTC minimum position ≈ $77 against a $10 cap); the tradeable set collapsed to SOL/BNB/ADA.
- LIVE trading was arithmetically impossible (2% of $100 = $2 < $5 floor), and docs used that arithmetic as a safety argument.
- Strategy measurements were dominated by a floor constraint that exists at no realistic account size.

The operator chose to re-scale to **$10,000, paper-only research scale**: remove the min-notional distortion and re-measure everything at a size where percent-based risk knobs actually express themselves.

## Decision

1. **`PAPER_INITIAL_BALANCE` (and `ACCOUNT_EQUITY_USD`) = 10000.0.** `shared/account.py` remains the sole declaration of record; trading-engine `Settings`, portfolio-manager `INITIAL_CAPITAL`, compose/k8s env, and the frontend fallback all follow it.
2. **Risk knobs are retained unchanged, now as deliberate operator choice, not a workaround:**

   | Knob | Value | At $10,000 |
   |---|---|---|
   | `max_risk_per_trade` (fraction) | 0.10 | $1,000/trade |
   | `max_daily_loss_pct` (ADR-028) | 12.0 | $1,200/day |
   | `max_position_size_pct` | 10.0 | $1,000/position |
   | `ensemble_min_position_pct` (ADR-015) | 0.05 | $500 floor |
   | `LIVE_MAX_RISK_PER_TRADE` | 0.02 | $200 — **untouched, non-negotiable** |

   ADR-010's *rationale* (clear min-notional on $100) is dead; its *value* survives by choice: aggressive paper sizing produces more P&L signal per day. ADR-028's one-full-loss-nearly-arms-the-breaker geometry ($1,000 trade vs $1,200 day) is knowingly kept.
3. **The no-literal rule survives with inverted polarity.** A bare `10000` in code is now *numerically correct and still a defect* — it bypasses the declared config and silently decouples on the next re-scale. `tests/test_account_size_invariant.py` now polices `100.0` as the stale value; `scripts/check_capital_literals.py` keeps rejecting `10000` literals near capital names.
4. **Fresh paper baseline.** DB reseeded at $10,000 (portfolios row + cash ledger), prior trades archived — executed after the 2026-08-27 isolation-run harvest, never mid-window.

## Consequences

- **LIVE safety argument changes shape.** 2% of $10,000 = $200 clears every venue minimum: LIVE is no longer arithmetically blocked. The ONLY barrier is the four deliberate flags (`PAPER_TRADING_MODE=false`, `TRADING_MODE=LIVE`, mainnet trade-permission keys, `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`). No document may present account arithmetic as a LIVE safeguard anymore.
- **BTC/ETH re-enter the mechanically tradeable set** ($1,000 cap vs BTC ≈ $77 minimum). The SOL/BNB/ADA-only conclusion (FUNNEL_REPORT 2026-08) is void pending re-derivation.
- **Edge is unchanged.** Fees and slippage are bps of notional; strategies with negative net Sharpe at $100 remain negative at $10,000. This flip buys *measurement fidelity*, not profit.
- **All pre-2026-08-25 evidence answers a $100 question** (and pre-2026-08-03 figures a frictionless-$10,000 question). Backtests/walk-forwards must be re-run before citing; the validation battery accompanying this ADR provides the first $10,000-scale, slippage-on baselines.
- Min-notional rejection logic (reject, never clamp up) is retained but is no longer exercised at default sizing; tests pin explicit small-balance scenarios to keep that coverage alive.

## Pre-LIVE requirement (unchanged in spirit from ADR-028)

Before `TRADING_MODE=LIVE`: restore per-trade to `LIVE_MAX_RISK_PER_TRADE` (2%), re-derive the daily breaker against it, and re-run the pre-live checklist. Paper-mode caps in this ADR transfer nothing to LIVE.
