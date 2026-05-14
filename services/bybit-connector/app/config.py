"""
Bybit Connector Service - Configuration Management
Purpose: Manage service configuration using Pydantic Settings
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, model_validator
from typing import List, Literal, Optional
from pathlib import Path


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables
    Inherits from BaseSettings for automatic .env file loading
    """

    # ========================================================================
    # ENVIRONMENT
    # ========================================================================
    environment: str = Field(
        default="development", description="Deployment environment"
    )
    log_level: str = Field(default="INFO", description="Logging level")
    debug: bool = Field(default=False, description="Debug mode")

    # ========================================================================
    # BYBIT API CONFIGURATION
    # ========================================================================
    bybit_api_key: str = Field(default="", description="Bybit API key")
    bybit_api_secret: str = Field(default="", description="Bybit API secret")
    bybit_testnet: bool = Field(
        default=False,
        description="Use testnet (true) or production (false). Default False — production prices. Set BYBIT_TESTNET=true explicitly for testnet.",
    )
    bybit_recv_window: int = Field(
        default=5000, description="API request receive window in milliseconds"
    )

    # ========================================================================
    # MARKET DATA SOURCE SELECTOR (D-14, D-15, D-17)
    # ========================================================================
    market_data_source: Literal["tape", "live"] = Field(
        default="tape",
        description="Source for Bybit market data: 'tape' replays JSONL fixtures, 'live' hits real Bybit REST/WS",
    )
    tape_fixtures_path: Path = Field(
        default=Path("/app/tests/fixtures/tape"),
        description="In-container path to tape JSONL fixtures (bind-mounted RO from repo tests/fixtures/tape)",
    )

    # ========================================================================
    # API ENDPOINTS
    # ========================================================================
    bybit_rest_url_testnet: str = Field(
        default="https://api-testnet.bybit.com", description="Testnet REST API URL"
    )
    bybit_rest_url_mainnet: str = Field(
        default="https://api.bybit.com", description="Mainnet REST API URL"
    )
    bybit_ws_url_testnet: str = Field(
        default="wss://stream-testnet.bybit.com/v5/public/linear",
        description="Testnet WebSocket URL",
    )
    bybit_ws_url_mainnet: str = Field(
        default="wss://stream.bybit.com/v5/public/linear",
        description="Mainnet WebSocket URL",
    )

    # ========================================================================
    # SERVICE CONFIGURATION
    # ========================================================================
    service_name: str = Field(default="bybit-connector", description="Service name")
    service_port: int = Field(default=8001, description="Service HTTP port")
    service_host: str = Field(default="0.0.0.0", description="Service bind host")

    # ========================================================================
    # REDIS CONFIGURATION (for caching)
    # ========================================================================
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    redis_db: int = Field(default=0, description="Redis database number")

    # ========================================================================
    # RABBITMQ CONFIGURATION (for messaging)
    # ========================================================================
    rabbitmq_host: str = Field(default="localhost", description="RabbitMQ host")
    rabbitmq_port: int = Field(default=5672, description="RabbitMQ port")
    rabbitmq_user: str = Field(default="cryptobot", description="RabbitMQ username")
    rabbitmq_password: str = Field(
        default="change_this_secure_password", description="RabbitMQ password"
    )
    rabbitmq_vhost: str = Field(
        default="cryptobot", description="RabbitMQ virtual host"
    )

    # ========================================================================
    # CIRCUIT BREAKER CONFIGURATION
    # ========================================================================
    circuit_breaker_failure_threshold: int = Field(
        default=5, description="Failures before circuit opens"
    )
    circuit_breaker_recovery_timeout: int = Field(
        default=60, description="Seconds before attempting recovery"
    )
    circuit_breaker_expected_exception: str = Field(
        default="Exception", description="Exception type to track"
    )

    # ========================================================================
    # RETRY CONFIGURATION
    # ========================================================================
    max_retry_attempts: int = Field(
        default=3, description="Maximum retry attempts for failed requests"
    )
    retry_base_delay: float = Field(
        default=1.0, description="Base delay for exponential backoff (seconds)"
    )
    retry_max_delay: float = Field(
        default=60.0, description="Maximum delay between retries (seconds)"
    )

    # ========================================================================
    # RATE LIMITING
    # ========================================================================
    rate_limit_requests_per_second: int = Field(
        default=10, description="Max requests per second"
    )
    rate_limit_burst: int = Field(
        default=20, description="Burst allowance for rate limiting"
    )

    # ========================================================================
    # WEBSOCKET CONFIGURATION
    # ========================================================================
    ws_ping_interval: int = Field(
        default=20, description="WebSocket ping interval (seconds)"
    )
    ws_ping_timeout: int = Field(
        default=10, description="WebSocket ping timeout (seconds)"
    )
    ws_reconnect_delay: int = Field(
        default=5, description="Delay before reconnect attempt (seconds)"
    )
    ws_max_reconnect_attempts: int = Field(
        default=10, description="Maximum reconnection attempts"
    )

    # ========================================================================
    # MONITORING
    # ========================================================================
    enable_metrics: bool = Field(default=True, description="Enable Prometheus metrics")
    metrics_port: int = Field(default=9090, description="Metrics endpoint port")

    # ========================================================================
    # SECURITY — CORS (BL-04: never `*` with credentials; spec violation)
    # ========================================================================
    cors_origins: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
        ],
        description="Allowed CORS origins (no wildcards in production)",
    )
    internal_service_origins: List[str] = Field(
        default=[
            "http://api-gateway:8000",
            "http://localhost:8000",
            "http://localhost:8001",
            "http://localhost:8002",
            "http://localhost:8003",
            "http://localhost:8004",
            "http://localhost:8005",
            "http://localhost:8006",
            "http://localhost:8007",
            "http://localhost:8008",
        ],
        description="Internal microservice origins for inter-service communication",
    )

    @property
    def all_cors_origins(self) -> List[str]:
        """Get combined list of all allowed CORS origins."""
        return list(set(self.cors_origins + self.internal_service_origins))

    # ========================================================================
    # VALIDATORS (Pydantic V2 syntax)
    # ========================================================================

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level is valid"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.upper()

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v):
        """Validate environment is valid"""
        valid_envs = ["development", "staging", "production"]
        if v.lower() not in valid_envs:
            raise ValueError(f"Environment must be one of {valid_envs}")
        return v.lower()

    @model_validator(mode="after")
    def validate_api_credentials(self):
        """Require non-empty Bybit credentials only in live mode (D-17 — tape mode bypasses auth)."""
        if self.market_data_source == "live":
            for field_name in ("bybit_api_key", "bybit_api_secret"):
                v = getattr(self, field_name)
                if not v or v == f"your_{field_name}_here":
                    raise ValueError(
                        f"{field_name} must be set with valid credentials when market_data_source='live'"
                    )
        return self

    @field_validator("service_port", "redis_port", "rabbitmq_port", "metrics_port")
    @classmethod
    def validate_port(cls, v, info):
        """Validate port numbers are in valid range"""
        if not 1 <= v <= 65535:
            raise ValueError(f"{info.field_name} must be between 1 and 65535")
        return v

    # ========================================================================
    # COMPUTED PROPERTIES
    # ========================================================================

    @property
    def rest_api_url(self) -> str:
        """Get appropriate REST API URL based on testnet setting"""
        return (
            self.bybit_rest_url_testnet
            if self.bybit_testnet
            else self.bybit_rest_url_mainnet
        )

    @property
    def websocket_url(self) -> str:
        """Get appropriate WebSocket URL based on testnet setting"""
        return (
            self.bybit_ws_url_testnet
            if self.bybit_testnet
            else self.bybit_ws_url_mainnet
        )

    @property
    def redis_url(self) -> str:
        """Construct Redis connection URL"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def rabbitmq_url(self) -> str:
        """Construct RabbitMQ connection URL"""
        return f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}@{self.rabbitmq_host}:{self.rabbitmq_port}/{self.rabbitmq_vhost}"

    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.environment == "production"

    @property
    def is_testnet(self) -> bool:
        """Check if using testnet"""
        return self.bybit_testnet

    @property
    def is_tape_mode(self) -> bool:
        """True when market data is replayed from JSONL fixtures (D-15)."""
        return self.market_data_source == "tape"

    # ========================================================================
    # CONFIG CLASS (Pydantic V2 syntax)
    # ========================================================================

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


# Global settings instance
# This will be loaded once and reused throughout the application
settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get application settings (singleton pattern)

    Returns:
        Settings instance

    Raises:
        ConfigurationException: If settings cannot be loaded
    """
    global settings

    if settings is None:
        try:
            settings = Settings()
        except Exception as e:
            from app.exceptions import ConfigurationException

            raise ConfigurationException(
                message=f"Failed to load configuration: {str(e)}",
                config_field="settings",
            )

    return settings


def reload_settings() -> Settings:
    """
    Reload settings from environment (useful for testing)

    Returns:
        New Settings instance
    """
    global settings
    settings = None
    return get_settings()
