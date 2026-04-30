"""
ML Retraining Service Configuration
Purpose: Centralized configuration for automated model retraining
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional


class RetrainingSettings(BaseSettings):
    """ML Model Retraining Service Configuration"""

    # Service Configuration
    service_name: str = Field(default="ml-retraining-service", description="Service name")
    service_host: str = Field(default="0.0.0.0", description="Host to bind to")
    service_port: int = Field(default=8009, description="Port to bind to")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # External Service URLs
    ml_prediction_url: str = Field(
        default="http://localhost:8007",
        description="ML Prediction Service URL for model operations"
    )
    market_data_url: str = Field(
        default="http://localhost:8002",
        description="Market Data Service URL for fetching training data"
    )
    notification_service_url: str = Field(
        default="http://localhost:8006",
        description="Notification Service URL for alerts"
    )

    # Retraining Schedule
    retrain_schedule_enabled: bool = Field(
        default=True,
        description="Enable automated retraining on schedule"
    )
    retrain_schedule_cron: str = Field(
        default="0 2 * * 1",  # Every Monday at 2 AM UTC
        description="Cron expression for retraining schedule"
    )
    retrain_on_demand_enabled: bool = Field(
        default=True,
        description="Enable manual trigger via API endpoint"
    )

    # Data Collection Settings
    retrain_data_days: int = Field(
        default=180,
        ge=30,
        le=365,
        description="Days of historical data to use for retraining"
    )
    retrain_data_intervals: List[str] = Field(
        default=["60"],
        description="Kline intervals to fetch for training (e.g., 15, 60, 240)"
    )
    retrain_data_symbols: List[str] = Field(
        default=["SOLUSDT", "BNBUSDT", "ADAUSDT"],
        description="Symbols to retrain models for"
    )

    # Training Configuration
    retrain_parallel_jobs: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of symbols to train in parallel"
    )
    retrain_max_epochs: int = Field(
        default=100,
        ge=10,
        le=500,
        description="Maximum training epochs (with early stopping)"
    )
    retrain_batch_size: int = Field(
        default=32,
        ge=8,
        le=128,
        description="Training batch size"
    )
    retrain_gpu_enabled: bool = Field(
        default=False,
        description="Use GPU for training if available"
    )

    # Validation Thresholds
    retrain_min_r2: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Minimum R² score for model deployment"
    )
    retrain_min_improvement: float = Field(
        default=0.02,
        ge=0.0,
        le=0.5,
        description="Minimum R² improvement required to deploy (2% = 0.02)"
    )
    retrain_max_degradation: float = Field(
        default=0.10,
        ge=0.0,
        le=0.5,
        description="Maximum allowed metric degradation (10% = 0.10)"
    )
    retrain_min_dsr: Optional[float] = Field(
        default=None,
        description=(
            "Deflated Sharpe Ratio gate (0..1). When set, retrains failing "
            "this threshold are not deployed. None disables the gate "
            "(DSR is still recorded as informational). 0.95 = 5% significance "
            "level after correcting for non-normality and selection bias."
        ),
    )
    retrain_target_mode: str = Field(
        default="price",
        pattern="^(price|log_returns)$",
        description=(
            "Training target. 'price' (default) preserves the legacy "
            "behaviour — model predicts raw close price, R² is "
            "autocorrelation-dominated (V0 finding c56765c). "
            "'log_returns' targets the 1-bar log-return directly; the "
            "T0.1 GRU rebuild uses this. Either way the on-disk artifact "
            "shape is unchanged: scaler_y maps the chosen target to "
            "[0,1] and the inference path recovers prices via "
            "last_close * exp(predicted_log_return) when needed."
        ),
    )
    retrain_feature_set: str = Field(
        default="legacy",
        pattern="^(legacy|stationary)$",
        description=(
            "Feature pipeline. 'legacy' (default) is the 22-indicator "
            "pile that mixes stationary and non-stationary inputs — what "
            "every production retrain has used. 'stationary' is the T0.1 "
            "rebuild's 17-feature stationary-only set: drops sma_*, "
            "ema_*, bb_middle/upper/lower, volume_sma, high_low_ratio; "
            "adds vol-of-vol, log-volume change, range-ratio, time-of-day "
            "sin/cos. See app/core/stationary_features.py."
        ),
    )
    retrain_min_r2_returns: Optional[float] = Field(
        default=None,
        description=(
            "R²-on-log-returns gate. When set, retrains failing this "
            "threshold are not deployed. None disables (R²-returns is "
            "still recorded informationally). Per the T0.1 design, the "
            "rebuild's pre-flight gate is `> 0.0` — naive persistence "
            "scores ~0 on log-returns, so any positive value means the "
            "model carries information beyond persistence."
        ),
    )
    retrain_min_dir_acc: Optional[float] = Field(
        default=None,
        description=(
            "Corrected directional-accuracy gate (0..1). When set, retrains "
            "failing this threshold are not deployed. None disables (the "
            "metric is still recorded informationally). T0.1 design's "
            "pre-flight gate is `> 0.55` — clearly above coin-flip after "
            "the V0 metric fix (commit c56765c)."
        ),
    )

    # Deployment Settings
    retrain_auto_deploy: bool = Field(
        default=True,
        description="Automatically deploy models that pass validation"
    )
    retrain_backup_before_deploy: bool = Field(
        default=True,
        description="Backup current production model before deployment"
    )
    retrain_rollback_on_error: bool = Field(
        default=True,
        description="Automatically rollback on deployment errors"
    )

    # Notification Settings
    retrain_notify_success: bool = Field(
        default=True,
        description="Send notification on successful retraining"
    )
    retrain_notify_failure: bool = Field(
        default=True,
        description="Send notification on retraining failure"
    )
    retrain_telegram_enabled: bool = Field(
        default=True,
        description="Send alerts via Telegram"
    )

    # Database Configuration
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5433)
    postgres_db: str = Field(default="ml_retraining")
    postgres_user: str = Field(default="cryptobot")
    postgres_password: str = Field(default="")

    # Redis Configuration
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=5)
    redis_password: str = Field(default="")

    # Model Storage Paths
    models_production_dir: str = Field(
        default="./models/production",
        description="Directory for production models"
    )
    models_versions_dir: str = Field(
        default="./models/versions",
        description="Directory for model version history"
    )
    models_backups_dir: str = Field(
        default="./models/backups",
        description="Directory for pre-deployment backups"
    )

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
_settings: RetrainingSettings | None = None


def get_settings() -> RetrainingSettings:
    """Get or create settings instance"""
    global _settings
    if _settings is None:
        _settings = RetrainingSettings()
    return _settings


def reload_settings() -> RetrainingSettings:
    """Reload settings from environment"""
    global _settings
    _settings = RetrainingSettings()
    return _settings
