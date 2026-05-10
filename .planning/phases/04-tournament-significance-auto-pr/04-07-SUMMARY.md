---
phase: 04-tournament-significance-auto-pr
plan: 07
subsystem: tournament-harness
tags: [tournament, ensemble, predict-fn, reproducibility, klines-filter]
provides:
  - "app.runner.predict_fn.build_predict_fn(snapshot) factory"
  - "Snapshot-bound predict-only callable for ensemble member re-hydration"
  - "Path-traversal guard at the predict_fn layer (T-04-36 defense in depth)"
  - "USDT-suffix assertion at the predict_fn layer (T-04-38)"
  - "D-13 reproducibility extension into Phase 4 (seed → identical OOS arrays)"
requires:
  - "app.runner.data.load_klines_from_timescale (canonical klines reader, CD-11)"
  - "app.core.stationary_features (compute_stationary_features + STATIONARY_FEATURE_COLS)"
  - "app.runner.sequences.create_sequences"
  - "app.core.models.REGISTRY"
  - "Phase 3 snapshot dict shape (export_snapshot output)"
affects:
  - "04-03 open-pr CLI: replace _build_predict_fn stub's NotImplementedError with `from app.runner.predict_fn import build_predict_fn`"
  - "04-04 idempotency CI test: monkeypatch on predict_cache.get_or_build_predictions still bypasses this module"
  - "04-06 e2e test: same monkeypatch shortcut keeps TF/Keras out of the e2e run"
tech-stack:
  added: []
  patterns:
    - "Path-traversal regex guard — ^[A-Za-z0-9._\\-]+$ on tournament_id (factory) and run_id (callable)"
    - "Lazy imports of app.core.* keep import-time cheap and let host pytest stub via sys.modules"
    - "Sys.modules injection for unit-test stubs — host pytest cannot resolve app.core because tournament-harness app/ shadows ml-retraining-service per 04-01 deviation"
    - "Defense-in-depth duplication of _seed_all rather than importing __main__'s private dunder"
key-files:
  created:
    - "services/tournament-harness/app/runner/predict_fn.py"
    - "services/tournament-harness/tests/unit/test_runner_predict_fn.py"
  modified: []
decisions:
  - "Plan <interfaces> referenced `build_train_test_split` and `build_and_train_model` symbols that do not exist in the live tree. Per planner's <action> note, used the actual __main__.py primitives (compute_stationary_features, create_sequences, sklearn train_test_split, REGISTRY[arch].build). No parallel training routine introduced."
  - "_seed_all is duplicated (six lines) inside predict_fn.py rather than imported from app.runner.__main__ — importing a private dunder symbol from a CLI entrypoint module would couple two unrelated lifecycles."
  - "last_close indexing copy-pasted from __main__.py lines 311-316 verbatim — the snapshot was scored with that exact slice; D-13 reproducibility requires byte-equivalent reconstruction."
  - "Prediction arrays flattened from (n, horizon) to 1-D by selecting the last horizon column. predict_cache contract (04-01 SUMMARY) mandates 1-D arrays; metrics_bridge passes 2-D straight through but the bootstrap test consumes log-returns at the predicted bar."
metrics:
  duration: "~25 minutes"
  tasks: 1
  unit-tests-added: 10
  files-created: 2
  files-modified: 0
  completed: 2026-05-09
---

# Phase 4 Plan 07: build_predict_fn for Ensemble Re-hydration — Summary

Production predict-only callable factory used by `open-pr`'s ensemble re-hydration. Resolves blocker **B3** (predict_fn circularly deferred between 04-01/04-03/04-06) and the static portion of blocker **B1** (every klines read in services/tournament-harness/ goes through the canonical loader whose SQL enforces `is_mainnet = TRUE`).

## Files Created

| Path | Lines | Purpose |
|------|-------|---------|
| `services/tournament-harness/app/runner/predict_fn.py` | ~225 | `build_predict_fn(snapshot)` factory + lazy-import-based deterministic predict pipeline |
| `services/tournament-harness/tests/unit/test_runner_predict_fn.py` | ~310 | 10 unit tests — shape contract, canonical loader use, no raw SQL, canonical import, is_mainnet evidence, determinism, run_id traversal guard, tournament_id traversal guard, status filter, USDT-suffix assertion |

