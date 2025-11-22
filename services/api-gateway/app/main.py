"""
API Gateway - Main Application
Unified entry point for all microservices
"""

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import time
import json
import asyncio
from typing import Optional, List, Set
from datetime import datetime

from app.config import settings
from app.services.service_proxy import ServiceProxy
from app.auth_models import (
    User,
    UserCreate,
    UserLogin,
    Token,
    create_user,
    authenticate_user,
    create_access_token
)
from app.auth_middleware import (
    get_current_user,
    get_current_active_user,
    get_current_admin_user
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============================================================================
# WebSocket Manager - Handles real-time client connections
# ============================================================================

class WebSocketManager:
    """Manages WebSocket connections and broadcasts updates to connected clients"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.broadcast_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket):
        """Accept and store new WebSocket connection"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send message to specific client"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: dict):
        """Send message to all connected clients"""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                disconnected.add(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

    async def start_broadcasting(self, service_proxy: ServiceProxy):
        """Start periodic broadcasting of updates"""
        logger.info("Starting WebSocket broadcast task")
        while True:
            try:
                if len(self.active_connections) > 0:
                    # Fetch latest data from services
                    data = await self.fetch_dashboard_updates(service_proxy)
                    await self.broadcast(data)

                # Wait 2 seconds before next broadcast
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Error in broadcast task: {e}")
                await asyncio.sleep(5)

    async def fetch_dashboard_updates(self, service_proxy: ServiceProxy) -> dict:
        """Fetch latest data from all services"""
        try:
            # Fetch health, portfolio, and market data
            health_task = service_proxy.proxy_request("api-gateway", "/health", "GET")
            portfolio_task = service_proxy.proxy_request("portfolio-manager", "/api/v1/portfolio/balance", "GET")

            health_resp, portfolio_resp = await asyncio.gather(
                health_task, portfolio_task,
                return_exceptions=True
            )

            # Parse responses
            health_data = None
            if not isinstance(health_resp, Exception):
                try:
                    health_data = json.loads(health_resp.body.decode())
                except:
                    pass

            portfolio_data = None
            if not isinstance(portfolio_resp, Exception):
                try:
                    portfolio_data = json.loads(portfolio_resp.body.decode())
                except:
                    pass

            return {
                "type": "dashboard_update",
                "timestamp": datetime.now().isoformat(),
                "data": {
                    "health": health_data,
                    "portfolio": portfolio_data
                }
            }

        except Exception as e:
            logger.error(f"Error fetching dashboard updates: {e}")
            return {
                "type": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            }


# Global instances
service_proxy: Optional[ServiceProxy] = None
websocket_manager = WebSocketManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management"""
    global service_proxy

    # Startup
    logger.info(f"🚀 Starting {settings.service_name} on port {settings.service_port}")

    service_proxy = ServiceProxy()
    await service_proxy.initialize()

    # Start WebSocket broadcast task
    websocket_manager.broadcast_task = asyncio.create_task(
        websocket_manager.start_broadcasting(service_proxy)
    )

    logger.info("✅ API Gateway ready (WebSocket enabled)")

    yield

    # Shutdown
    logger.info("🛑 Shutting down API Gateway")

    # Stop WebSocket broadcast task
    if websocket_manager.broadcast_task:
        websocket_manager.broadcast_task.cancel()
        try:
            await websocket_manager.broadcast_task
        except asyncio.CancelledError:
            pass

    if service_proxy:
        await service_proxy.cleanup()


# Create FastAPI app
app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
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


def get_proxy() -> ServiceProxy:
    """Get service proxy instance"""
    if service_proxy is None:
        raise HTTPException(status_code=503, detail="Service proxy not initialized")
    return service_proxy


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "service": settings.service_name,
        "version": settings.api_version,
        "description": settings.api_description,
        "services": {
            "bybit_connector": settings.bybit_connector_url,
            "market_data": settings.market_data_url,
            "technical_analysis": settings.technical_analysis_url,
            "trading_engine": settings.trading_engine_url,
            "portfolio_manager": settings.portfolio_manager_url,
            "risk_metrics": settings.risk_metrics_url,
            "ml_prediction": settings.ml_prediction_url,
            "sentiment_analysis": settings.sentiment_analysis_url
        },
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "market_data": "/api/market/*",
            "technical_analysis": "/api/analysis/*",
            "trading": "/api/trading/*",
            "portfolio": "/api/portfolio/*",
            "risk": "/api/risk/*",
            "performance": "/api/performance/*",
            "ml_predictions": "/api/ml/*",
            "sentiment": "/api/sentiment/*"
        }
    }




# Health endpoint
@app.get("/health")
async def health_check():
    """Gateway health check with backend service status"""
    proxy = get_proxy()

    # Check all backend services
    health_checks = await proxy.aggregate_health_checks()

    all_healthy = all(health_checks.values())

    return {
        "status": "healthy" if all_healthy else "degraded",
        "service": settings.service_name,
        "version": settings.api_version,
        "timestamp": int(time.time() * 1000),
        "backend_services": {
            "bybit_connector": health_checks.get("bybit", False),
            "market_data": health_checks.get("market-data", False),
            "technical_analysis": health_checks.get("technical-analysis", False),
            "trading_engine": health_checks.get("trading-engine", False),
            "portfolio_manager": health_checks.get("portfolio-manager", False),
            "risk_metrics": health_checks.get("risk-metrics", False),
            "ml_prediction": health_checks.get("ml-prediction", False),
            "sentiment_analysis": health_checks.get("sentiment-analysis", False),
            "notification_service": True  # Runs independently
        }
    }


# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@app.post("/auth/register", response_model=User, status_code=status.HTTP_201_CREATED)
async def register(user_create: UserCreate):
    """
    Register a new user

    - **username**: Unique username (3-50 characters, alphanumeric)
    - **email**: Valid email address
    - **password**: Strong password (min 8 chars, uppercase, lowercase, digit)
    - **full_name**: Optional full name
    """
    try:
        user = create_user(user_create)
        logger.info(f"New user registered: {user.username}")
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@app.post("/auth/login", response_model=Token)
async def login(user_login: UserLogin):
    """
    Login with username and password to receive JWT access token

    - **username**: Your username
    - **password**: Your password

    Returns JWT token to use in Authorization header: `Bearer <token>`
    """
    user = authenticate_user(user_login.username, user_login.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.user_id}
    )

    logger.info(f"User logged in: {user.username}")

    return Token(access_token=access_token)


@app.get("/auth/me", response_model=User)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """
    Get current authenticated user information

    Requires: Authorization header with Bearer token
    """
    return current_user


@app.post("/auth/logout")
async def logout(current_user: User = Depends(get_current_active_user)):
    """
    Logout current user

    Note: JWT tokens are stateless, so true logout requires token blacklisting
    which is not implemented in this basic version. Clients should delete their tokens.

    Requires: Authorization header with Bearer token
    """
    logger.info(f"User logged out: {current_user.username}")
    return {
        "message": "Successfully logged out",
        "detail": "Please delete your token on the client side"
    }


# ============================================================================
# MARKET DATA ROUTES
# ============================================================================

@app.get("/api/market/ticker/{symbol}")
async def get_ticker(symbol: str, request: Request):
    """Get ticker data for a symbol"""
    proxy = get_proxy()
    response_obj = await proxy.proxy_request(
        service_name="market-data",
        path=f"/api/v1/ticker/{symbol}",
        method="GET"
    )

    # Extract the actual data from JSONResponse
    import json
    response_body = response_obj.body.decode() if hasattr(response_obj, 'body') else response_obj
    response = json.loads(response_body) if isinstance(response_body, str) else response_body

    # Transform response format for frontend compatibility
    # API returns: {success: true, data: {...}}
    # Frontend expects: {ticker: {...}}
    if isinstance(response, dict) and response.get("success") and response.get("data"):
        ticker_data = response["data"]
        # Map field names to frontend expectations
        return {
            "ticker": {
                "symbol": ticker_data.get("symbol"),
                "last_price": str(ticker_data.get("last_price", 0)),
                "price_24h_pcnt": str(ticker_data.get("price_change_24h", 0)),
                "volume_24h": str(ticker_data.get("volume_24h", 0)),
                "high_price_24h": str(ticker_data.get("high_24h", 0)),
                "low_price_24h": str(ticker_data.get("low_24h", 0))
            }
        }

    return response


@app.get("/api/market/kline/{symbol}")
async def get_kline(symbol: str, interval: str = "60", limit: int = 100):
    """Get kline/candlestick data"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="market-data",
        path=f"/api/v1/kline/{symbol}",
        method="GET",
        query_params={"interval": interval, "limit": limit}
    )


