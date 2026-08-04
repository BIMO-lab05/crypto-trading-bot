#!/usr/bin/env python3
"""
Comprehensive Backtesting Framework for SQZMOM Strategy
Purpose: Test Squeeze Momentum strategy on real historical cryptocurrency data

Features:
- Multiple symbol backtesting
- Parameter optimization
- Comprehensive performance metrics
- Trade-by-trade analysis
- Statistical significance testing
- Market condition analysis
- Detailed reporting
"""

import asyncpg
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from decimal import Decimal
import json
import logging
import sys
import os

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Repo root on sys.path so `shared.account` resolves. This file is HOST-RUN
# ONLY -- services/technical-analysis/Dockerfile copies only `app/`, so
# `backtesting/` never ships in the image. That is what makes importing the
# declaration of record directly legal here, unlike code under
# `services/*/app/**`. See the table in `shared/account.py`.
_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..')
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.indicators.squeeze_momentum import SqueezeMomentumIndicator
from app.strategies.squeeze_momentum_strategy import SqueezeMomentumStrategy
from shared.account import PAPER_INITIAL_BALANCE

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Trade:
    """Represents a single trade with entry, exit, and P&L"""

    def __init__(
        self,
        symbol: str,
        direction: str,  # 'LONG' or 'SHORT'
        entry_time: datetime,
        entry_price: float,
        position_size: float
    ):
        """Initialize trade"""
        self.symbol = symbol
        self.direction = direction
        self.entry_time = entry_time
        self.entry_price = entry_price
        self.position_size = position_size

        self.exit_time: Optional[datetime] = None
        self.exit_price: Optional[float] = None
        self.exit_reason: Optional[str] = None

        self.pnl: float = 0.0
        self.pnl_pct: float = 0.0
        self.commission: float = 0.0
        self.net_pnl: float = 0.0
        self.duration_hours: float = 0.0

    def close(
        self,
        exit_time: datetime,
        exit_price: float,
        exit_reason: str,
        commission_rate: float
    ):
        """Close trade and calculate P&L"""
        self.exit_time = exit_time
        self.exit_price = exit_price
        self.exit_reason = exit_reason

        # Calculate P&L
        if self.direction == 'LONG':
            self.pnl = (exit_price - self.entry_price) * self.position_size
            self.pnl_pct = ((exit_price - self.entry_price) / self.entry_price) * 100
        else:  # SHORT
            self.pnl = (self.entry_price - exit_price) * self.position_size
            self.pnl_pct = ((self.entry_price - exit_price) / self.entry_price) * 100

        # Calculate commission (entry + exit)
        entry_value = self.entry_price * self.position_size
        exit_value = exit_price * self.position_size
        self.commission = (entry_value + exit_value) * commission_rate

        # Net P&L after commission
        self.net_pnl = self.pnl - self.commission

        # Duration
        self.duration_hours = (exit_time - self.entry_time).total_seconds() / 3600

    def to_dict(self) -> Dict:
        """Convert trade to dictionary"""
        return {
            'symbol': self.symbol,
            'direction': self.direction,
            'entry_time': self.entry_time.isoformat() if self.entry_time else None,
            'entry_price': round(self.entry_price, 2),
            'exit_time': self.exit_time.isoformat() if self.exit_time else None,
            'exit_price': round(self.exit_price, 2) if self.exit_price else None,
            'exit_reason': self.exit_reason,
            'position_size': round(self.position_size, 4),
            'pnl': round(self.pnl, 2),
            'pnl_pct': round(self.pnl_pct, 2),
            'commission': round(self.commission, 2),
            'net_pnl': round(self.net_pnl, 2),
            'duration_hours': round(self.duration_hours, 1)
        }


