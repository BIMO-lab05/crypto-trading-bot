"""
Trading Engine Service - FastAPI Application
Purpose: Core trading decision-making and execution service
"""

import logging
import time
from contextlib import asynccontextmanager
from decimal import Decimal
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.signal_aggregator import get_aggregator, close_aggregator
from app.position_manager import get_position_manager
from app.risk_manager import get_risk_manager
from app.paper_trading import get_paper_engine
from app.phase1_metrics import get_phase1_metrics
from app.multi_timeframe import get_multi_timeframe_analyzer, close_multi_timeframe_analyzer
from app.models import (
    HealthResponse,
    StatusResponse,
    SignalResponse,
    PositionListResponse,
    PositionResponse,
    PerformanceResponse,
    TradingControlResponse,
    OrderCreate,
    OrderSide,
    OrderType,
    PositionSide
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Settings
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    logger.info(f"Starting {settings.service_name} on port {settings.service_port}")
    logger.info(f"Trading Mode: {settings.trading_mode}")
    logger.info(f"Auto Trading: {settings.auto_trading_enabled}")

    # Check Technical Analysis Service connection
    aggregator = await get_aggregator()
    is_healthy = await aggregator.health_check()
    if is_healthy:
        logger.info("✅ Technical Analysis Service connection verified")
    else:
        logger.warning("⚠️ Technical Analysis Service not available")

    yield

    # Cleanup
    logger.info("Shutting down Trading Engine Service")
    await close_aggregator()
    await close_multi_timeframe_analyzer()


# FastAPI app
app = FastAPI(
    title="Trading Engine Service",
    description="Core trading decision-making and execution service",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health endpoints
@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint"""
    aggregator = await get_aggregator()
    ta_healthy = await aggregator.health_check()

    return HealthResponse(
        status="healthy",
        service=settings.service_name,
        technical_analysis_connection=ta_healthy,
        bybit_connector_connection=False,  # TODO: Implement when Bybit integration is ready
        database_connection=False,  # TODO: Implement when DB is added
        timestamp=int(time.time() * 1000)
    )


@app.get("/status", response_model=StatusResponse, tags=["Status"])
async def get_status():
    """Get trading engine status"""
    position_manager = get_position_manager()
    paper_engine = get_paper_engine()

    open_positions = position_manager.get_open_positions()

    return StatusResponse(
        status="running",
        trading_mode=settings.trading_mode,
        auto_trading_enabled=settings.auto_trading_enabled,
        active_strategy=settings.default_strategy,
        open_positions_count=len(open_positions),
        current_balance=float(paper_engine.get_balance()),
        timestamp=int(time.time() * 1000)
    )


# Signal endpoints
@app.get("/api/v1/signals/{symbol}", response_model=SignalResponse, tags=["Signals"])
async def get_trading_signal(
    symbol: str,
    interval: str = "60"
):
    """
    Get trading signal for a symbol

    Fetches all technical indicators and aggregates them into a trading signal.
    """
    try:
        aggregator = await get_aggregator()
        signal = await aggregator.get_trading_signal(symbol, interval)

        return SignalResponse(
            success=True,
            signal=signal,
            timestamp=int(time.time() * 1000)
        )

    except Exception as e:
        logger.error(f"Error getting trading signal for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/signals/{symbol}/analyze", response_model=SignalResponse, tags=["Signals"])
async def analyze_and_trade(
    symbol: str,
    interval: str = "60",
    execute: bool = False
):
    """
    Analyze signal and optionally execute trade

    Args:
        symbol: Trading symbol
        interval: Candlestick interval
        execute: If True, will execute trade based on signal
    """
    try:
        # Get trading signal
        aggregator = await get_aggregator()
        signal = await aggregator.get_trading_signal(symbol, interval)

        # Validate signal with risk manager
        risk_manager = get_risk_manager()
        is_valid, reason = risk_manager.validate_signal(signal.action, signal.confidence)

        if not is_valid:
            return SignalResponse(
                success=False,
                signal=signal,
                message=f"Signal validation failed: {reason}",
                timestamp=int(time.time() * 1000)
            )

        # Execute trade if requested
        if execute and settings.trading_mode == "PAPER":
            message = await execute_signal_trade(signal)
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


async def execute_signal_trade(signal) -> str:
    """Execute trade based on signal (paper trading)"""
    from app.models import SignalAction

    if signal.action not in [SignalAction.BUY, SignalAction.SELL]:
        return f"No trade executed: signal is {signal.action.value}"

    paper_engine = get_paper_engine()
    risk_manager = get_risk_manager()

    # Get current price from signal
    current_price = Decimal(str(signal.indicators.get("EMA", signal.indicators.get("SMA")).metadata.get("current_price", 0)))

    if signal.action == SignalAction.BUY:
        # Calculate position size
        quantity = risk_manager.calculate_position_size(
            paper_engine.get_total_equity(),
            current_price
        )

        # Check if we can open position
        can_open, reason = paper_engine.can_open_position(signal.symbol, quantity, current_price)
        if not can_open:
            return f"Cannot open position: {reason}"

        # Execute buy order
        order = OrderCreate(
            symbol=signal.symbol,
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=quantity,
            strategy=signal.strategy
        )

        executed_order, error = await paper_engine.execute_market_order(order, current_price)
        if error:
            return f"Order failed: {error}"

        return f"BUY order executed: {quantity} {signal.symbol} @ {current_price}"

    elif signal.action == SignalAction.SELL:
        # Find open position to close
        position_manager = get_position_manager()
        open_positions = [
            pos for pos in position_manager.get_open_positions()
            if pos.symbol == signal.symbol
        ]

        if not open_positions:
            return f"No open position for {signal.symbol} to close"

        # Close first position
        position = open_positions[0]
        order = OrderCreate(
            symbol=signal.symbol,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            quantity=position.quantity,
            position_id=position.id,
            strategy=signal.strategy
        )

        executed_order, error = await paper_engine.execute_market_order(order, current_price)
        if error:
            return f"Order failed: {error}"

        return f"SELL order executed: {position.quantity} {signal.symbol} @ {current_price}"


# Position endpoints
@app.get("/api/v1/positions", response_model=PositionListResponse, tags=["Positions"])
async def get_positions(status: str = "all"):
    """
    Get positions

    Args:
        status: Filter by status (all, open, closed)
    """
    try:
        position_manager = get_position_manager()

        if status == "open":
            positions = position_manager.get_open_positions()
        elif status == "closed":
            positions = position_manager.get_closed_positions()
        else:
            positions = position_manager.get_all_positions()

        return PositionListResponse(
            success=True,
            positions=positions,
            count=len(positions),
            timestamp=int(time.time() * 1000)
        )

    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/positions/{position_id}", response_model=PositionResponse, tags=["Positions"])
async def get_position(position_id: str):
    """Get specific position by ID"""
    try:
        from uuid import UUID
        position_manager = get_position_manager()
        position = position_manager.get_position(UUID(position_id))

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        return PositionResponse(
            success=True,
            position=position,
            timestamp=int(time.time() * 1000)
        )

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid position ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting position {position_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Performance endpoints
@app.get("/api/v1/performance", response_model=PerformanceResponse, tags=["Performance"])
async def get_performance():
    """Get performance metrics"""
    try:
        paper_engine = get_paper_engine()
        summary = paper_engine.get_performance_summary()

        from app.models import PerformanceMetrics
        metrics = PerformanceMetrics(
            total_trades=summary["total_trades"],
            winning_trades=summary["winning_trades"],
            losing_trades=summary["losing_trades"],
            total_pnl=Decimal(str(summary["total_pnl"])),
            win_rate=summary["win_rate"],
            current_balance=Decimal(str(summary["current_balance"])),
            initial_balance=Decimal(str(summary["initial_balance"])),
            roi=summary["roi"]
        )
        metrics.calculate_metrics()

        return PerformanceResponse(
            success=True,
            metrics=metrics,
            timestamp=int(time.time() * 1000)
        )

    except Exception as e:
        logger.error(f"Error getting performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Trading control endpoints
@app.post("/api/v1/trading/start", response_model=TradingControlResponse, tags=["Trading Control"])
async def start_trading():
    """Start automated trading"""
    try:
        # TODO: Implement automated trading loop
        return TradingControlResponse(
            success=False,
            message="Automated trading not yet implemented",
            trading_enabled=False,
            timestamp=int(time.time() * 1000)
        )
    except Exception as e:
        logger.error(f"Error starting trading: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/trading/stop", response_model=TradingControlResponse, tags=["Trading Control"])
async def stop_trading():
    """Stop automated trading"""
    try:
        # TODO: Implement automated trading loop
        return TradingControlResponse(
            success=True,
            message="Trading stopped",
            trading_enabled=False,
            timestamp=int(time.time() * 1000)
        )
    except Exception as e:
        logger.error(f"Error stopping trading: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Phase 1 Metrics endpoints
@app.get("/api/v1/phase1/metrics", tags=["Phase 1"])
async def get_phase1_metrics_endpoint(hours: int = 24):
    """
    Get Phase 1 performance metrics

    Args:
        hours: Number of hours to analyze (default: 24)

    Returns:
        Phase 1 metrics including filtering rates, GATEKEEPER/VALIDATOR stats
    """
    try:
        provider = get_phase1_metrics()
        metrics = provider.get_metrics(hours=hours)

        return {
            "success": True,
            "data": metrics,
            "timestamp": int(time.time() * 1000)
        }
    except Exception as e:
        logger.error(f"Error getting Phase 1 metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/phase1/health", tags=["Phase 1"])
async def get_phase1_health():
    """Get Phase 1 system health status"""
    try:
        provider = get_phase1_metrics()
        health = provider.get_system_health()

        return {
            "success": True,
            "data": health,
            "timestamp": int(time.time() * 1000)
        }
    except Exception as e:
        logger.error(f"Error getting Phase 1 health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/phase1/latest", tags=["Phase 1"])
async def get_latest_phase1_signal():
    """Get the most recent Phase 1 signal"""
    try:
        provider = get_phase1_metrics()
        signal = provider.get_latest_signal()

        if not signal:
            return {
                "success": True,
                "data": None,
                "message": "No recent signals",
                "timestamp": int(time.time() * 1000)
            }

        return {
            "success": True,
            "data": signal,
            "timestamp": int(time.time() * 1000)
        }
    except Exception as e:
        logger.error(f"Error getting latest Phase 1 signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Root endpoint
@app.get("/", tags=["Info"])
async def root():
    """Root endpoint with service information"""
    return {
        "service": settings.service_name,
        "version": "1.0.0",
        "status": "running",
        "trading_mode": settings.trading_mode,
        "endpoints": {
            "health": "/health",
            "status": "/status",
            "docs": "/docs",
            "signals": "/api/v1/signals/{symbol}",
            "positions": "/api/v1/positions",
            "performance": "/api/v1/performance"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.service_host,
        port=settings.service_port,
        reload=settings.debug
    )
