"""
Circuit Breaker Pattern Implementation
Provides fault tolerance for external API calls with exponential backoff retry
"""

import asyncio
import time
from enum import Enum
from typing import Callable, Optional, Any
from functools import wraps
import logging

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"  # Normal operation, requests allowed
    OPEN = "open"      # Too many failures, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open"""
    pass


class CircuitBreaker:
    """
    Circuit Breaker implementation for resilient external API calls

    States:
    - CLOSED: Normal operation, all requests pass through
    - OPEN: Service is failing, requests are rejected immediately
    - HALF_OPEN: Testing if service recovered with limited requests

    Args:
        failure_threshold: Number of failures before opening circuit (default: 5)
        recovery_timeout: Seconds to wait before trying half-open (default: 60)
        expected_exception: Exception type to catch (default: Exception)
        success_threshold: Successful calls needed in half-open to close (default: 2)
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception,
        success_threshold: int = 2,
        name: str = "unknown"
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.success_threshold = success_threshold
        self.name = name

        # State tracking
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.last_state_change = time.time()

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to try half-open state"""
        if self.state == CircuitState.OPEN and self.last_failure_time:
            return time.time() - self.last_failure_time >= self.recovery_timeout
        return False

    def _record_success(self):
        """Record a successful call"""
        self.failure_count = 0

        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            logger.info(
                f"Circuit breaker '{self.name}' half-open success "
                f"({self.success_count}/{self.success_threshold})"
            )

            if self.success_count >= self.success_threshold:
                self._close_circuit()
        elif self.state == CircuitState.OPEN:
            # Shouldn't happen, but handle gracefully
            logger.warning(f"Success recorded while circuit breaker '{self.name}' is OPEN")

    def _record_failure(self):
        """Record a failed call"""
        self.failure_count += 1
        self.success_count = 0
        self.last_failure_time = time.time()

        logger.warning(
            f"Circuit breaker '{self.name}' failure "
            f"({self.failure_count}/{self.failure_threshold})"
        )

        if self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open immediately reopens circuit
            self._open_circuit()
        elif self.failure_count >= self.failure_threshold:
            self._open_circuit()

    def _open_circuit(self):
        """Open the circuit breaker"""
        if self.state != CircuitState.OPEN:
            self.state = CircuitState.OPEN
            self.last_state_change = time.time()
            logger.error(
                f"Circuit breaker '{self.name}' OPENED after "
                f"{self.failure_count} failures"
            )

    def _close_circuit(self):
        """Close the circuit breaker"""
        if self.state != CircuitState.CLOSED:
            self.state = CircuitState.CLOSED
            self.success_count = 0
            self.last_state_change = time.time()
            logger.info(f"Circuit breaker '{self.name}' CLOSED - service recovered")

    def _half_open_circuit(self):
        """Move to half-open state to test service"""
        if self.state != CircuitState.HALF_OPEN:
            self.state = CircuitState.HALF_OPEN
            self.success_count = 0
            self.last_state_change = time.time()
            logger.info(f"Circuit breaker '{self.name}' HALF-OPEN - testing service")

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function through circuit breaker (sync version)

        Args:
            func: Function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function

        Returns:
            Function result if successful

        Raises:
            CircuitBreakerError: If circuit is open
            expected_exception: If function fails
        """
        # Check if we should attempt recovery
        if self._should_attempt_reset():
            self._half_open_circuit()

        # Reject if circuit is open
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerError(
                f"Circuit breaker '{self.name}' is OPEN. "
                f"Service unavailable. Try again in "
                f"{self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s"
            )

        try:
            # Execute the function
            result = func(*args, **kwargs)
            self._record_success()
            return result

        except self.expected_exception as e:
            self._record_failure()
            raise

    async def call_async(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute async function through circuit breaker

        Args:
            func: Async function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function

        Returns:
            Function result if successful

        Raises:
            CircuitBreakerError: If circuit is open
            expected_exception: If function fails
        """
        # Check if we should attempt recovery
        if self._should_attempt_reset():
            self._half_open_circuit()

        # Reject if circuit is open
        if self.state == CircuitState.OPEN:
            remaining = self.recovery_timeout - (time.time() - self.last_failure_time)
            raise CircuitBreakerError(
                f"Circuit breaker '{self.name}' is OPEN. "
                f"Service unavailable. Try again in {remaining:.0f}s"
            )

        try:
            # Execute the async function
            result = await func(*args, **kwargs)
            self._record_success()
            return result

        except self.expected_exception as e:
            self._record_failure()
            raise

    def get_state(self) -> dict:
        """Get current circuit breaker state"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "last_state_change": self.last_state_change,
            "time_in_state": time.time() - self.last_state_change
        }


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    expected_exception: type = Exception,
    name: Optional[str] = None
):
    """
    Decorator for circuit breaker pattern

    Usage:
        @circuit_breaker(failure_threshold=3, recovery_timeout=30)
        async def call_external_api():
            # API call here
            pass
    """
    def decorator(func: Callable):
        breaker_name = name or func.__name__
        breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            expected_exception=expected_exception,
            name=breaker_name
        )

        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await breaker.call_async(func, *args, **kwargs)
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                return breaker.call(func, *args, **kwargs)
            return sync_wrapper

    return decorator


class ExponentialBackoff:
    """
    Exponential backoff retry strategy

    Retry delays: base_delay * (2 ^ attempt)
    Example with base_delay=1: 1s, 2s, 4s, 8s, 16s...

    Args:
        max_retries: Maximum number of retry attempts (default: 5)
        base_delay: Initial delay in seconds (default: 1)
        max_delay: Maximum delay in seconds (default: 60)
        exponential_base: Base for exponential calculation (default: 2)
        jitter: Add randomness to prevent thundering herd (default: True)
    """

    def __init__(
        self,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number"""
        import random

        # Calculate exponential delay
        delay = min(
            self.base_delay * (self.exponential_base ** attempt),
            self.max_delay
        )

        # Add jitter to prevent thundering herd
        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)  # 50-100% of calculated delay

        return delay

    async def retry_async(
        self,
        func: Callable,
        *args,
        exceptions: tuple = (Exception,),
        **kwargs
    ) -> Any:
        """
        Retry async function with exponential backoff

        Args:
            func: Async function to retry
            *args: Positional arguments
            exceptions: Tuple of exceptions to catch and retry
            **kwargs: Keyword arguments

        Returns:
            Function result if successful

        Raises:
            Last exception if all retries exhausted
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)

            except exceptions as e:
                last_exception = e

                if attempt < self.max_retries:
                    delay = self.get_delay(attempt)
                    logger.warning(
                        f"Retry attempt {attempt + 1}/{self.max_retries} for "
                        f"{func.__name__} after {delay:.2f}s. Error: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"All {self.max_retries} retry attempts exhausted for "
                        f"{func.__name__}. Giving up."
                    )

        raise last_exception

    def retry(
        self,
        func: Callable,
        *args,
        exceptions: tuple = (Exception,),
        **kwargs
    ) -> Any:
        """
        Retry sync function with exponential backoff

        Args:
            func: Function to retry
            *args: Positional arguments
            exceptions: Tuple of exceptions to catch and retry
            **kwargs: Keyword arguments

        Returns:
            Function result if successful

        Raises:
            Last exception if all retries exhausted
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)

            except exceptions as e:
                last_exception = e

                if attempt < self.max_retries:
                    delay = self.get_delay(attempt)
                    logger.warning(
                        f"Retry attempt {attempt + 1}/{self.max_retries} for "
                        f"{func.__name__} after {delay:.2f}s. Error: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"All {self.max_retries} retry attempts exhausted for "
                        f"{func.__name__}. Giving up."
                    )

        raise last_exception


def retry_with_backoff(
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,)
):
    """
    Decorator for retry with exponential backoff

    Usage:
        @retry_with_backoff(max_retries=3, base_delay=2, exceptions=(ValueError, ConnectionError))
        async def unstable_operation():
            # Operation that might fail
            pass
    """
    backoff = ExponentialBackoff(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay
    )

    def decorator(func: Callable):
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await backoff.retry_async(func, *args, exceptions=exceptions, **kwargs)
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                return backoff.retry(func, *args, exceptions=exceptions, **kwargs)
            return sync_wrapper

    return decorator
