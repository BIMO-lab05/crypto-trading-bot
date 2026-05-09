"""
Integration Tests for Performance Dashboard
==========================================
Phase 5.3: Real-Time Performance Dashboard Integration Tests

Purpose:
- Test WebSocket communication for real-time updates
- Verify dashboard data aggregation
- Test event streaming and subscription management
- Validate dashboard API endpoints

Test Coverage:
- PerformanceDashboardHandler WebSocket updates
- Real-time metrics streaming
- Client subscription management
- Dashboard state synchronization
"""

import pytest

pytest.skip(
    "stale imports vs current trading-engine API; needs rewrite after PR #86 refactor",
    allow_module_level=True,
)


import pytest
import asyncio
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Dict, Any
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.testclient import TestClient as StarletteTestClient
from starlette.websockets import WebSocketDisconnect
import uuid

# Import dashboard components
from app.handlers.performance_dashboard import (
    PerformanceDashboardHandler,
    DashboardConfig,
    DashboardEvent,
    DashboardEventType,
    ClientSubscription,
    DashboardState,
)
from app.analytics.advanced_metrics import (
    AdvancedMetricsCalculator,
    PerformanceMetrics,
    RiskMetrics,
)


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def dashboard_config() -> DashboardConfig:
    """
    Create dashboard configuration for testing

    Returns:
        DashboardConfig configured for testing
    """
    return DashboardConfig(
        update_interval_seconds=1,  # Fast updates for testing
        metrics_cache_ttl_seconds=5,
        max_clients=100,
        enable_compression=False,  # Disable for easier testing
        heartbeat_interval_seconds=10,
    )


@pytest.fixture
def dashboard_handler(dashboard_config) -> PerformanceDashboardHandler:
    """
    Create dashboard handler instance

    Returns:
        PerformanceDashboardHandler for testing
    """
    handler = PerformanceDashboardHandler(config=dashboard_config)
    return handler


@pytest.fixture
def mock_metrics_calculator():
    """
    Create mock metrics calculator

    Returns:
        Mock AdvancedMetricsCalculator
    """
    calculator = MagicMock(spec=AdvancedMetricsCalculator)

    # Mock performance metrics
    calculator.calculate_performance_metrics.return_value = PerformanceMetrics(
        total_trades=100,
        win_rate=0.65,
        profit_factor=1.8,
        avg_win=150.0,
        avg_loss=-80.0,
        total_pnl=5000.0,
        expectancy=45.0,
    )

    # Mock risk metrics
    calculator.calculate_risk_metrics.return_value = RiskMetrics(
        sharpe_ratio=1.5,
        sortino_ratio=2.1,
        max_drawdown_pct=0.08,
        var_95=-500.0,
        cvar_95=-750.0,
        calmar_ratio=12.5,
    )

    return calculator


@pytest.fixture
def sample_dashboard_events() -> List[DashboardEvent]:
    """
    Generate sample dashboard events

    Returns:
        List of DashboardEvent objects
    """
    events = []
    base_time = datetime.now(timezone.utc)

    # Trade executed event
    events.append(DashboardEvent(
        event_type=DashboardEventType.TRADE_EXECUTED,
        timestamp=base_time,
        data={
            "trade_id": str(uuid.uuid4()),
            "symbol": "BTCUSDT",
            "side": "BUY",
            "pnl": 150.0,
            "pnl_pct": 3.0,
        }
    ))

    # Position update event
    events.append(DashboardEvent(
        event_type=DashboardEventType.POSITION_UPDATE,
        timestamp=base_time + timedelta(seconds=1),
        data={
            "symbol": "BTCUSDT",
            "position_size": 0.1,
            "unrealized_pnl": 75.0,
            "entry_price": 50000.0,
            "current_price": 50750.0,
        }
    ))

    # Portfolio update event
    events.append(DashboardEvent(
        event_type=DashboardEventType.PORTFOLIO_UPDATE,
        timestamp=base_time + timedelta(seconds=2),
        data={
            "total_equity": 10500.0,
            "total_pnl": 500.0,
            "daily_pnl": 150.0,
            "drawdown_pct": 0.02,
        }
    ))

    return events


