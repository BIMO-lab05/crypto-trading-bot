"""
Tests for Enhanced Trading Signal Endpoints
Tests ML prediction integration, enhanced signals, and multi-source aggregation
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch
from fastapi.responses import JSONResponse
import json

from app.main import app, get_proxy


class TestMLPredictionEndpoints:
    """Test ML prediction endpoints"""

    @pytest.mark.asyncio
    async def test_ml_predict_price(self, test_client, mock_service_proxy):
        """Test ML price prediction endpoint"""
        mock_response = JSONResponse(content={
            "symbol": "BTCUSDT",
            "predicted_price": 46000.0,
            "confidence": 0.85,
            "model_type": "LSTM"
        })
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/ml/predict/price/BTCUSDT?interval=60&model_type=LSTM")

        assert response.status_code == 200
        call_kwargs = mock_service_proxy.proxy_request.call_args[1]
        assert call_kwargs["service_name"] == "ml-prediction"
        assert "predict/price" in call_kwargs["path"]

    @pytest.mark.asyncio
    async def test_ml_predict_trend(self, test_client, mock_service_proxy):
        """Test ML trend prediction endpoint"""
        mock_response = JSONResponse(content={
            "symbol": "BTCUSDT",
            "trend": "BULLISH",
            "confidence": 0.78
        })
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/ml/predict/trend/ETHUSDT")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_ml_predict_volatility(self, test_client, mock_service_proxy):
        """Test ML volatility prediction endpoint"""
        mock_response = JSONResponse(content={
            "symbol": "BTCUSDT",
            "volatility_1h": 0.02,
            "volatility_4h": 0.05,
            "volatility_24h": 0.08
        })
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/ml/predict/volatility/BTCUSDT")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_ml_predict_signal_buy(self, test_client, mock_service_proxy):
        """Test ML signal generation - BUY signal"""
        # Mock price prediction response
        prediction_response = Mock()
        prediction_response.body = json.dumps({
            "predicted_direction": "UP",
            "directional_strength": 0.75
        }).encode()

        mock_service_proxy.proxy_request.return_value = prediction_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/ml/predict/signal/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["signal"] == "BUY"
        assert data["confidence"] == 0.75
        assert data["symbol"] == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_ml_predict_signal_sell(self, test_client, mock_service_proxy):
        """Test ML signal generation - SELL signal"""
        prediction_response = Mock()
        prediction_response.body = json.dumps({
            "predicted_direction": "DOWN",
            "directional_strength": 0.82
        }).encode()

        mock_service_proxy.proxy_request.return_value = prediction_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/ml/predict/signal/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["signal"] == "SELL"
        assert data["confidence"] == 0.82

    @pytest.mark.asyncio
    async def test_ml_predict_signal_hold(self, test_client, mock_service_proxy):
        """Test ML signal generation - HOLD signal"""
        prediction_response = Mock()
        prediction_response.body = json.dumps({
            "predicted_direction": "SIDEWAYS",
            "directional_strength": 0.45
        }).encode()

        mock_service_proxy.proxy_request.return_value = prediction_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/ml/predict/signal/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["signal"] == "HOLD"

    @pytest.mark.asyncio
    async def test_ml_predict_signal_error_handling(self, test_client, mock_service_proxy):
        """Test ML signal error handling"""
        mock_service_proxy.proxy_request.side_effect = Exception("ML service unavailable")

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/ml/predict/signal/BTCUSDT")

        assert response.status_code == 500
        assert "Failed to generate ML signal" in response.json()["detail"]


class TestMLModelManagementEndpoints:
    """Test ML model management endpoints"""

    @pytest.mark.asyncio
    async def test_list_ml_models(self, test_client, mock_service_proxy):
        """Test listing all ML models"""
        mock_response = JSONResponse(content={
            "models": ["LSTM", "GRU"],
            "count": 2
        })
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/ml/models")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_ml_model_info(self, test_client, mock_service_proxy):
        """Test getting specific model info"""
        mock_response = JSONResponse(content={
            "symbol": "BTCUSDT",
            "model_type": "LSTM",
            "accuracy": 0.85,
            "last_trained": "2025-11-23T00:00:00Z"
        })
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/ml/models/BTCUSDT?model_type=LSTM")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_train_ml_model(self, test_client, mock_service_proxy):
        """Test training ML model"""
        mock_response = JSONResponse(content={
            "success": True,
            "message": "Model training started"
        })
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.post(
                "/api/ml/models/train?symbol=BTCUSDT&lookback_days=90&force_retrain=false"
            )

        assert response.status_code == 200
        call_kwargs = mock_service_proxy.proxy_request.call_args[1]
        assert call_kwargs["method"] == "POST"

    @pytest.mark.asyncio
    async def test_compare_ml_models(self, test_client, mock_service_proxy):
        """Test comparing LSTM vs GRU models"""
        mock_response = JSONResponse(content={
            "symbol": "BTCUSDT",
            "lstm_accuracy": 0.85,
            "gru_accuracy": 0.82,
            "recommendation": "LSTM"
        })
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/ml/models/compare/BTCUSDT")

        assert response.status_code == 200


class TestEnhancedTradingSignalEndpoint:
    """Test enhanced trading signal that combines multiple sources"""

    @pytest.mark.asyncio
    async def test_enhanced_signal_all_buy(self, test_client, mock_service_proxy):
        """Test enhanced signal with all sources indicating BUY"""
        # Mock responses from all services
        ta_response = Mock()
        ta_response.body = json.dumps({"aggregated_signal": "BUY"}).encode()

        ml_response = Mock()
        ml_response.body = json.dumps({"trend": "BULLISH"}).encode()

        sentiment_response = Mock()
        sentiment_response.body = json.dumps({"combined_label": "BULLISH"}).encode()

        mtf_response = Mock()
        mtf_response.body = json.dumps({"consensus_signal": "BUY"}).encode()

        signal_response = Mock()
        signal_response.body = json.dumps({"signal": "BUY"}).encode()

        mock_service_proxy.proxy_request.side_effect = [
            ta_response, ml_response, sentiment_response, mtf_response, signal_response
        ]

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/trading/signals/enhanced/BTCUSDT?interval=60")

        assert response.status_code == 200
        data = response.json()

        assert data["signal"] == "BUY"
        assert data["confidence"] == 1.0  # All signals agree
        assert data["risk_level"] == "LOW"
        assert data["signal_breakdown"]["buy_signals"] == 5
        assert data["signal_breakdown"]["sell_signals"] == 0

    @pytest.mark.asyncio
    async def test_enhanced_signal_all_sell(self, test_client, mock_service_proxy):
        """Test enhanced signal with all sources indicating SELL"""
        ta_response = Mock()
        ta_response.body = json.dumps({"aggregated_signal": "SELL"}).encode()

        ml_response = Mock()
        ml_response.body = json.dumps({"trend": "BEARISH"}).encode()

        sentiment_response = Mock()
        sentiment_response.body = json.dumps({"combined_label": "BEARISH"}).encode()

        mtf_response = Mock()
        mtf_response.body = json.dumps({"consensus_signal": "SELL"}).encode()

        signal_response = Mock()
        signal_response.body = json.dumps({"signal": "SELL"}).encode()

        mock_service_proxy.proxy_request.side_effect = [
            ta_response, ml_response, sentiment_response, mtf_response, signal_response
        ]

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/trading/signals/enhanced/BTCUSDT")

        assert response.status_code == 200
        data = response.json()

        assert data["signal"] == "SELL"
        assert data["confidence"] == 1.0
        assert data["signal_breakdown"]["sell_signals"] == 5

    @pytest.mark.asyncio
    async def test_enhanced_signal_mixed_signals(self, test_client, mock_service_proxy):
        """Test enhanced signal with mixed signals"""
        ta_response = Mock()
        ta_response.body = json.dumps({"aggregated_signal": "BUY"}).encode()

        ml_response = Mock()
        ml_response.body = json.dumps({"trend": "BEARISH"}).encode()

        sentiment_response = Mock()
        sentiment_response.body = json.dumps({"combined_label": "NEUTRAL"}).encode()

        mtf_response = Mock()
        mtf_response.body = json.dumps({"consensus_signal": "BUY"}).encode()

        signal_response = Mock()
        signal_response.body = json.dumps({"signal": "HOLD"}).encode()

        mock_service_proxy.proxy_request.side_effect = [
            ta_response, ml_response, sentiment_response, mtf_response, signal_response
        ]

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/trading/signals/enhanced/BTCUSDT")

        assert response.status_code == 200
        data = response.json()

        # With 2 BUY, 1 SELL, 2 HOLD/NEUTRAL, majority is tied so result could be either
        # Based on logic: 2 neutral, 2 buy, 1 sell - neutral wins
        assert data["signal"] == "HOLD"
        assert data["risk_level"] in ["MEDIUM", "HIGH"]

    @pytest.mark.asyncio
    async def test_enhanced_signal_service_failures(self, test_client, mock_service_proxy):
        """Test enhanced signal handles service failures gracefully"""
        ta_response = Mock()
        ta_response.body = json.dumps({"aggregated_signal": "BUY"}).encode()

        # Other services fail
        mock_service_proxy.proxy_request.side_effect = [
            ta_response,
            Exception("ML service down"),
            Exception("Sentiment service down"),
            Exception("MTF service down"),
            Exception("Signal service down")
        ]

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/trading/signals/enhanced/BTCUSDT")

        assert response.status_code == 200
        data = response.json()

        # Should still work with partial data
        assert "signal" in data
        assert data["signal_breakdown"]["total_signals"] >= 0

    @pytest.mark.asyncio
    async def test_enhanced_signal_no_data(self, test_client, mock_service_proxy):
        """Test enhanced signal when no services return data"""
        # All services fail
        mock_service_proxy.proxy_request.side_effect = [
            Exception("Service 1 down"),
            Exception("Service 2 down"),
            Exception("Service 3 down"),
            Exception("Service 4 down"),
            Exception("Service 5 down")
        ]

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/trading/signals/enhanced/BTCUSDT")

        assert response.status_code == 200
        data = response.json()

        # Should default to HOLD with 0 confidence
        assert data["signal"] == "HOLD"
        assert data["confidence"] == 0.0
        assert data["signal_breakdown"]["total_signals"] == 0

    @pytest.mark.asyncio
    async def test_enhanced_signal_confidence_levels(self, test_client, mock_service_proxy):
        """Test different confidence levels affect risk rating"""
        # Test high confidence
        responses_high = [
            Mock(body=json.dumps({"aggregated_signal": "BUY"}).encode()),
            Mock(body=json.dumps({"trend": "BULLISH"}).encode()),
            Mock(body=json.dumps({"combined_label": "BULLISH"}).encode()),
            Mock(body=json.dumps({"consensus_signal": "BUY"}).encode()),
            Mock(body=json.dumps({"signal": "BUY"}).encode())
        ]

        mock_service_proxy.proxy_request.side_effect = responses_high

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/trading/signals/enhanced/BTCUSDT")

        data = response.json()
        assert data["confidence"] >= 0.7
        assert data["risk_level"] == "LOW"

    @pytest.mark.asyncio
    async def test_enhanced_signal_recommendation_text(self, test_client, mock_service_proxy):
        """Test recommendation text is generated correctly"""
        responses = [
            Mock(body=json.dumps({"aggregated_signal": "BUY"}).encode()),
            Mock(body=json.dumps({"trend": "BULLISH"}).encode()),
            Mock(body=json.dumps({"combined_label": "BULLISH"}).encode()),
            Mock(body=json.dumps({"consensus_signal": "BUY"}).encode()),
            Mock(body=json.dumps({"signal": "BUY"}).encode())
        ]

        mock_service_proxy.proxy_request.side_effect = responses

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/trading/signals/enhanced/BTCUSDT")

        data = response.json()
        assert "recommendation" in data
        assert isinstance(data["recommendation"], str)
        assert len(data["recommendation"]) > 0


class TestRiskAndPerformanceEndpoints:
    """Test additional risk and performance endpoints"""

    @pytest.mark.asyncio
    async def test_get_capital_metrics(self, test_client, mock_service_proxy):
        """Test capital allocation metrics endpoint"""
        mock_response = JSONResponse(content={
            "total_capital": 100000,
            "allocated": 50000,
            "available": 50000
        })
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/risk/capital")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_exposure_metrics(self, test_client, mock_service_proxy):
        """Test portfolio exposure analysis endpoint"""
        mock_response = JSONResponse(content={
            "total_exposure": 50000,
            "by_asset": {"BTC": 30000, "ETH": 20000}
        })
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/risk/exposure")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_drawdown_metrics(self, test_client, mock_service_proxy):
        """Test drawdown tracking metrics endpoint"""
        mock_response = JSONResponse(content={
            "current_drawdown": 0.05,
            "max_drawdown": 0.12
        })
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/risk/drawdown")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_active_alerts(self, test_client, mock_service_proxy):
        """Test active risk alerts endpoint"""
        mock_response = JSONResponse(content={
            "alerts": [],
            "count": 0
        })
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/risk/alerts")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_reset_circuit_breaker(self, test_client, mock_service_proxy):
        """Test circuit breaker reset endpoint"""
        mock_response = JSONResponse(content={
            "success": True,
            "message": "Circuit breaker reset"
        })
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.post("/api/risk/circuit-breaker/reset")

        assert response.status_code == 200
        call_kwargs = mock_service_proxy.proxy_request.call_args[1]
        assert call_kwargs["method"] == "POST"


class TestPerformanceMetricsEndpoints:
    """Test performance metrics endpoints"""

    @pytest.mark.asyncio
    async def test_get_performance_metrics(self, test_client, mock_service_proxy):
        """Test comprehensive performance metrics endpoint"""
        mock_response = JSONResponse(content={
            "total_return": 0.15,
            "sharpe_ratio": 1.5,
            "win_rate": 0.65
        })
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/performance/metrics")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_sharpe_ratio(self, test_client, mock_service_proxy):
        """Test Sharpe ratio calculation endpoint"""
        mock_response = JSONResponse(content={
            "sharpe_ratio": 1.75,
            "risk_free_rate": 0.02
        })
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/performance/sharpe")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_portfolio_performance(self, test_client, mock_service_proxy):
        """Test portfolio performance endpoint"""
        mock_response = JSONResponse(content={
            "total_pnl": 15000,
            "pnl_percentage": 0.15
        })
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/portfolio/performance")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_trades_with_filters(self, test_client, mock_service_proxy):
        """Test getting trades with limit and symbol filters"""
        mock_response = JSONResponse(content={
            "trades": [],
            "count": 0
        })
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/portfolio/trades?limit=50&symbol=BTCUSDT")

        assert response.status_code == 200
        call_kwargs = mock_service_proxy.proxy_request.call_args[1]
        assert call_kwargs["query_params"]["limit"] == 50
        assert call_kwargs["query_params"]["symbol"] == "BTCUSDT"
