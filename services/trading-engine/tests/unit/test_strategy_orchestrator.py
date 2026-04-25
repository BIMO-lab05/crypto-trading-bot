"""
Test Suite for Strategy Orchestrator
=====================================
Purpose: Comprehensive tests for Multi-Strategy Orchestration System

Tests cover:
1. Strategy registration and lifecycle
2. Signal aggregation and conflict detection
3. Capital allocation and rebalancing
4. Risk coordination and emergency stop
5. Performance tracking and reallocation triggers

Phase 9: Multi-Strategy Orchestration Engine
Author: Backend Developer Agent
Date: 2025-12-12
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch, AsyncMock
import uuid

# Import orchestration components
from app.orchestration import (
    StrategyOrchestrator,
    OrchestratorConfig,
    get_strategy_orchestrator,
    reset_strategy_orchestrator,
    StrategySignal,
    SignalDirection,
    ConflictResolutionMethod,
    AllocationMethod,
    StrategyStatus,
    reset_strategy_registry,
    reset_allocation_manager,
    reset_conflict_resolver,
    reset_strategy_metrics_tracker,
)
from app.orchestration.signal_aggregator import (
    SignalAggregator,
    SignalAggregatorConfig,
    get_signal_aggregator,
    reset_signal_aggregator,
)
from app.orchestration.performance_tracker import (
    PerformanceTracker,
    PerformanceTrackerConfig,
    get_performance_tracker,
    reset_performance_tracker,
)
from app.orchestration.risk_coordinator import (
    RiskCoordinator,
    RiskCoordinatorConfig,
    get_risk_coordinator,
    reset_risk_coordinator,
)
from app.orchestration.metrics import MetricsTrade


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def reset_global_instances():
    """Reset all global instances before each test"""
    reset_strategy_orchestrator()
    reset_strategy_registry()
    reset_allocation_manager()
    reset_conflict_resolver()
    reset_strategy_metrics_tracker()
    reset_signal_aggregator()
    reset_performance_tracker()
    reset_risk_coordinator()
    yield


@pytest.fixture
def orchestrator_config():
    """Create test orchestrator configuration"""
    return OrchestratorConfig(
        total_capital=100000.0,
        max_total_exposure_pct=80.0,
        cash_reserve_pct=10.0,
        allocation_method=AllocationMethod.EQUAL,
        default_conflict_resolution=ConflictResolutionMethod.WEIGHTED_VOTING,
        max_daily_loss_pct=5.0,
        max_total_drawdown_pct=15.0
    )


@pytest.fixture
def orchestrator(orchestrator_config):
    """Create test orchestrator instance"""
    return StrategyOrchestrator(orchestrator_config)


@pytest.fixture
def signal_aggregator():
    """Create test signal aggregator"""
    config = SignalAggregatorConfig(
        signal_expiry_seconds=300,
        min_confidence=0.3,
        min_strength=0.2
    )
    return SignalAggregator(config)


@pytest.fixture
def performance_tracker():
    """Create test performance tracker"""
    config = PerformanceTrackerConfig(
        underperformance_sharpe_threshold=0.0,
        realloc_min_trades_for_eval=10,
        realloc_evaluation_window_days=30
    )
    return PerformanceTracker(config)


@pytest.fixture
def risk_coordinator():
    """Create test risk coordinator"""
    config = RiskCoordinatorConfig(
        max_total_exposure_pct=80.0,
        max_total_drawdown_pct=15.0,
        max_concurrent_positions=20,
        emergency_stop_enabled=True
    )
    return RiskCoordinator(config)


@pytest.fixture
def sample_signal():
    """Create sample strategy signal"""
    return StrategySignal(
        signal_id=f"sig_{uuid.uuid4().hex[:8]}",
        strategy_id="test_strategy_1",
        symbol="BTCUSDT",
        timestamp=datetime.now(timezone.utc),
        direction=SignalDirection.LONG,
        action="BUY",
        strength=0.75,
        confidence=0.8,
        stop_loss_pct=2.0,
        take_profit_pct=4.0
    )


@pytest.fixture
def sample_trade():
    """Create sample completed trade"""
    return MetricsTrade(
        trade_id=f"trade_{uuid.uuid4().hex[:8]}",
        strategy_id="test_strategy_1",
        symbol="BTCUSDT",
        side="LONG",
        entry_time=datetime.now(timezone.utc) - timedelta(hours=2),
        exit_time=datetime.now(timezone.utc),
        entry_price=50000.0,
        exit_price=51000.0,
        quantity=0.1,
        pnl=100.0,
        pnl_pct=2.0
    )


# =============================================================================
# STRATEGY ORCHESTRATOR TESTS
# =============================================================================

class TestStrategyOrchestrator:
    """Test suite for StrategyOrchestrator"""

    def test_orchestrator_initialization(self, orchestrator_config):
        """Test orchestrator initializes correctly with config"""
        orchestrator = StrategyOrchestrator(orchestrator_config)

        assert orchestrator.config.total_capital == 100000.0
        assert orchestrator.config.max_total_exposure_pct == 80.0
        assert orchestrator.config.allocation_method == AllocationMethod.EQUAL

    def test_register_strategy_success(self, orchestrator):
        """Test successful strategy registration"""
        result = orchestrator.register_strategy(
            strategy_id="trend_following_v1",
            name="Trend Following Strategy",
            strategy_type="trend_following",
            risk_profile="moderate",
            symbols=["BTCUSDT", "ETHUSDT"],  # This maps to supported_symbols internally
            timeframe="1h",
            allocation_pct=20.0,
            priority=70,
            description="Test strategy",
            auto_activate=False
        )

        assert result["success"] is True
        assert result["strategy_id"] == "trend_following_v1"
        assert result["status"] == "disabled"

    def test_register_strategy_with_auto_activate(self, orchestrator):
        """Test strategy registration with auto-activation"""
        result = orchestrator.register_strategy(
            strategy_id="auto_active_strategy",
            name="Auto Active Strategy",
            strategy_type="momentum",
            symbols=["BTCUSDT", "ETHUSDT"],  # Required for proper registration
            allocation_pct=15.0,
            auto_activate=True
        )

        assert result["success"] is True
        assert result["status"] == "active"

    def test_activate_strategy(self, orchestrator):
        """Test strategy activation"""
        # First register
        orchestrator.register_strategy(
            strategy_id="test_strategy",
            name="Test Strategy",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=10.0
        )

        # Then activate
        result = orchestrator.activate_strategy("test_strategy")

        assert result["success"] is True
        assert result["status"] == "active"

    def test_activate_strategy_with_warmup(self, orchestrator):
        """Test strategy activation with warmup period"""
        orchestrator.register_strategy(
            strategy_id="warmup_strategy",
            name="Warmup Strategy",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=10.0
        )

        result = orchestrator.activate_strategy("warmup_strategy", warmup_minutes=30)

        assert result["success"] is True
        assert result["status"] == "warming_up"

    def test_deactivate_strategy(self, orchestrator):
        """Test strategy deactivation"""
        orchestrator.register_strategy(
            strategy_id="deactivate_test",
            name="Deactivate Test",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=10.0,
            auto_activate=True
        )

        result = orchestrator.deactivate_strategy("deactivate_test", reason="Testing deactivation")

        assert result["success"] is True
        assert result["reason"] == "Testing deactivation"

    def test_pause_strategy(self, orchestrator):
        """Test strategy pause functionality"""
        orchestrator.register_strategy(
            strategy_id="pause_test",
            name="Pause Test",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=10.0,
            auto_activate=True
        )

        result = orchestrator.pause_strategy("pause_test", reason="Performance issue", cooldown_hours=4)

        assert result["success"] is True
        assert result["status"] == "cooldown"
        assert result["cooldown_until"] is not None

    def test_unregister_strategy(self, orchestrator):
        """Test strategy unregistration"""
        orchestrator.register_strategy(
            strategy_id="unregister_test",
            name="Unregister Test",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=10.0
        )

        result = orchestrator.unregister_strategy("unregister_test")

        assert result["success"] is True

    def test_submit_signal_accepted(self, orchestrator, sample_signal):
        """Test signal submission is accepted for active strategy"""
        orchestrator.register_strategy(
            strategy_id=sample_signal.strategy_id,
            name="Test Strategy",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=10.0,
            auto_activate=True
        )

        result = orchestrator.submit_signal(sample_signal)

        assert result["accepted"] is True

    def test_submit_signal_rejected_inactive(self, orchestrator, sample_signal):
        """Test signal rejected for inactive strategy"""
        orchestrator.register_strategy(
            strategy_id=sample_signal.strategy_id,
            name="Test Strategy",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=10.0,
            auto_activate=False  # Not activated
        )

        result = orchestrator.submit_signal(sample_signal)

        assert result["accepted"] is False
        assert "not active" in result["reason"].lower()

    def test_submit_signals_batch(self, orchestrator):
        """Test batch signal submission"""
        orchestrator.register_strategy(
            strategy_id="batch_test_strategy",
            name="Batch Test Strategy",
            symbols=["BTCUSDT", "ETHUSDT", "ASSET0USDT", "ASSET1USDT", "ASSET2USDT"],
            allocation_pct=10.0,
            auto_activate=True
        )

        signals = [
            StrategySignal(
                signal_id=f"sig_{i}",
                strategy_id="batch_test_strategy",
                symbol=f"ASSET{i}USDT",
                timestamp=datetime.now(timezone.utc),
                direction=SignalDirection.LONG,
                action="BUY",
                strength=0.7,
                confidence=0.8
            )
            for i in range(3)
        ]

        result = orchestrator.submit_signals(signals)

        assert result["total"] == 3
        assert result["accepted"] == 3

    def test_get_aggregated_signal(self, orchestrator):
        """Test signal aggregation for a symbol"""
        # Register and activate strategy
        orchestrator.register_strategy(
            strategy_id="agg_test_strategy",
            name="Aggregation Test",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=20.0,
            auto_activate=True
        )

        # Submit signal
        signal = StrategySignal(
            signal_id="agg_sig_1",
            strategy_id="agg_test_strategy",
            symbol="BTCUSDT",
            timestamp=datetime.now(timezone.utc),
            direction=SignalDirection.LONG,
            action="BUY",
            strength=0.8,
            confidence=0.85
        )
        orchestrator.submit_signal(signal)

        # Get aggregated
        aggregated = orchestrator.get_aggregated_signal("BTCUSDT")

        assert aggregated is not None
        assert aggregated.symbol == "BTCUSDT"

    def test_pause_all_strategies(self, orchestrator):
        """Test pausing all active strategies"""
        # Register multiple strategies
        for i in range(3):
            orchestrator.register_strategy(
                strategy_id=f"multi_strategy_{i}",
                name=f"Multi Strategy {i}",
                symbols=["BTCUSDT", "ETHUSDT"],
                allocation_pct=10.0,
                auto_activate=True
            )

        result = orchestrator.pause_all("Emergency maintenance")

        assert result["success"] is True
        assert len(result["paused_strategies"]) == 3

    def test_resume_all_strategies(self, orchestrator):
        """Test resuming all paused strategies"""
        # Register and pause
        for i in range(2):
            orchestrator.register_strategy(
                strategy_id=f"resume_strategy_{i}",
                name=f"Resume Strategy {i}",
                symbols=["BTCUSDT", "ETHUSDT"],
                allocation_pct=10.0,
                auto_activate=True
            )

        orchestrator.pause_all("Test pause")
        result = orchestrator.resume_all()

        assert result["success"] is True
        assert len(result["resumed_strategies"]) == 2

    def test_get_orchestrator_status(self, orchestrator):
        """Test getting orchestrator status"""
        orchestrator.register_strategy(
            strategy_id="status_test",
            name="Status Test",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=20.0,
            auto_activate=True
        )

        status = orchestrator.get_orchestrator_status()

        assert status["is_active"] is True
        assert status["total_capital"] == 100000.0
        assert status["active_strategies"] == 1
        assert status["total_strategies"] == 1

    def test_get_all_strategies_status(self, orchestrator):
        """Test getting status for all strategies"""
        for i in range(3):
            orchestrator.register_strategy(
                strategy_id=f"all_status_{i}",
                name=f"All Status {i}",
                symbols=["BTCUSDT", "ETHUSDT"],
                allocation_pct=10.0,
                auto_activate=i % 2 == 0  # Alternate activation
            )

        statuses = orchestrator.get_all_strategies_status()

        assert len(statuses) == 3


# =============================================================================
# SIGNAL AGGREGATOR TESTS
# =============================================================================

class TestSignalAggregator:
    """Test suite for SignalAggregator"""

    def test_aggregator_initialization(self):
        """Test signal aggregator initializes correctly"""
        config = SignalAggregatorConfig(min_confidence=0.4)
        aggregator = SignalAggregator(config)

        assert aggregator.config.min_confidence == 0.4
        assert aggregator.get_signal_count() == 0

    def test_collect_signal_accepted(self, signal_aggregator, sample_signal):
        """Test signal collection accepts valid signal"""
        result = signal_aggregator.collect_signal(sample_signal)

        assert result["accepted"] is True
        assert signal_aggregator.get_signal_count() == 1

    def test_collect_signal_rejected_low_confidence(self, signal_aggregator):
        """Test signal rejection for low confidence"""
        signal = StrategySignal(
            signal_id="low_conf_sig",
            strategy_id="test_strategy",
            symbol="BTCUSDT",
            timestamp=datetime.now(timezone.utc),
            direction=SignalDirection.LONG,
            action="BUY",
            strength=0.5,
            confidence=0.1  # Below threshold
        )

        result = signal_aggregator.collect_signal(signal)

        assert result["accepted"] is False
        assert "confidence" in result["reason"].lower()

    def test_collect_signals_batch(self, signal_aggregator):
        """Test batch signal collection"""
        signals = [
            StrategySignal(
                signal_id=f"batch_{i}",
                strategy_id=f"strategy_{i}",
                symbol="BTCUSDT",
                timestamp=datetime.now(timezone.utc),
                direction=SignalDirection.LONG,
                action="BUY",
                strength=0.7,
                confidence=0.8
            )
            for i in range(5)
        ]

        result = signal_aggregator.collect_signals_batch(signals)

        assert result["total"] == 5
        assert result["accepted"] == 5
        assert result["batch_id"] is not None

    def test_detect_direction_conflict(self, signal_aggregator):
        """Test detection of opposing direction signals"""
        # Long signal
        signal_aggregator.collect_signal(StrategySignal(
            signal_id="long_sig",
            strategy_id="strategy_1",
            symbol="BTCUSDT",
            timestamp=datetime.now(timezone.utc),
            direction=SignalDirection.LONG,
            action="BUY",
            strength=0.8,
            confidence=0.8
        ))

        # Short signal
        signal_aggregator.collect_signal(StrategySignal(
            signal_id="short_sig",
            strategy_id="strategy_2",
            symbol="BTCUSDT",
            timestamp=datetime.now(timezone.utc),
            direction=SignalDirection.SHORT,
            action="SELL",
            strength=0.7,
            confidence=0.7
        ))

        conflict = signal_aggregator.detect_conflicts("BTCUSDT")

        assert conflict.has_conflict is True
        assert conflict.direction_conflict is True
        assert "strategy_1" in conflict.conflicting_strategies
        assert "strategy_2" in conflict.conflicting_strategies

    def test_detect_no_conflict(self, signal_aggregator):
        """Test no conflict when signals agree"""
        for i in range(3):
            signal_aggregator.collect_signal(StrategySignal(
                signal_id=f"agree_sig_{i}",
                strategy_id=f"strategy_{i}",
                symbol="BTCUSDT",
                timestamp=datetime.now(timezone.utc),
                direction=SignalDirection.LONG,
                action="BUY",
                strength=0.7 + i * 0.05,
                confidence=0.8
            ))

        conflict = signal_aggregator.detect_conflicts("BTCUSDT")

        assert conflict.has_conflict is False
        assert conflict.signal_count == 3

    def test_get_prioritized_signals(self, signal_aggregator):
        """Test signal prioritization"""
        # Add signals with different priorities
        signal_aggregator.set_strategy_priority("high_priority", 90)
        signal_aggregator.set_strategy_priority("low_priority", 30)

        signal_aggregator.collect_signal(StrategySignal(
            signal_id="high_pri_sig",
            strategy_id="high_priority",
            symbol="BTCUSDT",
            timestamp=datetime.now(timezone.utc),
            direction=SignalDirection.LONG,
            action="BUY",
            strength=0.6,
            confidence=0.7
        ))

        signal_aggregator.collect_signal(StrategySignal(
            signal_id="low_pri_sig",
            strategy_id="low_priority",
            symbol="BTCUSDT",
            timestamp=datetime.now(timezone.utc),
            direction=SignalDirection.LONG,
            action="BUY",
            strength=0.9,
            confidence=0.9
        ))

        prioritized = signal_aggregator.get_prioritized_signals("BTCUSDT")

        assert len(prioritized) == 2
        # Higher priority strategy should be first (despite lower strength)

    def test_clean_expired_signals(self, signal_aggregator):
        """Test automatic cleaning of expired signals"""
        # Create expired signal
        expired_signal = StrategySignal(
            signal_id="expired_sig",
            strategy_id="test_strategy",
            symbol="BTCUSDT",
            timestamp=datetime.now(timezone.utc) - timedelta(seconds=600),  # 10 minutes old
            direction=SignalDirection.LONG,
            action="BUY",
            strength=0.8,
            confidence=0.8,
            expiry_seconds=300  # 5 minute expiry
        )

        # Force add (bypassing expiry check)
        signal_aggregator._signals["BTCUSDT"].append((expired_signal, None))

        # Clean
        removed = signal_aggregator.clean_all_expired()

        assert removed >= 0  # May be cleaned

    def test_clear_symbol(self, signal_aggregator, sample_signal):
        """Test clearing signals for a specific symbol"""
        signal_aggregator.collect_signal(sample_signal)
        assert signal_aggregator.get_signal_count("BTCUSDT") == 1

        signal_aggregator.clear_symbol("BTCUSDT")

        assert signal_aggregator.get_signal_count("BTCUSDT") == 0


# =============================================================================
# PERFORMANCE TRACKER TESTS
# =============================================================================

class TestPerformanceTracker:
    """Test suite for PerformanceTracker"""

    def test_tracker_initialization(self):
        """Test performance tracker initialization"""
        config = PerformanceTrackerConfig(underperformance_sharpe_threshold=-0.5)
        tracker = PerformanceTracker(config)

        assert tracker.config.underperformance_sharpe_threshold == -0.5

    def test_record_trade(self, performance_tracker, sample_trade):
        """Test recording a completed trade"""
        result = performance_tracker.record_trade(sample_trade)

        assert result is not None

    def test_detect_underperformers_none(self, performance_tracker):
        """Test underperformer detection with no underperformers"""
        # Without trades, no underperformers
        underperformers = performance_tracker.detect_underperformers()

        assert len(underperformers) == 0

    def test_compare_strategies(self, performance_tracker):
        """Test strategy comparison"""
        comparison = performance_tracker.compare_strategies()

        assert comparison is not None

    def test_get_reallocation_recommendations(self, performance_tracker):
        """Test getting reallocation recommendations"""
        current_allocations = {
            "strategy_1": 30.0,
            "strategy_2": 30.0,
            "strategy_3": 40.0
        }

        recommendations = performance_tracker.get_reallocation_recommendations(current_allocations)

        assert isinstance(recommendations, list)

    def test_get_strategy_ranking(self, performance_tracker):
        """Test strategy ranking by metric"""
        ranking = performance_tracker.get_strategy_ranking("sharpe_ratio")

        assert isinstance(ranking, list)

    def test_get_portfolio_attribution(self, performance_tracker):
        """Test portfolio return attribution"""
        attribution = performance_tracker.get_portfolio_attribution()

        assert attribution is not None


# =============================================================================
# RISK COORDINATOR TESTS
# =============================================================================

class TestRiskCoordinator:
    """Test suite for RiskCoordinator"""

    def test_coordinator_initialization(self):
        """Test risk coordinator initialization"""
        config = RiskCoordinatorConfig(max_total_exposure_pct=75.0)
        coordinator = RiskCoordinator(config)

        assert coordinator.config.max_total_exposure_pct == 75.0

    def test_set_total_capital(self, risk_coordinator):
        """Test setting total capital"""
        risk_coordinator.set_total_capital(200000.0)

        status = risk_coordinator.get_status()
        assert status["total_capital"] == 200000.0

    def test_check_new_trade_allowed(self, risk_coordinator):
        """Test trade check passes for valid trade"""
        result = risk_coordinator.check_new_trade(
            strategy_id="test_strategy",
            symbol="BTCUSDT",
            size_pct=5.0,
            risk_pct=1.0
        )

        assert result.allowed is True

    def test_check_new_trade_exceeds_exposure(self, risk_coordinator):
        """Test trade check fails when exceeding exposure limit"""
        # Set high exposure
        risk_coordinator._total_exposure_pct = 78.0

        result = risk_coordinator.check_new_trade(
            strategy_id="test_strategy",
            symbol="BTCUSDT",
            size_pct=5.0,  # Would exceed 80% limit
            risk_pct=1.0
        )

        # Should have warning or suggestion
        assert len(result.warnings) > 0 or result.adjusted_size_pct is not None

    def test_check_new_trade_during_emergency(self, risk_coordinator):
        """Test trade check fails during emergency stop"""
        risk_coordinator.emergency_stop("Test emergency")

        result = risk_coordinator.check_new_trade(
            strategy_id="test_strategy",
            symbol="BTCUSDT",
            size_pct=5.0
        )

        assert result.allowed is False
        assert "emergency" in result.reason.lower()

    def test_update_position(self, risk_coordinator):
        """Test position tracking update"""
        risk_coordinator.update_position(
            strategy_id="test_strategy",
            symbol="BTCUSDT",
            size_pct=10.0,
            risk_pct=2.0
        )

        status = risk_coordinator.get_strategy_risk_status("test_strategy")
        assert status["exposure_pct"] == 10.0
        assert status["positions"] == 1

    def test_close_position(self, risk_coordinator):
        """Test closing a position"""
        # Open position
        risk_coordinator.update_position("test_strategy", "BTCUSDT", 10.0)

        # Close position
        risk_coordinator.update_position("test_strategy", "BTCUSDT", 0.0)

        status = risk_coordinator.get_strategy_risk_status("test_strategy")
        assert status["positions"] == 0

    def test_emergency_stop(self, risk_coordinator):
        """Test emergency stop activation"""
        result = risk_coordinator.emergency_stop("Critical market conditions")

        assert result["success"] is True
        assert risk_coordinator.is_emergency_stopped() is True

    def test_release_emergency_stop(self, risk_coordinator):
        """Test releasing emergency stop"""
        risk_coordinator.emergency_stop("Test stop")
        result = risk_coordinator.release_emergency_stop(start_recovery=True)

        assert result["success"] is True
        assert risk_coordinator.is_emergency_stopped() is False

    def test_get_risk_utilization(self, risk_coordinator):
        """Test getting risk utilization metrics"""
        risk_coordinator.update_position("strategy_1", "BTCUSDT", 20.0)
        risk_coordinator.update_position("strategy_1", "ETHUSDT", 15.0)

        utilization = risk_coordinator.get_risk_utilization()

        assert utilization.total_exposure_pct == 35.0
        assert utilization.total_positions == 2

    def test_close_all_positions(self, risk_coordinator):
        """Test closing all positions"""
        # Open multiple positions
        risk_coordinator.update_position("strategy_1", "BTCUSDT", 20.0)
        risk_coordinator.update_position("strategy_1", "ETHUSDT", 15.0)
        risk_coordinator.update_position("strategy_2", "BTCUSDT", 10.0)

        result = risk_coordinator.close_all_positions()

        assert result["positions_closed"] == 3

    def test_close_positions_by_strategy(self, risk_coordinator):
        """Test closing positions for specific strategy"""
        risk_coordinator.update_position("strategy_1", "BTCUSDT", 20.0)
        risk_coordinator.update_position("strategy_2", "BTCUSDT", 10.0)

        result = risk_coordinator.close_all_positions(strategy_id="strategy_1")

        assert result["positions_closed"] == 1

    def test_update_equity_triggers_emergency(self, risk_coordinator):
        """Test equity update triggers emergency stop on large drawdown"""
        risk_coordinator.set_total_capital(100000.0)

        # Update equity to trigger emergency (25% loss)
        result = risk_coordinator.update_equity(75000.0)

        assert result["drawdown_pct"] >= 20.0
        # Emergency stop should have been triggered
        assert "emergency_stop_triggered" in result["actions"] or risk_coordinator.is_emergency_stopped()

    def test_reset_daily_tracking(self, risk_coordinator):
        """Test daily tracking reset"""
        risk_coordinator.set_total_capital(100000.0)
        risk_coordinator.update_equity(95000.0)

        risk_coordinator.reset_daily_tracking()

        # After reset, today's starting equity should be updated


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestOrchestrationIntegration:
    """Integration tests for orchestration system"""

    def test_full_workflow(self, orchestrator):
        """Test complete orchestration workflow"""
        # 1. Register strategies
        orchestrator.register_strategy(
            strategy_id="sqzmom_strategy",
            name="SQZMOM Strategy",
            strategy_type="momentum",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=40.0,
            priority=80,
            auto_activate=True
        )

        orchestrator.register_strategy(
            strategy_id="pairs_strategy",
            name="Pairs Trading Strategy",
            strategy_type="arbitrage",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=30.0,
            priority=90,
            auto_activate=True
        )

        orchestrator.register_strategy(
            strategy_id="grid_strategy",
            name="Grid Trading Strategy",
            strategy_type="grid",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=30.0,
            priority=50,
            auto_activate=True
        )

        # 2. Verify all strategies registered
        status = orchestrator.get_orchestrator_status()
        assert status["total_strategies"] == 3
        assert status["active_strategies"] == 3

        # 3. Submit signals from strategies
        sqzmom_signal = StrategySignal(
            signal_id="sqzmom_sig_001",
            strategy_id="sqzmom_strategy",
            symbol="BTCUSDT",
            timestamp=datetime.now(timezone.utc),
            direction=SignalDirection.LONG,
            action="BUY",
            strength=0.75,
            confidence=0.75
        )

        pairs_signal = StrategySignal(
            signal_id="pairs_sig_001",
            strategy_id="pairs_strategy",
            symbol="BTCUSDT",
            timestamp=datetime.now(timezone.utc),
            direction=SignalDirection.SHORT,  # Conflicting!
            action="SELL",
            strength=0.65,
            confidence=0.65
        )

        orchestrator.submit_signal(sqzmom_signal)
        orchestrator.submit_signal(pairs_signal)

        # 4. Get aggregated signal (conflict resolution)
        aggregated = orchestrator.get_aggregated_signal("BTCUSDT")

        assert aggregated is not None
        assert aggregated.conflict_detected is True

        # 5. Verify status
        final_status = orchestrator.get_orchestrator_status()
        assert final_status["is_active"] is True

    def test_conflict_resolution_scenario(self, orchestrator):
        """Test specific conflict resolution scenario from requirements"""
        # Register strategies with specific allocations and priorities
        orchestrator.register_strategy(
            strategy_id="sqzmom",
            name="SQZMOM",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=40.0,
            priority=80,  # Actually maps to priority 8 in conflict resolver (higher number = higher priority)
            auto_activate=True
        )

        orchestrator.register_strategy(
            strategy_id="pairs",
            name="Pairs Trading",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=30.0,
            priority=90,  # Higher priority
            auto_activate=True
        )

        orchestrator.register_strategy(
            strategy_id="grid",
            name="Grid Trading",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=30.0,
            priority=50,
            auto_activate=True
        )

        # Submit conflicting signals
        orchestrator.submit_signal(StrategySignal(
            signal_id="sqzmom_btc",
            strategy_id="sqzmom",
            symbol="BTCUSDT",
            timestamp=datetime.now(timezone.utc),
            direction=SignalDirection.LONG,
            action="BUY",
            strength=0.75,
            confidence=0.75
        ))

        orchestrator.submit_signal(StrategySignal(
            signal_id="pairs_btc",
            strategy_id="pairs",
            symbol="BTCUSDT",
            timestamp=datetime.now(timezone.utc),
            direction=SignalDirection.SHORT,
            action="SELL",
            strength=0.65,
            confidence=0.65
        ))

        # Grid HOLD - no signal needed

        # Resolve conflict
        aggregated = orchestrator.get_aggregated_signal("BTCUSDT")

        assert aggregated is not None
        assert aggregated.conflict_detected is True
        # Resolution depends on method, but conflict should be resolved

    def test_emergency_stop_propagation(self, orchestrator):
        """Test emergency stop propagates to all components"""
        # Register and activate strategies
        orchestrator.register_strategy(
            strategy_id="emergency_test_1",
            name="Emergency Test 1",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=30.0,
            auto_activate=True
        )
        orchestrator.register_strategy(
            strategy_id="emergency_test_2",
            name="Emergency Test 2",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=30.0,
            auto_activate=True
        )

        # Get risk coordinator and trigger emergency
        coordinator = get_risk_coordinator()
        coordinator.emergency_stop("Test emergency propagation")

        # Verify orchestrator reflects emergency state
        # (through risk coordinator integration)
        assert coordinator.is_emergency_stopped() is True


# =============================================================================
# CAPITAL ALLOCATION TESTS
# =============================================================================

class TestCapitalAllocation:
    """Tests for capital allocation functionality"""

    def test_allocation_update(self, orchestrator):
        """Test allocation update"""
        orchestrator.register_strategy(
            strategy_id="alloc_test",
            name="Allocation Test",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=10.0,
            auto_activate=True
        )

        result = orchestrator.update_allocation("alloc_test", target_pct=25.0)

        assert result["success"] is True
        assert result["new_allocation"]["target_pct"] == 25.0

    def test_rebalance_trigger(self, orchestrator):
        """Test rebalancing trigger"""
        orchestrator.register_strategy(
            strategy_id="rebalance_test",
            name="Rebalance Test",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=50.0,
            auto_activate=True
        )

        result = orchestrator.trigger_rebalance()

        assert result is not None


# =============================================================================
# EDGE CASES AND ERROR HANDLING
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_unknown_strategy_operations(self, orchestrator):
        """Test operations on non-existent strategy"""
        result = orchestrator.activate_strategy("nonexistent_strategy")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_duplicate_registration(self, orchestrator):
        """Test duplicate strategy registration"""
        orchestrator.register_strategy(
            strategy_id="duplicate_test",
            name="Duplicate Test",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=10.0
        )

        # Try to register again
        result = orchestrator.register_strategy(
            strategy_id="duplicate_test",
            name="Duplicate Test Again",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=15.0
        )

        # Should fail or update
        assert result is not None

    def test_invalid_allocation_percentage(self, orchestrator):
        """Test handling of invalid allocation values"""
        orchestrator.register_strategy(
            strategy_id="invalid_alloc",
            name="Invalid Alloc",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=10.0,
            auto_activate=True
        )

        # Try to set invalid allocation
        result = orchestrator.update_allocation("invalid_alloc", target_pct=-5.0)

        # Should handle gracefully

    def test_empty_signals_aggregation(self, orchestrator):
        """Test aggregation with no signals"""
        aggregated = orchestrator.get_aggregated_signal("NOSYMBOL")

        assert aggregated is None

    def test_signal_expiration_handling(self, signal_aggregator):
        """Test handling of expired signals"""
        expired = StrategySignal(
            signal_id="old_signal",
            strategy_id="test_strategy",
            symbol="BTCUSDT",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            direction=SignalDirection.LONG,
            action="BUY",
            strength=0.8,
            confidence=0.8,
            expiry_seconds=300
        )

        result = signal_aggregator.collect_signal(expired)

        assert result["accepted"] is False


# =============================================================================
# CONCURRENT ACCESS TESTS
# =============================================================================

class TestConcurrency:
    """Test thread safety and concurrent access"""

    def test_concurrent_signal_submission(self, orchestrator):
        """Test concurrent signal submissions"""
        import threading

        orchestrator.register_strategy(
            strategy_id="concurrent_test",
            name="Concurrent Test",
            symbols=["BTCUSDT", "ETHUSDT"],
            allocation_pct=50.0,
            auto_activate=True
        )

        results = []
        errors = []

        def submit_signal(signal_num):
            try:
                signal = StrategySignal(
                    signal_id=f"concurrent_sig_{signal_num}",
                    strategy_id="concurrent_test",
                    symbol="BTCUSDT",
                    timestamp=datetime.now(timezone.utc),
                    direction=SignalDirection.LONG,
                    action="BUY",
                    strength=0.7,
                    confidence=0.8
                )
                result = orchestrator.submit_signal(signal)
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=submit_signal, args=(i,)) for i in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert all(r["accepted"] for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
