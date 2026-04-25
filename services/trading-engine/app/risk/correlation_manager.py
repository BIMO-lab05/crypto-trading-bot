"""
Portfolio Correlation Manager
Purpose: Track correlations between trading pairs for enhanced risk management

Phase 3.1: Portfolio Correlation Analysis
Created: 2025-12-11

This module provides:
1. Pearson correlation calculation between all trading pairs
2. Rolling correlation tracking (30-day, 60-day windows)
3. Redis caching for fast access to correlation matrix
4. Hourly correlation updates
5. Portfolio diversification scoring (0-100)
6. Alerts when correlation exceeds thresholds
7. Correlation-based position limits

Key Features:
- Prevents opening highly correlated positions (>0.7 correlation)
- Alerts when correlation between positions > 0.8
- Max 3 positions with correlation > 0.6
- Dynamic position size adjustment based on correlation changes

Usage:
    manager = get_correlation_manager()

    # Update correlations with price data
    await manager.update_correlations(price_data)

    # Check if can open position (correlation limits)
    can_open, reason = await manager.can_open_position("BTCUSDT", open_positions)

    # Get diversification score
    score = await manager.get_diversification_score(open_positions)

    # Get correlation matrix
    matrix = await manager.get_correlation_matrix()
"""

import logging
import asyncio
import json
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
import numpy as np
from scipy import stats

# Optional Redis import - gracefully handle if not available
try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class CorrelationConfig:
    """
    Configuration for correlation analysis and risk management

    All thresholds are based on research-backed best practices:
    - 0.7+ correlation indicates potential redundancy
    - 0.8+ correlation is high risk for concentrated positions
    - 30-day window balances responsiveness vs stability
    """

    # Correlation calculation settings
    rolling_window_short: int = 30  # 30-day rolling correlation (default)
    rolling_window_long: int = 60   # 60-day rolling correlation (long-term)
    min_data_points: int = 20       # Minimum data points for correlation calculation

    # Correlation thresholds for risk management
    high_correlation_threshold: float = 0.7   # Prevent opening new positions
    critical_correlation_threshold: float = 0.8  # Alert when exceeded
    moderate_correlation_threshold: float = 0.6  # Track but allow

    # Position limits based on correlation
    max_correlated_positions: int = 3  # Max positions with correlation > 0.6
    position_size_reduction_factor: float = 0.5  # Reduce size by 50% for correlated pairs

    # Cache settings
    cache_ttl_seconds: int = 3600  # 1 hour cache TTL
    update_interval_seconds: int = 3600  # Update hourly

    # Redis configuration
    redis_key_prefix: str = "correlation:"
    redis_matrix_key: str = "correlation:matrix"
    redis_scores_key: str = "correlation:scores"
    redis_alerts_key: str = "correlation:alerts"

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return asdict(self)


# =============================================================================
# DATA MODELS
# =============================================================================

class AlertSeverity(Enum):
    """Alert severity levels for correlation warnings"""
    INFO = "INFO"           # Informational (correlation > 0.5)
    WARNING = "WARNING"     # Warning (correlation > 0.6)
    HIGH = "HIGH"           # High risk (correlation > 0.7)
    CRITICAL = "CRITICAL"   # Critical (correlation > 0.8)


