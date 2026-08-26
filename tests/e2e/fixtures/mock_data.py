#!/usr/bin/env python3
"""
Mock Data Generators for E2E Testing

Utilities to generate realistic test data for trading scenarios.
"""

import time
import random
from typing import List, Dict, Optional
from decimal import Decimal
from datetime import datetime, timedelta

from shared.account import ACCOUNT_EQUITY_USD  # noqa: F401


def generate_bullish_candles(
    start_price: float = 100.0,
    num_candles: int = 20,
    price_increase_pct: float = 5.0
) -> List[Dict]:
    """
    Generate bullish (uptrending) candlestick data.

    Args:
        start_price: Starting price
        num_candles: Number of candles to generate
        price_increase_pct: Total price increase percentage

    Returns:
        List of OHLCV candlestick dictionaries
    """
    candles = []
    current_price = start_price
    price_step = (start_price * price_increase_pct / 100) / num_candles
    current_time = int(time.time()) - (num_candles * 60)  # 1-minute candles

    for i in range(num_candles):
        # Bullish candle: close > open
        open_price = current_price
        close_price = current_price + price_step + random.uniform(-0.5, 1.0)
        high_price = max(open_price, close_price) + random.uniform(0.1, 0.5)
        low_price = min(open_price, close_price) - random.uniform(0.1, 0.3)
        volume = random.uniform(1000, 5000)

        candles.append({
            "timestamp": current_time + (i * 60),
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "close": round(close_price, 2),
            "volume": round(volume, 2)
        })

        current_price = close_price

    return candles


def generate_bearish_candles(
    start_price: float = 100.0,
    num_candles: int = 20,
    price_decrease_pct: float = 5.0
) -> List[Dict]:
    """
    Generate bearish (downtrending) candlestick data.

    Args:
        start_price: Starting price
        num_candles: Number of candles to generate
        price_decrease_pct: Total price decrease percentage

    Returns:
        List of OHLCV candlestick dictionaries
    """
    candles = []
    current_price = start_price
    price_step = (start_price * price_decrease_pct / 100) / num_candles
    current_time = int(time.time()) - (num_candles * 60)

    for i in range(num_candles):
        # Bearish candle: close < open
        open_price = current_price
        close_price = current_price - price_step - random.uniform(-0.5, 1.0)
        high_price = max(open_price, close_price) + random.uniform(0.1, 0.3)
        low_price = min(open_price, close_price) - random.uniform(0.1, 0.5)
        volume = random.uniform(1000, 5000)

        candles.append({
            "timestamp": current_time + (i * 60),
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "close": round(close_price, 2),
            "volume": round(volume, 2)
        })

        current_price = close_price

    return candles


def generate_sideways_candles(
    base_price: float = 100.0,
    num_candles: int = 20,
    volatility: float = 1.0
) -> List[Dict]:
    """
    Generate sideways (ranging) candlestick data.

    Args:
        base_price: Base price to oscillate around
        num_candles: Number of candles to generate
        volatility: Price volatility range (+/- percentage)

    Returns:
        List of OHLCV candlestick dictionaries
    """
    candles = []
    current_time = int(time.time()) - (num_candles * 60)

    for i in range(num_candles):
        # Sideways movement around base price
        open_price = base_price + random.uniform(-volatility, volatility)
        close_price = base_price + random.uniform(-volatility, volatility)
        high_price = max(open_price, close_price) + random.uniform(0.1, 0.5)
        low_price = min(open_price, close_price) - random.uniform(0.1, 0.5)
        volume = random.uniform(800, 3000)

        candles.append({
            "timestamp": current_time + (i * 60),
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "close": round(close_price, 2),
            "volume": round(volume, 2)
        })

    return candles


def generate_price_spike(
    base_candles: List[Dict],
    spike_index: int,
    spike_pct: float = 10.0,
    direction: str = "up"
) -> List[Dict]:
    """
    Add a price spike to existing candle data.

    Args:
        base_candles: Base candlestick data
        spike_index: Index where spike should occur
        spike_pct: Spike percentage
        direction: "up" or "down"

    Returns:
        Modified candlestick list with spike
    """
    candles = base_candles.copy()

    if 0 <= spike_index < len(candles):
        candle = candles[spike_index].copy()
        spike_amount = candle["close"] * (spike_pct / 100)

        if direction == "up":
            candle["high"] += spike_amount
            candle["close"] += spike_amount
        else:
            candle["low"] -= spike_amount
            candle["close"] -= spike_amount

        candles[spike_index] = candle

    return candles


