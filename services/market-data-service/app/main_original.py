"""
Market Data Service - FastAPI Application
Purpose: Collect, store, and serve market data with production-ready features
"""

from fastapi import FastAPI, HTTPException, Query, Request, Depends
import sys
import uuid
from pathlib import Path

# Add shared utilities to path

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from contextlib import asynccontextmanager
from typing import Optional, List
from pydantic import BaseModel, Field, validator
from enum import Enum
import logging
import re
import time
import traceback

# Structured logging
# python-json-logger>=3 moved JsonFormatter into pythonjsonlogger.json;
# importing the legacy `jsonlogger` module emits a DeprecationWarning on
# 4.x. Try the new path first, fall back for python-json-logger<3.
try:
    from pythonjsonlogger import json as jsonlogger  # type: ignore[import]
except ImportError:  # pragma: no cover - only on python-json-logger<3
    from pythonjsonlogger import jsonlogger  # type: ignore[no-redef]

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

from app.config import get_settings
from app.database import init_database, close_database
from app.fetcher import create_fetcher
from app.repository import KlineRepository, TickerRepository
from app.auth import verify_api_key
from app.cache import cache_get, cache_set, close_redis
from app.scheduler import start_scheduler, stop_scheduler, get_scheduler_status, run_manual_collection


# ============================================================================
# STRUCTURED LOGGING WITH SECRET MASKING
# ============================================================================

class SecretMaskingFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter that masks sensitive data in logs"""

    SECRET_PATTERNS = [
        (re.compile(r'(api_key["\s:=]+)([^\s,}"]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(api_secret["\s:=]+)([^\s,}"]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(password["\s:=]+)([^\s,}"]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(token["\s:=]+)([^\s,}"]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(bearer\s+)([^\s,}"]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(authorization["\s:=]+)([^\s,}"]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'([?&]key=)([^&\s]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'([?&]secret=)([^&\s]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(postgres://[^:]+:)([^@]+)(@)', re.IGNORECASE), r'\1***MASKED***\3'),
        (re.compile(r'(redis://[^:]*:)([^@]+)(@)', re.IGNORECASE), r'\1***MASKED***\3'),
    ]

    def format(self, record):
        # Get the formatted message
        message = super().format(record)

        # Apply all masking patterns
        for pattern, replacement in self.SECRET_PATTERNS:
            message = pattern.sub(replacement, message)

        return message


def setup_logging():
    """Configure structured JSON logging"""
    log_handler = logging.StreamHandler()
    formatter = SecretMaskingFormatter(
        '%(timestamp)s %(level)s %(name)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    log_handler.setFormatter(formatter)

    logging.root.addHandler(log_handler)
    logging.root.setLevel(logging.INFO)

    # Suppress noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


setup_logging()
logger = logging.getLogger(__name__)


# ============================================================================
# PROMETHEUS METRICS
# ============================================================================

# HTTP request metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0]
)

http_requests_active = Gauge(
    'http_requests_active',
    'Number of active HTTP requests'
)

# Data collection metrics
data_collection_total = Counter(
    'data_collection_total',
    'Total data collection operations',
    ['symbol', 'data_type', 'status']
)

data_records_stored = Counter(
    'data_records_stored_total',
    'Total records stored in database',
    ['symbol', 'data_type']
)

# External service metrics
bybit_connector_calls_total = Counter(
    'bybit_connector_calls_total',
    'Total calls to Bybit Connector',
    ['endpoint', 'status']
)

database_operations_total = Counter(
    'database_operations_total',
    'Total database operations',
    ['operation', 'status']
)


# Prometheus middleware
from starlette.middleware.base import BaseHTTPMiddleware

class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip metrics endpoint
        if request.url.path == "/metrics":
            return await call_next(request)

        # Track active requests
        http_requests_active.inc()

        # Record start time
        start_time = time.time()

        try:
            # Process request
            response = await call_next(request)

            # Record metrics
            duration = time.time() - start_time
            http_request_duration_seconds.labels(
                method=request.method,
                endpoint=request.url.path
            ).observe(duration)

            http_requests_total.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code=response.status_code
            ).inc()

            return response

        finally:
            # Decrement active requests
            http_requests_active.dec()


# ============================================================================
# RATE LIMITING
# ============================================================================

limiter = Limiter(key_func=get_remote_address)


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class IntervalEnum(str, Enum):
    """Allowed candlestick intervals"""
    ONE_MIN = "1"
    FIVE_MIN = "5"
    FIFTEEN_MIN = "15"
    THIRTY_MIN = "30"
    ONE_HOUR = "60"
    FOUR_HOUR = "240"
    ONE_DAY = "D"


class CollectKlineRequest(BaseModel):
    """Request model for kline data collection"""
    symbol: str = Field(..., min_length=6, max_length=20)
    interval: IntervalEnum = Field(default=IntervalEnum.ONE_HOUR)
    days: int = Field(default=7, ge=1, le=30)

    @validator('symbol')
    def validate_symbol(cls, v):
        v = v.upper()
        if not re.match(r'^[A-Z]{6,20}$', v):
            raise ValueError("Symbol must be 6-20 uppercase letters")
        return v


class BulkCollectRequest(BaseModel):
    """Request model for bulk data collection"""
    symbols: Optional[List[str]] = Field(None, max_items=10)
    interval: IntervalEnum = Field(default=IntervalEnum.ONE_HOUR)
    days: int = Field(default=7, ge=1, le=30)


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
    await shutdown_handler.shutdown()

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
    version="1.0.0",
    lifespan=lifespan
)

# Add middlewares
app.add_middleware(PrometheusMiddleware)

# CORS middleware with security
settings_instance = get_settings()
# CORS configuration fixed

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


# Dependency for fetcher
def get_fetcher(request: Request):
    return request.app.state.fetcher


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
async def health_check(request: Request):
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "market-data-service",
        "timestamp": int(time.time() * 1000)
    }


@app.get("/ready", tags=["Health"])
@limiter.limit("60/minute")
async def readiness_check(request: Request, fetcher=Depends(get_fetcher)):
    """Readiness check"""
    is_ready = await fetcher.health_check() if fetcher else False

    if is_ready:
        return {
            "status": "ready",
            "service": "market-data-service",
            "bybit_connector": "ok"
        }
    else:
        raise HTTPException(status_code=503, detail="Bybit Connector not reachable")


@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ============================================================================
# DATA COLLECTION ENDPOINTS
# ============================================================================

@app.post("/api/v1/collect/kline/{symbol}", tags=["Data Collection"])
@limiter.limit("20/minute")
async def collect_kline_data(
    request: Request,
    symbol: str,
    interval: str = "60",
    days: int = Query(default=7, ge=1, le=30),
    fetcher=Depends(get_fetcher),
    api_key: str = Depends(verify_api_key)
):
    """
    Fetch and store historical kline data

    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        interval: Candlestick interval
        days: Number of days to fetch (max 30)
    """
    try:
        # Validate symbol
        symbol = symbol.upper()
        if not re.match(r'^[A-Z]{6,20}$', symbol):
            raise HTTPException(status_code=400, detail="Invalid symbol format")

        logger.info(f"Collecting {days} days of {symbol} klines ({interval})")

        # Track metric
        bybit_connector_calls_total.labels(endpoint='kline', status='attempt').inc()

        # Fetch data from Bybit Connector
        klines = await fetcher.get_historical_klines(
            symbol=symbol,
            interval=interval,
            days=days
        )

        if not klines:
            data_collection_total.labels(symbol=symbol, data_type='kline', status='no_data').inc()
            return {"success": False, "message": "No data fetched", "count": 0}

        bybit_connector_calls_total.labels(endpoint='kline', status='success').inc()

        # Add symbol and interval to each kline
        for k in klines:
            k['symbol'] = symbol
            k['interval'] = interval

        # Store in database
        database_operations_total.labels(operation='bulk_upsert', status='attempt').inc()
        count = await KlineRepository.bulk_upsert(klines)
        database_operations_total.labels(operation='bulk_upsert', status='success').inc()

        # Track metrics
        data_collection_total.labels(symbol=symbol, data_type='kline', status='success').inc()
        data_records_stored.labels(symbol=symbol, data_type='kline').inc(count)

        return {
            "success": True,
            "message": f"Collected and stored {count} klines",
            "symbol": symbol,
            "interval": interval,
            "count": count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error collecting kline data for {symbol}: {e}")
        data_collection_total.labels(symbol=symbol, data_type='kline', status='error').inc()
        bybit_connector_calls_total.labels(endpoint='kline', status='error').inc()
        raise HTTPException(status_code=500, detail="Failed to collect data")


@app.post("/api/v1/collect/ticker/{symbol}", tags=["Data Collection"])
@limiter.limit("30/minute")
async def collect_ticker_data(
    request: Request,
    symbol: str,
    fetcher=Depends(get_fetcher),
    api_key: str = Depends(verify_api_key)
):
    """
    Fetch and store current ticker data

    Args:
        symbol: Trading pair
    """
    try:
        # Validate symbol
        symbol = symbol.upper()
        if not re.match(r'^[A-Z]{6,20}$', symbol):
            raise HTTPException(status_code=400, detail="Invalid symbol format")

        # Fetch ticker
        ticker = await fetcher.get_ticker(symbol)

        if not ticker:
            data_collection_total.labels(symbol=symbol, data_type='ticker', status='no_data').inc()
            return {"success": False, "message": "No ticker data available"}

        # Store in database
        await TickerRepository.save_ticker(ticker)

        # Track metrics
        data_collection_total.labels(symbol=symbol, data_type='ticker', status='success').inc()
        data_records_stored.labels(symbol=symbol, data_type='ticker').inc()

        return {
            "success": True,
            "message": "Ticker data saved",
            "data": ticker
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error collecting ticker for {symbol}: {e}")
        data_collection_total.labels(symbol=symbol, data_type='ticker', status='error').inc()
        raise HTTPException(status_code=500, detail="Failed to collect ticker")


# ============================================================================
# DATA QUERY ENDPOINTS
# ============================================================================

@app.get("/api/v1/klines/{symbol}", tags=["Market Data"])
@limiter.limit("60/minute")
async def get_klines(
    request: Request,
    symbol: str,
    interval: str = "60",
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int = Query(default=100, ge=1, le=10000)
):
    """
    Get kline data from database

    Args:
        symbol: Trading pair
        interval: Candlestick interval
        start_time: Start timestamp (ms)
        end_time: End timestamp (ms)
        limit: Maximum records
    """
    try:
        # Validate inputs
        symbol = symbol.upper()
        if not re.match(r'^[A-Z]{6,20}$', symbol):
            raise HTTPException(status_code=400, detail="Invalid symbol format")

        klines = await KlineRepository.get_klines(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )

        # Convert to dict
        data = [k.to_dict() for k in klines]

        return {
            "success": True,
            "count": len(data),
            "data": data
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving klines for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve data")


@app.get("/api/v1/ticker/{symbol}", tags=["Market Data"])
@limiter.limit("60/minute")
async def get_ticker(
    request: Request,
    symbol: str,
    fetcher=Depends(get_fetcher)
):
    """
    Get latest ticker data (with Redis caching)

    Args:
        symbol: Trading pair
    """
    try:
        # Validate symbol
        symbol = symbol.upper()
        if not re.match(r'^[A-Z]{6,20}$', symbol):
            raise HTTPException(status_code=400, detail="Invalid symbol format")

        # Try cache first
        cache_key = f"ticker:{symbol}"
        cached_data = await cache_get(cache_key)
        if cached_data:
            logger.debug(f"Cache hit for ticker {symbol}")
            return {
                "success": True,
                "data": cached_data,
                "source": "cache"
            }

        # Cache miss - try database
        ticker = await TickerRepository.get_latest_ticker(symbol)

        if not ticker:
            # Database miss - fetch fresh from Bybit Connector
            ticker_data = await fetcher.get_ticker(symbol)
            if ticker_data:
                await TickerRepository.save_ticker(ticker_data)
                # Cache for 5 seconds
                await cache_set(cache_key, ticker_data, ttl=5)
                return {
                    "success": True,
                    "data": ticker_data,
                    "source": "live"
                }
            else:
                raise HTTPException(status_code=404, detail="Ticker not found")

        # Cache the database result for 5 seconds
        ticker_dict = ticker.to_dict()
        await cache_set(cache_key, ticker_dict, ttl=5)

        return {
            "success": True,
            "data": ticker_dict,
            "source": "database"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving ticker for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve ticker")


@app.get("/api/v1/latest/{symbol}", tags=["Market Data"])
@limiter.limit("60/minute")
async def get_latest_kline(
    request: Request,
    symbol: str,
    interval: str = "60"
):
    """
    Get most recent kline for symbol (with Redis caching)

    Args:
        symbol: Trading pair
        interval: Candlestick interval
    """
    try:
        # Validate symbol
        symbol = symbol.upper()
        if not re.match(r'^[A-Z]{6,20}$', symbol):
            raise HTTPException(status_code=400, detail="Invalid symbol format")

        # Try cache first
        cache_key = f"latest_kline:{symbol}:{interval}"
        cached_data = await cache_get(cache_key)
        if cached_data:
            logger.debug(f"Cache hit for latest kline {symbol} ({interval})")
            return {
                "success": True,
                "data": cached_data,
                "source": "cache"
            }

        # Cache miss - fetch from database
        kline = await KlineRepository.get_latest_kline(symbol, interval)

        if not kline:
            raise HTTPException(status_code=404, detail="No kline data found")

        # Cache for 60 seconds (klines change less frequently than tickers)
        kline_dict = kline.to_dict()
        await cache_set(cache_key, kline_dict, ttl=60)

        return {
            "success": True,
            "data": kline_dict,
            "source": "database"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving latest kline for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve data")


# ============================================================================
# BULK OPERATIONS
# ============================================================================

@app.post("/api/v1/collect/bulk", tags=["Data Collection"])
@limiter.limit("5/minute")  # Strict limit for bulk operations
async def collect_bulk_data(
    request: Request,
    symbols: Optional[List[str]] = None,
    interval: str = "60",
    days: int = Query(default=7, ge=1, le=30),
    fetcher=Depends(get_fetcher),
    api_key: str = Depends(verify_api_key)
):
    """
    Collect data for multiple symbols (max 10)

    Args:
        symbols: List of trading pairs (defaults to config symbols, max 10)
        interval: Candlestick interval
        days: Number of days to fetch (max 30)
    """
    settings = get_settings()
    target_symbols = symbols or settings.symbols_list

    # Enforce maximum symbols limit
    MAX_SYMBOLS = 10
    if len(target_symbols) > MAX_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_SYMBOLS} symbols allowed per request"
        )

    results = []

    for symbol in target_symbols:
        try:
            symbol = symbol.upper()

            # Fetch klines
            klines = await fetcher.get_historical_klines(
                symbol=symbol,
                interval=interval,
                days=days
            )

            if klines:
                # Add metadata
                for k in klines:
                    k['symbol'] = symbol
                    k['interval'] = interval

                # Store
                count = await KlineRepository.bulk_upsert(klines)
                results.append({
                    "symbol": symbol,
                    "success": True,
                    "count": count
                })

                # Track metrics
                data_collection_total.labels(symbol=symbol, data_type='kline', status='success').inc()
                data_records_stored.labels(symbol=symbol, data_type='kline').inc(count)
            else:
                results.append({
                    "symbol": symbol,
                    "success": False,
                    "error": "No data fetched"
                })

        except Exception as e:
            logger.error(f"Error collecting data for {symbol}: {e}")
            results.append({
                "symbol": symbol,
                "success": False,
                "error": str(e)
            })

    return {
        "success": True,
        "results": results,
        "total_symbols": len(target_symbols),
        "successful": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"])
    }


# ============================================================================
# SCHEDULER CONTROL ENDPOINTS
# ============================================================================

@app.get("/api/v1/scheduler/status", tags=["Scheduler"])
@limiter.limit("30/minute")
async def scheduler_status(request: Request):
    """
    Get scheduler status and job information

    Returns:
        dict: Scheduler status including running jobs and next run times
    """
    try:
        status = get_scheduler_status()
        return {
            "success": True,
            "scheduler": status
        }
    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get scheduler status")


@app.post("/api/v1/scheduler/start", tags=["Scheduler"])
@limiter.limit("10/minute")
async def start_scheduler_endpoint(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """
    Manually start the scheduler

    Requires API key authentication.
    """
    try:
        start_scheduler()
        logger.info("Scheduler started via API")
        return {
            "success": True,
            "message": "Scheduler started successfully"
        }
    except Exception as e:
        logger.error(f"Error starting scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/scheduler/stop", tags=["Scheduler"])
@limiter.limit("10/minute")
async def stop_scheduler_endpoint(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """
    Manually stop the scheduler

    Requires API key authentication.
    """
    try:
        stop_scheduler()
        logger.info("Scheduler stopped via API")
        return {
            "success": True,
            "message": "Scheduler stopped successfully"
        }
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/scheduler/collect", tags=["Scheduler"])
@limiter.limit("5/minute")
async def trigger_manual_collection(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """
    Manually trigger a full data collection cycle

    Collects both ticker and kline data for all configured symbols.
    Requires API key authentication.
    """
    try:
        logger.info("Manual data collection triggered via API")
        await run_manual_collection()
        return {
            "success": True,
            "message": "Manual data collection completed"
        }
    except Exception as e:
        logger.error(f"Error during manual collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
