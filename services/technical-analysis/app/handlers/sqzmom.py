"""
Squeeze Momentum (SQZMOM) Indicator Handlers
Purpose: API handlers for SQZMOM indicator and strategy endpoints
"""

import logging
from typing import Dict, Any
import pandas as pd
import numpy as np

from app.fetcher import get_fetcher
from app.indicators.squeeze_momentum import SqueezeMomentumIndicator
from app.strategies.squeeze_momentum_strategy import SqueezeMomentumStrategy

logger = logging.getLogger(__name__)


async def get_sqzmom(
    symbol: str,
    interval: str = "60",
    bb_length: int = 20,
    bb_mult: float = 2.0,
    kc_length: int = 20,
    kc_mult: float = 1.5,
    use_true_range: bool = True,
    limit: int = 200
) -> Dict[str, Any]:
    """
    Calculate Squeeze Momentum Indicator

    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        interval: Timeframe in minutes (default: 60)
        bb_length: Bollinger Bands period (default: 20)
        bb_mult: Bollinger Bands std dev multiplier (default: 2.0)
        kc_length: Keltner Channel period (default: 20)
        kc_mult: Keltner Channel ATR multiplier (default: 1.5)
        use_true_range: Use True Range for KC (default: True)
        limit: Number of candles to fetch (default: 200)

    Returns:
        Dictionary with SQZMOM indicator values and signal

    Raises:
        Exception if data fetch or calculation fails
    """
    try:
        logger.info(
            f"Calculating SQZMOM for {symbol} {interval}m: "
            f"BB({bb_length},{bb_mult}), KC({kc_length},{kc_mult})"
        )

        # Fetch market data
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df is None or len(df) == 0:
            logger.error(f"No candle data returned for {symbol}")
            raise Exception(f"Failed to fetch candles for {symbol}")

        # Validate required columns
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required_cols):
            logger.error(f"Missing required columns in candle data. Got: {df.columns.tolist()}")
            raise Exception("Invalid candle data structure")

        # Initialize indicator
        indicator = SqueezeMomentumIndicator(
            bb_length=bb_length,
            bb_mult=bb_mult,
            kc_length=kc_length,
            kc_mult=kc_mult,
            use_true_range=use_true_range
        )

        # Calculate indicator
        result_df = indicator.calculate(df)

        if result_df is None:
            logger.error("SQZMOM calculation returned None")
            raise Exception("Failed to calculate SQZMOM indicator")

        # Get signal
        signal_data = indicator.get_signal(df)

        # Get latest values for detailed response
        latest = result_df.iloc[-1]

        # Build response
        response = {
            'symbol': symbol.upper(),
            'interval': interval,
            'timestamp': int(latest.get('timestamp', df['timestamp'].iloc[-1] if 'timestamp' in df.columns else 0)),

            # Current state
            'squeeze_state': {
                'squeeze_on': bool(latest['squeeze_on']),
                'squeeze_off': bool(latest['squeeze_off']),
                'no_squeeze': bool(latest['no_squeeze'])
            },

            # Momentum
            'momentum': {
                'value': round(float(latest['sqz_momentum']), 4),
                'color': latest['sqz_color'],
                'direction': 'bullish' if latest['sqz_momentum'] > 0 else 'bearish'
            },

            # Bollinger Bands
            'bollinger_bands': {
                'upper': round(float(latest['bb_upper']), 2),
                'basis': round(float(latest['bb_basis']), 2),
                'lower': round(float(latest['bb_lower']), 2)
            },

            # Keltner Channels
            'keltner_channels': {
                'upper': round(float(latest['kc_upper']), 2),
                'basis': round(float(latest['kc_basis']), 2),
                'lower': round(float(latest['kc_lower']), 2)
            },

            # Signal
            'signal': {
                'action': latest['sqz_signal'],
                'confidence': round(float(latest['sqz_confidence']), 2),
                'strength': signal_data.get('strength', 0.0)
            },

            # Current price
            'current_price': round(float(latest['close']), 2),

            # Parameters used
            'parameters': {
                'bb_length': bb_length,
                'bb_mult': bb_mult,
                'kc_length': kc_length,
                'kc_mult': kc_mult,
                'use_true_range': use_true_range
            }
        }

        logger.info(
            f"SQZMOM calculated: {symbol} - "
            f"squeeze={response['squeeze_state']}, "
            f"signal={response['signal']['action']}, "
            f"confidence={response['signal']['confidence']}"
        )

        return response

    except Exception as e:
        logger.error(f"Error calculating SQZMOM for {symbol}: {e}", exc_info=True)
        raise


