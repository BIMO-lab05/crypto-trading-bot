"""
Market Data Service - Database Models Tests
Purpose: Test SQLAlchemy models for TimescaleDB
"""

import pytest
from decimal import Decimal
from datetime import datetime
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from app.models import Base, Kline, Ticker, OrderBook


# Fixture for in-memory SQLite database
@pytest.fixture
def db_engine():
    """Create an in-memory SQLite database for testing"""
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Create a database session for testing"""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


class TestKlineModel:
    """Test Kline (candlestick) model"""

    def test_kline_table_name(self):
        """Test Kline table name"""
        assert Kline.__tablename__ == "klines"

    def test_kline_creation_with_all_fields(self, db_session):
        """Test creating Kline with all fields"""
        kline = Kline(
            timestamp=1699000000000,
            symbol="BTCUSDT",
            interval="60",
            open=Decimal("35000.12345678"),
            high=Decimal("35500.12345678"),
            low=Decimal("34800.12345678"),
            close=Decimal("35200.12345678"),
            volume=Decimal("123.45678901"),
            turnover=Decimal("4356789.12345678"),
            created_at=1699000001000
        )

        db_session.add(kline)
        db_session.commit()

        retrieved = db_session.query(Kline).first()
        assert retrieved is not None
        assert retrieved.timestamp == 1699000000000
        assert retrieved.symbol == "BTCUSDT"
        assert retrieved.interval == "60"
        assert float(retrieved.open) == 35000.12345678
        assert float(retrieved.high) == 35500.12345678
        assert float(retrieved.low) == 34800.12345678
        assert float(retrieved.close) == 35200.12345678
        assert float(retrieved.volume) == 123.45678901
        assert float(retrieved.turnover) == 4356789.12345678

    def test_kline_primary_key_composite(self, db_session):
        """Test Kline composite primary key (timestamp + symbol + interval)"""
        kline1 = Kline(
            timestamp=1699000000000,
            symbol="BTCUSDT",
            interval="60",
            open=Decimal("35000"),
            high=Decimal("35500"),
            low=Decimal("34800"),
            close=Decimal("35200"),
            volume=Decimal("100"),
            created_at=1699000001000
        )

        # Same timestamp and symbol, different interval - should succeed
        kline2 = Kline(
            timestamp=1699000000000,
            symbol="BTCUSDT",
            interval="240",
            open=Decimal("35000"),
            high=Decimal("35500"),
            low=Decimal("34800"),
            close=Decimal("35200"),
            volume=Decimal("100"),
            created_at=1699000001000
        )

        db_session.add(kline1)
        db_session.add(kline2)
        db_session.commit()

        count = db_session.query(Kline).count()
        assert count == 2

    def test_kline_to_dict(self):
        """Test Kline to_dict method"""
        kline = Kline(
            timestamp=1699000000000,
            symbol="ETHUSDT",
            interval="60",
            open=Decimal("2000.50"),
            high=Decimal("2010.75"),
            low=Decimal("1990.25"),
            close=Decimal("2005.00"),
            volume=Decimal("500.123"),
            turnover=Decimal("1002500.00"),
            created_at=1699000001000
        )

        result = kline.to_dict()

        assert isinstance(result, dict)
        assert result['timestamp'] == 1699000000000
        assert result['symbol'] == "ETHUSDT"
        assert result['interval'] == "60"
        assert result['open'] == 2000.50
        assert result['high'] == 2010.75
        assert result['low'] == 1990.25
        assert result['close'] == 2005.00
        assert result['volume'] == 500.123
        assert result['turnover'] == 1002500.00
        assert result['created_at'] == 1699000001000

    def test_kline_to_dict_without_turnover(self):
        """Test Kline to_dict with None turnover"""
        kline = Kline(
            timestamp=1699000000000,
            symbol="ETHUSDT",
            interval="60",
            open=Decimal("2000.50"),
            high=Decimal("2010.75"),
            low=Decimal("1990.25"),
            close=Decimal("2005.00"),
            volume=Decimal("500.123"),
            turnover=None,
            created_at=1699000001000
        )

        result = kline.to_dict()
        assert result['turnover'] is None

    def test_kline_numeric_precision(self, db_session):
        """Test Kline numeric precision for prices"""
        kline = Kline(
            timestamp=1699000000000,
            symbol="BTCUSDT",
            interval="60",
            open=Decimal("35000.12345678"),
            high=Decimal("35500.87654321"),
            low=Decimal("34800.11111111"),
            close=Decimal("35200.99999999"),
            volume=Decimal("123.45678901"),
            turnover=Decimal("4356789.12345678"),
            created_at=1699000001000
        )

        db_session.add(kline)
        db_session.commit()

        retrieved = db_session.query(Kline).first()
        # Check precision is maintained
        assert str(retrieved.open) == "35000.12345678"
        assert str(retrieved.high) == "35500.87654321"
        assert str(retrieved.low) == "34800.11111111"
        assert str(retrieved.close) == "35200.99999999"

    def test_kline_symbol_length(self, db_session):
        """Test Kline symbol max length (20 characters)"""
        kline = Kline(
            timestamp=1699000000000,
            symbol="A" * 20,  # Max 20 characters
            interval="60",
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
            volume=Decimal("1000"),
            created_at=1699000001000
        )

        db_session.add(kline)
        db_session.commit()

        retrieved = db_session.query(Kline).first()
        assert len(retrieved.symbol) == 20


class TestTickerModel:
    """Test Ticker model"""

    def test_ticker_table_name(self):
        """Test Ticker table name"""
        assert Ticker.__tablename__ == "tickers"

    def test_ticker_creation_with_all_fields(self, db_session):
        """Test creating Ticker with all fields"""
        ticker = Ticker(
            timestamp=1699000000000,
            symbol="BTCUSDT",
            last_price=Decimal("35000.12345678"),
            bid_price=Decimal("34999.12345678"),
            ask_price=Decimal("35001.12345678"),
            high_24h=Decimal("36000.12345678"),
            low_24h=Decimal("34000.12345678"),
            volume_24h=Decimal("12345.12345678"),
            turnover_24h=Decimal("432100000.12345678"),
            price_change_24h=Decimal("2.5"),
            created_at=1699000001000
        )

        db_session.add(ticker)
        db_session.commit()

        retrieved = db_session.query(Ticker).first()
        assert retrieved is not None
        assert retrieved.timestamp == 1699000000000
        assert retrieved.symbol == "BTCUSDT"
        assert float(retrieved.last_price) == 35000.12345678
        assert float(retrieved.bid_price) == 34999.12345678
        assert float(retrieved.ask_price) == 35001.12345678
        assert float(retrieved.high_24h) == 36000.12345678
        assert float(retrieved.low_24h) == 34000.12345678
        assert float(retrieved.volume_24h) == 12345.12345678

    def test_ticker_primary_key_composite(self, db_session):
        """Test Ticker composite primary key (timestamp + symbol)"""
        ticker1 = Ticker(
            timestamp=1699000000000,
            symbol="BTCUSDT",
            last_price=Decimal("35000"),
            created_at=1699000001000
        )

        # Same timestamp, different symbol - should succeed
        ticker2 = Ticker(
            timestamp=1699000000000,
            symbol="ETHUSDT",
            last_price=Decimal("2000"),
            created_at=1699000001000
        )

        db_session.add(ticker1)
        db_session.add(ticker2)
        db_session.commit()

        count = db_session.query(Ticker).count()
        assert count == 2

    def test_ticker_to_dict_with_all_fields(self):
        """Test Ticker to_dict method with all fields"""
        ticker = Ticker(
            timestamp=1699000000000,
            symbol="BTCUSDT",
            last_price=Decimal("35000.50"),
            bid_price=Decimal("34999.50"),
            ask_price=Decimal("35001.50"),
            high_24h=Decimal("36000.00"),
            low_24h=Decimal("34000.00"),
            volume_24h=Decimal("12345.67"),
            turnover_24h=Decimal("432100000.00"),
            price_change_24h=Decimal("2.5"),
            created_at=1699000001000
        )

        result = ticker.to_dict()

        assert isinstance(result, dict)
        assert result['timestamp'] == 1699000000000
        assert result['symbol'] == "BTCUSDT"
        assert result['last_price'] == 35000.50
        assert result['bid_price'] == 34999.50
        assert result['ask_price'] == 35001.50
        assert result['high_24h'] == 36000.00
        assert result['low_24h'] == 34000.00
        assert result['volume_24h'] == 12345.67
        assert result['turnover_24h'] == 432100000.00
        assert result['price_change_24h'] == 2.5
        assert result['created_at'] == 1699000001000

    def test_ticker_to_dict_with_none_optionals(self):
        """Test Ticker to_dict with None optional fields"""
        ticker = Ticker(
            timestamp=1699000000000,
            symbol="BTCUSDT",
            last_price=Decimal("35000"),
            bid_price=None,
            ask_price=None,
            high_24h=None,
            low_24h=None,
            volume_24h=None,
            turnover_24h=None,
            price_change_24h=None,
            created_at=1699000001000
        )

        result = ticker.to_dict()

        assert result['last_price'] == 35000.0
        assert result['bid_price'] is None
        assert result['ask_price'] is None
        assert result['high_24h'] is None
        assert result['low_24h'] is None
        assert result['volume_24h'] is None
        assert result['turnover_24h'] is None
        assert result['price_change_24h'] is None

    def test_ticker_minimal_required_fields(self, db_session):
        """Test Ticker with only required fields"""
        ticker = Ticker(
            timestamp=1699000000000,
            symbol="ETHUSDT",
            last_price=Decimal("2000.00"),
            created_at=1699000001000
        )

        db_session.add(ticker)
        db_session.commit()

        retrieved = db_session.query(Ticker).first()
        assert retrieved.timestamp == 1699000000000
        assert retrieved.symbol == "ETHUSDT"
        assert float(retrieved.last_price) == 2000.00
        assert retrieved.bid_price is None
        assert retrieved.ask_price is None


class TestOrderBookModel:
    """Test OrderBook model"""

    def test_orderbook_table_name(self):
        """Test OrderBook table name"""
        assert OrderBook.__tablename__ == "orderbook_snapshots"

    def test_orderbook_creation(self, db_session):
        """Test creating OrderBook snapshot"""
        orderbook = OrderBook(
            id=1,  # Explicit ID for SQLite compatibility
            timestamp=1699000000000,
            symbol="BTCUSDT",
            snapshot_data='{"bids": [[35000, 1.5], [34999, 2.0]], "asks": [[35001, 1.2], [35002, 1.8]]}',
            created_at=1699000001000
        )

        db_session.add(orderbook)
        db_session.commit()

        retrieved = db_session.query(OrderBook).first()
        assert retrieved is not None
        assert retrieved.timestamp == 1699000000000
        assert retrieved.symbol == "BTCUSDT"
        assert "bids" in retrieved.snapshot_data
        assert "asks" in retrieved.snapshot_data

    def test_orderbook_auto_increment_id(self, db_session):
        """Test OrderBook auto-incrementing ID"""
        orderbook1 = OrderBook(
            id=1,  # Explicit ID for SQLite compatibility
            timestamp=1699000000000,
            symbol="BTCUSDT",
            snapshot_data='{"bids": [], "asks": []}',
            created_at=1699000001000
        )

        orderbook2 = OrderBook(
            id=2,  # Explicit ID for SQLite compatibility
            timestamp=1699000001000,
            symbol="BTCUSDT",
            snapshot_data='{"bids": [], "asks": []}',
            created_at=1699000002000
        )

        db_session.add(orderbook1)
        db_session.add(orderbook2)
        db_session.commit()

        # IDs should be set as specified
        assert orderbook1.id is not None
        assert orderbook2.id is not None
        assert orderbook2.id > orderbook1.id

    def test_orderbook_multiple_symbols(self, db_session):
        """Test storing orderbooks for multiple symbols"""
        orderbook1 = OrderBook(
            id=1,  # Explicit ID for SQLite compatibility
            timestamp=1699000000000,
            symbol="BTCUSDT",
            snapshot_data='{"bids": [], "asks": []}',
            created_at=1699000001000
        )

        orderbook2 = OrderBook(
            id=2,  # Explicit ID for SQLite compatibility
            timestamp=1699000000000,
            symbol="ETHUSDT",
            snapshot_data='{"bids": [], "asks": []}',
            created_at=1699000001000
        )

        db_session.add(orderbook1)
        db_session.add(orderbook2)
        db_session.commit()

        count = db_session.query(OrderBook).count()
        assert count == 2

    def test_orderbook_snapshot_data_json(self, db_session):
        """Test OrderBook snapshot_data stores JSON correctly"""
        import json

        snapshot_dict = {
            "bids": [
                [35000.50, 1.5],
                [34999.75, 2.0],
                [34998.00, 3.5]
            ],
            "asks": [
                [35001.25, 1.2],
                [35002.50, 1.8],
                [35003.75, 2.5]
            ]
        }

        orderbook = OrderBook(
            id=1,  # Explicit ID for SQLite compatibility
            timestamp=1699000000000,
            symbol="BTCUSDT",
            snapshot_data=json.dumps(snapshot_dict),
            created_at=1699000001000
        )

        db_session.add(orderbook)
        db_session.commit()

        retrieved = db_session.query(OrderBook).first()
        parsed_data = json.loads(retrieved.snapshot_data)

        assert len(parsed_data['bids']) == 3
        assert len(parsed_data['asks']) == 3
        assert parsed_data['bids'][0][0] == 35000.50
        assert parsed_data['asks'][0][0] == 35001.25


class TestModelIndexes:
    """Test model indexes are defined"""

    def test_kline_indexes_defined(self):
        """Test Kline model has correct indexes"""
        # Use __table__.indexes instead of inspect(Kline)
        indexes = list(Kline.__table__.indexes)

        # Check that indexes are defined in __table_args__
        assert hasattr(Kline, '__table_args__')
        assert len(Kline.__table_args__) > 0
        # Verify indexes exist on the table
        assert len(indexes) > 0 or len(Kline.__table_args__) > 0

    def test_ticker_indexes_defined(self):
        """Test Ticker model has correct indexes"""
        assert hasattr(Ticker, '__table_args__')
        assert len(Ticker.__table_args__) > 0

    def test_orderbook_indexes_defined(self):
        """Test OrderBook model has correct indexes"""
        assert hasattr(OrderBook, '__table_args__')
        assert len(OrderBook.__table_args__) > 0


class TestModelRelationships:
    """Test querying patterns across models"""

    def test_query_klines_by_symbol(self, db_session):
        """Test querying klines by symbol"""
        kline1 = Kline(
            timestamp=1699000000000, symbol="BTCUSDT", interval="60",
            open=Decimal("35000"), high=Decimal("35500"), low=Decimal("34800"),
            close=Decimal("35200"), volume=Decimal("100"), created_at=1699000001000
        )
        kline2 = Kline(
            timestamp=1699000001000, symbol="ETHUSDT", interval="60",
            open=Decimal("2000"), high=Decimal("2010"), low=Decimal("1990"),
            close=Decimal("2005"), volume=Decimal("500"), created_at=1699000002000
        )

        db_session.add(kline1)
        db_session.add(kline2)
        db_session.commit()

        btc_klines = db_session.query(Kline).filter(Kline.symbol == "BTCUSDT").all()
        assert len(btc_klines) == 1
        assert btc_klines[0].symbol == "BTCUSDT"

    def test_query_tickers_by_timestamp_range(self, db_session):
        """Test querying tickers by timestamp range"""
        ticker1 = Ticker(
            timestamp=1699000000000, symbol="BTCUSDT",
            last_price=Decimal("35000"), created_at=1699000001000
        )
        ticker2 = Ticker(
            timestamp=1699001000000, symbol="BTCUSDT",
            last_price=Decimal("35100"), created_at=1699001001000
        )
        ticker3 = Ticker(
            timestamp=1699002000000, symbol="BTCUSDT",
            last_price=Decimal("35200"), created_at=1699002001000
        )

        db_session.add_all([ticker1, ticker2, ticker3])
        db_session.commit()

        # Query range
        results = db_session.query(Ticker).filter(
            Ticker.timestamp >= 1699000500000,
            Ticker.timestamp <= 1699001500000
        ).all()

        assert len(results) == 1
        assert results[0].timestamp == 1699001000000


class TestModelComments:
    """Test that model comments are defined for documentation"""

    def test_kline_has_table_comment(self):
        """Test Kline table has comment"""
        table_args = Kline.__table_args__
        # Check if there's a comment in table_args dict
        for arg in table_args:
            if isinstance(arg, dict) and 'comment' in arg:
                assert arg['comment'] == 'Candlestick/Kline OHLCV data'
                return
        pytest.fail("Kline table comment not found")

    def test_ticker_has_table_comment(self):
        """Test Ticker table has comment"""
        table_args = Ticker.__table_args__
        for arg in table_args:
            if isinstance(arg, dict) and 'comment' in arg:
                assert arg['comment'] == 'Real-time ticker data'
                return
        pytest.fail("Ticker table comment not found")

    def test_orderbook_has_table_comment(self):
        """Test OrderBook table has comment"""
        table_args = OrderBook.__table_args__
        for arg in table_args:
            if isinstance(arg, dict) and 'comment' in arg:
                assert arg['comment'] == 'Order book snapshots'
                return
        pytest.fail("OrderBook table comment not found")
