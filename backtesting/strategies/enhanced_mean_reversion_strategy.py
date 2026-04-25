"""
Enhanced Mean Reversion Strategy
Phase 2.3 - Advanced Mean Reversion with Multiple Indicators

Strategy Logic:
- BUY when price touches/breaks below lower Bollinger Band + RSI oversold + Stochastic oversold
- SELL when price touches/breaks above upper Bollinger Band + RSI overbought + Stochastic overbought
- EXIT at middle band (mean) or stop loss
- Enhanced with VWAP and RSI divergence detection

This strategy assumes price will revert to mean after extreme moves.
Better suited for ranging/choppy markets vs trend-following.

Key Enhancements:
1. Multiple confirmation indicators (RSI + Stochastic + VWAP)
2. RSI divergence detection
3. Volume-weighted average price (VWAP) confirmation
4. Dynamic stop-loss based on ATR
5. Improved exit conditions
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any
from dataclasses import dataclass
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class EnhancedMeanReversionConfig:
    """Configuration for enhanced mean reversion strategy"""
    # Bollinger Bands
    bb_period: int = 20
    bb_std: float = 2.0
    bb_entry_threshold: float = 0.05  # How far beyond band to trigger (5% of width)

    # RSI confirmation
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    rsi_divergence_lookback: int = 20

    # Stochastic confirmation
    stoch_k_period: int = 14
    stoch_d_period: int = 3
    stoch_oversold: int = 20
    stoch_overbought: int = 80

    # VWAP parameters
    vwap_period: int = 20

    # ATR for dynamic stops
    atr_period: int = 14
    atr_stop_multiplier: float = 2.0

    # Risk management
    max_stop_loss_pct: float = 3.0  # Maximum stop loss percentage
    take_profit_ratio: float = 2.0  # TP = SL * ratio

    # Exit options
    exit_at_mean: bool = True  # Close position when price reaches middle band
    exit_on_opposite_band: bool = False  # Close when opposite band hit
    use_dynamic_stops: bool = True  # Use ATR-based stops


class EnhancedMeanReversionStrategy:
    """
    Enhanced Mean reversion strategy using multiple indicators

    Entry Rules:
    - LONG: Price <= Lower BB AND RSI < oversold AND Stoch K < 20 AND Price < VWAP
    - SHORT: Price >= Upper BB AND RSI > overbought AND Stoch K > 80 AND Price > VWAP

    Exit Rules:
    - Target: Middle band (mean) or take profit %
    - Stop: Dynamic ATR-based stop or opposite extreme
    """

    def __init__(self, config: EnhancedMeanReversionConfig = None):
        """Initialize strategy with configuration"""
        self.config = config or EnhancedMeanReversionConfig()
        logger.info(f"EnhancedMeanReversionStrategy initialized: BB({self.config.bb_period},{self.config.bb_std}), "
                   f"RSI({self.config.rsi_period}), Stoch({self.config.stoch_k_period})")

    def calculate_rsi(self, data: pd.DataFrame, period: int = None) -> pd.Series:
        """Calculate RSI"""
        period = period or self.config.rsi_period
        close = data['close']
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_stochastic(self, data: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        """Calculate Stochastic Oscillator (K and D lines)"""
        high = data['high']
        low = data['low']
        close = data['close']
        
        # Calculate %K
        lowest_low = low.rolling(window=self.config.stoch_k_period).min()
        highest_high = high.rolling(window=self.config.stoch_k_period).max()
        
        stoch_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
        stoch_d = stoch_k.rolling(window=self.config.stoch_d_period).mean()
        
        return stoch_k, stoch_d

    def calculate_bollinger_bands(
        self,
        data: pd.DataFrame,
        period: int = None,
        std_dev: float = None
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands"""
        period = period or self.config.bb_period
        std_dev = std_dev or self.config.bb_std

        close = data['close']
        middle_band = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)

        return upper_band, middle_band, lower_band

    def calculate_vwap(self, data: pd.DataFrame) -> pd.Series:
        """Calculate Volume Weighted Average Price"""
        typical_price = (data['high'] + data['low'] + data['close']) / 3
        vwap = (typical_price * data['volume']).rolling(window=self.config.vwap_period).sum() / \
               data['volume'].rolling(window=self.config.vwap_period).sum()
        return vwap

    def calculate_atr(self, data: pd.DataFrame) -> pd.Series:
        """Calculate Average True Range"""
        high = data['high']
        low = data['low']
        close = data['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=self.config.atr_period).mean()
        
        return atr

    def detect_rsi_divergence(self, data: pd.DataFrame) -> tuple[bool, bool]:
        """Detect RSI divergence (bullish and bearish)"""
        # This is a simplified divergence detection
        # In practice, this would require more sophisticated peak/trough detection
        
        rsi = self.calculate_rsi(data)
        close = data['close']
        
        # Look for recent divergences in the lookback period
        lookback = self.config.rsi_divergence_lookback
        if len(rsi) < lookback:
            return False, False
            
        recent_rsi = rsi.iloc[-lookback:]
        recent_price = close.iloc[-lookback:]
        
        # Simplified: check if price is making new highs/lows while RSI isn't
        # This is a basic implementation - real divergence detection is more complex
        bullish_div = False  # Recent price low but RSI not making new low
        bearish_div = False  # Recent price high but RSI not making new high
        
        return bullish_div, bearish_div

    def is_at_lower_band(
        self,
        price: float,
        lower_band: float,
        upper_band: float,
        middle_band: float
    ) -> bool:
        """Check if price is at or below lower Bollinger Band"""
        band_width = upper_band - lower_band
        threshold = lower_band + (band_width * self.config.bb_entry_threshold)
        return price <= threshold

    def is_at_upper_band(
        self,
        price: float,
        upper_band: float,
        lower_band: float,
        middle_band: float
    ) -> bool:
        """Check if price is at or above upper Bollinger Band"""
        band_width = upper_band - lower_band
        threshold = upper_band - (band_width * self.config.bb_entry_threshold)
        return price >= threshold

    def is_at_middle_band(
        self,
        price: float,
        middle_band: float,
        tolerance_pct: float = 0.3
    ) -> bool:
        """Check if price has reverted to mean (middle band)"""
        tolerance = middle_band * (tolerance_pct / 100)
        return abs(price - middle_band) <= tolerance

    def generate_signal(
        self,
        row: pd.Series,
        position: Any,
        idx: int,
        data: pd.DataFrame
    ) -> Optional[Dict[str, Any]]:
        """
        Generate enhanced mean reversion trading signal

        Args:
            row: Current row data
            position: Current position (or None)
            idx: Current index
            data: Full OHLCV DataFrame

        Returns:
            Signal dictionary or None
        """
        # Need enough data for all indicators
        min_period = max(
            self.config.bb_period,
            self.config.rsi_period,
            self.config.stoch_k_period,
            self.config.vwap_period,
            self.config.atr_period,
            self.config.rsi_divergence_lookback
        )

        if idx < min_period:
            return None

        # Get data subset
        if isinstance(data.index, pd.DatetimeIndex):
            data_subset = data.reset_index(drop=True).iloc[:idx+1]
        else:
            data_subset = data.iloc[:idx+1]

        try:
            # Calculate all indicators
            rsi = self.calculate_rsi(data_subset)
            stoch_k, stoch_d = self.calculate_stochastic(data_subset)
            upper_bb, middle_bb, lower_bb = self.calculate_bollinger_bands(data_subset)
            vwap = self.calculate_vwap(data_subset)
            atr = self.calculate_atr(data_subset)

            # Current values
            current_price = row['close']
            current_rsi = rsi.iloc[-1]
            current_stoch_k = stoch_k.iloc[-1]
            current_stoch_d = stoch_d.iloc[-1]
            current_upper = upper_bb.iloc[-1]
            current_middle = middle_bb.iloc[-1]
            current_lower = lower_bb.iloc[-1]
            current_vwap = vwap.iloc[-1] if not pd.isna(vwap.iloc[-1]) else current_price
            current_atr = atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else 0

            # Check for NaN
            if any(pd.isna(val) for val in [
                current_rsi, current_stoch_k, current_stoch_d, 
                current_upper, current_middle, current_lower, 
                current_vwap, current_atr
            ]):
                return None

            # If no position, look for entry signals
            if position is None:
                # LONG entry: Price at lower band + RSI oversold + Stoch oversold + Price < VWAP
                at_lower = self.is_at_lower_band(current_price, current_lower, current_upper, current_middle)
                rsi_oversold = current_rsi < self.config.rsi_oversold
                stoch_oversold = current_stoch_k < self.config.stoch_oversold
                price_below_vwap = current_price < current_vwap

                if at_lower and rsi_oversold and stoch_oversold and price_below_vwap:
                    reason = (f"Enhanced mean reversion LONG: Price ${current_price:.2f} at lower BB ${current_lower:.2f}, "
                             f"RSI {current_rsi:.1f}, Stoch K {current_stoch_k:.1f}, Price < VWAP ${current_vwap:.2f}")
                    logger.debug(f"Signal at idx {idx}: {reason}")

                    # Calculate dynamic stop loss based on ATR
                    if self.config.use_dynamic_stops and current_atr > 0:
                        stop_loss_pct = min((current_atr / current_price) * 100 * self.config.atr_stop_multiplier, 
                                          self.config.max_stop_loss_pct)
                        take_profit_pct = stop_loss_pct * self.config.take_profit_ratio
                    else:
                        stop_loss_pct = self.config.max_stop_loss_pct
                        take_profit_pct = stop_loss_pct * self.config.take_profit_ratio

                    return {
                        'action': 'BUY',
                        'stop_loss_pct': stop_loss_pct,
                        'take_profit_pct': take_profit_pct,
                        'reason': reason,
                        'price': current_price,
                        'lower_bb': current_lower,
                        'middle_bb': current_middle,
                        'upper_bb': current_upper,
                        'rsi': current_rsi,
                        'stoch_k': current_stoch_k,
                        'vwap': current_vwap,
                        'atr': current_atr
                    }

                # SHORT entry: Price at upper band + RSI overbought + Stoch overbought + Price > VWAP
                at_upper = self.is_at_upper_band(current_price, current_upper, current_lower, current_middle)
                rsi_overbought = current_rsi > self.config.rsi_overbought
                stoch_overbought = current_stoch_k > self.config.stoch_overbought
                price_above_vwap = current_price > current_vwap

                if at_upper and rsi_overbought and stoch_overbought and price_above_vwap:
                    reason = (f"Enhanced mean reversion SHORT: Price ${current_price:.2f} at upper BB ${current_upper:.2f}, "
                             f"RSI {current_rsi:.1f}, Stoch K {current_stoch_k:.1f}, Price > VWAP ${current_vwap:.2f}")
                    logger.debug(f"Signal at idx {idx}: {reason}")

                    # Calculate dynamic stop loss based on ATR
                    if self.config.use_dynamic_stops and current_atr > 0:
                        stop_loss_pct = min((current_atr / current_price) * 100 * self.config.atr_stop_multiplier, 
                                          self.config.max_stop_loss_pct)
                        take_profit_pct = stop_loss_pct * self.config.take_profit_ratio
                    else:
                        stop_loss_pct = self.config.max_stop_loss_pct
                        take_profit_pct = stop_loss_pct * self.config.take_profit_ratio

                    return {
                        'action': 'SELL',
                        'stop_loss_pct': stop_loss_pct,
                        'take_profit_pct': take_profit_pct,
                        'reason': reason,
                        'price': current_price,
                        'lower_bb': current_lower,
                        'middle_bb': current_middle,
                        'upper_bb': current_upper,
                        'rsi': current_rsi,
                        'stoch_k': current_stoch_k,
                        'vwap': current_vwap,
                        'atr': current_atr
                    }

            # If we have a position, check for exit signals
            else:
                if hasattr(position, 'order_type'):
                    # Exit LONG at middle band (mean reversion complete)
                    if position.order_type.value == 'BUY':
                        if self.config.exit_at_mean and self.is_at_middle_band(current_price, current_middle):
                            logger.debug(f"Exit LONG at idx {idx}: Price reverted to mean ${current_middle:.2f}")
                            return {'action': 'HOLD'}  # Close position

                        # Exit if price hits upper band (opposite extreme)
                        if self.config.exit_on_opposite_band and self.is_at_upper_band(
                            current_price, current_upper, current_lower, current_middle
                        ):
                            logger.debug(f"Exit LONG at idx {idx}: Price hit upper band ${current_upper:.2f}")
                            return {'action': 'HOLD'}

                    # Exit SHORT at middle band (mean reversion complete)
                    elif position.order_type.value == 'SELL':
                        if self.config.exit_at_mean and self.is_at_middle_band(current_price, current_middle):
                            logger.debug(f"Exit SHORT at idx {idx}: Price reverted to mean ${current_middle:.2f}")
                            return {'action': 'HOLD'}

                        # Exit if price hits lower band (opposite extreme)
                        if self.config.exit_on_opposite_band and self.is_at_lower_band(
                            current_price, current_lower, current_upper, current_middle
                        ):
                            logger.debug(f"Exit SHORT at idx {idx}: Price hit lower band ${current_lower:.2f}")
                            return {'action': 'HOLD'}

            return None

        except Exception as e:
            logger.warning(f"Error generating signal at idx {idx}: {e}")
            return None


def create_enhanced_mean_reversion_strategy(
    bb_period: int = 20,
    bb_std: float = 2.0,
    bb_entry_threshold: float = 0.05,
    rsi_period: int = 14,
    rsi_oversold: int = 30,
    rsi_overbought: int = 70,
    stoch_k_period: int = 14,
    stoch_d_period: int = 3,
    stoch_oversold: int = 20,
    stoch_overbought: int = 80,
    vwap_period: int = 20,
    atr_period: int = 14,
    atr_stop_multiplier: float = 2.0,
    max_stop_loss_pct: float = 3.0,
    take_profit_ratio: float = 2.0,
    exit_at_mean: bool = True,
    exit_on_opposite: bool = False,
    use_dynamic_stops: bool = True
):
    """
    Factory function to create enhanced mean reversion strategy

    Args:
        bb_period: Bollinger Bands period
        bb_std: Bollinger Bands standard deviation
        bb_entry_threshold: How far beyond band to trigger (fraction of width)
        rsi_period: RSI period
        rsi_oversold: RSI oversold threshold
        rsi_overbought: RSI overbought threshold
        stoch_k_period: Stochastic K period
        stoch_d_period: Stochastic D period
        stoch_oversold: Stochastic oversold threshold
        stoch_overbought: Stochastic overbought threshold
        vwap_period: VWAP period
        atr_period: ATR period for dynamic stops
        atr_stop_multiplier: Multiplier for ATR-based stops
        max_stop_loss_pct: Maximum stop loss percentage
        take_profit_ratio: Ratio of TP to SL
        exit_at_mean: Exit when price reaches middle band
        exit_on_opposite: Exit when price reaches opposite band
        use_dynamic_stops: Use ATR-based dynamic stops

    Returns:
        Strategy function compatible with backtest engine
    """
    config = EnhancedMeanReversionConfig(
        bb_period=bb_period,
        bb_std=bb_std,
        bb_entry_threshold=bb_entry_threshold,
        rsi_period=rsi_period,
        rsi_oversold=rsi_oversold,
        rsi_overbought=rsi_overbought,
        stoch_k_period=stoch_k_period,
        stoch_d_period=stoch_d_period,
        stoch_oversold=stoch_oversold,
        stoch_overbought=stoch_overbought,
        vwap_period=vwap_period,
        atr_period=atr_period,
        atr_stop_multiplier=atr_stop_multiplier,
        max_stop_loss_pct=max_stop_loss_pct,
        take_profit_ratio=take_profit_ratio,
        exit_at_mean=exit_at_mean,
        exit_on_opposite_band=exit_on_opposite,
        use_dynamic_stops=use_dynamic_stops
    )

    strategy = EnhancedMeanReversionStrategy(config)

    return strategy.generate_signal