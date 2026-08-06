"""H4 kill test: does the deployed ensemble signal carry information?

AUDIT.md:262 — every ensemble signal vs sign of 24h forward log-return.
Accept: directional accuracy > 50% AND DSR > 0.95, num_trials >= 8.
Fee-free by design: this measures information, not P&L.
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "backtesting"))

from killtests.candles import CandleStore  # noqa: E402
from killtests.offline_ensemble import _load_kernels  # noqa: E402
from killtests.report import latest_verdict, write_verdict  # noqa: E402

NUM_TRIALS_FIXTURE = os.path.join(_HERE, "fixtures", "h4_num_trials.json")


def load_num_trials(path: str = NUM_TRIALS_FIXTURE) -> dict:
    with open(path) as f:
        return json.load(f)


def score_signals(series: pd.DataFrame, store, horizon_bars: int = 24) -> pd.DataFrame:
    out = []
    fired = series[series["ens_action"].notna()].copy()
    for symbol, grp in fired.groupby("symbol"):
        f = store.frame(symbol, "60").reset_index(drop=True)
        pos_by_ts = {int(ts): i for i, ts in enumerate(f["ts_ms"])}
        for row in grp.itertuples():
            # row.ts_ms is the decision time = close of bar i => bar open at ts_ms - 1h
            i = pos_by_ts.get(int(row.ts_ms) - 3_600_000)
            if i is None or i + horizon_bars >= len(f):
                continue  # tail signal without a full horizon — dropped, counted below
            store_close = float(f["close"].iloc[i])
            # Cheap checksum against the ts_ms convention above: the series already
            # carries the decision-bar close it was scored against live. If the
            # resolved index i is off by one, this catches it loudly instead of
            # silently scoring against the wrong bar.
            if not np.isclose(float(row.close), store_close, rtol=1e-6, atol=1e-6):
                raise ValueError(
                    f"{symbol} ts_ms={row.ts_ms}: series close {row.close} != "
                    f"CandleStore close {store_close} at resolved index {i} — "
                    "ts_ms convention mismatch, refusing to score against the wrong bar"
                )
            if row.ens_action not in ("BUY", "SELL"):
                raise ValueError(
                    f"{symbol} ts_ms={row.ts_ms}: unexpected ens_action "
                    f"{row.ens_action!r} (expected 'BUY' or 'SELL' — HOLD/NEUTRAL rows "
                    "should already be filtered by ens_action.notna(), and the writer "
                    "must emit SignalAction.value, not the enum repr)"
                )
            fwd = float(np.log(f["close"].iloc[i + horizon_bars] / store_close))
            direction = 1.0 if row.ens_action == "BUY" else -1.0
            out.append(
                {
                    "symbol": symbol,
                    "ts_ms": int(row.ts_ms),
                    "ens_action": row.ens_action,
                    "fwd_ret": fwd,
                    "signed_ret": fwd * direction,
                    "hit": fwd * direction > 0,
                }
            )
    scored = pd.DataFrame(out)
    scored.attrs["dropped_tail"] = int(len(fired) - len(scored))
    return scored


class InsufficientSignalsError(Exception):
    pass


def h4_stats(scored: pd.DataFrame, num_trials: int) -> dict:
    if scored.empty:
        # All-HOLD (or every fired signal fell in the tail-horizon drop) is a real
        # outcome, not hypothetical — Task 11's run hit exactly this. `scored` has
        # no columns in that case, so any column access below would KeyError
        # instead of taking the intended REJECT-with-reason path.
        raise InsufficientSignalsError(
            "0 scored signals (all-HOLD series or every fired signal dropped at "
            "the horizon boundary) — cannot compute DSR"
        )
    k = _load_kernels()
    # CPCV purge/embargo assume chronological order; score_signals emits rows
    # grouped by symbol — sort by time or the leakage protection is fictional.
    # (With sparse multi-symbol signals a 24-sample purge in index space spans
    # >= 24h in time — conservative; noted in the verdict config.)
    dropped_tail = scored.attrs.get("dropped_tail", 0)
    scored = scored.sort_values("ts_ms").reset_index(drop=True)
    rets = scored["signed_ret"].to_numpy(dtype=float)
    cv = k["CombinatorialPurgedCV"](n_groups=10, k_test_groups=2, embargo_pct=0.01)
    min_n = 10 * (24 + max(1, int(np.ceil(0.01 * len(rets)))) + 1)
    if len(rets) < min_n:
        raise InsufficientSignalsError(
            f"{len(rets)} signals < CPCV minimum ~{min_n} "
            f"(n_groups*(label_horizon+embargo+1)) — cannot compute DSR honestly"
        )
    paths = {}
    for split in cv.split(n_samples=len(rets), label_horizon=24):
        paths.setdefault(split.path_id, []).append(rets[split.test_idx])
    returns_per_path = [np.concatenate(chunks) for chunks in paths.values()]
    # Path-Sharpe distribution from the KERNEL (no hand-rolled Sharpe convention):
    dist = k["cpcv_sharpe_distribution"](returns_per_path)
    n_valid = int(dist["n_paths"])
    if n_valid >= 2:
        # configuration-history floor bound on top of the kernel variance
        dsr = float(
            k["deflated_sharpe_ratio"](
                rets,
                num_trials=max(num_trials, n_valid),
                trial_sharpes_variance=float(dist["std"]) ** 2,
            )
        )
    else:
        dsr = float("nan")
    wins = float(scored.loc[scored["signed_ret"] > 0, "signed_ret"].sum())
    losses = abs(float(scored.loc[scored["signed_ret"] < 0, "signed_ret"].sum()))
    return {
        "n_signals": int(len(scored)),
        "directional_accuracy": float(scored["hit"].mean()),
        "dsr": dsr,
        "n_cpcv_paths": n_valid,
        "num_trials_used": max(num_trials, n_valid),
        "pf_pooled": wins / losses if losses else float("inf"),
        "dropped_tail_signals": dropped_tail,
        "path_sharpe_variance_source": "cpcv_sharpe_distribution (kernel)",
    }


def _check_gates(force: bool, evidence_dir: str = None, stamp_path: str = None) -> list:
    """Both paths parameterized so the gate is unit-testable against tmp dirs."""
    from killtests.report import EVIDENCE_DIR

    evidence_dir = evidence_dir or EVIDENCE_DIR
    stamp_path = stamp_path or os.path.join(EVIDENCE_DIR, "golden-parity-stamp.json")
    caveats = []
    if latest_verdict("H3", out_dir=evidence_dir) is None:
        if not force:
            raise SystemExit(
                "H4 refused: no H3 verdict on file (AUDIT.md:267 order). Use --force to override."
            )
        caveats.append("FORCED past missing H3 verdict")
    today = date.today().strftime("%Y%m%d")
    try:
        stamp = json.load(open(stamp_path))
    except (FileNotFoundError, json.JSONDecodeError):
        stamp = {}
    if not (stamp.get("date") == today and stamp.get("passed") is True):
        if not force:
            raise SystemExit(
                "H4 refused: golden parity stamp missing/stale. Run: "
                "python3 -m pytest tests/killtests/test_golden_parity.py -m golden --no-cov"
            )
        caveats.append("FORCED past missing/stale golden-parity stamp")
    return caveats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", required=True)
    ap.add_argument("--data-dir", default="backtesting/data")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    gate_caveats = _check_gates(force=args.force)

    series = pd.read_csv(args.series)
    symbols = sorted(series["symbol"].unique())
    store = CandleStore(args.data_dir, symbols, ["60"])
    doc = load_num_trials()
    non_hold_rate = float(series["ens_action"].notna().mean())

    try:
        scored = score_signals(series, store, horizon_bars=24)
        metrics = h4_stats(scored, num_trials=doc["floor"])
        metrics["non_hold_rate"] = non_hold_rate
        accept = metrics["directional_accuracy"] > 0.50 and metrics["dsr"] > 0.95
    except InsufficientSignalsError as e:
        metrics = {"error": str(e), "non_hold_rate": non_hold_rate}
        accept = False

    def _sha(p):
        return hashlib.sha256(open(p, "rb").read()).hexdigest()[:12]

    input_hashes = {
        "series_csv": _sha(args.series),
        "num_trials_fixture": _sha(NUM_TRIALS_FIXTURE),
    }
    manifest = ".planning/evidence/killtests/backfill-manifest-2026-08.md"
    if os.path.exists(manifest):  # carries per-CSV digests (spec §9 input-data hash)
        input_hashes["backfill_manifest"] = _sha(manifest)

    caveats = gate_caveats + [
        "DSR is evaluated on the full concatenated signed_ret series, whose 24-bar "
        "forward-return windows overlap ~24-fold — effective sample size is ~n/24, "
        "not n. deflated_sharpe_ratio's standard-error term does not correct for "
        "this autocorrelation, so DSR is ANTICONSERVATIVE (easier to clear 0.95 "
        "than a true iid-equivalent series would allow). CPCV purge/embargo "
        "addresses train/test leakage between paths only — it does not fix this.",
        "CPCV paths share training data, so per-path Sharpes are correlated trials, "
        "violating DSR's trial-independence assumption (documented at cpcv.py:247-250) "
        "— mildly anticonservative in the same direction as the overlap issue above.",
        "fee-free by design (information test, not P&L)",
        "series generated by the offline replay whose parity stamp is required",
    ]

    path = write_verdict(
        "H4",
        "ACCEPT" if accept else "REJECT",
        "directional accuracy > 50% AND DSR > 0.95, num_trials >= 8",
        metrics=metrics,
        caveats=caveats,
        config={
            "horizon_bars": 24,
            "num_trials_floor": doc["floor"],
            "cpcv": "n_groups=10 k=2 embargo=0.01 label_horizon=24, time-sorted",
            "dsr_composition": (
                "deflated_sharpe_ratio + cpcv_sharpe_distribution composed directly "
                "(cpcv_to_dsr hard-codes num_trials=len(valid path Sharpes) at "
                "cpcv.py:264 with no override, so it cannot honor the >=8 floor)"
            ),
        },
        input_hashes=input_hashes,
    )
    print(f"H4 verdict written: {path}")
    print(f"  accept={accept} metrics={json.dumps(metrics, sort_keys=True)}")


if __name__ == "__main__":
    main()
