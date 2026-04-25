"""
Analytics API Models
Purpose: Pydantic models for analytics API endpoints

This module defines request and response models for:
- Attribution Analysis API (Phase 5.1)
- Post-Trade Analysis API (Phase 4.3)

Author: Backend Developer Agent
Date: 2025-12-11
Updated: 2025-12-12 - Added Post-Trade Analysis models
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum


# =============================================================================
# ENUMS FOR API
# =============================================================================

class TimePeriod(str, Enum):
    """Time period for trend analysis"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class DimensionType(str, Enum):
    """Attribution dimension types"""
    STRATEGY = "strategy"
    SYMBOL = "symbol"
    DIRECTION = "direction"
    MARKET_CONDITION = "market_condition"


# =============================================================================
# POST-TRADE ANALYSIS ENUMS (Phase 4.3)
# =============================================================================

class ExecutionStyleEnum(str, Enum):
    """Trade execution style"""
    AGGRESSIVE = "aggressive"
    PASSIVE = "passive"
    HYBRID = "hybrid"


class MarketConditionEnum(str, Enum):
    """Market conditions during trade"""
    VOLATILE = "volatile"
    STABLE = "stable"
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"


class LiquidityLevelEnum(str, Enum):
    """Liquidity level classification"""
    DEEP = "deep"
    NORMAL = "normal"
    THIN = "thin"


class TradingSessionEnum(str, Enum):
    """Trading session by time"""
    ASIA = "asia"
    EUROPE = "europe"
    US = "us"


class QualityGradeEnum(str, Enum):
    """Execution quality grade"""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    VERY_POOR = "very_poor"


# =============================================================================
# RESPONSE MODELS - METRICS
# =============================================================================

class AttributionMetricsResponse(BaseModel):
    """Attribution metrics in API response format"""
    total_pnl: float = Field(
        description="Total profit/loss in USD"
    )
    win_rate: float = Field(
        description="Win rate as percentage (0-100)"
    )
    sharpe_ratio: float = Field(
        description="Sharpe ratio (risk-adjusted return)"
    )
    max_drawdown: float = Field(
        description="Maximum drawdown as percentage"
    )
    avg_win: float = Field(
        description="Average profit on winning trades"
    )
    avg_loss: float = Field(
        description="Average loss on losing trades"
    )
    profit_factor: float = Field(
        description="Ratio of gross profit to gross loss"
    )
    trades_count: int = Field(
        description="Total number of trades"
    )
    sortino_ratio: float = Field(
        description="Sortino ratio (downside risk-adjusted return)"
    )
    calmar_ratio: float = Field(
        description="Calmar ratio (return / max drawdown)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "total_pnl": 1250.50,
                "win_rate": 58.5,
                "sharpe_ratio": 1.85,
                "max_drawdown": -5.2,
                "avg_win": 125.30,
                "avg_loss": -85.20,
                "profit_factor": 1.47,
                "trades_count": 142,
                "sortino_ratio": 2.15,
                "calmar_ratio": 0.24,
            }
        }


# =============================================================================
# RESPONSE MODELS - ATTRIBUTION RESULT
# =============================================================================

class AttributionResultResponse(BaseModel):
    """Single attribution result for a dimension value"""
    dimension: str = Field(
        description="Attribution dimension (strategy, symbol, etc.)"
    )
    value: str = Field(
        description="Dimension value (e.g., BTCUSDT, pairs_trading)"
    )
    metrics: AttributionMetricsResponse = Field(
        description="Performance metrics for this attribution"
    )
    contribution_pct: float = Field(
        description="Contribution to total P&L as percentage"
    )
    trades_count: int = Field(
        description="Number of trades in this attribution"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "dimension": "strategy",
                "value": "pairs_trading",
                "metrics": {
                    "total_pnl": 850.25,
                    "win_rate": 62.3,
                    "sharpe_ratio": 2.1,
                    "max_drawdown": -3.5,
                    "avg_win": 95.50,
                    "avg_loss": -55.30,
                    "profit_factor": 1.73,
                    "trades_count": 45,
                    "sortino_ratio": 2.45,
                    "calmar_ratio": 0.28,
                },
                "contribution_pct": 68.0,
                "trades_count": 45,
            }
        }


