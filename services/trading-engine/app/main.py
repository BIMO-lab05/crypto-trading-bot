"""
Trading Engine Service - FastAPI Application
Purpose: Core trading decision-making and execution service

REFACTORED: Phase 3 Complete - Using modular handlers
Architecture: main.py -> handlers -> services -> domain

NEW: SQZMOM Strategy Integration (2025-11-20)
NEW: Portfolio Correlation Analysis (2025-12-11) - Phase 3.1
NEW: Kelly Position Sizing (2025-12-11) - Phase 3.2
NEW: Dynamic Risk Budgeting (2025-12-12) - Phase 3.3
NEW: Smart Order Routing (2025-12-11) - Phase 4.1
NEW: TWAP/VWAP Execution (2025-12-12) - Phase 4.2
NEW: Attribution Analysis (2025-12-11) - Phase 5.1

PROMETHEUS METRICS: 2025-12-12
- Added /metrics endpoint for Prometheus scraping
- HTTP request counters and histograms
- Trading-specific business metrics

VERSION: 3.7.0 - Phase 3.3 Dynamic Risk Budget Integration
"""

import logging
import time
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Query, Request
from fastapi.responses import Response
from typing import Optional, List, Dict

from fastapi.middleware.cors import CORSMiddleware

# Prometheus metrics imports
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

from app.config import get_settings
from app.position_manager import get_position_manager
from app.models import (
    HealthResponse,
    StatusResponse,
    SignalResponse,
    PositionListResponse,
    PositionResponse,
    PerformanceResponse,
    TradingControlResponse,
    TradeHistoryResponse,
)

# Import all handler functions (Phase 3: Modular architecture)
from app.handlers import (
    health_check,
    get_status,
    get_detailed_health,
    get_trading_signal,
    get_enhanced_trading_signal,  # NEW: Enhanced ML prediction integration
    analyze_and_trade,
    get_positions,
    get_position,
    get_performance,
    start_trading,
    stop_trading,
    get_auto_trading_status,
    get_phase1_metrics_endpoint,
    get_phase1_health,
    get_latest_phase1_signal,
    get_trade_history,
    # Backtesting
    list_strategies,
    run_backtest,
    get_backtest_quick_run,
    compare_strategies,
    get_equity_curve,
    BacktestRequest,
    # Statistical Arbitrage (Phase 2.2)
    initialize_stat_arb_manager,
    add_pairs_strategy,
    calibrate_pairs_strategy,
    add_funding_strategy,
    setup_triangular_arbitrage,
    generate_stat_arb_signals,
    get_stat_arb_performance,
    get_stat_arb_status,
    reset_stat_arb_manager,
    # Correlation Analysis (Phase 3.1)
    get_correlation_status,
    get_correlation_matrix,
    get_diversification_score,
    get_pair_correlation,
    get_correlation_alerts,
    check_can_open_position,
    update_correlations,
    kelly_router,
    # Dynamic Risk Budget Router (Phase 3.3)
    risk_budget_router,
    # Smart Order Routing Router (Phase 4.1)
    execution_router,
    # TWAP/VWAP Execution Router (Phase 4.2)
    twap_vwap_router,
    # Attribution Analysis Router (Phase 5.1)
    attribution_router,
    # Advanced Performance Metrics Router (Phase 5.2)
    analytics_router,
    analytics_report_router,
    # Performance Dashboard Router (Phase 5.3) — equity-curve, drawdown,
    # returns-distribution, correlations, statistics endpoints used by the
    # Performance frontend page. Was defined but never mounted; added
    # 2026-05-01 alongside gateway proxy routes.
    performance_dashboard_router,
)

# Import SQZMOM strategy (NEW)
from app.strategies import sqzmom_strategy, sqzmom_config

# Import Grid Trading router (Phase 2.3)
from app.handlers.grid_trading import router as grid_trading_router

# Import Multi-Strategy Orchestration router (Phase 9). Was defined in
# handlers/orchestration.py but never actually mounted — every endpoint
# under /api/v1/orchestrator/* (incl. emergency-stop, risk/utilization,
# strategies/*) was dead. Wired up 2026-04-29.
from app.handlers.orchestration import router as orchestration_router

# Import Correlation Manager (Phase 3.1)

# Import Kelly Sizer (Phase 3.2)

# Import Dynamic Risk Budget Manager (Phase 3.3)

# Import Smart Router (Phase 4.1)

# Import Execution Scheduler (Phase 4.2)

# Import Attribution Analyzer (Phase 5.1)

# Lifespan phase context managers (refactored 2026-05-01 — split fat lifespan
# into 4 composed @asynccontextmanager phases, see app/lifespan/__init__.py)
from app.lifespan import init_data, init_ml, init_risk, init_strategy

# Backward-compat re-exports for tests that patch `app.main.<symbol>`. These
# symbols moved into app/lifespan/* during the 2026-05-01 refactor; the F401
# noqa keeps autoflake from stripping them. Removing any line here will break
# tests that monkeypatch the lifespan dependencies via the main module.
from app.database.connection import db_manager  # noqa: F401
from app.signal_aggregator import get_aggregator  # noqa: F401
from app.repositories import get_portfolio_repository  # noqa: F401
from app.paper_trading import get_paper_engine  # noqa: F401

# Fixed: Create logs directory to prevent startup crashes (Critical Issue #1)
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Settings
settings = get_settings()

# Version constant for Phase 3.3 enhancements
VERSION = "3.7.0"


# ============================================================================
# PROMETHEUS METRICS
# ============================================================================

# HTTP request counter
http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status_code"]
)

# HTTP request duration histogram
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0],
)

# Active requests gauge
http_requests_active = Gauge("http_requests_active", "Number of active HTTP requests")

# Trading-specific metrics
trades_executed_total = Counter(
    "trades_executed_total", "Total trades executed", ["symbol", "side", "status"]
)

signals_generated_total = Counter(
    "signals_generated_total",
    "Total trading signals generated",
    ["symbol", "signal_type"],
)

open_positions_gauge = Gauge(
    "open_positions_total", "Number of open positions", ["symbol"]
)

portfolio_value_gauge = Gauge("portfolio_value_usd", "Total portfolio value in USD")

total_pnl_gauge = Gauge("total_pnl_usd", "Total realized P&L in USD")

auto_trader_status = Gauge(
    "auto_trader_running", "Auto trader running status (1=running, 0=stopped)"
)

