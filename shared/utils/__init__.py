"""
Shared Utilities for Crypto Trading Bot
Provides common functionality across all microservices
"""

from .circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerError,
    ExponentialBackoff,
    circuit_breaker,
    retry_with_backoff
)

from .structured_logging import (
    StructuredLogger,
    RequestContextLogger,
    setup_logging,
    log_performance
)

from .db_pool import (
    PostgresPool,
    RedisPool,
    DatabaseManager,
    db_manager,
    get_postgres,
    get_timescale,
    get_redis
)

from .graceful_shutdown import (
    GracefulShutdownHandler,
    ShutdownContext,
    with_graceful_shutdown,
    HealthCheckServer
)

from .rate_limiter import (
    RateLimiter,
    RateLimitConfig,
    RateLimitExceeded,
    SlidingWindowRateLimiter,
    TokenBucketRateLimiter,
    FixedWindowRateLimiter,
    AdaptiveRateLimiter,
    rate_limit
)

from .input_validation import (
    InputValidator,
    InputValidationMiddleware,
    SecurityPatterns,
    sanitize_input,
    is_safe_filename,
    validate_email,
    validate_url
)

from .dead_letter_queue import (
    DeadLetterQueue,
    DLQMessage,
    DLQMessageStatus,
    DLQWorker,
    create_dlq
)

__all__ = [
    # Circuit Breaker
    'CircuitBreaker',
    'CircuitState',
    'CircuitBreakerError',
    'ExponentialBackoff',
    'circuit_breaker',
    'retry_with_backoff',
    # Logging
    'StructuredLogger',
    'RequestContextLogger',
    'setup_logging',
    'log_performance',
    # Database Pooling
    'PostgresPool',
    'RedisPool',
    'DatabaseManager',
    'db_manager',
    'get_postgres',
    'get_timescale',
    'get_redis',
    # Graceful Shutdown
    'GracefulShutdownHandler',
    'ShutdownContext',
    'with_graceful_shutdown',
    'HealthCheckServer',
    # Rate Limiting
    'RateLimiter',
    'RateLimitConfig',
    'RateLimitExceeded',
    'SlidingWindowRateLimiter',
    'TokenBucketRateLimiter',
    'FixedWindowRateLimiter',
    'AdaptiveRateLimiter',
    'rate_limit',
    # Input Validation
    'InputValidator',
    'InputValidationMiddleware',
    'SecurityPatterns',
    'sanitize_input',
    'is_safe_filename',
    'validate_email',
    'validate_url',
    # Dead Letter Queue
    'DeadLetterQueue',
    'DLQMessage',
    'DLQMessageStatus',
    'DLQWorker',
    'create_dlq'
]
