"""
Enums for Portfolio Manager
Defines all enumeration types used across the service
"""

from enum import Enum


class AssetType(str, Enum):
    """Type of asset in the portfolio"""
    CRYPTO = "CRYPTO"
    FIAT = "FIAT"
    STABLECOIN = "STABLECOIN"


class AllocationStrategy(str, Enum):
    """Portfolio allocation strategies"""
    EQUAL_WEIGHT = "EQUAL_WEIGHT"  # Equal distribution across assets
    MARKET_CAP = "MARKET_CAP"  # Weight by market capitalization
    RISK_PARITY = "RISK_PARITY"  # Weight by risk contribution
    CUSTOM = "CUSTOM"  # Custom user-defined weights


class RebalanceReason(str, Enum):
    """Reason for portfolio rebalancing"""
    THRESHOLD_EXCEEDED = "THRESHOLD_EXCEEDED"  # Allocation drift exceeded threshold
    SCHEDULED = "SCHEDULED"  # Time-based rebalancing
    MANUAL = "MANUAL"  # User-initiated rebalancing
    RISK_ADJUSTMENT = "RISK_ADJUSTMENT"  # Risk parameters changed


class PerformanceMetric(str, Enum):
    """Performance metrics for portfolio evaluation"""
    TOTAL_RETURN = "TOTAL_RETURN"
    SHARPE_RATIO = "SHARPE_RATIO"
    SORTINO_RATIO = "SORTINO_RATIO"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"
    CALMAR_RATIO = "CALMAR_RATIO"
    WIN_RATE = "WIN_RATE"
    PROFIT_FACTOR = "PROFIT_FACTOR"
    ALPHA = "ALPHA"
    BETA = "BETA"


class TimePeriod(str, Enum):
    """Time periods for performance analysis"""
    DAY = "1d"
    WEEK = "7d"
    MONTH = "30d"
    QUARTER = "90d"
    YEAR = "365d"
    ALL = "all"