database_health = Gauge(
    "database_connection_health", "Database connection health (1=healthy, 0=unhealthy)"
)

ta_service_health = Gauge(
    "technical_analysis_service_health",
    "Technical Analysis service health (1=healthy, 0=unhealthy)",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    logger.info(
        f"Starting {settings.service_name} v{VERSION} on port {settings.service_port}"
    )
    logger.info(f"Trading Mode: {settings.trading_mode}")
    logger.info(f"Auto Trading: {settings.auto_trading_enabled}")
    logger.info("Prometheus metrics: enabled at /metrics")

    # Defense-in-depth: refuse to boot in LIVE mode without an explicit
    # operator ack. CLAUDE.md mandates a deliberate three-flag flip
    # (PAPER_TRADING_MODE=false + TRADING_MODE=LIVE + mainnet trade-permission
    # keys). The ack env var is a fourth gate to catch silent env drift on
    # cloud hosts where a forgotten value might otherwise reach prod.
    import os

    if settings.trading_mode == "LIVE":
        ack = os.environ.get("LIVE_TRADING_ACK", "")
        if ack != "I_UNDERSTAND_REAL_MONEY":
            raise RuntimeError(
                "Refusing to boot: TRADING_MODE=LIVE without "
                "LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY. "
                "Set the ack env var explicitly to authorize live trading."
            )
        logger.critical("LIVE trading mode acknowledged via LIVE_TRADING_ACK")

    # 4 phase context managers run in order on enter, reverse on exit (cm stack
    # semantics). Auto-trader start/stop stays OUTSIDE the phases — gated on
    # settings.auto_trading_enabled + EMERGENCY_STOP file (both off-switches).
    async with init_data(), init_ml(), init_strategy(), init_risk():
        # AUTO-START gate. Two off-switches block lifespan auto-start, in order:
        #   1. settings.auto_trading_enabled=False — operator says "don't auto-start
        #      at boot" (default). The /start API endpoint still works for manual
        #      operator control; this only governs the on-boot auto-start.
        #   2. EMERGENCY_STOP file present — strong "halt now" signal from the
        #      operator-side kill switch. Uses is_file() (not exists()) to handle
        #      the WSL bind-mount edge case where Docker may create a directory at
        #      the mount point if the host file is absent.
        auto_trader = None
        stop_file = Path(settings.emergency_stop_file)
        if not settings.auto_trading_enabled:
            logger.warning("=" * 60)
            logger.warning(
                "AUTO_TRADING_ENABLED=false — auto-trader will NOT auto-start"
            )
            logger.warning("Use the /start API endpoint to start manually.")
            logger.warning("=" * 60)
            auto_trader_status.set(0)
        elif stop_file.is_file():
            logger.critical("=" * 60)
            logger.critical(f"EMERGENCY_STOP file present at {stop_file}")
            logger.critical(
                "REFUSING to start auto-trader. Delete the file to re-enable."
            )
            logger.critical("=" * 60)
            auto_trader_status.set(0)
        else:
            try:
                from app.auto_trader import get_auto_trader

                auto_trader = get_auto_trader()
                await auto_trader.start()
                auto_trader_status.set(1)
                logger.info("=" * 60)
                logger.info("AUTO TRADER STARTED AUTOMATICALLY")
                logger.info(f"   Trading symbols: {auto_trader.symbols}")
                logger.info(f"   Check frequency: {auto_trader.check_frequency}s")
                logger.info(f"   Strategy mode: {auto_trader.strategy_mode.value}")
                logger.info("   Bot is now ACTIVE and monitoring markets!")
                logger.info("=" * 60)
            except Exception as e:
                logger.error(f"Failed to auto-start trading: {e}")
                auto_trader_status.set(0)

        try:
            yield
        finally:
            logger.info("Shutting down Trading Engine Service")
            if auto_trader is not None:
                try:
                    if auto_trader.is_running:
                        await auto_trader.stop()
                        auto_trader_status.set(0)
                        logger.info("Auto Trader stopped")
                except Exception as e:
                    logger.error(f"Error stopping auto trader: {e}")


# FastAPI app
app = FastAPI(
    title="Trading Engine Service",
    description="Core trading decision-making and execution service with Phase 3-5 enhancements: "
    "Correlation Analysis, Kelly Position Sizing, Dynamic Risk Budgeting, "
    "Smart Order Routing, TWAP/VWAP Execution, and Attribution Analysis",
    version=VERSION,
    lifespan=lifespan,
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
    normalized_path = re.sub(
        r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "/{uuid}",
        path,
        flags=re.IGNORECASE,
    )
    normalized_path = re.sub(r"/[A-Z]+USDT", "/{symbol}", normalized_path)

    http_requests_active.inc()
    start_time = time.time()

    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        status_code = 500
        raise
    finally:
        duration = time.time() - start_time
        http_requests_active.dec()

        http_requests_total.labels(
            method=method, endpoint=normalized_path, status_code=status_code
        ).inc()

        http_request_duration_seconds.labels(
            method=method, endpoint=normalized_path
        ).observe(duration)

    return response


# SECURITY HARDENING (2025-12-12): Strict CORS configuration
# Use configured origins from settings instead of wildcard
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.all_cors_origins,  # No wildcards - use configured origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=[
        "Accept",
        "Accept-Language",
        "Authorization",
        "Content-Language",
        "Content-Type",
        "Origin",
        "X-Requested-With",
        "X-Request-ID",
    ],
    expose_headers=[
        "X-Request-ID",
    ],
    max_age=600,  # 10 minutes preflight cache
)

# ============================================================================
# INCLUDE API ROUTERS (Phase 2.3 - 5.1)
# ============================================================================

# Include Grid Trading router (Phase 2.3 - Grid Trading Integration)
app.include_router(grid_trading_router)

# Include Multi-Strategy Orchestration router (Phase 9)
app.include_router(orchestration_router)

# Include Kelly Position Sizing router (Phase 3.2)
app.include_router(kelly_router)

# Include Dynamic Risk Budget router (Phase 3.3)
app.include_router(risk_budget_router)

# Include Smart Order Routing router (Phase 4.1)
app.include_router(execution_router)

# Include TWAP/VWAP Execution router (Phase 4.2)
app.include_router(twap_vwap_router)

# Include Attribution Analysis router (Phase 5.1)
app.include_router(attribution_router)

# Include Advanced Performance Metrics router (Phase 5.2)
app.include_router(analytics_router)
app.include_router(analytics_report_router)

