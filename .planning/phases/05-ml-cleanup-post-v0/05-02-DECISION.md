# 05-02 Decision: T0.1.x Experiment Selection

**Decision file for:** Phase 05, Plan 02 (MLCL-02)
**Date:** 2026-05-13
**Decision status:** PRE-CONFIRMED by operator (orchestrator level). This document fulfils
the deliverable contract — all five options are analyzed honestly. The choice is binding
on Task 2 implementation.

---

## 1. Context

REQUIREMENTS.md MLCL-02 mandates that exactly one T0.1.x experiment runs through the
Phase 3+4 tournament harness and that its result — whether edge found, no edge found,
or insufficient infrastructure — is committed to the evidence directory with a binding
written decision note.

This is the second milestone of Phase 5's ML cleanup arc. Phase 5's premise is that
the V0 GRU directional models showed chance-level performance after the look-ahead
leakage fix (commit c56765c) — they score at or below persistence on log-return R² and
chance-corrected directional accuracy. MLCL-02 asks: given the corrected pipeline is
now plumbed end-to-end through a rigorously-evaluated tournament harness (Phases 3+4),
which single experiment is the most informative and lowest-risk first probe into whether
any variant of the current architecture finds edge on the validated symbol set?

Operator context: the only Phase 5 budget for ML experiments is this plan. Anything
requiring new Python code in the harness, new service integrations, or new Docker images
is high-risk given the single-plan budget. The decision must maximize information gain
per unit of implementation effort, and must be reversible (a failed experiment must not
leave broken code or blocked CI).

The validated symbol set per PROJECT.md is SOLUSDT, BNBUSDT, ADAUSDT. XRP and DOGE
are explicitly excluded. The tournament harness already generates per-symbol leaderboard
rows and per-symbol significance tests, so running on the 3-symbol set is directly
supported with zero code changes.

---

## 2. Options Analysis

### 2.1 Option A: Different Horizon (different_horizon)

**Description:** The Phase 3 example config uses `horizon: [5]` — the model predicts
5 bars ahead. This option sweeps multiple horizon values (e.g. 3, 5, 7, 10) while
keeping all other hyperparameters fixed. Because `horizon` is already a YAML list field
in the schema, this is a pure config change.

**Pros:**
- Zero new Python code — the harness already iterates over `horizon` values as part of
  the Cartesian grid sweep.
- Verified by RESEARCH.md: "`horizon: [5]` is already a list. Changing it to
  `[1, 24, 96]` is a pure YAML edit — zero Python code changes." (HIGH confidence)
- Runs end-to-end through the existing Phase 3+4 pipeline today without any schema
  changes, new architecture registry entries, or new Docker image layers.
- Result is directly interpretable: does the V0-fixed GRU model show edge at any
  prediction horizon? Confirming the V0 finding generalizes across horizons is
  genuine information.
- Reversible: deleting the YAML file is a complete unship. No Python changed, no
  prior phase's grep gates can be tripped.
- The leaderboard already indexes on `horizon` as part of the `hp_hash` composite
  key, so multi-horizon results are correctly deduplicated.

**Cons:**
- Smallest information gain of the five candidates in terms of architectural diversity.
  The V0 result (chance-level on log-returns) may simply repeat across all four
  horizons, confirming the negative result without opening any new research direction.
- Does not probe whether a fundamentally different model class (gradient-boosted trees,
  classification target) could find signal the current regression GRU cannot.

**Cost in this plan's context budget:** LOW — minutes to author, plus training time.
**Expected information gain:** LOW-MEDIUM — confirms whether horizon is a tunable
  lever or the negative result is horizon-invariant.
**Reversibility:** HIGH — YAML deletion is a complete and clean unship.

---

### 2.2 Option B: Classification Head (classification_head)

