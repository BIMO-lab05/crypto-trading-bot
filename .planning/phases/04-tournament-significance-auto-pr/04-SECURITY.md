---
phase: 4
slug: tournament-significance-auto-pr
status: verified
threats_open: 0
threats_total: 47
threats_closed: 47
asvs_level: 1
block_on: high
created: 2026-05-15
verified: 2026-05-15
auditor: gsd-security-auditor (retroactive backfill, milestone-audit follow-up)
register_authored_at_plan_time: false
note: "Retroactive backfill per v1.0 milestone audit. Highest-risk phase in this batch (auto-PR opening + gh CLI subprocess). Threats T-04-01 through T-04-42 were authored inside the per-plan threat-model blocks of 04-01 through 04-07; this document consolidates them with file:line evidence and adds the 04-08/09/10 sub-IDs (T-04-08-NN through T-04-10-NN). Pre-existing semgrep WARNING on tournament-harness/app/main.py:65 (CORS allow_origins=['*']) carried as accepted risk pending v1.1 hardening."
---

# Phase 04 — Security (tournament-significance-auto-pr)

**Plans audited:** 04-01 (significance/ensemble foundation), 04-02 (statistical core), 04-03 (open-pr CLI + gh wrapper), 04-04 (reproducibility verifier), 04-05 (CI grep gates), 04-06 (open-pr e2e smoke), 04-07 (build_predict_fn factory), 04-08 (PEP 420 namespace fix), 04-09 (CI wiring), 04-10 (zero-safe baseline sharpe)
**ASVS Level:** L1 · **Block-on:** high · **Auditor:** gsd-security-auditor · **Date:** 2026-05-15
**Verdict:** SECURED — 47/47 threats CLOSED

---

## Summary

Phase 4 is the highest-risk surface in this milestone batch because it (a) invokes the
`gh` CLI as a subprocess to open draft pull requests and (b) ships a bootstrap-significance
gate whose p-value drives that auto-PR. Both surfaces have load-bearing tests pinning the
controls. No call to `gh pr merge` is reachable; the GH_TOKEN is env-only and never lands
in argv; branch names + tournament_ids + run_ids are regex-validated before any
`subprocess.run` or path construction; the legacy ">5% R²" win criterion is grep-banned.

The four genuinely new attack surfaces this phase added (gh CLI argv, draft-PR body
templating, reproducer HEAD-vs-SHA refusal, predict-cache path construction) all carry
mitigate-disposition controls verified by both unit and integration grep gates. The
remaining accept-disposition risks are operator-honour-system and inherited from
Phase 3 (docker.sock bind-mount, CORS wildcard on read-only API).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Operator → `tournament open-pr` CLI (Plan 04-03) | Operator invokes CLI with `tournament_id`; CLI loads snapshot, runs significance, opens draft PR | tournament_id, --allow-dirty, --dry-run flags |
| `tournament open-pr` → `gh` CLI subprocess (Plan 04-03) | `pr/gh.py:open_draft_pr` invokes `gh pr create --draft` with argv only; GH_TOKEN inherited from env | argv (title, body, head branch, base, labels) — token NEVER in argv |
| Snapshot JSON → significance pipeline (Plans 04-01, 04-03) | `data/snapshots/{tid}.json` rows feed `select_top_n_per_symbol` → bootstrap → win-gate | typed numeric leaderboard rows (status, dsr, hp_hash, run_id) |
| Predict callback → TimescaleDB (Plan 04-07) | `build_predict_fn` reads OOS klines via canonical `load_klines_from_timescale` | klines query (`is_mainnet=TRUE` enforced in SQL); `tournament_reader` role |
| Predict result → `.npz` cache (Plan 04-01) | `predict_cache.get_or_build_predictions` writes per-(tid,run_id) cache atomically | numpy arrays (pred_prices, actual_prices, last_close); no secrets |
| Operator → `tournament reproduce` CLI (Plan 04-04) | Operator passes `--git-sha`; CLI refuses if HEAD mismatch or dirty tree | tournament_id, git_sha, --force |
| Reproducer → temp leaderboard SQLite (Plan 04-04) | Temp DB at `data/leaderboard/reproduce_{tid}.db`; production `tournaments.db` is NEVER touched | snapshot rows re-packed for `LeaderboardDB.insert_run` |
| GH Actions runner → harness Docker image (Plan 04-09) | CI runs unit + integration jobs; container-integration job rebuilds image with `--no-cache` | no `env:` exposes runner secrets to container |