# Include Performance Dashboard router (Phase 5.3). Provides
# /api/v1/trading/{equity-curve,drawdown,returns-distribution,
# correlations,statistics} consumed by the frontend Performance page.
# Was defined in handlers/performance_dashboard.py but never mounted —
# same shape as the orchestration-router fix in commit 4a158e2.
app.include_router(performance_dashboard_router)


# ============================================================================
# PROMETHEUS METRICS ENDPOINT
# ============================================================================


@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ============================================================================
# HEALTH ENDPOINTS
# ============================================================================


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health():
    """Health check endpoint"""
    return await health_check()


@app.get("/status", response_model=StatusResponse, tags=["Status"])
async def status():
    """Get trading engine status"""
    return await get_status()


@app.get("/health/detailed", tags=["Health"])
async def detailed_health():
    """
    Get detailed health status with all metrics

    Returns comprehensive health report including:
    - All dependency statuses (PostgreSQL, Redis, external APIs)
    - System resource metrics (CPU, memory, disk)
    - Response time metrics
    - Failure counts
    """
    return await get_detailed_health()


# ============================================================================
# SIGNAL ENDPOINTS
# ============================================================================


@app.get("/api/v1/signals/{symbol}", response_model=SignalResponse, tags=["Signals"])
async def signal_endpoint(symbol: str, interval: str = "60"):
    """
    Get trading signal for a symbol

    Fetches all technical indicators and aggregates them into a trading signal.
    """
    signals_generated_total.labels(symbol=symbol, signal_type="aggregated").inc()
    return await get_trading_signal(symbol, interval)


@app.get(
    "/api/v1/signals/enhanced/{symbol}", response_model=SignalResponse, tags=["Signals"]
)
async def enhanced_signal_endpoint(symbol: str, interval: str = "60"):
    """
    Get ENHANCED trading signal with ML predictions for 5-10% win rate improvement

    Combines:
    - Technical Analysis: 30% weight
    - ML Predictions: 35% weight (enhanced with ensemble)
    - Sentiment Analysis: 15% weight
    - Market Regime: 10% weight
    - Risk Adjustment: 10% weight

    Target: 5-10% improvement in win rate through better signal quality
    """
    signals_generated_total.labels(symbol=symbol, signal_type="enhanced").inc()
    return await get_enhanced_trading_signal(symbol, interval)


@app.post(
    "/api/v1/signals/{symbol}/analyze", response_model=SignalResponse, tags=["Signals"]
)
async def analyze_endpoint(symbol: str, interval: str = "60", execute: bool = False):
    """
    Analyze signal and optionally execute trade

    Args:
        symbol: Trading symbol
        interval: Candlestick interval
        execute: If True, will execute trade based on signal
    """
    return await analyze_and_trade(symbol, interval, execute)


# ============================================================================
# POSITION ENDPOINTS
# ============================================================================


@app.get("/api/v1/positions", response_model=PositionListResponse, tags=["Positions"])
async def positions_endpoint(status: str = "all"):
    """
    Get positions

    Args:
        status: Filter by status (all, open, closed)
    """
    return await get_positions(status)


@app.get(
    "/api/v1/positions/{position_id}",
    response_model=PositionResponse,
    tags=["Positions"],
)
async def position_endpoint(position_id: str):
    """Get specific position by ID"""
    return await get_position(position_id)


@app.post("/api/v1/positions/update-tp-levels", tags=["Positions"])
async def update_tp_levels_endpoint():
    """
    Update all open positions with calculated TP1/TP2/TP3 levels

    For positions that don't have partial take profit levels set,
    calculate them based on the risk distance (entry to stop loss).

    Returns:
        Number of positions updated
    """
    from app.position_manager import get_position_manager

    position_mgr = get_position_manager()
    updated = position_mgr.update_positions_with_tp_levels()
    return {
        "success": True,
        "updated_positions": updated,
        "message": f"Updated {updated} positions with TP1/TP2/TP3 levels",
    }


# ============================================================================
# PERFORMANCE ENDPOINTS
# ============================================================================


@app.get(
    "/api/v1/performance", response_model=PerformanceResponse, tags=["Performance"]
)
async def performance_endpoint():
    """Get performance metrics"""
    return await get_performance()


# ============================================================================
# TRADE HISTORY ENDPOINTS
# ============================================================================


@app.get(
    "/api/v1/trades/history",
    response_model=TradeHistoryResponse,
    tags=["Trade History"],
)
async def trade_history_endpoint(limit: int = 50):
    """
    Get trade history with statistics

    Returns closed trades with win/loss stats including:
    - Win rate percentage
    - Total realized P&L
    - Average win/loss
    - Best/worst trade
    - Profit factor

    Args:
        limit: Maximum number of trades to return (default 50)
    """
    return await get_trade_history(limit)


# ============================================================================
# TRADING CONTROL ENDPOINTS
# ============================================================================


@app.post(
    "/api/v1/trading/start",
    response_model=TradingControlResponse,
    tags=["Trading Control"],
)
async def trading_start_endpoint():
    """
    Start automated trading loop

    The auto trader will:
    - Check signals every 5 minutes (configurable)
    - Execute trades when signal meets requirements
    - Apply risk management rules
    - Track all trades and performance
    """
    result = await start_trading()
    auto_trader_status.set(1)
    return result


@app.post(
    "/api/v1/trading/stop",
    response_model=TradingControlResponse,
    tags=["Trading Control"],
)
async def trading_stop_endpoint():
    """Stop automated trading loop"""
    result = await stop_trading()
    auto_trader_status.set(0)
    return result


@app.get("/api/v1/trading/status", tags=["Trading Control"])
async def trading_status_endpoint():
    """
    Get automated trading status and statistics

    Returns:
        Current status, symbols being traded, check frequency, and execution statistics
    """
    return await get_auto_trading_status()


# ============================================================================
# PHASE 1 METRICS ENDPOINTS
# ============================================================================


@app.get("/api/v1/phase1/metrics", tags=["Phase 1"])
async def phase1_metrics_endpoint(hours: int = 24):
    """
    Get Phase 1 performance metrics

    Args:
        hours: Number of hours to analyze (default: 24)

    Returns:
        Phase 1 metrics including filtering rates, GATEKEEPER/VALIDATOR stats
    """
    return await get_phase1_metrics_endpoint(hours)


@app.get("/api/v1/phase1/health", tags=["Phase 1"])
async def phase1_health_endpoint():
    """Get Phase 1 system health status"""
    return await get_phase1_health()


