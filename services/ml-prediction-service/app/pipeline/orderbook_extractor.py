"""
Order Book Feature Extractor - Phase 6.2 Feature Extraction
Purpose: Extract order book features for ML models
Author: Phase 6.4 Implementation
Date: 2025-12-11

Provides 8 order book features:
- bid_ask_spread_pct: Spread as percentage of mid price
- bid_ask_imbalance: Volume imbalance between bids and asks
- order_flow_imbalance: Flow direction indicator
- depth_imbalance_5: 5-level depth imbalance
- depth_imbalance_10: 10-level depth imbalance
- liquidity_score: Available liquidity measure
- volume_weighted_mid: Better mid price estimate
- order_pressure: Rate of change in order book
"""

import asyncio
import httpx
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import numpy as np

# Configure logger
logger = logging.getLogger(__name__)


@dataclass
class OrderBookFeatures:
    """
    Order book feature set for ML models

    All values are normalized for ML input:
    - bid_ask_spread_pct: [0, 1] spread as percentage
    - bid_ask_imbalance: [-1, 1] buy/sell pressure
    - order_flow_imbalance: [-1, 1] flow direction
    - depth_imbalance_5: [-1, 1] 5-level depth
    - depth_imbalance_10: [-1, 1] 10-level depth
    - liquidity_score: [0, 1] available liquidity
    - volume_weighted_mid: [0, 1] normalized mid price
    - order_pressure: [-1, 1] pressure rate of change
    """
    # Spread percentage (0-1 where 0.01 = 1%)
    bid_ask_spread_pct: float = 0.001  # Default 0.1%

    # Volume imbalance between bids and asks
    bid_ask_imbalance: float = 0.0  # -1 (ask heavy) to 1 (bid heavy)

    # Order flow direction
    order_flow_imbalance: float = 0.0  # -1 (selling) to 1 (buying)

    # Depth imbalance at different levels
    depth_imbalance_5: float = 0.0  # 5-level depth
    depth_imbalance_10: float = 0.0  # 10-level depth

    # Liquidity measure
    liquidity_score: float = 0.5  # 0 (illiquid) to 1 (liquid)

    # Volume-weighted mid price (normalized)
    volume_weighted_mid: float = 0.0  # Deviation from simple mid

    # Order pressure rate of change
    order_pressure: float = 0.0  # -1 (decreasing) to 1 (increasing)

    # Metadata
    timestamp: datetime = field(default_factory=datetime.utcnow)
    best_bid: float = 0.0
    best_ask: float = 0.0
    mid_price: float = 0.0
    orderbook_available: bool = False

    def to_array(self) -> np.ndarray:
        """Convert to numpy array for ML model input"""
        return np.array([
            self.bid_ask_spread_pct * 100,  # Scale spread for better gradients
            self.bid_ask_imbalance,
            self.order_flow_imbalance,
            self.depth_imbalance_5,
            self.depth_imbalance_10,
            self.liquidity_score,
            self.volume_weighted_mid,
            self.order_pressure
        ], dtype=np.float32)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            'bid_ask_spread_pct': self.bid_ask_spread_pct,
            'bid_ask_imbalance': self.bid_ask_imbalance,
            'order_flow_imbalance': self.order_flow_imbalance,
            'depth_imbalance_5': self.depth_imbalance_5,
            'depth_imbalance_10': self.depth_imbalance_10,
            'liquidity_score': self.liquidity_score,
            'volume_weighted_mid': self.volume_weighted_mid,
            'order_pressure': self.order_pressure,
            'timestamp': self.timestamp.isoformat(),
            'best_bid': self.best_bid,
            'best_ask': self.best_ask,
            'mid_price': self.mid_price,
            'orderbook_available': self.orderbook_available
        }

    @classmethod
    def feature_names(cls) -> List[str]:
        """Return list of feature names for dataframe columns"""
        return [
            'bid_ask_spread_pct_scaled',  # Scaled by 100
            'bid_ask_imbalance',
            'order_flow_imbalance',
            'depth_imbalance_5',
            'depth_imbalance_10',
            'liquidity_score',
            'volume_weighted_mid',
            'order_pressure'
        ]


