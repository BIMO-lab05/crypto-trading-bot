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
from edge_lab.fetch import funding_csv_path, kline_csv_path  # noqa: E402
from edge_lab.gate1 import run_gate1  # noqa: E402
from edge_lab.gate2 import Gate2Result, daily_returns_from_trades, run_gate2  # noqa: E402
from edge_lab.sanity import (  # noqa: E402
    SanityReport,
    check_funding,
    check_klines,
    render_sanity_table,
)
from edge_lab.trades import Trade, write_trades_csv  # noqa: E402
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


def read_kline_csv(path: Path) -> pd.DataFrame:
    """The on-disk kline CSV back into the `ts_ms` frame candidates expect.

    `ensure_klines` writes a `timestamp` column, not `ts_ms`. Pandas 3 parses
    it to `datetime64[us]`, so the obvious `astype("int64") // 1_000_000`
    yields SECONDS and every downstream day-number is wrong by a factor of
    1000 — with no exception raised anywhere. Casting to `datetime64[ms]`
    first pins the unit regardless of what the parser chose.
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
    return df.sort_values("ts_ms").reset_index(drop=True)


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


def load_bundle(data_dir: Path, pin: Mapping) -> tuple[dict[str, dict], str]:
    """Gate 0 over every pinned symbol, then the surviving data bundle.

    Returns `({"daily": ..., "h4": ..., "funding": ...}, sanity_summary)`.
    A symbol with a kline defect on EITHER interval is dropped from all
    three dicts — data this battery cannot trust on one timeframe is not
    trusted on another — and named in the summary. A merely absent 4h file
    is not a defect: it is named, and the symbol keeps its daily entry, so
    a daily candidate is not punished for a 4h file nobody fetched.

    Missing funding never drops a symbol (`sanity.check_funding`'s contract);
    it surfaces as `funding_ok=False` and, downstream, as the verdict's
    funding-exclusion caveat.
    """
    data_dir = Path(data_dir)
    symbols = [s["symbol"] for s in pin.get("symbols", [])]

    daily: dict[str, pd.DataFrame] = {}
    h4: dict[str, pd.DataFrame] = {}
    funding: dict[str, pd.DataFrame] = {}
    reports: list[SanityReport] = []
    notes: list[str] = []
    dropped: set[str] = set()

    for symbol in symbols:
        d_path = kline_csv_path(data_dir, symbol, DAILY_INTERVAL, DAILY_LOOKBACK_DAYS)
        if not d_path.is_file():
            reports.append(_missing_file_report(symbol, DAILY_INTERVAL, d_path))
            dropped.add(symbol)
            continue

        d_df = read_kline_csv(d_path)
        d_report = check_klines(d_df, symbol, DAILY_INTERVAL)

        f_path = funding_csv_path(data_dir, symbol)
        if f_path.is_file():
            f_df = pd.read_csv(f_path)
            funding[symbol] = f_df
            d_report.funding_ok, d_report.funding_n = check_funding(
                f_df, DAILY_LOOKBACK_DAYS
            )
        else:
            notes.append(f"{symbol} funding: no CSV at {f_path} — funding EXCLUDED")
        reports.append(d_report)
        if not d_report.ok:
            dropped.add(symbol)
        else:
            daily[symbol] = d_df

        h_path = kline_csv_path(data_dir, symbol, H4_INTERVAL, H4_LOOKBACK_DAYS)
        if not h_path.is_file():
            notes.append(
                f"{symbol} [{H4_INTERVAL}] no kline CSV at {h_path} — "
                "4h candidates skip this symbol (not a Gate 0 defect)"
            )
            continue
        h_df = read_kline_csv(h_path)
        h_report = check_klines(h_df, symbol, H4_INTERVAL)
        # Funding is per symbol, not per interval. Leaving the 4h row at the
        # dataclass default would print funding_ok=False directly beneath the
        # same symbol's daily row saying True — a contradiction that reads as
        # missing data.
        h_report.funding_ok, h_report.funding_n = (
            d_report.funding_ok,
            d_report.funding_n,
        )
        reports.append(h_report)
        if not h_report.ok:
            dropped.add(symbol)
        else:
            h4[symbol] = h_df

    for symbol in dropped:
        daily.pop(symbol, None)
        h4.pop(symbol, None)
        funding.pop(symbol, None)

    summary_lines = [render_sanity_table(reports)] if reports else []
    summary_lines.extend(notes)
    summary_lines.append(
        f"pinned={len(symbols)} kept_daily={len(daily)} kept_h4={len(h4)} "
        f"funding_series={len(funding)} dropped="
        + (", ".join(sorted(dropped)) if dropped else "none")
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
    """
    if entry.get("import_error"):
        raise ImportError(entry["import_error"])
    if "generate" in entry:
        return entry["generate"](bundle, variant)
    args = [bundle[key] for key in entry["inputs"]]
    return entry["module"].generate_trades(*args, variant)


def score_gate2(
    trades: Sequence[Trade],
    daily: Mapping[str, pd.DataFrame],
    candidate: str,
    funding_dir: Path,
) -> tuple[Gate2Result, int, int, int]:
    """Daily net-return series → CPCV/DSR. Returns (result, start, end, h).

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
    """
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
    return run_gate2(returns, horizon), start_ms, end_ms, horizon


def _score_variant(
    entry: Mapping,
    bundle: Mapping,
    variant,
    candidate: str,
    out_dir: Path,
    funding_dir: Path,
) -> dict[str, Any]:
    trades = _generate(entry, bundle, variant)
    csv_path = Path(out_dir) / "trades" / f"{candidate}_{variant.name}.csv"
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

    gate2, start_ms, end_ms, horizon = score_gate2(
        trades, bundle["daily"], candidate, funding_dir
    )
    record.update(
        dsr=gate2.dsr,
        pooled_pf=gate2.pooled_pf,
        positive_path_frac=gate2.positive_path_frac,
        n_paths_valid=gate2.n_paths_valid,
        n_samples=gate2.n_samples,
        sharpe_mean=gate2.sharpe_mean,
        sharpe_std=gate2.sharpe_std,
        gate2_passed=gate2.passed,
        gate2_reasons=list(gate2.reasons),
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
    bundle, sanity_summary = load_bundle(data_dir, pin)
    registry = default_registry() if candidates is None else candidates

    results: dict[str, dict] = {}
    for candidate, entry in registry.items():
        result: dict[str, Any] = {"variants": [], "verdict": "REJECT"}
        try:
            for variant in entry["variants"]:
                result["variants"].append(
                    _score_variant(
                        entry, bundle, variant, candidate, out_dir, funding_dir
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
                    candidate, result["variants"], pin, sanity_summary, date_str
                ),
                candidate,
                date_str,
                out_dir,
            )
            write_verdict_json(candidate, result["variants"], pin, date_str, out_dir)
        except Exception:
            logger.exception("failed to write the %s verdict doc", candidate)
            result["doc_error"] = traceback.format_exc()

    write_summary(
        render_summary(results, pin, sanity_summary, date_str), date_str, out_dir
    )
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
        help="YYYY-MM-DD run date; sets the data cutoff and names the docs",
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