# =============================================================================
# RESPONSE MODELS - BY STRATEGY
# =============================================================================

class AttributionByStrategyResponse(BaseModel):
    """Response for /api/v1/analytics/attribution/by-strategy endpoint"""
    success: bool = Field(
        default=True,
        description="Whether the request was successful"
    )
    attributions: List[AttributionResultResponse] = Field(
        description="List of attribution results by strategy"
    )
    total_strategies: int = Field(
        description="Total number of strategies with trades"
    )
    period_start: Optional[str] = Field(
        default=None,
        description="Start of analysis period (ISO format)"
    )
    period_end: Optional[str] = Field(
        default=None,
        description="End of analysis period (ISO format)"
    )
    generated_at: str = Field(
        description="When the analysis was generated"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "attributions": [
                    {
                        "dimension": "strategy",
                        "value": "pairs_trading",
                        "metrics": {
                            "total_pnl": 850.25,
                            "win_rate": 62.3,
                            "sharpe_ratio": 2.1,
                            "max_drawdown": -3.5,
                            "avg_win": 95.50,
                            "avg_loss": -55.30,
                            "profit_factor": 1.73,
                            "trades_count": 45,
                            "sortino_ratio": 2.45,
                            "calmar_ratio": 0.28,
                        },
                        "contribution_pct": 68.0,
                        "trades_count": 45,
                    }
                ],
                "total_strategies": 3,
                "period_start": "2025-12-01T00:00:00Z",
                "period_end": "2025-12-11T23:59:59Z",
                "generated_at": "2025-12-11T14:30:00Z",
            }
        }


# =============================================================================
# RESPONSE MODELS - BY SYMBOL
# =============================================================================

class AttributionBySymbolResponse(BaseModel):
    """Response for /api/v1/analytics/attribution/by-symbol endpoint"""
    success: bool = Field(
        default=True,
        description="Whether the request was successful"
    )
    attributions: List[AttributionResultResponse] = Field(
        description="List of attribution results by symbol"
    )
    total_symbols: int = Field(
        description="Total number of symbols traded"
    )
    period_start: Optional[str] = Field(
        default=None,
        description="Start of analysis period (ISO format)"
    )
    period_end: Optional[str] = Field(
        default=None,
        description="End of analysis period (ISO format)"
    )
    generated_at: str = Field(
        description="When the analysis was generated"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "attributions": [
                    {
                        "dimension": "symbol",
                        "value": "SOLUSDT",
                        "metrics": {
                            "total_pnl": 455.90,
                            "win_rate": 60.0,
                            "sharpe_ratio": 1.95,
                            "max_drawdown": -4.2,
                            "avg_win": 85.30,
                            "avg_loss": -62.40,
                            "profit_factor": 1.37,
                            "trades_count": 15,
                            "sortino_ratio": 2.25,
                            "calmar_ratio": 0.22,
                        },
                        "contribution_pct": 35.8,
                        "trades_count": 15,
                    }
                ],
                "total_symbols": 3,
                "period_start": "2025-12-01T00:00:00Z",
                "period_end": "2025-12-11T23:59:59Z",
                "generated_at": "2025-12-11T14:30:00Z",
            }
        }


# =============================================================================
# RESPONSE MODELS - SUMMARY
# =============================================================================

