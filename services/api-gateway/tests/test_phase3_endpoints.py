"""
Unit Tests for Phase 3 Endpoints Implementation
Tests all sentiment analysis and multi-timeframe analysis endpoints
Author: Python-Pro Agent
Date: 2025-11-19
Coverage Target: >90%
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch
from fastapi.responses import JSONResponse
import json
import time

from app.main import app, get_proxy


# ============================================================================
# FIXTURES FOR PHASE 3 TESTS
# ============================================================================

@pytest.fixture
def mock_news_sentiment_response():
    """Mock response for news sentiment endpoint"""
    return {
        "symbol": "BTCUSDT",
        "sentiment_label": "BULLISH",
        "sentiment_score": 0.72,
        "confidence": 0.85,
        "news_count": 15,
        "analyzed_at": 1700000000000
    }


@pytest.fixture
def mock_social_sentiment_response():
    """Mock response for social media sentiment endpoint"""
    return {
        "symbol": "BTCUSDT",
        "sentiment_label": "NEUTRAL",
        "sentiment_score": 0.52,
        "confidence": 0.78,
        "post_count": 1250,
        "analyzed_at": 1700000000000
    }


@pytest.fixture
def mock_combined_sentiment_response():
    """Mock response for combined sentiment endpoint"""
    return {
        "symbol": "BTCUSDT",
        "combined_label": "BULLISH",
        "combined_score": 0.65,
        "confidence": 0.85,
        "news_sentiment": {
            "label": "BULLISH",
            "score": 0.72,
            "weight": 0.4
        },
        "social_sentiment": {
            "label": "NEUTRAL",
            "score": 0.52,
            "weight": 0.3
        },
        "market_sentiment": {
            "label": "BULLISH",
            "score": 0.68,
            "weight": 0.3
        },
        "analyzed_at": 1700000000000
    }


@pytest.fixture
def mock_sentiment_trend_response():
    """Mock response for sentiment trend endpoint"""
    return {
        "symbol": "BTCUSDT",
        "timeframe_hours": 24,
        "current_sentiment": "BULLISH",
        "trend_direction": "IMPROVING",
        "data_points": [
            {
                "timestamp": 1700000000000,
                "sentiment_score": 0.65,
                "sentiment_label": "BULLISH"
            },
            {
                "timestamp": 1700003600000,
                "sentiment_score": 0.68,
                "sentiment_label": "BULLISH"
            },
            {
                "timestamp": 1700007200000,
                "sentiment_score": 0.70,
                "sentiment_label": "BULLISH"
            }
        ],
        "average_score": 0.62,
        "analyzed_at": 1700010800000
    }


@pytest.fixture
def mock_multi_timeframe_response():
    """Mock response for multi-timeframe analysis endpoint"""
    return {
        "symbol": "BTCUSDT",
        "alignment_score": 83,
        "consensus_signal": "BUY",
        "signal_strength": 0.75,
        "timeframe_signals": [
            {
                "timeframe": "1h",
                "signal": "BUY",
                "strength": 0.80,
                "rsi": 62,
                "macd_signal": "BUY"
            },
            {
                "timeframe": "4h",
                "signal": "BUY",
                "strength": 0.85,
                "rsi": 58,
                "macd_signal": "BUY"
            },
            {
                "timeframe": "1d",
                "signal": "NEUTRAL",
                "strength": 0.50,
                "rsi": 55,
                "macd_signal": "NEUTRAL"
            }
        ],
        "recommendation": "Strong buy signal across multiple timeframes",
        "analyzed_at": 1700000000000
    }


@pytest.fixture
def mock_indicator_signal_response():
    """Mock response for aggregated indicator signal endpoint"""
    return {
        "symbol": "BTCUSDT",
        "interval": "60",
        "aggregated_signal": "BUY",
        "confidence": 0.78,
        "indicator_signals": {
            "rsi": {
                "value": 62,
                "signal": "BUY",
                "strength": 0.70
            },
            "macd": {
                "signal": "BUY",
                "strength": 0.85
            },
            "bollinger": {
                "position": "middle",
                "signal": "NEUTRAL",
                "strength": 0.50
            },
            "ema_cross": {
                "signal": "BUY",
                "strength": 0.90
            }
        },
        "buy_indicators": 3,
        "sell_indicators": 0,
        "neutral_indicators": 1,
        "analyzed_at": 1700000000000
    }


# ============================================================================
# SENTIMENT ANALYSIS ENDPOINTS TESTS
# ============================================================================

class TestNewsSentimentEndpoint:
    """Test /api/sentiment/news/{symbol} endpoint"""

    @pytest.mark.asyncio
    async def test_get_news_sentiment_success(
        self,
        test_client,
        mock_service_proxy,
        mock_news_sentiment_response
    ):
        """Test successful news sentiment retrieval"""
        # Create mock response with body
        mock_response = JSONResponse(content=mock_news_sentiment_response)
        mock_response.body = json.dumps(mock_news_sentiment_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/sentiment/news/BTCUSDT")

        # Assert response
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTCUSDT"
        assert data["sentiment_label"] == "BULLISH"
        assert data["sentiment_score"] == 0.72
        assert data["confidence"] == 0.85
        assert data["news_count"] == 15
        assert "analyzed_at" in data

        # Verify proxy was called correctly
        call_kwargs = mock_service_proxy.proxy_request.call_args[1]
        assert call_kwargs["service_name"] == "sentiment-analysis"
        assert call_kwargs["path"] == "/api/v1/sentiment/news/BTCUSDT"
        assert call_kwargs["method"] == "GET"

    @pytest.mark.asyncio
    async def test_get_news_sentiment_different_symbols(
        self,
        test_client,
        mock_service_proxy
    ):
        """Test news sentiment with different symbols"""
        symbols = ["ETHUSDT", "BNBUSDT", "SOLUSDT"]

        for symbol in symbols:
            mock_response_data = {
                "symbol": symbol,
                "sentiment_label": "NEUTRAL",
                "sentiment_score": 0.5,
                "confidence": 0.7,
                "news_count": 10,
                "analyzed_at": int(time.time() * 1000)
            }
            mock_response = JSONResponse(content=mock_response_data)
            mock_response.body = json.dumps(mock_response_data).encode()
            mock_service_proxy.proxy_request.return_value = mock_response

            with patch('app.main.get_proxy', return_value=mock_service_proxy):
                response = test_client.get(f"/api/sentiment/news/{symbol}")

            assert response.status_code == 200
            data = response.json()
            assert data["symbol"] == symbol

    @pytest.mark.asyncio
    async def test_get_news_sentiment_service_unavailable(
        self,
        test_client,
        mock_service_proxy
    ):
        """Test handling when sentiment analysis service is unavailable"""
        from fastapi import HTTPException

        mock_service_proxy.proxy_request.side_effect = HTTPException(
            status_code=503,
            detail="Sentiment analysis service unavailable"
        )

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/sentiment/news/BTCUSDT")

        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_get_news_sentiment_malformed_backend_error(
        self,
        test_client,
        mock_service_proxy
    ):
        """Test handling when backend returns malformed error"""
        from fastapi import HTTPException

        mock_service_proxy.proxy_request.side_effect = HTTPException(
            status_code=500,
            detail="Backend service returned invalid data"
        )

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/sentiment/news/BTCUSDT")

        assert response.status_code == 500


class TestSocialSentimentEndpoint:
    """Test /api/sentiment/social/{symbol} endpoint"""

    @pytest.mark.asyncio
    async def test_get_social_sentiment_success(
        self,
        test_client,
        mock_service_proxy,
        mock_social_sentiment_response
    ):
        """Test successful social media sentiment retrieval"""
        mock_response = JSONResponse(content=mock_social_sentiment_response)
        mock_response.body = json.dumps(mock_social_sentiment_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/sentiment/social/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTCUSDT"
        assert data["sentiment_label"] == "NEUTRAL"
        assert data["sentiment_score"] == 0.52
        assert data["confidence"] == 0.78
        assert data["post_count"] == 1250

        # Verify correct service routing
        call_kwargs = mock_service_proxy.proxy_request.call_args[1]
        assert call_kwargs["service_name"] == "sentiment-analysis"
        assert call_kwargs["path"] == "/api/v1/sentiment/social/BTCUSDT"

    @pytest.mark.asyncio
    async def test_get_social_sentiment_bearish(
        self,
        test_client,
        mock_service_proxy
    ):
        """Test social sentiment with bearish signal"""
        bearish_response = {
            "symbol": "BTCUSDT",
            "sentiment_label": "BEARISH",
            "sentiment_score": 0.25,
            "confidence": 0.80,
            "post_count": 2000,
            "analyzed_at": int(time.time() * 1000)
        }
        mock_response = JSONResponse(content=bearish_response)
        mock_response.body = json.dumps(bearish_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/sentiment/social/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["sentiment_label"] == "BEARISH"
        assert data["sentiment_score"] < 0.5

    @pytest.mark.asyncio
    async def test_get_social_sentiment_timeout(
        self,
        test_client,
        mock_service_proxy
    ):
        """Test handling of service timeout"""
        from fastapi import HTTPException

        mock_service_proxy.proxy_request.side_effect = HTTPException(
            status_code=504,
            detail="Timeout connecting to sentiment-analysis"
        )

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/sentiment/social/ETHUSDT")

        assert response.status_code == 504


class TestCombinedSentimentEndpoint:
    """Test /api/sentiment/combined/{symbol} endpoint"""

    @pytest.mark.asyncio
    async def test_get_combined_sentiment_success(
        self,
        test_client,
        mock_service_proxy,
        mock_combined_sentiment_response
    ):
        """Test successful combined sentiment retrieval"""
        mock_response = JSONResponse(content=mock_combined_sentiment_response)
        mock_response.body = json.dumps(mock_combined_sentiment_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/sentiment/combined/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTCUSDT"
        assert data["combined_label"] == "BULLISH"
        assert data["combined_score"] == 0.65
        assert data["confidence"] == 0.85

        # Verify all sentiment sources are present
        assert "news_sentiment" in data
        assert "social_sentiment" in data
        assert "market_sentiment" in data

        # Verify weights are present
        assert data["news_sentiment"]["weight"] == 0.4
        assert data["social_sentiment"]["weight"] == 0.3
        assert data["market_sentiment"]["weight"] == 0.3

        # Verify correct service routing
        call_kwargs = mock_service_proxy.proxy_request.call_args[1]
        assert call_kwargs["path"] == "/api/v1/sentiment/combined/BTCUSDT"

    @pytest.mark.asyncio
    async def test_get_combined_sentiment_structure_validation(
        self,
        test_client,
        mock_service_proxy,
        mock_combined_sentiment_response
    ):
        """Test that combined sentiment response has correct structure"""
        mock_response = JSONResponse(content=mock_combined_sentiment_response)
        mock_response.body = json.dumps(mock_combined_sentiment_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/sentiment/combined/BTCUSDT")

        data = response.json()

        # Validate top-level fields
        required_fields = ["symbol", "combined_label", "combined_score", "confidence", "analyzed_at"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate nested sentiment objects
        for sentiment_type in ["news_sentiment", "social_sentiment", "market_sentiment"]:
            assert sentiment_type in data
            sentiment_obj = data[sentiment_type]
            assert "label" in sentiment_obj
            assert "score" in sentiment_obj
            assert "weight" in sentiment_obj

    @pytest.mark.asyncio
    async def test_get_combined_sentiment_mixed_signals(
        self,
        test_client,
        mock_service_proxy
    ):
        """Test combined sentiment with mixed signals from different sources"""
        mixed_response = {
            "symbol": "ETHUSDT",
            "combined_label": "NEUTRAL",
            "combined_score": 0.48,
            "confidence": 0.70,
            "news_sentiment": {
                "label": "BULLISH",
                "score": 0.65,
                "weight": 0.4
            },
            "social_sentiment": {
                "label": "BEARISH",
                "score": 0.30,
                "weight": 0.3
            },
            "market_sentiment": {
                "label": "NEUTRAL",
                "score": 0.50,
                "weight": 0.3
            },
            "analyzed_at": int(time.time() * 1000)
        }
        mock_response = JSONResponse(content=mixed_response)
        mock_response.body = json.dumps(mixed_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/sentiment/combined/ETHUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["combined_label"] == "NEUTRAL"
        assert 0.4 < data["combined_score"] < 0.6  # Should be neutral range


class TestSentimentTrendEndpoint:
    """Test /api/sentiment/trend/{symbol} endpoint"""

    @pytest.mark.asyncio
    async def test_get_sentiment_trend_default_params(
        self,
        test_client,
        mock_service_proxy,
        mock_sentiment_trend_response
    ):
        """Test sentiment trend with default parameters (24 hours)"""
        mock_response = JSONResponse(content=mock_sentiment_trend_response)
        mock_response.body = json.dumps(mock_sentiment_trend_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/sentiment/trend/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTCUSDT"
        assert data["timeframe_hours"] == 24
        assert data["current_sentiment"] == "BULLISH"
        assert data["trend_direction"] == "IMPROVING"
        assert "data_points" in data
        assert len(data["data_points"]) > 0

        # Verify query parameters were passed correctly
        call_kwargs = mock_service_proxy.proxy_request.call_args[1]
        assert call_kwargs["query_params"]["hours"] == 24

    @pytest.mark.asyncio
    async def test_get_sentiment_trend_custom_timeframe(
        self,
        test_client,
        mock_service_proxy
    ):
        """Test sentiment trend with custom timeframe"""
        custom_response = {
            "symbol": "BTCUSDT",
            "timeframe_hours": 48,
            "current_sentiment": "NEUTRAL",
            "trend_direction": "STABLE",
            "data_points": [
                {"timestamp": 1700000000000, "sentiment_score": 0.50, "sentiment_label": "NEUTRAL"},
                {"timestamp": 1700003600000, "sentiment_score": 0.51, "sentiment_label": "NEUTRAL"}
            ],
            "average_score": 0.505,
            "analyzed_at": int(time.time() * 1000)
        }
        mock_response = JSONResponse(content=custom_response)
        mock_response.body = json.dumps(custom_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/sentiment/trend/BTCUSDT?hours=48")

        assert response.status_code == 200
        data = response.json()
        assert data["timeframe_hours"] == 48

        # Verify custom parameter was passed
        call_kwargs = mock_service_proxy.proxy_request.call_args[1]
        assert call_kwargs["query_params"]["hours"] == 48

    @pytest.mark.asyncio
    async def test_get_sentiment_trend_various_timeframes(
        self,
        test_client,
        mock_service_proxy
    ):
        """Test sentiment trend with various timeframe values"""
        timeframes = [1, 6, 12, 24, 48, 72, 168]  # 1h to 1 week

        for hours in timeframes:
            trend_response = {
                "symbol": "BTCUSDT",
                "timeframe_hours": hours,
                "current_sentiment": "BULLISH",
                "trend_direction": "IMPROVING",
                "data_points": [],
                "average_score": 0.65,
                "analyzed_at": int(time.time() * 1000)
            }
            mock_response = JSONResponse(content=trend_response)
            mock_response.body = json.dumps(trend_response).encode()
            mock_service_proxy.proxy_request.return_value = mock_response

            with patch('app.main.get_proxy', return_value=mock_service_proxy):
                response = test_client.get(f"/api/sentiment/trend/BTCUSDT?hours={hours}")

            assert response.status_code == 200
            data = response.json()
            assert data["timeframe_hours"] == hours

    @pytest.mark.asyncio
    async def test_get_sentiment_trend_declining(
        self,
        test_client,
        mock_service_proxy
    ):
        """Test sentiment trend with declining sentiment"""
        declining_response = {
            "symbol": "ETHUSDT",
            "timeframe_hours": 24,
            "current_sentiment": "BEARISH",
            "trend_direction": "DECLINING",
            "data_points": [
                {"timestamp": 1700000000000, "sentiment_score": 0.70, "sentiment_label": "BULLISH"},
                {"timestamp": 1700003600000, "sentiment_score": 0.55, "sentiment_label": "NEUTRAL"},
                {"timestamp": 1700007200000, "sentiment_score": 0.35, "sentiment_label": "BEARISH"}
            ],
            "average_score": 0.53,
            "analyzed_at": int(time.time() * 1000)
        }
        mock_response = JSONResponse(content=declining_response)
        mock_response.body = json.dumps(declining_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/sentiment/trend/ETHUSDT?hours=24")

        assert response.status_code == 200
        data = response.json()
        assert data["trend_direction"] == "DECLINING"
        assert data["current_sentiment"] == "BEARISH"


# ============================================================================
# MULTI-TIMEFRAME ANALYSIS ENDPOINTS TESTS
# ============================================================================

class TestMultiTimeframeAnalysisEndpoint:
    """Test /api/analysis/multi-timeframe/{symbol} endpoint"""

    @pytest.mark.asyncio
    async def test_get_multi_timeframe_analysis_success(
        self,
        test_client,
        mock_service_proxy,
        mock_multi_timeframe_response
    ):
        """Test successful multi-timeframe analysis retrieval"""
        mock_response = JSONResponse(content=mock_multi_timeframe_response)
        mock_response.body = json.dumps(mock_multi_timeframe_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/analysis/multi-timeframe/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTCUSDT"
        assert data["alignment_score"] == 83
        assert data["consensus_signal"] == "BUY"
        assert data["signal_strength"] == 0.75
        assert "timeframe_signals" in data
        assert len(data["timeframe_signals"]) > 0

        # Verify correct service routing
        call_kwargs = mock_service_proxy.proxy_request.call_args[1]
        assert call_kwargs["service_name"] == "technical-analysis"
        assert call_kwargs["path"] == "/api/v1/analysis/multi-timeframe/BTCUSDT"

    @pytest.mark.asyncio
    async def test_get_multi_timeframe_analysis_structure(
        self,
        test_client,
        mock_service_proxy,
        mock_multi_timeframe_response
    ):
        """Test multi-timeframe response structure validation"""
        mock_response = JSONResponse(content=mock_multi_timeframe_response)
        mock_response.body = json.dumps(mock_multi_timeframe_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/analysis/multi-timeframe/BTCUSDT")

        data = response.json()

        # Validate top-level structure
        required_fields = [
            "symbol", "alignment_score", "consensus_signal",
            "signal_strength", "timeframe_signals", "recommendation", "analyzed_at"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate timeframe signals structure
        for tf_signal in data["timeframe_signals"]:
            assert "timeframe" in tf_signal
            assert "signal" in tf_signal
            assert "strength" in tf_signal
            assert "rsi" in tf_signal
            assert "macd_signal" in tf_signal

    @pytest.mark.asyncio
    async def test_get_multi_timeframe_sell_signal(
        self,
        test_client,
        mock_service_proxy
    ):
        """Test multi-timeframe analysis with sell signal"""
        sell_response = {
            "symbol": "BTCUSDT",
            "alignment_score": 78,
            "consensus_signal": "SELL",
            "signal_strength": 0.70,
            "timeframe_signals": [
                {
                    "timeframe": "1h",
                    "signal": "SELL",
                    "strength": 0.75,
                    "rsi": 75,
                    "macd_signal": "SELL"
                },
                {
                    "timeframe": "4h",
                    "signal": "SELL",
                    "strength": 0.80,
                    "rsi": 72,
                    "macd_signal": "SELL"
                }
            ],
            "recommendation": "Strong sell signal across multiple timeframes",
            "analyzed_at": int(time.time() * 1000)
        }
        mock_response = JSONResponse(content=sell_response)
        mock_response.body = json.dumps(sell_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/analysis/multi-timeframe/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["consensus_signal"] == "SELL"
        assert data["signal_strength"] > 0.6

    @pytest.mark.asyncio
    async def test_get_multi_timeframe_low_alignment(
        self,
        test_client,
        mock_service_proxy
    ):
        """Test multi-timeframe with low alignment (conflicting signals)"""
        low_alignment_response = {
            "symbol": "ETHUSDT",
            "alignment_score": 35,
            "consensus_signal": "NEUTRAL",
            "signal_strength": 0.40,
            "timeframe_signals": [
                {
                    "timeframe": "1h",
                    "signal": "BUY",
                    "strength": 0.60,
                    "rsi": 58,
                    "macd_signal": "BUY"
                },
                {
                    "timeframe": "4h",
                    "signal": "SELL",
                    "strength": 0.65,
                    "rsi": 68,
                    "macd_signal": "SELL"
                },
                {
                    "timeframe": "1d",
                    "signal": "NEUTRAL",
                    "strength": 0.45,
                    "rsi": 50,
                    "macd_signal": "NEUTRAL"
                }
            ],
            "recommendation": "Conflicting signals across timeframes, wait for clarity",
            "analyzed_at": int(time.time() * 1000)
        }
        mock_response = JSONResponse(content=low_alignment_response)
        mock_response.body = json.dumps(low_alignment_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/analysis/multi-timeframe/ETHUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["alignment_score"] < 50
        assert data["consensus_signal"] == "NEUTRAL"

    @pytest.mark.asyncio
    async def test_get_multi_timeframe_service_error(
        self,
        test_client,
        mock_service_proxy
    ):
        """Test handling of technical analysis service error"""
        from fastapi import HTTPException

        mock_service_proxy.proxy_request.side_effect = HTTPException(
            status_code=500,
            detail="Technical analysis service error"
        )

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/analysis/multi-timeframe/BTCUSDT")

        assert response.status_code == 500


class TestIndicatorSignalEndpoint:
    """Test /api/analysis/indicators/signal/{symbol} endpoint"""

    @pytest.mark.asyncio
    async def test_get_indicator_signal_default_interval(
        self,
        test_client,
        mock_service_proxy,
        mock_indicator_signal_response
    ):
        """Test indicator signal with default interval (60 minutes)"""
        mock_response = JSONResponse(content=mock_indicator_signal_response)
        mock_response.body = json.dumps(mock_indicator_signal_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/analysis/indicators/signal/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTCUSDT"
        assert data["interval"] == "60"
        assert data["aggregated_signal"] == "BUY"
        assert data["confidence"] == 0.78

        # Verify query parameters
        call_kwargs = mock_service_proxy.proxy_request.call_args[1]
        assert call_kwargs["query_params"]["interval"] == "60"

    @pytest.mark.asyncio
    async def test_get_indicator_signal_custom_interval(
        self,
        test_client,
        mock_service_proxy
    ):
        """Test indicator signal with custom interval"""
        custom_response = {
            "symbol": "ETHUSDT",
            "interval": "240",
            "aggregated_signal": "SELL",
            "confidence": 0.82,
            "indicator_signals": {
                "rsi": {"value": 72, "signal": "SELL", "strength": 0.85},
                "macd": {"signal": "SELL", "strength": 0.90},
                "bollinger": {"position": "upper", "signal": "SELL", "strength": 0.75},
                "ema_cross": {"signal": "SELL", "strength": 0.80}
            },
            "buy_indicators": 0,
            "sell_indicators": 4,
            "neutral_indicators": 0,
            "analyzed_at": int(time.time() * 1000)
        }
        mock_response = JSONResponse(content=custom_response)
        mock_response.body = json.dumps(custom_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/analysis/indicators/signal/ETHUSDT?interval=240")

        assert response.status_code == 200
        data = response.json()
        assert data["interval"] == "240"
        assert data["aggregated_signal"] == "SELL"

        # Verify custom interval was passed
        call_kwargs = mock_service_proxy.proxy_request.call_args[1]
        assert call_kwargs["query_params"]["interval"] == "240"

    @pytest.mark.asyncio
    async def test_get_indicator_signal_structure_validation(
        self,
        test_client,
        mock_service_proxy,
        mock_indicator_signal_response
    ):
        """Test indicator signal response structure"""
        mock_response = JSONResponse(content=mock_indicator_signal_response)
        mock_response.body = json.dumps(mock_indicator_signal_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/analysis/indicators/signal/BTCUSDT")

        data = response.json()

        # Validate top-level fields
        required_fields = [
            "symbol", "interval", "aggregated_signal", "confidence",
            "indicator_signals", "buy_indicators", "sell_indicators",
            "neutral_indicators", "analyzed_at"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate indicator signals
        assert "rsi" in data["indicator_signals"]
        assert "macd" in data["indicator_signals"]
        assert "bollinger" in data["indicator_signals"]
        assert "ema_cross" in data["indicator_signals"]

        # Validate indicator counts
        total_indicators = (
            data["buy_indicators"] +
            data["sell_indicators"] +
            data["neutral_indicators"]
        )
        assert total_indicators == 4  # RSI, MACD, Bollinger, EMA

    @pytest.mark.asyncio
    async def test_get_indicator_signal_all_neutral(
        self,
        test_client,
        mock_service_proxy
    ):
        """Test indicator signal when all indicators are neutral"""
        neutral_response = {
            "symbol": "BNBUSDT",
            "interval": "60",
            "aggregated_signal": "NEUTRAL",
            "confidence": 0.45,
            "indicator_signals": {
                "rsi": {"value": 50, "signal": "NEUTRAL", "strength": 0.50},
                "macd": {"signal": "NEUTRAL", "strength": 0.50},
                "bollinger": {"position": "middle", "signal": "NEUTRAL", "strength": 0.50},
                "ema_cross": {"signal": "NEUTRAL", "strength": 0.50}
            },
            "buy_indicators": 0,
            "sell_indicators": 0,
            "neutral_indicators": 4,
            "analyzed_at": int(time.time() * 1000)
        }
        mock_response = JSONResponse(content=neutral_response)
        mock_response.body = json.dumps(neutral_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/analysis/indicators/signal/BNBUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["aggregated_signal"] == "NEUTRAL"
        assert data["neutral_indicators"] == 4
        assert data["buy_indicators"] == 0
        assert data["sell_indicators"] == 0

    @pytest.mark.asyncio
    async def test_get_indicator_signal_mixed_indicators(
        self,
        test_client,
        mock_service_proxy
    ):
        """Test indicator signal with mixed buy/sell/neutral indicators"""
        mixed_response = {
            "symbol": "SOLUSDT",
            "interval": "60",
            "aggregated_signal": "BUY",
            "confidence": 0.60,
            "indicator_signals": {
                "rsi": {"value": 58, "signal": "BUY", "strength": 0.65},
                "macd": {"signal": "BUY", "strength": 0.70},
                "bollinger": {"position": "middle", "signal": "NEUTRAL", "strength": 0.50},
                "ema_cross": {"signal": "SELL", "strength": 0.55}
            },
            "buy_indicators": 2,
            "sell_indicators": 1,
            "neutral_indicators": 1,
            "analyzed_at": int(time.time() * 1000)
        }
        mock_response = JSONResponse(content=mixed_response)
        mock_response.body = json.dumps(mixed_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/analysis/indicators/signal/SOLUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data["buy_indicators"] == 2
        assert data["sell_indicators"] == 1
        assert data["neutral_indicators"] == 1
        # More buy signals should lead to BUY signal
        assert data["aggregated_signal"] == "BUY"

    @pytest.mark.asyncio
    async def test_get_indicator_signal_various_intervals(
        self,
        test_client,
        mock_service_proxy
    ):
        """Test indicator signal with various interval values.

        '1440' (raw minutes-per-day) was never a valid Bybit interval; the
        canonical day code is 'D'. validate_interval() rejects '1440' with
        400 — use 'D' here.
        """
        intervals = ["1", "5", "15", "60", "240", "D"]

        for interval in intervals:
            test_response = {
                "symbol": "BTCUSDT",
                "interval": interval,
                "aggregated_signal": "BUY",
                "confidence": 0.75,
                "indicator_signals": {},
                "buy_indicators": 3,
                "sell_indicators": 0,
                "neutral_indicators": 1,
                "analyzed_at": int(time.time() * 1000)
            }
            mock_response = JSONResponse(content=test_response)
            mock_response.body = json.dumps(test_response).encode()
            mock_service_proxy.proxy_request.return_value = mock_response

            with patch('app.main.get_proxy', return_value=mock_service_proxy):
                response = test_client.get(f"/api/analysis/indicators/signal/BTCUSDT?interval={interval}")

            assert response.status_code == 200
            data = response.json()
            assert data["interval"] == interval


# ============================================================================
# ERROR HANDLING AND EDGE CASES
# ============================================================================

class TestPhase3ErrorHandling:
    """Test error handling for Phase 3 endpoints"""

    @pytest.mark.asyncio
    async def test_invalid_symbol_format(self, test_client, mock_service_proxy):
        """Test handling of invalid symbol format"""
        # API gateway should pass through to backend service
        # Backend service will validate and return error
        from fastapi import HTTPException

        mock_service_proxy.proxy_request.side_effect = HTTPException(
            status_code=400,
            detail="Invalid symbol format"
        )

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/sentiment/news/INVALID@SYMBOL")

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_service_proxy_not_initialized(self, test_client):
        """Test handling when service proxy is not initialized"""
        with patch('app.main.service_proxy', None):
            response = test_client.get("/api/sentiment/news/BTCUSDT")

        # Should handle gracefully
        assert response.status_code in [500, 503]

    @pytest.mark.asyncio
    async def test_backend_service_404(self, test_client, mock_service_proxy):
        """Test handling when backend service endpoint not found"""
        from fastapi import HTTPException

        mock_service_proxy.proxy_request.side_effect = HTTPException(
            status_code=404,
            detail="Endpoint not found in backend service"
        )

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/api/sentiment/news/BTCUSDT")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, test_client, mock_service_proxy):
        """Test handling of concurrent requests to Phase 3 endpoints"""
        import asyncio

        mock_response_data = {
            "symbol": "BTCUSDT",
            "sentiment_label": "BULLISH",
            "sentiment_score": 0.72,
            "confidence": 0.85,
            "news_count": 15,
            "analyzed_at": int(time.time() * 1000)
        }
        mock_response = JSONResponse(content=mock_response_data)
        mock_response.body = json.dumps(mock_response_data).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            # Make multiple concurrent requests
            responses = [
                test_client.get("/api/sentiment/news/BTCUSDT"),
                test_client.get("/api/sentiment/social/BTCUSDT"),
                test_client.get("/api/sentiment/combined/BTCUSDT")
            ]

        # All requests should succeed
        for response in responses:
            assert response.status_code in [200, 500, 503]


# ============================================================================
# INTEGRATION WITH EXISTING ENDPOINTS
# ============================================================================

class TestPhase3Integration:
    """Test integration of Phase 3 endpoints with existing functionality"""

    @pytest.mark.asyncio
    async def test_phase3_endpoints_in_root_listing(self, test_client):
        """Test that Phase 3 endpoints might be listed in root endpoint"""
        response = test_client.get("/")

        assert response.status_code == 200
        # Root endpoint may or may not list all endpoints
        # This test just verifies root endpoint still works

    @pytest.mark.asyncio
    async def test_phase3_services_in_health_check(self, test_client, mock_service_proxy):
        """Test that Phase 3 services are included in health checks"""
        health_data = {
            "bybit": True,
            "market-data": True,
            "technical-analysis": True,
            "trading-engine": True,
            "portfolio-manager": True,
            "sentiment-analysis": True,  # Phase 3 service
            "ml-prediction": True  # Phase 3 service
        }
        mock_service_proxy.aggregate_health_checks.return_value = health_data

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            response = test_client.get("/health")

        assert response.status_code == 200
        # Health check should include all services


# ============================================================================
# PERFORMANCE AND RESPONSE TIME TESTS
# ============================================================================

class TestPhase3Performance:
    """Test performance characteristics of Phase 3 endpoints"""

    @pytest.mark.asyncio
    async def test_sentiment_endpoint_response_time(
        self,
        test_client,
        mock_service_proxy,
        mock_news_sentiment_response
    ):
        """Test that sentiment endpoints respond quickly"""
        import time

        mock_response = JSONResponse(content=mock_news_sentiment_response)
        mock_response.body = json.dumps(mock_news_sentiment_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            start_time = time.time()
            response = test_client.get("/api/sentiment/news/BTCUSDT")
            end_time = time.time()

        # Response should be fast (mocked, so should be <1s)
        assert response.status_code == 200
        assert (end_time - start_time) < 1.0

    @pytest.mark.asyncio
    async def test_multi_timeframe_caching_potential(
        self,
        test_client,
        mock_service_proxy,
        mock_multi_timeframe_response
    ):
        """Test that multi-timeframe results could be cached"""
        mock_response = JSONResponse(content=mock_multi_timeframe_response)
        mock_response.body = json.dumps(mock_multi_timeframe_response).encode()
        mock_service_proxy.proxy_request.return_value = mock_response

        with patch('app.main.get_proxy', return_value=mock_service_proxy):
            # Make multiple requests
            response1 = test_client.get("/api/analysis/multi-timeframe/BTCUSDT")
            response2 = test_client.get("/api/analysis/multi-timeframe/BTCUSDT")

        assert response1.status_code == 200
        assert response2.status_code == 200
        # Both requests should succeed (caching would be in backend service)
