"""
Tests for ``app.core.model_trainer.ModelTrainer``.

The full training loop pulls in ``tensorflow``, which is too heavy and too
slow to run in the unit-test pass. We use ``pytest.importorskip`` to
opt-out gracefully when TF is unavailable, and mock the keras model when
we do need a "trained model" placeholder.

What we cover here:
- Happy-path constructor / config invariants.
- ``prepare_features`` produces all expected indicator columns and drops
  the leading rows full of NaNs.
- ``create_sequences`` produces tensors with the documented shapes.
- ``save_model`` writes the *exact* artifact contract that the prediction
  service depends on (``scalers.pkl`` with keys
  ``{'price_scaler', 'feature_scaler'}``). Regression hook for commit
  ``ecdb29d``.
"""

from __future__ import annotations

import json
import pickle
from unittest.mock import MagicMock

import pytest

# These two are required even for the lightweight tests; the service
# already lists them in requirements.txt.
pytest.importorskip("numpy")
pytest.importorskip("pandas")
pytest.importorskip("sklearn")


# ---------------------------------------------------------------------------
# Heavy-import guard
# ---------------------------------------------------------------------------

tf = pytest.importorskip(
    "tensorflow",
    reason="tensorflow not installed in this environment",
)


from app.core.model_trainer import ModelTrainer  # noqa: E402  (after importorskip)


# ---------------------------------------------------------------------------
# Constructor / invariants
# ---------------------------------------------------------------------------

class TestModelTrainerInit:
    def test_default_architecture_matches_production(self):
        trainer = ModelTrainer()
        # These match the documented production GRU architecture and the
        # values that the prediction service expects when consuming the
        # saved model. Bumping any of these is a breaking change.
        assert trainer.sequence_length == 60
        assert trainer.prediction_horizon == 5
        assert trainer.gru_units == [128, 64]
        assert trainer.dropout_rate == 0.2

    def test_scalers_initialized(self):
        from sklearn.preprocessing import MinMaxScaler

        trainer = ModelTrainer()
        assert isinstance(trainer.scaler_x, MinMaxScaler)
        assert isinstance(trainer.scaler_y, MinMaxScaler)


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

class TestPrepareFeatures:
    def test_adds_expected_indicator_columns(self, synthetic_ohlcv):
        trainer = ModelTrainer()
        out = trainer.prepare_features(synthetic_ohlcv)

        expected_columns = {
            "returns",
            "log_returns",
            "sma_7",
            "sma_14",
            "sma_30",
            "ema_7",
            "ema_14",
            "volatility_7",
            "volatility_14",
            "rsi",
            "macd",
            "macd_signal",
            "macd_hist",
            "bb_middle",
            "bb_upper",
            "bb_lower",
            "bb_width",
            "volume_sma",
            "volume_ratio",
            "high_low_ratio",
            "momentum_7",
            "momentum_14",
        }
        missing = expected_columns - set(out.columns)
        assert not missing, f"missing indicator columns: {missing}"

    def test_drops_rows_with_nan(self, synthetic_ohlcv):
        trainer = ModelTrainer()
        out = trainer.prepare_features(synthetic_ohlcv)
        assert len(out) > 0
        assert len(out) < len(synthetic_ohlcv)
        assert out.isna().sum().sum() == 0


# ---------------------------------------------------------------------------
# Sequence creation
# ---------------------------------------------------------------------------

class TestCreateSequences:
    def test_shapes_match_config(self, synthetic_ohlcv):
        trainer = ModelTrainer()
        prepared = trainer.prepare_features(synthetic_ohlcv)
        X, y = trainer.create_sequences(prepared)

        # X: (samples, sequence_length, features)
        assert X.ndim == 3
        assert X.shape[1] == trainer.sequence_length

        # y: (samples, prediction_horizon)
        assert y.ndim == 2
        assert y.shape[1] == trainer.prediction_horizon

        # Sample counts agree
        assert X.shape[0] == y.shape[0]
        assert X.shape[0] > 0


# ---------------------------------------------------------------------------
# save_model — REGRESSION HOOK for commit ecdb29d
# ---------------------------------------------------------------------------

