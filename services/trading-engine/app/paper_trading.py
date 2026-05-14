"""
Paper Trading Engine
Purpose: Simulate trading without real money
Enhanced: Database persistence for trades and positions
"""

import asyncio
import logging
from decimal import Decimal
from typing import Optional
from app.config import get_settings
from app.models import (
    Order,
    OrderCreate,
    OrderStatus,
    OrderSide,
    PositionSide,
)
from app.position_manager import get_position_manager
from app.risk_manager import get_risk_manager
from app.repositories import get_trade_repository, get_portfolio_repository

logger = logging.getLogger(__name__)


def _trade_log_done(task: "asyncio.Task") -> None:
    """asyncio.Task done-callback: surface log_trade exceptions LOUDLY.

    Without this, fire-and-forget create_task() swallows coroutine errors —
    the GIGO chain that left `trades` empty for weeks despite a working
    log_trade() function.
    """
    try:
        exc = task.exception()
    except (asyncio.CancelledError, asyncio.InvalidStateError):
        return
    if exc is not None:
        logger.error("log_trade task failed: %s", exc, exc_info=exc)


def _spawn_trade_log(coro) -> None:
    """Schedule log_trade coro with error-visible done-callback."""
    task = asyncio.create_task(coro)
    task.add_done_callback(_trade_log_done)


