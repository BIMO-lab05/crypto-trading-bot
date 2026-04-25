"""
Order Book Microstructure Feature Extractor
Purpose: Extract market microstructure features from order book data for ML predictions
Author: Phase 6.2 ML Team
Date: 2025-12-11

This module provides comprehensive order book analysis for ML models:
- Bid-Ask Spread: Measures market liquidity and trading costs
- Bid-Ask Imbalance: Predicts short-term price direction
- Order Flow Imbalance: Tracks aggressive buying vs selling
- Depth Imbalance: Analyzes volume distribution at different price levels
- Liquidity Score: Measures market depth around mid price
- Volume-Weighted Mid: More accurate mid price estimate
- Order Pressure: Rate of order book changes over time

Performance Target: <10ms per feature calculation
"""

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from collections import deque

import numpy as np
import redis.asyncio as redis

# Configure module logger
logger = logging.getLogger(__name__)


# ==============================================================================
# DATA CLASSES
# ==============================================================================

@dataclass
class OrderBookLevel:
    """
    Single price level in the order book

    Attributes:
        price: Price at this level
        size: Total volume at this price
        side: 'bid' or 'ask'
    """
    price: float  # Price at this level
    size: float  # Total volume at this level
    side: str = ""  # 'bid' or 'ask'

    def __post_init__(self):
        """Validate side after initialization"""
        if self.side and self.side not in ('bid', 'ask', ''):
            raise ValueError(f"Invalid side: {self.side}. Must be 'bid' or 'ask'")


@dataclass
class OrderBookFeatures:
    """
    Extracted order book microstructure features for ML models

    Contains 8 primary features + metadata for ML pipeline integration

    Attributes:
        timestamp: When features were extracted
        symbol: Trading pair (e.g., BTCUSDT)
        bid_ask_spread_pct: Spread as percentage of mid price
        bid_ask_imbalance: Volume imbalance between bid and ask sides
        order_flow_imbalance: Ratio of buy vs sell orders (rolling window)
        depth_imbalance_5: Volume imbalance at top 5 price levels
        depth_imbalance_10: Volume imbalance at top 10 price levels
        liquidity_score: Total volume within 0.1% of mid price
        volume_weighted_mid: Volume-adjusted mid price
        order_pressure: Rate of order book changes (normalized)
    """
    timestamp: datetime  # When features were extracted
    symbol: str  # Trading pair symbol

    # Core microstructure features
    bid_ask_spread_pct: float = 0.0  # (best_ask - best_bid) / mid_price * 100
    bid_ask_imbalance: float = 0.0  # (bid_vol - ask_vol) / (bid_vol + ask_vol)
    order_flow_imbalance: float = 0.0  # Buy vs sell orders ratio (5 min rolling)
    depth_imbalance_5: float = 0.0  # Volume diff at top 5 levels
    depth_imbalance_10: float = 0.0  # Volume diff at top 10 levels
    liquidity_score: float = 0.0  # Volume within 0.1% of mid
    volume_weighted_mid: float = 0.0  # Better mid price estimate
    order_pressure: float = 0.0  # Rate of order book changes

    # Additional features for ML context
    best_bid: float = 0.0  # Best bid price
    best_ask: float = 0.0  # Best ask price
    mid_price: float = 0.0  # Simple mid price
    total_bid_volume: float = 0.0  # Total volume on bid side
    total_ask_volume: float = 0.0  # Total volume on ask side
    bid_depth_levels: int = 0  # Number of bid levels
    ask_depth_levels: int = 0  # Number of ask levels

    # Metadata
    calculation_time_ms: float = 0.0  # Time to calculate features
    data_source: str = "bybit"  # Exchange source
    levels_analyzed: int = 25  # Number of levels in source data

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = asdict(self)
        # Convert datetime to ISO format string
        result['timestamp'] = self.timestamp.isoformat()
        return result

    def to_ml_array(self) -> List[float]:
        """
        Convert to array of 8 core features for ML model input

        Returns:
            List of 8 floats in consistent order for ML pipeline
        """
        return [
            self.bid_ask_spread_pct,
            self.bid_ask_imbalance,
            self.order_flow_imbalance,
            self.depth_imbalance_5,
            self.depth_imbalance_10,
            self.liquidity_score,
            self.volume_weighted_mid,
            self.order_pressure,
        ]

    @staticmethod
    def get_feature_names() -> List[str]:
        """Get ordered list of ML feature names"""
        return [
            "bid_ask_spread_pct",
            "bid_ask_imbalance",
            "order_flow_imbalance",
            "depth_imbalance_5",
            "depth_imbalance_10",
            "liquidity_score",
            "volume_weighted_mid",
            "order_pressure",
        ]


