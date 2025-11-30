"""
Smart Order Execution Algorithms
Research Source: TWAP, VWAP, Iceberg Orders, Implementation Shortfall

Purpose:
- Implement intelligent order execution strategies
- TWAP (Time-Weighted Average Price)
- VWAP (Volume-Weighted Average Price)
- Iceberg orders for hiding large positions
- Adaptive order splitting

RESEARCH: Smart execution can reduce slippage by 20-50% on large orders.
TWAP is best for low liquidity, VWAP for following market volume.
"""

import asyncio
import logging
import random
from enum import Enum
from typing import Optional, List, Dict, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from collections import deque

logger = logging.getLogger(__name__)


class ExecutionAlgorithm(Enum):
    """Order execution algorithm types"""
    MARKET = "market"           # Simple market order
    LIMIT = "limit"             # Limit order
    TWAP = "twap"              # Time-Weighted Average Price
    VWAP = "vwap"              # Volume-Weighted Average Price
    ICEBERG = "iceberg"        # Hidden large orders
    POV = "pov"                # Percentage of Volume
    IMPLEMENTATION_SHORTFALL = "implementation_shortfall"  # Arrival price benchmark


class ExecutionUrgency(Enum):
    """Execution urgency levels"""
    LOW = "low"           # Patient, minimize impact
    NORMAL = "normal"     # Balanced
    HIGH = "high"         # Speed over cost
    CRITICAL = "critical" # Immediate execution


@dataclass
class ExecutionConfig:
    """Configuration for smart order execution"""
    # TWAP settings
    twap_duration_minutes: int = 30          # Execute over 30 minutes
    twap_min_slices: int = 10                # At least 10 slices
    twap_max_slices: int = 60                # At most 60 slices

    # VWAP settings
    vwap_participation_rate: float = 0.10    # 10% of volume
    vwap_adaptive: bool = True               # Adapt to real-time volume

    # Iceberg settings
    iceberg_visible_pct: float = 0.10        # Show 10% of order
    iceberg_randomize: bool = True           # Randomize visible size
    iceberg_variance: float = 0.20           # 20% variance in size

    # POV settings
    pov_target_rate: float = 0.10            # Target 10% of market volume

    # General settings
    max_slippage_pct: float = 0.50           # Max acceptable slippage
    retry_failed_slices: bool = True         # Retry failed slices
    max_retries: int = 3                     # Max retries per slice


@dataclass
class OrderSlice:
    """Individual slice of a larger order"""
    slice_id: int
    quantity: Decimal
    target_price: Optional[Decimal]
    scheduled_time: datetime
    executed: bool = False
    execution_price: Optional[Decimal] = None
    execution_time: Optional[datetime] = None
    fill_quantity: Optional[Decimal] = None
    slippage_pct: float = 0.0


@dataclass
class ExecutionPlan:
    """Complete execution plan for an order"""
    algorithm: ExecutionAlgorithm
    total_quantity: Decimal
    symbol: str
    side: str  # BUY or SELL
    slices: List[OrderSlice]
    start_time: datetime
    end_time: datetime
    arrival_price: Decimal
    urgency: ExecutionUrgency


@dataclass
class ExecutionResult:
    """Result of executing an order"""
    algorithm: ExecutionAlgorithm
    symbol: str
    side: str
    total_quantity: Decimal
    filled_quantity: Decimal
    avg_price: Decimal
    arrival_price: Decimal
    vwap: Decimal
    slippage_pct: float
    implementation_shortfall_pct: float
    execution_time_seconds: float
    slices_executed: int
    slices_failed: int
    total_cost: Decimal


