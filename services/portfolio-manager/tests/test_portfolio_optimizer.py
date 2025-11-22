"""
Test Portfolio Optimizer
Comprehensive tests for portfolio optimization algorithms
Target: >90% coverage
"""

import pytest
import numpy as np
import pandas as pd
from decimal import Decimal
from datetime import datetime, timedelta

from app.optimization.portfolio_optimizer import (
    PortfolioOptimizer,
    OptimizationObjective,
    OptimizationConstraints,
    OptimizationResult,
    EfficientFrontierPoint,
)


@pytest.fixture
def optimizer():
    """Create portfolio optimizer instance"""
    return PortfolioOptimizer(
        risk_free_rate=0.04,
        confidence_level=0.95,
        resampling_iterations=100
    )


@pytest.fixture
def sample_price_data():
    """Generate sample price data for testing"""
    # Create 252 trading days of data (1 year)
    dates = pd.date_range(end=datetime.now(), periods=252, freq='D')

    # Simulate price data for 3 assets with different characteristics
    np.random.seed(42)  # For reproducibility

    # Asset 1: High return, high volatility (like BTC)
    asset1_returns = np.random.normal(0.001, 0.03, 252)  # 0.1% daily return, 3% volatility
    asset1_prices = 50000 * np.exp(np.cumsum(asset1_returns))

    # Asset 2: Medium return, medium volatility (like ETH)
    asset2_returns = np.random.normal(0.0008, 0.025, 252)
    asset2_prices = 3000 * np.exp(np.cumsum(asset2_returns))

    # Asset 3: Lower return, lower volatility (like stablecoin pair)
    asset3_returns = np.random.normal(0.0003, 0.01, 252)
    asset3_prices = 100 * np.exp(np.cumsum(asset3_returns))

    # Create DataFrame
    price_data = pd.DataFrame({
        'BTCUSDT': asset1_prices,
        'ETHUSDT': asset2_prices,
        'BNBUSDT': asset3_prices
    }, index=dates)

    return price_data


@pytest.fixture
def sample_returns(optimizer, sample_price_data):
    """Calculate returns from sample price data"""
    return optimizer.calculate_returns_from_prices(sample_price_data)