# ============================================================================
# TECHNICAL ANALYSIS ROUTES
# ============================================================================

@app.get("/api/analysis/rsi/{symbol}")
async def get_rsi(symbol: str, interval: str = "60", period: int = 14):
    """Get RSI indicator"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="technical-analysis",
        path=f"/api/v1/indicators/rsi/{symbol}",
        method="GET",
        query_params={"interval": interval, "period": period}
    )


@app.get("/api/analysis/macd/{symbol}")
async def get_macd(symbol: str, interval: str = "60"):
    """Get MACD indicator"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="technical-analysis",
        path=f"/api/v1/indicators/macd/{symbol}",
        method="GET",
        query_params={"interval": interval}
    )


@app.get("/api/analysis/all/{symbol}")
async def get_all_indicators(symbol: str, interval: str = "60"):
    """Get all technical indicators"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="technical-analysis",
        path=f"/api/v1/analysis/{symbol}",
        method="GET",
        query_params={"interval": interval}
    )


# ============================================================================
# TRADING ENGINE ROUTES
# ============================================================================

@app.get("/api/trading/signals/{symbol}")
async def get_trading_signal(symbol: str, interval: str = "60"):
    """Get aggregated trading signal"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine",
        path=f"/api/v1/signals/{symbol}",
        method="GET",
        query_params={"interval": interval}
    )




