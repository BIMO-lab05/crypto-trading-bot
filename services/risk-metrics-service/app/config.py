"""
Configuration for Risk & Metrics Service
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Service configuration settings"""

    # Service Configuration
    service_name: str = "risk-metrics-service"
    service_port: int = 8007
    service_host: str = "0.0.0.0"
    log_level: str = "INFO"

    # External Services
    portfolio_manager_url: str = "http://localhost:8006"
    market_data_url: str = "http://localhost:8003"

    # Risk Management Parameters
    max_portfolio_risk: float = 0.05  # 5% max portfolio risk
    max_position_size: float = 0.02   # 2% max per position
    max_drawdown_threshold: float = 0.10  # 10% max drawdown before alert
    max_daily_loss: float = 0.05      # 5% daily loss limit
    max_exposure: float = 0.20        # 20% max total exposure

    # Performance Metrics
    risk_free_rate: float = 0.04      # 4% annual risk-free rate
    target_sharpe_ratio: float = 1.5  # Target Sharpe ratio
    lookback_period_days: int = 30    # Lookback period for metrics

    # Circuit Breakers
    enable_circuit_breaker: bool = True
    circuit_breaker_cooldown: int = 3600  # 1 hour cooldown in seconds

    # Database
    database_url: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
