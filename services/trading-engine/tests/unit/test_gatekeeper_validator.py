"""
Unit tests for Gatekeeper and Validator modules
Tests trend filtering and volume validation
"""

import pytest
from unittest.mock import Mock

from app.aggregation.gatekeeper import TrendGatekeeper
from app.aggregation.validator import VolumeValidator
from app.models import IndicatorSignal, SignalAction


class TestTrendGatekeeper:
    """Test TrendGatekeeper functionality"""

    @pytest.fixture
    def gatekeeper(self):
        """Create gatekeeper instance"""
        return TrendGatekeeper()

    def test_initialization(self, gatekeeper):
        """Test gatekeeper initialization"""
        assert gatekeeper.blocked_count == 0
        assert gatekeeper.passed_count == 0

    def test_check_signal_no_trend_filter(self, gatekeeper):
        """Test signal check when no trend filter available"""
        action, conf, blocked, reason = gatekeeper.check_signal(
            SignalAction.BUY, 0.8, None
        )

        assert action == SignalAction.BUY
        assert conf == 0.8
        assert blocked is False
        assert "No trend filter" in reason

    def test_check_signal_hold_passes_through(self, gatekeeper):
        """Test that HOLD signals always pass through"""
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.metadata = {"trend": "BEARISH"}

        action, conf, blocked, reason = gatekeeper.check_signal(
            SignalAction.HOLD, 0.5, trend_filter
        )

        assert action == SignalAction.HOLD
        assert conf == 0.5
        assert blocked is False

    def test_penalize_buy_in_strong_bearish_trend(self, gatekeeper):
        """Test penalizing BUY signal in strong BEARISH trend (0.9 confidence - below 0.95 threshold)

        UPDATED 2025-12-03: AGGRESSIVE mode (2025-11-28) only blocks at >=0.95 confidence.
        At 0.9 confidence, counter-trend signals get 5% penalty (0.95x) instead of blocking.
        """
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.9  # Strong trend but below 0.95 threshold
        trend_filter.metadata = {"trend": "BEARISH"}

        action, conf, blocked, reason = gatekeeper.check_signal(
            SignalAction.BUY, 0.8, trend_filter
        )

        # AGGRESSIVE mode: 0.9 < 0.95 threshold, so apply 5% penalty instead of blocking
        assert action == SignalAction.BUY  # Not blocked - just penalized
        assert conf == pytest.approx(0.8 * 0.95)  # 5% penalty (0.95x multiplier)
        assert blocked is False  # Not blocked in AGGRESSIVE mode at 0.9
        assert gatekeeper.penalized_count == 1  # Penalized, not passed

    def test_block_buy_in_very_strong_bearish_trend(self, gatekeeper):
        """Test blocking BUY signal in very strong BEARISH trend (>=0.95 confidence)

        ADDED 2025-12-03: Tests the actual blocking threshold in AGGRESSIVE mode.
        """
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.96  # Very strong trend >= 0.95 threshold
        trend_filter.metadata = {"trend": "BEARISH"}

        action, conf, blocked, reason = gatekeeper.check_signal(
            SignalAction.BUY, 0.8, trend_filter
        )

        assert action == SignalAction.HOLD  # Changed to HOLD - blocked
        assert conf == 0.8 * 0.3  # 70% penalty (0.3x multiplier for blocked signals)
        assert blocked is True
        assert "Counter-trend" in reason
        assert gatekeeper.blocked_count == 1

    def test_penalize_sell_in_strong_bullish_trend(self, gatekeeper):
        """Test penalizing SELL signal in strong BULLISH trend (0.9 confidence - below 0.95 threshold)

        UPDATED 2025-12-03: AGGRESSIVE mode (2025-11-28) only blocks at >=0.95 confidence.
        At 0.9 confidence, counter-trend signals get 5% penalty (0.95x) instead of blocking.
        """
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.9  # Strong trend but below 0.95 threshold
        trend_filter.metadata = {"trend": "BULLISH"}

        action, conf, blocked, reason = gatekeeper.check_signal(
            SignalAction.SELL, 0.8, trend_filter
        )

        # AGGRESSIVE mode: 0.9 < 0.95 threshold, so apply 5% penalty instead of blocking
        assert action == SignalAction.SELL  # Not blocked - just penalized
        assert conf == pytest.approx(0.8 * 0.95)  # 5% penalty (0.95x multiplier)
        assert blocked is False  # Not blocked in AGGRESSIVE mode at 0.9
        assert gatekeeper.penalized_count == 1  # Penalized, not passed

    def test_block_sell_in_very_strong_bullish_trend(self, gatekeeper):
        """Test blocking SELL signal in very strong BULLISH trend (>=0.95 confidence)

        ADDED 2025-12-03: Tests the actual blocking threshold in AGGRESSIVE mode.
        """
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.96  # Very strong trend >= 0.95 threshold
        trend_filter.metadata = {"trend": "BULLISH"}

        action, conf, blocked, reason = gatekeeper.check_signal(
            SignalAction.SELL, 0.8, trend_filter
        )

        assert action == SignalAction.HOLD  # Changed to HOLD - blocked
        assert conf == 0.8 * 0.3  # 70% penalty (0.3x multiplier for blocked signals)
        assert blocked is True
        assert "Counter-trend" in reason
        assert gatekeeper.blocked_count == 1

    def test_allow_buy_in_bullish_trend(self, gatekeeper):
        """Test allowing BUY signal in BULLISH trend"""
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.9
        trend_filter.metadata = {"trend": "BULLISH"}

        action, conf, blocked, reason = gatekeeper.check_signal(
            SignalAction.BUY, 0.8, trend_filter
        )

        assert action == SignalAction.BUY  # Unchanged
        assert conf == 0.8  # Unchanged
        assert blocked is False
        assert "aligned" in reason
        assert gatekeeper.passed_count == 1

    def test_allow_sell_in_bearish_trend(self, gatekeeper):
        """Test allowing SELL signal in BEARISH trend"""
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.9
        trend_filter.metadata = {"trend": "BEARISH"}

        action, conf, blocked, reason = gatekeeper.check_signal(
            SignalAction.SELL, 0.8, trend_filter
        )

        assert action == SignalAction.SELL  # Unchanged
        assert conf == 0.8  # Unchanged
        assert blocked is False
        assert gatekeeper.passed_count == 1

    def test_neutral_trend_no_penalty(self, gatekeeper):
        """Test that NEUTRAL trend has no penalty in AGGRESSIVE mode

        UPDATED 2025-12-03: AGGRESSIVE mode (2025-11-28) removed penalty for neutral trends.
        """
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.8
        trend_filter.metadata = {"trend": "NEUTRAL"}

        action, conf, blocked, reason = gatekeeper.check_signal(
            SignalAction.BUY, 1.0, trend_filter
        )

        assert action == SignalAction.BUY  # Unchanged
        assert conf == 1.0  # No penalty (AGGRESSIVE 2025-11-28)
        assert blocked is False
        assert "Neutral" in reason
        assert gatekeeper.passed_count == 1

    def test_get_stats_empty(self, gatekeeper):
        """Test getting stats when no signals processed"""
        stats = gatekeeper.get_stats()

        assert stats["blocked"] == 0
        assert stats["passed"] == 0
        assert stats["penalized"] == 0  # ADDED: new stat in AGGRESSIVE mode
        assert stats["total"] == 0
        assert stats["block_rate"] == 0.0
        assert stats["penalty_rate"] == 0.0  # ADDED: new stat in AGGRESSIVE mode

    def test_get_stats_with_data(self, gatekeeper):
        """Test getting stats after processing signals"""
        gatekeeper.blocked_count = 3
        gatekeeper.passed_count = 5
        gatekeeper.penalized_count = 2  # ADDED: new counter

        stats = gatekeeper.get_stats()

        assert stats["blocked"] == 3
        assert stats["passed"] == 5
        assert stats["penalized"] == 2  # ADDED: new stat
        assert stats["total"] == 10  # 3 + 5 + 2
        assert stats["block_rate"] == 0.3
        assert stats["penalty_rate"] == 0.2  # 2/10 = 0.2

    def test_reset_stats(self, gatekeeper):
        """Test resetting statistics"""
        gatekeeper.blocked_count = 5
        gatekeeper.passed_count = 10
        gatekeeper.penalized_count = 3  # ADDED: new counter

        gatekeeper.reset_stats()

        assert gatekeeper.blocked_count == 0
        assert gatekeeper.passed_count == 0
        assert gatekeeper.penalized_count == 0  # ADDED: new counter reset


