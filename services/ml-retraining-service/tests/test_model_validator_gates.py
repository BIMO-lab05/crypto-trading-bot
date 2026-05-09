"""
Tests for the T0.1 pre-flight gates in ``ModelValidator`` — chunk 3.

The two new gates (``retrain_min_r2_returns`` + ``retrain_min_dir_acc``)
share their plumbing with ``retrain_min_dsr`` via the shared
``_check_optional_gate`` helper. Existing DSR tests
(``test_model_validator_dsr.py``) cover the gate state machine
exhaustively; this file's job is to verify:

1. The two new settings default to ``None`` (informational, no block).
2. The two new gates flow into ``is_valid`` when configured.
3. The new ``r2_returns`` / ``dir_acc_corrected`` keys appear in
   ``new_metrics`` / ``current_metrics`` of the validation result.
4. The shared helper produces the right ``validation_checks`` shape for
   both new gates (parametrised against the existing DSR cases).

The DSR refactor in chunk 3 must not regress the 8 tests in
``test_model_validator_dsr.py`` — that file is kept untouched as the
regression suite.
"""

from __future__ import annotations

import math
import os
from unittest.mock import patch

import pytest

from app.config.settings import RetrainingSettings
from app.core.model_validator import ModelValidator


# ---------------------------------------------------------------------------
# Settings defaults — keep gates off out of the box per V0 reality
# ---------------------------------------------------------------------------


class TestNewGateDefaults:
    def test_retrain_min_r2_returns_default_is_none(self):
        with patch.dict(os.environ, {}, clear=True):
            s = RetrainingSettings()
        assert s.retrain_min_r2_returns is None

    def test_retrain_min_dir_acc_default_is_none(self):
        with patch.dict(os.environ, {}, clear=True):
            s = RetrainingSettings()
        assert s.retrain_min_dir_acc is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validator_with_thresholds(*, dsr=None, r2_returns=None, dir_acc=None):
    v = ModelValidator()
    v.settings.retrain_min_dsr = dsr
    v.settings.retrain_min_r2_returns = r2_returns
    v.settings.retrain_min_dir_acc = dir_acc
    return v