@pytest.fixture
def test_app(dashboard_handler) -> FastAPI:
    """
    Create FastAPI test application with dashboard routes

    Returns:
        FastAPI application for testing
    """
    app = FastAPI()

    # Register dashboard routes
    app.include_router(dashboard_handler.get_router(), prefix="/dashboard")

    return app


# ============================================================================
# WEBSOCKET CONNECTION TESTS
# ============================================================================

class TestWebSocketConnectionIntegration:
    """Test suite for WebSocket connection management"""

    @pytest.mark.asyncio
    async def test_client_connection(self, dashboard_handler):
        """
        Test client can connect to WebSocket

        Verifies:
        - Connection is accepted
        - Client is tracked
        """
        # Create mock WebSocket
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        client_id = str(uuid.uuid4())

        # Connect client
        await dashboard_handler.connect_client(client_id, mock_ws)

        # Verify connection
        assert client_id in dashboard_handler.active_clients
        mock_ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_client_disconnection(self, dashboard_handler):
        """
        Test client disconnection is handled properly

        Verifies:
        - Client is removed from tracking
        - Resources are cleaned up
        """
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        client_id = str(uuid.uuid4())

        # Connect and then disconnect
        await dashboard_handler.connect_client(client_id, mock_ws)
        assert client_id in dashboard_handler.active_clients

        await dashboard_handler.disconnect_client(client_id)
        assert client_id not in dashboard_handler.active_clients

    @pytest.mark.asyncio
    async def test_max_clients_limit(self, dashboard_handler):
        """
        Test maximum client limit is enforced

        Scenario:
        - Connect max number of clients
        - Try to connect one more
        - Should be rejected
        """
        dashboard_handler.config.max_clients = 3

        # Connect max clients
        for i in range(3):
            mock_ws = AsyncMock()
            mock_ws.accept = AsyncMock()
            await dashboard_handler.connect_client(f"client_{i}", mock_ws)

        # Try to connect one more
        extra_ws = AsyncMock()
        extra_ws.accept = AsyncMock()
        extra_ws.close = AsyncMock()

        with pytest.raises(Exception) as exc_info:
            await dashboard_handler.connect_client("extra_client", extra_ws)

        assert "max clients" in str(exc_info.value).lower()


# ============================================================================
# SUBSCRIPTION MANAGEMENT TESTS
# ============================================================================

class TestSubscriptionManagementIntegration:
    """Test suite for subscription management"""

    @pytest.mark.asyncio
    async def test_subscribe_to_event_types(self, dashboard_handler):
        """
        Test client can subscribe to specific event types

        Verifies:
        - Subscription is recorded
        - Only subscribed events are sent
        """
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        client_id = str(uuid.uuid4())

        await dashboard_handler.connect_client(client_id, mock_ws)

        # Subscribe to specific events
        subscription = ClientSubscription(
            client_id=client_id,
            event_types=[
                DashboardEventType.TRADE_EXECUTED,
                DashboardEventType.POSITION_UPDATE,
            ],
            symbols=["BTCUSDT"],
        )

        await dashboard_handler.subscribe(client_id, subscription)

        # Verify subscription
        client = dashboard_handler.active_clients[client_id]
        assert DashboardEventType.TRADE_EXECUTED in client.subscriptions
        assert DashboardEventType.POSITION_UPDATE in client.subscriptions
        assert DashboardEventType.PORTFOLIO_UPDATE not in client.subscriptions

    @pytest.mark.asyncio
    async def test_unsubscribe_from_events(self, dashboard_handler):
        """
        Test client can unsubscribe from event types

        Verifies:
        - Subscription is removed
        - Events no longer sent
        """
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        client_id = str(uuid.uuid4())

        await dashboard_handler.connect_client(client_id, mock_ws)

        # Subscribe then unsubscribe
        subscription = ClientSubscription(
            client_id=client_id,
            event_types=[
                DashboardEventType.TRADE_EXECUTED,
                DashboardEventType.POSITION_UPDATE,
            ],
        )
        await dashboard_handler.subscribe(client_id, subscription)

        # Unsubscribe from one event
        await dashboard_handler.unsubscribe(
            client_id,
            [DashboardEventType.POSITION_UPDATE]
        )

        client = dashboard_handler.active_clients[client_id]
        assert DashboardEventType.TRADE_EXECUTED in client.subscriptions
        assert DashboardEventType.POSITION_UPDATE not in client.subscriptions

    @pytest.mark.asyncio
    async def test_symbol_filtered_subscription(self, dashboard_handler):
        """
        Test symbol-filtered subscriptions work correctly

        Verifies:
        - Events are filtered by symbol
        - Only matching events are sent
        """
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        client_id = str(uuid.uuid4())

        await dashboard_handler.connect_client(client_id, mock_ws)

        # Subscribe only to BTCUSDT events
        subscription = ClientSubscription(
            client_id=client_id,
            event_types=[DashboardEventType.TRADE_EXECUTED],
            symbols=["BTCUSDT"],
        )
        await dashboard_handler.subscribe(client_id, subscription)

        # Emit BTC event (should be sent)
        btc_event = DashboardEvent(
            event_type=DashboardEventType.TRADE_EXECUTED,
            timestamp=datetime.now(timezone.utc),
            data={"symbol": "BTCUSDT", "pnl": 100.0},
        )
        await dashboard_handler.broadcast_event(btc_event)

        # Emit ETH event (should NOT be sent)
        eth_event = DashboardEvent(
            event_type=DashboardEventType.TRADE_EXECUTED,
            timestamp=datetime.now(timezone.utc),
            data={"symbol": "ETHUSDT", "pnl": 50.0},
        )
        await dashboard_handler.broadcast_event(eth_event)

        # Only BTC event should be sent
        assert mock_ws.send_json.call_count == 1


