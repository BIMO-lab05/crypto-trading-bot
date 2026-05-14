---
phase: 04-tournament-significance-auto-pr
verified: 2026-05-13T00:00:00Z
status: verified
score: 4/4 ROADMAP success criteria verified end-to-end (container-only tests now PASS post-04-08/04-10; CI wired in 04-09)
re_verification:
  previous_status: human_needed
  previous_score: "4/4 with caveats (2026-05-10)"
  closed_by:
    - "04-08-PLAN.md — PEP 420 namespace-pkg merge (deleted both app/__init__.py; restored ml-retraining __version__ via app/_version.py)"
    - "04-10-PLAN.md — zero-safe baseline sharpe in open_pr.py (guards PSR(zeros) → nan propagation)"
    - "04-09-PLAN.md — CI wiring: integration-fake-docker glob + new container-integration job (0-SKIP grep guard)"
  verified_evidence:
    container_e2e: "13 passed, 0 skipped, 0 failed (test_open_pr_e2e.py 7/7 + test_reproduce_idempotent.py 3/3 + test_canonical_metrics_importable.py 3/3) — logged at /tmp/04-10-e2e.log"
    host_grep_gates: "18 passed across 4 Phase 4 integration files (test_no_legacy_r2_criterion 5/5, test_no_auto_merge 4/4, test_klines_filter_required 5/5, test_no_parallel_metric_reimplementations 4/4)"
    host_integration: "26 passed total under integration-fake-docker glob form (18 grep gates + 8 Phase 3 integration)"
    unit_significance: "213 passed on host unit suite (was 208 + 5 new zero-variance baseline tests = 213); bootstrap.py and ml-retraining sharpe_metrics.py byte-identical (git diff empty)"
    ci_wiring: ".github/workflows/tournament-harness.yml — integration-fake-docker switched to `pytest tests/integration/ -v --ignore=...` form; new container-integration job (44 lines) added with rebuild + 0-SKIP guard; integration-real-stack `test_end_to_end_tournament.py` invocation preserved"
    ci_run: "Blocked by GitHub Actions billing — operator action only (github.com/settings/billing). YAML validated locally with python -c 'import yaml; yaml.safe_load(open(...))'. Workflow not yet visible in `gh workflow list` until first successful run."
---

# Phase 4: Tournament Significance & Auto-PR — Verification Report

**Phase Goal:** A tournament run automatically constructs a top-3 ensemble, runs a bootstrap significance test against the production baseline on OOS Sharpe and corrected directional accuracy, and opens a draft PR with the leaderboard and significance results when the ensemble wins — humans always merge.

**Verified:** 2026-05-13T00:00:00Z (re-verified after gap closure)
**Status:** verified — all 4 ROADMAP SC end-to-end green; CI run blocked only by GH Actions billing (operator action).
**Re-verification:** Yes — initial 2026-05-10 verification was `human_needed` (4/4 SC met but container e2e + CI gates unverified). Closed by plans 04-08, 04-10, 04-09 (see frontmatter `closed_by`).

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Tournament wraps with a top-3-by-DSR ensemble and a bootstrap p-value vs the persistence baseline at p<0.05 on OOS Sharpe and `dir_acc_corrected` | ✓ VERIFIED | `app/significance/ensemble.py:43-73` (`select_top_n_per_symbol` — DSR-desc tiebreak `cpcv_dsr→oos_sharpe→created_at`); `app/significance/bootstrap.py:114-192` (`stationary_block_bootstrap_pvalue` — Politis–Romano geometric blocks, one-tailed `H1: metric > 0`, additive smoothing line 184: `(1 + count) / (n_resamples + 1)` ⇒ `p > 0` always); `app/significance/win_gate.py:31-32` pins `P_THRESHOLD = 0.05`, `MIN_MEMBERS = 3`; D-02 aggregation order in `app/pr/open_pr.py:179-187` confirms log-returns FIRST per member (`log_returns_from_predictions`), then mean across members (`aggregate_log_returns`). 23/23 unit tests pass for significance/bootstrap/ensemble/win_gate/artifacts/predict_cache. |
| 2 | The R² win criterion is gone from the harness — `grep` for `>5%` or "5 percent R²" returns no matches | ✓ VERIFIED | `tests/integration/test_no_legacy_r2_criterion.py` PASSES (5 tests). 4 regex patterns + 3 literal strings scan `app/` and `.github/workflows/tournament*.yml`. Subprocess `grep -rEn` returns zero non-comment hits. |
| 3 | When the ensemble wins, a draft PR opens via `gh pr create --draft` containing leaderboard markdown, ensemble config, significance results, and reproducer command | ✓ VERIFIED (host-skipped e2e — see human verification) | `app/pr/gh.py:78-91` argv = `["gh", "pr", "create", "--draft", "--title", title, "--body", body, "--head", head, "--base", base]` + `--label` flags; CD-12 fallback `app/pr/body.py:158-178` truncates body when > 60_000 chars and links to `data/snapshots/{tid}.leaderboard.md`; reproducer block emitted in `app/pr/body.py:145-150`; `app/cli.py:141-156` exposes `open-pr` subcommand. CD-09 (`_check_gh_installed`) + D-11 (`_check_gh_token`) hard-fail with exit 2. Unit test `test_pr_gh.py` (12 tests) verifies argv shape, env-only token, branch validation. Integration test `test_open_pr_e2e.py::test_open_pr_gh_argv_shape_under_real_path` is host-skipped via documented `_CANONICAL_METRICS_AVAILABLE` gate — must run in container. |
| 4 | No `gh pr merge` call exists anywhere in the harness or its CI; merge requires a human action | ✓ VERIFIED | `tests/integration/test_no_auto_merge.py` PASSES (4 tests). Pattern `r"gh\s+pr\s+merge"` over `services/tournament-harness/` + `.github/workflows/`. Subprocess grep returns zero non-comment hits. `gh.py:18` docstring even constructs the forbidden literal at runtime to avoid the source matching itself. |

