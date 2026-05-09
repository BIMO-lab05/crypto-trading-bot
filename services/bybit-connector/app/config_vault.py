"""
Bybit Connector Service - Vault-Integrated Configuration
Purpose: Configuration management with HashiCorp Vault integration
Author: Security Engineer Agent
Date: 2025-11-21
Version: 2.0

This replaces config.py with Vault-aware configuration that:
- Loads secrets from Vault automatically
- Falls back to environment variables for development
- Supports automatic secret rotation
- Provides audit logging
"""

import sys
from pathlib import Path

# Add shared directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'shared'))

from vault_config import VaultAwareSettings
from pydantic import Field, field_validator
from typing import Optional


class BybitConnectorConfig(VaultAwareSettings):
    """
    Bybit Connector configuration with Vault integration

    This configuration class automatically loads secrets from Vault
    when available, with fallback to environment variables for
    development and testing.

    Vault Secret Paths:
    - API credentials: secret/bybit-connector/bybit
    - Redis config: secret/bybit-connector/redis
    - RabbitMQ config: secret/bybit-connector/rabbitmq

    Example Usage:
        >>> config = BybitConnectorConfig()
        >>> api_key = config.bybit_api_key  # Loaded from Vault
        >>> print(api_key)
    """

    # ========================================================================
    # SERVICE IDENTITY
    # ========================================================================
    service_name: str = Field(
        default="bybit-connector",
        description="Service name for Vault path resolution"
    )

    # ========================================================================
    # ENVIRONMENT CONFIGURATION (Non-Secret)
    # ========================================================================
    environment: str = Field(
        default="development",
        description="Deployment environment"
    )

    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )

    debug: bool = Field(
        default=False,
        description="Debug mode"
    )

    # ========================================================================
    # SERVICE CONFIGURATION (Non-Secret)
    # ========================================================================
    service_port: int = Field(
        default=8002,
        description="Service HTTP port"
    )

    service_host: str = Field(
        default="0.0.0.0",
        description="Service bind host"
    )

    # ========================================================================
    # BYBIT API CONFIGURATION (Non-Secret)
    # ========================================================================
    bybit_testnet: bool = Field(
        default=False,
        description="Use testnet (true) or production (false). Default False — production prices. Set BYBIT_TESTNET=true explicitly for testnet."
    )

    bybit_recv_window: int = Field(
        default=5000,
        description="API request receive window in milliseconds"
    )

    bybit_rest_url_testnet: str = Field(
        default="https://api-testnet.bybit.com",
        description="Testnet REST API URL"
    )

    bybit_rest_url_mainnet: str = Field(
        default="https://api.bybit.com",
        description="Mainnet REST API URL"
    )

    bybit_ws_url_testnet: str = Field(
        default="wss://stream-testnet.bybit.com/v5/public/linear",
        description="Testnet WebSocket URL"
    )

    bybit_ws_url_mainnet: str = Field(
        default="wss://stream.bybit.com/v5/public/linear",
        description="Mainnet WebSocket URL"
    )

    # ========================================================================
    # REDIS CONFIGURATION (Non-Secret)
    # ========================================================================
    redis_host: str = Field(
        default="localhost",
        description="Redis host"
    )

    redis_port: int = Field(
        default=6379,
        description="Redis port"
    )

    redis_db: int = Field(
        default=0,
        description="Redis database number"
    )

    # ========================================================================
    # RABBITMQ CONFIGURATION (Non-Secret)
    # ========================================================================
    rabbitmq_host: str = Field(
        default="localhost",
        description="RabbitMQ host"
    )

    rabbitmq_port: int = Field(
        default=5672,
        description="RabbitMQ port"
    )

    rabbitmq_user: str = Field(
        default="cryptobot",
        description="RabbitMQ username"
    )

    rabbitmq_vhost: str = Field(
        default="cryptobot",
        description="RabbitMQ virtual host"
    )

    # ========================================================================
    # CIRCUIT BREAKER CONFIGURATION
    # ========================================================================
    circuit_breaker_failure_threshold: int = Field(
        default=5,
        description="Failures before circuit opens"
    )

    circuit_breaker_recovery_timeout: int = Field(
        default=60,
        description="Seconds before attempting recovery"
    )

    # ========================================================================
    # RETRY CONFIGURATION
    # ========================================================================
    max_retry_attempts: int = Field(
        default=3,
        description="Maximum retry attempts for failed requests"
    )

    retry_base_delay: float = Field(
        default=1.0,
        description="Base delay for exponential backoff (seconds)"
    )

    retry_max_delay: float = Field(
        default=60.0,
        description="Maximum delay between retries (seconds)"
    )

    # ========================================================================
    # RATE LIMITING
    # ========================================================================
    rate_limit_requests_per_second: int = Field(
        default=10,
        description="Max requests per second"
    )

    rate_limit_burst: int = Field(
        default=20,
        description="Burst allowance for rate limiting"
    )

    # ========================================================================
    # WEBSOCKET CONFIGURATION
    # ========================================================================
    ws_ping_interval: int = Field(
        default=20,
        description="WebSocket ping interval (seconds)"
    )

    ws_ping_timeout: int = Field(
        default=10,
        description="WebSocket ping timeout (seconds)"
    )

    ws_reconnect_delay: int = Field(
        default=5,
        description="Delay before reconnect attempt (seconds)"
    )

    ws_max_reconnect_attempts: int = Field(
        default=10,
        description="Maximum reconnection attempts"
    )

    # ========================================================================
    # MONITORING
    # ========================================================================
    enable_metrics: bool = Field(
        default=True,
        description="Enable Prometheus metrics"
    )

    metrics_port: int = Field(
        default=9090,
        description="Metrics endpoint port"
    )

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

    @field_validator("service_port", "redis_port", "rabbitmq_port", "metrics_port")
    @classmethod
    def validate_port(cls, v, info):
        """Validate port numbers are in valid range"""
        if not 1 <= v <= 65535:
            raise ValueError(f"{info.field_name} must be between 1 and 65535")
        return v

    # ========================================================================
    # VAULT-BACKED SECRET PROPERTIES
    # ========================================================================

    @property
    def bybit_api_key(self) -> str:
        """
        Get Bybit API key from Vault

        Vault path: secret/bybit-connector/bybit
        Fallback: BYBIT_API_KEY environment variable
        """
        return self.get_vault_secret(
            path=f"{self.service_name}/bybit",
            key="BYBIT_API_KEY",
            fallback_env="BYBIT_API_KEY",
            required=True
        )

    @property
    def bybit_api_secret(self) -> str:
        """
        Get Bybit API secret from Vault

        Vault path: secret/bybit-connector/bybit
        Fallback: BYBIT_API_SECRET environment variable
        """
        return self.get_vault_secret(
            path=f"{self.service_name}/bybit",
            key="BYBIT_API_SECRET",
            fallback_env="BYBIT_API_SECRET",
            required=True
        )

    @property
    def redis_password(self) -> Optional[str]:
        """
        Get Redis password from Vault

        Vault path: secret/bybit-connector/redis
        Fallback: REDIS_PASSWORD environment variable
        """
        return self.get_vault_secret(
            path=f"{self.service_name}/redis",
            key="password",
            fallback_env="REDIS_PASSWORD",
            required=False
        )

    @property
    def rabbitmq_password(self) -> str:
        """
        Get RabbitMQ password from Vault

        Vault path: secret/bybit-connector/rabbitmq
        Fallback: RABBITMQ_PASSWORD environment variable
        """
        return self.get_vault_secret(
            path=f"{self.service_name}/rabbitmq",
            key="password",
            fallback_env="RABBITMQ_PASSWORD",
            required=True
        )

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
        """Construct Redis connection URL with Vault credentials"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def rabbitmq_url(self) -> str:
        """Construct RabbitMQ connection URL with Vault credentials"""
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/{self.rabbitmq_vhost}"
        )

    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.environment == "production"

    @property
    def is_testnet(self) -> bool:
        """Check if using testnet"""
        return self.bybit_testnet


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_config_instance: Optional[BybitConnectorConfig] = None


def get_config() -> BybitConnectorConfig:
    """
    Get configuration instance (singleton pattern)

    Returns:
        BybitConnectorConfig instance

    Example:
        >>> config = get_config()
        >>> print(config.bybit_api_key)  # Loaded from Vault
    """
    global _config_instance

    if _config_instance is None:
        _config_instance = BybitConnectorConfig()

    return _config_instance


def reload_config() -> BybitConnectorConfig:
    """
    Reload configuration from Vault (useful after secret rotation)

    This clears the singleton and Vault cache, forcing a fresh
    load of all configuration values.

    Returns:
        New BybitConnectorConfig instance

    Example:
        >>> # After secret rotation
        >>> config = reload_config()
        >>> # Now using new credentials
    """
    global _config_instance

    # Clear Vault cache
    if _config_instance is not None:
        _config_instance.reload_secrets()

    # Create new instance
    _config_instance = None
    return get_config()


# ============================================================================
# MIGRATION HELPER
# ============================================================================

def migrate_from_old_config():
    """
    Helper function to migrate from old config.py to Vault-based config

    This function helps during the transition period by comparing
    old environment-based config with new Vault-based config.

    Usage:
        >>> migrate_from_old_config()
    """
    print("=" * 80)
    print("Configuration Migration Check")
    print("=" * 80)

    try:
        # Try to load new Vault-based config
        new_config = get_config()
        print("✓ Successfully loaded Vault-based configuration")

        # Test Vault connection
        vault_client = new_config.get_vault_client()
        if vault_client:
            health = vault_client.health_check()
            if health['healthy']:
                print("✓ Vault connection healthy")
            else:
                print("✗ Vault connection unhealthy:", health.get('error'))
        else:
            print("⚠ Vault not available, using environment variables")

        # Test secret retrieval
        try:
            api_key = new_config.bybit_api_key
            print(f"✓ Successfully retrieved Bybit API key: {api_key[:10]}...")
        except Exception as e:
            print(f"✗ Failed to retrieve Bybit API key: {e}")

        print("\nConfiguration values:")
        print(f"  Service: {new_config.service_name}")
        print(f"  Environment: {new_config.environment}")
        print(f"  Port: {new_config.service_port}")
        print(f"  Testnet: {new_config.bybit_testnet}")
        print(f"  REST URL: {new_config.rest_api_url}")
        print(f"  Redis URL: {new_config.redis_url}")

        print("=" * 80)
        print("Migration check complete!")
        print("=" * 80)

    except Exception as e:
        print(f"✗ Configuration migration failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run migration check if executed directly
    migrate_from_old_config()
