"""
Tests for Signal Aggregation Modules
Purpose: Test gatekeeper, validator, voter, and core aggregator
"""

import pytest
from decimal import Decimal
from app.aggregation.gatekeeper import TrendGatekeeper
from app.aggregation.validator import VolumeValidator
from app.aggregation.voter import SignalVoter
from app.aggregation.aggregator_core import CoreAggregator
from app.models import SignalAction, IndicatorSignal


class TestTrendGatekeeper:
    """Test TrendGatekeeper (trend filtering logic)"""

    def setup_method(self):
        """Setup test fixtures"""
        self.gatekeeper = TrendGatekeeper()

    def test_block_buy_in_bearish_trend(self):
        """Test that BUY signals are blocked in BEARISH trends"""
        # Create mock trend filter indicator
        trend_filter = IndicatorSignal(
            name="TREND_FILTER",
            signal=SignalAction.SELL,
            confidence=0.8,
            value=Decimal("-5.0"),
            metadata={"trend": "BEARISH", "role": "GATEKEEPER"}
        )

        # Check BUY signal in BEARISH trend
        action, confidence, blocked, reason = self.gatekeeper.check_signal(
            SignalAction.BUY, 0.7, trend_filter
        )

        assert action == SignalAction.HOLD, "BUY should be blocked"
        assert blocked is True, "Signal should be marked as blocked"
        assert "BEARISH trend" in reason
        assert confidence < 0.7, "Confidence should be reduced"

    def test_block_sell_in_bullish_trend(self):
        """Test that SELL signals are blocked in BULLISH trends"""
        trend_filter = IndicatorSignal(
            name="TREND_FILTER",
            signal=SignalAction.BUY,
            confidence=0.8,
            value=Decimal("5.0"),
            metadata={"trend": "BULLISH", "role": "GATEKEEPER"}
        )

        action, confidence, blocked, reason = self.gatekeeper.check_signal(
            SignalAction.SELL, 0.7, trend_filter
        )

        assert action == SignalAction.HOLD, "SELL should be blocked"
        assert blocked is True
        assert "BULLISH trend" in reason

    def test_allow_buy_in_bullish_trend(self):
        """Test that BUY signals pass through in BULLISH trends"""
        trend_filter = IndicatorSignal(
            name="TREND_FILTER",
            signal=SignalAction.BUY,
            confidence=0.8,
            value=Decimal("5.0"),
            metadata={"trend": "BULLISH", "role": "GATEKEEPER"}
        )

        action, confidence, blocked, reason = self.gatekeeper.check_signal(
            SignalAction.BUY, 0.7, trend_filter
        )

        assert action == SignalAction.BUY, "BUY should pass through"
        assert blocked is False
        assert confidence == 0.7, "Confidence unchanged"

    def test_reduce_confidence_in_neutral_trend(self):
        """Test confidence reduction in NEUTRAL trends"""
        trend_filter = IndicatorSignal(
            name="TREND_FILTER",
            signal=SignalAction.HOLD,
            confidence=0.5,
            value=Decimal("0.0"),
            metadata={"trend": "NEUTRAL", "role": "GATEKEEPER"}
        )

        action, confidence, blocked, reason = self.gatekeeper.check_signal(
            SignalAction.BUY, 0.7, trend_filter
        )

        assert action == SignalAction.BUY, "Signal should pass"
        assert blocked is False
        assert abs(confidence - 0.49) < 0.001, "Confidence reduced by 0.7x"  # 0.7 * 0.7 = 0.49

    def test_hold_signal_passes_through(self):
        """Test that HOLD signals always pass through"""
        trend_filter = IndicatorSignal(
            name="TREND_FILTER",
            signal=SignalAction.SELL,
            confidence=0.8,
            value=Decimal("-5.0"),
            metadata={"trend": "BEARISH", "role": "GATEKEEPER"}
        )

        action, confidence, blocked, reason = self.gatekeeper.check_signal(
            SignalAction.HOLD, 0.5, trend_filter
        )

        assert action == SignalAction.HOLD
        assert blocked is False
        assert confidence == 0.5, "Confidence unchanged for HOLD"

    def test_no_trend_filter_available(self):
        """Test graceful handling when trend filter is None"""
        action, confidence, blocked, reason = self.gatekeeper.check_signal(
            SignalAction.BUY, 0.7, None
        )

        assert action == SignalAction.BUY
        assert blocked is False
        assert confidence == 0.7


