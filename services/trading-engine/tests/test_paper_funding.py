"""
Paper closes must accrue perp funding, in BOTH ledgers.

The engine charges commission on both legs and slippage on every fill, but
never funding - grep -c funding app/paper_trading.py returned 0. Positions
live up to the 48h max-hold, i.e. up to six Bybit 8h settlements.

The trap: charging only self.balance is invisible. get_performance_summary
reads realized P&L off positions and the daily-loss breaker is fed by
update_daily_pnl(net_close_pnl) - neither sees the cash line. Funding must
also reach position_manager via the close_commission channel, exactly as
close_commission itself is dual-booked (cash at paper_trading.py:432,
reported P&L at position_manager.py:510).

Rates here are the measured means recorded in tests/test_costs_funding.py
(module docstring), not invented figures.
"""

import sys
from decimal import Decimal
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from datetime import datetime, timezone  # noqa: E402
from uuid import uuid4  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from app.costs import FundingSettlement, funding_cost  # noqa: E402
from app.models import OrderCreate, OrderSide, OrderType, PositionSide  # noqa: E402
from app.paper_trading import PaperTradingEngine  # noqa: E402

H8 = 8 * 60 * 60 * 1000
BTC_RATE = Decimal("0.0000278")  # BTC mean per 8h, measured 2026-08-07 over 200
#                                  settlements/symbol - tests/test_costs_funding.py:10-14

# Fixed instants (2023, well before "now") so that the real engine's
# exit_ts_ms (datetime.now() at call time) always lands after every
# settlement below, regardless of when this suite runs.
_ENTRY_MS = 1_700_000_000_000
_EXIT_MS = _ENTRY_MS + H8 * 3

_CLOSE_PRICE = Decimal("60000")
_CLOSE_QTY = Decimal("0.0001")


def _settlements(n: int, rate: Decimal = BTC_RATE, t0: int = 1_000):
    return [FundingSettlement(ts_ms=t0 + H8 * i, rate=rate) for i in range(n)]


class _IdentitySlippage:
    """Fills at the reference price - keeps the commission math predictable."""

    def fill_price(self, symbol, side, price):
        return price

    def describe(self):
        return "identity (test)"


def _closing_order() -> OrderCreate:
    """A SELL that fully closes the LONG position built by the fixture."""
    return OrderCreate(
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=_CLOSE_QTY,
    )


def _commission_only(engine: PaperTradingEngine) -> Decimal:
    """What the exit commission alone would be, with no funding admixed -
    the pre-fix behaviour this test must distinguish itself from."""
    return engine.calculate_commission(_CLOSE_PRICE * _CLOSE_QTY)


def _open_long_position(opened_at_ms: int):
    """A MagicMock position, not a real Position row - the fixture stubs
    position_manager entirely so the assertions can inspect its call args
    directly."""
    position = MagicMock()
    position.id = uuid4()
    position.symbol = "BTCUSDT"
    position.side = PositionSide.LONG
    position.entry_price = _CLOSE_PRICE
    position.quantity = _CLOSE_QTY
    position.remaining_quantity = _CLOSE_QTY
    position.realized_pnl = Decimal("0")
    position.opened_at = datetime.fromtimestamp(opened_at_ms / 1000, tz=timezone.utc)
    return position


@pytest.fixture
def paper_engine_with_funding():
    """A PaperTradingEngine with mocked repos/managers, one open LONG BTC
    position, and the funding-rate fetch stubbed to a known, sign-correct
    settlement series crossing 3 Bybit settlements.
    """
    trade_repo = MagicMock()
    trade_repo.log_trade = AsyncMock()

    portfolio_repo = MagicMock()
    portfolio_repo.update_balance = AsyncMock()
    portfolio_repo.get_or_create = AsyncMock()

    position = _open_long_position(_ENTRY_MS)

    position_manager = MagicMock()
    position_manager.get_open_positions = MagicMock(return_value=[position])
    position_manager.get_position = MagicMock(return_value=None)
    position_manager.consume_posted_margin = MagicMock(return_value=Decimal("0"))

    closed_position = MagicMock()
    closed_position.id = position.id
    closed_position.realized_pnl = Decimal("0")
    position_manager.close_position = MagicMock(return_value=closed_position)
    position_manager.reduce_position = MagicMock()
    position_manager.get_total_unrealized_pnl = MagicMock(return_value=Decimal("0"))

    risk_manager = MagicMock()

    settlements = _settlements(3, t0=_ENTRY_MS)

    with (
        patch("app.paper_trading.get_trade_repository", return_value=trade_repo),
        patch(
            "app.paper_trading.get_portfolio_repository", return_value=portfolio_repo
        ),
        patch("app.paper_trading.get_position_manager", return_value=position_manager),
        patch("app.paper_trading.get_risk_manager", return_value=risk_manager),
        patch(
            "app.risk.funding_gate.FundingRateClient.get_settlements",
            new=AsyncMock(return_value=settlements),
        ),
    ):
        engine = PaperTradingEngine()
        engine.slippage = _IdentitySlippage()
        yield engine, position_manager, settlements


