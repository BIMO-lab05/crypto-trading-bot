"""
Test Suite for Performance Calculator Service
Comprehensive tests for P&L and risk metrics calculations
CRITICAL: These tests validate financial calculations
"""

import pytest
import numpy as np
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.services.performance_calculator import PerformanceCalculator
from app.models.portfolio import Portfolio
from app.models.performance import PerformanceMetrics


class TestPerformanceCalculatorInit:
    """Basic initialization tests"""

    def test_init_sets_risk_free_rate(self):
        """Test calculator initializes with risk-free rate from settings"""
        calc = PerformanceCalculator()

        assert calc.risk_free_rate is not None
        assert calc.risk_free_rate >= 0


class TestTotalReturnCalculation:
    """Tests for total return / P&L calculations"""

    def test_calculate_total_return_profit(self):
        """Test calculating positive total return (profit)"""
        calc = PerformanceCalculator()

        # Create portfolio with profit
        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("5000"),
            total_value=Decimal("12000"),
            total_pnl=Decimal("2000"),
            total_return_pct=Decimal("20"),
            realized_pnl=Decimal("1000"),
            unrealized_pnl=Decimal("1000")
        )

        metrics = calc.calculate_metrics(portfolio)

        assert metrics.total_return == Decimal("2000")
        assert metrics.total_return_pct == Decimal("20")
        assert metrics.total_pnl == Decimal("2000")
        assert metrics.realized_pnl == Decimal("1000")
        assert metrics.unrealized_pnl == Decimal("1000")

    def test_calculate_total_return_loss(self):
        """Test calculating negative total return (loss)"""
        calc = PerformanceCalculator()

        # Create portfolio with loss
        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("3000"),
            total_value=Decimal("8000"),
            total_pnl=Decimal("-2000"),
            total_return_pct=Decimal("-20"),
            realized_pnl=Decimal("-500"),
            unrealized_pnl=Decimal("-1500")
        )

        metrics = calc.calculate_metrics(portfolio)

        assert metrics.total_return == Decimal("-2000")
        assert metrics.total_return_pct == Decimal("-20")
        assert metrics.total_pnl == Decimal("-2000")

    def test_calculate_total_return_break_even(self):
        """Test calculating zero return (break even)"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("10000"),
            total_value=Decimal("10000"),
            total_pnl=Decimal("0"),
            total_return_pct=Decimal("0")
        )

        metrics = calc.calculate_metrics(portfolio)

        assert metrics.total_return == Decimal("0")
        assert metrics.total_return_pct == Decimal("0")


class TestSharpeRatioCalculation:
    """Tests for Sharpe ratio calculation"""

    def test_sharpe_ratio_calculation_positive(self):
        """Test Sharpe ratio calculation with positive returns"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("10000"),
            total_value=Decimal("10000")
        )

        # Daily values showing consistent positive returns
        daily_values = [
            Decimal("10000"),
            Decimal("10100"),  # +1%
            Decimal("10201"),  # +1%
            Decimal("10303"),  # +1%
            Decimal("10406"),  # +1%
            Decimal("10510"),  # +1%
        ]

        metrics = calc.calculate_metrics(portfolio, daily_values=daily_values)

        # With consistent positive returns, Sharpe should be positive
        assert metrics.sharpe_ratio is not None
        assert metrics.sharpe_ratio > 0

    def test_sharpe_ratio_calculation_negative(self):
        """Test Sharpe ratio calculation with negative returns"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("9000"),
            total_value=Decimal("9000")
        )

        # Daily values showing consistent losses
        daily_values = [
            Decimal("10000"),
            Decimal("9900"),  # -1%
            Decimal("9801"),  # -1%
            Decimal("9703"),  # -1%
            Decimal("9606"),  # -1%
            Decimal("9510"),  # -1%
        ]

        metrics = calc.calculate_metrics(portfolio, daily_values=daily_values)

        # With consistent losses, Sharpe should be negative
        assert metrics.sharpe_ratio is not None
        assert metrics.sharpe_ratio < 0

    def test_sharpe_ratio_zero_volatility(self):
        """Test Sharpe ratio returns None when volatility is zero"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("10000"),
            total_value=Decimal("10000")
        )

        # All same values = zero volatility
        daily_values = [Decimal("10000")] * 10

        metrics = calc.calculate_metrics(portfolio, daily_values=daily_values)

        assert metrics.sharpe_ratio is None

    def test_sharpe_ratio_insufficient_data(self):
        """Test Sharpe ratio with insufficient data points"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("10000"),
            total_value=Decimal("10000")
        )

        # Only one data point - cannot calculate returns
        daily_values = [Decimal("10000")]

        metrics = calc.calculate_metrics(portfolio, daily_values=daily_values)

        # Should handle gracefully
        assert metrics.sharpe_ratio is None


class TestSortinoRatioCalculation:
    """Tests for Sortino ratio calculation"""

    def test_sortino_ratio_with_downside_risk(self):
        """Test Sortino ratio calculation with mixed returns"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("10000"),
            total_value=Decimal("10500")
        )

        # Mixed returns with some negative days
        daily_values = [
            Decimal("10000"),
            Decimal("10200"),  # +2%
            Decimal("10000"),  # -1.96%
            Decimal("10300"),  # +3%
            Decimal("10100"),  # -1.94%
            Decimal("10500"),  # +3.96%
        ]

        metrics = calc.calculate_metrics(portfolio, daily_values=daily_values)

        # Sortino should be calculated
        assert metrics.sortino_ratio is not None

    def test_sortino_ratio_no_negative_returns(self):
        """Test Sortino ratio when all returns are positive"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("10000"),
            total_value=Decimal("10000")
        )

        # All positive returns
        daily_values = [
            Decimal("10000"),
            Decimal("10100"),
            Decimal("10200"),
            Decimal("10300"),
            Decimal("10400"),
        ]

        metrics = calc.calculate_metrics(portfolio, daily_values=daily_values)

        # With no downside, sortino should be None
        assert metrics.sortino_ratio is None


class TestMaxDrawdownCalculation:
    """Tests for maximum drawdown calculation"""

    def test_max_drawdown_calculation(self):
        """Test max drawdown is calculated correctly"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("10000"),
            total_value=Decimal("10000")
        )

        # Values with clear drawdown
        daily_values = [
            Decimal("10000"),
            Decimal("11000"),  # Peak
            Decimal("10000"),  # -9.09% from peak
            Decimal("9000"),   # -18.18% from peak (max drawdown)
            Decimal("10000"),  # Recovery
        ]

        metrics = calc.calculate_metrics(portfolio, daily_values=daily_values)

        assert metrics.max_drawdown is not None
        # Max drawdown from 11000 to 9000 = -18.18%
        assert metrics.max_drawdown < 0
        assert abs(metrics.max_drawdown - (-18.18)) < 1  # Within 1%

    def test_max_drawdown_duration(self):
        """Test max drawdown duration is tracked"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("10000"),
            total_value=Decimal("10000")
        )

        # Extended drawdown period
        daily_values = [
            Decimal("10000"),
            Decimal("11000"),  # Peak
            Decimal("10500"),  # Day 1 in drawdown
            Decimal("10200"),  # Day 2
            Decimal("10000"),  # Day 3
            Decimal("9500"),   # Day 4
            Decimal("11100"),  # Recovery
        ]

        metrics = calc.calculate_metrics(portfolio, daily_values=daily_values)

        assert metrics.max_drawdown_duration is not None
        assert metrics.max_drawdown_duration > 0

    def test_no_drawdown_scenario(self):
        """Test when there is no drawdown (monotonic increase)"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("10000"),
            total_value=Decimal("12000")
        )

        # Continuously increasing
        daily_values = [
            Decimal("10000"),
            Decimal("10500"),
            Decimal("11000"),
            Decimal("11500"),
            Decimal("12000"),
        ]

        metrics = calc.calculate_metrics(portfolio, daily_values=daily_values)

        # Max drawdown should be 0 or very close to 0
        assert metrics.max_drawdown is not None
        assert metrics.max_drawdown == 0 or abs(metrics.max_drawdown) < 0.01


