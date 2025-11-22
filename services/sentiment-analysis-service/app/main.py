# SENTIMENT ANALYSIS SERVICE - Main Application
# Analyzes news sentiment, social media sentiment, and market sentiment for cryptocurrencies
# Provides combined sentiment scores for trading decisions

from fastapi import FastAPI, HTTPException, Path as FastAPIPath, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import json
import sys
import os

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
    SocialSentiment,
    CombinedSentiment,
    SentimentTrend
)

# Import services
from app.analyzers.sentiment_analyzer import SentimentAnalyzer
from app.analyzers.news_fetcher import NewsFetcher
from app.analyzers.twitter_fetcher import TwitterFetcher

# Import metrics - module not implemented yet
# TODO: Implement metrics module
# from app.metrics import (
#     sentiment_analyses_total,
#     news_articles_fetched,
#     api_calls_total,
#     sentiment_analysis_duration
# )

# Placeholder metrics for now
sentiment_analyses_total = None
news_articles_fetched = None
api_calls_total = None
sentiment_analysis_duration = None

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

    logger.info("Starting sentiment analysis service...")

    try:
        # Initialize sentiment analyzer
        sentiment_analyzer = SentimentAnalyzer()
        logger.info("Sentiment analyzer initialized")

        # Initialize news fetcher
        news_fetcher = NewsFetcher(
            api_key=settings.news_api_key,
            cache_ttl=settings.cache_ttl
        )
        logger.info("News fetcher initialized")

        # Initialize Twitter fetcher
        twitter_fetcher = TwitterFetcher(
            bearer_token=settings.twitter_bearer_token,
            cache_ttl=settings.cache_ttl
        )
        logger.info("Twitter fetcher initialized")

        logger.info("Sentiment analysis service ready")

    except Exception as e:
        logger.error(f"Failed to initialize service: {e}", exc_info=True)
        raise

    yield

    logger.info("Shutting down sentiment analysis service...")


