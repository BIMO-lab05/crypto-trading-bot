"""
Unit Tests for Signal Voter
Tests voting and consensus logic for indicator aggregation
"""

import pytest

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
                name="RSI", signal=SignalAction.BUY, confidence=0.85, value=35.0
            ),
            "MACD": IndicatorSignal(
                name="MACD", signal=SignalAction.BUY, confidence=0.75, value=5.0
            ),
            "BOLLINGER_BANDS": IndicatorSignal(
                name="BOLLINGER_BANDS",
                signal=SignalAction.SELL,
                confidence=0.60,
                value=0.0,
            ),
            "SMA": IndicatorSignal(
                name="SMA", signal=SignalAction.HOLD, confidence=0.50, value=0.0
            ),
            "TREND_FILTER": IndicatorSignal(
                name="TREND_FILTER",
                signal=SignalAction.BUY,
                confidence=0.90,
                value=0.0,
                metadata={"role": "GATEKEEPER"},
            ),
            "VOLUME_CONFIRMATION": IndicatorSignal(
                name="VOLUME_CONFIRMATION",
                signal=SignalAction.BUY,
                confidence=0.80,
                value=0.0,
                metadata={"role": "VALIDATOR"},
            ),
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
                name="RSI", signal=SignalAction.BUY, confidence=0.85, value=35.0
            ),
            "MACD": IndicatorSignal(
                name="MACD", signal=SignalAction.BUY, confidence=0.75, value=5.0
            ),
        }

        score, consensus, buy_count, sell_count, hold_count = voter.calculate_votes(
            indicators
        )

        assert score > 0  # Positive score for BUY signals
        assert buy_count == 2
        assert sell_count == 0
        assert hold_count == 0
        assert consensus == 2

    def test_calculate_votes_mixed_signals(self, voter):
        """Test calculating votes with mixed signals"""
        indicators = {
            "RSI": IndicatorSignal(
                name="RSI", signal=SignalAction.BUY, confidence=0.85, value=35.0
            ),
            "MACD": IndicatorSignal(
                name="MACD", signal=SignalAction.SELL, confidence=0.75, value=-5.0
            ),
            "SMA": IndicatorSignal(
                name="SMA", signal=SignalAction.HOLD, confidence=0.50, value=0.0
            ),
        }

        score, consensus, buy_count, sell_count, hold_count = voter.calculate_votes(
            indicators
        )

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
                name="RSI", signal=SignalAction.BUY, confidence=0.85, value=35.0
            ),
            "MACD": IndicatorSignal(
                name="MACD", signal=SignalAction.BUY, confidence=0.75, value=5.0
            ),
        }

        voting_indicators = voter.filter_non_voting_indicators(all_voting)

        assert len(voting_indicators) == 2
        assert voting_indicators == all_voting


