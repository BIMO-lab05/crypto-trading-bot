"""
Market Regime Detector - Phase 6.3 Feature Extraction
Purpose: Detect market regimes for ML models
Author: Phase 6.4 Implementation
Date: 2025-12-11

Provides 9 regime features (one-hot encoded):
- trend_regime: UPTREND (3), DOWNTREND (3), SIDEWAYS (3) = 3 features
- volatility_regime: LOW (3), MEDIUM (3), HIGH (3) = 3 features
- volume_regime: LOW (3), NORMAL (3), HIGH (3) = 3 features

Total: 9 one-hot encoded features (3 categories x 3 regimes)
"""

import asyncio
import httpx
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import numpy as np
import pandas as pd

# Configure logger
logger = logging.getLogger(__name__)


class TrendRegime(Enum):
    """Trend regime classification"""
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    SIDEWAYS = "sideways"


class VolatilityRegime(Enum):
    """Volatility regime classification"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class VolumeRegime(Enum):
    """Volume regime classification"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


@dataclass
class MarketRegime:
    """
    Market regime features for ML models

    Uses one-hot encoding for regime classification:
    - Trend: 3 binary features (uptrend, downtrend, sideways)
    - Volatility: 3 binary features (low, medium, high)
    - Volume: 3 binary features (low, normal, high)

    Total: 9 one-hot encoded features
    """
    # Trend regime
    trend_regime: TrendRegime = TrendRegime.SIDEWAYS
    trend_strength: float = 0.0  # [0, 1] strength of trend

    # Volatility regime
    volatility_regime: VolatilityRegime = VolatilityRegime.MEDIUM
    volatility_percentile: float = 50.0  # [0, 100] current vs historical

    # Volume regime
    volume_regime: VolumeRegime = VolumeRegime.NORMAL
    volume_ratio: float = 1.0  # Current vs average

    # Regime confidence scores
    trend_confidence: float = 0.5
    volatility_confidence: float = 0.5
    volume_confidence: float = 0.5

    # Metadata
    timestamp: datetime = field(default_factory=datetime.utcnow)
    regime_age_hours: float = 0.0  # How long current regime has lasted

    # Raw metrics used for classification
    current_volatility: float = 0.0
    avg_volatility: float = 0.0
    current_volume: float = 0.0
    avg_volume: float = 0.0

    def to_array(self) -> np.ndarray:
        """
        Convert to numpy array with one-hot encoding

        Returns 9-element array:
        [trend_up, trend_down, trend_side, vol_low, vol_med, vol_high, vol_low, vol_norm, vol_high]
        """
        # One-hot encode trend regime
        trend_onehot = [0.0, 0.0, 0.0]
        if self.trend_regime == TrendRegime.UPTREND:
            trend_onehot = [1.0, 0.0, 0.0]
        elif self.trend_regime == TrendRegime.DOWNTREND:
            trend_onehot = [0.0, 1.0, 0.0]
        else:
            trend_onehot = [0.0, 0.0, 1.0]

        # One-hot encode volatility regime
        vol_onehot = [0.0, 0.0, 0.0]
        if self.volatility_regime == VolatilityRegime.LOW:
            vol_onehot = [1.0, 0.0, 0.0]
        elif self.volatility_regime == VolatilityRegime.MEDIUM:
            vol_onehot = [0.0, 1.0, 0.0]
        else:
            vol_onehot = [0.0, 0.0, 1.0]

        # One-hot encode volume regime
        volume_onehot = [0.0, 0.0, 0.0]
        if self.volume_regime == VolumeRegime.LOW:
            volume_onehot = [1.0, 0.0, 0.0]
        elif self.volume_regime == VolumeRegime.NORMAL:
            volume_onehot = [0.0, 1.0, 0.0]
        else:
            volume_onehot = [0.0, 0.0, 1.0]

        return np.array(
            trend_onehot + vol_onehot + volume_onehot,
            dtype=np.float32
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            'trend_regime': self.trend_regime.value,
            'trend_strength': self.trend_strength,
            'volatility_regime': self.volatility_regime.value,
            'volatility_percentile': self.volatility_percentile,
            'volume_regime': self.volume_regime.value,
            'volume_ratio': self.volume_ratio,
            'trend_confidence': self.trend_confidence,
            'volatility_confidence': self.volatility_confidence,
            'volume_confidence': self.volume_confidence,
            'timestamp': self.timestamp.isoformat(),
            'regime_age_hours': self.regime_age_hours,
            'current_volatility': self.current_volatility,
            'avg_volatility': self.avg_volatility,
            'current_volume': self.current_volume,
            'avg_volume': self.avg_volume
        }

    @classmethod
    def feature_names(cls) -> List[str]:
        """Return list of feature names for dataframe columns"""
        return [
            'trend_uptrend',      # One-hot: uptrend
            'trend_downtrend',    # One-hot: downtrend
            'trend_sideways',     # One-hot: sideways
            'vol_regime_low',     # One-hot: low volatility
            'vol_regime_medium',  # One-hot: medium volatility
            'vol_regime_high',    # One-hot: high volatility
            'volume_regime_low',  # One-hot: low volume
            'volume_regime_normal',  # One-hot: normal volume
            'volume_regime_high'  # One-hot: high volume
        ]

    def get_combined_regime_label(self) -> str:
        """Get combined regime label for logging"""
        return f"{self.trend_regime.value}_{self.volatility_regime.value}_vol_{self.volume_regime.value}"


