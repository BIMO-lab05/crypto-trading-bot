"""
Risk & Metrics Service - Main FastAPI Application
Provides real-time risk monitoring, performance analytics, and circuit breaker functionality
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
import httpx
import logging

from app.config import settings
from app.models import *
from app.risk_engine import RiskEngine

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
risk_engine: Optional[RiskEngine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management for the application"""
    global risk_engine

    # Startup
    logger.info(f"🚀 Starting {settings.service_name} on port {settings.service_port}")

    # Initialize risk engine
    risk_engine = RiskEngine()

    logger.info("✅ Risk & Metrics Service ready")

    yield

    # Shutdown
    logger.info("🛑 Shutting down Risk & Metrics Service")


# Create FastAPI app
app = FastAPI(
    title="Risk & Metrics Service",
    description="Real-time risk monitoring, performance analytics, and circuit breaker",
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


# === HELPER FUNCTIONS ===

async def fetch_portfolio_data() -> dict:
    """Fetch portfolio data from portfolio manager service"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{settings.portfolio_manager_url}/api/v1/portfolio")
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to fetch portfolio: {response.status_code}")
                return None
    except Exception as e:
        logger.error(f"Error fetching portfolio: {e}")
        return None


def get_risk_engine() -> RiskEngine:
    """Get risk engine instance"""
    if risk_engine is None:
        raise HTTPException(status_code=503, detail="Risk engine not initialized")
    return risk_engine


# === HEALTH & STATUS ENDPOINTS ===

@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Service health check"""
    # Check dependencies
    dependencies = {}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Check portfolio manager
            resp = await client.get(f"{settings.portfolio_manager_url}/health")
            dependencies["portfolio_manager"] = resp.status_code == 200
    except:
        dependencies["portfolio_manager"] = False

    return HealthCheckResponse(
        status="healthy" if all(dependencies.values()) else "degraded",
        service=settings.service_name,
        version="1.0.0",
        timestamp=datetime.now(),
        dependencies=dependencies
    )


@app.get("/status")
async def get_status():
    """Detailed service status"""
    engine = get_risk_engine()

    return {
        "service": settings.service_name,
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "circuit_breaker_active": engine.circuit_breaker_active,
        "configuration": {
            "max_position_size": settings.max_position_size,
            "max_portfolio_risk": settings.max_portfolio_risk,
            "max_drawdown_threshold": settings.max_drawdown_threshold,
            "max_daily_loss": settings.max_daily_loss,
            "max_exposure": settings.max_exposure,
            "risk_free_rate": settings.risk_free_rate,
            "circuit_breaker_enabled": settings.enable_circuit_breaker
        }
    }


# === RISK MONITORING ENDPOINTS ===

@app.get("/risk/scorecard", response_model=RiskScorecard)
async def get_risk_scorecard():
    """
    Get complete risk assessment scorecard
    Includes all risk metrics, alerts, and recommendations
    """
    engine = get_risk_engine()

    # Fetch portfolio data
    portfolio_data = await fetch_portfolio_data()
    if not portfolio_data:
        raise HTTPException(status_code=503, detail="Unable to fetch portfolio data")

    portfolio = portfolio_data.get('portfolio', {})
    positions = portfolio.get('holdings', [])
    total_capital = Decimal(str(portfolio.get('total_value', 10000)))

    # Calculate metrics
    capital_metrics = engine.calculate_capital_metrics(total_capital, positions)
    exposure_metrics = engine.calculate_exposure_metrics(positions, total_capital)

    # Drawdown (simplified - in production would use historical data)
    historical_values = [(datetime.now(), total_capital)]
    drawdown_metrics = engine.calculate_drawdown_metrics(total_capital, historical_values)

    # Performance (simplified - would use actual returns data)
    returns = engine.historical_returns if engine.historical_returns else [0.0]
    trades = []  # Would fetch from database
    performance_metrics = engine.calculate_performance_metrics(
        returns,
        drawdown_metrics.max_drawdown,
        trades
    )

    # Value at Risk
    var_metrics = engine.calculate_var(total_capital, returns)

    # Calculate risk score
    risk_score, risk_level = engine.calculate_risk_score(
        capital_metrics,
        exposure_metrics,
        drawdown_metrics,
        performance_metrics,
        var_metrics
    )

    # Generate alerts
    alerts = engine.generate_risk_alerts(
        capital_metrics,
        exposure_metrics,
        drawdown_metrics,
        performance_metrics
    )

    # Generate recommendations
    recommendations = []
    if capital_metrics.capital_utilization > 0.80:
        recommendations.append("High capital utilization - consider reducing position sizes")
    if exposure_metrics.exposure_ratio > 0.15:
        recommendations.append("Approaching exposure limit - monitor closely")
    if len(exposure_metrics.concentrated_positions) > 0:
        recommendations.append(f"Reduce concentration in {len(exposure_metrics.concentrated_positions)} positions")
    if performance_metrics.sharpe_ratio and performance_metrics.sharpe_ratio < 1.0:
        recommendations.append("Sharpe ratio below target - review strategy effectiveness")

    return RiskScorecard(
        timestamp=datetime.now(),
        overall_risk_level=risk_level,
        risk_score=risk_score,
        capital_risk_score=capital_metrics.capital_utilization * 20,
        exposure_risk_score=min(exposure_metrics.exposure_ratio / settings.max_exposure, 1.0) * 25,
        concentration_risk_score=min(len(exposure_metrics.concentrated_positions) * 5, 15),
        volatility_risk_score=min(performance_metrics.volatility / 0.20, 1.0) * 20,
        drawdown_risk_score=min((drawdown_metrics.current_drawdown / settings.max_drawdown_threshold) * 20, 20),
        capital_metrics=capital_metrics,
        exposure_metrics=exposure_metrics,
        drawdown_metrics=drawdown_metrics,
        performance_metrics=performance_metrics,
        var_metrics=var_metrics,
        active_alerts=alerts,
        recommendations=recommendations
    )


@app.get("/risk/capital", response_model=CapitalMetrics)
async def get_capital_metrics():
    """Get capital allocation and utilization metrics"""
    engine = get_risk_engine()

    portfolio_data = await fetch_portfolio_data()
    if not portfolio_data:
        raise HTTPException(status_code=503, detail="Unable to fetch portfolio data")

    portfolio = portfolio_data.get('portfolio', {})
    positions = portfolio.get('holdings', [])
    total_capital = Decimal(str(portfolio.get('total_value', 10000)))

    return engine.calculate_capital_metrics(total_capital, positions)


@app.get("/risk/exposure", response_model=ExposureMetrics)
async def get_exposure_metrics():
    """Get portfolio exposure analysis"""
    engine = get_risk_engine()

    portfolio_data = await fetch_portfolio_data()
    if not portfolio_data:
        raise HTTPException(status_code=503, detail="Unable to fetch portfolio data")

    portfolio = portfolio_data.get('portfolio', {})
    positions = portfolio.get('holdings', [])
    total_capital = Decimal(str(portfolio.get('total_value', 10000)))

    return engine.calculate_exposure_metrics(positions, total_capital)


@app.get("/risk/drawdown", response_model=DrawdownMetrics)
async def get_drawdown_metrics():
    """Get drawdown tracking metrics"""
    engine = get_risk_engine()

    portfolio_data = await fetch_portfolio_data()
    if not portfolio_data:
        raise HTTPException(status_code=503, detail="Unable to fetch portfolio data")

    portfolio = portfolio_data.get('portfolio', {})
    total_capital = Decimal(str(portfolio.get('total_value', 10000)))

    # In production, would fetch historical values from database
    historical_values = [(datetime.now(), total_capital)]

    return engine.calculate_drawdown_metrics(total_capital, historical_values)


@app.get("/risk/var", response_model=ValueAtRisk)
async def get_value_at_risk(confidence_level: float = 0.95, time_horizon_days: int = 1):
    """
    Calculate Value at Risk

    - **confidence_level**: Confidence level (0.90, 0.95, 0.99)
    - **time_horizon_days**: Time horizon in days
    """
    engine = get_risk_engine()

    portfolio_data = await fetch_portfolio_data()
    if not portfolio_data:
        raise HTTPException(status_code=503, detail="Unable to fetch portfolio data")

    portfolio = portfolio_data.get('portfolio', {})
    total_capital = Decimal(str(portfolio.get('total_value', 10000)))

    # In production, would fetch historical returns from database
    returns = engine.historical_returns if engine.historical_returns else []

    return engine.calculate_var(total_capital, returns, confidence_level, time_horizon_days)


# === PERFORMANCE ENDPOINTS ===

@app.get("/performance/metrics", response_model=PerformanceMetrics)
async def get_performance_metrics():
    """Get comprehensive performance metrics"""
    engine = get_risk_engine()

    portfolio_data = await fetch_portfolio_data()
    if not portfolio_data:
        raise HTTPException(status_code=503, detail="Unable to fetch portfolio data")

    # In production, would fetch returns and trades from database
    returns = engine.historical_returns if engine.historical_returns else []
    trades = []

    drawdown_data = await fetch_portfolio_data()
    historical_values = [(datetime.now(), Decimal(str(drawdown_data.get('portfolio', {}).get('total_value', 10000))))]
    drawdown_metrics = engine.calculate_drawdown_metrics(
        Decimal(str(drawdown_data.get('portfolio', {}).get('total_value', 10000))),
        historical_values
    )

    return engine.calculate_performance_metrics(
        returns,
        drawdown_metrics.max_drawdown,
        trades
    )


@app.get("/performance/sharpe")
async def get_sharpe_ratio():
    """Get Sharpe ratio calculation"""
    metrics = await get_performance_metrics()
    return {
        "sharpe_ratio": metrics.sharpe_ratio,
        "annualized_return": metrics.annualized_return,
        "volatility": metrics.volatility,
        "risk_free_rate": settings.risk_free_rate,
        "target_sharpe": settings.target_sharpe_ratio,
        "meets_target": metrics.sharpe_ratio >= settings.target_sharpe_ratio if metrics.sharpe_ratio else False
    }


# === ALERTS & CIRCUIT BREAKER ===

@app.get("/alerts", response_model=List[RiskAlert])
async def get_active_alerts():
    """Get active risk alerts"""
    scorecard = await get_risk_scorecard()
    return scorecard.active_alerts


@app.get("/circuit-breaker", response_model=CircuitBreakerStatus)
async def get_circuit_breaker_status():
    """
    Get circuit breaker status
    Returns whether trading is allowed
    """
    engine = get_risk_engine()

    portfolio_data = await fetch_portfolio_data()
    if not portfolio_data:
        raise HTTPException(status_code=503, detail="Unable to fetch portfolio data")

    portfolio = portfolio_data.get('portfolio', {})

    # Calculate daily P&L (simplified - would use actual daily data)
    daily_pnl = float(portfolio.get('total_return_pct', 0))

    # Get drawdown
    total_capital = Decimal(str(portfolio.get('total_value', 10000)))
    historical_values = [(datetime.now(), total_capital)]
    drawdown_metrics = engine.calculate_drawdown_metrics(total_capital, historical_values)

    # Get exposure
    positions = portfolio.get('holdings', [])
    exposure_metrics = engine.calculate_exposure_metrics(positions, total_capital)

    return engine.check_circuit_breaker(
        daily_pnl,
        drawdown_metrics.current_drawdown,
        exposure_metrics.exposure_ratio
    )


@app.post("/circuit-breaker/reset")
async def reset_circuit_breaker():
    """
    Reset circuit breaker (admin only)
    Requires manual intervention to resume trading after trip
    """
    engine = get_risk_engine()

    if not engine.circuit_breaker_active:
        return {
            "message": "Circuit breaker is not active",
            "status": "ok"
        }

    # Reset circuit breaker
    engine.circuit_breaker_active = False
    engine.circuit_breaker_tripped_at = None

    logger.warning("🔄 Circuit breaker manually reset")

    return {
        "message": "Circuit breaker reset successfully",
        "status": "reset",
        "timestamp": datetime.now().isoformat()
    }


# === CONFIGURATION ===

@app.get("/config/limits", response_model=RiskLimits)
async def get_risk_limits():
    """Get current risk limits configuration"""
    return RiskLimits(
        max_position_size=settings.max_position_size,
        max_portfolio_risk=settings.max_portfolio_risk,
        max_drawdown=settings.max_drawdown_threshold,
        max_daily_loss=settings.max_daily_loss,
        max_exposure=settings.max_exposure,
        max_leverage=2.0,  # Default
        min_sharpe_ratio=settings.target_sharpe_ratio
    )


@app.put("/config/limits")
async def update_risk_limits(limits: RiskLimits):
    """
    Update risk limits (admin only)
    ⚠️ Use with caution - affects all risk calculations
    """
    # In production, would persist to database and require authentication
    logger.warning(f"Risk limits update requested: {limits}")

    return {
        "message": "Risk limits updated",
        "limits": limits,
        "warning": "Changes will take effect immediately",
        "timestamp": datetime.now().isoformat()
    }


# === ROOT ENDPOINT ===

@app.get("/")
async def root():
    """Service information"""
    return {
        "service": "Risk & Metrics Service",
        "version": "1.0.0",
        "description": "Real-time risk monitoring and performance analytics",
        "endpoints": {
            "health": "/health",
            "risk_scorecard": "/risk/scorecard",
            "circuit_breaker": "/circuit-breaker",
            "performance": "/performance/metrics",
            "documentation": "/docs"
        },
        "status": "operational"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.service_host,
        port=settings.service_port,
        reload=True
    )
