---
type: decision
status: accepted
date: 2026-05
context: "operator-friendly halt mechanism"
deciders: []
tags: [decision, adr, safety]
created: 2026-05-05
updated: 2026-05-19
---

# ADR-005: EMERGENCY_STOP file flag alongside admin HTTP endpoint

## Context

Operator must be able to halt auto-trading without depending on api-gateway's auth flow being healthy or even reachable.

## Decision

Two paths:

1. **File flag**: `touch safety/EMERGENCY_STOP` (host). Trading-engine RO bind-mounts the shared `./safety/` dir to `/app/safety/`; loop checks `/app/safety/EMERGENCY_STOP` presence each tick.
2. **Admin endpoint**: `POST /api/portfolio/emergency-stop` (admin-guarded). Writes the file via `pathlib.Path.write_text`.

Full stop (not just pause): `POST /api/trading/auto/stop`.

## Consequences

- File method works even if api-gateway is down
- `pathlib.Path.write_text` choice introduced a test gotcha — see [[../concepts/Test-Setup-Gotchas]] §2
- RO bind-mount on trading-engine means it can't write/delete the file (only api-gateway RW-bind or operator on host can)
- Dir-to-dir mount (post-2026-05-19) is stable across container recreates: host `./safety/` always exists, so the bind never auto-creates a phantom directory at the file path

## Evolution

- 2026-05-05 — initial design: file-to-file bind of `./EMERGENCY_STOP:/app/EMERGENCY_STOP`
- 2026-05-19 — moved to dir-to-dir bind of `./safety:/app/safety`. Reason: file-to-file binds silently create a *directory* at the mount point when the host file is missing at compose-up, leaving the in-container `is_file()` check returning False forever (kill switch non-functional). Discovered when a `rmdir EMERGENCY_STOP` host-side fix was needed mid-session. Dir-to-dir mount removes the failure mode because the host `./safety/` directory always exists.

## Related

- [[../flows/Emergency-Stop]]
- [[../concepts/Auto-Trader]]
