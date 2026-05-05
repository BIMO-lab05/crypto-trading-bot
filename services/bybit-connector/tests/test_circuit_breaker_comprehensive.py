"""
Comprehensive Tests for Circuit Breaker
Purpose: Achieve >80% test coverage for circuit_breaker.py
Coverage Target: All states, transitions, sync/async operations
"""

import pytest
import time
import asyncio
from unittest.mock import Mock, AsyncMock
from app.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    circuit_breaker
)
from app.exceptions import CircuitBreakerOpenException


# ============================================================================
# CIRCUIT BREAKER STATE TESTS
# ============================================================================

class TestCircuitBreakerStates:
    """Test circuit breaker state transitions"""

    def test_circuit_breaker_initial_state_closed(self):
        """Test circuit breaker starts in CLOSED state"""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.success_count == 0
        assert breaker.last_failure_time is None

    def test_circuit_state_enum_values(self):
        """Test CircuitState enum has expected values"""
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"


# ============================================================================
# SYNCHRONOUS CALL TESTS
# ============================================================================

class TestSynchronousCalls:
    """Test synchronous function calls through circuit breaker"""

    def test_call_success_closed_state(self):
        """Test successful call in CLOSED state"""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)

        def mock_function():
            return "success"

        result = breaker.call(mock_function)

        assert result == "success"
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.success_count == 1

    def test_call_multiple_successes(self):
        """Test multiple successful calls increment success counter"""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)

        def mock_function():
            return "success"

        for i in range(5):
            breaker.call(mock_function)

        assert breaker.success_count == 5
        assert breaker.failure_count == 0
        assert breaker.state == CircuitState.CLOSED

    def test_call_failure_increments_counter(self):
        """Test failed call increments failure counter"""
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30,
            expected_exception=ValueError
        )

        def failing_function():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            breaker.call(failing_function)

        assert breaker.failure_count == 1
        assert breaker.state == CircuitState.CLOSED  # Still closed, under threshold

    def test_call_failures_open_circuit(self):
        """Test circuit opens after threshold failures"""
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30,
            expected_exception=ValueError
        )

        def failing_function():
            raise ValueError("Test error")

        # First 2 failures - circuit stays closed
        for i in range(2):
            with pytest.raises(ValueError):
                breaker.call(failing_function)
            assert breaker.state == CircuitState.CLOSED

        # 3rd failure - circuit opens
        with pytest.raises(ValueError):
            breaker.call(failing_function)

        assert breaker.state == CircuitState.OPEN
        assert breaker.failure_count == 3

    def test_call_circuit_open_raises_exception(self):
        """Test calls fail fast when circuit is open"""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=60)

        def failing_function():
            raise Exception("Test error")

        # Trigger circuit to open
        with pytest.raises(Exception):
            breaker.call(failing_function)

        # Circuit should now be open
        assert breaker.state == CircuitState.OPEN

        # Next call should fail fast without calling function
        call_count = 0

        def tracked_function():
            nonlocal call_count
            call_count += 1
            return "should not be called"

        with pytest.raises(CircuitBreakerOpenException):
            breaker.call(tracked_function)

        # Function should not have been called
        assert call_count == 0

    def test_call_with_arguments(self):
        """Test circuit breaker passes arguments to function"""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)

        def function_with_args(a, b, c=None):
            return f"{a}-{b}-{c}"

        result = breaker.call(function_with_args, "arg1", "arg2", c="kwarg1")

        assert result == "arg1-arg2-kwarg1"

    def test_call_unexpected_exception_not_counted(self):
        """Test unexpected exceptions are not counted as failures"""
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30,
            expected_exception=ValueError
        )

        def function_wrong_error():
            raise TypeError("Different error type")

        with pytest.raises(TypeError):
            breaker.call(function_wrong_error)

        # Should not count as failure since it's not ValueError
        assert breaker.failure_count == 0
        assert breaker.state == CircuitState.CLOSED


# ============================================================================
# ASYNCHRONOUS CALL TESTS
# ============================================================================