## Public API

```python
from app.runner.predict_fn import build_predict_fn

predict_fn = build_predict_fn(snapshot)         # validates tournament_id at factory time
arrays = predict_fn(member_row)                 # validates run_id, status, symbol;
                                                 # then load klines → features → split →
                                                 # build → fit → predict (all via canonical
                                                 # primitives; no parallel training routine)

# arrays = {
#     "pred_prices":   np.ndarray,   # shape (N_oos,) float64
#     "actual_prices": np.ndarray,   # shape (N_oos,) float64
#     "last_close":    np.ndarray,   # shape (N_oos,) float64 — close at t-1 per OOS bar
# }
```

## Output Contract (consumed by `predict_cache.get_or_build_predictions`)

| Key | Shape | Description |
|-----|-------|-------------|
| `pred_prices`   | `(N_oos,) float64` | Model predicted bar at the predicted horizon |
| `actual_prices` | `(N_oos,) float64` | Ground-truth bar at the same step (`y_test[:, -1]`) |
| `last_close`    | `(N_oos,) float64` | Close at `t-1` for the log-return base used by `compute_returns_metrics` |

All three arrays have identical positive length. `predict_cache` revalidates shapes before atomic `.npz` write per 04-01 contract.

## Validation & Threat Mitigations

| Layer | Check | Threat |
|-------|-------|--------|
| Factory entry | `tournament_id` matches `^[A-Za-z0-9._\-]+$` | T-04-36 (path traversal in cache write downstream) |
| Callable entry | `run_id` matches the same regex | T-04-36 |
| Callable entry | `row.status == "success"` | snapshot pre-filter regression catch |
| Callable entry | `symbol.endswith("USDT")` (assert) | T-04-38 (spoofing / misconfigured spec) |
| Callable body | klines read goes through `load_klines_from_timescale` (no raw SQL in module) | T-04-37 (testnet contamination) |
| Static test | `re.search(r"\\bSELECT\\s+", source)` returns None | B1 regression guard |
| Static test | `from app.runner.data import load_klines_from_timescale` present in source | B1 regression guard |
| Static test | `is_mainnet` literal present in source (docstring/comment trail) | B1 audit trail |

The existing B1 integration test `test_klines_filter_required.py` continues to pass after this plan (5/5 green) — the new module is scanned by `app_root.rglob("*.py")` and emits no klines-read patterns of its own.

## Reproducibility Guarantee (D-13)

Two invocations of `predict_fn(row)` with identical inputs return numpy-array-equal outputs:
- `_seed_all(seed)` runs BEFORE any data shuffling / model construction — same six-line body as `__main__._seed_all`.
- Train/test split uses `sklearn.train_test_split(..., shuffle=False)` (chronological).
- `last_close` slice mirrors `__main__.py:311-316` byte-for-byte.

`test_predict_fn_determinism_same_inputs_same_outputs` asserts numpy-equal arrays across two calls.

## Notes for Downstream Plans

### 04-03 (`open-pr` CLI)

Replace the existing `_build_predict_fn` stub's `NotImplementedError` with:

```python
from app.runner.predict_fn import build_predict_fn

# Inside run_open_pr, after snapshot is loaded:
predict_fn = build_predict_fn(snapshot)
# For each ensemble member row:
arrays = get_or_build_predictions(
    harness_root=HARNESS_ROOT,
    tournament_id=snapshot["tournament_id"],
    run_id=member_row["run_id"],
    predict_fn=lambda: predict_fn(member_row),  # zero-arg adapter
)
```

The lambda adapts the `(row) -> dict` signature to the `() -> dict` predict_cache expects.

### 04-04 (idempotency CI test)

No change. The existing monkeypatch on `predict_cache.get_or_build_predictions` continues to bypass this module entirely.

### 04-06 (e2e)

No change. Same monkeypatch shortcut applies — the e2e run does not pull TF/Keras through this code path.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Plan `<interfaces>` referenced symbols that do not exist**

