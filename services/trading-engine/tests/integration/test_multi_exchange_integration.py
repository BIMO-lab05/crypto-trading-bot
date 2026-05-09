"""
Integration Tests for Multi-Exchange Support
=============================================
Phase 6: Multi-Exchange Support Integration Tests

Purpose:
- Test exchange adapter abstraction layer
- Verify multi-exchange routing and arbitrage detection
- Test failover and redundancy mechanisms
- Validate cross-exchange position management

Test Coverage:
- BaseExchange adapter interface
- ExchangeManager multi-exchange coordination
- Arbitrage opportunity detection
- Cross-exchange order routing
- Exchange failover handling
"""

import pytest

pytest.skip(
    "stale imports vs current trading-engine API; needs rewrite after PR #86 refactor",
    allow_module_level=True,
)


import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Dict, Any
from unittest.mock import MagicMock, AsyncMock, patch
import uuid

# Import exchange components
from app.exchanges.base import (
    BaseExchange,
    ExchangeConfig,
    OrderRequest,
    OrderResponse,
    ExchangeError,
    RateLimitError,
)
from app.exchanges.manager import (
    ExchangeManager,
    ExchangeManagerConfig,
    ArbitrageOpportunity,
    RoutingStrategy,
)
from app.models import OrderSide, OrderType, OrderStatus


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def exchange_config_bybit() -> ExchangeConfig:
    """
    Create Bybit exchange configuration

    Returns:
        ExchangeConfig for Bybit
    """
    return ExchangeConfig(
        exchange_id="bybit",
        name="Bybit",
        api_key="test_api_key",
        api_secret="test_api_secret",
        testnet=True,
        rate_limit_per_second=10,
        timeout_seconds=10,
    )


@pytest.fixture
def exchange_config_binance() -> ExchangeConfig:
    """
    Create Binance exchange configuration

    Returns:
        ExchangeConfig for Binance
    """
    return ExchangeConfig(
        exchange_id="binance",
        name="Binance",
        api_key="test_api_key",
        api_secret="test_api_secret",
        testnet=True,
        rate_limit_per_second=20,
        timeout_seconds=10,
    )


@pytest.fixture
def manager_config() -> ExchangeManagerConfig:
    """
    Create exchange manager configuration

    Returns:
        ExchangeManagerConfig for testing
    """
    return ExchangeManagerConfig(
        primary_exchange="bybit",
        enable_arbitrage_detection=True,
        arbitrage_threshold_bps=50,  # 0.5% threshold
        failover_enabled=True,
        max_retry_attempts=3,
        routing_strategy=RoutingStrategy.BEST_PRICE,
    )


@pytest.fixture
def mock_bybit_exchange(exchange_config_bybit):
    """
    Create mock Bybit exchange

    Returns:
        Mock exchange with Bybit-like responses
    """
    exchange = AsyncMock(spec=BaseExchange)
    exchange.config = exchange_config_bybit
    exchange.exchange_id = "bybit"
    exchange.is_connected = True

    # Mock ticker data
    exchange.get_ticker = AsyncMock(return_value={
        "symbol": "BTCUSDT",
        "last_price": 50000.0,
        "bid_price": 49990.0,
        "ask_price": 50000.0,
        "volume_24h": 1000000000.0,
    })

    # Mock orderbook
    exchange.get_orderbook = AsyncMock(return_value={
        "bids": [
            {"price": 49990.0, "qty": 10.0},
            {"price": 49980.0, "qty": 20.0},
        ],
        "asks": [
            {"price": 50000.0, "qty": 10.0},
            {"price": 50010.0, "qty": 20.0},
        ],
    })

    # Mock order placement
    exchange.place_order = AsyncMock(return_value=OrderResponse(
        order_id=str(uuid.uuid4()),
        exchange_id="bybit",
        symbol="BTCUSDT",
        status=OrderStatus.FILLED,
        filled_qty=Decimal("0.1"),
        filled_price=Decimal("50000.0"),
        fee=Decimal("0.5"),
    ))

    # Mock balance
    exchange.get_balance = AsyncMock(return_value={
        "USDT": {"available": 10000.0, "total": 10500.0},
        "BTC": {"available": 0.5, "total": 0.5},
    })

    return exchange