@app.get("/api/v1/phase1/latest", tags=["Phase 1"])
async def phase1_latest_endpoint():
    """Get the most recent Phase 1 signal"""
    return await get_latest_phase1_signal()


# ============================================================================
# CORRELATION ANALYSIS ENDPOINTS (Phase 3.1)
# ============================================================================


@app.get("/api/v1/risk/correlation", tags=["Risk - Correlation"])
async def correlation_matrix_endpoint():
    """
    Get the current correlation matrix for all trading pairs

    Returns correlation coefficients between all tracked symbols,
    including both short-term (30-day) and long-term (60-day) correlations.

    Returns:
        Correlation matrix with highly correlated pairs highlighted
    """
    return await get_correlation_matrix()


@app.get("/api/v1/risk/correlation/status", tags=["Risk - Correlation"])
async def correlation_status_endpoint():
    """
    Get correlation manager status

    Returns:
        Manager status including initialization state, tracked symbols,
        and configuration parameters
    """
    return await get_correlation_status()


@app.get("/api/v1/risk/correlation/score", tags=["Risk - Correlation"])
async def diversification_score_endpoint(
    symbols: Optional[str] = Query(
        default=None,
        description="Comma-separated list of symbols (uses open positions if not provided)",
    ),
):
    """
    Get portfolio diversification score (0-100)

    Score interpretation:
    - 90-100: Excellent diversification
    - 70-89: Good diversification
    - 50-69: Moderate diversification
    - 30-49: Poor diversification
    - 0-29: High concentration risk

    Args:
        symbols: Comma-separated list of symbols (optional, uses open positions if not provided)

    Returns:
        Diversification score with detailed metrics and recommendations
    """
    symbol_list = symbols.split(",") if symbols else None
    return await get_diversification_score(symbol_list)


@app.get(
    "/api/v1/risk/correlation/pair/{symbol_a}/{symbol_b}", tags=["Risk - Correlation"]
)
async def pair_correlation_endpoint(symbol_a: str, symbol_b: str):
    """
    Get detailed correlation info for a specific pair

    Args:
        symbol_a: First trading symbol (e.g., BTCUSDT)
        symbol_b: Second trading symbol (e.g., ETHUSDT)

    Returns:
        Correlation details including position recommendations
    """
    return await get_pair_correlation(symbol_a, symbol_b)


@app.get("/api/v1/risk/correlation/alerts", tags=["Risk - Correlation"])
async def correlation_alerts_endpoint(
    min_severity: str = Query(
        default="WARNING",
        description="Minimum severity level (INFO, WARNING, HIGH, CRITICAL)",
    ),
):
    """
    Get correlation alerts

    Returns alerts for highly correlated positions that may indicate
    concentration risk.

    Args:
        min_severity: Minimum severity level to include

    Returns:
        List of correlation alerts sorted by severity
    """
    return await get_correlation_alerts(min_severity)


@app.post(
    "/api/v1/risk/correlation/check-position/{symbol}", tags=["Risk - Correlation"]
)
async def check_position_correlation_endpoint(symbol: str):
    """
    Check if a new position can be opened based on correlation limits

    Rules enforced:
    1. Cannot open position if highly correlated (>0.7) with existing position
    2. Max 3 positions with moderate correlation (>0.6)
    3. Position size may be reduced for moderately correlated pairs

    Args:
        symbol: Symbol for the new position

    Returns:
        Whether position can be opened and any restrictions
    """
    return await check_can_open_position(symbol)


@app.post("/api/v1/risk/correlation/update", tags=["Risk - Correlation"])
async def update_correlations_endpoint(
    price_data: Optional[Dict[str, List[float]]] = None,
):
    """
    Manually trigger correlation update

    If no price data provided, fetches latest prices from market data service.

    Args:
        price_data: Optional dictionary of symbol -> price list

    Returns:
        Update status and new correlation matrix summary
    """
    return await update_correlations(price_data)


# ============================================================================
# SQZMOM STRATEGY ENDPOINTS
# ============================================================================


@app.get("/api/v1/strategies/sqzmom/info", tags=["SQZMOM Strategy"])
async def get_sqzmom_info():
    """
    Get SQZMOM strategy information

    Returns complete strategy configuration, enabled symbols,
    backtesting results, and current state.
    """
    return sqzmom_strategy.get_strategy_info()


@app.get("/api/v1/strategies/sqzmom/config", tags=["SQZMOM Strategy"])
async def get_sqzmom_config():
    """
    Get current SQZMOM strategy configuration

    Returns all configuration parameters including:
    - Enabled symbols
    - Indicator parameters (BB, KC lengths)
    - Strategy parameters (momentum threshold, SL, TP)
    - Risk management (position size, max positions)
    - Trading mode (paper/live, auto/manual)
    """
    return sqzmom_config.dict()


@app.post("/api/v1/strategies/sqzmom/enable", tags=["SQZMOM Strategy"])
async def enable_sqzmom_trading(
    auto_trading: bool = Query(
        default=False,
        description="Enable automatic trade execution (False = manual approval required)",
    ),
):
    """
    Enable SQZMOM strategy

    Args:
        auto_trading: Enable automatic trade execution
                     - False: Signals are generated but require manual approval
                     - True: Trades are executed automatically

    Returns:
        Success status and current configuration
    """
    sqzmom_config.auto_trading = auto_trading

    logger.info(
        f"SQZMOM strategy {'ENABLED' if auto_trading else 'ENABLED (manual approval mode)'}"
    )

    return {
        "success": True,
        "message": f"SQZMOM strategy enabled with auto_trading={auto_trading}",
        "enabled_symbols": sqzmom_config.enabled_symbols,
        "paper_trading": sqzmom_config.paper_trading,
        "auto_trading": sqzmom_config.auto_trading,
        "max_positions": sqzmom_config.max_positions,
        "note": "Manual approval required"
        if not auto_trading
        else "Automatic execution enabled",
    }


@app.post("/api/v1/strategies/sqzmom/disable", tags=["SQZMOM Strategy"])
async def disable_sqzmom_trading():
    """
    Disable SQZMOM strategy

    Sets auto_trading to False, preventing any automatic trade execution.
    Manual signal fetching is still possible.
    """
    sqzmom_config.auto_trading = False

    logger.info("SQZMOM strategy DISABLED")

    return {
        "success": True,
        "message": "SQZMOM strategy disabled (auto_trading set to False)",
        "auto_trading": sqzmom_config.auto_trading,
    }


