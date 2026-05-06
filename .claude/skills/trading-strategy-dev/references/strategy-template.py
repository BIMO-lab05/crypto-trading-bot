"""
Skeleton for a new trading-engine strategy.

Drop into:
    services/trading-engine/app/strategies/<your_name>_strategy.py

Then register in:
    services/trading-engine/app/strategies/coordinator.py
    services/trading-engine/app/strategies/aggregator.py (if it participates in fusion)
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.strategies.base import (
    AnalysisResult,
    MarketCondition,
    StrategyBase,
    StrategyCategory,
    StrategyMetadata,
    StrategyRiskLevel,
    StrategySignal,
)

logger = logging.getLogger(__name__)


# --- 2% per-trade cap is project-load-bearing. Do NOT raise without explicit approval.
MAX_RISK_PER_TRADE = Decimal("0.02")


class TemplateStrategy(StrategyBase):
    metadata = StrategyMetadata(
        name="template_strategy",
        version="0.1.0",
        category=StrategyCategory.TREND_FOLLOWING,  # or MEAN_REVERSION, BREAKOUT, etc.
        risk_level=StrategyRiskLevel.MODERATE,
        min_capital=Decimal("100"),
        compatible_market_conditions=[
            MarketCondition.TRENDING_UP,
            MarketCondition.TRENDING_DOWN,
        ],
        description="ONE sentence on what this strategy actually does.",
    )

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config or {})
        # Pull tunables from config; document defaults at module level.
        self.lookback = int(self.config.get("lookback", 50))

    async def analyze(self, symbol: str, data: Any) -> AnalysisResult:
        """
        Compute indicators / features required by generate_signals.
        MUST be causal: every value at bar t depends only on bars <= t.
        """
        # Example shape: TA dataframe in, summary dict + market condition out.
        df = data.copy()
        # ... compute features ...
        market_condition = (
            MarketCondition.TRENDING_UP
        )  # derive, don't hardcode in real code.
        return AnalysisResult(
            symbol=symbol,
            market_condition=market_condition,
            indicators={"example_feature": 0.0},
            metadata={"lookback": self.lookback},
        )

    async def generate_signals(
        self,
        symbol: str,
        analysis: AnalysisResult,
        current_price: Decimal,
    ) -> List[StrategySignal]:
        """
        Return zero or more StrategySignal. Each signal carries:
            signal_type (LONG / SHORT / EXIT_LONG / EXIT_SHORT / HOLD),
            confidence (0..1),
            entry_price, stop_loss, take_profit (Decimal).
        Stop-loss should be derived via app.atr_stops.atr_stop, not as a fixed %.
        """
        signals: List[StrategySignal] = []
        # Derive entry/stop/tp...
        # signals.append(create_signal(
        #     strategy=self.metadata.name,
        #     symbol=symbol,
        #     signal_type=SignalType.LONG,
        #     confidence=0.7,
        #     entry_price=current_price,
        #     stop_loss=...,
        #     take_profit=...,
        # ))
        return signals

    def calculate_position_size(
        self,
        signal: StrategySignal,
        capital: Decimal,
        risk_pct: Optional[Decimal] = None,
    ) -> Decimal:
        """
        Convert a signal to an order quantity. MUST clamp at 2% capital.
        """
        risk_pct = min(risk_pct or MAX_RISK_PER_TRADE, MAX_RISK_PER_TRADE)
        risk_capital = capital * risk_pct
        if signal.stop_loss is None or signal.entry_price is None:
            logger.warning(
                "missing stop_loss/entry on signal; refusing to size",
                extra={"strategy": self.metadata.name, "symbol": signal.symbol},
            )
            return Decimal("0")
        per_unit_risk = abs(signal.entry_price - signal.stop_loss)
        if per_unit_risk == 0:
            return Decimal("0")
        qty = risk_capital / per_unit_risk
        return qty
