---
type: concept
status: active
tags: [concept, paper, trading]
created: 2026-05-05
updated: 2026-07-29
---

# Paper Trading Internals

What `PAPER_TRADING_MODE=true` actually does inside trading-engine.

## Execution model

Implemented in `services/trading-engine/app/paper_trading.py`. Signature is now `execute_market_order(order: OrderCreate, current_price)` (returns `tuple[Order, Optional[str]]` — the second element is an error message). Fills are still deterministic at the **passed price**:

- **Zero slippage** (price requested = price filled)
- **Zero latency** (synchronous return)
- **Fills at the passed price** — no partial fills on the price axis, no exchange-side queue

But it is **no longer "always FILLED"**: an order can now be REJECTED (`OrderStatus.FAILED` + error string) on insufficient balance, or on a reduce-only order with no matching open position.

## Accounting (rewritten 2026-07-28)

- **Margin, not notional.** Opens deduct `margin (= notional/leverage) + commission`. `sync_balance_with_positions` matches this (previously deducted full notional, understating cash on every restart with open positions).
- **Side-aware close credit.** Closes credit `margin_returned + realized_pnl − commission` for BOTH long and short. Previously a winning SHORT close *decreased* balance (P&L sign inverted) and leveraged LONG closes credited full notional.
- **`reduce_only` honored.** A reduce-only order with no matching open position is REJECTED. Previously it opened a full-size OPPOSITE position — every stop-loss exit silently opened a counter-trade.
- **`position_id` targeting + partial closes.** An order can target a specific position; an order smaller than remaining qty reduces it (`reduce_position`) and credits proportional margin + P&L. A same-side order with `position_id` scales IN (`scale_in`, DCA averaging) instead of opening a duplicate.
- **P&L on remaining qty.** `Position.update_pnl` / `pnl_percentage` compute on `remaining_quantity`; closed positions report realized P&L (was always +0.00% after close). `position_manager.close_position` accumulates realized P&L on remaining qty (no double-count after partial exits).

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

## Corrections 2026-07-29

- Signature was documented as `execute_market_order(symbol, side, quantity, price)`; it is now `execute_market_order(order: OrderCreate, current_price)`.
- "Always FILLED (no rejection)" was wrong post-2026-07-28: reduce-only-with-no-position and insufficient-balance now REJECT.
- Added the 2026-07-28 accounting rewrite (margin-not-notional, side-aware close credit, reduce_only/position_id semantics, partial closes/scale-in, P&L on remaining qty). Verified against `paper_trading.py:129-383`, `models/position.py:86-124`, `position_manager.py:260-460`.
