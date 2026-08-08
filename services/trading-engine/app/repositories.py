"""
Database Repositories
Purpose: Data access layer for persisting trading data
"""

import json as _json
import logging
from typing import List, Optional
from decimal import Decimal
from uuid import UUID
from datetime import datetime, timezone

# Import local database module (works in Docker without shared directory)
from app.config import get_settings  # noqa: F401  (used in get_or_create default)
from app.database.connection import db_manager
from app.database.models import (
    Position as DBPosition,
    Portfolio as DBPortfolio,
)
from sqlalchemy import func, select, update

from app.models import Position

logger = logging.getLogger(__name__)


class PositionRepository:
    """
    Repository for Position database operations

    Responsibilities:
    - Create positions in database
    - Update position prices and P&L
    - Close positions
    - Query positions by various criteria
    """

    def __init__(self):
        """Initialize position repository"""
        self.db = db_manager
        logger.info("PositionRepository initialized")

    async def create(
        self,
        position: Position,
        portfolio_id: str = "paper_trading",
        entry_fee: Decimal = Decimal("0"),
    ) -> UUID:
        """
        Create a new position in database

        Args:
            position: Position object from app.models
            portfolio_id: Portfolio ID (default: paper_trading)
            entry_fee: Commission charged on the opening leg (AUDIT H7)

        Returns:
            Position ID (UUID)
        """
        try:
            async with self.db.get_async_session() as session:
                # Convert app Position model to DB Position model
                db_position = DBPosition(
                    position_id=position.id,
                    portfolio_id=portfolio_id,
                    symbol=position.symbol,
                    side=position.side.value,
                    quantity=position.quantity,
                    entry_price=position.entry_price,
                    current_price=position.current_price,
                    cost_basis=position.entry_price * position.quantity,
                    unrealized_pnl=position.unrealized_pnl,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    status=position.status.value,
                    strategy=position.strategy,
                    opened_at=position.opened_at,  # Fixed: was entry_time
                    remaining_quantity=(
                        position.remaining_quantity
                        if position.remaining_quantity is not None
                        else position.quantity
                    ),
                    entry_fee=entry_fee,
                    exit_fee=Decimal("0"),
                    posted_margin=position.posted_margin,
                    leverage=position.leverage,
                    # Pre-existing gap fixed here: the column has existed since
                    # before 007 and was NULL on all 19 live rows because this
                    # mapper never wrote it.
                    entry_signal_confidence=position.entry_signal_confidence,
                )

                session.add(db_position)
                await session.commit()

                logger.info(f"✓ Position saved to database: {position.id}")
                return position.id

        except Exception as e:
            logger.error(f"Failed to create position in database: {e}")
            raise

    async def update_price(
        self, position_id: UUID, current_price: Decimal, unrealized_pnl: Decimal
    ):
        """
        Update position price and P&L

        Args:
            position_id: Position UUID
            current_price: Current market price
            unrealized_pnl: Updated unrealized P&L
        """
        try:
            async with self.db.get_async_session() as session:
                stmt = (
                    update(DBPosition)
                    .where(DBPosition.position_id == position_id)
                    .values(
                        current_price=current_price,
                        unrealized_pnl=unrealized_pnl,
                        updated_at=datetime.now(timezone.utc),
                    )
                )

                await session.execute(stmt)
                await session.commit()

                logger.debug(f"Position {position_id} price updated in database")

        except Exception as e:
            logger.error(f"Failed to update position price in database: {e}")
            raise

    async def close(
        self,
        position_id: UUID,
        exit_price: Decimal,
        realized_pnl: Decimal,
        exit_reason: Optional[str] = None,
        exit_fee: Optional[Decimal] = None,
        exit_kind: Optional[str] = None,
        posted_margin: Optional[Decimal] = None,
    ):
        """
        Close a position in database

        Args:
            position_id: Position UUID
            exit_price: Exit price
            realized_pnl: Realized P&L, NET of entry + exit commissions
                (2026-08-04, AUDIT H7 — was persisted gross before)
            exit_reason: Reason for closing (optional)
            exit_fee: Total accumulated exit-leg commission (optional so the
                live-trading caller, which has no paper fee model, is
                unaffected; the paper engine always passes it)
            exit_kind: Structured close reason (Stage 0, 2026-08-07); optional
                so callers not yet updated are unaffected
            posted_margin: Remaining posted margin to write on close (Stage 0,
                2026-08-07); optional, schema-only in this task — no caller
                passes it yet
        """
        try:
            async with self.db.get_async_session() as session:
                values = {
                    "status": "CLOSED",
                    "exit_price": exit_price,
                    "realized_pnl": realized_pnl,
                    "exit_reason": exit_reason,
                    # A closed position has nothing left open; without this the
                    # sold quantity resurrected on restart (AUDIT H5).
                    "remaining_quantity": Decimal("0"),
                    "closed_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
                if exit_fee is not None:
                    values["exit_fee"] = exit_fee
                if exit_kind is not None:
                    values["exit_kind"] = exit_kind
                if posted_margin is not None:
                    values["posted_margin"] = posted_margin

                stmt = (
                    update(DBPosition)
                    .where(DBPosition.position_id == position_id)
                    .values(**values)
                )

                await session.execute(stmt)
                await session.commit()

                logger.info(
                    f"✓ Position {position_id} closed in database "
                    f"(net P&L: ${realized_pnl}, exit fee: {exit_fee})"
                )

        except Exception as e:
            logger.error(f"Failed to close position in database: {e}")
            raise

    async def record_reduction(
        self,
        position_id: UUID,
        remaining_quantity: Decimal,
        realized_pnl: Decimal,
        exit_fee: Decimal,
        current_price: Decimal,
        unrealized_pnl: Decimal,
        posted_margin: Optional[Decimal] = None,
    ):
        """
        Persist a partial exit (2026-08-04, AUDIT H5).

        Before this method existed, reduce_position updated memory only, so a
        restart resurrected the sold quantity and the close then manufactured
        P&L on it (one position overstated by exactly $1.7029).

        Args:
            position_id: Position UUID
            remaining_quantity: Quantity still open after this reduction
            realized_pnl: Position's ACCUMULATED realized P&L so far, net of
                the exit-leg commissions and the proportional entry fee
            exit_fee: Accumulated exit-leg commission so far
            current_price: Fill price of the reducing leg
            unrealized_pnl: Unrealized P&L on the remaining quantity
            posted_margin: Margin STILL posted after this reduction (Stage 0,
                2026-08-07). Optional and guarded exactly as `close` guards
                exit_fee, so a caller that has not been updated writes nothing
                rather than zeroing a live ledger entry.
        """
        try:
            async with self.db.get_async_session() as session:
                values = {
                    "remaining_quantity": remaining_quantity,
                    "realized_pnl": realized_pnl,
                    "exit_fee": exit_fee,
                    "current_price": current_price,
                    "unrealized_pnl": unrealized_pnl,
                    "updated_at": datetime.now(timezone.utc),
                }
                if posted_margin is not None:
                    values["posted_margin"] = posted_margin

                stmt = (
                    update(DBPosition)
                    .where(DBPosition.position_id == position_id)
                    .values(**values)
                )

                await session.execute(stmt)
                await session.commit()

                logger.info(
                    f"✓ Position {position_id} reduction persisted "
                    f"(remaining: {remaining_quantity}, net realized: ${realized_pnl})"
                )

        except Exception as e:
            logger.error(f"Failed to persist position reduction: {e}")
            raise

    async def record_scale_in(
        self,
        position_id: UUID,
        quantity: Decimal,
        entry_price: Decimal,
        remaining_quantity: Decimal,
        entry_fee: Decimal,
        current_price: Decimal,
        unrealized_pnl: Decimal,
        posted_margin: Optional[Decimal] = None,
    ):
        """
        Persist a scale-in (DCA averaging) — 2026-08-04.

        scale_in previously persisted only a price update, so the added
        quantity and re-averaged entry price were lost on restart (same
        defect class as AUDIT H5, opposite direction).

        Args:
            position_id: Position UUID
            quantity: New TOTAL position quantity
            entry_price: New weighted-average entry price
            remaining_quantity: Quantity open after the scale-in
            entry_fee: Accumulated entry-leg commission (open + scale-ins)
            current_price: Fill price of the scale-in leg
            unrealized_pnl: Updated unrealized P&L
            posted_margin: ACCUMULATED margin posted across the open leg and
                every scale-in (Stage 0, 2026-08-07). Optional and guarded as
                `close` guards exit_fee.
        """
        try:
            async with self.db.get_async_session() as session:
                values = {
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "cost_basis": entry_price * quantity,
                    "remaining_quantity": remaining_quantity,
                    "entry_fee": entry_fee,
                    "current_price": current_price,
                    "unrealized_pnl": unrealized_pnl,
                    "updated_at": datetime.now(timezone.utc),
                }
                if posted_margin is not None:
                    values["posted_margin"] = posted_margin

                stmt = (
                    update(DBPosition)
                    .where(DBPosition.position_id == position_id)
                    .values(**values)
                )

                await session.execute(stmt)
                await session.commit()

                logger.info(
                    f"✓ Position {position_id} scale-in persisted "
                    f"(qty: {quantity} @ avg {entry_price})"
                )

        except Exception as e:
            logger.error(f"Failed to persist position scale-in: {e}")
            raise

    async def get_by_id(self, position_id: UUID) -> Optional[DBPosition]:
        """Get position by ID from database"""
        try:
            async with self.db.get_async_session() as session:
                result = await session.execute(
                    select(DBPosition).where(DBPosition.position_id == position_id)
                )
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to get position from database: {e}")
            return None

    async def get_open_positions(
        self, portfolio_id: str = "paper_trading"
    ) -> List[DBPosition]:
        """Get all open positions for a portfolio"""
        try:
            async with self.db.get_async_session() as session:
                result = await session.execute(
                    select(DBPosition)
                    .where(DBPosition.portfolio_id == portfolio_id)
                    .where(DBPosition.status == "OPEN")
                )
                return result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to get open positions from database: {e}")
            return []

    async def get_closed_positions(
        self, portfolio_id: str = "paper_trading", limit: int = 50
    ) -> List[DBPosition]:
        """
        Get all closed positions from database for a portfolio

        Args:
            portfolio_id: Portfolio ID (default: paper_trading)
            limit: Maximum number of positions to return (default: 50)

        Returns:
            List of closed DBPosition objects, sorted by closed_at descending
        """
        try:
            async with self.db.get_async_session() as session:
                result = await session.execute(
                    select(DBPosition)
                    .where(DBPosition.portfolio_id == portfolio_id)
                    .where(DBPosition.status == "CLOSED")
                    .order_by(DBPosition.closed_at.desc())
                    .limit(limit)
                )
                positions = result.scalars().all()
                logger.info(
                    f"Retrieved {len(positions)} closed positions from database"
                )
                return positions
        except Exception as e:
            logger.error(f"Failed to get closed positions from database: {e}")
            return []


class TradeRepository:
    """
    Repository for Trade database operations

    Note: Trade logging is currently simplified.
    Full implementation would include order details, execution info, etc.
    """

    def __init__(self):
        """Initialize trade repository"""
        self.db = db_manager
        logger.info("TradeRepository initialized")

    async def log_trade(
        self,
        portfolio_id: str,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        commission: Decimal,
        *,
        position_id: Optional[
            UUID
        ] = None,  # accepted but unused (live schema lacks column)
        strategy: Optional[str] = None,
        signal_confidence: Optional[Decimal] = None,
        realized_pnl: Optional[Decimal] = None,
        order_type: str = "MARKET",  # accepted but unused
        action: Optional[str] = None,  # legacy kwarg alias for side
    ):
        """
        Log a trade to the live `trades` table.

        Schema alignment (2026-05-06): the ORM `DBTrade` model drifted from the
        actual DB columns (`action`/`order_type`/`total_cost`/`position_id`
        don't exist in DB; live columns are `side`/`total_value`/`metadata`).
        Inserts via the ORM silently failed and were swallowed by the prior
        try/except, leaving `trades` empty and Performance Analytics blank.
        This impl bypasses the broken ORM and writes the live schema directly
        with raw SQL so the GIGO chain breaks here.

        Args:
            portfolio_id: Portfolio ID
            symbol: Trading symbol
            side: 'BUY' / 'SELL' / 'LONG' / 'SHORT' (mapped to BUY/SELL)
            quantity: Trade quantity
            price: Execution price
            commission: Commission (persisted to `fee`)
            position_id: Accepted for caller compat; not persisted (no column)
            strategy: Optional strategy name (persisted to `strategy`)
            signal_confidence: Optional confidence 0..1 (persisted)
            realized_pnl: Optional realized P&L for close-side trades
                (entry-side trades pass None; persisted to `realized_pnl`).
                Added 2026-05-15: prior to this all rows had NULL realized_pnl
                because close callers had the value but never passed it.
                Since 2026-08-04 (AUDIT H7) the paper engine passes this NET
                of the leg's commission and the proportional entry fee; rows
                before that date hold gross price P&L.
            order_type: Accepted for caller compat; not persisted
            action: Legacy alias for `side`
        """
        try:
            from sqlalchemy import text
            from uuid import uuid4 as _uuid4

            effective_side = side or action
            if effective_side is None:
                raise ValueError("log_trade requires 'side' (or legacy 'action')")
            # Map LONG/SHORT → BUY/SELL for the DB CHECK constraint.
            side_norm = effective_side.upper()
            if side_norm in ("LONG",):
                side_norm = "BUY"
            elif side_norm in ("SHORT",):
                side_norm = "SELL"

            total_value = Decimal(price) * Decimal(quantity)
            metadata_json = {
                "order_type": order_type,
            }
            if position_id is not None:
                metadata_json["position_id"] = str(position_id)

            async with self.db.get_async_session() as session:
                await session.execute(
                    text(
                        """
                        INSERT INTO trades (
                            trade_id, portfolio_id, symbol, side,
                            quantity, price, total_value, fee, realized_pnl,
                            strategy, signal_confidence, executed_at, metadata
                        ) VALUES (
                            :trade_id, :portfolio_id, :symbol, :side,
                            :quantity, :price, :total_value, :fee, :realized_pnl,
                            :strategy, :signal_confidence, :executed_at,
                            CAST(:metadata AS jsonb)
                        )
                        """
                    ),
                    {
                        "trade_id": str(_uuid4()),
                        "portfolio_id": portfolio_id,
                        "symbol": symbol,
                        "side": side_norm,
                        "quantity": quantity,
                        "price": price,
                        "total_value": total_value,
                        "fee": commission,
                        "realized_pnl": realized_pnl,
                        "strategy": strategy,
                        "signal_confidence": signal_confidence,
                        # Live `executed_at` column is `timestamp without time
                        # zone`; asyncpg rejects tz-aware datetimes against it
                        # ("can't subtract offset-naive and offset-aware").
                        "executed_at": datetime.now(timezone.utc).replace(tzinfo=None),
                        "metadata": _json.dumps(metadata_json),
                    },
                )
                await session.commit()
                logger.info(
                    f"✓ Trade logged: {side_norm} {quantity} {symbol} @ ${price}"
                )

        except Exception as e:
            logger.error(f"Failed to log trade to database: {e}", exc_info=True)
            # Do not re-raise; trade logging failure must not break execution.


class PortfolioRepository:
    """
    Repository for Portfolio database operations
    """

    def __init__(self):
        """Initialize portfolio repository"""
        self.db = db_manager
        logger.info("PortfolioRepository initialized")

    async def get_or_create(
        self,
        portfolio_id: str = "paper_trading",
        name: str = "Paper Trading Portfolio",
        initial_balance: Optional[Decimal] = None,
    ) -> DBPortfolio:
        """
        Get existing portfolio or create if doesn't exist

        Args:
            portfolio_id: Portfolio identifier
            name: Portfolio name
            initial_balance: Initial balance for new portfolio. Defaults to the
                configured paper-trading balance (``PAPER_INITIAL_BALANCE``).
                The previous hardcoded $10,000 default is what wrote the stale
                `portfolios.initial_balance = 10000` row on 2026-04-27.

        Returns:
            Portfolio object
        """
        if initial_balance is None:
            initial_balance = Decimal(str(get_settings().paper_initial_balance))

        try:
            async with self.db.get_async_session() as session:
                # Try to get existing portfolio
                result = await session.execute(
                    select(DBPortfolio).where(DBPortfolio.portfolio_id == portfolio_id)
                )
                portfolio = result.scalar_one_or_none()

                if portfolio:
                    logger.info(f"Found existing portfolio: {portfolio_id}")
                    return portfolio

                # Create new portfolio
                portfolio = DBPortfolio(
                    portfolio_id=portfolio_id,
                    name=name,
                    initial_balance=initial_balance,
                    cash_balance=initial_balance,
                    trading_mode="PAPER",
                )

                session.add(portfolio)
                await session.commit()

                logger.info(f"✓ Created new portfolio in database: {portfolio_id}")
                return portfolio

        except Exception as e:
            logger.error(f"Failed to get/create portfolio: {e}")
            raise

    async def record_position_close(
        self,
        portfolio_id: str,
        cash_balance: Decimal,
        realized_pnl_delta: Decimal,
    ):
        """
        Persist a position close into the portfolio ledger (2026-08-04, H7).

        ACCUMULATES `realized_pnl` SQL-side (`realized_pnl = COALESCE(...) +
        delta`) instead of overwriting it with a caller-computed total. The
        previous write path passed `get_total_realized_pnl()` — a sum over
        IN-MEMORY closed positions — which resets on every restart, so
        `portfolios.realized_pnl` held exactly the last post-restart trade
        (observed: 3.0901) while the account was down ~$7 (AUDIT 6.2).

        Args:
            portfolio_id: Portfolio ID
            cash_balance: Current cash balance from the paper engine ledger
            realized_pnl_delta: THIS position's total net realized P&L
                (fees deducted, partial exits included) — a delta, not a total
        """
        try:
            async with self.db.get_async_session() as session:
                stmt = (
                    update(DBPortfolio)
                    .where(DBPortfolio.portfolio_id == portfolio_id)
                    .values(
                        cash_balance=cash_balance,
                        realized_pnl=func.coalesce(DBPortfolio.realized_pnl, 0)
                        + realized_pnl_delta,
                        updated_at=datetime.now(timezone.utc),
                    )
                )

                result = await session.execute(stmt)
                await session.commit()

                if result.rowcount == 0:
                    # A close against a missing portfolio row must not vanish.
                    raise RuntimeError(
                        f"record_position_close matched no portfolio row "
                        f"for '{portfolio_id}'"
                    )

                logger.info(
                    f"✓ Portfolio {portfolio_id} realized P&L accumulated "
                    f"by {realized_pnl_delta} (cash: {cash_balance})"
                )

        except Exception as e:
            logger.error(f"Failed to record position close on portfolio: {e}")
            raise

    async def update_balance(
        self, portfolio_id: str, cash_balance: Decimal, realized_pnl: Decimal = None
    ):
        """
        Update portfolio balance and P&L

        WARNING (2026-08-04): `realized_pnl` here OVERWRITES the stored value.
        Do not call this from position-close paths — use
        `record_position_close`, which accumulates. This method remains for
        explicit balance administration only.

        Args:
            portfolio_id: Portfolio ID
            cash_balance: New cash balance
            realized_pnl: Total realized P&L (optional)
        """
        try:
            async with self.db.get_async_session() as session:
                update_values = {
                    "cash_balance": cash_balance,
                    "updated_at": datetime.now(timezone.utc),
                }

                if realized_pnl is not None:
                    update_values["realized_pnl"] = realized_pnl

                stmt = (
                    update(DBPortfolio)
                    .where(DBPortfolio.portfolio_id == portfolio_id)
                    .values(**update_values)
                )

                await session.execute(stmt)
                await session.commit()

                logger.debug(f"Portfolio {portfolio_id} balance updated in database")

        except Exception as e:
            logger.error(f"Failed to update portfolio balance: {e}")
            raise


# Singleton instances
_position_repo: Optional[PositionRepository] = None
_trade_repo: Optional[TradeRepository] = None
_portfolio_repo: Optional[PortfolioRepository] = None


def get_position_repository() -> PositionRepository:
    """Get position repository singleton"""
    global _position_repo
    if _position_repo is None:
        _position_repo = PositionRepository()
    return _position_repo


def get_trade_repository() -> TradeRepository:
    """Get trade repository singleton"""
    global _trade_repo
    if _trade_repo is None:
        _trade_repo = TradeRepository()
    return _trade_repo


def get_portfolio_repository() -> PortfolioRepository:
    """Get portfolio repository singleton"""
    global _portfolio_repo
    if _portfolio_repo is None:
        _portfolio_repo = PortfolioRepository()
    return _portfolio_repo
