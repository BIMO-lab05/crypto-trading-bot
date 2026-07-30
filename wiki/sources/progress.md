---
type: source
source_path: "progress.md"
ingested: 2026-05-05
status: summarized
tags: [source, log]
created: 2026-05-05
updated: 2026-07-30
---

# Source: progress.md

## Origin

Running session log. Append-only at end. Summary refreshed 2026-07-30; log itself current to 2026-05-20 (later work is logged in `.planning/` and `wiki/log.md` instead — consider retiring progress.md or resuming appends).

## Coverage

Sessions span 2025-10 (project start) through 2026-05-20 (most recent). Each entry: goal, completed, key findings, next steps.

## Most recent (2026-05-20) — signal-aggregator math fix

- 5+ months of zero fills traced to aggregator confidence math; fix went **live in container, not committed** at the time — captured by the committed 2026-07-28 confidence rework (verify).
- Open follow-ups still live: cascade penalty stack (0.95×·0.80×·0.90× = 0.684×) vs new metric un-investigated; production-aggregator backtest harness still missing (walk-forward tests the wrong strategy); May-7 "25 trades / 0 winners / −$0.78" unexplained.

## Prior (2026-05-03)

- PR #77 review (`fix/api-gateway-py314-deps`) — flagged bcrypt 5.0 + 72-byte password bug → fix committed `6cd9bf6` (switched to `bcrypt_sha256`). Stale on PR branch only.
- Deploy from main, not PR (compose regressions on PR branch flagged but not merged).
- api-gateway test fixture: `admin_client` overrides `get_current_admin_user`. 4 emergency-stop tests fixed (13 → 9 fails).
- Gotcha: patch `pathlib.Path.write_text`, not `builtins.open`.

## Earlier (2026-04-25 audit)

- 817 Python files, 372K LOC, 11 microservices
- 6 parallel agents deployed (backend, frontend, backtesting, infra, docs, tests)
- 609 uncommitted changes incl. critical Jan 2026 fixes

## Material lifted into wiki

- [[../decisions/ADR-001-LSTM-removed]]
- [[../decisions/ADR-002-trading-engine-lifespan-refactor]]
- [[../decisions/ADR-003-bcrypt-sha256-prehash]]
- [[../concepts/Test-Setup-Gotchas]]

## What lives in progress.md but NOT in wiki

- Per-session market data snapshots (BTC/SOL prices on day X — not actionable now)
- Trading performance numbers from individual sessions (better as Dataview query later)
- Per-day TODO completions

## Open questions

- Should weekly performance summaries get extracted into `meta/performance/` or stay in source?