@app.get("/api/v1/strategies/sqzmom/signals", tags=["SQZMOM Strategy"])
async def get_all_sqzmom_signals():
    """
    Get SQZMOM signals for all enabled symbols

    Fetches signals from Technical Analysis service for:
    - SOLUSDT
    - DOGEUSDT
    - BNBUSDT

    Returns dictionary mapping symbol to signal with action,
    confidence, entry/SL/TP prices, and reasoning.
    """
    signals = await sqzmom_strategy.get_all_signals()

    return {
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "enabled_symbols": sqzmom_config.enabled_symbols,
        "signals_retrieved": len(signals),
        "signals": signals,
    }


@app.get("/api/v1/strategies/sqzmom/signal/{symbol}", tags=["SQZMOM Strategy"])
async def get_sqzmom_signal(
    symbol: str,
    interval: Optional[str] = Query(
        default=None,
        description="Timeframe in minutes (default: from config, typically 60)",
    ),
):
    """
    Get SQZMOM signal for a specific symbol

    Args:
        symbol: Trading pair (e.g., SOLUSDT)
        interval: Timeframe in minutes (default: 60)

    Returns:
        Signal with action, confidence, prices, and reasoning

    Note:
        - Symbol must be in enabled list (SOLUSDT, DOGEUSDT, BNBUSDT)
        - Returns 404 if symbol not enabled
    """
    # Check if symbol is enabled
    if not sqzmom_strategy.is_symbol_enabled(symbol):
        return {
            "success": False,
            "error": f"Symbol {symbol} not in enabled list",
            "enabled_symbols": sqzmom_config.enabled_symbols,
        }

    # Get signal
    signal = await sqzmom_strategy.get_signal(symbol, interval)

    if signal is None:
        return {
            "success": False,
            "error": f"Failed to fetch signal for {symbol}",
            "symbol": symbol,
        }

    return {"success": True, "signal": signal}


@app.post("/api/v1/strategies/sqzmom/trade/{symbol}", tags=["SQZMOM Strategy"])
async def execute_sqzmom_trade(
    symbol: str,
    account_balance: float = Query(
        default=10000.0, description="Account balance for position sizing"
    ),
    force: bool = Query(
        default=False, description="Force execution even if auto_trading is disabled"
    ),
):
    """
    Execute SQZMOM trade for a symbol

    This endpoint demonstrates the full trading flow:
    1. Get SQZMOM signal from Technical Analysis service
    2. Validate signal meets entry criteria
    3. Calculate position size based on risk management
    4. Execute trade (paper or live mode)

    Args:
        symbol: Trading pair (must be in enabled list)
        account_balance: Account balance for position sizing (default: $10,000)
        force: Force execution even if auto_trading disabled (for manual approval)

    Returns:
        Trade execution result with details
    """

    # Check if symbol is enabled
    if not sqzmom_strategy.is_symbol_enabled(symbol):
        return {
            "success": False,
            "error": f"Symbol {symbol} not in enabled list",
            "enabled_symbols": sqzmom_config.enabled_symbols,
        }

    # Get signal
    signal = await sqzmom_strategy.get_signal(symbol)

    if not signal:
        return {"success": False, "error": "Failed to fetch signal", "symbol": symbol}

    # Check if HOLD
    if signal["action"] == "HOLD":
        return {
            "success": False,
            "message": "No valid signal (action is HOLD)",
            "symbol": symbol,
            "signal": signal,
        }

    # Check if should execute (unless forced)
    if not force:
        position_manager = get_position_manager()
        current_positions = len(position_manager.get_open_positions())
        should_execute, reason = await sqzmom_strategy.should_execute_trade(
            signal, current_positions
        )

        if not should_execute:
            return {
                "success": False,
                "message": "Trade validation failed",
                "reason": reason,
                "symbol": symbol,
                "signal": signal,
                "note": "Use force=true to override (manual approval)",
            }

    # Calculate position size
    quantity = await sqzmom_strategy.calculate_position_size(
        symbol, signal["entry_price"], signal["stop_loss"], account_balance
    )

    # Get symbol config for display
    symbol_cfg = sqzmom_strategy.get_symbol_config(symbol)

    # Record trade metric
    trades_executed_total.labels(
        symbol=symbol, side=signal["action"], status="success"
    ).inc()

    # Build trade result
    trade_result = {
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "symbol": symbol,
        "action": signal["action"],
        "quantity": float(quantity),
        "entry_price": signal["entry_price"],
        "stop_loss": signal["stop_loss"],
        "take_profit": signal["take_profit"],
        "confidence": signal["confidence"],
        "reason": signal["reason"],
        "position_size_pct": symbol_cfg["position_size_pct"],
        "position_value": float(quantity) * signal["entry_price"],
        "paper_trading": sqzmom_config.paper_trading,
        "forced": force,
        "note": "This is a simulated trade - actual execution not implemented yet",
    }

    logger.info(
        f"SQZMOM trade executed: {symbol} {signal['action']} "
        f"qty={quantity} @ ${signal['entry_price']}"
    )

    return trade_result


@app.get("/api/v1/strategies/sqzmom/symbols/{symbol}/config", tags=["SQZMOM Strategy"])
async def get_symbol_config(symbol: str):
    """
    Get configuration for a specific symbol

    Returns symbol-specific parameters including:
    - Position size percentage
    - Stop loss percentage
    - Take profit percentage
    - Minimum confidence threshold
    - Backtesting results
    """
    if not sqzmom_strategy.is_symbol_enabled(symbol):
        return {
            "success": False,
            "error": f"Symbol {symbol} not in enabled list",
            "enabled_symbols": sqzmom_config.enabled_symbols,
        }

    config = sqzmom_strategy.get_symbol_config(symbol)

    return {"success": True, "symbol": symbol, "config": config}


# ============================================================================
# BACKTESTING ENDPOINTS
# ============================================================================


@app.get("/api/v1/backtest/strategies", tags=["Backtesting"])
async def backtest_strategies_endpoint():
    """
    List all available backtesting strategies

    Returns list of strategies with their parameters and default values.
    Available strategies:
    - rsi_momentum: RSI crossover strategy with ATR-based stops
    - regime_adaptive: Hurst-based regime detection with adaptive RSI thresholds
    """
    return await list_strategies()


