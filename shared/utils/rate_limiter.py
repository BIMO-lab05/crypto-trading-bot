"""
API Rate Limiting and Throttling
Protects services from abuse and ensures fair resource allocation
"""

import time
import asyncio
from typing import Dict, Optional, Callable
from collections import deque
from dataclasses import dataclass
from functools import wraps
import logging

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration"""
    max_requests: int  # Maximum requests allowed
    window_seconds: int  # Time window in seconds
    strategy: str = "sliding_window"  # sliding_window, fixed_window, token_bucket


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded"""
    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after:.2f} seconds")


class SlidingWindowRateLimiter:
    """
    Sliding window rate limiter

    Most accurate method - tracks individual requests
    Memory usage: O(n) where n = max_requests
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: deque = deque()

    def _clean_old_requests(self, current_time: float):
        """Remove requests outside the window"""
        cutoff_time = current_time - self.window_seconds

        while self.requests and self.requests[0] < cutoff_time:
            self.requests.popleft()

    def is_allowed(self) -> bool:
        """Check if request is allowed"""
        current_time = time.time()
        self._clean_old_requests(current_time)

        if len(self.requests) < self.max_requests:
            self.requests.append(current_time)
            return True

        return False

    def get_retry_after(self) -> float:
        """Get seconds until next request is allowed"""
        if not self.requests:
            return 0.0

        current_time = time.time()
        self._clean_old_requests(current_time)

        if len(self.requests) < self.max_requests:
            return 0.0

        # Return time until oldest request expires
        return self.requests[0] + self.window_seconds - current_time

    def get_remaining(self) -> int:
        """Get remaining requests in current window"""
        current_time = time.time()
        self._clean_old_requests(current_time)
        return max(0, self.max_requests - len(self.requests))


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter

    Allows bursts while maintaining average rate
    Memory usage: O(1)
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.capacity = max_requests
        self.tokens = max_requests
        self.refill_rate = max_requests / window_seconds
        self.last_refill = time.time()

    def _refill(self):
        """Refill tokens based on elapsed time"""
        current_time = time.time()
        elapsed = current_time - self.last_refill

        new_tokens = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_refill = current_time

    def is_allowed(self) -> bool:
        """Check if request is allowed"""
        self._refill()

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True

        return False

    def get_retry_after(self) -> float:
        """Get seconds until next request is allowed"""
        self._refill()

        if self.tokens >= 1.0:
            return 0.0

        # Calculate time needed to accumulate 1 token
        tokens_needed = 1.0 - self.tokens
        return tokens_needed / self.refill_rate

    def get_remaining(self) -> int:
        """Get remaining requests"""
        self._refill()
        return int(self.tokens)


class FixedWindowRateLimiter:
    """
    Fixed window rate limiter

    Simple and memory efficient
    Memory usage: O(1)
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.window_start = time.time()
        self.request_count = 0

    def _reset_if_needed(self):
        """Reset counter if window has passed"""
        current_time = time.time()
        if current_time - self.window_start >= self.window_seconds:
            self.window_start = current_time
            self.request_count = 0

    def is_allowed(self) -> bool:
        """Check if request is allowed"""
        self._reset_if_needed()

        if self.request_count < self.max_requests:
            self.request_count += 1
            return True

        return False

    def get_retry_after(self) -> float:
        """Get seconds until next request is allowed"""
        self._reset_if_needed()

        if self.request_count < self.max_requests:
            return 0.0

        # Return time until window resets
        return self.window_seconds - (time.time() - self.window_start)

    def get_remaining(self) -> int:
        """Get remaining requests in current window"""
        self._reset_if_needed()
        return max(0, self.max_requests - self.request_count)


class RateLimiter:
    """
    Multi-key rate limiter with strategy selection

    Supports:
    - Per-user rate limiting
    - Per-IP rate limiting
    - Per-endpoint rate limiting
    - Global rate limiting
    """

    def __init__(
        self,
        config: RateLimitConfig,
        strategy: Optional[str] = None
    ):
        self.config = config
        self.strategy = strategy or config.strategy
        self.limiters: Dict[str, any] = {}

    def _get_limiter(self, key: str):
        """Get or create limiter for key"""
        if key not in self.limiters:
            if self.strategy == "sliding_window":
                self.limiters[key] = SlidingWindowRateLimiter(
                    self.config.max_requests,
                    self.config.window_seconds
                )
            elif self.strategy == "token_bucket":
                self.limiters[key] = TokenBucketRateLimiter(
                    self.config.max_requests,
                    self.config.window_seconds
                )
            elif self.strategy == "fixed_window":
                self.limiters[key] = FixedWindowRateLimiter(
                    self.config.max_requests,
                    self.config.window_seconds
                )
            else:
                raise ValueError(f"Unknown strategy: {self.strategy}")

        return self.limiters[key]

    def check_rate_limit(self, key: str) -> bool:
        """
        Check if request is allowed for given key

        Args:
            key: Identifier (user_id, ip_address, endpoint, etc.)

        Returns:
            True if allowed, False otherwise

        Raises:
            RateLimitExceeded: If rate limit exceeded
        """
        limiter = self._get_limiter(key)

        if limiter.is_allowed():
            return True

        retry_after = limiter.get_retry_after()
        logger.warning(
            f"Rate limit exceeded for key '{key}'. "
            f"Retry after {retry_after:.2f}s"
        )
        raise RateLimitExceeded(retry_after)

    def get_rate_limit_info(self, key: str) -> Dict:
        """Get rate limit information for key"""
        limiter = self._get_limiter(key)

        return {
            "limit": self.config.max_requests,
            "remaining": limiter.get_remaining(),
            "reset": int(time.time() + limiter.get_retry_after()),
            "retry_after": limiter.get_retry_after(),
            "window_seconds": self.config.window_seconds
        }

    def cleanup_old_limiters(self, inactive_seconds: int = 3600):
        """Remove limiters that haven't been used recently"""
        # Implementation would track last access time
        # and remove stale entries to prevent memory leaks
        pass


