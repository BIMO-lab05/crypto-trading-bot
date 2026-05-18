# Phase 8 Discussion Log — Pre-LIVE Preflight

> Recorded 2026-05-16 via `/gsd-discuss-phase 8`. Session ran in no-questions mode per user instruction ("work without stopping for clarifying questions; make the reasonable call and continue"). This log captures the gray areas identified, the decisions made, and the rationale Claude used so the user can audit and override.

## Mode

- **Mode used:** no-questions / auto-locked decisions.
- **Why:** User issued an active session instruction to proceed without prompting. No SPEC.md or prior CONTEXT.md existed for this phase.
- **Audit hook:** Every locked decision in `08-CONTEXT.md` includes the file-path/line-number evidence used to make it; user can revisit and flip any decision before plan-phase.

## Gray Areas Identified

1. **Preflight execution surface — CLI vs HTTP source of truth.** Should the CLI shell out to the HTTP endpoint, the HTTP endpoint shell out to the CLI, or should both import a shared module?
2. **Per-trade cap enforcement location.** Pydantic `model_validator` on Settings, lifespan boot-path check, or middleware?
3. **DSR evidence-row source table.** REQUIREMENTS.md says `tournament_results`; codebase has `leaderboard`. Which is authoritative?
4. **CI workflow scope.** Run on every PR vs only on labelled PRs?
5. **DSR check #6 semantics.** Latest row vs 14-day window vs PSR-CI flag?
6. **JSON schema versioning.** Schemaless dict vs versioned + Pydantic-validated?
7. **Preflight HTTP route authentication.** Admin-only (matches sensitive ops endpoints) vs unauthenticated read-only (matches `/api/config/safety-state`)?
8. **Grep gate location.** New CI workflow vs pytest under `tests/integration/`?

## Decisions Locked

| # | Area | Decision | Evidence |
|---|------|----------|----------|
| 1 | Source of truth | Shared module `services/trading-engine/app/preflight/`; CLI + HTTP both import it. No subprocess. | RETROSPECTIVE.md Lesson 3 (eager-import-swallowed-ImportError); avoid CLI/runtime drift. |
| 2 | Cap enforcement | Lifespan boot-path check at `services/trading-engine/app/main.py:258` (immediately after `LIVE_TRADING_ACK`). | Co-location with existing four-flag gate; matches v1.0 defence-in-depth pattern. |
| 3 | DSR source | Existing `leaderboard` table (`services/tournament-harness/migrations/0001_initial.sql:23,41`). REQUIREMENTS.md `tournament_results` is wording bug — update in plan. | Schema reality. |
| 4 | CI scope | Run on every PR (lint+unit); enforce only on PRs labelled `live: requested`. | Simplest operator mental model; zero skip cost for unlabelled. |
| 5 | DSR #6 semantics | Phase 8 reads latest `leaderboard` row + checks Phase 9 marker `/run/mlgate_auto_flip.json`; reports `UNKNOWN` if marker missing. 14-day rule is MLGATE-02 (Phase 9). | Clean phase boundary; UNKNOWN is a terminal state. |
| 6 | JSON schema | Versioned (`schema_version: 1`); dataclass-backed; identical shape for CLI `--json` and HTTP body. | Phase 10 (DASHLIVE) needs stable schema for per-check rendering. |
| 7 | HTTP auth | Unauthenticated read-only (matches `/api/config/safety-state` D-09 pattern at api-gateway:1049). | Same precedent: no secrets, no balances, no positions. |
| 8 | Grep gates | Pytest tests under `tests/integration/test_preflight_grep_gates.py`. | Established v1.0 pattern (TOURN-07, MLCL-03); no new CI infra. |

## Scope Creep Caught (and Redirected)

None encountered. All considered ideas mapped cleanly to existing phases or out-of-scope per REQUIREMENTS.md.

## Carried Forward From v1.0

- **Defence-in-depth boot-path assertion** (lifespan + CLI + grep gate) — RETROSPECTIVE.md Lesson 3.
- **CI grep gate paired with every "removed permanently" claim** — RETROSPECTIVE.md Lesson 1; TOURN-07 model.
- **`leaderboard` table reality** vs REQUIREMENTS.md `tournament_results` wording — flagged for plan-phase correction.
- **`/api/config/safety-state` unauthenticated read-only D-09 pattern** — adopted directly for preflight endpoint.
- **`LIVE_TRADING_ACK` four-flag pattern** — extended, not replaced; the cap check joins the chain at line 258.

## Deferred Ideas (Captured, Not Acted On)

- Slack notification on preflight FAIL (defer until Phase 10 dashboard tile lands).
- 24h continuous-PASS window logic (DASHLIVE-03 / Phase 10).
- `tournament_results` table rename or migration (none — `leaderboard` is the source; REQUIREMENTS.md wording fix only).
- `psr_ci_published` column add (MLGATE-01 / Phase 9).

## Open Question Left for Plan-Phase

- **Preflight HTTP route ownership.** Locked recommendation: trading-engine owns the route; api-gateway proxies. If trading-engine is unreachable, all 6 checks return `UNKNOWN` (never PASS-on-fallback). Confirm with the user during plan-phase only if planner finds a conflicting constraint; otherwise proceed.

## Outcome

`08-CONTEXT.md` written with locked decisions + boundaries + canonical refs. Plan-phase can proceed without re-asking these questions. User can override any locked decision by editing `08-CONTEXT.md` directly before running `/gsd-plan-phase 8`.

---
*End of discussion log.*
