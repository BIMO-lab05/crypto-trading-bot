"""
PAPER-01 regression suite: the paper engine must model slippage.

Before this suite, `execute_market_order` filled at exactly the price it was
handed (ADR-011: "zero slippage, zero latency, always filled"). Every paper
P&L figure and every strategy Sharpe measured through the paper engine was
therefore gross of the spread the venue would actually have charged.

What is pinned here:
  1. Slippage is per-symbol, not a flat constant (BTC != ADA).
  2. Slippage always HURTS -- all four legs: LONG entry, LONG exit,
     SHORT entry, SHORT exit. A model that helps a SHORT close is a bug and
     this repo has shipped SHORT-side inversions before.
  3. The slipped price reaches the *position manager*, not just the cash
     balance -- `get_performance_summary()["realized_pnl"]` is sourced from
     closed positions, so a fill price that never got there would leave
     reported P&L unchanged (the "wired but never bites" failure mode).
  4. Prices quantize to the symbol's tick size, never `round(price, 2)`
     (487d1bd: 2dp rounding on ADA caused 30+ flip-flop losses).
  5. Zero slippage stays reachable explicitly for A/B comparison, but is not
     the default.
"""

from decimal import Decimal
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import pytest

from app.models import (
    OrderCreate,
    OrderSide,
    OrderType,
    Position,
    PositionSide,
    PositionStatus,
)
from app.paper_slippage import (
    DEFAULT_SLIPPAGE_BPS,
    DEFAULT_TICK_SIZE,
    PaperSlippageModel,
    build_slippage_model,
)
from app.paper_trading import PaperTradingEngine

VALIDATED_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"]


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakePositionManager:
    """Minimal in-memory stand-in exposing the surface the engine touches.

    Deliberately NOT a Mock: the point of this suite is to observe the price
    the engine hands to create_position / close_position, and to read realized
    P&L back out of the resulting closed positions.
    """

    def __init__(self) -> None:
        self.positions: Dict[UUID, Position] = {}

    def create_position(
        self,
        symbol: str,
        side: PositionSide,
        entry_price: Decimal,
        quantity: Decimal,
        strategy: Optional[str] = None,
        entry_signal_confidence: Optional[float] = None,
    ) -> Position:
        pos = Position(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            strategy=strategy,
            entry_signal_confidence=entry_signal_confidence,
        )
        self.positions[pos.id] = pos
        return pos

    def get_position(self, position_id: UUID) -> Optional[Position]:
        return self.positions.get(position_id)

    def get_open_positions(self) -> List[Position]:
        return [p for p in self.positions.values() if p.status == PositionStatus.OPEN]

    def get_closed_positions(self) -> List[Position]:
        return [p for p in self.positions.values() if p.status == PositionStatus.CLOSED]

    def get_total_unrealized_pnl(self) -> Decimal:
        return Decimal("0")

    def close_position(
        self, position_id: UUID, exit_price: Decimal, reason: Optional[str] = None
    ) -> Position:
        pos = self.positions[position_id]
        qty = pos.remaining_quantity or pos.quantity
        if pos.side == PositionSide.LONG:
            pnl = (exit_price - pos.entry_price) * qty
        else:
            pnl = (pos.entry_price - exit_price) * qty
        pos.realized_pnl += pnl
        pos.exit_price = exit_price
        pos.exit_reason = reason
        pos.remaining_quantity = Decimal("0")
        pos.status = PositionStatus.CLOSED
        return pos

    def reduce_position(
        self,
        position_id: UUID,
        quantity: Decimal,
        exit_price: Decimal,
        realized_pnl: Decimal,
    ) -> Position:
        pos = self.positions[position_id]
        pos.remaining_quantity = (pos.remaining_quantity or pos.quantity) - quantity
        pos.realized_pnl += realized_pnl
        return pos

    def scale_in(
        self, position_id: UUID, quantity: Decimal, price: Decimal
    ) -> Position:
        pos = self.positions[position_id]
        old_qty = pos.remaining_quantity or pos.quantity
        new_qty = old_qty + quantity
        pos.entry_price = ((pos.entry_price * old_qty) + (price * quantity)) / new_qty
        pos.quantity = pos.quantity + quantity
        pos.remaining_quantity = new_qty
        return pos