class AttributionSummaryResponse(BaseModel):
    """Response for /api/v1/analytics/attribution/summary endpoint"""
    success: bool = Field(
        default=True,
        description="Whether the request was successful"
    )
    overall_metrics: AttributionMetricsResponse = Field(
        description="Overall portfolio performance metrics"
    )
    by_strategy: List[AttributionResultResponse] = Field(
        description="Attribution breakdown by strategy"
    )
    by_symbol: List[AttributionResultResponse] = Field(
        description="Attribution breakdown by symbol"
    )
    by_direction: List[AttributionResultResponse] = Field(
        description="Attribution breakdown by trade direction"
    )
    by_market_condition: List[AttributionResultResponse] = Field(
        description="Attribution breakdown by market condition"
    )
    performance_decomposition: List[Dict[str, Any]] = Field(
        default=[],
        description="Performance decomposition (alpha, beta, residual)"
    )
    period_start: Optional[str] = Field(
        default=None,
        description="Start of analysis period (ISO format)"
    )
    period_end: Optional[str] = Field(
        default=None,
        description="End of analysis period (ISO format)"
    )
    generated_at: str = Field(
        description="When the analysis was generated"
    )
    current_equity: float = Field(
        description="Current portfolio equity"
    )
    peak_equity: float = Field(
        description="Peak portfolio equity (for drawdown)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "overall_metrics": {
                    "total_pnl": 1250.50,
                    "win_rate": 58.5,
                    "sharpe_ratio": 1.85,
                    "max_drawdown": -5.2,
                    "avg_win": 125.30,
                    "avg_loss": -85.20,
                    "profit_factor": 1.47,
                    "trades_count": 142,
                    "sortino_ratio": 2.15,
                    "calmar_ratio": 0.24,
                },
                "by_strategy": [],
                "by_symbol": [],
                "by_direction": [],
                "by_market_condition": [],
                "performance_decomposition": [],
                "period_start": "2025-12-01T00:00:00Z",
                "period_end": "2025-12-11T23:59:59Z",
                "generated_at": "2025-12-11T14:30:00Z",
                "current_equity": 11250.50,
                "peak_equity": 11350.00,
            }
        }


# =============================================================================
# REQUEST/RESPONSE MODELS - TRENDS
# =============================================================================

class AttributionTrendsRequest(BaseModel):
    """Request parameters for attribution trends analysis"""
    period: TimePeriod = Field(
        default=TimePeriod.DAILY,
        description="Time period granularity for trend analysis"
    )
    lookback_days: int = Field(
        default=7,
        ge=1,
        le=365,
        description="Number of days to analyze"
    )
    dimension: DimensionType = Field(
        default=DimensionType.STRATEGY,
        description="Attribution dimension to analyze trends for"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "period": "daily",
                "lookback_days": 7,
                "dimension": "strategy",
            }
        }


class TrendDataResponse(BaseModel):
    """Trend data for a single dimension value"""
    dimension: str = Field(
        description="Attribution dimension"
    )
    value: str = Field(
        description="Dimension value"
    )
    periods: List[str] = Field(
        description="Time period labels"
    )
    pnl_trend: List[float] = Field(
        description="P&L values for each period"
    )
    win_rate_trend: List[float] = Field(
        description="Win rate (%) for each period"
    )
    trades_count_trend: List[int] = Field(
        description="Trade count for each period"
    )
    moving_avg_pnl: List[float] = Field(
        description="Moving average of P&L"
    )
    trend_direction: str = Field(
        description="Overall trend direction (up, down, flat)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "dimension": "strategy",
                "value": "pairs_trading",
                "periods": ["2025-12-05", "2025-12-06", "2025-12-07"],
                "pnl_trend": [120.50, 85.30, 145.80],
                "win_rate_trend": [60.0, 55.0, 65.0],
                "trades_count_trend": [5, 4, 6],
                "moving_avg_pnl": [120.50, 102.90, 117.20],
                "trend_direction": "up",
            }
        }


class AttributionTrendsResponse(BaseModel):
    """Response for /api/v1/analytics/attribution/trends endpoint"""
    success: bool = Field(
        default=True,
        description="Whether the request was successful"
    )
    trends: List[TrendDataResponse] = Field(
        description="Trend analysis for each dimension value"
    )
    period: str = Field(
        description="Time period granularity used"
    )
    lookback_days: int = Field(
        description="Number of days analyzed"
    )
    dimension: str = Field(
        description="Attribution dimension analyzed"
    )
    generated_at: str = Field(
        description="When the analysis was generated"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "trends": [
                    {
                        "dimension": "strategy",
                        "value": "pairs_trading",
                        "periods": ["2025-12-05", "2025-12-06", "2025-12-07"],
                        "pnl_trend": [120.50, 85.30, 145.80],
                        "win_rate_trend": [60.0, 55.0, 65.0],
                        "trades_count_trend": [5, 4, 6],
                        "moving_avg_pnl": [120.50, 102.90, 117.20],
                        "trend_direction": "up",
                    }
                ],
                "period": "daily",
                "lookback_days": 7,
                "dimension": "strategy",
                "generated_at": "2025-12-11T14:30:00Z",
            }
        }


