"""
API Gateway Configuration
Centralized configuration for the gateway service
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """API Gateway configuration settings"""

    # Service Configuration
    service_name: str = Field(default="api-gateway", description="Service identifier")
    service_port: int = Field(default=8000, ge=1024, le=65535, description="Service port")
    log_level: str = Field(default="INFO", description="Logging level")

    # Backend Service URLs
    # Defaults match the canonical port table in CLAUDE.md and
    # docker-compose.unified.yml. (Previous defaults had multiple
    # off-by-one errors and a port collision between risk_metrics and
    # ml_prediction at 8007 — fixed 2026-05-01.)
    bybit_connector_url: str = Field(
        default="http://localhost:8001",
        description="Bybit Connector service URL"
    )
    market_data_url: str = Field(
        default="http://localhost:8002",
        description="Market Data service URL"
    )
    technical_analysis_url: str = Field(
        default="http://localhost:8004",
        description="Technical Analysis service URL"
    )
    trading_engine_url: str = Field(
        default="http://localhost:8005",
        description="Trading Engine service URL"
    )
    portfolio_manager_url: str = Field(
        default="http://localhost:8003",
        description="Portfolio Manager service URL"
    )
    risk_metrics_url: str = Field(
        default="http://localhost:8009",
        description="Risk & Metrics service URL"
    )
    ml_prediction_url: str = Field(
        default="http://localhost:8007",
        description="ML Prediction service URL"
    )
    sentiment_analysis_url: str = Field(
        default="http://localhost:8008",
        description="Sentiment Analysis service URL"
    )

    # Security
    jwt_secret_key: str = Field(
        default="your-secret-key-change-in-production",
        description="JWT secret key"
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(
        default=30,
        ge=1,
        le=1440,
        description="Access token expiration in minutes"
    )

    # Rate Limiting
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_per_minute: int = Field(
        default=60,
        ge=1,
        description="Requests per minute per user"
    )
    rate_limit_burst: int = Field(default=10, ge=1, description="Burst allowance")

    # Caching
    cache_enabled: bool = Field(default=True, description="Enable response caching")
    cache_ttl_seconds: int = Field(
        default=60,
        ge=1,
        description="Cache time-to-live in seconds"
    )
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL"
    )

    # CORS
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origins"
    )

    # API Documentation
    api_title: str = Field(
        default="Crypto Trading Bot API Gateway",
        description="API title"
    )
    api_version: str = Field(default="1.0.0", description="API version")
    api_description: str = Field(
        default="Unified API Gateway for Crypto Trading Bot Services",
        description="API description"
    )

    # Model configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.upper()

    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, v: str) -> str:
        """Validate service name"""
        if not v or not v.strip():
            raise ValueError("Service name cannot be empty")
        return v.strip()


# Global settings instance
settings = Settings()
