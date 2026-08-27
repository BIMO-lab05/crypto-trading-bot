#!/usr/bin/env python3
"""Four-arm ablation of the Phase 21 ensemble-admission changes.

WHAT THIS MEASURES
------------------
Three Phase 21 fixes move trade admission and they push in OPPOSITE directions,
so a single before/after number would be uninterpretable:

  * Plan 21-03 (+ATR) INCREASES admission - `_atr_indicator` populates
    `indicators["ATR"]`, which un-deadens `mean_reversion`'s SMA-deviation
    sub-signals (they are gated on `atr_value > 0` and the key was never
    written).
  * Plan 21-03 (+ATR) also DECREASES admission - the shared `_atr_is_usable`
    predicate makes `atr.py::_default_response()` read as ABSENT inside
    `_atr_levels`, so the multi_indicator leg carries UNUSABLE_LEVEL stops and
    is refused pre-fill instead of trading an undeclared 3% stop.
  * Plans 21-05 and 21-06 (+gates) DECREASE admission - MTF demote-to-HOLD now
    suppresses every leg, and agreeing legs must span >= 2 indicator categories.

BOTH ATR effects belong to the +ATR arm. Filing the fetch-failure rejection
under +gates would invert the measured direction of both arms.

WHAT THIS IS NOT
----------------
This is an admission and signal-count measurement. It is NOT a profitability
result: no P&L is computed, no DSR/CPCV is computed, and none is claimed.
CLAUDE.md section 2 forbids any edge claim without DSR/CPCV.

HOW THE ARMS ARE PRODUCED
-------------------------
There is no pre-phase checkout to run against by this wave, so the four arms are
reconstructed from ONE tree by disabling each new behaviour individually:

  baseline  pre-phase: no synthetic ATR, permissive ATR predicate, MTF gate
            neutralised, diversity guard forced to pass
  +ATR      only the ATR work restored
  +gates    only the MTF suppression and the diversity guard restored
  both      the tree as it now stands

`_atr_is_usable` must be relaxed as well as `_atr_indicator` disabled. Plan
21-03 applied the predicate to `_atr_levels` too; stubbing only `_atr_indicator`
would leave the fetch-failure rejection active in all four arms and the +ATR
decrease would measure exactly zero.

MEASUREMENT BOUNDARY
--------------------
Admission is measured through `AutoTrader._ensemble_stops_are_consistent`, the
real production predicate, imported rather than re-implemented. `generate_signal`
does not reject an UNUSABLE_LEVEL stop - it emits a signal carrying 0.0 and the
pre-fill check refuses it. A measurement stopping at `generate_signal` would miss
the entire +ATR decrease.

DETERMINISM
-----------
No randomness is used, so no seed is required; `--seed` is accepted and printed
for the record. Leg weights are pinned inside the harness and
`StrategyPerformanceWeights.STATE_PATH` is repointed at a throwaway path, so the
persisted `/app/data/ensemble_weights.json` can neither be read nor written by
this run. Its digest is captured before and after regardless.

USAGE
-----
    cd services/trading-engine
    python3 scripts/ablation_ensemble_admission.py --arms all
    python3 scripts/ablation_ensemble_admission.py --arms all --json out.json
"""

import argparse
import copy
import hashlib
import importlib
import json
import logging
import os
import sys
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Host runs must not inherit an operator .env: pydantic-settings v2 deep-merges
# Dict fields, so SYMBOL_ALLOCATIONS unions instead of replacing. Same pin
# tests/conftest.py applies at import time, and for the same reason.
from app.config import Settings  # noqa: E402

Settings.model_config["env_file"] = None

from app.models.enums import SignalAction  # noqa: E402
from app.models.signal import IndicatorSignal, TradingSignal  # noqa: E402

ARMS = ("baseline", "+ATR", "+gates", "both")

# The real persisted weight file. Never read or written by this harness - the
# STATE_PATH is repointed before any ensemble is constructed - but digested
# before and after so a drift is provable rather than argued.
LIVE_WEIGHTS_PATH = "/app/data/ensemble_weights.json"

PRICE = 100.0

