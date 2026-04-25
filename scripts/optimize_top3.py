#!/usr/bin/env python3
"""
Walk-Forward Optimization for Top 3 Performers
Created: 2025-12-06
Purpose: Optimize BNB, SOL, and ADA using walk-forward analysis

Runs comprehensive walk-forward optimization on the top 3 performing symbols
to find robust parameters that work across different market conditions.
"""

import sys
import os
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from datetime import datetime
import logging
import json

from backtesting.optimizers.walk_forward_optimizer import WalkForwardOptimizer, WalkForwardConfig
from backtesting.backtest_engine import BacktestEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def calculate_rsi(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate RSI indicator"""
    close = data['close']
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def create_rsi_strategy(rsi_period: int, oversold: int, overbought: int):
    """Create RSI-based strategy function"""
    def strategy_func(row, position, idx, data):
        if idx < rsi_period:
            return None
        if isinstance(data.index, pd.DatetimeIndex):
            data_for_calc = data.reset_index(drop=True).iloc[:idx+1]
        else:
            data_for_calc = data.iloc[:idx+1]
        rsi_values = calculate_rsi(data_for_calc, period=rsi_period)
        current_rsi = rsi_values.iloc[-1]
        if pd.isna(current_rsi):
            return None
        if position is None:
            if current_rsi < oversold:
                return {'action': 'BUY', 'stop_loss_pct': 2.0, 'take_profit_pct': 4.0}
            elif current_rsi > overbought:
                return {'action': 'SELL', 'stop_loss_pct': 2.0, 'take_profit_pct': 4.0}
        else:
            if position.order_type.value == 'BUY' and current_rsi > overbought:
                return {'action': 'HOLD'}
            elif position.order_type.value == 'SELL' and current_rsi < oversold:
                return {'action': 'HOLD'}
        return None
    return strategy_func


class BacktestEngineAdapter:
    """Adapter to bridge API mismatch"""
    def __init__(self, backtest_engine, strategy_func_generator):
        self.engine = backtest_engine
        self.strategy_func_generator = strategy_func_generator
    
    def run(self, data: pd.DataFrame, strategy_params: dict) -> dict:
        strategy_func = self.strategy_func_generator(data, strategy_params)
        result = self.engine.run_backtest(data=data, strategy_func=strategy_func, strategy_name=f"RSI_{strategy_params}")
        return {
            'total_trades': result.total_trades,
            'sharpe_ratio': result.sharpe_ratio,
            'total_return': result.total_profit_loss_pct,
            'max_drawdown': result.max_drawdown_pct,
            'win_rate': result.win_rate,
            'profit_factor': result.profit_factor,
        }


def optimize_symbol(symbol: str, data: pd.DataFrame):
    """Run walk-forward optimization on a symbol"""
    logger.info(f"\n{'='*80}")
    logger.info(f"OPTIMIZING {symbol}")
    logger.info(f"{'='*80}")
    logger.info(f"Data: {len(data)} candles from {data.index[0]} to {data.index[-1]}")
    
    # Configuration
    config = WalkForwardConfig(
        total_periods=5,
        in_sample_ratio=0.70,
        out_sample_ratio=0.30,
        metric_to_optimize='sharpe_ratio',
        min_wfe=0.50,
        min_oos_sharpe=0.50,
        max_oos_drawdown=0.25,
        max_workers=4
    )
    
    # Parameter space
    parameter_space = {
        'rsi_period': [10, 14, 20],
        'oversold': [25, 30, 35],
        'overbought': [65, 70, 75]
    }
    
    # Create backtest engine and adapter
    backtest_engine = BacktestEngine(initial_capital=10000.0, commission=0.001, slippage=0.0005)
    
    def strategy_func_with_params(data_subset, params):
        return create_rsi_strategy(params.get('rsi_period', 14), params.get('oversold', 30), params.get('overbought', 70))
    
    adapter = BacktestEngineAdapter(backtest_engine, strategy_func_with_params)
    
    # Run optimization
    optimizer = WalkForwardOptimizer(config)
    results = optimizer.optimize(data=data, strategy_func=strategy_func_with_params, parameter_space=parameter_space, backtest_engine=adapter)
    
    # Display results
    logger.info(f"\n{symbol} RESULTS:")
    logger.info(f"  Average WFE: {results.average_wfe:.2%}")
    logger.info(f"  OOS Sharpe:  {results.total_oos_sharpe:.3f}")
    logger.info(f"  OOS Profit:  {results.total_oos_profit:.2%}")
    logger.info(f"  Robust:      {'YES ✅' if results.is_strategy_robust() else 'NO ❌'}")
    
    # Save results
    results_path = project_root / 'backtesting' / 'results' / f'{symbol}_walkforward_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, 'w') as f:
        json.dump(results.to_dict(), f, indent=2, default=str)
    logger.info(f"  Saved to: {results_path}")
    
    return results


def main():
    print("\n" + "="*80)
    print("WALK-FORWARD OPTIMIZATION - TOP 3 PERFORMERS")
    print("="*80 + "\n")
    
    symbols = ['BNBUSDT', 'SOLUSDT', 'ADAUSDT']
    all_results = {}
    
    for symbol in symbols:
        try:
            # Load data
            data_path = project_root / 'backtesting' / 'data' / f'{symbol}_60m_90d_bybit.csv'
            data = pd.read_csv(data_path)
            data['timestamp'] = pd.to_datetime(data['timestamp'])
            data = data.set_index('timestamp').sort_index()
            
            # Optimize
            results = optimize_symbol(symbol, data)
            all_results[symbol] = results
            
        except Exception as e:
            logger.error(f"❌ {symbol} optimization failed: {e}")
            all_results[symbol] = None
    
    # Summary
    print("\n" + "="*80)
    print("OPTIMIZATION SUMMARY")
    print("="*80)
    for symbol, results in all_results.items():
        if results:
            print(f"\n{symbol}:")
            print(f"  WFE: {results.average_wfe:.2%}")
            print(f"  OOS Sharpe: {results.total_oos_sharpe:.3f}")
            print(f"  Robust: {'✅' if results.is_strategy_robust() else '❌'}")
        else:
            print(f"\n{symbol}: ❌ FAILED")
    
    print("\n" + "="*80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
