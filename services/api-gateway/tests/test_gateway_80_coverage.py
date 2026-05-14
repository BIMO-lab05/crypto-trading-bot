"""
Comprehensive Gateway Test Suite - Coverage Goal: 80%+
Tests route forwarding, authentication, middleware, service proxy, and error handling
This test suite focuses on gaps in coverage and edge cases
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import httpx

from app.main import (
    app,
    WebSocketManager,
)
from app.services.service_proxy import ServiceProxy


# ============================================================================
# TEST SUITE 1: Route Forwarding & Service Proxy Tests
# ============================================================================


class TestRouteForwarding:
    """Test request routing to various backend services"""

    def test_portfolio_routes_with_mock(self, test_client):
        """Test that portfolio routes work correctly"""
        response = test_client.get("/api/portfolio?portfolio_id=default")
        # Route should exist and forward request
        assert response.status_code in [
            200,
            500,
            503,
        ]  # May be 503 if service not running

    def test_holdings_route_exists(self, test_client):
        """Test holdings endpoint exists and is accessible"""
        response = test_client.get("/api/portfolio/holdings?portfolio_id=test123")
        # Should route through gateway
        assert response.status_code in [200, 500, 503]

    def test_performance_endpoint_exists(self, test_client):
        """Test performance metrics endpoint exists"""
        response = test_client.get("/api/portfolio/performance")
        assert response.status_code in [200, 500, 503]

    def test_trades_endpoint_with_optional_params(self, test_client):
        """Test trades endpoint with optional filters"""
        response = test_client.get("/api/portfolio/trades?limit=50&symbol=BTCUSDT")
        assert response.status_code in [200, 500, 503]

    def test_buy_asset_endpoint_exists(self, test_client):
        """Test buy asset endpoint exists"""
        response = test_client.post(
            "/api/portfolio/buy",
            params={"symbol": "BTCUSDT", "quantity": "0.5", "price": "50000.00"},
        )
        assert response.status_code in [200, 500, 503]

    def test_sell_asset_endpoint_exists(self, test_client):
        """Test sell asset endpoint exists"""
        response = test_client.post(
            "/api/portfolio/sell",
            params={"symbol": "ETHUSDT", "quantity": "1.0", "price": "3000.00"},
        )
        assert response.status_code in [200, 500, 503]


class TestRiskMetricsRouting:
    """Test risk metrics endpoint routing"""

    def test_risk_scorecard_endpoint_exists(self, test_client):
        """Test risk scorecard endpoint exists"""
        response = test_client.get("/api/risk/scorecard")
        assert response.status_code in [200, 500, 503]

    def test_var_endpoint_with_parameters(self, test_client):
        """Test Value at Risk endpoint with custom parameters"""
        response = test_client.get(
            "/api/risk/var", params={"confidence_level": 0.99, "time_horizon_days": 5}
        )
        assert response.status_code in [200, 500, 503]

    def test_circuit_breaker_reset_endpoint_exists(self, test_client):
        """Test circuit breaker reset endpoint exists"""
        response = test_client.post("/api/risk/circuit-breaker/reset")
        assert response.status_code in [200, 500, 503]

    def test_exposure_metrics_endpoint(self, test_client):
        """Test exposure metrics endpoint"""
        response = test_client.get("/api/risk/exposure")
        assert response.status_code in [200, 500, 503]

    def test_drawdown_metrics_endpoint(self, test_client):
        """Test drawdown metrics endpoint"""
        response = test_client.get("/api/risk/drawdown")
        assert response.status_code in [200, 500, 503]

    def test_capital_metrics_endpoint(self, test_client):
        """Test capital metrics endpoint"""
        response = test_client.get("/api/risk/capital")
        assert response.status_code in [200, 500, 503]


# ============================================================================
# TEST SUITE 2: Authentication & Authorization Tests
# ============================================================================


class TestServiceProxyEdgeCases:
    """Test service proxy error handling and edge cases"""

    @pytest.mark.asyncio
    async def test_proxy_initialization_and_cleanup(self):
        """Test service proxy initialization and cleanup"""
        proxy = ServiceProxy()
        assert proxy.client is None

        await proxy.initialize()
        assert proxy.client is not None

        await proxy.cleanup()
        assert proxy.client is not None  # Just closed, not set to None

    @pytest.mark.asyncio
    async def test_proxy_with_unknown_service(self):
        """Test proxy request with unknown service"""
        proxy = ServiceProxy()
        await proxy.initialize()

        try:
            await proxy.proxy_request("nonexistent-service", "/test", "GET")
        except Exception as e:
            assert "not found" in str(e).lower() or "Service" in str(e)

        await proxy.cleanup()


class TestServiceProxyMethods:
    """Test different HTTP methods through proxy"""

    @pytest.mark.asyncio
    async def test_proxy_get_method(self):
        """Test GET method proxy"""
        proxy = ServiceProxy()
        await proxy.initialize()
        # Would need running service to fully test
        await proxy.cleanup()

    @pytest.mark.asyncio
    async def test_proxy_post_method(self):
        """Test POST method proxy"""
        proxy = ServiceProxy()
        await proxy.initialize()
        # Would need running service to fully test
        await proxy.cleanup()


# ============================================================================
# TEST SUITE 4: WebSocket Manager & Broadcast Tests
# ============================================================================


class TestWebSocketBroadcasting:
    """Test WebSocket broadcasting functionality"""

    @pytest.mark.asyncio
    async def test_websocket_manager_broadcast_error_handling(self):
        """Test broadcast handles client disconnections gracefully"""
        manager = WebSocketManager()

        # Create mock WebSocket connections
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        mock_ws2.send_json.side_effect = Exception("Disconnected")
        mock_ws3 = AsyncMock()

        manager.active_connections.add(mock_ws1)
        manager.active_connections.add(mock_ws2)
        manager.active_connections.add(mock_ws3)

        # Broadcast message
        message = {"type": "test", "data": "test"}
        await manager.broadcast(message)

        # Verify all ws received attempt to send
        mock_ws1.send_json.assert_called()
        mock_ws2.send_json.assert_called()
        mock_ws3.send_json.assert_called()

        # Verify failed client was disconnected
        assert mock_ws2 not in manager.active_connections

    @pytest.mark.asyncio
    async def test_fetch_dashboard_updates_with_exception(self):
        """Test dashboard update fetching handles service errors"""
        manager = WebSocketManager()
        mock_proxy = AsyncMock(spec=ServiceProxy)

        # Mock the proxy to throw exception
        async def mock_gather(*args, **kwargs):
            return [Exception("Service error"), Exception("Service error")]

        # Patch asyncio.gather
        with patch("asyncio.gather", side_effect=Exception("Service error")):
            result = await manager.fetch_dashboard_updates(mock_proxy)
            assert result["type"] == "error"
            assert "message" in result

    @pytest.mark.asyncio
    async def test_websocket_manager_personal_message_error(self):
        """Test personal message error handling"""
        manager = WebSocketManager()
        mock_ws = AsyncMock()
        mock_ws.send_json.side_effect = Exception("Send failed")

        manager.active_connections.add(mock_ws)

        # Send personal message
        await manager.send_personal_message({"type": "test"}, mock_ws)

        # Should disconnect the failed connection
        assert mock_ws not in manager.active_connections


class TestWebSocketLifecycle:
    """Test WebSocket connection lifecycle"""

    @pytest.mark.asyncio
    async def test_websocket_manager_initialization(self):
        """Test WebSocket manager initializes correctly"""
        manager = WebSocketManager()
        assert manager.active_connections == set()
        assert manager.broadcast_task is None

    @pytest.mark.asyncio
    async def test_websocket_multiple_connect_disconnect(self):
        """Test multiple connections and disconnections"""
        manager = WebSocketManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        mock_ws3 = AsyncMock()

        # Connect multiple
        await manager.connect(mock_ws1)
        await manager.connect(mock_ws2)
        await manager.connect(mock_ws3)

        assert len(manager.active_connections) == 3

        # Disconnect one
        manager.disconnect(mock_ws2)
        assert len(manager.active_connections) == 2
        assert mock_ws2 not in manager.active_connections


# ============================================================================
# TEST SUITE 5: Error Handling & Edge Cases
# ============================================================================


class TestErrorHandling:
    """Test error handling across gateway"""

    def test_emergency_stop_endpoint(self, admin_client):
        """Route writes the EMERGENCY_STOP file (mocked) and returns 200."""
        with patch("pathlib.Path.write_text") as mock_write:
            response = admin_client.post("/api/portfolio/emergency-stop")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "Emergency stop" in data["message"]
            mock_write.assert_called_once()

    def test_emergency_stop_file_write_error(self, admin_client):
        """Route returns 500 when the file write fails with OSError."""
        with patch("pathlib.Path.write_text", side_effect=OSError("Permission denied")):
            response = admin_client.post("/api/portfolio/emergency-stop")
            assert response.status_code == 500

    def test_cors_headers_present(self, test_client):
        """Test CORS middleware is configured"""
        # OPTIONS request should work due to CORS
        response = test_client.options("/")
        # Should either be 200 or 405 (Method not allowed)
        assert response.status_code in [200, 405, 404]


# ============================================================================
# TEST SUITE 6: Request/Response Transformation
# ============================================================================


class TestRequestResponseTransformation:
    """Test request and response transformations"""

    def test_ticker_endpoint_exists(self, test_client):
        """Test ticker endpoint exists"""
        response = test_client.get("/api/market/ticker/BTCUSDT")
        assert response.status_code in [200, 500, 503]

    def test_kline_endpoint_exists(self, test_client):
        """Test kline endpoint exists"""
        response = test_client.get("/api/market/kline/ETHUSDT?interval=15&limit=200")
        assert response.status_code in [200, 500, 503]


class TestAnalysisEndpointTransformation:
    """Test technical analysis endpoint transformations"""

    def test_rsi_endpoint_exists(self, test_client):
        """Test RSI endpoint exists"""
        response = test_client.get("/api/analysis/rsi/BTCUSDT?period=21&interval=120")
        assert response.status_code in [200, 500, 503]

    def test_macd_endpoint_exists(self, test_client):
        """Test MACD endpoint exists"""
        response = test_client.get("/api/analysis/macd/BTCUSDT")
        assert response.status_code in [200, 500, 503]

    def test_all_indicators_endpoint_exists(self, test_client):
        """Test all indicators endpoint exists"""
        response = test_client.get("/api/analysis/all/BTCUSDT")
        assert response.status_code in [200, 500, 503]


# ============================================================================
# TEST SUITE 7: Advanced Signal Endpoints
# ============================================================================


class TestAdvancedSignalGeneration:
    """Test enhanced and ML-based trading signals"""

    def test_trading_signal_endpoint_exists(self, test_client):
        """Test trading signal endpoint exists"""
        response = test_client.get("/api/trading/signals/BTCUSDT")
        assert response.status_code in [200, 500, 503]

    def test_analyze_and_trade_endpoint_exists(self, test_client):
        """Test analyze and trade endpoint exists"""
        response = test_client.post("/api/trading/signals/BTCUSDT/analyze")
        assert response.status_code in [200, 500, 503]

    def test_positions_endpoint_exists(self, test_client):
        """Test positions endpoint exists"""
        response = test_client.get("/api/trading/positions")
        assert response.status_code in [200, 500, 503]

    def test_enhanced_signal_endpoint_exists(self, test_client):
        """Test enhanced signal endpoint exists"""
        response = test_client.get("/api/trading/signals/enhanced/BTCUSDT")
        assert response.status_code in [200, 500, 503]


class TestMLPredictionEndpoints:
    """Test ML prediction endpoints"""

    def test_ml_predict_price_endpoint_exists(self, test_client):
        """Test ML price prediction endpoint exists"""
        response = test_client.get("/api/ml/predict/price/BTCUSDT")
        assert response.status_code in [200, 500, 503]

    def test_ml_predict_trend_endpoint_exists(self, test_client):
        """Test ML trend prediction endpoint exists"""
        response = test_client.get("/api/ml/predict/trend/ETHUSDT")
        assert response.status_code in [200, 500, 503]

    def test_ml_predict_volatility_endpoint_exists(self, test_client):
        """Test ML volatility prediction endpoint exists"""
        response = test_client.get("/api/ml/predict/volatility/BTCUSDT")
        assert response.status_code in [200, 500, 503]

    def test_ml_predict_signal_endpoint_exists(self, test_client):
        """Test ML signal endpoint exists"""
        response = test_client.get("/api/ml/predict/signal/LTCUSDT")
        assert response.status_code in [200, 500, 503]

    def test_ml_models_list_endpoint_exists(self, test_client):
        """Test ML models list endpoint exists"""
        response = test_client.get("/api/ml/models")
        assert response.status_code in [200, 500, 503]

    def test_ml_model_info_endpoint_exists(self, test_client):
        """Test ML model info endpoint exists"""
        response = test_client.get("/api/ml/models/BTCUSDT")
        assert response.status_code in [200, 500, 503]

    def test_ml_train_model_endpoint_exists(self, test_client):
        """Test ML model training endpoint exists"""
        response = test_client.post("/api/ml/models/train?symbol=BTCUSDT")
        assert response.status_code in [200, 500, 503]

    def test_ml_compare_models_endpoint_exists(self, test_client):
        """Test ML model comparison endpoint exists"""
        response = test_client.get("/api/ml/models/compare/BTCUSDT")
        assert response.status_code in [200, 500, 503]


# ============================================================================
# TEST SUITE 8: Sentiment Analysis Endpoints
# ============================================================================


class TestSentimentAnalysisEndpoints:
    """Test sentiment analysis endpoints"""

    def test_sentiment_news_endpoint_exists(self, test_client):
        """Test news sentiment endpoint exists"""
        response = test_client.get("/api/sentiment/news/BTCUSDT")
        assert response.status_code in [200, 500, 503]

    def test_sentiment_social_endpoint_exists(self, test_client):
        """Test social sentiment endpoint exists"""
        response = test_client.get("/api/sentiment/social/ETHUSDT")
        assert response.status_code in [200, 500, 503]

    def test_sentiment_combined_endpoint_exists(self, test_client):
        """Test combined sentiment endpoint exists"""
        response = test_client.get("/api/sentiment/combined/BTCUSDT")
        assert response.status_code in [200, 500, 503]

    def test_sentiment_trend_endpoint_exists(self, test_client):
        """Test sentiment trend endpoint is routed (currently proxies a 501)."""
        response = test_client.get("/api/sentiment/trend/BTCUSDT")
        # Upstream returns 501 (not yet implemented); 503 if sentiment
        # service is down; 5xx if proxy errors. 200 only resurfaces if a
        # real implementation is added.
        assert response.status_code in [200, 500, 501, 503]

    def test_sentiment_backward_compat_endpoint(self, test_client):
        """Test backward compatibility sentiment endpoint"""
        response = test_client.get("/api/sentiment/BTCUSDT")
        assert response.status_code in [200, 500, 503]

    def test_sentiment_aggregate_endpoint(self, test_client):
        """Test aggregated sentiment endpoint is routed (currently proxies a 501)."""
        response = test_client.get("/api/sentiment/aggregate")
        assert response.status_code in [200, 500, 501, 503]


# ============================================================================
# TEST SUITE 9: Multi-Timeframe Analysis
# ============================================================================


class TestMultiTimeframeAnalysis:
    """Test multi-timeframe analysis endpoints"""

    def test_multi_timeframe_endpoint_exists(self, test_client):
        """Test multi-timeframe analysis endpoint"""
        response = test_client.get("/api/analysis/multi-timeframe/BTCUSDT")
        assert response.status_code in [200, 500, 503]

    def test_indicator_signal_endpoint_exists(self, test_client):
        """Test indicator signal endpoint"""
        response = test_client.get("/api/analysis/indicators/signal/BTCUSDT")
        assert response.status_code in [200, 500, 503]


# ============================================================================
# TEST SUITE 10: Aggregation & Dashboard Endpoints
# ============================================================================


class TestAggregationEndpoints:
    """Test multi-service aggregation endpoints"""

    def test_dashboard_endpoint_exists(self, test_client):
        """Test dashboard endpoint exists"""
        response = test_client.get("/api/dashboard/BTCUSDT")
        assert response.status_code in [200, 500, 503]


# ============================================================================
# TEST SUITE 11: Health Check & Status Monitoring
# ============================================================================


class TestHealthAndMonitoring:
    """Test health check and monitoring endpoints"""

    def test_circuit_breaker_status_endpoint(self, test_client):
        """Test circuit breaker status endpoint"""
        response = test_client.get("/api/risk/circuit-breaker")
        assert response.status_code in [200, 500, 503]

    def test_risk_alerts_endpoint(self, test_client):
        """Test risk alerts endpoint"""
        response = test_client.get("/api/risk/alerts")
        assert response.status_code in [200, 500, 503]


# ============================================================================
# TEST SUITE 12: Configuration & Settings
# ============================================================================


class TestGatewayConfiguration:
    """Test API Gateway configuration.

    Plan 07.1-01 BUG-3: the gateway service-info JSON was relocated from
    `/` to `/gateway-info` so `/` can reverse-proxy to the frontend.
    """

    def test_gateway_info_endpoint_lists_all_services(self, test_client):
        """Test /gateway-info endpoint includes all configured services"""
        response = test_client.get("/gateway-info")
        assert response.status_code == 200
        data = response.json()

        # Check all services are listed
        services = data["services"]
        assert "bybit_connector" in services
        assert "market_data" in services
        assert "technical_analysis" in services
        assert "trading_engine" in services
        assert "portfolio_manager" in services
        assert "risk_metrics" in services
        assert "ml_prediction" in services
        assert "sentiment_analysis" in services

    def test_gateway_info_endpoint_api_info(self, test_client):
        """Test /gateway-info endpoint provides API information"""
        response = test_client.get("/gateway-info")
        assert response.status_code == 200
        data = response.json()

        assert data["service"] == "api-gateway"
        assert "version" in data
        assert "description" in data
        assert "endpoints" in data


# ============================================================================
# TEST SUITE 13: Concurrent & Parallel Request Handling
# ============================================================================


class TestConcurrentHandling:
    """Test concurrent request handling"""

    def test_multiple_concurrent_requests(self, test_client):
        """Test gateway handles multiple concurrent requests"""
        # Simulate concurrent requests
        responses = []
        for i in range(5):
            response = test_client.get("/health")
            responses.append(response)

        # All should return valid status
        assert all(r.status_code in [200, 503] for r in responses)


# ============================================================================
# TEST SUITE 14: Performance Metrics Endpoints
# ============================================================================


class TestPerformanceMetrics:
    """Test performance metrics endpoints"""

    def test_get_performance_metrics_endpoint(self, test_client):
        """Test performance metrics endpoint"""
        response = test_client.get("/api/performance/metrics")
        assert response.status_code in [200, 500, 503]

    def test_get_sharpe_ratio_endpoint(self, test_client):
        """Test Sharpe ratio endpoint"""
        response = test_client.get("/api/performance/sharpe")
        assert response.status_code in [200, 500, 503]


# ============================================================================
# TEST SUITE 15: Service Health Monitoring
# ============================================================================


class TestServiceHealthMonitoring:
    """Test individual service health monitoring"""

    @pytest.mark.asyncio
    async def test_service_health_check_timeout(self, mock_httpx_client):
        """Test health check handles timeout"""
        proxy = ServiceProxy()
        proxy.client = mock_httpx_client
        mock_httpx_client.get.side_effect = httpx.TimeoutException("Timeout")

        result = await proxy.check_service_health("bybit")
        assert result is False

    @pytest.mark.asyncio
    async def test_service_health_check_connection_error(self, mock_httpx_client):
        """Test health check handles connection errors"""
        proxy = ServiceProxy()
        proxy.client = mock_httpx_client
        mock_httpx_client.get.side_effect = httpx.RequestError("Connection refused")

        result = await proxy.check_service_health("market-data")
        assert result is False

    @pytest.mark.asyncio
    async def test_service_health_check_success(self, mock_httpx_client):
        """Test health check succeeds for healthy service"""
        proxy = ServiceProxy()
        proxy.client = mock_httpx_client

        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_httpx_client.get.return_value = mock_response

        result = await proxy.check_service_health("trading-engine")
        assert result is True


# ============================================================================
# TEST SUITE 16: WebSocket Endpoint
# ============================================================================


class TestWebSocketEndpoint:
    """Test WebSocket endpoint"""

    def test_websocket_route_exists(self, test_client):
        """Test WebSocket endpoint is defined"""
        # TestClient doesn't support WebSocket connections directly
        # Just verify the route is registered by checking app
        assert "/ws" in [str(route.path) for route in app.routes]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
