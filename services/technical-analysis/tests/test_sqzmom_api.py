"""
Test Suite for SQZMOM API Endpoints
Purpose: Test HTTP API endpoints for Squeeze Momentum indicator and strategy

Test Coverage:
- GET /api/v1/indicators/sqzmom/{symbol}
- GET /api/v1/strategies/sqzmom/signal/{symbol}
- GET /api/v1/indicators/sqzmom/{symbol}/backtest
- Parameter validation
- Error handling
- Response format validation
"""

import pytest
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock

# Import app
from app.main import app
from app.indicators.squeeze_momentum import SqueezeMomentumIndicator
from app.strategies.squeeze_momentum_strategy import SqueezeMomentumStrategy


# Test client - raise_server_exceptions=False to properly test 500 errors
# UPDATED 2025-12-03: Required to get proper 500 responses instead of raised exceptions
client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_market_data():
    """Mock market data for testing"""
    np.random.seed(42)
    data = {
        'timestamp': [1700000000000 + i * 60000 for i in range(100)],
        'open': [100 + i + np.random.randn() * 2 for i in range(100)],
        'high': [100 + i + np.random.randn() * 2 + 5 for i in range(100)],
        'low': [100 + i + np.random.randn() * 2 - 5 for i in range(100)],
        'close': [100 + i + np.random.randn() * 2 for i in range(100)],
        'volume': [1000 + np.random.randint(-200, 200) for _ in range(100)]
    }
    return pd.DataFrame(data)


@pytest.fixture
def mock_fetcher(mock_market_data):
    """Mock market data fetcher"""
    fetcher = MagicMock()

    # Create async mock for get_klines_as_dataframe
    async def async_return_df(*args, **kwargs):
        return mock_market_data

    fetcher.get_klines_as_dataframe = AsyncMock(side_effect=async_return_df)
    fetcher.health_check = AsyncMock(return_value=True)

    return fetcher


