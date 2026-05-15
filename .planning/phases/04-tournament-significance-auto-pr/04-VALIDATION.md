---
phase: 04-tournament-significance-auto-pr
validated: 2026-05-15T00:45:00Z
status: nyquist-compliant
nyquist_compliant: true
wave_0_complete: true
auditor: orchestrator (milestone-audit backfill)
note: "Retroactive audit per v1.0 milestone audit; SUMMARYs already shipped"
---

# Phase 04 — Validation Strategy

> Per-phase validation contract. State B reconstruction — derived from PLAN/SUMMARY artifacts and live tree after phase completion. Mirrors the shape of `02-VALIDATION.md` and `03-VALIDATION.md`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (project-wide) + pytest-asyncio (`asyncio_mode = auto`) |
| **Config file** | `pyproject.toml` (registers `slow` marker per Plan 04-02) + repo `pytest.ini` (rootdir for harness) |
| **Conftest** | `services/tournament-harness/tests/conftest.py` (path-import shim + `synthetic_snapshot_dict` factory added by 04-01) |
| **Quick run command** | `python3 -m pytest services/tournament-harness/tests/unit/ -q` |
| **Full host suite command** | `python3 -m pytest services/tournament-harness/tests/ -q -m "not slow"` (host) |
| **In-container command** | `docker compose -f docker-compose.unified.yml --profile tournament run --rm -v "$(pwd)/services/tournament-harness/tests:/app/tests:ro" -e PYTHONPATH=/app:/opt/ml_retraining tournament-harness pytest tests/integration/test_open_pr_e2e.py tests/integration/test_reproduce_idempotent.py tests/integration/test_canonical_metrics_importable.py -v` |
| **Estimated runtime** | ~13s host unit (213 tests) / ~6s host integration (26 tests) / ~74s container e2e (13 tests) |
| **CI** | `.github/workflows/tournament-harness.yml` — 5 jobs: `tourn07-grep-gate` → `unit-tests` → `integration-fake-docker` + `container-integration` (per-PR) + `integration-real-stack` (schedule/dispatch). 0-SKIP grep guard on container job. |

---

## Sampling Rate

- **After every task commit:** unit suite for the touched service (`pytest services/tournament-harness/tests/unit/test_<area>.py -q`).
- **After every plan wave:** full host suite + grep-gate integration (`pytest services/tournament-harness/tests/ -q -m "not slow"`).
- **Before `/gsd-verify-work`:** full host green + container e2e green (`13 passed, 0 skipped`) + CI green on PR.
- **Max feedback latency:** ~13s host unit, ~6s host integration, ~74s container e2e, ~5min CI per push.

---

## Nyquist Audit Summary

| Metric | Count |
|--------|-------|
| Plans audited | 10 (04-01 through 04-10) |
| Plans shipping production code | 7 (01, 02, 03, 04, 07, 08, 10) |
| Plans shipping tests-only | 2 (05, 06) |
| Plans shipping CI/infra-only | 1 (09) |
| New unit-test files created | 13 |
| New integration-test files created | 7 |
| Total new tests added in Phase 4 | 151 (108 unit + 43 integration; counts from `grep -cE '^(async )?def test_' <file>`) |
| Tests-per-feature ratio | ~21.6 (151 tests / 7 production code plans) — ≥ 2x feature-change rate |
| Plans shipping production code without ≥1 dedicated test file | 0 |
| Cross-cutting contract boundaries (PR body / gh argv / win-gate / artifacts schema / cache contract / predict_fn contract) | 6 — each has dedicated test file |
| Verdict | **NYQUIST-COMPLIANT** — coverage exceeds 2x feature change rate; every contract boundary tested; no production code shipped without test |

---

## Per-Plan Test Coverage Table

Notation: **U** = unit / **I** = integration / **C** = contract (grep gate / static invariant) / **CI** = CI workflow.