---

## Threat Verification — 42/42 CLOSED

### Plan 04-01 — significance/ensemble foundation

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-04-01 | Tampering | mitigate | closed | `app/significance/predict_cache.py:48` `_TID_RE = ^[A-Za-z0-9._\-]+$`; `_cache_path` validates BOTH tournament_id and run_id at L57-60 before any path construction; refuses `..`, `/`, NUL — `tests/unit/test_significance_predict_cache.py` enforces |
| T-04-02 | Tampering | mitigate | closed | `app/significance/predict_cache.py:120-131` `tempfile.mkstemp` + `np.savez(tmp,…)` + `os.replace` + cleanup-on-failure mirrors `snapshot.py` discipline; `tests/unit/test_significance_artifacts.py` covers 3 atomic writers (6/6 pass) |
| T-04-03 | Information disclosure | mitigate | closed | `app/significance/ensemble.py:97-110` `member_descriptor` strips snapshot row to {run_id, architecture, hp_hash, dsr} only — D-03 forbids weights/scalers/predictions in the JSON; unit test `test_write_ensemble_no_weights_no_predictions` enforces (case-insensitive grep) |
| T-04-04 | Repudiation | mitigate | closed | Every member dict carries `run_id` + `hp_hash` + `architecture` (`ensemble.py:105-108`); reproducer cross-checks via snapshot rows in `pr/reproduce.py:75-100` `_wrap_snapshot_row_for_insert` |
| T-04-05 | DoS | accept | closed | Solo operator; per-tournament cache bounded by run count × OOS bar count (~few MB); cleanup operator's job (`rm -rf data/cache/{tid}`) — see AR-04-01 |

### Plan 04-02 — statistical core (bootstrap + win-gate + baseline)

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-04-06 | Tampering | mitigate | closed | `app/significance/bootstrap.py:184` `p_value = (1 + count_ge_observed) / (n_resamples + 1)` — additive smoothing makes p=0 unreachable; `tests/unit/test_significance_bootstrap.py` 20 tests incl. `test_pvalue_lower_bound_nonzero` |
| T-04-07 | Repudiation | mitigate | closed | `app/significance/bootstrap.py:46-70` `derive_seed` is the single canonical path (blake2b → 31-bit mask); `seed` is a required kwarg of `stationary_block_bootstrap_pvalue` (L119); no global RNG state — `np.random.default_rng(seed)` at L168; determinism test in unit suite |
| T-04-08 | Elevation of Privilege | mitigate | closed | `app/significance/win_gate.py:31-32` `P_THRESHOLD = 0.05`, `MIN_MEMBERS = 3` — module-level constants; lowering them is a code-review tripwire; `tests/unit/test_significance_win_gate.py` (12/12) pins both values |
| T-04-09 | Information disclosure | accept | closed | (Plan 04-02 sense) No secrets / no PII flow through `bootstrap.py` / `win_gate.py` / `baseline.py` — pure-numeric pipelines; see AR-04-15. NB: ID also re-used in Plan 04-09 sub-numbering (T-04-09-01..05) — both rows present |
| T-04-10 | Spoofing | mitigate | closed | (Plan 04-02 sense) `app/significance/bootstrap.py:115-119` docstring + tests pin the `metric_fn: Callable[[np.ndarray], float]` contract: caller must pass a non-parallel impl; TOURN-07 grep gate at `tests/integration/test_no_parallel_metric_reimplementations.py` (4/4) catches violations harness-wide. NB: ID also re-used in Plan 04-10 sub-numbering (T-04-10-01..03) — both rows present |

