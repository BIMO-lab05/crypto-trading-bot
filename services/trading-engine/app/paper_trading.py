"""
Paper Trading Engine
Purpose: Simulate trading without real money
"""

import logging
from decimal import Decimal
from typing import Optional
from uuid import UUID
from app.config import get_settings
from app.models import Order, OrderCreate, OrderStatus, OrderSide, OrderType, PositionSide
from app.position_manager import get_position_manager
from app.risk_manager import get_risk_manager

logger = logging.getLogger(__name__)


class PaperTradingEngine:
    """
    Simulates trading without real money

    Features:
    1. Virtual account balance
    2. Simulated order execution
    3. Commission simulation
    4. Position tracking
    """

    def __init__(self):
        """Initialize paper trading engine"""
        self.settings = get_settings()
        self.balance = Decimal(str(self.settings.paper_initial_balance))
        self.initial_balance = self.balance
        self.commission_pct = Decimal(str(self.settings.paper_commission_pct / 100))
        self.position_manager = get_position_manager()
        self.risk_manager = get_risk_manager()

        logger.info("Paper Trading Engine initialized")
        logger.info(f"  Initial balance: ${self.balance}")
        logger.info(f"  Commission: {self.settings.paper_commission_pct}%")

    def get_balance(self) -> Decimal:
        """Get current account balance"""
        return self.balance

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
        self,
        order: OrderCreate,
        current_price: Decimal
    ) -> tuple[Order, Optional[str]]:
        """
        Execute a market order (paper trading simulation)

        Args:
            order: Order to execute
            current_price: Current market price

        Returns:
            Tuple of (executed_order, error_message)
        """
        logger.info(f"Executing paper market order: {order.side.value} {order.quantity} {order.symbol} @ {current_price}")

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
            bybit_order_id=f"PAPER_{order.symbol}_{order.side.value}"
        )

        # Handle BUY order
        if order.side == OrderSide.BUY:
            total_cost = order_value + commission

            # Check if sufficient balance
            if total_cost > self.balance:
                error_msg = f"Insufficient balance: need ${total_cost}, have ${self.balance}"
                logger.warning(error_msg)
                executed_order.status = OrderStatus.FAILED
                return executed_order, error_msg

            # Deduct from balance
            self.balance -= total_cost

            # Create LONG position
            position = self.position_manager.create_position(
                symbol=order.symbol,
                side=PositionSide.LONG,
                entry_price=current_price,
                quantity=order.quantity,
                strategy=order.strategy
            )

            executed_order.position_id = position.id

            logger.info(
                f"✓ BUY order filled: {order.quantity} {order.symbol} @ {current_price} | "
                f"Cost: ${order_value} + Commission: ${commission} = ${total_cost} | "
                f"Balance: ${self.balance}"
            )

        # Handle SELL order
        elif order.side == OrderSide.SELL:
            # Check if we have an open position to close
            open_positions = [
                pos for pos in self.position_manager.get_open_positions()
                if pos.symbol == order.symbol and pos.side == PositionSide.LONG
            ]

            if not open_positions:
                error_msg = f"No open LONG position for {order.symbol} to sell"
                logger.warning(error_msg)
                executed_order.status = OrderStatus.FAILED
                return executed_order, error_msg

            # Close the position
            position = open_positions[0]
            closed_position = self.position_manager.close_position(
                position.id,
                current_price,
                reason="Market sell order"
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

        return executed_order, None

    def can_open_position(self, symbol: str, quantity: Decimal, price: Decimal) -> tuple[bool, Optional[str]]:
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
            return False, f"Insufficient balance: need ${total_cost}, have ${self.balance}"

        # Check position limits
        open_positions = self.position_manager.get_open_positions()
        can_open, reason = self.risk_manager.check_position_limits(
            open_positions,
            self.get_total_equity()
        )

        if not can_open:
            return False, reason

        return True, None

    def get_performance_summary(self) -> dict:
        """Get performance summary"""
        total_equity = self.get_total_equity()
        total_pnl = total_equity - self.initial_balance
        roi = (total_pnl / self.initial_balance * 100) if self.initial_balance > 0 else 0

        closed_positions = self.position_manager.get_closed_positions()
        winning_trades = sum(1 for pos in closed_positions if pos.realized_pnl > 0)
        losing_trades = sum(1 for pos in closed_positions if pos.realized_pnl < 0)
        total_trades = len(closed_positions)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        return {
            "initial_balance": float(self.initial_balance),
            "current_balance": float(self.balance),
            "total_equity": float(total_equity),
            "total_pnl": float(total_pnl),
            "roi": round(float(roi), 2),
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 2),
            "open_positions": len(self.position_manager.get_open_positions())
        }


# Global paper trading engine instance
_paper_engine: Optional[PaperTradingEngine] = None


def get_paper_engine() -> PaperTradingEngine:
    """Get or create paper trading engine instance"""
    global _paper_engine
    if _paper_engine is None:
        _paper_engine = PaperTradingEngine()
    return _paper_engine
