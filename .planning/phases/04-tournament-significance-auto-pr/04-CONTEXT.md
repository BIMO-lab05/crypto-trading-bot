# Phase 4: Tournament Significance & Auto-PR - Context

**Gathered:** 2026-05-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4 turns Phase 3's tournament leaderboard snapshot into an evidence-backed PR. The harness reads `services/tournament-harness/data/snapshots/{tournament_id}.json`, builds **per-symbol top-3-by-DSR ensembles**, runs a one-tailed block-bootstrap significance test against a **persistence baseline** on OOS Sharpe and `dir_acc_corrected`, and — when at least one symbol clears `p<0.05` AND positive-lift on both metrics — opens a **draft GitHub PR** via `gh pr create --draft` containing the leaderboard markdown, ensemble config, significance results, and a single-line reproducer command. **No `gh pr merge` is invoked anywhere; humans always merge.** The legacy ">5% R²" win criterion is forbidden via a CI grep gate.

**In scope:**
- New `services/tournament-harness/app/significance/` module (bootstrap test, ensemble builder, win-gate)
- New `services/tournament-harness/app/pr/` module (gh CLI invocation, PR body templating)
- New CLI subcommands on the existing `app/cli.py`: `tournament open-pr {tid}`, `tournament reproduce {tid} --git-sha {sha}` (operator triggers, never automatic)
- Per-symbol top-3-by-DSR ensemble construction from snapshot rows
- Average-of-log-returns ensemble aggregation reusing `returns_metrics.py`
- Persistence baseline computed from the same OOS bars used by leaderboard rows
- Stationary block bootstrap (block_size = `floor(sqrt(N))`), one-tailed, n_resamples=10000, paired on per-bar return differences
- Win gate: per-symbol `p<0.05` AND positive raw lift on BOTH OOS Sharpe AND `dir_acc_corrected`
- PR body: leaderboard markdown (top-N + significance markers), ensemble config (run_ids by reference), significance results JSON inline, reproducer line, `tournaments_evaluated_count` + Bonferroni note
- Output artifacts written to `services/tournament-harness/data/snapshots/{tournament_id}.{ensemble,significance,leaderboard}.{json,md}` alongside the existing `{tournament_id}.json`
- New CI test `services/tournament-harness/tests/test_no_legacy_r2_criterion.py` enforcing the no-R²-win-criterion grep gate
- New CI test `services/tournament-harness/tests/test_no_auto_merge.py` enforcing no `gh pr merge` anywhere in `services/tournament-harness/` or `.github/workflows/tournament*`

**Out of scope (other phases / deferred):**
- Forward-paper-test of opt-in features (vol parity, maker, funding) — Phase 5 (MLCL-01)
- T0.1.x next-attempt experiment selection — Phase 5 (MLCL-02)
- Auto-flipping `ENABLE_ML_PREDICTIONS=true` on win — explicitly NOT in scope; PR is the gate, operator decides
- Production-aggregator (no-ML) baseline — deferred (D-04 below) — reconsider if persistence-only proves too easy a bar
- Per-architecture, cross-symbol, or pooled-multi-symbol ensembles — locked at per-symbol top-3
- Storing ensemble model weights in git — config-by-reference only
- Frontend significance/PR view — Phase 7 (DASH-04 may surface significance markers from snapshot)
- CI workflow that auto-fires `tournament open-pr` on snapshot commit — operator-in-the-loop is structural, not stylistic
- N-consecutive-winning-tournaments gate — anti-cherry-picking handled via PR-body disclosure, not a code block
- Bumping `n_resamples` to 100k — defer until borderline-p tournaments become a pattern

</domain>

<decisions>
## Implementation Decisions

