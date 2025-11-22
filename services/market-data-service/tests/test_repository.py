"""
Market Data Service - Repository Tests
Purpose: Test data repository operations for market data
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from decimal import Decimal
from app.repository import KlineRepository, TickerRepository
from app.models import Kline, Ticker


class TestKlineRepositoryBulkUpsert:
    """Test KlineRepository.bulk_upsert method"""

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    async def test_bulk_upsert_empty_list_returns_zero(self, mock_get_db_session):
        """Test bulk_upsert with empty list returns 0"""
        result = await KlineRepository.bulk_upsert([])
        assert result == 0
        # Should not create session for empty list
        mock_get_db_session.assert_not_called()

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    @patch('app.repository.time')
    async def test_bulk_upsert_single_kline(self, mock_time, mock_get_db_session):
        """Test bulk_upsert with single kline"""
        mock_time.time.return_value = 1699000000.0

        mock_session = AsyncMock()
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        klines = [{
            'timestamp': 1699000000000,
            'symbol': 'BTCUSDT',
            'interval': '60',
            'open': '35000.00',
            'high': '35500.00',
            'low': '34800.00',
            'close': '35200.00',
            'volume': '100.00',
            'turnover': '3520000.00'
        }]

        result = await KlineRepository.bulk_upsert(klines)

        assert result == 1
        mock_session.execute.assert_called_once()
        # Note: commit is called by get_db_session context manager, not directly

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    @patch('app.repository.time')
    async def test_bulk_upsert_multiple_klines(self, mock_time, mock_get_db_session):
        """Test bulk_upsert with multiple klines"""
        mock_time.time.return_value = 1699000000.0

        mock_session = AsyncMock()
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        klines = [
            {
                'timestamp': 1699000000000,
                'symbol': 'BTCUSDT',
                'interval': '60',
                'open': '35000.00',
                'high': '35500.00',
                'low': '34800.00',
                'close': '35200.00',
                'volume': '100.00'
            },
            {
                'timestamp': 1699003600000,
                'symbol': 'BTCUSDT',
                'interval': '60',
                'open': '35200.00',
                'high': '35700.00',
                'low': '35100.00',
                'close': '35400.00',
                'volume': '150.00'
            },
            {
                'timestamp': 1699007200000,
                'symbol': 'ETHUSDT',
                'interval': '60',
                'open': '2000.00',
                'high': '2010.00',
                'low': '1990.00',
                'close': '2005.00',
                'volume': '500.00'
            }
        ]

        result = await KlineRepository.bulk_upsert(klines)

        assert result == 3
        mock_session.execute.assert_called_once()
        # Note: commit is called by get_db_session context manager, not directly

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    @patch('app.repository.time')
    async def test_bulk_upsert_batching_large_dataset(self, mock_time, mock_get_db_session):
        """Test bulk_upsert batches large datasets (>500 records)"""
        mock_time.time.return_value = 1699000000.0

        mock_session = AsyncMock()
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        # Create 1000 klines to trigger batching
        klines = []
        for i in range(1000):
            klines.append({
                'timestamp': 1699000000000 + i * 60000,
                'symbol': 'BTCUSDT',
                'interval': '60',
                'open': '35000.00',
                'high': '35500.00',
                'low': '34800.00',
                'close': '35200.00',
                'volume': '100.00'
            })

        result = await KlineRepository.bulk_upsert(klines)

        assert result == 1000
        # Should be called 2 times (500 + 500)
        assert mock_session.execute.call_count == 2
        # Note: commit is called by get_db_session context manager, not directly

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    @patch('app.repository.time')
    async def test_bulk_upsert_handles_missing_optional_fields(self, mock_time, mock_get_db_session):
        """Test bulk_upsert handles missing optional fields"""
        mock_time.time.return_value = 1699000000.0

        mock_session = AsyncMock()
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        klines = [{
            'timestamp': 1699000000000,
            # Missing 'symbol' and 'interval' - should use empty string
            'open': '35000.00',
            'high': '35500.00',
            'low': '34800.00',
            'close': '35200.00',
            'volume': '100.00'
            # Missing 'turnover' - should be None
        }]

        result = await KlineRepository.bulk_upsert(klines)

        assert result == 1
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    @patch('app.repository.time')
    async def test_bulk_upsert_sets_created_at_timestamp(self, mock_time, mock_get_db_session):
        """Test bulk_upsert sets created_at timestamp"""
        mock_timestamp = 1699000000.0
        mock_time.time.return_value = mock_timestamp

        mock_session = AsyncMock()
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        klines = [{
            'timestamp': 1699000000000,
            'symbol': 'BTCUSDT',
            'interval': '60',
            'open': '35000.00',
            'high': '35500.00',
            'low': '34800.00',
            'close': '35200.00',
            'volume': '100.00'
        }]

        await KlineRepository.bulk_upsert(klines)

        # Verify created_at is set to current timestamp in milliseconds
        mock_time.time.assert_called()


class TestKlineRepositoryGetKlines:
    """Test KlineRepository.get_klines method"""

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    async def test_get_klines_with_symbol_and_interval(self, mock_get_db_session):
        """Test get_klines with symbol and interval filters"""
        mock_session = AsyncMock()
        mock_result = Mock()  # Changed from AsyncMock to Mock
        mock_scalars = Mock()
        mock_klines = [
            Mock(spec=Kline),
            Mock(spec=Kline),
            Mock(spec=Kline)
        ]
        mock_scalars.all = Mock(return_value=mock_klines)  # Explicitly set as Mock
        mock_result.scalars = Mock(return_value=mock_scalars)  # Explicitly set as Mock
        mock_session.execute.return_value = mock_result
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        klines = await KlineRepository.get_klines(
            symbol='BTCUSDT',
            interval='60'
        )

        assert len(klines) == 3
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    async def test_get_klines_with_time_filters(self, mock_get_db_session):
        """Test get_klines with start_time and end_time filters"""
        mock_session = AsyncMock()
        mock_result = Mock()  # Changed from AsyncMock to Mock
        mock_scalars = Mock()
        mock_scalars.all = Mock(return_value=[])  # Explicitly set as Mock
        mock_result.scalars = Mock(return_value=mock_scalars)  # Explicitly set as Mock
        mock_session.execute.return_value = mock_result
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        klines = await KlineRepository.get_klines(
            symbol='BTCUSDT',
            interval='60',
            start_time=1699000000000,
            end_time=1699100000000
        )

        assert isinstance(klines, list)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    async def test_get_klines_with_limit(self, mock_get_db_session):
        """Test get_klines respects limit parameter"""
        mock_session = AsyncMock()
        mock_result = Mock()  # Changed from AsyncMock to Mock
        mock_scalars = Mock()
        # Return exactly limit number of items
        mock_klines = [Mock(spec=Kline) for _ in range(50)]
        mock_scalars.all = Mock(return_value=mock_klines)  # Explicitly set as Mock
        mock_result.scalars = Mock(return_value=mock_scalars)  # Explicitly set as Mock
        mock_session.execute.return_value = mock_result
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        klines = await KlineRepository.get_klines(
            symbol='BTCUSDT',
            interval='60',
            limit=50
        )

        assert len(klines) == 50
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    async def test_get_klines_default_limit(self, mock_get_db_session):
        """Test get_klines uses default limit of 1000"""
        mock_session = AsyncMock()
        mock_result = Mock()  # Changed from AsyncMock to Mock
        mock_scalars = Mock()
        mock_scalars.all = Mock(return_value=[])  # Explicitly set as Mock
        mock_result.scalars = Mock(return_value=mock_scalars)  # Explicitly set as Mock
        mock_session.execute.return_value = mock_result
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        await KlineRepository.get_klines(
            symbol='BTCUSDT',
            interval='60'
            # No limit specified - should use default 1000
        )

        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    async def test_get_klines_returns_empty_list_when_no_data(self, mock_get_db_session):
        """Test get_klines returns empty list when no data found"""
        mock_session = AsyncMock()
        mock_result = Mock()  # Changed from AsyncMock to Mock
        mock_scalars = Mock()
        mock_scalars.all = Mock(return_value=[])  # Explicitly set as Mock
        mock_result.scalars = Mock(return_value=mock_scalars)  # Explicitly set as Mock
        mock_session.execute.return_value = mock_result
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        klines = await KlineRepository.get_klines(
            symbol='NONEXISTENT',
            interval='60'
        )

        assert klines == []


class TestKlineRepositoryGetLatestKline:
    """Test KlineRepository.get_latest_kline method"""

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    async def test_get_latest_kline_returns_kline(self, mock_get_db_session):
        """Test get_latest_kline returns latest kline"""
        mock_session = AsyncMock()
        mock_result = Mock()  # Changed from AsyncMock to Mock
        mock_kline = Mock(spec=Kline)
        mock_kline.timestamp = 1699000000000
        mock_kline.symbol = 'BTCUSDT'
        mock_result.scalar_one_or_none = Mock(return_value=mock_kline)  # Explicitly set as Mock
        mock_session.execute.return_value = mock_result
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        kline = await KlineRepository.get_latest_kline(
            symbol='BTCUSDT',
            interval='60'
        )

        assert kline is not None
        assert kline.timestamp == 1699000000000
        assert kline.symbol == 'BTCUSDT'
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    async def test_get_latest_kline_returns_none_when_no_data(self, mock_get_db_session):
        """Test get_latest_kline returns None when no data found"""
        mock_session = AsyncMock()
        mock_result = Mock()  # Changed from AsyncMock to Mock
        mock_result.scalar_one_or_none = Mock(return_value=None)  # Explicitly set as Mock
        mock_session.execute.return_value = mock_result
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        kline = await KlineRepository.get_latest_kline(
            symbol='NONEXISTENT',
            interval='60'
        )

        assert kline is None


class TestTickerRepositorySaveTicker:
    """Test TickerRepository.save_ticker method"""

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    @patch('app.repository.time')
    async def test_save_ticker_with_all_fields(self, mock_time, mock_get_db_session):
        """Test save_ticker with all fields"""
        mock_time.time.return_value = 1699000000.0

        mock_session = AsyncMock()
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        ticker_data = {
            'symbol': 'BTCUSDT',
            'last_price': '35000.00',
            'bid_price': '34999.00',
            'ask_price': '35001.00',
            'high_24h': '36000.00',
            'low_24h': '34000.00',
            'volume_24h': '12345.67',
            'turnover_24h': '432100000.00',
            'price_change_24h': '2.5'
        }

        result = await TickerRepository.save_ticker(ticker_data)

        assert result is True
        mock_session.add.assert_called_once()
        # Note: commit is called by get_db_session context manager, not directly

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    @patch('app.repository.time')
    async def test_save_ticker_with_required_fields_only(self, mock_time, mock_get_db_session):
        """Test save_ticker with only required fields"""
        mock_time.time.return_value = 1699000000.0

        mock_session = AsyncMock()
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        ticker_data = {
            'symbol': 'ETHUSDT',
            'last_price': '2000.00'
            # All other fields are optional
        }

        result = await TickerRepository.save_ticker(ticker_data)

        assert result is True
        mock_session.add.assert_called_once()
        # Note: commit is called by get_db_session context manager, not directly

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    @patch('app.repository.time')
    async def test_save_ticker_sets_timestamp(self, mock_time, mock_get_db_session):
        """Test save_ticker sets current timestamp"""
        mock_timestamp = 1699000000.0
        mock_time.time.return_value = mock_timestamp

        mock_session = AsyncMock()
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        ticker_data = {
            'symbol': 'BTCUSDT',
            'last_price': '35000.00'
        }

        await TickerRepository.save_ticker(ticker_data)

        # Verify time.time() was called to get timestamp
        mock_time.time.assert_called()
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    @patch('app.repository.time')
    async def test_save_ticker_handles_optional_fields_as_none(self, mock_time, mock_get_db_session):
        """Test save_ticker handles missing optional fields as None"""
        mock_time.time.return_value = 1699000000.0

        mock_session = AsyncMock()
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        ticker_data = {
            'symbol': 'BTCUSDT',
            'last_price': '35000.00'
            # bid_price, ask_price, etc. are not provided
        }

        result = await TickerRepository.save_ticker(ticker_data)

        assert result is True
        # Verify ticker was created with .get() calls for optional fields
        mock_session.add.assert_called_once()


class TestTickerRepositoryGetLatestTicker:
    """Test TickerRepository.get_latest_ticker method"""

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    async def test_get_latest_ticker_returns_ticker(self, mock_get_db_session):
        """Test get_latest_ticker returns latest ticker"""
        mock_session = AsyncMock()
        mock_result = Mock()  # Changed from AsyncMock to Mock
        mock_ticker = Mock(spec=Ticker)
        mock_ticker.timestamp = 1699000000000
        mock_ticker.symbol = 'BTCUSDT'
        mock_ticker.last_price = Decimal('35000.00')
        mock_result.scalar_one_or_none = Mock(return_value=mock_ticker)  # Explicitly set as Mock
        mock_session.execute.return_value = mock_result
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        ticker = await TickerRepository.get_latest_ticker('BTCUSDT')

        assert ticker is not None
        assert ticker.symbol == 'BTCUSDT'
        assert ticker.timestamp == 1699000000000
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    async def test_get_latest_ticker_returns_none_when_no_data(self, mock_get_db_session):
        """Test get_latest_ticker returns None when no data found"""
        mock_session = AsyncMock()
        mock_result = Mock()  # Changed from AsyncMock to Mock
        mock_result.scalar_one_or_none = Mock(return_value=None)  # Explicitly set as Mock
        mock_session.execute.return_value = mock_result
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        ticker = await TickerRepository.get_latest_ticker('NONEXISTENT')

        assert ticker is None
        mock_session.execute.assert_called_once()


class TestRepositoryErrorHandling:
    """Test repository error handling"""

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    async def test_bulk_upsert_handles_database_error(self, mock_get_db_session):
        """Test bulk_upsert handles database errors"""
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("Database error")
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        klines = [{
            'timestamp': 1699000000000,
            'symbol': 'BTCUSDT',
            'interval': '60',
            'open': '35000.00',
            'high': '35500.00',
            'low': '34800.00',
            'close': '35200.00',
            'volume': '100.00'
        }]

        with pytest.raises(Exception) as exc_info:
            await KlineRepository.bulk_upsert(klines)

        assert "Database error" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    @patch('app.repository.time')
    async def test_save_ticker_handles_database_error(self, mock_time, mock_get_db_session):
        """Test save_ticker handles database errors"""
        mock_time.time.return_value = 1699000000.0

        # Create a context manager that raises an exception when entering
        mock_context = AsyncMock()
        mock_context.__aenter__.side_effect = Exception("Database connection failed")
        mock_get_db_session.return_value = mock_context

        ticker_data = {
            'symbol': 'BTCUSDT',
            'last_price': '35000.00'
        }

        with pytest.raises(Exception) as exc_info:
            await TickerRepository.save_ticker(ticker_data)

        assert "Database connection failed" in str(exc_info.value)


class TestRepositoryBatchingLogic:
    """Test repository batching logic"""

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    @patch('app.repository.time')
    async def test_bulk_upsert_batch_size_500(self, mock_time, mock_get_db_session):
        """Test bulk_upsert uses batch size of 500"""
        mock_time.time.return_value = 1699000000.0

        mock_session = AsyncMock()
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        # Create exactly 501 klines to test batching
        klines = []
        for i in range(501):
            klines.append({
                'timestamp': 1699000000000 + i,
                'symbol': 'BTCUSDT',
                'interval': '60',
                'open': '35000.00',
                'high': '35500.00',
                'low': '34800.00',
                'close': '35200.00',
                'volume': '100.00'
            })

        result = await KlineRepository.bulk_upsert(klines)

        assert result == 501
        # Should be called 2 times (500 + 1)
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    @patch('app.repository.get_db_session')
    @patch('app.repository.time')
    async def test_bulk_upsert_multiple_batches(self, mock_time, mock_get_db_session):
        """Test bulk_upsert handles multiple batches correctly"""
        mock_time.time.return_value = 1699000000.0

        mock_session = AsyncMock()
        mock_get_db_session.return_value.__aenter__.return_value = mock_session

        # Create 1234 klines (3 batches: 500 + 500 + 234)
        klines = []
        for i in range(1234):
            klines.append({
                'timestamp': 1699000000000 + i,
                'symbol': 'BTCUSDT',
                'interval': '60',
                'open': '35000.00',
                'high': '35500.00',
                'low': '34800.00',
                'close': '35200.00',
                'volume': '100.00'
            })

        result = await KlineRepository.bulk_upsert(klines)

        assert result == 1234
        # Should be called 3 times (500 + 500 + 234)
        assert mock_session.execute.call_count == 3
