"""
Comprehensive tests for Predictor Factory and Model Comparator
Tests model creation, comparison, and recommendation logic
"""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
import tempfile
import shutil

from app.predictor_factory import PredictorFactory, ModelComparator
from app.predictor import LSTMPricePredictor
from app.ml_models.gru_model import GRUPricePredictor
from app.models import PricePrediction, PricePoint


@pytest.fixture
def sample_price_data():
    """Create sample price data for testing"""
    dates = pd.date_range(end=datetime.now(), periods=100, freq='1h')
    prices = [40000 + i*10 for i in range(100)]

    return pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': np.random.uniform(100, 1000, 100)
    })


class TestPredictorFactory:
    """Test PredictorFactory functionality"""

    def test_create_lstm_predictor(self):
        """Test creating LSTM predictor"""
        predictor = PredictorFactory.create_predictor("LSTM", "BTCUSDT", "60")

        assert isinstance(predictor, LSTMPricePredictor)
        assert predictor.symbol == "BTCUSDT"
        assert predictor.interval == "60"

    def test_create_gru_predictor(self):
        """Test creating GRU predictor"""
        predictor = PredictorFactory.create_predictor("GRU", "BTCUSDT", "60")

        assert isinstance(predictor, GRUPricePredictor)
        assert predictor.symbol == "BTCUSDT"
        assert predictor.interval == "60"

    def test_create_predictor_lowercase(self):
        """Test factory handles lowercase model type"""
        predictor = PredictorFactory.create_predictor("lstm", "ETHUSDT", "60")

        assert isinstance(predictor, LSTMPricePredictor)

    def test_create_predictor_mixed_case(self):
        """Test factory handles mixed case model type"""
        predictor = PredictorFactory.create_predictor("Gru", "ETHUSDT", "60")

        assert isinstance(predictor, GRUPricePredictor)

    def test_create_predictor_invalid_type(self):
        """Test factory raises error for invalid model type"""
        with pytest.raises(ValueError, match="Unsupported model type"):
            PredictorFactory.create_predictor("INVALID", "BTCUSDT", "60")

    def test_create_predictor_with_different_intervals(self):
        """Test factory creates predictors with different intervals"""
        for interval in ["1", "5", "15", "60", "240"]:
            predictor = PredictorFactory.create_predictor("LSTM", "BTCUSDT", interval)
            assert predictor.interval == interval

    def test_get_supported_models(self):
        """Test getting list of supported models"""
        models = PredictorFactory.get_supported_models()

        assert isinstance(models, list)
        assert "LSTM" in models
        assert "GRU" in models
        assert len(models) == 2


class TestModelComparatorInitialization:
    """Test ModelComparator initialization"""

    def test_comparator_initialization(self):
        """Test comparator initializes correctly"""
        comparator = ModelComparator("BTCUSDT", "60")

        assert comparator.symbol == "BTCUSDT"
        assert comparator.interval == "60"
        assert isinstance(comparator.lstm_predictor, LSTMPricePredictor)
        assert isinstance(comparator.gru_predictor, GRUPricePredictor)

    def test_comparator_creates_both_predictors(self):
        """Test comparator creates both LSTM and GRU predictors"""
        comparator = ModelComparator("ETHUSDT", "240")

        assert comparator.lstm_predictor.symbol == "ETHUSDT"
        assert comparator.gru_predictor.symbol == "ETHUSDT"
        assert comparator.lstm_predictor.interval == "240"
        assert comparator.gru_predictor.interval == "240"