def rate_limit(
    max_requests: int = 100,
    window_seconds: int = 60,
    strategy: str = "sliding_window",
    key_func: Optional[Callable] = None
):
    """
    Decorator for rate limiting functions

    Args:
        max_requests: Maximum requests allowed
        window_seconds: Time window in seconds
        strategy: Rate limiting strategy
        key_func: Function to extract key from arguments

    Usage:
        @rate_limit(max_requests=10, window_seconds=60)
        async def api_endpoint(user_id: str):
            return {"data": "response"}

        @rate_limit(
            max_requests=5,
            window_seconds=60,
            key_func=lambda request: request.client.host
        )
        async def login(request):
            # Per-IP rate limiting
            pass
    """
    config = RateLimitConfig(
        max_requests=max_requests,
        window_seconds=window_seconds,
        strategy=strategy
    )
    limiter = RateLimiter(config)

    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Extract key
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                # Default: use first argument as key
                key = str(args[0]) if args else "global"

            # Check rate limit
            limiter.check_rate_limit(key)

            # Execute function
            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Extract key
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                key = str(args[0]) if args else "global"

            # Check rate limit
            limiter.check_rate_limit(key)

            # Execute function
            return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


class AdaptiveRateLimiter:
    """
    Adaptive rate limiter that adjusts limits based on system load

    Features:
    - Automatic adjustment based on error rates
    - Circuit breaker integration
    - Load-based throttling
    """

    def __init__(
        self,
        base_config: RateLimitConfig,
        min_multiplier: float = 0.5,
        max_multiplier: float = 2.0
    ):
        self.base_config = base_config
        self.min_multiplier = min_multiplier
        self.max_multiplier = max_multiplier
        self.current_multiplier = 1.0

        self.success_count = 0
        self.error_count = 0
        self.adjustment_threshold = 100  # Adjust after 100 requests

    def adjust_multiplier(self):
        """Adjust rate limit multiplier based on success/error ratio"""
        total_requests = self.success_count + self.error_count

        if total_requests < self.adjustment_threshold:
            return

        error_rate = self.error_count / total_requests

        # Decrease limits if error rate is high
        if error_rate > 0.2:  # > 20% errors
            self.current_multiplier = max(
                self.min_multiplier,
                self.current_multiplier * 0.8
            )
            logger.warning(
                f"High error rate ({error_rate:.2%}), "
                f"reducing rate limit to {self.current_multiplier:.2f}x"
            )

        # Increase limits if error rate is low
        elif error_rate < 0.05:  # < 5% errors
            self.current_multiplier = min(
                self.max_multiplier,
                self.current_multiplier * 1.1
            )
            logger.info(
                f"Low error rate ({error_rate:.2%}), "
                f"increasing rate limit to {self.current_multiplier:.2f}x"
            )

        # Reset counters
        self.success_count = 0
        self.error_count = 0

    def get_adjusted_config(self) -> RateLimitConfig:
        """Get rate limit config with current multiplier"""
        return RateLimitConfig(
            max_requests=int(self.base_config.max_requests * self.current_multiplier),
            window_seconds=self.base_config.window_seconds,
            strategy=self.base_config.strategy
        )

    def record_success(self):
        """Record successful request"""
        self.success_count += 1
        self.adjust_multiplier()

    def record_error(self):
        """Record failed request"""
        self.error_count += 1
        self.adjust_multiplier()


# FastAPI middleware example (commented out - requires fastapi)
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI()

rate_limiter = RateLimiter(
    RateLimitConfig(max_requests=100, window_seconds=60)
)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Extract client IP
    client_ip = request.client.host

    try:
        # Check rate limit
        rate_limiter.check_rate_limit(client_ip)

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        info = rate_limiter.get_rate_limit_info(client_ip)
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(info["reset"])

        return response

    except RateLimitExceeded as e:
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "retry_after": e.retry_after},
            headers={"Retry-After": str(int(e.retry_after))}
        )
"""
