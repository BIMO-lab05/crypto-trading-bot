---
gsd_state_version: 1.0
milestone: v1.3
milestone_name: TA + Engine Correctness
status: executing
stopped_at: Phase 18 complete (plans + code review + fixes committed); uncommitted out-of-band work pending triage
last_updated: "2026-07-29T00:00:00.000Z"
last_activity: 2026-07-29 -- resume: Phases 16/17/18 confirmed complete; ~2.3k uncommitted service-code insertions from two out-of-band sessions detected
progress:
  total_phases: 9
  completed_phases: 3
  total_plans: 12
  completed_plans: 12
  percent: 33
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-23 after v1.3 milestone open)

**Core value:** The bot must never lose money it wasn't authorized to risk; every "edge" claim must be backed by DSR/CPCV evidence on returns, not raw R² on price levels.
**Current focus:** Triage of uncommitted out-of-band work (2026-07-28 / 2026-07-29 sessions) before opening Phase 19

## Current Position

Phase: 18 (Bybit-Adapter Contract Fix) — COMPLETE (3/3 plans, 18-REVIEW.md + 18-REVIEW-FIX.md, 9/9 in-scope findings fixed, e2e verify commit `2aac085`)
Plan: —
Status: Between phases. Next planned phase is 19 (Order Reconciliation + Idempotency), but see "Out-of-Band Work" below — Phase 19–24 premises need re-checking against uncommitted code first.
Last activity: 2026-07-29 -- resume session; state reconciled

Note: Phase 18 has no `18-VERIFICATION.md` while `workflow.verifier: true` and Phase 17 carries `17-VERIFICATION.md`. Gap, not a blocker.

## Out-of-Band Work (detected 2026-07-29, UNCOMMITTED)

Two audit/fix sessions ran outside GSD phase tracking and their output is **not committed**:

- `FIXES_2026-07-28_COMPREHENSIVE.md` (untracked) — trading-engine cash-accounting repair (reduce_only honoring, SHORT close inversion, TP payout, partial exits, kill-switch on equity, 48h max-hold, LIVE stop-loss path, daily-loss rollover, consensus-gate HOLD counting, per-trade cap clamp + hard 2% LIVE), TA indicator fixes, testnet-pollution DB repair script, frontend fixes.
- `AUDIT_2026-07-29_PRODUCTION_REVIEW.md` (untracked) — Bybit HMAC signature-over-transmitted-bytes fix (`bybit_rest_client.py`), auth on state-changing gateway endpoints (mode-gated), rate limiter, nan/inf validation in connector models, perf/UX/refactor items.

Scale: 367 changed paths (314 modified, 52 untracked, 1 deleted); ~2,306 insertions / 967 deletions across `services/` + `frontend/` alone. Backups written to session scratchpad: `wip-2026-07-29.patch` (tracked modifications), `wip-code-only.patch` (services/frontend/tests/backtesting/scripts subset), `wip-untracked.tgz` (161 untracked paths incl. both standalone test harnesses, `scripts/repair_testnet_pollution.{sh,sql}`, `backtesting/validate_mr_rr_fix.py`, both audit reports). **Scratchpad is ephemeral — not a substitute for a commit.**

**Validation status: INDEPENDENTLY VERIFIED 2026-07-29 — substantive claims hold.** Full record: `.planning/evidence/wip-verification-2026-07-29.md`. Confirmed by re-run: accounting harness 28/28, indicator harness 16/16, api-gateway 437/437 in-container, frontend build (2635 modules) + project lint (0 errors), 8/9 services 200, max mainnet BTC close exactly $82,791.20 with the $1.76M artefact gone. **No regression traceable to this work** — `test_repositories.py` and `test_pairs_trading.py` behave identically against a clean HEAD worktree; the 62 tests across WIP-modified + Phase-18 files all pass.

Reporting discrepancy (not a defect): the reports' failure accounting is internally consistent — 9 pre-existing + 2 since-fixed = the 11 in `cowork_run/te_pytest2.log` — but `cowork_run/STATUS.txt` line 5a records `5a. trading-engine pytest FAILED (exit 2)` while the report presents that suite as validated. Both of the 2 since-fixed files are green on re-run here.

Security gate verified: `auth_middleware.py:40-64` fails **closed** — auth becomes mandatory on `TRADING_MODE=LIVE`, `PAPER_TRADING_MODE=false`, or `ENVIRONMENT in {production, staging}`. Residual footgun: an explicit `REQUIRE_API_AUTH=false` overrides even LIVE; worth a boot-time hard-fail like the JWT one.

**New problems found during verification** (neither report mentions them): `docker exec crypto-bot-trading pytest tests/` collects **zero** tests — 4 fatal collection errors (`tests/integration/conftest.py:47` `database` import via a host-only `parents[5]/shared` path with `/app/shared` empty; `test_bybit_adapter_wr01_wr04.py` + `test_exchanges.py` missing **PyJWT in the image**; `test_config_default_on_gate.py:48` `parents[3]` IndexError). Also: the new untracked `services/trading-engine/.dockerignore` excludes `tests/standalone/`, so the next rebuild deletes the accounting-harness evidence base from the container.

Provenance: produced by an external "cowork" agent run on 2026-07-29 14:04–18:24, transferred in as tarballs (`_to_delete/*.tar.gz`), evidence logs in `cowork_run/`.

### Overlap with planned phases (checked in working tree 2026-07-29)

