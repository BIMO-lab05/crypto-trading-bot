"""
Tests for Application Lifecycle and Integration
Tests app startup, shutdown, and full integration scenarios
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
import json
import asyncio

from app.main import app, get_proxy


class TestAuthenticationEndpoints:
    """Test authentication endpoints"""

    @pytest.mark.asyncio
    async def test_register_user_success(self, test_client):
        """Test successful user registration"""
        response = test_client.post("/auth/register", json={
            "username": "testuser123",
            "email": "testuser@example.com",
            "password": "SecureP@ss123",
            "full_name": "Test User"
        })

        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "testuser123"
        assert data["email"] == "testuser@example.com"
        assert "hashed_password" not in data

    @pytest.mark.asyncio
    async def test_register_user_invalid_password(self, test_client):
        """Test registration with invalid password"""
        response = test_client.post("/auth/register", json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "weak"
        })

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, test_client):
        """Test registration with duplicate username"""
        # Register first user
        test_client.post("/auth/register", json={
            "username": "duplicate",
            "email": "user1@example.com",
            "password": "SecureP@ss123"
        })

        # Try to register with same username
        response = test_client.post("/auth/register", json={
            "username": "duplicate",
            "email": "user2@example.com",
            "password": "SecureP@ss123"
        })

        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_login_success(self, test_client):
        """Test successful login"""
        # Register user first
        test_client.post("/auth/register", json={
            "username": "logintest",
            "email": "login@example.com",
            "password": "SecureP@ss123"
        })

        # Login
        response = test_client.post("/auth/login", json={
            "username": "logintest",
            "password": "SecureP@ss123"
        })

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, test_client):
        """Test login with wrong password"""
        # Register user
        test_client.post("/auth/register", json={
            "username": "logintest2",
            "email": "login2@example.com",
            "password": "SecureP@ss123"
        })

        # Login with wrong password
        response = test_client.post("/auth/login", json={
            "username": "logintest2",
            "password": "WrongPassword123"
        })

        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, test_client):
        """Test login with nonexistent user"""
        response = test_client.post("/auth/login", json={
            "username": "nonexistent",
            "password": "SecureP@ss123"
        })

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_with_token(self, test_client):
        """Test getting current user info with valid token"""
        # Register and login
        test_client.post("/auth/register", json={
            "username": "metest",
            "email": "me@example.com",
            "password": "SecureP@ss123"
        })

        login_response = test_client.post("/auth/login", json={
            "username": "metest",
            "password": "SecureP@ss123"
        })
        token = login_response.json()["access_token"]

        # Get user info
        response = test_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "metest"

    @pytest.mark.asyncio
    async def test_get_current_user_without_token(self, test_client):
        """Test getting current user without token"""
        response = test_client.get("/auth/me")

        # 401, not 403: HTTPBearer(auto_error=True) raises Unauthorized when
        # the Authorization header is absent (RFC 7235). FastAPI corrected
        # this from 403 -> 401; picked up with the 0.141.1 bump.
        assert response.status_code == 401  # Unauthorized

    @pytest.mark.asyncio
    async def test_logout(self, test_client):
        """Test logout endpoint"""
        # Register and login
        test_client.post("/auth/register", json={
            "username": "logouttest",
            "email": "logout@example.com",
            "password": "SecureP@ss123"
        })

        login_response = test_client.post("/auth/login", json={
            "username": "logouttest",
            "password": "SecureP@ss123"
        })
        token = login_response.json()["access_token"]

        # Logout
        response = test_client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        assert "logged out" in response.json()["message"].lower()


class TestSentimentEndpoints:
    """Test sentiment analysis endpoints"""

    @pytest.mark.asyncio
    async def test_get_sentiment_backward_compat(self, test_client, mock_service_proxy):
        """Test backward compatibility sentiment endpoint"""
        mock_response = JSONResponse(content={
            "symbol": "BTCUSDT",
            "sentiment": "BULLISH"
        })
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/sentiment/BTCUSDT")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_aggregate_sentiment(self, test_client, mock_service_proxy):
        """Test aggregate market sentiment endpoint"""
        mock_response = JSONResponse(content={
            "overall_sentiment": "NEUTRAL",
            "symbols": []
        })
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/sentiment/aggregate")

        assert response.status_code == 200


class TestEnhancedSignalErrorHandling:
    """Test enhanced signal error scenarios"""

    @pytest.mark.asyncio
    async def test_enhanced_signal_exception_handling(self, test_client, mock_service_proxy):
        """Test enhanced signal handles exceptions"""
        # Make all services raise exceptions
        mock_service_proxy.proxy_request.side_effect = Exception("All services down")

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/trading/signals/enhanced/BTCUSDT")

        # Should still return 200 with partial data
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_enhanced_signal_malformed_json(self, test_client, mock_service_proxy):
        """Test enhanced signal handles malformed JSON responses"""
        # Return response with invalid body
        bad_response = Mock()
        bad_response.body = b"not json"

        mock_service_proxy.proxy_request.return_value = bad_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/trading/signals/enhanced/BTCUSDT")

        assert response.status_code == 200


class TestMLPredictionSignalDerivation:
    """Test ML signal derivation logic"""

    @pytest.mark.asyncio
    async def test_ml_signal_up_low_confidence(self, test_client, mock_service_proxy):
        """Test ML signal with UP but low confidence"""
        prediction_response = Mock()
        prediction_response.body = json.dumps({
            "predicted_direction": "UP",
            "directional_strength": 0.4  # Below 0.6 threshold
        }).encode()

        mock_service_proxy.proxy_request.return_value = prediction_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/ml/predict/signal/BTCUSDT")

        data = response.json()
        assert data["signal"] == "HOLD"  # Low confidence should give HOLD

    @pytest.mark.asyncio
    async def test_ml_signal_down_high_confidence(self, test_client, mock_service_proxy):
        """Test ML signal with DOWN and high confidence"""
        prediction_response = Mock()
        prediction_response.body = json.dumps({
            "predicted_direction": "DOWN",
            "directional_strength": 0.9
        }).encode()

        mock_service_proxy.proxy_request.return_value = prediction_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/ml/predict/signal/BTCUSDT")

        data = response.json()
        assert data["signal"] == "SELL"

    @pytest.mark.asyncio
    async def test_ml_signal_sideways(self, test_client, mock_service_proxy):
        """Test ML signal with SIDEWAYS direction"""
        prediction_response = Mock()
        prediction_response.body = json.dumps({
            "predicted_direction": "SIDEWAYS",
            "directional_strength": 0.8
        }).encode()

        mock_service_proxy.proxy_request.return_value = prediction_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/ml/predict/signal/BTCUSDT")

        data = response.json()
        assert data["signal"] == "HOLD"


class TestGetProxyDependency:
    """Test get_proxy dependency function"""

    @pytest.mark.asyncio
    async def test_get_proxy_when_initialized(self, test_client, mock_service_proxy):
        """Test get_proxy returns proxy when initialized"""
        with patch('app.main.service_proxy', mock_service_proxy):
            # Any endpoint that uses get_proxy
            mock_service_proxy.aggregate_health_checks = AsyncMock(return_value={
                "bybit": True,
                "market-data": True
            })

            response = test_client.get("/health")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_proxy_when_not_initialized(self, test_client):
        """Test get_proxy raises exception when not initialized"""
        with patch('app.main.service_proxy', None):
            response = test_client.get("/api/market/ticker/BTCUSDT")

            # Should return 503 Service Unavailable
            assert response.status_code == 503


class TestUncoveredEndpoints:
    """Test endpoints that weren't fully covered"""

    @pytest.mark.asyncio
    async def test_get_ticker_malformed_backend_response(self, test_client, mock_service_proxy):
        """Test ticker endpoint with malformed backend response"""
        # Return response without expected structure
        mock_response = Mock()
        mock_response.body = json.dumps({
            "unexpected": "structure"
        }).encode()

        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/market/ticker/BTCUSDT")

        # Should still return something
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dashboard_data_with_json_response(self, test_client, mock_service_proxy):
        """Test dashboard endpoint returns properly"""
        # Mock responses
        ticker_response = Mock()
        ticker_response.body = b'{"data": "ticker"}'

        signal_response = Mock()
        signal_response.body = b'{"signal": "BUY"}'

        portfolio_response = Mock()
        portfolio_response.body = b'{"balance": "100000"}'

        mock_service_proxy.proxy_request.side_effect = [
            ticker_response, signal_response, portfolio_response
        ]

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/dashboard/BTCUSDT")

        assert response.status_code == 200
        assert "data" in response.json()


