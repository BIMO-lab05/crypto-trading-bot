---
phase: 03-tournament-harness-core
plan: "02"
subsystem: ml
tags: [keras, tensorflow, registry, gru, lstm, transformer, tcn, refactor]

# Dependency graph
requires:
  - phase: pre-phase-3
    provides: "ml-retraining-service ModelTrainer with build_gru_model"
provides:
  - "app.core.models package: REGISTRY dict with gru/lstm/transformer/tcn"
  - "Each builder exposes build(input_shape, hp) -> keras.Model with hp validation"
  - "ModelTrainer.architecture attribute (default 'gru') for dynamic dispatch"
  - "Backward-compat shim: build_gru_model still callable, identical compile contract"
affects: [03-06-tournament-runner, 03-tournament-harness, ml-retraining-service]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Registry pattern: per-architecture module exposing uniform build(input_shape, hp) -> keras.Model"
    - "Defensive HP validation at build time: ValueError on missing keys, out-of-range scalars/lists, invalid arch-specific options (T-03-04, T-03-05)"
    - "Dynamic dispatch via `REGISTRY[self.architecture]` with sensible default ('gru') for legacy bit-identical behaviour"

key-files:
  created:
    - "services/ml-retraining-service/app/core/models/__init__.py"
    - "services/ml-retraining-service/app/core/models/gru.py"
    - "services/ml-retraining-service/app/core/models/lstm.py"
    - "services/ml-retraining-service/app/core/models/transformer.py"
    - "services/ml-retraining-service/app/core/models/tcn.py"
    - "services/ml-retraining-service/tests/unit/__init__.py"
    - "services/ml-retraining-service/tests/unit/test_models_gru.py"
    - "services/ml-retraining-service/tests/unit/test_models_lstm.py"
    - "services/ml-retraining-service/tests/unit/test_models_transformer.py"
    - "services/ml-retraining-service/tests/unit/test_models_tcn.py"
  modified:
    - "services/ml-retraining-service/app/core/model_trainer.py"
    - "services/ml-retraining-service/tests/test_model_trainer.py"

key-decisions:
  - "Registry path is a sibling-module pattern (each arch own file), not a single dispatcher function. Keeps each builder ≤90 LOC (CD-01) and lets tournament harness import the same module set as ml-retraining without service-boundary copies."
  - "Default ModelTrainer.architecture='gru' preserves bit-identical legacy behaviour. Tournament harness flips this attribute per experiment in 03-06; no config-flag plumbing needed."
  - "Backward-compat shim (build_gru_model) kept rather than deleted, so any external direct caller continues to work even though the only intra-repo caller is model_trainer itself."
  - "HP validation lives inside each module's _validate_hp helper. Architecture-specific keys (n_heads, kernel_size, dilation_base, n_blocks) carry explicit allow-list checks per T-03-05, not free-range numeric bounds."

patterns-established:
  - "Per-architecture registry under app.core.models: each module exposes _REQUIRED_HP_KEYS, _validate_hp(hp), and build(input_shape, hp) -> keras.Model. New architectures slot in by adding a sibling file and one entry in __init__.py REGISTRY dict."
  - "TDD per task with explicit RED commit (test() ...) before GREEN commit (feat() / refactor()). RED commits make the failing test the historical record of intent."
  - "Plan-deviation tracking via `[Rule N - Type] description` annotations in commit bodies, with cross-reference to .planning/phases/<phase>/deferred-items.md for any out-of-scope items."

requirements-completed:
  - TOURN-01
  - TOURN-03

# Metrics
duration: 41min
completed: 2026-05-09
---

# Phase 03 Plan 02: Model registry refactor — extract gru/lstm/transformer/tcn builders Summary

**Extracted ml-retraining's monolithic build_gru_model into a four-module registry (gru/lstm/transformer/tcn) under app.core.models, each exposing a uniform build(input_shape, hp) -> keras.Model contract with defensive hp validation; rewired ModelTrainer to dispatch via REGISTRY[self.architecture] while preserving bit-identical legacy default behaviour.**

## Performance