def _settings(slippage_enabled: bool = True) -> Mock:
    settings = Mock()
    settings.paper_initial_balance = 100.0
    settings.paper_commission_pct = 0.1
    settings.default_leverage = 1.0
    settings.paper_slippage_enabled = slippage_enabled
    settings.paper_slippage_bps_by_symbol = {}
    settings.paper_slippage_default_bps = 10.0
    return settings


def _engine(slippage_enabled: bool = True) -> PaperTradingEngine:
    trade_repo = Mock()
    trade_repo.log_trade = AsyncMock()
    risk_manager = Mock()
    risk_manager.check_position_limits.return_value = (True, None)
    with (
        patch(
            "app.paper_trading.get_settings",
            return_value=_settings(slippage_enabled),
        ),
        patch(
            "app.paper_trading.get_position_manager",
            return_value=FakePositionManager(),
        ),
        patch("app.paper_trading.get_risk_manager", return_value=risk_manager),
        patch("app.paper_trading.get_trade_repository", return_value=trade_repo),
        patch("app.paper_trading.get_portfolio_repository", return_value=Mock()),
    ):
        return PaperTradingEngine()


def _order(symbol: str, side: OrderSide, qty: Decimal, **kw) -> OrderCreate:
    return OrderCreate(
        symbol=symbol, side=side, quantity=qty, type=OrderType.MARKET, **kw
    )


# ---------------------------------------------------------------------------
# 1. The model itself
# ---------------------------------------------------------------------------


