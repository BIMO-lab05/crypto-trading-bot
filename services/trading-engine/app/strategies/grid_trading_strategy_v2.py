"""
Grid Trading Strategy V2 - Dynamic Grid Trading for Range-Bound Markets
=========================================================================
Purpose: Enhanced grid trading with dynamic grid levels, volatility-adaptive
spacing, and comprehensive risk management for range-bound market conditions.

Key Features:
1. **Dynamic Grid Creation**:
   - Calculate grid levels based on ATR or Bollinger Bands
   - Adjust grid spacing based on market volatility
   - Support both fixed and percentage-based grids
   - Geometric spacing for better distribution in volatile markets

2. **Position Management**:
   - Track individual grid positions with full metadata
   - Manage multiple open orders across grid levels
   - Partial fills and grid level completion tracking
   - Position pyramid rules with profitability checks

3. **Risk Management**:
   - Total exposure limits across all grid levels
   - Stop-loss for entire grid if market breaks range
   - Maximum position size per grid level
   - Drawdown protection with auto-pause

4. **Grid Optimization**:
   - Detect range-bound vs trending markets using ADX
   - Pause grid in strong trends (ADX > threshold)
   - Rebalance grid levels during consolidation
   - Dynamic profit targets based on grid spacing

5. **Market Regime Detection**:
   - ADX-based trend strength detection
   - Bollinger Band squeeze detection for consolidation
   - Volume confirmation for breakout detection
   - Automatic strategy pause during unfavorable conditions

Research Citations:
- Grid Trading: Systematic approach to range-bound markets (Chan, 2009)
- ADX trend filtering: J. Welles Wilder, "New Concepts in Technical Trading"
- Bollinger Bands: John Bollinger, "Bollinger on Bollinger Bands" (2001)
- Volatility-adjusted stops: ATR methodology (Wilder, 1978)
- Position sizing: Van Tharp's risk management principles

Author: Phase 2.3 - Grid Trading Implementation
Date: 2025-12-11
Version: 2.0.0
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import uuid

import numpy as np

# Import base strategy class from existing framework
from app.backtesting.strategy_base import (
    StrategyBase,
    Signal,
    SignalType,
    OHLCV,
)

# Configure module logger
logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION CONSTANTS - Grid Trading V2
# =============================================================================


# Grid Construction Parameters
class GridSpacingType(Enum):
    """Grid spacing calculation method"""

    ARITHMETIC = "arithmetic"  # Equal price intervals
    GEOMETRIC = "geometric"  # Equal percentage intervals
    ATR_BASED = "atr_based"  # Based on ATR volatility
    BOLLINGER = "bollinger"  # Based on Bollinger Bands


# Default Grid Settings
DEFAULT_GRID_LEVELS = 10  # Total grid levels (5 buy + 5 sell)
DEFAULT_GRID_RANGE_PCT = 0.08  # +/- 8% from mid-price
DEFAULT_SPACING_TYPE = GridSpacingType.ATR_BASED
MIN_GRID_SPACING_PCT = 0.005  # Minimum 0.5% between levels
MAX_GRID_SPACING_PCT = 0.05  # Maximum 5% between levels

# ATR-Based Spacing Configuration
ATR_PERIOD = 14  # Period for ATR calculation
ATR_GRID_MULTIPLIER = 1.0  # Grid spacing = ATR * multiplier
ATR_LOOKBACK_BARS = 100  # Bars to consider for ATR

# Bollinger Band Configuration
BB_PERIOD = 20  # Period for Bollinger Bands
BB_STD_DEV = 2.0  # Standard deviations for bands
BB_GRID_COVERAGE = 0.80  # Use 80% of BB range for grid

# Position Management
MAX_CONCURRENT_POSITIONS = 5  # Maximum open positions across all levels
POSITION_SIZE_PCT = 0.02  # 2% of equity per position
MIN_POSITION_VALUE_USD = 10.0  # Minimum $10 per position
MAX_POSITION_VALUE_USD = 10000.0  # Maximum $10k per position

# Grid Rebalancing Triggers
REBALANCE_THRESHOLD_PCT = 0.80  # Rebalance when price moves 80% through grid
MIN_PRICE_MOVE_FOR_REBALANCE = 0.05  # Minimum 5% price move to trigger rebalance
MIN_TIME_BETWEEN_REBALANCES = 3600  # Minimum 1 hour between rebalances (seconds)
REBALANCE_ON_VOLATILITY_CHANGE = True  # Rebalance if volatility changes significantly

# Risk Management - Grid Level
INDIVIDUAL_STOP_ATR_MULT = 1.5  # Individual position stop at 1.5x ATR
INDIVIDUAL_TP_ATR_MULT = 1.0  # Individual position TP at 1x ATR (next grid level)
MAX_LOSS_PER_LEVEL_PCT = 0.02  # Max 2% loss per grid level

# Risk Management - Grid Wide
GRID_STOP_LOSS_PCT = 0.05  # Stop entire grid at 5% loss from avg entry
GRID_MAX_DRAWDOWN_PCT = 0.10  # Reset grid at 10% max drawdown
MAX_TOTAL_EXPOSURE_PCT = 0.20  # Maximum 20% of equity across all positions
EMERGENCY_EXIT_LOSS_PCT = 0.15  # Emergency exit all positions at 15% loss

# Market Regime Detection
ADX_PERIOD = 14  # Period for ADX calculation
ADX_RANGING_THRESHOLD = 25  # ADX < 25 = ranging market (favorable)
ADX_STRONG_TREND_THRESHOLD = 40  # ADX > 40 = strong trend (unfavorable)
TREND_PAUSE_THRESHOLD = 30  # Pause grid when ADX > 30
BB_SQUEEZE_THRESHOLD = 0.02  # BB width < 2% = squeeze (expect breakout)

# RSI Filter for Entry Timing
RSI_PERIOD = 14  # Period for RSI calculation
RSI_OVERSOLD = 35  # Buy filter: RSI < 35
RSI_OVERBOUGHT = 65  # Sell filter: RSI > 65
USE_RSI_FILTER = True  # Enable RSI confirmation

# Volume Confirmation
VOLUME_MA_PERIOD = 20  # Period for volume moving average
VOLUME_THRESHOLD_MULT = 0.8  # Minimum 0.8x average volume for trades
USE_VOLUME_FILTER = True  # Enable volume confirmation

# Signal Confidence Calculation
BASE_BUY_CONFIDENCE = 0.65  # Base confidence for buy signals
BASE_SELL_CONFIDENCE = 0.70  # Base confidence for sell signals
CONFIDENCE_BOOST_RSI = 0.10  # Boost for extreme RSI
CONFIDENCE_BOOST_VOLUME = 0.05  # Boost for volume confirmation
CONFIDENCE_BOOST_REGIME = 0.10  # Boost for favorable market regime
MAX_CONFIDENCE = 0.95  # Cap at 95%

# Grid Performance Tracking
TRACK_LEVEL_PERFORMANCE = True  # Track performance per grid level
MIN_TRADES_FOR_STATS = 10  # Min trades for statistical significance


# =============================================================================
# DATA STRUCTURES
# =============================================================================


class MarketRegime(Enum):
    """Market regime classification for grid trading"""

    RANGING = "ranging"  # ADX < 25: Ideal for grid trading
    WEAK_TREND = "weak_trend"  # 25 <= ADX < 40: Proceed with caution
    STRONG_TREND = "strong_trend"  # ADX >= 40: Pause grid trading
    SQUEEZE = "squeeze"  # BB squeeze: Expect breakout
    UNKNOWN = "unknown"  # Insufficient data


class GridLevelStatus(Enum):
    """Status of a grid level"""

    PENDING = "pending"  # Waiting for price to reach level
    ACTIVE = "active"  # Order placed, awaiting fill
    FILLED = "filled"  # Position opened at this level
    COMPLETED = "completed"  # Position closed with profit/loss
    EXPIRED = "expired"  # Level no longer valid (grid rebalanced)


@dataclass
class GridLevelV2:
    """
    Enhanced Grid Level with comprehensive tracking

    Represents a single price level in the grid with full metadata
    for position tracking, performance analytics, and risk management.

    Attributes:
        level_id: Unique identifier for this grid level
        price: Target price for this grid level
        level_type: "buy" for lower levels, "sell" for upper levels
        level_index: Position in grid (0 = closest to mid-price)
        status: Current status of this level
        distance_from_mid_pct: Percentage distance from grid mid-price

        # Fill Information
        fill_price: Actual fill price when traded
        fill_timestamp: When the level was filled
        fill_quantity: Quantity filled at this level
        fill_value_usd: Value of fill in USD

        # Position Tracking
        stop_loss_price: Stop loss for position at this level
        take_profit_price: Take profit target
        current_pnl: Unrealized P&L for this level
        realized_pnl: Realized P&L when position closed

        # Performance Metrics
        trade_count: Number of times this level has been traded
        win_count: Number of profitable trades at this level
        total_pnl: Cumulative P&L from this level
    """

    # Core Identification
    level_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    price: float = 0.0
    level_type: str = "buy"  # "buy" or "sell"
    level_index: int = 0  # Position in grid
    status: GridLevelStatus = GridLevelStatus.PENDING
    distance_from_mid_pct: float = 0.0

    # Fill Information
    fill_price: Optional[float] = None
    fill_timestamp: Optional[datetime] = None
    fill_quantity: float = 0.0
    fill_value_usd: float = 0.0

    # Position Tracking
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    current_pnl: float = 0.0
    realized_pnl: float = 0.0

    # Performance Metrics
    trade_count: int = 0
    win_count: int = 0
    total_pnl: float = 0.0

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)

    def __repr__(self) -> str:
        """String representation of grid level"""
        return (
            f"GridLevel({self.level_type.upper()} @ ${self.price:.2f} "
            f"[{self.status.value}] PnL: ${self.total_pnl:.2f})"
        )

    def get_win_rate(self) -> float:
        """Calculate win rate for this level"""
        if self.trade_count == 0:
            return 0.0
        return (self.win_count / self.trade_count) * 100

    def update_pnl(self, current_price: float) -> None:
        """Update unrealized P&L based on current price"""
        if self.status == GridLevelStatus.FILLED and self.fill_price:
            if self.level_type == "buy":
                # Long position: profit when price goes up
                self.current_pnl = (
                    current_price - self.fill_price
                ) * self.fill_quantity
            else:
                # Short/close position: profit when price goes down
                self.current_pnl = (
                    self.fill_price - current_price
                ) * self.fill_quantity
        self.last_updated = datetime.now()

    def close_position(self, exit_price: float, exit_timestamp: datetime) -> float:
        """
        Close position at this level and calculate realized P&L

        Args:
            exit_price: Price at which position was closed
            exit_timestamp: Timestamp of exit

        Returns:
            Realized P&L for this trade
        """
        if self.fill_price is None:
            return 0.0

        # Calculate realized P&L
        if self.level_type == "buy":
            trade_pnl = (exit_price - self.fill_price) * self.fill_quantity
        else:
            trade_pnl = (self.fill_price - exit_price) * self.fill_quantity

        # Update statistics
        self.realized_pnl = trade_pnl
        self.total_pnl += trade_pnl
        self.trade_count += 1
        if trade_pnl > 0:
            self.win_count += 1

        # Update status
        self.status = GridLevelStatus.COMPLETED
        self.current_pnl = 0.0
        self.last_updated = exit_timestamp

        return trade_pnl


@dataclass
class GridStateV2:
    """
    Comprehensive grid state management

    Tracks the entire state of the grid including all levels,
    performance metrics, and risk management parameters.

    Attributes:
        grid_id: Unique identifier for this grid instance
        symbol: Trading pair symbol
        mid_price: Current center price of grid
        grid_levels: List of all grid levels

        # Grid Configuration
        num_levels: Total number of grid levels
        spacing_type: How grid spacing is calculated
        spacing_value: Current spacing between levels

        # Position Tracking
        active_positions: Count of currently open positions
        total_position_size: Sum of all position sizes
        average_entry_price: Weighted average entry price
        max_position_value: Peak position value

        # Performance Metrics
        total_trades: Number of completed trades
        winning_trades: Number of profitable trades
        total_realized_pnl: Sum of all realized P&L
        total_unrealized_pnl: Sum of all unrealized P&L
        peak_equity: Highest equity value achieved
        current_drawdown: Current drawdown from peak

        # Grid Lifecycle
        created_at: When grid was initialized
        last_rebalance: When grid was last rebalanced
        rebalance_count: Number of times rebalanced
        is_paused: Whether grid is currently paused
        pause_reason: Reason for pause if paused
    """

    # Core Identification
    grid_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    symbol: str = ""
    mid_price: float = 0.0
    grid_levels: List[GridLevelV2] = field(default_factory=list)

    # Grid Configuration
    num_levels: int = DEFAULT_GRID_LEVELS
    spacing_type: GridSpacingType = DEFAULT_SPACING_TYPE
    spacing_value: float = 0.0
    upper_boundary: float = 0.0
    lower_boundary: float = 0.0

    # Position Tracking
    active_positions: int = 0
    total_position_size: float = 0.0
    average_entry_price: Optional[float] = None
    max_position_value: float = 0.0

    # Performance Metrics
    total_trades: int = 0
    winning_trades: int = 0
    total_realized_pnl: float = 0.0
    total_unrealized_pnl: float = 0.0
    peak_equity: float = 0.0
    current_drawdown: float = 0.0

    # Grid Lifecycle
    created_at: datetime = field(default_factory=datetime.now)
    last_rebalance: Optional[datetime] = None
    rebalance_count: int = 0
    is_paused: bool = False
    pause_reason: Optional[str] = None

    # Market Regime
    current_regime: MarketRegime = MarketRegime.UNKNOWN
    last_regime_check: Optional[datetime] = None

    def get_buy_levels(self) -> List[GridLevelV2]:
        """Get all buy levels (below mid-price), sorted by price descending"""
        return sorted(
            [lvl for lvl in self.grid_levels if lvl.level_type == "buy"],
            key=lambda x: x.price,
            reverse=True,
        )

    def get_sell_levels(self) -> List[GridLevelV2]:
        """Get all sell levels (above mid-price), sorted by price ascending"""
        return sorted(
            [lvl for lvl in self.grid_levels if lvl.level_type == "sell"],
            key=lambda x: x.price,
        )

    def get_active_levels(self) -> List[GridLevelV2]:
        """Get all levels with open positions"""
        return [lvl for lvl in self.grid_levels if lvl.status == GridLevelStatus.FILLED]

    def get_pending_buy_levels(self) -> List[GridLevelV2]:
        """Get unfilled buy levels"""
        return [
            lvl
            for lvl in self.get_buy_levels()
            if lvl.status == GridLevelStatus.PENDING
        ]

    def get_pending_sell_levels(self) -> List[GridLevelV2]:
        """Get unfilled sell levels"""
        return [
            lvl
            for lvl in self.get_sell_levels()
            if lvl.status == GridLevelStatus.PENDING
        ]

    def get_nearest_buy_level(self, current_price: float) -> Optional[GridLevelV2]:
        """Get nearest pending buy level below current price"""
        pending_buys = [
            lvl for lvl in self.get_pending_buy_levels() if lvl.price <= current_price
        ]
        return pending_buys[0] if pending_buys else None

    def get_nearest_sell_level(self, current_price: float) -> Optional[GridLevelV2]:
        """Get nearest pending sell level above current price"""
        pending_sells = [
            lvl for lvl in self.get_pending_sell_levels() if lvl.price >= current_price
        ]
        return pending_sells[0] if pending_sells else None

    def get_win_rate(self) -> float:
        """Calculate overall win rate"""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100

    def get_profit_factor(self) -> float:
        """Calculate profit factor (gross profit / gross loss)"""
        gross_profit = sum(
            lvl.total_pnl for lvl in self.grid_levels if lvl.total_pnl > 0
        )
        gross_loss = abs(
            sum(lvl.total_pnl for lvl in self.grid_levels if lvl.total_pnl < 0)
        )

        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    def update_unrealized_pnl(self, current_price: float) -> None:
        """Update unrealized P&L for all active positions"""
        total_unrealized = 0.0
        for level in self.get_active_levels():
            level.update_pnl(current_price)
            total_unrealized += level.current_pnl
        self.total_unrealized_pnl = total_unrealized

    def get_total_exposure(self) -> float:
        """Calculate total USD exposure across all positions"""
        return sum(lvl.fill_value_usd for lvl in self.get_active_levels())

    def get_grid_summary(self) -> Dict[str, Any]:
        """Get comprehensive grid summary"""
        return {
            "grid_id": self.grid_id,
            "symbol": self.symbol,
            "mid_price": self.mid_price,
            "boundaries": f"${self.lower_boundary:.2f} - ${self.upper_boundary:.2f}",
            "active_positions": self.active_positions,
            "max_positions": MAX_CONCURRENT_POSITIONS,
            "total_trades": self.total_trades,
            "win_rate": f"{self.get_win_rate():.1f}%",
            "profit_factor": f"{self.get_profit_factor():.2f}",
            "realized_pnl": f"${self.total_realized_pnl:.2f}",
            "unrealized_pnl": f"${self.total_unrealized_pnl:.2f}",
            "current_drawdown": f"{self.current_drawdown * 100:.1f}%",
            "market_regime": self.current_regime.value,
            "is_paused": self.is_paused,
            "rebalance_count": self.rebalance_count,
        }


# =============================================================================
# GRID TRADING STRATEGY V2 IMPLEMENTATION
# =============================================================================


class GridTradingStrategyV2(StrategyBase):
    """
    Enhanced Grid Trading Strategy with Dynamic Grid Levels

    This strategy creates and manages a grid of buy/sell orders around
    the current price, profiting from price oscillations in range-bound
    markets. Features include:

    1. Dynamic grid calculation based on ATR or Bollinger Bands
    2. Automatic market regime detection with ADX
    3. Volatility-adaptive grid spacing
    4. Comprehensive risk management per level and grid-wide
    5. Smart rebalancing when price moves outside grid
    6. Performance tracking per grid level

    Best Used In:
    - Ranging/sideways markets (ADX < 25)
    - High volatility environments
    - Mean-reverting assets
    - Consolidation phases

    Parameters:
        symbol: Trading pair symbol
        grid_levels: Total number of grid levels (default: 10)
        grid_range_pct: Grid range as percentage of mid-price (default: 0.08)
        spacing_type: How to calculate grid spacing (default: ATR_BASED)
        max_positions: Maximum concurrent positions (default: 5)
        position_size_pct: Position size as percentage of equity (default: 0.02)
        use_filters: Enable RSI/Volume filters (default: True)
    """

    def __init__(
        self,
        symbol: str,
        grid_levels: int = DEFAULT_GRID_LEVELS,
        grid_range_pct: float = DEFAULT_GRID_RANGE_PCT,
        spacing_type: GridSpacingType = DEFAULT_SPACING_TYPE,
        max_positions: int = MAX_CONCURRENT_POSITIONS,
        position_size_pct: float = POSITION_SIZE_PCT,
        use_filters: bool = True,
        min_atr_periods: int = ATR_PERIOD + 5,
    ):
        """
        Initialize the Grid Trading Strategy V2

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            grid_levels: Total number of grid levels to create
            grid_range_pct: Grid range as percentage (e.g., 0.08 = +/- 8%)
            spacing_type: Method for calculating grid spacing
            max_positions: Maximum allowed concurrent positions
            position_size_pct: Size of each position as % of equity
            use_filters: Whether to use RSI and volume filters
            min_atr_periods: Minimum bars needed before trading
        """
        # Store configuration before calling parent init
        self.grid_levels_count = grid_levels
        self.grid_range_pct = grid_range_pct
        self.spacing_type = spacing_type
        self.max_positions = max_positions
        self.position_size_pct = position_size_pct
        self.use_filters = use_filters
        self.min_atr_periods = min_atr_periods

        # Initialize grid state
        self.grid_state: Optional[GridStateV2] = None
        self._grid_initialized: bool = False
        self._prev_price: Optional[float] = None

        # Indicator caches
        self._atr_cache: Optional[float] = None
        self._adx_cache: Optional[float] = None
        self._rsi_cache: Optional[float] = None
        self._bb_cache: Optional[Tuple[float, float, float]] = None

        # Performance tracking
        self._session_trades: int = 0
        self._session_wins: int = 0
        self._session_pnl: float = 0.0
        self._session_start: datetime = datetime.now()

        # Initialize parent class
        super().__init__(
            symbol,
            {
                "grid_levels": grid_levels,
                "grid_range_pct": grid_range_pct,
                "spacing_type": spacing_type.value,
                "max_positions": max_positions,
                "position_size_pct": position_size_pct,
                "use_filters": use_filters,
            },
        )

        logger.info(
            f"GridTradingStrategyV2 initialized for {symbol}: "
            f"{grid_levels} levels, +/-{grid_range_pct * 100}% range, "
            f"{spacing_type.value} spacing, max {max_positions} positions"
        )

    def get_name(self) -> str:
        """Return strategy name"""
        return f"Grid_V2_{self.grid_levels_count}lvl_{self.spacing_type.value}"

    # =========================================================================
    # INDICATOR CALCULATIONS
    # =========================================================================

    def _calculate_atr(self, period: int = ATR_PERIOD) -> Optional[float]:
        """
        Calculate Average True Range (ATR) for volatility measurement

        ATR measures market volatility by calculating the average of true
        ranges over a specified period. Used for:
        - Grid spacing calculation
        - Stop loss placement
        - Position sizing

        Args:
            period: Number of bars for ATR calculation

        Returns:
            ATR value, or None if insufficient data
        """
        if len(self._prices) < period + 1:
            return None

        # Get recent price data
        highs = np.array(self._highs[-(period + 1) :])
        lows = np.array(self._lows[-(period + 1) :])
        closes = np.array(self._prices[-(period + 1) :])

        # Calculate True Range for each bar
        # TR = max(H-L, abs(H-prevC), abs(L-prevC))
        high_low = highs[1:] - lows[1:]
        high_close = np.abs(highs[1:] - closes[:-1])
        low_close = np.abs(lows[1:] - closes[:-1])

        true_ranges = np.maximum(high_low, np.maximum(high_close, low_close))

        # Calculate ATR as mean of true ranges
        atr = np.mean(true_ranges)
        self._atr_cache = atr

        return atr

    def _calculate_adx(self, period: int = ADX_PERIOD) -> float:
        """
        Calculate ADX (Average Directional Index) for trend strength

        ADX measures trend strength regardless of direction:
        - ADX < 25: Weak trend or ranging (good for grid trading)
        - 25 <= ADX < 40: Developing trend (caution for grid)
        - ADX >= 40: Strong trend (pause grid trading)

        Args:
            period: Number of bars for ADX calculation

        Returns:
            ADX value (0-100)
        """
        if len(self._prices) < period + 1:
            return 0.0

        # Get price data
        highs = np.array(self._highs[-(period + 1) :])
        lows = np.array(self._lows[-(period + 1) :])
        closes = np.array(self._prices[-(period + 1) :])

        # Calculate True Range
        high_low = highs[1:] - lows[1:]
        high_close = np.abs(highs[1:] - closes[:-1])
        low_close = np.abs(lows[1:] - closes[:-1])
        true_range = np.maximum(high_low, np.maximum(high_close, low_close))

        # Calculate +DM and -DM (Directional Movement)
        plus_dm = np.where(
            (highs[1:] - highs[:-1]) > (lows[:-1] - lows[1:]),
            np.maximum(highs[1:] - highs[:-1], 0),
            0,
        )
        minus_dm = np.where(
            (lows[:-1] - lows[1:]) > (highs[1:] - highs[:-1]),
            np.maximum(lows[:-1] - lows[1:], 0),
            0,
        )

        # Calculate ATR (Average True Range)
        atr = np.mean(true_range)
        if atr == 0:
            return 0.0

        # Calculate +DI and -DI (Directional Indicators)
        plus_di = 100 * np.mean(plus_dm) / atr
        minus_di = 100 * np.mean(minus_dm) / atr

        # Calculate DX (Directional Index)
        di_sum = plus_di + minus_di
        if di_sum == 0:
            return 0.0

        dx = 100 * abs(plus_di - minus_di) / di_sum

        # ADX is smoothed DX (simplified)
        adx = dx
        self._adx_cache = adx

        return adx

    def _calculate_rsi(self, period: int = RSI_PERIOD) -> float:
        """
        Calculate RSI (Relative Strength Index) for momentum

        RSI measures recent price changes to evaluate overbought/oversold:
        - RSI < 30: Oversold (potential buy)
        - RSI > 70: Overbought (potential sell)

        Args:
            period: Number of bars for RSI calculation

        Returns:
            RSI value (0-100)
        """
        if len(self._prices) < period + 1:
            return 50.0  # Neutral if insufficient data

        # Get price changes
        prices = np.array(self._prices[-(period + 1) :])
        deltas = np.diff(prices)

        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Calculate average gain and loss
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)

        # Handle edge cases
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0

        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        self._rsi_cache = rsi

        return rsi

    def _calculate_bollinger_bands(
        self, period: int = BB_PERIOD, std_dev: float = BB_STD_DEV
    ) -> Tuple[float, float, float]:
        """
        Calculate Bollinger Bands for grid range

        Bollinger Bands provide dynamic support/resistance levels based on
        volatility. Used for:
        - Grid boundary calculation
        - Identifying squeeze conditions
        - Dynamic grid spacing

        Args:
            period: Number of bars for calculation
            std_dev: Number of standard deviations

        Returns:
            Tuple of (upper_band, middle_band, lower_band)
        """
        if len(self._prices) < period:
            current_price = self._prices[-1] if self._prices else 0.0
            return (current_price * 1.02, current_price, current_price * 0.98)

        # Get recent prices
        prices = np.array(self._prices[-period:])

        # Calculate middle band (SMA)
        middle = np.mean(prices)

        # Calculate standard deviation
        std = np.std(prices)

        # Calculate upper and lower bands
        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)

        self._bb_cache = (upper, middle, lower)

        return (upper, middle, lower)

    def _get_volume_ratio(self, current_volume: float) -> float:
        """
        Calculate current volume relative to recent average

        Args:
            current_volume: Volume of current bar

        Returns:
            Volume ratio (current / average)
        """
        if len(self._volumes) < VOLUME_MA_PERIOD:
            return 1.0  # Assume normal volume

        avg_volume = np.mean(self._volumes[-VOLUME_MA_PERIOD:])
        if avg_volume == 0:
            return 1.0

        return current_volume / avg_volume

    # =========================================================================
    # MARKET REGIME DETECTION
    # =========================================================================

    def _detect_market_regime(self) -> MarketRegime:
        """
        Detect current market regime for grid trading optimization

        Uses multiple indicators to classify market conditions:
        - ADX for trend strength
        - Bollinger Band width for volatility/squeeze

        Returns:
            MarketRegime enum value
        """
        # Need minimum data for regime detection
        if len(self._prices) < max(ADX_PERIOD, BB_PERIOD) + 5:
            return MarketRegime.UNKNOWN

        # Calculate ADX for trend strength
        adx = self._calculate_adx()

        # Calculate BB width for volatility assessment
        upper, middle, lower = self._calculate_bollinger_bands()
        bb_width = (upper - lower) / middle if middle > 0 else 0.0

        # Check for Bollinger squeeze (low volatility, potential breakout)
        if bb_width < BB_SQUEEZE_THRESHOLD:
            return MarketRegime.SQUEEZE

        # Classify based on ADX
        if adx < ADX_RANGING_THRESHOLD:
            return MarketRegime.RANGING
        elif adx < ADX_STRONG_TREND_THRESHOLD:
            return MarketRegime.WEAK_TREND
        else:
            return MarketRegime.STRONG_TREND

    def _should_pause_grid(self, regime: MarketRegime) -> Tuple[bool, Optional[str]]:
        """
        Determine if grid trading should be paused

        Args:
            regime: Current market regime

        Returns:
            Tuple of (should_pause, reason)
        """
        # Pause in strong trends - grid trading performs poorly
        if regime == MarketRegime.STRONG_TREND:
            return True, "Strong trend detected (ADX > 40)"

        # Pause in squeeze - expect breakout
        if regime == MarketRegime.SQUEEZE:
            return True, "Bollinger squeeze detected - expecting breakout"

        # Optional: Pause in weak trend if ADX above threshold
        if regime == MarketRegime.WEAK_TREND:
            adx = self._adx_cache or 0
            if adx > TREND_PAUSE_THRESHOLD:
                return (
                    True,
                    f"Trend strengthening (ADX={adx:.1f} > {TREND_PAUSE_THRESHOLD})",
                )

        return False, None

    # =========================================================================
    # GRID MANAGEMENT
    # =========================================================================

    def _initialize_grid(
        self, current_price: float, timestamp: datetime, equity: float
    ) -> None:
        """
        Initialize the trading grid around current price

        Creates grid levels based on configured spacing type and parameters.

        Args:
            current_price: Current market price (grid center)
            timestamp: Current timestamp
            equity: Current account equity for position sizing
        """
        logger.info(f"Initializing grid at mid-price ${current_price:.2f}")

        # Calculate grid spacing based on spacing type
        spacing = self._calculate_grid_spacing(current_price)

        # Create grid levels
        grid_levels = self._create_grid_levels(current_price, spacing, timestamp)

        # Calculate grid boundaries
        buy_levels = [lvl for lvl in grid_levels if lvl.level_type == "buy"]
        sell_levels = [lvl for lvl in grid_levels if lvl.level_type == "sell"]

        lower_boundary = (
            min(lvl.price for lvl in buy_levels) if buy_levels else current_price * 0.92
        )
        upper_boundary = (
            max(lvl.price for lvl in sell_levels)
            if sell_levels
            else current_price * 1.08
        )

        # Initialize grid state
        self.grid_state = GridStateV2(
            symbol=self.symbol,
            mid_price=current_price,
            grid_levels=grid_levels,
            num_levels=len(grid_levels),
            spacing_type=self.spacing_type,
            spacing_value=spacing,
            upper_boundary=upper_boundary,
            lower_boundary=lower_boundary,
            created_at=timestamp,
            last_rebalance=timestamp,
        )

        # Detect initial market regime
        self.grid_state.current_regime = self._detect_market_regime()
        self.grid_state.last_regime_check = timestamp

        self._grid_initialized = True

        logger.info(
            f"Grid initialized: {len(grid_levels)} levels, "
            f"range ${lower_boundary:.2f} - ${upper_boundary:.2f}, "
            f"spacing ${spacing:.2f}, regime: {self.grid_state.current_regime.value}"
        )

    def _calculate_grid_spacing(self, current_price: float) -> float:
        """
        Calculate grid spacing based on configured method

        Args:
            current_price: Current market price

        Returns:
            Grid spacing value in price units
        """
        if self.spacing_type == GridSpacingType.ATR_BASED:
            # ATR-based spacing adapts to volatility
            atr = self._calculate_atr(ATR_PERIOD)
            if atr is not None and atr > 0:
                spacing = atr * ATR_GRID_MULTIPLIER
                logger.debug(f"ATR-based spacing: ${spacing:.2f} (ATR=${atr:.2f})")
                return spacing
            # Fallback to percentage if ATR unavailable
            logger.warning("ATR unavailable, falling back to percentage spacing")

        if self.spacing_type == GridSpacingType.BOLLINGER:
            # Bollinger-based uses band width for spacing
            upper, middle, lower = self._calculate_bollinger_bands()
            bb_range = upper - lower
            # Divide band range by number of levels
            spacing = (bb_range * BB_GRID_COVERAGE) / self.grid_levels_count
            logger.debug(f"Bollinger-based spacing: ${spacing:.2f}")
            return spacing

        if self.spacing_type == GridSpacingType.GEOMETRIC:
            # Geometric spacing provides equal percentage intervals
            spacing_pct = self.grid_range_pct / (self.grid_levels_count / 2)
            spacing = current_price * spacing_pct
            logger.debug(
                f"Geometric spacing: ${spacing:.2f} ({spacing_pct * 100:.2f}%)"
            )
            return spacing

        # Default: Arithmetic (fixed) spacing
        spacing = current_price * (self.grid_range_pct / (self.grid_levels_count / 2))
        logger.debug(f"Arithmetic spacing: ${spacing:.2f}")

        # Enforce min/max spacing constraints
        min_spacing = current_price * MIN_GRID_SPACING_PCT
        max_spacing = current_price * MAX_GRID_SPACING_PCT
        spacing = max(min_spacing, min(spacing, max_spacing))

        return spacing

    def _create_grid_levels(
        self, mid_price: float, spacing: float, timestamp: datetime
    ) -> List[GridLevelV2]:
        """
        Create grid levels with specified spacing

        Args:
            mid_price: Center price for grid
            spacing: Distance between grid levels
            timestamp: Creation timestamp

        Returns:
            List of GridLevelV2 objects
        """
        levels = []
        num_levels_per_side = self.grid_levels_count // 2

        # Get current ATR for stop/TP calculation
        current_atr = self._atr_cache or (mid_price * 0.02)

        if self.spacing_type == GridSpacingType.GEOMETRIC:
            # Geometric spacing (equal percentage intervals)
            spacing_pct = spacing / mid_price

            for i in range(1, num_levels_per_side + 1):
                # Buy levels (below mid-price)
                buy_price = mid_price * ((1 - spacing_pct) ** i)
                buy_level = GridLevelV2(
                    price=buy_price,
                    level_type="buy",
                    level_index=i,
                    distance_from_mid_pct=((mid_price - buy_price) / mid_price) * 100,
                    stop_loss_price=buy_price
                    - (current_atr * INDIVIDUAL_STOP_ATR_MULT),
                    created_at=timestamp,
                )
                levels.append(buy_level)

                # Sell levels (above mid-price)
                sell_price = mid_price * ((1 + spacing_pct) ** i)
                sell_level = GridLevelV2(
                    price=sell_price,
                    level_type="sell",
                    level_index=i,
                    distance_from_mid_pct=((sell_price - mid_price) / mid_price) * 100,
                    take_profit_price=sell_price,  # Sell level is the TP
                    created_at=timestamp,
                )
                levels.append(sell_level)

        else:
            # Arithmetic spacing (equal price intervals)
            for i in range(1, num_levels_per_side + 1):
                # Buy levels (below mid-price)
                buy_price = mid_price - (spacing * i)
                buy_level = GridLevelV2(
                    price=buy_price,
                    level_type="buy",
                    level_index=i,
                    distance_from_mid_pct=((mid_price - buy_price) / mid_price) * 100,
                    stop_loss_price=buy_price
                    - (current_atr * INDIVIDUAL_STOP_ATR_MULT),
                    created_at=timestamp,
                )
                levels.append(buy_level)

                # Sell levels (above mid-price)
                sell_price = mid_price + (spacing * i)
                sell_level = GridLevelV2(
                    price=sell_price,
                    level_type="sell",
                    level_index=i,
                    distance_from_mid_pct=((sell_price - mid_price) / mid_price) * 100,
                    take_profit_price=sell_price,  # Sell level is the TP
                    created_at=timestamp,
                )
                levels.append(sell_level)

        # Set take profit for buy levels (next sell level)
        buy_levels = sorted(
            [l for l in levels if l.level_type == "buy"],
            key=lambda x: x.price,
            reverse=True,
        )
        sell_levels = sorted(
            [l for l in levels if l.level_type == "sell"], key=lambda x: x.price
        )

        for buy_level in buy_levels:
            # TP is the nearest sell level above the buy price
            valid_sells = [s for s in sell_levels if s.price > buy_level.price]
            if valid_sells:
                buy_level.take_profit_price = valid_sells[0].price
            else:
                buy_level.take_profit_price = mid_price + spacing

        # Sort by price for easier management
        levels.sort(key=lambda x: x.price)

        return levels

    def _should_rebalance_grid(
        self, current_price: float, timestamp: datetime
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if grid should be rebalanced

        Grid rebalances when:
        1. Price moves outside grid boundaries
        2. Price moves >80% through grid range
        3. Volatility changes significantly
        4. Minimum time has passed since last rebalance

        Args:
            current_price: Current market price
            timestamp: Current timestamp

        Returns:
            Tuple of (should_rebalance, reason)
        """
        if self.grid_state is None:
            return False, None

        # Check minimum time between rebalances
        if self.grid_state.last_rebalance:
            time_since_rebalance = (
                timestamp - self.grid_state.last_rebalance
            ).total_seconds()
            if time_since_rebalance < MIN_TIME_BETWEEN_REBALANCES:
                return False, None

        # Check if price is outside grid boundaries
        if current_price < self.grid_state.lower_boundary:
            return (
                True,
                f"Price ${current_price:.2f} below grid boundary ${self.grid_state.lower_boundary:.2f}",
            )

        if current_price > self.grid_state.upper_boundary:
            return (
                True,
                f"Price ${current_price:.2f} above grid boundary ${self.grid_state.upper_boundary:.2f}",
            )

        # Check if price has moved significantly through the grid
        grid_range = self.grid_state.upper_boundary - self.grid_state.lower_boundary
        if grid_range > 0:
            position_in_grid = (
                current_price - self.grid_state.lower_boundary
            ) / grid_range

            if position_in_grid > REBALANCE_THRESHOLD_PCT:
                return (
                    True,
                    f"Price at {position_in_grid * 100:.1f}% of grid (upper threshold)",
                )

            if position_in_grid < (1 - REBALANCE_THRESHOLD_PCT):
                return (
                    True,
                    f"Price at {position_in_grid * 100:.1f}% of grid (lower threshold)",
                )

        # Check for significant volatility change
        if REBALANCE_ON_VOLATILITY_CHANGE:
            current_atr = self._calculate_atr()
            if current_atr and self.grid_state.spacing_value > 0:
                atr_ratio = current_atr / self.grid_state.spacing_value
                if atr_ratio > 2.0:  # ATR doubled
                    return (
                        True,
                        f"Volatility increased significantly (ATR ratio: {atr_ratio:.2f})",
                    )
                if atr_ratio < 0.5:  # ATR halved
                    return (
                        True,
                        f"Volatility decreased significantly (ATR ratio: {atr_ratio:.2f})",
                    )

        return False, None

    def _rebalance_grid(
        self, current_price: float, timestamp: datetime, equity: float, reason: str
    ) -> None:
        """
        Rebalance grid around new mid-price

        Closes all open positions and reinitializes the grid.

        Args:
            current_price: New center price for grid
            timestamp: Current timestamp
            equity: Current account equity
            reason: Reason for rebalance
        """
        if self.grid_state is None:
            return

        logger.info(f"Rebalancing grid: {reason}")

        # Record performance before rebalance
        old_pnl = (
            self.grid_state.total_realized_pnl + self.grid_state.total_unrealized_pnl
        )
        old_trades = self.grid_state.total_trades
        rebalance_count = self.grid_state.rebalance_count + 1

        # Close all open positions (mark as expired)
        for level in self.grid_state.get_active_levels():
            level.status = GridLevelStatus.EXPIRED
            # In live trading, this would trigger actual position closes

        # Reinitialize grid
        self._initialize_grid(current_price, timestamp, equity)

        # Preserve rebalance count and accumulated stats
        if self.grid_state:
            self.grid_state.rebalance_count = rebalance_count
            self.grid_state.total_realized_pnl = old_pnl
            self.grid_state.total_trades = old_trades

        logger.info(
            f"Grid rebalanced #{rebalance_count}: new mid ${current_price:.2f}, "
            f"accumulated PnL: ${old_pnl:.2f}, trades: {old_trades}"
        )

    # =========================================================================
    # SIGNAL GENERATION
    # =========================================================================

    def on_bar(self, bar: OHLCV, equity: float) -> Optional[Signal]:
        """
        Process new bar and generate grid trading signals

        This is the main entry point called by the backtest/trading engine.
        Handles:
        1. Grid initialization
        2. Market regime detection
        3. Grid rebalancing checks
        4. Signal generation based on grid levels

        Args:
            bar: Current OHLCV bar
            equity: Current account equity

        Returns:
            Signal if action should be taken, None otherwise
        """
        current_price = bar.close

        # Need minimum data for ATR and indicator calculations
        if len(self._prices) < self.min_atr_periods:
            self._prev_price = current_price
            return None

        # Initialize grid on first valid bar
        if not self._grid_initialized:
            self._initialize_grid(current_price, bar.timestamp, equity)
            self._prev_price = current_price
            return None

        if self.grid_state is None:
            return None

        # Update market regime periodically
        regime = self._detect_market_regime()
        self.grid_state.current_regime = regime
        self.grid_state.last_regime_check = bar.timestamp

        # Check if grid should be paused
        should_pause, pause_reason = self._should_pause_grid(regime)
        if should_pause:
            if not self.grid_state.is_paused:
                logger.info(f"Pausing grid trading: {pause_reason}")
                self.grid_state.is_paused = True
                self.grid_state.pause_reason = pause_reason

            # Still check stop losses for open positions when paused
            stop_signal = self._check_grid_stop_loss(bar)
            if stop_signal:
                return stop_signal

            self._prev_price = current_price
            return None

        # Resume grid if was paused and conditions improved
        if self.grid_state.is_paused:
            logger.info(f"Resuming grid trading: Regime now {regime.value}")
            self.grid_state.is_paused = False
            self.grid_state.pause_reason = None

        # Check for grid rebalancing
        should_rebalance, rebalance_reason = self._should_rebalance_grid(
            current_price, bar.timestamp
        )
        if should_rebalance and rebalance_reason:
            self._rebalance_grid(current_price, bar.timestamp, equity, rebalance_reason)

        # Update unrealized P&L for all positions
        self.grid_state.update_unrealized_pnl(current_price)

        # Generate trading signal based on grid levels
        signal = self._generate_grid_signal(bar, equity)

        # Check for grid-wide stop loss
        if signal is None:
            signal = self._check_grid_stop_loss(bar)

        # Update previous price
        self._prev_price = current_price

        return signal

    def _generate_grid_signal(self, bar: OHLCV, equity: float) -> Optional[Signal]:
        """
        Generate buy/sell signal based on grid levels

        Args:
            bar: Current OHLCV bar
            equity: Current account equity

        Returns:
            Signal if grid level triggered, None otherwise
        """
        if self.grid_state is None or self._prev_price is None:
            return None

        current_price = bar.close

        # Calculate indicators for filtering
        rsi = self._calculate_rsi()
        volume_ratio = self._get_volume_ratio(bar.volume)

        # Check for BUY signal (price crossed below a buy level)
        if current_price <= self._prev_price:
            # Find crossed buy levels
            crossed_buy_levels = [
                lvl
                for lvl in self.grid_state.get_pending_buy_levels()
                if self._prev_price >= lvl.price >= current_price
            ]

            if crossed_buy_levels:
                # Get the highest crossed level (closest to current price)
                buy_level = max(crossed_buy_levels, key=lambda x: x.price)

                # Check position limits
                if self.grid_state.active_positions >= self.max_positions:
                    logger.debug(f"Max positions ({self.max_positions}) reached")
                    return None

                # Check exposure limits
                current_exposure = self.grid_state.get_total_exposure()
                max_exposure = equity * MAX_TOTAL_EXPOSURE_PCT
                if current_exposure >= max_exposure:
                    logger.debug(f"Max exposure ${max_exposure:.2f} reached")
                    return None

                # Apply filters if enabled
                if self.use_filters:
                    # RSI filter: Only buy when RSI indicates oversold
                    if USE_RSI_FILTER and rsi > RSI_OVERSOLD:
                        logger.debug(
                            f"RSI filter blocked buy: RSI={rsi:.1f} > {RSI_OVERSOLD}"
                        )
                        return None

                    # Volume filter: Require adequate volume
                    if USE_VOLUME_FILTER and volume_ratio < VOLUME_THRESHOLD_MULT:
                        logger.debug(
                            f"Volume filter blocked buy: ratio={volume_ratio:.2f}"
                        )
                        return None

                # Create buy signal
                return self._create_buy_signal(
                    bar, buy_level, equity, rsi, volume_ratio
                )

        # Check for SELL signal (price crossed above a sell level)
        elif current_price >= self._prev_price:
            # Find crossed sell levels
            crossed_sell_levels = [
                lvl
                for lvl in self.grid_state.get_pending_sell_levels()
                if self._prev_price <= lvl.price <= current_price
            ]

            if crossed_sell_levels:
                # Get the lowest crossed level (closest to current price)
                sell_level = min(crossed_sell_levels, key=lambda x: x.price)

                # Need open positions to sell
                if self.grid_state.active_positions == 0:
                    logger.debug("No positions to sell")
                    return None

                # Apply filters if enabled
                if self.use_filters:
                    # RSI filter: Only sell when RSI indicates overbought
                    if USE_RSI_FILTER and rsi < RSI_OVERBOUGHT:
                        logger.debug(
                            f"RSI filter blocked sell: RSI={rsi:.1f} < {RSI_OVERBOUGHT}"
                        )
                        return None

                    # Volume filter
                    if USE_VOLUME_FILTER and volume_ratio < VOLUME_THRESHOLD_MULT:
                        logger.debug(
                            f"Volume filter blocked sell: ratio={volume_ratio:.2f}"
                        )
                        return None

                # Create sell signal
                return self._create_sell_signal(bar, sell_level, rsi, volume_ratio)

        return None

    def _create_buy_signal(
        self,
        bar: OHLCV,
        grid_level: GridLevelV2,
        equity: float,
        rsi: float,
        volume_ratio: float,
    ) -> Optional[Signal]:
        """
        Create BUY signal for grid level

        Args:
            bar: Current OHLCV bar
            grid_level: Grid level being traded
            equity: Current account equity
            rsi: Current RSI value
            volume_ratio: Current volume ratio

        Returns:
            Buy Signal, or None if the sized position falls below the venue
            minimum (rejected — never rounded up).
        """
        current_price = bar.close

        # Calculate position size
        position_value = equity * self.position_size_pct
        # FIX 2026-08-05 (AUDIT 2.4, task E7): the old code did
        # max(MIN_POSITION_VALUE_USD, ...) — silently rounding a sub-minimum
        # trade UP to $10, which on a $100 account turns a configured cap into
        # a much larger one. Sub-minimum trades are REJECTED with a reason,
        # never clamped up (money.md sizing rule 4).
        if position_value < MIN_POSITION_VALUE_USD:
            logger.warning(
                f"Grid BUY rejected at {current_price}: position value "
                f"${position_value:.2f} (equity=${equity:.2f} x "
                f"{self.position_size_pct}) is below the ${MIN_POSITION_VALUE_USD:.2f} "
                f"minimum — refusing to round up to the venue floor"
            )
            return None
        position_value = min(position_value, MAX_POSITION_VALUE_USD)
        position_size = position_value / current_price

        # Calculate ATR for stop/TP
        current_atr = self._atr_cache or (current_price * 0.02)

        # Set stop loss
        stop_loss = current_price - (current_atr * INDIVIDUAL_STOP_ATR_MULT)

        # Set take profit at next sell level
        take_profit = grid_level.take_profit_price or (
            current_price + current_atr * INDIVIDUAL_TP_ATR_MULT
        )

        # Calculate confidence
        confidence = BASE_BUY_CONFIDENCE

        # Boost confidence based on conditions
        if rsi < RSI_OVERSOLD:
            confidence += CONFIDENCE_BOOST_RSI
        if volume_ratio > 1.5:
            confidence += CONFIDENCE_BOOST_VOLUME
        if self.grid_state and self.grid_state.current_regime == MarketRegime.RANGING:
            confidence += CONFIDENCE_BOOST_REGIME

        confidence = min(confidence, MAX_CONFIDENCE)

        # Update grid level status
        grid_level.status = GridLevelStatus.FILLED
        grid_level.fill_price = current_price
        grid_level.fill_timestamp = bar.timestamp
        grid_level.fill_quantity = position_size
        grid_level.fill_value_usd = position_value
        grid_level.stop_loss_price = stop_loss
        grid_level.take_profit_price = take_profit

        # Update grid state
        if self.grid_state:
            self.grid_state.active_positions += 1
            self.grid_state.total_position_size += position_size

            # Update average entry price
            total_value = (self.grid_state.average_entry_price or 0) * (
                self.grid_state.total_position_size - position_size
            )
            total_value += current_price * position_size
            self.grid_state.average_entry_price = (
                total_value / self.grid_state.total_position_size
            )

            # Update max position value
            self.grid_state.max_position_value = max(
                self.grid_state.max_position_value, self.grid_state.get_total_exposure()
            )

        logger.info(
            f"GRID BUY: Level #{grid_level.level_index} @ ${grid_level.price:.2f}, "
            f"Fill: ${current_price:.2f}, Size: {position_size:.6f}, "
            f"SL: ${stop_loss:.2f}, TP: ${take_profit:.2f}, Conf: {confidence:.2f}"
        )

        return Signal(
            signal_type=SignalType.BUY,
            symbol=self.symbol,
            price=current_price,
            timestamp=bar.timestamp,
            confidence=confidence,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size_pct=self.position_size_pct,
            metadata={
                "strategy": "grid_trading_v2",
                "grid_level": grid_level.price,
                "grid_level_index": grid_level.level_index,
                "active_positions": self.grid_state.active_positions
                if self.grid_state
                else 0,
                "market_regime": self.grid_state.current_regime.value
                if self.grid_state
                else "unknown",
                "rsi": rsi,
                "volume_ratio": volume_ratio,
                "atr": current_atr,
            },
        )

    def _create_sell_signal(
        self, bar: OHLCV, grid_level: GridLevelV2, rsi: float, volume_ratio: float
    ) -> Signal:
        """
        Create SELL signal for grid level (close long position)

        Args:
            bar: Current OHLCV bar
            grid_level: Grid level being traded
            rsi: Current RSI value
            volume_ratio: Current volume ratio

        Returns:
            Sell Signal (CLOSE_LONG)
        """
        current_price = bar.close

        # Find the corresponding buy position to close
        active_buys = self.grid_state.get_active_levels() if self.grid_state else []

        # Close the oldest buy position (FIFO)
        if active_buys:
            position_to_close = min(
                active_buys, key=lambda x: x.fill_timestamp or datetime.min
            )
            trade_pnl = position_to_close.close_position(current_price, bar.timestamp)

            # Update grid state
            if self.grid_state:
                self.grid_state.active_positions -= 1
                self.grid_state.total_position_size -= position_to_close.fill_quantity
                self.grid_state.total_trades += 1
                self.grid_state.total_realized_pnl += trade_pnl

                if trade_pnl > 0:
                    self.grid_state.winning_trades += 1

            # Track session performance
            self._session_trades += 1
            self._session_pnl += trade_pnl
            if trade_pnl > 0:
                self._session_wins += 1

            logger.info(
                f"GRID SELL: Level #{grid_level.level_index} @ ${grid_level.price:.2f}, "
                f"Exit: ${current_price:.2f}, PnL: ${trade_pnl:.2f}, "
                f"Remaining positions: {self.grid_state.active_positions if self.grid_state else 0}"
            )

        # Mark sell level as used
        grid_level.status = GridLevelStatus.COMPLETED
        grid_level.fill_price = current_price
        grid_level.fill_timestamp = bar.timestamp

        # Calculate confidence
        confidence = BASE_SELL_CONFIDENCE
        if rsi > RSI_OVERBOUGHT:
            confidence += CONFIDENCE_BOOST_RSI
        if volume_ratio > 1.5:
            confidence += CONFIDENCE_BOOST_VOLUME

        confidence = min(confidence, MAX_CONFIDENCE)

        return Signal(
            signal_type=SignalType.CLOSE_LONG,
            symbol=self.symbol,
            price=current_price,
            timestamp=bar.timestamp,
            confidence=confidence,
            metadata={
                "strategy": "grid_trading_v2",
                "grid_level": grid_level.price,
                "grid_level_index": grid_level.level_index,
                "exit_reason": "grid_level_hit",
                "trade_pnl": trade_pnl if active_buys else 0.0,
                "active_positions": self.grid_state.active_positions
                if self.grid_state
                else 0,
                "market_regime": self.grid_state.current_regime.value
                if self.grid_state
                else "unknown",
                "rsi": rsi,
            },
        )

    def _check_grid_stop_loss(self, bar: OHLCV) -> Optional[Signal]:
        """
        Check for grid-wide stop loss conditions

        Args:
            bar: Current OHLCV bar

        Returns:
            Close signal if stop hit, None otherwise
        """
        if self.grid_state is None or self.grid_state.average_entry_price is None:
            return None

        if self.grid_state.active_positions == 0:
            return None

        current_price = bar.close

        # Calculate current drawdown from average entry
        drawdown_pct = (
            self.grid_state.average_entry_price - current_price
        ) / self.grid_state.average_entry_price

        # Check grid stop loss
        if drawdown_pct > GRID_STOP_LOSS_PCT:
            logger.warning(
                f"Grid STOP LOSS triggered: Drawdown {drawdown_pct * 100:.1f}% > {GRID_STOP_LOSS_PCT * 100:.1f}%"
            )

            # Close all positions
            total_pnl = 0.0
            for level in self.grid_state.get_active_levels():
                pnl = level.close_position(current_price, bar.timestamp)
                total_pnl += pnl

            # Update grid state
            self.grid_state.active_positions = 0
            self.grid_state.total_position_size = 0.0
            self.grid_state.total_realized_pnl += total_pnl
            self.grid_state.total_trades += 1  # Count as single trade

            return Signal(
                signal_type=SignalType.CLOSE_LONG,
                symbol=self.symbol,
                price=current_price,
                timestamp=bar.timestamp,
                confidence=1.0,
                metadata={
                    "strategy": "grid_trading_v2",
                    "exit_reason": "grid_stop_loss",
                    "drawdown_pct": drawdown_pct,
                    "total_pnl": total_pnl,
                },
            )

        # Check emergency exit (severe loss)
        if drawdown_pct > EMERGENCY_EXIT_LOSS_PCT:
            logger.critical(
                f"EMERGENCY EXIT: Drawdown {drawdown_pct * 100:.1f}% > {EMERGENCY_EXIT_LOSS_PCT * 100:.1f}%"
            )

            # Force close all positions
            for level in self.grid_state.get_active_levels():
                level.close_position(current_price, bar.timestamp)

            self.grid_state.is_paused = True
            self.grid_state.pause_reason = (
                f"Emergency exit at {drawdown_pct * 100:.1f}% loss"
            )

            return Signal(
                signal_type=SignalType.CLOSE_LONG,
                symbol=self.symbol,
                price=current_price,
                timestamp=bar.timestamp,
                confidence=1.0,
                metadata={
                    "strategy": "grid_trading_v2",
                    "exit_reason": "emergency_exit",
                    "drawdown_pct": drawdown_pct,
                },
            )

        return None

    # =========================================================================
    # LIFECYCLE METHODS
    # =========================================================================

    def on_start(self, initial_equity: float) -> None:
        """Called at backtest/trading start"""
        super().on_start(initial_equity)
        self._session_start = datetime.now()
        self._session_trades = 0
        self._session_wins = 0
        self._session_pnl = 0.0

        logger.info(
            f"GridTradingStrategyV2 started for {self.symbol} | "
            f"Initial equity: ${initial_equity:.2f}"
        )

    def on_end(self, final_equity: float) -> None:
        """Called at backtest/trading end - log final statistics"""
        super().on_end(final_equity)

        if self.grid_state is None:
            return

        # Calculate final metrics
        session_duration = (
            datetime.now() - self._session_start
        ).total_seconds() / 3600  # hours
        win_rate = self.grid_state.get_win_rate()
        profit_factor = self.grid_state.get_profit_factor()

        # Log comprehensive summary
        logger.info("\n" + "=" * 70)
        logger.info("GRID TRADING STRATEGY V2 - FINAL STATISTICS")
        logger.info("=" * 70)
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Session Duration: {session_duration:.1f} hours")
        logger.info("-" * 70)
        logger.info(f"Total Trades: {self.grid_state.total_trades}")
        logger.info(f"Winning Trades: {self.grid_state.winning_trades}")
        logger.info(f"Win Rate: {win_rate:.1f}%")
        logger.info(f"Profit Factor: {profit_factor:.2f}")
        logger.info("-" * 70)
        logger.info(f"Total Realized P&L: ${self.grid_state.total_realized_pnl:.2f}")
        logger.info(f"Unrealized P&L: ${self.grid_state.total_unrealized_pnl:.2f}")
        logger.info(
            f"Average P&L per Trade: ${self.grid_state.total_realized_pnl / max(1, self.grid_state.total_trades):.2f}"
        )
        logger.info("-" * 70)
        logger.info(f"Grid Rebalances: {self.grid_state.rebalance_count}")
        logger.info(f"Final Regime: {self.grid_state.current_regime.value}")
        logger.info("=" * 70)

        # Log per-level statistics if tracking enabled
        if TRACK_LEVEL_PERFORMANCE:
            logger.info("\nPER-LEVEL STATISTICS:")
            logger.info("-" * 70)
            for level in sorted(
                self.grid_state.grid_levels, key=lambda x: x.price, reverse=True
            ):
                if level.trade_count > 0:
                    logger.info(
                        f"  Level ${level.price:.2f} ({level.level_type}): "
                        f"Trades={level.trade_count}, "
                        f"WinRate={level.get_win_rate():.1f}%, "
                        f"PnL=${level.total_pnl:.2f}"
                    )

    def get_strategy_params(self) -> Dict[str, Any]:
        """Return strategy configuration parameters"""
        return {
            "symbol": self.symbol,
            "grid_levels": self.grid_levels_count,
            "grid_range_pct": self.grid_range_pct,
            "spacing_type": self.spacing_type.value,
            "max_positions": self.max_positions,
            "position_size_pct": self.position_size_pct,
            "use_filters": self.use_filters,
            "version": "2.0.0",
            "features": [
                "dynamic_grid_spacing",
                "market_regime_detection",
                "volatility_adaptation",
                "comprehensive_risk_management",
                "per_level_performance_tracking",
            ],
        }

    def get_grid_state(self) -> Optional[Dict[str, Any]]:
        """Get current grid state for monitoring/visualization"""
        if self.grid_state is None:
            return None
        return self.grid_state.get_grid_summary()


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def create_grid_trading_strategy_v2(
    symbol: str, config: Optional[Dict[str, Any]] = None
) -> GridTradingStrategyV2:
    """
    Factory function to create Grid Trading Strategy V2

    Args:
        symbol: Trading pair symbol
        config: Optional configuration overrides

    Returns:
        Configured GridTradingStrategyV2 instance
    """
    if config is None:
        config = {}

    return GridTradingStrategyV2(
        symbol=symbol,
        grid_levels=config.get("grid_levels", DEFAULT_GRID_LEVELS),
        grid_range_pct=config.get("grid_range_pct", DEFAULT_GRID_RANGE_PCT),
        spacing_type=GridSpacingType(
            config.get("spacing_type", DEFAULT_SPACING_TYPE.value)
        ),
        max_positions=config.get("max_positions", MAX_CONCURRENT_POSITIONS),
        position_size_pct=config.get("position_size_pct", POSITION_SIZE_PCT),
        use_filters=config.get("use_filters", True),
    )


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "GridTradingStrategyV2",
    "GridLevelV2",
    "GridStateV2",
    "GridSpacingType",
    "GridLevelStatus",
    "MarketRegime",
    "create_grid_trading_strategy_v2",
    # Constants for external configuration
    "DEFAULT_GRID_LEVELS",
    "DEFAULT_GRID_RANGE_PCT",
    "MAX_CONCURRENT_POSITIONS",
    "POSITION_SIZE_PCT",
]
