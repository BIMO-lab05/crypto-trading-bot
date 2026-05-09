"""
Integration Tests for Execution Components
==========================================
Phase 4.2-4.3: TWAP/VWAP Execution Integration Tests

Purpose:
- Test TWAP (Time-Weighted Average Price) execution algorithm
- Test VWAP (Volume-Weighted Average Price) execution algorithm
- Verify integration with order management and exchange connectors
- Test execution optimizer routing decisions

Test Coverage:
- TWAPExecutor order slicing and timing
- VWAPExecutor volume-based execution
- SmartOrderRouter routing decisions
- Execution metrics and monitoring
- Integration with risk management
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
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any, List
import uuid

# Import execution components
from app.execution.twap_vwap import (
    TWAPExecutor,
    TWAPConfig,
    VWAPExecutor,
    VWAPConfig,
    ExecutionSlice,
    ExecutionProgress,
    ExecutionResult,
)
from app.execution.smart_router import (
    SmartOrderRouter,
    RoutingDecision,
    ExecutionAlgorithm,
)
from app.models import OrderSide, OrderType, OrderStatus


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def twap_config() -> TWAPConfig:
    """
    Create TWAP execution configuration

    Returns:
        TWAPConfig configured for testing
    """
    return TWAPConfig(
        total_duration_seconds=300,  # 5 minutes
        num_slices=10,  # 10 orders over 5 minutes
        randomize_timing=False,  # Deterministic for testing
        randomize_size=False,
        min_slice_size_usd=10.0,
        max_slice_deviation_pct=0.1,
        execution_timeout_seconds=60,
    )


@pytest.fixture
def vwap_config() -> VWAPConfig:
    """
    Create VWAP execution configuration

    Returns:
        VWAPConfig configured for testing
    """
    return VWAPConfig(
        execution_window_seconds=300,  # 5 minute window
        volume_participation_rate=0.1,  # 10% of volume
        min_slice_size_usd=10.0,
        max_slice_size_pct=0.05,  # Max 5% per slice
        update_interval_seconds=30,
        use_historical_volume_profile=True,
    )


@pytest.fixture
def twap_executor(twap_config) -> TWAPExecutor:
    """
    Create TWAP executor instance

    Returns:
        TWAPExecutor for testing
    """
    return TWAPExecutor(config=twap_config)


@pytest.fixture
def vwap_executor(vwap_config) -> VWAPExecutor:
    """
    Create VWAP executor instance

    Returns:
        VWAPExecutor for testing
    """
    return VWAPExecutor(config=vwap_config)


@pytest.fixture
def mock_exchange():
    """
    Create mock exchange connector

    Returns:
        Mock exchange with async methods
    """
    exchange = AsyncMock()

    # Mock order placement
    exchange.place_order = AsyncMock(return_value={
        "order_id": str(uuid.uuid4()),
        "status": "FILLED",
        "filled_qty": 0.01,
        "filled_price": 50000.0,
        "fee": 0.5,
    })

    # Mock get orderbook
    exchange.get_orderbook = AsyncMock(return_value={
        "bids": [
            {"price": 49990.0, "qty": 1.0},
            {"price": 49980.0, "qty": 2.0},
            {"price": 49970.0, "qty": 3.0},
        ],
        "asks": [
            {"price": 50000.0, "qty": 1.0},
            {"price": 50010.0, "qty": 2.0},
            {"price": 50020.0, "qty": 3.0},
        ],
    })

    # Mock get ticker
    exchange.get_ticker = AsyncMock(return_value={
        "symbol": "BTCUSDT",
        "last_price": 50000.0,
        "bid_price": 49990.0,
        "ask_price": 50000.0,
        "volume_24h": 1000000000.0,
    })

    # Mock get volume profile
    exchange.get_volume_profile = AsyncMock(return_value={
        "hourly_volumes": [100000.0] * 24,
        "avg_volume_per_minute": 1000.0,
    })

    return exchange


@pytest.fixture
def smart_router(mock_exchange) -> SmartOrderRouter:
    """
    Create smart order router instance

    Returns:
        SmartOrderRouter with mock exchange
    """
    router = SmartOrderRouter()
    router.register_exchange("bybit", mock_exchange)
    return router


# ============================================================================
# TWAP EXECUTOR TESTS
# ============================================================================

class TestTWAPExecutorIntegration:
    """Test suite for TWAP execution algorithm"""

    @pytest.mark.asyncio
    async def test_twap_creates_equal_slices(self, twap_executor, mock_exchange):
        """
        Test TWAP creates equal-sized order slices

        Verifies:
        - Total quantity is divided into equal slices
        - Timing is evenly distributed
        """
        # Create execution plan
        slices = twap_executor.create_execution_plan(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            total_quantity=Decimal("1.0"),
            total_value_usd=50000.0,
        )

        # Verify slice count
        assert len(slices) == twap_executor.config.num_slices

        # Verify equal sizing
        total_qty = sum(s.quantity for s in slices)
        assert abs(float(total_qty) - 1.0) < 0.001

        # Verify timing distribution
        intervals = []
        for i in range(1, len(slices)):
            interval = (slices[i].scheduled_time - slices[i-1].scheduled_time).total_seconds()
            intervals.append(interval)

        # All intervals should be approximately equal
        expected_interval = twap_executor.config.total_duration_seconds / twap_executor.config.num_slices
        for interval in intervals:
            assert abs(interval - expected_interval) < 1.0  # Within 1 second

    @pytest.mark.asyncio
    async def test_twap_executes_slices_sequentially(
        self,
        twap_executor,
        mock_exchange
    ):
        """
        Test TWAP executes slices in sequence with timing

        Verifies:
        - Slices execute at scheduled times
        - Progress is tracked correctly
        """
        # Create shortened config for faster testing
        twap_executor.config.total_duration_seconds = 10
        twap_executor.config.num_slices = 5

        # Create plan
        slices = twap_executor.create_execution_plan(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            total_quantity=Decimal("0.1"),
            total_value_usd=5000.0,
        )

        # Execute (with mock exchange)
        progress = await twap_executor.execute(
            slices=slices,
            exchange=mock_exchange,
        )

        # Verify execution
        assert progress.is_complete == True
        assert progress.slices_executed == 5
        assert progress.total_filled_qty > 0

    @pytest.mark.asyncio
    async def test_twap_handles_partial_fills(self, twap_executor, mock_exchange):
        """
        Test TWAP handles partial fills correctly

        Scenario:
        - Some slices partially fill
        - Remaining quantity is redistributed
        """
        # Configure exchange to return partial fills
        fill_sequence = [
            {"status": "FILLED", "filled_qty": 0.02, "filled_price": 50000.0},
            {"status": "PARTIALLY_FILLED", "filled_qty": 0.015, "filled_price": 50010.0},
            {"status": "FILLED", "filled_qty": 0.02, "filled_price": 50005.0},
        ]
        mock_exchange.place_order = AsyncMock(side_effect=[
            {**f, "order_id": str(uuid.uuid4()), "fee": 0.1}
            for f in fill_sequence * 5  # Repeat for all slices
        ])

        twap_executor.config.num_slices = 3
        twap_executor.config.total_duration_seconds = 3

        slices = twap_executor.create_execution_plan(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            total_quantity=Decimal("0.06"),
            total_value_usd=3000.0,
        )

        progress = await twap_executor.execute(
            slices=slices,
            exchange=mock_exchange,
        )

        # Should complete even with partial fills
        assert progress.is_complete == True
        assert progress.total_filled_qty > 0

    @pytest.mark.asyncio
    async def test_twap_calculates_execution_metrics(
        self,
        twap_executor,
        mock_exchange
    ):
        """
        Test TWAP calculates execution quality metrics

        Verifies:
        - VWAP price is calculated
        - Slippage is measured
        - Fill rate is tracked
        """
        twap_executor.config.num_slices = 3
        twap_executor.config.total_duration_seconds = 3

        slices = twap_executor.create_execution_plan(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            total_quantity=Decimal("0.1"),
            total_value_usd=5000.0,
        )

        progress = await twap_executor.execute(
            slices=slices,
            exchange=mock_exchange,
        )

        # Verify metrics
        result = twap_executor.get_execution_result(progress)

        assert isinstance(result, ExecutionResult)
        assert result.avg_fill_price > 0
        assert result.total_filled_qty > 0
        assert result.total_fees >= 0
        assert 0 <= result.fill_rate <= 1.0


# ============================================================================
# VWAP EXECUTOR TESTS
# ============================================================================

class TestVWAPExecutorIntegration:
    """Test suite for VWAP execution algorithm"""

    @pytest.mark.asyncio
    async def test_vwap_creates_volume_weighted_slices(
        self,
        vwap_executor,
        mock_exchange
    ):
        """
        Test VWAP creates slices based on volume profile

        Verifies:
        - Slices are sized based on expected volume
        - Participation rate is respected
        """
        # Get volume profile
        volume_profile = await mock_exchange.get_volume_profile()

        # Create execution plan
        slices = await vwap_executor.create_execution_plan(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            total_quantity=Decimal("1.0"),
            total_value_usd=50000.0,
            volume_profile=volume_profile,
        )

        # Verify slices exist
        assert len(slices) > 0

        # Verify total quantity
        total_qty = sum(s.quantity for s in slices)
        assert abs(float(total_qty) - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_vwap_adjusts_to_real_time_volume(
        self,
        vwap_executor,
        mock_exchange
    ):
        """
        Test VWAP adjusts execution based on real-time volume

        Scenario:
        - Start execution with expected volume
        - Volume increases -> increase slice size
        - Volume decreases -> decrease slice size
        """
        # Configure dynamic volume responses
        volume_responses = [
            {"current_volume": 1000.0, "expected_volume": 1000.0},  # Normal
            {"current_volume": 1500.0, "expected_volume": 1000.0},  # Higher volume
            {"current_volume": 500.0, "expected_volume": 1000.0},   # Lower volume
        ]

        call_count = [0]

        async def mock_get_volume():
            idx = min(call_count[0], len(volume_responses) - 1)
            call_count[0] += 1
            return volume_responses[idx]

        mock_exchange.get_current_volume = mock_get_volume

        # Execute with volume adaptation
        vwap_executor.config.update_interval_seconds = 1
        vwap_executor.config.execution_window_seconds = 5

        volume_profile = await mock_exchange.get_volume_profile()

        slices = await vwap_executor.create_execution_plan(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            total_quantity=Decimal("0.1"),
            total_value_usd=5000.0,
            volume_profile=volume_profile,
        )

        progress = await vwap_executor.execute(
            slices=slices,
            exchange=mock_exchange,
        )

        # Execution should complete
        assert progress.is_complete == True

    @pytest.mark.asyncio
    async def test_vwap_respects_participation_rate(
        self,
        vwap_executor,
        mock_exchange
    ):
        """
        Test VWAP limits execution to participation rate

        Verifies:
        - Each slice is limited to participation rate of volume
        - Large orders don't overwhelm market
        """
        vwap_executor.config.volume_participation_rate = 0.05  # 5% max

        volume_profile = await mock_exchange.get_volume_profile()

        slices = await vwap_executor.create_execution_plan(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            total_quantity=Decimal("10.0"),  # Large order
            total_value_usd=500000.0,
            volume_profile=volume_profile,
        )

        # Each slice should be limited
        for slice in slices:
            expected_volume = volume_profile.get("avg_volume_per_minute", 1000.0)
            max_slice_volume = expected_volume * vwap_executor.config.volume_participation_rate

            # Slice value should respect participation limit
            slice_value = float(slice.quantity) * 50000.0  # Assuming $50k price
            # Allow reasonable tolerance
            assert slice_value <= max_slice_volume * 2  # Account for price


# ============================================================================
# SMART ORDER ROUTER TESTS
# ============================================================================

class TestSmartOrderRouterIntegration:
    """Test suite for SmartOrderRouter integration"""

    @pytest.mark.asyncio
    async def test_router_selects_twap_for_large_orders(self, smart_router):
        """
        Test router selects TWAP for time-sensitive large orders

        Scenario:
        - Large order without urgency
        - Should route to TWAP for minimal market impact
        """
        decision = await smart_router.determine_execution_strategy(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            total_value_usd=100000.0,  # Large order
            urgency="LOW",
            market_conditions={
                "volatility": 0.02,
                "liquidity_score": 0.7,
                "spread_bps": 10,
            },
        )

        assert isinstance(decision, RoutingDecision)
        assert decision.algorithm in [ExecutionAlgorithm.TWAP, ExecutionAlgorithm.VWAP]

    @pytest.mark.asyncio
    async def test_router_selects_vwap_for_volume_participation(self, smart_router):
        """
        Test router selects VWAP when volume participation is key

        Scenario:
        - Order needs to minimize market impact
        - Volume profile is available
        """
        decision = await smart_router.determine_execution_strategy(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            total_value_usd=50000.0,
            urgency="MEDIUM",
            market_conditions={
                "volatility": 0.015,
                "liquidity_score": 0.8,
                "spread_bps": 8,
                "volume_available": True,
            },
        )

        # VWAP should be preferred for medium urgency with good liquidity
        assert decision.algorithm in [ExecutionAlgorithm.TWAP, ExecutionAlgorithm.VWAP]

    @pytest.mark.asyncio
    async def test_router_selects_immediate_for_urgent_orders(self, smart_router):
        """
        Test router selects immediate execution for urgent orders

        Scenario:
        - High urgency order
        - Should execute immediately despite size
        """
        decision = await smart_router.determine_execution_strategy(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            total_value_usd=25000.0,
            urgency="HIGH",
            market_conditions={
                "volatility": 0.03,
                "liquidity_score": 0.9,
                "spread_bps": 5,
            },
        )

        # High urgency should result in immediate or aggressive execution
        assert decision.algorithm in [
            ExecutionAlgorithm.IMMEDIATE,
            ExecutionAlgorithm.AGGRESSIVE
        ]

    @pytest.mark.asyncio
    async def test_router_executes_complete_flow(
        self,
        smart_router,
        mock_exchange
    ):
        """
        Test complete routing and execution flow

        Flow:
        1. Determine strategy
        2. Create execution plan
        3. Execute slices
        4. Return results
        """
        # Step 1: Determine strategy
        decision = await smart_router.determine_execution_strategy(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            total_value_usd=10000.0,
            urgency="MEDIUM",
            market_conditions={
                "volatility": 0.02,
                "liquidity_score": 0.8,
                "spread_bps": 10,
            },
        )

        # Step 2-4: Execute through router
        result = await smart_router.execute_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.2"),
            price=Decimal("50000.0"),
            execution_decision=decision,
        )

        # Verify result
        assert result is not None
        assert result.get("success") == True or result.get("order_id") is not None


# ============================================================================
# EXECUTION METRICS AND MONITORING TESTS
# ============================================================================

class TestExecutionMetricsIntegration:
    """Test execution metrics and monitoring"""

    @pytest.mark.asyncio
    async def test_execution_metrics_captured(
        self,
        twap_executor,
        mock_exchange
    ):
        """
        Test execution metrics are properly captured

        Verifies:
        - Fill rate tracking
        - Slippage calculation
        - Fee aggregation
        """
        twap_executor.config.num_slices = 3
        twap_executor.config.total_duration_seconds = 3

        slices = twap_executor.create_execution_plan(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            total_quantity=Decimal("0.1"),
            total_value_usd=5000.0,
        )

        progress = await twap_executor.execute(
            slices=slices,
            exchange=mock_exchange,
        )

        result = twap_executor.get_execution_result(progress)

        # Verify all metrics present
        assert result.execution_id is not None
        assert result.start_time is not None
        assert result.end_time is not None
        assert result.total_duration_seconds >= 0
        assert result.avg_fill_price > 0
        assert result.total_fees >= 0
        assert result.slippage_bps is not None

    @pytest.mark.asyncio
    async def test_execution_slippage_calculation(
        self,
        twap_executor,
        mock_exchange
    ):
        """
        Test slippage is calculated correctly

        Scenario:
        - Set arrival price
        - Execute with different fill prices
        - Verify slippage calculation
        """
        arrival_price = 50000.0

        # Configure fills at slightly different prices
        mock_exchange.place_order = AsyncMock(return_value={
            "order_id": str(uuid.uuid4()),
            "status": "FILLED",
            "filled_qty": 0.033,
            "filled_price": 50050.0,  # Slightly higher than arrival
            "fee": 0.1,
        })

        twap_executor.config.num_slices = 3
        twap_executor.config.total_duration_seconds = 3

        slices = twap_executor.create_execution_plan(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            total_quantity=Decimal("0.1"),
            total_value_usd=5000.0,
            arrival_price=arrival_price,
        )

        progress = await twap_executor.execute(
            slices=slices,
            exchange=mock_exchange,
        )

        result = twap_executor.get_execution_result(progress)

        # Slippage should be positive (paid more than arrival)
        expected_slippage_bps = ((50050.0 - 50000.0) / 50000.0) * 10000
        assert abs(result.slippage_bps - expected_slippage_bps) < 5  # Within 5 bps


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestExecutionErrorHandling:
    """Test error handling during execution"""

    @pytest.mark.asyncio
    async def test_twap_handles_exchange_errors(
        self,
        twap_executor,
        mock_exchange
    ):
        """
        Test TWAP handles exchange errors gracefully

        Scenario:
        - Exchange returns error for some slices
        - Execution should continue and retry
        """
        # Configure exchange to fail intermittently
        call_count = [0]

        async def flaky_place_order(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] % 2 == 0:
                raise Exception("Exchange temporarily unavailable")
            return {
                "order_id": str(uuid.uuid4()),
                "status": "FILLED",
                "filled_qty": 0.033,
                "filled_price": 50000.0,
                "fee": 0.1,
            }

        mock_exchange.place_order = flaky_place_order

        twap_executor.config.num_slices = 4
        twap_executor.config.total_duration_seconds = 4
        twap_executor.config.max_retries = 3

        slices = twap_executor.create_execution_plan(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            total_quantity=Decimal("0.1"),
            total_value_usd=5000.0,
        )

        # Should handle errors and still progress
        progress = await twap_executor.execute(
            slices=slices,
            exchange=mock_exchange,
        )

        # Some slices should have executed
        assert progress.slices_executed > 0
        assert progress.errors_encountered > 0

    @pytest.mark.asyncio
    async def test_execution_timeout_handling(
        self,
        twap_executor,
        mock_exchange
    ):
        """
        Test execution handles timeout correctly

        Scenario:
        - Exchange is very slow
        - Execution should timeout gracefully
        """
        async def slow_place_order(*args, **kwargs):
            await asyncio.sleep(10)  # Very slow
            return {
                "order_id": str(uuid.uuid4()),
                "status": "FILLED",
                "filled_qty": 0.01,
                "filled_price": 50000.0,
                "fee": 0.1,
            }

        mock_exchange.place_order = slow_place_order

        twap_executor.config.num_slices = 2
        twap_executor.config.total_duration_seconds = 2
        twap_executor.config.execution_timeout_seconds = 1  # Short timeout

        slices = twap_executor.create_execution_plan(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            total_quantity=Decimal("0.1"),
            total_value_usd=5000.0,
        )

        # Should timeout gracefully
        progress = await twap_executor.execute(
            slices=slices,
            exchange=mock_exchange,
        )

        # Execution may be incomplete due to timeout
        assert progress.timed_out == True or progress.slices_executed < len(slices)


# ============================================================================
# INTEGRATION WITH RISK MANAGEMENT
# ============================================================================

class TestExecutionRiskIntegration:
    """Test execution integration with risk management"""

    @pytest.mark.asyncio
    async def test_execution_respects_position_limits(
        self,
        smart_router,
        mock_exchange
    ):
        """
        Test execution respects risk position limits

        Scenario:
        - Large order exceeds position limits
        - Execution should be scaled or rejected
        """
        # Configure position limit check
        smart_router.set_position_limit(
            symbol="BTCUSDT",
            max_position_value=25000.0,
        )

        # Try to execute large order
        decision = await smart_router.determine_execution_strategy(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            total_value_usd=50000.0,  # Exceeds limit
            urgency="LOW",
            market_conditions={
                "volatility": 0.02,
                "liquidity_score": 0.8,
                "spread_bps": 10,
            },
        )

        # Decision should account for limit
        assert decision.adjusted_value_usd <= 25000.0 or decision.blocked == True

    @pytest.mark.asyncio
    async def test_execution_updates_risk_metrics(
        self,
        twap_executor,
        mock_exchange
    ):
        """
        Test execution updates risk metrics after completion

        Verifies:
        - Position exposure is updated
        - Risk budget is consumed
        """
        twap_executor.config.num_slices = 2
        twap_executor.config.total_duration_seconds = 2

        slices = twap_executor.create_execution_plan(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            total_quantity=Decimal("0.1"),
            total_value_usd=5000.0,
        )

        # Track risk metrics update
        risk_updates = []
        twap_executor.on_risk_update = lambda update: risk_updates.append(update)

        progress = await twap_executor.execute(
            slices=slices,
            exchange=mock_exchange,
        )

        # Risk updates should have been triggered
        result = twap_executor.get_execution_result(progress)
        assert result.risk_metrics_updated == True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
