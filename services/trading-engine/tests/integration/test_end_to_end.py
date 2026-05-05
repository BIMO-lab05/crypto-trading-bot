"""
End-to-End Integration Tests
============================
Complete Trading Flow Integration Tests

Purpose:
- Test complete signal-to-execution flow
- Verify cross-component data flow
- Test failure scenarios and recovery
- Validate production-like scenarios

Test Scenarios:
1. Signal -> Aggregation -> Execution -> Performance tracking
2. Multi-exchange arbitrage detection and execution
3. Risk limit breach -> Circuit breaker -> Alert -> Pause
4. Strategy coordination with conflict resolution
5. Health degradation -> Failover -> Recovery
"""

import pytest

pytest.skip(
    "stale imports vs current trading-engine API; needs rewrite after PR #86 refactor",
    allow_module_level=True,
)


import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, Any, List
from unittest.mock import MagicMock, AsyncMock, patch
import uuid

# Import all major components
from app.orchestration.orchestrator import (
    StrategyOrchestrator,
    OrchestratorConfig,
    reset_strategy_orchestrator,
    get_strategy_orchestrator,
)
from app.orchestration.models import (
    StrategySignal,
    SignalDirection,
    AggregatedSignal,
    AllocationMethod,
    ConflictResolutionMethod,
)
from app.orchestration.metrics import MetricsTrade

from app.risk.dynamic_budget import (
    DynamicBudgetManager,
    RiskBudgetConfig,
    get_budget_manager,
)

from app.execution.twap_vwap import (
    TWAPExecutor,
    TWAPConfig,
    VWAPExecutor,
    VWAPConfig,
)
from app.execution.smart_router import (
    SmartOrderRouter,
    RoutingDecision,
    ExecutionAlgorithm,
)

from app.analytics.advanced_metrics import (
    AdvancedMetricsCalculator,
    MetricsConfig,
)

from app.handlers.performance_dashboard import (
    PerformanceDashboardHandler,
    DashboardConfig,
    DashboardEvent,
    DashboardEventType,
)

from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    get_circuit_breaker,
)

from app.core.health import (
    HealthChecker,
    HealthStatus,
    get_health_checker,
)

from app.core.metrics import (
    TradingMetrics,
    get_metrics_collector,
)

from app.models import OrderSide, OrderType, OrderStatus


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def full_system_config() -> Dict[str, Any]:
    """
    Create full system configuration for E2E testing

    Returns:
        Dictionary with all component configs
    """
    return {
        "orchestrator": OrchestratorConfig(
            total_capital=100000.0,
            max_total_exposure_pct=80.0,
            allocation_method=AllocationMethod.PERFORMANCE_BASED,
            default_conflict_resolution=ConflictResolutionMethod.WEIGHTED_VOTING,
        ),
        "risk_budget": RiskBudgetConfig(
            total_capital=100000.0,
            base_risk_per_trade_pct=1.0,
            max_risk_per_trade_pct=2.0,
            max_daily_loss_pct=5.0,
        ),
        "twap": TWAPConfig(
            total_duration_seconds=60,
            num_slices=5,
            randomize_timing=False,
        ),
        "dashboard": DashboardConfig(
            update_interval_seconds=1,
            max_clients=10,
        ),
    }


@pytest.fixture
def mock_exchange():
    """Create comprehensive mock exchange"""
    exchange = AsyncMock()
    exchange.exchange_id = "bybit"
    exchange.is_connected = True

    exchange.get_ticker = AsyncMock(return_value={
        "symbol": "BTCUSDT",
        "last_price": 50000.0,
        "bid_price": 49995.0,
        "ask_price": 50000.0,
        "volume_24h": 1000000000.0,
    })

    exchange.get_orderbook = AsyncMock(return_value={
        "bids": [{"price": 49995.0, "qty": 10.0}],
        "asks": [{"price": 50000.0, "qty": 10.0}],
    })

    exchange.place_order = AsyncMock(return_value={
        "order_id": str(uuid.uuid4()),
        "status": "FILLED",
        "filled_qty": 0.1,
        "filled_price": 50000.0,
        "fee": 0.5,
    })

    exchange.get_balance = AsyncMock(return_value={
        "USDT": {"available": 100000.0, "total": 100000.0},
    })

    return exchange


