"""
Pydantic models for Statistical Arbitrage API
Provides request/response validation and OpenAPI documentation
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, ValidationInfo, field_validator


# ============================================================================
# REQUEST MODELS
# ============================================================================


class InitializeManagerRequest(BaseModel):
    """Request model for initializing Statistical Arbitrage Manager"""

    total_capital: float = Field(
        default=100000.0,
        gt=0,
        description="Total capital to allocate across strategies",
        example=100000.0,
    )
    pairs_allocation: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Percentage allocation for pairs trading (0.0-1.0)",
        example=0.4,
    )
    funding_allocation: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Percentage allocation for funding rate arbitrage (0.0-1.0)",
        example=0.4,
    )
    triangular_allocation: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Percentage allocation for triangular arbitrage (0.0-1.0)",
        example=0.2,
    )

    @field_validator("pairs_allocation", "funding_allocation", "triangular_allocation")
    @classmethod
    def validate_allocation(cls, v):
        """Validate that allocations are between 0 and 1"""
        if v < 0 or v > 1:
            raise ValueError(f"Allocation must be between 0 and 1, got {v}")
        return v

    @field_validator("triangular_allocation")
    @classmethod
    def validate_total_allocation(cls, v, info: ValidationInfo):
        """Validate that total allocation sums to 1.0"""
        total = (
            info.data.get("pairs_allocation", 0)
            + info.data.get("funding_allocation", 0)
            + v
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError(
                f"Allocations must sum to 1.0, got {total:.3f}. "
                f"pairs={info.data.get('pairs_allocation')}, "
                f"funding={info.data.get('funding_allocation')}, "
                f"triangular={v}"
            )
        return v

    class Config:
        schema_extra = {
            "example": {
                "total_capital": 100000.0,
                "pairs_allocation": 0.4,
                "funding_allocation": 0.4,
                "triangular_allocation": 0.2,
            }
        }


class AddPairsStrategyRequest(BaseModel):
    """Request model for adding a pairs trading strategy"""

    symbol_x: str = Field(
        ..., description="First symbol in the pair (e.g., BTCUSDT)", example="BTCUSDT"
    )
    symbol_y: str = Field(
        ..., description="Second symbol in the pair (e.g., ETHUSDT)", example="ETHUSDT"
    )
    entry_threshold: float = Field(
        default=2.0,
        gt=0,
        description="Z-score threshold to enter position",
        example=2.0,
    )
    exit_threshold: float = Field(
        default=0.5, gt=0, description="Z-score threshold to exit position", example=0.5
    )
    lookback_period: int = Field(
        default=20,
        gt=0,
        description="Historical period for spread calculation",
        example=20,
    )
    stop_loss_z: float = Field(
        default=3.0, gt=0, description="Maximum z-score before stop loss", example=3.0
    )

    @field_validator("symbol_x", "symbol_y")
    @classmethod
    def validate_symbol(cls, v):
        """Validate symbol format"""
        if not v or len(v) < 3:
            raise ValueError(f"Invalid symbol: {v}")
        return v.upper()

    @field_validator("exit_threshold")
    @classmethod
    def validate_exit_threshold(cls, v, info: ValidationInfo):
        """Validate that exit threshold is less than entry threshold"""
        entry = info.data.get("entry_threshold", 2.0)
        if v >= entry:
            raise ValueError(
                f"Exit threshold ({v}) must be less than entry threshold ({entry})"
            )
        return v

    class Config:
        schema_extra = {
            "example": {
                "symbol_x": "BTCUSDT",
                "symbol_y": "ETHUSDT",
                "entry_threshold": 2.0,
                "exit_threshold": 0.5,
                "lookback_period": 20,
                "stop_loss_z": 3.0,
            }
        }


class CalibratePairsStrategyRequest(BaseModel):
    """Request model for calibrating a pairs trading strategy"""

    strategy_id: str = Field(
        ..., description="ID of the strategy to calibrate", example="BTCUSDT_ETHUSDT"
    )
    historical_data: Optional[Dict[str, Any]] = Field(
        default=None, description="Historical price data for calibration"
    )

    class Config:
        schema_extra = {
            "example": {
                "strategy_id": "BTCUSDT_ETHUSDT",
                "historical_data": {
                    "BTCUSDT": [45000, 45100, 45200],
                    "ETHUSDT": [3000, 3010, 3020],
                },
            }
        }


class AddFundingStrategyRequest(BaseModel):
    """Request model for adding a funding rate arbitrage strategy"""

    symbol: str = Field(
        ..., description="Trading symbol (e.g., BTCUSDT)", example="BTCUSDT"
    )
    min_funding_rate: float = Field(
        default=0.0001,
        ge=0,
        description="Minimum funding rate to trigger trade (0.01%)",
        example=0.0001,
    )
    max_position_size: float = Field(
        default=10000.0,
        gt=0,
        description="Maximum position size in USDT",
        example=10000.0,
    )

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v):
        """Validate symbol format"""
        if not v or len(v) < 3:
            raise ValueError(f"Invalid symbol: {v}")
        return v.upper()

    class Config:
        schema_extra = {
            "example": {
                "symbol": "BTCUSDT",
                "min_funding_rate": 0.0001,
                "max_position_size": 10000.0,
            }
        }


class SetupTriangularArbitrageRequest(BaseModel):
    """Request model for setting up triangular arbitrage"""

    assets: List[str] = Field(
        ...,
        min_items=3,
        description="List of assets for triangular arbitrage paths",
        example=["BTC", "ETH", "BNB", "USDT"],
    )
    min_profit_threshold: float = Field(
        default=0.005,
        gt=0,
        le=1.0,
        description="Minimum profit percentage to execute (0.5%)",
        example=0.005,
    )
    max_latency_ms: float = Field(
        default=100.0,
        gt=0,
        description="Maximum acceptable latency in milliseconds",
        example=100.0,
    )

    @field_validator("assets")
    @classmethod
    def validate_assets(cls, v):
        """Validate assets list"""
        if len(v) < 3:
            raise ValueError("At least 3 assets required for triangular arbitrage")
        # Convert to uppercase and remove duplicates
        unique_assets = list(set(asset.upper() for asset in v))
        if len(unique_assets) != len(v):
            raise ValueError("Duplicate assets found in list")
        return unique_assets

    class Config:
        schema_extra = {
            "example": {
                "assets": ["BTC", "ETH", "BNB", "USDT"],
                "min_profit_threshold": 0.005,
                "max_latency_ms": 100.0,
            }
        }


class GenerateSignalsRequest(BaseModel):
    """Request model for generating signals from all strategies"""

    market_data: Dict[str, Dict[str, float]] = Field(
        ...,
        description="Current market data including prices, volumes, funding rates",
        example={
            "BTCUSDT": {"price": 45000.0, "volume": 1000000},
            "ETHUSDT": {"price": 3000.0, "volume": 500000},
        },
    )

    @field_validator("market_data")
    @classmethod
    def validate_market_data(cls, v):
        """Validate market data structure"""
        if not v:
            raise ValueError("Market data cannot be empty")

        for symbol, data in v.items():
            if not isinstance(data, dict):
                raise ValueError(f"Invalid data format for {symbol}")
            if "price" not in data:
                raise ValueError(f"Price missing for {symbol}")
            if data["price"] <= 0:
                raise ValueError(f"Invalid price for {symbol}: {data['price']}")

        return v

    class Config:
        schema_extra = {
            "example": {
                "market_data": {
                    "BTCUSDT": {
                        "price": 45000.0,
                        "volume": 1000000,
                        "funding_rate": 0.0001,
                    },
                    "ETHUSDT": {
                        "price": 3000.0,
                        "volume": 500000,
                        "funding_rate": 0.0002,
                    },
                }
            }
        }


# ============================================================================
# RESPONSE MODELS
# ============================================================================


class StrategyAllocationResponse(BaseModel):
    """Response model for strategy allocation"""

    pairs_trading: float = Field(description="Pairs trading allocation percentage")
    funding_rate: float = Field(
        description="Funding rate arbitrage allocation percentage"
    )
    triangular: float = Field(description="Triangular arbitrage allocation percentage")

    class Config:
        schema_extra = {
            "example": {"pairs_trading": 0.4, "funding_rate": 0.4, "triangular": 0.2}
        }


class InitializeManagerResponse(BaseModel):
    """Response model for manager initialization"""

    status: str = Field(description="Initialization status")
    config: Dict[str, Any] = Field(description="Manager configuration")
    message: str = Field(description="Human-readable message")

    class Config:
        schema_extra = {
            "example": {
                "status": "success",
                "config": {
                    "total_capital": 100000.0,
                    "allocation": {
                        "pairs_trading": 0.4,
                        "funding_rate": 0.4,
                        "triangular": 0.2,
                    },
                },
                "message": "Statistical Arbitrage Manager initialized successfully",
            }
        }


class StrategyResponse(BaseModel):
    """Response model for adding a strategy"""

    status: str = Field(description="Operation status")
    strategy_id: str = Field(description="Unique strategy identifier")
    strategy_type: str = Field(description="Type of strategy")
    config: Dict[str, Any] = Field(description="Strategy configuration")
    allocated_capital: float = Field(description="Capital allocated to this strategy")

    class Config:
        schema_extra = {
            "example": {
                "status": "success",
                "strategy_id": "BTCUSDT_ETHUSDT",
                "strategy_type": "pairs_trading",
                "config": {
                    "symbol_x": "BTCUSDT",
                    "symbol_y": "ETHUSDT",
                    "entry_threshold": 2.0,
                    "exit_threshold": 0.5,
                },
                "allocated_capital": 13333.33,
            }
        }


class PairsTradeSignalResponse(BaseModel):
    """Response model for a pairs trade signal"""

    action: str = Field(description="Trading action")
    symbol_x: str = Field(description="First symbol")
    symbol_y: str = Field(description="Second symbol")
    z_score: float = Field(description="Current spread z-score")
    hedge_ratio: float = Field(description="Optimal hedge ratio")
    position_size_x: float = Field(description="Position size for symbol X")
    position_size_y: float = Field(description="Position size for symbol Y")
    confidence: float = Field(description="Signal confidence")
    timestamp: str = Field(description="Signal timestamp")


class FundingRateSignalResponse(BaseModel):
    """Response model for a funding rate signal"""

    action: str = Field(description="Trading action")
    symbol: str = Field(description="Trading symbol")
    funding_rate: float = Field(description="Current funding rate")
    expected_apr: float = Field(description="Expected annualized return")
    spot_position_size: float = Field(description="Spot position size")
    futures_position_size: float = Field(description="Futures position size")
    timestamp: str = Field(description="Signal timestamp")


class TriangularArbitrageSignalResponse(BaseModel):
    """Response model for a triangular arbitrage signal"""

    action: str = Field(description="Trading action")
    path: List[str] = Field(description="Arbitrage path")
    execution_amount: float = Field(description="Amount to trade")
    gross_profit_pct: float = Field(description="Gross profit percentage")
    net_profit_pct: float = Field(description="Net profit after fees")
    estimated_latency_ms: float = Field(description="Estimated execution time")
    timestamp: str = Field(description="Signal timestamp")


class SignalsResponse(BaseModel):
    """Response model for generated signals"""

    status: str = Field(description="Operation status")
    signals: Dict[str, List[Dict[str, Any]]] = Field(
        description="Generated signals by strategy type"
    )
    timestamp: str = Field(description="Generation timestamp")
    total_signals: int = Field(description="Total number of signals generated")

    class Config:
        schema_extra = {
            "example": {
                "status": "success",
                "signals": {
                    "pairs": [
                        {
                            "strategy_id": "BTCUSDT_ETHUSDT",
                            "signal": {
                                "action": "LONG_X_SHORT_Y",
                                "z_score": 2.5,
                                "confidence": 0.85,
                            },
                        }
                    ],
                    "funding": [],
                    "triangular": [],
                },
                "timestamp": "2025-12-07T10:00:00",
                "total_signals": 1,
            }
        }


class StrategyPerformanceResponse(BaseModel):
    """Response model for individual strategy performance"""

    strategy_id: str = Field(description="Strategy identifier")
    strategy_type: str = Field(description="Strategy type")
    trades: int = Field(description="Number of trades executed")
    pnl: float = Field(description="Total profit/loss")
    win_rate: float = Field(description="Percentage of winning trades")
    sharpe_ratio: float = Field(description="Risk-adjusted return metric")
    max_drawdown: float = Field(description="Maximum drawdown percentage")


class PerformanceResponse(BaseModel):
    """Response model for performance metrics"""

    status: str = Field(description="Operation status")
    performance: Dict[str, Any] = Field(description="Performance metrics")
    timestamp: str = Field(description="Report timestamp")

    class Config:
        schema_extra = {
            "example": {
                "status": "success",
                "performance": {
                    "total_capital": 100000.0,
                    "total_pnl": 5234.50,
                    "total_trades": 47,
                    "winning_trades": 31,
                    "losing_trades": 16,
                    "win_rate": 0.659,
                    "sharpe_ratio": 2.34,
                    "max_drawdown": 0.032,
                    "strategies": {
                        "BTCUSDT_ETHUSDT": {
                            "strategy_type": "pairs_trading",
                            "trades": 15,
                            "pnl": 1234.50,
                            "win_rate": 0.733,
                        }
                    },
                },
                "timestamp": "2025-12-07T10:00:00",
            }
        }


class StatusResponse(BaseModel):
    """Response model for manager status"""

    status: str = Field(description="Manager status")
    initialized: bool = Field(description="Whether manager is initialized")
    total_capital: Optional[float] = Field(description="Total managed capital")
    active_strategies: Dict[str, int] = Field(
        description="Count of active strategies by type"
    )
    allocation: Optional[Dict[str, float]] = Field(
        description="Capital allocation percentages"
    )

    class Config:
        schema_extra = {
            "example": {
                "status": "active",
                "initialized": True,
                "total_capital": 100000.0,
                "active_strategies": {
                    "pairs_trading": 3,
                    "funding_rate": 2,
                    "triangular": 1,
                },
                "allocation": {
                    "pairs_trading": 0.4,
                    "funding_rate": 0.4,
                    "triangular": 0.2,
                },
            }
        }


class ResetResponse(BaseModel):
    """Response model for manager reset"""

    status: str = Field(description="Operation status")
    message: str = Field(description="Human-readable message")
    strategies_cleared: int = Field(description="Number of strategies removed")

    class Config:
        schema_extra = {
            "example": {
                "status": "success",
                "message": "Statistical Arbitrage Manager reset successfully",
                "strategies_cleared": 6,
            }
        }


class ErrorResponse(BaseModel):
    """Response model for errors"""

    status: str = Field(default="error", description="Error status")
    error: str = Field(description="Error message")
    detail: Optional[str] = Field(
        default=None, description="Detailed error information"
    )

    class Config:
        schema_extra = {
            "example": {
                "status": "error",
                "error": "Manager not initialized",
                "detail": "Please call /initialize endpoint first",
            }
        }
