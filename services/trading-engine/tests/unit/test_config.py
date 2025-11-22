"""
Unit Tests for Configuration Module
Tests settings validation, properties, and singleton behavior
"""

import pytest
from pydantic import ValidationError

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))

from app.config import Settings, get_settings, reload_settings


class TestSettings:
    """Test suite for Settings configuration"""

    def test_settings_defaults(self):
        """Test that settings have correct default values"""
        settings = Settings()

        assert settings.service_name == "trading-engine"
        assert settings.service_port == 8005
        assert settings.trading_mode == "PAPER"
        assert settings.default_symbol == "BTCUSDT"
        assert settings.max_position_size_pct == 2.0
        assert settings.paper_initial_balance == 10000.0

    def test_log_level_validator_valid(self):
        """Test log level validator with valid values"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

        for level in valid_levels:
            settings = Settings(log_level=level)
            assert settings.log_level == level.upper()

            # Test lowercase
            settings = Settings(log_level=level.lower())
            assert settings.log_level == level.upper()

    def test_log_level_validator_invalid(self):
        """Test log level validator with invalid value"""
        with pytest.raises(ValidationError) as exc_info:
            Settings(log_level="INVALID")

        assert "Log level must be one of" in str(exc_info.value)

    def test_trading_mode_validator_valid(self):
        """Test trading mode validator with valid values"""
        settings = Settings(trading_mode="PAPER")
        assert settings.trading_mode == "PAPER"

        settings = Settings(trading_mode="LIVE")
        assert settings.trading_mode == "LIVE"

    def test_trading_mode_validator_invalid(self):
        """Test trading mode validator with invalid value"""
        with pytest.raises(ValidationError) as exc_info:
            Settings(trading_mode="INVALID")

        # Pydantic's literal type validation happens before custom validator
        assert "Input should be 'PAPER' or 'LIVE'" in str(exc_info.value)

    def test_database_url_property(self):
        """Test database_url property"""
        settings = Settings(
            postgres_user="testuser",
            postgres_password="testpass",
            postgres_host="localhost",
            postgres_port=5432,
            postgres_db="testdb"
        )

        expected_url = "postgresql+asyncpg://testuser:testpass@localhost:5432/testdb"
        assert settings.database_url == expected_url

    def test_redis_url_property_with_password(self):
        """Test redis_url property with password"""
        settings = Settings(
            redis_host="localhost",
            redis_port=6379,
            redis_db=0,
            redis_password="secret"
        )

        expected_url = "redis://:secret@localhost:6379/0"
        assert settings.redis_url == expected_url

    def test_redis_url_property_without_password(self):
        """Test redis_url property without password"""
        settings = Settings(
            redis_host="localhost",
            redis_port=6379,
            redis_db=0,
            redis_password=""
        )

        expected_url = "redis://localhost:6379/0"
        assert settings.redis_url == expected_url

    def test_risk_management_validation(self):
        """Test risk management field validation"""
        # Valid values within range
        settings = Settings(
            max_position_size_pct=5.0,
            max_daily_loss_pct=10.0,
            max_total_exposure_pct=50.0
        )

        assert settings.max_position_size_pct == 5.0
        assert settings.max_daily_loss_pct == 10.0
        assert settings.max_total_exposure_pct == 50.0


class TestSettingsSingleton:
    """Test suite for settings singleton behavior"""

    def test_get_settings_singleton(self):
        """Test that get_settings returns the same instance"""
        settings1 = get_settings()
        settings2 = get_settings()

        # Should be the same instance
        assert settings1 is settings2

    def test_reload_settings(self):
        """Test that reload_settings creates a new instance"""
        settings1 = get_settings()
        settings2 = reload_settings()

        # Should be a new instance
        assert settings1 is not settings2

        # But get_settings should now return the new instance
        settings3 = get_settings()
        assert settings3 is settings2


class TestFieldValidation:
    """Test suite for field validation ranges"""

    def test_max_position_size_range(self):
        """Test max_position_size_pct validation"""
        # Valid value
        settings = Settings(max_position_size_pct=5.0)
        assert settings.max_position_size_pct == 5.0

        # Test boundaries
        settings = Settings(max_position_size_pct=0.1)
        assert settings.max_position_size_pct == 0.1

        settings = Settings(max_position_size_pct=10.0)
        assert settings.max_position_size_pct == 10.0

    def test_min_signal_confidence_range(self):
        """Test min_signal_confidence validation"""
        # Valid values
        settings = Settings(min_signal_confidence=0.0)
        assert settings.min_signal_confidence == 0.0

        settings = Settings(min_signal_confidence=0.5)
        assert settings.min_signal_confidence == 0.5

        settings = Settings(min_signal_confidence=1.0)
        assert settings.min_signal_confidence == 1.0


# Test configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
