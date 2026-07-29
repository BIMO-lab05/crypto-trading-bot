"""
Multi-Timeframe Analysis
Analyzes trends and signals across multiple timeframes for confirmation
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
import asyncio

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class TimeframeSignal(BaseModel):
    """Signal for a specific timeframe"""
    interval: str
    signal: str  # BUY, SELL, HOLD
    confidence: float
    rsi: Optional[float] = None
    macd_signal: Optional[str] = None
    trend: Optional[str] = None
    volume_confirmation: Optional[bool] = None


class MultiTimeframeAnalysis(BaseModel):
    """Analysis across multiple timeframes"""
    symbol: str
    timeframes: Dict[str, TimeframeSignal]

    # Alignment metrics
    alignment_score: float  # 0-100, how many timeframes agree
    consensus_signal: str  # BUY, SELL, HOLD
    consensus_confidence: float

    # Trend analysis
    short_term_trend: str  # 1m, 5m, 15m
    medium_term_trend: str  # 60m, 240m
    long_term_trend: str  # 1d

    # Overall assessment
    overall_signal: str
    signal_strength: float
    divergence_warnings: List[str]  # Any conflicting signals

    analysis_timestamp: datetime


class MultiTimeframeAnalyzer:
    """
    Analyzes crypto across multiple timeframes
    Provides confirmation when trends align across timeframes
    """

    # Timeframes to analyze (in minutes)
    TIMEFRAMES = {
        '1m': 1,
        '5m': 5,
        '15m': 15,
        '60m': 60,
        '240m': 240,  # 4h
        '1d': 1440,  # 24h
    }

    def __init__(self, market_data_url: str, technical_analysis_url: str):
        """
        Initialize multi-timeframe analyzer

        Args:
            market_data_url: URL for market data service
            technical_analysis_url: URL for technical analysis service
        """
        self.market_data_url = market_data_url
        self.technical_analysis_url = technical_analysis_url
        self.http_client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()

    async def analyze(
        self,
        symbol: str,
        timeframes: Optional[List[str]] = None
    ) -> MultiTimeframeAnalysis:
        """
        Analyze symbol across multiple timeframes

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            timeframes: List of timeframes to analyze (uses defaults if None)

        Returns:
            MultiTimeframeAnalysis with signals from all timeframes
        """
        if timeframes is None:
            timeframes = list(self.TIMEFRAMES.keys())

        logger.info(f"Analyzing {symbol} across {len(timeframes)} timeframes")

        # Fetch signals from all timeframes in parallel
        tasks = [
            self._get_timeframe_signal(symbol, tf)
            for tf in timeframes
        ]

        signals_list = await asyncio.gather(*tasks, return_exceptions=True)

        # Build timeframe signals dict
        timeframe_signals = {}
        for tf, signal in zip(timeframes, signals_list):
            if isinstance(signal, Exception):
                logger.warning(f"Failed to get signal for {tf}: {signal}")
                continue
            if signal:
                timeframe_signals[tf] = signal

        # Calculate alignment and consensus
        alignment_score = self._calculate_alignment(timeframe_signals)
        consensus_signal, consensus_confidence = self._calculate_consensus(timeframe_signals)

        # Analyze trends by timeframe groups
        short_term_trend = self._get_trend_for_group(timeframe_signals, ['1m', '5m', '15m'])
        medium_term_trend = self._get_trend_for_group(timeframe_signals, ['60m', '240m'])
        long_term_trend = self._get_trend_for_group(timeframe_signals, ['1d'])

        # Overall signal and strength
        overall_signal = self._determine_overall_signal(
            consensus_signal,
            short_term_trend,
            medium_term_trend,
            long_term_trend
        )

        signal_strength = self._calculate_signal_strength(
            alignment_score,
            consensus_confidence,
            len(timeframe_signals)
        )

        # Detect divergences
        divergence_warnings = self._detect_divergences(
            timeframe_signals,
            short_term_trend,
            medium_term_trend,
            long_term_trend
        )

        return MultiTimeframeAnalysis(
            symbol=symbol,
            timeframes=timeframe_signals,
            alignment_score=alignment_score,
            consensus_signal=consensus_signal,
            consensus_confidence=consensus_confidence,
            short_term_trend=short_term_trend,
            medium_term_trend=medium_term_trend,
            long_term_trend=long_term_trend,
            overall_signal=overall_signal,
            signal_strength=signal_strength,
            divergence_warnings=divergence_warnings,
            analysis_timestamp=datetime.utcnow()
        )

    async def _get_timeframe_signal(
        self,
        symbol: str,
        timeframe: str
    ) -> Optional[TimeframeSignal]:
        """
        Get trading signal for a specific timeframe

        Args:
            symbol: Trading pair
            timeframe: Timeframe (e.g., '60m')

        Returns:
            TimeframeSignal or None if failed
        """
        try:
            # Get interval in minutes
            interval_minutes = self.TIMEFRAMES.get(timeframe)
            if not interval_minutes:
                logger.warning(f"Unknown timeframe: {timeframe}")
                return None

            # Fetch indicators
            # Note: In production, you'd fetch multiple indicators
            # For simplicity, using a single endpoint that returns aggregated signal

            url = f"{self.technical_analysis_url}/api/v1/indicators/signal/{symbol}"
            # Normalize minute-denominated daily/weekly intervals to the
            # letter codes market-data stores them under ("1440" -> "D",
            # "10080" -> "W") — a raw "1440" query returns 0 rows.
            from app.fetcher import normalize_interval
            params = {"interval": normalize_interval(str(interval_minutes))}

            response = await self.http_client.get(url, params=params)

            if response.status_code != 200:
                logger.warning(f"Failed to get signal for {symbol} {timeframe}: {response.status_code}")
                return None

            data = response.json()

            # Extract signal information
            return TimeframeSignal(
                interval=timeframe,
                signal=data.get('signal', 'HOLD'),
                confidence=data.get('confidence', 0.5),
                rsi=data.get('rsi'),
                macd_signal=data.get('macd_signal'),
                trend=data.get('trend'),
                volume_confirmation=data.get('volume_confirmation')
            )

        except Exception as e:
            logger.error(f"Error getting signal for {symbol} {timeframe}: {e}")
            return None

    def _calculate_alignment(self, timeframe_signals: Dict[str, TimeframeSignal]) -> float:
        """
        Calculate how well timeframes align (0-100)

        100 = all agree on same signal
        0 = complete disagreement
        """
        if not timeframe_signals:
            return 0.0

        # Count signals
        signal_counts = {'BUY': 0, 'SELL': 0, 'HOLD': 0}

        for signal in timeframe_signals.values():
            signal_counts[signal.signal] += 1

        # Find dominant signal
        max_count = max(signal_counts.values())
        total_signals = len(timeframe_signals)

        # Alignment score = percentage with dominant signal
        alignment = (max_count / total_signals) * 100

        return round(alignment, 2)

    def _calculate_consensus(
        self,
        timeframe_signals: Dict[str, TimeframeSignal]
    ) -> tuple[str, float]:
        """
        Calculate consensus signal and confidence

        Returns:
            (consensus_signal, confidence)
        """
        if not timeframe_signals:
            return "HOLD", 0.0

        # Weight signals by confidence
        weighted_scores = {'BUY': 0.0, 'SELL': 0.0, 'HOLD': 0.0}
        total_weight = 0.0

        for signal in timeframe_signals.values():
            weighted_scores[signal.signal] += signal.confidence
            total_weight += signal.confidence

        # Normalize
        if total_weight > 0:
            for key in weighted_scores:
                weighted_scores[key] /= total_weight

        # Find consensus
        consensus = max(weighted_scores, key=weighted_scores.get)
        confidence = weighted_scores[consensus]

        return consensus, round(confidence, 3)

    def _get_trend_for_group(
        self,
        timeframe_signals: Dict[str, TimeframeSignal],
        timeframe_group: List[str]
    ) -> str:
        """Get trend for a group of timeframes"""
        # Collect signals from this group
        group_signals = [
            timeframe_signals[tf].signal
            for tf in timeframe_group
            if tf in timeframe_signals
        ]

        if not group_signals:
            return "NEUTRAL"

        # Count
        buy_count = group_signals.count('BUY')
        sell_count = group_signals.count('SELL')

        if buy_count > sell_count:
            return "BULLISH"
        elif sell_count > buy_count:
            return "BEARISH"
        else:
            return "NEUTRAL"

    def _determine_overall_signal(
        self,
        consensus: str,
        short_term: str,
        medium_term: str,
        long_term: str
    ) -> str:
        """
        Determine overall signal based on consensus and trends

        Priority: Long-term trend > Medium-term > Short-term
        But consensus can override if strong
        """
        # If all trends align, use that
        if short_term == medium_term == long_term:
            if short_term == "BULLISH":
                return "BUY"
            elif short_term == "BEARISH":
                return "SELL"

        # If long and medium align, use that
        if long_term == medium_term:
            if long_term == "BULLISH":
                return "BUY"
            elif long_term == "BEARISH":
                return "SELL"

        # Otherwise use consensus
        return consensus

    def _calculate_signal_strength(
        self,
        alignment_score: float,
        consensus_confidence: float,
        num_timeframes: int
    ) -> float:
        """
        Calculate overall signal strength (0-1)

        Factors:
        - Alignment across timeframes
        - Consensus confidence
        - Number of timeframes analyzed
        """
        # Normalize alignment to 0-1
        alignment_factor = alignment_score / 100.0

        # Bonus for analyzing more timeframes
        coverage_factor = min(1.0, num_timeframes / 6.0)

        # Combined strength
        strength = (alignment_factor * 0.4 + consensus_confidence * 0.4 + coverage_factor * 0.2)

        return round(strength, 3)

    def _detect_divergences(
        self,
        timeframe_signals: Dict[str, TimeframeSignal],
        short_term: str,
        medium_term: str,
        long_term: str
    ) -> List[str]:
        """
        Detect divergences between timeframes

        Returns list of warning messages
        """
        warnings = []

        # Check for trend divergences
        if short_term == "BULLISH" and medium_term == "BEARISH":
            warnings.append("Short-term bullish but medium-term bearish - potential reversal")

        if short_term == "BEARISH" and medium_term == "BULLISH":
            warnings.append("Short-term bearish but medium-term bullish - potential bounce")

        if medium_term != long_term and medium_term != "NEUTRAL" and long_term != "NEUTRAL":
            warnings.append(f"Medium-term ({medium_term}) diverges from long-term ({long_term})")

        # Check for extreme RSI divergences
        rsi_values = [
            s.rsi for s in timeframe_signals.values()
            if s.rsi is not None
        ]

        if len(rsi_values) >= 2:
            min_rsi = min(rsi_values)
            max_rsi = max(rsi_values)

            if min_rsi < 30 and max_rsi > 70:
                warnings.append("Extreme RSI divergence across timeframes")

        return warnings
