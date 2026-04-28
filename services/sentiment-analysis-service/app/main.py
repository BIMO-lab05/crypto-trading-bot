# SENTIMENT ANALYSIS SERVICE - Main Application
# Analyzes news sentiment, social media sentiment, and market sentiment for cryptocurrencies
# Provides combined sentiment scores for trading decisions
#
# PROMETHEUS METRICS: 2025-12-12
# - Added /metrics endpoint for Prometheus scraping
# - HTTP request counters and histograms
# - Sentiment analysis specific metrics

from fastapi import FastAPI, HTTPException, Path as FastAPIPath, Query, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from contextlib import asynccontextmanager
import logging
import time
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import json
import sys
import os

# Prometheus metrics imports
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client import multiprocess, CollectorRegistry
import os
import tempfile

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

# Import configuration
from app.config import get_settings

# Get settings instance
settings = get_settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/sentiment.log') if os.path.exists('logs') else logging.NullHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import models
from app.models import (
    HealthResponse,
    ReadyResponse,
    NewsArticle,
    NewsSentiment,
    SocialPost,
    SocialSentiment,
    CombinedSentiment,
    SentimentTrend
)

# Import services
from app.analyzers.sentiment_analyzer import SentimentAnalyzer
from app.analyzers.news_fetcher import NewsFetcher
from app.analyzers.twitter_fetcher import TwitterFetcher


# ============================================================================
# PROMETHEUS METRICS
# ============================================================================

# HTTP request counter
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

# HTTP request duration histogram
http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0]
)

# Active requests gauge
http_requests_active = Gauge(
    'http_requests_active',
    'Number of active HTTP requests'
)

# Sentiment-specific metrics
sentiment_analyses_total = Counter(
    'sentiment_analyses_total',
    'Total sentiment analyses performed',
    ['symbol', 'source']
)

news_articles_fetched = Counter(
    'news_articles_fetched',
    'Total news articles fetched',
    ['symbol', 'status']
)

api_calls_total = Counter(
    'api_calls_total',
    'Total external API calls',
    ['provider', 'status']
)