class TestVolumeValidator:
    """Test VolumeValidator functionality"""

    @pytest.fixture
    def validator(self):
        """Create validator instance"""
        return VolumeValidator()

    def test_initialization(self, validator):
        """Test validator initialization with adaptive weighting"""
        assert validator.confirmed_count == 0
        assert validator.rejected_count == 0
        # NEW: Verify strength stats initialization
        assert "STRONG" in validator.strength_stats
        assert "MODERATE" in validator.strength_stats
        assert "WEAK" in validator.strength_stats
        assert "INSUFFICIENT" in validator.strength_stats
        assert "MINIMAL" in validator.strength_stats
        assert validator.strength_stats["STRONG"] == 0

    def test_validate_volume_no_volume_data(self, validator):
        """Test validation when no volume data available"""
        conf, penalty, reason = validator.validate_volume(0.8, None)

        assert conf == 0.8
        assert penalty == 1.0
        assert "No volume data" in reason

    def test_validate_volume_confirmed_strong(self, validator):
        """Test validation with CONFIRMED + STRONG volume (no penalty)"""
        volume_conf = Mock(spec=IndicatorSignal)
        volume_conf.metadata = {"confirmed": True, "strength": "STRONG"}

        conf, penalty, reason = validator.validate_volume(0.8, volume_conf)

        assert conf == 0.8  # Unchanged - no penalty
        assert penalty == 1.0
        assert "Strong volume confirmed" in reason
        assert validator.confirmed_count == 1
        assert validator.strength_stats["STRONG"] == 1

    def test_validate_volume_confirmed_moderate(self, validator):
        """Test validation with CONFIRMED + MODERATE volume (10% penalty)"""
        volume_conf = Mock(spec=IndicatorSignal)
        volume_conf.metadata = {"confirmed": True, "strength": "MODERATE"}

        conf, penalty, reason = validator.validate_volume(0.8, volume_conf)

        assert conf == pytest.approx(0.72)  # 0.8 * 0.9 = 10% penalty
        assert penalty == 0.9
        assert "Moderate volume confirmed" in reason
        assert validator.confirmed_count == 1
        assert validator.strength_stats["MODERATE"] == 1

    def test_validate_volume_not_confirmed_moderate(self, validator):
        """Test validation with NOT CONFIRMED + MODERATE volume (20% penalty)

        UPDATED 2025-12-03: PROFITABILITY FIX (2025-11-27) reduced penalty from 0.7x to 0.8x.
        """
        volume_conf = Mock(spec=IndicatorSignal)
        volume_conf.metadata = {"confirmed": False, "strength": "MODERATE"}

        conf, penalty, reason = validator.validate_volume(0.8, volume_conf)

        assert conf == pytest.approx(
            0.64
        )  # 0.8 * 0.8 = 20% penalty (PROFITABILITY FIX)
        assert penalty == 0.8
        assert "Moderate volume (unconfirmed)" in reason
        assert validator.rejected_count == 1
        assert validator.strength_stats["MODERATE"] == 1

    def test_validate_volume_not_confirmed_weak(self, validator):
        """Test validation with NOT CONFIRMED + WEAK volume (25% penalty)

        UPDATED 2025-12-03: PROFITABILITY FIX (2025-11-27) reduced penalty from 0.6x to 0.75x.
        """
        volume_conf = Mock(spec=IndicatorSignal)
        volume_conf.metadata = {"confirmed": False, "strength": "WEAK"}

        conf, penalty, reason = validator.validate_volume(0.8, volume_conf)

        assert conf == pytest.approx(
            0.6
        )  # 0.8 * 0.75 = 25% penalty (PROFITABILITY FIX)
        assert penalty == 0.75
        assert "Weak volume" in reason
        assert validator.rejected_count == 1
        assert validator.strength_stats["WEAK"] == 1

    def test_validate_volume_not_confirmed_insufficient(self, validator):
        """NOT CONFIRMED + INSUFFICIENT volume must draw the 50% penalty.

        INSUFFICIENT is the string the technical-analysis producer actually
        emits (`app/indicators/volume_confirmation.py`) when volume is below
        1.0x average — measured on 64.7% of 17,478 bars. Until 2026-08-09 the
        validator branched only on the never-emitted "MINIMAL", so these bars
        fell through to the UNKNOWN branch and were penalised 0.95x. This test
        is the one that would have caught it.
        """
        volume_conf = Mock(spec=IndicatorSignal)
        volume_conf.metadata = {"confirmed": False, "strength": "INSUFFICIENT"}

        conf, penalty, reason = validator.validate_volume(0.9, volume_conf)

        assert penalty == 0.5, "INSUFFICIENT must be penalised 0.5x, not 0.95x"
        assert conf == pytest.approx(0.45)  # 0.9 * 0.5
        assert "Insufficient volume" in reason
        assert validator.rejected_count == 1
        assert validator.strength_stats["INSUFFICIENT"] == 1

    def test_validate_volume_not_confirmed_minimal_alias(self, validator):
        """The legacy "MINIMAL" alias keeps the same 50% penalty.

        UPDATED 2025-12-03: PROFITABILITY FIX (2025-11-27) reduced penalty from 0.3x to 0.5x.
        """
        volume_conf = Mock(spec=IndicatorSignal)
        volume_conf.metadata = {"confirmed": False, "strength": "MINIMAL"}

        conf, penalty, reason = validator.validate_volume(0.9, volume_conf)

        assert conf == pytest.approx(
            0.45
        )  # 0.9 * 0.5 = 50% penalty (PROFITABILITY FIX)
        assert penalty == 0.5
        assert "Minimal volume" in reason
        assert validator.rejected_count == 1
        assert validator.strength_stats["MINIMAL"] == 1

    def test_every_producer_strength_is_tracked_and_penalised(self, validator):
        """Contract test: no producer string may fall through to UNKNOWN.

        The producer vocabulary lives in the technical-analysis service and
        cannot be imported from here (separate Docker build context), so it is
        mirrored on VolumeValidator.PRODUCER_STRENGTHS. Any string the producer
        emits must (a) have a strength_stats bucket, or it is invisible in
        telemetry, and (b) not land in the UNKNOWN 0.95x fallback, or its
        designed penalty silently never applies.
        """
        for strength in VolumeValidator.PRODUCER_STRENGTHS:
            assert strength in validator.strength_stats, (
                f"{strength} has no strength_stats bucket - it will never "
                f"appear in get_stats()"
            )

        # (strength, confirmed, expected_penalty) as the producer emits them:
        # STRONG/MODERATE always set confirmed=True, WEAK only for
        # continuation signals, INSUFFICIENT never.
        producer_cases = [
            ("STRONG", True, 1.0),
            ("MODERATE", True, 0.9),
            ("WEAK", False, 0.75),
            ("INSUFFICIENT", False, 0.5),
        ]
        assert {c[0] for c in producer_cases} == set(
            VolumeValidator.PRODUCER_STRENGTHS
        ), "producer vocabulary changed - update this table"

        for strength, confirmed, expected_penalty in producer_cases:
            fresh = VolumeValidator()
            volume_conf = Mock(spec=IndicatorSignal)
            volume_conf.metadata = {"confirmed": confirmed, "strength": strength}

            _, penalty, reason = fresh.validate_volume(1.0, volume_conf)

            assert "Unknown volume strength" not in reason, (
                f"{strength} fell through to the UNKNOWN fallback"
            )
            assert penalty == expected_penalty, (
                f"{strength} penalised {penalty}x, expected {expected_penalty}x"
            )
            assert fresh.strength_stats[strength] == 1

    def test_get_stats_empty(self, validator):
        """Test getting stats when no validations performed"""
        stats = validator.get_stats()

        assert stats["confirmed"] == 0
        assert stats["rejected"] == 0
        assert stats["total"] == 0
        assert stats["rejection_rate"] == 0.0
        assert stats["confirmation_rate"] == 0.0
        # NEW: Check adaptive weighting stats
        assert "strength_distribution" in stats
        assert "average_penalty_estimate" in stats
        assert stats["average_penalty_estimate"] == 1.0  # No data = 1.0

    def test_get_stats_with_data(self, validator):
        """Test getting stats after validations"""
        validator.confirmed_count = 7
        validator.rejected_count = 3

        stats = validator.get_stats()

        assert stats["confirmed"] == 7
        assert stats["rejected"] == 3
        assert stats["total"] == 10
        assert stats["rejection_rate"] == 0.3
        assert stats["confirmation_rate"] == 0.7

    def test_reset_stats(self, validator):
        """Test resetting statistics including strength stats"""
        validator.confirmed_count = 10
        validator.rejected_count = 5
        validator.strength_stats["STRONG"] = 3
        validator.strength_stats["WEAK"] = 7
        validator.strength_stats["INSUFFICIENT"] = 11

        validator.reset_stats()

        assert validator.confirmed_count == 0
        assert validator.rejected_count == 0
        # NEW: Verify strength stats are also reset
        assert validator.strength_stats["STRONG"] == 0
        assert validator.strength_stats["WEAK"] == 0
        assert validator.strength_stats["INSUFFICIENT"] == 0
        assert validator.strength_stats["MINIMAL"] == 0