class TestComparePredictions:
    """Test prediction comparison functionality"""

    @pytest.mark.asyncio
    async def test_compare_predictions_both_models_trained(self, sample_price_data):
        """Test comparing predictions when both models are trained"""
        comparator = ModelComparator("BTCUSDT", "60")

        # Mock both predictors to have models
        comparator.lstm_predictor.model = MagicMock()
        comparator.gru_predictor.model = MagicMock()

        # Mock predictions
        lstm_prediction = MagicMock()
        lstm_prediction.predictions = [
            MagicMock(timestamp=datetime.now() + timedelta(hours=i), predicted_price=41000 + i*100, confidence=0.85)
            for i in range(3)
        ]
        lstm_prediction.predicted_direction = "bullish"
        lstm_prediction.average_confidence = 0.85

        gru_prediction = MagicMock()
        gru_prediction.predictions = [
            MagicMock(timestamp=datetime.now() + timedelta(hours=i), predicted_price=41000 + i*110, confidence=0.87)
            for i in range(3)
        ]
        gru_prediction.predicted_direction = "bullish"
        gru_prediction.average_confidence = 0.87

        comparator.lstm_predictor.predict = AsyncMock(return_value=lstm_prediction)
        comparator.gru_predictor.predict = AsyncMock(return_value=gru_prediction)
        comparator.lstm_predictor.training_stats = {'inference_time_ms': 45}
        comparator.gru_predictor.inference_time_ms = 38

        result = await comparator.compare_predictions(sample_price_data)

        assert result['symbol'] == 'BTCUSDT'
        assert 'lstm' in result
        assert 'gru' in result
        assert 'comparison' in result
        assert result['comparison']['direction_agreement'] is True

    @pytest.mark.asyncio
    async def test_compare_predictions_only_lstm_trained(self, sample_price_data):
        """Test comparison when only LSTM is trained"""
        comparator = ModelComparator("BTCUSDT", "60")

        comparator.lstm_predictor.model = MagicMock()
        comparator.gru_predictor.model = None

        lstm_prediction = MagicMock()
        lstm_prediction.predictions = [MagicMock(timestamp=datetime.now(), predicted_price=41000, confidence=0.85)]
        lstm_prediction.predicted_direction = "bullish"
        lstm_prediction.average_confidence = 0.85

        comparator.lstm_predictor.predict = AsyncMock(return_value=lstm_prediction)
        comparator.lstm_predictor.training_stats = {'inference_time_ms': 45}

        result = await comparator.compare_predictions(sample_price_data)

        assert result['lstm'] is not None
        assert result['gru'] is None

    @pytest.mark.asyncio
    async def test_compare_predictions_only_gru_trained(self, sample_price_data):
        """Test comparison when only GRU is trained"""
        comparator = ModelComparator("BTCUSDT", "60")

        comparator.lstm_predictor.model = None
        comparator.gru_predictor.model = MagicMock()

        gru_prediction = MagicMock()
        gru_prediction.predictions = [MagicMock(timestamp=datetime.now(), predicted_price=41000, confidence=0.87)]
        gru_prediction.predicted_direction = "bullish"
        gru_prediction.average_confidence = 0.87

        comparator.gru_predictor.predict = AsyncMock(return_value=gru_prediction)
        comparator.gru_predictor.inference_time_ms = 38

        result = await comparator.compare_predictions(sample_price_data)

        assert result['lstm'] is None
        assert result['gru'] is not None

    @pytest.mark.asyncio
    async def test_compare_predictions_handles_errors(self, sample_price_data):
        """Test comparison handles prediction errors gracefully"""
        comparator = ModelComparator("BTCUSDT", "60")

        comparator.lstm_predictor.model = MagicMock()
        comparator.gru_predictor.model = MagicMock()

        # Mock LSTM to fail
        comparator.lstm_predictor.predict = AsyncMock(side_effect=Exception("Model error"))

        # Mock GRU to succeed
        gru_prediction = MagicMock()
        gru_prediction.predictions = [MagicMock(timestamp=datetime.now(), predicted_price=41000, confidence=0.87)]
        gru_prediction.predicted_direction = "bullish"
        gru_prediction.average_confidence = 0.87
        comparator.gru_predictor.predict = AsyncMock(return_value=gru_prediction)
        comparator.gru_predictor.inference_time_ms = 38

        result = await comparator.compare_predictions(sample_price_data)

        assert 'error' in result['lstm']
        assert result['gru'] is not None

    @pytest.mark.asyncio
    async def test_compare_predictions_calculates_differences(self, sample_price_data):
        """Test comparison calculates price differences correctly"""
        comparator = ModelComparator("BTCUSDT", "60")

        comparator.lstm_predictor.model = MagicMock()
        comparator.gru_predictor.model = MagicMock()

        lstm_prediction = MagicMock()
        lstm_prediction.predictions = [
            MagicMock(timestamp=datetime.now(), predicted_price=41000, confidence=0.85),
            MagicMock(timestamp=datetime.now(), predicted_price=41100, confidence=0.85)
        ]
        lstm_prediction.predicted_direction = "bullish"
        lstm_prediction.average_confidence = 0.85

        gru_prediction = MagicMock()
        gru_prediction.predictions = [
            MagicMock(timestamp=datetime.now(), predicted_price=41050, confidence=0.87),
            MagicMock(timestamp=datetime.now(), predicted_price=41150, confidence=0.87)
        ]
        gru_prediction.predicted_direction = "bullish"
        gru_prediction.average_confidence = 0.87

        comparator.lstm_predictor.predict = AsyncMock(return_value=lstm_prediction)
        comparator.gru_predictor.predict = AsyncMock(return_value=gru_prediction)
        comparator.lstm_predictor.training_stats = {'inference_time_ms': 45}
        comparator.gru_predictor.inference_time_ms = 38

        result = await comparator.compare_predictions(sample_price_data)

        assert 'avg_price_difference' in result['comparison']
        assert 'max_price_difference' in result['comparison']
        assert result['comparison']['avg_price_difference'] == 50.0