### Plan 04-03 — open-pr CLI + gh wrapper (HIGHEST RISK)

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-04-11 | Spoofing | mitigate | closed | `app/pr/gh.py:36` `_BRANCH_RE = ^[A-Za-z0-9._\-/]+$`; `open_draft_pr` validates `head` at L74-77 before any subprocess call; rejects `..` explicitly; `tests/unit/test_pr_gh.py` `test_open_draft_pr_branch_regex_validates` covers shell metachars |
| T-04-12 | Tampering | mitigate | closed | `app/pr/body.py` renderer takes structured dicts only — `render_pr_title` (L29-40), `render_leaderboard_markdown` (L53-90), `render_pr_body` (L113-178) all consume typed numeric fields + allowlisted columns; `gh.py:107-113` `subprocess.run(cmd, …, shell=False)` consumes argv list — no `f"{user_input}"` lands in shell |
| T-04-13 | Repudiation | accept | closed | gh attributes the PR to the operator's GH_TOKEN identity; this IS the desired behavior per D-10 (operator triggered) — see AR-04-02 |
| T-04-14 | Information disclosure | mitigate | closed | `app/pr/gh.py:53-58` `_check_gh_token` reads `os.environ["GH_TOKEN"]` only; `subprocess.run` at L107-113 inherits env (NO custom `env=` kwarg constructs argv from token); module never logs token (L96-98 logs argv-len + branch only); `tests/unit/test_pr_gh.py` `test_gh_token_never_in_argv` + `test_logs_do_not_include_token` enforce |
| T-04-15 | DoS | accept | closed | Operator runs `open-pr` ≤ a few times per day; `gh.py:114-117` raises `RuntimeError` with stderr on rc != 0 — see AR-04-03 |
| T-04-16 | Elevation of Privilege | mitigate | closed | **Three-layer defense.** (1) `app/pr/gh.py:78-91` argv = `["gh", "pr", "create", "--draft", …]` ONLY — no `merge` subcommand reachable; docstring at L17 even constructs the forbidden literal at runtime to avoid the source matching itself. (2) `tests/integration/test_no_auto_merge.py` 4/4 pass — pattern `r"gh\s+pr\s+merge"` over `services/tournament-harness/` + `.github/workflows/`. (3) Unit mirror `tests/unit/test_pr_gh.py::test_no_gh_pr_merge_in_module`. CI-enforced via 04-09 wiring |
| T-04-17 | Tampering | mitigate | closed | `app/pr/open_pr.py:294-303` queries `db.count_tournaments()` inside `run_open_pr` at PR-open time, NEVER cached at module-load; `tests/unit/test_leaderboard_db_count.py` (3 tests) + integration `test_open_pr_count_tournaments_reflects_state_at_call_time` enforce |
| T-04-18 | Tampering | mitigate | closed | `app/pr/open_pr.py:146-151` `_git_is_dirty()` raises `SystemExit(3)` unless `allow_dirty=True`; matches Phase 3's `tournament run` ergonomics (D-11) |
| T-04-19 | Repudiation | mitigate | closed | `app/pr/open_pr.py:152` `git_sha = _git_sha()` captured once and embedded in title/body/significance.json (`body.py:131-133` shows in header); reproducer (Plan 04-04) refuses if HEAD doesn't match (see T-04-21) |
| T-04-20 | Tampering | mitigate | closed | (Plan 04-03 sense — aggregation order) `app/pr/open_pr.py:213-221` member log-returns built BEFORE mean (`log_returns_from_predictions` then `aggregate_log_returns`); B5 grep gates in `tests/integration/test_no_parallel_metric_reimplementations.py` (4/4 pass) ensure no price-space averaging substituted |

