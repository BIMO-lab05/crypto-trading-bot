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
from typing import Dict, List, Optional, Tuple
import logging
import json
import os
import threading
import time

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

    def __init__(self, mean_reversion: Optional[MeanReversionStrategy] = None):
        self.simple_rsi = SimpleRSIStrategy()
        self.mean_reversion = mean_reversion or MeanReversionStrategy()
        self.weights = get_ensemble_weights()
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
            # PATH, so clamp rather than trust the wire.
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
        # consensus that was genuinely HOLD, the regime hard-block
        # (signal_aggregator.py:1206+), and a per-timeframe requirements gate
        # resolving HOLD inside aggregator_core. Gating on the bare action would
        # suppress the last two as well, which 21-CONTEXT does not authorise.
        # The regime hard-block is recorded as a candidate follow-up, not fixed.
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

        agreeing_legs = sum(
            1
            for (a, _c, _sl, _tp, _r) in leg_signals.values()
            if (a == SignalAction.BUY and weighted_score > 0)
            or (a == SignalAction.SELL and weighted_score < 0)
        )
        if agreeing_legs < self.MIN_AGREEING_LEGS:
            logger.info(
                f"[ENSEMBLE] HOLD — only {agreeing_legs} legs agree (need {self.MIN_AGREEING_LEGS}). "
                f"Score={weighted_score:+.3f}, actions={leg_actions}"
            )
            return None

        if abs(weighted_score) < self.AGGREGATION_THRESHOLD:
            logger.info(
                f"[ENSEMBLE] HOLD — weighted score {weighted_score:+.3f} below threshold "
                f"{self.AGGREGATION_THRESHOLD}. Actions={leg_actions}"
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