| Plan | Files Changed (production) | Test Files Added | Test Count | Test Type | Verdict |
|------|----------------------------|------------------|------------|-----------|---------|
| **04-01** Significance/Ensemble Foundation | `significance/__init__.py`, `artifacts.py`, `ensemble.py`, `predict_cache.py` (4 modules) | `test_significance_artifacts.py`, `test_significance_ensemble.py`, `test_significance_predict_cache.py` (3 files) | 23 (6+9+8) | U | COVERED |
| **04-02** Significance Statistical Core | `significance/baseline.py`, `bootstrap.py`, `win_gate.py` (3 modules) + `pyproject.toml` slow-marker | `test_significance_baseline.py`, `test_significance_bootstrap.py`, `test_significance_win_gate.py` (3 files) | 35 (3+20+12; 1 slow-gated) | U | COVERED |
| **04-03** open-pr CLI | `pr/__init__.py`, `body.py`, `gh.py`, `open_pr.py` + `cli.py`, `metrics_bridge.py` (`dir_acc_corrected_from_log_returns`), `leaderboard/db.py` (`count_tournaments`) | `test_pr_body.py`, `test_pr_gh.py`, `test_leaderboard_db_count.py`, `test_metrics_bridge_log_returns.py` (4 files) | 30 (10+12+3+5) | U | COVERED |
| **04-04** Reproducibility Verifier | `pr/reproduce.py` + `cli.py` subparser | `test_pr_reproduce.py` (U) + `test_reproduce_idempotent.py` (I, container-only) | 20 (17+3) | U + I | COVERED |
| **04-05** CI Grep Gates | (tests-only — no production code) | `test_no_legacy_r2_criterion.py`, `test_no_auto_merge.py`, `test_klines_filter_required.py`, `test_no_parallel_metric_reimplementations.py` (4 files) | 18 (5+4+5+4) | C | COVERED |
| **04-06** open-pr e2e smoke | (tests-only — no production code) | `test_open_pr_e2e.py` (1 file, container-only) | 7 | I | COVERED |
| **04-07** build_predict_fn factory | `runner/predict_fn.py` | `test_runner_predict_fn.py` | 10 | U | COVERED |
| **04-08** PEP 420 namespace fix | Deleted `app/__init__.py` × 2; added `_version.py`; touched `main.py` (4 call sites) | `test_canonical_metrics_importable.py` (3 tests; container-only with host self-skip) | 3 | I + C | COVERED |
| **04-09** CI wiring | `.github/workflows/tournament-harness.yml` (+59/-2) | (uses existing 04-05/04-06/04-08/04-10 tests as gates) | 0 (wires existing) | CI | COVERED |
| **04-10** Zero-safe baseline sharpe | `pr/open_pr.py` (`_zero_safe_baseline_sharpe` helper) | `test_significance_zero_variance_baseline.py` | 5 | U | COVERED |

**Totals:** 13 new unit-test files (108 tests) + 7 new integration-test files (43 tests) = **151 tests added in Phase 4**.

---

## Per-Requirement Verification Map

