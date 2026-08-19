"""Trade record + the trades-CSV contract screen.py consumes.

Columns (screen.py adapt_row): symbol, side, gross_pnl, notional_in,
notional_out, entry_ts_ms, exit_ts_ms. side must be LONG/SHORT — te_costs
funding_cost switches on it.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from edge_lab.config import NOTIONAL_PER_TRADE

_Q = Decimal("0.00000001")


@dataclass(frozen=True)
class Trade:
    symbol: str
    side: str  # "LONG" | "SHORT"
    entry_ts_ms: int
    exit_ts_ms: int
    entry_px: float
    exit_px: float

    def __post_init__(self) -> None:
        if self.side not in ("LONG", "SHORT"):
            raise ValueError(f"side must be LONG/SHORT, got {self.side!r}")
        if self.entry_px <= 0 or self.exit_px <= 0:
            raise ValueError(f"non-positive price on {self.symbol}")
        if self.exit_ts_ms <= self.entry_ts_ms:
            raise ValueError(f"exit_ts_ms <= entry_ts_ms on {self.symbol}")


@dataclass(frozen=True)
class Variant:
    candidate: str  # e.g. "xs_momentum"
    name: str  # e.g. "lookback_30d"
    params: tuple  # hashable param pairs, e.g. (("lookback_days", 30),)


def _ratio(t: Trade) -> Decimal:
    return Decimal(str(t.exit_px)) / Decimal(str(t.entry_px))


def gross_pnl(t: Trade) -> Decimal:
    move = _ratio(t) - 1
    signed = move if t.side == "LONG" else -move
    return (NOTIONAL_PER_TRADE * signed).quantize(_Q)


def notionals(t: Trade) -> tuple[Decimal, Decimal]:
    n_in = NOTIONAL_PER_TRADE
    n_out = (NOTIONAL_PER_TRADE * _ratio(t)).quantize(_Q)
    return n_in, n_out


def write_trades_csv(trades: list[Trade], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "symbol",
                "side",
                "gross_pnl",
                "notional_in",
                "notional_out",
                "entry_ts_ms",
                "exit_ts_ms",
            ]
        )
        for t in sorted(trades, key=lambda x: x.entry_ts_ms):
            n_in, n_out = notionals(t)
            w.writerow(
                [
                    t.symbol,
                    t.side,
                    str(gross_pnl(t)),
                    str(n_in),
                    str(n_out),
                    t.entry_ts_ms,
                    t.exit_ts_ms,
                ]
            )
    return path
