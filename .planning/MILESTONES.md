# Milestones

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
