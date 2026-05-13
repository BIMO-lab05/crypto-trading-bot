"""
API Gateway - Main Application
Unified entry point for all microservices

SECURITY HARDENING: 2025-12-12
- Rate limiting with Redis backend
- Input validation for trading parameters
- Security headers (OWASP compliant)
- Strict CORS configuration

PROMETHEUS METRICS: 2025-12-12
- Added /metrics endpoint for Prometheus scraping
- HTTP request counters and histograms
- Active request gauge
"""

from fastapi import (
    FastAPI,
    Request,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    Depends,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from contextlib import asynccontextmanager
import logging
import time
import json
import asyncio
from typing import Optional, Set
from datetime import datetime

# Prometheus metrics imports
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from prometheus_client import multiprocess, CollectorRegistry
import os
from pathlib import Path
import tempfile

from app.config import settings
from app.services.service_proxy import ServiceProxy
from app.auth_models import (
    User,
    UserCreate,
    UserLogin,
    Token,
    create_user,
    authenticate_user,
    create_access_token,
)
from app.auth_middleware import (
    get_current_active_user,
    get_current_admin_user,
)

# Import security modules
from app.security.rate_limiter import (
    RateLimitConfig,
    get_rate_limiter,
    rate_limit_exceeded_handler,
)
from app.security.input_validation import (
    ValidationError,
    validate_symbol,
    validate_quantity,
    validate_price,
    validate_interval,
    validate_limit,
    ALLOWED_SYMBOLS,
)
from app.security.security_headers import (
    SecurityHeadersMiddleware,
    SecurityHeadersConfig,
    get_cors_config,
)
from slowapi.errors import RateLimitExceeded

# Configure logging
# Ensure logs directory exists before opening the file handler — pytest runs
# from various cwds (services/api-gateway/ in CI, repo root locally) so
# eagerly create it relative to wherever Python is started.
Path("logs").mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("logs/service.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# ============================================================================
# PROMETHEUS METRICS
# ============================================================================

# HTTP request counter - tracks total requests by method, endpoint, and status
http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status_code"]
)

# HTTP request duration histogram - tracks request latency distribution
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[
        0.005,
        0.01,
        0.025,
        0.05,
        0.075,
        0.1,
        0.25,
        0.5,
        0.75,
        1.0,
        2.5,
        5.0,
        7.5,
        10.0,
    ],
)

# Active requests gauge - tracks concurrent requests
http_requests_active = Gauge("http_requests_active", "Number of active HTTP requests")

# WebSocket connections gauge
websocket_connections_active = Gauge(
    "websocket_connections_active", "Number of active WebSocket connections"
)

# Backend service health gauge
backend_service_health = Gauge(
    "backend_service_health",
    "Backend service health status (1=healthy, 0=unhealthy)",
    ["service"],
)


# ============================================================================
# SECURITY CONFIGURATION
# ============================================================================

# Rate limiting configuration
rate_limit_config = RateLimitConfig(
    trading_limit=10,  # Trading endpoints: 10 req/min
    auth_limit=5,  # Auth endpoints: 5 req/min
    health_limit=60,  # Health checks: 60 req/min
    general_limit=30,  # General API: 30 req/min
    enabled=settings.rate_limit_enabled,
    redis_url=settings.redis_url if settings.rate_limit_enabled else None,
)

# Initialize rate limiter
rate_limiter = get_rate_limiter(rate_limit_config)

# Security headers configuration
security_headers_config = SecurityHeadersConfig(
    csp_enabled=True,
    frame_options="DENY",
    hsts_enabled=True,
    hsts_max_age=31536000,  # 1 year
)

# CORS configuration (strict - no wildcards in production)
cors_config = get_cors_config(additional_origins=settings.cors_origins)


# ============================================================================
# WebSocket Manager - Handles real-time client connections
# ============================================================================


class WebSocketManager:
    """Manages WebSocket connections and broadcasts updates to connected clients"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.broadcast_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket):
        """Accept and store new WebSocket connection"""
        await websocket.accept()
        self.active_connections.add(websocket)
        websocket_connections_active.set(len(self.active_connections))
        logger.info(
            f"WebSocket client connected. Total connections: {len(self.active_connections)}"
        )

    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        self.active_connections.discard(websocket)
        websocket_connections_active.set(len(self.active_connections))
        logger.info(
            f"WebSocket client disconnected. Total connections: {len(self.active_connections)}"
        )

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send message to specific client"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: dict):
        """Send message to all connected clients"""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                disconnected.add(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

    async def start_broadcasting(self, service_proxy: ServiceProxy):
        """Start periodic broadcasting of updates"""
        logger.info("Starting WebSocket broadcast task")
        while True:
            try:
                if len(self.active_connections) > 0:
                    # Fetch latest data from services
                    data = await self.fetch_dashboard_updates(service_proxy)
                    await self.broadcast(data)

                # Wait 2 seconds before next broadcast
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Error in broadcast task: {e}")
                await asyncio.sleep(5)

    async def fetch_dashboard_updates(self, service_proxy: ServiceProxy) -> dict:
        """Fetch latest data from all services"""
        try:
            # Health is computed locally by aggregating backend health
            # checks — we used to proxy to a non-existent "api-gateway"
            # service, which 404'd every 2s and spammed the logs. Fixed
            # 2026-05-01.
            health_task = service_proxy.aggregate_health_checks()
            portfolio_task = service_proxy.proxy_request(
                "portfolio-manager",
                "/api/v1/portfolio/balance",
                "GET",
            )

            health_resp, portfolio_resp = await asyncio.gather(
                health_task, portfolio_task, return_exceptions=True
            )

            # aggregate_health_checks returns dict[str, bool] directly,
            # not a JSONResponse — no decode step.
            health_data = (
                health_resp if not isinstance(health_resp, Exception) else None
            )

            portfolio_data = None
            if not isinstance(portfolio_resp, Exception):
                try:
                    portfolio_data = json.loads(portfolio_resp.body.decode())
                except Exception:
                    pass

            return {
                "type": "dashboard_update",
                "timestamp": datetime.now().isoformat(),
                "data": {"health": health_data, "portfolio": portfolio_data},
            }

        except Exception as e:
            logger.error(f"Error fetching dashboard updates: {e}")
            return {
                "type": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }


# Global instances
service_proxy: Optional[ServiceProxy] = None
websocket_manager = WebSocketManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management"""
    global service_proxy

    # Setup multiprocess metrics directory
    temp_dir = tempfile.mkdtemp(prefix="prometheus_multiproc_")
    os.environ["PROMETHEUS_MULTIPROC_DIR"] = temp_dir
    logger.info(f"Prometheus multiprocess directory: {temp_dir}")

    # Startup
    logger.info(f"Starting {settings.service_name} on port {settings.service_port}")
    logger.info(
        f"Rate limiting: {'enabled' if rate_limit_config.enabled else 'disabled'}"
    )
    logger.info("Security headers: enabled")
    logger.info("Prometheus metrics: enabled at /metrics")

    service_proxy = ServiceProxy()
    await service_proxy.initialize()

    # Start WebSocket broadcast task
    websocket_manager.broadcast_task = asyncio.create_task(
        websocket_manager.start_broadcasting(service_proxy)
    )

    logger.info("API Gateway ready (Security hardening enabled)")

    yield

    # Shutdown
    logger.info("Shutting down API Gateway")

    # Cleanup multiprocess metrics
    try:
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)
        if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
            del os.environ["PROMETHEUS_MULTIPROC_DIR"]
    except Exception as e:
        logger.error(f"Error cleaning up multiprocess metrics directory: {e}")

    # Stop WebSocket broadcast task
    if websocket_manager.broadcast_task:
        websocket_manager.broadcast_task.cancel()
        try:
            await websocket_manager.broadcast_task
        except asyncio.CancelledError:
            pass

    if service_proxy:
        await service_proxy.cleanup()


