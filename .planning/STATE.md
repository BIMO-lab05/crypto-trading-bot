---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 05 Plan 01 complete (05-01 MLCL-01 apparatus + gate).
last_updated: "2026-05-13T00:00:00.000Z"
last_activity: 2026-05-13 -- Phase 05 Plan 01 complete (MLCL-01)
progress:
  total_phases: 7
  completed_phases: 4
  total_plans: 37
  completed_plans: 35
  percent: 95
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-06)

**Core value:** The bot must never lose money it wasn't authorized to risk; every "edge" claim must be backed by DSR/CPCV evidence on returns.
**Current focus:** Phase 05 — ML Cleanup (post-V0) (next, not yet planned)

## Current Position

Phase: 05 (ml-cleanup-post-v0) — **EXECUTING** (Plan 01 of 4 complete)
Plans: 1 of 4 complete in Phase 05 (05-01 MLCL-01 apparatus + gate; 05-02, 05-03, 05-04 pending — each requires human-decision checkpoint at Task 1)
Status: Executing Phase 05
Last activity: 2026-05-13 -- Plan 05-01 complete (MLCL-01: forward-paper-test apparatus, PSR-CI kernel, default-on gate for Tier-1 flags)

CI: Workflow `tournament-harness.yml` registered upstream; first run blocked by GitHub Actions billing (operator must resolve at github.com/settings/billing). YAML validity confirmed locally.

Progress: [████████░░] 4/7 phases complete + Phase 05 in progress (57% → 95% of total plans)

## Performance Metrics

**Velocity:**

- Total plans completed: 19
- Average duration: —
- Total execution time: —

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 02 | 10 | - | - |
| 03 | 9 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 04-tournament-significance-auto-pr P09 | 35min | 3 tasks | 1 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Init: Skipped GSD codebase mapping; bootstrapped from existing CLAUDE.md + audit memory + V0 finding
- Init: Tournament uses Docker+Python orchestrator, not LLM subagents
- Init: Win criterion is DSR + bootstrap p<0.05 on OOS Sharpe / corrected Dir.Acc, not >5% R²
- Init: Bootstrap-tests run against fresh clone in tmp, never against working tree
- Init: Tournament wins open draft PRs; humans merge
- [Phase 04]: Used pytest --ignore (cwd-relative) over --deselect (rootdir-relative) in integration-fake-docker CI step — Plan literal --deselect tests/integration/X.py silently matched nothing because pytest rootdir is repo root; --ignore preserves cwd-relative path form and works correctly. Verified 26 passed / 14 ignored vs 40 collected with broken form.
- [Phase 04]: 0-SKIP grep guard in container-integration CI job is load-bearing — Pairs with Plan 04-08 test_canonical_metrics_importable.py for defence in depth — catches silent namespace-merge regression even if the regression test itself is re-routed to a skip path.

### Pending Todos

None yet (use `/gsd-capture` to add).

### Blockers/Concerns

- Local main is 60+ commits ahead of origin/main as of 2026-05-01 — push pending; verify CI green before opening tournament PRs
- Working tree dirty at init time (15+ modified files including service code + frontend); mods are unrelated to GSD setup and stay outside GSD commits
- `scripts/monitoring/*` autonomous tier-2 system parked since 2026-04-27; binding decision lives in Phase 5 (MLCL-03)

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| ML | Sentiment-as-filter integration | v2 | 2026-05-06 |
| ML | Classification head + calibration | v2 | 2026-05-06 |
| Dashboard | Server-side `/ws/metrics` route + WS subscription layer | v2 | 2026-05-06 |
| Dashboard | Mobile-friendly responsive layout | v2 | 2026-05-06 |
| Infra | K8s deployment | v2 | 2026-05-06 |
| Tournament | XRP/AVAX inclusion + multi-horizon search | v2 | 2026-05-06 |

## Session Continuity

Last session: 2026-05-13T00:00:00.000Z
Stopped at: Plan 05-01 complete (MLCL-01). Operator action: run ≥7-day evidence loops per Tier-1 flag.
Resume file: None
Next: `/gsd-execute-phase 05` plans 05-02, 05-03, 05-04 — each requires human-decision checkpoint at Task 1 (ML retrain scope, autonomous-tier decision, model acceptance gate).