**Description:** Replace the regression target (predict next bar's price) with a
binary classification target (predict sign of next log-return). The hypothesis is that
predicting direction is a strictly easier problem than predicting magnitude, so a model
that cannot beat persistence on R² might still beat 50% on directional accuracy.

**Pros:**
- The claim has face validity: calibrated binary classifiers have lower sample-complexity
  requirements than regressors for the same underlying signal.
- If the model cannot exceed 50% direction accuracy (the classification floor), the
  regression-target result is confirmed by an independent metric. Strong diagnostic.
- The harness already tracks `dir_acc_corrected` so the metric infrastructure exists.

**Cons:**
- Requires a new `target_mode: "binary_direction"` in `tournament_loader.py`, a new loss
  function in the GRU runner, and a new metric mapping in `metrics_bridge.py`. These
  touch Phase 3's locked schema.
- The `chance-corrected dir_acc_corrected` already measures directional accuracy on the
  regression output — it is possible the classification head adds noise (logistic output
  calibration) without adding information beyond what the existing metric already shows.
- Hours of integration work before the tournament can launch. Risk of breaking existing
  Phase 3+4 grep gates (TOURN-07, no-legacy-R², no-auto-merge).

**Cost in this plan's context budget:** MEDIUM — hours.
**Expected information gain:** MEDIUM — genuinely different question, useful diagnostic.
**Reversibility:** MEDIUM — Python changes to tournament_loader and metrics_bridge must
  be cleaned up or gated behind a flag if the experiment is abandoned.

---

### 2.3 Option C: XGBoost Control (xgboost_control)

**Description:** Add a gradient-boosted tree model as a non-deep-learning baseline.
The hypothesis is that tabular feature engineering (lag features, rolling stats) gives
a tree ensemble more exploitable structure than a GRU trained on the same OHLCV sequence.

**Pros:**
- Industry-standard ML control experiment. If XGBoost outperforms GRU/LSTM/TCN on the
  same OOS window, the deep-learning architecture pivot may be wrong.
- Orthogonal to horizon — information gain is architectural, not temporal.
- scikit-learn is a well-understood dependency; no custom training loop needed.

**Cons:**
- Requires a new `architectures.xgboost` registry entry in the harness runner, a new
  hyperparameter grid schema, scikit-learn added as a Docker image dependency, and a new
  runner class in the orchestrator. Multi-day implementation effort.
- scikit-learn is not currently in the tournament-harness Docker image; adding it
  requires an image rebuild and risks breaking the existing TensorFlow-based runners
  due to dependency conflicts.
- High engineering risk relative to Phase 5's single-plan ML experiment budget.
- Not reversible cheaply — a new architecture registry entry requires either a flag
  guard or a revert commit to disable cleanly.

**Cost in this plan's context budget:** HIGH — days.
**Expected information gain:** HIGH — strongest architectural evidence.
**Reversibility:** MEDIUM — registry entry plus Docker image change is non-trivial
  to un-ship.

---

### 2.4 Option D: Cross-Sectional Features (cross_sectional)

**Description:** Feed a panel of related symbols' lagged returns to predict one symbol's
next-bar return. The hypothesis is that inter-symbol correlations (SOL-BTC, BNB-ETH)
carry predictive signal that per-symbol models cannot see.

**Pros:**
- Genuinely new signal source — if cross-asset momentum is exploitable, the panel model
  could lift dir_acc_corrected substantially.
- Would validate or refute the hypothesis that crypto markets have cross-sectional
  predictability at 5m resolution.

**Cons:**
- Requires a multi-symbol input pipeline: the current per-symbol data loader fetches one
  OHLCV series per training run. Changing to a panel input requires a new feature
  engineering layer, a new model interface (multi-input GRU), and changes to how the
  leaderboard stores input-feature-set metadata.
- Highest engineering risk of the five candidates. Estimated at days+ of work.
- Introduces a new dependency on the ordering and alignment of the panel — data leakage
  risk if symbols are not synchronized correctly.
- Reversibility is low: panel pipeline touches the core data loading path.

**Cost in this plan's context budget:** HIGH — days+.
**Expected information gain:** HIGH — but unreachable within this budget.
**Reversibility:** LOW — deep pipeline changes require careful unwinding.

---

### 2.5 Option E: Sentiment-as-Filter (sentiment_filter)

**Description:** Gate the GRU signal with a sentiment score from the parked
sentiment-analysis-service. The hypothesis is that the model's predictions have higher
directional accuracy on bars where sentiment is not conflicted.

**Pros:**
- Tests whether the parked sentiment-analysis-service has signal value before a full
  v2 integration. Resolves the deferred-item question early.
- Relatively simple signal-merge logic: apply a sentiment threshold as a position filter
  rather than modifying the model architecture.

**Cons:**
- CLAUDE.md project rule: `ENABLE_SENTIMENT_ANALYSIS=false`. The sentiment-analysis-
  service is parked and the sentiment leg has been removed from the signal pipeline
  (commits c346483, acae081, fe941cf, c171bb0). Un-parking requires service restart,
  configuration changes, and a new signal-merge layer.
- Conflicts directly with REQUIREMENTS.md MLCL-V2-01 which defers sentiment integration
  to v2. Shipping it here would pre-empt that planning artifact.
- The sentiment service image has historically failed to build via pip (PyPI read
  timeouts — CLAUDE.md gotchas). Build risk at the worst moment (single-shot Phase 5
  budget).
- Days+ of work even before the sentiment service image issue is resolved.

**Cost in this plan's context budget:** HIGH — days+, plus build-risk.
**Expected information gain:** MEDIUM — conditional on the service actually running.
**Reversibility:** LOW — conflicts with MLCL-V2-01 deferral; hard to un-ship without
  re-parking the service and reverting the signal-merge code.

---

## 3. Comparative Summary

| Option | Code Changes | Cost | Info Gain | Reversibility | Verdict |
|--------|-------------|------|-----------|---------------|---------|
| different_horizon | YAML only | LOW | LOW-MED | HIGH | **SELECTED** |
| classification_head | loader + metrics | MED | MEDIUM | MEDIUM | Second choice |
| xgboost_control | new arch registry | HIGH | HIGH | MEDIUM | Defer to V2 |
| cross_sectional | pipeline rewrite | HIGH | HIGH | LOW | Defer to V2 |
| sentiment_filter | service + merge | HIGH | MEDIUM | LOW | Defer per MLCL-V2-01 |

---

## Decision: different_horizon

The `different_horizon` experiment is the binding selection for Plan 05-02.

---

## 4. Rationale

The `different_horizon` option dominates on three axes simultaneously: lowest
implementation cost (pure YAML edit, verified by RESEARCH.md to be correct and
sufficient), highest reversibility (delete YAML = complete unship), and sufficient
information gain for the stated MLCL-02 purpose.

The MLCL-02 requirement is not "find edge" — it is "run exactly one experiment through
the harness and commit a binding result." A confirmed negative result (NO_EDGE_FOUND or
INSUFFICIENT_DATA with infrastructure gap documented) is explicitly valid per the plan's
own success criteria. Given the V0 finding was chance-level at horizon=5, sweeping
horizons 3/5/7/10 answers the question: "is horizon a tunable lever for this model on
these symbols?" If the answer is no, the Phase 5 result is a clean, well-evidenced
negative that informs the V2 architecture decision.

