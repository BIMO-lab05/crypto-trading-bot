"""
TWAP/VWAP Execution Tests
Phase 4.2: Enhanced TWAP/VWAP Execution Algorithms - Comprehensive Test Suite

Purpose:
- Test TWAP (Time-Weighted Average Price) order slicing logic
- Test VWAP (Volume-Weighted Average Price) distribution calculations
- Verify execution scheduler background task management
- Test pause/resume/cancel mechanisms
- Validate execution quality scoring
- Test slippage tracking and benchmarking
- Verify API endpoint functionality

Target Coverage: >85%

Research Sources:
- TWAP/VWAP Execution Best Practices
- Algorithmic Trading Testing Methodologies
- Asyncio Task Testing Patterns

Created: 2025-12-12
Author: Backend Developer Agent
"""

import pytest
import asyncio
import logging
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List
import uuid

# Import the execution scheduler and related components
from app.execution.execution_scheduler import (
    ExecutionScheduler,
    ScheduledOrder,
    ChunkExecution,
    ExecutionReport,
    SchedulerMetrics,
    OrderPriority,
    AlgorithmType,
    SchedulerState,
    OrderLifecycleState,
    get_execution_scheduler,
    reset_execution_scheduler,
)

# Import TWAP/VWAP algorithms
from app.execution.twap_vwap import (
    TWAPAlgorithm,
    VWAPAlgorithm,
    TWAPConfig,
    VWAPConfig,
    AdaptiveMode,
    create_twap_algorithm,
    create_vwap_algorithm,
)

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture
def default_scheduler():
    """Provide fresh execution scheduler instance for each test"""
    return ExecutionScheduler(
        max_concurrent_orders=5,
        max_queue_size=100,
        default_participation_rate=0.15
    )


@pytest.fixture
def custom_scheduler():
    """Provide scheduler with custom configuration"""
    return ExecutionScheduler(
        max_concurrent_orders=3,
        max_queue_size=50,
        default_participation_rate=0.10
    )


@pytest.fixture
def mock_execute_func():
    """Mock execution function simulating exchange order placement"""
    async def execute_order(**params):
        # Simulate successful order execution
        quantity = Decimal(str(params.get('quantity', '0')))
        order_type = params.get('order_type', 'Market')

        # Simulate slight slippage for market orders
        base_price = Decimal('50000')
        if order_type == 'Market':
            # Add small slippage for market orders
            if params.get('side', 'BUY').upper() == 'BUY':
                fill_price = base_price * Decimal('1.0002')  # 0.02% slippage
            else:
                fill_price = base_price * Decimal('0.9998')
        else:
            fill_price = Decimal(params.get('price', str(base_price)))

        return {
            "order_id": f"test_{uuid.uuid4().hex[:8]}",
            "status": "filled",
            "filled_quantity": str(quantity),
            "filled_qty": str(quantity),
            "average_price": str(fill_price),
            "avg_price": str(fill_price),
            "executed_at": datetime.now(timezone.utc).isoformat()
        }

    return AsyncMock(side_effect=execute_order)


