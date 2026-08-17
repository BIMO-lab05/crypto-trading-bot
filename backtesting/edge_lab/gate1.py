"""Gate 1 - cost hurdle wrapper over screen.screen_trades.

Mirrors screen.py's main() composition exactly (CSV -> rows -> per-symbol
funding -> screen_trades), with edge_lab.config's pinned battery constants
substituted for screen.py's CLI defaults. See screen.py's module docstring
for the hurdle rationale; screen_trades verdicts are "PASS"/"KILL" only.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from costs_loader import load_costs, load_funding
from screen import (
    MODELLED_FEE_RATE_PER_PAIR,
    ScreenResult,
    _rows_from_csv,
    screen_trades,
)

from edge_lab.config import HURDLE_MULTIPLE, SLIPPAGE_BPS, SLIPPAGE_FALLBACK_BPS

_costs = load_costs()


def slippage_table() -> dict[str, Decimal]:
    """Majors-only slippage table. Every other symbol falls to
    SLIPPAGE_FALLBACK_BPS via screen_trades' slippage_fallback arg."""
    return dict(SLIPPAGE_BPS)


def run_gate1(trades_csv: Path, funding_dir: Path) -> ScreenResult:
    """Score one candidate's trades against the cost hurdle (Gate 1)."""
    rows, provenance = _rows_from_csv(
        str(trades_csv), modelled_fee_rate=MODELLED_FEE_RATE_PER_PAIR
    )
    symbols = {r["symbol"] for r in rows}
    funding = {s: load_funding(s, str(funding_dir)) for s in symbols}

    return screen_trades(
        rows,
        schedule=_costs.FeeSchedule.bybit_linear_perp(),
        slippage_table=slippage_table(),
        slippage_fallback=SLIPPAGE_FALLBACK_BPS,
        hurdle_multiple=HURDLE_MULTIPLE,
        funding_by_symbol=funding,
        funding_source=str(Path(funding_dir).resolve()),
        notional_provenance=provenance,
    )
