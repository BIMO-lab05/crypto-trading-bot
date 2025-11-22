"""
Tests for GRU Price Predictor
Tests GRU architecture, training, prediction, and comparison with LSTM
"""
import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from app.ml_models.gru_model import GRUPricePredictor
from app.predictor import LSTMPricePredictor
from app.predictor_factory import PredictorFactory, ModelComparator
from app.config import get_settings


@pytest.fixture
def sample_ohlcv_data():
    """
    Creates sample OHLCV data for testing
    Returns 150 candles with realistic price movements for proper feature engineering
    """
    dates = pd.date_range(start='2025-01-01', periods=150, freq='1h')
    base_price = 50000.0

    # Generate synthetic price data with trend and volatility
    prices = []
    current_price = base_price
    for i in range(150):
        # Add trend + noise + volatility cycles
        trend = 10 * i  # Upward trend
        noise = np.random.normal(0, 500)  # Random walk
        cycle = 1000 * np.sin(i / 10)  # Cyclical pattern
        current_price = base_price + trend + noise + cycle
        prices.append(current_price)

    data = []
    for i, date in enumerate(dates):
        open_price = prices[i]
        high_price = open_price + abs(np.random.normal(0, 200))
        low_price = open_price - abs(np.random.normal(0, 200))
        close_price = (open_price + high_price + low_price) / 3 + np.random.normal(0, 100)
        volume = abs(np.random.normal(1000000, 200000))

        data.append({
            'timestamp': date,
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': volume
        })

    return pd.DataFrame(data)


@pytest.fixture
def gru_predictor():
    """Creates a GRU predictor instance for testing"""
    return GRUPricePredictor(symbol="BTCUSDT", interval="60")


@pytest.fixture
def lstm_predictor():
    """Creates an LSTM predictor instance for comparison"""
    return LSTMPricePredictor(symbol="BTCUSDT", interval="60")


