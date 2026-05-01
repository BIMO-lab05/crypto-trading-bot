"""
Ensemble Predictor - Combines Multiple Signal Sources
Combines TA + ML + Sentiment + Multi-Timeframe for robust predictions

Weighting Strategy (as per plan):
- Traditional TA: 40%
- ML Predictions: 30%
- Sentiment Analysis: 15%
- Multi-Timeframe: 15%
"""

import logging
import httpx
from typing import List, Optional
from datetime import datetime
import numpy as np
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SignalComponent(BaseModel):
    """Individual signal component"""

    source: str  # 'TA', 'ML', 'Sentiment', 'MultiTimeframe'
    direction: str  # 'BUY', 'SELL', 'NEUTRAL'
    confidence: float  # 0.0 to 1.0
    weight: float  # Weight in ensemble (0.0 to 1.0)
    raw_score: float  # Raw signal strength (-1.0 to 1.0)


class EnsembleSignal(BaseModel):
    """Final ensemble signal"""

    symbol: str
    interval: str
    timestamp: datetime

    # Final decision
    direction: str  # 'BUY', 'SELL', 'NEUTRAL'
    confidence: float  # Overall confidence (0.0 to 1.0)
    strength: float  # Signal strength (0.0 to 1.0)

    # Component signals
    components: List[SignalComponent]

    # Weighted scores
    weighted_score: float  # Final weighted score (-1.0 to 1.0)
    buy_probability: float  # Probability of upward move
    sell_probability: float  # Probability of downward move

    # Metadata
    components_available: int
    components_used: int
    ensemble_method: str = "weighted_voting"