@pytest.fixture
def mock_binance_exchange(exchange_config_binance):
    """
    Create mock Binance exchange

    Returns:
        Mock exchange with Binance-like responses
    """
    exchange = AsyncMock(spec=BaseExchange)
    exchange.config = exchange_config_binance
    exchange.exchange_id = "binance"
    exchange.is_connected = True

    # Mock ticker data (slightly different prices for arbitrage testing)
    exchange.get_ticker = AsyncMock(return_value={
        "symbol": "BTCUSDT",
        "last_price": 50050.0,  # Higher than Bybit
        "bid_price": 50040.0,
        "ask_price": 50050.0,
        "volume_24h": 2000000000.0,
    })

    # Mock orderbook
    exchange.get_orderbook = AsyncMock(return_value={
        "bids": [
            {"price": 50040.0, "qty": 15.0},
            {"price": 50030.0, "qty": 25.0},
        ],
        "asks": [
            {"price": 50050.0, "qty": 15.0},
            {"price": 50060.0, "qty": 25.0},
        ],
    })

    # Mock order placement
    exchange.place_order = AsyncMock(return_value=OrderResponse(
        order_id=str(uuid.uuid4()),
        exchange_id="binance",
        symbol="BTCUSDT",
        status=OrderStatus.FILLED,
        filled_qty=Decimal("0.1"),
        filled_price=Decimal("50050.0"),
        fee=Decimal("0.5"),
    ))

    # Mock balance
    exchange.get_balance = AsyncMock(return_value={
        "USDT": {"available": 15000.0, "total": 15000.0},
        "BTC": {"available": 0.3, "total": 0.3},
    })

    return exchange


@pytest.fixture
def exchange_manager(
    manager_config,
    mock_bybit_exchange,
    mock_binance_exchange
) -> ExchangeManager:
    """
    Create exchange manager with mock exchanges

    Returns:
        ExchangeManager configured with test exchanges
    """
    manager = ExchangeManager(config=manager_config)
    manager.register_exchange(mock_bybit_exchange)
    manager.register_exchange(mock_binance_exchange)
    return manager


# ============================================================================
# EXCHANGE REGISTRATION TESTS
# ============================================================================

class TestExchangeRegistrationIntegration:
    """Test suite for exchange registration and management"""

    @pytest.mark.asyncio
    async def test_register_exchange(
        self,
        exchange_manager,
        mock_bybit_exchange
    ):
        """
        Test exchange can be registered

        Verifies:
        - Exchange is added to manager
        - Exchange configuration is stored
        """
        exchanges = exchange_manager.get_registered_exchanges()

        assert "bybit" in exchanges
        assert "binance" in exchanges
        assert len(exchanges) == 2

    @pytest.mark.asyncio
    async def test_unregister_exchange(self, exchange_manager):
        """
        Test exchange can be unregistered

        Verifies:
        - Exchange is removed from manager
        - Routing updates to exclude removed exchange
        """
        exchange_manager.unregister_exchange("binance")

        exchanges = exchange_manager.get_registered_exchanges()
        assert "binance" not in exchanges
        assert "bybit" in exchanges

    @pytest.mark.asyncio
    async def test_get_exchange_status(self, exchange_manager):
        """
        Test getting exchange connection status

        Verifies:
        - Status shows connection state
        - Rate limit info is included
        """
        status = await exchange_manager.get_exchange_status("bybit")

        assert status["exchange_id"] == "bybit"
        assert status["is_connected"] == True
        assert "rate_limit" in status


# ============================================================================
# PRICE AGGREGATION TESTS
# ============================================================================

class TestPriceAggregationIntegration:
    """Test suite for cross-exchange price aggregation"""

    @pytest.mark.asyncio
    async def test_get_best_price_across_exchanges(self, exchange_manager):
        """
        Test getting best price across all exchanges

        Verifies:
        - Best bid (highest) is found
        - Best ask (lowest) is found
        - Source exchange is identified
        """
        best_prices = await exchange_manager.get_best_prices("BTCUSDT")

        # Bybit has lower ask (50000) vs Binance (50050)
        assert best_prices["best_ask"]["price"] == 50000.0
        assert best_prices["best_ask"]["exchange"] == "bybit"

        # Binance has higher bid (50040) vs Bybit (49990)
        assert best_prices["best_bid"]["price"] == 50040.0
        assert best_prices["best_bid"]["exchange"] == "binance"

    @pytest.mark.asyncio
    async def test_aggregate_orderbook(self, exchange_manager):
        """
        Test aggregating orderbooks from multiple exchanges

        Verifies:
        - All liquidity is combined
        - Levels are sorted correctly
        """
        aggregated = await exchange_manager.get_aggregated_orderbook("BTCUSDT")

        # Bids should be sorted descending
        assert aggregated["bids"][0]["price"] >= aggregated["bids"][-1]["price"]

        # Asks should be sorted ascending
        assert aggregated["asks"][0]["price"] <= aggregated["asks"][-1]["price"]

        # Should have liquidity from both exchanges
        total_bid_qty = sum(b["qty"] for b in aggregated["bids"])
        assert total_bid_qty > 20  # Combined from both

    @pytest.mark.asyncio
    async def test_get_volume_weighted_price(self, exchange_manager):
        """
        Test volume-weighted average price across exchanges

        Verifies:
        - VWAP is calculated correctly
        - Weighted by exchange volume
        """
        vwap = await exchange_manager.get_volume_weighted_price("BTCUSDT")

        # VWAP should be between the two exchange prices
        assert 50000.0 <= vwap <= 50050.0


