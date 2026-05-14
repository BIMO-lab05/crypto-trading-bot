# Phase 3: Tournament Harness Core - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in 03-CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-08
**Phase:** 03-tournament-harness-core
**Areas discussed:** Orchestrator runtime + isolation, Training data source, Search-space config + sweep method, Failure semantics + write path

---

## Orchestrator runtime + isolation

### Q1: Where should the tournament harness live in the repo?

| Option | Description | Selected |
|--------|-------------|----------|
| New services/tournament-harness/ | FastAPI/CLI service, own Dockerfile + tests dir. Matches the 11 existing services pattern; gets its own image, env, and (optional) `/api/v1/tournament` endpoints. Compose entry off by default (profile=tournament). | ✓ |
| Top-level scripts/tournament/ Python package | Lives outside services/. CLI-only entrypoint. Lighter — no compose service, no FastAPI. | |
| Extend ml-retraining-service | Add tournament endpoints + worker into the existing service. Reuses its DB session, model storage volumes, and TF env. Risk: couples retrain scheduler to tournament workload. | |

**User's choice:** New services/tournament-harness/
**Notes:** Aligns with the existing service-per-directory convention; keeps default `bootstrap.sh` lean via compose `--profile tournament`.

---

### Q2: How should the harness launch each experiment container?

| Option | Description | Selected |
|--------|-------------|----------|
| docker run via Docker SDK for Python | Orchestrator imports `docker` library, calls `client.containers.run(...)`. Clean isolation, label-based listing, structured exit codes. | ✓ |
| subprocess.run(['docker', 'run', ...]) | Shell out to docker CLI per experiment. Simpler dep surface but parsing/log handling fragile. | |
| docker-compose run --rm tournament-runner | Use compose service per experiment. Couples tournament to compose lifecycle; harder to cap resources per-run. | |

**User's choice:** docker run via Docker SDK for Python

---

### Q3: What concurrency model should the orchestrator use for running experiments?

| Option | Description | Selected |
|--------|-------------|----------|
| Sequential, one experiment at a time | Simplest correctness story, bounded resource footprint, deterministic SQLite-write ordering. | ✓ |
| Bounded parallelism (configurable, default N=2) | Run N containers concurrently with semaphore. Cuts wallclock; orchestrator owns SQLite writes. | |
| Unbounded — spawn everything, OS decides | Maximum throughput; unsafe on WSL2/laptop hosts. | |

**User's choice:** Sequential, one experiment at a time
**Notes:** Future bounded-parallelism path captured in CD-04 of CONTEXT.md (defer until v1 sequential proves a wallclock blocker).

---

### Q4: What per-experiment resource caps should the orchestrator enforce on each container?

| Option | Description | Selected |
|--------|-------------|----------|
| Caps from tournament config, with safe defaults | `mem_limit=4g`, `cpus=2.0`, `wallclock_timeout=1800s` defaults; architecture-overridable. Avoids past BTC OOM pattern. | ✓ |
| Inherit host defaults, no caps | No `--memory/--cpus`. Risk: runaway TF process OOM-kills siblings. | |
| Hard-coded conservative caps | All experiments get same caps regardless of architecture. Predictable but Transformer/24h experiments may fail under-provisioned. | |

**User's choice:** Caps from tournament config, with safe defaults

---

## Training data source

### Q1: Where do experiments get their OHLCV training data from?

| Option | Description | Selected |
|--------|-------------|----------|
| TimescaleDB klines table, is_mainnet=true | Read directly from running TimescaleDB; `WHERE is_mainnet=true` (DATA-01). Reproducible if `tournament_start_ts` is pinned. | ✓ |
| Live Bybit historical fetch via data_collector.py | Each experiment hits Bybit mainnet REST. Risk: rate-limited, flaky for 64-grid; Bybit may serve revised candles. | |
| Pre-captured static parquet/CSV dump in repo | Single big dump committed at tournament setup. Fully deterministic, but adds 50-200MB git-lfs cost. | |
| Per-symbol training fixture sized for tournament | Like Phase 1 tape but bigger (~6mo × 5min). Forward-compatible with `tape_version` header. | |

**User's choice:** TimescaleDB klines table, is_mainnet=true

---

### Q2: What window of historical klines should each experiment train on?

| Option | Description | Selected |
|--------|-------------|----------|
| 12 months ending at tournament start | ~105K bars at 5m. Window pinned by `tournament_start_ts` for reproducibility. | ✓ |
| Full history available in TimescaleDB | Risk: pre-2026-04-25 testnet contamination still mixed into older candles. | |
| Per-architecture window (config-driven) | More flexibility; more knobs to tune. | |
| 6 months | Faster runs but ~52K bars marginal for Transformer + CPCV folds with purge windows. | |

