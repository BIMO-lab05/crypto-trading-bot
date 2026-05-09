"""
Tests for ``retrain_target_mode`` plumbing — chunk 1 of the T0.1 GRU rebuild.

The setting decides what the GRU's prediction target is:

- ``"price"`` (default, legacy): model predicts raw close prices. The
  inverse-transformed prediction is itself the price.
- ``"log_returns"``: model predicts ``log(close_{t+1}/last_close)``.
  Predicted prices are recovered downstream via
  ``last_close * exp(pred_log_return)`` so the returns-metrics / CPCV
  plumbing stays price-shaped without further branches.

This file is split into two halves on purpose:

- ``TestRetrainTargetModeSetting`` runs without tensorflow — pure
  Pydantic settings tests so the chunk-1 default ("price") is locked
  even on the local TF-less venv.
- ``TestRecoverPrices`` and ``TestTrainerInitTargetMode`` need to
  import ``ModelTrainer`` (which loads tensorflow at module level), so
  they importorskip TF inside each test rather than at module load.
  Otherwise pytest collection on a TF-less environment skips the entire
  module and the setting-default test silently disappears.
"""

from __future__ import annotations

import importlib.util
import os
from unittest.mock import patch

import pytest

pytest.importorskip("numpy")

import numpy as np  # noqa: E402

from app.config.settings import RetrainingSettings  # noqa: E402


TF_AVAILABLE = importlib.util.find_spec("tensorflow") is not None


# ---------------------------------------------------------------------------
# Setting default + validation — TF-free
# ---------------------------------------------------------------------------


class TestRetrainTargetModeSetting:
    def test_default_is_price_for_backwards_compat(self):
        # Existing production retrains predict raw close — the chunk 1
        # default has to keep that behaviour or every nightly retrain
        # silently swaps target on first deploy.
        with patch.dict(os.environ, {}, clear=True):
            s = RetrainingSettings()
        assert s.retrain_target_mode == "price"

    def test_log_returns_value_accepted(self):
        with patch.dict(os.environ, {"RETRAIN_TARGET_MODE": "log_returns"}, clear=True):
            s = RetrainingSettings()
        assert s.retrain_target_mode == "log_returns"

    def test_invalid_value_rejected(self):
        # The Field pattern guards against typos like 'log_return' or
        # 'returns' — both would otherwise silently fall through to a
        # KeyError deep in create_sequences.
        from pydantic import ValidationError
        with patch.dict(os.environ, {"RETRAIN_TARGET_MODE": "log_return"}, clear=True):
            with pytest.raises(ValidationError):
                RetrainingSettings()


# ---------------------------------------------------------------------------
# _recover_prices helper — needs ModelTrainer (TF) at runtime
# ---------------------------------------------------------------------------


class _StubTrainer:
    """Minimal stand-in for ModelTrainer just enough to exercise _recover_prices.

    The helper only reads ``self.target_mode``, no other state — so we
    bind the unbound method off the class object and pass this stub as
    ``self``. Avoids constructing a real ModelTrainer (which would also
    pull in pandas / sklearn at __init__).
    """

    def __init__(self, target_mode: str):
        self.target_mode = target_mode


def _call_recover_prices(target_mode, y, last_close):
    """Helper: call ModelTrainer._recover_prices via the stub trainer."""
    if not TF_AVAILABLE:
        pytest.skip("tensorflow required to import ModelTrainer")
    from app.core.model_trainer import ModelTrainer
    return ModelTrainer._recover_prices(_StubTrainer(target_mode), y, last_close)


class TestRecoverPrices:
    def test_price_mode_is_identity(self):
        y = np.array([100.0, 101.5, 99.25])
        last_close = np.array([100.0, 100.5, 100.0])  # ignored in price mode
        out = _call_recover_prices("price", y, last_close)
        np.testing.assert_array_equal(out, y)

    def test_log_returns_mode_recovers_via_exp(self):
        last_close = np.array([100.0, 100.0, 100.0])
        # log(110/100) ≈ 0.0953; recovery should map back to 110.
        log_ret = np.log(np.array([110.0, 90.0, 100.5]) / 100.0)
        out = _call_recover_prices("log_returns", log_ret, last_close)
        np.testing.assert_allclose(out, [110.0, 90.0, 100.5])

    def test_log_returns_zero_recovers_last_close(self):
        # A "no change" log_return must recover exactly the reference.
        last_close = np.array([100.0, 250.0, 0.5])
        out = _call_recover_prices("log_returns", np.zeros(3), last_close)
        np.testing.assert_allclose(out, last_close)

    def test_log_returns_negative_shrinks_below_reference(self):
        last_close = np.array([100.0])
        log_ret = np.log(np.array([80.0]) / 100.0)
        out = _call_recover_prices("log_returns", log_ret, last_close)
        np.testing.assert_allclose(out, [80.0])

    def test_handles_python_lists(self):
        # Helper is called on np.ndarray slices but should still tolerate
        # lists for use in tests / scripts.
        out = _call_recover_prices("log_returns", [0.0, 0.1], [100.0, 100.0])
        np.testing.assert_allclose(out, [100.0, 100.0 * np.exp(0.1)])


# ---------------------------------------------------------------------------
# Trainer __init__ wires target_col from target_mode
# ---------------------------------------------------------------------------


class TestTrainerInitTargetMode:
    def test_price_mode_target_col_is_close(self, monkeypatch):
        if not TF_AVAILABLE:
            pytest.skip("tensorflow required to import ModelTrainer")
        monkeypatch.setenv("RETRAIN_TARGET_MODE", "price")
        from app.config import settings as settings_mod
        settings_mod._settings = None
        from app.core.model_trainer import ModelTrainer
        t = ModelTrainer()
        assert t.target_mode == "price"
        assert t.target_col == "close"

    def test_log_returns_mode_target_col_is_log_returns(self, monkeypatch):
        if not TF_AVAILABLE:
            pytest.skip("tensorflow required to import ModelTrainer")
        monkeypatch.setenv("RETRAIN_TARGET_MODE", "log_returns")
        from app.config import settings as settings_mod
        settings_mod._settings = None
        from app.core.model_trainer import ModelTrainer
        t = ModelTrainer()
        assert t.target_mode == "log_returns"
        assert t.target_col == "log_returns"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
