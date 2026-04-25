"""
Prometheus Metrics Collection
Phase 7: High Availability & Monitoring Infrastructure

Purpose:
- Collect and expose trading performance metrics
- Track system health and resource utilization
- Provide real-time monitoring data for Grafana dashboards
- Enable alerting on critical thresholds

Metrics Categories:
- Trading Metrics: Orders, fills, P&L, positions
- System Metrics: CPU, memory, response times
- Business Metrics: Win rate, ROI, risk exposure
- Infrastructure Metrics: Database connections, cache hits

Integration:
- Prometheus scrapes /metrics endpoint
- Grafana visualizes metrics
- Alertmanager triggers notifications
"""

import time
import logging
import functools
from typing import Callable, Optional, Dict, Any, TypeVar, Awaitable
from datetime import datetime
from prometheus_client import (
    Counter, Gauge, Histogram, Summary,
    CollectorRegistry, make_asgi_app,
    CONTENT_TYPE_LATEST, generate_latest
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Type variable for generic functions
T = TypeVar('T')

# Custom registry for trading engine metrics
registry = CollectorRegistry()

# ============================================================================
# HTTP/API METRICS
# ============================================================================

http_requests_total = Counter(
    'trading_engine_http_requests_total',
    'Total HTTP requests to trading engine',
    ['method', 'endpoint', 'status_code'],
    registry=registry
)

http_request_duration_seconds = Histogram(
    'trading_engine_http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=registry
)

http_requests_in_progress = Gauge(
    'trading_engine_http_requests_in_progress',
    'Number of HTTP requests currently being processed',
    registry=registry
)

# ============================================================================
# TRADING METRICS
# ============================================================================

# Order metrics
orders_total = Counter(
    'trading_engine_orders_total',
    'Total orders submitted',
    ['symbol', 'side', 'order_type', 'status'],
    registry=registry
)

order_value_usd = Histogram(
    'trading_engine_order_value_usd',
    'Order value in USD',
    ['symbol', 'side'],
    buckets=[10, 50, 100, 250, 500, 1000, 2500, 5000, 10000],
    registry=registry
)

order_fill_latency_ms = Histogram(
    'trading_engine_order_fill_latency_ms',
    'Time from order submission to fill',
    ['symbol', 'order_type'],
    buckets=[10, 25, 50, 100, 250, 500, 1000, 2500, 5000],
    registry=registry
)

# Signal metrics
signals_generated_total = Counter(
    'trading_engine_signals_generated_total',
    'Total trading signals generated',
    ['symbol', 'signal_type', 'strategy'],
    registry=registry
)

signal_confidence = Histogram(
    'trading_engine_signal_confidence',
    'Signal confidence distribution',
    ['symbol', 'strategy'],
    buckets=[0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0],
    registry=registry
)

# Position metrics
active_positions = Gauge(
    'trading_engine_active_positions',
    'Number of active trading positions',
    ['symbol', 'side'],
    registry=registry
)

position_unrealized_pnl = Gauge(
    'trading_engine_position_unrealized_pnl',
    'Unrealized P&L for positions',
    ['symbol', 'position_id'],
    registry=registry
)

position_duration_hours = Histogram(
    'trading_engine_position_duration_hours',
    'Position holding duration in hours',
    ['symbol'],
    buckets=[0.5, 1, 2, 4, 8, 12, 24, 48, 72, 168],
    registry=registry
)

# Trade execution metrics
trades_executed_total = Counter(
    'trading_engine_trades_executed_total',
    'Total trades executed',
    ['symbol', 'side', 'result'],  # result: win, loss, breakeven
    registry=registry
)

trade_pnl_usd = Histogram(
    'trading_engine_trade_pnl_usd',
    'Trade P&L in USD',
    ['symbol', 'side'],
    buckets=[-500, -250, -100, -50, -10, 0, 10, 50, 100, 250, 500, 1000],
    registry=registry
)

trade_slippage_bps = Histogram(
    'trading_engine_trade_slippage_bps',
    'Trade slippage in basis points',
    ['symbol', 'side'],
    buckets=[0, 1, 2, 5, 10, 25, 50, 100],
    registry=registry
)

# ============================================================================
# ACCOUNT/PORTFOLIO METRICS
# ============================================================================

account_balance = Gauge(
    'trading_engine_account_balance',
    'Current account balance',
    ['account_type', 'currency'],  # account_type: paper, live
    registry=registry
)

account_equity = Gauge(
    'trading_engine_account_equity',
    'Total account equity (balance + unrealized P&L)',
    ['account_type', 'currency'],
    registry=registry
)

daily_pnl = Gauge(
    'trading_engine_daily_pnl',
    'Daily realized P&L',
    ['account_type'],
    registry=registry
)

total_realized_pnl = Gauge(
    'trading_engine_total_realized_pnl',
    'Total realized P&L since inception',
    ['account_type'],
    registry=registry
)

# ============================================================================
# RISK METRICS
# ============================================================================

daily_loss_amount = Gauge(
    'trading_engine_daily_loss_amount',
    'Current daily loss amount',
    registry=registry
)

daily_loss_percentage = Gauge(
    'trading_engine_daily_loss_percentage',
    'Current daily loss as percentage of equity',
    registry=registry
)

risk_exposure_percentage = Gauge(
    'trading_engine_risk_exposure_percentage',
    'Current risk exposure as percentage of equity',
    ['symbol'],
    registry=registry
)

total_risk_exposure = Gauge(
    'trading_engine_total_risk_exposure',
    'Total portfolio risk exposure percentage',
    registry=registry
)

max_drawdown_percentage = Gauge(
    'trading_engine_max_drawdown_percentage',
    'Maximum drawdown percentage',
    registry=registry
)

risk_limit_breaches_total = Counter(
    'trading_engine_risk_limit_breaches_total',
    'Total risk limit breaches',
    ['breach_type'],  # position_size, daily_loss, exposure, correlation
    registry=registry
)

# ============================================================================
# PERFORMANCE METRICS
# ============================================================================

win_rate = Gauge(
    'trading_engine_win_rate',
    'Current win rate percentage',
    ['strategy', 'symbol'],
    registry=registry
)

profit_factor = Gauge(
    'trading_engine_profit_factor',
    'Ratio of gross profits to gross losses',
    ['strategy'],
    registry=registry
)

sharpe_ratio = Gauge(
    'trading_engine_sharpe_ratio',
    'Risk-adjusted return metric',
    ['strategy'],
    registry=registry
)

roi_percentage = Gauge(
    'trading_engine_roi_percentage',
    'Return on investment percentage',
    ['account_type'],
    registry=registry
)

# ============================================================================
# EXTERNAL API METRICS
# ============================================================================

external_api_requests_total = Counter(
    'trading_engine_external_api_requests_total',
    'Total external API requests',
    ['service', 'endpoint', 'status'],
    registry=registry
)

external_api_latency_seconds = Histogram(
    'trading_engine_external_api_latency_seconds',
    'External API request latency',
    ['service', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    registry=registry
)

external_api_errors_total = Counter(
    'trading_engine_external_api_errors_total',
    'Total external API errors',
    ['service', 'error_type'],
    registry=registry
)

circuit_breaker_state = Gauge(
    'trading_engine_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=half-open, 2=open)',
    ['service'],
    registry=registry
)

# ============================================================================
# CACHE METRICS
# ============================================================================

cache_hits_total = Counter(
    'trading_engine_cache_hits_total',
    'Total cache hits',
    ['cache_type'],
    registry=registry
)

cache_misses_total = Counter(
    'trading_engine_cache_misses_total',
    'Total cache misses',
    ['cache_type'],
    registry=registry
)

cache_size = Gauge(
    'trading_engine_cache_size',
    'Current cache size',
    ['cache_type'],
    registry=registry
)

# ============================================================================
# DATABASE METRICS
# ============================================================================

db_connections_active = Gauge(
    'trading_engine_db_connections_active',
    'Active database connections',
    ['pool'],
    registry=registry
)

db_query_duration_seconds = Histogram(
    'trading_engine_db_query_duration_seconds',
    'Database query duration',
    ['query_type'],  # select, insert, update, delete
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=registry
)

db_errors_total = Counter(
    'trading_engine_db_errors_total',
    'Total database errors',
    ['error_type'],
    registry=registry
)

# ============================================================================
# STRATEGY-SPECIFIC METRICS
# ============================================================================

strategy_active = Gauge(
    'trading_engine_strategy_active',
    'Whether a strategy is currently active',
    ['strategy_name'],
    registry=registry
)

strategy_signals_per_minute = Gauge(
    'trading_engine_strategy_signals_per_minute',
    'Signal generation rate per minute',
    ['strategy_name'],
    registry=registry
)

strategy_execution_time_ms = Histogram(
    'trading_engine_strategy_execution_time_ms',
    'Strategy execution time in milliseconds',
    ['strategy_name'],
    buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000],
    registry=registry
)


class TradingMetrics:
    """
    High-level interface for recording trading metrics

    Provides convenient methods for common metric operations
    with proper labeling and error handling.

    Usage:
        metrics = TradingMetrics()
        metrics.record_order("BTCUSDT", "buy", "limit", "filled", 1500.0)
        metrics.record_trade_result("BTCUSDT", "buy", "win", 150.0)
        metrics.update_account_balance("paper", 10500.0)
    """

    def __init__(self):
        """Initialize trading metrics interface"""
        self._trade_count = 0
        self._win_count = 0
        self._loss_count = 0
        self._total_pnl = 0.0

    # Order Recording
    def record_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        status: str,
        value_usd: float
    ):
        """Record a trading order"""
        orders_total.labels(
            symbol=symbol,
            side=side,
            order_type=order_type,
            status=status
        ).inc()

        if value_usd > 0:
            order_value_usd.labels(symbol=symbol, side=side).observe(value_usd)

    def record_order_fill_latency(
        self,
        symbol: str,
        order_type: str,
        latency_ms: float
    ):
        """Record order fill latency"""
        order_fill_latency_ms.labels(
            symbol=symbol,
            order_type=order_type
        ).observe(latency_ms)

    # Signal Recording
    def record_signal(
        self,
        symbol: str,
        signal_type: str,
        strategy: str,
        confidence: float
    ):
        """Record a trading signal"""
        signals_generated_total.labels(
            symbol=symbol,
            signal_type=signal_type,
            strategy=strategy
        ).inc()

        signal_confidence.labels(
            symbol=symbol,
            strategy=strategy
        ).observe(confidence)

    # Position Tracking
    def update_position_count(self, symbol: str, side: str, count: int):
        """Update active position count"""
        active_positions.labels(symbol=symbol, side=side).set(count)

    def update_position_pnl(
        self,
        symbol: str,
        position_id: str,
        unrealized_pnl: float
    ):
        """Update position unrealized P&L"""
        position_unrealized_pnl.labels(
            symbol=symbol,
            position_id=position_id
        ).set(unrealized_pnl)

    def record_position_close(self, symbol: str, duration_hours: float):
        """Record position close duration"""
        position_duration_hours.labels(symbol=symbol).observe(duration_hours)

    # Trade Results
    def record_trade_result(
        self,
        symbol: str,
        side: str,
        result: str,
        pnl_usd: float,
        slippage_bps: float = 0
    ):
        """
        Record trade result

        Args:
            symbol: Trading symbol
            side: Trade side (buy/sell)
            result: Trade result (win/loss/breakeven)
            pnl_usd: Profit/loss in USD
            slippage_bps: Slippage in basis points
        """
        trades_executed_total.labels(
            symbol=symbol,
            side=side,
            result=result
        ).inc()

        trade_pnl_usd.labels(symbol=symbol, side=side).observe(pnl_usd)

        if slippage_bps > 0:
            trade_slippage_bps.labels(symbol=symbol, side=side).observe(slippage_bps)

        # Update internal tracking
        self._trade_count += 1
        self._total_pnl += pnl_usd
        if result == "win":
            self._win_count += 1
        elif result == "loss":
            self._loss_count += 1

    # Account Metrics
    def update_account_balance(
        self,
        account_type: str,
        balance: float,
        currency: str = "USD"
    ):
        """Update account balance"""
        account_balance.labels(
            account_type=account_type,
            currency=currency
        ).set(balance)

    def update_account_equity(
        self,
        account_type: str,
        equity: float,
        currency: str = "USD"
    ):
        """Update account equity"""
        account_equity.labels(
            account_type=account_type,
            currency=currency
        ).set(equity)

    def update_daily_pnl(self, account_type: str, pnl: float):
        """Update daily P&L"""
        daily_pnl.labels(account_type=account_type).set(pnl)

    def update_total_pnl(self, account_type: str, total: float):
        """Update total realized P&L"""
        total_realized_pnl.labels(account_type=account_type).set(total)

    # Risk Metrics
    def update_daily_loss(self, amount: float, percentage: float):
        """Update daily loss metrics"""
        daily_loss_amount.set(amount)
        daily_loss_percentage.set(percentage)

    def update_risk_exposure(self, symbol: str, exposure_pct: float):
        """Update risk exposure for symbol"""
        risk_exposure_percentage.labels(symbol=symbol).set(exposure_pct)

    def update_total_exposure(self, exposure_pct: float):
        """Update total portfolio risk exposure"""
        total_risk_exposure.set(exposure_pct)

    def update_max_drawdown(self, drawdown_pct: float):
        """Update maximum drawdown"""
        max_drawdown_percentage.set(drawdown_pct)

    def record_risk_breach(self, breach_type: str):
        """Record a risk limit breach"""
        risk_limit_breaches_total.labels(breach_type=breach_type).inc()

    # Performance Metrics
    def update_win_rate(
        self,
        rate: float,
        strategy: str = "all",
        symbol: str = "all"
    ):
        """Update win rate"""
        win_rate.labels(strategy=strategy, symbol=symbol).set(rate)

    def update_profit_factor(self, factor: float, strategy: str = "all"):
        """Update profit factor"""
        profit_factor.labels(strategy=strategy).set(factor)

    def update_sharpe_ratio(self, ratio: float, strategy: str = "all"):
        """Update Sharpe ratio"""
        sharpe_ratio.labels(strategy=strategy).set(ratio)

    def update_roi(self, roi_pct: float, account_type: str = "paper"):
        """Update return on investment"""
        roi_percentage.labels(account_type=account_type).set(roi_pct)

    # External API Metrics
    def record_api_call(
        self,
        service: str,
        endpoint: str,
        status: str,
        latency_seconds: float
    ):
        """Record external API call"""
        external_api_requests_total.labels(
            service=service,
            endpoint=endpoint,
            status=status
        ).inc()

        external_api_latency_seconds.labels(
            service=service,
            endpoint=endpoint
        ).observe(latency_seconds)

    def record_api_error(self, service: str, error_type: str):
        """Record external API error"""
        external_api_errors_total.labels(
            service=service,
            error_type=error_type
        ).inc()

    def update_circuit_breaker_state(self, service: str, state: int):
        """Update circuit breaker state (0=closed, 1=half-open, 2=open)"""
        circuit_breaker_state.labels(service=service).set(state)

    # Cache Metrics
    def record_cache_hit(self, cache_type: str):
        """Record cache hit"""
        cache_hits_total.labels(cache_type=cache_type).inc()

    def record_cache_miss(self, cache_type: str):
        """Record cache miss"""
        cache_misses_total.labels(cache_type=cache_type).inc()

    def update_cache_size(self, cache_type: str, size: int):
        """Update cache size"""
        cache_size.labels(cache_type=cache_type).set(size)

    # Database Metrics
    def update_db_connections(self, pool: str, count: int):
        """Update active database connections"""
        db_connections_active.labels(pool=pool).set(count)

    def record_db_query(self, query_type: str, duration_seconds: float):
        """Record database query duration"""
        db_query_duration_seconds.labels(query_type=query_type).observe(duration_seconds)

    def record_db_error(self, error_type: str):
        """Record database error"""
        db_errors_total.labels(error_type=error_type).inc()

    # Strategy Metrics
    def set_strategy_active(self, strategy_name: str, active: bool):
        """Set strategy active state"""
        strategy_active.labels(strategy_name=strategy_name).set(1 if active else 0)

    def update_strategy_signal_rate(self, strategy_name: str, rate: float):
        """Update strategy signal rate"""
        strategy_signals_per_minute.labels(strategy_name=strategy_name).set(rate)

    def record_strategy_execution(self, strategy_name: str, execution_time_ms: float):
        """Record strategy execution time"""
        strategy_execution_time_ms.labels(strategy_name=strategy_name).observe(execution_time_ms)


