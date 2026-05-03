"""
Bybit Connector Service - Configuration Tests
Purpose: Comprehensive tests for Settings validation and configuration management
"""

import pytest
import os
from pydantic import ValidationError

from app.config import Settings, get_settings, reload_settings
from app.exceptions import ConfigurationException


# ============================================================================
# SETTINGS INITIALIZATION TESTS
# ============================================================================

class TestSettingsInitialization:
    """Test Settings initialization and validation"""

    def test_settings_initialization_with_valid_data(self):
        """Test successful settings initialization with valid data"""
        # Given valid environment configuration
        settings_data = {
            "bybit_api_key": "test_api_key",
            "bybit_api_secret": "test_api_secret",
            "environment": "development",
            "log_level": "INFO",
            "service_port": 8002
        }

        # When creating settings
        settings = Settings(**settings_data)

        # Then settings are initialized correctly
        assert settings.bybit_api_key == "test_api_key"
        assert settings.bybit_api_secret == "test_api_secret"
        assert settings.environment == "development"
        assert settings.log_level == "INFO"
        assert settings.service_port == 8002

    def test_settings_default_values(self, monkeypatch):
        """Test settings use correct default values"""
        # Clear env vars that pydantic-settings would otherwise pull in via
        # the project's .env file or test-runner shell. Without this, running
        # under `pytest tests/` (full discovery) picks up SERVICE_PORT etc.
        # from another service's env and breaks the default-value asserts.
        for var in (
            "DEBUG",
            "SERVICE_PORT",
            "SERVICE_HOST",
            "SERVICE_NAME",
            "ENVIRONMENT",
            "LOG_LEVEL",
            "BYBIT_TESTNET",
            "BYBIT_RECV_WINDOW",
        ):
            monkeypatch.delenv(var, raising=False)

        settings_data = {
            "bybit_api_key": "test_key",
            "bybit_api_secret": "test_secret"
        }

        # When creating settings
        settings = Settings(**settings_data)

        # Then default values are used
        assert settings.environment == "development"
        assert settings.log_level == "INFO"
        # Note: debug may be True from .env file, so we check it exists
        assert isinstance(settings.debug, bool)
        assert settings.bybit_testnet is True
        assert settings.bybit_recv_window == 5000
        assert settings.service_name == "bybit-connector"
        # Default port is 8001 per CLAUDE.md service map.
        assert settings.service_port == 8001
        assert settings.service_host == "0.0.0.0"

    def test_settings_testnet_configuration(self):
        """Test testnet vs mainnet configuration"""
        # Given testnet settings
        settings_testnet = Settings(
            bybit_api_key="key",
            bybit_api_secret="secret",
            bybit_testnet=True
        )

        # When checking URLs
        # Then testnet URLs are used
        assert "testnet" in settings_testnet.rest_api_url
        assert "testnet" in settings_testnet.websocket_url

        # Given mainnet settings
        settings_mainnet = Settings(
            bybit_api_key="key",
            bybit_api_secret="secret",
            bybit_testnet=False
        )

        # When checking URLs
        # Then mainnet URLs are used
        assert "testnet" not in settings_mainnet.rest_api_url
        assert "testnet" not in settings_mainnet.websocket_url


# ============================================================================
# FIELD VALIDATION TESTS
# ============================================================================