# Create FastAPI app
app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    lifespan=lifespan,
)


# ============================================================================
# PROMETHEUS METRICS MIDDLEWARE
# ============================================================================


@app.middleware("http")
async def prometheus_metrics_middleware(request: Request, call_next):
    """Middleware to collect Prometheus metrics for all HTTP requests"""
    # Skip metrics endpoint itself to avoid recursion
    if request.url.path == "/metrics":
        return await call_next(request)

    # Extract method and path
    method = request.method
    path = request.url.path

    # Normalize path to prevent high cardinality
    # Replace dynamic segments like UUIDs, symbols, etc.
    import re

    normalized_path = re.sub(
        r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "/{uuid}",
        path,
        flags=re.IGNORECASE,
    )
    normalized_path = re.sub(r"/[A-Z]+USDT", "/{symbol}", normalized_path)
    normalized_path = re.sub(r"/\d+", "/{id}", normalized_path)

    # Increment active requests
    http_requests_active.inc()

    # Start timer
    start_time = time.time()

    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        status_code = 500
        raise
    finally:
        # Calculate duration
        duration = time.time() - start_time

        # Decrement active requests
        http_requests_active.dec()

        # Record metrics
        http_requests_total.labels(
            method=method, endpoint=normalized_path, status_code=status_code
        ).inc()

        http_request_duration_seconds.labels(
            method=method, endpoint=normalized_path
        ).observe(duration)

    return response


# ============================================================================
# MIDDLEWARE CONFIGURATION (Order matters: last added = first executed)
# ============================================================================

# 1. Security Headers Middleware (applied to all responses)
app.add_middleware(SecurityHeadersMiddleware, config=security_headers_config)

# 2. CORS Middleware (strict configuration)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_config.allow_origins,
    allow_credentials=cors_config.allow_credentials,
    allow_methods=cors_config.allow_methods,
    allow_headers=cors_config.allow_headers,
    expose_headers=cors_config.expose_headers,
    max_age=cors_config.max_age,
)

# 3. Rate Limiting - Add middleware and exception handler
from app.security.rate_limiter import RateLimitMiddleware

if rate_limiter.enabled:
    app.state.limiter = rate_limiter.limiter
    app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


# ============================================================================
# EXCEPTION HANDLERS
# ============================================================================


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    """Handle validation errors with consistent JSON response."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, **exc.detail, "timestamp": int(time.time() * 1000)},
    )


def get_proxy() -> ServiceProxy:
    """Get service proxy instance"""
    if service_proxy is None:
        raise HTTPException(status_code=503, detail="Service proxy not initialized")
    return service_proxy


# ============================================================================
# PROMETHEUS METRICS ENDPOINT
# ============================================================================


def get_metrics_registry():
    """Get appropriate registry based on multiprocess environment"""
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return registry
    else:
        return None


@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint"""
    registry = get_metrics_registry()
    if registry:
        data = generate_latest(registry)
    else:
        data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


# ============================================================================
# ROOT & HEALTH ENDPOINTS
# ============================================================================


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "service": settings.service_name,
        "version": settings.api_version,
        "description": settings.api_description,
        "security": {
            "rate_limiting": rate_limit_config.enabled,
            "security_headers": True,
            "input_validation": True,
            "cors_strict": True,
        },
        "services": {
            "bybit_connector": settings.bybit_connector_url,
            "market_data": settings.market_data_url,
            "technical_analysis": settings.technical_analysis_url,
            "trading_engine": settings.trading_engine_url,
            "portfolio_manager": settings.portfolio_manager_url,
            "risk_metrics": settings.risk_metrics_url,
            "ml_prediction": settings.ml_prediction_url,
            "sentiment_analysis": settings.sentiment_analysis_url,
        },
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "docs": "/docs",
            "market_data": "/api/market/*",
            "technical_analysis": "/api/analysis/*",
            "trading": "/api/trading/*",
            "portfolio": "/api/portfolio/*",
            "risk": "/api/risk/*",
            "performance": "/api/performance/*",
            "ml_predictions": "/api/ml/*",
            "sentiment": "/api/sentiment/*",
        },
        "allowed_symbols": sorted(list(ALLOWED_SYMBOLS))[:20],
        "rate_limits": {
            "trading": f"{rate_limit_config.trading_limit}/minute",
            "auth": f"{rate_limit_config.auth_limit}/minute",
            "health": f"{rate_limit_config.health_limit}/minute",
            "general": f"{rate_limit_config.general_limit}/minute",
        },
    }


@app.get("/health")
async def health_check():
    """Gateway health check with backend service status"""
    proxy = get_proxy()

    # Check all backend services
    health_checks = await proxy.aggregate_health_checks()

    all_healthy = all(health_checks.values())

    # Update backend service health metrics
    for service_name, is_healthy in health_checks.items():
        backend_service_health.labels(service=service_name).set(1 if is_healthy else 0)

    return {
        "status": "healthy" if all_healthy else "degraded",
        "service": settings.service_name,
        "version": settings.api_version,
        "timestamp": int(time.time() * 1000),
        "security": {
            "rate_limiting": rate_limit_config.enabled,
            "security_headers": True,
        },
        "backend_services": {
            "bybit_connector": health_checks.get("bybit", False),
            "market_data": health_checks.get("market-data", False),
            "technical_analysis": health_checks.get("technical-analysis", False),
            "trading_engine": health_checks.get("trading-engine", False),
            "portfolio_manager": health_checks.get("portfolio-manager", False),
            "risk_metrics": health_checks.get("risk-metrics", False),
            "ml_prediction": health_checks.get("ml-prediction", False),
            "sentiment_analysis": health_checks.get("sentiment-analysis", False),
            "notification_service": True,  # Runs independently
        },
    }


# ============================================================================
# AUTHENTICATION ENDPOINTS (Rate Limited: 5/min)
# ============================================================================


