"""
Bybit Connector Service - Configuration Management
Purpose: Manage service configuration using Pydantic Settings
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional
import os


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables
    Inherits from BaseSettings for automatic .env file loading
    """
    
    # ========================================================================
    # ENVIRONMENT
    # ========================================================================
    environment: str = Field(default="development", description="Deployment environment")
    log_level: str = Field(default="INFO", description="Logging level")
    debug: bool = Field(default=False, description="Debug mode")
    
    # ========================================================================
    # BYBIT API CONFIGURATION
    # ========================================================================
    bybit_api_key: str = Field(..., description="Bybit API key")
    bybit_api_secret: str = Field(..., description="Bybit API secret")
    bybit_testnet: bool = Field(default=True, description="Use testnet (true) or production (false)")
    bybit_recv_window: int = Field(default=5000, description="API request receive window in milliseconds")
    
    # ========================================================================
    # API ENDPOINTS
    # ========================================================================
    bybit_rest_url_testnet: str = Field(default="https://api-testnet.bybit.com", description="Testnet REST API URL")
    bybit_rest_url_mainnet: str = Field(default="https://api.bybit.com", description="Mainnet REST API URL")
    bybit_ws_url_testnet: str = Field(default="wss://stream-testnet.bybit.com/v5/public/linear", description="Testnet WebSocket URL")
    bybit_ws_url_mainnet: str = Field(default="wss://stream.bybit.com/v5/public/linear", description="Mainnet WebSocket URL")
    
    # ========================================================================
    # SERVICE CONFIGURATION
    # ========================================================================
    service_name: str = Field(default="bybit-connector", description="Service name")
    service_port: int = Field(default=8002, description="Service HTTP port")
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
    rabbitmq_password: str = Field(default="change_this_secure_password", description="RabbitMQ password")
    rabbitmq_vhost: str = Field(default="cryptobot", description="RabbitMQ virtual host")
    
    # ========================================================================
    # CIRCUIT BREAKER CONFIGURATION
    # ========================================================================
    circuit_breaker_failure_threshold: int = Field(default=5, description="Failures before circuit opens")
    circuit_breaker_recovery_timeout: int = Field(default=60, description="Seconds before attempting recovery")
    circuit_breaker_expected_exception: str = Field(default="Exception", description="Exception type to track")
    
    # ========================================================================
    # RETRY CONFIGURATION
    # ========================================================================
    max_retry_attempts: int = Field(default=3, description="Maximum retry attempts for failed requests")
    retry_base_delay: float = Field(default=1.0, description="Base delay for exponential backoff (seconds)")
    retry_max_delay: float = Field(default=60.0, description="Maximum delay between retries (seconds)")
    
    # ========================================================================
    # RATE LIMITING
    # ========================================================================
    rate_limit_requests_per_second: int = Field(default=10, description="Max requests per second")
    rate_limit_burst: int = Field(default=20, description="Burst allowance for rate limiting")
    
    # ========================================================================
    # WEBSOCKET CONFIGURATION
    # ========================================================================
    ws_ping_interval: int = Field(default=20, description="WebSocket ping interval (seconds)")
    ws_ping_timeout: int = Field(default=10, description="WebSocket ping timeout (seconds)")
    ws_reconnect_delay: int = Field(default=5, description="Delay before reconnect attempt (seconds)")
    ws_max_reconnect_attempts: int = Field(default=10, description="Maximum reconnection attempts")
    
    # ========================================================================
    # MONITORING
    # ========================================================================
    enable_metrics: bool = Field(default=True, description="Enable Prometheus metrics")
    metrics_port: int = Field(default=9090, description="Metrics endpoint port")
    
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

    @field_validator("bybit_api_key", "bybit_api_secret")
    @classmethod
    def validate_api_credentials(cls, v, info):
        """Validate API credentials are not empty"""
        if not v or v == f"your_{info.field_name}_here":
            raise ValueError(f"{info.field_name} must be set with valid credentials")
        return v

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
        return self.bybit_rest_url_testnet if self.bybit_testnet else self.bybit_rest_url_mainnet
    
    @property
    def websocket_url(self) -> str:
        """Get appropriate WebSocket URL based on testnet setting"""
        return self.bybit_ws_url_testnet if self.bybit_testnet else self.bybit_ws_url_mainnet
    
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
    
    # ========================================================================
    # CONFIG CLASS (Pydantic V2 syntax)
    # ========================================================================

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
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
                config_field="settings"
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
