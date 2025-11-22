"""
Service Layer Package
Extracted from main.py using Strangler Fig pattern

This package contains business logic for the trading-engine service.
Services are isolated from HTTP concerns and can be tested independently.

Architecture:
    Handlers → Service Layer (this package) → Domain Logic
"""

from .trading_service import TradingService

__all__ = [
    "TradingService",
]