def _strong_baseline(**overrides):
    """Strong-enough metrics so legacy R²/loss/MAE checks all pass."""
    base = {
        "val_r2": 0.95,
        "val_loss": 0.005,
        "val_mae": 1.0,
        "test_r2": 0.95,
        "test_loss": 0.005,
        "test_mae": 1.0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# r2_returns gate
# ---------------------------------------------------------------------------


class TestR2ReturnsGate:
    def test_default_does_not_block(self):
        v = _validator_with_thresholds()
        result = v.validate_model(
            new_metrics=_strong_baseline(test_r2_returns=-0.5),
            current_metrics=None,
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is True
        # Informational record present
        assert result["validation_checks"]["r2_returns"]["passed"] is None
        assert result["validation_checks"]["r2_returns"]["value"] == -0.5
        # Surfaced in new_metrics output
        assert result["new_metrics"]["r2_returns"] == -0.5

    def test_threshold_set_clears_passes(self):
        v = _validator_with_thresholds(r2_returns=0.0)
        result = v.validate_model(
            new_metrics=_strong_baseline(test_r2_returns=0.10),
            current_metrics=None,
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is True
        assert result["validation_checks"]["r2_returns"]["passed"] is True

    def test_threshold_set_fails_blocks(self):
        v = _validator_with_thresholds(r2_returns=0.0)
        result = v.validate_model(
            new_metrics=_strong_baseline(test_r2_returns=-0.1),
            current_metrics=None,
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is False
        assert result["should_deploy"] is False
        assert result["validation_checks"]["r2_returns"]["passed"] is False

    def test_missing_value_does_not_block(self):
        v = _validator_with_thresholds(r2_returns=0.0)
        result = v.validate_model(
            new_metrics=_strong_baseline(),  # no test_r2_returns key
            current_metrics=None,
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is True
        assert "R²(returns) unavailable" in result["validation_checks"]["r2_returns"]["note"]

    def test_nan_value_does_not_block(self):
        v = _validator_with_thresholds(r2_returns=0.0)
        result = v.validate_model(
            new_metrics=_strong_baseline(test_r2_returns=float("nan")),
            current_metrics=None,
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is True
        assert math.isnan(result["new_metrics"]["r2_returns"])


# ---------------------------------------------------------------------------
# dir_acc gate
# ---------------------------------------------------------------------------


class TestDirAccGate:
    def test_default_does_not_block(self):
        v = _validator_with_thresholds()
        result = v.validate_model(
            new_metrics=_strong_baseline(test_dir_acc_corrected=0.50),
            current_metrics=None,
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is True
        assert result["validation_checks"]["dir_acc_corrected"]["passed"] is None
        assert result["new_metrics"]["dir_acc_corrected"] == 0.50

    def test_threshold_set_clears_passes(self):
        v = _validator_with_thresholds(dir_acc=0.55)
        result = v.validate_model(
            new_metrics=_strong_baseline(test_dir_acc_corrected=0.62),
            current_metrics=None,
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is True
        assert result["validation_checks"]["dir_acc_corrected"]["passed"] is True

    def test_threshold_set_fails_blocks(self):
        v = _validator_with_thresholds(dir_acc=0.55)
        result = v.validate_model(
            new_metrics=_strong_baseline(test_dir_acc_corrected=0.50),
            current_metrics=None,
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is False
        assert result["should_deploy"] is False
        assert result["validation_checks"]["dir_acc_corrected"]["passed"] is False


# ---------------------------------------------------------------------------
# All three gates together — mirrors the four-gate composition in
# T0.1-gru-rebuild-design.md §4 (minus the operator-driven forward-paper
# Sharpe gate which lives outside the validator).
# ---------------------------------------------------------------------------


class TestAllGatesComposition:
    def test_all_gates_must_pass_for_is_valid(self):
        v = _validator_with_thresholds(dsr=0.95, r2_returns=0.0, dir_acc=0.55)
        # DSR clears, dir_acc clears, but r2_returns fails → blocked.
        result = v.validate_model(
            new_metrics=_strong_baseline(
                test_dsr=0.97,
                test_r2_returns=-0.1,
                test_dir_acc_corrected=0.62,
            ),
            current_metrics=None,
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is False
        assert result["validation_checks"]["dsr"]["passed"] is True
        assert result["validation_checks"]["r2_returns"]["passed"] is False
        assert result["validation_checks"]["dir_acc_corrected"]["passed"] is True

    def test_all_three_gate_keys_in_checks_when_disabled(self):
        # Even with everything off, all three records still appear so
        # operators can see the values without enabling gates.
        v = _validator_with_thresholds()
        result = v.validate_model(
            new_metrics=_strong_baseline(
                test_dsr=0.05,
                test_r2_returns=-0.3,
                test_dir_acc_corrected=0.50,
            ),
            current_metrics=None,
            symbol="SOLUSDT",
        )
        for key in ("dsr", "r2_returns", "dir_acc_corrected"):
            assert key in result["validation_checks"]
            assert result["validation_checks"][key]["passed"] is None

    def test_with_current_model_branch_surfaces_all_keys(self):
        v = _validator_with_thresholds()
        result = v.validate_model(
            new_metrics=_strong_baseline(
                test_dsr=0.10,
                test_r2_returns=0.05,
                test_dir_acc_corrected=0.51,
            ),
            current_metrics={
                "val_r2": 0.85,
                "val_loss": 0.01,
                "val_mae": 2.0,
                "test_dsr": 0.05,
                "test_r2_returns": -0.2,
                "test_dir_acc_corrected": 0.50,
            },
            symbol="SOLUSDT",
        )
        for key in ("dsr", "r2_returns", "dir_acc_corrected"):
            assert key in result["new_metrics"]
            assert key in result["current_metrics"]


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