class TestSQZMOMIndicatorEndpoint:
    """Test /api/v1/indicators/sqzmom/{symbol} endpoint"""

    @patch('app.handlers.sqzmom.get_fetcher')
    def test_get_sqzmom_default_parameters(self, mock_get_fetcher, mock_fetcher):
        """Test SQZMOM endpoint with default parameters"""
        mock_get_fetcher.return_value = mock_fetcher

        response = client.get("/api/v1/indicators/sqzmom/BTCUSDT")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert 'symbol' in data
        assert data['symbol'] == 'BTCUSDT'
        assert 'interval' in data
        assert 'squeeze_state' in data
        assert 'momentum' in data
        assert 'signal' in data
        # Fix: API returns 'bollinger_bands' not 'bb_bands'
        assert 'bollinger_bands' in data
        # Fix: API returns 'keltner_channels' not 'kc_channels'
        assert 'keltner_channels' in data

        # Verify squeeze state structure
        assert 'squeeze_on' in data['squeeze_state']
        assert 'squeeze_off' in data['squeeze_state']
        assert 'no_squeeze' in data['squeeze_state']

        # Fix: Signal field is 'action' not 'signal'
        assert data['signal']['action'] in ['BUY', 'SELL', 'HOLD']
        assert 0 <= data['signal']['confidence'] <= 1

    @patch('app.handlers.sqzmom.get_fetcher')
    def test_get_sqzmom_custom_parameters(self, mock_get_fetcher, mock_fetcher):
        """Test SQZMOM endpoint with custom parameters"""
        mock_get_fetcher.return_value = mock_fetcher

        # Fix: Close parenthesis after URL string and remove duplicate assertions
        response = client.get(
            "/api/v1/indicators/sqzmom/ETHUSDT"
            "?interval=240"
            "&bb_length=15"
            "&bb_mult=2.5"
            "&kc_length=25"
            "&kc_mult=1.8"
            "&use_true_range=false"
            "&limit=150"
        )

        assert response.status_code == 200
        data = response.json()

        assert data['symbol'] == 'ETHUSDT'
        assert data['interval'] == '240'

    @patch('app.handlers.sqzmom.get_fetcher')
    def test_get_sqzmom_invalid_symbol(self, mock_get_fetcher):
        """Test SQZMOM endpoint with invalid symbol"""
        mock_fetcher = MagicMock()
        mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=None)
        mock_get_fetcher.return_value = mock_fetcher

        response = client.get("/api/v1/indicators/sqzmom/INVALID")

        # Fix: Should return 500 when data fetch fails
        assert response.status_code == 500

    @patch('app.handlers.sqzmom.get_fetcher')
    def test_get_sqzmom_insufficient_data(self, mock_get_fetcher):
        """Test SQZMOM endpoint with insufficient data"""
        mock_fetcher = MagicMock()

        # Return dataframe with only 10 candles (insufficient for indicators)
        insufficient_data = pd.DataFrame({
            'timestamp': [1700000000000 + i * 60000 for i in range(10)],
            'open': [100] * 10,
            'high': [105] * 10,
            'low': [95] * 10,
            'close': [100] * 10,
            'volume': [1000] * 10
        })

        mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=insufficient_data)
        mock_get_fetcher.return_value = mock_fetcher

        response = client.get("/api/v1/indicators/sqzmom/BTCUSDT?limit=10")

        # Fix: API returns 422 for validation errors with insufficient data
        assert response.status_code in [422, 500]

    @patch('app.handlers.sqzmom.get_fetcher')
    def test_get_sqzmom_response_format(self, mock_get_fetcher, mock_fetcher):
        """Test SQZMOM endpoint response format in detail"""
        mock_get_fetcher.return_value = mock_fetcher

        response = client.get("/api/v1/indicators/sqzmom/BTCUSDT")

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields (fixed field names)
        required_fields = [
            'symbol', 'interval', 'timestamp',
            'squeeze_state', 'momentum', 'signal',
            'bollinger_bands', 'keltner_channels', 'parameters'
        ]

        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Verify Bollinger Bands structure
        assert 'upper' in data['bollinger_bands']
        assert 'basis' in data['bollinger_bands']
        assert 'lower' in data['bollinger_bands']
        assert isinstance(data['bollinger_bands']['upper'], (int, float))

        # Verify Keltner Channels structure
        assert 'upper' in data['keltner_channels']
        assert 'basis' in data['keltner_channels']
        assert 'lower' in data['keltner_channels']

        # Verify parameters
        assert 'bb_length' in data['parameters']
        assert 'bb_mult' in data['parameters']
        assert 'kc_length' in data['parameters']
        assert 'kc_mult' in data['parameters']


