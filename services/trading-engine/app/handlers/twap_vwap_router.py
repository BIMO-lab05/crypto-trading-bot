"""
TWAP/VWAP Execution API Router
Phase 4.2: Enhanced TWAP/VWAP Execution Algorithms

Purpose:
- Expose TWAP (Time-Weighted Average Price) execution via REST API
- Expose VWAP (Volume-Weighted Average Price) execution via REST API
- Provide execution monitoring and control endpoints
- Generate execution quality reports

Endpoints (8 total):
- POST /api/v1/execution/twap - Execute TWAP order
- POST /api/v1/execution/vwap - Execute VWAP order
- GET  /api/v1/execution/twap/{order_id} - Get TWAP status
- GET  /api/v1/execution/vwap/{order_id} - Get VWAP status
- GET  /api/v1/execution/active-algorithms - List running algorithms
- POST /api/v1/execution/pause/{order_id} - Pause execution
- POST /api/v1/execution/cancel/{order_id} - Cancel execution
- GET  /api/v1/execution/performance-report - Execution quality report

Research Sources:
- TWAP/VWAP Execution Best Practices
- Implementation Shortfall Analysis (Perold)
- Algorithmic Trading API Design Patterns

Created: 2025-12-12
Author: Backend Developer Agent
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field, field_validator

# Import execution scheduler
from app.execution.execution_scheduler import (
    ExecutionScheduler,
    ScheduledOrder,
    ExecutionReport,
    OrderPriority,
    AlgorithmType,
    OrderLifecycleState,
    get_execution_scheduler,
    reset_execution_scheduler,
)

# Import TWAP/VWAP algorithms
from app.execution.twap_vwap import (
    TWAPAlgorithm,
    VWAPAlgorithm,
    TWAPConfig,
    VWAPConfig,
    AdaptiveMode,
    create_twap_algorithm,
    create_vwap_algorithm,
)

# Configure logging
logger = logging.getLogger(__name__)

# Create FastAPI router for TWAP/VWAP endpoints
router = APIRouter(prefix="/api/v1/execution", tags=["TWAP/VWAP Execution"])


# ============================================================================
# PYDANTIC MODELS - Request/Response Schemas
# ============================================================================


class TWAPOrderRequest(BaseModel):
    """
    Request model for TWAP order execution

    TWAP (Time-Weighted Average Price) splits the order into equal-sized
    chunks executed at regular time intervals.
    """
    symbol: str = Field(
        description="Trading symbol (e.g., BTCUSDT)",
        example="BTCUSDT"
    )
    side: str = Field(
        description="Order side: BUY or SELL",
        example="BUY"
    )
    size: str = Field(
        description="Total order size to execute",
        example="1.5"
    )
    duration_minutes: int = Field(
        default=10,
        ge=1,
        le=480,
        description="Total execution duration in minutes (1-480)",
        example=10
    )
    num_chunks: Optional[int] = Field(
        default=None,
        ge=3,
        le=100,
        description="Number of order slices (3-100). Auto-calculated if not provided"
    )
    interval_minutes: Optional[int] = Field(
        default=None,
        ge=1,
        le=60,
        description="Minutes between chunks (1-60). Auto-calculated if not provided"
    )
    arrival_price: Optional[str] = Field(
        default=None,
        description="Price at order submission for benchmarking",
        example="50000.00"
    )
    participation_rate: float = Field(
        default=0.15,
        ge=0.01,
        le=0.30,
        description="Target % of market volume per interval (1-30%)",
        example=0.15
    )
    randomize_timing: bool = Field(
        default=True,
        description="Add +/-20% variance to timing to avoid detection"
    )
    randomize_size: bool = Field(
        default=True,
        description="Add +/-10% variance to chunk sizes"
    )
    urgency: str = Field(
        default="medium",
        description="Execution urgency: low, medium, high",
        example="medium"
    )
    use_limit_orders: bool = Field(
        default=True,
        description="Use limit orders (True) or market orders (False)"
    )
    max_slippage_pct: float = Field(
        default=0.10,
        ge=0.01,
        le=1.0,
        description="Maximum acceptable slippage percentage (0.01-1.0%)"
    )
    pause_on_high_slippage: bool = Field(
        default=True,
        description="Auto-pause if slippage exceeds max threshold"
    )

    @field_validator('side')
    @classmethod
    def validate_side(cls, v):
        """Validate order side"""
        if v.upper() not in ('BUY', 'SELL'):
            raise ValueError('side must be BUY or SELL')
        return v.upper()

    @field_validator('urgency')
    @classmethod
    def validate_urgency(cls, v):
        """Validate urgency level"""
        if v.lower() not in ('low', 'medium', 'high'):
            raise ValueError('urgency must be low, medium, or high')
        return v.lower()

    @field_validator('size', 'arrival_price')
    @classmethod
    def validate_decimal(cls, v):
        """Validate decimal string values"""
        if v is None:
            return v
        try:
            d = Decimal(v)
            if d <= 0:
                raise ValueError('value must be positive')
            return v
        except InvalidOperation:
            raise ValueError('invalid decimal value')


class VWAPOrderRequest(BaseModel):
    """
    Request model for VWAP order execution

    VWAP (Volume-Weighted Average Price) splits the order based on
    historical volume patterns to match market rhythm.
    """
    symbol: str = Field(
        description="Trading symbol (e.g., BTCUSDT)",
        example="BTCUSDT"
    )
    side: str = Field(
        description="Order side: BUY or SELL",
        example="BUY"
    )
    size: str = Field(
        description="Total order size to execute",
        example="2.0"
    )
    duration_minutes: int = Field(
        default=10,
        ge=1,
        le=480,
        description="Total execution duration in minutes (1-480)",
        example=10
    )
    target_vwap: Optional[str] = Field(
        default=None,
        description="Target VWAP to track (optional)",
        example="50000.00"
    )
    arrival_price: Optional[str] = Field(
        default=None,
        description="Price at order submission for benchmarking",
        example="50000.00"
    )
    volume_profile: Optional[List[float]] = Field(
        default=None,
        description="Historical volume distribution (normalized or raw)",
        example=[0.05, 0.08, 0.12, 0.15, 0.18, 0.15, 0.12, 0.08, 0.05, 0.02]
    )
    participation_rate: float = Field(
        default=0.15,
        ge=0.01,
        le=0.30,
        description="Maximum % of market volume per interval (1-30%)"
    )
    urgency: str = Field(
        default="medium",
        description="Execution urgency: low, medium, high, urgent"
    )
    adaptive_mode: str = Field(
        default="neutral",
        description="Adaptive mode: passive, neutral, aggressive, urgent"
    )
    use_limit_orders: bool = Field(
        default=True,
        description="Use limit orders (True) or market orders (False)"
    )
    max_slippage_pct: float = Field(
        default=0.10,
        ge=0.01,
        le=1.0,
        description="Maximum acceptable slippage vs VWAP (0.01-1.0%)"
    )

    @field_validator('side')
    @classmethod
    def validate_side(cls, v):
        """Validate order side"""
        if v.upper() not in ('BUY', 'SELL'):
            raise ValueError('side must be BUY or SELL')
        return v.upper()

    @field_validator('urgency')
    @classmethod
    def validate_urgency(cls, v):
        """Validate urgency level"""
        if v.lower() not in ('low', 'medium', 'high', 'urgent'):
            raise ValueError('urgency must be low, medium, high, or urgent')
        return v.lower()

    @field_validator('adaptive_mode')
    @classmethod
    def validate_adaptive_mode(cls, v):
        """Validate adaptive mode"""
        if v.lower() not in ('passive', 'neutral', 'aggressive', 'urgent'):
            raise ValueError('adaptive_mode must be passive, neutral, aggressive, or urgent')
        return v.lower()


class ExecutionProgress(BaseModel):
    """
    Execution progress tracking model

    Contains real-time progress information for an algorithmic order.
    """
    order_id: str = Field(description="Unique order identifier")
    algorithm: str = Field(description="Algorithm type: TWAP or VWAP")
    state: str = Field(description="Current execution state")

    # Progress
    total_quantity: str = Field(description="Total quantity to execute")
    filled_quantity: str = Field(description="Quantity filled so far")
    remaining_quantity: str = Field(description="Remaining quantity")
    fill_rate: float = Field(description="Fill rate (0-1)")
    progress_pct: float = Field(description="Progress percentage")

    # Chunks
    current_chunk: int = Field(description="Current chunk being executed")
    total_chunks: int = Field(description="Total number of chunks")
    chunks_completed: int = Field(description="Chunks successfully completed")

    # Pricing
    average_price: Optional[str] = Field(description="Volume-weighted average fill price")
    arrival_price: Optional[str] = Field(description="Price at order submission")
    benchmark_price: Optional[str] = Field(description="TWAP/VWAP benchmark price")

    # Slippage
    slippage_pct: float = Field(description="Slippage vs benchmark")
    slippage_usd: float = Field(description="Dollar cost of slippage")

    # Timing
    duration_minutes: int = Field(description="Planned duration")
    elapsed_minutes: float = Field(description="Elapsed time")
    estimated_completion: Optional[str] = Field(description="Estimated completion time")


class ExecutionQualityReport(BaseModel):
    """
    Comprehensive execution quality report model

    Provides detailed analysis of execution performance.
    """
    order_id: str
    algorithm: str
    symbol: str
    side: str

    # Summary
    total_quantity: str
    filled_quantity: str
    fill_rate: float
    quality_score: float = Field(description="Quality score 0-100")
    rating: str = Field(description="excellent/good/fair/poor")

    # Pricing
    arrival_price: Optional[str]
    average_price: Optional[str]
    benchmark_price: Optional[str]

    # Slippage analysis
    slippage_vs_arrival_pct: float
    slippage_vs_arrival_usd: float
    slippage_vs_benchmark_pct: float
    slippage_vs_benchmark_usd: float

    # Chunk analysis
    chunks_total: int
    chunks_successful: int
    chunks_failed: int
    avg_chunk_slippage: float
    max_chunk_slippage: float

    # Timing
    duration_planned_seconds: float
    duration_actual_seconds: float

    # Recommendations
    recommendations: List[str]


# ============================================================================
# API ENDPOINTS
# ============================================================================


@router.post("/twap", summary="Execute TWAP Order")
async def execute_twap_order(
    request: TWAPOrderRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Execute TWAP (Time-Weighted Average Price) order

    TWAP splits a large order into equal-sized chunks executed at regular
    time intervals. This minimizes timing risk and is simple to implement.

    **Features:**
    - Equal chunk sizing with optional randomization
    - Regular time intervals with optional variance (+/-20%)
    - Participation rate control (default 15% of market volume)
    - Pause/resume/cancel capabilities
    - Slippage monitoring and auto-pause
    - Adaptive timing based on fill rates

    **Best For:**
    - Low urgency orders
    - Stable market conditions
    - Simple benchmark tracking

    **Example:**
    ```json
    {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "size": "1.5",
        "duration_minutes": 10,
        "randomize_timing": true,
        "participation_rate": 0.15
    }
    ```

    Args:
        request: TWAP order configuration

    Returns:
        Order ID and execution details
    """
    try:
        # Parse quantity
        quantity = Decimal(request.size)
        arrival_price = Decimal(request.arrival_price) if request.arrival_price else None

        # Get scheduler
        scheduler = get_execution_scheduler()

        # Calculate chunks if not specified
        num_chunks = request.num_chunks
        if num_chunks is None:
            # Default: ~1 chunk per minute
            num_chunks = max(3, min(60, request.duration_minutes))

        # Submit TWAP order
        order_id = await scheduler.submit_twap_order(
            symbol=request.symbol,
            side=request.side,
            quantity=quantity,
            duration_minutes=request.duration_minutes,
            num_chunks=num_chunks,
            arrival_price=arrival_price,
            participation_rate=request.participation_rate,
            randomize_timing=request.randomize_timing,
            urgency=request.urgency
        )

        # Calculate interval for response
        interval_seconds = (request.duration_minutes * 60) // num_chunks

        logger.info(
            f"TWAP order submitted: {order_id} - "
            f"{request.symbol} {request.side} {request.size}, "
            f"{num_chunks} chunks over {request.duration_minutes}min"
        )

        return {
            "success": True,
            "order_id": order_id,
            "algorithm": "TWAP",
            "symbol": request.symbol,
            "side": request.side,
            "total_size": str(quantity),
            "execution_plan": {
                "duration_minutes": request.duration_minutes,
                "num_chunks": num_chunks,
                "interval_seconds": interval_seconds,
                "chunk_size": str(quantity / num_chunks),
                "participation_rate": f"{request.participation_rate:.1%}",
                "randomize_timing": request.randomize_timing,
                "randomize_size": request.randomize_size,
                "use_limit_orders": request.use_limit_orders,
                "max_slippage_pct": request.max_slippage_pct,
                "pause_on_high_slippage": request.pause_on_high_slippage
            },
            "urgency": request.urgency,
            "arrival_price": request.arrival_price,
            "status": "queued",
            "message": f"TWAP order queued: {num_chunks} chunks over {request.duration_minutes} minutes",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except ValueError as e:
        logger.error(f"Invalid TWAP request: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {str(e)}")
    except Exception as e:
        logger.error(f"TWAP order submission failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Order submission failed: {str(e)}")


@router.post("/vwap", summary="Execute VWAP Order")
async def execute_vwap_order(
    request: VWAPOrderRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Execute VWAP (Volume-Weighted Average Price) order

    VWAP splits a large order based on historical volume patterns to match
    market rhythm and minimize impact. Larger chunks during high volume periods.

    **Features:**
    - Volume-weighted chunk sizing
    - Historical volume profile analysis
    - Real-time VWAP tracking and deviation alerts
    - Participation rate limiting (max 10% default)
    - Adaptive scheduling (passive, neutral, aggressive, urgent)
    - Catch-up adjustment for aggressive mode

    **Best For:**
    - Matching market rhythm
    - VWAP benchmark tracking
    - Large institutional orders

    **Volume Profile Example:**
    ```json
    {
        "volume_profile": [0.05, 0.08, 0.12, 0.15, 0.18, 0.15, 0.12, 0.08, 0.05, 0.02]
    }
    ```
    This represents expected volume distribution across 10 periods.

    **Example:**
    ```json
    {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "size": "2.0",
        "duration_minutes": 15,
        "adaptive_mode": "neutral",
        "participation_rate": 0.10
    }
    ```

    Args:
        request: VWAP order configuration

    Returns:
        Order ID and execution details
    """
    try:
        # Parse quantity
        quantity = Decimal(request.size)
        arrival_price = Decimal(request.arrival_price) if request.arrival_price else None
        target_vwap = Decimal(request.target_vwap) if request.target_vwap else None

        # Get scheduler
        scheduler = get_execution_scheduler()

        # Submit VWAP order
        order_id = await scheduler.submit_vwap_order(
            symbol=request.symbol,
            side=request.side,
            quantity=quantity,
            duration_minutes=request.duration_minutes,
            historical_volumes=request.volume_profile,
            arrival_price=arrival_price,
            target_vwap=target_vwap,
            participation_rate=request.participation_rate,
            urgency=request.urgency
        )

        # Calculate num chunks for response
        if request.volume_profile:
            num_chunks = len(request.volume_profile)
        else:
            num_chunks = max(3, min(60, request.duration_minutes))

        interval_seconds = (request.duration_minutes * 60) // num_chunks

        logger.info(
            f"VWAP order submitted: {order_id} - "
            f"{request.symbol} {request.side} {request.size}, "
            f"{num_chunks} chunks over {request.duration_minutes}min"
        )

        return {
            "success": True,
            "order_id": order_id,
            "algorithm": "VWAP",
            "symbol": request.symbol,
            "side": request.side,
            "total_size": str(quantity),
            "execution_plan": {
                "duration_minutes": request.duration_minutes,
                "num_chunks": num_chunks,
                "interval_seconds": interval_seconds,
                "volume_profile_provided": request.volume_profile is not None,
                "participation_rate": f"{request.participation_rate:.1%}",
                "adaptive_mode": request.adaptive_mode,
                "use_limit_orders": request.use_limit_orders,
                "max_slippage_pct": request.max_slippage_pct
            },
            "urgency": request.urgency,
            "arrival_price": request.arrival_price,
            "target_vwap": request.target_vwap,
            "status": "queued",
            "message": f"VWAP order queued: {num_chunks} volume-weighted chunks over {request.duration_minutes} minutes",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except ValueError as e:
        logger.error(f"Invalid VWAP request: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {str(e)}")
    except Exception as e:
        logger.error(f"VWAP order submission failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Order submission failed: {str(e)}")


@router.get("/twap/{order_id}", summary="Get TWAP Order Status")
async def get_twap_status(order_id: str) -> Dict[str, Any]:
    """
    Get status of a TWAP order

    Returns real-time progress and execution metrics for the specified
    TWAP order including:
    - Fill progress (quantity filled, remaining, percentage)
    - Chunk execution status
    - Average price and slippage
    - Timing information

    Args:
        order_id: TWAP order ID (format: twap_SYMBOL_xxxxxxxx)

    Returns:
        Detailed TWAP order status
    """
    try:
        scheduler = get_execution_scheduler()
        status = scheduler.get_order_status(order_id)

        if not status:
            raise HTTPException(status_code=404, detail=f"Order not found: {order_id}")

        if status.get("algorithm") != "twap":
            raise HTTPException(status_code=400, detail=f"Order {order_id} is not a TWAP order")

        # Calculate additional metrics
        elapsed_seconds = 0
        if status["timing"]["started_at"]:
            started = datetime.fromisoformat(status["timing"]["started_at"].replace('Z', '+00:00'))
            elapsed_seconds = (datetime.now(timezone.utc) - started).total_seconds()

        estimated_completion = None
        if status["state"] == "executing" and status["progress"]["fill_rate"] > 0:
            remaining_pct = 1 - status["progress"]["fill_rate"]
            elapsed_pct = status["progress"]["fill_rate"]
            if elapsed_pct > 0:
                total_est = elapsed_seconds / elapsed_pct
                remaining_est = total_est - elapsed_seconds
                estimated_completion = (
                    datetime.now(timezone.utc) +
                    __import__('datetime').timedelta(seconds=remaining_est)
                ).isoformat()

        return {
            "success": True,
            "data": {
                **status,
                "elapsed_seconds": round(elapsed_seconds, 0),
                "elapsed_minutes": round(elapsed_seconds / 60, 1),
                "estimated_completion": estimated_completion
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting TWAP status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vwap/{order_id}", summary="Get VWAP Order Status")
async def get_vwap_status(order_id: str) -> Dict[str, Any]:
    """
    Get status of a VWAP order

    Returns real-time progress and execution metrics for the specified
    VWAP order including:
    - Fill progress and VWAP tracking
    - Volume participation rates
    - Benchmark comparison (execution VWAP vs market VWAP)
    - Deviation alerts

    Args:
        order_id: VWAP order ID (format: vwap_SYMBOL_xxxxxxxx)

    Returns:
        Detailed VWAP order status with benchmark comparison
    """
    try:
        scheduler = get_execution_scheduler()
        status = scheduler.get_order_status(order_id)

        if not status:
            raise HTTPException(status_code=404, detail=f"Order not found: {order_id}")

        if status.get("algorithm") != "vwap":
            raise HTTPException(status_code=400, detail=f"Order {order_id} is not a VWAP order")

        # Calculate VWAP-specific metrics
        elapsed_seconds = 0
        if status["timing"]["started_at"]:
            started = datetime.fromisoformat(status["timing"]["started_at"].replace('Z', '+00:00'))
            elapsed_seconds = (datetime.now(timezone.utc) - started).total_seconds()

        # VWAP deviation alert
        vwap_alert = None
        benchmark_price = status["execution"].get("benchmark_price")
        avg_price = status["execution"].get("average_price")

        if benchmark_price and avg_price:
            try:
                benchmark = Decimal(benchmark_price)
                avg = Decimal(avg_price)
                if benchmark > 0:
                    deviation = float((avg - benchmark) / benchmark) * 100
                    if abs(deviation) > 0.1:
                        vwap_alert = {
                            "severity": "warning" if abs(deviation) < 0.2 else "high",
                            "deviation_pct": round(deviation, 4),
                            "message": f"Execution VWAP deviating {deviation:.3f}% from target"
                        }
            except Exception:
                pass

        return {
            "success": True,
            "data": {
                **status,
                "elapsed_seconds": round(elapsed_seconds, 0),
                "elapsed_minutes": round(elapsed_seconds / 60, 1),
                "vwap_tracking": {
                    "target_vwap": benchmark_price,
                    "execution_vwap": avg_price,
                    "deviation_alert": vwap_alert
                }
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting VWAP status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/active-algorithms", summary="List Active Algorithms")
async def get_active_algorithms() -> Dict[str, Any]:
    """
    Get list of all active algorithmic orders

    Returns all currently running TWAP and VWAP orders with their
    progress and status.

    **Includes:**
    - Queued orders waiting to start
    - Currently executing orders
    - Paused orders

    Returns:
        List of active algorithmic orders
    """
    try:
        scheduler = get_execution_scheduler()
        active_orders = scheduler.get_active_algorithms()
        scheduler_status = scheduler.get_scheduler_status()

        # Group by algorithm type
        twap_orders = [o for o in active_orders if o["algorithm"] == "twap"]
        vwap_orders = [o for o in active_orders if o["algorithm"] == "vwap"]

        return {
            "success": True,
            "data": {
                "summary": {
                    "total_active": len(active_orders),
                    "twap_orders": len(twap_orders),
                    "vwap_orders": len(vwap_orders),
                    "scheduler_state": scheduler_status["state"]
                },
                "orders": active_orders,
                "by_algorithm": {
                    "twap": twap_orders,
                    "vwap": vwap_orders
                }
            },
            "scheduler": {
                "state": scheduler_status["state"],
                "queue_size": scheduler_status["queue_size"],
                "max_concurrent": scheduler_status["config"]["max_concurrent_orders"]
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting active algorithms: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pause/{order_id}", summary="Pause Execution")
async def pause_execution(order_id: str) -> Dict[str, Any]:
    """
    Pause an active algorithmic order

    Pauses execution of the specified order. The order can be resumed later
    using the resume endpoint. Chunks that are currently executing will
    complete before the pause takes effect.

    **Use Cases:**
    - Market conditions change unexpectedly
    - High slippage detected
    - Manual intervention needed
    - Trading halt

    Args:
        order_id: Order to pause

    Returns:
        Pause confirmation and current status
    """
    try:
        scheduler = get_execution_scheduler()

        # Pause the order
        success = scheduler.pause_order(order_id)

        if not success:
            # Get status to provide better error message
            status = scheduler.get_order_status(order_id)
            if not status:
                raise HTTPException(status_code=404, detail=f"Order not found: {order_id}")
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot pause order in state: {status['state']}"
                )

        # Get updated status
        status = scheduler.get_order_status(order_id)

        logger.info(f"Order paused: {order_id}")

        return {
            "success": True,
            "order_id": order_id,
            "action": "paused",
            "status": status,
            "message": f"Order {order_id} paused. Use resume endpoint to continue.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume/{order_id}", summary="Resume Execution")
async def resume_execution(order_id: str) -> Dict[str, Any]:
    """
    Resume a paused algorithmic order

    Resumes execution of a previously paused order. Execution continues
    from where it was paused.

    Args:
        order_id: Order to resume

    Returns:
        Resume confirmation and current status
    """
    try:
        scheduler = get_execution_scheduler()

        # Resume the order
        success = scheduler.resume_order(order_id)

        if not success:
            # Get status to provide better error message
            status = scheduler.get_order_status(order_id)
            if not status:
                raise HTTPException(status_code=404, detail=f"Order not found: {order_id}")
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot resume order in state: {status['state']} (must be paused)"
                )

        # Get updated status
        status = scheduler.get_order_status(order_id)

        logger.info(f"Order resumed: {order_id}")

        return {
            "success": True,
            "order_id": order_id,
            "action": "resumed",
            "status": status,
            "message": f"Order {order_id} resumed. Execution continuing.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cancel/{order_id}", summary="Cancel Execution")
async def cancel_execution(order_id: str) -> Dict[str, Any]:
    """
    Cancel an algorithmic order

    Cancels execution of the specified order. If the order has partially
    filled, it will be marked as 'partial'. Cancelled orders cannot be
    resumed.

    **Note:** Any chunks currently executing will complete before cancellation.

    Args:
        order_id: Order to cancel

    Returns:
        Cancellation confirmation with final status
    """
    try:
        scheduler = get_execution_scheduler()

        # Get status before cancel
        status_before = scheduler.get_order_status(order_id)

        if not status_before:
            raise HTTPException(status_code=404, detail=f"Order not found: {order_id}")

        # Cancel the order
        success = await scheduler.cancel_order(order_id)

        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel order in state: {status_before['state']}"
            )

        # Get final status
        status_after = scheduler.get_order_status(order_id)

        logger.info(
            f"Order cancelled: {order_id} - "
            f"filled={status_after['progress']['filled_quantity']}"
        )

        return {
            "success": True,
            "order_id": order_id,
            "action": "cancelled",
            "final_status": status_after,
            "summary": {
                "filled_quantity": status_after["progress"]["filled_quantity"],
                "fill_rate": status_after["progress"]["fill_rate"],
                "chunks_completed": status_after["progress"]["current_chunk"],
                "state": status_after["state"]
            },
            "message": (
                f"Order {order_id} cancelled. "
                f"Filled {status_after['progress']['fill_rate']:.1%} before cancellation."
            ),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance-report", summary="Execution Performance Report")
async def get_performance_report(
    period_hours: int = Query(
        default=24,
        ge=1,
        le=168,
        description="Report period in hours (1-168)"
    ),
    order_id: Optional[str] = Query(
        default=None,
        description="Specific order ID for detailed report (optional)"
    )
) -> Dict[str, Any]:
    """
    Get execution quality and performance report

    Returns comprehensive analysis of execution performance including:
    - Fill rates and slippage metrics
    - Algorithm-specific performance (TWAP vs VWAP)
    - Cost savings analysis
    - Recommendations for improvement

    **For specific order:** Provide order_id to get detailed report for one order.

    **For aggregate report:** Omit order_id to get aggregate metrics.

    Args:
        period_hours: Hours to analyze (default: 24)
        order_id: Optional specific order for detailed report

    Returns:
        Execution quality report with metrics and recommendations
    """
    try:
        scheduler = get_execution_scheduler()

        if order_id:
            # Detailed report for specific order
            report = scheduler.get_execution_report(order_id)

            if not report:
                raise HTTPException(status_code=404, detail=f"Order not found: {order_id}")

            return {
                "success": True,
                "report_type": "single_order",
                "order_id": order_id,
                "data": {
                    "summary": {
                        "algorithm": report.algorithm_type,
                        "symbol": report.symbol,
                        "side": report.side,
                        "quality_score": round(report.quality_score, 1),
                        "rating": report.rating
                    },
                    "execution": {
                        "total_quantity": str(report.total_quantity),
                        "filled_quantity": str(report.filled_quantity),
                        "fill_rate": round(report.fill_rate, 4)
                    },
                    "pricing": {
                        "arrival_price": str(report.arrival_price) if report.arrival_price else None,
                        "average_price": str(report.average_price) if report.average_price else None,
                        "benchmark_price": str(report.benchmark_price) if report.benchmark_price else None
                    },
                    "slippage": {
                        "vs_arrival_pct": round(report.slippage_vs_arrival_pct, 4),
                        "vs_arrival_usd": round(report.slippage_vs_arrival_usd, 2),
                        "vs_benchmark_pct": round(report.slippage_vs_benchmark_pct, 4),
                        "vs_benchmark_usd": round(report.slippage_vs_benchmark_usd, 2)
                    },
                    "chunks": {
                        "total": report.chunks_total,
                        "successful": report.chunks_successful,
                        "failed": report.chunks_failed,
                        "avg_slippage": round(report.avg_chunk_slippage, 4),
                        "max_slippage": round(report.max_chunk_slippage, 4)
                    },
                    "timing": {
                        "duration_planned_seconds": report.duration_planned_seconds,
                        "duration_actual_seconds": round(report.duration_actual_seconds, 1),
                        "started_at": report.started_at.isoformat() if report.started_at else None,
                        "completed_at": report.completed_at.isoformat() if report.completed_at else None
                    },
                    "recommendations": report.recommendations
                },
                "generated_at": datetime.now(timezone.utc).isoformat()
            }

        else:
            # Aggregate performance report
            report = scheduler.get_performance_report(hours=period_hours)

            return {
                "success": True,
                "report_type": "aggregate",
                "period_hours": period_hours,
                "data": report,
                "generated_at": datetime.now(timezone.utc).isoformat()
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating performance report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SCHEDULER CONTROL ENDPOINTS
# ============================================================================


@router.post("/scheduler/start", summary="Start Execution Scheduler")
async def start_scheduler() -> Dict[str, Any]:
    """
    Start the execution scheduler

    Starts the background task processor that executes queued orders.
    Must be called before submitting orders.

    Returns:
        Scheduler status
    """
    try:
        scheduler = get_execution_scheduler()
        await scheduler.start()

        return {
            "success": True,
            "action": "started",
            "status": scheduler.get_scheduler_status(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error starting scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scheduler/stop", summary="Stop Execution Scheduler")
async def stop_scheduler(
    wait_for_completion: bool = Query(
        default=True,
        description="Wait for active orders to complete"
    )
) -> Dict[str, Any]:
    """
    Stop the execution scheduler

    Stops the background task processor. Active orders can either
    complete or be cancelled based on wait_for_completion flag.

    Args:
        wait_for_completion: If True, wait for active orders to finish

    Returns:
        Scheduler status
    """
    try:
        scheduler = get_execution_scheduler()
        await scheduler.stop(wait_for_completion=wait_for_completion)

        return {
            "success": True,
            "action": "stopped",
            "waited_for_completion": wait_for_completion,
            "status": scheduler.get_scheduler_status(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scheduler/status", summary="Get Scheduler Status")
async def get_scheduler_status() -> Dict[str, Any]:
    """
    Get execution scheduler status

    Returns current scheduler state, queue size, and configuration.

    Returns:
        Scheduler status and metrics
    """
    try:
        scheduler = get_execution_scheduler()
        status = scheduler.get_scheduler_status()

        return {
            "success": True,
            "data": status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ROUTER EXPORT
# ============================================================================

# Export router for inclusion in main app
twap_vwap_router = router
