"""
MultiStrategyEnsemble — combine SimpleRSI + multi-indicator (aggregator) + MeanReversion.

Each leg returns its own (action, confidence). The ensemble:
  1. Polls all three.
  2. Weights each leg by its recent realized win rate (EMA over closed trades).
  3. Aggregates into a single weighted score; |score| > threshold → BUY/SELL.
  4. Picks SL/TP from the dominant leg (most weighted contribution).
  5. Tags the trade with a per-leg attribution dict so PerformanceTracker can update weights when the position closes.

Capital allocation is shaped by the ensemble's *total* weighted confidence: high-conviction
agreements (all 3 legs vote the same way) get full sizing; partial agreement gets scaled-down sizing.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import logging
import math
import json
import os
import threading
import time

from app.aggregation.voter import INDICATOR_CATEGORIES, SignalVoter
from app.models.signal import IndicatorSignal, TradingSignal
from app.models.enums import SignalAction
from app.strategies.simple_rsi_strategy import SimpleRSIStrategy
from app.strategies.mean_reversion_strategy import (
    MeanReversionStrategy,
)

logger = logging.getLogger(__name__)


LEG_RSI = "simple_rsi"
LEG_MULTI = "multi_indicator"
LEG_MEAN_REV = "mean_reversion"

# ---------------------------------------------------------------------------
# LEG SOURCE-DIVERSITY TAXONOMY - P21-2, 2026-08-27.
#
# ONE taxonomy, reused, never restated. `voter.INDICATOR_CATEGORIES` is the
# single source of truth for which indicator belongs to which category, and the
# reason is measured: MACD was re-bucketed from MOMENTUM to TREND on 2026-08-23
# because the old bucketing let the aggregator's diversity gate report "trend +
# momentum confirmation" when it had trend + trend - MACD was the sole non-TREND
# agreeing voter on 712 of 1,924 diversity passes over 8h of live logs
# (.planning/evidence/hold-funnel-2026-08-22.md). A second map declared here
# would drift from that one in exactly the same way, and just as silently.
# ---------------------------------------------------------------------------

# Every indicator name the shared taxonomy knows, DERIVED from it rather than
# listed again, so a name added to voter.INDICATOR_CATEGORIES is automatically
# known here.
_KNOWN_INDICATOR_NAMES = frozenset().union(*INDICATOR_CATEGORIES.values())

_category_voter: Optional[SignalVoter] = None


def _indicator_category(name: str) -> str:
    """`voter.SignalVoter.get_indicator_category`, through one shared instance.

    Upstream the lookup is a method rather than a module-level function, so
    this holds a single lazily-built voter instead of constructing one per
    call. It is deliberately NOT a local re-implementation - see the block
    comment above for the measured cost of a second taxonomy.
    """
    global _category_voter
    if _category_voter is None:
        _category_voter = SignalVoter()
    return _category_voter.get_indicator_category(name)


def _mean_reversion_source(sub_signal: str) -> Optional[str]:
    """Map a `MeanReversionSignal.indicators_aligned` entry to its indicator.

    The leg publishes WHICH SUB-SIGNALS fired (mean_reversion_strategy.py
    :150-209), not which indicators it read, so the mapping is by prefix:

        RSI_*        -> RSI              (RSI_EXTREME, RSI_OVERSOLD, ...)
        BB_*         -> BOLLINGER_BANDS  (BB_LOWER, BB_NEAR_UPPER, ...)
        PRICE_*_SMA  -> SMA              (PRICE_BELOW_SMA, PRICE_EXTREME_*)

    Written against `indicators_aligned` on purpose, NOT against an assumption
    that Bollinger is always present: since Plan 21-03 threaded a real ATR into
    this leg, the SMA-deviation branch (gated on `atr_value > 0`, previously
    dead code) is a second live firing route whose categories are
    {MOMENTUM, TREND} rather than {MOMENTUM, VOLATILITY}.

    Returns None for anything else. An unrecognised token must NOT resolve to
    "OTHER": `voter.calculate_category_consensus` counts OTHER as an agreeing
    category, which at the LEG level would hand a single-source leg a free
    second category and switch this guard off with nothing going red. Dropping
    it instead errs strict, which is the safe direction, and
    tests/strategies/test_ensemble_diversity_guard.py scans the leg's own
    source file for tokens this function does not know.
    """
    if sub_signal.startswith("RSI_"):
        return "RSI"
    if sub_signal.startswith("BB_"):
        return "BOLLINGER_BANDS"
    if sub_signal.startswith("PRICE_") and sub_signal.endswith("_SMA"):
        return "SMA"
    return None


# Sentinel meaning "this leg has no usable stop/target level".
#
# The multi-indicator leg used to read flat metadata["atr_stop_loss"] /
# ["atr_take_profit"] keys that NOTHING in production ever wrote. The
# aggregator stores its ATR payload nested, as metadata["atr"], keyed
# stop_loss_long / stop_loss_short / take_profit_long / take_profit_short
# (aggregator_core.py `_build_metadata`, populated from
# signal_aggregator.fetch_atr). So the dict.get() default fired on every
# signal and the leg's stop landed on current_price — a ZERO-WIDTH stop.
#
# When the levels are genuinely absent we must not invent one. A plausible
# fabricated level (entry x 0.98, say) is indistinguishable downstream from a
# real ATR level: it would override the risk manager's own default with a
# number nobody chose, and it would look correct in the Telegram message and
# in the DB row. 0.0 is instead rejected by
# AutoTrader._ensemble_stops_are_consistent's explicit `stop_loss <= 0`
# branch — a check written to reject it, not an accident of NaN comparison
# semantics — so the entry is refused pre-fill with an ERROR naming the
# symbol, and no position is opened against an unknown risk model.
UNUSABLE_LEVEL = 0.0


def _atr_is_usable(atr_data) -> bool:
    """One presence predicate for ATR, shared by every leg in this ensemble.

    P21-1, 2026-08-26. The ATR failure payload is NOT empty. When the TA
    service cannot compute an ATR it returns `atr.py::_default_response()`,
    which sets `atr` and `atr_pct` to 0.0 while POPULATING
    stop_loss_long/short at a hardcoded 3% (atr.py:129-146). Read naively,
    that one payload gave three different answers:

      * `_atr_levels` read the populated stops and traded a 3% stop nobody
        chose, presented as if it were a real ATR level;
      * `simple_rsi` read `atr_pct == 0.0` and fell back to its own 2%;
      * `mean_reversion` read `atr == 0.0` and skipped its SMA-deviation
        sub-signals entirely.

    Keying on `atr > 0 and atr_pct > 0` makes all three agree. A zero ATR is
    not a volatility reading — it is the marker of a failed fetch, and the
    only honest response is to treat it as absent (21-RESEARCH.md Option 1).

    No threshold value changed.
    """
    if not isinstance(atr_data, dict):
        return False
    try:
        atr = float(atr_data.get("atr"))
        atr_pct = float(atr_data.get("atr_pct"))
    except (TypeError, ValueError):
        return False
    # NaN fails both comparisons, which is the intended answer.
    return atr > 0.0 and atr_pct > 0.0


# ---------------------------------------------------------------------------
# STRUCTURED REJECTION CAUSES - Plan 21-06 Task 2, 2026-08-27.
#
# `generate_signal` signals every rejection the same way: it returns None. The
# trade funnel recorded that as ONE gate with a fixed
# reason="ensemble_returned_hold" and a detail naming only two causes
# ("weighted score below AGGREGATION_THRESHOLD or fewer than MIN_AGREEING_LEGS
# fired"). After Plan 21-05's MTF gate and Plan 21-06's diversity guard there
# are FIVE, so that string was factually wrong for three of them - decorative
# telemetry of exactly the kind signal_funnel.py's own module comment exists to
# prevent, and an attribution the Plan 21-09 ablation cannot make.
#
# 21-RESEARCH.md Pitfall 5 requires the choice between (a) a structured cause
# wired into the funnel and (b) parsing log lines to be STATED. This is (a).
# Log parsing would tie the funnel's schema to prose that no test pins.
#
# Identifiers are stable snake_case so the funnel and any later analysis can
# group on them. `SignalFunnel.reject`'s `reason` is a free-form dict key
# (signal_funnel.py: `st.reasons.setdefault(reason, _ReasonStat())`), NOT a
# constrained set, so adding values needs no schema change and no downstream
# consumer can silently drop one for being unknown.
#
# This changes no gate, no threshold and no admission decision.
# ---------------------------------------------------------------------------

REJECT_MTF_DEMOTED = "mtf_demoted"
REJECT_REGIME_BLOCKED = "regime_blocked"
REJECT_NO_DIRECTIONAL_LEGS = "no_directional_legs"
REJECT_INSUFFICIENT_DIVERSITY = "insufficient_category_diversity"
REJECT_INSUFFICIENT_AGREEING_LEGS = "insufficient_agreeing_legs"
REJECT_SCORE_BELOW_THRESHOLD = "score_below_threshold"


@dataclass(frozen=True)
class EnsembleRejection:
    """Why `generate_signal` returned None, in a form the funnel can group on."""

    cause: str
    detail: str


@dataclass
class EnsembleSignal:
    action: SignalAction
    confidence: float  # weighted score magnitude, [0, 1]
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size_pct: float  # ensemble-recommended size as % of capital
    reasoning: List[str] = field(default_factory=list)
    leg_contributions: Dict[str, float] = field(
        default_factory=dict
    )  # leg_id → signed contribution
    leg_actions: Dict[str, str] = field(default_factory=dict)
    weights_snapshot: Dict[str, float] = field(default_factory=dict)


class StrategyPerformanceWeights:
    """Per-leg weights derived from recent realized P&L, persisted to disk so weights survive restarts.

    Weight update rule (EMA on win indicator):
        w_new = (1-α) * w_old + α * outcome
    where outcome = 1 if win, 0 if loss; α = 0.10 (10 trades to converge).
    Weights are normalized to [0.10, 1.0] so a leg never goes fully silent.
    """

    STATE_PATH = "/app/data/ensemble_weights.json"
    ALPHA = 0.10
    MIN_WEIGHT = 0.10
    DEFAULT_WIN_RATE = 0.50

    def __init__(self):
        self._lock = threading.Lock()
        self._win_rates: Dict[str, float] = {
            LEG_RSI: self.DEFAULT_WIN_RATE,
            LEG_MULTI: self.DEFAULT_WIN_RATE,
            LEG_MEAN_REV: self.DEFAULT_WIN_RATE,
        }
        self._trade_counts: Dict[str, int] = {LEG_RSI: 0, LEG_MULTI: 0, LEG_MEAN_REV: 0}
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self.STATE_PATH):
                with open(self.STATE_PATH, "r") as f:
                    data = json.load(f)
                # Schema-validate before adopting. A corrupt-but-valid-JSON
                # file (non-numeric win rate, foreign leg key) would pass a
                # blind dict.update here and detonate later as a TypeError
                # inside normalized_weights — ON THE SIGNAL PATH. Known leg
                # ids are the keys of _win_rates as initialized in __init__;
                # invalid entries are skipped (that leg keeps its default).
                for leg_id, rate in (data.get("win_rates") or {}).items():
                    if (
                        leg_id in self._win_rates
                        and isinstance(rate, (int, float))
                        and not isinstance(rate, bool)
                        and 0.0 <= rate <= 1.0
                    ):
                        self._win_rates[leg_id] = float(rate)
                    else:
                        logger.warning(
                            f"[ENSEMBLE] Ignoring invalid win_rates entry "
                            f"{leg_id!r}={rate!r} in {self.STATE_PATH}; "
                            f"default retained for that leg"
                        )
                for leg_id, count in (data.get("trade_counts") or {}).items():
                    if (
                        leg_id in self._trade_counts
                        and isinstance(count, int)
                        and not isinstance(count, bool)
                        and count >= 0
                    ):
                        self._trade_counts[leg_id] = count
                    else:
                        logger.warning(
                            f"[ENSEMBLE] Ignoring invalid trade_counts entry "
                            f"{leg_id!r}={count!r} in {self.STATE_PATH}; "
                            f"default retained for that leg"
                        )
                logger.info(f"[ENSEMBLE] Loaded weights: {self._win_rates}")
        except Exception as e:
            logger.warning(f"[ENSEMBLE] Could not load weights state: {e}")

    def _persist(self) -> None:
        # Atomic write (tmp + os.replace): a torn write on trade close would
        # parse as corrupt JSON at next boot and silently reset learning to
        # the 1/3 defaults. os.replace is atomic on the same filesystem.
        try:
            os.makedirs(os.path.dirname(self.STATE_PATH), exist_ok=True)
            tmp_path = self.STATE_PATH + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(
                    {
                        "win_rates": self._win_rates,
                        "trade_counts": self._trade_counts,
                        "ts": time.time(),
                    },
                    f,
                )
            os.replace(tmp_path, self.STATE_PATH)
        except Exception as e:
            logger.warning(f"[ENSEMBLE] Could not persist weights state: {e}")

    def normalized_weights(self) -> Dict[str, float]:
        with self._lock:
            raw = {k: max(self.MIN_WEIGHT, v) for k, v in self._win_rates.items()}
            total = sum(raw.values())
            if total == 0:
                return {k: 1.0 / len(raw) for k in raw}
            return {k: v / total for k, v in raw.items()}

    def record_outcome(self, leg_id: str, won: bool) -> None:
        with self._lock:
            if leg_id not in self._win_rates:
                return
            outcome = 1.0 if won else 0.0
            self._win_rates[leg_id] = (1 - self.ALPHA) * self._win_rates[
                leg_id
            ] + self.ALPHA * outcome
            self._trade_counts[leg_id] += 1
            self._persist()
        logger.info(
            f"[ENSEMBLE] Updated {leg_id}: win_rate={self._win_rates[leg_id]:.3f} "
            f"(n={self._trade_counts[leg_id]}, won={won})"
        )

    def snapshot(self) -> Dict[str, Dict]:
        with self._lock:
            return {
                "win_rates": dict(self._win_rates),
                "trade_counts": dict(self._trade_counts),
                "weights": self.normalized_weights(),
            }


_weights_singleton: Optional[StrategyPerformanceWeights] = None


def get_ensemble_weights() -> StrategyPerformanceWeights:
    global _weights_singleton
    if _weights_singleton is None:
        _weights_singleton = StrategyPerformanceWeights()
    return _weights_singleton


class MultiStrategyEnsemble:
    """Combines three strategies with performance-weighted voting."""

    AGGREGATION_THRESHOLD = (
        0.10  # |weighted_score| ≥ this → fire trade (lowered for active markets)
    )
    MIN_AGREEING_LEGS = (
        1  # at least 1 leg must fire (ensemble still applies aggregation_threshold)
    )
    # Minimum number of distinct INDICATOR CATEGORIES the directionally-agreeing
    # legs must span. NOT a new knob and NOT a threshold change: it is the value
    # CoreAggregator already applies one level up, via
    # voter.check_category_diversity(..., min_categories=2). Mirrored here so
    # the same rule reaches leg-level agreement, which the aggregator never saw.
    MIN_LEG_CATEGORIES = 2

    def __init__(self, mean_reversion: Optional[MeanReversionStrategy] = None):
        self.simple_rsi = SimpleRSIStrategy()
        self.mean_reversion = mean_reversion or MeanReversionStrategy()
        self.weights = get_ensemble_weights()
        # Why the LAST generate_signal call returned None, or None when the
        # last call produced a signal. Read by
        # auto_trader._check_and_trade_ensemble; reset at the top of every
        # generate_signal so a value from the previous symbol can never be
        # reported as this one's cause.
        self.last_rejection: Optional[EnsembleRejection] = None
        logger.info(
            f"MultiStrategyEnsemble initialized: legs=[{LEG_RSI}, {LEG_MULTI}, {LEG_MEAN_REV}], "
            f"threshold={self.AGGREGATION_THRESHOLD}, min_agreeing={self.MIN_AGREEING_LEGS}, "
            f"weights={self.weights.normalized_weights()}"
        )

    @property
    def MAX_POSITION_PCT(self) -> float:
        """Ceiling for ensemble sizing. Bound to settings.max_risk_per_trade
        so operator-set caps (ADR-010 paper bump, LIVE 2% reset) actually
        propagate into ensemble decisions instead of being shadowed by a
        hard-coded class constant.
        """
        from app.config import get_settings

        return get_settings().max_risk_per_trade

    @staticmethod
    def _atr_levels(aggregator_signal: TradingSignal) -> Tuple[float, float]:
        """Side-aware (stop_loss, take_profit) for the multi-indicator leg.

        Reads the aggregator's real payload — nested `metadata["atr"]`, keyed
        `stop_loss_long` / `stop_loss_short` / `take_profit_long` /
        `take_profit_short`. Mirrors sqzmom_strategy_integration.py, the one
        place in this codebase that already reads that payload correctly.

        Returns `(UNUSABLE_LEVEL, UNUSABLE_LEVEL)` when the payload is absent
        or incomplete — see the constant for why that beats a fabricated
        level. A missing payload means the aggregator produced no ATR data at
        all, which is itself a defect worth seeing, so it is logged loudly
        rather than swallowed.
        """
        symbol = getattr(aggregator_signal, "symbol", "?")
        action = aggregator_signal.action
        atr_data = (aggregator_signal.metadata or {}).get("atr")

        if not isinstance(atr_data, dict):
            logger.warning(
                f"[ENSEMBLE][ATR] {symbol}: aggregator emitted no metadata['atr'] "
                f"(got {type(atr_data).__name__}) for a {getattr(action, 'value', action)} "
                f"signal — {LEG_MULTI} leg has no stop/target. The ATR fetch in "
                f"signal_aggregator.fetch_atr most likely failed."
            )
            return UNUSABLE_LEVEL, UNUSABLE_LEVEL

        if not _atr_is_usable(atr_data):
            # The ATR failure payload (atr.py::_default_response). Its
            # stop_loss_long/short ARE populated, at a 3% default nobody
            # chose, so reading them here presented a failed fetch as a real
            # risk model. ERROR, not WARNING: a silently-substituted stop is
            # strictly worse than no stop, because the sentinel is rejected
            # pre-fill by AutoTrader._ensemble_stops_are_consistent while the
            # 3% default was traded.
            logger.error(
                f"[ENSEMBLE][ATR] {symbol}: metadata['atr'] is the ATR FAILURE "
                f"payload (atr={atr_data.get('atr')!r}, "
                f"atr_pct={atr_data.get('atr_pct')!r}) — its populated "
                f"stop_loss_long/short are a hardcoded 3% default, not a "
                f"reading. Treating ATR as ABSENT for every leg. The ATR fetch "
                f"in signal_aggregator.fetch_atr failed, or the TA service had "
                f"insufficient candles."
            )
            return UNUSABLE_LEVEL, UNUSABLE_LEVEL

        if action == SignalAction.BUY:
            raw_sl, raw_tp = (
                atr_data.get("stop_loss_long"),
                atr_data.get("take_profit_long"),
            )
        else:
            raw_sl, raw_tp = (
                atr_data.get("stop_loss_short"),
                atr_data.get("take_profit_short"),
            )

        try:
            if raw_sl is None or raw_tp is None:
                raise ValueError("missing key")
            return float(raw_sl), float(raw_tp)
        except (TypeError, ValueError):
            logger.warning(
                f"[ENSEMBLE][ATR] {symbol}: metadata['atr'] present but unusable for "
                f"{getattr(action, 'value', action)} — sl={raw_sl!r} tp={raw_tp!r}. "
                f"Keys available: {sorted(atr_data)}. {LEG_MULTI} leg has no "
                f"stop/target."
            )
            return UNUSABLE_LEVEL, UNUSABLE_LEVEL

    @staticmethod
    def _atr_indicator(aggregator_signal: TradingSignal) -> Optional[IndicatorSignal]:
        """Rebuild the aggregator's risk-only ATR payload as an IndicatorSignal.

        P21-1, 2026-08-26. `indicators["ATR"]` was never written by anything,
        so two of three ensemble legs were structurally ATR-blind:
        `simple_rsi` sized every stop off a hardcoded 2%, and
        `mean_reversion`'s SMA-deviation sub-signals (gated on
        `atr_value > 0`) could never fire. The ATR IS fetched — it just lands
        in `metadata["atr"]` because `fetch_all_indicators` deliberately
        diverts it out of the voting dict (signal_aggregator.py:832-841).

        One signal serves both consumers, which is why a single synthetic
        entry suffices:
          * `.value` is the ABSOLUTE ATR — `mean_reversion` divides by it
            (mean_reversion_strategy.py:143, :170) and needs price units;
          * metadata carries `atr_pct` (a PERCENT, verbatim from the wire)
            and `atr_fraction` (that percent / 100), which is what
            `simple_rsi` multiplies against price.

        Returns None rather than a fabricated ATR when the payload is
        unusable — the same doctrine as UNUSABLE_LEVEL above. A plausible
        invented ATR is indistinguishable downstream from a real reading.

        No threshold value changed.
        """
        symbol = getattr(aggregator_signal, "symbol", "?")
        atr_data = (aggregator_signal.metadata or {}).get("atr")

        if not _atr_is_usable(atr_data):
            logger.warning(
                f"[ENSEMBLE][ATR] {symbol}: no usable metadata['atr'] "
                f"(got {type(atr_data).__name__}) — the {LEG_RSI} and "
                f"{LEG_MEAN_REV} legs fall back to their own documented "
                f"defaults instead of a fabricated ATR."
            )
            return None

        try:
            atr_absolute = float(atr_data["atr"])
            atr_pct = float(atr_data["atr_pct"])
            raw_confidence = atr_data.get("confidence")
            confidence = 0.5 if raw_confidence is None else float(raw_confidence)
            # IndicatorSignal.confidence is validated ge=0.0 le=1.0; an
            # out-of-range payload would raise ValidationError ON THE SIGNAL
            # PATH, so clamp rather than trust the wire. NaN is not a
            # clampable value — min(1.0, nan) returns nan's operand order
            # dependent result and would launder a failed payload into full
            # confidence, so it takes the failure branch instead.
            if math.isnan(confidence):
                raise ValueError("confidence is NaN")
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError, KeyError):
            logger.warning(
                f"[ENSEMBLE][ATR] {symbol}: metadata['atr'] passed the presence "
                f"check but could not be cast. Keys available: "
                f"{sorted(atr_data)}. No synthetic ATR built."
            )
            return None

        return IndicatorSignal(
            name="ATR",
            signal=SignalAction.HOLD,
            confidence=confidence,
            value=atr_absolute,
            metadata={
                "atr": atr_absolute,
                # PERCENT, verbatim from the wire. technical-analysis
                # atr.py:91 computes (atr / current_price) * 100, and
                # atr.py:94 buckets atr_pct < 1.0 as LOW volatility — so
                # sub-1 values are a modelled regime, not a unit error.
                "atr_pct": atr_pct,
                # FRACTION. The declared unit contract for stop sizing; see
                # SimpleRSIStrategy._resolve_atr_fraction.
                "atr_fraction": atr_pct / 100.0,
                "volatility": atr_data.get("volatility"),
                # NOTE: `role` and `weight` are deliberately NOT set here, and
                # they would not be guards if they were. voter._is_non_voting
                # returns `role in {"GATEKEEPER", "VALIDATOR"}`, and a PRESENT
                # role short-circuits the NON_VOTING_NAMES fallback (which does
                # not contain "ATR" either). Stamping role="RISK" would make
                # this signal MORE likely to vote, not less. The only thing
                # keeping it away from the voter is the local-copy dispatch in
                # generate_signal below.
            },
        )

    def _reject(self, cause: str, detail: str) -> None:
        """Record the cause of a `generate_signal` rejection, then return None.

        One writer for every return-None path, so a new path cannot be added
        without a cause and quietly land back in the generic bucket.
        """
        self.last_rejection = EnsembleRejection(cause=cause, detail=detail)

    @staticmethod
    def _leg_indicator_names(leg_id: str, mean_reversion_signal) -> Optional[Set[str]]:
        """Which indicators a directionally-agreeing leg actually consumed.

        Returns None when the leg's sources cannot be resolved - the caller
        then FAILS OPEN (see `_check_leg_source_diversity`). `LEG_MULTI` never
        reaches here; the caller handles it as diverse by construction.
        """
        if leg_id == LEG_RSI:
            # simple_rsi_strategy.py:153 - `indicators.get("RSI")` is the ONLY
            # key this leg reads. Structural, not a heuristic: there is no
            # payload under which it consumes a second indicator, so its
            # category set is {MOMENTUM} by construction.
            return {"RSI"}

        if leg_id == LEG_MEAN_REV:
            aligned = getattr(mean_reversion_signal, "indicators_aligned", None)
            if not isinstance(aligned, (list, tuple, set)):
                return None
            names: Set[str] = set()
            for token in aligned:
                source = _mean_reversion_source(str(token))
                if source is None or source not in _KNOWN_INDICATOR_NAMES:
                    logger.warning(
                        f"[ENSEMBLE][DIVERSITY] unmapped {LEG_MEAN_REV} sub-signal "
                        f"{token!r} - it contributes no category. Add it to "
                        f"_mean_reversion_source (and to the source scan in "
                        f"tests/strategies/test_ensemble_diversity_guard.py) "
                        f"rather than letting it fall through."
                    )
                    continue
                names.add(source)
            return names or None

        return None

    def _check_leg_source_diversity(
        self,
        agreeing_leg_ids: List[str],
        mean_reversion_signal,
        action: SignalAction,
        symbol: str,
    ) -> Tuple[bool, int, str]:
        """Do the agreeing legs span >= MIN_LEG_CATEGORIES indicator categories?

        Shape mirrors `voter.check_category_diversity`: HOLD short-circuits,
        the comparison is `>=`, and a human-readable reason is returned
        alongside the boolean so the log line and the funnel detail read the
        same sentence.
        """
        # HOLD short-circuit, exactly as voter.check_category_diversity does it.
        # Reaching this with a zero weighted score means no leg took the winning
        # side at all; that rejection belongs to the MIN_AGREEING_LEGS gate, and
        # attributing it to diversity would corrupt the funnel's per-cause
        # counts - the one thing the Plan 21-09 ablation reads.
        if action == SignalAction.HOLD:
            return True, 0, "HOLD outcomes do not require leg source diversity"

        if LEG_MULTI in agreeing_leg_ids:
            return (
                True,
                self.MIN_LEG_CATEGORIES,
                f"Leg source diversity OK: {LEG_MULTI} agrees and is diverse by "
                f"construction (it already cleared CoreAggregator's "
                f"check_category_diversity(min_categories="
                f"{self.MIN_LEG_CATEGORIES}))",
            )

        categories: Set[str] = set()
        for leg_id in agreeing_leg_ids:
            names = self._leg_indicator_names(leg_id, mean_reversion_signal)
            if not names:
                # FAIL OPEN, and say so. A leg object whose sources cannot be
                # read is a shape problem, not a market condition; failing
                # CLOSED here would let one upstream change halt every signal
                # the engine emits, with no error to find it by - the same
                # doctrine Plan 21-05 applied to `demoted_to_hold`.
                #
                # This cannot defeat the guard's purpose. simple_rsi is
                # hardcoded to {"RSI"} and is always resolvable, and
                # mean_reversion cannot be single-source at all
                # (MIN_INDICATORS_ALIGNED = 2 requires a Bollinger or SMA
                # co-signal), so the case this guard exists to block never
                # takes this path.
                logger.warning(
                    f"[ENSEMBLE][DIVERSITY] {symbol}: could not resolve the "
                    f"indicator sources of agreeing leg {leg_id!r} - the leg "
                    f"source-diversity guard is SKIPPED for this evaluation "
                    f"(failing open). Agreeing legs: {sorted(agreeing_leg_ids)}."
                )
                return (
                    True,
                    0,
                    f"Leg source diversity NOT EVALUATED: sources of {leg_id!r} "
                    f"could not be resolved; failing open",
                )
            categories.update(_indicator_category(name) for name in names)

        count = len(categories)
        listed = ", ".join(sorted(categories)) or "none"
        if count >= self.MIN_LEG_CATEGORIES:
            return (
                True,
                count,
                f"Leg source diversity OK: {count} categories agree ({listed})",
            )
        return (
            False,
            count,
            f"Insufficient leg source diversity: {count}/"
            f"{self.MIN_LEG_CATEGORIES} categories ({listed}) across agreeing "
            f"legs {sorted(agreeing_leg_ids)} - single-source agreement is not "
            f"independent multi-leg confirmation",
        )

    def generate_signal(
        self,
        aggregator_signal: TradingSignal,
        current_price: float,
        capital: Optional[float] = None,
    ) -> Optional[EnsembleSignal]:
        """Aggregate signals from the three legs.

        `aggregator_signal` is the existing CoreAggregator output — it both gives us the
        multi-indicator leg directly AND provides the indicator dict the other legs need.

        Args:
            capital: Available capital. None (default) resolves to
                Settings.paper_initial_balance. P21-8: the old `= 100.0`
                default was the pre-2026-08-25 account size, reachable by
                every caller that omitted the argument. A bare `10000` would
                be numerically correct under ADR-029 and STILL a defect — it
                bypasses the declared config and silently decouples on the
                next re-scale. Resolved in the BODY, never as a default
                argument: Python evaluates those once at import, which freezes
                the value and hides it from the AST detector in
                tests/test_account_size_invariant.py.
        """
        # MTF DEMOTE-TO-HOLD GATE — P21-3, 2026-08-27.
        #
        # When consolidate_mtf_confidence() demotes a directional consensus to
        # HOLD (signal_aggregator.py:71-78 — no timeframe's GATED action agreed
        # with a consensus computed from PRE-gate scores), that decision reaches
        # this method through `primary_signal.action` and, since Plan 21-05
        # Task 2, through `metadata["multi_timeframe"]["demoted_to_hold"]`.
        #
        # The defect this closes: only ONE of the three legs honoured it, and
        # only incidentally. `multi_indicator` below is guarded on
        # `action != SignalAction.HOLD and confidence > 0`, so it happens to see
        # the demoted action. `simple_rsi` and `mean_reversion` are dispatched
        # off the indicator dict and never read `.action` at all, so they traded
        # straight past a system-level HOLD. Two of three legs overriding a
        # decision the aggregator already made is an admission path nobody
        # chose.
        #
        # NARROW BY CONSTRUCTION. This is keyed on the `demoted_to_hold` flag,
        # NOT on `aggregator_signal.action == SignalAction.HOLD`. The broad
        # reading is simpler and needs no metadata key, but `action == HOLD`
        # arrives from four distinct upstream causes — this demotion, a raw
        # consensus that was genuinely HOLD, the regime hard-block (the
        # `if regime_analysis:` block in signal_aggregator's
        # `get_trading_signal_multi_timeframe`, marked by its REGIME
        # HARD-BLOCK log line), and a per-timeframe requirements
        # gate resolving HOLD inside aggregator_core. Gating on the bare action
        # would collapse all four into one cause the funnel cannot tell apart.
        # P22.1-2 (DEFER-21-02, 2026-08-27): the regime hard-block IS now gated
        # — in the SEPARATE gate immediately below, keyed on its own top-level
        # `regime_blocked` flag and recording its own rejection reason. One gate
        # per cause is the whole point, and the bare-action reading is exactly
        # what would have destroyed it. The requirements gate remains ungated.
        #
        # IDENTITY CHECK, not truthiness. `demoted_to_hold` is an untyped entry
        # in a plain dict that now decides whether ANY trade is produced. A
        # truthiness test would let one malformed upstream value ("true", 1, a
        # stray non-empty string) silently halt every signal the engine emits,
        # with no error and no log to find it by. The non-dict guard above it
        # exists for the same reason: garbage must degrade to the pre-fix
        # behaviour, never to a global halt.
        #
        # NO THRESHOLD VALUE CHANGED. MIN_AGREEING_LEGS (1),
        # AGGREGATION_THRESHOLD (0.10) and min_signal_confidence (0.30) are
        # untouched — this is wiring, not tuning. The behavioural threshold lock
        # in tests/strategies/test_ensemble_confidence_units.py
        # (`-k threshold_lock`) was observed green before this gate landed and
        # must stay green after it.
        #
        # Expected effect: trade admission DECREASES. 21-CONTEXT authorises that
        # explicitly. It belongs to the "+gates" arm of the Plan 21-09 ablation,
        # not the "+ATR" arm.
        # RESET FIRST, before any branch can return. `get_ensemble()` is a
        # process singleton and auto_trader evaluates symbol after symbol in one
        # loop, so a cause left over from BTCUSDT would otherwise be reported as
        # ETHUSDT's (T-21-06-05).
        self.last_rejection = None

        symbol = getattr(aggregator_signal, "symbol", "?")
        mtf_meta = (aggregator_signal.metadata or {}).get("multi_timeframe")
        if not isinstance(mtf_meta, dict):
            mtf_meta = {}
        if mtf_meta.get("demoted_to_hold") is True:
            logger.info(
                "[ENSEMBLE] HOLD — multi-timeframe consolidation demoted the "
                "consensus to HOLD; all three legs suppressed. Previously only "
                "the multi_indicator leg honoured this (via its action != HOLD "
                "guard) while simple_rsi and mean_reversion never read .action. "
                f"consensus={mtf_meta.get('consensus_action')} "
                f"consolidated={mtf_meta.get('consolidated_action')}"
            )
            self._reject(
                REJECT_MTF_DEMOTED,
                f"multi-timeframe consolidation demoted the consensus to HOLD "
                f"(consensus={mtf_meta.get('consensus_action')!r}, "
                f"consolidated={mtf_meta.get('consolidated_action')!r})",
            )
            return None

        # REGIME HARD-BLOCK GATE — P22.1-2 (DEFER-21-02), 2026-08-27.
        #
        # The last of the four HOLD causes above to get a consumer. When
        # market_regime.apply_regime_adjustment hard-blocks a counter-trend
        # consensus, signal_aggregator records the decision as a TOP-LEVEL
        # `metadata["regime_blocked"]` bool and forces the action to HOLD
        # (in `get_trading_signal_multi_timeframe`'s `if regime_analysis:`
        # block, marked by the REGIME HARD-BLOCK log line — an anchor, not a
        # line number, because line citations into that file have rotted
        # repeatedly). Half the machinery already existed:
        # the aggregator wrote the flag, nothing read it.
        #
        # The defect this closes is identical in shape to the MTF one above.
        # `multi_indicator` honours the block only incidentally, through its own
        # guard further down. `simple_rsi` and `mean_reversion` are dispatched
        # off the indicator dict and never read the aggregator's decision at
        # all, so two of three legs traded straight past a system-level
        # rejection. Measured before the fix, on a blocked payload: both legs
        # dispatched once each (the RED run of
        # tests/strategies/test_ensemble_confidence_units.py).
        #
        # NARROW BY CONSTRUCTION. Keyed on the `regime_blocked` flag, never on
        # `aggregator_signal.action == SignalAction.HOLD`. The paragraph above
        # says why collapsing the four causes is not on offer; the narrowness
        # pin in tests/strategies/test_ensemble_confidence_units.py drives a
        # HOLD carrying no regime flag through to both legs and fails if this
        # ever widens.
        #
        # IDENTITY CHECK, not truthiness, and FAIL OPEN on the container. This
        # is an untyped entry in a plain dict that now decides whether ANY trade
        # is produced. A truthiness test would let one malformed upstream value
        # (the string "true", a stray 1) silently halt every signal the engine
        # emits, with no error and no log to find it by — a denial of service
        # wearing the costume of a risk control. The `or {}` covers a missing
        # metadata container for the same reason: garbage must degrade to the
        # pre-fix behaviour, never to a global halt. Unlike the MTF flag this
        # one is top-level, so no isinstance layer is needed.
        #
        # NO THRESHOLD VALUE CHANGED. MIN_AGREEING_LEGS (1),
        # AGGREGATION_THRESHOLD (0.10) and min_signal_confidence (0.30) are
        # untouched — this adds a consumer for a flag that already existed, it
        # tunes nothing. The behavioural threshold lock in
        # tests/strategies/test_ensemble_confidence_units.py (`-k threshold_lock`)
        # was observed green before this gate landed and must stay green after.
        #
        # EXPECTED EFFECT: trade admission DECREASES — fewer trades in
        # counter-trend regimes. The operator ratified that direction on
        # 2026-08-27 (22.1-CONTEXT item A); no ablation is required, this is the
        # same class as the already-measured MTF gate. It is a wiring fix and no
        # P&L or edge claim attaches to it.
        signal_metadata = aggregator_signal.metadata or {}
        if signal_metadata.get("regime_blocked") is True:
            regime_reason = signal_metadata.get("regime_adjustment_reason")
            logger.info(
                f"[ENSEMBLE] HOLD — the regime hard-block rejected {symbol}; "
                "all three legs suppressed. Previously only the multi_indicator "
                "leg honoured it (via its own guard) while simple_rsi and "
                "mean_reversion never read the aggregator's decision. "
                f"reason={regime_reason}"
            )
            self._reject(
                REJECT_REGIME_BLOCKED,
                f"the regime hard-block rejected this consensus "
                f"(reason={regime_reason!r})",
            )
            return None

        # Resolved ONCE, here, and passed down to every leg. Letting two legs
        # resolve independently while a third receives a pass-through is how
        # one signal ends up sized against two different account figures.
        if capital is None:
            from app.config import get_settings

            capital = get_settings().paper_initial_balance
        # LOCAL SHALLOW COPY — this is the entire safety mechanism, do not
        # weaken it into an in-place write.
        #
        # P21-1, 2026-08-26. `aggregator_signal.indicators` is the SAME object
        # handed to hybrid_strategy.observe_regime (auto_trader.py:4703) and
        # reachable from aggregation/signal_cache.py. `fetch_all_indicators`
        # diverts ATR out of that dict on purpose (signal_aggregator.py:832-841)
        # precisely so it never reaches the voter. Injecting the synthetic ATR
        # into a copy gives the legs the reading they need while leaving the
        # shared object byte-identical. Metadata stamps such as role="RISK" or
        # weight=0.0 are NOT substitutes — see the note in _atr_indicator.
        indicators = dict(aggregator_signal.indicators or {})

        atr_indicator = self._atr_indicator(aggregator_signal)
        if atr_indicator is not None:
            indicators["ATR"] = atr_indicator

        leg_signals: Dict[str, Tuple[SignalAction, float, float, float, List[str]]] = {}

        # Leg 1: Simple RSI
        rsi_sig = self.simple_rsi.generate_signal(indicators, current_price, capital)
        if rsi_sig:
            leg_signals[LEG_RSI] = (
                rsi_sig.action,
                rsi_sig.confidence,
                rsi_sig.stop_loss,
                rsi_sig.take_profit,
                rsi_sig.reasoning,
            )

        # Leg 2: Multi-indicator (the existing CoreAggregator output)
        if (
            aggregator_signal.action != SignalAction.HOLD
            and aggregator_signal.confidence > 0
        ):
            atr_sl, atr_tp = self._atr_levels(aggregator_signal)
            multi_reasoning = [
                f"Aggregator score={aggregator_signal.aggregated_score:.3f}, consensus={aggregator_signal.consensus_count}"
            ]
            if atr_sl == UNUSABLE_LEVEL or atr_tp == UNUSABLE_LEVEL:
                multi_reasoning.append(
                    "ATR levels unavailable — leg votes but carries no usable "
                    "stop/target; the entry is rejected if this leg dominates"
                )
            leg_signals[LEG_MULTI] = (
                aggregator_signal.action,
                aggregator_signal.confidence,
                atr_sl,
                atr_tp,
                multi_reasoning,
            )

        # Leg 3: Mean reversion
        mr_sig = self.mean_reversion.generate_signal(indicators, current_price, capital)
        if mr_sig and mr_sig.action != SignalAction.HOLD:
            leg_signals[LEG_MEAN_REV] = (
                mr_sig.action,
                mr_sig.confidence,
                mr_sig.stop_loss,
                mr_sig.target,
                mr_sig.reasoning,
            )

        if not leg_signals:
            logger.info(
                f"[ENSEMBLE] HOLD — no legs fired. "
                f"agg_action={aggregator_signal.action.value} agg_conf={aggregator_signal.confidence:.2f}"
            )
            self._reject(
                REJECT_NO_DIRECTIONAL_LEGS,
                f"no leg produced a signal "
                f"(agg_action={aggregator_signal.action.value}, "
                f"agg_conf={aggregator_signal.confidence:.2f})",
            )
            return None

        weights = self.weights.normalized_weights()
        weighted_score = 0.0
        leg_contributions: Dict[str, float] = {}
        leg_actions: Dict[str, str] = {}

        # Denominator = the weight of the legs that actually took a side.
        #
        # 2026-08-23: this used to be implicit. Every contribution was scaled by
        # the leg's share of ALL THREE legs' weight, so a lone firing leg could
        # reach at most 1/3 however strong its conviction. That value is then
        # compared by auto_trader._ensemble_passes_signal_gates against
        # min_signal_confidence - a CONVICTION floor, the same constant
        # RiskManager.validate_signal applies to an aggregator confidence on the
        # REST path. A vote-share measured against a conviction bar: live
        # SOLUSDT 2026-08-23 01:00-01:23 carried post-MTF conviction 0.36,
        # reported it as conf=11.90% (0.36 / 3), and was rejected against the
        # 0.30 floor thirty-six times.
        #
        # It also contradicted MIN_AGREEING_LEGS = 1. That knob says one leg
        # suffices; the all-legs denominator made one leg arithmetically
        # incapable of clearing 0.30 (it would have needed conviction >= 0.90,
        # against an aggregator scale observed to top out near 0.62).
        #
        # Normalising over the legs that took a directional side keeps both
        # sides of that comparison in conviction units. Legs returning HOLD
        # abstain - they add nothing to the numerator and must not enter the
        # denominator either, or the same dilution returns in miniature.
        #
        # No threshold value changed. Evidence and measured counterfactuals:
        # .planning/evidence/hold-funnel-2026-08-22.md
        directional_weight = 0.0

        for leg_id, (action, conf, _sl, _tp, _reason) in leg_signals.items():
            sign = (
                1.0
                if action == SignalAction.BUY
                else (-1.0 if action == SignalAction.SELL else 0.0)
            )
            leg_weight = weights.get(leg_id, 0.0)
            contribution = sign * conf * leg_weight
            weighted_score += contribution
            leg_contributions[leg_id] = contribution
            leg_actions[leg_id] = action.value
            if sign != 0.0:
                directional_weight += leg_weight

        if directional_weight > 0.0:
            weighted_score /= directional_weight
            leg_contributions = {
                leg: value / directional_weight
                for leg, value in leg_contributions.items()
            }

        # ONE agreement predicate, evaluated once. The diversity guard below
        # needs the identities of the agreeing legs, not just how many there
        # are; writing a second predicate for it is the drift class this phase
        # exists to remove.
        agreeing_leg_ids = [
            leg_id
            for leg_id, (a, _c, _sl, _tp, _r) in leg_signals.items()
            if (a == SignalAction.BUY and weighted_score > 0)
            or (a == SignalAction.SELL and weighted_score < 0)
        ]
        agreeing_legs = len(agreeing_leg_ids)

        # LEG SOURCE-DIVERSITY GUARD - P21-2, 2026-08-27.
        #
        # The defect: agreement was counted without asking what each leg had
        # READ. `simple_rsi` consumes exactly one indicator key
        # (simple_rsi_strategy.py:153), so it is structurally a MOMENTUM-only
        # leg, and `mean_reversion`'s cheapest firing route starts from the same
        # RSI print. Two legs echoing one RSI reading were presented downstream
        # as independent multi-leg confirmation.
        #
        # Why it bites NOW, with measured context: until 2026-08-23 the weighted
        # score was normalised over ALL THREE legs' weight, so a lone leg was
        # capped at 1/3 of its conviction and could not clear the downstream
        # 0.30 floor whatever it believed (live SOLUSDT 2026-08-23 01:00-01:23:
        # conviction 0.36 reported as 0.119 and rejected 36 times). The fix that
        # normalises over DIRECTIONAL legs only - see the denominator comment
        # above - made single-leg admission reachable, which is precisely what
        # turns single-source agreement into a trade.
        #
        # THIS IS NOT A LEG COUNT. The two rules diverge on the row that matters:
        #
        #   agreeing legs            | categories  | this guard | MIN_LEGS = 2
        #   -------------------------|-------------|------------|-------------
        #   simple_rsi alone         | {MOMENTUM}  | block      | block
        #   simple_rsi + mean_rev    | 2           | pass       | pass
        #   multi_indicator alone    | >= 2 (ctor) | PASS       | block
        #
        # `multi_indicator` carries the full nine-voter gate stack and has
        # ALREADY cleared CoreAggregator's own
        # check_category_diversity(min_categories=2). Re-deriving its categories
        # here would invite the two gates to drift apart and would double-jeopardy
        # the strongest leg, so it is treated as diverse by construction. The
        # third row is pinned by an explicit test and is the same claim as Plan
        # 21-05's `threshold_lock`.
        #
        # NO THRESHOLD VALUE CHANGED. MIN_AGREEING_LEGS stays at 1,
        # AGGREGATION_THRESHOLD at 0.10, min_signal_confidence at 0.30. This is
        # wiring correctness, not tuning: the guard asks whether the information
        # is independent, not whether there is more of it.
        #
        # Expected effect: trade admission DECREASES. 21-CONTEXT authorises that
        # explicitly. It belongs to the "+gates" arm of the Plan 21-09 ablation,
        # together with 21-05's MTF gate, and NOT to the "+ATR" arm.
        proposed_action = (
            SignalAction.BUY
            if weighted_score > 0
            else (SignalAction.SELL if weighted_score < 0 else SignalAction.HOLD)
        )
        is_diverse, category_count, diversity_reason = self._check_leg_source_diversity(
            agreeing_leg_ids, mr_sig, proposed_action, symbol
        )
        if not is_diverse:
            logger.info(
                f"[ENSEMBLE] HOLD - {diversity_reason}. "
                f"Score={weighted_score:+.3f}, actions={leg_actions}"
            )
            self._reject(
                REJECT_INSUFFICIENT_DIVERSITY,
                f"{diversity_reason}; score={weighted_score:+.3f}, "
                f"actions={leg_actions}",
            )
            return None

        if agreeing_legs < self.MIN_AGREEING_LEGS:
            logger.info(
                f"[ENSEMBLE] HOLD — only {agreeing_legs} legs agree (need {self.MIN_AGREEING_LEGS}). "
                f"Score={weighted_score:+.3f}, actions={leg_actions}"
            )
            self._reject(
                REJECT_INSUFFICIENT_AGREEING_LEGS,
                f"only {agreeing_legs} leg(s) agree, need "
                f"{self.MIN_AGREEING_LEGS}; score={weighted_score:+.3f}, "
                f"actions={leg_actions}",
            )
            return None

        if abs(weighted_score) < self.AGGREGATION_THRESHOLD:
            logger.info(
                f"[ENSEMBLE] HOLD — weighted score {weighted_score:+.3f} below threshold "
                f"{self.AGGREGATION_THRESHOLD}. Actions={leg_actions}"
            )
            self._reject(
                REJECT_SCORE_BELOW_THRESHOLD,
                f"weighted score {weighted_score:+.3f} is below "
                f"AGGREGATION_THRESHOLD {self.AGGREGATION_THRESHOLD}; "
                f"actions={leg_actions}",
            )
            return None

        action = SignalAction.BUY if weighted_score > 0 else SignalAction.SELL
        confidence = min(abs(weighted_score), 1.0)

        # Take SL/TP from the leg with the largest absolute contribution in the chosen direction
        dominant_leg = max(
            leg_contributions.items(),
            key=lambda kv: (
                abs(kv[1]) if (kv[1] > 0) == (action == SignalAction.BUY) else -1.0
            ),
        )[0]
        _, _, sl, tp, dominant_reason = leg_signals[dominant_leg]

        # Position sizing cascade (ADR-015):
        #   floor   = settings.ensemble_min_position_pct
        #   cap     = settings.max_risk_per_trade  (via self.MAX_POSITION_PCT property)
        #   scaled  = confidence × cap × settings.ensemble_confidence_size_multiplier
        #   size    = min(cap, max(floor, scaled))
        # Defaults (5% floor, 3.7x mult, 10% cap) put typical-confidence
        # ensemble fires at ≥5% notional and reach the cap by conf ≈ 0.27.
        #
        # Order matters: the cap is applied LAST so it always wins. This read
        # max(floor, min(cap, scaled)) until the 2026-07-30 audit (F-2), which
        # discarded the cap whenever floor > cap — under the LIVE-strict 2% cap
        # the shipped 5% floor sized every trade at 2.5x the cap, at any
        # confidence. Preflight only inspected max_risk_per_trade, so it passed.
        from app.config import get_settings

        _settings = get_settings()
        cap = self.MAX_POSITION_PCT
        floor = _settings.ensemble_min_position_pct
        scaled = confidence * cap * _settings.ensemble_confidence_size_multiplier
        position_size_pct = min(cap, max(floor, scaled))

        if floor > cap:
            logger.warning(
                f"[ENSEMBLE] ensemble_min_position_pct={floor} exceeds per-trade cap "
                f"{cap}; sizing clamped to the cap. Lower the floor — this config "
                f"is rejected outright in LIVE."
            )

        reasoning = [
            f"Ensemble {action.value}: score={weighted_score:+.3f}, conf={confidence:.2%}",
            f"Legs: {leg_actions}",
            "Weights: " + ", ".join(f"{k}={v:.2f}" for k, v in weights.items()),
            f"Dominant: {dominant_leg}",
        ] + [f"  └ {r}" for r in dominant_reason]

        # Explicit even though the reset at the top already cleared it: a stale
        # cause sitting beside a live signal reads to an operator as the reason
        # the trade was blocked.
        self.last_rejection = None

        return EnsembleSignal(
            action=action,
            confidence=confidence,
            entry_price=current_price,
            stop_loss=sl,
            take_profit=tp,
            position_size_pct=position_size_pct,
            reasoning=reasoning,
            leg_contributions=leg_contributions,
            leg_actions=leg_actions,
            weights_snapshot=weights,
        )

    def record_trade_outcome(
        self, leg_contributions: Dict[str, float], pnl: float
    ) -> None:
        """Update each contributing leg's win-rate based on trade P&L.

        A leg whose contribution had the *same sign* as PnL is credited with a win.
        A leg whose contribution opposed PnL is credited with a loss. Legs that didn't fire
        (contribution == 0) are not updated.
        """
        won_overall = pnl > 0
        for leg_id, contrib in leg_contributions.items():
            if contrib == 0:
                continue
            leg_was_directionally_right = (contrib > 0 and won_overall) or (
                contrib < 0 and not won_overall
            )
            self.weights.record_outcome(leg_id, leg_was_directionally_right)


_ensemble_singleton: Optional[MultiStrategyEnsemble] = None


def get_ensemble() -> MultiStrategyEnsemble:
    global _ensemble_singleton
    if _ensemble_singleton is None:
        _ensemble_singleton = MultiStrategyEnsemble()
    return _ensemble_singleton
