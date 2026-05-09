# Phase 03 - Deferred Items

Items found during execution that are out-of-scope for the current plan.

## Plan 03-02 (model registry refactor)

### 1. Pre-existing serialisation warning in model_trainer.py

- **File:** `services/ml-retraining-service/app/core/model_trainer.py` (around line 723)
- **Pattern:** Binary scaler-state serialisation in `save_model`
- **Tool flag:** semgrep CWE-502 (Deserialization of Untrusted Data)
- **Why deferred:** Pre-existing code from commit `ecdb29d` ("ML retrained-model handoff + live-reload"). The
  prediction service (`services/ml-prediction-service/app/ml_models/gru_model.py`) loads `scalers.pkl` as a
  single payload — this is the documented retraining -> prediction handoff contract that Plan 03-02
  explicitly preserves (the scalers contract is locked by
  `test_save_model_writes_scalers_pkl_with_expected_keys`).
- **Risk model:** Trust boundary is internal — both writer and reader are services we own; no untrusted
  input reaches the deserialiser. Exploitation would require an attacker who can write to the model
  artifacts directory, which is already a much bigger compromise.
- **Suggested fix path:** Migrate to a safer format (joblib with allow-list, or a JSON-encoded MinMaxScaler
  state dict). Requires coordinated change across `model_trainer.save_model` AND
  `ml-prediction-service/app/ml_models/gru_model._load_model`. Out-of-scope for the registry refactor.
- **Owner:** Future plan (likely under Phase 5 ML cleanup or a dedicated security-hardening phase).

### 2. Pre-existing failing test: `test_save_model_writes_scalers_pkl_with_expected_keys`

- **File:** `services/ml-retraining-service/tests/test_model_trainer.py:208`
- **Pattern:** `assert payload["price_scaler"] is scaler_y` — identity check after a serialise/deserialise round-trip
- **Why deferred:** Test was already failing on the pre-03-02 baseline (verified by checking out HEAD~3 of
  `services/ml-retraining-service/app/core/model_trainer.py`, running the same test, observing the same
  failure). The other two assertions in the same test (`isinstance(payload["price_scaler"], MinMaxScaler)`
  and the "scaler_y -> price_scaler" mapping at the type level) succeed; only the `is` identity check
  fails because deserialised objects are new instances by definition.
- **Suggested fix path:** Replace `is` with structural equality (e.g., compare `min_`, `scale_`, `data_min_`
  attribute arrays) or assert only the type contract. Out-of-scope for the registry refactor (this is a
  test correctness bug in `test_save_model_writes_scalers_pkl_with_expected_keys`, not in production code).
- **Owner:** Test-hygiene cleanup; tracked here so the verifier doesn't flag it as a regression of 03-02.