@app.post("/auth/register", response_model=User, status_code=status.HTTP_201_CREATED)
# @rate_limiter.auth_limit  # Rate limited via middleware
async def register(user_create: UserCreate):
    """
    Register a new user

    Rate Limit: 5 requests/minute

    - **username**: Unique username (3-50 characters, alphanumeric)
    - **email**: Valid email address
    - **password**: Strong password (min 8 chars, uppercase, lowercase, digit)
    - **full_name**: Optional full name
    """
    try:
        user = create_user(user_create)
        logger.info(f"New user registered: {user.username}")
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/auth/login", response_model=Token)
# @rate_limiter.auth_limit  # Rate limited via middleware
async def login(user_login: UserLogin):
    """
    Login with username and password to receive JWT access token

    Rate Limit: 5 requests/minute (brute force protection)

    - **username**: Your username
    - **password**: Your password

    Returns JWT token to use in Authorization header: `Bearer <token>`
    """
    user = authenticate_user(user_login.username, user_login.password)

    if not user:
        # Log failed login attempt
        logger.warning(f"Failed login attempt for username: {user_login.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.user_id}
    )

    logger.info(f"User logged in: {user.username}")

    return Token(access_token=access_token)


@app.get("/auth/me", response_model=User)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """
    Get current authenticated user information

    Requires: Authorization header with Bearer token
    """
    return current_user


@app.post("/auth/logout")
async def logout(current_user: User = Depends(get_current_active_user)):
    """
    Logout current user

    Note: JWT tokens are stateless, so true logout requires token blacklisting
    which is not implemented in this basic version. Clients should delete their tokens.

    Requires: Authorization header with Bearer token
    """
    logger.info(f"User logged out: {current_user.username}")
    return {
        "message": "Successfully logged out",
        "detail": "Please delete your token on the client side",
    }


# ============================================================================
# MARKET DATA ROUTES (Rate Limited: 30/min)
# ============================================================================


@app.get("/api/market/ticker/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_ticker(symbol: str, request: Request):
    """
    Get ticker data for a symbol

    Rate Limit: 30 requests/minute

    Symbol must be in whitelist (BTCUSDT, ETHUSDT, etc.)
    """
    # Validate symbol
    validated_symbol = validate_symbol(symbol)

    proxy = get_proxy()
    response_obj = await proxy.proxy_request(
        service_name="market-data",
        path=f"/api/v1/ticker/{validated_symbol}",
        method="GET",
    )

    # Extract the actual data from JSONResponse
    response_body = (
        response_obj.body.decode() if hasattr(response_obj, "body") else response_obj
    )
    response = (
        json.loads(response_body) if isinstance(response_body, str) else response_body
    )

    # Transform response format for frontend compatibility
    if isinstance(response, dict) and response.get("success") and response.get("data"):
        ticker_data = response["data"]
        return {
            "ticker": {
                "symbol": ticker_data.get("symbol"),
                "last_price": float(ticker_data.get("last_price", 0)),
                "price_24h_pcnt": float(ticker_data.get("price_change_24h", 0)),
                "volume_24h": float(ticker_data.get("volume_24h", 0)),
                "high_price_24h": float(ticker_data.get("high_24h", 0)),
                "low_price_24h": float(ticker_data.get("low_24h", 0)),
            }
        }

    return response


@app.get("/api/market/kline/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_kline(symbol: str, interval: str = "60", limit: int = 100):
    """
    Get kline/candlestick data

    Rate Limit: 30 requests/minute

    Args:
        symbol: Trading symbol (must be in whitelist)
        interval: Candlestick interval (1, 5, 15, 60, 240, D)
        limit: Number of candles (max 1000)
    """
    # Validate inputs
    validated_symbol = validate_symbol(symbol)
    validated_interval = validate_interval(interval)
    validated_limit = validate_limit(limit, max_limit=1000)

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="market-data",
        path=f"/api/v1/klines/{validated_symbol}",
        method="GET",
        query_params={"interval": validated_interval, "limit": validated_limit},
    )


@app.get("/api/market/klines/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_klines_plural(symbol: str, interval: str = "60", limit: int = 100):
    """Get kline/candlestick data (plural alias for compatibility)"""
    validated_symbol = validate_symbol(symbol)
    validated_interval = validate_interval(interval)
    validated_limit = validate_limit(limit, max_limit=1000)

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="market-data",
        path=f"/api/v1/klines/{validated_symbol}",
        method="GET",
        query_params={"interval": validated_interval, "limit": validated_limit},
    )


# ============================================================================
# TECHNICAL ANALYSIS ROUTES (Rate Limited: 30/min)
# ============================================================================


@app.get("/api/analysis/rsi/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_rsi(symbol: str, interval: str = "60", period: int = 14):
    """Get RSI indicator"""
    validated_symbol = validate_symbol(symbol)
    validated_interval = validate_interval(interval)

    if period < 2 or period > 100:
        raise ValidationError(
            field="period", message="Period must be between 2 and 100", value=period
        )

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="technical-analysis",
        path=f"/api/v1/indicators/rsi/{validated_symbol}",
        method="GET",
        query_params={"interval": validated_interval, "period": period},
    )


@app.get("/api/analysis/macd/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_macd(symbol: str, interval: str = "60"):
    """Get MACD indicator"""
    validated_symbol = validate_symbol(symbol)
    validated_interval = validate_interval(interval)

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="technical-analysis",
        path=f"/api/v1/indicators/macd/{validated_symbol}",
        method="GET",
        query_params={"interval": validated_interval},
    )


@app.get("/api/analysis/all/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_all_indicators(symbol: str, interval: str = "60"):
    """Get all technical indicators"""
    validated_symbol = validate_symbol(symbol)
    validated_interval = validate_interval(interval)

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="technical-analysis",
        path=f"/api/v1/analysis/{validated_symbol}",
        method="GET",
        query_params={"interval": validated_interval},
    )


# ============================================================================
# TRADING ENGINE ROUTES (Rate Limited: 10/min for trading operations)
# ============================================================================


@app.get("/api/trading/signals/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_trading_signal(symbol: str, interval: str = "60"):
    """Get aggregated trading signal"""
    validated_symbol = validate_symbol(symbol)
    validated_interval = validate_interval(interval)

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine",
        path=f"/api/v1/signals/{validated_symbol}",
        method="GET",
        query_params={"interval": validated_interval},
    )


@app.get("/api/trading/signals/enhanced/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_enhanced_trading_signal(symbol: str, interval: str = "60"):
    """
    Get enhanced trading signal combining multiple data sources

    Combines:
    - Technical Analysis (RSI, MACD, Bollinger Bands, etc.)
    - ML Predictions (price trend, volatility)
    - Multi-timeframe confirmation
    - Risk metrics
    """
    validated_symbol = validate_symbol(symbol)
    validated_interval = validate_interval(interval)

    proxy = get_proxy()

    try:
        # Fetch data from multiple services in parallel
        ta_task = proxy.proxy_request(
            "technical-analysis",
            f"/api/v1/indicators/signal/{validated_symbol}",
            "GET",
            {"interval": validated_interval},
        )

        ml_task = proxy.proxy_request(
            "ml-prediction",
            f"/api/v1/predict/trend/{validated_symbol}",
            "GET",
            {"interval": validated_interval},
        )

        mtf_task = proxy.proxy_request(
            "technical-analysis",
            f"/api/v1/analysis/multi-timeframe/{validated_symbol}",
            "GET",
        )

        signal_task = proxy.proxy_request(
            "trading-engine",
            f"/api/v1/signals/{validated_symbol}",
            "GET",
            {"interval": validated_interval},
        )

        ta_resp, ml_resp, mtf_resp, signal_resp = await asyncio.gather(
            ta_task,
            ml_task,
            mtf_task,
            signal_task,
            return_exceptions=True,
        )

        def parse_response(resp):
            if isinstance(resp, Exception):
                return None
            try:
                return json.loads(resp.body.decode())
            except:
                return None

        ta_data = parse_response(ta_resp)
        ml_data = parse_response(ml_resp)
        mtf_data = parse_response(mtf_resp)
        signal_data = parse_response(signal_resp)

        # Calculate enhanced signal
        signals = []
        if ta_data and ta_data.get("aggregated_signal"):
            signals.append(ta_data["aggregated_signal"])
        if ml_data and ml_data.get("trend"):
            signals.append(ml_data["trend"])
        if mtf_data and mtf_data.get("consensus_signal"):
            signals.append(mtf_data["consensus_signal"])
        if signal_data and signal_data.get("signal"):
            signals.append(signal_data["signal"])

        # Determine consensus
        buy_count = sum(1 for s in signals if s in ["BUY", "BULLISH"])
        sell_count = sum(1 for s in signals if s in ["SELL", "BEARISH"])
        neutral_count = sum(1 for s in signals if s in ["HOLD", "NEUTRAL", "SIDEWAYS"])

        total_signals = len(signals)
        if total_signals == 0:
            enhanced_signal = "HOLD"
            confidence = 0.0
        elif buy_count > sell_count and buy_count > neutral_count:
            enhanced_signal = "BUY"
            confidence = buy_count / total_signals
        elif sell_count > buy_count and sell_count > neutral_count:
            enhanced_signal = "SELL"
            confidence = sell_count / total_signals
        else:
            enhanced_signal = "HOLD"
            confidence = neutral_count / total_signals if neutral_count > 0 else 0.5

        risk_level = "LOW"
        if confidence < 0.5:
            risk_level = "HIGH"
        elif confidence < 0.7:
            risk_level = "MEDIUM"

        if enhanced_signal == "BUY" and confidence >= 0.7:
            recommendation = f"Strong buy signal with {confidence:.0%} confidence across multiple indicators"
        elif enhanced_signal == "SELL" and confidence >= 0.7:
            recommendation = f"Strong sell signal with {confidence:.0%} confidence across multiple indicators"
        elif confidence >= 0.5:
            recommendation = f"Moderate {enhanced_signal.lower()} signal with {confidence:.0%} confidence"
        else:
            recommendation = f"Weak {enhanced_signal.lower()} signal - conflicting indicators suggest caution"

        return JSONResponse(
            content={
                "symbol": validated_symbol,
                "interval": validated_interval,
                "signal": enhanced_signal,
                "confidence": round(confidence, 2),
                "risk_level": risk_level,
                "signal_breakdown": {
                    "buy_signals": buy_count,
                    "sell_signals": sell_count,
                    "neutral_signals": neutral_count,
                    "total_signals": total_signals,
                },
                "technical_analysis": ta_data,
                "ml_predictions": ml_data,
                "multi_timeframe": mtf_data,
                "base_signal": signal_data,
                "recommendation": recommendation,
                "timestamp": int(time.time() * 1000),
            }
        )

    except Exception as e:
        # Don't echo `str(e)` to clients — it leaks internal structure
        # (stack traces, SQL fragments, downstream URLs). Log with
        # detail; respond with a generic message.
        logger.error(f"Error generating enhanced signal: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to generate enhanced signal",
        )


@app.post("/api/trading/signals/{symbol}/analyze")
# @rate_limiter.trading_limit  # Rate limited via middleware
async def analyze_and_trade(symbol: str, interval: str = "60", execute: bool = False):
    """
    Analyze signal and optionally execute trade

    Rate Limit: 10 requests/minute (trading operation)
    """
    validated_symbol = validate_symbol(symbol)
    validated_interval = validate_interval(interval)

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine",
        path=f"/api/v1/signals/{validated_symbol}/analyze",
        method="POST",
        query_params={"interval": validated_interval, "execute": execute},
    )


@app.get("/api/trading/positions")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_positions(status: str = "open"):
    """Get trading positions"""
    if status not in {"open", "closed", "all"}:
        raise ValidationError(
            field="status",
            message="Status must be 'open', 'closed', or 'all'",
            value=status,
            allowed_values=["open", "closed", "all"],
        )

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine",
        path="/api/v1/positions",
        method="GET",
        query_params={"status": status},
    )