class TestPortfolioOptimizer:
    """Test PortfolioOptimizer class"""

    def test_optimizer_initialization(self, optimizer):
        """Test optimizer is initialized with correct parameters"""
        assert optimizer.risk_free_rate == 0.04
        assert optimizer.confidence_level == 0.95
        assert optimizer.resampling_iterations == 100

    def test_calculate_returns_from_prices(self, optimizer, sample_price_data):
        """Test returns calculation from price data"""
        returns = optimizer.calculate_returns_from_prices(sample_price_data)

        # Check returns DataFrame shape
        assert len(returns) == len(sample_price_data) - 1  # One less due to diff
        assert list(returns.columns) == list(sample_price_data.columns)

        # Check no NaN values
        assert not returns.isnull().any().any()

        # Check returns are reasonable (not too extreme)
        assert returns.abs().max().max() < 1.0  # Max 100% single-day return

    def test_calculate_expected_returns_mean(self, optimizer, sample_returns):
        """Test expected returns calculation using mean method"""
        expected_returns = optimizer.calculate_expected_returns(
            sample_returns,
            method="mean"
        )

        # Check shape
        assert len(expected_returns) == len(sample_returns.columns)

        # Check all returns are finite
        assert np.all(np.isfinite(expected_returns))

    def test_calculate_expected_returns_exponential(self, optimizer, sample_returns):
        """Test expected returns calculation using exponential weighting"""
        expected_returns = optimizer.calculate_expected_returns(
            sample_returns,
            method="exponential"
        )

        # Check shape
        assert len(expected_returns) == len(sample_returns.columns)

        # Check all returns are finite
        assert np.all(np.isfinite(expected_returns))

    def test_calculate_covariance_matrix(self, optimizer, sample_returns):
        """Test covariance matrix calculation"""
        cov_matrix = optimizer.calculate_covariance_matrix(
            sample_returns,
            method="sample"
        )

        # Check shape (square matrix)
        n_assets = len(sample_returns.columns)
        assert cov_matrix.shape == (n_assets, n_assets)

        # Check symmetry
        assert np.allclose(cov_matrix, cov_matrix.T)

        # Check positive semi-definite (all eigenvalues >= 0)
        eigenvalues = np.linalg.eigvals(cov_matrix)
        assert np.all(eigenvalues >= -1e-10)  # Allow small numerical errors

    def test_calculate_correlation_matrix(self, optimizer, sample_returns):
        """Test correlation matrix calculation"""
        corr_matrix = optimizer.calculate_correlation_matrix(sample_returns)

        # Check shape
        n_assets = len(sample_returns.columns)
        assert corr_matrix.shape == (n_assets, n_assets)

        # Check diagonal is all 1s (correlation with self)
        assert np.allclose(np.diag(corr_matrix), 1.0)

        # Check all correlations are in [-1, 1]
        assert np.all(corr_matrix >= -1.0) and np.all(corr_matrix <= 1.0)

    def test_optimize_max_sharpe(self, optimizer, sample_returns):
        """Test maximum Sharpe ratio optimization"""
        result = optimizer.optimize_portfolio(
            returns=sample_returns,
            objective=OptimizationObjective.MAX_SHARPE
        )

        # Check result structure
        assert isinstance(result, OptimizationResult)
        assert result.objective == OptimizationObjective.MAX_SHARPE

        # Check weights
        assert len(result.weights) == len(sample_returns.columns)
        assert abs(sum(result.weights.values()) - 1.0) < 0.01  # Sum to 1
        assert all(0 <= w <= 1 for w in result.weights.values())  # All between 0 and 1

        # Check metrics
        assert result.expected_return is not None
        assert result.expected_volatility is not None
        assert result.sharpe_ratio is not None

        # Check Sharpe ratio is positive (for our sample data)
        assert result.sharpe_ratio > 0

    def test_optimize_min_volatility(self, optimizer, sample_returns):
        """Test minimum volatility optimization"""
        result = optimizer.optimize_portfolio(
            returns=sample_returns,
            objective=OptimizationObjective.MIN_VOLATILITY
        )

        # Check result
        assert result.objective == OptimizationObjective.MIN_VOLATILITY
        assert abs(sum(result.weights.values()) - 1.0) < 0.01

        # Volatility should be lower than equal-weight portfolio
        equal_weights = np.array([1/3, 1/3, 1/3])
        expected_returns = optimizer.calculate_expected_returns(sample_returns)
        cov_matrix = optimizer.calculate_covariance_matrix(sample_returns)
        equal_vol = np.sqrt(np.dot(equal_weights, np.dot(cov_matrix, equal_weights)))

        assert result.expected_volatility <= equal_vol + 0.01  # Small tolerance

    def test_optimize_risk_parity(self, optimizer, sample_returns):
        """Test risk parity optimization"""
        result = optimizer.optimize_portfolio(
            returns=sample_returns,
            objective=OptimizationObjective.RISK_PARITY
        )

        # Check result
        assert result.objective == OptimizationObjective.RISK_PARITY
        assert abs(sum(result.weights.values()) - 1.0) < 0.01

        # All weights should be positive for risk parity
        assert all(w > 0 for w in result.weights.values())

    def test_optimize_max_diversification(self, optimizer, sample_returns):
        """Test maximum diversification optimization"""
        result = optimizer.optimize_portfolio(
            returns=sample_returns,
            objective=OptimizationObjective.MAX_DIVERSIFICATION
        )

        # Check result
        assert result.objective == OptimizationObjective.MAX_DIVERSIFICATION
        assert abs(sum(result.weights.values()) - 1.0) < 0.01

        # Check diversification ratio is calculated
        assert result.diversification_ratio is not None
        assert result.diversification_ratio >= 1.0  # DR should be >= 1

    def test_optimize_kelly_criterion(self, optimizer, sample_returns):
        """Test Kelly Criterion optimization"""
        result = optimizer.optimize_portfolio(
            returns=sample_returns,
            objective=OptimizationObjective.KELLY_CRITERION
        )

        # Check result
        assert result.objective == OptimizationObjective.KELLY_CRITERION
        assert abs(sum(result.weights.values()) - 1.0) < 0.01

    def test_optimize_with_constraints(self, optimizer, sample_returns):
        """Test optimization with custom constraints"""
        constraints = OptimizationConstraints(
            max_position_size=0.5,  # Max 50% per asset
            min_position_size=0.1,  # Min 10% per asset
            max_portfolio_volatility=0.25
        )

        result = optimizer.optimize_portfolio(
            returns=sample_returns,
            objective=OptimizationObjective.MAX_SHARPE,
            constraints=constraints
        )

        # Check position size constraints
        for weight in result.weights.values():
            assert weight >= constraints.min_position_size - 0.01
            assert weight <= constraints.max_position_size + 0.01

    def test_generate_efficient_frontier(self, optimizer, sample_returns):
        """Test efficient frontier generation"""
        num_points = 20
        frontier_points = optimizer.generate_efficient_frontier(
            returns=sample_returns,
            num_points=num_points
        )

        # Check we get points
        assert len(frontier_points) > 0
        assert len(frontier_points) <= num_points

        # Check each point
        for point in frontier_points:
            assert isinstance(point, EfficientFrontierPoint)
            assert point.expected_return is not None
            assert point.expected_volatility is not None
            assert point.sharpe_ratio is not None
            assert len(point.weights) == len(sample_returns.columns)
            assert abs(sum(point.weights.values()) - 1.0) < 0.01

        # Check points are ordered by volatility (approximately)
        volatilities = [p.expected_volatility for p in frontier_points]
        # Allow some tolerance for numerical optimization
        assert volatilities == sorted(volatilities) or \
               all(abs(volatilities[i] - volatilities[i+1]) < 0.05
                   for i in range(len(volatilities)-1))

    def test_calculate_rebalancing_trades(self, optimizer):
        """Test rebalancing trade calculation"""
        current_weights = {
            'BTCUSDT': 0.50,
            'ETHUSDT': 0.30,
            'BNBUSDT': 0.20
        }

        target_weights = {
            'BTCUSDT': 0.40,
            'ETHUSDT': 0.35,
            'BNBUSDT': 0.25
        }

        portfolio_value = 10000.0

        trades = optimizer.calculate_rebalancing_trades(
            current_weights=current_weights,
            target_weights=target_weights,
            portfolio_value=portfolio_value,
            min_trade_size=100.0
        )

        # Check trades structure
        assert isinstance(trades, dict)

        # BTCUSDT should be sold (50% -> 40%)
        if 'BTCUSDT' in trades:
            action, amount = trades['BTCUSDT']
            assert action == "SELL"
            assert amount == pytest.approx(1000.0, abs=10)  # 10% of 10000

        # ETHUSDT should be bought (30% -> 35%)
        if 'ETHUSDT' in trades:
            action, amount = trades['ETHUSDT']
            assert action == "BUY"
            assert amount == pytest.approx(500.0, abs=10)  # 5% of 10000

        # BNBUSDT should be bought (20% -> 25%)
        if 'BNBUSDT' in trades:
            action, amount = trades['BNBUSDT']
            assert action == "BUY"
            assert amount == pytest.approx(500.0, abs=10)  # 5% of 10000

    def test_value_at_risk_calculation(self, optimizer, sample_returns):
        """Test VaR calculation"""
        expected_returns = optimizer.calculate_expected_returns(sample_returns)
        cov_matrix = optimizer.calculate_covariance_matrix(sample_returns)
        weights = np.array([1/3, 1/3, 1/3])

        var = optimizer._calculate_value_at_risk(weights, expected_returns, cov_matrix)

        # VaR should be positive and reasonable
        assert var > 0
        assert var < 0.5  # Less than 50% daily loss at 95% confidence

    def test_conditional_var_calculation(self, optimizer, sample_returns):
        """Test CVaR calculation"""
        expected_returns = optimizer.calculate_expected_returns(sample_returns)
        cov_matrix = optimizer.calculate_covariance_matrix(sample_returns)
        weights = np.array([1/3, 1/3, 1/3])

        cvar = optimizer._calculate_conditional_var(weights, expected_returns, cov_matrix)

        # CVaR should be positive and greater than VaR
        var = optimizer._calculate_value_at_risk(weights, expected_returns, cov_matrix)
        assert cvar > 0
        assert cvar >= var  # CVaR should be >= VaR

    def test_diversification_ratio_calculation(self, optimizer, sample_returns):
        """Test diversification ratio calculation"""
        cov_matrix = optimizer.calculate_covariance_matrix(sample_returns)

        # Test with equal weights
        equal_weights = np.array([1/3, 1/3, 1/3])
        div_ratio = optimizer._calculate_diversification_ratio(equal_weights, cov_matrix)

        assert div_ratio >= 1.0  # DR should be at least 1
        assert div_ratio <= len(equal_weights)  # DR should be at most N (num assets)

    def test_effective_num_assets_calculation(self, optimizer):
        """Test effective number of assets calculation"""
        # Test with equal weights (should give actual number of assets)
        equal_weights = np.array([1/3, 1/3, 1/3])
        eff_num = optimizer._calculate_effective_num_assets(equal_weights)
        assert eff_num == pytest.approx(3.0, abs=0.1)

        # Test with concentrated weights (should give lower number)
        concentrated_weights = np.array([0.8, 0.15, 0.05])
        eff_num = optimizer._calculate_effective_num_assets(concentrated_weights)
        assert eff_num < 3.0
        assert eff_num >= 1.0

    def test_constraints_checking(self, optimizer):
        """Test constraint validation"""
        constraints = OptimizationConstraints(
            max_position_size=0.5,
            min_position_size=0.1,
            min_assets=2,
            max_assets=5
        )

        # Valid weights
        valid_weights = np.array([0.4, 0.35, 0.25])
        assert optimizer._check_constraints(valid_weights, constraints)

        # Invalid: weight too large
        invalid_weights = np.array([0.7, 0.2, 0.1])
        assert not optimizer._check_constraints(invalid_weights, constraints)

        # Invalid: weight too small
        invalid_weights = np.array([0.05, 0.45, 0.5])
        assert not optimizer._check_constraints(invalid_weights, constraints)

    def test_optimization_time_tracking(self, optimizer, sample_returns):
        """Test that optimization time is tracked"""
        result = optimizer.optimize_portfolio(
            returns=sample_returns,
            objective=OptimizationObjective.MAX_SHARPE
        )

        assert result.optimization_time > 0
        assert result.optimization_time < 10  # Should complete in reasonable time