# =============================================================================
# TRADE RECORD MODELS
# =============================================================================

class TradeRecordResponse(BaseModel):
    """Trade record in API response format"""
    trade_id: str = Field(
        description="Unique trade identifier"
    )
    symbol: str = Field(
        description="Trading pair symbol"
    )
    strategy: str = Field(
        description="Strategy that generated the trade"
    )
    direction: str = Field(
        description="Trade direction (long/short)"
    )
    entry_time: str = Field(
        description="Entry timestamp (ISO format)"
    )
    exit_time: str = Field(
        description="Exit timestamp (ISO format)"
    )
    entry_price: float = Field(
        description="Entry price"
    )
    exit_price: float = Field(
        description="Exit price"
    )
    quantity: float = Field(
        description="Trade quantity"
    )
    pnl: float = Field(
        description="Profit/loss in USD"
    )
    pnl_pct: float = Field(
        description="Profit/loss as percentage"
    )
    fees: float = Field(
        description="Trading fees paid"
    )
    market_condition: str = Field(
        description="Market condition during trade"
    )
    is_winner: bool = Field(
        description="Whether trade was profitable"
    )
    duration_seconds: int = Field(
        description="Trade duration in seconds"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "trade_id": "tr_123456789",
                "symbol": "SOLUSDT",
                "strategy": "pairs_trading",
                "direction": "long",
                "entry_time": "2025-12-11T10:30:00Z",
                "exit_time": "2025-12-11T14:45:00Z",
                "entry_price": 225.50,
                "exit_price": 228.75,
                "quantity": 0.5,
                "pnl": 1.625,
                "pnl_pct": 1.44,
                "fees": 0.15,
                "market_condition": "trending_up",
                "is_winner": True,
                "duration_seconds": 15300,
            }
        }


# =============================================================================
# PERFORMANCE DECOMPOSITION MODELS
# =============================================================================

class PerformanceDecompositionResponse(BaseModel):
    """Performance decomposition result"""
    strategy: str = Field(
        description="Strategy name"
    )
    alpha: float = Field(
        description="Alpha (strategy-specific return/skill)"
    )
    beta: float = Field(
        description="Beta (market correlation)"
    )
    residual: float = Field(
        description="Residual (unexplained variance)"
    )
    r_squared: float = Field(
        description="R-squared (coefficient of determination)"
    )
    total_return: float = Field(
        description="Total return as percentage"
    )
    benchmark_return: float = Field(
        description="Benchmark return as percentage"
    )
    information_ratio: float = Field(
        description="Information ratio"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "strategy": "pairs_trading",
                "alpha": 0.0125,
                "beta": 0.85,
                "residual": 0.0035,
                "r_squared": 0.72,
                "total_return": 12.5,
                "benchmark_return": 8.2,
                "information_ratio": 1.23,
            }
        }


# =============================================================================
# DAILY REPORT MODEL
# =============================================================================

class DailyAttributionReportResponse(BaseModel):
    """Daily attribution report response"""
    success: bool = Field(
        default=True,
        description="Whether the report was generated successfully"
    )
    date: str = Field(
        description="Report date (YYYY-MM-DD)"
    )
    generated_at: str = Field(
        description="When the report was generated"
    )
    trades_today: int = Field(
        description="Number of trades executed today"
    )
    overall_pnl: float = Field(
        description="Today's total P&L"
    )
    win_rate: float = Field(
        description="Today's win rate as percentage"
    )
    top_strategies: List[AttributionResultResponse] = Field(
        description="Top performing strategies today"
    )
    top_symbols: List[AttributionResultResponse] = Field(
        description="Top performing symbols today"
    )
    current_equity: float = Field(
        description="Current portfolio equity"
    )
    peak_equity: float = Field(
        description="Peak portfolio equity"
    )
    current_drawdown: float = Field(
        description="Current drawdown from peak"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "date": "2025-12-11",
                "generated_at": "2025-12-11T23:59:00Z",
                "trades_today": 12,
                "overall_pnl": 185.50,
                "win_rate": 66.7,
                "top_strategies": [],
                "top_symbols": [],
                "current_equity": 11250.50,
                "peak_equity": 11350.00,
                "current_drawdown": -0.88,
            }
        }


