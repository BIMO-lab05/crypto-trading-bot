"""
Market Regime Detector - Core Implementation
Classifies market conditions (trending/ranging/volatile) for adaptive ML model behavior

Author: Phase 6.3 ML Team
Date: 2025-12-11
Version: 1.0.0

Regime Classifications:
    A. Trend Regime (3 states):
       - STRONG_UPTREND: Price > 200 EMA, ADX > 25, rising
       - RANGING: Price oscillating around 200 EMA, ADX < 20
       - STRONG_DOWNTREND: Price < 200 EMA, ADX > 25, falling

    B. Volatility Regime (3 states):
       - LOW_VOLATILITY: ATR < 20th percentile (90-day)
       - NORMAL_VOLATILITY: ATR between 20th-80th percentile
       - HIGH_VOLATILITY: ATR > 80th percentile

    C. Volume Regime (3 states):
       - LOW_VOLUME: Volume < 30th percentile (90-day)
       - NORMAL_VOLUME: Volume between 30th-70th percentile
       - HIGH_VOLUME: Volume > 70th percentile
"""

import logging
import numpy as np
import pandas as pd
from enum import Enum
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from pydantic import BaseModel, Field

# Configure module logger
logger = logging.getLogger(__name__)


# =============================================================================
# Enums for Regime Classification
# =============================================================================

class TrendRegime(str, Enum):
    """Trend regime classification states"""
    STRONG_UPTREND = "STRONG_UPTREND"       # Price > 200 EMA, ADX > 25, rising
    RANGING = "RANGING"                      # Price oscillating around 200 EMA, ADX < 20
    STRONG_DOWNTREND = "STRONG_DOWNTREND"   # Price < 200 EMA, ADX > 25, falling


class VolatilityRegime(str, Enum):
    """Volatility regime classification states"""
    LOW_VOLATILITY = "LOW_VOLATILITY"       # ATR < 20th percentile (90-day)
    NORMAL_VOLATILITY = "NORMAL_VOLATILITY" # ATR between 20th-80th percentile
    HIGH_VOLATILITY = "HIGH_VOLATILITY"     # ATR > 80th percentile


class VolumeRegime(str, Enum):
    """Volume regime classification states"""
    LOW_VOLUME = "LOW_VOLUME"               # Volume < 30th percentile (90-day)
    NORMAL_VOLUME = "NORMAL_VOLUME"         # Volume between 30th-70th percentile
    HIGH_VOLUME = "HIGH_VOLUME"             # Volume > 70th percentile


# =============================================================================
# Data Models
# =============================================================================

class MarketRegime(BaseModel):
    """
    Complete market regime classification for a symbol

    Combines trend, volatility, and volume regimes into a single assessment
    """
    # Symbol and timestamp
    symbol: str = Field(..., description="Trading pair (e.g., BTCUSDT)")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When regime was detected")

    # Individual regime classifications
    trend: TrendRegime = Field(..., description="Trend regime classification")
    volatility: VolatilityRegime = Field(..., description="Volatility regime classification")
    volume: VolumeRegime = Field(..., description="Volume regime classification")

    # Confidence score (0-1)
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall confidence in regime classification"
    )

    # Combined regime label
    regime_label: str = Field(..., description="Combined label like 'UPTREND_HIGH_VOL'")

    # Indicator values used for classification
    indicators: Dict[str, float] = Field(
        default_factory=dict,
        description="Raw indicator values used for classification"
    )

    class Config:
        """Pydantic configuration"""
        use_enum_values = True  # Serialize enums as their values


class RegimeHistory(BaseModel):
    """Historical regime changes for a symbol"""
    symbol: str = Field(..., description="Trading pair")
    regimes: List[MarketRegime] = Field(default_factory=list, description="Historical regime states")
    period_days: int = Field(default=30, description="History period in days")


class RegimeTransitionMatrix(BaseModel):
    """
    Regime transition probability matrix

    Tracks how often regimes transition from one state to another
    """
    symbol: str = Field(..., description="Trading pair")
    matrix: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description="Transition probabilities: matrix[from_regime][to_regime] = probability"
    )
    total_transitions: int = Field(default=0, description="Total transitions observed")
    last_updated: datetime = Field(default_factory=datetime.utcnow)


@dataclass
class IndicatorValues:
    """
    Container for all indicator values used in regime detection

    Attributes:
        ema_200: 200-period Exponential Moving Average
        adx: Average Directional Index (14-period)
        plus_di: Positive Directional Indicator
        minus_di: Negative Directional Indicator
        atr: Average True Range (14-period)
        atr_percentile: ATR percentile (0-100) relative to 90-day history
        current_volume: Current period volume
        volume_percentile: Volume percentile (0-100) relative to 90-day history
        current_price: Current close price
        price_vs_ema: Price position relative to EMA (% difference)
        adx_slope: Slope of ADX (positive = strengthening, negative = weakening)
    """
    ema_200: float = 0.0
    adx: float = 0.0
    plus_di: float = 0.0
    minus_di: float = 0.0
    atr: float = 0.0
    atr_percentile: float = 50.0
    current_volume: float = 0.0
    volume_percentile: float = 50.0
    current_price: float = 0.0
    price_vs_ema: float = 0.0
    adx_slope: float = 0.0


# =============================================================================
# Market Regime Detector Class
# =============================================================================

