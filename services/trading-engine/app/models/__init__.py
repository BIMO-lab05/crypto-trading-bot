"""
Data Models for Trading Engine
"""

from app.models.enums import (
    SignalAction,
    PositionSide,
    PositionStatus,
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce,  # Added 2026-01-16 for Fix #3 (stop loss limit orders)
    TradingMode
)
from app.models.signal import TradingSignal, IndicatorSignal
from app.models.position import Position, PositionCreate, PositionUpdate
from app.models.order import Order, OrderCreate, OrderUpdate
from app.models.performance import PerformanceMetrics, PerformanceSnapshot
from app.models.response import (
    HealthResponse,
    StatusResponse,
    SignalResponse,
    PositionResponse,
    PositionListResponse,
    PerformanceResponse,
    StrategyListResponse,
    TradingControlResponse,
    TradeHistoryStats,
    TradeHistoryResponse
)
from app.models.stat_arb_models import (
    # Request Models
    InitializeManagerRequest,
    AddPairsStrategyRequest,
    CalibratePairsStrategyRequest,
    AddFundingStrategyRequest,
    SetupTriangularArbitrageRequest,
    GenerateSignalsRequest,
    # Response Models
    StrategyAllocationResponse,
    InitializeManagerResponse,
    StrategyResponse,
    PairsTradeSignalResponse,
    FundingRateSignalResponse,
    TriangularArbitrageSignalResponse,
    SignalsResponse,
    StrategyPerformanceResponse,
    PerformanceResponse as StatArbPerformanceResponse,
    StatusResponse as StatArbStatusResponse,
    ResetResponse,
    ErrorResponse
)

__all__ = [
    # Enums
    "SignalAction",
    "PositionSide",
    "PositionStatus",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "TimeInForce",  # Added 2026-01-16 for Fix #3
    "TradingMode",
    # Signal Models
    "TradingSignal",
    "IndicatorSignal",
    # Position Models
    "Position",
    "PositionCreate",
    "PositionUpdate",
    # Order Models
    "Order",
    "OrderCreate",
    "OrderUpdate",
    # Performance Models
    "PerformanceMetrics",
    "PerformanceSnapshot",
    # Response Models
    "HealthResponse",
    "StatusResponse",
    "SignalResponse",
    "PositionResponse",
    "PositionListResponse",
    "PerformanceResponse",
    "StrategyListResponse",
    "TradingControlResponse",
    "TradeHistoryStats",
    "TradeHistoryResponse",
    # Statistical Arbitrage Request Models
    "InitializeManagerRequest",
    "AddPairsStrategyRequest",
    "CalibratePairsStrategyRequest",
    "AddFundingStrategyRequest",
    "SetupTriangularArbitrageRequest",
    "GenerateSignalsRequest",
    # Statistical Arbitrage Response Models
    "StrategyAllocationResponse",
    "InitializeManagerResponse",
    "StrategyResponse",
    "PairsTradeSignalResponse",
    "FundingRateSignalResponse",
    "TriangularArbitrageSignalResponse",
    "SignalsResponse",
    "StrategyPerformanceResponse",
    "StatArbPerformanceResponse",
    "StatArbStatusResponse",
    "ResetResponse",
    "ErrorResponse"
]
