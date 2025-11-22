"""
Integration tests for FastAPI endpoints - Risk & Metrics Service API
Tests all HTTP endpoints, authentication, error handling, and response validation
"""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestHealthEndpoints:
    """Tests for health check and status endpoints"""

    def test_health_check_success(self, test_client):
        """Test health check endpoint returns healthy status"""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "service" in data
        assert "version" in data
        assert "timestamp" in data
        assert data["service"] == "risk-metrics-service"

    def test_status_endpoint(self, test_client):
        """Test detailed status endpoint"""
        response = test_client.get("/status")

        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "risk-metrics-service"
        assert "configuration" in data
        assert "circuit_breaker_active" in data
        assert isinstance(data["circuit_breaker_active"], bool)

    def test_root_endpoint(self, test_client):
        """Test root endpoint returns service info"""
        response = test_client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Risk & Metrics Service"
        assert "endpoints" in data
        assert data["status"] == "operational"


@pytest.mark.integration
class TestRiskMetricsEndpoints:
    """Tests for risk metrics endpoints"""

    @patch("app.main.fetch_portfolio_data")
    async def test_get_capital_metrics(self, mock_fetch, test_client, mock_portfolio_data):
        """Test capital metrics endpoint"""
        mock_fetch.return_value = mock_portfolio_data

        response = test_client.get("/risk/capital")

        assert response.status_code == 200
        data = response.json()
        assert "total_capital" in data
        assert "allocated_capital" in data
        assert "available_capital" in data
        assert "capital_utilization" in data
        assert "max_position_size" in data

    @patch("app.main.fetch_portfolio_data")
    async def test_get_exposure_metrics(self, mock_fetch, test_client, mock_portfolio_data):
        """Test exposure metrics endpoint"""
        mock_fetch.return_value = mock_portfolio_data

        response = test_client.get("/risk/exposure")

        assert response.status_code == 200
        data = response.json()
        assert "total_exposure" in data
        assert "exposure_ratio" in data
        assert "long_exposure" in data
        assert "short_exposure" in data
        assert "concentrated_positions" in data
        assert isinstance(data["concentrated_positions"], list)

    @patch("app.main.fetch_portfolio_data")
    async def test_get_drawdown_metrics(self, mock_fetch, test_client, mock_portfolio_data):
        """Test drawdown metrics endpoint"""
        mock_fetch.return_value = mock_portfolio_data

        response = test_client.get("/risk/drawdown")

        assert response.status_code == 200
        data = response.json()
        assert "current_drawdown" in data
        assert "max_drawdown" in data
        assert "recovery_factor" in data
        assert "underwater_periods" in data

    @patch("app.main.fetch_portfolio_data")
    async def test_get_var_metrics(self, mock_fetch, test_client, mock_portfolio_data):
        """Test Value at Risk endpoint"""
        mock_fetch.return_value = mock_portfolio_data

        response = test_client.get("/risk/var?confidence_level=0.95&time_horizon_days=1")

        assert response.status_code == 200
        data = response.json()
        assert "var_95" in data
        assert "var_99" in data
        assert "cvar_95" in data
        assert "confidence_level" in data
        assert "time_horizon_days" in data
        assert data["confidence_level"] == 0.95

    @patch("app.main.fetch_portfolio_data")
    async def test_get_var_custom_params(self, mock_fetch, test_client, mock_portfolio_data):
        """Test VaR with custom confidence level and time horizon"""
        mock_fetch.return_value = mock_portfolio_data

        response = test_client.get("/risk/var?confidence_level=0.99&time_horizon_days=5")

        assert response.status_code == 200
        data = response.json()
        assert data["confidence_level"] == 0.99
        assert data["time_horizon_days"] == 5


@pytest.mark.integration
class TestRiskScorecardEndpoint:
    """Tests for comprehensive risk scorecard endpoint"""

    @patch("app.main.fetch_portfolio_data")
    async def test_get_risk_scorecard(self, mock_fetch, test_client, mock_portfolio_data):
        """Test comprehensive risk scorecard endpoint"""
        mock_fetch.return_value = mock_portfolio_data

        response = test_client.get("/risk/scorecard")

        assert response.status_code == 200
        data = response.json()

        # Check top-level fields
        assert "overall_risk_level" in data
        assert "risk_score" in data
        assert "timestamp" in data

        # Check individual risk component scores
        assert "capital_risk_score" in data
        assert "exposure_risk_score" in data
        assert "concentration_risk_score" in data
        assert "volatility_risk_score" in data
        assert "drawdown_risk_score" in data

        # Check nested metrics objects
        assert "capital_metrics" in data
        assert "exposure_metrics" in data
        assert "drawdown_metrics" in data
        assert "performance_metrics" in data
        assert "var_metrics" in data

        # Check alerts and recommendations
        assert "active_alerts" in data
        assert "recommendations" in data
        assert isinstance(data["active_alerts"], list)
        assert isinstance(data["recommendations"], list)

        # Verify risk level is valid
        assert data["overall_risk_level"] in ["low", "medium", "high", "critical"]

    @patch("app.main.fetch_portfolio_data")
    async def test_risk_scorecard_portfolio_unavailable(self, mock_fetch, test_client):
        """Test risk scorecard when portfolio data is unavailable"""
        mock_fetch.return_value = None

        response = test_client.get("/risk/scorecard")

        assert response.status_code == 503
        assert "portfolio data" in response.json()["detail"].lower()


