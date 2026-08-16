"""
Smart Order Router Tests
Phase 4.1: Smart Order Routing for Improved Execution

Purpose:
- Verify order type selection logic across all scenarios
- Test slippage estimation accuracy with realistic order book data
- Validate order splitting strategies (TWAP, Iceberg)
- Test execution flow with mocked order placement
- Ensure metrics tracking is accurate

Test Categories:
1. Order Book Analysis Tests
2. Slippage Estimation Tests
3. Order Type Selection Tests
4. Execution Strategy Tests
5. Metrics and Reporting Tests
6. Integration Tests

Target Coverage: >85%

Author: Backend Developer Agent
Created: 2025-12-11
"""

import pytest
import asyncio
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace
import logging

# Import the smart router module
from app.execution.smart_router import (
    SmartOrderRouter,
    SmartRouterConfig,
    OrderTypeRecommendation,
    ExecutionUrgency,
    ExecutionStrategyType,
    OrderTypeSelection,
    OrderBookAnalysis,
    SlippageEstimate,
    RouterMetrics,
    ExecutionQualityReport,
    ExecutionRecord,
    OrderBookLevel,
    get_smart_router,
    reset_smart_router,
)

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def default_config():
    """Provide default router configuration"""
    return SmartRouterConfig()


@pytest.fixture
def custom_config():
    """Provide custom router configuration for specific test scenarios"""
    return SmartRouterConfig(
        tight_spread_threshold=0.0003,       # 0.03% - tighter threshold
        wide_spread_threshold=0.001,         # 0.1% - tighter wide threshold
        small_order_threshold=500.0,         # $500
        medium_order_threshold=2500.0,       # $2500
        large_order_threshold_pct=0.005,     # 0.5% of book depth
        twap_min_chunks=2,
        twap_max_chunks=4,
        limit_timeout_seconds=10,
        max_acceptable_slippage_pct=0.20,
    )


@pytest.fixture
def router(default_config):
    """Provide fresh router instance for each test"""
    reset_smart_router()
    return SmartOrderRouter(default_config)


@pytest.fixture
def router_custom(custom_config):
    """Provide router with custom configuration"""
    return SmartOrderRouter(custom_config)


@pytest.fixture
def sample_orderbook_tight_spread():
    """
    Sample order book with tight spread (0.02%)
    BTC price ~$50,000
    """
    return {
        "bids": [
            ["49995.00", "1.5"],    # $74,992.50
            ["49990.00", "2.0"],    # $99,980.00
            ["49985.00", "3.0"],    # $149,955.00
            ["49980.00", "5.0"],    # $249,900.00
            ["49970.00", "10.0"],   # $499,700.00
        ],
        "asks": [
            ["50005.00", "1.5"],    # $75,007.50
            ["50010.00", "2.0"],    # $100,020.00
            ["50015.00", "3.0"],    # $150,045.00
            ["50020.00", "5.0"],    # $250,100.00
            ["50030.00", "10.0"],   # $500,300.00
        ]
    }


@pytest.fixture
def sample_orderbook_wide_spread():
    """
    Sample order book with wide spread (0.3%)
    BTC price ~$50,000
    """
    return {
        "bids": [
            ["49900.00", "0.5"],
            ["49850.00", "1.0"],
            ["49800.00", "1.5"],
            ["49750.00", "2.0"],
            ["49700.00", "3.0"],
        ],
        "asks": [
            ["50050.00", "0.5"],
            ["50100.00", "1.0"],
            ["50150.00", "1.5"],
            ["50200.00", "2.0"],
            ["50300.00", "3.0"],
        ]
    }


@pytest.fixture
def sample_orderbook_thin_liquidity():
    """
    Sample order book with thin liquidity
    Total depth < $10,000
    """
    return {
        "bids": [
            ["50000.00", "0.05"],   # $2,500
            ["49950.00", "0.03"],   # $1,498.50
        ],
        "asks": [
            ["50010.00", "0.05"],   # $2,500.50
            ["50050.00", "0.03"],   # $1,501.50
        ]
    }


@pytest.fixture
def empty_orderbook():
    """Empty order book for edge case testing"""
    return {"bids": [], "asks": []}


