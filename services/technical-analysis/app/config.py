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

    # ==========================================================================
    # ADVANCED INDICATOR ENDPOINT DEFAULTS (2026-08-20)
    # ==========================================================================
    # Single source of truth for the wired indicator endpoints' Query()
    # defaults; classic /sqzmom routes (main.py, handlers/sqzmom.py) keep
    # local literals by design.
    # Each field carries the previously hardcoded endpoint literal and is
    # env-overridable (e.g. DEFAULT_TREND_FAST_PERIOD=40). Endpoint handlers
    # and main.py routes must reference these instead of literals; drift is
    # pinned by tests/test_endpoint_defaults_from_settings.py.
    # ==========================================================================

    # Trend filter (dual EMA)
    default_trend_fast_period: int = Field(default=50)
    default_trend_slow_period: int = Field(default=200)
    default_trend_limit: int = Field(default=300)

    # Volume confirmation
    default_volume_period: int = Field(default=20)
    default_volume_signal_type: str = Field(default="breakout")
    # INCREASED 2026-02-25: 50 -> 100 for better volume analysis
    default_volume_limit: int = Field(default=100)

    # ATR
    default_atr_period: int = Field(default=14)

    # Stochastic oscillator
    default_stochastic_period: int = Field(default=14)
    default_stochastic_smooth_k: int = Field(default=3)
    default_stochastic_smooth_d: int = Field(default=3)

    # RSI divergence
    default_rsi_divergence_period: int = Field(default=14)
    default_rsi_divergence_lookback: int = Field(default=20)

    # Ichimoku cloud
    default_ichimoku_tenkan: int = Field(default=9)
    default_ichimoku_kijun: int = Field(default=26)
    default_ichimoku_senkou_b: int = Field(default=52)

    # Enhanced squeeze momentum
    default_sqzmom_bb_period: int = Field(default=20)
    default_sqzmom_bb_mult: float = Field(default=2.0)
    default_sqzmom_kc_period: int = Field(default=20)
    default_sqzmom_kc_mult: float = Field(default=1.5)
    default_sqzmom_mom_period: int = Field(default=12)

    # ADX
    default_adx_period: int = Field(default=14)
    default_adx_trending_threshold: float = Field(default=25.0)
    default_adx_weak_trend_threshold: float = Field(default=20.0)
    default_adx_strong_trend_threshold: float = Field(default=30.0)

    # Caching TTL
    # Kline fetch cache (fetcher.py) — the only cache that is actually wired.
    # <= 0 disables. Keep well under the market-data collector's 5-minute
    # cadence; 30s means a signal cycle's ~12 identical window requests cost
    # one TimescaleDB query instead of twelve (2026-08-12 DB stampede fix).
    kline_cache_ttl_seconds: int = Field(default=30)

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
