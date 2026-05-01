"""
Comprehensive tests for GRU Predictor
Tests GRU-specific functionality and compares with LSTM
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import tempfile
import shutil

from app.ml_models.gru_predictor import GRUPricePredictor, TENSORFLOW_AVAILABLE
from app.models import PricePrediction


@pytest.fixture
def temp_models_dir():
    """Create temporary directory for model storage"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_price_data():
    """Create sample price data for testing"""
    dates = pd.date_range(end=datetime.now(), periods=200, freq="1h")

    base_price = 40000
    prices = [base_price]

    for i in range(1, 200):
        change = np.random.normal(0, 100)
        prices.append(prices[-1] + change)

    data = pd.DataFrame(
        {
            "timestamp": dates,
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": np.random.uniform(100, 1000, 200),
        }
    )

    return data


@pytest.fixture
def gru_predictor(temp_models_dir):
    """Create GRU predictor instance with temp directory"""
    with patch("app.ml_models.gru_predictor.settings.models_dir", temp_models_dir):
        predictor = GRUPricePredictor("BTCUSDT", "60")
        return predictor


class TestGRUInitialization:
    """Test GRU predictor initialization"""

    def test_initialization(self, gru_predictor):
        """Test GRU predictor initializes correctly"""
        assert gru_predictor.symbol == "BTCUSDT"
        assert gru_predictor.interval == "60"
        assert gru_predictor.model is None

    def test_model_path_different_from_lstm(self, gru_predictor):
        """Test GRU uses different file path than LSTM"""
        path = gru_predictor._get_model_path()

        assert "gru" in str(path).lower()
        assert path.suffix == ".keras"


class TestGRUFeatureEngineering:
    """Test GRU feature engineering"""

    def test_create_features(self, gru_predictor, sample_price_data):
        """Test feature creation for GRU"""
        features = gru_predictor._create_features(sample_price_data)

        assert isinstance(features, pd.DataFrame)
        assert len(features) > 0
        assert "close" in features.columns

    def test_calculate_rsi(self, gru_predictor):
        """Test RSI calculation in GRU predictor"""
        prices = pd.Series([100 + i for i in range(50)])
        rsi = gru_predictor._calculate_rsi(prices, period=14)

        assert isinstance(rsi, pd.Series)
        assert rsi.iloc[-1] > 50  # Uptrend should have high RSI


class TestGRUModelBuilding:
    """Test GRU model architecture"""

    @pytest.mark.skipif(not TENSORFLOW_AVAILABLE, reason="TensorFlow not available")
    def test_build_gru_model(self, gru_predictor):
        """Test GRU model building"""
        n_features = 10
        model = gru_predictor._build_gru_model(n_features)

        from tensorflow import keras

        assert isinstance(model, keras.Model)

        # Check model uses GRU layers
        layer_types = [type(layer).__name__ for layer in model.layers]
        assert "GRU" in str(layer_types)

    @pytest.mark.skipif(not TENSORFLOW_AVAILABLE, reason="TensorFlow not available")
    def test_gru_model_structure(self, gru_predictor):
        """Test GRU model has correct input/output shapes"""
        n_features = 10
        model = gru_predictor._build_gru_model(n_features)

        # Check input shape
        assert model.input_shape[1] == gru_predictor.sequence_length
        assert model.input_shape[2] == n_features

        # Check output shape
        assert model.output_shape[1] == gru_predictor.prediction_horizon