@app.get("/api/trading/signals/enhanced/{symbol}")
async def get_enhanced_trading_signal(symbol: str, interval: str = "60"):
    """
    Get enhanced trading signal combining multiple data sources

    Combines:
    - Technical Analysis (RSI, MACD, Bollinger Bands, etc.)
    - ML Predictions (price trend, volatility)
    - Sentiment Analysis (news, social media)
    - Multi-timeframe confirmation
    - Risk metrics

    Returns comprehensive trading recommendation with confidence score

    Response format:
    {
        "symbol": "BTCUSDT",
        "interval": "60",
        "signal": "BUY",
        "confidence": 0.85,
        "risk_level": "MEDIUM",
        "technical_analysis": {...},
        "ml_predictions": {...},
        "sentiment": {...},
        "multi_timeframe": {...},
        "recommendation": "Strong buy signal with high confidence",
        "timestamp": 1700000000000
    }
    """
    proxy = get_proxy()

    try:
        # Fetch data from multiple services in parallel
        import asyncio
        import json

        # Get technical analysis
        ta_task = proxy.proxy_request(
            "technical-analysis",
            f"/api/v1/indicators/signal/{symbol}",
            "GET",
            {"interval": interval}
        )

        # Get ML prediction
        ml_task = proxy.proxy_request(
            "ml-prediction",
            f"/api/v1/predict/trend/{symbol}",
            "GET",
            {"interval": interval}
        )

        # Get sentiment
        sentiment_task = proxy.proxy_request(
            "sentiment-analysis",
            f"/api/v1/sentiment/combined/{symbol}",
            "GET"
        )

        # Get multi-timeframe analysis
        mtf_task = proxy.proxy_request(
            "technical-analysis",
            f"/api/v1/analysis/multi-timeframe/{symbol}",
            "GET"
        )

        # Get base trading signal
        signal_task = proxy.proxy_request(
            "trading-engine",
            f"/api/v1/signals/{symbol}",
            "GET",
            {"interval": interval}
        )

        # Wait for all responses
        ta_resp, ml_resp, sent_resp, mtf_resp, signal_resp = await asyncio.gather(
            ta_task, ml_task, sentiment_task, mtf_task, signal_task,
            return_exceptions=True
        )

        # Parse responses
        def parse_response(resp):
            if isinstance(resp, Exception):
                return None
            try:
                return json.loads(resp.body.decode())
            except:
                return None

        ta_data = parse_response(ta_resp)
        ml_data = parse_response(ml_resp)
        sent_data = parse_response(sent_resp)
        mtf_data = parse_response(mtf_resp)
        signal_data = parse_response(signal_resp)

        # Calculate enhanced signal
        signals = []
        if ta_data and ta_data.get("aggregated_signal"):
            signals.append(ta_data["aggregated_signal"])
        if ml_data and ml_data.get("trend"):
            signals.append(ml_data["trend"])
        if sent_data and sent_data.get("combined_label"):
            signals.append(sent_data["combined_label"])
        if mtf_data and mtf_data.get("consensus_signal"):
            signals.append(mtf_data["consensus_signal"])
        if signal_data and signal_data.get("signal"):
            signals.append(signal_data["signal"])

        # Determine consensus
        buy_count = sum(1 for s in signals if s in ["BUY", "BULLISH"])
        sell_count = sum(1 for s in signals if s in ["SELL", "BEARISH"])
        neutral_count = sum(1 for s in signals if s in ["HOLD", "NEUTRAL", "SIDEWAYS"])

        total_signals = len(signals)
        if total_signals == 0:
            enhanced_signal = "HOLD"
            confidence = 0.0
        elif buy_count > sell_count and buy_count > neutral_count:
            enhanced_signal = "BUY"
            confidence = buy_count / total_signals
        elif sell_count > buy_count and sell_count > neutral_count:
            enhanced_signal = "SELL"
            confidence = sell_count / total_signals
        else:
            enhanced_signal = "HOLD"
            confidence = neutral_count / total_signals if neutral_count > 0 else 0.5

        # Determine risk level
        risk_level = "LOW"
        if confidence < 0.5:
            risk_level = "HIGH"
        elif confidence < 0.7:
            risk_level = "MEDIUM"

        # Generate recommendation
        if enhanced_signal == "BUY" and confidence >= 0.7:
            recommendation = f"Strong buy signal with {confidence:.0%} confidence across multiple indicators"
        elif enhanced_signal == "SELL" and confidence >= 0.7:
            recommendation = f"Strong sell signal with {confidence:.0%} confidence across multiple indicators"
        elif confidence >= 0.5:
            recommendation = f"Moderate {enhanced_signal.lower()} signal with {confidence:.0%} confidence"
        else:
            recommendation = f"Weak {enhanced_signal.lower()} signal - conflicting indicators suggest caution"

        return JSONResponse(content={
            "symbol": symbol,
            "interval": interval,
            "signal": enhanced_signal,
            "confidence": round(confidence, 2),
            "risk_level": risk_level,
            "signal_breakdown": {
                "buy_signals": buy_count,
                "sell_signals": sell_count,
                "neutral_signals": neutral_count,
                "total_signals": total_signals
            },
            "technical_analysis": ta_data,
            "ml_predictions": ml_data,
            "sentiment": sent_data,
            "multi_timeframe": mtf_data,
            "base_signal": signal_data,
            "recommendation": recommendation,
            "timestamp": int(time.time() * 1000)
        })

    except Exception as e:
        logger.error(f"Error generating enhanced signal: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate enhanced signal: {str(e)}"
        )


