"""
Standardized Health Check Module for Crypto Trading Bot
Purpose: Provides consistent health check endpoints for all services
Version: 1.0.0 - Phase 7 High Availability

This module implements:
- Liveness probes: Is the service alive?
- Readiness probes: Is the service ready to handle traffic?
- Deep health checks: Database, Redis, External API connectivity

Usage:
    from shared.health_check import HealthCheckManager, HealthStatus

    health_manager = HealthCheckManager(service_name="trading-engine")
    health_manager.add_dependency("postgres", check_postgres)
    health_manager.add_dependency("redis", check_redis)

    # In FastAPI:
    @app.get("/health")
    async def health():
        return await health_manager.liveness()

    @app.get("/ready")
    async def ready():
        return await health_manager.readiness()

    @app.get("/health/deep")
    async def deep_health():
        return await health_manager.deep_check()
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Union

# Configure module logger
logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status enumeration for service components"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class DependencyType(str, Enum):
    """Types of service dependencies"""

    DATABASE = "database"
    CACHE = "cache"
    MESSAGE_QUEUE = "message_queue"
    EXTERNAL_API = "external_api"
    INTERNAL_SERVICE = "internal_service"
    FILE_SYSTEM = "file_system"


@dataclass
class DependencyHealth:
    """Health status of a single dependency"""

    name: str
    type: DependencyType
    status: HealthStatus
    latency_ms: float
    message: str = ""
    last_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ServiceHealth:
    """Overall health status of a service"""

    service_name: str
    status: HealthStatus
    version: str
    uptime_seconds: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    dependencies: List[DependencyHealth] = field(default_factory=list)
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "service_name": self.service_name,
            "status": self.status.value,
            "version": self.version,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "details": self.details,
            "dependencies": [
                {
                    "name": dep.name,
                    "type": dep.type.value,
                    "status": dep.status.value,
                    "latency_ms": round(dep.latency_ms, 2),
                    "message": dep.message,
                    "last_check": dep.last_check.isoformat(),
                    "details": dep.details
                }
                for dep in self.dependencies
            ]
        }


# Type alias for health check functions
HealthCheckFunc = Union[
    Callable[[], Coroutine[Any, Any, DependencyHealth]],
    Callable[[], DependencyHealth]
]


class HealthCheckManager:
    """
    Manages health checks for a microservice

    Features:
    - Liveness probe: Basic service alive check
    - Readiness probe: Service ready to handle requests
    - Deep health check: All dependencies checked
    - Caching of health check results
    - Configurable timeouts and retry logic
    """

    def __init__(
        self,
        service_name: str,
        version: str = "1.0.0",
        liveness_timeout_ms: float = 100,
        readiness_timeout_ms: float = 5000,
        deep_check_timeout_ms: float = 30000,
        cache_ttl_seconds: float = 5.0
    ):
        """
        Initialize the health check manager

        Args:
            service_name: Name of the service
            version: Service version string
            liveness_timeout_ms: Timeout for liveness checks
            readiness_timeout_ms: Timeout for readiness checks
            deep_check_timeout_ms: Timeout for deep health checks
            cache_ttl_seconds: Cache duration for health check results
        """
        self.service_name = service_name
        self.version = version
        self.start_time = time.time()

        # Timeouts
        self.liveness_timeout_ms = liveness_timeout_ms
        self.readiness_timeout_ms = readiness_timeout_ms
        self.deep_check_timeout_ms = deep_check_timeout_ms

        # Caching
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: Dict[str, tuple] = {}  # {check_type: (result, timestamp)}

        # Dependencies registry
        self._dependencies: Dict[str, tuple] = {}  # {name: (check_func, dep_type, critical)}

        # Liveness checks (fast, basic)
        self._liveness_checks: List[HealthCheckFunc] = []

        # Readiness checks (medium, service readiness)
        self._readiness_checks: List[HealthCheckFunc] = []

        logger.info(f"HealthCheckManager initialized for {service_name} v{version}")

    @property
    def uptime_seconds(self) -> float:
        """Get service uptime in seconds"""
        return time.time() - self.start_time

    def add_dependency(
        self,
        name: str,
        check_func: HealthCheckFunc,
        dep_type: DependencyType = DependencyType.INTERNAL_SERVICE,
        critical: bool = True
    ) -> None:
        """
        Register a dependency health check

        Args:
            name: Dependency name (e.g., "postgres", "redis")
            check_func: Async or sync function that returns DependencyHealth
            dep_type: Type of dependency
            critical: If True, failure makes service unhealthy; if False, degraded
        """
        self._dependencies[name] = (check_func, dep_type, critical)
        logger.debug(f"Added dependency: {name} (type={dep_type.value}, critical={critical})")

    def add_liveness_check(self, check_func: HealthCheckFunc) -> None:
        """Add a custom liveness check function"""
        self._liveness_checks.append(check_func)

    def add_readiness_check(self, check_func: HealthCheckFunc) -> None:
        """Add a custom readiness check function"""
        self._readiness_checks.append(check_func)

    async def _run_check(
        self,
        check_func: HealthCheckFunc,
        timeout_ms: float
    ) -> DependencyHealth:
        """
        Run a health check function with timeout

        Args:
            check_func: Health check function to run
            timeout_ms: Timeout in milliseconds

        Returns:
            DependencyHealth result
        """
        start_time = time.time()

        try:
            # Check if function is async
            if asyncio.iscoroutinefunction(check_func):
                result = await asyncio.wait_for(
                    check_func(),
                    timeout=timeout_ms / 1000
                )
            else:
                # Run sync function in thread pool
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, check_func),
                    timeout=timeout_ms / 1000
                )

            return result

        except asyncio.TimeoutError:
            latency = (time.time() - start_time) * 1000
            return DependencyHealth(
                name="timeout",
                type=DependencyType.INTERNAL_SERVICE,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                message=f"Health check timed out after {timeout_ms}ms"
            )
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            logger.error(f"Health check error: {e}")
            return DependencyHealth(
                name="error",
                type=DependencyType.INTERNAL_SERVICE,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                message=f"Health check failed: {str(e)}"
            )

    def _get_cached(self, cache_key: str) -> Optional[ServiceHealth]:
        """Get cached health check result if still valid"""
        if cache_key in self._cache:
            result, timestamp = self._cache[cache_key]
            if time.time() - timestamp < self.cache_ttl_seconds:
                return result
        return None

    def _set_cached(self, cache_key: str, result: ServiceHealth) -> None:
        """Cache a health check result"""
        self._cache[cache_key] = (result, time.time())

    async def liveness(self) -> ServiceHealth:
        """
        Liveness probe - Is the service alive?

        This should be FAST and only check if the service process is running.
        Used by Kubernetes to determine if container should be restarted.

        Returns:
            ServiceHealth with basic status
        """
        # Check cache
        cached = self._get_cached("liveness")
        if cached:
            return cached

        start_time = time.time()
        status = HealthStatus.HEALTHY
        message = "Service is alive"

        # Run custom liveness checks
        for check_func in self._liveness_checks:
            try:
                result = await self._run_check(check_func, self.liveness_timeout_ms)
                if result.status == HealthStatus.UNHEALTHY:
                    status = HealthStatus.UNHEALTHY
                    message = result.message
                    break
            except Exception as e:
                status = HealthStatus.UNHEALTHY
                message = f"Liveness check failed: {str(e)}"
                break

        health = ServiceHealth(
            service_name=self.service_name,
            status=status,
            version=self.version,
            uptime_seconds=self.uptime_seconds,
            message=message,
            details={
                "check_type": "liveness",
                "check_duration_ms": round((time.time() - start_time) * 1000, 2)
            }
        )

        self._set_cached("liveness", health)
        return health

    async def readiness(self) -> ServiceHealth:
        """
        Readiness probe - Is the service ready to handle traffic?

        Checks critical dependencies to determine if service can accept requests.
        Used by Kubernetes to add/remove service from load balancer.

        Returns:
            ServiceHealth with dependency status
        """
        # Check cache
        cached = self._get_cached("readiness")
        if cached:
            return cached

        start_time = time.time()
        dependencies: List[DependencyHealth] = []
        status = HealthStatus.HEALTHY
        messages: List[str] = []

        # Check critical dependencies
        for name, (check_func, dep_type, critical) in self._dependencies.items():
            if not critical:
                continue

            dep_start = time.time()
            try:
                result = await self._run_check(check_func, self.readiness_timeout_ms)
                result.name = name
                result.type = dep_type
                result.latency_ms = (time.time() - dep_start) * 1000
                dependencies.append(result)

                if result.status == HealthStatus.UNHEALTHY:
                    status = HealthStatus.UNHEALTHY
                    messages.append(f"{name}: {result.message}")
                elif result.status == HealthStatus.DEGRADED and status == HealthStatus.HEALTHY:
                    status = HealthStatus.DEGRADED
                    messages.append(f"{name}: {result.message}")

            except Exception as e:
                dependencies.append(DependencyHealth(
                    name=name,
                    type=dep_type,
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=(time.time() - dep_start) * 1000,
                    message=str(e)
                ))
                status = HealthStatus.UNHEALTHY
                messages.append(f"{name}: {str(e)}")

        # Run custom readiness checks
        for check_func in self._readiness_checks:
            try:
                result = await self._run_check(check_func, self.readiness_timeout_ms)
                if result.status == HealthStatus.UNHEALTHY:
                    status = HealthStatus.UNHEALTHY
                    messages.append(result.message)
                elif result.status == HealthStatus.DEGRADED and status == HealthStatus.HEALTHY:
                    status = HealthStatus.DEGRADED
                    messages.append(result.message)
            except Exception as e:
                status = HealthStatus.UNHEALTHY
                messages.append(f"Readiness check failed: {str(e)}")

        health = ServiceHealth(
            service_name=self.service_name,
            status=status,
            version=self.version,
            uptime_seconds=self.uptime_seconds,
            message="; ".join(messages) if messages else "Service is ready",
            dependencies=dependencies,
            details={
                "check_type": "readiness",
                "check_duration_ms": round((time.time() - start_time) * 1000, 2),
                "critical_deps_checked": len(dependencies)
            }
        )

        self._set_cached("readiness", health)
        return health

    async def deep_check(self) -> ServiceHealth:
        """
        Deep health check - Check ALL dependencies

        Comprehensive check of all registered dependencies including non-critical ones.
        Used for debugging and monitoring dashboards.

        Returns:
            ServiceHealth with all dependency statuses
        """
        start_time = time.time()
        dependencies: List[DependencyHealth] = []
        status = HealthStatus.HEALTHY
        messages: List[str] = []

        # Check all dependencies concurrently
        async def check_dependency(name: str, check_func: HealthCheckFunc,
                                  dep_type: DependencyType, critical: bool) -> DependencyHealth:
            dep_start = time.time()
            try:
                result = await self._run_check(check_func, self.deep_check_timeout_ms)
                result.name = name
                result.type = dep_type
                result.latency_ms = (time.time() - dep_start) * 1000
                result.details["critical"] = critical
                return result
            except Exception as e:
                return DependencyHealth(
                    name=name,
                    type=dep_type,
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=(time.time() - dep_start) * 1000,
                    message=str(e),
                    details={"critical": critical}
                )

        # Run all checks concurrently
        tasks = [
            check_dependency(name, check_func, dep_type, critical)
            for name, (check_func, dep_type, critical) in self._dependencies.items()
        ]

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    dependencies.append(DependencyHealth(
                        name="unknown",
                        type=DependencyType.INTERNAL_SERVICE,
                        status=HealthStatus.UNHEALTHY,
                        latency_ms=0,
                        message=str(result)
                    ))
                    status = HealthStatus.UNHEALTHY
                    messages.append(str(result))
                else:
                    dependencies.append(result)
                    critical = result.details.get("critical", True)

                    if result.status == HealthStatus.UNHEALTHY:
                        if critical:
                            status = HealthStatus.UNHEALTHY
                        elif status == HealthStatus.HEALTHY:
                            status = HealthStatus.DEGRADED
                        messages.append(f"{result.name}: {result.message}")

                    elif result.status == HealthStatus.DEGRADED:
                        if status == HealthStatus.HEALTHY:
                            status = HealthStatus.DEGRADED
                        messages.append(f"{result.name}: {result.message}")

        health = ServiceHealth(
            service_name=self.service_name,
            status=status,
            version=self.version,
            uptime_seconds=self.uptime_seconds,
            message="; ".join(messages) if messages else "All systems operational",
            dependencies=dependencies,
            details={
                "check_type": "deep",
                "check_duration_ms": round((time.time() - start_time) * 1000, 2),
                "total_deps_checked": len(dependencies),
                "healthy_deps": sum(1 for d in dependencies if d.status == HealthStatus.HEALTHY),
                "unhealthy_deps": sum(1 for d in dependencies if d.status == HealthStatus.UNHEALTHY),
                "degraded_deps": sum(1 for d in dependencies if d.status == HealthStatus.DEGRADED)
            }
        )

        return health


# =============================================================================
# Pre-built Health Check Functions for Common Dependencies
# =============================================================================

async def check_postgres(
    host: str = "localhost",
    port: int = 5432,
    database: str = "trading",
    user: str = "postgres",
    password: str = "",
    timeout: float = 5.0
) -> DependencyHealth:
    """
    Health check for PostgreSQL database

    Args:
        host: Database host
        port: Database port
        database: Database name
        user: Database user
        password: Database password
        timeout: Connection timeout

    Returns:
        DependencyHealth status
    """
    start_time = time.time()

    try:
        import asyncpg

        conn = await asyncpg.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            timeout=timeout
        )

        # Simple query to verify connection
        result = await conn.fetchval("SELECT 1")
        await conn.close()

        latency = (time.time() - start_time) * 1000

        return DependencyHealth(
            name="postgres",
            type=DependencyType.DATABASE,
            status=HealthStatus.HEALTHY,
            latency_ms=latency,
            message="Connected successfully",
            details={
                "host": host,
                "port": port,
                "database": database
            }
        )

    except ImportError:
        return DependencyHealth(
            name="postgres",
            type=DependencyType.DATABASE,
            status=HealthStatus.UNKNOWN,
            latency_ms=(time.time() - start_time) * 1000,
            message="asyncpg not installed"
        )
    except Exception as e:
        return DependencyHealth(
            name="postgres",
            type=DependencyType.DATABASE,
            status=HealthStatus.UNHEALTHY,
            latency_ms=(time.time() - start_time) * 1000,
            message=f"Connection failed: {str(e)}",
            details={
                "host": host,
                "port": port,
                "database": database,
                "error": str(e)
            }
        )


async def check_redis(
    url: str = "redis://localhost:6379/0",
    timeout: float = 5.0
) -> DependencyHealth:
    """
    Health check for Redis cache

    Args:
        url: Redis connection URL
        timeout: Connection timeout

    Returns:
        DependencyHealth status
    """
    start_time = time.time()

    try:
        import redis.asyncio as redis

        client = redis.from_url(url, socket_timeout=timeout)

        # Ping Redis
        result = await client.ping()

        # Get info for details
        info = await client.info("memory")
        await client.close()

        latency = (time.time() - start_time) * 1000

        return DependencyHealth(
            name="redis",
            type=DependencyType.CACHE,
            status=HealthStatus.HEALTHY,
            latency_ms=latency,
            message="Connected successfully",
            details={
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "connected_clients": info.get("connected_clients", 0)
            }
        )

    except ImportError:
        return DependencyHealth(
            name="redis",
            type=DependencyType.CACHE,
            status=HealthStatus.UNKNOWN,
            latency_ms=(time.time() - start_time) * 1000,
            message="redis package not installed"
        )
    except Exception as e:
        return DependencyHealth(
            name="redis",
            type=DependencyType.CACHE,
            status=HealthStatus.UNHEALTHY,
            latency_ms=(time.time() - start_time) * 1000,
            message=f"Connection failed: {str(e)}",
            details={"url": url.split("@")[-1], "error": str(e)}
        )


async def check_rabbitmq(
    url: str = "amqp://guest:guest@localhost:5672/",
    timeout: float = 5.0
) -> DependencyHealth:
    """
    Health check for RabbitMQ message queue

    Args:
        url: RabbitMQ connection URL
        timeout: Connection timeout

    Returns:
        DependencyHealth status
    """
    start_time = time.time()

    try:
        import aio_pika

        connection = await aio_pika.connect_robust(url, timeout=timeout)
        await connection.close()

        latency = (time.time() - start_time) * 1000

        return DependencyHealth(
            name="rabbitmq",
            type=DependencyType.MESSAGE_QUEUE,
            status=HealthStatus.HEALTHY,
            latency_ms=latency,
            message="Connected successfully"
        )

    except ImportError:
        return DependencyHealth(
            name="rabbitmq",
            type=DependencyType.MESSAGE_QUEUE,
            status=HealthStatus.UNKNOWN,
            latency_ms=(time.time() - start_time) * 1000,
            message="aio_pika not installed"
        )
    except Exception as e:
        return DependencyHealth(
            name="rabbitmq",
            type=DependencyType.MESSAGE_QUEUE,
            status=HealthStatus.UNHEALTHY,
            latency_ms=(time.time() - start_time) * 1000,
            message=f"Connection failed: {str(e)}"
        )


async def check_http_service(
    url: str,
    timeout: float = 5.0,
    expected_status: int = 200
) -> DependencyHealth:
    """
    Health check for HTTP service

    Args:
        url: Service health endpoint URL
        timeout: Request timeout
        expected_status: Expected HTTP status code

    Returns:
        DependencyHealth status
    """
    start_time = time.time()

    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)

        latency = (time.time() - start_time) * 1000

        if response.status_code == expected_status:
            return DependencyHealth(
                name=url.split("/")[2],  # Extract host
                type=DependencyType.INTERNAL_SERVICE,
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="Service responded successfully",
                details={"status_code": response.status_code}
            )
        else:
            return DependencyHealth(
                name=url.split("/")[2],
                type=DependencyType.INTERNAL_SERVICE,
                status=HealthStatus.DEGRADED,
                latency_ms=latency,
                message=f"Unexpected status: {response.status_code}",
                details={"status_code": response.status_code, "expected": expected_status}
            )

    except ImportError:
        return DependencyHealth(
            name="http_service",
            type=DependencyType.INTERNAL_SERVICE,
            status=HealthStatus.UNKNOWN,
            latency_ms=(time.time() - start_time) * 1000,
            message="httpx not installed"
        )
    except Exception as e:
        return DependencyHealth(
            name=url.split("/")[2] if "/" in url else url,
            type=DependencyType.INTERNAL_SERVICE,
            status=HealthStatus.UNHEALTHY,
            latency_ms=(time.time() - start_time) * 1000,
            message=f"Request failed: {str(e)}",
            details={"url": url, "error": str(e)}
        )


async def check_bybit_api(
    testnet: bool = True,
    timeout: float = 10.0
) -> DependencyHealth:
    """
    Health check for Bybit API connectivity

    Args:
        testnet: Use testnet endpoint
        timeout: Request timeout

    Returns:
        DependencyHealth status
    """
    start_time = time.time()

    base_url = "https://api-testnet.bybit.com" if testnet else "https://api.bybit.com"
    url = f"{base_url}/v5/market/time"

    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)

        latency = (time.time() - start_time) * 1000

        if response.status_code == 200:
            data = response.json()
            server_time = data.get("result", {}).get("timeSecond", 0)

            return DependencyHealth(
                name="bybit_api",
                type=DependencyType.EXTERNAL_API,
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="API accessible",
                details={
                    "endpoint": "testnet" if testnet else "mainnet",
                    "server_time": server_time
                }
            )
        else:
            return DependencyHealth(
                name="bybit_api",
                type=DependencyType.EXTERNAL_API,
                status=HealthStatus.DEGRADED,
                latency_ms=latency,
                message=f"API returned status {response.status_code}",
                details={"status_code": response.status_code}
            )

    except ImportError:
        return DependencyHealth(
            name="bybit_api",
            type=DependencyType.EXTERNAL_API,
            status=HealthStatus.UNKNOWN,
            latency_ms=(time.time() - start_time) * 1000,
            message="httpx not installed"
        )
    except Exception as e:
        return DependencyHealth(
            name="bybit_api",
            type=DependencyType.EXTERNAL_API,
            status=HealthStatus.UNHEALTHY,
            latency_ms=(time.time() - start_time) * 1000,
            message=f"API request failed: {str(e)}",
            details={"error": str(e)}
        )


# =============================================================================
# FastAPI Integration Helpers
# =============================================================================

def create_health_routes(health_manager: HealthCheckManager):
    """
    Create FastAPI routes for health checks

    Args:
        health_manager: Configured HealthCheckManager instance

    Returns:
        FastAPI APIRouter with health endpoints
    """
    from fastapi import APIRouter, Response

    router = APIRouter(tags=["health"])

    @router.get("/health")
    async def liveness_probe(response: Response):
        """
        Liveness probe - Is the service alive?

        Used by Kubernetes to determine if container should be restarted.
        Returns 200 if alive, 503 if unhealthy.
        """
        health = await health_manager.liveness()

        if health.status == HealthStatus.UNHEALTHY:
            response.status_code = 503

        return health.to_dict()

    @router.get("/ready")
    async def readiness_probe(response: Response):
        """
        Readiness probe - Is the service ready to handle traffic?

        Used by Kubernetes to add/remove service from load balancer.
        Returns 200 if ready, 503 if not ready.
        """
        health = await health_manager.readiness()

        if health.status == HealthStatus.UNHEALTHY:
            response.status_code = 503
        elif health.status == HealthStatus.DEGRADED:
            response.status_code = 200  # Still serve traffic when degraded

        return health.to_dict()

    @router.get("/health/deep")
    async def deep_health_check(response: Response):
        """
        Deep health check - Check ALL dependencies

        Comprehensive check for debugging and monitoring.
        """
        health = await health_manager.deep_check()

        if health.status == HealthStatus.UNHEALTHY:
            response.status_code = 503

        return health.to_dict()

    @router.get("/health/metrics")
    async def health_metrics():
        """
        Export health metrics in Prometheus format
        """
        health = await health_manager.deep_check()

        metrics = []

        # Service overall status (1=healthy, 0.5=degraded, 0=unhealthy)
        status_value = {"healthy": 1, "degraded": 0.5, "unhealthy": 0, "unknown": -1}
        metrics.append(
            f'service_health_status{{service="{health.service_name}"}} '
            f'{status_value.get(health.status.value, -1)}'
        )

        # Uptime
        metrics.append(
            f'service_uptime_seconds{{service="{health.service_name}"}} '
            f'{health.uptime_seconds}'
        )

        # Dependency statuses
        for dep in health.dependencies:
            metrics.append(
                f'dependency_health_status{{service="{health.service_name}",'
                f'dependency="{dep.name}",type="{dep.type.value}"}} '
                f'{status_value.get(dep.status.value, -1)}'
            )
            metrics.append(
                f'dependency_latency_ms{{service="{health.service_name}",'
                f'dependency="{dep.name}"}} {dep.latency_ms}'
            )

        return Response(
            content="\n".join(metrics),
            media_type="text/plain"
        )

    return router


# =============================================================================
# Consul Service Registration
# =============================================================================

class ConsulServiceRegistry:
    """
    Service registration with Consul for service discovery
    """

    def __init__(
        self,
        consul_host: str = "localhost",
        consul_port: int = 8500,
        service_name: str = "",
        service_id: str = "",
        service_port: int = 8000,
        service_address: str = "",
        tags: List[str] = None,
        check_interval: str = "10s",
        check_timeout: str = "5s"
    ):
        """
        Initialize Consul service registry

        Args:
            consul_host: Consul agent host
            consul_port: Consul agent port
            service_name: Name of the service to register
            service_id: Unique ID for this service instance
            service_port: Port the service listens on
            service_address: Service IP address
            tags: Service tags for filtering
            check_interval: Health check interval
            check_timeout: Health check timeout
        """
        self.consul_host = consul_host
        self.consul_port = consul_port
        self.service_name = service_name
        self.service_id = service_id or f"{service_name}-{service_port}"
        self.service_port = service_port
        self.service_address = service_address
        self.tags = tags or []
        self.check_interval = check_interval
        self.check_timeout = check_timeout

        self._registered = False

    async def register(self) -> bool:
        """
        Register service with Consul

        Returns:
            True if registration successful
        """
        try:
            import httpx

            registration = {
                "ID": self.service_id,
                "Name": self.service_name,
                "Port": self.service_port,
                "Tags": self.tags,
                "Check": {
                    "HTTP": f"http://{self.service_address or 'localhost'}:{self.service_port}/health",
                    "Interval": self.check_interval,
                    "Timeout": self.check_timeout,
                    "DeregisterCriticalServiceAfter": "1m"
                }
            }

            if self.service_address:
                registration["Address"] = self.service_address

            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"http://{self.consul_host}:{self.consul_port}/v1/agent/service/register",
                    json=registration
                )

            if response.status_code == 200:
                self._registered = True
                logger.info(f"Registered service {self.service_id} with Consul")
                return True
            else:
                logger.error(f"Failed to register with Consul: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Consul registration error: {e}")
            return False

    async def deregister(self) -> bool:
        """
        Deregister service from Consul

        Returns:
            True if deregistration successful
        """
        if not self._registered:
            return True

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"http://{self.consul_host}:{self.consul_port}/v1/agent/service/deregister/{self.service_id}"
                )

            if response.status_code == 200:
                self._registered = False
                logger.info(f"Deregistered service {self.service_id} from Consul")
                return True
            else:
                logger.error(f"Failed to deregister from Consul: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Consul deregistration error: {e}")
            return False

    async def get_healthy_instances(self, service_name: str) -> List[Dict[str, Any]]:
        """
        Get healthy instances of a service from Consul

        Args:
            service_name: Name of the service to query

        Returns:
            List of healthy service instances
        """
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://{self.consul_host}:{self.consul_port}/v1/health/service/{service_name}",
                    params={"passing": "true"}
                )

            if response.status_code == 200:
                instances = []
                for entry in response.json():
                    service = entry.get("Service", {})
                    instances.append({
                        "id": service.get("ID"),
                        "address": service.get("Address") or entry.get("Node", {}).get("Address"),
                        "port": service.get("Port"),
                        "tags": service.get("Tags", [])
                    })
                return instances
            else:
                return []

        except Exception as e:
            logger.error(f"Consul query error: {e}")
            return []


# Export all public classes and functions
__all__ = [
    "HealthStatus",
    "DependencyType",
    "DependencyHealth",
    "ServiceHealth",
    "HealthCheckManager",
    "check_postgres",
    "check_redis",
    "check_rabbitmq",
    "check_http_service",
    "check_bybit_api",
    "create_health_routes",
    "ConsulServiceRegistry"
]