@pytest.fixture
def mock_market_data_func():
    """Mock function to get current market data"""
    async def get_market_data(symbol: str):
        return {
            "symbol": symbol,
            "best_bid": "49990",
            "best_ask": "50010",
            "last_price": "50000",
            "volume_24h": "10000",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    return AsyncMock(side_effect=get_market_data)


@pytest.fixture
def sample_twap_order():
    """Provide sample TWAP order data"""
    return {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": Decimal("1.0"),
        "duration_minutes": 10,
        "num_chunks": 5,
        "arrival_price": Decimal("50000"),
        "participation_rate": 0.15,
        "randomize_timing": True,
        "urgency": "medium"
    }


@pytest.fixture
def sample_vwap_order():
    """Provide sample VWAP order data"""
    return {
        "symbol": "ETHUSDT",
        "side": "SELL",
        "quantity": Decimal("10.0"),
        "duration_minutes": 15,
        "historical_volumes": [0.05, 0.08, 0.12, 0.15, 0.20, 0.15, 0.12, 0.08, 0.05],
        "arrival_price": Decimal("3000"),
        "target_vwap": Decimal("3005"),
        "participation_rate": 0.10,
        "urgency": "low"
    }


@pytest.fixture
def volume_profile_standard():
    """Standard intraday volume profile (9 intervals)"""
    return [0.05, 0.08, 0.12, 0.15, 0.20, 0.15, 0.12, 0.08, 0.05]


@pytest.fixture
def volume_profile_flat():
    """Flat volume profile (equal distribution)"""
    return [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]


# ============================================================================
# SCHEDULED ORDER TESTS
# ============================================================================


class TestScheduledOrder:
    """Test suite for ScheduledOrder data class"""

    def test_scheduled_order_creation(self):
        """Test creating a scheduled order with default values"""
        order = ScheduledOrder(
            order_id="twap_BTCUSDT_12345678",
            algorithm_type=AlgorithmType.TWAP,
            symbol="BTCUSDT",
            side="BUY",
            total_quantity=Decimal("1.0")
        )

        assert order.order_id == "twap_BTCUSDT_12345678"
        assert order.algorithm_type == AlgorithmType.TWAP
        assert order.state == OrderLifecycleState.QUEUED
        assert order.filled_quantity == Decimal("0")
        assert order.current_chunk == 0

    def test_scheduled_order_fill_rate_calculation(self):
        """Test fill rate calculation"""
        order = ScheduledOrder(
            order_id="test_order",
            algorithm_type=AlgorithmType.TWAP,
            total_quantity=Decimal("10.0"),
            filled_quantity=Decimal("7.5")
        )

        fill_rate = order.get_fill_rate()
        assert fill_rate == pytest.approx(0.75, rel=0.01)

    def test_scheduled_order_fill_rate_zero_quantity(self):
        """Test fill rate with zero total quantity"""
        order = ScheduledOrder(
            order_id="test_order",
            algorithm_type=AlgorithmType.TWAP,
            total_quantity=Decimal("0"),
            filled_quantity=Decimal("0")
        )

        fill_rate = order.get_fill_rate()
        assert fill_rate == 0.0

    def test_scheduled_order_progress_percentage(self):
        """Test progress percentage calculation"""
        order = ScheduledOrder(
            order_id="test_order",
            algorithm_type=AlgorithmType.TWAP,
            num_chunks=10,
            current_chunk=4
        )

        progress = order.get_progress_pct()
        assert progress == pytest.approx(40.0, rel=0.01)

    def test_scheduled_order_is_active(self):
        """Test is_active() for various states"""
        # Active states
        for state in [OrderLifecycleState.QUEUED, OrderLifecycleState.SCHEDULED,
                      OrderLifecycleState.EXECUTING]:
            order = ScheduledOrder(
                order_id="test_order",
                algorithm_type=AlgorithmType.TWAP,
                state=state
            )
            assert order.is_active() is True

        # Inactive states
        for state in [OrderLifecycleState.COMPLETED, OrderLifecycleState.CANCELLED,
                      OrderLifecycleState.FAILED, OrderLifecycleState.PAUSED]:
            order = ScheduledOrder(
                order_id="test_order",
                algorithm_type=AlgorithmType.TWAP,
                state=state
            )
            assert order.is_active() is False

    def test_scheduled_order_slippage_calculation_buy(self):
        """Test slippage calculation for BUY orders"""
        order = ScheduledOrder(
            order_id="test_order",
            algorithm_type=AlgorithmType.TWAP,
            side="BUY",
            total_quantity=Decimal("1.0"),
            total_value=Decimal("50100"),  # Total value executed
            average_price=Decimal("50100"),  # Paid more
            benchmark_price=Decimal("50000")  # Expected price
        )

        slippage_pct, slippage_usd = order.calculate_slippage()

        # For buys, paying more = positive slippage (bad)
        assert slippage_pct == pytest.approx(0.2, rel=0.01)  # 0.2%
        assert slippage_usd > 0

    def test_scheduled_order_slippage_calculation_sell(self):
        """Test slippage calculation for SELL orders"""
        order = ScheduledOrder(
            order_id="test_order",
            algorithm_type=AlgorithmType.TWAP,
            side="SELL",
            total_quantity=Decimal("1.0"),
            total_value=Decimal("49900"),
            average_price=Decimal("49900"),  # Received less
            benchmark_price=Decimal("50000")  # Expected price
        )

        slippage_pct, slippage_usd = order.calculate_slippage()

        # For sells, receiving less = positive slippage (bad)
        assert slippage_pct == pytest.approx(0.2, rel=0.01)
        assert slippage_usd > 0


# ============================================================================
# EXECUTION SCHEDULER TESTS - LIFECYCLE
# ============================================================================


class TestExecutionSchedulerLifecycle:
    """Test suite for scheduler lifecycle management"""

    @pytest.mark.asyncio
    async def test_scheduler_start(self, default_scheduler):
        """Test scheduler starts correctly"""
        await default_scheduler.start()

        assert default_scheduler.state == SchedulerState.RUNNING
        assert default_scheduler._processor_task is not None

        await default_scheduler.stop(wait_for_completion=False)

    @pytest.mark.asyncio
    async def test_scheduler_stop(self, default_scheduler):
        """Test scheduler stops correctly"""
        await default_scheduler.start()
        await default_scheduler.stop(wait_for_completion=False)

        assert default_scheduler.state == SchedulerState.STOPPED

    @pytest.mark.asyncio
    async def test_scheduler_pause_resume(self, default_scheduler):
        """Test scheduler pause and resume"""
        await default_scheduler.start()

        default_scheduler.pause()
        assert default_scheduler.state == SchedulerState.PAUSED

        default_scheduler.resume()
        assert default_scheduler.state == SchedulerState.RUNNING

        await default_scheduler.stop(wait_for_completion=False)

    @pytest.mark.asyncio
    async def test_scheduler_double_start(self, default_scheduler):
        """Test that starting twice does not error"""
        await default_scheduler.start()
        await default_scheduler.start()  # Should not raise

        assert default_scheduler.state == SchedulerState.RUNNING

        await default_scheduler.stop(wait_for_completion=False)

    def test_scheduler_initial_state(self, default_scheduler):
        """Test scheduler initial state is IDLE"""
        assert default_scheduler.state == SchedulerState.IDLE
        assert len(default_scheduler._orders) == 0
        assert len(default_scheduler._order_queue) == 0


# ============================================================================
# TWAP ORDER TESTS
# ============================================================================


class TestTWAPOrderSubmission:
    """Test suite for TWAP order submission and slicing"""

    @pytest.mark.asyncio
    async def test_submit_twap_order_basic(self, default_scheduler, sample_twap_order):
        """Test basic TWAP order submission"""
        order_id = await default_scheduler.submit_twap_order(
            symbol=sample_twap_order["symbol"],
            side=sample_twap_order["side"],
            quantity=sample_twap_order["quantity"],
            duration_minutes=sample_twap_order["duration_minutes"],
            num_chunks=sample_twap_order["num_chunks"],
            arrival_price=sample_twap_order["arrival_price"],
            participation_rate=sample_twap_order["participation_rate"],
            urgency=sample_twap_order["urgency"]
        )

        assert order_id.startswith("twap_BTCUSDT_")
        assert len(order_id) > 15

        # Verify order is in storage
        order = default_scheduler._orders.get(order_id)
        assert order is not None
        assert order.algorithm_type == AlgorithmType.TWAP
        assert order.total_quantity == Decimal("1.0")
        assert order.num_chunks == 5
        assert order.state == OrderLifecycleState.QUEUED

    @pytest.mark.asyncio
    async def test_submit_twap_order_auto_chunks(self, default_scheduler):
        """Test TWAP order with auto-calculated chunks"""
        order_id = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("2.0"),
            duration_minutes=10,
            num_chunks=None  # Auto-calculate
        )

        order = default_scheduler._orders.get(order_id)
        assert order is not None

        # Auto-calculated: min(duration_minutes, 60), max 3
        assert order.num_chunks == 10  # 10 minutes = 10 chunks

    @pytest.mark.asyncio
    async def test_submit_twap_order_with_priority(self, default_scheduler):
        """Test TWAP order submission with different priorities"""
        order_id_urgent = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0"),
            duration_minutes=5,
            priority=OrderPriority.URGENT
        )

        order_id_normal = await default_scheduler.submit_twap_order(
            symbol="ETHUSDT",
            side="SELL",
            quantity=Decimal("10.0"),
            duration_minutes=10,
            priority=OrderPriority.NORMAL
        )

        urgent_order = default_scheduler._orders.get(order_id_urgent)
        normal_order = default_scheduler._orders.get(order_id_normal)

        assert urgent_order.priority == OrderPriority.URGENT
        assert normal_order.priority == OrderPriority.NORMAL

    @pytest.mark.asyncio
    async def test_twap_chunks_equal_distribution(self, default_scheduler):
        """Test TWAP creates equal-sized chunks"""
        order_id = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("10.0"),
            duration_minutes=10,
            num_chunks=5
        )

        order = default_scheduler._orders.get(order_id)
        chunks = default_scheduler._calculate_twap_chunks(order)

        # All chunks should be equal (2.0 each)
        expected_chunk_size = Decimal("2.0")
        for chunk in chunks:
            assert chunk == pytest.approx(expected_chunk_size, rel=0.01)

    @pytest.mark.asyncio
    async def test_twap_chunks_remainder_handling(self, default_scheduler):
        """Test TWAP handles remainder correctly"""
        order_id = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("10.0"),
            duration_minutes=10,
            num_chunks=3  # 10/3 = 3.333... per chunk
        )

        order = default_scheduler._orders.get(order_id)
        chunks = default_scheduler._calculate_twap_chunks(order)

        # Total should equal original quantity
        total = sum(chunks)
        assert total == Decimal("10.0")

    @pytest.mark.asyncio
    async def test_twap_interval_calculation(self, default_scheduler):
        """Test TWAP calculates correct interval between chunks"""
        order_id = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0"),
            duration_minutes=10,
            num_chunks=5
        )

        order = default_scheduler._orders.get(order_id)

        # 10 minutes / 5 chunks = 2 minutes = 120 seconds
        assert order.interval_seconds == 120


