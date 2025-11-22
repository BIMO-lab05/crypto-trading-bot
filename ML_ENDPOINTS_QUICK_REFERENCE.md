# ML Prediction Endpoints - Quick Reference

## Gateway URL
```
http://localhost:8000
```

---

## ML Prediction Endpoints

### 1. Price Prediction
```bash
GET /api/ml/predict/price/{symbol}?interval=60&model_type=LSTM

# Example
curl "http://localhost:8000/api/ml/predict/price/BTCUSDT?interval=60&model_type=LSTM"
```

**Response:**
- `predictions[]`: Array of price predictions with timestamps
- `current_price`: Latest price
- `model_type`: LSTM or GRU
- `predicted_direction`: UP, DOWN, or SIDEWAYS
- `average_confidence`: 0.0 to 1.0

---

### 2. Trend Prediction
```bash
GET /api/ml/predict/trend/{symbol}?interval=60&model_type=LSTM

# Example
curl "http://localhost:8000/api/ml/predict/trend/BTCUSDT?interval=60&model_type=LSTM"
```

**Response:**
- `trend`: BULLISH, BEARISH, or NEUTRAL
- `trend_confidence`: 0.0 to 1.0
- `reversal_probability`: 0.0 to 1.0
- `predicted_support_levels[]`: Support price levels
- `predicted_resistance_levels[]`: Resistance price levels

---

### 3. Volatility Forecast
```bash
GET /api/ml/predict/volatility/{symbol}?interval=60

# Example
curl "http://localhost:8000/api/ml/predict/volatility/BTCUSDT?interval=60"
```

**Response:**
- `current_volatility`: Current ATR/volatility
- `predicted_volatility_1h`: 1-hour forecast
- `predicted_volatility_4h`: 4-hour forecast
- `predicted_volatility_24h`: 24-hour forecast
- `risk_level`: LOW, MEDIUM, HIGH, or EXTREME
- `recommended_position_size_multiplier`: Position sizing factor

---

### 4. Trading Signal
```bash
GET /api/ml/predict/signal/{symbol}?interval=60&model_type=LSTM

# Example
curl "http://localhost:8000/api/ml/predict/signal/BTCUSDT?interval=60&model_type=LSTM"
```

**Response:**
- `signal`: BUY, SELL, or HOLD
- `confidence`: 0.0 to 1.0
- `prediction_data`: Full price prediction data

**Logic:**
- UP direction + strength > 0.6 → BUY
- DOWN direction + strength > 0.6 → SELL
- Otherwise → HOLD

---

### 5. List All Models
```bash
GET /api/ml/models

# Example
curl "http://localhost:8000/api/ml/models"
```

**Response:**
- `total_models`: Count of all models
- `lstm_count`: Number of LSTM models
- `gru_count`: Number of GRU models
- `models[]`: Array of model info

---

### 6. Get Model Info
```bash
GET /api/ml/models/{symbol}?interval=60&model_type=LSTM

# Example
curl "http://localhost:8000/api/ml/models/BTCUSDT?interval=60&model_type=LSTM"
```

**Response:**
- `model_type`: LSTM or GRU
- `model_version`: Version string
- `last_trained`: Training timestamp
- `validation_accuracy`: Model accuracy
- `validation_mae`: Mean Absolute Error
- `validation_rmse`: Root Mean Squared Error
- `validation_r2_score`: R² score
- `status`: READY, TRAINING, or ERROR
- `needs_retraining`: Boolean

---

### 7. Train Model
```bash
POST /api/ml/models/train?symbol=BTCUSDT&interval=60&lookback_days=90&force_retrain=false

# Example
curl -X POST "http://localhost:8000/api/ml/models/train?symbol=BTCUSDT&interval=60&lookback_days=90"
```

**Parameters:**
- `symbol`: Trading pair (required)
- `interval`: Timeframe in minutes (default: 60)
- `lookback_days`: Days of historical data (default: 90)
- `force_retrain`: Force retrain even if recent (default: false)

**Response:**
- `success`: Boolean
- `message`: Status message
- `model_version`: Model version
- `training_duration_seconds`: Time taken
- `model_info`: Full model information (if successful)

---

### 8. Compare Models
```bash
GET /api/ml/models/compare/{symbol}?interval=60

# Example
curl "http://localhost:8000/api/ml/models/compare/BTCUSDT?interval=60"
```

**Response:**
- `training_comparison`: LSTM vs GRU training metrics
- `prediction_comparison`: Prediction accuracy comparison
- `recommendation`: Which model to use
- `summary`: Quick comparison stats

---

## Sentiment Analysis Endpoints

### 9. Symbol Sentiment
```bash
GET /api/sentiment/{symbol}

# Example
curl "http://localhost:8000/api/sentiment/BTCUSDT"
```

