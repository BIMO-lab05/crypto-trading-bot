"""
Portfolio Manager Service Configuration
Handles all service settings with validation
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Portfolio Manager configuration settings"""

    # Service Configuration
    service_name: str = Field(
        default="portfolio-manager", description="Service identifier"
    )
    service_port: int = Field(
        default=8003, ge=1024, le=65535, description="Service port"
    )
    log_level: str = Field(default="INFO", description="Logging level")

    # HTTP Configuration
    http_timeout: float = Field(
        default=30.0, ge=1.0, le=300.0, description="HTTP request timeout in seconds"
    )

    # Rate Limiting
    rate_limit_transactions_per_minute: int = Field(
        default=30, ge=1, le=1000, description="Maximum transactions allowed per minute"
    )
    enable_rate_limiting: bool = Field(
        default=True, description="Enable rate limiting for API endpoints"
    )

    # External Service URLs
    trading_engine_url: str = Field(
        default="http://localhost:8005", description="Trading Engine service URL"
    )
    market_data_url: str = Field(
        default="http://localhost:8002", description="Market Data service URL"
    )

    # Portfolio Settings
    # REQUIRED — no default, per owner spec 2026-08-04 (AUDIT.md §2.2
    # mechanism 2): this service previously received no capital env vars from
    # compose and silently ran on a hardcoded default, so operator edits could
    # never land. Missing config must raise at boot, never fall back. Wired in
    # docker-compose.unified.yml (INITIAL_CAPITAL); host runs must export it
    # explicitly. shared/account.py is the declaration of record for the value.
    initial_capital: float = Field(
        gt=0,
        description=(
            "Initial capital for portfolio tracking. Required via the "
            "INITIAL_CAPITAL env var; the service refuses to boot without it."
        ),
    )
    rebalance_threshold_pct: float = Field(
        default=5.0,
        ge=1.0,
        le=50.0,
        description="Portfolio rebalance threshold percentage",
    )
    max_positions: int = Field(
        default=10, ge=1, le=100, description="Maximum number of concurrent positions"
    )
    max_single_asset_pct: float = Field(
        default=20.0,
        ge=5.0,
        le=100.0,
        description="Maximum allocation to single asset (%)",
    )

    # Performance Calculation
    risk_free_rate: float = Field(
        default=0.02,
        ge=0.0,
        le=0.10,
        description="Risk-free rate for Sharpe ratio calculation",
    )
    benchmark_symbol: str = Field(
        default="BTCUSDT", description="Benchmark symbol for comparison"
    )

    # Database Configuration (Future)
    database_url: str = Field(
        default="postgresql://localhost:5432/trading_bot",
        description="Database connection URL",
    )
    use_database: bool = Field(default=False, description="Enable database persistence")

    # Model configuration
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the accepted values"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.upper()

    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, v: str) -> str:
        """Validate service name is not empty"""
        if not v or not v.strip():
            raise ValueError("Service name cannot be empty")
        return v.strip()


# Global settings instance
settings = Settings()
