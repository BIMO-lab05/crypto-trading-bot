"""
Dynamic Risk Budget API Handlers - Phase 3.3
Purpose: REST API endpoints for dynamic risk budget management

Endpoints:
- GET /api/v1/risk/budget/current - Current risk budget
- GET /api/v1/risk/budget/utilization - Risk used vs available
- GET /api/v1/risk/budget/allocation - Per-strategy allocation
- POST /api/v1/risk/budget/calculate - Calculate for conditions
- POST /api/v1/risk/budget/adjust - Manual adjustment
- GET /api/v1/risk/budget/history - Historical risk budget

Phase 3.3 - Dynamic Risk Budgeting Implementation
Author: Backend Developer Agent
Date: 2025-12-12
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.risk.dynamic_risk_budget import (
    get_risk_budget_manager,
    reset_risk_budget_manager,
    MarketRegime,
    EmergencyTrigger,
    RiskBudgetAlertSeverity,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/risk/budget", tags=["risk", "budget"])


# =============================================================================
# PYDANTIC REQUEST/RESPONSE MODELS
# =============================================================================


class CurrentBudgetResponse(BaseModel):
    """Response model for current budget endpoint"""

    success: bool
    budget: Dict[str, Any] = Field(description="Current risk budget details")
    utilization: Dict[str, Any] = Field(description="Budget utilization breakdown")
    emergency_mode: bool = Field(description="Whether emergency mode is active")
    config: Dict[str, Any] = Field(description="Budget configuration")
    timestamp: str

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "budget": {
                    "base_budget_pct": 2.0,
                    "base_budget_usd": 2000.0,
                    "adjusted_budget_pct": 1.6,
                    "adjusted_budget_usd": 1600.0,
                    "volatility_multiplier": 0.8,
                    "drawdown_multiplier": 1.0,
                    "streak_multiplier": 1.0,
                    "correlation_multiplier": 1.0,
                    "liquidity_multiplier": 1.0,
                    "combined_multiplier": 0.8,
                    "market_regime": "ELEVATED_VOLATILITY",
                    "risk_level": "conservative",
                },
                "utilization": {
                    "total_budget_usd": 1600.0,
                    "used_budget_usd": 400.0,
                    "available_budget_usd": 1200.0,
                    "utilization_pct": 25.0,
                },
                "emergency_mode": False,
                "config": {"base_equity": 10000.0, "base_risk_pct": 2.0},
                "timestamp": "2025-12-12T10:30:00Z",
            }
        }


class UtilizationResponse(BaseModel):
    """Response model for utilization endpoint"""

    success: bool
    total_budget_usd: float = Field(description="Total available budget")
    used_budget_usd: float = Field(description="Currently used budget")
    available_budget_usd: float = Field(description="Remaining available")
    utilization_pct: float = Field(description="Utilization percentage")
    by_strategy: Dict[str, Dict[str, float]] = Field(description="Usage by strategy")
    by_asset: Dict[str, Dict[str, float]] = Field(description="Usage by asset")
    emergency_mode: bool
    current_risk_level: str
    timestamp: str

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "total_budget_usd": 1600.0,
                "used_budget_usd": 600.0,
                "available_budget_usd": 1000.0,
                "utilization_pct": 37.5,
                "by_strategy": {
                    "pairs_trading": {
                        "allocated": 640.0,
                        "used": 300.0,
                        "available": 340.0,
                        "utilization_pct": 46.9,
                    },
                    "mean_reversion": {
                        "allocated": 480.0,
                        "used": 200.0,
                        "available": 280.0,
                        "utilization_pct": 41.7,
                    },
                },
                "by_asset": {
                    "BTCUSDT": {"used": 300.0, "pct_of_total": 18.75},
                    "ETHUSDT": {"used": 200.0, "pct_of_total": 12.5},
                },
                "emergency_mode": False,
                "current_risk_level": "conservative",
                "timestamp": "2025-12-12T10:30:00Z",
            }
        }


class AllocationRequest(BaseModel):
    """Request model for setting strategy allocations"""

    strategies: Dict[str, float] = Field(
        ..., description="Strategy name to allocation percentage (0-100)"
    )
    performance: Optional[Dict[str, Dict[str, float]]] = Field(
        default=None, description="Optional performance metrics per strategy"
    )

    @field_validator("strategies")
    @classmethod
    def validate_allocations(cls, v):
        total = sum(v.values())
        if total > 100:
            raise ValueError(f"Total allocation ({total}%) exceeds 100%")
        if any(pct < 0 for pct in v.values()):
            raise ValueError("Allocation percentages must be non-negative")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "strategies": {
                    "pairs_trading": 40.0,
                    "mean_reversion": 30.0,
                    "momentum": 30.0,
                },
                "performance": {
                    "pairs_trading": {"sharpe_ratio": 1.5, "trades_count": 25},
                    "mean_reversion": {"sharpe_ratio": 1.2, "trades_count": 30},
                },
            }
        }


class AllocationResponse(BaseModel):
    """Response model for allocation endpoint"""

    success: bool
    allocations: Dict[str, Dict[str, Any]] = Field(description="Strategy allocations")
    total_budget_usd: float
    timestamp: str

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "allocations": {
                    "pairs_trading": {
                        "strategy_name": "pairs_trading",
                        "allocation_pct": 40.0,
                        "allocated_budget_usd": 640.0,
                        "current_usage_usd": 0.0,
                        "available_budget_usd": 640.0,
                        "utilization_pct": 0.0,
                        "performance_multiplier": 1.2,
                        "effective_budget_usd": 768.0,
                    }
                },
                "total_budget_usd": 1600.0,
                "timestamp": "2025-12-12T10:30:00Z",
            }
        }


class CalculateBudgetRequest(BaseModel):
    """Request model for budget calculation"""

    equity: float = Field(..., gt=0, description="Current equity/capital")
    volatility_percentile: Optional[float] = Field(
        default=None, ge=0, le=100, description="Volatility as percentile (0-100)"
    )
    current_drawdown: Optional[float] = Field(
        default=None, ge=0, le=100, description="Current drawdown percentage"
    )
    win_streak: Optional[int] = Field(
        default=None, ge=0, description="Number of consecutive wins"
    )
    loss_streak: Optional[int] = Field(
        default=None, ge=0, description="Number of consecutive losses"
    )
    avg_correlation: Optional[float] = Field(
        default=None, ge=0, le=1, description="Average portfolio correlation"
    )
    market_regime: Optional[str] = Field(
        default=None,
        description="Market regime (LOW_VOLATILITY, NORMAL, ELEVATED_VOLATILITY, HIGH_VOLATILITY, EXTREME_VOLATILITY)",
    )

    @field_validator("market_regime")
    @classmethod
    def validate_regime(cls, v):
        if v is not None:
            valid = [r.value for r in MarketRegime]
            if v.upper() not in valid:
                raise ValueError(f"Invalid market regime. Must be one of: {valid}")
            return v.upper()
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "equity": 10000,
                "volatility_percentile": 65,
                "current_drawdown": 5.0,
                "win_streak": 3,
                "avg_correlation": 0.45,
                "market_regime": "ELEVATED_VOLATILITY",
            }
        }


class CalculateBudgetResponse(BaseModel):
    """Response model for budget calculation"""

    success: bool
    base_budget_pct: float
    base_budget_usd: float
    adjusted_budget_pct: float
    adjusted_budget_usd: float
    multipliers: Dict[str, float]
    market_regime: str
    risk_level: str
    max_position_size: float
    recommendations: List[str]
    timestamp: str

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "base_budget_pct": 2.0,
                "base_budget_usd": 2000.0,
                "adjusted_budget_pct": 1.44,
                "adjusted_budget_usd": 1440.0,
                "multipliers": {
                    "volatility": 0.8,
                    "drawdown": 0.9,
                    "streak": 1.0,
                    "correlation": 1.0,
                    "liquidity": 1.0,
                    "combined": 0.72,
                },
                "market_regime": "ELEVATED_VOLATILITY",
                "risk_level": "conservative",
                "max_position_size": 1440.0,
                "recommendations": [
                    "High volatility detected (65th percentile). Consider reducing position sizes.",
                    "Portfolio in drawdown (5.0%). Focus on capital preservation.",
                ],
                "timestamp": "2025-12-12T10:30:00Z",
            }
        }


class AdjustBudgetRequest(BaseModel):
    """Request model for manual budget adjustment"""

    adjustment_type: str = Field(
        ..., description="Type: 'increase', 'decrease', 'set_level', 'emergency_stop'"
    )
    value: Optional[float] = Field(
        default=None,
        description="Adjustment value (% for increase/decrease, level for set_level)",
    )
    reason: str = Field(
        default="Manual adjustment", description="Reason for adjustment"
    )

    @field_validator("adjustment_type")
    @classmethod
    def validate_type(cls, v):
        valid = ["increase", "decrease", "set_level", "emergency_stop"]
        if v.lower() not in valid:
            raise ValueError(f"Invalid adjustment type. Must be one of: {valid}")
        return v.lower()

    class Config:
        json_schema_extra = {
            "example": {
                "adjustment_type": "decrease",
                "value": 0.5,
                "reason": "Market showing weakness",
            }
        }


class AdjustBudgetResponse(BaseModel):
    """Response model for budget adjustment"""

    success: bool
    adjustment_type: str
    previous_risk_pct: float
    new_risk_pct: float
    reason: str
    timestamp: str

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "adjustment_type": "decrease",
                "previous_risk_pct": 2.0,
                "new_risk_pct": 1.5,
                "reason": "Market showing weakness",
                "timestamp": "2025-12-12T10:30:00Z",
            }
        }


class BudgetHistoryResponse(BaseModel):
    """Response model for budget history"""

    success: bool
    entries: List[Dict[str, Any]]
    period_hours: int
    entry_count: int
    timestamp: str

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "entries": [
                    {
                        "timestamp": "2025-12-12T09:00:00Z",
                        "equity": 10000,
                        "risk_budget_pct": 2.0,
                        "risk_budget_usd": 2000.0,
                        "market_regime": "NORMAL",
                        "volatility_percentile": 50,
                    }
                ],
                "period_hours": 24,
                "entry_count": 24,
                "timestamp": "2025-12-12T10:30:00Z",
            }
        }


# =============================================================================
# API ENDPOINT HANDLERS
# =============================================================================


@router.get("/current", response_model=CurrentBudgetResponse)
async def get_current_budget():
    """
    Get current risk budget state

    Returns the current risk budget including:
    - Base and adjusted budget amounts
    - All multipliers (volatility, drawdown, streak, etc.)
    - Current utilization
    - Emergency mode status
    - Configuration

    This is the primary endpoint for monitoring risk budget status.
    """
    try:
        manager = get_risk_budget_manager()
        current_state = manager.get_current_budget()

        logger.info(
            f"Current budget requested: "
            f"${current_state['budget']['adjusted_budget_usd']:.0f} "
            f"({current_state['budget']['adjusted_budget_pct']:.2f}%)"
        )

        return CurrentBudgetResponse(
            success=True,
            budget=current_state["budget"],
            utilization=current_state["utilization"],
            emergency_mode=current_state["emergency_mode"],
            config=current_state["config"],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.error(f"Failed to get current budget: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve current budget: {str(e)}"
        )


@router.get("/utilization", response_model=UtilizationResponse)
async def get_risk_utilization():
    """
    Get risk budget utilization breakdown

    Returns detailed utilization including:
    - Total vs used vs available budget
    - Usage breakdown by strategy
    - Usage breakdown by asset
    - Current risk level

    Use this to monitor how much of the risk budget is currently deployed.
    """
    try:
        manager = get_risk_budget_manager()
        utilization = manager.get_risk_utilization()

        logger.info(
            f"Utilization requested: "
            f"{utilization.utilization_pct:.1f}% "
            f"(${utilization.used_budget_usd:.0f}/${utilization.total_budget_usd:.0f})"
        )

        return UtilizationResponse(
            success=True,
            total_budget_usd=utilization.total_budget_usd,
            used_budget_usd=utilization.used_budget_usd,
            available_budget_usd=utilization.available_budget_usd,
            utilization_pct=utilization.utilization_pct,
            by_strategy=utilization.by_strategy,
            by_asset=utilization.by_asset,
            emergency_mode=utilization.emergency_mode,
            current_risk_level=utilization.current_risk_level,
            timestamp=utilization.timestamp,
        )

    except Exception as e:
        logger.error(f"Failed to get utilization: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve utilization: {str(e)}"
        )


@router.get("/allocation", response_model=AllocationResponse)
async def get_strategy_allocations():
    """
    Get per-strategy risk budget allocations

    Returns allocation details for each configured strategy including:
    - Allocation percentage
    - Allocated budget in USD
    - Current usage
    - Performance multiplier
    - Effective budget after performance adjustment
    """
    try:
        manager = get_risk_budget_manager()

        # Get current budget for total
        budget = manager.calculate_risk_budget()
        total_budget = budget.adjusted_budget_usd

        # Get allocations
        allocations_raw = manager._strategy_allocations
        allocations = {}

        for strategy_name in allocations_raw.keys():
            alloc = manager.get_strategy_allocation(strategy_name)
            if alloc:
                allocations[strategy_name] = alloc.to_dict()

        logger.info(
            f"Allocations requested: {len(allocations)} strategies, "
            f"total=${total_budget:.0f}"
        )

        return AllocationResponse(
            success=True,
            allocations=allocations,
            total_budget_usd=round(total_budget, 2),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.error(f"Failed to get allocations: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve allocations: {str(e)}"
        )


@router.post("/allocation", response_model=AllocationResponse)
async def set_strategy_allocations(request: AllocationRequest):
    """
    Set strategy risk budget allocations

    Configure how the total risk budget is distributed across trading strategies.

    Request body:
    - strategies: Dict of strategy_name -> allocation_percentage (must sum to <= 100%)
    - performance: Optional performance metrics for performance-based adjustment

    Returns the updated allocation for each strategy.
    """
    try:
        manager = get_risk_budget_manager()

        # Set allocations
        allocations = manager.allocate_to_strategies(
            strategies=request.strategies,
            performance=request.performance,
        )

        # Convert to dict
        allocations_dict = {
            name: alloc.to_dict() for name, alloc in allocations.items()
        }

        # Get total budget
        budget = manager.calculate_risk_budget()

        logger.info(
            f"Set allocations for {len(request.strategies)} strategies: "
            f"{request.strategies}"
        )

        return AllocationResponse(
            success=True,
            allocations=allocations_dict,
            total_budget_usd=round(budget.adjusted_budget_usd, 2),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except ValueError as e:
        logger.warning(f"Invalid allocation request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to set allocations: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to set allocations: {str(e)}"
        )


@router.post("/calculate", response_model=CalculateBudgetResponse)
async def calculate_risk_budget(request: CalculateBudgetRequest):
    """
    Calculate risk budget for given market conditions

    Calculates the optimal risk budget based on:
    - Current equity
    - Volatility level (VIX-style percentile)
    - Portfolio drawdown
    - Win/loss streak
    - Portfolio correlation
    - Market regime

    Formula:
        final_budget = base_risk * vol_adj * dd_adj * streak_adj * corr_adj * liq_adj

    Returns detailed breakdown of all multipliers and recommendations.
    """
    try:
        manager = get_risk_budget_manager()

        # Parse market regime if provided
        regime = None
        if request.market_regime:
            regime = MarketRegime(request.market_regime)

        # Calculate budget
        result = manager.calculate_risk_budget(
            equity=request.equity,
            volatility_percentile=request.volatility_percentile,
            drawdown_pct=request.current_drawdown,
            win_streak=request.win_streak,
            loss_streak=request.loss_streak,
            avg_correlation=request.avg_correlation,
            market_regime=regime,
        )

        logger.info(
            f"Budget calculated: equity=${request.equity:,.0f}, "
            f"result=${result.adjusted_budget_usd:.0f} ({result.adjusted_budget_pct:.2f}%)"
        )

        return CalculateBudgetResponse(
            success=True,
            base_budget_pct=result.base_budget_pct,
            base_budget_usd=result.base_budget_usd,
            adjusted_budget_pct=result.adjusted_budget_pct,
            adjusted_budget_usd=result.adjusted_budget_usd,
            multipliers={
                "volatility": result.volatility_multiplier,
                "drawdown": result.drawdown_multiplier,
                "streak": result.streak_multiplier,
                "correlation": result.correlation_multiplier,
                "liquidity": result.liquidity_multiplier,
                "combined": result.combined_multiplier,
            },
            market_regime=result.market_regime,
            risk_level=result.risk_level,
            max_position_size=result.max_position_size,
            recommendations=result.recommendations,
            timestamp=result.timestamp,
        )

    except Exception as e:
        logger.error(f"Failed to calculate budget: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to calculate budget: {str(e)}"
        )


@router.post("/adjust", response_model=AdjustBudgetResponse)
async def adjust_risk_budget(request: AdjustBudgetRequest):
    """
    Manually adjust risk budget

    Allows manual override of the risk budget for special circumstances.

    Adjustment types:
    - 'increase': Increase risk budget by value %
    - 'decrease': Decrease risk budget by value %
    - 'set_level': Set risk budget to specific value %
    - 'emergency_stop': Trigger emergency mode (minimum risk)

    Use with caution - manual adjustments override automatic calculations.
    """
    try:
        manager = get_risk_budget_manager()

        # Perform adjustment
        adjustment = manager.manual_adjust(
            adjustment_type=request.adjustment_type,
            value=request.value,
            reason=request.reason,
            adjusted_by="api_user",
        )

        logger.warning(
            f"Manual budget adjustment: {request.adjustment_type} "
            f"{adjustment.previous_risk_pct:.2f}% -> {adjustment.new_risk_pct:.2f}% "
            f"({request.reason})"
        )

        return AdjustBudgetResponse(
            success=True,
            adjustment_type=adjustment.adjustment_type,
            previous_risk_pct=adjustment.previous_risk_pct,
            new_risk_pct=adjustment.new_risk_pct,
            reason=adjustment.reason,
            timestamp=adjustment.timestamp,
        )

    except ValueError as e:
        logger.warning(f"Invalid adjustment request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to adjust budget: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to adjust budget: {str(e)}"
        )


@router.get("/history", response_model=BudgetHistoryResponse)
async def get_budget_history(
    hours: int = Query(
        default=24, ge=1, le=720, description="Number of hours of history to retrieve"
    ),
):
    """
    Get historical risk budget data

    Returns budget history for the specified time period including:
    - Timestamp
    - Equity at that time
    - Risk budget percentage and USD
    - Market regime
    - Volatility percentile
    - All multipliers

    Useful for:
    - Analyzing budget changes over time
    - Understanding how market conditions affected risk
    - Backtesting risk management decisions
    """
    try:
        manager = get_risk_budget_manager()

        # Get history
        history = manager.get_budget_history(hours=hours)

        logger.info(f"Budget history requested: {hours} hours, {len(history)} entries")

        return BudgetHistoryResponse(
            success=True,
            entries=history,
            period_hours=hours,
            entry_count=len(history),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.error(f"Failed to get history: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve history: {str(e)}"
        )


# =============================================================================
# ADDITIONAL UTILITY ENDPOINTS
# =============================================================================


@router.get("/alerts")
async def get_budget_alerts(
    min_severity: str = Query(
        default="WARNING",
        description="Minimum severity: INFO, WARNING, HIGH, CRITICAL, EMERGENCY",
    ),
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    Get risk budget alerts

    Returns alerts generated by the risk budget system including:
    - High utilization warnings
    - Emergency mode triggers
    - Risk level changes

    Args:
        min_severity: Minimum alert severity to include
        limit: Maximum number of alerts to return
    """
    try:
        manager = get_risk_budget_manager()

        # Parse severity
        try:
            severity = RiskBudgetAlertSeverity(min_severity.upper())
        except ValueError:
            severity = RiskBudgetAlertSeverity.WARNING

        alerts = manager.get_alerts(min_severity=severity, limit=limit)

        return {
            "success": True,
            "alerts": alerts,
            "count": len(alerts),
            "min_severity": severity.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to get alerts: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve alerts: {str(e)}"
        )