class TestGatekeeperValidatorIntegration:
    """Integration tests for Gatekeeper and Validator working together"""

    def test_pipeline_both_pass(self):
        """Test pipeline where both gatekeeper and validator pass with STRONG volume"""
        gatekeeper = TrendGatekeeper()
        validator = VolumeValidator()

        # Setup trend filter (BULLISH)
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.9
        trend_filter.metadata = {"trend": "BULLISH"}

        # Setup volume confirmation (CONFIRMED + STRONG)
        volume_conf = Mock(spec=IndicatorSignal)
        volume_conf.metadata = {"confirmed": True, "strength": "STRONG"}

        # Pass through gatekeeper
        action, conf, blocked, _ = gatekeeper.check_signal(
            SignalAction.BUY, 0.8, trend_filter
        )

        assert action == SignalAction.BUY
        assert conf == 0.8
        assert not blocked

        # Pass through validator (STRONG = no penalty)
        conf, penalty, _ = validator.validate_volume(conf, volume_conf)

        assert conf == 0.8
        assert penalty == 1.0

    def test_pipeline_gatekeeper_penalizes(self):
        """Test pipeline where gatekeeper penalizes counter-trend signal (below 0.95 threshold)

        UPDATED 2025-12-03: AGGRESSIVE mode applies 5% penalty at 0.9 confidence instead of blocking.
        """
        gatekeeper = TrendGatekeeper()
        validator = VolumeValidator()

        # Setup trend filter (BEARISH with high confidence, but below 0.95 threshold)
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.9  # Strong trend but < 0.95 threshold
        trend_filter.metadata = {"trend": "BEARISH"}

        # Setup volume confirmation (CONFIRMED + STRONG)
        volume_conf = Mock(spec=IndicatorSignal)
        volume_conf.metadata = {"confirmed": True, "strength": "STRONG"}

        # Pass through gatekeeper (AGGRESSIVE mode: penalize but don't block at 0.9)
        action, conf, blocked, _ = gatekeeper.check_signal(
            SignalAction.BUY, 0.8, trend_filter
        )

        assert action == SignalAction.BUY  # Not blocked - just penalized
        assert conf == pytest.approx(0.76)  # 5% penalty (0.8 * 0.95)
        assert blocked is False

        # Pass through validator (STRONG volume = no additional penalty)
        conf, penalty, _ = validator.validate_volume(conf, volume_conf)

        assert conf == pytest.approx(0.76)  # Slight reduction from gatekeeper penalty
        assert penalty == 1.0  # STRONG volume = no penalty

    def test_pipeline_gatekeeper_blocks_very_strong(self):
        """Test pipeline where gatekeeper blocks signal in very strong counter-trend (>=0.95)

        ADDED 2025-12-03: Tests blocking at the AGGRESSIVE mode threshold of 0.95.
        """
        gatekeeper = TrendGatekeeper()
        validator = VolumeValidator()

        # Setup trend filter (BEARISH with very high confidence >= 0.95)
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.96  # Very strong trend >= 0.95 threshold
        trend_filter.metadata = {"trend": "BEARISH"}

        # Setup volume confirmation (CONFIRMED + STRONG)
        volume_conf = Mock(spec=IndicatorSignal)
        volume_conf.metadata = {"confirmed": True, "strength": "STRONG"}

        # Pass through gatekeeper (should block BUY at >= 0.95)
        action, conf, blocked, _ = gatekeeper.check_signal(
            SignalAction.BUY, 0.8, trend_filter
        )

        assert action == SignalAction.HOLD  # Blocked
        assert conf == pytest.approx(0.24)  # 70% penalty (0.8 * 0.3)
        assert blocked is True

        # Pass through validator (STRONG volume but doesn't matter - already blocked)
        conf, penalty, _ = validator.validate_volume(conf, volume_conf)

        assert conf == pytest.approx(0.24)  # Still low from gatekeeper penalty
        assert penalty == 1.0  # STRONG volume = no penalty

    def test_pipeline_validator_penalizes_weak(self):
        """Test pipeline where validator applies WEAK volume penalty (25% - PROFITABILITY FIX)

        UPDATED 2025-12-03: PROFITABILITY FIX (2025-11-27) reduced WEAK penalty from 0.6x to 0.75x.
        """
        gatekeeper = TrendGatekeeper()
        validator = VolumeValidator()

        # Setup trend filter (BULLISH - aligns with BUY)
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.9
        trend_filter.metadata = {"trend": "BULLISH"}

        # Setup volume confirmation (NOT CONFIRMED + WEAK)
        volume_conf = Mock(spec=IndicatorSignal)
        volume_conf.metadata = {"confirmed": False, "strength": "WEAK"}

        # Pass through gatekeeper (should allow)
        action, conf, blocked, _ = gatekeeper.check_signal(
            SignalAction.BUY, 0.8, trend_filter
        )

        assert action == SignalAction.BUY
        assert conf == 0.8
        assert not blocked

        # Pass through validator (WEAK = 25% penalty - PROFITABILITY FIX 2025-11-27)
        conf, penalty, _ = validator.validate_volume(conf, volume_conf)

        assert conf == pytest.approx(0.6)  # 0.8 * 0.75 = 25% penalty
        assert penalty == 0.75

    def test_pipeline_both_penalize_minimal(self):
        """Test pipeline with NEUTRAL trend + MINIMAL volume

        UPDATED 2025-12-03:
        - AGGRESSIVE mode (2025-11-28) removed NEUTRAL trend penalty (now 1.0x)
        - PROFITABILITY FIX (2025-11-27) reduced MINIMAL penalty from 0.3x to 0.5x
        """
        gatekeeper = TrendGatekeeper()
        validator = VolumeValidator()

        # Setup trend filter (NEUTRAL - no penalty in AGGRESSIVE mode)
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.7
        trend_filter.metadata = {"trend": "NEUTRAL"}

        # Setup volume confirmation (NOT CONFIRMED + MINIMAL)
        volume_conf = Mock(spec=IndicatorSignal)
        volume_conf.metadata = {"confirmed": False, "strength": "MINIMAL"}

        # Pass through gatekeeper (NEUTRAL trend = no penalty in AGGRESSIVE mode)
        action, conf, blocked, _ = gatekeeper.check_signal(
            SignalAction.BUY, 1.0, trend_filter
        )

        assert action == SignalAction.BUY
        assert conf == 1.0  # No penalty (AGGRESSIVE 2025-11-28)
        assert not blocked

        # Pass through validator (MINIMAL = 50% penalty - PROFITABILITY FIX)
        conf, penalty, _ = validator.validate_volume(conf, volume_conf)

        assert conf == pytest.approx(0.5)  # 1.0 * 0.5 (only MINIMAL penalty)
        assert penalty == 0.5

    def test_pipeline_both_penalize_moderate(self):
        """Test pipeline with NEUTRAL trend + MODERATE unconfirmed volume

        UPDATED 2025-12-03:
        - AGGRESSIVE mode (2025-11-28) removed NEUTRAL trend penalty (now 1.0x)
        - PROFITABILITY FIX (2025-11-27) reduced MODERATE unconfirmed penalty from 0.7x to 0.8x
        """
        gatekeeper = TrendGatekeeper()
        validator = VolumeValidator()

        # Setup trend filter (NEUTRAL - no penalty in AGGRESSIVE mode)
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.7
        trend_filter.metadata = {"trend": "NEUTRAL"}

        # Setup volume confirmation (NOT CONFIRMED + MODERATE)
        volume_conf = Mock(spec=IndicatorSignal)
        volume_conf.metadata = {"confirmed": False, "strength": "MODERATE"}

        # Pass through gatekeeper (NEUTRAL = no penalty - AGGRESSIVE 2025-11-28)
        action, conf, blocked, _ = gatekeeper.check_signal(
            SignalAction.BUY, 1.0, trend_filter
        )

        assert action == SignalAction.BUY
        assert conf == 1.0  # No penalty (AGGRESSIVE 2025-11-28)
        assert not blocked

        # Pass through validator (MODERATE unconfirmed = 20% penalty - PROFITABILITY FIX)
        conf, penalty, _ = validator.validate_volume(conf, volume_conf)

        assert conf == pytest.approx(0.8)  # 1.0 * 0.8 (only MODERATE penalty)
        assert penalty == 0.8