class TestAgreementConfidence:
    """
    Tests for SignalVoter.compute_agreement_confidence (added 2026-05-20).

    The new metric replaces |weighted_score| in CoreAggregator's BUY/SELL path.
    It measures fraction of weighted voting power agreeing with the action,
    weighted by each agreeing indicator's own conviction.
    """

    @pytest.fixture
    def voter(self):
        return SignalVoter(aggregation_threshold=0.15)

    @staticmethod
    def _ind(signal: SignalAction, confidence: float, weight: float = 1.0):
        meta = {"weight": weight} if weight != 1.0 else {}
        return IndicatorSignal(
            name="X",
            signal=signal,
            confidence=confidence,
            value=0.0,
            metadata=meta,
        )

    def test_all_agreeing_at_high_conviction(self, voter):
        """8 indicators all BUY at avg conf 0.6 — confidence near max realistic 0.6."""
        indicators = {f"I{i}": self._ind(SignalAction.BUY, 0.6) for i in range(8)}
        conf = voter.compute_agreement_confidence(indicators, SignalAction.BUY)
        # All 8 agree at conf 0.6, weight 1.0 each: (8*1.0*0.6) / (8*1.0) = 0.6
        assert conf == pytest.approx(0.6, abs=1e-6)

    def test_majority_agreeing(self, voter):
        """5 BUY at 0.5, 3 SELL at 0.5 — agreement conf ~ (5*0.5)/(8) = 0.31."""
        indicators = {}
        for i in range(5):
            indicators[f"B{i}"] = self._ind(SignalAction.BUY, 0.5)
        for i in range(3):
            indicators[f"S{i}"] = self._ind(SignalAction.SELL, 0.5)
        conf = voter.compute_agreement_confidence(indicators, SignalAction.BUY)
        assert conf == pytest.approx(5 * 0.5 / 8, abs=1e-6)
        # The opposite action gets the *other* fraction
        conf_sell = voter.compute_agreement_confidence(indicators, SignalAction.SELL)
        assert conf_sell == pytest.approx(3 * 0.5 / 8, abs=1e-6)

    def test_minority_agreeing(self, voter):
        """3 BUY at 0.5, 5 SELL at 0.5 — for the BUY action, only 3/8 weight × 0.5."""
        indicators = {}
        for i in range(3):
            indicators[f"B{i}"] = self._ind(SignalAction.BUY, 0.5)
        for i in range(5):
            indicators[f"S{i}"] = self._ind(SignalAction.SELL, 0.5)
        conf = voter.compute_agreement_confidence(indicators, SignalAction.BUY)
        # Below the 0.30 min_confidence floor — exactly what we want for noise
        assert conf == pytest.approx(3 * 0.5 / 8, abs=1e-6)
        assert conf < 0.30

    def test_hold_action_returns_zero(self, voter):
        """HOLD action is meaningless for agreement metric — return 0.0 sentinel."""
        indicators = {"X": self._ind(SignalAction.BUY, 0.9)}
        assert voter.compute_agreement_confidence(indicators, SignalAction.HOLD) == 0.0

    def test_empty_indicators_returns_zero(self, voter):
        """No voting power → 0.0, never NaN."""
        assert voter.compute_agreement_confidence({}, SignalAction.BUY) == 0.0

    def test_weighted_indicator_dominates(self, voter):
        """A high-weight indicator (Ichimoku 1.3x, SQZMOM 1.4x) skews the metric."""
        indicators = {
            "RSI": self._ind(SignalAction.SELL, 0.4),
            "MACD": self._ind(SignalAction.SELL, 0.4),
            "ICHIMOKU": self._ind(SignalAction.BUY, 1.0, weight=1.3),
        }
        # Total weight = 1 + 1 + 1.3 = 3.3
        # BUY agreeing weighted conf = 1.3 * 1.0 = 1.3
        # → conf = 1.3 / 3.3 ≈ 0.394
        conf = voter.compute_agreement_confidence(indicators, SignalAction.BUY)
        assert conf == pytest.approx(1.3 / 3.3, abs=1e-6)
        # SELL agreeing = 2 * 0.4 = 0.8 → 0.8/3.3 ≈ 0.242
        conf_sell = voter.compute_agreement_confidence(indicators, SignalAction.SELL)
        assert conf_sell == pytest.approx(0.8 / 3.3, abs=1e-6)

    def test_clamps_to_unit_interval(self, voter):
        """confidence always in [0, 1] even if upstream conf>1 sneaks in."""
        # Indicator confidence is gt=0.0 le=1.0 in the model, but defensive:
        # the validate_confidence helper inside the method clamps regardless.
        indicators = {"X": self._ind(SignalAction.BUY, 1.0)}
        conf = voter.compute_agreement_confidence(indicators, SignalAction.BUY)
        assert 0.0 <= conf <= 1.0
        assert conf == pytest.approx(1.0, abs=1e-6)

    def test_floor_reachability(self, voter):
        """
        The motivating regression: with 5+ indicators agreeing at avg conf 0.5,
        we must clear the 0.30 floor that the legacy |score| metric could not.
        """
        indicators = {
            "RSI": self._ind(SignalAction.BUY, 0.5),
            "MACD": self._ind(SignalAction.BUY, 0.5),
            "EMA": self._ind(SignalAction.BUY, 0.5),
            "BOLLINGER": self._ind(SignalAction.BUY, 0.5),
            "STOCH": self._ind(SignalAction.BUY, 0.5),
            "SMA": self._ind(SignalAction.SELL, 0.5),
            "ICHIMOKU": self._ind(SignalAction.SELL, 0.5),
            "ADX": self._ind(SignalAction.HOLD, 0.5),
        }
        conf = voter.compute_agreement_confidence(indicators, SignalAction.BUY)
        # 5 agreeing × 1.0 × 0.5 = 2.5; total weight = 8.0 → 0.3125
        assert conf >= 0.30, f"Confidence {conf} fails the 0.30 floor"


# Test configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