| Req | Plan(s) | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | Status |
|---|---|---|---|---|---|---|---|---|
| TOURN-05 | 04-01, 04-02 | 1-2 | Top-3-by-DSR ensemble + bootstrap p<0.05 vs persistence on OOS Sharpe + dir_acc_corrected; drops `>5% R²` | T-04-06 (p=0 unreachable), T-04-13 (R² literal absent) | additive-smoothed (1+count)/(n+1); Politis-Romano stationary block; D-13 grep gate on R² | unit + contract | `pytest services/tournament-harness/tests/unit/test_significance_*.py` + `pytest tests/integration/test_no_legacy_r2_criterion.py` | ✅ green (58 unit + 5 grep-gate) |
| TOURN-06 | 04-03, 04-04, 04-05, 04-06 | 3-5 | Auto-open draft PR via `gh` CLI with leaderboard + ensemble + significance + reproducer; humans merge — no `gh pr merge` | T-04-14 (GH_TOKEN never in argv), T-04-16 (no auto-merge), T-04-25 (temp DB isolation) | argv-list subprocess `shell=False`; env-only token; CD-10 grep gate; reproduce uses `output_suffix="dry-run"` | unit + integration + contract | `pytest tests/unit/test_pr_*.py test_metrics_bridge_log_returns.py test_leaderboard_db_count.py` + `pytest tests/integration/test_no_auto_merge.py test_open_pr_e2e.py test_reproduce_idempotent.py` | ✅ green (host unit 30; container e2e 10/10; grep-gate 4/4) |
| D-01 (per-symbol top-3 by `(dsr, cpcv_dsr, oos_sharpe, created_at)` tie-break) | 04-01 | 1 | TOURN-05 | — | deterministic sort + status filter | unit | `pytest tests/unit/test_significance_ensemble.py` | ✅ green (9/9) |
| D-02 (mean-of-log-returns aggregation, NOT price-space) | 04-01, 04-03 | 1, 3 | TOURN-05 | T-04-31 (no parallel impls) | `np.stack(...).mean(axis=0)`; B5 grep gates pin call site | unit + contract | `pytest tests/integration/test_no_parallel_metric_reimplementations.py` + open_pr.py B5 import grep | ✅ green |
| D-03 (config-by-reference ensemble JSON; no weights/scalers) | 04-01 | 1 | TOURN-05 | T-04-04 (no model bytes leaked) | atomic write; schema enforced; `member_descriptor` strips to `{run_id, architecture, hp_hash, dsr}` | unit | `pytest tests/unit/test_significance_artifacts.py` | ✅ green (6/6) |
| D-04 (persistence baseline = `np.zeros(N)`) | 04-02, 04-10 | 2, 6 | TOURN-05 | T-04-10-01 (PSR(zeros) = nan guarded) | function-not-constant for swap-point; `_zero_safe_baseline_sharpe` 1e-12 floor | unit | `pytest tests/unit/test_significance_baseline.py test_significance_zero_variance_baseline.py` | ✅ green (8/8) |
| D-06 (one-tailed H0 via centering) | 04-02 | 2 | TOURN-05 | — | `d - d.mean()`; algebraically equivalent to "count≤0" for location-equivariant metrics | unit | `pytest tests/unit/test_significance_bootstrap.py` | ✅ green (20 tests; 1 slow at n=10000) |
| D-08 (4-condition win gate + CD-08 insufficient_runs) | 04-02 | 2 | TOURN-05 | — | `P_THRESHOLD=0.05`, `MIN_MEMBERS=3` module-level constants; aggregate failure reasons | unit | `pytest tests/unit/test_significance_win_gate.py` | ✅ green (12/12) |
| D-09 (tournaments_evaluated_count Bonferroni disclosure) | 04-03 | 3 | TOURN-06 | — | `count_tournaments()` invoked at run-time inside `run_open_pr`, never module-load | unit + integration | `pytest tests/unit/test_leaderboard_db_count.py` + `test_open_pr_count_tournaments_reflects_state_at_call_time` | ✅ green (3 host + 1 container) |
| D-11 (dirty-tree refusal; GH_TOKEN required) | 04-03 | 3 | TOURN-06 | T-04-11, T-04-14 | `SystemExit(3)` for dirty-tree; `SystemExit(2)` for missing token; CD-09 install check | unit | `pytest tests/unit/test_pr_gh.py` | ✅ green (12/12) |
| D-12 (reproduce idempotency: `Δsharpe ≤ 1e-6`, `Δp ≤ 0.005`) | 04-04 | 4 | TOURN-05/06 | T-04-20 (path traversal), T-04-25 (temp DB isolation) | `_diff_significance` boundary-inclusive; temp DB at `reproduce_{tid}.db`; dirty-tree refusal (no `--allow-dirty`) | unit + integration | `pytest tests/unit/test_pr_reproduce.py` + `test_reproduce_idempotent.py` (container) | ✅ green (17 host unit + 3 container) |
| D-13 (no `>5% R²` win criterion) | 04-05 | 4 | TOURN-05 | T-04-13 | regex + literal scan over `app/` + `.github/workflows/tournament*.yml` | contract (grep gate) | `pytest tests/integration/test_no_legacy_r2_criterion.py` | ✅ green (5/5; CI-enforced via 04-09) |
| CD-10 (no `gh pr merge` anywhere) | 04-03, 04-05, 04-06 | 3-5 | TOURN-06 | T-04-16 | argv shape; grep gate; belt-and-suspenders argv assertion in e2e | contract + unit + integration | `pytest tests/integration/test_no_auto_merge.py` + `tests/unit/test_pr_gh.py::test_no_gh_pr_merge_in_module` + e2e `test_open_pr_gh_argv_shape_under_real_path` | ✅ green |
| CD-11 (predict cache `.npz` atomic write) | 04-01, 04-07 | 1, 3 | TOURN-05 | T-04-01 / T-04-36 (path traversal) | `^[A-Za-z0-9._-]+$` regex on tid + run_id; `mkstemp + .tmp.npz suffix + os.replace` | unit | `pytest tests/unit/test_significance_predict_cache.py test_runner_predict_fn.py` | ✅ green (8 + 10) |
| B1 (every klines read carries `is_mainnet` filter) | 04-05, 04-07 | 4 | TOURN-05 | T-04-37 (testnet contamination) | canonical loader-only; `is_mainnet=TRUE` enforced in SQL | contract | `pytest tests/integration/test_klines_filter_required.py` | ✅ green (5/5) |
| B2 (no parallel metric reimplementations in pr/+significance/) | 04-05 | 4 | TOURN-07 (Phase 3) | T-04-31 | strengthens `_?(sharpe\|dir_acc\|deflated\|...)` def-pattern + lambda-Sharpe form | contract | `pytest tests/integration/test_no_parallel_metric_reimplementations.py` | ✅ green (4/4) |
| B3 (real `build_predict_fn` wired into `open_pr.py`) | 04-07 | 3 | TOURN-05 | — | factory at `app.runner.predict_fn`; no `NotImplementedError` in `open_pr.py` | unit + integration | `pytest tests/unit/test_runner_predict_fn.py` + `test_open_pr_imports_real_predict_fn_factory` | ✅ green (10 + 1 container) |
| W1 (win gate runs over every symbol, including <3 members) | 04-03, 04-06 | 3, 5 | TOURN-05 | — | gate populates `["insufficient_runs"]` itself | unit + integration | `pytest tests/unit/test_significance_win_gate.py` + `test_open_pr_smoke_round_trip_winner` (container) | ✅ green |
| W2 (`output_suffix` reproduce; never overwrites operator originals) | 04-03, 04-04 | 3, 4 | TOURN-05/06 | — | `output_suffix="dry-run"`; mtime-preservation test | unit + integration | `pytest tests/unit/test_pr_reproduce.py` (4 W2 tests) + container reproduce idempotent | ✅ green |
| 04-08 PEP 420 namespace merge invariant | 04-08 | 6 | TOURN-05/06 | T-04-08-01/02 (silent regression) | both top-level `app/__init__.py` deleted; `_CANONICAL_METRICS_AVAILABLE=True` in container | integration + contract | `pytest tests/integration/test_canonical_metrics_importable.py` (container-only; host self-skip) | ✅ green (3/3 in container; CI-enforced 0-SKIP guard) |
| 04-10 Zero-safe baseline (PSR(zeros)→0.0) | 04-10 | 6 | TOURN-05 | T-04-10-01 (semantic shortcut), T-04-10-03 (bootstrap kernel byte-identical) | 1e-12 variance floor; canonical PSR untouched (`git diff` empty) | unit | `pytest tests/unit/test_significance_zero_variance_baseline.py` | ✅ green (5/5) |
| 04-09 CI wiring (per-PR enforcement of D-13 / CD-10 / B1 / B2 / SC-1 / SC-3) | 04-09 | 6 | TOURN-05/06 | T-04-09-01 (silent SKIP-pass) | dir-glob `pytest tests/integration/ --ignore=...`; new `container-integration` job with 0-SKIP grep guard | CI | `.github/workflows/tournament-harness.yml` 5 jobs verified locally (host 26/26 + container 13/13) | ✅ wired (CI run blocked by GH Actions billing — operator action) |

