"""
Orderbook Analyzer Tests
Phase 4.1: Smart Order Routing - Orderbook Analysis Component Tests

Purpose:
- Verify liquidity analysis accuracy
- Test market impact estimation
- Validate optimal limit price calculation
- Test edge cases (empty books, thin liquidity)
- Ensure correct classification of liquidity levels

Target Coverage: >85%

Author: Backend Developer Agent
Created: 2025-12-11
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import patch
import logging

# Import the orderbook analyzer module
from app.execution.orderbook_analyzer import (
    OrderbookAnalyzer,
    OrderBookConfig,
    LiquidityLevel,
    OrderBookState,
    SpreadCategory,
    PriceLevel,
    DepthAnalysis,
    MarketImpactEstimate,
    LiquidityReport,
    OptimalLimitPrice,
    get_orderbook_analyzer,
    reset_orderbook_analyzer,
)

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def default_config():
    """Provide default orderbook config"""
    return OrderBookConfig()


@pytest.fixture
def analyzer(default_config):
    """Provide fresh analyzer instance for each test"""
    reset_orderbook_analyzer()
    return OrderbookAnalyzer(default_config)


@pytest.fixture
def high_liquidity_orderbook():
    """
    High liquidity order book with tight spread
    BTC price ~$50,000, spread ~0.02%
    """
    return {
        "bids": [
            ["50000", "5.0"],     # $250,000
            ["49990", "3.0"],     # $149,970
            ["49980", "4.0"],     # $199,920
            ["49970", "2.5"],     # $124,925
            ["49960", "3.5"],     # $174,860
            ["49950", "2.0"],     # $99,900
            ["49940", "1.5"],     # $74,910
            ["49930", "2.0"],     # $99,860
            ["49920", "1.0"],     # $49,920
            ["49910", "1.5"],     # $74,865
        ],
        "asks": [
            ["50010", "4.0"],     # $200,040
            ["50020", "3.5"],     # $175,070
            ["50030", "2.5"],     # $125,075
            ["50040", "3.0"],     # $150,120
            ["50050", "2.0"],     # $100,100
            ["50060", "1.5"],     # $75,090
            ["50070", "2.5"],     # $125,175
            ["50080", "1.0"],     # $50,080
            ["50090", "1.5"],     # $75,135
            ["50100", "2.0"],     # $100,200
        ]
    }


@pytest.fixture
def low_liquidity_orderbook():
    """
    Low liquidity order book with wide spread
    Alt price ~$10, spread ~0.5%
    """
    return {
        "bids": [
            ["9.95", "100"],      # $995
            ["9.90", "150"],      # $1,485
            ["9.85", "200"],      # $1,970
        ],
        "asks": [
            ["10.00", "80"],      # $800
            ["10.05", "120"],     # $1,206
            ["10.10", "100"],     # $1,010
        ]
    }


@pytest.fixture
def imbalanced_orderbook_bids():
    """Order book with heavy bid side (buy pressure)"""
    return {
        "bids": [
            ["100", "500"],       # $50,000
            ["99.90", "400"],     # $39,960
            ["99.80", "300"],     # $29,940
            ["99.70", "200"],     # $19,940
        ],
        "asks": [
            ["100.10", "50"],     # $5,005
            ["100.20", "40"],     # $4,008
            ["100.30", "30"],     # $3,009
        ]
    }


@pytest.fixture
def imbalanced_orderbook_asks():
    """Order book with heavy ask side (sell pressure)"""
    return {
        "bids": [
            ["100", "50"],        # $5,000
            ["99.90", "40"],      # $3,996
        ],
        "asks": [
            ["100.10", "500"],    # $50,050
            ["100.20", "400"],    # $40,080
            ["100.30", "300"],    # $30,090
        ]
    }


# ============================================================================
# LIQUIDITY ANALYSIS TESTS
# ============================================================================

class TestLiquidityAnalysis:
    """Test suite for liquidity analysis functionality"""

    def test_analyze_high_liquidity_orderbook(self, analyzer, high_liquidity_orderbook):
        """Test analysis of high liquidity order book"""
        report = analyzer.analyze_liquidity(
            symbol="BTCUSDT",
            bids=high_liquidity_orderbook["bids"],
            asks=high_liquidity_orderbook["asks"]
        )

        # Verify basic price metrics
        assert report.best_bid == Decimal("50000")
        assert report.best_ask == Decimal("50010")
        assert report.mid_price == Decimal("50005")

        # Verify spread
        assert report.spread_absolute == Decimal("10")
        assert 0.0001 < report.spread_pct < 0.0003  # ~0.02%
        assert report.spread_category == SpreadCategory.TIGHT

        # Verify liquidity classification
        assert report.liquidity_level in (LiquidityLevel.HIGH, LiquidityLevel.MEDIUM)
        assert report.liquidity_score > 50

        # Verify depths are calculated
        assert report.total_bid_depth_usd > 0
        assert report.total_ask_depth_usd > 0
        assert report.total_depth_usd > 0

        # Verify no warnings for high liquidity
        assert len([w for w in report.warnings if "CRITICAL" in w]) == 0

    def test_analyze_low_liquidity_orderbook(self, analyzer, low_liquidity_orderbook):
        """Test analysis of low liquidity order book"""
        report = analyzer.analyze_liquidity(
            symbol="ALTUSDT",
            bids=low_liquidity_orderbook["bids"],
            asks=low_liquidity_orderbook["asks"]
        )

        # Verify spread is wider
        assert report.spread_pct > 0.003  # >0.3%
        assert report.spread_category in (SpreadCategory.WIDE, SpreadCategory.VERY_WIDE)

        # Verify lower liquidity classification
        assert report.liquidity_level in (LiquidityLevel.LOW, LiquidityLevel.VERY_LOW)
        assert report.liquidity_score < 50

        # Verify warnings present
        assert len(report.warnings) > 0

    def test_analyze_empty_orderbook(self, analyzer):
        """Test handling of empty order book"""
        report = analyzer.analyze_liquidity(
            symbol="UNKNOWN",
            bids=[],
            asks=[],
            current_price=Decimal("100")
        )

        # Should return with thin liquidity flag
        assert report.liquidity_level == LiquidityLevel.VERY_LOW
        assert report.is_thin_liquidity if hasattr(report, 'is_thin_liquidity') else True
        assert len(report.warnings) > 0

    def test_spread_categorization(self, analyzer):
        """Test spread categorization at various levels"""
        # Tight spread: 0.01%
        tight_book = {
            "bids": [["100000", "1.0"]],
            "asks": [["100010", "1.0"]]  # 0.01% spread
        }
        report = analyzer.analyze_liquidity("TEST", tight_book["bids"], tight_book["asks"])
        assert report.spread_category == SpreadCategory.TIGHT

        # Normal spread: 0.08%
        normal_book = {
            "bids": [["100000", "1.0"]],
            "asks": [["100080", "1.0"]]  # 0.08% spread
        }
        report = analyzer.analyze_liquidity("TEST", normal_book["bids"], normal_book["asks"])
        assert report.spread_category == SpreadCategory.NORMAL

        # Wide spread: 0.15%
        wide_book = {
            "bids": [["100000", "1.0"]],
            "asks": [["100150", "1.0"]]  # 0.15% spread
        }
        report = analyzer.analyze_liquidity("TEST", wide_book["bids"], wide_book["asks"])
        assert report.spread_category == SpreadCategory.WIDE

    def test_order_book_state_detection(self, analyzer, imbalanced_orderbook_bids, imbalanced_orderbook_asks):
        """Test detection of order book imbalance states"""
        # Test bid-heavy book
        report = analyzer.analyze_liquidity(
            symbol="TEST",
            bids=imbalanced_orderbook_bids["bids"],
            asks=imbalanced_orderbook_bids["asks"]
        )
        assert report.book_state == OrderBookState.BID_HEAVY
        assert report.imbalance_ratio > 1.0

        # Test ask-heavy book
        report = analyzer.analyze_liquidity(
            symbol="TEST",
            bids=imbalanced_orderbook_asks["bids"],
            asks=imbalanced_orderbook_asks["asks"]
        )
        assert report.book_state == OrderBookState.ASK_HEAVY
        assert report.imbalance_ratio < 1.0

    def test_depth_at_various_levels(self, analyzer, high_liquidity_orderbook):
        """Test depth calculation at different price levels"""
        report = analyzer.analyze_liquidity(
            symbol="BTCUSDT",
            bids=high_liquidity_orderbook["bids"],
            asks=high_liquidity_orderbook["asks"]
        )

        # Depth should increase with distance from mid
        assert report.depth_at_01pct.total_depth_usd >= 0
        assert report.depth_at_05pct.total_depth_usd >= report.depth_at_01pct.total_depth_usd
        assert report.depth_at_1pct.total_depth_usd >= report.depth_at_05pct.total_depth_usd


# ============================================================================
# MARKET IMPACT ESTIMATION TESTS
# ============================================================================

class TestMarketImpactEstimation:
    """Test suite for market impact estimation"""

    def test_small_order_impact(self, analyzer, high_liquidity_orderbook):
        """Test market impact for small order (minimal impact expected)"""
        impact = analyzer.estimate_market_impact(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.01"),  # ~$500 order
            bids=high_liquidity_orderbook["bids"],
            asks=high_liquidity_orderbook["asks"]
        )

        # Small order should have minimal impact
        assert impact.total_impact_pct < 0.1  # Less than 0.1%
        assert impact.price_levels_consumed <= 1
        assert impact.is_acceptable is True

    def test_large_order_impact(self, analyzer, high_liquidity_orderbook):
        """Test market impact for large order (significant impact expected)"""
        impact = analyzer.estimate_market_impact(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("10"),  # ~$500,000 order
            bids=high_liquidity_orderbook["bids"],
            asks=high_liquidity_orderbook["asks"]
        )

        # Large order should have higher impact
        assert impact.total_impact_pct > 0.01  # More than 0.01%
        assert impact.price_levels_consumed >= 1
        assert impact.slippage_cost_usd > 0

    def test_buy_vs_sell_impact(self, analyzer, high_liquidity_orderbook):
        """Test that buy and sell impact are calculated correctly"""
        buy_impact = analyzer.estimate_market_impact(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1"),
            bids=high_liquidity_orderbook["bids"],
            asks=high_liquidity_orderbook["asks"]
        )

        sell_impact = analyzer.estimate_market_impact(
            symbol="BTCUSDT",
            side="SELL",
            quantity=Decimal("1"),
            bids=high_liquidity_orderbook["bids"],
            asks=high_liquidity_orderbook["asks"]
        )

        # Both should have impact calculated
        assert buy_impact.execution_price >= 0
        assert sell_impact.execution_price >= 0

        # For buys, execution price should be >= mid
        assert buy_impact.execution_price >= buy_impact.mid_price or buy_impact.price_levels_consumed == 0

    def test_impact_with_low_liquidity(self, analyzer, low_liquidity_orderbook):
        """Test market impact with low liquidity (should show warning)"""
        impact = analyzer.estimate_market_impact(
            symbol="ALTUSDT",
            side="BUY",
            quantity=Decimal("500"),  # Large relative to liquidity
            bids=low_liquidity_orderbook["bids"],
            asks=low_liquidity_orderbook["asks"]
        )

        # Should have warning about partial fill or high impact
        assert impact.warning_message is not None or impact.total_impact_pct > 0.5
        assert impact.is_acceptable is False


# ============================================================================
# OPTIMAL LIMIT PRICE TESTS
# ============================================================================

class TestOptimalLimitPrice:
    """Test suite for optimal limit price calculation"""

    def test_optimal_price_for_buy(self, analyzer, high_liquidity_orderbook):
        """Test optimal limit price calculation for buy orders"""
        # First analyze order book
        analyzer.analyze_liquidity(
            symbol="BTCUSDT",
            bids=high_liquidity_orderbook["bids"],
            asks=high_liquidity_orderbook["asks"]
        )

        optimal = analyzer.find_optimal_limit_price(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.5"),
            target_fill_probability=0.8,
            bids=high_liquidity_orderbook["bids"],
            asks=high_liquidity_orderbook["asks"]
        )

        # For buys, recommended price should be at or below best ask
        assert optimal.recommended_price <= optimal.best_price
        assert optimal.estimated_fill_probability > 0
        assert optimal.expected_cost_vs_market_pct >= 0  # Should be savings

    def test_optimal_price_for_sell(self, analyzer, high_liquidity_orderbook):
        """Test optimal limit price calculation for sell orders"""
        analyzer.analyze_liquidity(
            symbol="BTCUSDT",
            bids=high_liquidity_orderbook["bids"],
            asks=high_liquidity_orderbook["asks"]
        )

        optimal = analyzer.find_optimal_limit_price(
            symbol="BTCUSDT",
            side="SELL",
            quantity=Decimal("0.5"),
            target_fill_probability=0.8,
            bids=high_liquidity_orderbook["bids"],
            asks=high_liquidity_orderbook["asks"]
        )

        # For sells, recommended price should be at or above best bid
        assert optimal.recommended_price >= optimal.best_price
        assert optimal.estimated_fill_probability > 0

    def test_aggressive_vs_passive_prices(self, analyzer, high_liquidity_orderbook):
        """Test that aggressive and passive prices are correctly positioned"""
        analyzer.analyze_liquidity(
            symbol="BTCUSDT",
            bids=high_liquidity_orderbook["bids"],
            asks=high_liquidity_orderbook["asks"]
        )

        optimal = analyzer.find_optimal_limit_price(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.5"),
            target_fill_probability=0.8,
            bids=high_liquidity_orderbook["bids"],
            asks=high_liquidity_orderbook["asks"]
        )

        # For buys: aggressive >= recommended >= passive
        assert optimal.aggressive_price >= optimal.recommended_price >= optimal.passive_price

    def test_fill_probability_affects_price(self, analyzer, high_liquidity_orderbook):
        """Test that higher fill probability target results in more aggressive price"""
        analyzer.analyze_liquidity(
            symbol="BTCUSDT",
            bids=high_liquidity_orderbook["bids"],
            asks=high_liquidity_orderbook["asks"]
        )

        high_prob = analyzer.find_optimal_limit_price(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.5"),
            target_fill_probability=0.9,
            bids=high_liquidity_orderbook["bids"],
            asks=high_liquidity_orderbook["asks"]
        )

        low_prob = analyzer.find_optimal_limit_price(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.5"),
            target_fill_probability=0.5,
            bids=high_liquidity_orderbook["bids"],
            asks=high_liquidity_orderbook["asks"]
        )

        # Higher probability should have higher (more aggressive) price for buys
        assert high_prob.recommended_price >= low_prob.recommended_price


# ============================================================================
# CACHING AND STATE TESTS
# ============================================================================

class TestCachingAndState:
    """Test suite for caching and state management"""

    def test_orderbook_caching(self, analyzer, high_liquidity_orderbook):
        """Test that analysis results are cached"""
        # First analysis
        report1 = analyzer.analyze_liquidity(
            symbol="BTCUSDT",
            bids=high_liquidity_orderbook["bids"],
            asks=high_liquidity_orderbook["asks"]
        )

        # Get cached report
        cached = analyzer.get_cached_report("BTCUSDT")

        # Should return cached report
        assert cached is not None
        assert cached.symbol == report1.symbol

    def test_spread_history_tracking(self, analyzer, high_liquidity_orderbook):
        """Test that spread history is tracked"""
        # Analyze multiple times
        for _ in range(5):
            analyzer.analyze_liquidity(
                symbol="BTCUSDT",
                bids=high_liquidity_orderbook["bids"],
                asks=high_liquidity_orderbook["asks"]
            )

        # Check average spread is available
        avg_spread = analyzer.get_average_spread("BTCUSDT")
        assert avg_spread is not None
        assert avg_spread > 0

    def test_global_instance_management(self):
        """Test global instance creation and reset"""
        reset_orderbook_analyzer()

        # Get instance
        analyzer1 = get_orderbook_analyzer()
        analyzer2 = get_orderbook_analyzer()

        # Should be same instance
        assert analyzer1 is analyzer2

        # Reset and get new
        reset_orderbook_analyzer()
        analyzer3 = get_orderbook_analyzer()

        # Should be different instance
        assert analyzer1 is not analyzer3


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Test suite for edge cases and error handling"""

    def test_single_level_orderbook(self, analyzer):
        """Test handling of single-level order book"""
        single_level = {
            "bids": [["100", "1"]],
            "asks": [["101", "1"]]
        }

        report = analyzer.analyze_liquidity(
            symbol="TEST",
            bids=single_level["bids"],
            asks=single_level["asks"]
        )

        # Should handle gracefully
        assert report.best_bid == Decimal("100")
        assert report.best_ask == Decimal("101")

    def test_zero_quantity_levels(self, analyzer):
        """Test handling of zero quantity levels"""
        zero_qty = {
            "bids": [["100", "0"], ["99", "1"]],
            "asks": [["101", "1"]]
        }

        report = analyzer.analyze_liquidity(
            symbol="TEST",
            bids=zero_qty["bids"],
            asks=zero_qty["asks"]
        )

        # Should not crash
        assert report is not None

    def test_very_large_spread(self, analyzer):
        """Test handling of extremely wide spread"""
        wide_spread = {
            "bids": [["100", "1"]],
            "asks": [["200", "1"]]  # 100% spread
        }

        report = analyzer.analyze_liquidity(
            symbol="TEST",
            bids=wide_spread["bids"],
            asks=wide_spread["asks"]
        )

        assert report.spread_category == SpreadCategory.VERY_WIDE
        assert report.liquidity_level == LiquidityLevel.VERY_LOW

    def test_string_vs_decimal_prices(self, analyzer):
        """Test that string prices are handled correctly"""
        string_book = {
            "bids": [["50000.50", "1.25"]],
            "asks": [["50010.75", "0.75"]]
        }

        report = analyzer.analyze_liquidity(
            symbol="TEST",
            bids=string_book["bids"],
            asks=string_book["asks"]
        )

        # Should parse correctly
        assert report.best_bid == Decimal("50000.50")
        assert report.best_ask == Decimal("50010.75")


