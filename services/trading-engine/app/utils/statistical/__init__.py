"""
Statistical Analysis Utilities for Statistical Arbitrage Strategies

This module provides statistical testing and analysis tools for:
- Cointegration testing (pairs trading)
- Correlation analysis
- Stationarity testing
- Spread analytics

Phase 2.2 - Statistical Arbitrage Implementation
"""

from .cointegration import (
    CointegrationTester,
    CointegrationResult,
    PairScanner,
    test_adf,
    test_engle_granger,
    test_johansen,
)

__all__ = [
    "CointegrationTester",
    "CointegrationResult",
    "PairScanner",
    "test_adf",
    "test_engle_granger",
    "test_johansen",
]

__version__ = "1.0.0"
