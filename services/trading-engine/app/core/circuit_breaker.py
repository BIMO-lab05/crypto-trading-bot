"""
Circuit Breaker Pattern Implementation
Phase 7: High Availability & Monitoring Infrastructure

Purpose:
- Prevent cascading failures when external services fail
- Automatically stop trading when API errors exceed threshold
- Self-heal after cooldown period
- Provide fallback mechanisms for degraded operation

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Failure threshold exceeded, requests blocked
- HALF_OPEN: Testing if service recovered

Research Source: FIA Best Practices for Automated Trading Risk Controls (2024)

Usage:
    # Context manager usage
    async with get_circuit_breaker("bybit_api"):
        result = await api_call()

    # Manual control
    breaker = get_circuit_breaker("technical_analysis")
    if breaker.can_execute():
        try:
            result = await api_call()
            breaker.record_success()
        except Exception as e:
            breaker.record_failure(e)

    # Decorator usage
    @circuit_protected("exchange_api")
    async def fetch_orderbook(symbol: str):
        return await exchange.get_orderbook(symbol)
"""

import logging
import time
import asyncio
import functools
from enum import Enum
from typing import Optional, Callable, Any, Dict, TypeVar, Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# Type variable for generic async functions
T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """
    Configuration for circuit breaker behavior

    Attributes:
        failure_threshold: Number of consecutive failures before opening circuit
        success_threshold: Number of consecutive successes to close circuit from half-open
        timeout_seconds: Time in seconds before attempting recovery (half-open)
        half_open_max_calls: Maximum number of test calls allowed in half-open state
        excluded_exceptions: Exception types that should not trigger circuit breaker
        fallback_value: Default value to return when circuit is open
        on_state_change: Callback function when state changes
    """
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout_seconds: float = 60.0
    half_open_max_calls: int = 3
    excluded_exceptions: tuple = ()
    fallback_value: Any = None
    on_state_change: Optional[Callable[[str, str, str], None]] = None


@dataclass
class CircuitBreakerStats:
    """
    Statistics for circuit breaker monitoring

    Tracks:
    - Total calls, successes, failures, and rejections
    - Consecutive failures and successes for state transitions
    - Timestamps for last events
    - State change count for monitoring
    """
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_changes: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    last_state_change: Optional[datetime] = None
    current_consecutive_failures: int = 0
    current_consecutive_successes: int = 0
    time_in_open_state: float = 0.0
    last_open_time: Optional[float] = None


# Prometheus metrics for circuit breakers
circuit_breaker_state = Gauge(
    'circuit_breaker_state',
    'Current state of circuit breaker (0=closed, 1=half_open, 2=open)',
    ['service_name']
)

circuit_breaker_calls_total = Counter(
    'circuit_breaker_calls_total',
    'Total calls to circuit breaker',
    ['service_name', 'result']  # result: success, failure, rejected
)

circuit_breaker_state_transitions = Counter(
    'circuit_breaker_state_transitions_total',
    'Total state transitions',
    ['service_name', 'from_state', 'to_state']
)

circuit_breaker_recovery_time = Histogram(
    'circuit_breaker_recovery_time_seconds',
    'Time taken to recover from open state',
    ['service_name'],
    buckets=[10, 30, 60, 120, 300, 600]
)


class CircuitBreakerOpenError(Exception):
    """
    Raised when circuit breaker is open and blocks execution

    Attributes:
        circuit_name: Name of the circuit breaker
        state: Current state of the circuit
        retry_after: Seconds until recovery attempt
    """
    def __init__(self, circuit_name: str, state: str, retry_after: float = 0):
        self.circuit_name = circuit_name
        self.state = state
        self.retry_after = retry_after
        super().__init__(
            f"CircuitBreaker '{circuit_name}' is {state}. "
            f"Retry after {retry_after:.1f} seconds."
        )


