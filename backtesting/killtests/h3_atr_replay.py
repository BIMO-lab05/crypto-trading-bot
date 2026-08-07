"""H3 kill test: replay the recorded entries with ATR-derived brackets.

AUDIT.md:261 — stops at 1.5x/2.5x ATR-derived daily vol, TP 2R, all else
identical. Accept: stop-out rate < 40% AND gross expectancy > 0 pre-fee.

Two things the verdict says that the criterion alone does not:

  * the headline ACCEPT requires EVERY stop-multiple variant to clear both
    legs (`headline_accept`) — the criterion has no any-variant clause;
  * trades that ran off the end of the CSV (`exit_reason == "end_of_data"`)
    are reported separately from the headline (`truncated_*`), because their
    outcome reflects backfill length rather than exit design. `max_hold`
    exits are NOT separated — the 48h cutoff is part of the design under test.

Intrabar rule copied from BacktestEngine._check_exit_conditions: stop is
checked BEFORE take-profit on every bar, for both sides (pessimistic).
Entries start at the first bar opening at/after the recorded entry time.

DEVIATION from task-6-brief.md (team-lead approved 2026-08-05, see
tests/killtests/test_h3_atr_replay.py::test_walk_starts_after_entry_ts for
the full writeup): the brief's own reference `replay_entry` decides
max_hold vs end_of_data via `len(walk) >= max_hold_bars`, which fails one of
the brief's own Step-1 tests. This implementation instead treats ANY walk
exhaustion before max_hold_bars is reached as "end_of_data" — consistent
with the other two exit-labeling tests, and truthful for the real run
(each entry's `bars` argument is its entire symbol/resolution history, so
running out of `walk` always means running out of real data, never an
intentional stop).
"""

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from dataclasses import asdict, dataclass

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "backtesting"))

from shared.account import PAPER_INITIAL_BALANCE, TAKER_FEE_PER_SIDE  # noqa: E402

from killtests.candles import (  # noqa: E402
    INTERVAL_MS,
    CandleStore,
    CandleValidationError,
)
from killtests.entries import DEFAULT_FIXTURE, Entry, load_entries  # noqa: E402
from killtests.report import latest_verdict, write_verdict  # noqa: E402

MODELLED_FEE_PER_SIDE = 0.001  # engine convention ("modelled"), AUDIT.md header
MAX_HOLD_HOURS = 48

# The backfill manifest digest the primary run's three narrative caveats
# (bracket inertness, regime concentration, stale-entry contamination) were
# computed against by hand on 2026-08-05. They are findings about THAT data,
# not something this script recomputes, so they are only emitted when the
# inputs still match. See _vintage_caveats.
NARRATIVE_MANIFEST_SHA12 = "cc63d3c487f1"


