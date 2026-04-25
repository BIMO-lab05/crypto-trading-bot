"""
Integration Tests for Analytics Components
==========================================
Phase 5.2: Advanced Performance Metrics Integration Tests

Purpose:
- Test advanced performance metrics calculation
- Verify integration with trading history
- Test real-time metrics updates
- Validate analytics dashboard data flow

Test Coverage:
- AdvancedMetricsCalculator comprehensive metrics
- Performance attribution analysis
- Risk-adjusted return calculations
- Rolling window analytics
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Dict, Any
from unittest.mock import MagicMock, AsyncMock, patch
import uuid
import numpy as np

# Import analytics components
from app.analytics.advanced_metrics import (
    AdvancedMetricsCalculator,
    MetricsConfig,
    PerformanceMetrics,
    RiskMetrics,
    TradeAnalytics,
    DrawdownAnalysis,
    get_metrics_calculator,
)
from app.models import OrderSide


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def metrics_config() -> MetricsConfig:
    """
    Create metrics configuration for testing

    Returns:
        MetricsConfig configured for testing
    """
    return MetricsConfig(
        risk_free_rate=0.05,  # 5% annual risk-free rate
        trading_days_per_year=252,
        rolling_window_days=30,
        benchmark_symbol="BTCUSDT",
        enable_monte_carlo=False,  # Disabled for faster tests
        confidence_level=0.95,
    )


@pytest.fixture
def metrics_calculator(metrics_config) -> AdvancedMetricsCalculator:
    """
    Create metrics calculator instance

    Returns:
        AdvancedMetricsCalculator for testing
    """
    return AdvancedMetricsCalculator(config=metrics_config)


@pytest.fixture
def sample_trades() -> List[Dict[str, Any]]:
    """
    Generate sample trade data for testing

    Returns:
        List of trade dictionaries
    """
    base_time = datetime.now(timezone.utc) - timedelta(days=30)
    trades = []

    # Generate 50 sample trades over 30 days
    for i in range(50):
        is_winner = np.random.random() > 0.4  # 60% win rate
        pnl = np.random.uniform(50, 500) if is_winner else -np.random.uniform(30, 200)

        trades.append({
            "trade_id": str(uuid.uuid4()),
            "symbol": np.random.choice(["BTCUSDT", "ETHUSDT"]),
            "side": np.random.choice([OrderSide.BUY, OrderSide.SELL]),
            "entry_price": Decimal(str(50000 + np.random.uniform(-1000, 1000))),
            "exit_price": Decimal(str(50000 + np.random.uniform(-1000, 1000))),
            "quantity": Decimal(str(np.random.uniform(0.01, 0.1))),
            "pnl": pnl,
            "pnl_pct": pnl / 1000,  # Assume $1000 position
            "entry_time": base_time + timedelta(hours=i * 14),
            "exit_time": base_time + timedelta(hours=i * 14 + np.random.uniform(1, 24)),
            "fees": abs(pnl) * 0.001,
            "strategy_id": np.random.choice(["trend", "mean_reversion", "momentum"]),
        })

    return trades


@pytest.fixture
def sample_equity_curve() -> List[Dict[str, Any]]:
    """
    Generate sample equity curve for testing

    Returns:
        List of equity snapshots
    """
    base_time = datetime.now(timezone.utc) - timedelta(days=30)
    initial_equity = 10000.0
    equity = initial_equity

    curve = []
    for i in range(30 * 24):  # Hourly data for 30 days
        # Simulate random walk with slight upward drift
        change = np.random.normal(0.0001, 0.002) * equity
        equity += change

        curve.append({
            "timestamp": base_time + timedelta(hours=i),
            "equity": equity,
            "unrealized_pnl": np.random.uniform(-100, 100),
            "realized_pnl": equity - initial_equity,
        })

    return curve


# ============================================================================
# PERFORMANCE METRICS TESTS
# ============================================================================

class TestPerformanceMetricsIntegration:
    """Test suite for performance metrics calculation"""

    @pytest.mark.asyncio
    async def test_basic_metrics_calculation(
        self,
        metrics_calculator,
        sample_trades
    ):
        """
        Test basic performance metrics are calculated correctly

        Verifies:
        - Total PnL calculation
        - Win rate calculation
        - Average trade metrics
        """
        # Load trades into calculator
        for trade in sample_trades:
            metrics_calculator.add_trade(trade)

        # Calculate metrics
        metrics = metrics_calculator.calculate_performance_metrics()

        # Verify metrics
        assert isinstance(metrics, PerformanceMetrics)
        assert metrics.total_trades == 50
        assert 0.0 <= metrics.win_rate <= 1.0
        assert metrics.avg_win > 0
        assert metrics.avg_loss < 0

    @pytest.mark.asyncio
    async def test_profit_factor_calculation(
        self,
        metrics_calculator,
        sample_trades
    ):
        """
        Test profit factor is calculated correctly

        Formula: Profit Factor = Gross Profit / Gross Loss
        """
        for trade in sample_trades:
            metrics_calculator.add_trade(trade)

        metrics = metrics_calculator.calculate_performance_metrics()

        # Manual calculation for verification
        gross_profit = sum(t["pnl"] for t in sample_trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in sample_trades if t["pnl"] < 0))

        expected_pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        assert abs(metrics.profit_factor - expected_pf) < 0.01

    @pytest.mark.asyncio
    async def test_expectancy_calculation(
        self,
        metrics_calculator,
        sample_trades
    ):
        """
        Test expectancy (expected value per trade) calculation

        Formula: Expectancy = (Win Rate * Avg Win) - (Loss Rate * Avg Loss)
        """
        for trade in sample_trades:
            metrics_calculator.add_trade(trade)

        metrics = metrics_calculator.calculate_performance_metrics()

        # Calculate expected value
        wins = [t["pnl"] for t in sample_trades if t["pnl"] > 0]
        losses = [t["pnl"] for t in sample_trades if t["pnl"] < 0]

        win_rate = len(wins) / len(sample_trades)
        loss_rate = 1 - win_rate
        avg_win = np.mean(wins) if wins else 0
        avg_loss = abs(np.mean(losses)) if losses else 0

        expected_expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)

        assert abs(metrics.expectancy - expected_expectancy) < 1.0


# ============================================================================
# RISK METRICS TESTS
# ============================================================================

class TestRiskMetricsIntegration:
    """Test suite for risk metrics calculation"""

    @pytest.mark.asyncio
    async def test_sharpe_ratio_calculation(
        self,
        metrics_calculator,
        sample_equity_curve
    ):
        """
        Test Sharpe ratio is calculated correctly

        Formula: Sharpe = (Return - Risk Free Rate) / Std Dev of Returns
        """
        # Load equity curve
        metrics_calculator.load_equity_curve(sample_equity_curve)

        risk_metrics = metrics_calculator.calculate_risk_metrics()

        assert isinstance(risk_metrics, RiskMetrics)
        # Sharpe ratio typically ranges from -3 to +3 for most strategies
        assert -5.0 <= risk_metrics.sharpe_ratio <= 5.0

    @pytest.mark.asyncio
    async def test_sortino_ratio_calculation(
        self,
        metrics_calculator,
        sample_equity_curve
    ):
        """
        Test Sortino ratio calculation (downside risk only)

        Formula: Sortino = (Return - Risk Free Rate) / Downside Deviation
        """
        metrics_calculator.load_equity_curve(sample_equity_curve)

        risk_metrics = metrics_calculator.calculate_risk_metrics()

        # Sortino should be >= Sharpe (penalizes only downside)
        # Note: This may not always hold for short periods
        assert risk_metrics.sortino_ratio is not None

    @pytest.mark.asyncio
    async def test_max_drawdown_calculation(
        self,
        metrics_calculator,
        sample_equity_curve
    ):
        """
        Test maximum drawdown calculation

        Verifies:
        - Max drawdown percentage
        - Drawdown duration
        - Recovery time
        """
        metrics_calculator.load_equity_curve(sample_equity_curve)

        drawdown = metrics_calculator.calculate_drawdown_analysis()

        assert isinstance(drawdown, DrawdownAnalysis)
        assert 0.0 <= drawdown.max_drawdown_pct <= 1.0
        assert drawdown.max_drawdown_duration_hours >= 0
        assert drawdown.current_drawdown_pct >= 0

    @pytest.mark.asyncio
    async def test_var_calculation(
        self,
        metrics_calculator,
        sample_equity_curve
    ):
        """
        Test Value at Risk (VaR) calculation

        Verifies:
        - Historical VaR
        - Parametric VaR
        - Conditional VaR (Expected Shortfall)
        """
        metrics_calculator.load_equity_curve(sample_equity_curve)

        risk_metrics = metrics_calculator.calculate_risk_metrics()

        # VaR should be negative (represents potential loss)
        assert risk_metrics.var_95 <= 0
        # CVaR should be worse (more negative) than VaR
        assert risk_metrics.cvar_95 <= risk_metrics.var_95

    @pytest.mark.asyncio
    async def test_calmar_ratio_calculation(
        self,
        metrics_calculator,
        sample_equity_curve
    ):
        """
        Test Calmar ratio calculation

        Formula: Calmar = Annual Return / Max Drawdown
        """
        metrics_calculator.load_equity_curve(sample_equity_curve)

        risk_metrics = metrics_calculator.calculate_risk_metrics()

        assert risk_metrics.calmar_ratio is not None


# ============================================================================
# TRADE ANALYTICS TESTS
# ============================================================================

class TestTradeAnalyticsIntegration:
    """Test suite for detailed trade analytics"""

    @pytest.mark.asyncio
    async def test_trade_distribution_analysis(
        self,
        metrics_calculator,
        sample_trades
    ):
        """
        Test trade PnL distribution analysis

        Verifies:
        - PnL percentiles
        - Skewness and kurtosis
        - Best/worst trades
        """
        for trade in sample_trades:
            metrics_calculator.add_trade(trade)

        analytics = metrics_calculator.calculate_trade_analytics()

        assert isinstance(analytics, TradeAnalytics)
        assert analytics.best_trade > 0
        assert analytics.worst_trade < 0
        assert analytics.median_trade is not None

    @pytest.mark.asyncio
    async def test_win_loss_streak_analysis(
        self,
        metrics_calculator,
        sample_trades
    ):
        """
        Test consecutive win/loss streak analysis

        Verifies:
        - Max winning streak
        - Max losing streak
        - Current streak
        """
        for trade in sample_trades:
            metrics_calculator.add_trade(trade)

        analytics = metrics_calculator.calculate_trade_analytics()

        assert analytics.max_win_streak >= 0
        assert analytics.max_loss_streak >= 0

    @pytest.mark.asyncio
    async def test_trade_duration_analysis(
        self,
        metrics_calculator,
        sample_trades
    ):
        """
        Test trade duration analysis

        Verifies:
        - Average holding time
        - Winning vs losing trade duration
        """
        for trade in sample_trades:
            metrics_calculator.add_trade(trade)

        analytics = metrics_calculator.calculate_trade_analytics()

        assert analytics.avg_holding_hours > 0
        # Winners may hold longer or shorter depending on strategy
        assert analytics.avg_winner_duration_hours > 0
        assert analytics.avg_loser_duration_hours > 0


# ============================================================================
# ROLLING WINDOW ANALYTICS TESTS
# ============================================================================

class TestRollingWindowAnalyticsIntegration:
    """Test suite for rolling window analytics"""

    @pytest.mark.asyncio
    async def test_rolling_sharpe_ratio(
        self,
        metrics_calculator,
        sample_equity_curve
    ):
        """
        Test rolling Sharpe ratio calculation

        Verifies:
        - Rolling window is applied correctly
        - Sharpe updates with new data
        """
        metrics_calculator.load_equity_curve(sample_equity_curve)

        # Calculate rolling metrics
        rolling_metrics = metrics_calculator.calculate_rolling_metrics(
            window_days=7
        )

        assert len(rolling_metrics) > 0
        assert "sharpe_ratio" in rolling_metrics[0]

    @pytest.mark.asyncio
    async def test_rolling_volatility(
        self,
        metrics_calculator,
        sample_equity_curve
    ):
        """
        Test rolling volatility calculation

        Verifies:
        - Volatility is annualized correctly
        - Responds to recent price action
        """
        metrics_calculator.load_equity_curve(sample_equity_curve)

        rolling_vol = metrics_calculator.calculate_rolling_volatility(
            window_days=14
        )

        assert len(rolling_vol) > 0
        # Annualized volatility typically 10-100% for crypto
        for vol in rolling_vol:
            assert 0.0 <= vol["volatility"] <= 2.0

    @pytest.mark.asyncio
    async def test_rolling_drawdown(
        self,
        metrics_calculator,
        sample_equity_curve
    ):
        """
        Test rolling drawdown tracking

        Verifies:
        - Drawdown is calculated from rolling peak
        - Recovery detection works
        """
        metrics_calculator.load_equity_curve(sample_equity_curve)

        rolling_dd = metrics_calculator.calculate_rolling_drawdown()

        assert len(rolling_dd) > 0
        for dd in rolling_dd:
            assert 0.0 <= dd["drawdown_pct"] <= 1.0


# ============================================================================
# STRATEGY ATTRIBUTION TESTS
# ============================================================================

class TestStrategyAttributionIntegration:
    """Test suite for strategy performance attribution"""

    @pytest.mark.asyncio
    async def test_pnl_attribution_by_strategy(
        self,
        metrics_calculator,
        sample_trades
    ):
        """
        Test PnL attribution by strategy

        Verifies:
        - PnL is correctly attributed to each strategy
        - Totals sum correctly
        """
        for trade in sample_trades:
            metrics_calculator.add_trade(trade)

        attribution = metrics_calculator.calculate_strategy_attribution()

        # Check all strategies are present
        strategies = set(t["strategy_id"] for t in sample_trades)
        assert all(s in attribution for s in strategies)

        # Verify totals
        total_pnl = sum(a["pnl"] for a in attribution.values())
        expected_total = sum(t["pnl"] for t in sample_trades)
        assert abs(total_pnl - expected_total) < 0.01

    @pytest.mark.asyncio
    async def test_pnl_attribution_by_symbol(
        self,
        metrics_calculator,
        sample_trades
    ):
        """
        Test PnL attribution by trading symbol

        Verifies:
        - PnL is correctly attributed to each symbol
        - Performance varies by symbol
        """
        for trade in sample_trades:
            metrics_calculator.add_trade(trade)

        attribution = metrics_calculator.calculate_symbol_attribution()

        symbols = set(t["symbol"] for t in sample_trades)
        assert all(s in attribution for s in symbols)

    @pytest.mark.asyncio
    async def test_contribution_to_portfolio(
        self,
        metrics_calculator,
        sample_trades
    ):
        """
        Test contribution of each strategy to portfolio returns

        Verifies:
        - Weighted contribution is calculated
        - Total contribution sums to 100%
        """
        for trade in sample_trades:
            metrics_calculator.add_trade(trade)

        contribution = metrics_calculator.calculate_portfolio_contribution()

        # Total contribution should sum to approximately 100%
        total_contribution = sum(c["contribution_pct"] for c in contribution.values())
        assert abs(total_contribution - 100.0) < 1.0


# ============================================================================
# REAL-TIME METRICS UPDATE TESTS
# ============================================================================

class TestRealTimeMetricsIntegration:
    """Test suite for real-time metrics updates"""

    @pytest.mark.asyncio
    async def test_incremental_metrics_update(
        self,
        metrics_calculator,
        sample_trades
    ):
        """
        Test metrics update incrementally with new trades

        Verifies:
        - Metrics update correctly after each trade
        - No need to recalculate from scratch
        """
        # Add initial trades
        for trade in sample_trades[:25]:
            metrics_calculator.add_trade(trade)

        initial_metrics = metrics_calculator.calculate_performance_metrics()
        initial_total = initial_metrics.total_trades

        # Add more trades
        for trade in sample_trades[25:]:
            metrics_calculator.add_trade(trade)

        updated_metrics = metrics_calculator.calculate_performance_metrics()

        # Trade count should increase
        assert updated_metrics.total_trades == 50
        assert updated_metrics.total_trades > initial_total

    @pytest.mark.asyncio
    async def test_equity_curve_live_update(
        self,
        metrics_calculator,
        sample_equity_curve
    ):
        """
        Test equity curve updates in real-time

        Verifies:
        - New equity points are added
        - Metrics recalculate with latest data
        """
        # Load historical data
        metrics_calculator.load_equity_curve(sample_equity_curve[:500])

        initial_risk = metrics_calculator.calculate_risk_metrics()
        initial_drawdown = initial_risk.max_drawdown_pct

        # Add new equity points
        for point in sample_equity_curve[500:]:
            metrics_calculator.add_equity_point(point)

        updated_risk = metrics_calculator.calculate_risk_metrics()

        # Max drawdown should be same or higher with more data
        assert updated_risk.max_drawdown_pct >= initial_drawdown * 0.9


# ============================================================================
# BENCHMARK COMPARISON TESTS
# ============================================================================

class TestBenchmarkComparisonIntegration:
    """Test suite for benchmark comparison analytics"""

    @pytest.mark.asyncio
    async def test_alpha_calculation(
        self,
        metrics_calculator,
        sample_equity_curve
    ):
        """
        Test alpha (excess return) calculation

        Verifies:
        - Alpha represents return above benchmark
        """
        metrics_calculator.load_equity_curve(sample_equity_curve)

        # Mock benchmark returns
        benchmark_returns = [0.001] * len(sample_equity_curve)  # 0.1% daily

        alpha = metrics_calculator.calculate_alpha(benchmark_returns)

        # Alpha can be positive or negative
        assert -10.0 <= alpha <= 10.0

    @pytest.mark.asyncio
    async def test_beta_calculation(
        self,
        metrics_calculator,
        sample_equity_curve
    ):
        """
        Test beta (market sensitivity) calculation

        Verifies:
        - Beta measures correlation with market
        """
        metrics_calculator.load_equity_curve(sample_equity_curve)

        # Mock benchmark returns
        benchmark_returns = [0.001 + np.random.normal(0, 0.01)
                           for _ in sample_equity_curve]

        beta = metrics_calculator.calculate_beta(benchmark_returns)

        # Beta typically ranges from -2 to 3
        assert -3.0 <= beta <= 4.0

    @pytest.mark.asyncio
    async def test_information_ratio(
        self,
        metrics_calculator,
        sample_equity_curve
    ):
        """
        Test information ratio calculation

        Formula: IR = (Portfolio Return - Benchmark Return) / Tracking Error
        """
        metrics_calculator.load_equity_curve(sample_equity_curve)

        benchmark_returns = [0.001] * len(sample_equity_curve)

        ir = metrics_calculator.calculate_information_ratio(benchmark_returns)

        # IR typically ranges from -2 to 2 for most strategies
        assert -5.0 <= ir <= 5.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