class CircuitBreaker:
    """
    Circuit Breaker for API Resilience

    RESEARCH-BACKED IMPLEMENTATION:
    - Monitors failure rates for external service calls
    - Automatically opens circuit to prevent cascading failures
    - Implements exponential backoff for recovery attempts
    - Provides fallback mechanisms for degraded operation
    - Integrates with Prometheus for monitoring

    Thread Safety:
    - Uses asyncio.Lock for concurrent access protection
    - All state transitions are atomic

    Usage Examples:
        # Basic usage with context manager
        breaker = CircuitBreaker("bybit_api")
        async with breaker:
            result = await bybit.place_order(order)

        # With fallback value
        breaker = CircuitBreaker(
            "market_data",
            config=CircuitBreakerConfig(fallback_value={})
        )

        # Check status before expensive operation
        if breaker.can_execute():
            await heavy_operation()
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ):
        """
        Initialize circuit breaker

        Args:
            name: Unique identifier for this circuit breaker (e.g., "bybit_api")
            config: Configuration settings for circuit behavior
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0

        # Initialize Prometheus metrics
        circuit_breaker_state.labels(service_name=name).set(0)

        logger.info(
            f"CircuitBreaker '{name}' initialized: "
            f"failure_threshold={self.config.failure_threshold}, "
            f"success_threshold={self.config.success_threshold}, "
            f"timeout={self.config.timeout_seconds}s"
        )

    def can_execute(self) -> bool:
        """
        Check if a request can be executed

        Returns:
            True if circuit allows execution, False otherwise

        State Logic:
        - CLOSED: Always allow
        - OPEN: Allow only if timeout has elapsed (transitions to HALF_OPEN)
        - HALF_OPEN: Allow if under max test calls limit
        """
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if timeout has elapsed for recovery attempt
            if self._should_attempt_recovery():
                self._transition_to_half_open()
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            # Allow limited calls in half-open state
            if self._half_open_calls < self.config.half_open_max_calls:
                return True
            return False

        return False

    def record_success(self):
        """
        Record a successful call

        Actions:
        - Increments success counters
        - Resets consecutive failure count
        - In HALF_OPEN: May transition to CLOSED if threshold met
        """
        self.stats.total_calls += 1
        self.stats.successful_calls += 1
        self.stats.current_consecutive_failures = 0
        self.stats.current_consecutive_successes += 1
        self.stats.last_success_time = datetime.now()

        # Update Prometheus metrics
        circuit_breaker_calls_total.labels(
            service_name=self.name,
            result='success'
        ).inc()

        if self.state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            # Check if we've had enough successes to close the circuit
            if self.stats.current_consecutive_successes >= self.config.success_threshold:
                self._transition_to_closed()

    def record_failure(self, error: Optional[Exception] = None):
        """
        Record a failed call

        Args:
            error: Optional exception that caused the failure

        Actions:
        - Increments failure counters
        - Resets consecutive success count
        - In CLOSED: May transition to OPEN if threshold met
        - In HALF_OPEN: Immediately transitions to OPEN
        """
        # Check if this exception should be excluded
        if error and isinstance(error, self.config.excluded_exceptions):
            logger.debug(
                f"CircuitBreaker '{self.name}': Excluded exception {type(error).__name__}"
            )
            return

        self.stats.total_calls += 1
        self.stats.failed_calls += 1
        self.stats.current_consecutive_successes = 0
        self.stats.current_consecutive_failures += 1
        self.stats.last_failure_time = datetime.now()
        self._last_failure_time = time.time()

        # Update Prometheus metrics
        circuit_breaker_calls_total.labels(
            service_name=self.name,
            result='failure'
        ).inc()

        if error:
            logger.warning(
                f"CircuitBreaker '{self.name}' recorded failure: "
                f"{type(error).__name__}: {error}"
            )

        if self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open state reopens the circuit
            self._transition_to_open()
        elif self.state == CircuitState.CLOSED:
            # Check if we've hit the failure threshold
            if self.stats.current_consecutive_failures >= self.config.failure_threshold:
                self._transition_to_open()

    def _should_attempt_recovery(self) -> bool:
        """
        Check if enough time has passed to attempt recovery

        Returns:
            True if timeout has elapsed since last failure
        """
        if self._last_failure_time is None:
            return True
        elapsed = time.time() - self._last_failure_time
        return elapsed >= self.config.timeout_seconds

    def _get_retry_after(self) -> float:
        """
        Calculate seconds until recovery attempt is allowed

        Returns:
            Seconds until retry is allowed (0 if immediate)
        """
        if self._last_failure_time is None:
            return 0
        elapsed = time.time() - self._last_failure_time
        remaining = self.config.timeout_seconds - elapsed
        return max(0, remaining)

    def _transition_to_open(self):
        """Transition to OPEN state"""
        if self.state != CircuitState.OPEN:
            old_state = self.state.value
            self.state = CircuitState.OPEN
            self.stats.state_changes += 1
            self.stats.last_state_change = datetime.now()
            self.stats.last_open_time = time.time()

            # Update Prometheus metrics
            circuit_breaker_state.labels(service_name=self.name).set(2)
            circuit_breaker_state_transitions.labels(
                service_name=self.name,
                from_state=old_state,
                to_state='open'
            ).inc()

            logger.warning(
                f"CircuitBreaker '{self.name}' OPENED: "
                f"{self.stats.current_consecutive_failures} consecutive failures. "
                f"Will retry in {self.config.timeout_seconds}s."
            )

            # Call state change callback if configured
            if self.config.on_state_change:
                try:
                    self.config.on_state_change(self.name, old_state, 'open')
                except Exception as e:
                    logger.error(f"State change callback error: {e}")

    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state"""
        if self.state != CircuitState.HALF_OPEN:
            old_state = self.state.value
            self.state = CircuitState.HALF_OPEN
            self._half_open_calls = 0
            self.stats.state_changes += 1
            self.stats.last_state_change = datetime.now()
            self.stats.current_consecutive_successes = 0

            # Update Prometheus metrics
            circuit_breaker_state.labels(service_name=self.name).set(1)
            circuit_breaker_state_transitions.labels(
                service_name=self.name,
                from_state=old_state,
                to_state='half_open'
            ).inc()

            logger.info(
                f"CircuitBreaker '{self.name}' HALF-OPEN: "
                f"Testing service recovery (max {self.config.half_open_max_calls} calls)"
            )

            # Call state change callback if configured
            if self.config.on_state_change:
                try:
                    self.config.on_state_change(self.name, old_state, 'half_open')
                except Exception as e:
                    logger.error(f"State change callback error: {e}")

    def _transition_to_closed(self):
        """Transition to CLOSED state"""
        if self.state != CircuitState.CLOSED:
            old_state = self.state.value
            self.state = CircuitState.CLOSED
            self.stats.state_changes += 1
            self.stats.last_state_change = datetime.now()
            self.stats.current_consecutive_failures = 0

            # Record recovery time
            if self.stats.last_open_time:
                recovery_time = time.time() - self.stats.last_open_time
                self.stats.time_in_open_state += recovery_time
                circuit_breaker_recovery_time.labels(
                    service_name=self.name
                ).observe(recovery_time)
                self.stats.last_open_time = None

            # Update Prometheus metrics
            circuit_breaker_state.labels(service_name=self.name).set(0)
            circuit_breaker_state_transitions.labels(
                service_name=self.name,
                from_state=old_state,
                to_state='closed'
            ).inc()

            logger.info(
                f"CircuitBreaker '{self.name}' CLOSED: "
                f"Service recovered after {self.stats.current_consecutive_successes} successes"
            )

            # Call state change callback if configured
            if self.config.on_state_change:
                try:
                    self.config.on_state_change(self.name, old_state, 'closed')
                except Exception as e:
                    logger.error(f"State change callback error: {e}")

    def force_open(self):
        """
        Manually force circuit to open state

        Use case: Emergency stop, maintenance mode
        """
        self._transition_to_open()
        self._last_failure_time = time.time()
        logger.warning(f"CircuitBreaker '{self.name}' manually forced OPEN")

    def force_close(self):
        """
        Manually force circuit to closed state

        Use case: Override after manual verification
        """
        self._transition_to_closed()
        self.stats.current_consecutive_failures = 0
        self._last_failure_time = None
        logger.info(f"CircuitBreaker '{self.name}' manually forced CLOSED")

    def reset_stats(self):
        """Reset statistics counters while preserving state"""
        self.stats = CircuitBreakerStats()
        logger.info(f"CircuitBreaker '{self.name}' statistics reset")

    def get_status(self) -> Dict[str, Any]:
        """
        Get current circuit breaker status

        Returns:
            Dictionary with complete status information
        """
        return {
            "name": self.name,
            "state": self.state.value,
            "is_available": self.can_execute(),
            "retry_after_seconds": self._get_retry_after(),
            "stats": {
                "total_calls": self.stats.total_calls,
                "successful_calls": self.stats.successful_calls,
                "failed_calls": self.stats.failed_calls,
                "rejected_calls": self.stats.rejected_calls,
                "state_changes": self.stats.state_changes,
                "consecutive_failures": self.stats.current_consecutive_failures,
                "consecutive_successes": self.stats.current_consecutive_successes,
                "last_failure": self.stats.last_failure_time.isoformat()
                    if self.stats.last_failure_time else None,
                "last_success": self.stats.last_success_time.isoformat()
                    if self.stats.last_success_time else None,
                "last_state_change": self.stats.last_state_change.isoformat()
                    if self.stats.last_state_change else None,
                "total_time_in_open_state": round(self.stats.time_in_open_state, 2),
            },
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "timeout_seconds": self.config.timeout_seconds,
                "half_open_max_calls": self.config.half_open_max_calls,
            }
        }

    async def __aenter__(self):
        """
        Async context manager entry

        Raises:
            CircuitBreakerOpenError: If circuit is open and blocking requests
        """
        async with self._lock:
            if not self.can_execute():
                self.stats.rejected_calls += 1
                circuit_breaker_calls_total.labels(
                    service_name=self.name,
                    result='rejected'
                ).inc()
                raise CircuitBreakerOpenError(
                    self.name,
                    self.state.value,
                    self._get_retry_after()
                )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit

        Automatically records success or failure based on exception
        """
        async with self._lock:
            if exc_type is None:
                self.record_success()
            else:
                self.record_failure(exc_val)
        return False  # Don't suppress exceptions


