"""
Signal Funnel — stage-by-stage instrumentation of the live trading path.

Created 2026-08-21 as the permanent answer to "the dashboard shows zeros and
nothing explains why". Before this module the only way to learn where signals
died was to grep 1,179 log lines by hand; the Hybrid Strategy Routing tile
could read `0 signals routed` for seven months without the system being able
to say whether that meant "no market opportunity" or "this code path is never
executed" (it was the latter — see docs/PIPELINE_MAP.md §0).

Design rules, enforced by tests/test_signal_funnel.py:

1. **No silent stages.** Every stage in ``STAGES`` is emitted on every
   snapshot even at zero, with ``evaluated``/``passed``/``rejected``. A stage
   that never ran is visibly ``evaluated: 0``, not absent.
2. **Every rejection carries numbers.** ``reject()`` REQUIRES a reason code
   and accepts the observed value and the threshold that rejected it. The
   snapshot reports count, min/mean/max of the observed values, and the
   threshold — so "rejected: confidence 0.2761 < 0.30 (84x, observed
   0.2761-0.2761)" is reconstructable without log access.
3. **No divide-by-zero masking.** Pass rates are ``None`` when the
   denominator is zero, never ``0.0``. A consumer that renders ``None`` as
   "n/a" tells the truth; one that renders 0.0 lies.
4. **Advisory stages are labelled.** ``passed_atr_filter`` is declared but
   marked ``advisory`` because the live pipeline has NO ATR reject — ATR
   feeds stops and confidence only (verified: ``aggregator_core.py`` never
   references atr_data in ``meets_requirements``). Recording it as a 100%
   pass gate without that label would manufacture a filter that does not
   exist.

Storage is a process-local singleton, same lifetime model as
``Phase1MetricsProvider`` and ``MarketRegimeDetector``. It is NOT durable
across container restarts — see docs/FINDINGS.md (FUNNEL-01).
"""

from __future__ import annotations

import logging
import math
import threading
from collections import Counter, deque
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

# Ordered funnel. Order is load-bearing: the API and the UI render it as a
# top-to-bottom cascade, and `terminal_stage` attribution assumes an
# evaluation dies at exactly one of these.
STAGES: List[str] = [
    "evaluations",
    "passed_risk_halt",
    "raw_signals_generated",
    "passed_price_lookup",
    "passed_indicator_agreement",
    "passed_gatekeeper",
    "passed_validator",
    "passed_regime_filter",
    "passed_category_diversity",
    "passed_consensus_count",
    "passed_confidence_floor",
    "passed_atr_filter",
    "routing_decision_made",
    "ensemble_signal_emitted",
    "passed_position_dedupe",
    "passed_cooldown",
    "passed_side_gate",
    "passed_signal_confidence_gate",
    "passed_daily_limit",
    "passed_stop_consistency",
    "passed_portfolio_heat",
    "order_intent_emitted",
]

# Stages that exist in the mission's funnel spec but are NOT gates in this
# codebase. Declared so the cascade is complete, labelled so nobody reads a
# 100% pass rate as evidence of a working filter.
ADVISORY_STAGES = {"passed_atr_filter"}

# The cascade is NOT monotonic and its stages do not share a denominator.
# The aggregator runs once per TIMEFRAME (15/60/240), so its stages count ~3x
# the per-evaluation stages around them. Without this label a reader compares
# "180/180" against "221/575" and concludes the funnel is broken. Emitted on
# every stage so the UI can say which population each rate is over.
STAGE_BASIS = {
    "evaluations": "per_evaluation",
    "passed_risk_halt": "per_evaluation",
    "raw_signals_generated": "per_evaluation",
    "passed_price_lookup": "per_evaluation",
    "passed_indicator_agreement": "per_timeframe_aggregation",
    "passed_gatekeeper": "per_timeframe_aggregation",
    "passed_validator": "per_timeframe_aggregation",
    "passed_regime_filter": "per_timeframe_aggregation",
    "passed_category_diversity": "per_timeframe_aggregation",
    "passed_consensus_count": "per_timeframe_aggregation",
    "passed_confidence_floor": "per_timeframe_aggregation",
    "passed_atr_filter": "per_evaluation",
    "routing_decision_made": "per_evaluation",
    "ensemble_signal_emitted": "per_evaluation",
    "passed_position_dedupe": "per_emitted_signal",
    "passed_cooldown": "per_emitted_signal",
    "passed_side_gate": "per_emitted_signal",
    "passed_signal_confidence_gate": "per_emitted_signal",
    "passed_daily_limit": "per_order_candidate",
    "passed_stop_consistency": "per_order_candidate",
    "passed_portfolio_heat": "per_order_candidate",
    "order_intent_emitted": "per_order_candidate",
}

