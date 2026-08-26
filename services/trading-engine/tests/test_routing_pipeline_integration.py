"""End-to-end: synthetic trending and ranging series through the live
ensemble path must produce routing decisions on BOTH branches.

Written 2026-08-21. Harness mirrors tests/test_ensemble_gates.py.

What makes this an integration test rather than a unit test: it drives
`AutoTrader._check_and_trade_ensemble` — the method the deployed 30-second
loop actually calls — with an aggregator signal carrying a real ADX leg
computed from a synthetic OHLC series. If the advisory routing call is ever
removed from that method, or the strategy-mode dispatch stops reaching it,
these assertions fail. That is precisely the regression that went unnoticed
from 2026-01-06 to 2026-08-21.

The Wilder ADX recursion below mirrors
`services/technical-analysis/app/indicators/adx.py`; its agreement with the
`ta` package is pinned separately in
`services/technical-analysis/tests/test_adx_reference_parity.py`.
"""

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

# Host-run test: money rules require the account size to come from
# shared/account.py, never a literal.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402

# Pre-import so the deferred imports inside _passes_min_notional /
# _snap_quantity_to_step find the modules already in sys.modules — importing
# lazily during a test re-runs prometheus Counter registration.
import app.main  # noqa: F401,E402
import app.core.metrics  # noqa: F401,E402
from app.models import OrderStatus, SignalAction  # noqa: E402
from app.monitoring.signal_funnel import get_signal_funnel  # noqa: E402

from app.services.instruments_cache import InstrumentSpec  # noqa: E402

BALANCE = Decimal(str(ACCOUNT_EQUITY_USD))
SOL_PRICE = 71.0

SOL_SPEC = InstrumentSpec(
    symbol="SOLUSDT",
    min_order_qty=Decimal("0.1"),
    qty_step=Decimal("0.1"),
    tick_size=Decimal("0.010"),
    min_notional=Decimal("5"),
    fetched_at=datetime.now(timezone.utc),
)


# --------------------------------------------------------------------------
# Synthetic series + Wilder ADX (no third-party dependency at test time)
# --------------------------------------------------------------------------


def _lcg(seed: int):
    state = seed

    def rand() -> float:
        nonlocal state
        state = (1103515245 * state + 12345) % (2**31)
        return state / (2**31)

    return rand


def make_series(n: int, mode: str, seed: int):
    rand = _lcg(seed)
    highs, lows, closes = [], [], []
    price = 100.0
    for _ in range(n):
        if mode == "trend":
            price += 0.35 + (rand() - 0.5) * 1.2
        else:
            price += (100.0 - price) * 0.35 + (rand() - 0.5) * 2.0
        rng = 0.6 + rand() * 0.8
        highs.append(round(price + rng / 2, 4))
        lows.append(round(price - rng / 2, 4))
        closes.append(round(price, 4))
    return highs, lows, closes


def wilder_adx(highs, lows, closes, period: int = 14) -> float:
    """Wilder's ADX, seeded the way `ewm(alpha=1/period, adjust=False)` seeds."""
    alpha = 1.0 / period
    s_tr = s_pdm = s_mdm = None
    adx = None
    for i in range(len(closes)):
        if i == 0:
            tr, pdm, mdm = highs[0] - lows[0], 0.0, 0.0
        else:
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            up = highs[i] - highs[i - 1]
            down = lows[i - 1] - lows[i]
            pdm = up if (up > 0 and up > down) else 0.0
            mdm = down if (down > 0 and down > up) else 0.0
        s_tr = tr if s_tr is None else s_tr + alpha * (tr - s_tr)
        s_pdm = pdm if s_pdm is None else s_pdm + alpha * (pdm - s_pdm)
        s_mdm = mdm if s_mdm is None else s_mdm + alpha * (mdm - s_mdm)
        pdi = 100 * s_pdm / s_tr if s_tr else 0.0
        mdi = 100 * s_mdm / s_tr if s_tr else 0.0
        dx = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0.0
        adx = dx if adx is None else adx + alpha * (dx - adx)
    return float(adx)


# --------------------------------------------------------------------------
# Harness
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_funnel():
    get_signal_funnel().reset()
    yield
    get_signal_funnel().reset()


