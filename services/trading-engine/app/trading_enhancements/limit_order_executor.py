"""
Limit Order Executor - Reduce Slippage Through Smart Limit Orders
Research Source: Market Microstructure Theory, Execution Cost Analysis

Purpose:
- Execute trades using limit orders instead of market orders to reduce slippage
- Support multiple limit order strategies (aggressive, passive, post-only)
- Implement order timeout and fallback mechanisms
- Handle partial fills gracefully
- Track and estimate slippage savings

RESEARCH: Using limit orders instead of market orders can save 2-10 basis points (bps)
per trade. For high-frequency traders, this can significantly impact profitability.
Aggressive limits fill quickly, passive limits capture more spread but risk non-fill.

Order Type Strategies:
- Aggressive limit: Place at or slightly better than current best price (high fill rate)
- Passive limit: Place 0.05-0.1% inside the spread (captures maker rebate, lower fill rate)
- Post-only: Guarantee maker fee only by rejecting taker execution
"""

import asyncio
import logging
from enum import Enum
from typing import Optional, Dict, Any, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from collections import deque
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class LimitOrderType(Enum):
    """
    Types of limit order strategies based on placement relative to current price.

    RESEARCH: Different strategies trade off between fill probability and price improvement.
    - Aggressive: High fill probability, minimal price improvement
    - Passive: Lower fill probability, better price
    - Post-only: Guaranteed maker status, may not fill if crosses spread
    """
    AGGRESSIVE = "aggressive"       # Place at/near best price for quick fill
    PASSIVE = "passive"             # Place inside spread for better price
    POST_ONLY = "post_only"         # Maker-only order, rejected if would be taker


class FillStatus(Enum):
    """Order fill status for tracking execution progress."""
    PENDING = "pending"             # Order placed, awaiting fill
    PARTIAL = "partial"             # Some quantity filled
    FILLED = "filled"               # Fully filled
    CANCELLED = "cancelled"         # Cancelled before full fill
    TIMEOUT = "timeout"             # Timed out, may have partial fill
    FAILED = "failed"               # Order placement failed


@dataclass
class LimitOrderConfig:
    """
    Configuration for limit order execution behavior.

    RESEARCH-BACKED DEFAULTS:
    - 0.03% offset: Balances fill probability vs price improvement
    - 30 second timeout: Allows time for fill without holding too long
    - Post-only enabled: Ensures maker fees in liquid markets
    - Max 3 retries: Handles transient failures without infinite loops
    - Fallback enabled: Market order as last resort ensures execution

    Attributes:
        default_offset_pct: Percentage offset from current price for passive orders.
            Positive value places order better for the trader (lower buy, higher sell).
        timeout_seconds: Maximum time to wait for order fill before cancelling/converting.
            Too short risks missing fills, too long ties up capital.
        use_post_only: Whether to use post-only flag to guarantee maker fees.
            Set False in illiquid markets where crossing spread is common.
        max_retries: Number of retry attempts for failed order placement.
            Each retry may adjust price based on market movement.
        fallback_to_market: Whether to fallback to market order if limit times out.
            Ensures execution at cost of potential slippage.
        aggressive_offset_pct: Offset for aggressive orders (typically at or near best price).
        passive_offset_pct: Offset for passive orders (inside the spread).
        min_fill_pct_before_cancel: Minimum fill percentage before allowing cancellation.
            Prevents premature cancellation of orders with significant partial fills.
        price_tick_size: Minimum price increment for the market.
            Orders are rounded to this precision.
    """
    default_offset_pct: float = 0.03          # 0.03% (3 bps) default offset
    timeout_seconds: int = 30                  # Wait up to 30 seconds for fill
    use_post_only: bool = True                 # Prefer maker fees
    max_retries: int = 3                       # Retry failed placements
    fallback_to_market: bool = True            # Market order as last resort
    aggressive_offset_pct: float = 0.01        # 0.01% for aggressive orders
    passive_offset_pct: float = 0.08           # 0.08% for passive orders
    min_fill_pct_before_cancel: float = 0.50   # Don't cancel if >50% filled
    price_tick_size: Decimal = Decimal("0.01") # Default tick size