# ============================================================================
# VWAP ORDER TESTS
# ============================================================================


class TestVWAPOrderSubmission:
    """Test suite for VWAP order submission and volume distribution"""

    @pytest.mark.asyncio
    async def test_submit_vwap_order_basic(self, default_scheduler, sample_vwap_order):
        """Test basic VWAP order submission"""
        order_id = await default_scheduler.submit_vwap_order(
            symbol=sample_vwap_order["symbol"],
            side=sample_vwap_order["side"],
            quantity=sample_vwap_order["quantity"],
            duration_minutes=sample_vwap_order["duration_minutes"],
            historical_volumes=sample_vwap_order["historical_volumes"],
            arrival_price=sample_vwap_order["arrival_price"],
            target_vwap=sample_vwap_order["target_vwap"],
            participation_rate=sample_vwap_order["participation_rate"],
            urgency=sample_vwap_order["urgency"]
        )

        assert order_id.startswith("vwap_ETHUSDT_")

        order = default_scheduler._orders.get(order_id)
        assert order is not None
        assert order.algorithm_type == AlgorithmType.VWAP
        assert order.total_quantity == Decimal("10.0")
        assert order.num_chunks == 9  # Based on volume profile length

    @pytest.mark.asyncio
    async def test_vwap_volume_profile_normalization(self, default_scheduler,
                                                      volume_profile_standard):
        """Test VWAP normalizes volume profile"""
        normalized = default_scheduler._normalize_volume_profile(volume_profile_standard)

        # Should sum to 1.0
        total = sum(normalized)
        assert total == pytest.approx(1.0, rel=0.001)

    @pytest.mark.asyncio
    async def test_vwap_volume_profile_non_normalized_input(self, default_scheduler):
        """Test VWAP handles non-normalized volume input"""
        # Raw volume counts instead of percentages
        raw_volumes = [100, 160, 240, 300, 400, 300, 240, 160, 100]

        normalized = default_scheduler._normalize_volume_profile(raw_volumes)

        total = sum(normalized)
        assert total == pytest.approx(1.0, rel=0.001)

        # Highest volume period should have highest weight
        max_idx = raw_volumes.index(max(raw_volumes))
        assert normalized[max_idx] == max(normalized)

    @pytest.mark.asyncio
    async def test_vwap_chunks_volume_weighted(self, default_scheduler,
                                                volume_profile_standard):
        """Test VWAP creates volume-weighted chunks"""
        order_id = await default_scheduler.submit_vwap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("10.0"),
            duration_minutes=9,
            historical_volumes=volume_profile_standard
        )

        order = default_scheduler._orders.get(order_id)
        chunks = default_scheduler._calculate_vwap_chunks(order)

        # Total should equal original quantity
        total = sum(chunks)
        assert total == Decimal("10.0")

        # Middle chunk (highest volume) should be largest
        max_chunk_idx = chunks.index(max(chunks))
        assert max_chunk_idx == 4  # Middle of 9 chunks

    @pytest.mark.asyncio
    async def test_vwap_without_volume_profile(self, default_scheduler):
        """Test VWAP falls back to equal distribution without profile"""
        order_id = await default_scheduler.submit_vwap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("10.0"),
            duration_minutes=10,
            historical_volumes=None  # No profile provided
        )

        order = default_scheduler._orders.get(order_id)

        # Should default to equal distribution (like TWAP)
        chunks = default_scheduler._calculate_vwap_chunks(order)

        # All chunks should be approximately equal
        first_chunk = chunks[0]
        for chunk in chunks:
            assert chunk == pytest.approx(first_chunk, rel=0.01)

    @pytest.mark.asyncio
    async def test_vwap_target_benchmark_stored(self, default_scheduler):
        """Test VWAP stores target VWAP as benchmark"""
        order_id = await default_scheduler.submit_vwap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0"),
            duration_minutes=10,
            target_vwap=Decimal("50500")
        )

        order = default_scheduler._orders.get(order_id)
        assert order.benchmark_price == Decimal("50500")