class TestGRUPricePredictor:
    """Test suite for GRU price predictor"""

    def test_initialization(self, gru_predictor):
        """
        Test that GRU predictor initializes with correct parameters
        """
        assert gru_predictor.symbol == "BTCUSDT"
        assert gru_predictor.interval == "60"
        assert gru_predictor.sequence_length == 60
        assert gru_predictor.prediction_horizon == 5
        assert gru_predictor.model is None
        assert gru_predictor.price_scaler is not None
        assert gru_predictor.feature_scaler is not None
        assert gru_predictor.inference_time_ms == 0.0

    def test_create_features(self, gru_predictor, sample_ohlcv_data):
        """
        Test feature engineering from OHLCV data
        Should create 15+ technical features (same as LSTM for fair comparison)
        """
        df = gru_predictor._create_features(sample_ohlcv_data)

        # Check DataFrame structure
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0  # Some rows dropped due to NaN

        # Check basic OHLCV columns
        assert 'open' in df.columns
        assert 'high' in df.columns
        assert 'low' in df.columns
        assert 'close' in df.columns
        assert 'volume' in df.columns

        # Check engineered features
        assert 'return_1' in df.columns
        assert 'return_5' in df.columns
        assert 'return_10' in df.columns
        assert 'price_momentum_5' in df.columns
        assert 'sma_7' in df.columns
        assert 'sma_14' in df.columns
        assert 'ema_7' in df.columns
        assert 'volatility_10' in df.columns
        assert 'rsi_14' in df.columns
        assert 'volume_ratio' in df.columns

        # Check no NaN values after dropna
        assert not df.isnull().any().any()

        # Check RSI is in valid range (0-100)
        assert df['rsi_14'].min() >= 0
        assert df['rsi_14'].max() <= 100

        # Should have at least 15 features
        assert len(df.columns) >= 20  # OHLCV + 15+ engineered features

    def test_calculate_rsi(self, gru_predictor, sample_ohlcv_data):
        """Test RSI calculation"""
        rsi = gru_predictor._calculate_rsi(sample_ohlcv_data['close'], period=14)

        # RSI should be in range 0-100
        valid_rsi = rsi.dropna()
        assert valid_rsi.min() >= 0
        assert valid_rsi.max() <= 100

        # RSI should have expected length
        assert len(rsi) == len(sample_ohlcv_data)

    def test_prepare_sequences(self, gru_predictor, sample_ohlcv_data):
        """
        Test sequence preparation for GRU input
        Should create X (sequences) and y (targets) arrays
        """
        df = gru_predictor._create_features(sample_ohlcv_data)
        X, y = gru_predictor._prepare_sequences(df)

        # Check shapes
        assert isinstance(X, np.ndarray)
        assert isinstance(y, np.ndarray)
        assert len(X.shape) == 3  # (samples, sequence_length, features)
        assert len(y.shape) == 2  # (samples, prediction_horizon)

        # Check sequence length
        assert X.shape[1] == gru_predictor.sequence_length  # 60 timesteps

        # Check prediction horizon
        assert y.shape[1] == gru_predictor.prediction_horizon  # 5 steps

        # Check number of samples matches
        assert X.shape[0] == y.shape[0]

        # Check feature count (should be at least 15)
        assert X.shape[2] >= 15

        # Check values are scaled (between 0 and 1)
        assert X.min() >= 0
        assert X.max() <= 1.01

    @patch('app.ml_models.gru_model.TENSORFLOW_AVAILABLE', True)
    @patch('app.ml_models.gru_model.keras')
    def test_build_gru_model(self, mock_keras, gru_predictor):
        """
        Test GRU model architecture building
        Should create 2-layer GRU with dropout (fewer params than LSTM)
        """
        # Mock keras components
        mock_sequential = MagicMock()
        mock_keras.Sequential.return_value = mock_sequential
        mock_keras.layers.GRU = MagicMock()
        mock_keras.layers.Dropout = MagicMock()
        mock_keras.layers.Dense = MagicMock()

        # Build model
        input_shape = (60, 20)  # (sequence_length, num_features)
        model = gru_predictor._build_gru_model(input_shape)

        # Check Sequential was called
        mock_keras.Sequential.assert_called_once()

        # Check GRU layers were added (2 layers)
        assert mock_keras.layers.GRU.call_count == 2

        # Check first GRU layer returns sequences
        first_gru_call = mock_keras.layers.GRU.call_args_list[0]
        assert first_gru_call[1].get('return_sequences') == True
        assert first_gru_call[1].get('units') == 128

        # Check second GRU layer doesn't return sequences
        second_gru_call = mock_keras.layers.GRU.call_args_list[1]
        assert second_gru_call[1].get('return_sequences') == False
        assert second_gru_call[1].get('units') == 64

        # Check Dropout layers (at least 2 for regularization)
        assert mock_keras.layers.Dropout.call_count >= 2

        # Check Dense output layer
        mock_keras.layers.Dense.assert_called()

    @pytest.mark.asyncio
    @patch('app.ml_models.gru_model.TENSORFLOW_AVAILABLE', True)
    async def test_train_success(self, gru_predictor, sample_ohlcv_data):
        """
        Test successful GRU model training
        Should train model and return comprehensive metrics
        """
        # Mock TensorFlow/Keras
        with patch('app.ml_models.gru_model.keras') as mock_keras:
            # Mock model
            mock_model = MagicMock()
            mock_model.count_params.return_value = 50000  # GRU has fewer params than LSTM

            # Mock training history
            mock_history = MagicMock()
            mock_history.history = {
                'loss': [0.5, 0.4, 0.3, 0.25, 0.2],
                'val_loss': [0.55, 0.45, 0.35, 0.3, 0.25],
                'mae': [0.1, 0.09, 0.08, 0.07, 0.06],
                'val_mae': [0.11, 0.10, 0.09, 0.08, 0.07]
            }
            mock_model.fit.return_value = mock_history

            # Mock predictions for evaluation
            y_pred = np.random.random((20, 5))  # 20 samples, 5 predictions
            mock_model.predict.return_value = y_pred

            # Mock model building
            with patch.object(gru_predictor, '_build_gru_model', return_value=mock_model):
                # Train
                result = await gru_predictor.train(sample_ohlcv_data)

                # Check result structure
                assert result.model_type == 'GRU'
                assert result.status == 'READY'
                assert result.model_version is not None
                assert result.training_samples > 0
                assert result.training_duration_seconds > 0

                # Check metrics
                assert result.validation_mae > 0
                assert result.validation_rmse > 0
                assert -1 <= result.validation_r2_score <= 1

                # Check model was built and trained
                mock_model.fit.assert_called_once()

                # Check model is now set
                assert gru_predictor.model is not None

                # Check training stats were saved
                assert 'mae' in gru_predictor.training_stats
                assert 'rmse' in gru_predictor.training_stats
                assert 'r2_score' in gru_predictor.training_stats
                assert 'directional_accuracy' in gru_predictor.training_stats
                assert 'mape' in gru_predictor.training_stats

    @pytest.mark.asyncio
    @patch('app.ml_models.gru_model.TENSORFLOW_AVAILABLE', True)
    async def test_predict_success(self, gru_predictor, sample_ohlcv_data):
        """
        Test price prediction with trained GRU model
        Should return multi-step predictions with confidence intervals
        """
        # Mock trained model
        with patch('app.ml_models.gru_model.keras') as mock_keras:
            mock_model = MagicMock()

            # Return shape: (1, prediction_horizon)
            mock_predictions = np.array([[0.52, 0.54, 0.56, 0.55, 0.57]])
            mock_model.predict.return_value = mock_predictions

            gru_predictor.model = mock_model
            gru_predictor.model_version = "v20251111_120000"
            gru_predictor.last_trained = datetime.utcnow()
            gru_predictor.training_stats = {
                'r2_score': 0.85,
                'rmse': 100.0,
                'mae': 80.0,
                'directional_accuracy': 0.75
            }

            # Predict
            result = await gru_predictor.predict(sample_ohlcv_data)

            # Check result structure
            assert result.symbol == "BTCUSDT"
            assert result.interval == "60m"
            assert result.model_type == 'GRU'
            assert result.current_price > 0

            # Check predictions
            assert len(result.predictions) == gru_predictor.prediction_horizon
            for pred in result.predictions:
                assert pred.predicted_price > 0
                assert 0 <= pred.confidence <= 1
                assert pred.lower_bound < pred.predicted_price < pred.upper_bound

            # Check direction classification
            assert result.predicted_direction in ['UP', 'DOWN', 'SIDEWAYS']
            assert 0 <= result.directional_strength <= 1

            # Check inference time was recorded
            assert gru_predictor.inference_time_ms > 0

    def test_needs_retraining_new_model(self, gru_predictor):
        """Test that new model needs training"""
        assert gru_predictor.needs_retraining() == True

    def test_needs_retraining_recent_model(self, gru_predictor):
        """Test that recently trained model doesn't need retraining"""
        gru_predictor.last_trained = datetime.utcnow()
        assert gru_predictor.needs_retraining() == False

    def test_needs_retraining_old_model(self, gru_predictor):
        """Test that old model needs retraining"""
        gru_predictor.last_trained = datetime.utcnow() - timedelta(days=30)
        assert gru_predictor.needs_retraining() == True

    def test_get_performance_metrics(self, gru_predictor):
        """Test getting comprehensive performance metrics"""
        gru_predictor.model_version = "v20251111_120000"
        gru_predictor.last_trained = datetime.utcnow()
        gru_predictor.training_stats = {
            'mae': 80.0,
            'rmse': 100.0,
            'r2_score': 0.85,
            'total_parameters': 50000
        }
        gru_predictor.inference_time_ms = 15.5

        metrics = gru_predictor.get_performance_metrics()

        assert metrics['model_type'] == 'GRU'
        assert metrics['training_stats'] == gru_predictor.training_stats
        assert metrics['inference_time_ms'] == 15.5
        assert metrics['total_parameters'] == 50000