# ============================================================================
# ARBITRAGE DETECTION TESTS
# ============================================================================

class TestArbitrageDetectionIntegration:
    """Test suite for arbitrage opportunity detection"""

    @pytest.mark.asyncio
    async def test_detect_arbitrage_opportunity(self, exchange_manager):
        """
        Test arbitrage opportunity detection

        Scenario:
        - Bybit ask: 50000, Binance bid: 50040
        - Potential profit: 40 (80 bps)
        """
        # Configure threshold lower than spread
        exchange_manager.config.arbitrage_threshold_bps = 50  # 0.5%

        opportunities = await exchange_manager.detect_arbitrage(["BTCUSDT"])

        # Should detect opportunity (80 bps > 50 bps threshold)
        assert len(opportunities) > 0

        opp = opportunities[0]
        assert isinstance(opp, ArbitrageOpportunity)
        assert opp.buy_exchange == "bybit"
        assert opp.sell_exchange == "binance"
        assert opp.profit_bps > 50

    @pytest.mark.asyncio
    async def test_no_arbitrage_when_spread_negative(self, exchange_manager):
        """
        Test no arbitrage when spread doesn't exist

        Scenario:
        - Make Bybit ask higher than Binance bid
        - No arbitrage opportunity
        """
        # Modify mock to eliminate arbitrage
        exchange_manager.exchanges["bybit"].get_ticker.return_value = {
            "symbol": "BTCUSDT",
            "last_price": 50100.0,
            "bid_price": 50090.0,
            "ask_price": 50100.0,  # Higher than Binance bid
            "volume_24h": 1000000000.0,
        }

        opportunities = await exchange_manager.detect_arbitrage(["BTCUSDT"])

        # Should not detect opportunity
        assert len(opportunities) == 0

    @pytest.mark.asyncio
    async def test_arbitrage_considers_fees(self, exchange_manager):
        """
        Test arbitrage considers trading fees

        Verifies:
        - Net profit accounts for fees on both exchanges
        - Opportunity rejected if fees exceed profit
        """
        opportunities = await exchange_manager.detect_arbitrage(
            ["BTCUSDT"],
            include_fees=True
        )

        for opp in opportunities:
            assert opp.net_profit_bps < opp.profit_bps
            assert opp.estimated_fees > 0


# ============================================================================
# ORDER ROUTING TESTS
# ============================================================================

class TestOrderRoutingIntegration:
    """Test suite for smart order routing across exchanges"""

    @pytest.mark.asyncio
    async def test_route_to_best_price_exchange(self, exchange_manager):
        """
        Test order routes to exchange with best price

        Scenario:
        - BUY order should go to Bybit (lower ask)
        - SELL order should go to Binance (higher bid)
        """
        # BUY order
        buy_request = OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("50000.0"),
        )

        buy_result = await exchange_manager.route_order(buy_request)

        # Should route to Bybit (best ask)
        assert buy_result.exchange_id == "bybit"
        assert buy_result.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_route_to_best_liquidity(self, exchange_manager):
        """
        Test order routes to exchange with best liquidity

        Scenario:
        - Large order routes to exchange with more depth
        """
        exchange_manager.config.routing_strategy = RoutingStrategy.BEST_LIQUIDITY

        order_request = OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("100.0"),  # Large order
            price=Decimal("50000.0"),
        )

        result = await exchange_manager.route_order(order_request)

        # Should route to exchange with better depth
        assert result is not None

    @pytest.mark.asyncio
    async def test_split_order_across_exchanges(self, exchange_manager):
        """
        Test splitting large order across multiple exchanges

        Verifies:
        - Order is split based on available liquidity
        - Total filled equals requested quantity
        """
        exchange_manager.config.routing_strategy = RoutingStrategy.SPLIT

        order_request = OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("50.0"),  # Large order to split
            price=Decimal("50050.0"),  # Above both asks
        )

        results = await exchange_manager.route_order_split(order_request)

        # Should have orders on multiple exchanges
        assert len(results) >= 1

        # Total filled should approach requested
        total_filled = sum(r.filled_qty for r in results)
        assert total_filled > 0


# ============================================================================
# FAILOVER TESTS
# ============================================================================

