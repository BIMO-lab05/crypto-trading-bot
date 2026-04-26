"""
Grid Trading Strategy
=====================
Purpose: Profit from price oscillations using a grid of buy/sell orders

This strategy implements:
1. Dynamic grid level calculation based on current price and volatility
2. BUY signals when price crosses below grid levels (buy low)
3. SELL signals when price crosses above grid levels (sell high)
4. Grid rebalancing when price moves beyond boundaries
5. ATR-based dynamic grid spacing for volatility adaptation
6. Position sizing based on equity and active positions

Grid Trading Concept:
- Creates a price grid with multiple levels above and below current price
- Places buy orders at lower levels, sell orders at upper levels
- Profits from mean-reversion and price oscillations
- Works best in ranging/sideways markets

Research-Backed Implementation:
- Grid spacing using ATR adapts to market volatility
- Maximum 5 concurrent positions to limit exposure
- Grid rebalances when price moves >80% through range
- Geometric spacing provides better distribution in volatile markets

Signal Generation Logic:
- BUY: Price crosses below a grid buy level + not at max positions
- SELL: Price crosses above a grid sell level + have open long position
- REBALANCE: Price moves outside grid boundaries (>80%)

Risk Management:
- Maximum 5 concurrent positions (diversified across grid)
- Each position sized at 2% of equity
- Grid-wide stop loss at -5% from average entry
- Individual position stops at 1.5x ATR

Author: Phase 2.3 - Grid Trading Implementation
Date: 2025-12-08
Updated: 2025-12-11 - Parameter optimization
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

# Import base strategy class
from app.backtesting.strategy_base import (
    StrategyBase,
    Signal,
    SignalType,
    OHLCV,
)

logger = logging.getLogger(__name__)


# =============================================================================
# GRID TRADING CONFIGURATION CONSTANTS
# =============================================================================

# Grid construction parameters
DEFAULT_GRID_LEVELS = 10           # Number of grid levels (5 above, 5 below)
DEFAULT_GRID_RANGE_PCT = 0.10      # ±10% from mid-price by default
GRID_SPACING_TYPE = "geometric"    # "arithmetic" or "geometric"

# ATR-based dynamic spacing
ATR_PERIOD = 14                    # Period for ATR calculation
ATR_GRID_MULTIPLIER = 2.0          # Grid spacing = ATR * multiplier (widened from 1.5 — gives more headroom in trending regimes so the grid doesn't get fully filled by a single directional move)
USE_ATR_SPACING = True             # Use ATR for dynamic spacing vs fixed %

# Position management
MAX_CONCURRENT_POSITIONS = 5       # Maximum number of open positions
POSITION_SIZE_PCT = 0.02           # 2% of equity per position
MIN_POSITION_VALUE = 10.0          # Minimum $10 per position

# Grid rebalancing
REBALANCE_THRESHOLD = 0.80         # Rebalance when price moves >80% through grid
MIN_PRICE_MOVE_FOR_REBALANCE = 0.03  # Minimum 3% price move to rebalance

# Risk management
GRID_STOP_LOSS_PCT = 0.05          # Stop entire grid at -5% from avg entry (Changed from 0.10)
INDIVIDUAL_STOP_MULTIPLIER = 1.5   # Individual position stop = ATR * 1.5 (Changed from 2.5)
MAX_GRID_DRAWDOWN_PCT = 0.15       # Maximum 15% drawdown before grid reset

# Signal confidence
BUY_CONFIDENCE_BASE = 0.60         # Base confidence for grid buy signals
SELL_CONFIDENCE_BASE = 0.65        # Base confidence for grid sell signals
CONFIDENCE_BOOST_VOLATILITY = 0.10  # Boost confidence in high volatility

# =============================================================================
# MARKET-ADAPTIVE FILTERS V2 (Improved approach)
# =============================================================================
# Different filter strategies for different market regimes
# Insight: Ranging markets need strict filters, trending markets need looser filters

# Master filter control
USE_ADAPTIVE_FILTERS = True        # Enable market-adaptive filter system
ADX_FILTER_PERIOD = 14             # Period for ADX calculation

# Market regime thresholds (based on ADX)
ADX_RANGING_THRESHOLD = 20         # ADX < 20 = RANGING market (Changed from 30)
ADX_WEAK_TREND_THRESHOLD = 45      # 20 <= ADX < 45 = WEAK TREND
# ADX >= 45 = STRONG TREND

# === RANGING MARKET FILTERS (ADX < 20) ===
# Use STRICT filters - optimize for quality in favorable conditions
RANGING_USE_RSI = True
RANGING_RSI_OVERSOLD = 30          # Buy when RSI < 30 (Changed from 40)
RANGING_RSI_OVERBOUGHT = 70        # Sell when RSI > 70 (Changed from 60)
RANGING_USE_VOLUME = True
RANGING_VOLUME_THRESHOLD = 0.8     # Require 0.8x average volume

# === WEAK TREND FILTERS (20 <= ADX < 45) ===
# Use MODERATE filters - allow more trades but maintain some quality control
WEAK_TREND_USE_RSI = True
WEAK_TREND_RSI_OVERSOLD = 45       # More lenient: Buy when RSI < 45
WEAK_TREND_RSI_OVERBOUGHT = 55     # More lenient: Sell when RSI > 55
WEAK_TREND_USE_VOLUME = True
WEAK_TREND_VOLUME_THRESHOLD = 0.6  # Lower volume requirement

# === STRONG TREND FILTERS (ADX >= 45) ===
# Use MINIMAL filters - let trades through, strong trends dominate
STRONG_TREND_USE_RSI = False       # Disable RSI filter (trends override)
STRONG_TREND_RSI_OVERSOLD = 50     # Not used if disabled
STRONG_TREND_RSI_OVERBOUGHT = 50   # Not used if disabled
STRONG_TREND_USE_VOLUME = True
STRONG_TREND_VOLUME_THRESHOLD = 0.5  # Minimal volume check only

# RSI calculation period (shared across all regimes)
RSI_PERIOD = 14

# Volume lookback period (shared across all regimes)
VOLUME_LOOKBACK = 20


# =============================================================================
# DATA STRUCTURES FOR GRID MANAGEMENT
# =============================================================================

@dataclass
class GridLevel:
    """
    Represents a single grid level (horizontal line on chart)

    Attributes:
        price: Price level for this grid line
        level_type: "buy" or "sell"
        is_filled: Whether this level has been traded
        fill_price: Actual fill price if traded
        fill_timestamp: When this level was filled
        position_size: Size of position at this level
    """
    price: float
    level_type: str  # "buy" or "sell"
    is_filled: bool = False
    fill_price: Optional[float] = None
    fill_timestamp: Optional[datetime] = None
    position_size: float = 0.0

    def __repr__(self) -> str:
        status = "FILLED" if self.is_filled else "PENDING"
        return f"GridLevel({self.level_type.upper()} @ ${self.price:.2f} [{status}])"


@dataclass
class GridState:
    """
    Tracks the current state of the entire grid

    Attributes:
        mid_price: Center price of the grid
        grid_levels: List of all grid levels (buy and sell)
        active_positions: Count of currently open positions
        average_entry_price: Average entry price across all positions
        total_position_size: Total size across all positions
        grid_pnl: Profit/loss for current grid
        last_rebalance_price: Price at last grid rebalance
        rebalance_count: Number of times grid has been rebalanced
    """
    mid_price: float
    grid_levels: List[GridLevel]
    active_positions: int = 0
    average_entry_price: Optional[float] = None
    total_position_size: float = 0.0
    grid_pnl: float = 0.0
    last_rebalance_price: Optional[float] = None
    rebalance_count: int = 0

    def get_buy_levels(self) -> List[GridLevel]:
        """Get all buy levels (below mid-price)"""
        return [lvl for lvl in self.grid_levels if lvl.level_type == "buy"]

    def get_sell_levels(self) -> List[GridLevel]:
        """Get all sell levels (above mid-price)"""
        return [lvl for lvl in self.grid_levels if lvl.level_type == "sell"]

    def get_unfilled_levels(self) -> List[GridLevel]:
        """Get levels that haven't been traded yet"""
        return [lvl for lvl in self.grid_levels if not lvl.is_filled]

    def get_nearest_unfilled_buy(self, current_price: float) -> Optional[GridLevel]:
        """Get nearest unfilled buy level below current price"""
        buy_levels = [lvl for lvl in self.get_buy_levels()
                     if not lvl.is_filled and lvl.price <= current_price]
        return max(buy_levels, key=lambda x: x.price) if buy_levels else None

    def get_nearest_unfilled_sell(self, current_price: float) -> Optional[GridLevel]:
        """Get nearest unfilled sell level above current price"""
        sell_levels = [lvl for lvl in self.get_sell_levels()
                      if not lvl.is_filled and lvl.price >= current_price]
        return min(sell_levels, key=lambda x: x.price) if sell_levels else None