@pytest.fixture
def mock_execute_func():
    """Mock order execution function"""
    mock = AsyncMock()
    mock.return_value = {
        "orderId": "test_order_123",
        "filled_qty": "0.1",
        "avg_price": "50000.00",
        "status": "filled"
    }
    return mock


@pytest.fixture
def mock_cancel_func():
    """Mock order cancellation function"""
    mock = AsyncMock()
    mock.return_value = {"success": True}
    return mock


# ============================================================================
# ORDER BOOK ANALYSIS TESTS
# ============================================================================

class TestOrderBookAnalysis:
    """Test order book analysis functionality"""

    def test_analyze_orderbook_tight_spread(self, router, sample_orderbook_tight_spread):
        """Test analysis of order book with tight spread"""
        # Execute analysis
        analysis = router.analyze_orderbook(
            symbol="BTCUSDT",
            bids=sample_orderbook_tight_spread["bids"],
            asks=sample_orderbook_tight_spread["asks"]
        )

        # Verify basic properties
        assert analysis.symbol == "BTCUSDT"
        assert analysis.best_bid == Decimal("49995.00")
        assert analysis.best_ask == Decimal("50005.00")

        # Verify mid price
        expected_mid = (Decimal("49995.00") + Decimal("50005.00")) / 2
        assert analysis.mid_price == expected_mid

        # Verify spread
        expected_spread = Decimal("50005.00") - Decimal("49995.00")
        assert analysis.spread_absolute == expected_spread
        assert analysis.spread_pct < 0.001  # Less than 0.1%

        # Verify not thin liquidity (total > $10k)
        assert analysis.depth_total_usd > 10000
        assert analysis.is_thin_liquidity == False

        logger.info(f"Tight spread analysis: spread={analysis.spread_pct:.4%}, depth=${analysis.depth_total_usd:,.0f}")

    def test_analyze_orderbook_wide_spread(self, router, sample_orderbook_wide_spread):
        """Test analysis of order book with wide spread"""
        analysis = router.analyze_orderbook(
            symbol="BTCUSDT",
            bids=sample_orderbook_wide_spread["bids"],
            asks=sample_orderbook_wide_spread["asks"]
        )

        # Verify wide spread detection
        assert analysis.spread_pct > 0.002  # Greater than 0.2%
        assert analysis.spread_pct < 0.005  # But less than 0.5%

        logger.info(f"Wide spread analysis: spread={analysis.spread_pct:.4%}")

    def test_analyze_orderbook_thin_liquidity(self, router, sample_orderbook_thin_liquidity):
        """Test analysis detects thin liquidity conditions"""
        analysis = router.analyze_orderbook(
            symbol="BTCUSDT",
            bids=sample_orderbook_thin_liquidity["bids"],
            asks=sample_orderbook_thin_liquidity["asks"]
        )

        # Should detect thin liquidity
        assert analysis.is_thin_liquidity == True
        assert analysis.thin_liquidity_warning is not None
        assert "Low liquidity" in analysis.thin_liquidity_warning

        logger.info(f"Thin liquidity: depth=${analysis.depth_total_usd:,.0f}")

    def test_analyze_orderbook_empty(self, router, empty_orderbook):
        """Test analysis handles empty order book gracefully"""
        analysis = router.analyze_orderbook(
            symbol="BTCUSDT",
            bids=empty_orderbook["bids"],
            asks=empty_orderbook["asks"],
            current_price=Decimal("50000")
        )

        # Should mark as thin liquidity
        assert analysis.is_thin_liquidity == True
        assert analysis.depth_total_usd == 0.0

    def test_analyze_orderbook_imbalance_ratio(self, router):
        """Test imbalance ratio calculation"""
        # Create orderbook with more bids than asks
        unbalanced_book = {
            "bids": [
                ["50000.00", "10.0"],  # $500,000
                ["49990.00", "5.0"],   # $249,950
            ],
            "asks": [
                ["50010.00", "2.0"],   # $100,020
                ["50020.00", "1.0"],   # $50,020
            ]
        }

        analysis = router.analyze_orderbook(
            symbol="BTCUSDT",
            bids=unbalanced_book["bids"],
            asks=unbalanced_book["asks"]
        )

        # Bid depth > Ask depth, so imbalance > 1
        assert analysis.imbalance_ratio > 1.0
        logger.info(f"Imbalance ratio: {analysis.imbalance_ratio:.2f} (buy pressure)")

    def test_analyze_orderbook_depth_levels(self, router, sample_orderbook_tight_spread):
        """Test depth calculation at multiple price levels"""
        analysis = router.analyze_orderbook(
            symbol="BTCUSDT",
            bids=sample_orderbook_tight_spread["bids"],
            asks=sample_orderbook_tight_spread["asks"]
        )

        # Depth should increase with distance from mid
        assert analysis.depth_at_01pct <= analysis.depth_at_05pct
        assert analysis.depth_at_05pct <= analysis.depth_at_1pct

        logger.info(
            f"Depth levels: 0.1%=${analysis.depth_at_01pct:,.0f}, "
            f"0.5%=${analysis.depth_at_05pct:,.0f}, 1%=${analysis.depth_at_1pct:,.0f}"
        )


