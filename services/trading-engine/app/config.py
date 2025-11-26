"""
Configuration Module for Trading Engine
Purpose: Centralized configuration management using Pydantic settings
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, List


class Settings(BaseSettings):
    """Trading Engine Service Configuration"""

    # Service Configuration
    service_name: str = Field(default="trading-engine", description="Service name")
    service_host: str = Field(default="0.0.0.0", description="Host to bind to")
    service_port: int = Field(default=8005, description="Port to bind to")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # Service URLs
    technical_analysis_url: str = Field(
        default="http://localhost:8004",
        description="Technical Analysis Service URL"
    )
    bybit_connector_url: str = Field(
        default="http://localhost:8002",
        description="Bybit Connector Service URL"
    )
    portfolio_manager_url: str = Field(
        default="http://localhost:8006",
        description="Portfolio Manager Service URL"
    )

    # Trading Configuration
    trading_mode: Literal["PAPER", "LIVE"] = Field(
        default="PAPER",
        description="Trading mode: PAPER or LIVE"
    )
    auto_trading_enabled: bool = Field(
        default=False,
        description="Enable automatic trading"
    )
    default_strategy: str = Field(
        default="consensus",
        description="Default trading strategy"
    )
    default_symbol: str = Field(
        default="BTCUSDT",
        description="Default trading symbol"
    )
    trading_symbols: List[str] = Field(
        default=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        description="List of symbols to trade in auto-trader"
    )
    default_interval: str = Field(
        default="60",
        description="Default candlestick interval"
    )

    # Risk Management
    max_position_size_pct: float = Field(
        default=2.0,
        ge=0.1,
        le=10.0,
        description="Maximum position size as % of capital"
    )
    max_daily_loss_pct: float = Field(
        default=5.0,
        ge=1.0,
        le=20.0,
        description="Maximum daily loss as % of capital"
    )
    max_total_exposure_pct: float = Field(
        default=20.0,
        ge=5.0,
        le=100.0,
        description="Maximum total exposure as % of capital"
    )
    default_stop_loss_pct: float = Field(
        default=3.0,
        ge=0.5,
        le=10.0,
        description="Default stop loss as % from entry"
    )
    default_take_profit_pct: float = Field(
        default=6.0,
        ge=1.0,
        le=50.0,
        description="Default take profit as % from entry"
    )

    # Signal Thresholds - ADJUSTED FOR MORE AGGRESSIVE TRADING (2025-11-26)
    # Changed from 0.5 to 0.45 to allow trades with 45%+ confidence
    min_signal_confidence: float = Field(
        default=0.45,
        ge=0.0,
        le=1.0,
        description="Minimum signal confidence to trade (lowered from 0.5 to 0.45)"
    )
    # Changed from 3 to 2 for more flexibility (2 out of 6-7 voting indicators)
    min_consensus_indicators: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Minimum indicators in agreement (2 out of 6-7 voting indicators)"
    )

    # Database Configuration
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5433)
    postgres_db: str = Field(default="trading_engine")
    postgres_user: str = Field(default="cryptobot")
    postgres_password: str = Field(default="")

    # Redis Configuration
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=2)
    redis_password: str = Field(default="")

    # Paper Trading
    paper_initial_balance: float = Field(
        default=10000.0,
        ge=100.0,
        description="Initial balance for paper trading"
    )
    paper_commission_pct: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Commission percentage for paper trading"
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.upper()

    @field_validator("trading_mode")
    @classmethod
    def validate_trading_mode(cls, v):
        """Validate trading mode"""
        if v.upper() not in ["PAPER", "LIVE"]:
            raise ValueError("Trading mode must be PAPER or LIVE")
        return v.upper()

    @property
    def database_url(self) -> str:
        """Get database connection URL"""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        """Get Redis connection URL"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create settings instance"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment"""
    global _settings
    _settings = Settings()
    return _settings