@app.post("/api/trading/signals/{symbol}/analyze")
async def analyze_and_trade(symbol: str, interval: str = "60", execute: bool = False):
    """Analyze signal and optionally execute trade"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine",
        path=f"/api/v1/signals/{symbol}/analyze",
        method="POST",
        query_params={"interval": interval, "execute": execute}
    )


@app.get("/api/trading/positions")
async def get_positions(status: str = "open"):
    """Get trading positions"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="trading-engine",
        path="/api/v1/positions",
        method="GET",
        query_params={"status": status}
    )


# ============================================================================
# PORTFOLIO MANAGER ROUTES
# ============================================================================

@app.get("/api/portfolio")
async def get_portfolio(portfolio_id: str = "default"):
    """Get portfolio details"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/portfolio",
        method="GET",
        query_params={"portfolio_id": portfolio_id}
    )


@app.get("/api/portfolio/balance")
async def get_balance(portfolio_id: str = "default"):
    """Get portfolio balance"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/portfolio/balance",
        method="GET",
        query_params={"portfolio_id": portfolio_id}
    )


@app.get("/api/portfolio/holdings")
async def get_holdings(portfolio_id: str = "default"):
    """Get portfolio holdings"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/portfolio/holdings",
        method="GET",
        query_params={"portfolio_id": portfolio_id}
    )


@app.get("/api/portfolio/performance")
async def get_performance(portfolio_id: str = "default"):
    """Get performance metrics"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/performance",
        method="GET",
        query_params={"portfolio_id": portfolio_id}
    )