# Named numeric series sampled for distribution reporting (Phase 3 needs the
# real distribution to set thresholds from, not a guessed constant).
DISTRIBUTION_SERIES = (
    "adx",
    "atr_pct",
    "aggregator_confidence",
    "ensemble_confidence",
    "aggregated_vote_score",
)

_SERIES_CAP = 20000
_EXAMPLE_CAP = 5


class _ReasonStat:
    """Per-reason rejection accounting, with the numbers that caused it."""

    __slots__ = ("count", "observed_min", "observed_max", "observed_sum",
                 "observed_n", "threshold", "examples")

    def __init__(self) -> None:
        self.count = 0
        self.observed_min: Optional[float] = None
        self.observed_max: Optional[float] = None
        self.observed_sum = 0.0
        self.observed_n = 0
        self.threshold: Optional[float] = None
        self.examples: Deque[str] = deque(maxlen=_EXAMPLE_CAP)

    def add(
        self,
        observed: Optional[float],
        threshold: Optional[float],
        detail: Optional[str],
    ) -> None:
        self.count += 1
        if observed is not None and not math.isnan(observed):
            self.observed_sum += observed
            self.observed_n += 1
            if self.observed_min is None or observed < self.observed_min:
                self.observed_min = observed
            if self.observed_max is None or observed > self.observed_max:
                self.observed_max = observed
        if threshold is not None:
            self.threshold = threshold
        if detail:
            self.examples.append(detail)

    def snapshot(self) -> Dict:
        return {
            "count": self.count,
            "threshold": self.threshold,
            "observed_min": self.observed_min,
            "observed_max": self.observed_max,
            "observed_mean": (
                self.observed_sum / self.observed_n if self.observed_n else None
            ),
            "examples": list(self.examples),
        }


class _StageStat:
    __slots__ = ("evaluated", "passed", "rejected", "reasons", "notes")

    def __init__(self) -> None:
        self.evaluated = 0
        self.passed = 0
        self.rejected = 0
        self.reasons: Dict[str, _ReasonStat] = {}
        # Observations that are NOT rejections: a stage that degrades a signal
        # without blocking it (the volume validator multiplies confidence by
        # 0.5-1.0 and never returns False). Kept out of `reasons` so
        # passed + rejected == evaluated always holds.
        self.notes: Dict[str, _ReasonStat] = {}

    def snapshot(self, name: str) -> Dict:
        return {
            "stage": name,
            "advisory": name in ADVISORY_STAGES,
            "basis": STAGE_BASIS.get(name, "unknown"),
            "evaluated": self.evaluated,
            "passed": self.passed,
            "rejected": self.rejected,
            # None, not 0.0 — see module docstring rule 3.
            "pass_rate_pct": (
                (self.passed / self.evaluated) * 100.0 if self.evaluated else None
            ),
            "rejection_reasons": {
                code: stat.snapshot()
                for code, stat in sorted(
                    self.reasons.items(), key=lambda kv: -kv[1].count
                )
            },
            "notes": {
                code: stat.snapshot()
                for code, stat in sorted(
                    self.notes.items(), key=lambda kv: -kv[1].count
                )
            },
        }


