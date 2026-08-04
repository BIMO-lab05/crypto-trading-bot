---
type: decision
status: accepted
date: 2026-05-06
context: "Paper-trading fill semantics"
deciders: []
tags: [decision, adr, paper, trading]
created: 2026-05-06
updated: 2026-08-03
---

# ADR-011: paper-trading executes deterministically (zero slippage, zero latency, always filled)

> ⚠️ **SUPERSEDED IN PART — 2026-08-03 (PAPER-01).** The zero-slippage half of this contract **no longer holds.** `PaperTradingEngine.execute_market_order` now applies a per-symbol adverse slippage model (`app/paper_slippage.py`), on by default, reaching every downstream price site (notional, commission, `filled_price`, realized P&L both sides, `close_position`, `reduce_position`, `scale_in`, `create_position`). Measured effect on a 10-round-trip winners-only tape: **realized P&L −$0.3836, ROI 2.21% → 1.82%**.
>
> "Alternatives considered" below **rejected** this change. That rejection is reversed. The stated reason — that slippage "removes paper's value as a clean plumbing test" — was outweighed by the fact that every strategy Sharpe in the repo (−0.22 to −0.50) had been measured through a frictionless engine, making all of them optimistic by an unknown amount. Zero-slippage remains reachable explicitly via `PAPER_SLIPPAGE_ENABLED=false` for A/B comparison and for the accounting tests that pin arithmetic rather than fill realism, so the plumbing-test use case survives as an opt-in.
>
> Zero-latency and always-filled are **unchanged** and still optimistic. Do not read this note as "paper is now realistic."

## Context

`PAPER_TRADING_MODE=true` simulates orders inside `services/trading-engine/app/paper_trading.py` instead of routing them to bybit-connector. The simulator's contract was never explicit; behavior was inferred from code.

Audited 2026-05-05 — `execute_market_order(symbol, side, quantity, price)` returns a FILLED order at the **passed price**:

- Zero slippage (requested price = filled price)
- Zero latency (synchronous return)
- Always FILLED (no partial fills, no rejection, no exchange-side queue)

`services/trading-engine/app/trading_enhancements/slippage_manager.py` exists and is wired into `auto_trader`, **but is not invoked inside the paper engine** — only on the LIVE path.

## Decision

Paper-trading mode is intentionally **deterministic and frictionless**:

- The signal pipeline + risk gate + persistence path are exercised; market microstructure is **not**
- Paper P&L is allowed to overstate real-trade results
- Strategies that depend on tight bid/ask spread, slippage modeling, or exchange queue behavior **must be validated in LIVE mode (or a future paper+slippage mode)** before relying on the paper P&L curve

Paper exists to validate **strategy plumbing**, not strategy edge under realistic execution.

> **Fill semantics unchanged, accounting overhauled (2026-07-28).** The zero-slippage / zero-latency / always-filled *fill* contract described here still holds. What changed is the **accounting** behind the fill: closes now credit `margin_returned + realized_pnl − commission` for *both* sides (a winning SHORT no longer reduces the balance), `reduce_only` orders reject instead of flipping into a counter-trade, `position_id` targets a specific position, and partial closes / DCA scale-ins are supported. Those are correctness fixes to the P&L math, not a change to execution realism, and are documented separately in [[ADR-018-paper-engine-accounting-overhaul]]. Paper P&L is now *correct* but still *optimistic* (frictionless), so the caution below stands.

## Consequences

- Backtests using the paper engine = optimistic; do not infer Sharpe from them
- Adding non-zero slippage to paper would be a behavior-change ADR of its own
- Auto-trader's slippage_manager wiring on the LIVE path is the canonical place to extend execution realism
- Pre-LIVE checklist must include re-running strategy under LIVE (or paper+slippage shadow) before sizing up

## Alternatives considered

- **Wire slippage_manager into paper engine.** Rejected: removes paper's value as a clean plumbing test. Reconsider as a separate `PAPER_REALISTIC_MODE` flag if/when needed.
- **Random latency + partial fills in paper.** Rejected: indeterminism makes regression-style tests on paper P&L flaky.

## Related

- [[../concepts/Paper-Trading-Internals]]
- [[../concepts/Trading-Mode-Flags]]
- [[../flows/Order-Lifecycle]]
- [[ADR-004-paper-trading-default]]
- [[ADR-006-mainnet-prices-paper-orders]]
- [[ADR-010-max-risk-per-trade-paper-bump]]
- [[ADR-018-paper-engine-accounting-overhaul]] (the 2026-07-28 accounting fixes)
