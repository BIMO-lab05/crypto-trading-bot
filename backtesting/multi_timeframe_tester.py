"""
Multi-Timeframe Strategy Testing Framework
========================================

This module implements testing capabilities across multiple timeframes (15m, 4H, 1D)
to evaluate strategy performance across different market conditions and time horizons.

Features:
1. Multi-timeframe data aggregation
2. Cross-timeframe signal validation
3. Performance comparison across timeframes
4. Timeframe-specific parameter optimization
5. Correlation analysis between timeframes
"""

import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import asyncio
from enum import Enum

# Import existing strategy modules
from strategies.enhanced_mean_reversion_strategy import EnhancedMeanReversionStrategy, EnhancedMeanReversionConfig
from strategies.enhanced_breakout_strategy import EnhancedBreakoutStrategy, EnhancedBreakoutConfig
from adaptive_strategy_controller import adapt_strategy_for_regime

logger = logging.getLogger(__name__)


class Timeframe(Enum):
    """Supported timeframes for testing"""
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"
    DAY_7 = "7d"


@dataclass
class TimeframeTestConfig:
    """Configuration for multi-timeframe testing"""
    # Timeframes to test
    timeframes: List[Timeframe] = None
    
    # Test duration parameters
    test_duration_days: int = 30
    warmup_period_days: int = 7  # Days of data needed for indicator calculations
    
    # Strategy parameters
    strategy_type: str = "mean_reversion"  # "mean_reversion", "breakout", "adaptive"
    
    # Performance metrics to track
    metrics_to_track: List[str] = None
    
    # Correlation analysis
    enable_correlation_analysis: bool = True
    correlation_lookback_days: int = 7
    
    def __post_init__(self):
        if self.timeframes is None:
            self.timeframes = [Timeframe.MINUTE_15, Timeframe.HOUR_4, Timeframe.DAY_1]
        if self.metrics_to_track is None:
            self.metrics_to_track = ["sharpe_ratio", "win_rate", "profit_factor", "max_drawdown", "total_return"]


@dataclass
class TimeframePerformance:
    """Performance results for a specific timeframe"""
    timeframe: Timeframe
    total_return: float
    sharpe_ratio: float
    win_rate: float
    profit_factor: float
    max_drawdown: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    best_trade: float
    worst_trade: float
    trade_duration_avg: float  # Average trade duration in hours
    volatility: float  # Annualized volatility
    sortino_ratio: float  # Sortino ratio (downside deviation)
    

@dataclass
class MultiTimeframeResults:
    """Results from multi-timeframe testing"""
    strategy_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    timeframe_results: Dict[Timeframe, TimeframePerformance]
    correlation_matrix: Optional[np.ndarray] = None
    best_timeframe: Optional[Timeframe] = None
    overall_metrics: Dict[str, float] = None


