---
gsd_state_version: 1.0
milestone: v1.3
milestone_name: TA + Engine Correctness
status: ready_to_plan
stopped_at: Phase 17 complete (2/2) — ready to discuss Phase 18
last_updated: 2026-05-24T10:39:57.122Z
last_activity: 2026-05-24 -- Phase 17 execution started
progress:
  total_phases: 9
  completed_phases: 1
  total_plans: 9
  completed_plans: 9
  percent: 11
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-23 after v1.3 milestone open)

**Core value:** The bot must never lose money it wasn't authorized to risk; every "edge" claim must be backed by DSR/CPCV evidence on returns, not raw R² on price levels.
**Current focus:** Phase 18 — bybit adapter contract fix

## Current Position

Phase: 18
Plan: Not started
Status: Ready to plan
Last activity: 2026-05-24

## Deferred Items

Items acknowledged and deferred at milestone close on 2026-05-18:

| Category | Item | Status |
|---|---|---|
| verification | Phase 08 VERIFICATION.md | human_needed (2 manual-only smokes: container-restart cap-rejection proof + live HTTP curl through api-gateway after image rebuild — both deferred to post-merge operator verification per Manual-Only #1/#2 in 08-VALIDATION.md) |
| operator-action | OP-01 — LIVE-flip manual smoke | open (blocks LIVECLOSE-05 evidence; harness shipped at scripts/closure/liveclose-05-live-flip-smoke.sh + docs/runbooks/LIVECLOSE-05.md, supervised-run-only) |
| operator-action | OP-02 — apply migration 005 (`tournament_reader` role) | open (blocks LIVECLOSE-04 verdict) |
| operator-action | OP-03 — set `TOURNAMENT_READER_PASSWORD` + force-recreate tournament-harness | open (blocks LIVECLOSE-04 verdict) |
| operator-action | OP-04 — resolve GitHub Actions billing | open (blocks LIVECLOSE-02, CIRESTORE-01, CIRESTORE-02 evidence accrual) |
| operator-action | INFRA-02 checkpoint — fresh tmp clone bootstrap × 2 | open (blocks LIVECLOSE-01 evidence; harness shipped at scripts/closure/liveclose-01-fresh-clone.sh) |
| operator-action | LIVECLOSE-03 ≥7-day evidence accrual | open (wall-clock-bound; harness shipped at scripts/closure/liveclose_03_psr_evidence.py) |

## Accumulated Context

### Roadmap Evolution

- v1.0 milestone shipped 2026-05-15 (9 phases, 50 plans, 427 commits)
- v1.1 milestone shipped 2026-05-18 (5 phases, 19 plans, 138 commits; Phase 11 umbrella superseded by Phase 11.1 harnesses-only split)
- v1.2 milestone shipped 2026-05-23 (3 phases, 19 plans; Phases 13–15)
- v1.3 milestone opened 2026-05-23 (planned 9 phases, two parallel tracks, paper-only — TA + Engine Correctness)

### Decisions

Decision history accumulates in PROJECT.md `## Key Decisions`. STATE.md retains only the open / load-bearing-now items:

- ML predictions remain `ENABLE_ML_PREDICTIONS=false`; trading-engine auto-flip is *armed* (Phase 9) but no qualifying DSR>0.95 evidence row exists in `leaderboard` yet (LIVECLOSE-03 wall-clock).
- Paper-mode per-trade cap relaxed to 10% (ADR-010); Phase 8 boot-path enforces ≤2% only in LIVE. Pre-LIVE checklist (RUNBOOK Pre-LIVE Operator Checklist) restores ≤2% before flip.
- [Phase ?]: Plan 16-06 merge: 81/74/7/0

### Blockers/Concerns

- 7 operator-action items open (5 LIVECLOSE harnesses + 2 CIRESTORE evidence + 1 INFRA-02 checkpoint). All have shipped harness code; only wall-clock execution remains.
- Phase 08 VERIFICATION.md `human_needed` status persists post-archive: 2 manual-only smokes require operator post-merge action.
- New (2026-05-22): OP-05 added — running api-gateway container computed `SECRET_KEY` before quick-260522-hv0 fix; must be force-recreated before any `TRADING_MODE=LIVE` or `PAPER_TRADING_MODE=false` flip or hard-fail predicate won't run.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260522-hv0 | Fix JWT default-secret hole — extend `_validate_jwt_secret()` hard-fail to `TRADING_MODE=LIVE` / `PAPER_TRADING_MODE=false`; remove dead `Settings.jwt_secret_key` Pydantic field with insecure default | 2026-05-22 | `e0c4aa6` | [260522-hv0-fix-jwt-default-secret-hole-extend-hard-](./quick/260522-hv0-fix-jwt-default-secret-hole-extend-hard-/) |

## Open Operator Actions (carry into v1.3)

| ID | Action | Blocks |
|---|---|---|
| OP-01 | LIVE-flip manual smoke (api-gateway `TRADING_MODE=LIVE`, rose outline, revert) | LIVECLOSE-05 |
| OP-02 | Apply migration 005 to market_data on timescaledb | LIVECLOSE-04 |
| OP-03 | Set `TOURNAMENT_READER_PASSWORD` + force-recreate tournament-harness | LIVECLOSE-04 |
| OP-04 | Resolve GH Actions billing | LIVECLOSE-02, CIRESTORE-01, CIRESTORE-02 |
| INFRA-02 chk | Run `bootstrap.sh` × 2 from fresh tmp clone | LIVECLOSE-01 |
| LIVECLOSE-03 accrual | Run `scripts/forward_paper_test/run_evidence_loop.py` for ≥7 trading days | LIVECLOSE-03 |
| OP-05 | Force-recreate `crypto-bot-api-gateway` to load hardened `_validate_jwt_secret()` from quick-260522-hv0 (`docker compose -f docker-compose.unified.yml up -d --force-recreate api-gateway` with `JWT_SECRET_KEY` set via `openssl rand -hex 64`) | Pre-LIVE flip, OP-01 |
| OP-06 | Rebuild + restart `crypto-bot-trading` so Phase 17 TE-CAP-02 route deletion takes effect at runtime (`docker compose -f docker-compose.unified.yml up -d --build trading-engine`), then verify with `curl -sS -X POST -o /dev/null -w "%{http_code}\n" http://localhost:8005/api/v1/orchestrator/emergency-stop` returns `404` (not `200`). Source change landed in commit `f2aaa77`; running container was built pre-Phase-17 so still serves the old route. Required for TE-CAP-02 runtime proof per 17-01-PLAN.md Task 3 gate 5. | Pre-merge / runtime TE-CAP-02 closure |

## Session Continuity

Last session: 2026-05-24T00:00:27.599Z
Stopped at: Phase 17 context gathered
Resume file: .planning/phases/17-execution-cap-hard-enforcement/17-CONTEXT.md

## Operator Next Steps

- Plan Phase 16 (AUDIT-01 Validated-set re-audit) with `/gsd:plan-phase 16` — this phase gates all other v1.3 phases since it reconciles which Validated REQs are actually implemented.