# =============================================================================
# ERROR RESPONSE MODEL
# =============================================================================

class AttributionErrorResponse(BaseModel):
    """Error response for attribution endpoints"""
    success: bool = Field(
        default=False,
        description="Always False for error responses"
    )
    error: str = Field(
        description="Error message"
    )
    error_code: str = Field(
        description="Error code for programmatic handling"
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional error details"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "error": "No trades found in the specified period",
                "error_code": "NO_TRADES",
                "details": {
                    "period_start": "2025-12-01T00:00:00Z",
                    "period_end": "2025-12-11T23:59:59Z",
                },
            }
        }


# =============================================================================
# POST-TRADE ANALYSIS MODELS (Phase 4.3)
# =============================================================================

class PostTradeAnalysisRequest(BaseModel):
    """Request model for post-trade analysis"""
    trade_id: str = Field(..., description="Unique trade identifier")
    symbol: str = Field(..., description="Trading symbol (e.g., BTCUSDT)")
    side: str = Field(..., description="Trade side: BUY or SELL")
    size: float = Field(..., description="Order size in base currency", gt=0)
    expected_price: float = Field(..., description="Expected execution price", gt=0)
    execution_price: float = Field(..., description="Actual average fill price", gt=0)
    fees: float = Field(0.0, description="Total fees paid", ge=0)
    order_type: str = Field("MARKET", description="Order type: MARKET, LIMIT, etc.")
    decision_timestamp: Optional[datetime] = Field(None, description="When trade decision was made")
    execution_timestamp: Optional[datetime] = Field(None, description="When trade was executed")
    strategy: str = Field("unknown", description="Strategy name")
    benchmark_prices: Optional[Dict[str, float]] = Field(
        None, description="Benchmark prices for comparison"
    )
    market_data: Optional[Dict[str, Any]] = Field(
        None, description="Additional market data (volatility, spread, etc.)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "trade_id": "tr_20251212_001",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "size": 1.5,
                "expected_price": 43000.00,
                "execution_price": 43020.50,
                "fees": 12.90,
                "order_type": "MARKET",
                "strategy": "momentum",
                "benchmark_prices": {"vwap": 43010.00, "twap": 43008.50},
                "market_data": {"spread_bps": 5.0, "volatility": 0.02},
            }
        }


class SlippageBreakdownResponse(BaseModel):
    """Response model for slippage breakdown"""
    market_impact: float = Field(..., description="Market impact cost in USD")
    spread_cost: float = Field(..., description="Spread crossing cost in USD")
    timing_cost: float = Field(..., description="Timing/adverse selection cost in USD")
    total_slippage: float = Field(..., description="Total slippage cost in USD")
    slippage_bps: float = Field(..., description="Total slippage in basis points")

    class Config:
        json_schema_extra = {
            "example": {
                "market_impact": 15.00,
                "spread_cost": 5.00,
                "timing_cost": 0.50,
                "total_slippage": 20.50,
                "slippage_bps": 4.77,
            }
        }


