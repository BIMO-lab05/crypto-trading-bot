# Sentiment Analysis Service

A microservice for analyzing cryptocurrency market sentiment from news and social media sources. Integrates with real APIs (NewsAPI and Twitter) with graceful fallback to mock data.

## Features

- **Real-time News Analysis**: Fetches crypto news from NewsAPI.org (80,000+ sources)
- **Twitter Sentiment**: Analyzes crypto-related tweets using Twitter API v2
- **Engagement Weighting**: Weights sentiment by engagement metrics (likes, retweets)
- **ML-Based Sentiment**: Uses FinBERT for financial sentiment analysis
- **Intelligent Caching**: TTL-based caching to respect API rate limits
- **Rate Limit Handling**: Exponential backoff with automatic retries
- **Graceful Degradation**: Falls back to cached/mock data on API failures
- **Trading Signals**: Generates BUY/SELL/HOLD signals based on sentiment

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
│                                                          │
│  REST API Endpoints:                                    │
│  - GET /api/v1/sentiment/news/{symbol}                 │
│  - GET /api/v1/sentiment/social/{symbol}               │
│  - GET /api/v1/sentiment/combined/{symbol}             │
│  - GET /api/v1/sentiment/trend/{symbol}                │
│  - GET /api/v1/stats                                   │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## Getting Started

### Prerequisites

