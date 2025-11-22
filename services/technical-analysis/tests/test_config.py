"""
Tests for Configuration Module
Coverage target: config.py lines 61-63, 68
"""

import pytest
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
            redis_db=1
        )
        
        expected = "redis://:secret123@redis-server:6379/1"
        assert settings.redis_url == expected
    
    def test_redis_url_without_password(self):
        """Test redis_url property constructs correct URL without password"""
        settings = Settings(
            redis_host="localhost",
            redis_port=6380,
            redis_password=None,
            redis_db=0
        )
        
        expected = "redis://localhost:6380/0"
        assert settings.redis_url == expected
    
    def test_rabbitmq_url_construction(self):
        """Test rabbitmq_url property constructs correct AMQP URL"""
        settings = Settings(
            rabbitmq_user="admin",
            rabbitmq_password="pass123",
            rabbitmq_host="rabbitmq-server",
            rabbitmq_port=5672,
            rabbitmq_vhost="trading"
        )
        
        expected = "amqp://admin:pass123@rabbitmq-server:5672/trading"
        assert settings.rabbitmq_url == expected
    
    def test_default_settings_values(self):
        """Test default configuration values are set correctly"""
        settings = Settings()
        
        assert settings.service_name == "technical-analysis"
        assert settings.service_port == 8004
        assert settings.environment == "development"
        assert settings.default_rsi_period == 14
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
    
    @patch('app.config._settings', None)
    def test_get_settings_creates_instance_when_none(self):
        """Test get_settings creates new instance when global is None"""
        import app.config
        app.config._settings = None
        
        settings = get_settings()
        assert settings is not None
        assert isinstance(settings, Settings)
