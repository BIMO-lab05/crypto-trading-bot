"""
Signal Aggregator
Purpose: Fetch and aggregate technical indicators from Technical Analysis Service

REFACTORED: Using Strangler Fig pattern
- Modular components in app/aggregation/
- CoreAggregator orchestrates gatekeeper, validator, voter
- Improved testability and maintainability
"""

import httpx
import logging
from typing import Dict, Optional
from app.config import get_settings
from app.models import TradingSignal, IndicatorSignal, SignalAction
from app.aggregation import CoreAggregator

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
        """Initialize signal aggregator with modular components"""
        self.settings = get_settings()
        self.base_url = self.settings.technical_analysis_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.core_aggregator = CoreAggregator(self.settings)  # Modular aggregation
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
        REFACTORED: Delegates to SignalVoter

        BUY    → +1.0
        SELL   → -1.0
        HOLD   →  0.0
        NEUTRAL→  0.0
        """
        # Delegate to modular voter component
        return self.core_aggregator.voter.signal_to_score(signal)

    def aggregate_signals(
        self,
        indicators: Dict[str, IndicatorSignal],
        timestamp: int,
        atr_data: Optional[Dict] = None
    ) -> TradingSignal:
        """
        Aggregate individual indicator signals into a final trading signal

        REFACTORED: Delegates to CoreAggregator using Strangler Fig pattern

        PHASE 1 ENHANCEMENTS (Now Modular):
        1. Trend Filter as GATEKEEPER: Blocks counter-trend trades (gatekeeper.py)
        2. Volume Confirmation as VALIDATOR: Filters low-volume signals (validator.py)
        3. Voting logic with consensus requirements (voter.py)
        4. Orchestrated aggregation pipeline (aggregator_core.py)

        Pipeline:
        1. VOTER: Calculate preliminary signal from voting indicators
        2. GATEKEEPER: Block counter-trend trades
        3. VALIDATOR: Apply volume confidence penalty
        4. REQUIREMENTS: Check consensus and minimum confidence
        5. OUTPUT: Final TradingSignal
        """
        # Delegate to modular CoreAggregator
        return self.core_aggregator.aggregate_signals(indicators, timestamp, atr_data)

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
