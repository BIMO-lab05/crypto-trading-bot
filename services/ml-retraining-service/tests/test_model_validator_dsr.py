"""
Tests for the Deflated-Sharpe-Ratio gate in ``ModelValidator``.

The gate is configured via ``settings.retrain_min_dsr``:

- ``0.95`` (default, SEV-6 fix 2026-08): a real gate, ON out of the box.
  ``new_metrics['test_dsr']`` must clear it for ``is_valid`` to be True.
  ``0.95`` corresponds to the 5% significance level (Bailey & López de
  Prado 2014). Under the current "no measured edge" reality this freezes
  deployment — that is the point: no model deploys without significant
  DSR evidence.
- ``None``: deliberate operator override — DSR is recorded
  informationally and never blocks a deployment.

DSR can also be missing (older artifacts) or NaN (degenerate test set).
While the gate is enabled those cases FAIL CLOSED (passed=False, reason
'metric unavailable') — matching edge_lab gate2 semantics. With the gate
disabled (None) they are informational only.
"""

from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from app.core.model_validator import ModelValidator


def _validator_with_min_dsr(threshold):
    """Return a ModelValidator whose retrain_min_dsr is the given value."""
    v = ModelValidator()
    # patch only the one knob we care about
    v.settings.retrain_min_dsr = threshold
    return v


def _baseline_new_metrics(**overrides):
    """Strong-enough new metrics so the legacy R²/loss/MAE checks all pass."""
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
# First-model branch (current_metrics is None) — exercises the early return
# ---------------------------------------------------------------------------


class TestDSRGateFirstModel:
    def test_default_threshold_none_does_not_block(self):
        v = _validator_with_min_dsr(None)
        result = v.validate_model(
            new_metrics=_baseline_new_metrics(test_dsr=0.10),  # very low
            current_metrics=None,
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is True
        assert result["should_deploy"] is True
        # DSR is recorded with passed=None ("not gating")
        assert result["validation_checks"]["dsr"]["passed"] is None
        assert result["validation_checks"]["dsr"]["value"] == 0.10
        # And surfaced in new_metrics
        assert result["new_metrics"]["dsr"] == 0.10

    def test_threshold_set_dsr_clears_passes(self):
        v = _validator_with_min_dsr(0.50)
        result = v.validate_model(
            new_metrics=_baseline_new_metrics(test_dsr=0.99),
            current_metrics=None,
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is True
        assert result["should_deploy"] is True
        assert result["validation_checks"]["dsr"]["passed"] is True

    def test_threshold_set_dsr_fails_blocks(self):
        v = _validator_with_min_dsr(0.95)
        result = v.validate_model(
            new_metrics=_baseline_new_metrics(test_dsr=0.10),
            current_metrics=None,
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is False
        assert result["should_deploy"] is False
        assert result["validation_checks"]["dsr"]["passed"] is False

    def test_dsr_missing_with_threshold_fails_closed(self):
        # SEV-6: gate enabled + no test_dsr at all → FAIL CLOSED.
        v = _validator_with_min_dsr(0.95)
        result = v.validate_model(
            new_metrics=_baseline_new_metrics(),  # no test_dsr key
            current_metrics=None,
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is False
        assert result["should_deploy"] is False
        assert result["validation_checks"]["dsr"]["passed"] is False
        assert "metric unavailable" in result["validation_checks"]["dsr"]["note"]

    def test_dsr_nan_with_threshold_fails_closed(self):
        # SEV-6: degenerate test set (zero-variance returns) → NaN DSR.
        # Gate enabled ⇒ FAIL CLOSED, never a silent pass.
        v = _validator_with_min_dsr(0.95)
        result = v.validate_model(
            new_metrics=_baseline_new_metrics(test_dsr=float("nan")),
            current_metrics=None,
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is False
        assert result["should_deploy"] is False
        assert result["validation_checks"]["dsr"]["passed"] is False
        assert "metric unavailable" in result["validation_checks"]["dsr"]["note"]
        # NaN survives into new_metrics for the report
        assert math.isnan(result["new_metrics"]["dsr"])


# ---------------------------------------------------------------------------
# With-current-model branch — exercises the full validation path
# ---------------------------------------------------------------------------


class TestDSRGateWithCurrentModel:
    def test_default_threshold_none_does_not_block_full_path(self):
        v = _validator_with_min_dsr(None)
        # New model improves R² over current; DSR is informational.
        result = v.validate_model(
            new_metrics=_baseline_new_metrics(test_dsr=-0.5),  # negative DSR
            current_metrics={
                "val_r2": 0.85,
                "val_loss": 0.01,
                "val_mae": 2.0,
            },
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is True
        assert result["should_deploy"] is True
        # New metrics surface DSR even when current has no DSR yet
        assert result["new_metrics"]["dsr"] == -0.5
        assert result["current_metrics"]["dsr"] is None

    def test_threshold_set_dsr_fails_blocks_deployment(self):
        v = _validator_with_min_dsr(0.95)
        result = v.validate_model(
            new_metrics=_baseline_new_metrics(test_dsr=0.10),
            current_metrics={
                "val_r2": 0.85,
                "val_loss": 0.01,
                "val_mae": 2.0,
                "test_dsr": 0.05,  # current also fails — consistent reality
            },
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is False
        # Even with R² improvement, gate failure blocks deployment
        assert result["should_deploy"] is False
        assert result["current_metrics"]["dsr"] == 0.05


# ---------------------------------------------------------------------------
# Settings default — SEV-6 (2026-08): the gate must be ON out of the box
# ---------------------------------------------------------------------------


class TestSettingsDefault:
    def test_retrain_min_dsr_default_is_095(self):
        # SEV-6 fix: the pydantic default is 0.95 so the DSR gate binds
        # by default (fail-open default was the defect). Disabling the
        # gate (None) is a deliberate operator override, not the default.
        from app.config.settings import RetrainingSettings

        # Use a fresh instance bypassing any cached env/file overrides.
        with patch.dict("os.environ", {}, clear=True):
            s = RetrainingSettings()
        assert s.retrain_min_dsr == 0.95


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
