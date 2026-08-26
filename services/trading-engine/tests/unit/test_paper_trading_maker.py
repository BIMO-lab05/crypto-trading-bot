"""
Paper-mode maker execution simulation (quick-260826-o2h / MAKER-SIM-01).

Pins the SIMULATED PostOnly maker path on PaperTradingEngine:

- a maker fill executes AT the limit price, pays the MAKER fee
  (paper_maker_commission_pct, 0.02 %/side) and gets NO taker slippage;
- a simulated timeout honours maker_fallback_to_taker: enabled -> taker
  fill (slippage + taker fee) stamped execution_path="taker_fallback",
  disabled -> (None, error) with no balance/position mutation;
- EVERY trade row carries execution metadata (maker_attempted,
  execution_path, fallback_reason, fee_rate_applied) -- including plain
  taker fills, stamped "taker_direct", so a harvest can split maker vs
  taker share from trades.metadata alone;
- money stays Decimal end to end (money.md).

FRESH file: tests/unit/test_live_trading_maker.py is skip-marked stale
(PR #86); only its helper PATTERNS are reused here, never its code.
Engine construction mirrors tests/unit/test_paper_trading.py.
"""

import asyncio

import pytest

from decimal import Decimal
from uuid import uuid4
from unittest.mock import Mock, AsyncMock, patch

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "shared"))

from app.config import get_settings
from app.paper_trading import PaperTradingEngine
from app.models import (
    OrderCreate,
    OrderStatus,
    OrderSide,
    OrderType,
    PositionSide,
)

#: Declared paper equity, routed through Settings (ADR-029) — never a bare
#: account-size literal. Dollar expectations below DERIVE from this so the
#: suite re-scales with the declared account automatically.
_BALANCE = Decimal(str(get_settings().paper_initial_balance))

#: Fee rates as FRACTIONS (Settings carries percent-per-side; engine /100s).
_MAKER_RATE = Decimal("0.02") / Decimal("100")  # 0.02 %/side
_TAKER_RATE = Decimal("0.055") / Decimal("100")  # 0.055 %/side

#: Expected limit prices from paper_slippage defaults (BTCUSDT 5 bps, tick
#: 0.1). BUY maker limit = bid estimate = 60000*(1-0.0005) floor-quantized;
#: SELL maker limit = ask estimate = 60000*(1+0.0005) ceil-quantized.
_REF = Decimal("60000")
_BUY_LIMIT = Decimal("59970.0")
_SELL_LIMIT = Decimal("60030.0")


def _order(side=OrderSide.BUY, qty="0.001", symbol="BTCUSDT"):
    """Order factory (pattern from test_live_trading_maker, rebuilt fresh)."""
    return OrderCreate(
        symbol=symbol,
        side=side,
        quantity=Decimal(qty),
        type=OrderType.MARKET,
        strategy="maker_sim_test",
    )


def _no_wall_clock():
    """Patch the module's asyncio.sleep so no test consumes wall time.

    Scoped as a context manager: exit BEFORE draining spawned tasks so the
    test's own asyncio.sleep(0) is the real one.
    """
    return patch("app.paper_trading.asyncio.sleep", new_callable=AsyncMock)


async def _drain_spawned_tasks():
    """Let _spawn_trade_log's create_task run before asserting on log_trade."""
    await asyncio.sleep(0)
    await asyncio.sleep(0)