# ==============================================================================
# ORDER BOOK CACHE (Redis-based)
# ==============================================================================

class OrderBookCache:
    """
    Redis-based cache for order book snapshots

    Stores order book data with 1-second granularity for:
    - Real-time feature calculation
    - Order flow imbalance (requires 5-minute rolling window)
    - Order pressure calculation (requires historical snapshots)

    Performance:
    - Uses Redis sorted sets for time-based queries
    - Automatic expiration of old snapshots (5 minute retention)
    - Async operations for non-blocking I/O
    """

    # Default time-to-live for order book snapshots (5 minutes)
    DEFAULT_TTL_SECONDS = 300

    # Key prefix for Redis storage
    KEY_PREFIX = "orderbook:"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 3,  # Different DB from predictions cache
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        enabled: bool = True
    ):
        """
        Initialize order book cache

        Args:
            host: Redis host address
            port: Redis port number
            db: Redis database number (default 3 for order book data)
            ttl_seconds: Time-to-live for snapshots (default 5 minutes)
            enabled: Whether caching is enabled
        """
        self.host = host
        self.port = port
        self.db = db
        self.ttl_seconds = ttl_seconds
        self.enabled = enabled
        self.redis_client: Optional[redis.Redis] = None
        self._is_connected = False

        # In-memory fallback when Redis unavailable
        self._memory_cache: Dict[str, deque] = {}
        self._memory_max_size = 300  # 5 minutes at 1-second granularity

        logger.info(
            f"OrderBookCache initialized: host={host}:{port}/{db}, "
            f"ttl={ttl_seconds}s, enabled={enabled}"
        )

    async def connect(self) -> bool:
        """
        Connect to Redis server

        Returns:
            True if connected successfully, False otherwise
        """
        if not self.enabled:
            logger.info("OrderBookCache disabled, using in-memory fallback")
            return True

        try:
            # Create Redis connection with timeout
            self.redis_client = await redis.from_url(
                f"redis://{self.host}:{self.port}/{self.db}",
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0
            )

            # Test connection with ping
            await self.redis_client.ping()
            self._is_connected = True
            logger.info(f"OrderBookCache connected to Redis at {self.host}:{self.port}/{self.db}")
            return True

        except Exception as e:
            logger.warning(
                f"OrderBookCache Redis connection failed: {e}. "
                "Using in-memory fallback."
            )
            self._is_connected = False
            self.redis_client = None
            return True  # Still return True since fallback is available

    async def disconnect(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("OrderBookCache disconnected from Redis")
        self._is_connected = False

    def _make_key(self, symbol: str) -> str:
        """Generate Redis key for symbol's order book snapshots"""
        return f"{self.KEY_PREFIX}{symbol.upper()}"

    async def store_snapshot(
        self,
        symbol: str,
        orderbook: Dict[str, Any],
        timestamp: Optional[datetime] = None
    ) -> bool:
        """
        Store order book snapshot

        Args:
            symbol: Trading pair symbol
            orderbook: Order book data with 'bids' and 'asks' arrays
            timestamp: Snapshot timestamp (default: current time)

        Returns:
            True if stored successfully
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        # Prepare snapshot data
        snapshot_data = {
            "timestamp": timestamp.isoformat(),
            "bids": orderbook.get("bids", []),
            "asks": orderbook.get("asks", []),
        }

        # Use Redis if connected
        if self._is_connected and self.redis_client:
            try:
                key = self._make_key(symbol)
                score = timestamp.timestamp()  # Unix timestamp for sorting

                # Store in sorted set with timestamp as score
                await self.redis_client.zadd(
                    key,
                    {json.dumps(snapshot_data): score}
                )

                # Remove old entries (older than TTL)
                cutoff = (timestamp - timedelta(seconds=self.ttl_seconds)).timestamp()
                await self.redis_client.zremrangebyscore(key, "-inf", cutoff)

                logger.debug(f"Stored orderbook snapshot for {symbol} at {timestamp}")
                return True

            except Exception as e:
                logger.error(f"Error storing orderbook snapshot: {e}")
                # Fall through to memory cache

        # Fallback to in-memory cache
        if symbol not in self._memory_cache:
            self._memory_cache[symbol] = deque(maxlen=self._memory_max_size)

        self._memory_cache[symbol].append(snapshot_data)
        logger.debug(f"Stored orderbook snapshot in memory for {symbol}")
        return True

    async def get_snapshots(
        self,
        symbol: str,
        seconds_back: int = 300
    ) -> List[Dict[str, Any]]:
        """
        Get order book snapshots for the specified time window

        Args:
            symbol: Trading pair symbol
            seconds_back: How many seconds of history to retrieve

        Returns:
            List of order book snapshots, oldest first
        """
        now = datetime.utcnow()

        # Try Redis first
        if self._is_connected and self.redis_client:
            try:
                key = self._make_key(symbol)
                cutoff = (now - timedelta(seconds=seconds_back)).timestamp()

                # Get snapshots in time range
                raw_snapshots = await self.redis_client.zrangebyscore(
                    key,
                    cutoff,
                    "+inf"
                )

                snapshots = [json.loads(s) for s in raw_snapshots]
                logger.debug(f"Retrieved {len(snapshots)} snapshots for {symbol}")
                return snapshots

            except Exception as e:
                logger.error(f"Error retrieving orderbook snapshots: {e}")

        # Fallback to memory cache
        if symbol in self._memory_cache:
            snapshots = list(self._memory_cache[symbol])
            cutoff = now - timedelta(seconds=seconds_back)

            # Filter by time
            filtered = [
                s for s in snapshots
                if datetime.fromisoformat(s["timestamp"]) >= cutoff
            ]

            logger.debug(f"Retrieved {len(filtered)} snapshots from memory for {symbol}")
            return filtered

        return []

    async def get_latest(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent order book snapshot

        Args:
            symbol: Trading pair symbol

        Returns:
            Latest snapshot or None if not found
        """
        snapshots = await self.get_snapshots(symbol, seconds_back=60)
        if snapshots:
            return snapshots[-1]
        return None

    @property
    def is_connected(self) -> bool:
        """Check if Redis connection is active"""
        return self._is_connected


# ==============================================================================
# ORDER BOOK FEATURE EXTRACTOR
# ==============================================================================

class OrderBookFeatureExtractor:
    """
    Extract market microstructure features from order book data

    This class provides methods to calculate various order book features
    that are useful for ML-based price prediction models.

    Features extracted:
    1. Bid-Ask Spread (%)
    2. Bid-Ask Imbalance
    3. Order Flow Imbalance
    4. Depth Imbalance (5 and 10 levels)
    5. Liquidity Score
    6. Volume-Weighted Mid Price
    7. Order Pressure

    Performance Target: <10ms total calculation time

    Usage:
        extractor = OrderBookFeatureExtractor()
        features = extractor.extract_all_features(orderbook_data)
    """

    # Price threshold for liquidity calculation (0.1% of mid price)
    LIQUIDITY_THRESHOLD_PCT = 0.001

    # Window size for order flow imbalance (5 minutes)
    ORDER_FLOW_WINDOW_SECONDS = 300

    def __init__(self, cache: Optional[OrderBookCache] = None):
        """
        Initialize feature extractor

        Args:
            cache: Optional OrderBookCache for historical data access
        """
        self.cache = cache
        self._last_features: Dict[str, OrderBookFeatures] = {}
        self._order_flow_history: Dict[str, deque] = {}

        logger.info("OrderBookFeatureExtractor initialized")

    def calculate_bid_ask_spread(
        self,
        orderbook: Dict[str, Any]
    ) -> Tuple[float, float, float, float]:
        """
        Calculate bid-ask spread and related prices

        The spread is a key measure of market liquidity:
        - Tight spread = High liquidity, low trading costs
        - Wide spread = Low liquidity, high trading costs

        Args:
            orderbook: Dict with 'bids' and 'asks' arrays
                      Each entry: [price, size] or {"price": x, "size": y}

        Returns:
            Tuple of (spread_pct, best_bid, best_ask, mid_price)
        """
        # Extract bids and asks
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])

        # Handle empty order book
        if not bids or not asks:
            logger.warning("Empty order book provided")
            return (0.0, 0.0, 0.0, 0.0)

        # Get best bid (highest buy price)
        best_bid = self._get_price(bids[0])

        # Get best ask (lowest sell price)
        best_ask = self._get_price(asks[0])

        # Calculate mid price
        mid_price = (best_bid + best_ask) / 2.0

        # Calculate spread as percentage of mid price
        if mid_price > 0:
            spread_pct = ((best_ask - best_bid) / mid_price) * 100
        else:
            spread_pct = 0.0

        return (spread_pct, best_bid, best_ask, mid_price)

    def calculate_bid_ask_imbalance(
        self,
        orderbook: Dict[str, Any],
        levels: int = 10
    ) -> Tuple[float, float, float]:
        """
        Calculate bid-ask volume imbalance

        Imbalance formula: (bid_volume - ask_volume) / (bid_volume + ask_volume)

        Range: [-1, 1]
        - Positive: More buying pressure (bullish signal)
        - Negative: More selling pressure (bearish signal)
        - Near 0: Balanced market

        Args:
            orderbook: Order book data
            levels: Number of price levels to consider (default 10)

        Returns:
            Tuple of (imbalance, bid_volume, ask_volume)
        """
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])

        # Calculate total volume on each side (limited to specified levels)
        bid_volume = sum(
            self._get_size(bids[i])
            for i in range(min(levels, len(bids)))
        )

        ask_volume = sum(
            self._get_size(asks[i])
            for i in range(min(levels, len(asks)))
        )

        # Calculate imbalance
        total_volume = bid_volume + ask_volume
        if total_volume > 0:
            imbalance = (bid_volume - ask_volume) / total_volume
        else:
            imbalance = 0.0

        return (imbalance, bid_volume, ask_volume)

    def calculate_order_flow_imbalance(
        self,
        symbol: str,
        current_orderbook: Dict[str, Any],
        history: Optional[List[Dict[str, Any]]] = None
    ) -> float:
        """
        Calculate order flow imbalance over rolling time window

        This measures the cumulative buying vs selling pressure
        by tracking changes in the order book over time.

        Args:
            symbol: Trading pair symbol (for caching)
            current_orderbook: Current order book snapshot
            history: Optional list of historical snapshots

        Returns:
            Order flow imbalance ratio [-1, 1]
        """
        # Initialize history tracking for this symbol
        if symbol not in self._order_flow_history:
            self._order_flow_history[symbol] = deque(maxlen=300)  # 5 min at 1s

        # Calculate current bid-ask volumes
        current_bid_vol = sum(
            self._get_size(b) for b in current_orderbook.get("bids", [])[:10]
        )
        current_ask_vol = sum(
            self._get_size(a) for a in current_orderbook.get("asks", [])[:10]
        )

        # Store current state
        now = datetime.utcnow()
        self._order_flow_history[symbol].append({
            "timestamp": now,
            "bid_volume": current_bid_vol,
            "ask_volume": current_ask_vol
        })

        # Calculate flow imbalance from history
        history_data = list(self._order_flow_history[symbol])

        if len(history_data) < 2:
            # Not enough history, use simple imbalance
            total = current_bid_vol + current_ask_vol
            if total > 0:
                return (current_bid_vol - current_ask_vol) / total
            return 0.0

        # Calculate cumulative volume changes
        bid_flow = 0.0
        ask_flow = 0.0

        for i in range(1, len(history_data)):
            prev = history_data[i - 1]
            curr = history_data[i]

            # Positive change in bid volume = buying pressure
            bid_delta = curr["bid_volume"] - prev["bid_volume"]
            ask_delta = curr["ask_volume"] - prev["ask_volume"]

            # Accumulate with decay factor (recent changes weighted more)
            decay = 0.95 ** (len(history_data) - i)
            bid_flow += max(0, bid_delta) * decay
            ask_flow += max(0, ask_delta) * decay

        # Calculate final imbalance
        total_flow = bid_flow + ask_flow
        if total_flow > 0:
            return (bid_flow - ask_flow) / total_flow

        return 0.0

    def calculate_depth_imbalance(
        self,
        orderbook: Dict[str, Any],
        levels: int = 5
    ) -> float:
        """
        Calculate volume imbalance at specified depth levels

        This measures the volume distribution at different price levels,
        useful for detecting large hidden orders or walls.

        Args:
            orderbook: Order book data
            levels: Number of price levels to analyze (5, 10, 20)

        Returns:
            Depth imbalance ratio [-1, 1]
        """
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])

        # Limit to specified levels
        bids = bids[:levels]
        asks = asks[:levels]

        # Calculate weighted volume (closer levels have more weight)
        bid_weighted_vol = 0.0
        ask_weighted_vol = 0.0

        for i, bid in enumerate(bids):
            weight = 1.0 / (i + 1)  # Higher weight for closer levels
            bid_weighted_vol += self._get_size(bid) * weight

        for i, ask in enumerate(asks):
            weight = 1.0 / (i + 1)
            ask_weighted_vol += self._get_size(ask) * weight

        # Calculate imbalance
        total = bid_weighted_vol + ask_weighted_vol
        if total > 0:
            return (bid_weighted_vol - ask_weighted_vol) / total

        return 0.0

    def calculate_liquidity_score(
        self,
        orderbook: Dict[str, Any],
        mid_price: Optional[float] = None
    ) -> float:
        """
        Calculate liquidity score based on volume within threshold of mid price

        The liquidity score measures how much volume is available near the
        current market price. Higher scores indicate better liquidity.

        Args:
            orderbook: Order book data
            mid_price: Optional pre-calculated mid price

        Returns:
            Liquidity score (total volume within 0.1% of mid)
        """
        # Calculate mid price if not provided
        if mid_price is None:
            _, _, _, mid_price = self.calculate_bid_ask_spread(orderbook)

        if mid_price <= 0:
            return 0.0

        # Calculate price threshold (0.1% of mid price)
        price_threshold = mid_price * self.LIQUIDITY_THRESHOLD_PCT
        lower_bound = mid_price - price_threshold
        upper_bound = mid_price + price_threshold

        # Sum volume within threshold
        total_volume = 0.0

        # Count bid volume within threshold
        for bid in orderbook.get("bids", []):
            price = self._get_price(bid)
            if price >= lower_bound:
                total_volume += self._get_size(bid)
            else:
                break  # Bids are sorted descending

        # Count ask volume within threshold
        for ask in orderbook.get("asks", []):
            price = self._get_price(ask)
            if price <= upper_bound:
                total_volume += self._get_size(ask)
            else:
                break  # Asks are sorted ascending

        return total_volume

    def calculate_volume_weighted_mid(
        self,
        orderbook: Dict[str, Any]
    ) -> float:
        """
        Calculate volume-weighted mid price

        This provides a more accurate estimate of the "true" mid price
        by weighting the best bid and ask by their respective volumes.

        Formula: (best_bid * ask_vol + best_ask * bid_vol) / (bid_vol + ask_vol)

        When ask volume > bid volume, VWMID is closer to bid (buyers aggressive)
        When bid volume > ask volume, VWMID is closer to ask (sellers aggressive)

        Args:
            orderbook: Order book data

        Returns:
            Volume-weighted mid price
        """
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])

        if not bids or not asks:
            return 0.0

        # Get best bid and ask with volumes
        best_bid = self._get_price(bids[0])
        best_ask = self._get_price(asks[0])
        bid_size = self._get_size(bids[0])
        ask_size = self._get_size(asks[0])

        # Calculate volume-weighted mid
        total_size = bid_size + ask_size
        if total_size > 0:
            # VWMID pulls toward the side with less volume
            vwmid = (best_bid * ask_size + best_ask * bid_size) / total_size
            return vwmid

        # Fallback to simple mid
        return (best_bid + best_ask) / 2.0

    def calculate_order_pressure(
        self,
        symbol: str,
        current_orderbook: Dict[str, Any],
        history: Optional[List[Dict[str, Any]]] = None
    ) -> float:
        """
        Calculate order pressure indicator (rate of order book changes)

        This measures how actively the order book is being updated,
        which can indicate increasing market activity or volatility.

        Args:
            symbol: Trading pair symbol
            current_orderbook: Current order book snapshot
            history: Optional list of historical snapshots

        Returns:
            Normalized order pressure score [-1, 1]
        """
        # Get historical snapshots from cache or memory
        flow_history = self._order_flow_history.get(symbol, deque())

        if len(flow_history) < 5:
            return 0.0  # Need minimum history for meaningful pressure

        # Calculate volume change rate
        recent_entries = list(flow_history)[-10:]  # Last 10 seconds

        if len(recent_entries) < 2:
            return 0.0

        # Calculate total volume changes
        total_bid_change = 0.0
        total_ask_change = 0.0

        for i in range(1, len(recent_entries)):
            prev = recent_entries[i - 1]
            curr = recent_entries[i]

            total_bid_change += abs(curr["bid_volume"] - prev["bid_volume"])
            total_ask_change += abs(curr["ask_volume"] - prev["ask_volume"])

        # Calculate directional pressure
        total_change = total_bid_change + total_ask_change
        if total_change > 0:
            # Positive = bid changes dominate (buying pressure)
            # Negative = ask changes dominate (selling pressure)
            pressure = (total_bid_change - total_ask_change) / total_change

            # Apply smoothing/normalization
            return np.clip(pressure, -1.0, 1.0)

        return 0.0

    def extract_all_features(
        self,
        orderbook: Dict[str, Any],
        symbol: str = "UNKNOWN",
        history: Optional[List[Dict[str, Any]]] = None
    ) -> OrderBookFeatures:
        """
        Extract all order book features in a single call

        This is the main entry point for feature extraction.
        Calculates all 8 core features plus supporting metrics.

        Performance: Targets <10ms total execution time

        Args:
            orderbook: Order book data with 'bids' and 'asks' arrays
            symbol: Trading pair symbol (for caching and logging)
            history: Optional historical snapshots for flow analysis

        Returns:
            OrderBookFeatures dataclass with all extracted features
        """
        start_time = time.perf_counter()

        try:
            # 1. Calculate bid-ask spread and basic prices
            spread_pct, best_bid, best_ask, mid_price = self.calculate_bid_ask_spread(
                orderbook
            )

            # 2. Calculate bid-ask imbalance
            imbalance, bid_vol, ask_vol = self.calculate_bid_ask_imbalance(
                orderbook, levels=10
            )

            # 3. Calculate order flow imbalance
            flow_imbalance = self.calculate_order_flow_imbalance(
                symbol, orderbook, history
            )

            # 4. Calculate depth imbalances at different levels
            depth_5 = self.calculate_depth_imbalance(orderbook, levels=5)
            depth_10 = self.calculate_depth_imbalance(orderbook, levels=10)

            # 5. Calculate liquidity score
            liquidity = self.calculate_liquidity_score(orderbook, mid_price)

            # 6. Calculate volume-weighted mid
            vwmid = self.calculate_volume_weighted_mid(orderbook)

            # 7. Calculate order pressure
            pressure = self.calculate_order_pressure(symbol, orderbook, history)

            # Calculate execution time
            calc_time_ms = (time.perf_counter() - start_time) * 1000

            # Build features object
            features = OrderBookFeatures(
                timestamp=datetime.utcnow(),
                symbol=symbol,
                bid_ask_spread_pct=spread_pct,
                bid_ask_imbalance=imbalance,
                order_flow_imbalance=flow_imbalance,
                depth_imbalance_5=depth_5,
                depth_imbalance_10=depth_10,
                liquidity_score=liquidity,
                volume_weighted_mid=vwmid,
                order_pressure=pressure,
                best_bid=best_bid,
                best_ask=best_ask,
                mid_price=mid_price,
                total_bid_volume=bid_vol,
                total_ask_volume=ask_vol,
                bid_depth_levels=len(orderbook.get("bids", [])),
                ask_depth_levels=len(orderbook.get("asks", [])),
                calculation_time_ms=calc_time_ms,
                levels_analyzed=min(
                    len(orderbook.get("bids", [])),
                    len(orderbook.get("asks", []))
                )
            )

            # Log performance if slow
            if calc_time_ms > 10:
                logger.warning(
                    f"Slow feature extraction for {symbol}: {calc_time_ms:.2f}ms"
                )
            else:
                logger.debug(
                    f"Feature extraction for {symbol} completed in {calc_time_ms:.2f}ms"
                )

            # Cache latest features
            self._last_features[symbol] = features

            return features

        except Exception as e:
            logger.error(f"Error extracting features for {symbol}: {e}", exc_info=True)
            # Return empty features on error
            return OrderBookFeatures(
                timestamp=datetime.utcnow(),
                symbol=symbol,
                calculation_time_ms=(time.perf_counter() - start_time) * 1000
            )

    def get_last_features(self, symbol: str) -> Optional[OrderBookFeatures]:
        """
        Get last calculated features for a symbol

        Args:
            symbol: Trading pair symbol

        Returns:
            Last calculated features or None
        """
        return self._last_features.get(symbol)

    def normalize_features(
        self,
        features: OrderBookFeatures,
        historical_stats: Optional[Dict[str, Dict[str, float]]] = None
    ) -> Dict[str, float]:
        """
        Normalize features using z-score normalization

        Args:
            features: OrderBookFeatures to normalize
            historical_stats: Optional dict with 'mean' and 'std' for each feature

        Returns:
            Dict of normalized feature values
        """
        # Default stats if not provided (from typical crypto market data)
        default_stats = {
            "bid_ask_spread_pct": {"mean": 0.05, "std": 0.03},
            "bid_ask_imbalance": {"mean": 0.0, "std": 0.3},
            "order_flow_imbalance": {"mean": 0.0, "std": 0.25},
            "depth_imbalance_5": {"mean": 0.0, "std": 0.35},
            "depth_imbalance_10": {"mean": 0.0, "std": 0.3},
            "liquidity_score": {"mean": 100.0, "std": 50.0},
            "volume_weighted_mid": {"mean": 50000.0, "std": 10000.0},
            "order_pressure": {"mean": 0.0, "std": 0.2},
        }

        stats = historical_stats or default_stats

        # Extract raw values
        raw_values = {
            "bid_ask_spread_pct": features.bid_ask_spread_pct,
            "bid_ask_imbalance": features.bid_ask_imbalance,
            "order_flow_imbalance": features.order_flow_imbalance,
            "depth_imbalance_5": features.depth_imbalance_5,
            "depth_imbalance_10": features.depth_imbalance_10,
            "liquidity_score": features.liquidity_score,
            "volume_weighted_mid": features.volume_weighted_mid,
            "order_pressure": features.order_pressure,
        }

        # Normalize each feature
        normalized = {}
        for name, value in raw_values.items():
            stat = stats.get(name, {"mean": 0.0, "std": 1.0})
            mean = stat["mean"]
            std = stat["std"] if stat["std"] > 0 else 1.0

            # Z-score normalization
            z_score = (value - mean) / std

            # Clip to reasonable range
            normalized[name] = np.clip(z_score, -3.0, 3.0)

        return normalized

    # ==========================================================================
    # PRIVATE HELPER METHODS
    # ==========================================================================

    def _get_price(self, level: Any) -> float:
        """
        Extract price from order book level

        Handles both formats:
        - Array: [price, size]
        - Dict: {"price": x, "size": y}

        Args:
            level: Order book level data

        Returns:
            Price as float
        """
        if isinstance(level, (list, tuple)):
            return float(level[0])
        elif isinstance(level, dict):
            return float(level.get("price", 0))
        else:
            return float(level)

    def _get_size(self, level: Any) -> float:
        """
        Extract size from order book level

        Args:
            level: Order book level data

        Returns:
            Size as float
        """
        if isinstance(level, (list, tuple)):
            return float(level[1]) if len(level) > 1 else 0.0
        elif isinstance(level, dict):
            return float(level.get("size", level.get("qty", 0)))
        else:
            return 0.0