# Post-ensemble admission gate. `generate_signal` emits a signal carrying
# UNUSABLE_LEVEL (0.0) stops; auto_trader refuses it pre-fill. Named here so the
# breakdown does not read as one of Plan 21-06's five in-ensemble causes.
REJECT_PREFILL_STOPS = "rejected_prefill_unusable_stops"


# ---------------------------------------------------------------------------
# Payload builders - shapes copied from tests/strategies/test_ensemble_leg_wiring.py,
# which are verified against what SignalAggregator actually emits.
# ---------------------------------------------------------------------------


def _atr_payload(price: float = PRICE, atr_pct: float = 2.0) -> dict:
    """`signal_aggregator.fetch_atr`'s dict, filed under metadata["atr"]."""
    atr = price * atr_pct / 100.0
    return {
        "atr": atr,
        "atr_pct": atr_pct,
        "stop_loss_long": price - 2 * atr,
        "stop_loss_short": price + 2 * atr,
        "take_profit_long": price + 4 * atr,
        "take_profit_short": price - 4 * atr,
        "volatility": "NORMAL",
        "confidence": 0.7,
        "risk_reward_ratio": 2.0,
    }


def _atr_failure_payload(price: float = PRICE) -> dict:
    """`technical-analysis/app/indicators/atr.py::_default_response()`, verbatim.

    NOT empty: `atr`/`atr_pct` are 0.0 while stop_loss_long/short are POPULATED
    at a hardcoded 3% nobody chose. That asymmetry is the whole reason
    `_atr_is_usable` exists, and it is the payload the +ATR arm's admission
    DECREASE is measured on.
    """
    return {
        "atr": 0.0,
        "atr_pct": 0.0,
        "stop_loss_long": float(price * 0.97),
        "stop_loss_short": float(price * 1.03),
        "take_profit_long": float(price * 1.06),
        "take_profit_short": float(price * 0.94),
        "volatility": "UNKNOWN",
        "confidence": 0.0,
        "risk_reward_ratio": 2.0,
    }


def _ind(name: str, value: float, metadata: dict, signal=SignalAction.HOLD, conf=0.3):
    return IndicatorSignal(
        name=name, signal=signal, confidence=conf, value=value, metadata=metadata
    )


def _rsi(value: float):
    """RSI as fetch_rsi builds it: numeric reading on `.value`."""
    action = (
        SignalAction.BUY
        if value <= 30
        else (SignalAction.SELL if value >= 70 else SignalAction.HOLD)
    )
    return _ind("RSI", value, {"period": 9, "weight": 1.0}, action, 0.55)


def _sma(value: float, price: float = PRICE):
    return _ind("SMA", value, {"current_price": price, "period": 21, "weight": 0.8})


def _bollinger(price: float, upper: float, lower: float):
    return _ind(
        "BOLLINGER_BANDS",
        price,
        {
            "upper_band": upper,
            "middle_band": (upper + lower) / 2,
            "lower_band": lower,
            "weight": 1.0,
        },
    )


def _signal(
    name: str,
    *,
    action=SignalAction.HOLD,
    confidence: float = 0.0,
    indicators: Optional[dict] = None,
    atr: Optional[dict] = None,
    mtf: Optional[dict] = None,
    price: float = PRICE,
) -> Tuple[str, TradingSignal, float]:
    metadata: Dict[str, Any] = {}
    if atr is not None:
        metadata["atr"] = atr
    if mtf is not None:
        metadata["multi_timeframe"] = mtf
    return (
        name,
        TradingSignal(
            symbol="SOLUSDT",
            timestamp=0,
            action=action,
            confidence=confidence,
            aggregated_score=(confidence if action == SignalAction.BUY else -confidence),
            consensus_count=5,
            indicators=indicators or {},
            metadata=metadata,
        ),
        price,
    )


