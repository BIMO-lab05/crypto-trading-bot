"""
Configuration for ML Prediction Service
Manages environment variables and service settings
"""

import os
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings


# All 16 GRU models available for trading (trained Dec 9-10, 2025)
# These are the symbols with trained GRU models for 60-minute timeframe
ALL_GRU_SYMBOLS = [
    "BTCUSDT",    # Bitcoin - Major pair
    "ETHUSDT",    # Ethereum - Major pair
    "BNBUSDT",    # Binance Coin
    "SOLUSDT",    # Solana
    "XRPUSDT",    # XRP
    "ADAUSDT",    # Cardano
    "DOGEUSDT",   # Dogecoin
    "APTUSDT",    # Aptos
    "AVAXUSDT",   # Avalanche
    "DOTUSDT",    # Polkadot
    "LTCUSDT",    # Litecoin
    "LINKUSDT",   # Chainlink
    "OPUSDT",     # Optimism
    "POLUSDT",    # Polygon
    "SUIUSDT",    # Sui
    "ARBUSDT",    # Arbitrum
]

# High-priority symbols for SQZMOM strategy (preload first)
# These are L2/Layer 2 and newer altcoins with higher volatility
PRIORITY_SYMBOLS = [
    "BNBUSDT",    # High liquidity
    "SOLUSDT",    # High volatility
    "ADAUSDT",    # Popular altcoin
    "ARBUSDT",    # Layer 2
    "OPUSDT",     # Layer 2
    "POLUSDT",    # Layer 2
    "SUIUSDT",    # New chain
]


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
    model_type: str = "GRU"  # GRU (default, superior performance), LSTM, or Transformer
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

    # Model persistence - Use relative path from service root, or absolute if in Docker
    models_dir: str = os.getenv("MODELS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"))
    model_retrain_days: int = 7  # Retrain model every N days

    # Model preloading settings
    # Set to True to preload all GRU models at startup for faster inference
    preload_models: bool = os.getenv("PRELOAD_MODELS", "true").lower() == "true"
    # Set to True to preload only priority symbols (SQZMOM strategy)
    preload_priority_only: bool = os.getenv("PRELOAD_PRIORITY_ONLY", "false").lower() == "true"
    # Default interval for preloading (60 = 1 hour)
    default_interval: str = os.getenv("DEFAULT_INTERVAL", "60")

    # Performance thresholds
    min_prediction_confidence: float = 0.60  # Minimum confidence to return prediction
    prediction_timeout_seconds: int = 5  # Max time for prediction API call

    # Redis caching settings
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "2"))  # DB 2 for ML predictions
    redis_enabled: bool = os.getenv("REDIS_ENABLED", "true").lower() == "true"
    cache_ttl_seconds: int = 300  # Cache predictions for 5 minutes (60m candles)
    cache_prefix: str = "ml:prediction:"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        protected_namespaces = ('settings_',)  # Fix pydantic warnings
        extra = 'ignore'  # Ignore extra env vars from other services


@lru_cache()
def get_settings() -> Settings:
    """
    Cached settings instance (created once per application lifecycle)
    """
    return Settings()


def get_symbols_to_preload() -> List[str]:
    """
    Get list of symbols to preload based on configuration

    Returns:
        List of symbol strings to preload at startup
    """
    settings = get_settings()

    if not settings.preload_models:
        return []

    if settings.preload_priority_only:
        return PRIORITY_SYMBOLS

    return ALL_GRU_SYMBOLS


def get_available_gru_models() -> List[str]:
    """
    Discover available GRU models from the filesystem

    Returns:
        List of symbol strings that have trained GRU models
    """
    import glob
    settings = get_settings()

    # Find all GRU model files
    pattern = os.path.join(settings.models_dir, "*_60m_gru.keras")
    model_files = glob.glob(pattern)

    # Extract symbol names from filenames
    symbols = []
    for model_file in model_files:
        filename = os.path.basename(model_file)
        # Format: SYMBOL_60m_gru.keras
        symbol = filename.replace("_60m_gru.keras", "")
        symbols.append(symbol)

    return sorted(symbols)
