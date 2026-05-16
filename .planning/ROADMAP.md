# Roadmap: Crypto Trading Bot

## Milestones

- ✅ **v1.0** — Bootstrap & tape, integration suite, tournament harness, significance + auto-PR, ML post-V0 cleanup, dashboard safety + smoke (Phases 1, 2, 3, 4, 5, 6, 7, 7.1, 7.2) — shipped 2026-05-15
- 🚧 **v1.1 Path to LIVE** — Close carry-ins, pre-LIVE preflight, ML re-enablement gate, path-to-LIVE dashboard tile, CI recovery (Phases 8–12) — in progress

## Phases

<details>
<summary>✅ v1.0 (Phases 1–7.2) — SHIPPED 2026-05-15</summary>

- [x] Phase 1: Bootstrap & Recorded Tape (4/4 plans) — completed 2026-05-06
- [x] Phase 2: Integration Test Suite & RUNBOOK (10/10 plans) — completed 2026-05-08
- [x] Phase 3: Tournament Harness Core (9/9 plans) — completed 2026-05-09
- [x] Phase 4: Tournament Significance & Auto-PR (10/10 plans) — completed 2026-05-12
- [x] Phase 5: ML Cleanup (post-V0) (4/4 plans) — completed 2026-05-13
- [x] Phase 6: Dashboard Audit & Safety State (5/5 plans) — completed 2026-05-14
- [x] Phase 7: Tournament View & Smoke Test (6/6 plans) — completed 2026-05-14
- [x] Phase 7.1: Smoke Test Bugfixes (1/1 plan) — completed 2026-05-15
- [x] Phase 7.2: Phase3Dashboard Skeleton-Loader Fix (1/1 plan) — completed 2026-05-15

Full milestone archive: [`.planning/milestones/v1.0-ROADMAP.md`](milestones/v1.0-ROADMAP.md)
Audit: [`.planning/milestones/v1.0-MILESTONE-AUDIT.md`](milestones/v1.0-MILESTONE-AUDIT.md) (`gaps_found` — operator items + 1 unsatisfied REQ carried into v1.1)

</details>

### 🚧 v1.1 Path to LIVE (In Progress)

**Milestone Goal:** Close all v1.0 operator-blocked carry-ins and ratify the path-to-LIVE checklist with code-enforced preconditions, so flipping `TRADING_MODE=LIVE` becomes a verified four-step act rather than a leap of faith. Real-money LIVE trading is NOT a v1.1 deliverable — the gates and preconditions are.

- [ ] **Phase 8: Pre-LIVE Preflight** — CLI + HTTP API + trading-engine boot enforcement + CI workflow + RUNBOOK checklist for all 6 LIVE preconditions (includes unit tests and CI grep gates per PREFLIGHT-01/02 scope)
- [ ] **Phase 9: ML Re-enablement Gate** — 7-day evidence loop driver, startup auto-flip based on DSR>0.95 evidence row, structured disable-reason enum with Telegram digest (includes unit tests and CI grep gate per MLGATE-02 scope)
- [ ] **Phase 10: Path-to-LIVE Dashboard** — PathToLiveTile showing preflight + carry-in state, DO-NOT-FLIP/ALMOST/READY logic, Playwright smoke
- [ ] **Phase 11: Carry-In Closure** — Operator-runnable harnesses for all 5 v1.0 carry-ins; each closes with evidence row under `.planning/evidence/LIVECLOSE-*/`
- [ ] **Phase 12: CI Recovery** — Billing-failure detector workflow + first green CI runs of integration/tournament/dashboard-smoke after OP-04 resolved

## Phase Details

