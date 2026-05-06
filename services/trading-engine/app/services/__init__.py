"""
Service Layer Package
Extracted from main.py using Strangler Fig pattern

This package contains business logic for the trading-engine service.
Services are isolated from HTTP concerns and can be tested independently.

Architecture:
    Handlers → Service Layer (this package) → Domain Logic
"""

from .trading_service import TradingService
from .notification_client import (
    NotificationClient,
    get_notification_client,
    close_notification_client,
)
from .indicator_registry import (
    IndicatorRegistry,
    IndicatorBelowThresholdError,
    get_indicator_registry,
    reset_indicator_registry,
)

__all__ = [
    "TradingService",
    "NotificationClient",
    "get_notification_client",
    "close_notification_client",
    "IndicatorRegistry",
    "IndicatorBelowThresholdError",
    "get_indicator_registry",
    "reset_indicator_registry",
]