| REQ | Phase | Still owed? | Evidence |
|---|---|---|---|
| PAPER-01 (slippage model) | 20 | YES | no `slippage` symbol in `paper_trading.py` |
| PAPER-02 (SL/TP trigger + monotonic id) | 20 | PARTIAL | monotonic id owed (`paper_trading.py:173` still `f"PAPER_{symbol}_{side}"`). **Trigger evaluation exists and fires for paper** — `position_manager.check_all_exit_conditions()` (`:589`) via `auto_trader.py:2725` in `_monitor_positions()` (`:2533`), loop-driven at `:916`/`:926`, no mode gate. Predates this work (`0d0271c`, 2025-11-30) |
| PAPER-03 (Jan-2026 regression tests) | 20 | YES | `tests/test_jan_2026_fixes_regression.py` absent |
| TA-AGG-01 (ADX/SQZMOM/Volume in vote) | 21 | YES | 0 ADX refs in `handlers/analysis.py` |
| TA-AGG-02 (MACD 5/35/5 single source) | 21 | PARTIAL | `main.py:291-293` values are canonical 5/35/5 but still **hardcoded** `Query(default=…)`, not `settings.macd_*` — value drift gone, single-source requirement still owed |
| TA-AGG-03 (BB std-dev 2.5) | 21 | PARTIAL | `main.py:314` `Query(default=2.5)` — same shape: right value, still not sourced from `settings.bollinger_std_dev` |
| PRICE-01/02 (`round(price, 2)`) | 22 | YES (widened) | **22** price-domain sites across 7 files, incl. `app/utils/support_resistance_detector.py` (6) which the 2026-05-23 audit missed entirely and PRICE-01's "strategy files" scope would not have covered |
| RECON-01/02 (reconciliation + orderLinkId) | 19 | YES | connector model accepts `orderLinkId`; no generator in adapter/engine |
| HYG-01 (sentiment weight log) | 24 | YES | `auto_trader.py:1131,1262` still say "Sentiment 15%" |
| HYG-03 (TA CORS lockdown) | 24 | YES | TA `main.py:224` still `allow_origins=["*"]` |

Phase 18's committed files (`bybit_adapter.py`, `tape_replay_client.py`, `test_bybit_adapter_contract.py`) are **disjoint** from the uncommitted set; the one shared file (`bybit-connector/app/models.py`) is additive — Phase 18's camelCase aliases survive at `models.py:69-81`.

**Consequence for planning:** ROADMAP premise text cites line numbers and behaviors the 2026-07 work has changed.

- **Phases 20, 21, 22 re-scoped 2026-07-30** — see the `> Re-scoped` blocks in their ROADMAP detail sections and the annotated REQUIREMENTS entries. Summary: PAPER-02 and PAPER-03 shrink (trigger evaluation and stop-loss-as-limit coverage already exist); TA-AGG-02/03 shrink from value-reconciliation to remove-the-literal; PRICE-01/02 **grow** — 22 sites across 7 files, one file and one regex class previously uncovered.
- **Phase 24 still un-re-scoped.** HYG-01 and HYG-03 confirmed still owed above, but the premise line numbers were not re-derived.
- **Phase 23 likely stale too, not re-derived.** Its premise cites `ml-retraining-service/app/core/model_trainer.py:430,623` and `feature_engineer.py:32,283`, while `ml-prediction-service/app/main.py` and `ml_models/gru_model.py` were both modified in commit `0214482`. Re-verify before planning.

### New operator actions from the out-of-band reports

| ID | Action | Source |
|---|---|---|
| OP-07 | Decide provenance + disposition of the 367 uncommitted paths (commit in groups / discard / partial) | resume 2026-07-29 |
| OP-08 | `bash scripts/repair_testnet_pollution.sh` before trusting any signal or backtest | FIXES §5 |
| OP-09 | Rebuild + restart `trading-engine technical-analysis market-data api-gateway frontend` (stale in-memory state = false pass) | FIXES §5 |
| OP-10 | ~~Re-run claimed validation~~ — **DONE 2026-07-29**, see `.planning/evidence/wip-verification-2026-07-29.md` | FIXES §5 |
| OP-11 | No frontend login flow — blocks any LIVE flip (auth gated open in local paper mode) | AUDIT §5 |
| OP-12 | 9 pre-existing trading-engine test failures (2 adapter source-contract, 5 backtest source-marker, 2 stale `mock.patch` targets) | AUDIT §5 |
| OP-14 | trading-engine image is missing **PyJWT** and `/app/shared` is empty — `docker exec crypto-bot-trading pytest tests/` collects zero tests. Add `PyJWT` to the image and fix the `shared/` copy, or the in-container suite (the CLAUDE.md-mandated env) stays unusable. | resume 2026-07-29 |
| OP-15 | New untracked `services/trading-engine/.dockerignore` excludes `tests/standalone/` — next rebuild removes the 28-check accounting harness from the container. Decide: drop that line, or accept host-only harness runs. | resume 2026-07-29 |
| OP-13 | `.planning/state/carry_ins.json` is mode `600`, owned by uid `999` (`systemd-journal`) — unreadable by the repo user. It aborted `git diff` this session and will likely break `gsd-sdk query init.resume` / next GSD command. Fix ownership (`sudo chown $USER:$USER .planning/state/carry_ins.json`) before running `/gsd:plan-phase 19`. | resume 2026-07-29 |

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

Last session: 2026-07-29 (resumed)
Stopped at: Phase 18 closed out (commits `5faa32e`..`2aac085`). Resume surfaced 367 uncommitted paths from an external cowork run; operator chose verify-then-commit. Verification complete and passing — awaiting approval of commit groupings (OP-07), then re-scope Phases 20–22 against the settled tree.
Resume file: .planning/evidence/wip-verification-2026-07-29.md

## Operator Next Steps

- Plan Phase 16 (AUDIT-01 Validated-set re-audit) with `/gsd:plan-phase 16` — this phase gates all other v1.3 phases since it reconciles which Validated REQs are actually implemented.
