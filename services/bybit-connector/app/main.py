"""
Bybit Connector Service - FastAPI Application
Purpose: REST API service for interfacing with Bybit exchange
Features: Rate limiting, structured logging, Prometheus metrics
"""

from fastapi import FastAPI, HTTPException, Depends, status, Request
from pathlib import Path

# Add shared utilities to path

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from typing import Optional
import logging
import re
import time
from contextlib import asynccontextmanager
from starlette.middleware.base import BaseHTTPMiddleware

# Fixed: Create logs directory to prevent startup crashes (Critical Issue #3)
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Rate limiting imports
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Prometheus metrics imports
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

# JSON logging imports.
# python-json-logger>=3 moved JsonFormatter into pythonjsonlogger.json. Try the
# new path first, fall back to the legacy path for compatibility.
try:
    from pythonjsonlogger import json as jsonlogger  # type: ignore[import]
except ImportError:  # pragma: no cover — only triggers on python-json-logger<3
    from pythonjsonlogger import jsonlogger  # type: ignore[no-redef]

from app.config import get_settings, Settings
from app.bybit_rest_client import BybitRestClient, create_rest_client
from app.tape_replay_client import TapeReplayClient
from app.circuit_breaker import CircuitState
from app.exceptions import BybitConnectorException
from app.models import PlaceOrderRequest, CancelOrderRequest


# ============================================================================
# STRUCTURED JSON LOGGING WITH SECRET MASKING
# ============================================================================


class SecretMaskingFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter that masks sensitive data in logs"""

    # Patterns to identify secrets in log messages and extra fields
    SECRET_PATTERNS = [
        (re.compile(r'(api_key["\s:=]+)([^\s,}"]+)', re.IGNORECASE), r"\1***MASKED***"),
        (
            re.compile(r'(api_secret["\s:=]+)([^\s,}"]+)', re.IGNORECASE),
            r"\1***MASKED***",
        ),
        (
            re.compile(r'(password["\s:=]+)([^\s,}"]+)', re.IGNORECASE),
            r"\1***MASKED***",
        ),
        (re.compile(r'(token["\s:=]+)([^\s,}"]+)', re.IGNORECASE), r"\1***MASKED***"),
        (re.compile(r'(secret["\s:=]+)([^\s,}"]+)', re.IGNORECASE), r"\1***MASKED***"),
        (
            re.compile(r'(authorization["\s:]*:["\s]*)([^\s,}"]+)', re.IGNORECASE),
            r"\1***MASKED***",
        ),
        (re.compile(r'(bearer["\s]+)([^\s,}"]+)', re.IGNORECASE), r"\1***MASKED***"),
    ]

    def add_fields(self, log_record, record, message_dict):
        """Override to add custom fields and mask secrets"""
        # Add standard fields
        super(SecretMaskingFormatter, self).add_fields(log_record, record, message_dict)

        # Add timestamp in ISO format
        log_record["timestamp"] = self.formatTime(record, self.datefmt)

        # Add log level
        log_record["level"] = record.levelname

        # Add logger name
        log_record["logger"] = record.name

        # Add thread info for debugging
        log_record["thread"] = record.thread

        # Mask secrets in the message
        if "message" in log_record:
            log_record["message"] = self._mask_secrets(str(log_record["message"]))

        # Mask secrets in all extra fields
        for key, value in list(log_record.items()):
            if isinstance(value, str):
                log_record[key] = self._mask_secrets(value)
            elif isinstance(value, dict):
                log_record[key] = self._mask_dict_secrets(value)

    def _mask_secrets(self, text: str) -> str:
        """Apply regex patterns to mask secrets in text"""
        for pattern, replacement in self.SECRET_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def _mask_dict_secrets(self, data: dict) -> dict:
        """Recursively mask secrets in dictionaries"""
        masked = {}
        for key, value in data.items():
            # Mask common secret field names
            if any(
                secret_key in key.lower()
                for secret_key in [
                    "api_key",
                    "api_secret",
                    "password",
                    "token",
                    "secret",
                    "authorization",
                ]
            ):
                masked[key] = "***MASKED***"
            elif isinstance(value, str):
                masked[key] = self._mask_secrets(value)
            elif isinstance(value, dict):
                masked[key] = self._mask_dict_secrets(value)
            else:
                masked[key] = value
        return masked


# Configure JSON logging with secret masking
def setup_json_logging():
    """Setup structured JSON logging with secret masking for container environments"""
    # Create handler for stdout (standard for containers)
    handler = logging.StreamHandler()

    # Use custom JSON formatter with secret masking
    formatter = SecretMaskingFormatter(
        fmt="%(timestamp)s %(level)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        json_ensure_ascii=False,
    )

    handler.setFormatter(formatter)

    # Get root logger and configure it
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers = []

    # Add our custom handler
    root_logger.addHandler(handler)

    return logging.getLogger(__name__)


# Initialize structured logging
logger = setup_json_logging()


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

# Circuit breaker state gauge - monitors circuit breaker status
circuit_breaker_state = Gauge(
    "circuit_breaker_state", "Circuit breaker state (0=closed, 1=open, 2=half-open)"
)


def _update_breaker_gauge(state: CircuitState) -> None:
    """Mirror breaker state into the Prometheus gauge whenever it transitions."""
    state_mapping = {
        CircuitState.CLOSED: 0,
        CircuitState.OPEN: 1,
        CircuitState.HALF_OPEN: 2,
    }
    circuit_breaker_state.set(state_mapping.get(state, 0))


# ============================================================================
# PROMETHEUS METRICS MIDDLEWARE
# ============================================================================


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware to collect Prometheus metrics for all HTTP requests"""

    async def dispatch(self, request: Request, call_next):
        """Process request and collect metrics"""
        # Skip metrics endpoint itself to avoid recursion
        if request.url.path == "/metrics":
            return await call_next(request)

        # Extract method and path
        method = request.method
        path = request.url.path

        # Normalize path to group by endpoint pattern (not dynamic values)
        endpoint = self._normalize_endpoint(path)

        # Increment active requests
        http_requests_active.inc()

        # Start timer for duration measurement
        start_time = time.time()

        try:
            # Process the request
            response = await call_next(request)

            # Record successful request
            status_code = response.status_code

        except Exception as e:
            # Record failed request
            status_code = 500
            logger.error(
                f"Request failed: {str(e)}",
                extra={"method": method, "endpoint": endpoint, "error": str(e)},
            )
            raise

        finally:
            # Calculate request duration
            duration = time.time() - start_time

            # Decrement active requests
            http_requests_active.dec()

            # Record metrics
            http_requests_total.labels(
                method=method, endpoint=endpoint, status_code=status_code
            ).inc()

            http_request_duration_seconds.labels(
                method=method, endpoint=endpoint
            ).observe(duration)

            # Log request with structured data
            logger.info(
                f"{method} {endpoint} {status_code}",
                extra={
                    "method": method,
                    "endpoint": endpoint,
                    "status_code": status_code,
                    "duration_seconds": round(duration, 4),
                    "client_ip": request.client.host if request.client else None,
                },
            )

        return response

    def _normalize_endpoint(self, path: str) -> str:
        """Normalize dynamic path segments to avoid high cardinality in metrics"""
        # Replace UUIDs, IDs, and other dynamic segments with placeholders
        normalized = re.sub(
            r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "/{uuid}",
            path,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(r"/\d+", "/{id}", normalized)
        return normalized


# ============================================================================
# RATE LIMITING CONFIGURATION
# ============================================================================

# Initialize rate limiter using client IP address
limiter = Limiter(key_func=get_remote_address)


# ============================================================================
# LIFESPAN MANAGEMENT
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle (startup/shutdown)

    Fixed: Wrapped in try/finally to ensure cleanup happens even if startup fails
    (Critical Issue #4 - Unhandled Exception in Lifespan)
    """
    # Startup
    settings = get_settings()

    logger.info(
        "Starting Bybit Connector Service",
        extra={
            "testnet": settings.bybit_testnet,
            "service_version": "1.0.0",
            "environment": "development" if settings.debug else "production",
        },
    )

    # D-14/D-15: branch on market_data_source. Tape mode skips live REST + clock sync.
    if settings.market_data_source == "tape":
        # Loud, grep-able startup line for log audits (must_have: "BYBIT_PRICE_SOURCE: mode=tape ...").
        logger.warning(
            "BYBIT_PRICE_SOURCE: mode=tape source_dir=%s tape_version=1",
            settings.tape_fixtures_path,
        )
        try:
            app.state.rest_client = TapeReplayClient(settings.tape_fixtures_path)
            _update_breaker_gauge(CircuitState.CLOSED)
            logger.info("Tape replay client initialized successfully")
        except FileNotFoundError as exc:
            # Landmine §6 — bind-mount race. Refuse to come up rather than silently serve empty.
            logger.error("TAPE_REPLAY_INIT_FAILED: %s", exc)
            raise
        try:
            yield
        finally:
            await app.state.rest_client.close()
            logger.info("Bybit Connector Service stopped gracefully (tape mode)")
        return

    # Live mode: connect to real Bybit REST/WS.
    # Loud, grep-able startup line so log audits can confirm the actual price source.
    logger.warning(
        "BYBIT_PRICE_SOURCE: mode=live testnet=%s rest_url=%s ws_url=%s",
        settings.bybit_testnet,
        settings.rest_api_url,
        settings.websocket_url,
    )

    try:
        # Initialize REST client and store in app state. Subscribe the breaker
        # so its state mirrors into the Prometheus gauge on every transition,
        # not just when /api/v1/status/circuit-breaker is hit.
        app.state.rest_client = create_rest_client(
            settings,
            on_breaker_state_change=_update_breaker_gauge,
        )
        # Initialise gauge to closed so dashboards don't read NaN until first event
        _update_breaker_gauge(CircuitState.CLOSED)
        logger.info("Bybit REST client initialized successfully")

        # Sync local clock against Bybit server time to immunise against the
        # 10004 "invalid timestamp" class of errors caused by host-clock drift.
        try:
            await app.state.rest_client.authenticator.sync_clock(
                app.state.rest_client.client, app.state.rest_client.base_url
            )
        except Exception as exc:
            # Best-effort: don't fail startup if clock sync hits a transient
            # network error — the auth path falls back to local time.
            logger.warning(f"Clock sync against Bybit server skipped: {exc}")

        yield

    finally:
        # Shutdown - guaranteed to run even if startup or yield fails
        if hasattr(app.state, "rest_client") and app.state.rest_client:
            await app.state.rest_client.close()
            logger.info("Bybit REST client closed")

        logger.info("Bybit Connector Service stopped gracefully")


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="Bybit Connector Service",
    description="Microservice for interfacing with Bybit exchange API with rate limiting, metrics, and structured logging",
    version="1.0.0",
    lifespan=lifespan,
)

# Add Prometheus metrics middleware (must be added before other middleware)
app.add_middleware(PrometheusMiddleware)

# Fixed: CORS middleware with restricted methods and headers (Critical Issue #2 - Security)
# Only allow necessary HTTP methods, not all methods including dangerous ones like DELETE/PATCH
settings_instance = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings_instance.all_cors_origins,  # BL-04: never `*` with credentials
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # Only allow safe methods for trading API
    allow_headers=[
        "Content-Type",
        "Authorization",
        "Accept",
        "Origin",
    ],  # Only necessary headers
)

# Add rate limiter state to app
app.state.limiter = limiter

# Add rate limit exceeded handler
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================


def require_live_orders_permitted() -> None:
    """
    Refuse real order placement unless the service is explicitly in LIVE mode.

    SEC-0 (2026-07-31): this service is the only component that can touch real
    money, and it previously had no mode check at all. The LIVE safeguards --
    PAPER_TRADING_MODE, TRADING_MODE, LIVE_TRADING_ACK, the kill switch, the
    per-trade cap, the daily-loss breaker -- all live in trading-engine, and
    the order routes here do not go through trading-engine. With
    BYBIT_TESTNET=false and port 8001 published, a single unauthenticated POST
    reached Bybit mainnet and bypassed every one of them.

    Enforcing the flags here puts them at the point where money is actually
    touched. Fail-closed: `live_orders_permitted` requires all three
    conditions, so absent or malformed configuration refuses.

    This is defence in depth, not a substitute for authentication -- the
    service still has none. Bind port 8001 to loopback as well.
    """
    settings = get_settings()
    permitted, reason = settings.live_orders_permitted
    if not permitted:
        logger.warning(f"Refused live order request: {reason}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Live order placement is disabled: {reason}. "
                "This connector refuses to touch the exchange unless "
                "PAPER_TRADING_MODE=false, TRADING_MODE=LIVE and "
                "LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY are all set."
            ),
        )


def get_rest_client(request: Request) -> BybitRestClient:
    """Dependency to get REST client from app state"""
    if (
        not hasattr(request.app.state, "rest_client")
        or request.app.state.rest_client is None
    ):
        logger.error("Bybit client not initialized in app state")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bybit client not initialized",
        )
    return request.app.state.rest_client


# ============================================================================
# PROMETHEUS METRICS ENDPOINT
# ============================================================================


@app.get("/metrics", include_in_schema=False)
async def metrics():
    """
    Prometheus metrics endpoint
    Returns metrics in Prometheus text format

    The breaker gauge is kept in sync via the on-state-change callback
    (see add_listener around line 222 + the comment at the bottom of this
    file); no in-endpoint refresh is needed. WR-04 removed a stale
    placeholder try/except pair with a bare `except:` (project ban-list).
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ============================================================================
# HEALTH ENDPOINTS
# Rate Limit: 60 requests/minute - frequently accessed for health checks
# ============================================================================


@app.get("/health", tags=["Health"])
@limiter.limit("60/minute")
async def health_check(request: Request):
    """
    Basic health check endpoint
    Returns 200 if service is running
    Rate limited to 60 requests/minute
    """
    return {"status": "healthy", "service": "bybit-connector"}


@app.get("/ready", tags=["Health"])
@limiter.limit("60/minute")
async def readiness_check(
    request: Request, client: BybitRestClient = Depends(get_rest_client)
):
    """
    Readiness check - verifies service can connect to Bybit
    Tests actual connectivity to Bybit API
    Rate limited to 60 requests/minute
    """
    try:
        # Probe a public endpoint with one of the validated trading symbols
        # (CLAUDE.md: SOL / BNB / ADA only). Just a connectivity check.
        await client.get_ticker(category="linear", symbol="SOLUSDT")
        logger.info("Readiness check passed - Bybit connection OK")
        return {"status": "ready", "bybit_connection": "ok"}
    except Exception as e:
        logger.error(f"Readiness check failed: {str(e)}", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Bybit connection failed: {str(e)}",
        )


# ============================================================================
# ACCOUNT ENDPOINTS
# Rate Limit: 20 requests/minute - moderate frequency for account queries
# ============================================================================


@app.get("/api/v1/account/balance", tags=["Account"])
@limiter.limit("20/minute")
async def get_balance(
    request: Request,
    account_type: str = "UNIFIED",
    coin: Optional[str] = None,
    client: BybitRestClient = Depends(get_rest_client),
):
    """
    Get wallet balance
    Returns account balance for specified account type and coin
    Rate limited to 20 requests/minute
    """
    try:
        logger.info(
            "Fetching wallet balance",
            extra={"account_type": account_type, "coin": coin},
        )
        result = await client.get_wallet_balance(account_type=account_type, coin=coin)
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        logger.error(f"Failed to get balance: {str(e)}", extra={"error": str(e)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/v1/account/positions", tags=["Account"])
@limiter.limit("20/minute")
async def get_positions(
    request: Request,
    category: str = "linear",
    symbol: Optional[str] = None,
    client: BybitRestClient = Depends(get_rest_client),
):
    """
    Get position information
    Returns current open positions
    Rate limited to 20 requests/minute
    """
    try:
        logger.info(
            "Fetching positions", extra={"category": category, "symbol": symbol}
        )
        result = await client.get_positions(category=category, symbol=symbol)
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        logger.error(f"Failed to get positions: {str(e)}", extra={"error": str(e)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============================================================================
# TRADING ENDPOINTS
# Rate Limit: 10 requests/minute - strict limit to prevent API abuse
# ============================================================================


@app.post("/api/v1/order/place", tags=["Trading"])
@limiter.limit("10/minute")
async def place_order(
    request: Request,
    order: PlaceOrderRequest,
    client: BybitRestClient = Depends(get_rest_client),
    _live_ok: None = Depends(require_live_orders_permitted),
):
    """
    Place a new order
    Creates a new trading order on Bybit
    Rate limited to 10 requests/minute for safety
    """
    try:
        logger.info(
            "Placing order",
            extra={
                "symbol": order.symbol,
                "side": order.side,
                "order_type": order.order_type,
                "qty": str(order.qty),
            },
        )
        result = await client.place_order(
            category=order.category,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            qty=order.qty,
            price=order.price,
            time_in_force=order.time_in_force,
            reduce_only=order.reduce_only,
            order_link_id=order.order_link_id,
            take_profit=order.take_profit,
            stop_loss=order.stop_loss,
            tpsl_mode=order.tpsl_mode,
            trigger_price=order.trigger_price,
            trigger_direction=order.trigger_direction,
        )
        logger.info(
            "Order placed successfully",
            extra={"order_id": result.get("orderId"), "symbol": order.symbol},
        )
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        logger.error(
            f"Failed to place order: {str(e)}",
            extra={"symbol": order.symbol, "error": str(e)},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/api/v1/order/cancel", tags=["Trading"])
@limiter.limit("10/minute")
async def cancel_order(
    request: Request,
    cancel_request: CancelOrderRequest,
    client: BybitRestClient = Depends(get_rest_client),
    _live_ok: None = Depends(require_live_orders_permitted),
):
    """
    Cancel an order
    Cancels an existing order by ID
    Rate limited to 10 requests/minute
    """
    try:
        logger.info(
            "Cancelling order",
            extra={
                "symbol": cancel_request.symbol,
                "order_id": cancel_request.order_id,
            },
        )
        result = await client.cancel_order(
            category=cancel_request.category,
            symbol=cancel_request.symbol,
            order_id=cancel_request.order_id,
            order_link_id=cancel_request.order_link_id,
        )
        logger.info(
            "Order cancelled successfully", extra={"order_id": cancel_request.order_id}
        )
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        logger.error(
            f"Failed to cancel order: {str(e)}",
            extra={"order_id": cancel_request.order_id, "error": str(e)},
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/v1/order/open", tags=["Trading"])
@limiter.limit("20/minute")
async def get_open_orders(
    request: Request,
    category: str = "linear",
    symbol: Optional[str] = None,
    limit: int = 50,
    client: BybitRestClient = Depends(get_rest_client),
):
    """
    Get open orders
    Returns list of currently open orders
    Rate limited to 20 requests/minute
    """
    try:
        logger.info(
            "Fetching open orders",
            extra={"category": category, "symbol": symbol, "limit": limit},
        )
        result = await client.get_open_orders(
            category=category, symbol=symbol, limit=limit
        )
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        logger.error(f"Failed to get open orders: {str(e)}", extra={"error": str(e)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/v1/order/history", tags=["Trading"])
@limiter.limit("20/minute")
async def get_order_history(
    request: Request,
    category: str = "linear",
    symbol: Optional[str] = None,
    limit: int = 50,
    cursor: Optional[str] = None,
    client: BybitRestClient = Depends(get_rest_client),
):
    """
    Get order history
    Returns historical orders with pagination
    Rate limited to 20 requests/minute
    """
    try:
        logger.info(
            "Fetching order history",
            extra={"category": category, "symbol": symbol, "limit": limit},
        )
        result = await client.get_order_history(
            category=category, symbol=symbol, limit=limit, cursor=cursor
        )
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        logger.error(f"Failed to get order history: {str(e)}", extra={"error": str(e)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============================================================================
# MARKET DATA ENDPOINTS
# Rate Limit: 200 requests/minute - increased for multi-symbol trading (20 symbols)
# ============================================================================


@app.get("/api/v1/market/ticker", tags=["Market Data"])
@limiter.limit("200/minute")
async def get_ticker(
    request: Request,
    category: str = "linear",
    symbol: Optional[str] = None,
    client: BybitRestClient = Depends(get_rest_client),
):
    """
    Get latest ticker data
    Returns current market ticker information
    Rate limited to 200 requests/minute (increased for multi-symbol trading)
    """
    try:
        logger.debug("Fetching ticker", extra={"category": category, "symbol": symbol})
        result = await client.get_ticker(category=category, symbol=symbol)
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        logger.error(f"Failed to get ticker: {str(e)}", extra={"error": str(e)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/v1/market/kline", tags=["Market Data"])
@limiter.limit("200/minute")
async def get_kline(
    request: Request,
    category: str = "linear",
    symbol: str = "BTCUSDT",
    interval: str = "60",
    limit: int = 200,
    start: Optional[int] = None,
    end: Optional[int] = None,
    client: BybitRestClient = Depends(get_rest_client),
):
    """
    Get kline/candlestick data with optional time range

    Returns historical price candles for the specified symbol and interval.
    Rate limited to 200 requests/minute (increased for multi-symbol trading)

    Args:
        category: Product category (linear, inverse, spot)
        symbol: Trading pair (e.g., BTCUSDT)
        interval: Kline interval (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)
        limit: Number of klines to fetch (max 1000, default 200)
        start: Start timestamp in milliseconds (optional)
        end: End timestamp in milliseconds (optional)

    Returns:
        List of kline data arrays [timestamp, open, high, low, close, volume, turnover]

    Note:
        - If neither start nor end is provided, returns the latest `limit` candles
        - Bybit API returns data in descending order (newest first)
        - Maximum 1000 candles per request (Bybit API limit)

    Fixed: 2025-12-11 - Added start/end parameters for historical data fetching
    """
    try:
        logger.debug(
            "Fetching kline data",
            extra={
                "category": category,
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
                "start": start,
                "end": end,
            },
        )
        result = await client.get_kline(
            category=category,
            symbol=symbol,
            interval=interval,
            limit=limit,
            start_time=start,
            end_time=end,
        )
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        logger.error(f"Failed to get kline: {str(e)}", extra={"error": str(e)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/v1/market/recent-trade", tags=["Market Data"])
@limiter.limit("200/minute")
async def get_recent_trades(
    request: Request,
    category: str = "linear",
    symbol: str = "SOLUSDT",
    limit: int = 100,
    client: BybitRestClient = Depends(get_rest_client),
):
    """
    Get recent public trades (executions)

    Proxies Bybit V5 `/v5/market/recent-trade`. Used by the trading-engine's
    multi-exchange adapter to estimate volume / order-flow. Public endpoint,
    no authentication.
    """
    try:
        logger.debug(
            "Fetching recent trades",
            extra={"category": category, "symbol": symbol, "limit": limit},
        )
        result = await client.get_recent_trades(
            category=category, symbol=symbol, limit=limit
        )
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        logger.error(f"Failed to get recent trades: {str(e)}", extra={"error": str(e)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/v1/market/orderbook", tags=["Market Data"])
@limiter.limit("200/minute")
async def get_orderbook(
    request: Request,
    category: str = "linear",
    symbol: str = "BTCUSDT",
    limit: int = 25,
    client: BybitRestClient = Depends(get_rest_client),
):
    """
    Get orderbook depth
    Returns current market orderbook (bids/asks)
    Rate limited to 200 requests/minute (increased for multi-symbol trading)
    """
    try:
        logger.debug(
            "Fetching orderbook",
            extra={"category": category, "symbol": symbol, "limit": limit},
        )
        result = await client.get_orderbook(
            category=category, symbol=symbol, limit=limit
        )
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        logger.error(f"Failed to get orderbook: {str(e)}", extra={"error": str(e)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/v1/market/funding-rate/history", tags=["Market Data"])
@limiter.limit("200/minute")
async def get_funding_rate_history(
    request: Request,
    symbol: str,
    category: str = "linear",
    start: Optional[int] = None,
    end: Optional[int] = None,
    limit: int = 200,
    client: BybitRestClient = Depends(get_rest_client),
):
    """
    Get historical funding rates for a perpetual contract.

    Funding settles every fundingInterval minutes (8h default for SOL/BNB/ADA-USDT
    on Bybit; some symbols use 1h or 4h — query /api/v1/market/instruments-info
    for the per-symbol interval). Funding rate is bounded ~±0.05% per settlement.

    Use case: T2.3 funding-rate awareness on perp entries — gate entries on
    funding sign/magnitude to avoid persistent funding drag (worst case
    ~55%/yr if always long into positive funding). Also enables cash-and-carry
    research (basis trade between spot and perp).

    Args:
        symbol: Trading pair (required, e.g. SOLUSDT).
        category: linear or inverse (perpetuals only — spot has no funding).
        start: Start timestamp in milliseconds (optional).
        end: End timestamp in milliseconds (optional).
        limit: 1-200 (Bybit hard limit), default 200.

    Returns:
        {success, data: [{symbol, fundingRate, fundingRateTimestamp}, ...]}
        ordered newest-first per Bybit convention.
    """
    try:
        logger.debug(
            "Fetching funding rate history",
            extra={
                "category": category,
                "symbol": symbol,
                "limit": limit,
                "start": start,
                "end": end,
            },
        )
        result = await client.get_funding_rate_history(
            category=category,
            symbol=symbol,
            start_time=start,
            end_time=end,
            limit=limit,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        # category=spot or other invalid — surface as 400 not 500
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except BybitConnectorException as e:
        logger.error(
            f"Failed to get funding rate history: {str(e)}", extra={"error": str(e)}
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/v1/market/instruments-info", tags=["Market Data"])
@limiter.limit("60/minute")
async def get_instruments_info(
    request: Request,
    category: str = "linear",
    symbol: Optional[str] = None,
    client: BybitRestClient = Depends(get_rest_client),
):
    """
    Get instrument metadata (tick size, lot size, fundingInterval, etc.).

    Lower rate limit (60/min) since this is a slow-changing reference dataset
    that callers should cache locally.

    Args:
        category: spot, linear, inverse, or option.
        symbol: Restrict to a single symbol (optional).

    Returns:
        {success, data: [...]}. For perp instruments each item includes
        fundingInterval (string of minutes) plus priceFilter / lotSizeFilter.
    """
    try:
        logger.debug(
            "Fetching instruments info",
            extra={"category": category, "symbol": symbol},
        )
        result = await client.get_instruments_info(category=category, symbol=symbol)
        return {"success": True, "data": result}
    except BybitConnectorException as e:
        logger.error(
            f"Failed to get instruments info: {str(e)}", extra={"error": str(e)}
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============================================================================
# MONITORING ENDPOINTS
# Rate Limit: 20 requests/minute - moderate frequency for monitoring
# ============================================================================


@app.get("/api/v1/status/circuit-breaker", tags=["Monitoring"])
@limiter.limit("20/minute")
async def get_circuit_breaker_status(
    request: Request, client: BybitRestClient = Depends(get_rest_client)
):
    """
    Get circuit breaker status
    Returns current state of the circuit breaker
    Rate limited to 20 requests/minute
    """
    status_data = client.get_circuit_breaker_status()

    # Gauge is kept in sync via on_state_change callback registered at startup;
    # no need to repeat it here. Read-only endpoint.

    logger.info(
        "Circuit breaker status checked", extra={"state": status_data.get("state")}
    )

    return {"success": True, "data": status_data}


@app.post("/api/v1/status/circuit-breaker/reset", tags=["Monitoring"])
@limiter.limit("10/minute")
async def reset_circuit_breaker(
    request: Request, client: BybitRestClient = Depends(get_rest_client)
):
    """
    Reset circuit breaker
    Manually resets the circuit breaker to closed state
    Rate limited to 10 requests/minute (admin operation)
    """
    logger.warning("Circuit breaker manually reset")
    client.reset_circuit_breaker()

    # Gauge is updated via on_state_change callback fired by reset().

    return {"success": True, "message": "Circuit breaker reset"}


@app.post("/admin/tape/reset", tags=["Admin"])
@limiter.limit("60/minute")
async def reset_tape_cursor(
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Reset the tape replay cursor to fixture position 0 (D-04).

    Gated to MARKET_DATA_SOURCE=tape mode only. Refuses in live mode —
    state-mutating admin endpoint must not be reachable in production.
    Called by integration suite's `tape_reset` fixture before each test.
    """
    # D-04 + threat model HIGH: refuse outside tape mode.
    if settings.market_data_source != "tape":
        raise HTTPException(
            status_code=403,
            detail="tape/reset only available when MARKET_DATA_SOURCE=tape",
        )
    client = request.app.state.rest_client
    if not isinstance(client, TapeReplayClient):
        raise HTTPException(
            status_code=503,
            detail="tape client not initialized",
        )
    logger.warning("TAPE_REPLAY: cursor reset")
    client.reset()
    return {"success": True, "message": "tape cursor reset"}


# ============================================================================
# APPLICATION ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    logger.info(
        "Starting uvicorn server",
        extra={
            "host": settings.service_host,
            "port": settings.service_port,
            "debug": settings.debug,
        },
    )

    uvicorn.run(
        "main:app",
        host=settings.service_host,
        port=settings.service_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
