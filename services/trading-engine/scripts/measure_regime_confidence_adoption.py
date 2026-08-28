#!/usr/bin/env python3
"""Two-arm measurement of the DEFER-21-05 regime-confidence adoption.

WHAT THIS MEASURES
------------------
`handlers/signals._fetch_market_regime` used to return a fixed
`"confidence": 0.7` on its success path while technical-analysis published a
COMPUTED confidence on the very same `/indicators/adx/{symbol}` response.
DEFER-21-05 adopts TA's number and OMITS the key when TA supplies none.

That value has exactly one arithmetic consumer,
`handlers/signals._calculate_enhanced_signal`, whose risk leg does

    risk_confidence = market_regime.get("confidence", 0.5)
    weights.append(risk_confidence * 0.15)

so the change is numeric, not cosmetic. This harness runs both arms through
that real function -- imported, never re-implemented -- over a constructed grid
and reports, per row and in aggregate, how the resolved risk confidence, the
risk-leg weight, the final signal label and the overall confidence move:

  fixed_0_7    every regime dict carries the removed constant 0.7, which is
               what the handler returned unconditionally before the fix
  ta_reported  the same regime dicts carry what technical-analysis reports,
               including the OMITTED case where TA reports nothing and the
               consumer's own declared 0.5 neutral applies

WHAT THIS IS NOT
----------------
This is a signal-composition measurement. It is NOT a profitability result: no
P&L is computed, no DSR is computed, no CPCV is computed, and no edge is
claimed. CLAUDE.md section 2 forbids any edge claim without DSR/CPCV.

It is also NOT a measurement of live trading behaviour, for two independent
reasons. Both must be read before any number below is quoted:

  1. Live trading runs the ENSEMBLE path
     (`strategies/multi_strategy_ensemble.py`, driven by `auto_trader`). The
     enhanced path measured here is reachable only through the on-demand HTTP
     route `GET /api/v1/signals/enhanced/{symbol}`. The auto-trader never
     calls it.

  2. That HTTP route does not currently reach this arithmetic AT ALL. The
     handler passes the aggregator's `TradingSignal` straight into
     `_calculate_enhanced_signal`, which reads `base_signal.signal.action` --
     and `TradingSignal` has no `.signal` attribute, so the call raises
     AttributeError on its first statement and the endpoint falls back to the
     basic signal. Verified 2026-08-28 on this tree; recorded by plan 22.1-05
     as an out-of-scope finding and deliberately NOT repaired here, because
     repairing it would turn a dead money-adjacent endpoint live.

Consequence: every delta reported below is a COUNTERFACTUAL -- what the risk
leg would do once the enhanced path is wired -- not a change in observed
behaviour. Today the removed 0.7 reached nothing. That is precisely why
removing it is safe, and it is the measurement rather than the assertion the
plan asked for.

The corpus is therefore driven through a `_BaseSignalDouble` supplying the
`base_signal.signal.*` shape the function is written against and that
production does not currently supply. That caveat is stated here, not only in
the SUMMARY, so it travels with the artifact.

Second observation, same class and also out of scope: the function computes
`final_signal` at `handlers/signals.py:332` and never stores it -- only
`confidence` is written back. The enhanced path therefore cannot change a
signal's action even once wired. This harness captures that discarded label by
wrapping the module's own `_numeric_to_signal` and delegating to it, so the
reported label is the one production computed, not one recomputed here.

DETERMINISM
-----------
No randomness is used, so no seed is required; `--seed` is accepted and printed
for the record. The corpus is constructed in-process by `build_corpus()` from a
fixed grid -- no database, no HTTP, no running stack. (postgres and timescaledb
in this environment have a documented history of dying `exit=127` after a host
suspend; a harness that only runs when services are up is a harness that does
not run.) No timestamp is written into the artifact, so two runs are literally
byte-identical, and `--check-determinism` additionally replays the whole corpus
in REVERSE order and compares the full result structures.

`_calculate_enhanced_signal` MUTATES the object it is handed
(`base_signal.signal.confidence = ...`, `.metadata.update(...)`), so a fresh
double is built for every arm of every row. Sharing one would make the second
arm read the first arm's output and the entire delta column would be garbage.

USAGE
-----
    cd services/trading-engine
    python3 scripts/measure_regime_confidence_adoption.py
    python3 scripts/measure_regime_confidence_adoption.py \\
        --json ../../.planning/evidence/22.1-regime-confidence-measurement.json
    python3 scripts/measure_regime_confidence_adoption.py --check-determinism
"""

