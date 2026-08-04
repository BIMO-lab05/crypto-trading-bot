"""
Monte Carlo Simulator
Created: 2025-12-06
Purpose: Assess strategy robustness through random path simulation

Monte Carlo simulation answers critical questions:
- What's the probability of losing more than X%?
- What's the expected maximum drawdown?
- How likely is the strategy to beat the market?
- What's the confidence interval for expected returns?

Process:
1. Take historical trade results
2. Randomly shuffle trade order (1000+ times)
3. Calculate equity curves for all paths
4. Analyze distribution of outcomes
"""

import logging
import os
import sys
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from scipy import stats
import json
from tqdm import tqdm

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
class MonteCarloConfig:
    """Configuration for Monte Carlo simulation"""

    # Simulation parameters
    num_simulations: int = 1000  # Number of random paths to simulate
    # FIX 2026-08-03 (capital audit): was 10000.0, 100x the real account.
    initial_capital: float = PAPER_INITIAL_BALANCE  # Starting capital

    # Confidence intervals
    confidence_levels: List[float] = field(default_factory=lambda: [0.90, 0.95, 0.99])  # 90%, 95%, 99%

    # Risk thresholds
    max_acceptable_drawdown: float = 0.30  # 30%
    min_acceptable_return: float = 0.0  # 0%

    # Bootstrap settings
    use_bootstrap: bool = True  # Resample with replacement
    preserve_trade_sequence: bool = False  # If True, keeps consecutive trades together


@dataclass
class MonteCarloPath:
    """Single Monte Carlo simulation path"""
    path_number: int
    trade_sequence: List[Dict[str, Any]]  # Shuffled trades
    equity_curve: List[float]  # Equity over time

    # Path metrics
    final_equity: float = 0.0
    total_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    num_losing_streaks: int = 0
    max_losing_streak: int = 0


@dataclass
class MonteCarloResults:
    """Complete Monte Carlo simulation results"""
    config: MonteCarloConfig
    original_equity_curve: List[float]
    simulated_paths: List[MonteCarloPath]

    # Distribution statistics
    mean_final_equity: float = 0.0
    median_final_equity: float = 0.0
    std_final_equity: float = 0.0

    mean_return: float = 0.0
    median_return: float = 0.0
    std_return: float = 0.0

    mean_max_drawdown: float = 0.0
    median_max_drawdown: float = 0.0
    worst_drawdown: float = 0.0

    # Confidence intervals
    confidence_intervals: Dict[float, Dict[str, Tuple[float, float]]] = field(default_factory=dict)
    # Format: {0.95: {'return': (lower, upper), 'drawdown': (lower, upper)}}

    # Risk metrics
    probability_of_loss: float = 0.0  # Probability final equity < initial capital
    probability_of_ruin: float = 0.0  # Probability of losing > 50% capital
    probability_drawdown_exceeds_30pct: float = 0.0

    # Best/Worst paths
    best_path: Optional[MonteCarloPath] = None
    worst_path: Optional[MonteCarloPath] = None

    def get_percentile(self, metric: str, percentile: float) -> float:
        """
        Get percentile value for a metric

        Args:
            metric: 'return', 'drawdown', or 'equity'
            percentile: Percentile to get (e.g., 5 for 5th percentile)

        Returns:
            Value at given percentile
        """
        if metric == 'return':
            values = [path.total_return for path in self.simulated_paths]
        elif metric == 'drawdown':
            values = [path.max_drawdown for path in self.simulated_paths]
        elif metric == 'equity':
            values = [path.final_equity for path in self.simulated_paths]
        else:
            raise ValueError(f"Unknown metric: {metric}")

        return np.percentile(values, percentile)

    def to_dict(self) -> Dict[str, Any]:
        """Convert results to dictionary"""
        return {
            'config': {
                'num_simulations': self.config.num_simulations,
                'initial_capital': self.config.initial_capital,
            },
            'distribution_statistics': {
                'return': {
                    'mean': round(self.mean_return * 100, 2),
                    'median': round(self.median_return * 100, 2),
                    'std': round(self.std_return * 100, 2),
                    'percentile_5': round(self.get_percentile('return', 5) * 100, 2),
                    'percentile_95': round(self.get_percentile('return', 95) * 100, 2),
                },
                'max_drawdown': {
                    'mean': round(self.mean_max_drawdown * 100, 2),
                    'median': round(self.median_max_drawdown * 100, 2),
                    'worst': round(self.worst_drawdown * 100, 2),
                    'percentile_95': round(self.get_percentile('drawdown', 95) * 100, 2),
                }
            },
            'risk_metrics': {
                'probability_of_loss': round(self.probability_of_loss * 100, 2),
                'probability_of_ruin': round(self.probability_of_ruin * 100, 2),
                'probability_drawdown_exceeds_30pct': round(self.probability_drawdown_exceeds_30pct * 100, 2),
            },
            'confidence_intervals': {
                f"{int(level*100)}%": {
                    'return': [round(self.confidence_intervals[level]['return'][0] * 100, 2),
                              round(self.confidence_intervals[level]['return'][1] * 100, 2)],
                    'drawdown': [round(self.confidence_intervals[level]['drawdown'][0] * 100, 2),
                                round(self.confidence_intervals[level]['drawdown'][1] * 100, 2)],
                }
                for level in self.config.confidence_levels
            },
            'extremes': {
                'best_return': round(self.best_path.total_return * 100, 2) if self.best_path else 0,
                'worst_return': round(self.worst_path.total_return * 100, 2) if self.worst_path else 0,
                'best_drawdown': round(self.best_path.max_drawdown * 100, 2) if self.best_path else 0,
                'worst_drawdown': round(self.worst_path.max_drawdown * 100, 2) if self.worst_path else 0,
            }
        }