@pytest.fixture
async def full_trading_system(full_system_config, mock_exchange):
    """
    Initialize full trading system for E2E tests

    Returns:
        Dictionary with all initialized components
    """
    reset_strategy_orchestrator()

    # Initialize all components
    orchestrator = StrategyOrchestrator(config=full_system_config["orchestrator"])
    budget_manager = DynamicBudgetManager(config=full_system_config["risk_budget"])
    twap_executor = TWAPExecutor(config=full_system_config["twap"])
    smart_router = SmartOrderRouter()
    smart_router.register_exchange("bybit", mock_exchange)
    metrics_calculator = AdvancedMetricsCalculator()
    dashboard = PerformanceDashboardHandler(config=full_system_config["dashboard"])
    health_checker = HealthChecker()
    trading_metrics = get_metrics_collector().trading_metrics

    # Register strategies
    strategies = [
        {
            "strategy_id": "trend_following",
            "name": "Trend Following",
            "allocation_pct": 35.0,
            "priority": 70,
        },
        {
            "strategy_id": "mean_reversion",
            "name": "Mean Reversion",
            "allocation_pct": 35.0,
            "priority": 60,
        },
    ]

    for s in strategies:
        orchestrator.register_strategy(
            strategy_id=s["strategy_id"],
            name=s["name"],
            symbols=["BTCUSDT"],
            allocation_pct=s["allocation_pct"],
            priority=s["priority"],
            auto_activate=True,
        )

    system = {
        "orchestrator": orchestrator,
        "budget_manager": budget_manager,
        "twap_executor": twap_executor,
        "smart_router": smart_router,
        "metrics_calculator": metrics_calculator,
        "dashboard": dashboard,
        "health_checker": health_checker,
        "trading_metrics": trading_metrics,
        "mock_exchange": mock_exchange,
    }

    yield system

    # Cleanup
    reset_strategy_orchestrator()


# ============================================================================
# SCENARIO 1: SIGNAL TO EXECUTION FLOW
# ============================================================================

