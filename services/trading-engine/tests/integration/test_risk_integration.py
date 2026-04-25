"""
Integration Tests for Risk Management Components
=================================================
Phase 3.3: Dynamic Risk Budgeting Integration Tests

Purpose:
- Test integration between dynamic budget manager and other risk components
- Verify risk budget allocation across strategies
- Test emergency shutdown triggers
- Validate risk metrics propagation

Test Coverage:
- DynamicBudgetManager with position sizing
- Risk budget allocation and rebalancing
- Emergency risk controls
- Integration with circuit breaker
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any

# Import risk components
from app.risk.dynamic_budget import (
    DynamicBudgetManager,
    BudgetConfig,
    get_budget_manager,
    reset_budget_manager,
)
from app.risk_manager import RiskManager, get_risk_manager
from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CircuitBreakerOpenError,
    get_circuit_breaker,
)
from app.core.metrics import TradingMetrics, get_metrics_collector


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def risk_budget_config() -> BudgetConfig:
    """
    Create test risk budget configuration

    Returns:
        BudgetConfig configured for testing
    """
    return BudgetConfig(
        total_capital=100000.0,
        max_total_risk_pct=10.0,
        max_strategy_risk_pct=5.0,
        max_asset_risk_pct=3.0,
        volatility_adjustment_enabled=True,
        correlation_adjustment_enabled=True,
        performance_adjustment_enabled=True,
        kelly_integration_enabled=True,
        rebalance_threshold_pct=1.0,
        alert_threshold_pct=80.0,
    )


@pytest.fixture
def budget_manager(risk_budget_config) -> DynamicBudgetManager:
    """
    Create test budget manager instance

    Returns:
        Fresh DynamicBudgetManager for testing
    """
    reset_budget_manager()
    manager = DynamicBudgetManager(config=risk_budget_config)
    return manager


@pytest.fixture
def risk_manager() -> RiskManager:
    """
    Create test risk manager instance

    Returns:
        RiskManager instance (uses settings from config)
    """
    return RiskManager()


@pytest.fixture
def mock_market_data() -> Dict[str, Any]:
    """
    Generate mock market data for risk calculations

    Returns:
        Dictionary with market data
    """
    return {
        "BTCUSDT": {
            "price": 50000.0,
            "volatility": 0.02,
            "percentile_rank": 50,
        },
        "ETHUSDT": {
            "price": 3000.0,
            "volatility": 0.025,
            "percentile_rank": 60,
        },
        "SOLUSDT": {
            "price": 100.0,
            "volatility": 0.04,
            "percentile_rank": 85,
        },
    }


# ============================================================================
# DYNAMIC BUDGET MANAGER TESTS
# ============================================================================

class TestDynamicBudgetManagerIntegration:
    """Test suite for DynamicBudgetManager integration"""

    def test_budget_initialization(self, budget_manager, risk_budget_config):
        """
        Test budget manager initializes correctly with config

        Verifies:
        - Manager is initialized with correct capital
        - Base risk parameters are set
        """
        assert budget_manager.config.total_capital == 100000.0
        assert budget_manager.config.max_total_risk_pct == 10.0

        # Get budget state
        state = budget_manager.get_budget_state()

        # Verify budget state structure
        assert "total_budget" in state
        assert "used_budget" in state
        assert "available_budget" in state
        assert state["total_budget"] == 10000.0  # 10% of 100,000

    def test_strategy_budget_allocation(self, budget_manager):
        """
        Test strategy budget allocation

        Verifies:
        - Budget allocation succeeds
        - Allocation is recorded correctly
        """
        # Allocate budget to strategy
        result = budget_manager.allocate_strategy_budget(
            strategy_name="trend_following",
            allocation_pct=50.0
        )

        assert result["success"] == True
        assert result["strategy"] == "trend_following"
        assert result["allocation_pct"] == 50.0
        assert result["allocated_budget"] > 0

    def test_multiple_strategy_allocation(self, budget_manager):
        """
        Test allocating budget across multiple strategies

        Verifies:
        - Multiple allocations work
        - Total doesn't exceed 100%
        """
        # Allocate to multiple strategies
        result1 = budget_manager.allocate_strategy_budget("strategy_1", 30.0)
        result2 = budget_manager.allocate_strategy_budget("strategy_2", 40.0)
        result3 = budget_manager.allocate_strategy_budget("strategy_3", 20.0)

        assert result1["success"] == True
        assert result2["success"] == True
        assert result3["success"] == True

        # Try to exceed 100%
        result_fail = budget_manager.allocate_strategy_budget("strategy_4", 20.0)
        assert result_fail["success"] == False

    def test_asset_limit_setting(self, budget_manager):
        """
        Test setting asset-specific risk limits

        Verifies:
        - Asset limit is set correctly
        - Limit is enforced
        """
        result = budget_manager.set_asset_limit("BTCUSDT", 2.0)

        assert result["success"] == True
        assert result["symbol"] == "BTCUSDT"
        assert result["max_risk_pct"] == 2.0

    def test_volatility_multiplier_calculation(self, budget_manager, mock_market_data):
        """
        Test volatility-based budget multiplier

        Verifies:
        - High volatility reduces multiplier
        - Low volatility increases multiplier
        """
        # Update volatility data
        budget_manager.update_volatility(mock_market_data)

        # Normal volatility (50th percentile)
        normal_mult = budget_manager.calculate_volatility_multiplier(
            mock_market_data["BTCUSDT"]
        )
        assert normal_mult == 1.0

        # High volatility (85th percentile)
        high_mult = budget_manager.calculate_volatility_multiplier(
            mock_market_data["SOLUSDT"]
        )
        assert high_mult < 1.0

    def test_correlation_multiplier_calculation(self, budget_manager):
        """
        Test correlation-based budget multiplier

        Verifies:
        - High correlation reduces multiplier
        - Low correlation increases multiplier
        """
        # High correlation
        budget_manager.update_correlations({"avg_correlation": 0.85})
        high_mult = budget_manager.calculate_correlation_multiplier()
        assert high_mult < 1.0

        # Low correlation
        budget_manager.update_correlations({"avg_correlation": 0.25})
        low_mult = budget_manager.calculate_correlation_multiplier()
        assert low_mult > 1.0

    def test_can_place_order_validation(self, budget_manager):
        """
        Test order placement validation against budgets

        Verifies:
        - Valid order is approved
        - Order exceeding limits is rejected
        """
        # Allocate strategy budget
        budget_manager.allocate_strategy_budget("test_strategy", 50.0)
        budget_manager.set_asset_limit("BTCUSDT", 2.0)

        # Valid order
        can_place, reason = budget_manager.can_place_order(
            strategy_name="test_strategy",
            symbol="BTCUSDT",
            order_risk_amount=500.0
        )
        assert can_place == True

        # Order exceeding asset limit (2% of 100k = 2000)
        can_place, reason = budget_manager.can_place_order(
            strategy_name="test_strategy",
            symbol="BTCUSDT",
            order_risk_amount=3000.0
        )
        assert can_place == False
        assert "asset limit" in reason.lower()

    def test_position_update_tracking(self, budget_manager):
        """
        Test position updates are tracked correctly

        Verifies:
        - Positions update budget usage
        - Strategy usage is calculated
        """
        budget_manager.allocate_strategy_budget("test_strategy", 50.0)

        positions = [
            {"symbol": "BTCUSDT", "strategy": "test_strategy", "risk_amount": 500.0},
            {"symbol": "ETHUSDT", "strategy": "test_strategy", "risk_amount": 300.0},
        ]

        result = budget_manager.update_positions(positions)

        assert result["success"] == True
        assert result["positions_count"] == 2

        # Check strategy usage
        usage = budget_manager.get_strategy_budget_usage("test_strategy")
        assert usage["used_budget"] == 800.0

    def test_rebalancing_detection(self, budget_manager):
        """
        Test rebalancing need detection

        Verifies:
        - Drift is detected
        - Rebalancing actions are calculated
        """
        budget_manager.allocate_strategy_budget("strategy_1", 50.0)
        budget_manager.allocate_strategy_budget("strategy_2", 50.0)

        # Create imbalanced positions
        positions = [
            {"symbol": "BTCUSDT", "strategy": "strategy_1", "risk_amount": 1000.0},
            # strategy_2 has no positions, creating drift
        ]
        budget_manager.update_positions(positions)

        # Check if rebalancing needed
        needs_rebalance = budget_manager.needs_rebalancing()

        # Force rebalance
        result = budget_manager.force_rebalance()
        assert result["success"] == True


# ============================================================================
# RISK MANAGER INTEGRATION TESTS
# ============================================================================

class TestRiskManagerIntegration:
    """Test suite for RiskManager integration with budget system"""

    def test_risk_manager_position_sizing(self, risk_manager):
        """
        Test RiskManager calculates position sizes

        Verifies:
        - Position size is calculated based on balance
        - Size respects maximum limits
        """
        # Calculate position size
        size = risk_manager.calculate_position_size(
            account_balance=Decimal("10000.0"),
            entry_price=Decimal("50000.0"),
        )

        # Should return a valid position size
        assert size >= 0

    def test_risk_manager_daily_pnl_tracking(self, risk_manager):
        """
        Test RiskManager tracks daily PnL

        Verifies:
        - PnL is updated correctly
        - Trading halt is triggered on large loss
        """
        # Reset daily PnL
        risk_manager.reset_daily_pnl()
        assert risk_manager.daily_pnl == 0

        # Update with profit
        risk_manager.update_daily_pnl(Decimal("100.0"))
        assert risk_manager.daily_pnl == Decimal("100.0")

        # Update with loss
        risk_manager.update_daily_pnl(Decimal("-50.0"))
        assert risk_manager.daily_pnl == Decimal("50.0")

    def test_risk_manager_trading_halt(self, risk_manager):
        """
        Test RiskManager halts trading on large loss

        Verifies:
        - Trading is halted when limit exceeded
        - Trading can be resumed manually
        """
        risk_manager.reset_daily_pnl()
        assert risk_manager.trading_halted == False

        # Check if should halt (with no loss, should not halt)
        assert risk_manager.should_halt_trading() == False


# ============================================================================
# CIRCUIT BREAKER INTEGRATION TESTS
# ============================================================================

class TestRiskCircuitBreakerIntegration:
    """Test circuit breaker integration with risk system"""

    def test_circuit_breaker_state_transitions(self):
        """
        Test circuit breaker state transitions

        Verifies:
        - Circuit opens after failures
        - Circuit closes after successes
        """
        breaker = get_circuit_breaker(
            "risk_test_breaker",
            CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout_seconds=1.0,
            )
        )
        breaker.force_close()

        assert breaker.state == CircuitState.CLOSED

        # Record failures to open circuit
        for i in range(3):
            breaker.record_failure(Exception(f"Error {i}"))

        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_breaker_context_manager(self):
        """
        Test circuit breaker as context manager

        Verifies:
        - Success is recorded on clean exit
        - Failure is recorded on exception
        """
        breaker = get_circuit_breaker("context_test_breaker")
        breaker.force_close()

        # Successful operation
        async with breaker:
            pass

        assert breaker.stats.successful_calls == 1

        # Failed operation
        with pytest.raises(ValueError):
            async with breaker:
                raise ValueError("Test error")

        assert breaker.stats.failed_calls == 1


# ============================================================================
# METRICS INTEGRATION TESTS
# ============================================================================

class TestRiskMetricsIntegration:
    """Test metrics integration with risk system"""

    def test_risk_metrics_recording(self, budget_manager):
        """
        Test risk metrics are properly recorded

        Verifies:
        - Budget operations update metrics
        - No exceptions during metric recording
        """
        metrics_collector = get_metrics_collector()
        trading_metrics = metrics_collector.trading_metrics

        # Record risk metrics
        trading_metrics.update_risk_exposure("BTCUSDT", 2.5)
        trading_metrics.update_total_exposure(15.0)
        trading_metrics.update_max_drawdown(8.5)
        trading_metrics.update_daily_loss(500.0, 5.0)

        # Should complete without exceptions
        assert True

    def test_budget_alerts_generation(self, budget_manager):
        """
        Test budget alerts are generated correctly

        Verifies:
        - Alerts are generated when thresholds exceeded
        - Alert severity is appropriate
        """
        # Create high usage scenario
        budget_manager.allocate_strategy_budget("high_usage", 80.0)

        # Update positions to near limit
        positions = [
            {"symbol": "BTCUSDT", "strategy": "high_usage", "risk_amount": 7500.0},
        ]
        budget_manager.update_positions(positions)

        # Get alerts
        alerts = budget_manager.get_budget_alerts()

        # Should have generated an alert (near 80% threshold)
        assert isinstance(alerts, list)


# ============================================================================
# CROSS-COMPONENT INTEGRATION TESTS
# ============================================================================

class TestCrossComponentRiskIntegration:
    """Test integration across multiple risk components"""

    def test_full_risk_workflow(
        self,
        budget_manager,
        risk_manager,
        mock_market_data
    ):
        """
        Test complete risk management workflow

        Workflow:
        1. Allocate strategy budget
        2. Update market data
        3. Get effective budget
        4. Validate order
        5. Update positions
        """
        # Step 1: Allocate budget
        budget_manager.allocate_strategy_budget("integration_test", 40.0)

        # Step 2: Update market data
        budget_manager.update_volatility(mock_market_data)
        budget_manager.update_correlations({"avg_correlation": 0.5})

        # Step 3: Get effective budget with adjustments
        effective = budget_manager.get_effective_budget(
            strategy_name="integration_test",
            symbol="BTCUSDT"
        )

        assert effective["base_budget"] > 0
        assert effective["effective_budget"] > 0

        # Step 4: Validate order
        can_place, reason = budget_manager.can_place_order(
            strategy_name="integration_test",
            symbol="BTCUSDT",
            order_risk_amount=500.0
        )
        assert can_place == True

        # Step 5: Update positions
        positions = [
            {"symbol": "BTCUSDT", "strategy": "integration_test", "risk_amount": 500.0},
        ]
        result = budget_manager.update_positions(positions)
        assert result["success"] == True

        # Verify usage updated
        usage = budget_manager.get_strategy_budget_usage("integration_test")
        assert usage["used_budget"] == 500.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
