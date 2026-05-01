"""Tests for predictor_factory after LSTM removal."""

import pytest

from app.ml_models.gru_model import GRUPricePredictor
from app.predictor_factory import ModelComparator, PredictorFactory


class TestPredictorFactoryRejectsLSTM:
    def test_create_predictor_rejects_lstm(self):
        with pytest.raises(ValueError, match="LSTM model type is no longer supported"):
            PredictorFactory.create_predictor("LSTM", "SOLUSDT", "60")

    def test_get_supported_models_excludes_lstm(self):
        assert "LSTM" not in PredictorFactory.get_supported_models()
        assert "GRU" in PredictorFactory.get_supported_models()

    def test_create_predictor_returns_gru(self):
        p = PredictorFactory.create_predictor("GRU", "SOLUSDT", "60")
        assert isinstance(p, GRUPricePredictor)


class TestModelComparatorStub:
    def test_lstm_predictor_is_none(self):
        comp = ModelComparator("SOLUSDT", "60")
        assert comp.lstm_predictor is None
        assert isinstance(comp.gru_predictor, GRUPricePredictor)

    def test_recommendation_when_no_model(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        comp = ModelComparator("FAKEUSDT", "60")
        # No .keras for FAKEUSDT, so model is None; expect NONE recommendation.
        assert "NONE" in comp.get_recommendation()
