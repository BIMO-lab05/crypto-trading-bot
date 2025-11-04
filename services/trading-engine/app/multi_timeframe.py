"""
Multi-Timeframe Analysis Module
Analyzes price trends across multiple timeframes for higher confidence signals

Phase 2 Component: Confirms signals by checking alignment across 6 timeframes
- 1m: Micro trends, precise entry timing
- 5m: Short-term momentum
- 15m: Intraday confirmation
- 60m: Hourly trend (Phase 1 baseline)
- 4h: Position trade context
- 1d: Major trend direction
"""

import logging
from typing import Dict, List, Optional
from enum import Enum
import asyncio
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)


class TrendDirection(str, Enum):
    """Trend direction classification"""
    STRONG_BULLISH = "STRONG_BULLISH"  # Very strong uptrend
    BULLISH = "BULLISH"                # Uptrend
    NEUTRAL = "NEUTRAL"                 # Sideways/ranging
    BEARISH = "BEARISH"                 # Downtrend
    STRONG_BEARISH = "STRONG_BEARISH"  # Very strong downtrend


class MultiTimeframeAnalyzer:
    """
    Analyzes trends across multiple timeframes for signal confirmation

    Timeframe hierarchy:
    - Longer timeframes = higher weight (more important)
    - All timeframes aligned = highest confidence
    - Mixed signals = lower confidence
    """

    # Timeframes to analyze (in minutes)
    TIMEFRAMES = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "60m": 60,      # Phase 1 baseline
        "4h": 240,
        "1d": 1440
    }

    # Weights for each timeframe (longer = more important)
    TIMEFRAME_WEIGHTS = {
        "1m": 1.0,   # Least important (noise)
        "5m": 1.5,
        "15m": 2.0,
        "60m": 3.0,  # Phase 1 baseline weight
        "4h": 4.0,
        "1d": 5.0    # Most important (major trend)
    }

    def __init__(self, ta_service_url: str = "http://localhost:8004"):
        """
        Initialize multi-timeframe analyzer

        Args:
            ta_service_url: URL of technical analysis service
        """
        self.ta_service_url = ta_service_url
        self.client = httpx.AsyncClient(timeout=10.0)

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

    async def get_timeframe_alignment(
        self,
        symbol: str
    ) -> Dict:
        """
        Analyze trend alignment across all timeframes

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")

        Returns:
            Dictionary with alignment analysis:
            {
                "alignment_score": 85,  # 0-100, higher = more aligned
                "trend_direction": "BULLISH",
                "confidence": 85,
                "timeframes": {
                    "1m": {"trend": "BULLISH", "strength": 60},
                    "5m": {"trend": "BULLISH", "strength": 70},
                    ...
                },
                "analysis": {
                    "bullish_count": 5,
                    "bearish_count": 0,
                    "neutral_count": 1,
                    "weighted_score": 85
                }
            }
        """
        try:
            # Fetch trend analysis for all timeframes in parallel
            tasks = [
                self._get_timeframe_trend(symbol, tf_name, tf_minutes)
                for tf_name, tf_minutes in self.TIMEFRAMES.items()
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            timeframes = {}
            successful_analyses = 0

            for tf_name, result in zip(self.TIMEFRAMES.keys(), results):
                if isinstance(result, Exception):
                    logger.warning(f"Failed to analyze {tf_name} for {symbol}: {result}")
                    timeframes[tf_name] = {
                        "trend": TrendDirection.NEUTRAL,
                        "strength": 0,
                        "error": str(result)
                    }
                else:
                    timeframes[tf_name] = result
                    successful_analyses += 1

            # Require at least 4 successful analyses
            if successful_analyses < 4:
                logger.warning(f"Only {successful_analyses}/6 timeframes analyzed for {symbol}")
                return self._create_low_confidence_response(timeframes)

            # Calculate alignment
            analysis = self._calculate_alignment(timeframes)

            # Determine overall trend direction
            trend_direction = self._determine_overall_trend(timeframes, analysis)

            # Calculate confidence based on alignment
            confidence = self._calculate_confidence(analysis, successful_analyses)

            return {
                "symbol": symbol,
                "timestamp": int(datetime.now().timestamp() * 1000),
                "alignment_score": analysis["weighted_score"],
                "trend_direction": trend_direction,
                "confidence": confidence,
                "timeframes": timeframes,
                "analysis": analysis,
                "recommendation": self._get_recommendation(
                    trend_direction,
                    confidence,
                    analysis["weighted_score"]
                )
            }

        except Exception as e:
            logger.error(f"Error in multi-timeframe analysis for {symbol}: {e}")
            return self._create_error_response(symbol, str(e))

    async def _get_timeframe_trend(
        self,
        symbol: str,
        timeframe_name: str,
        interval_minutes: int
    ) -> Dict:
        """
        Get trend analysis for a specific timeframe

        Uses EMA crossovers and trend filter from technical analysis service

        Args:
            symbol: Trading symbol
            timeframe_name: Name of timeframe (e.g., "60m")
            interval_minutes: Interval in minutes

        Returns:
            Dictionary with trend and strength:
            {
                "trend": "BULLISH"|"BEARISH"|"NEUTRAL",
                "strength": 0-100,
                "indicators": {...}
            }
        """
        try:
            # Fetch trend filter from TA service
            url = f"{self.ta_service_url}/api/v1/indicators/trend/{symbol}"
            params = {
                "interval": str(interval_minutes),
                "limit": 200  # Need history for reliable trend
            }

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if not data.get("success"):
                raise ValueError(f"TA service returned error: {data.get('message')}")

            trend_data = data.get("data", {})

            # Extract trend direction and strength
            trend = trend_data.get("trend", "NEUTRAL")
            strength = trend_data.get("strength", 50)

            # Map to our TrendDirection enum
            if trend == "BULLISH":
                if strength >= 80:
                    mapped_trend = TrendDirection.STRONG_BULLISH
                else:
                    mapped_trend = TrendDirection.BULLISH
            elif trend == "BEARISH":
                if strength >= 80:
                    mapped_trend = TrendDirection.STRONG_BEARISH
                else:
                    mapped_trend = TrendDirection.BEARISH
            else:
                mapped_trend = TrendDirection.NEUTRAL

            return {
                "trend": mapped_trend,
                "strength": strength,
                "indicators": {
                    "ema_50": trend_data.get("ema_50"),
                    "ema_200": trend_data.get("ema_200"),
                    "current_price": trend_data.get("current_price")
                }
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # No data available for this timeframe
                logger.debug(f"No data for {symbol} on {timeframe_name}")
                return {
                    "trend": TrendDirection.NEUTRAL,
                    "strength": 0,
                    "indicators": {},
                    "note": "Insufficient data"
                }
            raise

        except Exception as e:
            logger.error(f"Error fetching {timeframe_name} trend for {symbol}: {e}")
            raise

    def _calculate_alignment(self, timeframes: Dict) -> Dict:
        """
        Calculate how well timeframes are aligned

        Args:
            timeframes: Dictionary of timeframe analyses

        Returns:
            Analysis dictionary with counts and weighted score
        """
        # Count trend directions
        bullish_count = 0
        bearish_count = 0
        neutral_count = 0

        # Calculate weighted score
        weighted_bullish = 0.0
        weighted_bearish = 0.0
        total_weight = 0.0

        for tf_name, tf_data in timeframes.items():
            trend = tf_data.get("trend")
            strength = tf_data.get("strength", 0)
            weight = self.TIMEFRAME_WEIGHTS.get(tf_name, 1.0)

            # Count directions
            if trend in [TrendDirection.BULLISH, TrendDirection.STRONG_BULLISH]:
                bullish_count += 1
                weighted_bullish += weight * (strength / 100.0)
            elif trend in [TrendDirection.BEARISH, TrendDirection.STRONG_BEARISH]:
                bearish_count += 1
                weighted_bearish += weight * (strength / 100.0)
            else:
                neutral_count += 1

            total_weight += weight

        # Calculate weighted score (0-100)
        # Positive = bullish, negative = bearish, near zero = neutral
        if total_weight > 0:
            weighted_score = ((weighted_bullish - weighted_bearish) / total_weight) * 100
        else:
            weighted_score = 0

        # Calculate alignment percentage (how many agree with majority)
        total_timeframes = len(timeframes)
        majority_count = max(bullish_count, bearish_count, neutral_count)
        alignment_pct = (majority_count / total_timeframes * 100) if total_timeframes > 0 else 0

        return {
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
            "neutral_count": neutral_count,
            "weighted_score": round(weighted_score, 2),
            "alignment_percentage": round(alignment_pct, 2),
            "total_weight": total_weight
        }

    def _determine_overall_trend(
        self,
        timeframes: Dict,
        analysis: Dict
    ) -> TrendDirection:
        """
        Determine overall trend direction based on weighted analysis

        Priority:
        1. Weighted score (gives more importance to longer timeframes)
        2. Majority vote if weighted score is inconclusive

        Args:
            timeframes: Timeframe analyses
            analysis: Alignment analysis

        Returns:
            Overall trend direction
        """
        weighted_score = analysis["weighted_score"]

        # Strong signals (weighted score > 60)
        if weighted_score > 60:
            return TrendDirection.STRONG_BULLISH
        elif weighted_score < -60:
            return TrendDirection.STRONG_BEARISH

        # Medium signals (weighted score 30-60)
        elif weighted_score > 30:
            return TrendDirection.BULLISH
        elif weighted_score < -30:
            return TrendDirection.BEARISH

        # Weak/neutral signals
        else:
            # Use majority vote as fallback
            bullish = analysis["bullish_count"]
            bearish = analysis["bearish_count"]
            neutral = analysis["neutral_count"]

            if bullish > bearish and bullish > neutral:
                return TrendDirection.BULLISH
            elif bearish > bullish and bearish > neutral:
                return TrendDirection.BEARISH
            else:
                return TrendDirection.NEUTRAL

    def _calculate_confidence(
        self,
        analysis: Dict,
        successful_analyses: int
    ) -> int:
        """
        Calculate confidence score (0-100) based on alignment

        Higher confidence when:
        - More timeframes agree (alignment %)
        - Weighted score is strong
        - All timeframes analyzed successfully

        Args:
            analysis: Alignment analysis
            successful_analyses: Number of successful timeframe analyses

        Returns:
            Confidence score (0-100)
        """
        # Start with alignment percentage
        base_confidence = analysis["alignment_percentage"]

        # Boost for strong weighted score
        weighted_score_abs = abs(analysis["weighted_score"])
        if weighted_score_abs > 70:
            base_confidence += 15
        elif weighted_score_abs > 50:
            base_confidence += 10
        elif weighted_score_abs > 30:
            base_confidence += 5

        # Penalize for failed analyses
        if successful_analyses < 6:
            penalty = (6 - successful_analyses) * 5
            base_confidence -= penalty

        # Clamp to 0-100
        confidence = max(0, min(100, int(base_confidence)))

        return confidence

    def _get_recommendation(
        self,
        trend: TrendDirection,
        confidence: int,
        weighted_score: float
    ) -> str:
        """
        Generate trading recommendation based on analysis

        Args:
            trend: Overall trend direction
            confidence: Confidence score
            weighted_score: Weighted alignment score

        Returns:
            Trading recommendation string
        """
        if confidence < 50:
            return "AVOID - Low confidence, mixed signals across timeframes"

        if trend == TrendDirection.STRONG_BULLISH and confidence >= 75:
            return "STRONG BUY - All timeframes aligned bullish"
        elif trend == TrendDirection.BULLISH and confidence >= 60:
            return "BUY - Bullish trend with good confirmation"
        elif trend == TrendDirection.STRONG_BEARISH and confidence >= 75:
            return "STRONG SELL - All timeframes aligned bearish"
        elif trend == TrendDirection.BEARISH and confidence >= 60:
            return "SELL - Bearish trend with good confirmation"
        elif trend == TrendDirection.NEUTRAL:
            return "HOLD - Neutral/ranging market"
        else:
            return "HOLD - Insufficient alignment for clear signal"

    def _create_low_confidence_response(self, timeframes: Dict) -> Dict:
        """Create response for insufficient data"""
        return {
            "alignment_score": 0,
            "trend_direction": TrendDirection.NEUTRAL,
            "confidence": 0,
            "timeframes": timeframes,
            "analysis": {
                "bullish_count": 0,
                "bearish_count": 0,
                "neutral_count": len(timeframes),
                "weighted_score": 0
            },
            "recommendation": "HOLD - Insufficient data for analysis",
            "error": "Less than 4 timeframes available"
        }

    def _create_error_response(self, symbol: str, error: str) -> Dict:
        """Create error response"""
        return {
            "symbol": symbol,
            "timestamp": int(datetime.now().timestamp() * 1000),
            "alignment_score": 0,
            "trend_direction": TrendDirection.NEUTRAL,
            "confidence": 0,
            "timeframes": {},
            "analysis": {},
            "recommendation": "ERROR - Analysis failed",
            "error": error
        }


# Singleton instance
_analyzer: Optional[MultiTimeframeAnalyzer] = None


async def get_multi_timeframe_analyzer() -> MultiTimeframeAnalyzer:
    """Get multi-timeframe analyzer instance"""
    global _analyzer
    if _analyzer is None:
        _analyzer = MultiTimeframeAnalyzer()
    return _analyzer


async def close_multi_timeframe_analyzer():
    """Close analyzer and cleanup resources"""
    global _analyzer
    if _analyzer is not None:
        await _analyzer.close()
        _analyzer = None
