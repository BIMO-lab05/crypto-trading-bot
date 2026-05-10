---
phase: 04-tournament-significance-auto-pr
plan: 02
subsystem: tournament-harness/significance
tags: [bootstrap, statistical-significance, win-gate, persistence-baseline, TDD, tournament]

requires:
  - 04-01 ensemble.aggregate_log_returns (consumes its output as paired_diffs)
provides:
  - persistence_log_returns(N) → np.zeros(N)
  - derive_seed(tournament_id, symbol) → CD-07 31-bit blake2b seed
  - stationary_block_bootstrap_pvalue(...) → {observed_metric, p_value, n_oos_bars, block_size, n_resamples}
  - evaluate_win_gate(per_symbol_significance) → {per_symbol, n_winning_symbols}
affects:
  - 04-03 (PR-body / significance-runner): consumes the four functions above; wires Sharpe + dir_acc_corrected metric_fns from compute_returns_metrics
  - 04-04 (reproduce subcommand): re-derives the same seed + p_value via derive_seed

tech-stack:
  added: []
  patterns:
    - pure-numpy / pure-Python kernels with no I/O (mirror of cpcv.py / ingest.py shape)
    - Politis–Romano stationary block bootstrap with geometric block lengths
    - Davison & Hinkley §4.2 additive smoothing — p > 0 always
    - blake2b-derived 31-bit seed for cross-process reproducibility
    - module-level threshold constants (P_THRESHOLD, MIN_MEMBERS) as code-review tripwires
    - centering-based H0 implementation (algebraically equivalent to "count <= 0", generalises to non-mean metrics)
    - pytest "slow" marker registered in pyproject.toml so the n=10_000 production-value bootstrap test is opt-in

key-files:
  created:
    - services/tournament-harness/app/significance/baseline.py
    - services/tournament-harness/app/significance/bootstrap.py
    - services/tournament-harness/app/significance/win_gate.py
    - services/tournament-harness/tests/unit/test_significance_baseline.py
    - services/tournament-harness/tests/unit/test_significance_bootstrap.py
    - services/tournament-harness/tests/unit/test_significance_win_gate.py
  modified:
    - pyproject.toml  # registered "slow" marker (--strict-markers compat)

decisions:
  - D-04 implementation: persistence_log_returns is a function, not a constant; preserves call-site stability for a Phase-5 production-aggregator baseline swap.
  - D-06 H0 implementation: centering (d - d.mean()) instead of literal "count(stat <= 0)". Same answer for location-equivariant metrics (mean / Sharpe / dir_acc); generalises cleanly. Documented as a docstring note in bootstrap.py.
  - CD-07 seed mask: bitmask `& 0x7FFFFFFF` ensures non-negative 31-bit values, sidestepping NumPy `default_rng` sign edge cases.
  - CD-08 ordering inside the gate: insufficient-runs reason fires first AND independently of the four-condition checks. Reasons aggregate, so a sub-3-member symbol that ALSO has bad p-values reports both — informative for the PR body.
  - Defensive defaults in win_gate: missing keys read as worst-plausible (p=1.0, lift=0.0, n_members=0). Keeps the gate resilient to partial inputs without raising KeyError; downstream still sees a populated `gate_failure_reasons`.

metrics:
  duration: ~25 min
  tasks: 2
  tests_added: 35  # 22 fast bootstrap + 3 baseline + 12 win_gate; 1 slow gated by `-m slow`
  completed: 2026-05-10

requirements:
  - TOURN-05  # bootstrap p<0.05 + lift > 0 gate machinery
---

# Phase 04 Plan 02: Significance Statistical Core — Summary

**One-liner:** Pure-numpy persistence baseline + stationary block bootstrap with additive-smoothed one-tailed p-value + four-condition per-symbol win gate, all TOURN-07-clean (no parallel metric definitions).

## What Shipped

| Component | Public API | Key invariants |
| --- | --- | --- |
| `app.significance.baseline` | `persistence_log_returns(n_oos_bars: int) -> np.ndarray` | Returns `np.zeros((n_oos_bars,), dtype=float64)`. D-04 baseline. |
| `app.significance.bootstrap` | `derive_seed(tournament_id: str, symbol: str) -> int`<br/>`stationary_block_bootstrap_pvalue(paired_diffs, *, metric_fn, n_resamples=10_000, seed, alternative="greater") -> dict` | Seed in `[0, 2**31)`. p ∈ (0, 1] always. Block size `max(2, floor(sqrt(N)))`. |
| `app.significance.win_gate` | `evaluate_win_gate(per_symbol_significance: dict) -> dict`<br/>`P_THRESHOLD = 0.05`, `MIN_MEMBERS = 3` | D-08 four-condition AND + CD-08 insufficient-runs guard. Pass-through preserves all input fields. |

## Bootstrap result-dict shape (consumer contract for 04-03)

```python
{
    "observed_metric": float,   # metric_fn(paired_diffs)
    "p_value": float,           # additive-smoothed; (1+count)/(n+1); always > 0
    "n_oos_bars": int,          # len(paired_diffs)
    "block_size": int,          # max(2, floor(sqrt(n_oos_bars)))
    "n_resamples": int,         # echoes input n_resamples
}
```