### Phase 8: Pre-LIVE Preflight
**Goal**: The path to LIVE is enforced in code, not only in docs — `scripts/preflight_live.py` CLI and `GET /api/preflight/live-readiness` HTTP endpoint both assert all 6 preconditions with structured JSON output; trading-engine refuses to boot LIVE if `MAX_POSITION_RISK_PCT > 2`; a CI workflow blocks any `live: requested` PR that fails preflight; and the RUNBOOK gains a Pre-LIVE operator checklist. All three enforcement layers (CLI/HTTP, boot-path, CI) ship with unit tests and CI grep gates so regressions fail loudly.
**Depends on**: Nothing (first v1.1 phase; builds on existing trading-engine codebase)
**Requirements**: PREFLIGHT-01, PREFLIGHT-02, PREFLIGHT-03, PREFLIGHT-04
**Success Criteria** (what must be TRUE):
  1. `python scripts/preflight_live.py --check=cap` exits 0 when `MAX_POSITION_RISK_PCT=2` and exits 1 when `MAX_POSITION_RISK_PCT=3`; JSON output contains `{"check": "cap", "status": "PASS"|"FAIL", "detail": "..."}` for each of the 6 checks.
  2. `GET /api/preflight/live-readiness` returns the same JSON schema as `preflight_live.py --json` (per-check PASS/FAIL object); it is reachable at `http://localhost:8000/api/preflight/live-readiness` when the api-gateway is running.
  3. Trading-engine container startup in `TRADING_MODE=LIVE` with `MAX_POSITION_RISK_PCT=3` logs `LIVE_PREFLIGHT_REJECTED reason=cap_too_high` and exits non-zero; startup with `MAX_POSITION_RISK_PCT=2` and all other flags correct proceeds normally. Unit test asserts both directions.
  4. `.github/workflows/preflight-live-readiness.yml` exists and blocks any PR labeled `live: requested` where `preflight_live.py --dry-run --target=HEAD` exits non-zero; CI result is posted as a PR check status.
  5. `RUNBOOK.md` contains a "Pre-LIVE Operator Checklist" section with Diagnose/Action/Verification rows for each of the 6 preconditions; PROJECT.md Out of Scope section cross-links to it.
  6. CI grep gate test fails if the `LIVE_PREFLIGHT_REJECTED` log emission is removed from the trading-engine startup path; grep gate is enforced in the same CI workflow that runs the unit tests from criterion 3, making silent removal of the enforcement detectable.
**Plans:** 5 plans
- [ ] 08-01-preflight-core-module-PLAN.md — preflight package: types, 6 checks, run_all aggregator, unit tests (foundation, Wave 1)
- [ ] 08-02-cli-and-http-route-PLAN.md — scripts/preflight_live.py CLI + trading-engine handler + api-gateway proxy + tests (Wave 2)
- [ ] 08-03-lifespan-cap-check-PLAN.md — main.py cap-check block + router mount + grep gates + lifespan tests (Wave 2)
- [ ] 08-04-ci-workflow-PLAN.md — .github/workflows/preflight-live-readiness.yml with PR-label gate (Wave 3)
- [ ] 08-05-runbook-and-crosslink-PLAN.md — RUNBOOK Pre-LIVE Operator Checklist + PROJECT.md cross-link (Wave 1, parallel with 08-01)

### Phase 9: ML Re-enablement Gate
**Goal**: The ML on/off decision is driven by code and evidence, not by human memory — `run_evidence_loop.py` manages the ≥7-day evidence accrual + PSR-CI publish idempotently; trading-engine startup auto-flips `ENABLE_ML_PREDICTIONS` based on a DSR>0.95 evidence row within the last 14 days and reverts on stale/drop; every "ML disabled" event logs a structured reason from a fixed enum. This auto-flip startup check ships with unit tests and a CI grep gate (MLGATE-02 scope) so the enforcement cannot be silently removed.
**Depends on**: Phase 8 (PREFLIGHT-01 defines the DSR evidence-row schema referenced in MLGATE-02 startup check)
**Requirements**: MLGATE-01, MLGATE-02, MLGATE-03
**Success Criteria** (what must be TRUE):
  1. `python scripts/forward_paper_test/run_evidence_loop.py` runs without error, is idempotent across restart (re-run produces no duplicate rows), and resumes from the last persisted row in `tournament_results`; running it twice in sequence produces the same final row count.
  2. Trading-engine startup with a `tournament_results` row where `dsr > 0.95` and `run_date` within 14 days logs `MLGATE_AUTO_FLIP direction=enabled reason=dsr_above_gate`; startup with no qualifying row logs `MLGATE_AUTO_FLIP direction=disabled reason=no_evidence`; unit tests assert both cases against a seeded SQLite row.
  3. Every emission of `ENABLE_ML_PREDICTIONS=false` in `technical-analysis` service logs include a `reason` field drawn strictly from the enum `{no_evidence, dsr_below_gate, evidence_stale, regime_shift, manual_override}`; a CI grep gate blocks any literal `"ML predictions disabled"` string that lacks the `reason=` field.
  4. Telegram daily digest aggregates ML-disabled reason counts (e.g., `no_evidence: 3, dsr_below_gate: 1`) and delivers to the configured Telegram chat; digest format is confirmed by a unit test that reads the rendered message template.
  5. CI grep gate test fails if the `MLGATE_AUTO_FLIP` log emission is removed from the trading-engine startup path; grep gate runs in the same CI workflow as the unit tests from criterion 2, ensuring the auto-flip enforcement is a permanent, detectable contract.
