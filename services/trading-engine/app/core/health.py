"""
Health Check Endpoints Implementation
Phase 7: High Availability & Monitoring Infrastructure

Purpose:
- Provide comprehensive health check endpoints for Kubernetes probes
- Monitor all service dependencies (database, cache, external APIs)
- Support liveness, readiness, and startup probes
- Enable graceful degradation during partial failures

Endpoints:
- GET /health - Basic health check (liveness probe)
- GET /ready - Readiness probe (checks dependencies)
- GET /metrics - Prometheus metrics endpoint
- GET /health/detailed - Full system health report

Kubernetes Integration:
- livenessProbe: Uses /health endpoint
- readinessProbe: Uses /ready endpoint
- startupProbe: Uses /health endpoint with longer timeout
"""

import asyncio
import logging
import time
import psutil
import socket
from typing import Dict, Any, Optional, List, Callable, Awaitable
from enum import Enum
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from prometheus_client import Gauge, Counter, Histogram

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """
    Health status enumeration

    Values:
    - HEALTHY: All systems operational
    - DEGRADED: Some systems impaired but service functional
    - UNHEALTHY: Critical systems down, service impaired
    - UNKNOWN: Unable to determine status
    """
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ComponentType(str, Enum):
    """Types of components being monitored"""
    DATABASE = "database"
    CACHE = "cache"
    MESSAGE_QUEUE = "message_queue"
    EXTERNAL_API = "external_api"
    EXCHANGE = "exchange"
    INTERNAL_SERVICE = "internal_service"


@dataclass
class ComponentHealth:
    """
    Health status for a single component

    Attributes:
        name: Component identifier
        component_type: Type of component
        status: Current health status
        response_time_ms: Response time of health check
        error: Error message if unhealthy
        details: Additional diagnostic information
        last_check: Timestamp of last health check
    """
    name: str
    component_type: ComponentType
    status: HealthStatus = HealthStatus.UNKNOWN
    response_time_ms: float = 0.0
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    last_check: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "name": self.name,
            "type": self.component_type.value,
            "status": self.status.value,
            "response_time_ms": round(self.response_time_ms, 2),
            "error": self.error,
            "details": self.details,
            "last_check": self.last_check.isoformat()
        }


@dataclass
class SystemHealthReport:
    """
    Complete system health report

    Aggregates health status from all components and provides
    overall system health assessment.
    """
    status: HealthStatus = HealthStatus.UNKNOWN
    components: Dict[str, ComponentHealth] = field(default_factory=dict)
    system_metrics: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    version: str = "3.5.0"
    hostname: str = field(default_factory=socket.gethostname)

    def add_component(self, health: ComponentHealth):
        """Add component health to report"""
        self.components[health.name] = health

    def calculate_overall_status(self):
        """
        Calculate overall health status based on components

        Logic:
        - If any critical component (database, exchange) is UNHEALTHY -> UNHEALTHY
        - If any component is UNHEALTHY or multiple DEGRADED -> DEGRADED
        - If all components HEALTHY -> HEALTHY
        """
        if not self.components:
            self.status = HealthStatus.UNKNOWN
            return

        critical_components = {"postgres", "redis", "bybit_connector", "technical_analysis"}
        unhealthy_count = 0
        degraded_count = 0
        critical_unhealthy = False

        for name, comp in self.components.items():
            if comp.status == HealthStatus.UNHEALTHY:
                unhealthy_count += 1
                if name in critical_components:
                    critical_unhealthy = True
            elif comp.status == HealthStatus.DEGRADED:
                degraded_count += 1

        # Determine overall status
        if critical_unhealthy:
            self.status = HealthStatus.UNHEALTHY
        elif unhealthy_count > 0 or degraded_count >= 2:
            self.status = HealthStatus.DEGRADED
        elif degraded_count > 0:
            self.status = HealthStatus.DEGRADED
        else:
            self.status = HealthStatus.HEALTHY

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "status": self.status.value,
            "version": self.version,
            "hostname": self.hostname,
            "timestamp": self.timestamp.isoformat(),
            "components": {
                name: comp.to_dict()
                for name, comp in self.components.items()
            },
            "system_metrics": self.system_metrics,
            "summary": {
                "total_components": len(self.components),
                "healthy": sum(1 for c in self.components.values() if c.status == HealthStatus.HEALTHY),
                "degraded": sum(1 for c in self.components.values() if c.status == HealthStatus.DEGRADED),
                "unhealthy": sum(1 for c in self.components.values() if c.status == HealthStatus.UNHEALTHY),
            }
        }


