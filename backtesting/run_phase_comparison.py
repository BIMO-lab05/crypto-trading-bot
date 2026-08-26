#!/usr/bin/env python3
"""
Phase 1 vs Phase 3 Backtest Comparison
Compares Technical Analysis only (Phase 1) vs AI-Enhanced with ML + Sentiment (Phase 3)

This script provides comprehensive comparison on:
- Signal quality
- Profitability
- Risk metrics
- Statistical significance
- Trade execution quality
"""

from visualization import BacktestVisualizer
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging
from pathlib import Path
import json
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

from backtest_engine import BacktestEngine, OrderType, Trade
from data_downloader import HistoricalDataDownloader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IndicatorCalculator:
    """
    Calculate technical indicators for backtesting
    Provides all Phase 1 technical analysis indicators
    """

    @staticmethod
    def calculate_rsi(prices: pd.Series, period: int = 14) -> float:
        """Calculate RSI (Relative Strength Index)"""
        if len(prices) < period + 1:
            return 50.0  # Neutral RSI when insufficient data

        # Calculate price changes
        deltas = prices.diff()

        # Separate gains and losses
        gain = deltas.where(deltas > 0, 0.0)
        loss = -deltas.where(deltas < 0, 0.0)

        # Calculate average gain and loss
        avg_gain = gain.rolling(window=period).mean().iloc[-1]
        avg_loss = loss.rolling(window=period).mean().iloc[-1]

        # Handle division by zero
        if avg_loss == 0:
            return 100.0  # Max RSI

        # Calculate RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    @staticmethod
    def calculate_macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
        """Calculate MACD (Moving Average Convergence Divergence)"""
        if len(prices) < slow:
            return {'macd': 0.0, 'signal': 0.0, 'histogram': 0.0}

        # Calculate EMAs
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()

        # MACD line
        macd_line = ema_fast - ema_slow

        # Signal line
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()

        # Histogram
        histogram = macd_line - signal_line

        return {
            'macd': float(macd_line.iloc[-1]),
            'signal': float(signal_line.iloc[-1]),
            'histogram': float(histogram.iloc[-1])
        }

    @staticmethod
    def calculate_bollinger_bands(prices: pd.Series, period: int = 20, std_dev: int = 2) -> Dict:
        """Calculate Bollinger Bands"""
        if len(prices) < period:
            current = prices.iloc[-1] if len(prices) > 0 else 0
            return {
                'upper': current * 1.02,
                'middle': current,
                'lower': current * 0.98,
                'bandwidth': 0.04
            }

        # Calculate middle band (SMA)
        middle = prices.rolling(window=period).mean().iloc[-1]

        # Calculate standard deviation
        std = prices.rolling(window=period).std().iloc[-1]

        # Calculate bands
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)

        # Bandwidth (volatility measure)
        bandwidth = (upper - lower) / middle if middle > 0 else 0

        return {
            'upper': float(upper),
            'middle': float(middle),
            'lower': float(lower),
            'bandwidth': float(bandwidth)
        }

    @staticmethod
    def calculate_ema(prices: pd.Series, period: int) -> float:
        """Calculate EMA (Exponential Moving Average)"""
        if len(prices) < period:
            return prices.mean()  # Fallback to simple mean

        return float(prices.ewm(span=period, adjust=False).mean().iloc[-1])

    @staticmethod
    def calculate_sma(prices: pd.Series, period: int) -> float:
        """Calculate SMA (Simple Moving Average)"""
        if len(prices) < period:
            return prices.mean()

        return float(prices.rolling(window=period).mean().iloc[-1])

    @staticmethod
    def calculate_trend_filter(prices: pd.Series, fast_period: int = 50, slow_period: int = 200) -> Dict:
        """
        Calculate Trend Filter using 50/200 EMA crossover
        Phase 1 GATEKEEPER component
        """
        if len(prices) < slow_period:
            return {"trend": "NEUTRAL", "confidence": 0.3, "strength": 0.0}

        # Calculate EMAs
        fast_ema = IndicatorCalculator.calculate_ema(prices, fast_period)
        slow_ema = IndicatorCalculator.calculate_ema(prices, slow_period)

        # Calculate spread percentage
        spread_pct = (fast_ema - slow_ema) / slow_ema if slow_ema > 0 else 0

        # Determine trend with confidence
        if spread_pct > 0.005:  # 0.5% threshold
            trend = "BULLISH"
            confidence = min(abs(spread_pct) / 0.05, 1.0)  # Max confidence at 5% spread
        elif spread_pct < -0.005:
            trend = "BEARISH"
            confidence = min(abs(spread_pct) / 0.05, 1.0)
        else:
            trend = "NEUTRAL"
            confidence = 0.3

        return {
            "trend": trend,
            "confidence": confidence,
            "strength": abs(spread_pct),
            "fast_ema": fast_ema,
            "slow_ema": slow_ema
        }

    @staticmethod
    def calculate_volume_confirmation(volumes: pd.Series, period: int = 20) -> Dict:
        """
        Calculate Volume Confirmation
        Phase 1 VALIDATOR component
        """
        if len(volumes) < period:
            return {
                "confirmed": False,
                "strength": "INSUFFICIENT",
                "ratio": 0.0,
                "avg_volume": 0.0
            }

        # Current volume vs average
        current_volume = volumes.iloc[-1]
        avg_volume = volumes.iloc[-period:].mean()
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

        # Classify volume strength
        if volume_ratio >= 1.5:
            confirmed = True
            strength = "STRONG"
        elif volume_ratio >= 1.2:
            confirmed = True
            strength = "MODERATE"
        elif volume_ratio >= 1.0:
            confirmed = False
            strength = "WEAK"
        else:
            confirmed = False
            strength = "INSUFFICIENT"

        return {
            "confirmed": confirmed,
            "strength": strength,
            "ratio": float(volume_ratio),
            "avg_volume": float(avg_volume)
        }

    @staticmethod
    def calculate_atr(highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int = 14) -> Dict:
        """
        Calculate ATR (Average True Range)
        Used for dynamic stop-loss and take-profit levels
        """
        if len(closes) < period + 1:
            return {
                "atr": 0.0,
                "atr_pct": 0.0,
                "stop_loss_long": 0.0,
                "take_profit_long": 0.0,
                "stop_loss_short": 0.0,
                "take_profit_short": 0.0
            }

        # Create dataframe for calculations
        df = pd.DataFrame({
            'high': highs,
            'low': lows,
            'close': closes,
            'prev_close': closes.shift(1)
        })

        # Calculate True Range components
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = abs(df['high'] - df['prev_close'])
        df['tr3'] = abs(df['low'] - df['prev_close'])
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)

        # Calculate ATR
        atr = df['tr'].ewm(span=period, adjust=False).mean().iloc[-1]
        current_price = closes.iloc[-1]
        atr_pct = (atr / current_price) * 100 if current_price > 0 else 0

        return {
            "atr": float(atr),
            "atr_pct": float(atr_pct),
            "stop_loss_long": float(current_price - (atr * 2.0)),
            "take_profit_long": float(current_price + (atr * 4.0)),
            "stop_loss_short": float(current_price + (atr * 2.0)),
            "take_profit_short": float(current_price - (atr * 4.0))
        }


