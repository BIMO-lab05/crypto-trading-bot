"""
Health Monitor Module - Comprehensive Service Health Checks
Purpose: Monitor all service dependencies and system metrics
Pattern: Circuit breaker with health status aggregation

IMPLEMENTATION STATUS: ✅ PRODUCTION READY
"""

import asyncio
import logging
import time
import psutil
from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime, timedelta

# Database imports
try:
    from database.connection import db_manager
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    logging.warning("Database connection not available")

# Redis imports
try:
    import redis.asyncio as redis
    from redis.exceptions import RedisError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logging.warning("Redis not available")

# HTTP client for external services
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logging.warning("httpx not available")

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status enumeration"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class DependencyHealth:
    """Health status for a single dependency"""

    def __init__(
        self,
        name: str,
        status: HealthStatus = HealthStatus.UNKNOWN,
        response_time_ms: float = 0.0,
        error: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.name = name
        self.status = status
        self.response_time_ms = response_time_ms
        self.error = error
        self.details = details or {}
        self.last_check = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "status": self.status.value,
            "response_time_ms": round(self.response_time_ms, 2),
            "error": self.error,
            "details": self.details,
            "last_check": self.last_check.isoformat()
        }


class SystemHealth:
    """Overall system health status"""

    def __init__(self):
        self.status = HealthStatus.UNKNOWN
        self.dependencies: Dict[str, DependencyHealth] = {}
        self.metrics: Dict[str, Any] = {}
        self.timestamp = datetime.now()

    def add_dependency(self, health: DependencyHealth):
        """Add dependency health status"""
        self.dependencies[health.name] = health

    def calculate_overall_status(self):
        """Calculate overall health status based on dependencies"""
        if not self.dependencies:
            self.status = HealthStatus.UNKNOWN
            return

        # Count statuses
        unhealthy_count = sum(
            1 for dep in self.dependencies.values()
            if dep.status == HealthStatus.UNHEALTHY
        )
        degraded_count = sum(
            1 for dep in self.dependencies.values()
            if dep.status == HealthStatus.DEGRADED
        )

        # Determine overall status
        if unhealthy_count > 0:
            # Critical dependencies are unhealthy
            if any(dep.name in ["postgres", "redis"] and dep.status == HealthStatus.UNHEALTHY
                   for dep in self.dependencies.values()):
                self.status = HealthStatus.UNHEALTHY
            else:
                self.status = HealthStatus.DEGRADED
        elif degraded_count > 0:
            self.status = HealthStatus.DEGRADED
        else:
            self.status = HealthStatus.HEALTHY

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "dependencies": {
                name: dep.to_dict()
                for name, dep in self.dependencies.items()
            },
            "metrics": self.metrics
        }