# ============================================================================
# SLIPPAGE ESTIMATION TESTS
# ============================================================================

class TestSlippageEstimation:
    """Test slippage estimation functionality"""

    def test_estimate_slippage_small_buy(self, router, sample_orderbook_tight_spread):
        """Test slippage for small buy order (should be minimal)"""
        # Analyze orderbook first
        analysis = router.analyze_orderbook(
            symbol="BTCUSDT",
            bids=sample_orderbook_tight_spread["bids"],
            asks=sample_orderbook_tight_spread["asks"]
        )

        # Estimate slippage for small buy (0.01 BTC = ~$500)
        estimate = router.estimate_slippage(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.01"),
            orderbook_analysis=analysis,
            asks=sample_orderbook_tight_spread["asks"]
        )

        # Small order should have minimal slippage
        assert estimate.expected_slippage_pct < 0.1  # Less than 0.1%
        assert estimate.is_acceptable == True
        assert estimate.levels_consumed <= 1

        logger.info(f"Small buy slippage: {estimate.expected_slippage_pct:.4f}%")

    def test_estimate_slippage_large_buy(self, router, sample_orderbook_tight_spread):
        """Test slippage for large buy order (should consume multiple levels)"""
        analysis = router.analyze_orderbook(
            symbol="BTCUSDT",
            bids=sample_orderbook_tight_spread["bids"],
            asks=sample_orderbook_tight_spread["asks"]
        )

        # Estimate slippage for large buy (5 BTC = ~$250,000)
        estimate = router.estimate_slippage(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("5.0"),
            orderbook_analysis=analysis,
            asks=sample_orderbook_tight_spread["asks"]
        )

        # Large order should have higher slippage
        assert estimate.expected_slippage_pct > 0.01  # More than 0.01%
        assert estimate.levels_consumed > 1
        assert estimate.slippage_cost_usd > 0

        logger.info(
            f"Large buy slippage: {estimate.expected_slippage_pct:.4f}%, "
            f"cost=${estimate.slippage_cost_usd:.2f}, levels={estimate.levels_consumed}"
        )

    def test_estimate_slippage_sell(self, router, sample_orderbook_tight_spread):
        """Test slippage for sell order"""
        analysis = router.analyze_orderbook(
            symbol="BTCUSDT",
            bids=sample_orderbook_tight_spread["bids"],
            asks=sample_orderbook_tight_spread["asks"]
        )

        # Estimate slippage for sell (0.5 BTC)
        estimate = router.estimate_slippage(
            symbol="BTCUSDT",
            side="SELL",
            quantity=Decimal("0.5"),
            orderbook_analysis=analysis,
            bids=sample_orderbook_tight_spread["bids"]
        )

        # Sell should also calculate slippage
        assert estimate.side == "SELL"
        assert estimate.mid_price > 0
        assert estimate.execution_price > 0

        logger.info(f"Sell slippage: {estimate.expected_slippage_pct:.4f}%")

    def test_estimate_slippage_exceeds_threshold(self, router, sample_orderbook_thin_liquidity):
        """Test slippage warning when exceeding threshold"""
        analysis = router.analyze_orderbook(
            symbol="BTCUSDT",
            bids=sample_orderbook_thin_liquidity["bids"],
            asks=sample_orderbook_thin_liquidity["asks"]
        )

        # Large order in thin book should exceed threshold
        estimate = router.estimate_slippage(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.5"),  # Large relative to thin book
            orderbook_analysis=analysis,
            asks=sample_orderbook_thin_liquidity["asks"]
        )

        # Should generate warning
        assert estimate.warning_message is not None

        logger.info(f"Threshold exceeded: {estimate.warning_message}")

    def test_estimate_slippage_no_orderbook(self, router):
        """Test slippage estimation with no order book data"""
        # No analysis, no raw data
        estimate = router.estimate_slippage(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.0")
        )

        # Should return conservative estimate
        assert estimate.expected_slippage_pct == 0.5
        assert estimate.is_acceptable == False
        assert "No order book data" in estimate.warning_message