class TestVolumeValidator:
    """Test VolumeValidator (volume confirmation logic)"""

    def setup_method(self):
        """Setup test fixtures"""
        self.validator = VolumeValidator()

    def test_confirmed_volume_no_penalty(self):
        """Test that confirmed volume has no confidence penalty"""
        volume_conf = IndicatorSignal(
            name="VOLUME_CONFIRMATION",
            signal=SignalAction.BUY,
            confidence=0.8,
            value=Decimal("1.5"),
            metadata={
                "confirmed": True,
                "strength": "STRONG",
                "role": "VALIDATOR"
            }
        )

        confidence, penalty, reason = self.validator.validate_volume(0.7, volume_conf)

        assert confidence == 0.7, "Confidence unchanged"
        assert penalty == 1.0, "No penalty applied"
        assert "confirmed" in reason.lower()

    def test_unconfirmed_volume_penalty(self):
        """Test that unconfirmed volume applies 70% penalty"""
        volume_conf = IndicatorSignal(
            name="VOLUME_CONFIRMATION",
            signal=SignalAction.HOLD,
            confidence=0.3,
            value=Decimal("0.8"),
            metadata={
                "confirmed": False,
                "strength": "WEAK",
                "role": "VALIDATOR"
            }
        )

        confidence, penalty, reason = self.validator.validate_volume(0.7, volume_conf)

        assert confidence == 0.21, "Confidence reduced to 30% (0.7 * 0.3)"
        assert penalty == 0.3, "70% penalty applied"
        assert "Low volume" in reason

    def test_no_volume_data(self):
        """Test graceful handling when volume confirmation is None"""
        confidence, penalty, reason = self.validator.validate_volume(0.7, None)

        assert confidence == 0.7, "Confidence unchanged"
        assert penalty == 1.0, "No penalty"


class TestSignalVoter:
    """Test SignalVoter (voting and consensus logic)"""

    def setup_method(self):
        """Setup test fixtures"""
        self.voter = SignalVoter(aggregation_threshold=0.3)

    def test_signal_to_score_conversion(self):
        """Test signal to score conversion"""
        assert self.voter.signal_to_score(SignalAction.BUY) == 1.0
        assert self.voter.signal_to_score(SignalAction.SELL) == -1.0
        assert self.voter.signal_to_score(SignalAction.HOLD) == 0.0

    def test_calculate_votes_all_buy(self):
        """Test vote calculation when all indicators say BUY"""
        indicators = {
            "RSI": IndicatorSignal(name="RSI", signal=SignalAction.BUY, confidence=0.8, value=30),
            "MACD": IndicatorSignal(name="MACD", signal=SignalAction.BUY, confidence=0.7, value=0.5),
            "BB": IndicatorSignal(name="BB", signal=SignalAction.BUY, confidence=0.9, value=100)
        }

        score, consensus, buy_count, sell_count, hold_count = \
            self.voter.calculate_votes(indicators)

        assert buy_count == 3
        assert sell_count == 0
        assert hold_count == 0
        assert consensus == 3
        assert score > 0.7, "Aggregated score should be positive"

    def test_calculate_votes_mixed_signals(self):
        """Test vote calculation with mixed signals"""
        indicators = {
            "RSI": IndicatorSignal(name="RSI", signal=SignalAction.BUY, confidence=0.8, value=30),
            "MACD": IndicatorSignal(name="MACD", signal=SignalAction.SELL, confidence=0.7, value=-0.5),
            "BB": IndicatorSignal(name="BB", signal=SignalAction.HOLD, confidence=0.5, value=100)
        }

        score, consensus, buy_count, sell_count, hold_count = \
            self.voter.calculate_votes(indicators)

        assert buy_count == 1
        assert sell_count == 1
        assert hold_count == 1
        assert consensus == 1  # Max count
        assert abs(score) < 0.3, "Mixed signals should yield low score"

    def test_determine_action_buy(self):
        """Test action determination for strong BUY score"""
        action, confidence = self.voter.determine_action(0.8)

        assert action == SignalAction.BUY
        assert confidence == 0.8

    def test_determine_action_sell(self):
        """Test action determination for strong SELL score"""
        action, confidence = self.voter.determine_action(-0.8)

        assert action == SignalAction.SELL
        assert confidence == 0.8

    def test_determine_action_hold(self):
        """Test action determination for weak score"""
        action, confidence = self.voter.determine_action(0.1)

        assert action == SignalAction.HOLD
        assert confidence == 0.9  # 1.0 - 0.1

    def test_filter_non_voting_indicators(self):
        """Test filtering out GATEKEEPER and VALIDATOR from voting"""
        all_indicators = {
            "RSI": IndicatorSignal(name="RSI", signal=SignalAction.BUY, confidence=0.8, value=30),
            "TREND_FILTER": IndicatorSignal(name="TREND_FILTER", signal=SignalAction.BUY, confidence=0.9, value=5),
            "VOLUME_CONFIRMATION": IndicatorSignal(name="VOLUME_CONFIRMATION", signal=SignalAction.HOLD, confidence=0.5, value=1.2),
            "MACD": IndicatorSignal(name="MACD", signal=SignalAction.SELL, confidence=0.7, value=-0.5)
        }

        voting_indicators = self.voter.filter_non_voting_indicators(all_indicators)

        assert len(voting_indicators) == 2
        assert "RSI" in voting_indicators
        assert "MACD" in voting_indicators
        assert "TREND_FILTER" not in voting_indicators
        assert "VOLUME_CONFIRMATION" not in voting_indicators


