"""
Bybit Connector Service - FastAPI Application
Purpose: REST API service for interfacing with Bybit exchange
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging
from contextlib import asynccontextmanager

from app.config import get_settings, Settings
from app.bybit_rest_client import BybitRestClient, create_rest_client
from app.exceptions import BybitConnectorException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global client instance
rest_client: Optional[BybitRestClient] = None


# ============================================================================
# LIFESPAN MANAGEMENT
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle (startup/shutdown)"""
    # Startup
    global rest_client
    settings = get_settings()
    
    logger.info(f"Starting Bybit Connector Service (testnet={settings.bybit_testnet})")
    rest_client = create_rest_client(settings)
    logger.info("Bybit REST client initialized")
    
    yield
    
    # Shutdown
    if rest_client:
        await rest_client.close()
    logger.info("Bybit Connector Service stopped")


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="Bybit Connector Service",
    description="Microservice for interfacing with Bybit exchange API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class PlaceOrderRequest(BaseModel):
    """Request model for placing an order"""
    category: str = Field(default="linear", description="Product category")
    symbol: str = Field(..., description="Trading pair (e.g., BTCUSDT)")
    side: str = Field(..., description="Buy or Sell")
    order_type: str = Field(..., description="Market or Limit")
    qty: str = Field(..., description="Order quantity")
    price: Optional[str] = Field(None, description="Order price (required for Limit)")
    time_in_force: str = Field(default="GTC", description="Time in force")
    reduce_only: bool = Field(default=False)
    order_link_id: Optional[str] = None


class CancelOrderRequest(BaseModel):
    """Request model for cancelling an order"""
    category: str = Field(default="linear")
    symbol: str = Field(...)
    order_id: Optional[str] = None
    order_link_id: Optional[str] = None


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

def get_rest_client() -> BybitRestClient:
    """Dependency to get REST client"""
    if rest_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bybit client not initialized"
        )
    return rest_client


# ============================================================================
# HEALTH ENDPOINTS
# ============================================================================

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "bybit-connector"}


@app.get("/ready", tags=["Health"])
async def readiness_check(client: BybitRestClient = Depends(get_rest_client)):
    """Readiness check - verifies service can connect to Bybit"""
    try:
        # Try to get ticker data (public endpoint, no auth needed)
        await client.get_ticker(category="linear", symbol="BTCUSDT")
        return {"status": "ready", "bybit_connection": "ok"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Bybit connection failed: {str(e)}"
        )


# ============================================================================
# ACCOUNT ENDPOINTS
# ============================================================================

@app.get("/api/v1/account/balance", tags=["Account"])
async def get_balance(
    account_type: str = "UNIFIED",
    coin: Optional[str] = None,
    client: BybitRestClient = Depends(get_rest_client)
):
    """Get wallet balance"""
    try:
        result = await client.get_wallet_balance(account_type=account_type, coin=coin)
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/v1/account/positions", tags=["Account"])
async def get_positions(
    category: str = "linear",
    symbol: Optional[str] = None,
    client: BybitRestClient = Depends(get_rest_client)
):
    """Get position information"""
    try:
        result = await client.get_positions(category=category, symbol=symbol)
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============================================================================
# TRADING ENDPOINTS
# ============================================================================

@app.post("/api/v1/order/place", tags=["Trading"])
async def place_order(
    order: PlaceOrderRequest,
    client: BybitRestClient = Depends(get_rest_client)
):
    """Place a new order"""
    try:
        result = await client.place_order(
            category=order.category,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            qty=order.qty,
            price=order.price,
            time_in_force=order.time_in_force,
            reduce_only=order.reduce_only,
            order_link_id=order.order_link_id
        )
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/api/v1/order/cancel", tags=["Trading"])
async def cancel_order(
    request: CancelOrderRequest,
    client: BybitRestClient = Depends(get_rest_client)
):
    """Cancel an order"""
    try:
        result = await client.cancel_order(
            category=request.category,
            symbol=request.symbol,
            order_id=request.order_id,
            order_link_id=request.order_link_id
        )
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/v1/order/open", tags=["Trading"])
async def get_open_orders(
    category: str = "linear",
    symbol: Optional[str] = None,
    limit: int = 50,
    client: BybitRestClient = Depends(get_rest_client)
):
    """Get open orders"""
    try:
        result = await client.get_open_orders(category=category, symbol=symbol, limit=limit)
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/v1/order/history", tags=["Trading"])
async def get_order_history(
    category: str = "linear",
    symbol: Optional[str] = None,
    limit: int = 50,
    cursor: Optional[str] = None,
    client: BybitRestClient = Depends(get_rest_client)
):
    """Get order history"""
    try:
        result = await client.get_order_history(
            category=category,
            symbol=symbol,
            limit=limit,
            cursor=cursor
        )
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============================================================================
# MARKET DATA ENDPOINTS
# ============================================================================

@app.get("/api/v1/market/ticker", tags=["Market Data"])
async def get_ticker(
    category: str = "linear",
    symbol: Optional[str] = None,
    client: BybitRestClient = Depends(get_rest_client)
):
    """Get latest ticker data"""
    try:
        result = await client.get_ticker(category=category, symbol=symbol)
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/v1/market/kline", tags=["Market Data"])
async def get_kline(
    category: str = "linear",
    symbol: str = "BTCUSDT",
    interval: str = "60",
    limit: int = 200,
    client: BybitRestClient = Depends(get_rest_client)
):
    """Get kline/candlestick data"""
    try:
        result = await client.get_kline(
            category=category,
            symbol=symbol,
            interval=interval,
            limit=limit
        )
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/v1/market/orderbook", tags=["Market Data"])
async def get_orderbook(
    category: str = "linear",
    symbol: str = "BTCUSDT",
    limit: int = 25,
    client: BybitRestClient = Depends(get_rest_client)
):
    """Get orderbook depth"""
    try:
        result = await client.get_orderbook(category=category, symbol=symbol, limit=limit)
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============================================================================
# MONITORING ENDPOINTS
# ============================================================================

@app.get("/api/v1/status/circuit-breaker", tags=["Monitoring"])
async def get_circuit_breaker_status(client: BybitRestClient = Depends(get_rest_client)):
    """Get circuit breaker status"""
    return {"success": True, "data": client.get_circuit_breaker_status()}


@app.post("/api/v1/status/circuit-breaker/reset", tags=["Monitoring"])
async def reset_circuit_breaker(client: BybitRestClient = Depends(get_rest_client)):
    """Reset circuit breaker"""
    client.reset_circuit_breaker()
    return {"success": True, "message": "Circuit breaker reset"}


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
