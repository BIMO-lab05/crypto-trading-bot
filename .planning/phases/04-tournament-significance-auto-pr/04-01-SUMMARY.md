---
phase: 04-tournament-significance-auto-pr
plan: 01
subsystem: tournament-harness
tags: [tournament, significance, ensemble, cache, atomic-write]
provides:
  - "app.significance package (D-03/D-14 atomic artifact writers)"
  - "select_top_n_per_symbol (D-01) + aggregate_log_returns (D-02)"
  - "get_or_build_predictions on-disk .npz cache (CD-11)"
  - "log_returns_from_predictions pure-numpy helper"
requires:
  - "app.leaderboard.snapshot atomic-write pattern (lines 65-87)"
  - "Phase 3 snapshot dict shape (export_snapshot output)"
affects:
  - "Phase 4 plans 04-02 (bootstrap consumes aggregate_log_returns output) and 04-03 (open-pr CLI wires predict_fn callback)"
tech-stack:
  added: [numpy 1.26.4 (already present)]
  patterns:
    - "Atomic file write — tempfile.mkstemp + os.fsync + os.replace + cleanup-on-failure"
    - "Path-traversal regex guard — ^[A-Za-z0-9._-]+$ on both tournament_id and run_id"
    - "Equal-weighted ensemble aggregation — np.stack().mean(axis=0)"
key-files:
  created:
    - "services/tournament-harness/app/significance/__init__.py"
    - "services/tournament-harness/app/significance/artifacts.py"
    - "services/tournament-harness/app/significance/ensemble.py"
    - "services/tournament-harness/app/significance/predict_cache.py"
    - "services/tournament-harness/tests/unit/test_significance_artifacts.py"
    - "services/tournament-harness/tests/unit/test_significance_ensemble.py"
    - "services/tournament-harness/tests/unit/test_significance_predict_cache.py"
  modified:
    - "services/tournament-harness/tests/conftest.py (added synthetic_snapshot_dict factory fixture)"
decisions:
  - "Removed eager `from app.runner.metrics_bridge import compute_all_metrics` from ensemble.py (would block all host pytest runs since app.core.returns_metrics only resolves inside the harness container). TOURN-07 enforcement remains via the existing grep-gate test."
  - "Used tempfile suffix `.tmp.npz` (not `.npz.tmp`) for predict cache so numpy.savez does NOT auto-append `.npz` and break os.replace atomicity."
metrics:
  duration: "~25 minutes"
  tasks: 3
  unit-tests-added: 23
  files-created: 7
  files-modified: 1
  completed: 2026-05-10
---

# Phase 4 Plan 01: Significance/Ensemble Foundation — Summary

Per-symbol top-3-by-DSR ensemble selection (D-01), mean-of-log-returns aggregation (D-02), config-by-reference artifact writers (D-03/D-14), and a deterministic predict-only on-disk cache (CD-11) — the foundation 04-02 (bootstrap) and 04-03 (open-pr CLI) consume directly.

## Files Created

| Path | Lines | Purpose |
|------|-------|---------|
| `services/tournament-harness/app/significance/__init__.py` | 0 | Package marker |
| `services/tournament-harness/app/significance/artifacts.py` | ~140 | Atomic writers for `{tid}.ensemble.json`, `{tid}.significance.json`, `{tid}.leaderboard.md` |
| `services/tournament-harness/app/significance/ensemble.py` | ~115 | `select_top_n_per_symbol`, `aggregate_log_returns`, `member_descriptor` |
| `services/tournament-harness/app/significance/predict_cache.py` | ~150 | `get_or_build_predictions` + `log_returns_from_predictions` (CD-11 cache) |
| `services/tournament-harness/tests/unit/test_significance_artifacts.py` | ~115 | 6 unit tests — atomic-write, schema, no-weights, failure cleanup |
| `services/tournament-harness/tests/unit/test_significance_ensemble.py` | ~165 | 9 unit tests — D-01 tie-break, status filter, CD-08 short list, D-02 aggregation, TOURN-07 hygiene |
| `services/tournament-harness/tests/unit/test_significance_predict_cache.py` | ~150 | 8 unit tests — cache hit/miss, atomic .npz, T-04-01 path-traversal guard |

`services/tournament-harness/tests/conftest.py` extended with `synthetic_snapshot_dict` factory fixture mirroring the Phase 3 export contract (5 symbols × 4 rows; one `status="failed"` per symbol so the success-only filter has bite; deterministic `dsr = 0.5 + 0.1*i`).

## Public API

### `app.significance.artifacts`