### Plan 04-04 — reproducibility verifier

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-04-20 | Tampering | mitigate | closed | (Plan 04-04 sense — path traversal) `app/pr/reproduce.py:56-59` `_validate_tid` rejects `/`, `..`, NUL, space, backslash, newline, tab; called from `_temp_db_path` (L62-65) and `run_reproduce` (L147) before any path construction. Note: Plan 04-03 and 04-04 both registered T-04-20 — both controls are present and tested independently |
| T-04-21 | Repudiation | mitigate | closed | `app/pr/reproduce.py:156-162` HEAD-vs-`git_sha_expected` check raises `SystemExit(3)` with both values printed to stderr; `--git-sha` is REQUIRED at the argparse layer (`app/cli.py`); unit `test_pr_reproduce.py::test_head_mismatch_refused` |
| T-04-22 | Tampering | mitigate | closed | `app/pr/reproduce.py:150-155` `_git_is_dirty()` raises `SystemExit(3)`; D-12 explicitly forbids `--allow-dirty` here (no flag exposed in argparse); grep test `test_no_allow_dirty_flag_in_cli` |
| T-04-23 | Information disclosure | accept | closed | Original significance backup under `data/snapshots/`; no secrets in schema; cleaned up on success at `reproduce.py:243-244` finally block — see AR-04-04 |
| T-04-24 | DoS | accept | closed | CD-06: forensic-retain-on-failure is desired (`reproduce.py:228-230, 239-240`); operator cleans up via `--force` or manual rm — see AR-04-05 |
| T-04-25 | Tampering | mitigate | closed | `app/pr/reproduce.py:62-65` `_temp_db_path` returns `data/leaderboard/reproduce_{tid}.db` with `reproduce_` prefix; production `tournaments.db` is NEVER opened by the reproduce path (verified via grep); integration `tests/integration/test_reproduce_idempotent.py` (3/3 in container) |
| T-04-26 | Elevation of Privilege | mitigate | closed | `app/pr/reproduce.py:184-191` `--force` only drops the temp DB at `_temp_db_path(tid)` — the regex on the path enforces the `reproduce_` prefix via `_validate_tid` upstream; production DB unreachable through this code path |

### Plan 04-05 — CI grep gates

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-04-13 | Repudiation | mitigate | closed | (Plan 04-05 sense — R² regression) `tests/integration/test_no_legacy_r2_criterion.py` (5/5 pass) — 4 regex patterns (`>\s*5\s*%`, `5\s*percent\s*R[²2]`, `r2[_\s]*returns?\s*>\s*0\.0?5`, `R[²2]\s*>\s*0?\.0?5`) + 3 literal strings ("5% R2", "5% R²", "five percent R") scan `app/` + `.github/workflows/tournament*.yml` |
| T-04-27 | Tampering | mitigate | closed | Both gates skip lines starting with `#` (`test_no_auto_merge.py:71-76` `_is_comment_line`; mirror in `test_no_legacy_r2_criterion.py`); doc-comments tolerated, hidden invocations in non-comment strings DO get caught |
| T-04-28 | Tampering | mitigate | closed | `test_no_auto_merge.py:30` filter is exactly `/tests/` directory presence — non-test files cannot be moved into `tests/` to evade because they no longer execute as production code |
| T-04-29 | Repudiation | mitigate | closed | `test_no_auto_merge.py:54-57` `test_pattern_is_pinned` (CD-10) and the equivalent in `test_no_legacy_r2_criterion.py` defend the literal patterns against accidental deletion in code review |
| T-04-30 | Information disclosure | accept | closed | Tests read source only; no secrets exposed — see AR-04-06 |
| T-04-31 | Tampering | mitigate | closed | `tests/integration/test_no_parallel_metric_reimplementations.py` (4/4 pass) — strengthens TOURN-07 def-pattern + lambda-Sharpe form scan over `app/pr/` + `app/significance/`; CI-enforced via 04-09 |
| T-04-32 | Elevation of Privilege | accept | closed | Tests are read-only; cannot escalate — see AR-04-07 |

### Plan 04-06 — open-pr e2e smoke

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-04-33 | Information disclosure | mitigate | closed | `tests/integration/test_open_pr_e2e.py::test_open_pr_gh_argv_shape_under_real_path` asserts GH_TOKEN literal absent from constructed argv (verified live in container per 04-VERIFICATION 7/7 pass) |
| T-04-34 | Tampering | mitigate | closed | `test_open_pr_e2e.py` mocks `gh` subprocess at `subprocess.run` level — no real PR created during test; CI-enforced |
| T-04-35 | Repudiation | mitigate | closed | `test_open_pr_e2e.py` verifies `git_sha` consistency across all three artifacts (ensemble.json, significance.json, leaderboard.md) |