@app.get("/api/trading/status")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_trading_status():
    """Get trading bot status"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine", path="/api/v1/trading/status", method="GET"
    )


@app.get("/api/config/safety-state")
async def get_safety_state():
    """
    Aggregated safety posture for the dashboard StatusBar (DASH-03 / Plan 06-02).

    Returns the D-08 schema in a single fan-out call so the frontend does
    NOT have to stitch multiple endpoints. The dashboard polls this every
    5s (per D-04 + the polling cadence in Plan 06-04).

    Ownership split (D-09 / D-10):
    - api-gateway reads its own env for trading_mode / paper_trading_mode /
      ml_predictions_enabled (F-04 wired these into the compose env block).
    - Proxies to trading-engine for auto_trading_enabled + emergency_stop
      (D-10: only trading-engine reads the EMERGENCY_STOP bind-mount file).
    - Proxies to trading-engine for kill_switch state (D-04: 5% daily-loss
      circuit-breaker state lives in the risk-budget manager).

    Unauthenticated (D-09): read-only config disclosure. No secrets, no
    balances, no positions. Threat T-06-02-01 explicitly accepted.

    Graceful degradation: if trading-engine is unreachable, the response is
    still 200 with safe defaults (auto_trading_enabled=False,
    emergency_stop={active:False, mtime:None}, kill_switch fields zeroed
    and daily_loss_armed=False). The dashboard surfaces "trading-engine
    down" via these defaults; we never 500.

    F-01 fix: kill_switch.tripped reads the FLAT bool te_budget["emergency_mode"]
    (handler at services/trading-engine/app/handlers/risk_budget.py:50
    declares `emergency_mode: bool`). daily_loss_armed is sourced from
    te_budget reachability (bool(te_budget)). PATTERNS.md line 379 had the
    WRONG dict-walk on emergency_mode.armed — superseded here.

    F-03 fix: proxy_request returns a fastapi.responses.JSONResponse, NOT
    a dict. Calling .get() on it raises AttributeError. We decode the body
    via json.loads(resp.body.decode()) — same pattern as portfolio_resp at
    main.py:271.

    Deferred (Phase 7): live_trading_acknowledged flag tracking
    LIVE_TRADING_ACK env var. Not in D-08 schema; without it an operator
    could see TRADING_MODE=LIVE pill while trading-engine refuses to boot.
    """
    proxy = get_proxy()

    # --- Proxy to trading-engine /status ----------------------------------
    te_status: dict = {}
    try:
        te_status_resp = await proxy.proxy_request(
            service_name="trading-engine", path="/status", method="GET"
        )
        if getattr(te_status_resp, "status_code", 500) == 200:
            te_status = json.loads(te_status_resp.body.decode())
    except Exception as e:
        logger.warning(
            f"/api/config/safety-state: trading-engine /status proxy failed: {e}"
        )
        te_status = {}

    # --- Proxy to trading-engine /api/v1/risk/budget/current --------------
    te_budget: dict = {}
    try:
        te_budget_resp = await proxy.proxy_request(
            service_name="trading-engine",
            path="/api/v1/risk/budget/current",
            method="GET",
        )
        if getattr(te_budget_resp, "status_code", 500) == 200:
            te_budget = json.loads(te_budget_resp.body.decode())
    except Exception as e:
        logger.warning(
            f"/api/config/safety-state: trading-engine /api/v1/risk/budget/current proxy failed: {e}"
        )
        te_budget = {}

    # --- Local env reads (F-04 wired these into compose) ------------------
    trading_mode = os.getenv("TRADING_MODE", "PAPER").upper()
    paper_trading_mode = os.getenv("PAPER_TRADING_MODE", "true").lower() == "true"
    ml_predictions_enabled = (
        os.getenv("ENABLE_ML_PREDICTIONS", "false").lower() == "true"
    )

    # --- emergency_stop sub-dict from te_status ---------------------------
    es_raw = te_status.get("emergency_stop") or {}
    emergency_stop = {
        "active": bool(es_raw.get("active", False)),
        "mtime": es_raw.get("mtime"),  # ISO string or None (Plan 06-02 Task 1)
    }

    # --- kill_switch derivation (F-01 fix) --------------------------------
    # daily_loss_armed = bool(te_budget) — True iff te_budget is a non-empty
    # dict (proxy reachable AND backend returned a populated payload).
    # When trading-engine is unreachable or returns {}, this is False — the
    # dashboard renders a "kill-switch state unknown" pill.
    # tripped = bool(te_budget["emergency_mode"]) — flat bool read; this is
    # the canonical wire shape (handler at risk_budget.py:50).
    kill_switch = {
        "daily_loss_armed": bool(te_budget),
        "daily_pnl_pct": float(
            te_budget.get("utilization", {}).get("daily_pnl_pct", 0.0)
        ),
        "tripped": bool(te_budget.get("emergency_mode", False)),
    }

    # Local import: autoflake removes unused top-level imports across
    # api-gateway/main.py refactors. Importing inside the function pins
    # the use site and survives the autoflake pass (project memory:
    # feedback_main_imports_autoflake.md).
    from datetime import timezone as _tz

    return {
        "trading_mode": trading_mode,
        "paper_trading_mode": paper_trading_mode,
        "auto_trading_enabled": bool(te_status.get("auto_trading_enabled", False)),
        "emergency_stop": emergency_stop,
        "ml_predictions_enabled": ml_predictions_enabled,
        "kill_switch": kill_switch,
        "last_updated_at": datetime.now(_tz.utc).isoformat(),
    }


@app.get("/api/trading/performance")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_trading_performance():
    """Get trading performance metrics from trading-engine"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine", path="/api/v1/performance", method="GET"
    )