```python
SCHEMA_VERSION = 1

def write_ensemble(
    snapshot: Dict[str, Any],
    ensembles: Dict[str, list[Dict[str, Any]]],
    git_sha: str,
    output_path: str | os.PathLike,
) -> Dict[str, Any]: ...
# D-03/D-14 — config-by-reference; payload contains ONLY: schema_version,
# tournament_id, git_sha, created_at, aggregation="mean_log_returns", ensembles.

def write_significance(
    snapshot: Dict[str, Any],
    per_symbol_results: Dict[str, Dict[str, Any]],
    *,
    git_sha: str,
    tournaments_evaluated_count: int,
    n_winning_symbols: int,
    output_path: str | os.PathLike,
) -> Dict[str, Any]: ...
# D-14 — top-level: schema_version, tournament_id, baseline="persistence",
# aggregation="mean_log_returns", git_sha, evaluated_at,
# tournaments_evaluated_count (int), n_winning_symbols (int), per_symbol.

def write_leaderboard_markdown(
    markdown_text: str, output_path: str | os.PathLike
) -> str: ...
# CD-05 — atomic markdown write; returns the input text unchanged for
# inline-in-PR-body re-use.
```

### `app.significance.ensemble`

```python
def select_top_n_per_symbol(
    rows: Iterable[Dict[str, Any]], n: int = 3
) -> Dict[str, List[Dict[str, Any]]]: ...
# D-01 tie-break: dsr desc → cpcv_dsr desc → oos_sharpe desc → created_at asc.
# Filters status != "success". Symbols with < n successful runs return their
# available members (CD-08); caller decides on `[insufficient runs]` flag.

def aggregate_log_returns(
    member_log_returns: Sequence[np.ndarray],
) -> np.ndarray: ...
# D-02 — np.stack(arrays, axis=0).mean(axis=0). Equal-weighted across members.
# Raises ValueError on empty input or shape mismatch.

def member_descriptor(row: Dict[str, Any]) -> Dict[str, Any]: ...
# Strip a snapshot row to D-03 ensemble-member fields:
# {run_id, architecture, hp_hash, dsr}.
```

### `app.significance.predict_cache`

```python
def get_or_build_predictions(
    *,
    harness_root: Path,
    tournament_id: str,
    run_id: str,
    predict_fn: Callable[[], Dict[str, np.ndarray]],
) -> Dict[str, np.ndarray]: ...
# Returns {pred_prices, actual_prices, last_close} (all 1-D, equal length).
# Cache hit: predict_fn NEVER invoked. Cache miss: predict_fn called once,
# shapes validated, atomic .npz write to:
#   {harness_root}/data/cache/{tournament_id}/predictions/{run_id}.npz

def log_returns_from_predictions(
    pred_prices: np.ndarray, last_close: np.ndarray
) -> np.ndarray: ...
# Pure helper: log(pred_prices / last_close); zero-/negative-close defensively
# treated as 1.0 (crypto OOS closes are strictly positive in practice).
```

## Cache Path Schema (CD-11)

```
{harness_root}/data/cache/{tournament_id}/predictions/{run_id}.npz
```

Each .npz holds three named 1-D float arrays of identical length:

| Key | Description |
|-----|-------------|
| `pred_prices` | Model predicted close at each OOS bar |
| `actual_prices` | Ground-truth close at each OOS bar |
| `last_close` | Close at t-1 (log-return base for `compute_returns_metrics`) |

