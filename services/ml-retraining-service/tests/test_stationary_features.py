"""
Tests for ``app.core.stationary_features`` — chunk 2 of the T0.1 GRU
rebuild. Pure pandas/numpy; runs without tensorflow.

Coverage:
- The 17-column public list is what the trainer threads as ``feature_cols``.
- The compute function returns exactly those 17 + ``timestamp`` + ``close``.
- Each new column (vol-of-vol, log-volume change, range ratio, time-of-
  day sin/cos) computes the right values on a synthetic input.
- NaN-handling: leading rolling windows produce no surviving rows that
  contain NaN; ``np.log(0)`` rows are dropped instead of leaking +/-inf
  through ``dropna``.
- Legacy level-bound features are NOT present in the result (regression
  hook against a future PR adding ``sma_7`` etc. back).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("numpy")
pytest.importorskip("pandas")

from app.core.stationary_features import (  # noqa: E402
    STATIONARY_FEATURE_COLS,
    compute_stationary_features,
)


# ---------------------------------------------------------------------------
# Public column list
# ---------------------------------------------------------------------------


class TestStationaryFeatureColsList:
    def test_seventeen_columns(self):
        # Locks the contract: chunk 4's training script reads this length
        # to size its run.
        assert len(STATIONARY_FEATURE_COLS) == 17

    def test_no_level_features_present(self):
        # Regression hook: if a future PR adds sma_*, ema_*, bb_middle/
        # upper/lower, volume_sma, or high_low_ratio back here, this fails.
        forbidden = {
            "sma_7", "sma_14", "sma_30",
            "ema_7", "ema_14",
            "bb_middle", "bb_upper", "bb_lower",
            "volume_sma",
            "high_low_ratio",
            "close", "open", "high", "low", "volume",  # raw OHLCV bars
        }
        bad = forbidden & set(STATIONARY_FEATURE_COLS)
        assert not bad, f"level-bound features in stationary list: {bad}"

    def test_new_features_present(self):
        # The three additions called out in the design doc §3.
        assert "vol_of_vol_14" in STATIONARY_FEATURE_COLS
        assert "log_volume_change" in STATIONARY_FEATURE_COLS
        assert "range_ratio_14" in STATIONARY_FEATURE_COLS
        # Plus the time-of-day cyclical encoding.
        assert "hour_sin" in STATIONARY_FEATURE_COLS
        assert "hour_cos" in STATIONARY_FEATURE_COLS


# ---------------------------------------------------------------------------
# compute_stationary_features — output shape
# ---------------------------------------------------------------------------


def _make_synthetic_ohlcv(n: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = 100 + np.cumsum(rng.normal(0, 0.5, n))
    high = base + np.abs(rng.normal(0, 0.3, n))
    low = base - np.abs(rng.normal(0, 0.3, n))
    open_ = base + rng.normal(0, 0.1, n)
    close = base + rng.normal(0, 0.1, n)
    volume = np.abs(rng.normal(1000, 100, n))
    timestamps = pd.date_range("2026-01-01", periods=n, freq="60min")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


class TestComputeStationaryFeaturesShape:
    def test_returned_columns_are_timestamp_close_plus_stationary(self):
        df = _make_synthetic_ohlcv()
        out = compute_stationary_features(df)
        expected = {"timestamp", "close", *STATIONARY_FEATURE_COLS}
        assert set(out.columns) == expected

    def test_no_nan_rows_in_output(self):
        df = _make_synthetic_ohlcv()
        out = compute_stationary_features(df)
        assert out.isna().sum().sum() == 0

    def test_drops_leading_rows_for_rolling_windows(self):
        df = _make_synthetic_ohlcv(n=200)
        out = compute_stationary_features(df)
        # Vol-of-vol is std of std with two 14-windows + log_returns shift
        # — at least 28 leading rows are NaN; result is shorter than input.
        assert 0 < len(out) < len(df)

    def test_zero_volume_row_dropped(self):
        # log(volume / shift(volume)) is +/-inf when either side is 0.
        # Row should be dropped instead of leaking infinity through
        # MinMaxScaler downstream.
        df = _make_synthetic_ohlcv()
        df.loc[100, "volume"] = 0.0
        out = compute_stationary_features(df)
        assert np.isfinite(out["log_volume_change"]).all()
        # The bad row's timestamp should not appear in the output.
        assert df.loc[100, "timestamp"] not in out["timestamp"].values

    def test_close_column_preserved_for_last_close_extraction(self):
        # The trainer needs ``data_with_features['close']`` for
        # ``last_close_*``. Stationary mode must not strip it even though
        # close isn't a feature.
        df = _make_synthetic_ohlcv()
        out = compute_stationary_features(df)
        assert "close" in out.columns
        assert out["close"].notna().all()


# ---------------------------------------------------------------------------
# Individual feature correctness
# ---------------------------------------------------------------------------


class TestNewFeatures:
    def test_log_volume_change_matches_definition(self):
        df = _make_synthetic_ohlcv()
        out = compute_stationary_features(df)
        # log_volume_change[t] should equal log(volume[t] / volume[t-1])
        # for surviving rows. Reconstruct from input on the matching
        # timestamps to confirm.
        merged = out.merge(df[["timestamp", "volume"]], on="timestamp", how="inner")
        merged = merged.sort_values("timestamp").reset_index(drop=True)
        prev_volume = (
            df.set_index("timestamp")
            .loc[merged["timestamp"]]
            ["volume"]
            .shift(1)
            .reset_index(drop=True)
        )
        expected = np.log(merged["volume"] / prev_volume)
        # Drop leading NaN from shift; compare on overlapping rows.
        mask = expected.notna()
        np.testing.assert_allclose(
            merged.loc[mask, "log_volume_change"].values,
            expected[mask].values,
        )

    def test_hour_sin_cos_encode_utc_hour(self):
        # 24 hourly bars over one full day → hour_sin should sweep one
        # full sine cycle. hour_cos at hour 0 = 1; at hour 12 = -1.
        df = _make_synthetic_ohlcv(n=300)
        out = compute_stationary_features(df)
        # Pull a row whose timestamp hour is 0 and one whose hour is 12.
        out_with_hour = out.assign(_h=out["timestamp"].dt.hour)
        h0 = out_with_hour[out_with_hour["_h"] == 0].iloc[0]
        h12 = out_with_hour[out_with_hour["_h"] == 12].iloc[0]
        assert h0["hour_cos"] == pytest.approx(1.0, abs=1e-9)
        assert h0["hour_sin"] == pytest.approx(0.0, abs=1e-9)
        assert h12["hour_cos"] == pytest.approx(-1.0, abs=1e-9)
        assert abs(h12["hour_sin"]) < 1e-9

    def test_range_ratio_14_centers_around_one(self):
        # range_ratio_14 = bar_range / mean(bar_range_14). On a stationary
        # synthetic series it should hover around 1.0.
        df = _make_synthetic_ohlcv(n=500)
        out = compute_stationary_features(df)
        assert 0.5 < out["range_ratio_14"].mean() < 2.0

    def test_vol_of_vol_14_nonnegative(self):
        df = _make_synthetic_ohlcv(n=300)
        out = compute_stationary_features(df)
        # std of std → always non-negative.
        assert (out["vol_of_vol_14"] >= 0).all()


class TestNoTimestampInput:
    def test_falls_back_to_zero_hour_signal(self):
        # If the caller forgets to pass a datetime timestamp, we don't
        # blow up — hour_sin / hour_cos fall back to 0/1 (sin(0)=0,
        # cos(0)=1). Lets one-shot scripts work on raw arrays.
        df = _make_synthetic_ohlcv()
        df = df.drop(columns=["timestamp"])
        out = compute_stationary_features(df)
        # sin(0) = 0, cos(0) = 1
        assert (out["hour_sin"] == 0.0).all()
        assert (out["hour_cos"] == 1.0).all()


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
