"""
Portfolio Diversification Calculator
Purpose: Advanced diversification metrics and risk contribution analysis

Phase 3.1: Portfolio Correlation Analysis for Enhanced Risk Management
Created: 2025-12-11
Updated: 2025-12-11

This module provides:
1. Herfindahl-Hirschman Index (HHI) calculation
2. Effective Number of Positions (ENB)
3. Risk Contribution Analysis (marginal and total)
4. Optimal portfolio weights suggestion
5. Risk parity allocation
6. Concentration warnings and recommendations

Key Metrics:
- HHI: Measure of concentration (0 = perfect diversification, 1 = single position)
- ENB: Effective number of bets (inverse HHI)
- Risk Contribution: How much each position contributes to total portfolio risk
- Marginal Risk Contribution: Risk added by each additional dollar

Research Foundation:
- Modern Portfolio Theory (Markowitz, 1952)
- Risk Parity (Qian, 2005)
- Equal Risk Contribution (Maillard, 2010)

Usage:
    calculator = get_diversification_calculator()

    # Calculate diversification metrics
    metrics = calculator.calculate_metrics(positions, correlation_matrix)

    # Get position concentration warnings
    warnings = calculator.get_concentration_warnings(positions, portfolio_value)

    # Get risk parity weights
    weights = calculator.calculate_risk_parity_weights(positions, volatilities)

    # Get optimal weights based on mean-variance
    optimal = calculator.calculate_optimal_weights(returns, covariance_matrix)
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import numpy as np
from scipy.optimize import minimize

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class DiversificationConfig:
    """
    Configuration for diversification calculations

    Research-based defaults:
    - HHI threshold for concentration: 0.25 (4 effective positions)
    - Min positions for adequate diversification: 5
    - Max single position weight: 30%
    - Risk parity tolerance: 1% deviation
    """
    # Concentration thresholds
    hhi_excellent_threshold: float = 0.10      # HHI < 0.10 = excellent (>10 effective positions)
    hhi_good_threshold: float = 0.18           # HHI < 0.18 = good (~5.5 effective positions)
    hhi_moderate_threshold: float = 0.25       # HHI < 0.25 = moderate (~4 effective positions)
    hhi_poor_threshold: float = 0.40           # HHI < 0.40 = poor (~2.5 effective positions)
    # HHI >= 0.40 = concentrated

    # Position count thresholds
    min_positions_excellent: int = 8           # Excellent: 8+ positions
    min_positions_good: int = 5                # Good: 5-7 positions
    min_positions_moderate: int = 3            # Moderate: 3-4 positions
    # Poor: 1-2 positions

    # Weight limits
    max_single_position_pct: float = 30.0      # No position > 30%
    warning_single_position_pct: float = 20.0  # Warning if position > 20%
    min_position_pct: float = 2.0              # Minimum meaningful position

    # Risk contribution thresholds
    max_risk_contribution_pct: float = 40.0    # No position > 40% of total risk
    warning_risk_contribution_pct: float = 25.0  # Warning if > 25% risk contribution

    # Risk parity settings
    risk_parity_tolerance: float = 0.01        # 1% tolerance in risk parity
    max_iterations: int = 1000                 # Optimization iterations

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary"""
        return asdict(self)


# =============================================================================
# DATA MODELS
# =============================================================================

class ConcentrationLevel(Enum):
    """Portfolio concentration level classification"""
    EXCELLENT = "excellent"      # Well diversified, low concentration
    GOOD = "good"                # Adequately diversified
    MODERATE = "moderate"        # Some concentration
    POOR = "poor"                # High concentration
    CONCENTRATED = "concentrated"  # Very high concentration risk


@dataclass
class PositionData:
    """
    Position data for diversification calculations

    Lightweight representation focusing on risk-relevant metrics.
    """
    symbol: str                  # Trading symbol
    weight: float               # Weight as decimal (0.0 to 1.0)
    position_value: float       # USD value
    volatility: float = 0.20    # Annualized volatility (default 20%)
    beta: float = 1.0           # Beta to market
    expected_return: float = 0.0  # Expected return (for optimization)


@dataclass
class RiskContribution:
    """
    Risk contribution metrics for a single position

    Shows how much each position contributes to total portfolio risk.
    """
    symbol: str
    weight: float               # Position weight
    volatility: float           # Position volatility
    marginal_risk_contribution: float  # dPortfolioRisk / dWeight
    total_risk_contribution: float     # weight * marginal_risk_contribution
    risk_contribution_pct: float       # As percentage of total portfolio risk
    is_over_threshold: bool     # Exceeds max risk contribution

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "symbol": self.symbol,
            "weight": round(self.weight, 4),
            "volatility": round(self.volatility, 4),
            "marginal_risk_contribution": round(self.marginal_risk_contribution, 6),
            "total_risk_contribution": round(self.total_risk_contribution, 6),
            "risk_contribution_pct": round(self.risk_contribution_pct, 2),
            "is_over_threshold": self.is_over_threshold,
        }


