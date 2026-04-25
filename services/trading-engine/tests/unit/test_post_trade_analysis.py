"""
Unit Tests for Post-Trade Analysis Module (Phase 4.3)
Purpose: Comprehensive test coverage for post-trade analysis functionality

Test Categories:
1. Trade Cost Analysis - slippage calculations, fee analysis
2. Execution Quality Metrics - implementation shortfall, quality scoring
3. Trade Classification - market conditions, liquidity assessment
4. Improvement Recommendations - recommendation generation
5. Report Generation - daily summaries, weekly comparisons
6. Edge Cases - empty data, extreme values

Author: Backend Developer Agent
Date: 2025-12-12
Target Coverage: >80%
"""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import math

# Import the modules under test
from app.analytics.post_trade_analysis import (
    # Enums
    ExecutionStyle,
    MarketConditionType,
    LiquidityLevel,
    TradingSession,
    ExecutionQualityGrade,
    BenchmarkType,
    # Data Models
    SlippageBreakdown,
    ExecutionQuality,
    TradeClassification,
    TradeExecutionData,
    PostTradeAnalysisResult,
    DailySummary,
    ImprovementRecommendation,
    # Main classes
    PostTradeAnalyzer,
    get_post_trade_analyzer,
    reset_post_trade_analyzer,
)