# Prometheus metrics for health checks
health_check_duration = Histogram(
    'health_check_duration_seconds',
    'Duration of health check operations',
    ['component'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

health_check_status = Gauge(
    'health_check_status',
    'Current health status (0=healthy, 1=degraded, 2=unhealthy, 3=unknown)',
    ['component']
)

health_check_failures = Counter(
    'health_check_failures_total',
    'Total health check failures',
    ['component']
)


class HealthChecker:
    """
    Comprehensive Health Checking System

    Features:
    - Database connectivity checks (PostgreSQL)
    - Cache connectivity checks (Redis)
    - Message queue checks (RabbitMQ)
    - External API health verification
    - Exchange connectivity monitoring
    - System resource monitoring (CPU, memory, disk)
    - Caching of health check results
    - Configurable thresholds and timeouts
    - Prometheus metrics integration

    Usage:
        checker = HealthChecker(config)
        await checker.start_background_checks()

        # Get health report
        report = await checker.get_health_report()

        # Kubernetes probes
        is_live = await checker.liveness_check()
        is_ready = await checker.readiness_check()
    """

    def __init__(
        self,
        check_interval: int = 30,
        failure_threshold: int = 3,
        timeout_seconds: int = 5,
        degraded_response_time_ms: float = 500.0
    ):
        """
        Initialize Health Checker

        Args:
            check_interval: Seconds between background health checks
            failure_threshold: Consecutive failures before marking unhealthy
            timeout_seconds: Timeout for individual health checks
            degraded_response_time_ms: Response time threshold for degraded status
        """
        self.check_interval = check_interval
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.degraded_response_time_ms = degraded_response_time_ms

        # Track consecutive failures for circuit-breaker-like behavior
        self._failure_counts: Dict[str, int] = {}

        # Cache last health check results
        self._cached_report: Optional[SystemHealthReport] = None
        self._last_check_time: Optional[datetime] = None

        # Background monitoring
        self._monitor_task: Optional[asyncio.Task] = None
        self._monitoring_enabled = False

        # Custom health check functions
        self._custom_checks: Dict[str, Callable[[], Awaitable[ComponentHealth]]] = {}

        # Service readiness flag
        self._is_ready = False

        logger.info(
            f"HealthChecker initialized (interval={check_interval}s, "
            f"threshold={failure_threshold}, timeout={timeout_seconds}s)"
        )

    async def check_database(self, connection_string: Optional[str] = None) -> ComponentHealth:
        """
        Check PostgreSQL database connectivity

        Verifies:
        - Connection can be established
        - Simple query executes successfully
        - Connection pool is healthy
        """
        start_time = time.time()
        component = ComponentHealth(
            name="postgres",
            component_type=ComponentType.DATABASE
        )

        try:
            # Import database manager
            from app.database.connection import db_manager

            # Test database connection
            is_healthy = db_manager.health_check()
            response_time = (time.time() - start_time) * 1000

            if is_healthy:
                self._failure_counts["postgres"] = 0

                if response_time > self.degraded_response_time_ms:
                    component.status = HealthStatus.DEGRADED
                    component.details["warning"] = "High latency"
                else:
                    component.status = HealthStatus.HEALTHY

                component.details.update({
                    "connected": True,
                    "pool_size": getattr(db_manager, 'get_pool_size', lambda: "N/A")()
                })
            else:
                self._failure_counts["postgres"] = self._failure_counts.get("postgres", 0) + 1
                component.status = (
                    HealthStatus.UNHEALTHY
                    if self._failure_counts["postgres"] >= self.failure_threshold
                    else HealthStatus.DEGRADED
                )
                component.error = "Health check returned False"

            component.response_time_ms = response_time

        except ImportError:
            component.status = HealthStatus.UNHEALTHY
            component.error = "Database module not available"
        except Exception as e:
            self._failure_counts["postgres"] = self._failure_counts.get("postgres", 0) + 1
            component.status = HealthStatus.UNHEALTHY
            component.error = str(e)
            component.response_time_ms = (time.time() - start_time) * 1000
            health_check_failures.labels(component="postgres").inc()

        # Update Prometheus metric
        health_check_duration.labels(component="postgres").observe(
            component.response_time_ms / 1000
        )
        health_check_status.labels(component="postgres").set(
            {"healthy": 0, "degraded": 1, "unhealthy": 2, "unknown": 3}[component.status.value]
        )

        return component

    async def check_redis(self, redis_url: str) -> ComponentHealth:
        """
        Check Redis cache connectivity

        Verifies:
        - Connection can be established
        - PING command succeeds
        - Server info is retrievable
        """
        start_time = time.time()
        component = ComponentHealth(
            name="redis",
            component_type=ComponentType.CACHE
        )

        try:
            import redis.asyncio as redis_client

            # Create Redis connection with timeout
            client = redis_client.from_url(
                redis_url,
                socket_connect_timeout=self.timeout_seconds,
                socket_timeout=self.timeout_seconds
            )

            # Test connection with PING
            await client.ping()
            response_time = (time.time() - start_time) * 1000

            # Get Redis info
            info = await client.info()
            await client.close()

            # Reset failure count on success
            self._failure_counts["redis"] = 0

            # Determine status based on response time
            if response_time > self.degraded_response_time_ms / 2:
                component.status = HealthStatus.DEGRADED
            else:
                component.status = HealthStatus.HEALTHY

            component.response_time_ms = response_time
            component.details = {
                "version": info.get("redis_version", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "uptime_days": info.get("uptime_in_days", 0)
            }

        except ImportError:
            component.status = HealthStatus.DEGRADED
            component.error = "Redis module not available (optional)"
        except Exception as e:
            self._failure_counts["redis"] = self._failure_counts.get("redis", 0) + 1
            component.status = (
                HealthStatus.UNHEALTHY
                if self._failure_counts["redis"] >= self.failure_threshold
                else HealthStatus.DEGRADED
            )
            component.error = str(e)
            component.response_time_ms = (time.time() - start_time) * 1000
            health_check_failures.labels(component="redis").inc()

        # Update Prometheus metric
        health_check_duration.labels(component="redis").observe(
            component.response_time_ms / 1000
        )
        health_check_status.labels(component="redis").set(
            {"healthy": 0, "degraded": 1, "unhealthy": 2, "unknown": 3}[component.status.value]
        )

        return component

    async def check_rabbitmq(self, rabbitmq_url: str) -> ComponentHealth:
        """
        Check RabbitMQ message queue connectivity

        Verifies:
        - Connection can be established
        - Channel can be opened
        """
        start_time = time.time()
        component = ComponentHealth(
            name="rabbitmq",
            component_type=ComponentType.MESSAGE_QUEUE
        )

        try:
            import aio_pika

            # Connect to RabbitMQ
            connection = await asyncio.wait_for(
                aio_pika.connect_robust(rabbitmq_url),
                timeout=self.timeout_seconds
            )
            channel = await connection.channel()
            await channel.close()
            await connection.close()

            response_time = (time.time() - start_time) * 1000
            self._failure_counts["rabbitmq"] = 0

            if response_time > self.degraded_response_time_ms:
                component.status = HealthStatus.DEGRADED
            else:
                component.status = HealthStatus.HEALTHY

            component.response_time_ms = response_time
            component.details = {"connected": True}

        except ImportError:
            component.status = HealthStatus.DEGRADED
            component.error = "aio_pika not available (optional)"
        except asyncio.TimeoutError:
            self._failure_counts["rabbitmq"] = self._failure_counts.get("rabbitmq", 0) + 1
            component.status = HealthStatus.UNHEALTHY
            component.error = f"Connection timeout ({self.timeout_seconds}s)"
            health_check_failures.labels(component="rabbitmq").inc()
        except Exception as e:
            self._failure_counts["rabbitmq"] = self._failure_counts.get("rabbitmq", 0) + 1
            component.status = (
                HealthStatus.UNHEALTHY
                if self._failure_counts["rabbitmq"] >= self.failure_threshold
                else HealthStatus.DEGRADED
            )
            component.error = str(e)
            health_check_failures.labels(component="rabbitmq").inc()

        component.response_time_ms = (time.time() - start_time) * 1000

        # Update Prometheus metric
        health_check_duration.labels(component="rabbitmq").observe(
            component.response_time_ms / 1000
        )

        return component

    async def check_external_api(
        self,
        name: str,
        url: str,
        component_type: ComponentType = ComponentType.EXTERNAL_API
    ) -> ComponentHealth:
        """
        Check external API health endpoint

        Args:
            name: Service name for identification
            url: Health check URL
            component_type: Type of component

        Verifies:
        - HTTP request succeeds with 200 status
        - Response time is acceptable
        """
        start_time = time.time()
        component = ComponentHealth(
            name=name,
            component_type=component_type
        )

        try:
            import httpx

            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url)
                response_time = (time.time() - start_time) * 1000

                if response.status_code == 200:
                    self._failure_counts[name] = 0

                    if response_time > self.degraded_response_time_ms:
                        component.status = HealthStatus.DEGRADED
                    else:
                        component.status = HealthStatus.HEALTHY

                    # Try to parse response
                    try:
                        data = response.json()
                        if isinstance(data, dict):
                            component.details = {
                                "service_status": data.get("status", "unknown"),
                                "version": data.get("version", "unknown")
                            }
                    except:
                        pass
                else:
                    self._failure_counts[name] = self._failure_counts.get(name, 0) + 1
                    component.status = (
                        HealthStatus.UNHEALTHY
                        if self._failure_counts[name] >= self.failure_threshold
                        else HealthStatus.DEGRADED
                    )
                    component.error = f"HTTP {response.status_code}"

                component.response_time_ms = response_time

        except asyncio.TimeoutError:
            self._failure_counts[name] = self._failure_counts.get(name, 0) + 1
            component.status = HealthStatus.UNHEALTHY
            component.error = f"Timeout ({self.timeout_seconds}s)"
            component.response_time_ms = (time.time() - start_time) * 1000
            health_check_failures.labels(component=name).inc()
        except ImportError:
            component.status = HealthStatus.DEGRADED
            component.error = "httpx not available"
        except Exception as e:
            self._failure_counts[name] = self._failure_counts.get(name, 0) + 1
            component.status = (
                HealthStatus.UNHEALTHY
                if self._failure_counts[name] >= self.failure_threshold
                else HealthStatus.DEGRADED
            )
            component.error = str(e)
            component.response_time_ms = (time.time() - start_time) * 1000
            health_check_failures.labels(component=name).inc()

        # Update Prometheus metric
        health_check_duration.labels(component=name).observe(
            component.response_time_ms / 1000
        )
        health_check_status.labels(component=name).set(
            {"healthy": 0, "degraded": 1, "unhealthy": 2, "unknown": 3}[component.status.value]
        )

        return component

    def get_system_metrics(self) -> Dict[str, Any]:
        """
        Collect system resource metrics

        Returns:
            Dictionary with CPU, memory, disk, and process metrics
        """
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()

            # Memory metrics
            memory = psutil.virtual_memory()

            # Disk metrics
            disk = psutil.disk_usage('/')

            # Process-specific metrics
            process = psutil.Process()
            process_memory = process.memory_info()

            # Network connections
            connections = len(psutil.net_connections(kind='inet'))

            return {
                "cpu": {
                    "percent": round(cpu_percent, 2),
                    "count": cpu_count,
                    "load_avg": list(psutil.getloadavg()) if hasattr(psutil, 'getloadavg') else None
                },
                "memory": {
                    "total_mb": round(memory.total / (1024 * 1024), 2),
                    "available_mb": round(memory.available / (1024 * 1024), 2),
                    "used_mb": round(memory.used / (1024 * 1024), 2),
                    "percent": round(memory.percent, 2)
                },
                "disk": {
                    "total_gb": round(disk.total / (1024 ** 3), 2),
                    "used_gb": round(disk.used / (1024 ** 3), 2),
                    "free_gb": round(disk.free / (1024 ** 3), 2),
                    "percent": round(disk.percent, 2)
                },
                "process": {
                    "memory_mb": round(process_memory.rss / (1024 * 1024), 2),
                    "threads": process.num_threads(),
                    "connections": connections,
                    "open_files": len(process.open_files())
                },
                "thresholds": {
                    "cpu_warning": 80,
                    "memory_warning": 85,
                    "disk_warning": 90
                }
            }
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
            return {"error": str(e)}

    async def perform_full_check(
        self,
        check_database: bool = True,
        redis_url: Optional[str] = None,
        rabbitmq_url: Optional[str] = None,
        external_apis: Optional[Dict[str, str]] = None
    ) -> SystemHealthReport:
        """
        Perform comprehensive health check of all components

        Args:
            check_database: Whether to check PostgreSQL
            redis_url: Redis URL to check (optional)
            rabbitmq_url: RabbitMQ URL to check (optional)
            external_apis: Dictionary of service_name -> health_url

        Returns:
            Complete SystemHealthReport
        """
        report = SystemHealthReport()
        checks = []

        # Add database check
        if check_database:
            checks.append(self.check_database())

        # Add Redis check
        if redis_url:
            checks.append(self.check_redis(redis_url))

        # Add RabbitMQ check
        if rabbitmq_url:
            checks.append(self.check_rabbitmq(rabbitmq_url))

        # Add external API checks
        if external_apis:
            for name, url in external_apis.items():
                component_type = (
                    ComponentType.EXCHANGE if "bybit" in name.lower()
                    else ComponentType.INTERNAL_SERVICE
                )
                checks.append(self.check_external_api(name, url, component_type))

        # Add custom checks
        for check_func in self._custom_checks.values():
            checks.append(check_func())

        # Run all checks concurrently
        results = await asyncio.gather(*checks, return_exceptions=True)

        for result in results:
            if isinstance(result, ComponentHealth):
                report.add_component(result)
            elif isinstance(result, Exception):
                logger.error(f"Health check error: {result}")

        # Add system metrics
        report.system_metrics = self.get_system_metrics()

        # Calculate overall status
        report.calculate_overall_status()

        # Cache result
        self._cached_report = report
        self._last_check_time = datetime.now()

        return report

    async def get_cached_report(
        self,
        max_age_seconds: int = 30
    ) -> Optional[SystemHealthReport]:
        """
        Get cached health report if recent enough

        Args:
            max_age_seconds: Maximum age of cached report

        Returns:
            Cached report if valid, None otherwise
        """
        if self._cached_report and self._last_check_time:
            age = (datetime.now() - self._last_check_time).total_seconds()
            if age <= max_age_seconds:
                return self._cached_report
        return None

    async def liveness_check(self) -> Dict[str, Any]:
        """
        Kubernetes liveness probe endpoint

        Returns simple healthy/unhealthy status.
        Indicates if the process is alive and should be kept running.

        Returns:
            Dictionary with status and timestamp
        """
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat()
        }

    async def readiness_check(
        self,
        check_database: bool = True,
        redis_url: Optional[str] = None,
        external_apis: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Kubernetes readiness probe endpoint

        Checks if the service is ready to receive traffic.
        Verifies critical dependencies are available.

        Returns:
            Dictionary with status, ready flag, and component statuses
        """
        # Try to use cached report first
        report = await self.get_cached_report(max_age_seconds=10)

        if not report:
            # Perform quick health check
            report = await self.perform_full_check(
                check_database=check_database,
                redis_url=redis_url,
                external_apis=external_apis
            )

        is_ready = report.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
        self._is_ready = is_ready

        return {
            "status": report.status.value,
            "ready": is_ready,
            "timestamp": datetime.now().isoformat(),
            "components": {
                name: {"status": comp.status.value}
                for name, comp in report.components.items()
            }
        }

    def register_custom_check(
        self,
        name: str,
        check_func: Callable[[], Awaitable[ComponentHealth]]
    ):
        """
        Register a custom health check function

        Args:
            name: Unique name for the check
            check_func: Async function that returns ComponentHealth
        """
        self._custom_checks[name] = check_func
        logger.info(f"Registered custom health check: {name}")

    async def start_background_checks(
        self,
        check_database: bool = True,
        redis_url: Optional[str] = None,
        rabbitmq_url: Optional[str] = None,
        external_apis: Optional[Dict[str, str]] = None
    ):
        """
        Start background health monitoring

        Runs periodic health checks and maintains cached status.
        """
        if self._monitoring_enabled:
            logger.warning("Background health checks already running")
            return

        self._monitoring_enabled = True

        async def monitor_loop():
            logger.info("Background health monitoring started")

            while self._monitoring_enabled:
                try:
                    report = await self.perform_full_check(
                        check_database=check_database,
                        redis_url=redis_url,
                        rabbitmq_url=rabbitmq_url,
                        external_apis=external_apis
                    )

                    # Log status changes
                    if report.status == HealthStatus.UNHEALTHY:
                        logger.error(f"System health UNHEALTHY: {report.to_dict()}")
                    elif report.status == HealthStatus.DEGRADED:
                        logger.warning(f"System health DEGRADED")
                    else:
                        logger.debug("System health HEALTHY")

                except Exception as e:
                    logger.error(f"Background health check error: {e}", exc_info=True)

                await asyncio.sleep(self.check_interval)

        self._monitor_task = asyncio.create_task(monitor_loop())
        logger.info(f"Background monitoring task started (interval={self.check_interval}s)")

    async def stop_background_checks(self):
        """Stop background health monitoring"""
        if not self._monitoring_enabled:
            return

        self._monitoring_enabled = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("Background health monitoring stopped")


# Global health checker instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker(
    check_interval: int = 30,
    failure_threshold: int = 3,
    timeout_seconds: int = 5
) -> HealthChecker:
    """
    Get or create global health checker instance

    Returns:
        HealthChecker singleton instance
    """
    global _health_checker

    if _health_checker is None:
        _health_checker = HealthChecker(
            check_interval=check_interval,
            failure_threshold=failure_threshold,
            timeout_seconds=timeout_seconds
        )

    return _health_checker