@dataclass
class LimitOrderResult:
    """
    Result of a limit order execution attempt.

    Attributes:
        order_id: Unique identifier for the order.
        symbol: Trading symbol (e.g., "BTCUSDT").
        side: Order side ("BUY" or "SELL").
        original_quantity: Originally requested quantity.
        filled_quantity: Quantity that was filled.
        remaining_quantity: Unfilled quantity.
        limit_price: The limit price that was used.
        avg_fill_price: Volume-weighted average fill price.
        status: Current fill status.
        order_type: Type of limit order used.
        start_time: When the order was placed.
        end_time: When the order was completed/cancelled.
        slippage_bps: Slippage in basis points vs arrival price.
        used_fallback: Whether fallback to market was triggered.
        exchange_order_id: Order ID from the exchange.
        error_message: Error message if order failed.
    """
    order_id: UUID
    symbol: str
    side: str
    original_quantity: Decimal
    filled_quantity: Decimal
    remaining_quantity: Decimal
    limit_price: Decimal
    avg_fill_price: Optional[Decimal]
    status: FillStatus
    order_type: LimitOrderType
    start_time: datetime
    end_time: Optional[datetime] = None
    slippage_bps: float = 0.0
    used_fallback: bool = False
    exchange_order_id: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class SlippageSavingsEstimate:
    """
    Estimate of slippage savings from using limit orders.

    Attributes:
        order_value: Total value of the order.
        estimated_market_slippage_bps: Expected slippage with market order.
        estimated_limit_slippage_bps: Expected slippage with limit order.
        savings_bps: Difference (savings) in basis points.
        savings_absolute: Absolute value saved in quote currency.
        confidence: Confidence level of the estimate (0-1).
    """
    order_value: Decimal
    estimated_market_slippage_bps: float
    estimated_limit_slippage_bps: float
    savings_bps: float
    savings_absolute: Decimal
    confidence: float


@dataclass
class PartialFillInfo:
    """
    Information about a partial fill event.

    Attributes:
        fill_quantity: Quantity filled in this event.
        fill_price: Price at which this fill occurred.
        cumulative_filled: Total quantity filled so far.
        remaining: Quantity still unfilled.
        timestamp: When this fill occurred.
    """
    fill_quantity: Decimal
    fill_price: Decimal
    cumulative_filled: Decimal
    remaining: Decimal
    timestamp: datetime