class PaperTradingEngine:
    """
    Simulates trading without real money

    Features:
    1. Virtual account balance
    2. Simulated order execution
    3. Commission simulation
    4. Position tracking
    5. Balance sync with database positions on startup
    """

    def __init__(self):
        """Initialize paper trading engine with database persistence"""
        self.settings = get_settings()
        self.initial_balance = Decimal(str(self.settings.paper_initial_balance))
        self.balance = (
            self.initial_balance
        )  # Will be adjusted in sync_balance_with_positions
        self.commission_pct = Decimal(str(self.settings.paper_commission_pct / 100))
        self.position_manager = get_position_manager()
        self.risk_manager = get_risk_manager()

        # Database repositories for persistence
        self.trade_repo = get_trade_repository()
        self.portfolio_repo = get_portfolio_repository()

        logger.info("Paper Trading Engine initialized")
        logger.info(f"  Initial balance: ${self.initial_balance}")
        logger.info(f"  Commission: {self.settings.paper_commission_pct}%")
        logger.info("  Database persistence: ENABLED")

    def sync_balance_with_positions(self):
        """
        Sync cash balance with open positions loaded from database.
        Call this after positions are loaded from database to deduct their cost.
        """
        open_positions = self.position_manager.get_open_positions()
        if not open_positions:
            logger.info("No open positions to sync balance with")
            return

        # Calculate total cost of open positions (entry price * quantity + commission)
        total_position_cost = Decimal("0")
        for pos in open_positions:
            position_value = pos.entry_price * pos.quantity
            commission = position_value * self.commission_pct
            total_position_cost += position_value + commission

        # Adjust balance
        self.balance = self.initial_balance - total_position_cost

        logger.info(f"Balance synced with {len(open_positions)} open positions:")
        logger.info(f"  Total position cost: ${total_position_cost:.2f}")
        logger.info(f"  Adjusted balance: ${self.balance:.2f}")

    def get_balance(self) -> Decimal:
        """Get current account balance"""
        return self.balance

    def get_initial_balance(self) -> Decimal:
        """Starting equity used to compute returns / drawdown."""
        return self.initial_balance

    def get_total_equity(self) -> Decimal:
        """
        Get total equity (balance + unrealized P&L)
        """
        unrealized_pnl = self.position_manager.get_total_unrealized_pnl()
        return self.balance + unrealized_pnl

    def calculate_commission(self, order_value: Decimal) -> Decimal:
        """Calculate commission for an order"""
        return order_value * self.commission_pct

    async def execute_market_order(
        self, order: OrderCreate, current_price: Decimal
    ) -> tuple[Order, Optional[str]]:
        """
        Execute a market order (paper trading simulation)

        Args:
            order: Order to execute
            current_price: Current market price

        Returns:
            Tuple of (executed_order, error_message)
        """
        logger.info(
            f"Executing paper market order: {order.side.value} {order.quantity} {order.symbol} @ {current_price}"
        )

        # Calculate order value
        order_value = current_price * order.quantity

        # Calculate commission
        commission = self.calculate_commission(order_value)

        # Create order object
        executed_order = Order(
            **order.model_dump(),
            status=OrderStatus.FILLED,
            filled_price=current_price,
            filled_quantity=order.quantity,
            bybit_order_id=f"PAPER_{order.symbol}_{order.side.value}",
        )

        # Handle BUY order
        if order.side == OrderSide.BUY:
            # Check if we have an open SHORT position to close (2025-12-03)
            open_short_positions = [
                pos
                for pos in self.position_manager.get_open_positions()
                if pos.symbol == order.symbol and pos.side == PositionSide.SHORT
            ]

            if open_short_positions:
                # Close SHORT position
                position = open_short_positions[0]
                closed_position = self.position_manager.close_position(
                    position.id, current_price, reason="Market buy order (SHORT close)"
                )

                # Add proceeds to balance
                proceeds = order_value - commission
                self.balance += proceeds

                executed_order.position_id = closed_position.id

                logger.info(
                    f"✓ SHORT closed: {order.quantity} {order.symbol} @ {current_price} | "
                    f"Proceeds: ${proceeds} | P&L: ${closed_position.realized_pnl} | Balance: ${self.balance}"
                )

                _spawn_trade_log(
                    self.trade_repo.log_trade(
                        position_id=closed_position.id,
                        portfolio_id="paper_trading",
                        symbol=order.symbol,
                        side="BUY",
                        quantity=order.quantity,
                        price=current_price,
                        commission=commission,
                        strategy=order.strategy,
                        signal_confidence=order.entry_signal_confidence,
                    )
                )

                return executed_order, None

            # No SHORT position - open a LONG position (2025-12-18 FIX)
            # For leveraged LONG positions, only deduct margin (position_value / leverage) not full value
            leverage = Decimal(str(self.settings.default_leverage))
            margin_required = order_value / leverage
            total_cost = margin_required + commission

            # Check if sufficient balance
            if total_cost > self.balance:
                error_msg = (
                    f"Insufficient balance: need ${total_cost}, have ${self.balance}"
                )
                logger.warning(error_msg)
                executed_order.status = OrderStatus.FAILED
                return executed_order, error_msg

            # Deduct margin requirement from balance
            self.balance -= total_cost
            logger.debug(
                f"LONG margin calculation: order_value=${order_value}, leverage={leverage}x, margin=${margin_required}, commission=${commission}"
            )

            # Create LONG position
            position = self.position_manager.create_position(
                symbol=order.symbol,
                side=PositionSide.LONG,
                entry_price=current_price,
                quantity=order.quantity,
                strategy=order.strategy,
                # CRITICAL FIX 2025-12-07: Save entry signal confidence
                entry_signal_confidence=order.entry_signal_confidence,
            )

            executed_order.position_id = position.id

            logger.info(
                f"✓ LONG opened: {order.quantity} {order.symbol} @ {current_price} | "
                f"Position: ${order_value} | Margin: ${margin_required} ({leverage}x leverage) + Commission: ${commission} | "
                f"Balance: ${self.balance}"
            )

            # Log trade to database (async, errors surfaced via done-callback)
            _spawn_trade_log(
                self.trade_repo.log_trade(
                    position_id=position.id,
                    portfolio_id="paper_trading",
                    symbol=order.symbol,
                    side="BUY",
                    quantity=order.quantity,
                    price=current_price,
                    commission=commission,
                    strategy=order.strategy,
                    signal_confidence=order.entry_signal_confidence,
                )
            )

        # Handle SELL order
        elif order.side == OrderSide.SELL:
            # Check if we have an open LONG position to close
            open_long_positions = [
                pos
                for pos in self.position_manager.get_open_positions()
                if pos.symbol == order.symbol and pos.side == PositionSide.LONG
            ]

            if not open_long_positions:
                # No LONG position - open a SHORT position instead (2025-12-03)
                logger.info(
                    f"No LONG position for {order.symbol}, opening SHORT position"
                )

                # Deduct margin requirement from balance (2025-12-18 FIX)
                # For leveraged SHORT positions, only deduct margin (position_value / leverage) not full value
                leverage = Decimal(str(self.settings.default_leverage))
                margin_required = order_value / leverage
                self.balance -= margin_required + commission
                logger.debug(
                    f"SHORT margin calculation: order_value=${order_value}, leverage={leverage}x, margin=${margin_required}, commission=${commission}"
                )

                # Open SHORT position (same as LONG but with SHORT side)
                position = self.position_manager.create_position(
                    symbol=order.symbol,
                    side=PositionSide.SHORT,
                    entry_price=current_price,
                    quantity=order.quantity,
                    strategy="research_optimized",
                    # CRITICAL FIX 2025-12-07: Save entry signal confidence
                    entry_signal_confidence=order.entry_signal_confidence,
                )

                executed_order.position_id = position.id

                logger.info(
                    f"✓ SHORT opened: {order.quantity} {order.symbol} @ {current_price} | "
                    f"Position: ${order_value} | Margin: ${margin_required} ({leverage}x leverage) + Commission: ${commission} | "
                    f"Balance: ${self.balance}"
                )

                _spawn_trade_log(
                    self.trade_repo.log_trade(
                        position_id=position.id,
                        portfolio_id="paper_trading",
                        symbol=order.symbol,
                        side="SELL",
                        quantity=order.quantity,
                        price=current_price,
                        commission=commission,
                        strategy=order.strategy,
                        signal_confidence=order.entry_signal_confidence,
                    )
                )

                return executed_order, None

            # Close the LONG position
            position = open_long_positions[0]
            closed_position = self.position_manager.close_position(
                position.id, current_price, reason="Market sell order"
            )

            # Add proceeds to balance (minus commission)
            proceeds = order_value - commission
            self.balance += proceeds

            executed_order.position_id = closed_position.id

            logger.info(
                f"✓ SELL order filled: {order.quantity} {order.symbol} @ {current_price} | "
                f"Proceeds: ${order_value} - Commission: ${commission} = ${proceeds} | "
                f"P&L: ${closed_position.realized_pnl} | "
                f"Balance: ${self.balance}"
            )

            # Log trade to database (async, errors surfaced via done-callback)
            _spawn_trade_log(
                self.trade_repo.log_trade(
                    position_id=closed_position.id,
                    portfolio_id="paper_trading",
                    symbol=order.symbol,
                    side="SELL",
                    quantity=order.quantity,
                    price=current_price,
                    commission=commission,
                    strategy=order.strategy,
                    signal_confidence=order.entry_signal_confidence,
                )
            )

        return executed_order, None

    def can_open_position(
        self, symbol: str, quantity: Decimal, price: Decimal
    ) -> tuple[bool, Optional[str]]:
        """
        Check if we can open a new position

        Args:
            symbol: Trading symbol
            quantity: Position quantity
            price: Entry price

        Returns:
            Tuple of (can_open, reason if cannot)
        """
        # Calculate required capital
        order_value = quantity * price
        commission = self.calculate_commission(order_value)
        total_cost = order_value + commission

        # Check balance
        if total_cost > self.balance:
            return (
                False,
                f"Insufficient balance: need ${total_cost}, have ${self.balance}",
            )

        # Check position limits
        open_positions = self.position_manager.get_open_positions()
        can_open, reason = self.risk_manager.check_position_limits(
            open_positions, self.get_total_equity()
        )

        if not can_open:
            return False, reason

        return True, None

    def get_performance_summary(self) -> dict:
        """Get performance summary with accurate unrealized PnL"""
        # Get unrealized PnL from open positions
        unrealized_pnl = self.position_manager.get_total_unrealized_pnl()

        # Total equity = cash balance + unrealized PnL
        total_equity = self.balance + unrealized_pnl
        total_pnl = total_equity - self.initial_balance
        roi = (
            (total_pnl / self.initial_balance * 100) if self.initial_balance > 0 else 0
        )

        # Calculate realized PnL from closed positions
        closed_positions = self.position_manager.get_closed_positions()
        realized_pnl = sum(pos.realized_pnl for pos in closed_positions)
        winning_trades = sum(1 for pos in closed_positions if pos.realized_pnl > 0)
        losing_trades = sum(1 for pos in closed_positions if pos.realized_pnl < 0)
        total_trades = len(closed_positions)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        # Get open positions for exposure calculation
        open_positions = self.position_manager.get_open_positions()
        total_exposure = sum(
            float(pos.entry_price * pos.quantity) for pos in open_positions
        )

        return {
            "initial_balance": float(self.initial_balance),
            "current_balance": float(self.balance),
            "total_equity": float(total_equity),
            "total_exposure": float(total_exposure),
            "unrealized_pnl": float(unrealized_pnl),
            "realized_pnl": float(realized_pnl),
            "total_pnl": float(total_pnl),
            "roi": round(float(roi), 2),
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 2),
            "open_positions": len(open_positions),
        }


# Global paper trading engine instance
_paper_engine: Optional[PaperTradingEngine] = None


def get_paper_engine() -> PaperTradingEngine:
    """Get or create paper trading engine instance"""
    global _paper_engine
    if _paper_engine is None:
        _paper_engine = PaperTradingEngine()
    return _paper_engine