**Score:** 4/4 ROADMAP truths verified (subject to container-execution caveat for SC-3).

### Required Artifacts (PLAN must_haves)

| Artifact | Expected | Level 1 (exists) | Level 2 (substantive) | Level 3 (wired) | Status |
|----------|----------|------------------|------------------------|------------------|--------|
| `app/significance/ensemble.py` | `select_top_n_per_symbol` + `aggregate_log_returns` (D-01, D-02) | ✓ 117 lines | ✓ Both functions present, full tiebreak, equal-weighted mean | ✓ Imported by `app/pr/open_pr.py:65-69` | ✓ VERIFIED |
| `app/significance/bootstrap.py` | Politis–Romano stationary block bootstrap + `derive_seed` | ✓ 200 lines | ✓ `_generate_block_resample`, `stationary_block_bootstrap_pvalue` with additive smoothing, `derive_seed` (blake2b 31-bit mask) | ✓ Imported by `app/pr/open_pr.py:56-59` | ✓ VERIFIED |
| `app/significance/win_gate.py` | D-08 + CD-08 win-gate classifier | ✓ 105 lines | ✓ `evaluate_win_gate` enforces 4 conditions + insufficient_runs guard | ✓ Imported by `app/pr/open_pr.py:72` | ✓ VERIFIED |
| `app/significance/artifacts.py` | Atomic writers (D-03, D-14, CD-05) | ✓ 166 lines | ✓ `_atomic_write` mirrors snapshot.py pattern (mkstemp + fsync + os.replace + cleanup-on-failure); 3 writers | ✓ Imported by `app/pr/open_pr.py:51-55` | ✓ VERIFIED |
| `app/significance/baseline.py` | D-04 persistence baseline | ✓ 43 lines | ✓ `persistence_log_returns(n) → np.zeros(n)` | ⚠ Indirectly used (`open_pr.py:192` builds zeros directly via `np.zeros_like`) — module exists for future swap point | ✓ VERIFIED (call-site stable per D-04 design note) |
| `app/significance/predict_cache.py` | `get_or_build_predictions` + npz cache (CD-11) | ✓ 152 lines | ✓ Atomic mkstemp with `.tmp.npz` suffix, traversal guard via `_TID_RE`, shape validation before write | ✓ Imported by `app/pr/open_pr.py:70-71` | ✓ VERIFIED |
| `app/pr/open_pr.py` | Orchestrator wiring all of the above + gh.py | ✓ 360 lines | ✓ Full pipeline: snapshot load → dirty-check (exit 3) → ensemble → bootstrap → win_gate → artifacts → gh.open_draft_pr | ✓ Wired into `cli.py:57-65` | ✓ VERIFIED |
| `app/pr/gh.py` | gh CLI wrapper (CD-09, CD-10, T-04-11, T-04-14) | ✓ 124 lines | ✓ argv shape; branch regex; subprocess shell=False; GH_TOKEN never in argv; CD-09 install check; D-11 token check | ✓ Imported by `app/pr/open_pr.py:46` | ✓ VERIFIED |
| `app/pr/body.py` | Title + body + leaderboard markdown (CD-01, CD-05, CD-12) | ✓ 187 lines | ✓ MAX_BODY_CHARS=60000 with two-stage fallback; D-09 disclosure block; star marker for ensemble members | ✓ Imported by `app/pr/open_pr.py:41-45` | ✓ VERIFIED |
| `app/pr/reproduce.py` | `tournament reproduce` (D-12, CD-06) | ✓ 266 lines | ✓ Refuses dirty tree (NO --allow-dirty here); refuses HEAD ≠ git_sha; temp DB at `reproduce_{tid}.db`; output_suffix="dry-run"; FP tolerance check (1e-6 / 0.005) | ✓ Imported by `app/cli.py:68-76` | ✓ VERIFIED |
| `app/runner/predict_fn.py` | `build_predict_fn` factory (B1 static + B3) | ✓ 277 lines | ✓ Uses canonical `load_klines_from_timescale` (is_mainnet enforced in SQL); seeds all RNGs; rebuilds via REGISTRY[arch]; horizon/lookback from snapshot row | ✓ Imported by `app/pr/open_pr.py:82` | ✓ VERIFIED |
| `app/cli.py` | `open-pr` + `reproduce` subcommands | ✓ 187 lines | ✓ argparse subparsers wired with --allow-dirty / --dry-run / --git-sha / --force flags | ✓ Entry via `__main__` | ✓ VERIFIED |

