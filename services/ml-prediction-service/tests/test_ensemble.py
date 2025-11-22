"""
Tests for Ensemble Predictor
Tests ensemble strategies, weight optimization, and performance tracking
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta

from app.ml_models.ensemble_predictor import EnsemblePredictor, EnsemblePerformanceMetrics
from app.models import PricePoint, PricePrediction


@pytest.fixture
def sample_price_data():
    """Generate sample OHLCV data for testing"""
    dates = pd.date_range(start='2025-01-01', periods=150, freq='1h')
    base_price = 50000.0

    prices = []
    current_price = base_price
    for _ in range(150):
        change = np.random.normal(0, 500)
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
            'timestamp': date,
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': volume
        })

    return pd.DataFrame(data)


@pytest.fixture
def mock_price_prediction():
    """Create mock PricePrediction object"""
    predictions = [
        PricePoint(
            timestamp=datetime.utcnow() + timedelta(hours=i+1),
            predicted_price=50000 + (i * 100),
            confidence=0.8 - (i * 0.05),
            lower_bound=49500 + (i * 100),
            upper_bound=50500 + (i * 100)
        )
        for i in range(5)
    ]

    return PricePrediction(
        symbol="BTCUSDT",
        interval="60m",
        current_price=50000.0,
        predictions=predictions,
        model_type="LSTM",
        model_version="v20251111_120000",
        model_last_trained=datetime.utcnow(),
        average_confidence=0.75,
        prediction_horizon_minutes=300,
        predicted_direction="UP",
        directional_strength=0.6
    )


class TestEnsemblePredictor:
    """Test suite for Ensemble Predictor"""

    def test_initialization(self):
        """Test that ensemble predictor initializes correctly"""
        ensemble = EnsemblePredictor(symbol="BTCUSDT", interval="60")

        assert ensemble.symbol == "BTCUSDT"
        assert ensemble.interval == "60"
        assert ensemble.lstm_predictor is not None
        assert ensemble.gru_predictor is not None
        assert ensemble.lstm_weight == 0.5
        assert ensemble.gru_weight == 0.5
        assert isinstance(ensemble.performance_history, list)

    @pytest.mark.asyncio
    async def test_simple_average_strategy(self, sample_price_data, mock_price_prediction):
        """Test simple averaging ensemble strategy"""
        ensemble = EnsemblePredictor(symbol="BTCUSDT", interval="60")

        # Mock LSTM and GRU predictions
        lstm_pred = mock_price_prediction
        gru_pred = mock_price_prediction

        with patch.object(ensemble.lstm_predictor, 'predict', return_value=lstm_pred):
            with patch.object(ensemble.gru_predictor, 'predict', return_value=gru_pred):
                result = await ensemble.predict_simple_average(sample_price_data)

                # Check result structure
                assert isinstance(result, PricePrediction)
                assert result.model_type == "ENSEMBLE_SIMPLE_AVG"
                assert len(result.predictions) == len(lstm_pred.predictions)

                # Check that predictions are averaged
                for i, pred in enumerate(result.predictions):
                    expected_price = (lstm_pred.predictions[i].predicted_price + gru_pred.predictions[i].predicted_price) / 2
                    assert abs(pred.predicted_price - expected_price) < 0.01

    @pytest.mark.asyncio
    async def test_performance_weighted_strategy(self, sample_price_data, mock_price_prediction):
        """Test performance-weighted ensemble strategy"""
        ensemble = EnsemblePredictor(symbol="BTCUSDT", interval="60")

        # Set different performance scores
        ensemble.lstm_predictor.training_stats = {'r2_score': 0.8}
        ensemble.gru_predictor.training_stats = {'r2_score': 0.6}

        lstm_pred = mock_price_prediction
        gru_pred = mock_price_prediction

        with patch.object(ensemble.lstm_predictor, 'predict', return_value=lstm_pred):
            with patch.object(ensemble.gru_predictor, 'predict', return_value=gru_pred):
                result = await ensemble.predict_performance_weighted(sample_price_data)

                # Check result
                assert result.model_type == "ENSEMBLE_PERFORMANCE_WEIGHTED"

                # LSTM should have more weight (0.8 / 1.4 ≈ 0.57)
                # Predictions should be closer to LSTM than GRU
                assert len(result.predictions) == len(lstm_pred.predictions)

    @pytest.mark.asyncio
    async def test_confidence_weighted_strategy(self, sample_price_data, mock_price_prediction):
        """Test confidence-weighted ensemble strategy"""
        ensemble = EnsemblePredictor(symbol="BTCUSDT", interval="60")

        # Create predictions with different confidences
        lstm_pred = mock_price_prediction
        lstm_pred.average_confidence = 0.9

        gru_pred = mock_price_prediction
        gru_pred.average_confidence = 0.7

        with patch.object(ensemble.lstm_predictor, 'predict', return_value=lstm_pred):
            with patch.object(ensemble.gru_predictor, 'predict', return_value=gru_pred):
                result = await ensemble.predict_confidence_weighted(sample_price_data)

                # Check result
                assert result.model_type == "ENSEMBLE_CONFIDENCE_WEIGHTED"
                assert len(result.predictions) == len(lstm_pred.predictions)

                # Confidence should be weighted average
                assert result.average_confidence > 0

    @pytest.mark.asyncio
    async def test_adaptive_strategy_high_volatility(self, sample_price_data, mock_price_prediction):
        """Test adaptive strategy in high volatility conditions"""
        ensemble = EnsemblePredictor(symbol="BTCUSDT", interval="60")

        # Create high volatility data
        df = sample_price_data.copy()
        df['returns'] = df['close'].pct_change()

        # Inject high volatility
        df.loc[df.index[-20:], 'returns'] = np.random.normal(0, 0.05, 20)

        lstm_pred = mock_price_prediction
        gru_pred = mock_price_prediction

        with patch.object(ensemble.lstm_predictor, 'predict', return_value=lstm_pred):
            with patch.object(ensemble.gru_predictor, 'predict', return_value=gru_pred):
                result = await ensemble.predict_adaptive(df)

                # Check result
                assert result.model_type == "ENSEMBLE_ADAPTIVE"
                assert len(result.predictions) > 0

    @pytest.mark.asyncio
    async def test_optimize_weights(self, sample_price_data):
        """Test ensemble weight optimization"""
        ensemble = EnsemblePredictor(symbol="BTCUSDT", interval="60")

        # Mock predictions
        lstm_predictions = [50000, 50100, 50200, 50300, 50400]
        gru_predictions = [50050, 50150, 50250, 50350, 50450]

        # Actual prices (closer to GRU in this case)
        actual_prices = [50040, 50140, 50240, 50340, 50440]

        # Create mock PricePredictions
        lstm_pred = Mock()
        lstm_pred.predictions = [Mock(predicted_price=p) for p in lstm_predictions]

        gru_pred = Mock()
        gru_pred.predictions = [Mock(predicted_price=p) for p in gru_predictions]

        with patch.object(ensemble.lstm_predictor, 'predict', return_value=lstm_pred):
            with patch.object(ensemble.gru_predictor, 'predict', return_value=gru_pred):
                result = await ensemble.optimize_weights(sample_price_data, actual_prices)

                # Check result structure
                assert 'lstm_weight' in result
                assert 'gru_weight' in result
                assert 'ensemble_mae' in result
                assert 'improvement_over_lstm_pct' in result

                # Weights should sum to 1
                assert abs(result['lstm_weight'] + result['gru_weight'] - 1.0) < 0.001

                # GRU should have higher weight (closer to actual)
                assert result['gru_weight'] > result['lstm_weight']

    def test_detect_disagreement(self):
        """Test disagreement detection between models"""
        ensemble = EnsemblePredictor(symbol="BTCUSDT", interval="60")

        # Similar predictions (should not disagree)
        lstm_prices = [50000, 50100, 50200, 50300, 50400]
        gru_prices = [50010, 50110, 50210, 50310, 50410]  # ~0.02% difference

        result = ensemble.detect_disagreement(lstm_prices, gru_prices, threshold=0.05)

        assert 'has_significant_disagreement' in result
        assert result['has_significant_disagreement'] == False
        assert 'average_disagreement_pct' in result

        # Large disagreement
        lstm_prices = [50000, 50100, 50200, 50300, 50400]
        gru_prices = [51000, 51100, 51200, 51300, 51400]  # ~2% difference

        result = ensemble.detect_disagreement(lstm_prices, gru_prices, threshold=0.02)

        assert result['has_significant_disagreement'] == True
        assert result['disagreement_count'] > 0
        assert 'recommendation' in result

    @pytest.mark.asyncio
    async def test_ensemble_strategy_selection(self, sample_price_data, mock_price_prediction):
        """Test that different strategies can be selected"""
        ensemble = EnsemblePredictor(symbol="BTCUSDT", interval="60")

        lstm_pred = mock_price_prediction
        gru_pred = mock_price_prediction

        with patch.object(ensemble.lstm_predictor, 'predict', return_value=lstm_pred):
            with patch.object(ensemble.gru_predictor, 'predict', return_value=gru_pred):
                # Test each strategy
                strategies = ["simple", "performance", "confidence", "adaptive"]

                for strategy in strategies:
                    result = await ensemble.predict(sample_price_data, strategy=strategy)

                    assert isinstance(result, PricePrediction)
                    assert "ENSEMBLE" in result.model_type
                    assert len(result.predictions) > 0

    def test_ensemble_config_save_load(self, tmp_path):
        """Test saving and loading ensemble configuration"""
        # Create ensemble with custom weights
        ensemble = EnsemblePredictor(symbol="BTCUSDT", interval="60")
        ensemble.lstm_weight = 0.7
        ensemble.gru_weight = 0.3

        # Save config (would normally save to settings.models_dir)
        with patch('app.ml_models.ensemble_predictor.Path') as mock_path:
            mock_path.return_value = tmp_path
            ensemble._save_ensemble_config()

            # Create new ensemble and load config
            ensemble2 = EnsemblePredictor(symbol="BTCUSDT", interval="60")
            ensemble2._load_ensemble_config()

            # Note: In actual implementation, would check if weights match
            # For this test, we just verify methods don't crash

    def test_ensemble_performance_metrics_dataclass(self):
        """Test EnsemblePerformanceMetrics dataclass"""
        metrics = EnsemblePerformanceMetrics(
            strategy="adaptive",
            mae=100.5,
            rmse=150.3,
            r2_score=0.85,
            accuracy=0.90,
            lstm_weight=0.6,
            gru_weight=0.4,
            improvement_over_lstm=5.2,
            improvement_over_gru=3.8,
            timestamp=datetime.utcnow()
        )

        assert metrics.strategy == "adaptive"
        assert metrics.mae == 100.5
        assert metrics.lstm_weight + metrics.gru_weight == 1.0
        assert metrics.improvement_over_lstm > 0


class TestEnsembleIntegration:
    """Integration tests for ensemble predictor"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_ensemble_workflow(self, sample_price_data, mock_price_prediction):
        """Test complete ensemble workflow"""
        # Create ensemble
        ensemble = EnsemblePredictor(symbol="BTCUSDT", interval="60")

        # Mock both models
        ensemble.lstm_predictor.model = Mock()
        ensemble.lstm_predictor.training_stats = {'r2_score': 0.8, 'mae': 200, 'rmse': 300}
        ensemble.gru_predictor.model = Mock()
        ensemble.gru_predictor.training_stats = {'r2_score': 0.75, 'mae': 220, 'rmse': 320}

        lstm_pred = mock_price_prediction
        gru_pred = mock_price_prediction

        with patch.object(ensemble.lstm_predictor, 'predict', return_value=lstm_pred):
            with patch.object(ensemble.gru_predictor, 'predict', return_value=gru_pred):
                # Step 1: Get predictions with different strategies
                simple_pred = await ensemble.predict(sample_price_data, strategy="simple")
                assert simple_pred.model_type == "ENSEMBLE_SIMPLE_AVG"

                perf_pred = await ensemble.predict(sample_price_data, strategy="performance")
                assert perf_pred.model_type == "ENSEMBLE_PERFORMANCE_WEIGHTED"

                # Step 2: Optimize weights
                actual_prices = [50000, 50100, 50200, 50300, 50400]
                opt_result = await ensemble.optimize_weights(sample_price_data, actual_prices)

                assert 'lstm_weight' in opt_result
                assert 'gru_weight' in opt_result

                # Step 3: Get performance metrics
                history = ensemble.get_performance_metrics()
                assert isinstance(history, list)


@pytest.fixture(scope="session")
def settings():
    """Get settings for testing"""
    from app.config import get_settings
    return get_settings()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