@pytest.fixture
def live_trader(monkeypatch):
    from app.auto_trader import AutoTrader
    from app.trading_enhancements.portfolio_heat import reset_portfolio_heat_manager

    reset_portfolio_heat_manager()
    t = AutoTrader(symbols=["SOLUSDT"])
    monkeypatch.setattr(t.settings, "trading_mode", "PAPER", raising=False)
    monkeypatch.setattr(t.settings, "leverage_enabled", False, raising=False)
    monkeypatch.setattr(t.settings, "max_position_size_pct", 10.0, raising=False)
    monkeypatch.setattr(t.settings, "max_total_exposure_pct", 80.0, raising=False)
    monkeypatch.setattr(t.settings, "strategy_routing_mode", "advisory", raising=False)
    t.notification_client = MagicMock()
    t.notification_client.notify_trade_open = AsyncMock()
    t.notification_client.notify_trade_close = AsyncMock()
    return t


class _StubInstrumentsCache:
    def __init__(self, specs):
        self._specs = specs

    async def get(self, symbol):
        return self._specs.get(symbol)


def _wire(monkeypatch, *, adx_value, confidence=0.55, action=SignalAction.BUY):
    """Stub every external dependency, injecting a real ADX leg."""
    cache = _StubInstrumentsCache({"SOLUSDT": SOL_SPEC})
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: cache)

    risk_mgr = MagicMock()
    risk_mgr.should_halt_trading = MagicMock(return_value=False)
    monkeypatch.setattr("app.auto_trader.get_risk_manager", lambda: risk_mgr)

    price_leg = MagicMock()
    price_leg.metadata = {"current_price": SOL_PRICE}
    # The ADX leg is the whole point — a plain namespace so `getattr(sig,
    # "value")` returns the number rather than a MagicMock.
    adx_leg = SimpleNamespace(value=adx_value, confidence=0.8, metadata={"adx": adx_value})
    base_signal = MagicMock()
    base_signal.indicators = {"RSI": price_leg, "ADX": adx_leg}

    aggregator = MagicMock()
    aggregator.get_trading_signal_multi_timeframe = AsyncMock(return_value=base_signal)

    async def _fake_get_aggregator():
        return aggregator

    monkeypatch.setattr("app.auto_trader.get_aggregator", _fake_get_aggregator)

    paper_engine = MagicMock()
    paper_engine.get_balance = MagicMock(return_value=BALANCE)
    filled = MagicMock()
    filled.status = OrderStatus.FILLED
    filled.position_id = uuid4()
    paper_engine.execute_market_order = AsyncMock(return_value=(filled, None))
    monkeypatch.setattr("app.auto_trader.get_paper_engine", lambda: paper_engine)

    position_mgr = MagicMock()
    position_mgr.get_open_positions = MagicMock(return_value=[])
    monkeypatch.setattr("app.auto_trader.get_position_manager", lambda: position_mgr)

    ens_signal = MagicMock()
    ens_signal.action = action
    ens_signal.confidence = confidence
    ens_signal.position_size_pct = 0.10
    if action == SignalAction.SELL:
        ens_signal.stop_loss = SOL_PRICE * 1.02
        ens_signal.take_profit = SOL_PRICE * 0.96
    else:
        ens_signal.stop_loss = SOL_PRICE * 0.98
        ens_signal.take_profit = SOL_PRICE * 1.04
    ens_signal.leg_actions = {"simple_rsi": action.value}
    ens_signal.leg_contributions = {}

    ensemble = MagicMock()
    ensemble.generate_signal = MagicMock(return_value=ens_signal)
    import app.strategies.multi_strategy_ensemble as ens_mod

    monkeypatch.setattr(ens_mod, "get_ensemble", lambda: ensemble)
    return paper_engine


# --------------------------------------------------------------------------
# The series themselves must straddle the threshold, or the test is vacuous
# --------------------------------------------------------------------------

TREND_ADX = wilder_adx(*make_series(400, "trend", 12345))
RANGE_ADX = wilder_adx(*make_series(400, "range", 777))


def test_synthetic_series_are_on_opposite_sides_of_the_threshold():
    assert TREND_ADX >= 25.0, f"trending series only reached ADX {TREND_ADX:.2f}"
    assert RANGE_ADX < 25.0, f"ranging series reached ADX {RANGE_ADX:.2f}"


# --------------------------------------------------------------------------
# Full-path integration
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trending_series_routes_to_trend_following(live_trader, monkeypatch):
    _wire(monkeypatch, adx_value=TREND_ADX)

    await live_trader._check_and_trade_ensemble("SOLUSDT")

    stats = live_trader.hybrid_strategy.get_stats()
    assert stats["total_signals"] == 1, "no routing decision was made"
    assert stats["trend_signals"] == 1
    assert stats["mean_reversion_signals"] == 0
    assert stats["routing_mode"] == "advisory"

    routing = get_signal_funnel().snapshot()["routing"]
    assert routing["trend_following"] == 1
    assert routing["adx_distribution"]["max"] == pytest.approx(TREND_ADX)


