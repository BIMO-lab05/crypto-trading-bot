"""
ATR (Average True Range) Indicator
Measures market volatility for dynamic risk management
"""

from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

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

        # Fixed: Validate current_price before calculation (Critical Issue #4)
        # Division by zero would crash if current_price is 0 or invalid
        if current_price <= 0 or np.isnan(current_price) or np.isinf(current_price):
            logger.error(f"Invalid current_price: {current_price}. Cannot calculate ATR percentage.")
            return self._default_response(1.0)  # Use 1.0 as safe fallback for calculations

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
                "timestamp": int(pd.Timestamp.now().timestamp() * 1000)
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
            "timestamp": int(pd.Timestamp.now().timestamp() * 1000)
        }
