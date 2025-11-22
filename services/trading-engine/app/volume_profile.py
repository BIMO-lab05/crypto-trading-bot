"""
Volume Profile Calculator
Purpose: Calculate POC, VAH, VAL and volume distribution for trading signals
"""

import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VolumeProfileLevel:
    """Single price level in volume profile"""
    price: Decimal
    volume: Decimal
    buy_volume: Decimal
    sell_volume: Decimal
    percentage: float  # % of total volume at this level


@dataclass
class VolumeProfile:
    """Complete volume profile for a session/period"""
    symbol: str
    interval: str
    start_time: datetime
    end_time: datetime

    # Key levels
    poc: Decimal  # Point of Control (highest volume price)
    vah: Decimal  # Value Area High
    val: Decimal  # Value Area Low

    # Session bounds
    session_high: Decimal
    session_low: Decimal

    # Volume data
    total_volume: Decimal
    buy_volume: Decimal
    sell_volume: Decimal

    # Profile distribution
    levels: List[VolumeProfileLevel]

    # Value area stats
    value_area_volume_pct: float = 70.0  # % of volume in value area

    def get_price_position(self, current_price: Decimal) -> str:
        """
        Determine where current price is relative to value area

        Returns:
            ABOVE_VAH, IN_VALUE_AREA, AT_POC, BELOW_VAL
        """
        if current_price > self.vah:
            return "ABOVE_VAH"
        elif current_price < self.val:
            return "BELOW_VAL"
        elif abs(float(current_price - self.poc) / float(self.poc)) < 0.002:  # Within 0.2% of POC
            return "AT_POC"
        else:
            return "IN_VALUE_AREA"

    def get_volume_at_price(self, price: Decimal) -> Optional[VolumeProfileLevel]:
        """Get volume data at specific price level"""
        # Find closest price level
        closest_level = None
        min_distance = float('inf')

        for level in self.levels:
            distance = abs(float(price - level.price))
            if distance < min_distance:
                min_distance = distance
                closest_level = level

        return closest_level

    def get_support_resistance_levels(self) -> Dict[str, List[Decimal]]:
        """
        Get key support/resistance levels from volume profile

        Returns:
            Dictionary with 'support' and 'resistance' keys
        """
        # Sort levels by volume
        sorted_levels = sorted(self.levels, key=lambda x: x.volume, reverse=True)

        # Get top volume levels (excluding POC which we already have)
        top_levels = []
        for level in sorted_levels[:10]:  # Top 10 volume levels
            if abs(float(level.price - self.poc) / float(self.poc)) > 0.005:  # Not too close to POC
                top_levels.append(level.price)

        # Separate into support and resistance
        current_price = self.poc  # Use POC as reference

        support = sorted([p for p in top_levels if p < current_price], reverse=True)[:3]
        resistance = sorted([p for p in top_levels if p > current_price])[:3]

        return {
            "support": support,
            "resistance": resistance
        }


