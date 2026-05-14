---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 7 UI-SPEC approved
last_updated: "2026-05-14T20:39:34.643Z"
last_activity: 2026-05-14
progress:
  total_phases: 7
  completed_phases: 6
  total_plans: 48
  completed_plans: 47
  percent: 98
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-06)

**Core value:** The bot must never lose money it wasn't authorized to risk; every "edge" claim must be backed by DSR/CPCV evidence on returns.
**Current focus:** Phase 07 — tournament-view-smoke-test

## Current Position

Phase: 07 (tournament-view-smoke-test) — EXECUTING
Plan: 6 of 6
Plans: 4 of 4 complete in Phase 05 (05-01 MLCL-01 apparatus + gate DONE; 05-02 MLCL-02 horizon-sweep shipped DONE; 05-03 MLCL-03 monitoring disposition DONE; 05-04 MLCL-04 backtest divergence documented DONE)
Status: Ready to execute
Last activity: 2026-05-14

CI: Workflow `tournament-harness.yml` registered upstream; first run blocked by GitHub Actions billing (operator must resolve at github.com/settings/billing). YAML validity confirmed locally.

Progress: [██████████] 98%

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
| Phase 05-ml-cleanup-post-v0 P02 | ~25min | 3 tasks | 7 files |
| Phase 05-ml-cleanup-post-v0 P03 | ~25min | 3 tasks | 8 files |
| Phase 05-ml-cleanup-post-v0 P04 | ~30min | 2 tasks | 4 files |

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
- [Phase 05 MLCL-02]: different_horizon selected as T0.1.x experiment — sweep horizon [3,5,7,10] on GRU-only grid (12 experiments); pure YAML edit, zero new Python; INSUFFICIENT_DATA verdict due to TIMESCALE_PASSWORD not propagated into container env (operator action required before re-run).
- [Phase 05 MLCL-04]: document_divergence_permanently chosen over rewrite_to_core_aggregator — tournament harness is the honest-evaluation path; run_extended_backtest.py designated as strategy regime characterisation tool only with PERMANENT DIVERGENCE framing + ADR-012.

### Pending Todos

None yet (use `/gsd-capture` to add).

### Blockers/Concerns

- Local main is 60+ commits ahead of origin/main as of 2026-05-01 — push pending; verify CI green before opening tournament PRs
- Working tree dirty at init time (15+ modified files including service code + frontend); mods are unrelated to GSD setup and stay outside GSD commits
- `scripts/monitoring/` tier-2 deleted per ADR-011 (Phase 5 MLCL-03); tier-1 retained as cheap health monitor

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

Last session: 2026-05-14T12:35:47.641Z
Stopped at: Phase 7 UI-SPEC approved
Resume file: .planning/phases/07-tournament-view-smoke-test/07-UI-SPEC.md
Open operator actions (3):

  1. Manual smoke 1 LIVE flip — recreate api-gateway with TRADING_MODE=LIVE, verify rose outline + red MODE pill, then revert.
  2. Apply migration 005 against market_data — `docker cp infrastructure/migrations/005_tournament_reader.sql crypto-bot-timescaledb:/tmp/ && docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -f /tmp/005_tournament_reader.sql`.
  3. Set TOURNAMENT_READER_PASSWORD in .env + ALTER ROLE tournament_reader PASSWORD '<value>' on TimescaleDB + force-recreate tournament-harness. Then re-run MLCL-02 t0_1_x_horizon_sweep.

Next: After operator unblocks, advance to Phase 7 (Tournament View & Smoke Test).
