"""
Portfolio Manager Service - Main Application
FastAPI application with portfolio management endpoints

REFACTORED: Phase 3 Complete - Using modular handlers
Architecture: main.py → handlers → services → domain
Enhanced: Phase 4 - Historical Performance Tracking
"""

from fastapi import FastAPI, Request, Query
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from typing import Optional
import asyncpg

from app.config import settings
from app.models import (
    HealthResponse,
    StatusResponse,
    PortfolioResponse,
    PortfolioListResponse,
    BalanceResponse,
    HoldingsResponse,
    PerformanceResponse,
    AssetPerformanceResponse,
    AllocationResponse,
    RebalanceResponse,
    TransactionResponse,
    TransactionHistoryResponse,
)
from app.services import PortfolioManager, PerformanceCalculator, PerformanceHistory
from app.scheduler import PerformanceSnapshotScheduler

# Import optimization module
from app.optimization import PortfolioOptimizer

# Import all handler functions (Phase 3: Modular architecture)
from app.handlers import (
    health_check,
    get_status,
    get_portfolio,
    list_portfolios,
    get_balance,
    get_holdings,
    sync_with_trading_engine,
    get_performance,
    get_asset_performance,
    get_allocation,
    get_rebalance_recommendations,
    buy_asset,
    sell_asset,
    get_transaction_history,
    optimize_portfolio,
    get_efficient_frontier,
    execute_rebalancing
)

# Create logs directory if it doesn't exist
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global instances
portfolio_manager: Optional[PortfolioManager] = None
performance_calculator: Optional[PerformanceCalculator] = None
portfolio_optimizer: Optional[PortfolioOptimizer] = None
performance_history: Optional[PerformanceHistory] = None
snapshot_scheduler: Optional[PerformanceSnapshotScheduler] = None
db_pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management for the application"""
    global portfolio_manager, performance_calculator, portfolio_optimizer
    global performance_history, snapshot_scheduler, db_pool

    # Startup
    logger.info(f"🚀 Starting {settings.service_name} on port {settings.service_port}")

    # Initialize database connection pool if enabled
    if settings.use_database:
        try:
            logger.info(f"Connecting to database: {settings.database_url}")
            db_pool = await asyncpg.create_pool(
                settings.database_url,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            logger.info("✅ Database connection pool created")
        except Exception as e:
            logger.error(f"❌ Failed to connect to database: {e}")
            logger.warning("Continuing without database (historical tracking disabled)")
            db_pool = None

    # Initialize core services
    portfolio_manager = PortfolioManager()
    await portfolio_manager.initialize()

    performance_calculator = PerformanceCalculator()

    # Initialize portfolio optimizer with default parameters
    portfolio_optimizer = PortfolioOptimizer(
        risk_free_rate=0.04,  # 4% annual risk-free rate
        confidence_level=0.95,  # 95% confidence level
        resampling_iterations=100
    )

    # Initialize performance history service (if database available)
    if db_pool:
        logger.info("Initializing Performance History service")
        performance_history = PerformanceHistory()
        await performance_history.initialize(db_pool)
        logger.info("✅ Performance History service initialized")

        # Initialize and start snapshot scheduler
        logger.info("Initializing Performance Snapshot Scheduler")
        snapshot_scheduler = PerformanceSnapshotScheduler(
            portfolio_manager=portfolio_manager,
            performance_history=performance_history,
            snapshot_hour=0,  # Midnight UTC
            snapshot_minute=0
        )
        await snapshot_scheduler.start()
        logger.info("✅ Performance Snapshot Scheduler started")
    else:
        logger.warning("⚠️  Performance History disabled (database not available)")
        performance_history = None
        snapshot_scheduler = None

    logger.info("✅ Portfolio Manager Service ready")

    yield

    # Graceful shutdown
    logger.info("Initiating graceful shutdown", service=settings.service_name)

    # Stop scheduler
    if snapshot_scheduler:
        logger.info("Stopping snapshot scheduler")
        await snapshot_scheduler.stop()

    # Cleanup services
    if portfolio_manager:
        await portfolio_manager.cleanup()

    if performance_history:
        await performance_history.cleanup()

    # Close database pool
    if db_pool:
        logger.info("Closing database connection pool")
        await db_pool.close()
        logger.info("✅ Database connection pool closed")

    logger.info("✅ Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Portfolio Manager Service",
    description="Portfolio tracking, performance analysis, and historical tracking",
    version="2.2.0",  # Updated: Added historical performance tracking
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


# ============================================================================
# ROOT ENDPOINT
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint with service information"""
    scheduler_status = None
    if snapshot_scheduler:
        scheduler_status = snapshot_scheduler.get_scheduler_status()

    return {
        "service": settings.service_name,
        "version": "2.2.0",  # Updated: Added historical performance tracking
        "status": "running",
        "architecture": "Modular (Phase 3 Complete)",
        "features": {
            "portfolio_tracking": True,
            "performance_metrics": True,
            "historical_tracking": performance_history is not None,
            "automated_snapshots": snapshot_scheduler is not None,
            "portfolio_optimization": True,
            "transaction_history": True
        },
        "scheduler": scheduler_status,
        "endpoints": {
            "health": "/health",
            "status": "/status",
            "docs": "/docs",
            "portfolio": "/api/v1/portfolio",
            "performance": "/api/v1/performance",
            "transactions": "/api/v1/transactions",
            "optimization": "/api/v1/portfolio/optimize"
        },
        "refactoring": {
            "status": "Phase 4 Complete ✅",
            "original_lines": 1046,
            "current_lines": "~350",
            "reduction": "67%",
            "modules": 13,
            "architecture": "main.py → handlers → services → domain",
            "new_features": [
                "Historical performance tracking",
                "Daily automated snapshots",
                "Period-based analysis (week/month/year/all)",
                "PostgreSQL persistence"
            ]
        }
    }


