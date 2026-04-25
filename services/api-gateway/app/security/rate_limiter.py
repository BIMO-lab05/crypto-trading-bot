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
import time
from dataclasses import dataclass
from typing import Optional, Callable
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
    trading_limit: int = 10      # Trading endpoints: 10 req/min
    auth_limit: int = 5          # Auth endpoints: 5 req/min
    health_limit: int = 60       # Health checks: 60 req/min
    general_limit: int = 30      # General API: 30 req/min
    enabled: bool = True         # Rate limiting enabled
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
        Decorator for trading endpoint rate limiting.

        Limit: 10 requests per minute (strict for trading safety)

        Usage:
            @app.post("/api/trading/buy")
            @rate_limiter.trading_limit
            async def buy(request: Request, ...):
                ...
        """
        return self._create_limit_decorator(self.config.trading_limit)

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

        # Path prefixes for different rate limits
        self.trading_paths = ["/api/trading", "/api/portfolio/buy", "/api/portfolio/sell"]
        self.auth_paths = ["/auth/"]
        self.health_paths = ["/health", "/ready", "/status"]

    def _get_rate_limit_key(self, path: str) -> str:
        """
        Determine rate limit category for a path.

        Args:
            path: Request path

        Returns:
            Rate limit category: 'trading', 'auth', 'health', or 'general'
        """
        path_lower = path.lower()

        # Check trading paths
        for trading_path in self.trading_paths:
            if path_lower.startswith(trading_path.lower()):
                return "trading"

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

        # Get rate limit category
        category = self._get_rate_limit_key(request.url.path)

        # Add rate limit info to request state for logging
        request.state.rate_limit_category = category

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        response.headers["X-RateLimit-Category"] = category

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
