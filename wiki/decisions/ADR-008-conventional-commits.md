---
type: decision
status: accepted
date: 2025
context: "commit log readability and changelog generation"
deciders: []
tags: [decision, adr, conventions]
created: 2026-05-05
updated: 2026-05-05
---

# ADR-008: Conventional Commits

## Decision

Commits use `feat(service): ...`, `fix(service): ...`, `docs(service): ...` etc.

Branches: `feature/<service>-<desc>`, `fix/<desc>`.

## Consequences

- Readable git log
- Possible automated changelog (not currently wired up)
- Easier to spot per-service activity in `git log --grep='(trading-engine):'`