@router.post("/emergency/trigger")
async def trigger_emergency(
    reason: str = Query(..., description="Reason for emergency trigger"),
):
    """
    Manually trigger emergency risk reduction

    Use in extreme situations to immediately reduce risk exposure.
    This will:
    - Set emergency mode flag
    - Reduce risk budget to minimum
    - Generate critical alert

    WARNING: This should only be used in genuine emergencies.
    """
    try:
        manager = get_risk_budget_manager()

        result = manager.emergency_risk_reduction(
            trigger_reason=EmergencyTrigger.MANUAL_TRIGGER,
            details=reason,
        )

        logger.critical(f"Emergency risk reduction triggered via API: {reason}")

        return {
            "success": True,
            "message": "Emergency risk reduction activated",
            **result,
        }

    except Exception as e:
        logger.error(f"Failed to trigger emergency: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to trigger emergency: {str(e)}"
        )


@router.post("/emergency/clear")
async def clear_emergency(
    reason: str = Query(
        default="Manual clear via API", description="Reason for clearing emergency"
    ),
):
    """
    Clear emergency mode and resume normal operations

    Clears the emergency flag and allows normal risk budget calculations.
    Verify market conditions are stable before clearing.
    """
    try:
        manager = get_risk_budget_manager()

        result = manager.clear_emergency_mode(reason=reason)

        logger.warning(f"Emergency mode cleared via API: {reason}")

        return {
            "success": True,
            "message": "Emergency mode cleared",
            **result,
        }

    except Exception as e:
        logger.error(f"Failed to clear emergency: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to clear emergency: {str(e)}"
        )