class TestFieldValidation:
    """Test individual field validators"""

    def test_log_level_validation_valid_levels(self):
        """Test log_level validation accepts valid levels"""
        # Given valid log levels
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

        for level in valid_levels:
            # When creating settings with valid log level
            settings = Settings(
                bybit_api_key="key",
                bybit_api_secret="secret",
                log_level=level
            )

            # Then log level is set (uppercase)
            assert settings.log_level == level.upper()

    def test_log_level_validation_case_insensitive(self):
        """Test log_level validation is case insensitive"""
        # Given lowercase log level
        settings = Settings(
            bybit_api_key="key",
            bybit_api_secret="secret",
            log_level="info"
        )

        # When checking log level
        # Then it's converted to uppercase
        assert settings.log_level == "INFO"

    def test_log_level_validation_invalid_level(self):
        """Test log_level validation rejects invalid levels"""
        # Given invalid log level
        settings_data = {
            "bybit_api_key": "key",
            "bybit_api_secret": "secret",
            "log_level": "INVALID"
        }

        # When/Then creating settings raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            Settings(**settings_data)

        errors = exc_info.value.errors()
        assert any("Log level must be one of" in str(e) for e in errors)

    def test_environment_validation_valid_environments(self):
        """Test environment validation accepts valid environments"""
        # Given valid environments
        valid_envs = ["development", "staging", "production"]

        for env in valid_envs:
            # When creating settings with valid environment
            settings = Settings(
                bybit_api_key="key",
                bybit_api_secret="secret",
                environment=env
            )

            # Then environment is set (lowercase)
            assert settings.environment == env.lower()

    def test_environment_validation_case_insensitive(self):
        """Test environment validation is case insensitive"""
        # Given uppercase environment
        settings = Settings(
            bybit_api_key="key",
            bybit_api_secret="secret",
            environment="PRODUCTION"
        )

        # When checking environment
        # Then it's converted to lowercase
        assert settings.environment == "production"

    def test_environment_validation_invalid_environment(self):
        """Test environment validation rejects invalid environments"""
        # Given invalid environment
        settings_data = {
            "bybit_api_key": "key",
            "bybit_api_secret": "secret",
            "environment": "invalid_env"
        }

        # When/Then creating settings raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            Settings(**settings_data)

        errors = exc_info.value.errors()
        assert any("Environment must be one of" in str(e) for e in errors)

    def test_api_credentials_validation_empty_key(self):
        """Test API credentials validation rejects empty key"""
        # Given settings with empty API key
        settings_data = {
            "bybit_api_key": "",
            "bybit_api_secret": "secret"
        }

        # When/Then creating settings raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            Settings(**settings_data)

        errors = exc_info.value.errors()
        assert any("bybit_api_key" in str(e).lower() for e in errors)

    def test_api_credentials_validation_empty_secret(self):
        """Test API credentials validation rejects empty secret"""
        # Given settings with empty API secret
        settings_data = {
            "bybit_api_key": "key",
            "bybit_api_secret": ""
        }

        # When/Then creating settings raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            Settings(**settings_data)

        errors = exc_info.value.errors()
        assert any("bybit_api_secret" in str(e).lower() for e in errors)

    def test_port_validation_invalid_port_low(self):
        """Test port validation rejects ports below 1"""
        # Given settings with invalid port (too low)
        settings_data = {
            "bybit_api_key": "key",
            "bybit_api_secret": "secret",
            "service_port": 0
        }

        # When/Then creating settings raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            Settings(**settings_data)

        errors = exc_info.value.errors()
        assert any("must be between 1 and 65535" in str(e) for e in errors)

    def test_port_validation_invalid_port_high(self):
        """Test port validation rejects ports above 65535"""
        # Given settings with invalid port (too high)
        settings_data = {
            "bybit_api_key": "key",
            "bybit_api_secret": "secret",
            "service_port": 70000
        }

        # When/Then creating settings raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            Settings(**settings_data)

        errors = exc_info.value.errors()
        assert any("must be between 1 and 65535" in str(e) for e in errors)

    def test_port_validation_multiple_ports(self):
        """Test validation works for all port fields"""
        # Given settings with multiple port configurations
        settings = Settings(
            bybit_api_key="key",
            bybit_api_secret="secret",
            service_port=8002,
            redis_port=6379,
            rabbitmq_port=5672,
            metrics_port=9090
        )

        # Then all ports are valid
        assert settings.service_port == 8002
        assert settings.redis_port == 6379
        assert settings.rabbitmq_port == 5672
        assert settings.metrics_port == 9090


# ============================================================================
# COMPUTED PROPERTIES TESTS
# ============================================================================

