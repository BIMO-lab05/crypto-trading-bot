"""
API Gateway - Main Application
Unified entry point for all microservices
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import time
from typing import Optional

from app.config import settings
from app.services.service_proxy import ServiceProxy

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global service proxy
service_proxy: Optional[ServiceProxy] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management"""
    global service_proxy

    # Startup
    logger.info(f"🚀 Starting {settings.service_name} on port {settings.service_port}")

    service_proxy = ServiceProxy()
    await service_proxy.initialize()

    logger.info("✅ API Gateway ready")

    yield

    # Shutdown
    logger.info("🛑 Shutting down API Gateway")
    if service_proxy:
        await service_proxy.cleanup()


# Create FastAPI app
app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_proxy() -> ServiceProxy:
    """Get service proxy instance"""
    if service_proxy is None:
        raise HTTPException(status_code=503, detail="Service proxy not initialized")
    return service_proxy


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "service": settings.service_name,
        "version": settings.api_version,
        "description": settings.api_description,
        "services": {
            "bybit_connector": settings.bybit_connector_url,
            "market_data": settings.market_data_url,
            "technical_analysis": settings.technical_analysis_url,
            "trading_engine": settings.trading_engine_url,
            "portfolio_manager": settings.portfolio_manager_url,
            "risk_metrics": settings.risk_metrics_url
        },
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "market_data": "/api/market/*",
            "technical_analysis": "/api/analysis/*",
            "trading": "/api/trading/*",
            "portfolio": "/api/portfolio/*",
            "risk": "/api/risk/*",
            "performance": "/api/performance/*"
        }
    }


# Health endpoint
@app.get("/health")
async def health_check():
    """Gateway health check with backend service status"""
    proxy = get_proxy()

    # Check all backend services
    health_checks = await proxy.aggregate_health_checks()

    all_healthy = all(health_checks.values())

    return {
        "status": "healthy" if all_healthy else "degraded",
        "service": settings.service_name,
        "version": settings.api_version,
        "timestamp": int(time.time() * 1000),
        "backend_services": {
            "bybit_connector": health_checks.get("bybit", False),
            "market_data": health_checks.get("market-data", False),
            "technical_analysis": health_checks.get("technical-analysis", False),
            "trading_engine": health_checks.get("trading-engine", False),
            "portfolio_manager": health_checks.get("portfolio-manager", False)
        }
    }


# ============================================================================
# MARKET DATA ROUTES
# ============================================================================

@app.get("/api/market/ticker/{symbol}")
async def get_ticker(symbol: str, request: Request):
    """Get ticker data for a symbol"""
    proxy = get_proxy()
    response_obj = await proxy.proxy_request(
        service_name="market-data",
        path=f"/api/v1/ticker/{symbol}",
        method="GET"
    )

    # Extract the actual data from JSONResponse
    import json
    response_body = response_obj.body.decode() if hasattr(response_obj, 'body') else response_obj
    response = json.loads(response_body) if isinstance(response_body, str) else response_body

    # Transform response format for frontend compatibility
    # API returns: {success: true, data: {...}}
    # Frontend expects: {ticker: {...}}
    if isinstance(response, dict) and response.get("success") and response.get("data"):
        ticker_data = response["data"]
        # Map field names to frontend expectations
        return {
            "ticker": {
                "symbol": ticker_data.get("symbol"),
                "last_price": str(ticker_data.get("last_price", 0)),
                "price_24h_pcnt": str(ticker_data.get("price_change_24h", 0)),
                "volume_24h": str(ticker_data.get("volume_24h", 0)),
                "high_price_24h": str(ticker_data.get("high_24h", 0)),
                "low_price_24h": str(ticker_data.get("low_24h", 0))
            }
        }

    return response