class TestCoreAggregator:
    """Test CoreAggregator (pipeline orchestration)"""

    def setup_method(self):
        """Setup test fixtures"""
        from app.config import get_settings
        self.aggregator = CoreAggregator(get_settings())

    def test_aggregate_signals_no_indicators(self):
        """Test error handling when no indicators available"""
        signal = self.aggregator.aggregate_signals({}, 1234567890)

        assert signal.action == SignalAction.HOLD
        assert signal.confidence == 0.0
        assert "error" in signal.metadata

    def test_aggregate_signals_strong_buy(self):
        """Test aggregation with strong BUY consensus"""
        indicators = {
            "RSI": IndicatorSignal(name="RSI", signal=SignalAction.BUY, confidence=0.9, value=25),
            "MACD": IndicatorSignal(name="MACD", signal=SignalAction.BUY, confidence=0.8, value=1.5),
            "BB": IndicatorSignal(name="BB", signal=SignalAction.BUY, confidence=0.85, value=100),
            "SMA": IndicatorSignal(name="SMA", signal=SignalAction.BUY, confidence=0.75, value=50),
            "EMA": IndicatorSignal(name="EMA", signal=SignalAction.BUY, confidence=0.8, value=50),
            "STOCHASTIC": IndicatorSignal(name="STOCHASTIC", signal=SignalAction.BUY, confidence=0.7, value=20),
            "TREND_FILTER": IndicatorSignal(name="TREND_FILTER", signal=SignalAction.BUY, confidence=0.9, value=5.0,
                                           metadata={"trend": "BULLISH"}),
            "VOLUME_CONFIRMATION": IndicatorSignal(name="VOLUME_CONFIRMATION", signal=SignalAction.BUY, confidence=0.8, value=1.5,
                                                  metadata={"confirmed": True, "strength": "STRONG"})
        }

        signal = self.aggregator.aggregate_signals(indicators, 1234567890)

        # With 6 BUY votes out of 6 voting indicators (excluding TREND_FILTER and VOLUME_CONFIRMATION)
        # and confirmed volume + bullish trend, should pass
        assert signal.action == SignalAction.BUY or signal.action == SignalAction.HOLD
        assert signal.metadata["phase_1_active"] is True
        assert "voting_indicators_count" in signal.metadata

    def test_aggregate_signals_blocked_by_gatekeeper(self):
        """Test that counter-trend trades are blocked"""
        indicators = {
            "RSI": IndicatorSignal(name="RSI", signal=SignalAction.BUY, confidence=0.9, value=25),
            "MACD": IndicatorSignal(name="MACD", signal=SignalAction.BUY, confidence=0.8, value=1.5),
            "BB": IndicatorSignal(name="BB", signal=SignalAction.BUY, confidence=0.85, value=100),
            "SMA": IndicatorSignal(name="SMA", signal=SignalAction.BUY, confidence=0.75, value=50),
            "EMA": IndicatorSignal(name="EMA", signal=SignalAction.BUY, confidence=0.8, value=50),
            "STOCHASTIC": IndicatorSignal(name="STOCHASTIC", signal=SignalAction.BUY, confidence=0.7, value=20),
            "TREND_FILTER": IndicatorSignal(name="TREND_FILTER", signal=SignalAction.SELL, confidence=0.9, value=-5.0,
                                           metadata={"trend": "BEARISH"}),  # Counter-trend!
            "VOLUME_CONFIRMATION": IndicatorSignal(name="VOLUME_CONFIRMATION", signal=SignalAction.BUY, confidence=0.8, value=1.5,
                                                  metadata={"confirmed": True, "strength": "STRONG"})
        }

        signal = self.aggregator.aggregate_signals(indicators, 1234567890)

        # BUY in BEARISH trend should be blocked
        assert signal.action == SignalAction.HOLD
        assert signal.metadata["trend_blocked"] is True
        assert "BEARISH" in signal.metadata["trend_reason"]

    def test_aggregate_signals_low_volume_penalty(self):
        """Test that low volume reduces confidence"""
        indicators = {
            "RSI": IndicatorSignal(name="RSI", signal=SignalAction.BUY, confidence=0.9, value=25),
            "MACD": IndicatorSignal(name="MACD", signal=SignalAction.BUY, confidence=0.8, value=1.5),
            "BB": IndicatorSignal(name="BB", signal=SignalAction.BUY, confidence=0.85, value=100),
            "SMA": IndicatorSignal(name="SMA", signal=SignalAction.BUY, confidence=0.75, value=50),
            "TREND_FILTER": IndicatorSignal(name="TREND_FILTER", signal=SignalAction.BUY, confidence=0.9, value=5.0,
                                           metadata={"trend": "BULLISH"}),
            "VOLUME_CONFIRMATION": IndicatorSignal(name="VOLUME_CONFIRMATION", signal=SignalAction.HOLD, confidence=0.3, value=0.7,
                                                  metadata={"confirmed": False, "strength": "WEAK"})  # Low volume!
        }

        signal = self.aggregator.aggregate_signals(indicators, 1234567890)

        # Volume penalty should be applied
        assert signal.metadata["volume_penalty"] == 0.3
        assert "Low volume" in signal.metadata["volume_reason"]
