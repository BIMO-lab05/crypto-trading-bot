"""
Orchestration API Handler
==========================
Purpose: API endpoints for Multi-Strategy Orchestration System

Provides 15 endpoints for strategy management, signal processing,
conflict resolution, and performance tracking.

Phase 9: Multi-Strategy Orchestration Engine
Author: Backend Developer Agent
Date: 2025-12-12
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, HTTPException, Body
from pydantic import BaseModel, Field
import uuid

from app.orchestration import (
    StrategyOrchestrator,
    get_strategy_orchestrator,
    StrategySignal,
    SignalDirection,
    ConflictResolutionMethod,
    AllocationMethod,
    RegisterStrategyRequest,
    UpdateAllocationRequest,
)
from app.orchestration.metrics import MetricsTrade
from app.orchestration.signal_aggregator import get_signal_aggregator
from app.orchestration.performance_tracker import get_performance_tracker
from app.orchestration.risk_coordinator import get_risk_coordinator

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/api/v1/orchestrator",
    tags=["Multi-Strategy Orchestration"]
)


# =============================================================================
# PYDANTIC MODELS FOR API
# =============================================================================

class StrategyRegistrationRequest(BaseModel):
    """Request to register a new strategy"""
    strategy_id: str = Field(..., description="Unique strategy identifier")
    name: str = Field(..., description="Human-readable strategy name")
    strategy_type: str = Field("trend_following", description="Strategy type")
    risk_profile: str = Field("moderate", description="Risk profile")
    symbols: List[str] = Field(default_factory=list, description="Supported symbols")
    timeframe: str = Field("1h", description="Primary timeframe")
    allocation_pct: float = Field(10.0, ge=0.0, le=100.0, description="Target allocation %")
    priority: int = Field(50, ge=1, le=100, description="Priority for conflict resolution")
    description: str = Field("", description="Strategy description")
    auto_activate: bool = Field(False, description="Auto-activate after registration")


class AllocationUpdateRequest(BaseModel):
    """Request to update strategy allocation"""
    allocations: Dict[str, float] = Field(..., description="Strategy ID to allocation % mapping")


class SignalSubmissionRequest(BaseModel):
    """Request to submit a trading signal"""
    strategy_id: str = Field(..., description="Strategy generating the signal")
    symbol: str = Field(..., description="Trading symbol")
    direction: str = Field(..., description="Signal direction: long, short, flat")
    action: str = Field(..., description="Action: BUY, SELL, CLOSE_LONG, CLOSE_SHORT")
    strength: float = Field(0.5, ge=-1.0, le=1.0, description="Signal strength")
    confidence: float = Field(0.5, ge=0.0, le=1.0, description="Signal confidence")
    entry_price: Optional[float] = Field(None, description="Suggested entry price")
    stop_loss_pct: Optional[float] = Field(None, description="Stop loss percentage")
    take_profit_pct: Optional[float] = Field(None, description="Take profit percentage")
    position_size_pct: Optional[float] = Field(None, description="Suggested position size %")
    urgency: str = Field("MEDIUM", description="Signal urgency")
    reasoning: str = Field("", description="Signal reasoning")


class ConflictResolutionRequest(BaseModel):
    """Request to resolve signal conflicts"""
    symbol: str = Field(..., description="Symbol with conflicts")
    method: str = Field("weighted_voting", description="Resolution method to use")


class RebalanceRequest(BaseModel):
    """Request to trigger rebalancing"""
    force: bool = Field(False, description="Force rebalance even if not needed")


# =============================================================================
# STRATEGY MANAGEMENT ENDPOINTS
# =============================================================================

@router.get("/strategies", summary="List registered strategies")
async def list_strategies():
    """
    Get list of all registered strategies

    Returns all registered strategies with their current status,
    allocation, and performance summary.
    """
    try:
        orchestrator = get_strategy_orchestrator()
        strategies = orchestrator.get_all_strategies_status()

        return {
            "success": True,
            "total": len(strategies),
            "strategies": strategies,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error listing strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/strategy/register", summary="Register new strategy")
async def register_strategy(request: StrategyRegistrationRequest):
    """
    Register a new trading strategy with the orchestrator

    The strategy will be added to the registry and allocation manager.
    If auto_activate is True, it will be activated immediately.
    """
    try:
        orchestrator = get_strategy_orchestrator()

        result = orchestrator.register_strategy(
            strategy_id=request.strategy_id,
            name=request.name,
            strategy_type=request.strategy_type,
            risk_profile=request.risk_profile,
            symbols=request.symbols,
            timeframe=request.timeframe,
            allocation_pct=request.allocation_pct,
            priority=request.priority,
            description=request.description,
            auto_activate=request.auto_activate
        )

        if result.get("success"):
            logger.info(f"Registered strategy: {request.strategy_id}")
            return {
                "success": True,
                "message": f"Strategy {request.strategy_id} registered successfully",
                **result
            }
        else:
            raise HTTPException(status_code=400, detail=result.get("error", "Registration failed"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/strategy/{strategy_id}/enable", summary="Enable strategy")
async def enable_strategy(
    strategy_id: str,
    warmup_minutes: int = Query(0, description="Warmup period in minutes")
):
    """
    Enable/activate a registered strategy

    The strategy will start generating signals and can participate
    in trading. Optional warmup period to gather initial data.
    """
    try:
        orchestrator = get_strategy_orchestrator()
        result = orchestrator.activate_strategy(strategy_id, warmup_minutes)

        if result.get("success"):
            return {
                "success": True,
                "message": f"Strategy {strategy_id} enabled",
                **result
            }
        else:
            raise HTTPException(status_code=400, detail=result.get("error", "Enable failed"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/strategy/{strategy_id}/disable", summary="Disable strategy")
async def disable_strategy(
    strategy_id: str,
    reason: str = Query("Manual disable", description="Reason for disabling")
):
    """
    Disable/deactivate a strategy

    The strategy will stop generating signals and will not participate
    in trading until re-enabled.
    """
    try:
        orchestrator = get_strategy_orchestrator()
        result = orchestrator.deactivate_strategy(strategy_id, reason)

        if result.get("success"):
            return {
                "success": True,
                "message": f"Strategy {strategy_id} disabled",
                **result
            }
        else:
            raise HTTPException(status_code=400, detail=result.get("error", "Disable failed"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ALLOCATION ENDPOINTS
# =============================================================================

@router.get("/allocation", summary="Get current allocation")
async def get_allocation():
    """
    Get current capital allocation across strategies

    Returns the target and current allocation percentages for
    each registered strategy along with summary statistics.
    """
    try:
        orchestrator = get_strategy_orchestrator()
        status = orchestrator.get_orchestrator_status()

        # Get allocation details from internal allocator
        from app.orchestration.allocation import get_allocation_manager
        allocator = get_allocation_manager()
        allocations = allocator.get_all_allocations()

        allocation_details = {}
        for strategy_id, alloc in allocations.items():
            allocation_details[strategy_id] = {
                "target_pct": alloc.target_pct,
                "current_pct": alloc.current_pct,
                "allocated_capital": alloc.allocated_capital,
                "available_capital": alloc.available_capital,
                "used_capital": alloc.used_capital,
                "risk_budget_pct": alloc.risk_budget_pct
            }

        return {
            "success": True,
            "total_capital": status["total_capital"],
            "total_allocated_pct": status["total_allocated_pct"],
            "total_used_pct": status["total_used_pct"],
            "cash_reserve_pct": status.get("cash_reserve_pct", 0),
            "allocations": allocation_details,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting allocation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/allocation", summary="Update allocation")
async def update_allocation(request: AllocationUpdateRequest):
    """
    Update capital allocation for strategies

    Allows changing target allocation percentages for multiple
    strategies at once. The system will recalculate actual allocations.
    """
    try:
        orchestrator = get_strategy_orchestrator()
        results = []

        for strategy_id, target_pct in request.allocations.items():
            result = orchestrator.update_allocation(
                strategy_id=strategy_id,
                target_pct=target_pct
            )
            results.append({
                "strategy_id": strategy_id,
                **result
            })

        success_count = sum(1 for r in results if r.get("success"))

        return {
            "success": success_count == len(request.allocations),
            "updated": success_count,
            "total": len(request.allocations),
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error updating allocation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# SIGNAL ENDPOINTS
# =============================================================================

@router.get("/signals/active", summary="Get active signals")
async def get_active_signals():
    """
    Get all currently active (pending) signals

    Returns signals grouped by symbol that are awaiting
    aggregation and execution.
    """
    try:
        aggregator = get_signal_aggregator()
        orchestrator = get_strategy_orchestrator()

        all_signals = orchestrator.get_all_pending_signals()

        signals_by_symbol = {}
        for symbol, signals in all_signals.items():
            signals_by_symbol[symbol] = [
                {
                    "signal_id": s.signal_id,
                    "strategy_id": s.strategy_id,
                    "direction": s.direction.value,
                    "action": s.action,
                    "strength": s.strength,
                    "confidence": s.confidence,
                    "urgency": s.urgency,
                    "timestamp": s.timestamp.isoformat()
                }
                for s in signals
            ]

        return {
            "success": True,
            "total_symbols": len(signals_by_symbol),
            "total_signals": sum(len(s) for s in signals_by_symbol.values()),
            "signals": signals_by_symbol,
            "stats": aggregator.get_stats(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting active signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/conflicts", summary="Get conflicting signals")
async def get_conflicting_signals():
    """
    Get signals with detected conflicts

    Returns symbols where strategies are providing opposing
    or significantly different signals.
    """
    try:
        aggregator = get_signal_aggregator()
        conflicts = aggregator.get_all_conflicts()

        conflict_details = {}
        for symbol, result in conflicts.items():
            conflict_details[symbol] = result.to_dict()

        return {
            "success": True,
            "conflict_count": len(conflicts),
            "conflicts": conflict_details,
            "history": aggregator.get_conflict_history(limit=10),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting conflicts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signals/resolve", summary="Resolve signal conflicts")
async def resolve_conflicts(request: ConflictResolutionRequest):
    """
    Manually trigger conflict resolution for a symbol

    Resolves conflicting signals using the specified method
    and returns the aggregated signal result.
    """
    try:
        orchestrator = get_strategy_orchestrator()

        # Parse resolution method
        try:
            method = ConflictResolutionMethod(request.method)
        except ValueError:
            method = ConflictResolutionMethod.WEIGHTED_VOTING

        aggregated = orchestrator.get_aggregated_signal(request.symbol, method)

        if aggregated:
            return {
                "success": True,
                "symbol": request.symbol,
                "method_used": method.value,
                "result": aggregated.to_dict(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            return {
                "success": False,
                "symbol": request.symbol,
                "message": "No signals to resolve",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    except Exception as e:
        logger.error(f"Error resolving conflicts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PERFORMANCE ENDPOINTS
# =============================================================================

@router.get("/performance/by-strategy", summary="Get performance by strategy")
async def get_performance_by_strategy():
    """
    Get detailed performance metrics for each strategy

    Returns comprehensive metrics including Sharpe ratio,
    win rate, drawdown, and trade statistics.
    """
    try:
        tracker = get_performance_tracker()
        orchestrator = get_strategy_orchestrator()

        strategies_status = orchestrator.get_all_strategies_status()
        performance_data = {}

        for status in strategies_status:
            strategy_id = status["strategy_id"]
            metrics = orchestrator.get_strategy_metrics(strategy_id)

            performance_data[strategy_id] = {
                "status": status["status"],
                "allocation_pct": status["current_allocation_pct"],
                "metrics": metrics,
                "trend": tracker._performance_trends.get(strategy_id, "unknown"),
                "is_underperforming": strategy_id in tracker._underperformer_records
            }

        return {
            "success": True,
            "strategy_count": len(performance_data),
            "strategies": performance_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/comparison", summary="Compare strategies")
async def compare_strategies():
    """
    Compare performance across all strategies

    Provides rankings by various metrics (Sharpe, win rate,
    profit factor) and comparative analysis.
    """
    try:
        orchestrator = get_strategy_orchestrator()
        comparison = orchestrator.compare_strategies()

        # Add correlations
        correlations = orchestrator.get_correlations()

        # Get diversification score
        tracker = get_performance_tracker()
        diversification = tracker.get_diversification_score()

        return {
            "success": True,
            "comparison": comparison,
            "correlations": correlations,
            "diversification": diversification,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error comparing strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# REBALANCING ENDPOINTS
# =============================================================================

@router.post("/rebalance", summary="Trigger rebalancing")
async def trigger_rebalance(request: RebalanceRequest = Body(default=RebalanceRequest())):
    """
    Trigger portfolio rebalancing

    Recalculates optimal allocations based on performance
    and executes rebalancing if needed.
    """
    try:
        orchestrator = get_strategy_orchestrator()

        # Check if rebalancing is needed
        from app.orchestration.allocation import get_allocation_manager
        allocator = get_allocation_manager()

        if not request.force and not allocator.needs_rebalancing():
            return {
                "success": True,
                "message": "Rebalancing not needed",
                "rebalanced": False,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        result = orchestrator.trigger_rebalance()

        return {
            "success": True,
            "rebalanced": True,
            **result,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error triggering rebalance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# RISK ENDPOINTS
# =============================================================================

@router.get("/risk/utilization", summary="Get risk utilization")
async def get_risk_utilization():
    """
    Get current risk utilization metrics

    Returns portfolio-wide and per-strategy risk metrics
    including exposure, drawdown, and position limits.
    """
    try:
        coordinator = get_risk_coordinator()
        utilization = coordinator.get_risk_utilization()

        return {
            "success": True,
            "utilization": utilization.to_dict(),
            "is_emergency_stopped": coordinator.is_emergency_stopped(),
            "status": coordinator.get_status(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting risk utilization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emergency-stop", summary="Emergency stop all strategies")
async def emergency_stop(
    reason: str = Query("Manual emergency stop", description="Reason for stop")
):
    """
    Trigger emergency stop for all trading

    Immediately pauses all strategies and can optionally
    close all open positions.
    """
    try:
        # Stop via risk coordinator
        coordinator = get_risk_coordinator()
        result = coordinator.emergency_stop(reason)

        # Also pause all strategies via orchestrator
        orchestrator = get_strategy_orchestrator()
        orchestrator.pause_all(reason)

        logger.critical(f"EMERGENCY STOP triggered: {reason}")

        return {
            "success": True,
            "message": "Emergency stop activated",
            "reason": reason,
            **result,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error triggering emergency stop: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# STATUS ENDPOINT
# =============================================================================

@router.get("/status", summary="Get orchestrator status")
async def get_orchestrator_status():
    """
    Get comprehensive orchestrator status

    Returns overall orchestrator status including active
    strategies, allocation, positions, and risk metrics.
    """
    try:
        orchestrator = get_strategy_orchestrator()
        status = orchestrator.get_orchestrator_status()

        # Add additional context
        aggregator = get_signal_aggregator()
        tracker = get_performance_tracker()
        coordinator = get_risk_coordinator()

        return {
            "success": True,
            "orchestrator": status,
            "signals": aggregator.get_stats(),
            "performance": tracker.get_status(),
            "risk": coordinator.get_status(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# HELPER FUNCTION FOR SIGNAL SUBMISSION
# =============================================================================

@router.post("/signals/submit", summary="Submit trading signal")
async def submit_signal(request: SignalSubmissionRequest):
    """
    Submit a trading signal from a strategy

    The signal will be collected and processed for conflict
    resolution and potential execution.
    """
    try:
        orchestrator = get_strategy_orchestrator()

        # Parse direction
        try:
            direction = SignalDirection(request.direction)
        except ValueError:
            direction = SignalDirection.FLAT

        # Create signal
        signal = StrategySignal(
            signal_id=f"sig_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            timestamp=datetime.now(timezone.utc),
            direction=direction,
            action=request.action,
            strength=request.strength,
            confidence=request.confidence,
            entry_price=Decimal(str(request.entry_price)) if request.entry_price else None,
            stop_loss_pct=request.stop_loss_pct,
            take_profit_pct=request.take_profit_pct,
            position_size_pct=request.position_size_pct,
            urgency=request.urgency,
            reasoning=request.reasoning
        )

        result = orchestrator.submit_signal(signal)

        return {
            "success": result.get("accepted", False),
            "signal_id": signal.signal_id,
            **result,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error submitting signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# INDICATOR ROLLING-CONFIDENCE GATE (2026-05-06)
# =============================================================================
# A previously-disabled indicator may not be re-enabled until its rolling-mean
# confidence over the last 200 calls clears `settings.min_indicator_confidence`.
# This is the *gate* — the persistence flag (master switch lookup) is left to a
# follow-up; the point is the gate sits in the path.
#
# Auth note: trading-engine has no auth middleware; all admin routes are
# protected upstream at the api-gateway. We name the prefix `/admin/...` for
# routing convention, but enforce nothing at this layer.

from app.config import get_settings
from app.services.indicator_registry import (
    IndicatorBelowThresholdError,
    get_indicator_registry,
)

admin_indicator_router = APIRouter(
    prefix="/api/v1/admin/indicators",
    tags=["Admin: Indicator Gate"],
)


@admin_indicator_router.post(
    "/{name}/enable",
    summary="Enable a TA indicator (gated by rolling-confidence)",
)
async def enable_indicator(name: str) -> Dict[str, Any]:
    """Enable an indicator after it clears the rolling-confidence gate.

    Flow:
        1. Query the IndicatorRegistry for the rolling-mean confidence
           over the last 200 calls.
        2. If < ``settings.min_indicator_confidence`` (or fewer than 30
           samples), raise 409 Conflict.
        3. Otherwise: would flip the indicator's master switch — left as
           a TODO since the persistence layer for indicator enablement
           does not exist today.

    This endpoint is the *gate*. It does not by itself re-enable the
    two known stuck indicators (RSI_DIVERGENCE, SQZMOM_ENHANCED) — they
    stay commented out in ``signal_aggregator.py`` until they
    accumulate enough shadow-mode samples to clear the gate.
    """
    settings = get_settings()
    registry = get_indicator_registry()
    try:
        await registry.assert_eligible(
            name=name,
            threshold=settings.min_indicator_confidence,
        )
    except IndicatorBelowThresholdError as exc:
        logger.warning(
            "Refusing to enable indicator %s: avg=%s threshold=%s",
            exc.name,
            exc.current_avg,
            exc.threshold,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "error": "indicator_below_threshold",
                "indicator": exc.name,
                "current_avg": exc.current_avg,
                "threshold": exc.threshold,
                "message": str(exc),
            },
        )

    # TODO: indicator master switch lookup
    # Persistence for the per-indicator enable flag does not exist yet.
    # When it lands, this is where the flip happens. For now we surface
    # that the gate passed so an operator can take the next step manually.
    stats = await registry.stats(name)
    logger.info("Indicator %s passed rolling-confidence gate", name)
    return {
        "success": True,
        "gated": True,
        "persisted": False,
        "indicator": name,
        "stats": stats,
        "note": (
            "Gate passed; persistence layer for indicator master-switch is "
            "not yet implemented. Re-enablement still requires a code change "
            "(uncomment in signal_aggregator.py)."
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@admin_indicator_router.get(
    "/{name}/stats",
    summary="Read rolling-confidence stats for an indicator",
)
async def get_indicator_stats(name: str) -> Dict[str, Any]:
    """Return rolling-confidence stats for ``name``. Read-only."""
    stats = await get_indicator_registry().stats(name)
    return {
        "success": True,
        **stats,
        "threshold": get_settings().min_indicator_confidence,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
