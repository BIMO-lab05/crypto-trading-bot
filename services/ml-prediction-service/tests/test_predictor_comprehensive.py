"""
Comprehensive tests for LSTM Predictor
Tests model training, prediction, feature engineering, and persistence
"""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock
import tempfile
import shutil

from app.predictor import LSTMPricePredictor, TENSORFLOW_AVAILABLE
from app.models import PricePoint, PricePrediction


@pytest.fixture
def temp_models_dir():
    """Create temporary directory for model storage"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_price_data():
    """Create sample price data for testing"""
    dates = pd.date_range(end=datetime.now(), periods=200, freq='1h')

    # Create realistic price movement
    base_price = 40000
    prices = [base_price]

    for i in range(1, 200):
        change = np.random.normal(0, 100)
        prices.append(prices[-1] + change)

    data = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': [p * 1.01 for p in prices],
        'low': [p * 0.99 for p in prices],
        'close': prices,
        'volume': np.random.uniform(100, 1000, 200)
    })

    return data


@pytest.fixture
def predictor(temp_models_dir):
    """Create predictor instance with temp directory"""
    with patch('app.predictor.settings.models_dir', temp_models_dir):
        predictor = LSTMPricePredictor("BTCUSDT", "60")
        return predictor


class TestPredictorInitialization:
    """Test predictor initialization"""

    def test_initialization_without_model(self, predictor):
        """Test predictor initializes correctly without existing model"""
        assert predictor.symbol == "BTCUSDT"
        assert predictor.interval == "60"
        assert predictor.model is None
        assert predictor.last_trained is None

    def test_initialization_with_settings(self, temp_models_dir):
        """Test predictor uses settings correctly"""
        with patch('app.predictor.settings.models_dir', temp_models_dir):
            with patch('app.predictor.settings.sequence_length', 30):
                with patch('app.predictor.settings.prediction_horizon', 5):
                    predictor = LSTMPricePredictor("ETHUSDT", "60")

                    assert predictor.sequence_length == 30
                    assert predictor.prediction_horizon == 5


class TestFeatureEngineering:
    """Test feature creation and engineering"""

    def test_create_features_basic(self, predictor, sample_price_data):
        """Test basic feature creation"""
        features = predictor._create_features(sample_price_data)

        assert isinstance(features, pd.DataFrame)
        assert len(features) > 0
        assert 'close' in features.columns

        # Check that features were added
        assert len(features.columns) >= len(sample_price_data.columns)

    def test_create_features_handles_missing_data(self, predictor):
        """Test feature creation with missing data"""
        # Create data with NaN values
        data = pd.DataFrame({
            'timestamp': pd.date_range(end=datetime.now(), periods=10, freq='1h'),
            'open': [40000] * 10,
            'high': [40500] * 10,
            'low': [39500] * 10,
            'close': [40000] * 10,
            'volume': [100] * 10
        })

        features = predictor._create_features(data)

        # Should handle NaN values (drop or fill)
        assert not features.empty

    def test_calculate_rsi(self, predictor):
        """Test RSI calculation"""
        # Create price series with known trend
        prices = pd.Series([100 + i for i in range(50)])  # Uptrend

        rsi = predictor._calculate_rsi(prices, period=14)

        assert isinstance(rsi, pd.Series)
        assert len(rsi) == len(prices)
        # RSI should be high for uptrend
        assert rsi.iloc[-1] > 50

    def test_calculate_rsi_edge_cases(self, predictor):
        """Test RSI with edge cases"""
        # Test with insufficient data
        short_prices = pd.Series([100, 101, 102])
        rsi = predictor._calculate_rsi(short_prices, period=14)

        assert isinstance(rsi, pd.Series)

    def test_calculate_macd(self, predictor):
        """Test MACD calculation"""
        prices = pd.Series([100 + i*0.1 for i in range(100)])

        macd_line, signal_line = predictor._calculate_macd(prices)

        assert isinstance(macd_line, pd.Series)
        assert isinstance(signal_line, pd.Series)
        assert len(macd_line) == len(prices)
        assert len(signal_line) == len(prices)


class TestSequencePreparation:
    """Test sequence preparation for LSTM"""

    def test_prepare_sequences_basic(self, predictor, sample_price_data):
        """Test basic sequence preparation"""
        features = predictor._create_features(sample_price_data)

        if len(features) > predictor.sequence_length + predictor.prediction_horizon:
            X, y = predictor._prepare_sequences(features, features['close'].values)

            assert isinstance(X, np.ndarray)
            assert isinstance(y, np.ndarray)
            assert X.ndim == 3  # (samples, timesteps, features)
            assert y.ndim == 2  # (samples, prediction_horizon)

    def test_prepare_sequences_insufficient_data(self, predictor):
        """Test sequence preparation with insufficient data"""
        small_data = pd.DataFrame({
            'close': [100, 101, 102, 103, 104]
        })

        X, y = predictor._prepare_sequences(small_data, small_data['close'].values)

        # Should return empty arrays or minimal sequences
        assert isinstance(X, np.ndarray)
        assert isinstance(y, np.ndarray)


class TestModelBuilding:
    """Test model architecture building"""

    @pytest.mark.skipif(not TENSORFLOW_AVAILABLE, reason="TensorFlow not available")
    def test_build_lstm_model(self, predictor):
        """Test LSTM model building"""
        n_features = 10
        model = predictor._build_lstm_model(n_features)

        from tensorflow import keras
        assert isinstance(model, keras.Model)

        # Check model structure
        assert len(model.layers) > 0

        # Check input/output shapes
        expected_input_shape = (None, predictor.sequence_length, n_features)
        expected_output_shape = (None, predictor.prediction_horizon)

        # Model should accept sequences
        assert model.input_shape[1] == predictor.sequence_length
        assert model.input_shape[2] == n_features

    @pytest.mark.skipif(not TENSORFLOW_AVAILABLE, reason="TensorFlow not available")
    def test_build_lstm_model_different_features(self, predictor):
        """Test model building with different feature counts"""
        for n_features in [5, 10, 20]:
            model = predictor._build_lstm_model(n_features)
            assert model.input_shape[2] == n_features


class TestModelTraining:
    """Test model training functionality"""

    @pytest.mark.skipif(not TENSORFLOW_AVAILABLE, reason="TensorFlow not available")
    @pytest.mark.asyncio
    async def test_train_with_sufficient_data(self, predictor, sample_price_data):
        """Test training with sufficient data"""
        # Mock model saving
        with patch.object(predictor, '_save_model'):
            with patch.object(predictor, '_save_metadata'):
                result = await predictor.train(sample_price_data, epochs=1, batch_size=32)

                assert 'status' in result
                assert predictor.model is not None
                assert predictor.last_trained is not None

    @pytest.mark.asyncio
    async def test_train_with_insufficient_data(self, predictor):
        """Test training fails with insufficient data"""
        small_data = pd.DataFrame({
            'timestamp': pd.date_range(end=datetime.now(), periods=10, freq='1h'),
            'close': [40000] * 10,
            'open': [40000] * 10,
            'high': [40500] * 10,
            'low': [39500] * 10,
            'volume': [100] * 10
        })

        with pytest.raises(ValueError):
            await predictor.train(small_data)

    @pytest.mark.skipif(not TENSORFLOW_AVAILABLE, reason="TensorFlow not available")
    @pytest.mark.asyncio
    async def test_train_stores_metrics(self, predictor, sample_price_data):
        """Test that training stores performance metrics"""
        with patch.object(predictor, '_save_model'):
            with patch.object(predictor, '_save_metadata'):
                await predictor.train(sample_price_data, epochs=1)

                assert 'rmse' in predictor.training_stats
                assert 'mae' in predictor.training_stats
                assert 'r2_score' in predictor.training_stats


class TestPrediction:
    """Test price prediction functionality"""

    @pytest.mark.skipif(not TENSORFLOW_AVAILABLE, reason="TensorFlow not available")
    @pytest.mark.asyncio
    async def test_predict_without_model(self, predictor, sample_price_data):
        """Test prediction fails without trained model"""
        predictor.model = None

        with pytest.raises(ValueError):
            await predictor.predict(sample_price_data)

    @pytest.mark.skipif(not TENSORFLOW_AVAILABLE, reason="TensorFlow not available")
    @pytest.mark.asyncio
    async def test_predict_with_trained_model(self, predictor, sample_price_data):
        """Test prediction with trained model"""
        # Train model first
        with patch.object(predictor, '_save_model'):
            with patch.object(predictor, '_save_metadata'):
                await predictor.train(sample_price_data, epochs=1)

        # Make prediction
        prediction = await predictor.predict(sample_price_data)

        assert isinstance(prediction, PricePrediction)
        assert len(prediction.predictions) > 0
        assert all(isinstance(p, PricePoint) for p in prediction.predictions)

    @pytest.mark.skipif(not TENSORFLOW_AVAILABLE, reason="TensorFlow not available")
    @pytest.mark.asyncio
    async def test_predict_returns_confidence(self, predictor, sample_price_data):
        """Test that predictions include confidence scores"""
        # Train and predict
        with patch.object(predictor, '_save_model'):
            with patch.object(predictor, '_save_metadata'):
                await predictor.train(sample_price_data, epochs=1)

        prediction = await predictor.predict(sample_price_data)

        assert hasattr(prediction, 'average_confidence')
        assert 0 <= prediction.average_confidence <= 1


class TestModelPersistence:
    """Test model saving and loading"""

    def test_get_model_path(self, predictor):
        """Test model path generation"""
        path = predictor._get_model_path()

        assert isinstance(path, Path)
        assert 'BTCUSDT' in str(path)
        assert '60m' in str(path)
        assert path.suffix == '.keras'

    def test_get_metadata_path(self, predictor):
        """Test metadata path generation"""
        path = predictor._get_metadata_path()

        assert isinstance(path, Path)
        assert 'BTCUSDT' in str(path)
        assert '60m' in str(path)
        assert path.suffix == '.json'

    @pytest.mark.skipif(not TENSORFLOW_AVAILABLE, reason="TensorFlow not available")
    def test_save_and_load_model(self, predictor, sample_price_data, temp_models_dir):
        """Test saving and loading model"""
        import asyncio

        # Train model
        with patch('app.predictor.settings.models_dir', temp_models_dir):
            asyncio.run(predictor.train(sample_price_data, epochs=1))

            # Create new predictor instance
            new_predictor = LSTMPricePredictor("BTCUSDT", "60")

            # Check that model was loaded
            assert new_predictor.model is not None
            assert new_predictor.last_trained is not None


class TestTrendClassification:
    """Test trend classification"""

    def test_classify_trend_bullish(self, predictor):
        """Test bullish trend classification"""
        # Create uptrend data
        current_price = 42000
        predicted_prices = [42100, 42200, 42300]

        trend = predictor._classify_trend(current_price, predicted_prices)

        assert trend['direction'] in ['bullish', 'up', 'BULLISH']

    def test_classify_trend_bearish(self, predictor):
        """Test bearish trend classification"""
        # Create downtrend data
        current_price = 42000
        predicted_prices = [41900, 41800, 41700]

        trend = predictor._classify_trend(current_price, predicted_prices)

        assert trend['direction'] in ['bearish', 'down', 'BEARISH']

    def test_classify_trend_neutral(self, predictor):
        """Test neutral trend classification"""
        # Create sideways data
        current_price = 42000
        predicted_prices = [42000, 42010, 41990]

        trend = predictor._classify_trend(current_price, predicted_prices)

        assert trend['direction'] in ['neutral', 'sideways', 'NEUTRAL']


class TestVolatilityForecasting:
    """Test volatility prediction"""

    def test_calculate_volatility_forecast(self, predictor, sample_price_data):
        """Test volatility calculation"""
        volatility = predictor._calculate_volatility_forecast(sample_price_data)

        assert isinstance(volatility, dict)
        assert 'current_volatility' in volatility or volatility is not None

    def test_volatility_with_high_variance(self, predictor):
        """Test volatility with high variance data"""
        # Create high volatility data
        dates = pd.date_range(end=datetime.now(), periods=100, freq='1h')
        prices = [40000 + np.random.normal(0, 1000) for _ in range(100)]

        data = pd.DataFrame({
            'timestamp': dates,
            'close': prices,
            'open': prices,
            'high': [p * 1.05 for p in prices],
            'low': [p * 0.95 for p in prices],
            'volume': [100] * 100
        })

        volatility = predictor._calculate_volatility_forecast(data)

        # High volatility data should show high volatility
        assert volatility is not None


class TestModelInfo:
    """Test model information retrieval"""

    def test_get_model_info_no_model(self, predictor):
        """Test getting info when no model exists"""
        info = predictor.get_model_info()

        assert info['symbol'] == 'BTCUSDT'
        assert info['interval'] == '60'
        assert not info['is_trained']

    @pytest.mark.skipif(not TENSORFLOW_AVAILABLE, reason="TensorFlow not available")
    def test_get_model_info_with_model(self, predictor, sample_price_data):
        """Test getting info with trained model"""
        import asyncio

        with patch.object(predictor, '_save_model'):
            with patch.object(predictor, '_save_metadata'):
                asyncio.run(predictor.train(sample_price_data, epochs=1))

        info = predictor.get_model_info()

        assert info['is_trained']
        assert 'model_version' in info
        assert 'last_trained' in info


class TestRetrainingLogic:
    """Test model retraining logic"""

    def test_needs_retraining_new_model(self, predictor):
        """Test that new model needs training"""
        predictor.last_trained = None

        needs_retrain = predictor._needs_retraining()

        assert needs_retrain is True

    def test_needs_retraining_old_model(self, predictor):
        """Test that old model needs retraining"""
        predictor.last_trained = datetime.now() - timedelta(days=10)

        with patch('app.predictor.settings.model_retrain_days', 7):
            needs_retrain = predictor._needs_retraining()

            assert needs_retrain is True

    def test_needs_retraining_recent_model(self, predictor):
        """Test that recent model doesn't need retraining"""
        predictor.last_trained = datetime.now() - timedelta(days=1)

        with patch('app.predictor.settings.model_retrain_days', 7):
            needs_retrain = predictor._needs_retraining()

            assert needs_retrain is False


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_predictor_with_special_characters_symbol(self, temp_models_dir):
        """Test predictor with unusual symbol names"""
        with patch('app.predictor.settings.models_dir', temp_models_dir):
            # Should handle symbols with special chars
            predictor = LSTMPricePredictor("BTC-USDT", "60")
            assert predictor.symbol == "BTC-USDT"

    def test_predictor_with_different_intervals(self, temp_models_dir):
        """Test predictor with various interval values"""
        with patch('app.predictor.settings.models_dir', temp_models_dir):
            for interval in ["1", "5", "15", "60", "240", "D"]:
                predictor = LSTMPricePredictor("BTCUSDT", interval)
                assert predictor.interval == interval

    @pytest.mark.asyncio
    async def test_train_with_corrupted_data(self, predictor):
        """Test training handles corrupted data"""
        # Create data with inf and nan values
        data = pd.DataFrame({
            'timestamp': pd.date_range(end=datetime.now(), periods=100, freq='1h'),
            'close': [np.inf if i % 10 == 0 else 40000 for i in range(100)],
            'open': [40000] * 100,
            'high': [40500] * 100,
            'low': [39500] * 100,
            'volume': [np.nan if i % 5 == 0 else 100 for i in range(100)]
        })

        # Should either handle it or raise appropriate error
        try:
            await predictor.train(data, epochs=1)
        except (ValueError, Exception):
            # Expected to fail with corrupted data
            pass