class MultiTimeframeTester:
    """
    Multi-Timeframe Strategy Tester
    
    Tests trading strategies across multiple timeframes simultaneously to:
    1. Evaluate performance consistency across timeframes
    2. Identify optimal timeframe for specific strategies
    3. Analyze correlations between timeframe performances
    4. Optimize strategy parameters for different timeframes
    """
    
    def __init__(self, config: TimeframeTestConfig):
        """Initialize the multi-timeframe tester"""
        self.config = config
        self.data_cache: Dict[str, Dict[Timeframe, pd.DataFrame]] = {}
        
        logger.info(f"MultiTimeframeTester initialized with timeframes: {[tf.value for tf in config.timeframes]}")
    
    def load_data_for_timeframes(
        self, 
        symbol: str, 
        start_date: datetime, 
        end_date: datetime
    ) -> Dict[Timeframe, pd.DataFrame]:
        """
        Load data for all required timeframes
        
        Args:
            symbol: Trading symbol
            start_date: Start date for data
            end_date: End date for data
            
        Returns:
            Dictionary mapping timeframes to their respective data
        """
        data_by_timeframe = {}
        
        # Calculate extended date range to account for warmup period
        extended_start = start_date - timedelta(days=self.config.warmup_period_days)
        
        for timeframe in self.config.timeframes:
            try:
                # In a real implementation, this would fetch data from a database or API
                # For now, we'll simulate data loading
                data = self._simulate_data_for_timeframe(
                    symbol, extended_start, end_date, timeframe
                )
                
                if data is not None and len(data) > 0:
                    data_by_timeframe[timeframe] = data
                    logger.debug(f"Loaded {len(data)} candles for {symbol} on {timeframe.value}")
                else:
                    logger.warning(f"No data available for {symbol} on {timeframe.value}")
                    
            except Exception as e:
                logger.error(f"Error loading data for {symbol} on {timeframe.value}: {e}")
        
        return data_by_timeframe
    
    def _simulate_data_for_timeframe(
        self, 
        symbol: str, 
        start_date: datetime, 
        end_date: datetime, 
        timeframe: Timeframe
    ) -> Optional[pd.DataFrame]:
        """
        Simulate data for a specific timeframe (in production, this would fetch real data)
        
        Args:
            symbol: Trading symbol
            start_date: Start date
            end_date: End date
            timeframe: Target timeframe
            
        Returns:
            DataFrame with OHLCV data
        """
        # Calculate approximate number of candles based on timeframe
        if timeframe == Timeframe.MINUTE_15:
            candle_count = int((end_date - start_date).total_seconds() / (15 * 60))
        elif timeframe == Timeframe.HOUR_4:
            candle_count = int((end_date - start_date).total_seconds() / (4 * 3600))
        elif timeframe == Timeframe.DAY_1:
            candle_count = (end_date - start_date).days
        else:
            # For other timeframes, estimate based on 1-hour equivalent
            hour_equivalent = int(timeframe.value.replace('m', '').replace('h', '').replace('d', '')) * (
                1 if 'd' not in timeframe.value else 24
            )
            candle_count = int((end_date - start_date).total_seconds() / (hour_equivalent * 3600))
        
        # Limit to reasonable number for simulation
        candle_count = min(candle_count, 10000)
        
        if candle_count <= 0:
            return None
        
        # Generate simulated price data
        timestamps = pd.date_range(start=start_date, end=end_date, periods=candle_count)
        
        # Start with a base price
        base_price = 50000.0  # Starting price
        prices = [base_price]
        
        # Generate random price movements
        for i in range(1, len(timestamps)):
            # Random walk with slight drift
            change_percent = np.random.normal(0.0001, 0.02)  # 0.01% drift, 2% daily volatility
            new_price = prices[-1] * (1 + change_percent)
            prices.append(new_price)
        
        # Create OHLCV data
        opens = prices[:-1]  # Exclude last price since we need high/low/vol for each candle
        closes = prices[1:]   # Shift by one to align with opens
        
        # Generate high, low, volume based on opens/closes
        high = []
        low = []
        volume = []
        
        for i in range(len(opens)):
            o, c = opens[i], closes[i]
            # Random high and low around open/close
            daily_range = abs(c - o) * 2  # Make range slightly larger than just O-C
            h = max(o, c) + np.random.uniform(0, daily_range * 0.3)
            l = min(o, c) - np.random.uniform(0, daily_range * 0.3)
            
            high.append(h)
            low.append(l)
            
            # Random volume
            vol = np.random.uniform(100, 10000)
            volume.append(vol)
        
        # Create DataFrame
        df = pd.DataFrame({
            'timestamp': timestamps[1:],  # Align with opens/closes
            'open': opens,
            'high': high,
            'low': low,
            'close': closes,
            'volume': volume
        })
        
        # Set timestamp as index
        df.set_index('timestamp', inplace=True)
        
        return df
    
    def test_strategy_on_timeframe(
        self,
        strategy_func: Callable,
        data: pd.DataFrame,
        timeframe: Timeframe,
        symbol: str
    ) -> TimeframePerformance:
        """
        Test a strategy on a specific timeframe
        
        Args:
            strategy_func: Strategy function to test
            data: OHLCV data for the timeframe
            timeframe: The timeframe being tested
            symbol: Trading symbol
            
        Returns:
            TimeframePerformance object with results
        """
        # Initialize performance tracking
        returns = []
        trades = []
        positions = []
        
        # Run backtest
        for i in range(len(data)):
            row = data.iloc[i]
            
            # For simplicity, we'll simulate a basic backtest
            # In a real implementation, this would use the actual strategy logic
            if i > 20:  # Skip initial period for indicators
                # Simulate some basic trading logic
                current_price = row['close']
                
                # Simple example: buy when price is below 20-period MA, sell when above
                ma_20 = data['close'].iloc[max(0, i-20):i].mean()
                
                if current_price < ma_20 * 0.98 and len(positions) == 0:  # Buy signal
                    positions.append({
                        'entry_price': current_price,
                        'entry_time': data.index[i],
                        'size': 1.0  # Fixed position size for simulation
                    })
                elif current_price > ma_20 * 1.02 and len(positions) > 0:  # Sell signal
                    position = positions.pop()
                    pnl = (current_price - position['entry_price']) / position['entry_price']
                    trade_duration = (data.index[i] - position['entry_time']).total_seconds() / 3600  # Hours
                    
                    trades.append({
                        'return': pnl,
                        'duration': trade_duration,
                        'entry_price': position['entry_price'],
                        'exit_price': current_price
                    })
                    returns.append(pnl)
        
        # Calculate performance metrics
        if returns:
            returns_array = np.array(returns)
            total_return = np.sum(returns_array)
            win_trades = [t for t in returns if t > 0]
            lose_trades = [t for t in returns if t <= 0]
            
            win_rate = len(win_trades) / len(returns) if returns else 0
            avg_win = np.mean(win_trades) if win_trades else 0
            avg_loss = np.abs(np.mean(lose_trades)) if lose_trades else 0
            profit_factor = (avg_win * len(win_trades)) / (avg_loss * len(lose_trades)) if avg_loss > 0 else float('inf')
            
            # Calculate Sharpe ratio (assuming risk-free rate of 0)
            excess_returns = returns_array - 0  # Risk-free rate = 0
            if np.std(excess_returns) != 0:
                sharpe_ratio = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252 * 24)  # Annualized
            else:
                sharpe_ratio = 0
                
            # Calculate max drawdown
            cumulative = np.cumprod(1 + returns_array)
            running_max = np.maximum.accumulate(cumulative)
            drawdowns = (cumulative - running_max) / running_max
            max_drawdown = np.min(drawdowns) if len(drawdowns) > 0 else 0
            
            # Calculate volatility (annualized)
            volatility = np.std(returns_array) * np.sqrt(252 * 24)  # Annualized based on hourly returns
            
            # Calculate Sortino ratio (using only downside deviation)
            negative_returns = returns_array[returns_array < 0]
            if len(negative_returns) > 0:
                downside_deviation = np.std(negative_returns) * np.sqrt(252 * 24)
                sortino_ratio = (np.mean(returns_array) * 252 * 24) / downside_deviation if downside_deviation != 0 else 0
            else:
                sortino_ratio = sharpe_ratio  # If no negative returns, use sharpe ratio
                
            # Calculate trade duration average
            avg_duration = np.mean([t['duration'] for t in trades]) if trades else 0
            
            # Best and worst trades
            best_trade = max(returns) if returns else 0
            worst_trade = min(returns) if returns else 0
            
        else:
            # Default values when no trades occurred
            total_return = 0
            win_rate = 0
            profit_factor = 0
            sharpe_ratio = 0
            max_drawdown = 0
            avg_win = 0
            avg_loss = 0
            volatility = 0
            sortino_ratio = 0
            avg_duration = 0
            best_trade = 0
            worst_trade = 0
        
        performance = TimeframePerformance(
            timeframe=timeframe,
            total_return=total_return,
            sharpe_ratio=sharpe_ratio,
            win_rate=win_rate,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            total_trades=len(returns),
            winning_trades=len([r for r in returns if r > 0]),
            losing_trades=len([r for r in returns if r <= 0]),
            avg_win=avg_win,
            avg_loss=avg_loss,
            best_trade=best_trade,
            worst_trade=worst_trade,
            trade_duration_avg=avg_duration,
            volatility=volatility,
            sortino_ratio=sortino_ratio
        )
        
        logger.info(f"Performance on {timeframe.value}: Return={total_return:.2%}, Sharpe={sharpe_ratio:.2f}, WinRate={win_rate:.2%}")
        
        return performance
    
    def run_multi_timeframe_test(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        strategy_func: Optional[Callable] = None
    ) -> MultiTimeframeResults:
        """
        Run comprehensive multi-timeframe test
        
        Args:
            symbol: Trading symbol to test
            start_date: Start date for testing
            end_date: End date for testing
            strategy_func: Strategy function to test (if None, uses adaptive approach)
            
        Returns:
            MultiTimeframeResults object with complete test results
        """
        logger.info(f"Starting multi-timeframe test for {symbol} from {start_date} to {end_date}")
        
        # Load data for all timeframes
        data_by_timeframe = self.load_data_for_timeframes(symbol, start_date, end_date)
        
        if not data_by_timeframe:
            logger.error(f"No data available for {symbol} on any timeframe")
            return MultiTimeframeResults(
                strategy_name="None",
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                timeframe_results={},
                overall_metrics={}
            )
        
        # Test strategy on each timeframe
        timeframe_results = {}
        
        for timeframe, data in data_by_timeframe.items():
            logger.info(f"Testing strategy on {timeframe.value} timeframe...")
            
            # Use provided strategy or create based on configuration
            if strategy_func is None:
                # Create strategy based on configuration
                if self.config.strategy_type == "mean_reversion":
                    strategy = EnhancedMeanReversionStrategy()
                    strategy_func = strategy.generate_signal
                elif self.config.strategy_type == "breakout":
                    strategy = EnhancedBreakoutStrategy()
                    # For breakout strategy, we'd need to implement a compatible interface
                    # For now, we'll use a placeholder
                    def placeholder_strategy(row, position, idx, data):
                        return None
                    strategy_func = placeholder_strategy
                else:  # adaptive
                    # For adaptive strategy, we'll use a placeholder that selects based on regime
                    def adaptive_strategy(row, position, idx, data):
                        # Placeholder for adaptive strategy logic
                        return None
                    strategy_func = adaptive_strategy
            
            # Test the strategy on this timeframe
            performance = self.test_strategy_on_timeframe(
                strategy_func, data, timeframe, symbol
            )
            
            timeframe_results[timeframe] = performance
        
        # Find best performing timeframe
        best_timeframe = None
        best_performance = float('-inf')
        
        for timeframe, perf in timeframe_results.items():
            # Use Sharpe ratio as primary metric for best timeframe
            if perf.sharpe_ratio > best_performance:
                best_performance = perf.sharpe_ratio
                best_timeframe = timeframe
        
        # Calculate correlation matrix if enabled
        correlation_matrix = None
        if self.config.enable_correlation_analysis and len(timeframe_results) > 1:
            correlation_matrix = self._calculate_correlation_matrix(timeframe_results, data_by_timeframe)
        
        # Calculate overall metrics
        overall_metrics = self._calculate_overall_metrics(timeframe_results)
        
        results = MultiTimeframeResults(
            strategy_name=self.config.strategy_type,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timeframe_results=timeframe_results,
            correlation_matrix=correlation_matrix,
            best_timeframe=best_timeframe,
            overall_metrics=overall_metrics
        )
        
        logger.info(f"Multi-timeframe test completed for {symbol}. Best timeframe: {best_timeframe.value if best_timeframe else 'None'}")
        
        return results
    
    def _calculate_correlation_matrix(
        self,
        timeframe_results: Dict[Timeframe, TimeframePerformance],
        data_by_timeframe: Dict[Timeframe, pd.DataFrame]
    ) -> np.ndarray:
        """
        Calculate correlation matrix between timeframe performances
        
        Args:
            timeframe_results: Performance results by timeframe
            data_by_timeframe: Price data by timeframe
            
        Returns:
            Correlation matrix as numpy array
        """
        # For this implementation, we'll calculate correlations based on returns
        # In a real implementation, we'd use actual return series
        timeframes_list = list(timeframe_results.keys())
        n_timeframes = len(timeframes_list)
        
        # Create a dummy correlation matrix for now
        # In a real implementation, this would calculate actual correlations
        correlation_matrix = np.eye(n_timeframes)  # Identity matrix as placeholder
        
        logger.debug(f"Calculated correlation matrix for {n_timeframes} timeframes")
        
        return correlation_matrix
    
    def _calculate_overall_metrics(
        self,
        timeframe_results: Dict[Timeframe, TimeframePerformance]
    ) -> Dict[str, float]:
        """
        Calculate overall metrics across all timeframes
        
        Args:
            timeframe_results: Performance results by timeframe
            
        Returns:
            Dictionary with overall metrics
        """
        if not timeframe_results:
            return {}
        
        # Calculate averages of key metrics
        total_returns = [perf.total_return for perf in timeframe_results.values()]
        sharpe_ratios = [perf.sharpe_ratio for perf in timeframe_results.values()]
        win_rates = [perf.win_rate for perf in timeframe_results.values()]
        profit_factors = [perf.profit_factor for perf in timeframe_results.values()]
        max_drawdowns = [perf.max_drawdown for perf in timeframe_results.values()]
        
        overall_metrics = {
            'avg_total_return': np.mean(total_returns) if total_returns else 0,
            'avg_sharpe_ratio': np.mean(sharpe_ratios) if sharpe_ratios else 0,
            'avg_win_rate': np.mean(win_rates) if win_rates else 0,
            'avg_profit_factor': np.mean(profit_factors) if profit_factors else 0,
            'avg_max_drawdown': np.mean(max_drawdowns) if max_drawdowns else 0,
            'timeframe_consistency': self._calculate_timeframe_consistency(timeframe_results),
            'best_sharpe_ratio': max(sharpe_ratios) if sharpe_ratios else 0,
            'worst_sharpe_ratio': min(sharpe_ratios) if sharpe_ratios else 0
        }
        
        return overall_metrics
    
    def _calculate_timeframe_consistency(
        self,
        timeframe_results: Dict[Timeframe, TimeframePerformance]
    ) -> float:
        """
        Calculate consistency of performance across timeframes
        
        Args:
            timeframe_results: Performance results by timeframe
            
        Returns:
            Consistency score (0-1, where 1 is perfectly consistent)
        """
        if len(timeframe_results) <= 1:
            return 1.0
        
        # Calculate coefficient of variation for key metrics
        sharpe_ratios = [abs(perf.sharpe_ratio) for perf in timeframe_results.values()]
        win_rates = [perf.win_rate for perf in timeframe_results.values()]
        
        # Calculate CV (lower is more consistent)
        sharpe_cv = np.std(sharpe_ratios) / np.mean(sharpe_ratios) if np.mean(sharpe_ratios) != 0 else 0
        win_rate_cv = np.std(win_rates) / np.mean(win_rates) if np.mean(win_rates) != 0 else 0
        
        # Convert to consistency score (1 - normalized CV)
        consistency_score = 1 - min((sharpe_cv + win_rate_cv) / 2, 1)
        
        return max(0, consistency_score)
    
    def compare_strategies_across_timeframes(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        strategy_functions: Dict[str, Callable]
    ) -> Dict[str, MultiTimeframeResults]:
        """
        Compare multiple strategies across all timeframes
        
        Args:
            symbol: Trading symbol
            start_date: Start date
            end_date: End date
            strategy_functions: Dictionary mapping strategy names to strategy functions
            
        Returns:
            Dictionary mapping strategy names to their multi-timeframe results
        """
        comparison_results = {}
        
        for strategy_name, strategy_func in strategy_functions.items():
            logger.info(f"Testing strategy: {strategy_name}")
            
            # Temporarily modify config for this strategy test
            original_strategy_type = self.config.strategy_type
            self.config.strategy_type = strategy_name
            
            # Run test for this strategy
            results = self.run_multi_timeframe_test(
                symbol, start_date, end_date, strategy_func
            )
            
            comparison_results[strategy_name] = results
            
            # Restore original config
            self.config.strategy_type = original_strategy_type
        
        return comparison_results