@dataclass
class ConcentrationWarning:
    """
    Warning about portfolio concentration

    Actionable alert about concentration issues.
    """
    warning_type: str           # "SINGLE_POSITION", "HHI", "RISK_CONTRIBUTION", etc.
    severity: str               # "INFO", "WARNING", "CRITICAL"
    message: str                # Human-readable message
    symbol: Optional[str] = None  # Related symbol if applicable
    current_value: float = 0.0  # Current metric value
    threshold_value: float = 0.0  # Threshold that triggered warning
    recommendation: str = ""    # Actionable recommendation

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "warning_type": self.warning_type,
            "severity": self.severity,
            "message": self.message,
            "symbol": self.symbol,
            "current_value": round(self.current_value, 4),
            "threshold_value": round(self.threshold_value, 4),
            "recommendation": self.recommendation,
        }


@dataclass
class OptimalWeights:
    """
    Optimal portfolio weights from optimization

    Result of mean-variance or risk parity optimization.
    """
    method: str                 # "risk_parity", "mean_variance", "equal_weight"
    weights: Dict[str, float]   # Symbol -> weight mapping
    portfolio_volatility: float  # Expected portfolio volatility
    portfolio_return: float = 0.0  # Expected return (for mean-variance)
    sharpe_ratio: float = 0.0   # Sharpe ratio (if returns provided)
    convergence_achieved: bool = True
    iterations: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "method": self.method,
            "weights": {k: round(v, 4) for k, v in self.weights.items()},
            "portfolio_volatility": round(self.portfolio_volatility, 4),
            "portfolio_return": round(self.portfolio_return, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "convergence_achieved": self.convergence_achieved,
            "iterations": self.iterations,
        }


@dataclass
class DiversificationMetrics:
    """
    Complete diversification metrics result

    Comprehensive analysis of portfolio diversification quality.
    """
    # Basic metrics
    position_count: int
    total_portfolio_value: float

    # Concentration metrics
    hhi: float                  # Herfindahl-Hirschman Index (0-1)
    effective_positions: float  # Effective Number of Bets (1/HHI)
    concentration_level: ConcentrationLevel

    # Weight analysis
    max_weight: float           # Largest position weight
    min_weight: float           # Smallest position weight
    avg_weight: float           # Average position weight
    weight_std: float           # Standard deviation of weights

    # Risk analysis
    portfolio_volatility: float  # Total portfolio volatility
    risk_contributions: List[RiskContribution]
    max_risk_contribution_pct: float

    # Warnings
    warnings: List[ConcentrationWarning]

    # Recommendations
    recommendations: List[str]

    # Timestamp
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "position_count": self.position_count,
            "total_portfolio_value": round(self.total_portfolio_value, 2),
            "hhi": round(self.hhi, 4),
            "effective_positions": round(self.effective_positions, 2),
            "concentration_level": self.concentration_level.value,
            "max_weight": round(self.max_weight, 4),
            "min_weight": round(self.min_weight, 4),
            "avg_weight": round(self.avg_weight, 4),
            "weight_std": round(self.weight_std, 4),
            "portfolio_volatility": round(self.portfolio_volatility, 4),
            "risk_contributions": [rc.to_dict() for rc in self.risk_contributions],
            "max_risk_contribution_pct": round(self.max_risk_contribution_pct, 2),
            "warnings": [w.to_dict() for w in self.warnings],
            "recommendations": self.recommendations,
            "timestamp": self.timestamp.isoformat(),
        }


# =============================================================================
# DIVERSIFICATION CALCULATOR
# =============================================================================