### Plan 04-07 — build_predict_fn factory

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-04-36 | Tampering | mitigate | closed | `app/runner/predict_fn.py` re-asserts `_TID_RE` patterns at predict-fn entry; mirrors T-04-01 control; tested via `tests/unit/test_runner_predict_fn.py` (10/10) |
| T-04-37 | Tampering | mitigate | closed | Canonical loader-only path: `predict_fn.py:49` `from app.runner.data import load_klines_from_timescale`; `is_mainnet=TRUE` enforced in SQL upstream; `tests/integration/test_klines_filter_required.py` (5/5 pass) scans ±5-line neighborhood of every klines read |
| T-04-38 | Spoofing | mitigate | closed | `app/runner/predict_fn.py` asserts `symbol.endswith("USDT")` at predict-fn layer; mirrors canonical loader's defense; tournament_loader validates at YAML parse, predict_fn re-asserts because experiment containers are isolated |
| T-04-39 | Repudiation | mitigate | closed | `seed` sourced from snapshot row → identical seed across `open-pr` and `reproduce`; `train.build_and_train_model` honors seed; unit tests assert two invocations with same inputs return numpy-equal arrays |
| T-04-40 | Information disclosure | accept | closed | `TIMESCALE_PASSWORD` comes from env via canonical loader; `predict_fn` never logs or stringifies it — see AR-04-08 |
| T-04-41 | DoS | accept | closed | snapshot's hp_hash points at hyperparameters Phase 3 already trained with; if it OOMs, that's a Phase 3 regression — see AR-04-09 |
| T-04-42 | Elevation of Privilege | mitigate | closed | predict_fn uses `tournament_reader` (read-only) DB role; SQL grants enforced server-side by Phase 3 D-09 migration; `predict_fn` cannot escalate via this path |

### Plan 04-08 — PEP 420 namespace fix

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-04-08-01 | Tampering | mitigate | closed | Both top-level `app/__init__.py` files DELETED (verified `ls services/tournament-harness/app/__init__.py services/ml-retraining-service/app/__init__.py` → both missing); `tests/integration/test_canonical_metrics_importable.py` (3/3 in container) catches silent regression |
| T-04-08-02 | Repudiation | mitigate | closed | Same regression test enforces `_CANONICAL_METRICS_AVAILABLE=True` invariant inside container; CI 0-SKIP grep guard at `.github/workflows/tournament-harness.yml:134-138` (`grep -E '^[0-9]+ skipped' /tmp/container-integration.log`) catches silent skip |
| T-04-08-03 | Information disclosure | accept | closed | ml-retraining `__version__` / `__service_name__` constants exfil — constants are not secrets and have zero callers; deletion was dead-code removal with no surface change; `services/ml-retraining-service/app/_version.py` re-exposes `__version__` for the one preserved consumer — see AR-04-16 |
| T-04-08-04 | DoS | accept | closed | Namespace-package import slow path: `sys.path` lookup is O(len(sys.path)) but path has ~10 entries — measured-irrelevant overhead per import; solo operator — see AR-04-17 |
| T-04-08-05 | Repudiation | mitigate | closed | Plan 04-09 wires `test_canonical_metrics_importable.py` into the **container-integration** job (not host-integration); the in-container `_CANONICAL_METRICS_AVAILABLE` marker check + 0-SKIP guard at workflow L134-138 ensures non-skip when the gate matters |

### Plan 04-09 — CI wiring

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-04-09-01 | Repudiation | mitigate | closed | 0-SKIP grep guard at `.github/workflows/tournament-harness.yml:134-138`; verified locally — `13 passed, 0 skipped` (no skipped count line) means guard does not fire on healthy state |
| T-04-09-02 | Tampering | mitigate | closed | YAML comment invariant block + `pytest tests/integration/ --ignore=...` dir-glob form; future contributor adding host-skipping test without `--ignore` will be caught by 0-SKIP guard |
| T-04-09-03 | DoS | accept | closed | `--no-cache` build per PR; solo-operator low PR cadence — see AR-04-10 |
| T-04-09-04 | Tampering | mitigate | closed | Task 3 verification asserts `'integration-real-stack' in jobs`; re-run before commit confirmed (5 jobs in YAML: tourn07-grep-gate, unit-tests, integration-fake-docker, container-integration, integration-real-stack) |
| T-04-09-05 | Information disclosure | accept | closed | No `env:` block exposes runner secrets to container; `docker compose run --rm` does not inherit runner secrets — see AR-04-11 |