def build_corpus() -> List[Tuple[str, TradingSignal, float]]:
    """The deterministic payload corpus, rebuilt fresh on every call.

    A factory rather than a module constant: the +gates-off arms strip
    `demoted_to_hold` from the payload, and a corpus shared across arms would
    carry that mutation forward. Contamination of that kind survives a
    "run it twice" determinism check, which is why `--check-determinism` also
    runs the arms in reverse order.

    Scenario names are stable identifiers - the evidence document groups on them.
    """
    usable = _atr_payload()
    return [
        # --- the +ATR unlock, and the case where the two arms fight -----------
        # mean_reversion fires ONLY when ATR is present (SMA-deviation branch is
        # gated on atr_value > 0). Without it, simple_rsi is alone and
        # single-source -> the diversity guard blocks. With it, {MOMENTUM, TREND}.
        _signal(
            "atr_unlocks_sma_route_buy",
            indicators={"RSI": _rsi(28.0), "SMA": _sma(105.0)},
            atr=usable,
        ),
        _signal(
            "atr_unlocks_sma_route_sell",
            indicators={"RSI": _rsi(85.0), "SMA": _sma(95.0)},
            atr=usable,
        ),
        # --- pure +gates: single-source agreement, ATR irrelevant -------------
        _signal(
            "rsi_only_single_source",
            indicators={"RSI": _rsi(28.0)},
            atr=usable,
        ),
        _signal(
            "rsi_only_no_atr_payload",
            indicators={"RSI": _rsi(28.0)},
        ),
        # --- the +ATR DECREASE: the fetch-failure payload ---------------------
        # Pre-phase, `_atr_levels` read the populated 3% stops and traded them.
        # Post-21-03 it returns UNUSABLE_LEVEL and the pre-fill check refuses it.
        _signal(
            "atr_fetch_failure_multi_leg",
            action=SignalAction.BUY,
            confidence=0.55,
            indicators={"RSI": _rsi(50.0)},
            atr=_atr_failure_payload(),
        ),
        # --- pure +gates: the MTF demotion ------------------------------------
        _signal(
            "mtf_demoted_to_hold",
            action=SignalAction.BUY,
            confidence=0.55,
            indicators={"RSI": _rsi(28.0), "SMA": _sma(105.0)},
            atr=usable,
            mtf={
                "demoted_to_hold": True,
                "consensus_action": "BUY",
                "consolidated_action": "HOLD",
            },
        ),
        # Positive control on the identical shape minus the flag. Without it the
        # suppression count could be read off a payload that never emitted anyway.
        _signal(
            "mtf_not_demoted_control",
            action=SignalAction.BUY,
            confidence=0.55,
            indicators={"RSI": _rsi(28.0), "SMA": _sma(105.0)},
            atr=usable,
            mtf={
                "demoted_to_hold": False,
                "consensus_action": "BUY",
                "consolidated_action": "BUY",
            },
        ),
        # --- controls that must NOT move across arms --------------------------
        # multi_indicator alone is diverse BY CONSTRUCTION (it already cleared
        # CoreAggregator's own check_category_diversity). Blocking it would be
        # double jeopardy on the strongest leg - the row where the diversity
        # guard and MIN_AGREEING_LEGS = 2 deliberately diverge.
        _signal(
            "multi_indicator_alone",
            action=SignalAction.BUY,
            confidence=0.55,
            indicators={"RSI": _rsi(50.0)},
            atr=usable,
        ),
        # mean_reversion's Bollinger route needs no ATR, so this pair is
        # {MOMENTUM, VOLATILITY} in every arm.
        _signal(
            "rsi_plus_bollinger_route",
            indicators={"RSI": _rsi(28.0), "BOLLINGER_BANDS": _bollinger(100.0, 120.0, 100.0)},
            atr=usable,
        ),
        # The ONLY scenario in this corpus that can show a top-line admission
        # INCREASE for +ATR, and the reason is structural. Every other RSI-route
        # payload here sits at RSI <= 30, which fires `simple_rsi` as well (both
        # legs use 30/70), so `mean_reversion` joining can only change the leg
        # set - never whether a signal exists at all. At RSI 50 `simple_rsi`
        # returns None, so `mean_reversion` must carry the payload alone:
        # BB_LOWER (0.25) + PRICE_BELOW_SMA (0.15) = 0.40 over two aligned
        # sub-signals, spanning {VOLATILITY, TREND}. Without ATR the SMA branch
        # is dead, leaving one sub-signal, which fails MIN_INDICATORS_ALIGNED.
        _signal(
            "meanrev_alone_needs_atr",
            indicators={
                "RSI": _rsi(50.0),
                "BOLLINGER_BANDS": _bollinger(100.0, 120.0, 100.0),
                "SMA": _sma(105.0),
            },
            atr=usable,
        ),
        _signal(
            "no_legs_fire",
            indicators={"RSI": _rsi(50.0)},
            atr=usable,
        ),
        # --- first-failing-gate ordering, made visible ------------------------
        # simple_rsi BUY against a multi_indicator SELL nets |score| < 0.10.
        # Pre-phase that is `score_below_threshold`; with the guard in place the
        # diversity block fires FIRST. The evaluation did not change - the
        # attribution did. See the order-dependence note in the evidence doc.
        _signal(
            "opposed_legs_below_threshold",
            action=SignalAction.SELL,
            confidence=0.45,
            indicators={"RSI": _rsi(28.0)},
            atr=usable,
        ),
    ]


