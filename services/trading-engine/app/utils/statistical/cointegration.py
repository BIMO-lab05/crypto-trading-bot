"""
Cointegration Testing for Pairs Trading Strategy

This module implements statistical tests for identifying cointegrated asset pairs:
- Augmented Dickey-Fuller (ADF) Test for stationarity
- Engle-Granger Two-Step Cointegration Test
- Johansen Cointegration Test
- Pair Scanner for automated pair discovery

Mathematical Background:
- Two time series X and Y are cointegrated if their linear combination is stationary
- Stationarity: Mean-reverting behavior (required for pairs trading)
- Cointegration equation: Y = β*X + ε, where ε is stationary

Phase 2.2 - Statistical Arbitrage Implementation
Author: Trading Bot Development Team
Date: 2025-12-07
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from scipy import stats
import logging

logger = logging.getLogger(__name__)


@dataclass
class CointegrationResult:
    """
    Results from cointegration testing

    Attributes:
        is_cointegrated: Whether the pair is cointegrated
        test_statistic: Test statistic value
        p_value: P-value for hypothesis test
        critical_values: Critical values at different significance levels
        hedge_ratio: Optimal hedge ratio (beta coefficient)
        half_life: Half-life of mean reversion (days)
        spread_std: Standard deviation of spread
        confidence_level: Confidence level (95%, 90%, etc.)
        method: Testing method used (ADF, Engle-Granger, Johansen)
    """
    is_cointegrated: bool
    test_statistic: float
    p_value: float
    critical_values: Dict[str, float]
    hedge_ratio: float
    half_life: Optional[float] = None
    spread_std: Optional[float] = None
    confidence_level: str = "95%"
    method: str = "Engle-Granger"


def test_adf(series: pd.Series, max_lag: Optional[int] = None) -> Dict[str, float]:
    """
    Augmented Dickey-Fuller (ADF) Test for stationarity

    Hypothesis Test:
    - H0 (null): Series has unit root (non-stationary)
    - H1 (alternative): Series is stationary

    If p-value < 0.05, reject H0 → series is stationary

    Args:
        series: Time series data (prices or spread)
        max_lag: Maximum number of lags to use (default: auto-select)

    Returns:
        Dictionary with test results:
        - adf_statistic: Test statistic
        - p_value: P-value
        - critical_values: Critical values (1%, 5%, 10%)
        - is_stationary: Whether series is stationary (p < 0.05)

    Mathematical Formula:
        ΔY_t = α + βt + γY_{t-1} + Σδ_iΔY_{t-i} + ε_t
        Test if γ = 0 (unit root) vs γ < 0 (stationary)
    """
    try:
        from statsmodels.tsa.stattools import adfuller

        # Remove NaN values
        series_clean = series.dropna()

        # Auto-select lag order if not specified
        if max_lag is None:
            max_lag = int(np.ceil(12 * (len(series_clean) / 100) ** (1/4)))

        # Run ADF test
        result = adfuller(series_clean, maxlag=max_lag, regression='ct', autolag='AIC')

        adf_stat, p_value = result[0], result[1]
        critical_values = result[4]  # 1%, 5%, 10% critical values

        # Determine if stationary (reject null at 5% level)
        is_stationary = p_value < 0.05

        logger.debug(
            f"ADF Test: statistic={adf_stat:.4f}, p-value={p_value:.4f}, "
            f"stationary={is_stationary}"
        )

        return {
            "adf_statistic": adf_stat,
            "p_value": p_value,
            "critical_values": {
                "1%": critical_values["1%"],
                "5%": critical_values["5%"],
                "10%": critical_values["10%"],
            },
            "is_stationary": is_stationary,
            "lags_used": result[2],
        }

    except ImportError:
        logger.error("statsmodels not installed. Install: pip install statsmodels")
        raise
    except Exception as e:
        logger.error(f"ADF test failed: {e}")
        raise


def calculate_hedge_ratio(x: pd.Series, y: pd.Series) -> Tuple[float, float, pd.Series]:
    """
    Calculate optimal hedge ratio using Ordinary Least Squares (OLS) regression

    Regression Model:
        Y = α + β*X + ε
        β (hedge ratio) minimizes spread variance

    Args:
        x: Price series for asset X
        y: Price series for asset Y

    Returns:
        Tuple of (hedge_ratio, intercept, residuals)
        - hedge_ratio (β): How many units of X to hedge 1 unit of Y
        - intercept (α): Regression intercept
        - residuals (ε): Spread time series (Y - β*X - α)

    Example:
        If β = 0.5, then to hedge 1 BTC position, buy 0.5 ETH
    """
    try:
        from scipy.stats import linregress

        # Align series and remove NaN
        df = pd.DataFrame({'x': x, 'y': y}).dropna()

        # OLS regression: y = α + β*x + ε
        slope, intercept, r_value, p_value, std_err = linregress(df['x'], df['y'])

        # Calculate residuals (spread)
        residuals = df['y'] - (slope * df['x'] + intercept)

        logger.debug(
            f"Hedge ratio: β={slope:.4f}, α={intercept:.4f}, "
            f"R²={r_value**2:.4f}"
        )

        return slope, intercept, residuals

    except Exception as e:
        logger.error(f"Failed to calculate hedge ratio: {e}")
        raise


def calculate_half_life(spread: pd.Series) -> Optional[float]:
    """
    Calculate half-life of mean reversion for spread

    Half-life: Time for spread to revert halfway back to mean

    Mean Reversion Model (AR(1)):
        ΔS_t = λ(μ - S_{t-1}) + ε_t
        where λ is mean reversion speed

    Half-life formula:
        τ = -ln(2) / ln(1 + λ)

    Args:
        spread: Spread time series (residuals from regression)

    Returns:
        Half-life in time periods (e.g., hours if hourly data)
        Returns None if spread is not mean-reverting

    Interpretation:
        - Small half-life (<10 periods): Fast mean reversion, good for pairs trading
        - Large half-life (>100 periods): Slow reversion, risky
    """
    try:
        # Calculate lagged spread
        spread_lag = spread.shift(1)
        spread_diff = spread - spread_lag

        # Remove NaN
        df = pd.DataFrame({
            'spread_lag': spread_lag,
            'spread_diff': spread_diff
        }).dropna()

        # Fit AR(1) model: ΔS = λ*S_{t-1} + intercept
        from scipy.stats import linregress
        slope, intercept, r_value, p_value, std_err = linregress(
            df['spread_lag'], df['spread_diff']
        )

        # Mean reversion coefficient λ
        lambda_coef = slope

        # Check if mean-reverting (λ < 0)
        if lambda_coef >= 0:
            logger.warning("Spread is not mean-reverting (λ >= 0)")
            return None

        # Calculate half-life: τ = -ln(2) / ln(1 + λ)
        half_life = -np.log(2) / np.log(1 + lambda_coef)

        logger.debug(f"Half-life: {half_life:.2f} periods (λ={lambda_coef:.4f})")

        return float(half_life)

    except Exception as e:
        logger.error(f"Failed to calculate half-life: {e}")
        return None


def test_engle_granger(
    x: pd.Series,
    y: pd.Series,
    significance_level: float = 0.05
) -> CointegrationResult:
    """
    Engle-Granger Two-Step Cointegration Test

    Two-Step Process:
    1. Estimate cointegrating relationship via OLS: Y = β*X + ε
    2. Test if residuals (spread) are stationary using ADF

    If spread is stationary → X and Y are cointegrated → Good for pairs trading

    Args:
        x: Price series for asset X
        y: Price series for asset Y
        significance_level: Significance level for test (default: 0.05 = 5%)

    Returns:
        CointegrationResult with:
        - is_cointegrated: True if cointegrated at given significance
        - hedge_ratio: Optimal β for spread = Y - β*X
        - half_life: Mean reversion speed
        - All test statistics

    Critical Values (MacKinnon 1991):
        - More stringent than standard ADF critical values
        - Account for estimation of β in first step
    """
    try:
        # Step 1: Calculate hedge ratio via OLS regression
        hedge_ratio, intercept, spread = calculate_hedge_ratio(x, y)

        # Step 2: Test if spread is stationary
        adf_result = test_adf(spread)

        # Engle-Granger critical values (more stringent than ADF)
        # MacKinnon (1991) approximation for 2-variable system
        critical_values_eg = {
            "1%": -3.90,
            "5%": -3.34,
            "10%": -3.04,
        }

        # Determine cointegration based on significance level
        if significance_level == 0.01:
            critical_value = critical_values_eg["1%"]
            confidence = "99%"
        elif significance_level == 0.10:
            critical_value = critical_values_eg["10%"]
            confidence = "90%"
        else:  # 0.05 default
            critical_value = critical_values_eg["5%"]
            confidence = "95%"

        is_cointegrated = adf_result["adf_statistic"] < critical_value

        # Calculate additional metrics
        half_life = calculate_half_life(spread)
        spread_std = float(spread.std())

        result = CointegrationResult(
            is_cointegrated=is_cointegrated,
            test_statistic=adf_result["adf_statistic"],
            p_value=adf_result["p_value"],
            critical_values=critical_values_eg,
            hedge_ratio=hedge_ratio,
            half_life=half_life,
            spread_std=spread_std,
            confidence_level=confidence,
            method="Engle-Granger"
        )

        logger.info(
            f"Engle-Granger Test: cointegrated={is_cointegrated}, "
            f"statistic={result.test_statistic:.4f}, "
            f"critical={critical_value:.4f}, "
            f"hedge_ratio={hedge_ratio:.4f}"
        )

        return result

    except Exception as e:
        logger.error(f"Engle-Granger test failed: {e}")
        raise


def test_johansen(
    data: pd.DataFrame,
    significance_level: float = 0.05,
    det_order: int = 0
) -> Dict:
    """
    Johansen Cointegration Test (for multiple time series)

    Advantages over Engle-Granger:
    - Tests multiple cointegrating relationships simultaneously
    - More powerful for >2 variables
    - Provides trace and eigenvalue statistics

    Hypothesis:
    - H0: r = 0 (no cointegration)
    - H1: r > 0 (at least r cointegrating vectors)

    Args:
        data: DataFrame with multiple price series (columns = assets)
        significance_level: Significance level (0.01, 0.05, 0.10)
        det_order: Deterministic trend order:
            -1: No deterministic part
             0: Constant term
             1: Constant + linear trend

    Returns:
        Dictionary with:
        - num_cointegrating_vectors: Number of cointegrating relationships found
        - trace_statistic: Trace test statistic
        - max_eig_statistic: Maximum eigenvalue statistic
        - critical_values: Critical values for tests
        - eigenvectors: Cointegrating vectors (hedge ratios)

    Note: Requires at least 2 time series columns
    """
    try:
        from statsmodels.tsa.vector_ar.vecm import coint_johansen

        # Remove NaN values
        data_clean = data.dropna()

        # Run Johansen test
        result = coint_johansen(data_clean, det_order=det_order, k_ar_diff=1)

        # Determine significance index (0=90%, 1=95%, 2=99%)
        if significance_level == 0.01:
            sig_idx = 2
            confidence = "99%"
        elif significance_level == 0.10:
            sig_idx = 0
            confidence = "90%"
        else:
            sig_idx = 1
            confidence = "95%"

        # Trace statistic test
        trace_stat = result.lr1  # Trace statistics
        trace_crit = result.cvt[:, sig_idx]  # Critical values

        # Count cointegrating relationships
        num_coint = np.sum(trace_stat > trace_crit)

        logger.info(
            f"Johansen Test: found {num_coint} cointegrating vectors "
            f"at {confidence} confidence"
        )

        return {
            "num_cointegrating_vectors": int(num_coint),
            "trace_statistic": trace_stat.tolist(),
            "trace_critical_values": trace_crit.tolist(),
            "max_eig_statistic": result.lr2.tolist(),
            "max_eig_critical_values": result.cvm[:, sig_idx].tolist(),
            "eigenvectors": result.evec.tolist(),
            "confidence_level": confidence,
        }

    except ImportError:
        logger.error("statsmodels not installed. Install: pip install statsmodels")
        raise
    except Exception as e:
        logger.error(f"Johansen test failed: {e}")
        raise


class CointegrationTester:
    """
    Unified interface for cointegration testing

    Provides methods for:
    - Testing single pair cointegration
    - Calculating spread characteristics
    - Scoring pair quality

    Usage:
        tester = CointegrationTester()
        result = tester.test_pair(btc_prices, eth_prices)
        if result.is_cointegrated:
            print(f"Hedge ratio: {result.hedge_ratio}")
    """

    def __init__(self, significance_level: float = 0.05):
        """
        Initialize cointegration tester

        Args:
            significance_level: Significance level for tests (default: 0.05)
        """
        self.significance_level = significance_level
        logger.info(f"CointegrationTester initialized (α={significance_level})")

    def test_pair(
        self,
        x: pd.Series,
        y: pd.Series,
        method: str = "engle-granger"
    ) -> CointegrationResult:
        """
        Test if two price series are cointegrated

        Args:
            x: Price series for asset X
            y: Price series for asset Y
            method: Testing method ("engle-granger" or "johansen")

        Returns:
            CointegrationResult with test results
        """
        if method.lower() == "engle-granger":
            return test_engle_granger(x, y, self.significance_level)
        elif method.lower() == "johansen":
            # Johansen for 2-variable case
            data = pd.DataFrame({'x': x, 'y': y})
            johansen_result = test_johansen(data, self.significance_level)

            # Convert to CointegrationResult format
            is_coint = johansen_result["num_cointegrating_vectors"] > 0
            hedge_ratio, intercept, spread = calculate_hedge_ratio(x, y)

            return CointegrationResult(
                is_cointegrated=is_coint,
                test_statistic=johansen_result["trace_statistic"][0],
                p_value=0.0,  # Johansen doesn't provide p-value
                critical_values={
                    "trace": johansen_result["trace_critical_values"][0]
                },
                hedge_ratio=hedge_ratio,
                method="Johansen"
            )
        else:
            raise ValueError(f"Unknown method: {method}")

    def score_pair_quality(self, result: CointegrationResult) -> float:
        """
        Score pair quality for trading (0-100 scale)

        Scoring Criteria:
        - Cointegration strength (test statistic vs critical value)
        - Half-life (prefer 5-50 periods)
        - Spread stability (lower std deviation better)

        Args:
            result: CointegrationResult from test_pair()

        Returns:
            Quality score (0-100):
            - 90-100: Excellent pair
            - 70-90: Good pair
            - 50-70: Marginal pair
            - <50: Poor pair (don't trade)
        """
        score = 0.0

        # Cointegration strength (40 points max)
        if result.is_cointegrated:
            # Stronger cointegration = lower test statistic
            crit_val = result.critical_values.get("5%", -3.34)
            strength = abs(result.test_statistic / crit_val)
            score += min(40, strength * 20)

        # Half-life quality (30 points max)
        if result.half_life is not None:
            if 5 <= result.half_life <= 50:
                # Optimal range
                score += 30
            elif result.half_life < 5:
                # Too fast (might be noise)
                score += 15
            elif result.half_life <= 100:
                # Acceptable
                score += 20
            else:
                # Too slow
                score += 5

        # Spread stability (30 points max)
        if result.spread_std is not None:
            # Lower std deviation is better
            if result.spread_std < 0.01:
                score += 30
            elif result.spread_std < 0.05:
                score += 20
            elif result.spread_std < 0.10:
                score += 10

        return min(100.0, score)


class PairScanner:
    """
    Automated scanner to find cointegrated pairs from multiple assets

    Scans all possible pairs and identifies best candidates for pairs trading.

    Usage:
        scanner = PairScanner()
        pairs = scanner.scan_pairs(price_data)
        for pair in pairs:
            print(f"{pair['symbol_x']} / {pair['symbol_y']}: "
                  f"score={pair['score']:.1f}")
    """

    def __init__(
        self,
        significance_level: float = 0.05,
        min_quality_score: float = 50.0
    ):
        """
        Initialize pair scanner

        Args:
            significance_level: Significance level for cointegration tests
            min_quality_score: Minimum quality score to include pair (0-100)
        """
        self.tester = CointegrationTester(significance_level)
        self.min_quality_score = min_quality_score
        logger.info(
            f"PairScanner initialized (min_score={min_quality_score})"
        )

    def scan_pairs(
        self,
        price_data: Dict[str, pd.Series],
        max_pairs: Optional[int] = None
    ) -> List[Dict]:
        """
        Scan all possible pairs and rank by quality

        Args:
            price_data: Dictionary of {symbol: price_series}
            max_pairs: Maximum number of pairs to return (default: all)

        Returns:
            List of dictionaries sorted by quality score:
            [{
                'symbol_x': 'BTCUSDT',
                'symbol_y': 'ETHUSDT',
                'hedge_ratio': 0.05,
                'half_life': 12.5,
                'score': 85.3,
                'result': CointegrationResult(...)
            }, ...]
        """
        symbols = list(price_data.keys())
        pairs = []

        logger.info(f"Scanning {len(symbols)} symbols for cointegrated pairs")

        # Test all possible pairs (n choose 2)
        for i, symbol_x in enumerate(symbols):
            for symbol_y in symbols[i+1:]:
                try:
                    # Test cointegration
                    result = self.tester.test_pair(
                        price_data[symbol_x],
                        price_data[symbol_y]
                    )

                    # Score pair quality
                    score = self.tester.score_pair_quality(result)

                    # Only include if meets minimum quality
                    if score >= self.min_quality_score:
                        pairs.append({
                            'symbol_x': symbol_x,
                            'symbol_y': symbol_y,
                            'hedge_ratio': result.hedge_ratio,
                            'half_life': result.half_life,
                            'spread_std': result.spread_std,
                            'score': score,
                            'result': result
                        })

                        logger.debug(
                            f"Found pair: {symbol_x}/{symbol_y} "
                            f"(score={score:.1f})"
                        )

                except Exception as e:
                    logger.warning(
                        f"Failed to test {symbol_x}/{symbol_y}: {e}"
                    )
                    continue

        # Sort by quality score (descending)
        pairs.sort(key=lambda p: p['score'], reverse=True)

        # Limit number of pairs if requested
        if max_pairs is not None:
            pairs = pairs[:max_pairs]

        logger.info(
            f"Found {len(pairs)} cointegrated pairs "
            f"(min_score={self.min_quality_score})"
        )

        return pairs
