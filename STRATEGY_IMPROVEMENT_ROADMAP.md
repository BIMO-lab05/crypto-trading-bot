# Trading Strategy Improvement Roadmap
# Crypto Trading Bot - Strategy Enhancement Plan
# Created: 2025-11-04
# Based on: Comprehensive research + Current strategy analysis

---

## Executive Summary

This roadmap outlines the systematic improvement of our trading bot from a basic 5-indicator consensus strategy to a sophisticated, adaptive trading system. The improvements are based on:

- **Academic Research**: 2024-2025 papers on algorithmic trading
- **Industry Best Practices**: Professional trading strategies
- **Current Bot Analysis**: 15+ identified weaknesses with solutions
- **Risk Management**: Enhanced safety and capital preservation

**Expected Outcomes**:
- 📈 Higher win rate through better signal quality
- 🛡️ Reduced drawdowns via dynamic risk management
- 🎯 Fewer false signals with trend filtering
- 💰 Better risk/reward ratios with partial profit taking
- 🔄 Adaptability to different market conditions

---

## Table of Contents

1. [Current Strategy Overview](#current-strategy-overview)
2. [Identified Weaknesses](#identified-weaknesses)
3. [Improvement Phases](#improvement-phases)
4. [Phase 1: Core Enhancements](#phase-1-core-enhancements)
5. [Phase 2: Advanced Features](#phase-2-advanced-features)
6. [Phase 3: System Optimization](#phase-3-system-optimization)
7. [Implementation Timeline](#implementation-timeline)
8. [Testing Strategy](#testing-strategy)
9. [Risk Assessment](#risk-assessment)
10. [Success Metrics](#success-metrics)

---

## Current Strategy Overview

### Existing Implementation
```
Strategy Type: Multi-Indicator Consensus
Indicators: 5 (RSI, MACD, Bollinger Bands, SMA, EMA)
Signal Logic: Requires 3+ indicators to agree
Confidence: Minimum 60% threshold
Risk Management: Fixed 2% position, 3% SL, 6% TP
Status: Paper trading only
```

### Current Signal Flow
```
Market Data → Indicators → Signal Aggregation → Risk Check → Position Sizing → Order
```

### Strengths
✅ Multiple confirmation system reduces false signals
✅ Confidence-based scoring provides signal quality metric
✅ Basic risk management prevents over-exposure
✅ Modular microservices architecture
✅ Comprehensive logging and monitoring

### Weaknesses (15 Total)
❌ No trend filtering - trades in choppy markets
❌ No volume confirmation - misses low-volume fakeouts
❌ Fixed stop-loss - doesn't adapt to volatility
❌ No market regime detection
❌ Uniform indicator weighting
❌ No partial profit taking
❌ No consecutive loss protection
❌ Static position sizing
❌ No correlation analysis
❌ Missing timeout filters
❌ No divergence detection
❌ Lack of momentum confirmation
❌ No automated trading loop
❌ Missing backtesting framework
❌ No trade history persistence

---

## Identified Weaknesses

### Critical (Fix First)
| # | Weakness | Impact | Solution | Priority |
|---|----------|--------|----------|----------|
| 1 | No trend filter | Trading against major trends causes losses | Add 50/200 EMA trend filter | 🔴 HIGH |
| 2 | No volume confirmation | False breakouts on low volume | Add volume indicator with 1.2x threshold | 🔴 HIGH |
| 3 | Fixed stop-loss | Over-tight in volatile markets, too loose in calm | ATR-based dynamic stops | 🔴 HIGH |
| 4 | No momentum confirmation | Enters trades with weak momentum | Add Stochastic Oscillator | 🔴 HIGH |

### Important (Fix Second)
| # | Weakness | Impact | Solution | Priority |
|---|----------|--------|----------|----------|
| 5 | No market regime detection | Same strategy in trending vs sideways | Implement regime classifier | 🟡 MEDIUM |
| 6 | No partial profit taking | All-or-nothing exits reduce profit | Scale out at multiple levels | 🟡 MEDIUM |
| 7 | No consecutive loss protection | Continues trading after losing streak | Add circuit breaker (3 losses) | 🟡 MEDIUM |
| 8 | Static position sizing | Doesn't adjust to volatility | ATR-based position sizing | 🟡 MEDIUM |

### Nice to Have (Fix Later)
| # | Weakness | Impact | Solution | Priority |
|---|----------|--------|----------|----------|
| 9 | No correlation analysis | May double-expose on correlated pairs | Add correlation matrix | 🟢 LOW |
| 10 | No timeout filters | Trades too frequently | Add minimum hold time (4 hours) | 🟢 LOW |
| 11 | No divergence detection | Misses RSI/price divergences | Add divergence scanner | 🟢 LOW |
| 12 | Uniform indicator weights | All indicators treated equally | Implement dynamic weighting | 🟢 LOW |

### Infrastructure Improvements
| # | Weakness | Impact | Solution | Priority |
|---|----------|--------|----------|----------|
| 13 | No automated loop | Manual execution required | Add trading scheduler | 🔴 HIGH |
| 14 | No backtesting | Can't validate strategies | Build backtesting engine | 🟡 MEDIUM |
| 15 | No trade persistence | Lost on restart | Database trade logging | 🟡 MEDIUM |

---

## Improvement Phases

### Phase 1: Core Enhancements (Week 1-2)
**Goal**: Fix critical weaknesses that cause direct losses
**Duration**: 10-12 hours implementation + 3-4 hours testing
**Risk Level**: Low (additive changes, no breaking modifications)

**Improvements**:
1. Trend Filter (50 EMA / 200 EMA)
2. Volume Confirmation Indicator
3. ATR-based Dynamic Stop-Loss/Take-Profit
4. Stochastic Oscillator (Momentum confirmation)
5. Update Signal Aggregation Logic

**Files to Modify**: 5 files, 1 new file
**Lines of Code**: ~800 new, ~150 modified
**Breaking Changes**: None

---

### Phase 2: Advanced Features (Week 3-4)
**Goal**: Improve win rate and reduce drawdowns
**Duration**: 12-15 hours implementation + 5-6 hours testing
**Risk Level**: Medium (changes core strategy logic)

**Improvements**:
1. Market Regime Detection (Trending/Sideways/Volatile)
2. Partial Profit Taking (Scale-out strategy)
3. Consecutive Loss Circuit Breaker
4. Dynamic Position Sizing (ATR-based)
5. Correlation Analysis (Multi-asset)
6. Minimum Hold Time Filter

**Files to Modify**: 7 files, 2 new files
**Lines of Code**: ~1200 new, ~250 modified
**Breaking Changes**: Signal aggregation algorithm

---

### Phase 3: System Optimization (Week 5-6)
**Goal**: Production readiness and automation
**Duration**: 15-20 hours implementation + 8-10 hours testing
**Risk Level**: Low (infrastructure improvements)

**Improvements**:
1. Automated Trading Loop (Scheduler)
2. Trade History Database Persistence
3. Backtesting Framework
4. Performance Analytics Dashboard
5. Enhanced Monitoring & Alerts
6. Indicator Divergence Detection

**Files to Modify**: 10 files, 5 new files
**Lines of Code**: ~2000 new, ~100 modified
**Breaking Changes**: Database schema additions

---

## Phase 1: Core Enhancements

### 1.1 Trend Filter Implementation

**Purpose**: Prevent counter-trend trades that have low success probability

**Technical Approach**:
- Calculate 50-period EMA (short-term trend)
- Calculate 200-period EMA (long-term trend)
- Only allow BUY signals when 50 EMA > 200 EMA (bullish trend)
- Only allow SELL signals when 50 EMA < 200 EMA (bearish trend)
- Add "NEUTRAL" zone when EMAs are within 0.5% of each other

**File**: `services/technical-analysis/app/indicators/trend_filter.py` (NEW)

```python
"""
Trend Filter Indicator
Uses 50 EMA and 200 EMA to determine market trend direction
Prevents counter-trend trading
"""

from typing import Dict, List, Optional
import pandas as pd
import numpy as np
from app.core.logger import logger

class TrendFilter:
    """
    Trend filter using dual EMA system

    Logic:
    - Bullish: 50 EMA > 200 EMA + spread > 0.5%
    - Bearish: 50 EMA < 200 EMA + spread > 0.5%
    - Neutral: EMAs within 0.5% (choppy market)
    """

    def __init__(
        self,
        fast_period: int = 50,
        slow_period: int = 200,
        neutral_threshold: float = 0.005  # 0.5% threshold
    ):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.neutral_threshold = neutral_threshold

    def calculate(self, prices: List[float]) -> Dict:
        """
        Calculate trend filter signal

        Args:
            prices: List of closing prices (oldest to newest)

        Returns:
            {
                'trend': 'BULLISH' | 'BEARISH' | 'NEUTRAL',
                'fast_ema': float,
                'slow_ema': float,
                'spread_pct': float,
                'confidence': float,  # 0.0 to 1.0
                'signal': 'BUY' | 'SELL' | 'HOLD',
                'timestamp': int
            }
        """

        if len(prices) < self.slow_period:
            logger.warning(f"Insufficient data for trend filter: {len(prices)} < {self.slow_period}")
            return self._neutral_response()

        try:
            # Convert to pandas Series for EMA calculation
            price_series = pd.Series(prices)

            # Calculate EMAs
            fast_ema = price_series.ewm(span=self.fast_period, adjust=False).mean().iloc[-1]
            slow_ema = price_series.ewm(span=self.slow_period, adjust=False).mean().iloc[-1]

            # Calculate spread percentage
            spread_pct = (fast_ema - slow_ema) / slow_ema

            # Determine trend
            if spread_pct > self.neutral_threshold:
                trend = "BULLISH"
                signal = "BUY"
                # Confidence based on spread magnitude (capped at 1.0)
                confidence = min(abs(spread_pct) / 0.05, 1.0)  # 5% spread = 100% confidence
            elif spread_pct < -self.neutral_threshold:
                trend = "BEARISH"
                signal = "SELL"
                confidence = min(abs(spread_pct) / 0.05, 1.0)
            else:
                trend = "NEUTRAL"
                signal = "HOLD"
                confidence = 0.3  # Low confidence in choppy markets

            return {
                "trend": trend,
                "fast_ema": float(fast_ema),
                "slow_ema": float(slow_ema),
                "spread_pct": float(spread_pct),
                "confidence": float(confidence),
                "signal": signal,
                "description": f"{trend} trend ({spread_pct*100:.2f}% spread)",
                "timestamp": pd.Timestamp.now().timestamp() * 1000
            }

        except Exception as e:
            logger.error(f"Error calculating trend filter: {e}")
            return self._neutral_response()

    def _neutral_response(self) -> Dict:
        """Return neutral response when calculation fails"""
        return {
            "trend": "NEUTRAL",
            "fast_ema": 0.0,
            "slow_ema": 0.0,
            "spread_pct": 0.0,
            "confidence": 0.0,
            "signal": "HOLD",
            "description": "Insufficient data or error",
            "timestamp": pd.Timestamp.now().timestamp() * 1000
        }
```

**File**: `services/technical-analysis/app/main.py` (MODIFY)

**Line 15**: Add import
```python
from app.indicators.trend_filter import TrendFilter
```

**Line 45**: Add endpoint (after existing indicator endpoints)
```python
@app.get("/api/v1/indicators/trend/{symbol}")
async def get_trend_filter(
    symbol: str,
    interval: str = "60",
    fast_period: int = 50,
    slow_period: int = 200
):
    """
    Get trend filter indicator

    Uses dual EMA system to identify market trend:
    - BULLISH: Trade only long positions
    - BEARISH: Trade only short positions
    - NEUTRAL: Avoid trading (choppy market)
    """
    try:
        # Fetch kline data
        klines = await market_data.get_klines(
            symbol=symbol,
            interval=interval,
            limit=max(slow_period + 50, 250)  # Extra data for EMA warmup
        )

        if not klines or len(klines) < slow_period:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data: need {slow_period} candles"
            )

        # Extract close prices
        close_prices = [float(k['close']) for k in klines]

        # Calculate trend filter
        trend_filter = TrendFilter(
            fast_period=fast_period,
            slow_period=slow_period
        )
        result = trend_filter.calculate(close_prices)

        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "data": result,
            "timestamp": int(time.time() * 1000)
        }

    except Exception as e:
        logger.error(f"Error calculating trend filter for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

---

### 1.2 Volume Confirmation Indicator

**Purpose**: Filter out low-volume false breakouts and confirm signal strength

**Technical Approach**:
- Calculate 20-period average volume
- Current volume must exceed 1.2x average for breakout signals
- Lower threshold (1.0x) for continuation signals
- Confidence score based on volume ratio

**File**: `services/technical-analysis/app/indicators/volume_confirmation.py` (NEW)

```python
"""
Volume Confirmation Indicator
Validates signals based on trading volume
Prevents false breakouts on low volume
"""

from typing import Dict, List
import pandas as pd
import numpy as np
from app.core.logger import logger

class VolumeConfirmation:
    """
    Volume-based signal confirmation

    Logic:
    - High volume (>1.5x avg): Strong confirmation
    - Medium volume (1.2-1.5x avg): Moderate confirmation
    - Normal volume (1.0-1.2x avg): Weak confirmation
    - Low volume (<1.0x avg): Rejection
    """

    def __init__(
        self,
        period: int = 20,
        breakout_threshold: float = 1.2,
        strong_threshold: float = 1.5
    ):
        self.period = period
        self.breakout_threshold = breakout_threshold
        self.strong_threshold = strong_threshold

    def calculate(
        self,
        volumes: List[float],
        signal_type: str = "breakout"  # "breakout" or "continuation"
    ) -> Dict:
        """
        Calculate volume confirmation

        Args:
            volumes: List of volume values (oldest to newest)
            signal_type: "breakout" requires higher volume, "continuation" is more lenient

        Returns:
            {
                'confirmed': bool,
                'current_volume': float,
                'avg_volume': float,
                'volume_ratio': float,
                'confidence': float,
                'strength': 'STRONG' | 'MODERATE' | 'WEAK' | 'INSUFFICIENT',
                'signal': 'CONFIRM' | 'REJECT',
                'timestamp': int
            }
        """

        if len(volumes) < self.period:
            logger.warning(f"Insufficient volume data: {len(volumes)} < {self.period}")
            return self._reject_response()

        try:
            # Current volume and average
            current_volume = volumes[-1]
            avg_volume = np.mean(volumes[-self.period:])

            # Volume ratio
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

            # Determine threshold based on signal type
            threshold = self.breakout_threshold if signal_type == "breakout" else 1.0

            # Classify volume strength
            if volume_ratio >= self.strong_threshold:
                strength = "STRONG"
                confidence = 1.0
                confirmed = True
            elif volume_ratio >= self.breakout_threshold:
                strength = "MODERATE"
                confidence = 0.7
                confirmed = True
            elif volume_ratio >= 1.0:
                strength = "WEAK"
                confidence = 0.4
                confirmed = (signal_type == "continuation")
            else:
                strength = "INSUFFICIENT"
                confidence = 0.1
                confirmed = False

            return {
                "confirmed": confirmed,
                "current_volume": float(current_volume),
                "avg_volume": float(avg_volume),
                "volume_ratio": float(volume_ratio),
                "confidence": float(confidence),
                "strength": strength,
                "signal": "CONFIRM" if confirmed else "REJECT",
                "description": f"{strength} volume ({volume_ratio:.2f}x average)",
                "timestamp": pd.Timestamp.now().timestamp() * 1000
            }

        except Exception as e:
            logger.error(f"Error calculating volume confirmation: {e}")
            return self._reject_response()

    def _reject_response(self) -> Dict:
        """Return rejection response when calculation fails"""
        return {
            "confirmed": False,
            "current_volume": 0.0,
            "avg_volume": 0.0,
            "volume_ratio": 0.0,
            "confidence": 0.0,
            "strength": "INSUFFICIENT",
            "signal": "REJECT",
            "description": "Insufficient data or error",
            "timestamp": pd.Timestamp.now().timestamp() * 1000
        }
```

**File**: `services/technical-analysis/app/main.py` (MODIFY)

**Line 16**: Add import
```python
from app.indicators.volume_confirmation import VolumeConfirmation
```

**Line 85**: Add endpoint
```python
@app.get("/api/v1/indicators/volume/{symbol}")
async def get_volume_confirmation(
    symbol: str,
    interval: str = "60",
    period: int = 20,
    signal_type: str = "breakout"
):
    """
    Get volume confirmation indicator

    Validates whether current volume supports the trading signal
    - breakout: Requires 1.2x average volume
    - continuation: Accepts 1.0x average volume
    """
    try:
        # Fetch kline data
        klines = await market_data.get_klines(
            symbol=symbol,
            interval=interval,
            limit=period + 10
        )

        if not klines or len(klines) < period:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data: need {period} candles"
            )

        # Extract volumes
        volumes = [float(k['volume']) for k in klines]

        # Calculate volume confirmation
        volume_conf = VolumeConfirmation(period=period)
        result = volume_conf.calculate(volumes, signal_type)

        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "signal_type": signal_type,
            "data": result,
            "timestamp": int(time.time() * 1000)
        }

    except Exception as e:
        logger.error(f"Error calculating volume confirmation for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

---

### 1.3 ATR-based Dynamic Stop-Loss/Take-Profit

**Purpose**: Adapt stop-loss and take-profit levels to current market volatility

**Technical Approach**:
- Calculate 14-period ATR (Average True Range)
- Stop-loss = Entry Price ± (2 × ATR)
- Take-profit = Entry Price ± (4 × ATR) for 1:2 risk/reward
- Tighter stops in low volatility, wider in high volatility

**File**: `services/technical-analysis/app/indicators/atr.py` (NEW)

```python
"""
ATR (Average True Range) Indicator
Measures market volatility for dynamic risk management
"""

from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
from app.core.logger import logger

class ATR:
    """
    Average True Range indicator

    Uses True Range calculation:
    TR = max(high - low, |high - prev_close|, |low - prev_close|)
    ATR = EMA(TR, period)

    Purpose: Dynamic stop-loss and position sizing based on volatility
    """

    def __init__(
        self,
        period: int = 14,
        stop_loss_multiplier: float = 2.0,
        take_profit_multiplier: float = 4.0
    ):
        self.period = period
        self.sl_multiplier = stop_loss_multiplier
        self.tp_multiplier = take_profit_multiplier

    def calculate(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        current_price: float
    ) -> Dict:
        """
        Calculate ATR and suggested stop-loss/take-profit levels

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of close prices
            current_price: Current/entry price for position

        Returns:
            {
                'atr': float,
                'atr_pct': float,  # ATR as percentage of price
                'stop_loss_long': float,  # SL for long position
                'stop_loss_short': float,  # SL for short position
                'take_profit_long': float,  # TP for long position
                'take_profit_short': float,  # TP for short position
                'volatility': 'LOW' | 'MEDIUM' | 'HIGH' | 'EXTREME',
                'confidence': float,
                'timestamp': int
            }
        """

        if len(highs) < self.period + 1 or len(lows) < self.period + 1 or len(closes) < self.period + 1:
            logger.warning(f"Insufficient data for ATR: need {self.period + 1} candles")
            return self._default_response(current_price)

        try:
            # Calculate True Range
            df = pd.DataFrame({
                'high': highs,
                'low': lows,
                'close': closes
            })

            # TR = max(high-low, |high-prev_close|, |low-prev_close|)
            df['prev_close'] = df['close'].shift(1)
            df['tr1'] = df['high'] - df['low']
            df['tr2'] = abs(df['high'] - df['prev_close'])
            df['tr3'] = abs(df['low'] - df['prev_close'])
            df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)

            # Calculate ATR as EMA of TR
            atr = df['tr'].ewm(span=self.period, adjust=False).mean().iloc[-1]
            atr_pct = (atr / current_price) * 100  # ATR as percentage

            # Classify volatility
            if atr_pct < 1.0:
                volatility = "LOW"
                confidence = 0.8
            elif atr_pct < 2.0:
                volatility = "MEDIUM"
                confidence = 1.0
            elif atr_pct < 4.0:
                volatility = "HIGH"
                confidence = 0.7
            else:
                volatility = "EXTREME"
                confidence = 0.4  # Less confidence in extreme volatility

            # Calculate stop-loss and take-profit levels
            stop_distance = atr * self.sl_multiplier
            tp_distance = atr * self.tp_multiplier

            return {
                "atr": float(atr),
                "atr_pct": float(atr_pct),
                "stop_loss_long": float(current_price - stop_distance),
                "stop_loss_short": float(current_price + stop_distance),
                "take_profit_long": float(current_price + tp_distance),
                "take_profit_short": float(current_price - tp_distance),
                "volatility": volatility,
                "confidence": float(confidence),
                "description": f"{volatility} volatility ({atr_pct:.2f}% ATR)",
                "risk_reward_ratio": float(self.tp_multiplier / self.sl_multiplier),
                "timestamp": pd.Timestamp.now().timestamp() * 1000
            }

        except Exception as e:
            logger.error(f"Error calculating ATR: {e}")
            return self._default_response(current_price)

    def _default_response(self, current_price: float) -> Dict:
        """Return default ATR response with 3% stop-loss fallback"""
        default_sl_pct = 0.03  # 3% stop-loss
        default_tp_pct = 0.06  # 6% take-profit

        return {
            "atr": 0.0,
            "atr_pct": 0.0,
            "stop_loss_long": float(current_price * (1 - default_sl_pct)),
            "stop_loss_short": float(current_price * (1 + default_sl_pct)),
            "take_profit_long": float(current_price * (1 + default_tp_pct)),
            "take_profit_short": float(current_price * (1 - default_tp_pct)),
            "volatility": "UNKNOWN",
            "confidence": 0.3,
            "description": "Insufficient data - using default 3% SL",
            "risk_reward_ratio": 2.0,
            "timestamp": pd.Timestamp.now().timestamp() * 1000
        }
```

**File**: `services/technical-analysis/app/main.py` (MODIFY)

**Line 17**: Add import
```python
from app.indicators.atr import ATR
```

**Line 135**: Add endpoint
```python
@app.get("/api/v1/indicators/atr/{symbol}")
async def get_atr(
    symbol: str,
    interval: str = "60",
    period: int = 14,
    current_price: Optional[float] = None
):
    """
    Get ATR (Average True Range) indicator with dynamic stop-loss/take-profit

    Returns volatility-based risk management levels:
    - Stop-loss: Entry ± (2 × ATR)
    - Take-profit: Entry ± (4 × ATR)
    - Volatility classification: LOW/MEDIUM/HIGH/EXTREME
    """
    try:
        # Fetch kline data
        klines = await market_data.get_klines(
            symbol=symbol,
            interval=interval,
            limit=period + 20
        )

        if not klines or len(klines) < period + 1:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data: need {period + 1} candles"
            )

        # Extract OHLC data
        highs = [float(k['high']) for k in klines]
        lows = [float(k['low']) for k in klines]
        closes = [float(k['close']) for k in klines]

        # Use last close as current price if not provided
        if current_price is None:
            current_price = closes[-1]

        # Calculate ATR
        atr_indicator = ATR(period=period)
        result = atr_indicator.calculate(highs, lows, closes, current_price)

        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "current_price": current_price,
            "data": result,
            "timestamp": int(time.time() * 1000)
        }

    except Exception as e:
        logger.error(f"Error calculating ATR for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

---

### 1.4 Stochastic Oscillator (Momentum Confirmation)

**Purpose**: Confirm momentum direction and identify overbought/oversold conditions

**Technical Approach**:
- Calculate %K (14,3,3): (Close - Lowest Low) / (Highest High - Lowest Low) × 100
- Calculate %D: 3-period SMA of %K
- Overbought: %K > 80
- Oversold: %K < 20
- Bullish: %K crosses above %D
- Bearish: %K crosses below %D

**File**: `services/technical-analysis/app/indicators/stochastic.py` (NEW)

```python
"""
Stochastic Oscillator Indicator
Momentum indicator comparing closing price to price range over time
"""

from typing import Dict, List
import pandas as pd
import numpy as np
from app.core.logger import logger

class Stochastic:
    """
    Stochastic Oscillator (%K, %D)

    Formula:
    %K = 100 × (Close - Lowest Low) / (Highest High - Lowest Low)
    %D = SMA(%K, smooth_period)

    Signals:
    - Overbought: %K > 80 (potential reversal down)
    - Oversold: %K < 20 (potential reversal up)
    - Bullish: %K crosses above %D
    - Bearish: %K crosses below %D
    """

    def __init__(
        self,
        period: int = 14,
        smooth_k: int = 3,
        smooth_d: int = 3,
        overbought: int = 80,
        oversold: int = 20
    ):
        self.period = period
        self.smooth_k = smooth_k
        self.smooth_d = smooth_d
        self.overbought = overbought
        self.oversold = oversold

    def calculate(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float]
    ) -> Dict:
        """
        Calculate Stochastic Oscillator

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of close prices

        Returns:
            {
                'k': float,  # %K value (0-100)
                'd': float,  # %D value (0-100)
                'signal': 'BUY' | 'SELL' | 'HOLD',
                'condition': 'OVERBOUGHT' | 'OVERSOLD' | 'NEUTRAL',
                'confidence': float,
                'crossover': 'BULLISH' | 'BEARISH' | 'NONE',
                'description': str,
                'timestamp': int
            }
        """

        if len(highs) < self.period + self.smooth_k or len(lows) < self.period + self.smooth_k or len(closes) < self.period + self.smooth_k:
            logger.warning(f"Insufficient data for Stochastic: need {self.period + self.smooth_k} candles")
            return self._neutral_response()

        try:
            df = pd.DataFrame({
                'high': highs,
                'low': lows,
                'close': closes
            })

            # Calculate %K
            # Lowest low and highest high over period
            df['lowest_low'] = df['low'].rolling(window=self.period).min()
            df['highest_high'] = df['high'].rolling(window=self.period).max()

            # Raw %K
            df['k_raw'] = 100 * (df['close'] - df['lowest_low']) / (df['highest_high'] - df['lowest_low'])

            # Smooth %K
            df['k'] = df['k_raw'].rolling(window=self.smooth_k).mean()

            # %D = SMA of %K
            df['d'] = df['k'].rolling(window=self.smooth_d).mean()

            # Get current and previous values
            k_current = df['k'].iloc[-1]
            d_current = df['d'].iloc[-1]
            k_prev = df['k'].iloc[-2] if len(df) > 1 else k_current
            d_prev = df['d'].iloc[-2] if len(df) > 1 else d_current

            # Determine condition
            if k_current > self.overbought:
                condition = "OVERBOUGHT"
            elif k_current < self.oversold:
                condition = "OVERSOLD"
            else:
                condition = "NEUTRAL"

            # Detect crossover
            bullish_cross = k_prev <= d_prev and k_current > d_current
            bearish_cross = k_prev >= d_prev and k_current < d_current

            if bullish_cross:
                crossover = "BULLISH"
            elif bearish_cross:
                crossover = "BEARISH"
            else:
                crossover = "NONE"

            # Generate signal
            if condition == "OVERSOLD" and (crossover == "BULLISH" or k_current > d_current):
                signal = "BUY"
                confidence = 0.9  # High confidence in oversold + bullish
            elif condition == "OVERBOUGHT" and (crossover == "BEARISH" or k_current < d_current):
                signal = "SELL"
                confidence = 0.9
            elif crossover == "BULLISH":
                signal = "BUY"
                confidence = 0.6  # Moderate confidence on crossover only
            elif crossover == "BEARISH":
                signal = "SELL"
                confidence = 0.6
            else:
                signal = "HOLD"
                confidence = 0.3

            # Description
            description = f"{condition}"
            if crossover != "NONE":
                description += f", {crossover} crossover"
            description += f" (K={k_current:.1f}, D={d_current:.1f})"

            return {
                "k": float(k_current),
                "d": float(d_current),
                "signal": signal,
                "condition": condition,
                "confidence": float(confidence),
                "crossover": crossover,
                "description": description,
                "timestamp": pd.Timestamp.now().timestamp() * 1000
            }

        except Exception as e:
            logger.error(f"Error calculating Stochastic: {e}")
            return self._neutral_response()

    def _neutral_response(self) -> Dict:
        """Return neutral response when calculation fails"""
        return {
            "k": 50.0,
            "d": 50.0,
            "signal": "HOLD",
            "condition": "NEUTRAL",
            "confidence": 0.0,
            "crossover": "NONE",
            "description": "Insufficient data or error",
            "timestamp": pd.Timestamp.now().timestamp() * 1000
        }
```

**File**: `services/technical-analysis/app/main.py` (MODIFY)

**Line 18**: Add import
```python
from app.indicators.stochastic import Stochastic
```

**Line 190**: Add endpoint
```python
@app.get("/api/v1/indicators/stochastic/{symbol}")
async def get_stochastic(
    symbol: str,
    interval: str = "60",
    period: int = 14,
    smooth_k: int = 3,
    smooth_d: int = 3
):
    """
    Get Stochastic Oscillator indicator

    Momentum indicator showing:
    - Overbought/Oversold conditions
    - Bullish/Bearish crossovers
    - Momentum strength
    """
    try:
        # Fetch kline data
        klines = await market_data.get_klines(
            symbol=symbol,
            interval=interval,
            limit=period + smooth_k + smooth_d + 10
        )

        if not klines or len(klines) < period + smooth_k:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data: need {period + smooth_k} candles"
            )

        # Extract OHLC data
        highs = [float(k['high']) for k in klines]
        lows = [float(k['low']) for k in klines]
        closes = [float(k['close']) for k in klines]

        # Calculate Stochastic
        stoch = Stochastic(
            period=period,
            smooth_k=smooth_k,
            smooth_d=smooth_d
        )
        result = stoch.calculate(highs, lows, closes)

        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "data": result,
            "timestamp": int(time.time() * 1000)
        }

    except Exception as e:
        logger.error(f"Error calculating Stochastic for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

---

### 1.5 Update Signal Aggregation Logic

**Purpose**: Integrate new indicators into the existing signal aggregation system

**Changes Required**:
1. Add trend filter as a GATEKEEPER (blocks counter-trend signals)
2. Add volume confirmation as a VALIDATOR (confirms breakouts)
3. Use ATR for dynamic stop-loss/take-profit calculation
4. Add Stochastic as 6th indicator in consensus

**File**: `services/trading-engine/app/signal_aggregator.py` (MODIFY)

**Current Structure** (Lines 1-50):
```python
"""
Signal Aggregator
Combines signals from multiple indicators
"""

class SignalAggregator:
    def __init__(self):
        self.indicators = ['rsi', 'macd', 'bollinger', 'sma', 'ema']
        self.min_consensus = 3
        self.min_confidence = 0.6
```

**New Structure** (Lines 1-120, updated):
```python
"""
Signal Aggregator - Enhanced with Trend Filter and Volume Confirmation
Combines signals from multiple indicators with gatekeeper logic
"""

from typing import Dict, List, Optional
from app.core.logger import logger
import statistics

class SignalAggregator:
    """
    Enhanced signal aggregation with:
    1. Trend Filter Gatekeeper (blocks counter-trend trades)
    2. Volume Confirmation Validator (confirms breakouts)
    3. 6 indicators: RSI, MACD, Bollinger, SMA, EMA, Stochastic
    4. Dynamic stop-loss/take-profit via ATR
    """

    def __init__(self):
        # Core indicators (require consensus)
        self.core_indicators = ['rsi', 'macd', 'bollinger', 'sma', 'ema', 'stochastic']

        # Gatekeeper indicators (can block trades)
        self.gatekeepers = ['trend_filter']

        # Validators (confirm signal quality)
        self.validators = ['volume_confirmation']

        # Configuration
        self.min_consensus = 4  # Changed from 3 to 4 (out of 6 indicators)
        self.min_confidence = 0.6

        # Indicator weights (sum = 1.0)
        self.weights = {
            'trend_filter': 0.25,    # Highest weight - trend is king
            'rsi': 0.15,
            'macd': 0.15,
            'bollinger': 0.10,
            'sma': 0.10,
            'ema': 0.10,
            'stochastic': 0.10,
            'volume_confirmation': 0.05  # Confirmation only
        }

    def aggregate_signals(
        self,
        indicator_signals: Dict,
        signal_type: str = "entry"  # "entry" or "exit"
    ) -> Dict:
        """
        Aggregate signals from all indicators

        Args:
            indicator_signals: {
                'rsi': {'signal': 'BUY', 'confidence': 0.8, ...},
                'macd': {'signal': 'SELL', 'confidence': 0.6, ...},
                'trend_filter': {'trend': 'BULLISH', 'signal': 'BUY', ...},
                'volume_confirmation': {'confirmed': True, 'confidence': 0.7, ...},
                'atr': {'atr': 500, 'stop_loss_long': 95000, ...},
                ...
            }
            signal_type: Type of signal being generated

        Returns:
            {
                'signal': 'BUY' | 'SELL' | 'HOLD',
                'confidence': float,
                'score': float,  # -1.0 to 1.0
                'consensus_count': int,
                'total_indicators': int,
                'trend_allowed': bool,
                'volume_confirmed': bool,
                'stop_loss': float,
                'take_profit': float,
                'indicators_detail': {...},
                'reason': str
            }
        """

        # Step 1: Check trend filter (GATEKEEPER)
        trend_filter = indicator_signals.get('trend_filter', {})
        trend = trend_filter.get('trend', 'NEUTRAL')

        # Step 2: Check volume confirmation (VALIDATOR)
        volume_conf = indicator_signals.get('volume_confirmation', {})
        volume_confirmed = volume_conf.get('confirmed', False)

        # Step 3: Get ATR levels for stop-loss/take-profit
        atr_data = indicator_signals.get('atr', {})

        # Step 4: Aggregate core indicator signals
        buy_signals = []
        sell_signals = []
        confidences = []
        weighted_score = 0.0

        for indicator in self.core_indicators:
            if indicator not in indicator_signals:
                continue

            signal_data = indicator_signals[indicator]
            signal = signal_data.get('signal', 'HOLD')
            confidence = signal_data.get('confidence', 0.0)
            weight = self.weights.get(indicator, 0.1)

            if signal == 'BUY':
                buy_signals.append(indicator)
                weighted_score += weight * confidence
                confidences.append(confidence)
            elif signal == 'SELL':
                sell_signals.append(indicator)
                weighted_score -= weight * confidence
                confidences.append(confidence)

        # Step 5: Count consensus
        consensus_buy = len(buy_signals)
        consensus_sell = len(sell_signals)
        total_signals = len(self.core_indicators)

        # Step 6: Determine preliminary signal
        if consensus_buy >= self.min_consensus:
            preliminary_signal = "BUY"
        elif consensus_sell >= self.min_consensus:
            preliminary_signal = "SELL"
        else:
            preliminary_signal = "HOLD"

        # Step 7: Apply GATEKEEPER logic (trend filter)
        trend_allowed = True
        if preliminary_signal == "BUY" and trend != "BULLISH":
            trend_allowed = False
            preliminary_signal = "HOLD"
            reason = f"BUY blocked: Trend is {trend}, not BULLISH"
        elif preliminary_signal == "SELL" and trend != "BEARISH":
            trend_allowed = False
            preliminary_signal = "HOLD"
            reason = f"SELL blocked: Trend is {trend}, not BEARISH"
        else:
            reason = f"{preliminary_signal}: {consensus_buy} BUY, {consensus_sell} SELL signals"

        # Step 8: Apply VALIDATOR logic (volume confirmation)
        # For entry signals on breakouts, require volume confirmation
        if signal_type == "entry" and preliminary_signal != "HOLD" and not volume_confirmed:
            logger.warning(f"Signal {preliminary_signal} not confirmed by volume")
            # Reduce confidence but don't block (volume is validator, not gatekeeper)
            avg_confidence = statistics.mean(confidences) if confidences else 0.5
            avg_confidence *= 0.7  # Reduce by 30%
        else:
            avg_confidence = statistics.mean(confidences) if confidences else 0.5

        # Step 9: Final confidence check
        if avg_confidence < self.min_confidence:
            preliminary_signal = "HOLD"
            reason = f"Confidence too low: {avg_confidence:.2f} < {self.min_confidence}"

        # Step 10: Get stop-loss and take-profit from ATR
        if preliminary_signal == "BUY":
            stop_loss = atr_data.get('stop_loss_long', 0)
            take_profit = atr_data.get('take_profit_long', 0)
        elif preliminary_signal == "SELL":
            stop_loss = atr_data.get('stop_loss_short', 0)
            take_profit = atr_data.get('take_profit_short', 0)
        else:
            stop_loss = 0
            take_profit = 0

        return {
            "signal": preliminary_signal,
            "confidence": float(avg_confidence),
            "score": float(weighted_score),
            "consensus_count": max(consensus_buy, consensus_sell),
            "total_indicators": total_signals,
            "trend_allowed": trend_allowed,
            "volume_confirmed": volume_confirmed,
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
            "atr": float(atr_data.get('atr', 0)),
            "atr_pct": float(atr_data.get('atr_pct', 0)),
            "indicators_detail": {
                "buy_signals": buy_signals,
                "sell_signals": sell_signals,
                "trend": trend,
                "volume_strength": volume_conf.get('strength', 'UNKNOWN')
            },
            "reason": reason,
            "timestamp": indicator_signals.get('timestamp', 0)
        }
```

**File**: `services/trading-engine/app/main.py` (MODIFY)

**Line 180**: Update `/api/v1/signals/{symbol}` endpoint to call new indicators

```python
@app.get("/api/v1/signals/{symbol}")
async def get_trading_signal(symbol: str, interval: str = "60"):
    """
    Get aggregated trading signal with enhanced indicators

    New in Phase 1:
    - Trend filter (50/200 EMA)
    - Volume confirmation
    - ATR-based stop-loss/take-profit
    - Stochastic oscillator
    """
    try:
        # Fetch all indicators in parallel
        import asyncio

        # Existing indicators
        rsi_task = technical_analysis.get_rsi(symbol, interval)
        macd_task = technical_analysis.get_macd(symbol, interval)
        bb_task = technical_analysis.get_bollinger(symbol, interval)

        # New Phase 1 indicators
        trend_task = technical_analysis.get_trend_filter(symbol, interval)
        volume_task = technical_analysis.get_volume_confirmation(symbol, interval, signal_type="breakout")
        atr_task = technical_analysis.get_atr(symbol, interval)
        stoch_task = technical_analysis.get_stochastic(symbol, interval)

        # Gather all results
        results = await asyncio.gather(
            rsi_task, macd_task, bb_task,
            trend_task, volume_task, atr_task, stoch_task,
            return_exceptions=True
        )

        # Extract indicator data
        indicator_signals = {
            'rsi': results[0].get('data', {}) if not isinstance(results[0], Exception) else {},
            'macd': results[1].get('data', {}) if not isinstance(results[1], Exception) else {},
            'bollinger': results[2].get('data', {}) if not isinstance(results[2], Exception) else {},
            'trend_filter': results[3].get('data', {}) if not isinstance(results[3], Exception) else {},
            'volume_confirmation': results[4].get('data', {}) if not isinstance(results[4], Exception) else {},
            'atr': results[5].get('data', {}) if not isinstance(results[5], Exception) else {},
            'stochastic': results[6].get('data', {}) if not isinstance(results[6], Exception) else {},
        }

        # Aggregate signals
        aggregator = SignalAggregator()
        aggregated = aggregator.aggregate_signals(indicator_signals, signal_type="entry")

        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "signal": aggregated,
            "timestamp": int(time.time() * 1000)
        }

    except Exception as e:
        logger.error(f"Error generating signal for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

---

### Phase 1 Summary

**Total Changes**:
- **New Files**: 4 (trend_filter.py, volume_confirmation.py, atr.py, stochastic.py)
- **Modified Files**: 3 (technical-analysis/main.py, trading-engine/signal_aggregator.py, trading-engine/main.py)
- **New API Endpoints**: 4 (/api/v1/indicators/trend, /volume, /atr, /stochastic)
- **Lines of Code**: ~800 new, ~150 modified

**Testing Checklist**:
- [ ] Trend filter correctly identifies bullish/bearish/neutral trends
- [ ] Volume confirmation filters low-volume signals
- [ ] ATR calculates dynamic stop-loss/take-profit based on volatility
- [ ] Stochastic detects overbought/oversold + crossovers
- [ ] Signal aggregation blocks counter-trend trades
- [ ] Signal aggregation requires volume confirmation for breakouts
- [ ] All new endpoints return valid JSON
- [ ] Integration test: Full signal generation with all 7 indicators

**Expected Improvements**:
- 🎯 **Win Rate**: +10-15% (trend filter reduces losing trades)
- 📉 **Drawdown**: -20-30% (dynamic stops adapt to volatility)
- 💰 **Risk/Reward**: Maintained at 1:2 minimum
- 🚫 **False Signals**: -40-50% (volume + trend filtering)

---

## Phase 2: Advanced Features

*(This section continues with Phase 2 implementations including Market Regime Detection, Partial Profit Taking, Circuit Breaker, Dynamic Position Sizing, Correlation Analysis, and Minimum Hold Time)*

### 2.1 Market Regime Detection

**Purpose**: Adapt strategy to current market conditions (trending, sideways, volatile)

**Technical Approach**:
- ADX (Average Directional Index) for trend strength
- Bollinger Band width for volatility
- Price action analysis for regime classification
- Strategy adjustments per regime

**File**: `services/technical-analysis/app/indicators/market_regime.py` (NEW)

```python
"""
Market Regime Detection
Classifies market into: TRENDING_BULL, TRENDING_BEAR, SIDEWAYS, VOLATILE
"""

from typing import Dict, List
import pandas as pd
import numpy as np
from app.core.logger import logger

class MarketRegimeDetector:
    """
    Detects current market regime using:
    1. ADX for trend strength
    2. Bollinger Band width for volatility
    3. EMA slope for direction

    Regimes:
    - TRENDING_BULL: Strong uptrend (ADX > 25, price > EMA, EMA rising)
    - TRENDING_BEAR: Strong downtrend (ADX > 25, price < EMA, EMA falling)
    - SIDEWAYS: Low trend strength (ADX < 20, narrow BB)
    - VOLATILE: High volatility choppy (ADX < 20, wide BB)
    """

    def __init__(
        self,
        adx_period: int = 14,
        adx_trending_threshold: float = 25.0,
        adx_weak_threshold: float = 20.0,
        bb_period: int = 20,
        bb_std: float = 2.0,
        volatility_threshold: float = 0.04  # 4% BB width = volatile
    ):
        self.adx_period = adx_period
        self.adx_trending = adx_trending_threshold
        self.adx_weak = adx_weak_threshold
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.volatility_threshold = volatility_threshold

    def calculate_adx(self, highs: List[float], lows: List[float], closes: List[float]) -> float:
        """Calculate ADX (Average Directional Index)"""
        df = pd.DataFrame({'high': highs, 'low': lows, 'close': closes})

        # Calculate True Range
        df['prev_close'] = df['close'].shift(1)
        df['tr'] = df[['high', 'low', 'prev_close']].apply(
            lambda x: max(x['high'] - x['low'],
                         abs(x['high'] - x['prev_close']),
                         abs(x['low'] - x['prev_close'])),
            axis=1
        )

        # Calculate directional movement
        df['up_move'] = df['high'] - df['high'].shift(1)
        df['down_move'] = df['low'].shift(1) - df['low']

        df['plus_dm'] = df.apply(
            lambda x: x['up_move'] if x['up_move'] > x['down_move'] and x['up_move'] > 0 else 0,
            axis=1
        )
        df['minus_dm'] = df.apply(
            lambda x: x['down_move'] if x['down_move'] > x['up_move'] and x['down_move'] > 0 else 0,
            axis=1
        )

        # Smooth with EMA
        atr = df['tr'].ewm(span=self.adx_period, adjust=False).mean()
        plus_di = 100 * (df['plus_dm'].ewm(span=self.adx_period, adjust=False).mean() / atr)
        minus_di = 100 * (df['minus_dm'].ewm(span=self.adx_period, adjust=False).mean() / atr)

        # Calculate ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.ewm(span=self.adx_period, adjust=False).mean().iloc[-1]

        return float(adx)

    def calculate_bb_width(self, closes: List[float]) -> float:
        """Calculate Bollinger Band width as percentage"""
        closes_series = pd.Series(closes)
        sma = closes_series.rolling(window=self.bb_period).mean().iloc[-1]
        std = closes_series.rolling(window=self.bb_period).std().iloc[-1]

        upper_band = sma + (self.bb_std * std)
        lower_band = sma - (self.bb_std * std)

        bb_width_pct = (upper_band - lower_band) / sma
        return float(bb_width_pct)

    def detect_regime(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float]
    ) -> Dict:
        """
        Detect current market regime

        Returns:
            {
                'regime': 'TRENDING_BULL' | 'TRENDING_BEAR' | 'SIDEWAYS' | 'VOLATILE',
                'adx': float,
                'bb_width_pct': float,
                'trend_strength': 'STRONG' | 'MODERATE' | 'WEAK',
                'volatility': 'HIGH' | 'NORMAL' | 'LOW',
                'confidence': float,
                'strategy_recommendation': str,
                'timestamp': int
            }
        """

        try:
            # Calculate ADX
            adx = self.calculate_adx(highs, lows, closes)

            # Calculate BB width
            bb_width_pct = self.calculate_bb_width(closes)

            # Calculate EMA slope for direction
            closes_series = pd.Series(closes)
            ema_50 = closes_series.ewm(span=50, adjust=False).mean()
            ema_slope = (ema_50.iloc[-1] - ema_50.iloc[-10]) / ema_50.iloc[-10]  # 10-candle slope

            # Classify trend strength
            if adx >= self.adx_trending:
                trend_strength = "STRONG"
            elif adx >= self.adx_weak:
                trend_strength = "MODERATE"
            else:
                trend_strength = "WEAK"

            # Classify volatility
            if bb_width_pct >= self.volatility_threshold:
                volatility = "HIGH"
            elif bb_width_pct >= self.volatility_threshold * 0.5:
                volatility = "NORMAL"
            else:
                volatility = "LOW"

            # Determine regime
            current_price = closes[-1]
            ema_current = ema_50.iloc[-1]

            if adx >= self.adx_trending:
                if ema_slope > 0 and current_price > ema_current:
                    regime = "TRENDING_BULL"
                    strategy = "Use trend-following: ride the trend with trailing stops"
                    confidence = min(adx / 50.0, 1.0)
                else:
                    regime = "TRENDING_BEAR"
                    strategy = "Use trend-following: short positions or stay out"
                    confidence = min(adx / 50.0, 1.0)
            elif bb_width_pct >= self.volatility_threshold:
                regime = "VOLATILE"
                strategy = "Reduce position size, widen stops, avoid new entries"
                confidence = 0.6
            else:
                regime = "SIDEWAYS"
                strategy = "Use mean-reversion: buy support, sell resistance"
                confidence = 0.7

            return {
                "regime": regime,
                "adx": float(adx),
                "bb_width_pct": float(bb_width_pct * 100),  # Convert to percentage
                "trend_strength": trend_strength,
                "volatility": volatility,
                "confidence": float(confidence),
                "strategy_recommendation": strategy,
                "ema_slope": float(ema_slope),
                "timestamp": pd.Timestamp.now().timestamp() * 1000
            }

        except Exception as e:
            logger.error(f"Error detecting market regime: {e}")
            return {
                "regime": "UNKNOWN",
                "adx": 0.0,
                "bb_width_pct": 0.0,
                "trend_strength": "WEAK",
                "volatility": "NORMAL",
                "confidence": 0.0,
                "strategy_recommendation": "Insufficient data",
                "ema_slope": 0.0,
                "timestamp": pd.Timestamp.now().timestamp() * 1000
            }
```

**API Endpoint**: Add to `services/technical-analysis/app/main.py`

```python
@app.get("/api/v1/indicators/regime/{symbol}")
async def get_market_regime(symbol: str, interval: str = "60"):
    """Detect current market regime for strategy adaptation"""
    # Implementation similar to previous endpoints
```

---

### 2.2 Partial Profit Taking (Scale-Out Strategy)

**Purpose**: Lock in profits incrementally instead of all-or-nothing exits

**Strategy**:
- Exit 50% at first take-profit level (1.5 × ATR)
- Exit 25% at second level (3 × ATR)
- Exit final 25% at third level (4 × ATR) or trailing stop
- Move stop-loss to breakeven after first TP hit

**File**: `services/trading-engine/app/exit_manager.py` (NEW)

```python
"""
Exit Manager - Partial Profit Taking
Implements scale-out strategy for better risk/reward
"""

from typing import Dict, List, Optional
from app.core.logger import logger

class ExitManager:
    """
    Manages position exits with partial profit taking

    Scale-out levels:
    - Level 1 (50%): Entry + (1.5 × ATR)
    - Level 2 (25%): Entry + (3.0 × ATR)
    - Level 3 (25%): Entry + (4.0 × ATR) or trailing stop

    After Level 1 hit: Move stop-loss to breakeven
    After Level 2 hit: Move stop-loss to Level 1
    """

    def __init__(self):
        self.scale_out_levels = [
            {"percentage": 0.50, "atr_multiplier": 1.5, "name": "First Target"},
            {"percentage": 0.25, "atr_multiplier": 3.0, "name": "Second Target"},
            {"percentage": 0.25, "atr_multiplier": 4.0, "name": "Final Target"}
        ]

    def calculate_targets(
        self,
        entry_price: float,
        atr: float,
        direction: str  # "LONG" or "SHORT"
    ) -> Dict:
        """
        Calculate scaled exit targets

        Returns:
            {
                'targets': [
                    {'level': 1, 'price': float, 'percentage': 0.5, 'distance_atr': 1.5},
                    {'level': 2, 'price': float, 'percentage': 0.25, 'distance_atr': 3.0},
                    {'level': 3, 'price': float, 'percentage': 0.25, 'distance_atr': 4.0}
                ],
                'stop_loss_levels': {
                    'initial': float,
                    'breakeven': float,
                    'level_1': float
                }
            }
        """

        targets = []
        multiplier = 1 if direction == "LONG" else -1

        for idx, level in enumerate(self.scale_out_levels, 1):
            target_price = entry_price + (multiplier * atr * level["atr_multiplier"])
            targets.append({
                "level": idx,
                "name": level["name"],
                "price": float(target_price),
                "percentage": level["percentage"],
                "distance_atr": level["atr_multiplier"]
            })

        # Stop-loss levels
        initial_sl = entry_price - (multiplier * atr * 2.0)  # 2 × ATR initial stop

        return {
            "targets": targets,
            "stop_loss_levels": {
                "initial": float(initial_sl),
                "breakeven": float(entry_price),
                "level_1": float(targets[0]["price"])
            },
            "direction": direction,
            "atr": float(atr)
        }
```

---

### 2.3 Consecutive Loss Circuit Breaker

**Purpose**: Stop trading after consecutive losses to prevent emotional trading

**Implementation**: Add to `services/trading-engine/app/risk_manager.py`

```python
class CircuitBreaker:
    """
    Halt trading after consecutive losses

    Rules:
    - After 3 consecutive losses: Pause for 4 hours
    - After 5 consecutive losses: Pause for 24 hours
    - After daily loss limit hit: Pause until next day
    """

    def __init__(self):
        self.consecutive_losses = 0
        self.last_trade_time = 0
        self.pause_until = 0

    def check_status(self) -> Dict:
        """Check if trading is allowed"""
        current_time = time.time() * 1000

        if current_time < self.pause_until:
            return {
                "trading_allowed": False,
                "reason": f"Circuit breaker active until {self.pause_until}",
                "consecutive_losses": self.consecutive_losses
            }

        return {
            "trading_allowed": True,
            "consecutive_losses": self.consecutive_losses
        }

    def record_trade(self, profit_loss: float):
        """Record trade result and update circuit breaker"""
        if profit_loss < 0:
            self.consecutive_losses += 1

            # Apply pause based on consecutive losses
            if self.consecutive_losses >= 5:
                self.pause_until = time.time() * 1000 + (24 * 60 * 60 * 1000)  # 24 hours
            elif self.consecutive_losses >= 3:
                self.pause_until = time.time() * 1000 + (4 * 60 * 60 * 1000)  # 4 hours
        else:
            self.consecutive_losses = 0  # Reset on winning trade
```

---

### 2.4 Dynamic Position Sizing

**Purpose**: Adjust position size based on market volatility (ATR)

**Formula**:
```
Position Size = (Account Risk Amount) / (ATR × ATR Multiplier)
```

**Implementation**: Update `services/trading-engine/app/risk_manager.py`

```python
def calculate_position_size_dynamic(
    self,
    account_balance: float,
    atr: float,
    atr_multiplier: float = 2.0,
    max_risk_pct: float = 0.02
) -> float:
    """
    Calculate position size based on ATR volatility

    Lower ATR = Larger position (calm market)
    Higher ATR = Smaller position (volatile market)
    """

    risk_amount = account_balance * max_risk_pct
    stop_distance = atr * atr_multiplier

    # Position size = Risk Amount / Stop Distance
    position_size = risk_amount / stop_distance

    return position_size
```

---

### Phase 2 Summary

**Total Changes**:
- **New Files**: 2 (market_regime.py, exit_manager.py)
- **Modified Files**: 3 (technical-analysis/main.py, risk_manager.py, signal_aggregator.py)
- **New Features**: 6 (regime detection, partial TP, circuit breaker, dynamic sizing, correlation, min hold time)
- **Lines of Code**: ~1200 new, ~250 modified

**Expected Improvements**:
- 📈 **Win Rate**: Additional +5-10% (regime-appropriate strategies)
- 💰 **Average Win Size**: +30-40% (partial TP locks profits)
- 🛡️ **Max Consecutive Losses**: Capped at 3-5 (circuit breaker)
- 📊 **Position Sizing**: Optimized to volatility (ATR-based)

---

## Phase 3: System Optimization

### 3.1 Automated Trading Loop

**Purpose**: Continuous automated trading without manual intervention

**File**: `services/trading-engine/app/trading_scheduler.py` (NEW)

```python
"""
Trading Scheduler - Automated Trading Loop
Runs strategy checks at regular intervals
"""

import asyncio
import time
from app.core.logger import logger
from app.main import get_trading_signal, analyze_and_trade

class TradingScheduler:
    """
    Automated trading scheduler

    - Checks signals every 5 minutes
    - Executes trades based on strategy
    - Monitors open positions
    - Handles emergency stops
    """

    def __init__(
        self,
        symbols: List[str],
        interval: str = "60",
        check_frequency: int = 300  # 5 minutes in seconds
    ):
        self.symbols = symbols
        self.interval = interval
        self.check_frequency = check_frequency
        self.running = False

    async def run(self):
        """Main trading loop"""
        self.running = True

        logger.info(f"🤖 Trading scheduler started for {len(self.symbols)} symbols")

        while self.running:
            try:
                # Check for emergency stop
                if self.check_emergency_stop():
                    logger.warning("🚨 Emergency stop detected - halting trading")
                    break

                # Process each symbol
                for symbol in self.symbols:
                    await self.process_symbol(symbol)

                # Wait for next check
                await asyncio.sleep(self.check_frequency)

            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error

    async def process_symbol(self, symbol: str):
        """Process trading logic for one symbol"""
        try:
            # Get trading signal
            signal_result = await get_trading_signal(symbol, self.interval)

            if signal_result['signal']['signal'] != 'HOLD':
                # Execute trade
                trade_result = await analyze_and_trade(
                    symbol=symbol,
                    interval=self.interval,
                    execute=True
                )

                logger.info(f"✅ Trade executed for {symbol}: {trade_result}")

        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")

    def check_emergency_stop(self) -> bool:
        """Check if emergency stop file exists"""
        import os
        return os.path.exists("/mnt/d/Bimo_max/crypto-trading-bot/EMERGENCY_STOP")
```

---

### 3.2 Database Trade Persistence

**Purpose**: Store all trades in database for analysis and recovery

**File**: `services/trading-engine/app/models/trade.py` (NEW)

```python
"""
Trade Database Model
Stores trade history for analysis and auditing
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    direction = Column(String(10), nullable=False)  # LONG, SHORT
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    atr = Column(Float, nullable=True)
    entry_time = Column(DateTime, default=datetime.utcnow, index=True)
    exit_time = Column(DateTime, nullable=True)
    profit_loss = Column(Float, nullable=True)
    profit_loss_pct = Column(Float, nullable=True)
    status = Column(String(20), default="OPEN", index=True)  # OPEN, CLOSED, STOPPED
    exit_reason = Column(String(50), nullable=True)  # TAKE_PROFIT, STOP_LOSS, MANUAL, etc.
    signal_confidence = Column(Float, nullable=True)
    trend = Column(String(20), nullable=True)
    market_regime = Column(String(20), nullable=True)
```

---

### 3.3 Backtesting Framework

**Purpose**: Test strategies on historical data before live trading

**File**: `scripts/backtest_engine.py` (NEW)

```python
"""
Backtesting Engine
Test trading strategies on historical data
"""

class BacktestEngine:
    """
    Backtests trading strategy on historical data

    Features:
    - Load historical kline data
    - Simulate trades with realistic slippage
    - Calculate performance metrics
    - Generate equity curve
    - Export results to CSV
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission_pct: float = 0.001,  # 0.1% per trade
        slippage_pct: float = 0.0005  # 0.05% slippage
    ):
        self.initial_capital = initial_capital
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct
        self.trades = []
        self.equity_curve = []

    async def run_backtest(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "60"
    ) -> Dict:
        """
        Run backtest on historical data

        Returns performance metrics:
        - Total return %
        - Win rate %
        - Sharpe ratio
        - Max drawdown
        - Number of trades
        - Average win/loss
        """

        # Load historical data
        # Generate signals for each candle
        # Simulate trade execution
        # Calculate metrics

        pass
```

---

## Implementation Timeline

### Week 1-2: Phase 1 (Core Enhancements)
| Day | Task | Hours | Status |
|-----|------|-------|--------|
| 1-2 | Implement Trend Filter | 3h | ⏳ Pending |
| 2-3 | Implement Volume Confirmation | 3h | ⏳ Pending |
| 3-4 | Implement ATR Indicator | 4h | ⏳ Pending |
| 4-5 | Implement Stochastic Oscillator | 3h | ⏳ Pending |
| 5-7 | Update Signal Aggregation Logic | 5h | ⏳ Pending |
| 7-8 | Write Unit Tests | 4h | ⏳ Pending |
| 8-9 | Integration Testing | 3h | ⏳ Pending |
| 9-10 | Documentation Update | 2h | ⏳ Pending |
| **Total** | **Phase 1 Complete** | **27h** | |

### Week 3-4: Phase 2 (Advanced Features)
| Day | Task | Hours | Status |
|-----|------|-------|--------|
| 11-12 | Market Regime Detection | 4h | ⏳ Pending |
| 12-14 | Partial Profit Taking System | 5h | ⏳ Pending |
| 14-15 | Circuit Breaker Implementation | 3h | ⏳ Pending |
| 15-17 | Dynamic Position Sizing | 4h | ⏳ Pending |
| 17-18 | Correlation Analysis | 3h | ⏳ Pending |
| 18-19 | Minimum Hold Time Filter | 2h | ⏳ Pending |
| 19-21 | Testing & Validation | 6h | ⏳ Pending |
| 21-22 | Documentation | 2h | ⏳ Pending |
| **Total** | **Phase 2 Complete** | **29h** | |

### Week 5-6: Phase 3 (System Optimization)
| Day | Task | Hours | Status |
|-----|------|-------|--------|
| 23-25 | Trading Scheduler (Automated Loop) | 6h | ⏳ Pending |
| 25-27 | Database Trade Persistence | 5h | ⏳ Pending |
| 27-30 | Backtesting Framework | 8h | ⏳ Pending |
| 30-32 | Performance Dashboard | 5h | ⏳ Pending |
| 32-34 | Monitoring & Alerts Enhancement | 4h | ⏳ Pending |
| 34-35 | Final Integration Testing | 5h | ⏳ Pending |
| 35-36 | Complete Documentation | 3h | ⏳ Pending |
| **Total** | **Phase 3 Complete** | **36h** | |

**Total Project Time**: ~92 hours (11.5 working days)

---

## Testing Strategy

### Unit Testing (Each Indicator)
```python
# Example test for Trend Filter
def test_trend_filter_bullish():
    """Test that trend filter correctly identifies bullish trend"""
    # Create mock price data with clear uptrend
    prices = [100, 102, 104, 106, 108, 110, 112, 114, 116, 118]

    trend_filter = TrendFilter(fast_period=3, slow_period=5)
    result = trend_filter.calculate(prices)

    assert result['trend'] == 'BULLISH'
    assert result['signal'] == 'BUY'
    assert result['confidence'] > 0.5
```

### Integration Testing (Full Signal Flow)
```python
async def test_full_signal_generation():
    """Test complete signal generation with all indicators"""
    symbol = "BTCUSDT"
    interval = "60"

    # Get trading signal (should call all 7 indicators)
    result = await get_trading_signal(symbol, interval)

    assert result['success'] == True
    assert 'signal' in result
    assert result['signal']['signal'] in ['BUY', 'SELL', 'HOLD']
    assert 'trend_allowed' in result['signal']
    assert 'volume_confirmed' in result['signal']
```

### Backtesting Validation
```python
async def test_backtest_btc_2024():
    """Backtest strategy on BTC 2024 data"""
    engine = BacktestEngine(initial_capital=10000)

    results = await engine.run_backtest(
        symbol="BTCUSDT",
        start_date="2024-01-01",
        end_date="2024-12-31",
        interval="60"
    )

    # Validate positive expectancy
    assert results['total_return_pct'] > 0
    assert results['win_rate'] > 0.45  # At least 45% win rate
    assert results['max_drawdown_pct'] < 20  # Max 20% drawdown
```

---

## Risk Assessment

### Phase 1 Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Trend filter too restrictive | Medium | Medium | Add confidence threshold adjustment |
| Volume data unreliable on testnet | High | Low | Use mock data fallback for testing |
| ATR calculation errors | Low | High | Comprehensive unit tests + default fallback |
| Integration breaks existing signals | Medium | High | Feature flags + gradual rollout |

### Phase 2 Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Market regime misclassification | Medium | Medium | Multi-indicator regime detection |
| Partial TP complicates position tracking | Low | Medium | Thorough testing of exit logic |
| Circuit breaker false positives | Low | Low | Configurable thresholds |
| Dynamic sizing too conservative | Medium | Low | Backtesting to tune parameters |

### Phase 3 Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Automated loop memory leaks | Medium | High | Monitoring + automatic restarts |
| Database corruption | Low | High | Regular backups + transaction safety |
| Backtesting overfitting | High | Medium | Walk-forward testing + out-of-sample validation |

---

## Success Metrics

### Phase 1 Success Criteria

✅ **Functional Metrics**:
- [ ] All 4 new indicators return valid signals
- [ ] Signal aggregation blocks counter-trend trades correctly
- [ ] ATR-based stops adapt to volatility (tested across calm/volatile periods)
- [ ] All unit tests pass (>95% coverage)

✅ **Performance Metrics** (via backtesting):
- [ ] Win rate increase: +10% minimum
- [ ] Average drawdown reduction: -20% minimum
- [ ] False signal reduction: -30% minimum
- [ ] Risk/reward ratio: Maintained at 1:2 or better

### Phase 2 Success Criteria

✅ **Functional Metrics**:
- [ ] Market regime correctly classified >80% of the time
- [ ] Partial TP executes at all 3 levels in trending markets
- [ ] Circuit breaker activates after 3 consecutive losses
- [ ] Dynamic position sizing reduces size in high volatility

✅ **Performance Metrics**:
- [ ] Additional win rate increase: +5% minimum
- [ ] Average win size increase: +25% (partial TP effect)
- [ ] Max consecutive losses: ≤5 (circuit breaker working)
- [ ] Volatility-adjusted returns: Better Sharpe ratio

### Phase 3 Success Criteria

✅ **Functional Metrics**:
- [ ] Trading loop runs continuously for 7 days without crashes
- [ ] All trades persisted to database with no data loss
- [ ] Backtesting engine produces reproducible results
- [ ] Dashboard displays real-time performance metrics

✅ **Performance Metrics**:
- [ ] Backtested return: >50% annual (conservative estimate)
- [ ] Sharpe ratio: >1.5 (good risk-adjusted returns)
- [ ] Max drawdown: <15% (capital preservation)
- [ ] System uptime: >99% (reliable automation)

---

## Monitoring Dashboard

### Key Metrics to Track

**Real-Time Indicators**:
- Current positions (symbol, direction, P&L)
- Account balance & equity curve
- Daily/weekly/monthly returns
- Win rate (last 10, 30, 100 trades)
- Average win vs average loss
- Current trend filter status (per symbol)
- Market regime classification
- Circuit breaker status

**Risk Metrics**:
- Current drawdown from peak
- Daily loss limit remaining
- Total exposure (% of capital)
- Correlation between open positions
- ATR levels (volatility tracking)
- Consecutive losses counter

**System Health**:
- Trading loop uptime
- Last signal generation timestamp
- API latency (Bybit, microservices)
- Database connection status
- Error rate (last hour/day)

---

## Appendix A: Configuration Files

### Phase 1 Configuration
```yaml
# config/phase1_indicators.yaml
trend_filter:
  fast_period: 50
  slow_period: 200
  neutral_threshold: 0.005  # 0.5%

volume_confirmation:
  period: 20
  breakout_threshold: 1.2  # 1.2x average
  strong_threshold: 1.5    # 1.5x average

atr:
  period: 14
  stop_loss_multiplier: 2.0
  take_profit_multiplier: 4.0

stochastic:
  period: 14
  smooth_k: 3
  smooth_d: 3
  overbought: 80
  oversold: 20

signal_aggregation:
  min_consensus: 4  # Out of 6 core indicators
  min_confidence: 0.6
  trend_filter_weight: 0.25
  volume_confirmation_weight: 0.05
```

### Phase 2 Configuration
```yaml
# config/phase2_features.yaml
market_regime:
  adx_period: 14
  adx_trending_threshold: 25.0
  adx_weak_threshold: 20.0
  volatility_threshold: 0.04  # 4% BB width

partial_profit:
  levels:
    - percentage: 0.50
      atr_multiplier: 1.5
    - percentage: 0.25
      atr_multiplier: 3.0
    - percentage: 0.25
      atr_multiplier: 4.0

circuit_breaker:
  pause_after_3_losses: 4h    # 4 hours
  pause_after_5_losses: 24h   # 24 hours

dynamic_position:
  base_risk_pct: 0.02         # 2% risk per trade
  atr_multiplier: 2.0
  max_position_pct: 0.10      # 10% max position size
```

---

## Appendix B: API Endpoint Summary

### New Endpoints (Phase 1)

```
GET /api/v1/indicators/trend/{symbol}
    Query params: interval, fast_period, slow_period
    Returns: Trend direction (BULLISH/BEARISH/NEUTRAL)

GET /api/v1/indicators/volume/{symbol}
    Query params: interval, period, signal_type
    Returns: Volume confirmation (CONFIRM/REJECT)

GET /api/v1/indicators/atr/{symbol}
    Query params: interval, period, current_price
    Returns: ATR value, volatility, dynamic SL/TP levels

GET /api/v1/indicators/stochastic/{symbol}
    Query params: interval, period, smooth_k, smooth_d
    Returns: %K, %D, overbought/oversold, crossovers
```

### Enhanced Endpoints (Phase 1)

```
GET /api/v1/signals/{symbol}
    Now includes:
    - Trend filter status
    - Volume confirmation
    - ATR-based SL/TP
    - Stochastic signals
    - Enhanced confidence scoring
```

### New Endpoints (Phase 2)

```
GET /api/v1/indicators/regime/{symbol}
    Returns: Market regime classification

GET /api/v1/positions/{position_id}/targets
    Returns: Partial profit taking levels

GET /api/v1/risk/circuit-breaker
    Returns: Circuit breaker status
```

---

## Conclusion

This roadmap provides a systematic, phased approach to dramatically improving the trading bot's performance. Each phase builds on the previous one, with clear success criteria and testing requirements.

**Key Principles**:
1. **Research-Driven**: All improvements based on academic research and industry best practices
2. **Incremental**: Phased rollout allows testing and validation at each stage
3. **Risk-Aware**: Circuit breakers and dynamic risk management protect capital
4. **Testable**: Comprehensive backtesting before live deployment
5. **Maintainable**: Clean code architecture with proper documentation

**Next Steps**:
1. Review and approve this roadmap
2. Set up development branch for Phase 1
3. Begin implementation starting with Trend Filter
4. Continuous testing and validation
5. Iterate based on backtest results

**Estimated Total Timeline**: 6 weeks (with buffer for testing and refinement)

---

*Document Created*: 2025-11-04
*Last Updated*: 2025-11-04
*Status*: Ready for Implementation
*Approval Required*: Yes
