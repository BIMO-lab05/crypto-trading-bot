"""
Bybit Connector Service - Circuit Breaker Pattern
Purpose: Implement circuit breaker to prevent cascading failures
"""

import time
from enum import Enum
from typing import Callable, Any, Optional
from functools import wraps
import asyncio

from app.exceptions import CircuitBreakerOpenException


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation, requests allowed
    OPEN = "open"          # Too many failures, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker implementation for API resilience
    
    States:
    - CLOSED: Normal operation, all requests pass through
    - OPEN: Too many failures, requests fail fast without calling API
    - HALF_OPEN: Testing recovery, allow one request through
    
    Flow:
    CLOSED -> (failures exceed threshold) -> OPEN
    OPEN -> (timeout expires) -> HALF_OPEN
    HALF_OPEN -> (request succeeds) -> CLOSED
    HALF_OPEN -> (request fails) -> OPEN
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception
    ):
        """
        Initialize circuit breaker
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            expected_exception: Exception type to count as failure
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        # State tracking
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.success_count = 0
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection (sync version)
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
        
        Returns:
            Function result
        
        Raises:
            CircuitBreakerOpenException: If circuit is open
            Exception: Original exception if function fails
        """
        # Check if circuit should move to half-open
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitBreakerOpenException(
                    failure_count=self.failure_count,
                    threshold=self.failure_threshold,
                    reset_timeout=self.recovery_timeout
                )
        
        try:
            # Execute function
            result = func(*args, **kwargs)
            
            # Success - record and potentially close circuit
            self._on_success()
            return result
            
        except self.expected_exception as e:
            # Failure - record and potentially open circuit
            self._on_failure()
            raise e
    
    async def call_async(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute async function with circuit breaker protection
        
        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
        
        Returns:
            Function result
        
        Raises:
            CircuitBreakerOpenException: If circuit is open
            Exception: Original exception if function fails
        """
        # Check if circuit should move to half-open
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitBreakerOpenException(
                    failure_count=self.failure_count,
                    threshold=self.failure_threshold,
                    reset_timeout=self.recovery_timeout
                )
        
        try:
            # Execute async function
            result = await func(*args, **kwargs)
            
            # Success - record and potentially close circuit
            self._on_success()
            return result
            
        except self.expected_exception as e:
            # Failure - record and potentially open circuit
            self._on_failure()
            raise e
    
    def _on_success(self):
        """Handle successful request"""
        self.failure_count = 0
        self.success_count += 1
        
        # If in half-open state, close the circuit
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
    
    def _on_failure(self):
        """Handle failed request"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        # If in half-open state, reopen circuit immediately
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
        
        # If failure threshold exceeded, open circuit
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
    
    def _should_attempt_reset(self) -> bool:
        """
        Check if enough time has passed to attempt circuit reset
        
        Returns:
            True if should attempt reset, False otherwise
        """
        if self.last_failure_time is None:
            return False
        
        time_since_failure = time.time() - self.last_failure_time
        return time_since_failure >= self.recovery_timeout
    
    def reset(self):
        """Manually reset circuit breaker to closed state"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
    
    def get_state(self) -> dict:
        """
        Get current circuit breaker state
        
        Returns:
            Dict with state information
        """
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "last_failure_time": self.last_failure_time,
            "time_until_retry": self._time_until_retry() if self.state == CircuitState.OPEN else 0
        }
    
    def _time_until_retry(self) -> float:
        """Calculate seconds until retry attempt"""
        if self.last_failure_time is None:
            return 0
        
        elapsed = time.time() - self.last_failure_time
        remaining = max(0, self.recovery_timeout - elapsed)
        return remaining


# Decorator for easy circuit breaker application
def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    expected_exception: type = Exception
):
    """
    Decorator to apply circuit breaker to a function
    
    Args:
        failure_threshold: Failures before opening
        recovery_timeout: Seconds before retry
        expected_exception: Exception type to track
    
    Example:
        @circuit_breaker(failure_threshold=3, recovery_timeout=30)
        async def risky_api_call():
            # Your code here
            pass
    """
    breaker = CircuitBreaker(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        expected_exception=expected_exception
    )
    
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await breaker.call_async(func, *args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
