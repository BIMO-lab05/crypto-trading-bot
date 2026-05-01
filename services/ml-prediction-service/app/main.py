"""
ML Prediction Service - FastAPI Application
Provides machine learning-based price predictions
"""

import logging
import httpx
import time
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Any, Dict, List
from pathlib import Path
import pandas as pd

from fastapi import (
    FastAPI,
    HTTPException,
    Query,
    Path as FastAPIPath,
    BackgroundTasks,
    Request,
)
from fastapi.responses import Response
import sys

# Prometheus metrics imports
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

# Import local utils (fallback for Docker container where shared utils are not available)
try:
    # Try shared utils first (for local development)
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))
    from utils.structured_logging import setup_logging, RequestContextLogger
    from utils.graceful_shutdown import GracefulShutdownHandler
except ImportError:
    # Fall back to local utils (for Docker container)
    pass

from fastapi.middleware.cors import CORSMiddleware

from app.config import (
    get_settings,
    get_symbols_to_preload,
    get_available_gru_models,
    ALL_GRU_SYMBOLS,
    PRIORITY_SYMBOLS,
)
from app.models import (
    HealthResponse,
    ReadyResponse,
    PricePrediction,
    TrendPrediction,
    VolatilityPrediction,
    ModelInfo,
    TrainingRequest,
    TrainingResponse,
)
from app.predictor import TENSORFLOW_AVAILABLE
from app.ml_models.gru_model import GRUPricePredictor
from app.predictor_factory import PredictorFactory, ModelComparator
from app.utils.redis_cache import PredictionCache
from app.inference import EnsemblePredictor, EnsembleSignal
from app.models.ensemble_model import EnsemblePredictor as EnhancedEnsemblePredictor

# Create logs directory
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Settings
settings = get_settings()

# Global GRU predictor cache (LSTM removed — GRU replaced LSTM late 2025)
gru_predictors: Dict[str, GRUPricePredictor] = {}

# Track preloading statistics
preload_stats = {
    "started_at": None,
    "completed_at": None,
    "duration_seconds": 0.0,
    "total_attempted": 0,
    "total_loaded": 0,
    "failed": [],
    "preload_enabled": True,
}

# HTTP client for calling other services
http_client: httpx.AsyncClient = None

# Redis prediction cache
prediction_cache: PredictionCache = None

# Ensemble predictor combining TA + ML + Sentiment + MultiTimeframe
ensemble_predictor: EnsemblePredictor = None

# === PROMETHEUS METRICS ===

# HTTP request counter
http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)

# HTTP request duration histogram
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

# Active requests gauge
http_requests_active = Gauge("http_requests_active", "Number of active HTTP requests")

# ML-specific metrics
ml_predictions_total = Counter(
    "ml_predictions_total", "Total ML predictions made", ["symbol", "model_type"]
)

ml_prediction_duration_seconds = Histogram(
    "ml_prediction_duration_seconds",
    "ML prediction duration in seconds",
    ["symbol", "model_type"],
)

ml_models_loaded = Gauge(
    "ml_models_loaded", "Number of ML models currently loaded", ["model_type"]
)

ml_training_total = Counter(
    "ml_training_total",
    "Total ML model training operations",
    ["symbol", "model_type", "status"],
)

ml_training_duration_seconds = Histogram(
    "ml_training_duration_seconds",
    "ML model training duration in seconds",
    ["symbol", "model_type"],
)