**Plans**: TBD

### Phase 10: Path-to-LIVE Dashboard
**Goal**: Operator sees every LIVE precondition and carry-in state on one screen without digging through logs — `PathToLiveTile.jsx` polls `/api/preflight/live-readiness` every 5 seconds and renders per-check PASS/FAIL/UNKNOWN rows; the same tile shows OP-01..04 + INFRA-02 carry-in close states from `/api/preflight/carry-ins`; the tile transitions through DO-NOT-FLIP (red) → ALMOST (amber) → READY (green) as conditions pass; a Playwright smoke confirms correct behavior in paper mode.
**Depends on**: Phase 8 (PREFLIGHT-01 endpoint `/api/preflight/live-readiness` and `/api/preflight/carry-ins` endpoint), Phase 9 (DSR evidence-row shape)
**Requirements**: DASHLIVE-01, DASHLIVE-02, DASHLIVE-03, DASHLIVE-04
**Success Criteria** (what must be TRUE):
  1. `PathToLiveTile.jsx` renders in the React dashboard; each of the 6 PREFLIGHT checks appears as a labeled row with PASS (green), FAIL (red), or UNKNOWN (grey) chip on a 5-second poll against `GET /api/preflight/live-readiness`.
  2. The tile also renders OP-01, OP-02, OP-03, OP-04, and INFRA-02 carry-in close states (open/closed) sourced from `GET /api/preflight/carry-ins`, backed by `.planning/state/carry_ins.json` or git tags under `carry-in/closed/<id>`.
  3. Tile renders "DO NOT FLIP" with red background when any PREFLIGHT check is FAIL or UNKNOWN; renders "ALMOST" with amber background when all checks PASS but the 24h continuous-PASS window is not yet satisfied (tracked as a timestamped state record in `carry_ins.json`); renders "READY" with green background only after all checks have been PASS for ≥24h continuously (verified by timestamp comparison at poll time).
  4. `pytest tests/e2e/test_path_to_live_smoke.py` passes — validates tile renders in PAPER mode, preflight endpoint returns expected JSON shape, and DSR evidence-row schema (columns `dsr`, `run_date`) is asserted against the seeded `tournament_results` test fixture; smoke runs in `dashboard-smoke.yml` CI.
**Plans**: TBD
**UI hint**: yes

### Phase 11: Carry-In Closure
**Goal**: Every v1.0 operator-blocked carry-in has an explicit closure harness that produces a verifiable evidence row — LIVECLOSE-01 (fresh-clone checkpoint), LIVECLOSE-02 (first green ML-on CI run), LIVECLOSE-03 (7-day forward-paper-test accrual), LIVECLOSE-04 (T0.1.x sweep verdict), LIVECLOSE-05 (LIVE-flip manual smoke). Each closes via an operator-runnable procedure with structured evidence committed to `.planning/evidence/LIVECLOSE-*/`. Phase delivers the harnesses and documented closure paths; operator execution of wall-clock-bound items (LIVECLOSE-02, LIVECLOSE-03) is expected to extend beyond phase code completion and is marked `human_needed` in VERIFICATION.md.
**Depends on**: Phase 9 (MLGATE-01 `run_evidence_loop.py` driver must exist before LIVECLOSE-03 accrual can run), Phase 10 (DASHLIVE visible in dashboard before LIVECLOSE-05 LIVE-flip smoke so operator sees preflight state during smoke run)
**Requirements**: LIVECLOSE-01, LIVECLOSE-02, LIVECLOSE-03, LIVECLOSE-04, LIVECLOSE-05
**Success Criteria** (what must be TRUE):
  1. LIVECLOSE-01 — Operator runs `bash bootstrap.sh` against a fresh `git clone` into a tmp directory twice; both runs produce a log line matching `BYBIT_PRICE_SOURCE: mode=tape` and a 15-service health snapshot; output committed under `.planning/evidence/LIVECLOSE-01/run-1.txt` and `run-2.txt`. (human_needed checkpoint: operator execution required)
  2. LIVECLOSE-02 — GitHub Actions shows a green CI run for `integration-ml-on.yml` nightly variant; the CI run URL is linked in `.planning/evidence/LIVECLOSE-02/ci-url.txt`; evidence committed. (human_needed checkpoint: requires OP-04 billing resolution)
  3. LIVECLOSE-03 — `tournament_results` table contains ≥7 consecutive trading-day rows for at least one forward-paper-test feature with `psr_ci_published=true`; the row set is exported to `.planning/evidence/LIVECLOSE-03/psr-evidence.json`. (human_needed checkpoint: ≥7 wall-clock days required)
  4. LIVECLOSE-04 — After OP-02 (migration 005) and OP-03 (reader password) are applied, T0.1.x sweep re-runs; `tournament_results` shows verdict `PASS` or `FAIL` (not `INSUFFICIENT_DATA`) with a bootstrap p-value persisted in the row; verdict screenshot committed under `.planning/evidence/LIVECLOSE-04/`. (human_needed checkpoint: requires OP-02 + OP-03 operator actions)
  5. LIVECLOSE-05 — Operator force-recreates api-gateway with `TRADING_MODE=LIVE`; dashboard screenshot shows rose viewport outline + red MODE pill + KILL-SWITCH state; operator reverts and commits screenshot under `.planning/evidence/LIVECLOSE-05/`. (human_needed checkpoint: operator execution required)