class ExecutionQualityResponse(BaseModel):
    """Response model for execution quality metrics"""
    implementation_shortfall: float = Field(..., description="Implementation shortfall")
    implementation_shortfall_bps: float = Field(..., description="Implementation shortfall in bps")
    price_improvement: float = Field(..., description="Price improvement achieved")
    price_improvement_bps: float = Field(..., description="Price improvement in bps")
    fill_rate: float = Field(..., description="Percentage of order filled")
    time_to_completion: float = Field(..., description="Seconds to complete execution")
    spread_capture_rate: float = Field(..., description="Spread capture rate for limit orders")
    benchmark_comparisons: Dict[str, float] = Field(
        default_factory=dict, description="Performance vs benchmarks in bps"
    )
    quality_score: int = Field(..., description="Overall quality score (0-100)", ge=0, le=100)
    quality_grade: QualityGradeEnum = Field(..., description="Quality grade")

    class Config:
        json_schema_extra = {
            "example": {
                "implementation_shortfall": 0.00047,
                "implementation_shortfall_bps": 4.77,
                "price_improvement": 0.0,
                "price_improvement_bps": 0.0,
                "fill_rate": 100.0,
                "time_to_completion": 0.5,
                "spread_capture_rate": 0.0,
                "benchmark_comparisons": {"vwap": 2.43, "twap": 2.78},
                "quality_score": 85,
                "quality_grade": "good",
            }
        }


class TradeClassificationResponse(BaseModel):
    """Response model for trade classification"""
    execution_style: ExecutionStyleEnum = Field(..., description="Execution style")
    market_condition: MarketConditionEnum = Field(..., description="Market condition during trade")
    liquidity_level: LiquidityLevelEnum = Field(..., description="Liquidity level")
    trading_session: TradingSessionEnum = Field(..., description="Trading session")
    order_urgency: str = Field(..., description="Order urgency level")

    class Config:
        json_schema_extra = {
            "example": {
                "execution_style": "aggressive",
                "market_condition": "stable",
                "liquidity_level": "normal",
                "trading_session": "us",
                "order_urgency": "normal",
            }
        }


class TradeExecutionReport(BaseModel):
    """Complete trade execution report response"""
    trade_id: str = Field(..., description="Unique trade identifier")
    symbol: str = Field(..., description="Trading symbol")
    side: str = Field(..., description="Trade side")
    size: float = Field(..., description="Order size")
    expected_price: float = Field(..., description="Expected price")
    execution_price: float = Field(..., description="Actual execution price")
    slippage: SlippageBreakdownResponse = Field(..., description="Slippage breakdown")
    fees: float = Field(..., description="Total fees")
    total_cost: float = Field(..., description="Total execution cost")
    cost_bps: float = Field(..., description="Total cost in basis points")
    execution_quality: ExecutionQualityResponse = Field(..., description="Execution quality metrics")
    classification: TradeClassificationResponse = Field(..., description="Trade classification")
    recommendations: List[str] = Field(default_factory=list, description="Improvement recommendations")
    analyzed_at: datetime = Field(..., description="Analysis timestamp")
    strategy: str = Field(..., description="Strategy name")

    class Config:
        json_schema_extra = {
            "example": {
                "trade_id": "tr_20251212_001",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "size": 1.5,
                "expected_price": 43000.00,
                "execution_price": 43020.50,
                "slippage": {
                    "market_impact": 15.00,
                    "spread_cost": 5.00,
                    "timing_cost": 0.50,
                    "total_slippage": 20.50,
                    "slippage_bps": 4.77,
                },
                "fees": 12.90,
                "total_cost": 33.40,
                "cost_bps": 7.77,
                "execution_quality": {
                    "implementation_shortfall": 0.00047,
                    "implementation_shortfall_bps": 4.77,
                    "price_improvement": 0.0,
                    "price_improvement_bps": 0.0,
                    "fill_rate": 100.0,
                    "time_to_completion": 0.5,
                    "spread_capture_rate": 0.0,
                    "benchmark_comparisons": {},
                    "quality_score": 85,
                    "quality_grade": "good",
                },
                "classification": {
                    "execution_style": "aggressive",
                    "market_condition": "stable",
                    "liquidity_level": "normal",
                    "trading_session": "us",
                    "order_urgency": "normal",
                },
                "recommendations": [
                    "Use limit orders for this size in stable markets"
                ],
                "analyzed_at": "2025-12-12T10:30:00Z",
                "strategy": "momentum",
            }
        }