ml_prediction_confidence = Histogram(
    "ml_prediction_confidence",
    "ML prediction confidence scores",
    ["symbol", "model_type"],
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


def get_gru_predictor(symbol: str, interval: str) -> GRUPricePredictor:
    """Get or create GRU predictor for symbol/interval"""
    key = f"{symbol}_{interval}"
    if key not in gru_predictors:
        gru_predictors[key] = GRUPricePredictor(symbol, interval)
        ml_models_loaded.labels(model_type="GRU").inc()
    return gru_predictors[key]


def get_predictor(symbol: str, interval: str, model_type: str = "GRU"):
    """
    Get GRU predictor for symbol/interval. LSTM is no longer supported
    (removed late 2025; GRU replaced it with avg R²=0.92 vs LSTM ~0.85).
    """
    model_type = model_type.upper()
    if model_type == "GRU":
        return get_gru_predictor(symbol, interval)
    raise ValueError(f"Unsupported model_type: {model_type}. Only 'GRU' is supported.")


def preload_gru_models() -> Dict:
    """
    Preload all configured GRU models at startup

    This function:
    1. Discovers available GRU models from filesystem
    2. Loads all 16 GRU models into memory
    3. Tracks loading statistics for monitoring

    Returns:
        Dictionary with preloading statistics
    """
    global preload_stats

    if not TENSORFLOW_AVAILABLE:
        logger.warning("TensorFlow not available - skipping model preload")
        preload_stats["preload_enabled"] = False
        return preload_stats

    start_time = time.time()
    preload_stats["started_at"] = datetime.utcnow().isoformat()

    # Get symbols to preload based on configuration
    symbols_to_preload = get_symbols_to_preload()
    available_models = get_available_gru_models()

    logger.info(f"Model preloading configured: {len(symbols_to_preload)} symbols")
    logger.info(
        f"Available GRU models on disk: {len(available_models)} ({', '.join(available_models)})"
    )

    preload_stats["total_attempted"] = len(symbols_to_preload)
    preload_stats["failed"] = []

    loaded_count = 0
    interval = settings.default_interval

    for symbol in symbols_to_preload:
        try:
            # Check if model file exists on disk
            if symbol not in available_models:
                logger.warning(f"Model file not found for {symbol} - skipping")
                preload_stats["failed"].append(
                    {"symbol": symbol, "reason": "Model file not found on disk"}
                )
                continue

            # Load the predictor (this loads the model from disk)
            predictor = get_gru_predictor(symbol, interval)

            if predictor.model is not None:
                loaded_count += 1
                logger.info(
                    f"[{loaded_count}/{len(symbols_to_preload)}] Preloaded {symbol} GRU model "
                    f"(version: {predictor.model_version}, R2: {predictor.training_stats.get('r2_score', 'N/A'):.4f})"
                )
            else:
                preload_stats["failed"].append(
                    {
                        "symbol": symbol,
                        "reason": "Model loaded but model object is None",
                    }
                )
                logger.warning(f"Failed to load model for {symbol} - model is None")

        except Exception as e:
            preload_stats["failed"].append({"symbol": symbol, "reason": str(e)})
            logger.error(f"Error preloading {symbol}: {e}")

    # Update statistics
    preload_stats["completed_at"] = datetime.utcnow().isoformat()
    preload_stats["duration_seconds"] = round(time.time() - start_time, 2)
    preload_stats["total_loaded"] = loaded_count

    logger.info(
        f"Model preloading complete: {loaded_count}/{len(symbols_to_preload)} models loaded "
        f"in {preload_stats['duration_seconds']:.2f}s"
    )

    if preload_stats["failed"]:
        logger.warning(
            f"Failed to load {len(preload_stats['failed'])} models: "
            f"{[f['symbol'] for f in preload_stats['failed']]}"
        )

    return preload_stats


async def fetch_historical_data(
    symbol: str, interval: str, limit: int = 500
) -> pd.DataFrame:
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
        if isinstance(data, dict) and "data" in data:
            data = data["data"]

        # Convert to DataFrame
        df = pd.DataFrame(data)

        # Ensure required columns exist
        required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        # **FIX FOR FEATURE MISMATCH**
        # Filter to ONLY required columns to match training data
        # This prevents extra columns (symbol, interval, turnover, created_at) from causing feature mismatch
        df = df[required_cols]

        # Convert timestamp to datetime
        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        # Convert price columns to float
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        logger.debug(
            f"Fetched {len(df)} candles with {len(df.columns)} columns: {list(df.columns)}"
        )

        return df

    except Exception as e:
        logger.error(f"Error fetching historical data: {e}")
        raise HTTPException(
            status_code=503, detail=f"Failed to fetch market data: {str(e)}"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    global prediction_cache, ensemble_predictor

    logger.info(f"Starting {settings.service_name} on port {settings.service_port}")
    logger.info(f"TensorFlow available: {TENSORFLOW_AVAILABLE}")
    logger.info(f"Market Data URL: {settings.market_data_url}")
    logger.info(f"Supported models: {PredictorFactory.get_supported_models()}")

    # Initialize HTTP client
    await get_http_client()

    # Initialize Redis prediction cache
    prediction_cache = PredictionCache(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        ttl_seconds=settings.cache_ttl_seconds,
        key_prefix=settings.cache_prefix,
        enabled=settings.redis_enabled,
    )
    await prediction_cache.connect()

    # Initialize Ensemble Predictor
    # Combines TA (40%) + ML (30%) + Sentiment (15%) + MultiTimeframe (15%)
    ensemble_predictor = EnsemblePredictor(
        ta_weight=0.40,
        ml_weight=0.30,
        sentiment_weight=0.15,
        multi_tf_weight=0.15,
        ta_service_url=settings.technical_analysis_url,
        ml_service_url=f"http://localhost:{settings.service_port}",  # Self-reference for ML predictions
        market_data_url=settings.market_data_url,
    )
    logger.info(
        "Ensemble Predictor initialized with weights: TA=40%, ML=30%, Sentiment=15%, MultiTF=15%"
    )

    # Check TensorFlow availability
    if not TENSORFLOW_AVAILABLE:
        logger.warning(
            "TensorFlow not installed. ML predictions will not be available."
        )
        logger.warning("Install with: pip install tensorflow scikit-learn")
    else:
        # Preload GRU models at startup (load all 16 models)
        if settings.preload_models:
            logger.info("=" * 60)
            logger.info("PRELOADING GRU MODELS AT STARTUP")
            logger.info("=" * 60)
            preload_gru_models()
            logger.info("=" * 60)
        else:
            logger.info("Model preloading disabled - models will be loaded on-demand")

    yield

    # Cleanup
    logger.info("Shutting down ML Prediction Service")
    await close_http_client()

    # Disconnect Redis cache
    if prediction_cache:
        await prediction_cache.disconnect()

    # Close ensemble predictor
    if ensemble_predictor:
        await ensemble_predictor.close()


# FastAPI app
app = FastAPI(
    title="ML Prediction Service",
    description="Machine learning-based price predictions for crypto assets (LSTM & GRU)",
    version="2.0.0",
    lifespan=lifespan,
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
        http_request_duration_seconds.labels(method=method, endpoint=path).observe(
            duration
        )
        http_requests_total.labels(
            method=method, endpoint=path, status=response.status_code
        ).inc()

        return response
    finally:
        # Decrement active requests
        http_requests_active.dec()


# === END PROMETHEUS MIDDLEWARE ===


# Prometheus metrics endpoint
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Health endpoints
@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return HealthResponse(status="healthy", service="ml-prediction-service")


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
    models_loaded = len(gru_predictors) > 0

    return ReadyResponse(
        ready=tensorflow_ready and market_data_ready,
        models_loaded=models_loaded,
        dependencies_available={
            "tensorflow": tensorflow_ready,
            "market_data_service": market_data_ready,
        },
    )


# === NEW ENDPOINT: /api/v1/models/loaded ===


@app.get("/api/v1/models/loaded", tags=["Model Management"])
async def get_loaded_models():
    """
    Get comprehensive information about all available and loaded models

    Returns:
        - Total available models on disk
        - Total loaded models in memory
        - List of available model symbols
        - List of loaded model symbols with details
        - Preloading statistics
        - Configuration status
    """
    # Discover available models from filesystem
    available_models = get_available_gru_models()

    # Get loaded models
    loaded_gru = []
    for key, predictor in gru_predictors.items():
        if predictor.model is not None:
            loaded_gru.append(
                {
                    "symbol": predictor.symbol,
                    "interval": f"{predictor.interval}m",
                    "version": predictor.model_version,
                    "last_trained": predictor.last_trained.isoformat()
                    if predictor.last_trained
                    else None,
                    "r2_score": predictor.training_stats.get("r2_score", 0.0),
                    "mae": predictor.training_stats.get("mae", 0.0),
                    "rmse": predictor.training_stats.get("rmse", 0.0),
                    "directional_accuracy": predictor.training_stats.get(
                        "directional_accuracy", 0.0
                    ),
                    "needs_retraining": predictor.needs_retraining(),
                }
            )

    # LSTM removed late 2025 — GRU replaced it.
    memory_estimate_mb = len(loaded_gru) * 1.2

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "total_available": len(available_models),
        "total_loaded": len(loaded_gru),
        "gru_loaded": len(loaded_gru),
        "available_models": available_models,
        "loaded_gru_models": loaded_gru,
        "preload_stats": preload_stats,
        "configuration": {
            "preload_enabled": settings.preload_models,
            "preload_priority_only": settings.preload_priority_only,
            "default_interval": settings.default_interval,
            "all_configured_symbols": ALL_GRU_SYMBOLS,
            "priority_symbols": PRIORITY_SYMBOLS,
            "models_dir": settings.models_dir,
        },
        "memory_estimate_mb": round(memory_estimate_mb, 2),
    }


@app.post("/api/v1/models/preload", tags=["Model Management"])
async def trigger_preload(
    symbols: List[str] = Query(
        None, description="Specific symbols to preload (optional, defaults to all)"
    ),
    force: bool = Query(False, description="Force reload even if already loaded"),
):
    """
    Manually trigger model preloading

    Use this to:
    - Load specific symbols on-demand
    - Reload models after retraining
    - Load models that failed during startup
    """
    if not TENSORFLOW_AVAILABLE:
        raise HTTPException(status_code=503, detail="TensorFlow not available")

    start_time = time.time()

    # Determine symbols to load
    if symbols:
        symbols_to_load = symbols
    else:
        symbols_to_load = get_available_gru_models()

    interval = settings.default_interval
    loaded = []
    failed = []

    for symbol in symbols_to_load:
        try:
            key = f"{symbol}_{interval}"

            # Skip if already loaded and not forcing
            if (
                not force
                and key in gru_predictors
                and gru_predictors[key].model is not None
            ):
                loaded.append(
                    {
                        "symbol": symbol,
                        "status": "already_loaded",
                        "version": gru_predictors[key].model_version,
                    }
                )
                continue

            # Remove from cache if forcing reload
            if force and key in gru_predictors:
                del gru_predictors[key]
                ml_models_loaded.labels(model_type="GRU").dec()

            # Load the model
            predictor = get_gru_predictor(symbol, interval)

            if predictor.model is not None:
                loaded.append(
                    {
                        "symbol": symbol,
                        "status": "loaded",
                        "version": predictor.model_version,
                        "r2_score": predictor.training_stats.get("r2_score", 0.0),
                    }
                )
            else:
                failed.append(
                    {
                        "symbol": symbol,
                        "reason": "Model file not found or failed to load",
                    }
                )

        except Exception as e:
            failed.append({"symbol": symbol, "reason": str(e)})

    duration = time.time() - start_time

    return {
        "success": len(failed) == 0,
        "duration_seconds": round(duration, 2),
        "total_attempted": len(symbols_to_load),
        "total_loaded": len([l for l in loaded if l["status"] == "loaded"]),
        "already_loaded": len([l for l in loaded if l["status"] == "already_loaded"]),
        "failed": len(failed),
        "loaded": loaded,
        "failed_details": failed,
    }


# Prediction endpoints
@app.get(
    "/api/v1/predict/price/{symbol}",
    response_model=PricePrediction,
    tags=["Predictions"],
)
async def predict_price(
    symbol: str = FastAPIPath(..., description="Trading pair (e.g., BTCUSDT)"),
    interval: str = Query("60", description="Timeframe in minutes"),
    model_type: str = Query("GRU", description="Model type: GRU (default) or LSTM"),
    use_cache: bool = Query(True, description="Use cached predictions if available"),
):
    """
    Get price prediction for a symbol using specified model type

    Returns predicted prices for the next N periods (configured in settings)

    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        interval: Timeframe in minutes (default: 60)
        model_type: Either 'LSTM' or 'GRU' (default: LSTM)
        use_cache: Whether to use cached predictions (default: True)
    """
    if not TENSORFLOW_AVAILABLE:
        raise HTTPException(status_code=503, detail="TensorFlow not available")

    # Start prediction timer
    start_time = datetime.utcnow()

    try:
        # Check cache first (if enabled)
        if use_cache and prediction_cache and prediction_cache.is_connected:
            cached_prediction = await prediction_cache.get_prediction(
                symbol, interval, model_type
            )

            if cached_prediction:
                logger.info(f"Cache HIT for {symbol} {interval}m {model_type}")

                # Remove cache metadata before returning
                cached_prediction.pop("cached_at", None)
                cached_prediction.pop("ttl_seconds", None)

                # Record cache hit metric
                duration = (datetime.utcnow() - start_time).total_seconds()
                ml_prediction_duration_seconds.labels(
                    symbol=symbol, model_type=model_type
                ).observe(duration)
                ml_predictions_total.labels(symbol=symbol, model_type=model_type).inc()

                return PricePrediction(**cached_prediction)

        # Cache miss or cache disabled - run prediction
        logger.info(
            f"Cache MISS for {symbol} {interval}m {model_type} - running inference"
        )

        # Get predictor based on model type
        predictor = get_predictor(symbol, interval, model_type)

        # Check if model exists and is trained
        if predictor.model is None:
            raise HTTPException(
                status_code=404,
                detail=f"No trained {model_type} model found for {symbol} {interval}m. Please train the model first.",
            )

        # Check if model needs retraining
        if predictor.needs_retraining():
            logger.warning(
                f"{model_type} model for {symbol} {interval}m needs retraining (last trained: {predictor.last_trained})"
            )

        # Fetch recent data
        recent_data = await fetch_historical_data(
            symbol, interval, limit=settings.sequence_length + 50
        )

        # Make prediction
        prediction = await predictor.predict(recent_data)

        # Store in cache (if enabled)
        if use_cache and prediction_cache and prediction_cache.is_connected:
            # Convert to dict for caching
            prediction_dict = prediction.model_dump()
            await prediction_cache.set_prediction(
                symbol, interval, model_type, prediction_dict
            )

        # Record metrics
        duration = (datetime.utcnow() - start_time).total_seconds()
        ml_prediction_duration_seconds.labels(
            symbol=symbol, model_type=model_type
        ).observe(duration)
        ml_predictions_total.labels(symbol=symbol, model_type=model_type).inc()
        ml_prediction_confidence.labels(symbol=symbol, model_type=model_type).observe(
            prediction.average_confidence
        )

        return prediction

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Prediction error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")


@app.get(
    "/api/v1/predict/trend/{symbol}",
    response_model=TrendPrediction,
    tags=["Predictions"],
)
async def predict_trend(
    symbol: str = FastAPIPath(..., description="Trading pair"),
    interval: str = Query("60", description="Timeframe in minutes"),
    model_type: str = Query("GRU", description="Model type: GRU (default) or LSTM"),
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
        price_change_pct = (
            (last_pred - price_pred.current_price) / price_pred.current_price
        ) * 100

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
            prediction_timestamp=datetime.utcnow(),
        )

    except Exception as e:
        logger.error(f"Trend prediction error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Trend prediction failed: {str(e)}"
        )


@app.get(
    "/api/v1/predict/volatility/{symbol}",
    response_model=VolatilityPrediction,
    tags=["Predictions"],
)
async def predict_volatility(
    symbol: str = FastAPIPath(..., description="Trading pair"),
    interval: str = Query("60", description="Timeframe in minutes"),
):
    """
    Predict future volatility

    Helps with position sizing and risk management
    """
    try:
        # Fetch historical data
        df = await fetch_historical_data(symbol, interval, limit=100)

        # Calculate current volatility (using rolling std of returns)
        df["returns"] = df["close"].pct_change()
        current_volatility = float(
            df["returns"].rolling(window=20).std().iloc[-1] * 100
        )

        # Simple volatility forecast (in production, would use GARCH or similar)
        # For now, use recent trend
        recent_vol = df["returns"].rolling(window=5).std().iloc[-1] * 100
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
            recommended_position_size_multiplier=size_multiplier,
        )

    except Exception as e:
        logger.error(f"Volatility prediction error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Volatility prediction failed: {str(e)}"
        )


@app.get(
    "/api/v1/predict/ensemble/{symbol}",
    response_model=EnsembleSignal,
    tags=["Predictions"],
)
async def predict_ensemble(
    symbol: str = FastAPIPath(..., description="Trading pair (e.g., BTCUSDT)"),
    interval: str = Query("60", description="Timeframe in minutes"),
    ml_model: str = Query("GRU", description="ML model type: GRU (default) or LSTM"),
):
    """
    Get ensemble prediction combining multiple signal sources

    **Combines:**
    - **Traditional TA (40%)** - RSI, MACD, Bollinger Bands from technical-analysis service
    - **ML Predictions (30%)** - LSTM/GRU price predictions from this service
    - **Sentiment Analysis (15%)** - News/social media sentiment (placeholder - returns NEUTRAL)
    - **Multi-Timeframe (15%)** - Trend alignment across 15m, 1h, 4h, 1d timeframes

    **Signal Direction:**
    - BUY: Weighted score > 0.3
    - SELL: Weighted score < -0.3
    - NEUTRAL: Weighted score between -0.3 and 0.3

    **Returns:**
    - Final trading signal with confidence and strength
    - Individual component signals with their weights
    - Buy/sell probabilities
    - Metadata about components available and used

    **Example:**
    ```
    GET /api/v1/predict/ensemble/BTCUSDT?interval=60&ml_model=LSTM
    ```
    """
    try:
        if not ensemble_predictor:
            raise HTTPException(
                status_code=503,
                detail="Ensemble predictor not initialized. Please restart the service.",
            )

        start_time = datetime.utcnow()

        # Generate ensemble signal
        signal = await ensemble_predictor.predict(
            symbol=symbol, interval=interval, ml_model=ml_model
        )

        # Track metrics
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info(
            f"Ensemble prediction for {symbol} {interval}m: {signal.direction} "
            f"(confidence: {signal.confidence:.2f}, strength: {signal.strength:.2f}) "
            f"in {duration:.2f}s"
        )

        return signal

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ensemble prediction error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Ensemble prediction failed: {str(e)}"
        )


