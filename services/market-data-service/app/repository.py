"""
Market Data Service - Data Repository
Purpose: Database operations for market data
"""

from sqlalchemy import select, and_, desc, func
from sqlalchemy.dialects.postgresql import insert
from decimal import Decimal
from typing import List, Optional
import logging
import time

from app.config import get_settings
from app.models import Kline, OpenInterest, OrderBook, Ticker
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
                records.append(
                    {
                        "timestamp": k["timestamp"],
                        "symbol": k.get("symbol", ""),
                        "interval": k.get("interval", ""),
                        "open": k["open"],
                        "high": k["high"],
                        "low": k["low"],
                        "close": k["close"],
                        "volume": k["volume"],
                        "turnover": k.get("turnover"),
                        "is_mainnet": is_mainnet,
                        "created_at": created_at,
                    }
                )

            # Bulk upsert in batches to avoid PostgreSQL parameter limit
            # PostgreSQL max params is 32767, each kline has 10 params
            # Safe batch size: 500 records per batch
            batch_size = 500
            total_inserted = 0

            for i in range(0, len(records), batch_size):
                batch = records[i : i + batch_size]

                stmt = insert(Kline).values(batch)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["timestamp", "symbol", "interval"],
                    set_={
                        "open": stmt.excluded.open,
                        "high": stmt.excluded.high,
                        "low": stmt.excluded.low,
                        "close": stmt.excluded.close,
                        "volume": stmt.excluded.volume,
                        "turnover": stmt.excluded.turnover,
                    },
                )

                await session.execute(stmt)
                total_inserted += len(batch)
                logger.info(
                    f"Inserted batch {i // batch_size + 1}: {len(batch)} klines"
                )

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
        mainnet_only: bool = True,
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
                and_(Kline.symbol == symbol, Kline.interval == interval)
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
    async def get_latest_kline(
        symbol: str, interval: str, mainnet_only: bool = True
    ) -> Optional[Kline]:
        """
        Get most recent kline for a symbol/interval

        Args:
            symbol: Trading pair
            interval: Candlestick interval
            mainnet_only: If True (default), exclude rows tagged
                ``is_mainnet=False`` — same audit-aligned filtering as
                :meth:`get_klines`. Pass ``False`` to include testnet rows.

        Returns:
            Latest Kline or None
        """
        async with get_db_session() as session:
            query = select(Kline).where(
                and_(Kline.symbol == symbol, Kline.interval == interval)
            )

            if mainnet_only:
                query = query.where(Kline.is_mainnet.is_(True))

            query = query.order_by(desc(Kline.timestamp)).limit(1)

            result = await session.execute(query)
            kline = result.scalar_one_or_none()

            return kline


class TickerRepository:
    """Repository for ticker data operations"""

    @staticmethod
    async def get_newest_row_age_seconds() -> Optional[float]:
        """
        Age in seconds of the newest ticker row across all symbols, or None if
        the table is empty.

        Used by /ready to detect a stalled ingest. Deliberately symbol-agnostic:
        the question is "is the collector running at all", not "is this one pair
        current", and a single global MAX is one indexed lookup.
        """
        async with get_db_session() as session:
            result = await session.execute(select(func.max(Ticker.timestamp)))
            newest = result.scalar_one_or_none()

        if newest is None:
            return None
        return max(0.0, time.time() - (float(newest) / 1000.0))

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
                symbol=ticker_data["symbol"],
                last_price=ticker_data["last_price"],
                bid_price=ticker_data.get("bid_price"),
                ask_price=ticker_data.get("ask_price"),
                high_24h=ticker_data.get("high_24h"),
                low_24h=ticker_data.get("low_24h"),
                volume_24h=ticker_data.get("volume_24h"),
                turnover_24h=ticker_data.get("turnover_24h"),
                price_change_24h=ticker_data.get("price_change_24h"),
                created_at=int(time.time() * 1000),
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
            query = (
                select(Ticker)
                .where(Ticker.symbol == symbol)
                .order_by(desc(Ticker.timestamp))
                .limit(1)
            )

            result = await session.execute(query)
            ticker = result.scalar_one_or_none()

            return ticker


