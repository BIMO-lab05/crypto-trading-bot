"""
Sector Exposure Manager Tests
Purpose: Comprehensive tests for Phase 3.1 Sector Exposure Analysis

Created: 2025-12-11
Target Coverage: >85%

Test Categories:
1. Sector classification accuracy
2. Exposure calculation
3. Position limit enforcement
4. Beta calculation
5. Sector rotation detection
6. Integration tests
"""

import pytest
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List

# Import modules to test
from app.risk.sector_exposure import (
    SectorExposureManager,
    SectorExposureConfig,
    CryptoSector,
    SectorPosition,
    SectorExposure,
    SectorRotationSignal,
    SectorAnalysisResult,
    SECTOR_MAPPING,
    SECTOR_CHARACTERISTICS,
    get_sector_exposure_manager,
    reset_sector_exposure_manager,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def sector_config():
    """Create test sector exposure configuration"""
    return SectorExposureConfig(
        default_max_sector_pct=40.0,
        sector_limits={
            "layer_1": 50.0,
            "layer_2": 40.0,
            "defi": 35.0,
            "meme": 15.0,
            "infra": 30.0,
            "exchange": 25.0,
            "gaming": 25.0,
            "privacy": 20.0,
            "ai": 30.0,
            "other": 20.0,
        },
        min_sectors_for_diversification=3,
        beta_lookback_days=30,
        rotation_threshold=0.15,
    )


@pytest.fixture
def sector_manager(sector_config):
    """Create fresh sector exposure manager for each test"""
    reset_sector_exposure_manager()
    manager = SectorExposureManager(sector_config)
    return manager


@pytest.fixture
def sample_positions():
    """Create sample positions for testing"""
    return [
        SectorPosition(
            symbol="BTCUSDT",
            position_value=40000,
            risk_pct=4.0,
            entry_price=100000,
            current_price=102000,
            sector=CryptoSector.LAYER_1,
            unrealized_pnl_pct=2.0
        ),
        SectorPosition(
            symbol="ETHUSDT",
            position_value=30000,
            risk_pct=3.0,
            entry_price=3500,
            current_price=3600,
            sector=CryptoSector.LAYER_1,
            unrealized_pnl_pct=2.86
        ),
        SectorPosition(
            symbol="ARBUSDT",
            position_value=10000,
            risk_pct=1.5,
            entry_price=1.2,
            current_price=1.25,
            sector=CryptoSector.LAYER_2,
            unrealized_pnl_pct=4.17
        ),
        SectorPosition(
            symbol="UNIUSDT",
            position_value=8000,
            risk_pct=1.0,
            entry_price=10,
            current_price=11,
            sector=CryptoSector.DEFI,
            unrealized_pnl_pct=10.0
        ),
        SectorPosition(
            symbol="DOGEUSDT",
            position_value=2000,
            risk_pct=0.5,
            entry_price=0.1,
            current_price=0.095,
            sector=CryptoSector.MEME,
            unrealized_pnl_pct=-5.0
        ),
    ]


@pytest.fixture
def concentrated_positions():
    """Create positions concentrated in one sector"""
    return [
        SectorPosition(
            symbol="BTCUSDT",
            position_value=50000,
            risk_pct=5.0,
            entry_price=100000,
            current_price=102000,
            sector=CryptoSector.LAYER_1,
            unrealized_pnl_pct=2.0
        ),
        SectorPosition(
            symbol="ETHUSDT",
            position_value=40000,
            risk_pct=4.0,
            entry_price=3500,
            current_price=3600,
            sector=CryptoSector.LAYER_1,
            unrealized_pnl_pct=2.86
        ),
    ]


# =============================================================================
# SECTOR CLASSIFICATION TESTS
# =============================================================================

class TestSectorClassification:
    """Test suite for sector classification accuracy"""

    def test_get_sector_btc(self, sector_manager):
        """Test BTC is classified as Layer 1"""
        sector = sector_manager.get_sector("BTCUSDT")
        assert sector == CryptoSector.LAYER_1

    def test_get_sector_eth(self, sector_manager):
        """Test ETH is classified as Layer 1"""
        sector = sector_manager.get_sector("ETHUSDT")
        assert sector == CryptoSector.LAYER_1

    def test_get_sector_arb(self, sector_manager):
        """Test ARB is classified as Layer 2"""
        sector = sector_manager.get_sector("ARBUSDT")
        assert sector == CryptoSector.LAYER_2

    def test_get_sector_uni(self, sector_manager):
        """Test UNI is classified as DeFi"""
        sector = sector_manager.get_sector("UNIUSDT")
        assert sector == CryptoSector.DEFI

    def test_get_sector_doge(self, sector_manager):
        """Test DOGE is classified as Meme"""
        sector = sector_manager.get_sector("DOGEUSDT")
        assert sector == CryptoSector.MEME

    def test_get_sector_link(self, sector_manager):
        """Test LINK is classified as Infrastructure"""
        sector = sector_manager.get_sector("LINKUSDT")
        assert sector == CryptoSector.INFRASTRUCTURE

    def test_get_sector_bnb(self, sector_manager):
        """Test BNB is classified as Exchange"""
        sector = sector_manager.get_sector("BNBUSDT")
        assert sector == CryptoSector.EXCHANGE

    def test_get_sector_unknown(self, sector_manager):
        """Test unknown symbol defaults to OTHER"""
        sector = sector_manager.get_sector("UNKNOWNUSDT")
        assert sector == CryptoSector.OTHER

    def test_get_sector_without_usdt_suffix(self, sector_manager):
        """Test sector lookup works without USDT suffix"""
        sector = sector_manager.get_sector("BTC")
        assert sector == CryptoSector.LAYER_1

    def test_set_custom_sector(self, sector_manager):
        """Test setting custom sector classification"""
        sector_manager.set_sector("CUSTOMUSDT", CryptoSector.AI)
        sector = sector_manager.get_sector("CUSTOMUSDT")
        assert sector == CryptoSector.AI

    def test_custom_sector_overrides_default(self, sector_manager):
        """Test custom sector overrides built-in mapping"""
        # BTC is normally Layer 1, override to DeFi for test
        sector_manager.set_sector("BTCUSDT", CryptoSector.DEFI)
        sector = sector_manager.get_sector("BTCUSDT")
        assert sector == CryptoSector.DEFI


# =============================================================================
# SECTOR CHARACTERISTICS TESTS
# =============================================================================

class TestSectorCharacteristics:
    """Test suite for sector characteristics"""

    def test_get_sector_characteristics_layer1(self, sector_manager):
        """Test Layer 1 characteristics"""
        chars = sector_manager.get_sector_characteristics(CryptoSector.LAYER_1)

        assert "name" in chars
        assert "volatility_factor" in chars
        assert "correlation_to_btc" in chars
        assert "max_exposure_pct" in chars
        assert "risk_weight" in chars

        assert chars["volatility_factor"] == 1.0  # Base volatility
        assert chars["max_exposure_pct"] >= 40.0  # Higher limit for L1

    def test_get_sector_characteristics_meme(self, sector_manager):
        """Test Meme sector has higher volatility"""
        chars = sector_manager.get_sector_characteristics(CryptoSector.MEME)

        assert chars["volatility_factor"] > 2.0  # High volatility
        assert chars["risk_weight"] > 1.5  # High risk

    def test_get_sector_max_exposure(self, sector_manager):
        """Test getting max exposure for sectors"""
        l1_max = sector_manager.get_sector_max_exposure(CryptoSector.LAYER_1)
        meme_max = sector_manager.get_sector_max_exposure(CryptoSector.MEME)

        assert l1_max > meme_max  # L1 should allow more exposure than memes

    def test_get_all_sectors(self, sector_manager):
        """Test getting all sectors list"""
        sectors = sector_manager.get_all_sectors()

        assert len(sectors) == len(CryptoSector)
        assert all("sector" in s for s in sectors)
        assert all("max_exposure_pct" in s for s in sectors)


# =============================================================================
# EXPOSURE CALCULATION TESTS
# =============================================================================

class TestExposureCalculation:
    """Test suite for sector exposure calculations"""

    def test_calculate_sector_exposure_basic(
        self,
        sector_manager,
        sample_positions
    ):
        """Test basic sector exposure calculation"""
        portfolio_value = 100000
        analysis = sector_manager.calculate_sector_exposure(
            sample_positions,
            portfolio_value
        )

        assert isinstance(analysis, SectorAnalysisResult)
        assert analysis.total_portfolio_value == portfolio_value
        assert analysis.sector_count > 0

    def test_exposure_percentages_sum_correctly(
        self,
        sector_manager,
        sample_positions
    ):
        """Test that exposure percentages sum to 100% (or less)"""
        portfolio_value = sum(p.position_value for p in sample_positions)
        analysis = sector_manager.calculate_sector_exposure(
            sample_positions,
            portfolio_value
        )

        total_exposure = sum(
            e.exposure_pct for e in analysis.sector_exposures
            if e.position_count > 0
        )

        # Should sum to approximately 100%
        assert 99.0 <= total_exposure <= 101.0

    def test_layer1_exposure_calculated(
        self,
        sector_manager,
        sample_positions
    ):
        """Test Layer 1 exposure is calculated correctly"""
        portfolio_value = 100000
        analysis = sector_manager.calculate_sector_exposure(
            sample_positions,
            portfolio_value
        )

        l1_exposure = next(
            (e for e in analysis.sector_exposures if e.sector == CryptoSector.LAYER_1),
            None
        )

        assert l1_exposure is not None
        # BTC (40k) + ETH (30k) = 70k = 70% of 100k
        assert l1_exposure.exposure_pct == 70.0
        assert l1_exposure.position_count == 2
        assert "BTCUSDT" in l1_exposure.positions
        assert "ETHUSDT" in l1_exposure.positions

    def test_over_limit_detection(
        self,
        sector_manager,
        concentrated_positions
    ):
        """Test detection of over-limit sectors"""
        # BTC + ETH = 90k out of 90k = 100% in L1
        portfolio_value = sum(p.position_value for p in concentrated_positions)

        analysis = sector_manager.calculate_sector_exposure(
            concentrated_positions,
            portfolio_value
        )

        assert len(analysis.over_limit_sectors) > 0
        assert "layer_1" in analysis.over_limit_sectors

    def test_diversification_rating_excellent(self, sector_manager):
        """Test excellent diversification rating"""
        # Create well-diversified positions
        positions = [
            SectorPosition(
                symbol="BTCUSDT", position_value=10000, risk_pct=1.0,
                entry_price=100000, current_price=100000,
                sector=CryptoSector.LAYER_1, unrealized_pnl_pct=0
            ),
            SectorPosition(
                symbol="ARBUSDT", position_value=10000, risk_pct=1.0,
                entry_price=1.0, current_price=1.0,
                sector=CryptoSector.LAYER_2, unrealized_pnl_pct=0
            ),
            SectorPosition(
                symbol="UNIUSDT", position_value=10000, risk_pct=1.0,
                entry_price=10, current_price=10,
                sector=CryptoSector.DEFI, unrealized_pnl_pct=0
            ),
            SectorPosition(
                symbol="LINKUSDT", position_value=10000, risk_pct=1.0,
                entry_price=20, current_price=20,
                sector=CryptoSector.INFRASTRUCTURE, unrealized_pnl_pct=0
            ),
            SectorPosition(
                symbol="BNBUSDT", position_value=10000, risk_pct=1.0,
                entry_price=500, current_price=500,
                sector=CryptoSector.EXCHANGE, unrealized_pnl_pct=0
            ),
        ]

        analysis = sector_manager.calculate_sector_exposure(positions, 50000)

        assert analysis.diversification_rating in ["EXCELLENT", "GOOD"]
        assert analysis.sector_count >= 4

    def test_diversification_rating_concentrated(
        self,
        sector_manager,
        concentrated_positions
    ):
        """Test concentrated diversification rating"""
        portfolio_value = sum(p.position_value for p in concentrated_positions)

        analysis = sector_manager.calculate_sector_exposure(
            concentrated_positions,
            portfolio_value
        )

        assert analysis.diversification_rating in ["CONCENTRATED", "POOR"]

    def test_empty_positions(self, sector_manager):
        """Test handling of empty positions list"""
        analysis = sector_manager.calculate_sector_exposure([], 100000)

        assert analysis.sector_count == 0
        assert len(analysis.recommendations) > 0

    def test_zero_portfolio_value(self, sector_manager, sample_positions):
        """Test handling of zero portfolio value"""
        analysis = sector_manager.calculate_sector_exposure(sample_positions, 0)

        assert analysis.diversification_rating == "N/A"


# =============================================================================
# POSITION CHECK TESTS
# =============================================================================

class TestPositionChecks:
    """Test suite for position limit checks"""

    def test_can_add_position_within_limit(
        self,
        sector_manager,
        sample_positions
    ):
        """Test can add position when within limits"""
        can_add, reason = sector_manager.can_add_position(
            "AAVEUSDT",  # DeFi
            sample_positions,
            portfolio_value=100000,
            proposed_value=5000
        )

        assert can_add is True
        assert reason is None

    def test_cannot_add_position_exceeds_limit(
        self,
        sector_manager,
        concentrated_positions
    ):
        """Test cannot add position when sector limit exceeded"""
        portfolio_value = sum(p.position_value for p in concentrated_positions)

        # Try to add more L1 exposure
        can_add, reason = sector_manager.can_add_position(
            "SOLUSDT",  # Layer 1
            concentrated_positions,
            portfolio_value=portfolio_value,
            proposed_value=10000
        )

        assert can_add is False
        assert reason is not None
        assert "limit" in reason.lower() or "exceed" in reason.lower()

    def test_can_add_to_empty_portfolio(self, sector_manager):
        """Test can always add to empty portfolio"""
        can_add, reason = sector_manager.can_add_position(
            "BTCUSDT",
            [],
            portfolio_value=100000,
            proposed_value=50000
        )

        assert can_add is True

    def test_get_position_size_adjustment_low_exposure(self, sector_manager):
        """Test no adjustment when sector has low exposure"""
        positions = [
            SectorPosition(
                symbol="BTCUSDT", position_value=10000, risk_pct=1.0,
                entry_price=100000, current_price=100000,
                sector=CryptoSector.LAYER_1, unrealized_pnl_pct=0
            ),
        ]

        multiplier, details = sector_manager.get_position_size_adjustment(
            "ETHUSDT",
            positions,
            portfolio_value=100000
        )

        assert multiplier >= 0.8  # Should be close to 1.0

    def test_get_position_size_adjustment_high_exposure(
        self,
        sector_manager,
        concentrated_positions
    ):
        """Test adjustment when sector has high exposure"""
        portfolio_value = sum(p.position_value for p in concentrated_positions)

        multiplier, details = sector_manager.get_position_size_adjustment(
            "SOLUSDT",
            concentrated_positions,
            portfolio_value=portfolio_value
        )

        # Should be significantly reduced due to high L1 exposure
        assert multiplier < 1.0

    def test_meme_sector_higher_risk_adjustment(self, sector_manager):
        """Test meme sector gets additional risk adjustment"""
        multiplier, details = sector_manager.get_position_size_adjustment(
            "PEPEUSDT",  # Meme coin
            [],
            portfolio_value=100000
        )

        # Meme coins should have reduced multiplier due to high risk weight
        # Even with empty portfolio, risk weight affects it
        assert details["risk_weight"] > 1.5


# =============================================================================
# BETA CALCULATION TESTS
# =============================================================================

class TestBetaCalculation:
    """Test suite for beta calculations"""

    def test_beta_default_when_no_data(self, sector_manager):
        """Test beta returns default when no price data"""
        beta = sector_manager.calculate_beta("BTCUSDT")

        # Should return sector default
        assert beta is not None
        assert isinstance(beta, float)

    def test_update_price_history(self, sector_manager):
        """Test updating price history"""
        np.random.seed(42)
        price_data = {
            "BTCUSDT": [100000 + i * 100 + np.random.normal(0, 500) for i in range(30)],
            "ETHUSDT": [3500 + i * 10 + np.random.normal(0, 50) for i in range(30)],
        }

        sector_manager.update_price_history(price_data)

        assert len(sector_manager._price_history["BTCUSDT"]) == 30
        assert len(sector_manager._price_history["ETHUSDT"]) == 30

    def test_beta_with_price_data(self, sector_manager):
        """Test beta calculation with actual price data"""
        np.random.seed(42)

        # Generate correlated price data
        n_points = 50
        btc_returns = np.random.normal(0.001, 0.02, n_points)
        btc_prices = [100000]
        for ret in btc_returns:
            btc_prices.append(btc_prices[-1] * (1 + ret))

        # ETH follows BTC with beta ~1.2
        eth_prices = [3500]
        for ret in btc_returns:
            eth_return = 1.2 * ret + np.random.normal(0, 0.01)
            eth_prices.append(eth_prices[-1] * (1 + eth_return))

        price_data = {
            "BTCUSDT": btc_prices,
            "ETHUSDT": eth_prices,
        }

        sector_manager.update_price_history(price_data)

        beta = sector_manager.calculate_beta("ETHUSDT", "BTCUSDT")

        # Beta should be positive and somewhat close to 1.2
        assert beta is not None
        assert beta > 0.5

    def test_calculate_sector_betas(self, sector_manager):
        """Test calculating betas for all sectors"""
        betas = sector_manager.calculate_sector_betas()

        assert isinstance(betas, dict)
        assert len(betas) > 0
        # All betas should be numbers
        assert all(isinstance(v, (int, float)) for v in betas.values())


# =============================================================================
# SECTOR ROTATION TESTS
# =============================================================================

class TestSectorRotation:
    """Test suite for sector rotation detection"""

    def test_update_sector_performance(self, sector_manager):
        """Test updating sector performance data"""
        sector_returns = {
            "layer_1": 0.05,
            "defi": 0.08,
            "meme": 0.15,
        }

        sector_manager.update_sector_performance(sector_returns)

        assert "layer_1" in sector_manager._sector_performance
        assert len(sector_manager._sector_performance["layer_1"]) > 0

    def test_detect_sector_rotation_no_data(self, sector_manager):
        """Test rotation detection with no data"""
        signals = sector_manager.detect_sector_rotation()

        assert isinstance(signals, list)
        assert len(signals) == 0  # No signals without data

    def test_detect_sector_rotation_with_data(self, sector_manager):
        """Test rotation detection with performance data"""
        # Simulate multiple days of performance
        for _ in range(5):
            sector_returns = {
                "layer_1": 0.02,     # Moderate
                "defi": 0.08,        # Strong
                "meme": -0.05,       # Weak
            }
            sector_manager.update_sector_performance(sector_returns)

        signals = sector_manager.detect_sector_rotation()

        assert isinstance(signals, list)
        # Should have signals for sectors with data
        if signals:
            assert all(isinstance(s, SectorRotationSignal) for s in signals)
            assert all(s.signal in ["INFLOW", "OUTFLOW", "NEUTRAL"] for s in signals)


# =============================================================================
# SERIALIZATION TESTS
# =============================================================================

class TestSerialization:
    """Test suite for data serialization"""

    def test_sector_exposure_to_dict(self, sector_manager, sample_positions):
        """Test SectorExposure serialization"""
        analysis = sector_manager.calculate_sector_exposure(sample_positions, 100000)

        if analysis.sector_exposures:
            exposure_dict = analysis.sector_exposures[0].to_dict()

            assert "sector" in exposure_dict
            assert "exposure_pct" in exposure_dict
            assert "is_over_limit" in exposure_dict

    def test_sector_analysis_result_to_dict(
        self,
        sector_manager,
        sample_positions
    ):
        """Test SectorAnalysisResult serialization"""
        analysis = sector_manager.calculate_sector_exposure(sample_positions, 100000)
        result_dict = analysis.to_dict()

        assert "total_portfolio_value" in result_dict
        assert "sector_count" in result_dict
        assert "diversification_rating" in result_dict
        assert "sector_exposures" in result_dict
        assert "recommendations" in result_dict

    def test_sector_rotation_signal_to_dict(self):
        """Test SectorRotationSignal serialization"""
        signal = SectorRotationSignal(
            sector=CryptoSector.DEFI,
            sector_name="DeFi Protocols",
            relative_strength=0.15,
            strength_change=0.05,
            signal="INFLOW",
            confidence=0.8,
        )

        signal_dict = signal.to_dict()

        assert "sector" in signal_dict
        assert "signal" in signal_dict
        assert "confidence" in signal_dict


# =============================================================================
# STATUS AND SUMMARY TESTS
# =============================================================================

class TestStatusAndSummary:
    """Test suite for status and summary methods"""

    def test_get_status(self, sector_manager):
        """Test getting manager status"""
        status = sector_manager.get_status()

        assert "sectors_tracked" in status
        assert "custom_mappings" in status
        assert "config" in status

    def test_get_summary(self, sector_manager, sample_positions):
        """Test getting quick summary"""
        summary = sector_manager.get_summary(sample_positions, 100000)

        assert "total_value" in summary
        assert "sector_count" in summary
        assert "rating" in summary
        assert "top_sectors" in summary


# =============================================================================
# GLOBAL INSTANCE TESTS
# =============================================================================

class TestGlobalInstance:
    """Test suite for global instance management"""

    def test_get_sector_exposure_manager_singleton(self):
        """Test global manager is a singleton"""
        reset_sector_exposure_manager()

        manager1 = get_sector_exposure_manager()
        manager2 = get_sector_exposure_manager()

        assert manager1 is manager2

    def test_reset_sector_exposure_manager(self):
        """Test reset creates new instance"""
        manager1 = get_sector_exposure_manager()
        reset_sector_exposure_manager()
        manager2 = get_sector_exposure_manager()

        assert manager1 is not manager2


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test suite for edge cases"""

    def test_single_position(self, sector_manager):
        """Test analysis with single position"""
        positions = [
            SectorPosition(
                symbol="BTCUSDT", position_value=50000, risk_pct=5.0,
                entry_price=100000, current_price=100000,
                sector=CryptoSector.LAYER_1, unrealized_pnl_pct=0
            ),
        ]

        analysis = sector_manager.calculate_sector_exposure(positions, 50000)

        assert analysis.sector_count == 1
        assert len(analysis.recommendations) > 0

    def test_all_sectors_represented(self, sector_manager):
        """Test when all sectors are represented"""
        positions = []
        sectors = list(CryptoSector)

        for i, sector in enumerate(sectors):
            positions.append(SectorPosition(
                symbol=f"TEST{i}USDT",
                position_value=1000,
                risk_pct=0.1,
                entry_price=100,
                current_price=100,
                sector=sector,
                unrealized_pnl_pct=0
            ))

        analysis = sector_manager.calculate_sector_exposure(positions, len(sectors) * 1000)

        assert analysis.sector_count == len(sectors)

    def test_very_large_portfolio(self, sector_manager):
        """Test with very large portfolio value"""
        positions = [
            SectorPosition(
                symbol="BTCUSDT", position_value=100_000_000, risk_pct=5.0,
                entry_price=100000, current_price=100000,
                sector=CryptoSector.LAYER_1, unrealized_pnl_pct=0
            ),
        ]

        analysis = sector_manager.calculate_sector_exposure(positions, 100_000_000)

        assert analysis.total_portfolio_value == 100_000_000


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