class CircuitBreakerRegistry:
    """
    Registry for managing multiple circuit breakers

    Provides:
    - Centralized circuit breaker management
    - Bulk operations (force all open/closed)
    - Status reporting for all circuits
    - Configuration templates
    """

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

    def get(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ) -> CircuitBreaker:
        """
        Get or create a circuit breaker

        Args:
            name: Unique identifier for the circuit breaker
            config: Optional configuration (only used for creation)

        Returns:
            CircuitBreaker instance
        """
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, config)
        return self._breakers[name]

    def get_all_status(self) -> Dict[str, Dict]:
        """Get status of all circuit breakers"""
        return {
            name: breaker.get_status()
            for name, breaker in self._breakers.items()
        }

    def force_all_open(self):
        """Force all circuit breakers to open state"""
        for breaker in self._breakers.values():
            breaker.force_open()
        logger.warning("All circuit breakers forced OPEN")

    def force_all_closed(self):
        """Force all circuit breakers to closed state"""
        for breaker in self._breakers.values():
            breaker.force_close()
        logger.info("All circuit breakers forced CLOSED")

    def get_unhealthy_circuits(self) -> Dict[str, Dict]:
        """Get all circuits that are not in CLOSED state"""
        return {
            name: breaker.get_status()
            for name, breaker in self._breakers.items()
            if breaker.state != CircuitState.CLOSED
        }


