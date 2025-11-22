#!/usr/bin/env python3
"""
HashiCorp Vault Client for Crypto Trading Bot
Purpose: Secure secret retrieval and management
Author: Security Engineer Agent
Date: 2025-11-19
Version: 1.0
"""

import os
import json
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from functools import wraps
import hvac
from hvac.exceptions import (
    VaultError,
    InvalidPath,
    Forbidden,
    Unauthorized,
    InternalServerError,
)
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# Configure logging
logger = logging.getLogger(__name__)


class VaultClientError(Exception):
    """Base exception for Vault client errors"""
    pass


class VaultConnectionError(VaultClientError):
    """Raised when connection to Vault fails"""
    pass


class VaultAuthenticationError(VaultClientError):
    """Raised when authentication to Vault fails"""
    pass


class VaultSecretNotFoundError(VaultClientError):
    """Raised when requested secret is not found"""
    pass


def retry_on_failure(max_attempts: int = 3, delay: float = 1.0):
    """
    Decorator to retry failed operations

    Args:
        max_attempts: Maximum number of retry attempts
        delay: Delay in seconds between retries
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except (VaultError, requests.RequestException) as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait_time = delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_attempts} failed: {e}. "
                            f"Retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(f"All {max_attempts} attempts failed")

            raise last_exception

        return wrapper
    return decorator


class VaultClient:
    """
    HashiCorp Vault client for secrets management

    Features:
    - Automatic token renewal
    - Secret caching with TTL
    - Connection retry logic
    - Health check integration
    - Dynamic database credentials
    - Transit encryption/decryption

    Usage:
        vault = VaultClient()

        # Get secret
        secret = vault.get_secret("database/postgres")

        # Get dynamic database credentials
        db_creds = vault.get_database_credentials("trading-bot-role")

        # Encrypt/Decrypt data
        ciphertext = vault.encrypt("trading-data", "sensitive info")
        plaintext = vault.decrypt("trading-data", ciphertext)
    """

    def __init__(
        self,
        vault_addr: Optional[str] = None,
        vault_token: Optional[str] = None,
        vault_namespace: Optional[str] = None,
        cache_ttl: int = 300,
        verify_ssl: bool = True,
    ):
        """
        Initialize Vault client

        Args:
            vault_addr: Vault server address (default: VAULT_ADDR env var)
            vault_token: Vault authentication token (default: VAULT_TOKEN env var)
            vault_namespace: Vault namespace (default: VAULT_NAMESPACE env var)
            cache_ttl: Secret cache TTL in seconds (default: 300)
            verify_ssl: Verify SSL certificates (default: True)
        """
        # Configuration from environment or parameters
        self.vault_addr = vault_addr or os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
        self.vault_token = vault_token or os.getenv("VAULT_TOKEN")
        self.vault_namespace = vault_namespace or os.getenv("VAULT_NAMESPACE")
        self.verify_ssl = verify_ssl

        # Secret cache
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = cache_ttl

        # Token renewal tracking
        self._token_expiry: Optional[datetime] = None
        self._token_renewable = False

        # Initialize client
        self._client: Optional[hvac.Client] = None
        self._initialize_client()

        logger.info(f"Vault client initialized for {self.vault_addr}")

    def _initialize_client(self) -> None:
        """Initialize HVAC client with retry logic"""
        try:
            # Configure session with retry
            session = requests.Session()
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                method_whitelist=["GET", "POST", "PUT", "DELETE"],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)

            # Create client
            self._client = hvac.Client(
                url=self.vault_addr,
                token=self.vault_token,
                namespace=self.vault_namespace,
                verify=self.verify_ssl,
                session=session,
            )

            # Verify authentication
            if not self._client.is_authenticated():
                raise VaultAuthenticationError("Failed to authenticate with Vault")

            # Get token information
            self._update_token_info()

            logger.info("Vault client authenticated successfully")

        except Unauthorized as e:
            raise VaultAuthenticationError(f"Unauthorized: {e}")
        except requests.ConnectionError as e:
            raise VaultConnectionError(f"Cannot connect to Vault: {e}")
        except Exception as e:
            raise VaultClientError(f"Failed to initialize Vault client: {e}")

    def _update_token_info(self) -> None:
        """Update token expiry and renewal information"""
        try:
            token_info = self._client.auth.token.lookup_self()

            # Extract token properties
            ttl = token_info.get("data", {}).get("ttl", 0)
            self._token_renewable = token_info.get("data", {}).get("renewable", False)

            if ttl > 0:
                self._token_expiry = datetime.now() + timedelta(seconds=ttl)
                logger.debug(f"Token expires at {self._token_expiry}")

        except Exception as e:
            logger.warning(f"Failed to get token info: {e}")

    @retry_on_failure(max_attempts=3, delay=1.0)
    def renew_token(self) -> bool:
        """
        Renew authentication token

        Returns:
            bool: True if token was renewed successfully
        """
        try:
            if not self._token_renewable:
                logger.warning("Token is not renewable")
                return False

            # Check if renewal is needed (renew when 50% of TTL has passed)
            if self._token_expiry:
                time_remaining = (self._token_expiry - datetime.now()).total_seconds()
                if time_remaining > (self._cache_ttl / 2):
                    logger.debug("Token renewal not needed yet")
                    return True

            # Renew token
            self._client.auth.token.renew_self()
            self._update_token_info()

            logger.info("Token renewed successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to renew token: {e}")
            return False

    def _get_from_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get secret from cache if not expired

        Args:
            key: Secret cache key

        Returns:
            Optional[Dict]: Cached secret or None if expired/not found
        """
        if key not in self._cache:
            return None

        cached_data = self._cache[key]
        expiry = cached_data.get("expiry")

        if expiry and datetime.now() < expiry:
            logger.debug(f"Cache hit for {key}")
            return cached_data.get("data")

        # Expired - remove from cache
        del self._cache[key]
        logger.debug(f"Cache expired for {key}")
        return None

    def _set_cache(self, key: str, data: Dict[str, Any]) -> None:
        """
        Set secret in cache with expiry

        Args:
            key: Secret cache key
            data: Secret data to cache
        """
        self._cache[key] = {
            "data": data,
            "expiry": datetime.now() + timedelta(seconds=self._cache_ttl),
        }
        logger.debug(f"Cached secret for {key}")

    def clear_cache(self, key: Optional[str] = None) -> None:
        """
        Clear secret cache

        Args:
            key: Specific key to clear (default: clear all)
        """
        if key:
            self._cache.pop(key, None)
            logger.info(f"Cleared cache for {key}")
        else:
            self._cache.clear()
            logger.info("Cleared all cache")

    @retry_on_failure(max_attempts=3, delay=1.0)
    def get_secret(
        self,
        path: str,
        key: Optional[str] = None,
        use_cache: bool = True,
    ) -> Any:
        """
        Get secret from Vault KV v2 engine

        Args:
            path: Secret path (e.g., "database/postgres")
            key: Specific key to extract (default: return all data)
            use_cache: Use cached value if available (default: True)

        Returns:
            Any: Secret data or specific key value

        Raises:
            VaultSecretNotFoundError: If secret is not found
            VaultClientError: If retrieval fails
        """
        cache_key = f"secret/{path}"

        # Check cache
        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached.get(key) if key else cached

        try:
            # Renew token if needed
            self.renew_token()

            # Get secret from Vault
            response = self._client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point="secret",
            )

            secret_data = response.get("data", {}).get("data", {})

            if not secret_data:
                raise VaultSecretNotFoundError(f"Secret not found: {path}")

            # Cache the secret
            if use_cache:
                self._set_cache(cache_key, secret_data)

            logger.info(f"Retrieved secret: {path}")

            # Return specific key or all data
            if key:
                if key not in secret_data:
                    raise VaultSecretNotFoundError(
                        f"Key '{key}' not found in secret '{path}'"
                    )
                return secret_data[key]

            return secret_data

        except InvalidPath as e:
            raise VaultSecretNotFoundError(f"Secret path not found: {path}")
        except Forbidden as e:
            raise VaultAuthenticationError(f"Access denied to secret: {path}")
        except Exception as e:
            raise VaultClientError(f"Failed to get secret '{path}': {e}")

    @retry_on_failure(max_attempts=3, delay=1.0)
    def set_secret(
        self,
        path: str,
        data: Dict[str, Any],
        cas: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Set secret in Vault KV v2 engine

        Args:
            path: Secret path
            data: Secret data to store
            cas: Check-and-set value for optimistic locking (optional)

        Returns:
            Dict: Response from Vault

        Raises:
            VaultClientError: If write fails
        """
        try:
            # Renew token if needed
            self.renew_token()

            # Write secret to Vault
            response = self._client.secrets.kv.v2.create_or_update_secret(
                path=path,
                secret=data,
                cas=cas,
                mount_point="secret",
            )

            # Invalidate cache
            cache_key = f"secret/{path}"
            self.clear_cache(cache_key)

            logger.info(f"Set secret: {path}")
            return response

        except Exception as e:
            raise VaultClientError(f"Failed to set secret '{path}': {e}")

    @retry_on_failure(max_attempts=3, delay=1.0)
    def get_database_credentials(
        self,
        role: str,
        use_cache: bool = False,  # Don't cache dynamic credentials
    ) -> Dict[str, str]:
        """
        Get dynamic database credentials from Vault

        Args:
            role: Database role name
            use_cache: Use cached credentials (not recommended)

        Returns:
            Dict: Database credentials (username, password)

        Raises:
            VaultClientError: If credential generation fails
        """
        cache_key = f"database/creds/{role}"

        # Check cache (not recommended for dynamic creds)
        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached

        try:
            # Renew token if needed
            self.renew_token()

            # Generate dynamic credentials
            response = self._client.secrets.database.generate_credentials(
                name=role,
                mount_point="database",
            )

            credentials = response.get("data", {})

            if not credentials:
                raise VaultClientError(f"No credentials generated for role: {role}")

            logger.info(f"Generated database credentials for role: {role}")

            # Cache if requested (with short TTL)
            if use_cache:
                self._set_cache(cache_key, credentials)

            return credentials

        except Exception as e:
            raise VaultClientError(
                f"Failed to get database credentials for role '{role}': {e}"
            )

    @retry_on_failure(max_attempts=3, delay=1.0)
    def encrypt(self, key_name: str, plaintext: str) -> str:
        """
        Encrypt data using Vault Transit engine

        Args:
            key_name: Transit encryption key name
            plaintext: Data to encrypt

        Returns:
            str: Ciphertext (Vault format: vault:v1:...)

        Raises:
            VaultClientError: If encryption fails
        """
        try:
            # Renew token if needed
            self.renew_token()

            # Encrypt using Transit engine
            response = self._client.secrets.transit.encrypt_data(
                name=key_name,
                plaintext=plaintext,
                mount_point="transit",
            )

            ciphertext = response.get("data", {}).get("ciphertext")

            if not ciphertext:
                raise VaultClientError("Encryption failed: no ciphertext returned")

            logger.debug(f"Encrypted data with key: {key_name}")
            return ciphertext

        except Exception as e:
            raise VaultClientError(f"Failed to encrypt with key '{key_name}': {e}")

    @retry_on_failure(max_attempts=3, delay=1.0)
    def decrypt(self, key_name: str, ciphertext: str) -> str:
        """
        Decrypt data using Vault Transit engine

        Args:
            key_name: Transit encryption key name
            ciphertext: Vault ciphertext to decrypt

        Returns:
            str: Decrypted plaintext

        Raises:
            VaultClientError: If decryption fails
        """
        try:
            # Renew token if needed
            self.renew_token()

            # Decrypt using Transit engine
            response = self._client.secrets.transit.decrypt_data(
                name=key_name,
                ciphertext=ciphertext,
                mount_point="transit",
            )

            plaintext = response.get("data", {}).get("plaintext")

            if not plaintext:
                raise VaultClientError("Decryption failed: no plaintext returned")

            logger.debug(f"Decrypted data with key: {key_name}")
            return plaintext

        except Exception as e:
            raise VaultClientError(f"Failed to decrypt with key '{key_name}': {e}")

    def health_check(self) -> Dict[str, Any]:
        """
        Check Vault server health

        Returns:
            Dict: Health status information
        """
        try:
            status = {
                "vault_addr": self.vault_addr,
                "authenticated": False,
                "sealed": None,
                "standby": None,
                "cluster_name": None,
                "version": None,
                "token_renewable": self._token_renewable,
                "token_expiry": self._token_expiry.isoformat() if self._token_expiry else None,
            }

            # Check Vault health
            health = self._client.sys.read_health_status(method="GET")
            status["sealed"] = health.get("sealed", True)
            status["standby"] = health.get("standby", False)
            status["cluster_name"] = health.get("cluster_name")
            status["version"] = health.get("version")

            # Check authentication
            status["authenticated"] = self._client.is_authenticated()

            logger.info("Vault health check completed")
            return status

        except Exception as e:
            logger.error(f"Vault health check failed: {e}")
            return {
                "vault_addr": self.vault_addr,
                "error": str(e),
                "authenticated": False,
            }

    def list_secrets(self, path: str = "") -> List[str]:
        """
        List secrets at given path

        Args:
            path: Secret path to list (default: root)

        Returns:
            List[str]: List of secret keys
        """
        try:
            response = self._client.secrets.kv.v2.list_secrets(
                path=path,
                mount_point="secret",
            )

            keys = response.get("data", {}).get("keys", [])
            logger.info(f"Listed {len(keys)} secrets at path: {path}")
            return keys

        except Exception as e:
            logger.error(f"Failed to list secrets at '{path}': {e}")
            return []

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        # Clear cache on exit
        self.clear_cache()
        logger.info("Vault client closed")


# Convenience function for getting secrets
def get_vault_secret(path: str, key: Optional[str] = None) -> Any:
    """
    Convenience function to get a secret from Vault

    Args:
        path: Secret path
        key: Specific key to extract (optional)

    Returns:
        Any: Secret data
    """
    with VaultClient() as vault:
        return vault.get_secret(path, key)


# Example usage
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Example 1: Get static secret
    try:
        vault = VaultClient()

        # Get database credentials
        db_config = vault.get_secret("database/postgres")
        print(f"PostgreSQL Config: {db_config}")

        # Get specific key
        db_password = vault.get_secret("database/postgres", key="password")
        print(f"PostgreSQL Password: {db_password}")

        # Health check
        health = vault.health_check()
        print(f"Vault Health: {health}")

    except VaultClientError as e:
        print(f"Error: {e}")

    # Example 2: Get dynamic database credentials
    try:
        vault = VaultClient()

        creds = vault.get_database_credentials("trading-bot-role")
        print(f"Dynamic Credentials: {creds}")

    except VaultClientError as e:
        print(f"Error: {e}")

    # Example 3: Encrypt/Decrypt
    try:
        vault = VaultClient()

        plaintext = "sensitive trading data"
        ciphertext = vault.encrypt("trading-data", plaintext)
        print(f"Ciphertext: {ciphertext}")

        decrypted = vault.decrypt("trading-data", ciphertext)
        print(f"Decrypted: {decrypted}")

    except VaultClientError as e:
        print(f"Error: {e}")
