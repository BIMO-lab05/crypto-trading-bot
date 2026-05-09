"""Unit tests for app.risk.vol_targeting (T1.2 estimator + sizing helper)."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.risk.vol_targeting import (
    HOURLY_ANNUALISATION,
    RealizedVolEstimator,
    VolEstimatorConfig,
    VolParitySizingConfig,
    vol_parity_size,
)


def _series(start_price: float, returns: list[float], start: datetime, hours: int = 1):
    """Yield (ts, close) pairs by compounding returns from start_price."""
    px = start_price
    ts = start
    yield ts, px  # seed bar; produces no return
    for r in returns:
        ts = ts + timedelta(hours=hours)
        px = px * math.exp(r)
        yield ts, px


class TestRealizedVolEstimator:
    def test_empty_returns_none(self):
        est = RealizedVolEstimator(VolEstimatorConfig(min_samples=10))
        assert est.get_realized_vol_annualized("SOLUSDT") is None
        assert est.sample_count("SOLUSDT") == 0

    def test_below_min_samples_returns_none(self):
        est = RealizedVolEstimator(VolEstimatorConfig(min_samples=10))
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for ts, px in _series(100.0, [0.01] * 5, start):
            est.update("SOLUSDT", ts, px)
        assert est.sample_count("SOLUSDT") == 5
        assert est.get_realized_vol_annualized("SOLUSDT") is None

    def test_zero_vol_constant_price(self):
        est = RealizedVolEstimator(VolEstimatorConfig(min_samples=10, window_bars=100))
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # All returns identical -> zero variance
        for ts, px in _series(100.0, [0.0] * 50, start):
            est.update("SOLUSDT", ts, px)
        v = est.get_realized_vol_annualized("SOLUSDT")
        assert v == pytest.approx(0.0, abs=1e-12)

    def test_known_vol_recovered(self):
        # Hourly stdev of log returns = 0.01 -> annualised ≈ 0.01 * sqrt(24*365) ≈ 0.927
        est = RealizedVolEstimator(VolEstimatorConfig(min_samples=10, window_bars=10000))
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # Deterministic +/- 0.01 alternating returns -> sample stdev ≈ 0.01
        rets = [0.01 if i % 2 == 0 else -0.01 for i in range(2000)]
        for ts, px in _series(100.0, rets, start):
            est.update("SOLUSDT", ts, px)
        v = est.get_realized_vol_annualized("SOLUSDT")
        # Sample stdev of {+0.01, -0.01, ...} (with n large, mean ≈ 0) -> 0.01
        assert v == pytest.approx(0.01 * HOURLY_ANNUALISATION, rel=0.05)

    def test_symbols_independent(self):
        est = RealizedVolEstimator(VolEstimatorConfig(min_samples=10))
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for ts, px in _series(100.0, [0.0] * 30, start):
            est.update("SOLUSDT", ts, px)
        for ts, px in _series(100.0, [0.02] * 30, start):
            est.update("BNBUSDT", ts, px)
        sol = est.get_realized_vol_annualized("SOLUSDT")
        bnb = est.get_realized_vol_annualized("BNBUSDT")
        assert sol == pytest.approx(0.0, abs=1e-12)
        # BNB returns are constant +0.02 each, sample stdev = 0
        assert bnb == pytest.approx(0.0, abs=1e-12)
        assert est.sample_count("ADAUSDT") == 0

    def test_window_bound(self):
        est = RealizedVolEstimator(
            VolEstimatorConfig(min_samples=5, window_bars=50)
        )
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for ts, px in _series(100.0, [0.0] * 200, start):
            est.update("SOLUSDT", ts, px)
        # Window-bounded — older returns evicted
        assert est.sample_count("SOLUSDT") == 50

    def test_drops_non_positive_close(self):
        est = RealizedVolEstimator(VolEstimatorConfig(min_samples=2))
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        est.update("SOLUSDT", start, 100.0)
        est.update("SOLUSDT", start + timedelta(hours=1), 0.0)  # rejected
        est.update("SOLUSDT", start + timedelta(hours=2), float("nan"))  # rejected
        est.update("SOLUSDT", start + timedelta(hours=3), 105.0)
        assert est.sample_count("SOLUSDT") == 1  # only 100->105 produces a return

    def test_drops_out_of_order(self):
        est = RealizedVolEstimator(VolEstimatorConfig(min_samples=2))
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        est.update("SOLUSDT", t0, 100.0)
        est.update("SOLUSDT", t0 + timedelta(hours=1), 105.0)
        est.update("SOLUSDT", t0, 102.0)  # out of order — ignored
        assert est.sample_count("SOLUSDT") == 1


class TestVolParitySize:
    def test_none_realized_vol_returns_baseline(self):
        size = vol_parity_size(Decimal("100"), None)
        assert size == Decimal("100")

    def test_zero_realized_vol_returns_baseline(self):
        size = vol_parity_size(Decimal("100"), 0.0)
        assert size == Decimal("100")

    def test_negative_realized_vol_returns_baseline(self):
        size = vol_parity_size(Decimal("100"), -0.1)
        assert size == Decimal("100")

    def test_realized_above_target_shrinks_position(self):
        cfg = VolParitySizingConfig(target_vol_annualised=0.30)
        # Realised vol 0.60 is double the target -> size halves
        size = vol_parity_size(Decimal("100"), 0.60, cfg)
        assert size == pytest.approx(Decimal("50"), rel=Decimal("0.001"))

    def test_realized_below_target_grows_position(self):
        cfg = VolParitySizingConfig(target_vol_annualised=0.30, cap_multiplier=3.0)
        # Realised vol 0.15 is half the target -> size doubles
        size = vol_parity_size(Decimal("100"), 0.15, cfg)
        assert size == pytest.approx(Decimal("200"), rel=Decimal("0.001"))

    def test_low_realized_vol_capped_by_cap_multiplier(self):
        cfg = VolParitySizingConfig(
            target_vol_annualised=0.30, cap_multiplier=3.0, vol_floor_annualised=0.05
        )
        # Realised vol effectively 0.001 -> raw multiplier 300x; cap to 3x
        size = vol_parity_size(Decimal("100"), 0.001, cfg)
        # Floor enforces vol_floor=0.05 -> raw multiplier 6 -> capped to 3
        assert size == pytest.approx(Decimal("300"), rel=Decimal("0.001"))

    def test_high_realized_vol_floored_by_floor_multiplier(self):
        cfg = VolParitySizingConfig(
            target_vol_annualised=0.30,
            cap_multiplier=3.0,
            floor_multiplier=0.1,
        )
        # Realised vol 30 -> raw multiplier 0.01 -> floored to 0.1
        size = vol_parity_size(Decimal("100"), 30.0, cfg)
        assert size == pytest.approx(Decimal("10"), rel=Decimal("0.001"))

    def test_nan_realized_vol_returns_baseline(self):
        size = vol_parity_size(Decimal("100"), float("nan"))
        assert size == Decimal("100")