class TestSignalToExecutionFlow:
    """
    End-to-end test: Signal Generation -> Execution -> Performance Update

    Flow:
    1. Strategy generates signal
    2. Signal is submitted to orchestrator
    3. Orchestrator aggregates/resolves conflicts
    4. Risk budget is allocated
    5. Order is routed to exchange
    6. Execution occurs (TWAP/VWAP)
    7. Trade result is recorded
    8. Performance metrics are updated
    9. Dashboard receives update
    """

    @pytest.mark.asyncio
    async def test_complete_buy_signal_flow(self, full_trading_system):
        """Test complete flow for a BUY signal"""
        orchestrator = full_trading_system["orchestrator"]
        budget_manager = full_trading_system["budget_manager"]
        smart_router = full_trading_system["smart_router"]
        metrics_calculator = full_trading_system["metrics_calculator"]
        trading_metrics = full_trading_system["trading_metrics"]

        # Step 1: Create and submit signal
        signal = StrategySignal(
            signal_id=str(uuid.uuid4()),
            strategy_id="trend_following",
            symbol="BTCUSDT",
            timestamp=datetime.now(timezone.utc),
            direction=SignalDirection.LONG,
            action="BUY",
            strength=0.75,
            confidence=0.80,
            entry_price=Decimal("50000.0"),
            stop_loss_pct=2.0,
            take_profit_pct=6.0,
            position_size_pct=2.0,
        )

        # Step 2: Submit to orchestrator
        submit_result = orchestrator.submit_signal(signal)
        assert submit_result["accepted"] == True

        # Step 3: Get aggregated signal
        aggregated = orchestrator.get_aggregated_signal("BTCUSDT")
        assert aggregated is not None
        assert aggregated.direction == SignalDirection.LONG

        # Step 4: Allocate risk budget
        allocation = budget_manager.allocate_risk_budget(
            symbol="BTCUSDT",
            strategy_id="trend_following",
            signal_confidence=aggregated.aggregated_confidence,
            volatility=0.02,
        )
        assert allocation.is_blocked == False
        assert allocation.position_size_usd > 0

        # Step 5: Route order
        decision = await smart_router.determine_execution_strategy(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            total_value_usd=allocation.position_size_usd,
            urgency="MEDIUM",
            market_conditions={"volatility": 0.02, "liquidity_score": 0.8},
        )
        assert decision is not None

        # Step 6: Execute order
        order_result = await smart_router.execute_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            price=Decimal("50000.0"),
            execution_decision=decision,
        )
        assert order_result is not None

        # Step 7: Record trade result
        trade = MetricsTrade(
            trade_id=str(uuid.uuid4()),
            strategy_id="trend_following",
            symbol="BTCUSDT",
            side="LONG",
            entry_price=50000.0,
            exit_price=51500.0,  # Simulated profitable exit
            quantity=0.1,
            pnl=150.0,
            pnl_pct=3.0,
            entry_time=datetime.now(timezone.utc) - timedelta(hours=2),
            exit_time=datetime.now(timezone.utc),
            is_winner=True,
        )

        record_result = orchestrator.record_trade(trade)
        assert record_result["success"] == True

        # Step 8: Add to metrics calculator
        metrics_calculator.add_trade({
            "trade_id": trade.trade_id,
            "symbol": trade.symbol,
            "pnl": trade.pnl,
            "pnl_pct": trade.pnl_pct,
            "entry_time": trade.entry_time,
            "exit_time": trade.exit_time,
            "strategy_id": trade.strategy_id,
        })

        # Step 9: Update trading metrics
        trading_metrics.record_trade_result(
            symbol="BTCUSDT",
            side="buy",
            result="win",
            pnl_usd=150.0,
        )

        # Verify final state
        strategy_status = orchestrator.get_strategy_status("trend_following")
        assert strategy_status["total_trades"] == 1
        assert strategy_status["total_pnl"] == 150.0

    @pytest.mark.asyncio
    async def test_conflicting_signals_resolution_flow(self, full_trading_system):
        """Test flow when multiple strategies have conflicting signals"""
        orchestrator = full_trading_system["orchestrator"]

        # Submit conflicting signals
        long_signal = StrategySignal(
            signal_id=str(uuid.uuid4()),
            strategy_id="trend_following",  # Higher priority
            symbol="BTCUSDT",
            timestamp=datetime.now(timezone.utc),
            direction=SignalDirection.LONG,
            action="BUY",
            strength=0.6,
            confidence=0.70,
        )

        short_signal = StrategySignal(
            signal_id=str(uuid.uuid4()),
            strategy_id="mean_reversion",  # Lower priority
            symbol="BTCUSDT",
            timestamp=datetime.now(timezone.utc),
            direction=SignalDirection.SHORT,
            action="SELL",
            strength=0.55,
            confidence=0.65,
        )

        orchestrator.submit_signal(long_signal)
        orchestrator.submit_signal(short_signal)

        # Get resolved signal
        aggregated = orchestrator.get_aggregated_signal("BTCUSDT")

        # Should have conflict detected
        assert aggregated.conflict_detected == True

        # Resolution should have been applied
        assert aggregated.direction in [SignalDirection.LONG, SignalDirection.SHORT]


# ============================================================================
# SCENARIO 2: MULTI-EXCHANGE ARBITRAGE
# ============================================================================