class SignalFunnel:
    """Process-singleton funnel recorder for the live signal path."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stages: Dict[str, _StageStat] = {s: _StageStat() for s in STAGES}
        self._series: Dict[str, Deque[float]] = {
            name: deque(maxlen=_SERIES_CAP) for name in DISTRIBUTION_SERIES
        }
        self._terminal_stage: Counter = Counter()
        self._terminal_by_symbol: Dict[str, Counter] = {}
        self._route_branches: Counter = Counter()
        self._route_adx: Deque[float] = deque(maxlen=_SERIES_CAP)
        self._started_at = datetime.now(timezone.utc)
        self._last_event_at: Optional[datetime] = None
        self._cycles = 0

    # ---------------------------------------------------------------- record

    def enter(self, stage: str, symbol: Optional[str] = None) -> None:
        """Mark that `stage` was reached and is about to be evaluated."""
        self._require_stage(stage)
        with self._lock:
            self._stages[stage].evaluated += 1
            self._last_event_at = datetime.now(timezone.utc)

    def passed(self, stage: str, symbol: Optional[str] = None) -> None:
        self._require_stage(stage)
        with self._lock:
            self._stages[stage].passed += 1
            self._last_event_at = datetime.now(timezone.utc)

    def reject(
        self,
        stage: str,
        reason: str,
        *,
        symbol: Optional[str] = None,
        observed: Optional[float] = None,
        threshold: Optional[float] = None,
        detail: Optional[str] = None,
    ) -> None:
        """Record a rejection. `reason` is REQUIRED — there is no anonymous
        rejection. `observed`/`threshold` are what the mission calls "the
        numeric values that caused it"; omit them only for genuinely
        non-numeric rejections (e.g. `already_open_position`)."""
        self._require_stage(stage)
        if not reason:
            raise ValueError(
                f"SignalFunnel.reject({stage!r}) called without a reason code — "
                "anonymous rejections are what this module exists to prevent"
            )
        if detail is None and observed is not None and threshold is not None:
            detail = f"{observed:.6g} vs threshold {threshold:.6g}"
        with self._lock:
            st = self._stages[stage]
            st.rejected += 1
            st.reasons.setdefault(reason, _ReasonStat()).add(
                observed, threshold, detail
            )
            self._terminal_stage[stage] += 1
            if symbol:
                self._terminal_by_symbol.setdefault(symbol, Counter())[stage] += 1
            self._last_event_at = datetime.now(timezone.utc)

    def note(
        self,
        stage: str,
        code: str,
        *,
        symbol: Optional[str] = None,
        observed: Optional[float] = None,
        threshold: Optional[float] = None,
        detail: Optional[str] = None,
    ) -> None:
        """Record something that happened at a stage WITHOUT rejecting.

        For filters that degrade rather than block — the volume validator
        multiplies confidence by 0.5-1.0 and never returns False. Its effect
        is real and must be visible, but counting it as a rejection would
        break `passed + rejected == evaluated` and overstate the filter.
        """
        self._require_stage(stage)
        if detail is None and observed is not None and threshold is not None:
            detail = f"{observed:.6g} vs {threshold:.6g}"
        with self._lock:
            self._stages[stage].notes.setdefault(code, _ReasonStat()).add(
                observed, threshold, detail
            )
            self._last_event_at = datetime.now(timezone.utc)

    def gate(
        self,
        stage: str,
        ok: bool,
        *,
        reason: str = "",
        symbol: Optional[str] = None,
        observed: Optional[float] = None,
        threshold: Optional[float] = None,
        detail: Optional[str] = None,
    ) -> bool:
        """enter() + passed()/reject() in one call. Returns `ok` unchanged so
        it can wrap an existing predicate without restructuring control flow."""
        self.enter(stage, symbol=symbol)
        if ok:
            self.passed(stage, symbol=symbol)
        else:
            self.reject(
                stage,
                reason or f"{stage}_failed",
                symbol=symbol,
                observed=observed,
                threshold=threshold,
                detail=detail,
            )
        return ok

    def record_route(self, branch: str, adx: Optional[float]) -> None:
        """Record an advisory or executed routing decision.

        `branch` is `trend_following` | `mean_reversion` | `unknown`.
        """
        with self._lock:
            self._route_branches[branch] += 1
            if adx is not None and not math.isnan(adx):
                self._route_adx.append(float(adx))
                self._series["adx"].append(float(adx))
            self._last_event_at = datetime.now(timezone.utc)

    def observe(self, series: str, value: Optional[float]) -> None:
        """Sample a numeric series for distribution reporting."""
        if value is None:
            return
        try:
            v = float(value)
        except (TypeError, ValueError):
            return
        if math.isnan(v) or math.isinf(v):
            return
        if series not in self._series:
            # Unknown series is a programming error, not a runtime condition.
            raise KeyError(
                f"unknown funnel series {series!r}; add it to DISTRIBUTION_SERIES"
            )
        with self._lock:
            self._series[series].append(v)

    def start_cycle(self) -> None:
        with self._lock:
            self._cycles += 1

    # ------------------------------------------------------------------ read

    def snapshot(self) -> Dict:
        with self._lock:
            stages = [self._stages[name].snapshot(name) for name in STAGES]
            routes = dict(self._route_branches)
            route_total = sum(routes.values())
            distributions = {
                name: _describe(list(vals)) for name, vals in self._series.items()
            }
            terminal = dict(self._terminal_stage)
            by_symbol = {
                sym: dict(counter)
                for sym, counter in self._terminal_by_symbol.items()
            }
            started = self._started_at
            last = self._last_event_at
            cycles = self._cycles

        return {
            "schema_version": 1,
            "started_at": started.isoformat(),
            "last_event_at": last.isoformat() if last else None,
            "cycles": cycles,
            "stages": stages,
            "routing": {
                "total_decisions": route_total,
                "branches": routes,
                "trend_following": routes.get("trend_following", 0),
                "mean_reversion": routes.get("mean_reversion", 0),
                "unknown": routes.get("unknown", 0),
                # Rolling: `_route_adx` is a bounded deque (_SERIES_CAP), so
                # this is the most recent N routing decisions, not lifetime.
                "adx_distribution_window": _SERIES_CAP,
                "adx_distribution": _describe(list(self._route_adx)),
            },
            "distributions": distributions,
            "terminal_stage": terminal,
            "terminal_stage_by_symbol": by_symbol,
        }

    def reset(self) -> None:
        """Test hook. Never called from the trading path."""
        with self._lock:
            self._stages = {s: _StageStat() for s in STAGES}
            for d in self._series.values():
                d.clear()
            self._terminal_stage.clear()
            self._terminal_by_symbol.clear()
            self._route_branches.clear()
            self._route_adx.clear()
            self._started_at = datetime.now(timezone.utc)
            self._last_event_at = None
            self._cycles = 0

    # --------------------------------------------------------------- private

    @staticmethod
    def _require_stage(stage: str) -> None:
        if stage not in STAGES:
            raise KeyError(
                f"unknown funnel stage {stage!r}; add it to STAGES so it is "
                "emitted even at zero"
            )


def _describe(values: List[float]) -> Dict:
    """min/p25/median/p75/max — the shape Phase 3 sets thresholds from."""
    n = len(values)
    if n == 0:
        return {"n": 0, "min": None, "p25": None, "median": None,
                "p75": None, "max": None, "mean": None}
    s = sorted(values)

    def q(frac: float) -> float:
        if n == 1:
            return s[0]
        pos = frac * (n - 1)
        lo = int(math.floor(pos))
        hi = int(math.ceil(pos))
        if lo == hi:
            return s[lo]
        return s[lo] + (s[hi] - s[lo]) * (pos - lo)

    return {
        "n": n,
        "min": s[0],
        "p25": q(0.25),
        "median": q(0.5),
        "p75": q(0.75),
        "max": s[-1],
        "mean": sum(s) / n,
    }


_funnel: Optional[SignalFunnel] = None


def get_signal_funnel() -> SignalFunnel:
    """Process-local singleton."""
    global _funnel
    if _funnel is None:
        _funnel = SignalFunnel()
        logger.info(
            "SignalFunnel initialized: %d stages, %d distribution series",
            len(STAGES),
            len(DISTRIBUTION_SERIES),
        )
    return _funnel
