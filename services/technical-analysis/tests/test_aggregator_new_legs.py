"""
ADX and Enhanced SQZMOM must vote; Volume must NOT vote.

All three are computed in this service and exposed as endpoints, but
get_aggregated_signal consulted only RSI, MACD and TrendFilter.

Volume is deliberately not a voter: its labels are CONFIRM/REJECT, which
would KeyError signal_weights[sig] into an HTTP 500, and it is directionally
agnostic - high volume confirms a breakdown as much as a breakout. The
trading-engine models it as a post-vote confidence multiplier
(aggregation/validator.py); this mirrors that.

Patching note: these tests MUST patch the calculators in the
app.handlers.analysis namespace. The fixture frame is 10 rows, below ADX's
29-bar minimum, SQZMOM's 25-bar minimum and Volume's 20-bar period, and
those failure defaults are NOT neutral: ADX returns ("HOLD", 0.3) and
VolumeConfirmation returns _reject_response() with volume_ratio 0.0. An
unpatched leg would therefore cast a real vote / apply a real penalty and
the test would be measuring the wrong thing.
"""

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest


def _make_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100.0] * 10,
            "high": [101.0] * 10,
            "low": [99.0] * 10,
            "close": [100.0] * 10,
            "volume": [1000.0] * 10,
        },
        index=pd.DatetimeIndex([datetime(2026, 1, 1, i) for i in range(10)]),
    )


def _signal_enum(value: str):
    m = MagicMock()
    m.value = value
    return m


def _sqz_frame(signal: str, confidence: float) -> pd.DataFrame:
    return pd.DataFrame({"sqz_signal": [signal], "sqz_confidence": [confidence]})


def _patched(
    adx=("BUY", 0.8), sqz=("BUY", 0.9), volume_confirmed=True, volume_strength="STRONG"
):
    """Patch every leg so only the ones under test carry weight."""
    fetcher = AsyncMock()
    fetcher.get_klines_as_dataframe = AsyncMock(return_value=_make_df())

    rsi_inst = MagicMock()
    rsi_inst.calculate.return_value = None
    macd_inst = MagicMock()
    macd_inst.calculate.return_value = None
    trend_inst = MagicMock()
    trend_inst.calculate.return_value = None

    adx_inst = MagicMock()
    adx_inst.calculate_with_signal.return_value = ({"adx": 30.0}, adx[0], adx[1])
    sqz_inst = MagicMock()
    sqz_inst.calculate.return_value = _sqz_frame(sqz[0], sqz[1])
    vol_inst = MagicMock()
    vol_inst.calculate.return_value = {
        "confirmed": volume_confirmed,
        "strength": volume_strength,
        "volume_ratio": 1.6,
        "confidence": 1.0,
    }

    return patch.multiple(
        "app.handlers.analysis",
        get_fetcher=MagicMock(return_value=fetcher),
        RSICalculator=MagicMock(return_value=rsi_inst),
        MACDCalculator=MagicMock(return_value=macd_inst),
        TrendFilter=MagicMock(return_value=trend_inst),
        ADXCalculator=MagicMock(return_value=adx_inst),
        EnhancedSqueezeMomentum=MagicMock(return_value=sqz_inst),
        VolumeConfirmation=MagicMock(return_value=vol_inst),
    )


@pytest.mark.asyncio
async def test_adx_alone_can_carry_the_signal():
    """With RSI/MACD/trend dead, an ADX BUY must still produce BUY."""
    from app.handlers.analysis import get_aggregated_signal

    with _patched(adx=("BUY", 0.8), sqz=("HOLD", 0.0)):
        result = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    assert result["signal"] == "BUY", (
        f"ADX did not reach the vote; got {result['signal']!r}"
    )
    assert result["adx"]["signal"] == "BUY"


@pytest.mark.asyncio
async def test_sqzmom_alone_can_carry_the_signal():
    from app.handlers.analysis import get_aggregated_signal

    with _patched(adx=("HOLD", 0.0), sqz=("SELL", 0.9)):
        result = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    assert result["signal"] == "SELL", (
        f"SQZMOM did not reach the vote; got {result['signal']!r}"
    )
    assert result["sqzmom"]["signal"] == "SELL"


@pytest.mark.asyncio
async def test_unconfirmed_volume_penalizes_but_does_not_vote():
    """Volume must move confidence, never the label - and never KeyError."""
    from app.handlers.analysis import get_aggregated_signal

    with _patched(
        adx=("BUY", 0.8),
        sqz=("BUY", 0.9),
        volume_confirmed=True,
        volume_strength="STRONG",
    ):
        confirmed = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    with _patched(
        adx=("BUY", 0.8),
        sqz=("BUY", 0.9),
        volume_confirmed=False,
        volume_strength="WEAK",
    ):
        unconfirmed = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    assert confirmed["signal"] == unconfirmed["signal"] == "BUY", (
        "volume changed the direction - it must only scale confidence"
    )
    assert unconfirmed["confidence"] < confirmed["confidence"], (
        f"unconfirmed volume did not penalize confidence: "
        f"{unconfirmed['confidence']} vs {confirmed['confidence']}"
    )
    assert unconfirmed["volume"]["confirmed"] is False


@pytest.mark.asyncio
async def test_empty_vote_still_holds_with_the_new_legs_present():
    """Task 1's neutral fallback must survive the added legs."""
    from app.handlers.analysis import get_aggregated_signal

    with _patched(adx=("HOLD", 0.0), sqz=("HOLD", 0.0)):
        result = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    assert result["signal"] == "HOLD"
    assert result["confidence"] == 0.5