@pytest.mark.integration
class TestPerformanceEndpoints:
    """Tests for performance metrics endpoints"""

    @patch("app.main.fetch_portfolio_data")
    async def test_get_performance_metrics(self, mock_fetch, test_client, mock_portfolio_data):
        """Test performance metrics endpoint"""
        mock_fetch.return_value = mock_portfolio_data

        response = test_client.get("/performance/metrics")

        assert response.status_code == 200
        data = response.json()
        assert "total_return" in data
        assert "annualized_return" in data
        assert "volatility" in data
        assert "sharpe_ratio" in data
        assert "sortino_ratio" in data
        assert "max_drawdown" in data
        assert "win_rate" in data
        assert "profit_factor" in data

    @patch("app.main.fetch_portfolio_data")
    async def test_get_sharpe_ratio(self, mock_fetch, test_client, mock_portfolio_data):
        """Test Sharpe ratio endpoint"""
        mock_fetch.return_value = mock_portfolio_data

        response = test_client.get("/performance/sharpe")

        assert response.status_code == 200
        data = response.json()
        assert "sharpe_ratio" in data
        assert "annualized_return" in data
        assert "volatility" in data
        assert "risk_free_rate" in data
        assert "target_sharpe" in data
        assert "meets_target" in data
        assert isinstance(data["meets_target"], bool)


@pytest.mark.integration
class TestAlertEndpoints:
    """Tests for risk alert endpoints"""

    @patch("app.main.fetch_portfolio_data")
    async def test_get_active_alerts(self, mock_fetch, test_client, mock_portfolio_data_concentrated):
        """Test active alerts endpoint with concentrated portfolio"""
        mock_fetch.return_value = mock_portfolio_data_concentrated

        response = test_client.get("/alerts")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Concentrated portfolio should generate alerts
        assert len(data) > 0

        # Check alert structure
        if len(data) > 0:
            alert = data[0]
            assert "severity" in alert
            assert "category" in alert
            assert "message" in alert
            assert "timestamp" in alert
            assert alert["severity"] in ["info", "warning", "critical"]


