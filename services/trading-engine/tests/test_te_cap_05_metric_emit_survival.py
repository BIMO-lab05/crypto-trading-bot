"""TE-CAP-05 / WR-03: regression guarantee for the Category-M typed-except
sites at auto_trader.py:1594 (min_qty branch) and :1611 (min_notional branch).

Phase 17 / TE-CAP-05 originally caught `(OSError, ImportError)` around the
deferred Prometheus increment. WR-03 in the Phase 17 code review observed that
the regression test added under D-10 covered only the cap-check breach path and
gave ZERO coverage for the four other typed-except rewrites in the plan — so a
silent narrowing or re-broadening of the metric-emit clauses would slip
through.

This test exercises the Category-M sites directly with a forced
`ValueError` from `Counter.labels(...).inc()` (the realistic prometheus
label-name-mismatch refactor failure) and asserts:

  1. The function still returns `(False, "min_qty")` / `(False, "min_notional")`
     — i.e. the metric-emit failure does NOT skip the rejection-decision path
     (safety rail integrity).
  2. The inline `logger.warning("metrics emit failed ...")` log line fires
     — i.e. the failure is OBSERVABLE per D-08 Category-M intent.

HONEST FRAMING: like `test_te_cap_05_log_survival.py`, this is a forward-going
regression guarantee. On current code (post-WR-02 commit) the typed tuple is
`(ImportError, ValueError, AttributeError)`, so injecting `ValueError` passes
through the clause and the test PASSES. The "RED" failure mode it protects
against is a future refactor that narrows the tuple back to e.g. `(ImportError,)`
— at which point the `ValueError` would propagate uncaught past
`_passes_min_notional` and skip the rejection log + return, allowing the trade
through the gate. That regression is precisely what this test catches.

Per CLAUDE.md memory feedback_main_imports_autoflake.md: `# noqa: F401`
markers on `app.main` and `app.core.metrics` are load-bearing — autoflake
strips bare imports otherwise, triggering `Duplicated timeseries in
CollectorRegistry` against the default registry on re-import inside the
test.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from unittest.mock import MagicMock

import pytest

# Pre-import app.main + app.core.metrics so the deferred imports inside
# _passes_min_notional find the modules already in sys.modules. Importing
# them lazily during a test re-runs prometheus_client.Counter()
# registrations and trips `Duplicated timeseries in CollectorRegistry`.
import app.main  # noqa: F401
import app.core.metrics  # noqa: F401

from app.auto_trader import AutoTrader
from app.services.instruments_cache import InstrumentSpec


# ---------------------------------------------------------------- helpers


def _spec(min_qty="0.001", min_notional: Optional[str] = "5") -> InstrumentSpec:
    return InstrumentSpec(
        symbol="BTCUSDT",
        min_order_qty=Decimal(min_qty),
        qty_step=Decimal("0.001"),
        tick_size=Decimal("0.10"),
        min_notional=Decimal(min_notional) if min_notional is not None else None,
        fetched_at=datetime.now(timezone.utc),
    )


class _StubInstrumentsCache:
    def __init__(self, spec: Optional[InstrumentSpec]):
        self._spec = spec

    async def get(self, symbol: str):
        return self._spec


@pytest.fixture(autouse=True)
def _force_live_mode(monkeypatch):
    """Pin LIVE so these tests isolate the Category-M metric-emit branch.

    The gate runs in every mode (since 2026-08-04); LIVE only changes what a
    MISSING spec does (fails open — review I12). These tests always supply a
    spec, so the mode is pinned purely to keep the branch under test stable.
    """
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "trading_mode", "LIVE", raising=False)


@pytest.fixture
def trader():
    """Fresh AutoTrader for each test (no _trading_loop running)."""
    return AutoTrader(symbols=["BTCUSDT"])


def _install_raising_counter(monkeypatch, exc: BaseException) -> MagicMock:
    """Replace `app.core.metrics.trades_rejected_min_notional_total` with a
    MagicMock whose `.labels(...).inc()` raises `exc`. Returns the top-level
    mock so callers can inspect call args.

    The deferred import inside _passes_min_notional binds `trades_rejected_min_notional_total`
    to whatever lives at `app.core.metrics.trades_rejected_min_notional_total`
    at call time — so monkeypatching the attribute on the module is sufficient
    (no need to patch the import target inside auto_trader).
    """
    fake_counter = MagicMock()
    labels_holder = MagicMock()
    labels_holder.inc = MagicMock(side_effect=exc)
    fake_counter.labels = MagicMock(return_value=labels_holder)
    monkeypatch.setattr(
        "app.core.metrics.trades_rejected_min_notional_total",
        fake_counter,
    )
    return fake_counter


# ============================================================================
# WR-03 regression tests for Category-M sites
# ============================================================================


@pytest.mark.asyncio
async def test_min_qty_reject_survives_value_error_from_counter_inc(
    trader, monkeypatch, caplog
):
    """Force min_qty rejection AND make Counter.labels().inc() raise
    ValueError (label-name mismatch). Assert:
      - function still returns (False, "min_qty")
      - "metrics emit failed (min_qty)" warning is captured
      - no uncaught exception escapes
    """
    cache = _StubInstrumentsCache(spec=_spec(min_qty="0.001", min_notional=None))
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: cache)

    fake_counter = _install_raising_counter(
        monkeypatch, ValueError("Incorrect label names")
    )

    with caplog.at_level(logging.WARNING, logger="app.auto_trader"):
        ok, reason = await trader._passes_min_notional(
            symbol="BTCUSDT",
            quantity=Decimal("0.0000166"),  # < 0.001 → min_qty reject
            price=Decimal("60000"),
            balance=Decimal("100"),
        )

    # Safety rail: rejection decision must NOT be skipped by the metric-emit
    # failure. This is the safety-critical assertion.
    assert ok is False, "metric-emit ValueError must not allow trade through gate"
    assert reason == "min_qty"

    # The fake counter was actually invoked (proves we reached the metric site
    # and didn't bypass it via a typo or short-circuit upstream).
    fake_counter.labels.assert_called_once_with(symbol="BTCUSDT", reason="min_qty")

    # Observability: D-08 Category-M intent — the failure must be logged.
    assert any(
        "metrics emit failed (min_qty)" in rec.message for rec in caplog.records
    ), (
        f"Category-M observable failure log NOT emitted; "
        f"got {[(r.levelname, r.name, r.message[:100]) for r in caplog.records]!r}. "
        f"If this fails, the typed except at auto_trader.py:1594 has been narrowed "
        f"back to a tuple that does not include ValueError — re-add it or the "
        f"min-notional gate skips rejection on a Prometheus refactor."
    )


@pytest.mark.asyncio
async def test_min_notional_reject_survives_value_error_from_counter_inc(
    trader, monkeypatch, caplog
):
    """Force min_notional rejection (qty passes, notional fails) AND make
    Counter.labels().inc() raise ValueError. Assert the same invariants as the
    min_qty test for the second Category-M site at :1611.
    """
    # min_qty satisfied (0.001 ≥ 0.001); min_notional NOT satisfied ($3 < $5).
    cache = _StubInstrumentsCache(spec=_spec(min_qty="0.001", min_notional="5"))
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: cache)

    fake_counter = _install_raising_counter(
        monkeypatch, ValueError("Incorrect label names")
    )

    with caplog.at_level(logging.WARNING, logger="app.auto_trader"):
        ok, reason = await trader._passes_min_notional(
            symbol="BTCUSDT",
            quantity=Decimal("0.001"),
            price=Decimal("3000"),  # notional = $3 < $5
            balance=Decimal("100"),
        )

    # Safety rail: rejection decision must NOT be skipped.
    assert ok is False, "metric-emit ValueError must not allow trade through gate"
    assert reason == "min_notional"

    fake_counter.labels.assert_called_once_with(symbol="BTCUSDT", reason="min_notional")

    assert any(
        "metrics emit failed (min_notional)" in rec.message for rec in caplog.records
    ), (
        f"Category-M observable failure log NOT emitted; "
        f"got {[(r.levelname, r.name, r.message[:100]) for r in caplog.records]!r}. "
        f"If this fails, the typed except at auto_trader.py:1611 has been narrowed "
        f"back to a tuple that does not include ValueError — re-add it or the "
        f"min-notional gate skips rejection on a Prometheus refactor."
    )
