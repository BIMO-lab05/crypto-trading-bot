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
from pydantic import Field, model_validator
from typing import Optional

# Ichimoku warm-up inputs, mirrored from app/indicators/ichimoku.py.
#
# ICHIMOKU_CONSTRUCTOR_DEFAULT_DISPLACEMENT mirrors IchimokuCalculator.__init__'s
# `displacement: int = 26` default (ichimoku.py:56). It is consumed as
# `min_periods = senkou_b_period + displacement` (ichimoku.py:75).
#
# The live path does NOT use that default: IndicatorService.calculate_ichimoku
# passes `displacement=kijun_period` (services/indicator_service.py:342-347),
# because conventional Ichimoku sets displacement == kijun. So the real warm-up
# is `senkou_b + kijun` for the service and `senkou_b + 26` for a direct
# constructor caller - the floor below takes the max of both rather than
# assuming either.
#
# ICHIMOKU_KUMO_BREAKOUT_LOOKBACK is the extra tail detect_kumo_breakout needs
# on top of min_periods; below it the 1.2x kumo boost silently stops firing
# (pinned by tests/unit/test_ichimoku_displacement.py:132-141).
#
# Do NOT diverge these from ichimoku.py without recording why - a split here
# makes the warm-up floor claim something the calculator does not honour.
ICHIMOKU_CONSTRUCTOR_DEFAULT_DISPLACEMENT = 26
ICHIMOKU_KUMO_BREAKOUT_LOOKBACK = 5


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

    # Moving Averages (SINGLE-SOURCED 2026-08-27, phase 21 P21-4)
    # Previous: 20 (this file's declared default)
    # Current: 21 (the value the traded signal has actually been running on)
    # Why: the trading-engine's signal_aggregator.fetch_sma/fetch_ema forced
    # `period=21` on every outbound call, so the traded path used 21 while a
    # bare GET /api/v1/indicators/sma/{symbol} resolved to 20 here - the same
    # silent split the 2026-08-20 MACD rewire closed. Changing the traded
    # signal's parameters silently is worse than moving the declaration, so
    # the declaration moves to meet the live signal and the engine now omits
    # the param (single source of truth is this file).
    default_sma_period: int = Field(
        default=21,
        description="SMA period - matches the live traded value (prev: 20)",
    )
    default_ema_period: int = Field(
        default=21,
        description="EMA period - matches the live traded value (prev: 20)",
    )

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

    # Ichimoku cloud (SINGLE-SOURCED 2026-08-27, phase 21 P21-5)
    # Previous: 9/26/52 (traditional Japanese-market values, 5-day work weeks)
    # Current: 20/60/120 (crypto-optimized for 24/7 trading, 7-day weeks)
    # Why: the trading-engine's signal_aggregator.fetch_ichimoku forced
    # 20/60/120 on every outbound call, and main.py's route descriptions have
    # advertised "crypto optimized: 20/60/120" since before this change - only
    # the declared defaults still said 9/26/52. Description, declaration and
    # traded value now agree; the engine omits the params.
    default_ichimoku_tenkan: int = Field(
        default=20,
        description="Ichimoku Tenkan-sen period - crypto-optimized (prev: 9)",
    )
    default_ichimoku_kijun: int = Field(
        default=60,
        description="Ichimoku Kijun-sen period - crypto-optimized (prev: 26)",
    )
    default_ichimoku_senkou_b: int = Field(
        default=120,
        description="Ichimoku Senkou Span B period - crypto-optimized (prev: 52)",
    )

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

    # Aggregate / multi-timeframe kline window (2026-08-27, phase 21 P21-4)
    # The number of klines the dashboard aggregate endpoint and the
    # multi-timeframe handler request (handlers/analysis.py). Declared here so
    # an operator moving it moves every leg's warm-up together instead of
    # editing a literal per call site. Bounds are deliberately permissive; the
    # binding constraint is the cross-field warm-up floor validated below, not
    # `ge`, so that an under-feeding value fails with a message naming the leg
    # that starved rather than a bare range error.
    default_aggregate_limit: int = Field(
        default=200,
        ge=100,
        le=1000,
        description=(
            "Klines requested by the aggregate and multi-timeframe handlers. "
            "Must clear the slowest indicator's warm-up (see the validator)."
        ),
    )

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

    @model_validator(mode="after")
    def _aggregate_limit_clears_indicator_warmup(self) -> "Settings":
        """Reject an aggregate window too short to feed the slowest leg.

        Both floors are DERIVED from the other fields, never hardcoded - a
        literal here would be a new mirror inside the change whose purpose is
        removing mirrors, and it would go stale the moment a period moves.

        TrendFilter's slow EMA is the binding floor today (200). Ichimoku is
        included even though the aggregate handler constructs no Ichimoku
        calculator right now: this is the service-wide aggregate window, and a
        future leg addition must not silently under-feed it. Under-feeding is
        silent by construction - IchimokuCalculator.calculate() returns None
        below min_periods and the caller degrades to a neutral read rather
        than erroring.
        """
        trend_floor = self.default_trend_slow_period

        # Live displacement is kijun (indicator_service.py:342-347); a direct
        # constructor caller gets 26 (ichimoku.py:56). Take whichever is larger
        # so the floor is valid for both callers. +lookback keeps the
        # kumo-breakout boost alive rather than merely avoiding a None.
        displacement = max(self.default_ichimoku_kijun, ICHIMOKU_CONSTRUCTOR_DEFAULT_DISPLACEMENT)
        ichimoku_floor = (
            self.default_ichimoku_senkou_b + displacement + ICHIMOKU_KUMO_BREAKOUT_LOOKBACK
        )

        floor = max(trend_floor, ichimoku_floor)
        if self.default_aggregate_limit < floor:
            raise ValueError(
                f"default_aggregate_limit={self.default_aggregate_limit} is below "
                f"the indicator warm-up floor of {floor} klines. Contributing "
                f"floors: trend slow EMA needs {trend_floor} "
                f"(default_trend_slow_period), Ichimoku needs {ichimoku_floor} "
                f"(senkou_b {self.default_ichimoku_senkou_b} + displacement "
                f"{displacement} + kumo lookback "
                f"{ICHIMOKU_KUMO_BREAKOUT_LOOKBACK}). Raise "
                f"DEFAULT_AGGREGATE_LIMIT or lower the period that dominates."
            )
        return self


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get settings singleton"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