async def get_sqzmom_strategy_signal(
    symbol: str,
    interval: str = "60",
    min_momentum: float = 0.5,
    stop_loss_pct: float = 2.0,
    take_profit_pct: float = 4.0,
    require_squeeze_release: bool = True,
    require_volume: bool = False
) -> Dict[str, Any]:
    """
    Get trading signal from Squeeze Momentum Strategy

    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        interval: Timeframe in minutes (default: 60)
        min_momentum: Minimum momentum threshold for entry (default: 0.5)
        stop_loss_pct: Stop loss percentage (default: 2.0%)
        take_profit_pct: Take profit percentage (default: 4.0%)
        require_squeeze_release: Only trade on squeeze release (default: True)
        require_volume: Require volume confirmation (default: False)

    Returns:
        Dictionary with strategy signal and position details

    Raises:
        Exception if data fetch or analysis fails
    """
    try:
        logger.info(
            f"Getting SQZMOM strategy signal for {symbol} {interval}m: "
            f"min_momentum={min_momentum}, SL={stop_loss_pct}%, TP={take_profit_pct}%"
        )

        # Fetch market data
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, 200)

        if df is None or len(df) == 0:
            logger.error(f"No candle data returned for {symbol}")
            raise Exception(f"Failed to fetch candles for {symbol}")

        # Initialize strategy
        indicator = SqueezeMomentumIndicator()
        strategy = SqueezeMomentumStrategy(
            sqzmom_indicator=indicator,
            min_momentum_threshold=min_momentum,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            require_squeeze_release=require_squeeze_release,
            require_volume_confirmation=require_volume
        )

        # Analyze
        analysis = strategy.analyze(df)

        # Build response - Convert all numpy types to Python native types
        response = {
            'symbol': symbol.upper(),
            'interval': interval,
            'timestamp': int(df['timestamp'].iloc[-1]) if 'timestamp' in df.columns else 0,

            # Strategy signal
            'action': str(analysis['action']),
            'confidence': float(analysis['confidence']),
            'reason': str(analysis['reason']),

            # Position details
            'entry_price': float(analysis.get('entry_price', 0.0)),
            'stop_loss': float(analysis.get('stop_loss', 0.0)),
            'take_profit': float(analysis.get('take_profit', 0.0)),

            # Risk/Reward
            'risk_reward_ratio': 2.0,  # Fixed 1:2 ratio
            'risk_pct': float(stop_loss_pct),
            'reward_pct': float(take_profit_pct),

            # Market context
            'momentum': float(analysis.get('momentum', 0.0)),
            'squeeze_state': str(analysis.get('squeeze_state', 'UNKNOWN')),
            'momentum_color': str(analysis.get('color', 'gray')),

            # Strategy parameters
            'strategy_config': {
                'min_momentum_threshold': min_momentum,
                'stop_loss_pct': stop_loss_pct,
                'take_profit_pct': take_profit_pct,
                'require_squeeze_release': require_squeeze_release,
                'require_volume_confirmation': require_volume
            }
        }

        logger.info(
            f"Strategy signal: {symbol} - {response['action']} "
            f"(confidence: {response['confidence']}) - {response['reason']}"
        )

        return response

    except Exception as e:
        logger.error(f"Error getting strategy signal for {symbol}: {e}", exc_info=True)
        raise