# Auto-trader control routes — proxied to trading-engine's
# /api/v1/trading/{start,stop}. The frontend's autoTraderAPI calls
# these via the gateway in production; in dev the Vite proxy rewrites
# `/api/trading` → `/api/v1/trading` directly to port 8005, so the
# absence of these gateway routes only manifests in prod (404).
# Added 2026-05-01.
@app.post("/api/trading/start")
async def start_auto_trading():
    """Start the trading-engine auto-trader."""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine",
        path="/api/v1/trading/start",
        method="POST",
    )


@app.post("/api/trading/stop")
async def stop_auto_trading():
    """Stop the trading-engine auto-trader."""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine",
        path="/api/v1/trading/stop",
        method="POST",
    )


@app.get("/api/trading/trades/history")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_trading_trades_history(limit: int = 50):
    """
    Get closed trades history from trading-engine database

    Args:
        limit: Maximum number of trades to return (default 50, max 1000)
    """
    validated_limit = validate_limit(limit, max_limit=1000)

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine",
        path="/api/v1/trades/history",
        method="GET",
        query_params={"limit": validated_limit},
    )


# ============================================================================
# PERFORMANCE DASHBOARD ENDPOINTS — proxy to trading-engine
# /api/v1/trading/* (handlers/performance_dashboard.py, Phase 5.3)
#
# These routes were what the frontend's analyticsAPI expected; the
# downstream handlers existed but the router wasn't mounted in
# trading-engine main.py. Both fixes ship 2026-05-01.
# ============================================================================

_VALID_PERIODS = {"1d", "7d", "30d", "90d", "all"}


def _validate_period(period: str) -> str:
    if period not in _VALID_PERIODS:
        raise ValidationError(
            field="period",
            message=f"period must be one of {sorted(_VALID_PERIODS)}",
            value=period,
        )
    return period


@app.get("/api/trading/equity-curve")
async def get_trading_equity_curve(period: str = "30d", interval: str = "1h"):
    """Equity curve points for the Performance dashboard chart."""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine",
        path="/api/v1/trading/equity-curve",
        method="GET",
        query_params={"period": _validate_period(period), "interval": interval},
    )


@app.get("/api/trading/drawdown")
async def get_trading_drawdown(period: str = "30d"):
    """Drawdown series (peak-to-trough) for the Performance dashboard."""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine",
        path="/api/v1/trading/drawdown",
        method="GET",
        query_params={"period": _validate_period(period)},
    )


@app.get("/api/trading/returns-distribution")
async def get_trading_returns_distribution(period: str = "30d", bins: int = 20):
    """Returns histogram + summary stats (mean/std/skew/kurt)."""
    if not (5 <= bins <= 100):
        raise ValidationError(
            field="bins", message="bins must be in [5, 100]", value=bins
        )
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine",
        path="/api/v1/trading/returns-distribution",
        method="GET",
        query_params={"period": _validate_period(period), "bins": bins},
    )


@app.get("/api/trading/correlations")
async def get_trading_correlations(period: str = "30d", symbols: str | None = None):
    """Asset return correlation matrix. ``symbols`` is a comma-separated list."""
    qp = {"period": _validate_period(period)}
    if symbols:
        # Light validation: comma-separated, alnum + USDT pattern enforced by
        # the downstream service's input_validation. Defend against absurd
        # length here so we don't proxy a megabyte query string.
        if len(symbols) > 512:
            raise ValidationError(
                field="symbols", message="symbols list too long", value=len(symbols)
            )
        qp["symbols"] = symbols
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine",
        path="/api/v1/trading/correlations",
        method="GET",
        query_params=qp,
    )


@app.get("/api/trading/statistics")
async def get_trading_statistics(period: str = "30d", symbol: str | None = None):
    """Detailed trade statistics (win rate, profit factor, expectancy, ...)."""
    qp = {"period": _validate_period(period)}
    if symbol:
        qp["symbol"] = symbol
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine",
        path="/api/v1/trading/statistics",
        method="GET",
        query_params=qp,
    )


# ============================================================================
# PHASE 1 MONITORING ENDPOINTS
# ============================================================================


