"""
Enhanced Aggregator - Phase 3
Integrates ML predictions, sentiment analysis, and multi-timeframe confirmation
"""

import logging
import httpx
from typing import Dict, Optional, Tuple
from datetime import datetime

from app.models import TradingSignal, IndicatorSignal, SignalAction
from app.config import get_settings
from .aggregator_core import CoreAggregator

logger = logging.getLogger(__name__)


class EnhancedAggregator(CoreAggregator):
    """
    ENHANCED AGGREGATOR: Phase 3 signal aggregation with ML + Sentiment + Multi-Timeframe

    Extends CoreAggregator with:
    - ML price predictions (LSTM)
    - Sentiment analysis (news + social)
    - Multi-timeframe confirmation

    Enhanced Pipeline:
    1. VOTER: Calculate preliminary signal from technical indicators
    2. ML PREDICTOR: Get AI price prediction and trend forecast
    3. SENTIMENT ANALYZER: Get market sentiment score
    4. MULTI-TIMEFRAME: Check alignment across timeframes
    5. GATEKEEPER: Block counter-trend trades
    6. VALIDATOR: Apply volume confidence penalty
    7. ENHANCED SCORING: Weighted combination of all signals
    8. REQUIREMENTS: Check consensus and minimum confidence
    9. OUTPUT: Enhanced TradingSignal with ML + Sentiment metadata

    Signal Weights:
    - Technical indicators: 40%
    - ML predictions: 30%
    - Sentiment: 15%
    - Multi-timeframe: 15%
    """

    def __init__(self, settings=None):
        """Initialize enhanced aggregator"""
        super().__init__(settings)

        self.settings = settings or get_settings()

        # HTTP client for Phase 3 services
        self.http_client = httpx.AsyncClient(timeout=30.0)

        # Service URLs
        self.ml_prediction_url = self.settings.ml_prediction_url
        self.sentiment_url = self.settings.sentiment_analysis_url
        self.technical_analysis_url = self.settings.technical_analysis_url

        # Phase 3 configuration
        self.use_ml = self.settings.enable_ml_predictions
        self.use_sentiment = self.settings.enable_sentiment_analysis
        self.use_multi_timeframe = self.settings.enable_multi_timeframe

        # Signal weights
        self.technical_weight = 0.40
        self.ml_weight = 0.30
        self.sentiment_weight = 0.15
        self.multi_timeframe_weight = 0.15

        # Minimum thresholds
        self.min_ml_confidence = 0.60  # ML predictions below this are ignored
        self.min_sentiment_confidence = 0.50  # Sentiment below this is ignored
        self.min_alignment_score = 70.0  # Multi-timeframe alignment threshold

        logger.info(
            f"EnhancedAggregator initialized "
            f"(ML={self.use_ml}, Sentiment={self.use_sentiment}, MTF={self.use_multi_timeframe})"
        )

    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()

    async def aggregate_signals_enhanced(
        self,
        symbol: str,
        interval: str,
        indicators: Dict[str, IndicatorSignal],
        timestamp: int,
        atr_data: Optional[Dict] = None
    ) -> TradingSignal:
        """
        Enhanced signal aggregation with ML + Sentiment + Multi-Timeframe

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Timeframe in minutes
            indicators: Technical indicators
            timestamp: Signal timestamp
            atr_data: ATR data for stops

        Returns:
            Enhanced TradingSignal
        """
        logger.info("="*80)
        logger.info("PHASE 3 ENHANCED SIGNAL AGGREGATION")
        logger.info("="*80)

        # Step 1: Get base technical signal from Phase 1 pipeline
        base_signal = super().aggregate_signals(indicators, timestamp, atr_data)

        logger.info(f"Phase 1 Base Signal: {base_signal.action.value} (confidence={base_signal.confidence:.3f})")

        # Step 2-4: Fetch ML, Sentiment, and Multi-Timeframe in PARALLEL (performance optimization)
        import asyncio

        # Build parallel task list
        tasks = []
        task_names = []

        if self.use_ml:
            tasks.append(self._fetch_ml_prediction(symbol, interval))
            task_names.append('ML')
        else:
            tasks.append(asyncio.sleep(0))  # Dummy task
            task_names.append('ML_DISABLED')

        if self.use_sentiment:
            tasks.append(self._fetch_sentiment(symbol))
            task_names.append('SENTIMENT')
        else:
            tasks.append(asyncio.sleep(0))  # Dummy task
            task_names.append('SENTIMENT_DISABLED')

        if self.use_multi_timeframe:
            tasks.append(self._fetch_multi_timeframe(symbol))
            task_names.append('MTF')
        else:
            tasks.append(asyncio.sleep(0))  # Dummy task
            task_names.append('MTF_DISABLED')

        # Fetch all Phase 3 data sources in parallel
        logger.info(f"Fetching Phase 3 data in parallel: {', '.join([n for n in task_names if not n.endswith('DISABLED')])}")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Extract results
        ml_prediction = results[0] if self.use_ml and not isinstance(results[0], Exception) else None
        sentiment = results[1] if self.use_sentiment and not isinstance(results[1], Exception) else None
        mtf_analysis = results[2] if self.use_multi_timeframe and not isinstance(results[2], Exception) else None

        # Calculate scores from fetched data
        ml_score = self._calculate_ml_score(ml_prediction)
        sentiment_score = self._calculate_sentiment_score(sentiment)
        mtf_score = self._calculate_mtf_score(mtf_analysis, base_signal.action)

        # Log results
        if self.use_ml:
            logger.info(f"ML Prediction Score: {ml_score:.3f}")
        if self.use_sentiment:
            logger.info(f"Sentiment Score: {sentiment_score:.3f}")
        if self.use_multi_timeframe:
            logger.info(f"Multi-Timeframe Score: {mtf_score:.3f}")

        # Step 5: Calculate enhanced combined score
        enhanced_score, enhanced_confidence = self._combine_all_signals(
            base_signal=base_signal,
            ml_score=ml_score,
            sentiment_score=sentiment_score,
            mtf_score=mtf_score
        )

        # Step 6: Determine enhanced action
        enhanced_action = self._determine_enhanced_action(
            enhanced_score,
            base_signal.action,
            ml_prediction,
            sentiment,
            mtf_analysis
        )

        # Step 7: Build enhanced signal with all metadata
        enhanced_signal = self._build_enhanced_signal(
            symbol=symbol,
            timestamp=timestamp,
            base_signal=base_signal,
            enhanced_action=enhanced_action,
            enhanced_confidence=enhanced_confidence,
            ml_prediction=ml_prediction,
            sentiment=sentiment,
            mtf_analysis=mtf_analysis,
            atr_data=atr_data
        )

        logger.info("="*80)
        logger.info(f"FINAL ENHANCED SIGNAL: {enhanced_action.value} (confidence={enhanced_confidence:.3f})")
        logger.info("="*80)

        return enhanced_signal

    async def _fetch_ml_prediction(self, symbol: str, interval: str) -> Optional[Dict]:
        """Fetch ML price prediction"""
        try:
            url = f"{self.ml_prediction_url}/api/v1/predict/trend/{symbol}"
            params = {"interval": interval}

            response = await self.http_client.get(url, params=params)

            if response.status_code == 200:
                data = response.json()
                logger.debug(f"ML Prediction fetched: {data.get('trend')} (confidence={data.get('trend_confidence', 0):.2f})")
                return data
            else:
                logger.warning(f"ML Prediction service returned {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Failed to fetch ML prediction: {e}")
            return None

    async def _fetch_sentiment(self, symbol: str) -> Optional[Dict]:
        """Fetch combined sentiment analysis"""
        try:
            url = f"{self.sentiment_url}/api/v1/sentiment/combined/{symbol}"
            params = {"use_cache": "true"}

            response = await self.http_client.get(url, params=params)

            if response.status_code == 200:
                data = response.json()
                logger.debug(f"Sentiment fetched: {data.get('sentiment_label')} (score={data.get('overall_sentiment', 0):.2f})")
                return data
            else:
                logger.warning(f"Sentiment service returned {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Failed to fetch sentiment: {e}")
            return None

    async def _fetch_multi_timeframe(self, symbol: str) -> Optional[Dict]:
        """Fetch multi-timeframe analysis"""
        try:
            url = f"{self.technical_analysis_url}/api/v1/analysis/multi-timeframe/{symbol}"
            params = {"timeframes": "5m,15m,60m,240m"}  # 4 timeframes for speed

            response = await self.http_client.get(url, params=params)

            if response.status_code == 200:
                data = response.json()
                logger.debug(f"Multi-timeframe fetched: {data.get('overall_signal')} (alignment={data.get('alignment_score', 0):.1f}%)")
                return data
            else:
                logger.warning(f"Multi-timeframe service returned {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Failed to fetch multi-timeframe: {e}")
            return None

    def _calculate_ml_score(self, ml_prediction: Optional[Dict]) -> float:
        """
        Convert ML prediction to normalized score (-1 to +1)

        Args:
            ml_prediction: ML prediction data

        Returns:
            Normalized score: +1 (strong buy), 0 (neutral), -1 (strong sell)
        """
        if not ml_prediction:
            return 0.0

        trend = ml_prediction.get('trend', 'NEUTRAL')
        confidence = ml_prediction.get('trend_confidence', 0.0)

        # Ignore low-confidence predictions
        if confidence < self.min_ml_confidence:
            logger.debug(f"ML confidence too low ({confidence:.2f} < {self.min_ml_confidence}), ignoring")
            return 0.0

        # Convert trend to score
        if trend == 'BULLISH':
            score = confidence  # Positive score
        elif trend == 'BEARISH':
            score = -confidence  # Negative score
        else:
            score = 0.0

        return score

    def _calculate_sentiment_score(self, sentiment: Optional[Dict]) -> float:
        """
        Convert sentiment to normalized score (-1 to +1)

        Args:
            sentiment: Sentiment analysis data

        Returns:
            Normalized score
        """
        if not sentiment:
            return 0.0

        overall_sentiment = sentiment.get('overall_sentiment', 0.0)
        confidence = sentiment.get('confidence', 0.0)

        # Ignore low-confidence sentiment
        if confidence < self.min_sentiment_confidence:
            logger.debug(f"Sentiment confidence too low ({confidence:.2f} < {self.min_sentiment_confidence}), ignoring")
            return 0.0

        # Sentiment is already in -1 to +1 range, weight by confidence
        return overall_sentiment * confidence

    def _calculate_mtf_score(self, mtf_analysis: Optional[Dict], base_action: SignalAction) -> float:
        """
        Convert multi-timeframe analysis to score

        Args:
            mtf_analysis: Multi-timeframe data
            base_action: Base action from technical indicators

        Returns:
            Normalized score based on alignment
        """
        if not mtf_analysis:
            return 0.0

        alignment_score = mtf_analysis.get('alignment_score', 0.0)
        overall_signal = mtf_analysis.get('overall_signal', 'HOLD')
        signal_strength = mtf_analysis.get('signal_strength', 0.0)

        # Check if alignment is good enough
        if alignment_score < self.min_alignment_score:
            logger.debug(f"Multi-timeframe alignment too low ({alignment_score:.1f}% < {self.min_alignment_score}%)")
            return 0.0

        # Convert signal to score
        if overall_signal == 'BUY':
            mtf_value = signal_strength
        elif overall_signal == 'SELL':
            mtf_value = -signal_strength
        else:
            mtf_value = 0.0

        # Bonus if MTF aligns with base signal
        if (base_action == SignalAction.BUY and overall_signal == 'BUY') or \
           (base_action == SignalAction.SELL and overall_signal == 'SELL'):
            mtf_value *= 1.2  # 20% bonus for alignment
            logger.debug(f"Multi-timeframe ALIGNS with base signal (+20% bonus)")

        return mtf_value

    def _combine_all_signals(
        self,
        base_signal: TradingSignal,
        ml_score: float,
        sentiment_score: float,
        mtf_score: float
    ) -> Tuple[float, float]:
        """
        Combine all signal sources with weighted average

        Returns:
            (combined_score, combined_confidence)
        """
        # Convert base signal action to score
        if base_signal.action == SignalAction.BUY:
            base_score = base_signal.confidence
        elif base_signal.action == SignalAction.SELL:
            base_score = -base_signal.confidence
        else:
            base_score = 0.0

        # Weighted combination
        combined_score = (
            base_score * self.technical_weight +
            ml_score * self.ml_weight +
            sentiment_score * self.sentiment_weight +
            mtf_score * self.multi_timeframe_weight
        )

        # Combined confidence is the absolute value
        combined_confidence = abs(combined_score)

        # Normalize to 0-1 range
        combined_confidence = min(1.0, combined_confidence)

        logger.info(
            f"Combined scores: "
            f"Technical={base_score:.3f}*{self.technical_weight} + "
            f"ML={ml_score:.3f}*{self.ml_weight} + "
            f"Sentiment={sentiment_score:.3f}*{self.sentiment_weight} + "
            f"MTF={mtf_score:.3f}*{self.multi_timeframe_weight} "
            f"= {combined_score:.3f}"
        )

        return combined_score, combined_confidence

    def _determine_enhanced_action(
        self,
        combined_score: float,
        base_action: SignalAction,
        ml_prediction: Optional[Dict],
        sentiment: Optional[Dict],
        mtf_analysis: Optional[Dict]
    ) -> SignalAction:
        """
        Determine final action from combined score

        Uses threshold-based classification with safety checks
        """
        # Thresholds
        buy_threshold = 0.5
        sell_threshold = -0.5

        # Determine action from score
        if combined_score >= buy_threshold:
            action = SignalAction.BUY
        elif combined_score <= sell_threshold:
            action = SignalAction.SELL
        else:
            action = SignalAction.HOLD

        # Safety check: Don't override strong contradictions
        # If ML and Sentiment strongly disagree with technical, force HOLD
        if ml_prediction and sentiment:
            ml_trend = ml_prediction.get('trend', 'NEUTRAL')
            sentiment_label = sentiment.get('sentiment_label', 'NEUTRAL')

            # Check for strong contradiction
            technical_bullish = base_action == SignalAction.BUY
            ml_bearish = ml_trend == 'BEARISH'
            sentiment_bearish = sentiment_label == 'BEARISH'

            technical_bearish = base_action == SignalAction.SELL
            ml_bullish = ml_trend == 'BULLISH'
            sentiment_bullish = sentiment_label == 'BULLISH'

            if (technical_bullish and ml_bearish and sentiment_bearish) or \
               (technical_bearish and ml_bullish and sentiment_bullish):
                logger.warning("Strong contradiction detected: Technical vs ML+Sentiment. Forcing HOLD.")
                action = SignalAction.HOLD

        return action

    def _build_enhanced_signal(
        self,
        symbol: str,
        timestamp: int,
        base_signal: TradingSignal,
        enhanced_action: SignalAction,
        enhanced_confidence: float,
        ml_prediction: Optional[Dict],
        sentiment: Optional[Dict],
        mtf_analysis: Optional[Dict],
        atr_data: Optional[Dict]
    ) -> TradingSignal:
        """Build enhanced trading signal with all metadata"""

        # Build enhanced metadata
        metadata = base_signal.metadata.copy()

        # Add ML prediction metadata
        if ml_prediction:
            metadata['ml_prediction'] = {
                'trend': ml_prediction.get('trend'),
                'confidence': ml_prediction.get('trend_confidence'),
                'model_version': ml_prediction.get('model_version', 'unknown')
            }

        # Add sentiment metadata
        if sentiment:
            metadata['sentiment'] = {
                'score': sentiment.get('overall_sentiment'),
                'label': sentiment.get('sentiment_label'),
                'confidence': sentiment.get('confidence'),
                'data_quality': sentiment.get('data_quality')
            }

        # Add multi-timeframe metadata
        if mtf_analysis:
            metadata['multi_timeframe'] = {
                'alignment_score': mtf_analysis.get('alignment_score'),
                'consensus_signal': mtf_analysis.get('consensus_signal'),
                'signal_strength': mtf_analysis.get('signal_strength'),
                'short_term': mtf_analysis.get('short_term_trend'),
                'medium_term': mtf_analysis.get('medium_term_trend'),
                'long_term': mtf_analysis.get('long_term_trend')
            }

        # Mark as Phase 3 enhanced signal
        metadata['phase'] = 3
        metadata['enhancement'] = {
            'ml_enabled': self.use_ml,
            'sentiment_enabled': self.use_sentiment,
            'multi_timeframe_enabled': self.use_multi_timeframe
        }

        # Create enhanced signal
        return TradingSignal(
            symbol=symbol,
            action=enhanced_action,
            confidence=enhanced_confidence,
            timestamp=timestamp,
            indicators=base_signal.indicators,
            metadata=metadata
        )