@app.get("/api/v1/predict/enhanced/{symbol}", tags=["Predictions"])
async def enhanced_ml_prediction(
    symbol: str = FastAPIPath(..., description="Trading pair (e.g., BTCUSDT)"),
    interval: str = Query("60", description="Candlestick interval in minutes"),
    lookback_days: int = Query(
        default=90, description="Days of historical data to use"
    ),
    model_type: str = Query(
        default="ENSEMBLE", description="Model type: ENSEMBLE, LSTM, RF, GB, LR"
    ),
    confidence_threshold: float = Query(
        default=0.6, description="Minimum confidence for signal"
    ),
):
    """
    Enhanced ML prediction with ensemble approach targeting 5-10% win rate improvement

    Features:
    - Ensemble of 4+ models for robust predictions
    - Comprehensive technical features
    - Consensus-based signal generation
    - Confidence-weighted risk management
    - Market regime awareness
    - Volatility clustering detection
    """

    try:
        # Fetch historical data
        logger.info(f"Fetching {lookback_days} days of data for {symbol}")
        df = await fetch_historical_data(
            symbol, interval, limit=int((lookback_days * 24 * 60) / int(interval))
        )

        if len(df) < 50:
            return {
                "symbol": symbol,
                "interval": interval,
                "signal": "HOLD",
                "confidence": 0.0,
                "reason": "Insufficient historical data for ML prediction",
                "timestamp": datetime.now().isoformat(),
            }

        # Initialize enhanced ensemble predictor
        enhanced_predictor = EnhancedEnsemblePredictor()

        # Check if model exists and load it, otherwise train
        model_path = f"models/enhanced_ensemble_{symbol}_{interval}.pkl"
        if enhanced_predictor.load_model(model_path):
            logger.info(f"Loaded existing model for {symbol} {interval}")
        else:
            logger.info(f"Training new model for {symbol} {interval}")
            try:
                training_results = enhanced_predictor.train_models(df)
                logger.info(f"Training completed. Results: {training_results}")
            except Exception as e:
                logger.error(f"Training failed: {e}")
                return {
                    "symbol": symbol,
                    "interval": interval,
                    "signal": "HOLD",
                    "confidence": 0.0,
                    "reason": f"Model training failed: {str(e)}",
                    "timestamp": datetime.now().isoformat(),
                }

        # Make prediction
        prediction_result = enhanced_predictor.predict(df)

        # Apply confidence threshold
        if prediction_result["confidence"] < confidence_threshold:
            return {
                "symbol": symbol,
                "interval": interval,
                "signal": "HOLD",
                "confidence": prediction_result["confidence"],
                "reason": f"Confidence below threshold ({confidence_threshold})",
                "consensus": prediction_result["consensus"],
                "individual_predictions": prediction_result["individual_predictions"],
                "timestamp": prediction_result["timestamp"],
            }

        # Calculate enhanced metrics for win rate improvement
        enhanced_metrics = await calculate_enhanced_metrics(
            df, prediction_result, symbol, interval
        )

        return {
            "symbol": symbol,
            "interval": interval,
            "signal": prediction_result["signal"],
            "confidence": prediction_result["confidence"],
            "consensus": prediction_result["consensus"],
            "individual_predictions": prediction_result["individual_predictions"],
            "enhanced_metrics": enhanced_metrics,
            "model_accuracy": prediction_result["model_accuracy"],
            "timestamp": prediction_result["timestamp"],
            "target_win_rate_improvement": "5-10%",
        }

    except Exception as e:
        logger.error(f"Enhanced ML prediction failed: {e}", exc_info=True)
        return {
            "symbol": symbol,
            "interval": interval,
            "signal": "HOLD",
            "confidence": 0.0,
            "reason": f"Prediction error: {str(e)}",
            "timestamp": datetime.now().isoformat(),
        }


