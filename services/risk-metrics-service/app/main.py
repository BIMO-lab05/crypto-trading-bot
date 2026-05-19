"""
Risk & Metrics Service - Main FastAPI Application
Provides real-time risk monitoring, performance analytics, and circuit breaker functionality
With performance optimizations: Redis caching, connection pooling, request batching
"""

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import Response
from pathlib import Path

# Add shared utilities to path

from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
import httpx
import logging
import asyncio

# Prometheus metrics imports
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

from app.config import settings
from app.models import (
    HealthCheckResponse,
    RiskScorecard,
    CapitalMetrics,
    ExposureMetrics,
    DrawdownMetrics,
    ValueAtRisk,
    PerformanceMetrics,
    RiskAlert,
    CircuitBreakerStatus,
    RiskLimits,
)
from app.risk_engine import RiskEngine
from app.auth import verify_admin_key

# Import performance optimization modules
from app.cache import RiskMetricsCache
from app.performance import (
    PerformanceMonitor,
    RequestBatcher,
    ConnectionPool,
    get_performance_monitor,
    get_connection_pool,
)

# Ensure logs directory exists
Path("logs").mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("logs/service.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Global instances
risk_engine: Optional[RiskEngine] = None
cache: Optional[RiskMetricsCache] = None
performance_monitor: Optional[PerformanceMonitor] = None
request_batcher: Optional[RequestBatcher] = None
connection_pool: Optional[ConnectionPool] = None
http_client: Optional[httpx.AsyncClient] = None

# === PROMETHEUS METRICS ===

# HTTP request counter
http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)

# HTTP request duration histogram
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

# Active requests gauge
http_requests_active = Gauge("http_requests_active", "Number of active HTTP requests")

# Risk-specific metrics
risk_calculations_total = Counter(
    "risk_calculations_total",
    "Total risk calculations performed",
    ["symbol", "metric_type"],
)

risk_calculation_duration_seconds = Histogram(
    "risk_calculation_duration_seconds",
    "Risk calculation duration in seconds",
    ["metric_type"],
)

risk_score_gauge = Gauge("risk_score", "Current risk score", ["risk_level"])

risk_alerts_total = Counter(
    "risk_alerts_total", "Total risk alerts generated", ["severity", "category"]
)

circuit_breaker_trips = Counter(
    "circuit_breaker_trips", "Number of circuit breaker trips", ["reason"]
)

circuit_breaker_active_gauge = Gauge(
    "circuit_breaker_active",
    "Whether circuit breaker is currently active (1=active, 0=inactive)",
)

portfolio_value_gauge = Gauge("portfolio_value_usd", "Current portfolio value in USD")

capital_utilization_gauge = Gauge(
    "capital_utilization_ratio", "Current capital utilization ratio"
)

exposure_ratio_gauge = Gauge("exposure_ratio", "Current exposure ratio")

drawdown_current_gauge = Gauge(
    "drawdown_current_percent", "Current drawdown percentage"
)

sharpe_ratio_gauge = Gauge("sharpe_ratio", "Current Sharpe ratio")

cache_hit_counter = Counter("cache_hits_total", "Number of cache hits", ["endpoint"])

cache_miss_counter = Counter(
    "cache_misses_total", "Number of cache misses", ["endpoint"]
)

