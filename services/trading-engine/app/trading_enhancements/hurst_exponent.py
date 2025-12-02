"""
Hurst Exponent Calculator for Market Regime Detection
Research Source: Mandelbrot's Fractal Market Hypothesis (1997)
                Peters' Fractal Market Analysis (1994)

Purpose:
- Detect market regime (trending vs mean-reverting vs random walk)
- Guide strategy selection based on market characteristics
- Provide statistical foundation for adaptive trading

Hurst Exponent Interpretation:
- H > 0.55: Trending/momentum regime (persistence) -> Use trend-following strategies
- H ~ 0.50: Random walk (Brownian motion) -> Reduce trading, market is unpredictable
- H < 0.45: Mean-reverting regime (anti-persistence) -> Use mean reversion strategies

Method: R/S (Rescaled Range) Analysis
- Developed by Harold Edwin Hurst for Nile River flood analysis
- Adapted for financial time series by Mandelbrot
- Robust against non-Gaussian distributions common in financial data
"""

import logging
import numpy as np
from enum import Enum
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

# Configure module-level logger
logger = logging.getLogger(__name__)


class MarketRegimeType(Enum):
    """
    Market regime classification based on Hurst Exponent

    Each regime suggests different optimal trading strategies:
    - TRENDING: Market shows persistence, momentum strategies work well
    - RANDOM_WALK: Market is unpredictable, reducing exposure is advisable
    - MEAN_REVERTING: Market shows anti-persistence, reversion strategies work
    """
    TRENDING = "trending"           # H > 0.55: Strong trend persistence
    RANDOM_WALK = "random_walk"     # 0.45 <= H <= 0.55: No exploitable pattern
    MEAN_REVERTING = "mean_reverting"  # H < 0.45: Price tends to revert


class StrategyType(Enum):
    """
    Recommended strategy types based on market regime

    Maps directly to trading approaches that work best in each regime
    """
    TREND_FOLLOWING = "trend_following"   # Momentum, breakout strategies
    NEUTRAL = "neutral"                    # Reduce exposure, wait for clarity
    MEAN_REVERSION = "mean_reversion"     # RSI oversold/overbought, Bollinger bands


@dataclass
class HurstConfig:
    """
    Configuration for Hurst Exponent calculation

    Attributes:
        min_periods: Minimum data points required for valid calculation
                    (50 is minimum for statistical significance)
        lookback_periods: List of lookback periods for multi-scale analysis
                         Multiple periods provide more robust regime detection
        trending_threshold: Hurst value above which market is considered trending
                           0.55 provides buffer above random walk (0.5)
        mean_reversion_threshold: Hurst value below which market is mean-reverting
                                  0.45 provides buffer below random walk (0.5)
        confidence_level: Minimum confidence required for regime classification
                         Lower values allow more signals but less certainty
    """
    min_periods: int = 50                          # Minimum data points needed
    lookback_periods: List[int] = field(          # Periods for analysis
        default_factory=lambda: [20, 50, 100, 200]
    )
    trending_threshold: float = 0.55               # H > this = trending
    mean_reversion_threshold: float = 0.45         # H < this = mean reverting
    confidence_level: float = 0.7                  # Minimum confidence (0-1)

    def __post_init__(self):
        """Validate configuration parameters after initialization"""
        # Ensure min_periods is reasonable
        if self.min_periods < 20:
            logger.warning(
                f"min_periods={self.min_periods} is very low, "
                "recommend at least 20 for meaningful results"
            )

        # Validate thresholds make sense
        if self.trending_threshold <= self.mean_reversion_threshold:
            raise ValueError(
                f"trending_threshold ({self.trending_threshold}) must be > "
                f"mean_reversion_threshold ({self.mean_reversion_threshold})"
            )

        # Validate threshold bounds
        if not (0 < self.mean_reversion_threshold < 0.5):
            logger.warning(
                f"mean_reversion_threshold={self.mean_reversion_threshold} "
                "should typically be between 0 and 0.5"
            )

        if not (0.5 < self.trending_threshold < 1):
            logger.warning(
                f"trending_threshold={self.trending_threshold} "
                "should typically be between 0.5 and 1"
            )