class TestOptimizationConstraints:
    """Test OptimizationConstraints dataclass"""

    def test_default_constraints(self):
        """Test default constraint values"""
        constraints = OptimizationConstraints()

        assert constraints.max_position_size == 0.30
        assert constraints.min_position_size == 0.05
        assert constraints.min_assets == 3
        assert constraints.max_assets == 10
        assert constraints.max_sector_allocation == 0.50

    def test_custom_constraints(self):
        """Test custom constraint values"""
        constraints = OptimizationConstraints(
            max_position_size=0.40,
            min_position_size=0.10,
            max_portfolio_volatility=0.20,
            target_return=0.15
        )

        assert constraints.max_position_size == 0.40
        assert constraints.min_position_size == 0.10
        assert constraints.max_portfolio_volatility == 0.20
        assert constraints.target_return == 0.15


class TestOptimizationResult:
    """Test OptimizationResult dataclass"""

    def test_result_creation(self):
        """Test creating optimization result"""
        result = OptimizationResult(
            weights={'BTCUSDT': 0.5, 'ETHUSDT': 0.5},
            expected_return=0.25,
            expected_volatility=0.30,
            sharpe_ratio=0.70,
            objective=OptimizationObjective.MAX_SHARPE
        )

        assert len(result.weights) == 2
        assert result.expected_return == 0.25
        assert result.expected_volatility == 0.30
        assert result.sharpe_ratio == 0.70
        assert result.objective == OptimizationObjective.MAX_SHARPE


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_single_asset_optimization(self, optimizer):
        """Test that single asset raises appropriate error"""
        # Create single asset price data
        dates = pd.date_range(end=datetime.now(), periods=100, freq='D')
        price_data = pd.DataFrame({
            'BTCUSDT': np.random.randn(100).cumsum() + 50000
        }, index=dates)

        returns = optimizer.calculate_returns_from_prices(price_data)

        # Should handle single asset case (though not very useful)
        # The optimization will still work but all weight goes to the single asset
        result = optimizer.optimize_portfolio(
            returns=returns,
            objective=OptimizationObjective.MAX_SHARPE
        )

        assert result.weights['BTCUSDT'] == pytest.approx(1.0, abs=0.01)

    def test_zero_volatility_asset(self, optimizer):
        """Test handling of asset with zero volatility"""
        dates = pd.date_range(end=datetime.now(), periods=100, freq='D')

        # Create price data with one constant price asset
        price_data = pd.DataFrame({
            'BTCUSDT': np.random.randn(100).cumsum() + 50000,
            'STABLE': np.ones(100) * 1.0  # Constant price
        }, index=dates)

        returns = optimizer.calculate_returns_from_prices(price_data)

        # Should handle zero volatility
        result = optimizer.optimize_portfolio(
            returns=returns,
            objective=OptimizationObjective.MIN_VOLATILITY
        )

        # Should allocate heavily to stable asset for min volatility
        assert result.weights['STABLE'] > 0.5

    def test_negative_returns(self, optimizer):
        """Test optimization with negative returns"""
        dates = pd.date_range(end=datetime.now(), periods=100, freq='D')

        # Create declining price data
        price_data = pd.DataFrame({
            'BTCUSDT': np.exp(-0.01 * np.arange(100)) * 50000,
            'ETHUSDT': np.exp(-0.015 * np.arange(100)) * 3000
        }, index=dates)

        returns = optimizer.calculate_returns_from_prices(price_data)

        # Should still optimize even with negative returns
        result = optimizer.optimize_portfolio(
            returns=returns,
            objective=OptimizationObjective.MAX_SHARPE
        )

        # Sharpe ratio might be negative with declining assets
        assert result.expected_return < 0
        assert abs(sum(result.weights.values()) - 1.0) < 0.01