class OrderbookRepository:
    """Insert-only persistence for orderbook_snapshots (OrderBook model)"""

    @staticmethod
    def _build_row(snapshot: dict) -> OrderBook:
        """
        Build an OrderBook ORM instance from a raw snapshot dict.

        snapshot_data is assigned as a dict, not json.dumps()'d — the column
        is JSONB (final review H-3) and SQLAlchemy's postgresql.JSONB type
        binds Python dicts directly. Double-encoding would store a JSON
        *string* inside the jsonb column instead of a real object, defeating
        every jsonb operator and GIN index Phase C needs.

        best_bid/best_ask are built via Decimal(str(...)), never float() or
        round(_, 2) — the latter destroyed ADA precision in a prior incident
        (CLAUDE.md §10, commit 487d1bd) and NUMERIC(38, 8) columns need exact
        decimal input, not a float's binary rounding.
        """
        bids = snapshot["bids"]
        asks = snapshot["asks"]
        best_bid = Decimal(str(bids[0][0])) if bids else None
        best_ask = Decimal(str(asks[0][0])) if asks else None
        return OrderBook(
            timestamp=int(snapshot["timestamp_ms"]),
            symbol=snapshot["symbol"],
            snapshot_data={"bids": bids, "asks": asks},
            best_bid=best_bid,
            best_ask=best_ask,
            created_at=int(time.time() * 1000),
        )

    @staticmethod
    async def save_snapshot(snapshot: dict) -> bool:
        """
        Save a single orderbook snapshot (kept for compatibility; the
        scheduler's hot path uses save_snapshots_bulk instead — final review
        H-2/M-6, one session per tick rather than one per symbol).

        Args:
            snapshot: Dict with symbol, timestamp_ms, bids, asks

        Returns:
            True if successful, False on error
        """
        try:
            async with get_db_session() as session:
                row = OrderbookRepository._build_row(snapshot)
                session.add(row)
                # Commit is handled by get_db_session() context manager

                logger.debug(f"Saved orderbook snapshot for {snapshot['symbol']}")
                return True
        except Exception as e:
            logger.error(f"Error saving orderbook snapshot: {e}")
            return False

    @staticmethod
    async def save_snapshots_bulk(snapshots: List[dict]) -> int:
        """
        Persist a tick's worth of orderbook snapshots in ONE session
        (final review H-2/M-6): a single session.add_all + one commit instead
        of 14 sessions/BEGIN-COMMIT pairs per tick.

        Args:
            snapshots: List of dicts with symbol, timestamp_ms, bids, asks

        Returns:
            Number of rows written (0 on error, logged not raised — callers
            treat this like the aggregate error_count they already track)
        """
        if not snapshots:
            return 0

        try:
            async with get_db_session() as session:
                rows = [OrderbookRepository._build_row(s) for s in snapshots]
                session.add_all(rows)
                # Commit is handled by get_db_session() context manager

                logger.debug(f"Saved {len(rows)} orderbook snapshots in one session")
                return len(rows)
        except Exception as e:
            logger.error(f"Error bulk-saving orderbook snapshots: {e}")
            return 0


class OpenInterestRepository:
    """Repository for open_interest data operations (edge-search v2 A2)"""

    @staticmethod
    async def bulk_upsert(rows: List[dict]) -> int:
        """
        Bulk insert or update open-interest rows.
        Uses PostgreSQL's ON CONFLICT DO UPDATE against the unique
        (symbol, timestamp) index, same style as KlineRepository.bulk_upsert.

        Args:
            rows: List of {"symbol", "timestamp_ms", "open_interest",
                "open_interest_value"} dicts. open_interest_value may be
                None when Bybit's payload omits it (final review H-3).

        Returns:
            Number of records inserted/updated
        """
        if not rows:
            return 0

        async with get_db_session() as session:
            created_at = int(time.time() * 1000)
            records = [
                {
                    "timestamp": int(r["timestamp_ms"]),
                    "symbol": r["symbol"],
                    "open_interest": r["open_interest"],
                    "open_interest_value": r.get("open_interest_value"),
                    "created_at": created_at,
                }
                for r in rows
            ]

            batch_size = 500
            total_upserted = 0

            for i in range(0, len(records), batch_size):
                batch = records[i : i + batch_size]

                stmt = insert(OpenInterest).values(batch)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["symbol", "timestamp"],
                    set_={
                        "open_interest": stmt.excluded.open_interest,
                        "open_interest_value": stmt.excluded.open_interest_value,
                    },
                )

                await session.execute(stmt)
                total_upserted += len(batch)

            # Commit is handled by get_db_session() context manager

            logger.info(f"Upserted total {total_upserted} open interest rows")
            return total_upserted
