"""
Local Database Module for Trading Engine
Provides database connection and ORM models
"""

from .connection import (
    db_manager,
    get_db_session,
    get_async_db_session,
    close_db,
    init_db,
    DatabaseManager,
    get_db
)

from .models import (
    Portfolio,
    Position,
    Trade,
    PortfolioSnapshot,
    NotificationHistory
)

__all__ = [
    # Connection management
    'db_manager',
    'get_db_session',
    'get_async_db_session',
    'close_db',
    'init_db',
    'DatabaseManager',
    'get_db',

    # Models
    'Portfolio',
    'Position',
    'Trade',
    'PortfolioSnapshot',
    'NotificationHistory',
]