- **Found during:** Read-first phase (before writing any code).
- **Issue:** Plan's `<interfaces>` block named `app.runner.sequences.build_train_test_split` and `app.runner.train.build_and_train_model`. Neither exists in the live tree. `sequences.py` has only `create_sequences`. `app.runner.train` does not exist as a module. The actual training flow lives inline in `__main__.py:main()` lines 199-322 using `compute_stationary_features` → `create_sequences` → sklearn `train_test_split` → `REGISTRY[arch].build` → `model.fit`.
- **Fix:** Per planner's `<action>` note ("if its name differs in the live tree, read `__main__.py` to find the right symbol and update the import. Do NOT inline a parallel training routine here"), composed `predict_fn` from the actual primitives. No new helper functions extracted; no parallel training routine introduced; `files_modified` frontmatter respected (only `predict_fn.py` + its test).
- **Files affected:** `services/tournament-harness/app/runner/predict_fn.py` (production module — composes existing imports).
- **Tests adjusted:** Test monkeypatch targets switched from the named-but-missing symbols to the actual ones (`load_klines_from_timescale` + `sys.modules` injection of fake `app.core.stationary_features` and `app.core.models`). All 9 named test cases preserved with their assertions; one extra test (`test_predict_fn_path_traversal_rejected_in_tournament_id`) was added as a sibling of the run_id traversal test to cover both layers — total 10 tests, all green.
- **Commit:** `6cf753f`

**2. [Rule 2 — Critical] Lazy-import `app.core.*` to keep import-time cheap and host pytest functional**

- **Found during:** GREEN phase — eager `from app.core.stationary_features import ...` at module top would fail under host pytest (the tournament-harness `app/` package shadows ml-retraining-service's per the 04-01 SUMMARY deviation). Eager import → all 10 tests would error out at collection.
- **Fix:** All `app.core.*` imports moved INSIDE `_predict`. The static-check tests (raw-SQL grep, canonical-loader-import grep) continue to pass because they scan the source text, not the import side-effects. Host pytest stubs `app.core` via `monkeypatch.setitem(sys.modules, ...)`. In production (Docker container), `app.core` resolves naturally because `PYTHONPATH=/app:/opt/ml_retraining`.
- **Files affected:** `services/tournament-harness/app/runner/predict_fn.py`.
- **Commit:** `6cf753f`

### CLAUDE.md / Project-Rule Adjustments

None. Plan respects:
- Conventional-commit format (`test(tournament 04-07): ...`, `feat(tournament 04-07): ...`).
- `is_mainnet=TRUE` filter via canonical loader (CLAUDE.md "Data integrity" + B1).
- No `git clean` / no destructive operations.
- 2% LIVE risk cap untouched (this plan is read-only with respect to trading flags).
- TOURN-07 hygiene: no metric definitions (only imports of canonical loader); the existing grep-gate test continues to pass.

## Verification Results

| Check | Result |
|-------|--------|
| `pytest services/tournament-harness/tests/unit/test_runner_predict_fn.py -x -q` | **PASS** (10/10 in 4.0s) |
| `grep -nE "\\bSELECT\\s+\|FROM\\s+klines" services/tournament-harness/app/runner/predict_fn.py` | clean |
| `grep -n "from app.runner.data import load_klines_from_timescale" services/tournament-harness/app/runner/predict_fn.py` | line 49 |
| `grep -n "is_mainnet" services/tournament-harness/app/runner/predict_fn.py` | 4 mentions (docstring trail) |
| `grep -n "def build_predict_fn" services/tournament-harness/app/runner/predict_fn.py` | line 84 |
| `pytest services/tournament-harness/tests/integration/test_klines_filter_required.py` | **PASS** (5/5 — B1 regression guards still green) |
| Path-traversal guard exercised on `..`, `/`, NUL, whitespace, `\\` | covered (run_id × 5 inputs + tournament_id × 1) |
| Determinism — two calls with same inputs → numpy-equal arrays | asserted via `np.testing.assert_array_equal` ×3 |

## Self-Check: PASSED

- Created `services/tournament-harness/app/runner/predict_fn.py` — present
- Created `services/tournament-harness/tests/unit/test_runner_predict_fn.py` — present
- Commit `c78d554` (test RED) — present in git log
- Commit `6cf753f` (feat GREEN) — present in git log
- All 10 unit tests passing on host pytest runner (no docker required)
- B1 integration test still passes (5/5)

## Threat Flags

None. predict_fn introduces no new network endpoint, file-system write, or
schema change at a trust boundary that wasn't already in the plan's `<threat_model>`.
