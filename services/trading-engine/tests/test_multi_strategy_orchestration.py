"""
Test Suite for Multi-Strategy Orchestration System
===================================================
Purpose: Verify all components of Phase 9 multi-strategy orchestration

Tests:
1. Base Strategy class functionality
2. Individual strategy implementations (Mean Reversion, Trend Following, Breakout, Arbitrage)
3. Signal Aggregator with multiple aggregation methods
4. Strategy Coordinator for signal flow and risk management
5. Backtester for historical simulation
6. Integration test running multiple strategies in parallel

Author: Backend Developer Agent
Date: 2025-12-11
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Dict, Any
import statistics

# Import components to test
from app.strategies.base import (
    StrategyBase,
    StrategySignal,
    AnalysisResult,
    StrategyCategory,
    StrategyRiskLevel,
    SignalType,
    MarketCondition,
    create_signal,
)
from app.strategies.mean_reversion import (
    MeanReversionStrategy,
    MeanReversionConfig,
    create_mean_reversion_strategy,
)
from app.strategies.trend_following import (
    TrendFollowingStrategy,
    TrendFollowingConfig,
    create_trend_following_strategy,
)
from app.strategies.breakout import (
    BreakoutStrategy,
    BreakoutConfig,
    create_breakout_strategy,
)
from app.strategies.arbitrage import (
    ArbitrageStrategy,
    ArbitrageConfig,
    create_arbitrage_strategy,
)
from app.strategies.aggregator import (
    SignalAggregator,
    AggregatorConfig,
    AggregationMethod,
    SignalDirection,
)
from app.strategies.coordinator import (
    StrategyCoordinator,
    CoordinatorConfig,
)
from app.strategies.backtester import (
    StrategyBacktester,
    BacktestConfig,
    BacktestCandle,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def mock_candles() -> List[Dict[str, Any]]:
    """Generate mock candle data for testing"""
    base_price = 42000.0
    candles = []

    for i in range(300):
        # Create price movement pattern
        trend = 0.0001 * i  # Slight uptrend
        noise = (i % 20 - 10) * 0.001  # Oscillation
        volatility = 0.002 * (1 + (i % 10) / 10)  # Variable volatility

        open_price = base_price * (1 + trend + noise)
        high_price = open_price * (1 + volatility)
        low_price = open_price * (1 - volatility)
        close_price = open_price * (1 + noise * 0.5)

        candle = {
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=300-i)).isoformat(),
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": 1000000 * (1 + (i % 5) * 0.2),
            "o": open_price,
            "h": high_price,
            "l": low_price,
            "c": close_price,
            "v": 1000000 * (1 + (i % 5) * 0.2),
        }
        candles.append(candle)

    return candles


@pytest.fixture
def mock_backtest_candles() -> List[BacktestCandle]:
    """Generate BacktestCandle objects for testing"""
    base_price = 42000.0
    candles = []

    for i in range(200):
        trend = 0.0001 * i
        noise = (i % 20 - 10) * 0.001
        volatility = 0.002 * (1 + (i % 10) / 10)

        open_price = base_price * (1 + trend + noise)
        high_price = open_price * (1 + volatility)
        low_price = open_price * (1 - volatility)
        close_price = open_price * (1 + noise * 0.5)

        candle = BacktestCandle(
            timestamp=datetime.now(timezone.utc) - timedelta(hours=200-i),
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=1000000 * (1 + (i % 5) * 0.2),
        )
        candles.append(candle)

    return candles


@pytest.fixture
def mean_reversion_strategy() -> MeanReversionStrategy:
    """Create mean reversion strategy for testing"""
    return create_mean_reversion_strategy(
        symbols=["BTCUSDT", "ETHUSDT"],
        timeframe="60"
    )


@pytest.fixture
def trend_following_strategy() -> TrendFollowingStrategy:
    """Create trend following strategy for testing"""
    return create_trend_following_strategy(
        symbols=["BTCUSDT", "ETHUSDT"],
        timeframe="60"
    )


@pytest.fixture
def breakout_strategy() -> BreakoutStrategy:
    """Create breakout strategy for testing"""
    return create_breakout_strategy(
        symbols=["BTCUSDT", "ETHUSDT"],
        timeframe="60"
    )


@pytest.fixture
def arbitrage_strategy() -> ArbitrageStrategy:
    """Create arbitrage strategy for testing"""
    return create_arbitrage_strategy(
        trading_pairs=[("BTCUSDT", "ETHUSDT")],
        timeframe="15"
    )


@pytest.fixture
def signal_aggregator() -> SignalAggregator:
    """Create signal aggregator for testing"""
    config = AggregatorConfig(
        min_strategies_for_action=2,
        min_confidence_threshold=0.4
    )
    return SignalAggregator(config)


@pytest.fixture
def strategy_coordinator() -> StrategyCoordinator:
    """Create strategy coordinator for testing"""
    config = CoordinatorConfig(
        total_risk_budget_pct=10.0,
        max_concurrent_positions=5,
        require_aggregation_for_action=False  # Allow single strategy for testing
    )
    return StrategyCoordinator(config)


# =============================================================================
# BASE STRATEGY TESTS
# =============================================================================

class TestBaseStrategy:
    """Test base strategy functionality"""

    def test_create_signal(self):
        """Test signal creation with factory function"""
        signal = create_signal(
            strategy_id="test_strategy",
            symbol="BTCUSDT",
            signal_type=SignalType.ENTRY_LONG,
            entry_price=Decimal("42000"),
            stop_loss_pct=2.0,
            take_profit_pct=4.0,
            confidence=0.7,
            reasoning="Test signal"
        )

        assert signal.strategy_id == "test_strategy"
        assert signal.symbol == "BTCUSDT"
        assert signal.signal_type == SignalType.ENTRY_LONG
        assert signal.confidence == 0.7
        assert signal.stop_loss is not None
        assert signal.take_profit is not None
        assert signal.risk_reward_ratio == pytest.approx(2.0, rel=0.01)

    def test_signal_properties(self):
        """Test signal property methods"""
        long_signal = create_signal(
            strategy_id="test",
            symbol="BTCUSDT",
            signal_type=SignalType.ENTRY_LONG,
            entry_price=Decimal("42000"),
            stop_loss_pct=2.0,
            take_profit_pct=4.0,
            confidence=0.5
        )

        assert long_signal.is_entry_signal
        assert not long_signal.is_exit_signal
        assert long_signal.is_long
        assert not long_signal.is_short

    def test_signal_expiry(self):
        """Test signal expiry detection"""
        signal = create_signal(
            strategy_id="test",
            symbol="BTCUSDT",
            signal_type=SignalType.ENTRY_LONG,
            entry_price=Decimal("42000"),
            stop_loss_pct=2.0,
            take_profit_pct=4.0,
            confidence=0.5
        )
        signal.expiry_seconds = 1  # Very short expiry

        # Signal should not be expired immediately
        assert not signal.is_expired

        # Manually set old timestamp
        signal.timestamp = datetime.now(timezone.utc) - timedelta(seconds=10)
        assert signal.is_expired


# =============================================================================
# MEAN REVERSION STRATEGY TESTS
# =============================================================================

class TestMeanReversionStrategy:
    """Test mean reversion strategy"""

    @pytest.mark.asyncio
    async def test_strategy_initialization(self, mean_reversion_strategy):
        """Test strategy initializes correctly"""
        assert mean_reversion_strategy.strategy_id == "mean_reversion_v1"
        assert mean_reversion_strategy.metadata.category == StrategyCategory.MEAN_REVERSION
        assert mean_reversion_strategy.metadata.risk_level == StrategyRiskLevel.MODERATE

    @pytest.mark.asyncio
    async def test_analyze_returns_result(self, mean_reversion_strategy, mock_candles):
        """Test analyze method returns valid result"""
        await mean_reversion_strategy.on_initialize()

        data = {"candles": mock_candles}
        analysis = await mean_reversion_strategy.analyze("BTCUSDT", data)

        assert isinstance(analysis, AnalysisResult)
        assert analysis.symbol == "BTCUSDT"
        assert analysis.condition in MarketCondition
        assert 0 <= analysis.confidence <= 1

    @pytest.mark.asyncio
    async def test_generate_signals(self, mean_reversion_strategy, mock_candles):
        """Test signal generation"""
        await mean_reversion_strategy.on_initialize()

        data = {"candles": mock_candles}
        analysis = await mean_reversion_strategy.analyze("BTCUSDT", data)

        current_price = Decimal(str(mock_candles[-1]["close"]))
        signals = await mean_reversion_strategy.generate_signals(
            "BTCUSDT", analysis, current_price
        )

        assert isinstance(signals, list)
        for signal in signals:
            assert isinstance(signal, StrategySignal)
            assert signal.strategy_id == "mean_reversion_v1"

    def test_position_sizing(self, mean_reversion_strategy):
        """Test position size calculation"""
        signal = create_signal(
            strategy_id="mean_reversion_v1",
            symbol="BTCUSDT",
            signal_type=SignalType.ENTRY_LONG,
            entry_price=Decimal("42000"),
            stop_loss_pct=2.0,
            take_profit_pct=3.0,
            confidence=0.6
        )

        quantity, risk_amount = mean_reversion_strategy.calculate_position_size(
            signal,
            available_capital=10000.0,
            risk_per_trade_pct=1.5
        )

        assert quantity > 0
        assert risk_amount == pytest.approx(150.0, rel=0.01)  # 1.5% of 10000


# =============================================================================
# TREND FOLLOWING STRATEGY TESTS
# =============================================================================

class TestTrendFollowingStrategy:
    """Test trend following strategy"""

    @pytest.mark.asyncio
    async def test_strategy_initialization(self, trend_following_strategy):
        """Test strategy initializes correctly"""
        assert trend_following_strategy.strategy_id == "trend_following_v1"
        assert trend_following_strategy.metadata.category == StrategyCategory.TREND_FOLLOWING

    @pytest.mark.asyncio
    async def test_analyze_returns_result(self, trend_following_strategy, mock_candles):
        """Test analyze method returns valid result"""
        await trend_following_strategy.on_initialize()

        data = {"candles": mock_candles}
        analysis = await trend_following_strategy.analyze("BTCUSDT", data)

        assert isinstance(analysis, AnalysisResult)
        assert analysis.symbol == "BTCUSDT"
        assert "ema_fast" in analysis.indicators
        assert "adx" in analysis.indicators


# =============================================================================
# BREAKOUT STRATEGY TESTS
# =============================================================================

class TestBreakoutStrategy:
    """Test breakout strategy"""

    @pytest.mark.asyncio
    async def test_strategy_initialization(self, breakout_strategy):
        """Test strategy initializes correctly"""
        assert breakout_strategy.strategy_id == "breakout_v1"
        assert breakout_strategy.metadata.category == StrategyCategory.BREAKOUT
        assert breakout_strategy.metadata.risk_level == StrategyRiskLevel.AGGRESSIVE

    @pytest.mark.asyncio
    async def test_analyze_returns_result(self, breakout_strategy, mock_candles):
        """Test analyze method returns valid result"""
        await breakout_strategy.on_initialize()

        data = {"candles": mock_candles}
        analysis = await breakout_strategy.analyze("BTCUSDT", data)

        assert isinstance(analysis, AnalysisResult)
        assert "is_consolidating" in analysis.indicators
        assert "support" in str(type(analysis.support_levels)) or analysis.support_levels is not None


# =============================================================================
# SIGNAL AGGREGATOR TESTS
# =============================================================================

class TestSignalAggregator:
    """Test signal aggregator"""

    def test_aggregator_initialization(self, signal_aggregator):
        """Test aggregator initializes correctly"""
        assert signal_aggregator.config.min_strategies_for_action == 2

    def test_add_single_signal(self, signal_aggregator):
        """Test adding a single signal"""
        signal = create_signal(
            strategy_id="strategy_1",
            symbol="BTCUSDT",
            signal_type=SignalType.ENTRY_LONG,
            entry_price=Decimal("42000"),
            stop_loss_pct=2.0,
            take_profit_pct=4.0,
            confidence=0.7
        )

        result = signal_aggregator.add_signal(signal)
        assert result["accepted"]
        assert result["pending_count"] == 1

    def test_majority_vote_aggregation(self, signal_aggregator):
        """Test majority vote aggregation method"""
        # Add 3 long signals, 1 short signal
        for i in range(3):
            signal = create_signal(
                strategy_id=f"strategy_{i}",
                symbol="BTCUSDT",
                signal_type=SignalType.ENTRY_LONG,
                entry_price=Decimal("42000"),
                stop_loss_pct=2.0,
                take_profit_pct=4.0,
                confidence=0.7
            )
            signal_aggregator.add_signal(signal)

        short_signal = create_signal(
            strategy_id="strategy_3",
            symbol="BTCUSDT",
            signal_type=SignalType.ENTRY_SHORT,
            entry_price=Decimal("42000"),
            stop_loss_pct=2.0,
            take_profit_pct=4.0,
            confidence=0.6
        )
        signal_aggregator.add_signal(short_signal)

        result = signal_aggregator.aggregate("BTCUSDT", AggregationMethod.MAJORITY_VOTE)

        assert result is not None
        assert result.direction == SignalDirection.LONG
        assert result.agreement_ratio == pytest.approx(0.75, rel=0.01)

    def test_weighted_average_aggregation(self, signal_aggregator):
        """Test weighted average aggregation"""
        # Set different weights for strategies
        signal_aggregator.set_strategy_weight("strategy_1", 2.0)
        signal_aggregator.set_strategy_weight("strategy_2", 1.0)

        signal_1 = create_signal(
            strategy_id="strategy_1",
            symbol="BTCUSDT",
            signal_type=SignalType.ENTRY_LONG,
            entry_price=Decimal("42000"),
            stop_loss_pct=2.0,
            take_profit_pct=4.0,
            confidence=0.8
        )
        signal_2 = create_signal(
            strategy_id="strategy_2",
            symbol="BTCUSDT",
            signal_type=SignalType.ENTRY_SHORT,
            entry_price=Decimal("42000"),
            stop_loss_pct=2.0,
            take_profit_pct=4.0,
            confidence=0.6
        )

        signal_aggregator.add_signal(signal_1)
        signal_aggregator.add_signal(signal_2)

        result = signal_aggregator.aggregate("BTCUSDT", AggregationMethod.WEIGHTED_AVERAGE)

        # Strategy 1 has higher weight, so LONG should win
        assert result is not None
        assert result.direction == SignalDirection.LONG

    def test_unanimous_aggregation_agreement(self, signal_aggregator):
        """Test unanimous aggregation when all agree"""
        for i in range(3):
            signal = create_signal(
                strategy_id=f"strategy_{i}",
                symbol="BTCUSDT",
                signal_type=SignalType.ENTRY_LONG,
                entry_price=Decimal("42000"),
                stop_loss_pct=2.0,
                take_profit_pct=4.0,
                confidence=0.7
            )
            signal_aggregator.add_signal(signal)

        result = signal_aggregator.aggregate("BTCUSDT", AggregationMethod.UNANIMOUS)

        assert result is not None
        assert result.is_actionable
        assert result.agreement_ratio == 1.0

    def test_unanimous_aggregation_disagreement(self, signal_aggregator):
        """Test unanimous aggregation when strategies disagree"""
        signal_1 = create_signal(
            strategy_id="strategy_1",
            symbol="BTCUSDT",
            signal_type=SignalType.ENTRY_LONG,
            entry_price=Decimal("42000"),
            stop_loss_pct=2.0,
            take_profit_pct=4.0,
            confidence=0.7
        )
        signal_2 = create_signal(
            strategy_id="strategy_2",
            symbol="BTCUSDT",
            signal_type=SignalType.ENTRY_SHORT,
            entry_price=Decimal("42000"),
            stop_loss_pct=2.0,
            take_profit_pct=4.0,
            confidence=0.7
        )

        signal_aggregator.add_signal(signal_1)
        signal_aggregator.add_signal(signal_2)

        result = signal_aggregator.aggregate("BTCUSDT", AggregationMethod.UNANIMOUS)

        assert result is not None
        assert not result.is_actionable
        assert result.direction == SignalDirection.NEUTRAL


# =============================================================================
# STRATEGY COORDINATOR TESTS
# =============================================================================

class TestStrategyCoordinator:
    """Test strategy coordinator"""

    @pytest.mark.asyncio
    async def test_register_strategy(self, strategy_coordinator, mean_reversion_strategy):
        """Test registering a strategy"""
        result = strategy_coordinator.register_strategy(mean_reversion_strategy)

        assert result["success"]
        assert result["strategy_id"] == "mean_reversion_v1"
        assert strategy_coordinator.is_strategy_enabled("mean_reversion_v1")

    @pytest.mark.asyncio
    async def test_submit_signal(self, strategy_coordinator, mean_reversion_strategy):
        """Test submitting a signal"""
        strategy_coordinator.register_strategy(mean_reversion_strategy)

        signal = create_signal(
            strategy_id="mean_reversion_v1",
            symbol="BTCUSDT",
            signal_type=SignalType.ENTRY_LONG,
            entry_price=Decimal("42000"),
            stop_loss_pct=2.0,
            take_profit_pct=4.0,
            confidence=0.7
        )

        result = strategy_coordinator.submit_signal(signal)
        assert result["accepted"]

    @pytest.mark.asyncio
    async def test_position_tracking(self, strategy_coordinator, mean_reversion_strategy):
        """Test position tracking"""
        strategy_coordinator.register_strategy(mean_reversion_strategy)

        # Record position open
        result = strategy_coordinator.record_position_opened(
            position_id="pos_1",
            symbol="BTCUSDT",
            strategy_id="mean_reversion_v1",
            side="LONG",
            entry_price=42000.0,
            quantity=0.1,
            risk_pct=1.5
        )

        assert result["success"]

        status = strategy_coordinator.get_position_status()
        assert status["total_positions"] == 1

        # Record position close
        result = strategy_coordinator.record_position_closed(
            position_id="pos_1",
            exit_price=43000.0,
            pnl=100.0
        )

        assert result["success"]

        status = strategy_coordinator.get_position_status()
        assert status["total_positions"] == 0

    @pytest.mark.asyncio
    async def test_risk_budget(self, strategy_coordinator, mean_reversion_strategy):
        """Test risk budget management"""
        strategy_coordinator.register_strategy(mean_reversion_strategy)

        # Open position using risk budget
        strategy_coordinator.record_position_opened(
            position_id="pos_1",
            symbol="BTCUSDT",
            strategy_id="mean_reversion_v1",
            side="LONG",
            entry_price=42000.0,
            quantity=0.1,
            risk_pct=5.0
        )

        budget_status = strategy_coordinator.get_risk_budget_status()
        assert budget_status["used_pct"] == pytest.approx(5.0, rel=0.01)
        assert budget_status["available_pct"] == pytest.approx(5.0, rel=0.01)


# =============================================================================
# BACKTESTER TESTS
# =============================================================================

class TestBacktester:
    """Test backtester functionality"""

    def test_backtester_initialization(self):
        """Test backtester initializes correctly"""
        config = BacktestConfig(
            initial_capital=10000.0,
            slippage_pct=0.05
        )
        backtester = StrategyBacktester(config)

        assert backtester.config.initial_capital == 10000.0
        assert backtester.config.slippage_pct == 0.05

    @pytest.mark.asyncio
    async def test_run_backtest(self, mean_reversion_strategy, mock_backtest_candles):
        """Test running a backtest"""
        backtester = StrategyBacktester(BacktestConfig(
            initial_capital=10000.0,
            position_size_pct=5.0
        ))

        result = await backtester.run_backtest(
            strategy=mean_reversion_strategy,
            symbol="BTCUSDT",
            candles=mock_backtest_candles
        )

        assert result is not None
        assert result.strategy_id == "mean_reversion_v1"
        assert result.initial_capital == 10000.0
        assert len(result.equity_curve) > 0

    @pytest.mark.asyncio
    async def test_backtest_result_metrics(self, mean_reversion_strategy, mock_backtest_candles):
        """Test backtest result metrics calculation"""
        backtester = StrategyBacktester(BacktestConfig(
            initial_capital=10000.0
        ))

        result = await backtester.run_backtest(
            strategy=mean_reversion_strategy,
            symbol="BTCUSDT",
            candles=mock_backtest_candles
        )

        # Check that metrics are calculated
        assert hasattr(result, "total_trades")
        assert hasattr(result, "win_rate")
        assert hasattr(result, "sharpe_ratio")
        assert hasattr(result, "max_drawdown_pct")


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestMultiStrategyIntegration:
    """Integration tests for multi-strategy orchestration"""

    @pytest.mark.asyncio
    async def test_multiple_strategies_parallel(
        self,
        mean_reversion_strategy,
        trend_following_strategy,
        breakout_strategy,
        mock_candles
    ):
        """Test running multiple strategies in parallel"""
        # Initialize all strategies
        await mean_reversion_strategy.on_initialize()
        await trend_following_strategy.on_initialize()
        await breakout_strategy.on_initialize()

        data = {"candles": mock_candles}

        # Run all analyses in parallel
        analyses = await asyncio.gather(
            mean_reversion_strategy.analyze("BTCUSDT", data),
            trend_following_strategy.analyze("BTCUSDT", data),
            breakout_strategy.analyze("BTCUSDT", data)
        )

        # Verify all returned valid results
        for analysis in analyses:
            assert isinstance(analysis, AnalysisResult)
            assert analysis.symbol == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_coordinator_with_multiple_strategies(
        self,
        strategy_coordinator,
        mean_reversion_strategy,
        trend_following_strategy,
        mock_candles
    ):
        """Test coordinator managing multiple strategies"""
        # Register strategies
        strategy_coordinator.register_strategy(mean_reversion_strategy)
        strategy_coordinator.register_strategy(trend_following_strategy)

        # Initialize strategies
        await mean_reversion_strategy.on_initialize()
        await trend_following_strategy.on_initialize()

        data = {"candles": mock_candles}
        current_price = Decimal(str(mock_candles[-1]["close"]))

        # Generate signals from both strategies
        mr_analysis = await mean_reversion_strategy.analyze("BTCUSDT", data)
        tf_analysis = await trend_following_strategy.analyze("BTCUSDT", data)

        mr_signals = await mean_reversion_strategy.generate_signals("BTCUSDT", mr_analysis, current_price)
        tf_signals = await trend_following_strategy.generate_signals("BTCUSDT", tf_analysis, current_price)

        # Submit all signals to coordinator
        for signal in mr_signals:
            strategy_coordinator.submit_signal(signal)
        for signal in tf_signals:
            strategy_coordinator.submit_signal(signal)

        # Get stats
        stats = strategy_coordinator.get_stats()
        assert stats["registered_strategies"] == 2
        assert stats["enabled_strategies"] == 2

    @pytest.mark.asyncio
    async def test_signal_aggregation_integration(
        self,
        signal_aggregator,
        mean_reversion_strategy,
        trend_following_strategy,
        breakout_strategy,
        mock_candles
    ):
        """Test full signal aggregation flow"""
        # Initialize strategies
        await mean_reversion_strategy.on_initialize()
        await trend_following_strategy.on_initialize()
        await breakout_strategy.on_initialize()

        # Set weights based on "performance"
        signal_aggregator.set_strategy_weight("mean_reversion_v1", performance=1.2)
        signal_aggregator.set_strategy_weight("trend_following_v1", performance=1.5)
        signal_aggregator.set_strategy_weight("breakout_v1", performance=0.8)

        data = {"candles": mock_candles}
        current_price = Decimal(str(mock_candles[-1]["close"]))

        strategies = [
            mean_reversion_strategy,
            trend_following_strategy,
            breakout_strategy
        ]

        # Generate and add signals from all strategies
        for strategy in strategies:
            analysis = await strategy.analyze("BTCUSDT", data)
            signals = await strategy.generate_signals("BTCUSDT", analysis, current_price)
            for signal in signals:
                signal_aggregator.add_signal(signal)

        # Try different aggregation methods
        for method in [AggregationMethod.MAJORITY_VOTE,
                       AggregationMethod.WEIGHTED_AVERAGE,
                       AggregationMethod.CONSENSUS]:
            # Clear and re-add signals for each test
            signal_aggregator.clear("BTCUSDT")

            for strategy in strategies:
                analysis = await strategy.analyze("BTCUSDT", data)
                signals = await strategy.generate_signals("BTCUSDT", analysis, current_price)
                for signal in signals:
                    signal_aggregator.add_signal(signal)

            result = signal_aggregator.aggregate("BTCUSDT", method)
            # Result may be None if insufficient signals
            if result:
                assert result.method_used == method


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