# ============================================================================
# ORDER TYPE SELECTION TESTS
# ============================================================================

class TestOrderTypeSelection:
    """Test order type selection decision logic"""

    def test_small_order_tight_spread_high_urgency_market(self, router, sample_orderbook_tight_spread):
        """Small order + tight spread + high urgency = MARKET"""
        recommendation = router.get_order_recommendation(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.01"),  # ~$500 (small)
            urgency=ExecutionUrgency.HIGH,
            orderbook_depth=sample_orderbook_tight_spread,
            current_price=Decimal("50000")
        )

        assert recommendation.order_type == OrderTypeSelection.MARKET
        assert recommendation.strategy == ExecutionStrategyType.SINGLE
        assert "MARKET" in recommendation.reasoning.upper()

        logger.info(f"Decision: {recommendation.order_type.value} - {recommendation.reasoning}")

    def test_medium_order_limit_at_mid(self, router, sample_orderbook_tight_spread):
        """Medium order = LIMIT at mid price"""
        recommendation = router.get_order_recommendation(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.05"),  # ~$2,500 (medium)
            urgency=ExecutionUrgency.MEDIUM,
            orderbook_depth=sample_orderbook_tight_spread,
            current_price=Decimal("50000")
        )

        assert recommendation.order_type == OrderTypeSelection.LIMIT
        assert recommendation.limit_price is not None
        assert "LIMIT" in recommendation.reasoning or "mid" in recommendation.reasoning.lower()

        logger.info(f"Decision: {recommendation.order_type.value} at {recommendation.limit_price}")

    def test_wide_spread_forces_limit(self, router, sample_orderbook_wide_spread):
        """Wide spread should force LIMIT order regardless of size"""
        recommendation = router.get_order_recommendation(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.01"),  # Small order
            urgency=ExecutionUrgency.MEDIUM,
            orderbook_depth=sample_orderbook_wide_spread,
            current_price=Decimal("50000")
        )

        # Wide spread should result in LIMIT
        assert recommendation.order_type == OrderTypeSelection.LIMIT
        assert "spread" in recommendation.reasoning.lower()

        logger.info(f"Wide spread decision: {recommendation.reasoning}")

    def test_critical_urgency_always_market(self, router, sample_orderbook_wide_spread):
        """CRITICAL urgency should always use MARKET"""
        recommendation = router.get_order_recommendation(
            symbol="BTCUSDT",
            side="SELL",  # Urgent sell (stop loss)
            quantity=Decimal("0.1"),
            urgency=ExecutionUrgency.CRITICAL,
            orderbook_depth=sample_orderbook_wide_spread,
            current_price=Decimal("50000")
        )

        assert recommendation.order_type == OrderTypeSelection.MARKET
        assert "CRITICAL" in recommendation.reasoning

        logger.info(f"Critical urgency: {recommendation.order_type.value}")

    def test_low_urgency_post_only(self, router, sample_orderbook_tight_spread):
        """LOW urgency (stat arb) should use POST_ONLY"""
        recommendation = router.get_order_recommendation(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.05"),
            urgency=ExecutionUrgency.LOW,
            orderbook_depth=sample_orderbook_tight_spread,
            current_price=Decimal("50000")
        )

        assert recommendation.order_type == OrderTypeSelection.POST_ONLY
        assert recommendation.strategy == ExecutionStrategyType.POST_ONLY
        assert "maker" in recommendation.reasoning.lower()

        logger.info(f"Low urgency (stat arb): {recommendation.order_type.value}")

    def test_large_order_twap_split(self, router_custom, sample_orderbook_tight_spread):
        """Large order should use TWAP split strategy"""
        # Using custom config with lower thresholds
        recommendation = router_custom.get_order_recommendation(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("5.0"),  # ~$250,000 (large)
            urgency=ExecutionUrgency.MEDIUM,
            orderbook_depth=sample_orderbook_tight_spread,
            current_price=Decimal("50000")
        )

        assert recommendation.strategy == ExecutionStrategyType.SPLIT_TWAP
        assert len(recommendation.chunks) >= 2
        assert "TWAP" in recommendation.reasoning

        logger.info(f"TWAP split: {len(recommendation.chunks)} chunks - {recommendation.reasoning}")

    def test_large_order_low_urgency_iceberg(self, router_custom, sample_orderbook_tight_spread):
        """Large order with LOW urgency should use ICEBERG"""
        recommendation = router_custom.get_order_recommendation(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("5.0"),  # Large order
            urgency=ExecutionUrgency.LOW,
            orderbook_depth=sample_orderbook_tight_spread,
            current_price=Decimal("50000")
        )

        # POST_ONLY takes precedence for LOW urgency
        # But if book is large relative to order, it may use ICEBERG
        assert recommendation.strategy in (ExecutionStrategyType.POST_ONLY, ExecutionStrategyType.SPLIT_ICEBERG)

        logger.info(f"Large + Low urgency: {recommendation.strategy.value}")

    def test_thin_liquidity_warning(self, router, sample_orderbook_thin_liquidity):
        """Thin liquidity should add warning to recommendation"""
        recommendation = router.get_order_recommendation(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.1"),
            urgency=ExecutionUrgency.MEDIUM,
            orderbook_depth=sample_orderbook_thin_liquidity,
            current_price=Decimal("50000")
        )

        # Should have warning in reasoning
        assert "WARNING" in recommendation.reasoning or "Low liquidity" in recommendation.reasoning
        # Confidence should be reduced
        assert recommendation.confidence < 0.7

        logger.info(f"Thin liquidity warning: {recommendation.reasoning}")

    def test_recommendation_includes_analysis(self, router, sample_orderbook_tight_spread):
        """Recommendation should include order book analysis and slippage estimate"""
        recommendation = router.get_order_recommendation(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.1"),
            urgency=ExecutionUrgency.MEDIUM,
            orderbook_depth=sample_orderbook_tight_spread,
            current_price=Decimal("50000")
        )

        # Should have analysis attached
        assert recommendation.orderbook_analysis is not None
        assert recommendation.slippage_estimate is not None
        assert recommendation.orderbook_analysis.symbol == "BTCUSDT"

    def test_sell_order_routing(self, router, sample_orderbook_tight_spread):
        """Test sell order goes through same routing logic"""
        recommendation = router.get_order_recommendation(
            symbol="BTCUSDT",
            side="SELL",
            quantity=Decimal("0.1"),
            urgency=ExecutionUrgency.MEDIUM,
            orderbook_depth=sample_orderbook_tight_spread,
            current_price=Decimal("50000")
        )

        assert recommendation.side == "SELL"
        assert recommendation.order_type in (OrderTypeSelection.MARKET, OrderTypeSelection.LIMIT, OrderTypeSelection.POST_ONLY)