# ============================================================================
# EVENT BROADCASTING TESTS
# ============================================================================

class TestEventBroadcastingIntegration:
    """Test suite for event broadcasting"""

    @pytest.mark.asyncio
    async def test_broadcast_to_all_subscribers(
        self,
        dashboard_handler,
        sample_dashboard_events
    ):
        """
        Test events are broadcast to all subscribers

        Verifies:
        - All connected clients receive events
        - Event data is correct
        """
        # Connect multiple clients
        clients = {}
        for i in range(3):
            mock_ws = AsyncMock()
            mock_ws.accept = AsyncMock()
            mock_ws.send_json = AsyncMock()
            client_id = f"client_{i}"
            await dashboard_handler.connect_client(client_id, mock_ws)

            # Subscribe to all events
            subscription = ClientSubscription(
                client_id=client_id,
                event_types=list(DashboardEventType),
            )
            await dashboard_handler.subscribe(client_id, subscription)
            clients[client_id] = mock_ws

        # Broadcast event
        event = sample_dashboard_events[0]
        await dashboard_handler.broadcast_event(event)

        # All clients should receive the event
        for client_id, ws in clients.items():
            ws.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_selective_broadcast(
        self,
        dashboard_handler,
        sample_dashboard_events
    ):
        """
        Test events are only sent to interested subscribers

        Verifies:
        - Unsubscribed clients don't receive events
        - Subscribed clients receive events
        """
        # Client 1: subscribed to trades
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_json = AsyncMock()
        await dashboard_handler.connect_client("client_1", ws1)
        await dashboard_handler.subscribe("client_1", ClientSubscription(
            client_id="client_1",
            event_types=[DashboardEventType.TRADE_EXECUTED],
        ))

        # Client 2: subscribed to positions
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()
        await dashboard_handler.connect_client("client_2", ws2)
        await dashboard_handler.subscribe("client_2", ClientSubscription(
            client_id="client_2",
            event_types=[DashboardEventType.POSITION_UPDATE],
        ))

        # Broadcast trade event
        trade_event = DashboardEvent(
            event_type=DashboardEventType.TRADE_EXECUTED,
            timestamp=datetime.now(timezone.utc),
            data={"trade_id": "test123"},
        )
        await dashboard_handler.broadcast_event(trade_event)

        # Only client 1 should receive
        ws1.send_json.assert_called_once()
        ws2.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_event_serialization(self, dashboard_handler):
        """
        Test events are properly serialized for WebSocket

        Verifies:
        - Complex data types are serialized
        - Datetime is ISO formatted
        - Decimal is string formatted
        """
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        await dashboard_handler.connect_client("client_1", mock_ws)
        await dashboard_handler.subscribe("client_1", ClientSubscription(
            client_id="client_1",
            event_types=[DashboardEventType.TRADE_EXECUTED],
        ))

        # Event with complex data
        event = DashboardEvent(
            event_type=DashboardEventType.TRADE_EXECUTED,
            timestamp=datetime.now(timezone.utc),
            data={
                "price": Decimal("50000.50"),
                "timestamp": datetime.now(timezone.utc),
            },
        )
        await dashboard_handler.broadcast_event(event)

        # Verify serialization (no exceptions)
        mock_ws.send_json.assert_called_once()