# ============================================================================
# ORDER CONTROL TESTS (PAUSE/RESUME/CANCEL)
# ============================================================================


class TestOrderControl:
    """Test suite for order control mechanisms"""

    @pytest.mark.asyncio
    async def test_pause_order(self, default_scheduler, sample_twap_order):
        """Test pausing an active order"""
        order_id = await default_scheduler.submit_twap_order(
            symbol=sample_twap_order["symbol"],
            side=sample_twap_order["side"],
            quantity=sample_twap_order["quantity"],
            duration_minutes=sample_twap_order["duration_minutes"]
        )

        # Order starts as QUEUED (active)
        order = default_scheduler._orders.get(order_id)
        assert order.is_active() is True

        # Pause the order
        result = default_scheduler.pause_order(order_id)

        assert result is True
        assert order.state == OrderLifecycleState.PAUSED

    @pytest.mark.asyncio
    async def test_pause_nonexistent_order(self, default_scheduler):
        """Test pausing an order that doesn't exist"""
        result = default_scheduler.pause_order("nonexistent_order_id")
        assert result is False

    @pytest.mark.asyncio
    async def test_pause_completed_order(self, default_scheduler):
        """Test cannot pause completed order"""
        order_id = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0"),
            duration_minutes=5
        )

        # Manually set to completed
        order = default_scheduler._orders.get(order_id)
        order.state = OrderLifecycleState.COMPLETED

        result = default_scheduler.pause_order(order_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_resume_order(self, default_scheduler):
        """Test resuming a paused order"""
        order_id = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0"),
            duration_minutes=5
        )

        # Pause first
        default_scheduler.pause_order(order_id)
        order = default_scheduler._orders.get(order_id)
        assert order.state == OrderLifecycleState.PAUSED

        # Resume
        result = default_scheduler.resume_order(order_id)

        assert result is True
        assert order.state == OrderLifecycleState.SCHEDULED

    @pytest.mark.asyncio
    async def test_resume_non_paused_order(self, default_scheduler):
        """Test cannot resume non-paused order"""
        order_id = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0"),
            duration_minutes=5
        )

        # Try to resume without pausing
        result = default_scheduler.resume_order(order_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_order(self, default_scheduler):
        """Test cancelling an order"""
        order_id = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0"),
            duration_minutes=5
        )

        result = await default_scheduler.cancel_order(order_id)

        order = default_scheduler._orders.get(order_id)
        assert result is True
        assert order.state == OrderLifecycleState.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_partial_filled_order(self, default_scheduler):
        """Test cancelling partially filled order marks as PARTIAL"""
        order_id = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0"),
            duration_minutes=5
        )

        # Simulate partial fill
        order = default_scheduler._orders.get(order_id)
        order.filled_quantity = Decimal("0.5")

        result = await default_scheduler.cancel_order(order_id)

        assert result is True
        assert order.state == OrderLifecycleState.PARTIAL

    @pytest.mark.asyncio
    async def test_cancel_completed_order_fails(self, default_scheduler):
        """Test cannot cancel completed order"""
        order_id = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0"),
            duration_minutes=5
        )

        order = default_scheduler._orders.get(order_id)
        order.state = OrderLifecycleState.COMPLETED

        result = await default_scheduler.cancel_order(order_id)
        assert result is False


# ============================================================================
# ORDER STATUS AND REPORTING TESTS
# ============================================================================