async def get_sqzmom_backtest_data(
    symbol: str,
    interval: str = "60",
    limit: int = 500
) -> Dict[str, Any]:
    """
    Get historical SQZMOM data for backtesting

    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        interval: Timeframe in minutes (default: 60)
        limit: Number of candles to fetch (default: 500)

    Returns:
        Dictionary with historical SQZMOM values for backtesting

    Raises:
        Exception if data fetch or calculation fails
    """
    try:
        logger.info(f"Fetching SQZMOM backtest data for {symbol} {interval}m, {limit} candles")

        # Fetch market data
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df is None or len(df) == 0:
            raise Exception(f"Failed to fetch candles for {symbol}")

        # Calculate indicator
        indicator = SqueezeMomentumIndicator()
        result_df = indicator.calculate(df)

        if result_df is None:
            raise Exception("Failed to calculate SQZMOM indicator")

        # Convert to list of records for JSON response
        # Select key columns only to reduce response size
        backtest_columns = [
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'bb_upper', 'bb_basis', 'bb_lower',
            'kc_upper', 'kc_basis', 'kc_lower',
            'squeeze_on', 'squeeze_off', 'no_squeeze',
            'sqz_momentum', 'sqz_color', 'sqz_signal', 'sqz_confidence'
        ]

        # Ensure timestamp is included
        if 'timestamp' not in result_df.columns:
            result_df['timestamp'] = pd.to_datetime(result_df.index)

        # Filter to available columns
        available_cols = [col for col in backtest_columns if col in result_df.columns]
        backtest_df = result_df[available_cols].copy()

        # Convert to records - Convert numpy types to Python native types
        records = []
        for _, row in backtest_df.iterrows():
            record = {}
            for col in available_cols:
                value = row[col]
                # Convert numpy types to Python native types
                if pd.isna(value):
                    record[col] = None
                elif isinstance(value, (bool, np.bool_)):
                    record[col] = bool(value)
                elif isinstance(value, (int, np.integer)):
                    record[col] = int(value)
                elif isinstance(value, (float, np.floating)):
                    record[col] = float(value)
                else:
                    record[col] = str(value)
            records.append(record)

        # Calculate summary statistics
        total_bars = len(records)
        squeeze_on_count = sum(1 for r in records if r.get('squeeze_on', False))
        buy_signals = sum(1 for r in records if r.get('sqz_signal') == 'BUY')
        sell_signals = sum(1 for r in records if r.get('sqz_signal') == 'SELL')

        response = {
            'symbol': symbol.upper(),
            'interval': interval,
            'data_points': total_bars,

            # Summary statistics
            'statistics': {
                'total_bars': total_bars,
                'squeeze_on_count': squeeze_on_count,
                'squeeze_on_pct': round(squeeze_on_count / total_bars * 100, 2) if total_bars > 0 else 0,
                'buy_signals': buy_signals,
                'sell_signals': sell_signals,
                'hold_signals': total_bars - buy_signals - sell_signals,
                'avg_momentum': round(float(backtest_df['sqz_momentum'].mean()), 4) if 'sqz_momentum' in backtest_df else 0,
                'max_momentum': round(float(backtest_df['sqz_momentum'].max()), 4) if 'sqz_momentum' in backtest_df else 0,
                'min_momentum': round(float(backtest_df['sqz_momentum'].min()), 4) if 'sqz_momentum' in backtest_df else 0
            },

            # Historical data
            'data': records
        }

        logger.info(
            f"Backtest data ready: {total_bars} bars, "
            f"{squeeze_on_count} squeeze bars ({response['statistics']['squeeze_on_pct']}%)"
        )

        return response

    except Exception as e:
        logger.error(f"Error fetching backtest data for {symbol}: {e}", exc_info=True)
        raise
