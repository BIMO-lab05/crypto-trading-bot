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

from app.models.signal import TradingSignal
from app.models.enums import SignalAction
from app.strategies.simple_rsi_strategy import SimpleRSIStrategy
from app.strategies.mean_reversion_strategy import (
    MeanReversionStrategy,
)

logger = logging.getLogger(__name__)


LEG_RSI = "simple_rsi"
LEG_MULTI = "multi_indicator"
LEG_MEAN_REV = "mean_reversion"


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
                self._win_rates.update(data.get("win_rates", {}))
                self._trade_counts.update(data.get("trade_counts", {}))
                logger.info(f"[ENSEMBLE] Loaded weights: {self._win_rates}")
        except Exception as e:
            logger.warning(f"[ENSEMBLE] Could not load weights state: {e}")

    def _persist(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.STATE_PATH), exist_ok=True)
            with open(self.STATE_PATH, "w") as f:
                json.dump(
                    {
                        "win_rates": self._win_rates,
                        "trade_counts": self._trade_counts,
                        "ts": time.time(),
                    },
                    f,
                )
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

    def generate_signal(
        self,
        aggregator_signal: TradingSignal,
        current_price: float,
        capital: float = 100.0,
    ) -> Optional[EnsembleSignal]:
        """Aggregate signals from the three legs.

        `aggregator_signal` is the existing CoreAggregator output — it both gives us the
        multi-indicator leg directly AND provides the indicator dict the other legs need.
        """
        indicators = aggregator_signal.indicators or {}

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
            atr_sl = aggregator_signal.metadata.get("atr_stop_loss", current_price)
            atr_tp = aggregator_signal.metadata.get("atr_take_profit", current_price)
            leg_signals[LEG_MULTI] = (
                aggregator_signal.action,
                aggregator_signal.confidence,
                float(atr_sl) if atr_sl else current_price,
                float(atr_tp) if atr_tp else current_price,
                [
                    f"Aggregator score={aggregator_signal.aggregated_score:.3f}, consensus={aggregator_signal.consensus_count}"
                ],
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

        for leg_id, (action, conf, _sl, _tp, _reason) in leg_signals.items():
            sign = (
                1.0
                if action == SignalAction.BUY
                else (-1.0 if action == SignalAction.SELL else 0.0)
            )
            contribution = sign * conf * weights.get(leg_id, 0.0)
            weighted_score += contribution
            leg_contributions[leg_id] = contribution
            leg_actions[leg_id] = action.value

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
        #   size    = max(floor, min(cap, scaled))
        # Defaults (5% floor, 3.7x mult, 10% cap) put typical-confidence
        # ensemble fires at ≥5% notional and reach the cap by conf ≈ 0.27.
        from app.config import get_settings

        _settings = get_settings()
        cap = self.MAX_POSITION_PCT
        floor = _settings.ensemble_min_position_pct
        scaled = confidence * cap * _settings.ensemble_confidence_size_multiplier
        position_size_pct = max(floor, min(cap, scaled))

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