async def calculate_enhanced_metrics(
    df: pd.DataFrame, prediction_result: Dict, symbol: str, interval: str
) -> Dict[str, Any]:
    """
    Calculate enhanced metrics that contribute to win rate improvement
    """
    try:
        # Calculate market regime indicators
        market_regime = await classify_market_regime(df)

        # Calculate volatility clustering (GARCH-like features)
        volatility_regime = await calculate_volatility_regime(df)

        # Calculate trend strength
        trend_strength = await calculate_trend_strength(df)

        # Calculate momentum divergence
        momentum_divergence = await calculate_momentum_divergence(df)

        # Calculate support/resistance quality
        sr_quality = await calculate_support_resistance_quality(df)

        # Combine all factors for enhanced confidence
        enhanced_confidence = (
            prediction_result["confidence"] * 0.4  # Original ML confidence
            + (1 - abs(volatility_regime - 0.5)) * 0.2  # Volatility stability
            + min(trend_strength, 0.8) * 0.2  # Trend strength (capped)
            + (1 - abs(momentum_divergence)) * 0.1  # Momentum quality
            + sr_quality * 0.1  # Support/resistance quality
        )

        # Adjust signal based on market conditions
        adjusted_signal = adjust_signal_for_conditions(
            prediction_result["signal"],
            market_regime,
            volatility_regime,
            trend_strength,
        )

        return {
            "market_regime": market_regime,
            "volatility_regime": volatility_regime,
            "trend_strength": trend_strength,
            "momentum_divergence": momentum_divergence,
            "support_resistance_quality": sr_quality,
            "enhanced_confidence": min(enhanced_confidence, 1.0),
            "adjusted_signal": adjusted_signal,
            "win_rate_potential": estimate_win_rate_potential(
                prediction_result["confidence"],
                market_regime,
                volatility_regime,
                trend_strength,
            ),
        }

    except Exception as e:
        logger.error(f"Enhanced metrics calculation failed: {e}")
        return {
            "market_regime": "UNKNOWN",
            "volatility_regime": 0.5,
            "trend_strength": 0.5,
            "momentum_divergence": 0.0,
            "support_resistance_quality": 0.5,
            "enhanced_confidence": prediction_result["confidence"],
            "adjusted_signal": prediction_result["signal"],
            "win_rate_potential": 0.5,
        }


