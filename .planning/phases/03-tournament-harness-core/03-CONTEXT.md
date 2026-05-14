# Phase 3: Tournament Harness Core - Context

**Gathered:** 2026-05-08
**Status:** Ready for planning

<domain>
## Phase Boundary

A new microservice `services/tournament-harness/` orchestrates a Docker-isolated, Python-driven tournament. The orchestrator launches one container per (architecture × symbol × hyperparameter) experiment over GRU / LSTM / Transformer / TCN × {SOL, BNB, ADA} × HP grid, training each candidate against TimescaleDB mainnet klines and writing one row per run to a SQLite leaderboard. Honest returns metrics come from reusing the existing `returns_metrics.py` / `sharpe_metrics.py` / `cpcv.py` modules — no parallel metrics path. Failed runs persist with a typed failure reason. **No LLM-subagent fanout.** Significance gating + auto-PR is Phase 4 and is out of scope here.

**In scope:**
- New `services/tournament-harness/` (FastAPI + CLI; compose `profile=tournament` so default `bootstrap.sh` skips it)
- Tournament config (YAML) + experiment enumeration over a full Cartesian grid
- Per-experiment Docker container launch via Docker SDK for Python (`docker` package)
- Per-experiment isolation: own container, own mem/cpu caps, own wallclock cap, own random seed derived from a single tournament-level seed
- LSTM, Transformer, TCN model builders alongside the existing GRU builder (extend or factory; see Claude's Discretion CD-01)
- Reuse of `returns_metrics.py` (`r2_returns`, `dir_acc_corrected`), `sharpe_metrics.py` (PSR, DSR), `cpcv.py` (CPCV / `cpcv_to_dsr`) — imported, not re-implemented
- TimescaleDB klines reads with `is_mainnet=true` filter (DATA-01) over a 12-month trailing window pinned at tournament start
- Stationary-only feature set (`STATIONARY_FEATURE_COLS`, 17 cols) as the locked input feature pile
- SQLite leaderboard at `services/tournament-harness/data/leaderboard.db` with numbered SQL migrations under `services/tournament-harness/migrations/`
- Result write path: container writes `/output/result.json` → orchestrator parses → orchestrator inserts SQLite row (single-writer, no per-container DB connection)
- Failed-run persistence with typed `failure_reason` (oom_killed, nan_loss, timeout, exit_nonzero, train_diverged, db_unreachable)
- Committed JSON snapshot artifact (`data/snapshots/{tournament_id}.json`) consumed by Phase 4 (TOURN-05/06) and Phase 7 (DASH-04)

**Out of scope (other phases):**
- Top-3 ensemble construction + bootstrap significance test vs production baseline — Phase 4 (TOURN-05)
- Auto-open draft PR via `gh` — Phase 4 (TOURN-06)
- Forward-paper-test of opt-in features (vol parity, maker, funding) — Phase 5 (MLCL-01)
- T0.1.x next-attempt experiment selection — Phase 5 (MLCL-02), but the harness must be expressive enough for that to slot in
- Frontend tournament leaderboard view — Phase 7 (DASH-04)
- Playwright smoke against tournament-view — Phase 7 (DASH-06)
- XRP / AVAX inclusion — v2 (TOURN-V2-01); harness should not hardcode-exclude them, but tournament configs must opt them in explicitly
- Multi-horizon search (1h/4h/24h) as a production deployment toggle — v2 (TOURN-V2-02); single-horizon-per-cell stays in scope

</domain>

<decisions>
## Implementation Decisions

### Orchestrator runtime + isolation
- **D-01:** Harness home = **new `services/tournament-harness/`** with its own Dockerfile, `app/`, `tests/`, and `migrations/` dirs. Matches the 11-existing-service pattern. Compose entry uses `profile: ["tournament"]` so the default `bootstrap.sh up` does NOT start it; operator opts in with `docker compose -f docker-compose.unified.yml --profile tournament up tournament-harness`. Keeps the deterministic stack lean.
- **D-02:** Experiment launch = **Docker SDK for Python** (`pip install docker`). Orchestrator calls `client.containers.run(image, command=[...], mem_limit=..., cpu_quota=..., detach=True, network=NETWORK_NAME, labels={"tournament_id": ..., "run_id": ...}, volumes={...}, environment={...})`. Reasons: clean async log streaming, label-based listing for "list runs in tournament X", structured exit-code retrieval. CLI-shellout (`subprocess.run(['docker','run',...])`) and `docker compose run` rejected — both make resource caps + label discovery fragile.
- **D-03:** Concurrency = **sequential, one experiment at a time**. Bounded parallelism deferred until proven needed (compose: see CD-04). Reasons: deterministic SQLite-write ordering (orchestrator is single writer), bounded resource footprint on WSL2/laptop hosts (the only host class today; CLAUDE.md flags BTC training OOMing at default container limits), simpler failure attribution.
- **D-04:** Per-experiment resource caps = **driven by tournament config with safe defaults**. Defaults: `mem_limit=4g`, `cpus=2.0`, `wallclock_timeout=1800s` (30 min). Architecture-specific overrides in config (e.g., Transformer cell may set `mem_limit=8g`). Wallclock enforced via orchestrator-side `container.wait(timeout=...)` + `container.kill()` on overrun → `failure_reason=timeout`.
- **D-05:** Per-experiment image = **the `tournament-harness` image itself**, invoked with a `tournament-runner` CMD that takes the experiment spec as a JSON-serialized argument (or env var). Single image keeps build pipeline simple; the orchestrator and the runner are the same container with different entrypoints (mirrors how `model_trainer` lives next to the FastAPI app in `ml-retraining-service`).

### Training data source
- **D-06:** Data source = **TimescaleDB `klines` table with `is_mainnet=true`** (DATA-01 already enforces the column on insert). The harness does NOT use the Phase 1 recorded tape — tape is sized for integration tests (5 symbols × 7 days, ~844K) and is far too small for fitting (sequence_length=60 + horizon=5 leaves ~10K usable sequences per symbol; CPCV needs orders of magnitude more for honest DSR). Live Bybit historical fetch via `data_collector.py` rejected because (a) hits Bybit per-experiment (rate-limited, flaky for 64-grid), (b) Bybit may serve revised candles, breaking determinism.
- **D-07:** Train window = **12 months trailing, pinned at tournament start**. Orchestrator computes `tournament_start_ts = now()` once per tournament, stamps it on every leaderboard row, and every experiment in that tournament reads `klines WHERE timestamp BETWEEN tournament_start_ts - 365d AND tournament_start_ts` (and `is_mainnet=true`). ~105K bars per symbol at 5m. **Hard floor: tournament refuses to start if any (symbol, interval) pair has fewer than 50K rows in window.** Refresh policy = a tournament's data is implicitly refreshed by its `tournament_start_ts`; reproducibility means re-running same config + same `tournament_start_ts` (recorded on every row) and same `git_sha`.
- **D-08:** Pre-2026-04-25 contamination guard — even with `is_mainnet=true`, rows from before the testnet-flip bug fix (2026-04-25) are mixed-history per CLAUDE.md § Gotchas. The 12-month window will include them. **Orchestrator emits a warning (and stamps `train_window_includes_contaminated=true` on every leaderboard row in that tournament) when `tournament_start_ts - 365d < 2026-04-25`.** Eventually (post 2027-04-25) this guard is dead-weight; left in for now.
- **D-09:** DB access from experiment containers = **container joins `crypto-bot` Docker network and connects to `timescaledb:5432`**. New read-only Postgres role `tournament_reader` with `SELECT` on `klines` only; password injected as env var by orchestrator. No host-port exposure. Bind-mount-parquet path rejected (extra serialization step, less flexible for ad-hoc per-symbol slicing).
- **D-10:** Feature set = **stationary-only (`STATIONARY_FEATURE_COLS`, 17 features)** locked across all tournament experiments. Reason: V0 finding pinned R²-on-price-levels as the underlying bug; stationary-only is the post-fix set already used by the T0.1 rebuild path. Feature set is **not** in the HP grid for v1; ablation between legacy and stationary is deferred (see `<deferred>`).

### Search-space config + sweep method
- **D-11:** Config format = **YAML** (`tournament.yaml`). Top-level keys: `tournament_id`, `seed`, `symbols`, `intervals`, `architectures` (each with its own HP grid), `default_resource_caps`, `target_modes`. PyYAML is already a TF transitive dep — no new packages. JSON, TOML, and Python-module configs rejected (no comments, low ergonomics, or arbitrary-code risk respectively).
- **D-12:** Sweep method = **full Cartesian grid**. Operator declares the grid; harness enumerates every cell and assigns each a deterministic `run_id` (`hp_hash`). Random sampling and Bayesian (Optuna) rejected for v1 — reproducibility is load-bearing, and Bayesian's sequential dependence breaks "re-run is the same tournament". Operator controls grid size by trimming the YAML.
- **D-13:** Reproducibility — **single tournament-level `seed: 42` in YAML; each experiment seed = `hash(seed, run_id) mod 2**32`**. `git_sha = git rev-parse HEAD` captured once at tournament start, stamped on every row in that tournament. Same config + same commit + same `tournament_start_ts` (recorded on every row) ⇒ identical leaderboard. NumPy + TF + Python `random` all seeded from the per-run derived value inside the runner entrypoint.
- **D-14:** HP dimensions in the grid (per REQUIREMENTS.md TOURN-03) = **`units` (per layer), `depth`, `dropout`, `lr`, `batch`, `lookback`, `horizon`, `target_mode`**. `target_mode ∈ {price, log_returns}` exposed so the harness can ablate (V0 finding makes log_returns the expected winner). `feature_set` is **not** in the grid (locked stationary per D-10). Architecture-specific HP nests (`n_heads`, `kernel_size`, `dilation_base` for Transformer / TCN) live under each architecture's section in `tournament.yaml`.

### Failure semantics + leaderboard write path
- **D-15:** "Failed run" = **any non-success exit**. Typed `failure_reason ∈ {oom_killed, nan_loss, timeout, exit_nonzero, train_diverged, db_unreachable, unknown}`. Classification rules (orchestrator side):
  - `oom_killed`: container exits with code 137 OR `inspect.State.OOMKilled = True`
  - `timeout`: orchestrator's `container.wait(timeout=cap)` fires; orchestrator `kill`s
  - `nan_loss`: container writes `result.json` with `status=failed, reason=nan_loss` (runner sets this if it sees NaN in `loss` history)
  - `train_diverged`: runner sets when EarlyStopping never reduced from initial val_loss (no improvement for full epoch budget)
  - `db_unreachable`: runner can't connect to TimescaleDB; emits status JSON, exits 0 (so orchestrator can still log it as a controlled failure)
  - `exit_nonzero`: container exits non-zero AND no `result.json` was written
  - `unknown`: anything else (defensive). Stderr tail (last 4KB) persisted to leaderboard `failure_stderr_tail` column.
  Successful runs ALWAYS get a row; failed runs ALSO get a row. Every row carries the full PK `(architecture, symbol, horizon, target_mode, hp_hash, run_id)` so the failed-cell isn't silently retried as "missing".
- **D-16:** Result delivery = **container writes `/output/result.json`; orchestrator ingests after container exit**. Bind mount = `services/tournament-harness/data/results/{tournament_id}/{run_id}/` → `/output` (rw). After `container.wait()` returns, orchestrator parses `result.json` and inserts the leaderboard row. SQLite is single-writer (orchestrator process). No DB credential leaks into experiment containers, no SQLite WAL/bind-mount race hazards. Direct-DB-write and HTTP-callback paths rejected (concurrency / extra moving parts).
- **D-17:** Schema migrations = **hand-written numbered SQL files under `services/tournament-harness/migrations/0001_initial.sql`, applied in order at orchestrator startup**. Idempotent (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE … ADD COLUMN`). A `schema_version` table tracks applied migrations. No Alembic — Alembic on SQLite is constrained (no `ALTER COLUMN`), and SQLite is single-process here. Pattern matches existing `infrastructure/database/` SQL-migration convention used by Postgres.
- **D-18:** Leaderboard storage = **`services/tournament-harness/data/leaderboard.db` is gitignored** (binary churn unsuitable for git). The committed artifact is the JSON snapshot at `services/tournament-harness/data/snapshots/{tournament_id}.json` written by `tournament export-snapshot {tournament_id}`. The snapshot JSON is what Phase 4 reads for significance tests and Phase 7 reads for the dashboard tournament view (DASH-04). Operator workflow per tournament: run → export-snapshot → review → commit snapshot. DB is rebuildable from snapshots if it ever gets corrupted/deleted.

### Claude's Discretion

These were not selected for deep-dive but downstream agents should treat the stances as defaults; surface in RESEARCH.md / PLAN.md and operator can override before execution.

- **CD-01 (Architecture coverage strategy):** Refactor `services/ml-retraining-service/app/core/model_trainer.py` to a **`models/` registry pattern** (one module per architecture: `gru.py`, `lstm.py`, `transformer.py`, `tcn.py`, each exposing a `build(input_shape, hp) -> keras.Model` callable) and have `tournament-harness/` import this registry — keep the trainer in ml-retraining-service so the same builders power both retraining and tournament. The existing `build_gru_model` becomes `models/gru.py:build`. **Default scope:** four small builders (≤80 LOC each) using Keras layers; no custom CUDA, no PyTorch. Transformer = stacked `MultiHeadAttention` + FFN + Pos encoding; TCN = stacked dilated `Conv1D` with residual.
- **CD-02 (Per-run wallclock cap default):** **30 min**. 12mo of 5m bars × `epochs≤30` × Transformer batch_size≥64 fits comfortably in 30 min on a 2-CPU/4GB-RAM container; runaway training (loss not reducing) hits early-stopping well before. Per-architecture override available in YAML (e.g., Transformer cells with deeper depth may request `wallclock_timeout=3600`).
- **CD-03 (Container log capture):** Orchestrator captures `container.logs(stdout=True, stderr=True)` after `wait()` and writes to `data/results/{tournament_id}/{run_id}/stdout.log` (and `.stderr.log`). Keeps logs out of the leaderboard row (only the last 4KB of stderr is stamped on failure rows). Files gitignored; tournament snapshot includes only the leaderboard rows + tournament config, not logs.
- **CD-04 (Future bounded-parallelism path):** When v1 sequential becomes a wallclock blocker, the move is `concurrent.futures.ThreadPoolExecutor(max_workers=N)` around `container.run()` with the orchestrator still owning SQLite writes (results queued back from threads). No code change needed in the runner; only the orchestrator scheduler. Captured here so a Phase-4 or Phase-5 follow-up can flip it without rearchitecting.
- **CD-05 (Leaderboard query surface):** v1 = a small CLI on the orchestrator container: `tournament leaderboard list --tournament-id ... --top 3 --by dsr --where "symbol=SOL AND architecture=GRU"`. Implementation = parameterized SQL builder over a tiny query DSL (no ORM, no ad-hoc string concat — SQL injection guard). Phase 7 (DASH-04) consumes the JSON snapshot, not the CLI; CLI is the operator surface only.
- **CD-06 (CPCV wiring):** Tournament reuses `services/ml-retraining-service/app/core/cpcv_evaluation.py:evaluate_with_cpcv` as-is. CPCV fold count + purge bars defaulted from existing `retrain_*` settings (8 folds, `purge_bars = lookback`); not exposed in tournament YAML for v1 to keep the grid bounded. Operator can change them via env var override on the runner container if a future tournament needs to.
- **CD-07 (Status / progress API):** `services/tournament-harness/app/main.py` exposes `GET /api/v1/tournaments`, `GET /api/v1/tournaments/{tid}`, `GET /api/v1/tournaments/{tid}/runs` for read-only inspection (used by the operator and Phase 7 frontend). No mutation endpoints — start-tournament is CLI only (`tournament run config.yaml`) so the operator commits the YAML before launching.

### Folded Todos

(no todos folded — `cross_reference_todos` step returned 0 matches at init)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project context
- `.planning/PROJECT.md` — milestone scope, validated capability, V0 finding (load-bearing), key decision "Tournament uses Docker+Python orchestrator, not LLM subagents", "Drop >5% R² win criterion"
- `.planning/REQUIREMENTS.md` — TOURN-01, TOURN-02, TOURN-03, TOURN-04, TOURN-07 acceptance criteria for Phase 3 (TOURN-05/06 are Phase 4)
- `.planning/ROADMAP.md` § "Phase 3: Tournament Harness Core" — goal, depends-on, success criteria

### Phase carry-forward
- `.planning/phases/01-bootstrap-recorded-tape/01-CONTEXT.md` — tape format, MARKET_DATA_SOURCE selector; relevant only as proof that tape is the wrong data source for tournament training (D-06)
- `.planning/phases/02-integration-test-suite-runbook/02-CONTEXT.md` — `bootstrap.sh` is canonical bring-up; tournament must NOT add a new compose path that bypasses it (uses `--profile tournament`); CD-04 of Phase 2 supplies the `force-signal` admin pattern that Phase 3's tournament status API mirrors

### Existing assets to reuse / extend (load-bearing — do not re-implement)
- `services/ml-retraining-service/app/core/returns_metrics.py` — `compute_returns_metrics(model, X, y, last_close, dataset_name)` returns `{r2_returns, dir_acc_corrected}`. Tournament runner imports this verbatim (TOURN-07).
- `services/ml-retraining-service/app/sharpe_metrics.py` — `probabilistic_sharpe_ratio`, `expected_max_sharpe_under_null`, `deflated_sharpe_ratio`. Tournament runner emits `psr` + `dsr` from these.
- `services/ml-retraining-service/app/cpcv.py` — `CombinatorialPurgedCV`, `cpcv_sharpe_distribution`, `cpcv_to_dsr`. Tournament runner emits `cpcv_dsr`.
- `services/ml-retraining-service/app/core/cpcv_evaluation.py` — `evaluate_with_cpcv` is the existing harness; tournament reuses pattern (CD-06).
- `services/ml-retraining-service/app/core/model_trainer.py` — existing `build_gru_model`. Refactor to registry per CD-01; the GRU builder is the seed.
- `services/ml-retraining-service/app/core/data_collector.py` — Bybit historical fetch reference (NOT used at run-time per D-06 — kept as the "if we ever need to backfill TimescaleDB" path).
- `services/ml-retraining-service/app/core/stationary_features.py` — `STATIONARY_FEATURE_COLS` (17 features) + `compute_stationary_features(df)`. Locked input feature pile per D-10.
- `services/ml-retraining-service/app/database/models.py` — schema reference for `ModelVersion`, `RetrainingJob`. Tournament leaderboard schema borrows the ID + git_sha + timestamp conventions but lives in its own SQLite DB (D-18).

### Operator-facing rules (load-bearing)
- `crypto-trading-bot/CLAUDE.md` § "Project rules (load-bearing)" — V0 finding gate (`ENABLE_ML_PREDICTIONS=false` until DSR > 0.95 on returns), validated symbol set (SOL/BNB/ADA only), feature flag defaults
- `crypto-trading-bot/CLAUDE.md` § "Verification standards" — no "edge proven" claims on R² alone; honest metrics only
- `crypto-trading-bot/CLAUDE.md` § "Environment" — WSL2 + Docker context default (not desktop-linux), BuildKit hangs (`DOCKER_BUILDKIT=0` workaround), bind-mount race recovery, **ML training memory** (BTC training OOM at default container limits — drives D-04)
- `crypto-trading-bot/CLAUDE.md` § "Gotchas" — `docker-compose.unified.yml` canonical; **TimescaleDB has mixed testnet/mainnet history pre-2026-04-25** even with `is_mainnet=true` filter (drives D-08 contamination guard)

### V0 / safety baseline
- Memory: `project_v0_finding_2026-04-30.md` — why R² on price levels is the bug; `r2_returns` + DSR is the replacement
- Memory: `feedback_pf_metric_pooling.md` — pooled-PF rule; relevant if any tournament metric ever reports profit factor across CPCV folds (use sum-of-wins / sum-of-losses, not mean of fold PFs)

### Compose / infra
- `docker-compose.unified.yml` — canonical compose; tournament-harness service added under `profile: ["tournament"]` so default `bootstrap.sh up` does not start it
- `infrastructure/database/` — existing SQL-migration convention; `services/tournament-harness/migrations/` follows the same numbered-SQL pattern (D-17)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`returns_metrics.py:compute_returns_metrics`** — drop-in import for the runner; takes `(model, X, y, last_close, dataset_name)` and returns the honest `r2_returns` + `dir_acc_corrected` dict.
- **`sharpe_metrics.py:probabilistic_sharpe_ratio` / `deflated_sharpe_ratio`** — drop-in for the per-run PSR/DSR columns. PSR docstring confirms bar-frequency input.
- **`cpcv.py:cpcv_to_dsr`** — already wraps `deflated_sharpe_ratio` with the CPCV path-count adjustment; runner calls this once it has per-path returns.
- **`cpcv_evaluation.py:evaluate_with_cpcv`** — full CPCV harness (already used by ml-retraining); tournament's runner reuses this rather than re-implementing the fold loop.
- **`stationary_features.py:STATIONARY_FEATURE_COLS` + `compute_stationary_features`** — 17-column stationary feature pile; runner's input pipeline is `df → compute_stationary_features → MinMaxScaler.fit_transform`.
- **`model_trainer.py:build_gru_model`** (current state) — single function. CD-01 refactors to `models/gru.py:build` and adds `models/{lstm,transformer,tcn}.py`. The `create_sequences` + train/test split scaffolding stays (extract into a shared `runner.py` or import from ml-retraining).
- **`data_collector.py:_fetch_klines`** — Bybit REST fetch shape; NOT in the runner hot path, but referenced for any future "backfill TimescaleDB" tooling.

### Established Patterns
- **Service-per-directory under `services/`** with `Dockerfile`, `app/`, `requirements.txt`, `tests/` — `tournament-harness/` follows.
- **FastAPI + uvicorn** for HTTP; **APScheduler** for cron (not used by tournament — start is operator-driven).
- **`config/settings.py` Pydantic Settings** — tournament config (resource caps, default DB paths) reuses pattern; `tournament.yaml` is operator-supplied per-run, NOT in `Settings`.
- **`database/models.py` SQLAlchemy** for Postgres; **NOT used here** — leaderboard is SQLite + raw SQL via stdlib `sqlite3`. Pattern reused only for type/timestamp conventions.
- **Conventional Commits** (`feat(tournament): ...`, `fix(tournament): ...`).
- **`tests/integration/conftest.py` fixtures** (Phase 2) — tournament harness's own integration tests can reuse `bootstrap_stack` if they want a real TimescaleDB; unit tests should mock the DB layer.

### Integration Points
- **tournament-harness ↔ TimescaleDB** — read-only via new `tournament_reader` Postgres role; SELECT on `klines`. Connection from inside experiment container via `crypto-bot` Docker network. (D-09)
- **tournament-harness ↔ Docker socket** — orchestrator mounts `/var/run/docker.sock` (read+write) to spawn experiment containers. **Privilege boundary**: this is effectively root on the host. Mitigation: tournament-harness service is `--profile tournament` only (default off), and the runner CMD is the same image (no custom user-supplied images). Document in plan-phase risk section.
- **tournament-harness ↔ ml-retraining-service** — imports the registry refactor (CD-01) for builders; imports `returns_metrics`, `sharpe_metrics`, `cpcv` modules. Add the ml-retraining `app/` to `PYTHONPATH` in tournament Dockerfile, OR copy the relevant modules during build (preferred to keep service boundaries clean — but introduces drift risk; alternative is a shared `libs/` package consumed by both. Default stance for plan-phase: shared `libs/`).
- **tournament-harness ↔ SQLite leaderboard** — single writer (orchestrator process), readers are ad-hoc (CLI, future Phase 7 dashboard).
- **tournament-harness ↔ git** — `git rev-parse HEAD` at tournament start (D-13); `git status` check at start to refuse running on a dirty tree (avoids "what was the code at run-time" ambiguity). Override: `--allow-dirty` flag for development.
- **tournament-harness ↔ Phase 4 / Phase 7** — output contract is the JSON snapshot file at `services/tournament-harness/data/snapshots/{tournament_id}.json`. Both downstream phases consume this; nothing else.

</code_context>

<specifics>
## Specific Ideas

- **"No LLM-subagent fanout" is structural, not stylistic.** PROJECT.md and ROADMAP.md both pin Docker+Python as the right primitive specifically because Agent-tool spawns share parent shell — there's no per-experiment memory isolation, no resource caps, no reproducible exit-code mapping. The tournament harness is the answer to "what if 30 LLM subagents fanned out instead?" — and the answer is "no, this is what isolation actually looks like."
- **Reproducibility is load-bearing.** A tournament with the same `tournament.yaml` + same `git_sha` + same `tournament_start_ts` re-run anywhere must produce the same leaderboard (within FP-noise tolerance after seed-fixing). This is why: (a) full Cartesian grid (not random/Bayesian — D-12), (b) tournament-level seed → hash(seed, run_id) (D-13), (c) `tournament_start_ts` stamped on every row (D-07), (d) git_sha stamped on every row (D-13), (e) git-clean check at start with `--allow-dirty` opt-in (Integration Points).
- **TOURN-07 is a grep gate, not a code-review note.** The success criterion literally is `grep -r "def directional_accuracy\|def sharpe\|def deflated" services/tournament-harness/` returns nothing. Plan-phase needs to add this grep as a CI guard.
- **Per-trade risk caps are NOT in scope here.** Tournament is offline ML evaluation; the 2%-LIVE / 10%-paper risk caps live in trading-engine and are unaffected by this phase. Leaderboard rows include a `paper_sim_max_dd` column derived from CPCV-fold returns, but that's an evaluation artifact, not a runtime cap.
- **Why SQLite over Postgres for leaderboard.** Tournament is a one-shot eval batch with one writer; the bot stack's Postgres is for live state (positions, orders). Mixing offline-eval rows into the live DB couples two failure domains and complicates backups. SQLite-with-snapshot-JSON is the "small, file, embedded, queryable" sweet spot.

</specifics>

<deferred>
## Deferred Ideas

- **Bounded parallelism (`max_workers=N` thread pool)** — design path captured in CD-04; defer until v1 sequential proves a wallclock blocker. Re-open if a tournament regularly exceeds operator's patience window (~24h on the host).
- **`feature_set` ablation in HP grid (legacy vs stationary)** — locked stationary in v1 per D-10. If a Phase 5 T0.1.x experiment wants to ablate feature sets, add `feature_set` to the grid and bump `hp_hash` schema version.
- **Optuna / Bayesian sweep** — rejected for v1 reproducibility; revisit if the grid blows past operator's compute budget AND v1 results show a clear "promising region" worth refining.
- **Per-architecture train_window override** — D-07 locks 12mo for everything in v1. If a Phase 5 result shows Transformer wants 24mo while GRU wants 6mo, the schema and config grow a `train_window_days` HP cell.
- **GPU support** — defer until v1 CPU runs prove unworkable. Keras + TF code path is GPU-ready; orchestrator just needs to thread `runtime="nvidia"` + `device_requests=[...]` through the Docker SDK call. Not in scope; not blocked.
- **Multi-horizon production deployment from one tournament** — explicitly v2 (TOURN-V2-02). Tournament evaluates per-horizon honestly; *which* horizon ships to production is a Phase 4 / 5 decision, not Phase 3.
- **XRP / AVAX inclusion** — v2 (TOURN-V2-01). Harness must NOT hardcode-exclude them; tournament configs must opt them in explicitly via the symbols list. Validation gate (`PROJECT.md` validated-symbols rule) prevents production deployment without separate review.
- **Live-vs-backtest signal divergence audit (MLCL-04)** — Phase 5. Out of scope here, but the tournament's per-cell results feed the divergence question (tournament's metrics vs whatever the live signal computes).
- **Custom CUDA / PyTorch builders** — out of scope; locked to Keras for v1 to keep the registry small.
- **Tournament-of-tournaments (cross-tournament aggregation, CI auto-trigger)** — not raised; v1 is operator-launched per-tournament.
- **TOURN-04 Clause 1 (per-epoch early stopping on `r2_returns` / `dir_acc_corrected`)** — deferred for v1. When target_mode=log_returns + loss=MSE, `val_loss` is monotonic with `r2_returns` (R² is a constant-shift transform of negative MSE on a fixed validation set), so `EarlyStopping(monitor=val_loss, mode=min, patience=10)` is mathematically equivalent to monitoring `val_r2_returns`. For target_mode=price (V0-finding mode, expected to lose), val_loss is a less faithful proxy — but that mode is exposed in the HP grid only as an ablation target, not for production. Adding a custom Keras metric that recomputes `dir_acc_corrected` per epoch requires recovering the prev_close vector from validation batches inside the metric, which is non-trivial and adds runtime cost; defer until v1 results show early-stopping precision is a tournament bottleneck (e.g., a clear "stopped too early on a winner" pattern across runs). Plans 03-03/06/07/09 implement TOURN-04 Clause 2 only (failed runs persist to leaderboard); Clause 1 closure tracked here.

### Reviewed Todos (not folded)
None — `cross_reference_todos` step returned 0 matches.

</deferred>

---

*Phase: 03-tournament-harness-core*
*Context gathered: 2026-05-08*
