"""
Prometheus Metrics for Trading Engine
Provides comprehensive metrics for monitoring trading performance
"""

import time
from typing import Callable
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, make_asgi_app
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


# Create custom registry
registry = CollectorRegistry()

# HTTP Metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status'],
    registry=registry
)

http_request_duration = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    registry=registry
)

http_requests_in_progress = Gauge(
    'http_requests_in_progress',
    'Number of HTTP requests currently being processed',
    registry=registry
)

# Trading Metrics
trading_signals_total = Counter(
    'trading_signals_total',
    'Total trading signals generated',
    ['symbol', 'signal_type', 'strategy'],
    registry=registry
)

trade_executions_total = Counter(
    'trade_executions_total',
    'Total trade executions',
    ['symbol', 'side', 'status'],
    registry=registry
)

trade_errors_total = Counter(
    'trade_errors_total',
    'Total trade execution errors',
    ['symbol', 'error_type'],
    registry=registry
)

active_positions_gauge = Gauge(
    'active_positions',
    'Number of active trading positions',
    ['symbol'],
    registry=registry
)

position_pnl_gauge = Gauge(
    'position_unrealized_pnl',
    'Unrealized P&L for active positions',
    ['symbol', 'position_id'],
    registry=registry
)

balance_gauge = Gauge(
    'account_balance',
    'Current account balance',
    ['account_type'],  # paper, live
    registry=registry
)

total_equity_gauge = Gauge(
    'account_total_equity',
    'Total account equity (balance + unrealized P&L)',
    ['account_type'],
    registry=registry
)

# Risk Metrics
daily_loss_gauge = Gauge(
    'daily_loss_amount',
    'Current daily loss amount',
    registry=registry
)

daily_loss_percentage = Gauge(
    'daily_loss_percentage',
    'Current daily loss percentage',
    registry=registry
)

risk_limit_violations = Counter(
    'risk_limit_violations_total',
    'Total risk limit violations',
    ['violation_type'],  # position_size, daily_loss, exposure
    registry=registry
)

# Performance Metrics
win_rate_gauge = Gauge(
    'win_rate',
    'Win rate percentage',
    registry=registry
)

roi_gauge = Gauge(
    'roi',
    'Return on investment percentage',
    registry=registry
)

total_trades_counter = Counter(
    'total_trades',
    'Total number of trades executed',
    ['result'],  # win, loss
    registry=registry
)

# System Metrics
database_connections = Gauge(
    'database_connections',
    'Number of active database connections',
    ['pool_type'],  # postgres, redis
    registry=registry
)

external_api_calls = Counter(
    'external_api_calls_total',
    'Total external API calls',
    ['service', 'status'],  # technical_analysis, bybit, etc.
    registry=registry
)

external_api_duration = Histogram(
    'external_api_duration_seconds',
    'External API call duration',
    ['service'],
    registry=registry
)

external_api_errors = Counter(
    'external_api_errors_total',
    'Total external API errors',
    ['service', 'error_type'],
    registry=registry
)

# Cache Metrics
cache_hits = Counter(
    'cache_hits_total',
    'Total cache hits',
    ['cache_type'],
    registry=registry
)

cache_misses = Counter(
    'cache_misses_total',
    'Total cache misses',
    ['cache_type'],
    registry=registry
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware to track HTTP request metrics"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Track request metrics"""
        # Skip metrics endpoint itself
        if request.url.path == "/metrics":
            return await call_next(request)

        # Increment in-progress gauge
        http_requests_in_progress.inc()

        # Start timer
        start_time = time.time()

        try:
            # Process request
            response = await call_next(request)

            # Record duration
            duration = time.time() - start_time
            http_request_duration.labels(
                method=request.method,
                endpoint=request.url.path
            ).observe(duration)

            # Record total requests
            http_requests_total.labels(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code
            ).inc()

            return response

        except Exception as e:
            # Record errors
            http_requests_total.labels(
                method=request.method,
                endpoint=request.url.path,
                status=500
            ).inc()
            raise

        finally:
            # Decrement in-progress gauge
            http_requests_in_progress.dec()


def metrics_middleware():
    """Create metrics middleware instance"""
    return PrometheusMiddleware


def create_metrics_app():
    """Create Prometheus metrics ASGI app"""
    return make_asgi_app(registry=registry)


# Utility functions for updating metrics
def record_trading_signal(symbol: str, signal_type: str, strategy: str):
    """Record a trading signal"""
    trading_signals_total.labels(
        symbol=symbol,
        signal_type=signal_type,
        strategy=strategy
    ).inc()


def record_trade_execution(symbol: str, side: str, status: str):
    """Record a trade execution"""
    trade_executions_total.labels(
        symbol=symbol,
        side=side,
        status=status
    ).inc()


def record_trade_error(symbol: str, error_type: str):
    """Record a trade error"""
    trade_errors_total.labels(
        symbol=symbol,
        error_type=error_type
    ).inc()


def update_active_positions(symbol: str, count: int):
    """Update active positions count"""
    active_positions_gauge.labels(symbol=symbol).set(count)


def update_position_pnl(symbol: str, position_id: str, pnl: float):
    """Update position unrealized P&L"""
    position_pnl_gauge.labels(
        symbol=symbol,
        position_id=position_id
    ).set(pnl)


def update_balance(account_type: str, balance: float):
    """Update account balance"""
    balance_gauge.labels(account_type=account_type).set(balance)


def update_total_equity(account_type: str, equity: float):
    """Update total equity"""
    total_equity_gauge.labels(account_type=account_type).set(equity)


def update_daily_loss(amount: float, percentage: float):
    """Update daily loss metrics"""
    daily_loss_gauge.set(amount)
    daily_loss_percentage.set(percentage)


def record_risk_violation(violation_type: str):
    """Record a risk limit violation"""
    risk_limit_violations.labels(violation_type=violation_type).inc()


def update_performance_metrics(win_rate: float, roi: float):
    """Update performance metrics"""
    win_rate_gauge.set(win_rate)
    roi_gauge.set(roi)


def record_trade_result(result: str):
    """Record trade result (win/loss)"""
    total_trades_counter.labels(result=result).inc()


def record_api_call(service: str, status: str, duration: float = None):
    """Record external API call"""
    external_api_calls.labels(service=service, status=status).inc()
    if duration is not None:
        external_api_duration.labels(service=service).observe(duration)


def record_api_error(service: str, error_type: str):
    """Record external API error"""
    external_api_errors.labels(service=service, error_type=error_type).inc()


def record_cache_hit(cache_type: str):
    """Record cache hit"""
    cache_hits.labels(cache_type=cache_type).inc()


def record_cache_miss(cache_type: str):
    """Record cache miss"""
    cache_misses.labels(cache_type=cache_type).inc()
