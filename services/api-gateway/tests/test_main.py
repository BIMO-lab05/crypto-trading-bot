"""
Tests for API Gateway Main Application
Tests all endpoints, error handling, and CORS configuration
"""

import pytest
from unittest.mock import patch
from fastapi.responses import JSONResponse
import json


class TestGatewayInfoEndpoint:
    """Test gateway-info endpoint.

    Plan 07.1-01 BUG-3: the JSON service-info response that historically
    lived at `/` was relocated to `/gateway-info` so the catch-all
    reverse-proxy can serve the React SPA from `/`.
    """

    def test_gateway_info_returns_service_info(self, test_client):
        """Test that /gateway-info endpoint returns service information"""
        response = test_client.get("/gateway-info")

        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "api-gateway"
        assert "version" in data
        assert "services" in data
        assert "endpoints" in data

    def test_gateway_info_includes_all_services(self, test_client):
        """Test that /gateway-info endpoint lists all backend services"""
        response = test_client.get("/gateway-info")
        data = response.json()

        services = data["services"]
        assert "bybit_connector" in services
        assert "market_data" in services
        assert "technical_analysis" in services
        assert "trading_engine" in services
        assert "portfolio_manager" in services


class TestHealthEndpoint:
    """Test health check endpoint"""

    @pytest.mark.asyncio
    async def test_health_check_all_services_healthy(
        self, test_client, mock_service_proxy, sample_health_checks
    ):
        """Test health check when all services are healthy"""
        mock_service_proxy.aggregate_health_checks.return_value = sample_health_checks

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "backend_services" in data
        assert data["backend_services"]["bybit_connector"] is True
        assert data["backend_services"]["market_data"] is True

    @pytest.mark.asyncio
    async def test_health_check_some_services_down(
        self, test_client, mock_service_proxy
    ):
        """Test health check when some services are unavailable"""
        degraded_health = {
            "bybit": True,
            "market-data": False,
            "technical-analysis": True,
            "trading-engine": False,
            "portfolio-manager": True,
        }
        mock_service_proxy.aggregate_health_checks.return_value = degraded_health

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = test_client.get("/health")

        # 503 on degraded since 2026-08-05 (AUDIT 4.4): a 200 here made the
        # container healthcheck pass while required backends were down.
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["backend_services"]["market_data"] is False
        assert data["backend_services"]["trading_engine"] is False