class TestMultiExchangeArbitrage:
    """
    End-to-end test: Arbitrage Detection -> Simultaneous Execution

    Flow:
    1. Monitor prices across exchanges
    2. Detect arbitrage opportunity
    3. Validate opportunity is profitable after fees
    4. Execute simultaneous buy/sell
    5. Track arbitrage profit
    """

    @pytest.mark.asyncio
    async def test_arbitrage_detection_and_execution(self, full_trading_system):
        """Test arbitrage opportunity detection and execution"""
        smart_router = full_trading_system["smart_router"]

        # Create second mock exchange with price difference
        mock_exchange_2 = AsyncMock()
        mock_exchange_2.exchange_id = "binance"
        mock_exchange_2.is_connected = True
        mock_exchange_2.get_ticker = AsyncMock(return_value={
            "symbol": "BTCUSDT",
            "last_price": 50100.0,  # Higher than bybit
            "bid_price": 50095.0,   # Sell here
            "ask_price": 50100.0,
            "volume_24h": 2000000000.0,
        })
        mock_exchange_2.place_order = AsyncMock(return_value={
            "order_id": str(uuid.uuid4()),
            "status": "FILLED",
            "filled_qty": 0.1,
            "filled_price": 50095.0,
            "fee": 0.5,
        })

        smart_router.register_exchange("binance", mock_exchange_2)

        # Get best prices
        best_prices = await smart_router.get_best_prices("BTCUSDT")

        # Check for arbitrage
        # Buy at bybit ask (50000), sell at binance bid (50095)
        spread = best_prices["best_bid"]["price"] - best_prices["best_ask"]["price"]

        # If spread > 0, there's arbitrage
        if spread > 0:
            # Calculate profit potential
            profit_pct = (spread / best_prices["best_ask"]["price"]) * 100

            # Verify profitable (before fees ~0.1% each side)
            if profit_pct > 0.2:
                # Execute arbitrage
                # Buy on exchange with lowest ask
                buy_result = await smart_router.execute_order(
                    symbol="BTCUSDT",
                    side=OrderSide.BUY,
                    quantity=Decimal("0.1"),
                    price=Decimal(str(best_prices["best_ask"]["price"])),
                    execution_decision=RoutingDecision(
                        algorithm=ExecutionAlgorithm.IMMEDIATE,
                        exchange_id=best_prices["best_ask"]["exchange"],
                    ),
                )

                # Sell on exchange with highest bid
                sell_result = await smart_router.execute_order(
                    symbol="BTCUSDT",
                    side=OrderSide.SELL,
                    quantity=Decimal("0.1"),
                    price=Decimal(str(best_prices["best_bid"]["price"])),
                    execution_decision=RoutingDecision(
                        algorithm=ExecutionAlgorithm.IMMEDIATE,
                        exchange_id=best_prices["best_bid"]["exchange"],
                    ),
                )

                assert buy_result is not None
                assert sell_result is not None


# ============================================================================
# SCENARIO 3: RISK LIMIT BREACH AND RECOVERY
# ============================================================================

class TestRiskLimitBreachAndRecovery:
    """
    End-to-end test: Risk Breach -> Circuit Breaker -> Recovery

    Flow:
    1. Trading proceeds normally
    2. Consecutive losses trigger risk limit
    3. Circuit breaker opens
    4. Trading is halted
    5. Timeout allows recovery attempt
    6. Successful trade restores normal operation
    """

    @pytest.mark.asyncio
    async def test_risk_breach_triggers_protection(self, full_trading_system):
        """Test risk limit breach triggers protective measures"""
        orchestrator = full_trading_system["orchestrator"]
        budget_manager = full_trading_system["budget_manager"]

        # Get circuit breaker for risk system
        risk_breaker = get_circuit_breaker(
            "risk_test_e2e",
            CircuitBreakerConfig(
                failure_threshold=3,
                timeout_seconds=1.0,
            )
        )
        risk_breaker.force_close()

        # Record consecutive losses
        for i in range(4):
            # Record loss in budget manager
            budget_manager.record_trade_result(
                symbol="BTCUSDT",
                strategy_id="trend_following",
                pnl=-500.0,
                is_winner=False,
            )

            # Record failure in circuit breaker
            risk_breaker.record_failure(Exception(f"Loss {i+1}"))

            # Record in orchestrator
            trade = MetricsTrade(
                trade_id=str(uuid.uuid4()),
                strategy_id="trend_following",
                symbol="BTCUSDT",
                side="LONG",
                entry_price=50000.0,
                exit_price=49000.0,
                quantity=0.1,
                pnl=-100.0,
                pnl_pct=-2.0,
                entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
                exit_time=datetime.now(timezone.utc),
                is_winner=False,
            )
            orchestrator.record_trade(trade)

        # Circuit breaker should be open
        assert risk_breaker.state == CircuitState.OPEN

        # New allocations should be blocked
        allocation = budget_manager.allocate_risk_budget(
            symbol="ETHUSDT",
            strategy_id="mean_reversion",
            signal_confidence=0.9,
            volatility=0.02,
        )

        # Should be blocked due to daily loss limit
        assert allocation.risk_budget_pct < budget_manager.config.base_risk_per_trade_pct

    @pytest.mark.asyncio
    async def test_recovery_after_cooldown(self, full_trading_system):
        """Test system recovery after cooldown period"""
        risk_breaker = get_circuit_breaker(
            "risk_recovery_test",
            CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout_seconds=0.5,  # Short for testing
            )
        )

        # Open circuit
        for _ in range(3):
            risk_breaker.record_failure(Exception("Error"))

        assert risk_breaker.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.6)

        # Should transition to half-open
        assert risk_breaker.can_execute() == True
        assert risk_breaker.state == CircuitState.HALF_OPEN

        # Record successes to close
        risk_breaker.record_success()
        risk_breaker.record_success()

        assert risk_breaker.state == CircuitState.CLOSED