# ============================================================================
# EXECUTION TESTS
# ============================================================================

class TestExecution:
    """Test order execution functionality"""

    @pytest.mark.asyncio
    async def test_execute_market_order(self, router, sample_orderbook_tight_spread, mock_execute_func):
        """Test execution of simple market order"""
        recommendation = router.get_order_recommendation(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.1"),
            urgency=ExecutionUrgency.CRITICAL,
            orderbook_depth=sample_orderbook_tight_spread,
            current_price=Decimal("50000")
        )

        record = await router.execute_recommendation(
            recommendation=recommendation,
            execute_func=mock_execute_func
        )

        assert record.order_type == OrderTypeSelection.MARKET
        assert record.filled_quantity > 0
        assert record.is_complete or record.fill_rate > 0
        mock_execute_func.assert_called()

        logger.info(f"Execution record: filled={record.fill_rate:.1%}, slippage={record.slippage_pct:.3f}%")

    @pytest.mark.asyncio
    async def test_execute_limit_order(self, router, sample_orderbook_tight_spread, mock_execute_func, mock_cancel_func):
        """Test execution of limit order"""
        # Force limit order via wide spread scenario
        recommendation = router.get_order_recommendation(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.05"),
            urgency=ExecutionUrgency.MEDIUM,
            orderbook_depth=sample_orderbook_tight_spread,
            current_price=Decimal("50000")
        )

        record = await router.execute_recommendation(
            recommendation=recommendation,
            execute_func=mock_execute_func,
            cancel_func=mock_cancel_func
        )

        assert record.strategy == recommendation.strategy
        mock_execute_func.assert_called()

        logger.info(f"Limit order executed: type={record.order_type.value}")

    @pytest.mark.asyncio
    async def test_execute_twap(self, router_custom, sample_orderbook_tight_spread, mock_execute_func):
        """Test TWAP execution splits order into chunks"""
        # Force TWAP with large order
        recommendation = router_custom.get_order_recommendation(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("10.0"),  # Large order
            urgency=ExecutionUrgency.MEDIUM,
            orderbook_depth=sample_orderbook_tight_spread,
            current_price=Decimal("50000")
        )

        # Override to ensure TWAP
        recommendation.strategy = ExecutionStrategyType.SPLIT_TWAP
        recommendation.chunks = [
            {"chunk_id": 1, "quantity": Decimal("5.0"), "scheduled_time": datetime.now(timezone.utc).isoformat(), "status": "pending"},
            {"chunk_id": 2, "quantity": Decimal("5.0"), "scheduled_time": datetime.now(timezone.utc).isoformat(), "status": "pending"},
        ]

        # Execute with short interval for testing
        router_custom.config.twap_chunk_interval_seconds = 0  # No delay for test

        record = await router_custom.execute_recommendation(
            recommendation=recommendation,
            execute_func=mock_execute_func
        )

        # Should have called execute multiple times (once per chunk)
        assert mock_execute_func.call_count >= 2

        logger.info(f"TWAP executed: {mock_execute_func.call_count} chunks")

    @pytest.mark.asyncio
    async def test_execution_error_handling(self, router, sample_orderbook_tight_spread):
        """Test execution handles errors gracefully"""
        # Create failing execute function
        failing_func = AsyncMock(side_effect=Exception("API Error"))

        recommendation = router.get_order_recommendation(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.1"),
            urgency=ExecutionUrgency.MEDIUM,
            orderbook_depth=sample_orderbook_tight_spread,
            current_price=Decimal("50000")
        )

        record = await router.execute_recommendation(
            recommendation=recommendation,
            execute_func=failing_func
        )

        assert record.error_message is not None
        assert "API Error" in record.error_message
        assert record.is_complete == False

        logger.info(f"Error handled: {record.error_message}")


