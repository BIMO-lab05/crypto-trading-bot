"""
Simple RSI Strategy
Pure RSI-based mean-reversion entries with conservative confidence scaling.
Designed to be one of three components inside MultiStrategyEnsemble.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import logging

from app.models.signal import IndicatorSignal
from app.models.enums import SignalAction

logger = logging.getLogger(__name__)


@dataclass
class SimpleRSISignal:
    action: SignalAction
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float
    reasoning: List[str] = field(default_factory=list)


class SimpleRSIStrategy:
    """RSI 30/70 entries, ATR-based stops, 1:2 R/R targets.

    Inputs match MeanReversionStrategy / ResearchOptimizedStrategy so the
    ensemble can dispatch to all three with one indicator dict.
    """

    OVERSOLD = 30.0
    OVERBOUGHT = 70.0
    EXTREME_OVERSOLD = 20.0
    EXTREME_OVERBOUGHT = 80.0
    ATR_STOP_MULT = 2.0
    REWARD_RISK = 2.0
    MIN_CONFIDENCE = 0.20

    # Stop distance used when the ATR payload is absent or unusable, as a
    # FRACTION of price. Named so the number stops appearing inline and so a
    # fallback is distinguishable in a log from a real reading.
    DEFAULT_ATR_FRACTION = 0.02

    def __init__(self):
        logger.info("SimpleRSIStrategy initialized (30/70 mean-reversion, 1:2 R/R)")

    @classmethod
    def _resolve_atr_fraction(cls, atr_sig: Optional[IndicatorSignal]) -> float:
        """ATR as a FRACTION of price, under an explicit producer contract.

        P21-1, 2026-08-26. This replaced a unit GUESS:

            atr_pct = float(metadata.get("atr_pct") or <absolute ATR> or 0.02)
            if atr_pct > 1.0:
                atr_pct = atr_pct / 100.0

        The TA service emits `atr_pct` as a PERCENT
        (technical-analysis/app/indicators/atr.py:91 computes
        `(atr / current_price) * 100`), and a sub-1% hourly ATR is an
        explicitly modelled regime — atr.py:94 buckets `atr_pct < 1.0` as LOW
        volatility. So the `> 1.0` branch was wrong for exactly the calm
        markets it was most likely to meet. Measured against the running TA
        service on 2026-08-26 (60m interval):

            BTCUSDT atr_pct 0.6658 -> guessed 0.666   -> 133% stop distance
            ETHUSDT atr_pct 0.8376 -> guessed 0.838   -> 168% stop distance
            BNBUSDT atr_pct 0.7182 -> guessed 0.718   -> 144% stop distance
            SOLUSDT atr_pct 1.1065 -> guessed 0.01107 -> 2.2%  (correct)
            ADAUSDT atr_pct 1.4043 -> guessed 0.01404 -> 2.8%  (correct)

        Three of the five tradeable symbols were in the broken branch, and
        they are the three largest by notional; a 133% stop distance on a BUY
        is a NEGATIVE stop price. The defect was invisible only because
        `indicators["ATR"]` was never populated. It had to be fixed in the
        same commit that populates it (P21-1), or the broken combination
        would have shipped.

        The `or`-chain fall-through to the ABSOLUTE reading on
        `IndicatorSignal.value` (BTC ~522) is deliberately gone: the chain
        reached it whenever `atr_pct` was falsy — which includes 0.0,
        atr.py:136's FAILURE default. That was a second route into the same
        100x trap, since 522 > 1.0 and the heuristic "corrected" it to 5.22.

        Anything outside the open interval (0, 1) is refused with a WARNING
        and the named default; NaN fails the same comparison and takes the
        same path. No threshold value changed.
        """
        if atr_sig is None:
            return cls.DEFAULT_ATR_FRACTION

        metadata = atr_sig.metadata or {}
        raw = metadata.get("atr_fraction")
        source = "atr_fraction"

        if raw is None:
            # Producer contract: metadata["atr_pct"] is a PERCENT.
            raw = metadata.get("atr_pct")
            source = "atr_pct/100"
            if raw is not None:
                try:
                    raw = float(raw) / 100.0
                except (TypeError, ValueError):
                    raw = None

        if raw is not None:
            try:
                fraction = float(raw)
            except (TypeError, ValueError):
                fraction = None
            if fraction is not None and 0.0 < fraction < 1.0:
                return fraction

        logger.warning(
            f"[SIMPLE_RSI][ATR] unusable ATR payload "
            f"(atr_fraction={metadata.get('atr_fraction')!r}, "
            f"atr_pct={metadata.get('atr_pct')!r}, source={source}) — resolved "
            f"{raw!r}, which is not a fraction in (0, 1). Falling back to the "
            f"named default {cls.DEFAULT_ATR_FRACTION}. Note atr_pct=0.0 is "
            f"the TA service's FAILURE marker (atr.py:136), not a reading."
        )
        return cls.DEFAULT_ATR_FRACTION

    def generate_signal(
        self,
        indicators: Dict[str, IndicatorSignal],
        current_price: float,
        capital: float = 100.0,
    ) -> Optional[SimpleRSISignal]:
        rsi_sig = indicators.get("RSI")
        if not rsi_sig:
            return None
        # The reading lives on .value; metadata carries period/weight only.
        # Reading it from metadata returned None on every call — audit F-1.
        rsi = rsi_sig.numeric_value()
        if rsi is None:
            return None

        atr_fraction = self._resolve_atr_fraction(indicators.get("ATR"))

        action = SignalAction.HOLD
        confidence = 0.0
        reasoning: List[str] = []

        if rsi <= self.EXTREME_OVERSOLD:
            action = SignalAction.BUY
            confidence = 0.80
            reasoning.append(f"RSI {rsi:.1f} extreme oversold")
        elif rsi <= self.OVERSOLD:
            action = SignalAction.BUY
            confidence = (
                0.45
                + (self.OVERSOLD - rsi) / (self.OVERSOLD - self.EXTREME_OVERSOLD) * 0.30
            )
            reasoning.append(f"RSI {rsi:.1f} oversold")
        elif rsi >= self.EXTREME_OVERBOUGHT:
            action = SignalAction.SELL
            confidence = 0.80
            reasoning.append(f"RSI {rsi:.1f} extreme overbought")
        elif rsi >= self.OVERBOUGHT:
            action = SignalAction.SELL
            confidence = (
                0.45
                + (rsi - self.OVERBOUGHT)
                / (self.EXTREME_OVERBOUGHT - self.OVERBOUGHT)
                * 0.30
            )
            reasoning.append(f"RSI {rsi:.1f} overbought")
        else:
            return None

        if confidence < self.MIN_CONFIDENCE:
            return None

        stop_distance = current_price * atr_fraction * self.ATR_STOP_MULT
        if action == SignalAction.BUY:
            stop_loss = current_price - stop_distance
            take_profit = current_price + stop_distance * self.REWARD_RISK
        else:
            stop_loss = current_price + stop_distance
            take_profit = current_price - stop_distance * self.REWARD_RISK

        reasoning.append(
            f"ATR-based stop {atr_fraction * 100:.2f}% × {self.ATR_STOP_MULT}x, R/R 1:{self.REWARD_RISK}"
        )

        return SimpleRSISignal(
            action=action,
            confidence=round(confidence, 4),
            entry_price=current_price,
            stop_loss=round(stop_loss, 4),
            take_profit=round(take_profit, 4),
            reasoning=reasoning,
        )
