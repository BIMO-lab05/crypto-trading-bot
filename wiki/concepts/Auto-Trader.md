---
type: concept
status: armed
tags: [concept, auto-trader, safety]
created: 2026-05-05
updated: 2026-07-30
---

# Auto-Trader

Compose default `AUTO_TRADING_ENABLED=false`. **Operator override** in `.env`: `AUTO_TRADING_ENABLED=true` (set 2026-05-05).

[[../modules/trading-engine|trading-engine]] boots with auto-trader armed; loop only fires when the kill-switch file is **absent** inside the shared `safety/` dir (`./safety/EMERGENCY_STOP` host → `/app/safety/EMERGENCY_STOP` container). Trading-engine RO-binds the dir; api-gateway RW-binds it. Dir-to-dir bind-mount per 2026-05-19 compose patch (replaces older `./EMERGENCY_STOP` file-to-file bind that broke when host file was missing — Docker auto-created a directory in its place).

## Pause / stop

- **Pause:** `touch safety/EMERGENCY_STOP` or `POST /api/portfolio/emergency-stop` (admin-guarded)
- **Resume after file-halt:** `rm safety/EMERGENCY_STOP` **then** `POST /api/trading/start` (or restart the service). Verified against `auto_trader.py` (2026-07-30): detecting the file sets `is_running = False` and `break`s the loop — it does **not** auto-restart. (Repo CLAUDE.md previously claimed the inverse; corrected same day.)
- **Risk kill-switch halt is different:** when `kill_switch.should_halt_trading()` is true the loop keeps running (60s cadence, positions still monitored) and **auto-resumes** when limits clear.
- **Stop fully:** `POST /api/trading/auto/stop`

## Related

- [[../flows/Emergency-Stop|Emergency Stop]]
- [[../modules/trading-engine|trading-engine]]
