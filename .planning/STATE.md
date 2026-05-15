---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: Awaiting next milestone
stopped_at: Phase 7 UI-SPEC approved
last_updated: "2026-05-15T02:55:07.614Z"
last_activity: 2026-05-15 — Milestone v1.0 completed and archived
progress:
  total_phases: 9
  completed_phases: 9
  total_plans: 50
  completed_plans: 50
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-06)

**Core value:** The bot must never lose money it wasn't authorized to risk; every "edge" claim must be backed by DSR/CPCV evidence on returns.
**Current focus:** Phase 07.2 — phase3-skeleton-loader-fix

## Current Position

Phase: Milestone v1.0 complete
Plan: —
Status: Awaiting next milestone
Last activity: 2026-05-15 — Milestone v1.0 completed and archived

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

Items acknowledged and deferred at v1.0 milestone close on 2026-05-15:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| uat_gap | 01-UAT.md | partial (0 pending) | 2026-05-15 |
| uat_gap | 02-HUMAN-UAT.md | partial (5 pending operator scenarios) | 2026-05-15 |
| uat_gap | 04-UAT.md | gaps_closed (0 pending) | 2026-05-15 |
| verification_gap | 01-VERIFICATION.md | human_needed (INFRA-02 Plan 01-03 Task 4 fresh-clone checkpoint) | 2026-05-15 |
| verification_gap | 02-VERIFICATION.md | human_needed (INFRA-01 live-stack run, blocked OP-04) | 2026-05-15 |
| verification_gap | 05-VERIFICATION.md | human_needed (MLCL-01 ≥7-day evidence loops; MLCL-02 INSUFFICIENT_DATA pending OP-02/OP-03) | 2026-05-15 |
| verification_gap | 06-VERIFICATION.md | human_needed (DASH-03 LIVE-flip smoke, pending OP-01) | 2026-05-15 |
| verification_gap | 07-VERIFICATION.md | human_needed (DASH-06 CI run, pending OP-04; closed locally via P07.1 smoke green) | 2026-05-15 |
| ML | Sentiment-as-filter integration | v2 | 2026-05-06 |
| ML | Classification head + calibration | v2 | 2026-05-06 |
| Dashboard | Server-side `/ws/metrics` route + WS subscription layer | v2 | 2026-05-06 |
| Dashboard | Mobile-friendly responsive layout | v2 | 2026-05-06 |
| Infra | K8s deployment | v2 | 2026-05-06 |
| Tournament | XRP/AVAX inclusion + multi-horizon search | v2 | 2026-05-06 |

### Open Operator Actions (carry into v1.1)

| ID | Action | Blocks |
|---|---|---|
| OP-01 | Manual smoke: TRADING_MODE=LIVE force-recreate api-gateway, confirm rose outline + red MODE pill, revert | DASH-03 LIVE-flip visual; Phase 06 VERIFICATION transition |
| OP-02 | Apply `infrastructure/migrations/005_tournament_reader.sql` to `market_data` on `crypto-bot-timescaledb` | MLCL-02 verdict; tournament_reader role |
| OP-03 | Set `TOURNAMENT_READER_PASSWORD` in `.env` + `ALTER ROLE tournament_reader PASSWORD '<value>'` + force-recreate `tournament-harness` | MLCL-02 verdict |
| OP-04 | Resolve GitHub Actions billing at github.com/settings/billing | INFRA-01 CD-05 ML-on nightly variant; tournament-harness CI first run; DASH-06 CI confirmation |
| INFRA-02 checkpoint | Operator runs Plan 01-03 Task 4 — fresh tmp clone → `bash bootstrap.sh` × 2 → grep `BYBIT_PRICE_SOURCE: mode=tape` → 15 services healthy | INFRA-02 SC-1 + SC-3 behavioural confirmation |

OP-05 (push 60+ commits to origin/main) — CLOSED 2026-05-15T02:20Z.

## Session Continuity

Last session: 2026-05-14T12:35:47.641Z
Stopped at: Phase 7 UI-SPEC approved
Resume file: .planning/phases/07-tournament-view-smoke-test/07-UI-SPEC.md
Open operator actions (3):

  1. Manual smoke 1 LIVE flip — recreate api-gateway with TRADING_MODE=LIVE, verify rose outline + red MODE pill, then revert.
  2. Apply migration 005 against market_data — `docker cp infrastructure/migrations/005_tournament_reader.sql crypto-bot-timescaledb:/tmp/ && docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -f /tmp/005_tournament_reader.sql`.
  3. Set TOURNAMENT_READER_PASSWORD in .env + ALTER ROLE tournament_reader PASSWORD '<value>' on TimescaleDB + force-recreate tournament-harness. Then re-run MLCL-02 t0_1_x_horizon_sweep.

Next: After operator unblocks, advance to Phase 7 (Tournament View & Smoke Test).

## Operator Next Steps

- Start the next milestone with /gsd-new-milestone
