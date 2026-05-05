---
type: decision
status: accepted
date: 2026-05
context: "operator-friendly halt mechanism"
deciders: []
tags: [decision, adr, safety]
created: 2026-05-05
updated: 2026-05-05
---

# ADR-005: EMERGENCY_STOP file flag alongside admin HTTP endpoint

## Context

Operator must be able to halt auto-trading without depending on api-gateway's auth flow being healthy or even reachable.

## Decision

Two paths:

1. **File flag**: `touch EMERGENCY_STOP` at repo root. Trading-engine RO bind-mounts repo root; loop checks file presence each tick.
2. **Admin endpoint**: `POST /api/portfolio/emergency-stop` (admin-guarded). Writes the file via `pathlib.Path.write_text`.

Full stop (not just pause): `POST /api/trading/auto/stop`.

## Consequences

- File method works even if api-gateway is down
- `pathlib.Path.write_text` choice introduced a test gotcha — see [[../concepts/Test-Setup-Gotchas]] §2
- RO bind-mount means trading-engine container can't write the file (only delete via admin endpoint or operator on host)

## Related

- [[../flows/Emergency-Stop]]
- [[../concepts/Auto-Trader]]