class DailySummaryResponse(BaseModel):
    """Daily execution summary response"""
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    total_trades: int = Field(..., description="Total number of trades")
    total_volume: float = Field(..., description="Total trading volume in USD")
    avg_slippage_bps: float = Field(..., description="Average slippage in basis points")
    avg_cost_bps: float = Field(..., description="Average total cost in basis points")
    avg_quality_score: float = Field(..., description="Average quality score")
    total_fees: float = Field(..., description="Total fees paid")
    total_slippage_cost: float = Field(..., description="Total slippage cost")
    best_trade: Optional[Dict[str, Any]] = Field(None, description="Best execution of the day")
    worst_trade: Optional[Dict[str, Any]] = Field(None, description="Worst execution of the day")
    by_strategy: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict, description="Breakdown by strategy"
    )
    by_symbol: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict, description="Breakdown by symbol"
    )
    by_session: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict, description="Breakdown by session"
    )
    recommendations: List[str] = Field(default_factory=list, description="Daily recommendations")
    generated_at: datetime = Field(..., description="Report generation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "date": "2025-12-12",
                "total_trades": 25,
                "total_volume": 150000.00,
                "avg_slippage_bps": 5.2,
                "avg_cost_bps": 8.5,
                "avg_quality_score": 78.5,
                "total_fees": 85.50,
                "total_slippage_cost": 78.00,
                "best_trade": {"trade_id": "tr_001", "score": 95},
                "worst_trade": {"trade_id": "tr_015", "score": 45},
                "by_strategy": {"momentum": {"trade_count": 15, "avg_cost_bps": 7.5}},
                "by_symbol": {"BTCUSDT": {"trade_count": 10, "avg_cost_bps": 6.8}},
                "by_session": {"us": {"trade_count": 15, "avg_cost_bps": 7.2}},
                "recommendations": ["Consider using limit orders during US session"],
                "generated_at": "2025-12-12T23:59:00Z",
            }
        }


class ImprovementRecommendationResponse(BaseModel):
    """Improvement recommendation response"""
    category: str = Field(..., description="Recommendation category")
    priority: str = Field(..., description="Priority level: high, medium, low")
    recommendation: str = Field(..., description="Detailed recommendation")
    expected_savings_bps: float = Field(..., description="Expected savings in basis points")
    applicable_to: List[str] = Field(default_factory=list, description="Applicable strategies/symbols")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Supporting evidence")

    class Config:
        json_schema_extra = {
            "example": {
                "category": "execution_strategy",
                "priority": "high",
                "recommendation": "Use TWAP for orders >$10,000 to reduce market impact",
                "expected_savings_bps": 3.5,
                "applicable_to": ["momentum", "mean_reversion"],
                "evidence": {
                    "avg_slippage_large_orders": 12.5,
                    "avg_slippage_small_orders": 5.2,
                },
            }
        }


class BestWorstExecutionsResponse(BaseModel):
    """Response for best/worst executions endpoint"""
    report_type: str = Field(..., description="Report type: best_executions or worst_executions")
    generated_at: datetime = Field(..., description="Generation timestamp")
    count: int = Field(..., description="Number of executions")
    executions: List[Dict[str, Any]] = Field(default_factory=list, description="Execution details")
    common_patterns: List[str] = Field(default_factory=list, description="Common patterns identified")

    class Config:
        json_schema_extra = {
            "example": {
                "report_type": "best_executions",
                "generated_at": "2025-12-12T10:30:00Z",
                "count": 10,
                "executions": [
                    {
                        "trade_id": "tr_001",
                        "symbol": "BTCUSDT",
                        "score": 95,
                        "cost_bps": 2.5,
                    }
                ],
                "common_patterns": [
                    "70% of best executions during US session",
                    "80% used limit orders",
                ],
            }
        }


class StrategyAnalysisResponse(BaseModel):
    """Response for strategy-specific analysis"""
    strategy: str = Field(..., description="Strategy name")
    trade_count: int = Field(..., description="Total trades")
    avg_slippage_bps: float = Field(..., description="Average slippage in bps")
    avg_cost_bps: float = Field(..., description="Average cost in bps")
    avg_quality_score: float = Field(..., description="Average quality score")
    min_quality_score: int = Field(..., description="Minimum quality score")
    max_quality_score: int = Field(..., description="Maximum quality score")
    trades: List[Dict[str, Any]] = Field(
        default_factory=list, description="Individual trade summaries"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "strategy": "momentum",
                "trade_count": 45,
                "avg_slippage_bps": 6.5,
                "avg_cost_bps": 9.2,
                "avg_quality_score": 75.5,
                "min_quality_score": 35,
                "max_quality_score": 95,
                "trades": [],
            }
        }


