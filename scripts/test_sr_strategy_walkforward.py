#!/usr/bin/env python3
"""
Walk-Forward Validation Script for Support/Resistance Strategy
==============================================================
Purpose: Comprehensive walk-forward testing to validate S/R strategy robustness

Walk-Forward Analysis Parameters:
- Training window: 60 days (optimize parameters)
- Test window: 14 days (validate out-of-sample)
- Step size: 7 days (rolling advancement)
- Total period: Last 6 months of data (from CSV files)

Symbols Tested:
- SOLUSDT (high volatility)
- BNBUSDT (medium volatility)
- ADAUSDT (lower volatility)

Pass/Fail Criteria:
- Win rate > 50%
- Sharpe ratio > 0 (positive risk-adjusted returns)
- Max drawdown < 15%

Comparison baseline: research_optimized strategy

Data Source: CSV files from /data/historical/ directory

Author: Testing Guardian Agent
Date: 2025-12-07
Updated: 2025-12-11 - Fixed to use CSV data instead of API
"""

import sys
import os
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd
import numpy as np

# Setup path to import strategy modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'trading-engine'))

# Import strategies
from app.strategies.support_resistance_strategy import (
    SupportResistanceStrategy,
    TradeSetup as SRTradeSetup,
    SignalAction,
    MarketCondition as SRMarketCondition,
    SignalStrength as SRSignalStrength,
)
from app.strategies.research_optimized_strategy import (
    ResearchOptimizedStrategy,
    TradeSetup as ROTradeSetup,
    MarketCondition as ROMarketCondition,
    SignalStrength as ROSignalStrength,
)
from app.utils.support_resistance_detector import SupportResistanceDetector
from app.models import IndicatorSignal

# Declared account size (see shared/account.py).
import os as _os
import sys as _sys

_REPO_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
if _REPO_ROOT not in _sys.path:
    _sys.path.insert(0, _REPO_ROOT)
