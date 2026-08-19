"""
Support and Resistance Level Detector
======================================
Purpose: Detect support and resistance levels from OHLCV price data

This utility provides:
- Swing high/low detection using configurable window sizes
- Support/Resistance level identification based on price touches
- Level strength calculation based on:
  - Number of touches (bounces)
  - Age/recency of touches
  - Volume at touches (if available)
- Methods to check proximity to support/resistance levels

Research-Backed Implementation (2025-12-07):
- Multiple-touch confirmation for valid levels
- Volume-weighted level strength
- Time-decay weighting for recency
- Dynamic tolerance based on ATR

Author: Phase 2.1.3 Enhancement
Date: 2025-12-07
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Configure logging for this module
logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# Swing detection parameters
# Window size determines how many candles on each side to check for swing points
DEFAULT_SWING_WINDOW = 5  # 5 candles on each side = 11 total candles for swing detection

# Level clustering parameters
# Levels within this percentage are considered the same level
LEVEL_CLUSTER_TOLERANCE_PCT = 0.003  # 0.3% - cluster similar price levels together

# Minimum touches required for a valid support/resistance level
MIN_TOUCHES_FOR_LEVEL = 2  # At least 2 touches to confirm a level

# Level strength calculation weights
TOUCH_COUNT_WEIGHT = 0.40  # 40% weight for number of touches
RECENCY_WEIGHT = 0.35      # 35% weight for how recent the touches are
VOLUME_WEIGHT = 0.25       # 25% weight for volume at touches

# Time decay parameters for recency calculation
# Older touches contribute less to level strength
RECENCY_DECAY_FACTOR = 0.95  # Exponential decay per period

# Maximum lookback for level detection (in candles)
MAX_LOOKBACK_PERIODS = 200


class LevelStrength(Enum):
    """
    Classification of support/resistance level strength

    Based on number of touches, recency, and volume confirmation
    """
    STRONG = "STRONG"      # 70%+ strength score, multiple recent touches with volume
    MODERATE = "MODERATE"  # 50-70% strength score, some confirmations
    WEAK = "WEAK"          # 30-50% strength score, minimal confirmation
    VERY_WEAK = "VERY_WEAK"  # <30% strength score, single touch or old


@dataclass
class Touch:
    """
    Represents a single touch of a support/resistance level

    Attributes:
        timestamp: When the touch occurred (candle index or datetime)
        price: The exact price at the touch
        volume: Volume at the touch candle (for weighting)
        touch_type: 'bounce' or 'test' (bounce = reversed, test = through)
        candle_index: Index in the DataFrame for recency calculation
    """
    timestamp: datetime
    price: float
    volume: float
    touch_type: str  # 'bounce' or 'test'
    candle_index: int


@dataclass
class SupportLevel:
    """
    Represents a support level detected in price data

    Support levels are price zones where buying pressure historically
    prevented further price decline.

    Attributes:
        price: The price level of support
        strength: Calculated strength score (0.0-1.0)
        strength_category: LevelStrength enum classification
        touch_count: Number of times price touched this level
        last_touch_time: Timestamp of the most recent touch
        touches: List of individual Touch objects
        zone_low: Lower bound of the support zone
        zone_high: Upper bound of the support zone
        avg_volume_at_touches: Average volume when level was touched
        metadata: Additional information about the level
    """
    price: float
    strength: float
    strength_category: LevelStrength
    touch_count: int
    last_touch_time: datetime
    touches: List[Touch] = field(default_factory=list)
    zone_low: float = 0.0
    zone_high: float = 0.0
    avg_volume_at_touches: float = 0.0
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        """
        Calculate zone boundaries if not provided

        Zone is +/- 0.2% of the level price by default
        """
        if self.zone_low == 0.0:
            self.zone_low = self.price * 0.998  # -0.2%
        if self.zone_high == 0.0:
            self.zone_high = self.price * 1.002  # +0.2%


@dataclass
class ResistanceLevel:
    """
    Represents a resistance level detected in price data

    Resistance levels are price zones where selling pressure historically
    prevented further price advance.

    Attributes:
        price: The price level of resistance
        strength: Calculated strength score (0.0-1.0)
        strength_category: LevelStrength enum classification
        touch_count: Number of times price touched this level
        last_touch_time: Timestamp of the most recent touch
        touches: List of individual Touch objects
        zone_low: Lower bound of the resistance zone
        zone_high: Upper bound of the resistance zone
        avg_volume_at_touches: Average volume when level was touched
        metadata: Additional information about the level
    """
    price: float
    strength: float
    strength_category: LevelStrength
    touch_count: int
    last_touch_time: datetime
    touches: List[Touch] = field(default_factory=list)
    zone_low: float = 0.0
    zone_high: float = 0.0
    avg_volume_at_touches: float = 0.0
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        """
        Calculate zone boundaries if not provided

        Zone is +/- 0.2% of the level price by default
        """
        if self.zone_low == 0.0:
            self.zone_low = self.price * 0.998  # -0.2%
        if self.zone_high == 0.0:
            self.zone_high = self.price * 1.002  # +0.2%


class SupportResistanceDetector:
    """
    Detects support and resistance levels from OHLCV price data

    This class provides methods to:
    1. Detect swing highs and lows using a window-based approach
    2. Cluster nearby price levels into support/resistance zones
    3. Calculate level strength based on touches, recency, and volume
    4. Check if current price is near support or resistance

    Research-Backed Implementation:
    - Multi-touch confirmation reduces false levels
    - Volume weighting identifies levels with conviction
    - Time decay ensures recent levels are prioritized
    - Adaptive tolerance based on price volatility

    Example Usage:
        detector = SupportResistanceDetector(swing_window=5)
        support_levels = detector.find_support_levels(df, lookback=100)
        resistance_levels = detector.find_resistance_levels(df, lookback=100)

        is_near, level = detector.is_near_support(
            current_price=95000.0,
            levels=support_levels,
            tolerance_pct=0.005
        )
    """

    def __init__(
        self,
        swing_window: int = DEFAULT_SWING_WINDOW,
        cluster_tolerance_pct: float = LEVEL_CLUSTER_TOLERANCE_PCT,
        min_touches: int = MIN_TOUCHES_FOR_LEVEL,
        touch_weight: float = TOUCH_COUNT_WEIGHT,
        recency_weight: float = RECENCY_WEIGHT,
        volume_weight: float = VOLUME_WEIGHT,
    ):
        """
        Initialize the support/resistance detector

        Args:
            swing_window: Number of candles on each side for swing detection
            cluster_tolerance_pct: Percentage tolerance for clustering levels
            min_touches: Minimum touches required for valid level
            touch_weight: Weight for touch count in strength calculation
            recency_weight: Weight for recency in strength calculation
            volume_weight: Weight for volume in strength calculation
        """
        # Configuration parameters
        self.swing_window = swing_window
        self.cluster_tolerance_pct = cluster_tolerance_pct
        self.min_touches = min_touches

        # Strength calculation weights (must sum to 1.0)
        total_weight = touch_weight + recency_weight + volume_weight
        self.touch_weight = touch_weight / total_weight
        self.recency_weight = recency_weight / total_weight
        self.volume_weight = volume_weight / total_weight

        # Logging initialization
        logger.info(
            f"SupportResistanceDetector initialized: "
            f"swing_window={swing_window}, "
            f"cluster_tolerance={cluster_tolerance_pct*100:.2f}%, "
            f"min_touches={min_touches}"
        )
        logger.debug(
            f"Strength weights: touch={self.touch_weight:.2f}, "
            f"recency={self.recency_weight:.2f}, volume={self.volume_weight:.2f}"
        )

    def _detect_swing_lows(
        self,
        df: pd.DataFrame,
        lookback: int = 100
    ) -> List[Tuple[int, float, float, datetime]]:
        """
        Detect swing lows (potential support levels) in price data

        A swing low is a candle whose low is lower than the lows of
        `swing_window` candles on each side.

        Args:
            df: DataFrame with 'low', 'volume', and optionally 'timestamp' columns
            lookback: Number of candles to analyze

        Returns:
            List of tuples: (candle_index, low_price, volume, timestamp)
        """
        # Limit lookback to available data
        data = df.tail(min(lookback, len(df))).copy()

        # Ensure we have enough data
        if len(data) < (self.swing_window * 2 + 1):
            logger.warning(
                f"Not enough data for swing detection. "
                f"Need {self.swing_window * 2 + 1}, got {len(data)}"
            )
            return []

        swing_lows = []

        # Iterate through candles, excluding edges
        for i in range(self.swing_window, len(data) - self.swing_window):
            # Get the current candle's low
            current_low = data['low'].iloc[i]

            # Check if current low is lower than all surrounding lows
            is_swing_low = True

            # Check left side (preceding candles)
            for j in range(1, self.swing_window + 1):
                if data['low'].iloc[i - j] <= current_low:
                    is_swing_low = False
                    break

            # Check right side (following candles)
            if is_swing_low:
                for j in range(1, self.swing_window + 1):
                    if data['low'].iloc[i + j] <= current_low:
                        is_swing_low = False
                        break

            # If valid swing low, record it
            if is_swing_low:
                # Get the original index in the full DataFrame
                original_idx = len(df) - len(data) + i

                # Get volume at this candle
                volume = data['volume'].iloc[i] if 'volume' in data.columns else 0.0

                # Get timestamp (use index if no timestamp column)
                if 'timestamp' in data.columns:
                    timestamp = data['timestamp'].iloc[i]
                elif 'datetime' in data.columns:
                    timestamp = data['datetime'].iloc[i]
                else:
                    timestamp = datetime.now()

                swing_lows.append((original_idx, current_low, volume, timestamp))

        logger.debug(f"Detected {len(swing_lows)} swing lows in {len(data)} candles")
        return swing_lows

    def _detect_swing_highs(
        self,
        df: pd.DataFrame,
        lookback: int = 100
    ) -> List[Tuple[int, float, float, datetime]]:
        """
        Detect swing highs (potential resistance levels) in price data

        A swing high is a candle whose high is higher than the highs of
        `swing_window` candles on each side.

        Args:
            df: DataFrame with 'high', 'volume', and optionally 'timestamp' columns
            lookback: Number of candles to analyze

        Returns:
            List of tuples: (candle_index, high_price, volume, timestamp)
        """
        # Limit lookback to available data
        data = df.tail(min(lookback, len(df))).copy()

        # Ensure we have enough data
        if len(data) < (self.swing_window * 2 + 1):
            logger.warning(
                f"Not enough data for swing detection. "
                f"Need {self.swing_window * 2 + 1}, got {len(data)}"
            )
            return []

        swing_highs = []

        # Iterate through candles, excluding edges
        for i in range(self.swing_window, len(data) - self.swing_window):
            # Get the current candle's high
            current_high = data['high'].iloc[i]

            # Check if current high is higher than all surrounding highs
            is_swing_high = True

            # Check left side (preceding candles)
            for j in range(1, self.swing_window + 1):
                if data['high'].iloc[i - j] >= current_high:
                    is_swing_high = False
                    break

            # Check right side (following candles)
            if is_swing_high:
                for j in range(1, self.swing_window + 1):
                    if data['high'].iloc[i + j] >= current_high:
                        is_swing_high = False
                        break

            # If valid swing high, record it
            if is_swing_high:
                # Get the original index in the full DataFrame
                original_idx = len(df) - len(data) + i

                # Get volume at this candle
                volume = data['volume'].iloc[i] if 'volume' in data.columns else 0.0

                # Get timestamp (use index if no timestamp column)
                if 'timestamp' in data.columns:
                    timestamp = data['timestamp'].iloc[i]
                elif 'datetime' in data.columns:
                    timestamp = data['datetime'].iloc[i]
                else:
                    timestamp = datetime.now()

                swing_highs.append((original_idx, current_high, volume, timestamp))

        logger.debug(f"Detected {len(swing_highs)} swing highs in {len(data)} candles")
        return swing_highs

    def _cluster_levels(
        self,
        points: List[Tuple[int, float, float, datetime]],
        tolerance_pct: float
    ) -> List[Dict]:
        """
        Cluster nearby price points into support/resistance zones

        Points within tolerance_pct of each other are grouped together.
        This prevents having many levels very close to each other.

        Args:
            points: List of (index, price, volume, timestamp) tuples
            tolerance_pct: Maximum percentage difference for clustering

        Returns:
            List of cluster dicts with level_price, touches, avg_volume, etc.
        """
        if not points:
            return []

        # Sort by price for clustering
        sorted_points = sorted(points, key=lambda x: x[1])

        clusters = []
        current_cluster = [sorted_points[0]]

        for i in range(1, len(sorted_points)):
            current_price = sorted_points[i][1]
            cluster_avg = sum(p[1] for p in current_cluster) / len(current_cluster)

            # Check if within tolerance of cluster average
            if abs(current_price - cluster_avg) / cluster_avg <= tolerance_pct:
                # Add to current cluster
                current_cluster.append(sorted_points[i])
            else:
                # Save current cluster and start new one
                if current_cluster:
                    clusters.append(self._process_cluster(current_cluster))
                current_cluster = [sorted_points[i]]

        # Don't forget the last cluster
        if current_cluster:
            clusters.append(self._process_cluster(current_cluster))

        logger.debug(
            f"Clustered {len(points)} points into {len(clusters)} levels"
        )
        return clusters

    def _process_cluster(
        self,
        cluster_points: List[Tuple[int, float, float, datetime]]
    ) -> Dict:
        """
        Process a cluster of points into a level dictionary

        Args:
            cluster_points: List of (index, price, volume, timestamp) tuples

        Returns:
            Dict with level_price, touches, volumes, timestamps, indices
        """
        prices = [p[1] for p in cluster_points]
        volumes = [p[2] for p in cluster_points]
        timestamps = [p[3] for p in cluster_points]
        indices = [p[0] for p in cluster_points]

        return {
            'level_price': sum(prices) / len(prices),  # Average price
            'touch_count': len(cluster_points),
            'touches': [
                Touch(
                    timestamp=cluster_points[i][3],
                    price=cluster_points[i][1],
                    volume=cluster_points[i][2],
                    touch_type='bounce',
                    candle_index=cluster_points[i][0]
                )
                for i in range(len(cluster_points))
            ],
            'volumes': volumes,
            'timestamps': timestamps,
            'indices': indices,
            'min_price': min(prices),
            'max_price': max(prices),
        }

    def _calculate_level_strength(
        self,
        cluster: Dict,
        total_candles: int,
        avg_volume: float
    ) -> Tuple[float, LevelStrength]:
        """
        Calculate the strength of a support/resistance level

        Strength is calculated based on:
        1. Touch count (more touches = stronger level)
        2. Recency (recent touches weighted more)
        3. Volume (higher volume at touches = stronger level)

        Args:
            cluster: Cluster dict from _process_cluster
            total_candles: Total number of candles in analysis period
            avg_volume: Average volume across all candles

        Returns:
            Tuple of (strength_score, LevelStrength enum)
        """
        # 1. Touch count score (normalized to 0-1)
        # More than 5 touches is considered maximum
        touch_score = min(cluster['touch_count'] / 5.0, 1.0)

        # 2. Recency score (exponential decay based on candle age)
        recency_scores = []
        for idx in cluster['indices']:
            # Calculate how many periods ago this touch occurred
            periods_ago = total_candles - idx
            # Apply exponential decay
            recency = RECENCY_DECAY_FACTOR ** periods_ago
            recency_scores.append(recency)

        # Average recency score (weighted by how recent touches are)
        recency_score = sum(recency_scores) / len(recency_scores) if recency_scores else 0.0

        # 3. Volume score (relative to average)
        if avg_volume > 0 and cluster['volumes']:
            avg_touch_volume = sum(cluster['volumes']) / len(cluster['volumes'])
            # Normalize: 1.0 if at average, >1 if above, <1 if below
            volume_ratio = avg_touch_volume / avg_volume
            # Cap at 2x average for scoring
            volume_score = min(volume_ratio / 2.0, 1.0)
        else:
            volume_score = 0.5  # Default to neutral if no volume data

        # Combine scores with weights
        total_strength = (
            touch_score * self.touch_weight +
            recency_score * self.recency_weight +
            volume_score * self.volume_weight
        )

        # Classify strength
        if total_strength >= 0.70:
            strength_category = LevelStrength.STRONG
        elif total_strength >= 0.50:
            strength_category = LevelStrength.MODERATE
        elif total_strength >= 0.30:
            strength_category = LevelStrength.WEAK
        else:
            strength_category = LevelStrength.VERY_WEAK

        logger.debug(
            f"Level strength calculation: "
            f"touch={touch_score:.2f}*{self.touch_weight:.2f} + "
            f"recency={recency_score:.2f}*{self.recency_weight:.2f} + "
            f"volume={volume_score:.2f}*{self.volume_weight:.2f} = "
            f"{total_strength:.2f} ({strength_category.value})"
        )

        return total_strength, strength_category

    def find_support_levels(
        self,
        df: pd.DataFrame,
        lookback: int = 100
    ) -> List[SupportLevel]:
        """
        Find support levels in the given price data

        Process:
        1. Detect all swing lows in the lookback period
        2. Cluster nearby lows into support zones
        3. Filter by minimum touch count
        4. Calculate strength for each level
        5. Sort by strength (strongest first)

        Args:
            df: DataFrame with OHLCV data (columns: open, high, low, close, volume)
            lookback: Number of candles to analyze (default: 100)

        Returns:
            List of SupportLevel objects, sorted by strength descending
        """
        logger.info(f"Finding support levels with lookback={lookback}")

        # Validate input
        required_columns = ['high', 'low', 'close']
        if not all(col in df.columns for col in required_columns):
            logger.error(f"DataFrame missing required columns: {required_columns}")
            return []

        # Detect swing lows
        swing_lows = self._detect_swing_lows(df, lookback)

        if not swing_lows:
            logger.warning("No swing lows detected")
            return []

        # Cluster nearby levels
        clusters = self._cluster_levels(swing_lows, self.cluster_tolerance_pct)

        # Filter by minimum touches and calculate strength
        avg_volume = df['volume'].mean() if 'volume' in df.columns else 0.0
        total_candles = len(df)

        support_levels = []

        for cluster in clusters:
            # Skip if below minimum touches
            if cluster['touch_count'] < self.min_touches:
                continue

            # Calculate strength
            strength, strength_category = self._calculate_level_strength(
                cluster, total_candles, avg_volume
            )

            # Get last touch timestamp
            last_touch_time = max(cluster['timestamps'])

            # Calculate average volume at touches
            avg_touch_volume = (
                sum(cluster['volumes']) / len(cluster['volumes'])
                if cluster['volumes'] else 0.0
            )

            # Create SupportLevel object
            level = SupportLevel(
                # Trigger compared against market price, closed at market —
                # no exchange tick precision at this layer. round(price, 2)
                # collapsed zone_low and zone_high onto one tick at ADA scale
                # (PRICE-01).
                price=float(cluster['level_price']),
                strength=round(strength, 4),  # non-price-round
                strength_category=strength_category,
                touch_count=cluster['touch_count'],
                last_touch_time=last_touch_time,
                touches=cluster['touches'],
                zone_low=float(cluster['min_price']),
                zone_high=float(cluster['max_price']),
                avg_volume_at_touches=round(avg_touch_volume, 2),  # non-price-round
                metadata={
                    'lookback': lookback,
                    'swing_window': self.swing_window,
                    'detection_time': datetime.now().isoformat()
                }
            )
            support_levels.append(level)

        # Sort by strength (strongest first)
        support_levels.sort(key=lambda x: x.strength, reverse=True)

        logger.info(
            f"Found {len(support_levels)} support levels "
            f"(from {len(swing_lows)} swing lows)"
        )

        for i, level in enumerate(support_levels[:5]):  # Log top 5
            logger.debug(
                f"Support #{i+1}: price={level.price:.2f}, "
                f"strength={level.strength:.2f} ({level.strength_category.value}), "
                f"touches={level.touch_count}"
            )

        return support_levels

    def find_resistance_levels(
        self,
        df: pd.DataFrame,
        lookback: int = 100
    ) -> List[ResistanceLevel]:
        """
        Find resistance levels in the given price data

        Process:
        1. Detect all swing highs in the lookback period
        2. Cluster nearby highs into resistance zones
        3. Filter by minimum touch count
        4. Calculate strength for each level
        5. Sort by strength (strongest first)

        Args:
            df: DataFrame with OHLCV data (columns: open, high, low, close, volume)
            lookback: Number of candles to analyze (default: 100)

        Returns:
            List of ResistanceLevel objects, sorted by strength descending
        """
        logger.info(f"Finding resistance levels with lookback={lookback}")

        # Validate input
        required_columns = ['high', 'low', 'close']
        if not all(col in df.columns for col in required_columns):
            logger.error(f"DataFrame missing required columns: {required_columns}")
            return []

        # Detect swing highs
        swing_highs = self._detect_swing_highs(df, lookback)

        if not swing_highs:
            logger.warning("No swing highs detected")
            return []

        # Cluster nearby levels
        clusters = self._cluster_levels(swing_highs, self.cluster_tolerance_pct)

        # Filter by minimum touches and calculate strength
        avg_volume = df['volume'].mean() if 'volume' in df.columns else 0.0
        total_candles = len(df)

        resistance_levels = []

        for cluster in clusters:
            # Skip if below minimum touches
            if cluster['touch_count'] < self.min_touches:
                continue

            # Calculate strength
            strength, strength_category = self._calculate_level_strength(
                cluster, total_candles, avg_volume
            )

            # Get last touch timestamp
            last_touch_time = max(cluster['timestamps'])

            # Calculate average volume at touches
            avg_touch_volume = (
                sum(cluster['volumes']) / len(cluster['volumes'])
                if cluster['volumes'] else 0.0
            )

            # Create ResistanceLevel object
            level = ResistanceLevel(
                price=float(cluster['level_price']),
                strength=round(strength, 4),  # non-price-round
                strength_category=strength_category,
                touch_count=cluster['touch_count'],
                last_touch_time=last_touch_time,
                touches=cluster['touches'],
                zone_low=float(cluster['min_price']),
                zone_high=float(cluster['max_price']),
                avg_volume_at_touches=round(avg_touch_volume, 2),  # non-price-round
                metadata={
                    'lookback': lookback,
                    'swing_window': self.swing_window,
                    'detection_time': datetime.now().isoformat()
                }
            )
            resistance_levels.append(level)

        # Sort by strength (strongest first)
        resistance_levels.sort(key=lambda x: x.strength, reverse=True)

        logger.info(
            f"Found {len(resistance_levels)} resistance levels "
            f"(from {len(swing_highs)} swing highs)"
        )

        for i, level in enumerate(resistance_levels[:5]):  # Log top 5
            logger.debug(
                f"Resistance #{i+1}: price={level.price:.2f}, "
                f"strength={level.strength:.2f} ({level.strength_category.value}), "
                f"touches={level.touch_count}"
            )

        return resistance_levels

    def is_near_support(
        self,
        current_price: float,
        levels: List[SupportLevel],
        tolerance_pct: float = 0.005
    ) -> Tuple[bool, Optional[SupportLevel]]:
        """
        Check if current price is near a support level

        A price is considered "near" support if it's within tolerance_pct
        above the support level (bounce zone).

        Args:
            current_price: The current market price
            levels: List of SupportLevel objects to check against
            tolerance_pct: Percentage tolerance (default: 0.5%)

        Returns:
            Tuple of (is_near_support: bool, nearest_level: Optional[SupportLevel])
        """
        if not levels or current_price <= 0:
            return False, None

        nearest_level = None
        min_distance_pct = float('inf')

        for level in levels:
            # Calculate distance from price to support level
            # Positive distance means price is above support (expected)
            distance_pct = (current_price - level.price) / level.price

            # Check if within tolerance above support level
            # We want: 0 < distance_pct <= tolerance_pct
            # This means price is just above support, potential bounce zone
            if 0 <= distance_pct <= tolerance_pct:
                if distance_pct < min_distance_pct:
                    min_distance_pct = distance_pct
                    nearest_level = level

            # Also check if price is slightly below support (testing level)
            # Allow up to half the tolerance below
            elif -tolerance_pct/2 <= distance_pct < 0:
                if abs(distance_pct) < min_distance_pct:
                    min_distance_pct = abs(distance_pct)
                    nearest_level = level

        is_near = nearest_level is not None

        if is_near:
            logger.info(
                f"Price {current_price:.2f} is near support level "
                f"{nearest_level.price:.2f} "
                f"(distance: {min_distance_pct*100:.3f}%, "
                f"strength: {nearest_level.strength:.2f})"
            )

        return is_near, nearest_level

    def is_near_resistance(
        self,
        current_price: float,
        levels: List[ResistanceLevel],
        tolerance_pct: float = 0.005
    ) -> Tuple[bool, Optional[ResistanceLevel]]:
        """
        Check if current price is near a resistance level

        A price is considered "near" resistance if it's within tolerance_pct
        below the resistance level (rejection zone).

        Args:
            current_price: The current market price
            levels: List of ResistanceLevel objects to check against
            tolerance_pct: Percentage tolerance (default: 0.5%)

        Returns:
            Tuple of (is_near_resistance: bool, nearest_level: Optional[ResistanceLevel])
        """
        if not levels or current_price <= 0:
            return False, None

        nearest_level = None
        min_distance_pct = float('inf')

        for level in levels:
            # Calculate distance from price to resistance level
            # Negative distance means price is below resistance (expected)
            distance_pct = (current_price - level.price) / level.price

            # Check if within tolerance below resistance level
            # We want: -tolerance_pct <= distance_pct < 0
            # This means price is just below resistance, potential rejection zone
            if -tolerance_pct <= distance_pct < 0:
                if abs(distance_pct) < min_distance_pct:
                    min_distance_pct = abs(distance_pct)
                    nearest_level = level

            # Also check if price is slightly above resistance (testing level)
            # Allow up to half the tolerance above
            elif 0 <= distance_pct <= tolerance_pct/2:
                if distance_pct < min_distance_pct:
                    min_distance_pct = distance_pct
                    nearest_level = level

        is_near = nearest_level is not None

        if is_near:
            logger.info(
                f"Price {current_price:.2f} is near resistance level "
                f"{nearest_level.price:.2f} "
                f"(distance: {min_distance_pct*100:.3f}%, "
                f"strength: {nearest_level.strength:.2f})"
            )

        return is_near, nearest_level

    def find_next_resistance(
        self,
        current_price: float,
        levels: List[ResistanceLevel]
    ) -> Optional[ResistanceLevel]:
        """
        Find the next resistance level above current price

        Useful for calculating take profit targets for long positions.

        Args:
            current_price: Current market price
            levels: List of ResistanceLevel objects

        Returns:
            The nearest resistance level above current price, or None
        """
        if not levels:
            return None

        # Filter levels above current price and sort by price ascending
        above_levels = [
            level for level in levels
            if level.price > current_price
        ]

        if not above_levels:
            return None

        # Return the nearest one (lowest price above current)
        return min(above_levels, key=lambda x: x.price)

    def find_next_support(
        self,
        current_price: float,
        levels: List[SupportLevel]
    ) -> Optional[SupportLevel]:
        """
        Find the next support level below current price

        Useful for calculating take profit targets for short positions.

        Args:
            current_price: Current market price
            levels: List of SupportLevel objects

        Returns:
            The nearest support level below current price, or None
        """
        if not levels:
            return None

        # Filter levels below current price and sort by price descending
        below_levels = [
            level for level in levels
            if level.price < current_price
        ]

        if not below_levels:
            return None

        # Return the nearest one (highest price below current)
        return max(below_levels, key=lambda x: x.price)


# =============================================================================
# MODULE-LEVEL CONVENIENCE FUNCTIONS
# =============================================================================

# Global detector instance with default settings
_default_detector: Optional[SupportResistanceDetector] = None


def get_detector(
    swing_window: int = DEFAULT_SWING_WINDOW,
    cluster_tolerance_pct: float = LEVEL_CLUSTER_TOLERANCE_PCT,
    min_touches: int = MIN_TOUCHES_FOR_LEVEL
) -> SupportResistanceDetector:
    """
    Get or create the default SupportResistanceDetector instance

    Args:
        swing_window: Number of candles for swing detection
        cluster_tolerance_pct: Tolerance for clustering levels
        min_touches: Minimum touches for valid level

    Returns:
        SupportResistanceDetector instance
    """
    global _default_detector

    if _default_detector is None:
        _default_detector = SupportResistanceDetector(
            swing_window=swing_window,
            cluster_tolerance_pct=cluster_tolerance_pct,
            min_touches=min_touches
        )

    return _default_detector


def find_support_levels(
    df: pd.DataFrame,
    lookback: int = 100
) -> List[SupportLevel]:
    """
    Convenience function to find support levels using default detector

    Args:
        df: DataFrame with OHLCV data
        lookback: Number of candles to analyze

    Returns:
        List of SupportLevel objects
    """
    detector = get_detector()
    return detector.find_support_levels(df, lookback)


def find_resistance_levels(
    df: pd.DataFrame,
    lookback: int = 100
) -> List[ResistanceLevel]:
    """
    Convenience function to find resistance levels using default detector

    Args:
        df: DataFrame with OHLCV data
        lookback: Number of candles to analyze

    Returns:
        List of ResistanceLevel objects
    """
    detector = get_detector()
    return detector.find_resistance_levels(df, lookback)


def is_near_support(
    current_price: float,
    levels: List[SupportLevel],
    tolerance_pct: float = 0.005
) -> Tuple[bool, Optional[SupportLevel]]:
    """
    Convenience function to check if price is near support

    Args:
        current_price: Current market price
        levels: List of support levels
        tolerance_pct: Percentage tolerance

    Returns:
        Tuple of (is_near, nearest_level)
    """
    detector = get_detector()
    return detector.is_near_support(current_price, levels, tolerance_pct)


def is_near_resistance(
    current_price: float,
    levels: List[ResistanceLevel],
    tolerance_pct: float = 0.005
) -> Tuple[bool, Optional[ResistanceLevel]]:
    """
    Convenience function to check if price is near resistance

    Args:
        current_price: Current market price
        levels: List of resistance levels
        tolerance_pct: Percentage tolerance

    Returns:
        Tuple of (is_near, nearest_level)
    """
    detector = get_detector()
    return detector.is_near_resistance(current_price, levels, tolerance_pct)
