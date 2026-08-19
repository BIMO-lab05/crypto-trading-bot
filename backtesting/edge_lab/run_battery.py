"""Battery orchestrator — Gate 0 → candidates → Gate 1 → Gate 2 → verdicts.

Pure orchestration and network-free: every CSV it reads must already be on
disk (`edge_lab.fetch.ensure_klines` / `ensure_funding` put them there). It
reads klines through `fetch.kline_csv_path` with the lookbacks pinned in
`edge_lab.config`, deliberately NOT through `killtests`' CandleStore, which
hard-codes 365-day filenames and would silently miss the 730-day daily
files this battery is built on.

Crash isolation is the load-bearing property: a candidate that raises
anywhere — importing its module, generating trades, screening, or scoring —
records `{"error": traceback}` and its loop moves on. Every other candidate
still runs and every verdict doc still gets written. The battery always
completes, because a battery that dies on candidate 2 of 4 is worse than
useless: it looks like a result.

Zero-trade variants are recorded, never screened. `screen.screen_trades`
raises on an empty trade list by design ("a vacuous PASS on zero trades is
the single most dangerous output this module could produce"), so a variant
that generated nothing is written to `gate1_verdict="NO_TRADES"` directly.
Its header-only CSV is still written, so the artifact set has no holes.
"""

from __future__ import annotations

import sys
from pathlib import Path

# killtests/*.py and costs_loader/screen use absolute imports rooted at
# `backtesting/`, and edge_lab.config reads `shared.account` from the repo
# root. Boot both before any edge_lab import so `python3
# backtesting/edge_lab/run_battery.py` works as directly as `-m` does.
_BACKTESTING = str(Path(__file__).resolve().parents[1])
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_BACKTESTING, _REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import argparse  # noqa: E402
import importlib  # noqa: E402
import logging  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from decimal import Decimal  # noqa: E402
from typing import Any, Mapping, Sequence  # noqa: E402

import pandas as pd  # noqa: E402
from costs_loader import load_costs, load_funding  # noqa: E402

from edge_lab.config import (  # noqa: E402
    DAILY_INTERVAL,
    DAILY_LOOKBACK_DAYS,
    H4_INTERVAL,
    H4_LOOKBACK_DAYS,
    SLIPPAGE_BPS,
    SLIPPAGE_FALLBACK_BPS,
)
from edge_lab.fetch import (  # noqa: E402
    funding_csv_path,
    interval_ms,
    kline_csv_path,
)
from edge_lab.gate1 import run_gate1  # noqa: E402
from edge_lab.gate2 import Gate2Result, daily_returns_from_trades, run_gate2  # noqa: E402
from edge_lab.sanity import (  # noqa: E402
    SanityReport,
    check_funding,
    check_klines,
    render_sanity_table,
)
from edge_lab.trades import Trade, write_trades_csv  # noqa: E402
from edge_lab import trial_ledger  # noqa: E402
from edge_lab.universe import load_pin  # noqa: E402
from edge_lab.verdicts import (  # noqa: E402
    overall_verdict,
    render_summary,
    render_verdict,
    write_summary,
    write_verdict,
    write_verdict_json,
)

logger = logging.getLogger(__name__)

DAY = 86_400_000

# CPCV purge/embargo horizon per candidate — the holding period each one's
# label spans. Wrong here means purging the wrong amount of data around each
# test fold, so it is pinned rather than inferred from realized holds.
LABEL_HORIZONS = {
    "xs_momentum": 7,
    "funding_carry": 10,
    "lf_trend": 30,
    "vol_breakout": 5,
    "pairs_statarb": 2,
}
# Only reachable for a candidate outside the registry (a test stub). Named
# and warned about rather than silently assumed.
DEFAULT_LABEL_HORIZON_DAYS = 7

# name -> (module path, bundle keys its generate_trades takes, in order)
_CANDIDATE_SPECS = (
    ("xs_momentum", "edge_lab.candidates.xs_momentum", ("daily",)),
    ("funding_carry", "edge_lab.candidates.funding_carry", ("daily", "funding")),
    ("lf_trend", "edge_lab.candidates.lf_trend", ("daily",)),
    ("vol_breakout", "edge_lab.candidates.vol_breakout", ("h4",)),
    ("pairs_statarb", "edge_lab.candidates.pairs_statarb", ("daily",)),
)

_costs = load_costs()


