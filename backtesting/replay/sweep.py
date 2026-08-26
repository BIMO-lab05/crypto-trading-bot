#!/usr/bin/env python3
"""
Threshold sweep driver for the filter-stack replay.

Runs each configuration in its OWN subprocess. That is not tidiness: the
`SignalFunnel`, the `MarketRegimeDetector` and the ensemble weight store are
process-level singletons, so two configs in one process pool their counters
and every rejection table after the first is wrong.

**In-sample discipline.** `--select-on in_sample` is the default and the only
honest mode for choosing a threshold: pick using the pre-split slice only,
then look at out-of-sample exactly once for the winner. Sweeping the whole
window and splitting afterwards is leakage, and the out-of-sample number is
the single most valuable output of the exercise.

Usage:
    python3 backtesting/replay/sweep.py --frames F --klines K --out-dir D \\
        --split-date 2026-07-10 --param min_signal_confidence \\
        --values 0.20,0.25,0.30,0.35
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
REPLAY = os.path.join(_HERE, "replay_filter_stack.py")


def run_one(args, param: str, value: str) -> dict:
    label = f"{param}={value}"
    out = os.path.join(args.out_dir, f"{param}_{value}.json")
    cmd = [
        sys.executable,
        REPLAY,
        "--frames",
        args.frames,
        "--klines",
        args.klines,
        "--out",
        out,
        "--symbols",
        args.symbols,
        "--label",
        label,
        f"--{param.replace('_', '-')}",
        str(value),
    ]
    if args.split_date:
        cmd += ["--split-date", args.split_date]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout)
    if proc.returncode != 0:
        print(f"  {label}: FAILED rc={proc.returncode}")
        print(proc.stderr[-1500:])
        return {}
    with open(out) as fh:
        return json.load(fh)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--klines", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,ADAUSDT")
    ap.add_argument("--split-date", default="")
    ap.add_argument("--param", required=True)
    ap.add_argument("--values", required=True, help="comma-separated")
    ap.add_argument(
        "--select-on",
        default="in_sample",
        choices=["in_sample", "all"],
        help="which slice the comparison table reports. Choosing on 'all' is "
        "leakage — only use it for a descriptive run you will not tune from.",
    )
    ap.add_argument("--timeout", type=int, default=3600)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    rows = []
    for value in args.values.split(","):
        print(f"running {args.param}={value} ...", flush=True)
        report = run_one(args, args.param, value)
        if not report:
            continue
        slice_ = report.get(args.select_on) or report["all"]
        funnel = {s["stage"]: s for s in report["funnel"]["stages"]}
        rows.append(
            {
                "value": value,
                "signals": report["signals_emitted"],
                "trades": slice_["trades"],
                "win_rate_pct": slice_["win_rate_pct"],
                "expectancy_pct": slice_["expectancy_pct"],
                "avg_r": slice_["avg_r"],
                "total_net_return_pct": slice_["total_net_return_pct"],
                "max_drawdown_pct": slice_["max_drawdown_pct"],
                "profit_factor": slice_["profit_factor"],
                "gate_rejected": funnel["passed_signal_confidence_gate"]["rejected"],
                "path": os.path.join(args.out_dir, f"{args.param}_{value}.json"),
            }
        )

    print(f"\n=== {args.param} sweep ({args.select_on}) ===")
    hdr = (
        f"{'value':>8} {'trades':>7} {'win%':>7} {'exp%':>8} {'avgR':>7} "
        f"{'netRet%':>9} {'maxDD%':>8} {'PF':>6}"
    )
    print(hdr)
    for r in rows:

        def f(x, nd=2):
            return "n/a" if x is None else f"{x:.{nd}f}"

        print(
            f"{r['value']:>8} {r['trades']:>7} {f(r['win_rate_pct']):>7} "
            f"{f(r['expectancy_pct'], 4):>8} {f(r['avg_r'], 3):>7} "
            f"{f(r['total_net_return_pct']):>9} {f(r['max_drawdown_pct']):>8} "
            f"{f(r['profit_factor']):>6}"
        )

    summary = os.path.join(args.out_dir, f"sweep_{args.param}.json")
    with open(summary, "w") as fh:
        json.dump({"param": args.param, "select_on": args.select_on, "rows": rows}, fh, indent=2)
    print(f"\n-> {summary}")


if __name__ == "__main__":
    main()
