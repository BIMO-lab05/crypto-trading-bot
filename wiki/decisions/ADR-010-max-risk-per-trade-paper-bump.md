---
type: decision
status: accepted
date: 2026-05-06
context: "$100 paper balance + 2% cap = $2/trade — too small for meaningful paper-trade signal"
deciders: [operator]
tags: [decision, adr, risk, paper-trading]
created: 2026-05-06
updated: 2026-07-29
---

# ADR-010: max_risk_per_trade bumped 0.02 → 0.10 for paper-trading sizing

## Context

`CLAUDE.md` "Project rules" historically declared `max 2% capital per trade` as a load-bearing risk cap, written when the system was speced for higher paper / live capital. Current paper balance is $100. A 2% cap caps trades at $2 notional — below Bybit's per-symbol minimum notional for several validated symbols (BTC, ETH) and below the noise floor for any meaningful win-rate / drawdown signal.

Outcome: most signals were either rejected by the min-notional gate or executed at sizes too small to test execution, slippage handling, and stop logic.

## Decision

`services/trading-engine/app/config.py:321` default `max_risk_per_trade` raised from `0.02` to `0.10` (10% of balance).

This is **paper-mode only**. The cap is read in the sizing path and gates final notional. At $100 balance, max trade = $10 notional, which clears Bybit minimums for the validated symbols and produces a measurable PnL distribution.

### Enforcement semantics (updated 2026-07-28)

The cap no longer **rejects-and-skips** an oversized trade. Two changes landed in the fix campaign:

- **CLAMP instead of reject.** When the final notional exceeds `balance × cap_fraction`, the trade is resized *down* to the cap (`position_value = cap_value`, quantity recomputed) rather than dropped. The reject idiom was starving the research/hybrid entry path of 100 % of its signals — symbol allocations (25–30 %) always exceeded the 10 % cap, so every correctly-signalled trade on that path was thrown away, leaving only weaker-gated paths to trade. Clamping keeps the cap enforced *and* lets valid trades through. A `risk_limit_breaches_total{breach_type="position_size"}` metric still increments so the clamp is observable. See `auto_trader.py:1989-2022` and `auto_trader.py:3782-3796`.
- **HARD 2 % floor in LIVE.** When `TRADING_MODE=LIVE`, the cap fraction is forced to `min(cap_fraction, 0.02)` at runtime — the 10 % paper relaxation can no longer silently carry into LIVE if an env override forgets to restore it. This is a code-level guard, not just operator discipline. See `auto_trader.py:1995-1996` and `auto_trader.py:3785-3786`.

The cap remains **non-negotiable for live trading**. When `TRADING_MODE=LIVE`:
- The runtime `min(cap, 0.02)` clamp enforces ≤ 2 % regardless of `MAX_RISK_PER_TRADE`.
- The pre-live operational checklist should still set `MAX_RISK_PER_TRADE` back to ≤ 0.02 for clarity, AND
- A follow-up ADR documents the live-time cap with capital basis.

## Consequences

- Paper-trade sample sizes are now informative; backtests and forward-paper can be compared.
- `CLAUDE.md` "Project rules" line about 2% per-trade is updated to: "max 2% capital per trade in LIVE mode; paper mode currently relaxed to 10% per ADR-010".
- Audit trail: the prior bump was made directly in `config.py` without ADR; this ADR is the retrospective record (filed 2026-05-06, same day as the code change).
- Live-mode guard: trading-engine should refuse to boot in LIVE if `max_risk_per_trade > 0.02` AND `LIVE_TRADING_ACK` is set, until a per-capital ADR exists. Implemented separately if/when LIVE is enabled.

## Related

- `services/trading-engine/app/config.py:321-337` (default `max_risk_per_trade=0.10`)
- `services/trading-engine/app/auto_trader.py:1989-2022` (cap CLAMP + LIVE floor, research/hybrid path)
- `services/trading-engine/app/auto_trader.py:3782-3796` (cap CLAMP + LIVE floor, second sizing path)
- ADR-004 paper-trading-default
- ADR-006 mainnet-prices-paper-orders
- [[ADR-018-paper-engine-accounting-overhaul]] (companion accounting fixes)
- `CLAUDE.md` § Project rules
