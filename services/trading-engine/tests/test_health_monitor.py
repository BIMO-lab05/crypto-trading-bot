"""
Tests for Health Monitor Module
Purpose: Verify comprehensive health monitoring functionality

Test Coverage:
- PostgreSQL health checks
- Redis health checks
- External API health checks
- System metrics collection
- Health status aggregation
- Circuit breaker pattern
- Background monitoring
- Cached health checks
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timedelta

from app.monitoring.health import (
    HealthMonitor,
    HealthStatus,
    DependencyHealth,
    SystemHealth,
    get_health_monitor
)


class TestDependencyHealth:
    """Test DependencyHealth class"""

    def test_dependency_health_creation(self):
        """Test creating a dependency health status"""
        health = DependencyHealth(
            name="postgres",
            status=HealthStatus.HEALTHY,
            response_time_ms=15.5,
            error=None,
            details={"version": "14.5"}
        )

        assert health.name == "postgres"
        assert health.status == HealthStatus.HEALTHY
        assert health.response_time_ms == 15.5
        assert health.details["version"] == "14.5"

    def test_dependency_health_to_dict(self):
        """Test converting dependency health to dictionary"""
        health = DependencyHealth(
            name="redis",
            status=HealthStatus.DEGRADED,
            response_time_ms=75.0,
            error="High latency"
        )

        result = health.to_dict()

        assert result["name"] == "redis"
        assert result["status"] == "degraded"
        assert result["response_time_ms"] == 75.0
        assert result["error"] == "High latency"
        assert "last_check" in result


class TestSystemHealth:
    """Test SystemHealth class"""

    def test_system_health_creation(self):
        """Test creating system health status"""
        health = SystemHealth()

        assert health.status == HealthStatus.UNKNOWN
        assert len(health.dependencies) == 0

    def test_add_dependency(self):
        """Test adding dependency to system health"""
        health = SystemHealth()

        dep = DependencyHealth(
            name="postgres",
            status=HealthStatus.HEALTHY
        )

        health.add_dependency(dep)

        assert "postgres" in health.dependencies
        assert health.dependencies["postgres"].status == HealthStatus.HEALTHY

    def test_calculate_overall_status_all_healthy(self):
        """Test overall status when all dependencies are healthy"""
        health = SystemHealth()

        health.add_dependency(DependencyHealth("postgres", HealthStatus.HEALTHY))
        health.add_dependency(DependencyHealth("redis", HealthStatus.HEALTHY))

        health.calculate_overall_status()

        assert health.status == HealthStatus.HEALTHY

    def test_calculate_overall_status_one_degraded(self):
        """Test overall status when one dependency is degraded"""
        health = SystemHealth()

        health.add_dependency(DependencyHealth("postgres", HealthStatus.HEALTHY))
        health.add_dependency(DependencyHealth("redis", HealthStatus.DEGRADED))

        health.calculate_overall_status()

        assert health.status == HealthStatus.DEGRADED

    def test_calculate_overall_status_critical_unhealthy(self):
        """Test overall status when critical dependency is unhealthy"""
        health = SystemHealth()

        health.add_dependency(DependencyHealth("postgres", HealthStatus.UNHEALTHY))
        health.add_dependency(DependencyHealth("api", HealthStatus.HEALTHY))

        health.calculate_overall_status()

        assert health.status == HealthStatus.UNHEALTHY

    def test_system_health_to_dict(self):
        """Test converting system health to dictionary"""
        health = SystemHealth()
        health.add_dependency(DependencyHealth("postgres", HealthStatus.HEALTHY))
        health.metrics = {"cpu": 25.5}
        health.calculate_overall_status()

        result = health.to_dict()

        assert result["status"] == "healthy"
        assert "postgres" in result["dependencies"]
        assert result["metrics"]["cpu"] == 25.5


class TestHealthMonitor:
    """Test HealthMonitor class"""

    def test_health_monitor_initialization(self):
        """Test health monitor initialization"""
        monitor = HealthMonitor(
            check_interval=30,
            failure_threshold=3,
            timeout_seconds=5
        )

        assert monitor.check_interval == 30
        assert monitor.failure_threshold == 3
        assert monitor.timeout_seconds == 5

    @pytest.mark.asyncio
    @patch('database.connection.db_manager')
    async def test_check_database_health_success(self, mock_db_manager):
        """Test successful database health check"""
        mock_db_manager.health_check.return_value = True
        mock_db_manager.get_pool_size.return_value = 10

        monitor = HealthMonitor()
        health = await monitor.check_database_health()

        assert health.name == "postgres"
        assert health.status == HealthStatus.HEALTHY
        assert health.response_time_ms < 200  # Should be fast

    @pytest.mark.asyncio
    @patch('database.connection.db_manager')
    async def test_check_database_health_failure(self, mock_db_manager):
        """Test database health check failure"""
        mock_db_manager.health_check.side_effect = Exception("Connection failed")

        monitor = HealthMonitor()
        health = await monitor.check_database_health()

        assert health.name == "postgres"
        assert health.status == HealthStatus.UNHEALTHY
        assert "Connection failed" in health.error

    @pytest.mark.asyncio
    @patch('redis.asyncio.from_url')
    async def test_check_redis_health_success(self, mock_redis_from_url):
        """Test successful Redis health check"""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_redis.info = AsyncMock(return_value={
            "redis_version": "6.2.6",
            "connected_clients": 5,
            "used_memory_human": "1.5M",
            "uptime_in_days": 10
        })
        mock_redis.close = AsyncMock()
        mock_redis_from_url.return_value = mock_redis

        monitor = HealthMonitor()
        health = await monitor.check_redis_health("redis://localhost:6379/0")

        assert health.name == "redis"
        assert health.status == HealthStatus.HEALTHY
        assert health.details["version"] == "6.2.6"

    @pytest.mark.asyncio
    @patch('redis.asyncio.from_url')
    async def test_check_redis_health_failure(self, mock_redis_from_url):
        """Test Redis health check failure"""
        mock_redis_from_url.side_effect = Exception("Connection refused")

        monitor = HealthMonitor()
        health = await monitor.check_redis_health("redis://localhost:6379/0")

        assert health.name == "redis"
        assert health.status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
        assert "Connection refused" in health.error

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_check_external_api_health_success(self, mock_client_class):
        """Test successful external API health check"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "healthy",
            "version": "1.0.0"
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        monitor = HealthMonitor()
        health = await monitor.check_external_api_health(
            "technical_analysis",
            "http://localhost:8004/health"
        )

        assert health.name == "technical_analysis"
        assert health.status == HealthStatus.HEALTHY
        assert health.details["service_status"] == "healthy"

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_check_external_api_health_timeout(self, mock_client_class):
        """Test external API health check timeout"""
        import httpx

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_client_class.return_value = mock_client

        monitor = HealthMonitor(timeout_seconds=1)
        health = await monitor.check_external_api_health(
            "bybit_connector",
            "http://localhost:8001/health"
        )

        assert health.name == "bybit_connector"
        assert health.status == HealthStatus.UNHEALTHY
        assert "Timeout" in health.error

    def test_get_system_metrics(self):
        """Test getting system metrics"""
        monitor = HealthMonitor()
        metrics = monitor.get_system_metrics()

        # Check that metrics are present
        assert "cpu" in metrics
        assert "memory" in metrics
        assert "disk" in metrics
        assert "process" in metrics

        # Check metric structure
        assert "percent" in metrics["cpu"]
        assert "total_mb" in metrics["memory"]
        assert "used_gb" in metrics["disk"]

    @pytest.mark.asyncio
    @patch('database.connection.db_manager')
    @patch('httpx.AsyncClient')
    async def test_perform_health_check(self, mock_client_class, mock_db_manager):
        """Test comprehensive health check"""
        # Mock database
        mock_db_manager.health_check.return_value = True

        # Mock external API
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy"}

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        monitor = HealthMonitor()

        external_apis = {
            "technical_analysis": "http://localhost:8004/health"
        }

        health = await monitor.perform_health_check(
            postgres_enabled=True,
            redis_url=None,
            external_apis=external_apis
        )

        assert isinstance(health, SystemHealth)
        assert "postgres" in health.dependencies
        assert "technical_analysis" in health.dependencies
        assert health.metrics is not None

    @pytest.mark.asyncio
    async def test_cached_health_check(self):
        """Test cached health check retrieval"""
        monitor = HealthMonitor()

        # No cached result initially
        cached = await monitor.get_cached_health(max_age_seconds=30)
        assert cached is None

        # Create a health check
        health = SystemHealth()
        monitor._last_check = health
        monitor._last_check_time = datetime.now()

        # Should return cached result
        cached = await monitor.get_cached_health(max_age_seconds=30)
        assert cached is health

        # Should not return if too old
        monitor._last_check_time = datetime.now() - timedelta(seconds=60)
        cached = await monitor.get_cached_health(max_age_seconds=30)
        assert cached is None

    @pytest.mark.asyncio
    async def test_circuit_breaker_consecutive_failures(self):
        """Test circuit breaker tracks consecutive failures"""
        monitor = HealthMonitor(failure_threshold=3)

        # Mock Redis to fail
        with patch('redis.asyncio.from_url') as mock_redis:
            mock_redis.side_effect = Exception("Connection failed")

            # First failure - should be DEGRADED
            health1 = await monitor.check_redis_health("redis://localhost:6379/0")
            assert health1.status == HealthStatus.DEGRADED

            # Second failure - still DEGRADED
            health2 = await monitor.check_redis_health("redis://localhost:6379/0")
            assert health2.status == HealthStatus.DEGRADED

            # Third failure - should be UNHEALTHY
            health3 = await monitor.check_redis_health("redis://localhost:6379/0")
            assert health3.status == HealthStatus.UNHEALTHY

            # Verify failure count
            assert monitor._failure_counts["redis"] >= 3

    @pytest.mark.asyncio
    @patch('database.connection.db_manager')
    async def test_circuit_breaker_reset_on_success(self, mock_db_manager):
        """Test circuit breaker resets on successful check"""
        monitor = HealthMonitor()

        # Simulate failures
        monitor._failure_counts["postgres"] = 2

        # Successful check
        mock_db_manager.health_check.return_value = True
        health = await monitor.check_database_health()

        # Failure count should reset
        assert monitor._failure_counts["postgres"] == 0
        assert health.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_background_monitoring_start_stop(self):
        """Test starting and stopping background monitoring"""
        monitor = HealthMonitor(check_interval=1)

        # Start monitoring
        await monitor.start_monitoring(
            postgres_enabled=False,
            redis_url=None,
            external_apis=None
        )

        assert monitor._monitoring_enabled is True
        assert monitor._monitor_task is not None

        # Wait a bit
        await asyncio.sleep(0.5)

        # Stop monitoring
        await monitor.stop_monitoring()

        assert monitor._monitoring_enabled is False

    def test_get_health_monitor_singleton(self):
        """Test global health monitor singleton"""
        monitor1 = get_health_monitor()
        monitor2 = get_health_monitor()

        assert monitor1 is monitor2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
