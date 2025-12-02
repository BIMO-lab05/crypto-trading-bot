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
    market_data_url: str = Field(
        default="http://localhost:8002",
        description="Market Data Service URL for fetching live prices"
    )
    bybit_connector_url: str = Field(
        default="http://bybit-connector:8001",
        description="Bybit Connector Service URL"
    )
    portfolio_manager_url: str = Field(
        default="http://localhost:8006",
        description="Portfolio Manager Service URL"
    )

    # Phase 3 ML/AI Service URLs
    ml_prediction_url: str = Field(
        default="http://localhost:8007",
        description="ML Prediction Service URL for trend/price predictions"
    )
    sentiment_analysis_url: str = Field(
        default="http://localhost:8008",
        description="Sentiment Analysis Service URL (Phase 3)"
    )
    notification_service_url: str = Field(
        default="http://localhost:8006",
        description="Notification Service URL for trade alerts"
    )

    # Notification Settings
    enable_notifications: bool = Field(
        default=True,
        description="Enable trade notifications via Telegram/Email"
    )
    notify_on_trade_open: bool = Field(
        default=True,
        description="Send notification when trade is opened"
    )
    notify_on_trade_close: bool = Field(
        default=True,
        description="Send notification when trade is closed"
    )
    notify_on_daily_summary: bool = Field(
        default=True,
        description="Send daily PnL summary notification"
    )

    # Phase 3 Feature Flags - ENABLED 2025-12-02
    enable_ml_predictions: bool = Field(
        default=True,
        description="Enable ML predictions in signal aggregation (30% weight)"
    )
    enable_sentiment_analysis: bool = Field(
        default=True,
        description="Enable sentiment analysis in signal aggregation (15% weight)"
    )
    enable_multi_timeframe: bool = Field(
        default=False,
        description="Enable multi-timeframe analysis (15% weight)"
    )

    # Multi-Timeframe Alignment Requirements (2025-12-01)
    mtf_require_alignment: bool = Field(
        default=True,
        description="Require TF alignment before trading (reduces false signals)"
    )
    mtf_min_alignment_score: float = Field(
        default=60.0,
        ge=0.0,
        le=100.0,
        description="Minimum MTF alignment score (0-100) to execute trades"
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
        default=[
            # OPTIMIZED LIST (2025-12-02) - Removed underperformers, prioritized winners
            # Tier 1: Best performers (BNBUSDT 83% WR - highest priority)
            "BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT",
            # Tier 2: Large caps (good liquidity) - REMOVED XRPUSDT (30% WR worst performer)
            "ADAUSDT", "DOGEUSDT", "AVAXUSDT",
            # Tier 3: Popular alts (moderate liquidity)
            "LINKUSDT", "POLUSDT", "DOTUSDT", "LTCUSDT",
            # Tier 4: Trending coins
            "ARBUSDT", "OPUSDT", "APTUSDT", "SUIUSDT"
        ],
        description="Optimized 15 trading pairs - removed XRPUSDT (worst performer)"
    )
    default_interval: str = Field(
        default="60",
        description="Default candlestick interval"
    )

    # Trade Frequency Settings - EXPANDED for 16 symbols (2025-12-01)
    max_daily_trades: int = Field(
        default=40,
        ge=1,
        le=100,
        description="Maximum trades per day (increased for 16 symbols)"
    )
    check_frequency_seconds: int = Field(
        default=30,
        ge=10,
        le=300,
        description="How often to check for signals (seconds)"
    )
    allow_same_symbol_reentry: bool = Field(
        default=True,
        description="Allow re-entry on same symbol after position closed"
    )
    min_time_between_trades_same_symbol: int = Field(
        default=60,
        ge=0,
        le=3600,
        description="Minimum seconds between trades on same symbol"
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
        default=80.0,
        ge=5.0,
        le=100.0,
        description="Maximum total exposure as % of capital (80% to allow 20+ positions)"
    )
    default_stop_loss_pct: float = Field(
        default=2.0,
        ge=0.5,
        le=10.0,
        description="Default stop loss as % from entry (2% for 1:2 R/R ratio)"
    )
    default_take_profit_pct: float = Field(
        default=4.0,
        ge=1.0,
        le=50.0,
        description="Default take profit as % from entry (4% for 1:2 R/R ratio)"
    )

    # Signal Thresholds - RESEARCH-OPTIMIZED (2025-12-02)
    # Based on: 3Commas, Bitsgap, Cryptohopper best practices
    # Higher thresholds = fewer but higher quality trades
    min_signal_confidence: float = Field(
        default=0.60,
        ge=0.0,
        le=1.0,
        description="RESEARCH: 0.60+ confidence for 55-65% win rate"
    )
    # Need 3 indicators from different categories for consensus
    min_consensus_indicators: int = Field(
        default=3,
        ge=1,
        le=10,
        description="RESEARCH: 3 indicators from different categories (Trend+Momentum+Volume)"
    )

    # Time-Based Trading Filters (RESEARCH-BACKED 2025-12-01)
    # Best trading hours: 14:00-17:00 UTC (London/NY overlap)
    # Avoid: weekends, early morning UTC, low volume periods
    enable_time_filters: bool = Field(
        default=True,
        description="Enable time-based trade filtering for quality"
    )
    trading_start_hour_utc: int = Field(
        default=8,
        ge=0,
        le=23,
        description="Start trading hour UTC (8:00 = European open)"
    )
    trading_end_hour_utc: int = Field(
        default=21,
        ge=0,
        le=23,
        description="End trading hour UTC (21:00 = US close)"
    )
    avoid_weekends: bool = Field(
        default=True,
        description="Avoid trading on weekends (lower volume)"
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