class MarketRegimeDetector:
    """
    Market regime detector for ML models

    Detects three types of market regimes:
    1. Trend Regime: UPTREND, DOWNTREND, SIDEWAYS
    2. Volatility Regime: LOW, MEDIUM, HIGH
    3. Volume Regime: LOW, NORMAL, HIGH

    Uses technical analysis and statistical methods to classify
    current market conditions.

    Example usage:
        detector = MarketRegimeDetector(market_data_url="http://localhost:8005")
        regime = await detector.get_current_regime("BTCUSDT")
    """

    def __init__(
        self,
        market_data_url: str = "http://localhost:8005",
        technical_analysis_url: str = "http://localhost:8003",
        timeout: float = 15.0,
        cache_ttl_seconds: int = 300,  # 5 minutes
        lookback_periods: int = 100  # Candles for regime detection
    ):
        """
        Initialize market regime detector

        Args:
            market_data_url: URL of market data service
            technical_analysis_url: URL of technical analysis service
            timeout: HTTP request timeout
            cache_ttl_seconds: Cache TTL for regime data
            lookback_periods: Number of periods for regime analysis
        """
        self.market_data_url = market_data_url
        self.technical_analysis_url = technical_analysis_url
        self.timeout = timeout
        self.cache_ttl_seconds = cache_ttl_seconds
        self.lookback_periods = lookback_periods

        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None

        # Cache
        self._cache: Dict[str, Tuple[MarketRegime, datetime]] = {}

        # Historical regime tracking
        self._regime_history: Dict[str, List[Tuple[MarketRegime, datetime]]] = {}
        self._max_history_length = 24

        # Volatility thresholds (percentiles)
        self.vol_low_threshold = 25  # Below 25th percentile = low
        self.vol_high_threshold = 75  # Above 75th percentile = high

        # Volume thresholds (ratio to average)
        self.volume_low_threshold = 0.5  # Below 50% of average = low
        self.volume_high_threshold = 1.5  # Above 150% of average = high

        # Trend detection parameters
        self.trend_threshold = 0.3  # ADX above this indicates trend

        logger.info(f"MarketRegimeDetector initialized (market_data_url={market_data_url})")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        """Close HTTP client connections"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_current_regime(
        self,
        symbol: str,
        interval: str = "60",
        use_cache: bool = True
    ) -> MarketRegime:
        """
        Get current market regime for a symbol

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Timeframe in minutes (default: 60)
            use_cache: Whether to use cached data

        Returns:
            MarketRegime with all regime classifications
        """
        cache_key = f"{symbol}_{interval}"

        # Check cache
        if use_cache and cache_key in self._cache:
            cached_regime, cached_time = self._cache[cache_key]
            age_seconds = (datetime.utcnow() - cached_time).total_seconds()
            if age_seconds < self.cache_ttl_seconds:
                logger.debug(f"Using cached regime for {symbol} (age={age_seconds:.1f}s)")
                return cached_regime

        # Fetch market data
        candles = await self._fetch_candles(symbol, interval, self.lookback_periods)

        if candles is None or len(candles) < 20:
            logger.warning(f"Insufficient data for {symbol}, using default regime")
            return MarketRegime()

        # Detect regimes
        regime = self._detect_all_regimes(symbol, candles)

        # Update cache
        self._cache[cache_key] = (regime, datetime.utcnow())

        # Track regime history
        self._update_regime_history(cache_key, regime)

        return regime

    async def _fetch_candles(
        self,
        symbol: str,
        interval: str,
        limit: int
    ) -> Optional[pd.DataFrame]:
        """
        Fetch candle data from market data service

        Args:
            symbol: Trading pair
            interval: Timeframe in minutes
            limit: Number of candles

        Returns:
            DataFrame with OHLCV data or None
        """
        try:
            client = await self._get_client()

            url = f"{self.market_data_url}/api/v1/klines/{symbol}"
            params = {
                "interval": interval,
                "limit": limit
            }

            response = await client.get(url, params=params)

            if response.status_code == 200:
                data = response.json()

                # Handle wrapped response
                if 'data' in data:
                    data = data['data']

                df = pd.DataFrame(data)

                # Ensure required columns exist
                required = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                if not all(col in df.columns for col in required):
                    logger.warning(f"Missing columns in candle data for {symbol}")
                    return None

                # Convert types
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

                return df

            return None

        except Exception as e:
            logger.warning(f"Failed to fetch candles for {symbol}: {e}")
            return None

    def _detect_all_regimes(
        self,
        symbol: str,
        df: pd.DataFrame
    ) -> MarketRegime:
        """
        Detect all market regimes from price data

        Args:
            symbol: Trading pair
            df: DataFrame with OHLCV data

        Returns:
            MarketRegime with all classifications
        """
        regime = MarketRegime()
        regime.timestamp = datetime.utcnow()

        try:
            # 1. Detect Trend Regime
            trend_result = self._detect_trend_regime(df)
            regime.trend_regime = trend_result['regime']
            regime.trend_strength = trend_result['strength']
            regime.trend_confidence = trend_result['confidence']

            # 2. Detect Volatility Regime
            vol_result = self._detect_volatility_regime(df)
            regime.volatility_regime = vol_result['regime']
            regime.volatility_percentile = vol_result['percentile']
            regime.volatility_confidence = vol_result['confidence']
            regime.current_volatility = vol_result['current']
            regime.avg_volatility = vol_result['average']

            # 3. Detect Volume Regime
            volume_result = self._detect_volume_regime(df)
            regime.volume_regime = volume_result['regime']
            regime.volume_ratio = volume_result['ratio']
            regime.volume_confidence = volume_result['confidence']
            regime.current_volume = volume_result['current']
            regime.avg_volume = volume_result['average']

            # 4. Calculate regime age
            cache_key = f"{symbol}_60"
            regime.regime_age_hours = self._calculate_regime_age(cache_key, regime)

            logger.debug(
                f"Regime for {symbol}: {regime.get_combined_regime_label()} "
                f"(trend_str={regime.trend_strength:.2f}, vol_pct={regime.volatility_percentile:.0f})"
            )

        except Exception as e:
            logger.error(f"Error detecting regime for {symbol}: {e}")

        return regime

    def _detect_trend_regime(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Detect trend regime using multiple indicators

        Uses:
        - ADX for trend strength
        - Price vs moving averages for direction
        - Higher highs/lower lows for confirmation

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Dict with regime, strength, and confidence
        """
        result = {
            'regime': TrendRegime.SIDEWAYS,
            'strength': 0.0,
            'confidence': 0.5
        }

        try:
            close = df['close'].values
            high = df['high'].values
            low = df['low'].values

            # Calculate ADX
            adx = self._calculate_adx(high, low, close, period=14)

            if adx is None or len(adx) == 0:
                return result

            current_adx = adx[-1]

            # ADX > 25 indicates trending market
            is_trending = current_adx > 25

            # Calculate simple moving averages
            sma_20 = np.convolve(close, np.ones(20)/20, mode='valid')
            sma_50 = np.convolve(close, np.ones(50)/50, mode='valid')

            # Get current values
            current_close = close[-1]

            # Determine direction
            if len(sma_20) > 0 and len(sma_50) > 0:
                above_sma20 = current_close > sma_20[-1]
                above_sma50 = current_close > sma_50[-1]
                sma20_above_sma50 = sma_20[-1] > sma_50[-1] if len(sma_20) > 0 and len(sma_50) > 0 else False

                # Check for higher highs / lower lows
                recent_highs = high[-20:]
                recent_lows = low[-20:]
                higher_highs = recent_highs[-1] > np.max(recent_highs[:-1]) if len(recent_highs) > 1 else False
                lower_lows = recent_lows[-1] < np.min(recent_lows[:-1]) if len(recent_lows) > 1 else False

                # Classify trend
                if is_trending:
                    if above_sma20 and above_sma50 and sma20_above_sma50:
                        result['regime'] = TrendRegime.UPTREND
                        result['strength'] = min(current_adx / 50, 1.0)  # Normalize to [0, 1]
                        result['confidence'] = 0.8 if higher_highs else 0.6
                    elif not above_sma20 and not above_sma50 and not sma20_above_sma50:
                        result['regime'] = TrendRegime.DOWNTREND
                        result['strength'] = min(current_adx / 50, 1.0)
                        result['confidence'] = 0.8 if lower_lows else 0.6
                    else:
                        result['regime'] = TrendRegime.SIDEWAYS
                        result['strength'] = 0.3
                        result['confidence'] = 0.5
                else:
                    result['regime'] = TrendRegime.SIDEWAYS
                    result['strength'] = max(0, 1 - current_adx / 25)  # Lower ADX = more sideways
                    result['confidence'] = 0.7

        except Exception as e:
            logger.error(f"Error detecting trend regime: {e}")

        return result

    def _detect_volatility_regime(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Detect volatility regime using ATR and historical comparison

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Dict with regime, percentile, confidence, current, and average
        """
        result = {
            'regime': VolatilityRegime.MEDIUM,
            'percentile': 50.0,
            'confidence': 0.5,
            'current': 0.0,
            'average': 0.0
        }

        try:
            high = df['high'].values
            low = df['low'].values
            close = df['close'].values

            # Calculate ATR
            atr = self._calculate_atr(high, low, close, period=14)

            if atr is None or len(atr) == 0:
                return result

            current_atr = atr[-1]
            historical_atr = atr[:-1]

            # Normalize ATR as percentage of price
            current_atr_pct = current_atr / close[-1] * 100
            historical_atr_pct = historical_atr / close[-len(historical_atr):] * 100

            result['current'] = float(current_atr_pct)
            result['average'] = float(np.mean(historical_atr_pct))

            # Calculate percentile
            percentile = np.percentile(historical_atr_pct, [self.vol_low_threshold, self.vol_high_threshold])

            if current_atr_pct < percentile[0]:
                result['regime'] = VolatilityRegime.LOW
                result['percentile'] = float(np.searchsorted(np.sort(historical_atr_pct), current_atr_pct) / len(historical_atr_pct) * 100)
                result['confidence'] = 0.8
            elif current_atr_pct > percentile[1]:
                result['regime'] = VolatilityRegime.HIGH
                result['percentile'] = float(np.searchsorted(np.sort(historical_atr_pct), current_atr_pct) / len(historical_atr_pct) * 100)
                result['confidence'] = 0.8
            else:
                result['regime'] = VolatilityRegime.MEDIUM
                result['percentile'] = 50.0
                result['confidence'] = 0.6

        except Exception as e:
            logger.error(f"Error detecting volatility regime: {e}")

        return result

    def _detect_volume_regime(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Detect volume regime by comparing to historical average

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Dict with regime, ratio, confidence, current, and average
        """
        result = {
            'regime': VolumeRegime.NORMAL,
            'ratio': 1.0,
            'confidence': 0.5,
            'current': 0.0,
            'average': 0.0
        }

        try:
            volume = df['volume'].values

            # Calculate recent volume (last 5 periods)
            recent_volume = np.mean(volume[-5:])

            # Calculate average volume (excluding recent)
            avg_volume = np.mean(volume[:-5]) if len(volume) > 5 else np.mean(volume)

            result['current'] = float(recent_volume)
            result['average'] = float(avg_volume)

            if avg_volume > 0:
                ratio = recent_volume / avg_volume
                result['ratio'] = float(ratio)

                if ratio < self.volume_low_threshold:
                    result['regime'] = VolumeRegime.LOW
                    result['confidence'] = 0.8
                elif ratio > self.volume_high_threshold:
                    result['regime'] = VolumeRegime.HIGH
                    result['confidence'] = 0.8
                else:
                    result['regime'] = VolumeRegime.NORMAL
                    result['confidence'] = 0.6

        except Exception as e:
            logger.error(f"Error detecting volume regime: {e}")

        return result

    def _calculate_adx(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = 14
    ) -> Optional[np.ndarray]:
        """
        Calculate Average Directional Index (ADX)

        Args:
            high: High prices
            low: Low prices
            close: Close prices
            period: ADX period

        Returns:
            ADX values or None if insufficient data
        """
        try:
            if len(high) < period + 1:
                return None

            # True Range
            tr = np.maximum(
                high[1:] - low[1:],
                np.maximum(
                    np.abs(high[1:] - close[:-1]),
                    np.abs(low[1:] - close[:-1])
                )
            )

            # +DM and -DM
            plus_dm = np.where(
                (high[1:] - high[:-1]) > (low[:-1] - low[1:]),
                np.maximum(high[1:] - high[:-1], 0),
                0
            )
            minus_dm = np.where(
                (low[:-1] - low[1:]) > (high[1:] - high[:-1]),
                np.maximum(low[:-1] - low[1:], 0),
                0
            )

            # Smoothed averages
            atr = self._ema(tr, period)
            plus_di = 100 * self._ema(plus_dm, period) / atr
            minus_di = 100 * self._ema(minus_dm, period) / atr

            # DX and ADX
            dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
            adx = self._ema(dx, period)

            return adx

        except Exception as e:
            logger.error(f"Error calculating ADX: {e}")
            return None

    def _calculate_atr(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = 14
    ) -> Optional[np.ndarray]:
        """
        Calculate Average True Range (ATR)

        Args:
            high: High prices
            low: Low prices
            close: Close prices
            period: ATR period

        Returns:
            ATR values or None if insufficient data
        """
        try:
            if len(high) < period + 1:
                return None

            # True Range
            tr = np.maximum(
                high[1:] - low[1:],
                np.maximum(
                    np.abs(high[1:] - close[:-1]),
                    np.abs(low[1:] - close[:-1])
                )
            )

            # ATR as EMA of True Range
            atr = self._ema(tr, period)

            return atr

        except Exception as e:
            logger.error(f"Error calculating ATR: {e}")
            return None

    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average"""
        alpha = 2 / (period + 1)
        ema = np.zeros_like(data)
        ema[0] = data[0]

        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]

        return ema

    def _update_regime_history(self, cache_key: str, regime: MarketRegime):
        """Update regime history for a symbol"""
        if cache_key not in self._regime_history:
            self._regime_history[cache_key] = []

        history = self._regime_history[cache_key]
        history.append((regime, datetime.utcnow()))

        # Trim history
        if len(history) > self._max_history_length:
            self._regime_history[cache_key] = history[-self._max_history_length:]

    def _calculate_regime_age(self, cache_key: str, current_regime: MarketRegime) -> float:
        """
        Calculate how long current regime has persisted

        Args:
            cache_key: Cache key for symbol/interval
            current_regime: Current regime classification

        Returns:
            Age in hours
        """
        if cache_key not in self._regime_history:
            return 0.0

        history = self._regime_history[cache_key]
        current_label = current_regime.get_combined_regime_label()

        # Find when regime started
        regime_start = datetime.utcnow()
        for regime, timestamp in reversed(history):
            if regime.get_combined_regime_label() == current_label:
                regime_start = timestamp
            else:
                break

        age_hours = (datetime.utcnow() - regime_start).total_seconds() / 3600
        return float(age_hours)

    async def get_batch_regimes(
        self,
        symbols: List[str],
        interval: str = "60"
    ) -> Dict[str, MarketRegime]:
        """
        Get market regimes for multiple symbols in parallel

        Args:
            symbols: List of trading pairs
            interval: Timeframe in minutes

        Returns:
            Dictionary mapping symbol to MarketRegime
        """
        tasks = [self.get_current_regime(symbol, interval) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        regime_dict = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to get regime for {symbol}: {result}")
                regime_dict[symbol] = MarketRegime()
            else:
                regime_dict[symbol] = result

        return regime_dict

    def get_regime_trading_bias(self, regime: MarketRegime) -> Dict[str, Any]:
        """
        Get trading bias based on current regime

        Args:
            regime: MarketRegime object

        Returns:
            Dict with bias, confidence, and recommendations
        """
        bias = "NEUTRAL"
        confidence = 0.5
        recommendations = []

        # Trend-based bias
        if regime.trend_regime == TrendRegime.UPTREND:
            bias = "LONG"
            confidence = regime.trend_confidence * regime.trend_strength
            recommendations.append("Favor long positions with trend")
        elif regime.trend_regime == TrendRegime.DOWNTREND:
            bias = "SHORT"
            confidence = regime.trend_confidence * regime.trend_strength
            recommendations.append("Favor short positions with trend")
        else:
            recommendations.append("Range trading strategies preferred")

        # Volatility adjustments
        if regime.volatility_regime == VolatilityRegime.HIGH:
            recommendations.append("Reduce position size due to high volatility")
            confidence *= 0.8
        elif regime.volatility_regime == VolatilityRegime.LOW:
            recommendations.append("Consider wider targets in low volatility")

        # Volume considerations
        if regime.volume_regime == VolumeRegime.LOW:
            recommendations.append("Caution: Low volume may lead to false signals")
            confidence *= 0.9
        elif regime.volume_regime == VolumeRegime.HIGH:
            recommendations.append("High volume confirms regime strength")
            confidence = min(confidence * 1.1, 1.0)

        return {
            'bias': bias,
            'confidence': confidence,
            'recommendations': recommendations,
            'regime_label': regime.get_combined_regime_label()
        }