class TestSaveModelArtifactContract:
    """
    The prediction service (``services/ml-prediction-service/app/models/
    gru_model.py``) loads ``scalers.pkl`` as a single file containing a
    dict ``{'price_scaler': MinMaxScaler, 'feature_scaler': MinMaxScaler}``.

    Before commit ``ecdb29d`` this side wrote ``.npy`` arrays / split
    ``scaler_x.pkl`` + ``scaler_y.pkl`` files, which the prediction service
    silently ignored — retrained models never actually replaced the
    production scalers. These assertions lock the contract.
    """

    def _build_metadata(self):
        return {
            "version": "v2026-04-28_12-00",
            "symbol": "SOLUSDT",
            "interval": "60",
        }

    def test_save_model_writes_scalers_pkl_with_expected_keys(self, tmp_path):
        from sklearn.preprocessing import MinMaxScaler

        trainer = ModelTrainer()

        # Mock the keras model — we only care that ``.save()`` was invoked
        # with the model_path. No real TF graph needed.
        fake_model = MagicMock()
        fake_model.save = MagicMock()

        scaler_x = MinMaxScaler()
        scaler_y = MinMaxScaler()

        out_dir = tmp_path / "model_artifacts"

        paths = trainer.save_model(
            model=fake_model,
            metadata=self._build_metadata(),
            train_metrics={"train_r2": 0.99},
            val_metrics={"val_r2": 0.95, "val_loss": 0.01, "val_mae": 12.0},
            test_metrics={"test_r2": 0.93},
            scaler_x=scaler_x,
            scaler_y=scaler_y,
            output_dir=str(out_dir),
        )

        # 1. The scalers artifact must be a single ``scalers.pkl`` file —
        #    NOT ``scalers.npy`` and NOT split per-axis.
        assert paths["scalers_path"].endswith("scalers.pkl"), (
            "ecdb29d regression: scalers must be saved as a single .pkl"
        )
        assert (out_dir / "scalers.pkl").exists()
        assert not (out_dir / "scalers.npy").exists()
        assert not (out_dir / "scaler_x.pkl").exists()
        assert not (out_dir / "scaler_y.pkl").exists()

        # 2. The pickled payload must be a dict with the prediction-service
        #    contract keys, holding full sklearn scaler objects.
        with open(paths["scalers_path"], "rb") as f:
            payload = pickle.load(f)

        assert isinstance(payload, dict)
        assert set(payload.keys()) == {"price_scaler", "feature_scaler"}
        assert isinstance(payload["price_scaler"], MinMaxScaler)
        assert isinstance(payload["feature_scaler"], MinMaxScaler)

        # 3. Mapping is correct: scaler_y → price_scaler, scaler_x → feature_scaler.
        assert payload["price_scaler"] is scaler_y
        assert payload["feature_scaler"] is scaler_x

    def test_save_model_writes_metadata_and_metrics_json(self, tmp_path):
        from sklearn.preprocessing import MinMaxScaler

        trainer = ModelTrainer()
        fake_model = MagicMock()
        fake_model.save = MagicMock()

        out_dir = tmp_path / "model_artifacts2"
        train_m = {"train_r2": 0.9}
        val_m = {"val_r2": 0.85}
        test_m = {"test_r2": 0.8}

        paths = trainer.save_model(
            model=fake_model,
            metadata=self._build_metadata(),
            train_metrics=train_m,
            val_metrics=val_m,
            test_metrics=test_m,
            scaler_x=MinMaxScaler(),
            scaler_y=MinMaxScaler(),
            output_dir=str(out_dir),
        )

        # Keras .save was actually called with the right path
        fake_model.save.assert_called_once_with(paths["model_path"])

        with open(paths["metadata_path"]) as f:
            meta = json.load(f)
        assert meta["symbol"] == "SOLUSDT"

        with open(paths["metrics_path"]) as f:
            metrics = json.load(f)
        # save_model writes the merged dict
        assert metrics["train_r2"] == 0.9
        assert metrics["val_r2"] == 0.85
        assert metrics["test_r2"] == 0.8


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