class DiversificationCalculator:
    """
    Portfolio Diversification Calculator

    Provides advanced diversification metrics and optimization for
    portfolio risk management.

    Key Features:
    - Herfindahl-Hirschman Index (HHI) calculation
    - Effective Number of Positions (ENB)
    - Risk contribution analysis
    - Risk parity weight optimization
    - Mean-variance optimization
    - Concentration warnings

    Usage:
        calculator = DiversificationCalculator()

        # Calculate full metrics
        metrics = calculator.calculate_metrics(positions, covariance_matrix)

        # Get just HHI
        hhi = calculator.calculate_hhi(weights)

        # Get risk parity weights
        weights = calculator.calculate_risk_parity_weights(positions, covariance_matrix)
    """

    def __init__(self, config: Optional[DiversificationConfig] = None):
        """
        Initialize Diversification Calculator

        Args:
            config: Configuration (uses defaults if not provided)
        """
        self.config = config or DiversificationConfig()

        logger.info(
            f"DiversificationCalculator initialized: "
            f"max_single_position={self.config.max_single_position_pct}%, "
            f"hhi_good_threshold={self.config.hhi_good_threshold}"
        )

    # =========================================================================
    # CORE METRICS
    # =========================================================================

    def calculate_hhi(self, weights: List[float]) -> float:
        """
        Calculate Herfindahl-Hirschman Index (HHI)

        HHI = sum of squared weights
        Range: 1/n (perfect diversification) to 1 (single position)

        Args:
            weights: List of position weights (should sum to 1.0)

        Returns:
            HHI value between 0 and 1
        """
        if not weights or len(weights) == 0:
            return 1.0  # Maximum concentration (no positions)

        # Normalize weights if they don't sum to 1
        weight_sum = sum(weights)
        if weight_sum == 0:
            return 1.0

        normalized = [w / weight_sum for w in weights]

        # Calculate HHI (sum of squared weights)
        hhi = sum(w ** 2 for w in normalized)

        return float(hhi)

    def calculate_effective_positions(self, hhi: float) -> float:
        """
        Calculate Effective Number of Bets (ENB)

        ENB = 1 / HHI
        Represents the number of equal-weight positions that would produce the same HHI.

        Args:
            hhi: Herfindahl-Hirschman Index

        Returns:
            Effective number of positions
        """
        if hhi <= 0:
            return float('inf')

        return 1.0 / hhi

    def get_concentration_level(
        self,
        hhi: float,
        position_count: int
    ) -> ConcentrationLevel:
        """
        Determine concentration level from HHI and position count

        Args:
            hhi: Herfindahl-Hirschman Index
            position_count: Number of positions

        Returns:
            ConcentrationLevel enum
        """
        # First check position count
        if position_count <= 1:
            return ConcentrationLevel.CONCENTRATED

        # Then check HHI
        if hhi < self.config.hhi_excellent_threshold:
            return ConcentrationLevel.EXCELLENT
        elif hhi < self.config.hhi_good_threshold:
            return ConcentrationLevel.GOOD
        elif hhi < self.config.hhi_moderate_threshold:
            return ConcentrationLevel.MODERATE
        elif hhi < self.config.hhi_poor_threshold:
            return ConcentrationLevel.POOR
        else:
            return ConcentrationLevel.CONCENTRATED

    # =========================================================================
    # RISK CONTRIBUTION ANALYSIS
    # =========================================================================

    def calculate_portfolio_volatility(
        self,
        weights: np.ndarray,
        covariance_matrix: np.ndarray
    ) -> float:
        """
        Calculate portfolio volatility from weights and covariance matrix

        Vol = sqrt(w' * Sigma * w)

        Args:
            weights: Array of position weights
            covariance_matrix: Covariance matrix of returns

        Returns:
            Portfolio volatility (standard deviation)
        """
        portfolio_variance = weights @ covariance_matrix @ weights
        return float(np.sqrt(portfolio_variance))

    def calculate_marginal_risk_contributions(
        self,
        weights: np.ndarray,
        covariance_matrix: np.ndarray
    ) -> np.ndarray:
        """
        Calculate marginal risk contribution for each position

        MRC_i = (Sigma * w)_i / portfolio_vol

        Args:
            weights: Array of position weights
            covariance_matrix: Covariance matrix

        Returns:
            Array of marginal risk contributions
        """
        portfolio_vol = self.calculate_portfolio_volatility(weights, covariance_matrix)

        if portfolio_vol == 0:
            return np.zeros_like(weights)

        # Marginal risk contribution = covariance with portfolio / portfolio vol
        marginal = (covariance_matrix @ weights) / portfolio_vol

        return marginal

    def calculate_total_risk_contributions(
        self,
        weights: np.ndarray,
        covariance_matrix: np.ndarray
    ) -> np.ndarray:
        """
        Calculate total risk contribution for each position

        TRC_i = w_i * MRC_i

        Args:
            weights: Array of position weights
            covariance_matrix: Covariance matrix

        Returns:
            Array of total risk contributions
        """
        marginal = self.calculate_marginal_risk_contributions(weights, covariance_matrix)
        return weights * marginal

    def calculate_risk_contributions(
        self,
        positions: List[PositionData],
        covariance_matrix: Optional[np.ndarray] = None
    ) -> List[RiskContribution]:
        """
        Calculate detailed risk contributions for all positions

        Args:
            positions: List of PositionData objects
            covariance_matrix: Optional covariance matrix (estimated from volatilities if not provided)

        Returns:
            List of RiskContribution objects
        """
        if not positions:
            return []

        n = len(positions)
        weights = np.array([p.weight for p in positions])

        # Build covariance matrix if not provided
        if covariance_matrix is None:
            # Estimate from volatilities assuming correlation of 0.5
            vols = np.array([p.volatility for p in positions])
            default_correlation = 0.5

            covariance_matrix = np.zeros((n, n))
            for i in range(n):
                for j in range(n):
                    if i == j:
                        covariance_matrix[i, j] = vols[i] ** 2
                    else:
                        covariance_matrix[i, j] = default_correlation * vols[i] * vols[j]

        # Calculate contributions
        marginal = self.calculate_marginal_risk_contributions(weights, covariance_matrix)
        total = self.calculate_total_risk_contributions(weights, covariance_matrix)

        # Convert to percentages
        total_risk = np.sum(total)
        if total_risk == 0:
            total_risk = 1.0  # Avoid division by zero

        contributions = []
        for i, pos in enumerate(positions):
            contribution_pct = (total[i] / total_risk) * 100

            rc = RiskContribution(
                symbol=pos.symbol,
                weight=pos.weight,
                volatility=pos.volatility,
                marginal_risk_contribution=float(marginal[i]),
                total_risk_contribution=float(total[i]),
                risk_contribution_pct=float(contribution_pct),
                is_over_threshold=contribution_pct > self.config.max_risk_contribution_pct,
            )
            contributions.append(rc)

        # Sort by risk contribution (highest first)
        contributions.sort(key=lambda x: x.risk_contribution_pct, reverse=True)

        return contributions

    # =========================================================================
    # COMPLETE METRICS CALCULATION
    # =========================================================================

    def calculate_metrics(
        self,
        positions: List[PositionData],
        covariance_matrix: Optional[np.ndarray] = None
    ) -> DiversificationMetrics:
        """
        Calculate complete diversification metrics

        Args:
            positions: List of PositionData objects
            covariance_matrix: Optional covariance matrix

        Returns:
            DiversificationMetrics with full analysis
        """
        if not positions:
            return DiversificationMetrics(
                position_count=0,
                total_portfolio_value=0.0,
                hhi=1.0,
                effective_positions=1.0,
                concentration_level=ConcentrationLevel.CONCENTRATED,
                max_weight=0.0,
                min_weight=0.0,
                avg_weight=0.0,
                weight_std=0.0,
                portfolio_volatility=0.0,
                risk_contributions=[],
                max_risk_contribution_pct=0.0,
                warnings=[],
                recommendations=["No positions to analyze"],
            )

        n = len(positions)
        weights = [p.weight for p in positions]
        values = [p.position_value for p in positions]
        total_value = sum(values)

        # Calculate HHI and effective positions
        hhi = self.calculate_hhi(weights)
        effective_positions = self.calculate_effective_positions(hhi)
        concentration_level = self.get_concentration_level(hhi, n)

        # Weight statistics
        weight_array = np.array(weights)
        max_weight = float(np.max(weight_array))
        min_weight = float(np.min(weight_array))
        avg_weight = float(np.mean(weight_array))
        weight_std = float(np.std(weight_array))

        # Risk contributions
        risk_contributions = self.calculate_risk_contributions(positions, covariance_matrix)
        max_risk_contribution = max(
            (rc.risk_contribution_pct for rc in risk_contributions),
            default=0.0
        )

        # Portfolio volatility
        if covariance_matrix is not None:
            portfolio_vol = self.calculate_portfolio_volatility(
                weight_array,
                covariance_matrix
            )
        else:
            # Estimate from average volatility
            avg_vol = np.mean([p.volatility for p in positions])
            portfolio_vol = avg_vol * np.sqrt(hhi)  # Adjusted for concentration

        # Generate warnings
        warnings = self._generate_warnings(
            positions,
            weights,
            hhi,
            effective_positions,
            risk_contributions,
            total_value,
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            positions,
            hhi,
            concentration_level,
            risk_contributions,
            warnings,
        )

        return DiversificationMetrics(
            position_count=n,
            total_portfolio_value=total_value,
            hhi=hhi,
            effective_positions=effective_positions,
            concentration_level=concentration_level,
            max_weight=max_weight,
            min_weight=min_weight,
            avg_weight=avg_weight,
            weight_std=weight_std,
            portfolio_volatility=portfolio_vol,
            risk_contributions=risk_contributions,
            max_risk_contribution_pct=max_risk_contribution,
            warnings=warnings,
            recommendations=recommendations,
        )

    # =========================================================================
    # WARNINGS GENERATION
    # =========================================================================

    def _generate_warnings(
        self,
        positions: List[PositionData],
        weights: List[float],
        hhi: float,
        effective_positions: float,
        risk_contributions: List[RiskContribution],
        total_value: float,
    ) -> List[ConcentrationWarning]:
        """Generate concentration warnings based on metrics"""
        warnings = []

        # Check single position weights
        for pos, weight in zip(positions, weights):
            weight_pct = weight * 100

            if weight_pct > self.config.max_single_position_pct:
                warnings.append(ConcentrationWarning(
                    warning_type="SINGLE_POSITION_CRITICAL",
                    severity="CRITICAL",
                    message=f"{pos.symbol} has {weight_pct:.1f}% allocation, exceeding {self.config.max_single_position_pct}% limit",
                    symbol=pos.symbol,
                    current_value=weight_pct,
                    threshold_value=self.config.max_single_position_pct,
                    recommendation=f"Reduce {pos.symbol} position by {weight_pct - self.config.max_single_position_pct:.1f}%",
                ))
            elif weight_pct > self.config.warning_single_position_pct:
                warnings.append(ConcentrationWarning(
                    warning_type="SINGLE_POSITION_WARNING",
                    severity="WARNING",
                    message=f"{pos.symbol} has {weight_pct:.1f}% allocation, approaching {self.config.max_single_position_pct}% limit",
                    symbol=pos.symbol,
                    current_value=weight_pct,
                    threshold_value=self.config.warning_single_position_pct,
                    recommendation=f"Consider reducing {pos.symbol} exposure",
                ))

        # Check HHI
        if hhi > self.config.hhi_poor_threshold:
            warnings.append(ConcentrationWarning(
                warning_type="HHI_CRITICAL",
                severity="CRITICAL",
                message=f"Portfolio HHI of {hhi:.3f} indicates high concentration (effective positions: {effective_positions:.1f})",
                current_value=hhi,
                threshold_value=self.config.hhi_poor_threshold,
                recommendation="Add more positions to diversify portfolio",
            ))
        elif hhi > self.config.hhi_moderate_threshold:
            warnings.append(ConcentrationWarning(
                warning_type="HHI_WARNING",
                severity="WARNING",
                message=f"Portfolio HHI of {hhi:.3f} indicates moderate concentration (effective positions: {effective_positions:.1f})",
                current_value=hhi,
                threshold_value=self.config.hhi_moderate_threshold,
                recommendation="Consider adding 1-2 more positions",
            ))

        # Check risk contributions
        for rc in risk_contributions:
            if rc.risk_contribution_pct > self.config.max_risk_contribution_pct:
                warnings.append(ConcentrationWarning(
                    warning_type="RISK_CONTRIBUTION_CRITICAL",
                    severity="CRITICAL",
                    message=f"{rc.symbol} contributes {rc.risk_contribution_pct:.1f}% of portfolio risk, exceeding {self.config.max_risk_contribution_pct}% limit",
                    symbol=rc.symbol,
                    current_value=rc.risk_contribution_pct,
                    threshold_value=self.config.max_risk_contribution_pct,
                    recommendation=f"Reduce {rc.symbol} position or add uncorrelated positions",
                ))
            elif rc.risk_contribution_pct > self.config.warning_risk_contribution_pct:
                warnings.append(ConcentrationWarning(
                    warning_type="RISK_CONTRIBUTION_WARNING",
                    severity="WARNING",
                    message=f"{rc.symbol} contributes {rc.risk_contribution_pct:.1f}% of portfolio risk",
                    symbol=rc.symbol,
                    current_value=rc.risk_contribution_pct,
                    threshold_value=self.config.warning_risk_contribution_pct,
                    recommendation=f"Monitor {rc.symbol} risk contribution",
                ))

        # Check position count
        if len(positions) < self.config.min_positions_moderate:
            warnings.append(ConcentrationWarning(
                warning_type="LOW_POSITION_COUNT",
                severity="WARNING",
                message=f"Only {len(positions)} positions - consider adding more for diversification",
                current_value=float(len(positions)),
                threshold_value=float(self.config.min_positions_moderate),
                recommendation=f"Add at least {self.config.min_positions_moderate - len(positions)} more positions",
            ))

        # Sort warnings by severity
        severity_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
        warnings.sort(key=lambda w: severity_order.get(w.severity, 2))

        return warnings

    def _generate_recommendations(
        self,
        positions: List[PositionData],
        hhi: float,
        concentration_level: ConcentrationLevel,
        risk_contributions: List[RiskContribution],
        warnings: List[ConcentrationWarning],
    ) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []

        # Based on concentration level
        if concentration_level == ConcentrationLevel.CONCENTRATED:
            recommendations.append(
                "URGENT: Portfolio is highly concentrated. Add at least 3-4 more "
                "uncorrelated positions to reduce concentration risk."
            )
        elif concentration_level == ConcentrationLevel.POOR:
            recommendations.append(
                "Portfolio has poor diversification. Consider adding 2-3 more "
                "positions across different sectors."
            )
        elif concentration_level == ConcentrationLevel.MODERATE:
            recommendations.append(
                "Portfolio diversification is moderate. Adding 1-2 more positions "
                "would improve risk-adjusted returns."
            )
        elif concentration_level in [ConcentrationLevel.GOOD, ConcentrationLevel.EXCELLENT]:
            recommendations.append(
                "Portfolio is well-diversified. Maintain current allocation strategy."
            )

        # Position size recommendations
        weights = [p.weight for p in positions]
        max_weight = max(weights)
        if max_weight > 0.25:
            largest = positions[weights.index(max_weight)]
            recommendations.append(
                f"Consider reducing {largest.symbol} from {max_weight*100:.1f}% to below 25% "
                f"for better balance."
            )

        # Risk parity recommendation
        if risk_contributions:
            max_rc = max(risk_contributions, key=lambda x: x.risk_contribution_pct)
            min_rc = min(risk_contributions, key=lambda x: x.risk_contribution_pct)

            if max_rc.risk_contribution_pct > 2 * min_rc.risk_contribution_pct:
                recommendations.append(
                    f"Risk contribution is unequal: {max_rc.symbol} contributes "
                    f"{max_rc.risk_contribution_pct:.1f}% vs {min_rc.symbol} at "
                    f"{min_rc.risk_contribution_pct:.1f}%. Consider risk parity allocation."
                )

        # Warning-based recommendations
        critical_warnings = [w for w in warnings if w.severity == "CRITICAL"]
        if critical_warnings:
            recommendations.insert(0,
                f"ADDRESS CRITICAL ISSUES: {len(critical_warnings)} critical concentration "
                f"issues require immediate attention."
            )

        return recommendations

    # =========================================================================
    # PORTFOLIO OPTIMIZATION
    # =========================================================================

    def calculate_equal_weight(
        self,
        positions: List[PositionData]
    ) -> OptimalWeights:
        """
        Calculate equal weight allocation

        Args:
            positions: List of positions

        Returns:
            OptimalWeights with equal weights
        """
        if not positions:
            return OptimalWeights(
                method="equal_weight",
                weights={},
                portfolio_volatility=0.0,
            )

        n = len(positions)
        equal_weight = 1.0 / n

        weights = {pos.symbol: equal_weight for pos in positions}

        # Estimate portfolio volatility
        avg_vol = np.mean([p.volatility for p in positions])
        portfolio_vol = avg_vol * np.sqrt(1.0 / n)  # Simplified estimate

        return OptimalWeights(
            method="equal_weight",
            weights=weights,
            portfolio_volatility=portfolio_vol,
        )

    def calculate_risk_parity_weights(
        self,
        positions: List[PositionData],
        covariance_matrix: Optional[np.ndarray] = None
    ) -> OptimalWeights:
        """
        Calculate risk parity weights

        Risk parity allocates such that each position contributes equally to total risk.

        Args:
            positions: List of positions
            covariance_matrix: Optional covariance matrix

        Returns:
            OptimalWeights with risk parity allocation
        """
        if not positions:
            return OptimalWeights(
                method="risk_parity",
                weights={},
                portfolio_volatility=0.0,
            )

        n = len(positions)
        vols = np.array([p.volatility for p in positions])

        # Build covariance matrix if not provided
        if covariance_matrix is None:
            default_correlation = 0.5
            covariance_matrix = np.zeros((n, n))
            for i in range(n):
                for j in range(n):
                    if i == j:
                        covariance_matrix[i, j] = vols[i] ** 2
                    else:
                        covariance_matrix[i, j] = default_correlation * vols[i] * vols[j]

        # Risk parity objective: minimize variance of risk contributions
        def risk_parity_objective(weights):
            weights = np.array(weights)
            portfolio_vol = self.calculate_portfolio_volatility(weights, covariance_matrix)

            if portfolio_vol == 0:
                return 0

            # Calculate risk contributions
            marginal = (covariance_matrix @ weights) / portfolio_vol
            total_rc = weights * marginal
            target_rc = portfolio_vol / n  # Equal risk contribution

            # Minimize squared deviations from target
            return np.sum((total_rc - target_rc) ** 2)

        # Initial guess: inverse volatility weighted
        initial_weights = (1 / vols) / np.sum(1 / vols)

        # Constraints: weights sum to 1, all non-negative
        constraints = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}
        ]
        bounds = [(0.01, 1.0)] * n  # Minimum 1% per position

        # Optimize
        result = minimize(
            risk_parity_objective,
            initial_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints,
            options={'maxiter': self.config.max_iterations}
        )

        if result.success:
            opt_weights = result.x
            portfolio_vol = self.calculate_portfolio_volatility(opt_weights, covariance_matrix)

            weights_dict = {
                pos.symbol: float(opt_weights[i])
                for i, pos in enumerate(positions)
            }

            return OptimalWeights(
                method="risk_parity",
                weights=weights_dict,
                portfolio_volatility=portfolio_vol,
                convergence_achieved=True,
                iterations=result.nit,
            )
        else:
            # Fall back to inverse volatility
            inv_vol_weights = (1 / vols) / np.sum(1 / vols)
            portfolio_vol = self.calculate_portfolio_volatility(inv_vol_weights, covariance_matrix)

            weights_dict = {
                pos.symbol: float(inv_vol_weights[i])
                for i, pos in enumerate(positions)
            }

            return OptimalWeights(
                method="risk_parity",
                weights=weights_dict,
                portfolio_volatility=portfolio_vol,
                convergence_achieved=False,
                iterations=self.config.max_iterations,
            )

    def calculate_mean_variance_weights(
        self,
        positions: List[PositionData],
        covariance_matrix: np.ndarray,
        target_return: Optional[float] = None,
        risk_free_rate: float = 0.04
    ) -> OptimalWeights:
        """
        Calculate mean-variance optimal weights (Markowitz optimization)

        If target_return is provided, minimizes variance for that return.
        Otherwise, maximizes Sharpe ratio.

        Args:
            positions: List of positions with expected returns
            covariance_matrix: Covariance matrix
            target_return: Optional target return (maximizes Sharpe if None)
            risk_free_rate: Risk-free rate for Sharpe calculation

        Returns:
            OptimalWeights with mean-variance optimal allocation
        """
        if not positions or covariance_matrix is None:
            return OptimalWeights(
                method="mean_variance",
                weights={},
                portfolio_volatility=0.0,
            )

        n = len(positions)
        expected_returns = np.array([p.expected_return for p in positions])

        if target_return is not None:
            # Minimize variance for target return
            def objective(weights):
                return self.calculate_portfolio_volatility(weights, covariance_matrix) ** 2

            constraints = [
                {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0},
                {'type': 'eq', 'fun': lambda w: np.dot(w, expected_returns) - target_return}
            ]
        else:
            # Maximize Sharpe ratio
            def objective(weights):
                weights = np.array(weights)
                portfolio_return = np.dot(weights, expected_returns)
                portfolio_vol = self.calculate_portfolio_volatility(weights, covariance_matrix)

                if portfolio_vol == 0:
                    return 0

                sharpe = (portfolio_return - risk_free_rate) / portfolio_vol
                return -sharpe  # Minimize negative Sharpe = maximize Sharpe

            constraints = [
                {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}
            ]

        # Initial guess: equal weight
        initial_weights = np.ones(n) / n

        # Bounds
        bounds = [(0.01, 0.5)] * n  # Min 1%, max 50% per position

        # Optimize
        result = minimize(
            objective,
            initial_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints,
            options={'maxiter': self.config.max_iterations}
        )

        if result.success:
            opt_weights = np.array(result.x)
            portfolio_vol = self.calculate_portfolio_volatility(opt_weights, covariance_matrix)
            portfolio_return = float(np.dot(opt_weights, expected_returns))
            sharpe = (portfolio_return - risk_free_rate) / portfolio_vol if portfolio_vol > 0 else 0

            weights_dict = {
                pos.symbol: float(opt_weights[i])
                for i, pos in enumerate(positions)
            }

            return OptimalWeights(
                method="mean_variance",
                weights=weights_dict,
                portfolio_volatility=portfolio_vol,
                portfolio_return=portfolio_return,
                sharpe_ratio=sharpe,
                convergence_achieved=True,
                iterations=result.nit,
            )
        else:
            # Return equal weight as fallback
            return self.calculate_equal_weight(positions)

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def get_concentration_warnings(
        self,
        positions: List[PositionData],
        portfolio_value: float
    ) -> List[ConcentrationWarning]:
        """
        Get only concentration warnings (quick check)

        Args:
            positions: List of positions
            portfolio_value: Total portfolio value

        Returns:
            List of warnings
        """
        if not positions:
            return []

        weights = [p.position_value / portfolio_value for p in positions]
        hhi = self.calculate_hhi(weights)
        effective_positions = self.calculate_effective_positions(hhi)
        risk_contributions = self.calculate_risk_contributions(positions)

        return self._generate_warnings(
            positions,
            weights,
            hhi,
            effective_positions,
            risk_contributions,
            portfolio_value,
        )

    def get_rebalancing_trades(
        self,
        current_positions: List[PositionData],
        target_weights: Dict[str, float],
        portfolio_value: float,
        min_trade_value: float = 100.0
    ) -> List[Dict[str, Any]]:
        """
        Calculate trades needed to rebalance to target weights

        Args:
            current_positions: Current positions
            target_weights: Target weight for each symbol
            portfolio_value: Total portfolio value
            min_trade_value: Minimum trade size to suggest

        Returns:
            List of trade suggestions
        """
        trades = []

        # Build current weights dict
        current_weights = {
            pos.symbol: pos.weight for pos in current_positions
        }

        # Calculate trades for each symbol
        all_symbols = set(current_weights.keys()) | set(target_weights.keys())

        for symbol in all_symbols:
            current = current_weights.get(symbol, 0.0)
            target = target_weights.get(symbol, 0.0)
            diff = target - current

            trade_value = diff * portfolio_value

            if abs(trade_value) < min_trade_value:
                continue  # Skip small trades

            trades.append({
                "symbol": symbol,
                "action": "BUY" if trade_value > 0 else "SELL",
                "current_weight": round(current, 4),
                "target_weight": round(target, 4),
                "weight_change": round(diff, 4),
                "trade_value": round(abs(trade_value), 2),
            })

        # Sort by trade value (largest first)
        trades.sort(key=lambda t: t["trade_value"], reverse=True)

        return trades

    def get_status(self) -> Dict[str, Any]:
        """Get calculator status"""
        return {
            "config": self.config.to_dict(),
            "thresholds": {
                "hhi_excellent": self.config.hhi_excellent_threshold,
                "hhi_good": self.config.hhi_good_threshold,
                "hhi_moderate": self.config.hhi_moderate_threshold,
                "max_single_position_pct": self.config.max_single_position_pct,
                "max_risk_contribution_pct": self.config.max_risk_contribution_pct,
            }
        }


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_diversification_calculator: Optional[DiversificationCalculator] = None


