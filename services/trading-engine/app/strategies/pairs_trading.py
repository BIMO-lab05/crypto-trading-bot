"""
Pairs Trading Strategy - Statistical Arbitrage

This strategy trades cointegrated asset pairs using mean reversion of the spread.

Mathematical Background:
- Spread: S = Y - β*X (where β is the hedge ratio)
- Z-score: z = (S - μ_S) / σ_S
- Entry: When |z| > entry_threshold (e.g., 2.0)
- Exit: When |z| < exit_threshold (e.g., 0.5)
- Stop Loss: When |z| > stop_threshold (e.g., 3.0)

Trading Logic:
- If z > +2.0: Short Y, Long X (spread too high, will revert down)
- If z < -2.0: Long Y, Short X (spread too low, will revert up)
- If |z| < 0.5: Close positions (spread reverted to mean)
- If |z| > 3.0: Emergency stop loss (cointegration breakdown)

Phase 2.2 - Statistical Arbitrage Implementation
Author: Trading Bot Development Team
Date: 2025-12-07
"""

import pandas as pd
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

from app.utils.statistical.cointegration import (
    test_engle_granger,
)

logger = logging.getLogger(__name__)


@dataclass
class PairsTradeSignal:
    """
    Signal for pairs trading

    Attributes:
        timestamp: Signal generation time
        symbol_x: Symbol for asset X
        symbol_y: Symbol for asset Y
        action: Trade action ('OPEN_LONG_Y', 'OPEN_SHORT_Y', 'CLOSE', 'HOLD')
        spread: Current spread value
        z_score: Current Z-score
        hedge_ratio: Current hedge ratio
        confidence: Signal confidence (0-100)
        position_size_x: Position size for asset X
        position_size_y: Position size for asset Y
        reason: Reason for signal
    """

    timestamp: datetime
    symbol_x: str
    symbol_y: str
    action: str
    spread: float
    z_score: float
    hedge_ratio: float
    confidence: float
    position_size_x: float
    position_size_y: float
    reason: str


