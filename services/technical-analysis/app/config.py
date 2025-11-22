"""
Technical Analysis Service - Configuration
Purpose: Service configuration management
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Technical Analysis Service settings"""

    # Environment
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    debug: bool = Field(default=False)

    # Service
    service_name: str = Field(default="technical-analysis")
    service_port: int = Field(default=8004)
    service_host: str = Field(default="0.0.0.0")

    # Market Data Service
    market_data_url: str = Field(default="http://localhost:8003")

    # Redis (caching)
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_password: Optional[str] = Field(default=None)
    redis_db: int = Field(default=0)

    # RabbitMQ (messaging)
    rabbitmq_host: str = Field(default="localhost")
    rabbitmq_port: int = Field(default=5672)
    rabbitmq_user: str = Field(default="cryptobot")
    rabbitmq_password: str = Field(default="change_this_secure_password")
    rabbitmq_vhost: str = Field(default="cryptobot")

    # Technical Analysis Settings
    default_rsi_period: int = Field(default=14)
    default_macd_fast: int = Field(default=12)
    default_macd_slow: int = Field(default=26)
    default_macd_signal: int = Field(default=9)
    default_bb_period: int = Field(default=20)
    default_bb_std: float = Field(default=2.0)
    default_sma_period: int = Field(default=20)
    default_ema_period: int = Field(default=20)

    # Signal Generation
    signal_confidence_threshold: float = Field(default=0.6)
    enable_signal_publishing: bool = Field(default=True)

    # Caching TTL
    cache_ttl_indicator: int = Field(default=300)  # 5 minutes
    cache_ttl_signal: int = Field(default=60)  # 1 minute

    @property
    def redis_url(self) -> str:
        """Construct Redis connection URL"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def rabbitmq_url(self) -> str:
        """Construct RabbitMQ connection URL"""
        return f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}@{self.rabbitmq_host}:{self.rabbitmq_port}/{self.rabbitmq_vhost}"

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore"  # Ignore extra environment variables (like DB_* from other services)
    }


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get settings singleton"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