@app.post("/api/v1/backtest/run", tags=["Backtesting"])
async def backtest_run_endpoint(request: BacktestRequest):
    """
    Run a backtest with specified strategy and parameters

    Runs a complete backtest simulation including:
    - Trade execution with slippage and commission
    - Stop loss and take profit management
    - Performance metrics calculation (Sharpe, Sortino, Max Drawdown)
    - Trade-by-trade analysis

    Args:
        request: Backtest configuration including strategy, symbol, and parameters
    """
    return await run_backtest(request)


@app.get("/api/v1/backtest/quick/{strategy}", tags=["Backtesting"])
async def backtest_quick_endpoint(
    strategy: str,
    symbol: str = Query(default="BTCUSDT", description="Trading symbol"),
    days: int = Query(default=30, description="Number of days to backtest"),
):
    """
    Quick backtest with default parameters

    Runs a backtest with default strategy parameters for quick testing.

    Args:
        strategy: Strategy name (rsi_momentum or regime_adaptive)
        symbol: Trading symbol
        days: Number of days of historical data
    """
    return await get_backtest_quick_run(strategy, symbol, days)


@app.get("/api/v1/backtest/compare", tags=["Backtesting"])
async def backtest_compare_endpoint(
    symbol: str = Query(default="BTCUSDT", description="Trading symbol"),
    days: int = Query(default=90, description="Number of days to backtest"),
):
    """
    Compare all available strategies

    Runs all strategies on the same dataset for fair comparison.
    Returns rankings by total return and Sharpe ratio.

    Args:
        symbol: Trading symbol
        days: Number of days of historical data
    """
    return await compare_strategies(symbol, days)


@app.get("/api/v1/backtest/equity-curve/{strategy}", tags=["Backtesting"])
async def backtest_equity_curve_endpoint(
    strategy: str,
    symbol: str = Query(default="BTCUSDT", description="Trading symbol"),
    days: int = Query(default=30, description="Number of days"),
    sample_rate: int = Query(default=24, description="Sample every N points"),
):
    """
    Get equity curve data for charting

    Returns sampled equity curve data suitable for visualization.

    Args:
        strategy: Strategy name
        symbol: Trading symbol
        days: Number of days
        sample_rate: Sample every N data points (24 = daily for hourly data)
    """
    return await get_equity_curve(strategy, symbol, days, sample_rate)


# ============================================================================
# STATISTICAL ARBITRAGE ENDPOINTS (Phase 2.2)
# ============================================================================


@app.post("/api/v1/statistical-arbitrage/initialize", tags=["Statistical Arbitrage"])
async def stat_arb_initialize_endpoint(
    total_capital: float = Query(
        default=100000.0, description="Total capital to allocate"
    ),
    pairs_allocation: float = Query(
        default=0.4, description="Pairs trading allocation (0.0-1.0)"
    ),
    funding_allocation: float = Query(
        default=0.4, description="Funding rate arbitrage allocation (0.0-1.0)"
    ),
    triangular_allocation: float = Query(
        default=0.2, description="Triangular arbitrage allocation (0.0-1.0)"
    ),
):
    """
    Initialize Statistical Arbitrage Manager

    Sets up the manager with capital allocation across different arbitrage strategies.
    Allocations must sum to 1.0.

    Args:
        total_capital: Total capital to manage (default: $100,000)
        pairs_allocation: Percentage for pairs trading (default: 40%)
        funding_allocation: Percentage for funding rate arbitrage (default: 40%)
        triangular_allocation: Percentage for triangular arbitrage (default: 20%)

    Returns:
        Initialization status and configuration
    """
    return await initialize_stat_arb_manager(
        total_capital=total_capital,
        pairs_allocation=pairs_allocation,
        funding_allocation=funding_allocation,
        triangular_allocation=triangular_allocation,
    )


@app.post("/api/v1/statistical-arbitrage/pairs/add", tags=["Statistical Arbitrage"])
async def stat_arb_add_pairs_endpoint(
    symbol_x: str = Query(..., description="First symbol in pair (e.g., BTCUSDT)"),
    symbol_y: str = Query(..., description="Second symbol in pair (e.g., ETHUSDT)"),
    entry_threshold: float = Query(
        default=2.0, description="Z-score threshold for entry"
    ),
    exit_threshold: float = Query(
        default=0.5, description="Z-score threshold for exit"
    ),
    lookback_period: int = Query(
        default=20, description="Lookback period for cointegration"
    ),
    stop_loss_z: float = Query(default=3.0, description="Stop loss z-score threshold"),
):
    """
    Add a pairs trading strategy

    Creates a new pairs trading strategy between two correlated symbols.
    The strategy monitors the spread between the two symbols and trades
    when the spread deviates significantly from its mean.

    Args:
        symbol_x: First trading pair
        symbol_y: Second trading pair
        entry_threshold: Z-score threshold to enter position (default: 2.0)
        exit_threshold: Z-score threshold to exit position (default: 0.5)
        lookback_period: Historical period for spread calculation (default: 20)
        stop_loss_z: Maximum z-score before stop loss (default: 3.0)

    Returns:
        Strategy ID and configuration
    """
    return await add_pairs_strategy(
        symbol_x=symbol_x,
        symbol_y=symbol_y,
        entry_threshold=entry_threshold,
        exit_threshold=exit_threshold,
        lookback_period=lookback_period,
        stop_loss_z=stop_loss_z,
    )


@app.post(
    "/api/v1/statistical-arbitrage/pairs/calibrate", tags=["Statistical Arbitrage"]
)
async def stat_arb_calibrate_pairs_endpoint(
    strategy_id: str = Query(..., description="Strategy ID to calibrate"),
    historical_data: dict = None,
):
    """
    Calibrate a pairs trading strategy

    Recalibrates the hedge ratio and spread parameters for a pairs trading strategy
    using historical price data.

    Args:
        strategy_id: ID of the strategy to calibrate
        historical_data: Historical price data for calibration

    Returns:
        Calibration results including updated parameters
    """
    return await calibrate_pairs_strategy(
        strategy_id=strategy_id, historical_data=historical_data
    )