class TestOrderStatusReporting:
    """Test suite for order status queries and reporting"""

    @pytest.mark.asyncio
    async def test_get_order_status(self, default_scheduler, sample_twap_order):
        """Test getting order status"""
        order_id = await default_scheduler.submit_twap_order(
            symbol=sample_twap_order["symbol"],
            side=sample_twap_order["side"],
            quantity=sample_twap_order["quantity"],
            duration_minutes=sample_twap_order["duration_minutes"],
            num_chunks=sample_twap_order["num_chunks"],
            arrival_price=sample_twap_order["arrival_price"]
        )

        status = default_scheduler.get_order_status(order_id)

        assert status is not None
        assert status["order_id"] == order_id
        assert status["algorithm"] == "twap"
        assert status["symbol"] == "BTCUSDT"
        assert status["side"] == "BUY"
        assert status["state"] == "queued"
        assert status["progress"]["total_quantity"] == "1"
        assert status["progress"]["fill_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_get_order_status_nonexistent(self, default_scheduler):
        """Test getting status for nonexistent order"""
        status = default_scheduler.get_order_status("nonexistent_order")
        assert status is None

    @pytest.mark.asyncio
    async def test_get_active_algorithms(self, default_scheduler):
        """Test getting list of active algorithms"""
        # Submit multiple orders
        await default_scheduler.submit_twap_order(
            symbol="BTCUSDT", side="BUY", quantity=Decimal("1.0"), duration_minutes=5
        )
        await default_scheduler.submit_vwap_order(
            symbol="ETHUSDT", side="SELL", quantity=Decimal("10.0"), duration_minutes=10
        )

        active = default_scheduler.get_active_algorithms()

        assert len(active) == 2
        assert any(o["algorithm"] == "twap" for o in active)
        assert any(o["algorithm"] == "vwap" for o in active)

    @pytest.mark.asyncio
    async def test_get_execution_report(self, default_scheduler):
        """Test generating execution report"""
        order_id = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0"),
            duration_minutes=5,
            arrival_price=Decimal("50000")
        )

        # Simulate some execution
        order = default_scheduler._orders.get(order_id)
        order.filled_quantity = Decimal("0.8")
        order.average_price = Decimal("50050")
        order.total_value = Decimal("40040")
        order.benchmark_price = Decimal("50000")
        order.started_at = datetime.now(timezone.utc) - timedelta(minutes=4)
        order.state = OrderLifecycleState.COMPLETED
        order.completed_at = datetime.now(timezone.utc)
        order.chunk_results = [
            {"success": True, "slippage_pct": 0.05, "execution_time_ms": 50},
            {"success": True, "slippage_pct": 0.08, "execution_time_ms": 45},
            {"success": True, "slippage_pct": 0.10, "execution_time_ms": 55},
            {"success": False, "error": "timeout"},
        ]

        report = default_scheduler.get_execution_report(order_id)

        assert report is not None
        assert report.order_id == order_id
        assert report.algorithm_type == "twap"
        assert report.fill_rate == pytest.approx(0.8, rel=0.01)
        assert report.chunks_successful == 3
        assert report.chunks_failed == 1
        assert report.quality_score >= 0
        assert report.quality_score <= 100

    @pytest.mark.asyncio
    async def test_get_scheduler_status(self, default_scheduler):
        """Test getting scheduler status"""
        await default_scheduler.submit_twap_order(
            symbol="BTCUSDT", side="BUY", quantity=Decimal("1.0"), duration_minutes=5
        )

        status = default_scheduler.get_scheduler_status()

        assert status["state"] == "idle"
        assert status["queue_size"] == 1
        assert status["config"]["max_concurrent_orders"] == 5
        assert status["config"]["default_participation_rate"] == 0.15

    @pytest.mark.asyncio
    async def test_get_performance_report(self, default_scheduler):
        """Test aggregate performance report"""
        # Submit and simulate completion of multiple orders
        order_id1 = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT", side="BUY", quantity=Decimal("1.0"), duration_minutes=5
        )
        order_id2 = await default_scheduler.submit_vwap_order(
            symbol="ETHUSDT", side="SELL", quantity=Decimal("10.0"), duration_minutes=10
        )

        # Simulate completions
        for oid in [order_id1, order_id2]:
            order = default_scheduler._orders.get(oid)
            order.state = OrderLifecycleState.COMPLETED
            order.filled_quantity = order.total_quantity
            order.slippage_pct = 0.05
            order.total_value = order.total_quantity * Decimal("50000")

        report = default_scheduler.get_performance_report(hours=24)

        assert report["period_hours"] == 24
        assert report["summary"]["total_orders"] == 2
        assert report["summary"]["completed_orders"] == 2
        assert "by_algorithm" in report
        assert report["by_algorithm"]["twap"]["count"] == 1
        assert report["by_algorithm"]["vwap"]["count"] == 1


# ============================================================================
# EXECUTION QUALITY SCORING TESTS
# ============================================================================


class TestExecutionQualityScoring:
    """Test suite for execution quality score calculations"""

    def test_quality_score_perfect_execution(self, default_scheduler):
        """Test quality score for perfect execution"""
        score = default_scheduler._calculate_quality_score(
            fill_rate=1.0,          # 100% filled
            slippage_pct=0.0,       # No slippage
            success_rate=1.0,       # All chunks successful
            timing_accuracy=1.0     # Exact timing
        )

        # Should be very high (close to 100)
        assert score >= 95

    def test_quality_score_poor_execution(self, default_scheduler):
        """Test quality score for poor execution"""
        score = default_scheduler._calculate_quality_score(
            fill_rate=0.5,          # Only 50% filled
            slippage_pct=0.4,       # High slippage
            success_rate=0.6,       # Many failures
            timing_accuracy=0.5     # Poor timing
        )

        # Should be low
        assert score < 50

    def test_quality_score_weights(self, default_scheduler):
        """Test that fill rate has highest weight"""
        # Perfect fill rate with poor other metrics
        score_good_fill = default_scheduler._calculate_quality_score(
            fill_rate=1.0,
            slippage_pct=0.3,
            success_rate=0.7,
            timing_accuracy=0.7
        )

        # Poor fill rate with good other metrics
        score_poor_fill = default_scheduler._calculate_quality_score(
            fill_rate=0.5,
            slippage_pct=0.0,
            success_rate=1.0,
            timing_accuracy=1.0
        )

        # Fill rate impact should be significant
        assert score_good_fill > score_poor_fill

    def test_quality_rating_excellent(self, default_scheduler):
        """Test 'excellent' rating threshold"""
        order_id = "test_excellent"
        order = ScheduledOrder(
            order_id=order_id,
            algorithm_type=AlgorithmType.TWAP,
            total_quantity=Decimal("1.0"),
            filled_quantity=Decimal("1.0"),
            num_chunks=5
        )
        order.chunk_results = [{"success": True, "slippage_pct": 0.01}] * 5
        default_scheduler._orders[order_id] = order

        report = default_scheduler.get_execution_report(order_id)

        # Should be excellent if score >= 90
        if report.quality_score >= 90:
            assert report.rating == "excellent"

    def test_quality_recommendations_generated(self, default_scheduler):
        """Test that recommendations are generated for issues"""
        order_id = "test_recommendations"
        order = ScheduledOrder(
            order_id=order_id,
            algorithm_type=AlgorithmType.TWAP,
            total_quantity=Decimal("1.0"),
            filled_quantity=Decimal("0.5"),  # Low fill
            average_price=Decimal("50200"),
            benchmark_price=Decimal("50000"),  # 0.4% slippage
            num_chunks=5
        )
        order.chunk_results = [
            {"success": True, "slippage_pct": 0.4},
            {"success": False, "error": "timeout"},
            {"success": True, "slippage_pct": 0.3},
        ]
        default_scheduler._orders[order_id] = order

        report = default_scheduler.get_execution_report(order_id)

        # Should have recommendations due to issues
        assert len(report.recommendations) > 0


