"""
Integration Tests for Data Collection Endpoint Handlers
Tests for app/handlers/collection.py
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi import HTTPException, Request

from app.handlers.collection import (
    collect_kline_data,
    collect_ticker_data,
    collect_bulk_data,
    get_fetcher
)


class TestCollectKlineData:
    """Integration tests for collect_kline_data handler"""

    @pytest.fixture
    def mock_fetcher(self):
        """Create mock fetcher with successful response"""
        fetcher = Mock()
        fetcher.get_historical_klines = AsyncMock(return_value=[
            {"timestamp": 1700000000000, "open": 50000, "high": 51000, "low": 49000, "close": 50500, "volume": 100},
            {"timestamp": 1700003600000, "open": 50500, "high": 51500, "low": 50000, "close": 51000, "volume": 150},
        ])
        return fetcher

    @pytest.fixture
    def mock_api_key(self):
        """Mock API key validation"""
        return "test_api_key"

    @pytest.mark.asyncio
    @patch('app.handlers.collection.KlineRepository')
    async def test_collect_kline_valid_symbol(self, mock_repo, mock_fetcher, mock_api_key):
        """Test collecting kline data with valid symbol"""
        mock_repo.bulk_upsert = AsyncMock(return_value=2)

        result = await collect_kline_data(
            symbol="BTCUSDT",
            interval="60",
            days=7,
            fetcher=mock_fetcher,
            api_key=mock_api_key
        )

        assert result["success"] is True
        assert result["symbol"] == "BTCUSDT"
        assert result["interval"] == "60"
        assert result["count"] == 2
        assert "Collected and stored 2 klines" in result["message"]

    @pytest.mark.asyncio
    @patch('app.handlers.collection.KlineRepository')
    async def test_collect_kline_uppercase_symbol(self, mock_repo, mock_fetcher, mock_api_key):
        """Test that symbol is converted to uppercase"""
        mock_repo.bulk_upsert = AsyncMock(return_value=2)

        result = await collect_kline_data(
            symbol="btcusdt",
            interval="60",
            days=7,
            fetcher=mock_fetcher,
            api_key=mock_api_key
        )

        assert result["symbol"] == "BTCUSDT"
        mock_fetcher.get_historical_klines.assert_called_once_with(
            symbol="BTCUSDT",
            interval="60",
            days=7
        )

    @pytest.mark.asyncio
    async def test_collect_kline_invalid_symbol_too_short(self, mock_fetcher, mock_api_key):
        """Test that short symbol raises 400 error"""
        with pytest.raises(HTTPException) as exc_info:
            await collect_kline_data(
                symbol="BTC",
                interval="60",
                days=7,
                fetcher=mock_fetcher,
                api_key=mock_api_key
            )

        assert exc_info.value.status_code == 400
        assert "Invalid symbol format" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_collect_kline_invalid_symbol_with_numbers(self, mock_fetcher, mock_api_key):
        """Test that symbol with numbers raises 400 error"""
        with pytest.raises(HTTPException) as exc_info:
            await collect_kline_data(
                symbol="BTC123",
                interval="60",
                days=7,
                fetcher=mock_fetcher,
                api_key=mock_api_key
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_collect_kline_no_data_fetched(self, mock_api_key):
        """Test handling when no data is fetched"""
        fetcher = Mock()
        fetcher.get_historical_klines = AsyncMock(return_value=[])

        result = await collect_kline_data(
            symbol="BTCUSDT",
            interval="60",
            days=7,
            fetcher=fetcher,
            api_key=mock_api_key
        )

        assert result["success"] is False
        assert result["message"] == "No data fetched"
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_collect_kline_no_data_none_response(self, mock_api_key):
        """Test handling when fetcher returns None"""
        fetcher = Mock()
        fetcher.get_historical_klines = AsyncMock(return_value=None)

        result = await collect_kline_data(
            symbol="BTCUSDT",
            interval="60",
            days=7,
            fetcher=fetcher,
            api_key=mock_api_key
        )

        assert result["success"] is False
        assert result["count"] == 0

    @pytest.mark.asyncio
    @patch('app.handlers.collection.KlineRepository')
    async def test_collect_kline_adds_metadata_to_klines(self, mock_repo, mock_api_key):
        """Test that symbol and interval are added to each kline"""
        fetcher = Mock()
        klines = [
            {"timestamp": 1700000000000, "open": 50000, "close": 50500},
            {"timestamp": 1700003600000, "open": 50500, "close": 51000},
        ]
        fetcher.get_historical_klines = AsyncMock(return_value=klines)
        mock_repo.bulk_upsert = AsyncMock(return_value=2)

        await collect_kline_data(
            symbol="ETHUSDT",
            interval="240",
            days=7,
            fetcher=fetcher,
            api_key=mock_api_key
        )

        # Verify metadata was added
        assert klines[0]["symbol"] == "ETHUSDT"
        assert klines[0]["interval"] == "240"
        assert klines[1]["symbol"] == "ETHUSDT"
        assert klines[1]["interval"] == "240"

    @pytest.mark.asyncio
    @patch('app.handlers.collection.KlineRepository')
    async def test_collect_kline_calls_repository_bulk_upsert(self, mock_repo, mock_fetcher, mock_api_key):
        """Test that repository bulk_upsert is called"""
        mock_repo.bulk_upsert = AsyncMock(return_value=2)

        await collect_kline_data(
            symbol="BTCUSDT",
            interval="60",
            days=7,
            fetcher=mock_fetcher,
            api_key=mock_api_key
        )

        mock_repo.bulk_upsert.assert_called_once()
        call_args = mock_repo.bulk_upsert.call_args[0][0]
        assert len(call_args) == 2
        assert all(k["symbol"] == "BTCUSDT" for k in call_args)

    @pytest.mark.asyncio
    @patch('app.handlers.collection.KlineRepository')
    async def test_collect_kline_fetcher_exception_raises_500(self, mock_repo, mock_api_key):
        """Test that fetcher exception raises 500 error"""
        fetcher = Mock()
        fetcher.get_historical_klines = AsyncMock(side_effect=Exception("Connection error"))

        with pytest.raises(HTTPException) as exc_info:
            await collect_kline_data(
                symbol="BTCUSDT",
                interval="60",
                days=7,
                fetcher=fetcher,
                api_key=mock_api_key
            )

        assert exc_info.value.status_code == 500
        assert "Failed to collect data" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch('app.handlers.collection.KlineRepository')
    async def test_collect_kline_repository_exception_raises_500(self, mock_repo, mock_fetcher, mock_api_key):
        """Test that repository exception raises 500 error"""
        mock_repo.bulk_upsert = AsyncMock(side_effect=Exception("Database error"))

        with pytest.raises(HTTPException) as exc_info:
            await collect_kline_data(
                symbol="BTCUSDT",
                interval="60",
                days=7,
                fetcher=mock_fetcher,
                api_key=mock_api_key
            )

        assert exc_info.value.status_code == 500


class TestCollectTickerData:
    """Integration tests for collect_ticker_data handler"""

    @pytest.fixture
    def mock_fetcher(self):
        """Create mock fetcher with ticker response"""
        fetcher = Mock()
        fetcher.get_ticker = AsyncMock(return_value={
            "symbol": "BTCUSDT",
            "lastPrice": "50000.5",
            "volume24h": "12345.67",
            "highPrice24h": "51000",
            "lowPrice24h": "49000"
        })
        return fetcher

    @pytest.fixture
    def mock_api_key(self):
        """Mock API key validation"""
        return "test_api_key"

    @pytest.mark.asyncio
    @patch('app.handlers.collection.TickerRepository')
    async def test_collect_ticker_valid_symbol(self, mock_repo, mock_fetcher, mock_api_key):
        """Test collecting ticker data with valid symbol"""
        mock_repo.save_ticker = AsyncMock()

        result = await collect_ticker_data(
            symbol="BTCUSDT",
            fetcher=mock_fetcher,
            api_key=mock_api_key
        )

        assert result["success"] is True
        assert result["message"] == "Ticker data saved"
        assert result["data"]["symbol"] == "BTCUSDT"
        assert "lastPrice" in result["data"]

    @pytest.mark.asyncio
    @patch('app.handlers.collection.TickerRepository')
    async def test_collect_ticker_uppercase_symbol(self, mock_repo, mock_fetcher, mock_api_key):
        """Test that symbol is converted to uppercase"""
        mock_repo.save_ticker = AsyncMock()

        result = await collect_ticker_data(
            symbol="ethusdt",
            fetcher=mock_fetcher,
            api_key=mock_api_key
        )

        mock_fetcher.get_ticker.assert_called_once_with("ETHUSDT")

    @pytest.mark.asyncio
    async def test_collect_ticker_invalid_symbol(self, mock_fetcher, mock_api_key):
        """Test that invalid symbol raises 400 error"""
        with pytest.raises(HTTPException) as exc_info:
            await collect_ticker_data(
                symbol="BTC",
                fetcher=mock_fetcher,
                api_key=mock_api_key
            )

        assert exc_info.value.status_code == 400
        assert "Invalid symbol format" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_collect_ticker_no_data(self, mock_api_key):
        """Test handling when no ticker data is available"""
        fetcher = Mock()
        fetcher.get_ticker = AsyncMock(return_value=None)

        result = await collect_ticker_data(
            symbol="BTCUSDT",
            fetcher=fetcher,
            api_key=mock_api_key
        )

        assert result["success"] is False
        assert result["message"] == "No ticker data available"

    @pytest.mark.asyncio
    async def test_collect_ticker_empty_dict(self, mock_api_key):
        """Test handling when empty dict is returned"""
        fetcher = Mock()
        fetcher.get_ticker = AsyncMock(return_value={})

        result = await collect_ticker_data(
            symbol="BTCUSDT",
            fetcher=fetcher,
            api_key=mock_api_key
        )

        assert result["success"] is False

    @pytest.mark.asyncio
    @patch('app.handlers.collection.TickerRepository')
    async def test_collect_ticker_calls_repository(self, mock_repo, mock_fetcher, mock_api_key):
        """Test that repository save_ticker is called"""
        mock_repo.save_ticker = AsyncMock()

        await collect_ticker_data(
            symbol="BTCUSDT",
            fetcher=mock_fetcher,
            api_key=mock_api_key
        )

        mock_repo.save_ticker.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.handlers.collection.TickerRepository')
    async def test_collect_ticker_fetcher_exception(self, mock_repo, mock_api_key):
        """Test that fetcher exception raises 500 error"""
        fetcher = Mock()
        fetcher.get_ticker = AsyncMock(side_effect=Exception("API error"))

        with pytest.raises(HTTPException) as exc_info:
            await collect_ticker_data(
                symbol="BTCUSDT",
                fetcher=fetcher,
                api_key=mock_api_key
            )

        assert exc_info.value.status_code == 500
        assert "Failed to collect ticker" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch('app.handlers.collection.TickerRepository')
    async def test_collect_ticker_repository_exception(self, mock_repo, mock_fetcher, mock_api_key):
        """Test that repository exception raises 500 error"""
        mock_repo.save_ticker = AsyncMock(side_effect=Exception("Database error"))

        with pytest.raises(HTTPException) as exc_info:
            await collect_ticker_data(
                symbol="BTCUSDT",
                fetcher=mock_fetcher,
                api_key=mock_api_key
            )

        assert exc_info.value.status_code == 500


class TestCollectBulkData:
    """Integration tests for collect_bulk_data handler"""

    @pytest.fixture
    def mock_fetcher(self):
        """Create mock fetcher for bulk collection"""
        fetcher = Mock()
        fetcher.get_historical_klines = AsyncMock(return_value=[
            {"timestamp": 1700000000000, "open": 50000, "close": 50500},
        ])
        return fetcher

    @pytest.fixture
    def mock_api_key(self):
        """Mock API key validation"""
        return "test_api_key"

    @pytest.mark.asyncio
    @patch('app.handlers.collection.get_settings')
    @patch('app.handlers.collection.KlineRepository')
    async def test_collect_bulk_with_default_symbols(self, mock_repo, mock_settings, mock_fetcher, mock_api_key):
        """Test bulk collection with default symbols from settings"""
        mock_settings.return_value.symbols_list = ["BTCUSDT", "ETHUSDT"]
        mock_repo.bulk_upsert = AsyncMock(return_value=1)

        result = await collect_bulk_data(
            symbols=None,
            interval="60",
            days=7,
            fetcher=mock_fetcher,
            api_key=mock_api_key
        )

        assert result["success"] is True
        assert result["total_symbols"] == 2
        assert result["successful"] == 2
        assert result["failed"] == 0

    @pytest.mark.asyncio
    @patch('app.handlers.collection.KlineRepository')
    async def test_collect_bulk_with_provided_symbols(self, mock_repo, mock_fetcher, mock_api_key):
        """Test bulk collection with provided symbols"""
        mock_repo.bulk_upsert = AsyncMock(return_value=1)

        result = await collect_bulk_data(
            symbols=["BTCUSDT", "ETHUSDT", "BNBUSDT"],
            interval="60",
            days=7,
            fetcher=mock_fetcher,
            api_key=mock_api_key
        )

        assert result["total_symbols"] == 3
        assert result["successful"] == 3
        assert len(result["results"]) == 3

    @pytest.mark.asyncio
    async def test_collect_bulk_too_many_symbols(self, mock_fetcher, mock_api_key):
        """Test that more than 10 symbols raises 400 error"""
        symbols = [f"SYMBOL{i:02d}USDT" for i in range(11)]

        with pytest.raises(HTTPException) as exc_info:
            await collect_bulk_data(
                symbols=symbols,
                interval="60",
                days=7,
                fetcher=mock_fetcher,
                api_key=mock_api_key
            )

        assert exc_info.value.status_code == 400
        assert "Maximum 10 symbols allowed" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch('app.handlers.collection.KlineRepository')
    async def test_collect_bulk_exactly_10_symbols(self, mock_repo, mock_fetcher, mock_api_key):
        """Test that exactly 10 symbols is allowed"""
        mock_repo.bulk_upsert = AsyncMock(return_value=1)
        symbols = [f"SYMBOL{i:02d}USDT" for i in range(10)]

        result = await collect_bulk_data(
            symbols=symbols,
            interval="60",
            days=7,
            fetcher=mock_fetcher,
            api_key=mock_api_key
        )

        assert result["total_symbols"] == 10
        assert result["success"] is True

    @pytest.mark.asyncio
    @patch('app.handlers.collection.KlineRepository')
    async def test_collect_bulk_partial_failures(self, mock_repo, mock_api_key):
        """Test bulk collection with some symbols failing"""
        fetcher = Mock()

        # First call succeeds, second fails, third succeeds
        fetcher.get_historical_klines = AsyncMock(side_effect=[
            [{"timestamp": 1700000000000, "open": 50000}],
            Exception("API error"),
            [{"timestamp": 1700000000000, "open": 30000}],
        ])

        mock_repo.bulk_upsert = AsyncMock(return_value=1)

        result = await collect_bulk_data(
            symbols=["BTCUSDT", "ETHUSDT", "BNBUSDT"],
            interval="60",
            days=7,
            fetcher=fetcher,
            api_key=mock_api_key
        )

        assert result["total_symbols"] == 3
        assert result["successful"] == 2
        assert result["failed"] == 1
        assert result["results"][0]["success"] is True
        assert result["results"][1]["success"] is False
        assert result["results"][2]["success"] is True

    @pytest.mark.asyncio
    @patch('app.handlers.collection.KlineRepository')
    async def test_collect_bulk_no_data_for_symbol(self, mock_repo, mock_api_key):
        """Test handling when no data is fetched for a symbol"""
        fetcher = Mock()
        fetcher.get_historical_klines = AsyncMock(side_effect=[
            [{"timestamp": 1700000000000}],
            [],  # No data for second symbol
            [{"timestamp": 1700000000000}],
        ])

        mock_repo.bulk_upsert = AsyncMock(return_value=1)

        result = await collect_bulk_data(
            symbols=["BTCUSDT", "ETHUSDT", "BNBUSDT"],
            interval="60",
            days=7,
            fetcher=fetcher,
            api_key=mock_api_key
        )

        assert result["successful"] == 2
        assert result["failed"] == 1
        assert result["results"][1]["success"] is False
        assert result["results"][1]["error"] == "No data fetched"

    @pytest.mark.asyncio
    @patch('app.handlers.collection.KlineRepository')
    async def test_collect_bulk_adds_metadata(self, mock_repo, mock_api_key):
        """Test that metadata is added to all klines in bulk collection"""
        fetcher = Mock()
        klines = [{"timestamp": 1700000000000, "open": 50000}]
        fetcher.get_historical_klines = AsyncMock(return_value=klines)
        mock_repo.bulk_upsert = AsyncMock(return_value=1)

        await collect_bulk_data(
            symbols=["BTCUSDT"],
            interval="240",
            days=14,
            fetcher=fetcher,
            api_key=mock_api_key
        )

        assert klines[0]["symbol"] == "BTCUSDT"
        assert klines[0]["interval"] == "240"

    @pytest.mark.asyncio
    @patch('app.handlers.collection.KlineRepository')
    async def test_collect_bulk_result_structure(self, mock_repo, mock_fetcher, mock_api_key):
        """Test that bulk result has expected structure"""
        mock_repo.bulk_upsert = AsyncMock(return_value=1)

        result = await collect_bulk_data(
            symbols=["BTCUSDT"],
            interval="60",
            days=7,
            fetcher=mock_fetcher,
            api_key=mock_api_key
        )

        assert "success" in result
        assert "results" in result
        assert "total_symbols" in result
        assert "successful" in result
        assert "failed" in result

        # Check individual result structure
        assert "symbol" in result["results"][0]
        assert "success" in result["results"][0]
        assert "count" in result["results"][0]


class TestGetFetcher:
    """Integration tests for get_fetcher dependency"""

    def test_get_fetcher_extracts_from_request(self):
        """Test that get_fetcher extracts fetcher from request"""
        mock_fetcher = Mock()
        mock_request = Mock(spec=Request)
        mock_request.app.state.fetcher = mock_fetcher

        result = get_fetcher(mock_request)

        assert result == mock_fetcher

    def test_get_fetcher_with_none(self):
        """Test get_fetcher when fetcher is None"""
        mock_request = Mock(spec=Request)
        mock_request.app.state.fetcher = None

        result = get_fetcher(mock_request)

        assert result is None