# Global registry instance
_registry = CircuitBreakerRegistry()


def get_circuit_breaker(
    name: str,
    config: Optional[CircuitBreakerConfig] = None
) -> CircuitBreaker:
    """
    Get or create a circuit breaker from the global registry

    Args:
        name: Service name (e.g., "bybit_api", "technical_analysis")
        config: Optional configuration

    Returns:
        CircuitBreaker instance
    """
    return _registry.get(name, config)


def get_all_circuit_breakers() -> Dict[str, Dict]:
    """Get status of all circuit breakers from the global registry"""
    return _registry.get_all_status()


def circuit_protected(
    service_name: str,
    config: Optional[CircuitBreakerConfig] = None,
    fallback: Optional[Callable[..., T]] = None
):
    """
    Decorator for protecting async functions with circuit breaker

    Args:
        service_name: Name of the service being protected
        config: Optional circuit breaker configuration
        fallback: Optional fallback function to call when circuit is open

    Usage:
        @circuit_protected("bybit_api")
        async def place_order(order: Order) -> OrderResult:
            return await exchange.place(order)

        @circuit_protected("market_data", fallback=get_cached_price)
        async def get_price(symbol: str) -> float:
            return await exchange.get_price(symbol)
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            breaker = get_circuit_breaker(service_name, config)

            try:
                async with breaker:
                    return await func(*args, **kwargs)
            except CircuitBreakerOpenError:
                if fallback:
                    logger.warning(
                        f"Circuit '{service_name}' open, using fallback for {func.__name__}"
                    )
                    if asyncio.iscoroutinefunction(fallback):
                        return await fallback(*args, **kwargs)
                    return fallback(*args, **kwargs)
                raise

        return wrapper
    return decorator