class TestPaperMakerSimulation:
    """Maker fill / fallback / disabled / stamping / Decimal contract."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings pinned for the maker-simulation arithmetic."""
        settings = Mock()
        settings.paper_initial_balance = float(_BALANCE)
        settings.paper_commission_pct = 0.055  # Bybit linear-perp taker %/side
        settings.paper_maker_commission_pct = 0.02  # maker %/side
        settings.maker_quote_timeout_seconds = 1  # small; sleep is mocked
        settings.maker_fallback_to_taker = True
        # Slippage ON: the limit-price estimator reuses the slippage model,
        # so the expected _BUY_LIMIT/_SELL_LIMIT math needs it enabled.
        settings.paper_slippage_enabled = True
        settings.paper_slippage_bps_by_symbol = {}
        settings.paper_slippage_default_bps = 10.0
        # Pin 1x leverage so margin == notional (idiom from
        # tests/unit/test_paper_trading.py — a bare Mock here raises
        # decimal.InvalidOperation inside execute_market_order).
        settings.leverage_enabled = True
        settings.default_leverage = 1.0
        settings.min_leverage = 1.0
        settings.max_leverage = 20.0
        # Funding OFF: close-path funding fetch would crash on Mock datetimes.
        settings.paper_funding_enabled = False
        settings.bybit_connector_url = "http://bybit-connector:8001"
        return settings

    @pytest.fixture
    def mock_position_manager(self):
        manager = Mock()
        manager.get_total_unrealized_pnl.return_value = Decimal("0")
        manager.get_open_positions.return_value = []
        manager.get_closed_positions.return_value = []
        return manager

    @pytest.fixture
    def mock_risk_manager(self):
        manager = Mock()
        manager.check_position_limits.return_value = (True, None)
        return manager

    @pytest.fixture
    def mock_trade_repo(self):
        repo = Mock()
        repo.log_trade = AsyncMock()
        return repo

    @pytest.fixture
    def mock_portfolio_repo(self):
        return Mock()

    @pytest.fixture
    def trading_engine(
        self,
        mock_settings,
        mock_position_manager,
        mock_risk_manager,
        mock_trade_repo,
        mock_portfolio_repo,
    ):
        """PaperTradingEngine with mocked dependencies (existing idiom)."""
        with (
            patch("app.paper_trading.get_settings", return_value=mock_settings),
            patch(
                "app.paper_trading.get_position_manager",
                return_value=mock_position_manager,
            ),
            patch(
                "app.paper_trading.get_risk_manager",
                return_value=mock_risk_manager,
            ),
            patch(
                "app.paper_trading.get_trade_repository",
                return_value=mock_trade_repo,
            ),
            patch(
                "app.paper_trading.get_portfolio_repository",
                return_value=mock_portfolio_repo,
            ),
        ):
            engine = PaperTradingEngine()
            return engine

    # ------------------------------------------------------------- maker fill

    @pytest.mark.asyncio
    async def test_maker_fill_at_limit_with_maker_fee(self, trading_engine, mock_position_manager):
        """BUY maker fill executes AT the limit, charged the MAKER rate,
        with NO taker slippage applied on top of the limit."""
        mock_position = Mock()
        mock_position.id = uuid4()
        mock_position_manager.create_position.return_value = mock_position

        # Refetched price BELOW the buy limit -> first-touch fill.
        trading_engine._fetch_last_price = AsyncMock(return_value=Decimal("59960"))

        with _no_wall_clock():
            executed, error = await trading_engine.execute_maker_order_with_fallback(
                _order(OrderSide.BUY), _REF
            )
        await _drain_spawned_tasks()

        assert error is None
        assert executed.status == OrderStatus.FILLED
        # Fill AT the limit exactly — slippage NOT applied on top.
        assert executed.filled_price == _BUY_LIMIT
        assert executed.filled_quantity == Decimal("0.001")

        # Maker fee on the limit-price notional, not the taker fee.
        expected_commission = _BUY_LIMIT * Decimal("0.001") * _MAKER_RATE
        kwargs = mock_position_manager.create_position.call_args.kwargs
        assert kwargs["entry_price"] == _BUY_LIMIT
        assert kwargs["entry_fee"] == expected_commission

        # Balance debit reflects MAKER commission (1x: margin == notional).
        expected_balance = _BALANCE - _BUY_LIMIT * Decimal("0.001") - expected_commission
        assert trading_engine.balance == expected_balance

    @pytest.mark.asyncio
    async def test_sell_side_maker_fill(self, trading_engine, mock_position_manager):
        """SELL maker limit is the ask estimate ABOVE reference; a refetched
        price at/above the limit fills AT the limit and opens a SHORT."""
        mock_position = Mock()
        mock_position.id = uuid4()
        mock_position_manager.create_position.return_value = mock_position

        trading_engine._fetch_last_price = AsyncMock(return_value=Decimal("60040"))

        with _no_wall_clock():
            executed, error = await trading_engine.execute_maker_order_with_fallback(
                _order(OrderSide.SELL), _REF
            )
        await _drain_spawned_tasks()

        assert error is None
        assert executed.status == OrderStatus.FILLED
        assert executed.filled_price == _SELL_LIMIT
        kwargs = mock_position_manager.create_position.call_args.kwargs
        assert kwargs["side"] == PositionSide.SHORT
        assert kwargs["entry_price"] == _SELL_LIMIT

    # -------------------------------------------------------------- fallback

    @pytest.mark.asyncio
    async def test_timeout_falls_back_to_taker_with_metadata(
        self, trading_engine, mock_position_manager, mock_trade_repo
    ):
        """Non-crossing refetch -> taker fallback: slippage + taker fee, and
        the trade row records the attempt (taker_fallback / timeout)."""
        mock_position = Mock()
        mock_position.id = uuid4()
        mock_position_manager.create_position.return_value = mock_position

        # Refetched ABOVE the buy limit (59970.0) -> no maker fill.
        trading_engine._fetch_last_price = AsyncMock(return_value=Decimal("59980"))

        with _no_wall_clock():
            executed, error = await trading_engine.execute_maker_order_with_fallback(
                _order(OrderSide.BUY), _REF
            )
        await _drain_spawned_tasks()

        assert error is None
        assert executed.status == OrderStatus.FILLED
        # Taker fill from the REFETCHED reference: 59980*(1+5bps) ceil to 0.1.
        assert executed.filled_price == Decimal("60010.0")

        # Taker fee, not maker: entry_fee = notional * 0.055%.
        kwargs = mock_position_manager.create_position.call_args.kwargs
        assert kwargs["entry_fee"] == Decimal("60010.0") * Decimal("0.001") * _TAKER_RATE

        meta = mock_trade_repo.log_trade.call_args.kwargs["execution_metadata"]
        assert meta["maker_attempted"] is True
        assert meta["execution_path"] == "taker_fallback"
        assert meta["fallback_reason"] == "timeout"
        assert meta["fee_rate_applied"] == 0.055

    @pytest.mark.asyncio
    async def test_fallback_disabled_rejects_with_reason(
        self, trading_engine, mock_position_manager, mock_trade_repo
    ):
        """Timeout with fallback disabled -> (None, error); balance and
        positions untouched, nothing logged."""
        trading_engine.settings.maker_fallback_to_taker = False
        trading_engine._fetch_last_price = AsyncMock(return_value=Decimal("59980"))

        with _no_wall_clock():
            executed, error = await trading_engine.execute_maker_order_with_fallback(
                _order(OrderSide.BUY), _REF
            )
        await _drain_spawned_tasks()

        assert executed is None
        assert error is not None
        assert "fallback disabled" in error
        assert trading_engine.balance == _BALANCE
        mock_position_manager.create_position.assert_not_called()
        mock_trade_repo.log_trade.assert_not_called()

    @pytest.mark.asyncio
    async def test_refetch_failure_treated_as_no_fill(
        self, trading_engine, mock_position_manager, mock_trade_repo
    ):
        """A failed price re-fetch (None) is NEVER a maker fill — it takes
        the fallback branch, referenced at the original current_price."""
        mock_position = Mock()
        mock_position.id = uuid4()
        mock_position_manager.create_position.return_value = mock_position

        trading_engine._fetch_last_price = AsyncMock(return_value=None)

        with _no_wall_clock():
            executed, error = await trading_engine.execute_maker_order_with_fallback(
                _order(OrderSide.BUY), _REF
            )
        await _drain_spawned_tasks()

        assert error is None
        assert executed.status == OrderStatus.FILLED
        # Taker fill from the ORIGINAL reference (refetch unavailable).
        assert executed.filled_price == Decimal("60030.0")
        meta = mock_trade_repo.log_trade.call_args.kwargs["execution_metadata"]
        assert meta["execution_path"] == "taker_fallback"
        assert meta["execution_path"] != "maker"

    # -------------------------------------------------------------- stamping

    @pytest.mark.asyncio
    async def test_taker_direct_stamped(
        self, trading_engine, mock_position_manager, mock_trade_repo
    ):
        """A plain execute_market_order call (no maker context) stamps
        taker_direct — 'never tried' is distinguishable from 'fell back'."""
        mock_position = Mock()
        mock_position.id = uuid4()
        mock_position_manager.create_position.return_value = mock_position

        executed, error = await trading_engine.execute_market_order(_order(OrderSide.BUY), _REF)
        await _drain_spawned_tasks()

        assert error is None
        meta = mock_trade_repo.log_trade.call_args.kwargs["execution_metadata"]
        assert meta == {
            "maker_attempted": False,
            "execution_path": "taker_direct",
            "fallback_reason": None,
            "fee_rate_applied": 0.055,
        }

    @pytest.mark.asyncio
    async def test_maker_metadata_on_fill(
        self, trading_engine, mock_position_manager, mock_trade_repo
    ):
        """A maker fill stamps execution_path='maker' with the MAKER rate."""
        mock_position = Mock()
        mock_position.id = uuid4()
        mock_position_manager.create_position.return_value = mock_position

        trading_engine._fetch_last_price = AsyncMock(return_value=Decimal("59960"))

        with _no_wall_clock():
            executed, error = await trading_engine.execute_maker_order_with_fallback(
                _order(OrderSide.BUY), _REF
            )
        await _drain_spawned_tasks()

        assert error is None
        meta = mock_trade_repo.log_trade.call_args.kwargs["execution_metadata"]
        assert meta["maker_attempted"] is True
        assert meta["execution_path"] == "maker"
        assert meta["fallback_reason"] is None
        # fee_rate_applied is percent-per-side, matching Settings units.
        assert meta["fee_rate_applied"] == 0.02

    # --------------------------------------------------------------- Decimal

    @pytest.mark.asyncio
    async def test_money_types_are_decimal(
        self, trading_engine, mock_position_manager, mock_trade_repo
    ):
        """money.md: commission and filled_price on the maker path are
        Decimal, never float."""
        mock_position = Mock()
        mock_position.id = uuid4()
        mock_position_manager.create_position.return_value = mock_position

        trading_engine._fetch_last_price = AsyncMock(return_value=Decimal("59960"))

        with _no_wall_clock():
            executed, error = await trading_engine.execute_maker_order_with_fallback(
                _order(OrderSide.BUY), _REF
            )
        await _drain_spawned_tasks()

        assert error is None
        assert isinstance(executed.filled_price, Decimal)
        assert isinstance(trading_engine.balance, Decimal)
        assert isinstance(trading_engine.maker_commission_pct, Decimal)
        entry_fee = mock_position_manager.create_position.call_args.kwargs["entry_fee"]
        assert isinstance(entry_fee, Decimal)
        commission = mock_trade_repo.log_trade.call_args.kwargs["commission"]
        assert isinstance(commission, Decimal)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