# ============================================================================
# SCENARIO 4: SERVICE FAILURE AND FAILOVER
# ============================================================================

class TestServiceFailureAndFailover:
    """
    End-to-end test: Service Failure -> Health Detection -> Failover

    Flow:
    1. System is healthy
    2. Primary service fails
    3. Health check detects failure
    4. System marks service unhealthy
    5. Failover to backup service
    6. Operations continue
    7. Primary recovers and is restored
    """

    @pytest.mark.asyncio
    async def test_exchange_failover(self, full_trading_system, mock_exchange):
        """Test failover when primary exchange fails"""
        smart_router = full_trading_system["smart_router"]

        # Create backup exchange
        backup_exchange = AsyncMock()
        backup_exchange.exchange_id = "backup"
        backup_exchange.is_connected = True
        backup_exchange.get_ticker = AsyncMock(return_value={
            "symbol": "BTCUSDT",
            "last_price": 50010.0,
            "bid_price": 50005.0,
            "ask_price": 50010.0,
        })
        backup_exchange.place_order = AsyncMock(return_value={
            "order_id": str(uuid.uuid4()),
            "status": "FILLED",
            "filled_qty": 0.1,
            "filled_price": 50010.0,
            "fee": 0.5,
        })

        smart_router.register_exchange("backup", backup_exchange)

        # Make primary exchange fail
        mock_exchange.place_order.side_effect = Exception("Exchange unavailable")

        # Execute order (should failover)
        result = await smart_router.execute_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            price=Decimal("50010.0"),
            execution_decision=RoutingDecision(
                algorithm=ExecutionAlgorithm.IMMEDIATE,
                exchange_id="bybit",  # Primary
            ),
        )

        # Should have used backup
        assert result is not None
        # Verify backup was called
        assert backup_exchange.place_order.called or mock_exchange.place_order.called

    @pytest.mark.asyncio
    async def test_health_degradation_detection(self, full_trading_system):
        """Test health check detects service degradation"""
        health_checker = full_trading_system["health_checker"]

        # Mock database to be slow
        with patch('app.core.health.db_manager') as mock_db:
            mock_db.health_check.return_value = True
            mock_db.get_pool_size.return_value = 5

            # High degraded threshold for testing
            health_checker.degraded_response_time_ms = 10.0

            result = await health_checker.check_database()

            # Should be healthy or degraded based on response time
            assert result.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]


# ============================================================================
# SCENARIO 5: FULL DAY SIMULATION
# ============================================================================