class TestAsynchronousCalls:
    """Test asynchronous function calls through circuit breaker"""

    @pytest.mark.asyncio
    async def test_call_async_success(self):
        """Test successful async call"""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)

        async def async_function():
            await asyncio.sleep(0.01)
            return "async success"

        result = await breaker.call_async(async_function)

        assert result == "async success"
        assert breaker.success_count == 1
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_call_async_failure(self):
        """Test failed async call"""
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30,
            expected_exception=ValueError
        )

        async def failing_async_function():
            await asyncio.sleep(0.01)
            raise ValueError("Async error")

        with pytest.raises(ValueError):
            await breaker.call_async(failing_async_function)

        assert breaker.failure_count == 1

    @pytest.mark.asyncio
    async def test_call_async_opens_circuit(self):
        """Test circuit opens after async failures"""
        breaker = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=30,
            expected_exception=RuntimeError
        )

        async def failing_function():
            raise RuntimeError("Async failure")

        # Trigger failures to open circuit
        for i in range(2):
            with pytest.raises(RuntimeError):
                await breaker.call_async(failing_function)

        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_call_async_circuit_open_fails_fast(self):
        """Test async calls fail fast when circuit open"""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=60)

        async def failing_function():
            raise Exception("Error")

        # Open the circuit
        with pytest.raises(Exception):
            await breaker.call_async(failing_function)

        # Next call should fail fast
        call_count = 0

        async def tracked_async_function():
            nonlocal call_count
            call_count += 1
            return "should not execute"

        with pytest.raises(CircuitBreakerOpenException):
            await breaker.call_async(tracked_async_function)

        assert call_count == 0

    @pytest.mark.asyncio
    async def test_call_async_with_arguments(self):
        """Test async circuit breaker passes arguments correctly"""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)

        async def async_function_with_args(x, y, z=10):
            await asyncio.sleep(0.01)
            return x + y + z

        result = await breaker.call_async(async_function_with_args, 1, 2, z=3)

        assert result == 6


# ============================================================================
# CIRCUIT RECOVERY TESTS
# ============================================================================

class TestCircuitRecovery:
    """Test circuit breaker recovery mechanisms"""

    def test_should_attempt_reset_false_when_no_failures(self):
        """Test reset check returns False when no failures"""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)

        should_reset = breaker._should_attempt_reset()

        assert should_reset is False

    def test_should_attempt_reset_false_before_timeout(self):
        """Test reset check returns False before timeout expires"""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=60)

        # Simulate failure
        breaker.failure_count = 1
        breaker.last_failure_time = time.time()
        breaker.state = CircuitState.OPEN

        should_reset = breaker._should_attempt_reset()

        assert should_reset is False

    def test_should_attempt_reset_true_after_timeout(self):
        """Test reset check returns True after timeout expires"""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=1)

        # Simulate old failure
        breaker.failure_count = 1
        breaker.last_failure_time = time.time() - 2  # 2 seconds ago
        breaker.state = CircuitState.OPEN

        should_reset = breaker._should_attempt_reset()

        assert should_reset is True

    def test_transition_to_half_open_after_timeout(self):
        """Test circuit transitions to HALF_OPEN after timeout"""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=1)

        def failing_function():
            raise Exception("Error")

        # Open the circuit
        with pytest.raises(Exception):
            breaker.call(failing_function)

        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(1.1)

        # Next call should transition to HALF_OPEN
        def success_function():
            return "recovered"

        result = breaker.call(success_function)

        assert result == "recovered"
        assert breaker.state == CircuitState.CLOSED  # Successful call closes circuit

    def test_half_open_success_closes_circuit(self):
        """Test successful call in HALF_OPEN closes circuit"""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=1)

        # Force HALF_OPEN state
        breaker.state = CircuitState.HALF_OPEN
        breaker.failure_count = 1

        def success_function():
            return "success"

        result = breaker.call(success_function)

        assert result == "success"
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_half_open_failure_reopens_circuit(self):
        """Test failure in HALF_OPEN reopens circuit"""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=1)

        # Force HALF_OPEN state
        breaker.state = CircuitState.HALF_OPEN
        breaker.failure_count = 2

        def failing_function():
            raise Exception("Still failing")

        with pytest.raises(Exception):
            breaker.call(failing_function)

        assert breaker.state == CircuitState.OPEN
        assert breaker.failure_count == 3

    @pytest.mark.asyncio
    async def test_async_recovery_after_timeout(self):
        """Test async circuit recovery after timeout"""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=1)

        async def failing_function():
            raise Exception("Error")

        # Open circuit
        with pytest.raises(Exception):
            await breaker.call_async(failing_function)

        assert breaker.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(1.1)

        # Successful call should close circuit
        async def success_function():
            return "recovered"

        result = await breaker.call_async(success_function)

        assert result == "recovered"
        assert breaker.state == CircuitState.CLOSED