- **Duration:** ~41 min
- **Started:** 2026-05-09T00:21:00Z
- **Completed:** 2026-05-09T01:03:30Z
- **Tasks:** 3 (all complete)
- **Files created:** 10
- **Files modified:** 2
- **Test additions:** 21 unit/regression tests (5 gru + 5 lstm + 5 transformer + 5 tcn + 1 registry-dispatch)

## Accomplishments

- **Registry public surface live.** `from app.core.models import REGISTRY` resolves to `{"gru": <module>, "lstm": <module>, "transformer": <module>, "tcn": <module>}`; each module's `.build(input_shape, hp) -> keras.Model` has been smoke-tested with `(60, 17)` input shape and produces a `(None, 5)` output for horizon=5.
- **Defensive hp validation in place.** Every builder calls `_validate_hp(hp)` first; missing keys, units > 4096, dropout outside [0, 1), lr outside [1e-6, 1.0], horizon outside [1, 256], invalid `n_heads` (transformer), invalid `kernel_size` / `dilation_base` (tcn) all raise `ValueError` early — pre-empting the OOM-at-construction failure mode of T-03-04 and the pathological-architecture mode of T-03-05.
- **ModelTrainer dispatch wired.** `model_trainer.py` now imports `REGISTRY`, sets `self.architecture = "gru"` defensively in `__init__`, replaces `build_gru_model` body with a thin shim that delegates to `REGISTRY["gru"].build(...)`, and rewires the `train_model` Step 4 call site to `REGISTRY[self.architecture].build(...)`. Default `architecture="gru"` keeps legacy retrain jobs bit-identical.
- **Regression confirmed clean.** ml-retraining test suite: 167 passing, 1 pre-existing failure (verified pre-existing on HEAD~3 baseline; not a 03-02 regression — see Deferred Issues).
- **Architecture coverage ≤90 LOC each.** Final builder LOC after formatter passes: gru.py 76, lstm.py 63, transformer.py 80, tcn.py 88. All within CD-01 budget.

## Task Commits

Each task was committed atomically. TDD tasks have separate RED (test) and GREEN (feat/refactor) commits.

1. **Task 1 RED: failing tests for gru registry** — `a27aab1` (test)
2. **Task 1 GREEN: gru.py + __init__.py registry** — `82b0f1e` (feat)
3. **Task 2 RED: failing tests for lstm/transformer/tcn** — `3125547` (test)
4. **Task 2 GREEN: lstm/transformer/tcn builders + REGISTRY full set** — `a719208` (feat)
5. **Task 3: rewire model_trainer.py to REGISTRY dispatch** — `ddeab74` (refactor)
6. **Deferred-items tracking** — `a8f7ccc` (docs)

## Files Created/Modified

### Created
- `services/ml-retraining-service/app/core/models/__init__.py` — registry module: imports the four sibling modules and exposes `REGISTRY` dict.
- `services/ml-retraining-service/app/core/models/gru.py` — GRU builder. Verbatim port of legacy `build_gru_model` body, parameterised on hp. 76 LOC.
- `services/ml-retraining-service/app/core/models/lstm.py` — LSTM builder. Same shape as gru with `layers.LSTM` swapped in. 63 LOC.
- `services/ml-retraining-service/app/core/models/transformer.py` — Functional Keras model: input projection + n_blocks of (MultiHeadAttention + LayerNorm + FFN + LayerNorm) + GlobalAveragePooling1D + Dense head. Validates `n_heads in {1,2,4,8,16}`, `n_blocks in [1, 8]`. 80 LOC.
- `services/ml-retraining-service/app/core/models/tcn.py` — Functional Keras model: residual stack of dilated causal Conv1D blocks (`dilation_rate = dilation_base ** i`) + GlobalAveragePooling1D + Dense head. Validates `kernel_size in {2,3,4,5,7}`, `dilation_base in {2,3}`, `n_blocks in [1, 8]`. 88 LOC.
- `services/ml-retraining-service/tests/unit/__init__.py` — empty package marker for the new tests/unit/ subdir.
- `services/ml-retraining-service/tests/unit/test_models_gru.py` — 5 tests: happy-path build, missing-key reject, out-of-range units reject, zero-horizon reject, registry presence.
- `services/ml-retraining-service/tests/unit/test_models_lstm.py` — 5 mirror tests for LSTM.
- `services/ml-retraining-service/tests/unit/test_models_transformer.py` — 5 tests: happy-path build, missing-key reject, invalid `n_heads=3` reject (T-03-05), out-of-range units reject, registry presence.
- `services/ml-retraining-service/tests/unit/test_models_tcn.py` — 5 tests: happy-path build, missing-key reject, invalid `kernel_size=10` reject, invalid `dilation_base=4` reject, registry presence.
- `.planning/phases/03-tournament-harness-core/deferred-items.md` — out-of-scope items found during execution.