class TestPaperSlippageModel:
    def test_buy_pays_up_sell_gets_down(self):
        """REQUIREMENTS PAPER-01: BUY at 100 with 10 bps fills at 100.10."""
        model = PaperSlippageModel(
            enabled=True,
            bps_by_symbol={"ADAUSDT": Decimal("10")},
            tick_by_symbol={"ADAUSDT": Decimal("0.01")},
        )
        assert model.fill_price("ADAUSDT", OrderSide.BUY, Decimal("100")) == Decimal(
            "100.10"
        )
        assert model.fill_price("ADAUSDT", OrderSide.SELL, Decimal("100")) == Decimal(
            "99.90"
        )

    def test_per_symbol_not_a_flat_constant(self):
        """BTC and ADA do not have the same relative spread."""
        for symbol in VALIDATED_SYMBOLS:
            assert symbol in DEFAULT_SLIPPAGE_BPS, f"{symbol} missing from bps table"
            assert symbol in DEFAULT_TICK_SIZE, f"{symbol} missing from tick table"
        assert DEFAULT_SLIPPAGE_BPS["ADAUSDT"] > DEFAULT_SLIPPAGE_BPS["BTCUSDT"]
        assert len({DEFAULT_SLIPPAGE_BPS[s] for s in VALIDATED_SYMBOLS}) > 1

    def test_every_validated_symbol_moves_the_price_adversely(self):
        model = build_slippage_model(_settings(True))
        ref = {
            "BTCUSDT": Decimal("60000"),
            "ETHUSDT": Decimal("3000"),
            "SOLUSDT": Decimal("140"),
            "BNBUSDT": Decimal("600"),
            "ADAUSDT": Decimal("0.4000"),
        }
        for symbol, price in ref.items():
            assert model.fill_price(symbol, OrderSide.BUY, price) > price
            assert model.fill_price(symbol, OrderSide.SELL, price) < price

    def test_quantizes_to_tick_not_two_decimals(self):
        """487d1bd: round(price, 2) destroys ADA precision. Never again."""
        model = build_slippage_model(_settings(True))
        filled = model.fill_price("ADAUSDT", OrderSide.SELL, Decimal("0.4000"))
        # A 2dp round of any sub-dollar fill collapses to 0.40 and erases the
        # slippage entirely; the tick-quantized answer must stay below it.
        assert filled < Decimal("0.4000")
        assert filled != Decimal("0.40")
        assert filled % DEFAULT_TICK_SIZE["ADAUSDT"] == 0

    def test_quantization_is_away_from_mid(self):
        """Rounding must never hand back a better price than the raw model."""
        model = build_slippage_model(_settings(True))
        raw_buy = Decimal("60000") * (
            Decimal("1") + DEFAULT_SLIPPAGE_BPS["BTCUSDT"] / Decimal("10000")
        )
        raw_sell = Decimal("60000") * (
            Decimal("1") - DEFAULT_SLIPPAGE_BPS["BTCUSDT"] / Decimal("10000")
        )
        assert model.fill_price("BTCUSDT", OrderSide.BUY, Decimal("60000")) >= raw_buy
        assert model.fill_price("BTCUSDT", OrderSide.SELL, Decimal("60000")) <= raw_sell

    def test_returns_decimal_never_float(self):
        model = build_slippage_model(_settings(True))
        assert isinstance(
            model.fill_price("BTCUSDT", OrderSide.BUY, Decimal("60000")), Decimal
        )

    def test_disabled_is_reachable_but_not_the_default(self):
        off = build_slippage_model(_settings(False))
        assert off.fill_price("BTCUSDT", OrderSide.BUY, Decimal("60000")) == Decimal(
            "60000"
        )
        # Default (settings object without the attribute at all) is ON.
        bare = Mock(spec=[])
        assert build_slippage_model(bare).enabled is True

    def test_bad_config_falls_back_to_builtin_table(self):
        settings = _settings(True)
        settings.paper_slippage_bps_by_symbol = "not-a-dict"
        model = build_slippage_model(settings)
        assert model.bps_for("BTCUSDT") == DEFAULT_SLIPPAGE_BPS["BTCUSDT"]

    def test_config_override_wins(self):
        settings = _settings(True)
        settings.paper_slippage_bps_by_symbol = {"BTCUSDT": 50.0}
        model = build_slippage_model(settings)
        assert model.bps_for("BTCUSDT") == Decimal("50")
        assert model.bps_for("ADAUSDT") == DEFAULT_SLIPPAGE_BPS["ADAUSDT"]


# ---------------------------------------------------------------------------
# 2. The model actually reaches the fill path
# ---------------------------------------------------------------------------


class TestSlippageReachesTheFill:
    @pytest.mark.asyncio
    async def test_long_entry_fills_above_reference(self):
        engine = _engine()
        order = _order("BTCUSDT", OrderSide.BUY, Decimal("0.0005"))
        executed, err = await engine.execute_market_order(order, Decimal("60000"))
        assert err is None
        assert executed.filled_price > Decimal("60000")
        # The position manager -- not just the cash ledger -- sees the slip.
        pos = engine.position_manager.get_position(executed.position_id)
        assert pos.entry_price == executed.filled_price

    @pytest.mark.asyncio
    async def test_short_entry_fills_below_reference(self):
        engine = _engine()
        order = _order("BTCUSDT", OrderSide.SELL, Decimal("0.0005"))
        executed, err = await engine.execute_market_order(order, Decimal("60000"))
        assert err is None
        assert executed.filled_price < Decimal("60000")
        pos = engine.position_manager.get_position(executed.position_id)
        assert pos.side == PositionSide.SHORT
        assert pos.entry_price == executed.filled_price

    @pytest.mark.asyncio
    async def test_long_exit_fills_below_reference(self):
        engine = _engine()
        await engine.execute_market_order(
            _order("BTCUSDT", OrderSide.BUY, Decimal("0.0005")), Decimal("60000")
        )
        executed, err = await engine.execute_market_order(
            _order("BTCUSDT", OrderSide.SELL, Decimal("0.0005"), reduce_only=True),
            Decimal("61000"),
        )
        assert err is None
        assert executed.filled_price < Decimal("61000")
        closed = engine.position_manager.get_closed_positions()[0]
        assert closed.exit_price == executed.filled_price

    @pytest.mark.asyncio
    async def test_short_exit_fills_above_reference(self):
        """The leg most likely to be inverted: buying back a short must cost
        MORE, never less."""
        engine = _engine()
        await engine.execute_market_order(
            _order("BTCUSDT", OrderSide.SELL, Decimal("0.0005")), Decimal("60000")
        )
        executed, err = await engine.execute_market_order(
            _order("BTCUSDT", OrderSide.BUY, Decimal("0.0005"), reduce_only=True),
            Decimal("59000"),
        )
        assert err is None
        assert executed.filled_price > Decimal("59000")
        closed = engine.position_manager.get_closed_positions()[0]
        assert closed.exit_price == executed.filled_price


