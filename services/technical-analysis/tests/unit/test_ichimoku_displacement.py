#!/usr/bin/env python3
"""
Regression tests for Ichimoku displacement wiring.

`IndicatorService.calculate_ichimoku` used to construct IchimokuCalculator
without passing `displacement`, so it silently kept the 9/26/52 default of 26
even when the caller ran the crypto-scaled 20/60/120 periods the signal
aggregator sends. Conventional Ichimoku sets displacement == kijun period;
measured on 365d hourly BTC, leaving it at 26 flipped 19.5% of final
BUY/SELL/HOLD verdicts on the aggregator's heaviest-weighted (1.3x) leg.

The warm-up gate had the same stale literal (`senkou_b + 26`), which would
admit windows that `calculate()` then rejects.
"""

import pathlib
import sys
from unittest.mock import AsyncMock, patch

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from app.indicators.ichimoku import IchimokuCalculator  # noqa: E402
from app.services.indicator_service import IndicatorService  # noqa: E402

# Periods signal_aggregator.fetch_ichimoku sends (CRYPTO-OPTIMIZED 2025-12-23)
TENKAN, KIJUN, SENKOU_B = 20, 60, 120
# Endpoint default; fetch_ichimoku sends no `limit` (main.py ichimoku_endpoint)
LIVE_LIMIT = 200


def _ohlc(bars: int, seed: int = 7) -> pd.DataFrame:
    """Deterministic trending OHLC frame with enough movement to cross a cloud."""
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0.05, 1.2, bars))
    high = close + rng.uniform(0.1, 1.0, bars)
    low = close - rng.uniform(0.1, 1.0, bars)
    return pd.DataFrame(
        {
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.uniform(100, 1000, bars),
        },
        index=pd.date_range("2026-01-01", periods=bars, freq="h"),
    )


async def _call_service(df: pd.DataFrame, limit: int = LIVE_LIMIT):
    fetcher = AsyncMock()
    fetcher.get_klines_as_dataframe = AsyncMock(return_value=df)
    with patch("app.services.indicator_service.get_fetcher", return_value=fetcher):
        return await IndicatorService.calculate_ichimoku(
            "BTCUSDT", "60", TENKAN, KIJUN, SENKOU_B, limit
        )


@pytest.mark.asyncio
async def test_service_uses_displacement_equal_to_kijun():
    """The service's verdict must match displacement=kijun, not the 26 default."""
    df = _ohlc(LIVE_LIMIT)

    # calculate_with_signal returns (data, signal, confidence); the service
    # passes that tuple straight through as "data"
    served_data, served_signal, served_conf = (await _call_service(df))["data"]

    correct = IchimokuCalculator(TENKAN, KIJUN, SENKOU_B, displacement=KIJUN)
    expected_data, expected_signal, expected_conf = correct.calculate_with_signal(df)

    assert served_signal == expected_signal
    assert served_conf == pytest.approx(expected_conf)
    assert served_data["price_position"] == expected_data["price_position"]
    assert served_data["cloud_top"] == pytest.approx(expected_data["cloud_top"])
    assert served_data["cloud_bottom"] == pytest.approx(expected_data["cloud_bottom"])


@pytest.mark.asyncio
async def test_service_does_not_use_the_stale_default_displacement():
    """Guard the specific defect: displacement stuck at 26 while kijun is 60.

    Uses a seed where the two displacements genuinely disagree, so the test
    fails loudly if the `displacement=` kwarg is ever dropped again.
    """
    stale = IchimokuCalculator(TENKAN, KIJUN, SENKOU_B, displacement=26)
    correct = IchimokuCalculator(TENKAN, KIJUN, SENKOU_B, displacement=KIJUN)

    df = None
    for seed in range(40):
        candidate = _ohlc(LIVE_LIMIT, seed=seed)
        s_data, _, _ = stale.calculate_with_signal(candidate)
        c_data, _, _ = correct.calculate_with_signal(candidate)
        if s_data["cloud_top"] != c_data["cloud_top"]:
            df = candidate
            break
    assert df is not None, "no seed produced a disagreeing cloud - fixture too tame"

    served_data, _, _ = (await _call_service(df))["data"]
    stale_data, _, _ = stale.calculate_with_signal(df)

    assert served_data["cloud_top"] != pytest.approx(stale_data["cloud_top"]), (
        "service is still reading the cloud at displacement=26"
    )


@pytest.mark.asyncio
async def test_warmup_gate_tracks_calculator_min_periods():
    """The 400 threshold must be calculator.min_periods, not senkou_b + 26."""
    required = IchimokuCalculator(
        TENKAN, KIJUN, SENKOU_B, displacement=KIJUN
    ).min_periods
    assert required == SENKOU_B + KIJUN == 180

    # One bar short of the real requirement. The stale gate (senkou_b + 26 =
    # 146) would have let this through, and calculate() would then return None.
    with pytest.raises(HTTPException) as exc:
        await _call_service(_ohlc(required - 1), limit=required - 1)
    assert exc.value.status_code == 400
    assert str(required) in exc.value.detail

    # Exactly at the requirement the service must produce a real reading,
    # not the (None, NEUTRAL, 0.0) that calculate() returns when starved.
    data, signal, _ = (await _call_service(_ohlc(required), limit=required))["data"]
    assert data is not None
    assert signal.value in ("BUY", "SELL", "HOLD")


def test_live_limit_still_clears_the_raised_warmup_requirement():
    """displacement=60 raises min_periods 146 -> 180 against a fixed limit=200.

    Every additive guard loses 34 bars of slack. detect_kumo_breakout needs
    min_periods + lookback(5) = 185, and calculate_with_signal calls it on the
    live path, so falling under this silently stops the 1.2x kumo boost.
    """
    calc = IchimokuCalculator(TENKAN, KIJUN, SENKOU_B, displacement=KIJUN)
    assert LIVE_LIMIT >= calc.min_periods
    assert LIVE_LIMIT >= calc.min_periods + 5, "kumo-breakout leg would stop firing"
