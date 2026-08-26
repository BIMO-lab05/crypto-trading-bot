"""
Risk of Ruin Calculator
Created: 2025-12-06
Purpose: Calculate probability of catastrophic account loss

Risk of Ruin (RoR) answers:
- What's the probability I'll lose my entire account?
- How much capital do I need to avoid ruin?
- What's my safe position sizing?
- How does win rate affect survival probability?

Formula (simplified):
RoR = ((1-W) / W) ^ (Capital / AvgLoss)

Where:
- W = Win rate
- Capital = Available trading capital
- AvgLoss = Average losing trade size
"""

import logging
import os
import sys
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import numpy as np
import pandas as pd  # noqa: F401
from scipy.optimize import minimize_scalar  # noqa: F401
import json

# ---------------------------------------------------------------------------
# Repo root on sys.path so `shared.account` resolves however this module is
# invoked. Mirrors the existing bootstrap in `backtesting/run_walk_forward.py`
# and `backtesting/_probe_phase1_gates.py` — not a new pattern.
#
# This file is HOST-RUN ONLY: repo-root `backtesting/` appears in no compose
# service and no Dockerfile copies it, so unlike code under `services/*/app/**`
# it MAY import the declaration of record directly instead of going through a
# service's Settings. See the table in `shared/account.py`.
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.account import PAPER_INITIAL_BALANCE  # noqa: E402


logger = logging.getLogger(__name__)


@dataclass
class RiskOfRuinConfig:
    """Configuration for risk of ruin calculations"""

    # Capital settings.
    # FIX 2026-08-03 (capital audit): was a hardcoded 10000.0 — 100x the
    # then-declared $100 account. Routed through shared/account.py since;
    # ADR-029 later set the declared size to $10,000 again. The routing is
    # the fix, not the number — never reintroduce a literal here.
    initial_capital: float = PAPER_INITIAL_BALANCE
    ruin_threshold: float = 0.50  # Define ruin as losing 50% of capital

    # Trade statistics (will be calculated from historical trades if not provided)
    win_rate: Optional[float] = None
    avg_win: Optional[float] = None
    avg_loss: Optional[float] = None
    avg_trade_size: Optional[float] = None

    # Position sizing analysis
    test_position_sizes: List[float] = None  # % of capital per trade to test

    def __post_init__(self):
        if self.test_position_sizes is None:
            self.test_position_sizes = [0.01, 0.02, 0.03, 0.05, 0.10, 0.15, 0.20]


@dataclass
class RiskOfRuinResults:
    """Risk of ruin calculation results"""

    config: RiskOfRuinConfig

    # Trade statistics
    win_rate: float
    loss_rate: float
    avg_win: float
    avg_loss: float
    win_loss_ratio: float  # Avg win / Avg loss
    expectancy: float  # Expected value per trade

    # Risk of ruin calculations
    ror_current_sizing: float  # Risk of ruin with current position sizing
    ror_by_position_size: Dict[float, float]  # {position_size: ror}

    # Optimal position sizing
    kelly_criterion: float  # Kelly optimal position size
    half_kelly: float  # Conservative Kelly (50%)
    quarter_kelly: float  # Very conservative Kelly (25%)

    # Safe capital recommendations
    min_capital_for_5pct_ror: float  # Capital needed for <5% RoR
    min_capital_for_1pct_ror: float  # Capital needed for <1% RoR

    # Consecutive loss analysis
    prob_n_consecutive_losses: Dict[int, float]  # {n_losses: probability}
    max_consecutive_losses_95pct: int  # Max losses expected 95% of time

    def is_safe_to_trade(self) -> bool:
        """
        Determine if current configuration is safe

        Returns:
            True if risk of ruin < 5%
        """
        return self.ror_current_sizing < 0.05

    def get_recommended_position_size(self, risk_tolerance: str = "moderate") -> float:
        """
        Get recommended position size based on risk tolerance

        Args:
            risk_tolerance: 'conservative', 'moderate', or 'aggressive'

        Returns:
            Recommended position size as % of capital
        """
        if risk_tolerance == "conservative":
            return self.quarter_kelly
        elif risk_tolerance == "moderate":
            return self.half_kelly
        elif risk_tolerance == "aggressive":
            return self.kelly_criterion
        else:
            return self.half_kelly

    def to_dict(self) -> Dict[str, Any]:
        """Convert results to dictionary"""
        return {
            "trade_statistics": {
                "win_rate": round(self.win_rate * 100, 2),
                "loss_rate": round(self.loss_rate * 100, 2),
                "avg_win": round(self.avg_win, 2),
                "avg_loss": round(self.avg_loss, 2),
                "win_loss_ratio": round(self.win_loss_ratio, 2),
                "expectancy": round(self.expectancy, 2),
            },
            "risk_of_ruin": {
                "current_sizing": round(self.ror_current_sizing * 100, 4),
                "is_safe": self.is_safe_to_trade(),
                "by_position_size": {
                    f"{size * 100:.0f}%": round(ror * 100, 4)
                    for size, ror in sorted(self.ror_by_position_size.items())
                },
            },
            "optimal_position_sizing": {
                "kelly_criterion": round(self.kelly_criterion * 100, 2),
                "half_kelly_recommended": round(self.half_kelly * 100, 2),
                "quarter_kelly_conservative": round(self.quarter_kelly * 100, 2),
            },
            "capital_requirements": {
                "for_5pct_ror": round(self.min_capital_for_5pct_ror, 2),
                "for_1pct_ror": round(self.min_capital_for_1pct_ror, 2),
            },
            "consecutive_loss_probabilities": {
                f"{n}_losses": round(prob * 100, 4)
                for n, prob in sorted(self.prob_n_consecutive_losses.items())
            },
            "recommendations": {
                "conservative": {
                    "position_size_pct": round(
                        self.get_recommended_position_size("conservative") * 100, 2
                    ),
                    "max_risk_per_trade": round(
                        self.avg_loss * self.get_recommended_position_size("conservative"), 2
                    ),
                },
                "moderate": {
                    "position_size_pct": round(
                        self.get_recommended_position_size("moderate") * 100, 2
                    ),
                    "max_risk_per_trade": round(
                        self.avg_loss * self.get_recommended_position_size("moderate"), 2
                    ),
                },
                "aggressive": {
                    "position_size_pct": round(
                        self.get_recommended_position_size("aggressive") * 100, 2
                    ),
                    "max_risk_per_trade": round(
                        self.avg_loss * self.get_recommended_position_size("aggressive"), 2
                    ),
                },
            },
        }


