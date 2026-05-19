# Milestones

## v1.1 Path to LIVE (Shipped: 2026-05-18)

**Phases completed:** 5 phases (8, 9, 10, 11.1, 12 — Phase 11 superseded by 11.1), 19 plans, 32 tasks
**Timeline:** 2026-05-15 → 2026-05-18 (~4 days post v1.0 tag)
**Git range:** 138 commits since v1.0 tag, 339 files changed (+31,072 / −47,475 LOC; 92 code files in services/scripts/tests/.github/frontend with +14,522 / −574)
**Audit status:** `gaps_found` reconciled at close — audit dated 2026-05-18T02:55Z predates Phase 11.1 + 12 wave-3 verification; manually reconciled before archive. Net post-Phase-12 reality: **17/19 v1.1 deliverables shipped** (12 complete + 5 harness-delivered; 2 operator-blocked on OP-04 GH Actions billing).

### What Shipped

1. **Pre-LIVE preflight (Phase 8, 5 plans)** — `app/preflight/{types,checks,run_all}.py` core module with 6 checks; `scripts/preflight_live.py` CLI + `GET /api/preflight/live-readiness` HTTP route (gateway-proxied); `services/trading-engine` lifespan `cap_check` refuses LIVE boot when `MAX_POSITION_RISK_PCT > 0.02` (logs `LIVE_PREFLIGHT_REJECTED reason=cap_too_high`); `.github/workflows/preflight-live-readiness.yml` PR-label gate (`live: requested`); `RUNBOOK.md` Pre-LIVE Operator Checklist (6 Diagnose/Action/Verification subsections); two CI grep gates pin the enforcement against silent removal; boundary-agreement test guards the two intentionally-duplicate 0.02 thresholds.
2. **ML re-enablement gate (Phase 9, 3 plans)** — `scripts/forward_paper_test/run_evidence_loop.py` idempotent ≥7-day driver + migration `0002_mlgate_evidence_columns.sql` adding `run_date` + `psr_ci_published` to `leaderboard`; trading-engine startup `auto_flip_ml_predictions()` reads DSR>0.95 evidence within 14 days and writes `/run/mlgate_auto_flip.json` schema_version=1 marker + structured `MLGATE_AUTO_FLIP direction=X reason=Y` log; 5-member `MLGateReason` enum (`no_evidence|dsr_below_gate|evidence_stale|regime_shift|manual_override`); cross-plan reason-state cache; unauth read-only `/api/preflight/ml-gate-reason-counts`; notification-service scheduled Telegram digest (in-process Python call to `alert_manager.send_daily_summary`, not through admin-guarded HTTP — regression test pins the contract).
3. **Path-to-LIVE dashboard (Phase 10, 3 plans)** — `api-gateway` `GET /api/preflight/carry-ins` (schema_version=1) backed by atomic file-state machine at `.planning/state/carry_ins.json` (RW parent-dir bind-mount per WSL gotcha); two react-query hooks (`useLiveReadiness`, `useCarryIns`) verbatim from `useSafetyState` idiom (5s poll, retry=2); `PathToLiveTile.jsx` (banner + 6 PREFLIGHT chip rows + 5 carry-in rows + 24h continuous-PASS footer); banner tokens `bg-rose-700 / bg-amber-600 / bg-emerald-700`; pytest-playwright Chromium smoke (7 D-10-18 assertions); two defence-in-depth grep gates; `.github/workflows/dashboard-smoke.yml` with PR paths filter.
4. **Carry-in closure harnesses (Phase 11.1, 7 plans)** — Plan-1 closed-for-extension contract: Draft 2020-12 JSON Schema (`.planning/evidence/_schema.json`) + `scripts.closure._common.write_evidence()` helper auto-injecting `schema_version=1` + ISO-8601 UTC timestamp; five operator-runnable harnesses each emitting schema-validated evidence JSON: `liveclose-01-fresh-clone.sh` (double-bootstrap + `BYBIT_PRICE_SOURCE: mode=tape` grep), `liveclose-02-record-ci.sh` (gh-api validation of integration-ml-on.yml conclusion=success), `liveclose_03_psr_evidence.py` (≥7-consecutive-day window query on `leaderboard`), `liveclose_04_sweep_verdict.py` (decision_note.md verdict + significance.json p-values), `liveclose-05-live-flip-smoke.sh` (two-key authorized, EXIT-trap revert, supervised-run-only); `scripts/closure/run-all.sh` orchestrator (whitelisted `--exec` LIVECLOSE-01..04, refuses LIVECLOSE-05 auto-invocation); `LIVECLOSE-INDEX.md` fully wired (zero `<filled-by-plan-7>` tripwire tokens at close); 14 integration tests bolt the wiring contract into CI.
5. **CI recovery (Phase 12, 1 plan)** — `.github/workflows/billing-failure-detector.yml` cron-driven (every 6h) with self-trigger-safe naming (jq filter excludes own workflow name); direct curl to api.telegram.org (in-cluster notification-service unreachable from GitHub-hosted runners) + `gh issue create` with `ops: billing` label; 12-test grep-gate net pins the contract; evidence-dir scaffolds for the two operator-blocked carry-ins (CIRESTORE-01 OP-04 billing screenshot path + CIRESTORE-02 three green CI run URLs).