class SQZMOMBacktester:
    """
    Backtest SQZMOM strategy on historical data

    Features:
    - Multiple symbols backtesting
    - Multiple parameter sets
    - Detailed performance metrics
    - Trade-by-trade analysis
    - Statistical significance testing
    - Market condition analysis
    """

    def __init__(
        self,
        db_config: Dict,
        # FIX 2026-08-03 (capital audit): was 10000.0, 100x the real account.
        # NOTE this default is SHADOWED for the four standalone runners
        # (run_backtest.py, run_btc_eth_backtest.py, quick_test.py,
        # optimize_parameters.py), which pass 10000.0 explicitly. Their runtime
        # behaviour is unchanged by this fix -- they are a known residual,
        # recorded in the EXPANSION_QUEUE of tests/test_account_size_invariant.py.
        initial_capital: float = PAPER_INITIAL_BALANCE,
        commission: float = 0.001,  # 0.1% per trade
        risk_per_trade: float = 0.02  # 2% risk per trade
    ):
        """
        Initialize backtester

        Args:
            db_config: Database connection configuration
            initial_capital: Starting capital in USD. Defaults to the
                declared account size (shared.account.PAPER_INITIAL_BALANCE).
            commission: Commission rate per trade (0.001 = 0.1%)
            risk_per_trade: Maximum risk per trade as fraction of capital (0.02 = 2%)
        """
        self.db_config = db_config
        self.initial_capital = initial_capital
        self.commission_rate = commission
        self.risk_per_trade = risk_per_trade

        self.conn: Optional[asyncpg.Connection] = None
        self.trades: List[Trade] = []
        self.equity_curve: pd.DataFrame = None
        self.current_capital: float = initial_capital

        logger.info(
            f"Backtester initialized: capital=${initial_capital:,.2f}, "
            f"commission={commission*100:.2f}%, risk_per_trade={risk_per_trade*100:.1f}%"
        )

    async def connect_db(self):
        """Connect to TimescaleDB"""
        try:
            self.conn = await asyncpg.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                database=self.db_config['database'],
                user=self.db_config['user'],
                password=self.db_config['password']
            )
            logger.info("Connected to TimescaleDB")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def close(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()
            logger.info("Database connection closed")

    async def fetch_historical_data(
        self,
        symbol: str,
        interval: str = "60",
        start_date: str = None,
        end_date: str = None
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data from TimescaleDB

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Candle interval in minutes (default: 60 = 1 hour)
            start_date: Start date (ISO format or None for all)
            end_date: End date (ISO format or None for all)

        Returns:
            DataFrame with columns: time, open, high, low, close, volume
        """
        query = """
            SELECT time, open, high, low, close, volume
            FROM market_data.candles
            WHERE symbol = $1 AND interval = $2
        """

        params = [symbol, interval]

        if start_date:
            query += " AND time >= $3"
            params.append(start_date)
        if end_date:
            query += f" AND time <= ${len(params) + 1}"
            params.append(end_date)

        query += " ORDER BY time ASC"

        try:
            rows = await self.conn.fetch(query, *params)

            if not rows:
                logger.warning(f"No data found for {symbol}")
                return pd.DataFrame()

            # Convert to DataFrame and handle Decimal types
            df = pd.DataFrame(rows, columns=['time', 'open', 'high', 'low', 'close', 'volume'])

            # Convert Decimal to float for all numeric columns
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].apply(lambda x: float(x) if isinstance(x, Decimal) else x)

            df['time'] = pd.to_datetime(df['time'])
            df = df.set_index('time')

            logger.info(f"Fetched {len(df)} candles for {symbol}")
            return df

        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return pd.DataFrame()

    async def run_backtest(
        self,
        symbol: str,
        strategy_params: Dict = None,
        verbose: bool = True
    ) -> Dict:
        """
        Run backtest on a single symbol

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            strategy_params: Strategy configuration dict
            verbose: Print progress

        Returns:
            Dictionary with comprehensive metrics
        """
        if verbose:
            logger.info(f"Starting backtest for {symbol}...")

        # Reset for this backtest
        self.trades = []
        self.current_capital = self.initial_capital
        equity_history = []

        # Fetch historical data
        df = await self.fetch_historical_data(symbol)

        if df.empty:
            logger.error(f"No data available for {symbol}")
            return self._empty_results(symbol)

        # Initialize strategy
        if strategy_params is None:
            strategy_params = {
                'min_momentum_threshold': 0.5,
                'stop_loss_pct': 2.0,
                'take_profit_pct': 4.0,
                'require_squeeze_release': False,  # More trades for backtesting
                'require_volume_confirmation': False
            }

        indicator = SqueezeMomentumIndicator(
            bb_length=strategy_params.get('bb_length', 20),
            bb_mult=strategy_params.get('bb_mult', 2.0),
            kc_length=strategy_params.get('kc_length', 20),
            kc_mult=strategy_params.get('kc_mult', 1.5)
        )

        strategy = SqueezeMomentumStrategy(
            sqzmom_indicator=indicator,
            min_momentum_threshold=strategy_params['min_momentum_threshold'],
            stop_loss_pct=strategy_params['stop_loss_pct'],
            take_profit_pct=strategy_params['take_profit_pct'],
            require_squeeze_release=strategy_params['require_squeeze_release'],
            require_volume_confirmation=strategy_params['require_volume_confirmation']
        )

        # Calculate indicator for entire dataset
        df_with_signals = indicator.calculate(df)

        if df_with_signals is None:
            logger.error(f"Failed to calculate indicators for {symbol}")
            return self._empty_results(symbol)

        # Track current position
        current_trade: Optional[Trade] = None

        # Simulate trading bar by bar
        for i in range(len(df_with_signals)):
            # Get data up to current bar (for strategy analysis)
            current_df = df_with_signals.iloc[:i+1]
            current_row = current_df.iloc[-1]
            current_time = current_df.index[-1]
            current_price = float(current_row['close'])

            # Record equity
            equity_history.append({
                'time': current_time,
                'equity': self.current_capital,
                'price': current_price
            })

            # Check if we should exit current position
            if current_trade is not None:
                should_exit = strategy.should_exit(
                    current_df,
                    current_trade.direction,
                    current_trade.entry_price
                )

                if should_exit:
                    # Close trade
                    current_trade.close(
                        exit_time=current_time,
                        exit_price=current_price,
                        exit_reason="Strategy exit signal",
                        commission_rate=self.commission_rate
                    )

                    # Update capital
                    self.current_capital += current_trade.net_pnl

                    # Record trade
                    self.trades.append(current_trade)

                    if verbose and len(self.trades) % 10 == 0:
                        logger.info(f"  Closed trade {len(self.trades)}: {current_trade.direction} "
                                  f"P&L: ${current_trade.net_pnl:.2f} ({current_trade.pnl_pct:.2f}%)")

                    current_trade = None

            # Check for new entry if no position
            if current_trade is None:
                # Analyze for entry signal
                signal = strategy.analyze(current_df)

                if signal['action'] in ['BUY', 'SELL']:
                    # Calculate position size based on risk management
                    position_size = self._calculate_position_size(
                        capital=self.current_capital,
                        entry_price=current_price,
                        stop_loss_pct=strategy_params['stop_loss_pct']
                    )

                    # Open new trade
                    direction = 'LONG' if signal['action'] == 'BUY' else 'SHORT'
                    current_trade = Trade(
                        symbol=symbol,
                        direction=direction,
                        entry_time=current_time,
                        entry_price=current_price,
                        position_size=position_size
                    )

                    if verbose:
                        logger.debug(f"  Opened {direction} trade at ${current_price:.2f}, "
                                   f"size={position_size:.4f}, reason: {signal['reason']}")

        # Close any open position at end
        if current_trade is not None:
            final_row = df_with_signals.iloc[-1]
            final_time = df_with_signals.index[-1]
            final_price = float(final_row['close'])

            current_trade.close(
                exit_time=final_time,
                exit_price=final_price,
                exit_reason="End of backtest period",
                commission_rate=self.commission_rate
            )

            self.current_capital += current_trade.net_pnl
            self.trades.append(current_trade)

        # Create equity curve DataFrame
        self.equity_curve = pd.DataFrame(equity_history)
        if not self.equity_curve.empty:
            self.equity_curve = self.equity_curve.set_index('time')

        # Calculate metrics
        metrics = self.calculate_metrics(self.trades, self.equity_curve)
        metrics['symbol'] = symbol
        metrics['strategy_params'] = strategy_params

        if verbose:
            logger.info(f"Backtest completed for {symbol}: {metrics['total_trades']} trades, "
                       f"{metrics['total_return_pct']:.2f}% return")

        return metrics

    def _calculate_position_size(
        self,
        capital: float,
        entry_price: float,
        stop_loss_pct: float
    ) -> float:
        """
        Calculate position size based on risk management

        Args:
            capital: Current available capital
            entry_price: Entry price for trade
            stop_loss_pct: Stop loss percentage

        Returns:
            Position size in base currency
        """
        # Risk amount (e.g., 2% of capital)
        risk_amount = capital * self.risk_per_trade

        # Calculate position size
        # risk_amount = position_size * entry_price * (stop_loss_pct / 100)
        # position_size = risk_amount / (entry_price * stop_loss_pct / 100)

        position_size = risk_amount / (entry_price * stop_loss_pct / 100)

        # Ensure position doesn't exceed available capital
        max_position = capital / entry_price
        position_size = min(position_size, max_position * 0.95)  # Use max 95% of capital

        return position_size

    def _empty_results(self, symbol: str) -> Dict:
        """Return empty results structure"""
        return {
            'symbol': symbol,
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'total_pnl': 0.0,
            'total_return_pct': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'profit_factor': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'largest_win': 0.0,
            'largest_loss': 0.0,
            'avg_trade_duration_hours': 0.0,
            'long_trades': 0,
            'short_trades': 0,
            'long_win_rate': 0.0,
            'short_win_rate': 0.0,
            'gross_profit': 0.0,
            'gross_loss': 0.0,
            'final_capital': self.initial_capital,
            'trades': []
        }

    def calculate_metrics(self, trades: List[Trade], equity_curve: pd.DataFrame) -> Dict:
        """
        Calculate comprehensive performance metrics

        Args:
            trades: List of Trade objects
            equity_curve: DataFrame with equity over time

        Returns:
            Dictionary with all performance metrics
        """
        if not trades:
            return self._empty_results("unknown")

        # Basic trade statistics
        total_trades = len(trades)
        winning_trades = [t for t in trades if t.net_pnl > 0]
        losing_trades = [t for t in trades if t.net_pnl <= 0]

        num_wins = len(winning_trades)
        num_losses = len(losing_trades)
        win_rate = (num_wins / total_trades * 100) if total_trades > 0 else 0.0

        # P&L statistics
        total_pnl = sum(t.net_pnl for t in trades)
        total_return_pct = (total_pnl / self.initial_capital) * 100

        avg_win = np.mean([t.net_pnl for t in winning_trades]) if winning_trades else 0.0
        avg_loss = np.mean([t.net_pnl for t in losing_trades]) if losing_trades else 0.0
        largest_win = max([t.net_pnl for t in winning_trades]) if winning_trades else 0.0
        largest_loss = min([t.net_pnl for t in losing_trades]) if losing_trades else 0.0

        # Profit factor
        gross_profit = sum(t.net_pnl for t in winning_trades)
        gross_loss = abs(sum(t.net_pnl for t in losing_trades))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0.0

        # Duration statistics
        avg_duration = np.mean([t.duration_hours for t in trades if t.duration_hours])

        # Sharpe ratio (risk-adjusted return)
        if equity_curve is not None and not equity_curve.empty:
            returns = equity_curve['equity'].pct_change().dropna()
            if len(returns) > 0 and returns.std() > 0:
                # Annualized Sharpe ratio (assuming 24/7 crypto trading)
                sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(365 * 24)  # hourly data
            else:
                sharpe_ratio = 0.0

            # Maximum drawdown
            max_drawdown = self._calculate_max_drawdown(equity_curve['equity'])
        else:
            sharpe_ratio = 0.0
            max_drawdown = 0.0

        # Long vs Short statistics
        long_trades = [t for t in trades if t.direction == 'LONG']
        short_trades = [t for t in trades if t.direction == 'SHORT']

        long_win_rate = (len([t for t in long_trades if t.net_pnl > 0]) / len(long_trades) * 100) if long_trades else 0.0
        short_win_rate = (len([t for t in short_trades if t.net_pnl > 0]) / len(short_trades) * 100) if short_trades else 0.0

        return {
            'total_trades': total_trades,
            'winning_trades': num_wins,
            'losing_trades': num_losses,
            'win_rate': round(win_rate, 2),
            'total_pnl': round(total_pnl, 2),
            'total_return_pct': round(total_return_pct, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'max_drawdown': round(max_drawdown, 2),
            'profit_factor': round(profit_factor, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'largest_win': round(largest_win, 2),
            'largest_loss': round(largest_loss, 2),
            'avg_trade_duration_hours': round(avg_duration, 1),
            'long_trades': len(long_trades),
            'short_trades': len(short_trades),
            'long_win_rate': round(long_win_rate, 2),
            'short_win_rate': round(short_win_rate, 2),
            'gross_profit': round(gross_profit, 2),
            'gross_loss': round(gross_loss, 2),
            'final_capital': round(self.current_capital, 2),
            'trades': [t.to_dict() for t in trades]
        }

    def _calculate_max_drawdown(self, equity: pd.Series) -> float:
        """
        Calculate maximum drawdown percentage

        Args:
            equity: Series of equity values over time

        Returns:
            Maximum drawdown as percentage
        """
        # Calculate running maximum
        running_max = equity.expanding().max()

        # Calculate drawdown at each point
        drawdown = (equity - running_max) / running_max * 100

        # Return maximum drawdown (most negative value)
        return abs(drawdown.min())

    async def run_multi_symbol_backtest(
        self,
        symbols: List[str],
        strategy_params: Dict = None
    ) -> Dict:
        """
        Run backtest across multiple symbols (portfolio approach)

        Args:
            symbols: List of trading pairs
            strategy_params: Strategy configuration

        Returns:
            Dictionary with combined and per-symbol results
        """
        logger.info(f"Starting multi-symbol backtest for {len(symbols)} symbols...")

        per_symbol_results = {}
        all_trades = []

        # Run backtest for each symbol
        for symbol in symbols:
            results = await self.run_backtest(symbol, strategy_params, verbose=False)
            per_symbol_results[symbol] = results
            all_trades.extend(self.trades)

        # Calculate combined metrics
        combined_pnl = sum(results['total_pnl'] for results in per_symbol_results.values())
        combined_return_pct = (combined_pnl / (self.initial_capital * len(symbols))) * 100
        total_trades = sum(results['total_trades'] for results in per_symbol_results.values())

        winning_trades = sum(results['winning_trades'] for results in per_symbol_results.values())
        losing_trades = sum(results['losing_trades'] for results in per_symbol_results.values())
        combined_win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        # Average metrics across symbols
        avg_sharpe = np.mean([results['sharpe_ratio'] for results in per_symbol_results.values()])
        avg_max_dd = np.mean([results['max_drawdown'] for results in per_symbol_results.values()])
        avg_profit_factor = np.mean([results['profit_factor'] for results in per_symbol_results.values() if results['profit_factor'] > 0])

        combined_metrics = {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': round(combined_win_rate, 2),
            'total_pnl': round(combined_pnl, 2),
            'total_return_pct': round(combined_return_pct, 2),
            'avg_sharpe_ratio': round(avg_sharpe, 2),
            'avg_max_drawdown': round(avg_max_dd, 2),
            'avg_profit_factor': round(avg_profit_factor, 2)
        }

        logger.info(f"Multi-symbol backtest completed: {total_trades} total trades, "
                   f"{combined_return_pct:.2f}% combined return")

        return {
            'symbols': symbols,
            'combined_metrics': combined_metrics,
            'per_symbol_metrics': per_symbol_results,
            'strategy_params': strategy_params
        }

    async def optimize_parameters(
        self,
        symbol: str,
        param_ranges: Dict
    ) -> Dict:
        """
        Optimize strategy parameters using grid search

        Args:
            symbol: Trading pair to optimize on
            param_ranges: Dictionary of parameter ranges to test
                Example: {
                    'bb_length': [15, 20, 25],
                    'kc_length': [15, 20, 25],
                    'stop_loss_pct': [1.5, 2.0, 2.5],
                    'take_profit_pct': [3.0, 4.0, 5.0],
                    'min_momentum_threshold': [0.3, 0.5, 0.7]
                }

        Returns:
            Dictionary with best parameters and all results
        """
        logger.info(f"Starting parameter optimization for {symbol}...")
        logger.info(f"Parameter ranges: {param_ranges}")

        # Generate all parameter combinations
        from itertools import product

        param_names = list(param_ranges.keys())
        param_values = list(param_ranges.values())
        combinations = list(product(*param_values))

        logger.info(f"Testing {len(combinations)} parameter combinations...")

        all_results = []
        best_return = -float('inf')
        best_params = None
        best_metrics = None

        # Test each combination
        for i, combo in enumerate(combinations):
            params = dict(zip(param_names, combo))

            # Set default values for params not in ranges
            strategy_params = {
                'bb_length': params.get('bb_length', 20),
                'kc_length': params.get('kc_length', 20),
                'min_momentum_threshold': params.get('min_momentum_threshold', 0.5),
                'stop_loss_pct': params.get('stop_loss_pct', 2.0),
                'take_profit_pct': params.get('take_profit_pct', 4.0),
                'require_squeeze_release': False,
                'require_volume_confirmation': False
            }

            # Run backtest
            metrics = await self.run_backtest(symbol, strategy_params, verbose=False)

            result = {
                'params': strategy_params,
                'return_pct': metrics['total_return_pct'],
                'sharpe_ratio': metrics['sharpe_ratio'],
                'max_drawdown': metrics['max_drawdown'],
                'win_rate': metrics['win_rate'],
                'total_trades': metrics['total_trades'],
                'profit_factor': metrics['profit_factor']
            }

            all_results.append(result)

            # Check if this is the best so far
            if metrics['total_return_pct'] > best_return:
                best_return = metrics['total_return_pct']
                best_params = strategy_params.copy()
                best_metrics = metrics

            if (i + 1) % 10 == 0:
                logger.info(f"  Tested {i + 1}/{len(combinations)} combinations...")

        # Sort results by return
        all_results.sort(key=lambda x: x['return_pct'], reverse=True)

        logger.info(f"Optimization completed. Best return: {best_return:.2f}%")

        return {
            'symbol': symbol,
            'best_params': best_params,
            'best_return': round(best_return, 2),
            'best_metrics': best_metrics,
            'all_results': all_results[:20],  # Top 20 results
            'total_combinations_tested': len(combinations)
        }

    def generate_report(self, results: Dict) -> str:
        """
        Generate comprehensive backtesting report in Markdown format

        Args:
            results: Dictionary containing backtest results

        Returns:
            Markdown formatted report string
        """
        report = []

        report.append("# SQZMOM Strategy Backtest Report")
        report.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("\n---\n")

        # Executive Summary
        report.append("## Executive Summary\n")

        if 'individual' in results:
            # Individual symbol backtests
            for symbol, metrics in results['individual'].items():
                report.append(f"### {symbol}\n")
                report.append(f"- **Date Range**: {metrics.get('start_date', 'N/A')} to {metrics.get('end_date', 'N/A')}")
                report.append(f"- **Initial Capital**: ${self.initial_capital:,.2f}")
                report.append(f"- **Final Capital**: ${metrics['final_capital']:,.2f}")
                report.append(f"- **Total Return**: {metrics['total_return_pct']:.2f}%")
                report.append(f"- **Total Trades**: {metrics['total_trades']}")
                report.append(f"- **Win Rate**: {metrics['win_rate']:.2f}%")
                report.append(f"- **Sharpe Ratio**: {metrics['sharpe_ratio']:.2f}")
                report.append(f"- **Max Drawdown**: {metrics['max_drawdown']:.2f}%\n")

        if 'portfolio' in results:
            # Portfolio results
            combined = results['portfolio']['combined_metrics']
            report.append("### Portfolio Performance\n")
            report.append(f"- **Symbols Tested**: {', '.join(results['portfolio']['symbols'])}")
            report.append(f"- **Total Trades**: {combined['total_trades']}")
            report.append(f"- **Win Rate**: {combined['win_rate']:.2f}%")
            report.append(f"- **Combined Return**: {combined['total_return_pct']:.2f}%")
            report.append(f"- **Average Sharpe Ratio**: {combined['avg_sharpe_ratio']:.2f}\n")

        if 'optimization' in results:
            # Optimization results
            opt = results['optimization']
            report.append("### Parameter Optimization\n")
            report.append(f"- **Optimized Symbol**: {opt['symbol']}")
            report.append(f"- **Best Return**: {opt['best_return']:.2f}%")
            report.append(f"- **Combinations Tested**: {opt['total_combinations_tested']}")
            report.append("\n**Best Parameters**:")
            for param, value in opt['best_params'].items():
                report.append(f"- {param}: {value}")
            report.append("")

        report.append("\n---\n")

        return "\n".join(report)