---

## Wave-0 Fitness Assessment

**Question:** Does test coverage catch regressions at ≥ 2x the rate of feature change?

**Inputs:**
- Production code touched: 7 plans (04-01, 02, 03, 04, 07, 08, 10) shipping ~12 modules + 1 workflow + 4 call-site edits.
- Tests added: 151 across 20 new files (13 unit + 7 integration), exercising every public surface of every module shipped.
- Tests-per-feature ratio: 151 / 7 = **~21.6** (well over the 2x floor).

**Coverage by contract boundary:**

| Boundary | Test class | File(s) | Status |
|----------|------------|---------|--------|
| Atomic artifact write (3 writers) | unit + e2e atomic-leftover scan | `test_significance_artifacts.py` + `test_open_pr_writes_no_partial_artifacts` | ✅ |
| Ensemble selection (D-01 tie-break) | unit | `test_significance_ensemble.py` (9 tests incl. D-01 tie-break, status filter, CD-08 short list, D-02 aggregation) | ✅ |
| Bootstrap p-value (Politis-Romano) | unit (incl. n=10000 slow gate) | `test_significance_bootstrap.py` (20 tests) | ✅ |
| Win-gate classifier (4-condition + insufficient_runs) | unit + e2e | `test_significance_win_gate.py` + e2e winner/no-win paths | ✅ |
| Predict cache contract (.npz atomic + path-traversal guard) | unit | `test_significance_predict_cache.py` + `test_runner_predict_fn.py` | ✅ |
| `gh` CLI argv shape (no auto-merge, no token leak) | unit + integration + contract | `test_pr_gh.py` + `test_open_pr_gh_argv_shape_under_real_path` + `test_no_auto_merge.py` (triple-layer enforcement) | ✅ |
| PR body length-cap fallback (CD-12) | unit | `test_pr_body.py` (10 tests) | ✅ |
| Reproduce idempotency (D-12) | unit + integration | `test_pr_reproduce.py` (17 host) + `test_reproduce_idempotent.py` (3 container) | ✅ |
| R² win-criterion banished (D-13) | contract (grep gate) | `test_no_legacy_r2_criterion.py` (5 tests, regex + literal + workflow scan) | ✅ |
| Klines `is_mainnet` filter (B1) | contract | `test_klines_filter_required.py` (5 tests, ±5-line neighborhood) | ✅ |
| TOURN-07 strengthened (B2 — no parallel metric defs) | contract | `test_no_parallel_metric_reimplementations.py` (4 tests, def + lambda forms) | ✅ |
| PEP 420 namespace merge invariant | integration (container) | `test_canonical_metrics_importable.py` (3 tests + 0-SKIP CI guard) | ✅ |
| End-to-end smoke (4 ROADMAP SC in one round-trip) | integration (container) | `test_open_pr_e2e.py` (7 tests) | ✅ |

