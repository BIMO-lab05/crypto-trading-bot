# Prometheus Instrumentation Guide for Phase 3 Services

This guide explains how to add Prometheus metrics to the ML Prediction, Sentiment Analysis, and Risk Metrics services.

## Table of Contents
1. [Installation](#installation)
2. [Basic Setup](#basic-setup)
3. [ML Prediction Service Metrics](#ml-prediction-service-metrics)
4. [Sentiment Analysis Service Metrics](#sentiment-analysis-service-metrics)
5. [Risk Metrics Service Metrics](#risk-metrics-service-metrics)
6. [Best Practices](#best-practices)

---

## Installation

Add the Prometheus client library to each service's `requirements.txt`:

```bash
# Add to requirements.txt
prometheus-client==0.19.0
prometheus-fastapi-instrumentator==6.1.0
```

Install in each service:

```bash
# For ML Prediction Service
cd /mnt/d/Bimo_max/crypto-trading-bot/services/ml-prediction-service
echo "prometheus-client==0.19.0" >> requirements.txt
echo "prometheus-fastapi-instrumentator==6.1.0" >> requirements.txt
pip install prometheus-client prometheus-fastapi-instrumentator

# For Sentiment Analysis Service
cd /mnt/d/Bimo_max/crypto-trading-bot/services/sentiment-analysis-service
echo "prometheus-client==0.19.0" >> requirements.txt
echo "prometheus-fastapi-instrumentator==6.1.0" >> requirements.txt
pip install prometheus-client prometheus-fastapi-instrumentator

# For Risk Metrics Service
cd /mnt/d/Bimo_max/crypto-trading-bot/services/risk-metrics-service
echo "prometheus-client==0.19.0" >> requirements.txt
echo "prometheus-fastapi-instrumentator==6.1.0" >> requirements.txt
pip install prometheus-client prometheus-fastapi-instrumentator
```

---

## Basic Setup

### Step 1: Add Prometheus Instrumentation to FastAPI App

Create a new file in each service: `app/monitoring/metrics.py`

```python
# app/monitoring/metrics.py
"""
Prometheus metrics configuration and custom metrics for service monitoring.
Provides automatic HTTP request metrics and service-specific business metrics.
"""

from prometheus_client import Counter, Histogram, Gauge, Info
from prometheus_fastapi_instrumentator import Instrumentator
from fastapi import FastAPI
import logging

logger = logging.getLogger(__name__)

# =================================================================
# PROMETHEUS INSTRUMENTATOR SETUP
# =================================================================

def setup_metrics(app: FastAPI, service_name: str, service_version: str = "1.0.0"):
    """
    Setup Prometheus metrics for FastAPI application.

    Args:
        app: FastAPI application instance
        service_name: Name of the service (e.g., "ml-prediction")
        service_version: Version of the service

    Returns:
        Instrumentator instance for further customization
    """
    # Create instrumentator with custom configuration
    instrumentator = Instrumentator(
        should_group_status_codes=True,  # Group 2xx, 3xx, 4xx, 5xx
        should_ignore_untemplated=True,  # Ignore non-matched routes
        should_respect_env_var=True,     # Respect ENABLE_METRICS env var
        should_instrument_requests_inprogress=True,  # Track concurrent requests
        excluded_handlers=["/metrics", "/health", "/ready"],  # Don't track these
        env_var_name="ENABLE_METRICS",
        inprogress_name="http_requests_inprogress",
        inprogress_labels=True,
    )

    # Instrument the app with default metrics
    instrumentator.instrument(app)

    # Expose metrics endpoint at /metrics
    instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)

    # Add service info metric
    service_info = Info(f'{service_name}_service_info', 'Service information')
    service_info.info({
        'version': service_version,
        'service': service_name,
        'phase': '3'
    })

    logger.info(f"Prometheus metrics enabled for {service_name} at /metrics")

    return instrumentator

# =================================================================
# COMMON METRICS (Used by all services)
# =================================================================

# HTTP request latency histogram
http_request_duration = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint', 'status'],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

# Total error counter
errors_total = Counter(
    'service_errors_total',
    'Total number of errors',
    ['service', 'error_type']
)

# Active connections gauge
active_connections = Gauge(
    'active_connections',
    'Number of active connections',
    ['service']
)
```

### Step 2: Update main.py to Enable Metrics

```python
# app/main.py
from fastapi import FastAPI
from app.monitoring.metrics import setup_metrics

# Create FastAPI app
app = FastAPI(title="Service Name", version="1.0.0")

# Setup Prometheus metrics
setup_metrics(app, service_name="ml-prediction", service_version="1.0.0")

# ... rest of your FastAPI routes
```

---

## ML Prediction Service Metrics

Create service-specific metrics in `app/monitoring/ml_metrics.py`:

```python
# services/ml-prediction-service/app/monitoring/ml_metrics.py
"""
Custom Prometheus metrics for ML Prediction Service.
Tracks model performance, prediction accuracy, and inference time.
"""

from prometheus_client import Counter, Histogram, Gauge, Summary

# =================================================================
# ML PREDICTION METRICS
# =================================================================

# Prediction request counter
ml_prediction_requests = Counter(
    'ml_prediction_requests_total',
    'Total number of ML prediction requests',
    ['symbol', 'model_type']
)

# Prediction accuracy gauge (updated after validation)
ml_prediction_accuracy = Gauge(
    'ml_prediction_accuracy',
    'Current ML prediction accuracy percentage',
    ['symbol', 'model_type']
)

# Prediction confidence gauge
ml_prediction_confidence = Gauge(
    'ml_prediction_confidence',
    'Confidence score of ML predictions (0-1)',
    ['symbol', 'model_type']
)

# Model inference time histogram
ml_model_inference_seconds = Histogram(
    'ml_model_inference_seconds',
    'Time taken for model inference',
    ['model_type'],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0)
)

# Cache hit/miss counters
ml_cache_hits = Counter(
    'ml_cache_hits_total',
    'Number of cache hits for ML predictions',
    ['symbol']
)

ml_cache_misses = Counter(
    'ml_cache_misses_total',
    'Number of cache misses for ML predictions',
    ['symbol']
)

# Prediction correctness (tracked after market moves)
ml_prediction_correct = Counter(
    'ml_prediction_correct_total',
    'Number of correct predictions',
    ['symbol', 'direction']
)

ml_prediction_incorrect = Counter(
    'ml_prediction_incorrect_total',
    'Number of incorrect predictions',
    ['symbol', 'direction']
)

# Model training metrics
ml_model_training_time = Histogram(
    'ml_model_training_seconds',
    'Time taken to train the model',
    ['model_type'],
    buckets=(10, 30, 60, 120, 300, 600, 1800, 3600)
)

ml_model_last_training = Gauge(
    'ml_model_last_training_timestamp',
    'Timestamp of last model training',
    ['model_type']
)

# Error counter
ml_prediction_errors = Counter(
    'ml_prediction_errors_total',
    'Total ML prediction errors',
    ['error_type']
)

# =================================================================
# USAGE EXAMPLE
# =================================================================

"""
Example usage in your prediction endpoint:

from app.monitoring.ml_metrics import (
    ml_prediction_requests,
    ml_prediction_confidence,
    ml_model_inference_seconds,
    ml_cache_hits,
    ml_cache_misses
)
import time

@app.post("/predict")
async def predict(request: PredictionRequest):
    # Increment request counter
    ml_prediction_requests.labels(
        symbol=request.symbol,
        model_type="lstm"
    ).inc()

    # Check cache
    cached_result = cache.get(request.symbol)
    if cached_result:
        ml_cache_hits.labels(symbol=request.symbol).inc()
        return cached_result

    ml_cache_misses.labels(symbol=request.symbol).inc()

    # Measure inference time
    start_time = time.time()
    with ml_model_inference_seconds.labels(model_type="lstm").time():
        prediction = model.predict(request.data)

    # Record confidence
    ml_prediction_confidence.labels(
        symbol=request.symbol,
        model_type="lstm"
    ).set(prediction.confidence)

    return prediction
"""
```

---

## Sentiment Analysis Service Metrics

Create service-specific metrics in `app/monitoring/sentiment_metrics.py`:

```python
# services/sentiment-analysis-service/app/monitoring/sentiment_metrics.py
"""
Custom Prometheus metrics for Sentiment Analysis Service.
Tracks sentiment scores, news fetching, and API performance.
"""

from prometheus_client import Counter, Histogram, Gauge, Summary

# =================================================================
# SENTIMENT ANALYSIS METRICS
# =================================================================

# Sentiment request counter
sentiment_analysis_requests = Counter(
    'sentiment_analysis_requests_total',
    'Total number of sentiment analysis requests',
    ['symbol', 'source']  # source: news, twitter, reddit, etc.
)

# Current sentiment score gauge
sentiment_score = Gauge(
    'sentiment_score',
    'Current sentiment score (-1 to 1)',
    ['symbol', 'source']
)

# News fetch success/failure counters
sentiment_news_fetch_success = Counter(
    'sentiment_news_fetch_success_total',
    'Successful news article fetches',
    ['source']
)

sentiment_news_fetch_failure = Counter(
    'sentiment_news_fetch_failure_total',
    'Failed news article fetches',
    ['source', 'error_type']
)

# News articles processed
sentiment_news_articles_processed = Counter(
    'sentiment_news_articles_processed_total',
    'Total news articles processed',
    ['source']
)

# Sentiment API latency (external APIs like NewsAPI, Twitter)
sentiment_api_latency = Histogram(
    'sentiment_api_latency_seconds',
    'External API call latency',
    ['api_name'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
)

# Sentiment calculation latency (internal processing)
sentiment_calculation_latency = Histogram(
    'sentiment_calculation_latency_seconds',
    'Time to calculate sentiment from text',
    ['method'],  # method: lexicon, transformer, hybrid
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0)
)

# Sentiment distribution gauge (percentage of bearish/neutral/bullish)
sentiment_distribution_bearish = Gauge(
    'sentiment_distribution_bearish',
    'Percentage of bearish sentiment',
    ['symbol']
)

sentiment_distribution_neutral = Gauge(
    'sentiment_distribution_neutral',
    'Percentage of neutral sentiment',
    ['symbol']
)

sentiment_distribution_bullish = Gauge(
    'sentiment_distribution_bullish',
    'Percentage of bullish sentiment',
    ['symbol']
)

# Error counter
sentiment_analysis_errors = Counter(
    'sentiment_analysis_errors_total',
    'Total sentiment analysis errors',
    ['error_type']
)

# Rate limit tracking
sentiment_api_rate_limit_remaining = Gauge(
    'sentiment_api_rate_limit_remaining',
    'Remaining API calls before rate limit',
    ['api_name']
)

# =================================================================
# USAGE EXAMPLE
# =================================================================

"""
Example usage:

from app.monitoring.sentiment_metrics import (
    sentiment_analysis_requests,
    sentiment_score,
    sentiment_news_fetch_success,
    sentiment_api_latency
)

@app.get("/sentiment/{symbol}")
async def get_sentiment(symbol: str):
    sentiment_analysis_requests.labels(
        symbol=symbol,
        source="news"
    ).inc()

    # Fetch news with latency tracking
    with sentiment_api_latency.labels(api_name="newsapi").time():
        news_data = await fetch_news(symbol)

    if news_data:
        sentiment_news_fetch_success.labels(source="newsapi").inc()

    # Calculate and record sentiment
    score = calculate_sentiment(news_data)
    sentiment_score.labels(symbol=symbol, source="news").set(score)

    return {"symbol": symbol, "sentiment": score}
"""
```

---

## Risk Metrics Service Metrics

Create service-specific metrics in `app/monitoring/risk_metrics.py`:

```python
# services/risk-metrics-service/app/monitoring/risk_metrics.py
"""
Custom Prometheus metrics for Risk Metrics Service.
Tracks portfolio risk, VaR, drawdown, and risk-adjusted returns.
"""

from prometheus_client import Counter, Histogram, Gauge, Summary

# =================================================================
# RISK METRICS
# =================================================================

# Risk calculation request counter
risk_metrics_calculations = Counter(
    'risk_metrics_calculations_total',
    'Total number of risk metric calculations',
    ['metric_type']  # metric_type: var, cvar, sharpe, sortino, etc.
)

# Portfolio risk percentage gauge
portfolio_risk_percentage = Gauge(
    'portfolio_risk_percentage',
    'Current portfolio risk as percentage of total capital'
)

# Portfolio drawdown gauge
portfolio_drawdown_percentage = Gauge(
    'portfolio_drawdown_percentage',
    'Current drawdown from peak equity'
)

# Maximum drawdown gauge
max_drawdown_percentage = Gauge(
    'max_drawdown_percentage',
    'Maximum drawdown observed'
)

# Value at Risk (VaR) gauges
value_at_risk_95 = Gauge(
    'value_at_risk_95',
    'Value at Risk at 95% confidence level in USD'
)

value_at_risk_99 = Gauge(
    'value_at_risk_99',
    'Value at Risk at 99% confidence level in USD'
)

# Conditional VaR (CVaR) gauge
conditional_var_95 = Gauge(
    'conditional_var_95',
    'Conditional Value at Risk (CVaR) at 95% confidence in USD'
)

# Risk-adjusted return metrics
sharpe_ratio = Gauge(
    'sharpe_ratio',
    'Sharpe ratio (risk-adjusted returns)'
)

sortino_ratio = Gauge(
    'sortino_ratio',
    'Sortino ratio (downside risk-adjusted returns)'
)

# Position metrics
position_size_percentage = Gauge(
    'position_size_percentage',
    'Position size as percentage of portfolio',
    ['symbol']
)

# Win/Loss tracking
winning_trades = Counter(
    'winning_trades_total',
    'Total number of winning trades',
    ['symbol']
)

losing_trades = Counter(
    'losing_trades_total',
    'Total number of losing trades',
    ['symbol']
)

# Calculation latency
risk_calculation_latency = Histogram(
    'risk_calculation_latency_seconds',
    'Time to calculate risk metrics',
    ['metric_type'],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0)
)

# Error counter
risk_metrics_errors = Counter(
    'risk_metrics_errors_total',
    'Total risk metrics calculation errors',
    ['error_type']
)

# =================================================================
# USAGE EXAMPLE
# =================================================================

"""
Example usage:

from app.monitoring.risk_metrics import (
    risk_metrics_calculations,
    portfolio_risk_percentage,
    value_at_risk_95,
    sharpe_ratio
)

@app.get("/risk/portfolio")
async def get_portfolio_risk():
    risk_metrics_calculations.labels(metric_type="portfolio").inc()

    with risk_calculation_latency.labels(metric_type="portfolio").time():
        risk = calculate_portfolio_risk()
        var_95 = calculate_var_95()
        sharpe = calculate_sharpe_ratio()

    # Update gauges
    portfolio_risk_percentage.set(risk)
    value_at_risk_95.set(var_95)
    sharpe_ratio.set(sharpe)

    return {"risk": risk, "var_95": var_95, "sharpe": sharpe}
"""
```

---

## Best Practices

### 1. Metric Naming Conventions

- **Counters**: Use `_total` suffix (e.g., `requests_total`)
- **Gauges**: No special suffix (e.g., `active_connections`)
- **Histograms**: Use base unit suffix (e.g., `_seconds`, `_bytes`)
- **Use labels**: For dimensions, not metric names

### 2. Label Best Practices

- Keep cardinality low (avoid unique IDs as labels)
- Use meaningful label names
- Be consistent across services
- Example good labels: `symbol`, `service`, `error_type`
- Example bad labels: `user_id`, `timestamp`, `request_id`

### 3. Metric Types

- **Counter**: Monotonically increasing (requests, errors)
- **Gauge**: Can go up and down (CPU usage, queue size)
- **Histogram**: Distribution of values (latency, request size)
- **Summary**: Similar to histogram, calculates quantiles client-side

### 4. Performance Considerations

- Minimize labels to reduce cardinality
- Use histograms for latency measurements
- Don't create metrics in hot loops
- Use context managers for timing: `with metric.time():`

### 5. Error Tracking

Always track errors with appropriate labels:

```python
try:
    result = risky_operation()
except ValueError as e:
    errors_total.labels(
        service="ml-prediction",
        error_type="value_error"
    ).inc()
    raise
```

---

## Testing Metrics Endpoint

After implementing metrics, test the endpoint:

```bash
# Start the service
docker-compose up ml-prediction

# Check metrics endpoint
curl http://localhost:8007/metrics

# You should see output like:
# HELP ml_prediction_requests_total Total number of ML prediction requests
# TYPE ml_prediction_requests_total counter
# ml_prediction_requests_total{model_type="lstm",symbol="BTCUSDT"} 42.0
```

---

## Troubleshooting

### Metrics Not Showing Up

1. Check if Prometheus is scraping the service:
   ```bash
   # Check Prometheus targets
   open http://localhost:9090/targets
   ```

2. Verify service is exposing metrics:
   ```bash
   curl http://localhost:8007/metrics
   ```

3. Check Prometheus configuration:
   ```bash
   cat infrastructure/monitoring/prometheus.yml
   ```

### High Cardinality Warning

If you see "too many metrics" warnings:
- Reduce number of labels
- Avoid using unique IDs as labels
- Combine related metrics

### Metrics Not Updating

- Ensure you're incrementing/setting metrics in your code
- Check for exceptions in metric recording
- Verify metric names match Prometheus queries

---

## Next Steps

1. Add metrics to all Phase 3 services
2. Create custom dashboards in Grafana
3. Set up alert rules in Prometheus
4. Implement alert routing to Slack/email
5. Add metric-based autoscaling

For more information, see:
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Prometheus Python Client](https://github.com/prometheus/client_python)
- [FastAPI Instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator)
