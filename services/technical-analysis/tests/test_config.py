"""
Tests for Configuration Module
Coverage target: config.py lines 61-63, 68
"""

from unittest.mock import patch
from app.config import Settings, get_settings


class TestSettings:
    """Test Settings configuration class"""

    def test_redis_url_with_password(self):
        """Test redis_url property constructs correct URL with password"""
        settings = Settings(
            redis_host="redis-server",
            redis_port=6379,
            redis_password="secret123",
            redis_db=1,
        )

        expected = "redis://:secret123@redis-server:6379/1"
        assert settings.redis_url == expected

    def test_redis_url_without_password(self):
        """Test redis_url property constructs correct URL without password"""
        settings = Settings(
            redis_host="localhost", redis_port=6380, redis_password=None, redis_db=0
        )

        expected = "redis://localhost:6380/0"
        assert settings.redis_url == expected

    def test_default_settings_values(self, monkeypatch):
        """Test default configuration values are set correctly.

        CI sets ENVIRONMENT=test in the test job env which would otherwise
        override the default; clear it here so the assertion exercises the
        actual Settings default.
        """
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        settings = Settings()

        assert settings.service_name == "technical-analysis"
        assert settings.service_port == 8004
        assert settings.environment == "development"
        # default_rsi_period was tightened from 14 → 9 in the 2026-04-29
        # research-driven indicator-tuning pass.
        assert settings.default_rsi_period == 9
        assert settings.signal_confidence_threshold == 0.6


class TestGetSettings:
    """Test get_settings singleton function"""

    def test_get_settings_returns_settings_instance(self):
        """Test get_settings returns a Settings instance"""
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_get_settings_returns_same_instance(self):
        """Test get_settings returns singleton (same instance each time)"""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    @patch("app.config._settings", None)
    def test_get_settings_creates_instance_when_none(self):
        """Test get_settings creates new instance when global is None"""
        import app.config

        app.config._settings = None

        settings = get_settings()
        assert settings is not None
        assert isinstance(settings, Settings)