class MarketRegimeDetector:
    """
    Market Regime Detector for adaptive ML models

    Classifies current market conditions into:
    - Trend regimes (uptrend, ranging, downtrend)
    - Volatility regimes (low, normal, high)
    - Volume regimes (low, normal, high)

    Usage:
        detector = MarketRegimeDetector()

        # Detect current regime
        regime = detector.detect_regime(prices, volumes)

        # Get regime probabilities
        probs = detector.get_regime_probabilities(prices, volumes)
    """

    # =============================================================================
    # Constants for regime classification thresholds
    # =============================================================================

    # ADX thresholds for trend strength
    ADX_TRENDING_THRESHOLD: float = 25.0  # ADX > 25 indicates strong trend
    ADX_RANGING_THRESHOLD: float = 20.0   # ADX < 20 indicates ranging/consolidation

    # Price vs EMA threshold (percentage)
    PRICE_EMA_TREND_THRESHOLD: float = 1.0  # % above/below EMA for trend confirmation

    # Volatility percentile thresholds (relative to 90-day history)
    VOLATILITY_LOW_PERCENTILE: float = 20.0   # ATR < 20th percentile = low volatility
    VOLATILITY_HIGH_PERCENTILE: float = 80.0  # ATR > 80th percentile = high volatility

    # Volume percentile thresholds (relative to 90-day history)
    VOLUME_LOW_PERCENTILE: float = 30.0   # Volume < 30th percentile = low volume
    VOLUME_HIGH_PERCENTILE: float = 70.0  # Volume > 70th percentile = high volume

    # Default periods for indicator calculations
    EMA_PERIOD: int = 200
    ADX_PERIOD: int = 14
    ATR_PERIOD: int = 14
    LOOKBACK_DAYS: int = 90

    def __init__(
        self,
        ema_period: int = 200,
        adx_period: int = 14,
        atr_period: int = 14,
        lookback_days: int = 90,
        adx_trending_threshold: float = 25.0,
        adx_ranging_threshold: float = 20.0
    ):
        """
        Initialize Market Regime Detector

        Args:
            ema_period: Period for EMA calculation (default: 200)
            adx_period: Period for ADX calculation (default: 14)
            atr_period: Period for ATR calculation (default: 14)
            lookback_days: Days of history for percentile calculations (default: 90)
            adx_trending_threshold: ADX threshold for trending market (default: 25)
            adx_ranging_threshold: ADX threshold for ranging market (default: 20)
        """
        # Store configuration parameters
        self.ema_period = ema_period
        self.adx_period = adx_period
        self.atr_period = atr_period
        self.lookback_days = lookback_days

        # Store classification thresholds
        self.adx_trending_threshold = adx_trending_threshold
        self.adx_ranging_threshold = adx_ranging_threshold

        # Cache for historical regime data
        self._regime_cache: Dict[str, MarketRegime] = {}
        self._transition_matrices: Dict[str, RegimeTransitionMatrix] = {}

        logger.info(
            f"MarketRegimeDetector initialized with EMA={ema_period}, "
            f"ADX={adx_period}, ATR={atr_period}, lookback={lookback_days}d"
        )

    # =============================================================================
    # Main Detection Methods
    # =============================================================================

    def detect_regime(
        self,
        prices: pd.DataFrame,
        symbol: str = "UNKNOWN"
    ) -> MarketRegime:
        """
        Detect current market regime from price data

        Args:
            prices: DataFrame with columns [timestamp, open, high, low, close, volume]
                    OR [open, high, low, close, volume] with datetime index
            symbol: Trading pair symbol (e.g., BTCUSDT)

        Returns:
            MarketRegime object with complete classification

        Raises:
            ValueError: If insufficient data for calculations
        """
        logger.debug(f"Detecting regime for {symbol} with {len(prices)} candles")

        # Validate and prepare data
        df = self._prepare_dataframe(prices)

        # Check minimum data requirements
        min_required = max(self.ema_period, self.lookback_days * 24) + 50
        if len(df) < min_required:
            logger.warning(
                f"Insufficient data for {symbol}: {len(df)} candles "
                f"(need {min_required}). Using available data."
            )

        # Calculate all indicators
        indicators = self._calculate_all_indicators(df)

        # Classify each regime dimension
        trend = self._classify_trend(indicators)
        volatility = self._classify_volatility(indicators)
        volume = self._classify_volume(indicators)

        # Calculate overall confidence
        confidence = self._calculate_confidence(indicators, trend, volatility, volume)

        # Create combined label
        regime_label = self._create_regime_label(trend, volatility, volume)

        # Build indicator dict for response
        indicator_dict = {
            "ema_200": round(indicators.ema_200, 4),
            "adx": round(indicators.adx, 2),
            "plus_di": round(indicators.plus_di, 2),
            "minus_di": round(indicators.minus_di, 2),
            "atr": round(indicators.atr, 4),
            "atr_percentile": round(indicators.atr_percentile, 1),
            "current_price": round(indicators.current_price, 4),
            "price_vs_ema_pct": round(indicators.price_vs_ema, 2),
            "volume_percentile": round(indicators.volume_percentile, 1),
            "adx_slope": round(indicators.adx_slope, 4),
        }

        # Create regime object
        regime = MarketRegime(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            trend=trend,
            volatility=volatility,
            volume=volume,
            confidence=confidence,
            regime_label=regime_label,
            indicators=indicator_dict
        )

        # Update cache and transition matrix
        self._update_cache(symbol, regime)

        logger.info(
            f"Detected regime for {symbol}: {regime_label} "
            f"(confidence: {confidence:.2f})"
        )

        return regime

    def detect_trend_regime(
        self,
        prices: List[float],
        highs: Optional[List[float]] = None,
        lows: Optional[List[float]] = None
    ) -> TrendRegime:
        """
        Detect trend regime from price list

        Args:
            prices: List of close prices
            highs: List of high prices (optional, for ADX)
            lows: List of low prices (optional, for ADX)

        Returns:
            TrendRegime enum value
        """
        # Convert to series for calculations
        close = pd.Series(prices)

        # Calculate EMA
        ema_200 = close.ewm(span=self.ema_period, adjust=False).mean()

        # Calculate ADX if high/low provided
        if highs is not None and lows is not None:
            high = pd.Series(highs)
            low = pd.Series(lows)
            adx, plus_di, minus_di = self._calculate_adx(high, low, close)
        else:
            # Estimate ADX from price volatility
            adx = pd.Series([20.0] * len(close))  # Default neutral
            plus_di = pd.Series([25.0] * len(close))
            minus_di = pd.Series([25.0] * len(close))

        # Get current values
        current_price = close.iloc[-1]
        current_ema = ema_200.iloc[-1]
        current_adx = adx.iloc[-1] if len(adx) > 0 else 20.0
        current_plus_di = plus_di.iloc[-1] if len(plus_di) > 0 else 25.0
        current_minus_di = minus_di.iloc[-1] if len(minus_di) > 0 else 25.0

        # Calculate price vs EMA percentage
        price_vs_ema = ((current_price - current_ema) / current_ema) * 100

        # Calculate ADX slope (trend strength change)
        adx_slope = 0.0
        if len(adx) >= 5:
            adx_slope = (adx.iloc[-1] - adx.iloc[-5]) / 5

        # Create indicator container
        indicators = IndicatorValues(
            ema_200=current_ema,
            adx=current_adx,
            plus_di=current_plus_di,
            minus_di=current_minus_di,
            current_price=current_price,
            price_vs_ema=price_vs_ema,
            adx_slope=adx_slope
        )

        return self._classify_trend(indicators)

    def detect_volatility_regime(
        self,
        returns: List[float],
        historical_atr: Optional[List[float]] = None
    ) -> VolatilityRegime:
        """
        Detect volatility regime from returns

        Args:
            returns: List of period returns (or ATR values)
            historical_atr: Historical ATR values for percentile calculation

        Returns:
            VolatilityRegime enum value
        """
        # Calculate current volatility (std of returns)
        returns_series = pd.Series(returns)
        current_vol = returns_series.iloc[-self.atr_period:].std() * np.sqrt(252)  # Annualized

        # Calculate percentile
        if historical_atr is not None and len(historical_atr) > 0:
            atr_percentile = self._calculate_percentile(current_vol, historical_atr)
        else:
            # Use returns history for percentile
            all_vols = returns_series.rolling(self.atr_period).std() * np.sqrt(252)
            atr_percentile = self._calculate_percentile(current_vol, all_vols.dropna().tolist())

        # Create indicator container
        indicators = IndicatorValues(
            atr=current_vol,
            atr_percentile=atr_percentile
        )

        return self._classify_volatility(indicators)

    def detect_volume_regime(
        self,
        volumes: List[float]
    ) -> VolumeRegime:
        """
        Detect volume regime from volume data

        Args:
            volumes: List of volume values

        Returns:
            VolumeRegime enum value
        """
        volumes_series = pd.Series(volumes)

        # Get current volume and calculate percentile
        current_volume = volumes_series.iloc[-1]
        volume_percentile = self._calculate_percentile(current_volume, volumes)

        # Create indicator container
        indicators = IndicatorValues(
            current_volume=current_volume,
            volume_percentile=volume_percentile
        )

        return self._classify_volume(indicators)

    def get_current_regime(self, symbol: str) -> Optional[MarketRegime]:
        """
        Get cached current regime for a symbol

        Args:
            symbol: Trading pair symbol

        Returns:
            MarketRegime if cached, None otherwise
        """
        return self._regime_cache.get(symbol)

    def get_regime_probability(
        self,
        prices: pd.DataFrame,
        symbol: str = "UNKNOWN"
    ) -> Dict[str, float]:
        """
        Get probability distribution over regime states

        Uses fuzzy classification to return probabilities for each regime

        Args:
            prices: DataFrame with OHLCV data
            symbol: Trading pair symbol

        Returns:
            Dict mapping regime labels to probabilities
        """
        logger.debug(f"Calculating regime probabilities for {symbol}")

        # Prepare data and calculate indicators
        df = self._prepare_dataframe(prices)
        indicators = self._calculate_all_indicators(df)

        # Calculate probabilities for each dimension
        trend_probs = self._calculate_trend_probabilities(indicators)
        vol_probs = self._calculate_volatility_probabilities(indicators)
        volume_probs = self._calculate_volume_probabilities(indicators)

        # Combine into joint probabilities for major regime states
        regime_probs = {}

        # Calculate combined probabilities for key regime combinations
        for trend_regime, trend_prob in trend_probs.items():
            for vol_regime, vol_prob in vol_probs.items():
                label = f"{trend_regime}_{vol_regime}"
                regime_probs[label] = trend_prob * vol_prob

        # Add individual dimension probabilities
        regime_probs.update({
            "trend": trend_probs,
            "volatility": vol_probs,
            "volume": volume_probs
        })

        return regime_probs

    def get_regime_history(
        self,
        symbol: str,
        period_days: int = 30
    ) -> RegimeHistory:
        """
        Get historical regime changes for a symbol

        Note: Requires external data source or database integration

        Args:
            symbol: Trading pair symbol
            period_days: Number of days of history

        Returns:
            RegimeHistory object
        """
        # This would typically query from TimescaleDB or Redis
        # For now, return empty history
        logger.debug(f"Getting regime history for {symbol} ({period_days} days)")

        return RegimeHistory(
            symbol=symbol,
            regimes=[],
            period_days=period_days
        )

    def get_transition_matrix(self, symbol: str) -> RegimeTransitionMatrix:
        """
        Get regime transition probability matrix for a symbol

        Args:
            symbol: Trading pair symbol

        Returns:
            RegimeTransitionMatrix with transition probabilities
        """
        if symbol in self._transition_matrices:
            return self._transition_matrices[symbol]

        # Return empty matrix
        return RegimeTransitionMatrix(
            symbol=symbol,
            matrix={},
            total_transitions=0
        )

    # =============================================================================
    # Indicator Calculation Methods
    # =============================================================================

    def _prepare_dataframe(self, prices: pd.DataFrame) -> pd.DataFrame:
        """
        Prepare and validate DataFrame for calculations

        Args:
            prices: Input DataFrame

        Returns:
            Cleaned DataFrame with proper structure
        """
        df = prices.copy()

        # Ensure required columns exist
        required_cols = ['open', 'high', 'low', 'close', 'volume']

        # Handle timestamp column
        if 'timestamp' in df.columns:
            if not isinstance(df.index, pd.DatetimeIndex):
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.set_index('timestamp')
        elif not isinstance(df.index, pd.DatetimeIndex):
            # Try to infer datetime index
            try:
                df.index = pd.to_datetime(df.index)
            except Exception:
                pass  # Keep numeric index

        # Validate required columns
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        # Convert to numeric and drop NaN
        for col in required_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.dropna(subset=required_cols)

        return df

    def _calculate_all_indicators(self, df: pd.DataFrame) -> IndicatorValues:
        """
        Calculate all technical indicators needed for regime detection

        Args:
            df: Prepared DataFrame with OHLCV data

        Returns:
            IndicatorValues container with all indicator values
        """
        # Extract price series
        high = df['high']
        low = df['low']
        close = df['close']
        volume = df['volume']

        # Calculate EMA (200-period by default)
        ema_200 = close.ewm(span=self.ema_period, adjust=False).mean()

        # Calculate ADX and directional indicators
        adx, plus_di, minus_di = self._calculate_adx(high, low, close)

        # Calculate ATR
        atr = self._calculate_atr(high, low, close)

        # Get current values
        current_price = close.iloc[-1]
        current_ema = ema_200.iloc[-1]
        current_adx = adx.iloc[-1] if len(adx) > 0 else 20.0
        current_plus_di = plus_di.iloc[-1] if len(plus_di) > 0 else 25.0
        current_minus_di = minus_di.iloc[-1] if len(minus_di) > 0 else 25.0
        current_atr = atr.iloc[-1] if len(atr) > 0 else 0.0
        current_volume = volume.iloc[-1]

        # Calculate percentiles (relative to lookback period)
        lookback_candles = min(len(df), self.lookback_days * 24)
        atr_history = atr.iloc[-lookback_candles:].dropna().tolist()
        volume_history = volume.iloc[-lookback_candles:].tolist()

        atr_percentile = self._calculate_percentile(current_atr, atr_history)
        volume_percentile = self._calculate_percentile(current_volume, volume_history)

        # Calculate price vs EMA percentage
        price_vs_ema = ((current_price - current_ema) / current_ema) * 100

        # Calculate ADX slope (trend strength change over last 5 periods)
        adx_slope = 0.0
        if len(adx) >= 5:
            adx_slope = (adx.iloc[-1] - adx.iloc[-5]) / 5

        return IndicatorValues(
            ema_200=current_ema,
            adx=current_adx,
            plus_di=current_plus_di,
            minus_di=current_minus_di,
            atr=current_atr,
            atr_percentile=atr_percentile,
            current_volume=current_volume,
            volume_percentile=volume_percentile,
            current_price=current_price,
            price_vs_ema=price_vs_ema,
            adx_slope=adx_slope
        )

    def _calculate_adx(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate Average Directional Index (ADX) and DI+/DI-

        ADX measures trend strength (not direction):
        - ADX > 25: Strong trend
        - ADX < 20: Weak trend / ranging market
        - ADX 20-25: Developing trend

        Args:
            high: High prices
            low: Low prices
            close: Close prices

        Returns:
            Tuple of (ADX, Plus DI, Minus DI) as Series
        """
        # Calculate True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Calculate +DM and -DM (Directional Movement)
        plus_dm = high.diff()
        minus_dm = -low.diff()

        # Apply conditions for valid DM
        plus_dm = plus_dm.where((plus_dm > 0) & (plus_dm > minus_dm), 0)
        minus_dm = minus_dm.where((minus_dm > 0) & (minus_dm > plus_dm), 0)

        # Smooth TR, +DM, -DM using EMA
        atr_period = self.adx_period
        smooth_tr = tr.ewm(span=atr_period, adjust=False).mean()
        smooth_plus_dm = plus_dm.ewm(span=atr_period, adjust=False).mean()
        smooth_minus_dm = minus_dm.ewm(span=atr_period, adjust=False).mean()

        # Calculate +DI and -DI
        plus_di = 100 * smooth_plus_dm / smooth_tr
        minus_di = 100 * smooth_minus_dm / smooth_tr

        # Calculate DX (Directional Index)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)

        # Calculate ADX (smoothed DX)
        adx = dx.ewm(span=atr_period, adjust=False).mean()

        return adx, plus_di, minus_di

    def _calculate_atr(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series
    ) -> pd.Series:
        """
        Calculate Average True Range (ATR)

        ATR measures volatility:
        - Higher ATR = Higher volatility
        - Lower ATR = Lower volatility

        Args:
            high: High prices
            low: Low prices
            close: Close prices

        Returns:
            ATR Series
        """
        # Calculate True Range components
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        # True Range is max of the three
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # ATR is smoothed True Range
        atr = true_range.ewm(span=self.atr_period, adjust=False).mean()

        return atr

    def _calculate_percentile(
        self,
        value: float,
        history: List[float]
    ) -> float:
        """
        Calculate percentile of value within historical distribution

        Args:
            value: Current value to rank
            history: Historical values

        Returns:
            Percentile (0-100)
        """
        if not history or len(history) == 0:
            return 50.0  # Default to median

        # Convert to numpy for efficient calculation
        history_arr = np.array(history)
        history_arr = history_arr[~np.isnan(history_arr)]

        if len(history_arr) == 0:
            return 50.0

        # Calculate percentile rank
        percentile = (np.sum(history_arr < value) / len(history_arr)) * 100

        return float(percentile)

    # =============================================================================
    # Classification Methods
    # =============================================================================

    def _classify_trend(self, indicators: IndicatorValues) -> TrendRegime:
        """
        Classify trend regime based on EMA, ADX, and directional indicators

        Classification Logic:
        - STRONG_UPTREND: Price > EMA_200, ADX > 25, +DI > -DI
        - STRONG_DOWNTREND: Price < EMA_200, ADX > 25, -DI > +DI
        - RANGING: ADX < 20 or price near EMA_200

        Args:
            indicators: IndicatorValues container

        Returns:
            TrendRegime enum value
        """
        adx = indicators.adx
        plus_di = indicators.plus_di
        minus_di = indicators.minus_di
        price_vs_ema = indicators.price_vs_ema

        # Check for ranging market (weak trend)
        if adx < self.adx_ranging_threshold:
            return TrendRegime.RANGING

        # Check for trending market (strong ADX)
        if adx >= self.adx_trending_threshold:
            # Determine direction based on price vs EMA and DI crossover
            if price_vs_ema > self.PRICE_EMA_TREND_THRESHOLD and plus_di > minus_di:
                return TrendRegime.STRONG_UPTREND
            elif price_vs_ema < -self.PRICE_EMA_TREND_THRESHOLD and minus_di > plus_di:
                return TrendRegime.STRONG_DOWNTREND

        # Default to ranging for ambiguous cases
        return TrendRegime.RANGING

    def _classify_volatility(self, indicators: IndicatorValues) -> VolatilityRegime:
        """
        Classify volatility regime based on ATR percentile

        Classification Logic:
        - LOW_VOLATILITY: ATR < 20th percentile
        - HIGH_VOLATILITY: ATR > 80th percentile
        - NORMAL_VOLATILITY: Between 20th and 80th percentile

        Args:
            indicators: IndicatorValues container

        Returns:
            VolatilityRegime enum value
        """
        atr_percentile = indicators.atr_percentile

        if atr_percentile < self.VOLATILITY_LOW_PERCENTILE:
            return VolatilityRegime.LOW_VOLATILITY
        elif atr_percentile > self.VOLATILITY_HIGH_PERCENTILE:
            return VolatilityRegime.HIGH_VOLATILITY
        else:
            return VolatilityRegime.NORMAL_VOLATILITY

    def _classify_volume(self, indicators: IndicatorValues) -> VolumeRegime:
        """
        Classify volume regime based on volume percentile

        Classification Logic:
        - LOW_VOLUME: Volume < 30th percentile
        - HIGH_VOLUME: Volume > 70th percentile
        - NORMAL_VOLUME: Between 30th and 70th percentile

        Args:
            indicators: IndicatorValues container

        Returns:
            VolumeRegime enum value
        """
        volume_percentile = indicators.volume_percentile

        if volume_percentile < self.VOLUME_LOW_PERCENTILE:
            return VolumeRegime.LOW_VOLUME
        elif volume_percentile > self.VOLUME_HIGH_PERCENTILE:
            return VolumeRegime.HIGH_VOLUME
        else:
            return VolumeRegime.NORMAL_VOLUME

    def _calculate_confidence(
        self,
        indicators: IndicatorValues,
        trend: TrendRegime,
        volatility: VolatilityRegime,
        volume: VolumeRegime
    ) -> float:
        """
        Calculate overall confidence in regime classification

        Confidence is based on:
        - Clarity of ADX signal (distance from threshold)
        - Consistency between indicators
        - Historical regime stability

        Args:
            indicators: IndicatorValues container
            trend: Classified trend regime
            volatility: Classified volatility regime
            volume: Classified volume regime

        Returns:
            Confidence score (0.0 to 1.0)
        """
        confidence_scores = []

        # ADX confidence: Higher ADX = more confident trend classification
        adx = indicators.adx
        if trend != TrendRegime.RANGING:
            # For trending markets, confidence scales with ADX above threshold
            adx_confidence = min((adx - self.adx_trending_threshold) / 25.0, 1.0)
            adx_confidence = max(adx_confidence, 0.0)
        else:
            # For ranging markets, confidence scales with how low ADX is
            adx_confidence = min((self.adx_ranging_threshold - adx) / 20.0 + 0.5, 1.0)
            adx_confidence = max(adx_confidence, 0.0)
        confidence_scores.append(adx_confidence)

        # Volatility confidence: Based on distance from normal range
        atr_percentile = indicators.atr_percentile
        if volatility == VolatilityRegime.LOW_VOLATILITY:
            vol_confidence = 1.0 - (atr_percentile / self.VOLATILITY_LOW_PERCENTILE)
        elif volatility == VolatilityRegime.HIGH_VOLATILITY:
            vol_confidence = (atr_percentile - self.VOLATILITY_HIGH_PERCENTILE) / 20.0
        else:
            # Normal volatility - confidence based on distance from boundaries
            mid_point = 50.0
            distance = abs(atr_percentile - mid_point)
            max_distance = 30.0  # Distance to boundary
            vol_confidence = (max_distance - distance) / max_distance
        vol_confidence = max(0.0, min(1.0, vol_confidence))
        confidence_scores.append(vol_confidence)

        # Volume confidence: Similar to volatility
        volume_percentile = indicators.volume_percentile
        if volume == VolumeRegime.LOW_VOLUME:
            vol_conf = 1.0 - (volume_percentile / self.VOLUME_LOW_PERCENTILE)
        elif volume == VolumeRegime.HIGH_VOLUME:
            vol_conf = (volume_percentile - self.VOLUME_HIGH_PERCENTILE) / 30.0
        else:
            mid_point = 50.0
            distance = abs(volume_percentile - mid_point)
            max_distance = 20.0
            vol_conf = (max_distance - distance) / max_distance
        vol_conf = max(0.0, min(1.0, vol_conf))
        confidence_scores.append(vol_conf)

        # Average confidence scores
        overall_confidence = np.mean(confidence_scores)

        return round(overall_confidence, 4)

    def _create_regime_label(
        self,
        trend: TrendRegime,
        volatility: VolatilityRegime,
        volume: VolumeRegime
    ) -> str:
        """
        Create combined regime label from individual classifications

        Format: {TREND}_{VOLATILITY}_{VOLUME}

        Examples:
        - UPTREND_HIGH_VOL_HIGH_VOL
        - RANGING_LOW_VOL_NORMAL_VOL
        - DOWNTREND_NORMAL_VOL_LOW_VOL

        Args:
            trend: Trend regime
            volatility: Volatility regime
            volume: Volume regime

        Returns:
            Combined regime label string
        """
        # Shorten labels for readability
        trend_short = {
            TrendRegime.STRONG_UPTREND: "UPTREND",
            TrendRegime.RANGING: "RANGING",
            TrendRegime.STRONG_DOWNTREND: "DOWNTREND"
        }

        vol_short = {
            VolatilityRegime.LOW_VOLATILITY: "LOW_VOL",
            VolatilityRegime.NORMAL_VOLATILITY: "NORM_VOL",
            VolatilityRegime.HIGH_VOLATILITY: "HIGH_VOL"
        }

        volume_short = {
            VolumeRegime.LOW_VOLUME: "LOW_VOLM",
            VolumeRegime.NORMAL_VOLUME: "NORM_VOLM",
            VolumeRegime.HIGH_VOLUME: "HIGH_VOLM"
        }

        return f"{trend_short[trend]}_{vol_short[volatility]}_{volume_short[volume]}"

    # =============================================================================
    # Probability Calculation Methods
    # =============================================================================

    def _calculate_trend_probabilities(
        self,
        indicators: IndicatorValues
    ) -> Dict[str, float]:
        """
        Calculate probability distribution over trend regimes

        Uses fuzzy membership functions based on ADX and price vs EMA

        Args:
            indicators: IndicatorValues container

        Returns:
            Dict mapping trend regime to probability
        """
        adx = indicators.adx
        price_vs_ema = indicators.price_vs_ema
        plus_di = indicators.plus_di
        minus_di = indicators.minus_di

        # Base probabilities from ADX
        # Strong trend probability increases with ADX
        trend_strength = min(max(adx - 20, 0) / 25, 1.0)

        # Ranging probability (inverse of trend strength)
        ranging_prob = 1.0 - trend_strength

        # Direction probability based on DI crossover and price vs EMA
        if plus_di > minus_di and price_vs_ema > 0:
            uptrend_prob = trend_strength * (0.5 + 0.5 * min(price_vs_ema / 5, 1.0))
            downtrend_prob = trend_strength - uptrend_prob
        elif minus_di > plus_di and price_vs_ema < 0:
            downtrend_prob = trend_strength * (0.5 + 0.5 * min(abs(price_vs_ema) / 5, 1.0))
            uptrend_prob = trend_strength - downtrend_prob
        else:
            # Ambiguous - split probability
            uptrend_prob = trend_strength * 0.5
            downtrend_prob = trend_strength * 0.5

        # Normalize to sum to 1
        total = uptrend_prob + downtrend_prob + ranging_prob
        if total > 0:
            uptrend_prob /= total
            downtrend_prob /= total
            ranging_prob /= total

        return {
            TrendRegime.STRONG_UPTREND.value: round(uptrend_prob, 4),
            TrendRegime.RANGING.value: round(ranging_prob, 4),
            TrendRegime.STRONG_DOWNTREND.value: round(downtrend_prob, 4)
        }

    def _calculate_volatility_probabilities(
        self,
        indicators: IndicatorValues
    ) -> Dict[str, float]:
        """
        Calculate probability distribution over volatility regimes

        Uses fuzzy membership functions based on ATR percentile

        Args:
            indicators: IndicatorValues container

        Returns:
            Dict mapping volatility regime to probability
        """
        pct = indicators.atr_percentile

        # Fuzzy membership for low volatility (peaks at 0, zero at 40)
        low_vol = max(0, 1 - pct / 40)

        # Fuzzy membership for high volatility (zero at 60, peaks at 100)
        high_vol = max(0, (pct - 60) / 40)

        # Normal volatility fills the middle
        normal_vol = 1 - low_vol - high_vol

        # Ensure non-negative
        normal_vol = max(0, normal_vol)

        # Normalize
        total = low_vol + normal_vol + high_vol
        if total > 0:
            low_vol /= total
            normal_vol /= total
            high_vol /= total

        return {
            VolatilityRegime.LOW_VOLATILITY.value: round(low_vol, 4),
            VolatilityRegime.NORMAL_VOLATILITY.value: round(normal_vol, 4),
            VolatilityRegime.HIGH_VOLATILITY.value: round(high_vol, 4)
        }

    def _calculate_volume_probabilities(
        self,
        indicators: IndicatorValues
    ) -> Dict[str, float]:
        """
        Calculate probability distribution over volume regimes

        Uses fuzzy membership functions based on volume percentile

        Args:
            indicators: IndicatorValues container

        Returns:
            Dict mapping volume regime to probability
        """
        pct = indicators.volume_percentile

        # Fuzzy membership for low volume (peaks at 0, zero at 50)
        low_vol = max(0, 1 - pct / 50)

        # Fuzzy membership for high volume (zero at 50, peaks at 100)
        high_vol = max(0, (pct - 50) / 50)

        # Normal volume fills the middle
        normal_vol = 1 - low_vol - high_vol
        normal_vol = max(0, normal_vol)

        # Normalize
        total = low_vol + normal_vol + high_vol
        if total > 0:
            low_vol /= total
            normal_vol /= total
            high_vol /= total

        return {
            VolumeRegime.LOW_VOLUME.value: round(low_vol, 4),
            VolumeRegime.NORMAL_VOLUME.value: round(normal_vol, 4),
            VolumeRegime.HIGH_VOLUME.value: round(high_vol, 4)
        }

    # =============================================================================
    # Cache and Transition Matrix Methods
    # =============================================================================

    def _update_cache(self, symbol: str, regime: MarketRegime) -> None:
        """
        Update regime cache and transition matrix

        Args:
            symbol: Trading pair symbol
            regime: New MarketRegime
        """
        # Check for regime change
        previous_regime = self._regime_cache.get(symbol)

        # Update cache
        self._regime_cache[symbol] = regime

        # Update transition matrix if regime changed
        if previous_regime is not None and previous_regime.regime_label != regime.regime_label:
            self._update_transition_matrix(
                symbol,
                previous_regime.regime_label,
                regime.regime_label
            )

    def _update_transition_matrix(
        self,
        symbol: str,
        from_regime: str,
        to_regime: str
    ) -> None:
        """
        Update regime transition probability matrix

        Args:
            symbol: Trading pair symbol
            from_regime: Previous regime label
            to_regime: New regime label
        """
        # Get or create transition matrix
        if symbol not in self._transition_matrices:
            self._transition_matrices[symbol] = RegimeTransitionMatrix(
                symbol=symbol,
                matrix={},
                total_transitions=0
            )

        matrix = self._transition_matrices[symbol]

        # Update counts
        if from_regime not in matrix.matrix:
            matrix.matrix[from_regime] = {}

        if to_regime not in matrix.matrix[from_regime]:
            matrix.matrix[from_regime][to_regime] = 0

        matrix.matrix[from_regime][to_regime] += 1
        matrix.total_transitions += 1
        matrix.last_updated = datetime.utcnow()

        # Recalculate probabilities
        for from_state in matrix.matrix:
            total_from = sum(matrix.matrix[from_state].values())
            for to_state in matrix.matrix[from_state]:
                matrix.matrix[from_state][to_state] = (
                    matrix.matrix[from_state][to_state] / total_from
                )

        logger.debug(
            f"Updated transition matrix for {symbol}: "
            f"{from_regime} -> {to_regime}"
        )

    # =============================================================================
    # ML Integration Methods
    # =============================================================================

    def get_regime_features(
        self,
        prices: pd.DataFrame,
        symbol: str = "UNKNOWN"
    ) -> Dict[str, Any]:
        """
        Get regime features for ML model integration

        Returns one-hot encoded regime states and continuous features

        Args:
            prices: DataFrame with OHLCV data
            symbol: Trading pair symbol

        Returns:
            Dict with regime features for ML model
        """
        # Detect current regime
        regime = self.detect_regime(prices, symbol)

        # One-hot encode trend regime
        trend_onehot = {
            "trend_uptrend": 1 if regime.trend == TrendRegime.STRONG_UPTREND else 0,
            "trend_ranging": 1 if regime.trend == TrendRegime.RANGING else 0,
            "trend_downtrend": 1 if regime.trend == TrendRegime.STRONG_DOWNTREND else 0,
        }

        # One-hot encode volatility regime
        vol_onehot = {
            "vol_low": 1 if regime.volatility == VolatilityRegime.LOW_VOLATILITY else 0,
            "vol_normal": 1 if regime.volatility == VolatilityRegime.NORMAL_VOLATILITY else 0,
            "vol_high": 1 if regime.volatility == VolatilityRegime.HIGH_VOLATILITY else 0,
        }

        # One-hot encode volume regime
        volume_onehot = {
            "volume_low": 1 if regime.volume == VolumeRegime.LOW_VOLUME else 0,
            "volume_normal": 1 if regime.volume == VolumeRegime.NORMAL_VOLUME else 0,
            "volume_high": 1 if regime.volume == VolumeRegime.HIGH_VOLUME else 0,
        }

        # Continuous features
        continuous_features = {
            "adx": regime.indicators.get("adx", 20.0),
            "atr_percentile": regime.indicators.get("atr_percentile", 50.0),
            "volume_percentile": regime.indicators.get("volume_percentile", 50.0),
            "price_vs_ema_pct": regime.indicators.get("price_vs_ema_pct", 0.0),
            "regime_confidence": regime.confidence,
        }

        # Combine all features
        features = {
            **trend_onehot,
            **vol_onehot,
            **volume_onehot,
            **continuous_features,
            "regime_label": regime.regime_label,
        }

        return features

    def adjust_prediction_confidence(
        self,
        base_confidence: float,
        regime: MarketRegime
    ) -> float:
        """
        Adjust ML prediction confidence based on regime

        Confidence adjustments:
        - Trending + Normal/Low Vol: Increase confidence (predictable)
        - Ranging: Decrease confidence (unpredictable direction)
        - High Volatility: Decrease confidence (unpredictable magnitude)

        Args:
            base_confidence: Original prediction confidence
            regime: Current market regime

        Returns:
            Adjusted confidence score
        """
        adjustment = 1.0

        # Trend adjustments
        if regime.trend == TrendRegime.RANGING:
            # Ranging markets are less predictable
            adjustment *= 0.85
        elif regime.trend in [TrendRegime.STRONG_UPTREND, TrendRegime.STRONG_DOWNTREND]:
            # Strong trends are more predictable
            adjustment *= 1.10

        # Volatility adjustments
        if regime.volatility == VolatilityRegime.HIGH_VOLATILITY:
            # High volatility increases uncertainty
            adjustment *= 0.90
        elif regime.volatility == VolatilityRegime.LOW_VOLATILITY:
            # Low volatility is more predictable
            adjustment *= 1.05

        # Volume adjustments
        if regime.volume == VolumeRegime.LOW_VOLUME:
            # Low volume can have unpredictable moves
            adjustment *= 0.95

        # Apply adjustment and clamp
        adjusted = base_confidence * adjustment
        adjusted = max(0.0, min(1.0, adjusted))

        return round(adjusted, 4)


# =============================================================================
# Standalone Usage Example
# =============================================================================

if __name__ == "__main__":
    # Configure logging for demo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 80)
    print("MARKET REGIME DETECTOR - DEMO")
    print("=" * 80)

    # Create sample data
    np.random.seed(42)
    n_candles = 500

    # Generate synthetic trending data
    base_price = 50000
    trend = np.linspace(0, 5000, n_candles)  # Uptrend
    noise = np.random.normal(0, 200, n_candles)
    close_prices = base_price + trend + noise

    # Create DataFrame
    dates = pd.date_range(start='2024-01-01', periods=n_candles, freq='1h')
    df = pd.DataFrame({
        'timestamp': dates,
        'open': close_prices - np.random.uniform(0, 100, n_candles),
        'high': close_prices + np.random.uniform(0, 150, n_candles),
        'low': close_prices - np.random.uniform(0, 150, n_candles),
        'close': close_prices,
        'volume': np.random.uniform(1000, 5000, n_candles)
    })

    # Initialize detector
    detector = MarketRegimeDetector()

    # Detect regime
    regime = detector.detect_regime(df, symbol="BTCUSDT")

    print(f"\nDetected Regime for BTCUSDT:")
    print(f"  Trend:      {regime.trend}")
    print(f"  Volatility: {regime.volatility}")
    print(f"  Volume:     {regime.volume}")
    print(f"  Label:      {regime.regime_label}")
    print(f"  Confidence: {regime.confidence:.2%}")
    print(f"\nIndicators:")
    for key, value in regime.indicators.items():
        print(f"  {key}: {value}")

    # Get probabilities
    probs = detector.get_regime_probability(df, symbol="BTCUSDT")
    print(f"\nRegime Probabilities:")
    for key, value in probs.items():
        if isinstance(value, dict):
            print(f"  {key}:")
            for k, v in value.items():
                print(f"    {k}: {v:.2%}")
        else:
            print(f"  {key}: {value:.2%}")

    # Get ML features
    features = detector.get_regime_features(df, symbol="BTCUSDT")
    print(f"\nML Features:")
    for key, value in features.items():
        print(f"  {key}: {value}")

    print("=" * 80)