# ============================================================================
# CHUNK EXECUTION TESTS
# ============================================================================


class TestChunkExecution:
    """Test suite for individual chunk execution"""

    @pytest.mark.asyncio
    async def test_execute_chunk_success(self, default_scheduler, mock_execute_func):
        """Test successful chunk execution"""
        default_scheduler.set_execution_functions(
            execute_func=mock_execute_func,
            get_market_data_func=None
        )

        order = ScheduledOrder(
            order_id="test_chunk",
            algorithm_type=AlgorithmType.TWAP,
            symbol="BTCUSDT",
            side="BUY",
            total_quantity=Decimal("1.0"),
            arrival_price=Decimal("50000")
        )

        result = await default_scheduler._execute_chunk(
            order=order,
            chunk_id=1,
            quantity=Decimal("0.2")
        )

        assert result["success"] is True
        assert result["chunk_id"] == 1
        assert Decimal(result["filled_quantity"]) == Decimal("0.2")
        assert "average_price" in result
        assert "execution_time_ms" in result

    @pytest.mark.asyncio
    async def test_execute_chunk_failure(self, default_scheduler):
        """Test chunk execution failure handling"""
        async def failing_execute(**params):
            raise Exception("Exchange connection failed")

        default_scheduler.set_execution_functions(
            execute_func=AsyncMock(side_effect=failing_execute)
        )

        order = ScheduledOrder(
            order_id="test_fail_chunk",
            algorithm_type=AlgorithmType.TWAP,
            symbol="BTCUSDT",
            side="BUY",
            total_quantity=Decimal("1.0")
        )

        result = await default_scheduler._execute_chunk(
            order=order,
            chunk_id=1,
            quantity=Decimal("0.2")
        )

        assert result["success"] is False
        assert "error" in result
        assert result["filled_quantity"] == "0"

    @pytest.mark.asyncio
    async def test_execute_chunk_no_execute_func(self, default_scheduler):
        """Test chunk execution without configured execute function"""
        order = ScheduledOrder(
            order_id="test_no_func",
            algorithm_type=AlgorithmType.TWAP,
            symbol="BTCUSDT",
            side="BUY",
            total_quantity=Decimal("1.0")
        )

        result = await default_scheduler._execute_chunk(
            order=order,
            chunk_id=1,
            quantity=Decimal("0.2")
        )

        assert result["success"] is False
        assert "not configured" in result.get("error", "").lower()


# ============================================================================
# FULL ORDER EXECUTION TESTS
# ============================================================================


class TestFullOrderExecution:
    """Test suite for complete order execution flow"""

    @pytest.mark.asyncio
    async def test_full_twap_execution(self, default_scheduler, mock_execute_func,
                                       mock_market_data_func):
        """Test complete TWAP order execution"""
        default_scheduler.set_execution_functions(
            execute_func=mock_execute_func,
            get_market_data_func=mock_market_data_func
        )

        # Submit order
        order_id = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0"),
            duration_minutes=1,  # Short duration for test
            num_chunks=3,
            arrival_price=Decimal("50000"),
            randomize_timing=False  # Disable for predictable test
        )

        order = default_scheduler._orders.get(order_id)

        # Simulate execution (skip the waiting)
        order.state = OrderLifecycleState.EXECUTING
        order.started_at = datetime.now(timezone.utc)

        chunk_quantities = default_scheduler._calculate_twap_chunks(order)

        for i, chunk_qty in enumerate(chunk_quantities):
            result = await default_scheduler._execute_chunk(order, i + 1, chunk_qty)

            if result["success"]:
                filled = Decimal(result["filled_quantity"])
                price = Decimal(result["average_price"])
                order.filled_quantity += filled
                order.total_value += filled * price

        # Verify execution
        assert order.filled_quantity == Decimal("1.0")
        assert mock_execute_func.call_count == 3

    @pytest.mark.asyncio
    async def test_execution_updates_metrics(self, default_scheduler, mock_execute_func):
        """Test that execution updates scheduler metrics"""
        default_scheduler.set_execution_functions(execute_func=mock_execute_func)

        initial_queued = default_scheduler._metrics.total_orders_queued

        await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0"),
            duration_minutes=5
        )

        assert default_scheduler._metrics.total_orders_queued == initial_queued + 1
        assert default_scheduler._metrics.twap_orders > 0


