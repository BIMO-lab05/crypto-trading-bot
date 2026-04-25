"""
Pydantic models for ML Prediction Service API
Defines request and response schemas
"""

from datetime import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


# Health check models
class HealthResponse(BaseModel):
    """Health check response"""
    status: str = "healthy"
    service: str = "ml-prediction-service"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ReadyResponse(BaseModel):
    """Readiness check response"""
    ready: bool
    models_loaded: bool
    dependencies_available: Dict[str, bool]


# Prediction models
class PricePoint(BaseModel):
    """Single price prediction point"""
    timestamp: datetime
    predicted_price: float = Field(..., description="Predicted price value")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Prediction confidence (0-1)")
    lower_bound: float = Field(..., description="Lower confidence interval")
    upper_bound: float = Field(..., description="Upper confidence interval")


class PricePrediction(BaseModel):
    """Multi-step price prediction"""
    symbol: str = Field(..., description="Trading pair (e.g., BTCUSDT)")
    interval: str = Field(..., description="Timeframe (e.g., 60m)")
    current_price: float = Field(..., description="Latest price")

    predictions: List[PricePoint] = Field(..., description="Future price predictions")

    # Prediction metadata
    model_type: str = Field(..., description="ML model used (LSTM, GRU, etc.)")
    model_version: str = Field(..., description="Model version identifier")
    model_last_trained: datetime = Field(..., description="When model was last trained")

    # Prediction statistics
    average_confidence: float = Field(..., ge=0.0, le=1.0)
    prediction_horizon_minutes: int = Field(..., description="How far ahead prediction goes")

    # Direction signal
    predicted_direction: str = Field(..., description="UP, DOWN, or SIDEWAYS")
    directional_strength: float = Field(..., ge=0.0, le=1.0, description="How strong is the direction")


class TrendPrediction(BaseModel):
    """Trend classification prediction"""
    symbol: str
    interval: str

    # Trend classification
    trend: str = Field(..., description="BULLISH, BEARISH, or NEUTRAL")
    trend_confidence: float = Field(..., ge=0.0, le=1.0)
    trend_strength: float = Field(..., ge=0.0, le=1.0, description="How strong is the trend")

    # Reversal probability
    reversal_probability: float = Field(..., ge=0.0, le=1.0, description="Chance of trend reversal")
    reversal_timeframe: Optional[str] = Field(None, description="Expected reversal timeframe")

    # Support levels prediction
    predicted_support_levels: List[float] = Field(default_factory=list)
    predicted_resistance_levels: List[float] = Field(default_factory=list)

    # Model metadata
    model_accuracy: float = Field(..., description="Historical model accuracy")
    prediction_timestamp: datetime = Field(default_factory=datetime.utcnow)


class VolatilityPrediction(BaseModel):
    """Volatility forecast"""
    symbol: str
    interval: str

    # Current volatility
    current_volatility: float = Field(..., description="Current ATR or volatility measure")

    # Predicted volatility
    predicted_volatility_1h: float
    predicted_volatility_4h: float
    predicted_volatility_24h: float

    # Volatility trend
    volatility_trend: str = Field(..., description="INCREASING, DECREASING, or STABLE")
    volatility_confidence: float = Field(..., ge=0.0, le=1.0)

    # Risk assessment
    risk_level: str = Field(..., description="LOW, MEDIUM, HIGH, or EXTREME")
    recommended_position_size_multiplier: float = Field(..., description="Adjust position size by this factor")

    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ModelInfo(BaseModel):
    """Model information and performance"""
    model_type: str
    model_version: str
    symbols_supported: List[str]
    intervals_supported: List[str]

    # Training info
    last_trained: datetime
    training_samples: int
    training_duration_seconds: float

    # Performance metrics
    validation_accuracy: float = Field(..., description="Accuracy on validation set")
    validation_mae: float = Field(..., description="Mean Absolute Error")
    validation_rmse: float = Field(..., description="Root Mean Squared Error")
    validation_r2_score: float = Field(..., description="R² score")

    # Feature importance
    top_features: List[Dict[str, float]] = Field(default_factory=list, description="Most important features")

    # Model status
    status: str = Field(..., description="READY, TRAINING, ERROR")
    needs_retraining: bool = Field(default=False)


class TrainingRequest(BaseModel):
    """Request to train or retrain a model"""
    symbol: str
    interval: str = "60"
    lookback_days: int = Field(default=90, ge=30, le=365, description="Days of historical data")
    force_retrain: bool = Field(default=False, description="Force retrain even if recent model exists")


class TrainingResponse(BaseModel):
    """Response from model training"""
    success: bool
    message: str
    model_version: str
    training_duration_seconds: float
    model_info: Optional[ModelInfo] = None
    error: Optional[str] = None
