"""
Technical Analysis Service - Data Models
Purpose: Pydantic models for requests and responses
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum


class SignalType(str, Enum):
    """Trading signal types"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NEUTRAL = "NEUTRAL"


class IndicatorType(str, Enum):
    """Supported technical indicators"""
    RSI = "RSI"
    MACD = "MACD"
    BOLLINGER_BANDS = "BB"
    SMA = "SMA"
    EMA = "EMA"


class Kline(BaseModel):
    """Market data kline/candlestick"""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class IndicatorValue(BaseModel):
    """Single indicator calculation result"""
    symbol: str
    interval: str
    timestamp: int
    indicator: IndicatorType
    value: float | Dict[str, float]  # Single value or dict for multi-value indicators
    signal: SignalType
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: Optional[Dict[str, Any]] = None


class RSIResponse(BaseModel):
    """RSI indicator response"""
    symbol: str
    interval: str
    timestamp: int
    rsi: float
    signal: SignalType
    confidence: float
    parameters: Dict[str, int] = Field(default={"period": 14})


class MACDResponse(BaseModel):
    """MACD indicator response"""
    symbol: str
    interval: str
    timestamp: int
    macd_line: float
    signal_line: float
    histogram: float
    signal: SignalType
    confidence: float
    parameters: Dict[str, int] = Field(default={"fast": 12, "slow": 26, "signal": 9})


class BollingerBandsResponse(BaseModel):
    """Bollinger Bands response"""
    symbol: str
    interval: str
    timestamp: int
    upper_band: float
    middle_band: float
    lower_band: float
    current_price: float
    signal: SignalType
    confidence: float
    parameters: Dict[str, Any] = Field(default={"period": 20, "std_dev": 2.0})


class MovingAverageResponse(BaseModel):
    """Moving Average response"""
    symbol: str
    interval: str
    timestamp: int
    ma_type: str  # "SMA" or "EMA"
    value: float
    current_price: float
    signal: SignalType
    confidence: float
    parameters: Dict[str, int]


class AllIndicatorsResponse(BaseModel):
    """Combined response for all indicators"""
    symbol: str
    interval: str
    timestamp: int
    indicators: Dict[str, IndicatorValue]
    overall_signal: SignalType
    overall_confidence: float


class SignalAnalysis(BaseModel):
    """Multi-indicator signal analysis"""
    symbol: str
    interval: str
    timestamp: int
    overall_signal: SignalType
    confidence: float = Field(ge=0.0, le=1.0)
    indicators: Dict[str, Dict[str, Any]]
    recommendation: str
    risk_level: str  # "LOW", "MEDIUM", "HIGH"


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    market_data_connection: bool = False
    timestamp: int


class ReadyResponse(BaseModel):
    """Readiness check response"""
    status: str
    service: str
    dependencies: Dict[str, bool]
    timestamp: int