import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Host runs must not inherit an operator .env: pydantic-settings v2 deep-merges
# Dict fields, so SYMBOL_ALLOCATIONS unions instead of replacing. Same pin
# tests/conftest.py applies at import time, and for the same reason.
from app.config import Settings  # noqa: E402

Settings.model_config["env_file"] = None

from app.handlers import signals as signals_handler  # noqa: E402

# The removed constant. Named once so the arm and the source guard cannot drift.
REMOVED_FIXED_CONFIDENCE = 0.7

# The consumer's own declared neutral, applied when the key is ABSENT
# (`market_regime.get("confidence", 0.5)`), and the weight the risk leg carries.
CONSUMER_NEUTRAL = 0.5
RISK_LEG_WEIGHT = 0.15

ARMS = ("fixed_0_7", "ta_reported")

# Engine-side regime labels the mapper can emit, plus the UNKNOWN fall-through.
# Read off the production map rather than restated, so a label technical-analysis
# adds later enters this grid automatically instead of silently missing from it.
ENGINE_REGIMES = sorted(set(signals_handler.TA_REGIME_TO_ENGINE_REGIME.values())) + ["UNKNOWN"]

# TA's confidence range swept at 0.1, plus the ABSENT case the new
# absence-stays-absent rule introduces. Absence is the branch the tests say
# matters most; a grid that only carried present values would not cover it.
TA_CONFIDENCE_GRID: List[Optional[float]] = [round(i / 10, 1) for i in range(11)] + [None]

# Both directions plus HOLD, on the base leg and on the ML leg.
BASE_ACTIONS = ("BUY", "SELL", "HOLD")
ML_ACTIONS = ("BUY", "SELL", "HOLD")

BASE_CONFIDENCE = 0.6
ML_CONFIDENCE = 0.7


# ---------------------------------------------------------------------------
# Capture the label production computes and throws away (handlers/signals.py:332)
# ---------------------------------------------------------------------------

_ORIGINAL_NUMERIC_TO_SIGNAL = signals_handler._numeric_to_signal

# Module-global, written inside an async call and read after it. `run_corpus`
# drives rows STRICTLY SEQUENTIALLY and that ordering is LOAD-BEARING: an
# `asyncio.gather` here would interleave the two arms and each row would read
# whichever label happened to be recorded last. If this ever needs to run
# concurrently, pass a per-call recorder instead of promoting this to a lock.
_CAPTURED: Dict[str, Any] = {}


def _recording_numeric_to_signal(numeric: float) -> str:
    """Delegate to the real converter, recording what it returned.

    This is instrumentation, not re-implementation: the threshold logic stays
    in `handlers/signals._numeric_to_signal` and is called unchanged.
    """
    label = _ORIGINAL_NUMERIC_TO_SIGNAL(numeric)
    _CAPTURED["final_signal_numeric"] = round(float(numeric), 9)
    _CAPTURED["final_signal"] = label
    return label


signals_handler._numeric_to_signal = _recording_numeric_to_signal


class _BaseSignalDouble:
    """The `base_signal.signal.*` shape `_calculate_enhanced_signal` reads.

    See WHAT THIS IS NOT: production does not currently supply this shape,
    which is exactly why the enhanced endpoint falls back today.
    """

    def __init__(self, action: str, confidence: float):
        self.signal = SimpleNamespace(
            action=SimpleNamespace(value=action),
            confidence=confidence,
            metadata={},
        )


