"""
Tests for Configuration Settings
Tests configuration validation and environment variable loading
"""

import pytest
from pydantic import ValidationError

from app.config import Settings


class TestSettingsValidation:
    """Test settings validation"""

    def test_default_settings(self):
        """Test that default settings are valid"""
        settings = Settings()

        assert settings.service_name == "api-gateway"
        assert settings.service_port == 8000
        assert settings.log_level == "INFO"

    def test_service_port_validation(self):
        """Test service port validation"""
        # Valid port
        settings = Settings(service_port=8080)
        assert settings.service_port == 8080

        # Invalid port (too low)
        with pytest.raises(ValidationError):
            Settings(service_port=100)

        # Invalid port (too high)
        with pytest.raises(ValidationError):
            Settings(service_port=70000)

    def test_log_level_validation(self):
        """Test log level validation"""
        # Valid log levels
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            settings = Settings(log_level=level)
            assert settings.log_level == level

        # Case insensitive
        settings = Settings(log_level="info")
        assert settings.log_level == "INFO"

        # Invalid log level
        with pytest.raises(ValidationError):
            Settings(log_level="INVALID")

    def test_service_name_validation(self):
        """Test service name validation"""
        # Valid name
        settings = Settings(service_name="test-gateway")
        assert settings.service_name == "test-gateway"

        # Empty name should fail
        with pytest.raises(ValidationError):
            Settings(service_name="")

        # Whitespace-only name should fail
        with pytest.raises(ValidationError):
            Settings(service_name="   ")

    def test_backend_service_urls(self):
        """Test backend service URL configuration"""
        settings = Settings()

        # Port defaults aligned to CLAUDE.md / docker-compose.unified.yml
        # (corrected 2026-05-01).
        assert settings.bybit_connector_url == "http://localhost:8001"
        assert settings.market_data_url == "http://localhost:8002"
        assert settings.technical_analysis_url == "http://localhost:8004"
        assert settings.trading_engine_url == "http://localhost:8005"
        assert settings.portfolio_manager_url == "http://localhost:8003"
        assert settings.risk_metrics_url == "http://localhost:8009"

    def test_security_settings(self):
        """Test security configuration"""
        settings = Settings()

        assert settings.jwt_algorithm == "HS256"
        assert settings.access_token_expire_minutes == 30
        assert 1 <= settings.access_token_expire_minutes <= 1440

    def test_rate_limiting_settings(self):
        """Test rate limiting configuration"""
        settings = Settings()

        assert settings.rate_limit_enabled is True
        assert settings.rate_limit_per_minute == 60
        assert settings.rate_limit_burst == 10

    def test_caching_settings(self):
        """Test caching configuration"""
        settings = Settings()

        assert settings.cache_enabled is True
        assert settings.cache_ttl_seconds == 60
        assert settings.redis_url == "redis://localhost:6379"

    def test_cors_settings(self):
        """Test CORS configuration"""
        settings = Settings()

        assert isinstance(settings.cors_origins, list)
        assert "http://localhost:3000" in settings.cors_origins

    def test_api_documentation_settings(self):
        """Test API documentation configuration"""
        settings = Settings()

        assert settings.api_title == "Crypto Trading Bot API Gateway"
        assert settings.api_version == "1.0.0"
        assert "API Gateway" in settings.api_description

    def test_custom_environment_variables(self):
        """Test loading custom environment variables"""
        import os

        # Set custom environment variable
        os.environ["SERVICE_PORT"] = "9000"
        os.environ["LOG_LEVEL"] = "DEBUG"

        settings = Settings()

        assert settings.service_port == 9000
        assert settings.log_level == "DEBUG"

        # Clean up
        del os.environ["SERVICE_PORT"]
        del os.environ["LOG_LEVEL"]


class TestJWTSecretKeyWarning:
    """Test JWT secret key security"""

    def test_default_jwt_secret_is_insecure(self):
        """Test that default JWT secret key is recognized as insecure"""
        settings = Settings()

        # This should trigger a security warning in production
        # JWT secret is loaded from environment or default
        assert isinstance(settings.jwt_secret_key, str)
        assert len(settings.jwt_secret_key) > 0
        """Test setting custom JWT secret key"""
        import os

        os.environ["JWT_SECRET_KEY"] = "custom-secure-secret-key-32-chars-min"
        settings = Settings()

        assert settings.jwt_secret_key != "your-secret-key-change-in-production"
        assert len(settings.jwt_secret_key) >= 32

        # Clean up
        del os.environ["JWT_SECRET_KEY"]