class SmartOrderExecutor:
    """
    Smart Order Execution Engine

    RESEARCH-BACKED IMPLEMENTATION:
    - TWAP: Split orders across time
    - VWAP: Follow market volume profile
    - Iceberg: Hide large order size
    - Minimize market impact
    - Track execution quality

    Usage:
        executor = SmartOrderExecutor()

        # Create TWAP plan
        plan = executor.create_twap_plan(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0"),
            duration_minutes=30
        )

        # Execute the plan
        result = await executor.execute_plan(plan, exchange_client)
    """

    def __init__(self, config: Optional[ExecutionConfig] = None):
        """Initialize smart order executor"""
        self.config = config or ExecutionConfig()
        self._execution_history: deque = deque(maxlen=1000)
        self._active_plans: Dict[str, ExecutionPlan] = {}

        logger.info(
            f"SmartOrderExecutor initialized: "
            f"twap_duration={self.config.twap_duration_minutes}min, "
            f"vwap_participation={self.config.vwap_participation_rate:.1%}"
        )

    def create_twap_plan(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        current_price: Decimal,
        duration_minutes: Optional[int] = None,
        urgency: ExecutionUrgency = ExecutionUrgency.NORMAL
    ) -> ExecutionPlan:
        """
        Create a TWAP execution plan

        TWAP splits the order into equal-sized slices executed at
        regular intervals. Best for low-liquidity environments.

        Args:
            symbol: Trading symbol
            side: BUY or SELL
            quantity: Total quantity to execute
            current_price: Current market price
            duration_minutes: Execution duration
            urgency: Execution urgency level

        Returns:
            ExecutionPlan with TWAP slices
        """
        duration = duration_minutes or self.config.twap_duration_minutes

        # Adjust based on urgency
        if urgency == ExecutionUrgency.HIGH:
            duration = max(5, duration // 2)
        elif urgency == ExecutionUrgency.CRITICAL:
            duration = 1  # Execute immediately
        elif urgency == ExecutionUrgency.LOW:
            duration = min(120, duration * 2)

        # Calculate number of slices
        num_slices = max(
            self.config.twap_min_slices,
            min(self.config.twap_max_slices, duration)
        )

        # Calculate slice size and interval
        slice_quantity = quantity / num_slices
        interval_seconds = (duration * 60) / num_slices

        # Create slices
        slices = []
        start_time = datetime.now()

        for i in range(num_slices):
            scheduled_time = start_time + timedelta(seconds=i * interval_seconds)

            # Add small random variance to avoid detection
            if i > 0:  # Don't delay first slice
                jitter = random.uniform(-0.1, 0.1) * interval_seconds
                scheduled_time += timedelta(seconds=jitter)

            slices.append(OrderSlice(
                slice_id=i,
                quantity=slice_quantity,
                target_price=None,  # TWAP uses market orders
                scheduled_time=scheduled_time
            ))

        end_time = start_time + timedelta(minutes=duration)

        logger.info(
            f"TWAP plan created: {symbol} {side} {quantity} "
            f"in {num_slices} slices over {duration}min"
        )

        return ExecutionPlan(
            algorithm=ExecutionAlgorithm.TWAP,
            total_quantity=quantity,
            symbol=symbol,
            side=side,
            slices=slices,
            start_time=start_time,
            end_time=end_time,
            arrival_price=current_price,
            urgency=urgency
        )

    def create_vwap_plan(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        current_price: Decimal,
        volume_profile: Dict[int, float],  # hour -> expected volume %
        trading_hours: int = 24
    ) -> ExecutionPlan:
        """
        Create a VWAP execution plan

        VWAP weights execution by expected market volume, executing
        more during high-volume periods.

        Args:
            symbol: Trading symbol
            side: BUY or SELL
            quantity: Total quantity to execute
            current_price: Current market price
            volume_profile: Hour -> volume percentage mapping
            trading_hours: Number of hours to execute

        Returns:
            ExecutionPlan with VWAP slices
        """
        start_time = datetime.now()
        current_hour = start_time.hour

        # Normalize volume profile
        total_vol = sum(volume_profile.values())
        if total_vol == 0:
            # Use flat profile if none provided
            volume_profile = {h: 1.0/24 for h in range(24)}
            total_vol = 1.0

        # Create slices based on volume profile
        slices = []
        slice_id = 0

        for hour_offset in range(trading_hours):
            hour = (current_hour + hour_offset) % 24
            vol_pct = volume_profile.get(hour, 0) / total_vol

            if vol_pct > 0:
                slice_quantity = quantity * Decimal(str(vol_pct))
                scheduled_time = start_time + timedelta(hours=hour_offset)

                slices.append(OrderSlice(
                    slice_id=slice_id,
                    quantity=slice_quantity,
                    target_price=None,
                    scheduled_time=scheduled_time
                ))
                slice_id += 1

        end_time = start_time + timedelta(hours=trading_hours)

        logger.info(
            f"VWAP plan created: {symbol} {side} {quantity} "
            f"in {len(slices)} volume-weighted slices"
        )

        return ExecutionPlan(
            algorithm=ExecutionAlgorithm.VWAP,
            total_quantity=quantity,
            symbol=symbol,
            side=side,
            slices=slices,
            start_time=start_time,
            end_time=end_time,
            arrival_price=current_price,
            urgency=ExecutionUrgency.NORMAL
        )

    def create_iceberg_plan(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        limit_price: Decimal,
        visible_pct: Optional[float] = None
    ) -> ExecutionPlan:
        """
        Create an Iceberg order plan

        Iceberg orders show only a small portion of the total order,
        hiding the true size from other market participants.

        Args:
            symbol: Trading symbol
            side: BUY or SELL
            quantity: Total quantity to execute
            limit_price: Limit price for orders
            visible_pct: Percentage of order to show

        Returns:
            ExecutionPlan with iceberg slices
        """
        visible = visible_pct or self.config.iceberg_visible_pct
        variance = self.config.iceberg_variance if self.config.iceberg_randomize else 0

        # Calculate number of slices
        num_slices = int(1 / visible)
        base_slice_qty = quantity * Decimal(str(visible))

        slices = []
        remaining = quantity
        start_time = datetime.now()

        for i in range(num_slices + 10):  # Extra slices for variance
            if remaining <= 0:
                break

            # Calculate slice with variance
            if self.config.iceberg_randomize:
                variance_mult = 1 + random.uniform(-variance, variance)
                slice_qty = base_slice_qty * Decimal(str(variance_mult))
            else:
                slice_qty = base_slice_qty

            # Don't exceed remaining
            slice_qty = min(slice_qty, remaining)

            slices.append(OrderSlice(
                slice_id=i,
                quantity=slice_qty,
                target_price=limit_price,
                scheduled_time=start_time  # Execute immediately when previous fills
            ))

            remaining -= slice_qty

        logger.info(
            f"Iceberg plan created: {symbol} {side} {quantity} "
            f"({visible:.0%} visible) in {len(slices)} slices"
        )

        return ExecutionPlan(
            algorithm=ExecutionAlgorithm.ICEBERG,
            total_quantity=quantity,
            symbol=symbol,
            side=side,
            slices=slices,
            start_time=start_time,
            end_time=start_time + timedelta(hours=24),  # Max 24h
            arrival_price=limit_price,
            urgency=ExecutionUrgency.LOW
        )

    def create_pov_plan(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        current_price: Decimal,
        target_participation: Optional[float] = None,
        duration_hours: int = 4
    ) -> ExecutionPlan:
        """
        Create a Percentage of Volume (POV) plan

        POV targets a specific percentage of market volume,
        executing more when volume is high.

        Args:
            symbol: Trading symbol
            side: BUY or SELL
            quantity: Total quantity to execute
            current_price: Current market price
            target_participation: Target % of market volume
            duration_hours: Maximum execution duration

        Returns:
            ExecutionPlan with POV slices (dynamic)
        """
        participation = target_participation or self.config.pov_target_rate

        # POV is dynamic - create initial slice
        start_time = datetime.now()

        slices = [OrderSlice(
            slice_id=0,
            quantity=quantity,  # Will be adjusted dynamically
            target_price=None,
            scheduled_time=start_time
        )]

        logger.info(
            f"POV plan created: {symbol} {side} {quantity} "
            f"at {participation:.1%} participation rate"
        )

        return ExecutionPlan(
            algorithm=ExecutionAlgorithm.POV,
            total_quantity=quantity,
            symbol=symbol,
            side=side,
            slices=slices,
            start_time=start_time,
            end_time=start_time + timedelta(hours=duration_hours),
            arrival_price=current_price,
            urgency=ExecutionUrgency.NORMAL
        )

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        execute_func: Callable[[str, str, Decimal, Optional[Decimal]], Any]
    ) -> ExecutionResult:
        """
        Execute an order plan

        Args:
            plan: ExecutionPlan to execute
            execute_func: Async function to execute individual orders
                         signature: (symbol, side, quantity, price) -> order_result

        Returns:
            ExecutionResult with execution statistics
        """
        execution_start = datetime.now()
        filled_quantity = Decimal("0")
        total_value = Decimal("0")
        slices_executed = 0
        slices_failed = 0

        plan_id = f"{plan.symbol}_{plan.algorithm.value}_{execution_start.timestamp()}"
        self._active_plans[plan_id] = plan

        try:
            for slice_order in plan.slices:
                if filled_quantity >= plan.total_quantity:
                    break

                # Wait until scheduled time (for TWAP/VWAP)
                now = datetime.now()
                if slice_order.scheduled_time > now:
                    wait_seconds = (slice_order.scheduled_time - now).total_seconds()
                    if wait_seconds > 0:
                        await asyncio.sleep(wait_seconds)

                # Adjust quantity for last slice
                remaining = plan.total_quantity - filled_quantity
                slice_qty = min(slice_order.quantity, remaining)

                if slice_qty <= 0:
                    continue

                # Execute the slice
                retries = 0
                success = False

                while retries < self.config.max_retries and not success:
                    try:
                        result = await execute_func(
                            plan.symbol,
                            plan.side,
                            slice_qty,
                            slice_order.target_price
                        )

                        if result and result.get('filled_quantity'):
                            fill_qty = Decimal(str(result['filled_quantity']))
                            fill_price = Decimal(str(result.get('avg_price', plan.arrival_price)))

                            slice_order.executed = True
                            slice_order.execution_price = fill_price
                            slice_order.execution_time = datetime.now()
                            slice_order.fill_quantity = fill_qty

                            filled_quantity += fill_qty
                            total_value += fill_qty * fill_price
                            slices_executed += 1
                            success = True

                            # Calculate slice slippage
                            if plan.arrival_price > 0:
                                slice_order.slippage_pct = float(
                                    (fill_price - plan.arrival_price) / plan.arrival_price * 100
                                )

                            logger.debug(
                                f"Slice {slice_order.slice_id} executed: "
                                f"{fill_qty} @ {fill_price}"
                            )

                    except Exception as e:
                        retries += 1
                        logger.warning(
                            f"Slice {slice_order.slice_id} failed (retry {retries}): {e}"
                        )
                        if retries < self.config.max_retries:
                            await asyncio.sleep(1)

                if not success:
                    slices_failed += 1
                    logger.error(f"Slice {slice_order.slice_id} failed after {retries} retries")

            # Calculate results
            execution_time = (datetime.now() - execution_start).total_seconds()
            avg_price = total_value / filled_quantity if filled_quantity > 0 else plan.arrival_price
            vwap = avg_price  # For non-VWAP algos, VWAP = avg price

            # Calculate slippage and implementation shortfall
            if plan.side == "BUY":
                slippage_pct = float((avg_price - plan.arrival_price) / plan.arrival_price * 100)
            else:
                slippage_pct = float((plan.arrival_price - avg_price) / plan.arrival_price * 100)

            implementation_shortfall = slippage_pct + (slices_failed / len(plan.slices) * 0.1)

            result = ExecutionResult(
                algorithm=plan.algorithm,
                symbol=plan.symbol,
                side=plan.side,
                total_quantity=plan.total_quantity,
                filled_quantity=filled_quantity,
                avg_price=avg_price,
                arrival_price=plan.arrival_price,
                vwap=vwap,
                slippage_pct=slippage_pct,
                implementation_shortfall_pct=implementation_shortfall,
                execution_time_seconds=execution_time,
                slices_executed=slices_executed,
                slices_failed=slices_failed,
                total_cost=total_value
            )

            self._execution_history.append(result)
            logger.info(
                f"Execution complete: {plan.algorithm.value} {plan.symbol} "
                f"Filled={filled_quantity}/{plan.total_quantity} "
                f"AvgPrice={avg_price} Slippage={slippage_pct:.3f}%"
            )

            return result

        finally:
            del self._active_plans[plan_id]

    def get_recommended_algorithm(
        self,
        quantity: Decimal,
        avg_daily_volume: Decimal,
        current_price: Decimal,
        urgency: ExecutionUrgency = ExecutionUrgency.NORMAL,
        market_volatility: float = 0.02
    ) -> ExecutionAlgorithm:
        """
        Recommend the best execution algorithm based on order characteristics

        Args:
            quantity: Order quantity
            avg_daily_volume: Average daily volume
            current_price: Current market price
            urgency: Execution urgency
            market_volatility: Current market volatility

        Returns:
            Recommended ExecutionAlgorithm
        """
        order_value = float(quantity * current_price)
        order_as_pct_volume = float(quantity / avg_daily_volume) if avg_daily_volume > 0 else 0

        # Decision logic
        if urgency == ExecutionUrgency.CRITICAL:
            return ExecutionAlgorithm.MARKET

        if order_as_pct_volume > 0.05:  # Large order (>5% of daily volume)
            if urgency == ExecutionUrgency.LOW:
                return ExecutionAlgorithm.ICEBERG
            elif market_volatility > 0.03:  # High volatility
                return ExecutionAlgorithm.TWAP
            else:
                return ExecutionAlgorithm.VWAP

        if order_as_pct_volume > 0.01:  # Medium order (1-5% of daily volume)
            return ExecutionAlgorithm.TWAP

        # Small order
        return ExecutionAlgorithm.MARKET

    def get_execution_statistics(self) -> Dict:
        """Get execution performance statistics"""
        if not self._execution_history:
            return {"message": "No execution history"}

        total_executions = len(self._execution_history)
        avg_slippage = sum(r.slippage_pct for r in self._execution_history) / total_executions
        avg_impl_shortfall = sum(r.implementation_shortfall_pct for r in self._execution_history) / total_executions
        fill_rate = sum(
            float(r.filled_quantity / r.total_quantity)
            for r in self._execution_history
        ) / total_executions

        by_algorithm = {}
        for algo in ExecutionAlgorithm:
            algo_results = [r for r in self._execution_history if r.algorithm == algo]
            if algo_results:
                by_algorithm[algo.value] = {
                    "count": len(algo_results),
                    "avg_slippage": sum(r.slippage_pct for r in algo_results) / len(algo_results),
                    "avg_fill_rate": sum(
                        float(r.filled_quantity / r.total_quantity) for r in algo_results
                    ) / len(algo_results)
                }

        return {
            "total_executions": total_executions,
            "avg_slippage_pct": round(avg_slippage, 4),
            "avg_implementation_shortfall_pct": round(avg_impl_shortfall, 4),
            "avg_fill_rate": round(fill_rate, 4),
            "by_algorithm": by_algorithm,
            "active_plans": len(self._active_plans)
        }

    def get_status(self) -> Dict:
        """Get executor status"""
        return {
            "config": {
                "twap_duration_minutes": self.config.twap_duration_minutes,
                "vwap_participation_rate": self.config.vwap_participation_rate,
                "iceberg_visible_pct": self.config.iceberg_visible_pct,
                "max_slippage_pct": self.config.max_slippage_pct
            },
            "statistics": self.get_execution_statistics(),
            "active_plans_count": len(self._active_plans)
        }


# Default volume profile (crypto 24h market)
CRYPTO_VOLUME_PROFILE = {
    0: 0.030, 1: 0.025, 2: 0.025, 3: 0.025, 4: 0.030,
    5: 0.035, 6: 0.040, 7: 0.045, 8: 0.050, 9: 0.055,
    10: 0.055, 11: 0.050, 12: 0.050, 13: 0.055, 14: 0.060,
    15: 0.060, 16: 0.055, 17: 0.050, 18: 0.045, 19: 0.045,
    20: 0.045, 21: 0.040, 22: 0.035, 23: 0.030
}


# Global instance
_smart_executor: Optional[SmartOrderExecutor] = None


def get_smart_order_executor(config: Optional[ExecutionConfig] = None) -> SmartOrderExecutor:
    """Get or create global smart order executor"""
    global _smart_executor
    if _smart_executor is None:
        _smart_executor = SmartOrderExecutor(config)
    return _smart_executor