@router.delete("/reset")
async def reset_budget_manager():
    """
    Reset risk budget manager to initial state

    Clears all:
    - Strategy allocations
    - Usage tracking
    - History
    - Alerts

    WARNING: This cannot be undone. Use with caution.
    """
    try:
        reset_risk_budget_manager()

        logger.warning("Risk budget manager reset via API")

        return {
            "success": True,
            "message": "Risk budget manager reset to initial state",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to reset manager: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to reset manager: {str(e)}"
        )


# =============================================================================
# STANDALONE HANDLER FUNCTIONS (for handlers/__init__.py export)
# =============================================================================


async def get_current_budget_handler() -> Dict[str, Any]:
    """Handler function for current budget"""
    manager = get_risk_budget_manager()
    return manager.get_current_budget()


async def get_utilization_handler() -> Dict[str, Any]:
    """Handler function for utilization"""
    manager = get_risk_budget_manager()
    utilization = manager.get_risk_utilization()
    return utilization.to_dict()


async def get_allocation_handler() -> Dict[str, Any]:
    """Handler function for allocations"""
    manager = get_risk_budget_manager()
    budget = manager.calculate_risk_budget()

    allocations = {}
    for strategy_name in manager._strategy_allocations.keys():
        alloc = manager.get_strategy_allocation(strategy_name)
        if alloc:
            allocations[strategy_name] = alloc.to_dict()

    return {
        "allocations": allocations,
        "total_budget_usd": budget.adjusted_budget_usd,
    }