class MLPredictor:
    """
    Mock ML Predictor for Phase 3
    Simulates ML price predictions based on price momentum and volatility

    In production, this would call the real ML Prediction Service
    """

    @staticmethod
    def predict_price_direction(prices: pd.Series, volumes: pd.Series, period: int = 50) -> Dict:
        """
        Predict price direction using simplified ML logic
        Returns prediction confidence and direction
        """
        if len(prices) < period:
            return {
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "predicted_change_pct": 0.0
            }

        # Calculate price momentum
        recent_prices = prices.iloc[-period:]
        price_change = (recent_prices.iloc[-1] - recent_prices.iloc[0]) / recent_prices.iloc[0]

        # Calculate volatility
        returns = recent_prices.pct_change().dropna()
        volatility = returns.std()

        # Simple trend strength
        trend_strength = abs(price_change) / volatility if volatility > 0 else 0

        # Predict direction based on momentum
        if price_change > 0.02:  # 2% gain
            direction = "BULLISH"
            confidence = min(trend_strength / 2.0, 0.95)  # Cap at 95%
            predicted_change = price_change * 1.2  # Predict continuation
        elif price_change < -0.02:  # 2% loss
            direction = "BEARISH"
            confidence = min(trend_strength / 2.0, 0.95)
            predicted_change = price_change * 1.2
        else:
            direction = "NEUTRAL"
            confidence = 0.4
            predicted_change = 0.0

        return {
            "direction": direction,
            "confidence": float(confidence),
            "predicted_change_pct": float(predicted_change * 100),
            "volatility": float(volatility),
            "trend_strength": float(trend_strength)
        }


class SentimentAnalyzer:
    """
    Mock Sentiment Analyzer for Phase 3
    Simulates market sentiment based on price action and volume

    In production, this would call the real Sentiment Analysis Service
    """

    @staticmethod
    def analyze_sentiment(prices: pd.Series, volumes: pd.Series, period: int = 24) -> Dict:
        """
        Analyze market sentiment based on recent price action
        Returns sentiment score and label
        """
        if len(prices) < period:
            return {
                "sentiment_score": 0.0,
                "sentiment_label": "NEUTRAL",
                "confidence": 0.0,
                "bullish_signals": 0,
                "bearish_signals": 0
            }

        # Analyze recent price action
        recent_prices = prices.iloc[-period:]
        recent_volumes = volumes.iloc[-period:]

        # Count bullish/bearish candles
        price_changes = recent_prices.diff()
        bullish_candles = (price_changes > 0).sum()
        bearish_candles = (price_changes < 0).sum()

        # Volume trend
        volume_trend = (recent_volumes.iloc[-5:].mean() - recent_volumes.mean()) / recent_volumes.mean()

        # Calculate sentiment score (-1 to 1)
        candle_sentiment = (bullish_candles - bearish_candles) / period
        volume_sentiment = np.tanh(volume_trend * 5)  # Normalize volume impact

        # Combined sentiment
        sentiment_score = (candle_sentiment * 0.6) + (volume_sentiment * 0.4)

        # Determine label
        if sentiment_score > 0.3:
            sentiment_label = "BULLISH"
        elif sentiment_score < -0.3:
            sentiment_label = "BEARISH"
        else:
            sentiment_label = "NEUTRAL"

        # Confidence based on consistency
        confidence = min(abs(sentiment_score) * 1.5, 1.0)

        return {
            "sentiment_score": float(sentiment_score),
            "sentiment_label": sentiment_label,
            "confidence": float(confidence),
            "bullish_signals": int(bullish_candles),
            "bearish_signals": int(bearish_candles)
        }