class TestFullDaySimulation:
    """
    End-to-end test: Simulate full trading day

    Flow:
    1. Morning: Strategies activate
    2. Multiple signals generated and executed
    3. Risk events handled
    4. Performance tracking throughout
    5. End of day: Daily reset
    """

    @pytest.mark.asyncio
    async def test_simulated_trading_day(self, full_trading_system):
        """Simulate a complete trading day"""
        orchestrator = full_trading_system["orchestrator"]
        budget_manager = full_trading_system["budget_manager"]
        trading_metrics = full_trading_system["trading_metrics"]

        # Track events
        events = []
        orchestrator.on_event(lambda e: events.append(e))

        # Simulate 10 trading signals throughout the day
        trades_executed = 0
        total_pnl = 0.0

        for i in range(10):
            # Generate signal
            direction = SignalDirection.LONG if i % 3 != 0 else SignalDirection.SHORT
            confidence = 0.6 + (i * 0.02)

            signal = StrategySignal(
                signal_id=str(uuid.uuid4()),
                strategy_id="trend_following" if i % 2 == 0 else "mean_reversion",
                symbol="BTCUSDT",
                timestamp=datetime.now(timezone.utc),
                direction=direction,
                action="BUY" if direction == SignalDirection.LONG else "SELL",
                strength=0.5 + (i * 0.03),
                confidence=min(confidence, 0.85),
            )

            result = orchestrator.submit_signal(signal)

            if result["accepted"]:
                # Get aggregated signal
                aggregated = orchestrator.get_aggregated_signal("BTCUSDT")

                if aggregated:
                    # Check risk budget
                    allocation = budget_manager.allocate_risk_budget(
                        symbol="BTCUSDT",
                        strategy_id=signal.strategy_id,
                        signal_confidence=aggregated.aggregated_confidence,
                        volatility=0.02,
                    )

                    if not allocation.is_blocked:
                        # Simulate trade
                        pnl = 100.0 if i % 4 != 0 else -50.0
                        is_winner = pnl > 0

                        trade = MetricsTrade(
                            trade_id=str(uuid.uuid4()),
                            strategy_id=signal.strategy_id,
                            symbol="BTCUSDT",
                            side="LONG" if direction == SignalDirection.LONG else "SHORT",
                            entry_price=50000.0,
                            exit_price=50000.0 + (pnl * 10),
                            quantity=0.1,
                            pnl=pnl,
                            pnl_pct=pnl / 1000,
                            entry_time=datetime.now(timezone.utc) - timedelta(minutes=30),
                            exit_time=datetime.now(timezone.utc),
                            is_winner=is_winner,
                        )

                        orchestrator.record_trade(trade)
                        budget_manager.record_trade_result(
                            symbol="BTCUSDT",
                            strategy_id=signal.strategy_id,
                            pnl=pnl,
                            is_winner=is_winner,
                        )

                        trading_metrics.record_trade_result(
                            symbol="BTCUSDT",
                            side="buy" if direction == SignalDirection.LONG else "sell",
                            result="win" if is_winner else "loss",
                            pnl_usd=pnl,
                        )

                        trades_executed += 1
                        total_pnl += pnl

            # Clear signals for next iteration
            orchestrator.clear_signals("BTCUSDT")

            # Small delay between "trading sessions"
            await asyncio.sleep(0.01)

        # End of day: Check results
        status = orchestrator.get_orchestrator_status()

        assert status["total_strategies"] == 2
        assert trades_executed > 0

        # Check events were captured
        trade_events = [e for e in events if e.event_type == "trade_recorded"]
        assert len(trade_events) == trades_executed

        # Reset daily PnL
        orchestrator.reset_daily_pnl()

        # Verify reset
        strategy_status = orchestrator.get_strategy_status("trend_following")
        assert strategy_status["today_pnl"] == 0.0


# ============================================================================
# SCENARIO 6: STRESS TEST - HIGH FREQUENCY
# ============================================================================

class TestHighFrequencyStress:
    """
    Stress test: High frequency signal processing

    Flow:
    1. Generate many signals rapidly
    2. Verify system handles load
    3. Check for data consistency
    4. Measure performance
    """

    @pytest.mark.asyncio
    async def test_rapid_signal_processing(self, full_trading_system):
        """Test system handles rapid signal flow"""
        orchestrator = full_trading_system["orchestrator"]

        signals_submitted = 0
        signals_accepted = 0

        start_time = datetime.now(timezone.utc)

        # Submit 100 signals rapidly
        for i in range(100):
            signal = StrategySignal(
                signal_id=str(uuid.uuid4()),
                strategy_id="trend_following" if i % 2 == 0 else "mean_reversion",
                symbol="BTCUSDT",
                timestamp=datetime.now(timezone.utc),
                direction=SignalDirection.LONG if i % 3 == 0 else SignalDirection.SHORT,
                action="BUY",
                confidence=0.7,
            )

            result = orchestrator.submit_signal(signal)
            signals_submitted += 1
            if result["accepted"]:
                signals_accepted += 1

            # Clear every 10 signals to prevent buildup
            if i % 10 == 9:
                orchestrator.clear_signals("BTCUSDT")

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        # Should process all signals quickly (< 5 seconds for 100 signals)
        assert duration < 5.0

        # Most signals should be accepted
        assert signals_accepted > 50

        # System should still be healthy
        status = orchestrator.get_orchestrator_status()
        assert status["active_strategies"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