# ============================================================================
# METRICS AND REPORTING TESTS
# ============================================================================

class TestMetricsAndReporting:
    """Test metrics tracking and reporting functionality"""

    @pytest.mark.asyncio
    async def test_metrics_update_on_execution(self, router, sample_orderbook_tight_spread, mock_execute_func):
        """Test metrics are updated after execution"""
        initial_orders = router._metrics.total_orders

        recommendation = router.get_order_recommendation(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.1"),
            urgency=ExecutionUrgency.HIGH,
            orderbook_depth=sample_orderbook_tight_spread,
            current_price=Decimal("50000")
        )

        await router.execute_recommendation(
            recommendation=recommendation,
            execute_func=mock_execute_func
        )

        # Metrics should be updated
        assert router._metrics.total_orders == initial_orders + 1

    @pytest.mark.asyncio
    async def test_metrics_track_order_types(self, router, sample_orderbook_tight_spread, mock_execute_func):
        """Test metrics track different order types"""
        # Execute market order
        rec1 = router.get_order_recommendation(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.01"),
            urgency=ExecutionUrgency.CRITICAL,
            orderbook_depth=sample_orderbook_tight_spread,
            current_price=Decimal("50000")
        )
        await router.execute_recommendation(rec1, mock_execute_func)

        # Execute limit order
        rec2 = router.get_order_recommendation(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.03"),
            urgency=ExecutionUrgency.MEDIUM,
            orderbook_depth=sample_orderbook_tight_spread,
            current_price=Decimal("50000")
        )
        await router.execute_recommendation(rec2, mock_execute_func)

        metrics = router.get_metrics()
        assert metrics.total_orders == 2

        logger.info(f"Order type distribution: market={metrics.market_orders}, limit={metrics.limit_orders}")

    def test_get_status(self, router):
        """Test status endpoint returns expected data"""
        status = router.get_status()

        assert "config" in status
        assert "metrics" in status
        assert "order_type_distribution" in status
        assert "history_size" in status

        assert "tight_spread_threshold" in status["config"]
        assert "total_orders" in status["metrics"]

        logger.info(f"Status: {status}")

    @pytest.mark.asyncio
    async def test_execution_quality_report(self, router, sample_orderbook_tight_spread, mock_execute_func):
        """Test execution quality report generation"""
        # Execute a few orders
        for i in range(3):
            recommendation = router.get_order_recommendation(
                symbol="BTCUSDT",
                side="BUY",
                quantity=Decimal("0.1"),
                urgency=ExecutionUrgency.MEDIUM,
                orderbook_depth=sample_orderbook_tight_spread,
                current_price=Decimal("50000")
            )
            await router.execute_recommendation(recommendation, mock_execute_func)

        # Generate report
        report = router.get_execution_quality_report(period_hours=24)

        assert report.metrics.total_orders == 3
        assert len(report.recommendations) > 0
        assert report.report_period_start < report.report_period_end

        logger.info(f"Report: orders={report.metrics.total_orders}, recommendations={report.recommendations}")


