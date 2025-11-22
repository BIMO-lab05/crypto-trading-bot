"""
Portfolio Optimizer - Advanced Portfolio Optimization Algorithms
Implements:
- Modern Portfolio Theory (Markowitz Mean-Variance Optimization)
- Kelly Criterion for position sizing
- Sharpe Ratio maximization
- Risk Parity allocation
- Maximum Diversification strategy
- Efficient Frontier generation
"""

import numpy as np
import pandas as pd
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
import logging

# Import optimization libraries
try:
    from scipy.optimize import minimize
    import cvxpy as cp
except ImportError:
    raise ImportError(
        "Required optimization libraries not installed. "
        "Please install: scipy>=1.11.0 cvxpy>=1.4.0"
    )

logger = logging.getLogger(__name__)


class OptimizationObjective(str, Enum):
    """Optimization objective types"""
    MAX_SHARPE = "max_sharpe"  # Maximize Sharpe Ratio
    MIN_VOLATILITY = "min_volatility"  # Minimize portfolio volatility
    MAX_RETURN = "max_return"  # Maximize expected return
    RISK_PARITY = "risk_parity"  # Equal risk contribution
    MAX_DIVERSIFICATION = "max_diversification"  # Maximum diversification ratio
    KELLY_CRITERION = "kelly_criterion"  # Kelly optimal sizing


class RebalanceStrategy(str, Enum):
    """Portfolio rebalancing strategies"""
    THRESHOLD = "threshold"  # Rebalance when drift exceeds threshold
    PERIODIC = "periodic"  # Rebalance on fixed schedule
    TACTICAL = "tactical"  # Opportunistic rebalancing
    NO_REBALANCE = "no_rebalance"  # Buy and hold


@dataclass
class OptimizationConstraints:
    """Constraints for portfolio optimization"""
    # Position size constraints
    max_position_size: float = 0.30  # Maximum 30% per position
    min_position_size: float = 0.05  # Minimum 5% per position

    # Risk constraints
    max_portfolio_volatility: Optional[float] = None  # Maximum portfolio volatility
    target_return: Optional[float] = None  # Target return for efficient frontier

    # Diversification constraints
    min_assets: int = 3  # Minimum number of assets
    max_assets: int = 10  # Maximum number of assets

    # Sector/correlation constraints
    max_sector_allocation: float = 0.50  # Maximum allocation to correlated assets
    min_correlation_threshold: float = -1.0  # Minimum acceptable correlation
    max_correlation_threshold: float = 1.0  # Maximum acceptable correlation

    # Transaction constraints
    max_turnover: float = 1.0  # Maximum portfolio turnover (100%)
    min_trade_size: float = 100.0  # Minimum trade size in USD


@dataclass
class OptimizationResult:
    """Result of portfolio optimization"""
    # Optimal weights for each symbol
    weights: Dict[str, float]

    # Expected performance metrics
    expected_return: float  # Annual expected return
    expected_volatility: float  # Annual volatility (std dev)
    sharpe_ratio: float  # Risk-adjusted return

    # Risk metrics
    max_drawdown: Optional[float] = None
    value_at_risk_95: Optional[float] = None  # 95% VaR
    conditional_var_95: Optional[float] = None  # 95% CVaR

    # Diversification metrics
    diversification_ratio: Optional[float] = None
    effective_num_assets: Optional[float] = None  # Inverse HHI

    # Optimization metadata
    objective: OptimizationObjective = OptimizationObjective.MAX_SHARPE
    constraints_met: bool = True
    optimization_time: float = 0.0  # Seconds
    message: str = "Optimization successful"


@dataclass
class EfficientFrontierPoint:
    """Single point on the efficient frontier"""
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float
    weights: Dict[str, float]