### Modified
- `services/ml-retraining-service/app/core/model_trainer.py` — added `from app.core.models import REGISTRY` import; added `self.architecture = getattr(self, "architecture", "gru")` in `__init__`; replaced `build_gru_model` body with a registry-delegating shim; rewired `train_model` Step 4 to `REGISTRY[self.architecture].build(...)`. The `train_test_split`, callbacks, metrics, CPCV, and save_model paths are untouched.
- `services/ml-retraining-service/tests/test_model_trainer.py` — appended `test_train_uses_registry_when_architecture_set` covering the dynamic-dispatch path: default `trainer.architecture == "gru"` confirmed, flipping to `"lstm"` resolves to the LSTM module, and the resulting model has at least one LSTM layer.

## Decisions Made

- **Registry as sibling modules, not a dispatcher class.** Each architecture lives in its own file under `app/core/models/`. Keeps each builder under the ≤80/90 LOC CD-01 budget, and lets the tournament harness import the same modules ml-retraining does without copying them across service boundaries.
- **Backward-compat shim retained for `build_gru_model`.** Even though the only intra-repo caller is `model_trainer` itself, the public method stays — any external script importing `from app.core.model_trainer import ModelTrainer; trainer.build_gru_model(...)` continues to work, with identical compile output (Adam(lr=0.001), loss="mse", metrics=["mae"]).
- **Architecture-specific allow-lists, not free-range bounds.** `n_heads`, `kernel_size`, `dilation_base` use explicit set membership (e.g., `{1, 2, 4, 8, 16}`) rather than numeric ranges. This makes pathological tournament configs (e.g., `kernel_size=999`) fail loudly at build time instead of silently consuming GBs of memory before T-03-05's container-level mem cap kicks in.
- **Default `self.architecture = "gru"` via `getattr`.** Defensive — leaves any externally-set attribute alone (e.g., a future subclass that sets `self.architecture` before calling `__init__`). Guarantees existing retrain jobs are bit-identical post-refactor.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan's draft `test_train_uses_registry_when_architecture_set` had wrong constructor and unused fixtures**

- **Found during:** Task 3 (model_trainer rewire / new test).
- **Issue:** The plan's draft test invoked `ModelTrainer(symbol="BTCUSDT", interval="5m")`, but the actual `ModelTrainer.__init__(self)` takes zero positional or keyword args (constructor reads symbol/interval lazily from settings or function args). Additionally the fixture list `(monkeypatch, sample_klines_df)` was unused in the test body, and `sample_klines_df` is not defined anywhere in `tests/conftest.py` — the real fixture name is `synthetic_ohlcv` and it isn't needed for this test.
- **Fix:** Replaced with a parameter-less test function calling `trainer = ModelTrainer()`. Added an explicit `assert trainer.architecture == "gru"` before flipping to `"lstm"` to lock in the default invariant.
- **Files modified:** `services/ml-retraining-service/tests/test_model_trainer.py`.
- **Verification:** `pytest tests/test_model_trainer.py::test_train_uses_registry_when_architecture_set -x` passes (1/1). Documented in the commit message.
- **Committed in:** `ddeab74` (Task 3 commit).

**2. [Rule 1 - Bug] Plan's `tcn.py` body would have exceeded the ≤90 LOC CD-01 budget under the project's auto-formatter**

