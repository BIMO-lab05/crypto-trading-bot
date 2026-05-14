"""
Regression tests for INFRA-06 Bug 2 — confidence=0 signal filter.

The aggregation logic in handlers/analysis.py:get_aggregated_signal builds a
list of (label, confidence) tuples from RSI, MACD, and TrendFilter, then feeds
them through a weighted-sum loop.  Before the INFRA-06 fix, a zero-confidence
tuple was passed straight through to the weighted sum; after the fix an explicit
filter removes any tuple with confidence <= 0.0 and emits a
AGGREGATOR_CONFIDENCE_FILTER log line.

These tests drive get_aggregated_signal through mock indicator calls so we can
inject zero-confidence tuples and assert they are discarded.  Three scenarios:

  (a) confidence=0 tuple is filtered — the zero-confidence vote is absent from
      the aggregated result.
  (b) all-positive tuples aggregate without change — no regression on the
      normal code path.
  (c) empty signal list (all indicators inactive) returns the neutral-fallback
      shape (confidence == 0.5).
"""

import pandas as pd
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_df() -> pd.DataFrame:
    """Minimal DataFrame satisfying the handler's df.empty check."""
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
    """Minimal enum-like object with a .value attribute."""
    m = MagicMock()
    m.value = value
    return m


# ---------------------------------------------------------------------------
# Test (a): confidence=0 tuple is filtered
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confidence_zero_tuple_is_filtered(caplog):
    """
    When the TrendFilter returns confidence=0.0 (inactive indicator), the
    resulting (label, 0.0) tuple must not reach the weighted-sum loop.

    We inject: RSI → ("BUY", 0.8), MACD → ("HOLD", 0.0), trend → absent.
    Without the filter MACD would contribute a HOLD vote of weight 0.0 (harmless
    numerically but the log line must fire).  By patching TrendFilter.calculate to
    return None and MACD to return a zero-confidence signal we trigger the filter.
    """
    import logging
    from app.handlers.analysis import get_aggregated_signal

    mock_df = _make_df()

    rsi_signal_enum = _signal_enum("BUY")
    macd_signal_enum = _signal_enum("HOLD")

    with (
        patch("app.handlers.analysis.get_fetcher") as mock_get_fetcher,
        patch("app.handlers.analysis.RSICalculator") as MockRSI,
        patch("app.handlers.analysis.MACDCalculator") as MockMACD,
        patch("app.handlers.analysis.TrendFilter") as MockTrend,
    ):
        # Fetcher returns our minimal DataFrame
        mock_fetcher_inst = AsyncMock()
        mock_fetcher_inst.get_klines_as_dataframe = AsyncMock(return_value=mock_df)
        mock_get_fetcher.return_value = mock_fetcher_inst

        # RSI: returns a value + (BUY, 0.8)
        rsi_inst = MagicMock()
        rsi_inst.calculate.return_value = 28.0  # below 30 → BUY zone
        rsi_inst.generate_signal.return_value = (rsi_signal_enum, 0.8)
        MockRSI.return_value = rsi_inst

        # MACD: returns a dict + (HOLD, 0.0) — the zero-confidence case
        macd_dict = {"macd_line": 0.1, "signal_line": 0.05, "histogram": 0.05}
        macd_inst = MagicMock()
        macd_inst.calculate.return_value = macd_dict
        macd_inst.generate_signal.return_value = (macd_signal_enum, 0.0)
        MockMACD.return_value = macd_inst

        # TrendFilter: returns None (no trend data) → no trend tuple appended
        trend_inst = MagicMock()
        trend_inst.calculate.return_value = None
        MockTrend.return_value = trend_inst

        with caplog.at_level(logging.INFO, logger="app.handlers.analysis"):
            result = await get_aggregated_signal(symbol="BTCUSDT", interval="60")

    # The only non-zero-confidence tuple was RSI=(BUY, 0.8).
    # After filter: 1 tuple kept (RSI BUY), 1 dropped (MACD HOLD at 0.0).
    # Weighted sum: BUY=0.8, total=0.8 → confidence = 0.8/0.8 = 1.0
    # BUT the handler rounds to 3dp so: round(1.0, 3) == 1.0
    assert result["signal"] == "BUY", (
        f"Expected BUY signal (only RSI contributed); got {result['signal']}"
    )
    # The AGGREGATOR_CONFIDENCE_FILTER log line must have fired.
    assert any("AGGREGATOR_CONFIDENCE_FILTER" in m for m in caplog.messages), (
        "Expected AGGREGATOR_CONFIDENCE_FILTER log line when confidence=0 tuple dropped"
    )


