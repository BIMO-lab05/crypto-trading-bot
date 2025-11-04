"""
Signal Models
Purpose: Trading signal data structures
"""

from pydantic import BaseModel, Field
from typing import Dict, Optional
from decimal import Decimal
from app.models.enums import SignalAction


class IndicatorSignal(BaseModel):
    """Individual indicator signal"""
    name: str = Field(description="Indicator name (RSI, MACD, etc.)")
    signal: SignalAction = Field(description="Signal action")
    confidence: float = Field(ge=0.0, le=1.0, description="Signal confidence")
    value: Optional[float] = Field(default=None, description="Indicator value")
    metadata: Dict = Field(default_factory=dict, description="Additional metadata")


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
        description="Aggregated score: -1 (strong sell) to +1 (strong buy)"
    )
    consensus_count: int = Field(
        description="Number of indicators in agreement"
    )
    strategy: Optional[str] = Field(
        default=None,
        description="Strategy that generated this signal"
    )
    metadata: Dict = Field(
        default_factory=dict,
        description="Additional metadata"
    )
