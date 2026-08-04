# Sentiment Analysis Service

> **STATUS (2026-07-30): IDLE.** The sentiment leg was removed from the signal pipeline in **2026-05** (`ENABLE_SENTIMENT_ANALYSIS=false`; commits `c346483`, `acae081`, `fe941cf`, `c171bb0` — see repo CLAUDE.md), and this service **does not start by default**: since **2026-07-29** it sits behind the compose `analytics` profile. Its BUY/SELL/HOLD output is **not consumed** by the trading-engine. To run it anyway:
> ```bash
> docker compose -f docker-compose.unified.yml --profile analytics up -d sentiment-analysis-service
> ```

> Merged from `QUICK_START.md` on 2026-07-30.

A microservice for analyzing cryptocurrency market sentiment from news and social media sources. Integrates with real APIs (NewsAPI and Twitter) with graceful fallback to mock data. Runs on **port 8008**.

## Features

- **Real-time News Analysis**: Fetches crypto news from NewsAPI.org (80,000+ sources)
- **Twitter Sentiment**: Analyzes crypto-related tweets using Twitter API v2
- **Engagement Weighting**: Weights sentiment by engagement metrics (likes, retweets)
- **ML-Based Sentiment**: Uses FinBERT for financial sentiment analysis
- **Intelligent Caching**: TTL-based caching to respect API rate limits
- **Rate Limit Handling**: Exponential backoff with automatic retries
- **Graceful Degradation**: Falls back to cached/mock data on API failures
- **Trading Signals**: Generates BUY/SELL/HOLD signals based on sentiment (currently not wired into the trading pipeline — see status banner)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│          Sentiment Analysis Service (Port 8008)         │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ News Fetcher │  │   Twitter    │  │  Sentiment   │ │
│  │   (NewsAPI)  │  │   Fetcher    │  │  Analyzer    │ │
│  │              │  │ (Twitter v2) │  │  (FinBERT)   │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
│         │                  │                  │         │
│         └──────────────────┴──────────────────┘         │
│                           │                              │
│                    ┌──────▼───────┐                     │
│                    │ Sentiment    │                     │
│                    │ Aggregation  │                     │
│                    │ & Caching    │                     │
│                    └──────────────┘                     │
└─────────────────────────────────────────────────────────┘
```

Request flow:
```
Request → Cache Check → Real API → Sentiment Analysis → Response
              ↓ Miss       ↓ Fail         ↓
            Real API → Stale Cache → Mock Data
```

## Quick Start

### Option 1: With Real APIs

```bash
# 1. Get API keys
# - NewsAPI: https://newsapi.org/register (instant)
# - Twitter: https://developer.twitter.com/ (usually instant)