@app.post("/api/v1/statistical-arbitrage/funding/add", tags=["Statistical Arbitrage"])
async def stat_arb_add_funding_endpoint(
    symbol: str = Query(..., description="Trading symbol (e.g., BTCUSDT)"),
    min_funding_rate: float = Query(
        default=0.0001, description="Minimum funding rate threshold"
    ),
    max_position_size: float = Query(
        default=10000.0, description="Maximum position size"
    ),
):
    """
    Add a funding rate arbitrage strategy

    Creates a strategy that profits from funding rate differentials between
    spot and perpetual futures markets.

    Args:
        symbol: Trading pair to monitor
        min_funding_rate: Minimum funding rate to trigger trade (default: 0.01%)
        max_position_size: Maximum position size in USDT (default: $10,000)

    Returns:
        Strategy ID and configuration
    """
    return await add_funding_strategy(
        symbol=symbol,
        min_funding_rate=min_funding_rate,
        max_position_size=max_position_size,
    )


@app.post(
    "/api/v1/statistical-arbitrage/triangular/setup", tags=["Statistical Arbitrage"]
)
async def stat_arb_setup_triangular_endpoint(
    assets: list = Query(
        ...,
        description="List of assets for triangular arbitrage (e.g., ['BTC', 'ETH', 'BNB', 'USDT'])",
    ),
    min_profit_threshold: float = Query(
        default=0.005, description="Minimum profit threshold (0.5%)"
    ),
    max_latency_ms: float = Query(
        default=100.0, description="Maximum acceptable latency in milliseconds"
    ),
):
    """
    Setup triangular arbitrage strategy

    Configures a strategy to exploit price discrepancies across three or more
    trading pairs (e.g., BTC/USDT, ETH/USDT, BTC/ETH).

    Args:
        assets: List of assets to form arbitrage triangles
        min_profit_threshold: Minimum profit percentage to execute (default: 0.5%)
        max_latency_ms: Maximum latency tolerance (default: 100ms)

    Returns:
        Configuration status and detected arbitrage paths
    """
    return await setup_triangular_arbitrage(
        assets=assets,
        min_profit_threshold=min_profit_threshold,
        max_latency_ms=max_latency_ms,
    )


@app.post(
    "/api/v1/statistical-arbitrage/signals/generate", tags=["Statistical Arbitrage"]
)
async def stat_arb_generate_signals_endpoint(market_data: dict):
    """
    Generate signals from all enabled strategies

    Analyzes current market data and generates trading signals from all
    active statistical arbitrage strategies.

    Args:
        market_data: Current market data including prices, funding rates, etc.

    Returns:
        Signals from pairs, funding, and triangular arbitrage strategies
    """
    return await generate_stat_arb_signals(market_data=market_data)


@app.get("/api/v1/statistical-arbitrage/performance", tags=["Statistical Arbitrage"])
async def stat_arb_performance_endpoint():
    """
    Get performance metrics for all strategies

    Returns comprehensive performance statistics including:
    - Total P&L across all strategies
    - Win rate and trade statistics
    - Sharpe ratio and risk metrics
    - Individual strategy performance

    Returns:
        Aggregated performance metrics and individual strategy results
    """
    return await get_stat_arb_performance()


@app.get("/api/v1/statistical-arbitrage/status", tags=["Statistical Arbitrage"])
async def stat_arb_status_endpoint():
    """
    Get current status of Statistical Arbitrage Manager

    Returns:
        - Manager initialization status
        - Active strategies count
        - Capital allocation
        - Current positions
    """
    return await get_stat_arb_status()


@app.delete("/api/v1/statistical-arbitrage/reset", tags=["Statistical Arbitrage"])
async def stat_arb_reset_endpoint():
    """
    Reset Statistical Arbitrage Manager

    Clears all strategies and resets the manager to uninitialized state.
    WARNING: This will close all active positions.

    Returns:
        Reset confirmation
    """
    return await reset_stat_arb_manager()


# ============================================================================
# ROOT ENDPOINT
# ============================================================================