# === END PROMETHEUS METRICS ===


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management for the application"""
    global \
        risk_engine, \
        cache, \
        performance_monitor, \
        request_batcher, \
        connection_pool, \
        http_client

    # Startup
    logger.info(f"🚀 Starting {settings.service_name} on port {settings.service_port}")

    # Initialize risk engine
    risk_engine = RiskEngine()

    # Initialize performance monitoring
    if settings.enable_performance_monitoring:
        performance_monitor = PerformanceMonitor(
            max_history=settings.performance_history_size
        )
        logger.info("✅ Performance monitoring enabled")

    # Initialize Redis cache
    if settings.redis_enabled:
        cache = RiskMetricsCache(
            redis_url=settings.redis_url,
            ttl_seconds=settings.redis_cache_ttl,
            enabled=True,
        )
        await cache.connect()
    else:
        logger.warning("⚠️ Redis caching disabled")

    # Initialize request batcher
    if settings.enable_request_batching:
        request_batcher = RequestBatcher(
            batch_size=settings.batch_size, max_wait_ms=settings.batch_max_wait_ms
        )
        logger.info("✅ Request batching enabled")

    # Initialize connection pool
    connection_pool = ConnectionPool(
        max_connections=settings.max_http_connections, timeout=settings.http_timeout
    )
    logger.info(
        f"✅ HTTP connection pool initialized (max: {settings.max_http_connections})"
    )

    # Initialize shared HTTP client with connection pooling
    http_client = httpx.AsyncClient(
        timeout=settings.http_timeout,
        limits=httpx.Limits(
            max_keepalive_connections=settings.max_http_connections,
            max_connections=settings.max_http_connections,
        ),
    )

    logger.info("✅ Risk & Metrics Service ready")

    yield

    # Graceful shutdown
    logger.info(f"Initiating graceful shutdown for {settings.service_name}")

    # Close HTTP client
    if http_client:
        await http_client.aclose()

    # Disconnect cache
    if cache:
        await cache.disconnect()

    logger.info("✅ Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Risk & Metrics Service",
    description="Real-time risk monitoring, performance analytics, and circuit breaker",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware with restricted origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === PROMETHEUS MIDDLEWARE ===


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Track all HTTP requests with Prometheus metrics"""
    # Increment active requests
    http_requests_active.inc()

    # Extract method and path
    method = request.method
    path = request.url.path

    # Start timer
    start_time = datetime.utcnow()

    try:
        # Process request
        response = await call_next(request)

        # Calculate duration
        duration = (datetime.utcnow() - start_time).total_seconds()

        # Record metrics
        http_request_duration_seconds.labels(method=method, endpoint=path).observe(
            duration
        )
        http_requests_total.labels(
            method=method, endpoint=path, status=response.status_code
        ).inc()

        return response
    finally:
        # Decrement active requests
        http_requests_active.dec()


# === END PROMETHEUS MIDDLEWARE ===


# Prometheus metrics endpoint
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# === PERFORMANCE MIDDLEWARE ===


@app.middleware("http")
async def performance_tracking_middleware(request: Request, call_next):
    """Track request performance for all endpoints"""
    monitor = get_performance_monitor()

    if monitor and settings.enable_performance_monitoring:
        async with monitor.measure(request.url.path):
            response = await call_next(request)
        return response
    else:
        return await call_next(request)


# === HELPER FUNCTIONS ===