async def classify_market_regime(df: pd.DataFrame) -> str:
    """Classify current market regime for better prediction accuracy"""
    if len(df) < 20:
        return "INSUFFICIENT_DATA"

    # Calculate ADX for trend strength
    adx = df["adx"].iloc[-1] if "adx" in df.columns else 25

    # Calculate RSI for overbought/oversold
    rsi = df["rsi"].iloc[-1] if "rsi" in df.columns else 50

    # Calculate volatility
    volatility = df["volatility"].iloc[-1] if "volatility" in df.columns else 0.02

    if adx > 30:
        if rsi > 70:
            return "TRENDING_BULLISH"
        elif rsi < 30:
            return "TRENDING_BEARISH"
        else:
            return "TRENDING_NEUTRAL"
    elif adx < 20:
        if volatility > 0.03:
            return "CHOPPY_VOLATILE"
        else:
            return "CHOPPY_STABLE"
    else:
        return "TRANSITIONAL"


async def calculate_volatility_regime(df: pd.DataFrame) -> float:
    """Calculate volatility regime (0.0-1.0 scale)"""
    if len(df) < 30:
        return 0.5

    # Calculate rolling volatility and compare to historical average
    current_vol = df["volatility"].iloc[-1]
    avg_vol = df["volatility"].rolling(30).mean().iloc[-1]

    # Normalize to 0-1 scale (0 = very low volatility, 1 = very high)
    if avg_vol > 0:
        return min(max(current_vol / avg_vol, 0.0), 1.0)
    return 0.5