class TestComputedProperties:
    """Test computed properties and derived values"""

    def test_rest_api_url_testnet(self):
        """Test rest_api_url property returns testnet URL"""
        # Given testnet settings
        settings = Settings(
            bybit_api_key="key",
            bybit_api_secret="secret",
            bybit_testnet=True
        )

        # When getting REST API URL
        url = settings.rest_api_url

        # Then testnet URL is returned
        assert url == settings.bybit_rest_url_testnet
        assert "testnet" in url

    def test_rest_api_url_mainnet(self):
        """Test rest_api_url property returns mainnet URL"""
        # Given mainnet settings
        settings = Settings(
            bybit_api_key="key",
            bybit_api_secret="secret",
            bybit_testnet=False
        )

        # When getting REST API URL
        url = settings.rest_api_url

        # Then mainnet URL is returned
        assert url == settings.bybit_rest_url_mainnet
        assert "testnet" not in url

    def test_websocket_url_testnet(self):
        """Test websocket_url property returns testnet URL"""
        # Given testnet settings
        settings = Settings(
            bybit_api_key="key",
            bybit_api_secret="secret",
            bybit_testnet=True
        )

        # When getting WebSocket URL
        url = settings.websocket_url

        # Then testnet URL is returned
        assert url == settings.bybit_ws_url_testnet
        assert "testnet" in url

    def test_websocket_url_mainnet(self):
        """Test websocket_url property returns mainnet URL"""
        # Given mainnet settings
        settings = Settings(
            bybit_api_key="key",
            bybit_api_secret="secret",
            bybit_testnet=False
        )

        # When getting WebSocket URL
        url = settings.websocket_url

        # Then mainnet URL is returned
        assert url == settings.bybit_ws_url_mainnet
        assert "testnet" not in url

    def test_redis_url_without_password(self):
        """Test redis_url property without password"""
        # Given settings without Redis password
        settings = Settings(
            bybit_api_key="key",
            bybit_api_secret="secret",
            redis_host="localhost",
            redis_port=6379,
            redis_db=0,
            redis_password=None
        )

        # When getting Redis URL
        url = settings.redis_url

        # Then URL without password is generated
        assert url == "redis://localhost:6379/0"
        assert ":" not in url.split("//")[1].split("@")[0] if "@" in url else True

    def test_redis_url_with_password(self):
        """Test redis_url property with password"""
        # Given settings with Redis password
        settings = Settings(
            bybit_api_key="key",
            bybit_api_secret="secret",
            redis_host="redis-server",
            redis_port=6379,
            redis_db=1,
            redis_password="secure_password"
        )

        # When getting Redis URL
        url = settings.redis_url

        # Then URL with password is generated
        assert url == "redis://:secure_password@redis-server:6379/1"
        assert "secure_password" in url

    def test_rabbitmq_url(self):
        """Test rabbitmq_url property"""
        # Given settings with RabbitMQ config
        settings = Settings(
            bybit_api_key="key",
            bybit_api_secret="secret",
            rabbitmq_host="rabbitmq-server",
            rabbitmq_port=5672,
            rabbitmq_user="admin",
            rabbitmq_password="admin_pass",
            rabbitmq_vhost="trading"
        )

        # When getting RabbitMQ URL
        url = settings.rabbitmq_url

        # Then correct AMQP URL is generated
        assert url == "amqp://admin:admin_pass@rabbitmq-server:5672/trading"
        assert "amqp://" in url
        assert "admin:admin_pass" in url

    def test_is_production_flag_production(self):
        """Test is_production property in production environment"""
        # Given production settings
        settings = Settings(
            bybit_api_key="key",
            bybit_api_secret="secret",
            environment="production"
        )

        # When checking production flag
        is_prod = settings.is_production

        # Then flag is True
        assert is_prod is True

    def test_is_production_flag_development(self):
        """Test is_production property in development environment"""
        # Given development settings
        settings = Settings(
            bybit_api_key="key",
            bybit_api_secret="secret",
            environment="development"
        )

        # When checking production flag
        is_prod = settings.is_production

        # Then flag is False
        assert is_prod is False

    def test_is_testnet_flag(self):
        """Test is_testnet property"""
        # Given testnet settings
        settings_testnet = Settings(
            bybit_api_key="key",
            bybit_api_secret="secret",
            bybit_testnet=True
        )

        # When checking testnet flag
        # Then flag is True
        assert settings_testnet.is_testnet is True

        # Given mainnet settings
        settings_mainnet = Settings(
            bybit_api_key="key",
            bybit_api_secret="secret",
            bybit_testnet=False
        )

        # When checking testnet flag
        # Then flag is False
        assert settings_mainnet.is_testnet is False