@app.get("/api/trading/phase1/metrics")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_phase1_metrics(hours: int = 24):
    """Get Phase 1 performance metrics"""
    if hours < 1 or hours > 8760:  # Max 1 year
        raise ValidationError(
            field="hours", message="Hours must be between 1 and 8760", value=hours
        )

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine",
        path="/api/v1/phase1/metrics",
        method="GET",
        query_params={"hours": hours},
    )


@app.get("/api/trading/phase1/health")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_phase1_health():
    """Get Phase 1 system health status"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine", path="/api/v1/phase1/health", method="GET"
    )


@app.get("/api/trading/phase1/latest")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_phase1_latest():
    """Get the most recent Phase 1 signal"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine", path="/api/v1/phase1/latest", method="GET"
    )


# ============================================================================
# PORTFOLIO MANAGER ROUTES (Rate Limited: 10/min for buy/sell)
# ============================================================================


@app.get("/api/portfolio")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_portfolio(portfolio_id: str = "default"):
    """Get portfolio details"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/portfolio",
        method="GET",
        query_params={"portfolio_id": portfolio_id},
    )


@app.get("/api/portfolio/balance")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_balance(portfolio_id: str = "default"):
    """Get portfolio balance"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/portfolio/balance",
        method="GET",
        query_params={"portfolio_id": portfolio_id},
    )


@app.get("/api/portfolio/holdings")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_holdings(portfolio_id: str = "default"):
    """Get portfolio holdings"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/portfolio/holdings",
        method="GET",
        query_params={"portfolio_id": portfolio_id},
    )


@app.get("/api/portfolio/performance")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_performance(portfolio_id: str = "default"):
    """Get performance metrics"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/performance",
        method="GET",
        query_params={"portfolio_id": portfolio_id},
    )


@app.get("/api/portfolio/trades")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_trades(
    portfolio_id: str = "default", limit: int = None, symbol: str = None
):
    """Get transaction history (trades)"""
    query_params = {"portfolio_id": portfolio_id}

    if limit:
        query_params["limit"] = validate_limit(limit)

    if symbol:
        query_params["symbol"] = validate_symbol(symbol)

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/transactions",
        method="GET",
        query_params=query_params,
    )


@app.post("/api/portfolio/buy")
# @rate_limiter.trading_limit  # Rate limited via middleware
async def buy_asset(
    symbol: str,
    quantity: str,
    price: str,
    portfolio_id: str = "default",
):
    """
    Execute buy transaction

    Rate Limit: 10 requests/minute (trading operation)

    Args:
        symbol: Trading symbol (required, must be in whitelist)
        quantity: Amount to buy (0.0001 - 1,000,000)
        price: Price per unit ($0.00000001 - $1,000,000)

    NOTE: symbol/quantity/price are now required (no defaulting to
    None). Previously `validate_X(x) if x else None` let callers omit
    fields entirely and skip validation, then proxy a request with
    `None` query params. Fixed 2026-05-01.
    """
    validated_symbol = validate_symbol(symbol)
    validated_quantity = str(validate_quantity(quantity))
    validated_price = str(validate_price(price))

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/transaction/buy",
        method="POST",
        query_params={
            "portfolio_id": portfolio_id,
            "symbol": validated_symbol,
            "quantity": validated_quantity,
            "price": validated_price,
        },
    )


@app.post("/api/portfolio/sell")
# @rate_limiter.trading_limit  # Rate limited via middleware
async def sell_asset(
    symbol: str,
    quantity: str,
    price: str,
    portfolio_id: str = "default",
):
    """
    Execute sell transaction

    Rate Limit: 10 requests/minute (trading operation)

    See buy_asset for note on previously-bypassable validation.
    """
    validated_symbol = validate_symbol(symbol)
    validated_quantity = str(validate_quantity(quantity))
    validated_price = str(validate_price(price))

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/transaction/sell",
        method="POST",
        query_params={
            "portfolio_id": portfolio_id,
            "symbol": validated_symbol,
            "quantity": validated_quantity,
            "price": validated_price,
        },
    )


@app.post("/api/portfolio/emergency-stop")
# @rate_limiter.trading_limit  # Rate limited via middleware
async def emergency_stop(current_user: User = Depends(get_current_admin_user)):
    """
    Emergency stop — write the EMERGENCY_STOP file the trading-engine watches.

    Admin-only. Writes to EMERGENCY_STOP_FILE (default `/app/EMERGENCY_STOP`,
    matching the trading-engine setting). Bind-mount in compose puts the
    same host file in front of both containers; trading-engine sees it
    read-only at the same path and refuses to start / halts the loop on
    next iteration.

    Rate Limit: 10 requests/minute (trading operation)
    """
    stop_file = Path(os.getenv("EMERGENCY_STOP_FILE", "/app/EMERGENCY_STOP"))
    activated_at_ms = int(time.time() * 1000)

    if stop_file.is_dir():
        # WSL bind-mount edge case: if `./EMERGENCY_STOP` doesn't exist on
        # the host, Docker creates a directory at the mount point. We
        # cannot write the file in this state. Operator must touch the
        # host file (or remove the bogus directory) once.
        logger.error(
            f"Cannot activate emergency stop: {stop_file} is a directory "
            f"(missing host file before docker compose up)."
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "EMERGENCY_STOP path is a directory inside the container — "
                "likely the host file did not exist when the bind-mount was "
                "created. Touch the host file and restart api-gateway."
            ),
        )

    try:
        stop_file.parent.mkdir(parents=True, exist_ok=True)
        stop_file.write_text(
            f"Emergency stop activated at {activated_at_ms} "
            f"by {current_user.username}\n"
        )
    except OSError as e:
        logger.error(f"Failed to write {stop_file}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to activate emergency stop",
        )

    logger.warning(f"EMERGENCY STOP ACTIVATED by {current_user.username} → {stop_file}")
    return JSONResponse(
        content={
            "success": True,
            "message": "Emergency stop activated. Trading bot will halt operations.",
            "timestamp": activated_at_ms,
            "stop_file": str(stop_file),
            "activated_by": current_user.username,
        }
    )


# ============================================================================
# RISK & METRICS ENDPOINTS
# ============================================================================


@app.get("/api/risk/scorecard")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_risk_scorecard():
    """Get complete risk assessment scorecard"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics", path="/risk/scorecard", method="GET"
    )


@app.get("/api/risk/capital")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_capital_metrics():
    """Get capital allocation metrics"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics", path="/risk/capital", method="GET"
    )


@app.get("/api/risk/exposure")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_exposure_metrics():
    """Get portfolio exposure analysis"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics", path="/risk/exposure", method="GET"
    )


@app.get("/api/risk/drawdown")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_drawdown_metrics():
    """Get drawdown tracking metrics"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics", path="/risk/drawdown", method="GET"
    )