class VolumeProfileCalculator:
    """
    Calculate volume profile from price and volume data

    Implements session-based volume profile calculation similar to TradingView
    """

    def __init__(self, resolution: int = 30, value_area_pct: float = 70.0):
        """
        Initialize calculator

        Args:
            resolution: Number of price levels to divide range into
            value_area_pct: Percentage of volume for value area (default 70%)
        """
        self.resolution = resolution
        self.value_area_pct = value_area_pct
        logger.info(f"VolumeProfileCalculator initialized (resolution={resolution}, VA={value_area_pct}%)")

    def calculate_profile(
        self,
        symbol: str,
        interval: str,
        candles: List[Dict],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> VolumeProfile:
        """
        Calculate volume profile from candle data

        Args:
            symbol: Trading symbol
            interval: Timeframe interval
            candles: List of candle dicts with OHLCV data
            start_time: Session start (optional, will use first candle if not provided)
            end_time: Session end (optional, will use last candle if not provided)

        Returns:
            VolumeProfile object with all calculated levels
        """
        if not candles or len(candles) == 0:
            logger.warning(f"No candles provided for {symbol}")
            return None

        # Extract data from candles
        highs = [Decimal(str(c['high'])) for c in candles]
        lows = [Decimal(str(c['low'])) for c in candles]
        closes = [Decimal(str(c['close'])) for c in candles]
        opens = [Decimal(str(c['open'])) for c in candles]
        volumes = [Decimal(str(c['volume'])) for c in candles]
        timestamps = [c.get('timestamp', datetime.now()) for c in candles]

        # Session bounds
        session_high = max(highs)
        session_low = min(lows)
        session_start = start_time or timestamps[0]
        session_end = end_time or timestamps[-1]

        # Calculate price range and step size
        price_range = float(session_high - session_low)
        if price_range == 0:
            logger.warning(f"Zero price range for {symbol}, cannot calculate profile")
            return None

        step_size = price_range / self.resolution

        # Initialize volume arrays for each price level
        volume_levels = [Decimal(0) for _ in range(self.resolution)]
        buy_volume_levels = [Decimal(0) for _ in range(self.resolution)]
        sell_volume_levels = [Decimal(0) for _ in range(self.resolution)]

        # Distribute volume across price levels for each candle
        for i, candle_vol in enumerate(volumes):
            if candle_vol == 0:
                continue

            high = highs[i]
            low = lows[i]
            close = closes[i]
            open_price = opens[i]

            # Determine if candle is bullish or bearish
            is_bullish = close >= open_price

            # Calculate body and wick volumes (simplified)
            body_vol = candle_vol * Decimal("0.7")  # 70% in body
            wick_vol = candle_vol * Decimal("0.3")  # 30% in wicks

            # Distribute volume to price levels
            candle_range = float(high - low)
            if candle_range == 0:
                # Doji or single price - assign all volume to that level
                level_idx = int((float(close - session_low) / price_range) * (self.resolution - 1))
                level_idx = max(0, min(self.resolution - 1, level_idx))
                volume_levels[level_idx] += candle_vol
                if is_bullish:
                    buy_volume_levels[level_idx] += candle_vol
                else:
                    sell_volume_levels[level_idx] += candle_vol
                continue

            # Distribute body volume
            body_top = max(close, open_price)
            body_bot = min(close, open_price)

            for j in range(self.resolution):
                level_price = float(session_low) + (j + 0.5) * step_size
                level_top = float(session_low) + (j + 1) * step_size
                level_bot = float(session_low) + j * step_size

                # Check if this level overlaps with candle
                overlap_top = min(float(high), level_top)
                overlap_bot = max(float(low), level_bot)

                if overlap_top > overlap_bot:
                    # Calculate overlap percentage
                    overlap = overlap_top - overlap_bot
                    overlap_pct = overlap / candle_range

                    # Assign volume proportionally
                    level_vol = candle_vol * Decimal(str(overlap_pct))
                    volume_levels[j] += level_vol

                    # Assign to buy or sell based on candle direction
                    if is_bullish:
                        buy_volume_levels[j] += level_vol
                    else:
                        sell_volume_levels[j] += level_vol

        # Find POC (Point of Control) - highest volume level
        max_volume_idx = 0
        max_volume = volume_levels[0]
        for i, vol in enumerate(volume_levels):
            if vol > max_volume:
                max_volume = vol
                max_volume_idx = i

        poc_price = session_low + Decimal(str((max_volume_idx + 0.5) * step_size))

        # Calculate Value Area (70% of volume around POC)
        total_volume = sum(volume_levels)
        target_volume = total_volume * Decimal(str(self.value_area_pct / 100))

        # Expand from POC until we reach target volume
        va_volume = volume_levels[max_volume_idx]
        va_low_idx = max_volume_idx
        va_high_idx = max_volume_idx

        while va_volume < target_volume and (va_low_idx > 0 or va_high_idx < self.resolution - 1):
            # Check which direction has more volume
            vol_below = volume_levels[va_low_idx - 1] if va_low_idx > 0 else Decimal(0)
            vol_above = volume_levels[va_high_idx + 1] if va_high_idx < self.resolution - 1 else Decimal(0)

            if vol_above > vol_below:
                va_high_idx += 1
                va_volume += vol_above
            elif vol_below > Decimal(0):
                va_low_idx -= 1
                va_volume += vol_below
            else:
                break

        vah_price = session_low + Decimal(str((va_high_idx + 1) * step_size))
        val_price = session_low + Decimal(str(va_low_idx * step_size))

        # Create VolumeProfileLevel objects
        profile_levels = []
        for i in range(self.resolution):
            level_price = session_low + Decimal(str((i + 0.5) * step_size))
            level_vol = volume_levels[i]
            level_buy = buy_volume_levels[i]
            level_sell = sell_volume_levels[i]
            level_pct = float(level_vol / total_volume * 100) if total_volume > 0 else 0

            profile_levels.append(VolumeProfileLevel(
                price=level_price,
                volume=level_vol,
                buy_volume=level_buy,
                sell_volume=level_sell,
                percentage=level_pct
            ))

        # Calculate buy/sell volume totals
        total_buy_volume = sum(buy_volume_levels)
        total_sell_volume = sum(sell_volume_levels)

        return VolumeProfile(
            symbol=symbol,
            interval=interval,
            start_time=session_start,
            end_time=session_end,
            poc=poc_price,
            vah=vah_price,
            val=val_price,
            session_high=session_high,
            session_low=session_low,
            total_volume=total_volume,
            buy_volume=total_buy_volume,
            sell_volume=total_sell_volume,
            levels=profile_levels,
            value_area_volume_pct=self.value_area_pct
        )

    def calculate_session_profile(
        self,
        symbol: str,
        interval: str,
        candles: List[Dict],
        session_type: str = "daily"
    ) -> List[VolumeProfile]:
        """
        Calculate multiple volume profiles for different sessions

        Args:
            symbol: Trading symbol
            interval: Timeframe
            candles: All candles
            session_type: "daily", "4h", "weekly"

        Returns:
            List of VolumeProfile objects, one per session
        """
        if not candles:
            return []

        # Group candles by session
        sessions = self._group_by_session(candles, session_type)

        profiles = []
        for session_candles in sessions:
            if len(session_candles) > 0:
                profile = self.calculate_profile(
                    symbol=symbol,
                    interval=interval,
                    candles=session_candles
                )
                if profile:
                    profiles.append(profile)

        return profiles

    def _group_by_session(self, candles: List[Dict], session_type: str) -> List[List[Dict]]:
        """Group candles into sessions (daily, 4h, weekly)"""
        sessions = []
        current_session = []
        last_session_key = None

        for candle in candles:
            timestamp = candle.get('timestamp', datetime.now())

            # Determine session key based on type
            if session_type == "daily":
                session_key = timestamp.date()
            elif session_type == "4h":
                session_key = (timestamp.date(), timestamp.hour // 4)
            elif session_type == "weekly":
                session_key = timestamp.isocalendar()[:2]  # (year, week)
            else:
                session_key = timestamp.date()

            # Check if we need to start new session
            if last_session_key is not None and session_key != last_session_key:
                if current_session:
                    sessions.append(current_session)
                current_session = []

            current_session.append(candle)
            last_session_key = session_key

        # Add final session
        if current_session:
            sessions.append(current_session)

        return sessions


# Global instance
_vp_calculator: Optional[VolumeProfileCalculator] = None


def get_vp_calculator(resolution: int = 30, value_area_pct: float = 70.0) -> VolumeProfileCalculator:
    """Get or create global volume profile calculator"""
    global _vp_calculator
    if _vp_calculator is None:
        _vp_calculator = VolumeProfileCalculator(resolution, value_area_pct)
    return _vp_calculator


def reset_vp_calculator():
    """Reset global calculator (for testing)"""
    global _vp_calculator
    _vp_calculator = None