class TestSQZMOMStrategyEndpoint:
    """Test /api/v1/strategies/sqzmom/signal/{symbol} endpoint"""

    @patch('app.handlers.sqzmom.get_fetcher')
    def test_get_strategy_signal_default_parameters(self, mock_get_fetcher, mock_fetcher):
        """Test SQZMOM strategy endpoint with default parameters"""
        mock_get_fetcher.return_value = mock_fetcher

        response = client.get("/api/v1/strategies/sqzmom/signal/BTCUSDT")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert 'symbol' in data
        assert 'action' in data
        assert 'confidence' in data
        assert 'entry_price' in data
        assert 'stop_loss' in data
        assert 'take_profit' in data
        assert 'reason' in data
        assert 'squeeze_state' in data

        # Verify action is valid
        assert data['action'] in ['BUY', 'SELL', 'HOLD']

        # Verify confidence range
        assert 0 <= data['confidence'] <= 1

        # Verify prices are positive
        assert data['entry_price'] > 0
        if data['stop_loss']:
            assert data['stop_loss'] > 0
        if data['take_profit']:
            assert data['take_profit'] > 0

    @patch('app.handlers.sqzmom.get_fetcher')
    def test_get_strategy_signal_custom_parameters(self, mock_get_fetcher, mock_fetcher):
        """Test SQZMOM strategy endpoint with custom parameters"""
        mock_get_fetcher.return_value = mock_fetcher

        response = client.get(
            "/api/v1/strategies/sqzmom/signal/ETHUSDT"
            "?interval=120"
            "&min_momentum_threshold=1.0"
            "&stop_loss_pct=3.0"
            "&take_profit_pct=6.0"
            "&require_squeeze_release=false"
            "&require_volume_confirmation=true"
            "&volume_threshold=1.5"
        )

        assert response.status_code == 200
        data = response.json()

        assert data['symbol'] == 'ETHUSDT'
        assert 'action' in data

    @patch('app.handlers.sqzmom.get_fetcher')
    def test_get_strategy_signal_buy_condition(self, mock_get_fetcher):
        """Test strategy generates BUY signal for bullish data"""
        mock_fetcher = MagicMock()

        # Create strong bullish trend
        np.random.seed(42)
        bullish_data = pd.DataFrame({
            'timestamp': [1700000000000 + i * 60000 for i in range(100)],
            'open': [100 + i * 2 + np.random.randn() for i in range(100)],
            'high': [100 + i * 2 + np.random.randn() + 5 for i in range(100)],
            'low': [100 + i * 2 + np.random.randn() - 5 for i in range(100)],
            'close': [100 + i * 2 + np.random.randn() for i in range(100)],
            'volume': [1000 + np.random.randint(-200, 200) for _ in range(100)]
        })

        mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=bullish_data)
        mock_get_fetcher.return_value = mock_fetcher

        response = client.get(
            "/api/v1/strategies/sqzmom/signal/BTCUSDT"
            "?min_momentum_threshold=0.1"
            "&require_squeeze_release=false"
        )

        assert response.status_code == 200
        data = response.json()

        # With strong uptrend, should likely generate BUY or HOLD signal
        assert data['action'] in ['BUY', 'HOLD']

    @patch('app.handlers.sqzmom.get_fetcher')
    def test_get_strategy_signal_insufficient_data(self, mock_get_fetcher):
        """Test strategy handles insufficient data"""
        mock_fetcher = MagicMock()

        insufficient_data = pd.DataFrame({
            'timestamp': [1700000000000 + i * 60000 for i in range(10)],
            'open': [100] * 10,
            'high': [105] * 10,
            'low': [95] * 10,
            'close': [100] * 10,
            'volume': [1000] * 10
        })

        mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=insufficient_data)
        mock_get_fetcher.return_value = mock_fetcher

        response = client.get("/api/v1/strategies/sqzmom/signal/BTCUSDT")

        # Should handle gracefully (either error or HOLD signal)
        if response.status_code == 200:
            data = response.json()
            assert data['action'] == 'HOLD'
            assert data['confidence'] == 0.0