@pytest.mark.asyncio
async def test_client_parses_settlements_as_decimal():
    """fundingRate arrives as a STRING; float() would corrupt money math."""
    from app.risk.funding_gate import FundingGateConfig, FundingRateClient

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(
        return_value={
            "success": True,
            "data": [
                {
                    "symbol": "BTCUSDT",
                    "fundingRate": "0.00010000",
                    "fundingRateTimestamp": "1672041600000",
                }
            ],
        }
    )
    http = MagicMock()
    http.get = AsyncMock(return_value=response)

    client = FundingRateClient(
        connector_base_url="http://connector",
        config=FundingGateConfig(),
        client=http,
    )
    settlements = await client.get_settlements("BTCUSDT", 0, 1_700_000_000_000)

    assert len(settlements) == 1
    assert settlements[0].rate == Decimal("0.00010000")
    assert isinstance(settlements[0].rate, Decimal)
    assert settlements[0].ts_ms == 1672041600000


@pytest.mark.asyncio
async def test_client_fails_open_to_empty_list():
    """Tape-replay mode stubs this feed to empty; an outage must not raise."""
    from app.risk.funding_gate import FundingGateConfig, FundingRateClient

    http = MagicMock()
    http.get = AsyncMock(side_effect=RuntimeError("connector down"))

    client = FundingRateClient(
        connector_base_url="http://connector",
        config=FundingGateConfig(),
        client=http,
    )

    assert await client.get_settlements("BTCUSDT", 0, 1) == []


def test_long_pays_and_short_is_paid():
    """Sign correctness on both axes - reimplementing this inverts it."""
    settlements = _settlements(3)
    long_cost = funding_cost(
        Decimal("100"), "LONG", settlements, entry_ts_ms=0, exit_ts_ms=1_000 + H8 * 3
    )
    short_cost = funding_cost(
        Decimal("100"), "SHORT", settlements, entry_ts_ms=0, exit_ts_ms=1_000 + H8 * 3
    )

    assert long_cost == Decimal("100") * BTC_RATE * 3
    assert long_cost > 0  # positive means PAID
    assert short_cost == -long_cost


@pytest.mark.asyncio
async def test_close_charges_funding_to_both_ledgers(paper_engine_with_funding):
    """The load-bearing assertion: cash AND reported P&L both move."""
    engine, position_manager, settlements = paper_engine_with_funding

    cash_before = engine.balance
    await engine.execute_market_order(_closing_order(), _CLOSE_PRICE)

    expected = funding_cost(
        Decimal("60000") * Decimal("0.0001"),
        "LONG",
        settlements,
        entry_ts_ms=_ENTRY_MS,
        exit_ts_ms=_EXIT_MS,
    )
    assert expected > 0, "fixture must cross at least one settlement"

    # Ledger 1: cash
    assert engine.balance < cash_before, "funding never reached the cash ledger"

    # Tighter than the inequality above: commission alone would already make
    # that inequality true, which would mask a cash-ledger funding bug. The
    # cash delta (margin_returned=0, realized_pnl=0 by construction) must
    # exceed commission alone by exactly the funding leg.
    cash_delta = cash_before - engine.balance
    assert cash_delta > _commission_only(engine), (
        "cash delta equals commission alone - funding never reached the cash ledger"
    )
    assert cash_delta == _commission_only(engine) + expected

    # Ledger 2: reported P&L, via the close_commission channel
    close_kwargs = position_manager.close_position.call_args.kwargs
    assert close_kwargs["close_commission"] > _commission_only(engine), (
        "funding did not reach position_manager, so reported P&L and the "
        "daily-loss breaker never see it - the 'wired but never bites' trap"
    )
    assert close_kwargs["close_commission"] == _commission_only(engine) + expected


@pytest.mark.asyncio
async def test_short_is_paid_funding_in_a_positive_regime(paper_engine_with_funding):
    """funding_paid may be NEGATIVE - a SHORT is PAID when the rate is
    positive, and Decimal arithmetic must carry that sign into both ledgers
    rather than clamping or dropping it."""
    engine, position_manager, settlements = paper_engine_with_funding

    # Flip the fixture's LONG to a SHORT held over the same settlements.
    position = position_manager.get_open_positions()[0]
    position.side = PositionSide.SHORT

    cash_before = engine.balance
    closing_order = OrderCreate(
        symbol="BTCUSDT",
        side=OrderSide.BUY,  # BUY closes a SHORT
        type=OrderType.MARKET,
        quantity=_CLOSE_QTY,
    )
    await engine.execute_market_order(closing_order, _CLOSE_PRICE)

    expected_short = funding_cost(
        Decimal("60000") * Decimal("0.0001"),
        "SHORT",
        settlements,
        entry_ts_ms=_ENTRY_MS,
        exit_ts_ms=_EXIT_MS,
    )
    assert expected_short < 0, "fixture must be a net credit for the short leg"

    # Cash: commission is still owed, but funding is a CREDIT, so the net
    # cash outflow is SMALLER than commission alone (never the other sign
    # error of double-charging as if funding were also a cost).
    cash_delta = cash_before - engine.balance
    assert cash_delta == _commission_only(engine) + expected_short
    assert cash_delta < _commission_only(engine)

    close_kwargs = position_manager.close_position.call_args.kwargs
    assert close_kwargs["close_commission"] == _commission_only(engine) + expected_short
    assert close_kwargs["close_commission"] < _commission_only(engine)