async def calculate_trend_strength(df: pd.DataFrame) -> float:
    """Calculate trend strength (0.0-1.0 scale)"""
    if len(df) < 20:
        return 0.5

    # Use EMA convergence/divergence
    ema_fast = (
        df["ema_fast"].iloc[-1] if "ema_fast" in df.columns else df["close"].iloc[-1]
    )
    ema_slow = (
        df["ema_slow"].iloc[-1] if "ema_slow" in df.columns else df["close"].iloc[-1]
    )

    # Calculate trend strength based on EMA separation
    trend_sep = abs(ema_fast - ema_slow) / df["close"].iloc[-1]

    # Also consider direction consistency
    recent_directions = []
    for i in range(1, min(5, len(df))):
        if i < len(df):
            direction = 1 if df["close"].iloc[-i] > df["close"].iloc[-i - 1] else 0
            recent_directions.append(direction)

    direction_consistency = (
        sum(recent_directions) / len(recent_directions) if recent_directions else 0.5
    )

    return min((trend_sep * 2 + direction_consistency) / 2, 1.0)


async def calculate_momentum_divergence(df: pd.DataFrame) -> float:
    """Calculate momentum divergence (-1.0 to 1.0 scale)"""
    if len(df) < 20:
        return 0.0

    # Calculate price momentum vs indicator momentum
    price_mom = df["close"].pct_change(5).iloc[-1]
    rsi_mom = df["rsi"].pct_change(5).iloc[-1] if "rsi" in df.columns else 0.0

    # Divergence: opposite signs indicate potential reversal
    if price_mom * rsi_mom < 0:  # Opposite directions
        return (
            -1.0 if price_mom > 0 else 1.0
        )  # Negative if bullish divergence, positive if bearish
    else:
        return 0.0  # No significant divergence


