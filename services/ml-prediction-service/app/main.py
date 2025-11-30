"""
ML Prediction Service - FastAPI Application
Provides machine learning-based price predictions
"""

import logging
import httpx
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Dict
from pathlib import Path
import pandas as pd

from fastapi import FastAPI, HTTPException, Query, Path as FastAPIPath, BackgroundTasks, Request
from fastapi.responses import Response
import sys
import uuid
from pathlib import Path

# Prometheus metrics imports
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Import local utils (fallback for Docker container where shared utils are not available)
try:
    # Try shared utils first (for local development)
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))
    from utils.structured_logging import setup_logging, RequestContextLogger
    from utils.graceful_shutdown import GracefulShutdownHandler
except ImportError:
    # Fall back to local utils (for Docker container)
    from app.utils.structured_logging import setup_logging, RequestContextLogger
    from app.utils.graceful_shutdown import GracefulShutdownHandler

from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.models import (
    HealthResponse,
    ReadyResponse,
    PricePrediction,
    TrendPrediction,
    VolatilityPrediction,
    ModelInfo,
    TrainingRequest,
    TrainingResponse
)
from app.predictor import LSTMPricePredictor, TENSORFLOW_AVAILABLE
from app.ml_models.gru_model import GRUPricePredictor
from app.predictor_factory import PredictorFactory, ModelComparator

# Create logs directory
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Settings
settings = get_settings()

# Global predictors cache - supports both LSTM and GRU
lstm_predictors: Dict[str, LSTMPricePredictor] = {}
gru_predictors: Dict[str, GRUPricePredictor] = {}

# HTTP client for calling other services
http_client: httpx.AsyncClient = None

# === PROMETHEUS METRICS ===

# HTTP request counter
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

# HTTP request duration histogram
http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

# Active requests gauge
http_requests_active = Gauge(
    'http_requests_active',
    'Number of active HTTP requests'
)

# ML-specific metrics
ml_predictions_total = Counter(
    'ml_predictions_total',
    'Total ML predictions made',
    ['symbol', 'model_type']
)

ml_prediction_duration_seconds = Histogram(
    'ml_prediction_duration_seconds',
    'ML prediction duration in seconds',
    ['symbol', 'model_type']
)

ml_models_loaded = Gauge(
    'ml_models_loaded',
    'Number of ML models currently loaded',
    ['model_type']
)

ml_training_total = Counter(
    'ml_training_total',
    'Total ML model training operations',
    ['symbol', 'model_type', 'status']
)

ml_training_duration_seconds = Histogram(
    'ml_training_duration_seconds',
    'ML model training duration in seconds',
    ['symbol', 'model_type']
)

ml_prediction_confidence = Histogram(
    'ml_prediction_confidence',
    'ML prediction confidence scores',
    ['symbol', 'model_type']
)

# === END PROMETHEUS METRICS ===


async def get_http_client() -> httpx.AsyncClient:
    """Get or create HTTP client"""
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)
    return http_client


async def close_http_client():
    """Close HTTP client"""
    global http_client
    if http_client:
        await http_client.aclose()
        http_client = None


def get_lstm_predictor(symbol: str, interval: str) -> LSTMPricePredictor:
    """Get or create LSTM predictor for symbol/interval"""
    key = f"{symbol}_{interval}"
    if key not in lstm_predictors:
        lstm_predictors[key] = LSTMPricePredictor(symbol, interval)
        ml_models_loaded.labels(model_type='LSTM').inc()
    return lstm_predictors[key]


def get_gru_predictor(symbol: str, interval: str) -> GRUPricePredictor:
    """Get or create GRU predictor for symbol/interval"""
    key = f"{symbol}_{interval}"
    if key not in gru_predictors:
        gru_predictors[key] = GRUPricePredictor(symbol, interval)
        ml_models_loaded.labels(model_type='GRU').inc()
    return gru_predictors[key]


def get_predictor(symbol: str, interval: str, model_type: str = "LSTM"):
    """
    Get predictor based on model type

    Args:
        symbol: Trading pair
        interval: Timeframe in minutes
        model_type: Either 'LSTM' or 'GRU'

    Returns:
        Predictor instance
    """
    model_type = model_type.upper()
    if model_type == "GRU":
        return get_gru_predictor(symbol, interval)
    else:
        return get_lstm_predictor(symbol, interval)