@app.get("/api/market/kline/{symbol}")
async def get_kline(symbol: str, interval: str = "60", limit: int = 100):
    """Get kline/candlestick data"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="market-data",
        path=f"/api/v1/kline/{symbol}",
        method="GET",
        query_params={"interval": interval, "limit": limit}
    )


# ============================================================================
# TECHNICAL ANALYSIS ROUTES
# ============================================================================

@app.get("/api/analysis/rsi/{symbol}")
async def get_rsi(symbol: str, interval: str = "60", period: int = 14):
    """Get RSI indicator"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="technical-analysis",
        path=f"/api/v1/indicators/rsi/{symbol}",
        method="GET",
        query_params={"interval": interval, "period": period}
    )


@app.get("/api/analysis/macd/{symbol}")
async def get_macd(symbol: str, interval: str = "60"):
    """Get MACD indicator"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="technical-analysis",
        path=f"/api/v1/indicators/macd/{symbol}",
        method="GET",
        query_params={"interval": interval}
    )


@app.get("/api/analysis/all/{symbol}")
async def get_all_indicators(symbol: str, interval: str = "60"):
    """Get all technical indicators"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="technical-analysis",
        path=f"/api/v1/analysis/{symbol}",
        method="GET",
        query_params={"interval": interval}
    )


# ============================================================================
# TRADING ENGINE ROUTES
# ============================================================================

@app.get("/api/trading/signals/{symbol}")
async def get_trading_signal(symbol: str, interval: str = "60"):
    """Get aggregated trading signal"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine",
        path=f"/api/v1/signals/{symbol}",
        method="GET",
        query_params={"interval": interval}
    )


@app.post("/api/trading/signals/{symbol}/analyze")
async def analyze_and_trade(symbol: str, interval: str = "60", execute: bool = False):
    """Analyze signal and optionally execute trade"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine",
        path=f"/api/v1/signals/{symbol}/analyze",
        method="POST",
        query_params={"interval": interval, "execute": execute}
    )


@app.get("/api/trading/positions")
async def get_positions(status: str = "open"):
    """Get trading positions"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine",
        path="/api/v1/positions",
        method="GET",
        query_params={"status": status}
    )


# ============================================================================
# PORTFOLIO MANAGER ROUTES
# ============================================================================

@app.get("/api/portfolio")
async def get_portfolio(portfolio_id: str = "default"):
    """Get portfolio details"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/portfolio",
        method="GET",
        query_params={"portfolio_id": portfolio_id}
    )


@app.get("/api/portfolio/balance")
async def get_balance(portfolio_id: str = "default"):
    """Get portfolio balance"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/portfolio/balance",
        method="GET",
        query_params={"portfolio_id": portfolio_id}
    )


@app.get("/api/portfolio/holdings")
async def get_holdings(portfolio_id: str = "default"):
    """Get portfolio holdings"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/portfolio/holdings",
        method="GET",
        query_params={"portfolio_id": portfolio_id}
    )


@app.get("/api/portfolio/performance")
async def get_performance(portfolio_id: str = "default"):
    """Get performance metrics"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/performance",
        method="GET",
        query_params={"portfolio_id": portfolio_id}
    )


@app.post("/api/portfolio/buy")
async def buy_asset(
    portfolio_id: str = "default",
    symbol: str = None,
    quantity: str = None,
    price: str = None
):
    """Execute buy transaction"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/transaction/buy",
        method="POST",
        query_params={
            "portfolio_id": portfolio_id,
            "symbol": symbol,
            "quantity": quantity,
            "price": price
        }
    )


