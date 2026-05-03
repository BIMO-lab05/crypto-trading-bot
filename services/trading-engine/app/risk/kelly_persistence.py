"""
Kelly state persistence helpers.

The KellyPositionSizer keeps a rolling window of trades plus a few aggregate
counters. Without persistence the auto-trader resets to a "no edge" state on
every restart and has to re-accumulate ROLLING_WINDOW (50) trades before
Kelly sizing kicks back in. This module mirrors that state into a single
`kelly_state` row so the sizer survives container restarts.

The implementation uses SQLAlchemy Core (no ORM) so it works with both
PostgreSQL (production) and SQLite (tests). The rolling window is stored as
a plain JSON-encoded TEXT column — small and not indexed, but cross-DB
portable.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    select,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection
    from app.risk.kelly_position_sizing import KellyPositionSizer, TradeRecord

logger = logging.getLogger(__name__)

GLOBAL_STATE_ID = "global"

_metadata = MetaData()

kelly_state_table = Table(
    "kelly_state",
    _metadata,
    Column("id", String(50), primary_key=True),
    Column("total_trades", Integer, nullable=False, default=0),
    Column("winning_trades", Integer, nullable=False, default=0),
    Column("losing_trades", Integer, nullable=False, default=0),
    Column("total_wins_pct", Float, nullable=False, default=0.0),
    Column("total_losses_pct", Float, nullable=False, default=0.0),
    Column("current_streak", Integer, nullable=False, default=0),
    Column("current_kelly_fraction", Float, nullable=False, default=0.25),
    Column("rolling_window_json", Text, nullable=False, default="[]"),
    Column("updated_at", DateTime(timezone=True)),
)


def ensure_schema(connection: "Connection") -> None:
    """Create the kelly_state table on the given connection if absent.

    The production DDL lives in migration 006; this is for tests where we
    spin up an SQLite engine and need the schema in-process.
    """
    _metadata.create_all(bind=connection, tables=[kelly_state_table])


def _trade_to_dict(trade: "TradeRecord") -> dict:
    return {
        "trade_id": trade.trade_id,
        "symbol": trade.symbol,
        "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
        "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "pnl": trade.pnl,
        "pnl_pct": trade.pnl_pct,
        "is_win": trade.is_win,
        "strategy": trade.strategy,
        "kelly_suggested": trade.kelly_suggested,
        "actual_size": trade.actual_size,
    }


def _trade_from_dict(data: dict) -> "TradeRecord":
    # Imported here to avoid a circular import at module load time.
    from app.risk.kelly_position_sizing import TradeRecord

    return TradeRecord(
        trade_id=data["trade_id"],
        symbol=data["symbol"],
        entry_time=datetime.fromisoformat(data["entry_time"]) if data.get("entry_time") else datetime.utcnow(),
        exit_time=datetime.fromisoformat(data["exit_time"]) if data.get("exit_time") else datetime.utcnow(),
        entry_price=float(data.get("entry_price", 0.0)),
        exit_price=float(data.get("exit_price", 0.0)),
        pnl=float(data.get("pnl", 0.0)),
        pnl_pct=float(data.get("pnl_pct", 0.0)),
        is_win=bool(data.get("is_win", False)),
        strategy=data.get("strategy", "stat_arb"),
        kelly_suggested=data.get("kelly_suggested"),
        actual_size=data.get("actual_size"),
    )


def save_state(connection: "Connection", sizer: "KellyPositionSizer") -> None:
    """Upsert the sizer's aggregate state plus rolling window.

    Uses dialect-native `INSERT ... ON CONFLICT DO UPDATE` so each call is a
    single round-trip — important on the hot path where every trade close
    triggers a save. PostgreSQL and SQLite (3.24+) both support the syntax
    via SQLAlchemy's dialect-specific insert constructs.
    """
    rolling = [_trade_to_dict(t) for t in sizer._trade_history]
    payload = {
        "id": GLOBAL_STATE_ID,
        "total_trades": sizer._total_trades,
        "winning_trades": sizer._winning_trades,
        "losing_trades": sizer._losing_trades,
        "total_wins_pct": sizer._total_wins_pct,
        "total_losses_pct": sizer._total_losses_pct,
        "current_streak": sizer._current_streak,
        "current_kelly_fraction": sizer._current_kelly_fraction,
        "rolling_window_json": json.dumps(rolling),
        # Timezone-aware so a DateTime(timezone=True) column stores a real
        # UTC instant instead of a naive datetime that PostgreSQL would
        # reinterpret as the server's local timezone.
        "updated_at": datetime.now(timezone.utc),
    }

    dialect_name = connection.dialect.name
    if dialect_name == "postgresql":
        insert_stmt = pg_insert(kelly_state_table).values(**payload)
    elif dialect_name == "sqlite":
        insert_stmt = sqlite_insert(kelly_state_table).values(**payload)
    else:
        # Generic two-step fallback for dialects without ON CONFLICT support.
        existing = connection.execute(
            select(kelly_state_table.c.id).where(kelly_state_table.c.id == GLOBAL_STATE_ID)
        ).first()
        if existing is None:
            connection.execute(kelly_state_table.insert().values(**payload))
        else:
            connection.execute(
                kelly_state_table.update()
                .where(kelly_state_table.c.id == GLOBAL_STATE_ID)
                .values(**payload)
            )
        return

    update_columns = {k: v for k, v in payload.items() if k != "id"}
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=["id"],
        set_=update_columns,
    )
    connection.execute(upsert_stmt)


def load_state(connection: "Connection", sizer: "KellyPositionSizer") -> int:
    """Hydrate the sizer from the persisted row.

    Returns the number of rolling-window trades restored. If no row exists
    (fresh deploy) returns 0 and leaves the sizer untouched.
    """
    row = connection.execute(
        select(kelly_state_table).where(kelly_state_table.c.id == GLOBAL_STATE_ID)
    ).mappings().first()

    if row is None:
        return 0

    sizer._total_trades = int(row["total_trades"])
    sizer._winning_trades = int(row["winning_trades"])
    sizer._losing_trades = int(row["losing_trades"])
    sizer._total_wins_pct = float(row["total_wins_pct"])
    sizer._total_losses_pct = float(row["total_losses_pct"])
    sizer._current_streak = int(row["current_streak"])
    sizer._current_kelly_fraction = float(row["current_kelly_fraction"])

    sizer._trade_history.clear()
    rolling_json = row["rolling_window_json"] or "[]"
    try:
        rolling = json.loads(rolling_json)
    except json.JSONDecodeError:
        logger.warning("Corrupt rolling_window_json in kelly_state; ignoring")
        rolling = []

    restored = 0
    for entry in rolling:
        try:
            sizer._trade_history.append(_trade_from_dict(entry))
            restored += 1
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping malformed kelly trade record: %s", exc)

    sizer._stats_cache = None
    return restored