`tournament_id` and `run_id` are validated against `^[A-Za-z0-9._\-]+$` before any path construction (T-04-01 mitigation; mirrors snapshot.py's regex).

## TimescaleDB-Touching Note (CD-11 vs Integration Points)

`04-CONTEXT.md` Integration Points line says:
> tournament-harness ↔ TimescaleDB — `open-pr` does NOT touch TimescaleDB

CD-11 in the same document contradicts this — re-running predict on OOS klines is the only way to derive the ensemble's log-return series for the bootstrap test. **CD-11 wins.** The actual Postgres read happens in the `predict_fn` callback wired by 04-03's `open-pr` CLI handler (the callback closes over `snapshot.config`, `run_id`, `member.architecture`, `member.hp_hash`, queries klines via the existing `tournament_reader` role from Phase 3 D-09, loads the model, calls predict). **None of that lives in this module.** This module owns only the cache contract + the callback protocol — no DB driver, no model loading, no klines query.

A code-comment at the top of `predict_cache.py` documents the conflict and the resolution.

## Open Question for 04-03

**Which `predict_fn` implementation wires up?**

Two candidates surfaced in CD-11:

| Option | Pros | Cons |
|--------|------|------|
| **A.** Direct call into a stripped `runner.predict_only` path (a new function added to `app.runner` that loads model + queries klines + returns the three arrays, no training) | Fast — skips the launcher overhead; ensemble eval can run in seconds per member; reproducer (D-12) gets the same code path | Adds a new public function on the runner module; needs careful test coverage of the predict-only branch |
| **B.** Callback through `app.orchestrator.launcher.run_tournament` with a "predict-only" flag | Reuses the full launcher reproducibility scaffolding (git_sha capture, dirty-tree refusal, container isolation); zero new code on the runner side | Overkill for ensemble eval — spinning up a container per member just to call `model.predict()` is slow and wasteful for the operator's interactive `open-pr` invocation |

**Planner recommendation:** Option **A** — direct module call to `runner.predict_only`. The container-per-member overhead in B makes the interactive `open-pr` invocation feel slow without adding any reproducibility guarantee that D-13 (config + git_sha + seed → identical predictions) doesn't already provide. Reserve the launcher path for `tournament reproduce` (where the operator is asking for a forensic full-rerun anyway).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Removed eager `from app.runner.metrics_bridge import compute_all_metrics` from ensemble.py**

- **Found during:** Task 2 (running the GREEN tests)
- **Issue:** The plan skeleton listed this import as the TOURN-07 contract marker. Eager import of `metrics_bridge` transitively imports `from app.core.returns_metrics import compute_returns_metrics`, which only resolves inside the tournament-harness Docker image (where `PYTHONPATH=/app:/opt/ml_retraining` makes ml-retraining-service's `app/` directory addressable as `app.core`). On the host pytest runner, `app.core` doesn't resolve — the conftest path-shim adds tournament-harness's `app/` first, which shadows ml-retraining-service's. Module fails to import → all 9 ensemble tests error out at collection time.
- **Fix:** Replaced the import with an explanatory comment block. The actual TOURN-07 enforcement is the existing grep-gate test (`test_no_parallel_metric_definitions_in_module` in this plan; `test_no_metric_definitions_in_tournament_harness` in `test_runner_metrics_bridge.py` from Phase 3) — both run as static regex scans, no import resolution needed. When 04-02 / 04-03 actually need the canonical functions, they import from `metrics_bridge` directly at the call site (which is fine because those modules will be exercised inside the Docker container via integration tests; unit tests will skip via `pytest.importorskip` per the existing convention in `test_runner_metrics_bridge.py:32`).
- **Files modified:** `services/tournament-harness/app/significance/ensemble.py`
- **Commit:** `60fe45f`

**2. [Rule 1 — Bug] Changed predict-cache tempfile suffix from `.npz.tmp` to `.tmp.npz`**

- **Found during:** Task 3 (running the GREEN tests — `test_cache_miss_invokes_predict_callback_then_persists` failed with `EOFError: No data left in file`)
- **Issue:** `numpy.savez` always appends `.npz` to the target path if the path doesn't already end with `.npz`. With suffix `.npz.tmp`, savez wrote the actual zip archive to `tmp_path + ".npz"`, while the empty zero-byte file from `mkstemp` sat at `tmp_path`. The subsequent `os.replace(tmp_path, target)` moved the empty file into place — the durable cache entry was 0 bytes, and the next read crashed.
- **Fix:** Changed suffix to `.tmp.npz` (ends with `.npz` → savez writes directly to `tmp_path`, no extra suffix appended). Atomic-write semantics preserved.
- **Files modified:** `services/tournament-harness/app/significance/predict_cache.py`
- **Commit:** `a1e3af7`

### CLAUDE.md / Project-Rule Adjustments

None. Plan was already aligned with conventional-commits, atomic-write, and TOURN-07 hygiene.

## Verification Results

| Check | Result |
|-------|--------|
| `pytest test_significance_*.py` (23 tests) | **PASS** (0.84s) |
| `grep Path.write_text app/significance/` | clean (only docstring forbidding it) |
| `grep 'def (directional_accuracy|sharpe|deflated|compute_returns_metrics)' app/significance/` | clean |
| `grep '"weights"|"scaler"|"predictions"|"model_state"' artifacts.py` | clean |
| `grep 'data/cache' predict_cache.py` | present (CD-11 path) |
| Atomic-write — no .tmp leftovers after success | verified by tests + final cache dir enumeration |
| T-04-01 path-traversal guard on `..`, `/` | verified by tests for both tournament_id and run_id |

## Self-Check: PASSED

- Created `services/tournament-harness/app/significance/__init__.py` — present
- Created `services/tournament-harness/app/significance/artifacts.py` — present
- Created `services/tournament-harness/app/significance/ensemble.py` — present
- Created `services/tournament-harness/app/significance/predict_cache.py` — present
- Created `services/tournament-harness/tests/unit/test_significance_artifacts.py` — present
- Created `services/tournament-harness/tests/unit/test_significance_ensemble.py` — present
- Created `services/tournament-harness/tests/unit/test_significance_predict_cache.py` — present
- Modified `services/tournament-harness/tests/conftest.py` — present (added synthetic_snapshot_dict)
- Commit `a367a35` (test RED Task 1) — present in git log
- Commit `59705ca` (feat GREEN Task 1) — present
- Commit `0e7d8b7` (test RED Task 2) — present
- Commit `60fe45f` (feat GREEN Task 2) — present
- Commit `5bb2c9a` (test RED Task 3) — present
- Commit `a1e3af7` (feat GREEN Task 3) — present
- All 23 unit tests passing on host pytest runner (no docker required)
