"""
Test Suite for Multi-Exchange Support (Phase 6 Extended)
Purpose: Tests for Binance, Kraken, Coinbase adapters, Router, and Manager

Test Coverage:
- Exchange adapters (Binance, Kraken, Coinbase)
- ExchangeRouter smart routing
- ExchangeManager lifecycle and failover
- Cross-exchange operations

Created: 2025-12-11
Author: Backend Developer Agent
"""

import asyncio
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

# Import module under test
from app.exchanges import (
    # Base
    ExchangeName,
    ProductType,
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce,
    ExchangeConfig,
    ExchangeCapabilities,
    UnifiedOrder,
    AccountBalance,
    AssetBalance,
    UnifiedPosition,
    PositionSide,
    Ticker,
    OrderBook,
    OrderBookLevel,
    ExchangeInterface,

    # Adapters
    BinanceExchangeAdapter,
    KrakenExchangeAdapter,
    CoinbaseExchangeAdapter,
    create_binance_adapter,
    create_kraken_adapter,
    create_coinbase_adapter,

    # Error mapping
    map_binance_error,
    map_kraken_error,
    map_coinbase_error,

    # Router
    ExchangeRouter,
    RoutingConfig,
    RoutingStrategy,
    RoutingPriority,
    RoutingDecision,
    ExchangeMetrics,
    ExchangeLiquidity,

    # Manager
    ExchangeManager,
    ManagerConfig,
    HealthCheckConfig,
    FailoverConfig,
    ConnectionState,
    ExchangeStatus,
    PortfolioSummary,

    # Errors
    AuthenticationError,
    RateLimitError,
    InsufficientBalanceError,
    OrderNotFoundError,
    ValidationError,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def binance_config():
    """Create test Binance config"""
    return ExchangeConfig(
        exchange=ExchangeName.BINANCE,
        api_key="test_binance_key",
        api_secret="test_binance_secret",
        testnet=True
    )


@pytest.fixture
def kraken_config():
    """Create test Kraken config"""
    return ExchangeConfig(
        exchange=ExchangeName.KRAKEN,
        api_key="test_kraken_key",
        api_secret="dGVzdF9rcmFrZW5fc2VjcmV0",  # Base64 encoded
        testnet=False
    )


@pytest.fixture
def coinbase_config():
    """Create test Coinbase config"""
    return ExchangeConfig(
        exchange=ExchangeName.COINBASE,
        api_key="test_coinbase_key",
        api_secret="-----BEGIN EC PRIVATE KEY-----\ntest\n-----END EC PRIVATE KEY-----",
        testnet=True
    )


@pytest.fixture
def unified_order():
    """Create test unified order"""
    return UnifiedOrder(
        exchange=ExchangeName.BYBIT,
        symbol="BTCUSDT",
        product_type=ProductType.LINEAR,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.001"),
        time_in_force=TimeInForce.GTC
    )


@pytest.fixture
def mock_http_client():
    """Create mock HTTP client"""
    client = AsyncMock()
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.delete = AsyncMock()
    client.request = AsyncMock()
    client.aclose = AsyncMock()
    return client


# ============================================================================
# BINANCE ADAPTER TESTS
# ============================================================================

class TestBinanceAdapter:
    """Test BinanceExchangeAdapter"""

    def test_adapter_creation(self, binance_config):
        """Test adapter creation"""
        adapter = BinanceExchangeAdapter(binance_config)

        assert adapter.exchange_name == ExchangeName.BINANCE
        assert adapter.is_testnet is True
        assert adapter.is_initialized is False

    def test_adapter_capabilities(self, binance_config):
        """Test Binance capabilities"""
        adapter = BinanceExchangeAdapter(binance_config)

        caps = adapter.capabilities
        assert caps.spot_trading is True
        assert caps.perpetual_trading is True
        assert caps.margin_trading is True
        assert caps.market_orders is True
        assert caps.limit_orders is True
        assert caps.stop_orders is True
        assert caps.max_leverage == 125

    def test_order_to_binance_market(self, binance_config, unified_order):
        """Test market order conversion"""
        adapter = BinanceExchangeAdapter(binance_config)

        params = adapter._order_to_binance(unified_order)

        assert params["symbol"] == "BTCUSDT"
        assert params["side"] == "BUY"
        assert params["type"] == "MARKET"
        assert params["quantity"] == "0.001"

    def test_order_to_binance_limit(self, binance_config):
        """Test limit order conversion"""
        adapter = BinanceExchangeAdapter(binance_config)

        order = UnifiedOrder(
            exchange=ExchangeName.BINANCE,
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.001"),
            price=Decimal("50000"),
            time_in_force=TimeInForce.GTC
        )

        params = adapter._order_to_binance(order)

        assert params["type"] == "LIMIT"
        assert params["price"] == "50000"
        assert params["timeInForce"] == "GTC"

    def test_map_order_status(self, binance_config):
        """Test order status mapping"""
        adapter = BinanceExchangeAdapter(binance_config)

        assert adapter._map_order_status("NEW") == OrderStatus.NEW
        assert adapter._map_order_status("FILLED") == OrderStatus.FILLED
        assert adapter._map_order_status("CANCELED") == OrderStatus.CANCELLED
        assert adapter._map_order_status("EXPIRED") == OrderStatus.EXPIRED

    def test_binance_url_selection(self, binance_config):
        """Test correct URL selection"""
        # Testnet futures
        adapter = BinanceExchangeAdapter(binance_config, futures_mode=True)
        assert "testnet" in adapter._base_url

        # Mainnet
        binance_config.testnet = False
        adapter = BinanceExchangeAdapter(binance_config, futures_mode=True)
        assert "fapi" in adapter._base_url

    @pytest.mark.asyncio
    async def test_adapter_close(self, binance_config, mock_http_client):
        """Test adapter close"""
        adapter = BinanceExchangeAdapter(binance_config)
        adapter._client = mock_http_client

        await adapter.close()

        mock_http_client.aclose.assert_called_once()
        assert adapter.is_initialized is False


class TestBinanceErrorMapping:
    """Test Binance error mapping"""

    def test_map_rate_limit_error(self):
        """Test rate limit error mapping"""
        error = map_binance_error(-1003, "Too many requests")
        assert isinstance(error, RateLimitError)
        assert error.exchange == "binance"

    def test_map_auth_error(self):
        """Test authentication error mapping"""
        error = map_binance_error(-2015, "Invalid API key")
        assert isinstance(error, AuthenticationError)

    def test_map_balance_error(self):
        """Test balance error mapping"""
        error = map_binance_error(-2018, "Balance insufficient")
        assert isinstance(error, InsufficientBalanceError)

    def test_map_order_not_found(self):
        """Test order not found mapping"""
        error = map_binance_error(-2013, "Order does not exist")
        assert isinstance(error, OrderNotFoundError)


# ============================================================================
# KRAKEN ADAPTER TESTS
# ============================================================================

class TestKrakenAdapter:
    """Test KrakenExchangeAdapter"""

    def test_adapter_creation(self, kraken_config):
        """Test adapter creation"""
        adapter = KrakenExchangeAdapter(kraken_config)

        assert adapter.exchange_name == ExchangeName.KRAKEN
        assert adapter.is_initialized is False

    def test_adapter_capabilities(self, kraken_config):
        """Test Kraken capabilities"""
        adapter = KrakenExchangeAdapter(kraken_config)

        caps = adapter.capabilities
        assert caps.spot_trading is True
        assert caps.margin_trading is True
        assert caps.market_orders is True
        assert caps.limit_orders is True
        assert caps.max_leverage == 5

    def test_symbol_conversion(self):
        """Test Kraken symbol conversion"""
        from app.exchanges.kraken import to_kraken_symbol, from_kraken_symbol

        assert to_kraken_symbol("BTCUSD") == "XXBTZUSD"
        assert to_kraken_symbol("ETHUSD") == "XETHZUSD"
        assert from_kraken_symbol("XXBTZUSD") == "BTCUSD"

    def test_order_to_kraken(self, kraken_config):
        """Test order conversion to Kraken format"""
        adapter = KrakenExchangeAdapter(kraken_config)

        order = UnifiedOrder(
            exchange=ExchangeName.KRAKEN,
            symbol="BTCUSD",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal("50000")
        )

        params = adapter._order_to_kraken(order)

        assert params["type"] == "buy"
        assert params["ordertype"] == "limit"
        assert params["volume"] == "0.01"
        assert params["price"] == "50000"

    @pytest.mark.asyncio
    async def test_adapter_close(self, kraken_config, mock_http_client):
        """Test adapter close"""
        adapter = KrakenExchangeAdapter(kraken_config)
        adapter._client = mock_http_client

        await adapter.close()

        mock_http_client.aclose.assert_called_once()


class TestKrakenErrorMapping:
    """Test Kraken error mapping"""

    def test_map_rate_limit(self):
        """Test rate limit error"""
        error = map_kraken_error("EAPI:Rate limit exceeded")
        assert isinstance(error, RateLimitError)

    def test_map_auth_error(self):
        """Test auth error"""
        error = map_kraken_error("EAPI:Invalid key")
        assert isinstance(error, AuthenticationError)

    def test_map_balance_error(self):
        """Test balance error"""
        error = map_kraken_error("EOrder:Insufficient funds")
        assert isinstance(error, InsufficientBalanceError)


# ============================================================================
# COINBASE ADAPTER TESTS
# ============================================================================

class TestCoinbaseAdapter:
    """Test CoinbaseExchangeAdapter"""

    def test_adapter_creation(self, coinbase_config):
        """Test adapter creation"""
        adapter = CoinbaseExchangeAdapter(coinbase_config)

        assert adapter.exchange_name == ExchangeName.COINBASE
        assert adapter.is_testnet is True
        assert adapter.is_initialized is False

    def test_adapter_capabilities(self, coinbase_config):
        """Test Coinbase capabilities"""
        adapter = CoinbaseExchangeAdapter(coinbase_config)

        caps = adapter.capabilities
        assert caps.spot_trading is True
        assert caps.perpetual_trading is False  # Coinbase is spot only
        assert caps.market_orders is True
        assert caps.limit_orders is True
        assert caps.max_leverage == 1

    def test_symbol_conversion(self, coinbase_config):
        """Test symbol conversion"""
        adapter = CoinbaseExchangeAdapter(coinbase_config)

        assert adapter._to_coinbase_symbol("BTCUSDT") == "BTC-USD"
        assert adapter._to_coinbase_symbol("ETHUSD") == "ETH-USD"
        assert adapter._from_coinbase_symbol("BTC-USD") == "BTCUSD"

    @pytest.mark.asyncio
    async def test_adapter_close(self, coinbase_config, mock_http_client):
        """Test adapter close"""
        adapter = CoinbaseExchangeAdapter(coinbase_config)
        adapter._client = mock_http_client

        await adapter.close()

        mock_http_client.aclose.assert_called_once()


# ============================================================================
# EXCHANGE ROUTER TESTS
# ============================================================================

class TestExchangeRouter:
    """Test ExchangeRouter"""

    @pytest.fixture
    def mock_adapter(self):
        """Create mock exchange adapter"""
        adapter = AsyncMock(spec=ExchangeInterface)
        adapter.exchange_name = ExchangeName.BYBIT
        adapter.capabilities = ExchangeCapabilities(
            spot_trading=True,
            perpetual_trading=True
        )
        adapter.health_check = AsyncMock(return_value=True)
        adapter.get_orderbook = AsyncMock(return_value=OrderBook(
            exchange=ExchangeName.BYBIT,
            symbol="BTCUSDT",
            bids=[
                OrderBookLevel(price=Decimal("49990"), quantity=Decimal("10")),
                OrderBookLevel(price=Decimal("49980"), quantity=Decimal("20")),
            ],
            asks=[
                OrderBookLevel(price=Decimal("50010"), quantity=Decimal("10")),
                OrderBookLevel(price=Decimal("50020"), quantity=Decimal("20")),
            ]
        ))
        return adapter

    def test_router_creation(self):
        """Test router creation"""
        router = ExchangeRouter()

        assert router.config.strategy == RoutingStrategy.SMART
        assert len(router.get_available_exchanges()) == 0

    def test_router_with_config(self):
        """Test router with custom config"""
        config = RoutingConfig(
            strategy=RoutingStrategy.BEST_PRICE,
            max_spread_bps=30.0,
            split_threshold=50000.0
        )
        router = ExchangeRouter(config)

        assert router.config.strategy == RoutingStrategy.BEST_PRICE
        assert router.config.max_spread_bps == 30.0

    def test_register_exchange(self, mock_adapter):
        """Test exchange registration"""
        router = ExchangeRouter()

        router.register_exchange(mock_adapter)

        assert ExchangeName.BYBIT in router.get_available_exchanges()

    def test_unregister_exchange(self, mock_adapter):
        """Test exchange unregistration"""
        router = ExchangeRouter()
        router.register_exchange(mock_adapter)

        result = router.unregister_exchange(ExchangeName.BYBIT)

        assert result is True
        assert ExchangeName.BYBIT not in router.get_available_exchanges()

    @pytest.mark.asyncio
    async def test_route_order_no_exchanges(self, unified_order):
        """Test routing with no exchanges raises error"""
        router = ExchangeRouter()

        with pytest.raises(ValidationError):
            await router.route_order(unified_order)

    @pytest.mark.asyncio
    async def test_route_order_single_exchange(self, mock_adapter, unified_order):
        """Test routing with single exchange"""
        router = ExchangeRouter()
        router.register_exchange(mock_adapter)

        decision = await router.route_order(unified_order)

        assert isinstance(decision, RoutingDecision)
        assert decision.exchange == ExchangeName.BYBIT
        assert decision.score > 0

    @pytest.mark.asyncio
    async def test_get_liquidity(self, mock_adapter):
        """Test liquidity fetching"""
        router = ExchangeRouter()
        router.register_exchange(mock_adapter)

        liquidity = await router.get_liquidity("BTCUSDT")

        assert ExchangeName.BYBIT in liquidity
        assert liquidity[ExchangeName.BYBIT].bid_depth > 0
        assert liquidity[ExchangeName.BYBIT].ask_depth > 0

    @pytest.mark.asyncio
    async def test_plan_split_order(self, mock_adapter, unified_order):
        """Test order splitting"""
        router = ExchangeRouter()
        router.register_exchange(mock_adapter)

        # Make order larger
        unified_order.quantity = Decimal("10.0")

        plan = await router.plan_split_order(unified_order)

        assert plan.total_quantity == Decimal("10.0")
        assert len(plan.allocations) >= 1

    @pytest.mark.asyncio
    async def test_find_arbitrage_single_exchange(self, mock_adapter):
        """Test arbitrage with single exchange (should return empty)"""
        router = ExchangeRouter()
        router.register_exchange(mock_adapter)

        opportunities = await router.find_arbitrage("BTCUSDT")

        # Need at least 2 exchanges for arbitrage
        assert len(opportunities) == 0

    @pytest.mark.asyncio
    async def test_update_metrics(self):
        """Test metrics update"""
        router = ExchangeRouter()

        await router.update_metrics(
            ExchangeName.BYBIT,
            latency_ms=50.0,
            fill_rate=0.98
        )

        metrics = router._metrics.get(ExchangeName.BYBIT)
        assert metrics is not None
        # Latency uses exponential moving average
        assert metrics.latency_ms > 0


# ============================================================================
# EXCHANGE MANAGER TESTS
# ============================================================================

class TestExchangeManager:
    """Test ExchangeManager"""

    def test_manager_creation(self):
        """Test manager creation"""
        manager = ExchangeManager()

        assert manager.config is not None
        assert len(manager.get_healthy_exchanges()) == 0

    def test_manager_with_config(self):
        """Test manager with custom config"""
        config = ManagerConfig(
            health_check=HealthCheckConfig(
                interval_seconds=60.0,
                max_failures=5
            ),
            failover=FailoverConfig(
                enabled=True,
                primary_exchange=ExchangeName.BYBIT
            )
        )
        manager = ExchangeManager(config)

        assert manager.config.health_check.interval_seconds == 60.0
        assert manager.config.failover.primary_exchange == ExchangeName.BYBIT

    @pytest.mark.asyncio
    async def test_manager_start_stop(self):
        """Test manager start and stop"""
        manager = ExchangeManager()

        await manager.start()
        assert manager._running is True

        await manager.stop()
        assert manager._running is False

    @pytest.mark.asyncio
    async def test_get_status_empty(self):
        """Test getting status with no exchanges"""
        manager = ExchangeManager()
        await manager.start()

        status = manager.get_all_status()
        assert len(status) == 0

        await manager.stop()

    @pytest.mark.asyncio
    async def test_event_callbacks(self):
        """Test event callback registration"""
        manager = ExchangeManager()

        callback_called = False

        def on_connected(exchange):
            nonlocal callback_called
            callback_called = True

        manager.on_connected(on_connected)

        assert len(manager._callbacks["connected"]) == 1

    @pytest.mark.asyncio
    async def test_portfolio_summary_empty(self):
        """Test portfolio summary with no exchanges"""
        manager = ExchangeManager()
        await manager.start()

        portfolio = await manager.get_portfolio_summary()

        assert isinstance(portfolio, PortfolioSummary)
        assert portfolio.total_equity == Decimal("0")
        assert len(portfolio.by_exchange) == 0

        await manager.stop()

    @pytest.mark.asyncio
    async def test_calculate_risk_empty(self):
        """Test risk calculation with no positions"""
        manager = ExchangeManager()
        await manager.start()

        risk = await manager.calculate_risk()

        assert risk.total_exposure == Decimal("0")
        assert risk.risk_score == 0.0

        await manager.stop()


class TestConnectionState:
    """Test ConnectionState enum"""

    def test_connection_states(self):
        """Test all connection states exist"""
        assert ConnectionState.DISCONNECTED.value == "disconnected"
        assert ConnectionState.CONNECTING.value == "connecting"
        assert ConnectionState.CONNECTED.value == "connected"
        assert ConnectionState.RECONNECTING.value == "reconnecting"
        assert ConnectionState.FAILED.value == "failed"


class TestExchangeStatus:
    """Test ExchangeStatus dataclass"""

    def test_status_creation(self):
        """Test status creation"""
        status = ExchangeStatus(exchange=ExchangeName.BYBIT)

        assert status.exchange == ExchangeName.BYBIT
        assert status.state == ConnectionState.DISCONNECTED
        assert status.is_healthy is False
        assert status.error_count == 0

    def test_status_uptime(self):
        """Test uptime calculation"""
        status = ExchangeStatus(
            exchange=ExchangeName.BYBIT,
            state=ConnectionState.CONNECTED,
            connected_at=datetime.now(timezone.utc)
        )

        # Just connected, should be very small
        assert status.uptime_seconds >= 0
        assert status.uptime_seconds < 1


# ============================================================================
# ROUTING STRATEGY TESTS
# ============================================================================

class TestRoutingStrategies:
    """Test different routing strategies"""

    @pytest.fixture
    def router_with_exchanges(self):
        """Create router with mock exchanges"""
        router = ExchangeRouter()

        # Mock Bybit adapter
        bybit = AsyncMock(spec=ExchangeInterface)
        bybit.exchange_name = ExchangeName.BYBIT
        bybit.capabilities = ExchangeCapabilities()
        bybit.health_check = AsyncMock(return_value=True)
        bybit.get_orderbook = AsyncMock(return_value=OrderBook(
            exchange=ExchangeName.BYBIT,
            symbol="BTCUSDT",
            bids=[OrderBookLevel(price=Decimal("49990"), quantity=Decimal("100"))],
            asks=[OrderBookLevel(price=Decimal("50010"), quantity=Decimal("100"))]
        ))

        # Mock Binance adapter
        binance = AsyncMock(spec=ExchangeInterface)
        binance.exchange_name = ExchangeName.BINANCE
        binance.capabilities = ExchangeCapabilities()
        binance.health_check = AsyncMock(return_value=True)
        binance.get_orderbook = AsyncMock(return_value=OrderBook(
            exchange=ExchangeName.BINANCE,
            symbol="BTCUSDT",
            bids=[OrderBookLevel(price=Decimal("49995"), quantity=Decimal("200"))],
            asks=[OrderBookLevel(price=Decimal("50005"), quantity=Decimal("200"))]
        ))

        router.register_exchange(bybit)
        router.register_exchange(binance)

        # Set metrics
        router._metrics[ExchangeName.BYBIT] = ExchangeMetrics(
            exchange=ExchangeName.BYBIT,
            latency_ms=50.0,
            fee_taker=Decimal("0.0006")
        )
        router._metrics[ExchangeName.BINANCE] = ExchangeMetrics(
            exchange=ExchangeName.BINANCE,
            latency_ms=30.0,
            fee_taker=Decimal("0.0004")
        )

        return router

    @pytest.mark.asyncio
    async def test_best_price_strategy(self, router_with_exchanges, unified_order):
        """Test best price routing"""
        decision = await router_with_exchanges.route_order(
            unified_order,
            strategy=RoutingStrategy.BEST_PRICE
        )

        assert decision is not None
        assert decision.exchange in [ExchangeName.BYBIT, ExchangeName.BINANCE]

    @pytest.mark.asyncio
    async def test_lowest_fee_strategy(self, router_with_exchanges, unified_order):
        """Test lowest fee routing"""
        decision = await router_with_exchanges.route_order(
            unified_order,
            strategy=RoutingStrategy.LOWEST_FEE
        )

        # Binance has lower fee in mock
        assert decision.exchange == ExchangeName.BINANCE

    @pytest.mark.asyncio
    async def test_lowest_latency_strategy(self, router_with_exchanges, unified_order):
        """Test lowest latency routing"""
        decision = await router_with_exchanges.route_order(
            unified_order,
            strategy=RoutingStrategy.LOWEST_LATENCY
        )

        # Binance has lower latency in mock
        assert decision.exchange == ExchangeName.BINANCE

    @pytest.mark.asyncio
    async def test_smart_strategy(self, router_with_exchanges, unified_order):
        """Test smart (balanced) routing"""
        decision = await router_with_exchanges.route_order(
            unified_order,
            strategy=RoutingStrategy.SMART
        )

        assert decision is not None
        assert len(decision.reasons) > 0


# ============================================================================
# INTEGRATION TESTS (MOCKED)
# ============================================================================

class TestMultiExchangeIntegration:
    """Integration tests with mocked APIs"""

    @pytest.mark.asyncio
    async def test_full_order_flow_with_routing(self):
        """Test complete order flow with routing"""
        # Create manager
        manager = ExchangeManager()
        await manager.start()

        # Mock the factory to avoid real API calls
        with patch.object(manager, '_factory') as mock_factory:
            # Create mock adapter
            mock_adapter = AsyncMock(spec=ExchangeInterface)
            mock_adapter.exchange_name = ExchangeName.BYBIT
            mock_adapter.capabilities = ExchangeCapabilities()
            mock_adapter.is_initialized = True
            mock_adapter.health_check = AsyncMock(return_value=True)
            mock_adapter.get_balance = AsyncMock(return_value=AccountBalance(
                exchange=ExchangeName.BYBIT,
                total_equity=Decimal("10000"),
                available_balance=Decimal("8000")
            ))
            mock_adapter.get_positions = AsyncMock(return_value=[])
            mock_adapter.place_order = AsyncMock(return_value=UnifiedOrder(
                exchange=ExchangeName.BYBIT,
                exchange_order_id="test-123",
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=Decimal("0.001"),
                status=OrderStatus.FILLED
            ))
            mock_adapter.get_orderbook = AsyncMock(return_value=OrderBook(
                exchange=ExchangeName.BYBIT,
                symbol="BTCUSDT",
                bids=[OrderBookLevel(price=Decimal("50000"), quantity=Decimal("100"))],
                asks=[OrderBookLevel(price=Decimal("50010"), quantity=Decimal("100"))]
            ))

            mock_factory.create = AsyncMock(return_value=mock_adapter)

            # Add exchange
            manager._adapters[ExchangeName.BYBIT] = mock_adapter
            manager._status[ExchangeName.BYBIT] = ExchangeStatus(
                exchange=ExchangeName.BYBIT,
                state=ConnectionState.CONNECTED,
                is_healthy=True
            )
            manager._current_primary = ExchangeName.BYBIT

            # Register with router
            manager._router = ExchangeRouter()
            manager._router.register_exchange(mock_adapter)

            # Create order
            order = UnifiedOrder(
                exchange=ExchangeName.BYBIT,
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=Decimal("0.001")
            )

            # Route order
            decision = await manager.route_order(order)
            assert decision is not None

            # Execute order
            result = await manager.execute_order(order)
            assert result.status == OrderStatus.FILLED

            # Get portfolio
            portfolio = await manager.get_portfolio_summary()
            assert portfolio.total_equity == Decimal("10000")

        await manager.stop()


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
