"""
Unit tests for RiskEngine - Risk calculation and metrics engine
Tests all risk calculation methods, metrics generation, and circuit breaker logic
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from app.risk_engine import RiskEngine
from app.config import settings
from app.models import RiskLevel


@pytest.mark.unit
@pytest.mark.risk
class TestRiskEngineCapitalMetrics:
    """Tests for capital allocation and utilization metrics"""

    def test_calculate_capital_metrics_with_positions(self, risk_engine):
        """Test capital metrics calculation with active positions"""
        total_capital = Decimal("10000")
        positions = [
            {"current_value": 2500.0},  # 25% of capital
            {"current_value": 1500.0}   # 15% of capital
        ]

        metrics = risk_engine.calculate_capital_metrics(total_capital, positions)

        assert metrics.total_capital == total_capital
        assert metrics.allocated_capital == Decimal("4000")  # 2500 + 1500
        assert metrics.available_capital == Decimal("5500")  # 10000 - 4000 - 500 (reserved)
        assert metrics.capital_utilization == 0.40  # 40% utilization
        assert metrics.max_position_size == Decimal("200")  # 2% of 10000
        assert metrics.recommended_position_size == Decimal("100")  # 1% of 10000

    def test_calculate_capital_metrics_no_positions(self, risk_engine):
        """Test capital metrics with empty portfolio"""
        total_capital = Decimal("10000")
        positions = []

        metrics = risk_engine.calculate_capital_metrics(total_capital, positions)

        assert metrics.total_capital == total_capital
        assert metrics.allocated_capital == Decimal("0")
        assert metrics.available_capital == total_capital - Decimal("500")  # Minus reserved capital
        assert metrics.capital_utilization == 0.0
        assert metrics.max_position_size == Decimal("200")

    def test_calculate_capital_metrics_fully_invested(self, risk_engine):
        """Test capital metrics when portfolio is fully invested"""
        total_capital = Decimal("10000")
        positions = [
            {"current_value": 10000.0}  # 100% invested
        ]

        metrics = risk_engine.calculate_capital_metrics(total_capital, positions)

        assert metrics.allocated_capital == total_capital
        assert metrics.available_capital == Decimal("-500")  # Total - Allocated - Reserved
        assert metrics.capital_utilization == 1.0  # 100% utilization


@pytest.mark.unit
@pytest.mark.risk
class TestRiskEngineExposureMetrics:
    """Tests for portfolio exposure and concentration metrics"""

    def test_calculate_exposure_metrics_diversified(self, risk_engine):
        """Test exposure metrics with diversified portfolio"""
        total_capital = Decimal("10000")
        positions = [
            {"symbol": "BTCUSDT", "quantity": 0.1, "current_price": 45000.0, "current_value": 4500.0},
            {"symbol": "ETHUSDT", "quantity": 2.0, "current_price": 3000.0, "current_value": 6000.0}
        ]

        metrics = risk_engine.calculate_exposure_metrics(positions, total_capital)

        assert metrics.total_exposure == Decimal("10500")  # 4500 + 6000
        assert metrics.exposure_ratio == 1.05  # 10500 / 10000
        assert metrics.long_exposure == Decimal("10500")
        assert metrics.short_exposure == Decimal("0")
        assert metrics.net_exposure == Decimal("10500")
        assert metrics.gross_exposure == Decimal("10500")
        assert len(metrics.concentrated_positions) == 2  # Both positions > 2% (max_position_size)

    def test_calculate_exposure_metrics_concentrated(self, risk_engine):
        """Test exposure metrics with concentrated position (>2%)"""
        total_capital = Decimal("10000")
        positions = [
            {"symbol": "BTCUSDT", "quantity": 0.2, "current_price": 45000.0, "current_value": 9000.0}
        ]

        metrics = risk_engine.calculate_exposure_metrics(positions, total_capital)

        assert metrics.exposure_ratio == 0.9  # 9000 / 10000
        assert len(metrics.concentrated_positions) == 1
        assert metrics.concentrated_positions[0]['symbol'] == "BTCUSDT"

    def test_calculate_exposure_metrics_empty_portfolio(self, risk_engine):
        """Test exposure metrics with no positions"""
        total_capital = Decimal("10000")
        positions = []

        metrics = risk_engine.calculate_exposure_metrics(positions, total_capital)

        assert metrics.total_exposure == Decimal("0")
        assert metrics.exposure_ratio == 0.0
        assert len(metrics.concentrated_positions) == 0


@pytest.mark.unit
@pytest.mark.risk
class TestRiskEngineDrawdownMetrics:
    """Tests for drawdown calculation and tracking"""

    def test_calculate_drawdown_metrics_with_drawdown(self, risk_engine, sample_historical_values):
        """Test drawdown calculation with historical data showing drawdown"""
        current_value = Decimal("11000")

        metrics = risk_engine.calculate_drawdown_metrics(current_value, sample_historical_values)

        # Verify basic metrics
        assert metrics.current_drawdown >= 0
        assert metrics.max_drawdown >= 0
        assert metrics.max_drawdown >= metrics.current_drawdown
        assert metrics.max_drawdown_date is not None
        assert metrics.underwater_periods >= 0

    def test_calculate_drawdown_metrics_at_all_time_high(self, risk_engine):
        """Test drawdown when portfolio is at all-time high"""
        current_value = Decimal("12000")
        historical_values = [
            (datetime.now() - timedelta(days=i), Decimal(str(10000 * (1 + i * 0.01))))
            for i in range(10)
        ]

        metrics = risk_engine.calculate_drawdown_metrics(current_value, historical_values)

        assert metrics.current_drawdown == 0.0  # At ATH, no drawdown
        assert metrics.recovery_factor is not None or metrics.max_drawdown == 0

    def test_calculate_drawdown_metrics_single_value(self, risk_engine):
        """Test drawdown with only current value (no history)"""
        current_value = Decimal("10000")
        historical_values = [(datetime.now(), current_value)]

        metrics = risk_engine.calculate_drawdown_metrics(current_value, historical_values)

        assert metrics.current_drawdown == 0.0
        assert metrics.max_drawdown == 0.0

    def test_calculate_drawdown_metrics_zero_historical_value(self, risk_engine):
        """Test drawdown calculation handles zero historical values safely"""
        current_value = Decimal("10000")
        historical_values = [
            (datetime.now(), Decimal("0")),  # Zero value should be handled
            (datetime.now() - timedelta(days=1), Decimal("10000"))
        ]

        metrics = risk_engine.calculate_drawdown_metrics(current_value, historical_values)

        # Should not crash and should handle zero gracefully
        assert metrics.recovery_factor is None or isinstance(metrics.recovery_factor, float)


@pytest.mark.unit
@pytest.mark.risk
@pytest.mark.performance
class TestRiskEnginePerformanceMetrics:
    """Tests for performance metrics calculation"""

    def test_calculate_performance_metrics_with_returns(self, risk_engine, sample_returns, sample_trades):
        """Test performance metrics calculation with historical data"""
        max_drawdown = 0.08

        metrics = risk_engine.calculate_performance_metrics(sample_returns, max_drawdown, sample_trades)

        # Verify all metrics are calculated
        assert metrics.total_return is not None
        assert metrics.annualized_return is not None
        assert metrics.volatility >= 0
        assert metrics.sharpe_ratio is not None
        assert metrics.sortino_ratio is not None
        assert metrics.max_drawdown == max_drawdown
        assert metrics.win_rate >= 0 and metrics.win_rate <= 1
        assert metrics.profit_factor is None or metrics.profit_factor >= 0 or metrics.profit_factor == float('inf')
        assert metrics.total_trades == len(sample_trades)

    def test_calculate_performance_metrics_all_winning_trades(self, risk_engine):
        """Test performance metrics with only profitable trades"""
        returns = [0.02, 0.03, 0.01, 0.025]  # All positive returns
        max_drawdown = 0.0
        trades = [
            {"pnl": 100, "return_pct": 2.0},
            {"pnl": 150, "return_pct": 3.0},
            {"pnl": 50, "return_pct": 1.0}
        ]

        metrics = risk_engine.calculate_performance_metrics(returns, max_drawdown, trades)

        assert metrics.win_rate == 1.0  # 100% win rate
        assert metrics.profit_factor == float('inf')  # Infinite when no losses
        assert metrics.average_loss is None  # No losses

    def test_calculate_performance_metrics_no_returns(self, risk_engine):
        """Test performance metrics with empty returns list"""
        returns = []
        max_drawdown = 0.0
        trades = []

        metrics = risk_engine.calculate_performance_metrics(returns, max_drawdown, trades)

        assert metrics.total_return == 0.0
        assert metrics.volatility == 0.0
        assert metrics.sharpe_ratio == 0.0
        assert metrics.total_trades == 0

    def test_calculate_performance_metrics_sharpe_calculation(self, risk_engine):
        """Test Sharpe ratio calculation is correct"""
        # Returns with known characteristics
        returns = [0.01] * 252  # 1% daily return for a year
        max_drawdown = 0.05

        metrics = risk_engine.calculate_performance_metrics(returns, max_drawdown, [])

        # With consistent 1% returns, Sharpe should be very high
        assert metrics.sharpe_ratio is not None and metrics.sharpe_ratio > 3.0
        assert metrics.annualized_return > 0.50  # Should be high with consistent returns


@pytest.mark.unit
@pytest.mark.risk
class TestRiskEngineVaRCalculation:
    """Tests for Value at Risk (VaR) calculation"""

    def test_calculate_var_with_returns(self, risk_engine):
        """Test VaR calculation with sufficient historical returns"""
        portfolio_value = Decimal("10000")
        returns = [0.02, -0.01, 0.015, -0.03, 0.025, -0.02, 0.01, -0.015] * 10  # 80 returns

        var_metrics = risk_engine.calculate_var(portfolio_value, returns)

        assert var_metrics.var_95 > 0
        assert var_metrics.var_99 > var_metrics.var_95  # 99% VaR should be higher
        assert var_metrics.cvar_95 >= var_metrics.var_95  # CVaR >= VaR
        assert var_metrics.cvar_99 >= var_metrics.var_99
        assert var_metrics.confidence_level == 0.95
        assert var_metrics.time_horizon_days == 1

    def test_calculate_var_historical_method(self, risk_engine):
        """Test VaR using historical method with sufficient data"""
        portfolio_value = Decimal("10000")
        # Create 100 returns with known distribution
        returns = [0.01] * 50 + [-0.02] * 30 + [0.005] * 20

        var_metrics = risk_engine.calculate_var(portfolio_value, returns)

        assert var_metrics.calculation_method == "historical"  # Use calculation_method instead of method
        assert var_metrics.var_95 > 0
        assert var_metrics.var_99 > 0

    def test_calculate_var_insufficient_data(self, risk_engine):
        """Test VaR with insufficient data returns conservative estimates"""
        portfolio_value = Decimal("10000")
        returns = [0.01, -0.02, 0.015]  # Only 3 returns

        var_metrics = risk_engine.calculate_var(portfolio_value, returns)

        assert var_metrics.calculation_method == "insufficient_data"
        # Conservative estimates
        assert var_metrics.var_95 == portfolio_value * Decimal("0.05")
        assert var_metrics.var_99 == portfolio_value * Decimal("0.10")

    def test_calculate_var_custom_confidence(self, risk_engine):
        """Test VaR with custom confidence level"""
        portfolio_value = Decimal("10000")
        returns = [0.01, -0.02] * 50  # 100 returns

        var_metrics = risk_engine.calculate_var(
            portfolio_value, returns, confidence_level=0.99
        )

        assert var_metrics.confidence_level == 0.99
        assert var_metrics.var_99 > 0

    def test_calculate_var_multiday_horizon(self, risk_engine):
        """Test VaR with multi-day time horizon"""
        portfolio_value = Decimal("10000")
        returns = [0.01, -0.02, 0.015, -0.01] * 25  # 100 returns

        var_1day = risk_engine.calculate_var(portfolio_value, returns, time_horizon_days=1)
        var_5day = risk_engine.calculate_var(portfolio_value, returns, time_horizon_days=5)

        # 5-day VaR should be higher than 1-day VaR (square root of time rule)
        assert var_5day.var_95 > var_1day.var_95
        assert var_5day.time_horizon_days == 5


@pytest.mark.unit
@pytest.mark.risk
class TestRiskEngineRiskScore:
    """Tests for risk score calculation"""

    def test_calculate_risk_score_comprehensive(
        self, risk_engine, capital_metrics_sample, exposure_metrics_sample,
        drawdown_metrics_sample, performance_metrics_sample, var_metrics_sample
    ):
        """Test comprehensive risk score calculation with all metrics"""
        score, level = risk_engine.calculate_risk_score(
            capital_metrics_sample, exposure_metrics_sample, drawdown_metrics_sample,
            performance_metrics_sample, var_metrics_sample
        )

        assert 0 <= score <= 100
        assert level in [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]

    def test_calculate_risk_score_low_risk(self, risk_engine):
        """Test risk score for low-risk portfolio"""
        from app.models import CapitalMetrics, ExposureMetrics, DrawdownMetrics, PerformanceMetrics, ValueAtRisk

        # Low risk scenario
        capital = CapitalMetrics(
            total_capital=Decimal("10000"),
            available_capital=Decimal("8000"),
            allocated_capital=Decimal("2000"),
            capital_utilization=0.20,
            max_position_size=Decimal("200"),
            recommended_position_size=Decimal("100")
        )
        exposure = ExposureMetrics(
            total_exposure=Decimal("2000"),
            long_exposure=Decimal("2000"),
            short_exposure=Decimal("0"),
            net_exposure=Decimal("2000"),
            gross_exposure=Decimal("2000"),
            exposure_ratio=0.20,
            leverage=0.20,
            concentrated_positions=[]
        )
        drawdown = DrawdownMetrics(current_drawdown=0.02, max_drawdown=0.05)
        performance = PerformanceMetrics(
            total_return=0.10, annualized_return=0.15, volatility=0.10,
            sharpe_ratio=1.5, max_drawdown=0.05
        )
        var = ValueAtRisk(
            var_95=Decimal("500"), var_99=Decimal("700"),
            cvar_95=Decimal("600"), cvar_99=Decimal("800"),
            confidence_level=0.95, time_horizon_days=1,
            calculation_method="historical"
        )

        score, level = risk_engine.calculate_risk_score(capital, exposure, drawdown, performance, var)

        assert score < 30
        assert level == RiskLevel.LOW

    def test_calculate_risk_score_boundaries(self, risk_engine):
        """Test risk score boundaries for different risk levels"""
        from app.models import CapitalMetrics, ExposureMetrics, DrawdownMetrics, PerformanceMetrics, ValueAtRisk

        # Create high risk scenario
        exp_low = ExposureMetrics(
            total_exposure=Decimal("1000"),
            long_exposure=Decimal("1000"),
            short_exposure=Decimal("0"),
            net_exposure=Decimal("1000"),
            gross_exposure=Decimal("1000"),
            exposure_ratio=0.10,
            leverage=0.10,  # Add the required leverage field
            concentrated_positions=[]
        )

        # Medium risk scenario
        capital_med = CapitalMetrics(
            total_capital=Decimal("10000"),
            available_capital=Decimal("5000"),
            allocated_capital=Decimal("5000"),
            capital_utilization=0.50,
            max_position_size=Decimal("200"),
            recommended_position_size=Decimal("100")
        )
        exp_med = ExposureMetrics(
            total_exposure=Decimal("5000"),
            long_exposure=Decimal("5000"),
            short_exposure=Decimal("0"),
            net_exposure=Decimal("5000"),
            gross_exposure=Decimal("5000"),
            exposure_ratio=0.50,
            leverage=0.50,  # Add the required leverage field
            concentrated_positions=[]
        )
        drawdown = DrawdownMetrics(current_drawdown=0.05, max_drawdown=0.10)
        performance = PerformanceMetrics(
            total_return=0.10, annualized_return=0.15, volatility=0.15,
            sharpe_ratio=1.0, max_drawdown=0.10
        )
        var = ValueAtRisk(
            var_95=Decimal("1000"), var_99=Decimal("1500"),
            cvar_95=Decimal("1200"), cvar_99=Decimal("1700"),
            confidence_level=0.95, time_horizon_days=1,
            calculation_method="historical"
        )

        score, level = risk_engine.calculate_risk_score(capital_med, exp_med, drawdown, performance, var)

        assert 30 <= score < 60
        assert level == RiskLevel.MEDIUM


@pytest.mark.unit
@pytest.mark.risk
class TestRiskEngineAlerts:
    """Tests for risk alert generation"""

    def test_generate_risk_alerts_no_violations(
        self, risk_engine, capital_metrics_sample, exposure_metrics_sample,
        drawdown_metrics_sample, performance_metrics_sample
    ):
        """Test no alerts generated when all metrics are within limits"""
        alerts = risk_engine.generate_risk_alerts(
            capital_metrics_sample, exposure_metrics_sample, drawdown_metrics_sample, performance_metrics_sample
        )

        # Default fixtures should not trigger alerts
        assert len(alerts) == 0

    def test_generate_risk_alerts_high_utilization(self, risk_engine):
        """Test alert generation for high capital utilization"""
        from app.models import CapitalMetrics, ExposureMetrics, DrawdownMetrics, PerformanceMetrics

        capital_metrics = CapitalMetrics(
            total_capital=Decimal("10000"),
            available_capital=Decimal("500"),
            allocated_capital=Decimal("9500"),
            capital_utilization=0.95,  # 95% > 90% threshold
            max_position_size=Decimal("200"),
            recommended_position_size=Decimal("100")
        )
        exposure_metrics = ExposureMetrics(
            total_exposure=Decimal("9500"),
            long_exposure=Decimal("9500"),
            short_exposure=Decimal("0"),
            net_exposure=Decimal("9500"),
            gross_exposure=Decimal("9500"),
            exposure_ratio=0.95,
            leverage=0.95,  # Add the required leverage field
            concentrated_positions=[]
        )
        drawdown_metrics = DrawdownMetrics(current_drawdown=0.02, max_drawdown=0.05)
        performance_metrics = PerformanceMetrics(
            total_return=0.10, annualized_return=0.15, volatility=0.10,
            sharpe_ratio=1.5, max_drawdown=0.05
        )

        alerts = risk_engine.generate_risk_alerts(
            capital_metrics, exposure_metrics, drawdown_metrics, performance_metrics
        )

        assert len(alerts) > 0
        capital_alerts = [a for a in alerts if a.category == "Capital"]
        assert len(capital_alerts) == 1
        assert capital_alerts[0].metric_value == 0.95

    def test_generate_risk_alerts_multiple_violations(self, risk_engine):
        """Test multiple alert generation for various violations"""
        from app.models import CapitalMetrics, ExposureMetrics, DrawdownMetrics, PerformanceMetrics

        capital_metrics = CapitalMetrics(
            total_capital=Decimal("10000"),
            available_capital=Decimal("0"),
            allocated_capital=Decimal("10000"),
            capital_utilization=1.0,
            max_position_size=Decimal("200"),
            recommended_position_size=Decimal("100")
        )
        exposure_metrics = ExposureMetrics(
            total_exposure=Decimal("2500"),
            long_exposure=Decimal("2500"),
            short_exposure=Decimal("0"),
            net_exposure=Decimal("2500"),
            gross_exposure=Decimal("2500"),
            exposure_ratio=0.25,  # Exceeds 20% max
            leverage=0.25,
            concentrated_positions=[]
        )
        drawdown_metrics = DrawdownMetrics(current_drawdown=0.15, max_drawdown=0.15)  # Exceeds 10%
        performance_metrics = PerformanceMetrics(
            total_return=-0.05, annualized_return=-0.10, volatility=0.30,
            sharpe_ratio=0.5,  # Below 1.0
            max_drawdown=0.15
        )

        alerts = risk_engine.generate_risk_alerts(
            capital_metrics, exposure_metrics, drawdown_metrics, performance_metrics
        )

        assert len(alerts) >= 3  # Capital, exposure, and performance alerts

    def test_generate_risk_alerts_concentration(self, risk_engine):
        """Test alert generation for concentrated positions"""
        from app.models import CapitalMetrics, ExposureMetrics, DrawdownMetrics, PerformanceMetrics

        capital_metrics = CapitalMetrics(
            total_capital=Decimal("10000"),
            available_capital=Decimal("5000"),
            allocated_capital=Decimal("5000"),
            capital_utilization=0.50,
            max_position_size=Decimal("200"),
            recommended_position_size=Decimal("100")
        )
        exposure_metrics = ExposureMetrics(
            total_exposure=Decimal("5000"),
            long_exposure=Decimal("5000"),
            short_exposure=Decimal("0"),
            net_exposure=Decimal("5000"),
            gross_exposure=Decimal("5000"),
            exposure_ratio=0.50,
            leverage=0.50,  # Add the required leverage field
            concentrated_positions=[
                {'symbol': 'BTCUSDT', 'value': 3000.0, 'percentage': 30.0, 'excess': 28.0},
                {'symbol': 'ETHUSDT', 'value': 2000.0, 'percentage': 20.0, 'excess': 18.0}
            ]
        )
        drawdown_metrics = DrawdownMetrics(current_drawdown=0.05, max_drawdown=0.10)
        performance_metrics = PerformanceMetrics(
            total_return=0.10, annualized_return=0.15, volatility=0.15,
            sharpe_ratio=1.0, max_drawdown=0.10
        )

        alerts = risk_engine.generate_risk_alerts(
            capital_metrics, exposure_metrics, drawdown_metrics, performance_metrics
        )

        concentration_alerts = [a for a in alerts if a.category == "Concentration"]
        assert len(concentration_alerts) == 2


@pytest.mark.unit
@pytest.mark.risk
@pytest.mark.circuit_breaker
class TestRiskEngineCircuitBreaker:
    """Tests for circuit breaker functionality"""

    def test_circuit_breaker_normal_conditions(self, risk_engine):
        """Test circuit breaker remains off under normal conditions"""
        daily_pnl = -0.02  # -2% loss (within -5% limit)
        drawdown = 0.05  # 5% drawdown (within 10% limit)
        exposure_ratio = 0.15  # 15% exposure (within 20% limit)

        status = risk_engine.check_circuit_breaker(daily_pnl, drawdown, exposure_ratio)

        assert status.circuit_breaker_active is False
        assert status.is_tripped is False
        assert status.can_trade is True

    def test_circuit_breaker_excessive_daily_loss(self, risk_engine):
        """Test circuit breaker trips on excessive daily loss"""
        daily_pnl = -0.06  # -6% loss (exceeds -5% limit)
        drawdown = 0.05
        exposure_ratio = 0.15

        status = risk_engine.check_circuit_breaker(daily_pnl, drawdown, exposure_ratio)

        assert status.circuit_breaker_active is True
        assert status.is_tripped is True
        assert status.can_trade is False
        assert "Daily loss" in status.reason

    def test_circuit_breaker_excessive_drawdown(self, risk_engine):
        """Test circuit breaker trips on excessive drawdown"""
        daily_pnl = -0.02
        drawdown = 0.12  # 12% drawdown (exceeds 10% limit)
        exposure_ratio = 0.15

        status = risk_engine.check_circuit_breaker(daily_pnl, drawdown, exposure_ratio)

        assert status.circuit_breaker_active is True
        assert status.is_tripped is True
        assert status.can_trade is False
        assert "Drawdown" in status.reason

    def test_circuit_breaker_excessive_exposure(self, risk_engine):
        """Test circuit breaker trips on excessive exposure"""
        daily_pnl = -0.02
        drawdown = 0.05
        exposure_ratio = 0.25  # 25% exposure (exceeds 20% * 1.2 = 24% critical limit)

        status = risk_engine.check_circuit_breaker(daily_pnl, drawdown, exposure_ratio)

        assert status.circuit_breaker_active is True
        assert status.is_tripped is True
        assert status.can_trade is False
        assert "Exposure" in status.reason

    def test_circuit_breaker_multiple_violations(self, risk_engine):
        """Test circuit breaker with multiple violations"""
        daily_pnl = -0.07  # Violates daily loss limit
        drawdown = 0.15  # Violates drawdown limit
        exposure_ratio = 0.30  # Violates exposure limit

        status = risk_engine.check_circuit_breaker(daily_pnl, drawdown, exposure_ratio)

        assert status.circuit_breaker_active is True
        assert status.is_tripped is True
        assert status.can_trade is False
        assert len(status.reasons) >= 3  # Should have multiple reasons

    def test_circuit_breaker_disabled(self, risk_engine):
        """Test circuit breaker when disabled in settings"""
        # Temporarily disable circuit breaker
        original_setting = settings.enable_circuit_breaker
        settings.enable_circuit_breaker = False

        daily_pnl = -0.10  # -10% loss (would normally trip)
        drawdown = 0.20  # 20% drawdown (would normally trip)
        exposure_ratio = 0.50  # 50% exposure (would normally trip)

        status = risk_engine.check_circuit_breaker(daily_pnl, drawdown, exposure_ratio)

        assert status.is_tripped is False
        assert status.can_trade is True
        assert len(status.reasons) == 0  # No violations detected when disabled

        # Restore original setting
        settings.enable_circuit_breaker = original_setting

    def test_circuit_breaker_cooldown(self, risk_engine):
        """Test circuit breaker cooldown period"""
        # First, trip the circuit breaker
        daily_pnl = -0.06  # Exceeds limit
        drawdown = 0.05
        exposure_ratio = 0.15

        status1 = risk_engine.check_circuit_breaker(daily_pnl, drawdown, exposure_ratio)
        assert status1.is_tripped is True

        # Check again immediately - should still be tripped due to cooldown
        daily_pnl = -0.01  # Now within limits
        status2 = risk_engine.check_circuit_breaker(daily_pnl, drawdown, exposure_ratio)

        assert status2.is_tripped is True  # Still tripped due to cooldown
        assert status2.can_trade is False
        assert "cooldown" in status2.reason.lower()
        assert status2.cooldown_ends_at is not None