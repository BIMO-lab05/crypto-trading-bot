---
type: decision
status: accepted
date: 2026-05
context: "trading-engine startup complexity"
deciders: []
tags: [decision, adr, trading-engine]
created: 2026-05-05
updated: 2026-05-05
---

# ADR-002: trading-engine lifespan refactor

## Context

200-line `lifespan()` in `services/trading-engine/app/main.py` did 47 init steps across 4 phases. Hard to reason about teardown order, hard to test, hard to extend.

## Decision

Split into composed `@asynccontextmanager`s under `app/lifespan/`:
- `data.py`
- `ml.py`
- `strategy.py`
- `risk.py`

Composed via cm-stack (`contextlib.AsyncExitStack`) — gives correct teardown order automatically. Auto-trader gate stays outside the four phases.

## Commits

`1389dc3`

## Consequences

- New file layout: `services/trading-engine/app/lifespan/{data,ml,strategy,risk}.py`
- `test_lifespan.py` 4 tests pass (exit order, package exports, main integration, source-level guard)
- `main.py` keeps re-exports with `# noqa: F401` for backward-compat with monkeypatching tests — see [[../concepts/Test-Setup-Gotchas]] §6

## Related

- [[../modules/trading-engine]]
- [[../concepts/Test-Setup-Gotchas]]
