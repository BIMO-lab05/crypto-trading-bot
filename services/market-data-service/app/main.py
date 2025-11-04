"""
Market Data Service - FastAPI Application
Purpose: Collect, store, and serve market data
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Optional, List
import logging

from app.config import get_settings
from app.database import init_database, close_database
from app.fetcher import create_fetcher
from app.repository import KlineRepository, TickerRepository

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global instances
fetcher = None


# ============================================================================
# LIFESPAN MANAGEMENT
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Startup
    global fetcher
    settings = get_settings()
    
    logger.info(f"Starting Market Data Service")

    # Initialize database
    await init_database()
    logger.info("Database initialized")

    # Initialize data fetcher
    fetcher = create_fetcher()
    logger.info("Data fetcher initialized")
    
    # Check Bybit Connector health
    is_healthy = await fetcher.health_check()
    if is_healthy:
        logger.info("✅ Bybit Connector service is healthy")
    else:
        logger.warning("⚠️ Bybit Connector service is not reachable")
    
    yield
    
    # Shutdown
    if fetcher:
        await fetcher.close()
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

# CORS middleware
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

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "market-data-service"}


@app.get("/ready", tags=["Health"])
async def readiness_check():
    """Readiness check"""
    # Check if fetcher can reach Bybit Connector
    is_ready = await fetcher.health_check() if fetcher else False
    
    if is_ready:
        return {"status": "ready", "bybit_connector": "ok"}
    else:
        raise HTTPException(status_code=503, detail="Bybit Connector not reachable")


# ============================================================================
# DATA COLLECTION ENDPOINTS
# ============================================================================

@app.post("/api/v1/collect/kline/{symbol}", tags=["Data Collection"])
async def collect_kline_data(
    symbol: str,
    interval: str = "60",
    days: int = Query(default=7, ge=1, le=90)
):
    """
    Fetch and store historical kline data
    
    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        interval: Candlestick interval
        days: Number of days to fetch
    """
    try:
        logger.info(f"Collecting {days} days of {symbol} klines ({interval})")
        
        # Fetch data from Bybit Connector
        klines = await fetcher.get_historical_klines(
            symbol=symbol,
            interval=interval,
            days=days
        )
        
        if not klines:
            return {"success": False, "message": "No data fetched", "count": 0}
        
        # Add symbol and interval to each kline
        for k in klines:
            k['symbol'] = symbol
            k['interval'] = interval
        
        # Store in database
        count = await KlineRepository.bulk_upsert(klines)
        
        return {
            "success": True,
            "message": f"Collected and stored {count} klines",
            "symbol": symbol,
            "interval": interval,
            "count": count
        }
        
    except Exception as e:
        logger.error(f"Error collecting kline data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/collect/ticker/{symbol}", tags=["Data Collection"])
async def collect_ticker_data(symbol: str):
    """
    Fetch and store current ticker data
    
    Args:
        symbol: Trading pair
    """
    try:
        # Fetch ticker
        ticker = await fetcher.get_ticker(symbol)
        
        if not ticker:
            return {"success": False, "message": "No ticker data available"}
        
        # Store in database
        await TickerRepository.save_ticker(ticker)
        
        return {
            "success": True,
            "message": "Ticker data saved",
            "data": ticker
        }
        
    except Exception as e:
        logger.error(f"Error collecting ticker: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DATA QUERY ENDPOINTS
# ============================================================================

@app.get("/api/v1/klines/{symbol}", tags=["Market Data"])
async def get_klines(
    symbol: str,
    interval: str = "60",
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int = Query(default=100, ge=1, le=1000)
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
        
    except Exception as e:
        logger.error(f"Error retrieving klines: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/ticker/{symbol}", tags=["Market Data"])
async def get_ticker(symbol: str):
    """
    Get latest ticker data
    
    Args:
        symbol: Trading pair
    """
    try:
        ticker = await TickerRepository.get_latest_ticker(symbol)
        
        if not ticker:
            # Try fetching fresh from Bybit Connector
            ticker_data = await fetcher.get_ticker(symbol)
            if ticker_data:
                await TickerRepository.save_ticker(ticker_data)
                return {
                    "success": True,
                    "data": ticker_data,
                    "source": "live"
                }
            else:
                raise HTTPException(status_code=404, detail="Ticker not found")
        
        return {
            "success": True,
            "data": ticker.to_dict(),
            "source": "database"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving ticker: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/latest/{symbol}", tags=["Market Data"])
async def get_latest_kline(
    symbol: str,
    interval: str = "60"
):
    """
    Get most recent kline for symbol
    
    Args:
        symbol: Trading pair
        interval: Candlestick interval
    """
    try:
        kline = await KlineRepository.get_latest_kline(symbol, interval)
        
        if not kline:
            raise HTTPException(status_code=404, detail="No kline data found")
        
        return {
            "success": True,
            "data": kline.to_dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving latest kline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BULK OPERATIONS
# ============================================================================

@app.post("/api/v1/collect/bulk", tags=["Data Collection"])
async def collect_bulk_data(
    symbols: Optional[List[str]] = None,
    interval: str = "60",
    days: int = 7
):
    """
    Collect data for multiple symbols

    Args:
        symbols: List of trading pairs (defaults to config symbols)
        interval: Candlestick interval
        days: Number of days to fetch
    """
    settings = get_settings()
    target_symbols = symbols or settings.symbols_list

    results = []

    for symbol in target_symbols:
        try:
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
        "total_symbols": len(target_symbols)
    }


@app.post("/api/v1/collect/tickers/bulk", tags=["Data Collection"])
async def collect_bulk_tickers(
    symbols: Optional[List[str]] = None
):
    """
    Collect current ticker data for multiple symbols

    Args:
        symbols: List of trading pairs (defaults to config symbols)
    """
    settings = get_settings()
    target_symbols = symbols or settings.symbols_list

    results = []

    for symbol in target_symbols:
        try:
            # Fetch ticker
            ticker = await fetcher.get_ticker(symbol)

            if ticker:
                # Store in database
                await TickerRepository.save_ticker(ticker)
                results.append({
                    "symbol": symbol,
                    "success": True,
                    "data": ticker
                })
            else:
                results.append({
                    "symbol": symbol,
                    "success": False,
                    "error": "No ticker data available"
                })

        except Exception as e:
            logger.error(f"Error collecting ticker for {symbol}: {e}")
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