class TestMarketDataRoutes:
    """Test market data endpoints"""

    @pytest.mark.asyncio
    async def test_get_ticker_success(
        self, test_client, mock_service_proxy, sample_ticker_response
    ):
        """Test successful ticker data retrieval"""
        mock_response = JSONResponse(content=sample_ticker_response)
        mock_response.body = json.dumps(sample_ticker_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = test_client.get("/api/market/ticker/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert "ticker" in data
        assert data["ticker"]["symbol"] == "BTCUSDT"
        assert "last_price" in data["ticker"]

    @pytest.mark.asyncio
    async def test_get_kline_with_parameters(self, test_client, mock_service_proxy):
        """Test kline endpoint with query parameters"""
        mock_response = JSONResponse(content={"success": True, "data": []})
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = test_client.get(
                "/api/market/kline/BTCUSDT?interval=60&limit=100"
            )

        assert response.status_code == 200
        # Verify proxy was called with correct parameters
        call_kwargs = mock_service_proxy.proxy_request.call_args[1]
        assert call_kwargs["query_params"]["interval"] == "60"
        assert call_kwargs["query_params"]["limit"] == 100  # Integer, not string


class TestTechnicalAnalysisRoutes:
    """Test technical analysis endpoints"""

    @pytest.mark.asyncio
    async def test_get_rsi(self, test_client, mock_service_proxy):
        """Test RSI indicator endpoint"""
        mock_response = JSONResponse(content={"success": True, "data": {"rsi": 65.5}})
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = test_client.get(
                "/api/analysis/rsi/BTCUSDT?interval=60&period=14"
            )

        assert response.status_code == 200
        call_kwargs = mock_service_proxy.proxy_request.call_args[1]
        assert call_kwargs["service_name"] == "technical-analysis"
        assert "rsi" in call_kwargs["path"]

    @pytest.mark.asyncio
    async def test_get_macd(self, test_client, mock_service_proxy):
        """Test MACD indicator endpoint"""
        mock_response = JSONResponse(content={"success": True, "data": {}})
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = test_client.get("/api/analysis/macd/ETHUSDT")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_all_indicators(self, test_client, mock_service_proxy):
        """Test endpoint for all technical indicators"""
        mock_response = JSONResponse(content={"success": True, "data": {}})
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = test_client.get("/api/analysis/all/BTCUSDT")

        assert response.status_code == 200


class TestTradingEngineRoutes:
    """Test trading engine endpoints"""

    @pytest.mark.asyncio
    async def test_get_trading_signal(self, test_client, mock_service_proxy):
        """Test trading signal retrieval"""
        mock_response = JSONResponse(content={"success": True, "signal": "BUY"})
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = test_client.get("/api/trading/signals/BTCUSDT")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_analyze_and_trade(self, admin_client, mock_service_proxy):
        """Test analyze and trade endpoint (auth required)"""
        mock_response = JSONResponse(content={"success": True, "data": {}})
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = admin_client.post(
                "/api/trading/signals/BTCUSDT/analyze?execute=false"
            )

        assert response.status_code == 200
        call_kwargs = mock_service_proxy.proxy_request.call_args[1]
        assert call_kwargs["method"] == "POST"

    @pytest.mark.asyncio
    async def test_get_positions(self, test_client, mock_service_proxy):
        """Test get positions endpoint"""
        mock_response = JSONResponse(content={"success": True, "positions": []})
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = test_client.get("/api/trading/positions?status=open")

        assert response.status_code == 200


class TestPortfolioRoutes:
    """Test portfolio management endpoints"""

    @pytest.mark.asyncio
    async def test_get_portfolio(
        self, test_client, mock_service_proxy, sample_portfolio_response
    ):
        """Test portfolio retrieval"""
        mock_response = JSONResponse(content=sample_portfolio_response)
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = test_client.get("/api/portfolio")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_balance(self, test_client, mock_service_proxy):
        """Test balance retrieval"""
        mock_response = JSONResponse(content={"success": True, "balance": "100000.00"})
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = test_client.get("/api/portfolio/balance")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_holdings(self, test_client, mock_service_proxy):
        """Test holdings retrieval"""
        mock_response = JSONResponse(content={"success": True, "holdings": []})
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = test_client.get("/api/portfolio/holdings")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_buy_asset(self, admin_client, mock_service_proxy):
        """Test buy transaction (auth required)"""
        mock_response = JSONResponse(content={"success": True, "transaction_id": "123"})
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = admin_client.post(
                "/api/portfolio/buy?symbol=BTCUSDT&quantity=1.0&price=45000"
            )

        assert response.status_code == 200
        call_kwargs = mock_service_proxy.proxy_request.call_args[1]
        assert call_kwargs["method"] == "POST"

    @pytest.mark.asyncio
    async def test_sell_asset(self, admin_client, mock_service_proxy):
        """Test sell transaction (auth required)"""
        mock_response = JSONResponse(content={"success": True, "transaction_id": "124"})
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = admin_client.post(
                "/api/portfolio/sell?symbol=BTCUSDT&quantity=0.5&price=46000"
            )

        assert response.status_code == 200


class TestEmergencyStop:
    """Test emergency stop functionality"""

    @pytest.mark.asyncio
    async def test_emergency_stop_creates_file(self, admin_client):
        """Test that emergency stop writes the stop file."""
        with patch("pathlib.Path.write_text") as mock_write:
            response = admin_client.post("/api/portfolio/emergency-stop")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Emergency stop activated" in data["message"]
        mock_write.assert_called_once()

    @pytest.mark.asyncio
    async def test_emergency_stop_handles_error(self, admin_client):
        """Route returns 500 when the file write fails with OSError."""
        with patch("pathlib.Path.write_text", side_effect=OSError("Disk error")):
            response = admin_client.post("/api/portfolio/emergency-stop")

        assert response.status_code == 500


class TestRiskMetricsRoutes:
    """Test risk and metrics endpoints"""

    @pytest.mark.asyncio
    async def test_get_risk_scorecard(self, test_client, mock_service_proxy):
        """Test risk scorecard endpoint"""
        mock_response = JSONResponse(content={"success": True, "data": {}})
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = test_client.get("/api/risk/scorecard")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_value_at_risk(self, test_client, mock_service_proxy):
        """Test VaR calculation endpoint"""
        mock_response = JSONResponse(content={"success": True, "var": 5000})
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = test_client.get(
                "/api/risk/var?confidence_level=0.95&time_horizon_days=1"
            )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_status(self, test_client, mock_service_proxy):
        """Test circuit breaker status endpoint"""
        mock_response = JSONResponse(content={"success": True, "status": "closed"})
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = test_client.get("/api/risk/circuit-breaker")

        assert response.status_code == 200


class TestDashboardAggregation:
    """Test dashboard aggregation endpoint"""

    @pytest.mark.asyncio
    async def test_dashboard_data_success(self, test_client, mock_service_proxy):
        """Test successful dashboard data aggregation"""
        ticker_response = JSONResponse(content={"success": True, "data": {}})
        ticker_response.body = b'{"success": true, "data": {}}'

        signal_response = JSONResponse(content={"success": True, "signal": "BUY"})
        signal_response.body = b'{"success": true, "signal": "BUY"}'

        portfolio_response = JSONResponse(content={"success": True, "portfolio": {}})
        portfolio_response.body = b'{"success": true, "portfolio": {}}'

        # Mock sequential calls
        mock_service_proxy.proxy_request.side_effect = [
            ticker_response,
            signal_response,
            portfolio_response,
        ]

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = test_client.get("/api/dashboard/BTCUSDT?interval=60")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["symbol"] == "BTCUSDT"
        assert "data" in data

    @pytest.mark.asyncio
    async def test_dashboard_data_partial_failure(
        self, test_client, mock_service_proxy
    ):
        """Test dashboard data with some services failing"""
        ticker_response = JSONResponse(content={"success": True, "data": {}})
        ticker_response.body = b'{"success": true, "data": {}}'

        # Second and third calls fail
        mock_service_proxy.proxy_request.side_effect = [
            ticker_response,
            Exception("Service unavailable"),
            Exception("Service unavailable"),
        ]

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = test_client.get("/api/dashboard/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Should still return partial data


class TestCORSConfiguration:
    """Test CORS middleware configuration"""

    def test_cors_allows_configured_origins(self, test_client):
        """Test that CORS allows configured origins"""
        response = test_client.options(
            "/api/market/ticker/BTCUSDT",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    def test_cors_allows_credentials(self, test_client):
        """Test that CORS allows credentials"""
        response = test_client.options(
            "/",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        # CORS middleware should be active
        assert response.status_code == 200


class TestErrorHandling:
    """Test error handling across the application"""

    @pytest.mark.asyncio
    async def test_service_proxy_not_initialized(self, test_client):
        """Test handling when service proxy is not initialized"""
        with patch("app.main.service_proxy", None):
            response = test_client.get("/api/market/ticker/BTCUSDT")

        # Should handle gracefully
        assert response.status_code in [500, 503]

    @pytest.mark.asyncio
    async def test_backend_service_timeout(self, test_client, mock_service_proxy):
        """Test handling of backend service timeout"""
        from fastapi import HTTPException

        mock_service_proxy.proxy_request.side_effect = HTTPException(
            status_code=504, detail="Timeout connecting to market-data"
        )

        with patch("app.main.get_proxy", return_value=mock_service_proxy):
            response = test_client.get("/api/market/ticker/BTCUSDT")

        assert response.status_code == 504