### Requirements Coverage (Reconciled 3-state)

- **Complete (12/19)** — code + evidence verified: PREFLIGHT-01..04, MLGATE-01..03, DASHLIVE-01..04, CIRESTORE-03.
- **Harness-delivered (5/19)** — code/harness shipped, operator wall-clock execution remaining: LIVECLOSE-01 (fresh-clone × 2), LIVECLOSE-02 (CI URL after OP-04), LIVECLOSE-03 (≥7-day accrual), LIVECLOSE-04 (sweep verdict after OP-02 + OP-03), LIVECLOSE-05 (supervised LIVE-flip smoke).
- **Operator-blocked (2/19)** — external precondition not met (OP-04 GH Actions billing): CIRESTORE-01, CIRESTORE-02.

### Known Gaps at Close (operator wall-clock only — no code debt)

| Category | Item | Owner | Blocks |
|---|---|---|---|
| Operator action | OP-01 — LIVE-flip manual smoke (LIVECLOSE-05 harness execution) | operator | LIVECLOSE-05 evidence |
| Operator action | OP-02 — apply migration 005 (`tournament_reader` role) | operator | LIVECLOSE-04 verdict |
| Operator action | OP-03 — set `TOURNAMENT_READER_PASSWORD` + force-recreate harness | operator | LIVECLOSE-04 verdict |
| Operator action | OP-04 — resolve GitHub Actions billing | operator | LIVECLOSE-02, CIRESTORE-01, CIRESTORE-02 |
| Operator action | INFRA-02 checkpoint — fresh tmp clone bootstrap × 2 (LIVECLOSE-01 harness execution) | operator | LIVECLOSE-01 evidence |
| Verification | Phase 08 VERIFICATION.md status = `human_needed` (2 manual-only smokes: container-restart for cap rejection + curl /api/preflight/live-readiness through deployed api-gateway) | operator | Phase 08 final sign-off |
| Docs lag | None at close — REQUIREMENTS.md status table reconciled to 3-state taxonomy before archive | — | — |

### Key Decisions (Outcome ✓ Good unless marked)

- ✓ Phase 11 umbrella → Phase 11.1 harnesses-only — keep harness-delivery distinct from wall-clock operator execution so the milestone closes on code-deliverable scope rather than on operator wall-clock.
- ✓ 3-state requirements taxonomy at close (complete/harness-delivered/operator-blocked) — collapses the four-source-of-truth conflict identified by advisor pre-archive.
- ✓ MLGATE-02 cold-boot graceful degradation — `/run/mlgate_auto_flip.json` marker absent on first boot causes `check_dsr_evidence` to return UNKNOWN, not error. HTTP route mount happens after `init_ml()` so the gate is only reachable post-marker.
- ✓ Scheduler in-process Python call (notification-service → trading-engine via `alert_manager.send_daily_summary` direct invocation, NOT admin-guarded HTTP) — regression test pins the contract.
- ✓ Self-trigger-safe cron-monitor pattern for billing-failure-detector — workflow name must not contain its own substring filter; defense-in-depth `jq select(.name != own_name)`.
- ✓ Direct curl to api.telegram.org from GH Actions runners — in-cluster notification-service unreachable from GitHub-hosted runners (forced design).
- ✓ LIVECLOSE-05 supervised-run-only — `scripts/closure/run-all.sh` explicit refusal of `--exec liveclose-05`. Two-key authorization (`--i-understand-this-flips-live` + `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`) on the harness itself.
- ✓ Evidence JSON Schema closed for extension after Wave 1 (Phase 11.1-01) — Wave 2 plans consume `_schema.json` + `_common.py` read-only.
- ⚠ Carries forward: ML predictions remain `ENABLE_ML_PREDICTIONS=false` until DSR > 0.95 evidence lands via the gate. Auto-flip is *armed* but no qualifying row exists in `leaderboard` yet (LIVECLOSE-03 wall-clock).
- ⚠ Carries forward: 10% per-trade cap relaxed for paper mode (ADR-010) — pre-LIVE checklist (RUNBOOK Pre-LIVE Operator Checklist) must restore ≤2% before flipping `TRADING_MODE=LIVE`. Phase 8 enforces this in trading-engine boot.