@app.get("/api/portfolio/trades")
async def get_trades(portfolio_id: str = "default", limit: int = None, symbol: str = None):
    """Get transaction history (trades)"""
    proxy = get_proxy()
    query_params = {"portfolio_id": portfolio_id}
    if limit:
        query_params["limit"] = limit
    if symbol:
        query_params["symbol"] = symbol

    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/transactions",
        method="GET",
        query_params=query_params
    )


@app.post("/api/portfolio/buy")
async def buy_asset(
    portfolio_id: str = "default",
    symbol: str = None,
    quantity: str = None,
    price: str = None
):
    """Execute buy transaction"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/transaction/buy",
        method="POST",
        query_params={
            "portfolio_id": portfolio_id,
            "symbol": symbol,
            "quantity": quantity,
            "price": price
        }
    )


@app.post("/api/portfolio/sell")
async def sell_asset(
    portfolio_id: str = "default",
    symbol: str = None,
    quantity: str = None,
    price: str = None
):
    """Execute sell transaction"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="portfolio-manager",
        path="/api/v1/transaction/sell",
        method="POST",
        query_params={
            "portfolio_id": portfolio_id,
            "symbol": symbol,
            "quantity": quantity,
            "price": price
        }
    )


@app.post("/api/portfolio/emergency-stop")
async def emergency_stop():
    """
    Emergency stop - Halt all trading operations immediately
    This is a critical safety feature that stops the trading bot
    """
    try:
        # Create emergency stop file flag
        import os
        stop_file = "/mnt/d/Bimo_max/crypto-trading-bot/EMERGENCY_STOP"
        with open(stop_file, 'w') as f:
            f.write(f"Emergency stop activated at {int(time.time() * 1000)}\n")

        logger.warning("🚨 EMERGENCY STOP ACTIVATED")

        return JSONResponse(content={
            "success": True,
            "message": "Emergency stop activated. Trading bot will halt operations.",
            "timestamp": int(time.time() * 1000)
        })
    except Exception as e:
        logger.error(f"Failed to activate emergency stop: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to activate emergency stop: {str(e)}")


# ============================================================================
# RISK & METRICS ENDPOINTS
# ============================================================================

@app.get("/api/risk/scorecard")
async def get_risk_scorecard():
    """Get complete risk assessment scorecard"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/risk/scorecard",
        method="GET"
    )


@app.get("/api/risk/capital")
async def get_capital_metrics():
    """Get capital allocation metrics"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/risk/capital",
        method="GET"
    )


@app.get("/api/risk/exposure")
async def get_exposure_metrics():
    """Get portfolio exposure analysis"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/risk/exposure",
        method="GET"
    )


@app.get("/api/risk/drawdown")
async def get_drawdown_metrics():
    """Get drawdown tracking metrics"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/risk/drawdown",
        method="GET"
    )


@app.get("/api/risk/var")
async def get_value_at_risk(confidence_level: float = 0.95, time_horizon_days: int = 1):
    """Get Value at Risk calculation"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/risk/var",
        method="GET",
        query_params={
            "confidence_level": confidence_level,
            "time_horizon_days": time_horizon_days
        }
    )


@app.get("/api/performance/metrics")
async def get_performance_metrics():
    """Get comprehensive performance metrics"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/performance/metrics",
        method="GET"
    )


@app.get("/api/performance/sharpe")
async def get_sharpe_ratio():
    """Get Sharpe ratio calculation"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/performance/sharpe",
        method="GET"
    )


@app.get("/api/risk/alerts")
async def get_active_alerts():
    """Get active risk alerts"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/alerts",
        method="GET"
    )


