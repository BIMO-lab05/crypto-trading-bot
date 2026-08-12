#!/usr/bin/env python3
"""
Regression tests for MACD response precision.

`IndicatorService.calculate_macd` used to `round(..., 2)` macd_line /
signal_line / histogram before responding. ADA-scale MACD values (~1e-4 on a
~$0.60 price) all collapse to 0.0, and the trading-engine recomputes
crossovers from the served values — same defect family as the 30-loss ADA
flip-flop bug (487d1bd, PRICE-01/02). The calculator itself returns full
precision; destruction was purely at this response layer. The Bollinger
handler in the same file already serves full-precision `float(...)`.
"""

import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from app.indicators.macd import MACDCalculator  # noqa: E402
from app.models import SignalType  # noqa: E402
from app.services.indicator_service import IndicatorService  # noqa: E402

# Endpoint defaults (Kang 2021 params the signal aggregator sends)
FAST, SLOW, SIGNAL, LIMIT = 5, 35, 5, 200

# ADA-scale MACD reading: every field is far below the 0.005 threshold where
# round(x, 2) flattens it to 0.0
ADA_MACD = {"macd_line": 0.00042, "signal_line": 0.00039, "histogram": 0.00003}


def _ada_ohlc(bars: int = LIMIT, seed: int = 7) -> pd.DataFrame:
    """Deterministic sub-$1 OHLC frame at ADA's price scale (~$0.60)."""
    rng = np.random.default_rng(seed)
    close = 0.60 + np.cumsum(rng.normal(0.0, 0.002, bars))
    return pd.DataFrame(
        {
            "open": close,
            "high": close + rng.uniform(0.0005, 0.003, bars),
            "low": close - rng.uniform(0.0005, 0.003, bars),
            "close": close,
            "volume": rng.uniform(1e5, 1e6, bars),
        },
        index=pd.date_range("2026-01-01", periods=bars, freq="h"),
    )


async def _call_service(df: pd.DataFrame):
    fetcher = AsyncMock()
    fetcher.get_klines_as_dataframe = AsyncMock(return_value=df)
    with patch("app.services.indicator_service.get_fetcher", return_value=fetcher):
        return await IndicatorService.calculate_macd(
            "ADAUSDT", "60", FAST, SLOW, SIGNAL, LIMIT
        )


@pytest.mark.asyncio
async def test_ada_scale_macd_values_survive_the_response_layer():
    """Values of ~1e-4 must be served as-is, not rounded to 0.0."""
    calculator = MagicMock()
    calculator.calculate_with_signal.return_value = (
        dict(ADA_MACD),
        SignalType.BUY,
        0.6,
    )
    fetcher = AsyncMock()
    fetcher.get_klines_as_dataframe = AsyncMock(return_value=_ada_ohlc())
    with (
        patch("app.services.indicator_service.get_fetcher", return_value=fetcher),
        patch(
            "app.services.indicator_service.MACDCalculator",
            return_value=calculator,
        ),
    ):
        result = await IndicatorService.calculate_macd(
            "ADAUSDT", "60", FAST, SLOW, SIGNAL, LIMIT
        )

    assert result["macd_line"] == ADA_MACD["macd_line"]
    assert result["signal_line"] == ADA_MACD["signal_line"]
    assert result["histogram"] == ADA_MACD["histogram"]


@pytest.mark.asyncio
async def test_served_macd_matches_calculator_full_precision_on_ada_prices():
    """End-to-end on sub-$1 prices: response == calculator output, nonzero."""
    df = _ada_ohlc()
    expected, _, _ = MACDCalculator(FAST, SLOW, SIGNAL).calculate_with_signal(df)

    # Fixture sanity: values must sit in the range round(x, 2) destroys
    assert 0 < abs(expected["macd_line"]) < 0.005
    assert 0 < abs(expected["histogram"]) < 0.005

    result = await _call_service(df)

    assert result["macd_line"] == expected["macd_line"]
    assert result["signal_line"] == expected["signal_line"]
    assert result["histogram"] == expected["histogram"]
