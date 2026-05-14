"""
Technical Analysis Service - Configuration
Purpose: Service configuration management

RESEARCH-BASED OPTIMIZATION (2025-11-28):
Default parameters updated based on analysis of top open-source trading bots
(Freqtrade, Hummingbot, Jesse) for crypto-specific optimization:

RSI:
- Period: 14 -> 9 (more responsive for crypto volatility)
- Research shows 9-period RSI better captures crypto momentum

MACD (Updated 2025-11-29 - Kang 2021 Study):
- Fast EMA: 12 -> 5 (research-optimized)
- Slow EMA: 26 -> 35 (longer trend detection)
- Signal: 9 -> 5 (faster signal response)
- Research: 5-35-5 achieves +11% annual vs -3.6% for standard 12-26-9

NOTE: Parameters should be re-optimized quarterly using walk-forward
optimization with 6-month historical windows.
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
    market_data_url: str = Field(default="http://localhost:8002")

    # Redis (caching)
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_password: Optional[str] = Field(default=None)
    redis_db: int = Field(default=0)

    # ==========================================================================
    # TECHNICAL ANALYSIS SETTINGS - RESEARCH-OPTIMIZED (2025-11-28)
    # ==========================================================================
    # Based on analysis of Freqtrade, Hummingbot, Jesse open-source trading bots
    # Optimized for crypto market volatility and 82.68% target accuracy
    # Re-optimize quarterly using 6-month walk-forward windows
    # ==========================================================================

    # RSI Settings (RESEARCH-OPTIMIZED)
    # Previous: period=14 (traditional markets)
    # New: period=9 (crypto-optimized, more responsive)
    default_rsi_period: int = Field(
        default=9, description="RSI period - optimized for crypto (prev: 14)"
    )

    # MACD Settings (RESEARCH-OPTIMIZED 2025-11-29)
    # Kang 2021 Study Results:
    #   - Default 12-26-9: -3.6% annual return
    #   - Optimized 5-35-5: +11% annual return (+14.6% improvement)
    # Previous: 8/17/9 (earlier crypto optimization)
    # Current: 5/35/5 (research-backed optimal for crypto)
    default_macd_fast: int = Field(
        default=5,
        description="MACD fast EMA - research-optimized 5-35-5 (prev: 8, std: 12)",
    )
    default_macd_slow: int = Field(
        default=35,
        description="MACD slow EMA - research-optimized 5-35-5 (prev: 17, std: 26)",
    )
    default_macd_signal: int = Field(
        default=5, description="MACD signal line - research-optimized 5-35-5 (prev: 9)"
    )

    # Bollinger Bands (RESEARCH-OPTIMIZED 2025-11-29)
    # Research shows wider bands (2.5-3.0 SD) work better for crypto volatility
    # Reduces false breakout signals in volatile crypto markets
    default_bb_period: int = Field(default=20)
    default_bb_std: float = Field(
        default=2.5,
        description="BB std dev - widened for crypto volatility (prev: 2.0)",
    )

    # Moving Averages (unchanged)
    default_sma_period: int = Field(default=20)
    default_ema_period: int = Field(default=20)

    # Signal Generation
    # RESEARCH NOTE: 0.6 confidence threshold works well with crypto-optimized indicators
    signal_confidence_threshold: float = Field(default=0.6)

    # Caching TTL
    cache_ttl_indicator: int = Field(default=300)  # 5 minutes
    cache_ttl_signal: int = Field(default=60)  # 1 minute

    @property
    def redis_url(self) -> str:
        """Construct Redis connection URL"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore",  # Ignore extra environment variables (like DB_* from other services)
    }


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get settings singleton"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
