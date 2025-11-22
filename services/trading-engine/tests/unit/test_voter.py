"""
Unit Tests for Signal Voter
Tests voting and consensus logic for indicator aggregation
"""

import pytest
from decimal import Decimal

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))

from app.aggregation.voter import SignalVoter
from app.models import IndicatorSignal, SignalAction


class TestSignalVoter:
    """Test suite for SignalVoter"""

    @pytest.fixture
    def voter(self):
        """Create SignalVoter with default threshold"""
        return SignalVoter(aggregation_threshold=0.3)

    @pytest.fixture
    def sample_indicators(self):
        """Create sample indicator signals"""
        return {
            "RSI": IndicatorSignal(
                name="RSI",
                signal=SignalAction.BUY,
                confidence=0.85,
                value=35.0
            ),
            "MACD": IndicatorSignal(
                name="MACD",
                signal=SignalAction.BUY,
                confidence=0.75,
                value=5.0
            ),
            "BOLLINGER_BANDS": IndicatorSignal(
                name="BOLLINGER_BANDS",
                signal=SignalAction.SELL,
                confidence=0.60,
                value=0.0
            ),
            "SMA": IndicatorSignal(
                name="SMA",
                signal=SignalAction.HOLD,
                confidence=0.50,
                value=0.0
            ),
            "TREND_FILTER": IndicatorSignal(
                name="TREND_FILTER",
                signal=SignalAction.BUY,
                confidence=0.90,
                value=0.0,
                metadata={"role": "GATEKEEPER"}
            ),
            "VOLUME_CONFIRMATION": IndicatorSignal(
                name="VOLUME_CONFIRMATION",
                signal=SignalAction.BUY,
                confidence=0.80,
                value=0.0,
                metadata={"role": "VALIDATOR"}
            )
        }

    def test_initialization(self, voter):
        """Test voter initializes correctly"""
        assert voter.aggregation_threshold == 0.3

    def test_signal_to_score_buy(self, voter):
        """Test converting BUY signal to score"""
        score = voter.signal_to_score(SignalAction.BUY)
        assert score == 1.0

    def test_signal_to_score_sell(self, voter):
        """Test converting SELL signal to score"""
        score = voter.signal_to_score(SignalAction.SELL)
        assert score == -1.0

    def test_signal_to_score_hold(self, voter):
        """Test converting HOLD signal to score"""
        score = voter.signal_to_score(SignalAction.HOLD)
        assert score == 0.0

    def test_calculate_votes_all_buy(self, voter):
        """Test calculating votes with all BUY signals"""
        indicators = {
            "RSI": IndicatorSignal(
                name="RSI",
                signal=SignalAction.BUY,
                confidence=0.85,
                value=35.0
            ),
            "MACD": IndicatorSignal(
                name="MACD",
                signal=SignalAction.BUY,
                confidence=0.75,
                value=5.0
            )
        }

        score, consensus, buy_count, sell_count, hold_count = voter.calculate_votes(indicators)

        assert score > 0  # Positive score for BUY signals
        assert buy_count == 2
        assert sell_count == 0
        assert hold_count == 0
        assert consensus == 2

    def test_calculate_votes_mixed_signals(self, voter):
        """Test calculating votes with mixed signals"""
        indicators = {
            "RSI": IndicatorSignal(
                name="RSI",
                signal=SignalAction.BUY,
                confidence=0.85,
                value=35.0
            ),
            "MACD": IndicatorSignal(
                name="MACD",
                signal=SignalAction.SELL,
                confidence=0.75,
                value=-5.0
            ),
            "SMA": IndicatorSignal(
                name="SMA",
                signal=SignalAction.HOLD,
                confidence=0.50,
                value=0.0
            )
        }

        score, consensus, buy_count, sell_count, hold_count = voter.calculate_votes(indicators)

        assert buy_count == 1
        assert sell_count == 1
        assert hold_count == 1
        assert consensus == 1

    def test_calculate_votes_empty_indicators(self, voter):
        """Test calculating votes with empty indicators"""
        score, consensus, buy_count, sell_count, hold_count = voter.calculate_votes({})

        assert score == 0.0
        assert consensus == 0
        assert buy_count == 0
        assert sell_count == 0
        assert hold_count == 0

    def test_determine_action_strong_buy(self, voter):
        """Test determining action with strong BUY score"""
        action, confidence = voter.determine_action(0.75)

        assert action == SignalAction.BUY
        assert confidence == 0.75

    def test_determine_action_strong_sell(self, voter):
        """Test determining action with strong SELL score"""
        action, confidence = voter.determine_action(-0.65)

        assert action == SignalAction.SELL
        assert confidence == 0.65

    def test_determine_action_hold(self, voter):
        """Test determining action with weak score"""
        action, confidence = voter.determine_action(0.15)

        assert action == SignalAction.HOLD
        assert confidence > 0.5  # High confidence for HOLD when score near 0

    def test_determine_action_at_threshold(self, voter):
        """Test determining action exactly at threshold"""
        action, confidence = voter.determine_action(0.3)

        assert action == SignalAction.BUY
        assert confidence == 0.3

    def test_filter_non_voting_indicators(self, voter, sample_indicators):
        """Test filtering out non-voting indicators"""
        voting_indicators = voter.filter_non_voting_indicators(sample_indicators)

        # Should exclude TREND_FILTER and VOLUME_CONFIRMATION
        assert len(voting_indicators) == 4
        assert "TREND_FILTER" not in voting_indicators
        assert "VOLUME_CONFIRMATION" not in voting_indicators
        assert "RSI" in voting_indicators
        assert "MACD" in voting_indicators
        assert "BOLLINGER_BANDS" in voting_indicators
        assert "SMA" in voting_indicators

    def test_filter_non_voting_all_voting(self, voter):
        """Test filtering when all indicators are voting"""
        all_voting = {
            "RSI": IndicatorSignal(
                name="RSI",
                signal=SignalAction.BUY,
                confidence=0.85,
                value=35.0
            ),
            "MACD": IndicatorSignal(
                name="MACD",
                signal=SignalAction.BUY,
                confidence=0.75,
                value=5.0
            )
        }

        voting_indicators = voter.filter_non_voting_indicators(all_voting)

        assert len(voting_indicators) == 2
        assert voting_indicators == all_voting


# Test configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