class HealthMonitor:
    """
    Comprehensive Health Monitoring System

    Features:
    - PostgreSQL connection monitoring
    - Redis connection monitoring
    - External API health checks
    - System resource metrics
    - Circuit breaker pattern
    - Health status aggregation
    - Performance tracking
    """

    def __init__(
        self,
        check_interval: int = 30,
        failure_threshold: int = 3,
        timeout_seconds: int = 5
    ):
        """
        Initialize Health Monitor

        Args:
            check_interval: Seconds between health checks
            failure_threshold: Consecutive failures before marking unhealthy
            timeout_seconds: Timeout for health check operations
        """
        self.check_interval = check_interval
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds

        # Track consecutive failures for circuit breaker
        self._failure_counts: Dict[str, int] = {}

        # Cache last health check results
        self._last_check: Optional[SystemHealth] = None
        self._last_check_time: Optional[datetime] = None

        # Background monitoring task
        self._monitor_task: Optional[asyncio.Task] = None
        self._monitoring_enabled = False

        logger.info(
            f"HealthMonitor initialized (interval={check_interval}s, "
            f"threshold={failure_threshold}, timeout={timeout_seconds}s)"
        )

    async def check_database_health(self) -> DependencyHealth:
        """
        Check PostgreSQL database health

        Returns:
            DependencyHealth status for database
        """
        start_time = time.time()

        if not DB_AVAILABLE:
            return DependencyHealth(
                name="postgres",
                status=HealthStatus.UNHEALTHY,
                error="Database module not available"
            )

        try:
            # Test database connection
            is_healthy = db_manager.health_check()
            response_time = (time.time() - start_time) * 1000

            if is_healthy:
                # Connection successful
                if response_time > 100:  # More than 100ms is degraded
                    status = HealthStatus.DEGRADED
                else:
                    status = HealthStatus.HEALTHY

                # Reset failure count on success
                self._failure_counts["postgres"] = 0

                return DependencyHealth(
                    name="postgres",
                    status=status,
                    response_time_ms=response_time,
                    details={
                        "connection_pool_size": db_manager.get_pool_size() if hasattr(db_manager, 'get_pool_size') else "N/A"
                    }
                )
            else:
                # Connection failed
                self._failure_counts["postgres"] = self._failure_counts.get("postgres", 0) + 1

                if self._failure_counts["postgres"] >= self.failure_threshold:
                    status = HealthStatus.UNHEALTHY
                else:
                    status = HealthStatus.DEGRADED

                return DependencyHealth(
                    name="postgres",
                    status=status,
                    response_time_ms=(time.time() - start_time) * 1000,
                    error="Health check returned False",
                    details={"consecutive_failures": self._failure_counts["postgres"]}
                )

        except Exception as e:
            # Exception during check
            self._failure_counts["postgres"] = self._failure_counts.get("postgres", 0) + 1

            return DependencyHealth(
                name="postgres",
                status=HealthStatus.UNHEALTHY,
                response_time_ms=(time.time() - start_time) * 1000,
                error=str(e),
                details={"consecutive_failures": self._failure_counts["postgres"]}
            )

    async def check_redis_health(self, redis_url: str) -> DependencyHealth:
        """
        Check Redis connection health

        Args:
            redis_url: Redis connection URL

        Returns:
            DependencyHealth status for Redis
        """
        start_time = time.time()

        if not REDIS_AVAILABLE:
            return DependencyHealth(
                name="redis",
                status=HealthStatus.DEGRADED,
                error="Redis module not available (optional dependency)"
            )

        try:
            # Create Redis connection
            redis_client = redis.from_url(
                redis_url,
                socket_connect_timeout=self.timeout_seconds,
                socket_timeout=self.timeout_seconds
            )

            # Test connection with ping
            await redis_client.ping()
            response_time = (time.time() - start_time) * 1000

            # Get Redis info
            info = await redis_client.info()

            # Close connection
            await redis_client.close()

            # Reset failure count on success
            self._failure_counts["redis"] = 0

            # Determine status based on response time
            if response_time > 50:  # More than 50ms is degraded for cache
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.HEALTHY

            return DependencyHealth(
                name="redis",
                status=status,
                response_time_ms=response_time,
                details={
                    "version": info.get("redis_version", "unknown"),
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory_human": info.get("used_memory_human", "unknown"),
                    "uptime_days": info.get("uptime_in_days", 0)
                }
            )

        except Exception as e:
            # Connection failed
            self._failure_counts["redis"] = self._failure_counts.get("redis", 0) + 1

            if self._failure_counts["redis"] >= self.failure_threshold:
                status = HealthStatus.UNHEALTHY
            else:
                status = HealthStatus.DEGRADED

            return DependencyHealth(
                name="redis",
                status=status,
                response_time_ms=(time.time() - start_time) * 1000,
                error=str(e),
                details={"consecutive_failures": self._failure_counts["redis"]}
            )

    async def check_external_api_health(self, name: str, url: str) -> DependencyHealth:
        """
        Check external API health

        Args:
            name: Service name (e.g., "technical_analysis", "bybit_connector")
            url: Service health endpoint URL

        Returns:
            DependencyHealth status for external API
        """
        start_time = time.time()

        if not HTTPX_AVAILABLE:
            return DependencyHealth(
                name=name,
                status=HealthStatus.DEGRADED,
                error="HTTP client not available"
            )

        try:
            # Make health check request
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url)
                response_time = (time.time() - start_time) * 1000

                if response.status_code == 200:
                    # API is healthy
                    self._failure_counts[name] = 0

                    # Check response time
                    if response_time > 200:  # More than 200ms is degraded
                        status = HealthStatus.DEGRADED
                    else:
                        status = HealthStatus.HEALTHY

                    # Try to parse response details
                    details = {}
                    try:
                        response_data = response.json()
                        if isinstance(response_data, dict):
                            details = {
                                "service_status": response_data.get("status", "unknown"),
                                "version": response_data.get("version", "unknown")
                            }
                    except:
                        pass

                    return DependencyHealth(
                        name=name,
                        status=status,
                        response_time_ms=response_time,
                        details=details
                    )
                else:
                    # Non-200 response
                    self._failure_counts[name] = self._failure_counts.get(name, 0) + 1

                    if self._failure_counts[name] >= self.failure_threshold:
                        status = HealthStatus.UNHEALTHY
                    else:
                        status = HealthStatus.DEGRADED

                    return DependencyHealth(
                        name=name,
                        status=status,
                        response_time_ms=response_time,
                        error=f"HTTP {response.status_code}",
                        details={"consecutive_failures": self._failure_counts[name]}
                    )

        except httpx.TimeoutException:
            # Timeout
            self._failure_counts[name] = self._failure_counts.get(name, 0) + 1

            return DependencyHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=(time.time() - start_time) * 1000,
                error=f"Timeout after {self.timeout_seconds}s",
                details={"consecutive_failures": self._failure_counts[name]}
            )

        except Exception as e:
            # Other errors
            self._failure_counts[name] = self._failure_counts.get(name, 0) + 1

            if self._failure_counts[name] >= self.failure_threshold:
                status = HealthStatus.UNHEALTHY
            else:
                status = HealthStatus.DEGRADED

            return DependencyHealth(
                name=name,
                status=status,
                response_time_ms=(time.time() - start_time) * 1000,
                error=str(e),
                details={"consecutive_failures": self._failure_counts[name]}
            )

    def get_system_metrics(self) -> Dict[str, Any]:
        """
        Get system resource metrics

        Returns:
            Dictionary with CPU, memory, and disk metrics
        """
        try:
            # Get CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)

            # Get memory usage
            memory = psutil.virtual_memory()

            # Get disk usage for root partition
            disk = psutil.disk_usage('/')

            # Get process-specific metrics
            process = psutil.Process()
            process_memory = process.memory_info()

            return {
                "cpu": {
                    "percent": round(cpu_percent, 2),
                    "count": psutil.cpu_count()
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
                    "threads": process.num_threads()
                }
            }

        except Exception as e:
            logger.error(f"Error getting system metrics: {e}")
            return {"error": str(e)}

    async def perform_health_check(
        self,
        postgres_enabled: bool = True,
        redis_url: Optional[str] = None,
        external_apis: Optional[Dict[str, str]] = None
    ) -> SystemHealth:
        """
        Perform comprehensive health check

        Args:
            postgres_enabled: Whether to check PostgreSQL
            redis_url: Redis URL to check (optional)
            external_apis: Dictionary of external API URLs to check

        Returns:
            SystemHealth with all dependency statuses
        """
        health = SystemHealth()

        # Check PostgreSQL
        if postgres_enabled:
            db_health = await self.check_database_health()
            health.add_dependency(db_health)

        # Check Redis
        if redis_url:
            redis_health = await self.check_redis_health(redis_url)
            health.add_dependency(redis_health)

        # Check external APIs
        if external_apis:
            # Check all APIs concurrently
            api_checks = [
                self.check_external_api_health(name, url)
                for name, url in external_apis.items()
            ]
            api_results = await asyncio.gather(*api_checks, return_exceptions=True)

            for result in api_results:
                if isinstance(result, DependencyHealth):
                    health.add_dependency(result)
                elif isinstance(result, Exception):
                    logger.error(f"Error during API health check: {result}")

        # Get system metrics
        health.metrics = self.get_system_metrics()

        # Calculate overall status
        health.calculate_overall_status()

        # Cache result
        self._last_check = health
        self._last_check_time = datetime.now()

        return health

    async def get_cached_health(self, max_age_seconds: int = 30) -> Optional[SystemHealth]:
        """
        Get cached health check result if recent enough

        Args:
            max_age_seconds: Maximum age of cached result in seconds

        Returns:
            Cached SystemHealth if available and recent, None otherwise
        """
        if self._last_check and self._last_check_time:
            age = (datetime.now() - self._last_check_time).total_seconds()
            if age <= max_age_seconds:
                return self._last_check

        return None

    async def start_monitoring(
        self,
        postgres_enabled: bool = True,
        redis_url: Optional[str] = None,
        external_apis: Optional[Dict[str, str]] = None
    ):
        """
        Start background health monitoring

        Args:
            postgres_enabled: Whether to monitor PostgreSQL
            redis_url: Redis URL to monitor
            external_apis: External APIs to monitor
        """
        if self._monitoring_enabled:
            logger.warning("Health monitoring already running")
            return

        self._monitoring_enabled = True

        async def monitor_loop():
            """Background monitoring loop"""
            logger.info("Health monitoring started")

            while self._monitoring_enabled:
                try:
                    # Perform health check
                    health = await self.perform_health_check(
                        postgres_enabled=postgres_enabled,
                        redis_url=redis_url,
                        external_apis=external_apis
                    )

                    # Log health status
                    if health.status == HealthStatus.UNHEALTHY:
                        logger.error(f"System health UNHEALTHY: {health.to_dict()}")
                    elif health.status == HealthStatus.DEGRADED:
                        logger.warning(f"System health DEGRADED: {health.to_dict()}")
                    else:
                        logger.debug(f"System health HEALTHY")

                except Exception as e:
                    logger.error(f"Error during health monitoring: {e}", exc_info=True)

                # Wait for next check
                await asyncio.sleep(self.check_interval)

        # Start monitoring task
        self._monitor_task = asyncio.create_task(monitor_loop())
        logger.info(f"Health monitoring task started (interval={self.check_interval}s)")

    async def stop_monitoring(self):
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

        logger.info("Health monitoring stopped")


# Global health monitor instance
_health_monitor: Optional[HealthMonitor] = None


def get_health_monitor() -> HealthMonitor:
    """
    Get or create global health monitor instance

    Returns:
        HealthMonitor instance
    """
    global _health_monitor

    if _health_monitor is None:
        _health_monitor = HealthMonitor(
            check_interval=30,
            failure_threshold=3,
            timeout_seconds=5
        )

    return _health_monitor