class PairsTradingStrategy:
    """
    Pairs Trading Strategy using cointegration and Z-score

    This strategy:
    1. Verifies pair cointegration
    2. Calculates spread: S = Y - β*X
    3. Normalizes to Z-score: z = (S - μ) / σ
    4. Generates signals based on Z-score thresholds
    5. Manages paired positions with proper hedging

    Usage:
        strategy = PairsTradingStrategy(
            symbol_x='BTCUSDT',
            symbol_y='ETHUSDT',
            entry_threshold=2.0,
            exit_threshold=0.5,
            stop_threshold=3.0
        )

        signal = strategy.generate_signal(
            price_x, price_y, hist_x, hist_y, portfolio_value=allocated_capital
        )
    """

    def __init__(
        self,
        symbol_x: str,
        symbol_y: str,
        lookback_period: int = 60,
        entry_threshold: float = 2.0,
        exit_threshold: float = 0.5,
        stop_threshold: float = 3.0,
        recalibration_period: int = 24,  # Re-test cointegration every 24 hours
        max_position_size: float = 0.1,  # 10% of capital per leg
        significance_level: float = 0.05,
    ):
        """
        Initialize Pairs Trading Strategy

        Args:
            symbol_x: Symbol for asset X (e.g., 'BTCUSDT')
            symbol_y: Symbol for asset Y (e.g., 'ETHUSDT')
            lookback_period: Period for spread statistics (default: 60 periods)
            entry_threshold: Z-score threshold for entry (default: 2.0)
            exit_threshold: Z-score threshold for exit (default: 0.5)
            stop_threshold: Z-score threshold for stop loss (default: 3.0)
            recalibration_period: Hours between cointegration re-tests (default: 24)
            max_position_size: Maximum position size per leg (default: 0.1 = 10%)
            significance_level: Significance level for cointegration (default: 0.05)
        """
        self.symbol_x = symbol_x
        self.symbol_y = symbol_y
        self.lookback_period = lookback_period
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.stop_threshold = stop_threshold
        self.recalibration_period = recalibration_period
        self.max_position_size = max_position_size
        self.significance_level = significance_level

        # State tracking
        self.hedge_ratio: Optional[float] = None
        self.spread_mean: Optional[float] = None
        self.spread_std: Optional[float] = None
        self.half_life: Optional[float] = None
        self.is_cointegrated: bool = False
        self.last_calibration: Optional[datetime] = None
        self.current_position: Optional[str] = None  # 'LONG_Y', 'SHORT_Y', None

        logger.info(
            f"PairsTradingStrategy initialized: {symbol_x}/{symbol_y}, "
            f"thresholds: entry={entry_threshold}, exit={exit_threshold}, stop={stop_threshold}"
        )

    def calibrate(self, price_x: pd.Series, price_y: pd.Series) -> bool:
        """
        Calibrate strategy by testing cointegration and calculating spread parameters

        Args:
            price_x: Historical prices for asset X
            price_y: Historical prices for asset Y

        Returns:
            True if pair is cointegrated and calibration successful, False otherwise
        """
        try:
            logger.info(f"Calibrating {self.symbol_x}/{self.symbol_y}...")

            # Test cointegration
            result = test_engle_granger(
                price_x, price_y, significance_level=self.significance_level
            )

            self.is_cointegrated = result.is_cointegrated
            self.hedge_ratio = result.hedge_ratio
            self.half_life = result.half_life

            if not self.is_cointegrated:
                logger.warning(
                    f"{self.symbol_x}/{self.symbol_y} not cointegrated "
                    f"(p-value={result.p_value:.4f})"
                )
                return False

            # Calculate spread statistics
            spread = self._calculate_spread(price_x, price_y, self.hedge_ratio)
            self.spread_mean = spread.mean()
            self.spread_std = spread.std()

            self.last_calibration = datetime.now()

            logger.info(
                f"✅ Calibration successful: {self.symbol_x}/{self.symbol_y}\n"
                f"   Hedge Ratio: {self.hedge_ratio:.4f}\n"
                f"   Half-Life: {self.half_life:.2f} periods\n"
                f"   Spread: μ={self.spread_mean:.2f}, σ={self.spread_std:.2f}"
            )

            return True

        except Exception as e:
            logger.error(f"Calibration failed for {self.symbol_x}/{self.symbol_y}: {e}")
            return False

    def _calculate_spread(
        self, price_x: pd.Series, price_y: pd.Series, hedge_ratio: float
    ) -> pd.Series:
        """
        Calculate spread: S = Y - β*X

        Args:
            price_x: Prices for asset X
            price_y: Prices for asset Y
            hedge_ratio: Hedge ratio (β)

        Returns:
            Spread series
        """
        return price_y - (hedge_ratio * price_x)

    def _calculate_z_score(
        self, spread: float, spread_mean: float, spread_std: float
    ) -> float:
        """
        Calculate Z-score: z = (S - μ) / σ

        Args:
            spread: Current spread value
            spread_mean: Mean of spread
            spread_std: Standard deviation of spread

        Returns:
            Z-score
        """
        if spread_std == 0:
            return 0.0
        return (spread - spread_mean) / spread_std

    def _needs_recalibration(self) -> bool:
        """
        Check if strategy needs recalibration

        Returns:
            True if recalibration needed, False otherwise
        """
        if self.last_calibration is None:
            return True

        hours_since_calibration = (
            datetime.now() - self.last_calibration
        ).total_seconds() / 3600

        return hours_since_calibration >= self.recalibration_period

    def generate_signal(
        self,
        current_price_x: float,
        current_price_y: float,
        historical_data_x: pd.Series,
        historical_data_y: pd.Series,
        portfolio_value: float,
    ) -> Optional[PairsTradeSignal]:
        """
        Generate trading signal based on current prices and historical data

        Args:
            current_price_x: Current price of asset X
            current_price_y: Current price of asset Y
            historical_data_x: Historical prices for asset X (for calibration)
            historical_data_y: Historical prices for asset Y (for calibration)
            portfolio_value: Total portfolio value for position sizing.
                REQUIRED — the old 10000.0 default was 100x the real account;
                every live caller (StatisticalArbitrageManager) passes the
                allocated capital explicitly (AUDIT 2.5).

        Returns:
            PairsTradeSignal if signal generated, None otherwise
        """
        try:
            # Recalibrate if needed
            if self._needs_recalibration():
                calibrated = self.calibrate(historical_data_x, historical_data_y)
                if not calibrated:
                    return None

            # Ensure we have calibration parameters
            if not self.is_cointegrated or self.hedge_ratio is None:
                logger.warning(
                    f"Strategy not calibrated for {self.symbol_x}/{self.symbol_y}"
                )
                return None

            # Calculate current spread
            current_spread = current_price_y - (self.hedge_ratio * current_price_x)

            # Calculate Z-score
            z_score = self._calculate_z_score(
                current_spread, self.spread_mean, self.spread_std
            )

            # Determine action based on Z-score
            action, reason, confidence = self._determine_action(z_score)

            # Calculate position sizes
            position_size_x, position_size_y = self._calculate_position_sizes(
                current_price_x, current_price_y, portfolio_value, abs(z_score)
            )

            # Create signal
            signal = PairsTradeSignal(
                timestamp=datetime.now(),
                symbol_x=self.symbol_x,
                symbol_y=self.symbol_y,
                action=action,
                spread=current_spread,
                z_score=z_score,
                hedge_ratio=self.hedge_ratio,
                confidence=confidence,
                position_size_x=position_size_x,
                position_size_y=position_size_y,
                reason=reason,
            )

            # Update current position state
            if action == "OPEN_LONG_Y":
                self.current_position = "LONG_Y"
            elif action == "OPEN_SHORT_Y":
                self.current_position = "SHORT_Y"
            elif action == "CLOSE":
                self.current_position = None

            logger.debug(
                f"Signal: {self.symbol_x}/{self.symbol_y} - "
                f"Action: {action}, Z-score: {z_score:.2f}, "
                f"Spread: {current_spread:.2f}"
            )

            return signal

        except Exception as e:
            logger.error(
                f"Failed to generate signal for {self.symbol_x}/{self.symbol_y}: {e}"
            )
            return None

    def _determine_action(self, z_score: float) -> Tuple[str, str, float]:
        """
        Determine trading action based on Z-score

        Logic:
        - If z > +entry_threshold: Short Y, Long X (spread too high)
        - If z < -entry_threshold: Long Y, Short X (spread too low)
        - If |z| < exit_threshold: Close positions (spread reverted)
        - If |z| > stop_threshold: Emergency close (stop loss)

        Args:
            z_score: Current Z-score

        Returns:
            Tuple of (action, reason, confidence)
        """
        # Emergency stop loss
        if abs(z_score) > self.stop_threshold:
            if self.current_position is not None:
                return (
                    "CLOSE",
                    f"Stop loss triggered (|z|={abs(z_score):.2f} > {self.stop_threshold})",
                    100.0,
                )

        # Exit signal (mean reversion complete)
        if abs(z_score) < self.exit_threshold:
            if self.current_position is not None:
                return (
                    "CLOSE",
                    f"Mean reversion complete (|z|={abs(z_score):.2f} < {self.exit_threshold})",
                    90.0,
                )
            else:
                return ("HOLD", "No position, spread near mean", 0.0)

        # Entry signals
        if z_score > self.entry_threshold:
            if self.current_position == "SHORT_Y":
                return ("HOLD", "Already in SHORT_Y position", 0.0)
            elif self.current_position == "LONG_Y":
                return (
                    "CLOSE",
                    f"Reverse signal detected (z={z_score:.2f}), close LONG_Y first",
                    80.0,
                )
            else:
                confidence = min(100.0, (abs(z_score) - self.entry_threshold) * 30 + 70)
                return (
                    "OPEN_SHORT_Y",
                    f"Spread too high (z={z_score:.2f} > {self.entry_threshold}), SHORT Y / LONG X",
                    confidence,
                )

        if z_score < -self.entry_threshold:
            if self.current_position == "LONG_Y":
                return ("HOLD", "Already in LONG_Y position", 0.0)
            elif self.current_position == "SHORT_Y":
                return (
                    "CLOSE",
                    f"Reverse signal detected (z={z_score:.2f}), close SHORT_Y first",
                    80.0,
                )
            else:
                confidence = min(100.0, (abs(z_score) - self.entry_threshold) * 30 + 70)
                return (
                    "OPEN_LONG_Y",
                    f"Spread too low (z={z_score:.2f} < -{self.entry_threshold}), LONG Y / SHORT X",
                    confidence,
                )

        # No signal
        return ("HOLD", f"Z-score in neutral zone (z={z_score:.2f})", 0.0)

    def _calculate_position_sizes(
        self, price_x: float, price_y: float, portfolio_value: float, z_score_abs: float
    ) -> Tuple[float, float]:
        """
        Calculate position sizes for both legs of the pair

        Position sizing logic:
        - Base size: max_position_size * portfolio_value
        - Scale by Z-score strength: Higher |z| = larger position
        - Maintain hedge ratio: position_y = hedge_ratio * position_x

        Args:
            price_x: Current price of asset X
            price_y: Current price of asset Y
            portfolio_value: Total portfolio value
            z_score_abs: Absolute Z-score

        Returns:
            Tuple of (position_size_x, position_size_y) in units
        """
        # Base capital allocation per leg
        base_capital = self.max_position_size * portfolio_value

        # Scale by Z-score strength (higher |z| = larger position)
        # Range: 0.5x to 1.0x based on Z-score
        if z_score_abs >= self.entry_threshold:
            scale_factor = min(1.0, 0.5 + (z_score_abs - self.entry_threshold) * 0.2)
        else:
            scale_factor = 0.5

        capital_per_leg = base_capital * scale_factor

        # Calculate position sizes in units
        # For Y leg
        position_size_y = capital_per_leg / price_y

        # For X leg (maintain hedge ratio)
        position_size_x = position_size_y * self.hedge_ratio

        logger.debug(
            f"Position sizes: X={position_size_x:.4f} units, "
            f"Y={position_size_y:.4f} units (hedge_ratio={self.hedge_ratio:.4f})"
        )

        return position_size_x, position_size_y

    def get_status(self) -> Dict:
        """
        Get current strategy status

        Returns:
            Dictionary with strategy state
        """
        return {
            "symbol_x": self.symbol_x,
            "symbol_y": self.symbol_y,
            "is_cointegrated": self.is_cointegrated,
            "hedge_ratio": self.hedge_ratio,
            "spread_mean": self.spread_mean,
            "spread_std": self.spread_std,
            "half_life": self.half_life,
            "current_position": self.current_position,
            "last_calibration": self.last_calibration.isoformat()
            if self.last_calibration
            else None,
            "needs_recalibration": self._needs_recalibration(),
            "parameters": {
                "lookback_period": self.lookback_period,
                "entry_threshold": self.entry_threshold,
                "exit_threshold": self.exit_threshold,
                "stop_threshold": self.stop_threshold,
                "max_position_size": self.max_position_size,
            },
        }