**Response:**
- `sentiment_score`: -1.0 to 1.0
- `sentiment_class`: POSITIVE, NEGATIVE, or NEUTRAL
- `sources`: Array of sentiment sources
- `timestamp`: Analysis timestamp

---

### 10. Aggregate Sentiment
```bash
GET /api/sentiment/aggregate

# Example
curl "http://localhost:8000/api/sentiment/aggregate"
```

**Response:**
- `overall_sentiment`: Market-wide sentiment
- `sentiment_distribution`: Breakdown by classification
- `symbols`: Per-symbol sentiment
- `timestamp`: Analysis timestamp

---

## Common Parameters

### interval
- Values: "1", "5", "15", "60", "240", "D"
- Default: "60"
- Description: Timeframe in minutes (D = Daily)

### model_type
- Values: "LSTM", "GRU"
- Default: "LSTM"
- Description: Neural network architecture

### symbol
- Format: "{BASE}{QUOTE}" (e.g., "BTCUSDT")
- Required: Yes for most endpoints
- Description: Trading pair

---

## Error Codes

### 200 OK
Successful request

### 404 Not Found
```json
{
  "detail": "No trained LSTM model found for BTCUSDT 60m. Please train the model first."
}
```

### 503 Service Unavailable
```json
{
  "detail": "Service ml-prediction unavailable"
}
```
or
```json
{
  "detail": "TensorFlow not available"
}
```

### 504 Gateway Timeout
```json
{
  "detail": "Timeout connecting to ml-prediction"
}
```

---

## Quick Start

### 1. Train a model
```bash
curl -X POST "http://localhost:8000/api/ml/models/train?symbol=BTCUSDT&interval=60&lookback_days=90"
```

### 2. Get price prediction
```bash
curl "http://localhost:8000/api/ml/predict/price/BTCUSDT?interval=60"
```

### 3. Get trading signal
```bash
curl "http://localhost:8000/api/ml/predict/signal/BTCUSDT?interval=60"
```

### 4. Check model status
```bash
curl "http://localhost:8000/api/ml/models/BTCUSDT?interval=60"
```

---

## JavaScript Examples

```javascript
// Fetch price prediction
async function getPricePrediction(symbol, interval = '60', modelType = 'LSTM') {
  const response = await fetch(
    `/api/ml/predict/price/${symbol}?interval=${interval}&model_type=${modelType}`
  );
  return await response.json();
}

// Get trading signal
async function getTradingSignal(symbol, interval = '60') {
  const response = await fetch(
    `/api/ml/predict/signal/${symbol}?interval=${interval}`
  );
  return await response.json();
}

// Train model
async function trainModel(symbol, interval = '60', lookbackDays = 90) {
  const response = await fetch(
    `/api/ml/models/train?symbol=${symbol}&interval=${interval}&lookback_days=${lookbackDays}`,
    { method: 'POST' }
  );
  return await response.json();
}

// Check all models
async function getAllModels() {
  const response = await fetch('/api/ml/models');
  return await response.json();
}
```

---

## Python Examples

```python
import requests

# Base URL
BASE_URL = "http://localhost:8000"

# Get price prediction
def get_price_prediction(symbol, interval="60", model_type="LSTM"):
    url = f"{BASE_URL}/api/ml/predict/price/{symbol}"
    params = {"interval": interval, "model_type": model_type}
    response = requests.get(url, params=params)
    return response.json()

# Get trading signal
def get_trading_signal(symbol, interval="60"):
    url = f"{BASE_URL}/api/ml/predict/signal/{symbol}"
    params = {"interval": interval}
    response = requests.get(url, params=params)
    return response.json()

# Train model
def train_model(symbol, interval="60", lookback_days=90):
    url = f"{BASE_URL}/api/ml/models/train"
    params = {
        "symbol": symbol,
        "interval": interval,
        "lookback_days": lookback_days
    }
    response = requests.post(url, params=params)
    return response.json()

# Usage
prediction = get_price_prediction("BTCUSDT")
signal = get_trading_signal("BTCUSDT")
training = train_model("BTCUSDT", lookback_days=90)
```

---

## Integration Checklist

- [ ] API Gateway running on port 8000
- [ ] ML Prediction service running on port 8007
- [ ] Sentiment Analysis service running on port 8008
- [ ] Market Data service available (required for training)
- [ ] Models trained for desired symbols
- [ ] Error handling implemented in frontend
- [ ] Loading states for prediction requests
- [ ] Periodic model retraining scheduled

---

## Support

For issues or questions:
1. Check service health: `GET /health`
2. Verify model status: `GET /api/ml/models`
3. Review service logs: `docker logs crypto-bot-api-gateway`
4. Check ML service logs: `docker logs crypto-bot-ml-prediction`
