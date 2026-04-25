"""
Diversification Calculator Tests
Purpose: Comprehensive tests for Phase 3.1 Diversification Metrics

Created: 2025-12-11
Target Coverage: >85%

Test Categories:
1. HHI calculation accuracy
2. Effective number of positions
3. Risk contribution analysis
4. Portfolio optimization
5. Concentration warnings
6. Integration tests
"""

import pytest
import numpy as np
from datetime import datetime, timezone
from typing import Dict, List

# Import modules to test
from app.risk.diversification_calculator import (
    DiversificationCalculator,
    DiversificationConfig,
    DiversificationMetrics,
    ConcentrationLevel,
    PositionData,
    RiskContribution,
    ConcentrationWarning,
    OptimalWeights,
    get_diversification_calculator,
    reset_diversification_calculator,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def diversification_config():
    """Create test diversification configuration"""
    return DiversificationConfig(
        hhi_excellent_threshold=0.10,
        hhi_good_threshold=0.18,
        hhi_moderate_threshold=0.25,
        hhi_poor_threshold=0.40,
        max_single_position_pct=30.0,
        warning_single_position_pct=20.0,
        max_risk_contribution_pct=40.0,
        warning_risk_contribution_pct=25.0,
        risk_parity_tolerance=0.01,
        max_iterations=1000,
    )


@pytest.fixture
def diversification_calculator(diversification_config):
    """Create fresh diversification calculator for each test"""
    reset_diversification_calculator()
    calculator = DiversificationCalculator(diversification_config)
    return calculator


@pytest.fixture
def equal_weight_positions():
    """Create equally weighted positions"""
    return [
        PositionData(symbol="BTCUSDT", weight=0.20, position_value=20000, volatility=0.60),
        PositionData(symbol="ETHUSDT", weight=0.20, position_value=20000, volatility=0.70),
        PositionData(symbol="SOLUSDT", weight=0.20, position_value=20000, volatility=0.80),
        PositionData(symbol="ARBUSDT", weight=0.20, position_value=20000, volatility=0.90),
        PositionData(symbol="UNIUSDT", weight=0.20, position_value=20000, volatility=0.85),
    ]


@pytest.fixture
def concentrated_positions():
    """Create concentrated positions"""
    return [
        PositionData(symbol="BTCUSDT", weight=0.70, position_value=70000, volatility=0.60),
        PositionData(symbol="ETHUSDT", weight=0.30, position_value=30000, volatility=0.70),
    ]


@pytest.fixture
def unequal_positions():
    """Create unequally weighted positions"""
    return [
        PositionData(symbol="BTCUSDT", weight=0.40, position_value=40000, volatility=0.60),
        PositionData(symbol="ETHUSDT", weight=0.30, position_value=30000, volatility=0.70),
        PositionData(symbol="SOLUSDT", weight=0.15, position_value=15000, volatility=0.80),
        PositionData(symbol="ARBUSDT", weight=0.10, position_value=10000, volatility=0.90),
        PositionData(symbol="UNIUSDT", weight=0.05, position_value=5000, volatility=0.85),
    ]


@pytest.fixture
def sample_covariance_matrix():
    """Create sample covariance matrix for 5 assets"""
    # Volatilities: 60%, 70%, 80%, 90%, 85%
    vols = np.array([0.60, 0.70, 0.80, 0.90, 0.85])
    n = len(vols)

    # Correlation matrix (symmetric, positive definite)
    corr = np.array([
        [1.00, 0.80, 0.60, 0.40, 0.50],
        [0.80, 1.00, 0.70, 0.50, 0.60],
        [0.60, 0.70, 1.00, 0.55, 0.65],
        [0.40, 0.50, 0.55, 1.00, 0.45],
        [0.50, 0.60, 0.65, 0.45, 1.00],
    ])

    # Covariance = vol_i * vol_j * corr_ij
    cov = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            cov[i, j] = vols[i] * vols[j] * corr[i, j]

    return cov


# =============================================================================
# HHI CALCULATION TESTS
# =============================================================================

class TestHHICalculation:
    """Test suite for Herfindahl-Hirschman Index calculation"""

    def test_hhi_equal_weights(self, diversification_calculator):
        """Test HHI for equally weighted portfolio"""
        # 5 equal weights of 20% each
        weights = [0.2, 0.2, 0.2, 0.2, 0.2]
        hhi = diversification_calculator.calculate_hhi(weights)

        # HHI = 5 * 0.2^2 = 5 * 0.04 = 0.20
        assert abs(hhi - 0.20) < 0.001

    def test_hhi_single_position(self, diversification_calculator):
        """Test HHI for single position (maximum concentration)"""
        weights = [1.0]
        hhi = diversification_calculator.calculate_hhi(weights)

        # HHI = 1.0^2 = 1.0
        assert hhi == 1.0

    def test_hhi_two_equal_positions(self, diversification_calculator):
        """Test HHI for two equal positions"""
        weights = [0.5, 0.5]
        hhi = diversification_calculator.calculate_hhi(weights)

        # HHI = 2 * 0.5^2 = 0.5
        assert abs(hhi - 0.5) < 0.001

    def test_hhi_unequal_weights(self, diversification_calculator):
        """Test HHI for unequal weights"""
        weights = [0.4, 0.3, 0.15, 0.1, 0.05]
        hhi = diversification_calculator.calculate_hhi(weights)

        # HHI = 0.4^2 + 0.3^2 + 0.15^2 + 0.1^2 + 0.05^2
        # = 0.16 + 0.09 + 0.0225 + 0.01 + 0.0025 = 0.285
        expected = 0.16 + 0.09 + 0.0225 + 0.01 + 0.0025
        assert abs(hhi - expected) < 0.001

    def test_hhi_empty_weights(self, diversification_calculator):
        """Test HHI for empty weights"""
        hhi = diversification_calculator.calculate_hhi([])
        assert hhi == 1.0  # Maximum concentration

    def test_hhi_normalizes_weights(self, diversification_calculator):
        """Test HHI normalizes weights that don't sum to 1"""
        # Weights that sum to 2.0 (should be normalized)
        weights = [0.4, 0.4, 0.4, 0.4, 0.4]
        hhi = diversification_calculator.calculate_hhi(weights)

        # After normalization, each weight is 0.2
        # HHI = 5 * 0.2^2 = 0.20
        assert abs(hhi - 0.20) < 0.001


# =============================================================================
# EFFECTIVE POSITIONS TESTS
# =============================================================================

class TestEffectivePositions:
    """Test suite for Effective Number of Bets calculation"""

    def test_enb_from_hhi(self, diversification_calculator):
        """Test ENB calculation from HHI"""
        # HHI = 0.20 -> ENB = 5
        enb = diversification_calculator.calculate_effective_positions(0.20)
        assert abs(enb - 5.0) < 0.01

    def test_enb_single_position(self, diversification_calculator):
        """Test ENB for single position"""
        enb = diversification_calculator.calculate_effective_positions(1.0)
        assert enb == 1.0

    def test_enb_perfect_diversification(self, diversification_calculator):
        """Test ENB approaches number of positions for equal weights"""
        # 10 equal positions: HHI = 0.10
        hhi = 0.10
        enb = diversification_calculator.calculate_effective_positions(hhi)
        assert enb == 10.0

    def test_enb_zero_hhi(self, diversification_calculator):
        """Test ENB for zero HHI (edge case)"""
        enb = diversification_calculator.calculate_effective_positions(0.0)
        assert enb == float('inf')


# =============================================================================
# CONCENTRATION LEVEL TESTS
# =============================================================================

class TestConcentrationLevel:
    """Test suite for concentration level classification"""

    def test_concentration_excellent(self, diversification_calculator):
        """Test excellent concentration level"""
        level = diversification_calculator.get_concentration_level(0.08, 15)
        assert level == ConcentrationLevel.EXCELLENT

    def test_concentration_good(self, diversification_calculator):
        """Test good concentration level"""
        level = diversification_calculator.get_concentration_level(0.15, 8)
        assert level == ConcentrationLevel.GOOD

    def test_concentration_moderate(self, diversification_calculator):
        """Test moderate concentration level"""
        level = diversification_calculator.get_concentration_level(0.22, 5)
        assert level == ConcentrationLevel.MODERATE

    def test_concentration_poor(self, diversification_calculator):
        """Test poor concentration level"""
        level = diversification_calculator.get_concentration_level(0.35, 3)
        assert level == ConcentrationLevel.POOR

    def test_concentration_concentrated(self, diversification_calculator):
        """Test concentrated level"""
        level = diversification_calculator.get_concentration_level(0.50, 2)
        assert level == ConcentrationLevel.CONCENTRATED

    def test_single_position_always_concentrated(self, diversification_calculator):
        """Test single position is always concentrated"""
        level = diversification_calculator.get_concentration_level(0.05, 1)
        assert level == ConcentrationLevel.CONCENTRATED


# =============================================================================
# RISK CONTRIBUTION TESTS
# =============================================================================

class TestRiskContribution:
    """Test suite for risk contribution analysis"""

    def test_portfolio_volatility(
        self,
        diversification_calculator,
        sample_covariance_matrix
    ):
        """Test portfolio volatility calculation"""
        weights = np.array([0.2, 0.2, 0.2, 0.2, 0.2])
        vol = diversification_calculator.calculate_portfolio_volatility(
            weights,
            sample_covariance_matrix
        )

        assert vol > 0
        assert vol < 1.0  # Should be less than 100% annually

    def test_marginal_risk_contributions(
        self,
        diversification_calculator,
        sample_covariance_matrix
    ):
        """Test marginal risk contribution calculation"""
        weights = np.array([0.2, 0.2, 0.2, 0.2, 0.2])
        marginal = diversification_calculator.calculate_marginal_risk_contributions(
            weights,
            sample_covariance_matrix
        )

        assert len(marginal) == 5
        assert all(isinstance(m, float) for m in marginal)

    def test_total_risk_contributions(
        self,
        diversification_calculator,
        sample_covariance_matrix
    ):
        """Test total risk contribution calculation"""
        weights = np.array([0.2, 0.2, 0.2, 0.2, 0.2])
        total = diversification_calculator.calculate_total_risk_contributions(
            weights,
            sample_covariance_matrix
        )

        assert len(total) == 5
        # Total risk contributions should sum to portfolio volatility
        portfolio_vol = diversification_calculator.calculate_portfolio_volatility(
            weights,
            sample_covariance_matrix
        )
        assert abs(sum(total) - portfolio_vol) < 0.001

    def test_risk_contributions_list(
        self,
        diversification_calculator,
        unequal_positions,
        sample_covariance_matrix
    ):
        """Test detailed risk contributions list"""
        contributions = diversification_calculator.calculate_risk_contributions(
            unequal_positions,
            sample_covariance_matrix
        )

        assert len(contributions) == 5
        assert all(isinstance(c, RiskContribution) for c in contributions)

        # Check percentages sum to 100%
        total_pct = sum(c.risk_contribution_pct for c in contributions)
        assert abs(total_pct - 100.0) < 1.0

    def test_risk_contributions_without_covariance(
        self,
        diversification_calculator,
        unequal_positions
    ):
        """Test risk contributions with estimated covariance"""
        contributions = diversification_calculator.calculate_risk_contributions(
            unequal_positions,
            covariance_matrix=None
        )

        assert len(contributions) == 5


# =============================================================================
# COMPLETE METRICS TESTS
# =============================================================================

class TestCompleteMetrics:
    """Test suite for complete diversification metrics"""

    def test_calculate_metrics_basic(
        self,
        diversification_calculator,
        equal_weight_positions
    ):
        """Test basic metrics calculation"""
        metrics = diversification_calculator.calculate_metrics(equal_weight_positions)

        assert isinstance(metrics, DiversificationMetrics)
        assert metrics.position_count == 5
        assert metrics.total_portfolio_value == 100000

    def test_metrics_hhi_correct(
        self,
        diversification_calculator,
        equal_weight_positions
    ):
        """Test metrics HHI is correct"""
        metrics = diversification_calculator.calculate_metrics(equal_weight_positions)

        # 5 equal weights -> HHI = 0.20
        assert abs(metrics.hhi - 0.20) < 0.001

    def test_metrics_effective_positions(
        self,
        diversification_calculator,
        equal_weight_positions
    ):
        """Test metrics effective positions"""
        metrics = diversification_calculator.calculate_metrics(equal_weight_positions)

        # HHI = 0.20 -> ENB = 5
        assert abs(metrics.effective_positions - 5.0) < 0.01

    def test_metrics_weight_statistics(
        self,
        diversification_calculator,
        unequal_positions
    ):
        """Test metrics weight statistics"""
        metrics = diversification_calculator.calculate_metrics(unequal_positions)

        assert metrics.max_weight == 0.40
        assert metrics.min_weight == 0.05
        assert abs(metrics.avg_weight - 0.20) < 0.001

    def test_metrics_concentration_level(
        self,
        diversification_calculator,
        concentrated_positions
    ):
        """Test metrics concentration level for concentrated portfolio"""
        metrics = diversification_calculator.calculate_metrics(concentrated_positions)

        # 70/30 split: HHI = 0.49 + 0.09 = 0.58
        assert metrics.concentration_level in [
            ConcentrationLevel.POOR,
            ConcentrationLevel.CONCENTRATED
        ]

    def test_metrics_empty_positions(self, diversification_calculator):
        """Test metrics with empty positions"""
        metrics = diversification_calculator.calculate_metrics([])

        assert metrics.position_count == 0
        assert metrics.hhi == 1.0
        assert metrics.concentration_level == ConcentrationLevel.CONCENTRATED

    def test_metrics_warnings_generated(
        self,
        diversification_calculator,
        concentrated_positions
    ):
        """Test warnings are generated for concentrated portfolio"""
        metrics = diversification_calculator.calculate_metrics(concentrated_positions)

        assert len(metrics.warnings) > 0
        # Should have warning about 70% position
        assert any(w.warning_type.startswith("SINGLE_POSITION") for w in metrics.warnings)

    def test_metrics_recommendations(
        self,
        diversification_calculator,
        concentrated_positions
    ):
        """Test recommendations are generated"""
        metrics = diversification_calculator.calculate_metrics(concentrated_positions)

        assert len(metrics.recommendations) > 0


# =============================================================================
# PORTFOLIO OPTIMIZATION TESTS
# =============================================================================

class TestPortfolioOptimization:
    """Test suite for portfolio optimization methods"""

    def test_equal_weight_calculation(
        self,
        diversification_calculator,
        unequal_positions
    ):
        """Test equal weight calculation"""
        result = diversification_calculator.calculate_equal_weight(unequal_positions)

        assert isinstance(result, OptimalWeights)
        assert result.method == "equal_weight"
        assert len(result.weights) == 5

        # All weights should be 20%
        for weight in result.weights.values():
            assert abs(weight - 0.20) < 0.001

    def test_risk_parity_weights(
        self,
        diversification_calculator,
        unequal_positions,
        sample_covariance_matrix
    ):
        """Test risk parity optimization"""
        result = diversification_calculator.calculate_risk_parity_weights(
            unequal_positions,
            sample_covariance_matrix
        )

        assert isinstance(result, OptimalWeights)
        assert result.method == "risk_parity"
        assert len(result.weights) == 5

        # Weights should sum to 1.0
        total_weight = sum(result.weights.values())
        assert abs(total_weight - 1.0) < 0.01

    def test_risk_parity_without_covariance(
        self,
        diversification_calculator,
        unequal_positions
    ):
        """Test risk parity with estimated covariance"""
        result = diversification_calculator.calculate_risk_parity_weights(
            unequal_positions,
            covariance_matrix=None
        )

        assert isinstance(result, OptimalWeights)
        assert len(result.weights) == 5

    def test_risk_parity_convergence(
        self,
        diversification_calculator,
        equal_weight_positions,
        sample_covariance_matrix
    ):
        """Test risk parity convergence status"""
        result = diversification_calculator.calculate_risk_parity_weights(
            equal_weight_positions,
            sample_covariance_matrix
        )

        # Should report convergence status
        assert isinstance(result.convergence_achieved, bool)
        assert result.iterations >= 0

    def test_mean_variance_weights(
        self,
        diversification_calculator,
        sample_covariance_matrix
    ):
        """Test mean-variance optimization"""
        positions = [
            PositionData(symbol="A", weight=0.2, position_value=20000,
                        volatility=0.60, expected_return=0.10),
            PositionData(symbol="B", weight=0.2, position_value=20000,
                        volatility=0.70, expected_return=0.12),
            PositionData(symbol="C", weight=0.2, position_value=20000,
                        volatility=0.80, expected_return=0.15),
            PositionData(symbol="D", weight=0.2, position_value=20000,
                        volatility=0.90, expected_return=0.08),
            PositionData(symbol="E", weight=0.2, position_value=20000,
                        volatility=0.85, expected_return=0.11),
        ]

        result = diversification_calculator.calculate_mean_variance_weights(
            positions,
            sample_covariance_matrix
        )

        assert isinstance(result, OptimalWeights)
        assert result.method == "mean_variance"


# =============================================================================
# WARNINGS AND RECOMMENDATIONS TESTS
# =============================================================================

class TestWarningsAndRecommendations:
    """Test suite for warnings and recommendations"""

    def test_single_position_critical_warning(self, diversification_calculator):
        """Test critical warning for single large position"""
        positions = [
            PositionData(symbol="BTCUSDT", weight=0.50, position_value=50000, volatility=0.60),
            PositionData(symbol="ETHUSDT", weight=0.50, position_value=50000, volatility=0.70),
        ]

        metrics = diversification_calculator.calculate_metrics(positions)

        # 50% position exceeds 30% limit
        critical_warnings = [
            w for w in metrics.warnings
            if w.severity == "CRITICAL" and "SINGLE_POSITION" in w.warning_type
        ]
        assert len(critical_warnings) > 0

    def test_single_position_warning(self, diversification_calculator):
        """Test warning for position approaching limit"""
        positions = [
            PositionData(symbol="BTCUSDT", weight=0.25, position_value=25000, volatility=0.60),
            PositionData(symbol="ETHUSDT", weight=0.25, position_value=25000, volatility=0.70),
            PositionData(symbol="SOLUSDT", weight=0.25, position_value=25000, volatility=0.80),
            PositionData(symbol="ARBUSDT", weight=0.25, position_value=25000, volatility=0.90),
        ]

        metrics = diversification_calculator.calculate_metrics(positions)

        # 25% position exceeds 20% warning threshold
        warnings = [
            w for w in metrics.warnings
            if w.severity == "WARNING" and "SINGLE_POSITION" in w.warning_type
        ]
        assert len(warnings) > 0

    def test_hhi_critical_warning(self, diversification_calculator):
        """Test critical warning for high HHI"""
        positions = [
            PositionData(symbol="BTCUSDT", weight=0.90, position_value=90000, volatility=0.60),
            PositionData(symbol="ETHUSDT", weight=0.10, position_value=10000, volatility=0.70),
        ]

        metrics = diversification_calculator.calculate_metrics(positions)

        # HHI = 0.81 + 0.01 = 0.82 (very high)
        hhi_warnings = [
            w for w in metrics.warnings
            if "HHI" in w.warning_type
        ]
        assert len(hhi_warnings) > 0

    def test_low_position_count_warning(self, diversification_calculator):
        """Test warning for low position count"""
        positions = [
            PositionData(symbol="BTCUSDT", weight=0.50, position_value=50000, volatility=0.60),
            PositionData(symbol="ETHUSDT", weight=0.50, position_value=50000, volatility=0.70),
        ]

        metrics = diversification_calculator.calculate_metrics(positions)

        # Only 2 positions
        count_warnings = [
            w for w in metrics.warnings
            if "POSITION_COUNT" in w.warning_type
        ]
        assert len(count_warnings) > 0

    def test_warning_to_dict(self, diversification_calculator, concentrated_positions):
        """Test warning serialization"""
        metrics = diversification_calculator.calculate_metrics(concentrated_positions)

        if metrics.warnings:
            warning_dict = metrics.warnings[0].to_dict()

            assert "warning_type" in warning_dict
            assert "severity" in warning_dict
            assert "message" in warning_dict
            assert "recommendation" in warning_dict


# =============================================================================
# REBALANCING TRADES TESTS
# =============================================================================

class TestRebalancingTrades:
    """Test suite for rebalancing trade calculation"""

    def test_rebalancing_trades_basic(
        self,
        diversification_calculator,
        unequal_positions
    ):
        """Test basic rebalancing trades calculation"""
        target_weights = {
            "BTCUSDT": 0.20,
            "ETHUSDT": 0.20,
            "SOLUSDT": 0.20,
            "ARBUSDT": 0.20,
            "UNIUSDT": 0.20,
        }

        trades = diversification_calculator.get_rebalancing_trades(
            unequal_positions,
            target_weights,
            portfolio_value=100000
        )

        assert isinstance(trades, list)
        assert len(trades) > 0

        # BTC should be sold (from 40% to 20%)
        btc_trade = next((t for t in trades if t["symbol"] == "BTCUSDT"), None)
        assert btc_trade is not None
        assert btc_trade["action"] == "SELL"

        # UNI should be bought (from 5% to 20%)
        uni_trade = next((t for t in trades if t["symbol"] == "UNIUSDT"), None)
        assert uni_trade is not None
        assert uni_trade["action"] == "BUY"

    def test_rebalancing_skips_small_trades(
        self,
        diversification_calculator,
        equal_weight_positions
    ):
        """Test that small trades are skipped"""
        # Target is same as current (equal weight)
        target_weights = {pos.symbol: 0.20 for pos in equal_weight_positions}

        trades = diversification_calculator.get_rebalancing_trades(
            equal_weight_positions,
            target_weights,
            portfolio_value=100000,
            min_trade_value=100.0
        )

        # Should have no trades since already at target
        assert len(trades) == 0


# =============================================================================
# SERIALIZATION TESTS
# =============================================================================

class TestSerialization:
    """Test suite for data serialization"""

    def test_metrics_to_dict(
        self,
        diversification_calculator,
        unequal_positions
    ):
        """Test DiversificationMetrics serialization"""
        metrics = diversification_calculator.calculate_metrics(unequal_positions)
        metrics_dict = metrics.to_dict()

        assert "position_count" in metrics_dict
        assert "hhi" in metrics_dict
        assert "effective_positions" in metrics_dict
        assert "concentration_level" in metrics_dict
        assert "risk_contributions" in metrics_dict
        assert "warnings" in metrics_dict
        assert "recommendations" in metrics_dict
        assert "timestamp" in metrics_dict

    def test_risk_contribution_to_dict(
        self,
        diversification_calculator,
        unequal_positions
    ):
        """Test RiskContribution serialization"""
        contributions = diversification_calculator.calculate_risk_contributions(
            unequal_positions
        )

        if contributions:
            rc_dict = contributions[0].to_dict()

            assert "symbol" in rc_dict
            assert "weight" in rc_dict
            assert "risk_contribution_pct" in rc_dict
            assert "is_over_threshold" in rc_dict

    def test_optimal_weights_to_dict(
        self,
        diversification_calculator,
        equal_weight_positions
    ):
        """Test OptimalWeights serialization"""
        result = diversification_calculator.calculate_equal_weight(equal_weight_positions)
        result_dict = result.to_dict()

        assert "method" in result_dict
        assert "weights" in result_dict
        assert "portfolio_volatility" in result_dict
        assert "convergence_achieved" in result_dict


# =============================================================================
# GLOBAL INSTANCE TESTS
# =============================================================================

class TestGlobalInstance:
    """Test suite for global instance management"""

    def test_get_diversification_calculator_singleton(self):
        """Test global calculator is a singleton"""
        reset_diversification_calculator()

        calc1 = get_diversification_calculator()
        calc2 = get_diversification_calculator()

        assert calc1 is calc2

    def test_reset_diversification_calculator(self):
        """Test reset creates new instance"""
        calc1 = get_diversification_calculator()
        reset_diversification_calculator()
        calc2 = get_diversification_calculator()

        assert calc1 is not calc2


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test suite for edge cases"""

    def test_single_position(self, diversification_calculator):
        """Test metrics with single position"""
        positions = [
            PositionData(symbol="BTCUSDT", weight=1.0, position_value=100000, volatility=0.60),
        ]

        metrics = diversification_calculator.calculate_metrics(positions)

        assert metrics.hhi == 1.0
        assert metrics.effective_positions == 1.0
        assert metrics.concentration_level == ConcentrationLevel.CONCENTRATED

    def test_many_small_positions(self, diversification_calculator):
        """Test metrics with many small positions"""
        n = 20
        weight = 1.0 / n
        positions = [
            PositionData(
                symbol=f"POS{i}USDT",
                weight=weight,
                position_value=1000,
                volatility=0.60 + i * 0.01
            )
            for i in range(n)
        ]

        metrics = diversification_calculator.calculate_metrics(positions)

        assert metrics.position_count == n
        # HHI for 20 equal weights = 0.05
        assert abs(metrics.hhi - 0.05) < 0.001
        assert metrics.concentration_level == ConcentrationLevel.EXCELLENT

    def test_zero_weights(self, diversification_calculator):
        """Test handling of zero weights"""
        weights = [0.0, 0.0, 0.0]
        hhi = diversification_calculator.calculate_hhi(weights)

        # Should handle gracefully
        assert hhi == 1.0  # Division by zero case

    def test_very_small_weights(self, diversification_calculator):
        """Test handling of very small weights"""
        positions = [
            PositionData(symbol="A", weight=0.000001, position_value=1, volatility=0.60),
            PositionData(symbol="B", weight=0.999999, position_value=999999, volatility=0.70),
        ]

        metrics = diversification_calculator.calculate_metrics(positions)

        # Should not crash, HHI should be close to 1.0
        assert metrics.hhi > 0.9

    def test_negative_pnl_positions(self, diversification_calculator):
        """Test positions with negative P&L"""
        positions = [
            PositionData(
                symbol="BTCUSDT",
                weight=0.50,
                position_value=40000,  # Started at 50000
                volatility=0.60,
                expected_return=-0.20
            ),
            PositionData(
                symbol="ETHUSDT",
                weight=0.50,
                position_value=35000,  # Started at 50000
                volatility=0.70,
                expected_return=-0.30
            ),
        ]

        # Should not crash
        metrics = diversification_calculator.calculate_metrics(positions)
        assert metrics.position_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
