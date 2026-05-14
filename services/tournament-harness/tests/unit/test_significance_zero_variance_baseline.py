"""Pin the zero-variance-baseline contract for the Phase-04 significance pipeline.

Plan 04-10 closes Gap A from 04-08-SUMMARY: PSR over the D-04 persistence
baseline (np.zeros_like(actual_log_ret)) returns ``nan`` because
``std(zeros, ddof=1) == 0`` and the canonical PSR docstring (sharpe_metrics.py
lines 170-172) is explicit about that contract:

    Returns NaN if returns has < 2 samples or zero variance.

The subtractive lift ``ens_sharpe - base_sharpe`` then propagates ``nan``
through ``win_gate.evaluate_win_gate``, which records
``sharpe_lift_non_positive`` for every symbol and blocks all wins.

Option A from the plan (chosen): a module-private helper
``_zero_safe_baseline_sharpe`` short-circuits the baseline-Sharpe computation
to ``0.0`` when ``np.std(arr, ddof=1) < 1e-12`` (T-04-10-01 mitigation). The
candidate-side PSR is NEVER bypassed — a genuinely flat candidate still falls
through the win-gate's ``not (sharpe_lift > 0)`` check.

These tests run only in the harness Docker image (PYTHONPATH=/app:/opt/ml_retraining)
where the canonical PSR chain resolves. On host pytest they self-skip,
mirroring the existing pattern in ``test_runner_metrics_bridge.py`` and the
integration-layer e2e suite.
"""

from __future__ import annotations

import numpy as np
import pytest

# Skip on host where the canonical PSR chain does not resolve. The harness
# image bind-mounts /opt/ml_retraining and the PYTHONPATH merges both trees
# into one PEP-420 ``app`` namespace package — only there is
# ``app.sharpe_metrics`` importable. Mirrors test_runner_metrics_bridge.py
# line 33 (``pytest.importorskip("app.core.returns_metrics")``).
pytest.importorskip(
    "app.sharpe_metrics",
    reason="Requires canonical PSR chain — run inside tournament-harness container "
    "(PYTHONPATH=/app:/opt/ml_retraining).",
)

from app.pr.open_pr import _zero_safe_baseline_sharpe  # noqa: E402
from app.runner.metrics_bridge import probabilistic_sharpe_ratio  # noqa: E402
from app.significance.win_gate import evaluate_win_gate  # noqa: E402


def test_zero_safe_baseline_sharpe_returns_zero_on_zeros() -> None:
    """An all-zero baseline ⇒ 0.0 Sharpe (not nan). The load-bearing assertion.

    Plan 04-10 Task 1: rationale captured in the helper docstring — a constant
    series has no risk-adjusted return signal, so its Sharpe is defined as 0.0.
    """
    result = _zero_safe_baseline_sharpe(np.zeros(100))
    assert result == 0.0
    assert np.isfinite(result)


def test_zero_safe_baseline_sharpe_returns_psr_on_nonzero() -> None:
    """The helper is a guard, NOT a semantic shortcut.

    T-04-10-01 mitigation: on a non-zero baseline (variance > 1e-12) the
    helper MUST return the same value as a direct call to the canonical
    ``probabilistic_sharpe_ratio``. A future PR that altered the helper to
    return a different value on non-zero inputs would trip this test.
    """
    rng = np.random.default_rng(seed=42)
    r = rng.normal(0.001, 0.01, 200)
    expected = float(probabilistic_sharpe_ratio(r, benchmark_sr=0.0))
    actual = _zero_safe_baseline_sharpe(r)
    assert actual == expected
    assert np.isfinite(actual)


def test_zero_safe_baseline_sharpe_handles_near_zero_variance() -> None:
    """Near-zero variance (< 1e-12) triggers the same short-circuit path.

    Floating-point arithmetic on the persistence baseline can produce a
    series of exactly 1e-15 (or similar epsilon) instead of strict zeros if
    upstream code subtracts cancelling quantities. The helper must catch
    that case too — ``std == 0.0`` strict equality would leak nan.
    """
    result = _zero_safe_baseline_sharpe(np.full(50, 1e-15))
    assert result == 0.0
    assert np.isfinite(result)


def test_sharpe_lift_finite_with_persistence_baseline() -> None:
    """End-to-end lift over the D-04 persistence baseline must be finite.

    This is the integration-style assertion of the Gap A fix: with a
    realistic candidate log-return series and the zeros baseline, the lift
    ``cand_psr - base_psr`` must be finite (not nan) and must equal the
    candidate's own PSR (because base_sharpe == 0.0 by definition).
    """
    rng = np.random.default_rng(seed=42)
    candidate = rng.normal(0.001, 0.01, 50)
    baseline = np.zeros(50)
    cand_sharpe = float(probabilistic_sharpe_ratio(candidate, benchmark_sr=0.0))
    base_sharpe = _zero_safe_baseline_sharpe(baseline)
    lift = cand_sharpe - base_sharpe
    assert np.isfinite(lift)
    assert lift == cand_sharpe  # base_sharpe == 0.0 by definition.


def test_existing_failure_reason_semantics_preserved() -> None:
    """The fix MUST NOT mask a genuinely flat candidate.

    T-04-10-01 second invariant: when both candidate and baseline are flat,
    ``cand_psr = nan`` (canonical PSR on zero-variance), the helper still
    returns ``base_sharpe = 0.0``, so ``lift = nan - 0 = nan``.
    ``win_gate.evaluate_win_gate`` evaluates ``not (lift > 0)`` which is
    True for nan, so the symbol still fails with reason
    ``sharpe_lift_non_positive`` — exactly the pre-fix behavior for a
    no-edge candidate.
    """
    cand_flat = np.zeros(50)
    base_flat = np.zeros(50)
    cand_sharpe = float(probabilistic_sharpe_ratio(cand_flat, benchmark_sr=0.0))
    base_sharpe = _zero_safe_baseline_sharpe(base_flat)
    lift = cand_sharpe - base_sharpe  # nan - 0.0 = nan

    one_symbol = {
        "BTCUSDT": {
            "n_members": 3,
            "sharpe_pvalue": 0.01,  # passes
            "dir_acc_pvalue": 0.01,  # passes
            "sharpe_lift": lift,
            "dir_acc_lift": 0.05,  # passes
            "n_oos_bars": 50,
            "block_size": 7,
            "n_resamples": 10_000,
            "bootstrap_seed": 0,
        }
    }
    out = evaluate_win_gate(one_symbol)
    assert out["n_winning_symbols"] == 0
    reasons = out["per_symbol"]["BTCUSDT"]["gate_failure_reasons"]
    assert "sharpe_lift_non_positive" in reasons