# 2. Configure environment
cd services/sentiment-analysis-service
cp .env.example .env
nano .env  # Add your API keys

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run service
uvicorn app.main:app --reload --port 8008
```

### Option 2: Without APIs (Testing/Development)

```bash
cd services/sentiment-analysis-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8008
# Works immediately with realistic mock data
```

Production-style run: `uvicorn app.main:app --host 0.0.0.0 --port 8008 --workers 4`

### Quick API Test

```bash
curl http://localhost:8008/health                                       # health
curl http://localhost:8008/ready | jq                                   # which APIs configured
curl "http://localhost:8008/api/v1/sentiment/news/BTCUSDT" | jq         # news sentiment
curl "http://localhost:8008/api/v1/sentiment/social/BTCUSDT" | jq       # Twitter sentiment
curl "http://localhost:8008/api/v1/sentiment/combined/BTCUSDT" | jq     # combined + signal
curl http://localhost:8008/api/v1/stats | jq                            # API usage / cache
```

## API Configuration

### NewsAPI Setup

1. Sign up at https://newsapi.org/register
2. Plans: Free 100 requests/day; Developer ($49/mo) 250/day; Business ($499/mo) 1000/day
3. Add to `.env`:
```env
NEWS_API_KEY=your_newsapi_key_here
```

**Rate limits**: free tier 100 requests/day; service caches results 15 minutes and falls back to cached data when rate-limited.

### Twitter API Setup

1. Create a developer account at https://developer.twitter.com/
2. Create a Project + App, then generate a **Bearer Token** (Keys and tokens tab)
3. Add to `.env`:
```env
TWITTER_BEARER_TOKEN=your_twitter_bearer_token_here
```

**Rate limits**: Essential (free) access 450 requests per 15-minute window; service caches 10 minutes with automatic backoff.

### Access Levels Comparison

| Feature | Free NewsAPI | Free Twitter | Notes |
|---------|-------------|--------------|-------|
| Requests/day | 100 | ~43,200 (450/15min) | Twitter much more generous |
| Historical data | 1 month | 7 days | NewsAPI better for history |
| Real-time | Yes | Yes | Both support real-time |
| Caching | 15 min | 10 min | Configured in service |
| Cost | Free | Free | Both have paid tiers |

## API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Service health |
| `GET /ready` | API configuration status |
| `GET /api/v1/stats` | Usage stats, cache info |
| `GET /api/v1/sentiment/news/{symbol}` | News sentiment |
| `GET /api/v1/sentiment/social/{symbol}` | Twitter sentiment |
| `GET /api/v1/sentiment/combined/{symbol}` | Combined sentiment + signal |
| `GET /api/v1/sentiment/trend/{symbol}` | Sentiment trend |

### News Sentiment
```bash
GET /api/v1/sentiment/news/BTCUSDT?lookback_hours=24
```
```json
{
  "symbol": "BTCUSDT",
  "total_articles": 15,
  "articles": [...],
  "average_sentiment": 0.45,
  "sentiment_label": "BULLISH",
  "confidence": 0.82,
  "positive_count": 8,
  "negative_count": 3,
  "neutral_count": 4
}
```

### Social Sentiment
```bash
GET /api/v1/sentiment/social/BTCUSDT?lookback_hours=24
```
```json
{
  "twitter": {
    "symbol": "BTCUSDT",
    "platform": "twitter",
    "total_posts": 87,
    "posts": [...],
    "average_sentiment": 0.32,
    "weighted_sentiment": 0.41,
    "sentiment_label": "POSITIVE",
    "total_engagement": 15420.0,
    "average_engagement": 177.0
  }
}
```

### Combined Sentiment
```bash
GET /api/v1/sentiment/combined/BTCUSDT
```
```json
{
  "symbol": "BTCUSDT",
  "news_sentiment": {...},
  "social_sentiment": {...},
  "overall_sentiment": 0.52,
  "sentiment_label": "BULLISH",
  "sentiment_strength": 0.74,
  "confidence": 0.85,
  "data_quality": "EXCELLENT",
  "trading_signal": "BUY",
  "signal_strength": 0.74,
  "sources_used": ["news", "twitter"],
  "analysis_timestamp": "...",
  "next_update_at": "..."
}
```

## Configuration

### Environment Variables

```env
# Service Configuration
ENVIRONMENT=development
SERVICE_PORT=8008

# API Keys (optional - service works with mock data if not provided)
NEWS_API_KEY=your_newsapi_key_here
TWITTER_BEARER_TOKEN=your_twitter_bearer_token_here

# Sentiment Settings
SENTIMENT_CACHE_TTL_MINUTES=15
MIN_NEWS_COUNT=3
SENTIMENT_LOOKBACK_HOURS=24

# Scoring Weights (must sum to 1.0)
NEWS_WEIGHT=0.4
SOCIAL_WEIGHT=0.3
TECHNICAL_WEIGHT=0.3

# Sentiment Thresholds
BULLISH_THRESHOLD=0.6
BEARISH_THRESHOLD=0.4
```

### Caching Strategy

- **News**: TTL 15 min, cache size 100 queries, timestamps rounded to nearest 15 min for better hit rate; stale cache used on API failure
- **Twitter**: TTL 10 min, cache size 100 queries, timestamps rounded to nearest 10 min; stale cache on failure
- **Combined sentiment**: in-memory, configurable TTL (default 15 min)

### Rate Limit Strategy

Exponential backoff: 3 attempts with 2s/4s/8s waits; retries only on API errors (not data errors).

```bash
# Monitor API usage
curl http://localhost:8008/api/v1/stats
```
```json
{
  "news_api": {
    "api_enabled": true,
    "total_api_calls": 47,
    "cache_size": 12,
    "cache_hit_rate": "74.5%"
  },
  "twitter_api": {
    "api_enabled": true,
    "total_api_calls": 89,
    "cache_size": 23
  }
}
```

## Error Handling

1. **API key missing**: falls back to mock data (logs warning)
2. **Rate limit exceeded**: returns stale cached data if available
3. **API temporarily down**: uses mock data with warning log
4. **Network error**: retries with exponential backoff
5. **Data quality low**: returns result with `"POOR"` quality indicator

## Testing

```bash
# Without API keys — service uses realistic mock data
uvicorn app.main:app --reload
curl http://localhost:8008/api/v1/sentiment/combined/BTCUSDT

