---
type: concept
status: armed
tags: [concept, auto-trader, safety]
created: 2026-05-05
updated: 2026-05-05
---

# Auto-Trader

Compose default `AUTO_TRADING_ENABLED=false`. **Operator override** in `.env`: `AUTO_TRADING_ENABLED=true` (set 2026-05-05).

[[../modules/trading-engine|trading-engine]] boots with auto-trader armed; loop only fires when `EMERGENCY_STOP` file is **absent** at repo root (RO bind-mount in trading-engine container).

## Pause / stop

- **Pause:** `touch EMERGENCY_STOP` or `POST /api/portfolio/emergency-stop` (admin-guarded)
- **Stop fully:** `POST /api/trading/auto/stop`

## Related

- [[../flows/Emergency-Stop|Emergency Stop]]
- [[../modules/trading-engine|trading-engine]]