def default_registry() -> dict[str, dict]:
    """The four real candidates. A module that fails to import becomes an
    entry carrying its traceback, so the failure surfaces as that
    candidate's ERROR verdict instead of killing the battery at import."""
    registry: dict[str, dict] = {}
    for name, module_path, inputs in _CANDIDATE_SPECS:
        try:
            module = importlib.import_module(module_path)
            registry[name] = {
                "variants": list(module.VARIANTS),
                "module": module,
                "inputs": inputs,
            }
        except Exception:
            logger.exception("candidate %s failed to import", name)
            registry[name] = {
                "variants": [],
                "inputs": inputs,
                "import_error": traceback.format_exc(),
            }
    return registry


def date_str_from_ms(now_ms: int) -> str:
    return datetime.fromtimestamp(now_ms // 1000, tz=timezone.utc).strftime("%Y%m%d")


def _iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms // 1000, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )


def read_kline_csv(path: Path, interval: str, now_ms: int) -> pd.DataFrame:
    """The on-disk kline CSV back into the `ts_ms` frame candidates expect.

    `ensure_klines` writes a `timestamp` column, not `ts_ms`. Pandas 3 parses
    it to `datetime64[us]`, so the obvious `astype("int64") // 1_000_000`
    yields SECONDS and every downstream day-number is wrong by a factor of
    1000 — with no exception raised anywhere. Casting to `datetime64[ms]`
    first pins the unit regardless of what the parser chose.

    Rows are then cut at the run's `now_ms` using the same rule
    `fetch.fetch_klines` applies at download time — a bar counts only once
    it has CLOSED (`ts_ms + interval <= now_ms`). This is what makes `--date`
    an actual data cutoff: re-running an earlier date against a CSV that has
    since been extended reproduces the earlier run, and a still-forming final
    bar can never contribute a partial close as if it were final.

    Returned in FILE ORDER, not sorted. Sorting here would permanently
    disarm `check_klines`' monotonicity check, which exists precisely to
    catch a CSV whose rows are out of order. The caller sorts after checking.
    """
    raw = pd.read_csv(path)
    ts = pd.to_datetime(raw["timestamp"]).astype("datetime64[ms]").astype("int64")
    df = pd.DataFrame(
        {
            "ts_ms": ts,
            "open": raw["open"].astype(float),
            "high": raw["high"].astype(float),
            "low": raw["low"].astype(float),
            "close": raw["close"].astype(float),
            "volume": raw["volume"].astype(float),
            "turnover": (
                raw["turnover"] if "turnover" in raw.columns else raw["volume"]
            ).astype(float),
        }
    )
    closed = df["ts_ms"] + interval_ms(interval) <= now_ms
    return df[closed].reset_index(drop=True)


def _missing_file_report(symbol: str, interval: str, path: Path) -> SanityReport:
    return SanityReport(
        symbol=symbol,
        interval=interval,
        ok=False,
        n_bars=0,
        first_ts_ms=0,
        last_ts_ms=0,
        gaps=[],
        defects=[f"no kline CSV at {path}"],
    )


def load_bundle(
    data_dir: Path, pin: Mapping, now_ms: int
) -> tuple[dict[str, dict], str]:
    """Gate 0 over every pinned symbol, then the surviving data bundle.

    Returns `({"daily": ..., "h4": ..., "funding": ...}, sanity_summary)`.

    Drops are scoped to the interval that failed. A 4h defect costs the
    symbol its 4h entry only; its daily bars are still trustworthy and the
    daily candidates still trade it. A daily defect drops the daily entry
    AND the funding series, because funding_carry times its entries off
    daily bars — a funding series with no bars to trade against is not a
    usable input. The earlier all-three rule punished daily candidates for a
    4h problem and, worse, rewarded fetching *less* data: a symbol with no
    4h file at all kept everything, while one with a fetched-but-flawed 4h
    file lost its daily entry too.

    A merely absent file is not a defect — it is named, and costs only the
    interval it belongs to. A symbol with no daily CSV but a clean 4h one
    still reaches the 4h candidates, and still gets a 4h sanity row. Missing
    funding never drops anything (`sanity.check_funding`'s contract); it
    surfaces as `funding_ok=False` and, downstream, as the verdict's
    funding-exclusion caveat.

    Every drop is named per interval in the summary. No silent shrinkage.
    """
    data_dir = Path(data_dir)
    symbols = [s["symbol"] for s in pin.get("symbols", [])]

    daily: dict[str, pd.DataFrame] = {}
    h4: dict[str, pd.DataFrame] = {}
    funding: dict[str, pd.DataFrame] = {}
    reports: list[SanityReport] = []
    notes: list[str] = []
    dropped_daily: set[str] = set()
    dropped_h4: set[str] = set()

    for symbol in symbols:
        # Funding is per symbol, not per interval, so it is resolved once
        # up front and stamped onto BOTH interval rows. Reading it inside
        # the daily branch would leave the 4h row at the dataclass default,
        # printing funding_ok=False directly beneath the same symbol's daily
        # row saying True — a contradiction that reads as missing data.
        funding_ok, funding_n = False, 0
        f_path = funding_csv_path(data_dir, symbol)
        if f_path.is_file():
            f_df = pd.read_csv(f_path)
            # Same cutoff as the klines. Settlements at or after now_ms are
            # not observable at the cutoff, and funding_carry's signal reads
            # this frame directly. Gate 1 and Gate 2 re-read the unfiltered
            # CSV through costs_loader.load_funding, which is harmless: both
            # only account settlements falling INSIDE a trade's window, and
            # every trade is generated from cut klines, so it ends before
            # now_ms. No post-cutoff settlement can reach either.
            f_df = f_df[f_df["ts_ms"] < now_ms].reset_index(drop=True)
            funding[symbol] = f_df
            funding_ok, funding_n = check_funding(f_df, DAILY_LOOKBACK_DAYS)
        else:
            notes.append(f"{symbol} funding: no CSV at {f_path} — funding EXCLUDED")

        # The two intervals are resolved independently. Neither branch may
        # `continue`: an absent daily file used to skip the 4h block
        # entirely, costing the symbol its 4h entry AND its 4h sanity row
        # even when the 4h file was present and clean — the same
        # cross-interval punishment the per-interval rule removed, running
        # the other way.
        d_path = kline_csv_path(data_dir, symbol, DAILY_INTERVAL, DAILY_LOOKBACK_DAYS)
        if not d_path.is_file():
            d_report = _missing_file_report(symbol, DAILY_INTERVAL, d_path)
            dropped_daily.add(symbol)
        else:
            d_df = read_kline_csv(d_path, DAILY_INTERVAL, now_ms)
            d_report = check_klines(d_df, symbol, DAILY_INTERVAL)
            if d_report.ok:
                daily[symbol] = d_df.sort_values("ts_ms").reset_index(drop=True)
            else:
                dropped_daily.add(symbol)
        d_report.funding_ok, d_report.funding_n = funding_ok, funding_n
        reports.append(d_report)

        h_path = kline_csv_path(data_dir, symbol, H4_INTERVAL, H4_LOOKBACK_DAYS)
        if not h_path.is_file():
            notes.append(
                f"{symbol} [{H4_INTERVAL}] no kline CSV at {h_path} — "
                "4h candidates skip this symbol (not a Gate 0 defect)"
            )
        else:
            h_df = read_kline_csv(h_path, H4_INTERVAL, now_ms)
            h_report = check_klines(h_df, symbol, H4_INTERVAL)
            h_report.funding_ok, h_report.funding_n = funding_ok, funding_n
            reports.append(h_report)
            if h_report.ok:
                h4[symbol] = h_df.sort_values("ts_ms").reset_index(drop=True)
            else:
                dropped_h4.add(symbol)

    for symbol in dropped_daily:
        daily.pop(symbol, None)
        funding.pop(symbol, None)
    for symbol in dropped_h4:
        h4.pop(symbol, None)

    summary_lines = [render_sanity_table(reports)] if reports else []
    summary_lines.extend(notes)
    summary_lines.append(
        f"pinned={len(symbols)} kept_daily={len(daily)} kept_h4={len(h4)} "
        f"funding_series={len(funding)} "
        f"dropped_daily=[{', '.join(sorted(dropped_daily))}] "
        f"dropped_h4=[{', '.join(sorted(dropped_h4))}]"
    )
    bundle = {"daily": daily, "h4": h4, "funding": funding}
    return bundle, "\n".join(line for line in summary_lines if line)


def round_trip_bps(symbol: str) -> Decimal:
    """Taker/taker round-trip cost, same table Gate 1 screens against."""
    return _costs.round_trip_cost_bps(
        symbol,
        entry_liquidity=_costs.Liquidity.TAKER,
        exit_liquidity=_costs.Liquidity.TAKER,
        schedule=_costs.FeeSchedule.bybit_linear_perp(),
        slippage_table=SLIPPAGE_BPS,
        slippage_fallback=SLIPPAGE_FALLBACK_BPS,
    )


def _generate(entry: Mapping, bundle: Mapping, variant) -> list[Trade]:
    """Adapter over the candidates' differing signatures.

    A registry entry with a `generate` key is a test stub and gets the whole
    bundle; a real entry names the bundle keys its module's
    `generate_trades` takes positionally.

    An `import_error` entry never reaches here — `run_battery` raises on it
    before the variant loop, because such an entry has no variants to loop
    over. A guard in this function would be dead code.
    """
    if "generate" in entry:
        return entry["generate"](bundle, variant)
    args = [bundle[key] for key in entry["inputs"]]
    return entry["module"].generate_trades(*args, variant)


def score_gate2(
    trades: Sequence[Trade],
    daily: Mapping[str, pd.DataFrame],
    candidate: str,
    funding_dir: Path,
    num_trials_floor: int,
) -> tuple[Gate2Result, int, int, int, dict[str, int]]:
    """Daily net-return series → CPCV/DSR. Returns (result, start, end, h, dropped).

    Window runs from the first trade's entry to the end of the daily data
    (or the last exit, whichever is later, so no exit-day P&L is truncated).
    Starting at the first entry rather than at the start of the daily
    history keeps a 4h candidate from being charged ~365 days of "flat"
    that are really just days its 4h feed did not cover — a data-coverage
    artifact, not capital utilization. Flat days AFTER the first trade are
    kept at 0.0, which is what makes the Sharpe honest about utilization.

    `daily_closes` is the full loaded daily history, which therefore extends
    before the window start — `daily_returns_from_trades`' caller contract,
    since an intermediate holding day reads `close[day - 1]`.

    Gate 2 is a DAILY-return measure, but `load_bundle` keeps a symbol whose
    4h bars are clean even when its daily bars are absent, so a 4h candidate
    can legitimately trade a symbol Gate 2 has no closes for. Those trades
    are DROPPED from the scoring rather than scored against fabricated
    closes — resampling 4h bars into a synthetic daily series would invent
    the very prices the gate is meant to test against. The dropped symbols
    and their trade counts are logged and returned so the verdict records
    what was not measured. Dropping ALL of them raises instead: a variant
    scored on nothing is a data failure, and filing it as a REJECT would
    render a data outage as a finding about the candidate.
    """
    scored: list[Trade] = []
    dropped: dict[str, int] = {}
    for t in trades:
        if t.symbol in daily:
            scored.append(t)
        else:
            dropped[t.symbol] = dropped.get(t.symbol, 0) + 1
    if dropped:
        logger.warning(
            "%s: dropping %d of %d trades from Gate 2 — no daily frame for %s "
            "(4h-only symbols; Gate 2 scores daily returns and will not "
            "fabricate closes from 4h bars)",
            candidate,
            sum(dropped.values()),
            len(trades),
            ", ".join(f"{sym} ({n} trades)" for sym, n in sorted(dropped.items())),
        )
    if not scored:
        raise RuntimeError(
            f"every one of the {len(trades)} {candidate} trades is on a symbol "
            "with no daily frame "
            f"({', '.join(f'{s} ({n} trades)' for s, n in sorted(dropped.items()))})"
            " — Gate 2 has nothing to score, so this is a data failure, not a "
            f"finding about {candidate}."
        )
    trades = scored

    # Derived from the SURVIVING trades, not the originals: a dropped
    # symbol must not set the window start, and building the cost map here
    # is what keeps gate2's hard `cost_bps_rt[symbol]` lookup total.
    symbols = {t.symbol for t in trades}
    cost_bps_rt = {symbol: round_trip_bps(symbol) for symbol in symbols}
    funding = {symbol: load_funding(symbol, str(funding_dir)) for symbol in symbols}

    start_ms = min(t.entry_ts_ms for t in trades)
    data_end = max(
        (int(df["ts_ms"].iloc[-1]) for df in daily.values() if len(df)),
        default=start_ms,
    )
    end_ms = max(data_end, max(t.exit_ts_ms for t in trades))

    returns = daily_returns_from_trades(
        trades, daily, start_ms, end_ms, cost_bps_rt, funding
    )
    horizon = LABEL_HORIZONS.get(candidate)
    if horizon is None:
        horizon = DEFAULT_LABEL_HORIZON_DAYS
        logger.warning(
            "candidate %s is not in LABEL_HORIZONS — using the %d-day default",
            candidate,
            horizon,
        )
    return (
        run_gate2(returns, horizon, num_trials_floor=num_trials_floor),
        start_ms,
        end_ms,
        horizon,
        dropped,
    )


def _score_variant(
    entry: Mapping,
    bundle: Mapping,
    variant,
    candidate: str,
    out_dir: Path,
    funding_dir: Path,
    num_trials_floor: int,
    date_str: str,
) -> dict[str, Any]:
    trades = _generate(entry, bundle, variant)
    csv_path = Path(out_dir) / "trades" / date_str / f"{candidate}_{variant.name}.csv"
    write_trades_csv(trades, csv_path)

    record: dict[str, Any] = {
        "variant": variant.name,
        "params": {str(k): str(v) for k, v in variant.params},
        "n_trades": len(trades),
        "trades_csv": str(csv_path),
        "gate2_passed": None,
    }

    if not trades:
        # screen_trades raises on an empty list by design — record, never call.
        record["gate1_verdict"] = "NO_TRADES"
        record["gate2_passed"] = False
        return record

    screened = run_gate1(csv_path, funding_dir)
    record.update(
        gate1_verdict=screened.verdict,
        gross_edge_bps=screened.gross_edge_bps,
        cost_bps_taker=screened.cost_bps_taker,
        cost_bps_maker=screened.cost_bps_maker,
        ratio_taker=screened.ratio_taker,
        ratio_maker=screened.ratio_maker,
        net_taker=screened.net_taker,
        funding_total=screened.funding_total,
        funding_missing=list(screened.funding_symbols_missing),
        notional_provenance=screened.notional_provenance,
    )
    if screened.verdict != "PASS":
        record["gate2_passed"] = False
        return record

    gate2, start_ms, end_ms, horizon, dropped = score_gate2(
        trades, bundle["daily"], candidate, funding_dir, num_trials_floor
    )
    record.update(
        # Trades Gate 2 could not score for want of a daily frame. Recorded
        # even when empty, so a reader can tell "none dropped" from "this
        # run predates the field". Reaches the JSON verdict via
        # write_verdict_json's wholesale variant dump.
        gate2_trades_dropped_no_daily=dict(sorted(dropped.items())),
        gate2_n_trades_scored=len(trades) - sum(dropped.values()),
        dsr=gate2.dsr,
        pooled_pf=gate2.pooled_pf,
        positive_path_frac=gate2.positive_path_frac,
        n_paths_valid=gate2.n_paths_valid,
        n_samples=gate2.n_samples,
        sharpe_mean=gate2.sharpe_mean,
        sharpe_std=gate2.sharpe_std,
        gate2_passed=gate2.passed,
        gate2_reasons=list(gate2.reasons),
        num_trials_used=gate2.num_trials_used,
        label_horizon_days=horizon,
        window_start_ms=start_ms,
        window_end_ms=end_ms,
        window_start_iso=_iso(start_ms),
        window_end_iso=_iso(end_ms),
    )
    return record


def run_battery(
    data_dir: Path,
    pin_path: Path,
    out_dir: Path,
    now_ms: int,
    candidates: dict | None = None,
) -> dict:
    """Run every candidate end to end and write the evidence.

    Consumes the universe pin only — selecting or re-pinning a universe
    mid-battery would silently change what the verdicts are about.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = date_str_from_ms(now_ms)
    funding_dir = Path(data_dir) / "funding"

    pin = load_pin(pin_path)
    bundle, sanity_summary = load_bundle(data_dir, pin, now_ms)
    registry = default_registry() if candidates is None else candidates

    known = {(e["candidate"], e["variant"]) for e in trial_ledger.load_entries()}
    scored = {(c, v.name) for c, e in registry.items() for v in e["variants"]}
    total_new_variants = len(scored - known)
    effective_floor = trial_ledger.effective_trials_floor(total_new_variants)

    results: dict[str, dict] = {}
    for candidate, entry in registry.items():
        result: dict[str, Any] = {"variants": [], "verdict": "REJECT"}
        try:
            # A candidate whose required bundle dicts are empty would
            # generate zero trades and be filed as a clean REJECT — a data
            # outage rendered as an honest-looking "no edge" finding, the
            # worst output this battery could produce. Keyed per candidate
            # off its declared inputs, not off the whole bundle: a
            # daily-only outage must not be survivable just because the 4h
            # dict is still populated for vol_breakout.
            starved = [key for key in entry.get("inputs", ()) if not bundle.get(key)]
            if starved:
                raise RuntimeError(
                    "no usable data for required interval(s): "
                    f"{', '.join(starved)} — Gate 0 left them empty, so this "
                    f"is a data failure, not a finding about {candidate}."
                    f"\n\n{sanity_summary}"
                )
            # Catch-all for entries that declare no inputs (test stubs get
            # the whole bundle, so their requirement is unknowable here).
            if not any(bundle.values()):
                raise RuntimeError(
                    "no usable data after Gate 0 — every pinned symbol was "
                    "dropped or absent, so this is a data failure, not a "
                    f"finding about {candidate}.\n\n{sanity_summary}"
                )
            # An entry whose module failed to import carries the traceback
            # and no variants. Checked HERE, not inside the variant loop: an
            # empty variants list never enters that loop, so the failure used
            # to fall through to a REJECT verdict indistinguishable from a
            # real loss, with the traceback sitting unused in the registry.
            if entry.get("import_error"):
                raise ImportError(entry["import_error"])
            for variant in entry["variants"]:
                result["variants"].append(
                    _score_variant(
                        entry,
                        bundle,
                        variant,
                        candidate,
                        out_dir,
                        funding_dir,
                        effective_floor,
                        date_str,
                    )
                )
            result["verdict"] = overall_verdict(result["variants"])
        except Exception:
            tb = traceback.format_exc()
            logger.exception("candidate %s failed", candidate)
            result["error"] = tb
            result["variants"].append({"error": tb})
            result["verdict"] = "ERROR"
        results[candidate] = result

        # Written per candidate, as it finishes: a doc-writing failure must
        # not cost the candidates that already succeeded.
        try:
            write_verdict(
                render_verdict(
                    candidate,
                    result["variants"],
                    pin,
                    sanity_summary,
                    date_str,
                    num_trials_floor=effective_floor,
                ),
                candidate,
                date_str,
                out_dir,
            )
            write_verdict_json(
                candidate,
                result["variants"],
                pin,
                date_str,
                out_dir,
                num_trials_floor=effective_floor,
            )
        except Exception:
            logger.exception("failed to write the %s verdict doc", candidate)
            result["doc_error"] = traceback.format_exc()

        # Ledgered per candidate, not per battery: a battery that dies on a
        # later candidate must not cost the ledger entries for the ones that
        # already scored. Covers NO_TRADES and Gate-1 KILL variants too, not
        # just PASS — every variant this battery actually scored is a spent
        # trial.
        try:
            trial_ledger.append_entries(
                [
                    {"candidate": candidate, "variant": v.get("variant")}
                    for v in result["variants"]
                    if v.get("variant") is not None
                ]
            )
        except Exception:
            logger.exception("failed to append %s to the trial ledger", candidate)
            result["ledger_error"] = traceback.format_exc()

    # Last hole in "the battery always completes": by here every verdict doc
    # is already on disk, so a summary that fails to render must not take the
    # results down with it.
    try:
        write_summary(
            render_summary(
                results,
                pin,
                sanity_summary,
                date_str,
                num_trials_floor=effective_floor,
            ),
            date_str,
            out_dir,
        )
    except Exception:
        logger.exception("failed to write the battery summary")

    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the edge research battery over already-fetched CSVs"
    )
    parser.add_argument("--data-dir", default="backtesting/data")
    parser.add_argument("--pin", required=True, help="universe_<date>.json")
    parser.add_argument("--out", default=".planning/evidence/killtests")
    parser.add_argument(
        "--date",
        default=None,
        help=(
            "YYYY-MM-DD; cuts the data at that day's 00:00 UTC — kline bars "
            "that have not closed by then and funding settlements at or "
            "after it are dropped, so re-running an earlier date against a "
            "since-extended CSV reproduces the earlier run. Also names the "
            "output docs. Defaults to now."
        ),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    if args.date:
        day = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now_ms = int(day.timestamp() * 1000)
    else:
        now_ms = int(time.time() * 1000)

    results = run_battery(Path(args.data_dir), Path(args.pin), Path(args.out), now_ms)
    for candidate, result in results.items():
        logger.info("%s: %s", candidate, result["verdict"])

    # Non-zero on any ERROR. The battery deliberately completes through a
    # candidate failure, so without this an operator or CI job reads a clean
    # exit over a run that never scored part of its search space.
    errored = [name for name, res in results.items() if res["verdict"] == "ERROR"]
    if errored:
        logger.error("ERROR verdicts: %s — see the verdict docs", ", ".join(errored))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
