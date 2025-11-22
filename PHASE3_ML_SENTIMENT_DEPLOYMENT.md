# Phase 3: ML Predictions + Sentiment Analysis - Deployment Guide

**Date**: November 10, 2025
**Status**: ✅ Implementation Complete
**Services Added**: 2 new microservices (ML Prediction, Sentiment Analysis)

---

## 🎉 What's New in Phase 3

### New Capabilities
1. **ML Price Predictions** - LSTM-based price forecasting
2. **Sentiment Analysis** - News and social media sentiment scoring
3. **Multi-Timeframe Analysis** - Trend confirmation across 6 timeframes
4. **Enhanced Trading Signals** - ML + Sentiment + Technical combined

### New Services

| Service | Port | Purpose |
|---------|------|---------|
| **ML Prediction Service** | 8007 | LSTM price predictions, volatility forecasting |
| **Sentiment Analysis Service** | 8008 | News & social sentiment analysis |
| **Risk Metrics Service** | 8009 | *(Port changed from 8007 to avoid conflict)* |

---

## 📦 Installation

### 1. Install Dependencies for ML Prediction Service

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/services/ml-prediction-service

# Install Python dependencies
pip install -r requirements.txt

# Note: TensorFlow may take several minutes to install
# If you encounter issues with TensorFlow, use:
pip install tensorflow==2.15.0 --no-cache-dir
```

**Dependencies installed:**
- TensorFlow 2.15.0 (for LSTM models)
- scikit-learn 1.3.2 (for data preprocessing)
- pandas, numpy (for data processing)
- FastAPI, uvicorn (web framework)

### 2. Install Dependencies for Sentiment Analysis Service

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/services/sentiment-analysis-service

# Install Python dependencies
pip install -r requirements.txt

# Optional: For advanced ML-based sentiment (recommended but not required)
pip install transformers torch

# Note: transformers will use FinBERT model (financial sentiment analysis)
# First run will download ~400MB model - be patient!
```

**Dependencies installed:**
- transformers 4.35.0 (for FinBERT sentiment model)
- torch 2.1.1 (PyTorch for transformers)
- httpx, FastAPI (API framework)

### 3. Verify Installation

```bash
# Check TensorFlow
python3 -c "import tensorflow as tf; print('TensorFlow version:', tf.__version__)"

# Check transformers
python3 -c "import transformers; print('Transformers version:', transformers.__version__)"

# Check scikit-learn
python3 -c "import sklearn; print('scikit-learn version:', sklearn.__version__)"
```

---

## 🚀 Starting the Services

### Option A: Start All Services (Recommended)

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot

# Kill any existing services
pkill -f "uvicorn"

# Start ML Prediction Service (port 8007)
cd services/ml-prediction-service
PYTHONPATH=. nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8007 > /tmp/ml-prediction.log 2>&1 &

# Start Sentiment Analysis Service (port 8008)
cd /mnt/d/Bimo_max/crypto-trading-bot/services/sentiment-analysis-service
PYTHONPATH=. nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8008 > /tmp/sentiment-analysis.log 2>&1 &

# Restart Risk Metrics Service on new port (8009)
cd /mnt/d/Bimo_max/crypto-trading-bot/services/risk-metrics-service
PYTHONPATH=. nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8009 > /tmp/risk-metrics.log 2>&1 &

# Start other existing services (if not already running)
cd /mnt/d/Bimo_max/crypto-trading-bot

# API Gateway (port 8000)
cd services/api-gateway && PYTHONPATH=. nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/api-gateway.log 2>&1 &

# Bybit Connector (port 8002)
cd /mnt/d/Bimo_max/crypto-trading-bot/services/bybit-connector && PYTHONPATH=. nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8002 > /tmp/bybit-connector.log 2>&1 &

# Market Data Service (port 8003)
cd /mnt/d/Bimo_max/crypto-trading-bot/services/market-data-service && PYTHONPATH=. nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8003 > /tmp/market-data.log 2>&1 &

# Technical Analysis (port 8004)
cd /mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis && PYTHONPATH=. nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8004 > /tmp/technical-analysis.log 2>&1 &

# Trading Engine (port 8005)
cd /mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine && PYTHONPATH=. nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8005 > /tmp/trading-engine.log 2>&1 &