@app.post("/api/portfolio/sell")
async def sell_asset(
    portfolio_id: str = "default",
    symbol: str = None,
    quantity: str = None,
    price: str = None
):
    """Execute sell transaction"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/transaction/sell",
        method="POST",
        query_params={
            "portfolio_id": portfolio_id,
            "symbol": symbol,
            "quantity": quantity,
            "price": price
        }
    )


@app.post("/api/portfolio/emergency-stop")
async def emergency_stop():
    """
    Emergency stop - Halt all trading operations immediately
    This is a critical safety feature that stops the trading bot
    """
    try:
        # Create emergency stop file flag
        import os
        stop_file = "/mnt/d/Bimo_max/crypto-trading-bot/EMERGENCY_STOP"
        with open(stop_file, 'w') as f:
            f.write(f"Emergency stop activated at {int(time.time() * 1000)}\n")

        logger.warning("🚨 EMERGENCY STOP ACTIVATED")

        return JSONResponse(content={
            "success": True,
            "message": "Emergency stop activated. Trading bot will halt operations.",
            "timestamp": int(time.time() * 1000)
        })
    except Exception as e:
        logger.error(f"Failed to activate emergency stop: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to activate emergency stop: {str(e)}")


# ============================================================================
# RISK & METRICS ENDPOINTS
# ============================================================================

@app.get("/api/risk/scorecard")
async def get_risk_scorecard():
    """Get complete risk assessment scorecard"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/risk/scorecard",
        method="GET"
    )


@app.get("/api/risk/capital")
async def get_capital_metrics():
    """Get capital allocation metrics"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/risk/capital",
        method="GET"
    )


@app.get("/api/risk/exposure")
async def get_exposure_metrics():
    """Get portfolio exposure analysis"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/risk/exposure",
        method="GET"
    )


@app.get("/api/risk/drawdown")
async def get_drawdown_metrics():
    """Get drawdown tracking metrics"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/risk/drawdown",
        method="GET"
    )


@app.get("/api/risk/var")
async def get_value_at_risk(confidence_level: float = 0.95, time_horizon_days: int = 1):
    """Get Value at Risk calculation"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/risk/var",
        method="GET",
        query_params={
            "confidence_level": confidence_level,
            "time_horizon_days": time_horizon_days
        }
    )


@app.get("/api/performance/metrics")
async def get_performance_metrics():
    """Get comprehensive performance metrics"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/performance/metrics",
        method="GET"
    )


@app.get("/api/performance/sharpe")
async def get_sharpe_ratio():
    """Get Sharpe ratio calculation"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/performance/sharpe",
        method="GET"
    )


@app.get("/api/risk/alerts")
async def get_active_alerts():
    """Get active risk alerts"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/alerts",
        method="GET"
    )


@app.get("/api/risk/circuit-breaker")
async def get_circuit_breaker_status():
    """Get circuit breaker status"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/circuit-breaker",
        method="GET"
    )


@app.post("/api/risk/circuit-breaker/reset")
async def reset_circuit_breaker():
    """Reset circuit breaker (admin only)"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/circuit-breaker/reset",
        method="POST"
    )


# ============================================================================
# AGGREGATION ENDPOINTS (Combine Multiple Services)
# ============================================================================

@app.get("/api/dashboard/{symbol}")
async def get_dashboard_data(symbol: str, interval: str = "60"):
    """
    Aggregated dashboard endpoint
    Combines data from multiple services for a complete view
    """
    proxy = get_proxy()

    try:
        # Fetch data from multiple services in parallel
        import asyncio

        ticker_task = proxy.proxy_request("market-data", f"/api/v1/ticker/{symbol}", "GET")
        signal_task = proxy.proxy_request("trading-engine", f"/api/v1/signals/{symbol}", "GET", {"interval": interval})
        portfolio_task = proxy.proxy_request("portfolio-manager", "/api/v1/portfolio", "GET")

        ticker, signal, portfolio = await asyncio.gather(
            ticker_task, signal_task, portfolio_task,
            return_exceptions=True
        )

        return JSONResponse(content={
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "data": {
                "market": ticker.body.decode() if not isinstance(ticker, Exception) else None,
                "signal": signal.body.decode() if not isinstance(signal, Exception) else None,
                "portfolio": portfolio.body.decode() if not isinstance(portfolio, Exception) else None
            },
            "timestamp": int(time.time() * 1000)
        })

    except Exception as e:
        logger.error(f"Error fetching dashboard data: {e}")
        raise HTTPException(status_code=500, detail="Error fetching dashboard data")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.service_port)