class EnsemblePredictor:
    """
    Ensemble predictor combining multiple signal sources

    Combines:
    1. Traditional TA (40%) - RSI, MACD, Bollinger Bands
    2. ML Predictions (30%) - LSTM/GRU price predictions
    3. Sentiment Analysis (15%) - News/social media sentiment (placeholder)
    4. Multi-Timeframe (15%) - Trend alignment across timeframes
    """

    def __init__(
        self,
        ta_weight: float = 0.40,
        ml_weight: float = 0.30,
        sentiment_weight: float = 0.15,
        multi_tf_weight: float = 0.15,
        ta_service_url: str = "http://localhost:8004",
        ml_service_url: str = "http://localhost:8007",
        market_data_url: str = "http://localhost:8003",
    ):
        """
        Initialize ensemble predictor

        Args:
            ta_weight: Weight for traditional TA signals (default: 0.40)
            ml_weight: Weight for ML predictions (default: 0.30)
            sentiment_weight: Weight for sentiment analysis (default: 0.15)
            multi_tf_weight: Weight for multi-timeframe analysis (default: 0.15)
            ta_service_url: URL of technical analysis service
            ml_service_url: URL of ML prediction service
            market_data_url: URL of market data service
        """
        # Normalize weights to sum to 1.0
        total_weight = ta_weight + ml_weight + sentiment_weight + multi_tf_weight
        self.ta_weight = ta_weight / total_weight
        self.ml_weight = ml_weight / total_weight
        self.sentiment_weight = sentiment_weight / total_weight
        self.multi_tf_weight = multi_tf_weight / total_weight

        # Service URLs
        self.ta_service_url = ta_service_url
        self.ml_service_url = ml_service_url
        self.market_data_url = market_data_url

        # HTTP client for calling services
        self.http_client = httpx.AsyncClient(timeout=10.0)

        logger.info(
            f"EnsemblePredictor initialized with weights: "
            f"TA={self.ta_weight:.2f}, ML={self.ml_weight:.2f}, "
            f"Sentiment={self.sentiment_weight:.2f}, MultiTF={self.multi_tf_weight:.2f}"
        )

    async def get_ta_signal(
        self, symbol: str, interval: str = "60"
    ) -> Optional[SignalComponent]:
        """
        Get traditional TA signal from technical analysis service

        Combines RSI, MACD, Bollinger Bands into single signal

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Timeframe in minutes

        Returns:
            SignalComponent or None if service unavailable
        """
        try:
            # Call technical analysis service
            url = f"{self.ta_service_url}/api/v1/signals/{symbol}"
            response = await self.http_client.get(url, params={"interval": interval})

            if response.status_code != 200:
                logger.warning(f"TA service returned {response.status_code}")
                return None

            data = response.json()

            # Extract signal components
            rsi_signal = data.get("rsi", {}).get("signal", 0)  # -1 to 1
            macd_signal = data.get("macd", {}).get("signal", 0)
            bb_signal = data.get("bollinger_bands", {}).get("signal", 0)

            # Average the signals
            raw_score = (rsi_signal + macd_signal + bb_signal) / 3.0

            # Determine direction
            if raw_score > 0.2:
                direction = "BUY"
            elif raw_score < -0.2:
                direction = "SELL"
            else:
                direction = "NEUTRAL"

            # Confidence based on signal strength
            confidence = abs(raw_score)

            return SignalComponent(
                source="TA",
                direction=direction,
                confidence=confidence,
                weight=self.ta_weight,
                raw_score=raw_score,
            )

        except Exception as e:
            logger.error(f"Error getting TA signal: {e}")
            return None

    async def get_ml_signal(
        self, symbol: str, interval: str = "60", model_type: str = "GRU"
    ) -> Optional[SignalComponent]:
        """
        Get ML prediction signal

        Uses LSTM/GRU models to predict price direction

        Args:
            symbol: Trading pair
            interval: Timeframe in minutes
            model_type: ML model type (LSTM or GRU)

        Returns:
            SignalComponent or None if model unavailable
        """
        try:
            # Call ML prediction service
            url = f"{self.ml_service_url}/api/v1/predict/price/{symbol}"
            response = await self.http_client.get(
                url, params={"interval": interval, "model_type": model_type}
            )

            if response.status_code != 200:
                logger.warning(f"ML service returned {response.status_code}")
                return None

            data = response.json()

            # Extract prediction data
            current_price = data.get("current_price", 0)
            predictions = data.get("predictions", [])
            avg_confidence = data.get("average_confidence", 0)

            if not predictions:
                return None

            # Calculate average predicted price change
            predicted_prices = [p["predicted_price"] for p in predictions]
            avg_predicted_price = np.mean(predicted_prices)

            # Calculate % change
            price_change_pct = (
                (avg_predicted_price - current_price) / current_price
            ) * 100

            # Normalize to -1 to 1 scale
            # ±10% change = ±1.0 signal
            raw_score = np.clip(price_change_pct / 10.0, -1.0, 1.0)

            # Determine direction
            if price_change_pct > 0.5:  # >0.5% predicted increase
                direction = "BUY"
            elif price_change_pct < -0.5:  # >0.5% predicted decrease
                direction = "SELL"
            else:
                direction = "NEUTRAL"

            # Use model's average confidence
            confidence = avg_confidence

            return SignalComponent(
                source=f"ML_{model_type}",
                direction=direction,
                confidence=confidence,
                weight=self.ml_weight,
                raw_score=raw_score,
            )

        except Exception as e:
            logger.error(f"Error getting ML signal: {e}")
            return None

    async def get_sentiment_signal(self, symbol: str) -> Optional[SignalComponent]:
        """
        Get sentiment analysis signal

        PLACEHOLDER: Sentiment analysis not yet implemented
        Returns neutral signal with low weight

        Future implementation:
        - Twitter/Reddit sentiment
        - News headline analysis
        - Social media volume

        Args:
            symbol: Trading pair

        Returns:
            SignalComponent (placeholder - always NEUTRAL)
        """
        # TODO: Implement sentiment analysis service
        # For now, return neutral signal

        logger.debug(
            f"Sentiment signal not implemented - returning NEUTRAL for {symbol}"
        )

        return SignalComponent(
            source="Sentiment",
            direction="NEUTRAL",
            confidence=0.0,
            weight=self.sentiment_weight,
            raw_score=0.0,
        )

    async def get_multi_timeframe_signal(
        self, symbol: str, base_interval: str = "60"
    ) -> Optional[SignalComponent]:
        """
        Get multi-timeframe trend alignment signal

        Checks if trends align across multiple timeframes:
        - 15m (short-term)
        - 60m (current)
        - 240m (medium-term)
        - 1440m (daily)

        Strong signal when all timeframes agree

        Args:
            symbol: Trading pair
            base_interval: Base timeframe (default: 60m)

        Returns:
            SignalComponent based on timeframe alignment
        """
        try:
            timeframes = ["15", "60", "240", "1440"]  # 15m, 1h, 4h, 1d
            signals = []

            for tf in timeframes:
                # Get TA signal for each timeframe
                url = f"{self.ta_service_url}/api/v1/signals/{symbol}"
                response = await self.http_client.get(url, params={"interval": tf})

                if response.status_code == 200:
                    data = response.json()
                    overall_signal = data.get("overall_signal", 0)
                    signals.append(overall_signal)

            if not signals:
                return None

            # Calculate alignment
            avg_signal = np.mean(signals)
            signal_std = np.std(signals)

            # Low std = high alignment
            alignment = 1.0 - min(signal_std, 1.0)

            # Determine direction
            if avg_signal > 0.2:
                direction = "BUY"
            elif avg_signal < -0.2:
                direction = "SELL"
            else:
                direction = "NEUTRAL"

            # Confidence based on alignment
            confidence = alignment * abs(avg_signal)

            return SignalComponent(
                source="MultiTimeframe",
                direction=direction,
                confidence=confidence,
                weight=self.multi_tf_weight,
                raw_score=avg_signal,
            )

        except Exception as e:
            logger.error(f"Error getting multi-timeframe signal: {e}")
            return None

    async def predict(
        self, symbol: str, interval: str = "60", ml_model: str = "GRU"
    ) -> EnsembleSignal:
        """
        Generate ensemble prediction combining all signal sources

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Timeframe in minutes (default: 60)
            ml_model: ML model to use (LSTM or GRU)

        Returns:
            EnsembleSignal with weighted combination of all sources
        """
        logger.info(f"Generating ensemble signal for {symbol} {interval}m")

        # Gather all signal components
        components = []

        # 1. Traditional TA (40%)
        ta_signal = await self.get_ta_signal(symbol, interval)
        if ta_signal:
            components.append(ta_signal)

        # 2. ML Predictions (30%)
        ml_signal = await self.get_ml_signal(symbol, interval, ml_model)
        if ml_signal:
            components.append(ml_signal)

        # 3. Sentiment Analysis (15%)
        sentiment_signal = await self.get_sentiment_signal(symbol)
        if sentiment_signal:
            components.append(sentiment_signal)

        # 4. Multi-Timeframe (15%)
        mtf_signal = await self.get_multi_timeframe_signal(symbol, interval)
        if mtf_signal:
            components.append(mtf_signal)

        # Calculate weighted ensemble score
        total_weight = sum(c.weight for c in components)

        if total_weight == 0:
            # No signals available - return neutral
            return EnsembleSignal(
                symbol=symbol,
                interval=interval,
                timestamp=datetime.utcnow(),
                direction="NEUTRAL",
                confidence=0.0,
                strength=0.0,
                components=[],
                weighted_score=0.0,
                buy_probability=0.5,
                sell_probability=0.5,
                components_available=0,
                components_used=0,
            )

        # Weighted voting
        weighted_score = sum(c.raw_score * c.weight for c in components) / total_weight
        avg_confidence = sum(c.confidence * c.weight for c in components) / total_weight

        # Determine final direction
        if weighted_score > 0.3:
            direction = "BUY"
            strength = min(weighted_score, 1.0)
        elif weighted_score < -0.3:
            direction = "SELL"
            strength = min(abs(weighted_score), 1.0)
        else:
            direction = "NEUTRAL"
            strength = 0.5

        # Calculate probabilities
        # Map weighted_score (-1 to 1) to probabilities
        buy_prob = (weighted_score + 1.0) / 2.0  # 0.0 to 1.0
        sell_prob = 1.0 - buy_prob

        return EnsembleSignal(
            symbol=symbol,
            interval=interval,
            timestamp=datetime.utcnow(),
            direction=direction,
            confidence=avg_confidence,
            strength=strength,
            components=components,
            weighted_score=weighted_score,
            buy_probability=buy_prob,
            sell_probability=sell_prob,
            components_available=4,  # TA, ML, Sentiment, MultiTF
            components_used=len(components),
        )

    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()


# Convenience function for quick ensemble prediction
async def get_ensemble_signal(
    symbol: str, interval: str = "60", ml_model: str = "GRU"
) -> EnsembleSignal:
    """
    Quick function to get ensemble signal

    Args:
        symbol: Trading pair
        interval: Timeframe in minutes
        ml_model: ML model type (LSTM or GRU)

    Returns:
        EnsembleSignal
    """
    predictor = EnsemblePredictor()
    try:
        signal = await predictor.predict(symbol, interval, ml_model)
        return signal
    finally:
        await predictor.close()