@pytest.mark.integration
class TestIntegrationScenarios:
    """Integration tests for real-world scenarios"""

    def test_full_optimization_workflow(self, optimizer, sample_price_data):
        """Test complete optimization workflow"""
        # 1. Calculate returns
        returns = optimizer.calculate_returns_from_prices(sample_price_data)

        # 2. Optimize for max Sharpe
        result = optimizer.optimize_portfolio(
            returns=returns,
            objective=OptimizationObjective.MAX_SHARPE
        )

        # 3. Generate efficient frontier
        frontier = optimizer.generate_efficient_frontier(
            returns=returns,
            num_points=10
        )

        # 4. Calculate rebalancing trades
        current_weights = {'BTCUSDT': 0.33, 'ETHUSDT': 0.33, 'BNBUSDT': 0.34}
        trades = optimizer.calculate_rebalancing_trades(
            current_weights=current_weights,
            target_weights=result.weights,
            portfolio_value=10000.0
        )

        # All steps should complete successfully
        assert result is not None
        assert len(frontier) > 0
        assert isinstance(trades, dict)

    def test_compare_optimization_objectives(self, optimizer, sample_returns):
        """Test and compare different optimization objectives"""
        objectives = [
            OptimizationObjective.MAX_SHARPE,
            OptimizationObjective.MIN_VOLATILITY,
            OptimizationObjective.RISK_PARITY,
            OptimizationObjective.MAX_DIVERSIFICATION
        ]

        results = {}
        for objective in objectives:
            result = optimizer.optimize_portfolio(
                returns=sample_returns,
                objective=objective
            )
            results[objective] = result

        # All optimizations should succeed
        assert len(results) == len(objectives)

        # Min volatility should have lowest volatility
        min_vol_result = results[OptimizationObjective.MIN_VOLATILITY]
        assert all(
            min_vol_result.expected_volatility <= result.expected_volatility + 0.01
            for objective, result in results.items()
            if objective != OptimizationObjective.MIN_VOLATILITY
        )

        # Risk parity should have similar weights (more diversified)
        risk_parity_result = results[OptimizationObjective.RISK_PARITY]
        weights_std = np.std(list(risk_parity_result.weights.values()))
        assert weights_std < 0.2  # Weights should be relatively similar