# Create FastAPI application
app = FastAPI(
    title=settings.service_name,
    description="Sentiment analysis service for cryptocurrency trading",
    version=settings.api_version,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    stats = {
        "service": settings.service_name,
        "uptime_start": datetime.utcnow().isoformat(),
        "news_api": news_fetcher.get_api_stats() if news_fetcher else {},
        "twitter_api": twitter_fetcher.get_api_stats() if twitter_fetcher else {},
        "cache_stats": {
            "news_cache_size": len(news_fetcher.news_cache) if news_fetcher else 0,
            "twitter_cache_size": len(twitter_fetcher.twitter_cache) if twitter_fetcher else 0
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
            # Metrics disabled for now - module not implemented
            # news_articles_fetched.labels(symbol=symbol, status='success').inc()
            # api_calls_total.labels(provider='newsapi', status='success').inc()
        except Exception as e:
            logger.error(f"Error fetching news: {e}")
            # news_articles_fetched.labels(symbol=symbol, status='failed').inc()
            # api_calls_total.labels(provider='newsapi', status='failed').inc()
            articles_data = []

        if not articles_data:
            # Return neutral sentiment if no news found
            # sentiment_analyses_total.labels(symbol=symbol, source='news').inc()
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
        # sentiment_analyses_total.labels(symbol=symbol, source='news').inc()
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
                limit=100
            )
            api_calls_total.labels(provider='twitter', status='success').inc()
        except Exception as e:
            logger.error(f"Error fetching Twitter data: {e}")
            api_calls_total.labels(provider='twitter', status='failed').inc()
            twitter_data = []

        if not twitter_data:
            # sentiment_analyses_total.labels(symbol=symbol, source='social').inc()
            return SocialSentiment(
                symbol=symbol,
                total_posts=0,
                posts=[],
                average_sentiment=0.0,
                sentiment_label="NEUTRAL",
                positive_count=0,
                negative_count=0,
                neutral_count=0,
                confidence=0.0,
                data_sources=['twitter', 'reddit']
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
        # sentiment_analyses_total.labels(symbol=symbol, source='social').inc()
        duration = (datetime.utcnow() - start_time).total_seconds()
        sentiment_analysis_duration.labels(source='social').observe(duration)

        return SocialSentiment(
            symbol=symbol,
            total_posts=len(twitter_data),
            posts=twitter_data[:10],  # Return top 10
            average_sentiment=round(avg_sentiment, 3),
            sentiment_label=sentiment_label,
            positive_count=distribution['positive'],
            negative_count=distribution['negative'],
            neutral_count=distribution['neutral'],
            confidence=round(confidence, 2),
            data_sources=['twitter']
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

        # Calculate weighted average
        scores = []
        weights = []

        if news_sentiment and not isinstance(news_sentiment, Exception):
            # Normalize sentiment score from [-1, 1] to [0, 1]
            normalized_score = (news_sentiment.average_sentiment + 1) / 2
            scores.append(normalized_score)
            weights.append(0.4)  # 40% weight for news

        if social_sentiment and not isinstance(social_sentiment, Exception):
            # Normalize sentiment score
            normalized_score = (social_sentiment.average_sentiment + 1) / 2
            scores.append(normalized_score)
            weights.append(0.3)  # 30% weight for social

        # Add market sentiment (default neutral for now)
        scores.append(0.5)  # Neutral market sentiment
        weights.append(0.3)  # 30% weight for market

        # Calculate weighted average
        if scores:
            combined_score = sum(s * w for s, w in zip(scores, weights)) / sum(weights)
        else:
            combined_score = 0.5

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
        # sentiment_analyses_total.labels(symbol=symbol, source='combined').inc()
        duration = (datetime.utcnow() - start_time).total_seconds()
        sentiment_analysis_duration.labels(source='combined').observe(duration)

        return CombinedSentiment(
            symbol=symbol,
            combined_label=combined_label,
            combined_score=round(combined_sentiment_value, 3),
            confidence=round(abs(combined_sentiment_value), 2),
            news_sentiment=news_sentiment if not isinstance(news_sentiment, Exception) else None,
            social_sentiment=social_sentiment if not isinstance(social_sentiment, Exception) else None,
            market_sentiment={
                "label": "NEUTRAL",
                "score": 0.0,
                "weight": 0.3
            },
            analyzed_at=datetime.utcnow().isoformat(),
            analysis_duration_ms=round(duration * 1000)
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
    Get sentiment trend over time

    Shows how sentiment has evolved
    Useful for identifying trend changes
    """
    try:
        # Convert hours to int
        hours = int(hours)

        # Generate sample trend data
        data_points = []
        now = datetime.utcnow()
        interval = timedelta(hours=hours / 24)  # Divide into 24 points

        for i in range(24):
            timestamp = now - interval * (24 - i)
            # Simulate trend data
            score = 0.3 + (i * 0.02)  # Gradually increasing trend
            if i % 3 == 0:
                score -= 0.1  # Add some volatility

            if score > 0.3:
                label = "BULLISH"
            elif score < -0.3:
                label = "BEARISH"
            else:
                label = "NEUTRAL"

            data_points.append({
                "timestamp": timestamp.isoformat(),
                "sentiment_score": round(score, 3),
                "sentiment_label": label
            })

        # Determine trend direction
        if len(data_points) >= 2:
            trend_direction = "IMPROVING" if data_points[-1]["sentiment_score"] > data_points[0]["sentiment_score"] else "DECLINING"
        else:
            trend_direction = "STABLE"

        # Calculate average
        avg_score = sum(p["sentiment_score"] for p in data_points) / len(data_points) if data_points else 0.0

        # sentiment_analyses_total.labels(symbol=symbol, source='trend').inc()

        return SentimentTrend(
            symbol=symbol,
            timeframe_hours=hours,
            current_sentiment=data_points[-1]["sentiment_label"] if data_points else "NEUTRAL",
            trend_direction=trend_direction,
            data_points=data_points,
            average_score=round(avg_score, 3),
            analyzed_at=datetime.utcnow().isoformat()
        )

    except Exception as e:
        logger.error(f"Failed to get sentiment trend: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get sentiment trend: {str(e)}")


@app.get("/api/v1/sentiment/{symbol}", tags=["Sentiment"])
async def get_sentiment(
    symbol: str = FastAPIPath(..., description="Trading pair (e.g., BTCUSDT)")
):
    """
    Get sentiment analysis for a symbol (simplified endpoint)

    Returns combined sentiment from all sources
    """
    return await get_combined_sentiment(symbol)


@app.get("/api/v1/sentiment/aggregate", tags=["Sentiment"])
async def get_aggregate_sentiment():
    """
    Get aggregated market sentiment

    Returns overall market sentiment across all tracked symbols
    """
    try:
        # Sample aggregate data
        return {
            "market_sentiment": "NEUTRAL",
            "bullish_count": 12,
            "bearish_count": 10,
            "neutral_count": 18,
            "symbols_tracked": 40,
            "last_updated": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get aggregate sentiment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get aggregate sentiment: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.service_port,
        log_level=settings.log_level.lower()
    )