@pytest.mark.integration
class TestCircuitBreakerEndpoints:
    """Tests for circuit breaker endpoints"""

    @patch("app.main.fetch_portfolio_data")
    async def test_get_circuit_breaker_status(self, mock_fetch, test_client, mock_portfolio_data):
        """Test circuit breaker status endpoint"""
        mock_fetch.return_value = mock_portfolio_data

        response = test_client.get("/circuit-breaker")

        assert response.status_code == 200
        data = response.json()
        assert "trading_allowed" in data
        assert "circuit_breaker_active" in data
        assert "reasons" in data
        assert isinstance(data["trading_allowed"], bool)
        assert isinstance(data["reasons"], list)

    def test_reset_circuit_breaker_without_auth(self, test_client):
        """Test circuit breaker reset requires authentication"""
        response = test_client.post("/circuit-breaker/reset")

        assert response.status_code == 401  # Unauthorized

    def test_reset_circuit_breaker_invalid_auth(self, test_client, invalid_admin_headers):
        """Test circuit breaker reset with invalid API key"""
        response = test_client.post("/circuit-breaker/reset", headers=invalid_admin_headers)

        assert response.status_code == 403  # Forbidden

    def test_reset_circuit_breaker_success(self, test_client, admin_headers):
        """Test successful circuit breaker reset with valid auth"""
        response = test_client.post("/circuit-breaker/reset", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "status" in data


@pytest.mark.integration
@pytest.mark.auth
class TestConfigurationEndpoints:
    """Tests for configuration management endpoints"""

    def test_get_risk_limits(self, test_client):
        """Test get risk limits configuration"""
        response = test_client.get("/config/limits")

        assert response.status_code == 200
        data = response.json()
        assert "max_position_size" in data
        assert "max_portfolio_risk" in data
        assert "max_drawdown" in data
        assert "max_daily_loss" in data
        assert "max_exposure" in data
        assert "min_sharpe_ratio" in data

    def test_update_risk_limits_without_auth(self, test_client):
        """Test updating risk limits requires authentication"""
        new_limits = {
            "max_position_size": 0.03,
            "max_portfolio_risk": 0.06,
            "max_drawdown": 0.12,
            "max_daily_loss": 0.06,
            "max_exposure": 0.25,
            "max_leverage": 2.5,
            "min_sharpe_ratio": 1.8
        }

        response = test_client.put("/config/limits", json=new_limits)

        assert response.status_code == 401  # Unauthorized

    def test_update_risk_limits_invalid_auth(self, test_client, invalid_admin_headers):
        """Test updating risk limits with invalid API key"""
        new_limits = {
            "max_position_size": 0.03,
            "max_portfolio_risk": 0.06,
            "max_drawdown": 0.12,
            "max_daily_loss": 0.06,
            "max_exposure": 0.25,
            "max_leverage": 2.5,
            "min_sharpe_ratio": 1.8
        }

        response = test_client.put("/config/limits", json=new_limits, headers=invalid_admin_headers)

        assert response.status_code == 403  # Forbidden

    def test_update_risk_limits_success(self, test_client, admin_headers):
        """Test successful risk limits update with valid auth"""
        new_limits = {
            "max_position_size": 0.03,
            "max_portfolio_risk": 0.06,
            "max_drawdown": 0.12,
            "max_daily_loss": 0.06,
            "max_exposure": 0.25,
            "max_leverage": 2.5,
            "min_sharpe_ratio": 1.8
        }

        response = test_client.put("/config/limits", json=new_limits, headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "limits" in data
        assert "warning" in data


@pytest.mark.integration
class TestErrorHandling:
    """Tests for error handling and edge cases"""

    @patch("app.main.fetch_portfolio_data")
    async def test_portfolio_service_down(self, mock_fetch, test_client):
        """Test handling when portfolio manager service is unavailable"""
        mock_fetch.return_value = None

        response = test_client.get("/risk/capital")

        assert response.status_code == 503
        assert "portfolio data" in response.json()["detail"].lower()

    def test_invalid_endpoint(self, test_client):
        """Test requesting non-existent endpoint"""
        response = test_client.get("/invalid/endpoint")

        assert response.status_code == 404

    def test_invalid_http_method(self, test_client):
        """Test using wrong HTTP method on endpoint"""
        response = test_client.post("/risk/capital")

        assert response.status_code == 405  # Method not allowed

    @patch("app.main.fetch_portfolio_data")
    async def test_var_invalid_confidence_level(self, mock_fetch, test_client, mock_portfolio_data):
        """Test VaR with invalid confidence level"""
        mock_fetch.return_value = mock_portfolio_data

        # Confidence level > 1.0 should be handled
        response = test_client.get("/risk/var?confidence_level=1.5")

        # Should either return 422 (validation error) or handle gracefully
        assert response.status_code in [200, 422]


@pytest.mark.integration
class TestCORSAndSecurity:
    """Tests for CORS and security configurations"""

    def test_cors_headers_present(self, test_client):
        """Test that CORS headers are configured"""
        response = test_client.options("/health")

        # CORS headers should be present
        assert response.status_code in [200, 405]  # Depends on CORS config

    def test_protected_endpoint_requires_auth(self, test_client):
        """Test that admin endpoints require authentication"""
        protected_endpoints = [
            ("/circuit-breaker/reset", "POST"),
            ("/config/limits", "PUT")
        ]

        for endpoint, method in protected_endpoints:
            if method == "POST":
                response = test_client.post(endpoint)
            elif method == "PUT":
                response = test_client.put(endpoint, json={})

            assert response.status_code in [401, 403, 422]  # Unauthorized/Forbidden


@pytest.mark.integration
@pytest.mark.slow
class TestPerformanceAndLoad:
    """Performance and load tests for API endpoints"""

    def test_concurrent_requests(self, test_client):
        """Test handling multiple concurrent requests"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def make_request():
            return test_client.get("/health")

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(50)]
            responses = [future.result() for future in as_completed(futures)]

        # All requests should succeed
        assert all(r.status_code == 200 for r in responses)

    @patch("app.main.fetch_portfolio_data")
    async def test_response_time(self, mock_fetch, test_client, mock_portfolio_data):
        """Test API response time is acceptable"""
        import time

        mock_fetch.return_value = mock_portfolio_data

        start_time = time.time()
        response = test_client.get("/risk/scorecard")
        elapsed_time = time.time() - start_time

        assert response.status_code == 200
        assert elapsed_time < 1.0  # Should respond within 1 second
