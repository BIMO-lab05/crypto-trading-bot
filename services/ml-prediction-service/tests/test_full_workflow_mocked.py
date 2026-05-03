"""
Full workflow tests with proper TensorFlow mocking
These tests actually execute train() and predict() methods to boost coverage
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import sys
import asyncio
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))

from app.predictor import LSTMPricePredictor
from app.ml_models.gru_predictor import GRUPricePredictor


@pytest.fixture
def large_sample_data():
    """Generate large enough dataset for training"""
    dates = pd.date_range(start='2025-01-01', periods=500, freq='1h')
    data = {
        'timestamp': [int(d.timestamp() * 1000) for d in dates],
        'open': np.random.uniform(49000, 51000, 500),
        'high': np.random.uniform(51000, 52000, 500),
        'low': np.random.uniform(48000, 49000, 500),
        'close': np.random.uniform(49500, 50500, 500),
        'volume': np.random.uniform(900000, 1100000, 500)
    }
    return pd.DataFrame(data)


@pytest.fixture
def mock_keras_model():
    """Create a properly mocked Keras model"""
    mock_model = MagicMock()

    # Mock fit method
    mock_history = MagicMock()
    mock_history.history = {
        'loss': [0.5, 0.4, 0.3, 0.2, 0.1],
        'val_loss': [0.6, 0.5, 0.4, 0.3, 0.2],
        'mae': [100, 90, 80, 70, 60]
    }
    mock_model.fit.return_value = mock_history

    # Mock predict method
    mock_model.predict.return_value = np.random.uniform(0.4, 0.6, (10, 5))

    # Mock save method
    mock_model.save = MagicMock()

    return mock_model


class TestLSTMFullWorkflow:
    """Test complete LSTM workflow with mocking"""

    @patch('app.predictor.TENSORFLOW_AVAILABLE', True)
    @patch('app.predictor.keras')
    @patch('app.predictor.r2_score')
    @patch('app.predictor.mean_absolute_error')
    @patch('app.predictor.mean_squared_error')
    def test_lstm_train_full_workflow(
        self,
        mock_mse,
        mock_mae,
        mock_r2,
        mock_keras,
        mock_keras_model,
        large_sample_data
    ):
        """Test full LSTM training workflow"""
        # Setup mocks
        mock_keras.Sequential.return_value = mock_keras_model
        mock_keras.layers = MagicMock()
        mock_keras.optimizers.Adam = MagicMock()
        mock_keras.callbacks.EarlyStopping = MagicMock()

        mock_mae.return_value = 100.0
        mock_mse.return_value = 150.0 ** 2
        mock_r2.return_value = 0.85

        # Create predictor
        predictor = LSTMPricePredictor("BTCUSDT", "60")

        # Train model
        result = asyncio.run(predictor.train(large_sample_data))

        # Verify training happened
        assert result is not None
        assert result.model_type == "LSTM"
        assert result.validation_mae == 100.0
        assert result.validation_rmse == 150.0
        assert result.validation_r2_score == 0.85

    @patch('app.predictor.TENSORFLOW_AVAILABLE', True)
    @patch('app.predictor.keras')
    def test_lstm_predict_full_workflow(
        self,
        mock_keras,
        mock_keras_model,
        large_sample_data
    ):
        """Test full LSTM prediction workflow"""
        # Setup mocks
        mock_keras.models.load_model = MagicMock(return_value=mock_keras_model)

        # Create predictor with trained model
        predictor = LSTMPricePredictor("BTCUSDT", "60")
        predictor.model = mock_keras_model
        predictor.model_version = "v1"
        predictor.last_trained = datetime.utcnow()
        predictor.training_stats = {
            'r2_score': 0.85,
            'rmse': 150.0,
            'mae': 100.0
        }

        # Mock prediction
        mock_keras_model.predict.return_value = np.array([[0.5, 0.52, 0.54, 0.53, 0.55]])

        # Make prediction
        result = asyncio.run(predictor.predict(large_sample_data))

        # Verify prediction
        assert result is not None
        assert result.symbol == "BTCUSDT"
        assert len(result.predictions) == 5
        assert result.predicted_direction in ["UP", "DOWN", "SIDEWAYS"]

    @patch('app.predictor.TENSORFLOW_AVAILABLE', True)
    def test_lstm_train_insufficient_data(self):
        """Test LSTM training with insufficient data"""
        predictor = LSTMPricePredictor("BTCUSDT", "60")

        # Only 50 rows - not enough after feature engineering
        small_data = pd.DataFrame({
            'timestamp': range(50),
            'open': [50000] * 50,
            'high': [51000] * 50,
            'low': [49000] * 50,
            'close': [50500] * 50,
            'volume': [1000000] * 50
        })

        # Should fail due to insufficient data
        with pytest.raises((ValueError, IndexError)):
            asyncio.run(predictor.train(small_data))


class TestGRUFullWorkflow:
    """Test complete GRU workflow with mocking"""

    @patch('app.ml_models.gru_predictor.TENSORFLOW_AVAILABLE', True)
    @patch('app.ml_models.gru_predictor.keras')
    @patch('app.ml_models.gru_predictor.r2_score')
    @patch('app.ml_models.gru_predictor.mean_absolute_error')
    @patch('app.ml_models.gru_predictor.mean_squared_error')
    def test_gru_train_full_workflow(
        self,
        mock_mse,
        mock_mae,
        mock_r2,
        mock_keras,
        mock_keras_model,
        large_sample_data
    ):
        """Test full GRU training workflow"""
        # Setup mocks
        mock_keras.Sequential.return_value = mock_keras_model
        mock_keras.layers = MagicMock()
        mock_keras.optimizers.Adam = MagicMock()
        mock_keras.callbacks.EarlyStopping = MagicMock()

        mock_mae.return_value = 95.0
        mock_mse.return_value = 140.0 ** 2
        mock_r2.return_value = 0.87

        # Create predictor
        predictor = GRUPricePredictor("BTCUSDT", "60")

        # Train model
        result = asyncio.run(predictor.train(large_sample_data))

        # Verify training
        assert result is not None
        assert result.model_type == "GRU"
        assert result.validation_mae == 95.0
        assert result.validation_rmse == 140.0

    @patch('app.ml_models.gru_predictor.TENSORFLOW_AVAILABLE', True)
    @patch('app.ml_models.gru_predictor.keras')
    def test_gru_predict_full_workflow(
        self,
        mock_keras,
        mock_keras_model,
        large_sample_data
    ):
        """Test full GRU prediction workflow"""
        # Setup mocks
        mock_keras.models.load_model = MagicMock(return_value=mock_keras_model)

        # Create predictor
        predictor = GRUPricePredictor("BTCUSDT", "60")
        predictor.model = mock_keras_model
        predictor.model_version = "v1"
        predictor.last_trained = datetime.utcnow()
        predictor.training_stats = {
            'r2_score': 0.87,
            'rmse': 140.0,
            'mae': 95.0
        }

        # Mock prediction
        mock_keras_model.predict.return_value = np.array([[0.48, 0.50, 0.52, 0.51, 0.53]])

        # Make prediction
        result = asyncio.run(predictor.predict(large_sample_data))

        # Verify
        assert result is not None
        assert result.symbol == "BTCUSDT"
        assert len(result.predictions) == 5


class TestModelPersistence:
    """Test model saving and loading"""

    @patch('app.predictor.TENSORFLOW_AVAILABLE', True)
    @patch('app.predictor.keras')
    @patch('builtins.open', new_callable=MagicMock)
    @patch('pathlib.Path.exists')
    def test_lstm_save_model(
        self,
        mock_exists,
        mock_open,
        mock_keras,
        mock_keras_model
    ):
        """Test LSTM model saving"""
        mock_exists.return_value = False

        predictor = LSTMPricePredictor("BTCUSDT", "60")
        predictor.model = mock_keras_model
        predictor.model_version = "v1"
        predictor.last_trained = datetime.utcnow()
        predictor.training_stats = {"mae": 100.0}

        # Call save
        predictor._save_model()

        # Verify save was called
        mock_keras_model.save.assert_called_once()

    @patch('app.ml_models.gru_predictor.TENSORFLOW_AVAILABLE', True)
    @patch('app.ml_models.gru_predictor.keras')
    @patch('builtins.open', new_callable=MagicMock)
    @patch('pathlib.Path.exists')
    def test_gru_save_model(
        self,
        mock_exists,
        mock_open,
        mock_keras,
        mock_keras_model
    ):
        """Test GRU model saving"""
        mock_exists.return_value = False

        predictor = GRUPricePredictor("BTCUSDT", "60")
        predictor.model = mock_keras_model
        predictor.model_version = "v1"
        predictor.last_trained = datetime.utcnow()
        predictor.training_stats = {"mae": 95.0}

        # Call save
        predictor._save_model()

        # Verify
        mock_keras_model.save.assert_called_once()


class TestTensorFlowUnavailable:
    """Test behavior when TensorFlow is not available"""

    @patch('app.predictor.TENSORFLOW_AVAILABLE', False)
    def test_lstm_train_no_tensorflow(self, large_sample_data):
        """Test LSTM training fails without TensorFlow"""
        predictor = LSTMPricePredictor("BTCUSDT", "60")

        with pytest.raises(RuntimeError, match="TensorFlow not available"):
            asyncio.run(predictor.train(large_sample_data))

    @patch('app.ml_models.gru_predictor.TENSORFLOW_AVAILABLE', False)
    def test_gru_train_no_tensorflow(self, large_sample_data):
        """Test GRU training fails without TensorFlow"""
        predictor = GRUPricePredictor("BTCUSDT", "60")

        with pytest.raises(RuntimeError, match="TensorFlow not available"):
            asyncio.run(predictor.train(large_sample_data))


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_lstm_with_list_input(self):
        """Test LSTM with list input to train"""
        predictor = LSTMPricePredictor("BTCUSDT", "60")

        data_list = [
            {
                'timestamp': i * 3600000,
                'open': 50000,
                'high': 51000,
                'low': 49000,
                'close': 50500,
                'volume': 1000000
            }
            for i in range(100)
        ]

        # Should convert list to DataFrame
        df = predictor._create_features(data_list)
        assert isinstance(df, pd.DataFrame)

    def test_gru_with_list_input(self):
        """Test GRU with list input"""
        predictor = GRUPricePredictor("BTCUSDT", "60")

        data_list = [
            {
                'timestamp': i * 3600000,
                'open': 50000,
                'high': 51000,
                'low': 49000,
                'close': 50500,
                'volume': 1000000
            }
            for i in range(100)
        ]

        df = predictor._create_features(data_list)
        assert isinstance(df, pd.DataFrame)
