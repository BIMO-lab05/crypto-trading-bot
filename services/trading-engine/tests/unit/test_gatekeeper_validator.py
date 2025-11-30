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
            SignalAction.BUY,
            0.8,
            None
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
            SignalAction.HOLD,
            0.5,
            trend_filter
        )

        assert action == SignalAction.HOLD
        assert conf == 0.5
        assert blocked is False

    def test_block_buy_in_bearish_trend(self, gatekeeper):
        """Test blocking BUY signal in very strong BEARISH trend (>=0.75 confidence)"""
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.9  # Very strong trend
        trend_filter.metadata = {"trend": "BEARISH"}

        action, conf, blocked, reason = gatekeeper.check_signal(
            SignalAction.BUY,
            0.8,
            trend_filter
        )

        assert action == SignalAction.HOLD  # Changed to HOLD
        assert conf == 0.8 * 0.3  # 70% penalty (0.3x multiplier for blocked signals)
        assert blocked is True
        assert "Counter-trend" in reason
        assert gatekeeper.blocked_count == 1

    def test_block_sell_in_bullish_trend(self, gatekeeper):
        """Test blocking SELL signal in very strong BULLISH trend (>=0.75 confidence)"""
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.9  # Very strong trend
        trend_filter.metadata = {"trend": "BULLISH"}

        action, conf, blocked, reason = gatekeeper.check_signal(
            SignalAction.SELL,
            0.8,
            trend_filter
        )

        assert action == SignalAction.HOLD  # Changed to HOLD
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
            SignalAction.BUY,
            0.8,
            trend_filter
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
            SignalAction.SELL,
            0.8,
            trend_filter
        )

        assert action == SignalAction.SELL  # Unchanged
        assert conf == 0.8  # Unchanged
        assert blocked is False
        assert gatekeeper.passed_count == 1

    def test_neutral_trend_reduces_confidence(self, gatekeeper):
        """Test that NEUTRAL trend reduces confidence (10% penalty)"""
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.8
        trend_filter.metadata = {"trend": "NEUTRAL"}

        action, conf, blocked, reason = gatekeeper.check_signal(
            SignalAction.BUY,
            1.0,
            trend_filter
        )

        assert action == SignalAction.BUY  # Unchanged
        assert conf == 1.0 * 0.9  # 10% penalty (RESEARCH-BASED 2025-11-26)
        assert blocked is False
        assert "Neutral trend" in reason
        assert gatekeeper.passed_count == 1

    def test_get_stats_empty(self, gatekeeper):
        """Test getting stats when no signals processed"""
        stats = gatekeeper.get_stats()

        assert stats["blocked"] == 0
        assert stats["passed"] == 0
        assert stats["total"] == 0
        assert stats["block_rate"] == 0.0

    def test_get_stats_with_data(self, gatekeeper):
        """Test getting stats after processing signals"""
        gatekeeper.blocked_count = 3
        gatekeeper.passed_count = 7

        stats = gatekeeper.get_stats()

        assert stats["blocked"] == 3
        assert stats["passed"] == 7
        assert stats["total"] == 10
        assert stats["block_rate"] == 0.3

    def test_reset_stats(self, gatekeeper):
        """Test resetting statistics"""
        gatekeeper.blocked_count = 5
        gatekeeper.passed_count = 10

        gatekeeper.reset_stats()

        assert gatekeeper.blocked_count == 0
        assert gatekeeper.passed_count == 0


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
        """Test validation with NOT CONFIRMED + MODERATE volume (30% penalty)"""
        volume_conf = Mock(spec=IndicatorSignal)
        volume_conf.metadata = {"confirmed": False, "strength": "MODERATE"}

        conf, penalty, reason = validator.validate_volume(0.8, volume_conf)

        assert conf == pytest.approx(0.56)  # 0.8 * 0.7 = 30% penalty
        assert penalty == 0.7
        assert "Moderate volume (unconfirmed)" in reason
        assert validator.rejected_count == 1
        assert validator.strength_stats["MODERATE"] == 1

    def test_validate_volume_not_confirmed_weak(self, validator):
        """Test validation with NOT CONFIRMED + WEAK volume (40% penalty - RESEARCH-BASED)"""
        volume_conf = Mock(spec=IndicatorSignal)
        volume_conf.metadata = {"confirmed": False, "strength": "WEAK"}

        conf, penalty, reason = validator.validate_volume(0.8, volume_conf)

        assert conf == pytest.approx(0.48)  # 0.8 * 0.6 = 40% penalty (RESEARCH-BASED 2025-11-26)
        assert penalty == 0.6
        assert "Weak volume" in reason
        assert validator.rejected_count == 1
        assert validator.strength_stats["WEAK"] == 1

    def test_validate_volume_not_confirmed_minimal(self, validator):
        """Test validation with NOT CONFIRMED + MINIMAL volume (70% penalty)"""
        volume_conf = Mock(spec=IndicatorSignal)
        volume_conf.metadata = {"confirmed": False, "strength": "MINIMAL"}

        conf, penalty, reason = validator.validate_volume(0.9, volume_conf)

        assert conf == pytest.approx(0.27)  # 0.9 * 0.3 = 70% penalty (original aggressive penalty)
        assert penalty == 0.3
        assert "Minimal volume" in reason
        assert validator.rejected_count == 1
        assert validator.strength_stats["MINIMAL"] == 1

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

        validator.reset_stats()

        assert validator.confirmed_count == 0
        assert validator.rejected_count == 0
        # NEW: Verify strength stats are also reset
        assert validator.strength_stats["STRONG"] == 0
        assert validator.strength_stats["WEAK"] == 0
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
            SignalAction.BUY,
            0.8,
            trend_filter
        )

        assert action == SignalAction.BUY
        assert conf == 0.8
        assert not blocked

        # Pass through validator (STRONG = no penalty)
        conf, penalty, _ = validator.validate_volume(conf, volume_conf)

        assert conf == 0.8
        assert penalty == 1.0

    def test_pipeline_gatekeeper_blocks(self):
        """Test pipeline where gatekeeper blocks signal in very strong counter-trend"""
        gatekeeper = TrendGatekeeper()
        validator = VolumeValidator()

        # Setup trend filter (BEARISH with very high confidence)
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.9  # Very strong trend (>=0.75)
        trend_filter.metadata = {"trend": "BEARISH"}

        # Setup volume confirmation (CONFIRMED + STRONG)
        volume_conf = Mock(spec=IndicatorSignal)
        volume_conf.metadata = {"confirmed": True, "strength": "STRONG"}

        # Pass through gatekeeper (should block BUY in very strong BEARISH)
        action, conf, blocked, _ = gatekeeper.check_signal(
            SignalAction.BUY,
            0.8,
            trend_filter
        )

        assert action == SignalAction.HOLD  # Blocked
        assert conf == pytest.approx(0.24)  # 70% penalty (0.8 * 0.3)
        assert blocked is True

        # Pass through validator (STRONG volume but doesn't matter - already blocked)
        conf, penalty, _ = validator.validate_volume(conf, volume_conf)

        assert conf == pytest.approx(0.24)  # Still low from gatekeeper penalty
        assert penalty == 1.0  # STRONG volume = no penalty

    def test_pipeline_validator_penalizes_weak(self):
        """Test pipeline where validator applies WEAK volume penalty (40% - RESEARCH-BASED)"""
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
            SignalAction.BUY,
            0.8,
            trend_filter
        )

        assert action == SignalAction.BUY
        assert conf == 0.8
        assert not blocked

        # Pass through validator (WEAK = 40% penalty - RESEARCH-BASED 2025-11-26)
        conf, penalty, _ = validator.validate_volume(conf, volume_conf)

        assert conf == pytest.approx(0.48)  # 0.8 * 0.6 = 40% penalty
        assert penalty == 0.6

    def test_pipeline_both_penalize_minimal(self):
        """Test pipeline where both gatekeeper and validator reduce confidence (MINIMAL volume)"""
        gatekeeper = TrendGatekeeper()
        validator = VolumeValidator()

        # Setup trend filter (NEUTRAL - reduces confidence)
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.7
        trend_filter.metadata = {"trend": "NEUTRAL"}

        # Setup volume confirmation (NOT CONFIRMED + MINIMAL)
        volume_conf = Mock(spec=IndicatorSignal)
        volume_conf.metadata = {"confirmed": False, "strength": "MINIMAL"}

        # Pass through gatekeeper (NEUTRAL trend = 10% penalty - RESEARCH-BASED)
        action, conf, blocked, _ = gatekeeper.check_signal(
            SignalAction.BUY,
            1.0,
            trend_filter
        )

        assert action == SignalAction.BUY
        assert conf == 0.9  # 1.0 * 0.9 (10% penalty - RESEARCH-BASED 2025-11-26)
        assert not blocked

        # Pass through validator (MINIMAL = 70% penalty)
        conf, penalty, _ = validator.validate_volume(conf, volume_conf)

        assert conf == pytest.approx(0.27)  # 0.9 * 0.3 (combined penalties)
        assert penalty == 0.3

    def test_pipeline_both_penalize_moderate(self):
        """Test pipeline with NEUTRAL trend + MODERATE unconfirmed volume"""
        gatekeeper = TrendGatekeeper()
        validator = VolumeValidator()

        # Setup trend filter (NEUTRAL)
        trend_filter = Mock(spec=IndicatorSignal)
        trend_filter.confidence = 0.7
        trend_filter.metadata = {"trend": "NEUTRAL"}

        # Setup volume confirmation (NOT CONFIRMED + MODERATE)
        volume_conf = Mock(spec=IndicatorSignal)
        volume_conf.metadata = {"confirmed": False, "strength": "MODERATE"}

        # Pass through gatekeeper (NEUTRAL = 10% penalty - RESEARCH-BASED)
        action, conf, blocked, _ = gatekeeper.check_signal(
            SignalAction.BUY,
            1.0,
            trend_filter
        )

        assert action == SignalAction.BUY
        assert conf == 0.9  # 1.0 * 0.9 (10% penalty - RESEARCH-BASED 2025-11-26)
        assert not blocked

        # Pass through validator (MODERATE unconfirmed = 30% penalty)
        conf, penalty, _ = validator.validate_volume(conf, volume_conf)

        assert conf == pytest.approx(0.63)  # 0.9 * 0.7 (combined penalties)
        assert penalty == 0.7
