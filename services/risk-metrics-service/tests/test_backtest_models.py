"""
Unit tests for Backtest Models - Data structures for historical risk analysis
Tests model validation, serialization, and edge cases
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from pydantic import ValidationError

from app.backtest_models import (
    BacktestConfig,
    PortfolioSnapshot,
    BacktestMetrics,
    BacktestResult,
    RiskViolation,
    StrategyComparison,
    WalkForwardResult
)


@pytest.mark.unit
@pytest.mark.models
class TestBacktestConfig:
    """Tests for BacktestConfig model"""

    def test_backtest_config_valid(self):
        """Test creating valid backtest configuration"""
        start = datetime(2023, 1, 1)
        end = datetime(2023, 12, 31)

        config = BacktestConfig(
            start_date=start,
            end_date=end,
            initial_capital=Decimal("100000"),
            risk_limits={"max_loss": 0.05},
            rebalance_frequency="daily"
        )

        assert config.start_date == start
        assert config.end_date == end
        assert config.initial_capital == Decimal("100000")
        assert config.rebalance_frequency == "daily"

    def test_backtest_config_default_capital(self):
        """Test default initial capital value"""
        config = BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31)
        )

        assert config.initial_capital == Decimal("10000")

    def test_backtest_config_missing_required_dates(self):
        """Test that start_date and end_date are required"""
        with pytest.raises(ValidationError):
            BacktestConfig()

    def test_backtest_config_custom_risk_limits(self):
        """Test setting custom risk limits"""
        limits = {
            "max_loss": 0.02,
            "max_drawdown": 0.10,
            "max_leverage": 2.0
        }

        config = BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            risk_limits=limits
        )

        assert config.risk_limits == limits

    def test_backtest_config_rebalance_frequencies(self):
        """Test different rebalance frequency options"""
        frequencies = ["daily", "weekly", "monthly"]

        for freq in frequencies:
            config = BacktestConfig(
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                rebalance_frequency=freq
            )
            assert config.rebalance_frequency == freq


@pytest.mark.unit
@pytest.mark.models
class TestPortfolioSnapshot:
    """Tests for PortfolioSnapshot model"""

    def test_portfolio_snapshot_valid(self):
        """Test creating valid portfolio snapshot"""
        snapshot = PortfolioSnapshot(
            timestamp=datetime(2023, 6, 15, 12, 0, 0),
            total_value=Decimal("50000"),
            cash_balance=Decimal("5000"),
            positions=[
                {"symbol": "BTC", "quantity": 1, "price": 30000},
                {"symbol": "ETH", "quantity": 10, "price": 2000}
            ],
            daily_return=0.025,
            cumulative_return=0.15
        )

        assert snapshot.total_value == Decimal("50000")
        assert len(snapshot.positions) == 2
        assert snapshot.daily_return == 0.025

    def test_portfolio_snapshot_empty_positions(self):
        """Test portfolio snapshot with no positions"""
        snapshot = PortfolioSnapshot(
            timestamp=datetime(2023, 6, 15),
            total_value=Decimal("10000"),
            cash_balance=Decimal("10000"),
            positions=[]
        )

        assert len(snapshot.positions) == 0
        assert snapshot.total_value == Decimal("10000")

    def test_portfolio_snapshot_negative_cash(self):
        """Test portfolio with negative cash (margin scenario)"""
        snapshot = PortfolioSnapshot(
            timestamp=datetime(2023, 6, 15),
            total_value=Decimal("100000"),
            cash_balance=Decimal("-5000")  # Margin debt
        )

        assert snapshot.cash_balance == Decimal("-5000")

    def test_portfolio_snapshot_zero_value(self):
        """Test portfolio snapshot with zero value"""
        snapshot = PortfolioSnapshot(
            timestamp=datetime(2023, 6, 15),
            total_value=Decimal("0"),
            cash_balance=Decimal("0")
        )

        assert snapshot.total_value == Decimal("0")

    def test_portfolio_snapshot_large_returns(self):
        """Test portfolio with large positive and negative returns"""
        snapshot_positive = PortfolioSnapshot(
            timestamp=datetime(2023, 6, 15),
            total_value=Decimal("100000"),
            cash_balance=Decimal("50000"),
            daily_return=2.5,
            cumulative_return=15.0
        )

        snapshot_negative = PortfolioSnapshot(
            timestamp=datetime(2023, 6, 15),
            total_value=Decimal("50000"),
            cash_balance=Decimal("10000"),
            daily_return=-0.50,
            cumulative_return=-0.75
        )

        assert snapshot_positive.daily_return == 2.5
        assert snapshot_negative.cumulative_return == -0.75


@pytest.mark.unit
@pytest.mark.models
class TestBacktestMetrics:
    """Tests for BacktestMetrics model"""

    def test_backtest_metrics_valid(self):
        """Test creating valid backtest metrics"""
        metrics = BacktestMetrics(
            total_return=0.45,
            annualized_return=0.15,
            volatility=0.12,
            sharpe_ratio=1.25,
            sortino_ratio=1.80,
            max_drawdown=-0.18,
            max_drawdown_duration_days=45,
            calmar_ratio=0.83,
            win_rate=0.55,
            best_day=0.05,
            worst_day=-0.04,
            avg_winning_day=0.015,
            avg_losing_day=-0.010,
            profit_factor=1.5,
            total_trading_days=252
        )

        assert metrics.total_return == 0.45
        assert metrics.sharpe_ratio == 1.25
        assert metrics.total_trading_days == 252

    def test_backtest_metrics_zero_volatility(self):
        """Test metrics with zero volatility (flat return)"""
        metrics = BacktestMetrics(
            total_return=0.0,
            annualized_return=0.0,
            volatility=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            max_drawdown_duration_days=0,
            win_rate=0.5,
            best_day=0.0,
            worst_day=0.0,
            avg_winning_day=0.0,
            avg_losing_day=0.0,
            total_trading_days=252
        )

        assert metrics.volatility == 0.0

    def test_backtest_metrics_negative_returns(self):
        """Test metrics with negative returns"""
        metrics = BacktestMetrics(
            total_return=-0.25,
            annualized_return=-0.10,
            volatility=0.15,
            sharpe_ratio=-0.67,
            sortino_ratio=-1.0,
            max_drawdown=-0.50,
            max_drawdown_duration_days=120,
            win_rate=0.40,
            best_day=0.02,
            worst_day=-0.08,
            avg_winning_day=0.01,
            avg_losing_day=-0.02,
            total_trading_days=252
        )

        assert metrics.total_return == -0.25
        assert metrics.max_drawdown == -0.50

    def test_backtest_metrics_extreme_sharpe(self):
        """Test extreme Sharpe ratio values"""
        # Very high Sharpe ratio
        metrics_high = BacktestMetrics(
            total_return=1.0,
            annualized_return=0.5,
            volatility=0.01,
            sharpe_ratio=50.0,
            sortino_ratio=75.0,
            max_drawdown=-0.01,
            max_drawdown_duration_days=1,
            win_rate=0.95,
            best_day=0.10,
            worst_day=-0.01,
            avg_winning_day=0.05,
            avg_losing_day=-0.005,
            total_trading_days=252
        )

        assert metrics_high.sharpe_ratio == 50.0

    def test_backtest_metrics_trade_statistics(self):
        """Test metrics with detailed trade statistics"""
        metrics = BacktestMetrics(
            total_return=0.20,
            annualized_return=0.08,
            volatility=0.10,
            sharpe_ratio=0.8,
            sortino_ratio=1.2,
            max_drawdown=-0.15,
            max_drawdown_duration_days=60,
            win_rate=0.58,
            best_day=0.08,
            worst_day=-0.06,
            avg_winning_day=0.012,
            avg_losing_day=-0.010,
            profit_factor=1.8,
            total_trading_days=252
        )

        assert metrics.profit_factor == 1.8
        assert metrics.win_rate == 0.58


@pytest.mark.unit
@pytest.mark.models
class TestBacktestResult:
    """Tests for BacktestResult model"""

    def test_backtest_result_valid(self):
        """Test creating valid backtest result"""
        result = BacktestResult(
            config=BacktestConfig(
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31),
                initial_capital=Decimal("100000")
            ),
            metrics=BacktestMetrics(
                total_return=0.20,
                annualized_return=0.08,
                volatility=0.10,
                sharpe_ratio=0.8,
                sortino_ratio=1.2,
                max_drawdown=-0.15,
                max_drawdown_duration_days=60,
                win_rate=0.55,
                best_day=0.08,
                worst_day=-0.06,
                avg_winning_day=0.012,
                avg_losing_day=-0.010,
                total_trading_days=252
            ),
            snapshots=[],
            violations=[],
            start_value=Decimal("100000"),
            end_value=Decimal("120000"),
            peak_value=Decimal("125000"),
            valley_value=Decimal("95000"),
            duration_seconds=10.5
        )

        assert result.start_value == Decimal("100000")
        assert result.end_value == Decimal("120000")

    def test_backtest_result_with_violations(self):
        """Test backtest result with risk violations"""
        result = BacktestResult(
            config=BacktestConfig(
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2023, 12, 31)
            ),
            metrics=BacktestMetrics(
                total_return=-0.10,
                annualized_return=-0.04,
                volatility=0.20,
                sharpe_ratio=-0.2,
                sortino_ratio=-0.3,
                max_drawdown=-0.35,
                max_drawdown_duration_days=120,
                win_rate=0.45,
                best_day=0.05,
                worst_day=-0.08,
                avg_winning_day=0.010,
                avg_losing_day=-0.012,
                total_trading_days=252
            ),
            snapshots=[],
            violations=[
                RiskViolation(
                    timestamp=datetime(2023, 6, 15),
                    violation_type="drawdown",
                    limit_value=0.20,
                    actual_value=0.35,
                    severity="critical"
                )
            ],
            start_value=Decimal("100000"),
            end_value=Decimal("90000"),
            peak_value=Decimal("105000"),
            valley_value=Decimal("65000"),
            duration_seconds=15.2
        )

        assert len(result.violations) == 1
        assert result.violations[0].severity == "critical"


@pytest.mark.unit
@pytest.mark.models
class TestRiskViolation:
    """Tests for RiskViolation model"""

    def test_risk_violation_valid(self):
        """Test creating valid risk violation"""
        violation = RiskViolation(
            timestamp=datetime(2023, 6, 15, 10, 30, 0),
            violation_type="leverage",
            limit_value=2.0,
            actual_value=3.5,
            severity="critical"
        )

        assert violation.violation_type == "leverage"
        assert violation.actual_value == 3.5
        assert violation.severity == "critical"

    def test_risk_violation_severity_levels(self):
        """Test different severity levels"""
        severities = ["warning", "critical"]

        for severity in severities:
            violation = RiskViolation(
                timestamp=datetime(2023, 6, 15),
                violation_type="test",
                limit_value=1.0,
                actual_value=2.0,
                severity=severity
            )
            assert violation.severity == severity

    def test_risk_violation_circuit_breaker_flag(self):
        """Test violation with circuit breaker flag"""
        violation = RiskViolation(
            timestamp=datetime(2023, 6, 15),
            violation_type="loss",
            limit_value=-0.05,
            actual_value=-0.10,
            would_halt_trading=True
        )

        assert violation.would_halt_trading is True


@pytest.mark.unit
@pytest.mark.models
class TestStrategyComparison:
    """Tests for StrategyComparison model"""

    def test_strategy_comparison_valid(self):
        """Test creating valid strategy comparison"""
        comparison = StrategyComparison(
            strategies=[
                {"name": "Conservative", "max_loss": 0.02},
                {"name": "Aggressive", "max_loss": 0.05}
            ],
            results=[
                BacktestResult(
                    config=BacktestConfig(
                        start_date=datetime(2023, 1, 1),
                        end_date=datetime(2023, 12, 31)
                    ),
                    metrics=BacktestMetrics(
                        total_return=0.08,
                        annualized_return=0.08,
                        volatility=0.08,
                        sharpe_ratio=1.0,
                        sortino_ratio=1.5,
                        max_drawdown=-0.10,
                        max_drawdown_duration_days=30,
                        win_rate=0.55,
                        best_day=0.03,
                        worst_day=-0.02,
                        avg_winning_day=0.010,
                        avg_losing_day=-0.008,
                        total_trading_days=252
                    ),
                    snapshots=[],
                    violations=[],
                    start_value=Decimal("100000"),
                    end_value=Decimal("108000"),
                    peak_value=Decimal("110000"),
                    valley_value=Decimal("98000"),
                    duration_seconds=10.0
                )
            ],
            best_sharpe="strategy_a",
            best_return="strategy_b",
            lowest_drawdown="strategy_a",
            most_stable="strategy_a",
            recommendation="Conservative approach recommended"
        )

        assert comparison.best_sharpe == "strategy_a"
        assert len(comparison.strategies) == 2


@pytest.mark.unit
@pytest.mark.models
class TestWalkForwardResult:
    """Tests for WalkForwardResult model"""

    def test_walk_forward_result_valid(self):
        """Test creating valid walk-forward analysis result"""
        result = WalkForwardResult(
            in_sample_periods=[
                {
                    "period": 1,
                    "start": datetime(2022, 1, 1),
                    "end": datetime(2022, 12, 31),
                    "sharpe": 1.2
                }
            ],
            out_of_sample_periods=[
                {
                    "period": 1,
                    "start": datetime(2023, 1, 1),
                    "end": datetime(2023, 3, 31),
                    "sharpe": 0.8
                }
            ],
            optimal_parameters={"max_loss": 0.02, "max_drawdown": 0.15},
            parameter_stability=0.85,
            in_sample_sharpe=1.2,
            out_of_sample_sharpe=0.8,
            overfitting_score=1.3,
            recommended_for_live=True,
            confidence_score=0.75,
            notes="Stable parameters across periods"
        )

        assert result.in_sample_sharpe == 1.2
        assert result.out_of_sample_sharpe == 0.8
        assert result.recommended_for_live is True

    def test_walk_forward_result_overfitting_detected(self):
        """Test walk-forward result showing overfitting"""
        result = WalkForwardResult(
            in_sample_periods=[{"sharpe": 2.5}],
            out_of_sample_periods=[{"sharpe": 0.5}],
            optimal_parameters={"param": 1.0},
            parameter_stability=0.4,
            in_sample_sharpe=2.5,
            out_of_sample_sharpe=0.5,
            overfitting_score=2.8,  # High overfitting
            recommended_for_live=False,
            confidence_score=0.2,
            notes="High overfitting detected"
        )

        # Out-of-sample performance much worse than in-sample
        assert result.out_of_sample_sharpe < result.in_sample_sharpe
        assert result.overfitting_score > 2.0
        assert result.recommended_for_live is False


@pytest.mark.unit
@pytest.mark.models
class TestModelSerialization:
    """Tests for model serialization and deserialization"""

    def test_config_json_serialization(self):
        """Test BacktestConfig can be serialized to JSON"""
        config = BacktestConfig(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            initial_capital=Decimal("100000")
        )

        json_str = config.model_dump_json()
        assert "2023-01-01" in json_str
        assert "100000" in json_str

    def test_metrics_json_serialization(self):
        """Test BacktestMetrics can be serialized to JSON"""
        metrics = BacktestMetrics(
            total_return=0.20,
            annualized_return=0.08,
            volatility=0.10,
            sharpe_ratio=0.8,
            sortino_ratio=1.2,
            max_drawdown=-0.15,
            max_drawdown_duration_days=60,
            win_rate=0.58,
            best_day=0.08,
            worst_day=-0.06,
            avg_winning_day=0.012,
            avg_losing_day=-0.010,
            total_trading_days=252
        )

        json_str = metrics.model_dump_json()
        assert "0.2" in json_str or "0.20" in json_str
        assert "0.8" in json_str


@pytest.mark.unit
@pytest.mark.models
class TestModelValidation:
    """Tests for model validation constraints"""

    def test_snapshot_required_fields(self):
        """Test that required fields are enforced"""
        with pytest.raises(ValidationError):
            PortfolioSnapshot(
                timestamp=datetime(2023, 1, 1)
                # Missing required fields: total_value, cash_balance
            )

    def test_metrics_all_required_fields(self):
        """Test that all required metric fields are enforced"""
        with pytest.raises(ValidationError):
            BacktestMetrics(
                total_return=0.20
                # Missing many required fields
            )

    def test_result_required_fields(self):
        """Test that result required fields are enforced"""
        with pytest.raises(ValidationError):
            BacktestResult(
                config=BacktestConfig(
                    start_date=datetime(2023, 1, 1),
                    end_date=datetime(2023, 12, 31)
                )
                # Missing required fields: metrics, snapshots, etc
            )
