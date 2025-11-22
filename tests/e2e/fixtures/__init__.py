"""
E2E Test Fixtures

Fixtures for E2E testing including service clients,
mock data generators, and test configuration.
"""

from .mock_data import (
    generate_bullish_candles,
    generate_bearish_candles,
    generate_sideways_candles,
    generate_trade_data,
    generate_portfolio_data,
)

__all__ = [
    'generate_bullish_candles',
    'generate_bearish_candles',
    'generate_sideways_candles',
    'generate_trade_data',
    'generate_portfolio_data',
]