class PortfolioOptimizer:
    """
    Advanced Portfolio Optimization Engine

    Implements multiple optimization strategies:
    - Modern Portfolio Theory (Markowitz)
    - Kelly Criterion
    - Risk Parity
    - Maximum Diversification
    """

    def __init__(
        self,
        risk_free_rate: float = 0.04,  # 4% annual risk-free rate
        confidence_level: float = 0.95,  # 95% confidence for VaR/CVaR
        resampling_iterations: int = 100,  # For robust optimization
    ):
        """
        Initialize portfolio optimizer

        Args:
            risk_free_rate: Annual risk-free rate (e.g., 0.04 for 4%)
            confidence_level: Confidence level for risk metrics (0.95 = 95%)
            resampling_iterations: Number of iterations for robust optimization
        """
        self.risk_free_rate = risk_free_rate
        self.confidence_level = confidence_level
        self.resampling_iterations = resampling_iterations

        logger.info(
            f"Portfolio Optimizer initialized with risk-free rate: {risk_free_rate:.2%}, "
            f"confidence level: {confidence_level:.2%}"
        )

    def calculate_returns_from_prices(
        self,
        price_data: pd.DataFrame,
        period: str = "daily"
    ) -> pd.DataFrame:
        """
        Calculate returns from price data

        Args:
            price_data: DataFrame with symbols as columns and prices as rows
            period: Return period ('daily', 'hourly', 'weekly')

        Returns:
            DataFrame of returns
        """
        # Calculate log returns for better statistical properties
        returns = np.log(price_data / price_data.shift(1))

        # Drop NaN values from first row
        returns = returns.dropna()

        logger.debug(f"Calculated {len(returns)} {period} returns for {len(returns.columns)} assets")

        return returns

    def calculate_expected_returns(
        self,
        returns: pd.DataFrame,
        method: str = "mean"
    ) -> np.ndarray:
        """
        Calculate expected returns for each asset

        Args:
            returns: DataFrame of historical returns
            method: Estimation method ('mean', 'exponential', 'capm')

        Returns:
            Array of expected returns (annualized)
        """
        if method == "mean":
            # Simple historical mean (annualized)
            # Assuming daily returns, multiply by 252 trading days
            expected_returns = returns.mean() * 252

        elif method == "exponential":
            # Exponentially weighted moving average (gives more weight to recent data)
            span = 60  # 60-day span
            expected_returns = returns.ewm(span=span).mean().iloc[-1] * 252

        elif method == "capm":
            # CAPM-based expected returns (simplified - needs market data)
            # For crypto, use simple mean as fallback
            logger.warning("CAPM method not fully implemented, using mean")
            expected_returns = returns.mean() * 252

        else:
            raise ValueError(f"Unknown method: {method}")

        return expected_returns.values

    def calculate_covariance_matrix(
        self,
        returns: pd.DataFrame,
        method: str = "sample"
    ) -> np.ndarray:
        """
        Calculate covariance matrix of returns

        Args:
            returns: DataFrame of historical returns
            method: Estimation method ('sample', 'shrinkage', 'exponential')

        Returns:
            Covariance matrix (annualized)
        """
        if method == "sample":
            # Sample covariance matrix (annualized)
            cov_matrix = returns.cov() * 252

        elif method == "shrinkage":
            # Ledoit-Wolf shrinkage (reduces estimation error)
            from sklearn.covariance import LedoitWolf
            lw = LedoitWolf()
            cov_matrix = pd.DataFrame(
                lw.fit(returns).covariance_ * 252,
                index=returns.columns,
                columns=returns.columns
            )

        elif method == "exponential":
            # Exponentially weighted covariance
            cov_matrix = returns.ewm(span=60).cov().iloc[-len(returns.columns):] * 252

        else:
            raise ValueError(f"Unknown method: {method}")

        return cov_matrix.values

    def calculate_correlation_matrix(self, returns: pd.DataFrame) -> np.ndarray:
        """
        Calculate correlation matrix of returns

        Args:
            returns: DataFrame of historical returns

        Returns:
            Correlation matrix
        """
        return returns.corr().values

    def optimize_portfolio(
        self,
        returns: pd.DataFrame,
        objective: OptimizationObjective = OptimizationObjective.MAX_SHARPE,
        constraints: Optional[OptimizationConstraints] = None,
        current_weights: Optional[Dict[str, float]] = None
    ) -> OptimizationResult:
        """
        Optimize portfolio allocation

        Args:
            returns: DataFrame of historical returns
            objective: Optimization objective
            constraints: Optimization constraints
            current_weights: Current portfolio weights (for turnover constraint)

        Returns:
            OptimizationResult with optimal weights and metrics
        """
        start_time = datetime.now()

        # Set default constraints if not provided
        if constraints is None:
            constraints = OptimizationConstraints()

        # Calculate expected returns and covariance
        expected_returns = self.calculate_expected_returns(returns)
        cov_matrix = self.calculate_covariance_matrix(returns)

        # Get asset symbols
        symbols = returns.columns.tolist()
        n_assets = len(symbols)

        logger.info(
            f"Optimizing portfolio for {n_assets} assets with objective: {objective.value}"
        )

        # Choose optimization method based on objective
        if objective == OptimizationObjective.MAX_SHARPE:
            weights = self._optimize_max_sharpe(
                expected_returns, cov_matrix, constraints
            )
        elif objective == OptimizationObjective.MIN_VOLATILITY:
            weights = self._optimize_min_volatility(
                cov_matrix, constraints
            )
        elif objective == OptimizationObjective.MAX_RETURN:
            weights = self._optimize_max_return(
                expected_returns, cov_matrix, constraints
            )
        elif objective == OptimizationObjective.RISK_PARITY:
            weights = self._optimize_risk_parity(
                cov_matrix, constraints
            )
        elif objective == OptimizationObjective.MAX_DIVERSIFICATION:
            weights = self._optimize_max_diversification(
                cov_matrix, constraints
            )
        elif objective == OptimizationObjective.KELLY_CRITERION:
            weights = self._optimize_kelly_criterion(
                expected_returns, cov_matrix, constraints
            )
        else:
            raise ValueError(f"Unknown objective: {objective}")

        # Create weights dictionary
        weights_dict = {symbol: float(w) for symbol, w in zip(symbols, weights)}

        # Calculate portfolio metrics
        portfolio_return = float(np.dot(weights, expected_returns))
        portfolio_volatility = float(np.sqrt(np.dot(weights, np.dot(cov_matrix, weights))))
        sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_volatility if portfolio_volatility > 0 else 0.0

        # Calculate additional risk metrics
        var_95 = self._calculate_value_at_risk(weights, expected_returns, cov_matrix)
        cvar_95 = self._calculate_conditional_var(weights, expected_returns, cov_matrix)

        # Calculate diversification metrics
        diversification_ratio = self._calculate_diversification_ratio(weights, cov_matrix)
        effective_num_assets = self._calculate_effective_num_assets(weights)

        # Check if constraints are met
        constraints_met = self._check_constraints(weights, constraints)

        optimization_time = (datetime.now() - start_time).total_seconds()

        result = OptimizationResult(
            weights=weights_dict,
            expected_return=portfolio_return,
            expected_volatility=portfolio_volatility,
            sharpe_ratio=sharpe_ratio,
            value_at_risk_95=var_95,
            conditional_var_95=cvar_95,
            diversification_ratio=diversification_ratio,
            effective_num_assets=effective_num_assets,
            objective=objective,
            constraints_met=constraints_met,
            optimization_time=optimization_time,
            message="Optimization successful" if constraints_met else "Some constraints not met"
        )

        logger.info(
            f"Optimization complete in {optimization_time:.2f}s: "
            f"Return={portfolio_return:.2%}, Vol={portfolio_volatility:.2%}, "
            f"Sharpe={sharpe_ratio:.2f}"
        )

        return result

    def _optimize_max_sharpe(
        self,
        expected_returns: np.ndarray,
        cov_matrix: np.ndarray,
        constraints: OptimizationConstraints
    ) -> np.ndarray:
        """
        Maximize Sharpe Ratio (Markowitz optimization)

        The Sharpe ratio is: (Return - Risk_Free_Rate) / Volatility
        We maximize this by minimizing the negative Sharpe ratio
        """
        n_assets = len(expected_returns)

        # Objective function: minimize negative Sharpe ratio
        def objective(weights):
            portfolio_return = np.dot(weights, expected_returns)
            portfolio_volatility = np.sqrt(np.dot(weights, np.dot(cov_matrix, weights)))
            # Add small epsilon to avoid division by zero
            sharpe = -(portfolio_return - self.risk_free_rate) / (portfolio_volatility + 1e-10)
            return sharpe

        # Constraints
        constraints_list = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}  # Weights sum to 1
        ]

        # Bounds for each weight
        bounds = tuple(
            (constraints.min_position_size, constraints.max_position_size)
            for _ in range(n_assets)
        )

        # Initial guess: equal weights
        initial_weights = np.array([1.0 / n_assets] * n_assets)

        # Optimize
        result = minimize(
            objective,
            initial_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints_list,
            options={'maxiter': 1000}
        )

        if not result.success:
            logger.warning(f"Optimization warning: {result.message}")

        return result.x

    def _optimize_min_volatility(
        self,
        cov_matrix: np.ndarray,
        constraints: OptimizationConstraints
    ) -> np.ndarray:
        """
        Minimize portfolio volatility (minimum variance portfolio)
        """
        n_assets = cov_matrix.shape[0]

        # Objective: minimize variance (volatility squared)
        def objective(weights):
            return np.dot(weights, np.dot(cov_matrix, weights))

        # Constraints
        constraints_list = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}
        ]

        # Bounds
        bounds = tuple(
            (constraints.min_position_size, constraints.max_position_size)
            for _ in range(n_assets)
        )

        # Initial guess
        initial_weights = np.array([1.0 / n_assets] * n_assets)

        # Optimize
        result = minimize(
            objective,
            initial_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints_list,
            options={'maxiter': 1000}
        )

        return result.x

    def _optimize_max_return(
        self,
        expected_returns: np.ndarray,
        cov_matrix: np.ndarray,
        constraints: OptimizationConstraints
    ) -> np.ndarray:
        """
        Maximize expected return (subject to volatility constraint)
        """
        n_assets = len(expected_returns)

        # Objective: maximize return (minimize negative return)
        def objective(weights):
            return -np.dot(weights, expected_returns)

        # Constraints
        constraints_list = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}
        ]

        # Add volatility constraint if specified
        if constraints.max_portfolio_volatility is not None:
            def volatility_constraint(weights):
                vol = np.sqrt(np.dot(weights, np.dot(cov_matrix, weights)))
                return constraints.max_portfolio_volatility - vol
            constraints_list.append({'type': 'ineq', 'fun': volatility_constraint})

        # Bounds
        bounds = tuple(
            (constraints.min_position_size, constraints.max_position_size)
            for _ in range(n_assets)
        )

        # Initial guess
        initial_weights = np.array([1.0 / n_assets] * n_assets)

        # Optimize
        result = minimize(
            objective,
            initial_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints_list,
            options={'maxiter': 1000}
        )

        return result.x

    def _optimize_risk_parity(
        self,
        cov_matrix: np.ndarray,
        constraints: OptimizationConstraints
    ) -> np.ndarray:
        """
        Risk Parity allocation - equal risk contribution from each asset

        Each asset contributes equally to portfolio risk
        """
        n_assets = cov_matrix.shape[0]

        # Objective: minimize difference in risk contributions
        def objective(weights):
            portfolio_vol = np.sqrt(np.dot(weights, np.dot(cov_matrix, weights)))
            # Marginal contribution to risk
            marginal_contrib = np.dot(cov_matrix, weights) / (portfolio_vol + 1e-10)
            # Risk contribution
            risk_contrib = weights * marginal_contrib
            # Target: equal risk contribution
            target_contrib = portfolio_vol / n_assets
            # Minimize sum of squared deviations from target
            return np.sum((risk_contrib - target_contrib) ** 2)

        # Constraints
        constraints_list = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}
        ]

        # Bounds
        bounds = tuple(
            (constraints.min_position_size, constraints.max_position_size)
            for _ in range(n_assets)
        )

        # Initial guess: equal weights
        initial_weights = np.array([1.0 / n_assets] * n_assets)

        # Optimize
        result = minimize(
            objective,
            initial_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints_list,
            options={'maxiter': 1000}
        )

        return result.x

    def _optimize_max_diversification(
        self,
        cov_matrix: np.ndarray,
        constraints: OptimizationConstraints
    ) -> np.ndarray:
        """
        Maximum Diversification Portfolio

        Maximizes the diversification ratio:
        DR = (weighted average volatility) / (portfolio volatility)
        """
        n_assets = cov_matrix.shape[0]

        # Individual asset volatilities
        asset_vols = np.sqrt(np.diag(cov_matrix))

        # Objective: minimize negative diversification ratio
        def objective(weights):
            weighted_vol = np.dot(weights, asset_vols)
            portfolio_vol = np.sqrt(np.dot(weights, np.dot(cov_matrix, weights)))
            # Diversification ratio (higher is better)
            div_ratio = weighted_vol / (portfolio_vol + 1e-10)
            return -div_ratio  # Minimize negative = maximize positive

        # Constraints
        constraints_list = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}
        ]

        # Bounds
        bounds = tuple(
            (constraints.min_position_size, constraints.max_position_size)
            for _ in range(n_assets)
        )

        # Initial guess
        initial_weights = np.array([1.0 / n_assets] * n_assets)

        # Optimize
        result = minimize(
            objective,
            initial_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints_list,
            options={'maxiter': 1000}
        )

        return result.x

    def _optimize_kelly_criterion(
        self,
        expected_returns: np.ndarray,
        cov_matrix: np.ndarray,
        constraints: OptimizationConstraints
    ) -> np.ndarray:
        """
        Kelly Criterion optimal position sizing

        Kelly formula for multiple assets:
        f = C^-1 * (μ - r)
        where f = optimal fractions, C = covariance matrix, μ = expected returns, r = risk-free rate

        This maximizes long-term geometric growth rate
        """
        # Calculate Kelly optimal weights
        try:
            # Excess returns over risk-free rate
            excess_returns = expected_returns - self.risk_free_rate

            # Kelly weights: inverse covariance matrix times excess returns
            kelly_weights = np.linalg.solve(cov_matrix, excess_returns)

            # Normalize to sum to 1
            kelly_weights = kelly_weights / np.sum(np.abs(kelly_weights))

            # Apply constraints to Kelly weights
            # Clip weights to position size limits
            kelly_weights = np.clip(
                kelly_weights,
                constraints.min_position_size,
                constraints.max_position_size
            )

            # Renormalize
            kelly_weights = kelly_weights / np.sum(kelly_weights)

            # Kelly can be aggressive, so apply fractional Kelly (50%)
            fractional_kelly = 0.5
            kelly_weights = kelly_weights * fractional_kelly

            # Remaining weight goes to cash (represented as equal distribution)
            remaining = 1.0 - np.sum(kelly_weights)
            if remaining > 0:
                kelly_weights = kelly_weights + remaining / len(kelly_weights)

            return kelly_weights

        except np.linalg.LinAlgError:
            logger.warning("Kelly optimization failed (singular matrix), using equal weights")
            n_assets = len(expected_returns)
            return np.array([1.0 / n_assets] * n_assets)

    def generate_efficient_frontier(
        self,
        returns: pd.DataFrame,
        num_points: int = 50,
        constraints: Optional[OptimizationConstraints] = None
    ) -> List[EfficientFrontierPoint]:
        """
        Generate efficient frontier points

        The efficient frontier shows the set of optimal portfolios that offer
        the highest expected return for a defined level of risk

        Args:
            returns: DataFrame of historical returns
            num_points: Number of points to generate
            constraints: Optimization constraints

        Returns:
            List of EfficientFrontierPoint objects
        """
        logger.info(f"Generating efficient frontier with {num_points} points")

        if constraints is None:
            constraints = OptimizationConstraints()

        # Calculate expected returns and covariance
        expected_returns = self.calculate_expected_returns(returns)
        cov_matrix = self.calculate_covariance_matrix(returns)

        symbols = returns.columns.tolist()
        n_assets = len(symbols)

        # Find min volatility portfolio
        min_vol_weights = self._optimize_min_volatility(cov_matrix, constraints)
        min_vol_return = float(np.dot(min_vol_weights, expected_returns))

        # Find max return portfolio
        max_return_weights = self._optimize_max_return(expected_returns, cov_matrix, constraints)
        max_return = float(np.dot(max_return_weights, expected_returns))

        # Generate target returns from min to max
        target_returns = np.linspace(min_vol_return, max_return, num_points)

        frontier_points = []

        for target_return in target_returns:
            # Optimize for minimum volatility at this return level
            def objective(weights):
                return np.dot(weights, np.dot(cov_matrix, weights))

            # Constraints: weights sum to 1 and target return is met
            constraints_list = [
                {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0},
                {'type': 'eq', 'fun': lambda w: np.dot(w, expected_returns) - target_return}
            ]

            # Bounds
            bounds = tuple(
                (constraints.min_position_size, constraints.max_position_size)
                for _ in range(n_assets)
            )

            # Initial guess
            initial_weights = np.array([1.0 / n_assets] * n_assets)

            # Optimize
            result = minimize(
                objective,
                initial_weights,
                method='SLSQP',
                bounds=bounds,
                constraints=constraints_list,
                options={'maxiter': 1000}
            )

            if result.success:
                weights = result.x
                weights_dict = {symbol: float(w) for symbol, w in zip(symbols, weights)}

                portfolio_return = float(np.dot(weights, expected_returns))
                portfolio_volatility = float(np.sqrt(np.dot(weights, np.dot(cov_matrix, weights))))
                sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_volatility if portfolio_volatility > 0 else 0.0

                point = EfficientFrontierPoint(
                    expected_return=portfolio_return,
                    expected_volatility=portfolio_volatility,
                    sharpe_ratio=sharpe_ratio,
                    weights=weights_dict
                )

                frontier_points.append(point)

        logger.info(f"Generated {len(frontier_points)} efficient frontier points")

        return frontier_points

    def calculate_rebalancing_trades(
        self,
        current_weights: Dict[str, float],
        target_weights: Dict[str, float],
        portfolio_value: float,
        min_trade_size: float = 100.0
    ) -> Dict[str, Tuple[str, float]]:
        """
        Calculate required trades to rebalance portfolio

        Args:
            current_weights: Current portfolio weights
            target_weights: Target portfolio weights
            portfolio_value: Total portfolio value
            min_trade_size: Minimum trade size in USD

        Returns:
            Dictionary of {symbol: (action, amount_usd)}
        """
        trades = {}

        # Combine all symbols
        all_symbols = set(current_weights.keys()) | set(target_weights.keys())

        for symbol in all_symbols:
            current_weight = current_weights.get(symbol, 0.0)
            target_weight = target_weights.get(symbol, 0.0)

            # Calculate dollar difference
            current_value = current_weight * portfolio_value
            target_value = target_weight * portfolio_value
            difference = target_value - current_value

            # Determine action
            if abs(difference) >= min_trade_size:
                if difference > 0:
                    trades[symbol] = ("BUY", abs(difference))
                else:
                    trades[symbol] = ("SELL", abs(difference))

        logger.info(f"Calculated {len(trades)} rebalancing trades")

        return trades

    def _calculate_value_at_risk(
        self,
        weights: np.ndarray,
        expected_returns: np.ndarray,
        cov_matrix: np.ndarray
    ) -> float:
        """
        Calculate Value at Risk (VaR) at confidence level

        VaR is the maximum expected loss over a time period at a given confidence level
        """
        portfolio_return = np.dot(weights, expected_returns)
        portfolio_volatility = np.sqrt(np.dot(weights, np.dot(cov_matrix, weights)))

        # Using parametric VaR (assumes normal distribution)
        from scipy.stats import norm
        z_score = norm.ppf(1 - self.confidence_level)

        # Daily VaR (convert annual to daily)
        daily_return = portfolio_return / 252
        daily_vol = portfolio_volatility / np.sqrt(252)

        var = -(daily_return + z_score * daily_vol)

        return float(var)

    def _calculate_conditional_var(
        self,
        weights: np.ndarray,
        expected_returns: np.ndarray,
        cov_matrix: np.ndarray
    ) -> float:
        """
        Calculate Conditional Value at Risk (CVaR or Expected Shortfall)

        CVaR is the expected loss given that the loss exceeds VaR
        """
        portfolio_return = np.dot(weights, expected_returns)
        portfolio_volatility = np.sqrt(np.dot(weights, np.dot(cov_matrix, weights)))

        # Using parametric CVaR (assumes normal distribution)
        from scipy.stats import norm
        z_score = norm.ppf(1 - self.confidence_level)

        # Daily CVaR
        daily_return = portfolio_return / 252
        daily_vol = portfolio_volatility / np.sqrt(252)

        cvar = -(daily_return - daily_vol * norm.pdf(z_score) / (1 - self.confidence_level))

        return float(cvar)

    def _calculate_diversification_ratio(
        self,
        weights: np.ndarray,
        cov_matrix: np.ndarray
    ) -> float:
        """
        Calculate diversification ratio

        DR = (weighted average volatility) / (portfolio volatility)
        Higher values indicate better diversification
        """
        asset_vols = np.sqrt(np.diag(cov_matrix))
        weighted_vol = np.dot(weights, asset_vols)
        portfolio_vol = np.sqrt(np.dot(weights, np.dot(cov_matrix, weights)))

        if portfolio_vol == 0:
            return 1.0

        return float(weighted_vol / portfolio_vol)

    def _calculate_effective_num_assets(self, weights: np.ndarray) -> float:
        """
        Calculate effective number of assets (inverse HHI - Herfindahl-Hirschman Index)

        This measures portfolio concentration
        Range: [1, N] where N is number of assets
        Higher values indicate better diversification
        """
        # Herfindahl-Hirschman Index
        hhi = np.sum(weights ** 2)

        # Effective number of assets
        if hhi == 0:
            return 1.0

        return float(1.0 / hhi)

    def _check_constraints(
        self,
        weights: np.ndarray,
        constraints: OptimizationConstraints
    ) -> bool:
        """
        Check if portfolio weights meet all constraints
        """
        # Check weight bounds
        if np.any(weights < constraints.min_position_size) or np.any(weights > constraints.max_position_size):
            return False

        # Check sum to 1
        if not np.isclose(np.sum(weights), 1.0, atol=1e-6):
            return False

        # Check number of assets
        non_zero_assets = np.sum(weights > 0.001)  # Consider > 0.1% as non-zero
        if non_zero_assets < constraints.min_assets or non_zero_assets > constraints.max_assets:
            return False

        return True