async def calculate_support_resistance_quality(df: pd.DataFrame) -> float:
    """Calculate support/resistance quality (0.0-1.0 scale)"""
    if len(df) < 50:
        return 0.5

    # Look for recent price levels where price bounced
    recent_prices = df["close"].tail(20)
    high_recent = recent_prices.max()
    low_recent = recent_prices.min()

    # Calculate how often price tested these levels
    price_range = high_recent - low_recent
    if price_range == 0:
        return 0.5

    # Quality based on how much of the range has been explored recently
    exploration_ratio = (recent_prices.std() * 2) / price_range
    return min(exploration_ratio, 1.0)


def adjust_signal_for_conditions(
    original_signal: str,
    market_regime: str,
    volatility_regime: float,
    trend_strength: float,
) -> str:
    """Adjust signal based on market conditions for better win rate"""

    # In choppy/volatile markets, be more conservative
    if "CHOPPY" in market_regime:
        if volatility_regime > 0.7:  # High volatility
            return "HOLD"  # Too risky

    # In trending markets with strong trends, increase confidence
    if "TRENDING" in market_regime and trend_strength > 0.7:
        return original_signal  # Keep original signal

    # In uncertain regimes, be more conservative
    if market_regime in ["TRANSITIONAL", "INSUFFICIENT_DATA"]:
        return "HOLD"

    return original_signal


def estimate_win_rate_potential(
    confidence: float,
    market_regime: str,
    volatility_regime: float,
    trend_strength: float,
) -> float:
    """Estimate potential win rate improvement"""
    base_win_rate = 0.5  # Random guessing

    # Confidence contribution
    confidence_bonus = (confidence - 0.5) * 0.3  # Up to 15% improvement from confidence

    # Market regime bonus
    regime_bonus = 0.0
    if "TRENDING" in market_regime and trend_strength > 0.6:
        regime_bonus = 0.1  # 10% bonus in trending markets
    elif "CHOPPY" in market_regime:
        regime_bonus = -0.05  # Small penalty in choppy markets

    # Volatility adjustment
    vol_bonus = 0.0
    if 0.3 <= volatility_regime <= 0.7:  # Moderate volatility is ideal
        vol_bonus = 0.05
    elif volatility_regime > 0.8:  # Too volatile
        vol_bonus = -0.05

    estimated_win_rate = base_win_rate + confidence_bonus + regime_bonus + vol_bonus
    return max(0.4, min(estimated_win_rate, 0.9))  # Clamp between 40-90%