### Audit & Verification Artifacts

- Audit: `.planning/milestones/v1.1-MILESTONE-AUDIT.md` (status `gaps_found`, audited 2026-05-18T02:55Z; predates Phase 11.1 + 12 wave-3 verification — reconciled at close)
- Archived ROADMAP: `.planning/milestones/v1.1-ROADMAP.md`
- Archived REQUIREMENTS: `.planning/milestones/v1.1-REQUIREMENTS.md`
- All 5 phases: VERIFICATION.md present (4 verified, 1 human_needed = Phase 08); VALIDATION.md present (3/3 nyquist-compliant on completed phases 8/9/10; 11.1 + 12 verified via VERIFICATION); SECURITY.md present (3/3 verified, 0 open threats on completed phases 8/9/10).

---

## v1.0 (Shipped: 2026-05-15)

**Phases completed:** 9 phases (1, 2, 3, 4, 5, 6, 7, 7.1, 7.2), 50 plans, 67 tasks
**Timeline:** 2026-05-06 → 2026-05-15 (~9 days)
**Git range:** 427 commits, 764 files changed (+159,471 / -2,816 LOC)
**Audit status:** `gaps_found` (acknowledged — 4 operator-blocked items + INFRA-02 checkpoint carry into v1.1)

### What Shipped

1. **Bootstrap & recorded tape (Phase 1)** — 10 JSONL fixtures (5 symbols × klines + ticker, 844KB) captured from Bybit mainnet; `TapeReplayClient` JSONL replay loader with `MARKET_DATA_SOURCE=tape|live` selector wired into `bybit-connector` lifespan; `bootstrap.sh` fresh-clone boot of all 15 services with `DOCKER_BUILDKIT=0` WSL2 guard and EMERGENCY_STOP race-prevention.
2. **Integration suite + RUNBOOK (Phase 2)** — `pytest tests/integration` from fresh tmp clone (`test_fresh_clone_round_trip.py` 3 tests, asserts services healthy + tape prices + paper-trade <60s + notification delivers); `scripts/iter-fix.sh` + `iter-fix-check-diff.sh` checkpointed iteration anti-mock guard (10/10 tests); 6-symptom `RUNBOOK.md` in Diagnose/Action/Verification format; `.github/workflows/integration.yml` + `integration-ml-on.yml`.
3. **Tournament harness core (Phase 3)** — Docker-isolated SQLite leaderboard orchestrator (`launcher.py`, `mem_limit` + `nano_cpus` + `read_only=True` + `cap_drop=ALL`); `migrations/0001_initial.sql` composite PK `(architecture, symbol, horizon, target_mode, hp_hash, run_id)` with `r2_returns`, `dir_acc_corrected`, `oos_sharpe`, `psr`, `dsr`, `cpcv_dsr`, `git_sha`; failure-row persistence (`failure.py` D-15 enum); `metrics_bridge.py` imports canonical metrics only (TOURN-07 CI grep gate enforced).
4. **Significance + auto-PR (Phase 4)** — `select_top_n_per_symbol` DSR-desc tiebreak; Politis–Romano stationary block bootstrap with additive smoothing (p<0.05 on OOS Sharpe + `dir_acc_corrected`); `gh pr create --draft` only path; `tournament reproduce` CLI with idempotency check; `test_no_auto_merge.py` + `test_no_legacy_r2_criterion.py` grep gates.
5. **ML post-V0 cleanup (Phase 5)** — `scripts/forward_paper_test/{profiles,psr_ci,run_isolation}.py` apparatus + per-feature `PSR_CI_PUBLISHED` default-on gate (37 tests); T0.1.x `different_horizon` sweep YAML shipped (12 cells, verdict `INSUFFICIENT_DATA` pending operator OP-02/OP-03); `scripts/monitoring/` tier-2 (`tier2_escalate.sh`, `tier2_mission.md`, `auto_pr_janitor.sh`) deleted per STRIDE analysis (ADR-011); `run_extended_backtest.py` PERMANENT DIVERGENCE docstring + `_emit_divergence_warning()` runtime log (ADR-012); 4-test `claude -p` grep gate prevents regression.
6. **Dashboard safety + smoke (Phases 6, 7, 7.1, 7.2)** — 15-tile audit (9/9 PASS via `audit_tiles.py`); `GET /api/config/safety-state` endpoint + `useSafetyState` 5s poll; StatusBar MODE/KILL-SWITCH/ML pills + PAPER/LIVE viewport outline; `TileState.jsx` empty/error state machine (12 unit tests); `VITE_WS_URL` config-driven URLs; Tournament dashboard view (`TournamentDashboard.jsx` + 6 components, `GET /api/tournament/snapshots[/{id}]`); Playwright dashboard smoke (`test_dashboard_smoke.py`, green locally 1 passed in 135s); api-gateway catch-all reverse-proxy to frontend nginx; Phase3Dashboard 503 retry short-circuit.

