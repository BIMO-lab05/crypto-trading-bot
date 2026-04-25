"""
Funding Rate Arbitrage Strategy

This strategy exploits funding rate differences between perpetual futures and spot markets.

Strategy Overview:
- Perpetual futures pay/receive funding every 8 hours
- When funding rate is positive (long pays short): Go LONG spot + SHORT futures
- When funding rate is negative (short pays long): Go SHORT spot + LONG futures
- Collect funding payments while maintaining market-neutral hedge

Mathematical Background:
- Funding Rate: Periodic payment between long and short positions
- Funding Payment = Position Size × Funding Rate
- Annual Yield ≈ Funding Rate × 3 (payments per day) × 365

Example:
- Funding Rate: +0.01% per 8h = 0.03% daily = 10.95% annually
- Position: $10,000 LONG spot + $10,000 SHORT perpetual
- Daily Income: $10,000 × 0.03% = $3/day
- Annual Income: ~$1,095 (10.95% yield)

Risks:
- Basis Risk: Spot and futures prices diverge
- Funding Rate Reversal: Funding flips negative
- Liquidation Risk: Futures position liquidated due to price movement

Phase 2.2 - Statistical Arbitrage Implementation
Author: Trading Bot Development Team
Date: 2025-12-07
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class FundingRateSignal:
    """
    Signal for funding rate arbitrage

    Attributes:
        timestamp: Signal generation time
        symbol: Trading symbol (e.g., 'BTCUSDT')
        action: Trade action ('OPEN_HEDGE', 'CLOSE_HEDGE', 'HOLD')
        funding_rate: Current funding rate (per 8h)
        annualized_yield: Expected annual yield
        basis: Current basis (futures - spot)
        basis_pct: Basis as percentage
        spot_position_size: Spot position size
        futures_position_size: Futures position size
        confidence: Signal confidence (0-100)
        reason: Reason for signal
    """
    timestamp: datetime
    symbol: str
    action: str
    funding_rate: float
    annualized_yield: float
    basis: float
    basis_pct: float
    spot_position_size: float
    futures_position_size: float
    confidence: float
    reason: str


class FundingRateArbitrageStrategy:
    """
    Funding Rate Arbitrage Strategy

    This strategy:
    1. Monitors funding rates from Bybit API
    2. Opens hedged positions when funding rate is attractive
    3. Collects funding payments while maintaining hedge
    4. Closes positions when funding becomes unfavorable
    5. Manages basis risk between spot and futures

    Usage:
        strategy = FundingRateArbitrageStrategy(
            symbol='BTCUSDT',
            min_funding_rate=0.0003,  # 0.03% per 8h = 10.95% annually
            max_basis_pct=2.0,        # Max 2% basis divergence
        )

        signal = strategy.generate_signal(
            current_funding_rate,
            spot_price,
            futures_price,
            portfolio_value
        )
    """

    def __init__(
        self,
        symbol: str,
        min_funding_rate: float = 0.0003,  # 0.03% per 8h = ~11% annually
        max_funding_rate: float = 0.01,    # 1% per 8h = ~365% annually (too risky)
        max_basis_pct: float = 2.0,         # Max 2% basis divergence
        position_size_pct: float = 0.2,     # 20% of portfolio per side
        funding_collection_threshold: float = 0.0001,  # Min 0.01% to stay in position
    ):
        """
        Initialize Funding Rate Arbitrage Strategy

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            min_funding_rate: Minimum funding rate to open position (default: 0.0003 = 0.03%)
            max_funding_rate: Maximum funding rate (safety limit, default: 0.01 = 1%)
            max_basis_pct: Maximum basis percentage before closing (default: 2%)
            position_size_pct: Position size as % of portfolio per side (default: 0.2 = 20%)
            funding_collection_threshold: Min funding rate to maintain position (default: 0.0001)
        """
        self.symbol = symbol
        self.min_funding_rate = min_funding_rate
        self.max_funding_rate = max_funding_rate
        self.max_basis_pct = max_basis_pct
        self.position_size_pct = position_size_pct
        self.funding_collection_threshold = funding_collection_threshold

        # State tracking
        self.current_position: Optional[str] = None  # 'HEDGED', None
        self.entry_funding_rate: Optional[float] = None
        self.entry_basis: Optional[float] = None
        self.total_funding_collected: float = 0.0
        self.funding_history: List[Dict] = []

        logger.info(
            f"FundingRateArbitrageStrategy initialized: {symbol}\n"
            f"  Min funding rate: {min_funding_rate:.4f} ({self._annualize_funding(min_funding_rate):.2f}% annually)\n"
            f"  Max basis: {max_basis_pct}%\n"
            f"  Position size: {position_size_pct*100}% per side"
        )

    def _annualize_funding(self, funding_rate: float) -> float:
        """
        Convert 8-hour funding rate to annualized yield

        Args:
            funding_rate: Funding rate per 8 hours

        Returns:
            Annualized yield percentage
        """
        # 3 funding periods per day × 365 days
        return funding_rate * 3 * 365 * 100

    def _calculate_basis(
        self,
        spot_price: float,
        futures_price: float
    ) -> Tuple[float, float]:
        """
        Calculate basis and basis percentage

        Basis = Futures Price - Spot Price
        Basis % = (Basis / Spot Price) × 100

        Args:
            spot_price: Current spot price
            futures_price: Current futures price

        Returns:
            Tuple of (basis, basis_pct)
        """
        basis = futures_price - spot_price
        basis_pct = (basis / spot_price) * 100 if spot_price > 0 else 0
        return basis, basis_pct

    def _calculate_position_sizes(
        self,
        spot_price: float,
        futures_price: float,
        portfolio_value: float
    ) -> Tuple[float, float]:
        """
        Calculate position sizes for spot and futures

        Position sizing:
        - Spot: position_size_pct × portfolio_value / spot_price
        - Futures: Same USD value as spot

        Args:
            spot_price: Current spot price
            futures_price: Current futures price
            portfolio_value: Total portfolio value

        Returns:
            Tuple of (spot_position_size, futures_position_size) in units
        """
        # Capital allocation per side
        capital_per_side = self.position_size_pct * portfolio_value

        # Spot position in units
        spot_position_size = capital_per_side / spot_price

        # Futures position (same USD value, different price)
        futures_position_size = capital_per_side / futures_price

        logger.debug(
            f"Position sizes: Spot={spot_position_size:.6f} units, "
            f"Futures={futures_position_size:.6f} units"
        )

        return spot_position_size, futures_position_size

    def record_funding_payment(
        self,
        funding_rate: float,
        position_size: float,
        futures_price: float
    ):
        """
        Record funding payment received/paid

        Args:
            funding_rate: Funding rate for this period
            position_size: Futures position size (units)
            futures_price: Current futures price
        """
        # Funding payment = Position Value × Funding Rate
        position_value = position_size * futures_price
        funding_payment = position_value * funding_rate

        self.total_funding_collected += funding_payment

        self.funding_history.append({
            'timestamp': datetime.now(),
            'funding_rate': funding_rate,
            'position_size': position_size,
            'futures_price': futures_price,
            'funding_payment': funding_payment,
            'total_collected': self.total_funding_collected
        })

        logger.info(
            f"Funding payment: ${funding_payment:.2f} "
            f"(rate={funding_rate:.4f}, total=${self.total_funding_collected:.2f})"
        )

    def generate_signal(
        self,
        current_funding_rate: float,
        spot_price: float,
        futures_price: float,
        portfolio_value: float = 10000.0,
        next_funding_time: Optional[datetime] = None
    ) -> Optional[FundingRateSignal]:
        """
        Generate trading signal based on funding rate and basis

        Args:
            current_funding_rate: Current funding rate (per 8h)
            spot_price: Current spot price
            futures_price: Current futures price
            portfolio_value: Total portfolio value
            next_funding_time: Next funding payment time

        Returns:
            FundingRateSignal if signal generated, None otherwise
        """
        try:
            # Calculate basis
            basis, basis_pct = self._calculate_basis(spot_price, futures_price)

            # Calculate annualized yield
            annualized_yield = self._annualize_funding(current_funding_rate)

            # Determine action
            action, reason, confidence = self._determine_action(
                current_funding_rate,
                basis_pct,
                annualized_yield
            )

            # Calculate position sizes
            spot_size, futures_size = self._calculate_position_sizes(
                spot_price,
                futures_price,
                portfolio_value
            )

            # Create signal
            signal = FundingRateSignal(
                timestamp=datetime.now(),
                symbol=self.symbol,
                action=action,
                funding_rate=current_funding_rate,
                annualized_yield=annualized_yield,
                basis=basis,
                basis_pct=basis_pct,
                spot_position_size=spot_size,
                futures_position_size=futures_size,
                confidence=confidence,
                reason=reason
            )

            # Update state
            if action == 'OPEN_HEDGE':
                self.current_position = 'HEDGED'
                self.entry_funding_rate = current_funding_rate
                self.entry_basis = basis
            elif action == 'CLOSE_HEDGE':
                self.current_position = None
                self.entry_funding_rate = None
                self.entry_basis = None

            logger.debug(
                f"Signal: {self.symbol} - Action: {action}, "
                f"Funding: {current_funding_rate:.4f} ({annualized_yield:.2f}% APY), "
                f"Basis: {basis_pct:.2f}%"
            )

            return signal

        except Exception as e:
            logger.error(f"Failed to generate signal for {self.symbol}: {e}")
            return None

    def _determine_action(
        self,
        funding_rate: float,
        basis_pct: float,
        annualized_yield: float
    ) -> Tuple[str, str, float]:
        """
        Determine trading action based on funding rate and basis

        Decision Logic:
        1. Entry: funding_rate > min_funding_rate AND |basis_pct| < max_basis_pct
        2. Exit: funding_rate < funding_collection_threshold OR |basis_pct| > max_basis_pct
        3. Hold: Otherwise

        Args:
            funding_rate: Current funding rate
            basis_pct: Current basis percentage
            annualized_yield: Annualized yield

        Returns:
            Tuple of (action, reason, confidence)
        """
        # Safety check: funding rate too high (abnormal market)
        if abs(funding_rate) > self.max_funding_rate:
            if self.current_position == 'HEDGED':
                return (
                    'CLOSE_HEDGE',
                    f'Abnormal funding rate (|rate|={abs(funding_rate):.4f} > {self.max_funding_rate})',
                    100.0
                )
            else:
                return (
                    'HOLD',
                    f'Funding rate too high (abnormal market)',
                    0.0
                )

        # Exit condition 1: Basis risk too high
        if abs(basis_pct) > self.max_basis_pct:
            if self.current_position == 'HEDGED':
                return (
                    'CLOSE_HEDGE',
                    f'Basis risk exceeded (|basis|={abs(basis_pct):.2f}% > {self.max_basis_pct}%)',
                    95.0
                )

        # Exit condition 2: Funding rate became unfavorable
        if self.current_position == 'HEDGED':
            if funding_rate < self.funding_collection_threshold:
                return (
                    'CLOSE_HEDGE',
                    f'Funding rate too low (rate={funding_rate:.4f} < {self.funding_collection_threshold})',
                    90.0
                )

            # Funding rate reversed sign
            if self.entry_funding_rate is not None:
                if (self.entry_funding_rate > 0 and funding_rate < 0) or \
                   (self.entry_funding_rate < 0 and funding_rate > 0):
                    return (
                        'CLOSE_HEDGE',
                        f'Funding rate reversed (entry={self.entry_funding_rate:.4f}, current={funding_rate:.4f})',
                        95.0
                    )

        # Entry condition: Good funding rate with acceptable basis
        if self.current_position is None:
            if funding_rate >= self.min_funding_rate and abs(basis_pct) < self.max_basis_pct:
                confidence = min(100.0, (funding_rate / self.min_funding_rate) * 70 + 30)
                return (
                    'OPEN_HEDGE',
                    f'Attractive funding rate (rate={funding_rate:.4f}, APY={annualized_yield:.2f}%, basis={basis_pct:.2f}%)',
                    confidence
                )

            if funding_rate <= -self.min_funding_rate and abs(basis_pct) < self.max_basis_pct:
                confidence = min(100.0, (abs(funding_rate) / self.min_funding_rate) * 70 + 30)
                return (
                    'OPEN_HEDGE',
                    f'Attractive negative funding (rate={funding_rate:.4f}, APY={annualized_yield:.2f}%, basis={basis_pct:.2f}%)',
                    confidence
                )

        # Hold condition
        if self.current_position == 'HEDGED':
            return (
                'HOLD',
                f'Maintaining hedge (funding={funding_rate:.4f}, APY={annualized_yield:.2f}%, basis={basis_pct:.2f}%)',
                0.0
            )
        else:
            return (
                'HOLD',
                f'Funding rate insufficient (rate={funding_rate:.4f}, min={self.min_funding_rate})',
                0.0
            )

    def get_status(self) -> Dict:
        """
        Get current strategy status

        Returns:
            Dictionary with strategy state
        """
        return {
            'symbol': self.symbol,
            'current_position': self.current_position,
            'entry_funding_rate': self.entry_funding_rate,
            'entry_basis': self.entry_basis,
            'total_funding_collected': self.total_funding_collected,
            'num_funding_payments': len(self.funding_history),
            'parameters': {
                'min_funding_rate': self.min_funding_rate,
                'max_funding_rate': self.max_funding_rate,
                'max_basis_pct': self.max_basis_pct,
                'position_size_pct': self.position_size_pct,
                'funding_collection_threshold': self.funding_collection_threshold,
            },
            'annualized_targets': {
                'min_apy': self._annualize_funding(self.min_funding_rate),
                'threshold_apy': self._annualize_funding(self.funding_collection_threshold),
            }
        }

    def get_funding_history(self, limit: int = 10) -> List[Dict]:
        """
        Get recent funding payment history

        Args:
            limit: Maximum number of records to return

        Returns:
            List of recent funding payments
        """
        return self.funding_history[-limit:]

    def calculate_current_yield(
        self,
        funding_rate: float,
        days_held: int = 1
    ) -> Dict:
        """
        Calculate current yield metrics

        Args:
            funding_rate: Current funding rate
            days_held: Number of days position held

        Returns:
            Dictionary with yield calculations
        """
        daily_rate = funding_rate * 3  # 3 periods per day
        annualized_rate = daily_rate * 365

        return {
            'funding_rate_8h': funding_rate,
            'daily_rate': daily_rate,
            'annualized_rate': annualized_rate,
            'daily_rate_pct': daily_rate * 100,
            'annualized_rate_pct': annualized_rate * 100,
            'projected_30d_return': daily_rate * 30 * 100,
        }
