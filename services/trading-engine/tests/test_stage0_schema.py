"""
Stage 0 schema task: posted_margin / leverage / exit_kind must round-trip
through every one of the four hand-written mappers.

Regression target: positions.entry_signal_confidence has existed as a column
since before migration 007 and is NULL on all 19 live rows, because
PositionRepository.create never mapped it. A column added to the model and the
table but not to the mappers is a silent no-op.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4


from app.handlers.trades import db_position_to_app_position
from app.models.enums import ExitKind, PositionSide
from app.models.position import Position


def _db_row(**overrides):
    """A stand-in for a SQLAlchemy DBPosition row."""
    row = MagicMock()
    row.position_id = uuid4()
    row.symbol = "SOLUSDT"
    row.side = "LONG"
    row.quantity = Decimal("0.30")
    row.remaining_quantity = Decimal("0.201")
    row.entry_price = Decimal("72.68")
    row.current_price = Decimal("74.00")
    row.exit_price = None
    row.stop_loss = Decimal("71.2264")
    row.take_profit = Decimal("75.5872")
    row.status = "OPEN"
    row.strategy = "ensemble"
    # A real positions.opened_at is never NULL (server_default=func.now());
    # None here would make Position(...) raise on datetime validation
    # regardless of the Stage 0 fields under test, so use a real timestamp.
    row.opened_at = datetime(2026, 8, 7, 0, 0, 40, tzinfo=timezone.utc)
    row.closed_at = None
    row.unrealized_pnl = Decimal("0")
    row.realized_pnl = Decimal("0")
    row.exit_reason = None
    row.entry_fee = Decimal("0.012")
    row.exit_fee = Decimal("0")
    row.posted_margin = Decimal("21.804")
    row.leverage = Decimal("1")
    row.exit_kind = None
    for k, v in overrides.items():
        setattr(row, k, v)
    return row


def test_exit_kind_members_are_name_valued():
    for member in ExitKind:
        assert member.value == member.name, f"{member!r} value must equal its name"
    assert ExitKind.HARD_STOP.value == "HARD_STOP"
    assert ExitKind.MAX_HOLD.value == "MAX_HOLD"


def test_position_model_carries_margin_leverage_exit_kind():
    pos = Position(
        symbol="SOLUSDT",
        side=PositionSide.LONG,
        entry_price=Decimal("72.68"),
        quantity=Decimal("0.30"),
        posted_margin=Decimal("21.804"),
        leverage=Decimal("1"),
    )
    assert pos.posted_margin == Decimal("21.804")
    assert pos.leverage == Decimal("1")
    assert pos.exit_kind is None


def test_position_model_defaults_are_safe():
    pos = Position(
        symbol="BNBUSDT",
        side=PositionSide.SHORT,
        entry_price=Decimal("602.69"),
        quantity=Decimal("0.01"),
    )
    assert pos.posted_margin == Decimal("0")
    assert pos.leverage == Decimal("1")


def test_trade_history_mapper_carries_the_new_fields():
    """MAPPER 2 — handlers/trades.db_position_to_app_position."""
    row = _db_row(status="CLOSED", exit_kind="HARD_STOP", exit_price=Decimal("71.2264"))
    pos = db_position_to_app_position(row)
    assert pos.posted_margin == Decimal("21.804")
    assert pos.leverage == Decimal("1")
    assert pos.exit_kind == ExitKind.HARD_STOP


def test_trade_history_mapper_tolerates_nulls_on_legacy_rows():
    """The 17 pre-existing closed rows have NULL exit_kind and (pre-008) no margin."""
    row = _db_row(status="CLOSED", exit_kind=None, posted_margin=None, leverage=None)
    pos = db_position_to_app_position(row)
    assert pos.exit_kind is None
    assert pos.posted_margin == Decimal("0")
    assert pos.leverage == Decimal("1")
