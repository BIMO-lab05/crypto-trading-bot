---
type: flow
status: active
tags: [flow, order]
created: 2026-05-05
updated: 2026-05-05
---

# Order Lifecycle

In paper-trading mode (current).

```
[[../modules/trading-engine|trading-engine]]
  ├── strategy generates intent (LONG / SHORT, size, stop, target)
  ├── [[../concepts/Risk-Model|Risk Model]] gate (2% / trade, 5% / day)
  ├── [[../concepts/Auto-Trader|Auto-Trader]] check (EMERGENCY_STOP file?)
  ├── simulated fill (no exchange call in paper mode)
  └── ↓ event
[[../modules/portfolio-manager|portfolio-manager]]
  ├── position update
  ├── balance update
  └── P&L recompute
    ↓ event
[[../modules/notification-service|notification-service]]
  └── Telegram / email alert (if configured)
```

## LIVE mode

In LIVE: simulated fill replaced by real Bybit order via [[../modules/bybit-connector|bybit-connector]]. Requires all 4 [[../concepts/Trading-Mode-Flags|Trading Mode Flags]] aligned.