# Portfolio Manager (port 8006)
cd /mnt/d/Bimo_max/crypto-trading-bot/services/portfolio-manager && PYTHONPATH=. nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8006 > /tmp/portfolio-manager.log 2>&1 &

sleep 5

# Check all services are running
ps aux | grep uvicorn | grep -v grep
```

### Option B: Start Only New Services (for testing)

```bash
# Start only ML and Sentiment services
cd /mnt/d/Bimo_max/crypto-trading-bot

# ML Prediction Service
cd services/ml-prediction-service
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8007

# In another terminal, start Sentiment Analysis Service
cd /mnt/d/Bimo_max/crypto-trading-bot/services/sentiment-analysis-service
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8008
```

### Verify Services Are Running

```bash
# Check health of new services
curl http://localhost:8007/health  # ML Prediction Service
curl http://localhost:8008/health  # Sentiment Analysis Service
curl http://localhost:8009/health  # Risk Metrics (new port)

# Check API Gateway routes to new services
curl http://localhost:8000/health

# Check service logs
tail -f /tmp/ml-prediction.log
tail -f /tmp/sentiment-analysis.log
```

---

## 🧠 Training ML Models

Before making predictions, you need to train the LSTM models.

### Quick Start: Train Model for BTCUSDT

```bash
# Train BTCUSDT model (90 days of data)
curl -X POST "http://localhost:8007/api/v1/models/train" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "interval": "60",
    "lookback_days": 90,
    "force_retrain": false
  }'

# Training will take 5-15 minutes depending on your hardware
# Watch the logs to see progress
tail -f /tmp/ml-prediction.log
```

### Train Models for All Symbols

```bash
# Train models for BTC, ETH, BNB
for symbol in BTCUSDT ETHUSDT BNBUSDT; do
  echo "Training model for $symbol..."

  curl -X POST "http://localhost:8007/api/v1/models/train" \
    -H "Content-Type: application/json" \
    -d "{
      \"symbol\": \"$symbol\",
      \"interval\": \"60\",
      \"lookback_days\": 90,
      \"force_retrain\": false
    }"

  echo "Model training started for $symbol"
  sleep 5
done

echo "All training jobs submitted!"
echo "Check logs: tail -f /tmp/ml-prediction.log"
```

### Check Model Status

```bash
# Check if model is trained
curl "http://localhost:8007/api/v1/models/BTCUSDT?interval=60" | python3 -m json.tool

# List all trained models
curl "http://localhost:8007/api/v1/models" | python3 -m json.tool
```

**Expected output:**
```json
{
  "model_type": "LSTM",
  "model_version": "v20251110_120000",
  "last_trained": "2025-11-10T12:00:00",
  "validation_accuracy": 0.75,
  "validation_mae": 245.32,
  "validation_rmse": 312.54,
  "status": "READY",
  "needs_retraining": false
}
```

---

## 🧪 Testing the New Features

### 1. Test ML Price Predictions

```bash
# Get price prediction for BTCUSDT
curl "http://localhost:8000/api/ml/predict/price/BTCUSDT?interval=60" | python3 -m json.tool

# Expected output shows predictions for next 5 hours
# Example:
# {
#   "symbol": "BTCUSDT",
#   "current_price": 45000.00,
#   "predictions": [
#     {
#       "timestamp": "2025-11-10T13:00:00",
#       "predicted_price": 45123.45,
#       "confidence": 0.75,
#       "lower_bound": 44900.00,
#       "upper_bound": 45350.00
#     },
#     ...
#   ],
#   "predicted_direction": "UP",
#   "directional_strength": 0.65
# }
```

### 2. Test Sentiment Analysis

```bash
# Get news sentiment for BTCUSDT
curl "http://localhost:8000/api/sentiment/news/BTCUSDT?lookback_hours=24" | python3 -m json.tool

# Get combined sentiment (news + social + technical)
curl "http://localhost:8000/api/sentiment/combined/BTCUSDT" | python3 -m json.tool