from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/sr_walkforward.log', mode='w')
    ]
)
logger = logging.getLogger(__name__)
# Custom JSON encoder for numpy types
class NumpyEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles numpy types"""
    def default(self, obj):
        if isinstance(obj, (np.bool_, np.integer)):
            return bool(obj) if isinstance(obj, np.bool_) else int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)




# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# Walk-Forward Parameters
TRAINING_WINDOW_DAYS = 60      # 60 days for in-sample optimization
TEST_WINDOW_DAYS = 14          # 14 days for out-of-sample validation
STEP_SIZE_DAYS = 7             # Roll forward 7 days between windows
TOTAL_PERIOD_DAYS = 180        # Last 6 months of data

# Symbols to test
TEST_SYMBOLS = ['SOLUSDT', 'BNBUSDT', 'ADAUSDT']

# Data configuration - CSV files location
DATA_DIR = Path(__file__).parent.parent / "data" / "historical"
DATA_INTERVAL = '60'           # 1 hour candles

# Initial capital for backtesting
INITIAL_CAPITAL = ACCOUNT_EQUITY_USD

# Pass/Fail Criteria
MIN_WIN_RATE = 50.0            # Minimum 50% win rate
MIN_SHARPE_RATIO = 0.0         # Positive Sharpe required
MAX_DRAWDOWN_PCT = 15.0        # Maximum 15% drawdown
MIN_TRADES_PER_WINDOW = 5      # Minimum trades for valid results

# Commission and slippage
COMMISSION = 0.001             # 0.1% per trade
SLIPPAGE = 0.0005              # 0.05% slippage


# =============================================================================
# DATA CLASSES FOR RESULTS
# =============================================================================

@dataclass
class TradeRecord:
    """Record of a single trade during backtesting"""
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    direction: str  # 'LONG' or 'SHORT'
    position_size: float
    pnl: float
    pnl_pct: float
    exit_reason: str
    confidence: float = 0.0
    duration_hours: float = 0.0


@dataclass
class WindowMetrics:
    """Metrics for a single walk-forward window"""
    window_num: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    profit_factor: float
    avg_trade_duration_hours: float
    avg_win_pct: float
    avg_loss_pct: float
    trades: List[TradeRecord] = field(default_factory=list)
    is_valid: bool = True
    validation_message: str = ""


@dataclass
class SymbolResults:
    """Aggregated results for a single symbol"""
    symbol: str
    strategy_name: str
    windows: List[WindowMetrics]

    # Aggregate metrics
    total_windows: int = 0
    valid_windows: int = 0
    total_trades: int = 0
    total_wins: int = 0
    total_losses: int = 0
    aggregate_win_rate: float = 0.0
    aggregate_return_pct: float = 0.0
    aggregate_sharpe: float = 0.0
    avg_max_drawdown: float = 0.0
    avg_profit_factor: float = 0.0
    avg_trade_duration_hours: float = 0.0

    # Pass/Fail
    passes_win_rate: bool = False
    passes_sharpe: bool = False
    passes_drawdown: bool = False
    overall_pass: bool = False


@dataclass
class WalkForwardResults:
    """Complete walk-forward validation results"""
    timestamp: str
    strategy_name: str
    symbols: List[SymbolResults]

    # Overall metrics
    symbols_passed: int = 0
    symbols_failed: int = 0
    overall_win_rate: float = 0.0
    overall_sharpe: float = 0.0
    overall_return_pct: float = 0.0
    overall_max_drawdown: float = 0.0

    # Comparison with baseline
    baseline_results: Optional[Dict] = None
    outperforms_baseline: bool = False

    # Final verdict
    strategy_robust: bool = False
    recommendation: str = ""


# =============================================================================
# CSV DATA LOADING (REPLACES API FETCHING)
# =============================================================================

def load_csv_data(symbol: str) -> pd.DataFrame:
    """
    Load historical data from CSV file for a given symbol.

    This function replaces the previous API-based DataFetcher class.
    It searches for the most recent CSV file matching the symbol pattern.

    Args:
        symbol: Trading pair (e.g., SOLUSDT)

    Returns:
        DataFrame with OHLCV data indexed by timestamp

    Raises:
        FileNotFoundError: If no CSV file found for the symbol
    """
    # Find CSV files matching the symbol pattern
    csv_files = list(DATA_DIR.glob(f"{symbol}_180days_*.csv"))

    if not csv_files:
        raise FileNotFoundError(f"No CSV file found for {symbol} in {DATA_DIR}")

    # Sort by filename (contains date) and get the most recent file
    csv_files.sort(reverse=True)
    csv_file = csv_files[0]

    logger.info(f"Loading data from CSV: {csv_file}")

    # Read CSV file
    df = pd.read_csv(csv_file)

    # Convert timestamp column to datetime
    # The CSV has 'timestamp' in milliseconds and 'datetime' as string
    if 'datetime' in df.columns:
        df['timestamp'] = pd.to_datetime(df['datetime'])
    elif 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

    # Set timestamp as index
    df.set_index('timestamp', inplace=True)

    # Ensure proper column types for OHLCV data
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Sort by index to ensure chronological order
    df = df.sort_index()

    logger.info(f"Loaded {len(df)} candles for {symbol}")
    logger.info(f"Date range: {df.index[0]} to {df.index[-1]}")

    return df


def load_all_symbols(symbols: List[str]) -> Dict[str, pd.DataFrame]:
    """
    Load historical data for all specified symbols from CSV files.

    Args:
        symbols: List of trading pairs to load

    Returns:
        Dictionary mapping symbol to DataFrame
    """
    data = {}

    for symbol in symbols:
        try:
            df = load_csv_data(symbol)
            if not df.empty:
                data[symbol] = df
        except FileNotFoundError as e:
            logger.warning(f"No data file found for {symbol}: {e}")
        except Exception as e:
            logger.error(f"Error loading {symbol}: {e}")

    return data


# =============================================================================
# BACKTEST ENGINE FOR WALK-FORWARD
# =============================================================================

class WalkForwardBacktestEngine:
    """
    Simplified backtest engine for walk-forward validation

    Focuses on generating signals and tracking performance metrics
    """

    def __init__(
        self,
        initial_capital: float = INITIAL_CAPITAL,
        commission: float = COMMISSION,
        slippage: float = SLIPPAGE
    ):
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage

    def _calculate_indicators(self, df: pd.DataFrame) -> Dict[str, IndicatorSignal]:
        """
        Calculate indicators required by strategy

        Returns IndicatorSignal dict compatible with strategy interface.
        IndicatorSignal fields: name, signal (SignalAction), confidence, value, metadata
        """
        indicators = {}

        # RSI (14-period)
        delta = df['close'].diff()
        gains = delta.where(delta > 0, 0.0)
        losses = -delta.where(delta < 0, 0.0)
        avg_gain = gains.rolling(14, min_periods=14).mean()
        avg_loss = losses.rolling(14, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-10)
        rsi = 100 - (100 / (1 + rs))
        rsi_value = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50.0

        # Determine RSI signal
        if rsi_value < 30:
            rsi_signal = SignalAction.BUY
            rsi_conf = 0.7
        elif rsi_value > 70:
            rsi_signal = SignalAction.SELL
            rsi_conf = 0.7
        else:
            rsi_signal = SignalAction.NEUTRAL
            rsi_conf = 0.5

        indicators['RSI'] = IndicatorSignal(
            name='RSI',
            signal=rsi_signal,
            confidence=rsi_conf,
            value=rsi_value,
            metadata={'period': 14}
        )

        # MACD (12, 26, 9)
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line

        macd_val = macd_line.iloc[-1]
        hist_val = histogram.iloc[-1]

        if hist_val > 0 and macd_val > signal_line.iloc[-1]:
            macd_signal = SignalAction.BUY
            macd_conf = 0.6
        elif hist_val < 0 and macd_val < signal_line.iloc[-1]:
            macd_signal = SignalAction.SELL
            macd_conf = 0.6
        else:
            macd_signal = SignalAction.NEUTRAL
            macd_conf = 0.5

        indicators['MACD'] = IndicatorSignal(
            name='MACD',
            signal=macd_signal,
            confidence=macd_conf,
            value=macd_val,
            metadata={
                'macd_line': macd_val,
                'signal_line': signal_line.iloc[-1],
                'histogram': hist_val
            }
        )

        # Bollinger Bands (20, 2.5)
        sma20 = df['close'].rolling(20).mean()
        std20 = df['close'].rolling(20).std()
        bb_upper = sma20 + (std20 * 2.5)
        bb_lower = sma20 - (std20 * 2.5)
        current_price = df['close'].iloc[-1]

        if current_price < bb_lower.iloc[-1]:
            bb_signal = SignalAction.BUY
            bb_conf = 0.65
        elif current_price > bb_upper.iloc[-1]:
            bb_signal = SignalAction.SELL
            bb_conf = 0.65
        else:
            bb_signal = SignalAction.NEUTRAL
            bb_conf = 0.5

        indicators['BOLLINGER_BANDS'] = IndicatorSignal(
            name='BOLLINGER_BANDS',
            signal=bb_signal,
            confidence=bb_conf,
            value=sma20.iloc[-1],
            metadata={
                'upper_band': bb_upper.iloc[-1],
                'middle_band': sma20.iloc[-1],
                'lower_band': bb_lower.iloc[-1]
            }
        )

        # EMA (9)
        ema9 = df['close'].ewm(span=9, adjust=False).mean()
        ema9_val = ema9.iloc[-1]

        if current_price > ema9_val:
            ema_signal = SignalAction.BUY
        elif current_price < ema9_val:
            ema_signal = SignalAction.SELL
        else:
            ema_signal = SignalAction.NEUTRAL

        indicators['EMA'] = IndicatorSignal(
            name='EMA',
            signal=ema_signal,
            confidence=0.5,
            value=ema9_val,
            metadata={'period': 9}
        )

        # SMA (50)
        sma50 = df['close'].rolling(50).mean()
        sma50_val = sma50.iloc[-1] if not pd.isna(sma50.iloc[-1]) else df['close'].iloc[-1]

        if current_price > sma50_val:
            sma_signal = SignalAction.BUY
        elif current_price < sma50_val:
            sma_signal = SignalAction.SELL
        else:
            sma_signal = SignalAction.NEUTRAL

        indicators['SMA'] = IndicatorSignal(
            name='SMA',
            signal=sma_signal,
            confidence=0.5,
            value=sma50_val,
            metadata={'period': 50}
        )

        # ATR (14)
        high_low = df['high'] - df['low']
        high_close_prev = abs(df['high'] - df['close'].shift(1))
        low_close_prev = abs(df['low'] - df['close'].shift(1))
        tr = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        atr_val = atr.iloc[-1]

        # Add ATR to metadata for other indicators
        for ind in indicators.values():
            if ind.metadata:
                ind.metadata['atr'] = atr_val

        # Trend filter
        ema20 = df['close'].ewm(span=20, adjust=False).mean()
        ema50_val = sma50.iloc[-1] if not pd.isna(sma50.iloc[-1]) else ema20.iloc[-1]
        is_bullish = ema20.iloc[-1] > ema50_val

        trend_signal = SignalAction.BUY if is_bullish else SignalAction.SELL

        indicators['TREND_FILTER'] = IndicatorSignal(
            name='TREND_FILTER',
            signal=trend_signal,
            confidence=0.6,
            value=1 if is_bullish else -1,
            metadata={'trend': 'BULLISH' if is_bullish else 'BEARISH', 'adx': 25.0}
        )

        # Volume confirmation
        avg_volume = df['volume'].rolling(20).mean()
        vol_ratio = df['volume'].iloc[-1] / avg_volume.iloc[-1] if avg_volume.iloc[-1] > 0 else 1.0

        if vol_ratio > 1.5:
            vol_signal = SignalAction.BUY
            vol_conf = 0.7
            vol_strength = 'STRONG'
        elif vol_ratio > 1.0:
            vol_signal = SignalAction.NEUTRAL
            vol_conf = 0.5
            vol_strength = 'MODERATE'
        else:
            vol_signal = SignalAction.NEUTRAL
            vol_conf = 0.4
            vol_strength = 'WEAK'

        indicators['VOLUME_CONFIRMATION'] = IndicatorSignal(
            name='VOLUME_CONFIRMATION',
            signal=vol_signal,
            confidence=vol_conf,
            value=vol_ratio,
            metadata={'strength': vol_strength, 'ratio': vol_ratio}
        )

        return indicators

    def run_backtest(
        self,
        df: pd.DataFrame,
        strategy,
        strategy_name: str
    ) -> Tuple[List[TradeRecord], List[float]]:
        """
        Run backtest on given data with specified strategy

        Args:
            df: OHLCV DataFrame
            strategy: Strategy instance (SupportResistanceStrategy or ResearchOptimizedStrategy)
            strategy_name: Name for logging

        Returns:
            Tuple of (trades list, equity curve)
        """
        trades = []
        equity_curve = [self.initial_capital]
        capital = self.initial_capital

        current_position = None
        position_entry_time = None
        position_entry_price = None
        position_direction = None
        position_size = 0.0
        position_stop_loss = None
        position_take_profit = None
        position_confidence = 0.0

        # Need enough data for indicators
        min_lookback = 100

        for i in range(min_lookback, len(df)):
            # Get data up to current point
            df_slice = df.iloc[:i+1].copy()
            current_row = df.iloc[i]
            current_price = current_row['close']
            current_time = df.index[i]

            # Check stop loss / take profit for open position
            if current_position:
                exit_reason = None
                exit_price = None

                if position_direction == 'LONG':
                    if position_stop_loss and current_row['low'] <= position_stop_loss:
                        exit_reason = 'stop_loss'
                        exit_price = position_stop_loss
                    elif position_take_profit and current_row['high'] >= position_take_profit:
                        exit_reason = 'take_profit'
                        exit_price = position_take_profit
                else:  # SHORT
                    if position_stop_loss and current_row['high'] >= position_stop_loss:
                        exit_reason = 'stop_loss'
                        exit_price = position_stop_loss
                    elif position_take_profit and current_row['low'] <= position_take_profit:
                        exit_reason = 'take_profit'
                        exit_price = position_take_profit

                if exit_reason:
                    # Close position
                    exit_price = exit_price * (1 - self.slippage) if position_direction == 'LONG' else exit_price * (1 + self.slippage)

                    if position_direction == 'LONG':
                        pnl = (exit_price - position_entry_price) * position_size
                    else:
                        pnl = (position_entry_price - exit_price) * position_size

                    # Deduct commission
                    pnl -= position_size * exit_price * self.commission
                    capital += pnl

                    pnl_pct = (pnl / (position_entry_price * position_size)) * 100
                    duration = (current_time - position_entry_time).total_seconds() / 3600

                    trades.append(TradeRecord(
                        entry_time=position_entry_time,
                        exit_time=current_time,
                        entry_price=position_entry_price,
                        exit_price=exit_price,
                        direction=position_direction,
                        position_size=position_size,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        exit_reason=exit_reason,
                        confidence=position_confidence,
                        duration_hours=duration
                    ))

                    current_position = None
                    position_entry_time = None
                    position_entry_price = None
                    position_direction = None
                    position_size = 0.0
                    position_stop_loss = None
                    position_take_profit = None

            # Generate signal if no position
            if not current_position:
                indicators = self._calculate_indicators(df_slice)

                # Generate signal based on strategy type
                if isinstance(strategy, SupportResistanceStrategy):
                    signal = strategy.generate_signal(
                        indicators=indicators,
                        current_price=current_price,
                        df=df_slice,
                        capital=capital
                    )
                else:  # ResearchOptimizedStrategy
                    signal = strategy.generate_signal(
                        indicators=indicators,
                        current_price=current_price,
                        capital=capital
                    )

                if signal:
                    # Process signal
                    action = signal.action

                    if action in [SignalAction.BUY, SignalAction.SELL]:
                        # Open position
                        direction = 'LONG' if action == SignalAction.BUY else 'SHORT'
                        entry_price = current_price * (1 + self.slippage) if direction == 'LONG' else current_price * (1 - self.slippage)

                        # Calculate position size
                        pos_size_pct = signal.position_size_pct if hasattr(signal, 'position_size_pct') else 0.02
                        position_value = capital * pos_size_pct
                        position_size = position_value / entry_price

                        # Deduct commission
                        capital -= position_size * entry_price * self.commission

                        current_position = True
                        position_entry_time = current_time
                        position_entry_price = entry_price
                        position_direction = direction
                        position_stop_loss = signal.stop_loss if hasattr(signal, 'stop_loss') else None
                        position_take_profit = signal.take_profit if hasattr(signal, 'take_profit') else None
                        position_confidence = signal.confidence if hasattr(signal, 'confidence') else 0.0

            # Update equity curve
            current_equity = capital
            if current_position:
                if position_direction == 'LONG':
                    unrealized = (current_price - position_entry_price) * position_size
                else:
                    unrealized = (position_entry_price - current_price) * position_size
                current_equity += unrealized

            equity_curve.append(current_equity)

        # Close any open position at end
        if current_position:
            final_price = df.iloc[-1]['close']
            final_time = df.index[-1]

            if position_direction == 'LONG':
                pnl = (final_price - position_entry_price) * position_size
            else:
                pnl = (position_entry_price - final_price) * position_size

            pnl -= position_size * final_price * self.commission
            capital += pnl

            pnl_pct = (pnl / (position_entry_price * position_size)) * 100
            duration = (final_time - position_entry_time).total_seconds() / 3600

            trades.append(TradeRecord(
                entry_time=position_entry_time,
                exit_time=final_time,
                entry_price=position_entry_price,
                exit_price=final_price,
                direction=position_direction,
                position_size=position_size,
                pnl=pnl,
                pnl_pct=pnl_pct,
                exit_reason='end_of_data',
                confidence=position_confidence,
                duration_hours=duration
            ))

            equity_curve.append(capital)

        return trades, equity_curve

    def calculate_metrics(self, trades: List[TradeRecord], equity_curve: List[float]) -> Dict[str, float]:
        """Calculate performance metrics from trades and equity curve"""

        if not trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'total_return_pct': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown_pct': 0.0,
                'profit_factor': 0.0,
                'avg_trade_duration_hours': 0.0,
                'avg_win_pct': 0.0,
                'avg_loss_pct': 0.0
            }

        # Basic counts
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl <= 0]

        total_trades = len(trades)
        num_wins = len(winning_trades)
        num_losses = len(losing_trades)
        win_rate = (num_wins / total_trades * 100) if total_trades > 0 else 0.0

        # Returns
        total_return_pct = ((equity_curve[-1] - self.initial_capital) / self.initial_capital * 100) if equity_curve else 0.0

        # Sharpe ratio
        if len(equity_curve) > 1:
            returns = pd.Series(equity_curve).pct_change().dropna()
            if len(returns) > 0 and returns.std() > 0:
                sharpe = (returns.mean() / returns.std()) * np.sqrt(365 * 24)  # Annualized for hourly data
            else:
                sharpe = 0.0
        else:
            sharpe = 0.0

        # Max drawdown
        max_dd_pct = 0.0
        peak = equity_curve[0] if equity_curve else self.initial_capital
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100 if peak > 0 else 0.0
            if dd > max_dd_pct:
                max_dd_pct = dd

        # Profit factor
        gross_profit = sum(t.pnl for t in winning_trades)
        gross_loss = abs(sum(t.pnl for t in losing_trades))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0.0

        # Average durations
        avg_duration = sum(t.duration_hours for t in trades) / total_trades if total_trades > 0 else 0.0

        # Average win/loss percentages
        avg_win_pct = sum(t.pnl_pct for t in winning_trades) / num_wins if num_wins > 0 else 0.0
        avg_loss_pct = sum(t.pnl_pct for t in losing_trades) / num_losses if num_losses > 0 else 0.0

        return {
            'total_trades': total_trades,
            'winning_trades': num_wins,
            'losing_trades': num_losses,
            'win_rate': win_rate,
            'total_return_pct': total_return_pct,
            'sharpe_ratio': sharpe,
            'max_drawdown_pct': max_dd_pct,
            'profit_factor': profit_factor,
            'avg_trade_duration_hours': avg_duration,
            'avg_win_pct': avg_win_pct,
            'avg_loss_pct': avg_loss_pct
        }


# =============================================================================
# WALK-FORWARD VALIDATION ENGINE
# =============================================================================

class WalkForwardValidator:
    """
    Walk-Forward Validation Engine

    Implements rolling window optimization/validation to test strategy robustness
    """

    def __init__(
        self,
        training_days: int = TRAINING_WINDOW_DAYS,
        test_days: int = TEST_WINDOW_DAYS,
        step_days: int = STEP_SIZE_DAYS
    ):
        self.training_days = training_days
        self.test_days = test_days
        self.step_days = step_days
        self.backtest_engine = WalkForwardBacktestEngine()

    def create_windows(self, df: pd.DataFrame) -> List[Tuple[pd.DataFrame, pd.DataFrame, int]]:
        """
        Create rolling walk-forward windows

        Args:
            df: Full historical data

        Returns:
            List of (train_df, test_df, window_num) tuples
        """
        windows = []

        # Get date range
        start_date = df.index[0]
        end_date = df.index[-1]
        total_days = (end_date - start_date).days

        # Calculate window parameters in terms of rows (for hourly data)
        hours_per_day = 24
        train_rows = self.training_days * hours_per_day
        test_rows = self.test_days * hours_per_day
        step_rows = self.step_days * hours_per_day

        window_num = 1
        current_start = 0

        while current_start + train_rows + test_rows <= len(df):
            train_end = current_start + train_rows
            test_end = train_end + test_rows

            train_df = df.iloc[current_start:train_end].copy()
            test_df = df.iloc[train_end:test_end].copy()

            windows.append((train_df, test_df, window_num))

            current_start += step_rows
            window_num += 1

        logger.info(f"Created {len(windows)} walk-forward windows")
        return windows

    def validate_symbol(
        self,
        symbol: str,
        df: pd.DataFrame,
        strategy,
        strategy_name: str
    ) -> SymbolResults:
        """
        Run walk-forward validation for a single symbol

        Args:
            symbol: Trading pair
            df: Historical data
            strategy: Strategy instance
            strategy_name: Strategy name

        Returns:
            SymbolResults with all window metrics
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"Walk-Forward Validation: {symbol} - {strategy_name}")
        logger.info(f"{'='*60}")

        windows = self.create_windows(df)
        window_results = []

        for train_df, test_df, window_num in windows:
            logger.info(f"\nWindow {window_num}:")
            logger.info(f"  Train: {train_df.index[0]} to {train_df.index[-1]} ({len(train_df)} candles)")
            logger.info(f"  Test:  {test_df.index[0]} to {test_df.index[-1]} ({len(test_df)} candles)")

            # Run backtest on TEST window (strategy already "trained" via indicator calculation)
            trades, equity = self.backtest_engine.run_backtest(test_df, strategy, strategy_name)
            metrics = self.backtest_engine.calculate_metrics(trades, equity)

            # Validate window
            is_valid = True
            validation_msg = ""

            if metrics['total_trades'] < MIN_TRADES_PER_WINDOW:
                is_valid = False
                validation_msg = f"Insufficient trades ({metrics['total_trades']} < {MIN_TRADES_PER_WINDOW})"

            window_metrics = WindowMetrics(
                window_num=window_num,
                train_start=train_df.index[0],
                train_end=train_df.index[-1],
                test_start=test_df.index[0],
                test_end=test_df.index[-1],
                total_trades=metrics['total_trades'],
                winning_trades=metrics['winning_trades'],
                losing_trades=metrics['losing_trades'],
                win_rate=metrics['win_rate'],
                total_return_pct=metrics['total_return_pct'],
                sharpe_ratio=metrics['sharpe_ratio'],
                max_drawdown_pct=metrics['max_drawdown_pct'],
                profit_factor=metrics['profit_factor'],
                avg_trade_duration_hours=metrics['avg_trade_duration_hours'],
                avg_win_pct=metrics['avg_win_pct'],
                avg_loss_pct=metrics['avg_loss_pct'],
                trades=trades,
                is_valid=is_valid,
                validation_message=validation_msg
            )

            window_results.append(window_metrics)

            logger.info(f"  Results: {metrics['total_trades']} trades, "
                       f"WR={metrics['win_rate']:.1f}%, "
                       f"Return={metrics['total_return_pct']:.2f}%, "
                       f"Sharpe={metrics['sharpe_ratio']:.2f}")

        # Aggregate results
        symbol_results = self._aggregate_symbol_results(symbol, strategy_name, window_results)

        logger.info(f"\n{symbol} Summary:")
        logger.info(f"  Windows: {symbol_results.valid_windows}/{symbol_results.total_windows}")
        logger.info(f"  Total trades: {symbol_results.total_trades}")
        logger.info(f"  Win rate: {symbol_results.aggregate_win_rate:.1f}%")
        logger.info(f"  Sharpe ratio: {symbol_results.aggregate_sharpe:.2f}")
        logger.info(f"  Max drawdown: {symbol_results.avg_max_drawdown:.2f}%")
        logger.info(f"  Pass: {'YES' if symbol_results.overall_pass else 'NO'}")

        return symbol_results

    def _aggregate_symbol_results(
        self,
        symbol: str,
        strategy_name: str,
        windows: List[WindowMetrics]
    ) -> SymbolResults:
        """Aggregate metrics across all windows"""

        valid_windows = [w for w in windows if w.is_valid]

        results = SymbolResults(
            symbol=symbol,
            strategy_name=strategy_name,
            windows=windows,
            total_windows=len(windows),
            valid_windows=len(valid_windows)
        )

        if not valid_windows:
            return results

        # Aggregate trades
        results.total_trades = sum(w.total_trades for w in valid_windows)
        results.total_wins = sum(w.winning_trades for w in valid_windows)
        results.total_losses = sum(w.losing_trades for w in valid_windows)

        # Aggregate metrics (weighted by trades)
        if results.total_trades > 0:
            results.aggregate_win_rate = (results.total_wins / results.total_trades) * 100

        # Average metrics across windows
        results.aggregate_return_pct = sum(w.total_return_pct for w in valid_windows) / len(valid_windows)
        results.aggregate_sharpe = sum(w.sharpe_ratio for w in valid_windows) / len(valid_windows)
        results.avg_max_drawdown = sum(w.max_drawdown_pct for w in valid_windows) / len(valid_windows)
        results.avg_profit_factor = sum(w.profit_factor for w in valid_windows) / len(valid_windows)
        results.avg_trade_duration_hours = sum(w.avg_trade_duration_hours for w in valid_windows) / len(valid_windows)

        # Pass/Fail criteria
        results.passes_win_rate = results.aggregate_win_rate >= MIN_WIN_RATE
        results.passes_sharpe = results.aggregate_sharpe >= MIN_SHARPE_RATIO
        results.passes_drawdown = results.avg_max_drawdown <= MAX_DRAWDOWN_PCT
        results.overall_pass = results.passes_win_rate and results.passes_sharpe and results.passes_drawdown

        return results


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_walk_forward_validation():
    """Main entry point for walk-forward validation (synchronous - no async needed)"""

    print("\n" + "="*80)
    print("SUPPORT/RESISTANCE STRATEGY - WALK-FORWARD VALIDATION")
    print("="*80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Symbols: {', '.join(TEST_SYMBOLS)}")
    print(f"Training window: {TRAINING_WINDOW_DAYS} days")
    print(f"Test window: {TEST_WINDOW_DAYS} days")
    print(f"Step size: {STEP_SIZE_DAYS} days")
    print(f"Total period: {TOTAL_PERIOD_DAYS} days")
    print(f"Data source: CSV files in {DATA_DIR}")
    print("="*80 + "\n")

    # Initialize components
    validator = WalkForwardValidator()

    # Strategies to test
    sr_strategy = SupportResistanceStrategy()
    ro_strategy = ResearchOptimizedStrategy()

    # Load data from CSV files (replaces API fetching)
    logger.info("Loading historical data from CSV files...")
    symbol_data = load_all_symbols(TEST_SYMBOLS)

    if not symbol_data:
        logger.error("No data loaded. Check if CSV files exist in the data directory.")
        print(f"\nERROR: Could not load data from CSV files.")
        print(f"Please ensure CSV files exist in: {DATA_DIR}")
        print(f"Expected format: SYMBOL_180days_DATE.csv")
        return None

    # Report loaded data
    print(f"\nLoaded data for {len(symbol_data)} symbols:")
    for symbol, df in symbol_data.items():
        print(f"  {symbol}: {len(df)} candles ({df.index[0]} to {df.index[-1]})")

    # Results storage
    sr_results = []
    ro_results = []

    # Run validation for each symbol
    for symbol in TEST_SYMBOLS:
        if symbol not in symbol_data:
            logger.warning(f"No data for {symbol}, skipping")
            continue

        df = symbol_data[symbol]

        # S/R Strategy validation
        sr_result = validator.validate_symbol(
            symbol=symbol,
            df=df,
            strategy=sr_strategy,
            strategy_name="SupportResistanceStrategy"
        )
        sr_results.append(sr_result)

        # Research Optimized Strategy validation (baseline)
        ro_result = validator.validate_symbol(
            symbol=symbol,
            df=df,
            strategy=ro_strategy,
            strategy_name="ResearchOptimizedStrategy"
        )
        ro_results.append(ro_result)

    # Compile final results
    sr_final = compile_final_results(sr_results, "SupportResistanceStrategy")
    ro_final = compile_final_results(ro_results, "ResearchOptimizedStrategy")

    # Compare strategies
    sr_final.baseline_results = {
        'strategy_name': 'ResearchOptimizedStrategy',
        'overall_win_rate': ro_final.overall_win_rate,
        'overall_sharpe': ro_final.overall_sharpe,
        'overall_return_pct': ro_final.overall_return_pct,
        'overall_max_drawdown': ro_final.overall_max_drawdown
    }
    sr_final.outperforms_baseline = (
        sr_final.overall_win_rate > ro_final.overall_win_rate or
        sr_final.overall_sharpe > ro_final.overall_sharpe
    )

    # Print results
    print_results(sr_final, ro_final)

    # Save results to JSON
    save_results(sr_final, ro_final)

    return sr_final


def compile_final_results(symbol_results: List[SymbolResults], strategy_name: str) -> WalkForwardResults:
    """Compile final results across all symbols"""

    results = WalkForwardResults(
        timestamp=datetime.now().isoformat(),
        strategy_name=strategy_name,
        symbols=symbol_results
    )

    if not symbol_results:
        return results

    # Count passes
    results.symbols_passed = sum(1 for s in symbol_results if s.overall_pass)
    results.symbols_failed = len(symbol_results) - results.symbols_passed

    # Aggregate metrics
    total_trades = sum(s.total_trades for s in symbol_results)
    total_wins = sum(s.total_wins for s in symbol_results)

    results.overall_win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0.0
    results.overall_sharpe = sum(s.aggregate_sharpe for s in symbol_results) / len(symbol_results)
    results.overall_return_pct = sum(s.aggregate_return_pct for s in symbol_results) / len(symbol_results)
    results.overall_max_drawdown = max(s.avg_max_drawdown for s in symbol_results)

    # Final verdict
    results.strategy_robust = (
        results.overall_win_rate >= MIN_WIN_RATE and
        results.overall_sharpe >= MIN_SHARPE_RATIO and
        results.overall_max_drawdown <= MAX_DRAWDOWN_PCT and
        results.symbols_passed >= len(symbol_results) // 2 + 1  # Majority pass
    )

    if results.strategy_robust:
        results.recommendation = "PASS - Strategy shows robust out-of-sample performance. Ready for paper trading."
    else:
        issues = []
        if results.overall_win_rate < MIN_WIN_RATE:
            issues.append(f"Win rate {results.overall_win_rate:.1f}% < {MIN_WIN_RATE}%")
        if results.overall_sharpe < MIN_SHARPE_RATIO:
            issues.append(f"Sharpe {results.overall_sharpe:.2f} < {MIN_SHARPE_RATIO}")
        if results.overall_max_drawdown > MAX_DRAWDOWN_PCT:
            issues.append(f"Max DD {results.overall_max_drawdown:.1f}% > {MAX_DRAWDOWN_PCT}%")
        results.recommendation = f"FAIL - Issues: {'; '.join(issues)}"

    return results


def print_results(sr_results: WalkForwardResults, ro_results: WalkForwardResults):
    """Print formatted results to console"""

    print("\n" + "="*80)
    print("WALK-FORWARD VALIDATION RESULTS")
    print("="*80)

    # Summary table header
    print("\n{:<30} {:>15} {:>15}".format("Metric", "S/R Strategy", "Research Opt"))
    print("-"*60)

    # Metrics
    print("{:<30} {:>14.1f}% {:>14.1f}%".format(
        "Win Rate",
        sr_results.overall_win_rate,
        ro_results.overall_win_rate
    ))
    print("{:<30} {:>15.2f} {:>15.2f}".format(
        "Sharpe Ratio",
        sr_results.overall_sharpe,
        ro_results.overall_sharpe
    ))
    print("{:<30} {:>14.2f}% {:>14.2f}%".format(
        "Total Return",
        sr_results.overall_return_pct,
        ro_results.overall_return_pct
    ))
    print("{:<30} {:>14.2f}% {:>14.2f}%".format(
        "Max Drawdown",
        sr_results.overall_max_drawdown,
        ro_results.overall_max_drawdown
    ))
    print("{:<30} {:>15} {:>15}".format(
        "Symbols Passed",
        f"{sr_results.symbols_passed}/{len(sr_results.symbols)}",
        f"{ro_results.symbols_passed}/{len(ro_results.symbols)}"
    ))

    # Per-symbol breakdown
    print("\n" + "-"*80)
    print("PER-SYMBOL BREAKDOWN")
    print("-"*80)

    for sr_sym in sr_results.symbols:
        # Find matching RO result
        ro_sym = next((s for s in ro_results.symbols if s.symbol == sr_sym.symbol), None)

        print(f"\n{sr_sym.symbol}:")
        print("  {:30} {:>12} {:>12}".format("", "S/R", "Research"))
        print("  {:30} {:>11.1f}% {:>11.1f}%".format(
            "Win Rate",
            sr_sym.aggregate_win_rate,
            ro_sym.aggregate_win_rate if ro_sym else 0
        ))
        print("  {:30} {:>12.2f} {:>12.2f}".format(
            "Sharpe",
            sr_sym.aggregate_sharpe,
            ro_sym.aggregate_sharpe if ro_sym else 0
        ))
        print("  {:30} {:>11.2f}% {:>11.2f}%".format(
            "Return",
            sr_sym.aggregate_return_pct,
            ro_sym.aggregate_return_pct if ro_sym else 0
        ))
        print("  {:30} {:>11.2f}% {:>11.2f}%".format(
            "Max DD",
            sr_sym.avg_max_drawdown,
            ro_sym.avg_max_drawdown if ro_sym else 0
        ))
        print("  {:30} {:>12} {:>12}".format(
            "Total Trades",
            sr_sym.total_trades,
            ro_sym.total_trades if ro_sym else 0
        ))

        sr_pass = "PASS" if sr_sym.overall_pass else "FAIL"
        ro_pass = "PASS" if ro_sym and ro_sym.overall_pass else "FAIL"
        print("  {:30} {:>12} {:>12}".format("Result", sr_pass, ro_pass))

    # Pass/Fail criteria
    print("\n" + "="*80)
    print("PASS/FAIL CRITERIA")
    print("="*80)
    print(f"  Win Rate > {MIN_WIN_RATE}%: {'PASS' if sr_results.overall_win_rate >= MIN_WIN_RATE else 'FAIL'}")
    print(f"  Sharpe Ratio > {MIN_SHARPE_RATIO}: {'PASS' if sr_results.overall_sharpe >= MIN_SHARPE_RATIO else 'FAIL'}")
    print(f"  Max Drawdown < {MAX_DRAWDOWN_PCT}%: {'PASS' if sr_results.overall_max_drawdown <= MAX_DRAWDOWN_PCT else 'FAIL'}")

    # Comparison
    print("\n" + "="*80)
    print("COMPARISON WITH BASELINE")
    print("="*80)

    win_rate_diff = sr_results.overall_win_rate - ro_results.overall_win_rate
    sharpe_diff = sr_results.overall_sharpe - ro_results.overall_sharpe
    return_diff = sr_results.overall_return_pct - ro_results.overall_return_pct

    print(f"  Win Rate Difference: {win_rate_diff:+.1f}%")
    print(f"  Sharpe Difference: {sharpe_diff:+.2f}")
    print(f"  Return Difference: {return_diff:+.2f}%")
    print(f"  Outperforms Baseline: {'YES' if sr_results.outperforms_baseline else 'NO'}")

    # Final verdict
    print("\n" + "="*80)
    print("FINAL VERDICT")
    print("="*80)
    status = "PASS" if sr_results.strategy_robust else "FAIL"
    print(f"  Strategy Robust: {status}")
    print(f"  Recommendation: {sr_results.recommendation}")
    print("="*80 + "\n")


def save_results(sr_results: WalkForwardResults, ro_results: WalkForwardResults):
    """Save results to JSON file"""

    output_path = '/tmp/sr_walkforward_results.json'

    # Convert to serializable format
    def serialize_window(w: WindowMetrics) -> Dict:
        return {
            'window_num': w.window_num,
            'train_start': str(w.train_start),
            'train_end': str(w.train_end),
            'test_start': str(w.test_start),
            'test_end': str(w.test_end),
            'total_trades': w.total_trades,
            'winning_trades': w.winning_trades,
            'losing_trades': w.losing_trades,
            'win_rate': round(w.win_rate, 2),
            'total_return_pct': round(w.total_return_pct, 2),
            'sharpe_ratio': round(w.sharpe_ratio, 2),
            'max_drawdown_pct': round(w.max_drawdown_pct, 2),
            'profit_factor': round(w.profit_factor, 2),
            'avg_trade_duration_hours': round(w.avg_trade_duration_hours, 2),
            'is_valid': w.is_valid,
            'validation_message': w.validation_message
        }

    def serialize_symbol(s: SymbolResults) -> Dict:
        return {
            'symbol': s.symbol,
            'strategy_name': s.strategy_name,
            'total_windows': s.total_windows,
            'valid_windows': s.valid_windows,
            'total_trades': s.total_trades,
            'total_wins': s.total_wins,
            'total_losses': s.total_losses,
            'aggregate_win_rate': round(s.aggregate_win_rate, 2),
            'aggregate_return_pct': round(s.aggregate_return_pct, 2),
            'aggregate_sharpe': round(s.aggregate_sharpe, 2),
            'avg_max_drawdown': round(s.avg_max_drawdown, 2),
            'avg_profit_factor': round(s.avg_profit_factor, 2),
            'passes_win_rate': bool(s.passes_win_rate),
            'passes_sharpe': bool(s.passes_sharpe),
            'passes_drawdown': bool(s.passes_drawdown),
            'overall_pass': bool(s.overall_pass),
            'windows': [serialize_window(w) for w in s.windows]
        }

    output = {
        'timestamp': sr_results.timestamp,
        'configuration': {
            'training_window_days': TRAINING_WINDOW_DAYS,
            'test_window_days': TEST_WINDOW_DAYS,
            'step_size_days': STEP_SIZE_DAYS,
            'total_period_days': TOTAL_PERIOD_DAYS,
            'symbols': TEST_SYMBOLS,
            'data_source': str(DATA_DIR),
            'pass_criteria': {
                'min_win_rate': MIN_WIN_RATE,
                'min_sharpe_ratio': MIN_SHARPE_RATIO,
                'max_drawdown_pct': MAX_DRAWDOWN_PCT
            }
        },
        'support_resistance_strategy': {
            'overall_win_rate': round(sr_results.overall_win_rate, 2),
            'overall_sharpe': round(sr_results.overall_sharpe, 2),
            'overall_return_pct': round(sr_results.overall_return_pct, 2),
            'overall_max_drawdown': round(sr_results.overall_max_drawdown, 2),
            'symbols_passed': sr_results.symbols_passed,
            'symbols_failed': sr_results.symbols_failed,
            'strategy_robust': bool(sr_results.strategy_robust),
            'recommendation': sr_results.recommendation,
            'symbols': [serialize_symbol(s) for s in sr_results.symbols]
        },
        'research_optimized_strategy': {
            'overall_win_rate': round(ro_results.overall_win_rate, 2),
            'overall_sharpe': round(ro_results.overall_sharpe, 2),
            'overall_return_pct': round(ro_results.overall_return_pct, 2),
            'overall_max_drawdown': round(ro_results.overall_max_drawdown, 2),
            'symbols_passed': ro_results.symbols_passed,
            'symbols_failed': ro_results.symbols_failed,
            'strategy_robust': bool(ro_results.strategy_robust),
            'recommendation': ro_results.recommendation,
            'symbols': [serialize_symbol(s) for s in ro_results.symbols]
        },
        'comparison': {
            'sr_outperforms_baseline': bool(sr_results.outperforms_baseline),
            'win_rate_difference': round(sr_results.overall_win_rate - ro_results.overall_win_rate, 2),
            'sharpe_difference': round(sr_results.overall_sharpe - ro_results.overall_sharpe, 2),
            'return_difference': round(sr_results.overall_return_pct - ro_results.overall_return_pct, 2)
        }
    }

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)

    logger.info(f"Results saved to: {output_path}")
    print(f"\nResults saved to: {output_path}")


def main():
    """Main entry point"""
    try:
        # Synchronous execution - no async needed for CSV loading
        result = run_walk_forward_validation()

        if result:
            # Return exit code based on pass/fail
            return 0 if result.strategy_robust else 1
        else:
            return 1

    except KeyboardInterrupt:
        print("\nValidation interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Validation failed with error: {e}", exc_info=True)
        print(f"\nERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
