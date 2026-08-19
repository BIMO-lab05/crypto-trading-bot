"""
Hurdle-first screen: does a candidate's gross edge clear twice its cost?

This runs BEFORE any statistics. Most candidates die here in seconds, which is
the point - CLAUDE.md's stated value of this infrastructure is killing bad
strategies cheaply, and "disproved in an afternoon" is a win.

THE HURDLE. Gross edge per trade must be at least `hurdle_multiple` x the
all-in round-trip cost for that symbol:

    taker fees + slippage   21 bps (BTC/ETH/SOL) / 31 bps (BNB/ADA)
    maker fees only          4 bps  (+ unmodelled adverse selection)
    funding                  signed, per-symbol, per-side, per-holding-period

The headline verdict is the TAKER verdict. A candidate that clears only under
maker-only assumptions is NOT passed here: 4 bps covers explicit fees alone,
and adverse selection and non-fill are real costs this module cannot express.
Such a candidate must separately demonstrate a fill model that accounts for
the orders that never fill. Both ratios are reported so that case is visible.

For reference, the deployed ensemble measures 0.0488% (4.88 bps) of gross edge
per trade against 21-31 bps of cost - a 2.3x to 4.1x shortfall, and the reason
paper trading loses money.

FUNDING IS REPORTED AS UNAVAILABLE, NOT AS ZERO. Nothing in this repo has ever
stored funding rates, so `load_funding` returns [] for every symbol today. An
empty series contributes zero, which is honest arithmetic - but a bare
`funding total 0.000000` line would let a funding-EXCLUSIVE verdict be quoted
as a funding-inclusive one. Every symbol without a series is named, and the
`net` lines that a reader actually quotes carry the exclusion marker.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence

from costs_loader import load_costs

_costs = load_costs()
_BPS = Decimal("10000")

# The modelled round-trip fee rate recorded in the H3 per-trade tables:
# fees_modelled = (notional_in + notional_out) * 0.001, so one leg's notional
# is fees_modelled / 0.001 / 2. Only used when a CSV carries no explicit
# notional columns, and always declared in the rendered output - a table
# written at a different rate would otherwise get silently wrong notionals.
MODELLED_FEE_RATE_PER_PAIR = Decimal("0.001")

# Hand-maintained mirror of services/trading-engine/app/paper_slippage.py
# DEFAULT_SLIPPAGE_BPS / FALLBACK_SLIPPAGE_BPS (one-way basis points).
# screen.py must stay runnable standalone, so the values are restated rather
# than imported across the service boundary; agreement is enforced by
# tests/killtests/test_slippage_table_sync.py.
SLIPPAGE_BPS_BY_SYMBOL: dict[str, Decimal] = {
    "BTCUSDT": Decimal("5"),
    "ETHUSDT": Decimal("5"),
    "SOLUSDT": Decimal("5"),
    "BNBUSDT": Decimal("10"),
    "ADAUSDT": Decimal("10"),
}
SLIPPAGE_FALLBACK_BPS: Decimal = Decimal("10")

_NOTIONAL_FROM_COLUMNS = "notional_in / notional_out, as supplied"


@dataclass(frozen=True)
class ScreenResult:
    n_trades: int
    gross_total: Decimal
    gross_expectancy: Decimal
    mean_leg_notional: Decimal
    gross_edge_bps: Decimal
    cost_bps_taker: Decimal
    cost_bps_maker: Decimal
    funding_total: Decimal
    net_taker: Decimal
    net_maker: Decimal
    ratio_taker: Decimal
    ratio_maker: Decimal
    hurdle_multiple: Decimal
    verdict: str
    funding_symbols_covered: tuple[str, ...] = ()
    funding_symbols_missing: tuple[str, ...] = ()
    funding_source: str = "not supplied"
    notional_provenance: str = _NOTIONAL_FROM_COLUMNS

    @property
    def funding_complete(self) -> bool:
        """True only when every traded symbol had a non-empty series."""
        return not self.funding_symbols_missing

    def render(self) -> str:
        n_sym = len(self.funding_symbols_covered) + len(self.funding_symbols_missing)
        if self.funding_complete:
            funding_note = f"({len(self.funding_symbols_covered)} of {n_sym} symbols)"
            net_note = ""
        else:
            missing = ", ".join(self.funding_symbols_missing)
            funding_note = (
                f"[UNAVAILABLE — {len(self.funding_symbols_covered)} of {n_sym} "
                f"symbols have data; none for {missing}; source: "
                f"{self.funding_source}]"
            )
            net_note = "  (EXCLUDES funding — no data)"

        lines = [
            f"n trades                {self.n_trades}",
            f"gross total             {self.gross_total:.6f}",
            f"gross expectancy/trade  {self.gross_expectancy:.10f}",
            f"mean leg notional       {self.mean_leg_notional:.4f}",
            f"leg notional source     {self.notional_provenance}",
            f"gross edge              {self.gross_edge_bps:.4f} bps",
            f"cost, taker             {self.cost_bps_taker:.4f} bps",
            f"cost, maker             {self.cost_bps_maker:.4f} bps",
            f"funding total           {self.funding_total:.6f}  {funding_note}",
            f"net, taker              {self.net_taker:.4f}{net_note}",
            f"net, maker              {self.net_maker:.4f}{net_note}",
            f"edge/cost, taker        {self.ratio_taker:.3f}x "
            f"(need {self.hurdle_multiple}x)",
            f"edge/cost, maker        {self.ratio_maker:.3f}x",
            f"VERDICT                 {self.verdict}",
        ]
        return "\n".join(lines)


def screen_trades(
    trades: Sequence[Mapping],
    *,
    schedule,
    slippage_table: Mapping[str, Decimal],
    slippage_fallback: Decimal,
    hurdle_multiple: Decimal = Decimal("2"),
    funding_by_symbol: Mapping[str, list] | None = None,
    funding_source: str = "not supplied",
    notional_provenance: str = _NOTIONAL_FROM_COLUMNS,
) -> ScreenResult:
    """Score a trade list against the cost hurdle.

    Each trade needs: symbol, side, gross_pnl, notional_in, notional_out,
    entry_ts_ms, exit_ts_ms.

    An empty list RAISES. A vacuous PASS on zero trades is the single most
    dangerous output this module could produce.
    """
    if not trades:
        raise ValueError("no trades to screen — refusing to render a verdict")

    funding_by_symbol = funding_by_symbol or {}

    n = len(trades)
    gross_total = Decimal("0")
    leg_notional_total = Decimal("0")
    cost_taker_total = Decimal("0")
    cost_maker_total = Decimal("0")
    funding_total = Decimal("0")

    covered: set[str] = set()
    missing: set[str] = set()
    bps_cache: dict[str, tuple[Decimal, Decimal]] = {}

    for t in trades:
        symbol = t["symbol"]
        n_in = Decimal(str(t["notional_in"]))
        n_out = Decimal(str(t["notional_out"]))
        gross_total += Decimal(str(t["gross_pnl"]))
        leg_notional_total += (n_in + n_out) / 2

        if symbol not in bps_cache:
            bps_cache[symbol] = (
                _costs.round_trip_cost_bps(
                    symbol,
                    entry_liquidity=_costs.Liquidity.TAKER,
                    exit_liquidity=_costs.Liquidity.TAKER,
                    schedule=schedule,
                    slippage_table=slippage_table,
                    slippage_fallback=slippage_fallback,
                ),
                _costs.round_trip_cost_bps(
                    symbol,
                    entry_liquidity=_costs.Liquidity.MAKER,
                    exit_liquidity=_costs.Liquidity.MAKER,
                    schedule=schedule,
                    slippage_table=slippage_table,
                    slippage_fallback=slippage_fallback,
                ),
            )
        taker_bps, maker_bps = bps_cache[symbol]

        avg_leg = (n_in + n_out) / 2
        cost_taker_total += avg_leg * taker_bps / _BPS
        cost_maker_total += avg_leg * maker_bps / _BPS

        series = funding_by_symbol.get(symbol) or []
        if series:
            covered.add(symbol)
            funding_total += _costs.funding_cost(
                avg_leg,
                t["side"],
                series,
                entry_ts_ms=int(t["entry_ts_ms"]),
                exit_ts_ms=int(t["exit_ts_ms"]),
            )
        else:
            # No series is NOT a measured zero. Named, so the verdict can
            # never be quoted as funding-inclusive when it is not.
            missing.add(symbol)

    mean_leg = leg_notional_total / n
    gross_edge_bps = (gross_total / leg_notional_total) * _BPS

    # Per-symbol costs are reported as the notional-weighted average, so a
    # mixed-symbol candidate is scored against what it would actually pay.
    cost_bps_taker = (cost_taker_total / leg_notional_total) * _BPS
    cost_bps_maker = (cost_maker_total / leg_notional_total) * _BPS

    ratio_taker = (
        gross_edge_bps / cost_bps_taker if cost_bps_taker > 0 else Decimal("0")
    )
    ratio_maker = (
        gross_edge_bps / cost_bps_maker if cost_bps_maker > 0 else Decimal("0")
    )

    verdict = "PASS" if ratio_taker >= hurdle_multiple else "KILL"

    return ScreenResult(
        n_trades=n,
        gross_total=gross_total,
        gross_expectancy=gross_total / n,
        mean_leg_notional=mean_leg,
        gross_edge_bps=gross_edge_bps,
        cost_bps_taker=cost_bps_taker,
        cost_bps_maker=cost_bps_maker,
        funding_total=funding_total,
        net_taker=gross_total - cost_taker_total - funding_total,
        net_maker=gross_total - cost_maker_total - funding_total,
        ratio_taker=ratio_taker,
        ratio_maker=ratio_maker,
        hurdle_multiple=hurdle_multiple,
        verdict=verdict,
        funding_symbols_covered=tuple(sorted(covered)),
        funding_symbols_missing=tuple(sorted(missing)),
        funding_source=funding_source,
        notional_provenance=notional_provenance,
    )


def adapt_row(row: Mapping, *, modelled_fee_rate: Decimal) -> tuple[dict, str]:
    """One CSV row -> a screen trade, plus how its notional was obtained.

    Explicit `notional_in`/`notional_out` win. Failing that, the H3 per-trade
    tables record `fees_modelled = (notional_in + notional_out) *
    modelled_fee_rate`, so one leg is `fees_modelled / rate / 2`. A row with
    neither RAISES - guessing a notional would silently rescale every bps
    figure the screen prints.
    """
    if row.get("notional_in") and row.get("notional_out"):
        n_in = Decimal(str(row["notional_in"]))
        n_out = Decimal(str(row["notional_out"]))
        provenance = _NOTIONAL_FROM_COLUMNS
    elif row.get("fees_modelled"):
        n_in = n_out = Decimal(str(row["fees_modelled"])) / modelled_fee_rate / 2
        provenance = (
            f"derived from fees_modelled at {modelled_fee_rate} per round trip "
            f"— not read from the CSV"
        )
    else:
        raise KeyError(
            "row has neither notional_in/notional_out nor fees_modelled; "
            f"columns present: {sorted(row)}"
        )

    return (
        {
            "symbol": row["symbol"],
            "side": row["side"],
            "gross_pnl": Decimal(str(row["gross_pnl"])),
            "notional_in": n_in,
            "notional_out": n_out,
            "entry_ts_ms": int(row.get("entry_ts_ms") or 0),
            "exit_ts_ms": int(row.get("exit_ts_ms") or 0),
        },
        provenance,
    )


def _rows_from_csv(path: str, *, modelled_fee_rate: Decimal) -> tuple[list[dict], str]:
    with open(path) as fh:
        raw = list(csv.DictReader(fh))
    if not raw:
        raise ValueError(f"{path} has no rows — refusing to render a verdict")
    adapted = [adapt_row(r, modelled_fee_rate=modelled_fee_rate) for r in raw]
    provenances = {p for _, p in adapted}
    provenance = (
        provenances.pop()
        if len(provenances) == 1
        else "MIXED: " + "; ".join(sorted(provenances))
    )
    return [t for t, _ in adapted], provenance


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Hurdle-first edge screen")
    ap.add_argument("--trades", required=True, help="CSV of trades")
    ap.add_argument("--hurdle", default="2", help="required edge/cost multiple")
    ap.add_argument("--funding-dir", default="backtesting/data/funding")
    ap.add_argument(
        "--modelled-fee-rate",
        default=str(MODELLED_FEE_RATE_PER_PAIR),
        help=(
            "round-trip fee rate a CSV's fees_modelled column was written at; "
            "used only to derive leg notional when the CSV has no notional "
            "columns"
        ),
    )
    args = ap.parse_args()

    from pathlib import Path

    from costs_loader import load_funding

    rows, provenance = _rows_from_csv(
        args.trades, modelled_fee_rate=Decimal(args.modelled_fee_rate)
    )
    symbols = {r["symbol"] for r in rows}
    funding = {s: load_funding(s, args.funding_dir) for s in symbols}

    result = screen_trades(
        rows,
        schedule=_costs.FeeSchedule.bybit_linear_perp(),
        slippage_table=SLIPPAGE_BPS_BY_SYMBOL,
        slippage_fallback=SLIPPAGE_FALLBACK_BPS,
        hurdle_multiple=Decimal(args.hurdle),
        funding_by_symbol=funding,
        funding_source=str(Path(args.funding_dir).resolve()),
        notional_provenance=provenance,
    )
    print(result.render())


if __name__ == "__main__":
    main()