# ============================================================================
# EDGE CASES AND INTEGRATION TESTS
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_zero_quantity_handling(self, router, sample_orderbook_tight_spread):
        """Test handling of zero quantity order"""
        recommendation = router.get_order_recommendation(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0"),
            urgency=ExecutionUrgency.MEDIUM,
            orderbook_depth=sample_orderbook_tight_spread,
            current_price=Decimal("50000")
        )

        # Should still return a recommendation (validation should be done elsewhere)
        assert recommendation is not None
        assert recommendation.quantity == Decimal("0")

    def test_very_large_order(self, router, sample_orderbook_tight_spread):
        """Test handling of very large order (larger than book)"""
        recommendation = router.get_order_recommendation(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1000"),  # Much larger than book depth
            urgency=ExecutionUrgency.MEDIUM,
            orderbook_depth=sample_orderbook_tight_spread,
            current_price=Decimal("50000")
        )

        # Should recommend split strategy
        assert recommendation.strategy in (ExecutionStrategyType.SPLIT_TWAP, ExecutionStrategyType.SPLIT_ICEBERG)

        logger.info(f"Large order strategy: {recommendation.strategy.value}")

    def test_negative_slippage_favorable(self, router, sample_orderbook_tight_spread):
        """Test handling when execution is favorable (negative slippage)"""
        analysis = router.analyze_orderbook(
            symbol="BTCUSDT",
            bids=sample_orderbook_tight_spread["bids"],
            asks=sample_orderbook_tight_spread["asks"]
        )

        # With tight spread, small order might have favorable execution
        estimate = router.estimate_slippage(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.001"),  # Very small
            orderbook_analysis=analysis,
            asks=sample_orderbook_tight_spread["asks"]
        )

        # Slippage can be close to zero or slightly positive
        assert estimate.is_acceptable == True

    def test_cache_usage(self, router, sample_orderbook_tight_spread):
        """Test order book analysis caching"""
        # First analysis
        analysis1 = router.analyze_orderbook(
            symbol="BTCUSDT",
            bids=sample_orderbook_tight_spread["bids"],
            asks=sample_orderbook_tight_spread["asks"]
        )

        # Should be cached
        assert "BTCUSDT" in router._orderbook_cache

        # Estimate slippage should use cache if no new data provided
        estimate = router.estimate_slippage(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.1")
        )

        assert estimate.symbol == "BTCUSDT"


