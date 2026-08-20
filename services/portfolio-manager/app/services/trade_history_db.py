"""Read-only hydration of PM transaction history from the engine-owned trades
table (RES-09). PM never writes engine tables — mirror doctrine (FIX 11).

The trades table lives in the same postgres DB both services already share;
idx_trades_portfolio_executed (portfolio_id, executed_at DESC) backs this
query.

Schema note (controller-verified against the live DB, 2026-08-20): the
SQLAlchemy model this was originally drafted against is stale. The deployed
`public.trades` table has no `action`, `total_cost`, `pnl_percentage`, or
`position_id` columns. Live columns used here: trade_id (uuid), portfolio_id,
symbol, side, quantity, price, total_value, realized_pnl, executed_at
(timestamp WITHOUT time zone, stored as naive-UTC). `side` carries the live
values BUY/SELL, which match PM's `Transaction.action` semantics exactly, so
it maps straight across. There is no percentage-P&L column in the live
table; `realized_pnl_pct` is always None here — do not fabricate one.
"""

import logging
from datetime import timezone
from typing import Optional

from app.models.transaction import Transaction

logger = logging.getLogger(__name__)

_BASE_QUERY = (
    "SELECT trade_id, portfolio_id, symbol, side, quantity, price, "
    "total_value, realized_pnl, executed_at "
    "FROM trades WHERE portfolio_id = $1"
)


async def fetch_transactions(
    pool, portfolio_id: str, limit: Optional[int], symbol: Optional[str]
) -> list[Transaction]:
    """Fetch fill-level transaction history for a portfolio from the shared
    trades table, most recent first.

    `symbol` and `limit` are bound as parameterized args, never interpolated.
    """
    query = _BASE_QUERY
    args: list = [portfolio_id]
    if symbol:
        query += " AND symbol = $2"
        args.append(symbol)
    query += " ORDER BY executed_at DESC"
    if limit:
        query += f" LIMIT ${len(args) + 1}"
        args.append(limit)

    rows = await pool.fetch(query, *args)
    txns = []
    for r in rows:
        realized_pnl = r["realized_pnl"]
        # executed_at comes back naive (asyncpg + "timestamp without time
        # zone"); it is stored as UTC (controller-verified against known
        # event times). Attaching UTC explicitly here is load-bearing — a
        # bare .timestamp() would apply the container's local timezone.
        executed_at_utc = r["executed_at"].replace(tzinfo=timezone.utc)
        txns.append(
            Transaction(
                transaction_id=str(r["trade_id"]),
                portfolio_id=r["portfolio_id"],
                symbol=r["symbol"],
                action=r["side"],
                quantity=str(r["quantity"]),
                price=str(r["price"]),
                total_amount=str(r["total_value"]),
                realized_pnl=(str(realized_pnl) if realized_pnl is not None else None),
                realized_pnl_pct=None,
                timestamp=int(executed_at_utc.timestamp() * 1000),
            )
        )
    return txns
