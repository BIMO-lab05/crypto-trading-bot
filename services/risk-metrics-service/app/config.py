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
    #
    # Defaults align with PAPER-mode operating range (ADR-010, ADR-017):
    #   - trading-engine paper: max_risk_per_trade=0.10 (10%/trade)
    #   - ensemble sizing produces 5-10% positions per symbol
    #   - 5 active symbols → expected gross 25-50% under normal operation
    # Older 0.02/0.20 defaults were sized for the pre-ADR-010 2%/trade era
    # and caused the CB to false-trip every loop in paper mode (observed
    # 2026-05-19: real exposure 32.5% > old 24% trip threshold).
    #
    # For LIVE mode, override via env vars in deployment config:
    #   MAX_POSITION_SIZE=0.02 (matches 2% LIVE per-trade cap)
    #   MAX_EXPOSURE=0.20 (matches tighter live risk budget)
    max_portfolio_risk: float = 0.05  # 5% max portfolio risk
    max_position_size: float = 0.10  # 10% per-position alert threshold (paper)
    max_drawdown_threshold: float = 0.10  # 10% max drawdown before alert
    max_daily_loss: float = 0.05  # 5% daily loss limit
    max_exposure: float = 0.50  # 50% max gross exposure (paper)

    # Performance Metrics
    risk_free_rate: float = 0.04  # 4% annual risk-free rate
    target_sharpe_ratio: float = 1.5  # Target Sharpe ratio
    lookback_period_days: int = 30  # Lookback period for metrics

    # Circuit Breakers - Advanced Configuration
    enable_circuit_breaker: bool = True
    circuit_breaker_cooldown: int = 300  # Base cooldown in seconds (5 minutes)

    # Circuit Breaker State Machine Settings
    circuit_breaker_half_open_max_requests: int = 1  # Max requests in HALF_OPEN state
    circuit_breaker_failure_threshold: int = (
        3  # Consecutive failures before extending cooldown
    )
    circuit_breaker_cooldown_multiplier: float = (
        2.0  # Multiply cooldown on repeated failures
    )
    circuit_breaker_max_cooldown: int = 3600  # Maximum cooldown period (1 hour)

    # Circuit Breaker Trip Thresholds (can differ from alerting thresholds)
    circuit_breaker_daily_loss_threshold: float = 0.05  # 5% daily loss trips breaker
    circuit_breaker_drawdown_threshold: float = 0.10  # 10% drawdown trips breaker
    circuit_breaker_exposure_multiplier: float = 1.2  # 1.2x max_exposure trips breaker

    # Authentication - Admin API key for protected endpoints
    admin_api_key: str = "dev-admin-key-change-in-production"

    # CORS Configuration
    allowed_origins: str = "http://localhost:3000,http://localhost:5173"

    # Connection settings
    connection_timeout: float = 10.0  # Default timeout for external connections

    # Database
    database_url: Optional[str] = None

    # Redis Cache Configuration
    redis_enabled: bool = True
    redis_host: str = "localhost"  # Use REDIS_HOST env var in Docker
    redis_port: int = 6379
    redis_password: Optional[str] = None  # Use REDIS_PASSWORD env var in Docker
    redis_cache_ttl: int = 30  # Cache TTL in seconds (30s for high-frequency updates)

    @property
    def redis_url(self) -> str:
        """Construct Redis URL from host, port, and optional password"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}"
        return f"redis://{self.redis_host}:{self.redis_port}"

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