@dataclass
class CorrelationAlert:
    """
    Alert for high correlation between positions

    Attributes:
        symbol_a: First trading symbol
        symbol_b: Second trading symbol
        correlation: Correlation coefficient (-1 to 1)
        severity: Alert severity level
        message: Human-readable alert message
        timestamp: When the alert was generated
    """
    symbol_a: str
    symbol_b: str
    correlation: float
    severity: AlertSeverity
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary for JSON serialization"""
        return {
            "symbol_a": self.symbol_a,
            "symbol_b": self.symbol_b,
            "correlation": round(self.correlation, 4),
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class CorrelationMatrix:
    """
    Correlation matrix for all trading pairs

    Stores both short-term (30-day) and long-term (60-day) correlations.

    Attributes:
        symbols: List of trading symbols in the matrix
        short_term: 30-day rolling correlation matrix (dict of dicts)
        long_term: 60-day rolling correlation matrix (dict of dicts)
        last_updated: When the matrix was last updated
        data_points: Number of data points used for calculation
    """
    symbols: List[str]
    short_term: Dict[str, Dict[str, float]]
    long_term: Dict[str, Dict[str, float]]
    last_updated: datetime
    data_points: int = 0

    def get_correlation(
        self,
        symbol_a: str,
        symbol_b: str,
        window: str = "short"
    ) -> Optional[float]:
        """
        Get correlation between two symbols

        Args:
            symbol_a: First symbol
            symbol_b: Second symbol
            window: "short" (30-day) or "long" (60-day)

        Returns:
            Correlation coefficient or None if not available
        """
        # Same symbol always has correlation of 1.0
        if symbol_a == symbol_b:
            return 1.0

        matrix = self.short_term if window == "short" else self.long_term

        # Try both orderings (matrix may be stored either way)
        if symbol_a in matrix and symbol_b in matrix[symbol_a]:
            return matrix[symbol_a][symbol_b]
        if symbol_b in matrix and symbol_a in matrix[symbol_b]:
            return matrix[symbol_b][symbol_a]

        return None

    def get_highly_correlated_pairs(
        self,
        threshold: float = 0.7,
        window: str = "short"
    ) -> List[Tuple[str, str, float]]:
        """
        Get all pairs with correlation above threshold

        Args:
            threshold: Minimum correlation threshold
            window: "short" or "long" window

        Returns:
            List of (symbol_a, symbol_b, correlation) tuples
        """
        matrix = self.short_term if window == "short" else self.long_term
        pairs = []

        for symbol_a in matrix:
            for symbol_b, corr in matrix[symbol_a].items():
                if abs(corr) >= threshold and symbol_a < symbol_b:  # Avoid duplicates
                    pairs.append((symbol_a, symbol_b, corr))

        # Sort by absolute correlation descending
        pairs.sort(key=lambda x: abs(x[2]), reverse=True)
        return pairs

    def to_dict(self) -> Dict[str, Any]:
        """Convert matrix to dictionary for JSON serialization"""
        return {
            "symbols": self.symbols,
            "short_term": self.short_term,
            "long_term": self.long_term,
            "last_updated": self.last_updated.isoformat(),
            "data_points": self.data_points
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CorrelationMatrix":
        """Create matrix from dictionary"""
        return cls(
            symbols=data["symbols"],
            short_term=data["short_term"],
            long_term=data["long_term"],
            last_updated=datetime.fromisoformat(data["last_updated"]),
            data_points=data.get("data_points", 0)
        )


@dataclass
class DiversificationScore:
    """
    Portfolio diversification score (0-100)

    Higher score indicates better diversification:
    - 90-100: Excellent diversification
    - 70-89: Good diversification
    - 50-69: Moderate diversification
    - 30-49: Poor diversification
    - 0-29: High concentration risk

    Attributes:
        score: Overall diversification score (0-100)
        position_count: Number of open positions
        avg_correlation: Average pairwise correlation
        max_correlation: Maximum pairwise correlation
        correlated_pairs_count: Number of highly correlated pairs (>0.7)
        risk_level: Risk level description
        recommendations: List of recommendations to improve diversification
    """
    score: float
    position_count: int
    avg_correlation: float
    max_correlation: float
    correlated_pairs_count: int
    risk_level: str
    recommendations: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert score to dictionary"""
        return {
            "score": round(self.score, 2),
            "position_count": self.position_count,
            "avg_correlation": round(self.avg_correlation, 4),
            "max_correlation": round(self.max_correlation, 4),
            "correlated_pairs_count": self.correlated_pairs_count,
            "risk_level": self.risk_level,
            "recommendations": self.recommendations,
            "timestamp": self.timestamp.isoformat()
        }


# =============================================================================
# CORRELATION MANAGER
# =============================================================================

