"""
Signal Aggregator
Purpose: Fetch and aggregate technical indicators from Technical Analysis Service
"""

import httpx
import logging
from typing import Dict, Optional
from app.config import get_settings
from app.models import TradingSignal, IndicatorSignal, SignalAction

logger = logging.getLogger(__name__)


class SignalAggregator:
    """
    Fetches technical indicators and aggregates them into a trading signal

    Process:
    1. Fetch all indicators from Technical Analysis Service
    2. Normalize signals (BUY/SELL/HOLD → numerical score)
    3. Weight by confidence
    4. Generate final trading decision
    """

    def __init__(self):
        """Initialize signal aggregator"""
        self.settings = get_settings()
        self.base_url = self.settings.technical_analysis_url
        self.client = httpx.AsyncClient(timeout=30.0)
        logger.info(f"SignalAggregator initialized with TA URL: {self.base_url}")

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

    async def health_check(self) -> bool:
        """Check if Technical Analysis Service is available"""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Technical Analysis Service health check failed: {e}")
            return False

    async def fetch_rsi(
        self,
        symbol: str,
        interval: str = "60",
        period: int = 14
    ) -> Optional[IndicatorSignal]:
        """Fetch RSI indicator"""
        try:
            url = f"{self.base_url}/api/v1/indicators/rsi/{symbol}"
            params = {"interval": interval, "period": period}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            return IndicatorSignal(
                name="RSI",
                signal=SignalAction(data["signal"]),
                confidence=data["confidence"],
                value=data["rsi"],
                metadata={"period": period}
            )

        except Exception as e:
            logger.error(f"Error fetching RSI for {symbol}: {e}")
            return None

    async def fetch_macd(
        self,
        symbol: str,
        interval: str = "60"
    ) -> Optional[IndicatorSignal]:
        """Fetch MACD indicator"""
        try:
            url = f"{self.base_url}/api/v1/indicators/macd/{symbol}"
            params = {"interval": interval}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            return IndicatorSignal(
                name="MACD",
                signal=SignalAction(data["signal"]),
                confidence=data["confidence"],
                value=data["histogram"],
                metadata={
                    "macd_line": data["macd_line"],
                    "signal_line": data["signal_line"]
                }
            )

        except Exception as e:
            logger.error(f"Error fetching MACD for {symbol}: {e}")
            return None

    async def fetch_bollinger_bands(
        self,
        symbol: str,
        interval: str = "60"
    ) -> Optional[IndicatorSignal]:
        """Fetch Bollinger Bands indicator"""
        try:
            url = f"{self.base_url}/api/v1/indicators/bollinger/{symbol}"
            params = {"interval": interval}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            return IndicatorSignal(
                name="BOLLINGER_BANDS",
                signal=SignalAction(data["signal"]),
                confidence=data["confidence"],
                value=data["current_price"],
                metadata={
                    "upper_band": data["upper_band"],
                    "middle_band": data["middle_band"],
                    "lower_band": data["lower_band"]
                }
            )

        except Exception as e:
            logger.error(f"Error fetching Bollinger Bands for {symbol}: {e}")
            return None

    async def fetch_sma(
        self,
        symbol: str,
        interval: str = "60",
        period: int = 20
    ) -> Optional[IndicatorSignal]:
        """Fetch SMA indicator"""
        try:
            url = f"{self.base_url}/api/v1/indicators/sma/{symbol}"
            params = {"interval": interval, "period": period}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            return IndicatorSignal(
                name="SMA",
                signal=SignalAction(data["signal"]),
                confidence=data["confidence"],
                value=data["value"],
                metadata={
                    "current_price": data["current_price"],
                    "period": period
                }
            )

        except Exception as e:
            logger.error(f"Error fetching SMA for {symbol}: {e}")
            return None

    async def fetch_ema(
        self,
        symbol: str,
        interval: str = "60",
        period: int = 20
    ) -> Optional[IndicatorSignal]:
        """Fetch EMA indicator"""
        try:
            url = f"{self.base_url}/api/v1/indicators/ema/{symbol}"
            params = {"interval": interval, "period": period}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            return IndicatorSignal(
                name="EMA",
                signal=SignalAction(data["signal"]),
                confidence=data["confidence"],
                value=data["value"],
                metadata={
                    "current_price": data["current_price"],
                    "period": period
                }
            )

        except Exception as e:
            logger.error(f"Error fetching EMA for {symbol}: {e}")
            return None

    # ==================== PHASE 1 INDICATORS ====================

    async def fetch_trend_filter(
        self,
        symbol: str,
        interval: str = "60"
    ) -> Optional[IndicatorSignal]:
        """
        Fetch Trend Filter (50/200 EMA)

        Role: GATEKEEPER - Blocks counter-trend trades
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/trend/{symbol}"
            params = {"interval": interval, "limit": 300}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            result = response.json()
            data = result["data"]

            return IndicatorSignal(
                name="TREND_FILTER",
                signal=SignalAction(data["signal"]),
                confidence=data["confidence"],
                value=data["spread_pct"],
                metadata={
                    "trend": data["trend"],
                    "fast_ema": data["fast_ema"],
                    "slow_ema": data["slow_ema"],
                    "role": "GATEKEEPER"
                }
            )

        except Exception as e:
            logger.error(f"Error fetching Trend Filter for {symbol}: {e}")
            return None

    async def fetch_volume_confirmation(
        self,
        symbol: str,
        interval: str = "60",
        signal_type: str = "breakout"
    ) -> Optional[IndicatorSignal]:
        """
        Fetch Volume Confirmation

        Role: VALIDATOR - Filters low-volume signals
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/volume/{symbol}"
            params = {"interval": interval, "signal_type": signal_type}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            result = response.json()
            data = result["data"]

            # Convert volume confirmation to signal
            if data["confirmed"]:
                signal = SignalAction.BUY if data["strength"] in ["STRONG", "MODERATE"] else SignalAction.HOLD
            else:
                signal = SignalAction.HOLD

            return IndicatorSignal(
                name="VOLUME_CONFIRMATION",
                signal=signal,
                confidence=data["confidence"],
                value=data["volume_ratio"],
                metadata={
                    "confirmed": data["confirmed"],
                    "strength": data["strength"],
                    "current_volume": data["current_volume"],
                    "avg_volume": data["avg_volume"],
                    "role": "VALIDATOR"
                }
            )

        except Exception as e:
            logger.error(f"Error fetching Volume Confirmation for {symbol}: {e}")
            return None

    async def fetch_atr(
        self,
        symbol: str,
        interval: str = "60"
    ) -> Optional[Dict]:
        """
        Fetch ATR (Average True Range)

        Role: RISK MANAGER - Provides dynamic stop-loss levels
        Returns: Dict (not IndicatorSignal) as it's used for position sizing
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/atr/{symbol}"
            params = {"interval": interval}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            result = response.json()
            data = result["data"]

            return {
                "atr": data["atr"],
                "atr_pct": data["atr_pct"],
                "stop_loss_long": data["stop_loss_long"],
                "stop_loss_short": data["stop_loss_short"],
                "take_profit_long": data["take_profit_long"],
                "take_profit_short": data["take_profit_short"],
                "volatility": data["volatility"],
                "confidence": data["confidence"],
                "risk_reward_ratio": data["risk_reward_ratio"]
            }

        except Exception as e:
            logger.error(f"Error fetching ATR for {symbol}: {e}")
            return None

    async def fetch_stochastic(
        self,
        symbol: str,
        interval: str = "60"
    ) -> Optional[IndicatorSignal]:
        """
        Fetch Stochastic Oscillator

        Role: MOMENTUM INDICATOR - Timing confirmation
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/stochastic/{symbol}"
            params = {"interval": interval}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            result = response.json()
            data = result["data"]

            return IndicatorSignal(
                name="STOCHASTIC",
                signal=SignalAction(data["signal"]),
                confidence=data["confidence"],
                value=data["k"],
                metadata={
                    "k": data["k"],
                    "d": data["d"],
                    "condition": data["condition"],
                    "crossover": data["crossover"],
                    "role": "MOMENTUM"
                }
            )

        except Exception as e:
            logger.error(f"Error fetching Stochastic for {symbol}: {e}")
            return None

    async def fetch_all_indicators(
        self,
        symbol: str,
        interval: str = "60"
    ) -> tuple[Dict[str, IndicatorSignal], Optional[Dict]]:
        """
        Fetch all indicators in parallel

        Returns:
            tuple: (indicators_dict, atr_data)
            - indicators_dict: All voting indicators (RSI, MACD, BB, SMA, EMA, Trend Filter, Stochastic)
            - atr_data: ATR data for dynamic stops (Dict or None)
        """
        logger.info(f"Fetching all indicators for {symbol} ({interval}m)")

        # Fetch all indicators concurrently
        import asyncio
        tasks = {
            # Original 5 indicators
            "RSI": self.fetch_rsi(symbol, interval),
            "MACD": self.fetch_macd(symbol, interval),
            "BOLLINGER_BANDS": self.fetch_bollinger_bands(symbol, interval),
            "SMA": self.fetch_sma(symbol, interval),
            "EMA": self.fetch_ema(symbol, interval),
            # Phase 1 indicators
            "TREND_FILTER": self.fetch_trend_filter(symbol, interval),
            "VOLUME_CONFIRMATION": self.fetch_volume_confirmation(symbol, interval),
            "STOCHASTIC": self.fetch_stochastic(symbol, interval),
            "ATR": self.fetch_atr(symbol, interval)
        }

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        # Build indicator dictionary and extract ATR separately
        indicators = {}
        atr_data = None

        for name, result in zip(tasks.keys(), results):
            if name == "ATR":
                # ATR is stored separately (not a voting indicator)
                if isinstance(result, dict):
                    atr_data = result
                    logger.info(f"  ✓ ATR: {result['volatility']} volatility ({result['atr_pct']:.2f}%)")
                else:
                    logger.warning(f"  ✗ ATR: Failed to fetch")
            elif isinstance(result, IndicatorSignal):
                indicators[name] = result
                logger.info(f"  ✓ {name}: {result.signal.value} (conf: {result.confidence})")
            else:
                logger.warning(f"  ✗ {name}: Failed to fetch")

        return indicators, atr_data

    def signal_to_score(self, signal: SignalAction) -> float:
        """
        Convert signal action to numerical score

        BUY    → +1.0
        SELL   → -1.0
        HOLD   →  0.0
        NEUTRAL→  0.0
        """
        if signal == SignalAction.BUY:
            return 1.0
        elif signal == SignalAction.SELL:
            return -1.0
        else:  # HOLD or NEUTRAL
            return 0.0

    def aggregate_signals(
        self,
        indicators: Dict[str, IndicatorSignal],
        timestamp: int,
        atr_data: Optional[Dict] = None
    ) -> TradingSignal:
        """
        Aggregate individual indicator signals into a final trading signal

        PHASE 1 ENHANCEMENTS:
        1. Trend Filter as GATEKEEPER: Blocks counter-trend trades
        2. Volume Confirmation as VALIDATOR: Filters low-volume signals
        3. Stochastic included in voting
        4. ATR data stored in metadata for dynamic stops

        Algorithm:
        1. Apply GATEKEEPER filter (Trend Filter)
        2. Apply VALIDATOR filter (Volume Confirmation)
        3. Calculate weighted scores from voting indicators
        4. Apply consensus logic
        5. Determine final action
        """
        symbol = "UNKNOWN"  # Will be set from context

        if not indicators:
            logger.warning("No indicators available for aggregation")
            return TradingSignal(
                symbol=symbol,
                timestamp=timestamp,
                action=SignalAction.HOLD,
                confidence=0.0,
                indicators={},
                aggregated_score=0.0,
                consensus_count=0,
                metadata={"error": "No indicators available"}
            )

        # ==================== PHASE 1: GATEKEEPER (Trend Filter) ====================
        trend_filter = indicators.get("TREND_FILTER")
        trend_blocked = False
        trend_reason = ""

        if trend_filter:
            trend = trend_filter.metadata.get("trend")
            logger.info(f"🔍 Trend Filter: {trend} (confidence: {trend_filter.confidence:.2f})")
        else:
            logger.warning("⚠️  Trend Filter not available - proceeding without trend check")

        # ==================== PHASE 1: VALIDATOR (Volume Confirmation) ====================
        volume_conf = indicators.get("VOLUME_CONFIRMATION")
        volume_penalty = 1.0  # Multiplier for confidence (1.0 = no penalty)
        volume_reason = ""

        if volume_conf:
            confirmed = volume_conf.metadata.get("confirmed", False)
            strength = volume_conf.metadata.get("strength", "UNKNOWN")

            if not confirmed:
                volume_penalty = 0.3  # Reduce confidence to 30% for unconfirmed volume
                volume_reason = f"Low volume ({strength})"
                logger.warning(f"⚠️  Volume NOT confirmed: {strength}")
            else:
                logger.info(f"✅ Volume confirmed: {strength}")
        else:
            logger.warning("⚠️  Volume Confirmation not available - proceeding without volume check")

        # ==================== Calculate weighted scores ====================
        weighted_scores = []
        buy_count = 0
        sell_count = 0
        hold_count = 0

        # Exclude GATEKEEPER and VALIDATOR from voting (they filter, not vote)
        voting_indicators = {
            k: v for k, v in indicators.items()
            if k not in ["TREND_FILTER", "VOLUME_CONFIRMATION"]
        }

        for name, indicator in voting_indicators.items():
            score = self.signal_to_score(indicator.signal)
            weighted_score = score * indicator.confidence
            weighted_scores.append(weighted_score)

            # Count signals
            if indicator.signal == SignalAction.BUY:
                buy_count += 1
            elif indicator.signal == SignalAction.SELL:
                sell_count += 1
            else:
                hold_count += 1

        # Calculate aggregated score
        aggregated_score = sum(weighted_scores) / len(weighted_scores) if weighted_scores else 0.0

        # Determine consensus count (max of buy/sell/hold counts)
        consensus_count = max(buy_count, sell_count, hold_count)

        # Determine preliminary action based on aggregated score
        if aggregated_score >= 0.3:
            action = SignalAction.BUY
            confidence = min(abs(aggregated_score), 1.0)
        elif aggregated_score <= -0.3:
            action = SignalAction.SELL
            confidence = min(abs(aggregated_score), 1.0)
        else:
            action = SignalAction.HOLD
            confidence = 1.0 - abs(aggregated_score)

        # ==================== PHASE 1: Apply GATEKEEPER filter ====================
        if trend_filter and action != SignalAction.HOLD:
            trend = trend_filter.metadata.get("trend")

            # Block counter-trend trades
            if action == SignalAction.BUY and trend == "BEARISH":
                trend_blocked = True
                trend_reason = "Counter-trend (BUY in BEARISH trend)"
                logger.warning(f"🚫 BLOCKED: {trend_reason}")
                action = SignalAction.HOLD
                confidence *= 0.2  # Drastically reduce confidence

            elif action == SignalAction.SELL and trend == "BULLISH":
                trend_blocked = True
                trend_reason = "Counter-trend (SELL in BULLISH trend)"
                logger.warning(f"🚫 BLOCKED: {trend_reason}")
                action = SignalAction.HOLD
                confidence *= 0.2

            elif trend == "NEUTRAL":
                # Neutral trend: allow but reduce confidence
                confidence *= 0.7
                trend_reason = "Neutral trend (reduced confidence)"
                logger.info(f"⚠️  {trend_reason}")

        # ==================== PHASE 1: Apply VALIDATOR penalty ====================
        confidence *= volume_penalty

        # Check if signal meets minimum requirements
        # Updated: Now need 4 out of 7 voting indicators (increased from 3/5)
        min_consensus = 4  # Stricter consensus with more indicators
        meets_requirements = (
            consensus_count >= min_consensus and
            confidence >= self.settings.min_signal_confidence and
            not trend_blocked
        )

        if not meets_requirements:
            reasons = []
            if consensus_count < min_consensus:
                reasons.append(f"consensus={consensus_count} (min={min_consensus})")
            if confidence < self.settings.min_signal_confidence:
                reasons.append(f"confidence={confidence:.2f} (min={self.settings.min_signal_confidence})")
            if trend_blocked:
                reasons.append(f"trend_blocked: {trend_reason}")

            logger.info(f"Signal does not meet requirements: {', '.join(reasons)}")
            action = SignalAction.HOLD

        # Build metadata
        metadata = {
            "buy_count": buy_count,
            "sell_count": sell_count,
            "hold_count": hold_count,
            "meets_requirements": meets_requirements,
            "phase_1_active": True,
            "trend_blocked": trend_blocked,
            "trend_reason": trend_reason,
            "volume_penalty": volume_penalty,
            "volume_reason": volume_reason,
            "voting_indicators_count": len(voting_indicators)
        }

        # Add ATR data for dynamic stops if available
        if atr_data:
            metadata["atr"] = atr_data
            logger.info(f"💰 ATR Dynamic Stops: SL={atr_data['stop_loss_long']:.2f}, TP={atr_data['take_profit_long']:.2f}")

        logger.info(
            f"Aggregated Signal: {action.value} "
            f"(score: {aggregated_score:+.2f}, conf: {confidence:.2f}, "
            f"consensus: {consensus_count}/{len(voting_indicators)})"
        )

        return TradingSignal(
            symbol=symbol,
            timestamp=timestamp,
            action=action,
            confidence=round(confidence, 2),
            indicators=indicators,
            aggregated_score=round(aggregated_score, 3),
            consensus_count=consensus_count,
            metadata=metadata
        )

    async def get_trading_signal(
        self,
        symbol: str,
        interval: str = "60"
    ) -> TradingSignal:
        """
        Get complete trading signal for a symbol

        This is the main entry point for getting a trading signal.

        PHASE 1 UPDATE: Now fetches and includes ATR data for dynamic stops
        """
        import time
        timestamp = int(time.time() * 1000)

        # Fetch all indicators (returns both indicators and ATR data)
        indicators, atr_data = await self.fetch_all_indicators(symbol, interval)

        # Aggregate signals with ATR data
        signal = self.aggregate_signals(indicators, timestamp, atr_data)
        signal.symbol = symbol

        return signal


# Global signal aggregator instance
_aggregator: Optional[SignalAggregator] = None


async def get_aggregator() -> SignalAggregator:
    """Get or create signal aggregator instance"""
    global _aggregator
    if _aggregator is None:
        _aggregator = SignalAggregator()
    return _aggregator


async def close_aggregator():
    """Close signal aggregator"""
    global _aggregator
    if _aggregator is not None:
        await _aggregator.close()
        _aggregator = None