# ============================================================================
# STATE MANAGEMENT TESTS
# ============================================================================

class TestStateManagement:
    """Test circuit breaker state management"""

    def test_manual_reset(self):
        """Test manual reset of circuit breaker"""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=60)

        # Open the circuit
        def failing_function():
            raise Exception("Error")

        with pytest.raises(Exception):
            breaker.call(failing_function)

        assert breaker.state == CircuitState.OPEN
        assert breaker.failure_count == 1

        # Manual reset
        breaker.reset()

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.success_count == 0
        assert breaker.last_failure_time is None

    def test_get_state(self):
        """Test getting circuit breaker state"""
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

        state = breaker.get_state()

        assert state["state"] == "closed"
        assert state["failure_count"] == 0
        assert state["success_count"] == 0
        assert state["failure_threshold"] == 5
        assert state["recovery_timeout"] == 60
        assert state["last_failure_time"] is None
        assert state["time_until_retry"] == 0

    def test_get_state_with_failures(self):
        """Test get state after failures"""
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=60,
            expected_exception=ValueError
        )

        # Trigger some failures
        def failing_function():
            raise ValueError("Error")

        for i in range(2):
            with pytest.raises(ValueError):
                breaker.call(failing_function)

        state = breaker.get_state()

        assert state["failure_count"] == 2
        assert state["state"] == "closed"  # Not yet open
        assert state["last_failure_time"] is not None

    def test_time_until_retry_calculation(self):
        """Test time until retry calculation when circuit is open"""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=60)

        def failing_function():
            raise Exception("Error")

        # Open circuit
        with pytest.raises(Exception):
            breaker.call(failing_function)

        state = breaker.get_state()

        assert state["state"] == "open"
        # Time until retry should be close to 60 seconds
        assert 55 <= state["time_until_retry"] <= 60

    def test_time_until_retry_decreases(self):
        """Test time until retry decreases over time"""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=5)

        def failing_function():
            raise Exception("Error")

        # Open circuit
        with pytest.raises(Exception):
            breaker.call(failing_function)

        initial_time = breaker.get_state()["time_until_retry"]

        # Wait a bit
        time.sleep(1)

        updated_time = breaker.get_state()["time_until_retry"]

        assert updated_time < initial_time

    def test_on_success_resets_failure_count(self):
        """Test success handler resets failure count"""
        breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=30,
            expected_exception=ValueError
        )

        # Have some failures
        def failing_function():
            raise ValueError("Error")

        with pytest.raises(ValueError):
            breaker.call(failing_function)

        assert breaker.failure_count == 1

        # Successful call should reset failures
        def success_function():
            return "success"

        breaker.call(success_function)

        assert breaker.failure_count == 0
        assert breaker.success_count == 1

    def test_on_failure_updates_timestamp(self):
        """Test failure handler updates last failure time"""
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30,
            expected_exception=Exception
        )

        before_time = time.time()

        def failing_function():
            raise Exception("Error")

        with pytest.raises(Exception):
            breaker.call(failing_function)

        after_time = time.time()

        assert breaker.last_failure_time is not None
        assert before_time <= breaker.last_failure_time <= after_time


# ============================================================================
# DECORATOR TESTS
# ============================================================================