### Ensemble construction & inference
- **D-01:** Ensemble selection scope = **per-symbol top-3-by-DSR**. For each symbol `s` in the snapshot's `symbols` set, pick the 3 successful runs (`status=success`) with the highest `dsr` (ties broken by `cpcv_dsr`, then `oos_sharpe`, then `created_at` ascending for determinism). Symbols with fewer than 3 successful runs are reported as "insufficient runs" and skipped from the gate; PR body lists them. Single global top-3 and per-(symbol, architecture) top-3 rejected: per-symbol matches how production trades and produces one ensemble per deployment unit.
- **D-02:** Ensemble aggregation = **mean of predicted log-returns**. For each ensemble member, recover its OOS prediction array, convert to log-returns vs `last_close` per row (mirroring `returns_metrics.py:compute_returns_metrics`), then take the equal-weighted mean across the 3 members per timestep. Sharpe + `dir_acc_corrected` are computed directly on the averaged log-return series — no re-conversion to price for metric purposes (price form is for human display only). DSR-weighted averaging rejected for v1 (one cell can dominate; revisit if equal-weight underperforms in practice). Voting on direction rejected (loses magnitude → weak Sharpe estimator).
- **D-03:** Ensemble artifact = **`{tournament_id}.ensemble.json` — config-by-reference only**. JSON contains `tournament_id`, `git_sha`, `created_at`, `aggregation: "mean_log_returns"`, and per-symbol `ensembles: [{symbol, members: [{run_id, architecture, hp_hash, dsr}, ...]}]`. NO model weights, NO scalers, NO prediction arrays. Reproducer (D-12) re-derives predictions deterministically by re-training the 3 cells from the same seeds. Matches Phase 3 D-18 ("snapshots, not weights").

