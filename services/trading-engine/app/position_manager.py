"""
Position Manager
Purpose: Track and manage trading positions
Enhanced: Database persistence for positions

UPDATED 2025-11-29: Research-backed position management
- Added trailing stop support with ATR-based distance
- Added partial exit handling at multiple take profit levels
- Integrated with ATRStopCalculator for dynamic stop levels
"""

import logging
from typing import List, Optional, Dict, Tuple
from decimal import Decimal
from uuid import UUID
from datetime import datetime, timezone
from app.models import Position, PositionCreate, PositionStatus, PositionSide
from app.risk_manager import get_risk_manager
from app.repositories import get_position_repository, get_portfolio_repository
from app.atr_stops import get_atr_calculator, ATRStopCalculator

logger = logging.getLogger(__name__)


class PositionManager:
    """
    Manages trading positions

    Responsibilities:
    1. Track all open and closed positions
    2. Calculate P&L
    3. Check stop-loss and take-profit
    4. Update position prices
    """

    def __init__(self):
        """Initialize position manager with database persistence"""
        self.positions: dict[UUID, Position] = {}
        self.risk_manager = get_risk_manager()
        self.position_repo = get_position_repository()
        self.portfolio_repo = get_portfolio_repository()
        logger.info("PositionManager initialized with database persistence")

    def create_position(
        self,
        symbol: str,
        side: PositionSide,
        entry_price: Decimal,
        quantity: Decimal,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
        strategy: Optional[str] = None,
        take_profit_1: Optional[Decimal] = None,
        take_profit_2: Optional[Decimal] = None,
        take_profit_3: Optional[Decimal] = None,
        entry_signal_confidence: Optional[float] = None  # CRITICAL FIX 2025-12-05
    ) -> Position:
        """
        Create a new position

        Args:
            symbol: Trading symbol
            side: Position side (LONG/SHORT)
            entry_price: Entry price
            quantity: Position quantity
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price (final target)
            strategy: Strategy name
            take_profit_1: Optional TP1 - first partial exit target
            take_profit_2: Optional TP2 - second partial exit target
            take_profit_3: Optional TP3 - third partial exit target
            entry_signal_confidence: Optional entry signal confidence (0.0-1.0)

        Returns:
            Created position
        """
        # Calculate stop-loss and take-profit if not provided
        if stop_loss is None:
            stop_loss = self.risk_manager.calculate_stop_loss(entry_price, side)

        if take_profit is None:
            take_profit = self.risk_manager.calculate_take_profit(entry_price, side)

        # Auto-calculate TP1/TP2/TP3 if not provided but we have SL and TP
        # Based on ATR multiples: TP1 @ 0.8x, TP2 @ 1.3x, TP3 @ 2.0x
        if take_profit_1 is None and stop_loss and entry_price:
            risk_distance = abs(entry_price - stop_loss)
            if side == PositionSide.LONG:
                take_profit_1 = entry_price + (risk_distance * Decimal("0.8"))
                take_profit_2 = entry_price + (risk_distance * Decimal("1.3"))
                take_profit_3 = entry_price + (risk_distance * Decimal("2.0"))
            else:  # SHORT
                take_profit_1 = entry_price - (risk_distance * Decimal("0.8"))
                take_profit_2 = entry_price - (risk_distance * Decimal("1.3"))
                take_profit_3 = entry_price - (risk_distance * Decimal("2.0"))

        # Create position
        position = Position(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            current_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy=strategy,
            status=PositionStatus.OPEN,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            take_profit_3=take_profit_3,
            entry_signal_confidence=entry_signal_confidence  # CRITICAL FIX 2025-12-05
        )

        # Store position in memory
        self.positions[position.id] = position

        logger.info(
            f"✓ Position created: {position.id} | "
            f"{symbol} {side.value} {quantity} @ {entry_price} | "
            f"SL: {stop_loss} | TP: {take_profit}"
        )
        if take_profit_1:
            logger.info(
                f"  Partial TPs: TP1=${take_profit_1:.2f} | TP2=${take_profit_2:.2f} | TP3=${take_profit_3:.2f}"
            )

        # Persist to database (async, non-blocking)
        import asyncio
        try:
            asyncio.create_task(
                self.position_repo.create(position, portfolio_id="paper_trading")
            )
        except Exception as e:
            logger.warning(f"Failed to persist position to database: {e}")

        return position

    def get_position(self, position_id: UUID) -> Optional[Position]:
        """Get position by ID"""
        return self.positions.get(position_id)

    def get_all_positions(self) -> List[Position]:
        """Get all positions"""
        return list(self.positions.values())

    def get_open_positions(self) -> List[Position]:
        """Get all open positions"""
        return [pos for pos in self.positions.values() if pos.status == PositionStatus.OPEN]

    def update_positions_with_tp_levels(self) -> int:
        """
        Update existing positions with calculated TP1/TP2/TP3 levels

        For positions that don't have partial take profit levels set,
        calculate them based on the risk distance (entry to stop loss).

        Returns:
            Number of positions updated
        """
        updated = 0
        for position in self.positions.values():
            if position.status != PositionStatus.OPEN:
                continue

            # Skip if already has TP levels
            if position.take_profit_1 is not None:
                continue

            # Calculate TP levels based on risk distance
            if position.stop_loss and position.entry_price:
                risk_distance = abs(position.entry_price - position.stop_loss)

                if position.side == PositionSide.LONG:
                    position.take_profit_1 = position.entry_price + (risk_distance * Decimal("0.8"))
                    position.take_profit_2 = position.entry_price + (risk_distance * Decimal("1.3"))
                    position.take_profit_3 = position.entry_price + (risk_distance * Decimal("2.0"))
                else:  # SHORT
                    position.take_profit_1 = position.entry_price - (risk_distance * Decimal("0.8"))
                    position.take_profit_2 = position.entry_price - (risk_distance * Decimal("1.3"))
                    position.take_profit_3 = position.entry_price - (risk_distance * Decimal("2.0"))

                logger.info(
                    f"Updated {position.symbol} with TP levels: "
                    f"TP1=${position.take_profit_1:.2f}, TP2=${position.take_profit_2:.2f}, TP3=${position.take_profit_3:.2f}"
                )
                updated += 1

        logger.info(f"Updated {updated} positions with TP levels")
        return updated

    def get_closed_positions(self) -> List[Position]:
        """Get all closed positions"""
        return [pos for pos in self.positions.values() if pos.status == PositionStatus.CLOSED]

    def update_position_price(
        self,
        position_id: UUID,
        current_price: Decimal
    ) -> Position:
        """
        Update position with current price and recalculate P&L

        Args:
            position_id: Position ID
            current_price: Current market price

        Returns:
            Updated position
        """
        position = self.positions.get(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")

        # Update P&L
        position.update_pnl(current_price)

        logger.debug(
            f"Position {position_id} updated: "
            f"price={current_price}, unrealized_pnl={position.unrealized_pnl} "
            f"({position.pnl_percentage:+.2f}%)"
        )

        # Update price in database (async, non-blocking)
        import asyncio
        try:
            asyncio.create_task(
                self.position_repo.update_price(
                    position_id, current_price, position.unrealized_pnl
                )
            )
        except Exception as e:
            logger.warning(f"Failed to update position price in database: {e}")

        return position

    def check_position_exit(
        self,
        position_id: UUID,
        current_price: Decimal
    ) -> tuple[bool, Optional[str]]:
        """
        Check if position should be closed

        Args:
            position_id: Position ID
            current_price: Current market price

        Returns:
            Tuple of (should_close, reason)
        """
        position = self.positions.get(position_id)
        if not position:
            return False, "Position not found"

        if position.status != PositionStatus.OPEN:
            return False, "Position not open"

        return self.risk_manager.should_close_position(position, current_price)

    def close_position(
        self,
        position_id: UUID,
        close_price: Decimal,
        reason: Optional[str] = None
    ) -> Position:
        """
        Close a position

        Args:
            position_id: Position ID
            close_price: Closing price
            reason: Reason for closing

        Returns:
            Closed position
        """
        position = self.positions.get(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")

        if position.status != PositionStatus.OPEN:
            raise ValueError(f"Position {position_id} is not open")

        # FIX 2026-07-28: realize P&L on the REMAINING quantity only, and
        # ACCUMULATE into realized_pnl instead of overwriting it. Previously a
        # position that had taken partial exits (TP1/TP2) had its realized P&L
        # overwritten at close with a full-quantity mark — double counting the
        # already-exited quantity and corrupting daily-P&L / circuit breakers.
        remaining = (
            position.remaining_quantity
            if position.remaining_quantity is not None
            else position.quantity
        )
        if position.side == PositionSide.LONG:
            pnl_on_remaining = (close_price - position.entry_price) * remaining
        else:  # SHORT
            pnl_on_remaining = (position.entry_price - close_price) * remaining

        position.current_price = close_price
        position.realized_pnl += pnl_on_remaining
        position.unrealized_pnl = Decimal("0")
        position.remaining_quantity = Decimal("0")
        position.status = PositionStatus.CLOSED
        position.closed_at = datetime.now(timezone.utc)
        position.exit_price = close_price
        position.exit_reason = reason

        # Update risk manager daily P&L with THIS close's P&L only
        self.risk_manager.update_daily_pnl(pnl_on_remaining)

        logger.info(
            f"✓ Position closed: {position_id} | "
            f"{position.symbol} at {close_price} | "
            f"P&L: {position.realized_pnl} ({position.pnl_percentage:+.2f}%) | "
            f"Reason: {reason or 'Manual'}"
        )

        # Close position in database (async, non-blocking)
        import asyncio
        try:
            asyncio.create_task(
                self.position_repo.close(
                    position_id,
                    close_price,
                    position.realized_pnl,
                    exit_reason=reason
                )
            )

            # Update portfolio realized P&L only (2025-12-18 FIX, refixed 2026-05-01).
            # Audit 2026-05-01 found this branch was passing the literal
            # cash_balance=Decimal("100.00") on every close — overwriting the
            # portfolio's true cash balance to $100 each time a position closed,
            # corrupting the DB row that the paper engine reconciles against on
            # restart. The right owner of cash is PaperTradingEngine; the close
            # path here only knows realized PnL. Read current cash from the
            # paper engine and pass it through, so the DB stays consistent.
            total_realized_pnl = self.get_total_realized_pnl()
            try:
                from app.paper_trading import get_paper_engine
                _cash_now = get_paper_engine().get_balance()
            except Exception:
                # Best-effort: if the engine isn't available, skip the cash
                # write rather than overwrite with a garbage constant.
                _cash_now = None
            if _cash_now is not None:
                asyncio.create_task(
                    self.portfolio_repo.update_balance(
                        portfolio_id="paper_trading",
                        cash_balance=_cash_now,
                        realized_pnl=total_realized_pnl,
                    )
                )
            logger.info(f"Portfolio updated: total realized P&L = ${total_realized_pnl}")
        except Exception as e:
            logger.warning(f"Failed to close position in database: {e}")

        return position

    def reduce_position(
        self,
        position_id: UUID,
        quantity: Decimal,
        price: Decimal,
        realized_pnl: Decimal,
    ) -> Position:
        """
        Reduce an open position by a quantity (partial close). Added 2026-07-28.

        The caller (paper/live engine) is responsible for cash accounting;
        this method updates position state and daily P&L only.
        """
        position = self.positions.get(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")
        if position.status != PositionStatus.OPEN:
            raise ValueError(f"Position {position_id} is not open")

        remaining = (
            position.remaining_quantity
            if position.remaining_quantity is not None
            else position.quantity
        )
        if quantity >= remaining:
            raise ValueError(
                f"reduce_position quantity {quantity} >= remaining {remaining}; "
                f"use close_position for full closes"
            )

        position.remaining_quantity = remaining - quantity
        position.realized_pnl += realized_pnl
        position.update_pnl(price)

        self.risk_manager.update_daily_pnl(realized_pnl)

        logger.info(
            f"✓ Position reduced: {position_id} | {position.symbol} "
            f"-{quantity} @ {price} | Realized: {realized_pnl:+.4f} | "
            f"Remaining: {position.remaining_quantity}"
        )

        import asyncio
        try:
            asyncio.create_task(
                self.position_repo.update_price(
                    position_id, price, position.unrealized_pnl
                )
            )
        except Exception as e:
            logger.warning(f"Failed to persist position reduction: {e}")

        return position

    def scale_in(
        self,
        position_id: UUID,
        quantity: Decimal,
        price: Decimal,
    ) -> Position:
        """
        Add quantity to an open position at a new price (DCA averaging).
        Added 2026-07-28: previously DCA safety orders opened DUPLICATE
        positions with their own default stops instead of averaging in.

        Entry price becomes the weighted average of remaining + added quantity.
        The caller is responsible for cash accounting.
        """
        position = self.positions.get(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")
        if position.status != PositionStatus.OPEN:
            raise ValueError(f"Position {position_id} is not open")
        if quantity <= 0:
            raise ValueError("scale_in quantity must be positive")

        remaining = (
            position.remaining_quantity
            if position.remaining_quantity is not None
            else position.quantity
        )
        new_remaining = remaining + quantity
        position.entry_price = (
            (position.entry_price * remaining) + (price * quantity)
        ) / new_remaining
        position.quantity = position.quantity + quantity
        position.remaining_quantity = new_remaining
        position.update_pnl(price)

        logger.info(
            f"✓ Position scaled in: {position_id} | {position.symbol} "
            f"+{quantity} @ {price} | New avg entry: {position.entry_price:.6f} | "
            f"Remaining: {position.remaining_quantity}"
        )

        import asyncio
        try:
            asyncio.create_task(
                self.position_repo.update_price(
                    position_id, price, position.unrealized_pnl
                )
            )
        except Exception as e:
            logger.warning(f"Failed to persist position scale-in: {e}")

        return position

    def get_total_exposure(self) -> Decimal:
        """Calculate total exposure from open positions"""
        return sum(
            pos.entry_price * pos.quantity
            for pos in self.get_open_positions()
        )

    def get_total_unrealized_pnl(self) -> Decimal:
        """Calculate total unrealized P&L from open positions"""
        return sum(pos.unrealized_pnl for pos in self.get_open_positions())

    def get_total_realized_pnl(self) -> Decimal:
        """Calculate total realized P&L from closed positions"""
        return sum(pos.realized_pnl for pos in self.get_closed_positions())

    def get_position_count(self) -> dict:
        """Get position counts by status"""
        return {
            "total": len(self.positions),
            "open": len(self.get_open_positions()),
            "closed": len(self.get_closed_positions())
        }

    # ============================================================================
    # RESEARCH-BACKED: Trailing Stops and Partial Exits (2025-11-29)
    # ============================================================================

    def update_position_with_trailing(
        self,
        position_id: UUID,
        current_price: Decimal,
        atr_value: Optional[float] = None
    ) -> Tuple[Position, Optional[Dict]]:
        """
        Update position with trailing stop and check for partial exits

        This is the main method for managing open positions. It:
        1. Updates P&L
        2. Updates trailing stop if enabled
        3. Checks for partial exit triggers

        Args:
            position_id: Position ID
            current_price: Current market price
            atr_value: ATR value for trailing stop distance (optional)

        Returns:
            Tuple of (updated_position, partial_exit_info or None)
        """
        position = self.positions.get(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")

        # Update P&L
        position.update_pnl(current_price)

        partial_exit = None

        # Update trailing stop if enabled and ATR provided
        if atr_value and position.trailing_stop_enabled:
            atr_calc = get_atr_calculator()
            trail_distance = Decimal(str(atr_value * atr_calc.multipliers["trailing"]))

            if position.update_trailing_stop(current_price, trail_distance):
                logger.info(
                    f"Trailing stop updated: {position.symbol} -> {position.trailing_stop:.2f}"
                )

        # Check for partial exit
        partial_exit = position.check_partial_exit(current_price)

        if partial_exit:
            logger.info(
                f"Partial exit triggered: {position.symbol} {partial_exit['level']} - "
                f"Exit {partial_exit['exit_quantity']:.4f} ({partial_exit['exit_percentage']:.0f}%)"
            )

        return position, partial_exit

    def execute_partial_exit(
        self,
        position_id: UUID,
        exit_info: Dict,
        exit_price: Decimal
    ) -> Tuple[Position, Decimal]:
        """
        Execute a partial exit for a position

        Args:
            position_id: Position ID
            exit_info: Exit info from check_partial_exit()
            exit_price: Price at which to execute the exit

        Returns:
            Tuple of (updated_position, realized_pnl_from_exit)
        """
        position = self.positions.get(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")

        # Calculate realized P&L for this partial exit
        exit_quantity = exit_info["exit_quantity"]
        if position.side == PositionSide.LONG:
            partial_pnl = (exit_price - position.entry_price) * exit_quantity
        else:
            partial_pnl = (position.entry_price - exit_price) * exit_quantity

        # Apply the partial exit
        position.apply_partial_exit(exit_info, partial_pnl)

        logger.info(
            f"✓ Partial exit executed: {position.symbol} {exit_info['level']} | "
            f"Qty: {exit_quantity:.4f} @ {exit_price} | "
            f"P&L: {partial_pnl:+.2f} | "
            f"Remaining: {position.remaining_quantity:.4f}"
        )

        # Update risk manager with realized P&L
        self.risk_manager.update_daily_pnl(partial_pnl)

        return position, partial_pnl

    def check_all_exit_conditions(
        self,
        position_id: UUID,
        current_price: Decimal
    ) -> Tuple[bool, str, Optional[Dict]]:
        """
        Check all exit conditions for a position

        Order of checks:
        1. Stop loss (original)
        2. Trailing stop (if enabled)
        3. Partial exit (TP1, TP2, TP3)
        4. Full take profit (legacy)

        Args:
            position_id: Position ID
            current_price: Current market price

        Returns:
            Tuple of (should_exit, reason, exit_info_or_none)
        """
        position = self.positions.get(position_id)
        if not position:
            return False, "Position not found", None

        if position.status != PositionStatus.OPEN:
            return False, "Position not open", None

        # 1. Check stop loss
        if position.check_stop_loss(current_price):
            return True, "Stop loss triggered", None

        # 2. Check trailing stop
        if position.check_trailing_stop(current_price):
            return True, "Trailing stop triggered", None

        # 3. Check partial exits
        partial_exit = position.check_partial_exit(current_price)
        if partial_exit:
            if partial_exit["level"] == "TP3":
                return True, "TP3 - Full exit", partial_exit
            return False, f"{partial_exit['level']} - Partial exit", partial_exit

        # 4. Check legacy take profit
        if position.check_take_profit(current_price):
            return True, "Take profit triggered", None

        return False, "No exit conditions met", None

    def set_position_stops(
        self,
        position_id: UUID,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
        tp1: Optional[Decimal] = None,
        tp2: Optional[Decimal] = None,
        tp3: Optional[Decimal] = None,
        trailing_stop: Optional[Decimal] = None,
        enable_trailing: bool = False
    ) -> Position:
        """
        Set stop loss and take profit levels for a position

        Args:
            position_id: Position ID
            stop_loss: Stop loss price
            take_profit: Primary take profit price
            tp1: Take profit level 1 (1:1 R:R)
            tp2: Take profit level 2 (2:1 R:R)
            tp3: Take profit level 3 (3:1 R:R)
            trailing_stop: Initial trailing stop level
            enable_trailing: Whether to enable trailing stop

        Returns:
            Updated position
        """
        position = self.positions.get(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")

        if stop_loss:
            position.stop_loss = stop_loss
        if take_profit:
            position.take_profit = take_profit
        if tp1:
            position.take_profit_1 = tp1
        if tp2:
            position.take_profit_2 = tp2
        if tp3:
            position.take_profit_3 = tp3
        if trailing_stop:
            position.trailing_stop = trailing_stop
        position.trailing_stop_enabled = enable_trailing

        logger.info(
            f"Position stops updated: {position.symbol} | "
            f"SL: {stop_loss} | TP: {take_profit} | "
            f"TP1/2/3: {tp1}/{tp2}/{tp3} | "
            f"Trailing: {trailing_stop} ({'enabled' if enable_trailing else 'disabled'})"
        )

        return position

    def create_position_with_atr_stops(
        self,
        symbol: str,
        side: PositionSide,
        entry_price: Decimal,
        quantity: Decimal,
        atr_value: float,
        strategy: Optional[str] = None,
        entry_signal_confidence: Optional[float] = None  # CRITICAL FIX 2025-12-05
    ) -> Position:
        """
        Create a position with ATR-based stop levels

        This is the preferred method for creating positions as it:
        - Sets dynamic stops based on market volatility
        - Configures multiple take profit levels for partial exits
        - Prepares trailing stop (enabled after TP1)

        Args:
            symbol: Trading symbol
            side: Position side (LONG/SHORT)
            entry_price: Entry price
            quantity: Position quantity
            atr_value: Current ATR value
            strategy: Strategy name
            entry_signal_confidence: Optional entry signal confidence (0.0-1.0)

        Returns:
            Created position with all stop levels set
        """
        atr_calc = get_atr_calculator()
        stop_levels = atr_calc.calculate_stops(
            float(entry_price),
            atr_value,
            side.value
        )

        # Create position with ATR-based stops
        position = Position(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            current_price=entry_price,
            stop_loss=Decimal(str(stop_levels.stop_loss)),
            take_profit=Decimal(str(stop_levels.take_profit_2)),  # Legacy: use TP2
            take_profit_1=Decimal(str(stop_levels.take_profit_1)),
            take_profit_2=Decimal(str(stop_levels.take_profit_2)),
            take_profit_3=Decimal(str(stop_levels.take_profit_3)),
            trailing_stop=Decimal(str(stop_levels.trailing_stop)),
            trailing_stop_enabled=False,  # Enabled after TP1
            strategy=strategy,
            entry_signal_confidence=entry_signal_confidence,  # CRITICAL FIX 2025-12-05
            status=PositionStatus.OPEN
        )

        # Store position
        self.positions[position.id] = position

        logger.info(
            f"✓ Position created with ATR stops: {position.id} | "
            f"{symbol} {side.value} {quantity} @ {entry_price} | "
            f"SL: {stop_levels.stop_loss:.2f} | "
            f"TP1/2/3: {stop_levels.take_profit_1:.2f}/{stop_levels.take_profit_2:.2f}/{stop_levels.take_profit_3:.2f}"
        )

        # Persist to database
        import asyncio
        try:
            asyncio.create_task(
                self.position_repo.create(position, portfolio_id="paper_trading")
            )
        except Exception as e:
            logger.warning(f"Failed to persist position to database: {e}")

        return position

    async def load_positions_from_db(self) -> int:
        """
        Load open positions from database into memory at startup.

        Returns:
            Number of positions loaded
        """
        try:
            db_positions = await self.position_repo.get_open_positions()
            loaded_count = 0

            for db_pos in db_positions:
                # Convert DB position to in-memory Position model
                position = Position(
                    symbol=db_pos.symbol,
                    side=PositionSide(db_pos.side),
                    entry_price=Decimal(str(db_pos.entry_price)),
                    quantity=Decimal(str(db_pos.quantity)),
                    current_price=Decimal(str(db_pos.current_price or db_pos.entry_price)),
                    stop_loss=Decimal(str(db_pos.stop_loss)) if db_pos.stop_loss else None,
                    take_profit=Decimal(str(db_pos.take_profit)) if db_pos.take_profit else None,
                    strategy=db_pos.strategy,
                    status=PositionStatus.OPEN
                )
                # Use the DB position_id
                position.id = db_pos.position_id

                self.positions[position.id] = position
                loaded_count += 1
                logger.info(
                    f"Loaded position from DB: {db_pos.symbol} {db_pos.side} "
                    f"@ {db_pos.entry_price} (ID: {db_pos.position_id})"
                )

            logger.info(f"✅ Loaded {loaded_count} open positions from database")
            return loaded_count

        except Exception as e:
            logger.error(f"Failed to load positions from database: {e}")
            return 0


# Global position manager instance
_position_manager: Optional[PositionManager] = None


def get_position_manager() -> PositionManager:
    """Get or create position manager instance"""
    global _position_manager
    if _position_manager is None:
        _position_manager = PositionManager()
    return _position_manager