class MonteCarloSimulator:
    """
    Monte Carlo Simulator for Trading Strategy Assessment

    Simulates thousands of possible trading scenarios by randomly
    reordering historical trades to understand probability distributions
    and worst-case scenarios.

    Usage:
        config = MonteCarloConfig(num_simulations=1000)
        simulator = MonteCarloSimulator(config)

        # Historical trades from backtest
        trades = [
            {'pnl': 100, 'return': 0.01},
            {'pnl': -50, 'return': -0.005},
            {'pnl': 200, 'return': 0.02},
            # ...
        ]

        results = simulator.simulate(trades)

        print(f"Mean return: {results.mean_return:.2%}")
        print(f"Probability of loss: {results.probability_of_loss:.2%}")
        print(f"95% confidence interval: {results.confidence_intervals[0.95]['return']}")
        print(f"Worst drawdown (95th percentile): {results.get_percentile('drawdown', 95):.2%}")
    """

    def __init__(self, config: Optional[MonteCarloConfig] = None):
        """Initialize Monte Carlo simulator"""
        self.config = config or MonteCarloConfig()
        logger.info(f"Initialized MonteCarloSimulator with {self.config.num_simulations} simulations")

    def simulate_single_path(
        self,
        trades: List[Dict[str, Any]],
        path_number: int
    ) -> MonteCarloPath:
        """
        Simulate a single random trading path

        Args:
            trades: List of historical trades
            path_number: Path identifier

        Returns:
            MonteCarloPath with simulated equity curve
        """
        # Shuffle trades (bootstrap resampling)
        if self.config.use_bootstrap:
            # Sample with replacement
            shuffled_trades = [trades[i] for i in np.random.choice(len(trades), len(trades), replace=True)]
        else:
            # Permutation without replacement
            shuffled_trades = trades.copy()
            np.random.shuffle(shuffled_trades)

        # Calculate equity curve
        equity = self.config.initial_capital
        equity_curve = [equity]
        peak_equity = equity
        max_drawdown = 0.0

        for trade in shuffled_trades:
            # Apply trade PnL
            pnl = trade.get('pnl', 0) or trade.get('realized_pnl', 0)
            equity += pnl
            equity_curve.append(equity)

            # Update drawdown
            if equity > peak_equity:
                peak_equity = equity

            current_drawdown = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0
            max_drawdown = max(max_drawdown, current_drawdown)

        # Calculate path metrics
        final_equity = equity_curve[-1]
        total_return = (final_equity - self.config.initial_capital) / self.config.initial_capital

        # Calculate Sharpe ratio (from returns)
        returns = np.diff(equity_curve) / equity_curve[:-1]
        sharpe_ratio = (np.mean(returns) / np.std(returns) * np.sqrt(252)) if len(returns) > 1 and np.std(returns) > 0 else 0

        # Count losing streaks
        losing_streaks = 0
        current_streak = 0
        max_losing_streak = 0

        for trade in shuffled_trades:
            pnl = trade.get('pnl', 0) or trade.get('realized_pnl', 0)
            if pnl < 0:
                current_streak += 1
                max_losing_streak = max(max_losing_streak, current_streak)
            else:
                if current_streak > 0:
                    losing_streaks += 1
                current_streak = 0

        path = MonteCarloPath(
            path_number=path_number,
            trade_sequence=shuffled_trades,
            equity_curve=equity_curve,
            final_equity=final_equity,
            total_return=total_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            num_losing_streaks=losing_streaks,
            max_losing_streak=max_losing_streak
        )

        return path

    def simulate(
        self,
        trades: List[Dict[str, Any]],
        show_progress: bool = True
    ) -> MonteCarloResults:
        """
        Run complete Monte Carlo simulation

        Args:
            trades: Historical trades with 'pnl' or 'realized_pnl' field
            show_progress: Show progress bar

        Returns:
            MonteCarloResults with complete distribution analysis
        """
        logger.info("="*60)
        logger.info("MONTE CARLO SIMULATION STARTING")
        logger.info(f"Simulating {self.config.num_simulations} random trading paths")
        logger.info("="*60)

        if len(trades) < 10:
            raise ValueError("Need at least 10 trades for meaningful Monte Carlo simulation")

        # Calculate original equity curve
        original_equity = self.config.initial_capital
        original_curve = [original_equity]
        for trade in trades:
            pnl = trade.get('pnl', 0) or trade.get('realized_pnl', 0)
            original_equity += pnl
            original_curve.append(original_equity)

        # Simulate all paths
        simulated_paths = []

        if show_progress:
            progress_bar = tqdm(total=self.config.num_simulations, desc="Simulating paths")

        for i in range(self.config.num_simulations):
            path = self.simulate_single_path(trades, i + 1)
            simulated_paths.append(path)

            if show_progress:
                progress_bar.update(1)

        if show_progress:
            progress_bar.close()

        # Calculate distribution statistics
        final_equities = [path.final_equity for path in simulated_paths]
        returns = [path.total_return for path in simulated_paths]
        drawdowns = [path.max_drawdown for path in simulated_paths]

        mean_final_equity = np.mean(final_equities)
        median_final_equity = np.median(final_equities)
        std_final_equity = np.std(final_equities)

        mean_return = np.mean(returns)
        median_return = np.median(returns)
        std_return = np.std(returns)

        mean_max_drawdown = np.mean(drawdowns)
        median_max_drawdown = np.median(drawdowns)
        worst_drawdown = np.max(drawdowns)

        # Calculate confidence intervals
        confidence_intervals = {}
        for level in self.config.confidence_levels:
            alpha = 1 - level
            return_ci = (
                np.percentile(returns, alpha/2 * 100),
                np.percentile(returns, (1 - alpha/2) * 100)
            )
            drawdown_ci = (
                np.percentile(drawdowns, alpha/2 * 100),
                np.percentile(drawdowns, (1 - alpha/2) * 100)
            )
            confidence_intervals[level] = {
                'return': return_ci,
                'drawdown': drawdown_ci
            }

        # Calculate risk probabilities
        probability_of_loss = sum(1 for r in returns if r < 0) / len(returns)
        probability_of_ruin = sum(1 for r in returns if r < -0.50) / len(returns)  # Lose > 50%
        probability_drawdown_exceeds_30pct = sum(1 for dd in drawdowns if dd > 0.30) / len(drawdowns)

        # Find best and worst paths
        best_path = max(simulated_paths, key=lambda p: p.total_return)
        worst_path = min(simulated_paths, key=lambda p: p.total_return)

        # Create results
        results = MonteCarloResults(
            config=self.config,
            original_equity_curve=original_curve,
            simulated_paths=simulated_paths,
            mean_final_equity=mean_final_equity,
            median_final_equity=median_final_equity,
            std_final_equity=std_final_equity,
            mean_return=mean_return,
            median_return=median_return,
            std_return=std_return,
            mean_max_drawdown=mean_max_drawdown,
            median_max_drawdown=median_max_drawdown,
            worst_drawdown=worst_drawdown,
            confidence_intervals=confidence_intervals,
            probability_of_loss=probability_of_loss,
            probability_of_ruin=probability_of_ruin,
            probability_drawdown_exceeds_30pct=probability_drawdown_exceeds_30pct,
            best_path=best_path,
            worst_path=worst_path
        )

        logger.info("="*60)
        logger.info("MONTE CARLO SIMULATION COMPLETE")
        logger.info(f"Mean return: {mean_return:.2%} ± {std_return:.2%}")
        logger.info(f"95% CI return: [{results.confidence_intervals[0.95]['return'][0]:.2%}, {results.confidence_intervals[0.95]['return'][1]:.2%}]")
        logger.info(f"Probability of loss: {probability_of_loss:.2%}")
        logger.info(f"Worst drawdown (95th percentile): {results.get_percentile('drawdown', 95):.2%}")
        logger.info("="*60)

        return results

    def save_results(self, results: MonteCarloResults, filepath: str):
        """Save Monte Carlo results to JSON"""
        with open(filepath, 'w') as f:
            json.dump(results.to_dict(), f, indent=2)
        logger.info(f"Saved Monte Carlo results to {filepath}")

    def load_results(self, filepath: str) -> Dict[str, Any]:
        """Load Monte Carlo results from JSON"""
        with open(filepath, 'r') as f:
            results_dict = json.load(f)
        logger.info(f"Loaded Monte Carlo results from {filepath}")
        return results_dict


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example: Create simulator
    config = MonteCarloConfig(
        num_simulations=1000, initial_capital=PAPER_INITIAL_BALANCE
    )
    simulator = MonteCarloSimulator(config)

    # Example trades
    example_trades = [
        {'pnl': 100}, {'pnl': -50}, {'pnl': 200}, {'pnl': -75},
        {'pnl': 150}, {'pnl': -100}, {'pnl': 250}, {'pnl': -80},
    ] * 10  # 80 trades total

    print(f"Monte Carlo Simulator initialized")
    print(f"Will simulate {config.num_simulations} random paths")
    print(f"Using {len(example_trades)} historical trades")