def build_corpus() -> List[Dict[str, Any]]:
    """Constructed deterministic grid: regime x TA confidence x base x ML action."""
    rows: List[Dict[str, Any]] = []
    for regime in ENGINE_REGIMES:
        for ta_confidence in TA_CONFIDENCE_GRID:
            for base_action in BASE_ACTIONS:
                for ml_action in ML_ACTIONS:
                    shown = "absent" if ta_confidence is None else ta_confidence
                    rows.append(
                        {
                            "row_id": (f"{regime}|ta={shown}|base={base_action}|ml={ml_action}"),
                            "regime": regime,
                            "ta_confidence": ta_confidence,
                            "base_action": base_action,
                            "ml_action": ml_action,
                        }
                    )
    return rows


def regime_dict_for(arm: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """The dict `_fetch_market_regime` returns under each arm.

    `fixed_0_7` reproduces the pre-DEFER-21-05 shape: the key was ALWAYS
    present and ALWAYS 0.7, whatever technical-analysis actually reported.
    `ta_reported` reproduces the post-fix shape: TA's value when it supplies
    one, and NO KEY AT ALL when it does not.
    """
    base = {"regime": row["regime"], "adx": 27.0}
    if arm == "fixed_0_7":
        return {**base, "confidence": REMOVED_FIXED_CONFIDENCE}
    if arm == "ta_reported":
        if row["ta_confidence"] is None:
            return base
        return {**base, "confidence": row["ta_confidence"]}
    raise ValueError(f"unknown arm {arm!r}")


async def run_row(arm: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """One arm of one row, through the real `_calculate_enhanced_signal`."""
    # Fresh double per arm per row -- the function mutates what it is handed.
    double = _BaseSignalDouble(row["base_action"], BASE_CONFIDENCE)
    _CAPTURED.clear()

    result = await signals_handler._calculate_enhanced_signal(
        double,
        {"signal": row["ml_action"], "confidence": ML_CONFIDENCE},
        regime_dict_for(arm, row),
    )

    metadata = getattr(result, "metadata", {}) or {}
    risk_leg = (metadata.get("individual_signals") or {}).get("risk_adjustment") or {}
    # Read back out of the metadata the function itself wrote, not recomputed.
    resolved = risk_leg.get("confidence")

    return {
        "arm": arm,
        "row_id": row["row_id"],
        "resolved_risk_confidence": resolved,
        "risk_leg_weight": (None if resolved is None else round(resolved * RISK_LEG_WEIGHT, 9)),
        "final_signal": _CAPTURED.get("final_signal"),
        "final_signal_numeric": _CAPTURED.get("final_signal_numeric"),
        "overall_confidence": (
            None if result.confidence is None else round(float(result.confidence), 9)
        ),
        "arithmetic_completed": metadata.get("enhanced") is True,
    }


async def run_corpus(corpus: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    return {arm: [await run_row(arm, row) for row in corpus] for arm in ARMS}


def compare(
    corpus: List[Dict[str, Any]], per_arm: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, Any]:
    """Row-by-row old-vs-new comparison plus the aggregate figures."""
    old_rows = {r["row_id"]: r for r in per_arm["fixed_0_7"]}
    new_rows = {r["row_id"]: r for r in per_arm["ta_reported"]}

    rows: List[Dict[str, Any]] = []
    for row in corpus:
        rid = row["row_id"]
        old, new = old_rows[rid], new_rows[rid]
        old_conf, new_conf = old["overall_confidence"], new["overall_confidence"]
        delta = None if old_conf is None or new_conf is None else round(new_conf - old_conf, 9)
        rows.append(
            {
                "row_id": rid,
                "regime": row["regime"],
                "ta_confidence": row["ta_confidence"],
                "base_action": row["base_action"],
                "ml_action": row["ml_action"],
                "old_risk_confidence": old["resolved_risk_confidence"],
                "new_risk_confidence": new["resolved_risk_confidence"],
                "old_risk_leg_weight": old["risk_leg_weight"],
                "new_risk_leg_weight": new["risk_leg_weight"],
                "old_final_signal": old["final_signal"],
                "new_final_signal": new["final_signal"],
                "label_changed": old["final_signal"] != new["final_signal"],
                "old_overall_confidence": old_conf,
                "new_overall_confidence": new_conf,
                "overall_confidence_delta": delta,
                "arithmetic_completed_both_arms": (
                    old["arithmetic_completed"] and new["arithmetic_completed"]
                ),
            }
        )

    deltas = [
        abs(r["overall_confidence_delta"])
        for r in rows
        if r["overall_confidence_delta"] is not None
    ]
    biggest = max(rows, key=lambda r: abs(r["overall_confidence_delta"] or 0.0))

    return {
        "row_count": len(rows),
        "rows_where_arithmetic_completed_both_arms": sum(
            1 for r in rows if r["arithmetic_completed_both_arms"]
        ),
        "rows_where_ta_reported_no_confidence": sum(1 for r in rows if r["ta_confidence"] is None),
        "label_changes": sum(1 for r in rows if r["label_changed"]),
        "rows_with_a_nonzero_confidence_delta": sum(1 for d in deltas if d > 0),
        "abs_confidence_delta_min": min(deltas) if deltas else None,
        "abs_confidence_delta_median": (round(statistics.median(deltas), 9) if deltas else None),
        "abs_confidence_delta_max": max(deltas) if deltas else None,
        "biggest_mover": biggest,
        "rows": rows,
    }


def summary_lines(result: Dict[str, Any]) -> List[str]:
    b = result["biggest_mover"]
    return [
        f"rows                                : {result['row_count']}",
        f"  of which TA reported no confidence: {result['rows_where_ta_reported_no_confidence']}",
        f"arithmetic completed (both arms)    : {result['rows_where_arithmetic_completed_both_arms']}",
        f"final-label changes                 : {result['label_changes']}",
        f"rows with a nonzero conf delta      : {result['rows_with_a_nonzero_confidence_delta']}",
        f"|delta overall confidence| min      : {result['abs_confidence_delta_min']}",
        f"|delta overall confidence| median   : {result['abs_confidence_delta_median']}",
        f"|delta overall confidence| max      : {result['abs_confidence_delta_max']}",
        f"biggest mover                       : {b['row_id']}",
        f"  risk confidence  {b['old_risk_confidence']} -> {b['new_risk_confidence']}",
        f"  risk leg weight  {b['old_risk_leg_weight']} -> {b['new_risk_leg_weight']}",
        f"  overall conf     {b['old_overall_confidence']} -> {b['new_overall_confidence']}",
        f"  final signal     {b['old_final_signal']} -> {b['new_final_signal']}",
    ]


def capture_live_confidences() -> Dict[str, Any]:
    """Optional, OFF by default: what technical-analysis is reporting right now.

    Never the sole source of the artifact -- it is recorded ALONGSIDE the
    constructed grid, and an unreachable service degrades to a printed notice
    rather than a failure. Excluded from the determinism guarantee by
    construction, which is exactly why it is opt-in.
    """
    try:
        import httpx

        base = Settings().technical_analysis_url
        observed = {}
        with httpx.Client(timeout=5.0) as client:
            for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"):
                response = client.get(
                    f"{base}/api/v1/indicators/adx/{symbol}", params={"interval": "60"}
                )
                response.raise_for_status()
                data = response.json().get("data", {}) or {}
                observed[symbol] = data.get("confidence")
        return {
            "status": "captured",
            "note": "recorded alongside the constructed grid, never instead of it",
            "observed_confidence": observed,
        }
    except Exception as exc:
        return {
            "status": "unreachable",
            "note": f"technical-analysis not reachable ({exc}); constructed grid only",
            "observed_confidence": None,
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure the DEFER-21-05 regime-confidence adoption (two arms)."
    )
    parser.add_argument("--json", dest="json_path", help="write the machine-readable artifact here")
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="recorded for the record; this harness uses no randomness",
    )
    parser.add_argument("--verbose", action="store_true", help="show the handler's own logging")
    parser.add_argument(
        "--check-determinism",
        action="store_true",
        help="replay the corpus in REVERSE order and assert identical results",
    )
    parser.add_argument(
        "--live-capture",
        action="store_true",
        help=(
            "OFF by default. Additionally probe the running technical-analysis "
            "service for the confidences it reports right now. Degrades to "
            "constructed-only with a printed notice when unreachable, and is "
            "never the sole source of the artifact."
        ),
    )
    args = parser.parse_args()

    logging.disable(logging.NOTSET if args.verbose else logging.CRITICAL)

    corpus = build_corpus()
    # Integrity guard, and it must sit BEFORE compare(): this check used to
    # run after the comparison, but compare() calls max() over the rows and
    # raises ValueError on an empty sequence, so the graceful FAIL below it
    # could never execute (review 22.1 IN-03). Unreachable today -- the grid
    # always contains UNKNOWN -- but a guard that documents a failure mode
    # must actually be the code path that expresses it.
    if not corpus:
        print("FAIL: empty corpus", file=sys.stderr)
        return 1
    per_arm = asyncio.run(run_corpus(corpus))
    result = compare(corpus, per_arm)

    determinism = None
    if args.check_determinism:
        replayed = asyncio.run(run_corpus(list(reversed(corpus))))
        replayed = {arm: list(reversed(rows)) for arm, rows in replayed.items()}
        determinism = replayed == per_arm

    live = capture_live_confidences() if args.live_capture else None

    print(f"seed={args.seed} (unused - no randomness in this harness)")
    print(f"corpus=constructed grid (n={len(corpus)}); arms={list(ARMS)}")
    print(
        "caveat: COUNTERFACTUAL only - live trading runs the ensemble path, and "
        "the enhanced HTTP route does not currently reach this arithmetic. See "
        "WHAT THIS IS NOT in the module docstring before quoting any number."
    )
    print()
    for line in summary_lines(result):
        print(line)
    if determinism is not None:
        print()
        print(f"determinism (reverse-order replay identical): {determinism}")
    if live is not None:
        print()
        print(f"live capture: {live['status']} - {live['note']}")

    payload = {
        "measurement": "DEFER-21-05 regime confidence adoption",
        "seed": args.seed,
        "arms": list(ARMS),
        "removed_fixed_confidence": REMOVED_FIXED_CONFIDENCE,
        "consumer_neutral_when_key_absent": CONSUMER_NEUTRAL,
        "risk_leg_weight": RISK_LEG_WEIGHT,
        "corpus_source": "constructed grid",
        "corpus_size": len(corpus),
        "reverse_order_replay_identical": determinism,
        "live_capture": live,
        "is_not": (
            "Signal composition only. No P&L, no DSR, no CPCV, no edge claim "
            "(CLAUDE.md section 2). COUNTERFACTUAL: live trading runs the "
            "ensemble path, and the enhanced HTTP route currently raises "
            "AttributeError before reaching this arithmetic, so the removed 0.7 "
            "influenced nothing in production. The final signal label is "
            "computed and discarded by handlers/signals.py:332; it is captured "
            "here by wrapping the module's own _numeric_to_signal."
        ),
        "aggregate": {k: v for k, v in result.items() if k != "rows"},
        "rows": result["rows"],
    }

    if args.json_path:
        with open(args.json_path, "w") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"\nwrote {args.json_path}")

    # Integrity: if the enhanced arithmetic degraded on any row, the deltas
    # would be comparing exception fallbacks rather than weights. (The
    # empty-corpus check that used to sit here moved above compare() --
    # review 22.1 IN-03.)
    if result["rows_where_arithmetic_completed_both_arms"] != result["row_count"]:
        print(
            "\nFAIL: the enhanced arithmetic degraded on at least one row",
            file=sys.stderr,
        )
        return 1
    if result["rows_where_ta_reported_no_confidence"] == 0:
        print(
            "\nFAIL: the grid never exercised the absent-confidence branch",
            file=sys.stderr,
        )
        return 1
    if determinism is False:
        print("\nFAIL: reverse-order replay differed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
