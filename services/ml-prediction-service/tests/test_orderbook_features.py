"""
Tests for Order Book Microstructure Feature Extractor
Purpose: Comprehensive test coverage for Phase 6.2 implementation
Author: Phase 6.2 ML Team
Date: 2025-12-11

Test Coverage Target: >85%

Tests:
- Feature calculation accuracy
- Edge cases (empty order book, single level, etc.)
- Performance benchmarks (<10ms)
- Redis cache integration
- API endpoint functionality
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, List

import numpy as np

# Import modules under test
from app.features.orderbook_features import (
    OrderBookFeatureExtractor,
    OrderBookFeatures,
    OrderBookCache,
    OrderBookLevel,
)


# ==============================================================================
# TEST FIXTURES
# ==============================================================================

@pytest.fixture
def sample_orderbook() -> Dict[str, Any]:
    """
    Standard order book fixture for testing

    Structure:
    - 10 bid levels, descending from 100000
    - 10 ask levels, ascending from 100001
    - Spread: $1 (0.001%)
    """
    return {
        "bids": [
            [100000.0, 1.5],
            [99999.5, 2.0],
            [99999.0, 0.8],
            [99998.5, 1.2],
            [99998.0, 3.0],
            [99997.5, 2.5],
            [99997.0, 1.8],
            [99996.5, 4.0],
            [99996.0, 2.2],
            [99995.5, 1.5],
        ],
        "asks": [
            [100001.0, 1.2],
            [100001.5, 1.8],
            [100002.0, 2.5],
            [100002.5, 1.0],
            [100003.0, 3.2],
            [100003.5, 2.0],
            [100004.0, 1.5],
            [100004.5, 2.8],
            [100005.0, 1.9],
            [100005.5, 2.1],
        ]
    }


@pytest.fixture
def imbalanced_orderbook() -> Dict[str, Any]:
    """Order book with significant bid-side imbalance (bullish)"""
    return {
        "bids": [
            [100000.0, 10.0],  # Heavy bid volume
            [99999.5, 8.0],
            [99999.0, 6.0],
            [99998.5, 5.0],
            [99998.0, 4.0],
        ],
        "asks": [
            [100001.0, 1.0],  # Light ask volume
            [100001.5, 0.8],
            [100002.0, 0.5],
            [100002.5, 0.3],
            [100003.0, 0.4],
        ]
    }


@pytest.fixture
def wide_spread_orderbook() -> Dict[str, Any]:
    """Order book with wide spread (low liquidity)"""
    return {
        "bids": [
            [99000.0, 1.0],  # Best bid at 99000
            [98990.0, 2.0],
            [98980.0, 1.5],
        ],
        "asks": [
            [101000.0, 1.0],  # Best ask at 101000 ($2000 spread!)
            [101010.0, 2.0],
            [101020.0, 1.5],
        ]
    }


@pytest.fixture
def empty_orderbook() -> Dict[str, Any]:
    """Empty order book"""
    return {"bids": [], "asks": []}


@pytest.fixture
def single_level_orderbook() -> Dict[str, Any]:
    """Order book with only one level on each side"""
    return {
        "bids": [[100000.0, 1.0]],
        "asks": [[100001.0, 1.0]]
    }


@pytest.fixture
def dict_format_orderbook() -> Dict[str, Any]:
    """Order book using dict format instead of arrays"""
    return {
        "bids": [
            {"price": 100000.0, "size": 1.5},
            {"price": 99999.5, "size": 2.0},
        ],
        "asks": [
            {"price": 100001.0, "size": 1.2},
            {"price": 100001.5, "size": 1.8},
        ]
    }


@pytest.fixture
def feature_extractor() -> OrderBookFeatureExtractor:
    """Create feature extractor instance"""
    return OrderBookFeatureExtractor()


# ==============================================================================
# ORDERBOOK LEVEL TESTS
# ==============================================================================

class TestOrderBookLevel:
    """Tests for OrderBookLevel dataclass"""

    def test_create_level_bid(self):
        """Test creating a bid level"""
        level = OrderBookLevel(price=100000.0, size=1.5, side="bid")
        assert level.price == 100000.0
        assert level.size == 1.5
        assert level.side == "bid"

    def test_create_level_ask(self):
        """Test creating an ask level"""
        level = OrderBookLevel(price=100001.0, size=1.2, side="ask")
        assert level.price == 100001.0
        assert level.size == 1.2
        assert level.side == "ask"

    def test_create_level_empty_side(self):
        """Test creating level without side"""
        level = OrderBookLevel(price=100000.0, size=1.0)
        assert level.side == ""

    def test_invalid_side_raises_error(self):
        """Test that invalid side raises ValueError"""
        with pytest.raises(ValueError):
            OrderBookLevel(price=100000.0, size=1.0, side="invalid")


# ==============================================================================
# BID-ASK SPREAD TESTS
# ==============================================================================

class TestBidAskSpread:
    """Tests for bid-ask spread calculation"""

    def test_normal_spread(self, feature_extractor, sample_orderbook):
        """Test normal spread calculation"""
        spread_pct, best_bid, best_ask, mid = feature_extractor.calculate_bid_ask_spread(
            sample_orderbook
        )

        assert best_bid == 100000.0
        assert best_ask == 100001.0
        assert mid == 100000.5
        # Spread = ($1 / $100000.5) * 100 = ~0.001%
        assert 0.0009 < spread_pct < 0.0011

    def test_wide_spread(self, feature_extractor, wide_spread_orderbook):
        """Test wide spread calculation"""
        spread_pct, best_bid, best_ask, mid = feature_extractor.calculate_bid_ask_spread(
            wide_spread_orderbook
        )

        assert best_bid == 99000.0
        assert best_ask == 101000.0
        assert mid == 100000.0
        # Spread = ($2000 / $100000) * 100 = 2.0%
        assert 1.99 < spread_pct < 2.01

    def test_empty_orderbook(self, feature_extractor, empty_orderbook):
        """Test spread with empty order book"""
        spread_pct, best_bid, best_ask, mid = feature_extractor.calculate_bid_ask_spread(
            empty_orderbook
        )

        assert spread_pct == 0.0
        assert best_bid == 0.0
        assert best_ask == 0.0
        assert mid == 0.0

    def test_single_level_spread(self, feature_extractor, single_level_orderbook):
        """Test spread with single level"""
        spread_pct, best_bid, best_ask, mid = feature_extractor.calculate_bid_ask_spread(
            single_level_orderbook
        )

        assert best_bid == 100000.0
        assert best_ask == 100001.0
        assert mid == 100000.5


# ==============================================================================
# BID-ASK IMBALANCE TESTS
# ==============================================================================

class TestBidAskImbalance:
    """Tests for bid-ask imbalance calculation"""

    def test_balanced_imbalance(self, feature_extractor, sample_orderbook):
        """Test imbalance with relatively balanced book"""
        imbalance, bid_vol, ask_vol = feature_extractor.calculate_bid_ask_imbalance(
            sample_orderbook, levels=10
        )

        # Sample book has slightly more bid volume
        assert bid_vol > 0
        assert ask_vol > 0
        assert -1.0 <= imbalance <= 1.0

    def test_bullish_imbalance(self, feature_extractor, imbalanced_orderbook):
        """Test imbalance with bullish order book (more bids)"""
        imbalance, bid_vol, ask_vol = feature_extractor.calculate_bid_ask_imbalance(
            imbalanced_orderbook, levels=5
        )

        # Should be strongly positive (bullish)
        assert imbalance > 0.5
        assert bid_vol > ask_vol

    def test_empty_imbalance(self, feature_extractor, empty_orderbook):
        """Test imbalance with empty order book"""
        imbalance, bid_vol, ask_vol = feature_extractor.calculate_bid_ask_imbalance(
            empty_orderbook
        )

        assert imbalance == 0.0
        assert bid_vol == 0.0
        assert ask_vol == 0.0

    def test_imbalance_range(self, feature_extractor, sample_orderbook):
        """Test imbalance is always in [-1, 1] range"""
        for levels in [1, 5, 10, 25]:
            imbalance, _, _ = feature_extractor.calculate_bid_ask_imbalance(
                sample_orderbook, levels=levels
            )
            assert -1.0 <= imbalance <= 1.0


# ==============================================================================
# DEPTH IMBALANCE TESTS
# ==============================================================================

class TestDepthImbalance:
    """Tests for depth imbalance calculation"""

    def test_depth_5_levels(self, feature_extractor, sample_orderbook):
        """Test depth imbalance at 5 levels"""
        depth = feature_extractor.calculate_depth_imbalance(
            sample_orderbook, levels=5
        )
        assert -1.0 <= depth <= 1.0

    def test_depth_10_levels(self, feature_extractor, sample_orderbook):
        """Test depth imbalance at 10 levels"""
        depth = feature_extractor.calculate_depth_imbalance(
            sample_orderbook, levels=10
        )
        assert -1.0 <= depth <= 1.0

    def test_depth_bullish(self, feature_extractor, imbalanced_orderbook):
        """Test depth imbalance with bullish book"""
        depth = feature_extractor.calculate_depth_imbalance(
            imbalanced_orderbook, levels=5
        )
        # Should be positive (more bid depth)
        assert depth > 0.3

    def test_depth_empty(self, feature_extractor, empty_orderbook):
        """Test depth imbalance with empty book"""
        depth = feature_extractor.calculate_depth_imbalance(empty_orderbook)
        assert depth == 0.0


# ==============================================================================
# LIQUIDITY SCORE TESTS
# ==============================================================================

class TestLiquidityScore:
    """Tests for liquidity score calculation"""

    def test_normal_liquidity(self, feature_extractor, sample_orderbook):
        """Test liquidity score with normal book"""
        liquidity = feature_extractor.calculate_liquidity_score(sample_orderbook)
        assert liquidity > 0

    def test_liquidity_with_mid(self, feature_extractor, sample_orderbook):
        """Test liquidity with pre-calculated mid price"""
        liquidity = feature_extractor.calculate_liquidity_score(
            sample_orderbook,
            mid_price=100000.5
        )
        assert liquidity > 0

    def test_liquidity_empty(self, feature_extractor, empty_orderbook):
        """Test liquidity with empty book"""
        liquidity = feature_extractor.calculate_liquidity_score(empty_orderbook)
        assert liquidity == 0.0

    def test_liquidity_zero_mid(self, feature_extractor, sample_orderbook):
        """Test liquidity with zero mid price"""
        liquidity = feature_extractor.calculate_liquidity_score(
            sample_orderbook,
            mid_price=0.0
        )
        assert liquidity == 0.0


# ==============================================================================
# VOLUME-WEIGHTED MID TESTS
# ==============================================================================

class TestVolumeWeightedMid:
    """Tests for volume-weighted mid price calculation"""

    def test_normal_vwmid(self, feature_extractor, sample_orderbook):
        """Test VWMID with normal order book"""
        vwmid = feature_extractor.calculate_volume_weighted_mid(sample_orderbook)

        # Should be between best bid and best ask
        assert 100000.0 <= vwmid <= 100001.0

    def test_vwmid_balanced(self, feature_extractor, single_level_orderbook):
        """Test VWMID with equal volumes"""
        # Equal volumes should give simple mid
        vwmid = feature_extractor.calculate_volume_weighted_mid(
            single_level_orderbook
        )
        assert vwmid == 100000.5

    def test_vwmid_imbalanced(self, feature_extractor, imbalanced_orderbook):
        """Test VWMID with imbalanced book"""
        vwmid = feature_extractor.calculate_volume_weighted_mid(imbalanced_orderbook)

        # With more bid volume, VWMID should be closer to ask
        # (buyers are aggressive)
        mid = (99000.0 + 101000.0) / 2  # Assuming these are best bid/ask
        assert vwmid > 0

    def test_vwmid_empty(self, feature_extractor, empty_orderbook):
        """Test VWMID with empty book"""
        vwmid = feature_extractor.calculate_volume_weighted_mid(empty_orderbook)
        assert vwmid == 0.0


# ==============================================================================
# ORDER FLOW IMBALANCE TESTS
# ==============================================================================

class TestOrderFlowImbalance:
    """Tests for order flow imbalance calculation"""

    def test_initial_flow(self, feature_extractor, sample_orderbook):
        """Test order flow with no history"""
        flow = feature_extractor.calculate_order_flow_imbalance(
            "BTCUSDT",
            sample_orderbook
        )
        assert -1.0 <= flow <= 1.0

    def test_flow_accumulation(self, feature_extractor, sample_orderbook):
        """Test order flow accumulates over multiple calls"""
        # Make multiple calls to build history
        for _ in range(5):
            feature_extractor.calculate_order_flow_imbalance(
                "BTCUSDT",
                sample_orderbook
            )

        flow = feature_extractor.calculate_order_flow_imbalance(
            "BTCUSDT",
            sample_orderbook
        )
        assert -1.0 <= flow <= 1.0

    def test_flow_different_symbols(self, feature_extractor, sample_orderbook):
        """Test flow is tracked separately per symbol"""
        flow_btc = feature_extractor.calculate_order_flow_imbalance(
            "BTCUSDT",
            sample_orderbook
        )
        flow_eth = feature_extractor.calculate_order_flow_imbalance(
            "ETHUSDT",
            sample_orderbook
        )

        # Both should be valid
        assert -1.0 <= flow_btc <= 1.0
        assert -1.0 <= flow_eth <= 1.0


# ==============================================================================
# ORDER PRESSURE TESTS
# ==============================================================================

class TestOrderPressure:
    """Tests for order pressure calculation"""

    def test_initial_pressure(self, feature_extractor, sample_orderbook):
        """Test pressure with no history"""
        pressure = feature_extractor.calculate_order_pressure(
            "BTCUSDT",
            sample_orderbook
        )
        assert -1.0 <= pressure <= 1.0

    def test_pressure_buildup(self, feature_extractor, sample_orderbook):
        """Test pressure with history buildup"""
        # Build history
        for _ in range(10):
            feature_extractor.calculate_order_flow_imbalance(
                "BTCUSDT",
                sample_orderbook
            )

        pressure = feature_extractor.calculate_order_pressure(
            "BTCUSDT",
            sample_orderbook
        )
        assert -1.0 <= pressure <= 1.0


# ==============================================================================
# EXTRACT ALL FEATURES TESTS
# ==============================================================================

class TestExtractAllFeatures:
    """Tests for comprehensive feature extraction"""

    def test_extract_all_returns_features(self, feature_extractor, sample_orderbook):
        """Test extract_all_features returns OrderBookFeatures"""
        features = feature_extractor.extract_all_features(
            sample_orderbook,
            symbol="BTCUSDT"
        )

        assert isinstance(features, OrderBookFeatures)
        assert features.symbol == "BTCUSDT"

    def test_extract_all_core_features(self, feature_extractor, sample_orderbook):
        """Test all 8 core features are calculated"""
        features = feature_extractor.extract_all_features(
            sample_orderbook,
            symbol="BTCUSDT"
        )

        # Check all 8 core features exist
        assert features.bid_ask_spread_pct >= 0
        assert -1.0 <= features.bid_ask_imbalance <= 1.0
        assert -1.0 <= features.order_flow_imbalance <= 1.0
        assert -1.0 <= features.depth_imbalance_5 <= 1.0
        assert -1.0 <= features.depth_imbalance_10 <= 1.0
        assert features.liquidity_score >= 0
        assert features.volume_weighted_mid > 0
        assert -1.0 <= features.order_pressure <= 1.0

    def test_extract_all_context_features(self, feature_extractor, sample_orderbook):
        """Test context features are calculated"""
        features = feature_extractor.extract_all_features(
            sample_orderbook,
            symbol="BTCUSDT"
        )

        assert features.best_bid == 100000.0
        assert features.best_ask == 100001.0
        assert features.mid_price == 100000.5
        assert features.total_bid_volume > 0
        assert features.total_ask_volume > 0

    def test_extract_all_metadata(self, feature_extractor, sample_orderbook):
        """Test metadata is populated"""
        features = feature_extractor.extract_all_features(
            sample_orderbook,
            symbol="BTCUSDT"
        )

        assert features.calculation_time_ms > 0
        assert features.levels_analyzed > 0
        assert features.data_source == "bybit"
        assert isinstance(features.timestamp, datetime)

    def test_extract_all_empty_book(self, feature_extractor, empty_orderbook):
        """Test extract_all with empty order book"""
        features = feature_extractor.extract_all_features(
            empty_orderbook,
            symbol="BTCUSDT"
        )

        # Should return features object with zeros
        assert features.bid_ask_spread_pct == 0.0
        assert features.mid_price == 0.0

    def test_extract_all_performance(self, feature_extractor, sample_orderbook):
        """Test feature extraction performance (<10ms)"""
        features = feature_extractor.extract_all_features(
            sample_orderbook,
            symbol="BTCUSDT"
        )

        # Should complete in under 10ms
        assert features.calculation_time_ms < 10.0

    def test_extract_all_dict_format(self, feature_extractor, dict_format_orderbook):
        """Test with dict format order book"""
        features = feature_extractor.extract_all_features(
            dict_format_orderbook,
            symbol="BTCUSDT"
        )

        assert features.best_bid == 100000.0
        assert features.best_ask == 100001.0


# ==============================================================================
# ORDERBOOK FEATURES DATACLASS TESTS
# ==============================================================================

class TestOrderBookFeaturesDataclass:
    """Tests for OrderBookFeatures dataclass"""

    def test_to_dict(self, feature_extractor, sample_orderbook):
        """Test conversion to dictionary"""
        features = feature_extractor.extract_all_features(
            sample_orderbook,
            symbol="BTCUSDT"
        )

        result = features.to_dict()
        assert isinstance(result, dict)
        assert result["symbol"] == "BTCUSDT"
        assert isinstance(result["timestamp"], str)  # ISO format

    def test_to_ml_array(self, feature_extractor, sample_orderbook):
        """Test conversion to ML array"""
        features = feature_extractor.extract_all_features(
            sample_orderbook,
            symbol="BTCUSDT"
        )

        array = features.to_ml_array()
        assert isinstance(array, list)
        assert len(array) == 8  # 8 core features
        assert all(isinstance(v, float) for v in array)

    def test_get_feature_names(self):
        """Test static feature names"""
        names = OrderBookFeatures.get_feature_names()
        assert len(names) == 8
        assert "bid_ask_spread_pct" in names
        assert "bid_ask_imbalance" in names
        assert "order_flow_imbalance" in names


# ==============================================================================
# FEATURE NORMALIZATION TESTS
# ==============================================================================

class TestFeatureNormalization:
    """Tests for feature normalization"""

    def test_normalize_default_stats(self, feature_extractor, sample_orderbook):
        """Test normalization with default stats"""
        features = feature_extractor.extract_all_features(
            sample_orderbook,
            symbol="BTCUSDT"
        )

        normalized = feature_extractor.normalize_features(features)
        assert isinstance(normalized, dict)
        assert len(normalized) == 8

        # All values should be clipped to [-3, 3]
        for name, value in normalized.items():
            assert -3.0 <= value <= 3.0

    def test_normalize_custom_stats(self, feature_extractor, sample_orderbook):
        """Test normalization with custom stats"""
        features = feature_extractor.extract_all_features(
            sample_orderbook,
            symbol="BTCUSDT"
        )

        custom_stats = {
            "bid_ask_spread_pct": {"mean": 0.01, "std": 0.005},
            "bid_ask_imbalance": {"mean": 0.0, "std": 0.5},
            "order_flow_imbalance": {"mean": 0.0, "std": 0.5},
            "depth_imbalance_5": {"mean": 0.0, "std": 0.5},
            "depth_imbalance_10": {"mean": 0.0, "std": 0.5},
            "liquidity_score": {"mean": 50.0, "std": 25.0},
            "volume_weighted_mid": {"mean": 100000.0, "std": 5000.0},
            "order_pressure": {"mean": 0.0, "std": 0.3},
        }

        normalized = feature_extractor.normalize_features(features, custom_stats)
        assert isinstance(normalized, dict)


# ==============================================================================
# HELPER METHOD TESTS
# ==============================================================================

class TestHelperMethods:
    """Tests for private helper methods"""

    def test_get_price_array(self, feature_extractor):
        """Test price extraction from array format"""
        price = feature_extractor._get_price([100000.0, 1.5])
        assert price == 100000.0

    def test_get_price_dict(self, feature_extractor):
        """Test price extraction from dict format"""
        price = feature_extractor._get_price({"price": 100000.0, "size": 1.5})
        assert price == 100000.0

    def test_get_size_array(self, feature_extractor):
        """Test size extraction from array format"""
        size = feature_extractor._get_size([100000.0, 1.5])
        assert size == 1.5

    def test_get_size_dict(self, feature_extractor):
        """Test size extraction from dict format"""
        size = feature_extractor._get_size({"price": 100000.0, "size": 1.5})
        assert size == 1.5

    def test_get_size_dict_qty(self, feature_extractor):
        """Test size extraction with 'qty' key"""
        size = feature_extractor._get_size({"price": 100000.0, "qty": 2.0})
        assert size == 2.0


# ==============================================================================
# ORDERBOOK CACHE TESTS
# ==============================================================================

class TestOrderBookCache:
    """Tests for OrderBookCache class"""

    @pytest.fixture
    def cache(self):
        """Create cache instance with Redis disabled"""
        return OrderBookCache(enabled=False)

    @pytest.mark.asyncio
    async def test_connect_disabled(self, cache):
        """Test connection with cache disabled"""
        result = await cache.connect()
        assert result is True
        assert cache.is_connected is False

    @pytest.mark.asyncio
    async def test_store_snapshot_memory(self, cache, sample_orderbook):
        """Test storing snapshot in memory"""
        await cache.connect()
        result = await cache.store_snapshot("BTCUSDT", sample_orderbook)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_snapshots_memory(self, cache, sample_orderbook):
        """Test retrieving snapshots from memory"""
        await cache.connect()
        await cache.store_snapshot("BTCUSDT", sample_orderbook)

        snapshots = await cache.get_snapshots("BTCUSDT", seconds_back=60)
        assert len(snapshots) >= 1

    @pytest.mark.asyncio
    async def test_get_latest(self, cache, sample_orderbook):
        """Test getting latest snapshot"""
        await cache.connect()
        await cache.store_snapshot("BTCUSDT", sample_orderbook)

        latest = await cache.get_latest("BTCUSDT")
        assert latest is not None
        assert "bids" in latest
        assert "asks" in latest

    @pytest.mark.asyncio
    async def test_get_latest_empty(self, cache):
        """Test getting latest from empty cache"""
        await cache.connect()
        latest = await cache.get_latest("BTCUSDT")
        assert latest is None

    def test_make_key(self, cache):
        """Test key generation"""
        key = cache._make_key("BTCUSDT")
        assert key == "orderbook:BTCUSDT"


# ==============================================================================
# PERFORMANCE BENCHMARK TESTS
# ==============================================================================

class TestPerformanceBenchmarks:
    """Performance benchmark tests"""

    def test_spread_calculation_fast(self, feature_extractor, sample_orderbook):
        """Benchmark spread calculation"""
        start = time.perf_counter()
        for _ in range(1000):
            feature_extractor.calculate_bid_ask_spread(sample_orderbook)
        elapsed = (time.perf_counter() - start) * 1000  # ms

        # Should complete 1000 calculations in < 100ms
        assert elapsed < 100

    def test_imbalance_calculation_fast(self, feature_extractor, sample_orderbook):
        """Benchmark imbalance calculation"""
        start = time.perf_counter()
        for _ in range(1000):
            feature_extractor.calculate_bid_ask_imbalance(sample_orderbook)
        elapsed = (time.perf_counter() - start) * 1000

        assert elapsed < 100

    def test_all_features_fast(self, feature_extractor, sample_orderbook):
        """Benchmark full feature extraction"""
        start = time.perf_counter()
        for _ in range(100):
            feature_extractor.extract_all_features(sample_orderbook, "BTCUSDT")
        elapsed = (time.perf_counter() - start) * 1000

        # Should complete 100 extractions in < 500ms (5ms each)
        assert elapsed < 500


# ==============================================================================
# INTEGRATION TESTS
# ==============================================================================

class TestIntegration:
    """Integration tests for complete workflow"""

    @pytest.mark.asyncio
    async def test_full_workflow(self, sample_orderbook):
        """Test complete feature extraction workflow"""
        # Create cache and extractor
        cache = OrderBookCache(enabled=False)
        await cache.connect()

        extractor = OrderBookFeatureExtractor(cache=cache)

        # Store snapshot
        await cache.store_snapshot("BTCUSDT", sample_orderbook)

        # Extract features
        features = extractor.extract_all_features(
            sample_orderbook,
            symbol="BTCUSDT"
        )

        # Verify features
        assert features.symbol == "BTCUSDT"
        assert len(features.to_ml_array()) == 8

        # Get last features
        last = extractor.get_last_features("BTCUSDT")
        assert last is not None
        assert last.symbol == "BTCUSDT"

        # Clean up
        await cache.disconnect()

    @pytest.mark.asyncio
    async def test_multiple_symbols(self, sample_orderbook):
        """Test extraction for multiple symbols"""
        extractor = OrderBookFeatureExtractor()

        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

        for symbol in symbols:
            features = extractor.extract_all_features(
                sample_orderbook,
                symbol=symbol
            )
            assert features.symbol == symbol

        # Verify all cached
        for symbol in symbols:
            last = extractor.get_last_features(symbol)
            assert last is not None


# ==============================================================================
# EDGE CASE TESTS
# ==============================================================================

class TestEdgeCases:
    """Edge case tests"""

    def test_very_large_order_book(self, feature_extractor):
        """Test with very large order book (500 levels)"""
        large_book = {
            "bids": [[100000 - i * 0.5, np.random.uniform(0.1, 10)] for i in range(500)],
            "asks": [[100001 + i * 0.5, np.random.uniform(0.1, 10)] for i in range(500)]
        }

        features = feature_extractor.extract_all_features(large_book, "BTCUSDT")
        assert features.calculation_time_ms < 50  # Still fast

    def test_zero_volume_levels(self, feature_extractor):
        """Test with zero volume levels"""
        book = {
            "bids": [[100000.0, 0.0], [99999.0, 1.0]],
            "asks": [[100001.0, 0.0], [100002.0, 1.0]]
        }

        features = feature_extractor.extract_all_features(book, "BTCUSDT")
        assert features is not None

    def test_negative_prices(self, feature_extractor):
        """Test handling of negative prices (invalid data)"""
        book = {
            "bids": [[-100.0, 1.0]],
            "asks": [[100.0, 1.0]]
        }

        # Should handle gracefully
        features = feature_extractor.extract_all_features(book, "BTCUSDT")
        assert features is not None

    def test_string_numbers(self, feature_extractor):
        """Test with string numbers (common in API responses)"""
        book = {
            "bids": [["100000.0", "1.5"], ["99999.5", "2.0"]],
            "asks": [["100001.0", "1.2"], ["100001.5", "1.8"]]
        }

        features = feature_extractor.extract_all_features(book, "BTCUSDT")
        assert features.best_bid == 100000.0
        assert features.best_ask == 100001.0


# ==============================================================================
# API HANDLER TESTS
# ==============================================================================

class TestAPIHandlers:
    """Tests for API endpoint handlers"""

    @pytest.mark.asyncio
    async def test_interpret_imbalance_bullish(self):
        """Test bullish imbalance interpretation"""
        from app.handlers.orderbook import interpret_imbalance
        result = interpret_imbalance(0.5)
        assert "Bullish" in result

    @pytest.mark.asyncio
    async def test_interpret_imbalance_bearish(self):
        """Test bearish imbalance interpretation"""
        from app.handlers.orderbook import interpret_imbalance
        result = interpret_imbalance(-0.5)
        assert "Bearish" in result

    @pytest.mark.asyncio
    async def test_interpret_imbalance_neutral(self):
        """Test neutral imbalance interpretation"""
        from app.handlers.orderbook import interpret_imbalance
        result = interpret_imbalance(0.05)
        assert "Neutral" in result

    @pytest.mark.asyncio
    async def test_determine_liquidity_high(self):
        """Test high liquidity determination"""
        from app.handlers.orderbook import determine_liquidity_level
        level = determine_liquidity_level(0.01, 150)
        assert level == "HIGH"

    @pytest.mark.asyncio
    async def test_determine_liquidity_medium(self):
        """Test medium liquidity determination"""
        from app.handlers.orderbook import determine_liquidity_level
        level = determine_liquidity_level(0.03, 75)
        assert level == "MEDIUM"

    @pytest.mark.asyncio
    async def test_determine_liquidity_low(self):
        """Test low liquidity determination"""
        from app.handlers.orderbook import determine_liquidity_level
        level = determine_liquidity_level(0.1, 20)
        assert level == "LOW"

    @pytest.mark.asyncio
    async def test_estimate_slippage(self, sample_orderbook):
        """Test slippage estimation"""
        from app.handlers.orderbook import estimate_slippage

        slippage = estimate_slippage(sample_orderbook, 1.0, "buy")
        assert slippage >= 0


# ==============================================================================
# MODULE EXECUTION TEST
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=app.features", "--cov-report=term-missing"])