def generate_trade_data(
    symbol: str = "BTCUSDT",
    side: str = "BUY",
    quantity: float = 0.01,
    price: float = 100.0,
    pnl: float = 0.0
) -> Dict:
    """
    Generate mock trade data.

    Args:
        symbol: Trading symbol
        side: Trade side ("BUY" or "SELL")
        quantity: Trade quantity
        price: Execution price
        pnl: Profit/loss

    Returns:
        Trade dictionary
    """
    return {
        "id": f"trade_{int(time.time())}_{random.randint(1000, 9999)}",
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "price": price,
        "timestamp": int(time.time()),
        "status": "FILLED",
        "pnl": pnl,
        "commission": round(price * quantity * 0.001, 4)  # 0.1% commission
    }


def generate_portfolio_data(
    balance: float = ACCOUNT_EQUITY_USD,
    positions: Optional[List[Dict]] = None
) -> Dict:
    """
    Generate mock portfolio data.

    Args:
        balance: Account balance
        positions: List of open positions

    Returns:
        Portfolio dictionary
    """
    if positions is None:
        positions = []

    total_position_value = sum(
        pos.get("quantity", 0) * pos.get("entry_price", 0)
        for pos in positions
    )

    return {
        "balance": balance,
        "available_balance": balance - total_position_value,
        "total_equity": balance + sum(pos.get("unrealized_pnl", 0) for pos in positions),
        "positions": positions,
        "timestamp": int(time.time())
    }


def generate_position_data(
    symbol: str = "BTCUSDT",
    side: str = "BUY",
    quantity: float = 0.01,
    entry_price: float = 100.0,
    current_price: Optional[float] = None
) -> Dict:
    """
    Generate mock position data.

    Args:
        symbol: Trading symbol
        side: Position side
        quantity: Position quantity
        entry_price: Entry price
        current_price: Current market price (for unrealized P&L)

    Returns:
        Position dictionary
    """
    if current_price is None:
        current_price = entry_price

    if side == "BUY":
        unrealized_pnl = (current_price - entry_price) * quantity
    else:  # SELL
        unrealized_pnl = (entry_price - current_price) * quantity

    return {
        "id": f"pos_{symbol}_{side}_{int(time.time())}",
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "entry_price": entry_price,
        "current_price": current_price,
        "unrealized_pnl": round(unrealized_pnl, 2),
        "timestamp": int(time.time())
    }


def generate_indicator_data(
    rsi: Optional[float] = None,
    macd: Optional[float] = None,
    bb_position: Optional[float] = None,
    trend_filter: Optional[str] = None
) -> Dict:
    """
    Generate mock technical indicator data.

    Args:
        rsi: RSI value (0-100)
        macd: MACD value
        bb_position: Bollinger Band position (0-100)
        trend_filter: Trend direction ("BULLISH", "BEARISH", "NEUTRAL")

    Returns:
        Indicators dictionary
    """
    # Generate random values if not provided
    if rsi is None:
        rsi = random.uniform(20, 80)
    if macd is None:
        macd = random.uniform(-2, 2)
    if bb_position is None:
        bb_position = random.uniform(10, 90)
    if trend_filter is None:
        trend_filter = random.choice(["BULLISH", "BEARISH", "NEUTRAL"])

    # Determine signals based on values
    rsi_signal = "BUY" if rsi < 30 else ("SELL" if rsi > 70 else "NEUTRAL")
    macd_signal = "BUY" if macd > 0 else "SELL"
    bb_signal = "BUY" if bb_position < 20 else ("SELL" if bb_position > 80 else "NEUTRAL")

    return {
        "RSI": {
            "name": "RSI",
            "value": round(rsi, 2),
            "signal": rsi_signal,
            "confidence": abs(rsi - 50) / 50  # Higher confidence further from 50
        },
        "MACD": {
            "name": "MACD",
            "value": round(macd, 4),
            "signal": macd_signal,
            "confidence": min(abs(macd) / 2, 1.0)  # Normalize to 0-1
        },
        "BB": {
            "name": "Bollinger Bands",
            "value": round(bb_position, 2),
            "signal": bb_signal,
            "confidence": abs(bb_position - 50) / 50
        },
        "TREND_FILTER": {
            "name": "Trend Filter",
            "value": 1.0 if trend_filter == "BULLISH" else (-1.0 if trend_filter == "BEARISH" else 0.0),
            "signal": "BUY" if trend_filter == "BULLISH" else ("SELL" if trend_filter == "BEARISH" else "NEUTRAL"),
            "confidence": 0.9 if trend_filter != "NEUTRAL" else 0.5,
            "metadata": {"trend": trend_filter}
        }
    }


