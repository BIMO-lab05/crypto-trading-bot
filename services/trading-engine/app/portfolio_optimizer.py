"""
Portfolio Optimizer - Multi-Symbol Portfolio Management
Purpose: Manage 5-10 symbols simultaneously with portfolio-level risk controls
Features:
- Symbol correlation analysis
- Diversification scoring
- Capital allocation optimization
- Portfolio-level risk management
- Rebalancing strategies
"""

import logging
import asyncio
from typing import Dict, List, Tuple, Optional
from decimal import Decimal
from datetime import datetime, timedelta
import numpy as np
from dataclasses import dataclass

from app.config import get_settings
from app.models import Position, PositionStatus

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class SymbolAllocation:
    """Capital allocation for a symbol"""
    symbol: str
    target_weight: float  # Target % of portfolio (0.0 to 1.0)
    current_weight: float  # Current % of portfolio
    max_position_value: Decimal  # Maximum position value in USD
    priority: int  # Trading priority (1=highest)
    correlation_group: str  # For diversification tracking


@dataclass
class PortfolioMetrics:
    """Portfolio-level metrics"""
    total_value: Decimal
    total_exposure: Decimal
    exposure_pct: float
    cash_balance: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    num_positions: int
    diversification_score: float  # 0.0 to 1.0 (1.0 = perfectly diversified)
    correlation_risk: float  # 0.0 to 1.0 (1.0 = high correlation risk)


