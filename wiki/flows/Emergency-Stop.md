---
type: flow
status: active
tags: [flow, safety]
created: 2026-05-05
updated: 2026-05-05
---

# Emergency Stop

Two paths to halt auto-trading.

## File flag (manual)

```bash
touch EMERGENCY_STOP
```

[[../modules/trading-engine|trading-engine]] mounts repo root RO. Loop checks file presence; presence = pause. Loop resumes when file removed.

## Admin endpoint

```
POST /api/portfolio/emergency-stop
```

Admin-guarded. Writes `EMERGENCY_STOP` via `pathlib.Path.write_text` (not `builtins.open` — see CLAUDE.md gotcha for tests).

## Full stop

```
POST /api/trading/auto/stop
```

Disables auto-trader entirely (not just pause).

## Related

- [[../concepts/Auto-Trader|Auto-Trader]]
- [[../modules/api-gateway|api-gateway]]
- [[../modules/trading-engine|trading-engine]]
