"""
Slippage Manager - Dynamic Slippage Control
Research Source: LuxAlgo Trading Slippage Analysis, MarketCalls API Optimization

Purpose:
- Monitor execution quality vs expected prices
- Dynamically adjust slippage tolerance based on market conditions
- Reject executions that exceed acceptable slippage
- Track slippage statistics for optimization

RESEARCH: Slippage can reduce algorithmic trading profits by up to 30%
for frequent small trades. Dynamic slippage controls outperform static bots.
"""

import logging
from enum import Enum
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from collections import deque

logger = logging.getLogger(__name__)


class SlippageLevel(Enum):
    """Slippage severity levels"""
    MINIMAL = "minimal"       # < 0.05%
    ACCEPTABLE = "acceptable" # 0.05% - 0.15%
    ELEVATED = "elevated"     # 0.15% - 0.30%
    HIGH = "high"            # 0.30% - 0.50%
    EXCESSIVE = "excessive"   # > 0.50%


class MarketCondition(Enum):
    """Market conditions affecting slippage"""
    NORMAL = "normal"
    VOLATILE = "volatile"
    LOW_LIQUIDITY = "low_liquidity"
    NEWS_EVENT = "news_event"


@dataclass
class SlippageConfig:
    """
    Configuration for slippage management

    RESEARCH-BACKED DEFAULTS:
    - Normal slippage: 0.1% - 0.3% is typical for crypto
    - Volatile markets: Allow up to 0.5%
    - Rejection threshold: Protect against extreme slippage
    """
    base_tolerance_pct: float = 0.15        # Normal market tolerance
    volatile_tolerance_pct: float = 0.30    # Volatile market tolerance
    rejection_threshold_pct: float = 0.50   # Reject if slippage exceeds this
    use_limit_orders: bool = True           # Prefer limit over market orders
    order_splitting_enabled: bool = True    # Split large orders
    max_order_value_for_market: float = 1000.0  # Use limit orders above this


@dataclass
class SlippageRecord:
    """Record of a single slippage event"""
    symbol: str
    expected_price: Decimal
    actual_price: Decimal
    slippage_pct: float
    slippage_amount: Decimal
    side: str  # BUY or SELL
    quantity: Decimal
    timestamp: datetime
    market_condition: MarketCondition
    was_rejected: bool = False


@dataclass
class SlippageStats:
    """Aggregate slippage statistics"""
    total_trades: int = 0
    total_slippage_pct: float = 0.0
    avg_slippage_pct: float = 0.0
    max_slippage_pct: float = 0.0
    min_slippage_pct: float = 0.0
    rejected_count: int = 0
    by_level: Dict[str, int] = field(default_factory=dict)
    by_symbol: Dict[str, float] = field(default_factory=dict)