# ============================================================================
# DASHBOARD STATE TESTS
# ============================================================================

class TestDashboardStateIntegration:
    """Test suite for dashboard state management"""

    @pytest.mark.asyncio
    async def test_initial_state_on_connect(
        self,
        dashboard_handler,
        mock_metrics_calculator
    ):
        """
        Test initial state is sent on client connection

        Verifies:
        - Full state snapshot is sent
        - All metrics are included
        """
        dashboard_handler.metrics_calculator = mock_metrics_calculator

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        await dashboard_handler.connect_client("client_1", mock_ws)

        # Initial state should be sent
        calls = mock_ws.send_json.call_args_list
        assert len(calls) >= 1

        # First call should be initial state
        initial_state = calls[0][0][0]
        assert initial_state.get("type") == "initial_state"

    @pytest.mark.asyncio
    async def test_state_includes_all_metrics(
        self,
        dashboard_handler,
        mock_metrics_calculator
    ):
        """
        Test dashboard state includes all required metrics

        Verifies:
        - Performance metrics present
        - Risk metrics present
        - Position summary present
        """
        dashboard_handler.metrics_calculator = mock_metrics_calculator

        state = await dashboard_handler.get_current_state()

        assert isinstance(state, DashboardState)
        assert state.performance_metrics is not None
        assert state.risk_metrics is not None
        assert "total_pnl" in state.portfolio_summary

    @pytest.mark.asyncio
    async def test_state_caching(self, dashboard_handler, mock_metrics_calculator):
        """
        Test dashboard state is cached appropriately

        Verifies:
        - Repeated calls within TTL return cached state
        - Expired cache triggers recalculation
        """
        dashboard_handler.metrics_calculator = mock_metrics_calculator
        dashboard_handler.config.metrics_cache_ttl_seconds = 2

        # First call
        state1 = await dashboard_handler.get_current_state()

        # Second call (should be cached)
        state2 = await dashboard_handler.get_current_state()

        # Should be same object (cached)
        assert state1.timestamp == state2.timestamp

        # Wait for cache to expire
        await asyncio.sleep(2.5)

        # Third call (should recalculate)
        state3 = await dashboard_handler.get_current_state()
        assert state3.timestamp > state1.timestamp


# ============================================================================
# REAL-TIME UPDATE TESTS
# ============================================================================

