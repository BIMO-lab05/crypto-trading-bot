"""
Unit Tests for Advanced Performance Metrics - Phase 5.2
Purpose: Comprehensive test coverage for institutional-grade metrics

Test coverage includes:
- Risk-Adjusted Metrics (Sharpe, Sortino, Calmar, Omega, Treynor)
- Drawdown Analysis (Max DD, Ulcer Index, Pain Index, Recovery Factor)
- Win/Loss Metrics (Win Rate, Profit Factor, Kelly %, Streaks)
- Risk Metrics (VaR, CVaR, MAE, MFE, Risk of Ruin)
- Trade Efficiency (Duration, Frequency, Capital Utilization)
- Benchmark Comparison (Alpha, Beta, Information Ratio)
- Edge cases (no trades, all wins, all losses)

Author: Backend Developer Agent
Date: 2025-12-12
"""

import pytest
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import List

from app.analytics.advanced_metrics import (
    AdvancedMetricsCalculator,
    TradeMetadata,
    RiskAdjustedMetrics,
    DrawdownMetrics,
    WinLossMetrics,
    RiskMetrics,
    EfficiencyMetrics,
    BenchmarkComparison,
    AllMetrics,
    MetricsPeriod,
    RiskLevel,
    DrawdownStatus,
    get_advanced_metrics_calculator,
    reset_advanced_metrics_calculator,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def calculator():
    """Create a fresh calculator for each test"""
    reset_advanced_metrics_calculator()
    return AdvancedMetricsCalculator(
        initial_capital=10000.0,
        risk_free_rate=0.02,
    )


@pytest.fixture
def sample_trades() -> List[TradeMetadata]:
    """Create sample trades for testing"""
    base_time = datetime.now(timezone.utc) - timedelta(days=30)

    trades = [
        # Mix of winners and losers
        TradeMetadata(
            trade_id="tr_001",
            timestamp=base_time + timedelta(days=1),
            pnl=150.0,
            pnl_pct=0.015,
            strategy="momentum",
            symbol="BTCUSDT",
            direction="long",
            duration_seconds=3600,
            is_winner=True,
            entry_price=50000.0,
            exit_price=50750.0,
            position_size=0.2,
            max_adverse_excursion=0.005,
            max_favorable_excursion=0.02,
        ),
        TradeMetadata(
            trade_id="tr_002",
            timestamp=base_time + timedelta(days=2),
            pnl=-80.0,
            pnl_pct=-0.008,
            strategy="momentum",
            symbol="ETHUSDT",
            direction="short",
            duration_seconds=7200,
            is_winner=False,
            entry_price=3000.0,
            exit_price=3024.0,
            position_size=0.5,
            max_adverse_excursion=0.012,
            max_favorable_excursion=0.003,
        ),
        TradeMetadata(
            trade_id="tr_003",
            timestamp=base_time + timedelta(days=3),
            pnl=200.0,
            pnl_pct=0.02,
            strategy="mean_reversion",
            symbol="BTCUSDT",
            direction="long",
            duration_seconds=5400,
            is_winner=True,
            entry_price=51000.0,
            exit_price=52020.0,
            position_size=0.19,
            max_adverse_excursion=0.003,
            max_favorable_excursion=0.025,
        ),
        TradeMetadata(
            trade_id="tr_004",
            timestamp=base_time + timedelta(days=4),
            pnl=120.0,
            pnl_pct=0.012,
            strategy="momentum",
            symbol="SOLUSDT",
            direction="long",
            duration_seconds=4800,
            is_winner=True,
            entry_price=150.0,
            exit_price=151.8,
            position_size=6.0,
            max_adverse_excursion=0.002,
            max_favorable_excursion=0.018,
        ),
        TradeMetadata(
            trade_id="tr_005",
            timestamp=base_time + timedelta(days=5),
            pnl=-50.0,
            pnl_pct=-0.005,
            strategy="mean_reversion",
            symbol="ETHUSDT",
            direction="short",
            duration_seconds=1800,
            is_winner=False,
            entry_price=3100.0,
            exit_price=3115.5,
            position_size=0.3,
            max_adverse_excursion=0.008,
            max_favorable_excursion=0.001,
        ),
        # More trades for statistical significance
        TradeMetadata(
            trade_id="tr_006",
            timestamp=base_time + timedelta(days=6),
            pnl=180.0,
            pnl_pct=0.018,
            strategy="momentum",
            symbol="BTCUSDT",
            direction="long",
            duration_seconds=6000,
            is_winner=True,
            entry_price=52000.0,
            exit_price=52936.0,
            position_size=0.18,
            max_adverse_excursion=0.004,
            max_favorable_excursion=0.022,
        ),
        TradeMetadata(
            trade_id="tr_007",
            timestamp=base_time + timedelta(days=7),
            pnl=-100.0,
            pnl_pct=-0.01,
            strategy="mean_reversion",
            symbol="SOLUSDT",
            direction="short",
            duration_seconds=2400,
            is_winner=False,
            entry_price=155.0,
            exit_price=156.55,
            position_size=6.5,
            max_adverse_excursion=0.015,
            max_favorable_excursion=0.002,
        ),
        TradeMetadata(
            trade_id="tr_008",
            timestamp=base_time + timedelta(days=8),
            pnl=250.0,
            pnl_pct=0.025,
            strategy="momentum",
            symbol="BTCUSDT",
            direction="long",
            duration_seconds=8000,
            is_winner=True,
            entry_price=53000.0,
            exit_price=54325.0,
            position_size=0.19,
            max_adverse_excursion=0.003,
            max_favorable_excursion=0.03,
        ),
        TradeMetadata(
            trade_id="tr_009",
            timestamp=base_time + timedelta(days=9),
            pnl=90.0,
            pnl_pct=0.009,
            strategy="mean_reversion",
            symbol="ETHUSDT",
            direction="long",
            duration_seconds=3000,
            is_winner=True,
            entry_price=3200.0,
            exit_price=3228.8,
            position_size=0.3,
            max_adverse_excursion=0.002,
            max_favorable_excursion=0.012,
        ),
        TradeMetadata(
            trade_id="tr_010",
            timestamp=base_time + timedelta(days=10),
            pnl=-60.0,
            pnl_pct=-0.006,
            strategy="momentum",
            symbol="SOLUSDT",
            direction="short",
            duration_seconds=2000,
            is_winner=False,
            entry_price=160.0,
            exit_price=160.96,
            position_size=6.0,
            max_adverse_excursion=0.01,
            max_favorable_excursion=0.002,
        ),
    ]

    return trades


@pytest.fixture
def benchmark_returns() -> List[float]:
    """Create sample benchmark returns aligned with trades"""
    return [0.01, -0.005, 0.015, 0.008, -0.003, 0.012, -0.008, 0.02, 0.005, -0.004]


@pytest.fixture
def loaded_calculator(calculator, sample_trades, benchmark_returns):
    """Calculator with loaded trades and benchmark"""
    calculator.add_trades_batch(sample_trades)
    calculator.set_benchmark_returns(benchmark_returns)
    return calculator


# =============================================================================
# RISK-ADJUSTED METRICS TESTS
# =============================================================================

class TestRiskAdjustedMetrics:
    """Tests for risk-adjusted return metrics"""

    def test_sharpe_ratio_positive(self, loaded_calculator):
        """Test Sharpe ratio calculation with positive returns"""
        metrics = loaded_calculator.get_risk_adjusted_metrics()

        # Should be positive for overall profitable strategy
        assert metrics.sharpe_ratio > 0
        assert isinstance(metrics.sharpe_ratio, float)

    def test_sharpe_ratio_known_values(self, calculator):
        """Test Sharpe ratio with known return values"""
        # Add trades with known returns: [0.01, 0.02, 0.015, 0.01, 0.025]
        base_time = datetime.now(timezone.utc)
        returns = [0.01, 0.02, 0.015, 0.01, 0.025]

        for i, ret in enumerate(returns):
            trade = TradeMetadata(
                trade_id=f"tr_{i}",
                timestamp=base_time + timedelta(hours=i),
                pnl=100.0 * ret,
                pnl_pct=ret,
                strategy="test",
                symbol="BTCUSDT",
                direction="long",
                is_winner=ret > 0,
            )
            calculator.add_trade(trade)

        metrics = calculator.get_risk_adjusted_metrics()

        # Manual calculation
        returns_arr = np.array(returns)
        mean_ret = np.mean(returns_arr)
        std_ret = np.std(returns_arr, ddof=1)
        expected_sharpe = (mean_ret - 0.02/252) / std_ret * np.sqrt(5)

        # Allow small tolerance for floating point differences
        assert abs(metrics.sharpe_ratio - expected_sharpe) < 0.1

    def test_sortino_ratio_calculation(self, loaded_calculator):
        """Test Sortino ratio calculation"""
        metrics = loaded_calculator.get_risk_adjusted_metrics()

        # Sortino should be >= Sharpe since it only penalizes downside
        assert metrics.sortino_ratio >= metrics.sharpe_ratio * 0.8  # Allow some variance
        assert isinstance(metrics.sortino_ratio, float)

    def test_sortino_all_positive_returns(self, calculator):
        """Test Sortino with all positive returns (infinite)"""
        base_time = datetime.now(timezone.utc)

        for i in range(5):
            trade = TradeMetadata(
                trade_id=f"tr_{i}",
                timestamp=base_time + timedelta(hours=i),
                pnl=100.0,
                pnl_pct=0.01,
                strategy="test",
                symbol="BTCUSDT",
                direction="long",
                is_winner=True,
            )
            calculator.add_trade(trade)

        metrics = calculator.get_risk_adjusted_metrics()

        # With no negative returns, Sortino should be infinity or very large
        assert metrics.sortino_ratio == float('inf') or metrics.sortino_ratio > 10

    def test_calmar_ratio_calculation(self, loaded_calculator):
        """Test Calmar ratio calculation"""
        metrics = loaded_calculator.get_risk_adjusted_metrics()

        # Calmar should be defined if there's a drawdown
        assert isinstance(metrics.calmar_ratio, float)

    def test_omega_ratio_calculation(self, loaded_calculator):
        """Test Omega ratio calculation"""
        metrics = loaded_calculator.get_risk_adjusted_metrics()

        # Omega > 1 indicates more gains than losses
        assert metrics.omega_ratio > 0
        assert isinstance(metrics.omega_ratio, float)

    def test_treynor_ratio_calculation(self, loaded_calculator):
        """Test Treynor ratio with benchmark"""
        metrics = loaded_calculator.get_risk_adjusted_metrics()

        # Should have a valid Treynor ratio with benchmark
        assert isinstance(metrics.treynor_ratio, float)

    def test_information_ratio_calculation(self, loaded_calculator):
        """Test Information ratio calculation"""
        metrics = loaded_calculator.get_risk_adjusted_metrics()

        # Information ratio should be calculated with benchmark
        assert isinstance(metrics.information_ratio, float)

    def test_gain_to_pain_ratio(self, loaded_calculator):
        """Test Gain to Pain ratio"""
        metrics = loaded_calculator.get_risk_adjusted_metrics()

        # With overall positive returns, should be > 0
        total_pnl = sum(t.pnl for t in loaded_calculator._trades)
        if total_pnl > 0:
            assert metrics.gain_to_pain_ratio > 0


# =============================================================================
# DRAWDOWN METRICS TESTS
# =============================================================================

class TestDrawdownMetrics:
    """Tests for drawdown analysis metrics"""

    def test_max_drawdown_calculation(self, loaded_calculator):
        """Test maximum drawdown calculation"""
        metrics = loaded_calculator.get_drawdown_metrics()

        # Max drawdown should be non-positive
        assert metrics.max_drawdown <= 0
        # As percentage, should be reasonable
        assert metrics.max_drawdown >= -1.0  # Not more than 100%

    def test_drawdown_with_losing_streak(self, calculator):
        """Test drawdown calculation with a losing streak"""
        base_time = datetime.now(timezone.utc)

        # Start with profit
        calculator.add_trade(TradeMetadata(
            trade_id="tr_1",
            timestamp=base_time,
            pnl=500.0,
            pnl_pct=0.05,
            strategy="test",
            symbol="BTCUSDT",
            direction="long",
            is_winner=True,
        ))

        # Then consecutive losses
        for i in range(3):
            calculator.add_trade(TradeMetadata(
                trade_id=f"tr_{i+2}",
                timestamp=base_time + timedelta(hours=i+1),
                pnl=-200.0,
                pnl_pct=-0.02,
                strategy="test",
                symbol="BTCUSDT",
                direction="long",
                is_winner=False,
            ))

        metrics = calculator.get_drawdown_metrics()

        # Should have meaningful drawdown
        assert metrics.max_drawdown < 0

    def test_ulcer_index_calculation(self, loaded_calculator):
        """Test Ulcer Index calculation"""
        metrics = loaded_calculator.get_drawdown_metrics()

        # Ulcer Index should be non-negative
        assert metrics.ulcer_index >= 0
        assert isinstance(metrics.ulcer_index, float)

    def test_pain_index_calculation(self, loaded_calculator):
        """Test Pain Index calculation"""
        metrics = loaded_calculator.get_drawdown_metrics()

        # Pain Index should be non-negative
        assert metrics.pain_index >= 0
        assert isinstance(metrics.pain_index, float)

    def test_recovery_factor_calculation(self, loaded_calculator):
        """Test Recovery Factor calculation"""
        metrics = loaded_calculator.get_drawdown_metrics()

        # Recovery factor should be calculated
        assert isinstance(metrics.recovery_factor, float)

    def test_average_drawdown(self, loaded_calculator):
        """Test average drawdown calculation"""
        metrics = loaded_calculator.get_drawdown_metrics()

        # Average drawdown should be between 0 and max drawdown
        assert metrics.avg_drawdown <= 0
        assert metrics.avg_drawdown >= metrics.max_drawdown

    def test_time_underwater(self, loaded_calculator):
        """Test time underwater percentage"""
        metrics = loaded_calculator.get_drawdown_metrics()

        # Should be between 0 and 1
        assert 0 <= metrics.time_underwater_pct <= 1


# =============================================================================
# WIN/LOSS METRICS TESTS
# =============================================================================

class TestWinLossMetrics:
    """Tests for win/loss analysis metrics"""

    def test_win_rate_calculation(self, loaded_calculator):
        """Test win rate calculation"""
        metrics = loaded_calculator.get_win_loss_metrics()

        # Win rate should be between 0 and 1
        assert 0 <= metrics.win_rate <= 1

        # Manual verification
        winners = sum(1 for t in loaded_calculator._trades if t.is_winner)
        expected_rate = winners / len(loaded_calculator._trades)
        assert abs(metrics.win_rate - expected_rate) < 0.001

    def test_profit_factor_calculation(self, loaded_calculator):
        """Test profit factor calculation"""
        metrics = loaded_calculator.get_win_loss_metrics()

        # Profit factor should be positive
        assert metrics.profit_factor > 0

        # With overall profit, should be > 1
        total_pnl = sum(t.pnl for t in loaded_calculator._trades)
        if total_pnl > 0:
            assert metrics.profit_factor > 1

    def test_payoff_ratio_calculation(self, loaded_calculator):
        """Test payoff ratio (avg win / avg loss)"""
        metrics = loaded_calculator.get_win_loss_metrics()

        # Payoff ratio should be positive
        assert metrics.payoff_ratio > 0

    def test_expectancy_calculation(self, loaded_calculator):
        """Test expectancy calculation"""
        metrics = loaded_calculator.get_win_loss_metrics()

        # Expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
        expected_expectancy = (metrics.win_rate * metrics.avg_win) - \
                            ((1 - metrics.win_rate) * metrics.avg_loss)

        # Allow small tolerance
        assert abs(metrics.expectancy - expected_expectancy) < 1.0

    def test_kelly_percentage_calculation(self, loaded_calculator):
        """Test Kelly percentage calculation"""
        metrics = loaded_calculator.get_win_loss_metrics()

        # Kelly should be between 0 and 0.5 (half Kelly)
        assert 0 <= metrics.kelly_percentage <= 0.5

    def test_consecutive_streaks(self, calculator):
        """Test consecutive win/loss streak calculation"""
        base_time = datetime.now(timezone.utc)

        # 3 wins, 2 losses, 4 wins pattern
        pattern = [True, True, True, False, False, True, True, True, True]

        for i, is_winner in enumerate(pattern):
            trade = TradeMetadata(
                trade_id=f"tr_{i}",
                timestamp=base_time + timedelta(hours=i),
                pnl=100.0 if is_winner else -50.0,
                pnl_pct=0.01 if is_winner else -0.005,
                strategy="test",
                symbol="BTCUSDT",
                direction="long",
                is_winner=is_winner,
            )
            calculator.add_trade(trade)

        metrics = calculator.get_win_loss_metrics()

        # Max consecutive wins should be 4
        assert metrics.consecutive_wins == 4
        # Max consecutive losses should be 2
        assert metrics.consecutive_losses == 2
        # Current streak should be 4 (wins)
        assert metrics.current_streak == 4

    def test_largest_win_loss(self, loaded_calculator):
        """Test largest win and loss tracking"""
        metrics = loaded_calculator.get_win_loss_metrics()

        # Largest win should equal max of winning trades
        winners = [t.pnl for t in loaded_calculator._trades if t.is_winner]
        assert metrics.largest_win == max(winners)

        # Largest loss should equal abs of min of losing trades
        losers = [t.pnl for t in loaded_calculator._trades if not t.is_winner and t.pnl < 0]
        assert metrics.largest_loss == abs(min(losers))


# =============================================================================
# RISK METRICS TESTS
# =============================================================================

class TestRiskMetrics:
    """Tests for risk quantification metrics"""

    def test_var_calculation(self, loaded_calculator):
        """Test Value at Risk calculation"""
        metrics = loaded_calculator.get_risk_metrics()

        # VaR 99% should be greater than VaR 95%
        assert metrics.var_99 >= metrics.var_95

        # VaR should be non-negative (as loss)
        assert metrics.var_95 >= 0
        assert metrics.var_99 >= 0

    def test_cvar_calculation(self, loaded_calculator):
        """Test Conditional VaR calculation"""
        metrics = loaded_calculator.get_risk_metrics()

        # CVaR should be >= VaR (expected shortfall is worse case)
        assert metrics.cvar_95 >= metrics.var_95
        assert metrics.cvar_99 >= metrics.var_99

    def test_beta_calculation(self, loaded_calculator):
        """Test Beta calculation with benchmark"""
        metrics = loaded_calculator.get_risk_metrics()

        # Beta should be reasonable (typically -2 to 2)
        assert -3 <= metrics.beta <= 3

    def test_mae_mfe_calculation(self, loaded_calculator):
        """Test MAE and MFE calculation"""
        metrics = loaded_calculator.get_risk_metrics()

        # MAE and MFE should be non-negative percentages
        assert metrics.max_adverse_excursion >= 0
        assert metrics.max_favorable_excursion >= 0

    def test_risk_of_ruin(self, loaded_calculator):
        """Test Risk of Ruin calculation"""
        metrics = loaded_calculator.get_risk_metrics()

        # Risk of ruin should be between 0 and 1
        assert 0 <= metrics.risk_of_ruin <= 1

    def test_volatility_calculation(self, loaded_calculator):
        """Test volatility calculation"""
        metrics = loaded_calculator.get_risk_metrics()

        # Volatility should be non-negative
        assert metrics.volatility >= 0
        assert metrics.downside_volatility >= 0

        # Downside volatility should be <= total volatility
        assert metrics.downside_volatility <= metrics.volatility * 1.5  # Allow some tolerance

    def test_risk_level_classification(self, loaded_calculator):
        """Test risk level classification"""
        metrics = loaded_calculator.get_risk_metrics()

        # Should be a valid risk level
        assert metrics.risk_level in [
            RiskLevel.VERY_LOW, RiskLevel.LOW, RiskLevel.MODERATE,
            RiskLevel.HIGH, RiskLevel.VERY_HIGH
        ]

    def test_tail_ratio(self, loaded_calculator):
        """Test tail ratio calculation"""
        metrics = loaded_calculator.get_risk_metrics()

        # Tail ratio should be positive
        assert metrics.tail_ratio > 0


# =============================================================================
# EFFICIENCY METRICS TESTS
# =============================================================================

class TestEfficiencyMetrics:
    """Tests for trade efficiency metrics"""

    def test_avg_trade_duration(self, loaded_calculator):
        """Test average trade duration calculation"""
        metrics = loaded_calculator.get_efficiency_metrics()

        # Duration should be positive
        assert metrics.avg_trade_duration > 0

        # Manual verification
        durations = [t.duration_seconds / 3600 for t in loaded_calculator._trades if t.duration_seconds > 0]
        expected_duration = np.mean(durations)
        assert abs(metrics.avg_trade_duration - expected_duration) < 0.01

    def test_trades_per_period(self, loaded_calculator):
        """Test trades per day/week/month calculation"""
        metrics = loaded_calculator.get_efficiency_metrics()

        # All should be non-negative
        assert metrics.trades_per_day >= 0
        assert metrics.trades_per_week >= 0
        assert metrics.trades_per_month >= 0

        # Weekly should be ~7x daily
        if metrics.trades_per_day > 0:
            assert 5 <= metrics.trades_per_week / metrics.trades_per_day <= 9

    def test_position_size(self, loaded_calculator):
        """Test average position size calculation"""
        metrics = loaded_calculator.get_efficiency_metrics()

        # Position size should be between 0 and 1 (percentage)
        assert 0 <= metrics.avg_position_size <= 1

    def test_capital_utilization(self, loaded_calculator):
        """Test capital utilization calculation"""
        metrics = loaded_calculator.get_efficiency_metrics()

        # Should be between 0 and 1
        assert 0 <= metrics.capital_utilization <= 1

    def test_turnover_ratio(self, loaded_calculator):
        """Test turnover ratio calculation"""
        metrics = loaded_calculator.get_efficiency_metrics()

        # Turnover ratio should be non-negative
        assert metrics.turnover_ratio >= 0


# =============================================================================
# BENCHMARK COMPARISON TESTS
# =============================================================================

class TestBenchmarkComparison:
    """Tests for benchmark comparison metrics"""

    def test_excess_return_calculation(self, loaded_calculator):
        """Test excess return calculation"""
        comparison = loaded_calculator.get_benchmark_comparison()

        # Excess return = strategy - benchmark
        expected_excess = comparison.strategy_return - comparison.benchmark_return
        assert abs(comparison.excess_return - expected_excess) < 0.0001

    def test_alpha_calculation(self, loaded_calculator):
        """Test alpha calculation"""
        comparison = loaded_calculator.get_benchmark_comparison()

        # Alpha should be calculated
        assert isinstance(comparison.alpha, float)

    def test_correlation(self, loaded_calculator):
        """Test correlation calculation"""
        comparison = loaded_calculator.get_benchmark_comparison()

        # Correlation should be between -1 and 1
        assert -1 <= comparison.correlation <= 1

    def test_tracking_error(self, loaded_calculator):
        """Test tracking error calculation"""
        comparison = loaded_calculator.get_benchmark_comparison()

        # Tracking error should be non-negative
        assert comparison.tracking_error >= 0

    def test_capture_ratios(self, loaded_calculator):
        """Test up/down capture ratios"""
        comparison = loaded_calculator.get_benchmark_comparison()

        # Capture ratios can be any value
        assert isinstance(comparison.up_capture, float)
        assert isinstance(comparison.down_capture, float)


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions"""

    def test_no_trades(self, calculator):
        """Test metrics with no trades"""
        metrics = calculator.get_all_metrics()

        # Should return default values without errors
        assert metrics.total_trades == 0
        assert metrics.total_pnl == 0.0

    def test_single_trade(self, calculator):
        """Test metrics with single trade"""
        trade = TradeMetadata(
            trade_id="tr_001",
            timestamp=datetime.now(timezone.utc),
            pnl=100.0,
            pnl_pct=0.01,
            strategy="test",
            symbol="BTCUSDT",
            direction="long",
            is_winner=True,
        )
        calculator.add_trade(trade)

        metrics = calculator.get_all_metrics()

        assert metrics.total_trades == 1
        assert metrics.win_loss.win_rate == 1.0

    def test_all_winners(self, calculator):
        """Test metrics when all trades are winners"""
        base_time = datetime.now(timezone.utc)

        for i in range(10):
            trade = TradeMetadata(
                trade_id=f"tr_{i}",
                timestamp=base_time + timedelta(hours=i),
                pnl=100.0,
                pnl_pct=0.01,
                strategy="test",
                symbol="BTCUSDT",
                direction="long",
                is_winner=True,
            )
            calculator.add_trade(trade)

        metrics = calculator.get_all_metrics()

        assert metrics.win_loss.win_rate == 1.0
        assert metrics.win_loss.consecutive_losses == 0
        assert metrics.win_loss.avg_loss == 0.0

    def test_all_losers(self, calculator):
        """Test metrics when all trades are losers"""
        base_time = datetime.now(timezone.utc)

        for i in range(10):
            trade = TradeMetadata(
                trade_id=f"tr_{i}",
                timestamp=base_time + timedelta(hours=i),
                pnl=-50.0,
                pnl_pct=-0.005,
                strategy="test",
                symbol="BTCUSDT",
                direction="long",
                is_winner=False,
            )
            calculator.add_trade(trade)

        metrics = calculator.get_all_metrics()

        assert metrics.win_loss.win_rate == 0.0
        assert metrics.win_loss.consecutive_wins == 0
        assert metrics.win_loss.profit_factor == 0.0
        assert metrics.risk.risk_of_ruin == 1.0  # Certain ruin with negative edge

    def test_identical_returns(self, calculator):
        """Test with identical returns (zero volatility)"""
        base_time = datetime.now(timezone.utc)

        for i in range(5):
            trade = TradeMetadata(
                trade_id=f"tr_{i}",
                timestamp=base_time + timedelta(hours=i),
                pnl=100.0,
                pnl_pct=0.01,
                strategy="test",
                symbol="BTCUSDT",
                direction="long",
                is_winner=True,
            )
            calculator.add_trade(trade)

        metrics = calculator.get_risk_adjusted_metrics()

        # Sharpe should be 0 or very large with zero volatility
        assert metrics.sharpe_ratio == 0.0 or abs(metrics.sharpe_ratio) > 100

    def test_alternating_wins_losses(self, calculator):
        """Test with alternating wins and losses"""
        base_time = datetime.now(timezone.utc)

        for i in range(10):
            is_winner = i % 2 == 0
            trade = TradeMetadata(
                trade_id=f"tr_{i}",
                timestamp=base_time + timedelta(hours=i),
                pnl=100.0 if is_winner else -50.0,
                pnl_pct=0.01 if is_winner else -0.005,
                strategy="test",
                symbol="BTCUSDT",
                direction="long",
                is_winner=is_winner,
            )
            calculator.add_trade(trade)

        metrics = calculator.get_win_loss_metrics()

        assert metrics.win_rate == 0.5
        assert metrics.consecutive_wins == 1
        assert metrics.consecutive_losses == 1


# =============================================================================
# STATE MANAGEMENT TESTS
# =============================================================================

class TestStateManagement:
    """Tests for state management functionality"""

    def test_get_and_load_state(self, loaded_calculator):
        """Test state persistence"""
        # Get state
        state = loaded_calculator.get_state()

        # Create new calculator and load state
        new_calculator = AdvancedMetricsCalculator()
        new_calculator.load_state(state)

        # Verify state is restored
        assert len(new_calculator._trades) == len(loaded_calculator._trades)
        assert new_calculator._current_equity == loaded_calculator._current_equity

    def test_reset(self, loaded_calculator):
        """Test calculator reset"""
        loaded_calculator.reset()

        assert len(loaded_calculator._trades) == 0
        assert loaded_calculator._current_equity == loaded_calculator.initial_capital
        assert loaded_calculator._peak_equity == loaded_calculator.initial_capital

    def test_summary(self, loaded_calculator):
        """Test quick summary method"""
        summary = loaded_calculator.get_summary()

        assert "total_trades" in summary
        assert "total_pnl" in summary
        assert "current_equity" in summary
        assert "win_rate" in summary


# =============================================================================
# ALL METRICS COMBINED TEST
# =============================================================================

class TestAllMetricsCombined:
    """Tests for the combined all metrics response"""

    def test_all_metrics_structure(self, loaded_calculator):
        """Test that all metrics contains all required fields"""
        metrics = loaded_calculator.get_all_metrics()

        # Check structure
        assert isinstance(metrics.risk_adjusted, RiskAdjustedMetrics)
        assert isinstance(metrics.drawdown, DrawdownMetrics)
        assert isinstance(metrics.win_loss, WinLossMetrics)
        assert isinstance(metrics.risk, RiskMetrics)
        assert isinstance(metrics.efficiency, EfficiencyMetrics)

        # Check summary fields
        assert metrics.total_trades == len(loaded_calculator._trades)
        assert isinstance(metrics.total_pnl, float)
        assert isinstance(metrics.generated_at, datetime)

    def test_to_dict_conversion(self, loaded_calculator):
        """Test conversion to dictionary for API response"""
        metrics = loaded_calculator.get_all_metrics()
        metrics_dict = metrics.to_dict()

        # Check all sections exist
        assert "risk_adjusted" in metrics_dict
        assert "drawdown" in metrics_dict
        assert "win_loss" in metrics_dict
        assert "risk" in metrics_dict
        assert "efficiency" in metrics_dict

        # Check nested structure
        assert "sharpe_ratio" in metrics_dict["risk_adjusted"]
        assert "max_drawdown" in metrics_dict["drawdown"]
        assert "win_rate" in metrics_dict["win_loss"]
        assert "var_95" in metrics_dict["risk"]
        assert "trades_per_day" in metrics_dict["efficiency"]


# =============================================================================
# PERIOD COMPARISON TESTS
# =============================================================================

class TestPeriodComparison:
    """Tests for period comparison functionality"""

    def test_compare_periods(self, loaded_calculator):
        """Test period comparison"""
        comparison = loaded_calculator.compare_periods(period_days=5)

        # Check structure
        assert "period_days" in comparison
        assert "current_period" in comparison
        assert "previous_period" in comparison
        assert "changes" in comparison

        # Check changes contain expected fields
        assert "trades_change" in comparison["changes"]
        assert "pnl_change" in comparison["changes"]


# =============================================================================
# MATHEMATICAL CORRECTNESS TESTS
# =============================================================================

class TestMathematicalCorrectness:
    """Tests for mathematical correctness of calculations"""

    def test_sortino_formula(self, calculator):
        """Verify Sortino ratio formula correctness"""
        returns = [0.02, -0.01, 0.03, -0.02, 0.01, 0.04, -0.005, 0.015, -0.01, 0.025]
        base_time = datetime.now(timezone.utc)

        for i, ret in enumerate(returns):
            trade = TradeMetadata(
                trade_id=f"tr_{i}",
                timestamp=base_time + timedelta(hours=i),
                pnl=100.0 * ret,
                pnl_pct=ret,
                strategy="test",
                symbol="BTCUSDT",
                direction="long",
                is_winner=ret > 0,
            )
            calculator.add_trade(trade)

        metrics = calculator.get_risk_adjusted_metrics()

        # Manual Sortino calculation
        returns_arr = np.array(returns)
        mean_ret = np.mean(returns_arr)
        downside = returns_arr[returns_arr < 0]
        downside_std = np.std(downside, ddof=1)
        expected_sortino = (mean_ret - 0.02/252) / downside_std * np.sqrt(len(returns))

        # Allow reasonable tolerance
        assert abs(metrics.sortino_ratio - expected_sortino) < 0.5

    def test_omega_formula(self, calculator):
        """Verify Omega ratio formula correctness"""
        returns = [0.02, -0.01, 0.03, -0.02, 0.01, 0.04, -0.005, 0.015, -0.01, 0.025]
        base_time = datetime.now(timezone.utc)

        for i, ret in enumerate(returns):
            trade = TradeMetadata(
                trade_id=f"tr_{i}",
                timestamp=base_time + timedelta(hours=i),
                pnl=100.0 * ret,
                pnl_pct=ret,
                strategy="test",
                symbol="BTCUSDT",
                direction="long",
                is_winner=ret > 0,
            )
            calculator.add_trade(trade)

        metrics = calculator.get_risk_adjusted_metrics()

        # Manual Omega calculation
        returns_arr = np.array(returns)
        gains = returns_arr[returns_arr > 0]
        losses = -returns_arr[returns_arr < 0]
        expected_omega = np.sum(gains) / np.sum(losses)

        assert abs(metrics.omega_ratio - expected_omega) < 0.01

    def test_kelly_formula(self, calculator):
        """Verify Kelly percentage formula correctness"""
        # Create specific win/loss scenario
        base_time = datetime.now(timezone.utc)

        # 60% win rate, avg win = 150, avg loss = 100
        for i in range(100):
            is_winner = i < 60
            trade = TradeMetadata(
                trade_id=f"tr_{i}",
                timestamp=base_time + timedelta(hours=i),
                pnl=150.0 if is_winner else -100.0,
                pnl_pct=0.015 if is_winner else -0.01,
                strategy="test",
                symbol="BTCUSDT",
                direction="long",
                is_winner=is_winner,
            )
            calculator.add_trade(trade)

        metrics = calculator.get_win_loss_metrics()

        # Kelly = W - (1-W)/R = 0.6 - 0.4/1.5 = 0.333...
        # Half Kelly (safety factor) = 0.167
        expected_kelly = (0.6 - 0.4/1.5) * 0.5

        # Allow some tolerance due to rounding
        assert abs(metrics.kelly_percentage - expected_kelly) < 0.05
