"""
Market Data Service - Main Application
Purpose: Collect, store, and serve market data with production-ready features

REFACTORED: Phase 2 Complete - Using modular handlers and utilities
Architecture: main.py → handlers → repository/services → database/external APIs
"""

from fastapi import FastAPI, HTTPException, Query, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from typing import Optional, List
import logging
import traceback

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Import utilities (extracted)
from app.utils import (
    setup_logging,
    PrometheusMiddleware
)

# Import core modules
from app.config import get_settings
from app.database import init_database, close_database
from app.fetcher import create_fetcher
from app.cache import close_redis
from app.scheduler import start_scheduler, stop_scheduler

# Import all handler functions (Phase 2: Modular architecture)
from app.handlers import (
    # Health
    health_check,
    readiness_check,
    metrics_endpoint,
    # Collection
    collect_kline_data,
    collect_ticker_data,
    collect_bulk_data,
    # Query
    get_klines,
    get_ticker,
    get_latest_kline,
    # Scheduler
    get_scheduler_status_handler,
    start_scheduler_handler,
    stop_scheduler_handler,
    trigger_manual_collection_handler
)

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


# ============================================================================
# RATE LIMITING
# ============================================================================

limiter = Limiter(key_func=get_remote_address)


# ============================================================================
# LIFESPAN MANAGEMENT
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    settings = get_settings()

    logger.info(f"Starting Market Data Service")

    # Initialize database
    await init_database()
    logger.info("Database initialized")

    # Initialize data fetcher
    app.state.fetcher = create_fetcher()
    logger.info("Data fetcher initialized")

    # Check Bybit Connector health
    is_healthy = await app.state.fetcher.health_check()
    if is_healthy:
        logger.info("✅ Bybit Connector service is healthy")
    else:
        logger.warning("⚠️ Bybit Connector service is not reachable")

    # Start automated data collection scheduler
    try:
        start_scheduler()
        logger.info("✅ Automated data collection scheduler started")
    except Exception as e:
        logger.error(f"⚠️ Failed to start scheduler: {e}")

    yield

    # Graceful shutdown
    logger.info("Initiating graceful shutdown", service=settings.service_name)

    # Stop scheduler
    try:
        stop_scheduler()
        logger.info("✅ Scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")

    # Close connections
    if hasattr(app.state, 'fetcher'):
        await app.state.fetcher.close()
    await close_redis()
    await close_database()
    logger.info("Market Data Service stopped")


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="Market Data Service",
    description="Microservice for collecting and serving cryptocurrency market data",
    version="2.0.0",  # Updated: Phase 2 refactoring
    lifespan=lifespan
)

# Add middlewares
app.add_middleware(PrometheusMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
    max_age=3600,
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ============================================================================
# EXCEPTION HANDLERS
# ============================================================================

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions"""
    logger.error(
        "Unhandled exception",
        extra={
            "path": request.url.path,
            "method": request.method,
            "error": str(exc),
            "traceback": traceback.format_exc()
        }
    )

    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "path": request.url.path}
    )


# ============================================================================
# HEALTH ENDPOINTS
# ============================================================================

@app.get("/health", tags=["Health"])
@limiter.limit("60/minute")
async def health(request: Request):
    """Health check endpoint"""
    return await health_check()


@app.get("/ready", tags=["Health"])
@limiter.limit("60/minute")
async def ready(request: Request):
    """Readiness check"""
    fetcher = request.app.state.fetcher
    return await readiness_check(fetcher)


@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint"""
    return await metrics_endpoint()


# ============================================================================
# DATA COLLECTION ENDPOINTS
# ============================================================================

@app.post("/api/v1/collect/kline/{symbol}", tags=["Data Collection"])
@limiter.limit("20/minute")
async def collect_kline_endpoint(
    request: Request,
    symbol: str,
    interval: str = "60",
    days: int = Query(default=7, ge=1, le=30),
    fetcher=Depends(lambda r: r.app.state.fetcher),
    api_key: str = Depends(lambda r: None)  # Will use verify_api_key in handler
):
    """Fetch and store historical kline data"""
    return await collect_kline_data(symbol, interval, days, fetcher, api_key)


@app.post("/api/v1/collect/ticker/{symbol}", tags=["Data Collection"])
@limiter.limit("30/minute")
async def collect_ticker_endpoint(
    request: Request,
    symbol: str,
    fetcher=Depends(lambda r: r.app.state.fetcher),
    api_key: str = Depends(lambda r: None)
):
    """Fetch and store current ticker data"""
    return await collect_ticker_data(symbol, fetcher, api_key)


@app.post("/api/v1/collect/bulk", tags=["Data Collection"])
@limiter.limit("5/minute")
async def collect_bulk_endpoint(
    request: Request,
    symbols: Optional[List[str]] = None,
    interval: str = "60",
    days: int = Query(default=7, ge=1, le=30),
    fetcher=Depends(lambda r: r.app.state.fetcher),
    api_key: str = Depends(lambda r: None)
):
    """Collect data for multiple symbols (max 10)"""
    return await collect_bulk_data(symbols, interval, days, fetcher, api_key)


# ============================================================================
# DATA QUERY ENDPOINTS
# ============================================================================

@app.get("/api/v1/klines/{symbol}", tags=["Market Data"])
@limiter.limit("60/minute")
async def klines_endpoint(
    request: Request,
    symbol: str,
    interval: str = "60",
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int = Query(default=100, ge=1, le=10000)
):
    """Get kline data from database"""
    return await get_klines(symbol, interval, start_time, end_time, limit)


@app.get("/api/v1/ticker/{symbol}", tags=["Market Data"])
@limiter.limit("60/minute")
async def ticker_endpoint(
    request: Request,
    symbol: str
):
    """Get latest ticker data (with Redis caching)"""
    fetcher = request.app.state.fetcher
    return await get_ticker(symbol, fetcher)


@app.get("/api/v1/latest/{symbol}", tags=["Market Data"])
@limiter.limit("60/minute")
async def latest_endpoint(
    request: Request,
    symbol: str,
    interval: str = "60"
):
    """Get most recent kline for symbol (with Redis caching)"""
    return await get_latest_kline(symbol, interval)


# ============================================================================
# SCHEDULER CONTROL ENDPOINTS
# ============================================================================

@app.get("/api/v1/scheduler/status", tags=["Scheduler"])
@limiter.limit("30/minute")
async def scheduler_status_endpoint(request: Request):
    """Get scheduler status and job information"""
    return await get_scheduler_status_handler()


@app.post("/api/v1/scheduler/start", tags=["Scheduler"])
@limiter.limit("10/minute")
async def start_scheduler_endpoint(
    request: Request,
    api_key: str = Depends(lambda r: None)
):
    """Manually start the scheduler"""
    return await start_scheduler_handler(api_key)


@app.post("/api/v1/scheduler/stop", tags=["Scheduler"])
@limiter.limit("10/minute")
async def stop_scheduler_endpoint(
    request: Request,
    api_key: str = Depends(lambda r: None)
):
    """Manually stop the scheduler"""
    return await stop_scheduler_handler(api_key)


@app.post("/api/v1/scheduler/collect", tags=["Scheduler"])
@limiter.limit("5/minute")
async def trigger_collection_endpoint(
    request: Request,
    api_key: str = Depends(lambda r: None)
):
    """Manually trigger a full data collection cycle"""
    return await trigger_manual_collection_handler(api_key)


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()

    uvicorn.run(
        "main:app",
        host=settings.service_host,
        port=settings.service_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