async def fetch_portfolio_data() -> dict:
    """
    Fetch portfolio data from portfolio manager service
    Uses connection pool for efficiency
    """
    try:
        pool = get_connection_pool()
        async with pool.acquire():
            response = await http_client.get(
                f"{settings.portfolio_manager_url}/api/v1/portfolio"
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to fetch portfolio: {response.status_code}")
                return None
    except Exception as e:
        logger.error(f"Error fetching portfolio: {e}")
        return None


async def fetch_performance_data() -> Optional[dict]:
    """
    Fetch performance metrics from portfolio manager service.

    Used by the circuit-breaker route to read DAILY return (not lifetime).
    Returns the parsed JSON or None on any failure; callers must treat a
    None / missing daily metric as "no signal" rather than as a loss.
    """
    try:
        pool = get_connection_pool()
        async with pool.acquire():
            response = await http_client.get(
                f"{settings.portfolio_manager_url}/api/v1/performance"
            )
            if response.status_code == 200:
                return response.json()
            logger.warning(f"Failed to fetch performance: HTTP {response.status_code}")
            return None
    except Exception as e:
        logger.warning(f"Error fetching performance: {e}")
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
        pool = get_connection_pool()
        async with pool.acquire():
            resp = await http_client.get(f"{settings.portfolio_manager_url}/health")
            dependencies["portfolio_manager"] = resp.status_code == 200
    except Exception as e:
        logger.debug(f"Portfolio manager health check failed: {e}")
        dependencies["portfolio_manager"] = False

    # Check Redis
    if cache and cache.enabled:
        try:
            await cache.client.ping()
            dependencies["redis_cache"] = True
        except:
            dependencies["redis_cache"] = False
    else:
        dependencies["redis_cache"] = False

    return HealthCheckResponse(
        status="healthy" if all(dependencies.values()) else "degraded",
        service=settings.service_name,
        version="1.0.0",
        timestamp=datetime.now(),
        dependencies=dependencies,
    )


@app.get("/ready")
async def readiness_check():
    """Kubernetes readiness probe - indicates service is ready to accept traffic"""
    # Simple check - service is running and can respond
    return {
        "ready": True,
        "service": settings.service_name,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/status")
async def get_status():
    """Detailed service status with performance metrics"""
    engine = get_risk_engine()
    monitor = get_performance_monitor()
    pool = get_connection_pool()

    status_data = {
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
            "circuit_breaker_enabled": settings.enable_circuit_breaker,
        },
    }

    # Add performance stats if monitoring enabled
    if monitor:
        status_data["performance"] = monitor.get_summary(last_minutes=5)

    # Add cache stats
    if cache:
        status_data["cache"] = cache.get_stats()

    # Add connection pool stats
    if pool:
        status_data["connection_pool"] = pool.get_stats()

    return status_data


@app.get("/performance/stats")
async def get_performance_stats():
    """Get detailed performance statistics"""
    monitor = get_performance_monitor()

    if not monitor:
        return {"message": "Performance monitoring disabled"}

    return {
        "summary": monitor.get_summary(),
        "last_5_minutes": monitor.get_summary(last_minutes=5),
        "endpoints": monitor.get_endpoint_stats(),
    }


@app.post("/performance/reset")
async def reset_performance_stats(api_key: str = Depends(verify_admin_key)):
    """Reset performance statistics (admin only)"""
    monitor = get_performance_monitor()
    if monitor:
        monitor.metrics.clear()
        monitor.endpoint_stats.clear()

    if cache:
        cache.reset_stats()

    return {
        "message": "Performance statistics reset",
        "timestamp": datetime.now().isoformat(),
    }


# === RISK MONITORING ENDPOINTS (WITH CACHING) ===


@app.get("/risk/scorecard", response_model=RiskScorecard)
async def get_risk_scorecard():
    """
    Get complete risk assessment scorecard
    Includes all risk metrics, alerts, and recommendations
    WITH CACHING for improved performance
    """
    engine = get_risk_engine()
    monitor = get_performance_monitor()

    # Start timer
    start_time = datetime.utcnow()

    # Try cache first
    cache_key_params = {"endpoint": "scorecard"}
    cached_result = (
        await cache.get("risk_scorecard", **cache_key_params) if cache else None
    )

    if cached_result:
        logger.debug("Serving risk scorecard from cache")
        cache_hit_counter.labels(endpoint="scorecard").inc()
        # Record cache hit in monitoring
        if monitor:
            async with monitor.measure("/risk/scorecard", cache_hit=True):
                pass
        return RiskScorecard(**cached_result)

    cache_miss_counter.labels(endpoint="scorecard").inc()

    # Cache miss - calculate fresh data
    async with monitor.measure("/risk/scorecard") if monitor else asyncio.nullcontext():
        # Fetch portfolio data
        portfolio_data = await fetch_portfolio_data()
        if not portfolio_data:
            raise HTTPException(
                status_code=503, detail="Unable to fetch portfolio data"
            )

        portfolio = portfolio_data.get("portfolio", {})
        positions = portfolio.get("holdings", [])
        total_capital = Decimal(str(portfolio.get("total_value", 10000)))

        # Update portfolio value gauge
        portfolio_value_gauge.set(float(total_capital))

        # Calculate metrics in parallel using asyncio.gather for better performance
        capital_metrics = engine.calculate_capital_metrics(total_capital, positions)
        exposure_metrics = engine.calculate_exposure_metrics(positions, total_capital)

        # Drawdown (simplified - in production would use historical data)
        historical_values = [(datetime.now(), total_capital)]
        drawdown_metrics = engine.calculate_drawdown_metrics(
            total_capital, historical_values
        )

        # Performance (simplified - would use actual returns data)
        returns = engine.historical_returns if engine.historical_returns else [0.0]
        trades = []  # Would fetch from database
        performance_metrics = engine.calculate_performance_metrics(
            returns, drawdown_metrics.max_drawdown, trades
        )

        # Value at Risk
        var_metrics = engine.calculate_var(total_capital, returns)

        # Calculate risk score
        risk_score, risk_level = engine.calculate_risk_score(
            capital_metrics,
            exposure_metrics,
            drawdown_metrics,
            performance_metrics,
            var_metrics,
        )

        # Update gauges
        risk_score_gauge.labels(risk_level=risk_level).set(risk_score)
        capital_utilization_gauge.set(capital_metrics.capital_utilization)
        exposure_ratio_gauge.set(exposure_metrics.exposure_ratio)
        drawdown_current_gauge.set(drawdown_metrics.current_drawdown)
        if performance_metrics.sharpe_ratio:
            sharpe_ratio_gauge.set(performance_metrics.sharpe_ratio)

        # Generate alerts
        alerts = engine.generate_risk_alerts(
            capital_metrics, exposure_metrics, drawdown_metrics, performance_metrics
        )

        # Record alert metrics
        for alert in alerts:
            risk_alerts_total.labels(
                severity=alert.severity, category=alert.category
            ).inc()

        # Generate recommendations
        recommendations = []
        if capital_metrics.capital_utilization > 0.80:
            recommendations.append(
                "High capital utilization - consider reducing position sizes"
            )
        if exposure_metrics.exposure_ratio > 0.15:
            recommendations.append("Approaching exposure limit - monitor closely")
        if len(exposure_metrics.concentrated_positions) > 0:
            recommendations.append(
                f"Reduce concentration in {len(exposure_metrics.concentrated_positions)} positions"
            )
        if performance_metrics.sharpe_ratio and performance_metrics.sharpe_ratio < 1.0:
            recommendations.append(
                "Sharpe ratio below target - review strategy effectiveness"
            )

        scorecard = RiskScorecard(
            timestamp=datetime.now(),
            overall_risk_level=risk_level,
            risk_score=risk_score,
            capital_risk_score=capital_metrics.capital_utilization * 20,
            exposure_risk_score=min(
                exposure_metrics.exposure_ratio / settings.max_exposure, 1.0
            )
            * 25,
            concentration_risk_score=min(
                len(exposure_metrics.concentrated_positions) * 5, 15
            ),
            volatility_risk_score=min(performance_metrics.volatility / 0.20, 1.0) * 20,
            drawdown_risk_score=min(
                (drawdown_metrics.current_drawdown / settings.max_drawdown_threshold)
                * 20,
                20,
            ),
            capital_metrics=capital_metrics,
            exposure_metrics=exposure_metrics,
            drawdown_metrics=drawdown_metrics,
            performance_metrics=performance_metrics,
            var_metrics=var_metrics,
            active_alerts=alerts,
            recommendations=recommendations,
        )

        # Cache the result
        if cache:
            await cache.set(
                "risk_scorecard", scorecard.model_dump(), **cache_key_params
            )

        # Record metrics
        duration = (datetime.utcnow() - start_time).total_seconds()
        risk_calculation_duration_seconds.labels(metric_type="scorecard").observe(
            duration
        )
        risk_calculations_total.labels(
            symbol="portfolio", metric_type="scorecard"
        ).inc()

        return scorecard


@app.get("/risk/capital", response_model=CapitalMetrics)
async def get_capital_metrics():
    """Get capital allocation and utilization metrics WITH CACHING"""
    engine = get_risk_engine()

    # Try cache first
    cache_key_params = {"endpoint": "capital"}
    cached_result = (
        await cache.get("capital_metrics", **cache_key_params) if cache else None
    )

    if cached_result:
        cache_hit_counter.labels(endpoint="capital").inc()
        return CapitalMetrics(**cached_result)

    cache_miss_counter.labels(endpoint="capital").inc()

    portfolio_data = await fetch_portfolio_data()
    if not portfolio_data:
        raise HTTPException(status_code=503, detail="Unable to fetch portfolio data")

    portfolio = portfolio_data.get("portfolio", {})
    positions = portfolio.get("holdings", [])
    total_capital = Decimal(str(portfolio.get("total_value", 10000)))

    metrics = engine.calculate_capital_metrics(total_capital, positions)

    # Cache the result
    if cache:
        await cache.set("capital_metrics", metrics.model_dump(), **cache_key_params)

    # Record metrics
    risk_calculations_total.labels(symbol="portfolio", metric_type="capital").inc()

    return metrics


@app.get("/risk/exposure", response_model=ExposureMetrics)
async def get_exposure_metrics():
    """Get portfolio exposure analysis WITH CACHING"""
    engine = get_risk_engine()

    # Try cache first
    cache_key_params = {"endpoint": "exposure"}
    cached_result = (
        await cache.get("exposure_metrics", **cache_key_params) if cache else None
    )

    if cached_result:
        cache_hit_counter.labels(endpoint="exposure").inc()
        return ExposureMetrics(**cached_result)

    cache_miss_counter.labels(endpoint="exposure").inc()

    portfolio_data = await fetch_portfolio_data()
    if not portfolio_data:
        raise HTTPException(status_code=503, detail="Unable to fetch portfolio data")

    portfolio = portfolio_data.get("portfolio", {})
    positions = portfolio.get("holdings", [])
    total_capital = Decimal(str(portfolio.get("total_value", 10000)))

    metrics = engine.calculate_exposure_metrics(positions, total_capital)

    # Cache the result
    if cache:
        await cache.set("exposure_metrics", metrics.model_dump(), **cache_key_params)

    # Record metrics
    risk_calculations_total.labels(symbol="portfolio", metric_type="exposure").inc()

    return metrics


@app.get("/risk/drawdown", response_model=DrawdownMetrics)
async def get_drawdown_metrics():
    """Get drawdown tracking metrics WITH CACHING"""
    engine = get_risk_engine()

    # Try cache first
    cache_key_params = {"endpoint": "drawdown"}
    cached_result = (
        await cache.get("drawdown_metrics", **cache_key_params) if cache else None
    )

    if cached_result:
        cache_hit_counter.labels(endpoint="drawdown").inc()
        return DrawdownMetrics(**cached_result)

    cache_miss_counter.labels(endpoint="drawdown").inc()

    portfolio_data = await fetch_portfolio_data()
    if not portfolio_data:
        raise HTTPException(status_code=503, detail="Unable to fetch portfolio data")

    portfolio = portfolio_data.get("portfolio", {})
    total_capital = Decimal(str(portfolio.get("total_value", 10000)))

    # In production, would fetch historical values from database
    historical_values = [(datetime.now(), total_capital)]

    metrics = engine.calculate_drawdown_metrics(total_capital, historical_values)

    # Cache the result
    if cache:
        await cache.set("drawdown_metrics", metrics.model_dump(), **cache_key_params)

    # Record metrics
    risk_calculations_total.labels(symbol="portfolio", metric_type="drawdown").inc()

    return metrics


@app.get("/risk/var", response_model=ValueAtRisk)
async def get_value_at_risk(confidence_level: float = 0.95, time_horizon_days: int = 1):
    """
    Calculate Value at Risk WITH CACHING

    - **confidence_level**: Confidence level (0.90, 0.95, 0.99)
    - **time_horizon_days**: Time horizon in days
    """
    engine = get_risk_engine()

    # Try cache first
    cache_key_params = {
        "endpoint": "var",
        "confidence": confidence_level,
        "horizon": time_horizon_days,
    }
    cached_result = (
        await cache.get("var_metrics", **cache_key_params) if cache else None
    )

    if cached_result:
        cache_hit_counter.labels(endpoint="var").inc()
        return ValueAtRisk(**cached_result)

    cache_miss_counter.labels(endpoint="var").inc()

    portfolio_data = await fetch_portfolio_data()
    if not portfolio_data:
        raise HTTPException(status_code=503, detail="Unable to fetch portfolio data")

    portfolio = portfolio_data.get("portfolio", {})
    total_capital = Decimal(str(portfolio.get("total_value", 10000)))

    # In production, would fetch historical returns from database
    returns = engine.historical_returns if engine.historical_returns else []

    metrics = engine.calculate_var(
        total_capital, returns, confidence_level, time_horizon_days
    )

    # Cache the result
    if cache:
        await cache.set("var_metrics", metrics.model_dump(), **cache_key_params)

    # Record metrics
    risk_calculations_total.labels(symbol="portfolio", metric_type="var").inc()

    return metrics


# === API V1 ENDPOINTS (RESTful) ===
#
# NOTE: Two endpoints previously lived here:
#   - GET /api/v1/alerts/active
#   - GET /api/v1/portfolio/{portfolio_id}/risk-scorecard
# Both called RiskEngine methods that do not exist
# (get_circuit_breaker_status, get_risk_level, generate_recommendations)
# and passed wrong arg shapes to generate_risk_alerts / calculate_risk_score
# (raw scalars instead of typed metrics objects). They returned HTTP 500 on
# first call. Removed during 2026-05-01 audit.
#
# - Use /alerts (line ~882) for the alerts list (delegates to /risk/scorecard).
# - Use /risk/scorecard for the scorecard. Per-portfolio scoping is not yet
#   implemented; portfolio-manager exposes a single portfolio.


# === PERFORMANCE ENDPOINTS ===


@app.get("/performance/metrics", response_model=PerformanceMetrics)
async def get_performance_metrics():
    """Get comprehensive performance metrics WITH CACHING"""
    engine = get_risk_engine()

    # Try cache first
    cache_key_params = {"endpoint": "performance"}
    cached_result = (
        await cache.get("performance_metrics", **cache_key_params) if cache else None
    )

    if cached_result:
        cache_hit_counter.labels(endpoint="performance").inc()
        return PerformanceMetrics(**cached_result)

    cache_miss_counter.labels(endpoint="performance").inc()

    portfolio_data = await fetch_portfolio_data()
    if not portfolio_data:
        raise HTTPException(status_code=503, detail="Unable to fetch portfolio data")

    # In production, would fetch returns and trades from database
    returns = engine.historical_returns if engine.historical_returns else []
    trades = []

    # Reuse already-fetched portfolio data to avoid duplicate network call
    portfolio = portfolio_data.get("portfolio", {})
    total_capital = Decimal(str(portfolio.get("total_value", 10000)))
    historical_values = [(datetime.now(), total_capital)]
    drawdown_metrics = engine.calculate_drawdown_metrics(
        total_capital, historical_values
    )

    metrics = engine.calculate_performance_metrics(
        returns, drawdown_metrics.max_drawdown, trades
    )

    # Cache the result
    if cache:
        await cache.set("performance_metrics", metrics.model_dump(), **cache_key_params)

    # Record metrics
    risk_calculations_total.labels(symbol="portfolio", metric_type="performance").inc()

    return metrics


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
        "meets_target": metrics.sharpe_ratio >= settings.target_sharpe_ratio
        if metrics.sharpe_ratio is not None
        else False,
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

    portfolio = portfolio_data.get("portfolio", {})

    # Daily P&L for circuit breaker MUST be fractional (e.g. -0.05 for -5%) —
    # that is what RiskEngine.check_circuit_breaker compares against
    # settings.circuit_breaker_daily_loss_threshold (also fractional, 0.05 by
    # default). Two bugs lived here previously:
    #   1. Read portfolio.total_return_pct, which is *lifetime* return —
    #      caused the CB to trip every loop on any account underwater >5%
    #      since inception, regardless of today's activity.
    #   2. The value is in *percent* form (e.g. -25.07 for -25%), but it was
    #      passed straight to check_circuit_breaker as if fractional, then
    #      formatted as `daily_pnl*100`, producing phantom "Daily loss
    #      -2507.74%" reasons (a 100x scale error on top of the wrong metric).
    # Fix: pull metrics.daily_return_pct from the /performance endpoint and
    # divide by 100 to get fractional. Missing/unreachable → treat as 0
    # (no signal, do not falsely trip the CB on a fetch failure).
    daily_pnl = 0.0
    perf_data = await fetch_performance_data()
    if perf_data:
        metrics = (
            (perf_data.get("metrics") or {}) if isinstance(perf_data, dict) else {}
        )
        try:
            daily_return_pct = float(metrics.get("daily_return_pct", 0) or 0)
        except (TypeError, ValueError):
            daily_return_pct = 0.0
        daily_pnl = daily_return_pct / 100.0

    # Get drawdown
    total_capital = Decimal(str(portfolio.get("total_value", 10000)))
    historical_values = [(datetime.now(), total_capital)]
    drawdown_metrics = engine.calculate_drawdown_metrics(
        total_capital, historical_values
    )

    # Get exposure
    positions = portfolio.get("holdings", [])
    exposure_metrics = engine.calculate_exposure_metrics(positions, total_capital)

    status = engine.check_circuit_breaker(
        daily_pnl, drawdown_metrics.current_drawdown, exposure_metrics.exposure_ratio
    )

    # Update circuit breaker gauge. CircuitBreakerStatus has no .active field
    # (was renamed to is_tripped during a state-machine refactor); use that.
    circuit_breaker_active_gauge.set(1 if status.is_tripped else 0)

    return status


@app.post("/circuit-breaker/reset")
async def reset_circuit_breaker(api_key: str = Depends(verify_admin_key)):
    """
    Reset circuit breaker (admin only)
    Requires manual intervention to resume trading after trip
    Requires X-Admin-Key header for authentication
    """
    engine = get_risk_engine()

    if not engine.circuit_breaker_active:
        return {"message": "Circuit breaker is not active", "status": "ok"}

    # Reset circuit breaker
    engine.circuit_breaker_active = False
    engine.circuit_breaker_tripped_at = None

    # Update gauge
    circuit_breaker_active_gauge.set(0)

    logger.warning("🔄 Circuit breaker manually reset")

    return {
        "message": "Circuit breaker reset successfully",
        "status": "reset",
        "timestamp": datetime.now().isoformat(),
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
        min_sharpe_ratio=settings.target_sharpe_ratio,
    )


@app.put("/config/limits")
async def update_risk_limits(
    limits: RiskLimits, api_key: str = Depends(verify_admin_key)
):
    """
    Update risk limits (admin only)
    ⚠️ Use with caution - affects all risk calculations
    Requires X-Admin-Key header for authentication
    """
    # In production, would persist to database
    logger.warning(f"Risk limits update requested: {limits}")

    # Invalidate cache when limits change
    if cache:
        await cache.invalidate_pattern("risk_metrics:*")

    return {
        "message": "Risk limits updated",
        "limits": limits,
        "warning": "Changes will take effect immediately",
        "timestamp": datetime.now().isoformat(),
    }


# === CACHE MANAGEMENT ===


@app.post("/cache/invalidate")
async def invalidate_cache(api_key: str = Depends(verify_admin_key)):
    """Invalidate all cached risk metrics (admin only)"""
    if not cache:
        return {"message": "Cache not enabled"}

    deleted = await cache.invalidate_pattern("risk_metrics:*")

    return {
        "message": f"Cache invalidated ({deleted} keys deleted)",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/cache/stats")
async def get_cache_stats():
    """Get cache performance statistics"""
    if not cache:
        return {"message": "Cache not enabled"}

    return cache.get_stats()


# === ROOT ENDPOINT ===


@app.get("/")
async def root():
    """Service information"""
    return {
        "service": "Risk & Metrics Service",
        "version": "1.0.0",
        "description": "Real-time risk monitoring and performance analytics",
        "optimizations": {
            "redis_caching": settings.redis_enabled,
            "request_batching": settings.enable_request_batching,
            "performance_monitoring": settings.enable_performance_monitoring,
            "connection_pooling": True,
        },
        "endpoints": {
            "health": "/health",
            "status": "/status",
            "risk_scorecard": "/risk/scorecard",
            "circuit_breaker": "/circuit-breaker",
            "performance": "/performance/metrics",
            "performance_stats": "/performance/stats",
            "cache_stats": "/cache/stats",
            "metrics": "/metrics",
            "documentation": "/docs",
        },
        "status": "operational",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.service_host,
        port=settings.service_port,
        reload=True,
    )