# ==============================================================================
# MODULE ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    """Demo usage of OrderBookFeatureExtractor"""
    import asyncio

    logging.basicConfig(level=logging.INFO)

    # Sample order book data (Bybit format)
    sample_orderbook = {
        "bids": [
            [100000.0, 1.5],  # Best bid: $100,000, 1.5 BTC
            [99999.5, 2.0],
            [99999.0, 0.8],
            [99998.5, 1.2],
            [99998.0, 3.0],
            [99997.5, 2.5],
            [99997.0, 1.8],
            [99996.5, 4.0],
            [99996.0, 2.2],
            [99995.5, 1.5],
        ],
        "asks": [
            [100001.0, 1.2],  # Best ask: $100,001, 1.2 BTC
            [100001.5, 1.8],
            [100002.0, 2.5],
            [100002.5, 1.0],
            [100003.0, 3.2],
            [100003.5, 2.0],
            [100004.0, 1.5],
            [100004.5, 2.8],
            [100005.0, 1.9],
            [100005.5, 2.1],
        ]
    }

    print("\n" + "=" * 80)
    print("ORDER BOOK FEATURE EXTRACTION DEMO")
    print("=" * 80)

    # Create extractor
    extractor = OrderBookFeatureExtractor()

    # Extract features
    features = extractor.extract_all_features(
        sample_orderbook,
        symbol="BTCUSDT"
    )

    # Display results
    print(f"\nSymbol: {features.symbol}")
    print(f"Timestamp: {features.timestamp}")
    print(f"Calculation time: {features.calculation_time_ms:.3f}ms")
    print("\n--- Core Features ---")
    print(f"Bid-Ask Spread: {features.bid_ask_spread_pct:.4f}%")
    print(f"Bid-Ask Imbalance: {features.bid_ask_imbalance:.4f}")
    print(f"Order Flow Imbalance: {features.order_flow_imbalance:.4f}")
    print(f"Depth Imbalance (5): {features.depth_imbalance_5:.4f}")
    print(f"Depth Imbalance (10): {features.depth_imbalance_10:.4f}")
    print(f"Liquidity Score: {features.liquidity_score:.2f}")
    print(f"Volume-Weighted Mid: ${features.volume_weighted_mid:,.2f}")
    print(f"Order Pressure: {features.order_pressure:.4f}")
    print("\n--- Prices ---")
    print(f"Best Bid: ${features.best_bid:,.2f}")
    print(f"Best Ask: ${features.best_ask:,.2f}")
    print(f"Mid Price: ${features.mid_price:,.2f}")
    print("\n--- ML Feature Array ---")
    print(f"Feature names: {OrderBookFeatures.get_feature_names()}")
    print(f"Feature values: {features.to_ml_array()}")

    print("\n" + "=" * 80)
