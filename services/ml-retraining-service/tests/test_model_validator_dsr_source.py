"""
Tests for WHICH DSR variant the ``ModelValidator`` deploy gate consumes.

Decision of record (SEV-5, 2026-08): the honest-N ``test_cpcv_dsr``
(num_trials = max(valid paths, total CPCV path count)) is the
decision-of-record variant, and the fail-closed 0.95 deploy gate must
run on it — not on the legacy under-deflated ``test_dsr``
(num_trials = valid-path count). The legacy key remains a fallback only
for older artifacts that predate the honest-N key.

Companion suites: ``test_model_validator_dsr.py`` (gate state machine,
legacy-key artifacts) and ``test_model_validator_gates.py`` (T0.1
gates). Both are kept untouched as regression suites.
"""

from __future__ import annotations

import pytest

from app.core.model_validator import ModelValidator


def _validator_with_min_dsr(threshold):
    v = ModelValidator()
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


class TestDSRGateSource:
    def test_gate_prefers_honest_cpcv_dsr_over_legacy(self):
        # The divergence case: degenerate paths dropped, so the legacy
        # variant clears 0.95 while the honest-N variant does not. The
        # gate must run on the honest number and REJECT.
        v = _validator_with_min_dsr(0.95)
        result = v.validate_model(
            new_metrics=_baseline_new_metrics(test_dsr=0.99, test_cpcv_dsr=0.10),
            current_metrics=None,
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is False
        assert result["should_deploy"] is False
        assert result["validation_checks"]["dsr"]["passed"] is False
        assert result["validation_checks"]["dsr"]["value"] == 0.10
        assert result["validation_checks"]["dsr"]["source"] == "test_cpcv_dsr"

    def test_gate_falls_back_to_legacy_dsr_when_cpcv_key_absent(self):
        # Older artifacts never recorded test_cpcv_dsr; the legacy key
        # still gates (fallback), recorded as such.
        v = _validator_with_min_dsr(0.95)
        result = v.validate_model(
            new_metrics=_baseline_new_metrics(test_dsr=0.99),
            current_metrics=None,
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is True
        assert result["validation_checks"]["dsr"]["passed"] is True
        assert result["validation_checks"]["dsr"]["value"] == 0.99
        assert result["validation_checks"]["dsr"]["source"] == "test_dsr"

    def test_nan_cpcv_dsr_fails_closed_without_legacy_fallback(self):
        # A present-but-NaN honest-N DSR must not silently fall back to
        # a valid legacy value — unmeasurable honest DSR => REJECT.
        v = _validator_with_min_dsr(0.95)
        result = v.validate_model(
            new_metrics=_baseline_new_metrics(
                test_dsr=0.99, test_cpcv_dsr=float("nan")
            ),
            current_metrics=None,
            symbol="SOLUSDT",
        )
        assert result["is_valid"] is False
        assert result["should_deploy"] is False
        assert result["validation_checks"]["dsr"]["passed"] is False
        assert "metric unavailable" in result["validation_checks"]["dsr"]["note"]

    def test_verdict_reports_deflation_components(self):
        # Decision of record: verdict artifacts report the components
        # (ledger_count, n_paths, num_trials_used) alongside the DSR.
        v = _validator_with_min_dsr(0.95)
        result = v.validate_model(
            new_metrics=_baseline_new_metrics(
                test_dsr=0.97,
                test_cpcv_dsr=0.96,
                test_cpcv_n_paths=43,
                test_cpcv_num_trials_used=45,
            ),
            current_metrics=None,
            symbol="SOLUSDT",
        )
        dsr_check = result["validation_checks"]["dsr"]
        assert dsr_check["passed"] is True
        assert dsr_check["ledger_count"] is None  # no trial ledger here
        assert dsr_check["n_paths"] == 43
        assert dsr_check["num_trials_used"] == 45

    def test_full_path_current_metrics_prefer_honest_variant(self):
        # Informational current_metrics.dsr uses the same preference so
        # the report never compares honest-N new against legacy current.
        v = _validator_with_min_dsr(None)
        result = v.validate_model(
            new_metrics=_baseline_new_metrics(test_dsr=0.5, test_cpcv_dsr=0.4),
            current_metrics={
                "val_r2": 0.85,
                "val_loss": 0.01,
                "val_mae": 2.0,
                "test_dsr": 0.30,
                "test_cpcv_dsr": 0.20,
            },
            symbol="SOLUSDT",
        )
        assert result["new_metrics"]["dsr"] == 0.4
        assert result["current_metrics"]["dsr"] == 0.20


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
