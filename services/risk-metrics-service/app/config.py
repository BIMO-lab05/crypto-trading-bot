"""
Configuration for Risk & Metrics Service
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Service configuration settings"""

    # Service Configuration
    service_name: str = "risk-metrics-service"
    service_port: int = 8009
    service_host: str = "0.0.0.0"
    log_level: str = "INFO"

    # External Services
    portfolio_manager_url: str = "http://localhost:8003"
    market_data_url: str = "http://localhost:8002"

    # Risk Management Parameters
    max_portfolio_risk: float = 0.05  # 5% max portfolio risk
    max_position_size: float = 0.02   # 2% max per position
    max_drawdown_threshold: float = 0.10  # 10% max drawdown before alert
    max_daily_loss: float = 0.05      # 5% daily loss limit
    max_exposure: float = 0.20        # 20% max total exposure

    # Performance Metrics
    risk_free_rate: float = 0.04      # 4% annual risk-free rate
    target_sharpe_ratio: float = 1.5  # Target Sharpe ratio
    lookback_period_days: int = 30    # Lookback period for metrics

    # Circuit Breakers - Advanced Configuration
    enable_circuit_breaker: bool = True
    circuit_breaker_cooldown: int = 300  # Base cooldown in seconds (5 minutes)

    # Circuit Breaker State Machine Settings
    circuit_breaker_half_open_max_requests: int = 1  # Max requests in HALF_OPEN state
    circuit_breaker_failure_threshold: int = 3  # Consecutive failures before extending cooldown
    circuit_breaker_cooldown_multiplier: float = 2.0  # Multiply cooldown on repeated failures
    circuit_breaker_max_cooldown: int = 3600  # Maximum cooldown period (1 hour)

    # Circuit Breaker Trip Thresholds (can differ from alerting thresholds)
    circuit_breaker_daily_loss_threshold: float = 0.05  # 5% daily loss trips breaker
    circuit_breaker_drawdown_threshold: float = 0.10  # 10% drawdown trips breaker
    circuit_breaker_exposure_multiplier: float = 1.2  # 1.2x max_exposure trips breaker

    # Authentication - Admin API key for protected endpoints
    admin_api_key: str = "dev-admin-key-change-in-production"

    # Connection settings
    connection_timeout: float = 10.0  # Default timeout for external connections

    # Database
    database_url: Optional[str] = None

    # Redis Cache Configuration
    redis_enabled: bool = True
    redis_url: str = "redis://localhost:6379"
    redis_cache_ttl: int = 30  # Cache TTL in seconds (30s for high-frequency updates)

    # HTTP Connection Pool Configuration
    max_http_connections: int = 100  # Maximum concurrent HTTP connections
    http_timeout: float = 10.0  # HTTP request timeout in seconds

    # Request Batching Configuration
    enable_request_batching: bool = True
    batch_size: int = 10  # Process requests in batches of 10
    batch_max_wait_ms: int = 50  # Maximum wait time before processing batch

    # Performance Monitoring
    enable_performance_monitoring: bool = True
    performance_history_size: int = 1000  # Keep last 1000 metrics in memory

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
