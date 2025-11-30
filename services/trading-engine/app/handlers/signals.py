"""
Signal Endpoint Handlers
Extracted from main.py - Responsibility: Signal fetching and trading execution

Handles trading signal retrieval and analysis with optional execution.

UPDATED: Signal recording now handled by CoreAggregator with real filter data
"""

import logging
import time
from fastapi import HTTPException

from app.config import get_settings
from app.signal_aggregator import get_aggregator
from app.risk_manager import get_risk_manager
from app.models import SignalResponse
from app.services import TradingService

logger = logging.getLogger(__name__)
settings = get_settings()


async def get_trading_signal(
    symbol: str,
    interval: str = "60"
) -> SignalResponse:
    """
    Get trading signal for a symbol

    Fetches all technical indicators and aggregates them into a trading signal.
    Signal is automatically recorded by CoreAggregator with real filter data.

    Args:
        symbol: Trading symbol (e.g., BTCUSDT)
        interval: Candlestick interval in minutes (default: 60)

    Returns:
        SignalResponse with aggregated signal and confidence

    Raises:
        HTTPException: If signal fetching fails
    """
    try:
        aggregator = await get_aggregator()
        # CoreAggregator now records signal to Phase1MetricsProvider with real filter data
        signal = await aggregator.get_trading_signal(symbol, interval)

        return SignalResponse(
            success=True,
            signal=signal,
            timestamp=int(time.time() * 1000)
        )

    except Exception as e:
        logger.error(f"Error getting trading signal for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def analyze_and_trade(
    symbol: str,
    interval: str = "60",
    execute: bool = False
) -> SignalResponse:
    """
    Analyze signal and optionally execute trade

    Process:
    1. Fetch trading signal from aggregator
    2. Validate signal with risk manager
    3. Execute trade if requested and validated

    Args:
        symbol: Trading symbol (e.g., BTCUSDT)
        interval: Candlestick interval in minutes (default: 60)
        execute: If True, will execute trade based on signal

    Returns:
        SignalResponse with signal analysis and execution result

    Raises:
        HTTPException: If analysis or execution fails
    """
    try:
        # Fetch trading signal
        aggregator = await get_aggregator()
        signal = await aggregator.get_trading_signal(symbol, interval)

        # Validate signal with risk manager
        risk_manager = get_risk_manager()
        is_valid, reason = risk_manager.validate_signal(
            signal.action, signal.confidence
        )

        if not is_valid:
            return SignalResponse(
                success=False,
                signal=signal,
                message=f"Signal validation failed: {reason}",
                timestamp=int(time.time() * 1000)
            )

        # Execute trade if requested (paper trading only)
        if execute and settings.trading_mode == "PAPER":
            message = await TradingService.execute_signal_trade(signal)
            return SignalResponse(
                success=True,
                signal=signal,
                message=message,
                timestamp=int(time.time() * 1000)
            )

        return SignalResponse(
            success=True,
            signal=signal,
            message="Signal analyzed (not executed)",
            timestamp=int(time.time() * 1000)
        )

    except Exception as e:
        logger.error(f"Error analyzing signal for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