# With real APIs — add keys to .env, then verify:
curl http://localhost:8008/api/v1/stats     # "api_enabled": true for both APIs

# Unit tests (mocked APIs)
pytest tests/ -v
pytest tests/ --cov=app --cov-report=html
pytest tests/test_news_fetcher.py -v
```

## Deployment

Preferred: canonical compose with the `analytics` profile (see status banner). Standalone docker:

```bash
# Build
docker build -t sentiment-analysis-service .

# Run without API keys (mock data)
docker run -p 8008:8008 sentiment-analysis-service

# Run with API keys
docker run -d -p 8008:8008 \
  -e NEWS_API_KEY=your_key \
  -e TWITTER_BEARER_TOKEN=your_token \
  --name sentiment-service \
  sentiment-analysis-service
```

### Monitoring

```bash
tail -f logs/sentiment-analysis.log
watch -n 5 'curl -s http://localhost:8008/api/v1/stats | jq'
curl http://localhost:8008/health
```

### Activation Checklist (if re-enabling the service)

- [ ] Start under `analytics` profile (`--profile analytics`)
- [ ] Add API keys to `.env`
- [ ] Test with `/ready` endpoint
- [ ] Monitor `/api/v1/stats` for usage
- [ ] Review cache TTL settings and test fallback behavior
- [ ] Set up log monitoring and health checks
- [ ] Re-wiring the signal into trading requires reverting the 2026-05 pipeline removal in trading-engine/technical-analysis (`ENABLE_SENTIMENT_ANALYSIS`) — a deliberate decision, not just starting this service

## Troubleshooting

### NewsAPI

**"You have exceeded your rate limit"**: check `curl http://localhost:8008/api/v1/stats`; service automatically serves cached data; upgrade plan for higher limits.

**"No articles found"**: check symbol is recognized, extend `lookback_hours`, verify API key.

### Twitter API

**"401 Unauthorized"**: verify bearer token correct/unexpired; app has read permissions.

**"Rate limit exceeded"**: service waits automatically; tune cache TTL; consider elevated access.

### General

**Service returning mock data**: `curl http://localhost:8008/ready | jq '.apis_configured'` — add API keys to `.env`.

**Sentiment always neutral**: check FinBERT model loaded (`transformers` package installed), verify text contains sentiment keywords, try other symbols/timeframes.

**No sentiment data**: use standard Bybit symbol format — `BTCUSDT`, `ETHUSDT` (not `BTC-USDT` or `btc`).

## Performance Tips

1. **Enable caching**: default 15 minutes (cuts API calls ~75%)
2. **Use the combined endpoint**: all data in one call
3. **Monitor stats**: check `/api/v1/stats` for optimization opportunities
4. **Batch requests**: request multiple symbols in sequence (cache works)
5. **Adjust lookback**: shorter = faster, longer = more accurate

## Development

### Adding New Data Sources

1. Create new fetcher module (e.g., `reddit_fetcher.py`)
2. Implement caching and retry logic
3. Add configuration to `config.py`
4. Integrate in `main.py`
5. Update tests

### Customizing Sentiment Weights

Edit `.env`:
```env
NEWS_WEIGHT=0.5      # Increase news importance
SOCIAL_WEIGHT=0.4    # Increase social importance
TECHNICAL_WEIGHT=0.1 # Decrease technical importance
```

## API Cost Comparison

| Provider | Free Tier | Paid Tier | Cost/1000 req |
|----------|-----------|-----------|---------------|
| NewsAPI | 100/day | 250-1000/day | $0.16-$1.66 |
| Twitter | 450/15min | Same (higher monthly) | Free |
| Reddit | 60/min | Same | Free |

**Recommendation**: free tiers with proper caching are sufficient for most use cases.

## Support & Resources

- **API Docs**: http://localhost:8008/docs (Swagger UI)
- **Environment example**: `.env.example`
- **Logs**: `logs/sentiment-analysis.log`
- **API stats**: `GET /api/v1/stats`

## License

MIT License - See LICENSE file for details
