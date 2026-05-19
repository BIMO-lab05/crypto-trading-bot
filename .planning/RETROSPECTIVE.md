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

## Milestone: v1.1 — Path to LIVE

**Shipped:** 2026-05-18
**Phases:** 5 (8, 9, 10, 11.1, 12 — Phase 11 superseded by 11.1) | **Plans:** 19 | **Tasks:** 32 | **Commits:** 138 | **Timeline:** ~4 days post v1.0 tag (2026-05-15 → 2026-05-18) | **LOC:** +14,522 / -574 across 92 code files (services/scripts/tests/.github/frontend); total branch diff +31,072 / -47,475 across 339 files reflects concurrent _archive_lstm/* removals from same branch

### What Was Built

- **Pre-LIVE preflight (Phase 8):** 6-check `app/preflight/` core module + `scripts/preflight_live.py` CLI + `GET /api/preflight/live-readiness` HTTP route (gateway-proxied); trading-engine lifespan refuses LIVE boot when `MAX_POSITION_RISK_PCT > 0.02` (`LIVE_PREFLIGHT_REJECTED reason=cap_too_high`); `.github/workflows/preflight-live-readiness.yml` PR-label gate; `RUNBOOK.md` Pre-LIVE Operator Checklist (6 Diagnose/Action/Verification subsections); two CI grep gates + boundary-agreement test pin the enforcement against silent removal.
- **ML re-enablement gate (Phase 9):** `run_evidence_loop.py` idempotent ≥7-day driver + migration `0002_mlgate_evidence_columns.sql` adding `run_date` + `psr_ci_published` to `leaderboard`; trading-engine startup `auto_flip_ml_predictions()` reads DSR>0.95 evidence within 14 days and writes `/run/mlgate_auto_flip.json` schema_version=1 marker + `MLGATE_AUTO_FLIP direction=X reason=Y` log; 5-member `MLGateReason` enum + unauth read-only `/api/preflight/ml-gate-reason-counts`; notification-service Telegram digest via in-process `alert_manager.send_daily_summary` call (NOT admin-guarded HTTP — regression test pins the contract).
- **Path-to-LIVE dashboard (Phase 10):** api-gateway `GET /api/preflight/carry-ins` backed by atomic file-state machine at `.planning/state/carry_ins.json` (RW parent-dir bind-mount per WSL gotcha); two react-query hooks verbatim from `useSafetyState` idiom; `PathToLiveTile.jsx` (banner + 6 PREFLIGHT chip rows + 5 carry-in rows + 24h continuous-PASS footer); pytest-playwright Chromium smoke covering all 7 D-10-18 assertions; `dashboard-smoke.yml` CI with PR paths filter.
- **Carry-in closure harnesses (Phase 11.1):** Draft 2020-12 JSON Schema (`.planning/evidence/_schema.json`) + `scripts.closure._common.write_evidence()` helper (auto-injects `schema_version=1` + ISO-8601 UTC timestamp, schema-validated before disk write); five operator-runnable harnesses (`liveclose-01-fresh-clone.sh`, `liveclose-02-record-ci.sh`, `liveclose_03_psr_evidence.py`, `liveclose_04_sweep_verdict.py`, `liveclose-05-live-flip-smoke.sh`); `scripts/closure/run-all.sh` read-mostly orchestrator with whitelisted `--exec` LIVECLOSE-01..04 and explicit refusal of LIVECLOSE-05 auto-invocation; `LIVECLOSE-INDEX.md` fully wired (zero `<filled-by-plan-7>` tripwires at close); 14 integration tests bolt the wiring contract into CI.
- **CI billing-failure detector (Phase 12):** `.github/workflows/billing-failure-detector.yml` cron-driven (every 6h) with self-trigger-safe naming (jq filter excludes own workflow name); direct curl to api.telegram.org (in-cluster notification-service unreachable from GitHub-hosted runners) + `gh issue create` with `ops: billing` label; 12-test grep-gate net pins the contract; evidence-dir scaffolds for the two operator-blocked carry-ins.

### What Worked

- **Phase 11 → 11.1 split** at planning time, splitting harness code-delivery from operator wall-clock execution, kept the milestone closeable on a code-scope criterion rather than waiting on operator availability. Best single planning decision of v1.1.
- **3-state requirements taxonomy reconciliation at close** (complete / harness-delivered / operator-blocked) collapsed a four-source-of-truth conflict between REQUIREMENTS `[x]`, PROJECT.md Validated, audit Satisfied, and reality post-execution. Each archive file is now internally consistent.
- **Defense-in-depth pre-LIVE enforcement** (CLI + HTTP + boot-path + CI gate, each with its own grep test) survived the natural test of being merged across 5 plans — no path silently regressed. Boundary-agreement test at `0.0200 / 0.0201` caught the duplication drift we explicitly accepted.
- **Closed-for-extension evidence schema (Phase 11.1-01)** with auto-injected `schema_version=1` + `timestamp` (caller cannot override) eliminated drift across 5 independent harness implementers. Tripwire tokens (`<filled-by-plan-7>`) made Wave-3 wiring detection automatic.
- **Self-trigger-safe billing detector** — naming the workflow such that its own `gh run list --status failure --limit 5` query never matches itself, plus a jq `select(.name != own_name)` defense-in-depth, kept the cron monitor from page-storming on its own future failures.
- **Two-key authorization on LIVECLOSE-05** + explicit orchestrator refusal of `--exec liveclose-05` prevented the agent (or anyone) from auto-invoking the LIVE-flip step. Forced design constraint: LIVE-flip is supervised-only by construction.

### What Was Inefficient

- **Audit timing mismatch.** v1.1 audit refresh ran at 02:55Z on 2026-05-18 before Phase 11.1 + 12 wave-3 verification completed at 16:30Z same day. Audit numbers (11/19 satisfied, 8 orphaned) were stale at milestone close. Reconciled manually pre-archive but a second audit pass post-Phase-12 would have produced cleaner numbers in the audit file itself. Lesson: audit refresh should be the last step of the last phase, not the first step of milestone close.
- **REQUIREMENTS.md checkbox drift across the milestone.** PREFLIGHT-01/03/04 stayed `[ ]` in REQUIREMENTS.md long after VERIFICATION marked them SATISFIED. MLGATE-01/02/03 same. Operator only flipped 12 boxes (LIVECLOSE-01..05 + PREFLIGHT-02/03 + DASHLIVE-01..04 + CIRESTORE-03) before close. Plan SUMMARY → REQUIREMENTS auto-sync would have caught this earlier than the close-time reconciliation.
- **Phase 11 umbrella appeared as `Not started`** in ROADMAP.md right up to milestone close, even though Phase 11.1 (which absorbed its scope) was complete. ROADMAP only surfaced the `superseded` line when reconciling pre-archive. Insertion of a decimal phase (11.1) should automatically mark the parent (11) superseded if all REQs are covered.
- **One-liner discipline drifted further than v1.0** — `gsd-sdk query summary-extract` returned "1. [Rule 3 - Blocking] ..." (which is the first line of the CR-Resolution section, not a one-liner) for at least 5 of 19 plans. The auto-generated MILESTONES.md entry was unusable; had to hand-curate the same way as v1.0. Plan template still needs `one-liner: required and not /^Rule|^Task/` validation.
- **Phase 08 VERIFICATION.md `human_needed` persists.** Two manual-only smokes (container-restart cap rejection + live-curl through api-gateway image rebuild) were deferred to post-merge operator action. They are documented in 08-VALIDATION.md as Manual-Only #1/#2 but they leave the verification status sticky-yellow forever. Pattern works but creates a permanent visible-amber tile in any per-phase audit dashboard.
- **`docker-compose.live.override.yml` shipped untracked at repo root** as pre-scaffold for LIVECLOSE-05 from a prior session, surfaced by integration checker as INFO. Not actually a problem (intentional scaffolding), but flagged as a noise item three times across audit refreshes. Either commit early or document as expected-untracked in audit ignore.

### Patterns Established

- **Umbrella→decimal phase split** for separating code-deliverable from wall-clock operator execution. Phase 11 stays as the requirement-mapping anchor; Phase 11.1 ships the code. Audit and milestone-close treat them as one logical phase but distinct execution units.
- **3-state requirements taxonomy** (complete / harness-delivered / operator-blocked) — distinguishes "code done, evidence pending operator" from "code done, evidence done" from "blocked on something we don't own." Each state has different milestone-close semantics. Now the default model going forward.
- **Closed-for-extension contract files in Wave 1** (`_schema.json` + `_common.py` write helper for Phase 11.1; `lifespan/ml.py` + `_MLGATE_MARKER_PATH` for Phase 9) — Wave-2 plans MUST consume read-only. Prevents downstream plans from forking the contract. Tripwire tokens (`<filled-by-plan-7>`) make detection of forgotten wires automatic.
- **Boundary-agreement tests for intentionally-duplicate constants** — when keeping two copies of the same threshold for code-locality reasons (Phase 8: cap check inline at main.py + `check_cap()` in shared module), parametrise a test at the boundary value + boundary+1 to detect drift between the two sites.
- **Self-trigger-safe cron monitors** — workflow that watches CI must not match itself in its own filter. Naming-based prevention + jq `select()` defense-in-depth. Apply to any future monitor workflow.
- **In-process scheduler → service call (not admin-guarded HTTP)** for intra-cluster digests. notification-service → trading-engine `alert_manager.send_daily_summary` direct Python call. Regression test pins the contract by failing if the scheduler ever switches to HTTP. Avoids the admin-auth burden on internal automation.
- **Supervised-run-only harness with orchestrator refusal** for LIVE-flipping operations. Two-key authorization on the harness itself (`--i-understand-this-flips-live` flag + `LIVE_TRADING_ACK` env var) and explicit orchestrator refusal of `--exec` for that harness. Use for any operation where the agent should be physically incapable of unattended invocation.

### Key Lessons

1. **Run the milestone audit refresh after the last phase verification, not before milestone close.** Stale audit numbers force manual reconciliation; fresh audit numbers archive cleanly. The 13-hour gap on 2026-05-18 was avoidable.
2. **Distinguish "code shipped" from "evidence accrued" at requirements level.** A REQ with a wall-clock-bound success criterion (≥7 days) cannot complete in a single milestone unless the milestone is ≥7 days long. The right answer is a 3-state taxonomy with explicit harness-delivered status, not pretending the REQ is `active` for weeks after the code shipped.
3. **Auto-generated milestone summaries from plan one-liners only work if plan one-liners are disciplined.** `gsd-sdk query summary-extract` is only as good as its input. Plan template should reject ambiguous one-liner content (Rule lines, Task headers, empty fields) at planning time, not extract garbage at close time.
4. **Supersession of an umbrella phase by an inserted decimal phase should be machine-detected.** If Phase 11.1 covers all REQs originally assigned to Phase 11, ROADMAP.md should auto-mark Phase 11 as `superseded` rather than leaving it as `Not started` indefinitely. `gsd-sdk query roadmap.analyze` could compute this.
5. **Pre-merge defense-in-depth saves post-merge debugging.** Phase 8's three-layer preflight enforcement (CLI + HTTP + boot + CI gate, with grep tests pinning each) caught two real regressions during Phase 9/10 integration that would otherwise have slipped through. Single-layer enforcement is fragile in any milestone where multiple plans touch the same enforcement path.
6. **Forced-design constraints are sometimes the right answer.** GH Actions runners cannot reach in-cluster notification-service; rather than route through a public-facing proxy, accept direct curl to api.telegram.org as the right pattern. Document explicitly so future plans don't re-debate.

### Cost Observations

- **Model mix:** ~100% opus (with sonnet subagents for integration-checker, gsd-verifier, gsd-validator); no haiku usage logged.
- **Sessions:** Multi-day milestone; exact session count not tracked. v1.1 felt tighter per-session than v1.0 — phases were smaller (1-7 plans vs 4-10), planning artifacts more uniform, and the 3-state taxonomy made progress legible at a glance.
- **Notable efficiency:** Phase 11.1 (7 plans, 1 day) and Phase 12 (1 plan, ~52 min) — both used the same closed-for-extension-in-Wave-1 + parallel-Wave-2 + wiring-in-Wave-3 pattern; high throughput. Phase 8 (5 plans, ~1.5 days) was the longest because of the 3-layer defense-in-depth requirement, but each plan stayed under ~30 min execution.
- **Notable inefficiency:** ~3-4 audit refresh cycles on the same day as Phase 11.1 + 12 wave-3 completion (02:55Z then again at close). One pass after-verification would have been cleaner.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Plans | Key Change |
|-----------|----------|--------|-------|------------|
| v1.0 | multi-day | 9 | 50 | First milestone under GSD workflow with full audit + integration-checker; established 3-source REQ cross-reference; introduced decimal phases for verification-driven bugfixes; CI grep gates as defence-in-depth pattern |
| v1.1 | multi-day, ~4 calendar days | 5 (8, 9, 10, 11.1, 12) | 19 | Umbrella→decimal phase split (11→11.1) to separate code-deliverable from wall-clock operator execution; 3-state requirements taxonomy (complete/harness-delivered/operator-blocked) at close; closed-for-extension contract files in Wave 1 with tripwire-token detection; defense-in-depth pre-LIVE enforcement at 3 layers + CI gate; supervised-run-only harnesses with orchestrator refusal for LIVE-flipping |

### Cumulative Quality

| Milestone | Tests Added | Coverage | Zero-Dep Additions | Open Threats |
|-----------|-------------|----------|---------------------|--------------|
| v1.0 | ~580+ (151 in P4 alone; 35 tape fixtures; 12 TileState; 11 safety-state; 5 horizon-sweep; 4 ADR-011 grep gate; 5 ADR-012 invariant; ...) | not measured | low | 0 (98 retroactive threats registered + all closed in `5a6323c`) |
| v1.1 | ~120+ (37 preflight; 22 mlgate; ~30 dashlive incl. 7-assert Playwright smoke; 10 LIVECLOSE-02 + 9 LIVECLOSE-05 + 14 wiring; 12 billing-detector grep gates; boundary-agreement) | not measured | low (jsonschema added Phase 11.1; pytest-playwright added Phase 10) | 0 across 3 completed phases (8: 26 threats closed; 9: 22 threats closed incl. T-09-03-05 via `660a9ac`; 10: 18 threats closed) |

### Recurring Friction

- WSL2 + Docker Desktop BuildKit hangs — documented in RUNBOOK + `make build-no-buildkit`; persists across milestones (v1.0, v1.1).
- GitHub Actions billing (OP-04) — STILL blocked v1.1. Blocked first CI runs for INFRA-01 nightly + tournament-harness + DASH-06 (v1.0) and LIVECLOSE-02 + CIRESTORE-01 + CIRESTORE-02 (v1.1). v1.1 mitigation: shipped `billing-failure-detector.yml` so the regression is detectable next time. Carries into v1.2.
- ML edge claims gated behind DSR > 0.95 on returns — V0 finding still load-bearing. v1.0 shipped the tournament harness; v1.1 shipped the gate (`MLGATE-02` auto-flip + `LIVECLOSE-03` evidence-loop harness). v1.2 carries the wall-clock evidence accrual.
- One-liner discipline in plan SUMMARYs — flagged in v1.0 retro, drifted further in v1.1 (auto-extracted MILESTONES.md entry unusable both milestones). Plan template enforcement not yet shipped. Carries to v1.2 as a planning-tooling backlog item.
- Audit-refresh timing — v1.1 audit ran 13h before milestone close, requiring manual reconciliation. v1.0 had similar timing risk. Pattern: run audit after the last phase verification, not before milestone close. Carries to v1.2 as a workflow discipline item.

---
*Last updated: 2026-05-18 after v1.1 milestone close*