def create_multi_timeframe_tester(
    timeframes: List[Timeframe] = None,
    test_duration_days: int = 30,
    strategy_type: str = "mean_reversion"
) -> MultiTimeframeTester:
    """
    Factory function to create a multi-timeframe tester
    
    Args:
        timeframes: List of timeframes to test (defaults to 15m, 4H, 1D)
        test_duration_days: Number of days to test
        strategy_type: Type of strategy to test
        
    Returns:
        MultiTimeframeTester instance
    """
    if timeframes is None:
        timeframes = [Timeframe.MINUTE_15, Timeframe.HOUR_4, Timeframe.DAY_1]
    
    config = TimeframeTestConfig(
        timeframes=timeframes,
        test_duration_days=test_duration_days,
        strategy_type=strategy_type
    )
    
    return MultiTimeframeTester(config)


def run_comprehensive_multi_timeframe_analysis(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    timeframes: List[Timeframe] = None
) -> Dict[str, Any]:
    """
    Run comprehensive multi-timeframe analysis with adaptive strategy selection
    
    Args:
        symbol: Trading symbol
        start_date: Start date for analysis
        end_date: End date for analysis
        timeframes: List of timeframes to analyze (defaults to 15m, 4H, 1D)
        
    Returns:
        Dictionary with comprehensive analysis results
    """
    if timeframes is None:
        timeframes = [Timeframe.MINUTE_15, Timeframe.HOUR_4, Timeframe.DAY_1]
    
    # Create tester
    tester = create_multi_timeframe_tester(timeframes=timeframes)
    
    # Run analysis
    results = tester.run_multi_timeframe_test(symbol, start_date, end_date)
    
    # Perform additional analysis
    analysis = {
        'symbol': symbol,
        'timeframe_results': {
            tf.value: {
                'sharpe_ratio': perf.sharpe_ratio,
                'win_rate': perf.win_rate,
                'total_return': perf.total_return,
                'max_drawdown': perf.max_drawdown,
                'total_trades': perf.total_trades
            } for tf, perf in results.timeframe_results.items()
        },
        'best_timeframe': results.best_timeframe.value if results.best_timeframe else None,
        'overall_metrics': results.overall_metrics,
        'timeframe_rankings': _rank_timeframes_by_metric(results.timeframe_results, 'sharpe_ratio'),
        'recommendation': _generate_recommendation(results)
    }
    
    return analysis


