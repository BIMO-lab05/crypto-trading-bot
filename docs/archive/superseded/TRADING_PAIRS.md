# Trading Pairs Documentation

## Overview
This document describes the trading pairs supported by the crypto trading bot and their configuration across all services.

**Last Updated:** 2025-11-11

## Supported Trading Pairs

The bot currently supports the following 7 trading pairs:

| Symbol      | Base Asset | Quote Asset | Description                    | Typical Price Range |
|-------------|------------|-------------|--------------------------------|---------------------|
| BTCUSDT     | BTC        | USDT        | Bitcoin / Tether               | $20,000 - $100,000  |
| ETHUSDT     | ETH        | USDT        | Ethereum / Tether              | $1,000 - $5,000     |
| BNBUSDT     | BNB        | USDT        | Binance Coin / Tether          | $200 - $700         |
| SOLUSDT     | SOL        | USDT        | Solana / Tether                | $10 - $200          |
| XRPUSDT     | XRP        | USDT        | Ripple / Tether                | $0.30 - $3.00       |
| ADAUSDT     | ADA        | USDT        | Cardano / Tether               | $0.20 - $3.00       |
| DOGEUSDT    | DOGE       | USDT        | Dogecoin / Tether              | $0.05 - $0.70       |

## Service Configuration

### 1. Market Data Service
**File:** `services/market-data-service/app/config.py`

```python
default_symbols: str = Field(
    default="BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT"
)
```

- Collects real-time and historical price data for all pairs
- Stores data in TimescaleDB for time-series analysis
- Caches ticker data with 5-second TTL
- Fetches 30 days of historical data on startup

### 2. Technical Analysis Service
**File:** `services/technical-analysis/app/config.py`

- Calculates indicators (RSI, MACD, Bollinger Bands, EMA, SMA) for all pairs
- Generates trading signals with confidence scores
- Publishes signals via RabbitMQ for consumption by trading engine

### 3. Trading Engine
**File:** `services/trading-engine/app/config.py`

```python
default_symbol: str = Field(
    default="BTCUSDT",
    description="Default trading symbol"
)
```

- Aggregates signals from multiple sources
- Executes trades for any of the 7 pairs
- Applies risk management rules per pair
- Supports both paper and live trading modes

### 4. ML Prediction Service
**File:** `services/ml-prediction-service/app/config.py`

- LSTM models train independently for each trading pair
- Predicts price trends 5 candles ahead (5 hours for 60m timeframe)
- Models stored in: `services/ml-prediction-service/trained_models/{symbol}/`
- Retraining recommended every 7 days

### 5. Sentiment Analysis Service
**File:** `services/sentiment-analysis-service/app/config.py`

- Analyzes news and social media sentiment for each asset
- Caches sentiment scores for 15 minutes
- Combines news (40%), social (30%), and technical (30%) weights
- Supports symbol-specific searches (e.g., "Solana" for SOL, "Ripple" for XRP)

### 6. API Gateway
**File:** `services/api-gateway/app/config.py`

- Routes requests for all 7 pairs to appropriate backend services
- Validates symbols using SymbolValidator (must end with "USDT")
- Implements rate limiting per symbol endpoint
- Caches frequently accessed data

## Frontend Integration

### Phase 3 Dashboard
**File:** `frontend/src/pages/Phase3Dashboard.jsx`

```javascript
const symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT']
```

Features:
- Symbol selector with all 7 pairs
- ML predictions display per symbol
- Sentiment analysis per asset
- Multi-timeframe confirmation
- Real-time enhanced signals

### Price Ticker Grid
**File:** `frontend/src/components/PriceTickerGrid.jsx`

```javascript
symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT']
```

Displays:
- Real-time prices with 3-second refresh
- 24-hour price change percentage
- 24-hour high/low
- 24-hour trading volume
- Responsive grid (1 column mobile, 3 desktop, 4 large screens)

## Scripts and Automation

### Automated Trading Loop
**File:** `scripts/automated_trading_loop.py`

```python
symbols=["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT"]
```

Configuration:
- Monitors all 7 pairs every 5 minutes
- Executes trades based on 60-minute signals
- Maximum 20 trades per day across all pairs
- 2% position size limit per trade
- 5% daily loss limit across portfolio

### Backtesting Scripts
**File:** `backtesting/run_phase1_backtest.py`

Default symbol: BTCUSDT (can be changed via `--symbol` argument)

```bash
python backtesting/run_phase1_backtest.py --symbol SOLUSDT --days 90
```

Supports all 7 pairs for historical performance analysis.

## Data Requirements

### Historical Data
Minimum data needed for indicators:
- RSI: 14+ candles
- MACD: 26+ candles
- Bollinger Bands: 20+ candles
- EMA 50/200 (Trend Filter): 200+ candles
- ML Training: 500+ candles recommended