class SymbolAnalysisResponse(BaseModel):
    """Response for symbol-specific analysis"""
    symbol: str = Field(..., description="Trading symbol")
    trade_count: int = Field(..., description="Total trades")
    avg_slippage_bps: float = Field(..., description="Average slippage in bps")
    avg_cost_bps: float = Field(..., description="Average cost in bps")
    avg_quality_score: float = Field(..., description="Average quality score")
    min_quality_score: int = Field(..., description="Minimum quality score")
    max_quality_score: int = Field(..., description="Maximum quality score")
    trades: List[Dict[str, Any]] = Field(
        default_factory=list, description="Individual trade summaries"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "BTCUSDT",
                "trade_count": 30,
                "avg_slippage_bps": 5.8,
                "avg_cost_bps": 8.5,
                "avg_quality_score": 78.0,
                "min_quality_score": 40,
                "max_quality_score": 92,
                "trades": [],
            }
        }


class WeeklyComparisonResponse(BaseModel):
    """Response for weekly comparison report"""
    week_start: str = Field(..., description="Week start date")
    week_end: str = Field(..., description="Week end date")
    report_generated_at: datetime = Field(..., description="Report generation timestamp")
    current_week: Dict[str, Any] = Field(..., description="Current week metrics")
    previous_week: Optional[Dict[str, Any]] = Field(None, description="Previous week metrics")
    wow_changes: Dict[str, Any] = Field(..., description="Week-over-week changes")
    trends: Dict[str, str] = Field(..., description="Trend directions")
    best_executions: List[Dict[str, Any]] = Field(default_factory=list)
    worst_executions: List[Dict[str, Any]] = Field(default_factory=list)
    strategy_comparison: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    symbol_comparison: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    insights: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "week_start": "2025-12-09",
                "week_end": "2025-12-15",
                "report_generated_at": "2025-12-12T10:30:00Z",
                "current_week": {"trade_count": 50, "avg_cost_bps": 7.5},
                "previous_week": {"trade_count": 45, "avg_cost_bps": 8.2},
                "wow_changes": {"cost_change_bps": -0.7, "quality_change": 2.5},
                "trends": {"slippage": "improving", "quality": "stable"},
                "best_executions": [],
                "worst_executions": [],
                "strategy_comparison": {},
                "symbol_comparison": {},
                "insights": ["Execution costs improved 8.5% week-over-week"],
                "recommendations": ["Continue using current limit order strategy"],
            }
        }


class PostTradeAnalysisSummaryResponse(BaseModel):
    """Summary of all post-trade analyses"""
    total_analyses: int = Field(..., description="Total number of analyses")
    avg_slippage_bps: float = Field(0.0, description="Average slippage in bps")
    avg_cost_bps: float = Field(0.0, description="Average cost in bps")
    avg_quality_score: float = Field(0.0, description="Average quality score")
    total_slippage_cost: float = Field(0.0, description="Total slippage cost")
    total_fees: float = Field(0.0, description="Total fees")
    unique_strategies: int = Field(0, description="Number of unique strategies")
    unique_symbols: int = Field(0, description="Number of unique symbols")
    quality_distribution: Dict[str, int] = Field(
        default_factory=dict, description="Distribution by quality grade"
    )
    message: Optional[str] = Field(None, description="Additional message")

    class Config:
        json_schema_extra = {
            "example": {
                "total_analyses": 150,
                "avg_slippage_bps": 6.2,
                "avg_cost_bps": 9.5,
                "avg_quality_score": 72.5,
                "total_slippage_cost": 450.00,
                "total_fees": 225.00,
                "unique_strategies": 5,
                "unique_symbols": 8,
                "quality_distribution": {
                    "excellent": 15,
                    "good": 45,
                    "fair": 60,
                    "poor": 25,
                    "very_poor": 5,
                },
                "message": None,
            }
        }