**User's choice:** 12 months ending at tournament start
**Notes:** D-08 of CONTEXT.md adds a contamination guard that warns + stamps `train_window_includes_contaminated=true` when the 12mo window starts before 2026-04-25.

---

### Q3: How does the experiment container access TimescaleDB?

| Option | Description | Selected |
|--------|-------------|----------|
| Container joins crypto-bot network, reads via service hostname | `docker run --network crypto-bot_default`; container connects to `timescaledb:5432`. New read-only `tournament_reader` Postgres role. | ✓ |
| Orchestrator pre-extracts data and bind-mounts a parquet file per experiment | Slower setup but bulletproof reproducibility (airgapped from running stack). | |
| Orchestrator passes data via stdin/HTTP to each container | Orchestrator HTTP server; container fetches its slice. More moving parts. | |

**User's choice:** Container joins crypto-bot network, reads via service hostname

---

### Q4: What feature set should the tournament use for input features?

| Option | Description | Selected |
|--------|-------------|----------|
| Stationary-only (T0.1 set, 17 features) | `STATIONARY_FEATURE_COLS`. Aligned with V0 finding (excludes raw price levels). | ✓ |
| Legacy 22-indicator pile | Risk: includes price-level features that drove the look-ahead-leakage failure. | |
| Per-experiment via tournament config | Lets harness ablate stationary-vs-legacy as part of search. More search space. | |

**User's choice:** Stationary-only (T0.1 set, 17 features)
**Notes:** `feature_set` deferred from HP grid in v1 (locked stationary). If a Phase 5 T0.1.x experiment wants to ablate feature sets, add to grid and bump `hp_hash` schema version.

---

## Search-space config + sweep method

### Q1: What format should the tournament config file use?

| Option | Description | Selected |
|--------|-------------|----------|
| YAML | `tournament.yaml` with nested sections. PyYAML already in TF transitive deps. | ✓ |
| JSON | No comments; harder for operator to author by hand. | |
| TOML | Less common in this repo (no .toml configs currently). | |
| Python module (tournament_config.py) | Maximum flexibility; arbitrary code execution risk if checked into PRs. | |

**User's choice:** YAML

---

### Q2: What sweep method should the harness use to enumerate experiments from the config?

| Option | Description | Selected |
|--------|-------------|----------|
| Full Cartesian grid | Operator lists architectures, symbols, HP values; harness enumerates cross-product. Reproducible, no extra deps. | ✓ |
| Random N samples from grid | Operator declares grid + sample count; harness picks N points with deterministic seed. | |
| Bayesian (Optuna) | Sequential search; sample-efficient but breaks "re-run is the same tournament" reproducibility. | |

**User's choice:** Full Cartesian grid
**Notes:** Operator controls grid size by trimming the YAML.

---

### Q3: How should seed and git_sha get pinned per experiment for reproducibility?

| Option | Description | Selected |
|--------|-------------|----------|
| Single tournament-level seed; per-run seed = hash(seed, run_id) | Operator sets one `seed: 42`; orchestrator derives each experiment's seed deterministically. git_sha captured once at tournament start. | ✓ |
| Per-experiment seed in config | More verbose; same reproducibility. Useful for two-seed comparisons. | |
| Random seeds, recorded after the fact | Trade reproducibility for noise sampling. Rejected for safety-aware project. | |

**User's choice:** Single tournament-level seed; per-run seed = hash(seed, run_id)

---

### Q4: What HP dimensions should be pinned in the tournament search-space (vs hardcoded)?

| Option | Description | Selected |
|--------|-------------|----------|
| units (per layer), depth, dropout, lr, batch, lookback, horizon, target_mode | Matches REQUIREMENTS.md TOURN-03 spec exactly. Architecture-specific knobs nest per architecture. | ✓ |
| Minimal: only architecture, symbol, lr, lookback | Smaller grid; can't claim 'searched HP space honestly' if depth/dropout/units frozen. | |
| Everything Keras/optimizer | Combinatorial blowup; most cells noise. | |

**User's choice:** units (per layer), depth, dropout, lr, batch, lookback, horizon, target_mode
**Notes:** `feature_set` not in grid (locked stationary, D-10).

---

## Failure semantics + write path

### Q1: What counts as a 'failed run' that still gets a leaderboard row with a reason?

| Option | Description | Selected |
|--------|-------------|----------|
| All non-success exits (OOM/NaN/timeout/crash) | Typed `failure_reason ∈ {oom_killed, nan_loss, timeout, exit_nonzero, train_diverged, db_unreachable}`. | ✓ |
| Only crashes/OOM; treat NaN-loss + early-stop as success | NaN rows would pollute leaderboard sort. | |
| Only OOM and timeout count as failures | Hides systematic issues; conflicts with SC-3. | |

**User's choice:** All non-success exits (OOM/NaN/timeout/crash)
**Notes:** Stderr tail (last 4KB) persisted to `failure_stderr_tail` column. Classification rules detailed in D-15 of CONTEXT.md.