- **Found during:** Task 2 verification (LOC checks).
- **Issue:** The plan's specified TCN body, when written out with the formatter (black-style 88-char wrapping) expanded to 91-93 LOC across two write attempts. CD-01's acceptance criterion is `< 90`.
- **Fix:** Compressed `_REQUIRED_HP_KEYS` onto a single line, kept long ValueError messages on one line where they fit under 88 chars, and reduced docstring noise. Final tcn.py is 88 LOC. Logic and validation behaviour are identical to the plan spec; only formatting was changed.
- **Files modified:** `services/ml-retraining-service/app/core/models/tcn.py`.
- **Verification:** `wc -l < tcn.py` returns 88; all 5 tcn tests still pass.
- **Committed in:** `a719208` (Task 2 commit).

---

**Total deviations:** 2 auto-fixed (Rule 1).
**Impact on plan:** Both deviations were correctness/precision fixes, not scope changes. Task semantics, public surface, and acceptance criteria are exactly as the plan specified.

## Issues Encountered

- **Auto-flake stripped `from app.core.models import REGISTRY` between Edit calls** (project memory: "Main.py autoflake strips test-patched imports"). The auto-formatter on `model_trainer.py` removed the import the first time because the import wasn't yet referenced anywhere in the file body. Resolved by reordering the edits so REGISTRY usage (in the `build_gru_model` shim and `train_model` call site) was added FIRST, then the import was re-added — autoflake then preserved it because it had a real reference.
- **Pre-existing `test_save_model_writes_scalers_pkl_with_expected_keys` failure** surfaced in the regression run. Verified to fail identically on the pre-03-02 baseline (`HEAD~3` of `model_trainer.py`); the test bug is `assert payload["price_scaler"] is scaler_y` — an identity check after a serialise/deserialise round-trip, which can't pass by construction. Documented in `deferred-items.md`. Not a 03-02 regression.

## Deferred Issues

See `.planning/phases/03-tournament-harness-core/deferred-items.md` for full details. Two items, both pre-existing:

1. semgrep CWE-502 flag on the existing scaler-state binary serialisation in `model_trainer.save_model` (commit `ecdb29d`). Out of scope; the prediction service depends on the binary handoff contract.
2. Pre-existing failing test `test_save_model_writes_scalers_pkl_with_expected_keys` (test correctness bug; verified to fail on the pre-03-02 baseline).

## User Setup Required

None — no external service configuration required. The registry refactor is purely an internal restructuring; no env vars added, no compose changes, no migrations.

## Next Phase Readiness

- **Plan 03-06 (tournament-runner build) unblocked.** It can now `from app.core.models import REGISTRY` once the ml-retraining `app/` directory is on its `PYTHONPATH` (Dockerfile add) — the registry returns Keras-compiled models that `model.fit(...)` consumes directly, identically to how `model_trainer.train_model` exercises them today.
- **Tournament HP grid (Plan 03-04) can refer to the four architectures.** Each builder accepts the same hp dict shape with optional architecture-specific keys (`n_heads`/`n_blocks` for transformer, `kernel_size`/`dilation_base`/`n_blocks` for tcn). The YAML loader can map `tournament.architectures.transformer.hp_grid` directly to the `transformer.build(input_shape, hp)` signature.
- **No blockers.** Default ml-retraining behaviour is bit-identical, and the new dispatch path is opt-in via `trainer.architecture = "lstm"|"transformer"|"tcn"`.

## Self-Check: PASSED

**Files (11):** all created files verified present on disk.
- `services/ml-retraining-service/app/core/models/{__init__,gru,lstm,transformer,tcn}.py` — present.
- `services/ml-retraining-service/tests/unit/{__init__,test_models_gru,test_models_lstm,test_models_transformer,test_models_tcn}.py` — present.
- `.planning/phases/03-tournament-harness-core/deferred-items.md` — present.

**Commits (6):** all hashes located in `git log --oneline --all`.
- `a27aab1` test(03-02): RED for gru registry tests
- `82b0f1e` feat(03-02): gru.py + REGISTRY
- `3125547` test(03-02): RED for lstm/transformer/tcn tests
- `a719208` feat(03-02): lstm/transformer/tcn builders
- `ddeab74` refactor(03-02): model_trainer rewire
- `a8f7ccc` docs(03-02): deferred-items.md

---
*Phase: 03-tournament-harness-core*
*Plan: 02*
*Completed: 2026-05-09*