class TestVolatilityCalculation:
    """Tests for volatility calculation"""

    def test_volatility_calculation(self):
        """Test volatility is calculated correctly"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("10000"),
            total_value=Decimal("10000")
        )

        # Values with some volatility
        daily_values = [
            Decimal("10000"),
            Decimal("10500"),  # +5%
            Decimal("10200"),  # -2.86%
            Decimal("10800"),  # +5.88%
            Decimal("10400"),  # -3.7%
        ]

        metrics = calc.calculate_metrics(portfolio, daily_values=daily_values)

        assert metrics.volatility is not None
        assert metrics.volatility > 0

    def test_zero_volatility(self):
        """Test volatility is zero for constant values"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("10000"),
            total_value=Decimal("10000")
        )

        # Constant values
        daily_values = [Decimal("10000")] * 10

        metrics = calc.calculate_metrics(portfolio, daily_values=daily_values)

        assert metrics.volatility == 0.0


class TestTradeHistoryMetrics:
    """Tests for metrics from trade history"""

    def test_metrics_with_trade_history(self):
        """Test comprehensive metrics with trade history"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("10000"),
            total_value=Decimal("11000")
        )

        trades_history = [
            {"pnl": 500},   # Win
            {"pnl": -200},  # Loss
            {"pnl": 300},   # Win
            {"pnl": -100},  # Loss
            {"pnl": 400},   # Win
        ]

        metrics = calc.calculate_metrics(portfolio, trades_history=trades_history)

        assert metrics.total_trades == 5
        assert metrics.winning_trades == 3
        assert metrics.losing_trades == 2
        assert metrics.win_rate == 60.0

    def test_win_rate_calculation(self):
        """Test win rate percentage calculation"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("10000"),
            total_value=Decimal("10000")
        )

        # 7 wins, 3 losses = 70% win rate
        trades_history = [{"pnl": 100}] * 7 + [{"pnl": -50}] * 3

        metrics = calc.calculate_metrics(portfolio, trades_history=trades_history)

        assert metrics.win_rate == 70.0

    def test_average_win_loss(self):
        """Test average win and loss calculation"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("10000"),
            total_value=Decimal("10000")
        )

        trades_history = [
            {"pnl": 100},
            {"pnl": 200},
            {"pnl": 300},  # Avg win: 200
            {"pnl": -50},
            {"pnl": -150},  # Avg loss: -100
        ]

        metrics = calc.calculate_metrics(portfolio, trades_history=trades_history)

        assert metrics.average_win == Decimal("200")
        assert metrics.average_loss == Decimal("-100")

    def test_profit_factor_calculation(self):
        """Test profit factor (total wins / total losses)"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("10000"),
            total_value=Decimal("10000")
        )

        # Total wins: 1000, Total losses: 500, Profit factor: 2.0
        trades_history = [
            {"pnl": 500},
            {"pnl": 500},
            {"pnl": -200},
            {"pnl": -300},
        ]

        metrics = calc.calculate_metrics(portfolio, trades_history=trades_history)

        assert metrics.profit_factor == 2.0

    def test_no_trades(self):
        """Test metrics with empty trade history"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("10000"),
            total_value=Decimal("10000")
        )

        metrics = calc.calculate_metrics(portfolio, trades_history=[])

        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0


class TestDailyPerformance:
    """Tests for daily performance calculation"""

    def test_calculate_daily_performance(self):
        """Test daily performance snapshots"""
        calc = PerformanceCalculator()

        now_ts = int(datetime.now().timestamp() * 1000)
        day_ms = 24 * 60 * 60 * 1000

        snapshots = [
            {"timestamp": now_ts - 2 * day_ms, "total_value": "10000", "trades_count": 0},
            {"timestamp": now_ts - day_ms, "total_value": "10500", "trades_count": 2},
            {"timestamp": now_ts, "total_value": "10800", "trades_count": 1},
        ]

        daily_performances = calc.calculate_daily_performance(snapshots)

        assert len(daily_performances) == 3
        # First day has no prior day, so daily return is 0
        assert daily_performances[0].daily_return_pct == "0"
        # Second day: (10500-10000)/10000 = 5%
        assert Decimal(daily_performances[1].daily_return_pct) == Decimal("5")

    def test_cumulative_return_calculation(self):
        """Test cumulative return tracking"""
        calc = PerformanceCalculator()

        now_ts = int(datetime.now().timestamp() * 1000)
        day_ms = 24 * 60 * 60 * 1000

        snapshots = [
            {"timestamp": now_ts - day_ms, "total_value": "10000"},
            {"timestamp": now_ts, "total_value": "12000"},  # +20% cumulative
        ]

        daily_performances = calc.calculate_daily_performance(snapshots)

        assert Decimal(daily_performances[1].cumulative_return_pct) == Decimal("20")


class TestPeriodPerformance:
    """Tests for period performance calculation"""

    def test_period_performance_7d(self):
        """Test 7-day period performance calculation returns valid result"""
        calc = PerformanceCalculator()

        current_value = Decimal("11000")
        now = datetime.now()

        # Create historical values within 7-day window
        historical_values = [
            (now - timedelta(days=6), Decimal("10000")),
            (now - timedelta(days=5), Decimal("10200")),
            (now - timedelta(days=3), Decimal("10500")),
            (now - timedelta(days=1), Decimal("10800")),
        ]

        period_perf = calc.calculate_period_performance(
            current_value, historical_values, "7d"
        )

        assert period_perf is not None
        assert period_perf.period == "7d"
        # Total return should be current - start
        total_return = Decimal(period_perf.total_return)
        assert total_return > 0  # Positive return

    def test_period_performance_30d(self):
        """Test 30-day period performance calculation"""
        calc = PerformanceCalculator()

        current_value = Decimal("12000")
        now = datetime.now()

        historical_values = [
            (now - timedelta(days=29), Decimal("10000")),
            (now - timedelta(days=20), Decimal("10500")),
            (now - timedelta(days=10), Decimal("11000")),
            (now - timedelta(days=5), Decimal("11500")),
        ]

        period_perf = calc.calculate_period_performance(
            current_value, historical_values, "30d"
        )

        assert period_perf is not None
        assert period_perf.period == "30d"
        # Return from 10000 to 12000 = 2000 (20%)
        assert Decimal(period_perf.total_return) == Decimal("2000")
        assert Decimal(period_perf.total_return_pct) == Decimal("20")

    def test_period_performance_invalid_period(self):
        """Test invalid period returns None"""
        calc = PerformanceCalculator()

        result = calc.calculate_period_performance(
            Decimal("10000"),
            [],
            "invalid"
        )

        assert result is None

    def test_period_performance_insufficient_data(self):
        """Test period with insufficient historical data"""
        calc = PerformanceCalculator()

        result = calc.calculate_period_performance(
            Decimal("10000"),
            [(datetime.now(), Decimal("10000"))],  # Only one point
            "7d"
        )

        assert result is None


class TestEdgeCases:
    """Edge cases for financial calculations"""

    def test_decimal_precision_in_returns(self):
        """Test decimal precision is maintained in calculations"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000.12345678"),
            cash_balance=Decimal("10000.12345678"),
            total_value=Decimal("10000.12345678"),
            total_pnl=Decimal("0.00000001"),
            total_return_pct=Decimal("0.0000001")
        )

        metrics = calc.calculate_metrics(portfolio)

        # Precision should be maintained
        assert metrics.total_pnl == Decimal("0.00000001")

    def test_empty_daily_values(self):
        """Test handling of empty daily values"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("10000"),
            total_value=Decimal("10000")
        )

        metrics = calc.calculate_metrics(portfolio, daily_values=[])

        # Should not crash, returns should be empty/None
        assert metrics.sharpe_ratio is None
        assert metrics.volatility is None

    def test_large_values(self):
        """Test handling of large portfolio values"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("1000000000"),  # 1 billion
            cash_balance=Decimal("1000000000"),
            total_value=Decimal("1500000000"),  # 1.5 billion
            total_pnl=Decimal("500000000"),
            total_return_pct=Decimal("50")
        )

        metrics = calc.calculate_metrics(portfolio)

        assert metrics.total_return == Decimal("500000000")
        assert metrics.total_return_pct == Decimal("50")

    def test_very_small_returns(self):
        """Test handling of very small daily returns"""
        calc = PerformanceCalculator()

        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("10000"),
            total_value=Decimal("10000")
        )

        # Very small changes
        daily_values = [
            Decimal("10000.00"),
            Decimal("10000.01"),
            Decimal("10000.02"),
            Decimal("10000.01"),
            Decimal("10000.03"),
        ]

        metrics = calc.calculate_metrics(portfolio, daily_values=daily_values)

        # Should handle without overflow/underflow
        assert metrics.volatility is not None

    def test_negative_portfolio_value(self):
        """Test handling of negative portfolio value (edge case)"""
        calc = PerformanceCalculator()

        # This shouldn't happen in practice but test robustness
        portfolio = Portfolio(
            portfolio_id="test",
            initial_capital=Decimal("10000"),
            cash_balance=Decimal("0"),
            total_value=Decimal("0"),
            total_pnl=Decimal("-10000"),
            total_return_pct=Decimal("-100")
        )

        metrics = calc.calculate_metrics(portfolio)

        assert metrics.total_return == Decimal("-10000")
        assert metrics.total_return_pct == Decimal("-100")