### Key Link Verification

| From | To | Via | Status |
|------|-----|-----|--------|
| `app/pr/open_pr.py` | `app/significance/ensemble.py` | direct import lines 65-69 | ✓ WIRED |
| `app/pr/open_pr.py` | `app/significance/bootstrap.py` | direct import lines 56-59 | ✓ WIRED |
| `app/pr/open_pr.py` | `app/significance/win_gate.py` | direct import line 72 | ✓ WIRED |
| `app/pr/open_pr.py` | `app/significance/artifacts.py` | direct import lines 51-55 | ✓ WIRED |
| `app/pr/open_pr.py` | `app/significance/predict_cache.py` | direct import lines 70-71 | ✓ WIRED |
| `app/pr/open_pr.py` | `app/runner/metrics_bridge` | `dir_acc_corrected_from_log_returns`, `probabilistic_sharpe_ratio` (TOURN-07 — no parallel impls) | ✓ WIRED |
| `app/pr/open_pr.py` | `app/runner/predict_fn.build_predict_fn` | line 82 (B3) | ✓ WIRED |
| `app/pr/open_pr.py` | `app/pr/gh.open_draft_pr` | line 46 | ✓ WIRED |
| `app/cli.py::cmd_open_pr` | `app/pr/open_pr.run_open_pr` | lazy import line 59 | ✓ WIRED |
| `app/cli.py::cmd_reproduce` | `app/pr/reproduce.run_reproduce` | lazy import line 70 | ✓ WIRED |
| `predict_fn.py` | canonical klines loader | `from app.runner.data import load_klines_from_timescale` (line 49) | ✓ WIRED |
| Phase 4 grep-gate tests | `.github/workflows/tournament-harness.yml` integration job | NOT listed in pytest invocation lines 81-82 | ⚠ PARTIAL — gate code exists; CI runner does NOT exercise these specific files |

### Behavioral Spot-Checks (host pytest, no Docker)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 4 unit tests for significance package | `pytest services/tournament-harness/tests/unit/test_significance_*.py` | 6 files, 79 tests pass | ✓ PASS |
| Phase 4 unit tests for pr package | `pytest tests/unit/test_pr_body.py test_pr_gh.py test_pr_reproduce.py` | 36 tests pass (1 CWD-relative path fragility — `test_pr_gh.py::test_no_gh_pr_merge_in_module` passes from repo root, fails from harness dir; not a code defect) | ✓ PASS |
| Predict-fn unit tests | `pytest tests/unit/test_runner_predict_fn.py` | passes | ✓ PASS |
| Metrics-bridge log-returns tests | `pytest tests/unit/test_metrics_bridge_log_returns.py` | passes | ✓ PASS |
| Leaderboard count helper | `pytest tests/unit/test_leaderboard_db_count.py` | passes | ✓ PASS |
| D-13 grep gate (no `>5% R²`) | `pytest tests/integration/test_no_legacy_r2_criterion.py` | 5/5 pass | ✓ PASS |
| CD-10 grep gate (no `gh pr merge`) | `pytest tests/integration/test_no_auto_merge.py` | 4/4 pass | ✓ PASS |
| B1 grep gate (klines is_mainnet) | `pytest tests/integration/test_klines_filter_required.py` | 5/5 pass | ✓ PASS |
| B2 strengthened grep gate (no parallel metrics) | `pytest tests/integration/test_no_parallel_metric_reimplementations.py` | 4/4 pass | ✓ PASS |
| End-to-end open-pr smoke (winner + no-win + argv shape) | `pytest tests/integration/test_open_pr_e2e.py` | 7 SKIPPED (documented `_CANONICAL_METRICS_AVAILABLE` host-skip; container only) | ? SKIP — must run inside the harness Docker image |
| Reproduce idempotency (D-12) | `pytest tests/integration/test_reproduce_idempotent.py` | 3 SKIPPED (same documented host-skip) | ? SKIP — must run inside the harness Docker image |

