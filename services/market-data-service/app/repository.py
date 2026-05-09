"""
Market Data Service - Data Repository
Purpose: Database operations for market data
"""

from sqlalchemy import select, and_, desc
from sqlalchemy.dialects.postgresql import insert
from typing import List, Optional
import logging
import time

from app.config import get_settings
from app.models import Kline, Ticker
from app.database import get_db_session

logger = logging.getLogger(__name__)


class KlineRepository:
    """Repository for kline/candlestick data operations"""
    
    @staticmethod
    async def bulk_upsert(klines: List[dict]) -> int:
        """
        Bulk insert or update klines
        Uses PostgreSQL's ON CONFLICT DO UPDATE
        
        Args:
            klines: List of kline dictionaries
        
        Returns:
            Number of records inserted/updated
        """
        if not klines:
            return 0
        
        async with get_db_session() as session:
            # Prepare data for insert
            records = []
            created_at = int(time.time() * 1000)
            # Tag every ingest row with the current connector source. Each
            # batch is homogeneous because we only flip BYBIT_TESTNET via
            # restart, never mid-run. Audit 2026-04-29.
            is_mainnet = not get_settings().bybit_testnet

            for k in klines:
                records.append({
                    'timestamp': k['timestamp'],
                    'symbol': k.get('symbol', ''),
                    'interval': k.get('interval', ''),
                    'open': k['open'],
                    'high': k['high'],
                    'low': k['low'],
                    'close': k['close'],
                    'volume': k['volume'],
                    'turnover': k.get('turnover'),
                    'is_mainnet': is_mainnet,
                    'created_at': created_at
                })

            # Bulk upsert in batches to avoid PostgreSQL parameter limit
            # PostgreSQL max params is 32767, each kline has 10 params
            # Safe batch size: 500 records per batch
            batch_size = 500
            total_inserted = 0

            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]

                stmt = insert(Kline).values(batch)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['timestamp', 'symbol', 'interval'],
                    set_={
                        'open': stmt.excluded.open,
                        'high': stmt.excluded.high,
                        'low': stmt.excluded.low,
                        'close': stmt.excluded.close,
                        'volume': stmt.excluded.volume,
                        'turnover': stmt.excluded.turnover
                    }
                )

                await session.execute(stmt)
                total_inserted += len(batch)
                logger.info(f"Inserted batch {i//batch_size + 1}: {len(batch)} klines")

            # Commit is handled by get_db_session() context manager

            logger.info(f"Upserted total {total_inserted} klines")
            return total_inserted
    
    @staticmethod
    async def get_klines(
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000,
        mainnet_only: bool = True
    ) -> List[Kline]:
        """
        Query klines from database.

        Args:
            symbol: Trading pair
            interval: Candlestick interval
            start_time: Start timestamp (ms)
            end_time: End timestamp (ms)
            limit: Maximum records to return
            mainnet_only: If True (default), exclude rows tagged
                ``is_mainnet=False``. The 2026-04-25 testnet→mainnet flip
                left mixed history in the table; default-True filtering
                is the audit-aligned safe behaviour. Pass ``False`` to
                explicitly include testnet rows (e.g. forensic analysis).

        Returns:
            List of Kline objects
        """
        async with get_db_session() as session:
            # Build query
            query = select(Kline).where(
                and_(
                    Kline.symbol == symbol,
                    Kline.interval == interval
                )
            )

            if mainnet_only:
                query = query.where(Kline.is_mainnet.is_(True))

            # Add time filters
            if start_time:
                query = query.where(Kline.timestamp >= start_time)
            if end_time:
                query = query.where(Kline.timestamp <= end_time)

            # Order by time descending and limit
            query = query.order_by(desc(Kline.timestamp)).limit(limit)

            # Execute
            result = await session.execute(query)
            klines = result.scalars().all()

            logger.info(
                f"Retrieved {len(klines)} klines for {symbol} ({interval}) "
                f"mainnet_only={mainnet_only}"
            )
            return klines
    
    @staticmethod
    async def get_latest_kline(symbol: str, interval: str) -> Optional[Kline]:
        """
        Get most recent kline for a symbol/interval
        
        Args:
            symbol: Trading pair
            interval: Candlestick interval
        
        Returns:
            Latest Kline or None
        """
        async with get_db_session() as session:
            query = select(Kline).where(
                and_(
                    Kline.symbol == symbol,
                    Kline.interval == interval
                )
            ).order_by(desc(Kline.timestamp)).limit(1)
            
            result = await session.execute(query)
            kline = result.scalar_one_or_none()
            
            return kline


class TickerRepository:
    """Repository for ticker data operations"""
    
    @staticmethod
    async def save_ticker(ticker_data: dict) -> bool:
        """
        Save ticker data
        
        Args:
            ticker_data: Ticker dictionary
        
        Returns:
            True if successful
        """
        async with get_db_session() as session:
            ticker = Ticker(
                timestamp=int(time.time() * 1000),
                symbol=ticker_data['symbol'],
                last_price=ticker_data['last_price'],
                bid_price=ticker_data.get('bid_price'),
                ask_price=ticker_data.get('ask_price'),
                high_24h=ticker_data.get('high_24h'),
                low_24h=ticker_data.get('low_24h'),
                volume_24h=ticker_data.get('volume_24h'),
                turnover_24h=ticker_data.get('turnover_24h'),
                price_change_24h=ticker_data.get('price_change_24h'),
                created_at=int(time.time() * 1000)
            )

            session.add(ticker)
            # Commit is handled by get_db_session() context manager

            logger.info(f"Saved ticker for {ticker_data['symbol']}")
            return True
    
    @staticmethod
    async def get_latest_ticker(symbol: str) -> Optional[Ticker]:
        """
        Get latest ticker for symbol
        
        Args:
            symbol: Trading pair
        
        Returns:
            Latest Ticker or None
        """
        async with get_db_session() as session:
            query = select(Ticker).where(
                Ticker.symbol == symbol
            ).order_by(desc(Ticker.timestamp)).limit(1)
            
            result = await session.execute(query)
            ticker = result.scalar_one_or_none()
            
            return ticker
