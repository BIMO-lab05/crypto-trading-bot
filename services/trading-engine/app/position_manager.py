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
from app.models import Position, PositionStatus, PositionSide
from app.models.enums import ExitKind
from app.risk_manager import get_risk_manager
from app.repositories import get_position_repository, get_portfolio_repository
from app.atr_stops import get_atr_calculator


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """
    Normalise a DB timestamp to timezone-aware UTC.

    `positions.opened_at` is `timestamp without time zone`, so SQLAlchemy hands
    back a naive datetime. Comparing that against `datetime.now(timezone.utc)`
    -- which the max-hold check and the balance reconciliation both do --
    raises TypeError. Values are stored as UTC, so attach UTC rather than
    assuming the container's local zone.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


logger = logging.getLogger(__name__)


def _persist_done(task) -> None:
    """asyncio.Task done-callback: surface persistence failures LOUDLY.

    Fire-and-forget create_task() swallows coroutine exceptions unless a
    done-callback re-raises them into the log — the same GIGO chain that left
    `trades` empty for weeks (see paper_trading._trade_log_done).
    """
    import asyncio

    try:
        exc = task.exception()
    except (asyncio.CancelledError, asyncio.InvalidStateError):
        return
    if exc is not None:
        logger.error("position persistence task failed: %s", exc, exc_info=exc)


def _spawn_persist(coro, what: str) -> None:
    """Schedule a persistence coroutine with an error-visible done-callback.

    Scheduling itself can fail when no event loop is running (sync callers in
    tests); that is logged and tolerated — matching the pre-existing contract
    of every persistence call in this module — but a scheduled task that
    FAILS is always logged as an error by the callback above.
    """
    import asyncio

    try:
        task = asyncio.create_task(coro)
        task.add_done_callback(_persist_done)
    except Exception as e:
        coro.close()
        logger.warning(f"Failed to schedule persistence ({what}): {e}")


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
        # Fee ledgers per position (2026-08-04, AUDIT H7). The in-memory
        # Position model has no fee fields, so commissions are tracked here
        # and persisted to positions.entry_fee / positions.exit_fee; they are
        # reloaded from the DB on restart (load_positions_from_db).
        self._entry_fees: dict[UUID, Decimal] = {}
        self._exit_fees: dict[UUID, Decimal] = {}
        # How much of each position's entry fee has already been charged to a
        # closed leg (2026-08-06, review I16). Not a persisted column; it is
        # reconstructed on reload (see load_positions_from_db).
        self._entry_fees_consumed: dict[UUID, Decimal] = {}
        logger.info("PositionManager initialized with database persistence")

    def _consume_entry_fee(self, position: Position, quantity: Decimal) -> Decimal:
        """Entry commission attributable to `quantity`, marked as consumed.

        Attribution spreads the still-UNCONSUMED entry fee over the REMAINING
        quantity. It used to divide the whole entry fee by position.quantity,
        which scale_in increments — so whenever a scale-in followed a partial
        exit, part of the entry fee had already left the cash balance but was
        never charged to any leg's reported P&L, and the two ledgers diverged
        (review I16).

        Call exactly once per exit leg, BEFORE remaining_quantity is reduced.
        A leg that takes the whole remainder is handed the exact residual
        rather than a computed share, so conservation is exact and not subject
        to Decimal division rounding.
        """
        entry_fee = self._entry_fees.get(position.id, Decimal("0"))
        consumed = self._entry_fees_consumed.get(position.id, Decimal("0"))
        unconsumed = entry_fee - consumed
        remaining = (
            position.remaining_quantity
            if position.remaining_quantity is not None
            else position.quantity
        )
        if unconsumed <= 0 or remaining <= 0 or quantity <= 0:
            return Decimal("0")

        if quantity >= remaining:
            portion = unconsumed
        else:
            portion = unconsumed * quantity / remaining

        self._entry_fees_consumed[position.id] = consumed + portion
        return portion

    def unconsumed_entry_fee(self, position_id: UUID) -> Decimal:
        """Entry commission debited at open that no closed leg has absorbed yet.

        Stage 0 fix round (2026-08-08). The cash ledger debits the WHOLE entry
        fee at open, while realized_pnl nets only the CONSUMED portion — so the
        unconsumed remainder is the part still owed against the persisted cash
        figure. `_open_position_cost` reads this instead of recomputing
        entry_price*qty*commission_pct from the CURRENT rate, which was the same
        defect class as the leverage flip: change PAPER_COMMISSION_PCT and every
        restart mis-deducts for positions opened at the old rate.

        Returns 0 for an unknown position — a position with no ledger entry
        posted no fee through this manager.
        """
        fee = self._entry_fees.get(position_id, Decimal("0"))
        consumed = self._entry_fees_consumed.get(position_id, Decimal("0"))
        remainder = fee - consumed
        return remainder if remainder > 0 else Decimal("0")

    def consume_posted_margin(self, position_id: UUID, quantity: Decimal) -> Decimal:
        """Margin attributable to `quantity`, released from the position.

        Stage 0 (2026-08-07). Mirrors `_consume_entry_fee`: spread the still-
        posted margin over the REMAINING quantity, and hand a leg that takes
        the whole remainder the exact residual rather than a computed share,
        so conservation is exact and not subject to Decimal rounding.

        MUST be called BEFORE close_position/reduce_position mutate
        remaining_quantity — those methods set it to 0 / decrement it.

        Public (not underscore-prefixed) because the cash ledger lives in
        PaperTradingEngine, not here: reduce_position's docstring states that
        'the caller is responsible for cash accounting'.
        """
        position = self.positions.get(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")

        posted = position.posted_margin or Decimal("0")
        remaining = (
            position.remaining_quantity
            if position.remaining_quantity is not None
            else position.quantity
        )
        if posted <= 0 or remaining <= 0 or quantity <= 0:
            return Decimal("0")

        if quantity >= remaining:
            portion = posted
        else:
            portion = posted * quantity / remaining

        position.posted_margin = posted - portion
        return portion

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
        entry_signal_confidence: Optional[float] = None,  # CRITICAL FIX 2025-12-05
        entry_fee: Decimal = Decimal("0"),  # AUDIT H7 (2026-08-04)
        posted_margin: Decimal = Decimal("0"),  # Stage 0 (2026-08-07)
        leverage: Decimal = Decimal("1"),
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
            entry_fee: Commission charged on the opening leg; deducted from
                net realized P&L proportionally as quantity is closed
            posted_margin: Dollar margin the caller actually debited from cash
                for this leg (Stage 0, 2026-08-07). Consumed proportionally by
                consume_posted_margin as quantity is closed; it — not the
                global settings.default_leverage — is what the close leg
                credits back.
            leverage: Leverage in force when this position opened. Audit only;
                no cash arithmetic reads it. Stored so a position opened at 10x
                is still identifiable after DEFAULT_LEVERAGE changes.

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
            entry_signal_confidence=entry_signal_confidence,  # CRITICAL FIX 2025-12-05
            posted_margin=posted_margin,
            leverage=leverage,
        )

        # Store position in memory
        self.positions[position.id] = position
        self._entry_fees[position.id] = entry_fee
        self._exit_fees[position.id] = Decimal("0")
        self._entry_fees_consumed[position.id] = Decimal("0")

        logger.info(
            f"✓ Position created: {position.id} | "
            f"{symbol} {side.value} {quantity} @ {entry_price} | "
            f"SL: {stop_loss} | TP: {take_profit} | "
            f"Entry fee: {entry_fee} | Margin: {posted_margin} ({leverage}x)"
        )
        if take_profit_1:
            logger.info(
                f"  Partial TPs: TP1=${take_profit_1:.2f} | TP2=${take_profit_2:.2f} | TP3=${take_profit_3:.2f}"
            )

        # Persist to database (async, non-blocking)
        _spawn_persist(
            self.position_repo.create(
                position, portfolio_id="paper_trading", entry_fee=entry_fee
            ),
            "position create",
        )

        return position

    def get_position(self, position_id: UUID) -> Optional[Position]:
        """Get position by ID"""
        return self.positions.get(position_id)

    def get_all_positions(self) -> List[Position]:
        """Get all positions"""
        return list(self.positions.values())

    def get_open_positions(self) -> List[Position]:
        """Get all open positions"""
        return [
            pos for pos in self.positions.values() if pos.status == PositionStatus.OPEN
        ]

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
                    position.take_profit_1 = position.entry_price + (
                        risk_distance * Decimal("0.8")
                    )
                    position.take_profit_2 = position.entry_price + (
                        risk_distance * Decimal("1.3")
                    )
                    position.take_profit_3 = position.entry_price + (
                        risk_distance * Decimal("2.0")
                    )
                else:  # SHORT
                    position.take_profit_1 = position.entry_price - (
                        risk_distance * Decimal("0.8")
                    )
                    position.take_profit_2 = position.entry_price - (
                        risk_distance * Decimal("1.3")
                    )
                    position.take_profit_3 = position.entry_price - (
                        risk_distance * Decimal("2.0")
                    )

                logger.info(
                    f"Updated {position.symbol} with TP levels: "
                    f"TP1=${position.take_profit_1:.2f}, TP2=${position.take_profit_2:.2f}, TP3=${position.take_profit_3:.2f}"
                )
                updated += 1

        logger.info(f"Updated {updated} positions with TP levels")
        return updated

    def get_closed_positions(self) -> List[Position]:
        """Get all closed positions"""
        return [
            pos
            for pos in self.positions.values()
            if pos.status == PositionStatus.CLOSED
        ]

    def update_position_price(
        self, position_id: UUID, current_price: Decimal
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
        self, position_id: UUID, current_price: Decimal
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
        reason: Optional[str] = None,
        close_commission: Decimal = Decimal("0"),
        exit_kind: Optional[ExitKind] = None,
    ) -> Position:
        """
        Close a position

        Args:
            position_id: Position ID
            close_price: Closing price
            reason: Reason for closing (prose, API-visible via
                TradeHistoryResponse; unchanged by this parameter)
            close_commission: Commission charged on this closing leg. The
                paper engine always passes it; callers without a fee model
                (live path) default to 0.
            exit_kind: Structured close reason (Stage 0, 2026-08-07) — a
                second, additive channel alongside `reason`. Full closes
                only; None for legacy callers and partial exits.

        Returns:
            Closed position (realized_pnl NET of entry + exit commissions)
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
        #
        # FIX 2026-08-04 (AUDIT H7): realized P&L is NET of commissions — this
        # closing leg's commission plus the not-yet-accrued portion of the
        # entry fee. The cash ledger always subtracted fees; the persisted and
        # reported P&L did not, so every DB row and dashboard overstated.
        remaining = (
            position.remaining_quantity
            if position.remaining_quantity is not None
            else position.quantity
        )
        if position.side == PositionSide.LONG:
            pnl_on_remaining = (close_price - position.entry_price) * remaining
        else:  # SHORT
            pnl_on_remaining = (position.entry_price - close_price) * remaining

        entry_fee_portion = self._consume_entry_fee(position, remaining)
        net_close_pnl = pnl_on_remaining - close_commission - entry_fee_portion

        position.current_price = close_price
        position.realized_pnl += net_close_pnl
        position.unrealized_pnl = Decimal("0")
        position.remaining_quantity = Decimal("0")
        # Stage 0 (2026-08-07): a closed position has no margin posted. The
        # caller has already consumed it via consume_posted_margin (which is
        # why that call MUST precede this one); this is belt-and-braces for a
        # caller with no cash ledger, e.g. live_trading.close_position.
        position.posted_margin = Decimal("0")
        position.status = PositionStatus.CLOSED
        position.closed_at = datetime.now(timezone.utc)
        position.exit_price = close_price
        position.exit_reason = reason
        position.exit_kind = exit_kind

        total_exit_fee = (
            self._exit_fees.get(position_id, Decimal("0")) + close_commission
        )
        self._exit_fees[position_id] = total_exit_fee

        # Update risk manager daily P&L with THIS close's net P&L only
        self.risk_manager.update_daily_pnl(net_close_pnl)

        logger.info(
            f"✓ Position closed: {position_id} | "
            f"{position.symbol} at {close_price} | "
            f"Net P&L: {position.realized_pnl} ({position.pnl_percentage:+.2f}%) | "
            f"Fees (entry/exit): {self._entry_fees.get(position_id, Decimal('0'))}"
            f"/{total_exit_fee} | Reason: {reason or 'Manual'} | "
            f"ExitKind: {exit_kind.value if exit_kind else 'None'}"
        )

        # Close position in database (async, non-blocking)
        _spawn_persist(
            self.position_repo.close(
                position_id,
                close_price,
                position.realized_pnl,
                exit_reason=reason,
                exit_fee=total_exit_fee,
                posted_margin=Decimal("0"),
                exit_kind=exit_kind.value if exit_kind else None,
            ),
            "position close",
        )

        # Portfolio ledger (2025-12-18 FIX, refixed 2026-05-01, refixed
        # 2026-08-04 per AUDIT 6.2/H7): cash is owned by PaperTradingEngine
        # and passed through; realized P&L is ACCUMULATED SQL-side with this
        # position's total net P&L as the delta. The previous code wrote
        # get_total_realized_pnl() — a sum over in-memory closed positions,
        # which resets on restart — so portfolios.realized_pnl held exactly
        # the last post-restart trade instead of the account's history.
        _cash_now = None
        try:
            from app.paper_trading import get_paper_engine

            _cash_now = get_paper_engine().get_balance()
        except Exception as e:
            logger.error(
                "Could not read cash balance from paper engine; portfolio "
                f"ledger NOT updated for close of {position_id}: {e}"
            )
        if _cash_now is not None:
            _spawn_persist(
                self.portfolio_repo.record_position_close(
                    portfolio_id="paper_trading",
                    cash_balance=_cash_now,
                    realized_pnl_delta=position.realized_pnl,
                ),
                "portfolio close ledger",
            )

        return position

    def reduce_position(
        self,
        position_id: UUID,
        quantity: Decimal,
        price: Decimal,
        realized_pnl: Decimal,
        close_commission: Decimal = Decimal("0"),
    ) -> Position:
        """
        Reduce an open position by a quantity (partial close). Added 2026-07-28.

        The caller (paper/live engine) is responsible for cash accounting;
        this method updates position state and daily P&L.

        FIX 2026-08-04 (AUDIT H5 + H7): previously this persisted only a
        price update — neither the reduced quantity nor the incremental
        realized P&L reached the DB, so a restart resurrected the sold
        quantity and the eventual close manufactured P&L on it (one position
        overstated by exactly $1.7029). Now the reduced remaining_quantity,
        the accumulated NET realized P&L (this leg's gross price P&L minus
        its commission minus the proportional entry fee) and the accumulated
        exit fee are persisted on every reduction.

        Args:
            position_id: Position ID
            quantity: Quantity to close (must be < remaining)
            price: Fill price of the reducing leg
            realized_pnl: GROSS price P&L for this leg ((exit-entry)×qty,
                sign per side) — fees are netted here, not by the caller
            close_commission: Commission charged on this reducing leg
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

        entry_fee_portion = self._consume_entry_fee(position, quantity)
        net_leg_pnl = realized_pnl - close_commission - entry_fee_portion

        position.remaining_quantity = remaining - quantity
        position.realized_pnl += net_leg_pnl
        position.update_pnl(price)

        total_exit_fee = (
            self._exit_fees.get(position_id, Decimal("0")) + close_commission
        )
        self._exit_fees[position_id] = total_exit_fee

        self.risk_manager.update_daily_pnl(net_leg_pnl)

        logger.info(
            f"✓ Position reduced: {position_id} | {position.symbol} "
            f"-{quantity} @ {price} | Net realized: {net_leg_pnl:+.4f} "
            f"(gross {realized_pnl:+.4f}, fee {close_commission}, "
            f"entry-fee portion {entry_fee_portion:.8f}) | "
            f"Remaining: {position.remaining_quantity}"
        )

        _spawn_persist(
            self.position_repo.record_reduction(
                position_id,
                remaining_quantity=position.remaining_quantity,
                realized_pnl=position.realized_pnl,
                exit_fee=total_exit_fee,
                current_price=price,
                unrealized_pnl=position.unrealized_pnl,
                posted_margin=position.posted_margin,
            ),
            "position reduction",
        )

        return position

    def scale_in(
        self,
        position_id: UUID,
        quantity: Decimal,
        price: Decimal,
        entry_fee: Decimal = Decimal("0"),
        posted_margin: Decimal = Decimal("0"),
    ) -> Position:
        """
        Add quantity to an open position at a new price (DCA averaging).
        Added 2026-07-28: previously DCA safety orders opened DUPLICATE
        positions with their own default stops instead of averaging in.

        Entry price becomes the weighted average of remaining + added quantity.
        The caller is responsible for cash accounting.

        FIX 2026-08-04: the new quantity, weighted entry price, remaining
        quantity and accumulated entry fee are persisted (previously only a
        price update was written — the scale-in vanished on restart, the
        mirror image of AUDIT H5).

        Args:
            entry_fee: Commission charged on this scale-in leg; accumulates
                into the position's entry fee.
            posted_margin: Dollar margin debited from cash for THIS leg (Stage
                0, 2026-08-07); accumulates onto position.posted_margin. This
                is why margin is stored as dollars and not as a leverage ratio:
                this method rewrites entry_price to a weighted average, so a
                single stored ratio could not reconcile legs opened at
                different leverage. A summed dollar amount can.
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

        total_entry_fee = self._entry_fees.get(position_id, Decimal("0")) + entry_fee
        self._entry_fees[position_id] = total_entry_fee
        position.posted_margin = (
            position.posted_margin or Decimal("0")
        ) + posted_margin

        # Stage 0 fix round (2026-08-08): re-blend the recorded leverage.
        # Leaving it at the FIRST leg's value made the row say 10x when the
        # blend across legs was ~3.19x, and broke the reconciliation
        # `entry_price * remaining / leverage == posted_margin` that migration
        # 008's own backfill uses — anyone auditing a scaled-in row got the
        # wrong answer.
        #
        # Derived FROM posted_margin, never the reverse: posted_margin stays
        # authoritative and no cash path reads this. Reconstructing margin from
        # a stored ratio is what 008's header warns against; this is the
        # opposite direction and leaves that guarantee intact.
        #
        # Invariant under partial exits: consume_posted_margin scales margin and
        # remaining quantity by the same factor, so the ratio does not drift and
        # only a scale-in needs to recompute it.
        if position.posted_margin > 0:
            position.leverage = (
                position.entry_price * position.remaining_quantity
            ) / position.posted_margin

        logger.info(
            f"✓ Position scaled in: {position_id} | {position.symbol} "
            f"+{quantity} @ {price} | New avg entry: {position.entry_price:.6f} | "
            f"Remaining: {position.remaining_quantity} | "
            f"Entry fee total: {total_entry_fee} | "
            f"Margin total: {position.posted_margin}"
        )

        _spawn_persist(
            self.position_repo.record_scale_in(
                position_id,
                quantity=position.quantity,
                entry_price=position.entry_price,
                remaining_quantity=position.remaining_quantity,
                entry_fee=total_entry_fee,
                current_price=price,
                unrealized_pnl=position.unrealized_pnl,
                posted_margin=position.posted_margin,
                leverage=position.leverage,
            ),
            "position scale-in",
        )

        return position

    def get_total_exposure(self) -> Decimal:
        """Calculate total exposure from open positions"""
        return sum(pos.entry_price * pos.quantity for pos in self.get_open_positions())

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
            "closed": len(self.get_closed_positions()),
        }

    # ============================================================================
    # RESEARCH-BACKED: Trailing Stops and Partial Exits (2025-11-29)
    # ============================================================================

    def update_position_with_trailing(
        self,
        position_id: UUID,
        current_price: Decimal,
        atr_value: Optional[float] = None,
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

    # execute_partial_exit was REMOVED 2026-08-06. It persisted nothing and
    # charged no commission — the exact AUDIT H5 defect, left standing beside
    # its own fix. It had no callers: reduce_position (via
    # PaperTradingEngine.execute_market_order) is the partial-exit path, and it
    # persists the reduced remainder, the incremental net P&L and both fee
    # legs. auto_trader._execute_partial_exit already routes there.

    def check_all_exit_conditions(
        self, position_id: UUID, current_price: Decimal
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
        enable_trailing: bool = False,
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

        # Stage 0 (2026-08-07): persist. This method used to be memory-only,
        # so load_positions_from_db re-read the create-time risk-manager
        # default and every post-fill refinement vanished on restart.
        _spawn_persist(
            self.position_repo.update_stops(
                position_id,
                stop_loss=stop_loss,
                take_profit=take_profit,
            ),
            "position stops update",
        )

        return position

    # create_position_with_atr_stops was REMOVED 2026-08-06. It dropped the
    # entry commission entirely (never populated _entry_fees, and persisted
    # the row without entry_fee) — the exact AUDIT H7 defect, left standing
    # beside its own fix, under a docstring calling itself "the preferred
    # method for creating positions". It had no callers. Use create_position,
    # which carries entry_fee; pass ATR-derived stop_loss / take_profit_1..3
    # from app.atr_stops.get_atr_calculator().calculate_stops() at the call
    # site if ATR stops are wanted.

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
                    current_price=Decimal(
                        str(db_pos.current_price or db_pos.entry_price)
                    ),
                    stop_loss=Decimal(str(db_pos.stop_loss))
                    if db_pos.stop_loss
                    else None,
                    take_profit=Decimal(str(db_pos.take_profit))
                    if db_pos.take_profit
                    else None,
                    strategy=db_pos.strategy,
                    status=PositionStatus.OPEN,
                    # Restore the real open time. Omitting it let the model's
                    # `default_factory=now()` win, which handed every position a
                    # fresh 48h max-hold window on each restart -- a position
                    # could be held forever as long as the service restarted
                    # inside each window (the 185h SOLUSDT failure mode). It is
                    # also the reference point the paper engine uses to decide
                    # which positions post-date the last persisted cash balance.
                    opened_at=_as_utc(db_pos.opened_at),
                    realized_pnl=Decimal(str(db_pos.realized_pnl or 0)),
                    # Stage 0: restore the posted margin so a restart credits
                    # back what was actually posted. 008 made the column
                    # NOT NULL DEFAULT 0, so the `is not None` arm below is
                    # only a guard against reading a pre-008 database — an
                    # un-backfilled row presents as 0, which the check further
                    # down reports as an error.
                    posted_margin=Decimal(str(db_pos.posted_margin))
                    if db_pos.posted_margin is not None
                    else Decimal("0"),
                    leverage=Decimal(str(db_pos.leverage))
                    if db_pos.leverage is not None
                    else Decimal("1"),
                )
                # Use the DB position_id
                position.id = db_pos.position_id

                # FIX 2026-08-04 (AUDIT H5): restore the persisted remaining
                # quantity. Omitting it let Position.__init__ default it to
                # the FULL quantity, resurrecting partially-sold quantity on
                # every restart (position 59's close P&L was overstated by
                # exactly $1.7029 this way).
                #
                # Unlike posted_margin, this column is still NULLABLE: 007 added
                # it without NOT NULL and backfilled existing rows, and 008 did
                # not change that. So a NULL means either 007 never ran against
                # this database or a writer inserted the row without the column
                # (no current writer does — PositionRepository.create always
                # sets it). Either way the fallback re-inflates the position to
                # full quantity, so say so loudly rather than silently.
                if db_pos.remaining_quantity is not None:
                    position.remaining_quantity = Decimal(
                        str(db_pos.remaining_quantity)
                    )
                else:
                    logger.error(
                        f"positions.remaining_quantity is NULL for "
                        f"{db_pos.position_id} — migration 007 not applied, or "
                        f"the row was written without it. Falling back to full "
                        f"quantity {db_pos.quantity}; any prior partial exits "
                        f"on this position are LOST."
                    )

                # Stage 0 (2026-08-07): migration 008 made this column
                # NOT NULL DEFAULT 0, so an un-backfilled row reads 0, not NULL —
                # a NULL check would never fire. Zero margin on an OPEN position
                # is unreachable by design (open posts > 0; a partial close leaves
                # a positive remainder; a full close zeroes it only while setting
                # status=CLOSED), so it means either 008's backfill missed this row
                # or the margin ledger has a defect. Either way the next close
                # credits NO margin back — say so.
                if (position.posted_margin or Decimal("0")) <= 0:
                    logger.error(
                        f"positions.posted_margin is 0 on OPEN position "
                        f"{db_pos.position_id} ({db_pos.symbol}) — 008 backfill "
                        f"missed it, or the margin ledger is broken. Closing this "
                        f"position will credit NO margin back to cash."
                    )

                # Restore fee ledgers (AUDIT H7) so net-P&L math survives
                # restarts. Columns are NOT NULL DEFAULT 0 as of migration 007.
                self._entry_fees[position.id] = Decimal(str(db_pos.entry_fee or 0))
                self._exit_fees[position.id] = Decimal(str(db_pos.exit_fee or 0))

                # Consumed entry fee (review I16) has no persisted column, and
                # is not derivable from the three stored scalars because it
                # depends on leg ORDER. Reconstruct it from the quantity
                # already exited: exact whenever the entry fee per unit was
                # uniform — i.e. no scale-in intervened between partial exits,
                # the common case — and otherwise degrading to the pre-I16
                # attribution rather than double-charging the remainder.
                qty_total = Decimal(str(db_pos.quantity))
                exited = qty_total - position.remaining_quantity
                if qty_total > 0 and exited > 0:
                    self._entry_fees_consumed[position.id] = (
                        self._entry_fees[position.id] * exited / qty_total
                    )
                else:
                    self._entry_fees_consumed[position.id] = Decimal("0")

                self.positions[position.id] = position
                loaded_count += 1
                logger.info(
                    f"Loaded position from DB: {db_pos.symbol} {db_pos.side} "
                    f"@ {db_pos.entry_price} (ID: {db_pos.position_id}, "
                    f"remaining: {position.remaining_quantity})"
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
