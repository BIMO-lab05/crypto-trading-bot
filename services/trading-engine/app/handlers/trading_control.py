"""
Trading Control Endpoint Handlers
Extracted from main.py - Responsibility: Automated trading lifecycle management

Handles starting, stopping, and monitoring automated trading.
"""

import logging
import time
from fastapi import HTTPException

from app.auto_trader import get_auto_trader
from app.models import TradingControlResponse

logger = logging.getLogger(__name__)


async def start_trading() -> TradingControlResponse:
    """
    Start automated trading loop

    The auto trader will:
    - Check signals every 5 minutes (configurable)
    - Execute trades when signal meets requirements
    - Apply risk management rules
    - Track all trades and performance

    Returns:
        TradingControlResponse with success status

    Raises:
        HTTPException: If auto trader fails to start
    """
    try:
        auto_trader = get_auto_trader()
        success = await auto_trader.start()

        if success:
            logger.info("✅ Automated trading started successfully")
            return TradingControlResponse(
                success=True,
                message="Automated trading started successfully",
                trading_enabled=True,
                timestamp=int(time.time() * 1000)
            )
        else:
            return TradingControlResponse(
                success=False,
                message="Automated trading is already running",
                trading_enabled=True,
                timestamp=int(time.time() * 1000)
            )

    except Exception as e:
        logger.error(f"Error starting trading: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def stop_trading() -> TradingControlResponse:
    """
    Stop automated trading loop

    Gracefully stops the automated trading system.
    Open positions are not automatically closed.

    Returns:
        TradingControlResponse with success status

    Raises:
        HTTPException: If auto trader fails to stop
    """
    try:
        auto_trader = get_auto_trader()
        success = await auto_trader.stop()

        if success:
            logger.info("✅ Automated trading stopped successfully")
            return TradingControlResponse(
                success=True,
                message="Automated trading stopped successfully",
                trading_enabled=False,
                timestamp=int(time.time() * 1000)
            )
        else:
            return TradingControlResponse(
                success=False,
                message="Automated trading was not running",
                trading_enabled=False,
                timestamp=int(time.time() * 1000)
            )

    except Exception as e:
        logger.error(f"Error stopping trading: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_auto_trading_status():
    """
    Get automated trading status and statistics

    Returns:
    - Current status (running/stopped)
    - Symbols being traded
    - Check frequency
    - Execution statistics

    Returns:
        Dict with auto trading status and stats

    Raises:
        HTTPException: If status retrieval fails
    """
    try:
        auto_trader = get_auto_trader()
        status = auto_trader.get_status()

        return {
            "success": True,
            "status": status,
            "timestamp": int(time.time() * 1000)
        }

    except Exception as e:
        logger.error(f"Error getting auto trading status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
