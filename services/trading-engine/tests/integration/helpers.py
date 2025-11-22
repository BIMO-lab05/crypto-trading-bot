"""
Integration Test Helper Utilities
Purpose: Provide utility functions for integration tests

Utilities:
- Data generators
- Assertion helpers
- Test data builders
- Mock helpers
"""

from decimal import Decimal
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from uuid import uuid4

from app.models import (
    TradingSignal,
    IndicatorSignal,
    SignalAction,
    OrderCreate,
    OrderSide,
    OrderType,
    Position,
    PositionSide,
    PositionStatus,
)


# ============================================================================
# SIGNAL GENERATORS
# ============================================================================

def generate_buy_signal(
    symbol: str = "BTCUSDT",
    confidence: float = 0.75,
    price: float = 50000.0,
    num_indicators: int = 5,
) -> TradingSignal:
    """
    Generate a BUY trading signal with specified parameters

    Args:
        symbol: Trading symbol
        confidence: Overall signal confidence (0-1)
        price: Current market price
        num_indicators: Number of indicators to include

    Returns:
        TradingSignal configured for BUY action
    """
    # Create indicator signals
    indicators = {}

    if num_indicators >= 1:
        indicators["rsi"] = IndicatorSignal(
            name="RSI",
            value=35.0,  # Oversold
            signal=SignalAction.BUY,
            confidence=0.70,
            weight=1.0,
            metadata={"current_price": price, "period": 14},
        )

    if num_indicators >= 2:
        indicators["macd"] = IndicatorSignal(
            name="MACD",
            value=15.5,
            signal=SignalAction.BUY,
            confidence=0.75,
            weight=1.0,
            metadata={"current_price": price, "signal_line": 12.0},
        )

    if num_indicators >= 3:
        indicators["bollinger"] = IndicatorSignal(
            name="Bollinger Bands",
            value=price - 1000,  # Below lower band
            signal=SignalAction.BUY,
            confidence=0.65,
            weight=0.8,
            metadata={"current_price": price, "lower_band": price - 1000},
        )

    if num_indicators >= 4:
        indicators["ema"] = IndicatorSignal(
            name="EMA",
            value=price - 500,
            signal=SignalAction.BUY,
            confidence=0.72,
            weight=0.9,
            metadata={"current_price": price, "ema_9": price - 500, "ema_21": price - 800},
        )

    if num_indicators >= 5:
        indicators["volume"] = IndicatorSignal(
            name="Volume",
            value=1500000.0,
            signal=SignalAction.BUY,
            confidence=0.60,
            weight=0.7,
            metadata={"current_price": price, "avg_volume": 1200000.0},
        )

    return TradingSignal(
        symbol=symbol,
        action=SignalAction.BUY,
        confidence=confidence,
        aggregated_score=confidence,
        consensus_strength=0.85,
        indicators=indicators,
        timeframe="60",
        metadata={
            "meets_requirements": True,
            "required_indicators": 3,
            "aligned_indicators": len(indicators),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


def generate_sell_signal(
    symbol: str = "BTCUSDT",
    confidence: float = 0.72,
    price: float = 51000.0,
    num_indicators: int = 5,
) -> TradingSignal:
    """
    Generate a SELL trading signal with specified parameters

    Args:
        symbol: Trading symbol
        confidence: Overall signal confidence (0-1)
        price: Current market price
        num_indicators: Number of indicators to include

    Returns:
        TradingSignal configured for SELL action
    """
    # Create indicator signals
    indicators = {}

    if num_indicators >= 1:
        indicators["rsi"] = IndicatorSignal(
            name="RSI",
            value=75.0,  # Overbought
            signal=SignalAction.SELL,
            confidence=0.75,
            weight=1.0,
            metadata={"current_price": price, "period": 14},
        )

    if num_indicators >= 2:
        indicators["macd"] = IndicatorSignal(
            name="MACD",
            value=-12.5,
            signal=SignalAction.SELL,
            confidence=0.70,
            weight=1.0,
            metadata={"current_price": price, "signal_line": -10.0},
        )

    if num_indicators >= 3:
        indicators["bollinger"] = IndicatorSignal(
            name="Bollinger Bands",
            value=price + 1000,  # Above upper band
            signal=SignalAction.SELL,
            confidence=0.68,
            weight=0.8,
            metadata={"current_price": price, "upper_band": price + 1000},
        )

    if num_indicators >= 4:
        indicators["ema"] = IndicatorSignal(
            name="EMA",
            value=price + 500,
            signal=SignalAction.SELL,
            confidence=0.72,
            weight=0.9,
            metadata={"current_price": price, "ema_9": price + 500, "ema_21": price + 800},
        )

    if num_indicators >= 5:
        indicators["volume"] = IndicatorSignal(
            name="Volume",
            value=800000.0,
            signal=SignalAction.SELL,
            confidence=0.58,
            weight=0.7,
            metadata={"current_price": price, "avg_volume": 1200000.0},
        )

    return TradingSignal(
        symbol=symbol,
        action=SignalAction.SELL,
        confidence=confidence,
        aggregated_score=confidence,
        consensus_strength=0.80,
        indicators=indicators,
        timeframe="60",
        metadata={
            "meets_requirements": True,
            "required_indicators": 3,
            "aligned_indicators": len(indicators),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


def generate_hold_signal(
    symbol: str = "BTCUSDT",
    confidence: float = 0.45,
    price: float = 50500.0,
) -> TradingSignal:
    """
    Generate a HOLD/NEUTRAL trading signal

    Args:
        symbol: Trading symbol
        confidence: Overall signal confidence (0-1)
        price: Current market price

    Returns:
        TradingSignal configured for HOLD action
    """
    return TradingSignal(
        symbol=symbol,
        action=SignalAction.HOLD,
        confidence=confidence,
        aggregated_score=confidence,
        consensus_strength=0.30,
        indicators={
            "rsi": IndicatorSignal(
                name="RSI",
                value=55.0,  # Neutral
                signal=SignalAction.HOLD,
                confidence=0.40,
                weight=1.0,
                metadata={"current_price": price},
            ),
        },
        timeframe="60",
        metadata={
            "meets_requirements": False,
            "required_indicators": 3,
            "aligned_indicators": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


# ============================================================================
# ORDER BUILDERS
# ============================================================================

def create_market_buy_order(
    symbol: str = "BTCUSDT",
    quantity: Decimal = Decimal("0.01"),
    strategy: str = "test",
) -> OrderCreate:
    """
    Create a market BUY order

    Args:
        symbol: Trading symbol
        quantity: Order quantity
        strategy: Strategy name

    Returns:
        OrderCreate object for BUY market order
    """
    return OrderCreate(
        symbol=symbol,
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        quantity=quantity,
        strategy=strategy,
    )


def create_market_sell_order(
    symbol: str = "BTCUSDT",
    quantity: Decimal = Decimal("0.01"),
    strategy: str = "test",
) -> OrderCreate:
    """
    Create a market SELL order

    Args:
        symbol: Trading symbol
        quantity: Order quantity
        strategy: Strategy name

    Returns:
        OrderCreate object for SELL market order
    """
    return OrderCreate(
        symbol=symbol,
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=quantity,
        strategy=strategy,
    )


# ============================================================================
# TRADE SCENARIO BUILDERS
# ============================================================================

class TradeScenario:
    """
    Builder for complete trade scenarios

    Simplifies creating complex multi-step trading scenarios for tests
    """

    def __init__(self, symbol: str = "BTCUSDT"):
        """
        Initialize trade scenario builder

        Args:
            symbol: Trading symbol for scenario
        """
        self.symbol = symbol
        self.steps: List[Dict[str, Any]] = []

    def add_buy(
        self,
        price: Decimal,
        quantity: Decimal,
        strategy: str = "test",
    ) -> "TradeScenario":
        """
        Add a BUY step to scenario

        Args:
            price: Buy price
            quantity: Buy quantity
            strategy: Strategy name

        Returns:
            Self for method chaining
        """
        self.steps.append({
            "action": "BUY",
            "price": price,
            "quantity": quantity,
            "strategy": strategy,
        })
        return self

    def add_sell(
        self,
        price: Decimal,
        quantity: Decimal,
        strategy: str = "test",
    ) -> "TradeScenario":
        """
        Add a SELL step to scenario

        Args:
            price: Sell price
            quantity: Sell quantity
            strategy: Strategy name

        Returns:
            Self for method chaining
        """
        self.steps.append({
            "action": "SELL",
            "price": price,
            "quantity": quantity,
            "strategy": strategy,
        })
        return self

    def add_profitable_cycle(
        self,
        entry_price: Decimal,
        exit_price: Decimal,
        quantity: Decimal,
    ) -> "TradeScenario":
        """
        Add a complete profitable trade cycle (buy low, sell high)

        Args:
            entry_price: Entry (buy) price
            exit_price: Exit (sell) price
            quantity: Trade quantity

        Returns:
            Self for method chaining
        """
        assert exit_price > entry_price, "Exit price must be higher for profit"
        self.add_buy(entry_price, quantity)
        self.add_sell(exit_price, quantity)
        return self

    def add_losing_cycle(
        self,
        entry_price: Decimal,
        exit_price: Decimal,
        quantity: Decimal,
    ) -> "TradeScenario":
        """
        Add a complete losing trade cycle (buy high, sell low)

        Args:
            entry_price: Entry (buy) price
            exit_price: Exit (sell) price
            quantity: Trade quantity

        Returns:
            Self for method chaining
        """
        assert exit_price < entry_price, "Exit price must be lower for loss"
        self.add_buy(entry_price, quantity)
        self.add_sell(exit_price, quantity)
        return self

    async def execute(self, paper_engine) -> List[Dict[str, Any]]:
        """
        Execute all steps in scenario

        Args:
            paper_engine: PaperTradingEngine instance

        Returns:
            List of execution results
        """
        results = []

        for step in self.steps:
            order = OrderCreate(
                symbol=self.symbol,
                side=OrderSide.BUY if step["action"] == "BUY" else OrderSide.SELL,
                type=OrderType.MARKET,
                quantity=step["quantity"],
                strategy=step["strategy"],
            )

            executed_order, error = await paper_engine.execute_market_order(
                order, step["price"]
            )

            results.append({
                "order": executed_order,
                "error": error,
                "step": step,
            })

        return results


# ============================================================================
# ASSERTION HELPERS
# ============================================================================

def assert_trade_profitable(
    entry_price: Decimal,
    exit_price: Decimal,
    quantity: Decimal,
    commission_pct: Decimal = Decimal("0.001"),
) -> Decimal:
    """
    Assert trade is profitable and return expected profit

    Args:
        entry_price: Entry price
        exit_price: Exit price
        quantity: Trade quantity
        commission_pct: Commission percentage

    Returns:
        Expected net profit

    Raises:
        AssertionError: If trade would be unprofitable
    """
    gross_profit = (exit_price - entry_price) * quantity
    buy_commission = (entry_price * quantity) * commission_pct
    sell_commission = (exit_price * quantity) * commission_pct
    net_profit = gross_profit - buy_commission - sell_commission

    assert net_profit > 0, (
        f"Trade should be profitable. "
        f"Gross: {gross_profit}, Commissions: {buy_commission + sell_commission}, "
        f"Net: {net_profit}"
    )

    return net_profit


def assert_position_size_valid(
    position_value: Decimal,
    portfolio_value: Decimal,
    max_pct: Decimal = Decimal("2.0"),
) -> None:
    """
    Assert position size is within limits

    Args:
        position_value: Position value in USDT
        portfolio_value: Total portfolio value
        max_pct: Maximum position size percentage

    Raises:
        AssertionError: If position size exceeds limit
    """
    actual_pct = (position_value / portfolio_value) * Decimal("100")
    assert actual_pct <= max_pct, (
        f"Position size {actual_pct:.2f}% exceeds maximum {max_pct:.2f}%"
    )


def assert_balance_reasonable(
    balance: Decimal,
    expected_range: tuple[Decimal, Decimal],
) -> None:
    """
    Assert balance is within reasonable range

    Args:
        balance: Actual balance
        expected_range: Tuple of (min, max) expected balance

    Raises:
        AssertionError: If balance outside range
    """
    min_balance, max_balance = expected_range
    assert min_balance <= balance <= max_balance, (
        f"Balance {balance} outside expected range [{min_balance}, {max_balance}]"
    )


# ============================================================================
# DATA VALIDATORS
# ============================================================================

def validate_signal_structure(signal: TradingSignal) -> None:
    """
    Validate trading signal has all required fields

    Args:
        signal: TradingSignal to validate

    Raises:
        AssertionError: If signal structure is invalid
    """
    assert signal.symbol is not None, "Signal missing symbol"
    assert signal.action in [SignalAction.BUY, SignalAction.SELL, SignalAction.HOLD]
    assert 0.0 <= signal.confidence <= 1.0, f"Invalid confidence: {signal.confidence}"
    assert signal.indicators is not None, "Signal missing indicators"
    assert len(signal.indicators) > 0, "Signal has no indicators"
    assert signal.timeframe is not None, "Signal missing timeframe"


def validate_position_state(position: Position) -> None:
    """
    Validate position object has consistent state

    Args:
        position: Position to validate

    Raises:
        AssertionError: If position state is invalid
    """
    assert position.symbol is not None, "Position missing symbol"
    assert position.quantity > 0, f"Invalid quantity: {position.quantity}"
    assert position.entry_price > 0, f"Invalid entry price: {position.entry_price}"

    if position.status == PositionStatus.CLOSED:
        assert position.exit_price is not None, "Closed position missing exit price"
        assert position.realized_pnl is not None, "Closed position missing realized P&L"
        assert position.closed_at is not None, "Closed position missing closed_at timestamp"


# ============================================================================
# TIME HELPERS
# ============================================================================

def get_test_timestamp(offset_seconds: int = 0) -> datetime:
    """
    Get consistent test timestamp

    Args:
        offset_seconds: Seconds to offset from current time

    Returns:
        Datetime in UTC timezone
    """
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)


def format_timestamp(dt: datetime) -> str:
    """
    Format datetime as ISO string for tests

    Args:
        dt: Datetime to format

    Returns:
        ISO format string
    """
    return dt.isoformat()


# ============================================================================
# MARKET DATA GENERATORS
# ============================================================================

def generate_price_series(
    start_price: Decimal,
    num_points: int,
    volatility: Decimal = Decimal("0.01"),
) -> List[Decimal]:
    """
    Generate realistic price series with random walk

    Args:
        start_price: Starting price
        num_points: Number of price points
        volatility: Price volatility (percentage)

    Returns:
        List of prices
    """
    import random

    prices = [start_price]
    for _ in range(num_points - 1):
        change_pct = Decimal(str(random.uniform(-float(volatility), float(volatility))))
        change = prices[-1] * change_pct
        new_price = prices[-1] + change
        prices.append(new_price)

    return prices


# ============================================================================
# MOCK RESPONSE BUILDERS
# ============================================================================

def build_indicator_response(
    indicator_name: str,
    signal: str = "BUY",
    confidence: float = 0.70,
    value: float = 50.0,
    **metadata,
) -> Dict[str, Any]:
    """
    Build mock indicator API response

    Args:
        indicator_name: Name of indicator
        signal: Signal type (BUY/SELL/HOLD)
        confidence: Confidence score
        value: Indicator value
        **metadata: Additional metadata fields

    Returns:
        Dictionary formatted as API response
    """
    return {
        "success": True,
        "data": {
            "indicator": indicator_name,
            "value": value,
            "signal": signal,
            "confidence": confidence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **metadata,
        },
    }


# ============================================================================
# SUMMARY
# ============================================================================

"""
Helper Utilities Summary:

Signal Generators:
- generate_buy_signal()
- generate_sell_signal()
- generate_hold_signal()

Order Builders:
- create_market_buy_order()
- create_market_sell_order()

Trade Scenarios:
- TradeScenario class with fluent API

Assertion Helpers:
- assert_trade_profitable()
- assert_position_size_valid()
- assert_balance_reasonable()

Validators:
- validate_signal_structure()
- validate_position_state()

Time Utilities:
- get_test_timestamp()
- format_timestamp()

Market Data:
- generate_price_series()

Mock Builders:
- build_indicator_response()

Usage Example:
    # Create profitable trade scenario
    scenario = (TradeScenario("BTCUSDT")
                .add_profitable_cycle(
                    Decimal("50000"),
                    Decimal("52000"),
                    Decimal("0.02")
                ))
    results = await scenario.execute(paper_engine)
"""
