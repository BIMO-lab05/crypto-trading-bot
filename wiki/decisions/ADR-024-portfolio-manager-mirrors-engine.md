---
type: decision
status: accepted
date: 2026-07-29
context: "portfolio-manager reconstructed positions as spot BUYs — SHORTs shown as LONGs with inverted P&L, cash over-deducted, phantom -84% return"
deciders: [operator]
tags: [decision, adr, portfolio-manager, accounting]
created: 2026-07-29
updated: 2026-07-29
---

# ADR-024: portfolio-manager mirrors the trading engine (side-aware, authoritative cash/equity)

## Context

`sync_with_trading_engine` rebuilt the book by calling `portfolio.add_asset()` (a spot BUY) for every engine position. This:

- **Ignored `position["side"]`** — leveraged SHORTs were modeled as spot LONGs, so their P&L was inverted.
- **Deducted full notional from cash** — a $100 book with two leveraged shorts showed cash ≈ $15 and a phantom −84 % return.

The trading engine is the authoritative book (cash, realized/unrealized P&L, per-position side, margin already reflected); reconstructing it from spot-buy accounting could never match.

## Decision

`portfolio-manager/app/services/portfolio_manager.py` `sync_with_trading_engine` was rewritten (2026-07-29) to **faithfully mirror** the engine rather than reconstruct:

- Build assets directly from engine positions, carrying `side` (LONG/SHORT) onto each `Asset`. `portfolio_manager.py:204-240`.
- Pull the engine's **authoritative cash + realized P&L** from `/api/v1/performance` (`current_balance`, `realized_pnl`) and copy them; fall back to local sums only if the endpoint is unavailable. `portfolio_manager.py:242-266`.
- Compute futures/margin equity as `cash + unrealized P&L` (cash already reflects margin + realized). Allocation is exposure-based (`notional / equity`), which may exceed 100 % on leverage — honest, not a bug. `portfolio_manager.py:259-284`.

`Asset.update_valuation` is now **side-aware**: `unrealized_pnl = total_cost − current_value` for SHORT, `current_value − total_cost` for LONG. `models/asset.py:23-27, 49-69`.

## Consequences

- Portfolio equity, cash, and per-position P&L match the engine exactly; SHORT P&L has the correct sign.
- The phantom negative-return dashboard bug is gone.
- Portfolio-manager is now a read-through mirror of the engine's book — depends on the engine's own accounting being correct (see [[ADR-018-paper-engine-accounting-overhaul]]).

## Related

- `services/portfolio-manager/app/services/portfolio_manager.py:168-296`
- `services/portfolio-manager/app/models/asset.py:23-69`
- [[ADR-018-paper-engine-accounting-overhaul]]
- [[ADR-017-risk-metrics-paper-mode-alignment]]
- [[../modules/portfolio-manager]]
