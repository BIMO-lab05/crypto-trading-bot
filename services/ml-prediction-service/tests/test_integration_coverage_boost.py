"""
Integration tests to boost coverage for ml-prediction-service
Focus on testing actual code paths without complex mocking
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))

from app.predictor import LSTMPricePredictor
from app.ml_models.gru_predictor import GRUPricePredictor
from app.models import PricePoint, PricePrediction


@pytest.fixture
def sample_data():
    """Generate sample OHLCV data as pandas DataFrame"""
    dates = pd.date_range(start='2025-01-01', periods=200, freq='1h')
    base_price = 50000.0

    data = {
        'timestamp': [int(d.timestamp() * 1000) for d in dates],
        'open': [],
        'high': [],
        'low': [],
        'close': [],
        'volume': []
    }

    current_price = base_price
    for i in range(200):
        change = np.random.normal(0, 500)
        current_price += change

        open_price = current_price
        high_price = open_price + abs(np.random.normal(0, 200))
        low_price = open_price - abs(np.random.normal(0, 200))
        close_price = (open_price + high_price + low_price) / 3 + np.random.normal(0, 100)
        volume = abs(np.random.normal(1000000, 200000))

        data['open'].append(open_price)
        data['high'].append(high_price)
        data['low'].append(low_price)
        data['close'].append(close_price)
        data['volume'].append(volume)

    return pd.DataFrame(data)


class TestLSTMPredictorIntegration:
    """Integration tests for LSTM predictor"""

    def test_create_features_with_dataframe(self, sample_data):
        """Test feature creation with DataFrame input"""
        predictor = LSTMPricePredictor("BTCUSDT", "60")
        df = predictor._create_features(sample_data)

        # Should have reduced rows due to NaN dropping
        assert len(df) < len(sample_data)
        assert len(df) > 100  # But still substantial

        # Check key features exist
        assert 'return_1' in df.columns
        assert 'sma_7' in df.columns
        assert 'rsi_14' in df.columns

        # No NaN values after processing
        assert not df.isnull().any().any()

    def test_create_features_with_list(self):
        """Test feature creation with list input"""
        predictor = LSTMPricePredictor("ETHUSDT", "60")

        # Create list of dicts
        data = []
        for i in range(100):
            data.append({
                'timestamp': int((datetime.now() + timedelta(hours=i)).timestamp() * 1000),
                'open': 3000 + i,
                'high': 3020 + i,
                'low': 2980 + i,
                'close': 3010 + i,
                'volume': 1000000
            })

        df = predictor._create_features(data)

        assert isinstance(df, pd.DataFrame)
        assert len(df) > 50
        assert 'return_1' in df.columns

    def test_calculate_rsi(self, sample_data):
        """Test RSI calculation"""
        predictor = LSTMPricePredictor("BTCUSDT", "60")
        rsi = predictor._calculate_rsi(sample_data['close'], 14)

        # RSI should be between 0 and 100
        assert rsi.dropna().min() >= 0
        assert rsi.dropna().max() <= 100

    def test_prepare_sequences(self, sample_data):
        """Test sequence preparation for training"""
        predictor = LSTMPricePredictor("BTCUSDT", "60")
        df = predictor._create_features(sample_data)
        X, y = predictor._prepare_sequences(df)

        # Check shapes
        assert len(X.shape) == 3  # (samples, sequence_length, features)
        assert len(y.shape) == 2  # (samples, prediction_horizon)
        assert X.shape[0] == y.shape[0]  # Same number of samples
        assert X.shape[1] == predictor.sequence_length
        assert y.shape[1] == predictor.prediction_horizon

    @patch('app.predictor.keras')
    def test_build_lstm_model(self, mock_keras):
        """Test model building"""
        predictor = LSTMPricePredictor("BTCUSDT", "60")

        # Create mock model
        mock_model = MagicMock()
        mock_keras.Sequential.return_value = mock_model
        mock_keras.layers.LSTM = MagicMock()
        mock_keras.layers.Dense = MagicMock()
        mock_keras.layers.Dropout = MagicMock()
        mock_keras.optimizers.Adam = MagicMock()

        model = predictor._build_lstm_model((60, 15))

        assert mock_keras.Sequential.called
        assert mock_keras.layers.LSTM.called
        assert mock_keras.layers.Dense.called

    def test_needs_retraining_no_training(self):
        """Test retraining flag when never trained"""
        predictor = LSTMPricePredictor("BTCUSDT", "60")
        assert predictor.needs_retraining() == True

    def test_needs_retraining_recent(self):
        """Test retraining flag with recent training"""
        predictor = LSTMPricePredictor("BTCUSDT", "60")
        predictor.last_trained = datetime.utcnow()
        assert predictor.needs_retraining() == False

    def test_needs_retraining_old(self):
        """Test retraining flag with old training"""
        predictor = LSTMPricePredictor("BTCUSDT", "60")
        predictor.last_trained = datetime.utcnow() - timedelta(days=100)
        assert predictor.needs_retraining() == True


class TestGRUPredictorIntegration:
    """Integration tests for GRU predictor"""

    def test_create_features_with_dataframe(self, sample_data):
        """Test GRU feature creation with DataFrame"""
        predictor = GRUPricePredictor("BTCUSDT", "60")
        df = predictor._create_features(sample_data)

        assert len(df) < len(sample_data)
        assert 'return_1' in df.columns
        assert 'rsi_14' in df.columns
        assert not df.isnull().any().any()

    def test_create_features_with_list(self):
        """Test GRU feature creation with list"""
        predictor = GRUPricePredictor("ETHUSDT", "60")

        data = []
        for i in range(100):
            data.append({
                'timestamp': int((datetime.now() + timedelta(hours=i)).timestamp() * 1000),
                'open': 3000 + i,
                'high': 3020 + i,
                'low': 2980 + i,
                'close': 3010 + i,
                'volume': 1000000
            })

        df = predictor._create_features(data)

        assert isinstance(df, pd.DataFrame)
        assert len(df) > 50

    def test_prepare_sequences(self, sample_data):
        """Test GRU sequence preparation"""
        predictor = GRUPricePredictor("BTCUSDT", "60")
        df = predictor._create_features(sample_data)
        X, y = predictor._prepare_sequences(df)

        assert len(X.shape) == 3
        assert len(y.shape) == 2
        assert X.shape[1] == predictor.sequence_length

    @patch('app.ml_models.gru_predictor.keras')
    def test_build_gru_model(self, mock_keras):
        """Test GRU model building"""
        predictor = GRUPricePredictor("BTCUSDT", "60")

        mock_model = MagicMock()
        mock_keras.Sequential.return_value = mock_model
        mock_keras.layers.GRU = MagicMock()
        mock_keras.layers.Dense = MagicMock()
        mock_keras.layers.Dropout = MagicMock()
        mock_keras.optimizers.Adam = MagicMock()

        model = predictor._build_gru_model((60, 15))

        assert mock_keras.Sequential.called
        assert mock_keras.layers.GRU.called

    def test_needs_retraining(self):
        """Test GRU retraining logic"""
        predictor = GRUPricePredictor("BTCUSDT", "60")
        assert predictor.needs_retraining() == True

        predictor.last_trained = datetime.utcnow()
        assert predictor.needs_retraining() == False

    def test_get_model_path(self):
        """Test GRU model path generation"""
        predictor = GRUPricePredictor("BTCUSDT", "60")
        path = predictor._get_model_path()

        assert "BTCUSDT" in str(path)
        assert "60m_gru" in str(path)
        assert str(path).endswith(".keras")

    def test_get_metadata_path(self):
        """Test GRU metadata path generation"""
        predictor = GRUPricePredictor("BTCUSDT", "60")
        path = predictor._get_metadata_path()

        assert "BTCUSDT" in str(path)
        assert "gru_metadata" in str(path)
        assert str(path).endswith(".json")


class TestPredictorComparison:
    """Test LSTM vs GRU similarities"""

    def test_same_feature_engineering(self, sample_data):
        """Both predictors should create same features"""
        lstm = LSTMPricePredictor("BTCUSDT", "60")
        gru = GRUPricePredictor("BTCUSDT", "60")

        lstm_features = lstm._create_features(sample_data)
        gru_features = gru._create_features(sample_data)

        # Should have same columns
        assert set(lstm_features.columns) == set(gru_features.columns)
        assert len(lstm_features) == len(gru_features)

    def test_same_sequence_preparation(self, sample_data):
        """Both should prepare sequences similarly"""
        lstm = LSTMPricePredictor("BTCUSDT", "60")
        gru = GRUPricePredictor("BTCUSDT", "60")

        lstm_df = lstm._create_features(sample_data)
        gru_df = gru._create_features(sample_data)

        lstm_X, lstm_y = lstm._prepare_sequences(lstm_df)
        gru_X, gru_y = gru._prepare_sequences(gru_df)

        # Shapes should match
        assert lstm_X.shape == gru_X.shape
        assert lstm_y.shape == gru_y.shape


class TestErrorHandling:
    """Test error handling in predictors"""

    def test_predict_without_model_lstm(self, sample_data):
        """LSTM should raise error when predicting without trained model"""
        predictor = LSTMPricePredictor("BTCUSDT", "60")
        predictor.model = None

        with pytest.raises(RuntimeError, match="Model not available"):
            import asyncio
            asyncio.run(predictor.predict(sample_data))

    def test_predict_without_model_gru(self, sample_data):
        """GRU should raise error when predicting without trained model"""
        predictor = GRUPricePredictor("BTCUSDT", "60")
        predictor.model = None

        with pytest.raises(RuntimeError, match="not available"):
            import asyncio
            asyncio.run(predictor.predict(sample_data))

    def test_predict_insufficient_data_lstm(self):
        """LSTM should raise error with insufficient data"""
        predictor = LSTMPricePredictor("BTCUSDT", "60")
        predictor.model = MagicMock()

        # Only 10 candles, need 60+
        small_data = pd.DataFrame({
            'timestamp': range(10),
            'open': [50000] * 10,
            'high': [51000] * 10,
            'low': [49000] * 10,
            'close': [50500] * 10,
            'volume': [1000000] * 10
        })

        with pytest.raises(ValueError, match="Need at least"):
            import asyncio
            asyncio.run(predictor.predict(small_data))

    def test_predict_insufficient_data_gru(self):
        """GRU should raise error with insufficient data"""
        predictor = GRUPricePredictor("BTCUSDT", "60")
        predictor.model = MagicMock()

        small_data = pd.DataFrame({
            'timestamp': range(10),
            'open': [50000] * 10,
            'high': [51000] * 10,
            'low': [49000] * 10,
            'close': [50500] * 10,
            'volume': [1000000] * 10
        })

        with pytest.raises(ValueError, match="Need at least"):
            import asyncio
            asyncio.run(predictor.predict(small_data))


class TestDataTypeHandling:
    """Test different data type inputs"""

    def test_lstm_with_dict_list(self):
        """Test LSTM with list of dictionaries"""
        predictor = LSTMPricePredictor("BTCUSDT", "60")

        data = [
            {
                'timestamp': i * 3600000,
                'open': 50000 + i,
                'high': 50100 + i,
                'low': 49900 + i,
                'close': 50050 + i,
                'volume': 1000000
            }
            for i in range(100)
        ]

        df = predictor._create_features(data)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 50

    def test_gru_with_dict_list(self):
        """Test GRU with list of dictionaries"""
        predictor = GRUPricePredictor("BTCUSDT", "60")

        data = [
            {
                'timestamp': i * 3600000,
                'open': 50000 + i,
                'high': 50100 + i,
                'low': 49900 + i,
                'close': 50050 + i,
                'volume': 1000000
            }
            for i in range(100)
        ]

        df = predictor._create_features(data)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 50

    def test_dataframe_preserved(self, sample_data):
        """Test that DataFrame input doesn't modify original"""
        predictor = LSTMPricePredictor("BTCUSDT", "60")
        original_len = len(sample_data)

        df = predictor._create_features(sample_data)

        # Original should be unchanged
        assert len(sample_data) == original_len
        # Result should be different
        assert len(df) != original_len


class TestModelMetadata:
    """Test model metadata handling"""

    def test_lstm_get_model_path(self):
        """Test LSTM model path construction"""
        predictor = LSTMPricePredictor("ETHUSDT", "240")
        path = predictor._get_model_path()

        assert "ETHUSDT" in str(path)
        assert "240m" in str(path)
        assert "lstm" in str(path)

    def test_gru_different_from_lstm_path(self):
        """Test that GRU and LSTM have different paths"""
        lstm = LSTMPricePredictor("BTCUSDT", "60")
        gru = GRUPricePredictor("BTCUSDT", "60")

        lstm_path = str(lstm._get_model_path())
        gru_path = str(gru._get_model_path())

        assert lstm_path != gru_path
        assert "lstm" in lstm_path
        assert "gru" in gru_path
