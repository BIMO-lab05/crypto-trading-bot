"""
Endpoint Handlers Package
Extracted from main.py using Strangler Fig pattern

This package contains all HTTP endpoint handlers for the portfolio-manager service.
Handlers are thin orchestration layers that delegate business logic to service layer.

Architecture:
    Request → Handler (this package) → Service Layer → Domain Logic
"""

# Health endpoints
from .health import health_check, get_status, readiness_check

# Portfolio CRUD endpoints
from .portfolio import (
    get_portfolio,
    list_portfolios,
    get_balance,
    get_holdings,
    sync_with_trading_engine,
)

# Performance endpoints
from .performance import get_performance, get_asset_performance

# Allocation endpoints
from .allocation import get_allocation, get_rebalance_recommendations

# Transaction endpoints
from .transactions import buy_asset, sell_asset
from .transaction_history import get_transaction_history

# Optimization endpoints
from .optimization import (
    optimize_portfolio,
    get_efficient_frontier,
    execute_rebalancing,
)

__all__ = [
    # Health
    "health_check",
    "get_status",
    # Portfolio
    "get_portfolio",
    "list_portfolios",
    "get_balance",
    "get_holdings",
    "sync_with_trading_engine",
    # Performance
    "get_performance",
    "get_asset_performance",
    # Allocation
    "get_allocation",
    "get_rebalance_recommendations",
    # Transactions
    "buy_asset",
    "sell_asset",
    "get_transaction_history",
    # Optimization
    "optimize_portfolio",
    "get_efficient_frontier",
    "execute_rebalancing",
]