class TestCircuitBreakerDecorator:
    """Test circuit breaker decorator functionality"""

    def test_decorator_on_sync_function(self):
        """Test decorator applied to synchronous function"""

        @circuit_breaker(failure_threshold=2, recovery_timeout=30)
        def decorated_function(value):
            return value * 2

        result = decorated_function(5)

        assert result == 10

    @pytest.mark.asyncio
    async def test_decorator_on_async_function(self):
        """Test decorator applied to asynchronous function"""

        @circuit_breaker(failure_threshold=2, recovery_timeout=30)
        async def decorated_async_function(value):
            await asyncio.sleep(0.01)
            return value * 3

        result = await decorated_async_function(4)

        assert result == 12

    def test_decorator_failure_tracking(self):
        """Test decorator tracks failures correctly"""

        @circuit_breaker(failure_threshold=2, recovery_timeout=30, expected_exception=ValueError)
        def failing_decorated_function():
            raise ValueError("Decorated failure")

        # First failure
        with pytest.raises(ValueError):
            failing_decorated_function()

        # Second failure - should open circuit
        with pytest.raises(ValueError):
            failing_decorated_function()

        # Third call should fail fast
        with pytest.raises(CircuitBreakerOpenException):
            failing_decorated_function()

    @pytest.mark.asyncio
    async def test_decorator_async_failure_tracking(self):
        """Test decorator tracks async failures correctly"""

        @circuit_breaker(failure_threshold=1, recovery_timeout=30, expected_exception=RuntimeError)
        async def failing_async_decorated():
            raise RuntimeError("Async decorated failure")

        # First failure opens circuit
        with pytest.raises(RuntimeError):
            await failing_async_decorated()

        # Second call fails fast
        with pytest.raises(CircuitBreakerOpenException):
            await failing_async_decorated()


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_zero_failure_threshold(self):
        """Test circuit breaker with zero failure threshold"""
        breaker = CircuitBreaker(failure_threshold=0, recovery_timeout=30)

        assert breaker.failure_threshold == 0
        assert breaker.state == CircuitState.CLOSED

    def test_very_long_recovery_timeout(self):
        """Test circuit breaker with very long recovery timeout"""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=86400)  # 1 day

        def failing_function():
            raise Exception("Error")

        with pytest.raises(Exception):
            breaker.call(failing_function)

        # Should not be ready to retry
        assert breaker._should_attempt_reset() is False

    def test_concurrent_success_counting(self):
        """Test success count increments correctly with rapid calls"""
        breaker = CircuitBreaker(failure_threshold=10, recovery_timeout=30)

        def success_function():
            return "ok"

        for i in range(100):
            breaker.call(success_function)

        assert breaker.success_count == 100

    def test_time_until_retry_when_closed(self):
        """Test time until retry is zero when circuit is closed"""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)

        time_until = breaker._time_until_retry()

        assert time_until == 0

    def test_time_until_retry_no_last_failure(self):
        """Test time until retry when no failures recorded"""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
        breaker.state = CircuitState.OPEN  # Force open state

        time_until = breaker._time_until_retry()

        assert time_until == 0


class TestStateChangeCallback:
    """Phase A4: subscribers receive every state transition"""

    def test_callback_fires_on_open(self):
        events = []
        breaker = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=1,
            on_state_change=events.append,
        )

        def boom():
            raise RuntimeError("nope")

        for _ in range(2):
            try:
                breaker.call(boom)
            except RuntimeError:
                pass

        assert events == [CircuitState.OPEN]

    def test_callback_does_not_fire_on_no_change(self):
        events = []
        breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            on_state_change=events.append,
        )
        breaker._set_state(CircuitState.CLOSED)  # already CLOSED — no-op
        assert events == []

    def test_callback_fires_on_reset(self):
        events = []
        breaker = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout=60,
            on_state_change=events.append,
        )

        # Trip the breaker.
        def boom():
            raise RuntimeError("x")

        try:
            breaker.call(boom)
        except RuntimeError:
            pass
        assert events[-1] == CircuitState.OPEN

        breaker.reset()
        assert events[-1] == CircuitState.CLOSED