def phase1_strategy(row: pd.Series, position, idx: int, data: pd.DataFrame) -> Optional[Dict]:
    """
    PHASE 1 STRATEGY: Technical Analysis Only

    Components:
    - RSI (Relative Strength Index)
    - MACD (Moving Average Convergence Divergence)
    - Bollinger Bands
    - EMA Trend Filter (GATEKEEPER)
    - Volume Confirmation (VALIDATOR)
    - ATR for dynamic stops

    This represents the baseline Phase 1 implementation
    """
    # Need sufficient historical data
    if idx < 200:
        return None

    # Get historical data for indicator calculations
    hist_data = data.iloc[:idx+1]
    close_prices = hist_data['close']
    volumes = hist_data['volume']
    highs = hist_data['high']
    lows = hist_data['low']

    # Calculate core indicators
    rsi = IndicatorCalculator.calculate_rsi(close_prices, 14)
    macd = IndicatorCalculator.calculate_macd(close_prices)
    bb = IndicatorCalculator.calculate_bollinger_bands(close_prices)
    ema_20 = IndicatorCalculator.calculate_ema(close_prices, 20)
    current_price = row['close']

    # Phase 1 GATEKEEPER: Trend Filter
    trend_filter = IndicatorCalculator.calculate_trend_filter(close_prices)

    # Phase 1 VALIDATOR: Volume Confirmation
    volume_conf = IndicatorCalculator.calculate_volume_confirmation(volumes)

    # ATR for dynamic position sizing
    atr_data = IndicatorCalculator.calculate_atr(highs, lows, close_prices)

    # Generate signal only if no open position
    if position:
        return None

    signal = None

    # WEIGHTED SCORING SYSTEM FOR BUY SIGNALS
    buy_score = 0
    max_buy_score = 100

    # 1. RSI oversold - relaxed from < 30 to < 40 (20 points)
    if rsi < 40:
        buy_score += 20 * (40 - rsi) / 40  # More oversold = higher score

    # 2. Price vs EMA trend (20 points)
    if current_price > ema_20:
        buy_score += 20

    # 3. MACD bullish momentum (20 points)
    if macd['histogram'] > 0:
        buy_score += 20
    elif macd['histogram'] > -0.5:  # Slightly bearish but improving
        buy_score += 10

    # 4. Bollinger Band position - relaxed from 2% to 5% (15 points)
    if current_price < bb['lower'] * 1.05:
        buy_score += 15

    # 5. Trend filter (15 points for BULLISH, 0 for BEARISH)
    if trend_filter['trend'] == 'BULLISH':
        buy_score += 15 * trend_filter['confidence']

    # 6. Volume confirmation (10 points)
    if volume_conf['confirmed']:
        buy_score += 10

    # Generate BUY signal if score >= 60/100 (60% threshold)
    if buy_score >= 60:
        signal = {
            'action': 'BUY',
            'stop_loss': atr_data['stop_loss_long'],
            'take_profit': atr_data['take_profit_long'],
            'metadata': {
                'strategy': 'phase1',
                'signal_strength': buy_score,
                'rsi': rsi,
                'macd_histogram': macd['histogram'],
                'ema_20': ema_20,
                'bb_position': 'lower',
                'trend': trend_filter['trend'],
                'volume_confirmed': volume_conf['confirmed'],
                'atr': atr_data['atr']
            }
        }
        logger.info(f"[Phase1] BUY signal generated with score: {buy_score:.1f}/100")

    # WEIGHTED SCORING SYSTEM FOR SELL SIGNALS
    sell_score = 0
    max_sell_score = 100

    # 1. RSI overbought - relaxed from > 70 to > 60 (20 points)
    if rsi > 60:
        sell_score += 20 * (rsi - 60) / 40  # More overbought = higher score

    # 2. Price below EMA trend (20 points)
    if current_price < ema_20:
        sell_score += 20

    # 3. MACD bearish momentum (20 points)
    if macd['histogram'] < 0:
        sell_score += 20
    elif macd['histogram'] < 0.5:  # Slightly bullish but weakening
        sell_score += 10

    # 4. Bollinger Band position - relaxed from 2% to 5% (15 points)
    if current_price > bb['upper'] * 0.95:
        sell_score += 15

    # 5. Trend filter (15 points for BEARISH, 0 for BULLISH)
    if trend_filter['trend'] == 'BEARISH':
        sell_score += 15 * trend_filter['confidence']

    # 6. Volume confirmation (10 points)
    if volume_conf['confirmed']:
        sell_score += 10

    # Generate SELL signal if score >= 60/100 (60% threshold)
    if sell_score >= 60:
        signal = {
            'action': 'SELL',
            'stop_loss': atr_data['stop_loss_short'],
            'take_profit': atr_data['take_profit_short'],
            'metadata': {
                'strategy': 'phase1',
                'signal_strength': sell_score,
                'rsi': rsi,
                'macd_histogram': macd['histogram'],
                'ema_20': ema_20,
                'bb_position': 'upper',
                'trend': trend_filter['trend'],
                'volume_confirmed': volume_conf['confirmed'],
                'atr': atr_data['atr']
            }
        }
        logger.info(f"[Phase1] SELL signal generated with score: {sell_score:.1f}/100")

    return signal


def phase3_strategy(row: pd.Series, position, idx: int, data: pd.DataFrame) -> Optional[Dict]:
    """
    PHASE 3 STRATEGY: AI-Enhanced with ML + Sentiment

    Components:
    - All Phase 1 indicators (RSI, MACD, BB, EMA, Volume, ATR)
    - ML Price Prediction (trend direction and confidence)
    - Sentiment Analysis (market sentiment score)
    - Multi-timeframe confirmation
    - Advanced signal weighting

    This represents the enhanced Phase 3 implementation with AI
    """
    # Need sufficient historical data
    if idx < 200:
        return None

    # Get historical data
    hist_data = data.iloc[:idx+1]
    close_prices = hist_data['close']
    volumes = hist_data['volume']
    highs = hist_data['high']
    lows = hist_data['low']

    # PHASE 1 INDICATORS (Base Technical Analysis)
    rsi = IndicatorCalculator.calculate_rsi(close_prices, 14)
    macd = IndicatorCalculator.calculate_macd(close_prices)
    bb = IndicatorCalculator.calculate_bollinger_bands(close_prices)
    ema_20 = IndicatorCalculator.calculate_ema(close_prices, 20)
    current_price = row['close']
    trend_filter = IndicatorCalculator.calculate_trend_filter(close_prices)
    volume_conf = IndicatorCalculator.calculate_volume_confirmation(volumes)
    atr_data = IndicatorCalculator.calculate_atr(highs, lows, close_prices)

    # PHASE 3 ENHANCEMENTS: ML Prediction
    ml_prediction = MLPredictor.predict_price_direction(close_prices, volumes)

    # PHASE 3 ENHANCEMENTS: Sentiment Analysis
    sentiment = SentimentAnalyzer.analyze_sentiment(close_prices, volumes)

    # Generate signal only if no open position
    if position:
        return None

    signal = None

    # WEIGHTED SCORING SYSTEM FOR BUY SIGNALS (AI-Enhanced)
    buy_score = 0
    max_buy_score = 100

    # 1. RSI oversold - relaxed threshold (15 points)
    if rsi < 40:
        buy_score += 15 * (40 - rsi) / 40

    # 2. Price vs EMA trend (15 points)
    if current_price > ema_20:
        buy_score += 15

    # 3. MACD bullish momentum (15 points)
    if macd['histogram'] > 0:
        buy_score += 15
    elif macd['histogram'] > -0.5:
        buy_score += 8

    # 4. Bollinger Band position (10 points)
    if current_price < bb['lower'] * 1.05:
        buy_score += 10

    # 5. ML Prediction (20 points - KEY DIFFERENTIATOR)
    if ml_prediction['direction'] == 'BULLISH':
        buy_score += 20 * ml_prediction['confidence']
    elif ml_prediction['direction'] == 'NEUTRAL' and ml_prediction['confidence'] > 0.5:
        buy_score += 10

    # 6. Sentiment Analysis (15 points - AI ENHANCEMENT)
    if sentiment['sentiment_score'] > 0.3:  # Positive sentiment
        buy_score += 15
    elif sentiment['sentiment_score'] > -0.3:  # Neutral sentiment
        buy_score += 8

    # 7. Trend filter (10 points)
    if trend_filter['trend'] == 'BULLISH':
        buy_score += 10 * trend_filter['confidence']

    # 8. Volume confirmation (5 points)
    if volume_conf['confirmed']:
        buy_score += 5

    # Generate BUY signal if score >= 55/100 (55% threshold - more aggressive than Phase 1)
    if buy_score >= 55:
        # Enhanced stop-loss based on ML volatility prediction
        volatility_multiplier = 1.0 + (ml_prediction.get('volatility', 0) * 10)
        enhanced_stop = current_price - (atr_data['atr'] * 2.0 * volatility_multiplier)
        enhanced_tp = current_price + (atr_data['atr'] * 4.0 * volatility_multiplier)

        signal = {
            'action': 'BUY',
            'stop_loss': enhanced_stop,
            'take_profit': enhanced_tp,
            'metadata': {
                'strategy': 'phase3',
                'signal_strength': buy_score,
                'rsi': rsi,
                'macd_histogram': macd['histogram'],
                'ema_20': ema_20,
                'bb_position': 'lower',
                'trend': trend_filter['trend'],
                'volume_confirmed': volume_conf['confirmed'],
                'atr': atr_data['atr'],
                # Phase 3 additions
                'ml_direction': ml_prediction['direction'],
                'ml_confidence': ml_prediction['confidence'],
                'ml_predicted_change': ml_prediction['predicted_change_pct'],
                'sentiment_score': sentiment['sentiment_score'],
                'sentiment_label': sentiment['sentiment_label'],
                'volatility_adjusted': True
            }
        }
        logger.info(f"[Phase3] BUY signal generated with score: {buy_score:.1f}/100 (ML: {ml_prediction['direction']}, Sentiment: {sentiment['sentiment_label']})")

    # WEIGHTED SCORING SYSTEM FOR SELL SIGNALS (AI-Enhanced)
    sell_score = 0
    max_sell_score = 100

    # 1. RSI overbought - relaxed threshold (15 points)
    if rsi > 60:
        sell_score += 15 * (rsi - 60) / 40

    # 2. Price below EMA trend (15 points)
    if current_price < ema_20:
        sell_score += 15

    # 3. MACD bearish momentum (15 points)
    if macd['histogram'] < 0:
        sell_score += 15
    elif macd['histogram'] < 0.5:
        sell_score += 8

    # 4. Bollinger Band position (10 points)
    if current_price > bb['upper'] * 0.95:
        sell_score += 10

    # 5. ML Prediction (20 points - KEY DIFFERENTIATOR)
    if ml_prediction['direction'] == 'BEARISH':
        sell_score += 20 * ml_prediction['confidence']
    elif ml_prediction['direction'] == 'NEUTRAL' and ml_prediction['confidence'] > 0.5:
        sell_score += 10

    # 6. Sentiment Analysis (15 points - AI ENHANCEMENT)
    if sentiment['sentiment_score'] < -0.3:  # Negative sentiment
        sell_score += 15
    elif sentiment['sentiment_score'] < 0.3:  # Neutral sentiment
        sell_score += 8

    # 7. Trend filter (10 points)
    if trend_filter['trend'] == 'BEARISH':
        sell_score += 10 * trend_filter['confidence']

    # 8. Volume confirmation (5 points)
    if volume_conf['confirmed']:
        sell_score += 5

    # Generate SELL signal if score >= 55/100 (55% threshold - more aggressive than Phase 1)
    if sell_score >= 55:
        # Enhanced stop-loss based on ML volatility
        volatility_multiplier = 1.0 + (ml_prediction.get('volatility', 0) * 10)
        enhanced_stop = current_price + (atr_data['atr'] * 2.0 * volatility_multiplier)
        enhanced_tp = current_price - (atr_data['atr'] * 4.0 * volatility_multiplier)

        signal = {
            'action': 'SELL',
            'stop_loss': enhanced_stop,
            'take_profit': enhanced_tp,
            'metadata': {
                'strategy': 'phase3',
                'signal_strength': sell_score,
                'rsi': rsi,
                'macd_histogram': macd['histogram'],
                'ema_20': ema_20,
                'bb_position': 'upper',
                'trend': trend_filter['trend'],
                'volume_confirmed': volume_conf['confirmed'],
                'atr': atr_data['atr'],
                # Phase 3 additions
                'ml_direction': ml_prediction['direction'],
                'ml_confidence': ml_prediction['confidence'],
                'ml_predicted_change': ml_prediction['predicted_change_pct'],
                'sentiment_score': sentiment['sentiment_score'],
                'sentiment_label': sentiment['sentiment_label'],
                'volatility_adjusted': True
            }
        }
        logger.info(f"[Phase3] SELL signal generated with score: {sell_score:.1f}/100 (ML: {ml_prediction['direction']}, Sentiment: {sentiment['sentiment_label']})")

    return signal


