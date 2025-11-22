"""
Tests for ML Prediction Service API endpoints
Tests FastAPI endpoints for price predictions, training, and model management
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import numpy as np

from app.main import app
from app.predictor import LSTMPricePredictor


@pytest.fixture
def client():
    """
    Creates test client for FastAPI app
    """
    return TestClient(app)


@pytest.fixture
def mock_predictor():
    """
    Creates mock predictor for testing
    """
    predictor = MagicMock(spec=LSTMPricePredictor)
    predictor.symbol = "BTCUSDT"
    predictor.interval = "60"
    predictor.is_trained = True
    predictor.model_version = "v20251110_120000"
    return predictor


class TestHealthEndpoint:
    """Tests for health check endpoint"""

    def test_health_check(self, client):
        """
        Test /health endpoint returns service status
        """
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'ml-prediction-service'
        assert 'timestamp' in data


class TestModelManagementEndpoints:
    """Tests for model management endpoints"""

    def test_list_models_empty(self, client):
        """
        Test /api/v1/models when no models exist
        Should return empty list
        """
        with patch('app.main.model_store', {}):
            response = client.get("/api/v1/models")

            assert response.status_code == 200
            data = response.json()
            assert data['models'] == []
            assert data['count'] == 0

    def test_list_models_with_data(self, client, mock_predictor):
        """
        Test /api/v1/models with trained models
        Should return list of model info
        """
        mock_predictor.get_model_info.return_value = {
            'symbol': 'BTCUSDT',
            'interval': '60',
            'is_trained': True,
            'model_version': 'v20251110_120000'
        }

        with patch('app.main.model_store', {'BTCUSDT_60': mock_predictor}):
            response = client.get("/api/v1/models")

            assert response.status_code == 200
            data = response.json()
            assert data['count'] == 1
            assert len(data['models']) == 1
            assert data['models'][0]['symbol'] == 'BTCUSDT'
            assert data['models'][0]['is_trained'] == True

    def test_get_model_info_exists(self, client, mock_predictor):
        """
        Test /api/v1/models/{symbol} for existing model
        """
        mock_predictor.get_model_info.return_value = {
            'symbol': 'BTCUSDT',
            'interval': '60',
            'is_trained': True,
            'model_version': 'v20251110_120000',
            'training_samples': 1000
        }

        with patch('app.main.model_store', {'BTCUSDT_60': mock_predictor}):
            response = client.get("/api/v1/models/BTCUSDT?interval=60")

            assert response.status_code == 200
            data = response.json()
            assert data['symbol'] == 'BTCUSDT'
            assert data['is_trained'] == True
            assert data['model_version'] == 'v20251110_120000'

    def test_get_model_info_not_found(self, client):
        """
        Test /api/v1/models/{symbol} for non-existent model
        Should return 404
        """
        with patch('app.main.model_store', {}):
            response = client.get("/api/v1/models/ETHUSDT?interval=60")

            assert response.status_code == 404
            data = response.json()
            assert 'detail' in data


class TestModelTrainingEndpoint:
    """Tests for model training endpoint"""

    def test_train_model_success(self, client, mock_predictor):
        """
        Test POST /api/v1/models/train with valid params
        Should start training and return success
        """
        mock_predictor.train.return_value = {
            'status': 'success',
            'model_version': 'v20251110_120000',
            'training_samples': 1000,
            'epochs': 50
        }

        with patch('app.main.LSTMPricePredictor', return_value=mock_predictor):
            response = client.post(
                "/api/v1/models/train",
                json={
                    'symbol': 'BTCUSDT',
                    'interval': '60',
                    'lookback_days': 90
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'success'
            assert 'model_version' in data
            assert data['training_samples'] == 1000

    def test_train_model_invalid_symbol(self, client):
        """
        Test training with invalid symbol format
        Should return 422 validation error
        """
        response = client.post(
            "/api/v1/models/train",
            json={
                'symbol': '',  # Invalid empty symbol
                'interval': '60',
                'lookback_days': 90
            }
        )

        assert response.status_code == 422  # Validation error

    def test_train_model_invalid_lookback(self, client):
        """
        Test training with invalid lookback days (too small)
        Should return 422 validation error
        """
        response = client.post(
            "/api/v1/models/train",
            json={
                'symbol': 'BTCUSDT',
                'interval': '60',
                'lookback_days': 0  # Invalid: too small
            }
        )

        assert response.status_code == 422

    def test_train_model_failure(self, client, mock_predictor):
        """
        Test training when training fails
        Should return error response
        """
        mock_predictor.train.return_value = {
            'status': 'error',
            'error': 'Insufficient data'
        }

        with patch('app.main.LSTMPricePredictor', return_value=mock_predictor):
            response = client.post(
                "/api/v1/models/train",
                json={
                    'symbol': 'BTCUSDT',
                    'interval': '60',
                    'lookback_days': 90
                }
            )

            assert response.status_code == 500
            data = response.json()
            assert 'error' in data


class TestPredictionEndpoints:
    """Tests for price prediction endpoints"""

    def test_predict_price_success(self, client, mock_predictor):
        """
        Test GET /api/v1/predict/price/{symbol} with trained model
        Should return price predictions
        """
        mock_predictor.predict.return_value = {
            'symbol': 'BTCUSDT',
            'interval': '60',
            'predictions': [50000, 50500, 51000, 51500, 52000],
            'trend': 'BULLISH',
            'confidence': 0.78,
            'model_version': 'v20251110_120000'
        }

        with patch('app.main.model_store', {'BTCUSDT_60': mock_predictor}):
            response = client.get("/api/v1/predict/price/BTCUSDT?interval=60")

            assert response.status_code == 200
            data = response.json()
            assert data['symbol'] == 'BTCUSDT'
            assert len(data['predictions']) == 5
            assert data['trend'] == 'BULLISH'
            assert 0 <= data['confidence'] <= 1.0

    def test_predict_price_model_not_trained(self, client):
        """
        Test prediction when model doesn't exist
        Should return 404
        """
        with patch('app.main.model_store', {}):
            response = client.get("/api/v1/predict/price/ETHUSDT?interval=60")

            assert response.status_code == 404
            data = response.json()
            assert 'not found' in data['detail'].lower()

    def test_predict_trend_success(self, client, mock_predictor):
        """
        Test GET /api/v1/predict/trend/{symbol}
        Should return trend classification
        """
        mock_predictor.predict.return_value = {
            'symbol': 'BTCUSDT',
            'predictions': [50000, 50500, 51000, 51500, 52000],
            'trend': 'BULLISH',
            'confidence': 0.82
        }

        with patch('app.main.model_store', {'BTCUSDT_60': mock_predictor}):
            response = client.get("/api/v1/predict/trend/BTCUSDT?interval=60")

            assert response.status_code == 200
            data = response.json()
            assert data['symbol'] == 'BTCUSDT'
            assert data['trend'] in ['BULLISH', 'BEARISH', 'NEUTRAL']
            assert 'confidence' in data
            assert 'direction' in data

    def test_predict_volatility_success(self, client, mock_predictor):
        """
        Test GET /api/v1/predict/volatility/{symbol}
        Should return volatility forecast
        """
        mock_predictor.predict.return_value = {
            'predictions': [50000, 50500, 49800, 51200, 50300],
            'volatility': 1.5
        }

        with patch('app.main.model_store', {'BTCUSDT_60': mock_predictor}):
            response = client.get("/api/v1/predict/volatility/BTCUSDT?interval=60")

            assert response.status_code == 200
            data = response.json()
            assert data['symbol'] == 'BTCUSDT'
            assert 'volatility' in data
            assert 'volatility_level' in data
            assert data['volatility_level'] in ['LOW', 'MEDIUM', 'HIGH']

    def test_predict_signal_for_trading_success(self, client, mock_predictor):
        """
        Test GET /api/v1/predict/signal/{symbol}
        Should return ML-based trading signal
        """
        mock_predictor.predict.return_value = {
            'symbol': 'BTCUSDT',
            'predictions': [50000, 50500, 51000, 51500, 52000],
            'trend': 'BULLISH',
            'confidence': 0.85,
            'volatility': 1.2
        }

        with patch('app.main.model_store', {'BTCUSDT_60': mock_predictor}):
            response = client.get("/api/v1/predict/signal/BTCUSDT?interval=60")

            assert response.status_code == 200
            data = response.json()
            assert data['symbol'] == 'BTCUSDT'
            assert data['signal'] in ['BUY', 'SELL', 'HOLD']
            assert data['trend'] == 'BULLISH'
            assert 0 <= data['confidence'] <= 1.0
            assert 'strength' in data

    def test_predict_signal_low_confidence(self, client, mock_predictor):
        """
        Test signal generation with low confidence prediction
        Should return HOLD signal
        """
        mock_predictor.predict.return_value = {
            'symbol': 'BTCUSDT',
            'predictions': [50000, 50100, 49900, 50050, 49950],
            'trend': 'NEUTRAL',
            'confidence': 0.45,  # Below threshold
            'volatility': 0.8
        }

        with patch('app.main.model_store', {'BTCUSDT_60': mock_predictor}):
            response = client.get("/api/v1/predict/signal/BTCUSDT?interval=60")

            assert response.status_code == 200
            data = response.json()
            assert data['signal'] == 'HOLD'  # Low confidence -> HOLD
            assert data['confidence'] < 0.6


class TestModelRetrainingEndpoint:
    """Tests for model retraining endpoint"""

    def test_retrain_model_success(self, client, mock_predictor):
        """
        Test POST /api/v1/models/retrain/{symbol}
        Should retrain existing model
        """
        mock_predictor.train.return_value = {
            'status': 'success',
            'model_version': 'v20251110_130000',
            'training_samples': 1200,
            'improvement': '+5%'
        }

        with patch('app.main.model_store', {'BTCUSDT_60': mock_predictor}):
            response = client.post(
                "/api/v1/models/retrain/BTCUSDT?interval=60&lookback_days=90"
            )

            assert response.status_code == 200
            data = response.json()
            assert data['status'] == 'success'
            assert 'model_version' in data

    def test_retrain_model_not_found(self, client):
        """
        Test retraining when model doesn't exist
        Should return 404
        """
        with patch('app.main.model_store', {}):
            response = client.post(
                "/api/v1/models/retrain/ETHUSDT?interval=60&lookback_days=90"
            )

            assert response.status_code == 404


class TestPredictionValidation:
    """Tests for prediction validation logic"""

    def test_prediction_with_custom_interval(self, client, mock_predictor):
        """
        Test prediction with different intervals (5m, 15m, etc.)
        """
        mock_predictor.predict.return_value = {
            'symbol': 'BTCUSDT',
            'interval': '15',
            'predictions': [50000, 50200, 50400],
            'trend': 'BULLISH',
            'confidence': 0.75
        }

        with patch('app.main.model_store', {'BTCUSDT_15': mock_predictor}):
            response = client.get("/api/v1/predict/price/BTCUSDT?interval=15")

            assert response.status_code == 200
            data = response.json()
            assert data['interval'] == '15'


# Performance tests
class TestPerformance:
    """Performance tests for API endpoints"""

    @pytest.mark.performance
    def test_prediction_response_time(self, client, mock_predictor):
        """
        Test that prediction endpoint responds within acceptable time
        Should be under 500ms
        """
        import time

        mock_predictor.predict.return_value = {
            'symbol': 'BTCUSDT',
            'predictions': [50000, 50500, 51000, 51500, 52000],
            'trend': 'BULLISH',
            'confidence': 0.78
        }

        with patch('app.main.model_store', {'BTCUSDT_60': mock_predictor}):
            start = time.time()
            response = client.get("/api/v1/predict/price/BTCUSDT?interval=60")
            elapsed = time.time() - start

            assert response.status_code == 200
            assert elapsed < 0.5  # Should respond within 500ms


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
