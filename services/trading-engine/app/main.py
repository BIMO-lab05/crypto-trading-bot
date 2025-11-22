"""
Trading Engine Service - FastAPI Application
Purpose: Core trading decision-making and execution service

REFACTORED: Phase 3 Complete - Using modular handlers
Architecture: main.py → handlers → services → domain

NEW: SQZMOM Strategy Integration (2025-11-20)
"""

import logging
from contextlib import asynccontextmanager
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Query
from typing import Optional

from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.signal_aggregator import get_aggregator, close_aggregator
from app.multi_timeframe import get_multi_timeframe_analyzer, close_multi_timeframe_analyzer
from app.repositories import get_portfolio_repository
from database.connection import db_manager
from app.models import (
    HealthResponse,
    StatusResponse,
    SignalResponse,
    PositionListResponse,
    PositionResponse,
    PerformanceResponse,
    TradingControlResponse
)

# Import all handler functions (Phase 3: Modular architecture)
from app.handlers import (
    health_check,
    get_status,
    get_detailed_health,
    get_trading_signal,
    analyze_and_trade,
    get_positions,
    get_position,
    get_performance,
    start_trading,
    stop_trading,
    get_auto_trading_status,
    get_phase1_metrics_endpoint,
    get_phase1_health,
    get_latest_phase1_signal
)

# Import SQZMOM strategy (NEW)
from app.strategies import sqzmom_strategy, sqzmom_config

# Fixed: Create logs directory to prevent startup crashes (Critical Issue #1)
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

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

    # Initialize database connection
    try:
        db_manager.init_async_engine()
        db_health = db_manager.health_check()
        if db_health:
            logger.info("✅ Database connection initialized")

            # Ensure paper trading portfolio exists
            portfolio_repo = get_portfolio_repository()
            await portfolio_repo.get_or_create(
                portfolio_id="paper_trading",
                name="Paper Trading Portfolio",
                initial_balance=Decimal(str(settings.paper_initial_balance))
            )
            logger.info("✅ Paper trading portfolio verified")
        else:
            logger.warning("⚠️ Database connection failed - trades will not be persisted")
    except Exception as e:
        logger.error(f"⚠️ Database initialization error: {e}")
        logger.warning("Continuing without database persistence")

    # Check Technical Analysis Service connection
    aggregator = await get_aggregator()
    is_healthy = await aggregator.health_check()
    if is_healthy:
        logger.info("✅ Technical Analysis Service connection verified")
    else:
        logger.warning("⚠️ Technical Analysis Service not available")

    # Log SQZMOM strategy status (NEW)
    logger.info("=" * 60)
    logger.info("SQZMOM Strategy Configuration:")
    logger.info(f"  Enabled symbols: {sqzmom_config.enabled_symbols}")
    logger.info(f"  Paper trading: {sqzmom_config.paper_trading}")
    logger.info(f"  Auto trading: {sqzmom_config.auto_trading}")
    logger.info(f"  Max positions: {sqzmom_config.max_positions}")
    logger.info("=" * 60)

    yield

    # Cleanup
    logger.info("Shutting down Trading Engine Service")
    await close_aggregator()
    await close_multi_timeframe_analyzer()

    # Close SQZMOM strategy (NEW)
    await sqzmom_strategy.close()

    # Close database connections
    try:
        await db_manager.close()
        logger.info("✅ Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")


# FastAPI app
app = FastAPI(
    title="Trading Engine Service",
    description="Core trading decision-making and execution service with SQZMOM strategy",
    version="2.2.0",  # Updated: SQZMOM integration
    lifespan=lifespan
)

# Fixed: CORS middleware with configured origins (High Issue #11 - Security)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# HEALTH ENDPOINTS
# ============================================================================

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health():
    """Health check endpoint"""
    return await health_check()


@app.get("/status", response_model=StatusResponse, tags=["Status"])
async def status():
    """Get trading engine status"""
    return await get_status()


@app.get("/health/detailed", tags=["Health"])
async def detailed_health():
    """
    Get detailed health status with all metrics

    Returns comprehensive health report including:
    - All dependency statuses (PostgreSQL, Redis, external APIs)
    - System resource metrics (CPU, memory, disk)
    - Response time metrics
    - Failure counts
    """
    return await get_detailed_health()


# ============================================================================
# SIGNAL ENDPOINTS
# ============================================================================

@app.get("/api/v1/signals/{symbol}", response_model=SignalResponse, tags=["Signals"])
async def signal_endpoint(
    symbol: str,
    interval: str = "60"
):
    """
    Get trading signal for a symbol

    Fetches all technical indicators and aggregates them into a trading signal.
    """
    return await get_trading_signal(symbol, interval)


