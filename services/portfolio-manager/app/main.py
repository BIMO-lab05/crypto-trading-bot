"""
Portfolio Manager Service - Main Application
FastAPI application with portfolio management endpoints
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from decimal import Decimal
import httpx
import time
import logging
from typing import Optional

from app.config import settings
from app.models import *
from app.services import PortfolioManager, PerformanceCalculator

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

# Global instances
portfolio_manager: Optional[PortfolioManager] = None
performance_calculator: Optional[PerformanceCalculator] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management for the application"""
    global portfolio_manager, performance_calculator

    # Startup
    logger.info(f"🚀 Starting {settings.service_name} on port {settings.service_port}")

    portfolio_manager = PortfolioManager()
    await portfolio_manager.initialize()

    performance_calculator = PerformanceCalculator()

    logger.info("✅ Portfolio Manager Service ready")

    yield

    # Shutdown
    logger.info("🛑 Shutting down Portfolio Manager Service")
    if portfolio_manager:
        await portfolio_manager.cleanup()


# Create FastAPI app
app = FastAPI(
    title="Portfolio Manager Service",
    description="Portfolio tracking, performance analysis, and rebalancing",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Helper functions
async def check_service_health(url: str) -> bool:
    """Check if external service is healthy"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/health")
            return response.status_code == 200
    except Exception:
        return False


def get_portfolio_manager() -> PortfolioManager:
    """Get portfolio manager instance"""
    if portfolio_manager is None:
        raise HTTPException(status_code=503, detail="Portfolio Manager not initialized")
    return portfolio_manager


def get_performance_calculator() -> PerformanceCalculator:
    """Get performance calculator instance"""
    if performance_calculator is None:
        raise HTTPException(status_code=503, detail="Performance Calculator not initialized")
    return performance_calculator


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": settings.service_name,
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "status": "/status",
            "docs": "/docs",
            "portfolio": "/api/v1/portfolio",
            "performance": "/api/v1/performance"
        }
    }


# Health endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    trading_engine_healthy = await check_service_health(settings.trading_engine_url)
    market_data_healthy = await check_service_health(settings.market_data_url)

    return HealthResponse(
        status="healthy",
        trading_engine_connection=trading_engine_healthy,
        market_data_connection=market_data_healthy,
        database_connection=False  # Not implemented yet
    )


@app.get("/status", response_model=StatusResponse)
async def get_status():
    """Get service status"""
    manager = get_portfolio_manager()
    portfolios = manager.list_portfolios()

    total_value = sum(p.total_value for p in portfolios)
    active_positions = sum(len(p.assets) for p in portfolios)

    return StatusResponse(
        status="running",
        portfolio_count=len(portfolios),
        total_value=str(total_value),
        active_positions=active_positions
    )


# Portfolio endpoints
@app.get("/api/v1/portfolio", response_model=PortfolioResponse)
async def get_portfolio(portfolio_id: str = "default"):
    """Get portfolio details"""
    manager = get_portfolio_manager()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    # Update prices before returning
    await manager.update_prices(portfolio_id)

    snapshot = manager.get_snapshot(portfolio_id)

    return PortfolioResponse(
        success=True,
        portfolio=snapshot,
        message="Portfolio retrieved successfully"
    )


@app.get("/api/v1/portfolios", response_model=PortfolioListResponse)
async def list_portfolios():
    """List all portfolios"""
    manager = get_portfolio_manager()

    snapshots = []
    for portfolio in manager.list_portfolios():
        snapshot = manager.get_snapshot(portfolio.portfolio_id)
        if snapshot:
            snapshots.append(snapshot)

    return PortfolioListResponse(
        success=True,
        portfolios=snapshots,
        count=len(snapshots)
    )


@app.get("/api/v1/portfolio/balance", response_model=BalanceResponse)
async def get_balance(portfolio_id: str = "default"):
    """Get portfolio balance information"""
    manager = get_portfolio_manager()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    # Update prices
    await manager.update_prices(portfolio_id)

    return BalanceResponse(
        success=True,
        portfolio_id=portfolio.portfolio_id,
        cash_balance=str(portfolio.cash_balance),
        total_value=str(portfolio.total_value),
        unrealized_pnl=str(portfolio.unrealized_pnl),
        realized_pnl=str(portfolio.realized_pnl),
        total_pnl=str(portfolio.total_pnl),
        total_return_pct=str(portfolio.total_return_pct)
    )


@app.get("/api/v1/portfolio/holdings", response_model=HoldingsResponse)
async def get_holdings(portfolio_id: str = "default"):
    """Get portfolio holdings"""
    manager = get_portfolio_manager()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    # Update prices
    await manager.update_prices(portfolio_id)

    snapshot = manager.get_snapshot(portfolio_id)

    total_value = sum(Decimal(h.current_value) for h in snapshot.holdings)

    return HoldingsResponse(
        success=True,
        portfolio_id=portfolio_id,
        holdings=snapshot.holdings,
        total_value=str(total_value),
        count=len(snapshot.holdings)
    )


# Performance endpoints
@app.get("/api/v1/performance", response_model=PerformanceResponse)
async def get_performance(
    portfolio_id: str = "default",
    include_daily: bool = False,
    include_periods: bool = False
):
    """Get portfolio performance metrics"""
    manager = get_portfolio_manager()
    calculator = get_performance_calculator()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    # Update prices
    await manager.update_prices(portfolio_id)

    # Calculate metrics
    metrics = calculator.calculate_metrics(portfolio)

    # Optional: Add daily and period performance
    daily_performance = None
    period_performance = None

    # TODO: Implement historical tracking for daily/period performance

    return PerformanceResponse(
        success=True,
        portfolio_id=portfolio_id,
        metrics=metrics,
        daily_performance=daily_performance,
        period_performance=period_performance
    )


@app.get("/api/v1/performance/assets", response_model=AssetPerformanceResponse)
async def get_asset_performance(portfolio_id: str = "default"):
    """Get performance by asset"""
    manager = get_portfolio_manager()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    # Update prices
    await manager.update_prices(portfolio_id)

    assets = manager.get_asset_performance(portfolio_id)

    return AssetPerformanceResponse(
        success=True,
        portfolio_id=portfolio_id,
        assets=assets
    )


# Allocation endpoints
@app.get("/api/v1/allocation", response_model=AllocationResponse)
async def get_allocation(portfolio_id: str = "default"):
    """Get portfolio allocation"""
    manager = get_portfolio_manager()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    # Update prices
    await manager.update_prices(portfolio_id)

    allocations = portfolio.get_asset_allocation()
    allocations_str = {k: str(v) for k, v in allocations.items()}

    needs_rebalancing, _ = manager.check_rebalancing_needed(portfolio_id)

    return AllocationResponse(
        success=True,
        portfolio_id=portfolio_id,
        allocations=allocations_str,
        needs_rebalancing=needs_rebalancing
    )


@app.get("/api/v1/rebalance", response_model=RebalanceResponse)
async def get_rebalance_recommendations(portfolio_id: str = "default"):
    """Get rebalancing recommendations"""
    manager = get_portfolio_manager()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    # Update prices
    await manager.update_prices(portfolio_id)

    needs_rebalancing, recommendations = manager.check_rebalancing_needed(portfolio_id)

    total_cost = sum(Decimal(r.estimated_cost) for r in recommendations)

    return RebalanceResponse(
        success=True,
        portfolio_id=portfolio_id,
        needs_rebalancing=needs_rebalancing,
        recommendations=recommendations,
        total_transactions=len(recommendations),
        estimated_total_cost=str(total_cost)
    )


# Transaction endpoints
@app.post("/api/v1/transaction/buy", response_model=TransactionResponse)
async def buy_asset(
    portfolio_id: str = "default",
    symbol: str = Query(..., description="Asset symbol"),
    quantity: str = Query(..., description="Quantity to buy"),
    price: Optional[str] = Query(None, description="Price (fetch if not provided)")
):
    """Execute buy transaction"""
    manager = get_portfolio_manager()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    # Parse quantity
    qty = Decimal(quantity)

    # Get price if not provided
    if price is None:
        current_price = await manager._fetch_current_price(symbol)
        if current_price == 0:
            raise HTTPException(status_code=400, detail=f"Could not fetch price for {symbol}")
    else:
        current_price = Decimal(price)

    # Execute transaction
    success, message, _ = manager.execute_transaction(
        portfolio_id=portfolio_id,
        symbol=symbol,
        action="BUY",
        quantity=qty,
        price=current_price
    )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    total_cost = qty * current_price

    return TransactionResponse(
        success=True,
        transaction_id=f"txn_{int(time.time() * 1000)}",
        symbol=symbol,
        action="BUY",
        quantity=str(qty),
        price=str(current_price),
        total_cost=str(total_cost),
        message=message
    )


@app.post("/api/v1/transaction/sell", response_model=TransactionResponse)
async def sell_asset(
    portfolio_id: str = "default",
    symbol: str = Query(..., description="Asset symbol"),
    quantity: str = Query(..., description="Quantity to sell"),
    price: Optional[str] = Query(None, description="Price (fetch if not provided)")
):
    """Execute sell transaction"""
    manager = get_portfolio_manager()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    # Parse quantity
    qty = Decimal(quantity)

    # Get price if not provided
    if price is None:
        current_price = await manager._fetch_current_price(symbol)
        if current_price == 0:
            raise HTTPException(status_code=400, detail=f"Could not fetch price for {symbol}")
    else:
        current_price = Decimal(price)

    # Execute transaction
    success, message, realized_pnl = manager.execute_transaction(
        portfolio_id=portfolio_id,
        symbol=symbol,
        action="SELL",
        quantity=qty,
        price=current_price
    )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    total_proceeds = qty * current_price

    return TransactionResponse(
        success=True,
        transaction_id=f"txn_{int(time.time() * 1000)}",
        symbol=symbol,
        action="SELL",
        quantity=str(qty),
        price=str(current_price),
        total_cost=str(total_proceeds),
        realized_pnl=str(realized_pnl) if realized_pnl else None,
        message=message
    )


# Sync endpoint
@app.post("/api/v1/sync")
async def sync_with_trading_engine(portfolio_id: str = "default"):
    """Sync portfolio with Trading Engine positions"""
    manager = get_portfolio_manager()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    success = await manager.sync_with_trading_engine(portfolio_id)

    if success:
        return {"success": True, "message": "Portfolio synced successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to sync with Trading Engine")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.service_port)
