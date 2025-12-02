"""
DCA Manager - Dollar Cost Averaging for Losing Positions
Research Source: Pionex, 3Commas, TradeSanta best practices (2025-12-02)

Purpose:
- Average down on losing positions to reduce break-even price
- Research shows DCA needs only 1.02% recovery after 5% drop (vs 4.2% for grid)
- Implements safety orders with configurable step percentages
- Limits maximum DCA layers to manage risk

Key Features:
- Configurable price deviation triggers (5%, 10%, 15%)
- Position size scaling per layer (1x, 1.5x, 2x)
- Maximum safety orders limit
- Dynamic take profit recalculation
- Integration with existing position manager
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime
from decimal import Decimal
from enum import Enum

logger = logging.getLogger(__name__)


class DCAStatus(Enum):
    """DCA position status"""
    INITIAL = "initial"           # First order, no DCA yet
    AVERAGING = "averaging"       # DCA orders placed
    MAX_LAYERS_REACHED = "max_layers_reached"  # No more DCA allowed
    RECOVERED = "recovered"       # Position recovered, DCA successful
    STOPPED_OUT = "stopped_out"   # Hit final stop loss


@dataclass
class DCAConfig:
    """
    DCA Configuration - Research-backed defaults

    Based on Pionex/3Commas/TradeSanta research:
    - 5% price deviation for first safety order
    - 1.5x-2x position scaling per layer
    - 3-5 maximum safety orders
    - Volume scale increases with each layer
    """
    # Enable/disable DCA
    enabled: bool = True

    # Price deviation triggers (% drop from average entry)
    safety_order_deviation_pct: List[float] = field(
        default_factory=lambda: [5.0, 10.0, 15.0, 20.0, 25.0]
    )

    # Position size multiplier for each safety order
    # Research: Increasing size on each layer (Martingale-lite)
    safety_order_volume_scale: List[float] = field(
        default_factory=lambda: [1.0, 1.5, 2.0, 2.5, 3.0]
    )

    # Maximum number of safety orders
    max_safety_orders: int = 5

    # Minimum time between DCA orders (seconds)
    min_time_between_orders: int = 300  # 5 minutes

    # Base safety order size as % of original position
    base_safety_order_pct: float = 100.0  # 100% = same size as original

    # Take profit recalculation
    recalculate_tp_on_dca: bool = True
    tp_after_dca_pct: float = 2.0  # 2% profit target after averaging

    # Risk limits
    max_total_position_pct: float = 10.0  # Max 10% of capital in single position
    stop_loss_after_max_dca_pct: float = 10.0  # 10% SL after max DCA orders


@dataclass
class DCAOrder:
    """Individual DCA/Safety order"""
    order_id: str
    layer: int  # 1 = first safety order, 2 = second, etc.
    price: float
    quantity: float
    deviation_pct: float  # Price deviation at time of order
    timestamp: datetime
    filled: bool = False
    fill_price: Optional[float] = None
    fill_time: Optional[datetime] = None


@dataclass
class DCAPosition:
    """
    DCA-enhanced position tracking

    Tracks original position plus all DCA/safety orders
    to calculate accurate average entry and break-even
    """
    symbol: str
    side: str  # LONG or SHORT
    original_entry_price: float
    original_quantity: float
    original_timestamp: datetime

    # Current state
    average_entry_price: float
    total_quantity: float
    total_cost: float

    # DCA tracking
    safety_orders: List[DCAOrder] = field(default_factory=list)
    current_layer: int = 0
    status: DCAStatus = DCAStatus.INITIAL

    # Targets
    current_take_profit: float = 0.0
    current_stop_loss: float = 0.0
    break_even_price: float = 0.0

    # Metadata
    last_dca_time: Optional[datetime] = None
    total_dca_orders: int = 0

    def add_safety_order(self, order: DCAOrder):
        """Add a safety order and recalculate averages"""
        self.safety_orders.append(order)
        self.current_layer = order.layer
        self.total_dca_orders += 1
        self.last_dca_time = order.timestamp

        if order.filled and order.fill_price:
            # Recalculate average entry
            order_cost = order.fill_price * order.quantity
            self.total_cost += order_cost
            self.total_quantity += order.quantity
            self.average_entry_price = self.total_cost / self.total_quantity
            self.break_even_price = self.average_entry_price

            logger.info(
                f"DCA Layer {order.layer} added for {self.symbol}: "
                f"New avg entry: ${self.average_entry_price:.4f}, "
                f"Total qty: {self.total_quantity:.6f}"
            )

    def get_unrealized_pnl_pct(self, current_price: float) -> float:
        """Calculate unrealized PnL percentage"""
        if self.side == "LONG":
            return ((current_price - self.average_entry_price) / self.average_entry_price) * 100
        else:
            return ((self.average_entry_price - current_price) / self.average_entry_price) * 100


class DCAManager:
    """
    DCA Manager - Implements Dollar Cost Averaging strategy

    Research-backed implementation from:
    - Pionex: DCA needs only 1.02% recovery after 5% drop
    - 3Commas: Safety orders with volume scaling
    - TradeSanta: Recalculates TP with each new order

    Usage:
        dca_manager = DCAManager(config)

        # Check if position needs DCA
        if dca_manager.should_add_safety_order(position, current_price):
            order = dca_manager.create_safety_order(position, current_price)
            # Execute order...

        # After order filled
        dca_manager.process_filled_order(position, order)
    """

    def __init__(self, config: Optional[DCAConfig] = None):
        """Initialize DCA Manager"""
        self.config = config or DCAConfig()
        self.positions: Dict[str, DCAPosition] = {}

        logger.info(
            f"DCAManager initialized: enabled={self.config.enabled}, "
            f"max_layers={self.config.max_safety_orders}, "
            f"deviations={self.config.safety_order_deviation_pct}"
        )

    def create_dca_position(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        take_profit: float,
        stop_loss: float
    ) -> DCAPosition:
        """
        Create a new DCA-tracked position

        Args:
            symbol: Trading symbol
            side: LONG or SHORT
            entry_price: Initial entry price
            quantity: Initial quantity
            take_profit: Initial take profit
            stop_loss: Initial stop loss

        Returns:
            DCAPosition object
        """
        position = DCAPosition(
            symbol=symbol,
            side=side,
            original_entry_price=entry_price,
            original_quantity=quantity,
            original_timestamp=datetime.now(),
            average_entry_price=entry_price,
            total_quantity=quantity,
            total_cost=entry_price * quantity,
            current_take_profit=take_profit,
            current_stop_loss=stop_loss,
            break_even_price=entry_price
        )

        self.positions[symbol] = position
        logger.info(
            f"DCA position created for {symbol}: "
            f"entry=${entry_price:.4f}, qty={quantity:.6f}"
        )

        return position

    def should_add_safety_order(
        self,
        symbol: str,
        current_price: float
    ) -> bool:
        """
        Check if a safety order should be placed

        Args:
            symbol: Trading symbol
            current_price: Current market price

        Returns:
            True if safety order should be placed
        """
        if not self.config.enabled:
            return False

        position = self.positions.get(symbol)
        if not position:
            return False

        # Check if max layers reached
        if position.current_layer >= self.config.max_safety_orders:
            if position.status != DCAStatus.MAX_LAYERS_REACHED:
                position.status = DCAStatus.MAX_LAYERS_REACHED
                logger.warning(f"DCA max layers reached for {symbol}")
            return False

        # Check minimum time between orders
        if position.last_dca_time:
            elapsed = (datetime.now() - position.last_dca_time).total_seconds()
            if elapsed < self.config.min_time_between_orders:
                return False

        # Calculate current deviation from average entry
        unrealized_pnl_pct = position.get_unrealized_pnl_pct(current_price)

        # For LONG, we want to add when price drops (negative PnL)
        # For SHORT, we want to add when price rises (negative PnL)
        if unrealized_pnl_pct >= 0:
            return False  # Position is in profit, no DCA needed

        loss_pct = abs(unrealized_pnl_pct)
        next_layer = position.current_layer + 1

        # Check if loss exceeds threshold for next layer
        if next_layer <= len(self.config.safety_order_deviation_pct):
            threshold = self.config.safety_order_deviation_pct[next_layer - 1]
            if loss_pct >= threshold:
                logger.info(
                    f"DCA trigger for {symbol}: loss={loss_pct:.2f}% >= "
                    f"threshold={threshold}% (layer {next_layer})"
                )
                return True

        return False

    def calculate_safety_order_size(
        self,
        position: DCAPosition,
        capital: float
    ) -> float:
        """
        Calculate safety order size based on layer and config

        Args:
            position: Current DCA position
            capital: Available capital

        Returns:
            Quantity for safety order
        """
        next_layer = position.current_layer + 1

        # Get volume scale for this layer
        if next_layer <= len(self.config.safety_order_volume_scale):
            volume_scale = self.config.safety_order_volume_scale[next_layer - 1]
        else:
            volume_scale = self.config.safety_order_volume_scale[-1]

        # Base size is percentage of original position
        base_quantity = position.original_quantity * (self.config.base_safety_order_pct / 100)

        # Apply volume scale
        safety_quantity = base_quantity * volume_scale

        # Check max position limit
        max_position_value = capital * (self.config.max_total_position_pct / 100)
        current_position_value = position.total_cost
        remaining_room = max_position_value - current_position_value

        if remaining_room <= 0:
            logger.warning(f"Max position limit reached for {position.symbol}")
            return 0.0

        # Adjust quantity if it would exceed limit
        safety_value = safety_quantity * position.average_entry_price
        if safety_value > remaining_room:
            safety_quantity = remaining_room / position.average_entry_price
            logger.info(f"Safety order size reduced to fit position limit")

        return safety_quantity

    def create_safety_order(
        self,
        symbol: str,
        current_price: float,
        capital: float
    ) -> Optional[DCAOrder]:
        """
        Create a safety order for the position

        Args:
            symbol: Trading symbol
            current_price: Current market price
            capital: Available capital

        Returns:
            DCAOrder if created, None otherwise
        """
        position = self.positions.get(symbol)
        if not position:
            return None

        quantity = self.calculate_safety_order_size(position, capital)
        if quantity <= 0:
            return None

        next_layer = position.current_layer + 1
        deviation = position.get_unrealized_pnl_pct(current_price)

        order = DCAOrder(
            order_id=f"DCA_{symbol}_{next_layer}_{int(datetime.now().timestamp())}",
            layer=next_layer,
            price=current_price,
            quantity=quantity,
            deviation_pct=abs(deviation),
            timestamp=datetime.now()
        )

        logger.info(
            f"DCA safety order created for {symbol}: "
            f"layer={next_layer}, price=${current_price:.4f}, "
            f"qty={quantity:.6f}, deviation={abs(deviation):.2f}%"
        )

        return order

    def process_filled_order(
        self,
        symbol: str,
        order: DCAOrder,
        fill_price: float
    ) -> Optional[Dict]:
        """
        Process a filled safety order and update position

        Args:
            symbol: Trading symbol
            order: The DCA order that was filled
            fill_price: Actual fill price

        Returns:
            Dict with new TP/SL levels if recalculated
        """
        position = self.positions.get(symbol)
        if not position:
            return None

        # Update order
        order.filled = True
        order.fill_price = fill_price
        order.fill_time = datetime.now()

        # Add to position
        position.add_safety_order(order)
        position.status = DCAStatus.AVERAGING

        result = {
            "average_entry": position.average_entry_price,
            "total_quantity": position.total_quantity,
            "layer": order.layer,
            "break_even": position.break_even_price
        }

        # Recalculate take profit if enabled
        if self.config.recalculate_tp_on_dca:
            if position.side == "LONG":
                new_tp = position.average_entry_price * (1 + self.config.tp_after_dca_pct / 100)
            else:
                new_tp = position.average_entry_price * (1 - self.config.tp_after_dca_pct / 100)

            position.current_take_profit = new_tp
            result["new_take_profit"] = new_tp

            logger.info(
                f"DCA TP recalculated for {symbol}: "
                f"new avg=${position.average_entry_price:.4f}, "
                f"new TP=${new_tp:.4f} ({self.config.tp_after_dca_pct}%)"
            )

        # Update stop loss after max DCA
        if position.current_layer >= self.config.max_safety_orders:
            if position.side == "LONG":
                new_sl = position.average_entry_price * (1 - self.config.stop_loss_after_max_dca_pct / 100)
            else:
                new_sl = position.average_entry_price * (1 + self.config.stop_loss_after_max_dca_pct / 100)

            position.current_stop_loss = new_sl
            result["new_stop_loss"] = new_sl

            logger.warning(
                f"Max DCA reached for {symbol}: "
                f"new SL=${new_sl:.4f} ({self.config.stop_loss_after_max_dca_pct}%)"
            )

        return result

    def get_position_status(self, symbol: str) -> Optional[Dict]:
        """Get current DCA position status"""
        position = self.positions.get(symbol)
        if not position:
            return None

        return {
            "symbol": symbol,
            "side": position.side,
            "status": position.status.value,
            "original_entry": position.original_entry_price,
            "average_entry": position.average_entry_price,
            "total_quantity": position.total_quantity,
            "total_cost": position.total_cost,
            "break_even": position.break_even_price,
            "current_layer": position.current_layer,
            "max_layers": self.config.max_safety_orders,
            "current_tp": position.current_take_profit,
            "current_sl": position.current_stop_loss,
            "safety_orders": len(position.safety_orders)
        }

    def remove_position(self, symbol: str):
        """Remove a position from DCA tracking"""
        if symbol in self.positions:
            del self.positions[symbol]
            logger.info(f"DCA position removed for {symbol}")


# Global instance
_dca_manager: Optional[DCAManager] = None


def get_dca_manager() -> DCAManager:
    """Get or create DCA manager instance"""
    global _dca_manager
    if _dca_manager is None:
        _dca_manager = DCAManager()
    return _dca_manager


def reset_dca_manager():
    """Reset DCA manager (for testing)"""
    global _dca_manager
    _dca_manager = None
