"""
Vault-Aware Configuration Base Class
Purpose: Provides Vault integration for service configurations
Author: Security Engineer Agent
Date: 2025-11-21
Version: 1.0

This module provides a base configuration class that automatically
loads secrets from HashiCorp Vault instead of environment variables.
"""

import os
import logging
from typing import Optional, Dict, Any, Type
from pydantic import Field
from pydantic_settings import BaseSettings
from functools import lru_cache

from shared.vault_client import VaultClient, VaultConnectionError

logger = logging.getLogger(__name__)


class VaultConfigMixin:
    """
    Mixin to add Vault support to Pydantic Settings classes

    This mixin provides methods to load configuration from Vault
    and automatically fall back to environment variables if Vault
    is not available (for development/testing).

    Usage:
        class ServiceConfig(BaseSettings, VaultConfigMixin):
            vault_enabled: bool = Field(default=True)
            service_name: str = Field(default="my-service")

            @property
            def database_password(self) -> str:
                return self.get_vault_secret(
                    path=f"{self.service_name}/database",
                    key="password",
                    fallback_env="DATABASE_PASSWORD"
                )
    """

    _vault_client: Optional[VaultClient] = None
    _vault_enabled: bool = True

    @classmethod
    def get_vault_client(cls) -> Optional[VaultClient]:
        """
        Get or create Vault client instance

        Returns:
            VaultClient instance or None if Vault is not available
        """
        if not cls._vault_enabled:
            return None

        if cls._vault_client is None:
            try:
                cls._vault_client = VaultClient(
                    vault_addr=os.getenv("VAULT_ADDR"),
                    vault_token=os.getenv("VAULT_TOKEN"),
                    auto_renew_token=True
                )
                logger.info("Vault client initialized successfully")
            except VaultConnectionError as e:
                logger.warning(f"Vault not available, using environment variables: {e}")
                cls._vault_enabled = False
                cls._vault_client = None

        return cls._vault_client

    def get_vault_secret(
        self,
        path: str,
        key: str,
        fallback_env: Optional[str] = None,
        required: bool = True,
        use_cache: bool = True
    ) -> Optional[str]:
        """
        Get secret from Vault with automatic fallback to environment

        Args:
            path: Vault secret path (e.g., "service-name/database")
            key: Key within the secret
            fallback_env: Environment variable to use if Vault unavailable
            required: If True, raise error if secret not found
            use_cache: Use cached value if available

        Returns:
            Secret value or None if not found and not required

        Raises:
            ValueError: If secret is required but not found

        Example:
            >>> config = ServiceConfig()
            >>> password = config.get_vault_secret(
            ...     path="trading-engine/database",
            ...     key="password",
            ...     fallback_env="DATABASE_PASSWORD"
            ... )
        """
        vault = self.get_vault_client()

        # Try Vault first
        if vault is not None:
            try:
                secret_data = vault.read_secret(path, use_cache=use_cache)
                value = secret_data.get(key)

                if value is not None:
                    logger.debug(f"Loaded {key} from Vault: {path}")
                    return value
                else:
                    logger.warning(f"Key {key} not found in Vault secret: {path}")

            except Exception as e:
                logger.warning(f"Failed to read from Vault {path}/{key}: {e}")

        # Fall back to environment variable
        if fallback_env:
            value = os.getenv(fallback_env)
            if value is not None:
                logger.debug(f"Loaded {key} from environment: {fallback_env}")
                return value

        # Not found anywhere
        if required:
            error_msg = f"Required secret not found: {path}/{key}"
            if fallback_env:
                error_msg += f" (fallback env: {fallback_env})"
            logger.error(error_msg)
            raise ValueError(error_msg)

        return None

    def get_vault_secret_dict(
        self,
        path: str,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Get entire secret dictionary from Vault

        Args:
            path: Vault secret path
            use_cache: Use cached value if available

        Returns:
            Dictionary of secret key-value pairs

        Example:
            >>> config = ServiceConfig()
            >>> db_creds = config.get_vault_secret_dict("trading-engine/database")
            >>> print(db_creds['username'], db_creds['password'])
        """
        vault = self.get_vault_client()

        if vault is not None:
            try:
                return vault.read_secret(path, use_cache=use_cache)
            except Exception as e:
                logger.warning(f"Failed to read from Vault {path}: {e}")

        return {}

    def reload_secrets(self):
        """
        Force reload of all secrets from Vault (clear cache)

        This should be called when receiving a reload signal
        """
        vault = self.get_vault_client()
        if vault is not None:
            vault._clear_cache()
            logger.info("Vault secret cache cleared")

    @classmethod
    def close_vault_client(cls):
        """Close Vault client and cleanup resources"""
        if cls._vault_client is not None:
            cls._vault_client.close()
            cls._vault_client = None
            logger.info("Vault client closed")


class VaultAwareSettings(BaseSettings, VaultConfigMixin):
    """
    Base settings class with Vault integration

    All service configuration classes should inherit from this
    instead of BaseSettings directly.

    Attributes:
        service_name: Name of the service (used for Vault paths)
        vault_enabled: Whether to use Vault for secrets
        vault_addr: Vault server address
        vault_token: Vault authentication token
    """

    service_name: str = Field(
        default="crypto-trading-bot",
        description="Service name for Vault path resolution"
    )

    vault_enabled: bool = Field(
        default=True,
        description="Enable Vault secret management"
    )

    vault_addr: Optional[str] = Field(
        default=None,
        description="Vault server address"
    )

    vault_token: Optional[str] = Field(
        default=None,
        description="Vault authentication token"
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }

    def model_post_init(self, __context):
        """Initialize Vault client after model creation"""
        if self.vault_enabled:
            # Set environment variables for Vault client
            if self.vault_addr:
                os.environ["VAULT_ADDR"] = self.vault_addr
            if self.vault_token:
                os.environ["VAULT_TOKEN"] = self.vault_token

            # Initialize Vault client
            self.get_vault_client()


# Example service configuration using Vault
class ExampleServiceConfig(VaultAwareSettings):
    """
    Example service configuration with Vault integration

    This demonstrates how to create a service configuration
    that automatically loads secrets from Vault.
    """

    service_name: str = Field(default="example-service")

    # Non-secret configuration (still from environment)
    service_port: int = Field(default=8000)
    log_level: str = Field(default="INFO")
    debug: bool = Field(default=False)

    # Database configuration
    database_host: str = Field(default="localhost")
    database_port: int = Field(default=5432)
    database_name: str = Field(default="cryptobot")

    # Properties that load from Vault
    @property
    def database_username(self) -> str:
        """Get database username from Vault"""
        return self.get_vault_secret(
            path=f"{self.service_name}/database/postgres",
            key="username",
            fallback_env="POSTGRES_USER",
            required=True
        )

    @property
    def database_password(self) -> str:
        """Get database password from Vault"""
        return self.get_vault_secret(
            path=f"{self.service_name}/database/postgres",
            key="password",
            fallback_env="POSTGRES_PASSWORD",
            required=True
        )

    @property
    def database_url(self) -> str:
        """Construct database URL with Vault credentials"""
        return (
            f"postgresql://{self.database_username}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )

    @property
    def redis_password(self) -> str:
        """Get Redis password from Vault"""
        return self.get_vault_secret(
            path=f"{self.service_name}/redis",
            key="password",
            fallback_env="REDIS_PASSWORD",
            required=True
        )

    @property
    def redis_url(self) -> str:
        """Construct Redis URL with Vault credentials"""
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = os.getenv("REDIS_PORT", "6379")
        redis_db = os.getenv("REDIS_DB", "0")

        return f"redis://:{self.redis_password}@{redis_host}:{redis_port}/{redis_db}"

    @property
    def rabbitmq_password(self) -> str:
        """Get RabbitMQ password from Vault"""
        return self.get_vault_secret(
            path=f"{self.service_name}/rabbitmq",
            key="password",
            fallback_env="RABBITMQ_PASSWORD",
            required=True
        )

    @property
    def rabbitmq_url(self) -> str:
        """Construct RabbitMQ URL with Vault credentials"""
        rabbitmq_host = os.getenv("RABBITMQ_HOST", "localhost")
        rabbitmq_port = os.getenv("RABBITMQ_PORT", "5672")
        rabbitmq_user = os.getenv("RABBITMQ_USER", "cryptobot")
        rabbitmq_vhost = os.getenv("RABBITMQ_VHOST", "cryptobot")

        return (
            f"amqp://{rabbitmq_user}:{self.rabbitmq_password}"
            f"@{rabbitmq_host}:{rabbitmq_port}/{rabbitmq_vhost}"
        )


@lru_cache
def get_service_config(config_class: Type[VaultAwareSettings]) -> VaultAwareSettings:
    """
    Get cached service configuration instance

    Args:
        config_class: Configuration class to instantiate

    Returns:
        Configuration instance (cached)

    Example:
        >>> config = get_service_config(ExampleServiceConfig)
        >>> print(config.database_url)
    """
    return config_class()


def reload_service_config():
    """
    Reload service configuration (clear cache and reload secrets)

    This should be called when receiving a reload signal from
    the secret rotation system.
    """
    # Clear LRU cache
    get_service_config.cache_clear()

    # Clear Vault cache
    VaultConfigMixin.get_vault_client().clear_cache() if VaultConfigMixin.get_vault_client() else None

    logger.info("Service configuration reloaded")