class OrderBookFeatureExtractor:
    """
    Order book feature extractor for ML models

    Fetches order book data from Bybit connector service and
    extracts meaningful features for price prediction.

    Example usage:
        extractor = OrderBookFeatureExtractor(bybit_url="http://localhost:8004")
        features = await extractor.extract_all_features("BTCUSDT")
    """

    def __init__(
        self,
        bybit_connector_url: str = "http://localhost:8004",
        market_data_url: str = "http://localhost:8005",
        timeout: float = 10.0,
        cache_ttl_seconds: int = 5,  # Order book data should be fresh
        depth_limit: int = 50
    ):
        """
        Initialize order book feature extractor

        Args:
            bybit_connector_url: URL of Bybit connector service
            market_data_url: URL of market data service (alternative source)
            timeout: HTTP request timeout in seconds
            cache_ttl_seconds: Cache TTL (short for order book)
            depth_limit: Number of order book levels to fetch
        """
        self.bybit_connector_url = bybit_connector_url
        self.market_data_url = market_data_url
        self.timeout = timeout
        self.cache_ttl_seconds = cache_ttl_seconds
        self.depth_limit = depth_limit

        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None

        # Cache for order book data
        self._cache: Dict[str, Tuple[OrderBookFeatures, datetime]] = {}

        # Historical data for pressure calculation
        self._pressure_history: Dict[str, List[Tuple[float, datetime]]] = {}
        self._max_history_length = 10

        logger.info(f"OrderBookFeatureExtractor initialized (url={bybit_connector_url})")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        """Close HTTP client connections"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def extract_all_features(
        self,
        symbol: str,
        use_cache: bool = True
    ) -> OrderBookFeatures:
        """
        Extract all order book features for a symbol

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            use_cache: Whether to use cached data

        Returns:
            OrderBookFeatures with all 8 indicators
        """
        # Check cache (very short TTL for order book)
        if use_cache and symbol in self._cache:
            cached_features, cached_time = self._cache[symbol]
            age_seconds = (datetime.utcnow() - cached_time).total_seconds()
            if age_seconds < self.cache_ttl_seconds:
                logger.debug(f"Using cached order book for {symbol} (age={age_seconds:.1f}s)")
                return cached_features

        # Fetch order book data
        orderbook = await self._fetch_orderbook(symbol)

        if orderbook is None:
            logger.warning(f"Order book not available for {symbol}, using defaults")
            return OrderBookFeatures()

        # Extract features from order book
        features = self._extract_features_from_orderbook(symbol, orderbook)

        # Update cache
        self._cache[symbol] = (features, datetime.utcnow())

        return features

    async def _fetch_orderbook(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch order book from Bybit connector service

        Args:
            symbol: Trading pair

        Returns:
            Order book data or None if unavailable
        """
        try:
            client = await self._get_client()

            # Try Bybit connector first
            url = f"{self.bybit_connector_url}/api/v1/orderbook/{symbol}"
            params = {"limit": self.depth_limit}

            response = await client.get(url, params=params)

            if response.status_code == 200:
                data = response.json()
                # Handle wrapped response
                if 'data' in data:
                    data = data['data']
                logger.debug(f"Fetched order book for {symbol}")
                return data

            # Fallback to market data service
            logger.debug(f"Bybit connector returned {response.status_code}, trying market data service")
            url = f"{self.market_data_url}/api/v1/orderbook/{symbol}"
            response = await client.get(url, params=params)

            if response.status_code == 200:
                data = response.json()
                if 'data' in data:
                    data = data['data']
                return data

            return None

        except httpx.TimeoutException:
            logger.warning(f"Order book fetch timeout for {symbol}")
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch order book for {symbol}: {e}")
            return None

    def _extract_features_from_orderbook(
        self,
        symbol: str,
        orderbook: Dict[str, Any]
    ) -> OrderBookFeatures:
        """
        Extract ML features from raw order book data

        Args:
            symbol: Trading pair
            orderbook: Raw order book data with 'bids' and 'asks'

        Returns:
            OrderBookFeatures object
        """
        features = OrderBookFeatures()

        try:
            # Parse bids and asks
            # Format: [[price, size], ...] or [{"price": p, "size": s}, ...]
            bids = self._parse_orders(orderbook.get('bids', orderbook.get('b', [])))
            asks = self._parse_orders(orderbook.get('asks', orderbook.get('a', [])))

            if not bids or not asks:
                logger.warning(f"Empty order book for {symbol}")
                return features

            features.orderbook_available = True

            # Best bid/ask
            features.best_bid = bids[0][0]
            features.best_ask = asks[0][0]
            features.mid_price = (features.best_bid + features.best_ask) / 2

            # 1. Bid-Ask Spread Percentage
            features.bid_ask_spread_pct = self._calculate_spread_pct(
                features.best_bid,
                features.best_ask
            )

            # 2. Bid-Ask Volume Imbalance
            features.bid_ask_imbalance = self._calculate_volume_imbalance(bids, asks)

            # 3. Order Flow Imbalance (using top of book)
            features.order_flow_imbalance = self._calculate_order_flow_imbalance(
                bids[:5],
                asks[:5]
            )

            # 4. Depth Imbalance at 5 levels
            features.depth_imbalance_5 = self._calculate_depth_imbalance(
                bids[:5],
                asks[:5]
            )

            # 5. Depth Imbalance at 10 levels
            features.depth_imbalance_10 = self._calculate_depth_imbalance(
                bids[:10],
                asks[:10]
            )

            # 6. Liquidity Score
            features.liquidity_score = self._calculate_liquidity_score(
                bids,
                asks,
                features.mid_price
            )

            # 7. Volume-Weighted Mid Price
            features.volume_weighted_mid = self._calculate_vwap_deviation(
                bids[:10],
                asks[:10],
                features.mid_price
            )

            # 8. Order Pressure (rate of change)
            features.order_pressure = self._calculate_order_pressure(
                symbol,
                features.bid_ask_imbalance
            )

            features.timestamp = datetime.utcnow()

        except Exception as e:
            logger.error(f"Error extracting order book features: {e}")

        return features

    def _parse_orders(
        self,
        orders: List[Any]
    ) -> List[Tuple[float, float]]:
        """
        Parse order book entries to (price, size) tuples

        Args:
            orders: Raw order data

        Returns:
            List of (price, size) tuples
        """
        parsed = []

        for order in orders:
            try:
                if isinstance(order, (list, tuple)):
                    # Format: [price, size]
                    price = float(order[0])
                    size = float(order[1])
                elif isinstance(order, dict):
                    # Format: {"price": p, "size": s} or {"p": p, "v": v}
                    price = float(order.get('price', order.get('p', 0)))
                    size = float(order.get('size', order.get('qty', order.get('v', 0))))
                else:
                    continue

                parsed.append((price, size))

            except (ValueError, TypeError, IndexError):
                continue

        return parsed

    def _calculate_spread_pct(self, best_bid: float, best_ask: float) -> float:
        """
        Calculate bid-ask spread as percentage

        Args:
            best_bid: Best bid price
            best_ask: Best ask price

        Returns:
            Spread percentage [0, 1]
        """
        if best_bid <= 0 or best_ask <= 0:
            return 0.01  # Default 1%

        mid = (best_bid + best_ask) / 2
        spread = (best_ask - best_bid) / mid

        # Cap at 10%
        return min(spread, 0.1)

    def _calculate_volume_imbalance(
        self,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]]
    ) -> float:
        """
        Calculate volume imbalance between bids and asks

        Args:
            bids: List of (price, size) bid orders
            asks: List of (price, size) ask orders

        Returns:
            Imbalance [-1, 1] where 1 = more bids, -1 = more asks
        """
        total_bid_volume = sum(size for _, size in bids)
        total_ask_volume = sum(size for _, size in asks)

        total = total_bid_volume + total_ask_volume

        if total == 0:
            return 0.0

        # Imbalance: (bids - asks) / total
        imbalance = (total_bid_volume - total_ask_volume) / total

        return max(-1.0, min(1.0, imbalance))

    def _calculate_order_flow_imbalance(
        self,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]]
    ) -> float:
        """
        Calculate order flow imbalance using price-weighted volume

        Gives more weight to orders closer to mid price

        Args:
            bids: Top bid orders
            asks: Top ask orders

        Returns:
            Flow imbalance [-1, 1]
        """
        if not bids or not asks:
            return 0.0

        mid = (bids[0][0] + asks[0][0]) / 2

        # Weight by distance from mid (closer = higher weight)
        def weighted_volume(orders: List[Tuple[float, float]], is_bid: bool) -> float:
            total = 0.0
            for price, size in orders:
                distance = abs(price - mid) / mid
                weight = 1.0 / (1.0 + distance * 100)  # Higher weight for closer prices
                total += size * weight
            return total

        bid_weighted = weighted_volume(bids, is_bid=True)
        ask_weighted = weighted_volume(asks, is_bid=False)

        total = bid_weighted + ask_weighted
        if total == 0:
            return 0.0

        return max(-1.0, min(1.0, (bid_weighted - ask_weighted) / total))

    def _calculate_depth_imbalance(
        self,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]]
    ) -> float:
        """
        Calculate depth imbalance at specified levels

        Args:
            bids: Bid orders at specified levels
            asks: Ask orders at specified levels

        Returns:
            Depth imbalance [-1, 1]
        """
        bid_depth = sum(price * size for price, size in bids)
        ask_depth = sum(price * size for price, size in asks)

        total = bid_depth + ask_depth

        if total == 0:
            return 0.0

        imbalance = (bid_depth - ask_depth) / total

        return max(-1.0, min(1.0, imbalance))

    def _calculate_liquidity_score(
        self,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
        mid_price: float
    ) -> float:
        """
        Calculate liquidity score based on available depth

        Args:
            bids: All bid orders
            asks: All ask orders
            mid_price: Current mid price

        Returns:
            Liquidity score [0, 1]
        """
        if mid_price <= 0:
            return 0.5

        # Calculate total notional value within 2% of mid price
        bid_liquidity = sum(
            price * size
            for price, size in bids
            if price >= mid_price * 0.98
        )
        ask_liquidity = sum(
            price * size
            for price, size in asks
            if price <= mid_price * 1.02
        )

        total_liquidity = bid_liquidity + ask_liquidity

        # Normalize: $1M = 1.0 liquidity score
        # Adjust multiplier based on typical market depth
        normalized = min(total_liquidity / 1_000_000, 1.0)

        return normalized

    def _calculate_vwap_deviation(
        self,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
        mid_price: float
    ) -> float:
        """
        Calculate volume-weighted average price deviation from mid

        Args:
            bids: Top bid orders
            asks: Top ask orders
            mid_price: Simple mid price

        Returns:
            Deviation [-1, 1] where positive = VWAP above mid
        """
        if mid_price <= 0 or not bids or not asks:
            return 0.0

        # Calculate VWAP from both sides
        total_volume = 0.0
        total_value = 0.0

        for price, size in bids + asks:
            total_volume += size
            total_value += price * size

        if total_volume == 0:
            return 0.0

        vwap = total_value / total_volume

        # Deviation from mid as percentage, normalized to [-1, 1]
        deviation = (vwap - mid_price) / mid_price

        # Cap at +/- 1% = +/- 1.0
        return max(-1.0, min(1.0, deviation * 100))

    def _calculate_order_pressure(
        self,
        symbol: str,
        current_imbalance: float
    ) -> float:
        """
        Calculate rate of change in order book pressure

        Args:
            symbol: Trading pair
            current_imbalance: Current bid-ask imbalance

        Returns:
            Pressure rate of change [-1, 1]
        """
        if symbol not in self._pressure_history:
            self._pressure_history[symbol] = []

        history = self._pressure_history[symbol]

        # Add current reading
        history.append((current_imbalance, datetime.utcnow()))

        # Trim history
        if len(history) > self._max_history_length:
            self._pressure_history[symbol] = history[-self._max_history_length:]

        if len(history) < 2:
            return 0.0

        # Calculate rate of change
        imbalances = [h[0] for h in history]
        pressure_change = imbalances[-1] - imbalances[0]

        return max(-1.0, min(1.0, pressure_change))

    async def get_batch_features(
        self,
        symbols: List[str]
    ) -> Dict[str, OrderBookFeatures]:
        """
        Extract order book features for multiple symbols in parallel

        Args:
            symbols: List of trading pairs

        Returns:
            Dictionary mapping symbol to OrderBookFeatures
        """
        tasks = [self.extract_all_features(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        features_dict = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to get order book for {symbol}: {result}")
                features_dict[symbol] = OrderBookFeatures()
            else:
                features_dict[symbol] = result

        return features_dict

    def get_order_book_signal(self, features: OrderBookFeatures) -> str:
        """
        Derive trading signal from order book features

        Args:
            features: OrderBookFeatures object

        Returns:
            Signal string: "BUY", "SELL", or "HOLD"
        """
        # Weighted score based on imbalances
        score = (
            features.bid_ask_imbalance * 0.3 +
            features.order_flow_imbalance * 0.3 +
            features.depth_imbalance_10 * 0.2 +
            features.order_pressure * 0.2
        )

        if score > 0.3:
            return "BUY"
        elif score < -0.3:
            return "SELL"
        else:
            return "HOLD"