**Verdict:** Wave-0 fitness met. Every contract boundary has at least one dedicated test, and the most invariant-load-bearing (atomic-write, gh argv, R² ban, no-auto-merge, namespace merge) carry **defense-in-depth via 2-3 layers** (unit + integration + grep-contract). Sampling rate exceeds Nyquist: ~22 tests per production change, with the 2x floor easily cleared.

---

## Manual-Only / Operator-Procedural

| Item | Source | Rationale |
|---|---|---|
| GH Actions CI run on `tournament-harness.yml` | Plan 04-09 SUMMARY hand-off | YAML validated locally; full job chain proven via host 26/26 + container 13/13. CI run blocked by **GH Actions billing** — operator action only (`github.com/settings/billing`). Workflow not yet visible in `gh workflow list` until first successful run. |
| `gh` auth + `GH_TOKEN` rotation | Plan 04-03 SUMMARY (D-11) | Operator-procedural — env var; never argv (T-04-14 mitigation auto-tested); rotation is an operator concern. |
| `tournament-harness` Docker image rebuild after Phase 4 changes | Plan 04-08 SUMMARY | Operator must run `DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml --profile tournament build --no-cache tournament-harness` once per Phase 4 deploy to materialise the PEP 420 namespace merge. Auto-tested invariant (`test_canonical_metrics_importable.py`) confirms the merge after rebuild. |
| `tournament reproduce` HEAD-vs-`--git-sha` operator step | Plan 04-04 SUMMARY (CLI surface) | Operator passes the recorded git SHA; CLI refuses with exit 3 if HEAD doesn't match. Auto-test exists for the refusal branch (`test_head_mismatch_refused`); operator drives the success path manually per tournament. |