def _rank_timeframes_by_metric(
    timeframe_results: Dict[Timeframe, TimeframePerformance], 
    metric: str
) -> List[tuple]:
    """
    Rank timeframes by a specific metric
    
    Args:
        timeframe_results: Results by timeframe
        metric: Metric to rank by (e.g., 'sharpe_ratio', 'win_rate')
        
    Returns:
        List of (timeframe, metric_value) tuples ranked by metric
    """
    rankings = []
    for tf, perf in timeframe_results.items():
        if hasattr(perf, metric):
            value = getattr(perf, metric)
            rankings.append((tf.value, value))
    
    # Sort by metric value (descending)
    rankings.sort(key=lambda x: x[1], reverse=True)
    return rankings


def _generate_recommendation(results: MultiTimeframeResults) -> str:
    """
    Generate recommendation based on multi-timeframe results
    
    Args:
        results: Multi-timeframe results
        
    Returns:
        Recommendation string
    """
    if not results.timeframe_results:
        return "No data available for analysis"
    
    # Find the best performing timeframe
    best_tf = results.best_timeframe
    if best_tf is None:
        return "No timeframe showed positive performance"
    
    best_perf = results.timeframe_results[best_tf]
    
    if best_perf.sharpe_ratio > 1.0:
        recommendation = f"Strong recommendation for {best_tf.value} timeframe: "
    elif best_perf.sharpe_ratio > 0.5:
        recommendation = f"Moderate recommendation for {best_tf.value} timeframe: "
    else:
        recommendation = f"Cautious approach for {best_tf.value} timeframe: "
    
    recommendation += f"Sharpe ratio {best_perf.sharpe_ratio:.2f}, "
    recommendation += f"Win rate {best_perf.win_rate:.1%}, "
    recommendation += f"Return {best_perf.total_return:.1%}"
    
    return recommendation