---

### Q2: How does the experiment container deliver its result to the leaderboard?

| Option | Description | Selected |
|--------|-------------|----------|
| Container writes JSON to bind-mounted output dir; orchestrator ingests after container exit | Single-writer SQLite. No DB credential leaks into experiment containers. | ✓ |
| Container writes directly to SQLite via bind-mounted DB file | Bind-mount WAL/FS-flush hazards on Docker (especially WSL2 bind-mount race). | |
| Container POSTs result to orchestrator HTTP endpoint | Robust to mid-run kill; more moving parts (network/auth). | |

**User's choice:** Container writes JSON to bind-mounted output dir; orchestrator ingests after container exit

---

### Q3: What schema-evolution strategy should the SQLite leaderboard use?

| Option | Description | Selected |
|--------|-------------|----------|
| Hand-written numbered SQL migrations in services/tournament-harness/migrations/ | `0001_initial.sql` etc., applied at orchestrator startup. Matches `infrastructure/database/` pattern. | ✓ |
| Alembic | Same framework ml-retraining uses for Postgres. SQLite-on-Alembic constrained (no `ALTER COLUMN`). | |
| Drop-and-rebuild on schema change | Conflicts with TOURN-02 cross-tournament queries. | |

**User's choice:** Hand-written numbered SQL migrations in services/tournament-harness/migrations/

---

### Q4: Where should the SQLite leaderboard DB file live, and how is it persisted?

| Option | Description | Selected |
|--------|-------------|----------|
| services/tournament-harness/data/leaderboard.db (gitignored), backed up via committed JSON snapshots | Snapshot JSON is the artifact consumed by Phase 4 (significance/PR) and Phase 7 (DASH-04). | ✓ |
| Commit the SQLite DB to git | Binary file, every run mutates it, merge conflicts, repo bloat. | |
| Postgres table in the existing app DB | Couples one-shot eval tool to the running app stack. | |

**User's choice:** services/tournament-harness/data/leaderboard.db (gitignored), backed up via committed JSON snapshots

---

## Claude's Discretion

The user did NOT select these areas for deep-dive in `present_gray_areas`. Claude captured defaults in CONTEXT.md `<decisions>` § "Claude's Discretion" (CD-01 through CD-07). Operator may override before plan-phase execution:

- **CD-01: Architecture coverage strategy** — Refactor `model_trainer.py:build_gru_model` to a `models/` registry pattern; one module per architecture (`gru.py`, `lstm.py`, `transformer.py`, `tcn.py`) each exposing `build(input_shape, hp) -> keras.Model`. Keep registry in ml-retraining-service so the same builders power both retraining and tournament.
- **CD-02: Per-run wallclock cap default** — 30 min. Architecture-specific YAML overrides allowed.
- **CD-03: Container log capture** — Orchestrator writes `stdout.log` / `stderr.log` per run under `data/results/{tournament_id}/{run_id}/`. Last 4KB of stderr stamped on failure rows; full logs gitignored.
- **CD-04: Future bounded-parallelism path** — `concurrent.futures.ThreadPoolExecutor(max_workers=N)` around `container.run()` with orchestrator-side SQLite writes. Captured here; not enabled in v1.
- **CD-05: Leaderboard query surface** — CLI on the orchestrator container: `tournament leaderboard list --top N --by dsr --where "..."`. Phase 7 dashboard consumes JSON snapshot, not CLI.
- **CD-06: CPCV wiring** — Reuse `cpcv_evaluation.evaluate_with_cpcv` as-is. Defaults: 8 folds, `purge_bars = lookback`. Not in tournament YAML grid for v1.
- **CD-07: Status / progress API** — Read-only endpoints (`GET /api/v1/tournaments`, `.../{tid}`, `.../{tid}/runs`). No mutation endpoints; tournament start is CLI only.

---

## Deferred Ideas

(Captured in CONTEXT.md `<deferred>` — repeated here for audit completeness.)

- Bounded parallelism (`max_workers=N` thread pool) — design path in CD-04; defer until sequential proves wallclock blocker.
- `feature_set` ablation in HP grid (legacy vs stationary) — locked stationary in v1.
- Optuna / Bayesian sweep — rejected for v1 reproducibility.
- Per-architecture train_window override — locked at 12mo for v1.
- GPU support — defer until CPU runs prove unworkable.
- Multi-horizon production deployment from one tournament — v2 (TOURN-V2-02).
- XRP / AVAX inclusion — v2 (TOURN-V2-01); harness must not hardcode-exclude.
- Live-vs-backtest signal divergence audit (MLCL-04) — Phase 5.
- Custom CUDA / PyTorch builders — out of scope; Keras-only for v1.
- Tournament-of-tournaments (cross-tournament aggregation, CI auto-trigger) — not raised; v1 is operator-launched.