---

## Accepted Deferrals

| Item | Source | Rationale |
|---|---|---|
| Production-aggregator second comparator | 04-06 SUMMARY follow-up #1 | D-04 persistence baseline ships in Phase 4; the 9-indicator voting aggregator as a second comparator is **explicitly Phase 5 scope**. Win-gate would carry `sharpe_lift_vs_persistence` + `sharpe_lift_vs_aggregator`. Not a Phase 4 gap. |
| Multiple-testing correction across tournaments (deflated DSR) | 04-06 SUMMARY follow-up #2 | `tournaments_evaluated_count` is **disclosed** (D-09) but not yet used to deflate the per-tournament win rate. Deferred to Phase 5 — explicit follow-up, not a coverage gap. |
| `tournament-pr.yml` snapshot-commit auto-trigger workflow | 04-06 SUMMARY follow-up #3 | Current pipeline is operator-triggered (`tournament open-pr` from shell). Auto-trigger on snapshot-commit is Phase 5. |
| `test_save_model_writes_scalers_pkl_with_expected_keys` (ml-retraining) `is`-identity bug | 04-08 + 04-10 SUMMARY (Gap B) | **Pre-existing**, predates Phase 4. Documented in Phase 3 deferred-items since 03-02. Not introduced by Phase 4; surfaced only by 04-08's broader test runs. |

---

## Gaps Found

**None.** Every plan that shipped production code has at least one dedicated test file, and every contract boundary identified by the PLAN/SUMMARY artifacts has automated coverage.

The two items that surfaced as "gaps" mid-phase (`sharpe_lift = nan` in 04-08, CI-wiring missing four grep gates per 04-VERIFICATION re-verify) were both **closed inside Phase 4** by gap-closure plans 04-09 and 04-10 — they are recorded as resolved-within-phase rather than open gaps.

---

## Test Audit Trail

| Audit Date | Gaps Found | Resolved | Escalated | Manual-Only | Run By |
|------------|------------|----------|-----------|-------------|--------|
| 2026-05-10 | 2 (`sharpe_lift=nan`; CI not wired) | 0 (escalated to in-phase plans) | 2 → 04-09 + 04-10 | 1 (CI run gated on GH billing) | gsd-verifier (initial) |
| 2026-05-13 | 0 | 2 (closed by 04-08 + 04-10 + 04-09) | 0 | 1 (CI run still gated on billing) | gsd-verifier (re-verify; status `verified`) |
| 2026-05-15 | 0 | 0 | 0 | 4 (operator-procedural — see Manual-Only) | gsd-nyquist-auditor (this audit) |

**Final test count (Phase 4 contributions):** 151 new tests across 20 files (108 unit + 43 integration). On host: 213 unit + 26 integration green; in container: 13/13 e2e green (zero skips). Zero regressions.

---

## Sign-Off

- [x] Every requirement (TOURN-05, TOURN-06) maps to an automated command via unit + integration + grep-contract layering.
- [x] Test infrastructure matches what the project already runs (pytest, no new framework introduced; `slow` marker registration cleanly added in 04-02).
- [x] CI gates the load-bearing invariants (D-13 R² ban, CD-10 no auto-merge, B1 klines is_mainnet, B2 no parallel metrics, SC-1 PSR persistence baseline e2e, SC-3 draft PR e2e, namespace-merge regression) via `tournament-harness.yml` 5-job chain.
- [x] Manual-only items are operator-procedural (GH billing, image rebuild, gh auth, reproduce HEAD-vs-SHA) not skipped automation.
- [x] Wave-0 fitness exceeds 2x feature change rate (~22 tests per production plan).
- [x] All in-phase gaps resolved by gap-closure plans 04-08, 04-09, 04-10.
- [x] Phase is **Nyquist-compliant**.
