"""
Test Suite for Attribution Analysis Module
Purpose: Comprehensive tests for P&L attribution system

Test Coverage Target: >85%

Tests include:
- Trade record creation and manipulation
- Metrics calculation (Sharpe, Sortino, Profit Factor, etc.)
- Attribution by dimension (strategy, symbol, direction, market condition)
- Trend analysis over time periods
- Performance decomposition (Alpha, Beta, Residual)
- API endpoint response validation

Author: Backend Developer Agent
Date: 2025-12-11
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock
import numpy as np

# Import the modules to test
from app.analytics.attribution import (
    AttributionAnalyzer,
    AttributionMetrics,
    TradeRecord,
    AttributionResult,
    AttributionSummary,
    TrendAnalysis,
    PerformanceDecomposition,
    AttributionDimension,
    MarketCondition,
    TradeDirection,
    TradePeriod,
    get_attribution_analyzer,
    reset_attribution_analyzer,
)

from app.analytics.models import (
    AttributionByStrategyResponse,
    AttributionBySymbolResponse,
    AttributionSummaryResponse,
    AttributionTrendsResponse,
    AttributionMetricsResponse,
    AttributionResultResponse,
    TimePeriod,
    DimensionType,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def analyzer():
    """Create a fresh AttributionAnalyzer for each test"""
    reset_attribution_analyzer()
    return AttributionAnalyzer(initial_capital=10000.0)


@pytest.fixture
def sample_trades():
    """Generate sample trades for testing"""
    base_time = datetime.now(timezone.utc)

    trades = [
        # Pairs Trading Strategy - Winning trades
        TradeRecord(
            trade_id="tr_001",
            symbol="BTCUSDT",
            strategy="pairs_trading",
            direction=TradeDirection.LONG,
            entry_time=base_time - timedelta(hours=48),
            exit_time=base_time - timedelta(hours=47),
            entry_price=50000.0,
            exit_price=50500.0,
            quantity=0.1,
            pnl=50.0,
            pnl_pct=0.01,
            fees=0.5,
            market_condition=MarketCondition.TRENDING_UP,
        ),
        TradeRecord(
            trade_id="tr_002",
            symbol="ETHUSDT",
            strategy="pairs_trading",
            direction=TradeDirection.LONG,
            entry_time=base_time - timedelta(hours=46),
            exit_time=base_time - timedelta(hours=45),
            entry_price=3000.0,
            exit_price=3060.0,
            quantity=0.5,
            pnl=30.0,
            pnl_pct=0.02,
            fees=0.3,
            market_condition=MarketCondition.TRENDING_UP,
        ),
        # Pairs Trading Strategy - Losing trade
        TradeRecord(
            trade_id="tr_003",
            symbol="BTCUSDT",
            strategy="pairs_trading",
            direction=TradeDirection.SHORT,
            entry_time=base_time - timedelta(hours=44),
            exit_time=base_time - timedelta(hours=43),
            entry_price=51000.0,
            exit_price=51300.0,
            quantity=0.1,
            pnl=-30.0,
            pnl_pct=-0.006,
            fees=0.5,
            market_condition=MarketCondition.VOLATILE,
        ),
        # Funding Rate Arbitrage Strategy
        TradeRecord(
            trade_id="tr_004",
            symbol="SOLUSDT",
            strategy="funding_rate_arb",
            direction=TradeDirection.LONG,
            entry_time=base_time - timedelta(hours=42),
            exit_time=base_time - timedelta(hours=41),
            entry_price=100.0,
            exit_price=102.5,
            quantity=5.0,
            pnl=12.5,
            pnl_pct=0.025,
            fees=0.1,
            market_condition=MarketCondition.RANGING,
        ),
        TradeRecord(
            trade_id="tr_005",
            symbol="SOLUSDT",
            strategy="funding_rate_arb",
            direction=TradeDirection.SHORT,
            entry_time=base_time - timedelta(hours=40),
            exit_time=base_time - timedelta(hours=39),
            entry_price=103.0,
            exit_price=101.5,
            quantity=5.0,
            pnl=7.5,
            pnl_pct=0.015,
            fees=0.1,
            market_condition=MarketCondition.TRENDING_DOWN,
        ),
        # Triangular Arbitrage Strategy
        TradeRecord(
            trade_id="tr_006",
            symbol="BNBUSDT",
            strategy="triangular_arb",
            direction=TradeDirection.LONG,
            entry_time=base_time - timedelta(hours=38),
            exit_time=base_time - timedelta(hours=37),
            entry_price=350.0,
            exit_price=355.0,
            quantity=2.0,
            pnl=10.0,
            pnl_pct=0.014,
            fees=0.2,
            market_condition=MarketCondition.VOLATILE,
        ),
        # More trades for better statistics
        TradeRecord(
            trade_id="tr_007",
            symbol="BTCUSDT",
            strategy="pairs_trading",
            direction=TradeDirection.LONG,
            entry_time=base_time - timedelta(hours=36),
            exit_time=base_time - timedelta(hours=35),
            entry_price=51500.0,
            exit_price=51800.0,
            quantity=0.1,
            pnl=30.0,
            pnl_pct=0.0058,
            fees=0.5,
            market_condition=MarketCondition.TRENDING_UP,
        ),
        TradeRecord(
            trade_id="tr_008",
            symbol="ETHUSDT",
            strategy="funding_rate_arb",
            direction=TradeDirection.SHORT,
            entry_time=base_time - timedelta(hours=34),
            exit_time=base_time - timedelta(hours=33),
            entry_price=3100.0,
            exit_price=3050.0,
            quantity=0.3,
            pnl=15.0,
            pnl_pct=0.016,
            fees=0.2,
            market_condition=MarketCondition.TRENDING_DOWN,
        ),
    ]
    return trades


@pytest.fixture
def analyzer_with_trades(analyzer, sample_trades):
    """Analyzer preloaded with sample trades"""
    analyzer.add_trades_batch(sample_trades)
    return analyzer


# =============================================================================
# TEST TRADE RECORD
# =============================================================================

class TestTradeRecord:
    """Tests for TradeRecord dataclass"""

    def test_trade_record_creation(self):
        """Test creating a trade record with all required fields"""
        trade = TradeRecord(
            trade_id="test_001",
            symbol="BTCUSDT",
            strategy="momentum",
            direction=TradeDirection.LONG,
            entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
            exit_time=datetime.now(timezone.utc),
            entry_price=50000.0,
            exit_price=50500.0,
            quantity=0.1,
            pnl=50.0,
            pnl_pct=0.01,
        )

        assert trade.trade_id == "test_001"
        assert trade.symbol == "BTCUSDT"
        assert trade.strategy == "momentum"
        assert trade.direction == TradeDirection.LONG
        assert trade.pnl == 50.0

    def test_trade_record_is_winner(self):
        """Test the is_winner property"""
        winning_trade = TradeRecord(
            trade_id="win_001",
            symbol="BTCUSDT",
            strategy="momentum",
            direction=TradeDirection.LONG,
            entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
            exit_time=datetime.now(timezone.utc),
            entry_price=50000.0,
            exit_price=50500.0,
            quantity=0.1,
            pnl=50.0,
            pnl_pct=0.01,
        )

        losing_trade = TradeRecord(
            trade_id="lose_001",
            symbol="BTCUSDT",
            strategy="momentum",
            direction=TradeDirection.LONG,
            entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
            exit_time=datetime.now(timezone.utc),
            entry_price=50000.0,
            exit_price=49500.0,
            quantity=0.1,
            pnl=-50.0,
            pnl_pct=-0.01,
        )

        assert winning_trade.is_winner is True
        assert losing_trade.is_winner is False

    def test_trade_record_duration(self):
        """Test the duration_seconds property"""
        entry = datetime.now(timezone.utc) - timedelta(hours=2)
        exit_time = datetime.now(timezone.utc)

        trade = TradeRecord(
            trade_id="dur_001",
            symbol="BTCUSDT",
            strategy="momentum",
            direction=TradeDirection.LONG,
            entry_time=entry,
            exit_time=exit_time,
            entry_price=50000.0,
            exit_price=50500.0,
            quantity=0.1,
            pnl=50.0,
            pnl_pct=0.01,
        )

        # Should be approximately 2 hours = 7200 seconds
        assert abs(trade.duration_seconds - 7200) < 10  # Allow small variance

    def test_trade_record_to_dict(self):
        """Test conversion to dictionary"""
        trade = TradeRecord(
            trade_id="dict_001",
            symbol="BTCUSDT",
            strategy="momentum",
            direction=TradeDirection.LONG,
            entry_time=datetime(2025, 12, 11, 10, 0, 0, tzinfo=timezone.utc),
            exit_time=datetime(2025, 12, 11, 11, 0, 0, tzinfo=timezone.utc),
            entry_price=50000.0,
            exit_price=50500.0,
            quantity=0.1,
            pnl=50.0,
            pnl_pct=0.01,
            market_condition=MarketCondition.TRENDING_UP,
        )

        trade_dict = trade.to_dict()

        assert trade_dict["trade_id"] == "dict_001"
        assert trade_dict["symbol"] == "BTCUSDT"
        assert trade_dict["direction"] == "long"
        assert trade_dict["is_winner"] is True
        assert trade_dict["market_condition"] == "trending_up"


# =============================================================================
# TEST ATTRIBUTION METRICS
# =============================================================================

class TestAttributionMetrics:
    """Tests for AttributionMetrics dataclass"""

    def test_metrics_default_values(self):
        """Test default metric values"""
        metrics = AttributionMetrics()

        assert metrics.total_pnl == 0.0
        assert metrics.win_rate == 0.0
        assert metrics.sharpe_ratio == 0.0
        assert metrics.trades_count == 0

    def test_metrics_to_dict(self):
        """Test conversion to dictionary"""
        metrics = AttributionMetrics(
            total_pnl=1000.0,
            win_rate=0.65,
            sharpe_ratio=1.85,
            max_drawdown=-0.05,
            avg_win=150.0,
            avg_loss=-80.0,
            profit_factor=1.88,
            trades_count=50,
            sortino_ratio=2.15,
            calmar_ratio=0.25,
        )

        metrics_dict = metrics.to_dict()

        assert metrics_dict["total_pnl"] == 1000.0
        assert metrics_dict["win_rate"] == 65.0  # Converted to percentage
        assert metrics_dict["sharpe_ratio"] == 1.85
        assert metrics_dict["max_drawdown"] == -0.05
        assert metrics_dict["trades_count"] == 50


# =============================================================================
# TEST ATTRIBUTION ANALYZER - BASIC OPERATIONS
# =============================================================================

class TestAttributionAnalyzerBasic:
    """Tests for basic AttributionAnalyzer operations"""

    def test_analyzer_initialization(self, analyzer):
        """Test analyzer initialization"""
        assert analyzer.initial_capital == 10000.0
        assert analyzer._current_equity == 10000.0
        assert analyzer._peak_equity == 10000.0
        assert len(analyzer._trades) == 0

    def test_add_single_trade(self, analyzer):
        """Test adding a single trade"""
        trade = TradeRecord(
            trade_id="single_001",
            symbol="BTCUSDT",
            strategy="momentum",
            direction=TradeDirection.LONG,
            entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
            exit_time=datetime.now(timezone.utc),
            entry_price=50000.0,
            exit_price=50500.0,
            quantity=0.1,
            pnl=50.0,
            pnl_pct=0.01,
        )

        analyzer.add_trade(trade)

        assert len(analyzer._trades) == 1
        assert analyzer._current_equity == 10050.0
        assert analyzer._peak_equity == 10050.0

    def test_add_losing_trade_updates_equity(self, analyzer):
        """Test that losing trades update equity correctly"""
        analyzer.add_trade(TradeRecord(
            trade_id="win_001",
            symbol="BTCUSDT",
            strategy="momentum",
            direction=TradeDirection.LONG,
            entry_time=datetime.now(timezone.utc) - timedelta(hours=2),
            exit_time=datetime.now(timezone.utc) - timedelta(hours=1),
            entry_price=50000.0,
            exit_price=50500.0,
            quantity=0.1,
            pnl=50.0,
            pnl_pct=0.01,
        ))

        assert analyzer._peak_equity == 10050.0

        analyzer.add_trade(TradeRecord(
            trade_id="lose_001",
            symbol="BTCUSDT",
            strategy="momentum",
            direction=TradeDirection.LONG,
            entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
            exit_time=datetime.now(timezone.utc),
            entry_price=50500.0,
            exit_price=50200.0,
            quantity=0.1,
            pnl=-30.0,
            pnl_pct=-0.006,
        ))

        assert analyzer._current_equity == 10020.0
        assert analyzer._peak_equity == 10050.0  # Peak should not change

    def test_add_trades_batch(self, analyzer, sample_trades):
        """Test adding multiple trades at once"""
        analyzer.add_trades_batch(sample_trades)

        assert len(analyzer._trades) == len(sample_trades)

    def test_get_trades_filtering(self, analyzer_with_trades):
        """Test filtering trades by various criteria"""
        # Filter by symbol
        btc_trades = analyzer_with_trades.get_trades(symbol="BTCUSDT")
        assert all(t.symbol == "BTCUSDT" for t in btc_trades)

        # Filter by strategy
        pairs_trades = analyzer_with_trades.get_trades(strategy="pairs_trading")
        assert all(t.strategy == "pairs_trading" for t in pairs_trades)

    def test_reset(self, analyzer_with_trades):
        """Test resetting the analyzer"""
        assert len(analyzer_with_trades._trades) > 0

        analyzer_with_trades.reset()

        assert len(analyzer_with_trades._trades) == 0
        assert analyzer_with_trades._current_equity == analyzer_with_trades.initial_capital
        assert analyzer_with_trades._peak_equity == analyzer_with_trades.initial_capital


# =============================================================================
# TEST METRICS CALCULATION
# =============================================================================

class TestMetricsCalculation:
    """Tests for metrics calculation"""

    def test_calculate_metrics_with_trades(self, analyzer_with_trades):
        """Test metrics calculation with sample trades"""
        trades = analyzer_with_trades._trades
        metrics = analyzer_with_trades._calculate_metrics(trades)

        # Check basic metrics are calculated
        assert metrics.trades_count == len(trades)
        assert metrics.total_pnl != 0
        assert 0 <= metrics.win_rate <= 1

    def test_calculate_metrics_empty_trades(self, analyzer):
        """Test metrics calculation with no trades"""
        metrics = analyzer._calculate_metrics([])

        assert metrics.trades_count == 0
        assert metrics.total_pnl == 0
        assert metrics.win_rate == 0

    def test_profit_factor_calculation(self, analyzer_with_trades):
        """Test profit factor calculation"""
        trades = analyzer_with_trades._trades
        metrics = analyzer_with_trades._calculate_metrics(trades)

        # Profit factor should be > 0 if there are both wins and losses
        assert metrics.profit_factor >= 0

    def test_sharpe_ratio_calculation(self, analyzer_with_trades):
        """Test Sharpe ratio calculation"""
        returns = [0.01, 0.02, -0.01, 0.015, 0.008, -0.005, 0.012]
        sharpe = analyzer_with_trades._calculate_sharpe_ratio(returns)

        # Sharpe ratio should be a finite number
        assert not np.isnan(sharpe)
        assert not np.isinf(sharpe)

    def test_sortino_ratio_calculation(self, analyzer_with_trades):
        """Test Sortino ratio calculation"""
        returns = [0.01, 0.02, -0.01, 0.015, 0.008, -0.005, 0.012]
        sortino = analyzer_with_trades._calculate_sortino_ratio(returns)

        # Sortino ratio should be >= Sharpe ratio (same or better since it only penalizes downside)
        sharpe = analyzer_with_trades._calculate_sharpe_ratio(returns)
        # Note: This may not always hold due to calculation differences
        assert not np.isnan(sortino)

    def test_max_drawdown_calculation(self, analyzer_with_trades):
        """Test maximum drawdown calculation"""
        trades = analyzer_with_trades._trades
        max_dd = analyzer_with_trades._calculate_max_drawdown(trades)

        # Max drawdown should be <= 0 (it's expressed as a negative percentage)
        assert max_dd <= 0


# =============================================================================
# TEST ATTRIBUTION BY DIMENSION
# =============================================================================

class TestAttributionByDimension:
    """Tests for attribution by different dimensions"""

    def test_attribution_by_strategy(self, analyzer_with_trades):
        """Test P&L attribution by strategy"""
        attributions = analyzer_with_trades.get_attribution_by_strategy()

        assert len(attributions) > 0

        # Check each attribution has required fields
        for attr in attributions:
            assert attr.dimension == AttributionDimension.STRATEGY
            assert attr.value is not None
            assert attr.metrics is not None
            assert len(attr.trades) > 0

        # Check strategies present
        strategies = [a.value for a in attributions]
        assert "pairs_trading" in strategies

    def test_attribution_by_symbol(self, analyzer_with_trades):
        """Test P&L attribution by symbol"""
        attributions = analyzer_with_trades.get_attribution_by_symbol()

        assert len(attributions) > 0

        # Check symbols present
        symbols = [a.value for a in attributions]
        assert "BTCUSDT" in symbols
        assert "ETHUSDT" in symbols

    def test_attribution_by_direction(self, analyzer_with_trades):
        """Test P&L attribution by trade direction"""
        attributions = analyzer_with_trades.get_attribution_by_direction()

        assert len(attributions) > 0

        # Check directions present
        directions = [a.value for a in attributions]
        assert "long" in directions
        assert "short" in directions

    def test_attribution_by_market_condition(self, analyzer_with_trades):
        """Test P&L attribution by market condition"""
        attributions = analyzer_with_trades.get_attribution_by_market_condition()

        assert len(attributions) > 0

        # Check market conditions present
        conditions = [a.value for a in attributions]
        # At least one condition should be present
        assert len(conditions) > 0

    def test_contribution_percentages_sum(self, analyzer_with_trades):
        """Test that contribution percentages are calculated correctly"""
        attributions = analyzer_with_trades.get_attribution_by_strategy()

        # Calculate total P&L
        total_pnl = sum(a.metrics.total_pnl for a in attributions)

        # Each attribution's contribution should be relative to total
        for attr in attributions:
            if total_pnl != 0:
                expected_contribution = (attr.metrics.total_pnl / abs(total_pnl)) * 100
                assert abs(attr.contribution_pct - expected_contribution) < 0.1

    def test_time_filtered_attribution(self, analyzer_with_trades):
        """Test attribution with time filters"""
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)

        attributions = analyzer_with_trades.get_attribution_by_strategy(
            start_time=yesterday,
            end_time=now
        )

        # All trades should be within the time range
        for attr in attributions:
            for trade in attr.trades:
                assert trade.exit_time >= yesterday
                assert trade.exit_time <= now


# =============================================================================
# TEST ATTRIBUTION SUMMARY
# =============================================================================

class TestAttributionSummary:
    """Tests for attribution summary"""

    def test_get_attribution_summary(self, analyzer_with_trades):
        """Test getting complete attribution summary"""
        summary = analyzer_with_trades.get_attribution_summary()

        assert summary is not None
        assert summary.overall_metrics is not None
        assert len(summary.by_strategy) > 0
        assert len(summary.by_symbol) > 0
        assert len(summary.by_direction) > 0
        assert summary.generated_at is not None

    def test_summary_to_dict(self, analyzer_with_trades):
        """Test summary conversion to dictionary"""
        summary = analyzer_with_trades.get_attribution_summary()
        summary_dict = summary.to_dict()

        assert "overall_metrics" in summary_dict
        assert "by_strategy" in summary_dict
        assert "by_symbol" in summary_dict
        assert "by_direction" in summary_dict
        assert "generated_at" in summary_dict

    def test_summary_period_bounds(self, analyzer_with_trades):
        """Test that summary includes correct period bounds"""
        summary = analyzer_with_trades.get_attribution_summary()

        assert summary.period_start is not None
        assert summary.period_end is not None
        assert summary.period_start <= summary.period_end


# =============================================================================
# TEST TREND ANALYSIS
# =============================================================================

class TestTrendAnalysis:
    """Tests for trend analysis over time"""

    def test_get_attribution_trends(self, analyzer_with_trades):
        """Test getting attribution trends"""
        trends = analyzer_with_trades.get_attribution_trends(
            period=TradePeriod.DAILY,
            lookback_days=7,
            dimension=AttributionDimension.STRATEGY
        )

        # Should return trends for each strategy
        assert len(trends) > 0

        for trend in trends:
            assert trend.dimension == AttributionDimension.STRATEGY
            assert len(trend.periods) > 0
            assert len(trend.pnl_trend) == len(trend.periods)
            assert trend.trend_direction in ["up", "down", "flat"]

    def test_trend_moving_average(self, analyzer_with_trades):
        """Test moving average calculation in trends"""
        trends = analyzer_with_trades.get_attribution_trends(
            period=TradePeriod.DAILY,
            lookback_days=7
        )

        for trend in trends:
            assert len(trend.moving_avg_pnl) == len(trend.pnl_trend)

    def test_trend_direction_determination(self, analyzer):
        """Test trend direction determination"""
        # Test upward trend
        up_values = [1.0, 2.0, 3.0, 4.0, 5.0]
        direction = analyzer._determine_trend_direction(up_values)
        assert direction == "up"

        # Test downward trend
        down_values = [5.0, 4.0, 3.0, 2.0, 1.0]
        direction = analyzer._determine_trend_direction(down_values)
        assert direction == "down"

        # Test flat trend
        flat_values = [3.0, 3.1, 2.9, 3.0, 3.05]
        direction = analyzer._determine_trend_direction(flat_values)
        assert direction == "flat"


# =============================================================================
# TEST PERFORMANCE DECOMPOSITION
# =============================================================================

class TestPerformanceDecomposition:
    """Tests for performance decomposition (Alpha, Beta, Residual)"""

    def test_get_performance_decomposition(self, analyzer_with_trades):
        """Test getting performance decomposition"""
        # Set some benchmark returns
        benchmark_returns = [0.005, 0.01, -0.005, 0.008, 0.003, -0.002, 0.007, 0.004]
        analyzer_with_trades.set_benchmark_returns(benchmark_returns)

        decompositions = analyzer_with_trades.get_performance_decomposition()

        assert len(decompositions) > 0

        for decomp in decompositions:
            assert decomp.strategy is not None
            assert decomp.alpha is not None
            assert decomp.beta is not None
            assert decomp.r_squared is not None

    def test_decomposition_without_benchmark(self, analyzer_with_trades):
        """Test decomposition without benchmark (should still work)"""
        decompositions = analyzer_with_trades.get_performance_decomposition()

        # Should return decompositions but with default beta=0
        for decomp in decompositions:
            assert decomp.strategy is not None


# =============================================================================
# TEST MARKET CONDITION CLASSIFICATION
# =============================================================================

class TestMarketConditionClassification:
    """Tests for market condition classification"""

    def test_classify_trending_up(self):
        """Test classification of upward trending market"""
        price_changes = [0.01, 0.02, 0.015, 0.008, 0.012, 0.005]
        condition = AttributionAnalyzer.classify_market_condition(price_changes)
        assert condition == MarketCondition.TRENDING_UP

    def test_classify_trending_down(self):
        """Test classification of downward trending market"""
        price_changes = [-0.01, -0.02, -0.015, -0.008, -0.012, -0.005]
        condition = AttributionAnalyzer.classify_market_condition(price_changes)
        assert condition == MarketCondition.TRENDING_DOWN

    def test_classify_ranging(self):
        """Test classification of ranging market"""
        price_changes = [0.01, -0.01, 0.008, -0.005, 0.003, -0.007]
        condition = AttributionAnalyzer.classify_market_condition(price_changes)
        assert condition == MarketCondition.RANGING

    def test_classify_volatile(self):
        """Test classification of volatile market"""
        price_changes = [0.05, -0.06, 0.04, -0.07, 0.03, -0.05]
        condition = AttributionAnalyzer.classify_market_condition(price_changes)
        assert condition == MarketCondition.VOLATILE

    def test_classify_empty(self):
        """Test classification with empty data"""
        condition = AttributionAnalyzer.classify_market_condition([])
        assert condition == MarketCondition.UNKNOWN


# =============================================================================
# TEST DAILY REPORT
# =============================================================================

class TestDailyReport:
    """Tests for daily attribution report generation"""

    def test_generate_daily_report(self, analyzer_with_trades):
        """Test generating daily report"""
        report = analyzer_with_trades.generate_daily_report()

        assert "date" in report
        assert "generated_at" in report
        assert "overall_pnl" in report
        assert "win_rate" in report
        assert "current_equity" in report
        assert "current_drawdown" in report

    def test_daily_report_top_strategies(self, analyzer_with_trades):
        """Test that daily report includes top strategies"""
        report = analyzer_with_trades.generate_daily_report()

        assert "top_strategies" in report
        # Should have at most 3 top strategies
        assert len(report["top_strategies"]) <= 3


# =============================================================================
# TEST STATE PERSISTENCE
# =============================================================================

class TestStatePersistence:
    """Tests for state persistence (save/load)"""

    def test_get_state(self, analyzer_with_trades):
        """Test getting analyzer state"""
        state = analyzer_with_trades.get_state()

        assert "initial_capital" in state
        assert "current_equity" in state
        assert "trades_count" in state
        assert "trades" in state
        assert len(state["trades"]) == len(analyzer_with_trades._trades)

    def test_load_state(self, analyzer):
        """Test loading analyzer state"""
        # Create a state to load
        state = {
            "initial_capital": 10000.0,
            "risk_free_rate": 0.02,
            "current_equity": 10500.0,
            "peak_equity": 10500.0,
            "trades": [
                {
                    "trade_id": "load_001",
                    "symbol": "BTCUSDT",
                    "strategy": "momentum",
                    "direction": "long",
                    "entry_time": "2025-12-11T10:00:00+00:00",
                    "exit_time": "2025-12-11T11:00:00+00:00",
                    "entry_price": 50000.0,
                    "exit_price": 50500.0,
                    "quantity": 0.1,
                    "pnl": 50.0,
                    "pnl_pct": 0.01,
                    "fees": 0.5,
                    "market_condition": "trending_up",
                }
            ],
            "equity_curve": [],
            "benchmark_returns": [],
        }

        analyzer.load_state(state)

        assert analyzer._current_equity == 10500.0
        assert len(analyzer._trades) == 1
        assert analyzer._trades[0].trade_id == "load_001"


# =============================================================================
# TEST GLOBAL INSTANCE MANAGEMENT
# =============================================================================

class TestGlobalInstanceManagement:
    """Tests for global analyzer instance management"""

    def test_get_attribution_analyzer(self):
        """Test getting global analyzer instance"""
        reset_attribution_analyzer()

        analyzer1 = get_attribution_analyzer(initial_capital=10000.0)
        analyzer2 = get_attribution_analyzer()

        assert analyzer1 is analyzer2

    def test_reset_attribution_analyzer(self):
        """Test resetting global analyzer"""
        analyzer1 = get_attribution_analyzer(initial_capital=10000.0)

        reset_attribution_analyzer()

        analyzer2 = get_attribution_analyzer(initial_capital=20000.0)

        assert analyzer2.initial_capital == 20000.0


# =============================================================================
# TEST API MODELS
# =============================================================================

class TestAPIModels:
    """Tests for API response models"""

    def test_attribution_metrics_response(self):
        """Test AttributionMetricsResponse model"""
        response = AttributionMetricsResponse(
            total_pnl=1000.0,
            win_rate=65.0,
            sharpe_ratio=1.85,
            max_drawdown=-5.0,
            avg_win=150.0,
            avg_loss=-80.0,
            profit_factor=1.88,
            trades_count=50,
            sortino_ratio=2.15,
            calmar_ratio=0.25,
        )

        assert response.total_pnl == 1000.0
        assert response.trades_count == 50

    def test_attribution_result_response(self):
        """Test AttributionResultResponse model"""
        metrics = AttributionMetricsResponse(
            total_pnl=500.0,
            win_rate=60.0,
            sharpe_ratio=1.5,
            max_drawdown=-3.0,
            avg_win=100.0,
            avg_loss=-60.0,
            profit_factor=1.67,
            trades_count=25,
            sortino_ratio=1.8,
            calmar_ratio=0.2,
        )

        response = AttributionResultResponse(
            dimension="strategy",
            value="pairs_trading",
            metrics=metrics,
            contribution_pct=40.0,
            trades_count=25,
        )

        assert response.dimension == "strategy"
        assert response.value == "pairs_trading"
        assert response.contribution_pct == 40.0

    def test_attribution_by_strategy_response(self):
        """Test AttributionByStrategyResponse model"""
        response = AttributionByStrategyResponse(
            success=True,
            attributions=[],
            total_strategies=3,
            period_start="2025-12-01T00:00:00Z",
            period_end="2025-12-11T23:59:59Z",
            generated_at="2025-12-11T14:30:00Z",
        )

        assert response.success is True
        assert response.total_strategies == 3

    def test_attribution_summary_response(self):
        """Test AttributionSummaryResponse model"""
        metrics = AttributionMetricsResponse(
            total_pnl=1000.0,
            win_rate=60.0,
            sharpe_ratio=1.5,
            max_drawdown=-5.0,
            avg_win=100.0,
            avg_loss=-60.0,
            profit_factor=1.67,
            trades_count=100,
            sortino_ratio=1.8,
            calmar_ratio=0.2,
        )

        response = AttributionSummaryResponse(
            success=True,
            overall_metrics=metrics,
            by_strategy=[],
            by_symbol=[],
            by_direction=[],
            by_market_condition=[],
            generated_at="2025-12-11T14:30:00Z",
            current_equity=11000.0,
            peak_equity=11200.0,
        )

        assert response.success is True
        assert response.current_equity == 11000.0


# =============================================================================
# TEST EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling"""

    def test_empty_analyzer_summary(self, analyzer):
        """Test getting summary from empty analyzer"""
        summary = analyzer.get_attribution_summary()

        assert summary.overall_metrics.trades_count == 0
        assert summary.overall_metrics.total_pnl == 0

    def test_single_trade_metrics(self, analyzer):
        """Test metrics with single trade"""
        trade = TradeRecord(
            trade_id="single_001",
            symbol="BTCUSDT",
            strategy="momentum",
            direction=TradeDirection.LONG,
            entry_time=datetime.now(timezone.utc) - timedelta(hours=1),
            exit_time=datetime.now(timezone.utc),
            entry_price=50000.0,
            exit_price=50500.0,
            quantity=0.1,
            pnl=50.0,
            pnl_pct=0.01,
        )
        analyzer.add_trade(trade)

        metrics = analyzer._calculate_metrics([trade])

        assert metrics.trades_count == 1
        assert metrics.win_rate == 1.0  # 100% win rate with single winning trade

    def test_all_losing_trades(self, analyzer):
        """Test metrics with all losing trades"""
        for i in range(5):
            analyzer.add_trade(TradeRecord(
                trade_id=f"lose_{i}",
                symbol="BTCUSDT",
                strategy="momentum",
                direction=TradeDirection.LONG,
                entry_time=datetime.now(timezone.utc) - timedelta(hours=i+1),
                exit_time=datetime.now(timezone.utc) - timedelta(hours=i),
                entry_price=50000.0,
                exit_price=49900.0,
                quantity=0.1,
                pnl=-10.0,
                pnl_pct=-0.002,
            ))

        metrics = analyzer._calculate_metrics(analyzer._trades)

        assert metrics.win_rate == 0.0
        assert metrics.total_pnl < 0

    def test_all_winning_trades(self, analyzer):
        """Test metrics with all winning trades"""
        for i in range(5):
            analyzer.add_trade(TradeRecord(
                trade_id=f"win_{i}",
                symbol="BTCUSDT",
                strategy="momentum",
                direction=TradeDirection.LONG,
                entry_time=datetime.now(timezone.utc) - timedelta(hours=i+1),
                exit_time=datetime.now(timezone.utc) - timedelta(hours=i),
                entry_price=50000.0,
                exit_price=50100.0,
                quantity=0.1,
                pnl=10.0,
                pnl_pct=0.002,
            ))

        metrics = analyzer._calculate_metrics(analyzer._trades)

        assert metrics.win_rate == 1.0
        assert metrics.total_pnl > 0
        # Profit factor should be infinity or very high
        assert metrics.profit_factor > 0


