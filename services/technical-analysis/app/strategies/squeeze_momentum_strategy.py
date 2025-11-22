"""
Squeeze Momentum Trading Strategy
Purpose: Entry/exit rules based on Squeeze Momentum Indicator (SQZMOM)

This strategy trades breakouts from low-volatility squeeze conditions using
LazyBear's Squeeze Momentum Indicator for timing and direction.
"""

import pandas as pd
import logging
from typing import Dict, Optional
from datetime import datetime

from app.indicators.squeeze_momentum import SqueezeMomentumIndicator
from app.models import SignalType

logger = logging.getLogger(__name__)


class SqueezeMomentumStrategy:
    """
    Trading Strategy based on Squeeze Momentum Indicator

    Entry Rules:
    - LONG Entry:
      * Squeeze releases (squeeze_off = True) OR
      * Squeeze active with accelerating positive momentum (color = 'lime')
      * Momentum > min_momentum_threshold
      * Optional: Volume confirmation

    - SHORT Entry:
      * Squeeze releases (squeeze_off = True) OR
      * Squeeze active with accelerating negative momentum (color = 'red')
      * abs(Momentum) > min_momentum_threshold
      * Optional: Volume confirmation

    Exit Rules:
    - Stop Loss:
      * Momentum reversal (color changes from bullish to bearish or vice versa)
      * OR Fixed percentage stop loss (default: 2%)

    - Take Profit:
      * Momentum exhaustion (momentum declining for 3+ bars)
      * OR Fixed percentage take profit (default: 4%)
      * OR 1:2 Risk/Reward ratio reached

    Risk Management:
    - Position sizing based on stop loss distance
    - Maximum 2% risk per trade
    - 1:2 minimum risk/reward ratio
    """

    def __init__(
        self,
        sqzmom_indicator: Optional[SqueezeMomentumIndicator] = None,
        min_momentum_threshold: float = 0.5,
        stop_loss_pct: float = 2.0,
        take_profit_pct: float = 4.0,
        require_squeeze_release: bool = True,
        require_volume_confirmation: bool = False,
        volume_threshold: float = 1.2
    ):
        """
        Initialize Squeeze Momentum Strategy

        Args:
            sqzmom_indicator: Instance of SqueezeMomentumIndicator (creates default if None)
            min_momentum_threshold: Minimum absolute momentum value for entry (default: 0.5)
            stop_loss_pct: Stop loss percentage from entry (default: 2.0%)
            take_profit_pct: Take profit percentage from entry (default: 4.0%)
            require_squeeze_release: Only enter on squeeze release, not during squeeze (default: True)
            require_volume_confirmation: Require above-average volume for entry (default: False)
            volume_threshold: Minimum volume multiplier vs average (default: 1.2x)
        """
        # Initialize indicator if not provided
        self.indicator = sqzmom_indicator if sqzmom_indicator else SqueezeMomentumIndicator()

        # Strategy parameters
        self.min_momentum = min_momentum_threshold
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.require_squeeze_release = require_squeeze_release
        self.require_volume_confirmation = require_volume_confirmation
        self.volume_threshold = volume_threshold

        # Tracking variables
        self.momentum_exhaustion_count = 0
        self.exhaustion_threshold = 3  # Bars of declining momentum before exit

        logger.info(
            f"Squeeze Momentum Strategy initialized: "
            f"min_momentum={min_momentum_threshold}, "
            f"stop_loss={stop_loss_pct}%, take_profit={take_profit_pct}%, "
            f"require_release={require_squeeze_release}, "
            f"volume_confirm={require_volume_confirmation}"
        )

    def analyze(self, df: pd.DataFrame) -> Dict:
        """
        Analyze market data and generate trading signal

        Args:
            df: DataFrame with OHLCV data (columns: open, high, low, close, volume)

        Returns:
            Dictionary with:
            - action: 'BUY'|'SELL'|'HOLD'
            - confidence: float (0-1)
            - entry_price: float (current close price)
            - stop_loss: float (calculated stop loss price)
            - take_profit: float (calculated take profit price)
            - reason: str (explanation for the signal)
            - momentum: float (current momentum value)
            - squeeze_state: str ('ON'|'OFF'|'TRANSITIONAL')
            - color: str (momentum bar color)

        Returns error dict if analysis fails.
        """
        # Validate input
        if df is None or len(df) == 0:
            return {
                'action': 'HOLD',
                'confidence': 0.0,
                'reason': 'No data provided'
            }

        try:
            # Calculate indicator
            result_df = self.indicator.calculate(df)

            if result_df is None:
                return {
                    'action': 'HOLD',
                    'confidence': 0.0,
                    'reason': 'Insufficient data for SQZMOM calculation'
                }

            # Get latest values
            latest = result_df.iloc[-1]
            entry_price = float(latest['close'])

            # Extract squeeze state
            squeeze_on = latest['squeeze_on']
            squeeze_off = latest['squeeze_off']
            no_squeeze = latest['no_squeeze']

            # Determine squeeze state string
            if squeeze_on:
                squeeze_state = 'ON'
            elif squeeze_off:
                squeeze_state = 'OFF'
            else:
                squeeze_state = 'TRANSITIONAL'

            # Extract momentum and color
            momentum = latest['sqz_momentum']
            color = latest['sqz_color']
            confidence = latest['sqz_confidence']

            # Check volume if required
            if self.require_volume_confirmation:
                volume_ok = self._check_volume(result_df)
                if not volume_ok:
                    return {
                        'action': 'HOLD',
                        'confidence': 0.0,
                        'entry_price': entry_price,
                        'stop_loss': 0.0,
                        'take_profit': 0.0,
                        'reason': 'Insufficient volume for entry',
                        'momentum': round(float(momentum), 4),
                        'squeeze_state': squeeze_state,
                        'color': color
                    }

            # Determine action
            action = 'HOLD'
            reason = 'No clear signal'

            # Check for LONG entry
            if self.should_enter_long(result_df):
                action = 'BUY'
                stop_loss = entry_price * (1 - self.stop_loss_pct / 100)
                take_profit = entry_price * (1 + self.take_profit_pct / 100)
                reason = self._get_long_entry_reason(latest)

            # Check for SHORT entry
            elif self.should_enter_short(result_df):
                action = 'SELL'
                stop_loss = entry_price * (1 + self.stop_loss_pct / 100)
                take_profit = entry_price * (1 - self.take_profit_pct / 100)
                reason = self._get_short_entry_reason(latest)

            # HOLD
            else:
                stop_loss = 0.0
                take_profit = 0.0
                reason = self._get_hold_reason(latest)

            return {
                'action': action,
                'confidence': round(float(confidence), 2),
                'entry_price': round(entry_price, 2),
                'stop_loss': round(stop_loss, 2),
                'take_profit': round(take_profit, 2),
                'reason': reason,
                'momentum': round(float(momentum), 4),
                'squeeze_state': squeeze_state,
                'color': color,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error in strategy analysis: {e}", exc_info=True)
            return {
                'action': 'HOLD',
                'confidence': 0.0,
                'reason': f'Analysis error: {str(e)}'
            }

    def should_enter_long(self, df: pd.DataFrame) -> bool:
        """
        Check if conditions are met for LONG entry

        Args:
            df: DataFrame with calculated SQZMOM indicators

        Returns:
            True if should enter LONG, False otherwise

        Entry Conditions (ALL must be met):
        1. Momentum is positive and above threshold
        2. Either:
           a. Squeeze released (squeeze_off = True), OR
           b. Squeeze active with accelerating momentum (color = 'lime')
        3. Momentum bar color is bullish ('lime' or 'green')
        """
        latest = df.iloc[-1]

        # Check if we have required data
        if pd.isna(latest['sqz_momentum']):
            return False

        momentum = latest['sqz_momentum']
        color = latest['sqz_color']
        squeeze_on = latest['squeeze_on']
        squeeze_off = latest['squeeze_off']

        # Condition 1: Positive momentum above threshold
        if momentum < self.min_momentum:
            logger.debug(f"LONG rejected: momentum {momentum:.4f} < threshold {self.min_momentum}")
            return False

        # Condition 2: Color must be bullish
        if color not in ['lime', 'green']:
            logger.debug(f"LONG rejected: color {color} not bullish")
            return False

        # Condition 3: Squeeze condition check
        if self.require_squeeze_release:
            # Strict mode: Only enter on squeeze release
            if not squeeze_off:
                logger.debug("LONG rejected: require squeeze release but not released")
                return False
        else:
            # Relaxed mode: Enter on squeeze release OR accelerating momentum during squeeze
            if not squeeze_off and not (squeeze_on and color == 'lime'):
                logger.debug("LONG rejected: neither squeeze release nor accelerating momentum")
                return False

        logger.info(
            f"LONG entry signal: momentum={momentum:.4f}, color={color}, "
            f"squeeze_off={squeeze_off}, squeeze_on={squeeze_on}"
        )
        return True

    def should_enter_short(self, df: pd.DataFrame) -> bool:
        """
        Check if conditions are met for SHORT entry

        Args:
            df: DataFrame with calculated SQZMOM indicators

        Returns:
            True if should enter SHORT, False otherwise

        Entry Conditions (ALL must be met):
        1. Momentum is negative and below -threshold
        2. Either:
           a. Squeeze released (squeeze_off = True), OR
           b. Squeeze active with accelerating negative momentum (color = 'red')
        3. Momentum bar color is bearish ('red' or 'maroon')
        """
        latest = df.iloc[-1]

        # Check if we have required data
        if pd.isna(latest['sqz_momentum']):
            return False

        momentum = latest['sqz_momentum']
        color = latest['sqz_color']
        squeeze_on = latest['squeeze_on']
        squeeze_off = latest['squeeze_off']

        # Condition 1: Negative momentum below -threshold
        if momentum > -self.min_momentum:
            logger.debug(f"SHORT rejected: momentum {momentum:.4f} > -threshold {-self.min_momentum}")
            return False

        # Condition 2: Color must be bearish
        if color not in ['red', 'maroon']:
            logger.debug(f"SHORT rejected: color {color} not bearish")
            return False

        # Condition 3: Squeeze condition check
        if self.require_squeeze_release:
            # Strict mode: Only enter on squeeze release
            if not squeeze_off:
                logger.debug("SHORT rejected: require squeeze release but not released")
                return False
        else:
            # Relaxed mode: Enter on squeeze release OR accelerating negative momentum during squeeze
            if not squeeze_off and not (squeeze_on and color == 'red'):
                logger.debug("SHORT rejected: neither squeeze release nor accelerating negative momentum")
                return False

        logger.info(
            f"SHORT entry signal: momentum={momentum:.4f}, color={color}, "
            f"squeeze_off={squeeze_off}, squeeze_on={squeeze_on}"
        )
        return True

    def should_exit(
        self,
        df: pd.DataFrame,
        position_type: str,
        entry_price: float
    ) -> bool:
        """
        Check if should exit current position

        Args:
            df: DataFrame with calculated SQZMOM indicators
            position_type: 'LONG' or 'SHORT'
            entry_price: Entry price of the position

        Returns:
            True if should exit, False otherwise

        Exit Conditions (ANY triggers exit):
        1. Momentum reversal (color flip: bullish to bearish or vice versa)
        2. Momentum exhaustion (momentum declining for exhaustion_threshold bars)
        3. Stop loss hit
        4. Take profit hit
        """
        latest = df.iloc[-1]
        current_price = float(latest['close'])
        color = latest['sqz_color']

        position_type = position_type.upper()

        # Calculate P&L percentage
        if position_type == 'LONG':
            pnl_pct = ((current_price - entry_price) / entry_price) * 100

            # Stop loss check
            if pnl_pct <= -self.stop_loss_pct:
                logger.info(f"EXIT LONG: Stop loss hit ({pnl_pct:.2f}%)")
                return True

            # Take profit check
            if pnl_pct >= self.take_profit_pct:
                logger.info(f"EXIT LONG: Take profit hit ({pnl_pct:.2f}%)")
                return True

            # Momentum reversal (bullish to bearish)
            if color in ['red', 'maroon']:
                logger.info(f"EXIT LONG: Momentum reversed to bearish ({color})")
                return True

        elif position_type == 'SHORT':
            pnl_pct = ((entry_price - current_price) / entry_price) * 100

            # Stop loss check
            if pnl_pct <= -self.stop_loss_pct:
                logger.info(f"EXIT SHORT: Stop loss hit ({pnl_pct:.2f}%)")
                return True

            # Take profit check
            if pnl_pct >= self.take_profit_pct:
                logger.info(f"EXIT SHORT: Take profit hit ({pnl_pct:.2f}%)")
                return True

            # Momentum reversal (bearish to bullish)
            if color in ['lime', 'green']:
                logger.info(f"EXIT SHORT: Momentum reversed to bullish ({color})")
                return True

        # Momentum exhaustion check (requires historical data)
        if self._check_momentum_exhaustion(df, position_type):
            logger.info("EXIT: Momentum exhaustion detected")
            return True

        return False

    def _check_volume(self, df: pd.DataFrame, period: int = 20) -> bool:
        """
        Check if current volume is above threshold vs average

        Args:
            df: DataFrame with 'volume' column
            period: Period for volume average calculation

        Returns:
            True if volume is sufficient, False otherwise
        """
        if 'volume' not in df.columns or len(df) < period:
            # If no volume data, don't block trades
            logger.warning("No volume data available, skipping volume check")
            return True

        current_volume = df['volume'].iloc[-1]
        avg_volume = df['volume'].rolling(window=period).mean().iloc[-1]

        if pd.isna(avg_volume) or avg_volume == 0:
            return True

        volume_ratio = current_volume / avg_volume

        if volume_ratio >= self.volume_threshold:
            logger.debug(f"Volume OK: {volume_ratio:.2f}x average")
            return True
        else:
            logger.debug(f"Volume insufficient: {volume_ratio:.2f}x average (need {self.volume_threshold}x)")
            return False

    def _check_momentum_exhaustion(self, df: pd.DataFrame, position_type: str) -> bool:
        """
        Check if momentum is exhausting (declining for multiple bars)

        Args:
            df: DataFrame with 'sqz_momentum' column
            position_type: 'LONG' or 'SHORT'

        Returns:
            True if momentum exhaustion detected, False otherwise
        """
        if len(df) < self.exhaustion_threshold + 1:
            return False

        # Get last N momentum values
        recent_momentum = df['sqz_momentum'].tail(self.exhaustion_threshold + 1)

        if position_type == 'LONG':
            # For LONG, check if positive momentum is declining
            is_declining = all(
                recent_momentum.iloc[i] > recent_momentum.iloc[i + 1]
                for i in range(len(recent_momentum) - 1)
            )
            if is_declining:
                logger.debug(f"Momentum exhaustion (LONG): declining for {self.exhaustion_threshold} bars")
                return True

        elif position_type == 'SHORT':
            # For SHORT, check if negative momentum is weakening (becoming less negative)
            is_weakening = all(
                recent_momentum.iloc[i] < recent_momentum.iloc[i + 1]
                for i in range(len(recent_momentum) - 1)
            )
            if is_weakening:
                logger.debug(f"Momentum exhaustion (SHORT): weakening for {self.exhaustion_threshold} bars")
                return True

        return False

    def _get_long_entry_reason(self, latest: pd.Series) -> str:
        """Generate explanation for LONG entry"""
        squeeze_state = "Squeeze released" if latest['squeeze_off'] else "Squeeze active"
        momentum = latest['sqz_momentum']
        color = latest['sqz_color']

        return (
            f"LONG Entry: {squeeze_state}, bullish momentum ({momentum:.4f}), "
            f"accelerating ({color})"
        )

    def _get_short_entry_reason(self, latest: pd.Series) -> str:
        """Generate explanation for SHORT entry"""
        squeeze_state = "Squeeze released" if latest['squeeze_off'] else "Squeeze active"
        momentum = latest['sqz_momentum']
        color = latest['sqz_color']

        return (
            f"SHORT Entry: {squeeze_state}, bearish momentum ({momentum:.4f}), "
            f"accelerating ({color})"
        )

    def _get_hold_reason(self, latest: pd.Series) -> str:
        """Generate explanation for HOLD signal"""
        momentum = latest['sqz_momentum']
        color = latest['sqz_color']
        squeeze_on = latest['squeeze_on']
        squeeze_off = latest['squeeze_off']

        if abs(momentum) < self.min_momentum:
            return f"Momentum too weak ({momentum:.4f} < {self.min_momentum})"
        elif squeeze_on and not self.require_squeeze_release:
            return f"Squeeze building, waiting for release (momentum: {momentum:.4f})"
        elif squeeze_off:
            return f"Squeeze released but unclear momentum direction ({color})"
        else:
            return f"Transitional state, no clear signal (momentum: {momentum:.4f}, color: {color})"