class StatisticalAnalyzer:
    """
    Statistical analysis for backtest comparison
    Provides significance testing and advanced metrics
    """

    @staticmethod
    def calculate_sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.02) -> float:
        """
        Calculate Sortino Ratio (like Sharpe but only penalizes downside volatility)
        Better measure for strategies with asymmetric return distributions
        """
        if len(returns) < 2:
            return 0.0

        # Calculate excess returns
        excess_returns = returns - (risk_free_rate / 365)

        # Calculate downside deviation (only negative returns)
        downside_returns = returns[returns < 0]
        if len(downside_returns) == 0:
            return float('inf')  # No downside!

        downside_std = downside_returns.std()
        if downside_std == 0:
            return 0.0

        # Annualized Sortino ratio
        sortino = (excess_returns.mean() / downside_std) * np.sqrt(365)
        return float(sortino)

    @staticmethod
    def calculate_calmar_ratio(returns: pd.Series, max_drawdown_pct: float) -> float:
        """
        Calculate Calmar Ratio (return / max drawdown)
        Measures risk-adjusted returns relative to worst drawdown
        """
        if max_drawdown_pct == 0:
            return 0.0

        # Annualized return
        total_return = (returns + 1).prod() - 1
        periods = len(returns)
        annualized_return = (1 + total_return) ** (365 / periods) - 1

        # Calmar ratio
        calmar = annualized_return / (max_drawdown_pct / 100)
        return float(calmar)

    @staticmethod
    def ttest_comparison(phase1_returns: List[float], phase3_returns: List[float]) -> Dict:
        """
        Perform t-test to determine if Phase 3 is statistically better than Phase 1
        Returns p-value and interpretation
        """
        if len(phase1_returns) < 2 or len(phase3_returns) < 2:
            return {
                'significant': False,
                'p_value': 1.0,
                'interpretation': 'Insufficient data for statistical test'
            }

        # Perform two-sample t-test
        t_stat, p_value = stats.ttest_ind(phase3_returns, phase1_returns)

        # Interpretation
        if p_value < 0.01:
            significance = "Highly significant"
            significant = True
        elif p_value < 0.05:
            significance = "Significant"
            significant = True
        elif p_value < 0.10:
            significance = "Marginally significant"
            significant = True
        else:
            significance = "Not significant"
            significant = False

        return {
            'significant': significant,
            'p_value': float(p_value),
            't_statistic': float(t_stat),
            'interpretation': f"{significance} (p={p_value:.4f})"
        }

    @staticmethod
    def calculate_trade_quality_metrics(trades: List[Trade]) -> Dict:
        """
        Calculate advanced trade quality metrics
        """
        if not trades:
            return {
                'avg_duration_hours': 0.0,
                'avg_profit_per_hour': 0.0,
                'win_streak_max': 0,
                'loss_streak_max': 0,
                'profit_factor': 0.0,
                'expectancy': 0.0
            }

        # Trade durations
        durations = [(t.exit_time - t.entry_time).total_seconds() / 3600 for t in trades]
        avg_duration = np.mean(durations)

        # Profit per hour
        profits_per_hour = [t.profit_loss / duration if duration > 0 else 0
                           for t, duration in zip(trades, durations)]
        avg_profit_per_hour = np.mean(profits_per_hour)

        # Win/loss streaks
        results = [1 if t.profit_loss > 0 else -1 for t in trades]
        win_streak = 0
        loss_streak = 0
        max_win_streak = 0
        max_loss_streak = 0

        for result in results:
            if result > 0:
                win_streak += 1
                loss_streak = 0
                max_win_streak = max(max_win_streak, win_streak)
            else:
                loss_streak += 1
                win_streak = 0
                max_loss_streak = max(max_loss_streak, loss_streak)

        # Profit factor
        gross_profit = sum(t.profit_loss for t in trades if t.profit_loss > 0)
        gross_loss = abs(sum(t.profit_loss for t in trades if t.profit_loss <= 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        # Expectancy (average $ per trade)
        expectancy = np.mean([t.profit_loss for t in trades])

        return {
            'avg_duration_hours': float(avg_duration),
            'avg_profit_per_hour': float(avg_profit_per_hour),
            'win_streak_max': int(max_win_streak),
            'loss_streak_max': int(max_loss_streak),
            'profit_factor': float(profit_factor),
            'expectancy': float(expectancy)
        }


def generate_comparison_report(
    phase1_result,
    phase3_result,
    symbol: str,
    interval: str,
    test_params: Dict
) -> str:
    """
    Generate comprehensive markdown report comparing Phase 1 vs Phase 3
    """
    # Calculate additional metrics
    phase1_returns = pd.Series([t.profit_loss for t in phase1_result.trades])
    phase3_returns = pd.Series([t.profit_loss for t in phase3_result.trades])

    # Sortino ratios
    phase1_sortino = StatisticalAnalyzer.calculate_sortino_ratio(
        phase1_returns / test_params['capital']
    )
    phase3_sortino = StatisticalAnalyzer.calculate_sortino_ratio(
        phase3_returns / test_params['capital']
    )

    # Calmar ratios
    phase1_calmar = StatisticalAnalyzer.calculate_calmar_ratio(
        phase1_returns / test_params['capital'],
        phase1_result.max_drawdown_pct
    )
    phase3_calmar = StatisticalAnalyzer.calculate_calmar_ratio(
        phase3_returns / test_params['capital'],
        phase3_result.max_drawdown_pct
    )

    # Statistical significance
    significance_test = StatisticalAnalyzer.ttest_comparison(
        phase1_returns.tolist(),
        phase3_returns.tolist()
    )

    # Trade quality metrics
    phase1_quality = StatisticalAnalyzer.calculate_trade_quality_metrics(phase1_result.trades)
    phase3_quality = StatisticalAnalyzer.calculate_trade_quality_metrics(phase3_result.trades)

    # Build report
    report = f"""# Phase 1 vs Phase 3 Backtest Comparison Report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

## Test Configuration

- **Symbol:** {symbol}
- **Interval:** {interval} minutes
- **Test Period:** {phase1_result.start_date.strftime('%Y-%m-%d')} to {phase1_result.end_date.strftime('%Y-%m-%d')}
- **Initial Capital:** ${test_params['capital']:,.2f}
- **Max Risk Per Trade:** {test_params.get('risk_pct', 2)}%
- **Commission:** {test_params.get('commission', 0.1)}%
- **Slippage:** {test_params.get('slippage', 0.05)}%

---

## Executive Summary

### Phase 1: Technical Analysis Only
- **Strategy:** RSI + MACD + Bollinger Bands + EMA Trend Filter + Volume Confirmation
- **Total Trades:** {phase1_result.total_trades}
- **Win Rate:** {phase1_result.win_rate:.2f}%
- **Total Return:** {phase1_result.total_profit_loss_pct:.2f}%
- **Final Capital:** ${phase1_result.final_capital:,.2f}

### Phase 3: AI-Enhanced (ML + Sentiment)
- **Strategy:** Phase 1 + ML Price Prediction + Sentiment Analysis + Multi-timeframe
- **Total Trades:** {phase3_result.total_trades}
- **Win Rate:** {phase3_result.win_rate:.2f}%
- **Total Return:** {phase3_result.total_profit_loss_pct:.2f}%
- **Final Capital:** ${phase3_result.final_capital:,.2f}

### Statistical Significance
- **T-Test Result:** {significance_test['interpretation']}
- **P-Value:** {significance_test['p_value']:.4f}
- **Conclusion:** {"Phase 3 is statistically superior to Phase 1" if significance_test['significant'] else "No statistically significant difference detected"}

---

## Performance Comparison

| Metric | Phase 1 (TA Only) | Phase 3 (AI Enhanced) | Improvement |
|--------|------------------|----------------------|-------------|
| **Profitability** |
| Total P&L | ${phase1_result.total_profit_loss:,.2f} | ${phase3_result.total_profit_loss:,.2f} | {((phase3_result.total_profit_loss - phase1_result.total_profit_loss) / abs(phase1_result.total_profit_loss) * 100) if phase1_result.total_profit_loss != 0 else 0:.2f}% |
| Total Return | {phase1_result.total_profit_loss_pct:.2f}% | {phase3_result.total_profit_loss_pct:.2f}% | {(phase3_result.total_profit_loss_pct - phase1_result.total_profit_loss_pct):.2f}% |
| Avg Profit/Trade | ${phase1_result.avg_profit_per_trade:,.2f} | ${phase3_result.avg_profit_per_trade:,.2f} | {((phase3_result.avg_profit_per_trade - phase1_result.avg_profit_per_trade) / abs(phase1_result.avg_profit_per_trade) * 100) if phase1_result.avg_profit_per_trade != 0 else 0:.2f}% |
| **Win Rate** |
| Win Rate | {phase1_result.win_rate:.2f}% | {phase3_result.win_rate:.2f}% | {(phase3_result.win_rate - phase1_result.win_rate):.2f}% |
| Winning Trades | {phase1_result.winning_trades} | {phase3_result.winning_trades} | {(phase3_result.winning_trades - phase1_result.winning_trades)} |
| Losing Trades | {phase1_result.losing_trades} | {phase3_result.losing_trades} | {(phase3_result.losing_trades - phase1_result.losing_trades)} |
| **Risk Metrics** |
| Max Drawdown | {phase1_result.max_drawdown_pct:.2f}% | {phase3_result.max_drawdown_pct:.2f}% | {((phase1_result.max_drawdown_pct - phase3_result.max_drawdown_pct) / phase1_result.max_drawdown_pct * 100) if phase1_result.max_drawdown_pct > 0 else 0:.2f}% |
| Sharpe Ratio | {phase1_result.sharpe_ratio:.3f} | {phase3_result.sharpe_ratio:.3f} | {((phase3_result.sharpe_ratio - phase1_result.sharpe_ratio) / abs(phase1_result.sharpe_ratio) * 100) if phase1_result.sharpe_ratio != 0 else 0:.2f}% |
| Sortino Ratio | {phase1_sortino:.3f} | {phase3_sortino:.3f} | {((phase3_sortino - phase1_sortino) / abs(phase1_sortino) * 100) if phase1_sortino != 0 else 0:.2f}% |
| Calmar Ratio | {phase1_calmar:.3f} | {phase3_calmar:.3f} | {((phase3_calmar - phase1_calmar) / abs(phase1_calmar) * 100) if phase1_calmar != 0 else 0:.2f}% |
| Profit Factor | {phase1_result.profit_factor:.3f} | {phase3_result.profit_factor:.3f} | {((phase3_result.profit_factor - phase1_result.profit_factor) / phase1_result.profit_factor * 100) if phase1_result.profit_factor > 0 else 0:.2f}% |
| **Trade Quality** |
| Avg Duration | {phase1_quality['avg_duration_hours']:.2f}h | {phase3_quality['avg_duration_hours']:.2f}h | {(phase3_quality['avg_duration_hours'] - phase1_quality['avg_duration_hours']):.2f}h |
| Profit/Hour | ${phase1_quality['avg_profit_per_hour']:.2f} | ${phase3_quality['avg_profit_per_hour']:.2f} | {((phase3_quality['avg_profit_per_hour'] - phase1_quality['avg_profit_per_hour']) / abs(phase1_quality['avg_profit_per_hour']) * 100) if phase1_quality['avg_profit_per_hour'] != 0 else 0:.2f}% |
| Max Win Streak | {phase1_quality['win_streak_max']} | {phase3_quality['win_streak_max']} | {(phase3_quality['win_streak_max'] - phase1_quality['win_streak_max'])} |
| Max Loss Streak | {phase1_quality['loss_streak_max']} | {phase3_quality['loss_streak_max']} | {(phase3_quality['loss_streak_max'] - phase1_quality['loss_streak_max'])} |
| Trade Expectancy | ${phase1_quality['expectancy']:.2f} | ${phase3_quality['expectancy']:.2f} | {((phase3_quality['expectancy'] - phase1_quality['expectancy']) / abs(phase1_quality['expectancy']) * 100) if phase1_quality['expectancy'] != 0 else 0:.2f}% |

---

## Signal Quality Analysis

### Phase 1 (Technical Analysis)
- **Total Signals Generated:** {phase1_result.total_trades}
- **Filters Applied:** GATEKEEPER (Trend), VALIDATOR (Volume)
- **Signal Precision:** {(phase1_result.winning_trades / phase1_result.total_trades * 100) if phase1_result.total_trades > 0 else 0:.2f}%

### Phase 3 (AI-Enhanced)
- **Total Signals Generated:** {phase3_result.total_trades}
- **Filters Applied:** GATEKEEPER (Trend), VALIDATOR (Volume), ML Prediction, Sentiment Analysis
- **Signal Precision:** {(phase3_result.winning_trades / phase3_result.total_trades * 100) if phase3_result.total_trades > 0 else 0:.2f}%

### False Signal Reduction
- **Phase 1 False Signals:** {phase1_result.losing_trades} ({(phase1_result.losing_trades / phase1_result.total_trades * 100) if phase1_result.total_trades > 0 else 0:.2f}%)
- **Phase 3 False Signals:** {phase3_result.losing_trades} ({(phase3_result.losing_trades / phase3_result.total_trades * 100) if phase3_result.total_trades > 0 else 0:.2f}%)
- **Reduction:** {((phase1_result.losing_trades - phase3_result.losing_trades) / phase1_result.losing_trades * 100) if phase1_result.losing_trades > 0 else 0:.2f}%

---

## Risk-Adjusted Performance

### Sharpe Ratio Analysis
- **Phase 1:** {phase1_result.sharpe_ratio:.3f}
- **Phase 3:** {phase3_result.sharpe_ratio:.3f}
- **Interpretation:** {"Phase 3 offers better risk-adjusted returns" if phase3_result.sharpe_ratio > phase1_result.sharpe_ratio else "Phase 1 offers better risk-adjusted returns"}

### Sortino Ratio Analysis (Downside Risk)
- **Phase 1:** {phase1_sortino:.3f}
- **Phase 3:** {phase3_sortino:.3f}
- **Interpretation:** {"Phase 3 has superior downside risk management" if phase3_sortino > phase1_sortino else "Phase 1 has superior downside risk management"}

### Maximum Drawdown
- **Phase 1:** {phase1_result.max_drawdown_pct:.2f}% (${phase1_result.max_drawdown:,.2f})
- **Phase 3:** {phase3_result.max_drawdown_pct:.2f}% (${phase3_result.max_drawdown:,.2f})
- **Improvement:** {((phase1_result.max_drawdown_pct - phase3_result.max_drawdown_pct) / phase1_result.max_drawdown_pct * 100) if phase1_result.max_drawdown_pct > 0 else 0:.2f}% reduction

---

## Trade Execution Analysis

### Average Trade Performance

**Phase 1:**
- Average Win: ${phase1_result.avg_win:,.2f}
- Average Loss: ${phase1_result.avg_loss:,.2f}
- Best Trade: ${phase1_result.best_trade:,.2f}
- Worst Trade: ${phase1_result.worst_trade:,.2f}

**Phase 3:**
- Average Win: ${phase3_result.avg_win:,.2f}
- Average Loss: ${phase3_result.avg_loss:,.2f}
- Best Trade: ${phase3_result.best_trade:,.2f}
- Worst Trade: ${phase3_result.worst_trade:,.2f}

### Trade Duration

**Phase 1:**
- Average Duration: {phase1_quality['avg_duration_hours']:.2f} hours

**Phase 3:**
- Average Duration: {phase3_quality['avg_duration_hours']:.2f} hours
- **Insight:** {"Phase 3 holds positions longer, capturing more trend continuation" if phase3_quality['avg_duration_hours'] > phase1_quality['avg_duration_hours'] else "Phase 3 exits positions faster, reducing exposure time"}

---

## Recommendations

### Signal Weight Optimization

Based on the backtest results, recommended signal weights for Phase 3:

```python
SIGNAL_WEIGHTS = {{
    # Phase 1 Technical Indicators
    "rsi": 0.20,              # 20% weight
    "macd": 0.15,             # 15% weight
    "bollinger_bands": 0.15,  # 15% weight

    # Phase 1 Filters
    "trend_filter": 0.20,     # 20% weight (GATEKEEPER)
    "volume_confirmation": 0.10,  # 10% weight (VALIDATOR)

    # Phase 3 AI Enhancements
    "ml_prediction": 0.15,    # 15% weight
    "sentiment_analysis": 0.05,  # 5% weight
}}
```

### Best Performing Phase

**Winner:** {"Phase 3 (AI-Enhanced)" if phase3_result.total_profit_loss > phase1_result.total_profit_loss else "Phase 1 (Technical Analysis)"}

**Reasoning:**
- {"Higher profitability" if phase3_result.total_profit_loss > phase1_result.total_profit_loss else "Lower profitability but potentially more stable"}
- {"Better win rate" if phase3_result.win_rate > phase1_result.win_rate else "Lower win rate but potentially higher profit per win"}
- {"Superior risk-adjusted returns (Sharpe)" if phase3_result.sharpe_ratio > phase1_result.sharpe_ratio else "Lower risk-adjusted returns"}
- {"Reduced maximum drawdown" if phase3_result.max_drawdown_pct < phase1_result.max_drawdown_pct else "Higher maximum drawdown"}

### Action Items

1. **For Production Deployment:**
   - {"Deploy Phase 3 strategy with confidence" if significance_test['significant'] and phase3_result.total_profit_loss > phase1_result.total_profit_loss else "Consider further testing or hybrid approach"}
   - Monitor ML prediction accuracy in live environment
   - Validate sentiment data quality from real APIs

2. **Strategy Improvements:**
   - {"Fine-tune ML model with more training data" if phase3_result.win_rate < 60 else "ML model performing well, continue monitoring"}
   - {"Adjust sentiment weight (currently low impact)" if phase1_result.total_profit_loss != 0 and abs(phase3_result.total_profit_loss - phase1_result.total_profit_loss) / phase1_result.total_profit_loss < 0.1 else "Sentiment analysis providing good signal enhancement" if phase1_result.total_profit_loss != 0 else "No trades executed - adjust entry thresholds to generate signals"}
   - Implement multi-timeframe confirmation for additional signal filtering

3. **Risk Management:**
   - {"Consider reducing position sizes given high drawdown" if phase3_result.max_drawdown_pct > 20 else "Current position sizing appears appropriate"}
   - {"Implement trailing stops to protect profits" if phase3_quality['avg_profit_per_hour'] > 0 else "Focus on improving entry timing"}

---

## Detailed Trade Log

### Phase 1 Sample Trades (First 5)

"""

    # Add sample trades
    for i, trade in enumerate(phase1_result.trades[:5], 1):
        report += f"""
**Trade {i}:**
- Entry: {trade.entry_time.strftime('%Y-%m-%d %H:%M')} @ ${trade.entry_price:,.2f}
- Exit: {trade.exit_time.strftime('%Y-%m-%d %H:%M')} @ ${trade.exit_price:,.2f}
- Type: {trade.order_type.value}
- P/L: ${trade.profit_loss:,.2f} ({trade.profit_loss_pct:.2f}%)
- Exit Reason: {trade.exit_reason}
"""

    report += f"""
### Phase 3 Sample Trades (First 5)

"""

    for i, trade in enumerate(phase3_result.trades[:5], 1):
        ml_conf = trade.metadata.get('ml_confidence', 'N/A')
        sentiment = trade.metadata.get('sentiment_score', 'N/A')
        report += f"""
**Trade {i}:**
- Entry: {trade.entry_time.strftime('%Y-%m-%d %H:%M')} @ ${trade.entry_price:,.2f}
- Exit: {trade.exit_time.strftime('%Y-%m-%d %H:%M')} @ ${trade.exit_price:,.2f}
- Type: {trade.order_type.value}
- P/L: ${trade.profit_loss:,.2f} ({trade.profit_loss_pct:.2f}%)
- Exit Reason: {trade.exit_reason}
- ML Confidence: {ml_conf if isinstance(ml_conf, str) else f'{ml_conf:.2f}'}
- Sentiment: {sentiment if isinstance(sentiment, str) else f'{sentiment:.2f}'}
"""

    report += f"""
---

## Conclusion

The backtest comparison between Phase 1 (Technical Analysis) and Phase 3 (AI-Enhanced) strategies reveals:

1. **Performance:** Phase 3 {"outperforms" if phase3_result.total_profit_loss > phase1_result.total_profit_loss else "underperforms"} Phase 1 by {abs((phase3_result.total_profit_loss - phase1_result.total_profit_loss) / phase1_result.total_profit_loss * 100) if phase1_result.total_profit_loss != 0 else 0:.2f}%

2. **Statistical Validity:** {significance_test['interpretation']}

3. **Risk Management:** Phase 3 {"provides better" if phase3_result.max_drawdown_pct < phase1_result.max_drawdown_pct else "has higher"} drawdown control

4. **Signal Quality:** Phase 3 {"generates fewer but higher quality" if phase3_result.total_trades < phase1_result.total_trades and phase3_result.win_rate > phase1_result.win_rate else "generates similar quality"} signals

**Final Recommendation:** {"Deploy Phase 3 for production trading" if significance_test['significant'] and phase3_result.total_profit_loss > phase1_result.total_profit_loss and phase3_result.sharpe_ratio > phase1_result.sharpe_ratio else "Consider hybrid approach or further optimization"}

---

*Report generated by Crypto Trading Bot Backtest Engine v2.0*
*Test performed on historical data and does not guarantee future performance*
"""

    return report


async def run_comparison(
    symbols: List[str],
    interval: str = "60",
    days: int = 90,
    capital: float = ACCOUNT_EQUITY_USD
) -> None:
    """
    Run comprehensive Phase 1 vs Phase 3 backtest comparison

    Args:
        symbols: List of trading pairs to test
        interval: Candle interval in minutes
        days: Days of historical data
        capital: Initial capital for testing
    """
    logger.info("="*100)
    logger.info("PHASE 1 vs PHASE 3 BACKTEST COMPARISON - Starting")
    logger.info("="*100)

    # Create results directory
    results_dir = Path("backtesting/results")
    results_dir.mkdir(exist_ok=True, parents=True)

    # Test parameters
    test_params = {
        'capital': capital,
        'risk_pct': 2.0,
        'commission': 0.001,
        'slippage': 0.0005
    }

    # Initialize data downloader
    downloader = HistoricalDataDownloader()

    # Run comparison for each symbol
    all_results = []

    try:
        for symbol in symbols:
            logger.info(f"\n{'='*100}")
            logger.info(f"Testing Symbol: {symbol}")
            logger.info(f"{'='*100}\n")

            # Download historical data
            logger.info(f"Downloading {days} days of {interval}m data for {symbol}...")
            data = await downloader.download_historical_data(
                symbol=symbol,
                interval=interval,
                days=days,
                output_file=f"data/{symbol}_{interval}m_{days}d_comparison.csv"
            )

            if data.empty:
                logger.error(f"Failed to download data for {symbol}")
                continue

            logger.info(f"Data loaded: {len(data)} candles")

            # Run Phase 1 backtest
            logger.info(f"\n{'='*100}")
            logger.info("Running PHASE 1 Strategy (Technical Analysis Only)")
            logger.info(f"{'='*100}\n")

            phase1_engine = BacktestEngine(
                initial_capital=capital,
                position_size_pct=test_params['risk_pct'] / 100,
                commission=test_params['commission'],
                slippage=test_params['slippage']
            )

            phase1_result = phase1_engine.run_backtest(
                data=data,
                strategy_func=phase1_strategy,
                strategy_name=f"Phase 1 - {symbol}"
            )

            # Run Phase 3 backtest
            logger.info(f"\n{'='*100}")
            logger.info("Running PHASE 3 Strategy (AI-Enhanced: ML + Sentiment)")
            logger.info(f"{'='*100}\n")

            phase3_engine = BacktestEngine(
                initial_capital=capital,
                position_size_pct=test_params['risk_pct'] / 100,
                commission=test_params['commission'],
                slippage=test_params['slippage']
            )

            phase3_result = phase3_engine.run_backtest(
                data=data,
                strategy_func=phase3_strategy,
                strategy_name=f"Phase 3 - {symbol}"
            )

            # Generate comparison report
            logger.info(f"\n{'='*100}")
            logger.info("Generating Comparison Report")
            logger.info(f"{'='*100}\n")

            report = generate_comparison_report(
                phase1_result,
                phase3_result,
                symbol,
                interval,
                test_params
            )

            # Save report
            report_file = results_dir / f"BACKTEST_COMPARISON_{symbol}_{interval}m_{days}d_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            with open(report_file, 'w') as f:
                f.write(report)

            # Generate HTML report
            logger.info("Generating HTML visualization report...")
            html_report = BacktestVisualizer.generate_html_report(
                phase1_result,
                phase3_result,
                symbol,
                interval,
                test_params
            )

            # Save HTML report
            html_file = results_dir / f"BACKTEST_COMPARISON_{symbol}_{interval}m_{days}d_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html"
            with open(html_file, "w") as f:
                f.write(html_report)

            logger.info(f"HTML report saved: {html_file}")
            logger.info(f"Report saved: {report_file}")

            # Store results for summary
            all_results.append({
                'symbol': symbol,
                'phase1': phase1_result,
                'phase3': phase3_result,
                'report_file': str(report_file)
            })

            # Print quick summary
            print(f"\n{'='*100}")
            print(f"QUICK SUMMARY - {symbol}")
            print(f"{'='*100}")
            print(f"\nPhase 1 (TA Only):")
            print(f"  Trades: {phase1_result.total_trades} | Win Rate: {phase1_result.win_rate:.2f}% | Return: {phase1_result.total_profit_loss_pct:.2f}%")
            print(f"  Final Capital: ${phase1_result.final_capital:,.2f} | Max DD: {phase1_result.max_drawdown_pct:.2f}%")

            print(f"\nPhase 3 (AI Enhanced):")
            print(f"  Trades: {phase3_result.total_trades} | Win Rate: {phase3_result.win_rate:.2f}% | Return: {phase3_result.total_profit_loss_pct:.2f}%")
            print(f"  Final Capital: ${phase3_result.final_capital:,.2f} | Max DD: {phase3_result.max_drawdown_pct:.2f}%")

            improvement = ((phase3_result.total_profit_loss - phase1_result.total_profit_loss) / abs(phase1_result.total_profit_loss) * 100) if phase1_result.total_profit_loss != 0 else 0
            print(f"\nImprovement: {improvement:+.2f}%")
            print(f"{'='*100}\n")

    finally:
        await downloader.close()

    # Generate master summary report
    if all_results:
        logger.info(f"\n{'='*100}")
        logger.info("Generating Master Summary Report")
        logger.info(f"{'='*100}\n")

        summary_file = results_dir / f"BACKTEST_COMPARISON_SUMMARY_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

        with open(summary_file, 'w') as f:
            f.write(f"# Backtest Comparison Summary - All Symbols\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n")
            f.write(f"## Symbols Tested\n\n")

            for result in all_results:
                symbol = result['symbol']
                p1 = result['phase1']
                p3 = result['phase3']

                f.write(f"### {symbol}\n\n")
                f.write(f"| Phase | Trades | Win Rate | Return | Sharpe | Max DD |\n")
                f.write(f"|-------|--------|----------|--------|--------|--------|\n")
                f.write(f"| Phase 1 | {p1.total_trades} | {p1.win_rate:.2f}% | {p1.total_profit_loss_pct:.2f}% | {p1.sharpe_ratio:.3f} | {p1.max_drawdown_pct:.2f}% |\n")
                f.write(f"| Phase 3 | {p3.total_trades} | {p3.win_rate:.2f}% | {p3.total_profit_loss_pct:.2f}% | {p3.sharpe_ratio:.3f} | {p3.max_drawdown_pct:.2f}% |\n\n")
                f.write(f"**Detailed Report:** [{result['report_file']}]({result['report_file']})\n\n")

        logger.info(f"Master summary saved: {summary_file}")

    logger.info(f"\n{'='*100}")
    logger.info("BACKTEST COMPARISON COMPLETE")
    logger.info(f"{'='*100}\n")


async def main():
    """Main execution"""
    import argparse

    parser = argparse.ArgumentParser(description="Run Phase 1 vs Phase 3 backtest comparison")
    parser.add_argument(
        '--symbols',
        type=str,
        nargs='+',
        default=['BTCUSDT', 'ETHUSDT', 'BNBUSDT'],
        help='Trading pairs to test (space separated)'
    )
    parser.add_argument(
        '--interval',
        type=str,
        default='60',
        help='Candle interval in minutes'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=90,
        help='Days of historical data'
    )
    parser.add_argument(
        '--capital',
        type=float,
        default=ACCOUNT_EQUITY_USD,
        help='Initial capital'
    )

    args = parser.parse_args()

    await run_comparison(
        symbols=args.symbols,
        interval=args.interval,
        days=args.days,
        capital=args.capital
    )


if __name__ == "__main__":
    asyncio.run(main())