@dataclass
class HurstResult:
    """
    Result of Hurst Exponent calculation

    Contains the calculated Hurst value, detected regime, confidence metrics,
    and strategy recommendations based on the analysis.

    Attributes:
        hurst_value: The calculated Hurst exponent (0-1 range)
        regime: Detected market regime type
        confidence: Confidence in the regime classification (0-1)
        recommended_strategy: Suggested strategy type for this regime
        period: Lookback period used for calculation
        sample_size: Number of data points used
        r_squared: R-squared of the log-log regression (goodness of fit)
        calculated_at: Timestamp of calculation
        multi_period_values: Hurst values for each lookback period (if multi-period)
    """
    hurst_value: float                              # Core Hurst exponent
    regime: MarketRegimeType                        # Detected regime
    confidence: float                               # Classification confidence
    recommended_strategy: StrategyType              # Strategy recommendation
    period: int                                     # Lookback period used
    sample_size: int                                # Data points analyzed
    r_squared: float                                # Regression fit quality
    calculated_at: datetime = field(               # Timestamp
        default_factory=datetime.now
    )
    multi_period_values: Optional[Dict[int, float]] = None  # Per-period results

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for serialization"""
        return {
            "hurst_value": round(self.hurst_value, 4),
            "regime": self.regime.value,
            "confidence": round(self.confidence, 4),
            "recommended_strategy": self.recommended_strategy.value,
            "period": self.period,
            "sample_size": self.sample_size,
            "r_squared": round(self.r_squared, 4),
            "calculated_at": self.calculated_at.isoformat(),
            "multi_period_values": {
                k: round(v, 4) for k, v in (self.multi_period_values or {}).items()
            }
        }


class HurstExponentCalculator:
    """
    Hurst Exponent Calculator for Market Regime Detection

    RESEARCH-BACKED IMPLEMENTATION:
    Uses R/S (Rescaled Range) Analysis to calculate the Hurst Exponent,
    which measures the long-term memory of a time series. This helps
    identify whether markets are trending, mean-reverting, or random.

    The R/S analysis works by:
    1. Dividing the series into subseries of varying lengths
    2. For each subseries, calculating the range (R) and standard deviation (S)
    3. Computing the rescaled range R/S for each length
    4. Fitting log(R/S) vs log(n) to estimate Hurst exponent

    Key advantages:
    - Works with non-Gaussian distributions (fat tails in crypto)
    - Robust to outliers common in crypto markets
    - Provides statistical confidence measure

    Usage:
        calculator = HurstExponentCalculator()

        # Single period calculation
        result = calculator.calculate_hurst(prices, period=100)
        print(f"Hurst: {result.hurst_value}, Regime: {result.regime}")

        # Multi-period analysis for more robust detection
        result = calculator.calculate_multi_period_hurst(prices)
        print(f"Averaged Hurst: {result.hurst_value}")

        # Get strategy recommendation
        strategy = calculator.get_strategy_recommendation(result.regime)
        print(f"Recommended: {strategy}")
    """

    def __init__(self, config: Optional[HurstConfig] = None):
        """
        Initialize Hurst Exponent Calculator

        Args:
            config: Configuration settings for calculation thresholds
                   and analysis parameters. Defaults to HurstConfig()
        """
        # Store configuration (use defaults if not provided)
        self.config = config or HurstConfig()

        # Log initialization with key parameters
        logger.info(
            f"HurstExponentCalculator initialized: "
            f"trending_threshold={self.config.trending_threshold}, "
            f"mean_reversion_threshold={self.config.mean_reversion_threshold}, "
            f"lookback_periods={self.config.lookback_periods}"
        )

    def calculate_hurst(
        self,
        prices: List[float],
        period: Optional[int] = None
    ) -> HurstResult:
        """
        Calculate Hurst Exponent using R/S Analysis

        The Hurst exponent H is estimated by fitting the relationship:
        E[R(n)/S(n)] = C * n^H

        Where:
        - R(n) is the range of cumulative deviations
        - S(n) is the standard deviation
        - n is the subseries length
        - C is a constant
        - H is the Hurst exponent

        Args:
            prices: List of price values (close prices typically)
            period: Optional specific lookback period. If None, uses
                   the largest period from config that fits the data.

        Returns:
            HurstResult containing the Hurst value, regime, and metadata

        Raises:
            ValueError: If insufficient data points for calculation
        """
        # Convert to numpy array for efficient calculations
        prices_array = np.array(prices, dtype=np.float64)

        # Determine effective period to use
        if period is not None:
            effective_period = min(period, len(prices_array))
        else:
            # Use largest period that fits the data
            effective_period = len(prices_array)

        # Validate we have enough data
        if effective_period < self.config.min_periods:
            raise ValueError(
                f"Insufficient data: need at least {self.config.min_periods} "
                f"points, got {effective_period}"
            )

        # Take the most recent 'effective_period' prices
        analysis_data = prices_array[-effective_period:]

        logger.debug(
            f"Calculating Hurst exponent for {len(analysis_data)} data points"
        )

        # Calculate Hurst using R/S analysis
        hurst_value, r_squared = self._rs_analysis(analysis_data)

        # Determine market regime based on Hurst value
        regime = self.get_regime(hurst_value)

        # Calculate confidence based on R-squared and Hurst distance from 0.5
        confidence = self._calculate_confidence(hurst_value, r_squared)

        # Get strategy recommendation
        recommended_strategy = self.get_strategy_recommendation(regime)

        # Create and return result
        result = HurstResult(
            hurst_value=hurst_value,
            regime=regime,
            confidence=confidence,
            recommended_strategy=recommended_strategy,
            period=effective_period,
            sample_size=len(analysis_data),
            r_squared=r_squared
        )

        logger.info(
            f"Hurst calculation complete: H={hurst_value:.4f}, "
            f"regime={regime.value}, confidence={confidence:.2f}"
        )

        return result

    def _rs_analysis(self, data: np.ndarray) -> Tuple[float, float]:
        """
        Perform R/S (Rescaled Range) Analysis

        This is the core algorithm for Hurst exponent estimation:
        1. Calculate log returns from price data
        2. For each subseries length n:
           a. Divide series into non-overlapping subseries of length n
           b. For each subseries:
              - Calculate mean-adjusted series (deviations from mean)
              - Compute cumulative sum of deviations
              - Calculate range R = max(cumsum) - min(cumsum)
              - Calculate standard deviation S
              - Compute rescaled range R/S
           c. Average R/S values for this length n
        3. Fit log(R/S) vs log(n) using linear regression
        4. Hurst exponent H = slope of the regression line

        Args:
            data: Numpy array of price data

        Returns:
            Tuple of (hurst_exponent, r_squared)
        """
        # Calculate log returns (more stationary than prices)
        # Use log returns: ln(P_t / P_{t-1})
        returns = np.diff(np.log(data))
        n = len(returns)

        # Determine range of subseries lengths to analyze
        # Use powers of 2 for efficiency, from 8 to n/4
        min_length = 8  # Minimum meaningful subseries length
        max_length = n // 4  # Maximum to ensure enough subseries

        if max_length < min_length:
            # Not enough data for proper R/S analysis
            # Fall back to simple variance ratio estimate
            logger.warning(
                f"Limited data ({n} returns), using simplified estimation"
            )
            return self._simplified_hurst_estimate(returns)

        # Generate subseries lengths (roughly logarithmically spaced)
        lengths = []
        length = min_length
        while length <= max_length:
            lengths.append(length)
            length = int(length * 1.5)  # Increase by factor of ~1.5

        # Ensure we have at least 4 points for regression
        if len(lengths) < 4:
            lengths = list(range(min_length, max_length + 1, max(1, (max_length - min_length) // 4)))

        # Calculate R/S for each length
        log_lengths = []
        log_rs_values = []

        for length in lengths:
            # Calculate number of complete subseries
            num_subseries = n // length

            if num_subseries < 1:
                continue

            # Calculate R/S for each subseries of this length
            rs_list = []

            for i in range(num_subseries):
                # Extract subseries
                start_idx = i * length
                end_idx = start_idx + length
                subseries = returns[start_idx:end_idx]

                # Calculate R/S for this subseries
                rs = self.calculate_rs_analysis(subseries)

                if rs is not None and rs > 0:
                    rs_list.append(rs)

            # Average R/S for this length
            if rs_list:
                avg_rs = np.mean(rs_list)
                log_lengths.append(np.log(length))
                log_rs_values.append(np.log(avg_rs))

        # Need at least 2 points for regression
        if len(log_lengths) < 2:
            logger.warning("Insufficient R/S data points, using fallback")
            return self._simplified_hurst_estimate(returns)

        # Fit linear regression: log(R/S) = H * log(n) + c
        # Using numpy polyfit for slope (Hurst exponent)
        log_lengths_array = np.array(log_lengths)
        log_rs_array = np.array(log_rs_values)

        # Linear regression using least squares
        coefficients = np.polyfit(log_lengths_array, log_rs_array, 1)
        hurst_value = coefficients[0]  # Slope is the Hurst exponent

        # Calculate R-squared for goodness of fit
        fitted_values = np.polyval(coefficients, log_lengths_array)
        ss_res = np.sum((log_rs_array - fitted_values) ** 2)
        ss_tot = np.sum((log_rs_array - np.mean(log_rs_array)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        # Clamp Hurst value to valid range [0, 1]
        hurst_value = max(0.0, min(1.0, hurst_value))
        r_squared = max(0.0, min(1.0, r_squared))

        logger.debug(
            f"R/S analysis: H={hurst_value:.4f}, R^2={r_squared:.4f}, "
            f"lengths={lengths}"
        )

        return hurst_value, r_squared

    def calculate_rs_analysis(self, series: np.ndarray) -> Optional[float]:
        """
        Calculate R/S (Rescaled Range) statistic for a single series

        The R/S statistic measures the range of cumulative deviations
        from the mean, scaled by the standard deviation:

        R/S = (max(Y) - min(Y)) / S

        Where:
        - Y_t = sum(X_i - X_mean) for i=1 to t (cumulative deviation)
        - S = standard deviation of X

        Args:
            series: Numpy array of values (typically returns)

        Returns:
            R/S value, or None if calculation fails
        """
        n = len(series)

        # Need minimum length for meaningful calculation
        if n < 4:
            return None

        # Calculate mean of the series
        mean_value = np.mean(series)

        # Calculate mean-adjusted series (deviations from mean)
        deviations = series - mean_value

        # Calculate cumulative sum of deviations
        cumulative_deviations = np.cumsum(deviations)

        # Calculate range R = max(cumsum) - min(cumsum)
        range_value = np.max(cumulative_deviations) - np.min(cumulative_deviations)

        # Calculate standard deviation S
        std_value = np.std(series, ddof=1)  # Sample std dev

        # Avoid division by zero
        if std_value < 1e-10:
            return None

        # Return rescaled range R/S
        rs_value = range_value / std_value

        return rs_value

    def _simplified_hurst_estimate(self, returns: np.ndarray) -> Tuple[float, float]:
        """
        Simplified Hurst estimation for limited data

        Uses variance ratio method as a fallback when there's not enough
        data for proper R/S analysis. Less accurate but better than nothing.

        The idea is that for a random walk, variance grows linearly with time,
        while for trending series it grows faster, and for mean-reverting slower.

        Args:
            returns: Array of log returns

        Returns:
            Tuple of (hurst_estimate, confidence)
        """
        n = len(returns)

        if n < 10:
            # Really minimal data, assume random walk
            return 0.5, 0.0

        # Calculate variance at different scales
        var_1 = np.var(returns)

        # Calculate variance of 2-period returns
        returns_2 = returns[::2] + returns[1::2] if n >= 4 else returns
        var_2 = np.var(returns_2) if len(returns_2) > 1 else var_1

        # For random walk: var_2 should be 2 * var_1
        # Hurst ~ 0.5 * log2(var_2 / var_1)
        if var_1 > 0:
            ratio = var_2 / (2 * var_1) if var_1 > 0 else 1.0
            hurst = 0.5 + 0.5 * np.log2(max(0.1, min(10, ratio)))
        else:
            hurst = 0.5

        # Clamp to valid range
        hurst = max(0.0, min(1.0, hurst))

        # Low confidence for simplified estimate
        confidence = 0.3

        logger.debug(f"Simplified Hurst estimate: H={hurst:.4f}")

        return hurst, confidence

    def _calculate_confidence(self, hurst: float, r_squared: float) -> float:
        """
        Calculate confidence in the regime classification

        Confidence is based on:
        1. R-squared of the regression (how well the data fits the model)
        2. Distance of Hurst from 0.5 (clearer signal further from random)

        Args:
            hurst: Calculated Hurst exponent
            r_squared: R-squared from regression

        Returns:
            Confidence value between 0 and 1
        """
        # Distance from random walk (0.5)
        # Maximum useful distance is about 0.3 (H=0.2 or H=0.8)
        distance_from_random = abs(hurst - 0.5)
        distance_factor = min(1.0, distance_from_random / 0.3)

        # Combine R-squared and distance factor
        # Weight R-squared more heavily as it indicates fit quality
        confidence = 0.6 * r_squared + 0.4 * distance_factor

        # Clamp to valid range
        confidence = max(0.0, min(1.0, confidence))

        return confidence

    def get_regime(self, hurst_value: float) -> MarketRegimeType:
        """
        Determine market regime from Hurst exponent value

        Classification:
        - H > trending_threshold (0.55): Market is trending (persistence)
        - H < mean_reversion_threshold (0.45): Market is mean-reverting
        - Otherwise: Market is random walk

        Args:
            hurst_value: Calculated Hurst exponent (0-1 range)

        Returns:
            MarketRegimeType indicating the detected regime
        """
        if hurst_value > self.config.trending_threshold:
            regime = MarketRegimeType.TRENDING
            logger.debug(f"Hurst {hurst_value:.4f} > {self.config.trending_threshold}: TRENDING")
        elif hurst_value < self.config.mean_reversion_threshold:
            regime = MarketRegimeType.MEAN_REVERTING
            logger.debug(f"Hurst {hurst_value:.4f} < {self.config.mean_reversion_threshold}: MEAN_REVERTING")
        else:
            regime = MarketRegimeType.RANDOM_WALK
            logger.debug(f"Hurst {hurst_value:.4f} in neutral zone: RANDOM_WALK")

        return regime

    def get_strategy_recommendation(self, regime: MarketRegimeType) -> StrategyType:
        """
        Get recommended strategy type based on market regime

        Strategy mapping:
        - TRENDING -> TREND_FOLLOWING: Use momentum, breakout, moving average strategies
        - RANDOM_WALK -> NEUTRAL: Reduce exposure, avoid trading, wait for clarity
        - MEAN_REVERTING -> MEAN_REVERSION: Use RSI extremes, Bollinger bands, pairs

        Args:
            regime: Detected market regime

        Returns:
            StrategyType recommendation for the given regime
        """
        strategy_map = {
            MarketRegimeType.TRENDING: StrategyType.TREND_FOLLOWING,
            MarketRegimeType.RANDOM_WALK: StrategyType.NEUTRAL,
            MarketRegimeType.MEAN_REVERTING: StrategyType.MEAN_REVERSION
        }

        strategy = strategy_map[regime]

        logger.info(f"Strategy recommendation for {regime.value}: {strategy.value}")

        return strategy

    def calculate_multi_period_hurst(
        self,
        prices: List[float],
        periods: Optional[List[int]] = None
    ) -> HurstResult:
        """
        Calculate Hurst Exponent across multiple lookback periods

        Multi-period analysis provides more robust regime detection by:
        1. Calculating Hurst for each specified period
        2. Weighting results by confidence (R-squared)
        3. Averaging to get final estimate

        This helps filter out noise and provides more stable regime detection
        across different time horizons.

        Args:
            prices: List of price values
            periods: Optional list of periods to analyze.
                    Defaults to config.lookback_periods [20, 50, 100, 200]

        Returns:
            HurstResult with averaged values and per-period breakdown

        Raises:
            ValueError: If no valid periods could be calculated
        """
        # Use provided periods or default from config
        analysis_periods = periods or self.config.lookback_periods

        # Filter periods that fit the data
        available_data = len(prices)
        valid_periods = [p for p in analysis_periods if p <= available_data and p >= self.config.min_periods]

        if not valid_periods:
            raise ValueError(
                f"No valid periods for {available_data} data points. "
                f"Minimum required: {self.config.min_periods}"
            )

        logger.info(
            f"Multi-period Hurst analysis: {len(valid_periods)} periods, "
            f"data points: {available_data}"
        )

        # Calculate Hurst for each period
        results: Dict[int, HurstResult] = {}
        weights: Dict[int, float] = {}

        for period in valid_periods:
            try:
                result = self.calculate_hurst(prices, period=period)
                results[period] = result
                # Weight by R-squared (fit quality) and sample size
                size_factor = min(1.0, period / 100)  # Favor larger samples up to 100
                weights[period] = result.r_squared * size_factor

                logger.debug(
                    f"Period {period}: H={result.hurst_value:.4f}, "
                    f"R^2={result.r_squared:.4f}, weight={weights[period]:.4f}"
                )
            except Exception as e:
                logger.warning(f"Failed to calculate Hurst for period {period}: {e}")
                continue

        if not results:
            raise ValueError("No valid Hurst calculations across any period")

        # Calculate weighted average Hurst value
        total_weight = sum(weights.values())

        if total_weight > 0:
            weighted_hurst = sum(
                results[p].hurst_value * weights[p]
                for p in results
            ) / total_weight
        else:
            # Fall back to simple average
            weighted_hurst = np.mean([r.hurst_value for r in results.values()])

        # Calculate average R-squared
        avg_r_squared = np.mean([r.r_squared for r in results.values()])

        # Determine regime from weighted average
        regime = self.get_regime(weighted_hurst)

        # Calculate confidence
        confidence = self._calculate_confidence(weighted_hurst, avg_r_squared)

        # Check for regime agreement across periods
        regimes = [r.regime for r in results.values()]
        regime_agreement = regimes.count(regime) / len(regimes) if regimes else 0

        # Boost confidence if regimes agree, reduce if they disagree
        confidence = confidence * (0.7 + 0.3 * regime_agreement)

        # Get strategy recommendation
        strategy = self.get_strategy_recommendation(regime)

        # Extract per-period Hurst values for result
        multi_period_values = {p: r.hurst_value for p, r in results.items()}

        # Use the largest period as the primary period
        primary_period = max(results.keys())
        total_samples = results[primary_period].sample_size

        # Create combined result
        combined_result = HurstResult(
            hurst_value=weighted_hurst,
            regime=regime,
            confidence=confidence,
            recommended_strategy=strategy,
            period=primary_period,
            sample_size=total_samples,
            r_squared=avg_r_squared,
            multi_period_values=multi_period_values
        )

        logger.info(
            f"Multi-period Hurst complete: H={weighted_hurst:.4f}, "
            f"regime={regime.value}, confidence={confidence:.2f}, "
            f"periods_analyzed={len(results)}, "
            f"regime_agreement={regime_agreement:.0%}"
        )

        return combined_result

    def get_regime_strength(self, hurst_value: float) -> float:
        """
        Calculate the strength/intensity of the current regime

        Strength indicates how far from random walk the market is:
        - 0.0 = exactly random walk (H = 0.5)
        - 1.0 = extremely trending (H = 1.0) or mean-reverting (H = 0.0)

        This can be used to scale position sizes or filter signals.

        Args:
            hurst_value: Calculated Hurst exponent

        Returns:
            Regime strength from 0.0 to 1.0
        """
        # Distance from 0.5 (random walk), normalized to 0-1
        strength = abs(hurst_value - 0.5) * 2  # Max distance is 0.5, so *2 for 0-1 range

        # Clamp to valid range
        strength = max(0.0, min(1.0, strength))

        return strength

    def should_trade(self, result: HurstResult) -> bool:
        """
        Determine if trading is advisable based on Hurst analysis

        Trading is not recommended when:
        - Regime is RANDOM_WALK (no exploitable pattern)
        - Confidence is below configured threshold

        Args:
            result: HurstResult from calculation

        Returns:
            True if trading is recommended, False otherwise
        """
        # Don't trade during random walk
        if result.regime == MarketRegimeType.RANDOM_WALK:
            logger.info("Trading not recommended: market in random walk regime")
            return False

        # Don't trade with low confidence
        if result.confidence < self.config.confidence_level:
            logger.info(
                f"Trading not recommended: confidence {result.confidence:.2f} "
                f"below threshold {self.config.confidence_level}"
            )
            return False

        logger.info(
            f"Trading recommended: regime={result.regime.value}, "
            f"confidence={result.confidence:.2f}"
        )
        return True

    def get_status(self) -> Dict[str, Any]:
        """
        Get current calculator status and configuration

        Returns:
            Dictionary with configuration and status information
        """
        return {
            "name": "HurstExponentCalculator",
            "config": {
                "min_periods": self.config.min_periods,
                "lookback_periods": self.config.lookback_periods,
                "trending_threshold": self.config.trending_threshold,
                "mean_reversion_threshold": self.config.mean_reversion_threshold,
                "confidence_level": self.config.confidence_level
            },
            "regime_thresholds": {
                "trending": f"H > {self.config.trending_threshold}",
                "random_walk": f"{self.config.mean_reversion_threshold} <= H <= {self.config.trending_threshold}",
                "mean_reverting": f"H < {self.config.mean_reversion_threshold}"
            },
            "strategy_mapping": {
                regime.value: self.get_strategy_recommendation(regime).value
                for regime in MarketRegimeType
            }
        }


# Factory function for easy instantiation
def create_hurst_calculator(
    trending_threshold: float = 0.55,
    mean_reversion_threshold: float = 0.45,
    min_periods: int = 50,
    lookback_periods: Optional[List[int]] = None,
    confidence_level: float = 0.7
) -> HurstExponentCalculator:
    """
    Factory function to create a Hurst Exponent Calculator

    Provides a convenient way to create a calculator with custom settings.

    Args:
        trending_threshold: Hurst value above which market is trending (default: 0.55)
        mean_reversion_threshold: Hurst value below which market is mean-reverting (default: 0.45)
        min_periods: Minimum data points required (default: 50)
        lookback_periods: Periods for multi-scale analysis (default: [20, 50, 100, 200])
        confidence_level: Minimum confidence for regime classification (default: 0.7)

    Returns:
        Configured HurstExponentCalculator instance
    """
    config = HurstConfig(
        trending_threshold=trending_threshold,
        mean_reversion_threshold=mean_reversion_threshold,
        min_periods=min_periods,
        lookback_periods=lookback_periods or [20, 50, 100, 200],
        confidence_level=confidence_level
    )

    return HurstExponentCalculator(config)
