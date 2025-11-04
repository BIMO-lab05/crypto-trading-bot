"""
Shared Database Module
Provides database connection and ORM models for all services
"""

from .connection import (
    get_db_session,
    get_async_db_session,
    close_db,
    init_db,
    DatabaseManager
)

from .models import (
    Portfolio,
    Position,
    Trade,
    PortfolioSnapshot,
    NotificationHistory
)

from .repositories import (
    PortfolioRepository,
    PositionRepository,
    TradeRepository,
    SnapshotRepository,
    NotificationRepository
)

__all__ = [
    # Connection management
    'get_db_session',
    'get_async_db_session',
    'close_db',
    'init_db',
    'DatabaseManager',

    # Models
    'Portfolio',
    'Position',
    'Trade',
    'PortfolioSnapshot',
    'NotificationHistory',

    # Repositories
    'PortfolioRepository',
    'PositionRepository',
    'TradeRepository',
    'SnapshotRepository',
    'NotificationRepository',
]
