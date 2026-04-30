"""
Tests for the eval-arrays persistence path on ``ModelTrainer.save_model``.

When ``train_model`` runs evaluation-time CPCV it produces a triple
``{actual_prices, pred_prices, last_close}`` for the held-out test set
(see ``_calculate_cpcv_metrics``). ``save_model`` persists that triple
as ``eval_arrays.npz`` so risk-metrics-service can re-run CPCV / DSR
later without retraining the GRU.

This is a regression hook: if anyone breaks the npz path they will see
this test fail with a clear message instead of discovering it months
from now when someone tries to re-evaluate an old artifact.

These tests don't need tensorflow — ``save_model`` only calls
``model.save(path)`` and we mock the model.
"""

from __future__ import annotations

import pickle
from unittest.mock import MagicMock

import pytest

pytest.importorskip("numpy")
pytest.importorskip("sklearn")

import numpy as np  # noqa: E402

# tensorflow is required to import ModelTrainer (it's a module-level
# import). Skip the whole file if TF is not in this environment, the
# same convention test_model_trainer.py uses.
pytest.importorskip("tensorflow", reason="TF required to import ModelTrainer")

from sklearn.preprocessing import MinMaxScaler  # noqa: E402

from app.core.model_trainer import ModelTrainer  # noqa: E402


def _build_metadata():
    return {
        "version": "v2026-04-30_12-00",
        "symbol": "SOLUSDT",
        "interval": "60",
    }


def _save_with(eval_arrays, tmp_path):
    trainer = ModelTrainer()
    fake_model = MagicMock()
    fake_model.save = MagicMock()
    return trainer.save_model(
        model=fake_model,
        metadata=_build_metadata(),
        train_metrics={"train_r2": 0.99},
        val_metrics={"val_r2": 0.95, "val_loss": 0.01, "val_mae": 1.0},
        test_metrics={"test_r2": 0.93, "test_dsr": 0.05},
        scaler_x=MinMaxScaler(),
        scaler_y=MinMaxScaler(),
        output_dir=str(tmp_path),
        eval_arrays=eval_arrays,
    )


class TestEvalArraysPersistence:
    def test_eval_arrays_written_to_npz(self, tmp_path):
        eval_arrays = {
            "actual_prices": np.array([100.0, 101.0, 99.5]),
            "pred_prices": np.array([100.5, 100.8, 99.7]),
            "last_close": np.array([100.0, 100.5, 100.0]),
        }

        paths = _save_with(eval_arrays, tmp_path)

        assert "eval_arrays_path" in paths
        assert paths["eval_arrays_path"].endswith("eval_arrays.npz")

        loaded = np.load(paths["eval_arrays_path"])
        assert set(loaded.files) == {"actual_prices", "pred_prices", "last_close"}
        np.testing.assert_allclose(loaded["actual_prices"], eval_arrays["actual_prices"])
        np.testing.assert_allclose(loaded["pred_prices"], eval_arrays["pred_prices"])
        np.testing.assert_allclose(loaded["last_close"], eval_arrays["last_close"])

    def test_eval_arrays_omitted_when_not_provided(self, tmp_path):
        # Backwards-compat: callers that don't pass eval_arrays still get a
        # working save_model and no stray npz file.
        paths = _save_with(None, tmp_path)
        assert "eval_arrays_path" not in paths
        assert not (tmp_path / "eval_arrays.npz").exists()

    def test_legacy_artifact_contract_unchanged(self, tmp_path):
        # The four legacy artifacts (model.h5, metadata.json, metrics.json,
        # scalers.pkl) must still be produced regardless of eval_arrays.
        # This is the same contract test_model_trainer.py locks down for
        # commit ecdb29d — duplicated here so a partial test run still
        # catches a regression.
        paths = _save_with(None, tmp_path)
        for key in ("model_path", "metadata_path", "metrics_path", "scalers_path"):
            assert key in paths
        assert (tmp_path / "scalers.pkl").exists()

        with open(paths["scalers_path"], "rb") as f:
            payload = pickle.load(f)
        assert set(payload.keys()) == {"price_scaler", "feature_scaler"}


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