class MetricsCollector:
    """
    Central metrics collection and management

    Provides:
    - HTTP middleware for request metrics
    - Metrics endpoint generation
    - Batch metric updates
    - Custom metric registration
    """

    def __init__(self):
        """Initialize metrics collector"""
        self.trading_metrics = TradingMetrics()
        self._custom_gauges: Dict[str, Gauge] = {}
        self._custom_counters: Dict[str, Counter] = {}

    def get_metrics_app(self):
        """Get ASGI app for /metrics endpoint"""
        return make_asgi_app(registry=registry)

    def get_metrics_text(self) -> bytes:
        """Get metrics in Prometheus text format"""
        return generate_latest(registry)

    def create_custom_gauge(
        self,
        name: str,
        description: str,
        labels: list = None
    ) -> Gauge:
        """Create a custom gauge metric"""
        if name not in self._custom_gauges:
            self._custom_gauges[name] = Gauge(
                name,
                description,
                labels or [],
                registry=registry
            )
        return self._custom_gauges[name]

    def create_custom_counter(
        self,
        name: str,
        description: str,
        labels: list = None
    ) -> Counter:
        """Create a custom counter metric"""
        if name not in self._custom_counters:
            self._custom_counters[name] = Counter(
                name,
                description,
                labels or [],
                registry=registry
            )
        return self._custom_counters[name]


class PrometheusMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware for HTTP request metrics

    Records:
    - Total requests by method, endpoint, status
    - Request duration by method, endpoint
    - Requests in progress
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and record metrics"""
        # Skip metrics endpoint to avoid recursion
        if request.url.path == "/metrics":
            return await call_next(request)

        # Increment in-progress counter
        http_requests_in_progress.inc()

        # Start timer
        start_time = time.time()

        try:
            # Process request
            response = await call_next(request)

            # Record duration
            duration = time.time() - start_time
            http_request_duration_seconds.labels(
                method=request.method,
                endpoint=self._normalize_path(request.url.path)
            ).observe(duration)

            # Record request count
            http_requests_total.labels(
                method=request.method,
                endpoint=self._normalize_path(request.url.path),
                status_code=response.status_code
            ).inc()

            return response

        except Exception as e:
            # Record error
            http_requests_total.labels(
                method=request.method,
                endpoint=self._normalize_path(request.url.path),
                status_code=500
            ).inc()
            raise

        finally:
            # Decrement in-progress counter
            http_requests_in_progress.dec()

    def _normalize_path(self, path: str) -> str:
        """
        Normalize path for metrics labels

        Replaces dynamic path segments to prevent metric explosion
        """
        # Remove query parameters
        path = path.split('?')[0]

        # Replace common dynamic segments
        parts = path.split('/')
        normalized = []
        for part in parts:
            # Skip empty parts
            if not part:
                continue
            # Replace UUIDs and numeric IDs
            if len(part) == 36 and '-' in part:
                normalized.append('{uuid}')
            elif part.isdigit():
                normalized.append('{id}')
            elif part.upper() in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'DOGEUSDT']:
                normalized.append('{symbol}')
            else:
                normalized.append(part)

        return '/' + '/'.join(normalized)


# Global metrics collector instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create global metrics collector"""
    global _metrics_collector

    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()

    return _metrics_collector


def timed_operation(metric_name: str, labels: Dict[str, str] = None):
    """
    Decorator to time async operations

    Usage:
        @timed_operation("external_api", {"service": "bybit"})
        async def fetch_price(symbol: str):
            return await exchange.get_price(symbol)
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time

                # Record to histogram
                if labels:
                    external_api_latency_seconds.labels(**labels).observe(duration)

                return result
            except Exception as e:
                duration = time.time() - start_time
                if labels:
                    external_api_errors_total.labels(
                        service=labels.get('service', 'unknown'),
                        error_type=type(e).__name__
                    ).inc()
                raise

        return wrapper
    return decorator