class TestPredictorFactory:
    """Test predictor factory"""

    def test_create_lstm_predictor(self):
        """Test creating LSTM predictor"""
        predictor = PredictorFactory.create_predictor('LSTM', 'BTCUSDT', '60')
        assert isinstance(predictor, LSTMPricePredictor)
        assert predictor.symbol == 'BTCUSDT'

    def test_create_gru_predictor(self):
        """Test creating GRU predictor"""
        predictor = PredictorFactory.create_predictor('GRU', 'BTCUSDT', '60')
        assert isinstance(predictor, GRUPricePredictor)
        assert predictor.symbol == 'BTCUSDT'

    def test_create_predictor_case_insensitive(self):
        """Test that model type is case insensitive"""
        predictor1 = PredictorFactory.create_predictor('gru', 'BTCUSDT', '60')
        predictor2 = PredictorFactory.create_predictor('GRU', 'BTCUSDT', '60')
        assert type(predictor1) == type(predictor2)

    def test_create_predictor_invalid_type(self):
        """Test that invalid model type raises error"""
        with pytest.raises(ValueError, match="Unsupported model type"):
            PredictorFactory.create_predictor('INVALID', 'BTCUSDT', '60')

    def test_get_supported_models(self):
        """Test getting list of supported models"""
        models = PredictorFactory.get_supported_models()
        assert 'LSTM' in models
        assert 'GRU' in models
        assert len(models) == 2