def get_diversification_calculator(
    config: Optional[DiversificationConfig] = None
) -> DiversificationCalculator:
    """
    Get or create the global DiversificationCalculator instance

    Args:
        config: Optional configuration (only used on first call)

    Returns:
        DiversificationCalculator singleton instance
    """
    global _diversification_calculator
    if _diversification_calculator is None:
        _diversification_calculator = DiversificationCalculator(config)
    return _diversification_calculator


def reset_diversification_calculator():
    """Reset the global DiversificationCalculator instance (for testing)"""
    global _diversification_calculator
    _diversification_calculator = None


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    def test_diversification_calculator():
        """Test the diversification calculator"""
        calculator = get_diversification_calculator()

        print("\n=== Testing Diversification Calculator ===")

        # Create test positions
        positions = [
            PositionData(symbol="BTCUSDT", weight=0.40, position_value=40000, volatility=0.60),
            PositionData(symbol="ETHUSDT", weight=0.30, position_value=30000, volatility=0.70),
            PositionData(symbol="SOLUSDT", weight=0.15, position_value=15000, volatility=0.80),
            PositionData(symbol="ARBUSDT", weight=0.10, position_value=10000, volatility=0.90),
            PositionData(symbol="UNIUSDT", weight=0.05, position_value=5000, volatility=0.85),
        ]

        print("\n=== Basic Metrics ===")
        weights = [p.weight for p in positions]
        hhi = calculator.calculate_hhi(weights)
        enb = calculator.calculate_effective_positions(hhi)

        print(f"  HHI: {hhi:.4f}")
        print(f"  Effective Positions: {enb:.2f}")
        print(f"  Concentration Level: {calculator.get_concentration_level(hhi, len(positions)).value}")

        print("\n=== Full Metrics Analysis ===")
        metrics = calculator.calculate_metrics(positions)

        print(f"  Position Count: {metrics.position_count}")
        print(f"  Total Value: ${metrics.total_portfolio_value:,.2f}")
        print(f"  HHI: {metrics.hhi:.4f}")
        print(f"  Effective Positions: {metrics.effective_positions:.2f}")
        print(f"  Concentration Level: {metrics.concentration_level.value}")
        print(f"  Max Weight: {metrics.max_weight*100:.1f}%")
        print(f"  Portfolio Volatility: {metrics.portfolio_volatility*100:.1f}%")

        print("\n=== Risk Contributions ===")
        for rc in metrics.risk_contributions:
            flag = " [HIGH]" if rc.is_over_threshold else ""
            print(
                f"  {rc.symbol}: {rc.risk_contribution_pct:.1f}% of risk "
                f"(weight: {rc.weight*100:.1f}%){flag}"
            )

        print("\n=== Warnings ===")
        for warning in metrics.warnings:
            print(f"  [{warning.severity}] {warning.message}")

        print("\n=== Recommendations ===")
        for rec in metrics.recommendations:
            print(f"  - {rec}")

        print("\n=== Risk Parity Weights ===")
        risk_parity = calculator.calculate_risk_parity_weights(positions)
        print(f"  Converged: {risk_parity.convergence_achieved}")
        print(f"  Portfolio Vol: {risk_parity.portfolio_volatility*100:.1f}%")
        for symbol, weight in risk_parity.weights.items():
            print(f"    {symbol}: {weight*100:.1f}%")

        print("\n=== Rebalancing Trades (to Risk Parity) ===")
        trades = calculator.get_rebalancing_trades(
            positions,
            risk_parity.weights,
            portfolio_value=100000
        )
        for trade in trades:
            print(
                f"  {trade['action']} ${trade['trade_value']:,.0f} of {trade['symbol']} "
                f"({trade['current_weight']*100:.1f}% -> {trade['target_weight']*100:.1f}%)"
            )

    test_diversification_calculator()
