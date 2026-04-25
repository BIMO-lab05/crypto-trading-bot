"""
Smart Order Routing Handler
Phase 4.1: Smart Order Routing for Improved Execution

Purpose:
- Expose smart order routing functionality via REST API
- Provide endpoints for order type recommendations
- Track and report execution quality metrics
- Allow configuration of routing parameters

Endpoints:
- GET  /api/v1/execution/router-stats - Get router performance metrics
- GET  /api/v1/execution/router-status - Get router configuration and status
- POST /api/v1/execution/recommend - Get order type recommendation
- POST /api/v1/execution/analyze-orderbook - Analyze order book liquidity
- POST /api/v1/execution/estimate-slippage - Estimate slippage for order
- GET  /api/v1/execution/quality-report - Get execution quality report

Created: 2025-12-11
Author: Backend Developer Agent
"""

import logging
from decimal import Decimal
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

# Import smart router
from app.execution.smart_router import (
    SmartOrderRouter,
    SmartRouterConfig,
    ExecutionUrgency,
    get_smart_router,
    reset_smart_router,
)

# Configure logging
logger = logging.getLogger(__name__)

# Create FastAPI router for execution endpoints
router = APIRouter(prefix="/api/v1/execution", tags=["Smart Order Routing"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class OrderBookData(BaseModel):
    """Order book data for analysis"""
    bids: List[List[str]] = Field(
        description="Bid levels [[price, qty], ...]",
        example=[["50000.00", "1.5"], ["49999.00", "2.0"]]
    )
    asks: List[List[str]] = Field(
        description="Ask levels [[price, qty], ...]",
        example=[["50001.00", "1.5"], ["50002.00", "2.0"]]
    )


class RecommendationRequest(BaseModel):
    """Request for order type recommendation"""
    symbol: str = Field(description="Trading symbol", example="BTCUSDT")
    side: str = Field(description="Order side (BUY/SELL)", example="BUY")
    quantity: str = Field(description="Order quantity", example="0.1")
    urgency: str = Field(
        default="medium",
        description="Execution urgency (low/medium/high/critical)",
        example="medium"
    )
    orderbook: Optional[OrderBookData] = Field(
        default=None,
        description="Order book data (optional, will fetch if not provided)"
    )
    current_price: Optional[str] = Field(
        default=None,
        description="Current market price",
        example="50000.00"
    )


class SlippageRequest(BaseModel):
    """Request for slippage estimation"""
    symbol: str = Field(description="Trading symbol", example="BTCUSDT")
    side: str = Field(description="Order side (BUY/SELL)", example="BUY")
    quantity: str = Field(description="Order quantity", example="0.5")
    orderbook: OrderBookData = Field(description="Order book data")


class OrderBookAnalysisRequest(BaseModel):
    """Request for order book analysis"""
    symbol: str = Field(description="Trading symbol", example="BTCUSDT")
    orderbook: OrderBookData = Field(description="Order book data")
    current_price: Optional[str] = Field(default=None, description="Current price")


class RouterConfigUpdate(BaseModel):
    """Router configuration update request"""
    tight_spread_threshold: Optional[float] = Field(
        default=None,
        description="Spread below which market orders are preferred (as decimal)"
    )
    wide_spread_threshold: Optional[float] = Field(
        default=None,
        description="Spread above which limit orders are strongly preferred"
    )
    small_order_threshold: Optional[float] = Field(
        default=None,
        description="Order value (USD) below which single market order is used"
    )
    medium_order_threshold: Optional[float] = Field(
        default=None,
        description="Order value (USD) threshold for medium orders"
    )
    limit_timeout_seconds: Optional[int] = Field(
        default=None,
        description="Timeout for limit orders before fallback"
    )
    max_acceptable_slippage_pct: Optional[float] = Field(
        default=None,
        description="Maximum acceptable slippage percentage"
    )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _parse_urgency(urgency_str: str) -> ExecutionUrgency:
    """Parse urgency string to enum"""
    urgency_map = {
        "low": ExecutionUrgency.LOW,
        "medium": ExecutionUrgency.MEDIUM,
        "high": ExecutionUrgency.HIGH,
        "critical": ExecutionUrgency.CRITICAL
    }
    return urgency_map.get(urgency_str.lower(), ExecutionUrgency.MEDIUM)


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/router-stats")
async def get_router_stats():
    """
    Get smart router performance metrics

    Returns aggregate statistics about router performance including:
    - Total orders processed
    - Average slippage
    - Order type distribution
    - Fill rates

    Returns:
        Router performance metrics
    """
    try:
        smart_router = get_smart_router()
        metrics = smart_router.get_metrics()

        return {
            "success": True,
            "data": {
                "total_orders": metrics.total_orders,
                "successful_orders": metrics.successful_orders,
                "failed_orders": metrics.failed_orders,
                "partial_fills": metrics.partial_fills,
                "slippage": {
                    "average_pct": round(metrics.avg_slippage_pct, 4),
                    "max_pct": round(metrics.max_slippage_pct, 4),
                    "total_usd": round(metrics.total_slippage_usd, 2),
                    "vs_estimate": round(metrics.slippage_vs_estimate, 2) if metrics.slippage_vs_estimate else None
                },
                "fill_rates": {
                    "average": round(metrics.avg_fill_rate, 4),
                    "limit_orders": round(metrics.limit_order_fill_rate, 4)
                },
                "order_type_distribution": {
                    "market": metrics.market_orders,
                    "limit": metrics.limit_orders,
                    "post_only": metrics.post_only_orders,
                    "iceberg": metrics.iceberg_orders,
                    "twap": metrics.twap_orders
                },
                "timing": {
                    "avg_execution_time_ms": round(metrics.avg_execution_time_ms, 1)
                },
                "last_updated": metrics.last_updated.isoformat() if metrics.last_updated else None
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting router stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/router-status")
async def get_router_status():
    """
    Get router configuration and current status

    Returns:
        Router configuration and operational status
    """
    try:
        smart_router = get_smart_router()
        status = smart_router.get_status()

        return {
            "success": True,
            "data": status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting router status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recommend")
async def get_order_recommendation(request: RecommendationRequest):
    """
    Get intelligent order type recommendation

    Analyzes market conditions and order parameters to recommend
    the optimal order type and execution strategy.

    Args:
        request: RecommendationRequest with order details and market data

    Returns:
        Order type recommendation with reasoning
    """
    try:
        smart_router = get_smart_router()

        # Parse inputs
        quantity = Decimal(request.quantity)
        urgency = _parse_urgency(request.urgency)
        current_price = Decimal(request.current_price) if request.current_price else None

        # Prepare order book data
        orderbook_depth = None
        if request.orderbook:
            orderbook_depth = {
                "bids": request.orderbook.bids,
                "asks": request.orderbook.asks
            }

        # Get recommendation
        recommendation = smart_router.get_order_recommendation(
            symbol=request.symbol,
            side=request.side.upper(),
            quantity=quantity,
            urgency=urgency,
            orderbook_depth=orderbook_depth,
            current_price=current_price
        )

        # Format response
        response_data = {
            "symbol": recommendation.symbol,
            "side": recommendation.side,
            "quantity": str(recommendation.quantity),
            "order_value_usd": round(recommendation.order_value_usd, 2),
            "urgency": recommendation.urgency.value,
            "recommendation": {
                "order_type": recommendation.order_type.value,
                "strategy": recommendation.strategy.value,
                "limit_price": str(recommendation.limit_price) if recommendation.limit_price else None,
                "visible_quantity": str(recommendation.visible_quantity) if recommendation.visible_quantity else None,
                "chunks": recommendation.chunks if recommendation.chunks else None
            },
            "analysis": {
                "spread_pct": round(recommendation.orderbook_analysis.spread_pct * 100, 4) if recommendation.orderbook_analysis else None,
                "depth_total_usd": round(recommendation.orderbook_analysis.depth_total_usd, 0) if recommendation.orderbook_analysis else None,
                "is_thin_liquidity": recommendation.orderbook_analysis.is_thin_liquidity if recommendation.orderbook_analysis else None,
                "expected_slippage_pct": round(recommendation.slippage_estimate.expected_slippage_pct, 4) if recommendation.slippage_estimate else None,
                "slippage_cost_usd": round(recommendation.slippage_estimate.slippage_cost_usd, 2) if recommendation.slippage_estimate else None
            },
            "reasoning": recommendation.reasoning,
            "confidence": round(recommendation.confidence, 2)
        }

        logger.info(
            f"Recommendation for {request.symbol} {request.side} {request.quantity}: "
            f"{recommendation.order_type.value}/{recommendation.strategy.value}"
        )

        return {
            "success": True,
            "data": response_data,
            "timestamp": recommendation.timestamp.isoformat()
        }

    except ValueError as e:
        logger.error(f"Invalid request parameters: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {str(e)}")
    except Exception as e:
        logger.error(f"Error generating recommendation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-orderbook")
async def analyze_orderbook(request: OrderBookAnalysisRequest):
    """
    Analyze order book for liquidity metrics

    Examines order book structure to understand:
    - Current spread and mid-price
    - Available liquidity at various price levels
    - Order imbalance indicating buy/sell pressure
    - Thin liquidity conditions

    Args:
        request: OrderBookAnalysisRequest with order book data

    Returns:
        Comprehensive order book analysis
    """
    try:
        smart_router = get_smart_router()

        current_price = Decimal(request.current_price) if request.current_price else None

        analysis = smart_router.analyze_orderbook(
            symbol=request.symbol,
            bids=request.orderbook.bids,
            asks=request.orderbook.asks,
            current_price=current_price
        )

        return {
            "success": True,
            "data": {
                "symbol": analysis.symbol,
                "prices": {
                    "best_bid": str(analysis.best_bid),
                    "best_ask": str(analysis.best_ask),
                    "mid_price": str(analysis.mid_price)
                },
                "spread": {
                    "absolute": str(analysis.spread_absolute),
                    "percentage": round(analysis.spread_pct * 100, 4)
                },
                "depth": {
                    "bids_usd": round(analysis.depth_bids_usd, 0),
                    "asks_usd": round(analysis.depth_asks_usd, 0),
                    "total_usd": round(analysis.depth_total_usd, 0),
                    "at_01_pct": round(analysis.depth_at_01pct, 0),
                    "at_05_pct": round(analysis.depth_at_05pct, 0),
                    "at_1_pct": round(analysis.depth_at_1pct, 0)
                },
                "imbalance_ratio": round(analysis.imbalance_ratio, 3),
                "liquidity": {
                    "is_thin": analysis.is_thin_liquidity,
                    "warning": analysis.thin_liquidity_warning
                }
            },
            "timestamp": analysis.timestamp.isoformat()
        }

    except Exception as e:
        logger.error(f"Error analyzing order book: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/estimate-slippage")
async def estimate_slippage(request: SlippageRequest):
    """
    Estimate slippage for a potential order

    Calculates expected slippage by simulating order execution
    through the order book.

    Args:
        request: SlippageRequest with order and order book data

    Returns:
        Slippage estimation with cost analysis
    """
    try:
        smart_router = get_smart_router()

        quantity = Decimal(request.quantity)

        estimate = smart_router.estimate_slippage(
            symbol=request.symbol,
            side=request.side.upper(),
            quantity=quantity,
            bids=request.orderbook.bids,
            asks=request.orderbook.asks
        )

        return {
            "success": True,
            "data": {
                "symbol": estimate.symbol,
                "side": estimate.side,
                "quantity": str(estimate.quantity),
                "order_value_usd": round(estimate.order_value_usd, 2),
                "slippage": {
                    "expected_pct": round(estimate.expected_slippage_pct, 4),
                    "worst_case_pct": round(estimate.worst_case_slippage_pct, 4),
                    "best_case_pct": round(estimate.best_case_slippage_pct, 4),
                    "cost_usd": round(estimate.slippage_cost_usd, 2)
                },
                "execution": {
                    "mid_price": str(estimate.mid_price),
                    "expected_fill_price": str(estimate.execution_price),
                    "levels_consumed": estimate.levels_consumed
                },
                "assessment": {
                    "is_acceptable": estimate.is_acceptable,
                    "warning": estimate.warning_message
                }
            },
            "timestamp": estimate.timestamp.isoformat()
        }

    except ValueError as e:
        logger.error(f"Invalid slippage request: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {str(e)}")
    except Exception as e:
        logger.error(f"Error estimating slippage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quality-report")
async def get_execution_quality_report(
    period_hours: int = Query(default=24, ge=1, le=168, description="Report period in hours")
):
    """
    Get comprehensive execution quality report

    Analyzes router performance over specified time period and
    provides actionable recommendations for improvement.

    Args:
        period_hours: Number of hours to analyze (1-168)

    Returns:
        Execution quality report with recommendations
    """
    try:
        smart_router = get_smart_router()
        report = smart_router.get_execution_quality_report(period_hours=period_hours)

        return {
            "success": True,
            "data": {
                "period": {
                    "start": report.report_period_start.isoformat(),
                    "end": report.report_period_end.isoformat(),
                    "hours": period_hours
                },
                "summary": {
                    "total_orders": report.metrics.total_orders,
                    "successful_orders": report.metrics.successful_orders,
                    "failed_orders": report.metrics.failed_orders,
                    "avg_slippage_pct": round(report.metrics.avg_slippage_pct, 4),
                    "avg_fill_rate": round(report.metrics.avg_fill_rate, 4)
                },
                "performance": {
                    "slippage_reduction_pct": round(report.slippage_reduction_pct, 2),
                    "slippage_savings_usd": round(report.slippage_savings_usd, 2),
                    "fill_rate_improvement": round(report.fill_rate_improvement, 4)
                },
                "strategy_breakdown": report.strategy_breakdown,
                "order_type_breakdown": report.order_type_breakdown,
                "recommendations": report.recommendations
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error generating quality report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
async def reset_router():
    """
    Reset smart router instance

    Creates a fresh router instance with default configuration.
    Useful for testing or after configuration changes.

    Returns:
        Confirmation of reset
    """
    try:
        reset_smart_router()
        logger.info("Smart router reset")

        return {
            "success": True,
            "message": "Smart router reset successfully",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error resetting router: {e}")
        raise HTTPException(status_code=500, detail=str(e))