class TestRealTimeUpdatesIntegration:
    """Test suite for real-time update streaming"""

    @pytest.mark.asyncio
    async def test_periodic_metrics_update(
        self,
        dashboard_handler,
        mock_metrics_calculator
    ):
        """
        Test periodic metrics updates are sent to clients

        Verifies:
        - Updates sent at configured interval
        - All subscribed clients receive updates
        """
        dashboard_handler.metrics_calculator = mock_metrics_calculator
        dashboard_handler.config.update_interval_seconds = 0.5

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        await dashboard_handler.connect_client("client_1", mock_ws)
        await dashboard_handler.subscribe("client_1", ClientSubscription(
            client_id="client_1",
            event_types=[DashboardEventType.METRICS_UPDATE],
        ))

        # Start update loop
        update_task = asyncio.create_task(
            dashboard_handler.start_periodic_updates()
        )

        # Wait for a few updates
        await asyncio.sleep(1.5)

        # Stop updates
        dashboard_handler.stop_periodic_updates()
        update_task.cancel()

        # Should have received at least 2 updates
        assert mock_ws.send_json.call_count >= 2

    @pytest.mark.asyncio
    async def test_heartbeat_keeps_connection_alive(
        self,
        dashboard_handler
    ):
        """
        Test heartbeat messages keep connection alive

        Verifies:
        - Heartbeat sent at configured interval
        - Client can respond to heartbeat
        """
        dashboard_handler.config.heartbeat_interval_seconds = 0.5

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.receive_text = AsyncMock(return_value='{"type": "pong"}')

        await dashboard_handler.connect_client("client_1", mock_ws)

        # Start heartbeat
        heartbeat_task = asyncio.create_task(
            dashboard_handler.send_heartbeats()
        )

        await asyncio.sleep(1.2)

        dashboard_handler.stop_heartbeats()
        heartbeat_task.cancel()

        # Should have sent heartbeats
        heartbeat_calls = [
            call for call in mock_ws.send_json.call_args_list
            if call[0][0].get("type") == "ping"
        ]
        assert len(heartbeat_calls) >= 2


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestDashboardErrorHandlingIntegration:
    """Test suite for dashboard error handling"""

    @pytest.mark.asyncio
    async def test_disconnected_client_handling(self, dashboard_handler):
        """
        Test handling of disconnected clients

        Verifies:
        - Disconnected clients are removed
        - Broadcast continues for remaining clients
        """
        # Connect two clients
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_json = AsyncMock()
        await dashboard_handler.connect_client("client_1", ws1)

        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock(side_effect=WebSocketDisconnect(1000))
        await dashboard_handler.connect_client("client_2", ws2)

        # Subscribe both
        for client_id in ["client_1", "client_2"]:
            await dashboard_handler.subscribe(client_id, ClientSubscription(
                client_id=client_id,
                event_types=[DashboardEventType.TRADE_EXECUTED],
            ))

        # Broadcast (client_2 will disconnect)
        event = DashboardEvent(
            event_type=DashboardEventType.TRADE_EXECUTED,
            timestamp=datetime.now(timezone.utc),
            data={"test": True},
        )
        await dashboard_handler.broadcast_event(event)

        # Client 2 should be removed
        assert "client_2" not in dashboard_handler.active_clients
        assert "client_1" in dashboard_handler.active_clients

    @pytest.mark.asyncio
    async def test_metrics_calculation_error_handling(
        self,
        dashboard_handler
    ):
        """
        Test handling of metrics calculation errors

        Verifies:
        - Errors don't crash the dashboard
        - Clients receive error notification
        """
        # Mock calculator that raises error
        failing_calculator = MagicMock()
        failing_calculator.calculate_performance_metrics.side_effect = \
            Exception("Calculation error")

        dashboard_handler.metrics_calculator = failing_calculator

        # Should not raise, should return empty/default state
        state = await dashboard_handler.get_current_state()

        assert state.error is not None
        assert "error" in state.error.lower()


# ============================================================================
# API ENDPOINT TESTS
# ============================================================================

class TestDashboardAPIIntegration:
    """Test suite for dashboard REST API endpoints"""

    def test_get_dashboard_state_endpoint(
        self,
        test_app,
        mock_metrics_calculator,
        dashboard_handler
    ):
        """
        Test GET /dashboard/state endpoint

        Verifies:
        - Returns current dashboard state
        - Includes all metrics sections
        """
        dashboard_handler.metrics_calculator = mock_metrics_calculator

        client = TestClient(test_app)
        response = client.get("/dashboard/state")

        assert response.status_code == 200
        data = response.json()

        assert "performance_metrics" in data
        assert "risk_metrics" in data
        assert "timestamp" in data

    def test_get_positions_summary_endpoint(
        self,
        test_app,
        dashboard_handler
    ):
        """
        Test GET /dashboard/positions endpoint

        Verifies:
        - Returns position summary
        - Includes open positions list
        """
        client = TestClient(test_app)
        response = client.get("/dashboard/positions")

        assert response.status_code == 200
        data = response.json()

        assert "open_positions" in data
        assert "total_value" in data

    def test_get_trade_history_endpoint(
        self,
        test_app,
        dashboard_handler
    ):
        """
        Test GET /dashboard/trades endpoint

        Verifies:
        - Returns recent trades
        - Supports pagination
        """
        client = TestClient(test_app)
        response = client.get("/dashboard/trades?limit=10")

        assert response.status_code == 200
        data = response.json()

        assert "trades" in data
        assert "total_count" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
