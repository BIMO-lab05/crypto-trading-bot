"""
Unit tests for Circuit Breaker State Machine
Tests the complete state machine with cooldown periods, half-open state, and recovery logic
"""

import pytest
from datetime import datetime, timedelta
from app.config import settings
from app.models import CircuitBreakerState


@pytest.mark.unit
@pytest.mark.circuit_breaker
@pytest.mark.state_machine
class TestCircuitBreakerStateMachine:
    """Tests for the complete circuit breaker state machine"""

    def test_state_transition_closed_to_open(self, risk_engine):
        """Test transition from CLOSED to OPEN when threshold exceeded"""
        # Initial state should be CLOSED
        assert risk_engine.circuit_breaker_state == CircuitBreakerState.CLOSED

        # Trip the circuit breaker
        status = risk_engine.check_circuit_breaker(
            daily_pnl=-0.06,  # Exceeds -5% limit
            drawdown=0.05,
            exposure_ratio=0.15,
        )

        # Verify transition to OPEN
        assert status.state == CircuitBreakerState.OPEN
        assert risk_engine.circuit_breaker_state == CircuitBreakerState.OPEN
        assert status.is_tripped is True
        assert status.can_trade is False
        assert status.cooldown_until is not None
        assert status.failure_count == 1

    def test_state_transition_open_to_half_open(self, risk_engine):
        """Test transition from OPEN to HALF_OPEN after cooldown expires"""
        # Trip the circuit breaker
        risk_engine.check_circuit_breaker(
            daily_pnl=-0.06, drawdown=0.05, exposure_ratio=0.15
        )

        # Verify we're in OPEN state
        assert risk_engine.circuit_breaker_state == CircuitBreakerState.OPEN

        # Manually expire the cooldown for testing
        risk_engine.circuit_breaker_cooldown_until = datetime.now() - timedelta(
            seconds=1
        )

        # Check again - should transition to HALF_OPEN
        status = risk_engine.check_circuit_breaker(
            daily_pnl=-0.02,  # Within limits
            drawdown=0.05,
            exposure_ratio=0.15,
        )

        # Verify transition to HALF_OPEN
        assert status.state == CircuitBreakerState.HALF_OPEN
        assert risk_engine.circuit_breaker_state == CircuitBreakerState.HALF_OPEN
        assert status.is_tripped is False  # Not fully tripped in half-open
        assert status.can_trade is True  # Can trade in half-open
        assert "recovery" in status.reason.lower()

    def test_state_transition_half_open_to_closed_on_success(self, risk_engine):
        """Test transition from HALF_OPEN to CLOSED after successful trades"""
        # Setup: Get to HALF_OPEN state
        risk_engine.circuit_breaker_state = CircuitBreakerState.HALF_OPEN
        risk_engine.circuit_breaker_tripped_at = datetime.now() - timedelta(minutes=10)
        risk_engine.circuit_breaker_failure_count = 1

        # Record successful trades (need max_requests successes to transition)
        for _ in range(settings.circuit_breaker_half_open_max_requests):
            risk_engine.record_trade_result(success=True)

        # Check status - should transition to CLOSED
        status = risk_engine.check_circuit_breaker(
            daily_pnl=-0.02, drawdown=0.05, exposure_ratio=0.15
        )

        # Verify transition to CLOSED
        assert status.state == CircuitBreakerState.CLOSED
        assert risk_engine.circuit_breaker_state == CircuitBreakerState.CLOSED
        assert status.can_trade is True
        assert risk_engine.circuit_breaker_tripped_at is None
        assert risk_engine.circuit_breaker_failure_count == 0

    def test_state_transition_half_open_to_open_on_failure(self, risk_engine):
        """Test transition from HALF_OPEN back to OPEN when trade fails"""
        # Setup: Get to HALF_OPEN state
        risk_engine.circuit_breaker_state = CircuitBreakerState.HALF_OPEN
        risk_engine.circuit_breaker_tripped_at = datetime.now() - timedelta(minutes=10)
        risk_engine.circuit_breaker_failure_count = 1
        original_cooldown = risk_engine.circuit_breaker_cooldown_duration

        # Record failed trade
        risk_engine.record_trade_result(success=False)

        # Verify transition back to OPEN
        assert risk_engine.circuit_breaker_state == CircuitBreakerState.OPEN
        assert risk_engine.circuit_breaker_failure_count == 2

        # Verify cooldown was extended
        assert risk_engine.circuit_breaker_cooldown_duration > original_cooldown

    def test_exponential_backoff_cooldown(self, risk_engine):
        """Test that cooldown period increases exponentially with failures"""
        base_cooldown = settings.circuit_breaker_cooldown
        cooldowns = []

        # Trip circuit breaker multiple times
        for i in range(3):
            status = risk_engine.check_circuit_breaker(
                daily_pnl=-0.06,  # Exceeds limit
                drawdown=0.05,
                exposure_ratio=0.15,
            )

            cooldowns.append(status.cooldown_duration)

            # Manually expire cooldown and transition to HALF_OPEN, then fail
            risk_engine.circuit_breaker_cooldown_until = datetime.now() - timedelta(
                seconds=1
            )
            risk_engine.check_circuit_breaker(
                -0.02, 0.05, 0.15
            )  # Transition to HALF_OPEN
            risk_engine.record_trade_result(success=False)  # Fail and return to OPEN

        # Verify exponential growth
        assert cooldowns[1] > cooldowns[0]
        assert cooldowns[2] > cooldowns[1]

        # Verify multiplier is being applied
        expected_cooldown_1 = (
            base_cooldown * settings.circuit_breaker_cooldown_multiplier
        )
        assert abs(cooldowns[1] - expected_cooldown_1) < 1  # Allow 1 second tolerance

    def test_max_cooldown_limit(self, risk_engine):
        """Test that cooldown never exceeds maximum configured limit"""
        # Set high failure count to trigger max cooldown
        risk_engine.circuit_breaker_failure_count = 10

        # Trip circuit breaker
        status = risk_engine.check_circuit_breaker(
            daily_pnl=-0.06, drawdown=0.05, exposure_ratio=0.15
        )

        # Verify cooldown is capped at max
        assert status.cooldown_duration <= settings.circuit_breaker_max_cooldown

    def test_cooldown_period_prevents_trading(self, risk_engine):
        """Test that trading is not allowed during cooldown period"""
        # Trip circuit breaker
        status1 = risk_engine.check_circuit_breaker(
            daily_pnl=-0.06, drawdown=0.05, exposure_ratio=0.15
        )

        # Verify cooldown is active
        assert status1.cooldown_until is not None
        cooldown_end = status1.cooldown_until

        # Check again during cooldown (even though metrics are now within limits)
        status2 = risk_engine.check_circuit_breaker(
            daily_pnl=-0.01,  # Now within limits
            drawdown=0.05,
            exposure_ratio=0.15,
        )

        # Should still be in OPEN state due to cooldown
        assert status2.state == CircuitBreakerState.OPEN
        assert status2.can_trade is False
        assert "cooldown" in status2.reason.lower()
        assert status2.cooldown_until == cooldown_end

    def test_half_open_allows_limited_trading(self, risk_engine):
        """Test that HALF_OPEN state allows trading"""
        # Setup: Get to HALF_OPEN state
        risk_engine.circuit_breaker_state = CircuitBreakerState.HALF_OPEN
        risk_engine.circuit_breaker_tripped_at = datetime.now() - timedelta(minutes=10)

        # Check status
        status = risk_engine.check_circuit_breaker(
            daily_pnl=-0.02, drawdown=0.05, exposure_ratio=0.15
        )

        # Verify trading is allowed
        assert status.state == CircuitBreakerState.HALF_OPEN
        assert status.can_trade is True
        assert status.trading_allowed is True

    def test_manual_reset(self, risk_engine):
        """Test manual reset of circuit breaker"""
        # Trip circuit breaker
        risk_engine.check_circuit_breaker(
            daily_pnl=-0.06, drawdown=0.05, exposure_ratio=0.15
        )

        # Verify it's tripped
        assert risk_engine.circuit_breaker_state == CircuitBreakerState.OPEN

        # Manually reset
        risk_engine.reset_circuit_breaker()

        # Verify reset
        assert risk_engine.circuit_breaker_state == CircuitBreakerState.CLOSED
        assert risk_engine.circuit_breaker_tripped_at is None
        assert risk_engine.circuit_breaker_cooldown_until is None
        assert risk_engine.circuit_breaker_failure_count == 0
        assert risk_engine.circuit_breaker_success_count == 0

    def test_record_trade_result_tracks_successes(self, risk_engine):
        """Test that successful trades are tracked in HALF_OPEN state"""
        # Setup: HALF_OPEN state
        risk_engine.circuit_breaker_state = CircuitBreakerState.HALF_OPEN

        # Record successful trades
        risk_engine.record_trade_result(success=True)
        assert risk_engine.circuit_breaker_success_count == 1

        risk_engine.record_trade_result(success=True)
        assert risk_engine.circuit_breaker_success_count == 2

    def test_record_trade_result_only_in_half_open(self, risk_engine):
        """Test that trade results are only tracked in HALF_OPEN state"""
        # Try recording result in CLOSED state
        risk_engine.circuit_breaker_state = CircuitBreakerState.CLOSED
        risk_engine.record_trade_result(success=True)

        # Should log warning but not change state
        assert risk_engine.circuit_breaker_success_count == 0

    def test_state_persistence_across_checks(self, risk_engine):
        """Test that state persists across multiple check_circuit_breaker calls"""
        # Trip the circuit breaker
        status1 = risk_engine.check_circuit_breaker(
            daily_pnl=-0.06, drawdown=0.05, exposure_ratio=0.15
        )

        # Check again (without expiring cooldown)
        status2 = risk_engine.check_circuit_breaker(
            daily_pnl=-0.02, drawdown=0.05, exposure_ratio=0.15
        )

        # State should persist
        assert status1.state == status2.state == CircuitBreakerState.OPEN
        assert status1.tripped_at == status2.tripped_at
        assert status1.failure_count == status2.failure_count

    def test_multiple_violations_recorded(self, risk_engine):
        """Test that multiple simultaneous violations are all recorded"""
        # Trip with multiple violations.
        # ADR-017: max_exposure raised to 0.50, trip threshold = 0.50 * 1.2
        # = 0.60. Pre-ADR-017 exposure_ratio=0.30 tripped against the 0.24
        # threshold; now we need >0.60 to fire the third reason.
        status = risk_engine.check_circuit_breaker(
            daily_pnl=-0.07,  # Violates daily loss
            drawdown=0.15,  # Violates drawdown
            exposure_ratio=0.65,  # Violates exposure
        )

        # Verify all reasons are recorded
        assert len(status.reasons) >= 3
        assert any("Daily loss" in r for r in status.reasons)
        assert any("Drawdown" in r for r in status.reasons)
        assert any("Exposure" in r for r in status.reasons)

    def test_cooldown_calculation_accuracy(self, risk_engine):
        """Test that cooldown period is calculated accurately"""
        # Trip circuit breaker
        before_trip = datetime.now()
        status = risk_engine.check_circuit_breaker(
            daily_pnl=-0.06, drawdown=0.05, exposure_ratio=0.15
        )
        after_trip = datetime.now()

        # Verify cooldown_until is approximately cooldown_duration seconds in the future
        expected_cooldown_end = before_trip + timedelta(
            seconds=status.cooldown_duration
        )
        actual_cooldown_end = status.cooldown_until

        # Allow 2 second tolerance for test execution time
        time_diff = abs((actual_cooldown_end - expected_cooldown_end).total_seconds())
        assert time_diff < 2