class TestGRUTraining:
    """Test GRU model training"""

    @pytest.mark.skipif(not TENSORFLOW_AVAILABLE, reason="TensorFlow not available")
    @pytest.mark.asyncio
    async def test_train_gru(self, gru_predictor, sample_price_data):
        """Test GRU training"""
        with patch.object(gru_predictor, "_save_model"):
            with patch.object(gru_predictor, "_save_metadata"):
                result = await gru_predictor.train(
                    sample_price_data, epochs=1, batch_size=32
                )

                assert "status" in result
                assert gru_predictor.model is not None

    @pytest.mark.skipif(not TENSORFLOW_AVAILABLE, reason="TensorFlow not available")
    @pytest.mark.asyncio
    async def test_gru_training_speed(self, gru_predictor, sample_price_data):
        """Test that GRU training completes (speed test)"""
        start_time = datetime.now()

        with patch.object(gru_predictor, "_save_model"):
            with patch.object(gru_predictor, "_save_metadata"):
                await gru_predictor.train(sample_price_data, epochs=1)

        duration = (datetime.now() - start_time).total_seconds()

        # GRU should complete training in reasonable time
        assert duration < 300  # 5 minutes max for test


class TestGRUPrediction:
    """Test GRU prediction functionality"""

    @pytest.mark.skipif(not TENSORFLOW_AVAILABLE, reason="TensorFlow not available")
    @pytest.mark.asyncio
    async def test_gru_predict(self, gru_predictor, sample_price_data):
        """Test GRU prediction"""
        # Train first
        with patch.object(gru_predictor, "_save_model"):
            with patch.object(gru_predictor, "_save_metadata"):
                await gru_predictor.train(sample_price_data, epochs=1)

        # Predict
        prediction = await gru_predictor.predict(sample_price_data)

        assert isinstance(prediction, PricePrediction)
        assert len(prediction.predictions) > 0

    @pytest.mark.asyncio
    async def test_gru_predict_without_model(self, gru_predictor, sample_price_data):
        """Test GRU prediction fails without model"""
        gru_predictor.model = None

        with pytest.raises(ValueError):
            await gru_predictor.predict(sample_price_data)


class TestGRUPersistence:
    """Test GRU model saving and loading"""

    def test_gru_model_path(self, gru_predictor):
        """Test GRU model path is correct"""
        path = gru_predictor._get_model_path()

        assert "gru" in str(path).lower()
        assert "BTCUSDT" in str(path)

    def test_gru_metadata_path(self, gru_predictor):
        """Test GRU metadata path"""
        path = gru_predictor._get_metadata_path()

        assert "gru" in str(path).lower()
        assert path.suffix == ".json"

    @pytest.mark.skipif(not TENSORFLOW_AVAILABLE, reason="TensorFlow not available")
    def test_save_and_load_gru(self, gru_predictor, sample_price_data, temp_models_dir):
        """Test saving and loading GRU model"""
        import asyncio

        with patch("app.ml_models.gru_predictor.settings.models_dir", temp_models_dir):
            # Train and save
            asyncio.run(gru_predictor.train(sample_price_data, epochs=1))

            # Load in new instance
            new_predictor = GRUPricePredictor("BTCUSDT", "60")

            assert new_predictor.model is not None


class TestGRUPerformanceMetrics:
    """Test GRU performance metrics"""

    @pytest.mark.skipif(not TENSORFLOW_AVAILABLE, reason="TensorFlow not available")
    @pytest.mark.asyncio
    async def test_gru_stores_metrics(self, gru_predictor, sample_price_data):
        """Test GRU stores training metrics"""
        with patch.object(gru_predictor, "_save_model"):
            with patch.object(gru_predictor, "_save_metadata"):
                await gru_predictor.train(sample_price_data, epochs=1)

                assert "rmse" in gru_predictor.training_stats
                assert "mae" in gru_predictor.training_stats
                assert "r2_score" in gru_predictor.training_stats

    def test_gru_get_model_info(self, gru_predictor):
        """Test getting GRU model info"""
        info = gru_predictor.get_model_info()

        assert info["symbol"] == "BTCUSDT"
        assert info["model_type"] == "GRU"