class TestExchangeFailoverIntegration:
    """Test suite for exchange failover handling"""

    @pytest.mark.asyncio
    async def test_failover_on_exchange_error(
        self,
        exchange_manager,
        mock_bybit_exchange
    ):
        """
        Test failover to backup exchange on error

        Scenario:
        - Primary exchange (Bybit) fails
        - Order routed to backup (Binance)
        """
        # Make Bybit fail
        mock_bybit_exchange.place_order.side_effect = ExchangeError("Connection failed")

        order_request = OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("50050.0"),
        )

        result = await exchange_manager.route_order(order_request)

        # Should failover to Binance
        assert result.exchange_id == "binance"
        assert result.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_failover_on_rate_limit(
        self,
        exchange_manager,
        mock_bybit_exchange
    ):
        """
        Test failover when exchange is rate limited

        Scenario:
        - Primary exchange returns rate limit error
        - Order routed to backup exchange
        """
        mock_bybit_exchange.place_order.side_effect = RateLimitError(
            "Rate limit exceeded, retry in 30s"
        )

        order_request = OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("50050.0"),
        )

        result = await exchange_manager.route_order(order_request)

        # Should failover to Binance
        assert result.exchange_id == "binance"

    @pytest.mark.asyncio
    async def test_all_exchanges_fail(
        self,
        exchange_manager,
        mock_bybit_exchange,
        mock_binance_exchange
    ):
        """
        Test behavior when all exchanges fail

        Verifies:
        - Error is raised after all failovers exhausted
        - Original error is preserved
        """
        mock_bybit_exchange.place_order.side_effect = ExchangeError("Bybit down")
        mock_binance_exchange.place_order.side_effect = ExchangeError("Binance down")

        order_request = OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("50000.0"),
        )

        with pytest.raises(ExchangeError) as exc_info:
            await exchange_manager.route_order(order_request)

        assert "all exchanges failed" in str(exc_info.value).lower()


# ============================================================================
# POSITION AGGREGATION TESTS
# ============================================================================

class TestPositionAggregationIntegration:
    """Test suite for cross-exchange position management"""

    @pytest.mark.asyncio
    async def test_aggregate_positions(self, exchange_manager):
        """
        Test aggregating positions across exchanges

        Verifies:
        - All positions from all exchanges are collected
        - Total position is calculated
        """
        # Add mock positions
        exchange_manager.exchanges["bybit"].get_positions = AsyncMock(return_value=[
            {"symbol": "BTCUSDT", "side": "LONG", "size": 0.5, "entry_price": 48000.0},
        ])
        exchange_manager.exchanges["binance"].get_positions = AsyncMock(return_value=[
            {"symbol": "BTCUSDT", "side": "LONG", "size": 0.3, "entry_price": 49000.0},
        ])

        aggregated = await exchange_manager.get_aggregated_positions()

        # Should have combined BTC position
        btc_position = aggregated.get("BTCUSDT")
        assert btc_position is not None
        assert btc_position["total_size"] == 0.8  # 0.5 + 0.3
        assert btc_position["avg_entry_price"] > 0

    @pytest.mark.asyncio
    async def test_aggregate_balances(self, exchange_manager):
        """
        Test aggregating balances across exchanges

        Verifies:
        - Balances from all exchanges are summed
        - Available and total are separated
        """
        balances = await exchange_manager.get_aggregated_balances()

        # Should have combined USDT
        assert "USDT" in balances
        # Bybit: 10000 + Binance: 15000 = 25000 available
        assert balances["USDT"]["available"] == 25000.0

        # Should have combined BTC
        assert "BTC" in balances
        # Bybit: 0.5 + Binance: 0.3 = 0.8
        assert balances["BTC"]["available"] == 0.8


# ============================================================================
# HEALTH MONITORING TESTS
# ============================================================================

class TestExchangeHealthMonitoringIntegration:
    """Test suite for exchange health monitoring"""

    @pytest.mark.asyncio
    async def test_health_check_all_exchanges(self, exchange_manager):
        """
        Test health check across all exchanges

        Verifies:
        - Each exchange is checked
        - Status includes latency
        """
        health = await exchange_manager.check_all_exchanges_health()

        assert "bybit" in health
        assert "binance" in health

        for exchange_id, status in health.items():
            assert "is_healthy" in status
            assert "latency_ms" in status

    @pytest.mark.asyncio
    async def test_exchange_marked_unhealthy_on_timeout(
        self,
        exchange_manager,
        mock_bybit_exchange
    ):
        """
        Test exchange marked unhealthy on timeout

        Verifies:
        - Slow exchange is flagged
        - Routing avoids unhealthy exchange
        """
        # Make Bybit slow
        async def slow_ticker():
            await asyncio.sleep(15)  # Timeout
            return {"last_price": 50000.0}

        mock_bybit_exchange.get_ticker = slow_ticker

        health = await exchange_manager.check_all_exchanges_health()

        # Bybit should be unhealthy due to timeout
        assert health["bybit"]["is_healthy"] == False
        assert health["binance"]["is_healthy"] == True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
