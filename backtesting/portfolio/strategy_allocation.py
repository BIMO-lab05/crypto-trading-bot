#!/usr/bin/env python3
"""
Strategy Allocation Optimizer
Phase 1.3 - Portfolio Capital Allocation

This module provides advanced allocation optimization methods for
portfolio construction, including risk parity, Kelly criterion,
and Sharpe-weighted approaches.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging
from scipy.optimize import minimize

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AllocationResult:
    """Result of allocation optimization"""
    weights: Dict[str, float]  # Strategy name -> allocation percentage
    method: str
    expected_return: float
    expected_sharpe: float
    expected_volatility: float
    diversification_ratio: float

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'weights': self.weights,
            'method': self.method,
            'expected_return': self.expected_return,
            'expected_sharpe': self.expected_sharpe,
            'expected_volatility': self.expected_volatility,
            'diversification_ratio': self.diversification_ratio
        }


class StrategyAllocator:
    """
    Optimize capital allocation across multiple strategies

    Methods:
    - Equal Weight: Simple 1/N allocation
    - Sharpe Weighted: Weight by risk-adjusted returns
    - Risk Parity: Equal risk contribution from each strategy
    - Kelly Optimal: Kelly criterion for maximum growth
    - Minimum Variance: Minimize portfolio volatility
    - Maximum Sharpe: Optimize for highest Sharpe ratio
    """

    def __init__(
        self,
        min_allocation: float = 0.05,  # Minimum 5% per strategy
        max_allocation: float = 0.50   # Maximum 50% per strategy
    ):
        """
        Initialize strategy allocator

        Args:
            min_allocation: Minimum allocation per strategy (0-1)
            max_allocation: Maximum allocation per strategy (0-1)
        """
        self.min_allocation = min_allocation
        self.max_allocation = max_allocation
        logger.info(f"StrategyAllocator initialized (min={min_allocation:.0%}, max={max_allocation:.0%})")

    def equal_weight(
        self,
        strategy_names: List[str]
    ) -> AllocationResult:
        """
        Equal weight allocation (1/N)

        Args:
            strategy_names: List of strategy names

        Returns:
            AllocationResult with equal weights
        """
        n = len(strategy_names)
        weight = 1.0 / n

        weights = {name: weight for name in strategy_names}

        logger.info(f"Equal weight allocation: {weight:.2%} per strategy")

        return AllocationResult(
            weights=weights,
            method="equal_weight",
            expected_return=0.0,  # Unknown without historical data
            expected_sharpe=0.0,
            expected_volatility=0.0,
            diversification_ratio=1.0
        )

    def sharpe_weighted(
        self,
        strategy_metrics: Dict[str, Dict]
    ) -> AllocationResult:
        """
        Weight strategies by their Sharpe ratios

        Args:
            strategy_metrics: Dict of {strategy_name: {'sharpe': float, 'return': float}}

        Returns:
            AllocationResult with Sharpe-weighted allocations
        """
        # Extract Sharpe ratios
        sharpe_ratios = {}
        for name, metrics in strategy_metrics.items():
            sharpe = metrics.get('sharpe', 0.0)
            # Only use positive Sharpe ratios
            sharpe_ratios[name] = max(sharpe, 0.0)

        # Calculate total Sharpe
        total_sharpe = sum(sharpe_ratios.values())

        if total_sharpe <= 0:
            logger.warning("All Sharpe ratios <= 0, falling back to equal weight")
            return self.equal_weight(list(strategy_metrics.keys()))

        # Calculate weights proportional to Sharpe
        weights = {}
        for name, sharpe in sharpe_ratios.items():
            weight = sharpe / total_sharpe
            weights[name] = weight

        # Apply constraints and normalize properly
        weights = self._apply_constraints(weights)

        # Calculate expected portfolio metrics
        expected_return = sum(
            weights[name] * strategy_metrics[name].get('return', 0.0)
            for name in weights.keys()
        )

        expected_sharpe = sum(
            weights[name] * sharpe_ratios[name]
            for name in weights.keys()
        )

        logger.info(f"Sharpe-weighted allocation: E[Return]={expected_return:.2%}, E[Sharpe]={expected_sharpe:.2f}")

        return AllocationResult(
            weights=weights,
            method="sharpe_weighted",
            expected_return=expected_return,
            expected_sharpe=expected_sharpe,
            expected_volatility=0.0,  # Would need returns series
            diversification_ratio=self._calculate_diversification(weights)
        )

    def risk_parity(
        self,
        strategy_metrics: Dict[str, Dict],
        returns_data: Optional[pd.DataFrame] = None
    ) -> AllocationResult:
        """
        Risk parity allocation - equal risk contribution

        Args:
            strategy_metrics: Dict of strategy metrics
            returns_data: Optional DataFrame with columns as strategy names, rows as daily returns

        Returns:
            AllocationResult with risk parity weights
        """
        if returns_data is None:
            # Without returns data, use volatility from metrics if available
            volatilities = {}
            for name, metrics in strategy_metrics.items():
                vol = metrics.get('volatility', 1.0)
                volatilities[name] = vol if vol > 0 else 1.0

            # Inverse volatility weighting
            inv_vol = {name: 1.0 / vol for name, vol in volatilities.items()}
            total_inv_vol = sum(inv_vol.values())

            weights = {name: iv / total_inv_vol for name, iv in inv_vol.items()}
        else:
            # Calculate covariance matrix
            cov_matrix = returns_data.cov()

            # Use optimization to find risk parity weights
            weights = self._optimize_risk_parity(cov_matrix)

        # Apply constraints
        weights = self._apply_constraints(weights)

        logger.info("Risk parity allocation calculated")

        return AllocationResult(
            weights=weights,
            method="risk_parity",
            expected_return=sum(weights[name] * strategy_metrics[name].get('return', 0.0)
                               for name in weights.keys()),
            expected_sharpe=0.0,
            expected_volatility=0.0,
            diversification_ratio=self._calculate_diversification(weights)
        )

    def kelly_optimal(
        self,
        strategy_metrics: Dict[str, Dict]
    ) -> AllocationResult:
        """
        Kelly criterion allocation for maximum geometric growth

        Args:
            strategy_metrics: Dict with 'win_rate', 'avg_win', 'avg_loss' per strategy

        Returns:
            AllocationResult with Kelly-optimal weights
        """
        kelly_fractions = {}

        for name, metrics in strategy_metrics.items():
            win_rate = metrics.get('win_rate', 0.5)
            avg_win = metrics.get('avg_win', 1.0)
            avg_loss = metrics.get('avg_loss', 1.0)

            # Kelly formula: f = (p * b - q) / b
            # where p = win rate, q = 1-p, b = avg_win / avg_loss
            if avg_loss > 0:
                b = avg_win / avg_loss
                kelly = (win_rate * b - (1 - win_rate)) / b

                # Use fractional Kelly (25% of full Kelly for safety)
                kelly_fractions[name] = max(0, kelly * 0.25)
            else:
                kelly_fractions[name] = 0.0

        # Normalize to sum to 1.0
        total_kelly = sum(kelly_fractions.values())

        if total_kelly <= 0:
            logger.warning("All Kelly fractions <= 0, falling back to equal weight")
            return self.equal_weight(list(strategy_metrics.keys()))

        weights = {name: k / total_kelly for name, k in kelly_fractions.items()}

        # Apply constraints
        weights = self._apply_constraints(weights)

        logger.info("Kelly optimal allocation calculated")

        return AllocationResult(
            weights=weights,
            method="kelly_optimal",
            expected_return=sum(weights[name] * strategy_metrics[name].get('return', 0.0)
                               for name in weights.keys()),
            expected_sharpe=0.0,
            expected_volatility=0.0,
            diversification_ratio=self._calculate_diversification(weights)
        )

    def minimum_variance(
        self,
        returns_data: pd.DataFrame
    ) -> AllocationResult:
        """
        Minimum variance portfolio optimization

        Args:
            returns_data: DataFrame with strategy returns

        Returns:
            AllocationResult with minimum variance weights
        """
        # Calculate covariance matrix
        cov_matrix = returns_data.cov()
        n = len(returns_data.columns)

        # Objective: minimize portfolio variance
        def portfolio_variance(weights):
            return weights.T @ cov_matrix @ weights

        # Constraints: weights sum to 1
        constraints = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}
        ]

        # Bounds: min/max allocation per strategy
        bounds = [(self.min_allocation, self.max_allocation) for _ in range(n)]

        # Initial guess: equal weight
        initial = np.array([1.0 / n] * n)

        # Optimize
        result = minimize(
            portfolio_variance,
            initial,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints
        )

        if not result.success:
            logger.warning("Minimum variance optimization failed, using equal weight")
            return self.equal_weight(list(returns_data.columns))

        # Create weights dict
        weights = {name: w for name, w in zip(returns_data.columns, result.x)}

        portfolio_vol = np.sqrt(result.fun)

        logger.info(f"Minimum variance allocation: Portfolio Vol={portfolio_vol:.2%}")

        return AllocationResult(
            weights=weights,
            method="minimum_variance",
            expected_return=0.0,
            expected_sharpe=0.0,
            expected_volatility=portfolio_vol,
            diversification_ratio=self._calculate_diversification(weights)
        )

    def maximum_sharpe(
        self,
        returns_data: pd.DataFrame,
        risk_free_rate: float = 0.0
    ) -> AllocationResult:
        """
        Maximum Sharpe ratio portfolio optimization

        Args:
            returns_data: DataFrame with strategy returns
            risk_free_rate: Risk-free rate (annual)

        Returns:
            AllocationResult with maximum Sharpe weights
        """
        # Calculate mean returns and covariance
        mean_returns = returns_data.mean()
        cov_matrix = returns_data.cov()
        n = len(returns_data.columns)

        # Objective: maximize Sharpe ratio (minimize negative Sharpe)
        def negative_sharpe(weights):
            portfolio_return = weights @ mean_returns
            portfolio_vol = np.sqrt(weights.T @ cov_matrix @ weights)

            if portfolio_vol == 0:
                return 1e10  # Large penalty

            sharpe = (portfolio_return - risk_free_rate) / portfolio_vol
            return -sharpe  # Minimize negative Sharpe

        # Constraints
        constraints = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}
        ]

        # Bounds
        bounds = [(self.min_allocation, self.max_allocation) for _ in range(n)]

        # Initial guess
        initial = np.array([1.0 / n] * n)

        # Optimize
        result = minimize(
            negative_sharpe,
            initial,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints
        )

        if not result.success:
            logger.warning("Maximum Sharpe optimization failed, using equal weight")
            return self.equal_weight(list(returns_data.columns))

        # Create weights dict
        weights = {name: w for name, w in zip(returns_data.columns, result.x)}

        # Calculate portfolio metrics
        portfolio_return = result.x @ mean_returns
        portfolio_vol = np.sqrt(result.x.T @ cov_matrix @ result.x)
        portfolio_sharpe = (portfolio_return - risk_free_rate) / portfolio_vol if portfolio_vol > 0 else 0

        logger.info(f"Maximum Sharpe allocation: Sharpe={portfolio_sharpe:.2f}, Return={portfolio_return:.2%}")

        return AllocationResult(
            weights=weights,
            method="maximum_sharpe",
            expected_return=portfolio_return,
            expected_sharpe=portfolio_sharpe,
            expected_volatility=portfolio_vol,
            diversification_ratio=self._calculate_diversification(weights)
        )

    def _optimize_risk_parity(self, cov_matrix: pd.DataFrame) -> Dict[str, float]:
        """
        Optimize for risk parity allocation

        Args:
            cov_matrix: Covariance matrix

        Returns:
            Dictionary of weights
        """
        n = len(cov_matrix)

        # Objective: minimize difference in risk contributions
        def risk_parity_objective(weights):
            portfolio_vol = np.sqrt(weights.T @ cov_matrix @ weights)

            # Marginal risk contributions
            marginal_contrib = cov_matrix @ weights / portfolio_vol

            # Risk contributions
            risk_contrib = weights * marginal_contrib

            # Target: equal risk from each strategy
            target_risk = portfolio_vol / n

            # Sum of squared differences from target
            return np.sum((risk_contrib - target_risk) ** 2)

        # Constraints
        constraints = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}
        ]

        # Bounds
        bounds = [(self.min_allocation, self.max_allocation) for _ in range(n)]

        # Initial guess
        initial = np.array([1.0 / n] * n)

        # Optimize
        result = minimize(
            risk_parity_objective,
            initial,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints
        )

        if not result.success:
            # Fallback to equal weight
            return {name: 1.0 / n for name in cov_matrix.columns}

        return {name: w for name, w in zip(cov_matrix.columns, result.x)}

    def _apply_constraints(self, weights: Dict[str, float]) -> Dict[str, float]:
        """
        Apply min/max constraints and normalize iteratively

        Args:
            weights: Dictionary of weights

        Returns:
            Constrained and normalized weights
        """
        if not weights:
            return weights

        # Iterative constraint enforcement
        constrained = dict(weights)
        max_iterations = 10

        for iteration in range(max_iterations):
            # Clamp to min/max
            for name in constrained.keys():
                constrained[name] = max(self.min_allocation,
                                       min(self.max_allocation, constrained[name]))

            # Check if normalization needed
            total = sum(constrained.values())

            if abs(total - 1.0) < 0.0001:
                # Already normalized
                break

            # Normalize
            for name in constrained.keys():
                constrained[name] = constrained[name] / total

            # Check if any weights exceed max after normalization
            violations = {name: w for name, w in constrained.items()
                         if w > self.max_allocation + 0.0001}

            if not violations:
                # No violations, we're done
                break

            # Fix violations: cap at max and redistribute excess
            excess = 0.0
            for name in violations.keys():
                excess += constrained[name] - self.max_allocation
                constrained[name] = self.max_allocation

            # Distribute excess to non-maxed strategies
            non_maxed = [name for name, w in constrained.items()
                        if w < self.max_allocation - 0.0001]

            if non_maxed:
                # Distribute proportionally among non-maxed strategies
                for name in non_maxed:
                    constrained[name] += excess / len(non_maxed)
            else:
                # All strategies at max - force equal weight
                n = len(constrained)
                constrained = {name: 1.0 / n for name in constrained.keys()}
                break

        # Final normalization to ensure sum = 1.0
        total = sum(constrained.values())
        if total > 0:
            constrained = {name: w / total for name, w in constrained.items()}

        return constrained

    def _calculate_diversification(self, weights: Dict[str, float]) -> float:
        """
        Calculate diversification ratio

        Diversification ratio measures concentration:
        - 1.0 = perfectly concentrated (one strategy)
        - N = perfectly diversified (equal weight across N strategies)

        Args:
            weights: Dictionary of weights

        Returns:
            Diversification ratio
        """
        # Herfindahl index: sum of squared weights
        herfindahl = sum(w ** 2 for w in weights.values())

        # Diversification ratio: 1 / Herfindahl
        # Higher is better (more diversified)
        return 1.0 / herfindahl if herfindahl > 0 else 0.0

    def compare_allocations(
        self,
        strategy_metrics: Dict[str, Dict],
        returns_data: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Compare different allocation methods

        Args:
            strategy_metrics: Strategy performance metrics
            returns_data: Optional returns data for advanced methods

        Returns:
            DataFrame comparing allocation methods
        """
        results = []

        # Equal weight
        equal = self.equal_weight(list(strategy_metrics.keys()))
        results.append(equal)

        # Sharpe weighted
        sharpe = self.sharpe_weighted(strategy_metrics)
        results.append(sharpe)

        # Risk parity
        risk_par = self.risk_parity(strategy_metrics, returns_data)
        results.append(risk_par)

        # Kelly optimal
        kelly = self.kelly_optimal(strategy_metrics)
        results.append(kelly)

        # If returns data available, add advanced methods
        if returns_data is not None:
            min_var = self.minimum_variance(returns_data)
            results.append(min_var)

            max_sharpe = self.maximum_sharpe(returns_data)
            results.append(max_sharpe)

        # Build comparison DataFrame
        comparison_data = []
        for result in results:
            comparison_data.append({
                'Method': result.method,
                'Expected Return': f"{result.expected_return:.2%}",
                'Expected Sharpe': f"{result.expected_sharpe:.2f}",
                'Expected Vol': f"{result.expected_volatility:.2%}",
                'Diversification': f"{result.diversification_ratio:.2f}",
                **{f"{name}_weight": f"{w:.1%}" for name, w in result.weights.items()}
            })

        df = pd.DataFrame(comparison_data)

        logger.info(f"\\nAllocation Comparison:\\n{df.to_string()}")

        return df