class TestModelComparator:
    """Test model comparison functionality"""

    def test_initialization(self):
        """Test comparator initialization"""
        comparator = ModelComparator('BTCUSDT', '60')
        assert comparator.symbol == 'BTCUSDT'
        assert comparator.interval == '60'
        assert isinstance(comparator.lstm_predictor, LSTMPricePredictor)
        assert isinstance(comparator.gru_predictor, GRUPricePredictor)

    @pytest.mark.asyncio
    async def test_compare_predictions_no_models(self, sample_ohlcv_data):
        """Test comparison when no models are trained"""
        comparator = ModelComparator('BTCUSDT', '60')
        result = await comparator.compare_predictions(sample_ohlcv_data)

        assert result['symbol'] == 'BTCUSDT'
        assert result['lstm'] is None or 'error' in result['lstm']
        assert result['gru'] is None or 'error' in result['gru']

    def test_get_recommendation_no_models(self):
        """Test recommendation when no models trained"""
        comparator = ModelComparator('BTCUSDT', '60')
        recommendation = comparator.get_recommendation()
        assert 'NONE' in recommendation

    def test_get_recommendation_lstm_only(self):
        """Test recommendation when only LSTM available"""
        comparator = ModelComparator('BTCUSDT', '60')
        comparator.lstm_predictor.model = MagicMock()
        recommendation = comparator.get_recommendation()
        assert 'LSTM' in recommendation

    def test_get_recommendation_gru_only(self):
        """Test recommendation when only GRU available"""
        comparator = ModelComparator('BTCUSDT', '60')
        comparator.gru_predictor.model = MagicMock()
        recommendation = comparator.get_recommendation()
        assert 'GRU' in recommendation

    def test_calculate_overall_score(self):
        """Test overall score calculation"""
        comparator = ModelComparator('BTCUSDT', '60')

        metrics = {
            'r2_score': 0.85,
            'directional_accuracy': 0.75,
            'rmse': 100.0,
            'mae': 80.0,
            'inference_time_ms': 15.0,
            'model_size_mb': 5.0
        }

        score = comparator._calculate_overall_score(metrics)

        # Score should be between 0 and 1
        assert 0 <= score <= 1

        # High R² and directional accuracy should give good score
        assert score > 0.5

    def test_calculate_overall_score_empty_metrics(self):
        """Test score calculation with empty metrics"""
        comparator = ModelComparator('BTCUSDT', '60')
        score = comparator._calculate_overall_score({})
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_compare_training_metrics(self):
        """Test training metrics comparison"""
        comparator = ModelComparator('BTCUSDT', '60')

        # Mock both models with training stats
        comparator.lstm_predictor.model = MagicMock()
        comparator.lstm_predictor.last_trained = datetime.utcnow()
        comparator.lstm_predictor.model_version = "v1"
        comparator.lstm_predictor.training_stats = {
            'rmse': 100.0,
            'mae': 80.0,
            'r2_score': 0.80,
            'total_parameters': 75000
        }

        comparator.gru_predictor.model = MagicMock()
        comparator.gru_predictor.last_trained = datetime.utcnow()
        comparator.gru_predictor.model_version = "v1"
        comparator.gru_predictor.training_stats = {
            'rmse': 95.0,
            'mae': 75.0,
            'r2_score': 0.82,
            'total_parameters': 50000  # GRU has fewer parameters
        }
        comparator.gru_predictor.inference_time_ms = 12.0

        result = await comparator.compare_training_metrics()

        # Check structure
        assert 'models' in result
        assert 'lstm' in result['models']
        assert 'gru' in result['models']
        assert 'winner' in result

        # Check winner determination
        assert 'rmse' in result['winner']
        assert 'parameters' in result['winner']
        assert 'overall' in result['winner']


class TestIntegration:
    """Integration tests for GRU model with full workflow"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    @patch('app.ml_models.gru_model.TENSORFLOW_AVAILABLE', True)
    async def test_full_gru_workflow(self, sample_ohlcv_data):
        """
        Test complete GRU workflow: init -> train -> predict -> compare
        """
        # Create predictor
        predictor = GRUPricePredictor(symbol="BTCUSDT", interval="60")

        # Mock TensorFlow
        with patch('app.ml_models.gru_model.keras') as mock_keras:
            mock_model = MagicMock()
            mock_model.count_params.return_value = 50000
            mock_model.fit.return_value = MagicMock(history={
                'loss': [0.3, 0.2],
                'val_loss': [0.35, 0.25]
            })
            mock_model.predict.return_value = np.array([[0.52, 0.54, 0.56, 0.55, 0.57]])

            with patch.object(predictor, '_build_gru_model', return_value=mock_model):
                # Step 1: Train
                train_result = await predictor.train(sample_ohlcv_data)
                assert train_result.status == 'READY'
                assert train_result.model_type == 'GRU'

                # Step 2: Check metrics
                assert predictor.training_stats['mae'] > 0
                assert predictor.training_stats['rmse'] > 0

                # Step 3: Predict
                prediction_result = await predictor.predict(sample_ohlcv_data)
                assert len(prediction_result.predictions) == 5
                assert prediction_result.model_type == 'GRU'

                # Step 4: Check performance metrics
                metrics = predictor.get_performance_metrics()
                assert metrics['model_type'] == 'GRU'
                assert metrics['inference_time_ms'] > 0


# Fixtures for pytest
@pytest.fixture(scope="session")
def settings():
    """Get settings for testing"""
    return get_settings()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