# =============================================================================
# GRID TRADING STRATEGY CLASS
# =============================================================================

class GridTradingStrategy(StrategyBase):
    """
    Grid Trading Strategy Implementation

    Creates a grid of buy/sell orders around current price and profits
    from price oscillations. Automatically rebalances grid when price
    moves significantly.

    Best suited for:
    - Ranging/sideways markets
    - High volatility environments
    - Mean-reverting assets

    Parameters:
        symbol: Trading pair symbol
        grid_levels: Number of grid levels (default: 10)
        grid_range_pct: Grid range as % of mid-price (default: 0.10 = ±10%)
        use_atr_spacing: Use ATR for dynamic spacing (default: True)
        max_positions: Maximum concurrent positions (default: 5)
        position_size_pct: Position size as % of equity (default: 0.02 = 2%)
    """

    def __init__(
        self,
        symbol: str,
        grid_levels: int = DEFAULT_GRID_LEVELS,
        grid_range_pct: float = DEFAULT_GRID_RANGE_PCT,
        use_atr_spacing: bool = USE_ATR_SPACING,
        max_positions: int = MAX_CONCURRENT_POSITIONS,
        position_size_pct: float = POSITION_SIZE_PCT,
    ):
        # Set attributes BEFORE calling super().__init__
        self.grid_levels = grid_levels
        self.grid_range_pct = grid_range_pct
        self.use_atr_spacing = use_atr_spacing
        self.max_positions = max_positions
        self.position_size_pct = position_size_pct

        # Initialize grid state
        self.grid_state: Optional[GridState] = None
        self._prev_price: Optional[float] = None
        self._grid_initialized: bool = False

        # Performance tracking
        self._total_trades: int = 0
        self._winning_trades: int = 0
        self._total_pnl: float = 0.0

        # Call parent constructor
        super().__init__(symbol, {
            "grid_levels": grid_levels,
            "grid_range_pct": grid_range_pct,
            "use_atr_spacing": use_atr_spacing,
            "max_positions": max_positions,
            "position_size_pct": position_size_pct,
        })

        logger.info(
            f"GridTradingStrategy initialized: {grid_levels} levels, "
            f"±{grid_range_pct*100}% range, max {max_positions} positions"
        )

    def get_name(self) -> str:
        """Return strategy name"""
        return f"Grid_Trading_{self.grid_levels}lvl"

    # ==========================================================================
    # FILTER HELPER METHODS (from Enhanced v2 learnings)
    # ==========================================================================

    def _calculate_adx(self, period: int = ADX_FILTER_PERIOD) -> float:
        """
        Calculate ADX (Average Directional Index) to detect market regime

        ADX < 20 = ranging/weak trend (optimal for grid trading)
        ADX > 20 = trending (grid trading may perform poorly)

        Args:
            period: Lookback period for ADX calculation

        Returns:
            ADX value (0-100), or 0.0 if insufficient data
        """
        if len(self._prices) < period + 1:
            return 0.0

        # Get recent price data from stored lists
        highs = np.array(self._highs[-(period + 1):])
        lows = np.array(self._lows[-(period + 1):])
        closes = np.array(self._prices[-(period + 1):])

        # Calculate True Range components
        high_low = highs[1:] - lows[1:]
        high_close = np.abs(highs[1:] - closes[:-1])
        low_close = np.abs(lows[1:] - closes[:-1])
        true_range = np.maximum(high_low, np.maximum(high_close, low_close))

        # Calculate +DM and -DM (directional movement)
        plus_dm = np.where(
            (highs[1:] - highs[:-1]) > (lows[:-1] - lows[1:]),
            np.maximum(highs[1:] - highs[:-1], 0),
            0
        )
        minus_dm = np.where(
            (lows[:-1] - lows[1:]) > (highs[1:] - highs[:-1]),
            np.maximum(lows[:-1] - lows[1:], 0),
            0
        )

        # Calculate smoothed ATR
        atr = np.mean(true_range)
        if atr == 0:
            return 0.0

        # Calculate +DI and -DI (directional indicators)
        plus_di = 100 * np.mean(plus_dm) / atr
        minus_di = 100 * np.mean(minus_dm) / atr

        # Calculate DX (Directional Index)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)

        # ADX is smoothed DX (simplified to mean for performance)
        adx = dx

        return adx

    def _calculate_rsi(self, period: int = RSI_PERIOD) -> float:
        """
        Calculate RSI (Relative Strength Index) for entry timing

        RSI < 30 = oversold (good time to buy)
        RSI > 70 = overbought (good time to sell)

        Args:
            period: Lookback period for RSI calculation

        Returns:
            RSI value (0-100), or 50.0 if insufficient data
        """
        if len(self._prices) < period + 1:
            return 50.0  # Neutral RSI if not enough data

        # Get price changes
        prices = np.array(self._prices[-(period + 1):])
        deltas = np.diff(prices)

        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Calculate average gain and loss
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)

        # Avoid division by zero
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0

        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _check_volume_confirmation(self, current_volume: float) -> bool:
        """
        Check if current volume is sufficient for trade confirmation

        Requires volume > 0.8x recent average to confirm trades
        This ensures sufficient liquidity and reduces false signals

        Args:
            current_volume: Current bar's volume

        Returns:
            True if volume confirms trade, False otherwise
        """
        if len(self._volumes) < VOLUME_LOOKBACK:
            return True  # Allow trades if not enough volume history

        # Calculate recent average volume
        recent_volumes = self._volumes[-VOLUME_LOOKBACK:]
        avg_volume = np.mean(recent_volumes)

        # Check if current volume meets threshold
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

        return volume_ratio >= VOLUME_THRESHOLD

    # ==========================================================================
    # MAIN STRATEGY LOGIC
    # ==========================================================================

    def on_bar(self, bar: OHLCV, equity: float) -> Optional[Signal]:
        """
        Process new bar and generate grid trading signals

        Args:
            bar: Current OHLCV bar
            equity: Current account equity

        Returns:
            Signal if action should be taken, None otherwise
        """
        current_price = bar.close

        # Need enough data for ATR calculation
        if len(self._prices) < ATR_PERIOD + 1:
            self._prev_price = current_price
            return None

        # Initialize grid on first valid bar
        if not self._grid_initialized:
            self._initialize_grid(current_price, bar.timestamp)
            self._prev_price = current_price
            return None

        # Generate trading signal BEFORE rebalancing (so we don't miss opportunities)
        signal = self._generate_grid_signal(bar, equity)

        # Check if grid needs rebalancing AFTER signal generation
        if self._should_rebalance_grid(current_price):
            logger.info(f"Rebalancing grid at price ${current_price:.2f}")
            self._rebalance_grid(current_price, bar.timestamp)

        # Update previous price for next bar
        self._prev_price = current_price
        return signal

    def _initialize_grid(self, mid_price: float, timestamp: datetime) -> None:
        """
        Initialize the trading grid around current price

        Args:
            mid_price: Current market price (grid center)
            timestamp: Current timestamp
        """
        logger.info(f"Initializing grid at mid-price ${mid_price:.2f}")

        # Calculate grid spacing
        if self.use_atr_spacing:
            atr = self.atr(ATR_PERIOD)
            if atr is None:
                # Fallback to percentage-based spacing
                grid_spacing = mid_price * (self.grid_range_pct / self.grid_levels)
                logger.warning("ATR unavailable, using percentage spacing")
            else:
                grid_spacing = atr * ATR_GRID_MULTIPLIER
                logger.info(f"Using ATR-based spacing: ${grid_spacing:.2f} ({atr:.2f} ATR)")
        else:
            # Fixed percentage spacing
            grid_spacing = mid_price * (self.grid_range_pct / self.grid_levels)

        # Create grid levels
        grid_levels = self._create_grid_levels(mid_price, grid_spacing)

        # Initialize grid state
        self.grid_state = GridState(
            mid_price=mid_price,
            grid_levels=grid_levels,
            last_rebalance_price=mid_price,
        )

        self._grid_initialized = True

        logger.info(
            f"Grid initialized: {len(grid_levels)} levels, "
            f"range ${min(lvl.price for lvl in grid_levels):.2f} - "
            f"${max(lvl.price for lvl in grid_levels):.2f}"
        )

    def _create_grid_levels(
        self,
        mid_price: float,
        spacing: float
    ) -> List[GridLevel]:
        """
        Create grid levels with specified spacing

        Args:
            mid_price: Center price for grid
            spacing: Distance between grid levels

        Returns:
            List of GridLevel objects
        """
        levels = []
        num_levels_per_side = self.grid_levels // 2

        if GRID_SPACING_TYPE == "arithmetic":
            # Arithmetic spacing (equal price intervals)
            for i in range(1, num_levels_per_side + 1):
                # Buy levels (below mid-price)
                buy_price = mid_price - (spacing * i)
                levels.append(GridLevel(price=buy_price, level_type="buy"))

                # Sell levels (above mid-price)
                sell_price = mid_price + (spacing * i)
                levels.append(GridLevel(price=sell_price, level_type="sell"))

        else:  # geometric spacing
            # Geometric spacing (equal percentage intervals)
            spacing_pct = spacing / mid_price

            for i in range(1, num_levels_per_side + 1):
                # Buy levels (below mid-price)
                buy_price = mid_price * ((1 - spacing_pct) ** i)
                levels.append(GridLevel(price=buy_price, level_type="buy"))

                # Sell levels (above mid-price)
                sell_price = mid_price * ((1 + spacing_pct) ** i)
                levels.append(GridLevel(price=sell_price, level_type="sell"))

        # Sort by price
        levels.sort(key=lambda x: x.price)

        return levels

    def _should_rebalance_grid(self, current_price: float) -> bool:
        """
        Check if grid should be rebalanced

        Grid rebalances when:
        1. Price moves >80% through grid range
        2. Price moves >3% from last rebalance

        Args:
            current_price: Current market price

        Returns:
            True if grid should be rebalanced
        """
        if self.grid_state is None:
            return False

        # Get grid boundaries
        grid_low = min(lvl.price for lvl in self.grid_state.grid_levels)
        grid_high = max(lvl.price for lvl in self.grid_state.grid_levels)
        grid_range = grid_high - grid_low

        # Check if price is near grid boundaries (>80% through range)
        price_position = (current_price - grid_low) / grid_range if grid_range > 0 else 0.5

        if price_position > REBALANCE_THRESHOLD or price_position < (1 - REBALANCE_THRESHOLD):
            logger.info(f"Price at {price_position*100:.1f}% of grid range - rebalancing")
            return True

        # Check if price has moved significantly from last rebalance
        if self.grid_state.last_rebalance_price is not None:
            price_change_pct = abs(
                (current_price - self.grid_state.last_rebalance_price) /
                self.grid_state.last_rebalance_price
            )

            if price_change_pct > MIN_PRICE_MOVE_FOR_REBALANCE:
                logger.info(f"Price moved {price_change_pct*100:.1f}% - rebalancing")
                return True

        return False

    def _rebalance_grid(self, new_mid_price: float, timestamp: datetime) -> None:
        """
        Rebalance grid around new mid-price

        Closes all positions and re-initializes grid

        Args:
            new_mid_price: New center price for grid
            timestamp: Current timestamp
        """
        if self.grid_state is not None:
            # Calculate PnL from old grid
            old_pnl = self._calculate_grid_pnl(new_mid_price)
            self._total_pnl += old_pnl

            logger.info(
                f"Grid #{self.grid_state.rebalance_count} PnL: ${old_pnl:.2f} "
                f"(Total: ${self._total_pnl:.2f})"
            )

            # Increment rebalance counter
            rebalance_count = self.grid_state.rebalance_count + 1
        else:
            rebalance_count = 0

        # Re-initialize grid
        self._initialize_grid(new_mid_price, timestamp)

        if self.grid_state is not None:
            self.grid_state.rebalance_count = rebalance_count

    def _calculate_grid_pnl(self, current_price: float) -> float:
        """
        Calculate profit/loss for current grid

        Args:
            current_price: Current market price

        Returns:
            Grid PnL in dollars
        """
        if self.grid_state is None or self.grid_state.average_entry_price is None:
            return 0.0

        # Calculate unrealized PnL
        unrealized_pnl = (
            (current_price - self.grid_state.average_entry_price) *
            self.grid_state.total_position_size
        )

        return self.grid_state.grid_pnl + unrealized_pnl

    def _generate_grid_signal(self, bar: OHLCV, equity: float) -> Optional[Signal]:
        """
        Generate buy/sell signal based on grid levels

        Args:
            bar: Current OHLCV bar
            equity: Current account equity

        Returns:
            Signal if grid level crossed, None otherwise
        """
        if self.grid_state is None or self._prev_price is None:
            return None

        current_price = bar.close

        # Check for buy signal (price crossed below a buy level)
        if current_price <= self._prev_price:
            # Find ALL unfilled buy levels that were crossed
            buy_levels = self.grid_state.get_buy_levels()
            crossed_buy_levels = [
                lvl for lvl in buy_levels
                if not lvl.is_filled and self._prev_price >= lvl.price >= current_price
            ]

            if crossed_buy_levels:
                # Pick the highest crossed level (closest to current price)
                buy_level = max(crossed_buy_levels, key=lambda x: x.price)

                # Check if we can add more positions
                if self.grid_state.active_positions < self.max_positions:
                    # === MARKET-ADAPTIVE FILTERS V2 ===
                    # Apply different filter strategies based on market regime

                    if USE_ADAPTIVE_FILTERS:
                        # Step 1: Calculate ADX to determine market regime
                        adx = self._calculate_adx()

                        # Step 2: Determine market regime and select appropriate filters
                        if adx < ADX_RANGING_THRESHOLD:
                            # RANGING MARKET - Use STRICT filters
                            market_regime = "RANGING"
                            use_rsi = RANGING_USE_RSI
                            rsi_threshold = RANGING_RSI_OVERSOLD
                            use_volume = RANGING_USE_VOLUME
                            volume_threshold = RANGING_VOLUME_THRESHOLD

                        elif adx < ADX_WEAK_TREND_THRESHOLD:
                            # WEAK TREND - Use MODERATE filters
                            market_regime = "WEAK_TREND"
                            use_rsi = WEAK_TREND_USE_RSI
                            rsi_threshold = WEAK_TREND_RSI_OVERSOLD
                            use_volume = WEAK_TREND_USE_VOLUME
                            volume_threshold = WEAK_TREND_VOLUME_THRESHOLD

                        else:
                            # STRONG TREND - Use MINIMAL filters
                            market_regime = "STRONG_TREND"
                            use_rsi = STRONG_TREND_USE_RSI
                            rsi_threshold = STRONG_TREND_RSI_OVERSOLD
                            use_volume = STRONG_TREND_USE_VOLUME
                            volume_threshold = STRONG_TREND_VOLUME_THRESHOLD

                        logger.debug(f"Market regime: {market_regime} (ADX={adx:.1f})")

                        # Step 3: Apply RSI filter if enabled for this regime
                        if use_rsi:
                            rsi = self._calculate_rsi()
                            if rsi >= rsi_threshold:
                                logger.debug(f"RSI filter blocked BUY in {market_regime}: RSI {rsi:.1f} >= {rsi_threshold}")
                                return None

                        # Step 4: Apply volume filter if enabled for this regime
                        if use_volume:
                            volume_ratio = bar.volume / np.mean(self._volumes[-VOLUME_LOOKBACK:]) if len(self._volumes) >= VOLUME_LOOKBACK else 1.0
                            if volume_ratio < volume_threshold:
                                logger.debug(f"Volume filter blocked BUY in {market_regime}: ratio {volume_ratio:.2f} < {volume_threshold}")
                                return None

                    # All filters passed - create buy signal
                    return self._create_buy_signal(bar, buy_level, equity)
                else:
                    logger.debug(f"Max positions ({self.max_positions}) reached, skipping buy")

        # Check for sell signal (price crossed above a sell level)
        elif current_price >= self._prev_price:
            # Find ALL unfilled sell levels that were crossed
            sell_levels = self.grid_state.get_sell_levels()
            crossed_sell_levels = [
                lvl for lvl in sell_levels
                if not lvl.is_filled and self._prev_price <= lvl.price <= current_price
            ]

            if crossed_sell_levels:
                # Pick the lowest crossed level (closest to current price)
                sell_level = min(crossed_sell_levels, key=lambda x: x.price)

                # Check if we have positions to sell
                if self.grid_state.active_positions > 0:
                    # === MARKET-ADAPTIVE FILTERS V2 FOR SELL ===
                    # Apply different filter strategies based on market regime

                    if USE_ADAPTIVE_FILTERS:
                        # Step 1: Calculate ADX to determine market regime
                        adx = self._calculate_adx()

                        # Step 2: Determine market regime and select appropriate filters
                        if adx < ADX_RANGING_THRESHOLD:
                            # RANGING MARKET - Use STRICT filters
                            market_regime = "RANGING"
                            use_rsi = RANGING_USE_RSI
                            rsi_threshold = RANGING_RSI_OVERBOUGHT
                            use_volume = RANGING_USE_VOLUME
                            volume_threshold = RANGING_VOLUME_THRESHOLD

                        elif adx < ADX_WEAK_TREND_THRESHOLD:
                            # WEAK TREND - Use MODERATE filters
                            market_regime = "WEAK_TREND"
                            use_rsi = WEAK_TREND_USE_RSI
                            rsi_threshold = WEAK_TREND_RSI_OVERBOUGHT
                            use_volume = WEAK_TREND_USE_VOLUME
                            volume_threshold = WEAK_TREND_VOLUME_THRESHOLD

                        else:
                            # STRONG TREND - Use MINIMAL filters
                            market_regime = "STRONG_TREND"
                            use_rsi = STRONG_TREND_USE_RSI
                            rsi_threshold = STRONG_TREND_RSI_OVERBOUGHT
                            use_volume = STRONG_TREND_USE_VOLUME
                            volume_threshold = STRONG_TREND_VOLUME_THRESHOLD

                        logger.debug(f"Market regime: {market_regime} (ADX={adx:.1f})")

                        # Step 3: Apply RSI filter if enabled for this regime
                        if use_rsi:
                            rsi = self._calculate_rsi()
                            if rsi <= rsi_threshold:
                                logger.debug(f"RSI filter blocked SELL in {market_regime}: RSI {rsi:.1f} <= {rsi_threshold}")
                                return None

                        # Step 4: Apply volume filter if enabled for this regime
                        if use_volume:
                            volume_ratio = bar.volume / np.mean(self._volumes[-VOLUME_LOOKBACK:]) if len(self._volumes) >= VOLUME_LOOKBACK else 1.0
                            if volume_ratio < volume_threshold:
                                logger.debug(f"Volume filter blocked SELL in {market_regime}: ratio {volume_ratio:.2f} < {volume_threshold}")
                                return None

                    # All filters passed - create sell signal
                    return self._create_sell_signal(bar, sell_level)
                else:
                    logger.debug("No positions to sell")

        # Check for stop loss
        if self.has_position():
            stop_signal = self._check_stop_loss(bar)
            if stop_signal is not None:
                return stop_signal

        return None

    def _create_buy_signal(
        self,
        bar: OHLCV,
        grid_level: GridLevel,
        equity: float
    ) -> Signal:
        """
        Create BUY signal for grid level

        Args:
            bar: Current OHLCV bar
            grid_level: Grid level being traded
            equity: Current account equity

        Returns:
            Buy Signal
        """
        # Calculate position size
        position_value = equity * self.position_size_pct
        position_value = max(position_value, MIN_POSITION_VALUE)

        # Calculate ATR for stop loss
        current_atr = self.atr(ATR_PERIOD)
        if current_atr is None:
            current_atr = bar.close * 0.02  # Fallback to 2% of price

        # Set stop loss
        stop_loss = bar.close - (current_atr * INDIVIDUAL_STOP_MULTIPLIER)

        # Set take profit at next sell level
        take_profit = None
        sell_levels = self.grid_state.get_sell_levels() if self.grid_state else []
        if sell_levels:
            next_sell = min([lvl for lvl in sell_levels if lvl.price > bar.close],
                          key=lambda x: x.price, default=None)
            if next_sell:
                take_profit = next_sell.price

        # Calculate confidence based on volatility
        confidence = BUY_CONFIDENCE_BASE
        if current_atr and bar.close > 0:
            atr_pct = current_atr / bar.close
            if atr_pct > 0.03:  # High volatility (>3%)
                confidence += CONFIDENCE_BOOST_VOLATILITY

        # Mark grid level as filled
        grid_level.is_filled = True
        grid_level.fill_price = bar.close
        grid_level.fill_timestamp = bar.timestamp
        grid_level.position_size = position_value / bar.close

        # Update grid state
        if self.grid_state:
            self.grid_state.active_positions += 1
            self.grid_state.total_position_size += grid_level.position_size

            # Update average entry price
            if self.grid_state.average_entry_price is None:
                self.grid_state.average_entry_price = bar.close
            else:
                total_value = self.grid_state.average_entry_price * (
                    self.grid_state.total_position_size - grid_level.position_size
                )
                total_value += bar.close * grid_level.position_size
                self.grid_state.average_entry_price = (
                    total_value / self.grid_state.total_position_size
                )

        logger.info(
            f"GRID BUY: Level ${grid_level.price:.2f}, Size: {position_value:.2f}, "
            f"Active: {self.grid_state.active_positions if self.grid_state else 0}/{self.max_positions}"
        )

        return Signal(
            signal_type=SignalType.BUY,
            symbol=self.symbol,
            price=bar.close,
            timestamp=bar.timestamp,
            confidence=confidence,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size_pct=self.position_size_pct,
            metadata={
                "strategy": "grid_trading",
                "grid_level": grid_level.price,
                "active_positions": self.grid_state.active_positions if self.grid_state else 0,
                "atr": current_atr,
            }
        )

    def _create_sell_signal(self, bar: OHLCV, grid_level: GridLevel) -> Signal:
        """
        Create SELL signal for grid level

        Args:
            bar: Current OHLCV bar
            grid_level: Grid level being traded

        Returns:
            Sell Signal (close long position)
        """
        # Mark grid level as filled
        grid_level.is_filled = True
        grid_level.fill_price = bar.close
        grid_level.fill_timestamp = bar.timestamp

        # Calculate PnL for this trade
        if self.grid_state and self.grid_state.average_entry_price:
            trade_pnl = (bar.close - self.grid_state.average_entry_price) * (
                self.grid_state.total_position_size / self.grid_state.active_positions
            )

            if trade_pnl > 0:
                self._winning_trades += 1

            self._total_trades += 1
            self.grid_state.grid_pnl += trade_pnl

            # Update grid state
            self.grid_state.active_positions -= 1
            position_size_reduction = self.grid_state.total_position_size / (
                self.grid_state.active_positions + 1
            )
            self.grid_state.total_position_size -= position_size_reduction

            logger.info(
                f"GRID SELL: Level ${grid_level.price:.2f}, PnL: ${trade_pnl:.2f}, "
                f"Remaining: {self.grid_state.active_positions}"
            )

        return Signal(
            signal_type=SignalType.CLOSE_LONG,
            symbol=self.symbol,
            price=bar.close,
            timestamp=bar.timestamp,
            confidence=SELL_CONFIDENCE_BASE,
            metadata={
                "strategy": "grid_trading",
                "grid_level": grid_level.price,
                "exit_reason": "grid_level_hit",
                "active_positions": self.grid_state.active_positions if self.grid_state else 0,
            }
        )

    def _check_stop_loss(self, bar: OHLCV) -> Optional[Signal]:
        """
        Check if grid-wide stop loss is hit

        Args:
            bar: Current OHLCV bar

        Returns:
            Close signal if stop hit, None otherwise
        """
        if self.grid_state is None or self.grid_state.average_entry_price is None:
            return None

        # Calculate current drawdown
        drawdown_pct = (
            (self.grid_state.average_entry_price - bar.close) /
            self.grid_state.average_entry_price
        )

        if drawdown_pct > GRID_STOP_LOSS_PCT:
            logger.warning(
                f"Grid stop loss hit! Drawdown: {drawdown_pct*100:.1f}% "
                f"(max: {GRID_STOP_LOSS_PCT*100:.1f}%)"
            )

            return Signal(
                signal_type=SignalType.CLOSE_LONG,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                confidence=1.0,
                metadata={
                    "strategy": "grid_trading",
                    "exit_reason": "grid_stop_loss",
                    "drawdown_pct": drawdown_pct,
                }
            )

        return None

    def on_end(self, final_equity: float) -> None:
        """Called at backtest end - log final statistics"""
        super().on_end(final_equity)

        if self._total_trades > 0:
            win_rate = (self._winning_trades / self._total_trades) * 100
            logger.info(
                f"\n{'='*60}\n"
                f"Grid Trading Final Statistics:\n"
                f"  Total Trades: {self._total_trades}\n"
                f"  Winning Trades: {self._winning_trades}\n"
                f"  Win Rate: {win_rate:.1f}%\n"
                f"  Total PnL: ${self._total_pnl:.2f}\n"
                f"  Average PnL/Trade: ${self._total_pnl/self._total_trades:.2f}\n"
                f"  Grid Rebalances: {self.grid_state.rebalance_count if self.grid_state else 0}\n"
                f"{'='*60}"
            )
