"""
Tests for LSTM Price Predictor
Tests feature engineering, model building, training, and prediction
"""
import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from app.predictor import LSTMPricePredictor
from app.config import get_settings


@pytest.fixture
def sample_ohlcv_data():
    """
    Creates sample OHLCV data for testing
    Returns 100 candles with realistic price movements
    """
    dates = pd.date_range(start='2025-01-01', periods=100, freq='1h')
    base_price = 50000.0

    # Generate synthetic price data with trend
    prices = []
    current_price = base_price
    for _ in range(100):
        change = np.random.normal(0, 500)  # Random walk
        current_price += change
        prices.append(current_price)

    data = []
    for i, date in enumerate(dates):
        open_price = prices[i]
        high_price = open_price + abs(np.random.normal(0, 200))
        low_price = open_price - abs(np.random.normal(0, 200))
        close_price = (open_price + high_price + low_price) / 3 + np.random.normal(0, 100)
        volume = abs(np.random.normal(1000000, 200000))

        data.append({
            'timestamp': int(date.timestamp() * 1000),
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': volume
        })

    return data


@pytest.fixture
def predictor():
    """
    Creates a predictor instance for testing
    """
    return LSTMPricePredictor(symbol="BTCUSDT", interval="60")


class TestLSTMPricePredictor:
    """Test suite for LSTM price predictor"""

    def test_initialization(self, predictor):
        """
        Test that predictor initializes with correct parameters
        """
        assert predictor.symbol == "BTCUSDT"
        assert predictor.interval == "60"
        assert predictor.sequence_length == 60
        assert predictor.prediction_horizon == 5
        assert predictor.model is None
        assert predictor.price_scaler is not None
        assert predictor.feature_scaler is not None

    def test_create_features(self, predictor, sample_ohlcv_data):
        """
        Test feature engineering from OHLCV data
        Should create 15+ technical features
        """
        df = predictor._create_features(sample_ohlcv_data)

        # Check DataFrame structure
        assert isinstance(df, pd.DataFrame)
        assert len(df) == len(sample_ohlcv_data)

        # Check basic OHLCV columns
        assert 'open' in df.columns
        assert 'high' in df.columns
        assert 'low' in df.columns
        assert 'close' in df.columns
        assert 'volume' in df.columns

        # Check engineered features
        assert 'returns' in df.columns
        assert 'log_returns' in df.columns
        assert 'volatility' in df.columns
        assert 'rsi' in df.columns
        assert 'macd' in df.columns
        assert 'bb_position' in df.columns

        # Check feature values are valid (no NaN after dropna)
        assert not df['returns'].isna().any()
        assert not df['rsi'].isna().any()

        # Check RSI is in valid range (0-100)
        assert df['rsi'].min() >= 0
        assert df['rsi'].max() <= 100

    def test_create_sequences(self, predictor, sample_ohlcv_data):
        """
        Test sequence creation for LSTM input
        Should create X (sequences) and y (targets) arrays
        """
        df = predictor._create_features(sample_ohlcv_data)
        X, y = predictor._create_sequences(df)

        # Check shapes
        assert isinstance(X, np.ndarray)
        assert isinstance(y, np.ndarray)
        assert len(X.shape) == 3  # (samples, sequence_length, features)
        assert len(y.shape) == 2  # (samples, prediction_horizon)

        # Check sequence length
        assert X.shape[1] == predictor.sequence_length

        # Check prediction horizon
        assert y.shape[1] == predictor.prediction_horizon

        # Check number of samples matches
        assert X.shape[0] == y.shape[0]

        # Check feature count (should be at least 15)
        assert X.shape[2] >= 15

    @patch('app.predictor.keras')
    def test_build_lstm_model(self, mock_keras, predictor):
        """
        Test LSTM model architecture building
        Should create 2-layer LSTM with dropout
        """
        # Mock keras components
        mock_sequential = MagicMock()
        mock_keras.Sequential.return_value = mock_sequential
        mock_keras.layers.LSTM = MagicMock()
        mock_keras.layers.Dropout = MagicMock()
        mock_keras.layers.Dense = MagicMock()

        # Build model
        input_shape = (60, 15)  # (sequence_length, num_features)
        model = predictor._build_lstm_model(input_shape)

        # Check Sequential was called
        mock_keras.Sequential.assert_called_once()

        # Check LSTM layers were added (2 layers)
        assert mock_keras.layers.LSTM.call_count >= 2

        # Check Dropout was added (for regularization)
        assert mock_keras.layers.Dropout.call_count >= 1

        # Check Dense output layer was added
        mock_keras.layers.Dense.assert_called()

    @patch('app.predictor.requests.get')
    def test_train_success(self, mock_get, predictor, sample_ohlcv_data):
        """
        Test successful model training
        Should fetch data, train model, and return metrics
        """
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_ohlcv_data
        mock_get.return_value = mock_response

        # Mock model training (skip actual training)
        with patch.object(predictor, '_build_lstm_model') as mock_build:
            mock_model = MagicMock()
            mock_model.fit.return_value = MagicMock()
            mock_build.return_value = mock_model

            # Train
            result = predictor.train(lookback_days=1)

            # Check result structure
            assert isinstance(result, dict)
            assert 'status' in result
            assert result['status'] == 'success'
            assert 'model_version' in result
            assert 'training_samples' in result

            # Check model was built and trained
            mock_build.assert_called_once()
            mock_model.fit.assert_called_once()

            # Check model is now set
            assert predictor.model is not None

    @patch('app.predictor.requests.get')
    def test_train_insufficient_data(self, mock_get, predictor):
        """
        Test training with insufficient data
        Should return error
        """
        # Mock API response with too little data
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {'timestamp': 1234567890000, 'open': 50000, 'high': 50100,
             'low': 49900, 'close': 50050, 'volume': 1000}
        ]  # Only 1 candle
        mock_get.return_value = mock_response

        # Train
        result = predictor.train(lookback_days=1)

        # Check error result
        assert isinstance(result, dict)
        assert 'status' in result
        assert result['status'] == 'error'
        assert 'error' in result

    def test_predict_without_trained_model(self, predictor):
        """
        Test prediction before model is trained
        Should raise ValueError
        """
        with pytest.raises(ValueError, match="Model not trained"):
            predictor.predict()

    @patch('app.predictor.requests.get')
    def test_predict_with_trained_model(self, mock_get, predictor, sample_ohlcv_data):
        """
        Test price prediction with trained model
        Should return multi-step predictions
        """
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_ohlcv_data
        mock_get.return_value = mock_response

        # Mock trained model
        mock_model = MagicMock()
        # Return shape: (1, prediction_horizon)
        mock_predictions = np.array([[0.5, 0.52, 0.54, 0.53, 0.55]])
        mock_model.predict.return_value = mock_predictions
        predictor.model = mock_model

        # Mock scalers
        predictor.is_trained = True
        predictor.last_actual_price = 50000.0

        # Predict
        result = predictor.predict()

        # Check result structure
        assert isinstance(result, dict)
        assert 'predictions' in result
        assert 'trend' in result
        assert 'confidence' in result

        # Check predictions array
        predictions = result['predictions']
        assert isinstance(predictions, list)
        assert len(predictions) == predictor.prediction_horizon

        # Check trend classification
        assert result['trend'] in ['BULLISH', 'BEARISH', 'NEUTRAL']

        # Check confidence score
        assert 0 <= result['confidence'] <= 1.0

    def test_classify_trend_bullish(self, predictor):
        """
        Test trend classification for bullish predictions
        """
        predictions = [50000, 50500, 51000, 51500, 52000]  # Strong uptrend
        trend, confidence = predictor._classify_trend(predictions)

        assert trend == 'BULLISH'
        assert confidence > 0.7  # High confidence

    def test_classify_trend_bearish(self, predictor):
        """
        Test trend classification for bearish predictions
        """
        predictions = [50000, 49500, 49000, 48500, 48000]  # Strong downtrend
        trend, confidence = predictor._classify_trend(predictions)

        assert trend == 'BEARISH'
        assert confidence > 0.7  # High confidence

    def test_classify_trend_neutral(self, predictor):
        """
        Test trend classification for neutral/ranging predictions
        """
        predictions = [50000, 50100, 49900, 50050, 49950]  # Sideways
        trend, confidence = predictor._classify_trend(predictions)

        assert trend == 'NEUTRAL'
        assert confidence < 0.7  # Low confidence for neutral

    def test_save_and_load_model(self, predictor, tmp_path):
        """
        Test model saving and loading
        Should persist model to disk and reload correctly
        """
        # Create a mock trained model
        mock_model = MagicMock()
        predictor.model = mock_model
        predictor.is_trained = True
        predictor.model_version = "v20251110_120000"

        # Mock save/load
        with patch('app.predictor.keras') as mock_keras:
            # Save
            save_path = tmp_path / "test_model"
            predictor._save_model(str(save_path))

            # Check save was called
            mock_model.save.assert_called_once()

            # Load
            predictor_new = LSTMPricePredictor(symbol="BTCUSDT", interval="60")
            predictor_new._load_model(str(save_path))

            # Check load was called
            mock_keras.models.load_model.assert_called_once()

    def test_calculate_volatility_forecast(self, predictor):
        """
        Test volatility forecasting
        Should return volatility estimate
        """
        predictions = [50000, 50500, 49800, 51200, 50300]
        volatility = predictor._calculate_volatility_forecast(predictions)

        assert isinstance(volatility, float)
        assert volatility > 0  # Volatility should be positive

    def test_get_model_info(self, predictor):
        """
        Test getting model information
        Should return metadata about trained model
        """
        # Without trained model
        info = predictor.get_model_info()
        assert info['is_trained'] == False
        assert info['model_version'] is None

        # With trained model
        predictor.is_trained = True
        predictor.model_version = "v20251110_120000"
        predictor.last_training_date = "2025-11-10"

        info = predictor.get_model_info()
        assert info['is_trained'] == True
        assert info['model_version'] == "v20251110_120000"
        assert info['symbol'] == "BTCUSDT"
        assert info['interval'] == "60"