When 04-03 wires bootstrap into the per-symbol pipeline, it computes Sharpe and `dir_acc_corrected` separately — running `stationary_block_bootstrap_pvalue` twice per symbol — then merges into the D-14 schema as:

```python
per_symbol_significance[symbol] = {
    "sharpe_pvalue":   sharpe_result["p_value"],
    "sharpe_lift":     sharpe_result["observed_metric"]   - baseline_sharpe,
    "dir_acc_pvalue":  dir_acc_result["p_value"],
    "dir_acc_lift":    dir_acc_result["observed_metric"]  - baseline_dir_acc,
    "n_oos_bars":      sharpe_result["n_oos_bars"],     # (== dir_acc result; same input)
    "block_size":      sharpe_result["block_size"],
    "n_resamples":     sharpe_result["n_resamples"],
    "bootstrap_seed":  derive_seed(tournament_id, symbol),  # D-14 stamp
    "n_members":       len(top_n_runs_for_symbol),
}
```

## Win-gate output shape (consumer contract for 04-03)

```python
{
    "per_symbol": {
        "BTCUSDT": {
            **input_fields,                # bootstrap_seed, n_oos_bars, block_size, n_resamples, … all preserved
            "win_gate_passed": bool,
            "gate_failure_reasons": list[str],   # empty if passed
        },
        ...
    },
    "n_winning_symbols": int,
}
```

`gate_failure_reasons` strings (stable for downstream string matching):
- `"insufficient_runs"` — CD-08 (n_members < 3)
- `"sharpe_pvalue>=0.05"` — D-08 condition 1
- `"dir_acc_pvalue>=0.05"` — D-08 condition 2
- `"sharpe_lift_non_positive"` — D-08 condition 3
- `"dir_acc_lift_non_positive"` — D-08 condition 4

## `metric_fn` callable contract — concrete example for 04-03

When 04-03 wires this in, the harness imports the canonical metric helpers from `app.runner.metrics_bridge` (which itself re-exports from `services/ml-retraining-service/app/core/returns_metrics.py` / `sharpe_metrics.py`). NEVER redefine them inline (TOURN-07).

```python
# 04-03 pseudo-wiring sketch — DO NOT add to bootstrap.py / win_gate.py.
from app.runner.metrics_bridge import compute_all_metrics
from app.significance.bootstrap import (
    derive_seed,
    stationary_block_bootstrap_pvalue,
)
from app.significance.win_gate import evaluate_win_gate

def _sharpe_metric(returns: np.ndarray) -> float:
    # mean / std with ddof=1; +tiny floor protects against zero-variance resamples.
    mu = float(returns.mean())
    sigma = float(returns.std(ddof=1)) + 1e-12
    return mu / sigma

def _dir_acc_metric(returns: np.ndarray) -> float:
    # On the centered/resampled diffs, "directional accuracy" reduces to the
    # share of bars where the resampled diff is positive — equivalent in
    # signal to compute_all_metrics(...)["dir_acc_corrected"] on the
    # ensemble vs. baseline pair, post-centering.
    return float((returns > 0).mean())

per_symbol_significance: dict = {}
for symbol, top_runs in selected_top_n.items():
    paired_diffs = aggregate_log_returns([r["log_returns"] for r in top_runs])
    seed = derive_seed(tournament_id, symbol)
    sharpe_result = stationary_block_bootstrap_pvalue(
        paired_diffs, metric_fn=_sharpe_metric, n_resamples=10_000, seed=seed,
    )
    dir_acc_result = stationary_block_bootstrap_pvalue(
        paired_diffs, metric_fn=_dir_acc_metric, n_resamples=10_000, seed=seed,
    )
    per_symbol_significance[symbol] = {
        "sharpe_pvalue":   sharpe_result["p_value"],
        "sharpe_lift":     sharpe_result["observed_metric"],          # baseline Sharpe = 0
        "dir_acc_pvalue":  dir_acc_result["p_value"],
        "dir_acc_lift":    dir_acc_result["observed_metric"] - 0.5,   # baseline dir_acc = 0.5 under persistence
        "n_oos_bars":      sharpe_result["n_oos_bars"],
        "block_size":      sharpe_result["block_size"],
        "n_resamples":     sharpe_result["n_resamples"],
        "bootstrap_seed":  seed,
        "n_members":       len(top_runs),
    }

gate_result = evaluate_win_gate(per_symbol_significance)
```

> **Note for 04-03 planner:** the exact baseline subtraction (`baseline Sharpe = 0`, `baseline dir_acc = 0.5`) is a property of the persistence baseline (D-04). Sharpe of an all-zeros series is undefined (0/0 numerically), so 04-03 should treat it as 0 by convention. Dir-acc of "always predict zero" against any direction-having target is 0.5 in expectation. These two constants belong in the 04-03 wiring layer; this plan deliberately keeps them out of bootstrap/win_gate.

## Decisions Made