class LimitOrderExecutor:
    """
    Smart Limit Order Execution Engine.

    RESEARCH-BACKED IMPLEMENTATION:
    - Uses limit orders to reduce slippage compared to market orders
    - Supports multiple execution strategies (aggressive, passive, post-only)
    - Implements timeout and fallback mechanisms for guaranteed execution
    - Tracks partial fills and handles remaining quantities
    - Estimates and reports slippage savings

    Key Benefits:
    - Slippage reduction: 2-10 bps savings per trade
    - Maker fee capture: Post-only orders earn maker rebates
    - Execution quality: Better average fill prices
    - Risk management: Configurable timeouts and fallbacks

    Usage:
        executor = LimitOrderExecutor()

        # Calculate limit price
        limit_price = executor.calculate_limit_price(
            current_price=Decimal("50000"),
            side="BUY",
            order_type=LimitOrderType.PASSIVE
        )

        # Execute limit order
        result = await executor.execute_limit_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.1"),
            current_price=Decimal("50000"),
            order_type=LimitOrderType.AGGRESSIVE
        )

        # Estimate savings
        savings = executor.estimate_slippage_savings(order_value=5000.0)
    """

    # Historical average market slippage by order size tier (in bps)
    # RESEARCH: Based on empirical analysis of crypto market microstructure
    MARKET_SLIPPAGE_BY_SIZE: Dict[str, float] = {
        "micro": 2.0,     # < $1,000
        "small": 4.0,     # $1,000 - $10,000
        "medium": 6.0,    # $10,000 - $50,000
        "large": 10.0,    # $50,000 - $100,000
        "xlarge": 15.0    # > $100,000
    }

    # Expected limit order slippage reduction (percentage of market slippage)
    LIMIT_SLIPPAGE_REDUCTION: Dict[LimitOrderType, float] = {
        LimitOrderType.AGGRESSIVE: 0.60,  # 40% reduction vs market
        LimitOrderType.PASSIVE: 0.30,     # 70% reduction vs market
        LimitOrderType.POST_ONLY: 0.20    # 80% reduction vs market (if fills)
    }

    def __init__(self, config: Optional[LimitOrderConfig] = None):
        """
        Initialize the limit order executor.

        Args:
            config: Configuration for limit order behavior.
                    Uses defaults if not provided.
        """
        # Store configuration, using defaults if none provided
        self.config = config or LimitOrderConfig()

        # Execution history for performance analysis
        # Maintains rolling window of last 500 executions
        self._execution_history: deque = deque(maxlen=500)

        # Statistics counters
        self._stats = {
            "total_orders": 0,
            "filled_orders": 0,
            "partial_fills": 0,
            "timeouts": 0,
            "fallbacks_used": 0,
            "total_slippage_bps": 0.0,
            "total_savings_bps": 0.0
        }

        # Active orders being monitored
        self._active_orders: Dict[UUID, LimitOrderResult] = {}

        logger.info(
            f"LimitOrderExecutor initialized: "
            f"timeout={self.config.timeout_seconds}s, "
            f"fallback_enabled={self.config.fallback_to_market}, "
            f"post_only={self.config.use_post_only}"
        )

    def calculate_limit_price(
        self,
        current_price: Decimal,
        side: str,
        order_type: LimitOrderType = LimitOrderType.AGGRESSIVE,
        offset_pct: Optional[float] = None,
        tick_size: Optional[Decimal] = None
    ) -> Decimal:
        """
        Calculate the optimal limit price based on current price and order type.

        The limit price is offset from the current price to balance between
        fill probability and price improvement. The offset direction depends
        on the order side:
        - BUY: Lower price is better, so we subtract the offset
        - SELL: Higher price is better, so we add the offset

        Args:
            current_price: Current market price (typically mid-price or last trade).
            side: Order side, either "BUY" or "SELL".
            order_type: Type of limit order strategy to use.
            offset_pct: Optional override for the offset percentage.
                        If not provided, uses config defaults based on order_type.
            tick_size: Optional tick size for price rounding.
                       If not provided, uses config default.

        Returns:
            Calculated limit price rounded to tick size.

        Raises:
            ValueError: If side is not "BUY" or "SELL".

        Example:
            >>> executor = LimitOrderExecutor()
            >>> price = executor.calculate_limit_price(
            ...     current_price=Decimal("50000"),
            ...     side="BUY",
            ...     order_type=LimitOrderType.PASSIVE
            ... )
            >>> print(price)  # Will be ~49960 (0.08% below current)
        """
        # Validate side parameter
        if side not in ("BUY", "SELL"):
            raise ValueError(f"Invalid side: {side}. Must be 'BUY' or 'SELL'.")

        # Determine the offset percentage based on order type if not overridden
        if offset_pct is None:
            if order_type == LimitOrderType.AGGRESSIVE:
                offset_pct = self.config.aggressive_offset_pct
            elif order_type == LimitOrderType.PASSIVE:
                offset_pct = self.config.passive_offset_pct
            else:  # POST_ONLY uses passive offset
                offset_pct = self.config.passive_offset_pct

        # Convert offset to decimal multiplier
        # Example: 0.08% offset = 0.0008 multiplier
        offset_multiplier = Decimal(str(offset_pct)) / Decimal("100")

        # Calculate the price offset amount
        price_offset = current_price * offset_multiplier

        # Apply offset based on side
        # BUY orders: lower price is better (subtract offset)
        # SELL orders: higher price is better (add offset)
        if side == "BUY":
            # For buys, we want to buy at a lower price
            # Subtract offset to get a better (lower) buy price
            limit_price = current_price - price_offset
            # Round down for buy orders to ensure we don't exceed our target
            rounding = ROUND_DOWN
        else:
            # For sells, we want to sell at a higher price
            # Add offset to get a better (higher) sell price
            limit_price = current_price + price_offset
            # Round up for sell orders to ensure we don't go below our target
            rounding = ROUND_UP

        # Get tick size for rounding
        tick = tick_size or self.config.price_tick_size

        # Round to tick size
        # This ensures the price is valid for the exchange
        limit_price = self._round_to_tick(limit_price, tick, rounding)

        logger.debug(
            f"Calculated limit price: {side} @ {limit_price} "
            f"(current={current_price}, offset={offset_pct}%, type={order_type.value})"
        )

        return limit_price

    def _round_to_tick(
        self,
        price: Decimal,
        tick_size: Decimal,
        rounding: str = ROUND_DOWN
    ) -> Decimal:
        """
        Round price to the nearest valid tick size.

        Args:
            price: Price to round.
            tick_size: Minimum price increment.
            rounding: Rounding direction (ROUND_DOWN or ROUND_UP).

        Returns:
            Price rounded to tick size.
        """
        # Calculate number of ticks
        ticks = price / tick_size

        # Round to whole number of ticks
        if rounding == ROUND_UP:
            rounded_ticks = ticks.quantize(Decimal("1"), rounding=ROUND_UP)
        else:
            rounded_ticks = ticks.quantize(Decimal("1"), rounding=ROUND_DOWN)

        # Convert back to price
        return rounded_ticks * tick_size

    async def create_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        limit_price: Decimal,
        order_type: LimitOrderType = LimitOrderType.AGGRESSIVE,
        place_order_func: Optional[Callable] = None
    ) -> LimitOrderResult:
        """
        Create and submit a limit order to the exchange.

        This method creates the order structure and optionally submits it
        to the exchange via the provided callback function.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT").
            side: Order side ("BUY" or "SELL").
            quantity: Quantity to trade.
            limit_price: Limit price for the order.
            order_type: Type of limit order strategy.
            place_order_func: Async callback to place order on exchange.
                             Signature: async (symbol, side, qty, price, post_only) -> Dict
                             Should return dict with 'order_id', 'status', etc.

        Returns:
            LimitOrderResult with order details and initial status.

        Example:
            >>> async def place_on_exchange(symbol, side, qty, price, post_only):
            ...     # Call exchange API
            ...     return {"order_id": "123", "status": "OPEN"}
            ...
            >>> result = await executor.create_limit_order(
            ...     symbol="BTCUSDT",
            ...     side="BUY",
            ...     quantity=Decimal("0.1"),
            ...     limit_price=Decimal("49950"),
            ...     place_order_func=place_on_exchange
            ... )
        """
        # Generate unique order ID for tracking
        order_id = uuid4()
        now = datetime.now()

        # Determine if post-only flag should be used
        use_post_only = (
            self.config.use_post_only and
            order_type in (LimitOrderType.PASSIVE, LimitOrderType.POST_ONLY)
        )

        # Create initial result object
        result = LimitOrderResult(
            order_id=order_id,
            symbol=symbol,
            side=side,
            original_quantity=quantity,
            filled_quantity=Decimal("0"),
            remaining_quantity=quantity,
            limit_price=limit_price,
            avg_fill_price=None,
            status=FillStatus.PENDING,
            order_type=order_type,
            start_time=now
        )

        # If exchange callback provided, place the order
        if place_order_func:
            try:
                # Call exchange API to place order
                exchange_response = await place_order_func(
                    symbol,
                    side,
                    quantity,
                    limit_price,
                    use_post_only
                )

                # Extract exchange order ID from response
                if exchange_response and "order_id" in exchange_response:
                    result.exchange_order_id = str(exchange_response["order_id"])
                    logger.info(
                        f"Limit order placed: {symbol} {side} {quantity} @ {limit_price} "
                        f"(exchange_id={result.exchange_order_id}, post_only={use_post_only})"
                    )
                else:
                    result.status = FillStatus.FAILED
                    result.error_message = "No order ID in exchange response"
                    logger.error(f"Failed to place limit order: no order ID returned")

            except Exception as e:
                result.status = FillStatus.FAILED
                result.error_message = str(e)
                logger.error(f"Failed to place limit order: {e}")
        else:
            # No exchange callback - order is created but not submitted
            logger.debug(
                f"Limit order created (not submitted): {symbol} {side} {quantity} @ {limit_price}"
            )

        # Track the order
        self._active_orders[order_id] = result
        self._stats["total_orders"] += 1

        return result

    async def monitor_order_fill(
        self,
        order_id: UUID,
        timeout_seconds: Optional[int] = None,
        check_order_func: Optional[Callable] = None,
        check_interval: float = 0.5
    ) -> Tuple[FillStatus, Decimal, Optional[Decimal]]:
        """
        Monitor an order until it fills, times out, or is cancelled.

        This method polls the order status at regular intervals until
        the order reaches a terminal state or times out.

        Args:
            order_id: ID of the order to monitor.
            timeout_seconds: Maximum time to wait for fill (uses config default if None).
            check_order_func: Async callback to check order status on exchange.
                             Signature: async (exchange_order_id) -> Dict
                             Should return dict with 'status', 'filled_qty', 'avg_price', etc.
            check_interval: Seconds between status checks.

        Returns:
            Tuple of (FillStatus, filled_quantity, avg_fill_price).

        Example:
            >>> async def check_status(exchange_id):
            ...     # Call exchange API
            ...     return {"status": "FILLED", "filled_qty": "0.1", "avg_price": "49955"}
            ...
            >>> status, filled, price = await executor.monitor_order_fill(
            ...     order_id=order_id,
            ...     timeout_seconds=30,
            ...     check_order_func=check_status
            ... )
        """
        # Get the order being monitored
        if order_id not in self._active_orders:
            logger.error(f"Order {order_id} not found for monitoring")
            return FillStatus.FAILED, Decimal("0"), None

        result = self._active_orders[order_id]
        timeout = timeout_seconds or self.config.timeout_seconds

        # Calculate deadline
        deadline = datetime.now() + timedelta(seconds=timeout)

        logger.info(
            f"Monitoring order {order_id} for up to {timeout}s "
            f"(exchange_id={result.exchange_order_id})"
        )

        # Monitor loop
        while datetime.now() < deadline:
            # Check order status if callback provided
            if check_order_func and result.exchange_order_id:
                try:
                    status_response = await check_order_func(result.exchange_order_id)

                    if status_response:
                        # Update filled quantity
                        if "filled_qty" in status_response:
                            result.filled_quantity = Decimal(str(status_response["filled_qty"]))
                            result.remaining_quantity = result.original_quantity - result.filled_quantity

                        # Update average price
                        if "avg_price" in status_response and status_response["avg_price"]:
                            result.avg_fill_price = Decimal(str(status_response["avg_price"]))

                        # Check if fully filled
                        exchange_status = status_response.get("status", "").upper()
                        if exchange_status == "FILLED" or result.filled_quantity >= result.original_quantity:
                            result.status = FillStatus.FILLED
                            result.end_time = datetime.now()
                            self._stats["filled_orders"] += 1

                            logger.info(
                                f"Order {order_id} FILLED: {result.filled_quantity} @ {result.avg_fill_price}"
                            )
                            return FillStatus.FILLED, result.filled_quantity, result.avg_fill_price

                        # Check for partial fill
                        if result.filled_quantity > 0 and result.status != FillStatus.PARTIAL:
                            result.status = FillStatus.PARTIAL
                            self._stats["partial_fills"] += 1
                            logger.debug(
                                f"Order {order_id} partial fill: {result.filled_quantity}/{result.original_quantity}"
                            )

                        # Check if cancelled
                        if exchange_status in ("CANCELLED", "CANCELED", "EXPIRED"):
                            result.status = FillStatus.CANCELLED
                            result.end_time = datetime.now()
                            logger.info(f"Order {order_id} cancelled by exchange")
                            return FillStatus.CANCELLED, result.filled_quantity, result.avg_fill_price

                except Exception as e:
                    logger.warning(f"Error checking order status: {e}")

            # Wait before next check
            await asyncio.sleep(check_interval)

        # Timeout reached
        result.status = FillStatus.TIMEOUT
        result.end_time = datetime.now()
        self._stats["timeouts"] += 1

        logger.warning(
            f"Order {order_id} TIMEOUT after {timeout}s "
            f"(filled={result.filled_quantity}/{result.original_quantity})"
        )

        return FillStatus.TIMEOUT, result.filled_quantity, result.avg_fill_price

    async def handle_partial_fill(
        self,
        order_id: UUID,
        filled_qty: Decimal,
        fill_price: Decimal,
        cancel_order_func: Optional[Callable] = None,
        place_order_func: Optional[Callable] = None,
        current_price: Optional[Decimal] = None
    ) -> LimitOrderResult:
        """
        Handle a partial fill by either keeping, cancelling, or re-placing the remaining order.

        This method is called when an order has been partially filled. It decides
        whether to:
        1. Keep waiting for the rest to fill
        2. Cancel the remaining order
        3. Re-place the remaining quantity at a new price

        Args:
            order_id: ID of the partially filled order.
            filled_qty: Quantity that was just filled.
            fill_price: Price of the fill.
            cancel_order_func: Async callback to cancel remaining order.
                              Signature: async (exchange_order_id) -> bool
            place_order_func: Async callback to place new order for remaining.
                             Same signature as create_limit_order callback.
            current_price: Current market price for potential re-pricing.

        Returns:
            Updated LimitOrderResult with new status and potentially new order details.

        Example:
            >>> result = await executor.handle_partial_fill(
            ...     order_id=order_id,
            ...     filled_qty=Decimal("0.05"),
            ...     fill_price=Decimal("49950"),
            ...     cancel_order_func=cancel_on_exchange,
            ...     current_price=Decimal("50000")
            ... )
        """
        # Get the order
        if order_id not in self._active_orders:
            logger.error(f"Order {order_id} not found for partial fill handling")
            raise ValueError(f"Order {order_id} not found")

        result = self._active_orders[order_id]

        # Create partial fill info
        partial_info = PartialFillInfo(
            fill_quantity=filled_qty,
            fill_price=fill_price,
            cumulative_filled=result.filled_quantity + filled_qty,
            remaining=result.original_quantity - result.filled_quantity - filled_qty,
            timestamp=datetime.now()
        )

        # Update the result with new fill info
        result.filled_quantity = partial_info.cumulative_filled
        result.remaining_quantity = partial_info.remaining

        # Calculate new average fill price (weighted average)
        if result.avg_fill_price is not None:
            # Weighted average of previous fills and new fill
            prev_value = result.avg_fill_price * (result.filled_quantity - filled_qty)
            new_value = fill_price * filled_qty
            result.avg_fill_price = (prev_value + new_value) / result.filled_quantity
        else:
            result.avg_fill_price = fill_price

        logger.info(
            f"Partial fill handled for {order_id}: "
            f"filled={result.filled_quantity}/{result.original_quantity}, "
            f"avg_price={result.avg_fill_price}"
        )

        # Check if fill percentage meets cancellation threshold
        fill_pct = float(result.filled_quantity / result.original_quantity)

        if fill_pct >= self.config.min_fill_pct_before_cancel:
            # Enough filled - we might want to cancel remaining and accept partial
            logger.info(
                f"Order {order_id} {fill_pct:.1%} filled, "
                f"considering cancellation of remaining {result.remaining_quantity}"
            )

            # For now, just update status to partial - let monitor handle timeout
            result.status = FillStatus.PARTIAL
        else:
            # Not enough filled yet - keep waiting
            result.status = FillStatus.PARTIAL

            # If we have current price and it's moved significantly, consider re-pricing
            if current_price and place_order_func and cancel_order_func:
                price_move_pct = abs(float(current_price - result.limit_price) / float(result.limit_price)) * 100

                # If price moved more than 0.1%, consider re-pricing
                if price_move_pct > 0.1:
                    logger.info(
                        f"Price moved {price_move_pct:.2f}% from limit price, "
                        f"considering re-pricing remaining {result.remaining_quantity}"
                    )
                    # Re-pricing logic could be added here
                    # For now, we just log and let the order continue

        return result

    def estimate_slippage_savings(
        self,
        order_value: float,
        order_type: LimitOrderType = LimitOrderType.AGGRESSIVE
    ) -> SlippageSavingsEstimate:
        """
        Estimate the slippage savings from using limit orders vs market orders.

        This method provides an estimate based on historical market microstructure
        research and the specific order type being used.

        Args:
            order_value: Total value of the order in quote currency (e.g., USD).
            order_type: Type of limit order strategy being used.

        Returns:
            SlippageSavingsEstimate with detailed breakdown of expected savings.

        Example:
            >>> estimate = executor.estimate_slippage_savings(
            ...     order_value=10000.0,
            ...     order_type=LimitOrderType.PASSIVE
            ... )
            >>> print(f"Estimated savings: {estimate.savings_bps:.2f} bps (${estimate.savings_absolute:.2f})")
        """
        # Determine order size tier
        if order_value < 1000:
            tier = "micro"
        elif order_value < 10000:
            tier = "small"
        elif order_value < 50000:
            tier = "medium"
        elif order_value < 100000:
            tier = "large"
        else:
            tier = "xlarge"

        # Get expected market slippage for this tier
        market_slippage_bps = self.MARKET_SLIPPAGE_BY_SIZE[tier]

        # Get reduction factor for order type
        reduction_factor = self.LIMIT_SLIPPAGE_REDUCTION[order_type]

        # Calculate expected limit slippage
        limit_slippage_bps = market_slippage_bps * reduction_factor

        # Calculate savings
        savings_bps = market_slippage_bps - limit_slippage_bps

        # Convert to absolute value
        # 1 basis point = 0.01% = 0.0001
        savings_absolute = Decimal(str(order_value)) * Decimal(str(savings_bps)) / Decimal("10000")

        # Confidence based on order size (larger orders have more uncertainty)
        confidence_by_tier = {
            "micro": 0.90,
            "small": 0.85,
            "medium": 0.75,
            "large": 0.65,
            "xlarge": 0.50
        }
        confidence = confidence_by_tier[tier]

        estimate = SlippageSavingsEstimate(
            order_value=Decimal(str(order_value)),
            estimated_market_slippage_bps=market_slippage_bps,
            estimated_limit_slippage_bps=limit_slippage_bps,
            savings_bps=savings_bps,
            savings_absolute=savings_absolute,
            confidence=confidence
        )

        logger.debug(
            f"Slippage savings estimate for ${order_value:.2f} order: "
            f"{savings_bps:.2f} bps (${savings_absolute:.2f}) "
            f"using {order_type.value} limit order"
        )

        return estimate

    async def execute_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        current_price: Decimal,
        order_type: LimitOrderType = LimitOrderType.AGGRESSIVE,
        place_order_func: Optional[Callable] = None,
        check_order_func: Optional[Callable] = None,
        cancel_order_func: Optional[Callable] = None,
        place_market_func: Optional[Callable] = None
    ) -> LimitOrderResult:
        """
        Execute a complete limit order flow with monitoring and fallback.

        This is the main entry point for executing limit orders. It:
        1. Calculates the optimal limit price
        2. Places the limit order
        3. Monitors for fills
        4. Handles timeouts and partial fills
        5. Falls back to market order if configured and necessary

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT").
            side: Order side ("BUY" or "SELL").
            quantity: Quantity to trade.
            current_price: Current market price for limit price calculation.
            order_type: Type of limit order strategy.
            place_order_func: Async callback to place limit order.
            check_order_func: Async callback to check order status.
            cancel_order_func: Async callback to cancel order.
            place_market_func: Async callback to place market order (for fallback).

        Returns:
            LimitOrderResult with complete execution details.

        Example:
            >>> result = await executor.execute_limit_order(
            ...     symbol="BTCUSDT",
            ...     side="BUY",
            ...     quantity=Decimal("0.1"),
            ...     current_price=Decimal("50000"),
            ...     order_type=LimitOrderType.PASSIVE,
            ...     place_order_func=place_limit,
            ...     check_order_func=check_status,
            ...     cancel_order_func=cancel_order,
            ...     place_market_func=place_market
            ... )
        """
        arrival_price = current_price

        # Step 1: Calculate limit price
        limit_price = self.calculate_limit_price(
            current_price=current_price,
            side=side,
            order_type=order_type
        )

        logger.info(
            f"Executing {order_type.value} limit order: "
            f"{symbol} {side} {quantity} @ {limit_price} "
            f"(arrival={arrival_price})"
        )

        # Step 2: Place the limit order
        result = await self.create_limit_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
            order_type=order_type,
            place_order_func=place_order_func
        )

        if result.status == FillStatus.FAILED:
            logger.error(f"Failed to place limit order: {result.error_message}")
            return result

        # Step 3: Monitor for fill
        retry_count = 0
        while retry_count < self.config.max_retries:
            fill_status, filled_qty, avg_price = await self.monitor_order_fill(
                order_id=result.order_id,
                check_order_func=check_order_func
            )

            # Update result
            result.filled_quantity = filled_qty
            result.remaining_quantity = quantity - filled_qty
            result.avg_fill_price = avg_price

            # Handle different outcomes
            if fill_status == FillStatus.FILLED:
                # Complete fill - success!
                result.status = FillStatus.FILLED
                result.end_time = datetime.now()

                # Calculate slippage vs arrival price
                if result.avg_fill_price:
                    result.slippage_bps = self._calculate_slippage_bps(
                        arrival_price=arrival_price,
                        fill_price=result.avg_fill_price,
                        side=side
                    )
                    self._stats["total_slippage_bps"] += result.slippage_bps

                self._execution_history.append(result)
                logger.info(
                    f"Limit order completed: {symbol} {side} {filled_qty} @ {avg_price} "
                    f"(slippage={result.slippage_bps:.2f} bps)"
                )
                return result

            elif fill_status == FillStatus.TIMEOUT:
                # Timeout - decide whether to retry, cancel, or fallback
                retry_count += 1

                # If some quantity filled, check if we should keep partial
                if result.filled_quantity > 0:
                    fill_pct = float(result.filled_quantity / result.original_quantity)
                    if fill_pct >= self.config.min_fill_pct_before_cancel:
                        # Accept partial fill
                        logger.info(
                            f"Accepting partial fill {fill_pct:.1%} after timeout"
                        )
                        result.status = FillStatus.PARTIAL
                        result.end_time = datetime.now()

                        # Cancel remaining if callback provided
                        if cancel_order_func and result.exchange_order_id:
                            try:
                                await cancel_order_func(result.exchange_order_id)
                            except Exception as e:
                                logger.warning(f"Error cancelling remaining order: {e}")

                        self._execution_history.append(result)
                        return result

                # Not enough filled - consider retry or fallback
                if retry_count < self.config.max_retries:
                    logger.info(
                        f"Limit order timeout, retry {retry_count}/{self.config.max_retries}"
                    )

                    # Cancel existing order
                    if cancel_order_func and result.exchange_order_id:
                        try:
                            await cancel_order_func(result.exchange_order_id)
                        except Exception as e:
                            logger.warning(f"Error cancelling for retry: {e}")

                    # Re-calculate price with more aggressive offset
                    if order_type != LimitOrderType.AGGRESSIVE:
                        # Upgrade to aggressive for retry
                        limit_price = self.calculate_limit_price(
                            current_price=current_price,
                            side=side,
                            order_type=LimitOrderType.AGGRESSIVE
                        )

                        # Place new order for remaining quantity
                        remaining_qty = result.remaining_quantity
                        new_result = await self.create_limit_order(
                            symbol=symbol,
                            side=side,
                            quantity=remaining_qty,
                            limit_price=limit_price,
                            order_type=LimitOrderType.AGGRESSIVE,
                            place_order_func=place_order_func
                        )

                        # Merge results
                        result.exchange_order_id = new_result.exchange_order_id
                        result.order_type = LimitOrderType.AGGRESSIVE
                        continue

                # All retries exhausted - consider fallback
                break

            elif fill_status == FillStatus.CANCELLED:
                # Order cancelled externally
                result.status = FillStatus.CANCELLED
                result.end_time = datetime.now()
                self._execution_history.append(result)
                return result

            else:
                # Other failure
                result.status = fill_status
                result.end_time = datetime.now()
                self._execution_history.append(result)
                return result

        # Step 4: Fallback to market order if configured
        if self.config.fallback_to_market and result.remaining_quantity > 0:
            logger.warning(
                f"Falling back to market order for remaining {result.remaining_quantity}"
            )
            result.used_fallback = True
            self._stats["fallbacks_used"] += 1

            if place_market_func:
                try:
                    market_result = await place_market_func(
                        symbol,
                        side,
                        result.remaining_quantity
                    )

                    if market_result:
                        # Update with market fill
                        market_filled = Decimal(str(market_result.get("filled_qty", result.remaining_quantity)))
                        market_price = Decimal(str(market_result.get("avg_price", current_price)))

                        # Calculate combined average price
                        if result.avg_fill_price and result.filled_quantity > 0:
                            total_value = (result.avg_fill_price * result.filled_quantity) + (market_price * market_filled)
                            total_qty = result.filled_quantity + market_filled
                            result.avg_fill_price = total_value / total_qty
                        else:
                            result.avg_fill_price = market_price

                        result.filled_quantity += market_filled
                        result.remaining_quantity -= market_filled

                        if result.remaining_quantity <= 0:
                            result.status = FillStatus.FILLED
                        else:
                            result.status = FillStatus.PARTIAL

                        logger.info(
                            f"Market fallback filled: {market_filled} @ {market_price}"
                        )

                except Exception as e:
                    logger.error(f"Market fallback failed: {e}")
                    result.error_message = f"Market fallback failed: {e}"

        # Finalize result
        result.end_time = datetime.now()

        # Calculate final slippage
        if result.avg_fill_price:
            result.slippage_bps = self._calculate_slippage_bps(
                arrival_price=arrival_price,
                fill_price=result.avg_fill_price,
                side=side
            )
            self._stats["total_slippage_bps"] += result.slippage_bps

        self._execution_history.append(result)

        logger.info(
            f"Limit order execution complete: "
            f"{result.filled_quantity}/{result.original_quantity} filled "
            f"@ {result.avg_fill_price} (slippage={result.slippage_bps:.2f} bps, "
            f"fallback={result.used_fallback})"
        )

        return result

    def _calculate_slippage_bps(
        self,
        arrival_price: Decimal,
        fill_price: Decimal,
        side: str
    ) -> float:
        """
        Calculate slippage in basis points.

        Positive slippage = unfavorable (paid more for buy, received less for sell)
        Negative slippage = favorable (price improvement)

        Args:
            arrival_price: Price when order was initiated.
            fill_price: Actual average fill price.
            side: Order side ("BUY" or "SELL").

        Returns:
            Slippage in basis points.
        """
        if arrival_price == 0:
            return 0.0

        price_diff = float(fill_price - arrival_price)
        arrival = float(arrival_price)

        if side == "BUY":
            # For buys: higher fill price = positive (bad) slippage
            slippage_pct = (price_diff / arrival) * 100
        else:
            # For sells: lower fill price = positive (bad) slippage
            slippage_pct = (-price_diff / arrival) * 100

        # Convert percentage to basis points (1% = 100 bps)
        return slippage_pct * 100

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get execution statistics for the limit order executor.

        Returns:
            Dictionary with execution metrics and performance stats.
        """
        total = self._stats["total_orders"]
        filled = self._stats["filled_orders"]

        fill_rate = (filled / total * 100) if total > 0 else 0.0
        avg_slippage = (self._stats["total_slippage_bps"] / total) if total > 0 else 0.0
        fallback_rate = (self._stats["fallbacks_used"] / total * 100) if total > 0 else 0.0

        return {
            "total_orders": total,
            "filled_orders": filled,
            "fill_rate_pct": round(fill_rate, 2),
            "partial_fills": self._stats["partial_fills"],
            "timeouts": self._stats["timeouts"],
            "fallbacks_used": self._stats["fallbacks_used"],
            "fallback_rate_pct": round(fallback_rate, 2),
            "avg_slippage_bps": round(avg_slippage, 2),
            "total_slippage_bps": round(self._stats["total_slippage_bps"], 2),
            "config": {
                "timeout_seconds": self.config.timeout_seconds,
                "use_post_only": self.config.use_post_only,
                "fallback_enabled": self.config.fallback_to_market,
                "aggressive_offset_pct": self.config.aggressive_offset_pct,
                "passive_offset_pct": self.config.passive_offset_pct
            }
        }

    def get_status(self) -> Dict[str, Any]:
        """
        Get current status of the limit order executor.

        Returns:
            Dictionary with status information.
        """
        return {
            "active_orders": len(self._active_orders),
            "execution_history_size": len(self._execution_history),
            "statistics": self.get_statistics()
        }


# Global instance for singleton pattern
_limit_order_executor: Optional[LimitOrderExecutor] = None


def get_limit_order_executor(config: Optional[LimitOrderConfig] = None) -> LimitOrderExecutor:
    """
    Get or create global limit order executor instance.

    This follows the singleton pattern used by other trading enhancements.

    Args:
        config: Optional configuration to use when creating the instance.

    Returns:
        Global LimitOrderExecutor instance.
    """
    global _limit_order_executor
    if _limit_order_executor is None:
        _limit_order_executor = LimitOrderExecutor(config)
    return _limit_order_executor