The second-best option (classification_head) has genuine diagnostic value but requires
hours of integration work touching Phase 3's locked schema — disproportionate for a
cleanup phase with a single-plan ML budget. The three higher-cost options (xgboost,
cross_sectional, sentiment) are correctly deferred to V2 where their implementation
cost can be properly planned.

The decision aligns with the Phase 5 "cost, risk, expected info gain" framework: min
cost, min risk, acceptable info gain.

---

## 5. Implementation Notes (Task 2 Actions)

- Create `services/tournament-harness/app/config/t0_1_x_experiment.yaml`.
- `tournament_id: "t0_1_x_horizon_sweep"` — slug derived from experiment name.
- `seed: 42` for reproducibility per harness convention.
- `symbols: [SOLUSDT, BNBUSDT, ADAUSDT]` — the full v1 validated set.
- `intervals: ["5m"]` — same as example config; 5m is the interval at which klines
  are ingested by the live market-data-service.
- `target_modes: ["log_returns"]` — V0 result used `price`-based R² (leakage vector).
  Post-fix evaluation is log-return only. Dropping `price` keeps the grid clean.
- **GRU only** — drop lstm, transformer, tcn to stay within the `max_experiments: 100`
  hard cap. GRU is the V0 architecture; testing it at multiple horizons answers the V0
  follow-up question directly. Grid math: 4 horizons × 3 symbols × 1 target_mode ×
  (units×dropout×lr×batch combinations) = must stay ≤ 100.
- Minimal HP grid: `units: [[64]]`, `dropout: [0.2]`, `lr: [0.001]`, `batch: [32]`,
  `lookback: [60]`, `horizon: [3, 5, 7, 10]`.
- `max_experiments: 100` hard cap.
- After YAML is authored, attempt to launch the tournament via docker compose. If the
  tournament harness infrastructure is unavailable (daemon not running, image build
  failure, OOM, training crash), write `decision_note.md` with terminal verdict
  `INSUFFICIENT_DATA` per plan Task 2(F) — this is a valid Phase 5 outcome.
- The `leaderboard_row.md` and `decision_note.md` files go into
  `.planning/evidence/t0_1_x/` regardless of whether the tournament ran or not.

---

## 6. What Is Explicitly NOT Being Shipped

**classification_head:** Deferred. Requires new `target_mode` enum in tournament_loader
and new metric mapping in metrics_bridge. Recommended as first follow-up if
`different_horizon` confirms the negative result — it tests a strictly cheaper target.
Disposition: V2 candidate, plan not filed yet.

**xgboost_control:** Deferred. Strong sanity check but high engineering risk (new arch
registry, new Docker dependency, potential scikit-learn/TF conflict). Disposition:
V2 scope — file a dedicated plan when the harness has stabilized post-Phase 5 cleanup.

**cross_sectional_features:** Deferred. Highest potential information gain but requires
multi-symbol input pipeline rewrite. Disposition: V2 or later, requires a dedicated
planning phase.

**sentiment_filter:** Deferred per CLAUDE.md project rule (`ENABLE_SENTIMENT_ANALYSIS=
false`) and REQUIREMENTS.md MLCL-V2-01 (sentiment integration explicitly deferred to
v2). Disposition: do not re-visit in Phase 5; open MLCL-V2-01 planning when the V2
phase launches.
