---
type: decision
status: accepted
date: 2026-05-06
context: "$100 paper balance + 2% cap = $2/trade — too small for meaningful paper-trade signal"
deciders: [operator]
tags: [decision, adr, risk, paper-trading]
created: 2026-05-06
updated: 2026-05-06
---

# ADR-010: max_risk_per_trade bumped 0.02 → 0.10 for paper-trading sizing

## Context

`CLAUDE.md` "Project rules" historically declared `max 2% capital per trade` as a load-bearing risk cap, written when the system was speced for higher paper / live capital. Current paper balance is $100. A 2% cap caps trades at $2 notional — below Bybit's per-symbol minimum notional for several validated symbols (BTC, ETH) and below the noise floor for any meaningful win-rate / drawdown signal.

Outcome: most signals were either rejected by the min-notional gate or executed at sizes too small to test execution, slippage handling, and stop logic.

## Decision

`services/trading-engine/app/config.py:321` default `max_risk_per_trade` raised from `0.02` to `0.10` (10% of balance).

This is **paper-mode only**. The cap is read by `auto_trader.py:1837` and gates final notional. At $100 balance, max trade = $10 notional, which clears Bybit minimums for the validated symbols and produces a measurable PnL distribution.

The cap remains **non-negotiable for live trading**. When `TRADING_MODE=LIVE`:
- The pre-live operational checklist must verify `MAX_RISK_PER_TRADE` is back to ≤ 0.02 (or whatever post-paper analysis justifies), AND
- A follow-up ADR documents the live-time cap with capital basis.

## Consequences

- Paper-trade sample sizes are now informative; backtests and forward-paper can be compared.
- `CLAUDE.md` "Project rules" line about 2% per-trade is updated to: "max 2% capital per trade in LIVE mode; paper mode currently relaxed to 10% per ADR-010".
- Audit trail: the prior bump was made directly in `config.py` without ADR; this ADR is the retrospective record (filed 2026-05-06, same day as the code change).
- Live-mode guard: trading-engine should refuse to boot in LIVE if `max_risk_per_trade > 0.02` AND `LIVE_TRADING_ACK` is set, until a per-capital ADR exists. Implemented separately if/when LIVE is enabled.

## Related

- `services/trading-engine/app/config.py:321-332`
- `services/trading-engine/app/auto_trader.py:1832-1850` (cap-enforcement gate)
- ADR-004 paper-trading-default
- ADR-006 mainnet-prices-paper-orders
- `CLAUDE.md` § Project rules
