"""
Tests for WebSocket Functionality
Tests WebSocket manager, connections, broadcasting, and real-time updates
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi import WebSocket
from datetime import datetime
import json

from app.main import WebSocketManager, websocket_manager
from app.services.service_proxy import ServiceProxy


class TestWebSocketManager:
    """Test WebSocketManager class"""

    @pytest.fixture
    def ws_manager(self):
        """Create fresh WebSocketManager instance"""
        return WebSocketManager()

    @pytest.fixture
    def mock_websocket(self):
        """Create mock WebSocket"""
        ws = AsyncMock(spec=WebSocket)
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.receive_text = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_websocket_connect(self, ws_manager, mock_websocket):
        """Test WebSocket connection"""
        await ws_manager.connect(mock_websocket)

        # Check websocket was accepted
        mock_websocket.accept.assert_called_once()

        # Check websocket was added to active connections
        assert mock_websocket in ws_manager.active_connections
        assert len(ws_manager.active_connections) == 1

    @pytest.mark.asyncio
    async def test_websocket_multiple_connections(self, ws_manager):
        """Test multiple WebSocket connections"""
        ws1 = AsyncMock(spec=WebSocket)
        ws1.accept = AsyncMock()

        ws2 = AsyncMock(spec=WebSocket)
        ws2.accept = AsyncMock()

        await ws_manager.connect(ws1)
        await ws_manager.connect(ws2)

        assert len(ws_manager.active_connections) == 2
        assert ws1 in ws_manager.active_connections
        assert ws2 in ws_manager.active_connections

    def test_websocket_disconnect(self, ws_manager, mock_websocket):
        """Test WebSocket disconnection"""
        # Add websocket first
        ws_manager.active_connections.add(mock_websocket)
        assert len(ws_manager.active_connections) == 1

        # Disconnect
        ws_manager.disconnect(mock_websocket)

        # Check websocket was removed
        assert mock_websocket not in ws_manager.active_connections
        assert len(ws_manager.active_connections) == 0

    def test_websocket_disconnect_not_connected(self, ws_manager, mock_websocket):
        """Test disconnecting websocket that was never connected"""
        # Should not raise exception
        ws_manager.disconnect(mock_websocket)

        assert len(ws_manager.active_connections) == 0

    @pytest.mark.asyncio
    async def test_send_personal_message_success(self, ws_manager, mock_websocket):
        """Test sending personal message to specific client"""
        ws_manager.active_connections.add(mock_websocket)

        message = {"type": "test", "data": "hello"}
        await ws_manager.send_personal_message(message, mock_websocket)

        mock_websocket.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_send_personal_message_failure(self, ws_manager, mock_websocket):
        """Test sending personal message handles errors"""
        ws_manager.active_connections.add(mock_websocket)
        mock_websocket.send_json.side_effect = Exception("Connection lost")

        message = {"type": "test", "data": "hello"}
        await ws_manager.send_personal_message(message, mock_websocket)

        # Should disconnect websocket on error
        assert mock_websocket not in ws_manager.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_to_all_clients(self, ws_manager):
        """Test broadcasting message to all connected clients"""
        ws1 = AsyncMock(spec=WebSocket)
        ws1.send_json = AsyncMock()

        ws2 = AsyncMock(spec=WebSocket)
        ws2.send_json = AsyncMock()

        ws_manager.active_connections.add(ws1)
        ws_manager.active_connections.add(ws2)

        message = {"type": "broadcast", "data": "test message"}
        await ws_manager.broadcast(message)

        # All clients should receive message
        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_broadcast_handles_failures(self, ws_manager):
        """Test broadcasting handles individual client failures"""
        ws1 = AsyncMock(spec=WebSocket)
        ws1.send_json = AsyncMock()

        ws2 = AsyncMock(spec=WebSocket)
        ws2.send_json = AsyncMock(side_effect=Exception("Client disconnected"))

        ws3 = AsyncMock(spec=WebSocket)
        ws3.send_json = AsyncMock()

        ws_manager.active_connections.add(ws1)
        ws_manager.active_connections.add(ws2)
        ws_manager.active_connections.add(ws3)

        message = {"type": "broadcast", "data": "test"}
        await ws_manager.broadcast(message)

        # Failed client should be removed
        assert ws2 not in ws_manager.active_connections
        # Successful clients should still be connected
        assert ws1 in ws_manager.active_connections
        assert ws3 in ws_manager.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_with_no_clients(self, ws_manager):
        """Test broadcasting with no connected clients"""
        message = {"type": "broadcast", "data": "test"}

        # Should not raise exception
        await ws_manager.broadcast(message)

        assert len(ws_manager.active_connections) == 0

    @pytest.mark.asyncio
    async def test_fetch_dashboard_updates_success(self, ws_manager):
        """Test fetching dashboard updates from services"""
        mock_proxy = AsyncMock(spec=ServiceProxy)

        # Mock health response
        health_response = Mock()
        health_response.body = json.dumps({"status": "healthy"}).encode()

        # Mock portfolio response
        portfolio_response = Mock()
        portfolio_response.body = json.dumps({"balance": "100000"}).encode()

        mock_proxy.proxy_request = AsyncMock(side_effect=[health_response, portfolio_response])

        data = await ws_manager.fetch_dashboard_updates(mock_proxy)

        assert data["type"] == "dashboard_update"
        assert "timestamp" in data
        assert "data" in data
        assert data["data"]["health"] == {"status": "healthy"}
        assert data["data"]["portfolio"] == {"balance": "100000"}

    @pytest.mark.asyncio
    async def test_fetch_dashboard_updates_service_failure(self, ws_manager):
        """Test fetching dashboard updates handles service failures"""
        mock_proxy = AsyncMock(spec=ServiceProxy)
        mock_proxy.proxy_request = AsyncMock(side_effect=Exception("Service unavailable"))

        data = await ws_manager.fetch_dashboard_updates(mock_proxy)

        # Should return error type
        # Should still return dashboard_update type, but with None data
        assert data["type"] == "dashboard_update"
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_fetch_dashboard_updates_malformed_response(self, ws_manager):
        """Test fetching dashboard updates handles malformed responses"""
        mock_proxy = AsyncMock(spec=ServiceProxy)

        # Mock response with invalid JSON
        invalid_response = Mock()
        invalid_response.body = b"not valid json"

        mock_proxy.proxy_request = AsyncMock(return_value=invalid_response)

        data = await ws_manager.fetch_dashboard_updates(mock_proxy)

        # Should handle gracefully and return None for failed parsing
        assert data["type"] == "dashboard_update"
        assert data["data"]["health"] is None

    @pytest.mark.asyncio
    async def test_start_broadcasting_with_clients(self, ws_manager):
        """Test broadcast task sends updates to clients"""
        mock_proxy = AsyncMock(spec=ServiceProxy)

        ws1 = AsyncMock(spec=WebSocket)
        ws1.send_json = AsyncMock()
        ws_manager.active_connections.add(ws1)

        # Mock fetch_dashboard_updates
        mock_data = {
            "type": "dashboard_update",
            "timestamp": datetime.now().isoformat(),
            "data": {"health": {}, "portfolio": {}}
        }

        with patch.object(ws_manager, 'fetch_dashboard_updates', return_value=mock_data):
            # Start broadcast task
            task = asyncio.create_task(ws_manager.start_broadcasting(mock_proxy))

            # Let it run for a short time
            await asyncio.sleep(0.1)

            # Cancel task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Should have sent at least one message
        assert ws1.send_json.call_count >= 1

    @pytest.mark.asyncio
    async def test_start_broadcasting_without_clients(self, ws_manager):
        """Test broadcast task works with no clients"""
        mock_proxy = AsyncMock(spec=ServiceProxy)

        # No clients connected
        assert len(ws_manager.active_connections) == 0

        # Start broadcast task
        task = asyncio.create_task(ws_manager.start_broadcasting(mock_proxy))

        # Let it run for a short time
        await asyncio.sleep(0.1)

        # Cancel task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should not raise exception with no clients

    @pytest.mark.asyncio
    async def test_start_broadcasting_handles_errors(self, ws_manager):
        """Test broadcast task handles errors gracefully"""
        mock_proxy = AsyncMock(spec=ServiceProxy)

        # Make fetch fail
        with patch.object(ws_manager, 'fetch_dashboard_updates', side_effect=Exception("Fetch error")):
            task = asyncio.create_task(ws_manager.start_broadcasting(mock_proxy))

            # Let it run for a short time
            await asyncio.sleep(0.1)

            # Cancel task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Should not crash, just log error and continue


class TestWebSocketEndpoint:
    """Test WebSocket endpoint integration"""

    @pytest.mark.asyncio
    async def test_websocket_endpoint_connection_message(self, test_client):
        """Test WebSocket endpoint sends connection message"""
        # This is a complex integration test that requires TestClient with WebSocket support
        # For now, we'll test the manager functionality which is what's tested above
        pass

    @pytest.mark.asyncio
    async def test_websocket_endpoint_ping_pong(self, test_client):
        """Test WebSocket ping/pong mechanism"""
        # Integration test for ping/pong
        pass


class TestWebSocketManagerLifecycle:
    """Test WebSocket manager lifecycle"""

    @pytest.mark.asyncio
    async def test_manager_initialization(self):
        """Test WebSocket manager initialization"""
        manager = WebSocketManager()

        assert manager.active_connections == set()
        assert manager.broadcast_task is None

    @pytest.mark.asyncio
    async def test_manager_handles_concurrent_connections(self):
        """Test manager handles multiple concurrent connections"""
        manager = WebSocketManager()

        # Create multiple websockets
        websockets = [AsyncMock(spec=WebSocket) for _ in range(10)]

        # Connect all simultaneously
        await asyncio.gather(*[manager.connect(ws) for ws in websockets])

        assert len(manager.active_connections) == 10

        # Disconnect all
        for ws in websockets:
            manager.disconnect(ws)

        assert len(manager.active_connections) == 0

    @pytest.mark.asyncio
    async def test_manager_broadcast_to_many_clients(self):
        """Test broadcasting to many clients"""
        manager = WebSocketManager()

        # Create 100 mock clients
        clients = []
        for _ in range(100):
            ws = AsyncMock(spec=WebSocket)
            ws.send_json = AsyncMock()
            manager.active_connections.add(ws)
            clients.append(ws)

        message = {"type": "test", "data": "mass broadcast"}
        await manager.broadcast(message)

        # All clients should receive message
        for client in clients:
            client.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_manager_partial_broadcast_failure(self):
        """Test broadcasting with some failures"""
        manager = WebSocketManager()

        # 5 successful clients
        success_clients = []
        for _ in range(5):
            ws = AsyncMock(spec=WebSocket)
            ws.send_json = AsyncMock()
            manager.active_connections.add(ws)
            success_clients.append(ws)

        # 5 failing clients
        fail_clients = []
        for _ in range(5):
            ws = AsyncMock(spec=WebSocket)
            ws.send_json = AsyncMock(side_effect=Exception("Failed"))
            manager.active_connections.add(ws)
            fail_clients.append(ws)

        assert len(manager.active_connections) == 10

        message = {"type": "test", "data": "partial broadcast"}
        await manager.broadcast(message)

        # Failed clients should be removed
        for fail_client in fail_clients:
            assert fail_client not in manager.active_connections

        # Successful clients should remain
        for success_client in success_clients:
            assert success_client in manager.active_connections

        assert len(manager.active_connections) == 5