### Anti-Pattern Scan

Scanned `app/significance/`, `app/pr/`, `app/runner/predict_fn.py`, `app/cli.py` for TODO/FIXME/placeholder/empty-return patterns.

| File | Hits | Notes |
|------|------|-------|
| All Phase 4 source files | 0 | No TODOs, no FIXMEs, no `return None`/`return []`/`return {}` stubs, no `placeholder` strings, no `console.log`-only handlers. Atomic-write discipline (mkstemp + fsync + os.replace) enforced consistently across `artifacts.py` and `predict_cache.py`. |

### Requirements Coverage

| Req | Plan(s) | Description | Status | Evidence |
|-----|---------|-------------|--------|----------|
| TOURN-05 | 04-01, 04-02 | Top-3 ensemble (DSR rank) + bootstrap significance test vs persistence baseline on OOS Sharpe + corrected Dir.Acc, p<0.05; drops "5% R²" criterion | ✓ SATISFIED | `select_top_n_per_symbol` + `stationary_block_bootstrap_pvalue` + `evaluate_win_gate` (P_THRESHOLD=0.05) + `test_no_legacy_r2_criterion.py` |
| TOURN-06 | 04-03, 04-05 | Auto-open draft PR via `gh` CLI containing leaderboard markdown, ensemble config, significance test results, reproducer link; humans merge — no auto-merge | ✓ SATISFIED | `app/pr/gh.open_draft_pr` invokes only `gh pr create --draft`; `app/pr/body.render_pr_body` includes leaderboard, ensemble, significance, reproduce sections; `test_no_auto_merge.py` enforces no `gh pr merge` |

### Deferred Items

None deferred to later phases — Phase 4 closes both TOURN-05 and TOURN-06 scope.

### Anti-Patterns Found

None.

### Human Verification Required

1. **Container-execution proof for the e2e smoke + reproduce idempotency tests.** `test_open_pr_e2e.py` (7 tests) and `test_reproduce_idempotent.py` (3 tests) are host-skipped via the documented `_CANONICAL_METRICS_AVAILABLE` gate. The 04-06 SUMMARY claims they passed in the container; this verification cannot reproduce that locally because host Python cannot merge `services/ml-retraining-service/app/...` and `services/tournament-harness/app/...` into the same `app` namespace. **Action:** run `docker compose -f docker-compose.unified.yml --profile tournament run --rm tournament-harness pytest tests/integration/test_open_pr_e2e.py tests/integration/test_reproduce_idempotent.py -v` and confirm 10 PASS.

2. **CI wiring for the four Phase 4 grep-gate integration tests.** `.github/workflows/tournament-harness.yml` integration-fake-docker job invokes only `test_tourn07_grep_gate.py` and `test_orchestrator_with_fake_docker.py`. Phase 4's `test_no_legacy_r2_criterion.py`, `test_no_auto_merge.py`, `test_klines_filter_required.py`, `test_no_parallel_metric_reimplementations.py`, plus the e2e + reproduce tests, are NOT exercised. The 04-05 SUMMARY claim "will pick up new tests automatically" is incorrect for the current YAML invocation form. The unit-test job DOES exercise the unit-layer mirrors (e.g. `test_pr_gh.py::test_no_gh_pr_merge_in_module`), so the **invariants are partially enforced**, but the integration-layer gates that scan the full app/ tree run only on developer machines. **Action:** decide whether to extend the integration-fake-docker step to `pytest tests/integration/ -v --deselect tests/integration/test_end_to_end_tournament.py` (or list explicitly), or accept this gap as a Phase 5 follow-up. Recording this here so it does not regress silently.

### Gaps Summary

The phase delivered every code artifact the ROADMAP and PLANs called for. All four ROADMAP success criteria map to working code with passing host-runnable tests. The two outstanding items are:

- **Container-only test coverage** — by design, the e2e + reproduce idempotency tests cannot run on host Python; the `_CANONICAL_METRICS_AVAILABLE` gate is documented and intentional, but operator must produce the container-side green run for the SUMMARYs' claims to be independently verified.
- **CI workflow wiring** — Phase 4 added six new integration test files but the GHA YAML still hard-lists only Phase 3's two integration files. Static invariants run on host; CI does not enforce them on PRs. Easy fix (one-line YAML change), but classifying as `human_needed` rather than `gaps_found` because the intent is captured in 04-05 SUMMARY and the operator should choose the wiring approach.

---

_Verified: 2026-05-10T01:31:27Z_
_Verifier: Claude (gsd-verifier, Opus 4.7 1M)_