from app.analytics.trade_report import (
    # Enums
    ReportFormat,
    ReportPeriod,
    TrendDirection,
    # Data Models
    IndividualTradeReport,
    WeeklyComparisonReport,
    ExecutionTrend,
    # Main classes
    TradeReportGenerator,
    get_trade_report_generator,
    reset_trade_report_generator,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def analyzer():
    """Create a fresh PostTradeAnalyzer for each test"""
    reset_post_trade_analyzer()
    return get_post_trade_analyzer()


@pytest.fixture
def report_generator():
    """Create a fresh TradeReportGenerator for each test"""
    reset_post_trade_analyzer()
    reset_trade_report_generator()
    return get_trade_report_generator()


@pytest.fixture
def sample_trade_data():
    """Create sample trade execution data"""
    return TradeExecutionData(
        trade_id="tr_test_001",
        symbol="BTCUSDT",
        side="BUY",
        size=1.5,
        expected_price=43000.00,
        execution_price=43020.50,
        fees=12.90,
        order_type="MARKET",
        decision_timestamp=datetime(2025, 12, 12, 10, 0, 0, tzinfo=timezone.utc),
        execution_timestamp=datetime(2025, 12, 12, 10, 0, 0, 500000, tzinfo=timezone.utc),
        strategy="momentum",
        benchmark_prices={"vwap": 43010.00, "twap": 43008.50},
        market_data={
            "spread_bps": 5.0,
            "volatility": 0.02,
            "avg_volume": 1000000,
            "price_change_1h": 0.01,
        },
    )


@pytest.fixture
def sample_sell_trade_data():
    """Create sample SELL trade execution data"""
    return TradeExecutionData(
        trade_id="tr_test_002",
        symbol="ETHUSDT",
        side="SELL",
        size=10.0,
        expected_price=2250.00,
        execution_price=2248.50,
        fees=5.62,
        order_type="LIMIT",
        decision_timestamp=datetime(2025, 12, 12, 14, 0, 0, tzinfo=timezone.utc),
        execution_timestamp=datetime(2025, 12, 12, 14, 0, 30, tzinfo=timezone.utc),
        strategy="mean_reversion",
        benchmark_prices={"vwap": 2249.00},
        market_data={
            "spread_bps": 3.0,
            "volatility": 0.015,
            "avg_volume": 500000,
        },
    )


@pytest.fixture
def multiple_trade_data(sample_trade_data, sample_sell_trade_data):
    """Create multiple sample trades for aggregate testing"""
    trades = [sample_trade_data, sample_sell_trade_data]

    # Add more trades with varying quality
    for i in range(3, 11):
        slippage_factor = (i - 5) * 2  # Varying slippage
        trades.append(TradeExecutionData(
            trade_id=f"tr_test_{i:03d}",
            symbol="BTCUSDT" if i % 2 == 0 else "ETHUSDT",
            side="BUY" if i % 2 == 0 else "SELL",
            size=float(i) * 0.5,
            expected_price=43000.00 if i % 2 == 0 else 2250.00,
            execution_price=(43000.00 + slippage_factor) if i % 2 == 0 else (2250.00 - slippage_factor * 0.05),
            fees=float(i) * 1.5,
            order_type="MARKET" if i < 6 else "LIMIT",
            strategy="momentum" if i < 5 else "mean_reversion",
            market_data={
                "spread_bps": 3.0 + i * 0.5,
                "volatility": 0.01 + i * 0.002,
                "avg_volume": 1000000,
            },
        ))

    return trades


# =============================================================================
# TEST CLASS: SLIPPAGE BREAKDOWN
# =============================================================================

class TestSlippageBreakdown:
    """Tests for slippage calculation and breakdown"""

    def test_slippage_breakdown_creation(self):
        """Test SlippageBreakdown dataclass creation"""
        breakdown = SlippageBreakdown(
            market_impact=15.00,
            spread_cost=5.00,
            timing_cost=0.50,
            total_slippage=20.50,
            slippage_bps=4.77,
        )

        assert breakdown.market_impact == 15.00
        assert breakdown.spread_cost == 5.00
        assert breakdown.timing_cost == 0.50
        assert breakdown.total_slippage == 20.50
        assert breakdown.slippage_bps == 4.77

    def test_slippage_breakdown_to_dict(self):
        """Test SlippageBreakdown conversion to dictionary"""
        breakdown = SlippageBreakdown(
            market_impact=15.00,
            spread_cost=5.00,
            timing_cost=0.50,
            total_slippage=20.50,
            slippage_bps=4.77,
        )

        result = breakdown.to_dict()

        assert isinstance(result, dict)
        assert "market_impact" in result
        assert "spread_cost" in result
        assert "total_slippage" in result
        assert result["slippage_bps"] == 4.77


# =============================================================================
# TEST CLASS: TRADE COST ANALYSIS
# =============================================================================

class TestTradeCostAnalysis:
    """Tests for trade cost calculations"""

    def test_buy_trade_positive_slippage(self, analyzer, sample_trade_data):
        """Test slippage calculation for BUY trade with adverse price movement"""
        result = analyzer.analyze_trade(sample_trade_data)

        # BUY at higher price = positive slippage (bad)
        assert result.slippage.total_slippage > 0
        assert result.slippage.slippage_bps > 0

        # Check total cost includes fees
        assert result.total_cost == result.slippage.total_slippage + result.fees
        assert result.cost_bps > 0

    def test_buy_trade_price_improvement(self, analyzer):
        """Test slippage calculation for BUY trade with price improvement"""
        trade = TradeExecutionData(
            trade_id="tr_improvement_001",
            symbol="BTCUSDT",
            side="BUY",
            size=1.0,
            expected_price=43000.00,
            execution_price=42990.00,  # Better than expected
            fees=10.00,
            order_type="LIMIT",
            strategy="test",
        )

        result = analyzer.analyze_trade(trade)

        # BUY at lower price = negative slippage (price improvement)
        assert result.slippage.total_slippage < 0
        assert result.slippage.slippage_bps < 0

    def test_sell_trade_slippage(self, analyzer, sample_sell_trade_data):
        """Test slippage calculation for SELL trade"""
        result = analyzer.analyze_trade(sample_sell_trade_data)

        # SELL at lower price = positive slippage (bad)
        assert result.slippage.total_slippage > 0
        assert result.slippage.slippage_bps > 0

    def test_sell_trade_price_improvement(self, analyzer):
        """Test slippage calculation for SELL trade with price improvement"""
        trade = TradeExecutionData(
            trade_id="tr_sell_improvement",
            symbol="ETHUSDT",
            side="SELL",
            size=5.0,
            expected_price=2250.00,
            execution_price=2255.00,  # Better than expected
            fees=5.00,
            order_type="LIMIT",
            strategy="test",
        )

        result = analyzer.analyze_trade(trade)

        # SELL at higher price = negative slippage (price improvement)
        assert result.slippage.total_slippage < 0

    def test_slippage_components(self, analyzer, sample_trade_data):
        """Test that slippage components sum correctly"""
        result = analyzer.analyze_trade(sample_trade_data)

        # Components should be non-negative for positive total slippage
        if result.slippage.total_slippage > 0:
            # Market impact, spread, and timing should be >= 0
            assert result.slippage.market_impact >= 0
            assert result.slippage.spread_cost >= 0

    def test_cost_bps_calculation(self, analyzer, sample_trade_data):
        """Test cost in basis points calculation"""
        result = analyzer.analyze_trade(sample_trade_data)

        # Calculate expected cost in bps
        notional = sample_trade_data.size * sample_trade_data.execution_price
        expected_bps = (result.total_cost / notional) * 10000

        assert abs(result.cost_bps - expected_bps) < 0.01

    def test_zero_slippage(self, analyzer):
        """Test when execution matches expected price exactly"""
        trade = TradeExecutionData(
            trade_id="tr_zero_slip",
            symbol="BTCUSDT",
            side="BUY",
            size=1.0,
            expected_price=43000.00,
            execution_price=43000.00,  # Exact match
            fees=10.00,
            order_type="LIMIT",
            strategy="test",
        )

        result = analyzer.analyze_trade(trade)

        assert result.slippage.total_slippage == 0
        assert result.slippage.slippage_bps == 0
        # Total cost should be just fees
        assert result.total_cost == trade.fees


# =============================================================================
# TEST CLASS: EXECUTION QUALITY
# =============================================================================

class TestExecutionQuality:
    """Tests for execution quality metrics"""

    def test_quality_score_range(self, analyzer, sample_trade_data):
        """Test that quality score is within valid range"""
        result = analyzer.analyze_trade(sample_trade_data)

        assert 0 <= result.execution_quality.quality_score <= 100

    def test_quality_grade_mapping(self, analyzer):
        """Test quality grade assignment based on score"""
        # Test excellent (90+)
        trade = TradeExecutionData(
            trade_id="tr_excellent",
            symbol="BTCUSDT",
            side="BUY",
            size=1.0,
            expected_price=43000.00,
            execution_price=42998.00,  # Very small slippage
            fees=5.00,
            order_type="LIMIT",
            strategy="test",
            market_data={"fill_rate": 100},
        )

        result = analyzer.analyze_trade(trade)

        # Should be good or excellent for minimal slippage
        assert result.execution_quality.quality_grade in [
            ExecutionQualityGrade.EXCELLENT,
            ExecutionQualityGrade.GOOD,
        ]

    def test_implementation_shortfall(self, analyzer, sample_trade_data):
        """Test implementation shortfall calculation"""
        result = analyzer.analyze_trade(sample_trade_data)

        # Implementation shortfall should be calculated
        assert isinstance(result.execution_quality.implementation_shortfall, float)
        assert isinstance(result.execution_quality.implementation_shortfall_bps, float)

    def test_fill_rate(self, analyzer, sample_trade_data):
        """Test fill rate handling"""
        result = analyzer.analyze_trade(sample_trade_data)

        # Default fill rate should be 100%
        assert result.execution_quality.fill_rate == 100.0

    def test_fill_rate_partial(self, analyzer):
        """Test partial fill rate"""
        trade = TradeExecutionData(
            trade_id="tr_partial",
            symbol="BTCUSDT",
            side="BUY",
            size=1.0,
            expected_price=43000.00,
            execution_price=43000.00,
            fees=10.00,
            order_type="LIMIT",
            strategy="test",
            market_data={"fill_rate": 75.0},
        )

        result = analyzer.analyze_trade(trade)

        assert result.execution_quality.fill_rate == 75.0

    def test_time_to_completion(self, analyzer, sample_trade_data):
        """Test time to completion calculation"""
        result = analyzer.analyze_trade(sample_trade_data)

        # Decision to execution was 0.5 seconds
        expected_time = 0.5
        assert abs(result.execution_quality.time_to_completion - expected_time) < 0.1

    def test_benchmark_comparisons(self, analyzer, sample_trade_data):
        """Test benchmark price comparisons"""
        result = analyzer.analyze_trade(sample_trade_data)

        # Should have VWAP and TWAP comparisons
        assert "vwap" in result.execution_quality.benchmark_comparisons
        assert "twap" in result.execution_quality.benchmark_comparisons

    def test_poor_execution_low_score(self, analyzer):
        """Test that poor executions get low scores"""
        trade = TradeExecutionData(
            trade_id="tr_poor",
            symbol="BTCUSDT",
            side="BUY",
            size=1.0,
            expected_price=43000.00,
            execution_price=43100.00,  # 0.23% slippage - high
            fees=50.00,
            order_type="MARKET",
            strategy="test",
            decision_timestamp=datetime(2025, 12, 12, 10, 0, 0, tzinfo=timezone.utc),
            execution_timestamp=datetime(2025, 12, 12, 10, 5, 0, tzinfo=timezone.utc),  # 5 min delay
        )

        result = analyzer.analyze_trade(trade)

        # Should have lower score
        assert result.execution_quality.quality_score < 70


# =============================================================================
# TEST CLASS: TRADE CLASSIFICATION
# =============================================================================

class TestTradeClassification:
    """Tests for trade classification"""

    def test_aggressive_style_market_order(self, analyzer, sample_trade_data):
        """Test classification of market orders as aggressive"""
        result = analyzer.analyze_trade(sample_trade_data)

        assert result.classification.execution_style == ExecutionStyle.AGGRESSIVE

    def test_passive_style_limit_order(self, analyzer, sample_sell_trade_data):
        """Test classification of limit orders as passive"""
        result = analyzer.analyze_trade(sample_sell_trade_data)

        assert result.classification.execution_style == ExecutionStyle.PASSIVE

    def test_market_condition_stable(self, analyzer, sample_trade_data):
        """Test stable market condition classification"""
        result = analyzer.analyze_trade(sample_trade_data)

        # With volatility 0.02 and small price change, should be stable or trending
        assert result.classification.market_condition in [
            MarketConditionType.STABLE,
            MarketConditionType.TRENDING_UP,
        ]

    def test_market_condition_volatile(self, analyzer):
        """Test volatile market condition classification"""
        trade = TradeExecutionData(
            trade_id="tr_volatile",
            symbol="BTCUSDT",
            side="BUY",
            size=1.0,
            expected_price=43000.00,
            execution_price=43020.00,
            fees=10.00,
            order_type="MARKET",
            strategy="test",
            market_data={"volatility": 0.08},  # High volatility
        )

        result = analyzer.analyze_trade(trade)

        assert result.classification.market_condition == MarketConditionType.VOLATILE

    def test_liquidity_level_deep(self, analyzer):
        """Test deep liquidity classification"""
        trade = TradeExecutionData(
            trade_id="tr_deep_liq",
            symbol="BTCUSDT",
            side="BUY",
            size=1.0,
            expected_price=43000.00,
            execution_price=43000.00,
            fees=10.00,
            order_type="MARKET",
            strategy="test",
            market_data={
                "spread_bps": 2.0,  # Tight spread
                "orderbook_depth_ratio": 0.9,  # Deep book
            },
        )

        result = analyzer.analyze_trade(trade)

        assert result.classification.liquidity_level == LiquidityLevel.DEEP

    def test_liquidity_level_thin(self, analyzer):
        """Test thin liquidity classification"""
        trade = TradeExecutionData(
            trade_id="tr_thin_liq",
            symbol="BTCUSDT",
            side="BUY",
            size=1.0,
            expected_price=43000.00,
            execution_price=43050.00,
            fees=10.00,
            order_type="MARKET",
            strategy="test",
            market_data={
                "spread_bps": 15.0,  # Wide spread
                "orderbook_depth_ratio": 0.2,  # Thin book
            },
        )

        result = analyzer.analyze_trade(trade)

        assert result.classification.liquidity_level == LiquidityLevel.THIN

    def test_trading_session_asia(self, analyzer):
        """Test Asian session classification"""
        trade = TradeExecutionData(
            trade_id="tr_asia",
            symbol="BTCUSDT",
            side="BUY",
            size=1.0,
            expected_price=43000.00,
            execution_price=43000.00,
            fees=10.00,
            order_type="MARKET",
            strategy="test",
            execution_timestamp=datetime(2025, 12, 12, 3, 0, 0, tzinfo=timezone.utc),  # 3 AM UTC
        )

        result = analyzer.analyze_trade(trade)

        assert result.classification.trading_session == TradingSession.ASIA

    def test_trading_session_europe(self, analyzer):
        """Test European session classification"""
        trade = TradeExecutionData(
            trade_id="tr_europe",
            symbol="BTCUSDT",
            side="BUY",
            size=1.0,
            expected_price=43000.00,
            execution_price=43000.00,
            fees=10.00,
            order_type="MARKET",
            strategy="test",
            execution_timestamp=datetime(2025, 12, 12, 12, 0, 0, tzinfo=timezone.utc),  # 12 PM UTC
        )

        result = analyzer.analyze_trade(trade)

        assert result.classification.trading_session == TradingSession.EUROPE

    def test_trading_session_us(self, analyzer):
        """Test US session classification"""
        trade = TradeExecutionData(
            trade_id="tr_us",
            symbol="BTCUSDT",
            side="BUY",
            size=1.0,
            expected_price=43000.00,
            execution_price=43000.00,
            fees=10.00,
            order_type="MARKET",
            strategy="test",
            execution_timestamp=datetime(2025, 12, 12, 20, 0, 0, tzinfo=timezone.utc),  # 8 PM UTC
        )

        result = analyzer.analyze_trade(trade)

        assert result.classification.trading_session == TradingSession.US


# =============================================================================
# TEST CLASS: IMPROVEMENT RECOMMENDATIONS
# =============================================================================

class TestImprovementRecommendations:
    """Tests for improvement recommendation generation"""

    def test_recommendations_for_high_slippage(self, analyzer):
        """Test recommendations generated for high slippage trades"""
        trade = TradeExecutionData(
            trade_id="tr_high_slip",
            symbol="BTCUSDT",
            side="BUY",
            size=1.0,
            expected_price=43000.00,
            execution_price=43100.00,  # ~23 bps slippage
            fees=10.00,
            order_type="MARKET",
            strategy="test",
        )

        result = analyzer.analyze_trade(trade)

        # Should have recommendations
        assert len(result.recommendations) > 0
        # Should mention slippage or limit orders
        rec_text = " ".join(result.recommendations).lower()
        assert "slippage" in rec_text or "limit" in rec_text

    def test_recommendations_for_thin_liquidity(self, analyzer):
        """Test recommendations for trades in thin liquidity"""
        trade = TradeExecutionData(
            trade_id="tr_thin_rec",
            symbol="BTCUSDT",
            side="BUY",
            size=1.0,
            expected_price=43000.00,
            execution_price=43020.00,
            fees=10.00,
            order_type="MARKET",
            strategy="test",
            market_data={
                "spread_bps": 15.0,
                "orderbook_depth_ratio": 0.2,
            },
        )

        result = analyzer.analyze_trade(trade)

        # Should mention liquidity
        rec_text = " ".join(result.recommendations).lower()
        assert "liquidity" in rec_text

    def test_positive_reinforcement_good_execution(self, analyzer):
        """Test positive recommendations for good executions"""
        trade = TradeExecutionData(
            trade_id="tr_good",
            symbol="BTCUSDT",
            side="BUY",
            size=1.0,
            expected_price=43000.00,
            execution_price=42998.00,  # Slight improvement
            fees=5.00,
            order_type="LIMIT",
            strategy="test",
            decision_timestamp=datetime(2025, 12, 12, 10, 0, 0, tzinfo=timezone.utc),
            execution_timestamp=datetime(2025, 12, 12, 10, 0, 1, tzinfo=timezone.utc),
            market_data={"fill_rate": 100},
        )

        result = analyzer.analyze_trade(trade)

        # Should have positive recommendation if score is high
        if result.execution_quality.quality_score >= 85:
            rec_text = " ".join(result.recommendations).lower()
            assert "excellent" in rec_text or "good" in rec_text or "working well" in rec_text

    def test_global_improvement_recommendations(self, analyzer, multiple_trade_data):
        """Test global improvement recommendations after multiple trades"""
        # Analyze multiple trades
        for trade in multiple_trade_data:
            analyzer.analyze_trade(trade)

        # Get global recommendations
        recommendations = analyzer.get_improvement_recommendations()

        # Should generate some recommendations
        assert isinstance(recommendations, list)

    def test_strategy_specific_recommendations(self, analyzer, multiple_trade_data):
        """Test recommendations specific to strategies"""
        # Analyze multiple trades
        for trade in multiple_trade_data:
            analyzer.analyze_trade(trade)

        recommendations = analyzer.get_improvement_recommendations()

        # Check for strategy-specific recommendations
        for rec in recommendations:
            assert hasattr(rec, "applicable_to")
            assert hasattr(rec, "priority")
            assert hasattr(rec, "expected_savings_bps")


# =============================================================================
# TEST CLASS: AGGREGATION AND REPORTING
# =============================================================================

class TestAggregationAndReporting:
    """Tests for aggregation and reporting functions"""

    def test_get_analysis_by_id(self, analyzer, sample_trade_data):
        """Test retrieving analysis by trade ID"""
        analyzer.analyze_trade(sample_trade_data)

        result = analyzer.get_analysis(sample_trade_data.trade_id)

        assert result is not None
        assert result.trade_id == sample_trade_data.trade_id

    def test_get_analysis_not_found(self, analyzer):
        """Test retrieving non-existent analysis"""
        result = analyzer.get_analysis("nonexistent_trade_id")

        assert result is None

    def test_get_daily_summary(self, analyzer, multiple_trade_data):
        """Test daily summary generation"""
        # Set all trades to same date
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        for trade in multiple_trade_data:
            analyzer.analyze_trade(trade)

        summary = analyzer.get_daily_summary(today)

        assert isinstance(summary, DailySummary)
        assert summary.date == today
        assert summary.total_trades == len(multiple_trade_data)

    def test_daily_summary_empty_date(self, analyzer):
        """Test daily summary for date with no trades"""
        summary = analyzer.get_daily_summary("2020-01-01")

        assert summary.total_trades == 0
        assert len(summary.recommendations) > 0  # Should have a message

    def test_get_worst_executions(self, analyzer, multiple_trade_data):
        """Test retrieving worst executions"""
        for trade in multiple_trade_data:
            analyzer.analyze_trade(trade)

        worst = analyzer.get_worst_executions(limit=5)

        assert len(worst) <= 5
        # Should be sorted by score ascending
        scores = [w.execution_quality.quality_score for w in worst]
        assert scores == sorted(scores)

    def test_get_best_executions(self, analyzer, multiple_trade_data):
        """Test retrieving best executions"""
        for trade in multiple_trade_data:
            analyzer.analyze_trade(trade)

        best = analyzer.get_best_executions(limit=5)

        assert len(best) <= 5
        # Should be sorted by score descending
        scores = [b.execution_quality.quality_score for b in best]
        assert scores == sorted(scores, reverse=True)

    def test_get_by_strategy(self, analyzer, multiple_trade_data):
        """Test filtering analyses by strategy"""
        for trade in multiple_trade_data:
            analyzer.analyze_trade(trade)

        momentum_trades = analyzer.get_by_strategy("momentum")

        assert all(t.strategy == "momentum" for t in momentum_trades)

    def test_get_by_symbol(self, analyzer, multiple_trade_data):
        """Test filtering analyses by symbol"""
        for trade in multiple_trade_data:
            analyzer.analyze_trade(trade)

        btc_trades = analyzer.get_by_symbol("BTCUSDT")

        assert all(t.symbol == "BTCUSDT" for t in btc_trades)

    def test_get_strategy_stats(self, analyzer, multiple_trade_data):
        """Test strategy statistics aggregation"""
        for trade in multiple_trade_data:
            analyzer.analyze_trade(trade)

        stats = analyzer.get_strategy_stats("momentum")

        assert "trade_count" in stats
        assert "avg_slippage_bps" in stats
        assert "avg_quality_score" in stats
        assert stats["trade_count"] > 0

    def test_get_symbol_stats(self, analyzer, multiple_trade_data):
        """Test symbol statistics aggregation"""
        for trade in multiple_trade_data:
            analyzer.analyze_trade(trade)

        stats = analyzer.get_symbol_stats("BTCUSDT")

        assert "trade_count" in stats
        assert "avg_slippage_bps" in stats
        assert stats["trade_count"] > 0

    def test_get_summary(self, analyzer, multiple_trade_data):
        """Test overall summary generation"""
        for trade in multiple_trade_data:
            analyzer.analyze_trade(trade)

        summary = analyzer.get_summary()

        assert "total_analyses" in summary
        assert summary["total_analyses"] == len(multiple_trade_data)
        assert "quality_distribution" in summary


# =============================================================================
# TEST CLASS: TRADE REPORT GENERATOR
# =============================================================================

class TestTradeReportGenerator:
    """Tests for TradeReportGenerator"""

    def test_individual_report_generation(self, report_generator, analyzer, sample_trade_data):
        """Test individual trade report generation"""
        analyzer.analyze_trade(sample_trade_data)

        report = report_generator.generate_individual_report(sample_trade_data.trade_id)

        assert report is not None
        assert report.trade_id == sample_trade_data.trade_id
        assert "summary" in report.to_dict()
        assert "cost_analysis" in report.to_dict()
        assert "quality_analysis" in report.to_dict()

    def test_individual_report_text_format(self, report_generator, analyzer, sample_trade_data):
        """Test individual report text generation"""
        analyzer.analyze_trade(sample_trade_data)

        report = report_generator.generate_individual_report(sample_trade_data.trade_id)
        text = report.to_text()

        assert "TRADE EXECUTION REPORT" in text
        assert sample_trade_data.trade_id in text
        assert "COST ANALYSIS" in text
        assert "EXECUTION QUALITY" in text

    def test_individual_report_not_found(self, report_generator):
        """Test individual report for non-existent trade"""
        report = report_generator.generate_individual_report("nonexistent")

        assert report is None

    def test_weekly_comparison_report(self, report_generator, analyzer, multiple_trade_data):
        """Test weekly comparison report generation"""
        for trade in multiple_trade_data:
            analyzer.analyze_trade(trade)

        report = report_generator.generate_weekly_comparison(week_offset=0)

        assert isinstance(report, WeeklyComparisonReport)
        assert report.week_start is not None
        assert report.week_end is not None
        assert report.current_week is not None

    def test_best_executions_report(self, report_generator, analyzer, multiple_trade_data):
        """Test best executions report generation"""
        for trade in multiple_trade_data:
            analyzer.analyze_trade(trade)

        report = report_generator.get_best_executions_report(limit=5)

        assert report["report_type"] == "best_executions"
        assert len(report["executions"]) <= 5
        assert "common_patterns" in report

    def test_worst_executions_report(self, report_generator, analyzer, multiple_trade_data):
        """Test worst executions report generation"""
        for trade in multiple_trade_data:
            analyzer.analyze_trade(trade)

        report = report_generator.get_worst_executions_report(limit=5)

        assert report["report_type"] == "worst_executions"
        assert len(report["executions"]) <= 5


# =============================================================================
# TEST CLASS: EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions"""

    def test_very_small_trade(self, analyzer):
        """Test analysis of very small trade"""
        trade = TradeExecutionData(
            trade_id="tr_tiny",
            symbol="BTCUSDT",
            side="BUY",
            size=0.0001,  # Tiny size
            expected_price=43000.00,
            execution_price=43000.50,
            fees=0.01,
            order_type="MARKET",
            strategy="test",
        )

        result = analyzer.analyze_trade(trade)

        assert result is not None
        assert result.trade_id == "tr_tiny"

    def test_very_large_trade(self, analyzer):
        """Test analysis of very large trade"""
        trade = TradeExecutionData(
            trade_id="tr_huge",
            symbol="BTCUSDT",
            side="BUY",
            size=1000.0,  # Large size
            expected_price=43000.00,
            execution_price=43100.00,
            fees=1000.00,
            order_type="MARKET",
            strategy="test",
            market_data={"avg_volume": 500000},  # Large relative to volume
        )

        result = analyzer.analyze_trade(trade)

        assert result is not None
        # Should have high market impact
        assert result.slippage.market_impact > 0

    def test_extreme_slippage(self, analyzer):
        """Test analysis with extreme slippage"""
        trade = TradeExecutionData(
            trade_id="tr_extreme",
            symbol="BTCUSDT",
            side="BUY",
            size=1.0,
            expected_price=43000.00,
            execution_price=45000.00,  # ~4.6% slippage
            fees=50.00,
            order_type="MARKET",
            strategy="test",
        )

        result = analyzer.analyze_trade(trade)

        assert result is not None
        assert result.execution_quality.quality_grade in [
            ExecutionQualityGrade.POOR,
            ExecutionQualityGrade.VERY_POOR,
        ]

    def test_zero_fees(self, analyzer):
        """Test analysis with zero fees"""
        trade = TradeExecutionData(
            trade_id="tr_no_fees",
            symbol="BTCUSDT",
            side="BUY",
            size=1.0,
            expected_price=43000.00,
            execution_price=43010.00,
            fees=0.0,
            order_type="MARKET",
            strategy="test",
        )

        result = analyzer.analyze_trade(trade)

        assert result.fees == 0.0
        assert result.total_cost == result.slippage.total_slippage

    def test_reset_analyzer(self, analyzer, sample_trade_data):
        """Test analyzer reset functionality"""
        analyzer.analyze_trade(sample_trade_data)

        # Verify trade exists
        assert analyzer.get_analysis(sample_trade_data.trade_id) is not None

        # Reset
        analyzer.reset()

        # Should be empty
        assert analyzer.get_analysis(sample_trade_data.trade_id) is None
        assert analyzer.get_summary()["total_analyses"] == 0

    def test_concurrent_trade_analysis(self, analyzer):
        """Test thread safety of trade analysis"""
        import concurrent.futures

        trades = [
            TradeExecutionData(
                trade_id=f"tr_concurrent_{i}",
                symbol="BTCUSDT",
                side="BUY",
                size=1.0,
                expected_price=43000.00,
                execution_price=43000.00 + i,
                fees=10.00,
                order_type="MARKET",
                strategy="test",
            )
            for i in range(10)
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(analyzer.analyze_trade, t) for t in trades]
            results = [f.result() for f in futures]

        assert len(results) == 10
        assert analyzer.get_summary()["total_analyses"] == 10


# =============================================================================
# TEST CLASS: SINGLETON PATTERN
# =============================================================================

class TestSingletonPattern:
    """Tests for singleton pattern implementation"""

    def test_analyzer_singleton(self):
        """Test that get_post_trade_analyzer returns same instance"""
        reset_post_trade_analyzer()

        analyzer1 = get_post_trade_analyzer()
        analyzer2 = get_post_trade_analyzer()

        assert analyzer1 is analyzer2

    def test_report_generator_singleton(self):
        """Test that get_trade_report_generator returns same instance"""
        reset_trade_report_generator()

        gen1 = get_trade_report_generator()
        gen2 = get_trade_report_generator()

        assert gen1 is gen2

    def test_reset_creates_new_instance(self):
        """Test that reset creates new instance"""
        analyzer1 = get_post_trade_analyzer()

        reset_post_trade_analyzer()

        analyzer2 = get_post_trade_analyzer()

        # Should be different instances
        # (comparing by checking state is reset)
        assert analyzer2.get_summary()["total_analyses"] == 0


# =============================================================================
# TEST CLASS: DATA MODEL CONVERSIONS
# =============================================================================

class TestDataModelConversions:
    """Tests for data model to_dict conversions"""

    def test_post_trade_result_to_dict(self, analyzer, sample_trade_data):
        """Test PostTradeAnalysisResult.to_dict()"""
        result = analyzer.analyze_trade(sample_trade_data)

        result_dict = result.to_dict()

        assert "trade_id" in result_dict
        assert "slippage" in result_dict
        assert "execution_quality" in result_dict
        assert "classification" in result_dict
        assert isinstance(result_dict["slippage"], dict)

    def test_daily_summary_to_dict(self, analyzer, multiple_trade_data):
        """Test DailySummary.to_dict()"""
        for trade in multiple_trade_data:
            analyzer.analyze_trade(trade)

        summary = analyzer.get_daily_summary(datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        summary_dict = summary.to_dict()

        assert "date" in summary_dict
        assert "total_trades" in summary_dict
        assert "by_strategy" in summary_dict
        assert "recommendations" in summary_dict

    def test_improvement_recommendation_to_dict(self):
        """Test ImprovementRecommendation.to_dict()"""
        rec = ImprovementRecommendation(
            category="execution_strategy",
            priority="high",
            recommendation="Use limit orders",
            expected_savings_bps=5.0,
            applicable_to=["momentum"],
            evidence={"avg_slippage": 10.0},
        )

        rec_dict = rec.to_dict()

        assert rec_dict["category"] == "execution_strategy"
        assert rec_dict["priority"] == "high"
        assert rec_dict["expected_savings_bps"] == 5.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
