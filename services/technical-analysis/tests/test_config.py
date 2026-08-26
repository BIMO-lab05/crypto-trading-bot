"""
Tests for Configuration Module
Coverage target: config.py lines 61-63, 68
"""

from unittest.mock import patch
from app.config import Settings, get_settings


class TestSettings:
    """Test Settings configuration class"""

    def test_dead_config_removed(self):
        """Redis + unused cache/signal fields were dead config, deleted
        2026-08-20: nothing in this app ever read them (the only wired cache
        is kline_cache_ttl_seconds, fetcher.py)."""
        settings = Settings()
        for gone in (
            "redis_host",
            "redis_port",
            "redis_password",
            "redis_db",
            "redis_url",
            "cache_ttl_indicator",
            "cache_ttl_signal",
            "signal_confidence_threshold",
        ):
            assert not hasattr(settings, gone), f"{gone} should be deleted"

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
        assert settings.kline_cache_ttl_seconds == 30


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