# ============================================================================
# HEALTH ENDPOINTS
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint"""
    return await health_check()


@app.get("/status", response_model=StatusResponse)
async def status():
    """Get service status"""
    return await get_status()


# ============================================================================
# PORTFOLIO ENDPOINTS
# ============================================================================

@app.get("/api/v1/portfolio", response_model=PortfolioResponse)
async def portfolio_endpoint(portfolio_id: str = "default"):
    """Get portfolio details"""
    return await get_portfolio(portfolio_id)


@app.get("/api/v1/portfolios", response_model=PortfolioListResponse)
async def portfolios_endpoint():
    """List all portfolios"""
    return await list_portfolios()


@app.get("/api/v1/portfolio/balance", response_model=BalanceResponse)
async def balance_endpoint(portfolio_id: str = "default"):
    """Get portfolio balance information"""
    return await get_balance(portfolio_id)


@app.get("/api/v1/portfolio/holdings", response_model=HoldingsResponse)
async def holdings_endpoint(portfolio_id: str = "default"):
    """Get portfolio holdings"""
    return await get_holdings(portfolio_id)


# ============================================================================
# PERFORMANCE ENDPOINTS
# ============================================================================

@app.get("/api/v1/performance", response_model=PerformanceResponse)
async def performance_endpoint(
    portfolio_id: str = "default",
    include_daily: bool = False,
    include_periods: bool = False
):
    """
    Get portfolio performance metrics

    Args:
        portfolio_id: Portfolio identifier (default: "default")
        include_daily: Include daily performance history (requires database)
        include_periods: Include period performance stats (requires database)

    Returns:
        Performance metrics with optional historical data
    """
    return await get_performance(portfolio_id, include_daily, include_periods)


@app.get("/api/v1/performance/assets", response_model=AssetPerformanceResponse)
async def asset_performance_endpoint(portfolio_id: str = "default"):
    """Get performance by asset"""
    return await get_asset_performance(portfolio_id)


# ============================================================================
# ALLOCATION ENDPOINTS
# ============================================================================

@app.get("/api/v1/allocation", response_model=AllocationResponse)
async def allocation_endpoint(portfolio_id: str = "default"):
    """Get portfolio allocation"""
    return await get_allocation(portfolio_id)


@app.get("/api/v1/rebalance", response_model=RebalanceResponse)
async def rebalance_endpoint(portfolio_id: str = "default"):
    """Get rebalancing recommendations"""
    return await get_rebalance_recommendations(portfolio_id)


# ============================================================================
# TRANSACTION ENDPOINTS
# ============================================================================

@app.post("/api/v1/transaction/buy", response_model=TransactionResponse)
async def buy_endpoint(request: Request, portfolio_id: str = Query("default"), symbol: str = Query(None), quantity: str = Query(None), price: str = Query(None)):
    """Execute buy transaction"""
    return await buy_asset(request, portfolio_id, symbol, quantity, price)


@app.post("/api/v1/transaction/sell", response_model=TransactionResponse)
async def sell_endpoint(request: Request, portfolio_id: str = Query("default"), symbol: str = Query(None), quantity: str = Query(None), price: str = Query(None)):
    """Execute sell transaction"""
    return await sell_asset(request, portfolio_id, symbol, quantity, price)


@app.get("/api/v1/transactions", response_model=TransactionHistoryResponse)
async def transactions_endpoint(portfolio_id: str = "default", limit: int = None, symbol: str = None):
    """Get transaction history"""
    return await get_transaction_history(portfolio_id, limit, symbol)


# ============================================================================
# SYNC ENDPOINT
# ============================================================================

@app.post("/api/v1/sync")
async def sync_endpoint(portfolio_id: str = "default"):
    """Sync portfolio with Trading Engine positions"""
    return await sync_with_trading_engine(portfolio_id)


# ============================================================================
# PORTFOLIO OPTIMIZATION ENDPOINTS
# ============================================================================

@app.post("/api/v1/portfolio/optimize")
async def optimize_endpoint(request: Request, portfolio_id: str = Query("default"), objective=None, lookback_days: int = 60,
                           max_position_size: float = 0.30, min_position_size: float = 0.05,
                           max_portfolio_volatility: float = None):
    """Calculate optimal portfolio allocation using Modern Portfolio Theory"""
    return await optimize_portfolio(
        request, portfolio_id, objective, lookback_days,
        max_position_size, min_position_size, max_portfolio_volatility
    )


@app.get("/api/v1/portfolio/efficient-frontier")
async def efficient_frontier_endpoint(request: Request, portfolio_id: str = Query("default"), num_points: int = 50, lookback_days: int = 60):
    """Generate efficient frontier for portfolio"""
    return await get_efficient_frontier(request, portfolio_id, num_points, lookback_days)


@app.post("/api/v1/portfolio/rebalance")
async def execute_rebalance_endpoint(request: Request, portfolio_id: str = Query("default"), target_weights: dict = None, execute: bool = False):
    """Execute portfolio rebalancing to target weights"""
    return await execute_rebalancing(request, portfolio_id, target_weights, execute)


# ============================================================================
# ADMIN/SCHEDULER ENDPOINTS
# ============================================================================

@app.post("/api/v1/admin/snapshot")
async def manual_snapshot_endpoint(portfolio_id: str = "default"):
    """
    Manually trigger performance snapshot

    Useful for testing or taking snapshots outside regular schedule.
    Requires database to be enabled.
    """
    if not snapshot_scheduler:
        return {
            "success": False,
            "error": "Snapshot scheduler not available (database disabled)"
        }

    try:
        result = await snapshot_scheduler.trigger_manual_snapshot()
        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        logger.error(f"Manual snapshot failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/v1/admin/scheduler/status")
async def scheduler_status_endpoint():
    """Get scheduler status information"""
    if not snapshot_scheduler:
        return {
            "enabled": False,
            "reason": "Database not configured"
        }

    status = snapshot_scheduler.get_scheduler_status()
    return {
        "enabled": True,
        **status
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.service_port)