# ---------------------------------------------------------------------------
# Arm construction
# ---------------------------------------------------------------------------


def _permissive_atr_is_usable(atr_data) -> bool:
    """`_atr_levels`' pre-21-03 presence test.

    Before Plan 21-03 the only check was `isinstance(atr_data, dict)`; the
    populated stop_loss_long/short of the failure payload were then read and
    traded at an undeclared 3%. Restoring exactly that is what makes the +ATR
    arm's admission DECREASE measurable instead of measuring zero.
    """
    return isinstance(atr_data, dict)


def _disabled_diversity_guard(self, agreeing_leg_ids, mean_reversion_signal, action, symbol):
    return (True, 0, "diversity guard disabled (pre-phase arm)")


@contextmanager
def armed_module(arm: str, weights_state_path: str):
    """Yield a freshly reloaded ensemble module patched for `arm`.

    Reload per arm so each starts from a clean module binding - the module holds
    a weights singleton and a lazily-built category voter.
    """
    import app.strategies.multi_strategy_ensemble as mod

    importlib.reload(mod)

    # Pin the weight file BEFORE any StrategyPerformanceWeights is constructed.
    # A drifting /app/data/ensemble_weights.json feeds normalized_weights() into
    # every leg contribution and is indistinguishable from a code-caused delta.
    mod.StrategyPerformanceWeights.STATE_PATH = weights_state_path

    atr_on = arm in ("+ATR", "both")
    gates_on = arm in ("+gates", "both")

    if not atr_on:
        mod.MultiStrategyEnsemble._atr_indicator = staticmethod(lambda _agg: None)
        mod._atr_is_usable = _permissive_atr_is_usable
    if not gates_on:
        mod.MultiStrategyEnsemble._check_leg_source_diversity = _disabled_diversity_guard

    _assert_patches_took(mod, arm, atr_on, gates_on)
    yield mod, gates_on


def _assert_patches_took(mod, arm: str, atr_on: bool, gates_on: bool) -> None:
    """Prove each arm's patches bound. A silently-unpatched arm reads as
    "no delta", which is precisely the failure mode this measurement exists to
    avoid (21-RESEARCH Pitfall 7, in a new costume).
    """
    failure = _atr_failure_payload()
    usable = _atr_payload()

    got = mod.MultiStrategyEnsemble._atr_indicator(
        TradingSignal(
            symbol="X",
            timestamp=0,
            action=SignalAction.HOLD,
            confidence=0.0,
            aggregated_score=0.0,
            consensus_count=0,
            indicators={},
            metadata={"atr": usable},
        )
    )
    if atr_on:
        assert got is not None, f"[{arm}] _atr_indicator should be LIVE but returned None"
        assert mod._atr_is_usable(failure) is False, (
            f"[{arm}] _atr_is_usable should be STRICT but accepted the failure payload"
        )
    else:
        assert got is None, f"[{arm}] _atr_indicator should be DISABLED but built a signal"
        assert mod._atr_is_usable(failure) is True, (
            f"[{arm}] _atr_is_usable should be PERMISSIVE but rejected the failure payload"
        )

    # Behavioural check, not just an identity check: the permissive arm must
    # actually read the failure payload's populated 3% stops back out.
    levels = mod.MultiStrategyEnsemble._atr_levels(
        TradingSignal(
            symbol="X",
            timestamp=0,
            action=SignalAction.BUY,
            confidence=0.5,
            aggregated_score=0.5,
            consensus_count=1,
            indicators={},
            metadata={"atr": failure},
        )
    )
    if atr_on:
        assert levels == (mod.UNUSABLE_LEVEL, mod.UNUSABLE_LEVEL), (
            f"[{arm}] _atr_levels should refuse the failure payload, got {levels}"
        )
    else:
        assert levels != (mod.UNUSABLE_LEVEL, mod.UNUSABLE_LEVEL), (
            f"[{arm}] _atr_levels should have traded the failure payload's 3% stops"
        )

    guard = mod.MultiStrategyEnsemble._check_leg_source_diversity
    single_source = guard(
        mod.MultiStrategyEnsemble.__new__(mod.MultiStrategyEnsemble),
        [mod.LEG_RSI],
        None,
        SignalAction.BUY,
        "X",
    )
    if gates_on:
        assert single_source[0] is False, (
            f"[{arm}] the diversity guard should be LIVE but passed a lone simple_rsi"
        )
    else:
        assert single_source[0] is True, (
            f"[{arm}] the diversity guard should be DISABLED but blocked"
        )