@app.get("/", tags=["Info"])
async def root():
    """Root endpoint with service information"""
    return {
        "service": settings.service_name,
        "version": VERSION,
        "status": "running",
        "architecture": "Modular (Phase 3-5 Complete)",
        "trading_mode": settings.trading_mode,
        "endpoints": {
            "health": "/health",
            "health_detailed": "/health/detailed",
            "status": "/status",
            "metrics": "/metrics",
            "docs": "/docs",
            "signals": "/api/v1/signals/{symbol}",
            "positions": "/api/v1/positions",
            "performance": "/api/v1/performance",
            "trading_control": {
                "start": "/api/v1/trading/start",
                "stop": "/api/v1/trading/stop",
                "status": "/api/v1/trading/status",
            },
            "phase1": {
                "metrics": "/api/v1/phase1/metrics",
                "health": "/api/v1/phase1/health",
                "latest": "/api/v1/phase1/latest",
            },
            "correlation_analysis": {
                "matrix": "/api/v1/risk/correlation",
                "status": "/api/v1/risk/correlation/status",
                "score": "/api/v1/risk/correlation/score",
                "pair": "/api/v1/risk/correlation/pair/{symbol_a}/{symbol_b}",
                "alerts": "/api/v1/risk/correlation/alerts",
                "check_position": "POST /api/v1/risk/correlation/check-position/{symbol}",
                "update": "POST /api/v1/risk/correlation/update",
            },
            "kelly_position_sizing": {
                "stats": "GET /api/v1/risk/kelly-stats",
                "calculate": "POST /api/v1/risk/kelly-calculate",
                "simulate": "POST /api/v1/risk/kelly-simulate",
                "record_trade": "POST /api/v1/risk/kelly-record-trade",
                "comparison": "GET /api/v1/risk/kelly-comparison",
                "reset": "DELETE /api/v1/risk/kelly-reset",
            },
            "dynamic_risk_budget": {
                "current": "GET /api/v1/risk/budget/current",
                "utilization": "GET /api/v1/risk/budget/utilization",
                "allocation": "GET /api/v1/risk/budget/allocation",
                "calculate": "POST /api/v1/risk/budget/calculate",
                "adjust": "POST /api/v1/risk/budget/adjust",
                "history": "GET /api/v1/risk/budget/history",
                "alerts": "GET /api/v1/risk/budget/alerts",
                "emergency_trigger": "POST /api/v1/risk/budget/emergency/trigger",
                "emergency_clear": "POST /api/v1/risk/budget/emergency/clear",
                "reset": "DELETE /api/v1/risk/budget/reset",
            },
            "smart_order_routing": {
                "stats": "GET /api/v1/execution/router-stats",
                "status": "GET /api/v1/execution/router-status",
                "recommend": "POST /api/v1/execution/recommend",
                "analyze_orderbook": "POST /api/v1/execution/analyze-orderbook",
                "estimate_slippage": "POST /api/v1/execution/estimate-slippage",
                "quality_report": "GET /api/v1/execution/quality-report",
                "reset": "POST /api/v1/execution/reset",
            },
            "twap_vwap_execution": {
                "twap": "POST /api/v1/execution/twap",
                "vwap": "POST /api/v1/execution/vwap",
                "twap_status": "GET /api/v1/execution/twap/{order_id}",
                "vwap_status": "GET /api/v1/execution/vwap/{order_id}",
                "active_algorithms": "GET /api/v1/execution/active-algorithms",
                "pause": "POST /api/v1/execution/pause/{order_id}",
                "cancel": "POST /api/v1/execution/cancel/{order_id}",
                "performance_report": "GET /api/v1/execution/performance-report",
            },
            "attribution_analysis": {
                "by_strategy": "GET /api/v1/analytics/attribution/by-strategy",
                "by_symbol": "GET /api/v1/analytics/attribution/by-symbol",
                "summary": "GET /api/v1/analytics/attribution/summary",
                "trends": "GET /api/v1/analytics/attribution/trends",
                "daily_report": "GET /api/v1/analytics/attribution/daily-report",
                "decomposition": "GET /api/v1/analytics/attribution/performance-decomposition",
            },
            "sqzmom_strategy": {
                "info": "/api/v1/strategies/sqzmom/info",
                "config": "/api/v1/strategies/sqzmom/config",
                "enable": "POST /api/v1/strategies/sqzmom/enable",
                "disable": "POST /api/v1/strategies/sqzmom/disable",
                "signals": "/api/v1/strategies/sqzmom/signals",
                "signal": "/api/v1/strategies/sqzmom/signal/{symbol}",
                "trade": "POST /api/v1/strategies/sqzmom/trade/{symbol}",
                "symbol_config": "/api/v1/strategies/sqzmom/symbols/{symbol}/config",
            },
            "backtesting": {
                "strategies": "/api/v1/backtest/strategies",
                "run": "POST /api/v1/backtest/run",
                "quick": "/api/v1/backtest/quick/{strategy}",
                "compare": "/api/v1/backtest/compare",
                "equity_curve": "/api/v1/backtest/equity-curve/{strategy}",
            },
            "statistical_arbitrage": {
                "initialize": "POST /api/v1/statistical-arbitrage/initialize",
                "add_pairs_strategy": "POST /api/v1/statistical-arbitrage/pairs/add",
                "calibrate_pairs": "POST /api/v1/statistical-arbitrage/pairs/calibrate",
                "add_funding_strategy": "POST /api/v1/statistical-arbitrage/funding/add",
                "setup_triangular": "POST /api/v1/statistical-arbitrage/triangular/setup",
                "generate_signals": "POST /api/v1/statistical-arbitrage/signals/generate",
                "performance": "/api/v1/statistical-arbitrage/performance",
                "status": "/api/v1/statistical-arbitrage/status",
                "reset": "DELETE /api/v1/statistical-arbitrage/reset",
            },
        },
        "features": {"prometheus_metrics": True},
        "refactoring": {
            "status": "Phase 3.3 Complete",
            "version": VERSION,
            "modules": 15,
            "architecture": "main.py -> handlers -> services -> domain",
        },
        "enhancements": {
            "phase_3_1_correlation": {
                "description": "Portfolio Correlation Analysis",
                "status": "ACTIVE",
                "features": [
                    "Pearson correlation between all trading pairs",
                    "Rolling correlation (30-day, 60-day windows)",
                    "Portfolio diversification scoring (0-100)",
                    "Correlation-based position limits",
                    "High correlation alerts",
                ],
            },
            "phase_3_2_kelly": {
                "description": "Kelly Criterion Position Sizing",
                "status": "ACTIVE",
                "features": [
                    "Full Kelly (theoretical optimal)",
                    "Fractional Kelly (25% - conservative)",
                    "Dynamic Kelly (streak-adjusted)",
                    "Rolling win rate tracking",
                    "Trade recording and performance stats",
                ],
            },
            "phase_3_3_risk_budget": {
                "description": "Dynamic Risk Budgeting",
                "status": "ACTIVE",
                "features": [
                    "Volatility-based risk adjustment (VIX-style)",
                    "Drawdown-based risk reduction",
                    "Win/loss streak adjustment",
                    "Correlation-based risk scaling",
                    "Liquidity timing adjustment",
                    "Emergency risk triggers",
                    "Risk ladder (0.5% - 2.5%)",
                    "Multi-strategy budget allocation",
                ],
            },
            "phase_4_1_smart_routing": {
                "description": "Smart Order Routing",
                "status": "ACTIVE",
                "features": [
                    "Intelligent order type selection",
                    "Slippage estimation and minimization",
                    "Order book liquidity analysis",
                    "Basic TWAP for large orders",
                    "Execution quality reporting",
                ],
            },
            "phase_4_2_twap_vwap": {
                "description": "Enhanced TWAP/VWAP Execution",
                "status": "ACTIVE",
                "features": [
                    "Professional-grade TWAP execution",
                    "Volume-weighted VWAP execution",
                    "Random timing variation (+/-20%)",
                    "Adaptive slice sizing based on fill rates",
                    "Participation rate limiting (max 30%)",
                    "Pause/Resume/Cancel mechanisms",
                    "Execution quality benchmarking",
                    "Slippage tracking vs TWAP/VWAP benchmark",
                ],
            },
            "phase_5_1_attribution": {
                "description": "P&L Attribution Analysis",
                "status": "ACTIVE",
                "features": [
                    "Attribution by Strategy",
                    "Attribution by Symbol",
                    "Attribution by Direction (Long/Short)",
                    "Attribution by Market Condition",
                    "Performance Decomposition (Alpha, Beta, Residual)",
                    "Daily attribution reports",
                ],
            },
        },
        "sqzmom_strategy": {
            "enabled": True,
            "symbols": sqzmom_config.enabled_symbols,
            "paper_trading": sqzmom_config.paper_trading,
            "auto_trading": sqzmom_config.auto_trading,
            "backtesting_results": {
                "SOLUSDT": "+2,706% (22% WR, 4.76 Sharpe)",
                "DOGEUSDT": "+630% (28% WR, 5.41 Sharpe)",
                "BNBUSDT": "+330% (31% WR)",
            },
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.service_host,
        port=settings.service_port,
        reload=settings.debug,
    )