### ML Model Training
Per symbol requirements:
- Training data: 80% of available history
- Test data: 20% of available history
- Minimum dataset: 60 candles (for 60-step sequence)
- Recommended dataset: 1000+ candles (40+ days at 60m interval)
- Retraining frequency: Weekly or when accuracy drops

### Sentiment Data
- News articles: Minimum 3 per symbol for analysis
- Social media: Posts from last 24 hours
- Data quality threshold: "HIGH" requires 10+ sources

## Adding New Trading Pairs

To add a new trading pair (e.g., MATICUSDT):

1. **Update Service Configs:**
   ```python
   # services/market-data-service/app/config.py
   default_symbols: str = "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,MATICUSDT"
   ```

2. **Update Frontend:**
   ```javascript
   // frontend/src/pages/Phase3Dashboard.jsx
   const symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'MATICUSDT']
   ```

3. **Update Scripts:**
   ```python
   # scripts/automated_trading_loop.py
   symbols=["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "MATICUSDT"]
   ```

4. **Fetch Historical Data:**
   ```bash
   python backtesting/data_downloader.py --symbol MATICUSDT --days 90
   ```

5. **Train ML Model:**
   ```bash
   curl -X POST http://localhost:8007/ml/train/MATICUSDT?interval=60
   ```

6. **Restart Services:**
   ```bash
   docker-compose restart market-data-service technical-analysis ml-prediction-service
   ```

## Symbol Validation

All symbols must:
- Be uppercase (e.g., BTCUSDT, not btcusdt)
- End with "USDT" (only USDT pairs supported)
- Have alphabetic base asset (BTC, ETH, etc.)
- Be 5-20 characters in length
- Be supported by Bybit exchange

Invalid examples:
- ~~BTCUSD~~ (missing T)
- ~~btcusdt~~ (lowercase)
- ~~BTC-USDT~~ (contains hyphen)
- ~~BTCBUSD~~ (wrong quote asset)

## Performance Considerations

### Timeframe Support
All pairs support these intervals:
- 1 minute (1)
- 5 minutes (5)
- 15 minutes (15)
- 30 minutes (30)
- 1 hour (60) - **default**
- 4 hours (240)
- Daily (D)

### API Rate Limits
Bybit limits:
- 120 requests per minute for market data
- 100 requests per minute for trading
- Bot implements connection pooling and caching to stay within limits

### Database Storage
Per symbol, per day (60m interval):
- OHLCV data: ~24 rows/day
- Indicators: ~24 rows/day
- Signals: ~5-10 rows/day
- Storage: ~5KB/day per symbol

For 7 symbols over 90 days: ~3.15MB

## Testing Recommendations

### Unit Testing
Test each pair individually:
```python
@pytest.mark.parametrize("symbol", [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT",
    "XRPUSDT", "ADAUSDT", "DOGEUSDT"
])
def test_indicator_calculation(symbol):
    # Test logic here
```

### Integration Testing
1. Verify all pairs return ticker data
2. Confirm technical indicators calculate correctly
3. Test ML predictions for each pair
4. Validate sentiment analysis retrieval

### Performance Testing
- Load test with all 7 pairs fetching simultaneously
- Verify p95 latency < 100ms per symbol
- Confirm cache hit rate > 80%

## Monitoring

### Key Metrics Per Symbol
- API response time
- Signal generation frequency
- Model prediction accuracy
- Trade execution success rate
- Position profit/loss

### Alerts
Set up alerts for:
- Missing ticker data (>60 seconds)
- ML model errors
- Failed trade executions
- Unusual price movements (>20% in 1 hour)
- Daily loss limit approaching (>4%)

## Resources

### External Links
- [Bybit API Documentation](https://bybit-exchange.github.io/docs/v5/intro)
- [Technical Analysis Library](https://technical-analysis-library-in-python.readthedocs.io/)
- [TensorFlow LSTM Guide](https://www.tensorflow.org/guide/keras/rnn)

### Internal Documentation
- [Architecture Overview](./architecture/SYSTEM_OVERVIEW.md)
- [API Specifications](./api/openapi.yaml)
- [Development Setup](./development/SETUP.md)
- [Risk Management](./trading/RISK_MANAGEMENT.md)

## Version History

| Version | Date       | Changes                                           |
|---------|------------|---------------------------------------------------|
| 2.0     | 2025-11-11 | Added SOLUSDT, XRPUSDT, ADAUSDT, DOGEUSDT         |
| 1.0     | 2025-10-30 | Initial version with BTCUSDT, ETHUSDT, BNBUSDT    |

---

**Note:** All trading pairs are subject to Bybit availability. If a pair is delisted or suspended, remove it from configurations immediately to prevent errors.

**Risk Warning:** Cryptocurrency trading involves significant risk. Always test new pairs in paper trading mode before live trading. Never risk more than you can afford to lose.