class CorrelationManager:
    """
    Portfolio Correlation Manager

    Manages correlation tracking between trading pairs for enhanced
    risk management and diversification.

    Key Features:
    - Calculate Pearson correlation between all trading pairs
    - Track rolling correlations (30-day, 60-day windows)
    - Cache correlation matrix in Redis for fast access
    - Update correlations hourly
    - Calculate portfolio diversification score
    - Alert on high correlations
    - Enforce correlation-based position limits

    Usage:
        manager = CorrelationManager()
        await manager.initialize(redis_url)

        # Update with price data
        await manager.update_correlations({
            "BTCUSDT": [100000, 100500, 99800, ...],  # 30+ prices
            "ETHUSDT": [3500, 3520, 3480, ...],
            ...
        })

        # Check before opening position
        can_open, reason = await manager.can_open_position(
            "BTCUSDT",
            ["ETHUSDT", "SOLUSDT"]  # Current open position symbols
        )

        # Get diversification score
        score = await manager.get_diversification_score(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    """

    def __init__(self, config: Optional[CorrelationConfig] = None):
        """
        Initialize correlation manager

        Args:
            config: Correlation configuration (uses defaults if not provided)
        """
        self.config = config or CorrelationConfig()
        self.redis: Optional[Any] = None  # Redis client (optional)
        self.correlation_matrix: Optional[CorrelationMatrix] = None
        self.price_history: Dict[str, List[float]] = {}  # In-memory price history
        self.alerts: List[CorrelationAlert] = []  # Recent alerts
        self.last_update: Optional[datetime] = None
        self._update_lock = asyncio.Lock()  # Prevent concurrent updates
        self._initialized = False

        logger.info(
            f"CorrelationManager created with config: "
            f"high_threshold={self.config.high_correlation_threshold}, "
            f"critical_threshold={self.config.critical_correlation_threshold}, "
            f"max_correlated_positions={self.config.max_correlated_positions}"
        )

    async def initialize(self, redis_url: Optional[str] = None) -> bool:
        """
        Initialize the correlation manager with optional Redis connection

        Args:
            redis_url: Redis connection URL (optional)

        Returns:
            True if initialized successfully
        """
        if self._initialized:
            logger.warning("CorrelationManager already initialized")
            return True

        # Try to connect to Redis if URL provided and Redis is available
        if redis_url and REDIS_AVAILABLE:
            try:
                self.redis = await aioredis.from_url(
                    redis_url,
                    encoding="utf-8",
                    decode_responses=True
                )
                # Test connection
                await self.redis.ping()
                logger.info(f"CorrelationManager connected to Redis: {redis_url}")

                # Try to load existing matrix from cache
                cached = await self._load_from_cache()
                if cached:
                    logger.info("Loaded correlation matrix from Redis cache")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}. Using in-memory storage.")
                self.redis = None
        else:
            if redis_url and not REDIS_AVAILABLE:
                logger.warning("Redis URL provided but redis package not available")
            logger.info("CorrelationManager using in-memory storage (no Redis)")

        self._initialized = True
        logger.info("CorrelationManager initialized successfully")
        return True

    async def close(self):
        """Close Redis connection if open"""
        if self.redis:
            await self.redis.close()
            self.redis = None
        self._initialized = False
        logger.info("CorrelationManager closed")

    # =========================================================================
    # CORRELATION CALCULATION
    # =========================================================================

    def calculate_correlation(
        self,
        prices_a: List[float],
        prices_b: List[float]
    ) -> Optional[float]:
        """
        Calculate Pearson correlation coefficient between two price series

        Args:
            prices_a: Price series for first symbol
            prices_b: Price series for second symbol

        Returns:
            Correlation coefficient (-1 to 1) or None if insufficient data
        """
        # Ensure same length
        min_len = min(len(prices_a), len(prices_b))
        if min_len < self.config.min_data_points:
            logger.debug(
                f"Insufficient data for correlation: {min_len} points "
                f"(min: {self.config.min_data_points})"
            )
            return None

        # Use most recent data
        a = np.array(prices_a[-min_len:])
        b = np.array(prices_b[-min_len:])

        # Calculate returns (percentage changes) - more stable than raw prices
        returns_a = np.diff(a) / a[:-1]
        returns_b = np.diff(b) / b[:-1]

        # Handle edge cases (no variance)
        if np.std(returns_a) == 0 or np.std(returns_b) == 0:
            logger.debug("Zero variance in returns, cannot calculate correlation")
            return None

        try:
            # Pearson correlation
            correlation, p_value = stats.pearsonr(returns_a, returns_b)

            # Log if statistically significant
            if p_value < 0.05:
                logger.debug(
                    f"Correlation calculated: {correlation:.4f} (p-value: {p_value:.4f})"
                )

            return float(correlation)
        except Exception as e:
            logger.error(f"Error calculating correlation: {e}")
            return None

    async def update_correlations(
        self,
        price_data: Dict[str, List[float]]
    ) -> CorrelationMatrix:
        """
        Update correlation matrix with new price data

        This method should be called hourly (or when significant price updates occur).

        Args:
            price_data: Dictionary mapping symbol to list of prices
                       e.g., {"BTCUSDT": [100000, 100500, ...], "ETHUSDT": [...]}

        Returns:
            Updated CorrelationMatrix
        """
        async with self._update_lock:
            # Update internal price history
            for symbol, prices in price_data.items():
                if symbol not in self.price_history:
                    self.price_history[symbol] = []

                # Append new prices and trim to max window
                self.price_history[symbol].extend(prices)
                max_history = self.config.rolling_window_long + 10  # Buffer
                if len(self.price_history[symbol]) > max_history:
                    self.price_history[symbol] = self.price_history[symbol][-max_history:]

            symbols = list(self.price_history.keys())
            n_symbols = len(symbols)

            logger.info(
                f"Updating correlations for {n_symbols} symbols: {symbols}"
            )

            # Calculate correlation matrices
            short_term: Dict[str, Dict[str, float]] = {}
            long_term: Dict[str, Dict[str, float]] = {}

            for i, symbol_a in enumerate(symbols):
                short_term[symbol_a] = {}
                long_term[symbol_a] = {}

                for j, symbol_b in enumerate(symbols):
                    if i >= j:  # Skip diagonal and lower triangle (symmetric matrix)
                        continue

                    prices_a = self.price_history[symbol_a]
                    prices_b = self.price_history[symbol_b]

                    # Short-term correlation (30-day)
                    short_window = min(
                        self.config.rolling_window_short,
                        len(prices_a),
                        len(prices_b)
                    )
                    if short_window >= self.config.min_data_points:
                        corr_short = self.calculate_correlation(
                            prices_a[-short_window:],
                            prices_b[-short_window:]
                        )
                        if corr_short is not None:
                            short_term[symbol_a][symbol_b] = corr_short

                    # Long-term correlation (60-day)
                    long_window = min(
                        self.config.rolling_window_long,
                        len(prices_a),
                        len(prices_b)
                    )
                    if long_window >= self.config.min_data_points:
                        corr_long = self.calculate_correlation(
                            prices_a[-long_window:],
                            prices_b[-long_window:]
                        )
                        if corr_long is not None:
                            long_term[symbol_a][symbol_b] = corr_long

            # Create matrix object
            self.correlation_matrix = CorrelationMatrix(
                symbols=symbols,
                short_term=short_term,
                long_term=long_term,
                last_updated=datetime.now(timezone.utc),
                data_points=min(len(v) for v in self.price_history.values()) if self.price_history else 0
            )

            self.last_update = datetime.now(timezone.utc)

            # Generate alerts for high correlations
            self._generate_alerts()

            # Cache to Redis if available
            await self._save_to_cache()

            logger.info(
                f"Correlation matrix updated: {n_symbols} symbols, "
                f"{len(self.alerts)} alerts generated"
            )

            return self.correlation_matrix

    def _generate_alerts(self):
        """Generate alerts for high correlations"""
        if not self.correlation_matrix:
            return

        self.alerts = []

        # Check all pairs for high correlations
        for symbol_a in self.correlation_matrix.short_term:
            for symbol_b, corr in self.correlation_matrix.short_term[symbol_a].items():
                abs_corr = abs(corr)

                if abs_corr >= self.config.critical_correlation_threshold:
                    severity = AlertSeverity.CRITICAL
                    message = (
                        f"CRITICAL: {symbol_a} and {symbol_b} have {corr:.2%} correlation. "
                        f"Consider closing one position to reduce concentration risk."
                    )
                elif abs_corr >= self.config.high_correlation_threshold:
                    severity = AlertSeverity.HIGH
                    message = (
                        f"HIGH: {symbol_a} and {symbol_b} have {corr:.2%} correlation. "
                        f"New positions in these pairs should be avoided."
                    )
                elif abs_corr >= self.config.moderate_correlation_threshold:
                    severity = AlertSeverity.WARNING
                    message = (
                        f"WARNING: {symbol_a} and {symbol_b} have {corr:.2%} correlation. "
                        f"Position sizes may be reduced."
                    )
                else:
                    continue  # No alert needed

                alert = CorrelationAlert(
                    symbol_a=symbol_a,
                    symbol_b=symbol_b,
                    correlation=corr,
                    severity=severity,
                    message=message
                )
                self.alerts.append(alert)

        # Sort alerts by severity (critical first)
        severity_order = {
            AlertSeverity.CRITICAL: 0,
            AlertSeverity.HIGH: 1,
            AlertSeverity.WARNING: 2,
            AlertSeverity.INFO: 3
        }
        self.alerts.sort(key=lambda a: (severity_order[a.severity], -abs(a.correlation)))

    # =========================================================================
    # POSITION LIMIT CHECKS
    # =========================================================================

    async def can_open_position(
        self,
        symbol: str,
        open_position_symbols: List[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a new position can be opened based on correlation limits

        Rules:
        1. Cannot open position if highly correlated (>0.7) with existing position
        2. Max 3 positions with moderate correlation (>0.6)

        Args:
            symbol: Symbol for the new position
            open_position_symbols: List of symbols with open positions

        Returns:
            Tuple of (can_open, reason_if_blocked)
        """
        # No restrictions if no correlation data
        if not self.correlation_matrix:
            logger.debug("No correlation matrix available, allowing position")
            return True, None

        # No restrictions if no existing positions
        if not open_position_symbols:
            return True, None

        # Check correlation with each open position
        high_corr_count = 0

        for existing_symbol in open_position_symbols:
            corr = self.correlation_matrix.get_correlation(symbol, existing_symbol)

            if corr is None:
                continue  # No data, assume uncorrelated

            abs_corr = abs(corr)

            # Block if highly correlated (>0.7)
            if abs_corr >= self.config.high_correlation_threshold:
                reason = (
                    f"Cannot open {symbol}: {abs_corr:.2%} correlation with "
                    f"existing position {existing_symbol} exceeds threshold "
                    f"({self.config.high_correlation_threshold:.0%})"
                )
                logger.warning(reason)
                return False, reason

            # Count moderate correlations
            if abs_corr >= self.config.moderate_correlation_threshold:
                high_corr_count += 1

        # Check max correlated positions limit
        if high_corr_count >= self.config.max_correlated_positions:
            reason = (
                f"Cannot open {symbol}: Would exceed max correlated positions limit "
                f"({self.config.max_correlated_positions}). Currently have "
                f"{high_corr_count} moderately correlated positions."
            )
            logger.warning(reason)
            return False, reason

        logger.debug(
            f"Position allowed: {symbol} (correlated positions: {high_corr_count})"
        )
        return True, None

    def get_position_size_adjustment(
        self,
        symbol: str,
        open_position_symbols: List[str]
    ) -> float:
        """
        Get position size adjustment factor based on correlation

        If the new position is correlated with existing positions,
        reduce the size to manage concentration risk.

        Args:
            symbol: Symbol for the new position
            open_position_symbols: List of symbols with open positions

        Returns:
            Position size multiplier (0.0 to 1.0)
        """
        if not self.correlation_matrix or not open_position_symbols:
            return 1.0  # Full size

        max_correlation = 0.0

        for existing_symbol in open_position_symbols:
            corr = self.correlation_matrix.get_correlation(symbol, existing_symbol)
            if corr is not None:
                max_correlation = max(max_correlation, abs(corr))

        # No adjustment if low correlation
        if max_correlation < self.config.moderate_correlation_threshold:
            return 1.0

        # Linear reduction based on correlation
        # 0.6 correlation -> 100% size
        # 0.7 correlation -> 50% size (reduction factor)
        # Higher correlations are blocked by can_open_position()
        adjustment = 1.0 - (
            (max_correlation - self.config.moderate_correlation_threshold) /
            (self.config.high_correlation_threshold - self.config.moderate_correlation_threshold) *
            (1.0 - self.config.position_size_reduction_factor)
        )

        adjustment = max(self.config.position_size_reduction_factor, min(1.0, adjustment))

        logger.debug(
            f"Position size adjustment for {symbol}: {adjustment:.2f} "
            f"(max correlation: {max_correlation:.2%})"
        )

        return adjustment

    # =========================================================================
    # DIVERSIFICATION SCORING
    # =========================================================================

    async def get_diversification_score(
        self,
        position_symbols: List[str]
    ) -> DiversificationScore:
        """
        Calculate portfolio diversification score (0-100)

        Score calculation:
        - Starts at 100
        - Deducts points for high correlations
        - Deducts points for concentration (few positions)
        - Adjusts based on average correlation

        Args:
            position_symbols: List of symbols with open positions

        Returns:
            DiversificationScore with detailed metrics
        """
        n_positions = len(position_symbols)

        # Edge cases
        if n_positions == 0:
            return DiversificationScore(
                score=100.0,
                position_count=0,
                avg_correlation=0.0,
                max_correlation=0.0,
                correlated_pairs_count=0,
                risk_level="No Positions",
                recommendations=["Open positions to begin trading"]
            )

        if n_positions == 1:
            return DiversificationScore(
                score=50.0,
                position_count=1,
                avg_correlation=0.0,
                max_correlation=0.0,
                correlated_pairs_count=0,
                risk_level="Concentrated",
                recommendations=[
                    "Consider adding uncorrelated positions for diversification",
                    "Single position carries higher idiosyncratic risk"
                ]
            )

        # Calculate pairwise correlations
        correlations = []
        max_corr = 0.0
        high_corr_count = 0

        if self.correlation_matrix:
            for i, symbol_a in enumerate(position_symbols):
                for j, symbol_b in enumerate(position_symbols):
                    if i >= j:
                        continue

                    corr = self.correlation_matrix.get_correlation(symbol_a, symbol_b)
                    if corr is not None:
                        abs_corr = abs(corr)
                        correlations.append(abs_corr)
                        max_corr = max(max_corr, abs_corr)

                        if abs_corr >= self.config.high_correlation_threshold:
                            high_corr_count += 1

        # Calculate average correlation
        avg_corr = np.mean(correlations) if correlations else 0.0

        # Calculate score
        score = 100.0
        recommendations = []

        # Deduct for high average correlation (max -30 points)
        avg_deduction = min(30, avg_corr * 50)
        score -= avg_deduction

        # Deduct for max correlation (max -20 points)
        max_deduction = min(20, max_corr * 25)
        score -= max_deduction

        # Deduct for highly correlated pairs (max -30 points)
        pair_deduction = min(30, high_corr_count * 10)
        score -= pair_deduction

        # Bonus for position diversity (up to +10 points)
        if n_positions >= 5:
            score += 10
        elif n_positions >= 3:
            score += 5

        # Ensure score is in valid range
        score = max(0.0, min(100.0, score))

        # Determine risk level
        if score >= 90:
            risk_level = "Excellent"
        elif score >= 70:
            risk_level = "Good"
        elif score >= 50:
            risk_level = "Moderate"
        elif score >= 30:
            risk_level = "Poor"
        else:
            risk_level = "Critical"

        # Generate recommendations
        if high_corr_count > 0:
            recommendations.append(
                f"Consider reducing exposure: {high_corr_count} highly correlated pairs"
            )

        if avg_corr > 0.5:
            recommendations.append(
                f"Average correlation ({avg_corr:.2%}) is high. Add uncorrelated assets."
            )

        if n_positions < 3:
            recommendations.append(
                "Increase position count for better diversification"
            )

        if max_corr > self.config.critical_correlation_threshold:
            recommendations.append(
                f"CRITICAL: Max correlation ({max_corr:.2%}) indicates concentration risk"
            )

        if not recommendations:
            recommendations.append("Portfolio is well-diversified. Maintain current allocation.")

        return DiversificationScore(
            score=score,
            position_count=n_positions,
            avg_correlation=float(avg_corr),
            max_correlation=float(max_corr),
            correlated_pairs_count=high_corr_count,
            risk_level=risk_level,
            recommendations=recommendations
        )

    # =========================================================================
    # GETTERS
    # =========================================================================

    async def get_correlation_matrix(self) -> Optional[CorrelationMatrix]:
        """
        Get the current correlation matrix

        Returns cached matrix or loads from Redis if available.

        Returns:
            CorrelationMatrix or None if not calculated yet
        """
        if self.correlation_matrix:
            return self.correlation_matrix

        # Try to load from cache
        await self._load_from_cache()
        return self.correlation_matrix

    def get_alerts(
        self,
        min_severity: AlertSeverity = AlertSeverity.WARNING
    ) -> List[CorrelationAlert]:
        """
        Get correlation alerts filtered by minimum severity

        Args:
            min_severity: Minimum severity level to include

        Returns:
            List of alerts at or above the specified severity
        """
        severity_order = {
            AlertSeverity.CRITICAL: 0,
            AlertSeverity.HIGH: 1,
            AlertSeverity.WARNING: 2,
            AlertSeverity.INFO: 3
        }

        min_level = severity_order.get(min_severity, 3)

        return [
            alert for alert in self.alerts
            if severity_order.get(alert.severity, 3) <= min_level
        ]

    def get_pair_correlation(
        self,
        symbol_a: str,
        symbol_b: str
    ) -> Dict[str, Any]:
        """
        Get detailed correlation info for a specific pair

        Args:
            symbol_a: First symbol
            symbol_b: Second symbol

        Returns:
            Dictionary with correlation details
        """
        if not self.correlation_matrix:
            return {
                "symbol_a": symbol_a,
                "symbol_b": symbol_b,
                "error": "Correlation matrix not available"
            }

        short_corr = self.correlation_matrix.get_correlation(symbol_a, symbol_b, "short")
        long_corr = self.correlation_matrix.get_correlation(symbol_a, symbol_b, "long")

        return {
            "symbol_a": symbol_a,
            "symbol_b": symbol_b,
            "short_term_correlation": short_corr,
            "long_term_correlation": long_corr,
            "is_highly_correlated": short_corr is not None and abs(short_corr) >= self.config.high_correlation_threshold,
            "position_allowed": short_corr is None or abs(short_corr) < self.config.high_correlation_threshold,
            "size_adjustment": self.get_position_size_adjustment(symbol_a, [symbol_b]) if short_corr else 1.0
        }

    # =========================================================================
    # CACHE MANAGEMENT
    # =========================================================================

    async def _save_to_cache(self) -> bool:
        """Save correlation matrix to Redis cache"""
        if not self.redis or not self.correlation_matrix:
            return False

        try:
            # Save matrix
            matrix_json = json.dumps(self.correlation_matrix.to_dict())
            await self.redis.setex(
                self.config.redis_matrix_key,
                self.config.cache_ttl_seconds,
                matrix_json
            )

            # Save alerts
            alerts_json = json.dumps([a.to_dict() for a in self.alerts])
            await self.redis.setex(
                self.config.redis_alerts_key,
                self.config.cache_ttl_seconds,
                alerts_json
            )

            logger.debug("Correlation data saved to Redis cache")
            return True
        except Exception as e:
            logger.error(f"Failed to save correlation data to cache: {e}")
            return False

    async def _load_from_cache(self) -> bool:
        """Load correlation matrix from Redis cache"""
        if not self.redis:
            return False

        try:
            # Load matrix
            matrix_json = await self.redis.get(self.config.redis_matrix_key)
            if matrix_json:
                self.correlation_matrix = CorrelationMatrix.from_dict(
                    json.loads(matrix_json)
                )
                logger.debug("Loaded correlation matrix from Redis cache")

            # Load alerts
            alerts_json = await self.redis.get(self.config.redis_alerts_key)
            if alerts_json:
                alerts_data = json.loads(alerts_json)
                self.alerts = [
                    CorrelationAlert(
                        symbol_a=a["symbol_a"],
                        symbol_b=a["symbol_b"],
                        correlation=a["correlation"],
                        severity=AlertSeverity(a["severity"]),
                        message=a["message"],
                        timestamp=datetime.fromisoformat(a["timestamp"])
                    )
                    for a in alerts_data
                ]

            return self.correlation_matrix is not None
        except Exception as e:
            logger.error(f"Failed to load correlation data from cache: {e}")
            return False

    async def clear_cache(self) -> bool:
        """Clear all cached correlation data"""
        if not self.redis:
            return False

        try:
            await self.redis.delete(self.config.redis_matrix_key)
            await self.redis.delete(self.config.redis_alerts_key)
            await self.redis.delete(self.config.redis_scores_key)
            logger.info("Correlation cache cleared")
            return True
        except Exception as e:
            logger.error(f"Failed to clear correlation cache: {e}")
            return False

    # =========================================================================
    # STATUS AND METRICS
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get correlation manager status"""
        return {
            "initialized": self._initialized,
            "redis_connected": self.redis is not None,
            "matrix_available": self.correlation_matrix is not None,
            "symbols_tracked": len(self.price_history),
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "data_points": self.correlation_matrix.data_points if self.correlation_matrix else 0,
            "alert_count": len(self.alerts),
            "critical_alerts": len([a for a in self.alerts if a.severity == AlertSeverity.CRITICAL]),
            "config": {
                "high_correlation_threshold": self.config.high_correlation_threshold,
                "critical_correlation_threshold": self.config.critical_correlation_threshold,
                "max_correlated_positions": self.config.max_correlated_positions,
                "update_interval_seconds": self.config.update_interval_seconds
            }
        }


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_correlation_manager: Optional[CorrelationManager] = None


def get_correlation_manager() -> CorrelationManager:
    """
    Get or create the global CorrelationManager instance

    Returns:
        CorrelationManager singleton instance
    """
    global _correlation_manager
    if _correlation_manager is None:
        _correlation_manager = CorrelationManager()
    return _correlation_manager


def reset_correlation_manager():
    """Reset the global CorrelationManager instance (for testing)"""
    global _correlation_manager
    _correlation_manager = None


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)

    async def test_correlation_manager():
        """Test the correlation manager"""
        manager = get_correlation_manager()
        await manager.initialize()

        # Generate test data (simulated prices)
        np.random.seed(42)
        n_points = 60

        # BTC - random walk
        btc_prices = [100000]
        for _ in range(n_points - 1):
            btc_prices.append(btc_prices[-1] * (1 + np.random.normal(0, 0.02)))

        # ETH - correlated with BTC (0.8 correlation)
        eth_prices = [3500]
        for i in range(n_points - 1):
            btc_return = (btc_prices[i + 1] - btc_prices[i]) / btc_prices[i]
            eth_return = 0.8 * btc_return + 0.2 * np.random.normal(0, 0.02)
            eth_prices.append(eth_prices[-1] * (1 + eth_return))

        # SOL - less correlated (0.4)
        sol_prices = [200]
        for i in range(n_points - 1):
            btc_return = (btc_prices[i + 1] - btc_prices[i]) / btc_prices[i]
            sol_return = 0.4 * btc_return + 0.6 * np.random.normal(0, 0.03)
            sol_prices.append(sol_prices[-1] * (1 + sol_return))

        # Update correlations
        price_data = {
            "BTCUSDT": btc_prices,
            "ETHUSDT": eth_prices,
            "SOLUSDT": sol_prices
        }

        matrix = await manager.update_correlations(price_data)

        print("\n=== Correlation Matrix ===")
        print(f"Symbols: {matrix.symbols}")
        print(f"Short-term correlations: {matrix.short_term}")

        print("\n=== Position Checks ===")
        # Test position checks
        can_open, reason = await manager.can_open_position("ETHUSDT", ["BTCUSDT"])
        print(f"Can open ETHUSDT with BTCUSDT open: {can_open} ({reason})")

        can_open, reason = await manager.can_open_position("SOLUSDT", ["BTCUSDT"])
        print(f"Can open SOLUSDT with BTCUSDT open: {can_open} ({reason})")

        print("\n=== Diversification Score ===")
        score = await manager.get_diversification_score(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        print(f"Score: {score.score:.1f}/100")
        print(f"Risk Level: {score.risk_level}")
        print(f"Recommendations: {score.recommendations}")

        print("\n=== Alerts ===")
        for alert in manager.get_alerts():
            print(f"[{alert.severity.value}] {alert.message}")

        print("\n=== Status ===")
        status = manager.get_status()
        print(json.dumps(status, indent=2))

        await manager.close()

    asyncio.run(test_correlation_manager())