class TestCompareTrainingMetrics:
    """Test training metrics comparison"""

    @pytest.mark.asyncio
    async def test_compare_training_metrics_both_models(self):
        """Test comparing training metrics when both models exist"""
        comparator = ModelComparator("BTCUSDT", "60")

        # Mock both models
        comparator.lstm_predictor.model = MagicMock()
        comparator.gru_predictor.model = MagicMock()

        comparator.lstm_predictor.last_trained = datetime.now()
        comparator.gru_predictor.last_trained = datetime.now()

        comparator.lstm_predictor.model_version = "v1"
        comparator.gru_predictor.model_version = "v1"

        comparator.lstm_predictor.training_stats = {
            'rmse': 150.0,
            'mae': 120.0,
            'r2_score': 0.85,
            'directional_accuracy': 0.72
        }

        comparator.gru_predictor.training_stats = {
            'rmse': 140.0,
            'mae': 115.0,
            'r2_score': 0.87,
            'directional_accuracy': 0.75
        }

        result = await comparator.compare_training_metrics()

        assert 'models' in result
        assert 'lstm' in result['models']
        assert 'gru' in result['models']
        assert 'winner' in result

    @pytest.mark.asyncio
    async def test_compare_training_determines_winners(self):
        """Test comparison determines winners for each metric"""
        comparator = ModelComparator("BTCUSDT", "60")

        comparator.lstm_predictor.model = MagicMock()
        comparator.gru_predictor.model = MagicMock()
        comparator.lstm_predictor.last_trained = datetime.now()
        comparator.gru_predictor.last_trained = datetime.now()
        comparator.lstm_predictor.model_version = "v1"
        comparator.gru_predictor.model_version = "v1"

        comparator.lstm_predictor.training_stats = {
            'rmse': 150.0,
            'mae': 120.0,
            'r2_score': 0.85,
            'directional_accuracy': 0.72
        }

        comparator.gru_predictor.training_stats = {
            'rmse': 140.0,  # GRU better
            'mae': 115.0,   # GRU better
            'r2_score': 0.87,  # GRU better
            'directional_accuracy': 0.75  # GRU better
        }

        result = await comparator.compare_training_metrics()

        assert result['winner']['rmse'] == 'GRU'
        assert result['winner']['mae'] == 'GRU'
        assert result['winner']['r2_score'] == 'GRU'
        assert result['winner']['overall'] == 'GRU'


class TestGetTrainingMetrics:
    """Test _get_training_metrics helper method"""

    def test_get_training_metrics_with_model(self):
        """Test extracting metrics from trained model"""
        comparator = ModelComparator("BTCUSDT", "60")

        comparator.lstm_predictor.model = MagicMock()
        comparator.lstm_predictor.last_trained = datetime.now()
        comparator.lstm_predictor.model_version = "v1"
        comparator.lstm_predictor.training_stats = {
            'rmse': 150.0,
            'mae': 120.0,
            'r2_score': 0.85
        }

        metrics = comparator._get_training_metrics(comparator.lstm_predictor, 'LSTM')

        assert metrics is not None
        assert metrics['model_type'] == 'LSTM'
        assert metrics['rmse'] == 150.0
        assert metrics['mae'] == 120.0

    def test_get_training_metrics_without_model(self):
        """Test extracting metrics when no model exists"""
        comparator = ModelComparator("BTCUSDT", "60")

        comparator.lstm_predictor.model = None

        metrics = comparator._get_training_metrics(comparator.lstm_predictor, 'LSTM')

        assert metrics is None


class TestCalculateOverallScore:
    """Test overall score calculation"""

    def test_calculate_overall_score(self):
        """Test overall score calculation with valid metrics"""
        comparator = ModelComparator("BTCUSDT", "60")

        metrics = {
            'r2_score': 0.85,
            'directional_accuracy': 0.75,
            'rmse': 150.0,
            'mae': 120.0,
            'inference_time_ms': 45.0,
            'model_size_mb': 5.0
        }

        score = comparator._calculate_overall_score(metrics)

        assert isinstance(score, float)
        assert 0 <= score <= 1

    def test_calculate_overall_score_perfect_metrics(self):
        """Test score with perfect metrics"""
        comparator = ModelComparator("BTCUSDT", "60")

        metrics = {
            'r2_score': 1.0,
            'directional_accuracy': 1.0,
            'rmse': 1.0,
            'mae': 1.0,
            'inference_time_ms': 1.0,
            'model_size_mb': 1.0
        }

        score = comparator._calculate_overall_score(metrics)

        assert score > 0.8  # Should be high with perfect metrics

    def test_calculate_overall_score_poor_metrics(self):
        """Test score with poor metrics"""
        comparator = ModelComparator("BTCUSDT", "60")

        metrics = {
            'r2_score': 0.1,
            'directional_accuracy': 0.4,
            'rmse': 1000.0,
            'mae': 800.0,
            'inference_time_ms': 200.0,
            'model_size_mb': 50.0
        }

        score = comparator._calculate_overall_score(metrics)

        assert score < 0.5  # Should be low with poor metrics

    def test_calculate_overall_score_empty_metrics(self):
        """Test score with empty metrics"""
        comparator = ModelComparator("BTCUSDT", "60")

        score = comparator._calculate_overall_score({})

        assert score == 0.0


