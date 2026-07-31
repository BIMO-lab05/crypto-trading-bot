"""
Market Data Service - Configuration
Purpose: Service configuration management
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Market Data Service settings"""

    # Environment
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    debug: bool = Field(default=False)

    # Service
    service_name: str = Field(default="market-data-service")
    # 8002 matches the production / compose port. Was 8003 in the in-code
    # default, which collided with portfolio-manager (also 8003) on
    # standalone runs. The compose stack overrode this via SERVICE_PORT,
    # so the live system was fine — this is the standalone-run fix.
    service_port: int = Field(default=8002)
    service_host: str = Field(default="0.0.0.0")

    # TimescaleDB (market data storage)
    timescale_host: str = Field(default="localhost")
    timescale_port: int = Field(
        default=5432
    )  # Internal Docker port, not host-mapped port
    timescale_user: str = Field(default="cryptobot")
    timescale_password: str = Field(default="change_this_secure_password")
    timescale_db: str = Field(default="market_data")

    # PostgreSQL (application data)
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_user: str = Field(default="cryptobot")
    postgres_password: str = Field(default="change_this_secure_password")
    postgres_db: str = Field(default="cryptobot")

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

    # Bybit Connector Service
    # Phase 13 (BC-05/D-09): bybit-connector listens on :8001; the prior default
    # was a copy-paste of market-data-service's own :8002 — harmless under the
    # compose stack (env overrides) but a misroute for any host-side script that
    # constructed Settings() without setting BYBIT_CONNECTOR_URL.
    bybit_connector_url: str = Field(default="http://localhost:8001")

    # Mirror of the BYBIT_TESTNET env var on bybit-connector. Used to tag
    # ingested klines with `is_mainnet=not bybit_testnet` so the table
    # can later be filtered by source. Operators must keep this in sync
    # with whatever bybit-connector is running against. Audit 2026-04-29.
    bybit_testnet: bool = Field(
        default=False,
        description="True if connector is on testnet — newly-ingested klines get is_mainnet=False",
    )

    # Data Collection Settings - 14 ACTIVE symbols (2026-05-03)
    # SYNCHRONIZED with trading-engine config.py
    # 2026-05-03: ETH re-added per operator request (was excluded 2025-12-05).
    # Still excluded: XRP (-$39.73, 23% WR), DOGE (-$9.81, 30% WR).
    default_symbols: str = Field(
        default=(
            # TIER 1: MEGA CAPS (Core trading pairs, highest liquidity)
            "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,ADAUSDT,AVAXUSDT,LINKUSDT,"
            # TIER 2: VERIFIED ALTCOINS (Working indicators, good historical data)
            "ARBUSDT,OPUSDT,SUIUSDT,"
            # TIER 3: NEWLY ADDED (2025-12-05) - All have 1000 klines, 41 days data
            "APTUSDT,DOTUSDT,LTCUSDT,POLUSDT"
        )
    )
    default_interval: str = Field(default="60")  # 1 hour
    fetch_historical_days: int = Field(default=30)  # Fetch last 30 days on startup

    # Data freshness
    #
    # Ticker collection runs every 5 minutes, so three consecutive missed
    # cycles is unambiguous failure rather than jitter. Beyond this age a
    # stored row is treated as a cache miss (triggering a live re-fetch) and
    # /ready reports the service as not ready.
    #
    # This exists because ingest once stopped for 17 hours while every read
    # kept returning the last stored row as current, with HTTP 200 and a green
    # /health -- see .planning/audits/2026-07-31-full-system-diagnostic.md DL-1.
    market_data_staleness_seconds: int = Field(default=900, ge=60)

    # Caching
    cache_ttl_ticker: int = Field(default=5)  # 5 seconds for ticker
    cache_ttl_kline: int = Field(default=60)  # 1 minute for kline
    cache_ttl_orderbook: int = Field(default=2)  # 2 seconds for orderbook

    # Database Connection Pool
    db_pool_min_size: int = Field(default=10)
    db_pool_max_size: int = Field(default=20)

    @property
    def timescale_url(self) -> str:
        """Construct TimescaleDB connection URL"""
        return f"postgresql+asyncpg://{self.timescale_user}:{self.timescale_password}@{self.timescale_host}:{self.timescale_port}/{self.timescale_db}"

    @property
    def postgres_url(self) -> str:
        """Construct PostgreSQL connection URL"""
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def redis_url(self) -> str:
        """Construct Redis connection URL"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def symbols_list(self) -> list:
        """Get list of trading symbols"""
        return [s.strip() for s in self.default_symbols.split(",")]

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore",  # Ignore extra environment variables (like DB_*, API_KEYS)
    }


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get settings singleton"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
