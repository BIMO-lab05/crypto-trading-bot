---
type: flow
status: active
tags: [flow, order]
created: 2026-05-05
updated: 2026-07-29
---

# Order Lifecycle

In paper-trading mode (current).

```
[[../modules/trading-engine|trading-engine]]
  ├── strategy generates intent (LONG / SHORT, size, stop, target)
  ├── [[../concepts/Risk-Model|Risk Model]] gate
  │     ├── per-trade cap: CLAMP notional to max_risk_per_trade (10% paper);
  │     │   hard min(cap, 0.02) in LIVE — see [[../decisions/ADR-010-max-risk-per-trade-paper-bump]]
  │     └── daily-loss limit (auto-rolls per UTC day) + kill switch (equity-fed)
  ├── [[../concepts/Auto-Trader|Auto-Trader]] check (EMERGENCY_STOP file?)
  ├── simulated fill (no exchange call in paper mode) — zero slippage / always filled
  │     └── accounting (see [[../decisions/ADR-018-paper-engine-accounting-overhaul]]):
  │           • OPEN: deduct margin (notional / leverage) + commission
  │           • CLOSE/REDUCE: credit margin_returned + realized_pnl − commission,
  │             side-aware P&L (LONG: price−entry; SHORT: entry−price)
  │           • reduce_only with no matching position → REJECT (never flips to a counter-trade)
  │           • order.position_id targets a specific position (no [0] guess)
  │           • partial close reduces position; same-side + position_id scales IN (DCA avg)
  └── ↓ kill switch update_metrics(equity, is_trade_close=True on close)
[[../modules/portfolio-manager|portfolio-manager]]
  ├── MIRRORS the engine (side-aware, authoritative cash/equity — no spot-buy reconstruction)
  │     see [[../decisions/ADR-024-portfolio-manager-mirrors-engine]]
  ├── position update
  ├── balance / equity = cash + unrealized P&L
  └── P&L recompute (side-aware)
    ↓ event
[[../modules/notification-service|notification-service]]
  └── Telegram / email alert (real delivery by default — see [[../decisions/ADR-025-notification-real-delivery-default]])
```

## LIVE mode

In LIVE: simulated fill replaced by a real Bybit order via [[../modules/bybit-connector|bybit-connector]]. Requires all 4 [[../concepts/Trading-Mode-Flags|Trading Mode Flags]] aligned. Authenticated requests sign the exact compact bytes transmitted (see [[../decisions/ADR-023-bybit-request-signing-fix]]), and the per-trade cap is hard-clamped to ≤ 2%.

## Related

- [[../decisions/ADR-011-paper-deterministic-execution]] — fill contract (frictionless)
- [[../decisions/ADR-018-paper-engine-accounting-overhaul]] — close / reduce_only / DCA accounting
- [[../decisions/ADR-019-kill-switch-equity-and-streak]] — kill switch + daily-loss breaker