def _pinned_ensemble(mod):
    """An ensemble whose leg weights are fixed, not loaded from disk."""
    ens = mod.MultiStrategyEnsemble()
    ens.weights._win_rates = {
        mod.LEG_RSI: mod.StrategyPerformanceWeights.DEFAULT_WIN_RATE,
        mod.LEG_MULTI: mod.StrategyPerformanceWeights.DEFAULT_WIN_RATE,
        mod.LEG_MEAN_REV: mod.StrategyPerformanceWeights.DEFAULT_WIN_RATE,
    }
    ens.weights._trade_counts = {mod.LEG_RSI: 0, mod.LEG_MULTI: 0, mod.LEG_MEAN_REV: 0}
    return ens


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def run_arm(arm: str, weights_state_path: str, stops_ok: Callable) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []

    with armed_module(arm, weights_state_path) as (mod, gates_on):
        ens = _pinned_ensemble(mod)
        weights = ens.weights.normalized_weights()

        for name, signal, price in build_corpus():
            payload = copy.deepcopy(signal)
            if not gates_on:
                # Pre-phase code never read `demoted_to_hold`; the gate is inline
                # with no patchable helper, so the faithful reconstruction is to
                # present the payload as the pre-phase reader saw it. Applied to a
                # deep copy, never to the corpus.
                mtf = (payload.metadata or {}).get("multi_timeframe")
                if isinstance(mtf, dict):
                    mtf.pop("demoted_to_hold", None)

            out = ens.generate_signal(payload, current_price=price, capital=None)
            rejection = ens.last_rejection

            if out is None:
                rows.append(
                    {
                        "scenario": name,
                        "admitted": False,
                        "signal_produced": False,
                        "cause": rejection.cause if rejection else "unknown",
                    }
                )
                continue

            consistent = stops_ok(out.action, price, out.stop_loss, out.take_profit)
            rows.append(
                {
                    "scenario": name,
                    "admitted": bool(consistent),
                    "signal_produced": True,
                    "cause": None if consistent else REJECT_PREFILL_STOPS,
                    "action": out.action.value,
                    "confidence": round(out.confidence, 6),
                    "stop_loss": round(out.stop_loss, 6),
                    "take_profit": round(out.take_profit, 6),
                    "legs": dict(sorted(out.leg_actions.items())),
                }
            )

    causes: Dict[str, int] = {}
    for row in rows:
        if row["cause"]:
            causes[row["cause"]] = causes.get(row["cause"], 0) + 1

    return {
        "arm": arm,
        "payloads": len(rows),
        "signals_produced": sum(1 for r in rows if r["signal_produced"]),
        "admitted": sum(1 for r in rows if r["admitted"]),
        "rejections": dict(sorted(causes.items())),
        "leg_weights": {k: round(v, 6) for k, v in sorted(weights.items())},
        "rows": rows,
    }


