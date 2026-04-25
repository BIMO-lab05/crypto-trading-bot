"""
Correlation Analysis Endpoint Handlers
Purpose: HTTP handlers for portfolio correlation analysis and risk management

Phase 3.1: Portfolio Correlation Analysis for Enhanced Risk Management
Created: 2025-12-11

Endpoints:
- GET /api/v1/risk/correlation - Get correlation matrix
- GET /api/v1/risk/correlation/status - Get correlation manager status
- GET /api/v1/risk/correlation/score - Get portfolio diversification score
- GET /api/v1/risk/correlation/pair/{symbol_a}/{symbol_b} - Get pair correlation
- GET /api/v1/risk/correlation/alerts - Get correlation alerts
- POST /api/v1/risk/correlation/check-position - Check if can open position
- POST /api/v1/risk/correlation/update - Manually trigger correlation update
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from app.risk import (
    get_correlation_manager,
    CorrelationManager,
    AlertSeverity,
)
from app.position_manager import get_position_manager
from app.config import get_settings

logger = logging.getLogger(__name__)


async def get_correlation_status() -> Dict[str, Any]:
    """
    Get correlation manager status

    Returns:
        Dictionary with manager status and configuration
    """
    manager = get_correlation_manager()
    status = manager.get_status()

    return {
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status
    }


async def get_correlation_matrix() -> Dict[str, Any]:
    """
    Get the current correlation matrix for all trading pairs

    Returns:
        Correlation matrix with short-term and long-term correlations
    """
    manager = get_correlation_manager()
    matrix = await manager.get_correlation_matrix()

    if not matrix:
        return {
            "success": False,
            "error": "Correlation matrix not available. Run update first.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    # Also get highly correlated pairs for convenience
    high_corr_pairs = matrix.get_highly_correlated_pairs(threshold=0.6)

    return {
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "matrix": matrix.to_dict(),
        "highly_correlated_pairs": [
            {
                "symbol_a": pair[0],
                "symbol_b": pair[1],
                "correlation": round(pair[2], 4)
            }
            for pair in high_corr_pairs
        ],
        "pair_count": len(matrix.symbols),
        "data_points": matrix.data_points
    }


async def get_diversification_score(symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Get portfolio diversification score

    If no symbols provided, calculates score for currently open positions.

    Args:
        symbols: Optional list of symbols (uses open positions if not provided)

    Returns:
        Diversification score with recommendations
    """
    manager = get_correlation_manager()

    # Use open positions if no symbols provided
    if not symbols:
        position_manager = get_position_manager()
        open_positions = position_manager.get_open_positions()
        symbols = [pos.symbol for pos in open_positions]

    score = await manager.get_diversification_score(symbols)

    return {
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "diversification": score.to_dict(),
        "analyzed_symbols": symbols
    }


async def get_pair_correlation(symbol_a: str, symbol_b: str) -> Dict[str, Any]:
    """
    Get detailed correlation info for a specific pair

    Args:
        symbol_a: First trading symbol (e.g., "BTCUSDT")
        symbol_b: Second trading symbol (e.g., "ETHUSDT")

    Returns:
        Correlation details including position recommendations
    """
    manager = get_correlation_manager()
    pair_info = manager.get_pair_correlation(symbol_a, symbol_b)

    return {
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pair": pair_info
    }


async def get_correlation_alerts(
    min_severity: str = "WARNING"
) -> Dict[str, Any]:
    """
    Get correlation alerts

    Args:
        min_severity: Minimum severity level ("INFO", "WARNING", "HIGH", "CRITICAL")

    Returns:
        List of correlation alerts
    """
    manager = get_correlation_manager()

    # Convert string to enum
    try:
        severity = AlertSeverity(min_severity.upper())
    except ValueError:
        severity = AlertSeverity.WARNING

    alerts = manager.get_alerts(min_severity=severity)

    return {
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alert_count": len(alerts),
        "min_severity": severity.value,
        "alerts": [alert.to_dict() for alert in alerts]
    }


async def check_can_open_position(symbol: str) -> Dict[str, Any]:
    """
    Check if a new position can be opened based on correlation limits

    Args:
        symbol: Trading symbol for the new position

    Returns:
        Whether position can be opened and any restrictions
    """
    manager = get_correlation_manager()
    position_manager = get_position_manager()

    # Get currently open positions
    open_positions = position_manager.get_open_positions()
    open_symbols = [pos.symbol for pos in open_positions]

    # Check if can open
    can_open, reason = await manager.can_open_position(symbol, open_symbols)

    # Get position size adjustment
    size_adjustment = manager.get_position_size_adjustment(symbol, open_symbols)

    return {
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "can_open": can_open,
        "reason": reason,
        "position_size_adjustment": round(size_adjustment, 2),
        "current_open_positions": open_symbols
    }


async def update_correlations(
    price_data: Optional[Dict[str, List[float]]] = None
) -> Dict[str, Any]:
    """
    Manually trigger correlation update

    If no price data provided, fetches latest prices from market data service.

    Args:
        price_data: Optional dictionary of symbol -> price list

    Returns:
        Update status and new correlation matrix summary
    """
    manager = get_correlation_manager()
    settings = get_settings()

    # If no price data provided, try to fetch from market data service
    if not price_data:
        try:
            import httpx

            price_data = {}

            # Fetch recent candles for each trading symbol
            async with httpx.AsyncClient(timeout=30.0) as client:
                for symbol in settings.trading_symbols:
                    try:
                        response = await client.get(
                            f"{settings.market_data_url}/api/v1/candles/{symbol}",
                            params={
                                "interval": "60",  # Hourly candles
                                "limit": 60  # 60 hours of data
                            }
                        )
                        if response.status_code == 200:
                            data = response.json()
                            if "candles" in data:
                                prices = [float(c["close"]) for c in data["candles"]]
                                if prices:
                                    price_data[symbol] = prices
                                    logger.debug(
                                        f"Fetched {len(prices)} prices for {symbol}"
                                    )
                    except Exception as e:
                        logger.warning(f"Failed to fetch prices for {symbol}: {e}")

            if not price_data:
                return {
                    "success": False,
                    "error": "Could not fetch price data from market data service",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

        except ImportError:
            return {
                "success": False,
                "error": "httpx not available and no price data provided",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    # Update correlations
    matrix = await manager.update_correlations(price_data)

    # Get summary statistics
    high_corr_pairs = matrix.get_highly_correlated_pairs(threshold=0.7)

    return {
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbols_updated": len(price_data),
        "symbols": list(price_data.keys()),
        "data_points": matrix.data_points,
        "highly_correlated_pairs_count": len(high_corr_pairs),
        "highly_correlated_pairs": [
            {
                "symbol_a": pair[0],
                "symbol_b": pair[1],
                "correlation": round(pair[2], 4)
            }
            for pair in high_corr_pairs[:5]  # Top 5 most correlated
        ],
        "last_updated": matrix.last_updated.isoformat()
    }


async def initialize_correlation_manager() -> Dict[str, Any]:
    """
    Initialize the correlation manager with Redis connection

    Returns:
        Initialization status
    """
    manager = get_correlation_manager()
    settings = get_settings()

    # Initialize with Redis URL from settings
    success = await manager.initialize(redis_url=settings.redis_url)

    return {
        "success": success,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": manager.get_status()
    }


# =============================================================================
# ENDPOINT EXPORTS
# =============================================================================

__all__ = [
    "get_correlation_status",
    "get_correlation_matrix",
    "get_diversification_score",
    "get_pair_correlation",
    "get_correlation_alerts",
    "check_can_open_position",
    "update_correlations",
    "initialize_correlation_manager",
]