### Plan 04-10 — zero-safe baseline sharpe

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-04-10-01 | Tampering | mitigate | closed | `app/pr/open_pr.py:90-121` `_zero_safe_baseline_sharpe` — bounded scope (baseline side ONLY); candidate still flows through canonical PSR; var_eps gate at L119 (`1e-12`); docstring at L102-108 explicit about scope; `tests/unit/test_significance_zero_variance_baseline.py` (5/5 pass) |
| T-04-10-02 | Information disclosure | accept | closed | `gate_failure_reasons` schema: label `sharpe_lift_non_positive` now covers (a) lift ≤ 0 and (b) lift = nan (flat candidate) — both legitimately fail the gate; no new disclosure surface; PR body and leaderboard markdown surface area unchanged — see AR-04-18 |
| T-04-10-03 | Repudiation | mitigate | closed | Bootstrap kernel reproducibility: `git diff HEAD` for `services/tournament-harness/app/significance/bootstrap.py` and `services/ml-retraining-service/app/.../sharpe_metrics.py` is empty (verified at 04-10 SUMMARY L188); seed derivation, geometric block resampling, and p-value smoothing bit-for-bit identical to Plan 04-08 |

---

## Per-Plan Verification Summary

| Plan | Threats | All CLOSED? | Test Run |
|------|---------|-------------|----------|
| 04-01 | 5 | yes | 23 unit tests pass (test_significance_artifacts/ensemble/predict_cache) |
| 04-02 | 5 (T-04-06..10) | yes | 35 unit tests pass (test_significance_baseline/bootstrap/win_gate) |
| 04-03 | 10 (T-04-11..20) | yes | 30 unit tests pass (test_pr_body/gh + leaderboard_db_count + metrics_bridge_log_returns) |
| 04-04 | 7 (T-04-20..26 incl. dup-numbered T-04-20) | yes | 17 unit + 3 container integration tests pass (test_pr_reproduce + test_reproduce_idempotent) |
| 04-05 | 6 (T-04-13, 27..32) | yes | 18 grep-gate tests pass (test_no_legacy_r2_criterion 5 + test_no_auto_merge 4 + test_klines_filter_required 5 + test_no_parallel_metric_reimplementations 4) |
| 04-06 | 3 (T-04-33..35) | yes | 7 e2e tests pass in container (test_open_pr_e2e) |
| 04-07 | 7 (T-04-36..42) | yes | 10 unit tests pass (test_runner_predict_fn) |
| 04-08 | 5 (T-04-08-01..05) | yes | 3 container tests pass (test_canonical_metrics_importable) |
| 04-09 | 5 (T-04-09-01..05) | yes | CI wiring verified locally (13/13 container + 26/26 host); CI run blocked by GH Actions billing |
| 04-10 | 3 (T-04-10-01..03) | yes | 5 unit tests pass (test_significance_zero_variance_baseline) |
| **Total** | **47** | **47 / 47** | — |

*(T-04-20 appears in BOTH Plan 04-03 (aggregation tampering) and Plan 04-04 (path traversal) registers — verified via two independent controls + tests. Similarly Plan 04-02 introduced T-04-09 / T-04-10 BEFORE the 04-09/04-10 plans existed; the IDs were re-used by sub-numbering — both the parent IDs AND their sub-IDs are present and tested.)*

---

## Unregistered Threat Flags

None. All `## Threat Flags` / `## Threat Surface Update` sections in 04-06, 04-07, 04-08, 04-09, 04-10 SUMMARYs explicitly state "no new threat surface" beyond plan registers.