# Model management endpoints
@app.get("/api/v1/models/{symbol}", response_model=ModelInfo, tags=["Model Management"])
async def get_model_info(
    symbol: str = FastAPIPath(..., description="Trading pair"),
    interval: str = Query("60", description="Timeframe in minutes"),
    model_type: str = Query("GRU", description="Model type: GRU (default) or LSTM"),
):
    """Get information about a trained model"""
    try:
        predictor = get_predictor(symbol, interval, model_type)

        if predictor.model is None:
            raise HTTPException(
                status_code=404,
                detail=f"No {model_type} model found for {symbol} {interval}m",
            )

        return ModelInfo(
            model_type=model_type.upper(),
            model_version=predictor.model_version or "unknown",
            symbols_supported=[symbol],
            intervals_supported=[f"{interval}m"],
            last_trained=predictor.last_trained or datetime.utcnow(),
            training_samples=predictor.training_stats.get("train_samples", 0),
            training_duration_seconds=0.0,  # Not tracked in metadata currently
            validation_accuracy=predictor.training_stats.get("r2_score", 0.0),
            validation_mae=predictor.training_stats.get("mae", 0.0),
            validation_rmse=predictor.training_stats.get("rmse", 0.0),
            validation_r2_score=predictor.training_stats.get("r2_score", 0.0),
            top_features=[],
            status="READY" if predictor.model else "UNTRAINED",
            needs_retraining=predictor.needs_retraining(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting model info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/api/v1/models/train", response_model=TrainingResponse, tags=["Model Management"]
)
async def train_model(request: TrainingRequest, background_tasks: BackgroundTasks):
    """LSTM training was removed late 2025 — GRU replaced it."""
    raise HTTPException(
        status_code=410,
        detail="LSTM training removed; use POST /api/v1/models/train-gru/{symbol}",
    )


@app.post(
    "/api/v1/models/train-gru/{symbol}",
    response_model=TrainingResponse,
    tags=["Model Management"],
)
async def train_gru_model(
    symbol: str = FastAPIPath(..., description="Trading pair"),
    interval: str = Query("60", description="Timeframe in minutes"),
    lookback_days: int = Query(
        90, ge=30, le=365, description="Days of historical data"
    ),
    force_retrain: bool = Query(
        False, description="Force retrain even if recent model exists"
    ),
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
                ml_training_total.labels(
                    symbol=symbol, model_type="GRU", status="skipped"
                ).inc()
                return TrainingResponse(
                    success=False,
                    message=f"GRU model already trained recently ({predictor.last_trained}). Use force_retrain=true to retrain.",
                    model_version=predictor.model_version or "unknown",
                    training_duration_seconds=0.0,
                )

        # Fetch historical data
        logger.info(f"Fetching {lookback_days} days of data for GRU training")
        limit = int(
            (lookback_days * 24 * 60) / int(interval)
        )  # Convert days to candles
        # Cap at 10000 (market-data service maximum)
        limit = min(limit, 10000)
        logger.info(f"Calculated limit: {limit} candles (capped at 10000)")
        historical_data = await fetch_historical_data(symbol, interval, limit=limit)

        # Train GRU model
        model_info = await predictor.train(historical_data)
        training_duration = (datetime.utcnow() - start_time).total_seconds()

        logger.info(f"GRU training completed in {training_duration:.2f}s")

        # Record metrics
        ml_training_duration_seconds.labels(symbol=symbol, model_type="GRU").observe(
            training_duration
        )
        ml_training_total.labels(
            symbol=symbol, model_type="GRU", status="success"
        ).inc()

        return TrainingResponse(
            success=True,
            message=f"GRU model trained successfully with {len(historical_data)} samples",
            model_version=model_info.model_version,
            training_duration_seconds=training_duration,
            model_info=model_info,
        )

    except Exception as e:
        logger.error(f"GRU training error: {e}", exc_info=True)
        ml_training_total.labels(symbol=symbol, model_type="GRU", status="failed").inc()
        return TrainingResponse(
            success=False,
            message="GRU training failed",
            model_version="error",
            training_duration_seconds=0.0,
            error=str(e),
        )


@app.get("/api/v1/models/compare/{symbol}", tags=["Model Management"])
async def compare_models(
    symbol: str = FastAPIPath(..., description="Trading pair"),
    interval: str = Query("60", description="Timeframe in minutes"),
):
    """
    Compare LSTM vs GRU model performance

    Comparison metrics:
    - Prediction accuracy (RMSE, MAE, R^2, MAPE)
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
            recent_data = await fetch_historical_data(
                symbol, interval, limit=settings.sequence_length + 50
            )
            prediction_comparison = await comparator.compare_predictions(recent_data)

        # Get recommendation
        recommendation = comparator.get_recommendation()

        return {
            "symbol": symbol,
            "interval": f"{interval}m",
            "timestamp": datetime.utcnow().isoformat(),
            "training_comparison": training_comparison,
            "prediction_comparison": prediction_comparison,
            "recommendation": recommendation,
            "summary": {
                "lstm_available": comparator.lstm_predictor.model is not None,
                "gru_available": comparator.gru_predictor.model is not None,
                "winner": training_comparison.get("winner", {}).get("overall", "NONE"),
            },
        }

    except Exception as e:
        logger.error(f"Model comparison error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")


# Utility endpoints
@app.get("/api/v1/models", tags=["Model Management"])
async def list_models():
    """List all loaded GRU models. LSTM removed late 2025."""
    models = []

    for key, predictor in gru_predictors.items():
        if predictor.model is not None:
            models.append(
                {
                    "model_type": "GRU",
                    "symbol": predictor.symbol,
                    "interval": f"{predictor.interval}m",
                    "version": predictor.model_version,
                    "last_trained": predictor.last_trained.isoformat()
                    if predictor.last_trained
                    else None,
                    "needs_retraining": predictor.needs_retraining(),
                }
            )

    return {
        "total_models": len(models),
        "gru_count": len(models),
        "models": models,
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
                "best_for": "Long-term dependencies, complex patterns",
            },
            {
                "type": "GRU",
                "name": "Gated Recurrent Unit",
                "description": "Efficient RNN variant, faster than LSTM",
                "parameters": "~2/3 LSTM parameters",
                "training_speed": "25-30% faster than LSTM",
                "best_for": "Shorter sequences, faster inference, resource constraints",
            },
        ],
        "default": "GRU",
        "available_gru_models": get_available_gru_models(),
        "configured_symbols": ALL_GRU_SYMBOLS,
    }


# Cache management endpoints
@app.get("/api/v1/cache/stats", tags=["Cache Management"])
async def get_cache_stats():
    """
    Get Redis cache statistics

    Returns metrics like:
    - Connection status
    - Total cached predictions
    - Memory usage
    - TTL configuration
    """
    if not prediction_cache:
        return {"enabled": False, "message": "Redis caching not initialized"}

    return await prediction_cache.get_cache_stats()


@app.delete("/api/v1/cache/clear", tags=["Cache Management"])
async def clear_cache():
    """
    Clear all cached predictions

    Use when:
    - Models are retrained
    - Cache is stale
    - Testing fresh predictions
    """
    if not prediction_cache or not prediction_cache.is_connected:
        return {
            "success": False,
            "message": "Redis cache not available",
            "cleared_count": 0,
        }

    cleared_count = await prediction_cache.clear_all()

    return {
        "success": True,
        "message": f"Cleared {cleared_count} cached predictions",
        "cleared_count": cleared_count,
    }


@app.delete("/api/v1/cache/{symbol}", tags=["Cache Management"])
async def invalidate_cache(
    symbol: str = FastAPIPath(..., description="Trading pair"),
    interval: str = Query("60", description="Timeframe in minutes"),
    model_type: str = Query("GRU", description="Model type: GRU (default) or LSTM"),
):
    """
    Invalidate cache for a specific symbol/interval/model

    Use when:
    - Model is retrained for specific symbol
    - Want fresh prediction for specific pair
    """
    if not prediction_cache or not prediction_cache.is_connected:
        return {"success": False, "message": "Redis cache not available"}

    success = await prediction_cache.invalidate_prediction(symbol, interval, model_type)

    return {
        "success": success,
        "message": f"Cache invalidated for {symbol} {interval}m {model_type}"
        if success
        else "No cache found to invalidate",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.service_port)
