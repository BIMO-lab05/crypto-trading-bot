# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — Bootstrap, Tournament Harness, Dashboard Safety

**Shipped:** 2026-05-15
**Phases:** 9 (1, 2, 3, 4, 5, 6, 7, 7.1, 7.2) | **Plans:** 50 | **Tasks:** 67 | **Commits:** 427 | **Timeline:** 9 days (2026-05-06 → 2026-05-15) | **LOC:** +159,471 / -2,816 across 764 files

### What Was Built

- **Reproducible fresh-clone bootstrap:** 10 JSONL exchange-data fixtures + `TapeReplayClient` + `bootstrap.sh` with WSL2 BuildKit guard + 6-symptom Diagnose/Action/Verification RUNBOOK.
- **Integration test harness:** `pytest tests/integration` from fresh tmp clone (round-trip <60s assertion); `scripts/iter-fix.sh` + anti-mock diff guard (10-case test suite); `.github/workflows/integration.yml` + nightly ML-on variant.
- **Tournament harness:** Docker-isolated SQLite leaderboard orchestrator (`mem_limit` + `read_only=True` + `cap_drop=ALL`); 4-architecture registry (GRU/LSTM/Transformer/TCN); composite-PK schema with `r2_returns`/`dir_acc_corrected`/`oos_sharpe`/`psr`/`dsr`/`cpcv_dsr`; failure-row persistence; TOURN-07 canonical-metrics-imports-only CI grep gate.
- **Significance + auto-PR pipeline:** Top-3-by-DSR ensemble + Politis–Romano stationary block bootstrap (p<0.05 on OOS Sharpe + corrected Dir.Acc); `gh pr create --draft` only path; `tournament reproduce` CLI with FP-tolerance idempotency check; no-auto-merge grep gate.
- **ML post-V0 cleanup:** Forward-paper-test apparatus + per-feature `PSR_CI_PUBLISHED` default-on gate (37 tests); T0.1.x `different_horizon` sweep YAML (12 cells); tier-2 monitoring (`claude -p` PR-opening) deleted (ADR-011); backtest divergence documented permanently (ADR-012).
- **Dashboard safety + smoke:** 15-tile audit (9/9 PASS via `audit_tiles.py`); `GET /api/config/safety-state` endpoint; `useSafetyState` 5s poll; StatusBar MODE/KILL/ML pills + PAPER/LIVE viewport outline; `TileState.jsx` empty/error state machine (12 unit tests); config-driven `VITE_WS_URL`; Tournament view with significance badge + filter chips; Playwright dashboard smoke green locally (135s).

### What Worked

- **Decomposing the milestone into 4 ROADMAP-named initiatives** (Infra, Tournament, ML cleanup, Dashboard) with strict phase dependencies kept blast-radius bounded — every phase had a clear consumer in the next.
- **Anti-mock diff guard from Phase 2 onward** prevented Goodhart drift across remaining 7 phases. Zero `pytest.skip` / `xfail` / `unittest.mock` regressions in `tests/integration/`.
- **CI grep gates as defence-in-depth** (TOURN-07 metrics; no-auto-merge; no `>5% R²`; no `claude -p`; no hardcoded URLs) — every "removed permanently" decision survives without continuous attention because regressions fail CI loudly.
- **Plan SUMMARY + VERIFICATION.md per phase** made the v1.0 audit cheap: 3-source cross-reference (REQUIREMENTS traceability + VERIFICATION + SUMMARY frontmatter) caught 0 false positives. Audit ran in ~30 min from cold.
- **Phase 7.1 + 7.2 as fast bug-close phases** instead of cramming fixes back into Phase 7 — clean per-bug commit history; verification cycles stayed short.
- **gsd-integration-checker subagent** for cross-phase wiring confirmed FLOW-A..E once and re-confirmed on delta refresh with `NO_DELTA` verdict — saves the orchestrator from doing it manually each audit cycle.

### What Was Inefficient

- **SUMMARY.md `one-liner` discipline drifted.** Many plan SUMMARYs left "One-liner:" placeholder or pasted Rule 3 lines as the one-liner — `gsd-sdk query summary-extract` produced garbage when used for the MILESTONES.md auto-accomplishment list. Had to hand-curate the 6-theme list. Plan template should enforce real one-liner.
- **`02-08-PLAN.md` key_link patterns didn't match reality** (`model_loader.get_current_model` never existed; `confidence == 0` was `> 0`). Operator-approved retarget mid-phase. Plan-time validation against the codebase would catch this before commit.
- **`metrics_bridge.py` eager imports silently swallowed `ImportError`** in tournament-harness for ~3 phases before INT-02 caught it. Cost: silent canonical-metrics break in Phase 04 container-only tests; required a follow-up patch (`960986c` + 3 unit tests + lifespan assertion + runner-boot assertion). Lesson: explicit `assert_canonical_metrics_available()` at every boot path beats letting `try/except ImportError: pass` hide it.
- **Phase 3 namespace-merge breakage** (deleted `__init__.py` files to enable PEP 420; broke ml-retraining `__version__`) only surfaced in Phase 4 container-integration tests. Needed `04-08-PLAN.md` to restore via `_version.py` shim. Lesson: namespace-pkg merges should ship their own canary test in the same plan, not the next one.
- **OP-04 GH Actions billing block** prevented INFRA-01 nightly variant + tournament-harness first CI run + DASH-06 CI from ever showing green CI signal during the milestone. Operator-only resolution unknown at plan time. v1.0 audit relies on local smoke + grep gates as compensation.
- **`docker-compose.unified.yml` vs `docker-compose.yml` duality** (latter incomplete — missing DBs) confused at least 2 plan executions before being fully documented in CLAUDE.md. Stack should consolidate on `unified` only.