class RiskOfRuinCalculator:
    """
    Risk of Ruin Calculator

    Calculates the probability of losing a significant portion of trading capital.

    Usage:
        config = RiskOfRuinConfig(initial_capital=PAPER_INITIAL_BALANCE)
        calculator = RiskOfRuinCalculator(config)

        # Historical trades
        trades = [
            {'pnl': 100},
            {'pnl': -50},
            {'pnl': 200},
            {'pnl': -75},
            # ...
        ]

        results = calculator.calculate(trades)

        print(f"Win rate: {results.win_rate:.2%}")
        print(f"Risk of ruin: {results.ror_current_sizing:.2%}")
        print(f"Kelly criterion: {results.kelly_criterion:.2%}")
        print(f"Recommended size: {results.half_kelly:.2%} (Half Kelly)")

        if results.is_safe_to_trade():
            print("✅ Safe to trade with current sizing")
        else:
            print("⚠️  High risk of ruin - reduce position size!")
    """

    def __init__(self, config: Optional[RiskOfRuinConfig] = None):
        """Initialize risk of ruin calculator"""
        self.config = config or RiskOfRuinConfig()
        logger.info(f"Initialized RiskOfRuinCalculator with capital={self.config.initial_capital}")

    def calculate_trade_statistics(self, trades: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Calculate trade statistics from historical trades

        Args:
            trades: List of trades with 'pnl' or 'realized_pnl'

        Returns:
            Dict with win_rate, avg_win, avg_loss, etc.
        """
        pnls = [trade.get("pnl", 0) or trade.get("realized_pnl", 0) for trade in trades]

        winning_trades = [pnl for pnl in pnls if pnl > 0]
        losing_trades = [pnl for pnl in pnls if pnl < 0]

        total_trades = len(pnls)
        num_wins = len(winning_trades)
        num_losses = len(losing_trades)

        win_rate = num_wins / total_trades if total_trades > 0 else 0
        loss_rate = num_losses / total_trades if total_trades > 0 else 0

        avg_win = np.mean(winning_trades) if winning_trades else 0
        avg_loss = abs(np.mean(losing_trades)) if losing_trades else 0

        win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0

        # Expectancy = (Win Rate × Average Win) - (Loss Rate × Average Loss)
        expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)

        return {
            "win_rate": win_rate,
            "loss_rate": loss_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "win_loss_ratio": win_loss_ratio,
            "expectancy": expectancy,
            "total_trades": total_trades,
        }

    def calculate_risk_of_ruin(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        capital: float,
        position_size_pct: float,
    ) -> float:
        """
        Calculate risk of ruin for given parameters

        Uses simplified gambler's ruin formula

        Args:
            win_rate: Probability of winning trade
            avg_win: Average winning trade amount
            avg_loss: Average losing trade amount (positive number)
            capital: Available trading capital
            position_size_pct: Position size as % of capital

        Returns:
            Probability of ruin (0 to 1)
        """
        if win_rate >= 1.0 or win_rate <= 0:
            return 0 if win_rate >= 1.0 else 1.0

        # Risk per trade
        risk_per_trade = capital * position_size_pct

        # Number of trades until ruin
        trades_to_ruin = capital / (avg_loss * position_size_pct)

        # Loss rate
        loss_rate = 1 - win_rate

        # Gambler's ruin formula (simplified)
        # RoR = (loss_rate / win_rate) ^ trades_to_ruin
        if loss_rate >= win_rate:
            # Negative expectancy - high risk of ruin
            ror = min(1.0, (loss_rate / win_rate) ** min(trades_to_ruin, 100))
        else:
            # Positive expectancy - lower risk
            ror = (loss_rate / win_rate) ** trades_to_ruin

        # Cap at 100%
        return min(1.0, max(0.0, ror))

    def calculate_kelly_criterion(self, win_rate: float, win_loss_ratio: float) -> float:
        """
        Calculate Kelly Criterion optimal position size

        Kelly % = W - [(1 - W) / R]
        Where:
            W = Win rate
            R = Win/Loss ratio (Avg Win / Avg Loss)

        Args:
            win_rate: Probability of winning
            win_loss_ratio: Ratio of avg win to avg loss

        Returns:
            Optimal position size as % of capital
        """
        if win_loss_ratio <= 0:
            return 0.0

        kelly = win_rate - ((1 - win_rate) / win_loss_ratio)

        # Kelly can be negative (don't trade) or > 1 (highly confident)
        # Cap at reasonable values
        kelly = max(0.0, min(kelly, 0.25))  # Max 25% of capital

        return kelly

    def calculate_consecutive_loss_probabilities(
        self, loss_rate: float, max_consecutive: int = 10
    ) -> Dict[int, float]:
        """
        Calculate probability of N consecutive losses

        P(N consecutive losses) = loss_rate ^ N

        Args:
            loss_rate: Probability of single loss
            max_consecutive: Maximum number to calculate

        Returns:
            Dict of {n: probability}
        """
        probabilities = {}
        for n in range(1, max_consecutive + 1):
            prob = loss_rate**n
            probabilities[n] = prob

        return probabilities

    def calculate_min_capital(
        self, target_ror: float, win_rate: float, avg_loss: float, position_size_pct: float
    ) -> float:
        """
        Calculate minimum capital needed to achieve target RoR

        Args:
            target_ror: Target risk of ruin (e.g., 0.05 for 5%)
            win_rate: Win rate
            avg_loss: Average loss
            position_size_pct: Position size %

        Returns:
            Minimum capital required
        """

        # Binary search for minimum capital
        def ror_for_capital(capital):
            return self.calculate_risk_of_ruin(
                win_rate=win_rate,
                avg_win=avg_loss * 2,  # Assume 2:1 win/loss ratio
                avg_loss=avg_loss,
                capital=capital,
                position_size_pct=position_size_pct,
            )

        # Search range
        min_cap = self.config.initial_capital
        max_cap = self.config.initial_capital * 10

        # Binary search
        while max_cap - min_cap > 100:
            mid_cap = (min_cap + max_cap) / 2
            ror = ror_for_capital(mid_cap)

            if ror > target_ror:
                min_cap = mid_cap
            else:
                max_cap = mid_cap

        return max_cap

    def calculate(self, trades: List[Dict[str, Any]]) -> RiskOfRuinResults:
        """
        Run complete risk of ruin analysis

        Args:
            trades: Historical trades with PnL

        Returns:
            RiskOfRuinResults with complete analysis
        """
        logger.info("=" * 60)
        logger.info("RISK OF RUIN ANALYSIS STARTING")
        logger.info("=" * 60)

        # Calculate trade statistics
        stats = self.calculate_trade_statistics(trades)

        logger.info("Trade Statistics:")
        logger.info(f"  Win rate: {stats['win_rate']:.2%}")
        logger.info(f"  Avg win: ${stats['avg_win']:.2f}")
        logger.info(f"  Avg loss: ${stats['avg_loss']:.2f}")
        logger.info(f"  Win/Loss ratio: {stats['win_loss_ratio']:.2f}")
        logger.info(f"  Expectancy: ${stats['expectancy']:.2f}")

        # Calculate Kelly Criterion
        kelly = self.calculate_kelly_criterion(stats["win_rate"], stats["win_loss_ratio"])
        half_kelly = kelly * 0.50
        quarter_kelly = kelly * 0.25

        logger.info("\nKelly Criterion:")
        logger.info(f"  Full Kelly: {kelly:.2%}")
        logger.info(f"  Half Kelly: {half_kelly:.2%} (recommended)")
        logger.info(f"  Quarter Kelly: {quarter_kelly:.2%} (conservative)")

        # Calculate RoR for different position sizes
        ror_by_position_size = {}
        for pos_size in self.config.test_position_sizes:
            ror = self.calculate_risk_of_ruin(
                win_rate=stats["win_rate"],
                avg_win=stats["avg_win"],
                avg_loss=stats["avg_loss"],
                capital=self.config.initial_capital,
                position_size_pct=pos_size,
            )
            ror_by_position_size[pos_size] = ror

        # Calculate consecutive loss probabilities
        consecutive_loss_probs = self.calculate_consecutive_loss_probabilities(
            stats["loss_rate"], max_consecutive=10
        )

        # Find max consecutive losses at 95% confidence
        max_consecutive_95 = next(
            (n for n, prob in consecutive_loss_probs.items() if prob < 0.05), 10
        )

        # Calculate minimum capital requirements
        min_capital_5pct = self.calculate_min_capital(
            target_ror=0.05,
            win_rate=stats["win_rate"],
            avg_loss=stats["avg_loss"],
            position_size_pct=half_kelly,
        )

        min_capital_1pct = self.calculate_min_capital(
            target_ror=0.01,
            win_rate=stats["win_rate"],
            avg_loss=stats["avg_loss"],
            position_size_pct=half_kelly,
        )

        # Create results
        results = RiskOfRuinResults(
            config=self.config,
            win_rate=stats["win_rate"],
            loss_rate=stats["loss_rate"],
            avg_win=stats["avg_win"],
            avg_loss=stats["avg_loss"],
            win_loss_ratio=stats["win_loss_ratio"],
            expectancy=stats["expectancy"],
            ror_current_sizing=ror_by_position_size.get(0.02, 0),  # Assume 2% default
            ror_by_position_size=ror_by_position_size,
            kelly_criterion=kelly,
            half_kelly=half_kelly,
            quarter_kelly=quarter_kelly,
            min_capital_for_5pct_ror=min_capital_5pct,
            min_capital_for_1pct_ror=min_capital_1pct,
            prob_n_consecutive_losses=consecutive_loss_probs,
            max_consecutive_losses_95pct=max_consecutive_95,
        )

        logger.info("\nRisk of Ruin Analysis:")
        logger.info(f"  2% position size: {results.ror_by_position_size.get(0.02, 0):.4%}")
        logger.info(f"  5% position size: {results.ror_by_position_size.get(0.05, 0):.4%}")
        logger.info(f"  10% position size: {results.ror_by_position_size.get(0.10, 0):.4%}")

        logger.info("\nConsecutive Losses:")
        logger.info(f"  Max expected (95% confidence): {max_consecutive_95} losses")
        logger.info(f"  Probability of 5 consecutive: {consecutive_loss_probs.get(5, 0):.4%}")

        logger.info("=" * 60)
        logger.info("RISK OF RUIN ANALYSIS COMPLETE")
        logger.info(f"Is Safe: {'YES ✅' if results.is_safe_to_trade() else 'NO ⚠️ '}")
        logger.info("=" * 60)

        return results

    def save_results(self, results: RiskOfRuinResults, filepath: str):
        """Save risk of ruin results to JSON"""
        with open(filepath, "w") as f:
            json.dump(results.to_dict(), f, indent=2)
        logger.info(f"Saved risk of ruin results to {filepath}")

    def load_results(self, filepath: str) -> Dict[str, Any]:
        """Load risk of ruin results from JSON"""
        with open(filepath, "r") as f:
            results_dict = json.load(f)
        logger.info(f"Loaded risk of ruin results from {filepath}")
        return results_dict


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    config = RiskOfRuinConfig(initial_capital=PAPER_INITIAL_BALANCE)
    calculator = RiskOfRuinCalculator(config)

    # Example trades
    example_trades = [
        {"pnl": 100},
        {"pnl": -50},
        {"pnl": 150},
        {"pnl": -75},
        {"pnl": 200},
        {"pnl": -60},
    ] * 15  # 90 trades

    print("Risk of Ruin Calculator initialized")
    print(f"Initial capital: ${config.initial_capital:,}")
