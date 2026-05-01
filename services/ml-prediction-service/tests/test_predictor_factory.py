"""Tests for predictor_factory gating + LSTM removal migration."""

import pytest

from app.predictor_factory import ModelComparator, PredictorFactory
from app.predictor import LSTMPricePredictor
from app.ml_models.gru_model import GRUPricePredictor


class TestPredictorFactoryRejectsLSTM:
    def test_create_predictor_rejects_lstm(self):
        with pytest.raises(ValueError, match="LSTM model type is no longer supported"):
            PredictorFactory.create_predictor("LSTM", "SOLUSDT", "60")

    def test_get_supported_models_excludes_lstm(self):
        assert "LSTM" not in PredictorFactory.get_supported_models()
        assert "GRU" in PredictorFactory.get_supported_models()


class TestModelComparatorLSTMGating:
    def test_lstm_skipped_when_artifact_absent(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        comp = ModelComparator("SOLUSDT", "60")
        assert comp.lstm_predictor is None
        assert isinstance(comp.gru_predictor, GRUPricePredictor)

    def test_lstm_loaded_when_artifact_present(self, tmp_path, monkeypatch):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "SOLUSDT_60m_lstm.keras").write_bytes(b"")
        monkeypatch.chdir(tmp_path)
        comp = ModelComparator("SOLUSDT", "60")
        assert isinstance(comp.lstm_predictor, LSTMPricePredictor)
