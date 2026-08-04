"""
Rate Limiter Module
===================
Implements rate limiting for API Gateway using slowapi with Redis backend.

Rate Limits (per minute):
- Trading endpoints: 10 requests/minute
- Auth endpoints: 5 requests/minute
- Health checks: 60 requests/minute
- General API: 30 requests/minute

Features:
- Redis backend for distributed rate limiting
- Custom error responses with Retry-After header
- Logging of rate limit violations
- Per-endpoint configuration

Version: 1.0.1
Created: 2025-12-12
Updated: 2025-12-12 - Fixed decorator to work without Request param
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable, Tuple
from functools import wraps

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """
    Configuration for rate limiting rules.

    Attributes:
        trading_limit: Requests per minute for trading endpoints
        auth_limit: Requests per minute for auth endpoints
        health_limit: Requests per minute for health endpoints
        general_limit: Requests per minute for general API endpoints
        enabled: Whether rate limiting is enabled
        redis_url: Redis connection URL for distributed rate limiting
    """
    # Limits recalibrated 2026-07-29 for the real single-user dashboard, which
    # legitimately polls ~250-300 read req/min across ~10 query keys. The old
    # values (general 30, trading 10) throttled normal use into constant 429s
    # the moment enforcement went live. These ceilings still bound abuse
    # (thousands/min) while never touching legitimate dashboard traffic; the
    # strict `trading_write_limit` applies ONLY to state-changing trade
    # actions (start/stop/buy/sell), which a human triggers a handful of times.
    trading_write_limit: int = 60   # Mutating trade actions: 60 req/min
    auth_limit: int = 10            # Auth endpoints (brute-force guard): 10 req/min
    health_limit: int = 1200        # Health/status polls: 1200 req/min
    general_limit: int = 1200       # General API + read polls: 1200 req/min
    enabled: bool = True            # Rate limiting enabled
    redis_url: Optional[str] = None  # Redis URL for distributed limiting


def get_client_identifier(request: Request) -> str:
    """
    Get client identifier for rate limiting.

    Uses X-Forwarded-For header if behind proxy, otherwise uses remote address.
    Also considers authenticated user if available.

    Args:
        request: FastAPI request object

    Returns:
        Client identifier string for rate limit key
    """
    # Check for authenticated user first
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "user_id"):
        return f"user:{user.user_id}"

    # Check for X-Forwarded-For header (proxy/load balancer)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        client_ip = forwarded_for.split(",")[0].strip()
        return f"ip:{client_ip}"

    # Fall back to remote address
    client_ip = get_remote_address(request)
    return f"ip:{client_ip}"


class RateLimiter:
    """
    Rate limiter with Redis backend for distributed rate limiting.

    Provides endpoint-specific rate limits:
    - Trading endpoints: 10/min (strict for safety)
    - Auth endpoints: 5/min (prevent brute force)
    - Health checks: 60/min (monitoring needs)
    - General API: 30/min (default)

    Usage:
        limiter = RateLimiter(config)

        @app.get("/api/trading/signal")
        @limiter.trading_limit
        async def get_signal(request: Request):
            ...
    """

    def __init__(self, config: RateLimitConfig):
        """
        Initialize rate limiter with configuration.

        Args:
            config: Rate limit configuration
        """
        self.config = config
        self._limiter: Optional[Limiter] = None
        self._enabled = config.enabled

        if self._enabled:
            self._initialize_limiter()

    def _initialize_limiter(self) -> None:
        """Initialize slowapi limiter with Redis backend if available."""
        try:
            storage_uri = self.config.redis_url or "memory://"

            self._limiter = Limiter(
                key_func=get_client_identifier,
                storage_uri=storage_uri,
                default_limits=[f"{self.config.general_limit}/minute"],
                headers_enabled=True,  # Include rate limit headers in response
            )

            logger.info(
                f"Rate limiter initialized with storage: "
                f"{'Redis' if self.config.redis_url else 'Memory'}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize rate limiter: {e}")
            # Fall back to memory storage
            self._limiter = Limiter(
                key_func=get_client_identifier,
                storage_uri="memory://",
                default_limits=[f"{self.config.general_limit}/minute"],
            )
            logger.warning("Falling back to in-memory rate limiting")

    @property
    def limiter(self) -> Optional[Limiter]:
        """Get the underlying slowapi limiter instance."""
        return self._limiter

    @property
    def enabled(self) -> bool:
        """Check if rate limiting is enabled."""
        return self._enabled and self._limiter is not None

    def _create_limit_decorator(self, limit_value: int) -> Callable:
        """
        Create a rate limit decorator for a specific limit.

        Args:
            limit_value: Requests per minute limit

        Returns:
            Decorator function
        """
        if not self.enabled:
            # Return a no-op decorator if rate limiting is disabled
            def noop_decorator(func: Callable) -> Callable:
                return func
            return noop_decorator

        return self._limiter.limit(f"{limit_value}/minute")

    @property
    def trading_limit(self) -> Callable:
        """
        Decorator for trading endpoint rate limiting (legacy slowapi path;
        enforcement is done by RateLimitMiddleware, not these decorators).

        Limit: trading_write_limit requests per minute (mutating trade actions).
        """
        return self._create_limit_decorator(self.config.trading_write_limit)

    @property
    def auth_limit(self) -> Callable:
        """
        Decorator for authentication endpoint rate limiting.

        Limit: 5 requests per minute (prevent brute force attacks)

        Usage:
            @app.post("/auth/login")
            @rate_limiter.auth_limit
            async def login(request: Request, ...):
                ...
        """
        return self._create_limit_decorator(self.config.auth_limit)

    @property
    def health_limit(self) -> Callable:
        """
        Decorator for health check endpoint rate limiting.

        Limit: 60 requests per minute (monitoring needs)

        Usage:
            @app.get("/health")
            @rate_limiter.health_limit
            async def health(request: Request):
                ...
        """
        return self._create_limit_decorator(self.config.health_limit)

    @property
    def general_limit(self) -> Callable:
        """
        Decorator for general API endpoint rate limiting.

        Limit: 30 requests per minute (default)

        Usage:
            @app.get("/api/market/ticker/{symbol}")
            @rate_limiter.general_limit
            async def get_ticker(request: Request, symbol: str):
                ...
        """
        return self._create_limit_decorator(self.config.general_limit)


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter(config: Optional[RateLimitConfig] = None) -> RateLimiter:
    """
    Get or create global rate limiter instance.

    Args:
        config: Optional rate limit configuration

    Returns:
        RateLimiter instance
    """
    global _rate_limiter

    if _rate_limiter is None:
        if config is None:
            config = RateLimitConfig()
        _rate_limiter = RateLimiter(config)

    return _rate_limiter


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Custom handler for rate limit exceeded errors.

    Returns standardized JSON error response with:
    - Error message
    - Rate limit details
    - Retry-After header

    Args:
        request: FastAPI request object
        exc: RateLimitExceeded exception

    Returns:
        JSONResponse with rate limit error details
    """
    # Extract retry-after from exception message
    retry_after = 60  # Default to 60 seconds
    try:
        if hasattr(exc, "detail"):
            # Try to parse retry time from error message
            import re
            match = re.search(r"(\d+)\s*(?:second|minute)", str(exc.detail))
            if match:
                retry_after = int(match.group(1))
    except Exception:
        pass

    # Get client identifier for logging
    client_id = get_client_identifier(request)

    # Log the rate limit violation
    logger.warning(
        f"Rate limit exceeded: client={client_id}, "
        f"path={request.url.path}, method={request.method}"
    )

    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "success": False,
            "error": "rate_limit_exceeded",
            "message": "Too many requests. Please slow down.",
            "detail": str(exc.detail) if hasattr(exc, "detail") else "Rate limit exceeded",
            "retry_after_seconds": retry_after,
            "path": request.url.path,
            "timestamp": int(time.time() * 1000)
        },
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": "varies by endpoint",
            "X-RateLimit-Remaining": "0",
        }
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware for applying rate limits based on endpoint path.

    Automatically applies appropriate rate limits:
    - /api/trading/* -> Trading limit (10/min)
    - /auth/* -> Auth limit (5/min)
    - /health, /ready -> Health limit (60/min)
    - Everything else -> General limit (30/min)
    """

    def __init__(self, app, rate_limiter: RateLimiter):
        """
        Initialize rate limit middleware.

        Args:
            app: FastAPI application
            rate_limiter: RateLimiter instance
        """
        super().__init__(app)
        self.rate_limiter = rate_limiter

        # Path prefixes for different rate limits. NOTE (2026-07-29): the
        # strict trade bucket now applies only to MUTATING requests on these
        # paths (see _get_rate_limit_key's method check) so read polls of
        # /api/trading/status|signals|positions are NOT throttled as trades.
        self.trading_paths = ["/api/trading", "/api/portfolio/buy", "/api/portfolio/sell"]
        self.auth_paths = ["/auth/"]
        self.health_paths = ["/health", "/ready", "/status"]

        # In-process fixed-window counters used to ACTUALLY enforce limits.
        #
        # SECURITY FIX 2026-07-29: this middleware previously only tagged
        # each request with an `X-RateLimit-Category` header and never
        # rejected anything, so every route documented as "Rate limited
        # via middleware" (including /auth/login brute-force protection)
        # was effectively unlimited. We now count requests per
        # (client, category) in a 60s window and fail closed with HTTP 429
        # once the configured limit is exceeded.
        #
        # NOTE: this counter is per-process. For a single gateway instance
        # (the current deployment) it enforces correctly. A multi-replica
        # deployment needs the shared Redis-backed limiter
        # (slowapi/`limits`) for global accuracy; the per-process window is
        # still a strict-per-replica lower bound and strictly better than
        # the previous no-op.
        self._windows: Dict[Tuple[str, str], List[int]] = {}
        self._windows_lock = threading.Lock()

    def _limit_for_category(self, category: str) -> int:
        """Return the configured requests-per-minute limit for a category."""
        cfg = self.rate_limiter.config
        return {
            "trading_write": cfg.trading_write_limit,
            "auth": cfg.auth_limit,
            "health": cfg.health_limit,
            "general": cfg.general_limit,
        }.get(category, cfg.general_limit)

    def _check_and_increment(self, client_id: str, category: str) -> Tuple[bool, int, int]:
        """
        Register one request against the (client, category) fixed window.

        Returns (allowed, limit, remaining).
        """
        limit = self._limit_for_category(category)
        current_window = int(time.time() // 60)
        key = (client_id, category)

        with self._windows_lock:
            entry = self._windows.get(key)
            if entry is None or entry[0] != current_window:
                # New window for this key. Opportunistically evict stale
                # windows so the dict cannot grow without bound under a
                # spray of distinct client identifiers.
                if len(self._windows) > 50000:
                    stale = [
                        k for k, v in self._windows.items()
                        if v[0] != current_window
                    ]
                    for k in stale:
                        del self._windows[k]
                entry = [current_window, 0]
                self._windows[key] = entry
            entry[1] += 1
            count = entry[1]

        allowed = count <= limit
        remaining = max(0, limit - count)
        return allowed, limit, remaining

    def _get_rate_limit_key(self, path: str, method: str = "GET") -> str:
        """
        Determine rate limit category for a path + method.

        Args:
            path: Request path
            method: HTTP method (mutating methods on trade paths get the
                strict ``trading_write`` bucket; GET reads fall through to the
                generous ``general`` bucket so dashboard polling isn't 429'd).

        Returns:
            Rate limit category: 'trading_write', 'auth', 'health', or 'general'
        """
        path_lower = path.lower()
        is_mutating = method.upper() in ("POST", "PUT", "PATCH", "DELETE")

        # Check trading paths — only MUTATING requests get the strict bucket.
        if is_mutating:
            for trading_path in self.trading_paths:
                if path_lower.startswith(trading_path.lower()):
                    return "trading_write"

        # Check auth paths
        for auth_path in self.auth_paths:
            if path_lower.startswith(auth_path.lower()):
                return "auth"

        # Check health paths
        for health_path in self.health_paths:
            if path_lower.startswith(health_path.lower()):
                return "health"

        return "general"

    async def dispatch(self, request: Request, call_next):
        """
        Process request with rate limiting.

        Args:
            request: FastAPI request
            call_next: Next middleware/handler

        Returns:
            Response from handler or rate limit error
        """
        # Skip if rate limiting is disabled
        if not self.rate_limiter.enabled:
            return await call_next(request)

        # Get rate limit category (method-aware: read polls are not throttled
        # as trades).
        category = self._get_rate_limit_key(request.url.path, request.method)

        # Add rate limit info to request state for logging
        request.state.rate_limit_category = category

        # Enforce the limit (fail closed on abuse / brute force).
        client_id = get_client_identifier(request)
        allowed, limit, remaining = self._check_and_increment(client_id, category)

        if not allowed:
            retry_after = 60 - int(time.time() % 60)
            logger.warning(
                f"Rate limit exceeded: client={client_id}, category={category}, "
                f"limit={limit}/min, path={request.url.path}, method={request.method}"
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "success": False,
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests. Please slow down.",
                    "retry_after_seconds": retry_after,
                    "path": request.url.path,
                    "timestamp": int(time.time() * 1000),
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Category": category,
                },
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        response.headers["X-RateLimit-Category"] = category
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response


def rate_limit_middleware(config: Optional[RateLimitConfig] = None):
    """
    Factory function to create rate limit middleware.

    Args:
        config: Optional rate limit configuration

    Returns:
        RateLimitMiddleware class configured with limiter
    """
    limiter = get_rate_limiter(config)

    def middleware_factory(app):
        return RateLimitMiddleware(app, limiter)

    return middleware_factory