class TestGetRecommendation:
    """Test model recommendation logic"""

    def test_recommendation_no_models(self):
        """Test recommendation when no models trained"""
        comparator = ModelComparator("BTCUSDT", "60")

        comparator.lstm_predictor.model = None
        comparator.gru_predictor.model = None

        recommendation = comparator.get_recommendation()

        assert "NONE" in recommendation

    def test_recommendation_only_lstm(self):
        """Test recommendation when only LSTM trained"""
        comparator = ModelComparator("BTCUSDT", "60")

        comparator.lstm_predictor.model = MagicMock()
        comparator.gru_predictor.model = None

        recommendation = comparator.get_recommendation()

        assert "LSTM" in recommendation

    def test_recommendation_only_gru(self):
        """Test recommendation when only GRU trained"""
        comparator = ModelComparator("BTCUSDT", "60")

        comparator.lstm_predictor.model = None
        comparator.gru_predictor.model = MagicMock()

        recommendation = comparator.get_recommendation()

        assert "GRU" in recommendation

    def test_recommendation_both_models_lstm_better(self):
        """Test recommendation when LSTM performs better"""
        comparator = ModelComparator("BTCUSDT", "60")

        comparator.lstm_predictor.model = MagicMock()
        comparator.gru_predictor.model = MagicMock()

        comparator.lstm_predictor.last_trained = datetime.now()
        comparator.gru_predictor.last_trained = datetime.now()

        comparator.lstm_predictor.model_version = "v1"
        comparator.gru_predictor.model_version = "v1"

        # LSTM better metrics
        comparator.lstm_predictor.training_stats = {
            'rmse': 100.0,
            'mae': 80.0,
            'r2_score': 0.95,
            'directional_accuracy': 0.85
        }

        comparator.gru_predictor.training_stats = {
            'rmse': 150.0,
            'mae': 120.0,
            'r2_score': 0.80,
            'directional_accuracy': 0.70
        }

        recommendation = comparator.get_recommendation()

        assert "LSTM" in recommendation

    def test_recommendation_both_models_gru_better(self):
        """Test recommendation when GRU performs better"""
        comparator = ModelComparator("BTCUSDT", "60")

        comparator.lstm_predictor.model = MagicMock()
        comparator.gru_predictor.model = MagicMock()

        comparator.lstm_predictor.last_trained = datetime.now()
        comparator.gru_predictor.last_trained = datetime.now()

        comparator.lstm_predictor.model_version = "v1"
        comparator.gru_predictor.model_version = "v1"

        # GRU better metrics
        comparator.lstm_predictor.training_stats = {
            'rmse': 150.0,
            'mae': 120.0,
            'r2_score': 0.80,
            'directional_accuracy': 0.70
        }

        comparator.gru_predictor.training_stats = {
            'rmse': 100.0,
            'mae': 80.0,
            'r2_score': 0.95,
            'directional_accuracy': 0.85
        }

        recommendation = comparator.get_recommendation()

        assert "GRU" in recommendation


class TestFactoryEdgeCases:
    """Test edge cases for factory and comparator"""

    def test_factory_with_whitespace(self):
        """Test factory handles whitespace in model type"""
        predictor = PredictorFactory.create_predictor(" LSTM ", "BTCUSDT", "60")

        # Should strip whitespace
        assert isinstance(predictor, LSTMPricePredictor)

    def test_comparator_with_different_symbols(self):
        """Test comparator with various symbols"""
        for symbol in ["BTCUSDT", "ETHUSDT", "BTC-USDT", "ETH/USDT"]:
            comparator = ModelComparator(symbol, "60")
            assert comparator.symbol == symbol

    def test_comparator_with_different_intervals(self):
        """Test comparator with various intervals"""
        for interval in ["1", "5", "15", "60", "240", "D"]:
            comparator = ModelComparator("BTCUSDT", interval)
            assert comparator.interval == interval
