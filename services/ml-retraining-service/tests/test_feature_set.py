"""
Tests for the ``retrain_feature_set`` setting + trainer dispatcher —
chunk 2 of the T0.1 GRU rebuild.

Mirrors ``test_target_mode.py``: TF-free tests for the Pydantic setting
default + validation; TF-required tests for the trainer's ``__init__``,
``prepare_features`` dispatch, and ``create_sequences`` feature_cols
plumbing.
"""

from __future__ import annotations

import importlib.util
import os
from unittest.mock import patch

import pytest

pytest.importorskip("numpy")
pytest.importorskip("pandas")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.config.settings import RetrainingSettings  # noqa: E402
from app.core.stationary_features import STATIONARY_FEATURE_COLS  # noqa: E402


TF_AVAILABLE = importlib.util.find_spec("tensorflow") is not None


# ---------------------------------------------------------------------------
# Setting default + validation — TF-free
# ---------------------------------------------------------------------------


class TestRetrainFeatureSetSetting:
    def test_default_is_legacy_for_backwards_compat(self):
        # Existing production retrains use the 22-indicator legacy pile.
        # Chunk 2 must not silently flip the default.
        with patch.dict(os.environ, {}, clear=True):
            s = RetrainingSettings()
        assert s.retrain_feature_set == "legacy"

    def test_stationary_value_accepted(self):
        with patch.dict(os.environ, {"RETRAIN_FEATURE_SET": "stationary"}, clear=True):
            s = RetrainingSettings()
        assert s.retrain_feature_set == "stationary"

    def test_invalid_value_rejected(self):
        from pydantic import ValidationError
        with patch.dict(os.environ, {"RETRAIN_FEATURE_SET": "stationery"}, clear=True):
            with pytest.raises(ValidationError):
                RetrainingSettings()


# ---------------------------------------------------------------------------
# Trainer dispatch — TF-required
# ---------------------------------------------------------------------------


def _make_synthetic_ohlcv(n: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = 100 + np.cumsum(rng.normal(0, 0.5, n))
    high = base + np.abs(rng.normal(0, 0.3, n))
    low = base - np.abs(rng.normal(0, 0.3, n))
    open_ = base + rng.normal(0, 0.1, n)
    close = base + rng.normal(0, 0.1, n)
    volume = np.abs(rng.normal(1000, 100, n))
    timestamps = pd.date_range("2026-01-01", periods=n, freq="60min")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def _force_settings_reload():
    from app.config import settings as settings_mod
    settings_mod._settings = None


class TestTrainerInitFeatureSet:
    def test_legacy_mode_stored(self, monkeypatch):
        if not TF_AVAILABLE:
            pytest.skip("tensorflow required")
        monkeypatch.setenv("RETRAIN_FEATURE_SET", "legacy")
        _force_settings_reload()
        from app.core.model_trainer import ModelTrainer
        t = ModelTrainer()
        assert t.feature_set == "legacy"

    def test_stationary_mode_stored(self, monkeypatch):
        if not TF_AVAILABLE:
            pytest.skip("tensorflow required")
        monkeypatch.setenv("RETRAIN_FEATURE_SET", "stationary")
        _force_settings_reload()
        from app.core.model_trainer import ModelTrainer
        t = ModelTrainer()
        assert t.feature_set == "stationary"


class TestPrepareFeaturesDispatch:
    def test_legacy_dispatch_uses_inline_22_indicators(self, monkeypatch):
        if not TF_AVAILABLE:
            pytest.skip("tensorflow required")
        monkeypatch.setenv("RETRAIN_FEATURE_SET", "legacy")
        _force_settings_reload()
        from app.core.model_trainer import ModelTrainer

        df = _make_synthetic_ohlcv()
        t = ModelTrainer()
        out = t.prepare_features(df)

        # Legacy pile contains both stationary and level features.
        assert "sma_7" in out.columns        # level
        assert "rsi" in out.columns          # stationary
        assert "bb_middle" in out.columns    # level

    def test_stationary_dispatch_strips_level_features(self, monkeypatch):
        if not TF_AVAILABLE:
            pytest.skip("tensorflow required")
        monkeypatch.setenv("RETRAIN_FEATURE_SET", "stationary")
        _force_settings_reload()
        from app.core.model_trainer import ModelTrainer

        df = _make_synthetic_ohlcv()
        t = ModelTrainer()
        out = t.prepare_features(df)

        for forbidden in ("sma_7", "ema_7", "bb_middle", "bb_upper", "bb_lower",
                          "volume_sma", "high_low_ratio"):
            assert forbidden not in out.columns
        # Stationary additions present.
        assert "vol_of_vol_14" in out.columns
        assert "log_volume_change" in out.columns
        assert "hour_sin" in out.columns


# ---------------------------------------------------------------------------
# create_sequences feature_cols plumbing
# ---------------------------------------------------------------------------


class TestCreateSequencesFeatureCols:
    def test_explicit_feature_cols_overrides_default(self, monkeypatch):
        if not TF_AVAILABLE:
            pytest.skip("tensorflow required")
        # Build a stationary-mode trainer and prove only the listed
        # columns become features even when ``close`` is in the
        # DataFrame.
        monkeypatch.setenv("RETRAIN_FEATURE_SET", "stationary")
        monkeypatch.setenv("RETRAIN_TARGET_MODE", "log_returns")
        _force_settings_reload()
        from app.core.model_trainer import ModelTrainer

        df = _make_synthetic_ohlcv(n=300)
        t = ModelTrainer()
        prepared = t.prepare_features(df)
        # log_returns is the target; close is in the frame for last_close;
        # neither should appear in features.
        X, y = t.create_sequences(
            prepared,
            target_col="log_returns",
            feature_cols=list(STATIONARY_FEATURE_COLS),
        )
        # X.shape[2] = number of features = exactly len(STATIONARY_FEATURE_COLS).
        assert X.shape[2] == len(STATIONARY_FEATURE_COLS)

    def test_default_feature_cols_excludes_target_only(self, monkeypatch):
        # Backwards-compat for callers that don't pass feature_cols
        # (notably the existing test_model_trainer.py).
        if not TF_AVAILABLE:
            pytest.skip("tensorflow required")
        monkeypatch.setenv("RETRAIN_FEATURE_SET", "legacy")
        monkeypatch.setenv("RETRAIN_TARGET_MODE", "price")
        _force_settings_reload()
        from app.core.model_trainer import ModelTrainer

        df = _make_synthetic_ohlcv()
        t = ModelTrainer()
        prepared = t.prepare_features(df)
        X, y = t.create_sequences(prepared)  # no feature_cols
        # Legacy with target=close → features = all columns minus
        # timestamp + close. Sanity: at least 22 (the documented legacy
        # count) and not zero.
        assert X.shape[2] >= 22


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