### Requirements Coverage

- **Satisfied:** 19/23 — INFRA-03..06, TOURN-01..07, MLCL-03, MLCL-04, DASH-01..06
- **Partial (operator-blocked):** 3/23 — INFRA-01 (live-stack run pending OP-04 GH billing), MLCL-01 (≥7-day evidence loops = operator action), MLCL-02 (INSUFFICIENT_DATA pending OP-02 migration + OP-03 password)
- **Unsatisfied:** 1/23 — INFRA-02 (Plan 01-03 Task 4 fresh-clone checkpoint never executed)

### Known Gaps at Close

| Category | Item | Owner | Blocks |
|---|---|---|---|
| Operator action | OP-01 — LIVE-flip manual smoke | operator | DASH-03 LIVE visual; Phase 06 VERIFICATION transition |
| Operator action | OP-02 — apply migration 005 (`tournament_reader` role) | operator | MLCL-02 verdict |
| Operator action | OP-03 — set `TOURNAMENT_READER_PASSWORD` + force-recreate harness | operator | MLCL-02 verdict |
| Operator action | OP-04 — resolve GitHub Actions billing | operator | INFRA-01 ML-on nightly; tournament-harness CI; DASH-06 CI |
| Operator action | INFRA-02 checkpoint — fresh tmp clone bootstrap × 2 | operator | INFRA-02 SC-1 + SC-3 behavioural |
| UAT | P02 HUMAN-UAT 5 pending operator scenarios | operator | Phase 02 sign-off |

OP-05 (push to origin) closed 2026-05-15T02:20Z. Known deferred items: 8 (see STATE.md Deferred Items).

### Key Decisions (Outcome ✓ Good unless marked)

- ✓ Win criterion = DSR + bootstrap p<0.05 on OOS Sharpe / corrected Dir.Acc, not >5% R²
- ✓ Tournament uses Docker+Python orchestrator, not LLM subagents (per-experiment isolation)
- ✓ Bootstrap-tests run against fresh tmp clone, never against working tree
- ✓ Tournament wins open draft PRs only; humans merge
- ✓ Backtest divergence documented permanently (ADR-012) over rewrite to CoreAggregator
- ✓ Tier-2 monitoring deleted (ADR-011) — no autonomous `claude -p` in CI
- ⚠ Revisit: 2% per-trade risk cap relaxed to 10% in paper mode (ADR-010, 2026-05-06) to clear Bybit min-notional on $100 balance — pre-LIVE checklist must restore ≤2% before flipping TRADING_MODE=LIVE
- — Pending: ML re-enablement (ENABLE_ML_PREDICTIONS=true) blocked behind DSR > 0.95 evidence on returns (V0 finding)

### Audit & Verification Artifacts

- Audit: `.planning/milestones/v1.0-MILESTONE-AUDIT.md`
- Archived ROADMAP: `.planning/milestones/v1.0-ROADMAP.md`
- Archived REQUIREMENTS: `.planning/milestones/v1.0-REQUIREMENTS.md`
- All 9 phases: VERIFICATION.md present (4 verified, 5 human_needed); VALIDATION.md present (9/9 nyquist-compliant); SECURITY.md present (9/9 verified, 0 open threats)

---