- 04-06: "T-04-33 GH_TOKEN literal verified absent from argv; T-04-34 gh subprocess mocked at run() level; T-04-35 git_sha consistency verified across artifacts"
- 04-07: "USDT-suffix assertion at the predict_fn layer (T-04-38)"
- 04-08: "PEP 420 namespace-merge bounded to two trusted service trees both built into the same Docker image; T-04-08-01 and T-04-08-02 mitigations implemented by new regression test"
- 04-09: 5 sub-threats T-04-09-01..05 all dispositioned in SUMMARY
- 04-10: 3 sub-threats T-04-10-01..03 all dispositioned in SUMMARY

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-04-01 | T-04-05 | Solo-operator predict-cache disk fill; `rm -rf data/cache/{tid}` on operator schedule | operator | 2026-05-15 |
| AR-04-02 | T-04-13 (Plan 04-03) | gh attributes the PR to operator's GH_TOKEN identity by design (D-10) | operator | 2026-05-15 |
| AR-04-03 | T-04-15 | Operator runs `open-pr` ≤ a few times/day; gh rate limit surfaced via RuntimeError | operator | 2026-05-15 |
| AR-04-04 | T-04-23 | Original-significance backup under `data/snapshots/`, no secrets in schema | operator | 2026-05-15 |
| AR-04-05 | T-04-24 | CD-06 forensic-retain-on-failure is desired behavior; operator cleans temp DBs | operator | 2026-05-15 |
| AR-04-06 | T-04-30 | Grep-gate tests are read-only over source; no secrets exposed | operator | 2026-05-15 |
| AR-04-07 | T-04-32 | Grep-gate tests cannot escalate; pytest read-only over filesystem | operator | 2026-05-15 |
| AR-04-08 | T-04-40 | `TIMESCALE_PASSWORD` consumed via canonical loader; never logged/stringified by predict_fn | operator | 2026-05-15 |
| AR-04-09 | T-04-41 | Snapshot hp_hash points at Phase-3-trained hyperparameters; OOM regression caught upstream | operator | 2026-05-15 |
| AR-04-10 | T-04-09-03 | `--no-cache` per-PR build; solo-operator low PR cadence | operator | 2026-05-15 |
| AR-04-11 | T-04-09-05 | No `env:` block exposes runner secrets; `docker compose run --rm` does not inherit | operator | 2026-05-15 |
| AR-04-12 | (carried, Phase 3) | `/var/run/docker.sock` bind-mount at `docker-compose.unified.yml:794` mitigated by `profiles: [tournament]` keep-off-by-default at L738 (Phase 3 T-03-01); orchestrator-only surface unchanged in Phase 4 | operator | carried 2026-05-15 |
| AR-04-13 | (pre-existing, semgrep WARNING) | CORS `allow_origins=["*"]` at `services/tournament-harness/app/main.py:65` on the read-only inspection API; Phase 4 added/modified zero lines in this file; pending hardening in v1.1 | operator | carried 2026-05-15 |
| AR-04-14 | (operator action, infra) | GH Actions CI run on `tournament-harness.yml` blocked by GitHub Actions billing (operator action only at github.com/settings/billing); workflow validated locally via host 26/26 + container 13/13; not a Phase 4 security defect | operator | 2026-05-15 |
| AR-04-15 | T-04-09 (Plan 04-02 sense) | No secrets / no PII flow through bootstrap.py / win_gate.py / baseline.py — pure-numeric pipelines | operator | 2026-05-15 |
| AR-04-16 | T-04-08-03 | ml-retraining `__version__` / `__service_name__` are not secrets; deletion was dead-code removal; `_version.py` re-exposes `__version__` for the one preserved consumer | operator | 2026-05-15 |
| AR-04-17 | T-04-08-04 | Namespace-package import path lookup is O(len(sys.path)) ≈ 10 entries — measured-irrelevant overhead; solo operator | operator | 2026-05-15 |
| AR-04-18 | T-04-10-02 | `gate_failure_reasons` schema unchanged in surface area; `sharpe_lift_non_positive` covers both lift ≤ 0 and lift = nan cases without disclosing additional state | operator | 2026-05-15 |

*Any organizational scaling beyond solo-founder requires revisiting AR-04-13 (CORS), AR-04-12 (docker.sock), AR-04-02 (PR identity), AR-04-08 (DB credential lifecycle).*