@pytest.mark.asyncio
async def test_ranging_series_routes_to_mean_reversion(live_trader, monkeypatch):
    _wire(monkeypatch, adx_value=RANGE_ADX)

    await live_trader._check_and_trade_ensemble("SOLUSDT")

    stats = live_trader.hybrid_strategy.get_stats()
    assert stats["total_signals"] == 1
    assert stats["mean_reversion_signals"] == 1
    assert stats["trend_signals"] == 0

    routing = get_signal_funnel().snapshot()["routing"]
    assert routing["mean_reversion"] == 1


@pytest.mark.asyncio
async def test_both_branches_accumulate_across_cycles(live_trader, monkeypatch):
    """Percentages must be computed from a real denominator and sum to 100."""
    for adx in (TREND_ADX, RANGE_ADX, TREND_ADX, RANGE_ADX):
        _wire(monkeypatch, adx_value=adx)
        await live_trader._check_and_trade_ensemble("SOLUSDT")

    stats = live_trader.hybrid_strategy.get_stats()
    assert stats["total_signals"] == 4
    assert stats["trend_signals"] == 2
    assert stats["mean_reversion_signals"] == 2
    assert stats["trend_pct"] == pytest.approx(50.0)
    assert stats["mean_reversion_pct"] == pytest.approx(50.0)
    assert stats["trend_pct"] + stats["mean_reversion_pct"] == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_status_payload_carries_routing_stats_in_ensemble_mode(live_trader, monkeypatch):
    """The regression that caused the zeros: `hybrid_strategy_stats` used to be
    omitted from the payload entirely unless strategy_mode was RESEARCH/HYBRID.
    """
    from app.auto_trader import StrategyMode

    live_trader.strategy_mode = StrategyMode.ENSEMBLE
    _wire(monkeypatch, adx_value=TREND_ADX)
    await live_trader._check_and_trade_ensemble("SOLUSDT")

    status = live_trader.get_status()
    assert "hybrid_strategy_stats" in status, (
        "routing stats missing from the status payload in ensemble mode — "
        "the frontend renders this absence as '0 signals routed'"
    )
    assert status["hybrid_strategy_stats"]["total_signals"] == 1
    assert status["hybrid_strategy_stats"]["routing_mode"] == "advisory"
    assert "signal_funnel" in status
    stage_names = {s["stage"] for s in status["signal_funnel"]["stages"]}
    assert "routing_decision_made" in stage_names
    assert "order_intent_emitted" in stage_names


@pytest.mark.asyncio
async def test_funnel_records_the_full_cascade_on_a_successful_entry(live_trader, monkeypatch):
    paper_engine = _wire(monkeypatch, adx_value=TREND_ADX, confidence=0.55)

    await live_trader._check_and_trade_ensemble("SOLUSDT")

    paper_engine.execute_market_order.assert_awaited()
    stages = {s["stage"]: s for s in get_signal_funnel().snapshot()["stages"]}
    assert stages["evaluations"]["evaluated"] == 1
    assert stages["raw_signals_generated"]["passed"] == 1
    assert stages["routing_decision_made"]["passed"] == 1
    assert stages["ensemble_signal_emitted"]["passed"] == 1
    assert stages["passed_signal_confidence_gate"]["passed"] == 1
    assert stages["order_intent_emitted"]["passed"] == 1


@pytest.mark.asyncio
async def test_rejection_is_attributed_to_the_stage_that_caused_it(live_trader, monkeypatch):
    """0.1730 is the lowest confidence observed on a real ensemble entry leg."""
    paper_engine = _wire(monkeypatch, adx_value=TREND_ADX, confidence=0.1730)

    await live_trader._check_and_trade_ensemble("SOLUSDT")

    paper_engine.execute_market_order.assert_not_awaited()
    stages = {s["stage"]: s for s in get_signal_funnel().snapshot()["stages"]}
    gate = stages["passed_signal_confidence_gate"]
    assert gate["rejected"] == 1
    reason = gate["rejection_reasons"]["confidence_below_min_signal_confidence"]
    assert reason["observed_min"] == pytest.approx(0.1730)
    assert reason["threshold"] == pytest.approx(float(live_trader.settings.min_signal_confidence))
    assert stages["order_intent_emitted"]["evaluated"] == 0
    # A routing decision was still made — the router observes every evaluation,
    # not only the ones that become orders.
    assert stages["routing_decision_made"]["passed"] == 1