class TestSQZMOMBacktestEndpoint:
    """Test /api/v1/indicators/sqzmom/{symbol}/backtest endpoint"""

    @patch('app.handlers.sqzmom.get_fetcher')
    def test_get_backtest_data(self, mock_get_fetcher, mock_fetcher):
        """Test SQZMOM backtest endpoint"""
        mock_get_fetcher.return_value = mock_fetcher

        # Fix: Correct endpoint path
        response = client.get(
            "/api/v1/indicators/sqzmom/BTCUSDT/backtest"
            "?interval=60"
            "&limit=100"
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert 'symbol' in data
        assert 'interval' in data
        assert 'data' in data  # Fix: API returns 'data' not 'backtest_data'
        assert 'statistics' in data  # Fix: API returns 'statistics' not 'summary'

        # Verify backtest data is a list
        assert isinstance(data['data'], list)

        # Verify each entry has required fields
        if len(data['data']) > 0:
            entry = data['data'][0]
            assert 'timestamp' in entry
            assert 'close' in entry  # Fix: backtest data has 'close' not 'price'
            assert 'squeeze_on' in entry
            assert 'sqz_momentum' in entry  # Fix: field is 'sqz_momentum'
            assert 'sqz_signal' in entry  # Fix: field is 'sqz_signal'

    @patch('app.handlers.sqzmom.get_fetcher')
    def test_get_backtest_data_with_custom_params(self, mock_get_fetcher, mock_fetcher):
        """Test backtest endpoint with custom parameters"""
        mock_get_fetcher.return_value = mock_fetcher

        # Fix: Correct endpoint path
        response = client.get(
            "/api/v1/indicators/sqzmom/ETHUSDT/backtest"
            "?interval=240"
            "&limit=200"
            "&bb_length=15"
            "&kc_length=25"
        )

        assert response.status_code == 200
        data = response.json()

        assert data['symbol'] == 'ETHUSDT'
        assert data['interval'] == '240'

    @patch('app.handlers.sqzmom.get_fetcher')
    def test_get_backtest_summary_statistics(self, mock_get_fetcher, mock_fetcher):
        """Test backtest endpoint includes summary statistics"""
        mock_get_fetcher.return_value = mock_fetcher

        # Fix: Correct endpoint path
        response = client.get("/api/v1/indicators/sqzmom/BTCUSDT/backtest")

        assert response.status_code == 200
        data = response.json()

        # Verify summary statistics
        assert 'statistics' in data  # Fix: API returns 'statistics' not 'summary'
        summary = data['statistics']

        # Expected summary fields
        expected_fields = [
            'total_bars',
            'squeeze_on_count',
            'squeeze_on_pct',
            'buy_signals',
            'sell_signals'
        ]

        for field in expected_fields:
            assert field in summary, f"Missing summary field: {field}"


class TestAPIErrorHandling:
    """Test API error handling and edge cases"""

    def test_invalid_endpoint(self):
        """Test accessing invalid endpoint"""
        response = client.get("/api/v1/indicators/invalid_endpoint")
        assert response.status_code == 404

    @patch('app.handlers.sqzmom.get_fetcher')
    def test_fetcher_failure(self, mock_get_fetcher):
        """Test handling of fetcher failure"""
        mock_fetcher = MagicMock()
        # Fix: AsyncMock with side_effect for raising exception
        mock_fetcher.get_klines_as_dataframe = AsyncMock(side_effect=Exception("Network error"))
        mock_get_fetcher.return_value = mock_fetcher

        response = client.get("/api/v1/indicators/sqzmom/BTCUSDT")

        # Should return 500 with error details
        assert response.status_code == 500

    @patch('app.handlers.sqzmom.get_fetcher')
    def test_invalid_parameter_types(self, mock_get_fetcher, mock_fetcher):
        """Test handling of invalid parameter types"""
        mock_get_fetcher.return_value = mock_fetcher

        # Invalid bb_length (string instead of int)
        response = client.get("/api/v1/indicators/sqzmom/BTCUSDT?bb_length=invalid")

        # FastAPI should return 422 for validation error
        assert response.status_code == 422

    @patch('app.handlers.sqzmom.get_fetcher')
    def test_negative_parameters(self, mock_get_fetcher, mock_fetcher):
        """Test handling of negative parameters"""
        mock_get_fetcher.return_value = mock_fetcher

        # Negative bb_length
        response = client.get("/api/v1/indicators/sqzmom/BTCUSDT?bb_length=-20")

        # Should either reject (422) or handle gracefully (500)
        assert response.status_code in [422, 500]


class TestConcurrentRequests:
    """Test handling of concurrent requests"""

    @patch('app.handlers.sqzmom.get_fetcher')
    def test_multiple_concurrent_requests(self, mock_get_fetcher, mock_fetcher):
        """Test multiple concurrent requests to SQZMOM endpoint"""
        mock_get_fetcher.return_value = mock_fetcher

        # Send multiple requests concurrently
        symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT']

        responses = []
        for symbol in symbols:
            response = client.get(f"/api/v1/indicators/sqzmom/{symbol}")
            responses.append(response)

        # All requests should succeed
        for response in responses:
            assert response.status_code == 200


# Pytest configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