@app.get("/api/risk/var")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_value_at_risk(confidence_level: float = 0.95, time_horizon_days: int = 1):
    """Get Value at Risk calculation"""
    if confidence_level < 0.9 or confidence_level > 0.99:
        raise ValidationError(
            field="confidence_level",
            message="Confidence level must be between 0.9 and 0.99",
            value=confidence_level,
        )

    if time_horizon_days < 1 or time_horizon_days > 365:
        raise ValidationError(
            field="time_horizon_days",
            message="Time horizon must be between 1 and 365 days",
            value=time_horizon_days,
        )

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/risk/var",
        method="GET",
        query_params={
            "confidence_level": confidence_level,
            "time_horizon_days": time_horizon_days,
        },
    )


@app.get("/api/performance/metrics")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_performance_metrics():
    """Get comprehensive performance metrics"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics", path="/performance/metrics", method="GET"
    )


@app.get("/api/performance/sharpe")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_sharpe_ratio():
    """Get Sharpe ratio calculation"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics", path="/performance/sharpe", method="GET"
    )


@app.get("/api/risk/alerts")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_active_alerts():
    """Get active risk alerts"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics", path="/alerts", method="GET"
    )


@app.get("/api/risk/circuit-breaker")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_circuit_breaker_status():
    """Get circuit breaker status"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics", path="/circuit-breaker", method="GET"
    )


@app.post("/api/risk/circuit-breaker/reset")
# @rate_limiter.trading_limit  # Rate limited via middleware
async def reset_circuit_breaker():
    """Reset circuit breaker (admin only)"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics", path="/circuit-breaker/reset", method="POST"
    )


# ============================================================================
# ML PREDICTION ENDPOINTS
# ============================================================================


@app.get("/api/ml/predict/price/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def ml_predict_price(symbol: str, interval: str = "60", model_type: str = "GRU"):
    """Get ML-based price predictions for a symbol. LSTM removed late 2025; GRU only."""
    validated_symbol = validate_symbol(symbol)
    validated_interval = validate_interval(interval)

    if model_type not in {"GRU"}:
        raise ValidationError(
            field="model_type",
            message="Model type must be 'GRU' (LSTM no longer supported)",
            value=model_type,
            allowed_values=["GRU"],
        )

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="ml-prediction",
        path=f"/api/v1/predict/price/{validated_symbol}",
        method="GET",
        query_params={"interval": validated_interval, "model_type": model_type},
    )


@app.get("/api/ml/predict/trend/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def ml_predict_trend(symbol: str, interval: str = "60", model_type: str = "GRU"):
    """Get ML-based trend prediction (BULLISH/BEARISH/NEUTRAL)"""
    validated_symbol = validate_symbol(symbol)
    validated_interval = validate_interval(interval)

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="ml-prediction",
        path=f"/api/v1/predict/trend/{validated_symbol}",
        method="GET",
        query_params={"interval": validated_interval, "model_type": model_type},
    )


@app.get("/api/ml/predict/volatility/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def ml_predict_volatility(symbol: str, interval: str = "60"):
    """Get volatility forecast for risk management"""
    validated_symbol = validate_symbol(symbol)
    validated_interval = validate_interval(interval)

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="ml-prediction",
        path=f"/api/v1/predict/volatility/{validated_symbol}",
        method="GET",
        query_params={"interval": validated_interval},
    )


@app.get("/api/ml/predict/signal/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def ml_predict_signal(symbol: str, interval: str = "60", model_type: str = "GRU"):
    """Get ML-based trading signal"""
    validated_symbol = validate_symbol(symbol)
    validated_interval = validate_interval(interval)

    proxy = get_proxy()

    try:
        prediction_response = await proxy.proxy_request(
            service_name="ml-prediction",
            path=f"/api/v1/predict/price/{validated_symbol}",
            method="GET",
            query_params={"interval": validated_interval, "model_type": model_type},
        )

        prediction_data = json.loads(prediction_response.body.decode())

        predicted_direction = prediction_data.get("predicted_direction", "SIDEWAYS")
        directional_strength = prediction_data.get("directional_strength", 0.0)

        if predicted_direction == "UP" and directional_strength > 0.6:
            signal = "BUY"
        elif predicted_direction == "DOWN" and directional_strength > 0.6:
            signal = "SELL"
        else:
            signal = "HOLD"

        return JSONResponse(
            content={
                "symbol": validated_symbol,
                "interval": validated_interval,
                "signal": signal,
                "confidence": directional_strength,
                "model_type": model_type,
                "prediction_data": prediction_data,
                "timestamp": int(time.time() * 1000),
            }
        )

    except Exception as e:
        logger.error(f"Error generating ML signal: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to generate ML signal",
        )


@app.get("/api/ml/models")
# @rate_limiter.general_limit  # Rate limited via middleware
async def list_ml_models():
    """List all available trained ML models"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="ml-prediction", path="/api/v1/models", method="GET"
    )


@app.get("/api/ml/models/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_ml_model_info(
    symbol: str, interval: str = "60", model_type: str = "LSTM"
):
    """Get detailed information about a specific ML model"""
    validated_symbol = validate_symbol(symbol)
    validated_interval = validate_interval(interval)

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="ml-prediction",
        path=f"/api/v1/models/{validated_symbol}",
        method="GET",
        query_params={"interval": validated_interval, "model_type": model_type},
    )


@app.post("/api/ml/models/train")
# @rate_limiter.trading_limit  # Rate limited via middleware
async def train_ml_model(
    symbol: str,
    interval: str = "60",
    lookback_days: int = 90,
    force_retrain: bool = False,
):
    """Train or retrain an ML model (long-running operation)"""
    validated_symbol = validate_symbol(symbol)
    validated_interval = validate_interval(interval)

    if lookback_days < 30 or lookback_days > 365:
        raise ValidationError(
            field="lookback_days",
            message="Lookback days must be between 30 and 365",
            value=lookback_days,
        )

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="ml-prediction",
        path="/api/v1/models/train",
        method="POST",
        body={
            "symbol": validated_symbol,
            "interval": validated_interval,
            "lookback_days": lookback_days,
            "force_retrain": force_retrain,
        },
    )


@app.get("/api/ml/models/compare/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def compare_ml_models(symbol: str, interval: str = "60"):
    """Compare LSTM vs GRU model performance"""
    validated_symbol = validate_symbol(symbol)
    validated_interval = validate_interval(interval)

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="ml-prediction",
        path=f"/api/v1/models/compare/{validated_symbol}",
        method="GET",
        query_params={"interval": validated_interval},
    )


# ============================================================================
# SENTIMENT ANALYSIS ENDPOINTS
# ============================================================================


@app.get("/api/sentiment/news/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_news_sentiment(symbol: str):
    """Get news sentiment analysis for a symbol"""
    validated_symbol = validate_symbol(symbol)

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="sentiment-analysis",
        path=f"/api/v1/sentiment/news/{validated_symbol}",
        method="GET",
    )


@app.get("/api/sentiment/social/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_social_sentiment(symbol: str):
    """Get social media sentiment analysis for a symbol"""
    validated_symbol = validate_symbol(symbol)

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="sentiment-analysis",
        path=f"/api/v1/sentiment/social/{validated_symbol}",
        method="GET",
    )


