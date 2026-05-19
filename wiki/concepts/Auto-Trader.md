---
type: concept
status: armed
tags: [concept, auto-trader, safety]
created: 2026-05-05
updated: 2026-05-05
---

# Auto-Trader

Compose default `AUTO_TRADING_ENABLED=false`. **Operator override** in `.env`: `AUTO_TRADING_ENABLED=true` (set 2026-05-05).

[[../modules/trading-engine|trading-engine]] boots with auto-trader armed; loop only fires when the kill-switch file is **absent** inside the shared `safety/` dir (`./safety/EMERGENCY_STOP` host → `/app/safety/EMERGENCY_STOP` container). Trading-engine RO-binds the dir; api-gateway RW-binds it. Dir-to-dir bind-mount per 2026-05-19 compose patch (replaces older `./EMERGENCY_STOP` file-to-file bind that broke when host file was missing — Docker auto-created a directory in its place).

## Pause / stop

- **Pause:** `touch safety/EMERGENCY_STOP` or `POST /api/portfolio/emergency-stop` (admin-guarded)
- **Resume after pause:** `rm safety/EMERGENCY_STOP` (+ `POST /api/trading/start` if loop was halted mid-iteration; auto-trader doesn't auto-restart from a halt)
- **Stop fully:** `POST /api/trading/auto/stop`

## Related

- [[../flows/Emergency-Stop|Emergency Stop]]
- [[../modules/trading-engine|trading-engine]]
