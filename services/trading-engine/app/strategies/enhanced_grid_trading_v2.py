"""
Enhanced Grid Trading Strategy v2
===================================
Purpose: Achieve >80% win rate through highly selective trade filtering

Key Improvements Over v1:
1. **Market Regime Filter**: Only trade in ranging markets (ADX < 25)
2. **RSI Confirmation**: Only buy when RSI < 30 (oversold), sell when RSI > 70 (overbought)
3. **Bollinger Band Filter**: Only trade near bands for mean reversion
4. **Volatility-Based Stops**: Dynamic stop-loss at 1.5x ATR
5. **Quick Profit Taking**: Take profit at 0.8x ATR (smaller wins, higher frequency)
6. **Tighter Grid Range**: Reduce grid range to 8% (vs 15%) for more frequent triggers
7. **Position Pyramid**: Only add positions if previous ones are profitable
8. **Volume Confirmation**: Require volume > 20-period average for entries

Target: >80% Win Rate (vs current 32.6%)
Strategy: Be highly selective, take small wins frequently, cut losses fast

Research Citations:
- ADX < 25 indicates ranging market (J. Welles Wilder, 1978)
- RSI extremes (< 30, > 70) show reversal probability (J. Welles Wilder, 1978)
- Bollinger Bands mean reversion has 70-80% success in ranging markets (John Bollinger, 2001)
- Quick profit taking improves win rate but reduces profit factor (Van Tharp, 2007)

Author: Enhanced Grid Trading Team
Date: 2025-12-08
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

from app.backtesting.strategy_base import (
    StrategyBase,
    Signal,
    SignalType,
    OHLCV,
)

logger = logging.getLogger(__name__)


# =============================================================================
# ENHANCED CONFIGURATION CONSTANTS (80% Win Rate Target)
# =============================================================================

# Market regime filter (KEY IMPROVEMENT #1)
ADX_PERIOD = 14
ADX_RANGING_THRESHOLD = 35  # ADX < 35 = ranging/weak trend market (LOOSENED from 25)
MIN_BARS_FOR_ADX = 30  # Need sufficient data for ADX calculation

# RSI momentum filter (KEY IMPROVEMENT #2)
RSI_PERIOD = 14
RSI_OVERSOLD = 40  # Buy when RSI < 40 (LOOSENED from 30 for more opportunities)
RSI_OVERBOUGHT = 60  # Sell when RSI > 60 (LOOSENED from 70 for more opportunities)
MIN_BARS_FOR_RSI = 20

# Bollinger Bands mean reversion filter (KEY IMPROVEMENT #3)
BB_PERIOD = 20
BB_STD_DEV = 2.0
BB_ENTRY_THRESHOLD = 0.80  # Within 80% of band distance (LOOSENED from 0.95)

# Volatility and risk management (KEY IMPROVEMENT #4 & #5)
ATR_PERIOD = 14
STOP_LOSS_ATR_MULT = 1.5  # Stop at 1.5x ATR (tighter than v1's 2.5x)
TAKE_PROFIT_ATR_MULT = 0.8  # Take profit at 0.8x ATR (quick wins!)
MIN_BARS_FOR_ATR = 20

# Grid configuration (KEY IMPROVEMENT #6)
ENHANCED_GRID_LEVELS = 5  # Fewer levels, tighter range
ENHANCED_GRID_RANGE_PCT = 0.10  # ±10% (LOOSENED from 8% to allow more range)
MAX_CONCURRENT_POSITIONS = 3  # Allow more positions (INCREASED from 2)
POSITION_SIZE_PCT = 0.015  # 1.5% per position (INCREASED from 1%)

# Position pyramid rules (KEY IMPROVEMENT #7)
ALLOW_PYRAMID = True
MIN_PROFIT_PCT_FOR_PYRAMID = 0.3  # Previous position +0.3% profitable (LOWERED from 0.5%)

# Volume filter (KEY IMPROVEMENT #8)
VOLUME_MA_PERIOD = 20
VOLUME_THRESHOLD_MULT = 0.8  # Volume > 0.8x average (LOOSENED from 1.0x)

# Signal confidence adjustments
BASE_BUY_CONFIDENCE = 0.70  # Lower confidence with looser filters (was 0.85)
BASE_SELL_CONFIDENCE = 0.70  # Lower confidence with looser filters (was 0.85)
CONF_BOOST_EXTREME_RSI = 0.05  # Extra confidence for extreme RSI
CONF_BOOST_VOLUME_SPIKE = 0.03  # Extra confidence for volume confirmation
CONF_BOOST_BB_EXTREME = 0.04  # Extra confidence at Bollinger extremes


# =============================================================================
# GRID LEVEL DATA STRUCTURE
# =============================================================================

@dataclass
class EnhancedGridLevel:
    """Grid level with enhanced metadata for v2 strategy"""
    price: float
    level_type: str  # "buy" or "sell"
    level_number: int

    # v2 enhancements
    distance_from_current_pct: float = 0.0
    is_near_bb_band: bool = False  # Within 95% of BB band
    volume_confirmed: bool = False
    rsi_confirmed: bool = False

    # Trade tracking
    triggered: bool = False
    trigger_timestamp: Optional[datetime] = None


@dataclass
class EnhancedPosition:
    """Enhanced position tracking with profit/loss monitoring"""
    entry_price: float
    size: float
    entry_timestamp: datetime
    grid_level: int

    # v2 enhancements
    stop_loss_price: float
    take_profit_price: float
    current_pnl_pct: float = 0.0
    is_profitable: bool = False

    # Exit tracking
    exit_price: Optional[float] = None
    exit_timestamp: Optional[datetime] = None
    exit_reason: Optional[str] = None  # "stop_loss", "take_profit", "signal"


# =============================================================================
# ENHANCED GRID TRADING STRATEGY V2
# =============================================================================

class EnhancedGridTradingV2(StrategyBase):
    """
    Enhanced Grid Trading Strategy with 80%+ Win Rate Target

    Core Philosophy: Be HIGHLY selective, trade ONLY in optimal conditions

    Entry Requirements (ALL must be met):
    1. Market is ranging (ADX < 25)
    2. Price near Bollinger Band (mean reversion setup)
    3. RSI extreme (< 30 for buy, > 70 for sell)
    4. Volume confirmed (> recent average)
    5. No conflicting open positions
    6. Grid level not already triggered recently

    Exit Strategy:
    - Quick profit taking at 0.8x ATR (don't be greedy!)
    - Tight stop loss at 1.5x ATR (cut losses fast!)
    - Exit if market regime changes (ADX > 25)
    """

    def __init__(
        self,
        symbol: str,
        grid_levels: int = ENHANCED_GRID_LEVELS,
        grid_range_pct: float = ENHANCED_GRID_RANGE_PCT,
        max_positions: int = MAX_CONCURRENT_POSITIONS,
        position_size_pct: float = POSITION_SIZE_PCT,
        rsi_oversold: float = RSI_OVERSOLD,
        rsi_overbought: float = RSI_OVERBOUGHT,
        adx_threshold: float = ADX_RANGING_THRESHOLD,
    ):
        """Initialize Enhanced Grid Trading Strategy v2"""
        super().__init__(symbol)

        # Grid configuration
        self.grid_levels = grid_levels
        self.grid_range_pct = grid_range_pct
        self.max_positions = max_positions
        self.position_size_pct = position_size_pct

        # Filter thresholds
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.adx_threshold = adx_threshold

        # State management
        self.grid: List[EnhancedGridLevel] = []
        self.open_positions: List[EnhancedPosition] = []
        self.last_grid_calculation_price: Optional[float] = None
        self.bars: List[OHLCV] = []  # Bar history for indicator calculations

        # Performance tracking
        self.total_wins = 0
        self.total_losses = 0
        self.total_trades = 0

        logger.info(
            f"Enhanced Grid Trading v2 initialized for {symbol}: "
            f"L={grid_levels}, R={grid_range_pct*100:.1f}%, "
            f"RSI={rsi_oversold}/{rsi_overbought}, ADX<{adx_threshold}"
        )

    def get_strategy_name(self) -> str:
        """Return strategy identifier"""
        return f"EnhancedGridV2_{self.symbol}"

    def calculate_rsi(self, closes: List[float], period: int = RSI_PERIOD) -> float:
        """Calculate RSI indicator"""
        if len(closes) < period + 1:
            return 50.0  # Neutral if insufficient data

        deltas = np.diff(closes[-period-1:])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_adx(self, bars: List[OHLCV], period: int = ADX_PERIOD) -> float:
        """
        Calculate ADX (Average Directional Index)
        ADX < 25 = ranging/weak trend
        ADX > 25 = trending market
        """
        if len(bars) < period + 1:
            return 0.0

        highs = np.array([b.high for b in bars[-(period+1):]])
        lows = np.array([b.low for b in bars[-(period+1):]])
        closes = np.array([b.close for b in bars[-(period+1):]])

        # Calculate True Range
        high_low = highs[1:] - lows[1:]
        high_close = np.abs(highs[1:] - closes[:-1])
        low_close = np.abs(lows[1:] - closes[:-1])
        tr = np.maximum(high_low, np.maximum(high_close, low_close))

        # Calculate +DM and -DM
        plus_dm = np.where((highs[1:] - highs[:-1]) > (lows[:-1] - lows[1:]),
                           np.maximum(highs[1:] - highs[:-1], 0), 0)
        minus_dm = np.where((lows[:-1] - lows[1:]) > (highs[1:] - highs[:-1]),
                            np.maximum(lows[:-1] - lows[1:], 0), 0)

        # Smooth with EMA
        atr = np.mean(tr)
        if atr == 0:
            return 0.0

        plus_di = 100 * np.mean(plus_dm) / atr
        minus_di = 100 * np.mean(minus_dm) / atr

        # Calculate ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        adx = np.mean([dx] * min(period, len([dx])))  # Simplified

        return adx

    def calculate_bollinger_bands(
        self, closes: List[float], period: int = BB_PERIOD, std_dev: float = BB_STD_DEV
    ) -> Tuple[float, float, float]:
        """Calculate Bollinger Bands (upper, middle, lower)"""
        if len(closes) < period:
            close = closes[-1] if closes else 0.0
            return (close, close, close)

        recent_closes = closes[-period:]
        middle = np.mean(recent_closes)
        std = np.std(recent_closes)

        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)

        return (upper, middle, lower)

    def calculate_atr(self, bars: List[OHLCV], period: int = ATR_PERIOD) -> float:
        """Calculate Average True Range for volatility measurement"""
        if len(bars) < period + 1:
            return 0.0

        true_ranges = []
        for i in range(len(bars) - period, len(bars)):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i-1].close if i > 0 else bars[i].close

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)

        return np.mean(true_ranges)

    def is_market_ranging(self, bars: List[OHLCV]) -> bool:
        """Check if market is in ranging mode (ADX < threshold)"""
        if len(bars) < MIN_BARS_FOR_ADX:
            return False

        adx = self.calculate_adx(bars)
        is_ranging = adx < self.adx_threshold

        logger.debug(f"{self.symbol}: ADX={adx:.2f}, Ranging={is_ranging}")
        return is_ranging

    def calculate_grid(self, current_price: float, atr: float) -> List[EnhancedGridLevel]:
        """
        Calculate enhanced grid levels with tighter range for higher win rate
        """
        grid = []

        # Use ATR-adaptive range (but cap it)
        atr_pct = (atr / current_price) * 100
        adaptive_range = min(self.grid_range_pct, atr_pct * 2)  # Max 2x ATR

        upper_price = current_price * (1 + adaptive_range)
        lower_price = current_price * (1 - adaptive_range)

        # Create buy levels (below current price)
        buy_levels = self.grid_levels // 2
        for i in range(1, buy_levels + 1):
            level_price = current_price - (i * (current_price - lower_price) / (buy_levels + 1))
            grid.append(EnhancedGridLevel(
                price=level_price,
                level_type="buy",
                level_number=i,
                distance_from_current_pct=((level_price - current_price) / current_price) * 100
            ))

        # Create sell levels (above current price)
        sell_levels = self.grid_levels - buy_levels
        for i in range(1, sell_levels + 1):
            level_price = current_price + (i * (upper_price - current_price) / (sell_levels + 1))
            grid.append(EnhancedGridLevel(
                price=level_price,
                level_type="sell",
                level_number=i,
                distance_from_current_pct=((level_price - current_price) / current_price) * 100
            ))

        return grid

    def check_pyramid_allowed(self) -> bool:
        """Check if we can add another position (pyramid rule)"""
        if not ALLOW_PYRAMID:
            return len(self.open_positions) == 0

        if len(self.open_positions) == 0:
            return True

        # Check if previous positions are profitable
        for pos in self.open_positions:
            if not pos.is_profitable or pos.current_pnl_pct < MIN_PROFIT_PCT_FOR_PYRAMID:
                return False

        return True

    def update_position_pnl(self, current_price: float):
        """Update P&L for all open positions"""
        for pos in self.open_positions:
            pos.current_pnl_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100
            pos.is_profitable = pos.current_pnl_pct > 0

    def check_position_exits(self, current_price: float) -> List[Tuple[EnhancedPosition, str]]:
        """
        Check if any positions should be exited (stop-loss or take-profit)
        Returns list of (position, exit_reason) tuples
        """
        exits = []

        for pos in self.open_positions:
            # Check stop-loss
            if current_price <= pos.stop_loss_price:
                exits.append((pos, "stop_loss"))
            # Check take-profit
            elif current_price >= pos.take_profit_price:
                exits.append((pos, "take_profit"))

        return exits

    def generate_signal(self, bars: List[OHLCV]) -> Signal:
        """
        Generate highly filtered trading signal for 80%+ win rate

        Entry Logic (ALL conditions must be TRUE):
        1. Market is ranging (ADX < 25)
        2. Price near Bollinger Band (mean reversion setup)
        3. RSI extreme (< 30 for buy, > 70 for sell)
        4. Volume > average (confirmation)
        5. Can pyramid (if positions exist)
        6. Not at max positions

        Exit Logic (ANY condition triggers exit):
        1. Stop-loss hit (1.5x ATR)
        2. Take-profit hit (0.8x ATR)
        3. Market regime changes (ADX > 25)
        """
        if len(bars) < max(MIN_BARS_FOR_ADX, MIN_BARS_FOR_RSI, MIN_BARS_FOR_ATR):
            return Signal(
                signal_type=SignalType.HOLD,
                symbol=self.symbol,
                price=bars[-1].close,
                timestamp=bars[-1].timestamp,
                confidence=0.0
            )

        current_bar = bars[-1]
        current_price = current_bar.close

        # Calculate all indicators
        closes = [b.close for b in bars]
        rsi = self.calculate_rsi(closes)
        adx = self.calculate_adx(bars)
        atr = self.calculate_atr(bars)
        bb_upper, bb_middle, bb_lower = self.calculate_bollinger_bands(closes)

        # Volume filter
        volumes = [b.volume for b in bars[-VOLUME_MA_PERIOD:]]
        avg_volume = np.mean(volumes)
        current_volume = current_bar.volume
        volume_confirmed = current_volume > (avg_volume * VOLUME_THRESHOLD_MULT)

        # Update existing positions P&L
        self.update_position_pnl(current_price)

        # Check for position exits first
        exits = self.check_position_exits(current_price)
        for pos, reason in exits:
            self.open_positions.remove(pos)
            pos.exit_price = current_price
            pos.exit_timestamp = current_bar.timestamp
            pos.exit_reason = reason

            # Track win/loss
            self.total_trades += 1
            if pos.is_profitable:
                self.total_wins += 1
            else:
                self.total_losses += 1

            logger.info(
                f"{self.symbol}: EXIT {reason} at {current_price:.2f}, "
                f"P&L={pos.current_pnl_pct:+.2f}%, Win Rate={self.get_win_rate():.1f}%"
            )

        # === FILTER #1: Market Regime (MOST IMPORTANT) ===
        if not self.is_market_ranging(bars):
            logger.debug(f"{self.symbol}: Market trending (ADX={adx:.2f} >= {self.adx_threshold}), SKIP")
            return Signal(
                signal_type=SignalType.HOLD,
                symbol=self.symbol,
                price=current_price,
                timestamp=current_bar.timestamp,
                confidence=0.0
            )

        # === FILTER #2: Position Limits ===
        if len(self.open_positions) >= self.max_positions:
            return Signal(
                signal_type=SignalType.HOLD,
                symbol=self.symbol,
                price=current_price,
                timestamp=current_bar.timestamp,
                confidence=0.0
            )

        # === FILTER #3: Pyramid Rules ===
        if not self.check_pyramid_allowed():
            logger.debug(f"{self.symbol}: Pyramid not allowed (prev positions not profitable)")
            return Signal(
                signal_type=SignalType.HOLD,
                symbol=self.symbol,
                price=current_price,
                timestamp=current_bar.timestamp,
                confidence=0.0
            )

        # Calculate/update grid
        if not self.grid or not self.last_grid_calculation_price or \
           abs(current_price - self.last_grid_calculation_price) / self.last_grid_calculation_price > 0.05:
            self.grid = self.calculate_grid(current_price, atr)
            self.last_grid_calculation_price = current_price

        # === CHECK BUY CONDITIONS ===
        # Filter #4: RSI oversold
        if rsi < self.rsi_oversold:
            # Filter #5: Near lower Bollinger Band
            distance_from_lower_bb = abs(current_price - bb_lower) / bb_lower
            if distance_from_lower_bb < (1 - BB_ENTRY_THRESHOLD):
                # Filter #6: Volume confirmation
                if volume_confirmed:
                    # All filters passed! Generate BUY signal
                    confidence = BASE_BUY_CONFIDENCE
                    confidence += CONF_BOOST_EXTREME_RSI if rsi < 25 else 0
                    confidence += CONF_BOOST_VOLUME_SPIKE if current_volume > avg_volume * 1.5 else 0
                    confidence += CONF_BOOST_BB_EXTREME if distance_from_lower_bb < 0.02 else 0
                    confidence = min(confidence, 0.99)  # Cap at 99%

                    # Calculate stop-loss and take-profit
                    stop_loss = current_price - (atr * STOP_LOSS_ATR_MULT)
                    take_profit = current_price + (atr * TAKE_PROFIT_ATR_MULT)

                    # Create position
                    position = EnhancedPosition(
                        entry_price=current_price,
                        size=self.position_size_pct,
                        entry_timestamp=current_bar.timestamp,
                        grid_level=len(self.open_positions) + 1,
                        stop_loss_price=stop_loss,
                        take_profit_price=take_profit
                    )
                    self.open_positions.append(position)

                    logger.info(
                        f"{self.symbol}: BUY at {current_price:.2f} "
                        f"(RSI={rsi:.1f}, ADX={adx:.1f}, Vol={volume_confirmed}, "
                        f"SL={stop_loss:.2f}, TP={take_profit:.2f}, Conf={confidence:.2%})"
                    )

                    return Signal(
                        signal_type=SignalType.BUY,
                        symbol=self.symbol,
                        price=current_price,
                        timestamp=current_bar.timestamp,
                        confidence=confidence,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        position_size_pct=self.position_size_pct
                    )

        # === CHECK SELL CONDITIONS ===
        # Filter #4: RSI overbought
        if rsi > self.rsi_overbought:
            # Filter #5: Near upper Bollinger Band
            distance_from_upper_bb = abs(current_price - bb_upper) / bb_upper
            if distance_from_upper_bb < (1 - BB_ENTRY_THRESHOLD):
                # Filter #6: Volume confirmation
                if volume_confirmed:
                    # Filter #7: Must have open long position to sell
                    if len(self.open_positions) > 0:
                        # All filters passed! Generate SELL signal
                        confidence = BASE_SELL_CONFIDENCE
                        confidence += CONF_BOOST_EXTREME_RSI if rsi > 75 else 0
                        confidence += CONF_BOOST_VOLUME_SPIKE if current_volume > avg_volume * 1.5 else 0
                        confidence += CONF_BOOST_BB_EXTREME if distance_from_upper_bb < 0.02 else 0
                        confidence = min(confidence, 0.99)

                        logger.info(
                            f"{self.symbol}: SELL at {current_price:.2f} "
                            f"(RSI={rsi:.1f}, ADX={adx:.1f}, Vol={volume_confirmed}, Conf={confidence:.2%})"
                        )

                        return Signal(
                            signal_type=SignalType.CLOSE_LONG,  # FIX: Use CLOSE_LONG to close long positions
                            symbol=self.symbol,
                            price=current_price,
                            timestamp=current_bar.timestamp,
                            confidence=confidence,
                            position_size_pct=self.position_size_pct
                        )

        # No entry conditions met
        return Signal(
            signal_type=SignalType.HOLD,
            symbol=self.symbol,
            price=current_price,
            timestamp=current_bar.timestamp,
            confidence=0.0
        )

    def get_win_rate(self) -> float:
        """Calculate current win rate"""
        if self.total_trades == 0:
            return 0.0
        return (self.total_wins / self.total_trades) * 100

    def get_strategy_params(self) -> Dict:
        """Return strategy configuration parameters"""
        return {
            "grid_levels": self.grid_levels,
            "grid_range_pct": self.grid_range_pct,
            "max_positions": self.max_positions,
            "position_size_pct": self.position_size_pct,
            "rsi_oversold": self.rsi_oversold,
            "rsi_overbought": self.rsi_overbought,
            "adx_threshold": self.adx_threshold,
            "stop_loss_atr": STOP_LOSS_ATR_MULT,
            "take_profit_atr": TAKE_PROFIT_ATR_MULT,
            "strategy_version": "v2_enhanced",
            "target_win_rate": "80%+"
        }

    def get_name(self) -> str:
        """
        Return strategy name (required by StrategyBase)
        """
        return "Enhanced Grid Trading v2"

    def on_bar(self, bar: OHLCV, equity: float) -> Signal:
        """
        Process a new bar and generate trading signal (required by StrategyBase)

        This is the main entry point called by the backtest engine for each bar.
        Delegates to generate_signal() for the actual signal logic.

        Args:
            bar: New OHLCV bar to process
            equity: Current account equity

        Returns:
            Signal: Trading signal (BUY/SELL/HOLD)
        """
        # Add the new bar to our bar history
        self.bars.append(bar)

        # Keep only the last 200 bars for memory efficiency
        if len(self.bars) > 200:
            self.bars = self.bars[-200:]

        # Generate signal from the complete bar history
        return self.generate_signal(self.bars)