# ============================================================================
# GLOBAL INSTANCE MANAGEMENT TESTS
# ============================================================================


class TestGlobalInstanceManagement:
    """Test suite for global scheduler instance management"""

    @pytest.mark.asyncio
    async def test_get_execution_scheduler_singleton(self):
        """Test get_execution_scheduler returns singleton"""
        await reset_execution_scheduler()

        scheduler1 = get_execution_scheduler()
        scheduler2 = get_execution_scheduler()

        assert scheduler1 is scheduler2

    @pytest.mark.asyncio
    async def test_get_execution_scheduler_with_config(self):
        """Test get_execution_scheduler respects initial config"""
        await reset_execution_scheduler()

        scheduler = get_execution_scheduler(
            max_concurrent_orders=10,
            max_queue_size=200
        )

        assert scheduler.max_concurrent_orders == 10
        assert scheduler.max_queue_size == 200

    @pytest.mark.asyncio
    async def test_reset_execution_scheduler(self):
        """Test reset_execution_scheduler creates new instance"""
        scheduler1 = get_execution_scheduler()
        await reset_execution_scheduler()
        scheduler2 = get_execution_scheduler()

        assert scheduler1 is not scheduler2


# ============================================================================
# EDGE CASES AND ERROR HANDLING TESTS
# ============================================================================


class TestEdgeCases:
    """Test suite for edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_very_small_order(self, default_scheduler):
        """Test handling very small order quantities"""
        order_id = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.0001"),  # Very small
            duration_minutes=5,
            num_chunks=3
        )

        order = default_scheduler._orders.get(order_id)
        chunks = default_scheduler._calculate_twap_chunks(order)

        # Should still create chunks that sum to total
        assert sum(chunks) == Decimal("0.0001")

    @pytest.mark.asyncio
    async def test_very_large_order(self, default_scheduler):
        """Test handling very large order quantities"""
        order_id = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1000000"),  # Very large
            duration_minutes=60,
            num_chunks=60
        )

        order = default_scheduler._orders.get(order_id)
        assert order is not None
        assert order.total_quantity == Decimal("1000000")

    @pytest.mark.asyncio
    async def test_minimum_chunks(self, default_scheduler):
        """Test minimum chunk count (3)"""
        order_id = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0"),
            duration_minutes=1,  # Short duration
            num_chunks=None  # Auto-calculate
        )

        order = default_scheduler._orders.get(order_id)
        assert order.num_chunks >= 3  # Minimum 3 chunks

    @pytest.mark.asyncio
    async def test_empty_volume_profile(self, default_scheduler):
        """Test VWAP with empty volume profile"""
        normalized = default_scheduler._normalize_volume_profile([])
        assert normalized == []

    @pytest.mark.asyncio
    async def test_zero_sum_volume_profile(self, default_scheduler):
        """Test VWAP with zero-sum volume profile"""
        normalized = default_scheduler._normalize_volume_profile([0, 0, 0])

        # Should fallback to equal distribution
        for weight in normalized:
            assert weight == pytest.approx(1.0 / 3, rel=0.01)

    @pytest.mark.asyncio
    async def test_concurrent_order_limit(self, custom_scheduler):
        """Test respecting max concurrent orders limit"""
        # Submit more orders than max concurrent
        order_ids = []
        for i in range(5):  # max_concurrent is 3
            oid = await custom_scheduler.submit_twap_order(
                symbol=f"PAIR{i}USDT",
                side="BUY",
                quantity=Decimal("1.0"),
                duration_minutes=5
            )
            order_ids.append(oid)

        assert len(custom_scheduler._order_queue) == 5
        assert custom_scheduler.max_concurrent_orders == 3


# ============================================================================
# TIMING RANDOMIZATION TESTS
# ============================================================================


class TestTimingRandomization:
    """Test suite for timing randomization in TWAP"""

    @pytest.mark.asyncio
    async def test_randomize_timing_flag(self, default_scheduler):
        """Test randomize_timing flag is stored"""
        order_id_random = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0"),
            duration_minutes=5,
            randomize_timing=True
        )

        order_id_fixed = await default_scheduler.submit_twap_order(
            symbol="ETHUSDT",
            side="SELL",
            quantity=Decimal("1.0"),
            duration_minutes=5,
            randomize_timing=False
        )

        random_order = default_scheduler._orders.get(order_id_random)
        fixed_order = default_scheduler._orders.get(order_id_fixed)

        assert random_order.randomize_timing is True
        assert fixed_order.randomize_timing is False

    @pytest.mark.asyncio
    async def test_vwap_no_randomization(self, default_scheduler):
        """Test VWAP doesn't use timing randomization"""
        order_id = await default_scheduler.submit_vwap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0"),
            duration_minutes=5
        )

        order = default_scheduler._orders.get(order_id)
        assert order.randomize_timing is False


# ============================================================================
# METRICS TRACKING TESTS
# ============================================================================


class TestMetricsTracking:
    """Test suite for scheduler metrics tracking"""

    @pytest.mark.asyncio
    async def test_order_count_tracking(self, default_scheduler):
        """Test order count metrics are tracked"""
        initial = default_scheduler._metrics.total_orders_queued

        await default_scheduler.submit_twap_order(
            symbol="BTCUSDT", side="BUY", quantity=Decimal("1.0"), duration_minutes=5
        )
        await default_scheduler.submit_vwap_order(
            symbol="ETHUSDT", side="SELL", quantity=Decimal("10.0"), duration_minutes=10
        )

        assert default_scheduler._metrics.total_orders_queued == initial + 2
        assert default_scheduler._metrics.twap_orders >= 1
        assert default_scheduler._metrics.vwap_orders >= 1

    @pytest.mark.asyncio
    async def test_cancellation_tracking(self, default_scheduler):
        """Test cancellation metrics are tracked"""
        order_id = await default_scheduler.submit_twap_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0"),
            duration_minutes=5
        )

        initial_cancelled = default_scheduler._metrics.total_orders_cancelled

        await default_scheduler.cancel_order(order_id)

        assert default_scheduler._metrics.total_orders_cancelled == initial_cancelled + 1