# Expected output shows aggregated sentiment
# {
#   "symbol": "BTCUSDT",
#   "overall_sentiment": 0.45,
#   "sentiment_label": "BULLISH",
#   "trading_signal": "BUY",
#   "signal_strength": 0.65,
#   "confidence": 0.70
# }
```

### 3. Test Multi-Timeframe Analysis

```bash
# Analyze BTCUSDT across multiple timeframes
curl "http://localhost:8000/api/analysis/multi-timeframe/BTCUSDT?timeframes=1m,5m,15m,60m,240m,1d" | python3 -m json.tool

# Expected output shows alignment across timeframes
# {
#   "alignment_score": 85.0,
#   "consensus_signal": "BUY",
#   "short_term_trend": "BULLISH",
#   "medium_term_trend": "BULLISH",
#   "long_term_trend": "BULLISH",
#   "overall_signal": "BUY",
#   "signal_strength": 0.82
# }
```

### 4. Test API Gateway Integration

```bash
# Test all new endpoints through API Gateway
endpoints=(
  "/api/ml/predict/price/BTCUSDT?interval=60"
  "/api/ml/predict/trend/BTCUSDT?interval=60"
  "/api/ml/predict/volatility/BTCUSDT?interval=60"
  "/api/sentiment/combined/BTCUSDT"
  "/api/analysis/multi-timeframe/BTCUSDT"
)

for endpoint in "${endpoints[@]}"; do
  echo "Testing: $endpoint"
  curl "http://localhost:8000$endpoint" | python3 -m json.tool
  echo ""
  sleep 1
done
```

---

## 📊 API Documentation

### Interactive API Docs

Access Swagger UI for each service:

- **ML Prediction**: http://localhost:8007/docs
- **Sentiment Analysis**: http://localhost:8008/docs
- **API Gateway (all endpoints)**: http://localhost:8000/docs

### New Endpoints via API Gateway

#### ML Prediction Endpoints

```
GET  /api/ml/predict/price/{symbol}       - Get price predictions
GET  /api/ml/predict/trend/{symbol}       - Get trend prediction
GET  /api/ml/predict/volatility/{symbol}  - Get volatility forecast
GET  /api/ml/models/{symbol}              - Get model info
POST /api/ml/models/train                 - Train/retrain model
```

#### Sentiment Analysis Endpoints

```
GET /api/sentiment/news/{symbol}          - News sentiment
GET /api/sentiment/social/{symbol}        - Social media sentiment
GET /api/sentiment/combined/{symbol}      - Combined sentiment
GET /api/sentiment/trend/{symbol}         - Sentiment trend over time
```

#### Multi-Timeframe Analysis

```
GET /api/analysis/multi-timeframe/{symbol} - Analyze multiple timeframes
```

---

## 🔧 Configuration

### ML Prediction Service Configuration

Edit `services/ml-prediction-service/app/config.py`:

```python
# Model settings
model_type: str = "LSTM"  # LSTM, GRU, or Transformer
sequence_length: int = 60  # Number of candles to look back
prediction_horizon: int = 5  # Predict N candles ahead

# Training settings
epochs: int = 50
batch_size: int = 32
learning_rate: float = 0.001

# Model retraining
model_retrain_days: int = 7  # Retrain every N days
```

### Sentiment Analysis Service Configuration

Edit `services/sentiment-analysis-service/app/config.py`:

```python
# Sentiment settings
sentiment_cache_ttl_minutes: int = 15
min_news_count: int = 3
sentiment_lookback_hours: int = 24

# Scoring weights
news_weight: float = 0.4
social_weight: float = 0.3
technical_weight: float = 0.3

# Thresholds
bullish_threshold: float = 0.6
bearish_threshold: float = 0.4
```

---

## 🎯 Integration with Trading Engine

### Using ML Predictions in Trading Decisions

The trading engine can now use ML predictions by calling:

```python
# In trading-engine/app/signal_aggregator.py

async def get_ml_enhanced_signal(symbol: str, interval: str):
    # Fetch ML prediction
    ml_prediction = await http_client.get(
        f"{ml_prediction_url}/api/v1/predict/price/{symbol}",
        params={"interval": interval}
    )

    # Fetch sentiment
    sentiment = await http_client.get(
        f"{sentiment_url}/api/v1/sentiment/combined/{symbol}"
    )

    # Fetch multi-timeframe
    mtf_analysis = await http_client.get(
        f"{technical_analysis_url}/api/v1/analysis/multi-timeframe/{symbol}"
    )

    # Combine signals with weights
    final_signal = (
        ml_prediction['directional_strength'] * 0.3 +
        sentiment['signal_strength'] * 0.2 +
        mtf_analysis['signal_strength'] * 0.5
    )

    return final_signal