# ============================================================================
# SINGLETON PATTERN TESTS
# ============================================================================

class TestSingletonPattern:
    """Test singleton pattern for settings management"""

    def test_get_settings_returns_instance(self, monkeypatch):
        """Test get_settings returns a Settings instance"""
        # Given environment with API credentials
        monkeypatch.setenv("BYBIT_API_KEY", "test_key")
        monkeypatch.setenv("BYBIT_API_SECRET", "test_secret")

        # When getting settings
        settings = get_settings()

        # Then Settings instance is returned
        assert isinstance(settings, Settings)

    def test_get_settings_singleton(self, monkeypatch):
        """Test get_settings returns same instance (singleton)"""
        # Given environment with API credentials
        monkeypatch.setenv("BYBIT_API_KEY", "test_key")
        monkeypatch.setenv("BYBIT_API_SECRET", "test_secret")

        # When getting settings multiple times
        settings1 = get_settings()
        settings2 = get_settings()

        # Then same instance is returned
        assert settings1 is settings2

    def test_reload_settings_creates_new_instance(self, monkeypatch):
        """Test reload_settings creates new instance"""
        # Given environment with API credentials
        monkeypatch.setenv("BYBIT_API_KEY", "test_key")
        monkeypatch.setenv("BYBIT_API_SECRET", "test_secret")

        # When getting settings then reloading
        settings1 = get_settings()
        settings2 = reload_settings()

        # Then new instance is created
        assert settings1 is not settings2
        assert isinstance(settings2, Settings)


# ============================================================================
# ENVIRONMENT VARIABLE LOADING TESTS
# ============================================================================

class TestEnvironmentVariableLoading:
    """Test loading settings from environment variables"""

    def test_load_from_environment_variables(self, monkeypatch):
        """Test settings loaded from environment variables"""
        # Given environment variables
        monkeypatch.setenv("BYBIT_API_KEY", "env_api_key")
        monkeypatch.setenv("BYBIT_API_SECRET", "env_api_secret")
        monkeypatch.setenv("ENVIRONMENT", "staging")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("SERVICE_PORT", "9000")

        # When reloading settings (to pick up env vars)
        settings = reload_settings()

        # Then environment variables are used
        assert settings.bybit_api_key == "env_api_key"
        assert settings.bybit_api_secret == "env_api_secret"
        assert settings.environment == "staging"
        assert settings.log_level == "DEBUG"
        assert settings.service_port == 9000

    def test_constructor_overrides_environment(self, monkeypatch):
        """Test constructor values override environment variables"""
        # Given environment variable
        monkeypatch.setenv("LOG_LEVEL", "ERROR")

        # When creating settings with explicit value
        settings = Settings(
            bybit_api_key="key",
            bybit_api_secret="secret",
            log_level="DEBUG"
        )

        # Then explicit value is used
        assert settings.log_level == "DEBUG"


# ============================================================================
# CORS CONFIGURATION TESTS (DEPRECATED - CORS field removed from config)
# ============================================================================

class TestCORSConfiguration:
    """Test CORS configuration - DEPRECATED: CORS handling moved to main.py"""

    @pytest.mark.skip(reason="CORS configuration removed from Settings - handled in main.py middleware")
    def test_cors_default_configuration(self):
        """Test CORS uses default allowed origins"""
        pass  # Skipped - CORS not in Settings

    @pytest.mark.skip(reason="CORS configuration removed from Settings - handled in main.py middleware")
    def test_cors_custom_configuration(self):
        """Test CORS with custom allowed origins"""
        pass  # Skipped - CORS not in Settings
