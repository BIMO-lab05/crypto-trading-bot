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

    def __init__(self):
        logger.info("SimpleRSIStrategy initialized (30/70 mean-reversion, 1:2 R/R)")

    def generate_signal(
        self,
        indicators: Dict[str, IndicatorSignal],
        current_price: float,
        capital: float = 100.0,
    ) -> Optional[SimpleRSISignal]:
        rsi_sig = indicators.get("RSI")
        if not rsi_sig or not rsi_sig.metadata:
            return None
        rsi = rsi_sig.metadata.get("value")
        if rsi is None:
            return None

        atr_sig = indicators.get("ATR")
        atr_pct = 0.02
        if atr_sig and atr_sig.metadata:
            atr_pct = float(atr_sig.metadata.get("atr_pct") or atr_sig.metadata.get("value", 0.02))
            if atr_pct > 1.0:
                atr_pct = atr_pct / 100.0

        action = SignalAction.HOLD
        confidence = 0.0
        reasoning: List[str] = []

        if rsi <= self.EXTREME_OVERSOLD:
            action = SignalAction.BUY
            confidence = 0.80
            reasoning.append(f"RSI {rsi:.1f} extreme oversold")
        elif rsi <= self.OVERSOLD:
            action = SignalAction.BUY
            confidence = 0.45 + (self.OVERSOLD - rsi) / (self.OVERSOLD - self.EXTREME_OVERSOLD) * 0.30
            reasoning.append(f"RSI {rsi:.1f} oversold")
        elif rsi >= self.EXTREME_OVERBOUGHT:
            action = SignalAction.SELL
            confidence = 0.80
            reasoning.append(f"RSI {rsi:.1f} extreme overbought")
        elif rsi >= self.OVERBOUGHT:
            action = SignalAction.SELL
            confidence = 0.45 + (rsi - self.OVERBOUGHT) / (self.EXTREME_OVERBOUGHT - self.OVERBOUGHT) * 0.30
            reasoning.append(f"RSI {rsi:.1f} overbought")
        else:
            return None

        if confidence < self.MIN_CONFIDENCE:
            return None

        stop_distance = current_price * atr_pct * self.ATR_STOP_MULT
        if action == SignalAction.BUY:
            stop_loss = current_price - stop_distance
            take_profit = current_price + stop_distance * self.REWARD_RISK
        else:
            stop_loss = current_price + stop_distance
            take_profit = current_price - stop_distance * self.REWARD_RISK

        reasoning.append(f"ATR-based stop {atr_pct*100:.2f}% × {self.ATR_STOP_MULT}x, R/R 1:{self.REWARD_RISK}")

        return SimpleRSISignal(
            action=action,
            confidence=round(confidence, 4),
            entry_price=current_price,
            stop_loss=round(stop_loss, 4),
            take_profit=round(take_profit, 4),
            reasoning=reasoning,
        )