```

---

## 📈 Performance Expectations

### ML Prediction Service

- **Training time**: 5-15 minutes per symbol (90 days of data)
- **Prediction latency**: <500ms per request
- **Model size**: ~50-100MB per symbol
- **Memory usage**: ~1-2GB RAM during training, ~500MB at rest

### Sentiment Analysis Service

- **Lexicon-based sentiment**: <100ms per request
- **ML-based sentiment (FinBERT)**: 200-500ms per request
- **Model size**: ~400MB (FinBERT)
- **Cache TTL**: 15 minutes

### Multi-Timeframe Analysis

- **Analysis latency**: 1-2 seconds (6 timeframes)
- **Memory usage**: Minimal (~100MB)
- **Recommended use**: Pre-trade confirmation

---

## 🐛 Troubleshooting

### ML Prediction Service Won't Start

**Issue**: TensorFlow import error

```bash
# Check TensorFlow installation
python3 -c "import tensorflow as tf"

# If error, reinstall
pip uninstall tensorflow
pip install tensorflow==2.15.0 --no-cache-dir
```

**Issue**: Model training fails

```bash
# Check market data service is running
curl http://localhost:8003/health

# Check sufficient historical data available
curl "http://localhost:8003/api/v1/market/klines/BTCUSDT?interval=60&limit=500"

# Check disk space
df -h
```

### Sentiment Analysis Service Issues

**Issue**: Transformers model download fails

```bash
# Set cache directory
export TRANSFORMERS_CACHE=/path/to/cache

# Manually download model
python3 -c "from transformers import pipeline; pipeline('sentiment-analysis', model='ProsusAI/finbert')"
```

**Issue**: Slow sentiment analysis

- Use lexicon-based mode (faster but less accurate)
- Increase cache TTL to reduce API calls
- Consider upgrading hardware (FinBERT requires GPU for best performance)

### Port Conflicts

**Issue**: Port already in use

```bash
# Kill process using port
lsof -ti:8007 | xargs kill
lsof -ti:8008 | xargs kill

# Or kill all uvicorn processes
pkill -f uvicorn
```

---

## 🔄 Maintenance

### Model Retraining Schedule

Models should be retrained weekly to adapt to market changes:

```bash
# Add to crontab for weekly retraining (Sunday 2 AM)
0 2 * * 0 curl -X POST http://localhost:8007/api/v1/models/train -H "Content-Type: application/json" -d '{"symbol":"BTCUSDT","interval":"60","lookback_days":90,"force_retrain":true}'
```

### Monitor Model Performance

```bash
# Check model accuracy
curl "http://localhost:8007/api/v1/models/BTCUSDT?interval=60" | jq '.validation_r2_score'

# If R² score < 0.5, retrain the model
```

### Clear Sentiment Cache

```bash
# Restart service to clear cache
pkill -f "sentiment-analysis"
cd /mnt/d/Bimo_max/crypto-trading-bot/services/sentiment-analysis-service
PYTHONPATH=. python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8008 &
```

---

## 📝 Next Steps

1. **Train models for all symbols** (15-45 minutes)
2. **Test all endpoints** with sample requests
3. **Integrate with trading engine** (update signal aggregator)
4. **Update frontend dashboard** to display ML + Sentiment data
5. **Run backtests** to validate Phase 3 improvements
6. **Monitor performance** for 1-2 weeks before live trading

---

## 🎉 Summary

**Phase 3 Implementation Complete!**

✅ **ML Prediction Service** - LSTM price forecasting
✅ **Sentiment Analysis Service** - News & social sentiment
✅ **Multi-Timeframe Analysis** - Trend confirmation
✅ **API Gateway Integration** - Unified endpoints
✅ **Documentation** - Complete deployment guide

**Next Phase: Frontend Integration & Backtesting**

---

*Last Updated: November 10, 2025*
*Version: 1.0*