sentiment_analysis_duration = Histogram(
    'sentiment_analysis_duration_seconds',
    'Sentiment analysis duration in seconds',
    ['source'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

cache_size_gauge = Gauge(
    'sentiment_cache_size',
    'Size of sentiment data cache',
    ['cache_type']
)


# Global service instances
sentiment_analyzer: Optional[SentimentAnalyzer] = None
news_fetcher: Optional[NewsFetcher] = None
twitter_fetcher: Optional[TwitterFetcher] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle management
    Initializes services on startup and cleans up on shutdown
    """
    global sentiment_analyzer, news_fetcher, twitter_fetcher

    # Setup multiprocess metrics directory
    temp_dir = tempfile.mkdtemp(prefix="prometheus_multiproc_")
    os.environ['PROMETHEUS_MULTIPROC_DIR'] = temp_dir
    logger.info(f"Prometheus multiprocess directory: {temp_dir}")

    logger.info("Starting sentiment analysis service...")
    logger.info("Prometheus metrics: enabled at /metrics")

    try:
        # Initialize sentiment analyzer
        sentiment_analyzer = SentimentAnalyzer()
        logger.info("Sentiment analyzer initialized")

        # Initialize news fetcher
        news_fetcher = NewsFetcher(
            api_key=settings.news_api_key
        )
        logger.info("News fetcher initialized")

        # Initialize Twitter fetcher
        twitter_fetcher = TwitterFetcher(
            bearer_token=settings.twitter_bearer_token
        )
        logger.info("Twitter fetcher initialized")

        logger.info("Sentiment analysis service ready")

    except Exception as e:
        logger.error(f"Failed to initialize service: {e}", exc_info=True)
        raise

    yield

    logger.info("Shutting down sentiment analysis service...")

    # Cleanup multiprocess metrics
    try:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        if 'PROMETHEUS_MULTIPROC_DIR' in os.environ:
            del os.environ['PROMETHEUS_MULTIPROC_DIR']
    except Exception as e:
        logger.error(f"Error cleaning up multiprocess metrics directory: {e}")


# Create FastAPI application
app = FastAPI(
    title=settings.service_name,
    description="Sentiment analysis service for cryptocurrency trading",
    version=settings.api_version,
    lifespan=lifespan
)


# ============================================================================
# PROMETHEUS METRICS MIDDLEWARE
# ============================================================================

@app.middleware("http")
async def prometheus_metrics_middleware(request: Request, call_next):
    """Middleware to collect Prometheus metrics for all HTTP requests"""
    # Skip metrics endpoint itself
    if request.url.path == "/metrics":
        return await call_next(request)

    method = request.method
    path = request.url.path

    # Normalize path to prevent high cardinality
    import re
    normalized_path = re.sub(r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '/{uuid}', path, flags=re.IGNORECASE)
    normalized_path = re.sub(r'/[A-Z]+USDT', '/{symbol}', normalized_path)

    http_requests_active.inc()
    start_time = time.time()

    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as e:
        status_code = 500
        raise
    finally:
        duration = time.time() - start_time
        http_requests_active.dec()

        http_requests_total.labels(
            method=method,
            endpoint=normalized_path,
            status_code=status_code
        ).inc()

        http_request_duration_seconds.labels(
            method=method,
            endpoint=normalized_path
        ).observe(duration)

    return response


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# PROMETHEUS METRICS ENDPOINT
# ============================================================================

def get_metrics_registry():
    """Get appropriate registry based on multiprocess environment"""
    if 'PROMETHEUS_MULTIPROC_DIR' in os.environ:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return registry
    else:
        return None

@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint"""
    registry = get_metrics_registry()
    if registry:
        data = generate_latest(registry)
    else:
        data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


# ============================================================================
# HEALTH CHECK ENDPOINTS
# ============================================================================

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint

    Returns service health status
    """
    return HealthResponse(
        status="healthy",
        service="sentiment-analysis-service"
    )


@app.get("/ready", response_model=ReadyResponse, tags=["Health"])
async def readiness_check():
    """
    Readiness check endpoint

    Shows which APIs are configured and ready to use
    """
    apis_configured = {
        "news_api": bool(settings.news_api_key),
        "twitter_api": bool(settings.twitter_bearer_token),
        "reddit_api": bool(settings.reddit_client_id and settings.reddit_client_secret),
        "sentiment_analyzer": sentiment_analyzer is not None,
        "news_fetcher": news_fetcher is not None,
        "twitter_fetcher": twitter_fetcher is not None
    }

    # Service is ready if core components are initialized
    is_ready = (sentiment_analyzer is not None and
                news_fetcher is not None and
                twitter_fetcher is not None)

    return ReadyResponse(
        ready=is_ready,
        apis_configured=apis_configured
    )


@app.get("/api/v1/stats", tags=["Health"])
async def get_api_stats():
    """
    Get API usage statistics

    Returns statistics about API calls and cache usage
    """
    # Update cache size metrics
    if news_fetcher:
        cache_size_gauge.labels(cache_type='news').set(len(news_fetcher.news_cache))
    if twitter_fetcher:
        cache_size_gauge.labels(cache_type='twitter').set(len(twitter_fetcher.tweets_cache))

    stats = {
        "service": settings.service_name,
        "uptime_start": datetime.utcnow().isoformat(),
        "news_api": news_fetcher.get_api_stats() if news_fetcher else {},
        "twitter_api": twitter_fetcher.get_api_stats() if twitter_fetcher else {},
        "cache_stats": {
            "news_cache_size": len(news_fetcher.news_cache) if news_fetcher else 0,
            "twitter_cache_size": len(twitter_fetcher.tweets_cache) if twitter_fetcher else 0
        }
    }
    return stats


# ============================================================================
# SENTIMENT ENDPOINTS
# ============================================================================

# Sentiment endpoints
@app.get("/api/v1/sentiment/news/{symbol}", response_model=NewsSentiment, tags=["Sentiment"])
async def get_news_sentiment(
    symbol: str = FastAPIPath(..., description="Trading pair (e.g., BTCUSDT)"),
    lookback_hours: int = Query(24, ge=1, le=168, description="Hours to look back")
):
    """
    Get news sentiment for a symbol

    Fetches recent news from NewsAPI and analyzes sentiment
    Falls back to mock data if API is unavailable
    """
    # Start timer
    start_time = datetime.utcnow()

    try:
        # Convert lookback_hours to int (in case it's still a Query object)
        lookback_hours = int(lookback_hours)

        # Fetch news articles (uses real API if configured, mock data otherwise)
        try:
            articles_data = await news_fetcher.fetch_crypto_news(
                symbol=symbol,
                lookback_hours=lookback_hours,
                max_articles=20
            )
            news_articles_fetched.labels(symbol=symbol, status='success').inc()
            api_calls_total.labels(provider='newsapi', status='success').inc()
        except Exception as e:
            logger.error(f"Error fetching news: {e}")
            news_articles_fetched.labels(symbol=symbol, status='failed').inc()
            api_calls_total.labels(provider='newsapi', status='failed').inc()
            articles_data = []

        if not articles_data:
            # Return neutral sentiment if no news found
            sentiment_analyses_total.labels(symbol=symbol, source='news').inc()
            return NewsSentiment(
                symbol=symbol,
                total_articles=0,
                articles=[],
                average_sentiment=0.0,
                sentiment_label="NEUTRAL",
                positive_count=0,
                negative_count=0,
                neutral_count=0,
                confidence=0.0
            )

        # Analyze sentiment for each article
        articles = []
        sentiment_scores = []

        for article_data in articles_data:
            # Analyze title sentiment
            score, label = sentiment_analyzer.analyze_text(article_data['title'])
            sentiment_scores.append(score)

            article = NewsArticle(
                title=article_data['title'],
                source=article_data['source'],
                url=article_data.get('url'),
                published_at=article_data['published_at'],
                sentiment_score=score,
                sentiment_label=label
            )
            articles.append(article)

        # Calculate aggregated sentiment
        avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.0

        # Get distribution
        distribution = sentiment_analyzer.get_sentiment_distribution(sentiment_scores)

        # Determine overall label
        if avg_sentiment > 0.3:
            sentiment_label = "BULLISH"
        elif avg_sentiment < -0.3:
            sentiment_label = "BEARISH"
        else:
            sentiment_label = "NEUTRAL"

        # Calculate confidence based on agreement
        max_count = max(distribution['positive'], distribution['negative'], distribution['neutral'])
        confidence = max_count / len(sentiment_scores) if sentiment_scores else 0.0

        # Record metrics
        sentiment_analyses_total.labels(symbol=symbol, source='news').inc()
        duration = (datetime.utcnow() - start_time).total_seconds()
        sentiment_analysis_duration.labels(source='news').observe(duration)

        return NewsSentiment(
            symbol=symbol,
            total_articles=len(articles),
            articles=articles,
            average_sentiment=round(avg_sentiment, 3),
            sentiment_label=sentiment_label,
            positive_count=distribution['positive'],
            negative_count=distribution['negative'],
            neutral_count=distribution['neutral'],
            confidence=round(confidence, 2)
        )

    except Exception as e:
        logger.error(f"Failed to analyze news sentiment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to analyze news sentiment: {str(e)}")


@app.get("/api/v1/sentiment/social/{symbol}", response_model=SocialSentiment, tags=["Sentiment"])
async def get_social_sentiment(
    symbol: str = FastAPIPath(..., description="Trading pair (e.g., BTCUSDT)"),
    lookback_hours: int = Query(24, ge=1, le=168, description="Hours to look back")
):
    """
    Get social media sentiment for a symbol

    Analyzes Twitter and Reddit sentiment
    Falls back to mock data if APIs are unavailable
    """
    # Start timer
    start_time = datetime.utcnow()

    try:
        # Convert lookback_hours to int
        lookback_hours = int(lookback_hours)

        # Fetch social data
        try:
            twitter_data = await twitter_fetcher.fetch_crypto_tweets(
                symbol=symbol,
                lookback_hours=lookback_hours,
                max_tweets=100
            )
            api_calls_total.labels(provider='twitter', status='success').inc()
        except Exception as e:
            logger.error(f"Error fetching Twitter data: {e}")
            api_calls_total.labels(provider='twitter', status='failed').inc()
            twitter_data = []

        if not twitter_data:
            sentiment_analyses_total.labels(symbol=symbol, source='social').inc()
            return SocialSentiment(
                symbol=symbol,
                platform="twitter",
                total_posts=0,
                posts=[],
                average_sentiment=0.0,
                weighted_sentiment=0.0,
                sentiment_label="NEUTRAL",
                positive_count=0,
                negative_count=0,
                neutral_count=0,
                total_engagement=0.0,
                average_engagement=0.0
            )

        # Analyze sentiment for tweets
        sentiment_scores = []
        for tweet in twitter_data:
            score, label = sentiment_analyzer.analyze_text(tweet.get('text', ''))
            sentiment_scores.append(score)

        # Calculate aggregated sentiment
        avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.0

        # Get distribution
        distribution = sentiment_analyzer.get_sentiment_distribution(sentiment_scores)

        # Determine overall label
        if avg_sentiment > 0.3:
            sentiment_label = "BULLISH"
        elif avg_sentiment < -0.3:
            sentiment_label = "BEARISH"
        else:
            sentiment_label = "NEUTRAL"

        # Calculate confidence
        max_count = max(distribution['positive'], distribution['negative'], distribution['neutral'])
        confidence = max_count / len(sentiment_scores) if sentiment_scores else 0.0

        # Record metrics
        sentiment_analyses_total.labels(symbol=symbol, source='social').inc()
        duration = (datetime.utcnow() - start_time).total_seconds()
        sentiment_analysis_duration.labels(source='social').observe(duration)

        # Transform twitter data to SocialPost format
        social_posts = []
        total_engagement = 0.0
        for i, post in enumerate(twitter_data[:10]):
            # Get engagement score from the post data
            engagement = post.get('engagement_score', 0.0) or post.get('engagement', 0.0) or 0.0
            total_engagement += engagement

            # Get sentiment from analyzed scores (calculated above)
            post_sentiment = sentiment_scores[i] if i < len(sentiment_scores) else 0.0

            # Get posted time - handle both created_at and posted_at field names
            posted_time = post.get('created_at') or post.get('posted_at')
            if isinstance(posted_time, str):
                try:
                    posted_time = datetime.fromisoformat(posted_time.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    posted_time = datetime.utcnow()
            elif posted_time is None:
                posted_time = datetime.utcnow()

            social_posts.append(SocialPost(
                platform="twitter",
                text=post.get('text', ''),
                author=post.get('author'),
                posted_at=posted_time,
                engagement_score=engagement,
                sentiment_score=round(post_sentiment, 3),
                sentiment_label="POSITIVE" if post_sentiment > 0.1 else ("NEGATIVE" if post_sentiment < -0.1 else "NEUTRAL")
            ))

        avg_engagement = total_engagement / len(social_posts) if social_posts else 0.0

        return SocialSentiment(
            symbol=symbol,
            platform="twitter",
            total_posts=len(twitter_data),
            posts=social_posts,
            average_sentiment=round(avg_sentiment, 3),
            weighted_sentiment=round(avg_sentiment, 3),
            sentiment_label=sentiment_label,
            positive_count=distribution['positive'],
            negative_count=distribution['negative'],
            neutral_count=distribution['neutral'],
            total_engagement=total_engagement,
            average_engagement=avg_engagement
        )

    except Exception as e:
        logger.error(f"Failed to analyze social sentiment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to analyze social sentiment: {str(e)}")


@app.get("/api/v1/sentiment/combined/{symbol}", response_model=CombinedSentiment, tags=["Sentiment"])
async def get_combined_sentiment(
    symbol: str = FastAPIPath(..., description="Trading pair (e.g., BTCUSDT)"),
    lookback_hours: int = Query(24, ge=1, le=168, description="Hours to look back")
):
    """
    Get combined sentiment from all sources

    Aggregates news, social media, and market sentiment
    Provides weighted composite score
    """
    # Start timer
    start_time = datetime.utcnow()

    try:
        # Convert lookback_hours to int
        lookback_hours = int(lookback_hours)

        # Fetch sentiment from all sources in parallel
        import asyncio

        news_task = get_news_sentiment(symbol, lookback_hours)
        social_task = get_social_sentiment(symbol, lookback_hours)

        try:
            news_sentiment, social_sentiment = await asyncio.gather(
                news_task,
                social_task,
                return_exceptions=True
            )
        except Exception as e:
            logger.error(f"Error gathering sentiment data: {e}")
            news_sentiment = None
            social_sentiment = None

        # Weighted average over real sources only. Earlier code added a
        # third "market sentiment" pseudo-source that was hardcoded to a
        # 0.5 (neutral) score with 30% weight — pulling every result
        # toward neutral by 30% even when both news and social agreed
        # strongly. Removed 2026-04-29; restore only with a real market-
        # sentiment input (e.g. funding-rate / open-interest skew).
        # Weights here are nominal (60/40 news/social) — they're
        # normalised by `sum(weights)` so absolute values don't matter,
        # only the ratio.
        scores = []
        weights = []

        if news_sentiment and not isinstance(news_sentiment, Exception):
            normalized_score = (news_sentiment.average_sentiment + 1) / 2
            scores.append(normalized_score)
            weights.append(0.6)

        if social_sentiment and not isinstance(social_sentiment, Exception):
            normalized_score = (social_sentiment.average_sentiment + 1) / 2
            scores.append(normalized_score)
            weights.append(0.4)

        if not scores:
            # Both upstream fetches failed — refuse to fabricate. Earlier
            # behaviour was to fall back to combined_score=0.5 (neutral)
            # and label the source as "market_data", which was a lie.
            raise HTTPException(
                status_code=503,
                detail=(
                    f"No sentiment sources available for {symbol} — both "
                    "news and social fetches failed. Try again later."
                ),
            )

        combined_score = sum(s * w for s, w in zip(scores, weights)) / sum(weights)

        # Normalize back to [-1, 1] for consistency
        combined_sentiment_value = (combined_score * 2) - 1

        # Determine label
        if combined_sentiment_value > 0.3:
            combined_label = "BULLISH"
        elif combined_sentiment_value < -0.3:
            combined_label = "BEARISH"
        else:
            combined_label = "NEUTRAL"

        # Record metrics
        sentiment_analyses_total.labels(symbol=symbol, source='combined').inc()
        duration = (datetime.utcnow() - start_time).total_seconds()
        sentiment_analysis_duration.labels(source='combined').observe(duration)

        # Determine trading signal based on sentiment
        if combined_sentiment_value > 0.3:
            trading_signal = "BUY"
            signal_strength = min(combined_sentiment_value, 1.0)
        elif combined_sentiment_value < -0.3:
            trading_signal = "SELL"
            signal_strength = min(abs(combined_sentiment_value), 1.0)
        else:
            trading_signal = "HOLD"
            signal_strength = 0.3

        # Determine data quality. The "no sources" branch is now
        # unreachable — we 503 above when scores is empty — but kept
        # defensively in case future code adds an optional source.
        sources_used = []
        if news_sentiment and not isinstance(news_sentiment, Exception):
            sources_used.append("news")
        if social_sentiment and not isinstance(social_sentiment, Exception):
            sources_used.append("social")

        if len(sources_used) >= 2:
            data_quality = "EXCELLENT"
        elif len(sources_used) == 1:
            data_quality = "GOOD"
        else:
            data_quality = "POOR"

        return CombinedSentiment(
            symbol=symbol,
            news_sentiment=news_sentiment if not isinstance(news_sentiment, Exception) else None,
            social_sentiment={"twitter": social_sentiment} if social_sentiment and not isinstance(social_sentiment, Exception) else None,
            overall_sentiment=round(combined_sentiment_value, 3),
            sentiment_label=combined_label,
            sentiment_strength=round(abs(combined_sentiment_value), 2),
            confidence=round(abs(combined_sentiment_value), 2),
            data_quality=data_quality,
            trading_signal=trading_signal,
            signal_strength=round(signal_strength, 2),
            sources_used=sources_used,
            analysis_timestamp=datetime.utcnow(),
            next_update_at=datetime.utcnow() + timedelta(minutes=15)
        )

    except Exception as e:
        logger.error(f"Failed to analyze combined sentiment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to analyze combined sentiment: {str(e)}")


@app.get("/api/v1/sentiment/trend/{symbol}", response_model=SentimentTrend, tags=["Sentiment"])
async def get_sentiment_trend(
    symbol: str = FastAPIPath(..., description="Trading pair (e.g., BTCUSDT)"),
    hours: int = Query(24, ge=1, le=168, description="Time period in hours")
):
    """
    Get sentiment trend over time. **Not implemented.**

    Implementation requires persisted historical sentiment data (per-symbol,
    per-bucket). The service does not yet store sentiment snapshots — it
    only computes on-demand from live news/Twitter fetches. Returning 501
    is honest; an earlier version of this endpoint synthesised a fake
    score series (`0.3 + i*0.02` with periodic `-= 0.1`) and dressed it
    up with "trend_direction", "momentum", "volatility" fields. Removed
    2026-04-29 because callers (incl. the dashboard) had no way to know
    those numbers were fiction.

    To re-enable: persist sentiment snapshots (e.g. TimescaleDB hypertable
    keyed by `(symbol, timestamp)`), then bucket and aggregate over the
    requested window.
    """
    raise HTTPException(
        status_code=501,
        detail=(
            "Sentiment trend not implemented — no historical sentiment "
            "data is persisted yet. Use /api/v1/sentiment/combined/{symbol} "
            "for current-window sentiment."
        ),
    )


@app.get("/api/v1/sentiment/{symbol}", tags=["Sentiment"])
async def get_sentiment(
    symbol: str = FastAPIPath(..., description="Trading pair (e.g., BTCUSDT)")
):
    """
    Get sentiment analysis for a symbol (simplified endpoint)

    Returns combined sentiment from all sources
    """
    return await get_combined_sentiment(symbol, 24)


@app.get("/api/v1/sentiment/aggregate", tags=["Sentiment"])
async def get_aggregate_sentiment():
    """
    Get aggregated market sentiment across all tracked symbols. **Not implemented.**

    A real implementation would iterate over the configured symbol list,
    call `get_combined_sentiment` for each (each call hits news + Twitter
    APIs), and tally bullish/bearish/neutral counts. That fan-out is
    expensive (~N × external API latency) and rate-limited per-source,
    so it needs a scheduler that pre-computes and caches aggregate state
    rather than computing on every request. None of that exists yet.

    The earlier version returned hardcoded counts
    (`bullish_count: 12, bearish_count: 10, neutral_count: 18,
    symbols_tracked: 40`) on every call. Removed 2026-04-29.

    To re-enable: add a periodic aggregate-snapshot job (Redis-cached or
    TimescaleDB-backed) and have this endpoint return the latest snapshot.
    """
    raise HTTPException(
        status_code=501,
        detail=(
            "Aggregate market sentiment not implemented — needs a "
            "scheduled fan-out + caching job. Use "
            "/api/v1/sentiment/combined/{symbol} per-symbol meanwhile."
        ),
    )


# ============================================================================
# ROOT ENDPOINT
# ============================================================================

@app.get("/", tags=["Info"])
async def root():
    """Root endpoint with service information"""
    return {
        "service": settings.service_name,
        "version": settings.api_version,
        "status": "running",
        "endpoints": {
            "health": "/health",
            "ready": "/ready",
            "metrics": "/metrics",
            "docs": "/docs",
            "sentiment": {
                "news": "/api/v1/sentiment/news/{symbol}",
                "social": "/api/v1/sentiment/social/{symbol}",
                "combined": "/api/v1/sentiment/combined/{symbol}",
                "trend": "/api/v1/sentiment/trend/{symbol}",
                "aggregate": "/api/v1/sentiment/aggregate"
            }
        },
        "features": {
            "prometheus_metrics": True,
            "news_api": bool(settings.news_api_key),
            "twitter_api": bool(settings.twitter_bearer_token)
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.service_port,
        log_level=settings.log_level.lower()
    )