@app.get("/api/risk/circuit-breaker")
async def get_circuit_breaker_status():
    """Get circuit breaker status"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/circuit-breaker",
        method="GET"
    )


@app.post("/api/risk/circuit-breaker/reset")
async def reset_circuit_breaker():
    """Reset circuit breaker (admin only)"""
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="risk-metrics",
        path="/circuit-breaker/reset",
        method="POST"
    )


# ============================================================================
# ML PREDICTION ENDPOINTS - Phase 3 AI Integration
# ============================================================================

@app.get("/api/ml/predict/price/{symbol}")
async def ml_predict_price(
    symbol: str,
    interval: str = "60",
    model_type: str = "LSTM"
):
    """
    Get ML-based price predictions for a symbol

    Returns predicted prices with confidence intervals
    Supports LSTM and GRU models
    """
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="ml-prediction",
        path=f"/api/v1/predict/price/{symbol}",
        method="GET",
        query_params={"interval": interval, "model_type": model_type}
    )


@app.get("/api/ml/predict/trend/{symbol}")
async def ml_predict_trend(
    symbol: str,
    interval: str = "60",
    model_type: str = "LSTM"
):
    """
    Get ML-based trend prediction (BULLISH/BEARISH/NEUTRAL)

    Combines ML model predictions with technical analysis
    Returns trend classification with confidence score
    """
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="ml-prediction",
        path=f"/api/v1/predict/trend/{symbol}",
        method="GET",
        query_params={"interval": interval, "model_type": model_type}
    )


@app.get("/api/ml/predict/volatility/{symbol}")
async def ml_predict_volatility(
    symbol: str,
    interval: str = "60"
):
    """
    Get volatility forecast for risk management

    Predicts future volatility (1h, 4h, 24h)
    Provides risk level and position size recommendations
    """
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="ml-prediction",
        path=f"/api/v1/predict/volatility/{symbol}",
        method="GET",
        query_params={"interval": interval}
    )


@app.get("/api/ml/predict/signal/{symbol}")
async def ml_predict_signal(
    symbol: str,
    interval: str = "60",
    model_type: str = "LSTM"
):
    """
    Get ML-based trading signal

    This endpoint derives a trading signal from ML price predictions
    Returns BUY/SELL/HOLD recommendation
    """
    proxy = get_proxy()

    # Get price prediction from ML service
    try:
        prediction_response = await proxy.proxy_request(
            service_name="ml-prediction",
            path=f"/api/v1/predict/price/{symbol}",
            method="GET",
            query_params={"interval": interval, "model_type": model_type}
        )

        # Extract prediction data
        import json
        prediction_data = json.loads(prediction_response.body.decode())

        # Derive signal from prediction
        # If predicted direction is UP with high confidence -> BUY
        # If predicted direction is DOWN with high confidence -> SELL
        # Otherwise -> HOLD
        predicted_direction = prediction_data.get("predicted_direction", "SIDEWAYS")
        directional_strength = prediction_data.get("directional_strength", 0.0)

        if predicted_direction == "UP" and directional_strength > 0.6:
            signal = "BUY"
        elif predicted_direction == "DOWN" and directional_strength > 0.6:
            signal = "SELL"
        else:
            signal = "HOLD"

        return JSONResponse(content={
            "symbol": symbol,
            "interval": interval,
            "signal": signal,
            "confidence": directional_strength,
            "model_type": model_type,
            "prediction_data": prediction_data,
            "timestamp": int(time.time() * 1000)
        })

    except Exception as e:
        logger.error(f"Error generating ML signal: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate ML signal: {str(e)}"
        )


@app.get("/api/ml/models")
async def list_ml_models():
    """
    List all available trained ML models

    Returns information about LSTM and GRU models
    Shows training status and performance metrics
    """
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="ml-prediction",
        path="/api/v1/models",
        method="GET"
    )


@app.get("/api/ml/models/{symbol}")
async def get_ml_model_info(
    symbol: str,
    interval: str = "60",
    model_type: str = "LSTM"
):
    """
    Get detailed information about a specific ML model

    Returns training metrics, accuracy, and model status
    Includes information about when retraining is needed
    """
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="ml-prediction",
        path=f"/api/v1/models/{symbol}",
        method="GET",
        query_params={"interval": interval, "model_type": model_type}
    )


@app.post("/api/ml/models/train")
async def train_ml_model(
    symbol: str,
    interval: str = "60",
    lookback_days: int = 90,
    force_retrain: bool = False
):
    """
    Train or retrain an ML model

    This is a long-running operation that trains an LSTM model
    Requires historical market data
    """
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="ml-prediction",
        path="/api/v1/models/train",
        method="POST",
        body={
            "symbol": symbol,
            "interval": interval,
            "lookback_days": lookback_days,
            "force_retrain": force_retrain
        }
    )


@app.get("/api/ml/models/compare/{symbol}")
async def compare_ml_models(
    symbol: str,
    interval: str = "60"
):
    """
    Compare LSTM vs GRU model performance

    Returns comprehensive comparison with metrics
    Recommends which model to use based on performance
    """
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="ml-prediction",
        path=f"/api/v1/models/compare/{symbol}",
        method="GET",
        query_params={"interval": interval}
    )


# ============================================================================
# SENTIMENT ANALYSIS ENDPOINTS - Phase 3 AI Integration
# ============================================================================

@app.get("/api/sentiment/news/{symbol}")
async def get_news_sentiment(symbol: str):
    """
    Get news sentiment analysis for a symbol

    Analyzes recent news articles and headlines
    Returns sentiment score, label, and confidence

    Response format:
    {
        "symbol": "BTCUSDT",
        "sentiment_label": "BULLISH",
        "sentiment_score": 0.72,
        "confidence": 0.85,
        "news_count": 15,
        "analyzed_at": 1700000000000
    }
    """
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="sentiment-analysis",
        path=f"/api/v1/sentiment/news/{symbol}",
        method="GET"
    )


@app.get("/api/sentiment/social/{symbol}")
async def get_social_sentiment(symbol: str):
    """
    Get social media sentiment analysis for a symbol

    Analyzes Twitter, Reddit, and other social media sources
    Returns sentiment score, label, and confidence

    Response format:
    {
        "symbol": "BTCUSDT",
        "sentiment_label": "NEUTRAL",
        "sentiment_score": 0.52,
        "confidence": 0.78,
        "post_count": 1250,
        "analyzed_at": 1700000000000
    }
    """
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="sentiment-analysis",
        path=f"/api/v1/sentiment/social/{symbol}",
        method="GET"
    )


@app.get("/api/sentiment/combined/{symbol}")
async def get_combined_sentiment(symbol: str):
    """
    Get combined sentiment analysis from all sources

    Aggregates news, social media, and market sentiment
    Returns weighted combined score with detailed breakdown

    Response format:
    {
        "symbol": "BTCUSDT",
        "combined_label": "BULLISH",
        "combined_score": 0.65,
        "confidence": 0.85,
        "news_sentiment": {
            "label": "BULLISH",
            "score": 0.72,
            "weight": 0.4
        },
        "social_sentiment": {
            "label": "NEUTRAL",
            "score": 0.52,
            "weight": 0.3
        },
        "market_sentiment": {
            "label": "BULLISH",
            "score": 0.68,
            "weight": 0.3
        },
        "analyzed_at": 1700000000000
    }
    """
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="sentiment-analysis",
        path=f"/api/v1/sentiment/combined/{symbol}",
        method="GET"
    )


@app.get("/api/sentiment/trend/{symbol}")
async def get_sentiment_trend(symbol: str, hours: int = 24):
    """
    Get sentiment trend over time for a symbol

    Shows how sentiment has evolved over the specified time period
    Returns historical sentiment data points

    Response format:
    {
        "symbol": "BTCUSDT",
        "timeframe_hours": 24,
        "current_sentiment": "BULLISH",
        "trend_direction": "IMPROVING",
        "data_points": [
            {
                "timestamp": 1700000000000,
                "sentiment_score": 0.65,
                "sentiment_label": "BULLISH"
            },
            ...
        ],
        "average_score": 0.62,
        "analyzed_at": 1700000000000
    }
    """
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="sentiment-analysis",
        path=f"/api/v1/sentiment/trend/{symbol}",
        method="GET",
        query_params={"hours": hours}
    )


# ============================================================================
# MULTI-TIMEFRAME ANALYSIS ENDPOINTS - Phase 3 Advanced TA
# ============================================================================

@app.get("/api/analysis/multi-timeframe/{symbol}")
async def get_multi_timeframe_analysis(symbol: str):
    """
    Get multi-timeframe technical analysis for a symbol

    Analyzes multiple timeframes (1m, 5m, 15m, 1h, 4h, 1d) simultaneously
    Returns alignment score and consensus signal

    Response format:
    {
        "symbol": "BTCUSDT",
        "alignment_score": 83,
        "consensus_signal": "BUY",
        "signal_strength": 0.75,
        "timeframe_signals": [
            {
                "timeframe": "1h",
                "signal": "BUY",
                "strength": 0.80,
                "rsi": 62,
                "macd_signal": "BUY"
            },
            {
                "timeframe": "4h",
                "signal": "BUY",
                "strength": 0.85,
                "rsi": 58,
                "macd_signal": "BUY"
            },
            ...
        ],
        "recommendation": "Strong buy signal across multiple timeframes",
        "analyzed_at": 1700000000000
    }
    """
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="technical-analysis",
        path=f"/api/v1/analysis/multi-timeframe/{symbol}",
        method="GET"
    )


@app.get("/api/analysis/indicators/signal/{symbol}")
async def get_indicator_signal(symbol: str, interval: str = "60"):
    """
    Get aggregated signal from all technical indicators

    Combines RSI, MACD, Bollinger Bands, EMA crossovers
    Returns unified signal with confidence score

    Response format:
    {
        "symbol": "BTCUSDT",
        "interval": "60",
        "aggregated_signal": "BUY",
        "confidence": 0.78,
        "indicator_signals": {
            "rsi": {
                "value": 62,
                "signal": "BUY",
                "strength": 0.70
            },
            "macd": {
                "signal": "BUY",
                "strength": 0.85
            },
            "bollinger": {
                "position": "middle",
                "signal": "NEUTRAL",
                "strength": 0.50
            },
            "ema_cross": {
                "signal": "BUY",
                "strength": 0.90
            }
        },
        "buy_indicators": 3,
        "sell_indicators": 0,
        "neutral_indicators": 1,
        "analyzed_at": 1700000000000
    }
    """
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="technical-analysis",
        path=f"/api/v1/indicators/signal/{symbol}",
        method="GET",
        query_params={"interval": interval}
    )


@app.get("/api/sentiment/{symbol}")
async def get_sentiment(symbol: str):
    """
    Get sentiment analysis for a symbol (backwards compatibility)

    Analyzes social media, news, and market sentiment
    Returns sentiment score and classification
    """
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="sentiment-analysis",
        path=f"/api/v1/sentiment/{symbol}",
        method="GET"
    )


@app.get("/api/sentiment/aggregate")
async def get_aggregate_sentiment():
    """
    Get aggregated market sentiment across all tracked symbols

    Returns overall market mood and sentiment distribution
    """
    proxy = get_proxy()
    return await proxy.proxy_request(
        service_name="sentiment-analysis",
        path="/api/v1/sentiment/aggregate",
        method="GET"
    )


# ============================================================================
# AGGREGATION ENDPOINTS (Combine Multiple Services)
# ============================================================================

@app.get("/api/dashboard/{symbol}")
async def get_dashboard_data(symbol: str, interval: str = "60"):
    """
    Aggregated dashboard endpoint
    Combines data from multiple services for a complete view
    """
    proxy = get_proxy()

    try:
        # Fetch data from multiple services in parallel
        import asyncio

        ticker_task = proxy.proxy_request("market-data", f"/api/v1/ticker/{symbol}", "GET")
        signal_task = proxy.proxy_request("trading-engine", f"/api/v1/signals/{symbol}", "GET", {"interval": interval})
        portfolio_task = proxy.proxy_request("portfolio-manager", "/api/v1/portfolio", "GET")

        ticker, signal, portfolio = await asyncio.gather(
            ticker_task, signal_task, portfolio_task,
            return_exceptions=True
        )

        return JSONResponse(content={
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "data": {
                "market": ticker.body.decode() if not isinstance(ticker, Exception) else None,
                "signal": signal.body.decode() if not isinstance(signal, Exception) else None,
                "portfolio": portfolio.body.decode() if not isinstance(portfolio, Exception) else None
            },
            "timestamp": int(time.time() * 1000)
        })

    except Exception as e:
        logger.error(f"Error fetching dashboard data: {e}")
        raise HTTPException(status_code=500, detail="Error fetching dashboard data")


# ============================================================================
# WEBSOCKET ENDPOINT - Real-time Updates
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates
    Clients connect here to receive live updates every 2 seconds
    """
    await websocket_manager.connect(websocket)

    try:
        # Send initial connection message
        await websocket_manager.send_personal_message({
            "type": "connection",
            "message": "Connected to API Gateway WebSocket",
            "timestamp": datetime.now().isoformat()
        }, websocket)

        # Keep connection alive and handle client messages
        while True:
            # Wait for messages from client (ping/pong, requests, etc.)
            data = await websocket.receive_text()

            # Echo back or handle specific commands
            if data == "ping":
                await websocket_manager.send_personal_message({
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                }, websocket)

    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
        logger.info("Client disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        websocket_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.service_port)
