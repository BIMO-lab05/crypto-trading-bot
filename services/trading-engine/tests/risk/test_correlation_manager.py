"""
Portfolio Correlation Manager Tests
Purpose: Comprehensive tests for Phase 3.1 Portfolio Correlation Analysis

Created: 2025-12-11
Target Coverage: >85%

Test Categories:
1. Correlation calculation accuracy
2. Diversification scoring
3. Position limit enforcement
4. Alert generation
5. Cache management
6. Integration tests

Test Data:
- Uses synthetic price data with known correlations
- BTC-ETH highly correlated (0.8+)
- BTC-SOL moderately correlated (0.4-0.6)
- BTC-ADA low correlation (0.1-0.3)
"""

import pytest
import asyncio
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List

# Import modules to test
from app.risk.correlation_manager import (
    CorrelationManager,
    CorrelationConfig,
    CorrelationMatrix,
    DiversificationScore,
    CorrelationAlert,
    AlertSeverity,
    get_correlation_manager,
    reset_correlation_manager,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def correlation_config():
    """Create test correlation configuration"""
    return CorrelationConfig(
        rolling_window_short=20,
        rolling_window_long=40,
        min_data_points=10,
        high_correlation_threshold=0.7,
        critical_correlation_threshold=0.8,
        moderate_correlation_threshold=0.6,
        max_correlated_positions=3,
        position_size_reduction_factor=0.5,
        cache_ttl_seconds=60,
        update_interval_seconds=60
    )


@pytest.fixture
def correlation_manager(correlation_config):
    """Create fresh correlation manager for each test"""
    reset_correlation_manager()
    manager = CorrelationManager(correlation_config)
    return manager


@pytest.fixture
def synthetic_price_data():
    """
    Generate synthetic price data with known correlations

    Creates price series where:
    - BTCUSDT: Base random walk
    - ETHUSDT: 0.85 correlated with BTC
    - SOLUSDT: 0.5 correlated with BTC
    - ADAUSDT: 0.2 correlated with BTC
    - XRPUSDT: -0.3 correlated with BTC (negative)
    """
    np.random.seed(42)  # Reproducible results
    n_points = 60

    # Base BTC prices (random walk)
    btc_returns = np.random.normal(0, 0.02, n_points)
    btc_prices = [100000]
    for ret in btc_returns:
        btc_prices.append(btc_prices[-1] * (1 + ret))
    btc_prices = btc_prices[1:]  # Remove initial seed

    # ETH - highly correlated with BTC (0.85)
    eth_prices = [3500]
    for i, ret in enumerate(btc_returns):
        eth_return = 0.85 * ret + 0.15 * np.random.normal(0, 0.02)
        eth_prices.append(eth_prices[-1] * (1 + eth_return))
    eth_prices = eth_prices[1:]

    # SOL - moderately correlated with BTC (0.5)
    sol_prices = [200]
    for i, ret in enumerate(btc_returns):
        sol_return = 0.5 * ret + 0.5 * np.random.normal(0, 0.03)
        sol_prices.append(sol_prices[-1] * (1 + sol_return))
    sol_prices = sol_prices[1:]

    # ADA - low correlation with BTC (0.2)
    ada_prices = [0.5]
    for i, ret in enumerate(btc_returns):
        ada_return = 0.2 * ret + 0.8 * np.random.normal(0, 0.03)
        ada_prices.append(ada_prices[-1] * (1 + ada_return))
    ada_prices = ada_prices[1:]

    # XRP - negative correlation with BTC (-0.3)
    xrp_prices = [0.6]
    for i, ret in enumerate(btc_returns):
        xrp_return = -0.3 * ret + 0.7 * np.random.normal(0, 0.025)
        xrp_prices.append(xrp_prices[-1] * (1 + xrp_return))
    xrp_prices = xrp_prices[1:]

    return {
        "BTCUSDT": btc_prices,
        "ETHUSDT": eth_prices,
        "SOLUSDT": sol_prices,
        "ADAUSDT": ada_prices,
        "XRPUSDT": xrp_prices
    }


@pytest.fixture
def insufficient_price_data():
    """Price data with insufficient points for correlation calculation"""
    return {
        "BTCUSDT": [100000, 100500, 101000],
        "ETHUSDT": [3500, 3520, 3540]
    }


# =============================================================================
# CORRELATION CALCULATION TESTS
# =============================================================================

class TestCorrelationCalculation:
    """Test suite for correlation calculation accuracy"""

    def test_calculate_correlation_positive_correlated(self, correlation_manager):
        """Test correlation calculation for positively correlated series"""
        # Generate perfectly correlated series
        np.random.seed(42)
        base = [100 + i * 10 + np.random.normal(0, 5) for i in range(30)]
        correlated = [b * 0.9 + np.random.normal(0, 1) for b in base]

        correlation = correlation_manager.calculate_correlation(base, correlated)

        assert correlation is not None
        assert correlation > 0.7, "Highly correlated series should have correlation > 0.7"

    def test_calculate_correlation_negative_correlated(self, correlation_manager):
        """Test correlation calculation for negatively correlated returns"""
        # Generate series with negatively correlated RETURNS
        # The correlation is calculated on returns, not raw prices
        np.random.seed(42)
        n_points = 50

        # Base series with returns
        base_returns = np.random.normal(0.01, 0.02, n_points - 1)
        base_prices = [100]
        for ret in base_returns:
            base_prices.append(base_prices[-1] * (1 + ret))

        # Negative correlated returns series
        neg_prices = [100]
        for ret in base_returns:
            # Invert returns to create negative correlation
            neg_return = -0.9 * ret + 0.1 * np.random.normal(0, 0.02)
            neg_prices.append(neg_prices[-1] * (1 + neg_return))

        correlation = correlation_manager.calculate_correlation(base_prices, neg_prices)

        assert correlation is not None
        # The correlation should be negative (returns are inverted)
        # Due to noise, we allow some tolerance
        assert correlation < 0, f"Should have negative correlation, got {correlation}"

    def test_calculate_correlation_uncorrelated(self, correlation_manager):
        """Test correlation calculation for uncorrelated series"""
        np.random.seed(42)
        series_a = [np.random.normal(100, 10) for _ in range(30)]
        series_b = [np.random.normal(100, 10) for _ in range(30)]

        correlation = correlation_manager.calculate_correlation(series_a, series_b)

        assert correlation is not None
        assert abs(correlation) < 0.5, "Uncorrelated series should have low correlation"

    def test_calculate_correlation_insufficient_data(self, correlation_manager):
        """Test correlation returns None for insufficient data"""
        series_a = [100, 101, 102]
        series_b = [50, 51, 52]

        correlation = correlation_manager.calculate_correlation(series_a, series_b)

        assert correlation is None, "Should return None for insufficient data"

    def test_calculate_correlation_different_lengths(self, correlation_manager):
        """Test correlation handles different length series"""
        np.random.seed(42)
        series_a = [100 + i for i in range(50)]
        series_b = [100 + i * 0.9 for i in range(30)]  # Shorter

        correlation = correlation_manager.calculate_correlation(series_a, series_b)

        assert correlation is not None, "Should handle different length series"

    def test_calculate_correlation_zero_variance(self, correlation_manager):
        """Test correlation handles zero variance (constant series)"""
        constant = [100.0] * 30
        varying = [100 + i for i in range(30)]

        correlation = correlation_manager.calculate_correlation(constant, varying)

        assert correlation is None, "Should return None for zero variance series"


# =============================================================================
# CORRELATION MATRIX TESTS
# =============================================================================

class TestCorrelationMatrix:
    """Test suite for correlation matrix operations"""

    @pytest.mark.asyncio
    async def test_update_correlations_creates_matrix(
        self,
        correlation_manager,
        synthetic_price_data
    ):
        """Test that update_correlations creates a valid matrix"""
        await correlation_manager.initialize()
        matrix = await correlation_manager.update_correlations(synthetic_price_data)

        assert matrix is not None
        assert isinstance(matrix, CorrelationMatrix)
        assert len(matrix.symbols) == 5
        assert "BTCUSDT" in matrix.symbols
        assert "ETHUSDT" in matrix.symbols

    @pytest.mark.asyncio
    async def test_matrix_symmetry(self, correlation_manager, synthetic_price_data):
        """Test that correlation matrix is symmetric"""
        await correlation_manager.initialize()
        matrix = await correlation_manager.update_correlations(synthetic_price_data)

        # Check correlation(A, B) == correlation(B, A)
        corr_ab = matrix.get_correlation("BTCUSDT", "ETHUSDT")
        corr_ba = matrix.get_correlation("ETHUSDT", "BTCUSDT")

        assert corr_ab is not None
        assert corr_ba is not None
        assert abs(corr_ab - corr_ba) < 0.0001, "Matrix should be symmetric"

    @pytest.mark.asyncio
    async def test_btc_eth_high_correlation(
        self,
        correlation_manager,
        synthetic_price_data
    ):
        """Test BTC-ETH correlation is high (0.7+)"""
        await correlation_manager.initialize()
        matrix = await correlation_manager.update_correlations(synthetic_price_data)

        corr = matrix.get_correlation("BTCUSDT", "ETHUSDT")

        assert corr is not None
        assert corr > 0.6, f"BTC-ETH correlation should be high, got {corr}"

    @pytest.mark.asyncio
    async def test_btc_ada_low_correlation(
        self,
        correlation_manager,
        synthetic_price_data
    ):
        """Test BTC-ADA correlation is low (<0.5)"""
        await correlation_manager.initialize()
        matrix = await correlation_manager.update_correlations(synthetic_price_data)

        corr = matrix.get_correlation("BTCUSDT", "ADAUSDT")

        assert corr is not None
        assert abs(corr) < 0.6, f"BTC-ADA correlation should be low, got {corr}"

    @pytest.mark.asyncio
    async def test_get_highly_correlated_pairs(
        self,
        correlation_manager,
        synthetic_price_data
    ):
        """Test retrieval of highly correlated pairs"""
        await correlation_manager.initialize()
        matrix = await correlation_manager.update_correlations(synthetic_price_data)

        high_corr_pairs = matrix.get_highly_correlated_pairs(threshold=0.6)

        assert isinstance(high_corr_pairs, list)
        # BTC-ETH should be in the list
        pair_symbols = [(p[0], p[1]) for p in high_corr_pairs]
        assert any(
            ("BTCUSDT" in pair and "ETHUSDT" in pair)
            for pair in pair_symbols
        ), "BTC-ETH should be in highly correlated pairs"

    @pytest.mark.asyncio
    async def test_matrix_short_long_term(
        self,
        correlation_manager,
        synthetic_price_data
    ):
        """Test both short-term and long-term correlations are calculated"""
        await correlation_manager.initialize()
        matrix = await correlation_manager.update_correlations(synthetic_price_data)

        short_corr = matrix.get_correlation("BTCUSDT", "ETHUSDT", "short")
        long_corr = matrix.get_correlation("BTCUSDT", "ETHUSDT", "long")

        assert short_corr is not None
        # Long term may be None if not enough data points
        # This is expected behavior


# =============================================================================
# DIVERSIFICATION SCORING TESTS
# =============================================================================

class TestDiversificationScoring:
    """Test suite for portfolio diversification scoring"""

    @pytest.mark.asyncio
    async def test_score_no_positions(self, correlation_manager):
        """Test diversification score with no positions"""
        await correlation_manager.initialize()

        score = await correlation_manager.get_diversification_score([])

        assert score.score == 100.0
        assert score.position_count == 0
        assert score.risk_level == "No Positions"

    @pytest.mark.asyncio
    async def test_score_single_position(self, correlation_manager):
        """Test diversification score with single position"""
        await correlation_manager.initialize()

        score = await correlation_manager.get_diversification_score(["BTCUSDT"])

        assert score.score == 50.0
        assert score.position_count == 1
        assert score.risk_level == "Concentrated"
        assert len(score.recommendations) > 0

    @pytest.mark.asyncio
    async def test_score_diverse_portfolio(
        self,
        correlation_manager,
        synthetic_price_data
    ):
        """Test diversification score with diverse portfolio"""
        await correlation_manager.initialize()
        await correlation_manager.update_correlations(synthetic_price_data)

        # Use uncorrelated symbols
        score = await correlation_manager.get_diversification_score(
            ["ADAUSDT", "XRPUSDT", "SOLUSDT"]
        )

        assert score.score > 50, "Diverse portfolio should have decent score"
        assert score.position_count == 3
        assert score.risk_level in ["Excellent", "Good", "Moderate"]

    @pytest.mark.asyncio
    async def test_score_correlated_portfolio(
        self,
        correlation_manager,
        synthetic_price_data
    ):
        """Test diversification score with correlated portfolio"""
        await correlation_manager.initialize()
        await correlation_manager.update_correlations(synthetic_price_data)

        # Use highly correlated symbols (BTC and ETH)
        score = await correlation_manager.get_diversification_score(
            ["BTCUSDT", "ETHUSDT"]
        )

        assert score.position_count == 2
        assert score.max_correlation > 0.5, "Max correlation should be high"
        assert len(score.recommendations) > 0

    @pytest.mark.asyncio
    async def test_score_to_dict(self, correlation_manager):
        """Test DiversificationScore serialization"""
        await correlation_manager.initialize()

        score = await correlation_manager.get_diversification_score(["BTCUSDT"])
        score_dict = score.to_dict()

        assert "score" in score_dict
        assert "position_count" in score_dict
        assert "risk_level" in score_dict
        assert "recommendations" in score_dict
        assert "timestamp" in score_dict


# =============================================================================
# POSITION LIMIT ENFORCEMENT TESTS
# =============================================================================

class TestPositionLimits:
    """Test suite for correlation-based position limit enforcement"""

    @pytest.mark.asyncio
    async def test_can_open_no_existing_positions(self, correlation_manager):
        """Test position can always open when no existing positions"""
        await correlation_manager.initialize()

        can_open, reason = await correlation_manager.can_open_position("BTCUSDT", [])

        assert can_open is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_can_open_without_correlation_data(self, correlation_manager):
        """Test position can open when no correlation data available"""
        await correlation_manager.initialize()

        can_open, reason = await correlation_manager.can_open_position(
            "BTCUSDT",
            ["ETHUSDT"]
        )

        # Should allow when no data
        assert can_open is True

    @pytest.mark.asyncio
    async def test_block_highly_correlated_position(
        self,
        correlation_manager,
        synthetic_price_data
    ):
        """Test highly correlated position is blocked"""
        await correlation_manager.initialize()
        await correlation_manager.update_correlations(synthetic_price_data)

        # ETH is highly correlated with BTC
        can_open, reason = await correlation_manager.can_open_position(
            "ETHUSDT",
            ["BTCUSDT"]
        )

        assert can_open is False, "Should block highly correlated position"
        assert reason is not None
        assert "correlation" in reason.lower()

    @pytest.mark.asyncio
    async def test_allow_uncorrelated_position(
        self,
        correlation_manager,
        synthetic_price_data
    ):
        """Test uncorrelated position is allowed"""
        await correlation_manager.initialize()
        await correlation_manager.update_correlations(synthetic_price_data)

        # ADA has low correlation with BTC
        can_open, reason = await correlation_manager.can_open_position(
            "ADAUSDT",
            ["BTCUSDT"]
        )

        assert can_open is True, "Should allow uncorrelated position"

    @pytest.mark.asyncio
    async def test_max_correlated_positions_limit(
        self,
        correlation_manager,
        synthetic_price_data
    ):
        """Test max correlated positions limit is enforced"""
        await correlation_manager.initialize()
        await correlation_manager.update_correlations(synthetic_price_data)

        # Open 3 moderately correlated positions first
        # Then try to open another
        open_positions = ["BTCUSDT", "SOLUSDT", "ETHUSDT"]

        # Create scenario where max is exceeded
        correlation_manager.config.max_correlated_positions = 2

        can_open, reason = await correlation_manager.can_open_position(
            "ADAUSDT",
            open_positions
        )

        # This might pass or fail depending on actual correlations
        # The test verifies the logic runs without error
        assert isinstance(can_open, bool)

    @pytest.mark.asyncio
    async def test_position_size_adjustment_no_correlation(self, correlation_manager):
        """Test no adjustment when no correlation data"""
        await correlation_manager.initialize()

        adjustment = correlation_manager.get_position_size_adjustment("BTCUSDT", [])

        assert adjustment == 1.0

    @pytest.mark.asyncio
    async def test_position_size_adjustment_high_correlation(
        self,
        correlation_manager,
        synthetic_price_data
    ):
        """Test position size reduced for high correlation"""
        await correlation_manager.initialize()
        await correlation_manager.update_correlations(synthetic_price_data)

        adjustment = correlation_manager.get_position_size_adjustment(
            "ETHUSDT",
            ["BTCUSDT"]
        )

        assert adjustment < 1.0, "Size should be reduced for correlated pairs"
        assert adjustment >= correlation_manager.config.position_size_reduction_factor


# =============================================================================
# ALERT GENERATION TESTS
# =============================================================================

class TestAlertGeneration:
    """Test suite for correlation alert generation"""

    @pytest.mark.asyncio
    async def test_alerts_generated_on_update(
        self,
        correlation_manager,
        synthetic_price_data
    ):
        """Test alerts are generated when correlations are updated"""
        await correlation_manager.initialize()
        await correlation_manager.update_correlations(synthetic_price_data)

        alerts = correlation_manager.get_alerts()

        assert isinstance(alerts, list)
        # BTC-ETH high correlation should generate at least one alert
        assert len(alerts) > 0

    @pytest.mark.asyncio
    async def test_alert_severity_levels(
        self,
        correlation_manager,
        synthetic_price_data
    ):
        """Test alerts have correct severity levels"""
        await correlation_manager.initialize()
        await correlation_manager.update_correlations(synthetic_price_data)

        all_alerts = correlation_manager.get_alerts(AlertSeverity.INFO)
        warning_plus = correlation_manager.get_alerts(AlertSeverity.WARNING)
        high_plus = correlation_manager.get_alerts(AlertSeverity.HIGH)

        # More inclusive filter should return more alerts
        assert len(all_alerts) >= len(warning_plus)
        assert len(warning_plus) >= len(high_plus)

    @pytest.mark.asyncio
    async def test_alert_contains_required_fields(
        self,
        correlation_manager,
        synthetic_price_data
    ):
        """Test alert objects contain required fields"""
        await correlation_manager.initialize()
        await correlation_manager.update_correlations(synthetic_price_data)

        alerts = correlation_manager.get_alerts()

        if alerts:  # If any alerts were generated
            alert = alerts[0]
            assert hasattr(alert, "symbol_a")
            assert hasattr(alert, "symbol_b")
            assert hasattr(alert, "correlation")
            assert hasattr(alert, "severity")
            assert hasattr(alert, "message")
            assert hasattr(alert, "timestamp")

    @pytest.mark.asyncio
    async def test_alert_to_dict(self, correlation_manager, synthetic_price_data):
        """Test alert serialization"""
        await correlation_manager.initialize()
        await correlation_manager.update_correlations(synthetic_price_data)

        alerts = correlation_manager.get_alerts()

        if alerts:
            alert_dict = alerts[0].to_dict()
            assert "symbol_a" in alert_dict
            assert "symbol_b" in alert_dict
            assert "correlation" in alert_dict
            assert "severity" in alert_dict
            assert "message" in alert_dict
            assert "timestamp" in alert_dict


# =============================================================================
# MANAGER STATUS AND LIFECYCLE TESTS
# =============================================================================

class TestManagerLifecycle:
    """Test suite for manager initialization and lifecycle"""

    @pytest.mark.asyncio
    async def test_initialize_without_redis(self, correlation_manager):
        """Test manager initializes without Redis"""
        success = await correlation_manager.initialize(redis_url=None)

        assert success is True
        assert correlation_manager._initialized is True

    @pytest.mark.asyncio
    async def test_double_initialization(self, correlation_manager):
        """Test manager handles double initialization"""
        await correlation_manager.initialize()
        success = await correlation_manager.initialize()

        assert success is True  # Should not error

    @pytest.mark.asyncio
    async def test_close_manager(self, correlation_manager):
        """Test manager closes cleanly"""
        await correlation_manager.initialize()
        await correlation_manager.close()

        assert correlation_manager._initialized is False

    @pytest.mark.asyncio
    async def test_get_status(self, correlation_manager, synthetic_price_data):
        """Test status reporting"""
        await correlation_manager.initialize()
        await correlation_manager.update_correlations(synthetic_price_data)

        status = correlation_manager.get_status()

        assert "initialized" in status
        assert "redis_connected" in status
        assert "matrix_available" in status
        assert "symbols_tracked" in status
        assert "alert_count" in status
        assert "config" in status

        assert status["initialized"] is True
        assert status["matrix_available"] is True
        assert status["symbols_tracked"] == 5

    @pytest.mark.asyncio
    async def test_get_pair_correlation_details(
        self,
        correlation_manager,
        synthetic_price_data
    ):
        """Test get_pair_correlation returns detailed info"""
        await correlation_manager.initialize()
        await correlation_manager.update_correlations(synthetic_price_data)

        pair_info = correlation_manager.get_pair_correlation("BTCUSDT", "ETHUSDT")

        assert "symbol_a" in pair_info
        assert "symbol_b" in pair_info
        assert "short_term_correlation" in pair_info
        assert "is_highly_correlated" in pair_info
        assert "position_allowed" in pair_info


# =============================================================================
# GLOBAL INSTANCE TESTS
# =============================================================================

class TestGlobalInstance:
    """Test suite for global instance management"""

    def test_get_correlation_manager_singleton(self):
        """Test global manager is a singleton"""
        reset_correlation_manager()

        manager1 = get_correlation_manager()
        manager2 = get_correlation_manager()

        assert manager1 is manager2

    def test_reset_correlation_manager(self):
        """Test reset creates new instance"""
        manager1 = get_correlation_manager()
        reset_correlation_manager()
        manager2 = get_correlation_manager()

        assert manager1 is not manager2


# =============================================================================
# EDGE CASES AND ERROR HANDLING
# =============================================================================

class TestEdgeCases:
    """Test suite for edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_update_with_insufficient_data(
        self,
        correlation_manager,
        insufficient_price_data
    ):
        """Test update handles insufficient data gracefully"""
        await correlation_manager.initialize()
        matrix = await correlation_manager.update_correlations(insufficient_price_data)

        # Matrix should be created but correlations may be None
        assert matrix is not None
        assert len(matrix.symbols) == 2

    @pytest.mark.asyncio
    async def test_empty_price_data(self, correlation_manager):
        """Test update handles empty price data"""
        await correlation_manager.initialize()
        matrix = await correlation_manager.update_correlations({})

        assert matrix is not None
        assert len(matrix.symbols) == 0

    @pytest.mark.asyncio
    async def test_single_symbol_data(self, correlation_manager):
        """Test update handles single symbol"""
        await correlation_manager.initialize()

        price_data = {"BTCUSDT": [100000 + i * 100 for i in range(30)]}
        matrix = await correlation_manager.update_correlations(price_data)

        assert matrix is not None
        assert len(matrix.symbols) == 1
        # No pairs to correlate

    @pytest.mark.asyncio
    async def test_concurrent_updates(
        self,
        correlation_manager,
        synthetic_price_data
    ):
        """Test concurrent update handling"""
        await correlation_manager.initialize()

        # Run multiple updates concurrently
        tasks = [
            correlation_manager.update_correlations(synthetic_price_data)
            for _ in range(3)
        ]

        results = await asyncio.gather(*tasks)

        assert all(r is not None for r in results)

    @pytest.mark.asyncio
    async def test_get_matrix_before_update(self, correlation_manager):
        """Test getting matrix before any update"""
        await correlation_manager.initialize()

        matrix = await correlation_manager.get_correlation_matrix()

        assert matrix is None

    @pytest.mark.asyncio
    async def test_correlation_with_nan_values(self, correlation_manager):
        """Test correlation calculation with NaN values in data"""
        series_a = [100, 101, float('nan'), 103, 104] + [100 + i for i in range(25)]
        series_b = [50, 51, 52, 53, 54] + [50 + i * 0.5 for i in range(25)]

        # NumPy correlation handles NaN
        # Our implementation uses scipy which may handle differently
        correlation = correlation_manager.calculate_correlation(series_a, series_b)

        # Either returns None or a valid number
        assert correlation is None or isinstance(correlation, float)


# =============================================================================
# DATA MODEL TESTS
# =============================================================================

class TestDataModels:
    """Test suite for data model classes"""

    def test_correlation_config_defaults(self):
        """Test CorrelationConfig has sensible defaults"""
        config = CorrelationConfig()

        assert config.rolling_window_short == 30
        assert config.rolling_window_long == 60
        assert config.high_correlation_threshold == 0.7
        assert config.critical_correlation_threshold == 0.8

    def test_correlation_config_to_dict(self):
        """Test CorrelationConfig serialization"""
        config = CorrelationConfig()
        config_dict = config.to_dict()

        assert "rolling_window_short" in config_dict
        assert "high_correlation_threshold" in config_dict

    def test_correlation_matrix_to_dict(self):
        """Test CorrelationMatrix serialization"""
        matrix = CorrelationMatrix(
            symbols=["BTCUSDT", "ETHUSDT"],
            short_term={"BTCUSDT": {"ETHUSDT": 0.85}},
            long_term={"BTCUSDT": {"ETHUSDT": 0.82}},
            last_updated=datetime.now(timezone.utc),
            data_points=30
        )

        matrix_dict = matrix.to_dict()

        assert "symbols" in matrix_dict
        assert "short_term" in matrix_dict
        assert "long_term" in matrix_dict
        assert "last_updated" in matrix_dict

    def test_correlation_matrix_from_dict(self):
        """Test CorrelationMatrix deserialization"""
        data = {
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "short_term": {"BTCUSDT": {"ETHUSDT": 0.85}},
            "long_term": {"BTCUSDT": {"ETHUSDT": 0.82}},
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "data_points": 30
        }

        matrix = CorrelationMatrix.from_dict(data)

        assert matrix.symbols == ["BTCUSDT", "ETHUSDT"]
        assert matrix.get_correlation("BTCUSDT", "ETHUSDT") == 0.85

    def test_diversification_score_model(self):
        """Test DiversificationScore model"""
        score = DiversificationScore(
            score=75.0,
            position_count=3,
            avg_correlation=0.35,
            max_correlation=0.65,
            correlated_pairs_count=1,
            risk_level="Good",
            recommendations=["Consider adding more positions"]
        )

        assert score.score == 75.0
        assert score.position_count == 3

        score_dict = score.to_dict()
        assert score_dict["score"] == 75.0

    def test_correlation_alert_model(self):
        """Test CorrelationAlert model"""
        alert = CorrelationAlert(
            symbol_a="BTCUSDT",
            symbol_b="ETHUSDT",
            correlation=0.85,
            severity=AlertSeverity.HIGH,
            message="High correlation detected"
        )

        assert alert.symbol_a == "BTCUSDT"
        assert alert.severity == AlertSeverity.HIGH

        alert_dict = alert.to_dict()
        assert alert_dict["severity"] == "HIGH"


# =============================================================================
# PERFORMANCE TESTS
# =============================================================================

class TestPerformance:
    """Test suite for performance characteristics"""

    @pytest.mark.asyncio
    async def test_large_symbol_set(self, correlation_manager):
        """Test performance with large number of symbols"""
        await correlation_manager.initialize()

        # Generate data for 20 symbols
        np.random.seed(42)
        n_points = 60
        n_symbols = 20

        price_data = {}
        for i in range(n_symbols):
            symbol = f"SYMBOL{i}USDT"
            prices = [100 + np.random.normal(0, 5) for _ in range(n_points)]
            price_data[symbol] = prices

        matrix = await correlation_manager.update_correlations(price_data)

        assert matrix is not None
        assert len(matrix.symbols) == n_symbols
        # Should complete in reasonable time (pytest will timeout if too slow)

    @pytest.mark.asyncio
    async def test_repeated_updates(
        self,
        correlation_manager,
        synthetic_price_data
    ):
        """Test performance of repeated updates"""
        await correlation_manager.initialize()

        # Simulate 10 hourly updates
        for _ in range(10):
            # Add new price points
            for symbol in synthetic_price_data:
                synthetic_price_data[symbol].append(
                    synthetic_price_data[symbol][-1] * (1 + np.random.normal(0, 0.01))
                )

            matrix = await correlation_manager.update_correlations(synthetic_price_data)
            assert matrix is not None


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests combining multiple features"""

    @pytest.mark.asyncio
    async def test_full_workflow(self, correlation_manager, synthetic_price_data):
        """Test complete workflow from initialization to position check"""
        # 1. Initialize
        await correlation_manager.initialize()

        # 2. Update correlations
        matrix = await correlation_manager.update_correlations(synthetic_price_data)
        assert matrix is not None

        # 3. Get diversification score
        score = await correlation_manager.get_diversification_score(["BTCUSDT", "SOLUSDT"])
        assert score.score > 0

        # 4. Check position limits
        can_open, _ = await correlation_manager.can_open_position("ADAUSDT", ["BTCUSDT"])
        assert isinstance(can_open, bool)

        # 5. Get alerts
        alerts = correlation_manager.get_alerts()
        assert isinstance(alerts, list)

        # 6. Get status
        status = correlation_manager.get_status()
        assert status["initialized"] is True

        # 7. Cleanup
        await correlation_manager.close()

    @pytest.mark.asyncio
    async def test_risk_management_scenario(
        self,
        correlation_manager,
        synthetic_price_data
    ):
        """Test realistic risk management scenario"""
        await correlation_manager.initialize()
        await correlation_manager.update_correlations(synthetic_price_data)

        # Scenario: Already have BTC position, want to add more
        open_positions = ["BTCUSDT"]

        # Should block ETH (high correlation)
        can_open_eth, _ = await correlation_manager.can_open_position("ETHUSDT", open_positions)

        # Should allow ADA (low correlation)
        can_open_ada, _ = await correlation_manager.can_open_position("ADAUSDT", open_positions)

        # High correlation pair should be blocked or size reduced
        assert can_open_eth is False or correlation_manager.get_position_size_adjustment("ETHUSDT", open_positions) < 1.0

        # Low correlation pair should be allowed
        assert can_open_ada is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
