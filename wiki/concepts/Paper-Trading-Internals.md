---
type: concept
status: active
tags: [concept, paper, trading]
created: 2026-05-05
updated: 2026-05-05
---

# Paper Trading Internals

What `PAPER_TRADING_MODE=true` actually does inside trading-engine.

## Execution model

Implemented in `services/trading-engine/app/paper_trading.py`. `execute_market_order(symbol, side, quantity, price)` deterministically returns a FILLED order at the **passed price**:

- **Zero slippage** (price requested = price filled)
- **Zero latency** (synchronous return)
- **Always FILLED** (no partial fills, no rejection, no exchange-side queue)

## The slippage manager that isn't called

`services/trading-engine/app/trading_enhancements/slippage_manager.py` exists and is wired into `auto_trader`. **It is not invoked inside the paper engine** — only on the LIVE path.

## Implications

- Paper P&L will systematically **overstate** real-trade results
- Backtests using paper engine = optimistic
- Strategy that depends on tight bid/ask spread = no signal in paper

## Real fill source

LIVE mode (`PAPER_TRADING_MODE=false`) routes orders through [[../modules/bybit-connector]] which calls Bybit REST. Slippage manager wraps the call.

## Related

- [[../flows/Order-Lifecycle]]
- [[Trading-Mode-Flags]]
- [[../decisions/ADR-011-paper-deterministic-execution]]
- [[../decisions/ADR-010-max-risk-per-trade-paper-bump]]