**Plans**: TBD

### Phase 12: CI Recovery
**Goal**: Once GH Actions billing is resolved, CI regressions are detectable automatically and the three blocked CI jobs produce their first green runs — `billing-failure-detector.yml` workflow runs every 6h and creates a GitHub Issue + Telegram alert on billing failure detection; first green runs of `integration-ml-on.yml`, `tournament-harness.yml`, and `dashboard-smoke.yml` are linked as evidence. The billing detector ships regardless of OP-04 state; CIRESTORE-02 green-run evidence is `awaiting-checkpoint` until OP-04 is resolved.
**Depends on**: Phase 11 (CIRESTORE-01 is an operator carry-in close confirmation that pairs with LIVECLOSE-02; structurally Phase 12 can begin code work in parallel, but CIRESTORE-02 evidence waits on OP-04)
**Requirements**: CIRESTORE-01, CIRESTORE-02, CIRESTORE-03
**Success Criteria** (what must be TRUE):
  1. CIRESTORE-01 — Operator confirms GH Actions billing resolved; `.planning/evidence/OP-04/billing-screenshot.png` committed with visible timestamp on the billing page. (human_needed checkpoint: operator action)
  2. CIRESTORE-02 — Three green CI run URLs committed to `.planning/evidence/CIRESTORE-02/`: one each for `integration-ml-on.yml` nightly variant, `tournament-harness.yml`, and `dashboard-smoke.yml`. (human_needed checkpoint: requires OP-04 billing resolution)
  3. `.github/workflows/billing-failure-detector.yml` runs on `schedule: cron: '0 */6 * * *'`; on detecting a run with `billing` substring in failure reason via `gh run list --status failure --limit 5`, it posts to the Telegram notification path and creates a GitHub Issue labeled `ops: billing`; behavior is asserted by a unit test that mocks `gh run list` output containing `billing`.
**Plans**: TBD

## Progress

**Execution Order:** 8 → 9 → 10 → 11 → 12

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Bootstrap & Recorded Tape | v1.0 | 4/4 | Complete | 2026-05-06 |
| 2. Integration Test Suite & RUNBOOK | v1.0 | 10/10 | Complete | 2026-05-08 |
| 3. Tournament Harness Core | v1.0 | 9/9 | Complete | 2026-05-09 |
| 4. Tournament Significance & Auto-PR | v1.0 | 10/10 | Complete | 2026-05-12 |
| 5. ML Cleanup (post-V0) | v1.0 | 4/4 | Complete | 2026-05-13 |
| 6. Dashboard Audit & Safety State | v1.0 | 5/5 | Complete | 2026-05-14 |
| 7. Tournament View & Smoke Test | v1.0 | 6/6 | Complete | 2026-05-14 |
| 7.1. Smoke Test Bugfixes | v1.0 | 1/1 | Complete | 2026-05-15 |
| 7.2. Phase3Dashboard Skeleton-Loader Fix | v1.0 | 1/1 | Complete | 2026-05-15 |
| 8. Pre-LIVE Preflight | v1.1 | 0/5 | Not started | - |
| 9. ML Re-enablement Gate | v1.1 | 0/TBD | Not started | - |
| 10. Path-to-LIVE Dashboard | v1.1 | 0/TBD | Not started | - |
| 11. Carry-In Closure | v1.1 | 0/TBD | Not started | - |
| 12. CI Recovery | v1.1 | 0/TBD | Not started | - |
