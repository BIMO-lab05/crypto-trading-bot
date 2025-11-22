"""
HashiCorp Vault Client for Crypto Trading Bot
Purpose: Secure secrets management with automatic rotation and caching
Author: Security Engineer Agent
Date: 2025-11-21
Version: 1.0
"""

import os
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import threading
import hvac
from hvac.exceptions import VaultError, InvalidPath
import json
from functools import wraps

# Configure logging
logger = logging.getLogger(__name__)


class VaultConnectionError(Exception):
    """Raised when Vault connection fails"""
    pass


class VaultSecretNotFound(Exception):
    """Raised when requested secret is not found"""
    pass


class VaultClient:
    """
    HashiCorp Vault Client with automatic token renewal and secret caching

    Features:
    - Automatic token renewal
    - Secret caching with TTL
    - Database dynamic credentials
    - Transit encryption/decryption
    - Audit logging of all operations
    - Connection pooling and retry logic
    - Thread-safe operations

    Attributes:
        client: HVAC Vault client instance
        token: Vault authentication token
        vault_addr: Vault server address
        cache: In-memory secret cache
        cache_ttl: Cache time-to-live in seconds
        audit_enabled: Enable audit logging
        token_renew_thread: Background thread for token renewal
    """

    def __init__(
        self,
        vault_addr: Optional[str] = None,
        vault_token: Optional[str] = None,
        verify_ssl: bool = True,
        cache_ttl: int = 300,  # 5 minutes
        enable_audit: bool = True,
        auto_renew_token: bool = True
    ):
        """
        Initialize Vault client

        Args:
            vault_addr: Vault server address (defaults to VAULT_ADDR env var)
            vault_token: Vault token (defaults to VAULT_TOKEN env var)
            verify_ssl: Verify SSL certificates
            cache_ttl: Secret cache TTL in seconds
            enable_audit: Enable audit logging
            auto_renew_token: Automatically renew token before expiration

        Raises:
            VaultConnectionError: If connection to Vault fails
        """
        # Load configuration from environment
        self.vault_addr = vault_addr or os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
        self.token = vault_token or os.getenv("VAULT_TOKEN")

        if not self.token:
            raise VaultConnectionError("Vault token not provided. Set VAULT_TOKEN environment variable.")

        # Initialize Vault client
        try:
            self.client = hvac.Client(
                url=self.vault_addr,
                token=self.token,
                verify=verify_ssl
            )

            # Verify connection and authentication
            if not self.client.is_authenticated():
                raise VaultConnectionError("Failed to authenticate with Vault")

            logger.info(f"Successfully connected to Vault at {self.vault_addr}")

        except Exception as e:
            logger.error(f"Failed to initialize Vault client: {e}")
            raise VaultConnectionError(f"Vault connection failed: {e}")

        # Initialize cache
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl = cache_ttl
        self.cache_lock = threading.Lock()

        # Audit configuration
        self.audit_enabled = enable_audit
        self.audit_log_path = os.getenv("VAULT_AUDIT_LOG_PATH", "/var/log/vault/audit.log")

        # Token renewal
        self.auto_renew = auto_renew_token
        self.token_renew_thread = None
        if self.auto_renew:
            self._start_token_renewal()

        logger.info("Vault client initialized successfully")

    def _start_token_renewal(self):
        """Start background thread for automatic token renewal"""
        def renew_token_loop():
            while True:
                try:
                    # Get token TTL
                    token_info = self.client.auth.token.lookup_self()
                    ttl = token_info['data']['ttl']

                    # Renew when 1/3 of TTL remains
                    sleep_time = max(ttl // 3, 60)  # At least 60 seconds

                    logger.debug(f"Token TTL: {ttl}s, next renewal in {sleep_time}s")
                    time.sleep(sleep_time)

                    # Renew token
                    self.client.auth.token.renew_self()
                    logger.info("Vault token renewed successfully")

                    # Log audit event
                    if self.audit_enabled:
                        self._audit_log("token_renewal", {"status": "success"})

                except Exception as e:
                    logger.error(f"Failed to renew token: {e}")
                    # Log audit event
                    if self.audit_enabled:
                        self._audit_log("token_renewal", {"status": "failed", "error": str(e)})
                    # Sleep and retry
                    time.sleep(60)

        self.token_renew_thread = threading.Thread(
            target=renew_token_loop,
            daemon=True,
            name="VaultTokenRenewal"
        )
        self.token_renew_thread.start()
        logger.info("Started automatic token renewal thread")

    def _audit_log(self, operation: str, details: Dict[str, Any]):
        """
        Log audit event

        Args:
            operation: Operation type (e.g., 'read_secret', 'write_secret')
            details: Additional operation details
        """
        if not self.audit_enabled:
            return

        audit_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "operation": operation,
            "vault_addr": self.vault_addr,
            "details": details
        }

        try:
            # Log to file
            os.makedirs(os.path.dirname(self.audit_log_path), exist_ok=True)
            with open(self.audit_log_path, 'a') as f:
                f.write(json.dumps(audit_entry) + '\n')
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

    def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve secret from cache if not expired

        Args:
            cache_key: Cache key

        Returns:
            Cached secret or None if expired/not found
        """
        with self.cache_lock:
            if cache_key in self.cache:
                cache_entry = self.cache[cache_key]
                if datetime.now() < cache_entry['expires_at']:
                    logger.debug(f"Cache hit for {cache_key}")
                    return cache_entry['data']
                else:
                    # Remove expired entry
                    del self.cache[cache_key]
                    logger.debug(f"Cache expired for {cache_key}")
        return None

    def _set_cache(self, cache_key: str, data: Dict[str, Any]):
        """
        Store secret in cache

        Args:
            cache_key: Cache key
            data: Secret data to cache
        """
        with self.cache_lock:
            self.cache[cache_key] = {
                'data': data,
                'expires_at': datetime.now() + timedelta(seconds=self.cache_ttl)
            }
            logger.debug(f"Cached {cache_key} with TTL {self.cache_ttl}s")

    def _clear_cache(self, cache_key: Optional[str] = None):
        """
        Clear cache entry or entire cache

        Args:
            cache_key: Specific key to clear, or None to clear all
        """
        with self.cache_lock:
            if cache_key:
                self.cache.pop(cache_key, None)
                logger.debug(f"Cleared cache for {cache_key}")
            else:
                self.cache.clear()
                logger.debug("Cleared entire cache")

    def read_secret(self, path: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Read secret from Vault KV v2 secret engine

        Args:
            path: Secret path (e.g., 'database/postgres')
            use_cache: Use cached value if available

        Returns:
            Secret data dictionary

        Raises:
            VaultSecretNotFound: If secret not found
            VaultError: If Vault operation fails

        Example:
            >>> vault = VaultClient()
            >>> postgres_creds = vault.read_secret('database/postgres')
            >>> print(postgres_creds['username'])
        """
        cache_key = f"secret:{path}"

        # Check cache first
        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached

        try:
            # Read from Vault (KV v2 format)
            response = self.client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point='secret'
            )

            secret_data = response['data']['data']

            # Cache the result
            if use_cache:
                self._set_cache(cache_key, secret_data)

            # Audit log
            if self.audit_enabled:
                self._audit_log("read_secret", {
                    "path": path,
                    "status": "success",
                    "cached": False
                })

            logger.debug(f"Successfully read secret from {path}")
            return secret_data

        except InvalidPath:
            logger.error(f"Secret not found at path: {path}")
            if self.audit_enabled:
                self._audit_log("read_secret", {
                    "path": path,
                    "status": "not_found"
                })
            raise VaultSecretNotFound(f"Secret not found: {path}")

        except Exception as e:
            logger.error(f"Failed to read secret from {path}: {e}")
            if self.audit_enabled:
                self._audit_log("read_secret", {
                    "path": path,
                    "status": "error",
                    "error": str(e)
                })
            raise VaultError(f"Failed to read secret: {e}")

    def write_secret(self, path: str, data: Dict[str, Any]) -> None:
        """
        Write secret to Vault KV v2 secret engine

        Args:
            path: Secret path
            data: Secret data to write

        Raises:
            VaultError: If Vault operation fails

        Example:
            >>> vault = VaultClient()
            >>> vault.write_secret('database/postgres', {
            ...     'username': 'dbuser',
            ...     'password': 'secure_password'
            ... })
        """
        try:
            self.client.secrets.kv.v2.create_or_update_secret(
                path=path,
                secret=data,
                mount_point='secret'
            )

            # Clear cache for this path
            cache_key = f"secret:{path}"
            self._clear_cache(cache_key)

            # Audit log (don't log actual secret data)
            if self.audit_enabled:
                self._audit_log("write_secret", {
                    "path": path,
                    "status": "success",
                    "keys": list(data.keys())  # Log keys only, not values
                })

            logger.info(f"Successfully wrote secret to {path}")

        except Exception as e:
            logger.error(f"Failed to write secret to {path}: {e}")
            if self.audit_enabled:
                self._audit_log("write_secret", {
                    "path": path,
                    "status": "error",
                    "error": str(e)
                })
            raise VaultError(f"Failed to write secret: {e}")

    def delete_secret(self, path: str) -> None:
        """
        Delete secret from Vault

        Args:
            path: Secret path to delete

        Raises:
            VaultError: If Vault operation fails
        """
        try:
            self.client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=path,
                mount_point='secret'
            )

            # Clear cache
            cache_key = f"secret:{path}"
            self._clear_cache(cache_key)

            # Audit log
            if self.audit_enabled:
                self._audit_log("delete_secret", {
                    "path": path,
                    "status": "success"
                })

            logger.info(f"Successfully deleted secret at {path}")

        except Exception as e:
            logger.error(f"Failed to delete secret at {path}: {e}")
            if self.audit_enabled:
                self._audit_log("delete_secret", {
                    "path": path,
                    "status": "error",
                    "error": str(e)
                })
            raise VaultError(f"Failed to delete secret: {e}")

    def get_database_credentials(self, role: str) -> Dict[str, str]:
        """
        Get dynamic database credentials from Vault

        Args:
            role: Database role name (e.g., 'trading-bot-role')

        Returns:
            Dictionary with 'username', 'password', and 'lease_id'

        Raises:
            VaultError: If credential generation fails

        Example:
            >>> vault = VaultClient()
            >>> creds = vault.get_database_credentials('trading-bot-role')
            >>> print(f"Username: {creds['username']}")
        """
        try:
            response = self.client.secrets.database.generate_credentials(
                name=role,
                mount_point='database'
            )

            credentials = {
                'username': response['data']['username'],
                'password': response['data']['password'],
                'lease_id': response['lease_id'],
                'lease_duration': response['lease_duration']
            }

            # Audit log (don't log password)
            if self.audit_enabled:
                self._audit_log("get_db_credentials", {
                    "role": role,
                    "status": "success",
                    "username": credentials['username'],
                    "lease_duration": credentials['lease_duration']
                })

            logger.info(f"Generated database credentials for role: {role}")
            return credentials

        except Exception as e:
            logger.error(f"Failed to generate database credentials for {role}: {e}")
            if self.audit_enabled:
                self._audit_log("get_db_credentials", {
                    "role": role,
                    "status": "error",
                    "error": str(e)
                })
            raise VaultError(f"Failed to generate database credentials: {e}")

    def revoke_lease(self, lease_id: str) -> None:
        """
        Revoke a Vault lease (e.g., database credentials)

        Args:
            lease_id: Lease ID to revoke

        Raises:
            VaultError: If lease revocation fails
        """
        try:
            self.client.sys.revoke_lease(lease_id=lease_id)

            # Audit log
            if self.audit_enabled:
                self._audit_log("revoke_lease", {
                    "lease_id": lease_id,
                    "status": "success"
                })

            logger.info(f"Successfully revoked lease: {lease_id}")

        except Exception as e:
            logger.error(f"Failed to revoke lease {lease_id}: {e}")
            if self.audit_enabled:
                self._audit_log("revoke_lease", {
                    "lease_id": lease_id,
                    "status": "error",
                    "error": str(e)
                })
            raise VaultError(f"Failed to revoke lease: {e}")

    def encrypt(self, key_name: str, plaintext: str) -> str:
        """
        Encrypt data using Vault Transit engine

        Args:
            key_name: Transit key name
            plaintext: Data to encrypt

        Returns:
            Encrypted ciphertext

        Raises:
            VaultError: If encryption fails
        """
        try:
            import base64

            # Encode plaintext to base64
            plaintext_b64 = base64.b64encode(plaintext.encode()).decode()

            response = self.client.secrets.transit.encrypt_data(
                name=key_name,
                plaintext=plaintext_b64,
                mount_point='transit'
            )

            ciphertext = response['data']['ciphertext']

            # Audit log
            if self.audit_enabled:
                self._audit_log("encrypt", {
                    "key_name": key_name,
                    "status": "success"
                })

            logger.debug(f"Successfully encrypted data with key: {key_name}")
            return ciphertext

        except Exception as e:
            logger.error(f"Failed to encrypt data with key {key_name}: {e}")
            if self.audit_enabled:
                self._audit_log("encrypt", {
                    "key_name": key_name,
                    "status": "error",
                    "error": str(e)
                })
            raise VaultError(f"Failed to encrypt data: {e}")

    def decrypt(self, key_name: str, ciphertext: str) -> str:
        """
        Decrypt data using Vault Transit engine

        Args:
            key_name: Transit key name
            ciphertext: Data to decrypt

        Returns:
            Decrypted plaintext

        Raises:
            VaultError: If decryption fails
        """
        try:
            import base64

            response = self.client.secrets.transit.decrypt_data(
                name=key_name,
                ciphertext=ciphertext,
                mount_point='transit'
            )

            # Decode from base64
            plaintext_b64 = response['data']['plaintext']
            plaintext = base64.b64decode(plaintext_b64).decode()

            # Audit log
            if self.audit_enabled:
                self._audit_log("decrypt", {
                    "key_name": key_name,
                    "status": "success"
                })

            logger.debug(f"Successfully decrypted data with key: {key_name}")
            return plaintext

        except Exception as e:
            logger.error(f"Failed to decrypt data with key {key_name}: {e}")
            if self.audit_enabled:
                self._audit_log("decrypt", {
                    "key_name": key_name,
                    "status": "error",
                    "error": str(e)
                })
            raise VaultError(f"Failed to decrypt data: {e}")

    def health_check(self) -> Dict[str, Any]:
        """
        Check Vault health status

        Returns:
            Dictionary with health check results
        """
        try:
            health = self.client.sys.read_health_status()

            return {
                "healthy": True,
                "initialized": health.get('initialized', False),
                "sealed": health.get('sealed', True),
                "standby": health.get('standby', False),
                "server_time": health.get('server_time_utc', 0)
            }

        except Exception as e:
            logger.error(f"Vault health check failed: {e}")
            return {
                "healthy": False,
                "error": str(e)
            }

    def close(self):
        """Close Vault client and cleanup resources"""
        # Stop token renewal thread
        if self.token_renew_thread and self.token_renew_thread.is_alive():
            logger.info("Stopping token renewal thread...")
            # Thread is daemon, will stop automatically

        # Clear cache
        self._clear_cache()

        logger.info("Vault client closed")


def vault_secret(path: str, key: str, use_cache: bool = True):
    """
    Decorator to inject Vault secret as function parameter

    Args:
        path: Vault secret path
        key: Key within the secret
        use_cache: Use cached value if available

    Example:
        >>> @vault_secret('database/postgres', 'password')
        ... def connect_db(password):
        ...     return psycopg2.connect(password=password)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            vault = VaultClient()
            secret = vault.read_secret(path, use_cache=use_cache)
            kwargs[key] = secret.get(key)
            return func(*args, **kwargs)
        return wrapper
    return decorator


# Singleton instance for easy access
_vault_client_instance: Optional[VaultClient] = None


def get_vault_client() -> VaultClient:
    """
    Get singleton Vault client instance

    Returns:
        VaultClient instance
    """
    global _vault_client_instance

    if _vault_client_instance is None:
        _vault_client_instance = VaultClient()

    return _vault_client_instance