# ---------------------------------------------------------------------------
# Test (b): all-positive tuples aggregate without regression
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_positive_confidence_unchanged():
    """
    When every signal tuple carries confidence > 0, the filter is a no-op and
    the weighted aggregation proceeds exactly as before the INFRA-06 fix.

    Inject: RSI=(BUY, 0.6), MACD=(BUY, 0.4) — both BUY, both positive.
    Expected signal: BUY.  No AGGREGATOR_CONFIDENCE_FILTER log.
    """
    from app.handlers.analysis import get_aggregated_signal

    mock_df = _make_df()

    rsi_signal_enum = _signal_enum("BUY")
    macd_signal_enum = _signal_enum("BUY")

    with (
        patch("app.handlers.analysis.get_fetcher") as mock_get_fetcher,
        patch("app.handlers.analysis.RSICalculator") as MockRSI,
        patch("app.handlers.analysis.MACDCalculator") as MockMACD,
        patch("app.handlers.analysis.TrendFilter") as MockTrend,
    ):
        mock_fetcher_inst = AsyncMock()
        mock_fetcher_inst.get_klines_as_dataframe = AsyncMock(return_value=mock_df)
        mock_get_fetcher.return_value = mock_fetcher_inst

        rsi_inst = MagicMock()
        rsi_inst.calculate.return_value = 25.0
        rsi_inst.generate_signal.return_value = (rsi_signal_enum, 0.6)
        MockRSI.return_value = rsi_inst

        macd_dict = {"macd_line": 0.2, "signal_line": 0.1, "histogram": 0.1}
        macd_inst = MagicMock()
        macd_inst.calculate.return_value = macd_dict
        macd_inst.generate_signal.return_value = (macd_signal_enum, 0.4)
        MockMACD.return_value = macd_inst

        trend_inst = MagicMock()
        trend_inst.calculate.return_value = None
        MockTrend.return_value = trend_inst

        result = await get_aggregated_signal(symbol="ETHUSDT", interval="60")

    assert result["signal"] == "BUY", (
        f"Expected BUY (both RSI and MACD positive); got {result['signal']}"
    )
    # Confidence = (0.6 + 0.4) / (0.6 + 0.4) = 1.0
    assert result["confidence"] == 1.0, (
        f"Expected confidence=1.0 (all weight in BUY); got {result['confidence']}"
    )


# ---------------------------------------------------------------------------
# Test (c): empty signal list → neutral fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_signal_list_returns_neutral_fallback():
    """
    When all indicators fail to produce a signal (rsi_value=None, macd=None,
    trend_result=None), the signals list is empty.  After filtering (nothing to
    drop), total_weight == 0 and the handler falls back to confidence=0.5.
    The signal label will be whichever key max() picks in the all-zero dict
    (typically BUY due to dict ordering — but the contract is confidence==0.5).
    """
    from app.handlers.analysis import get_aggregated_signal

    mock_df = _make_df()

    with (
        patch("app.handlers.analysis.get_fetcher") as mock_get_fetcher,
        patch("app.handlers.analysis.RSICalculator") as MockRSI,
        patch("app.handlers.analysis.MACDCalculator") as MockMACD,
        patch("app.handlers.analysis.TrendFilter") as MockTrend,
    ):
        mock_fetcher_inst = AsyncMock()
        mock_fetcher_inst.get_klines_as_dataframe = AsyncMock(return_value=mock_df)
        mock_get_fetcher.return_value = mock_fetcher_inst

        # RSI: returns None → no RSI signal appended
        rsi_inst = MagicMock()
        rsi_inst.calculate.return_value = None
        MockRSI.return_value = rsi_inst

        # MACD: returns None → no MACD signal appended
        macd_inst = MagicMock()
        macd_inst.calculate.return_value = None
        MockMACD.return_value = macd_inst

        # TrendFilter: returns None → no trend signal appended
        trend_inst = MagicMock()
        trend_inst.calculate.return_value = None
        MockTrend.return_value = trend_inst

        result = await get_aggregated_signal(symbol="SOLUSDT", interval="60")

    # With total_weight == 0, confidence must fall back to 0.5.
    assert result["confidence"] == 0.5, (
        f"Expected neutral-fallback confidence=0.5; got {result['confidence']}"
    )
    # Signal is defined (one of the three keys wins max() on the all-zero dict).
    assert result["signal"] in ("BUY", "SELL", "HOLD"), (
        f"Unexpected signal value: {result['signal']}"
    )