def generate_signal_data(
    action: str = "BUY",
    confidence: float = 0.75,
    symbol: str = "BTCUSDT",
    indicators: Optional[Dict] = None
) -> Dict:
    """
    Generate mock trading signal data.

    Args:
        action: Signal action ("BUY", "SELL", "HOLD")
        confidence: Signal confidence (0-1)
        symbol: Trading symbol
        indicators: Contributing indicators

    Returns:
        Signal dictionary
    """
    if indicators is None:
        indicators = generate_indicator_data()

    return {
        "symbol": symbol,
        "action": action,
        "confidence": confidence,
        "timestamp": int(time.time()),
        "indicators": indicators,
        "metadata": {
            "strategy": "multi_indicator",
            "timeframe": "60m"
        }
    }


def generate_market_data_series(
    symbol: str = "BTCUSDT",
    num_points: int = 100,
    trend: str = "bullish",
    start_price: float = 100.0
) -> List[Dict]:
    """
    Generate a complete time series of market data.

    Args:
        symbol: Trading symbol
        num_points: Number of data points
        trend: Market trend ("bullish", "bearish", "sideways")
        start_price: Starting price

    Returns:
        List of market data points
    """
    if trend == "bullish":
        return generate_bullish_candles(start_price, num_points)
    elif trend == "bearish":
        return generate_bearish_candles(start_price, num_points)
    else:  # sideways
        return generate_sideways_candles(start_price, num_points)


def generate_order_book(
    current_price: float = 100.0,
    depth: int = 10
) -> Dict:
    """
    Generate mock order book data.

    Args:
        current_price: Current market price
        depth: Number of levels on each side

    Returns:
        Order book dictionary
    """
    bids = []
    asks = []

    for i in range(depth):
        bid_price = current_price - (i + 1) * 0.01
        ask_price = current_price + (i + 1) * 0.01
        quantity = random.uniform(0.1, 1.0)

        bids.append([round(bid_price, 2), round(quantity, 4)])
        asks.append([round(ask_price, 2), round(quantity, 4)])

    return {
        "symbol": "BTCUSDT",
        "bids": bids,
        "asks": asks,
        "timestamp": int(time.time())
    }


# Convenience functions
def create_profitable_trade_scenario():
    """Create mock data for a profitable trading scenario."""
    entry_price = 100.0
    exit_price = 110.0
    quantity = 0.1

    return {
        "entry_trade": generate_trade_data("BTCUSDT", "BUY", quantity, entry_price, 0),
        "exit_trade": generate_trade_data("BTCUSDT", "SELL", quantity, exit_price, (exit_price - entry_price) * quantity),
        "candles": generate_bullish_candles(entry_price, 20, 10),
        "expected_profit": (exit_price - entry_price) * quantity
    }


def create_losing_trade_scenario():
    """Create mock data for a losing trading scenario."""
    entry_price = 100.0
    exit_price = 95.0
    quantity = 0.1

    return {
        "entry_trade": generate_trade_data("BTCUSDT", "BUY", quantity, entry_price, 0),
        "exit_trade": generate_trade_data("BTCUSDT", "SELL", quantity, exit_price, (exit_price - entry_price) * quantity),
        "candles": generate_bearish_candles(entry_price, 20, 5),
        "expected_loss": abs((exit_price - entry_price) * quantity)
    }