async def fetch_historical_data(symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
    """
    Fetch historical data from Market Data Service

    Args:
        symbol: Trading pair
        interval: Timeframe in minutes
        limit: Number of candles to fetch

    Returns:
        DataFrame with OHLCV data (timestamp, open, high, low, close, volume ONLY)
    """
    try:
        client = await get_http_client()
        url = f"{settings.market_data_url}/api/v1/klines/{symbol}"
        params = {"interval": interval, "limit": limit}

        response = await client.get(url, params=params)
        response.raise_for_status()

        data = response.json()

        # Extract data array from wrapped response
        if isinstance(data, dict) and 'data' in data:
            data = data['data']

        # Convert to DataFrame
        df = pd.DataFrame(data)

        # Ensure required columns exist
        required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        # **FIX FOR FEATURE MISMATCH**
        # Filter to ONLY required columns to match training data
        # This prevents extra columns (symbol, interval, turnover, created_at) from causing feature mismatch
        df = df[required_cols]

        # Convert timestamp to datetime
        if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        # Convert price columns to float
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        logger.debug(f"Fetched {len(df)} candles with {len(df.columns)} columns: {list(df.columns)}")

        return df

    except Exception as e:
        logger.error(f"Error fetching historical data: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to fetch market data: {str(e)}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    logger.info(f"Starting {settings.service_name} on port {settings.service_port}")
    logger.info(f"TensorFlow available: {TENSORFLOW_AVAILABLE}")
    logger.info(f"Market Data URL: {settings.market_data_url}")
    logger.info(f"Supported models: {PredictorFactory.get_supported_models()}")

    # Initialize HTTP client
    await get_http_client()

    # Check TensorFlow availability
    if not TENSORFLOW_AVAILABLE:
        logger.warning("⚠️ TensorFlow not installed. ML predictions will not be available.")
        logger.warning("Install with: pip install tensorflow scikit-learn")

    yield

    # Cleanup
    logger.info("Shutting down ML Prediction Service")
    await close_http_client()


# FastAPI app
app = FastAPI(
    title="ML Prediction Service",
    description="Machine learning-based price predictions for crypto assets (LSTM & GRU)",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === PROMETHEUS MIDDLEWARE ===

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Track all HTTP requests with Prometheus metrics"""
    # Increment active requests
    http_requests_active.inc()

    # Extract method and path
    method = request.method
    path = request.url.path

    # Start timer
    start_time = datetime.utcnow()

    try:
        # Process request
        response = await call_next(request)

        # Calculate duration
        duration = (datetime.utcnow() - start_time).total_seconds()

        # Record metrics
        http_request_duration_seconds.labels(method=method, endpoint=path).observe(duration)
        http_requests_total.labels(method=method, endpoint=path, status=response.status_code).inc()

        return response
    finally:
        # Decrement active requests
        http_requests_active.dec()


# === END PROMETHEUS MIDDLEWARE ===


# Prometheus metrics endpoint
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# Health endpoints
@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        service="ml-prediction-service"
    )


@app.get("/ready", response_model=ReadyResponse, tags=["Health"])
async def readiness_check():
    """Readiness check endpoint"""
    # Check if TensorFlow is available
    tensorflow_ready = TENSORFLOW_AVAILABLE

    # Check if we can reach market data service
    try:
        client = await get_http_client()
        response = await client.get(f"{settings.market_data_url}/health", timeout=5.0)
        market_data_ready = response.status_code == 200
    except:
        market_data_ready = False

    # Check if any models are loaded
    models_loaded = len(lstm_predictors) > 0 or len(gru_predictors) > 0

    return ReadyResponse(
        ready=tensorflow_ready and market_data_ready,
        models_loaded=models_loaded,
        dependencies_available={
            "tensorflow": tensorflow_ready,
            "market_data_service": market_data_ready
        }
    )


# Prediction endpoints
@app.get("/api/v1/predict/price/{symbol}", response_model=PricePrediction, tags=["Predictions"])
async def predict_price(
    symbol: str = FastAPIPath(..., description="Trading pair (e.g., BTCUSDT)"),
    interval: str = Query("60", description="Timeframe in minutes"),
    model_type: str = Query("LSTM", description="Model type: LSTM or GRU")
):
    """
    Get price prediction for a symbol using specified model type

    Returns predicted prices for the next N periods (configured in settings)

    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        interval: Timeframe in minutes (default: 60)
        model_type: Either 'LSTM' or 'GRU' (default: LSTM)
    """
    if not TENSORFLOW_AVAILABLE:
        raise HTTPException(status_code=503, detail="TensorFlow not available")

    # Start prediction timer
    start_time = datetime.utcnow()

    try:
        # Get predictor based on model type
        predictor = get_predictor(symbol, interval, model_type)

        # Check if model exists and is trained
        if predictor.model is None:
            raise HTTPException(
                status_code=404,
                detail=f"No trained {model_type} model found for {symbol} {interval}m. Please train the model first."
            )

        # Check if model needs retraining
        if predictor.needs_retraining():
            logger.warning(f"{model_type} model for {symbol} {interval}m needs retraining (last trained: {predictor.last_trained})")

        # Fetch recent data
        recent_data = await fetch_historical_data(symbol, interval, limit=settings.sequence_length + 50)

        # Make prediction
        prediction = await predictor.predict(recent_data)

        # Record metrics
        duration = (datetime.utcnow() - start_time).total_seconds()
        ml_prediction_duration_seconds.labels(symbol=symbol, model_type=model_type).observe(duration)
        ml_predictions_total.labels(symbol=symbol, model_type=model_type).inc()
        ml_prediction_confidence.labels(symbol=symbol, model_type=model_type).observe(prediction.average_confidence)

        return prediction

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Prediction error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")


@app.get("/api/v1/predict/trend/{symbol}", response_model=TrendPrediction, tags=["Predictions"])
async def predict_trend(
    symbol: str = FastAPIPath(..., description="Trading pair"),
    interval: str = Query("60", description="Timeframe in minutes"),
    model_type: str = Query("LSTM", description="Model type: LSTM or GRU")
):
    """
    Get trend prediction (BULLISH, BEARISH, NEUTRAL)

    Uses ML model + technical analysis to determine overall trend
    """
    # This is a simplified version - in production, would use a separate classifier
    try:
        # Get price prediction
        price_pred = await predict_price(symbol, interval, model_type)

        # Determine trend from predictions
        first_pred = price_pred.predictions[0].predicted_price
        last_pred = price_pred.predictions[-1].predicted_price
        price_change_pct = ((last_pred - price_pred.current_price) / price_pred.current_price) * 100

        # Classify trend
        if price_change_pct > 2.0:
            trend = "BULLISH"
            trend_strength = min(1.0, price_change_pct / 10.0)
        elif price_change_pct < -2.0:
            trend = "BEARISH"
            trend_strength = min(1.0, abs(price_change_pct) / 10.0)
        else:
            trend = "NEUTRAL"
            trend_strength = 0.5

        # Calculate reversal probability (simplified)
        reversal_probability = 1.0 - price_pred.average_confidence

        # Get support/resistance from predictions
        predicted_prices = [p.predicted_price for p in price_pred.predictions]
        predicted_support = [min(predicted_prices)]
        predicted_resistance = [max(predicted_prices)]

        return TrendPrediction(
            symbol=symbol,
            interval=f"{interval}m",
            trend=trend,
            trend_confidence=price_pred.average_confidence,
            trend_strength=trend_strength,
            reversal_probability=reversal_probability,
            reversal_timeframe=f"{len(price_pred.predictions) * int(interval)} minutes",
            predicted_support_levels=predicted_support,
            predicted_resistance_levels=predicted_resistance,
            model_accuracy=price_pred.average_confidence,
            prediction_timestamp=datetime.utcnow()
        )

    except Exception as e:
        logger.error(f"Trend prediction error: {e}")
        raise HTTPException(status_code=500, detail=f"Trend prediction failed: {str(e)}")


@app.get("/api/v1/predict/volatility/{symbol}", response_model=VolatilityPrediction, tags=["Predictions"])
async def predict_volatility(
    symbol: str = FastAPIPath(..., description="Trading pair"),
    interval: str = Query("60", description="Timeframe in minutes")
):
    """
    Predict future volatility

    Helps with position sizing and risk management
    """
    try:
        # Fetch historical data
        df = await fetch_historical_data(symbol, interval, limit=100)

        # Calculate current volatility (using rolling std of returns)
        df['returns'] = df['close'].pct_change()
        current_volatility = float(df['returns'].rolling(window=20).std().iloc[-1] * 100)

        # Simple volatility forecast (in production, would use GARCH or similar)
        # For now, use recent trend
        recent_vol = df['returns'].rolling(window=5).std().iloc[-1] * 100
        predicted_1h_vol = float(recent_vol * 1.1)
        predicted_4h_vol = float(recent_vol * 1.2)
        predicted_24h_vol = float(recent_vol * 1.3)

        # Determine volatility trend
        vol_change = (recent_vol - current_volatility) / current_volatility
        if vol_change > 0.1:
            vol_trend = "INCREASING"
        elif vol_change < -0.1:
            vol_trend = "DECREASING"
        else:
            vol_trend = "STABLE"

        # Risk level assessment
        if current_volatility > 5.0:
            risk_level = "EXTREME"
            size_multiplier = 0.3
        elif current_volatility > 3.0:
            risk_level = "HIGH"
            size_multiplier = 0.5
        elif current_volatility > 1.5:
            risk_level = "MEDIUM"
            size_multiplier = 0.8
        else:
            risk_level = "LOW"
            size_multiplier = 1.2

        return VolatilityPrediction(
            symbol=symbol,
            interval=f"{interval}m",
            current_volatility=current_volatility,
            predicted_volatility_1h=predicted_1h_vol,
            predicted_volatility_4h=predicted_4h_vol,
            predicted_volatility_24h=predicted_24h_vol,
            volatility_trend=vol_trend,
            volatility_confidence=0.7,
            risk_level=risk_level,
            recommended_position_size_multiplier=size_multiplier
        )

    except Exception as e:
        logger.error(f"Volatility prediction error: {e}")
        raise HTTPException(status_code=500, detail=f"Volatility prediction failed: {str(e)}")


# Model management endpoints
@app.get("/api/v1/models/{symbol}", response_model=ModelInfo, tags=["Model Management"])
async def get_model_info(
    symbol: str = FastAPIPath(..., description="Trading pair"),
    interval: str = Query("60", description="Timeframe in minutes"),
    model_type: str = Query("LSTM", description="Model type: LSTM or GRU")
):
    """Get information about a trained model"""
    try:
        predictor = get_predictor(symbol, interval, model_type)

        if predictor.model is None:
            raise HTTPException(status_code=404, detail=f"No {model_type} model found for {symbol} {interval}m")

        return ModelInfo(
            model_type=model_type.upper(),
            model_version=predictor.model_version or "unknown",
            symbols_supported=[symbol],
            intervals_supported=[f"{interval}m"],
            last_trained=predictor.last_trained or datetime.utcnow(),
            training_samples=predictor.training_stats.get('train_samples', 0),
            training_duration_seconds=0.0,  # Not tracked in metadata currently
            validation_accuracy=predictor.training_stats.get('r2_score', 0.0),
            validation_mae=predictor.training_stats.get('mae', 0.0),
            validation_rmse=predictor.training_stats.get('rmse', 0.0),
            validation_r2_score=predictor.training_stats.get('r2_score', 0.0),
            top_features=[],
            status="READY" if predictor.model else "UNTRAINED",
            needs_retraining=predictor.needs_retraining()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting model info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/models/train", response_model=TrainingResponse, tags=["Model Management"])
async def train_model(
    request: TrainingRequest,
    background_tasks: BackgroundTasks
):
    """
    Train or retrain an LSTM model

    This is a long-running operation and will run in the background
    """
    if not TENSORFLOW_AVAILABLE:
        raise HTTPException(status_code=503, detail="TensorFlow not available")

    # Start training timer
    start_time = datetime.utcnow()

    try:
        # Get LSTM predictor
        predictor = get_lstm_predictor(request.symbol, request.interval)

        # Check if model already exists and is recent
        if predictor.model is not None and not request.force_retrain:
            if not predictor.needs_retraining():
                ml_training_total.labels(symbol=request.symbol, model_type='LSTM', status='skipped').inc()
                return TrainingResponse(
                    success=False,
                    message=f"LSTM model already trained recently ({predictor.last_trained}). Use force_retrain=true to retrain.",
                    model_version=predictor.model_version or "unknown",
                    training_duration_seconds=0.0
                )

        # Fetch historical data
        logger.info(f"Fetching {request.lookback_days} days of data for LSTM training")
        limit = int((request.lookback_days * 24 * 60) / int(request.interval))  # Convert days to candles
        # Cap at 10000 (market-data service maximum)
        limit = min(limit, 10000)
        logger.info(f"Calculated limit: {limit} candles (capped at 10000)")
        historical_data = await fetch_historical_data(request.symbol, request.interval, limit=limit)

        # Train model
        model_info = await predictor.train(historical_data)
        training_duration = (datetime.utcnow() - start_time).total_seconds()

        # Record metrics
        ml_training_duration_seconds.labels(symbol=request.symbol, model_type='LSTM').observe(training_duration)
        ml_training_total.labels(symbol=request.symbol, model_type='LSTM', status='success').inc()

        return TrainingResponse(
            success=True,
            message=f"LSTM model trained successfully with {len(historical_data)} samples",
            model_version=model_info.model_version,
            training_duration_seconds=training_duration,
            model_info=model_info
        )

    except Exception as e:
        logger.error(f"LSTM training error: {e}", exc_info=True)
        ml_training_total.labels(symbol=request.symbol, model_type='LSTM', status='failed').inc()
        return TrainingResponse(
            success=False,
            message="LSTM training failed",
            model_version="error",
            training_duration_seconds=0.0,
            error=str(e)
        )


@app.post("/api/v1/models/train-gru/{symbol}", response_model=TrainingResponse, tags=["Model Management"])
async def train_gru_model(
    symbol: str = FastAPIPath(..., description="Trading pair"),
    interval: str = Query("60", description="Timeframe in minutes"),
    lookback_days: int = Query(90, ge=30, le=365, description="Days of historical data"),
    force_retrain: bool = Query(False, description="Force retrain even if recent model exists")
):
    """
    Train or retrain a GRU model

    GRU (Gated Recurrent Unit) benefits:
    - Faster training than LSTM (25-30% faster)
    - Fewer parameters (more efficient)
    - Similar or better performance
    - Better for shorter sequences

    This is a long-running operation
    """
    if not TENSORFLOW_AVAILABLE:
        raise HTTPException(status_code=503, detail="TensorFlow not available")

    # Start training timer
    start_time = datetime.utcnow()

    try:
        # Get GRU predictor
        predictor = get_gru_predictor(symbol, interval)

        # Check if model already exists and is recent
        if predictor.model is not None and not force_retrain:
            if not predictor.needs_retraining():
                ml_training_total.labels(symbol=symbol, model_type='GRU', status='skipped').inc()
                return TrainingResponse(
                    success=False,
                    message=f"GRU model already trained recently ({predictor.last_trained}). Use force_retrain=true to retrain.",
                    model_version=predictor.model_version or "unknown",
                    training_duration_seconds=0.0
                )

        # Fetch historical data
        logger.info(f"Fetching {lookback_days} days of data for GRU training")
        limit = int((lookback_days * 24 * 60) / int(interval))  # Convert days to candles
        # Cap at 10000 (market-data service maximum)
        limit = min(limit, 10000)
        logger.info(f"Calculated limit: {limit} candles (capped at 10000)")
        historical_data = await fetch_historical_data(symbol, interval, limit=limit)

        # Train GRU model
        model_info = await predictor.train(historical_data)
        training_duration = (datetime.utcnow() - start_time).total_seconds()

        logger.info(f"GRU training completed in {training_duration:.2f}s")

        # Record metrics
        ml_training_duration_seconds.labels(symbol=symbol, model_type='GRU').observe(training_duration)
        ml_training_total.labels(symbol=symbol, model_type='GRU', status='success').inc()

        return TrainingResponse(
            success=True,
            message=f"GRU model trained successfully with {len(historical_data)} samples",
            model_version=model_info.model_version,
            training_duration_seconds=training_duration,
            model_info=model_info
        )

    except Exception as e:
        logger.error(f"GRU training error: {e}", exc_info=True)
        ml_training_total.labels(symbol=symbol, model_type='GRU', status='failed').inc()
        return TrainingResponse(
            success=False,
            message="GRU training failed",
            model_version="error",
            training_duration_seconds=0.0,
            error=str(e)
        )


@app.get("/api/v1/models/compare/{symbol}", tags=["Model Management"])
async def compare_models(
    symbol: str = FastAPIPath(..., description="Trading pair"),
    interval: str = Query("60", description="Timeframe in minutes")
):
    """
    Compare LSTM vs GRU model performance

    Comparison metrics:
    - Prediction accuracy (RMSE, MAE, R², MAPE)
    - Directional accuracy
    - Inference speed
    - Training time
    - Model size
    - Parameter count

    Returns comprehensive comparison with winner determination
    """
    try:
        # Create comparator
        comparator = ModelComparator(symbol, interval)

        # Get training metrics comparison
        training_comparison = await comparator.compare_training_metrics()

        # Get prediction comparison if both models available
        prediction_comparison = None
        if comparator.lstm_predictor.model and comparator.gru_predictor.model:
            # Fetch recent data for predictions
            recent_data = await fetch_historical_data(symbol, interval, limit=settings.sequence_length + 50)
            prediction_comparison = await comparator.compare_predictions(recent_data)

        # Get recommendation
        recommendation = comparator.get_recommendation()

        return {
            'symbol': symbol,
            'interval': f"{interval}m",
            'timestamp': datetime.utcnow().isoformat(),
            'training_comparison': training_comparison,
            'prediction_comparison': prediction_comparison,
            'recommendation': recommendation,
            'summary': {
                'lstm_available': comparator.lstm_predictor.model is not None,
                'gru_available': comparator.gru_predictor.model is not None,
                'winner': training_comparison.get('winner', {}).get('overall', 'NONE')
            }
        }

    except Exception as e:
        logger.error(f"Model comparison error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")


# Utility endpoints
@app.get("/api/v1/models", tags=["Model Management"])
async def list_models():
    """List all loaded models (both LSTM and GRU)"""
    models = []

    # Add LSTM models
    for key, predictor in lstm_predictors.items():
        if predictor.model is not None:
            models.append({
                "model_type": "LSTM",
                "symbol": predictor.symbol,
                "interval": f"{predictor.interval}m",
                "version": predictor.model_version,
                "last_trained": predictor.last_trained.isoformat() if predictor.last_trained else None,
                "needs_retraining": predictor.needs_retraining()
            })

    # Add GRU models
    for key, predictor in gru_predictors.items():
        if predictor.model is not None:
            models.append({
                "model_type": "GRU",
                "symbol": predictor.symbol,
                "interval": f"{predictor.interval}m",
                "version": predictor.model_version,
                "last_trained": predictor.last_trained.isoformat() if predictor.last_trained else None,
                "needs_retraining": predictor.needs_retraining()
            })

    return {
        "total_models": len(models),
        "lstm_count": sum(1 for m in models if m['model_type'] == 'LSTM'),
        "gru_count": sum(1 for m in models if m['model_type'] == 'GRU'),
        "models": models
    }


@app.get("/api/v1/supported-models", tags=["Model Management"])
async def get_supported_models():
    """Get list of supported model types and their descriptions"""
    return {
        "supported_models": [
            {
                "type": "LSTM",
                "name": "Long Short-Term Memory",
                "description": "Advanced RNN with memory cells, best for long sequences",
                "parameters": "~3x GRU parameters",
                "training_speed": "Slower",
                "best_for": "Long-term dependencies, complex patterns"
            },
            {
                "type": "GRU",
                "name": "Gated Recurrent Unit",
                "description": "Efficient RNN variant, faster than LSTM",
                "parameters": "~2/3 LSTM parameters",
                "training_speed": "25-30% faster than LSTM",
                "best_for": "Shorter sequences, faster inference, resource constraints"
            }
        ],
        "default": "LSTM"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.service_port)