class SlippageManager:
    """
    Dynamic Slippage Control Manager

    RESEARCH-BACKED IMPLEMENTATION:
    - Monitors slippage for all executions
    - Adjusts tolerance based on market conditions
    - Rejects executions exceeding threshold
    - Recommends limit orders for large trades
    - Tracks statistics for analysis

    Usage:
        slippage_mgr = SlippageManager()

        # Before execution
        tolerance = slippage_mgr.get_tolerance(symbol, market_condition)

        # After execution
        result = slippage_mgr.record_execution(
            symbol="BTCUSDT",
            expected_price=Decimal("50000"),
            actual_price=Decimal("50025"),
            side="BUY",
            quantity=Decimal("0.1")
        )

        if result.was_rejected:
            # Handle rejection
            pass
    """

    def __init__(self, config: Optional[SlippageConfig] = None):
        """
        Initialize slippage manager

        Args:
            config: Configuration settings
        """
        self.config = config or SlippageConfig()
        self.stats = SlippageStats()
        self._history: deque = deque(maxlen=1000)  # Rolling history
        self._current_condition = MarketCondition.NORMAL
        self._symbol_conditions: Dict[str, MarketCondition] = {}

        # Initialize level counts
        self.stats.by_level = {level.value: 0 for level in SlippageLevel}

        logger.info(
            f"SlippageManager initialized: "
            f"base_tolerance={self.config.base_tolerance_pct}%, "
            f"rejection_threshold={self.config.rejection_threshold_pct}%"
        )

    def get_tolerance(
        self,
        symbol: str,
        market_condition: Optional[MarketCondition] = None
    ) -> float:
        """
        Get current slippage tolerance for a symbol

        Args:
            symbol: Trading symbol
            market_condition: Current market condition

        Returns:
            Slippage tolerance as percentage
        """
        condition = market_condition or self._symbol_conditions.get(symbol, MarketCondition.NORMAL)

        if condition in (MarketCondition.VOLATILE, MarketCondition.NEWS_EVENT):
            tolerance = self.config.volatile_tolerance_pct
        elif condition == MarketCondition.LOW_LIQUIDITY:
            tolerance = self.config.volatile_tolerance_pct * 1.5  # Extra tolerance
        else:
            tolerance = self.config.base_tolerance_pct

        # Adjust based on recent symbol performance
        recent_avg = self._get_recent_average(symbol)
        if recent_avg > tolerance:
            # Market is showing higher slippage than expected
            tolerance = min(recent_avg * 1.2, self.config.rejection_threshold_pct)
            logger.debug(f"{symbol} tolerance adjusted to {tolerance:.2f}% based on history")

        return tolerance

    def _get_recent_average(self, symbol: str, lookback: int = 10) -> float:
        """Get average slippage for symbol from recent trades"""
        symbol_records = [r for r in self._history if r.symbol == symbol][-lookback:]
        if not symbol_records:
            return 0.0
        return sum(r.slippage_pct for r in symbol_records) / len(symbol_records)

    def set_market_condition(
        self,
        symbol: str,
        condition: MarketCondition
    ):
        """
        Set market condition for a symbol

        Args:
            symbol: Trading symbol
            condition: Current market condition
        """
        self._symbol_conditions[symbol] = condition
        logger.info(f"Market condition for {symbol}: {condition.value}")

    def validate_execution(
        self,
        expected_price: Decimal,
        actual_price: Decimal,
        side: str,
        symbol: str
    ) -> Tuple[bool, float, str]:
        """
        Validate an execution's slippage

        Args:
            expected_price: Expected execution price
            actual_price: Actual execution price
            side: BUY or SELL
            symbol: Trading symbol

        Returns:
            Tuple of (is_acceptable: bool, slippage_pct: float, message: str)
        """
        slippage_pct = self._calculate_slippage(expected_price, actual_price, side)
        tolerance = self.get_tolerance(symbol)

        # Determine slippage level
        level = self._classify_slippage(slippage_pct)

        if slippage_pct > self.config.rejection_threshold_pct:
            return False, slippage_pct, f"Slippage {slippage_pct:.3f}% exceeds rejection threshold"

        if slippage_pct > tolerance:
            return False, slippage_pct, f"Slippage {slippage_pct:.3f}% exceeds tolerance {tolerance:.2f}%"

        return True, slippage_pct, f"Slippage {slippage_pct:.3f}% ({level.value})"

    def record_execution(
        self,
        symbol: str,
        expected_price: Decimal,
        actual_price: Decimal,
        side: str,
        quantity: Decimal,
        market_condition: Optional[MarketCondition] = None
    ) -> SlippageRecord:
        """
        Record an execution and check slippage

        Args:
            symbol: Trading symbol
            expected_price: Expected execution price
            actual_price: Actual execution price
            side: BUY or SELL
            quantity: Execution quantity
            market_condition: Market condition at execution

        Returns:
            SlippageRecord with details
        """
        condition = market_condition or self._symbol_conditions.get(symbol, MarketCondition.NORMAL)
        slippage_pct = self._calculate_slippage(expected_price, actual_price, side)
        slippage_amount = abs(actual_price - expected_price) * quantity

        # Check if should reject
        is_acceptable, _, message = self.validate_execution(
            expected_price, actual_price, side, symbol
        )
        was_rejected = not is_acceptable

        # Create record
        record = SlippageRecord(
            symbol=symbol,
            expected_price=expected_price,
            actual_price=actual_price,
            slippage_pct=slippage_pct,
            slippage_amount=slippage_amount,
            side=side,
            quantity=quantity,
            timestamp=datetime.now(),
            market_condition=condition,
            was_rejected=was_rejected
        )

        # Update statistics
        self._update_stats(record)

        # Add to history
        self._history.append(record)

        # Log
        level = self._classify_slippage(slippage_pct)
        if was_rejected:
            logger.warning(
                f"SLIPPAGE REJECTED: {symbol} {side} | "
                f"Expected: ${expected_price:.2f} -> Actual: ${actual_price:.2f} | "
                f"Slippage: {slippage_pct:.3f}% (${slippage_amount:.2f})"
            )
        else:
            logger.info(
                f"Slippage recorded: {symbol} {side} | "
                f"{slippage_pct:.3f}% ({level.value}) | ${slippage_amount:.4f}"
            )

        return record

    def _calculate_slippage(
        self,
        expected_price: Decimal,
        actual_price: Decimal,
        side: str
    ) -> float:
        """
        Calculate slippage percentage

        Positive slippage = unfavorable (paid more / received less)
        Negative slippage = favorable (paid less / received more)

        Args:
            expected_price: Expected price
            actual_price: Actual price
            side: BUY or SELL

        Returns:
            Slippage as percentage (positive = bad, negative = good)
        """
        if expected_price == 0:
            return 0.0

        price_diff = float(actual_price - expected_price)
        expected = float(expected_price)

        if side == "BUY":
            # For buys, higher actual price = positive (bad) slippage
            slippage = (price_diff / expected) * 100
        else:
            # For sells, lower actual price = positive (bad) slippage
            slippage = (-price_diff / expected) * 100

        return slippage

    def _classify_slippage(self, slippage_pct: float) -> SlippageLevel:
        """Classify slippage into severity level"""
        abs_slippage = abs(slippage_pct)
        if abs_slippage < 0.05:
            return SlippageLevel.MINIMAL
        elif abs_slippage < 0.15:
            return SlippageLevel.ACCEPTABLE
        elif abs_slippage < 0.30:
            return SlippageLevel.ELEVATED
        elif abs_slippage < 0.50:
            return SlippageLevel.HIGH
        else:
            return SlippageLevel.EXCESSIVE

    def _update_stats(self, record: SlippageRecord):
        """Update aggregate statistics"""
        self.stats.total_trades += 1
        self.stats.total_slippage_pct += abs(record.slippage_pct)
        self.stats.avg_slippage_pct = self.stats.total_slippage_pct / self.stats.total_trades

        if record.slippage_pct > self.stats.max_slippage_pct:
            self.stats.max_slippage_pct = record.slippage_pct
        if self.stats.min_slippage_pct == 0 or record.slippage_pct < self.stats.min_slippage_pct:
            self.stats.min_slippage_pct = record.slippage_pct

        if record.was_rejected:
            self.stats.rejected_count += 1

        # By level
        level = self._classify_slippage(record.slippage_pct)
        self.stats.by_level[level.value] += 1

        # By symbol
        if record.symbol not in self.stats.by_symbol:
            self.stats.by_symbol[record.symbol] = 0.0
        self.stats.by_symbol[record.symbol] = self._get_recent_average(record.symbol)

    def should_use_limit_order(
        self,
        order_value: float,
        symbol: str
    ) -> Tuple[bool, str]:
        """
        Determine if limit order should be used instead of market

        RESEARCH: Limit orders reduce slippage but may not fill

        Args:
            order_value: Total order value
            symbol: Trading symbol

        Returns:
            Tuple of (should_use_limit: bool, reason: str)
        """
        if not self.config.use_limit_orders:
            return False, "Limit orders disabled"

        if order_value > self.config.max_order_value_for_market:
            return True, f"Order value ${order_value:.2f} exceeds market order limit"

        condition = self._symbol_conditions.get(symbol, MarketCondition.NORMAL)
        if condition == MarketCondition.VOLATILE:
            return True, "Volatile market conditions"

        recent_avg = self._get_recent_average(symbol)
        if recent_avg > self.config.base_tolerance_pct:
            return True, f"Recent slippage {recent_avg:.2f}% above normal"

        return False, "Market order acceptable"

    def get_recommended_limit_price(
        self,
        current_price: Decimal,
        side: str,
        tolerance_pct: Optional[float] = None
    ) -> Decimal:
        """
        Get recommended limit price for better execution

        Args:
            current_price: Current market price
            side: BUY or SELL
            tolerance_pct: Optional specific tolerance

        Returns:
            Recommended limit price
        """
        tolerance = Decimal(str(tolerance_pct or self.config.base_tolerance_pct)) / 100

        if side == "BUY":
            # For buys, set limit slightly below current price
            return current_price * (1 - tolerance / 2)
        else:
            # For sells, set limit slightly above current price
            return current_price * (1 + tolerance / 2)

    def get_status(self) -> Dict:
        """Get slippage manager status"""
        return {
            "config": {
                "base_tolerance_pct": self.config.base_tolerance_pct,
                "volatile_tolerance_pct": self.config.volatile_tolerance_pct,
                "rejection_threshold_pct": self.config.rejection_threshold_pct,
                "use_limit_orders": self.config.use_limit_orders,
            },
            "stats": {
                "total_trades": self.stats.total_trades,
                "avg_slippage_pct": round(self.stats.avg_slippage_pct, 4),
                "max_slippage_pct": round(self.stats.max_slippage_pct, 4),
                "rejected_count": self.stats.rejected_count,
                "rejection_rate": round(
                    self.stats.rejected_count / self.stats.total_trades * 100, 2
                ) if self.stats.total_trades > 0 else 0,
            },
            "by_level": self.stats.by_level,
            "by_symbol": {k: round(v, 4) for k, v in self.stats.by_symbol.items()},
            "market_conditions": {k: v.value for k, v in self._symbol_conditions.items()},
        }


# Global slippage manager instance
_slippage_manager: Optional[SlippageManager] = None


def get_slippage_manager(config: Optional[SlippageConfig] = None) -> SlippageManager:
    """Get or create global slippage manager"""
    global _slippage_manager
    if _slippage_manager is None:
        _slippage_manager = SlippageManager(config)
    return _slippage_manager
