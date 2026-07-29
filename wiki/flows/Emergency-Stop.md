---
type: flow
status: active
tags: [flow, safety]
created: 2026-05-05
updated: 2026-07-29
---

# Emergency Stop

Manual paths to halt auto-trading, plus the automated multi-threshold kill switch.

## File flag (manual)

```bash
touch safety/EMERGENCY_STOP    # halt
rm safety/EMERGENCY_STOP       # clear (manual /api/trading/start needed if halted at boot)
```

[[../modules/trading-engine|trading-engine]] RO-binds `./safety/` to `/app/safety/`. Loop checks `/app/safety/EMERGENCY_STOP` presence each tick (`is_file()`); presence = halt. The host `./safety/` dir always exists (committed empty with `.gitkeep`), so the bind-mount is stable across container recreates.

## Admin endpoint

```
POST /api/portfolio/emergency-stop
```

Admin-guarded. Writes `/app/safety/EMERGENCY_STOP` via `pathlib.Path.write_text` (not `builtins.open` — see CLAUDE.md gotcha for tests).

## Full stop

```
POST /api/trading/auto/stop
```

Disables auto-trader entirely (not just pause).

## Automated kill switch

The trading-engine also runs a multi-threshold `KillSwitch` that halts the loop on daily-loss, drawdown, consecutive-loss, or max-position-value breaches. Fixed 2026-07-28 (see [[../decisions/ADR-019-kill-switch-equity-and-streak]]): it is fed **equity** (cash + unrealized P&L), not raw cash, so opening a position no longer looks like a loss; the consecutive-loss streak only advances on trade **closes**; and the daily-loss window **auto-rolls per UTC day**. Auto-resets after `auto_reset_hours` (24h) or via `POST` deactivate.

## History

- 2026-05-05 — original design: file-to-file bind of `./EMERGENCY_STOP:/app/EMERGENCY_STOP`
- 2026-05-19 — moved to `./safety/` dir-to-dir bind. File-to-file bind silently created a directory at the mount point when the host file was missing at compose-up, leaving the kill switch non-functional. See [[../decisions/ADR-005-emergency-stop-file-flag]].

## Related

- [[../concepts/Auto-Trader|Auto-Trader]]
- [[../modules/api-gateway|api-gateway]]
- [[../modules/trading-engine|trading-engine]]
- [[../decisions/ADR-019-kill-switch-equity-and-streak]]