### Baseline & significance test
- **D-04:** Baseline = **persistence only** (predict next-bar close = current close → log-return = 0). Aligns with the load-bearing reference in `returns_metrics.py:9` ("a persistence baseline gets the same number"). No production-aggregator runtime hook needed — keeps the harness offline. Production-aggregator baseline left as a Phase 5 follow-up (see deferred); if persistence proves trivially beatable, raise the bar then.
- **D-05:** Bootstrap method = **stationary block bootstrap** on per-bar paired return differences `d_t = ensemble_log_ret_t - baseline_log_ret_t = ensemble_log_ret_t - 0 = ensemble_log_ret_t`. Block size = `max(2, floor(sqrt(N)))` where N is the number of OOS bars. Stationary (Politis-Romano geometric block lengths) chosen over fixed-block to remove the block-size knife-edge. IID paired bootstrap rejected — crypto returns autocorrelate at minute scale, IID overstates significance.
- **D-06:** Resamples = **n_resamples = 10000**, one-tailed (`H1: ensemble metric > baseline metric`). Test statistic per resample = `metric(resampled_d) - 0` for both Sharpe and `dir_acc_corrected`. p-value = `(1 + count(stat_resampled <= 0)) / (n_resamples + 1)` (additive smoothing per Davison & Hinkley §4.2 — never reports `p=0`). One-tailed because we want "better", not "different"; two-tailed wastes statistical power on the side we don't care about.
- **D-07:** Significance code home = **new `services/tournament-harness/app/significance/bootstrap.py`** (paired block bootstrap), `app/significance/baseline.py` (persistence reference series), `app/significance/ensemble.py` (top-3 selection + aggregation), `app/significance/win_gate.py` (per-symbol pass logic). Tournament-specific concern stays in tournament-harness. `services/risk-metrics-service/app/cpcv.py` (production module) NOT extended — Phase 3 already locked the no-parallel-metrics rule, and that module ships in production trading paths (don't grow it with tournament-only code). For OOS slice construction, reuse the `cpcv` library functions by import only, not extension.

### Win gate & anti-cherry-picking
- **D-08:** Win gate (per symbol) = **all four conditions must hold**:
  1. `p_value(OOS Sharpe lift) < 0.05`
  2. `p_value(dir_acc_corrected lift) < 0.05`
  3. raw `OOS Sharpe(ensemble) - OOS Sharpe(baseline) > 0`
  4. raw `dir_acc_corrected(ensemble) - dir_acc_corrected(baseline) > 0`
  PR fires when **at least one symbol passes**; symbols that fail are reported in the PR body as `no win` with their p-values + lifts so the reviewer sees the full picture. Conditions (3)+(4) prevent the "significantly worse" loophole where a one-tailed test technically passes against the null but the lift is in the wrong direction (paranoid but cheap).
- **D-09:** Anti-cherry-picking = **disclosure, not blocking**. PR body MUST include:
  - `tournaments_evaluated_count` = `SELECT COUNT(DISTINCT tournament_id) FROM tournaments` from the leaderboard DB at PR-open time
  - Bonferroni-style adjusted note: `p_adjusted ≈ p × tournaments_evaluated_count`, with the explicit comment that DSR already deflates *within* a tournament but does NOT deflate *across* tournaments
  - The list of prior `tournament_id`s the operator can compare against
  Operator-discipline gate, not a code gate. N-consecutive-winners and idempotency-on-tournament-id rejected (slow + encourages parameter-tuning to chase streaks; idempotency conflicts with reproducer-by-rerun semantics).

### Auto-PR mechanics
- **D-10:** Trigger = **separate `tournament open-pr {tid}` CLI subcommand**, never inline at end of `tournament run`. `tournament run` writes the snapshot only. Operator inspects, then runs `tournament open-pr {tid}` which:
  1. Loads `{tournament_id}.json` (errors if missing)
  2. Builds per-symbol ensembles + writes `{tournament_id}.ensemble.json`
  3. Runs significance + writes `{tournament_id}.significance.json`
  4. If win-gate passes for ≥1 symbol → writes `{tournament_id}.leaderboard.md` and invokes `gh pr create --draft`
  5. If no symbol passes → writes the same artifacts plus a `no_win=true` flag and exits 0 (success — "tournament evaluated, no winner") with a clear stdout summary; NO PR opened
  Matches PROJECT.md constraint "No unattended loops that can commit/push without checkpoint review". CI-trigger-on-snapshot-commit and inline-at-tournament-end both rejected for the same reason.
- **D-11:** PR target + auth = **read repo from `git remote get-url origin` (parsed to `owner/name`); require `GH_TOKEN` env var or hard-fail with `exit 2`**. No config knob, no CLI override flag, no soft skip. Failure mode is the one we MOST want to surface — a missing PR after a winning tournament is the worst possible silent failure. Behavior on dirty git tree: refuse with `exit 3` unless `--allow-dirty` (mirrors Phase 3's `tournament run --allow-dirty` ergonomics).
- **D-12:** Reproducer command in PR body = **single line**: `python -m services.tournament_harness.app.cli reproduce {tournament_id} --git-sha {git_sha}`. The new `reproduce` subcommand:
  1. Refuses if working tree dirty (no `--allow-dirty` here — reproducibility is the whole point)
  2. Refuses if `git rev-parse HEAD != git_sha` (operator must `git checkout {git_sha}` first; the message in the PR body says so)
  3. Restores the tournament YAML from the snapshot's `config` block, runs `tournament run` with the same `tournament_id` (refuses if that ID already exists in the DB — operator must drop or pass `--force`), then re-runs the full `open-pr` pipeline in `--dry-run` mode (writes artifacts, no `gh pr create`), and prints a diff between the original and re-derived `significance.json`
  Within FP-noise tolerance (Sharpe diff `< 1e-6`, p-value diff `< 0.005` allowing for bootstrap re-randomization within the same RNG seed), the diff must be empty — else exit 4 ("reproducibility broken; investigate").

### R² grep gate
- **D-13:** R² gate = **CI test `services/tournament-harness/tests/test_no_legacy_r2_criterion.py`** that runs `subprocess.check_output(["grep", "-rEn", PATTERNS, "services/tournament-harness/app/", "services/tournament-harness/tests/", ".github/workflows/tournament*.yml"])` and asserts no matches. Patterns: `>\s*5\s*%`, `5\s*percent\s*R[²2]`, `r2[_\s]*returns?\s*>\s*0\.0?5`, `R[²2]\s*>\s*0?\.0?5`, plus the literal strings `"5% R2"`, `"5% R²"`, `"five percent R"`. Matches Phase 3's pattern (`tests/test_no_parallel_metrics.py` for TOURN-07). Build-time, not runtime — runtime assertions catch dynamic uses but miss comments/strings/docs, and Phase 3 established grep-gate-as-pytest as the convention.

### Output artifact layout (Claude's Discretion → defaults below)
- **D-14:** All Phase 4 artifacts live under `services/tournament-harness/data/snapshots/` next to the existing `{tournament_id}.json`:
  - `{tournament_id}.ensemble.json` — config-by-reference (D-03)
  - `{tournament_id}.significance.json` — `{per_symbol: {symbol: {sharpe_lift, sharpe_pvalue, dir_acc_lift, dir_acc_pvalue, n_oos_bars, block_size, n_resamples, win_gate_passed: bool, n_members: int}}, baseline: "persistence", aggregation: "mean_log_returns", git_sha, evaluated_at, tournaments_evaluated_count, n_winning_symbols}`
  - `{tournament_id}.leaderboard.md` — top-5-by-DSR rows per symbol with per-row `dsr`, `psr`, `cpcv_dsr`, `oos_sharpe`, `dir_acc_corrected`, `architecture`, `hp_hash`; the 3 ensemble members per symbol marked with `★`; `[WIN]` / `[no win]` / `[insufficient runs]` tag per symbol
  All four files committed when the operator commits the snapshot (no separate gitignore entries — they are the receipts).

### Claude's Discretion

These were not selected for deep-dive but downstream agents should treat the stances as defaults; surface in RESEARCH.md / PLAN.md and operator can override before execution.

- **CD-01 (PR title format):** `Tournament {tournament_id}: ensemble wins {n_winning_symbols}/{n_total_symbols} symbols (p<0.05 vs persistence)`. Single line, ≤90 chars; truncate `tournament_id` to 12 chars if needed (it's a hash). Body carries the full table.
- **CD-02 (PR branch naming):** `tournament/{tournament_id}` (e.g., `tournament/2026-05-09-bnb-grid-a3f1c2`). One branch per tournament — re-running `open-pr` for the same `tid` updates the existing branch's PR via `gh pr edit` (gh's natural idempotency), not a new PR. If the branch already exists locally, push to it; if not, create from current HEAD.
- **CD-03 (PR labels):** `tournament`, `evaluation-gate`, plus `winner` only when `n_winning_symbols >= 1`. Created via `gh pr create --label`. If the labels don't exist on the repo, `gh` ignores them (no hard fail there — labels are discoverability, not gate).
- **CD-04 (PR assignees / reviewers):** none auto-assigned. Solo founder per PROJECT.md; assignees would be noise. If the PR-opener wants to override, use `gh pr edit --add-reviewer` after.
- **CD-05 (Leaderboard markdown row format):** standard GFM table; columns in a fixed order so diffs across tournaments are readable. Numeric columns rounded to 4dp for display only (raw values stay in `significance.json`).
- **CD-06 (`reproduce` subcommand interaction with snapshot DB):** Phase 3 leaderboard DB is gitignored; the snapshot JSON contains all rows needed to rebuild it. `reproduce` builds a temp SQLite under `data/leaderboard/reproduce_{tournament_id}.db`, ingests the snapshot rows verbatim, and operates against the temp DB to keep the operator's main leaderboard untouched. Cleaned up on success; left in place on failure for forensic inspection.
- **CD-07 (Bootstrap RNG seed):** `seed = int(hashlib.blake2b(f"{tournament_id}|sig|{symbol}".encode(), digest_size=8).hexdigest(), 16) & 0x7FFFFFFF`. Tournament-id-derived so `reproduce` lands on the same resamples; per-symbol-derived so symbols don't share state. Stamped on every `significance.json` per-symbol block as `bootstrap_seed`.
- **CD-08 (Insufficient-runs threshold):** symbols with `< 3 status=success` runs in the snapshot are skipped from the gate, reported as `[insufficient runs]` in `leaderboard.md`, and contribute `n_members < 3` to `significance.json` for that symbol. PR still opens if at least one OTHER symbol wins; if NO symbol has ≥3 successful runs, the whole pipeline exits 0 with `no_win=true` and "insufficient data" reason.
- **CD-09 (gh CLI absence):** if `gh` is not on PATH, `open-pr` exits 2 with the install hint `https://cli.github.com/`. Same exit code as missing token (operator-fixable env issue).
- **CD-10 (Auto-merge guard):** the `test_no_auto_merge.py` test asserts `subprocess.check_output(["grep", "-rEn", "gh\\s+pr\\s+merge", "services/tournament-harness/", ".github/workflows/"])` returns no matches. Same-shape gate as the R² grep gate (D-13). Both gates run in the same nightly CI step.
- **CD-11 (Where ensemble OOS bars come from):** the snapshot rows already carry per-cell `cpcv_dsr` derived from CPCV folds — which means each cell already evaluated against the same `is_mainnet=true` 12mo OOS slice via `evaluate_with_cpcv`. The ensemble's OOS prediction series is reconstructed by re-running predict on the same OOS bars (TimescaleDB `klines WHERE timestamp BETWEEN tournament_start_ts - 365d AND tournament_start_ts AND is_mainnet=true`) using the 3 retrained models. Because the snapshot is config-by-reference (D-03), the runner must call back into the Phase 3 `tournament run` machinery for the 3 cells (or a stripped `runner.predict_only` path — design choice for the planner). Caching predictions on disk between `open-pr` and `reproduce` invocations: TBD by planner; recommended `data/cache/{tournament_id}/predictions/{run_id}.npz`.
- **CD-12 (PR body length):** GitHub PR body cap is 65k chars; `leaderboard.md` for a wide tournament can blow past that. If `len(body) > 60000`, embed a summary header + a link to `services/tournament-harness/data/snapshots/{tournament_id}.leaderboard.md` (which is in the same PR) instead of the inline table.

### Folded Todos

(no todos folded — `cross_reference_todos` step returned 0 matches)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project context
- `.planning/PROJECT.md` — milestone scope; Key Decisions table includes "Drop >5% R² win criterion" and "Tournament wins open draft PRs; humans merge"; constraint "No unattended loops that can weaken tests, mock failing pieces, or commit/push without checkpoint review"
- `.planning/REQUIREMENTS.md` — TOURN-05 (top-3 ensemble + bootstrap p<0.05), TOURN-06 (auto-open draft PR; humans merge), TOURN-07 (no parallel metrics — relevant for the no-R²-gate enforcement)
- `.planning/ROADMAP.md` § "Phase 4: Tournament Significance & Auto-PR" — goal, depends-on Phase 3, success criteria (4 items)

### Phase carry-forward
- `.planning/phases/03-tournament-harness-core/03-CONTEXT.md` — Phase 3 D-06 (data source), D-07 (12mo trailing window pinned at start), D-13 (seed/git_sha reproducibility), D-15 (failure semantics — Phase 4 only consumes `status=success` rows for ensemble), D-18 (snapshot artifact contract — the input to Phase 4); CD-05 (leaderboard CLI Phase 4 reuses for queries); CD-07 (status API surface)
- `.planning/phases/03-tournament-harness-core/03-VALIDATION.md` — Phase 3 validation strategy; Phase 4 follows the same Nyquist patterns
- `.planning/phases/02-integration-test-suite-runbook/02-CONTEXT.md` — `bootstrap.sh` is canonical bring-up (Phase 4 must NOT add a new compose path); CI workflow conventions for the test_no_legacy_r2_criterion.py + test_no_auto_merge.py gates

### Existing assets to reuse / extend (load-bearing — do not re-implement)
- `services/tournament-harness/app/leaderboard/snapshot.py:export_snapshot` — Phase 4 reads the JSON files this writes; do NOT modify the writer
- `services/tournament-harness/app/leaderboard/db.py` — `LeaderboardDB.list_runs(tournament_id=...)` for the `tournaments_evaluated_count` query and the temp-DB rebuild in `reproduce`
- `services/tournament-harness/app/leaderboard/queries.py` — `parse_where`, `ALLOWED_FILTER_COLS`, `ALLOWED_ORDER_BY` — Phase 4 ensemble selection MUST go through this safe DSL, not raw SQL
- `services/tournament-harness/app/cli.py` — extend with new `open-pr` and `reproduce` subcommands; reuse `_setup_logging` and the existing argparse pattern (do NOT add a parallel CLI)
- `services/tournament-harness/app/orchestrator/launcher.py` — `run_tournament` and its git-sha capture pattern; `reproduce` reuses the launcher with the snapshot's recovered config
- `services/tournament-harness/app/runner/metrics_bridge.py` — bridge to `returns_metrics`/`sharpe_metrics`/`cpcv` from ml-retraining-service; ensemble metric computation reuses this bridge, NOT a new path
- `services/ml-retraining-service/app/core/returns_metrics.py:compute_returns_metrics` — REQUIRED import for ensemble metrics; do NOT re-implement Sharpe/dir-acc on log-returns
- `services/ml-retraining-service/app/sharpe_metrics.py:probabilistic_sharpe_ratio,deflated_sharpe_ratio` — DSR is the selection metric for top-3 ranking
- `services/ml-retraining-service/app/cpcv.py:cpcv_to_dsr` — used by Phase 3 to populate `cpcv_dsr`; Phase 4 only READS that column from the snapshot; if a tie-break is needed beyond `dsr`, fall back to `cpcv_dsr` (D-01)

### Operator-facing rules (load-bearing)
- `crypto-trading-bot/CLAUDE.md` § "Project rules (load-bearing)" — V0 finding gate (`ENABLE_ML_PREDICTIONS=false` until DSR > 0.95 on returns); Phase 4 winning a PR does NOT auto-flip this flag
- `crypto-trading-bot/CLAUDE.md` § "Verification standards" — no "edge proven" claims on R² alone (drives D-13 grep gate)
- `crypto-trading-bot/CLAUDE.md` § "Commits" — Conventional Commits (`feat(tournament): ...`, `feat(tournament-pr): ...`)

### V0 / safety baseline
- Memory: `project_v0_finding_2026-04-30.md` — why R²-on-price-levels is the underlying bug; persistence baseline matches the same number under the bug → drives D-04 baseline choice
- Memory: `feedback_pf_metric_pooling.md` — pooled-PF rule (sum-of-wins / sum-of-losses, not mean of fold PFs); relevant if a future Phase 5 ensemble metric ever reports profit factor across folds (NOT in Phase 4 scope but flagged for the planner)

### Compose / infra
- `docker-compose.unified.yml` — canonical compose; tournament-harness already runs under `--profile tournament` (Phase 3 D-01); Phase 4 adds NO new service, NO new profile, NO new container — `open-pr` and `reproduce` are CLI-only on the existing tournament-harness image
- `infrastructure/database/` — SQL migration convention; Phase 4 does NOT extend the SQLite leaderboard schema (snapshot is the input contract)

### External tooling
- `gh` CLI (https://cli.github.com/) — `gh pr create --draft --title ... --body ... --label ... --head ... --base main`; `gh pr edit` for re-runs; NEVER `gh pr merge` (CI-enforced via D-13's sibling test, CD-10)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`services/tournament-harness/app/leaderboard/snapshot.py:export_snapshot`** — `open-pr` reads its output JSON; the contract is fixed (rows + config + summary).
- **`services/tournament-harness/app/leaderboard/db.py:LeaderboardDB.list_runs`** — used to count `tournaments_evaluated_count` (CD distinct-tournament_id query) and to materialize the temp DB inside `reproduce`.
- **`services/tournament-harness/app/leaderboard/queries.py:parse_where`** — safe DSL for ensemble selection (`status=success AND symbol={s}` parametric); replaces any temptation to write raw SQL strings.
- **`services/tournament-harness/app/cli.py`** — argparse subcommand pattern + `_setup_logging`; Phase 4 extends with two new subcommands and three new artifact-write paths.
- **`services/tournament-harness/app/runner/metrics_bridge.py`** — single point of contact for the ml-retraining returns/sharpe/cpcv modules; ensemble metric calls go through this bridge, never around it.
- **`services/tournament-harness/app/orchestrator/launcher.py:run_tournament`** — `reproduce` reuses this with a recovered YAML config; the git-sha capture + dirty-tree refusal pattern is reusable as-is.
- **`services/ml-retraining-service/app/core/returns_metrics.py:compute_returns_metrics`** — REQUIRED for ensemble Sharpe + `dir_acc_corrected`; the function signature is `(actual_prices, pred_prices, last_close, dataset_name) -> dict`. Ensemble runner calls it once per symbol per ensemble.

### Established Patterns
- **Service-per-directory under `services/`** — Phase 4 adds NO new service. Module-level extension only inside `services/tournament-harness/app/`.
- **CLI subcommand-per-action** (`tournament run`, `tournament leaderboard list`, `tournament export-snapshot`) — Phase 4 adds `tournament open-pr` and `tournament reproduce` in the same shape.
- **Atomic file writes** (`snapshot.py` uses `tempfile.mkstemp` + `os.replace`) — `ensemble.json`, `significance.json`, `leaderboard.md` ALL use the same atomic pattern.
- **Grep-gate-as-pytest** (`tests/test_no_parallel_metrics.py` from Phase 3 — the TOURN-07 gate for forbidden re-implementations) — Phase 4 D-13 follows the same shape for the R² ban; CD-10 follows it for the `gh pr merge` ban.
- **No raw SQL string concat** (Phase 3 T-03-29) — ensemble selection goes through `parse_where`.
- **Conventional Commits** (`feat(tournament): ...`, `fix(tournament): ...`); Phase 4 plans use the `tournament` scope (or `tournament-pr` if a planner wants to tag the PR-machinery commits separately).

### Integration Points
- **tournament-harness ↔ git** — `git rev-parse HEAD` at `open-pr` time (must equal snapshot's `git_sha`, else refuse); `git status` clean check (`--allow-dirty` opt-in for `open-pr` only — `reproduce` refuses unconditionally). Pattern matches Phase 3 D-13 / Integration Points.
- **tournament-harness ↔ gh CLI** — `subprocess.run(["gh", "pr", "create", "--draft", ...])`; `GH_TOKEN` from env (read but not logged); error parsing of gh stderr for known failure modes (rate limit, auth expired, repo not found). Privilege boundary: `gh` writes to GitHub on the operator's behalf — operator-triggered (D-10) is the safety mechanism.
- **tournament-harness ↔ TimescaleDB** — `reproduce` joins the `crypto-bot` Docker network and connects via the existing `tournament_reader` Postgres role (Phase 3 D-09); `open-pr` does NOT touch TimescaleDB (it operates entirely on snapshot data + the SQLite leaderboard).
- **tournament-harness ↔ SQLite leaderboard** — `open-pr` does a single read query for `tournaments_evaluated_count`; `reproduce` builds a temp DB from the snapshot rows. Original DB untouched.
- **tournament-harness ↔ Phase 5 / Phase 7** — Phase 4 outputs are themselves the input contract for Phase 7 DASH-04 (tournament dashboard view reads `significance.json` for win markers). Phase 5 (MLCL-01 forward-paper-test) consumes nothing from Phase 4 directly but follows the same "evidence then operator" pattern.

### Known landmines (from prior phases)
- **`is_mainnet=true` filter** is mandatory on every `klines` read in `reproduce` — bypassing pollutes results with pre-2026-04-25 testnet data (CLAUDE.md § Gotchas; Phase 3 D-08).
- **PF metric pooling** (memory `feedback_pf_metric_pooling.md`) — if any helper ever computes profit factor across CPCV folds, use `sum(wins)/sum(losses)` pooled, not mean of fold PFs. Not in Phase 4's metric set, but flagged for the planner in case ensemble eval grows.
- **Bind-mount race on WSL2** (CLAUDE.md § Environment) — only relevant if `reproduce` mounts new dirs into the tournament-harness container; reuse Phase 3's bind paths verbatim and the race is already handled by the existing `--force-recreate` runbook entry.

</code_context>

<specifics>
## Specific Ideas

- **The PR is the gate, not the auto-promotion.** A winning tournament opens a draft PR with the receipts; merging it is a separate human decision; flipping `ENABLE_ML_PREDICTIONS=true` after merge is yet another human decision (gated on the V0 DSR>0.95 rule in CLAUDE.md, which Phase 4's bootstrap p<0.05 does NOT satisfy on its own). Three hands on the wheel by design — keeps the tournament from becoming a one-click route to production ML.
- **Reproducibility is load-bearing across phases.** Phase 3 staked everything on (config + git_sha + tournament_start_ts) → identical leaderboard. Phase 4 extends that contract to (snapshot + git_sha + bootstrap_seed) → identical significance. The `reproduce` subcommand (D-12) is the executable proof; `test_reproduce_idempotent.py` should be a CI test that runs `tournament run` → `tournament open-pr --dry-run` → `tournament reproduce` and asserts the second `significance.json` matches the first within FP-noise tolerance.
- **Persistence baseline is the floor, not the ceiling.** Picking persistence-only (D-04) over production-aggregator is a deliberate Phase-4-scope decision: get the bootstrap-on-snapshot pipeline shipped first, then in Phase 5 raise the bar to "beat persistence AND the no-ML aggregator" if the floor gets cleared too easily. The `significance.json` schema (D-14) explicitly carries `baseline: "persistence"` so the field exists for "production_aggregator" or "both" later without a schema rev.
- **Anti-cherry-picking via disclosure** (D-09) is a calculated bet — the operator is a solo founder, the audit reader is the operator, and Bonferroni-as-disclosure is honest enough for that loop. If a third-party reviewer joins, the disclosure becomes the conversation starter rather than a sign-off ritual; if it ever becomes a rubber-stamp, escalate to N-consecutive-winners (deferred).
- **The R² grep gate (D-13) is enforced where the rule lives** — inside `services/tournament-harness/`, not in shared `risk-metrics-service` modules (those still legitimately use R² for non-tournament purposes via `returns_metrics.py` which computes `r2_returns` correctly). The grep is scoped tightly to avoid false positives.
- **`gh pr merge` ban (CD-10) is as load-bearing as the R² ban.** Both are "code can't sneak past human review" rules; both share the same grep-gate-as-pytest shape; both belong to the same nightly CI step. PR description should call this out explicitly so any future contributor sees the rationale before adding "just one auto-merge for the docs PR".

</specifics>

<deferred>
## Deferred Ideas

- **Production-aggregator baseline** (Phase 5 candidate). Hook into the live `CoreAggregator` (or a snapshot of its decisions on the same OOS bars) and run the bootstrap against the harder bar. Adds a runtime dependency on the aggregator's pure-function path. Re-open if persistence-only PRs start firing trivially.
- **DSR-weighted ensemble averaging** (post-Phase 4). If equal-weight (D-02) underperforms a per-cell-DSR weighted variant on shadow-evaluations, swap aggregation methods; `significance.json` already carries `aggregation` as a string field for this.
- **Per-(symbol, architecture) ensembles** — N_symbols × N_architectures ensembles. Useful when an architecture clearly dominates per-symbol; combinatorial cost in Phase 4 is not worth it yet.
- **Single global top-3 across all cells** — could be useful as a "is there any ML signal anywhere" diagnostic; not for production deployment. If wanted, add as a second `tournament open-pr --mode global-top3 {tid}` subcommand later.
- **n_resamples = 100k** (Phase 4 follow-up). Sharper p-values near the 0.05 boundary. Defer until borderline tournaments are a pattern; bumping is a one-line config change.
- **CI workflow `tournament-pr.yml`** that fires `tournament open-pr` on snapshot commit. Decoupled from local dev. Rejected for Phase 4 (operator-in-the-loop is the safety mechanism); revisit when the harness has a year of solo-operator track record.
- **Auto-flipping `ENABLE_ML_PREDICTIONS=true` on PR merge** — explicit non-goal. The V0 finding's DSR>0.95 gate is independent of Phase 4's p<0.05 gate; auto-flipping would conflate them. Operator does the flag flip after merging the PR, after their own judgment.
- **Inline at end of `tournament run`** auto-PR — rejected (D-10) for the same operator-in-the-loop reason. Re-open only if the operator runs many tournaments per day and the manual `open-pr` step becomes friction.
- **Idempotency-on-tournament-id PR refusal** — rejected for Phase 4 (D-09); breaks the reproducer-by-rerun semantics. If `gh pr edit` idempotency on the same branch isn't enough discipline, escalate to a `--force` flag with confirmation prompt, not a refusal.
- **Storing model weights / scalers in the ensemble artifact** (D-03 reject). If a future need arises (e.g., a third-party reviewer wants to load and inspect), add a separate `tournament export-bundle {tid}` subcommand that writes a tarball outside git LFS — don't put weights in `data/snapshots/`.
- **N-consecutive-winning-tournaments anti-cherry-picking** — rejected (D-09); slow + game-able. If the disclosure-only approach proves insufficient, escalate to FDR (Benjamini-Hochberg) across tournaments, not consecutive-streak.
- **Bumping branch / repo / labels into config.json** — rejected (D-11 / CD-02 / CD-03). Conventions are fixed for Phase 4; if a fork ever needs to override, add CLI flags then, don't pre-build the knobs.
- **Refusing if same `tid` was opened before with a different result** — rejected (D-09). Reproducibility means re-runs MUST match; if they don't, the diff is forensic information that belongs in `reproduce`'s output, not a refusal.

### Reviewed Todos (not folded)
None — `cross_reference_todos` step returned 0 matches.

</deferred>

---

*Phase: 04-tournament-significance-auto-pr*
*Context gathered: 2026-05-09*