def digest(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            return "sha256:" + hashlib.sha256(fh.read()).hexdigest()
    except FileNotFoundError:
        return "absent (no such file)"
    except OSError as exc:
        return f"unreadable ({exc.__class__.__name__})"


def summary_line(result: Dict[str, Any]) -> str:
    causes = ", ".join(f"{k}={v}" for k, v in result["rejections"].items()) or "none"
    return (
        f"{result['arm']:<9} payloads={result['payloads']:<3} "
        f"signals={result['signals_produced']:<3} admitted={result['admitted']:<3} "
        f"rejections[{causes}]"
    )


def render(results: List[Dict[str, Any]]) -> str:
    all_causes: List[str] = []
    for res in results:
        for cause in res["rejections"]:
            if cause not in all_causes:
                all_causes.append(cause)
    all_causes.sort()

    head = f"| {'arm':<9} | payloads | signals | admitted | " + " | ".join(
        f"{c}" for c in all_causes
    )
    lines = [head, "|" + "-" * (len(head) - 1)]
    for res in results:
        cells = " | ".join(str(res["rejections"].get(c, 0)) for c in all_causes)
        lines.append(
            f"| {res['arm']:<9} | {res['payloads']:<8} | {res['signals_produced']:<7} "
            f"| {res['admitted']:<8} | {cells}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Four-arm ablation of the Phase 21 ensemble-admission changes"
    )
    parser.add_argument(
        "--arms",
        default="all",
        help="'all' or a comma-separated subset of: " + ", ".join(ARMS),
    )
    parser.add_argument("--json", dest="json_path", help="write machine-readable output here")
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="recorded for the record; this harness uses no randomness",
    )
    parser.add_argument("--verbose", action="store_true", help="show the ensemble's own logging")
    parser.add_argument(
        "--check-determinism",
        action="store_true",
        help="re-run every arm in REVERSE order and assert identical results",
    )
    args = parser.parse_args()

    logging.disable(logging.NOTSET if args.verbose else logging.CRITICAL)

    arms = ARMS if args.arms == "all" else tuple(a.strip() for a in args.arms.split(","))
    unknown = [a for a in arms if a not in ARMS]
    if unknown:
        parser.error(f"unknown arm(s): {unknown}; choose from {list(ARMS)}")

    # Repointing STATE_PATH here means the live file is never opened by this run.
    # It is digested anyway so "it did not move" is evidence, not an assurance.
    scratch = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".ablation_weights_never_written.json"
    )
    weights_before = digest(LIVE_WEIGHTS_PATH)

    # The REAL pre-fill admission predicate, imported rather than re-implemented.
    from app.auto_trader import AutoTrader

    stops_ok = AutoTrader._ensemble_stops_are_consistent

    results = [run_arm(arm, scratch, stops_ok) for arm in arms]

    determinism = None
    if args.check_determinism:
        replay = [run_arm(arm, scratch, stops_ok) for arm in reversed(arms)]
        replay.reverse()
        determinism = replay == results

    weights_after = digest(LIVE_WEIGHTS_PATH)

    print(f"seed={args.seed} (unused - no randomness in this harness)")
    print(f"corpus=constructed payloads (n={len(build_corpus())})")
    print(f"{LIVE_WEIGHTS_PATH} before: {weights_before}")
    print(f"{LIVE_WEIGHTS_PATH} after : {weights_after}")
    print(f"scratch weights path      : {scratch} (exists={os.path.exists(scratch)})")
    print()
    print(render(results))
    print()
    for res in results:
        print(summary_line(res))
    if determinism is not None:
        print()
        print(f"determinism (reverse-order replay identical): {determinism}")

    payload = {
        "seed": args.seed,
        "corpus_source": "constructed payloads",
        "corpus_size": len(build_corpus()),
        "weights_digest_before": weights_before,
        "weights_digest_after": weights_after,
        "reverse_order_replay_identical": determinism,
        "arms": results,
    }
    if args.json_path:
        with open(args.json_path, "w") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        print(f"\nwrote {args.json_path}")

    if weights_before != weights_after:
        print("\nFAIL: the persisted leg-weight file moved during the run", file=sys.stderr)
        return 1
    if determinism is False:
        print("\nFAIL: reverse-order replay differed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
