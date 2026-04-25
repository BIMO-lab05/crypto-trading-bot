"""
Unit Tests for Support/Resistance Detector
===========================================
Purpose: Comprehensive test coverage for S/R level detection

Test Coverage:
- Swing high/low detection
- Level clustering and zone calculation
- Strength calculation with multiple factors
- Near support/resistance detection
- Next support/resistance finding
- Edge cases and boundary conditions

Author: Phase 2.1.3 Testing Suite
Date: 2025-12-08
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Tuple

from app.utils.support_resistance_detector import (
    SupportResistanceDetector,
    SupportLevel,
    ResistanceLevel,
    LevelStrength,
    Touch,
    DEFAULT_SWING_WINDOW,
    LEVEL_CLUSTER_TOLERANCE_PCT,
    MIN_TOUCHES_FOR_LEVEL,
)


# =============================================================================
# TEST DATA FIXTURES
# =============================================================================

@pytest.fixture
def sample_df_simple():
    """
    Create simple price data with clear support/resistance levels

    Pattern:
    - Price oscillates between 95-105 (resistance at 105, support at 95)
    - 100 candles of data
    """
    np.random.seed(42)  # For reproducibility

    dates = pd.date_range(start='2025-01-01', periods=100, freq='1H')

    # Create oscillating price pattern between 95-105
    base_prices = []
    for i in range(100):
        # Oscillate between support and resistance
        if i % 10 < 5:
            base_prices.append(95 + np.random.uniform(0, 5))  # Near support
        else:
            base_prices.append(100 + np.random.uniform(0, 5))  # Near resistance

    data = {
        'timestamp': dates,
        'open': [p + np.random.uniform(-1, 1) for p in base_prices],
        'high': [p + np.random.uniform(0, 2) for p in base_prices],
        'low': [p - np.random.uniform(0, 2) for p in base_prices],
        'close': base_prices,
        'volume': np.random.uniform(1000, 5000, 100)
    }

    return pd.DataFrame(data)


@pytest.fixture
def sample_df_trending():
    """
    Create trending price data (uptrend with higher lows)

    Pattern:
    - Clear uptrend with support levels at 100, 110, 120
    - Resistance levels at 105, 115, 125
    """
    np.random.seed(43)

    dates = pd.date_range(start='2025-01-01', periods=150, freq='1H')

    # Create uptrending prices with clear S/R levels
    base_prices = []
    for i in range(150):
        # Uptrend: price increases over time with S/R levels
        trend_price = 100 + (i / 5)  # Base uptrend

        # Add oscillation around trend
        if i % 15 < 8:
            # Testing support
            base_prices.append(trend_price - np.random.uniform(0, 2))
        else:
            # Testing resistance
            base_prices.append(trend_price + np.random.uniform(3, 5))

    data = {
        'timestamp': dates,
        'open': [p + np.random.uniform(-1, 1) for p in base_prices],
        'high': [p + np.random.uniform(0, 2) for p in base_prices],
        'low': [p - np.random.uniform(0, 2) for p in base_prices],
        'close': base_prices,
        'volume': np.random.uniform(2000, 6000, 150)
    }

    return pd.DataFrame(data)


@pytest.fixture
def sample_df_volatile():
    """
    Create highly volatile price data

    Pattern:
    - Wide price swings with less clear levels
    - Good for testing edge cases
    """
    np.random.seed(44)

    dates = pd.date_range(start='2025-01-01', periods=200, freq='1H')

    # Create volatile random walk
    base_prices = [100]
    for i in range(199):
        change = np.random.uniform(-10, 10)  # Large random moves
        base_prices.append(max(50, base_prices[-1] + change))  # Keep above 50

    data = {
        'timestamp': dates,
        'open': [p + np.random.uniform(-5, 5) for p in base_prices],
        'high': [p + np.random.uniform(0, 10) for p in base_prices],
        'low': [p - np.random.uniform(0, 10) for p in base_prices],
        'close': base_prices,
        'volume': np.random.uniform(1000, 10000, 200)
    }

    return pd.DataFrame(data)


@pytest.fixture
def detector_default():
    """Default detector with standard settings"""
    return SupportResistanceDetector()


@pytest.fixture
def detector_custom():
    """Custom detector with different settings"""
    return SupportResistanceDetector(
        swing_window=3,
        cluster_tolerance_pct=0.005,  # 0.5%
        min_touches=3  # Require more touches
    )


# =============================================================================
# TEST CLASS: Swing Detection
# =============================================================================

class TestSwingDetection:
    """Test swing high/low detection methods"""

    def test_detect_swing_lows_finds_valid_lows(self, detector_default, sample_df_simple):
        """Test that swing low detection finds local minima"""
        swing_lows = detector_default._detect_swing_lows(sample_df_simple, lookback=100)

        # Should find at least some swing lows
        assert len(swing_lows) > 0, "Should detect swing lows in oscillating price data"

        # Each swing low should be a tuple: (index, price, volume, timestamp)
        for swing in swing_lows:
            assert len(swing) == 4, "Swing low should have 4 elements"
            idx, price, volume, timestamp = swing
            assert isinstance(idx, (int, np.integer)), "Index should be integer"
            assert price > 0, "Price should be positive"
            assert volume >= 0, "Volume should be non-negative"
            assert isinstance(timestamp, (datetime, pd.Timestamp)), "Should have timestamp"

    def test_detect_swing_highs_finds_valid_highs(self, detector_default, sample_df_simple):
        """Test that swing high detection finds local maxima"""
        swing_highs = detector_default._detect_swing_highs(sample_df_simple, lookback=100)

        # Should find at least some swing highs
        assert len(swing_highs) > 0, "Should detect swing highs in oscillating price data"

        # Each swing high should be a tuple: (index, price, volume, timestamp)
        for swing in swing_highs:
            assert len(swing) == 4, "Swing high should have 4 elements"
            idx, price, volume, timestamp = swing
            assert isinstance(idx, (int, np.integer)), "Index should be integer"
            assert price > 0, "Price should be positive"
            assert volume >= 0, "Volume should be non-negative"

    def test_swing_detection_with_insufficient_data(self, detector_default):
        """Test swing detection with too few candles"""
        # Create very small dataset (less than 2*swing_window + 1)
        small_df = pd.DataFrame({
            'timestamp': pd.date_range('2025-01-01', periods=5, freq='1H'),
            'high': [100, 101, 102, 101, 100],
            'low': [99, 100, 101, 100, 99],
            'close': [100, 100.5, 101.5, 100.5, 99.5],
            'volume': [1000, 1100, 1200, 1100, 1000]
        })

        swing_lows = detector_default._detect_swing_lows(small_df, lookback=100)
        swing_highs = detector_default._detect_swing_highs(small_df, lookback=100)

        # Should return empty list (not enough data)
        assert len(swing_lows) == 0, "Should return empty for insufficient data"
        assert len(swing_highs) == 0, "Should return empty for insufficient data"

    def test_swing_window_parameter_affects_sensitivity(self, sample_df_simple):
        """Test that larger swing window finds fewer but stronger swings"""
        detector_small = SupportResistanceDetector(swing_window=3)
        detector_large = SupportResistanceDetector(swing_window=10)

        swings_small = detector_small._detect_swing_lows(sample_df_simple, lookback=100)
        swings_large = detector_large._detect_swing_lows(sample_df_simple, lookback=100)

        # Smaller window should find more swings (more sensitive)
        # Larger window should find fewer swings (less sensitive)
        assert len(swings_small) >= len(swings_large), \
            "Smaller swing window should detect more swing points"

    def test_swing_detection_validates_surrounding_candles(self, detector_default):
        """Test that swing detection properly validates surrounding candles"""
        # Create perfect V-shape for swing low
        df = pd.DataFrame({
            'timestamp': pd.date_range('2025-01-01', periods=15, freq='1H'),
            'high': [105, 104, 103, 102, 101, 100, 99, 98, 99, 100, 101, 102, 103, 104, 105],
            'low': [103, 102, 101, 100, 99, 98, 97, 96, 97, 98, 99, 100, 101, 102, 103],
            'close': [104, 103, 102, 101, 100, 99, 98, 97, 98, 99, 100, 101, 102, 103, 104],
            'volume': [1000] * 15
        })

        swing_lows = detector_default._detect_swing_lows(df, lookback=15)

        # Should detect the swing low at index 7 (lowest point)
        assert len(swing_lows) == 1, "Should detect exactly one swing low in V-shape"
        assert swing_lows[0][1] == 96, "Should detect the lowest point as swing low"


# =============================================================================
# TEST CLASS: Level Clustering
# =============================================================================

class TestLevelClustering:
    """Test level clustering and processing"""

    def test_cluster_levels_groups_nearby_prices(self, detector_default):
        """Test that nearby price levels are clustered together"""
        # Create points with two distinct clusters
        points = [
            (10, 100.0, 1000, datetime(2025, 1, 1, 10, 0)),
            (20, 100.2, 1100, datetime(2025, 1, 1, 20, 0)),  # Close to 100
            (30, 100.1, 1050, datetime(2025, 1, 2, 6, 0)),  # Close to 100
            (50, 105.0, 1200, datetime(2025, 1, 2, 2, 0)),
            (60, 105.3, 1250, datetime(2025, 1, 2, 12, 0)),  # Close to 105
        ]

        clusters = detector_default._cluster_levels(points, tolerance_pct=0.003)

        # Should create 2 clusters (one around 100, one around 105)
        assert len(clusters) == 2, "Should create 2 distinct clusters"

        # First cluster should be around 100
        assert 99.5 < clusters[0]['level_price'] < 100.5, "First cluster around 100"
        assert clusters[0]['touch_count'] == 3, "First cluster should have 3 touches"

        # Second cluster should be around 105
        assert 104.5 < clusters[1]['level_price'] < 105.5, "Second cluster around 105"
        assert clusters[1]['touch_count'] == 2, "Second cluster should have 2 touches"

    def test_cluster_tolerance_affects_grouping(self):
        """Test that different tolerance values affect clustering"""
        points = [
            (10, 100.0, 1000, datetime(2025, 1, 1, 10, 0)),
            (20, 100.5, 1100, datetime(2025, 1, 1, 20, 0)),  # 0.5% from 100
            (30, 101.0, 1050, datetime(2025, 1, 2, 6, 0)),  # 1.0% from 100
        ]

        # Tight tolerance (0.3%) - should create 3 separate clusters
        detector_tight = SupportResistanceDetector(cluster_tolerance_pct=0.003)
        clusters_tight = detector_tight._cluster_levels(points, tolerance_pct=0.003)

        # Loose tolerance (2.0%) - should create 1 cluster
        detector_loose = SupportResistanceDetector(cluster_tolerance_pct=0.02)
        clusters_loose = detector_loose._cluster_levels(points, tolerance_pct=0.02)

        assert len(clusters_tight) > len(clusters_loose), \
            "Tighter tolerance should create more clusters"

    def test_process_cluster_calculates_correct_statistics(self, detector_default):
        """Test that cluster processing calculates correct statistics"""
        cluster_points = [
            (10, 100.0, 1000, datetime(2025, 1, 1, 10, 0)),
            (20, 100.2, 1500, datetime(2025, 1, 1, 20, 0)),
            (30, 99.8, 800, datetime(2025, 1, 2, 6, 0)),
        ]

        cluster = detector_default._process_cluster(cluster_points)

        # Check calculated values
        assert cluster['level_price'] == pytest.approx(100.0, abs=0.1), \
            "Level price should be average of prices"
        assert cluster['touch_count'] == 3, "Should have 3 touches"
        assert cluster['min_price'] == 99.8, "Should track minimum price"
        assert cluster['max_price'] == 100.2, "Should track maximum price"
        assert len(cluster['touches']) == 3, "Should create Touch objects"

        # Check Touch objects
        for touch in cluster['touches']:
            assert isinstance(touch, Touch), "Should create Touch objects"
            assert touch.touch_type == 'bounce', "Default touch type is bounce"

    def test_empty_points_returns_empty_clusters(self, detector_default):
        """Test that empty point list returns empty clusters"""
        clusters = detector_default._cluster_levels([], tolerance_pct=0.003)
        assert len(clusters) == 0, "Empty points should return empty clusters"


# =============================================================================
# TEST CLASS: Strength Calculation
# =============================================================================

class TestStrengthCalculation:
    """Test level strength calculation"""

    def test_strength_increases_with_touch_count(self, detector_default):
        """Test that more touches increase level strength"""
        # Cluster with 2 touches
        cluster_2_touches = {
            'level_price': 100.0,
            'touch_count': 2,
            'touches': [],
            'volumes': [1000, 1000],
            'timestamps': [datetime.now(), datetime.now()],
            'indices': [50, 60],
            'min_price': 99.9,
            'max_price': 100.1,
        }

        # Cluster with 5 touches
        cluster_5_touches = {
            'level_price': 100.0,
            'touch_count': 5,
            'touches': [],
            'volumes': [1000] * 5,
            'timestamps': [datetime.now()] * 5,
            'indices': [40, 50, 60, 70, 80],
            'min_price': 99.9,
            'max_price': 100.1,
        }

        strength_2, _ = detector_default._calculate_level_strength(
            cluster_2_touches, total_candles=100, avg_volume=1000
        )
        strength_5, _ = detector_default._calculate_level_strength(
            cluster_5_touches, total_candles=100, avg_volume=1000
        )

        assert strength_5 > strength_2, \
            "More touches should result in higher strength"

    def test_strength_increases_with_recency(self, detector_default):
        """Test that recent touches increase level strength"""
        # Old touches (far from end)
        cluster_old = {
            'level_price': 100.0,
            'touch_count': 3,
            'touches': [],
            'volumes': [1000] * 3,
            'timestamps': [datetime.now()] * 3,
            'indices': [10, 20, 30],  # Early in dataset
            'min_price': 99.9,
            'max_price': 100.1,
        }

        # Recent touches (near end)
        cluster_recent = {
            'level_price': 100.0,
            'touch_count': 3,
            'touches': [],
            'volumes': [1000] * 3,
            'timestamps': [datetime.now()] * 3,
            'indices': [70, 80, 90],  # Late in dataset
            'min_price': 99.9,
            'max_price': 100.1,
        }

        strength_old, _ = detector_default._calculate_level_strength(
            cluster_old, total_candles=100, avg_volume=1000
        )
        strength_recent, _ = detector_default._calculate_level_strength(
            cluster_recent, total_candles=100, avg_volume=1000
        )

        assert strength_recent > strength_old, \
            "Recent touches should result in higher strength"

    def test_strength_increases_with_volume(self, detector_default):
        """Test that higher volume at touches increases strength"""
        # Low volume touches
        cluster_low_vol = {
            'level_price': 100.0,
            'touch_count': 3,
            'touches': [],
            'volumes': [500, 500, 500],  # Below average
            'timestamps': [datetime.now()] * 3,
            'indices': [50, 60, 70],
            'min_price': 99.9,
            'max_price': 100.1,
        }

        # High volume touches
        cluster_high_vol = {
            'level_price': 100.0,
            'touch_count': 3,
            'touches': [],
            'volumes': [2000, 2000, 2000],  # Above average
            'timestamps': [datetime.now()] * 3,
            'indices': [50, 60, 70],
            'min_price': 99.9,
            'max_price': 100.1,
        }

        strength_low, _ = detector_default._calculate_level_strength(
            cluster_low_vol, total_candles=100, avg_volume=1000
        )
        strength_high, _ = detector_default._calculate_level_strength(
            cluster_high_vol, total_candles=100, avg_volume=1000
        )

        assert strength_high > strength_low, \
            "Higher volume should result in higher strength"

    def test_strength_category_classification(self, detector_default):
        """Test that strength is correctly classified into categories"""
        # Very weak level (low touches, old, low volume)
        cluster_very_weak = {
            'level_price': 100.0,
            'touch_count': 2,  # Minimum touches
            'touches': [],
            'volumes': [200, 200],  # Very low volume
            'timestamps': [datetime.now()] * 2,
            'indices': [5, 10],  # Very old
            'min_price': 99.9,
            'max_price': 100.1,
        }

        # Strong level (many touches, recent, high volume)
        cluster_strong = {
            'level_price': 100.0,
            'touch_count': 6,  # Many touches
            'touches': [],
            'volumes': [3000, 3000, 3000, 3000, 3000, 3000],  # High volume
            'timestamps': [datetime.now()] * 6,
            'indices': [80, 82, 85, 88, 92, 95],  # Very recent
            'min_price': 99.9,
            'max_price': 100.1,
        }

        strength_vw, category_vw = detector_default._calculate_level_strength(
            cluster_very_weak, total_candles=100, avg_volume=1000
        )
        strength_s, category_s = detector_default._calculate_level_strength(
            cluster_strong, total_candles=100, avg_volume=1000
        )

        # Very weak should be in VERY_WEAK or WEAK category
        assert category_vw in [LevelStrength.VERY_WEAK, LevelStrength.WEAK], \
            "Low quality level should be VERY_WEAK or WEAK"

        # Strong should be in MODERATE or STRONG category
        assert category_s in [LevelStrength.MODERATE, LevelStrength.STRONG], \
            "High quality level should be MODERATE or STRONG"

        assert strength_s > strength_vw, "Strong level should have higher score"


# =============================================================================
# TEST CLASS: Support/Resistance Finding
# =============================================================================

class TestSupportResistanceFinding:
    """Test find_support_levels and find_resistance_levels methods"""

    def test_find_support_levels_returns_valid_levels(self, detector_default, sample_df_simple):
        """Test that find_support_levels returns valid SupportLevel objects"""
        support_levels = detector_default.find_support_levels(sample_df_simple, lookback=100)

        # Should find at least one support level
        assert len(support_levels) > 0, "Should find support levels in price data"

        # Validate each support level
        for level in support_levels:
            assert isinstance(level, SupportLevel), "Should return SupportLevel objects"
            assert level.price > 0, "Price should be positive"
            assert 0 <= level.strength <= 1.0, "Strength should be 0-1"
            assert isinstance(level.strength_category, LevelStrength), \
                "Should have LevelStrength category"
            assert level.touch_count >= MIN_TOUCHES_FOR_LEVEL, \
                f"Should have minimum {MIN_TOUCHES_FOR_LEVEL} touches"
            assert isinstance(level.last_touch_time, (datetime, pd.Timestamp)), \
                "Should have timestamp"
            assert level.zone_low < level.zone_high, "Zone should be valid range"

    def test_find_resistance_levels_returns_valid_levels(self, detector_default, sample_df_simple):
        """Test that find_resistance_levels returns valid ResistanceLevel objects"""
        resistance_levels = detector_default.find_resistance_levels(sample_df_simple, lookback=100)

        # Should find at least one resistance level
        assert len(resistance_levels) > 0, "Should find resistance levels in price data"

        # Validate each resistance level
        for level in resistance_levels:
            assert isinstance(level, ResistanceLevel), "Should return ResistanceLevel objects"
            assert level.price > 0, "Price should be positive"
            assert 0 <= level.strength <= 1.0, "Strength should be 0-1"
            assert isinstance(level.strength_category, LevelStrength), \
                "Should have LevelStrength category"
            assert level.touch_count >= MIN_TOUCHES_FOR_LEVEL, \
                f"Should have minimum {MIN_TOUCHES_FOR_LEVEL} touches"

    def test_levels_sorted_by_strength(self, detector_default, sample_df_trending):
        """Test that returned levels are sorted by strength descending"""
        support_levels = detector_default.find_support_levels(sample_df_trending, lookback=150)
        resistance_levels = detector_default.find_resistance_levels(sample_df_trending, lookback=150)

        # Check support levels are sorted
        if len(support_levels) > 1:
            for i in range(len(support_levels) - 1):
                assert support_levels[i].strength >= support_levels[i+1].strength, \
                    "Support levels should be sorted by strength descending"

        # Check resistance levels are sorted
        if len(resistance_levels) > 1:
            for i in range(len(resistance_levels) - 1):
                assert resistance_levels[i].strength >= resistance_levels[i+1].strength, \
                    "Resistance levels should be sorted by strength descending"

    def test_min_touches_filter_applied(self, detector_custom, sample_df_simple):
        """Test that minimum touches filter is applied"""
        # detector_custom requires 3 touches minimum
        support_levels = detector_custom.find_support_levels(sample_df_simple, lookback=100)

        # All returned levels should have at least 3 touches
        for level in support_levels:
            assert level.touch_count >= 3, \
                "All levels should meet minimum touches requirement"

    def test_empty_dataframe_returns_empty_list(self, detector_default):
        """Test that empty DataFrame returns empty list"""
        empty_df = pd.DataFrame({
            'timestamp': [],
            'open': [],
            'high': [],
            'low': [],
            'close': [],
            'volume': []
        })

        support_levels = detector_default.find_support_levels(empty_df, lookback=100)
        resistance_levels = detector_default.find_resistance_levels(empty_df, lookback=100)

        assert len(support_levels) == 0, "Empty DataFrame should return no support levels"
        assert len(resistance_levels) == 0, "Empty DataFrame should return no resistance levels"

    def test_missing_required_columns_returns_empty(self, detector_default):
        """Test that missing required columns returns empty list"""
        bad_df = pd.DataFrame({
            'timestamp': pd.date_range('2025-01-01', periods=10, freq='1H'),
            'price': [100] * 10,  # Wrong column name
        })

        support_levels = detector_default.find_support_levels(bad_df, lookback=10)
        resistance_levels = detector_default.find_resistance_levels(bad_df, lookback=10)

        assert len(support_levels) == 0, "Invalid DataFrame should return no support levels"
        assert len(resistance_levels) == 0, "Invalid DataFrame should return no resistance levels"


# =============================================================================
# TEST CLASS: Proximity Detection
# =============================================================================

class TestProximityDetection:
    """Test is_near_support and is_near_resistance methods"""

    def test_is_near_support_detects_proximity(self, detector_default):
        """Test that is_near_support correctly identifies price near support"""
        # Create support level at 100
        support_level = SupportLevel(
            price=100.0,
            strength=0.8,
            strength_category=LevelStrength.STRONG,
            touch_count=5,
            last_touch_time=datetime.now(),
            touches=[],
            zone_low=99.8,
            zone_high=100.2,
            avg_volume_at_touches=1000,
            metadata={}
        )

        # Price at 100.3 (0.3% above support) - should be near
        is_near, level = detector_default.is_near_support(
            current_price=100.3,
            levels=[support_level],
            tolerance_pct=0.005  # 0.5% tolerance
        )

        assert is_near, "Price 0.3% above support should be detected as near"
        assert level == support_level, "Should return the support level"

    def test_is_near_support_rejects_far_prices(self, detector_default):
        """Test that is_near_support rejects prices far from support"""
        support_level = SupportLevel(
            price=100.0,
            strength=0.8,
            strength_category=LevelStrength.STRONG,
            touch_count=5,
            last_touch_time=datetime.now(),
            touches=[],
            metadata={}
        )

        # Price at 102 (2% above support) - should NOT be near with 0.5% tolerance
        is_near, level = detector_default.is_near_support(
            current_price=102.0,
            levels=[support_level],
            tolerance_pct=0.005
        )

        assert not is_near, "Price 2% above support should NOT be near with 0.5% tolerance"
        assert level is None, "Should return None when not near"

    def test_is_near_resistance_detects_proximity(self, detector_default):
        """Test that is_near_resistance correctly identifies price near resistance"""
        # Create resistance level at 100
        resistance_level = ResistanceLevel(
            price=100.0,
            strength=0.8,
            strength_category=LevelStrength.STRONG,
            touch_count=5,
            last_touch_time=datetime.now(),
            touches=[],
            zone_low=99.8,
            zone_high=100.2,
            avg_volume_at_touches=1000,
            metadata={}
        )

        # Price at 99.7 (0.3% below resistance) - should be near
        is_near, level = detector_default.is_near_resistance(
            current_price=99.7,
            levels=[resistance_level],
            tolerance_pct=0.005
        )

        assert is_near, "Price 0.3% below resistance should be detected as near"
        assert level == resistance_level, "Should return the resistance level"

    def test_proximity_returns_nearest_level(self, detector_default):
        """Test that proximity detection returns the nearest level when multiple exist"""
        support_levels = [
            SupportLevel(price=100.0, strength=0.8, strength_category=LevelStrength.STRONG,
                        touch_count=5, last_touch_time=datetime.now(), touches=[], metadata={}),
            SupportLevel(price=95.0, strength=0.7, strength_category=LevelStrength.MODERATE,
                        touch_count=3, last_touch_time=datetime.now(), touches=[], metadata={}),
        ]

        # Price at 100.2 - should match 100 level (closer)
        is_near, level = detector_default.is_near_support(
            current_price=100.2,
            levels=support_levels,
            tolerance_pct=0.01  # 1% tolerance
        )

        assert is_near, "Should find nearby support"
        assert level.price == 100.0, "Should return the nearest support level"

    def test_proximity_with_empty_levels_list(self, detector_default):
        """Test proximity detection with empty levels list"""
        is_near, level = detector_default.is_near_support(
            current_price=100.0,
            levels=[],
            tolerance_pct=0.005
        )

        assert not is_near, "Should return False for empty levels list"
        assert level is None, "Should return None for empty levels list"

    def test_proximity_with_invalid_price(self, detector_default):
        """Test proximity detection with invalid price"""
        support_level = SupportLevel(
            price=100.0, strength=0.8, strength_category=LevelStrength.STRONG,
            touch_count=5, last_touch_time=datetime.now(), touches=[], metadata={}
        )

        # Test with zero price
        is_near, level = detector_default.is_near_support(
            current_price=0,
            levels=[support_level],
            tolerance_pct=0.005
        )

        assert not is_near, "Should return False for zero price"
        assert level is None, "Should return None for invalid price"

        # Test with negative price
        is_near, level = detector_default.is_near_support(
            current_price=-10,
            levels=[support_level],
            tolerance_pct=0.005
        )

        assert not is_near, "Should return False for negative price"


# =============================================================================
# TEST CLASS: Next Level Finding
# =============================================================================

class TestNextLevelFinding:
    """Test find_next_support and find_next_resistance methods"""

    def test_find_next_resistance_above_price(self, detector_default):
        """Test finding the next resistance level above current price"""
        resistance_levels = [
            ResistanceLevel(price=110.0, strength=0.8, strength_category=LevelStrength.STRONG,
                           touch_count=5, last_touch_time=datetime.now(), touches=[], metadata={}),
            ResistanceLevel(price=105.0, strength=0.7, strength_category=LevelStrength.MODERATE,
                           touch_count=3, last_touch_time=datetime.now(), touches=[], metadata={}),
            ResistanceLevel(price=95.0, strength=0.6, strength_category=LevelStrength.WEAK,
                           touch_count=2, last_touch_time=datetime.now(), touches=[], metadata={}),
        ]

        # Current price at 100 - next resistance should be 105
        next_resistance = detector_default.find_next_resistance(
            current_price=100.0,
            levels=resistance_levels
        )

        assert next_resistance is not None, "Should find next resistance"
        assert next_resistance.price == 105.0, "Should return nearest resistance above price"

    def test_find_next_support_below_price(self, detector_default):
        """Test finding the next support level below current price"""
        support_levels = [
            SupportLevel(price=110.0, strength=0.8, strength_category=LevelStrength.STRONG,
                        touch_count=5, last_touch_time=datetime.now(), touches=[], metadata={}),
            SupportLevel(price=95.0, strength=0.7, strength_category=LevelStrength.MODERATE,
                        touch_count=3, last_touch_time=datetime.now(), touches=[], metadata={}),
            SupportLevel(price=90.0, strength=0.6, strength_category=LevelStrength.WEAK,
                        touch_count=2, last_touch_time=datetime.now(), touches=[], metadata={}),
        ]

        # Current price at 100 - next support should be 95
        next_support = detector_default.find_next_support(
            current_price=100.0,
            levels=support_levels
        )

        assert next_support is not None, "Should find next support"
        assert next_support.price == 95.0, "Should return nearest support below price"

    def test_next_level_with_no_levels_above(self, detector_default):
        """Test next resistance when no levels exist above price"""
        resistance_levels = [
            ResistanceLevel(price=95.0, strength=0.8, strength_category=LevelStrength.STRONG,
                           touch_count=5, last_touch_time=datetime.now(), touches=[], metadata={}),
            ResistanceLevel(price=90.0, strength=0.7, strength_category=LevelStrength.MODERATE,
                           touch_count=3, last_touch_time=datetime.now(), touches=[], metadata={}),
        ]

        # Current price at 100 - no resistance above
        next_resistance = detector_default.find_next_resistance(
            current_price=100.0,
            levels=resistance_levels
        )

        assert next_resistance is None, "Should return None when no levels above"

    def test_next_level_with_no_levels_below(self, detector_default):
        """Test next support when no levels exist below price"""
        support_levels = [
            SupportLevel(price=105.0, strength=0.8, strength_category=LevelStrength.STRONG,
                        touch_count=5, last_touch_time=datetime.now(), touches=[], metadata={}),
            SupportLevel(price=110.0, strength=0.7, strength_category=LevelStrength.MODERATE,
                        touch_count=3, last_touch_time=datetime.now(), touches=[], metadata={}),
        ]

        # Current price at 100 - no support below
        next_support = detector_default.find_next_support(
            current_price=100.0,
            levels=support_levels
        )

        assert next_support is None, "Should return None when no levels below"

    def test_next_level_with_empty_list(self, detector_default):
        """Test next level finding with empty levels list"""
        next_resistance = detector_default.find_next_resistance(100.0, [])
        next_support = detector_default.find_next_support(100.0, [])

        assert next_resistance is None, "Should return None for empty resistance list"
        assert next_support is None, "Should return None for empty support list"


# =============================================================================
# TEST CLASS: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_dataframe_with_no_volume_column(self, detector_default):
        """Test handling of DataFrame without volume column"""
        df_no_volume = pd.DataFrame({
            'timestamp': pd.date_range('2025-01-01', periods=50, freq='1H'),
            'open': np.random.uniform(95, 105, 50),
            'high': np.random.uniform(100, 110, 50),
            'low': np.random.uniform(90, 100, 50),
            'close': np.random.uniform(95, 105, 50),
        })

        # Should still work, just without volume weighting
        support_levels = detector_default.find_support_levels(df_no_volume, lookback=50)
        resistance_levels = detector_default.find_resistance_levels(df_no_volume, lookback=50)

        # Should return levels (may or may not find any depending on data)
        assert isinstance(support_levels, list), "Should return list for DataFrame without volume"
        assert isinstance(resistance_levels, list), "Should return list for DataFrame without volume"

    def test_very_tight_price_range(self, detector_default):
        """Test with prices in very tight range (low volatility)"""
        # Prices between 99.9 and 100.1 (very low volatility)
        df_tight = pd.DataFrame({
            'timestamp': pd.date_range('2025-01-01', periods=100, freq='1H'),
            'open': np.random.uniform(99.9, 100.1, 100),
            'high': np.random.uniform(100.0, 100.1, 100),
            'low': np.random.uniform(99.9, 100.0, 100),
            'close': np.random.uniform(99.9, 100.1, 100),
            'volume': np.random.uniform(1000, 2000, 100),
        })

        support_levels = detector_default.find_support_levels(df_tight, lookback=100)
        resistance_levels = detector_default.find_resistance_levels(df_tight, lookback=100)

        # Should handle tight range without errors
        assert isinstance(support_levels, list), "Should handle tight price range"
        assert isinstance(resistance_levels, list), "Should handle tight price range"

    def test_very_wide_price_range(self, detector_default, sample_df_volatile):
        """Test with highly volatile prices"""
        # Uses sample_df_volatile fixture with wide swings
        support_levels = detector_default.find_support_levels(sample_df_volatile, lookback=200)
        resistance_levels = detector_default.find_resistance_levels(sample_df_volatile, lookback=200)

        # Should handle volatile data without errors
        assert isinstance(support_levels, list), "Should handle volatile data"
        assert isinstance(resistance_levels, list), "Should handle volatile data"

    def test_lookback_larger_than_data(self, detector_default, sample_df_simple):
        """Test with lookback period larger than available data"""
        # Request 500 candles but only have 100
        support_levels = detector_default.find_support_levels(sample_df_simple, lookback=500)

        # Should use all available data
        assert isinstance(support_levels, list), "Should handle lookback > data length"

    def test_zone_boundaries_calculated(self, detector_default):
        """Test that support/resistance zones have proper boundaries"""
        support_level = SupportLevel(
            price=100.0,
            strength=0.8,
            strength_category=LevelStrength.STRONG,
            touch_count=5,
            last_touch_time=datetime.now(),
            touches=[],
            metadata={}
        )

        # Zones should be auto-calculated in __post_init__
        assert support_level.zone_low < support_level.price, \
            "Zone low should be below level price"
        assert support_level.zone_high > support_level.price, \
            "Zone high should be above level price"
        assert support_level.zone_low == pytest.approx(100.0 * 0.998, abs=0.01), \
            "Zone low should be -0.2% of price"
        assert support_level.zone_high == pytest.approx(100.0 * 1.002, abs=0.01), \
            "Zone high should be +0.2% of price"

    def test_touch_object_creation(self):
        """Test Touch object creation and attributes"""
        touch = Touch(
            timestamp=datetime(2025, 1, 1, 12, 0),
            price=100.0,
            volume=1500,
            touch_type='bounce',
            candle_index=50
        )

        assert touch.timestamp == datetime(2025, 1, 1, 12, 0), "Timestamp should match"
        assert touch.price == 100.0, "Price should match"
        assert touch.volume == 1500, "Volume should match"
        assert touch.touch_type == 'bounce', "Touch type should match"
        assert touch.candle_index == 50, "Candle index should match"

    def test_level_strength_enum_values(self):
        """Test LevelStrength enum has correct values"""
        assert LevelStrength.STRONG.value == "STRONG"
        assert LevelStrength.MODERATE.value == "MODERATE"
        assert LevelStrength.WEAK.value == "WEAK"
        assert LevelStrength.VERY_WEAK.value == "VERY_WEAK"

    def test_custom_strength_weights(self):
        """Test that custom strength weights are normalized"""
        detector = SupportResistanceDetector(
            touch_weight=0.5,
            recency_weight=0.3,
            volume_weight=0.2
        )

        # Weights should sum to 1.0
        total_weight = detector.touch_weight + detector.recency_weight + detector.volume_weight
        assert total_weight == pytest.approx(1.0, abs=0.001), \
            "Weights should be normalized to sum to 1.0"


# =============================================================================
# TEST CLASS: Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for complete workflows"""

    def test_full_workflow_with_simple_data(self, detector_default, sample_df_simple):
        """Test complete workflow: detect levels, check proximity, find next levels"""
        # Step 1: Find support and resistance levels
        support_levels = detector_default.find_support_levels(sample_df_simple, lookback=100)
        resistance_levels = detector_default.find_resistance_levels(sample_df_simple, lookback=100)

        assert len(support_levels) > 0, "Should find support levels"
        assert len(resistance_levels) > 0, "Should find resistance levels"

        # Step 2: Check if current price is near any level
        current_price = 98.0  # Near support
        is_near_sup, nearest_sup = detector_default.is_near_support(
            current_price, support_levels, tolerance_pct=0.01
        )

        # Step 3: Find next resistance for potential take profit
        if is_near_sup:
            next_res = detector_default.find_next_resistance(current_price, resistance_levels)
            if next_res:
                assert next_res.price > current_price, \
                    "Next resistance should be above current price"

    def test_trending_market_detection(self, detector_default, sample_df_trending):
        """Test level detection in trending market"""
        support_levels = detector_default.find_support_levels(sample_df_trending, lookback=150)
        resistance_levels = detector_default.find_resistance_levels(sample_df_trending, lookback=150)

        # In trending market, should find multiple levels at different price ranges
        if len(support_levels) > 1:
            # Support levels should have increasing prices in uptrend
            prices = [level.price for level in support_levels]
            # At least some variation in support prices
            assert max(prices) > min(prices), "Should find supports at different levels"

    def test_performance_with_large_dataset(self, detector_default):
        """Test performance with large dataset"""
        import time

        # Create large dataset (1000 candles)
        np.random.seed(45)
        large_df = pd.DataFrame({
            'timestamp': pd.date_range('2025-01-01', periods=1000, freq='1H'),
            'open': np.random.uniform(95, 105, 1000),
            'high': np.random.uniform(100, 110, 1000),
            'low': np.random.uniform(90, 100, 1000),
            'close': np.random.uniform(95, 105, 1000),
            'volume': np.random.uniform(1000, 5000, 1000),
        })

        # Measure execution time
        start_time = time.time()
        support_levels = detector_default.find_support_levels(large_df, lookback=1000)
        resistance_levels = detector_default.find_resistance_levels(large_df, lookback=1000)
        execution_time = time.time() - start_time

        # Should complete in reasonable time (< 5 seconds for 1000 candles)
        assert execution_time < 5.0, \
            f"Detection should complete in < 5 seconds, took {execution_time:.2f}s"

        # Should return valid results
        assert isinstance(support_levels, list), "Should return list"
        assert isinstance(resistance_levels, list), "Should return list"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
