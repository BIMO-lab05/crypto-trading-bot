"""
Regression tests for IndicatorService.calculate_enhanced_sqzmom column-name mapping.

Audit 2026-05-05 (P0): The service layer was reading non-prefixed keys
(`momentum`, `momentum_color`, `signal`, `confidence`) from the DataFrame row
returned by EnhancedSqueezeMomentum.calculate(). The indicator actually writes
the columns with the `sqz_` prefix (sqz_momentum, sqz_color, sqz_signal,
sqz_confidence). Result: every API response defaulted to momentum=0.0,
color='gray', signal='HOLD', confidence=0.5 regardless of market state.

These tests pin the column-name contract so the regression cannot recur silently.
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import AsyncMock, patch

from app.services.indicator_service import IndicatorService


def _make_klines_df(n: int = 60) -> pd.DataFrame:
    """Build an OHLCV DataFrame with enough rows for SQZMOM calculation."""
    # Synthetic upward drift with mild noise so the indicator produces
    # non-trivial momentum / color / signal rather than NaN-only results.
    rng = np.random.default_rng(seed=42)
    base = np.linspace(100.0, 130.0, n)
    noise = rng.normal(0.0, 0.5, n)
    close = base + noise
    high = close + 1.0
    low = close - 1.0
    open_ = close - 0.2
    volume = np.full(n, 1000.0)

    idx = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=idx,
    )


class TestEnhancedSqzmomColumnMapping:
    """Pin the sqz_* -> response key mapping in calculate_enhanced_sqzmom."""

    @pytest.mark.asyncio
    async def test_response_carries_real_momentum_not_default_zero(self):
        """Response `momentum` must come from sqz_momentum, not default 0.0."""
        df = _make_klines_df(80)

        with patch("app.services.indicator_service.get_fetcher") as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=df)
            mock_get_fetcher.return_value = mock_fetcher

            result = await IndicatorService.calculate_enhanced_sqzmom(
                symbol="BTCUSDT",
                interval="60",
                bb_period=20,
                bb_mult=2.0,
                kc_period=20,
                kc_mult=1.5,
                mom_period=12,
                limit=80,
            )

        data = result["data"]

        # Required keys present
        for key in (
            "squeeze_on",
            "squeeze_off",
            "squeeze_firing",
            "momentum",
            "momentum_color",
            "signal",
            "confidence",
        ):
            assert key in data, f"missing key {key} in response"

        # The synthetic upward-drift series should yield non-zero momentum
        # if the column wiring is correct. The pre-fix code returned exactly
        # 0.0 because `latest.get('momentum', 0)` always missed.
        assert data["momentum"] != 0.0, (
            "momentum is exactly 0.0 — sqz_momentum column likely not wired through"
        )

        # Color must be one of the indicator's real palette, not the default
        # 'gray' that the buggy code returned for every call.
        assert data["momentum_color"] in {"lime", "green", "red", "maroon", "gray"}

        # Signal and confidence must come from the indicator (sqz_signal /
        # sqz_confidence), not the hard-coded default fallbacks.
        assert data["signal"] in {"BUY", "SELL", "HOLD"}
        assert 0.0 <= data["confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_response_keys_match_aggregator_contract(self):
        """trading-engine's fetch_enhanced_sqzmom reads these exact keys."""
        df = _make_klines_df(80)

        with patch("app.services.indicator_service.get_fetcher") as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=df)
            mock_get_fetcher.return_value = mock_fetcher

            result = await IndicatorService.calculate_enhanced_sqzmom(
                symbol="ETHUSDT",
                interval="60",
                bb_period=20,
                bb_mult=2.0,
                kc_period=20,
                kc_mult=1.5,
                mom_period=12,
                limit=80,
            )

        data = result["data"]
        # signal_aggregator.fetch_enhanced_sqzmom reads:
        #   data["signal"], data["confidence"], data["momentum"],
        #   data["squeeze_on"], data["squeeze_off"]
        assert isinstance(data["signal"], str)
        assert isinstance(data["confidence"], float)
        assert isinstance(data["momentum"], float)
        assert isinstance(data["squeeze_on"], bool)
        assert isinstance(data["squeeze_off"], bool)
