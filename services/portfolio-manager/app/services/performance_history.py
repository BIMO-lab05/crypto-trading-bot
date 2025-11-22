"""
Performance History Service
Handles historical tracking of portfolio performance metrics

Responsibilities:
- Store daily performance snapshots in PostgreSQL
- Retrieve historical performance data
- Calculate period-based performance (week, month, year, all-time)
- Manage performance data lifecycle
"""

import logging
from typing import List, Dict, Optional, Any
from decimal import Decimal
from datetime import datetime, timedelta, timezone
import asyncpg
from asyncpg.pool import Pool

from app.models import (
    DailyPerformance,
    PeriodPerformance,
    PerformanceMetrics
)
from app.config import settings

logger = logging.getLogger(__name__)


class PerformanceHistory:
    """
    Performance history tracking service

    Manages historical performance snapshots and period-based calculations
    using PostgreSQL for persistence.

    Attributes:
        db_pool: AsyncPG connection pool
        initialized: Whether the service is initialized
    """

    def __init__(self, db_pool: Optional[Pool] = None):
        """
        Initialize performance history service

        Args:
            db_pool: PostgreSQL connection pool (optional, can be set later)
        """
        self.db_pool = db_pool
        self.initialized = False
        logger.info("PerformanceHistory service created")

    async def initialize(self, db_pool: Pool) -> None:
        """
        Initialize service with database connection pool

        Args:
            db_pool: PostgreSQL connection pool
        """
        self.db_pool = db_pool
        self.initialized = True
        logger.info("PerformanceHistory service initialized with database pool")

    async def snapshot_performance(
        self,
        portfolio_id: str,
        metrics: PerformanceMetrics,
        total_value: Decimal,
        cash_balance: Decimal,
        positions_value: Decimal,
        snapshot_type: str = "DAILY"
    ) -> bool:
        """
        Store daily performance snapshot in database

        Creates a historical record of portfolio performance for tracking
        and period-based analysis.

        Args:
            portfolio_id: Portfolio identifier
            metrics: Current performance metrics
            total_value: Total portfolio value
            cash_balance: Available cash balance
            positions_value: Total value of open positions
            snapshot_type: Type of snapshot (DAILY, MANUAL, EOD)

        Returns:
            bool: True if snapshot saved successfully

        Raises:
            RuntimeError: If database not initialized
            Exception: If database insert fails
        """
        if not self.initialized or not self.db_pool:
            raise RuntimeError("PerformanceHistory not initialized with database pool")

        try:
            # Calculate daily P&L from previous snapshot
            daily_pnl = await self._calculate_daily_pnl(portfolio_id, total_value)

            # Calculate daily return percentage
            daily_return_pct = await self._calculate_daily_return(portfolio_id, total_value)

            # Insert snapshot into database
            async with self.db_pool.acquire() as conn:
                query = """
                INSERT INTO portfolio.performance_history (
                    portfolio_id,
                    timestamp,
                    total_value,
                    cash_balance,
                    positions_value,
                    realized_pnl,
                    unrealized_pnl,
                    total_pnl,
                    daily_pnl,
                    roi_percent,
                    daily_return_percent,
                    sharpe_ratio,
                    max_drawdown,
                    volatility,
                    win_rate,
                    total_trades,
                    winning_trades,
                    losing_trades,
                    snapshot_type,
                    created_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17, $18, $19, $20
                )
                ON CONFLICT (portfolio_id, date_trunc('day', timestamp))
                DO UPDATE SET
                    total_value = EXCLUDED.total_value,
                    cash_balance = EXCLUDED.cash_balance,
                    positions_value = EXCLUDED.positions_value,
                    realized_pnl = EXCLUDED.realized_pnl,
                    unrealized_pnl = EXCLUDED.unrealized_pnl,
                    total_pnl = EXCLUDED.total_pnl,
                    daily_pnl = EXCLUDED.daily_pnl,
                    roi_percent = EXCLUDED.roi_percent,
                    daily_return_percent = EXCLUDED.daily_return_percent,
                    sharpe_ratio = EXCLUDED.sharpe_ratio,
                    max_drawdown = EXCLUDED.max_drawdown,
                    volatility = EXCLUDED.volatility,
                    win_rate = EXCLUDED.win_rate,
                    total_trades = EXCLUDED.total_trades,
                    winning_trades = EXCLUDED.winning_trades,
                    losing_trades = EXCLUDED.losing_trades,
                    snapshot_type = EXCLUDED.snapshot_type
                RETURNING id;
                """

                result = await conn.fetchval(
                    query,
                    portfolio_id,
                    datetime.now(timezone.utc),
                    total_value,
                    cash_balance,
                    positions_value,
                    metrics.realized_pnl,
                    metrics.unrealized_pnl,
                    metrics.total_pnl,
                    daily_pnl,
                    metrics.total_return_pct,
                    daily_return_pct,
                    metrics.sharpe_ratio,
                    metrics.max_drawdown,
                    metrics.volatility,
                    metrics.win_rate,
                    metrics.total_trades,
                    metrics.winning_trades,
                    metrics.losing_trades,
                    snapshot_type,
                    datetime.now(timezone.utc)
                )

                logger.info(
                    f"Performance snapshot saved for {portfolio_id}: "
                    f"value={total_value}, pnl={metrics.total_pnl}, "
                    f"snapshot_id={result}"
                )
                return True

        except Exception as e:
            logger.error(
                f"Failed to save performance snapshot for {portfolio_id}: {e}",
                exc_info=True
            )
            raise

    async def get_daily_performance(
        self,
        portfolio_id: str,
        days: int = 30
    ) -> List[DailyPerformance]:
        """
        Retrieve daily performance for last N days

        Fetches historical performance snapshots in chronological order
        for trend analysis and charting.

        Args:
            portfolio_id: Portfolio identifier
            days: Number of days to retrieve (default: 30)

        Returns:
            List[DailyPerformance]: Daily performance records

        Raises:
            RuntimeError: If database not initialized
        """
        if not self.initialized or not self.db_pool:
            raise RuntimeError("PerformanceHistory not initialized with database pool")

        try:
            async with self.db_pool.acquire() as conn:
                query = """
                SELECT
                    timestamp::DATE as date,
                    total_value,
                    daily_pnl,
                    daily_return_percent,
                    roi_percent,
                    total_trades
                FROM portfolio.performance_history
                WHERE portfolio_id = $1
                    AND timestamp >= NOW() - ($2 || ' days')::INTERVAL
                    AND snapshot_type = 'DAILY'
                ORDER BY timestamp ASC;
                """

                rows = await conn.fetch(query, portfolio_id, days)

                # Convert to DailyPerformance models
                daily_performance = []
                cumulative_return = Decimal("0")

                for row in rows:
                    # Calculate cumulative return
                    if row['roi_percent']:
                        cumulative_return = Decimal(str(row['roi_percent']))

                    daily_performance.append(
                        DailyPerformance(
                            date=row['date'].strftime('%Y-%m-%d'),
                            portfolio_value=str(row['total_value']),
                            daily_pnl=str(row['daily_pnl'] or Decimal("0")),
                            daily_return_pct=str(row['daily_return_percent'] or Decimal("0")),
                            cumulative_return_pct=str(cumulative_return),
                            trades_count=row['total_trades'] or 0
                        )
                    )

                logger.info(
                    f"Retrieved {len(daily_performance)} daily performance "
                    f"records for {portfolio_id}"
                )

                return daily_performance

        except Exception as e:
            logger.error(
                f"Failed to retrieve daily performance for {portfolio_id}: {e}",
                exc_info=True
            )
            return []

    async def calculate_period_performance(
        self,
        portfolio_id: str,
        period: str  # 'week', 'month', 'year', 'all'
    ) -> Optional[PeriodPerformance]:
        """
        Calculate performance for specific period

        Aggregates historical data to compute period-based metrics including
        returns, volatility, drawdowns, and trading statistics.

        Args:
            portfolio_id: Portfolio identifier
            period: Period type ('week', 'month', 'year', 'all')

        Returns:
            Optional[PeriodPerformance]: Period performance metrics or None

        Raises:
            RuntimeError: If database not initialized
        """
        if not self.initialized or not self.db_pool:
            raise RuntimeError("PerformanceHistory not initialized with database pool")

        # Map period to days
        period_days = {
            'week': 7,
            'month': 30,
            'year': 365,
            'all': 10000  # Large number to get all data
        }

        if period not in period_days:
            logger.warning(f"Invalid period: {period}, defaulting to 'month'")
            period = 'month'

        days = period_days[period]

        try:
            async with self.db_pool.acquire() as conn:
                # Use the database function for period statistics
                query = """
                SELECT * FROM portfolio.get_period_stats($1, $2);
                """

                row = await conn.fetchrow(query, portfolio_id, days)

                if not row or not row['start_value']:
                    logger.warning(
                        f"No performance data found for {portfolio_id} "
                        f"in period {period}"
                    )
                    return None

                # Get best and worst days
                best_day, worst_day = await self._get_extreme_days(
                    conn, portfolio_id, days
                )

                period_perf = PeriodPerformance(
                    period=period,
                    start_date=row['start_date'].strftime('%Y-%m-%d'),
                    end_date=row['end_date'].strftime('%Y-%m-%d'),
                    start_value=str(row['start_value']),
                    end_value=str(row['end_value']),
                    total_return=str(row['total_return']),
                    total_return_pct=str(row['return_percent']),
                    volatility=float(row['volatility']) if row['volatility'] else None,
                    sharpe_ratio=None,  # Would need risk-free rate calculation
                    max_drawdown=None,  # Would need peak tracking
                    trades_count=row['total_trades'] or 0
                )

                logger.info(
                    f"Calculated {period} performance for {portfolio_id}: "
                    f"return={period_perf.total_return_pct}%"
                )

                return period_perf

        except Exception as e:
            logger.error(
                f"Failed to calculate period performance for {portfolio_id}: {e}",
                exc_info=True
            )
            return None

    async def _calculate_daily_pnl(
        self,
        portfolio_id: str,
        current_value: Decimal
    ) -> Optional[Decimal]:
        """
        Calculate P&L change from previous day

        Args:
            portfolio_id: Portfolio identifier
            current_value: Current total portfolio value

        Returns:
            Optional[Decimal]: Daily P&L or None if no previous data
        """
        if not self.db_pool:
            return None

        try:
            async with self.db_pool.acquire() as conn:
                query = """
                SELECT total_value
                FROM portfolio.performance_history
                WHERE portfolio_id = $1
                ORDER BY timestamp DESC
                LIMIT 1;
                """

                previous_value = await conn.fetchval(query, portfolio_id)

                if previous_value is None:
                    return None

                return current_value - Decimal(str(previous_value))

        except Exception as e:
            logger.error(f"Failed to calculate daily P&L: {e}")
            return None

    async def _calculate_daily_return(
        self,
        portfolio_id: str,
        current_value: Decimal
    ) -> Optional[Decimal]:
        """
        Calculate daily return percentage

        Args:
            portfolio_id: Portfolio identifier
            current_value: Current total portfolio value

        Returns:
            Optional[Decimal]: Daily return percentage or None
        """
        if not self.db_pool:
            return None

        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.fetchval(
                    "SELECT portfolio.calculate_daily_return($1, $2)",
                    portfolio_id,
                    current_value
                )

                return Decimal(str(result)) if result is not None else None

        except Exception as e:
            logger.error(f"Failed to calculate daily return: {e}")
            return None

    async def _get_extreme_days(
        self,
        conn: asyncpg.Connection,
        portfolio_id: str,
        days: int
    ) -> tuple[Optional[Dict], Optional[Dict]]:
        """
        Get best and worst performing days in period

        Args:
            conn: Database connection
            portfolio_id: Portfolio identifier
            days: Number of days to analyze

        Returns:
            Tuple of (best_day, worst_day) dictionaries
        """
        try:
            query = """
            WITH period_data AS (
                SELECT
                    timestamp::DATE as date,
                    daily_return_percent,
                    daily_pnl,
                    total_value
                FROM portfolio.performance_history
                WHERE portfolio_id = $1
                    AND timestamp >= NOW() - ($2 || ' days')::INTERVAL
                    AND snapshot_type = 'DAILY'
                    AND daily_return_percent IS NOT NULL
            )
            SELECT
                (SELECT row_to_json(t) FROM (
                    SELECT * FROM period_data
                    ORDER BY daily_return_percent DESC LIMIT 1
                ) t) as best_day,
                (SELECT row_to_json(t) FROM (
                    SELECT * FROM period_data
                    ORDER BY daily_return_percent ASC LIMIT 1
                ) t) as worst_day;
            """

            row = await conn.fetchrow(query, portfolio_id, days)

            return (row['best_day'], row['worst_day'])

        except Exception as e:
            logger.error(f"Failed to get extreme days: {e}")
            return (None, None)

    async def cleanup(self) -> None:
        """Cleanup service resources"""
        # Database pool is managed externally, just mark as not initialized
        self.initialized = False
        logger.info("PerformanceHistory service cleaned up")