def _load_atr_calculator():
    """Spec-load trading-engine atr_stops.py under a unique name (no `app` collision)."""
    path = os.path.join(_REPO, "services", "trading-engine", "app", "atr_stops.py")
    spec = importlib.util.spec_from_file_location("_killtests_atr_stops", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_killtests_atr_stops"] = mod
    spec.loader.exec_module(mod)
    return mod.ATRStopCalculator


def daily_atr(
    store: CandleStore, symbol: str, entry_ts_ms: int, period: int = 14
) -> float:
    win = store.daily_window_before(symbol, entry_ts_ms, n=period + 1)
    calc = _load_atr_calculator()(atr_period=period)
    atr = calc.calculate_atr(
        win["high"].tolist(), win["low"].tolist(), win["close"].tolist()
    )
    if atr <= 0:
        raise ValueError(f"non-positive ATR for {symbol} at {entry_ts_ms}")
    return atr


@dataclass
class TradeOutcome:
    exit_price: float
    exit_reason: str
    bars_held: int
    gross_pnl: float
    ambiguous_bars: int


def replay_entry(
    entry: Entry, bars: pd.DataFrame, stop: float, tp: float, max_hold_bars: int
) -> TradeOutcome:
    walk = bars[bars["ts_ms"] >= entry.entry_ts_ms].reset_index(drop=True)
    if walk.empty:
        raise ValueError(
            f"{entry.position_id}: no bars at/after entry ts {entry.entry_ts_ms}"
        )
    long = entry.side == "LONG"
    ambiguous = 0
    exit_price, reason, held = None, None, 0
    n = min(len(walk), max_hold_bars)
    for i in range(n):
        row = walk.iloc[i]
        stop_hit = row.low <= stop if long else row.high >= stop
        tp_hit = row.high >= tp if long else row.low <= tp
        if stop_hit and tp_hit:
            ambiguous += 1
        if stop_hit:  # stop checked first — pessimistic, mirrors BacktestEngine
            exit_price, reason, held = stop, "stop_loss", i + 1
            break
        if tp_hit:
            exit_price, reason, held = tp, "take_profit", i + 1
            break
    if exit_price is None:
        # Walked through `n` bars (either max_hold_bars reached, or the walk
        # ran out first) without a stop/TP touch. Distinguish the two: only
        # an intentional cutoff at max_hold_bars is "max_hold" — running out
        # of `walk` before that is always "end_of_data" (see module
        # docstring for why the brief's own formula was wrong here).
        held = n
        reason = "max_hold" if len(walk) >= max_hold_bars else "end_of_data"
        exit_price = float(walk.iloc[n - 1]["close"])
    direction = 1.0 if long else -1.0
    gross = (exit_price - entry.entry_price) * direction * entry.quantity
    return TradeOutcome(float(exit_price), reason, held, float(gross), ambiguous)


def _pick_resolution(store: CandleStore, entry, preferred: str) -> str:
    """Per-entry resolution: preferred (15m) if its frame covers the entry start,
    else fall back to 60m (spec §5: 'fallback noted per-entry')."""
    for res in (preferred, "60"):
        f = store.frame(entry.symbol, res)
        if int(f["ts_ms"].iloc[0]) <= entry.entry_ts_ms <= int(f["ts_ms"].iloc[-1]):
            return res
    raise ValueError(
        f"{entry.position_id} ({entry.symbol}): no frame ({preferred}m or 60m) "
        f"covers entry ts {entry.entry_ts_ms} — genuine backfill hole, refresh it"
    )


def load_entries_from_series(series_path: str) -> list:
    """Build synthetic Entry objects from an offline_ensemble.py signal series
    (spec §5 staged item — H3 secondary run for larger n).

    Only rows where `ens_action` fired (BUY/SELL) become entries — HOLD rows
    carry no position. entry price = row `close` (the bar-close price the
    ensemble decided against, per offline_ensemble.py:416-431); quantity =
    `ens_position_size_pct * PAPER_INITIAL_BALANCE / close` (ens_position_size_pct
    is a fraction of capital, not a percent — see multi_strategy_ensemble.py:302,
    `cap = settings.max_risk_per_trade`, itself a fraction); ts = `ts_ms`.

    exit_ts_ms / actual_exit_price / actual_realized_pnl have no real value
    here (there is no recorded close for a synthetic entry) — filled with
    inert placeholders since replay_entry/run_h3 never read them for the
    replay itself. signal_confidence is repurposed to carry the row's
    `ens_confidence` (more informative than None).
    """
    df = pd.read_csv(series_path)
    fired = df[df["ens_action"].notna()].copy()
    entries = []
    for row in fired.itertuples():
        close = float(row.close)
        if not (close > 0):
            raise ValueError(
                f"{row.symbol} ts_ms={row.ts_ms}: non-positive close {close} — "
                "refusing to synthesize an entry with an invalid price"
            )
        size_pct = row.ens_position_size_pct
        if size_pct is None or pd.isna(size_pct):
            raise ValueError(
                f"{row.symbol} ts_ms={row.ts_ms}: ens_action={row.ens_action!r} "
                "fired but ens_position_size_pct is missing — series writer bug"
            )
        side = "LONG" if row.ens_action == "BUY" else "SHORT"
        quantity = float(size_pct) * PAPER_INITIAL_BALANCE / close
        entries.append(
            Entry(
                position_id=f"series-{row.symbol}-{int(row.ts_ms)}",
                symbol=row.symbol,
                side=side,
                quantity=quantity,
                entry_price=close,
                entry_ts_ms=int(row.ts_ms),
                exit_ts_ms=int(row.ts_ms) + 1,
                actual_exit_price=close,
                actual_realized_pnl=0.0,
                signal_confidence=(
                    float(row.ens_confidence)
                    if not pd.isna(row.ens_confidence)
                    else None
                ),
            )
        )
    return entries


def run_h3(
    data_dir: str,
    stop_mult: float,
    resolution: str = "15",
    fixture: str = DEFAULT_FIXTURE,
    entries: list = None,
    skip_missing_atr: bool = False,
) -> dict:
    entries = entries if entries is not None else load_entries(fixture)
    symbols = sorted({e.symbol for e in entries})
    store = CandleStore(data_dir, symbols, [resolution, "60", "1440"])
    rows = []
    truncated = 0
    fallbacks = 0
    atr_skipped = 0
    for e in entries:
        res = _pick_resolution(store, e, resolution)
        fallbacks += res != resolution
        bar_hours = INTERVAL_MS[res] / 3_600_000
        max_hold_bars = int(MAX_HOLD_HOURS * 3_600_000 / INTERVAL_MS[res])
        # Truncation at the DATA END is allowed (exits via end_of_data, counted
        # as a caveat). A frame that starts AFTER the entry is a hard abort
        # (interior hole — spec §8), handled inside _pick_resolution.
        try:
            atr = daily_atr(store, e.symbol, e.entry_ts_ms)
        except CandleValidationError:
            if not skip_missing_atr:
                raise
            # Series-sourced entries can predate the daily CSV's ATR(14)
            # warmup (first ~15 days of the backfill window). The 13-trade
            # primary fixture never does — its hard abort stays intact.
            atr_skipped += 1
            continue
        risk = stop_mult * atr
        if e.side == "LONG":
            stop, tp = e.entry_price - risk, e.entry_price + 2 * risk
        else:
            stop, tp = e.entry_price + risk, e.entry_price - 2 * risk
        out = replay_entry(e, store.frame(e.symbol, res), stop, tp, max_hold_bars)
        truncated += out.exit_reason == "end_of_data"
        notional_in = e.entry_price * e.quantity
        notional_out = out.exit_price * e.quantity
        # funding overlay (spec §5): ~0.01% of notional per 8h held (not modelled live)
        funding_est = notional_in * 0.0001 * (out.bars_held * bar_hours / 8.0)
        rows.append(
            {
                "position_id": e.position_id,
                "symbol": e.symbol,
                "side": e.side,
                "resolution": res,
                "atr_daily": atr,
                "stop": stop,
                "tp": tp,
                **asdict(out),
                "fees_modelled": (notional_in + notional_out) * MODELLED_FEE_PER_SIDE,
                "fees_bybit_est": (notional_in + notional_out) * TAKER_FEE_PER_SIDE,
                "funding_est": funding_est,
            }
        )
    if not rows:
        raise ValueError(
            f"no entries survived setup: {len(entries)} supplied, {atr_skipped} "
            "skipped for missing daily-ATR warmup, 0 replayed — nothing to "
            "measure. Widen the backfill window or check the entry source."
        )
    df = pd.DataFrame(rows)
    # HEADLINE vs TRUNCATED. A trade whose walk ran off the end of the CSV
    # (exit_reason == "end_of_data") never got an exit decision from this
    # run's rules — its outcome is an artifact of the backfill vintage, and a
    # longer CSV would score it differently. It is reported separately rather
    # than dropped. Note max_hold exits stay in the headline: the 48h cutoff
    # IS part of the exit design under test.
    truncated_mask = df["exit_reason"] == "end_of_data"
    decided = df[~truncated_mask]
    cut = df[truncated_mask]
    if decided.empty:
        raise ValueError(
            f"all {len(df)} replayed trades exited end_of_data — every window "
            "ran off the end of the CSV, so this run measures backfill length, "
            "not exit design. Refresh/extend the backfill."
        )
    stop_out_rate = float((decided["exit_reason"] == "stop_loss").mean())
    gross_expectancy = float(decided["gross_pnl"].mean())
    return {
        "stop_mult": stop_mult,
        "resolution": resolution,
        "n": len(decided),  # headline denominator
        "n_replayed": len(df),
        "stop_out_rate": stop_out_rate,
        "gross_expectancy_per_trade": gross_expectancy,
        "gross_total": float(decided["gross_pnl"].sum()),
        "net_total_modelled": float(
            (decided["gross_pnl"] - decided["fees_modelled"]).sum()
        ),
        "net_total_bybit_est": float(
            (decided["gross_pnl"] - decided["fees_bybit_est"]).sum()
        ),
        "funding_est_total": float(decided["funding_est"].sum()),
        "fees_modelled_total": float(decided["fees_modelled"].sum()),
        "fees_bybit_est_total": float(decided["fees_bybit_est"].sum()),
        # Mean single-leg notional, for the cost-vs-edge arithmetic. Derived
        # from the fee column so it stays correct if sizing changes.
        "mean_leg_notional": float(
            decided["fees_modelled"].sum() / MODELLED_FEE_PER_SIDE / len(decided) / 2
        ),
        "truncated_n": int(len(cut)),
        "truncated_gross_total": float(cut["gross_pnl"].sum()),
        "truncated_gross_expectancy": (
            float(cut["gross_pnl"].mean()) if len(cut) else 0.0
        ),
        "ambiguous_bars_total": int(df["ambiguous_bars"].sum()),
        "truncated_windows": int(truncated),
        "resolution_fallbacks": int(fallbacks),
        "atr_skipped": int(atr_skipped),
        "exit_reasons": df["exit_reason"].value_counts().to_dict(),
        "per_trade": rows,
        "accept": stop_out_rate < 0.40 and gross_expectancy > 0,
    }


def headline_accept(results: dict) -> dict:
    """Combine the per-variant accepts into the headline verdict.

    The AUDIT.md criterion is stated once, for "the" replay, with no
    either/any-variant clause. Running it at two stop multiples produces two
    independent measurements, and the honest headline is the conjunction: a
    mixed result means the criterion holds for one bracket geometry and fails
    for another, which is not "the exit design passed".

    Until 2026-08-07 this was `any(...)`. On the 2026-08-05 data both variants
    cleared, so the committed verdict happened to be correct and its caveat
    ("both clear INDEPENDENTLY ... none is invoked here") happened to be true
    of the data — but not of the code, which would have printed ACCEPT on a
    single passing variant. `accept_any` is still recorded so a reader can see
    the weaker reading was considered and rejected.
    """
    per_variant = {m: bool(r["accept"]) for m, r in results.items()}
    return {
        "per_variant": per_variant,
        "accept_all": all(per_variant.values()),
        "accept_any": any(per_variant.values()),
        "accept": all(per_variant.values()),
    }


def _vintage_caveats(test_id: str, current_sha12: str | None) -> tuple:
    """Compare this run's backfill-manifest digest against the standing verdict's.

    Returns `(caveats, narrative_valid)`. A standing verdict is committed
    evidence about a specific CSV snapshot; when the CSVs are refreshed the
    same script produces different numbers from the same fixture (observed
    2026-08-07: gross expectancy +1.2056 -> +1.0411 on the primary fixture,
    manifest cc63d3c487f1 -> e63ac88f8f9d). This does not refuse — refusing
    would make the harness unrunnable after any legitimate refresh, which is
    the opposite of "kill bad strategies cheaply" — but it makes the
    divergence impossible to miss, in the verdict and on stderr.
    """
    caveats = []
    narrative_valid = current_sha12 == NARRATIVE_MANIFEST_SHA12
    standing = latest_verdict(test_id)
    prior = (standing or {}).get("input_hashes", {}).get("backfill_manifest")
    if prior and current_sha12 and prior != current_sha12:
        msg = (
            f"INPUT VINTAGE MISMATCH: the standing {test_id} verdict "
            f"({standing.get('date')}) was computed on backfill manifest "
            f"{prior}; this run used {current_sha12}. The CSVs were refreshed "
            "between the two, so every figure below is a different measurement "
            "of the same test, not a reproduction of the standing verdict. "
            "Compare the two verdict files directly before treating either as "
            "superseded."
        )
        caveats.append(msg)
        print(f"\nWARNING: {msg}\n", file=sys.stderr)
    if not narrative_valid:
        caveats.append(
            "the standing verdict's hand-computed narrative caveats (BRACKET "
            "INERTNESS, REGIME CONCENTRATION, STALE-ENTRY CONTAMINATION) were "
            f"derived from backfill manifest {NARRATIVE_MANIFEST_SHA12} and are "
            "NOT recomputed by this script — they are omitted here because this "
            "run's inputs differ. Re-derive them by hand before reusing them."
        )
    return caveats, narrative_valid


def _cost_caveat(results: dict) -> str:
    """Gross-edge-vs-cost arithmetic, computed from the run's own numbers.

    The AUDIT.md criterion is explicitly PRE-FEE, so a positive gross
    expectancy clears it no matter how small. Whether that expectancy
    survives a round trip is a separate question the verdict file must answer
    on its own, because the verdict word at the top of the file outlives the
    commit message that once said it.
    """
    parts = []
    negative = False
    for m, r in results.items():
        edge_pct = r["gross_expectancy_per_trade"] / r["mean_leg_notional"] * 100
        rt_bybit, rt_modelled = (
            2 * TAKER_FEE_PER_SIDE * 100,
            2 * MODELLED_FEE_PER_SIDE * 100,
        )
        negative |= edge_pct < rt_bybit
        parts.append(
            f"{m}x: gross edge {edge_pct:+.4f}% of mean leg notional "
            f"(${r['mean_leg_notional']:.2f}) vs round-trip cost {rt_bybit:.3f}% "
            f"(Bybit est.) / {rt_modelled:.3f}% (modelled); total fees "
            f"${r['fees_bybit_est_total']:.2f} / ${r['fees_modelled_total']:.2f} "
            f"vs total gross ${r['gross_total']:.2f}; net "
            f"${r['net_total_bybit_est']:+.2f} / ${r['net_total_modelled']:+.2f}"
        )
    head = (
        "COST REALITY — COSTS EXCEED THE GROSS EDGE: " if negative else "COST REALITY: "
    )
    tail = (
        " ACCEPT here means the PRE-FEE criterion was not falsified; it does "
        "NOT mean this exit design is tradeable. Funding is excluded from "
        "these nets and adds further cost."
        if negative
        else ""
    )
    return head + " | ".join(parts) + "." + tail


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="backtesting/data")
    ap.add_argument("--resolution", default="15")
    ap.add_argument("--fixture", default=DEFAULT_FIXTURE)
    ap.add_argument(
        "--entries-from-series",
        default=None,
        help=(
            "Path to an offline_ensemble.py signal-series CSV. When set, entries "
            "are synthesized from every fired (BUY/SELL) row instead of the "
            "committed 13-trade fixture, and the verdict is written as "
            "'H3-secondary' — secondary evidence at larger n, never merged into "
            "the primary audit-faithful H3 verdict (spec §5 staged item)."
        ),
    )
    args = ap.parse_args()
    secondary = args.entries_from_series is not None
    entries = load_entries_from_series(args.entries_from_series) if secondary else None
    results = {
        m: run_h3(
            args.data_dir,
            m,
            args.resolution,
            args.fixture,
            entries=entries,
            skip_missing_atr=secondary,
        )
        for m in (1.5, 2.5)
    }
    decision = headline_accept(results)
    per_variant = decision["per_variant"]
    accept_all, accept_any = decision["accept_all"], decision["accept_any"]
    accept = decision["accept"]
    metrics = {
        "accept_rule": "all variants must pass (conjunction)",
        "accept_all_variants": accept_all,
        "accept_any_variant": accept_any,
    }
    for m, r in results.items():
        metrics[f"accept_{m}x"] = bool(r["accept"])
        metrics[f"stop_out_rate_{m}x"] = r["stop_out_rate"]
        metrics[f"gross_expectancy_{m}x"] = r["gross_expectancy_per_trade"]
        metrics[f"gross_total_{m}x"] = r["gross_total"]
        metrics[f"net_total_modelled_{m}x"] = r["net_total_modelled"]
        metrics[f"net_total_bybit_est_{m}x"] = r["net_total_bybit_est"]
        metrics[f"funding_est_total_{m}x"] = r["funding_est_total"]
        metrics[f"mean_leg_notional_{m}x"] = r["mean_leg_notional"]
        metrics[f"ambiguous_bars_{m}x"] = r["ambiguous_bars_total"]
        metrics[f"n_headline_{m}x"] = r["n"]
        metrics[f"n_replayed_{m}x"] = r["n_replayed"]
        # Reported, never folded into the headline — see run_h3.
        metrics[f"truncated_n_{m}x"] = r["truncated_n"]
        metrics[f"truncated_gross_total_{m}x"] = r["truncated_gross_total"]
        metrics[f"truncated_gross_expectancy_{m}x"] = r["truncated_gross_expectancy"]
        metrics[f"exit_reasons_{m}x"] = json.dumps(r["exit_reasons"], sort_keys=True)

    def _sha(p):
        return hashlib.sha256(open(p, "rb").read()).hexdigest()[:12]

    if secondary:
        input_hashes = {"signal_series": _sha(args.entries_from_series)}
    else:
        input_hashes = {"entries_fixture": _sha(args.fixture)}
    manifest = ".planning/evidence/killtests/backfill-manifest-2026-08.md"
    if os.path.exists(manifest):  # carries per-CSV digests (spec §9 input-data hash)
        input_hashes["backfill_manifest"] = _sha(manifest)

    test_id = "H3-secondary" if secondary else "H3"
    vintage, narrative_valid = _vintage_caveats(
        test_id, input_hashes.get("backfill_manifest")
    )

    common_caveats = [
        f"n={results[1.5]['n']} decided of {results[1.5]['n_replayed']} replayed "
        "— percentages describe these trades, not true rates. NOTE the headline n "
        "changed meaning on 2026-08-07 (it now excludes truncated trades), so a "
        "smaller n than an older verdict for the same inputs is a definition "
        "change, not a data change.",
        "gross P&L is pre-fee (the criterion); net shown under both fee conventions",
        "funding not modelled live; overlay estimate reported (0.01%/8h of entry notional)",
        "walk starts at first full bar after entry; partial entry bar excluded (conservative)",
        f"resolution {args.resolution}m with per-entry 60m fallback; stop-before-TP on ambiguous bars (pessimistic)",
        "TRUNCATED TRADES EXCLUDED FROM THE HEADLINE: trades whose walk ran off "
        "the end of the CSV (exit=end_of_data) got no exit decision from these "
        "rules — their outcome reflects backfill length, not exit design — so "
        "they are reported under truncated_* instead of in the headline "
        "stop-out rate / expectancy / totals. They are NOT dropped. max_hold "
        "exits DO stay in the headline: the 48h cutoff is part of the exit "
        f"design under test. Counts: { {m: r['truncated_n'] for m, r in results.items()} }",
        f"resolution fallbacks to 60m: { {m: r['resolution_fallbacks'] for m, r in results.items()} }",
        f"VERDICT RULE: headline ACCEPT requires EVERY stop-multiple variant to "
        f"clear both criterion legs. Per-variant: {per_variant} "
        f"(accept_all={accept_all}, accept_any={accept_any}). The AUDIT.md "
        "criterion has no either/any-variant clause, so a mixed result is REJECT.",
        _cost_caveat(results),
    ] + vintage

    criterion = (
        'AUDIT.md:261 verbatim — "stop-out rate <40% AND gross expectancy >0 pre-fee"'
    )
    if secondary:
        caveats = common_caveats + [
            "regenerated entries — secondary evidence, never merged into the "
            "primary n=13 verdict",
            "entries synthesized from the offline ensemble's own fired signals "
            "(entry price = signal-bar close, quantity = ens_position_size_pct * "
            "PAPER_INITIAL_BALANCE / close) — this measures the SAME ATR-bracket "
            "exit design against a much larger, ensemble-generated entry set, not "
            "an independent confirmation of the 13 real paper trades",
            f"entries predating daily ATR(14) warmup skipped (first ~15 days of "
            f"the backfill window): "
            f"{ {m: r['atr_skipped'] for m, r in results.items()} }",
        ]
    else:
        # Hand-derived findings about the 2026-08-05 snapshot, not recomputed
        # here — emitted only while the inputs still match (see _vintage_caveats).
        caveats = common_caveats + (
            [
                "BRACKET INERTNESS: zero take-profit touches across all 26 outcomes "
                "(13 trades x 2 variants). Max favorable excursion across the 13 trades is "
                "2.64 ATR, below the 3.0 ATR (1.5x) and 5.0 ATR (2.5x) TP requirement in "
                "both variants — no trade could reach TP either way. Widening the stop 67% "
                "(1.5x to 2.5x) changed exactly 1 of 26 outcomes. The brackets almost never "
                "bind: this test primarily measures 48h directional drift of the recorded "
                'entries, not ATR bracket design. Read ACCEPT as "not falsified by this '
                'sample", not "brackets validated".',
                "REGIME CONCENTRATION: 10 of 13 entries are LONG, contributing +14.67 of "
                "+15.67 total gross, all within one week (2026-07-29 to 2026-08-05) of a "
                "rising tape; the top 4 trades carry 82% of gross.",
                "STALE-ENTRY CONTAMINATION (reviewer-computed): trades 11 (SOLUSDT LONG, "
                "recorded entry 71.04 vs true market 73.59) and 12 (BNBUSDT LONG, recorded "
                "576.3 vs true market 589.7), both opened 2026-08-04 14:10:3x, were booked "
                "at prices the market had not traded for 60+ hours (stuck-ticker gotcha, "
                "CLAUDE.md section 10) — the paper engine itself recorded the phantom P&L "
                "upstream of this replay. $4.37 of $15.67 total gross is phantom. Repricing "
                "both at the true close of their entry bar (reviewer calculation, not "
                "recomputed by this script): gross +15.67 -> +11.30, expectancy "
                "+1.2056 -> +0.8691 for the 1.5x variant — ACCEPT still clears both "
                "criterion legs after repricing. The bias is directional (stale-low longs "
                "in a rising tape) and will not average out at larger n. This is an "
                "upstream H1/H2 data-quality issue, not something this replay fixes.",
            ]
            if narrative_valid
            else []
        )

    path = write_verdict(
        test_id,
        "ACCEPT" if accept else "REJECT",
        criterion,
        metrics=metrics,
        caveats=caveats,
        config={
            "stop_mults": [1.5, 2.5],
            "tp_r_multiple": 2.0,
            "max_hold_hours": MAX_HOLD_HOURS,
            "atr_period": 14,
            "initial_capital_source": f"shared.account ({PAPER_INITIAL_BALANCE})",
            "entries_source": (args.entries_from_series if secondary else args.fixture),
        },
        input_hashes=input_hashes,
        tables={f"per_trade_{m}x": r["per_trade"] for m, r in results.items()},
    )
    print(
        f"{test_id} verdict: {'ACCEPT' if accept else 'REJECT'} (all variants "
        f"must pass; accept_any would be {accept_any}) -> {path}"
    )
    for m, r in results.items():
        print(
            f"  {m}x: stop-out {r['stop_out_rate']:.1%}, "
            f"gross expectancy {r['gross_expectancy_per_trade']:+.4f}, "
            f"accept={r['accept']} (n={r['n']} decided, {r['truncated_n']} truncated)"
        )


if __name__ == "__main__":
    main()