class TestPredictorIntegration:
    """Integration tests for predictor with real-like data"""

    @pytest.mark.integration
    @patch('app.predictor.requests.get')
    def test_full_workflow(self, mock_get, sample_ohlcv_data):
        """
        Test complete workflow: init -> train -> predict
        Simulates real usage pattern
        """
        # Create predictor
        predictor = LSTMPricePredictor(symbol="BTCUSDT", interval="60")

        # Mock market data API
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_ohlcv_data
        mock_get.return_value = mock_response

        # Mock model training
        with patch.object(predictor, '_build_lstm_model') as mock_build:
            mock_model = MagicMock()
            mock_model.fit.return_value = MagicMock()
            mock_model.predict.return_value = np.array([[0.5, 0.52, 0.54, 0.53, 0.55]])
            mock_build.return_value = mock_model

            # Step 1: Train
            train_result = predictor.train(lookback_days=1)
            assert train_result['status'] == 'success'

            # Step 2: Get model info
            info = predictor.get_model_info()
            assert info['is_trained'] == True

            # Step 3: Predict
            prediction_result = predictor.predict()
            assert 'predictions' in prediction_result
            assert len(prediction_result['predictions']) == 5
            assert prediction_result['trend'] in ['BULLISH', 'BEARISH', 'NEUTRAL']


# Fixtures for pytest
@pytest.fixture(scope="session")
def settings():
    """Get settings for testing"""
    return get_settings()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
