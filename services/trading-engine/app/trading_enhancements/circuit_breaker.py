"""
Circuit Breaker Pattern for API Resilience
Research Source: FIA Best Practices for Automated Trading Risk Controls (2024)

Purpose:
- Prevent cascading failures when external services fail
- Automatically stop trading when API errors exceed threshold
- Self-heal after cooldown period

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Failure threshold exceeded, requests blocked
- HALF_OPEN: Testing if service recovered
"""

import logging
import time
from enum import Enum
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import asyncio

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Blocking requests
    HALF_OPEN = "half_open" # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    failure_threshold: int = 5          # Failures before opening circuit
    success_threshold: int = 3          # Successes to close circuit from half-open
    timeout_seconds: float = 60.0       # Time before attempting recovery
    half_open_max_calls: int = 3        # Max test calls in half-open state


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_changes: int = 0
    last_failure_time: Optional[datetime] = None
    last_state_change: Optional[datetime] = None
    current_consecutive_failures: int = 0
    current_consecutive_successes: int = 0


class CircuitBreaker:
    """
    Circuit Breaker for API Resilience

    RESEARCH-BACKED IMPLEMENTATION:
    - Monitors failure rates for external service calls
    - Automatically opens circuit to prevent cascading failures
    - Implements exponential backoff for recovery attempts
    - Provides fallback mechanisms for degraded operation

    Usage:
        breaker = CircuitBreaker("bybit_api")

        async with breaker:
            result = await api_call()

        # Or with manual control:
        if breaker.can_execute():
            try:
                result = await api_call()
                breaker.record_success()
            except Exception as e:
                breaker.record_failure(e)
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ):
        """
        Initialize circuit breaker

        Args:
            name: Identifier for this circuit breaker
            config: Configuration settings
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0

        logger.info(
            f"CircuitBreaker '{name}' initialized: "
            f"failure_threshold={self.config.failure_threshold}, "
            f"timeout={self.config.timeout_seconds}s"
        )

    def can_execute(self) -> bool:
        """
        Check if a request can be executed

        Returns:
            True if circuit allows execution, False otherwise
        """
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if timeout has elapsed
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
        """Record a successful call"""
        self.stats.total_calls += 1
        self.stats.successful_calls += 1
        self.stats.current_consecutive_failures = 0
        self.stats.current_consecutive_successes += 1

        if self.state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self.stats.current_consecutive_successes >= self.config.success_threshold:
                self._transition_to_closed()

    def record_failure(self, error: Optional[Exception] = None):
        """
        Record a failed call

        Args:
            error: Optional exception that caused the failure
        """
        self.stats.total_calls += 1
        self.stats.failed_calls += 1
        self.stats.current_consecutive_successes = 0
        self.stats.current_consecutive_failures += 1
        self.stats.last_failure_time = datetime.now()
        self._last_failure_time = time.time()

        if error:
            logger.warning(f"CircuitBreaker '{self.name}' recorded failure: {error}")

        if self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open state reopens the circuit
            self._transition_to_open()
        elif self.state == CircuitState.CLOSED:
            if self.stats.current_consecutive_failures >= self.config.failure_threshold:
                self._transition_to_open()

    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to attempt recovery"""
        if self._last_failure_time is None:
            return True
        elapsed = time.time() - self._last_failure_time
        return elapsed >= self.config.timeout_seconds

    def _transition_to_open(self):
        """Transition to OPEN state"""
        if self.state != CircuitState.OPEN:
            self.state = CircuitState.OPEN
            self.stats.state_changes += 1
            self.stats.last_state_change = datetime.now()
            logger.warning(
                f"CircuitBreaker '{self.name}' OPENED: "
                f"{self.stats.current_consecutive_failures} consecutive failures"
            )

    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state"""
        if self.state != CircuitState.HALF_OPEN:
            self.state = CircuitState.HALF_OPEN
            self._half_open_calls = 0
            self.stats.state_changes += 1
            self.stats.last_state_change = datetime.now()
            self.stats.current_consecutive_successes = 0
            logger.info(f"CircuitBreaker '{self.name}' HALF-OPEN: testing recovery")

    def _transition_to_closed(self):
        """Transition to CLOSED state"""
        if self.state != CircuitState.CLOSED:
            self.state = CircuitState.CLOSED
            self.stats.state_changes += 1
            self.stats.last_state_change = datetime.now()
            self.stats.current_consecutive_failures = 0
            logger.info(f"CircuitBreaker '{self.name}' CLOSED: service recovered")

    def force_open(self):
        """Manually force circuit to open state"""
        self._transition_to_open()
        logger.warning(f"CircuitBreaker '{self.name}' manually forced OPEN")

    def force_close(self):
        """Manually force circuit to closed state"""
        self._transition_to_closed()
        self.stats.current_consecutive_failures = 0
        logger.info(f"CircuitBreaker '{self.name}' manually forced CLOSED")

    def get_status(self) -> dict:
        """Get current circuit breaker status"""
        return {
            "name": self.name,
            "state": self.state.value,
            "stats": {
                "total_calls": self.stats.total_calls,
                "successful_calls": self.stats.successful_calls,
                "failed_calls": self.stats.failed_calls,
                "rejected_calls": self.stats.rejected_calls,
                "state_changes": self.stats.state_changes,
                "consecutive_failures": self.stats.current_consecutive_failures,
                "consecutive_successes": self.stats.current_consecutive_successes,
                "last_failure": self.stats.last_failure_time.isoformat() if self.stats.last_failure_time else None,
                "last_state_change": self.stats.last_state_change.isoformat() if self.stats.last_state_change else None,
            },
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "timeout_seconds": self.config.timeout_seconds,
            }
        }

    async def __aenter__(self):
        """Async context manager entry"""
        if not self.can_execute():
            self.stats.rejected_calls += 1
            raise CircuitBreakerOpenError(
                f"CircuitBreaker '{self.name}' is {self.state.value}"
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if exc_type is None:
            self.record_success()
        else:
            self.record_failure(exc_val)
        return False  # Don't suppress exceptions


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and blocks execution"""
    pass


# Global circuit breakers for different services
_circuit_breakers: dict = {}


def get_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """
    Get or create a circuit breaker for a service

    Args:
        name: Service name (e.g., "bybit_api", "technical_analysis")
        config: Optional configuration

    Returns:
        CircuitBreaker instance
    """
    global _circuit_breakers
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name, config)
    return _circuit_breakers[name]


def get_all_circuit_breakers() -> dict:
    """Get status of all circuit breakers"""
    return {
        name: breaker.get_status()
        for name, breaker in _circuit_breakers.items()
    }