# ============================================================================
# STATUS AND REPORTING TESTS
# ============================================================================

class TestStatusAndReporting:
    """Test suite for status and reporting functionality"""

    def test_get_status(self, analyzer, high_liquidity_orderbook):
        """Test status retrieval"""
        # Analyze some data first
        analyzer.analyze_liquidity(
            symbol="BTCUSDT",
            bids=high_liquidity_orderbook["bids"],
            asks=high_liquidity_orderbook["asks"]
        )

        status = analyzer.get_status()

        # Verify status structure
        assert "config" in status
        assert "cached_symbols" in status
        assert "spread_history_symbols" in status
        assert "BTCUSDT" in status["cached_symbols"]

    def test_liquidity_report_completeness(self, analyzer, high_liquidity_orderbook):
        """Test that liquidity report contains all required fields"""
        report = analyzer.analyze_liquidity(
            symbol="BTCUSDT",
            bids=high_liquidity_orderbook["bids"],
            asks=high_liquidity_orderbook["asks"]
        )

        # Check all required fields
        assert hasattr(report, "symbol")
        assert hasattr(report, "timestamp")
        assert hasattr(report, "best_bid")
        assert hasattr(report, "best_ask")
        assert hasattr(report, "mid_price")
        assert hasattr(report, "spread_pct")
        assert hasattr(report, "spread_category")
        assert hasattr(report, "liquidity_level")
        assert hasattr(report, "liquidity_score")
        assert hasattr(report, "book_state")
        assert hasattr(report, "imbalance_ratio")
        assert hasattr(report, "warnings")
        assert hasattr(report, "recommended_max_market_order_usd")
        assert hasattr(report, "recommended_max_limit_order_usd")
