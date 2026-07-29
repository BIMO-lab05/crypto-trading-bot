---
type: decision
status: accepted
date: 2026-07-28
context: "paper P&L / balance were wrong: winning shorts reduced cash, stop exits flipped into counter-trades, DCA opened duplicate positions"
deciders: [operator]
tags: [decision, adr, paper, trading, accounting]
created: 2026-07-29
updated: 2026-07-29
---

# ADR-018: paper-engine accounting overhaul (side-aware close, reduce_only, position targeting, partial close + DCA)

## Context

`PaperTradingEngine.execute_market_order` (see [[ADR-011-paper-deterministic-execution]] for the *fill* contract) had correct fill semantics but broken **accounting**. An audit on 2026-07-28 found:

- **Asymmetric close crediting.** Opens deducted MARGIN (`notional / leverage`) + commission, but closes credited *close-notional* on SHORT and *full notional* on leveraged LONG. Net effect: a winning SHORT *reduced* the balance, and leveraged closes over-credited cash.
- **Reduce-only flipped into a new trade.** A reduce-only order (every stop-loss / take-profit exit) with no matching open position silently *opened an opposite position* — each exit became a brand-new counter-trade.
- **Blind position targeting.** The engine closed `open_positions[0]` rather than the intended position.
- **DCA opened duplicates.** A same-side safety order opened a duplicate position (with its own default stops) instead of averaging in.
- **Restart under-counted cash.** `sync_balance_with_positions` deducted full notional, not margin.
- **realized_pnl overwrite.** `close_position` overwrote realized P&L with a full-quantity mark, double-counting quantity already exited at TP1/TP2 and corrupting daily-P&L / circuit breakers.

## Decision

`execute_market_order` was rewritten (2026-07-28) so that:

- **Closes credit `margin_returned + realized_pnl − commission` for BOTH sides.** P&L is `(price − entry)·qty` for LONG, `(entry − price)·qty` for SHORT, on the quantity actually closed. `paper_trading.py:208-275`.
- **`reduce_only` is honored: no match → REJECT** (`OrderStatus.FAILED`), never flip to a counter-trade. `paper_trading.py:186-197, 277-285`.
- **`order.position_id` targets a specific position**; no more `[0]` guesswork. `paper_trading.py:184-207`.
- **Partial closes** reduce the position and credit proportional margin + P&L via `PositionManager.reduce_position`. `paper_trading.py:236-250`, `position_manager.py:360-412`.
- **Same-side + explicit `position_id` scales INTO** the position (weighted-average entry) via `scale_in`, instead of duplicating. `paper_trading.py:287-332`, `position_manager.py:414-465`.
- **`close_position` accumulates** realized P&L on the *remaining* quantity only (`+=`, not `=`). `position_manager.py:284-309`.
- **`sync_balance_with_positions` deducts margin + commission** on restart. `paper_trading.py:80-108`.
- **`Position.update_pnl` and `pnl_percentage` use remaining quantity** and report realized P&L for closed positions. `models/position.py:86-124`.

## Consequences

- Paper balance, equity and realized/unrealized P&L are now internally consistent and side-correct; downstream risk gates (kill switch, daily-loss breaker) receive true numbers — see [[ADR-019-kill-switch-equity-and-streak]].
- Fill realism is unchanged (still zero-slippage / always-filled per ADR-011); paper P&L is *correct* but still *optimistic*.
- Stop-loss / take-profit exits close the intended position instead of doubling exposure.
- Tests were updated to the new close/cap semantics (`test_paper_trading*`, commit `a9ed2a8`).

## Related

- `services/trading-engine/app/paper_trading.py:129-383`
- `services/trading-engine/app/position_manager.py:260-465`
- `services/trading-engine/app/models/position.py:86-124`
- [[ADR-011-paper-deterministic-execution]]
- [[ADR-010-max-risk-per-trade-paper-bump]]
- [[../flows/Order-Lifecycle]]