@app.get("/api/sentiment/combined/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_combined_sentiment(symbol: str):
    """Get combined sentiment analysis from all sources"""
    validated_symbol = validate_symbol(symbol)

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="sentiment-analysis",
        path=f"/api/v1/sentiment/combined/{validated_symbol}",
        method="GET",
    )


@app.get("/api/sentiment/trend/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_sentiment_trend(symbol: str, hours: int = 24):
    """Get sentiment trend over time for a symbol"""
    validated_symbol = validate_symbol(symbol)

    if hours < 1 or hours > 720:  # Max 30 days
        raise ValidationError(
            field="hours", message="Hours must be between 1 and 720", value=hours
        )

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="sentiment-analysis",
        path=f"/api/v1/sentiment/trend/{validated_symbol}",
        method="GET",
        query_params={"hours": hours},
    )


# ============================================================================
# MULTI-TIMEFRAME ANALYSIS ENDPOINTS
# ============================================================================


@app.get("/api/analysis/multi-timeframe/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_multi_timeframe_analysis(symbol: str):
    """Get multi-timeframe technical analysis for a symbol"""
    validated_symbol = validate_symbol(symbol)

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="technical-analysis",
        path=f"/api/v1/analysis/multi-timeframe/{validated_symbol}",
        method="GET",
    )


@app.get("/api/analysis/indicators/signal/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_indicator_signal(symbol: str, interval: str = "60"):
    """Get aggregated signal from all technical indicators"""
    validated_symbol = validate_symbol(symbol)
    validated_interval = validate_interval(interval)

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="technical-analysis",
        path=f"/api/v1/indicators/signal/{validated_symbol}",
        method="GET",
        query_params={"interval": validated_interval},
    )


# Order matters here: FastAPI matches routes in registration order, so
# the literal `/api/sentiment/aggregate` MUST be declared before the
# catch-all `/api/sentiment/{symbol}`. Otherwise the catch-all wins,
# `validate_symbol("aggregate")` raises 400, and the aggregate endpoint
# is unreachable. (Bug fixed 2026-05-01.)
@app.get("/api/sentiment/aggregate")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_aggregate_sentiment():
    """Get aggregated market sentiment across all tracked symbols"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="sentiment-analysis",
        path="/api/v1/sentiment/aggregate",
        method="GET",
    )


@app.get("/api/sentiment/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_sentiment(symbol: str):
    """Get sentiment analysis for a symbol (backwards compatibility)"""
    validated_symbol = validate_symbol(symbol)

    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="sentiment-analysis",
        path=f"/api/v1/sentiment/{validated_symbol}",
        method="GET",
    )


# ============================================================================
# AGGREGATION ENDPOINTS
# ============================================================================


@app.get("/api/dashboard/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_dashboard_data(symbol: str, interval: str = "60"):
    """Aggregated dashboard endpoint combining data from multiple services"""
    validated_symbol = validate_symbol(symbol)
    validated_interval = validate_interval(interval)

    proxy = get_proxy()

    try:
        ticker_task = proxy.proxy_request(
            "market-data", f"/api/v1/ticker/{validated_symbol}", "GET"
        )
        signal_task = proxy.proxy_request(
            "trading-engine",
            f"/api/v1/signals/{validated_symbol}",
            "GET",
            {"interval": validated_interval},
        )
        portfolio_task = proxy.proxy_request(
            "portfolio-manager", "/api/v1/portfolio", "GET"
        )

        ticker, signal, portfolio = await asyncio.gather(
            ticker_task, signal_task, portfolio_task, return_exceptions=True
        )

        def _parse(resp):
            # Backend response was already parsed to a dict by
            # ServiceProxy and re-serialized to JSON in JSONResponse.
            # Returning .body.decode() here would put a JSON string
            # inside a JSON field — frontend would have to double-parse.
            if isinstance(resp, Exception):
                return None
            try:
                return json.loads(resp.body.decode())
            except Exception:
                return None

        return JSONResponse(
            content={
                "success": True,
                "symbol": validated_symbol,
                "interval": validated_interval,
                "data": {
                    "market": _parse(ticker),
                    "signal": _parse(signal),
                    "portfolio": _parse(portfolio),
                },
                "timestamp": int(time.time() * 1000),
            }
        )

    except Exception as e:
        logger.error(f"Error fetching dashboard data: {e}")
        raise HTTPException(status_code=500, detail="Error fetching dashboard data")


# ============================================================================
# API V1 ROUTES - Compatibility layer
# ============================================================================


@app.get("/api/v1/market/ticker/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_ticker_v1(symbol: str):
    """Get ticker data (v1 compatibility)"""
    return await get_ticker(symbol, None)


@app.get("/api/v1/market/klines/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_klines_v1(symbol: str, interval: str = "60", limit: int = 100):
    """Get klines (v1 compatibility)"""
    return await get_klines_plural(symbol, interval, limit)


@app.get("/api/v1/analysis/rsi/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_rsi_v1(symbol: str, interval: str = "60", period: int = 14):
    """Get RSI (v1 compatibility)"""
    return await get_rsi(symbol, interval, period)


@app.get("/api/v1/analysis/macd/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_macd_v1(symbol: str, interval: str = "60"):
    """Get MACD (v1 compatibility)"""
    return await get_macd(symbol, interval)


@app.get("/api/v1/analysis/all/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_all_indicators_v1(symbol: str, interval: str = "60"):
    """Get all indicators (v1 compatibility)"""
    return await get_all_indicators(symbol, interval)


@app.get("/api/v1/ml/predict/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def ml_predict_v1(symbol: str, interval: str = "60", model_type: str = "GRU"):
    """Get ML prediction (v1 compatibility)"""
    return await ml_predict_price(symbol, interval, model_type)


@app.get("/api/v1/ml/predict/price/{symbol}")
# @rate_limiter.general_limit  # Rate limited via middleware
async def ml_predict_price_v1(
    symbol: str, interval: str = "60", model_type: str = "GRU"
):
    """Get ML price prediction (v1 compatibility)"""
    return await ml_predict_price(symbol, interval, model_type)


@app.get("/api/v1/portfolio/balance")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_balance_v1(portfolio_id: str = "default"):
    """Get portfolio balance (v1 compatibility)"""
    return await get_balance(portfolio_id)


@app.get("/api/v1/portfolio/holdings")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_holdings_v1(portfolio_id: str = "default"):
    """Get portfolio holdings (v1 compatibility)"""
    return await get_holdings(portfolio_id)


@app.get("/api/v1/portfolio/positions")
# @rate_limiter.general_limit  # Rate limited via middleware
async def get_positions_v1(status: str = "open"):
    """Get trading positions (v1 compatibility)"""
    return await get_positions(status)


# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time dashboard updates"""
    await websocket_manager.connect(websocket)

    try:
        await websocket_manager.send_personal_message(
            {
                "type": "connection",
                "message": "Connected to API Gateway WebSocket",
                "timestamp": datetime.now().isoformat(),
            },
            websocket,
        )

        while True:
            data = await websocket.receive_text()

            if data == "ping":
                await websocket_manager.send_personal_message(
                    {"type": "pong", "timestamp": datetime.now().isoformat()}, websocket
                )

    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
        logger.info("Client disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        websocket_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.service_port)