### Patterns Established

- **Operator-checkpoint gates as the explicit termination point** for plans whose final step can't run on CI (fresh-clone E2E, LIVE-flip visual, ≥7-day evidence accrual). Plan declares `Status: AWAITING CHECKPOINT`; VERIFICATION.md sets `status: human_needed`; audit catches the gap loudly.
- **3-source REQ cross-reference at milestone-close** (VERIFICATION.md status + SUMMARY frontmatter `requirements-completed` + REQUIREMENTS.md traceability `[x]`). Catches "phase claimed REQ but never listed it" + "REQ listed but verification still human_needed" + "REQ checked off but verification missing" — all three failure modes in one pass.
- **ADR-numbered decision artifacts** (ADR-010, ADR-011, ADR-012, ADR-016) — one per binding decision with a permanent home in `docs/decisions/` (or `wiki/decisions/` for ops-side decisions). v1.0 had a wiki-vs-docs namespace collision (INT-01) — namespace policy now in `wiki/decisions/_index.md`.
- **Defense-in-depth boot-path assertions** — single boot-path check (`metrics_bridge` import) is fragile; assert at FastAPI lifespan + CLI `main()` + caller-site grep gate. Survives one path regressing.
- **Audit-driven Playwright smoke** — test reads `06-TILE-AUDIT.json` at runtime, hard-asserts every non-REMOVED row has `data_testid`, walks all rows. No drift between audit and smoke; one source of truth.

### Key Lessons

1. **CI grep gates beat documentation-only "permanently removed" claims.** ADR alone is not enforcement. Pair every "we don't do X anymore" with a grep gate in CI; the ADR explains the *why* and the grep catches the regression.
2. **Operator-checkpoint gates must be visible in audit, not just in plan SUMMARY.** Mark VERIFICATION.md `status: human_needed` so milestone audit surfaces it, not hidden inside `awaiting-checkpoint` plan status.
3. **Eager imports of canonical libraries should fail loud at boot, not silent at first use.** Every cross-service "imports canonical metrics from X" needs an explicit `assert_imports_resolve()` at lifespan/CLI entry. Silent ImportError swallowing is a silent edge-claim source.
4. **Namespace-pkg merges need their own canary test in the same plan.** Don't ship a `__init__.py` deletion to enable PEP 420 without a test that fails if the merge broke a transitive import. Otherwise the regression lands and the next phase eats the debugging cost.
5. **Decimal phases (7.1, 7.2) are a healthy pattern for closing bugs found in verification.** Don't cram them back into the parent phase; let the verification report drive the next decimal phase. Keeps commit history clean and verification cycles short.
6. **Plan one-liner discipline matters at milestone close.** SDK auto-extract needs structured input; placeholder text becomes the official accomplishment list. Plan template should reject empty or placeholder one-liners.

### Cost Observations

- **Model mix:** ~100% opus (with sonnet subagents for integration-checker, etc.); no haiku usage logged.
- **Sessions:** Multi-day milestone; exact session count not tracked.
- **Notable efficiency:** Phase 7.1 + 7.2 (1 plan each, ~1 day each) significantly outperformed earlier 9-10-plan phases on signal-to-noise — bug-close phases have natural goal-backward shape (close N bugs) and reduce planning overhead.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Plans | Key Change |
|-----------|----------|--------|-------|------------|
| v1.0 | multi-day | 9 | 50 | First milestone under GSD workflow with full audit + integration-checker; established 3-source REQ cross-reference; introduced decimal phases for verification-driven bugfixes; CI grep gates as defence-in-depth pattern |

### Cumulative Quality

| Milestone | Tests Added | Coverage | Zero-Dep Additions | Open Threats |
|-----------|-------------|----------|---------------------|--------------|
| v1.0 | ~580+ (151 in P4 alone; 35 tape fixtures; 12 TileState; 11 safety-state; 5 horizon-sweep; 4 ADR-011 grep gate; 5 ADR-012 invariant; ...) | not measured | low | 0 (98 retroactive threats registered + all closed in `5a6323c`) |

### Recurring Friction

- WSL2 + Docker Desktop BuildKit hangs — documented in RUNBOOK + `make build-no-buildkit`; persists across milestones.
- GitHub Actions billing — blocked first CI runs for INFRA-01 nightly + tournament-harness + DASH-06. Carries into v1.1.
- ML edge claims gated behind DSR > 0.95 on returns — V0 finding still load-bearing; tournament-harness is the v1.0 contribution to closing this loop.

---
*Last updated: 2026-05-15 after v1.0 milestone close*