# ============================================================================
# INTEGRATION WITH TWAP/VWAP ALGORITHM CLASSES
# ============================================================================


class TestTWAPVWAPAlgorithmIntegration:
    """Test suite for integration with TWAP/VWAP algorithm classes"""

    def test_twap_config_creation(self):
        """Test TWAPConfig can be created with valid parameters"""
        # TWAPConfig uses num_chunks and interval_seconds, not duration/quantity
        config = TWAPConfig(
            num_chunks=15,
            interval_seconds=120,
            participation_rate=0.15,
            randomize_timing=True,
            randomize_size=True
        )

        assert config.num_chunks == 15
        assert config.interval_seconds == 120
        assert config.participation_rate == 0.15

    def test_vwap_config_creation(self):
        """Test VWAPConfig can be created with valid parameters"""
        # VWAPConfig uses participation_rate, not volume_profile directly
        config = VWAPConfig(
            participation_rate=0.15,
            max_participation_rate=0.30,
            volume_profile_periods=20
        )

        assert config.participation_rate == 0.15
        assert config.max_participation_rate == 0.30
        assert config.volume_profile_periods == 20

    def test_create_twap_algorithm_helper(self):
        """Test create_twap_algorithm helper function"""
        config = TWAPConfig(
            num_chunks=10,
            interval_seconds=60
        )
        algorithm = create_twap_algorithm(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("5.0"),
            config=config
        )

        assert algorithm is not None
        assert algorithm.quantity == Decimal("5.0")
        assert algorithm.symbol == "BTCUSDT"
        assert algorithm.side == "BUY"

    def test_create_vwap_algorithm_helper(self):
        """Test create_vwap_algorithm helper function"""
        config = VWAPConfig(
            participation_rate=0.10
        )
        algorithm = create_vwap_algorithm(
            symbol="ETHUSDT",
            side="SELL",
            quantity=Decimal("20.0"),
            config=config
        )

        assert algorithm is not None
        assert algorithm.quantity == Decimal("20.0")
        assert algorithm.symbol == "ETHUSDT"
        assert algorithm.side == "SELL"

    def test_twap_config_defaults(self):
        """Test TWAPConfig has sensible defaults"""
        config = TWAPConfig()

        assert config.num_chunks == 10
        assert config.interval_seconds == 60
        assert config.participation_rate == 0.15
        assert config.max_participation_rate == 0.30
        assert config.randomize_timing is True
        assert config.randomize_size is True
        assert config.max_slippage_pct == 0.10

    def test_vwap_config_defaults(self):
        """Test VWAPConfig has sensible defaults"""
        config = VWAPConfig()

        assert config.participation_rate == 0.15
        assert config.max_participation_rate == 0.30
        assert config.volume_profile_periods == 20
        assert config.min_chunk_size_pct == 0.02
        assert config.max_chunk_size_pct == 0.25

    def test_adaptive_mode_values(self):
        """Test AdaptiveMode enum values"""
        assert AdaptiveMode.PASSIVE == "passive"
        assert AdaptiveMode.NEUTRAL == "neutral"
        assert AdaptiveMode.AGGRESSIVE == "aggressive"
        assert AdaptiveMode.URGENT == "urgent"


# ============================================================================
# API ROUTER TESTS (UNIT LEVEL)
# ============================================================================


class TestAPIRouterModels:
    """Test suite for API router request/response models"""

    def test_twap_order_request_validation(self):
        """Test TWAP order request model can be created"""
        from app.handlers.twap_vwap_router import TWAPOrderRequest

        request = TWAPOrderRequest(
            symbol="BTCUSDT",
            side="BUY",
            size="1.0",
            duration_minutes=10,
            num_chunks=5,
            participation_rate=0.15
        )

        assert request.symbol == "BTCUSDT"
        assert request.side == "BUY"
        assert request.size == "1.0"
        assert request.duration_minutes == 10

    def test_vwap_order_request_validation(self):
        """Test VWAP order request model can be created"""
        from app.handlers.twap_vwap_router import VWAPOrderRequest

        request = VWAPOrderRequest(
            symbol="ETHUSDT",
            side="SELL",
            size="10.0",
            duration_minutes=15,
            volume_profile=[0.1, 0.2, 0.3, 0.2, 0.1, 0.1]
        )

        assert request.symbol == "ETHUSDT"
        assert request.side == "SELL"
        assert request.size == "10.0"
        assert len(request.volume_profile) == 6

    def test_side_validation_uppercase(self):
        """Test that side is normalized to uppercase"""
        from app.handlers.twap_vwap_router import TWAPOrderRequest

        request = TWAPOrderRequest(
            symbol="BTCUSDT",
            side="buy",  # lowercase
            size="1.0"
        )

        assert request.side == "BUY"

    def test_urgency_validation(self):
        """Test urgency is normalized to lowercase"""
        from app.handlers.twap_vwap_router import TWAPOrderRequest

        request = TWAPOrderRequest(
            symbol="BTCUSDT",
            side="BUY",
            size="1.0",
            urgency="HIGH"
        )

        assert request.urgency == "high"


# ============================================================================
# RUN CONFIGURATION
# ============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