- Python 3.11+
- NewsAPI key (optional, get from https://newsapi.org/)
- Twitter API Bearer Token (optional, get from https://developer.twitter.com/)

### Installation

1. **Install dependencies**:
```bash
cd services/sentiment-analysis-service
pip install -r requirements.txt
```

2. **Configure environment variables**:
```bash
# Copy example env file
cp .env.example .env

# Edit .env with your API keys
nano .env
```

3. **Run the service**:
```bash
# Development mode
uvicorn app.main:app --reload --port 8008

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8008 --workers 4
```

## API Configuration

### NewsAPI Setup

1. **Sign up** for NewsAPI at https://newsapi.org/register
2. **Choose a plan**:
   - Free: 100 requests/day
   - Developer ($49/month): 250 requests/day
   - Business ($499/month): 1000 requests/day
3. **Copy your API key** from the dashboard
4. **Add to .env**:
```env
NEWS_API_KEY=your_newsapi_key_here
```

**Rate Limits**:
- Free tier: 100 requests per day
- Service caches results for 15 minutes to minimize API calls
- Graceful fallback to cached data when rate limit exceeded

### Twitter API Setup

1. **Create a Twitter Developer Account**:
   - Go to https://developer.twitter.com/
   - Apply for developer access (usually approved instantly)

2. **Create a Project and App**:
   - Navigate to Projects & Apps
   - Create a new project
   - Create a new app within the project

3. **Get Bearer Token**:
   - Go to your app's "Keys and tokens" tab
   - Generate a Bearer Token
   - Copy the token (save it securely)

4. **Add to .env**:
```env
TWITTER_BEARER_TOKEN=your_twitter_bearer_token_here
```

**Rate Limits**:
- Essential access (free): 450 requests per 15-minute window
- Elevated access (free, approval required): Same limits with higher monthly caps
- Service caches results for 10 minutes
- Automatic rate limit handling with exponential backoff

### Access Levels Comparison

| Feature | Free NewsAPI | Free Twitter | Notes |
|---------|-------------|--------------|-------|
| Requests/day | 100 | ~43,200 (450/15min) | Twitter much more generous |
| Historical data | 1 month | 7 days | NewsAPI better for history |
| Real-time | Yes | Yes | Both support real-time |
| Caching | 15 min | 10 min | Configured in service |
| Cost | Free | Free | Both have paid tiers |

## API Endpoints

### Health Check
```bash
GET /health
# Returns: {"status": "healthy", "service": "sentiment-analysis-service"}

GET /ready
# Returns: API configuration status

GET /api/v1/stats
# Returns: API usage statistics and cache info
```

### News Sentiment
```bash
GET /api/v1/sentiment/news/BTCUSDT?lookback_hours=24

Response:
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

Response:
{
  "twitter": {
    "symbol": "BTCUSDT",
    "platform": "twitter",
    "total_posts": 87,
    "posts": [...],
    "average_sentiment": 0.32,
    "weighted_sentiment": 0.41,  # Weighted by engagement
    "sentiment_label": "POSITIVE",
    "total_engagement": 15420.0,
    "average_engagement": 177.0
  }
}
```

### Combined Sentiment
```bash
GET /api/v1/sentiment/combined/BTCUSDT

Response:
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
  "analysis_timestamp": "2025-11-11T10:30:00Z",
  "next_update_at": "2025-11-11T10:45:00Z"
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

The service implements intelligent caching to minimize API calls:

**News Caching**:
- TTL: 15 minutes
- Cache size: 100 queries
- Rounds timestamps to nearest 15 minutes for better cache hit rate
- Falls back to stale cache on API failure

**Twitter Caching**:
- TTL: 10 minutes
- Cache size: 100 queries
- Rounds timestamps to nearest 10 minutes
- Falls back to stale cache on API failure

**Sentiment Caching**:
- TTL: Configurable (default 15 minutes)
- In-memory cache for combined sentiment results
- Prevents redundant API calls for same symbol

### Rate Limit Strategy

**Exponential Backoff**:
```python
# Retries: 3 attempts
# Wait times: 2s, 4s, 8s (exponential)
# Only retries on API errors (not on data errors)
```

**Monitoring**:
```bash
# Check API usage stats
curl http://localhost:8008/api/v1/stats

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

The service implements graceful error handling:

1. **API Key Missing**: Falls back to mock data (logs warning)
2. **Rate Limit Exceeded**: Returns stale cached data if available
3. **API Temporarily Down**: Uses mock data with warning log
4. **Network Error**: Retries with exponential backoff
5. **Data Quality Low**: Returns result with "POOR" quality indicator

## Testing

### Without API Keys (Mock Data)
```bash
# Service works without API keys using realistic mock data
uvicorn app.main:app --reload

# Test endpoints
curl http://localhost:8008/api/v1/sentiment/news/BTCUSDT
curl http://localhost:8008/api/v1/sentiment/social/BTCUSDT
curl http://localhost:8008/api/v1/sentiment/combined/BTCUSDT
```

### With Real APIs
```bash
# Add keys to .env
NEWS_API_KEY=real_key_here
TWITTER_BEARER_TOKEN=real_token_here

# Run service
uvicorn app.main:app --reload

# Verify real data
curl http://localhost:8008/api/v1/stats
# Check "api_enabled": true for both APIs
```

### Unit Tests
```bash
# Run tests with mocked APIs
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

## Production Deployment

### Docker Deployment
```bash
# Build image
docker build -t sentiment-analysis-service .

# Run container
docker run -d \
  -p 8008:8008 \
  -e NEWS_API_KEY=your_key \
  -e TWITTER_BEARER_TOKEN=your_token \
  --name sentiment-service \
  sentiment-analysis-service
```

### Performance Tuning
```bash
# Multiple workers for production
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8008 \
  --workers 4 \
  --log-level info
```

### Monitoring
```bash
# Check logs
tail -f logs/sentiment-analysis.log

# Monitor API calls
watch -n 5 'curl -s http://localhost:8008/api/v1/stats | jq'

# Health check
curl http://localhost:8008/health
```

## Troubleshooting

### NewsAPI Issues

**Problem**: "newsapi.newsapi_exception.NewsAPIException: You have exceeded your rate limit"
**Solution**:
- Check usage: `curl http://localhost:8008/api/v1/stats`
- Service will automatically use cached data
- Upgrade to paid plan for higher limits

**Problem**: "No articles found"
**Solution**:
- Check symbol is recognized (BTC, ETH, etc.)
- Extend lookback_hours parameter
- Verify API key is valid

### Twitter API Issues

**Problem**: "tweepy.errors.Unauthorized: 401 Unauthorized"
**Solution**:
- Verify bearer token is correct
- Check token hasn't expired
- Ensure app has read permissions

**Problem**: "Rate limit exceeded"
**Solution**:
- Service automatically waits when rate limited
- Check cache settings (reduce TTL for more caching)
- Consider applying for elevated access

### General Issues

**Problem**: "Sentiment always neutral"
**Solution**:
- Check if FinBERT model is loaded (requires transformers package)
- Verify text contains sentiment keywords
- Try with different symbols/timeframes

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

**Recommendation**: Start with free tiers. With proper caching, free tier is sufficient for most use cases.

## License

MIT License - See LICENSE file for details

## Support

For issues or questions:
- Open GitHub issue
- Check logs: `tail -f logs/sentiment-analysis.log`
- Review API stats: `GET /api/v1/stats`