async def calculate_budget_handler(
    equity: float,
    volatility_percentile: Optional[float] = None,
    current_drawdown: Optional[float] = None,
    win_streak: Optional[int] = None,
    avg_correlation: Optional[float] = None,
) -> Dict[str, Any]:
    """Handler function for budget calculation"""
    manager = get_risk_budget_manager()
    result = manager.calculate_risk_budget(
        equity=equity,
        volatility_percentile=volatility_percentile,
        drawdown_pct=current_drawdown,
        win_streak=win_streak,
        avg_correlation=avg_correlation,
    )
    return result.to_dict()


async def adjust_budget_handler(
    adjustment_type: str,
    value: Optional[float] = None,
    reason: str = "Manual adjustment",
) -> Dict[str, Any]:
    """Handler function for budget adjustment"""
    manager = get_risk_budget_manager()
    adjustment = manager.manual_adjust(
        adjustment_type=adjustment_type,
        value=value,
        reason=reason,
    )
    return adjustment.to_dict()


async def get_history_handler(hours: int = 24) -> List[Dict[str, Any]]:
    """Handler function for budget history"""
    manager = get_risk_budget_manager()
    return manager.get_budget_history(hours=hours)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Router
    "router",
    # Endpoint handlers
    "get_current_budget",
    "get_risk_utilization",
    "get_strategy_allocations",
    "set_strategy_allocations",
    "calculate_risk_budget",
    "adjust_risk_budget",
    "get_budget_history",
    "get_budget_alerts",
    "trigger_emergency",
    "clear_emergency",
    "reset_budget_manager",
    # Standalone handlers
    "get_current_budget_handler",
    "get_utilization_handler",
    "get_allocation_handler",
    "calculate_budget_handler",
    "adjust_budget_handler",
    "get_history_handler",
]
