"""
Signal Models
Purpose: Trading signal data structures
"""

from pydantic import BaseModel, Field
from typing import Dict, Optional
from app.models.enums import SignalAction


class IndicatorSignal(BaseModel):
    """Individual indicator signal"""

    name: str = Field(description="Indicator name (RSI, MACD, etc.)")
    signal: SignalAction = Field(description="Signal action")
    confidence: float = Field(ge=0.0, le=1.0, description="Signal confidence")
    value: Optional[float] = Field(default=None, description="Indicator value")
    metadata: Dict = Field(default_factory=dict, description="Additional metadata")

    def numeric_value(self) -> Optional[float]:
        """The indicator's numeric reading, wherever the producer put it.

        `SignalAggregator` sets the reading on the `value` field and reserves
        `metadata` for aggregation bookkeeping (period, weight). Consumers that
        read `metadata["value"]` instead got `None` on every call — see audit
        2026-07-30 finding F-1, where this silently disabled two of the three
        ensemble legs for the lifetime of the process.

        Falls back to `metadata["value"]` so producers that do write there keep
        working. Returns None when no reading is available anywhere; callers
        must treat that as "cannot evaluate", never as a neutral reading.
        """
        if self.value is not None:
            return float(self.value)
        raw = (self.metadata or {}).get("value")
        return None if raw is None else float(raw)


class TradingSignal(BaseModel):
    """Aggregated trading signal"""

    symbol: str = Field(description="Trading symbol")
    timestamp: int = Field(description="Signal timestamp (ms)")
    action: SignalAction = Field(description="Recommended action")
    confidence: float = Field(ge=0.0, le=1.0, description="Overall confidence")
    indicators: Dict[str, IndicatorSignal] = Field(
        description="Individual indicator signals"
    )
    aggregated_score: float = Field(
        ge=-1.0,
        le=1.0,
        description="Aggregated score: -1 (strong sell) to +1 (strong buy)",
    )
    consensus_count: int = Field(description="Number of indicators in agreement")
    strategy: Optional[str] = Field(
        default=None, description="Strategy that generated this signal"
    )
    metadata: Dict = Field(default_factory=dict, description="Additional metadata")
