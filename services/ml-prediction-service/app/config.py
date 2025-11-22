"""
Configuration for ML Prediction Service
Manages environment variables and service settings
"""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Service configuration using Pydantic BaseSettings
    Environment variables override default values
    """
    # Service info
    service_name: str = "ML Prediction Service"
    service_port: int = 8007
    environment: str = os.getenv("ENVIRONMENT", "development")

    # Dependent services
    market_data_url: str = os.getenv("MARKET_DATA_URL", "http://localhost:8003")
    technical_analysis_url: str = os.getenv("TECHNICAL_ANALYSIS_URL", "http://localhost:8004")

    # ML Model settings
    model_type: str = "LSTM"  # LSTM, GRU, or Transformer
    sequence_length: int = 60  # Number of candles to look back
    prediction_horizon: int = 5  # Predict N candles ahead (5 = 5 hours for 60m timeframe)

    # Feature engineering
    use_technical_indicators: bool = True  # Include RSI, MACD, etc.
    use_volume_features: bool = True  # Include volume-based features
    use_price_features: bool = True  # Include OHLC features

    # Model training
    train_test_split: float = 0.8  # 80% train, 20% test
    epochs: int = 50
    batch_size: int = 32
    learning_rate: float = 0.001

    # Model persistence - FIXED: Use absolute path that works in container
    models_dir: str = os.getenv("MODELS_DIR", "/app/models")
    model_retrain_days: int = 7  # Retrain model every N days

    # Performance thresholds
    min_prediction_confidence: float = 0.60  # Minimum confidence to return prediction
    prediction_timeout_seconds: int = 5  # Max time for prediction API call

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        protected_namespaces = ('settings_',)  # Fix pydantic warnings


@lru_cache()
def get_settings() -> Settings:
    """
    Cached settings instance (created once per application lifecycle)
    """
    return Settings()