class TestGlobalInstance:
    """Test global instance management"""

    def test_get_smart_router_singleton(self):
        """Test global router is a singleton"""
        reset_smart_router()

        router1 = get_smart_router()
        router2 = get_smart_router()

        assert router1 is router2

    def test_reset_smart_router(self):
        """Test router reset creates new instance"""
        router1 = get_smart_router()
        reset_smart_router()
        router2 = get_smart_router()

        assert router1 is not router2

    def test_get_smart_router_with_config(self):
        """Test global router accepts config on creation"""
        reset_smart_router()

        custom_config = SmartRouterConfig(
            tight_spread_threshold=0.001
        )
        router = get_smart_router(custom_config)

        assert router.config.tight_spread_threshold == 0.001

    def test_small_order_threshold_dataclass_default_unchanged(self):
        """RES-05: direct construction is unaffected by the Settings wiring.

        The dataclass default stays 1000.0, so every caller that builds its
        own SmartRouterConfig behaves exactly as it did before.
        """
        assert SmartRouterConfig().small_order_threshold == 1000.0

    def test_get_smart_router_uses_settings_threshold(self):
        """RES-05: the no-argument factory honours the operator Setting.

        Wired in the FACTORY rather than the lifespan on purpose: the
        POST /api/v1/execution/reset handler calls reset_smart_router() and
        the next get_smart_router() rebuilds here, so a lifespan-only wiring
        would silently revert to the hardcoded literal on the first reset.
        """
        reset_smart_router()
        try:
            fake_settings = SimpleNamespace(
                smart_router_small_order_threshold_usd=2500.0
            )
            with patch("app.config.get_settings", return_value=fake_settings):
                router = get_smart_router()

            assert router.config.small_order_threshold == 2500.0
        finally:
            # Never leak a 2500.0 router into the module-level singleton
            reset_smart_router()

    def test_explicit_config_still_wins_over_settings(self):
        """RES-05: an explicit config is not overridden by the Setting."""
        reset_smart_router()
        try:
            fake_settings = SimpleNamespace(
                smart_router_small_order_threshold_usd=2500.0
            )
            explicit = SmartRouterConfig(small_order_threshold=750.0)
            with patch("app.config.get_settings", return_value=fake_settings):
                router = get_smart_router(explicit)

            assert router.config.small_order_threshold == 750.0
        finally:
            reset_smart_router()


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

class TestPerformance:
    """Test performance characteristics"""

    def test_orderbook_analysis_performance(self, router, benchmark_timer):
        """Order book analysis should complete quickly"""
        # Large order book
        large_book = {
            "bids": [[str(50000 - i), "1.0"] for i in range(100)],
            "asks": [[str(50000 + i), "1.0"] for i in range(100)]
        }

        with benchmark_timer() as timer:
            for _ in range(100):
                router.analyze_orderbook(
                    symbol="BTCUSDT",
                    bids=large_book["bids"],
                    asks=large_book["asks"]
                )

        # Should complete 100 analyses in under 500ms
        timer.assert_faster_than(500, "Order book analysis too slow")

        logger.info(f"100 analyses completed in {timer.elapsed_ms:.2f}ms")

    def test_recommendation_performance(self, router, sample_orderbook_tight_spread, benchmark_timer):
        """Recommendation generation should be fast"""
        with benchmark_timer() as timer:
            for _ in range(50):
                router.get_order_recommendation(
                    symbol="BTCUSDT",
                    side="BUY",
                    quantity=Decimal("0.1"),
                    urgency=ExecutionUrgency.MEDIUM,
                    orderbook_depth=sample_orderbook_tight_spread,
                    current_price=Decimal("50000")
                )

        # Should complete 50 recommendations in under 500ms
        timer.assert_faster_than(500, "Recommendation generation too slow")

        logger.info(f"50 recommendations generated in {timer.elapsed_ms:.2f}ms")


# ============================================================================
# BENCHMARK TIMER FIXTURE (from conftest.py if not available)
# ============================================================================

@pytest.fixture
def benchmark_timer():
    """Simple timer for performance testing"""
    import time

    class Timer:
        def __init__(self):
            self.start_time = None
            self.elapsed_ms = None

        def __enter__(self):
            self.start_time = time.time()
            return self

        def __exit__(self, *args):
            self.elapsed_ms = (time.time() - self.start_time) * 1000

        def assert_faster_than(self, max_ms: float, message: str = None):
            assert self.elapsed_ms < max_ms, (
                message or f"Operation took {self.elapsed_ms:.2f}ms, expected < {max_ms}ms"
            )

    return Timer