| Decision | What | Why |
| --- | --- | --- |
| Centering for H0 | `d_centered = d - d.mean()`; count resamples whose metric ≥ observed | Algebraically equivalent to D-06's "count ≤ 0" for location-equivariant metrics; generalises cleanly to Sharpe / dir_acc without a separate code path. |
| Function not constant for baseline | `persistence_log_returns(N)` not a module-level zeros array | Preserves call-site for the Phase-5 production-aggregator baseline swap (D-14 already carries `baseline: "persistence"` so a future swap doesn't need a schema rev). |
| 31-bit seed mask | `& 0x7FFFFFFF` | Non-negative + safely below NumPy `default_rng`'s upper bound; avoids sign edge cases on round-trip casts. |
| Aggregate failure reasons in win_gate | All failing conditions reported, not just the first | Lets the PR body / leaderboard explain *every* reason a symbol didn't qualify, not just the alphabetically-first. Especially useful for sub-3-member symbols that ALSO have bad p-values. |
| Defensive defaults in win_gate | Missing keys → worst-plausible | Survives partial-input edge cases without raising KeyError; partial inputs always fail with a populated `gate_failure_reasons`. |

## Deviations from Plan

### Plan-driven adjustments

**[Rule 3 - Blocking issue] Registered `slow` pytest marker in `pyproject.toml`**
- **Found during:** Task 1 GREEN run.
- **Issue:** Project pytest config has `--strict-markers`, so `@pytest.mark.slow` would error at collect time without registration.
- **Fix:** Added a single `markers = [...]` entry under `[tool.pytest.ini_options]` describing the marker.
- **Files modified:** `pyproject.toml`.
- **Commit:** `82b7dad` (the RED commit, since the marker was needed to collect the test that referenced it).

No bugs auto-fixed (Rule 1) and no missing critical functionality auto-added (Rule 2). The plan was written tightly enough that the only deviation was the strict-markers compatibility nudge above.

## TDD Gate Compliance

Both tasks followed RED → GREEN cycle:

| Task | RED commit | GREEN commit |
| --- | --- | --- |
| 1: baseline + bootstrap | `82b7dad` (test) | `6bb99ea` (feat) |
| 2: win_gate | `f1e6699` (test) | `a3537b5` (feat) |

REFACTOR phase skipped — no cleanup needed; the green implementations matched the plan template within the docstring/comment overhead.

## Verification Evidence

```text
$ PYTHONPATH=services/tournament-harness python3 -m pytest \
    services/tournament-harness/tests/unit/test_significance_baseline.py \
    services/tournament-harness/tests/unit/test_significance_bootstrap.py \
    services/tournament-harness/tests/unit/test_significance_win_gate.py \
    -q -m "not slow"
..................................                                       [100%]
34 passed

$ PYTHONPATH=services/tournament-harness python3 -m pytest \
    services/tournament-harness/tests/unit/test_significance_bootstrap.py \
    -q -m "slow"
.                                                                        [100%]
1 passed

$ grep -nE "p\s*==\s*0\b|return 0\.0$" services/tournament-harness/app/significance/bootstrap.py
(no matches — additive smoothing means p == 0 unreachable; T-04-06)

$ grep -nE "def (sharpe|directional_accuracy|deflated|compute_returns_metrics)" \
       services/tournament-harness/app/significance/baseline.py \
       services/tournament-harness/app/significance/bootstrap.py \
       services/tournament-harness/app/significance/win_gate.py
(no matches — TOURN-07 hygiene clean)

$ grep -n "blake2b" services/tournament-harness/app/significance/bootstrap.py
4:- ``derive_seed(tournament_id, symbol)`` — CD-07: blake2b-derived 31-bit seed
49:    Uses ``blake2b(f"{tid}|sig|{symbol}", digest_size=8)``; masks to 31 bits
66:    digest = hashlib.blake2b(

$ grep -n "P_THRESHOLD\|MIN_MEMBERS" services/tournament-harness/app/significance/win_gate.py
31:P_THRESHOLD: float = 0.05  # D-08
32:MIN_MEMBERS: int = 3  # CD-08
…
```

Cross-suite regression check (no impact on 04-01 outputs):

```text
$ PYTHONPATH=services/tournament-harness python3 -m pytest \
    services/tournament-harness/tests/unit/test_significance_*.py \
    -q -m "not slow"
.........................................................                [100%]
57 passed
```

## Self-Check

- [x] `services/tournament-harness/app/significance/baseline.py` — FOUND
- [x] `services/tournament-harness/app/significance/bootstrap.py` — FOUND
- [x] `services/tournament-harness/app/significance/win_gate.py` — FOUND
- [x] `services/tournament-harness/tests/unit/test_significance_baseline.py` — FOUND
- [x] `services/tournament-harness/tests/unit/test_significance_bootstrap.py` — FOUND
- [x] `services/tournament-harness/tests/unit/test_significance_win_gate.py` — FOUND
- [x] Commits `82b7dad`, `6bb99ea`, `f1e6699`, `a3537b5` — FOUND in `git log`

## Self-Check: PASSED