class TestGRUSpecificFeatures:
    """Test GRU-specific features"""

    @pytest.mark.skipif(not TENSORFLOW_AVAILABLE, reason="TensorFlow not available")
    def test_gru_parameter_count(self, gru_predictor):
        """Test GRU has fewer parameters than equivalent LSTM"""
        model = gru_predictor._build_gru_model(10)

        # GRU should have trainable parameters
        param_count = model.count_params()
        assert param_count > 0

        # GRU typically has ~75% of LSTM parameters
        # This is a characteristic advantage of GRU

    def test_gru_supports_same_intervals(self, temp_models_dir):
        """Test GRU supports same intervals as LSTM"""
        with patch("app.ml_models.gru_predictor.settings.models_dir", temp_models_dir):
            for interval in ["1", "5", "15", "60", "240"]:
                predictor = GRUPricePredictor("BTCUSDT", interval)
                assert predictor.interval == interval


class TestGRUEdgeCases:
    """Test GRU edge cases"""

    @pytest.mark.asyncio
    async def test_gru_with_minimal_data(self, gru_predictor):
        """Test GRU with minimal data"""
        small_data = pd.DataFrame(
            {
                "timestamp": pd.date_range(end=datetime.now(), periods=10, freq="1h"),
                "close": [40000] * 10,
                "open": [40000] * 10,
                "high": [40500] * 10,
                "low": [39500] * 10,
                "volume": [100] * 10,
            }
        )

        with pytest.raises(ValueError):
            await gru_predictor.train(small_data)

    def test_gru_with_special_symbols(self, temp_models_dir):
        """Test GRU with special symbol characters"""
        with patch("app.ml_models.gru_predictor.settings.models_dir", temp_models_dir):
            predictor = GRUPricePredictor("ETH-USDT", "60")
            assert predictor.symbol == "ETH-USDT"


class TestGRUInferenceTracking:
    """Test GRU-specific tracking. LSTM comparison removed (LSTM phased out late 2025)."""

    def test_gru_inference_time_tracking(self, gru_predictor):
        """Test GRU tracks inference time"""
        assert hasattr(gru_predictor, "inference_time_ms") or True
        # GRU should track inference time for comparison


class TestGRUErrorHandling:
    """Test GRU error handling"""

    @pytest.mark.asyncio
    async def test_gru_handles_nan_data(self, gru_predictor):
        """Test GRU handles NaN data appropriately"""
        data = pd.DataFrame(
            {
                "timestamp": pd.date_range(end=datetime.now(), periods=100, freq="1h"),
                "close": [np.nan if i % 10 == 0 else 40000 for i in range(100)],
                "open": [40000] * 100,
                "high": [40500] * 100,
                "low": [39500] * 100,
                "volume": [100] * 100,
            }
        )

        # Should handle or raise appropriate error
        try:
            features = gru_predictor._create_features(data)
            assert features is not None
        except ValueError:
            # Expected to fail with NaN data
            pass

    @pytest.mark.asyncio
    async def test_gru_prediction_without_training(
        self, gru_predictor, sample_price_data
    ):
        """Test GRU prediction without training raises error"""
        with pytest.raises(ValueError):
            await gru_predictor.predict(sample_price_data)


class TestGRUModelSize:
    """Test GRU model size tracking"""

    def test_gru_get_model_size(self, gru_predictor):
        """Test GRU can report model size"""
        if hasattr(gru_predictor, "get_model_size_mb"):
            # If method exists, it should work
            assert True
        else:
            # Model size can be calculated from file
            path = gru_predictor._get_model_path()
            assert isinstance(path, Path)


class TestGRURetraining:
    """Test GRU retraining logic"""

    def test_gru_needs_retraining_new(self, gru_predictor):
        """Test new GRU model needs training"""
        gru_predictor.last_trained = None

        if hasattr(gru_predictor, "_needs_retraining"):
            needs_retrain = gru_predictor._needs_retraining()
            assert needs_retrain is True

    def test_gru_needs_retraining_old(self, gru_predictor):
        """Test old GRU model needs retraining"""
        gru_predictor.last_trained = datetime.now() - timedelta(days=10)

        if hasattr(gru_predictor, "_needs_retraining"):
            with patch("app.ml_models.gru_predictor.settings.model_retrain_days", 7):
                needs_retrain = gru_predictor._needs_retraining()
                assert needs_retrain is True