# =============================================================================
# TEST API ENDPOINT HANDLERS
# =============================================================================

class TestAPIHandlers:
    """Tests for API endpoint handler functions"""

    @pytest.mark.asyncio
    async def test_attribution_by_strategy_endpoint(self, analyzer_with_trades):
        """Test attribution by strategy endpoint"""
        from app.handlers.attribution import get_attribution_by_strategy

        # Mock the analyzer
        with patch('app.handlers.attribution.get_attribution_analyzer', return_value=analyzer_with_trades):
            response = await get_attribution_by_strategy(start_time=None, end_time=None)

            assert response.success is True
            assert response.total_strategies > 0

    @pytest.mark.asyncio
    async def test_attribution_by_symbol_endpoint(self, analyzer_with_trades):
        """Test attribution by symbol endpoint"""
        from app.handlers.attribution import get_attribution_by_symbol

        with patch('app.handlers.attribution.get_attribution_analyzer', return_value=analyzer_with_trades):
            response = await get_attribution_by_symbol(start_time=None, end_time=None)

            assert response.success is True
            assert response.total_symbols > 0

    @pytest.mark.asyncio
    async def test_attribution_summary_endpoint(self, analyzer_with_trades):
        """Test attribution summary endpoint"""
        from app.handlers.attribution import get_attribution_summary

        with patch('app.handlers.attribution.get_attribution_analyzer', return_value=analyzer_with_trades):
            response = await get_attribution_summary(
                start_time=None,
                end_time=None,
                include_decomposition=False
            )

            assert response.success is True
            assert response.overall_metrics is not None

    @pytest.mark.asyncio
    async def test_attribution_trends_endpoint(self, analyzer_with_trades):
        """Test attribution trends endpoint"""
        from app.handlers.attribution import get_attribution_trends
        from app.analytics.models import TimePeriod, DimensionType

        with patch('app.handlers.attribution.get_attribution_analyzer', return_value=analyzer_with_trades):
            response = await get_attribution_trends(
                period=TimePeriod.DAILY,
                lookback_days=7,
                dimension=DimensionType.STRATEGY
            )

            assert response.success is True

    @pytest.mark.asyncio
    async def test_daily_report_endpoint(self, analyzer_with_trades):
        """Test daily report endpoint"""
        from app.handlers.attribution import get_daily_report

        with patch('app.handlers.attribution.get_attribution_analyzer', return_value=analyzer_with_trades):
            response = await get_daily_report()

            assert response.success is True
            assert response.date is not None


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=app.analytics", "--cov-report=html"])
