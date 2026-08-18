"""
The Phase-3 MTF leg must contribute a non-zero score.

Two defects, fixed together because either alone leaves the leg at zero:
the 0-1 alignment_score was compared against a 50.0 threshold (so the early
return always fired), and signal_strength was read from a key the TA payload
never contains - the correct key is confidence, as the aggregator's own
metadata builder documents at _build_enhanced_signal:476-486.

DORMANT: the enhanced path needs both enable_ml_predictions and
enable_multi_timeframe, which default False. Unit test is the only proof.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

import app.main  # noqa: F401,E402
import app.core.metrics  # noqa: F401,E402

import pytest  # noqa: E402

from app.aggregation.enhanced_aggregator import EnhancedAggregator  # noqa: E402
from app.models import SignalAction  # noqa: E402


@pytest.fixture
def aggregator():
    return EnhancedAggregator(settings=None)


def test_aligned_buy_payload_scores_positive(aggregator):
    """A real TA payload: alignment 2/3, confidence 0.8."""
    payload = {"overall_signal": "BUY", "confidence": 0.8, "alignment_score": 0.667}

    score = aggregator._calculate_mtf_score(payload, SignalAction.BUY)

    assert score == pytest.approx(0.8 * 1.2), (
        f"MTF scored {score}; expected confidence x the 20% alignment bonus"
    )


def test_sell_payload_scores_negative(aggregator):
    payload = {"overall_signal": "SELL", "confidence": 0.9, "alignment_score": 0.75}

    score = aggregator._calculate_mtf_score(payload, SignalAction.SELL)

    assert score == pytest.approx(-0.9 * 1.2)


def test_low_alignment_still_returns_zero(aggregator):
    """The threshold must keep working after the scale fix - 1/3 is below 50%."""
    payload = {"overall_signal": "BUY", "confidence": 0.8, "alignment_score": 0.333}

    assert aggregator._calculate_mtf_score(payload, SignalAction.BUY) == 0.0