class TestEnhancedSignalRiskLevels:
    """Test risk level determination in enhanced signals"""

    @pytest.mark.asyncio
    async def test_enhanced_signal_medium_risk(self, test_client, mock_service_proxy):
        """Test enhanced signal with medium risk level.

        Sentiment was removed from enhanced-signal aggregation in PR #86 — endpoint
        now fans out to 4 services (TA, ML, MTF, signal), so the smallest
        non-zero confidence is 1/4=0.25 and confidence values are quarters.
        2 BUY + 2 HOLD with 4 services → buy doesn't beat neutral → HOLD with
        confidence 2/4=0.5, which lands in the MEDIUM band (0.5..0.7).
        """
        responses = [
            Mock(body=json.dumps({"aggregated_signal": "BUY"}).encode()),
            Mock(body=json.dumps({"trend": "BULLISH"}).encode()),
            Mock(body=json.dumps({"consensus_signal": "HOLD"}).encode()),
            Mock(body=json.dumps({"signal": "HOLD"}).encode()),
        ]

        mock_service_proxy.proxy_request.side_effect = responses

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/trading/signals/enhanced/BTCUSDT")

        data = response.json()
        assert data["confidence"] == 0.5
        assert data["risk_level"] == "MEDIUM"

    @pytest.mark.asyncio
    async def test_enhanced_signal_high_risk(self, test_client, mock_service_proxy):
        """Test enhanced signal with high risk level.

        With 4 services and a tied 1-BUY/1-SELL/1-HOLD spread (the 4th
        response carries no recognised signal field so it doesn't enter the
        tally), the endpoint takes the HOLD fallback branch and reports
        confidence = neutral/total = 1/3 ≈ 0.33, which lands in HIGH.
        """
        responses = [
            Mock(body=json.dumps({"aggregated_signal": "BUY"}).encode()),
            Mock(body=json.dumps({"trend": "BEARISH"}).encode()),
            Mock(body=json.dumps({"consensus_signal": "HOLD"}).encode()),
            # No "signal" / "trend" / "consensus_signal" / "aggregated_signal"
            # field — endpoint skips this entry, so total_signals = 3.
            Mock(body=json.dumps({"unrelated": "field"}).encode()),
        ]

        mock_service_proxy.proxy_request.side_effect = responses

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/trading/signals/enhanced/BTCUSDT")

        data = response.json()
        # Very mixed signals = low confidence
        assert data["confidence"] < 0.5
        assert data["risk_level"] == "HIGH"