@pytest.mark.unit
@pytest.mark.circuit_breaker
class TestCircuitBreakerEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_trip_on_exact_threshold(self, risk_engine):
        """Test circuit breaker behavior at exact threshold values"""
        # Test at exact threshold (should NOT trip)
        status = risk_engine.check_circuit_breaker(
            daily_pnl=-0.05,  # Exactly at limit
            drawdown=0.10,  # Exactly at limit
            exposure_ratio=0.24,  # Exactly at limit (0.20 * 1.2)
        )

        # Should NOT trip at exact threshold
        assert status.state == CircuitBreakerState.CLOSED
        assert status.can_trade is True

    def test_trip_just_beyond_threshold(self, risk_engine):
        """Test circuit breaker trips just beyond threshold"""
        # Test just beyond threshold (should trip)
        status = risk_engine.check_circuit_breaker(
            daily_pnl=-0.050001,  # Just beyond limit
            drawdown=0.05,
            exposure_ratio=0.15,
        )

        # Should trip
        assert status.state == CircuitBreakerState.OPEN
        assert status.can_trade is False

    def test_recovery_with_zero_successes_required(self, risk_engine):
        """Test edge case where max_requests is 0 (should not be possible in production)"""
        # Save original setting
        original_max_requests = settings.circuit_breaker_half_open_max_requests

        # Temporarily set to 0 (edge case)
        settings.circuit_breaker_half_open_max_requests = 0

        try:
            # Setup HALF_OPEN state
            risk_engine.circuit_breaker_state = CircuitBreakerState.HALF_OPEN

            # Check status - should immediately transition to CLOSED
            status = risk_engine.check_circuit_breaker(
                daily_pnl=-0.02, drawdown=0.05, exposure_ratio=0.15
            )

            assert status.state == CircuitBreakerState.CLOSED

        finally:
            # Restore original setting
            settings.circuit_breaker_half_open_max_requests = original_max_requests