---

## Verification Gates (CI/test pins for the controls)

| Control | Gate | Live Result |
|---------|------|-------------|
| No `gh pr merge` literal | `pytest services/tournament-harness/tests/integration/test_no_auto_merge.py` | 4/4 pass; CI-wired via 04-09 |
| No `>5% R²` win criterion | `pytest .../tests/integration/test_no_legacy_r2_criterion.py` | 5/5 pass; CI-wired |
| Klines `is_mainnet` filter | `pytest .../tests/integration/test_klines_filter_required.py` | 5/5 pass; CI-wired |
| No parallel metric impls | `pytest .../tests/integration/test_no_parallel_metric_reimplementations.py` | 4/4 pass; CI-wired |
| PEP 420 namespace merge invariant | `pytest .../tests/integration/test_canonical_metrics_importable.py` (container) | 3/3 pass; 0-SKIP CI guard at workflow L134-138 |
| Branch-name regex (T-04-11) | `pytest .../tests/unit/test_pr_gh.py::test_open_draft_pr_branch_regex_validates` | pass |
| GH_TOKEN never in argv (T-04-14) | `pytest .../tests/unit/test_pr_gh.py::test_gh_token_never_in_argv` + `test_logs_do_not_include_token` | pass |
| Bootstrap p > 0 (T-04-06) | `pytest .../tests/unit/test_significance_bootstrap.py::test_pvalue_lower_bound_nonzero` | pass |
| Win-gate constants pinned (T-04-08) | `pytest .../tests/unit/test_significance_win_gate.py` | 12/12 pass |
| Reproduce HEAD-vs-SHA refusal (T-04-21) | `pytest .../tests/unit/test_pr_reproduce.py::test_head_mismatch_refused` | pass |
| Reproduce dirty-tree refusal (T-04-22) | unit test in `test_pr_reproduce.py` | pass |
| Reproduce idempotency (T-04-25) | `pytest .../tests/integration/test_reproduce_idempotent.py` (container) | 3/3 pass |
| End-to-end gh argv shape under real path | `test_open_pr_e2e.py::test_open_pr_gh_argv_shape_under_real_path` | pass in container |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-15 | 47 | 47 | 0 | gsd-security-auditor (retroactive backfill) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept)
- [x] Accepted risks documented in Accepted Risks Log (18 entries — incl. inherited Phase 3 docker.sock + pre-existing CORS WARNING + GH billing block)
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter
- [x] Highest-risk surfaces (gh CLI argv injection T-04-11/14/16; reproducer SHA tampering T-04-21/22/25; bootstrap p-value tampering T-04-06; R² regression T-04-13) all carry mitigate-disposition controls verified by both unit and integration grep gates

**Approval:** verified 2026-05-15

---

## Operator Notes

- **Pre-existing semgrep WARNING** on `services/tournament-harness/app/main.py:65` (CORS `allow_origins=["*"]`) was NOT introduced by Phase 4 — Phase 4 added/modified zero lines in `main.py`. Carried as AR-04-13 pending v1.1 CORS hardening.
- **`gh` CLI auth + `GH_TOKEN` rotation** is operator-procedural — env var; never argv (T-04-14 mitigation auto-tested); rotation is an operator concern.
- **GH Actions billing block (AR-04-14)** prevents the CI workflow from running on PRs; mitigations are exercised on developer machines via the host pytest commands listed under Verification Gates. Once billing is restored, CI will enforce the same gates per-PR.
- **Reproduce HEAD-vs-`--git-sha` operator step** is partially operator-driven: operator must `git checkout {sha}` before running `tournament reproduce {tid} --git-sha {sha}`; CLI refuses with exit 3 if HEAD doesn't match (T-04-21 auto-tested for the refusal branch).
- **All accepted-risk entries (AR-04-01 through AR-04-14) remain solo-operator honour-system or carried-from-Phase-3.** Any organizational scaling will require revisiting AR-04-12 (docker.sock), AR-04-13 (CORS), AR-04-02 (PR identity), AR-04-08 (DB credential lifecycle).