# ---------------------------------------------------------------------------
# 3. It bites: reported P&L must get worse
# ---------------------------------------------------------------------------


async def _round_trip(
    engine: PaperTradingEngine,
    symbol: str,
    entry: Decimal,
    exit_: Decimal,
    side: OrderSide,
    qty: Decimal,
) -> None:
    opened, err = await engine.execute_market_order(_order(symbol, side, qty), entry)
    assert err is None, err
    close_side = OrderSide.SELL if side == OrderSide.BUY else OrderSide.BUY
    _, err = await engine.execute_market_order(
        _order(
            symbol,
            close_side,
            qty,
            reduce_only=True,
            position_id=opened.position_id,
        ),
        exit_,
    )
    assert err is None, err


class TestReportedPnLGetsWorse:
    @pytest.mark.asyncio
    async def test_long_round_trip_realized_pnl_is_worse_with_slippage(self):
        frictionless = _engine(slippage_enabled=False)
        realistic = _engine(slippage_enabled=True)
        for engine in (frictionless, realistic):
            await _round_trip(
                engine,
                "BTCUSDT",
                Decimal("60000"),
                Decimal("61000"),
                OrderSide.BUY,
                Decimal("0.0005"),
            )
        a = frictionless.get_performance_summary()["realized_pnl"]
        b = realistic.get_performance_summary()["realized_pnl"]
        assert b < a, f"slippage did not reach reported P&L: {b} vs {a}"

    @pytest.mark.asyncio
    async def test_short_round_trip_realized_pnl_is_worse_with_slippage(self):
        frictionless = _engine(slippage_enabled=False)
        realistic = _engine(slippage_enabled=True)
        for engine in (frictionless, realistic):
            await _round_trip(
                engine,
                "BTCUSDT",
                Decimal("60000"),
                Decimal("59000"),
                OrderSide.SELL,
                Decimal("0.0005"),
            )
        a = frictionless.get_performance_summary()["realized_pnl"]
        b = realistic.get_performance_summary()["realized_pnl"]
        assert b < a, f"slippage helped a SHORT: {b} vs {a}"

    @pytest.mark.asyncio
    async def test_every_validated_symbol_costs_equity(self):
        """A/B on identical input across all 5 traded symbols."""
        legs = [
            ("BTCUSDT", Decimal("60000"), Decimal("60600"), Decimal("0.0005")),
            ("ETHUSDT", Decimal("3000"), Decimal("3030"), Decimal("0.01")),
            ("SOLUSDT", Decimal("140"), Decimal("141.40"), Decimal("0.2")),
            ("BNBUSDT", Decimal("600"), Decimal("606"), Decimal("0.05")),
            ("ADAUSDT", Decimal("0.4000"), Decimal("0.4040"), Decimal("50")),
        ]
        for symbol, entry, exit_, qty in legs:
            frictionless = _engine(slippage_enabled=False)
            realistic = _engine(slippage_enabled=True)
            for engine in (frictionless, realistic):
                await _round_trip(engine, symbol, entry, exit_, OrderSide.BUY, qty)
            a = frictionless.get_total_equity()
            b = realistic.get_total_equity()
            assert b < a, f"{symbol}: slippage cost nothing ({b} vs {a})"