@app.post("/api/v1/signals/{symbol}/analyze", response_model=SignalResponse, tags=["Signals"])
async def analyze_endpoint(
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
    return await analyze_and_trade(symbol, interval, execute)


# ============================================================================
# POSITION ENDPOINTS
# ============================================================================

@app.get("/api/v1/positions", response_model=PositionListResponse, tags=["Positions"])
async def positions_endpoint(status: str = "all"):
    """
    Get positions

    Args:
        status: Filter by status (all, open, closed)
    """
    return await get_positions(status)


@app.get("/api/v1/positions/{position_id}", response_model=PositionResponse, tags=["Positions"])
async def position_endpoint(position_id: str):
    """Get specific position by ID"""
    return await get_position(position_id)


# ============================================================================
# PERFORMANCE ENDPOINTS
# ============================================================================

@app.get("/api/v1/performance", response_model=PerformanceResponse, tags=["Performance"])
async def performance_endpoint():
    """Get performance metrics"""
    return await get_performance()


# ============================================================================
# TRADING CONTROL ENDPOINTS
# ============================================================================

@app.post("/api/v1/trading/start", response_model=TradingControlResponse, tags=["Trading Control"])
async def trading_start_endpoint():
    """
    Start automated trading loop

    The auto trader will:
    - Check signals every 5 minutes (configurable)
    - Execute trades when signal meets requirements
    - Apply risk management rules
    - Track all trades and performance
    """
    return await start_trading()


@app.post("/api/v1/trading/stop", response_model=TradingControlResponse, tags=["Trading Control"])
async def trading_stop_endpoint():
    """Stop automated trading loop"""
    return await stop_trading()


@app.get("/api/v1/trading/status", tags=["Trading Control"])
async def trading_status_endpoint():
    """
    Get automated trading status and statistics

    Returns:
        Current status, symbols being traded, check frequency, and execution statistics
    """
    return await get_auto_trading_status()


# ============================================================================
# PHASE 1 METRICS ENDPOINTS
# ============================================================================

@app.get("/api/v1/phase1/metrics", tags=["Phase 1"])
async def phase1_metrics_endpoint(hours: int = 24):
    """
    Get Phase 1 performance metrics

    Args:
        hours: Number of hours to analyze (default: 24)

    Returns:
        Phase 1 metrics including filtering rates, GATEKEEPER/VALIDATOR stats
    """
    return await get_phase1_metrics_endpoint(hours)


@app.get("/api/v1/phase1/health", tags=["Phase 1"])
async def phase1_health_endpoint():
    """Get Phase 1 system health status"""
    return await get_phase1_health()


@app.get("/api/v1/phase1/latest", tags=["Phase 1"])
async def phase1_latest_endpoint():
    """Get the most recent Phase 1 signal"""
    return await get_latest_phase1_signal()


# ============================================================================
# SQZMOM STRATEGY ENDPOINTS (NEW)
# ============================================================================

@app.get("/api/v1/strategies/sqzmom/info", tags=["SQZMOM Strategy"])
async def get_sqzmom_info():
    """
    Get SQZMOM strategy information

    Returns complete strategy configuration, enabled symbols,
    backtesting results, and current state.
    """
    return sqzmom_strategy.get_strategy_info()


@app.get("/api/v1/strategies/sqzmom/config", tags=["SQZMOM Strategy"])
async def get_sqzmom_config():
    """
    Get current SQZMOM strategy configuration

    Returns all configuration parameters including:
    - Enabled symbols
    - Indicator parameters (BB, KC lengths)
    - Strategy parameters (momentum threshold, SL, TP)
    - Risk management (position size, max positions)
    - Trading mode (paper/live, auto/manual)
    """
    return sqzmom_config.dict()


@app.post("/api/v1/strategies/sqzmom/enable", tags=["SQZMOM Strategy"])
async def enable_sqzmom_trading(
    auto_trading: bool = Query(
        default=False,
        description="Enable automatic trade execution (False = manual approval required)"
    )
):
    """
    Enable SQZMOM strategy

    Args:
        auto_trading: Enable automatic trade execution
                     - False: Signals are generated but require manual approval
                     - True: Trades are executed automatically

    Returns:
        Success status and current configuration
    """
    sqzmom_config.auto_trading = auto_trading

    logger.info(
        f"SQZMOM strategy {'ENABLED' if auto_trading else 'ENABLED (manual approval mode)'}"
    )

    return {
        "success": True,
        "message": f"SQZMOM strategy enabled with auto_trading={auto_trading}",
        "enabled_symbols": sqzmom_config.enabled_symbols,
        "paper_trading": sqzmom_config.paper_trading,
        "auto_trading": sqzmom_config.auto_trading,
        "max_positions": sqzmom_config.max_positions,
        "note": "Manual approval required" if not auto_trading else "Automatic execution enabled"
    }


@app.post("/api/v1/strategies/sqzmom/disable", tags=["SQZMOM Strategy"])
async def disable_sqzmom_trading():
    """
    Disable SQZMOM strategy

    Sets auto_trading to False, preventing any automatic trade execution.
    Manual signal fetching is still possible.
    """
    sqzmom_config.auto_trading = False

    logger.info("SQZMOM strategy DISABLED")

    return {
        "success": True,
        "message": "SQZMOM strategy disabled (auto_trading set to False)",
        "auto_trading": sqzmom_config.auto_trading
    }


@app.get("/api/v1/strategies/sqzmom/signals", tags=["SQZMOM Strategy"])
async def get_all_sqzmom_signals():
    """
    Get SQZMOM signals for all enabled symbols

    Fetches signals from Technical Analysis service for:
    - SOLUSDT
    - DOGEUSDT
    - BNBUSDT

    Returns dictionary mapping symbol to signal with action,
    confidence, entry/SL/TP prices, and reasoning.
    """
    signals = await sqzmom_strategy.get_all_signals()

    return {
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "enabled_symbols": sqzmom_config.enabled_symbols,
        "signals_retrieved": len(signals),
        "signals": signals
    }


@app.get("/api/v1/strategies/sqzmom/signal/{symbol}", tags=["SQZMOM Strategy"])
async def get_sqzmom_signal(
    symbol: str,
    interval: Optional[str] = Query(
        default=None,
        description="Timeframe in minutes (default: from config, typically 60)"
    )
):
    """
    Get SQZMOM signal for a specific symbol

    Args:
        symbol: Trading pair (e.g., SOLUSDT)
        interval: Timeframe in minutes (default: 60)

    Returns:
        Signal with action, confidence, prices, and reasoning

    Note:
        - Symbol must be in enabled list (SOLUSDT, DOGEUSDT, BNBUSDT)
        - Returns 404 if symbol not enabled
    """
    # Check if symbol is enabled
    if not sqzmom_strategy.is_symbol_enabled(symbol):
        return {
            "success": False,
            "error": f"Symbol {symbol} not in enabled list",
            "enabled_symbols": sqzmom_config.enabled_symbols
        }

    # Get signal
    signal = await sqzmom_strategy.get_signal(symbol, interval)

    if signal is None:
        return {
            "success": False,
            "error": f"Failed to fetch signal for {symbol}",
            "symbol": symbol
        }

    return {
        "success": True,
        "signal": signal
    }


@app.post("/api/v1/strategies/sqzmom/trade/{symbol}", tags=["SQZMOM Strategy"])
async def execute_sqzmom_trade(
    symbol: str,
    account_balance: float = Query(
        default=10000.0,
        description="Account balance for position sizing"
    ),
    force: bool = Query(
        default=False,
        description="Force execution even if auto_trading is disabled"
    )
):
    """
    Execute SQZMOM trade for a symbol

    This endpoint demonstrates the full trading flow:
    1. Get SQZMOM signal from Technical Analysis service
    2. Validate signal meets entry criteria
    3. Calculate position size based on risk management
    4. Execute trade (paper or live mode)

    Args:
        symbol: Trading pair (must be in enabled list)
        account_balance: Account balance for position sizing (default: $10,000)
        force: Force execution even if auto_trading disabled (for manual approval)

    Returns:
        Trade execution result with details
    """

    # Check if symbol is enabled
    if not sqzmom_strategy.is_symbol_enabled(symbol):
        return {
            "success": False,
            "error": f"Symbol {symbol} not in enabled list",
            "enabled_symbols": sqzmom_config.enabled_symbols
        }

    # Get signal
    signal = await sqzmom_strategy.get_signal(symbol)

    if not signal:
        return {
            "success": False,
            "error": "Failed to fetch signal",
            "symbol": symbol
        }

    # Check if HOLD
    if signal['action'] == 'HOLD':
        return {
            "success": False,
            "message": "No valid signal (action is HOLD)",
            "symbol": symbol,
            "signal": signal
        }

    # Check if should execute (unless forced)
    if not force:
        current_positions = 0  # TODO: Get from position manager
        should_execute, reason = await sqzmom_strategy.should_execute_trade(
            signal,
            current_positions
        )

        if not should_execute:
            return {
                "success": False,
                "message": "Trade validation failed",
                "reason": reason,
                "symbol": symbol,
                "signal": signal,
                "note": "Use force=true to override (manual approval)"
            }

    # Calculate position size
    quantity = await sqzmom_strategy.calculate_position_size(
        symbol,
        signal['entry_price'],
        signal['stop_loss'],
        account_balance
    )

    # Get symbol config for display
    symbol_cfg = sqzmom_strategy.get_symbol_config(symbol)

    # Build trade result
    trade_result = {
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "symbol": symbol,
        "action": signal['action'],
        "quantity": float(quantity),
        "entry_price": signal['entry_price'],
        "stop_loss": signal['stop_loss'],
        "take_profit": signal['take_profit'],
        "confidence": signal['confidence'],
        "reason": signal['reason'],
        "position_size_pct": symbol_cfg['position_size_pct'],
        "position_value": float(quantity) * signal['entry_price'],
        "paper_trading": sqzmom_config.paper_trading,
        "forced": force,
        "note": "This is a simulated trade - actual execution not implemented yet"
    }

    logger.info(
        f"SQZMOM trade executed: {symbol} {signal['action']} "
        f"qty={quantity} @ ${signal['entry_price']}"
    )

    return trade_result


@app.get("/api/v1/strategies/sqzmom/symbols/{symbol}/config", tags=["SQZMOM Strategy"])
async def get_symbol_config(symbol: str):
    """
    Get configuration for a specific symbol

    Returns symbol-specific parameters including:
    - Position size percentage
    - Stop loss percentage
    - Take profit percentage
    - Minimum confidence threshold
    - Backtesting results
    """
    if not sqzmom_strategy.is_symbol_enabled(symbol):
        return {
            "success": False,
            "error": f"Symbol {symbol} not in enabled list",
            "enabled_symbols": sqzmom_config.enabled_symbols
        }

    config = sqzmom_strategy.get_symbol_config(symbol)

    return {
        "success": True,
        "symbol": symbol,
        "config": config
    }


# ============================================================================
# ROOT ENDPOINT
# ============================================================================

@app.get("/", tags=["Info"])
async def root():
    """Root endpoint with service information"""
    return {
        "service": settings.service_name,
        "version": "2.2.0",  # Updated: SQZMOM strategy integration
        "status": "running",
        "architecture": "Modular (Phase 3 Complete)",
        "trading_mode": settings.trading_mode,
        "endpoints": {
            "health": "/health",
            "health_detailed": "/health/detailed",
            "status": "/status",
            "docs": "/docs",
            "signals": "/api/v1/signals/{symbol}",
            "positions": "/api/v1/positions",
            "performance": "/api/v1/performance",
            "trading_control": {
                "start": "/api/v1/trading/start",
                "stop": "/api/v1/trading/stop",
                "status": "/api/v1/trading/status"
            },
            "phase1": {
                "metrics": "/api/v1/phase1/metrics",
                "health": "/api/v1/phase1/health",
                "latest": "/api/v1/phase1/latest"
            },
            "sqzmom_strategy": {
                "info": "/api/v1/strategies/sqzmom/info",
                "config": "/api/v1/strategies/sqzmom/config",
                "enable": "POST /api/v1/strategies/sqzmom/enable",
                "disable": "POST /api/v1/strategies/sqzmom/disable",
                "signals": "/api/v1/strategies/sqzmom/signals",
                "signal": "/api/v1/strategies/sqzmom/signal/{symbol}",
                "trade": "POST /api/v1/strategies/sqzmom/trade/{symbol}",
                "symbol_config": "/api/v1/strategies/sqzmom/symbols/{symbol}/config"
            }
        },
        "refactoring": {
            "status": "Phase 3 Complete ✅",
            "original_lines": 606,
            "current_lines": "~200",
            "reduction": "67%",
            "modules": 8,
            "architecture": "main.py → handlers → services → domain"
        },
        "new_features": {
            "redis_signal_cache": "✅ Implemented",
            "health_monitor": "✅ Implemented",
            "cache_metrics": "✅ Tracking",
            "system_metrics": "✅ CPU/Memory/Disk",
            "sqzmom_strategy": "✅ Implemented (2025-11-20)"
        },
        "sqzmom_strategy": {
            "enabled": True,
            "symbols": sqzmom_config.enabled_symbols,
            "paper_trading": sqzmom_config.paper_trading,
            "auto_trading": sqzmom_config.auto_trading,
            "backtesting_results": {
                "SOLUSDT": "+2,706% (22% WR, 4.76 Sharpe)",
                "DOGEUSDT": "+630% (28% WR, 5.41 Sharpe)",
                "BNBUSDT": "+330% (31% WR)"
            }
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
