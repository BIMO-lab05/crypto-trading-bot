"""
Order Book API Handlers for ML Prediction Service
Purpose: REST API endpoints for order book microstructure features
Author: Phase 6.2 ML Team
Date: 2025-12-11

Endpoints:
- GET /api/v1/orderbook/{symbol}/features - Current order book features
- GET /api/v1/orderbook/{symbol}/imbalance - Bid-ask imbalance metrics
- GET /api/v1/orderbook/{symbol}/liquidity - Liquidity metrics
- POST /api/v1/orderbook/{symbol}/snapshot - Store order book snapshot
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

import httpx
from fastapi import APIRouter, HTTPException, Query, Path as FastAPIPath, BackgroundTasks
from pydantic import BaseModel, Field

from app.features.orderbook_features import (
    OrderBookFeatureExtractor,
    OrderBookFeatures,
    OrderBookCache,
)
from app.config import get_settings

# Configure logger
logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter(
    prefix="/api/v1/orderbook",
    tags=["Order Book Features"]
)

# Global instances (initialized on startup)
_feature_extractor: Optional[OrderBookFeatureExtractor] = None
_orderbook_cache: Optional[OrderBookCache] = None
_http_client: Optional[httpx.AsyncClient] = None


# ==============================================================================
# PYDANTIC MODELS FOR API
# ==============================================================================

class OrderBookFeaturesResponse(BaseModel):
    """Response model for order book features endpoint"""
    symbol: str = Field(..., description="Trading pair symbol")
    timestamp: datetime = Field(..., description="Feature calculation timestamp")

    # Core features
    bid_ask_spread_pct: float = Field(..., description="Bid-ask spread as percentage")
    bid_ask_imbalance: float = Field(..., description="Volume imbalance [-1, 1]")
    order_flow_imbalance: float = Field(..., description="Order flow ratio [-1, 1]")
    depth_imbalance_5: float = Field(..., description="Depth imbalance at 5 levels")
    depth_imbalance_10: float = Field(..., description="Depth imbalance at 10 levels")
    liquidity_score: float = Field(..., description="Volume within 0.1% of mid")
    volume_weighted_mid: float = Field(..., description="Volume-weighted mid price")
    order_pressure: float = Field(..., description="Order book change rate [-1, 1]")

    # Additional context
    best_bid: float = Field(..., description="Best bid price")
    best_ask: float = Field(..., description="Best ask price")
    mid_price: float = Field(..., description="Simple mid price")
    total_bid_volume: float = Field(..., description="Total bid volume analyzed")
    total_ask_volume: float = Field(..., description="Total ask volume analyzed")

    # Metadata
    calculation_time_ms: float = Field(..., description="Time to calculate features")
    levels_analyzed: int = Field(..., description="Number of order book levels used")
    data_source: str = Field(default="bybit", description="Exchange source")

    class Config:
        """Pydantic config"""
        json_schema_extra = {
            "example": {
                "symbol": "BTCUSDT",
                "timestamp": "2025-12-11T10:00:00Z",
                "bid_ask_spread_pct": 0.01,
                "bid_ask_imbalance": 0.15,
                "order_flow_imbalance": 0.08,
                "depth_imbalance_5": 0.12,
                "depth_imbalance_10": 0.10,
                "liquidity_score": 125.5,
                "volume_weighted_mid": 100000.50,
                "order_pressure": 0.05,
                "best_bid": 100000.0,
                "best_ask": 100001.0,
                "mid_price": 100000.5,
                "total_bid_volume": 45.2,
                "total_ask_volume": 38.7,
                "calculation_time_ms": 1.25,
                "levels_analyzed": 25,
                "data_source": "bybit"
            }
        }


class ImbalanceResponse(BaseModel):
    """Response model for imbalance endpoint"""
    symbol: str
    timestamp: datetime
    bid_ask_imbalance: float = Field(..., description="Volume imbalance at top 10 levels")
    depth_imbalance_5: float = Field(..., description="Weighted imbalance at 5 levels")
    depth_imbalance_10: float = Field(..., description="Weighted imbalance at 10 levels")
    depth_imbalance_20: float = Field(..., description="Weighted imbalance at 20 levels")
    order_flow_imbalance: float = Field(..., description="Rolling 5-min order flow")
    bid_volume: float
    ask_volume: float
    interpretation: str = Field(..., description="Human-readable interpretation")

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "BTCUSDT",
                "timestamp": "2025-12-11T10:00:00Z",
                "bid_ask_imbalance": 0.25,
                "depth_imbalance_5": 0.30,
                "depth_imbalance_10": 0.22,
                "depth_imbalance_20": 0.18,
                "order_flow_imbalance": 0.15,
                "bid_volume": 55.0,
                "ask_volume": 35.0,
                "interpretation": "Bullish: Strong buying pressure detected"
            }
        }


class LiquidityResponse(BaseModel):
    """Response model for liquidity endpoint"""
    symbol: str
    timestamp: datetime
    liquidity_score: float = Field(..., description="Volume within 0.1% of mid")
    bid_ask_spread_pct: float = Field(..., description="Current spread percentage")
    spread_bps: float = Field(..., description="Spread in basis points")
    total_bid_depth: float = Field(..., description="Total bid volume")
    total_ask_depth: float = Field(..., description="Total ask volume")
    depth_ratio: float = Field(..., description="Bid depth / Ask depth ratio")
    liquidity_level: str = Field(..., description="HIGH, MEDIUM, or LOW")
    slippage_estimate_1btc: float = Field(
        ...,
        description="Estimated slippage for 1 BTC order"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "BTCUSDT",
                "timestamp": "2025-12-11T10:00:00Z",
                "liquidity_score": 125.5,
                "bid_ask_spread_pct": 0.01,
                "spread_bps": 1.0,
                "total_bid_depth": 450.2,
                "total_ask_depth": 387.1,
                "depth_ratio": 1.16,
                "liquidity_level": "HIGH",
                "slippage_estimate_1btc": 0.0012
            }
        }


class OrderBookSnapshotRequest(BaseModel):
    """Request model for storing order book snapshot"""
    bids: List[List[float]] = Field(..., description="Bid levels [[price, size], ...]")
    asks: List[List[float]] = Field(..., description="Ask levels [[price, size], ...]")
    timestamp: Optional[datetime] = Field(None, description="Optional snapshot timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "bids": [[100000.0, 1.5], [99999.5, 2.0]],
                "asks": [[100001.0, 1.2], [100001.5, 1.8]],
                "timestamp": "2025-12-11T10:00:00Z"
            }
        }


class MLFeatureArrayResponse(BaseModel):
    """Response model for ML-ready feature array"""
    symbol: str
    timestamp: datetime
    feature_names: List[str] = Field(..., description="Ordered feature names")
    feature_values: List[float] = Field(..., description="Feature values in order")
    normalized_values: Dict[str, float] = Field(
        ...,
        description="Z-score normalized features"
    )


# ==============================================================================
# INITIALIZATION FUNCTIONS
# ==============================================================================

async def initialize_orderbook_handler():
    """
    Initialize order book handler dependencies

    Called during application startup to create:
    - Feature extractor instance
    - Redis cache connection
    - HTTP client for Bybit API calls
    """
    global _feature_extractor, _orderbook_cache, _http_client

    settings = get_settings()

    # Initialize cache
    _orderbook_cache = OrderBookCache(
        host=settings.redis_host,
        port=settings.redis_port,
        db=3,  # Separate DB for order book data
        ttl_seconds=300,  # 5 minute retention
        enabled=settings.redis_enabled
    )
    await _orderbook_cache.connect()

    # Initialize feature extractor with cache
    _feature_extractor = OrderBookFeatureExtractor(cache=_orderbook_cache)

    # Initialize HTTP client for Bybit API
    _http_client = httpx.AsyncClient(timeout=10.0)

    logger.info("Order book handler initialized successfully")


async def shutdown_orderbook_handler():
    """Clean up order book handler resources"""
    global _orderbook_cache, _http_client

    if _orderbook_cache:
        await _orderbook_cache.disconnect()

    if _http_client:
        await _http_client.aclose()

    logger.info("Order book handler shutdown complete")


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

async def fetch_orderbook_from_bybit(symbol: str, limit: int = 25) -> Dict[str, Any]:
    """
    Fetch order book from Bybit API

    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        limit: Number of levels to fetch (max 500)

    Returns:
        Order book dict with 'bids' and 'asks'
    """
    global _http_client

    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=10.0)

    # Bybit V5 API endpoint for linear perpetual order book
    url = "https://api.bybit.com/v5/market/orderbook"
    params = {
        "category": "linear",
        "symbol": symbol.upper(),
        "limit": min(limit, 500)
    }

    try:
        response = await _http_client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if data.get("retCode") != 0:
            raise HTTPException(
                status_code=502,
                detail=f"Bybit API error: {data.get('retMsg', 'Unknown error')}"
            )

        result = data.get("result", {})

        # Convert to standard format: [[price, size], ...]
        bids = [
            [float(b[0]), float(b[1])]
            for b in result.get("b", [])
        ]
        asks = [
            [float(a[0]), float(a[1])]
            for a in result.get("a", [])
        ]

        return {
            "bids": bids,
            "asks": asks,
            "timestamp": result.get("ts", int(datetime.utcnow().timestamp() * 1000))
        }

    except httpx.HTTPError as e:
        logger.error(f"Error fetching order book from Bybit: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to fetch order book: {str(e)}"
        )


def interpret_imbalance(imbalance: float) -> str:
    """Generate human-readable interpretation of imbalance"""
    if imbalance > 0.3:
        return "Bullish: Strong buying pressure detected"
    elif imbalance > 0.1:
        return "Slightly Bullish: Moderate buying interest"
    elif imbalance < -0.3:
        return "Bearish: Strong selling pressure detected"
    elif imbalance < -0.1:
        return "Slightly Bearish: Moderate selling interest"
    else:
        return "Neutral: Balanced order book"


def determine_liquidity_level(
    spread_pct: float,
    liquidity_score: float
) -> str:
    """Determine liquidity level based on spread and score"""
    if spread_pct < 0.02 and liquidity_score > 100:
        return "HIGH"
    elif spread_pct < 0.05 and liquidity_score > 50:
        return "MEDIUM"
    else:
        return "LOW"


def estimate_slippage(
    orderbook: Dict[str, Any],
    order_size: float,
    side: str = "buy"
) -> float:
    """
    Estimate slippage for a given order size

    Args:
        orderbook: Order book data
        order_size: Size of order (e.g., 1.0 BTC)
        side: 'buy' or 'sell'

    Returns:
        Estimated slippage as percentage
    """
    levels = orderbook.get("asks" if side == "buy" else "bids", [])

    if not levels:
        return 0.0

    # Calculate volume-weighted average price
    remaining = order_size
    total_cost = 0.0
    base_price = levels[0][0]

    for price, size in levels:
        fill_size = min(remaining, size)
        total_cost += fill_size * price
        remaining -= fill_size
        if remaining <= 0:
            break

    if order_size > remaining:
        avg_price = total_cost / (order_size - remaining)
        slippage = abs(avg_price - base_price) / base_price * 100
        return slippage

    return 0.0


# ==============================================================================
# API ENDPOINTS
# ==============================================================================

@router.get(
    "/{symbol}/features",
    response_model=OrderBookFeaturesResponse,
    summary="Get Order Book Features",
    description="""
    Extract all order book microstructure features for a symbol.

    **Features extracted:**
    - Bid-Ask Spread (%)
    - Bid-Ask Imbalance
    - Order Flow Imbalance (5-min rolling)
    - Depth Imbalance (5 and 10 levels)
    - Liquidity Score
    - Volume-Weighted Mid Price
    - Order Pressure

    **Performance:** Targets <10ms calculation time

    **Usage for ML:**
    These features can be added to your GRU/LSTM model input to capture
    market microstructure signals that improve prediction accuracy.
    """
)
async def get_orderbook_features(
    symbol: str = FastAPIPath(..., description="Trading pair (e.g., BTCUSDT)"),
    levels: int = Query(25, ge=5, le=100, description="Order book depth levels"),
    use_cache: bool = Query(True, description="Use cached order book if available")
):
    """Get comprehensive order book features for ML models"""
    global _feature_extractor, _orderbook_cache

    # Initialize if needed
    if _feature_extractor is None:
        await initialize_orderbook_handler()

    try:
        # Try to get cached order book first
        orderbook = None
        if use_cache and _orderbook_cache:
            orderbook = await _orderbook_cache.get_latest(symbol.upper())

        # Fetch fresh data if no cache or cache disabled
        if orderbook is None:
            orderbook = await fetch_orderbook_from_bybit(symbol, levels)

            # Store in cache for future use
            if _orderbook_cache:
                await _orderbook_cache.store_snapshot(symbol.upper(), orderbook)

        # Extract features
        features = _feature_extractor.extract_all_features(
            orderbook,
            symbol=symbol.upper()
        )

        # Convert to response model
        return OrderBookFeaturesResponse(
            symbol=features.symbol,
            timestamp=features.timestamp,
            bid_ask_spread_pct=features.bid_ask_spread_pct,
            bid_ask_imbalance=features.bid_ask_imbalance,
            order_flow_imbalance=features.order_flow_imbalance,
            depth_imbalance_5=features.depth_imbalance_5,
            depth_imbalance_10=features.depth_imbalance_10,
            liquidity_score=features.liquidity_score,
            volume_weighted_mid=features.volume_weighted_mid,
            order_pressure=features.order_pressure,
            best_bid=features.best_bid,
            best_ask=features.best_ask,
            mid_price=features.mid_price,
            total_bid_volume=features.total_bid_volume,
            total_ask_volume=features.total_ask_volume,
            calculation_time_ms=features.calculation_time_ms,
            levels_analyzed=features.levels_analyzed,
            data_source=features.data_source
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting order book features: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Feature extraction failed: {str(e)}"
        )


@router.get(
    "/{symbol}/imbalance",
    response_model=ImbalanceResponse,
    summary="Get Bid-Ask Imbalance",
    description="""
    Get detailed order book imbalance metrics.

    **Imbalance indicates buying/selling pressure:**
    - Positive (>0): More buying pressure (bullish)
    - Negative (<0): More selling pressure (bearish)
    - Near 0: Balanced market

    **Multiple depth levels:**
    - 5 levels: Short-term/scalping signal
    - 10 levels: Medium-term signal
    - 20 levels: Longer-term pressure indication
    """
)
async def get_imbalance(
    symbol: str = FastAPIPath(..., description="Trading pair"),
    levels: int = Query(25, ge=5, le=100, description="Order book depth")
):
    """Get order book imbalance metrics"""
    global _feature_extractor

    if _feature_extractor is None:
        await initialize_orderbook_handler()

    try:
        # Fetch order book
        orderbook = await fetch_orderbook_from_bybit(symbol, levels)

        # Calculate imbalances at different depths
        imb_10, bid_vol, ask_vol = _feature_extractor.calculate_bid_ask_imbalance(
            orderbook, levels=10
        )
        depth_5 = _feature_extractor.calculate_depth_imbalance(orderbook, levels=5)
        depth_10 = _feature_extractor.calculate_depth_imbalance(orderbook, levels=10)
        depth_20 = _feature_extractor.calculate_depth_imbalance(orderbook, levels=20)

        # Calculate order flow imbalance
        flow_imb = _feature_extractor.calculate_order_flow_imbalance(
            symbol.upper(),
            orderbook
        )

        # Generate interpretation
        interpretation = interpret_imbalance(imb_10)

        return ImbalanceResponse(
            symbol=symbol.upper(),
            timestamp=datetime.utcnow(),
            bid_ask_imbalance=imb_10,
            depth_imbalance_5=depth_5,
            depth_imbalance_10=depth_10,
            depth_imbalance_20=depth_20,
            order_flow_imbalance=flow_imb,
            bid_volume=bid_vol,
            ask_volume=ask_vol,
            interpretation=interpretation
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating imbalance: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Imbalance calculation failed: {str(e)}"
        )


@router.get(
    "/{symbol}/liquidity",
    response_model=LiquidityResponse,
    summary="Get Liquidity Metrics",
    description="""
    Get market liquidity analysis for a symbol.

    **Metrics provided:**
    - Liquidity Score: Volume within 0.1% of mid price
    - Spread: Cost of crossing the bid-ask
    - Depth: Total volume on each side
    - Slippage Estimate: Expected price impact

    **Liquidity Levels:**
    - HIGH: Tight spread (<0.02%), high depth
    - MEDIUM: Moderate spread, adequate depth
    - LOW: Wide spread or thin depth
    """
)
async def get_liquidity(
    symbol: str = FastAPIPath(..., description="Trading pair"),
    order_size: float = Query(1.0, ge=0.01, le=100, description="Size for slippage estimate")
):
    """Get liquidity metrics for a symbol"""
    global _feature_extractor

    if _feature_extractor is None:
        await initialize_orderbook_handler()

    try:
        # Fetch order book
        orderbook = await fetch_orderbook_from_bybit(symbol, 50)

        # Calculate spread
        spread_pct, best_bid, best_ask, mid_price = _feature_extractor.calculate_bid_ask_spread(
            orderbook
        )

        # Calculate liquidity score
        liquidity_score = _feature_extractor.calculate_liquidity_score(
            orderbook, mid_price
        )

        # Calculate total depths
        total_bid = sum(level[1] for level in orderbook.get("bids", []))
        total_ask = sum(level[1] for level in orderbook.get("asks", []))

        # Calculate depth ratio
        depth_ratio = total_bid / total_ask if total_ask > 0 else 0.0

        # Determine liquidity level
        liquidity_level = determine_liquidity_level(spread_pct, liquidity_score)

        # Estimate slippage
        slippage = estimate_slippage(orderbook, order_size, "buy")

        return LiquidityResponse(
            symbol=symbol.upper(),
            timestamp=datetime.utcnow(),
            liquidity_score=liquidity_score,
            bid_ask_spread_pct=spread_pct,
            spread_bps=spread_pct * 100,  # Convert to basis points
            total_bid_depth=total_bid,
            total_ask_depth=total_ask,
            depth_ratio=depth_ratio,
            liquidity_level=liquidity_level,
            slippage_estimate_1btc=slippage
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating liquidity: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Liquidity calculation failed: {str(e)}"
        )


@router.post(
    "/{symbol}/snapshot",
    summary="Store Order Book Snapshot",
    description="""
    Store an order book snapshot for historical analysis.

    Used by WebSocket handlers to store real-time order book updates
    for calculating order flow imbalance and order pressure.

    **Note:** Snapshots are automatically expired after 5 minutes.
    """
)
async def store_snapshot(
    symbol: str = FastAPIPath(..., description="Trading pair"),
    snapshot: OrderBookSnapshotRequest = ...,
    background_tasks: BackgroundTasks = None
):
    """Store order book snapshot for historical tracking"""
    global _orderbook_cache

    if _orderbook_cache is None:
        await initialize_orderbook_handler()

    try:
        orderbook = {
            "bids": snapshot.bids,
            "asks": snapshot.asks
        }

        # Store in cache
        success = await _orderbook_cache.store_snapshot(
            symbol.upper(),
            orderbook,
            snapshot.timestamp
        )

        return {
            "success": success,
            "symbol": symbol.upper(),
            "timestamp": snapshot.timestamp or datetime.utcnow(),
            "message": "Snapshot stored successfully" if success else "Storage failed"
        }

    except Exception as e:
        logger.error(f"Error storing snapshot: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Snapshot storage failed: {str(e)}"
        )


@router.get(
    "/{symbol}/ml-features",
    response_model=MLFeatureArrayResponse,
    summary="Get ML-Ready Feature Array",
    description="""
    Get order book features formatted for ML model input.

    **Returns:**
    - 8 core features in consistent order
    - Z-score normalized values for ML pipeline
    - Feature names for documentation

    **Features (in order):**
    1. bid_ask_spread_pct
    2. bid_ask_imbalance
    3. order_flow_imbalance
    4. depth_imbalance_5
    5. depth_imbalance_10
    6. liquidity_score
    7. volume_weighted_mid
    8. order_pressure
    """
)
async def get_ml_features(
    symbol: str = FastAPIPath(..., description="Trading pair")
):
    """Get features formatted for ML model input"""
    global _feature_extractor

    if _feature_extractor is None:
        await initialize_orderbook_handler()

    try:
        # Fetch order book
        orderbook = await fetch_orderbook_from_bybit(symbol, 25)

        # Extract all features
        features = _feature_extractor.extract_all_features(
            orderbook,
            symbol=symbol.upper()
        )

        # Get normalized values
        normalized = _feature_extractor.normalize_features(features)

        return MLFeatureArrayResponse(
            symbol=symbol.upper(),
            timestamp=features.timestamp,
            feature_names=OrderBookFeatures.get_feature_names(),
            feature_values=features.to_ml_array(),
            normalized_values=normalized
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ML features: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"ML feature extraction failed: {str(e)}"
        )


# ==============================================================================
# CACHE MANAGEMENT ENDPOINTS
# ==============================================================================

@router.get(
    "/cache/stats",
    summary="Get Order Book Cache Statistics",
    tags=["Cache Management"]
)
async def get_cache_stats():
    """Get order book cache statistics"""
    global _orderbook_cache

    if _orderbook_cache is None:
        return {
            "enabled": False,
            "message": "Order book cache not initialized"
        }

    if not _orderbook_cache.is_connected:
        return {
            "enabled": True,
            "connected": False,
            "message": "Using in-memory fallback"
        }

    return {
        "enabled": True,
        "connected": True,
        "host": _orderbook_cache.host,
        "port": _orderbook_cache.port,
        "db": _orderbook_cache.db,
        "ttl_seconds": _orderbook_cache.ttl_seconds
    }
