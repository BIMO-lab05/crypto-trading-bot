# Quick Start Guide - Sentiment Analysis Service

## 5-Minute Setup

### Option 1: With Real APIs (Recommended for Production)

```bash
# 1. Get API keys (5 minutes)
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
# 1. Install dependencies
cd services/sentiment-analysis-service
pip install -r requirements.txt

# 2. Run service (uses mock data)
uvicorn app.main:app --reload --port 8008

# Service works immediately with realistic mock data!
```

---

## Quick API Test

```bash
# Health check
curl http://localhost:8008/health

# Check which APIs are configured
curl http://localhost:8008/ready | jq

# Get Bitcoin news sentiment
curl "http://localhost:8008/api/v1/sentiment/news/BTCUSDT" | jq

# Get Bitcoin Twitter sentiment
curl "http://localhost:8008/api/v1/sentiment/social/BTCUSDT" | jq

# Get combined sentiment (trading signal)
curl "http://localhost:8008/api/v1/sentiment/combined/BTCUSDT" | jq

# Monitor API usage
curl http://localhost:8008/api/v1/stats | jq
```

---

## API Keys Quick Reference

### NewsAPI
```env
NEWS_API_KEY=your_key_here
```
- **Signup**: https://newsapi.org/register
- **Free**: 100 requests/day
- **Cache**: 15 minutes
- **Cost**: $0 (sufficient for most use cases)

### Twitter API
```env
TWITTER_BEARER_TOKEN=your_token_here
```
- **Signup**: https://developer.twitter.com/
- **Free**: 450 requests per 15 minutes
- **Cache**: 10 minutes
- **Cost**: $0 (very generous limits)

---

## Common Issues

**Issue**: "Service returning mock data"
```bash
# Check if APIs are configured
curl http://localhost:8008/ready | jq '.apis_configured'

# Solution: Add API keys to .env file
```

**Issue**: "Rate limit exceeded"
```bash
# Check current usage
curl http://localhost:8008/api/v1/stats | jq '.news_api.total_api_calls'

# Solution: Service automatically uses cached data
# Or increase cache TTL in .env
```

**Issue**: "No sentiment data"
```bash
# Verify symbol format
# Correct: BTCUSDT, ETHUSDT
# Wrong: BTC-USDT, btc

# Solution: Use standard Bybit format (e.g., BTCUSDT)
```

---

## Environment Variables Cheat Sheet

```env
# Required (optional - service works without them)
NEWS_API_KEY=your_key
TWITTER_BEARER_TOKEN=your_token

# Optional (sensible defaults provided)
SENTIMENT_CACHE_TTL_MINUTES=15
MIN_NEWS_COUNT=3
SENTIMENT_LOOKBACK_HOURS=24
NEWS_WEIGHT=0.4
SOCIAL_WEIGHT=0.3
BULLISH_THRESHOLD=0.6
BEARISH_THRESHOLD=0.4
```

---

## Quick Architecture

```
Request → Cache Check → Real API → Sentiment Analysis → Response
              ↓ Miss       ↓ Fail         ↓
            Real API → Stale Cache → Mock Data
```

---

## Testing Commands

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app

# Run specific test
pytest tests/test_news_fetcher.py -v
```

---

## Docker Quick Start

```bash
# Build
docker build -t sentiment-service .

# Run without API keys (mock data)
docker run -p 8008:8008 sentiment-service

# Run with API keys
docker run -p 8008:8008 \
  -e NEWS_API_KEY=your_key \
  -e TWITTER_BEARER_TOKEN=your_token \
  sentiment-service
```

---

## Useful Endpoints

| Endpoint | Purpose | Example |
|----------|---------|---------|
| `/health` | Service health | Always returns healthy |
| `/ready` | API status | Shows which APIs configured |
| `/api/v1/stats` | Usage stats | Monitor API calls & cache |
| `/api/v1/sentiment/news/{symbol}` | News sentiment | Get news analysis |
| `/api/v1/sentiment/social/{symbol}` | Twitter sentiment | Get tweet analysis |
| `/api/v1/sentiment/combined/{symbol}` | Trading signal | BUY/SELL/HOLD |

---

## Performance Tips

1. **Enable caching**: Default 15 minutes (reduce API calls by ~75%)
2. **Use combined endpoint**: Gets all data in one call
3. **Monitor stats**: Check `/api/v1/stats` for optimization opportunities
4. **Batch requests**: Request multiple symbols in sequence (cache works)
5. **Adjust lookback**: Shorter = faster, longer = more accurate

---

## Support & Resources

- **Full Documentation**: `README.md`
- **Integration Guide**: `API_INTEGRATION_SUMMARY.md`
- **Environment Example**: `.env.example`
- **API Docs**: http://localhost:8008/docs (Swagger UI)
- **Logs**: `logs/sentiment-analysis.log`

---

## Production Checklist

- [ ] Add API keys to `.env`
- [ ] Test with `/ready` endpoint
- [ ] Monitor `/api/v1/stats` for usage
- [ ] Set up log monitoring
- [ ] Configure health checks
- [ ] Review cache TTL settings
- [ ] Test fallback behavior
- [ ] Document API rate limits

---

**Ready to go!** 🚀

The service works out-of-the-box with mock data and seamlessly upgrades to real APIs when keys are added. No code changes required.