class PortfolioOptimizer:
    """
    Multi-symbol portfolio optimizer with correlation analysis

    Manages:
    1. Symbol selection and weighting
    2. Correlation-based diversification
    3. Capital allocation
    4. Rebalancing signals
    5. Portfolio-level risk limits
    """

    def __init__(self):
        """Initialize portfolio optimizer"""
        self.allocations: Dict[str, SymbolAllocation] = {}
        self.correlation_matrix: Dict[str, Dict[str, float]] = {}
        self.price_history: Dict[str, List[float]] = {}
        self.max_history_length = 100  # Keep 100 data points for correlation

        logger.info("PortfolioOptimizer initialized")

    def setup_default_portfolio(self) -> Dict[str, SymbolAllocation]:
        """
        Setup default multi-symbol portfolio

        Returns:
            Dictionary of symbol allocations
        """
        # Define default portfolio: Only symbols with available market data
        # Updated 2025-11-30: Limited to symbols with data in TimescaleDB
        default_symbols = [
            # Large Cap (40% allocation)
            ("BTCUSDT", 0.20, 1, "large_cap"),  # Bitcoin
            ("ETHUSDT", 0.20, 1, "large_cap"),  # Ethereum

            # Mid Cap (35% allocation)
            ("BNBUSDT", 0.12, 2, "mid_cap"),    # Binance Coin
            ("SOLUSDT", 0.12, 2, "mid_cap"),    # Solana
            ("XRPUSDT", 0.11, 2, "mid_cap"),    # XRP

            # Small Cap (25% allocation)
            ("ADAUSDT", 0.13, 3, "small_cap"),  # Cardano
            ("DOGEUSDT", 0.12, 3, "small_cap"), # Dogecoin
        ]

        # Get initial balance for calculations
        initial_balance = Decimal(str(settings.paper_initial_balance))

        for symbol, weight, priority, group in default_symbols:
            max_value = initial_balance * Decimal(str(weight))

            self.allocations[symbol] = SymbolAllocation(
                symbol=symbol,
                target_weight=weight,
                current_weight=0.0,
                max_position_value=max_value,
                priority=priority,
                correlation_group=group
            )

        logger.info(f"✓ Default portfolio setup: {len(self.allocations)} symbols")
        logger.info(f"  Large Cap: 40% | Mid Cap: 30% | Small Cap: 30%")

        return self.allocations

    def update_price_history(self, symbol: str, price: float):
        """
        Update price history for correlation calculation

        Args:
            symbol: Trading symbol
            price: Current price
        """
        if symbol not in self.price_history:
            self.price_history[symbol] = []

        self.price_history[symbol].append(price)

        # Keep only recent history
        if len(self.price_history[symbol]) > self.max_history_length:
            self.price_history[symbol] = self.price_history[symbol][-self.max_history_length:]

    def calculate_correlation_matrix(self) -> Dict[str, Dict[str, float]]:
        """
        Calculate correlation matrix between all symbols

        Returns:
            Correlation matrix (symbol1 -> symbol2 -> correlation)
        """
        symbols = list(self.price_history.keys())

        # Need at least 30 data points for meaningful correlation
        valid_symbols = [s for s in symbols if len(self.price_history[s]) >= 30]

        if len(valid_symbols) < 2:
            logger.warning("Insufficient price history for correlation calculation")
            return {}

        correlation_matrix = {}

        for symbol1 in valid_symbols:
            correlation_matrix[symbol1] = {}

            for symbol2 in valid_symbols:
                if symbol1 == symbol2:
                    correlation_matrix[symbol1][symbol2] = 1.0
                else:
                    # Calculate returns
                    prices1 = np.array(self.price_history[symbol1])
                    prices2 = np.array(self.price_history[symbol2])

                    # Align lengths
                    min_len = min(len(prices1), len(prices2))
                    prices1 = prices1[-min_len:]
                    prices2 = prices2[-min_len:]

                    # Calculate returns
                    returns1 = np.diff(prices1) / prices1[:-1]
                    returns2 = np.diff(prices2) / prices2[:-1]

                    # Calculate correlation
                    if len(returns1) > 0 and len(returns2) > 0:
                        correlation = np.corrcoef(returns1, returns2)[0, 1]
                        correlation_matrix[symbol1][symbol2] = float(correlation)
                    else:
                        correlation_matrix[symbol1][symbol2] = 0.0

        self.correlation_matrix = correlation_matrix
        logger.info(f"✓ Correlation matrix calculated for {len(valid_symbols)} symbols")

        return correlation_matrix

    def get_correlation(self, symbol1: str, symbol2: str) -> float:
        """
        Get correlation between two symbols

        Args:
            symbol1: First symbol
            symbol2: Second symbol

        Returns:
            Correlation coefficient (-1.0 to 1.0)
        """
        if symbol1 not in self.correlation_matrix:
            return 0.0
        return self.correlation_matrix.get(symbol1, {}).get(symbol2, 0.0)

    def calculate_diversification_score(
        self,
        positions: List[Position]
    ) -> float:
        """
        Calculate portfolio diversification score

        Args:
            positions: Current open positions

        Returns:
            Diversification score (0.0 to 1.0, higher = better diversified)
        """
        if not positions:
            return 1.0  # No positions = perfectly diversified

        # Count positions per correlation group
        group_exposure = {}
        total_value = Decimal("0")

        for pos in positions:
            if pos.status != PositionStatus.OPEN:
                continue

            symbol = pos.symbol
            position_value = pos.entry_price * pos.quantity
            total_value += position_value

            # Get correlation group
            if symbol in self.allocations:
                group = self.allocations[symbol].correlation_group
                group_exposure[group] = group_exposure.get(group, Decimal("0")) + position_value

        if total_value == 0:
            return 1.0

        # Calculate concentration (inverse of diversification)
        # Herfindahl-Hirschman Index (HHI)
        concentration = sum(
            (float(exposure) / float(total_value)) ** 2
            for exposure in group_exposure.values()
        )

        # Convert to diversification score (0 = concentrated, 1 = diversified)
        # Perfect diversification: 3 groups equally weighted = HHI of 0.33
        max_concentration = 1.0  # All in one group
        min_concentration = 1.0 / len(self.allocations) if self.allocations else 1.0

        if max_concentration == min_concentration:
            return 1.0

        diversification = 1.0 - (
            (concentration - min_concentration) /
            (max_concentration - min_concentration)
        )

        return max(0.0, min(1.0, diversification))

    def calculate_correlation_risk(
        self,
        positions: List[Position]
    ) -> float:
        """
        Calculate correlation risk of portfolio

        Args:
            positions: Current open positions

        Returns:
            Correlation risk (0.0 to 1.0, higher = more correlated)
        """
        if not positions or len(positions) < 2:
            return 0.0

        open_positions = [p for p in positions if p.status == PositionStatus.OPEN]
        if len(open_positions) < 2:
            return 0.0

        # Calculate average correlation between all pairs
        symbols = [p.symbol for p in open_positions]
        correlations = []

        for i, symbol1 in enumerate(symbols):
            for symbol2 in symbols[i+1:]:
                corr = abs(self.get_correlation(symbol1, symbol2))
                correlations.append(corr)

        if not correlations:
            return 0.0

        # Average absolute correlation
        avg_correlation = sum(correlations) / len(correlations)

        return avg_correlation

    def get_portfolio_metrics(
        self,
        balance: Decimal,
        positions: List[Position]
    ) -> PortfolioMetrics:
        """
        Calculate comprehensive portfolio metrics

        Args:
            balance: Current cash balance
            positions: All positions

        Returns:
            Portfolio metrics
        """
        total_exposure = Decimal("0")
        unrealized_pnl = Decimal("0")
        realized_pnl = Decimal("0")
        num_open = 0

        for pos in positions:
            if pos.status == PositionStatus.OPEN:
                total_exposure += pos.entry_price * pos.quantity
                unrealized_pnl += pos.unrealized_pnl or Decimal("0")
                num_open += 1
            elif pos.status == PositionStatus.CLOSED:
                realized_pnl += pos.realized_pnl or Decimal("0")

        total_value = balance + unrealized_pnl + realized_pnl
        exposure_pct = float(total_exposure / total_value * 100) if total_value > 0 else 0.0

        # Calculate diversification and correlation
        diversification = self.calculate_diversification_score(positions)
        correlation_risk = self.calculate_correlation_risk(positions)

        return PortfolioMetrics(
            total_value=total_value,
            total_exposure=total_exposure,
            exposure_pct=exposure_pct,
            cash_balance=balance,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
            num_positions=num_open,
            diversification_score=diversification,
            correlation_risk=correlation_risk
        )

    def should_trade_symbol(
        self,
        symbol: str,
        current_positions: List[Position],
        portfolio_balance: Decimal
    ) -> Tuple[bool, str]:
        """
        Determine if we should trade a symbol based on portfolio rules

        Args:
            symbol: Symbol to evaluate
            current_positions: Current positions
            portfolio_balance: Current balance

        Returns:
            Tuple of (should_trade, reason)
        """
        # Check if symbol is in portfolio
        if symbol not in self.allocations:
            return False, f"Symbol {symbol} not in portfolio allocation"

        allocation = self.allocations[symbol]

        # Get portfolio metrics
        metrics = self.get_portfolio_metrics(portfolio_balance, current_positions)

        # Check portfolio-level exposure limit
        max_exposure_pct = settings.max_total_exposure_pct
        if metrics.exposure_pct >= max_exposure_pct:
            return False, f"Portfolio exposure {metrics.exposure_pct:.1f}% >= max {max_exposure_pct}%"

        # Check if we already have position in this symbol
        has_position = any(
            p.symbol == symbol and p.status == PositionStatus.OPEN
            for p in current_positions
        )

        if has_position:
            return False, f"Already have open position in {symbol}"

        # Check correlation risk
        if metrics.correlation_risk > 0.8:
            # High correlation risk - only trade if diversification improves
            group = allocation.correlation_group
            group_has_position = any(
                p.symbol in self.allocations and
                self.allocations[p.symbol].correlation_group == group and
                p.status == PositionStatus.OPEN
                for p in current_positions
            )

            if group_has_position:
                return False, f"High correlation risk {metrics.correlation_risk:.2f}, group already exposed"

        # Check if we have capacity for this symbol's allocation
        current_symbol_exposure = sum(
            pos.entry_price * pos.quantity
            for pos in current_positions
            if pos.symbol == symbol and pos.status == PositionStatus.OPEN
        )

        if current_symbol_exposure >= allocation.max_position_value:
            return False, f"Symbol allocation limit reached"

        return True, "OK to trade"

    def get_trading_priority_list(
        self,
        current_positions: List[Position]
    ) -> List[str]:
        """
        Get list of symbols ordered by trading priority

        Args:
            current_positions: Current positions

        Returns:
            List of symbols in priority order
        """
        # Get symbols we don't have positions in
        open_symbols = {
            p.symbol for p in current_positions
            if p.status == PositionStatus.OPEN
        }

        available_symbols = [
            (symbol, alloc.priority)
            for symbol, alloc in self.allocations.items()
            if symbol not in open_symbols
        ]

        # Sort by priority (lower number = higher priority)
        available_symbols.sort(key=lambda x: x[1])

        return [symbol for symbol, _ in available_symbols]

    def calculate_position_size(
        self,
        symbol: str,
        current_price: Decimal,
        portfolio_balance: Decimal
    ) -> Decimal:
        """
        Calculate optimal position size for a symbol

        Args:
            symbol: Trading symbol
            current_price: Current price
            portfolio_balance: Available balance

        Returns:
            Position quantity
        """
        if symbol not in self.allocations:
            # Fallback to settings default
            max_value = portfolio_balance * (Decimal(str(settings.max_position_size_pct)) / 100)
            return max_value / current_price

        allocation = self.allocations[symbol]

        # Calculate position value based on target weight
        target_value = portfolio_balance * Decimal(str(allocation.target_weight))

        # Don't exceed max position value
        position_value = min(target_value, allocation.max_position_value)

        # Also respect per-trade risk limit
        max_per_trade = portfolio_balance * (Decimal(str(settings.max_position_size_pct)) / 100)
        position_value = min(position_value, max_per_trade)

        # Calculate quantity
        quantity = position_value / current_price

        return quantity

    def log_portfolio_status(self, metrics: PortfolioMetrics):
        """
        Log current portfolio status

        Args:
            metrics: Portfolio metrics
        """
        logger.info("=" * 60)
        logger.info("📊 PORTFOLIO STATUS")
        logger.info("=" * 60)
        logger.info(f"Total Value:      ${metrics.total_value:,.2f}")
        logger.info(f"Cash Balance:     ${metrics.cash_balance:,.2f}")
        logger.info(f"Total Exposure:   ${metrics.total_exposure:,.2f} ({metrics.exposure_pct:.1f}%)")
        logger.info(f"Unrealized P&L:   ${metrics.unrealized_pnl:,.2f}")
        logger.info(f"Realized P&L:     ${metrics.realized_pnl:,.2f}")
        logger.info(f"Open Positions:   {metrics.num_positions}")
        logger.info(f"Diversification:  {metrics.diversification_score:.2%} (1.0 = perfect)")
        logger.info(f"Correlation Risk: {metrics.correlation_risk:.2%} (0.0 = no risk)")
        logger.info("=" * 60)


# Global instance
_portfolio_optimizer: Optional[PortfolioOptimizer] = None


def get_portfolio_optimizer() -> PortfolioOptimizer:
    """Get or create portfolio optimizer instance"""
    global _portfolio_optimizer
    if _portfolio_optimizer is None:
        _portfolio_optimizer = PortfolioOptimizer()
        _portfolio_optimizer.setup_default_portfolio()
    return _portfolio_optimizer


def reset_portfolio_optimizer():
    """Reset portfolio optimizer (for testing)"""
    global _portfolio_optimizer
    _portfolio_optimizer = None
