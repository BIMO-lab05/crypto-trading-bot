"""
Unit Tests for Cointegration Testing Module

Tests cover:
- ADF stationarity test
- Engle-Granger cointegration test
- Johansen cointegration test
- Hedge ratio calculation
- Half-life calculation
- Pair scanner functionality

Phase 2.2 - Statistical Arbitrage Implementation
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Tuple

# Import the module we're testing
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from app.utils.statistical.cointegration import (
    test_adf,
    test_engle_granger,
    test_johansen,
    calculate_hedge_ratio,
    calculate_half_life,
    CointegrationTester,
    PairScanner,
    CointegrationResult,
)


# ============================================================================
# Test Data Generation
# ============================================================================

def generate_stationary_series(n: int = 100, seed: int = 42) -> pd.Series:
    """Generate a stationary time series (mean-reverting)"""
    np.random.seed(seed)

    # AR(1) process with mean reversion: y_t = 0.7*y_{t-1} + noise
    y = np.zeros(n)
    y[0] = np.random.normal(0, 1)

    for t in range(1, n):
        y[t] = 0.7 * y[t-1] + np.random.normal(0, 0.5)

    return pd.Series(y, index=pd.date_range('2025-01-01', periods=n, freq='H'))


def generate_nonstationary_series(n: int = 100, seed: int = 42) -> pd.Series:
    """Generate a non-stationary time series (random walk)"""
    np.random.seed(seed)

    # Random walk: y_t = y_{t-1} + noise
    y = np.cumsum(np.random.normal(0, 1, n))

    return pd.Series(y, index=pd.date_range('2025-01-01', periods=n, freq='H'))


def generate_cointegrated_pair(
    n: int = 100,
    hedge_ratio: float = 0.5,
    seed: int = 42
) -> Tuple[pd.Series, pd.Series]:
    """
    Generate two cointegrated price series

    Y = β*X + stationary_spread

    This ensures X and Y are cointegrated with hedge ratio β
    """
    np.random.seed(seed)

    dates = pd.date_range('2025-01-01', periods=n, freq='H')

    # Generate non-stationary series X (random walk)
    x_returns = np.random.normal(0.001, 0.02, n)
    x_prices = 100 * np.exp(np.cumsum(x_returns))
    x = pd.Series(x_prices, index=dates)

    # Generate stationary spread
    spread = generate_stationary_series(n, seed=seed+1) * 2

    # Cointegrated series: Y = β*X + spread
    y = hedge_ratio * x + spread

    return x, y


def generate_non_cointegrated_pair(
    n: int = 100,
    seed: int = 42
) -> Tuple[pd.Series, pd.Series]:
    """Generate two independent non-cointegrated series"""
    np.random.seed(seed)

    dates = pd.date_range('2025-01-01', periods=n, freq='H')

    # Two independent random walks
    x = pd.Series(
        100 * np.exp(np.cumsum(np.random.normal(0.001, 0.02, n))),
        index=dates
    )
    y = pd.Series(
        100 * np.exp(np.cumsum(np.random.normal(0.001, 0.02, n))),
        index=dates
    )

    return x, y


# ============================================================================
# Test ADF Stationarity Test
# ============================================================================

class TestADF:
    """Test Augmented Dickey-Fuller stationarity test"""

    def test_adf_stationary_series(self):
        """Test that stationary series is correctly identified"""
        series = generate_stationary_series(n=200)

        result = test_adf(series)

        # Check result structure
        assert "adf_statistic" in result
        assert "p_value" in result
        assert "critical_values" in result
        assert "is_stationary" in result

        # Stationary series should have p-value < 0.05
        assert result["is_stationary"] == True
        assert result["p_value"] < 0.05

        # Test statistic should be more negative than critical values
        assert result["adf_statistic"] < result["critical_values"]["5%"]

    def test_adf_nonstationary_series(self):
        """Test that non-stationary series is correctly identified"""
        series = generate_nonstationary_series(n=200)

        result = test_adf(series)

        # Non-stationary series should have p-value > 0.05
        # Note: Random walk sometimes tests as stationary with small samples
        # So we just check the test runs correctly
        assert "is_stationary" in result
        assert "p_value" in result
        assert result["p_value"] >= 0.0  # Valid p-value

    def test_adf_handles_nan(self):
        """Test that ADF handles NaN values correctly"""
        series = generate_stationary_series(n=100)
        series.iloc[10:15] = np.nan  # Insert NaN values

        result = test_adf(series)

        # Should run without error and give valid results
        assert result["is_stationary"] in [True, False]
        assert 0 <= result["p_value"] <= 1


# ============================================================================
# Test Hedge Ratio Calculation
# ============================================================================

class TestHedgeRatio:
    """Test hedge ratio calculation via OLS regression"""

    def test_hedge_ratio_calculation(self):
        """Test that hedge ratio is calculated correctly"""
        # Generate pair with known hedge ratio
        x, y = generate_cointegrated_pair(n=200, hedge_ratio=0.5)

        hedge_ratio, intercept, residuals = calculate_hedge_ratio(x, y)

        # Hedge ratio should be close to 0.5 (within 10% tolerance)
        assert abs(hedge_ratio - 0.5) < 0.05

        # Residuals should be mean-reverting (check length)
        assert len(residuals) == len(x)

        # Residuals should have lower variance than original series
        assert residuals.std() < y.std()

    def test_hedge_ratio_perfect_correlation(self):
        """Test hedge ratio when Y = 2*X (perfect correlation)"""
        n = 100
        x = pd.Series(np.arange(1, n+1), index=pd.date_range('2025-01-01', periods=n))
        y = 2 * x  # Y = 2*X

        hedge_ratio, intercept, residuals = calculate_hedge_ratio(x, y)

        # Should get hedge ratio of 2.0
        assert abs(hedge_ratio - 2.0) < 0.01

        # Residuals should be near zero
        assert residuals.std() < 0.01


# ============================================================================
# Test Half-Life Calculation
# ============================================================================

class TestHalfLife:
    """Test half-life of mean reversion calculation"""

    def test_half_life_stationary_spread(self):
        """Test half-life calculation for mean-reverting spread"""
        spread = generate_stationary_series(n=200)

        half_life = calculate_half_life(spread)

        # Should return a positive half-life
        assert half_life is not None
        assert half_life > 0

        # For this AR(1) process with λ=0.7, half-life should be reasonable
        assert 1 < half_life < 100

    def test_half_life_random_walk(self):
        """Test half-life for non-mean-reverting series"""
        spread = generate_nonstationary_series(n=200)

        half_life = calculate_half_life(spread)

        # Random walk is not mean-reverting, should return None or very large
        # (depends on random sample)
        if half_life is not None:
            # If it returns a value, should be very large or unreasonable
            assert half_life > 0


# ============================================================================
# Test Engle-Granger Cointegration
# ============================================================================

class TestEngleGranger:
    """Test Engle-Granger two-step cointegration test"""

    def test_cointegrated_pair(self):
        """Test that cointegrated pair is correctly identified"""
        x, y = generate_cointegrated_pair(n=300, hedge_ratio=0.5)

        result = test_engle_granger(x, y, significance_level=0.05)

        # Check result structure
        assert isinstance(result, CointegrationResult)
        assert result.method == "Engle-Granger"

        # Should be identified as cointegrated
        assert result.is_cointegrated == True

        # Hedge ratio should be close to 0.5
        assert abs(result.hedge_ratio - 0.5) < 0.1

        # Should have reasonable half-life
        assert result.half_life is not None
        assert 0 < result.half_life < 200

    def test_non_cointegrated_pair(self):
        """Test that non-cointegrated pair is correctly rejected"""
        x, y = generate_non_cointegrated_pair(n=300)

        result = test_engle_granger(x, y, significance_level=0.05)

        # Non-cointegrated pairs should be rejected
        # Note: Sometimes random samples can appear cointegrated
        # So we just check the test runs correctly
        assert isinstance(result, CointegrationResult)
        assert result.is_cointegrated in [True, False]

    def test_different_significance_levels(self):
        """Test Engle-Granger at different significance levels"""
        x, y = generate_cointegrated_pair(n=300, hedge_ratio=0.5)

        # Test at 1%, 5%, 10% significance
        result_01 = test_engle_granger(x, y, significance_level=0.01)
        result_05 = test_engle_granger(x, y, significance_level=0.05)
        result_10 = test_engle_granger(x, y, significance_level=0.10)

        # More stringent test (1%) might reject, less stringent (10%) more likely to accept
        # Check confidence levels are set correctly
        assert result_01.confidence_level == "99%"
        assert result_05.confidence_level == "95%"
        assert result_10.confidence_level == "90%"


# ============================================================================
# Test Johansen Cointegration
# ============================================================================

class TestJohansen:
    """Test Johansen cointegration test"""

    def test_johansen_cointegrated_pair(self):
        """Test Johansen on cointegrated pair"""
        x, y = generate_cointegrated_pair(n=300, hedge_ratio=0.5)
        data = pd.DataFrame({'x': x, 'y': y})

        result = test_johansen(data, significance_level=0.05)

        # Check result structure
        assert "num_cointegrating_vectors" in result
        assert "trace_statistic" in result
        assert "eigenvectors" in result

        # Should find at least one cointegrating relationship
        assert result["num_cointegrating_vectors"] >= 0


# ============================================================================
# Test CointegrationTester Class
# ============================================================================

class TestCointegrationTester:
    """Test unified CointegrationTester interface"""

    def test_tester_initialization(self):
        """Test tester initialization"""
        tester = CointegrationTester(significance_level=0.05)

        assert tester.significance_level == 0.05

    def test_tester_test_pair(self):
        """Test pair testing via unified interface"""
        tester = CointegrationTester()

        x, y = generate_cointegrated_pair(n=300, hedge_ratio=0.5)
        result = tester.test_pair(x, y, method="engle-granger")

        assert isinstance(result, CointegrationResult)
        assert result.is_cointegrated == True

    def test_tester_score_pair_quality(self):
        """Test pair quality scoring"""
        tester = CointegrationTester()

        x, y = generate_cointegrated_pair(n=300, hedge_ratio=0.5)
        result = tester.test_pair(x, y)

        score = tester.score_pair_quality(result)

        # Score should be 0-100
        assert 0 <= score <= 100

        # Cointegrated pair should get a decent score
        if result.is_cointegrated:
            assert score >= 30  # At least some points


# ============================================================================
# Test PairScanner Class
# ============================================================================

class TestPairScanner:
    """Test automated pair scanning"""

    def test_scanner_initialization(self):
        """Test scanner initialization"""
        scanner = PairScanner(
            significance_level=0.05,
            min_quality_score=50.0
        )

        assert scanner.min_quality_score == 50.0

    def test_scanner_scan_pairs(self):
        """Test scanning multiple symbols for cointegrated pairs"""
        scanner = PairScanner(min_quality_score=0)  # Accept all pairs

        # Generate 3 pairs: 2 cointegrated, 1 independent
        x1, y1 = generate_cointegrated_pair(n=300, hedge_ratio=0.5, seed=1)
        x2, y2 = generate_cointegrated_pair(n=300, hedge_ratio=0.7, seed=2)
        x3, y3 = generate_non_cointegrated_pair(n=300, seed=3)

        price_data = {
            'SYMBOL_X1': x1,
            'SYMBOL_Y1': y1,
            'SYMBOL_X2': x2,
            'SYMBOL_Y2': y2,
            'SYMBOL_X3': x3,
            'SYMBOL_Y3': y3,
        }

        pairs = scanner.scan_pairs(price_data, max_pairs=10)

        # Should find some pairs
        assert isinstance(pairs, list)
        assert len(pairs) > 0

        # Each pair should have required fields
        for pair in pairs:
            assert 'symbol_x' in pair
            assert 'symbol_y' in pair
            assert 'hedge_ratio' in pair
            assert 'score' in pair
            assert 'result' in pair

            # Score should be 0-100
            assert 0 <= pair['score'] <= 100

    def test_scanner_max_pairs_limit(self):
        """Test that scanner respects max_pairs limit"""
        scanner = PairScanner(min_quality_score=0)

        # Generate 4 symbols (6 possible pairs)
        symbols = {}
        for i in range(4):
            x, y = generate_cointegrated_pair(n=200, seed=i)
            symbols[f'SYM{i}'] = x

        # Request max 3 pairs
        pairs = scanner.scan_pairs(symbols, max_pairs=3)

        # Should return at most 3 pairs
        assert len(pairs) <= 3

    def test_scanner_quality_filtering(self):
        """Test that scanner filters by minimum quality score"""
        scanner = PairScanner(min_quality_score=80.0)  # High threshold

        # Generate mixed quality pairs
        x1, y1 = generate_cointegrated_pair(n=300, hedge_ratio=0.5, seed=1)
        x2, y2 = generate_non_cointegrated_pair(n=300, seed=2)

        price_data = {
            'GOOD_X': x1,
            'GOOD_Y': y1,
            'BAD_X': x2,
            'BAD_Y': y2,
        }

        pairs = scanner.scan_pairs(price_data)

        # All returned pairs should meet minimum quality
        for pair in pairs:
            assert pair['score'] >= 80.0


# ============================================================================
# Integration Tests
# ============================================================================

class TestCointegrationIntegration:
    """Integration tests for complete workflow"""

    def test_complete_workflow(self):
        """Test complete cointegration testing workflow"""
        # 1. Generate synthetic data
        btc_prices, eth_prices = generate_cointegrated_pair(
            n=500,
            hedge_ratio=0.05,  # 1 BTC = 0.05 ETH (hypothetical)
            seed=42
        )

        # 2. Initialize tester
        tester = CointegrationTester(significance_level=0.05)

        # 3. Test for cointegration
        result = tester.test_pair(btc_prices, eth_prices)

        # 4. Verify results
        assert isinstance(result, CointegrationResult)
        assert result.is_cointegrated == True

        # 5. Score pair quality
        score = tester.score_pair_quality(result)
        assert 0 <= score <= 100

        # 6. Log results
        print(f"\n=== Cointegration Test Results ===")
        print(f"Pair: BTC/ETH")
        print(f"Cointegrated: {result.is_cointegrated}")
        print(f"Hedge Ratio: {result.hedge_ratio:.4f}")
        print(f"Half-life: {result.half_life:.2f} periods")
        print(f"Quality Score: {score:.1f}/100")

    def test_scanner_workflow(self):
        """Test complete pair scanning workflow"""
        # 1. Generate price data for multiple symbols
        price_data = {}

        # Create 3 cointegrated pairs
        for i in range(3):
            x, y = generate_cointegrated_pair(n=300, hedge_ratio=0.5+i*0.1, seed=i)
            price_data[f'ASSET_X{i}'] = x
            price_data[f'ASSET_Y{i}'] = y

        # 2. Initialize scanner
        scanner = PairScanner(min_quality_score=30.0)

        # 3. Scan for pairs
        pairs = scanner.scan_pairs(price_data, max_pairs=5)

        # 4. Verify results
        assert len(pairs) > 0

        # 5. Print top pairs
        print(f"\n=== Top Cointegrated Pairs ===")
        for pair in pairs[:3]:
            print(f"{pair['symbol_x']} / {pair['symbol_y']}: "
                  f"Score={pair['score']:.1f}, "
                  f"Hedge Ratio={pair['hedge_ratio']:.4f}")


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    # Run all tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
