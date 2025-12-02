"""
Walk Forward Efficiency (WFE) Testing Framework
Research Source: Walk Forward Analysis, Out-of-Sample Testing, Strategy Validation

Purpose:
- Validate trading strategy robustness using walk-forward optimization
- Detect overfitting by comparing in-sample vs out-of-sample performance
- Calculate statistical confidence based on trade count
- Provide comprehensive robustness reports

RESEARCH: Walk Forward Efficiency measures how well in-sample optimization
translates to out-of-sample performance. WFE = OOS Performance / IS Performance.
- WFE > 50-60%: Strategy is robust and likely not overfit
- WFE < 50%: Strategy may be overfit to historical data
- Minimum 385 trades required for 95% statistical confidence (Chebyshev bound)

Key Concepts:
- In-Sample (IS): Training period where strategy parameters are optimized
- Out-of-Sample (OOS): Testing period to validate optimization results
- Rolling Windows: Multiple IS/OOS periods for continuous validation
- Statistical Confidence: Based on sample size and variance
"""

import logging
import numpy as np
from enum import Enum
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
import math

# Configure module logger
logger = logging.getLogger(__name__)


class WFEStatus(Enum):
    """Status indicators for walk-forward efficiency analysis"""
    ROBUST = "robust"                    # WFE exceeds threshold - strategy is robust
    MARGINAL = "marginal"                # WFE near threshold - needs monitoring
    OVERFIT = "overfit"                  # WFE below threshold - strategy likely overfit
    INSUFFICIENT_DATA = "insufficient"   # Not enough trades for confidence


@dataclass
class WFEConfig:
    """
    Configuration for Walk Forward Efficiency testing

    Research-backed default values:
    - 70/30 IS/OOS split is standard in quantitative finance
    - 385 trades for 95% confidence based on Chebyshev's inequality
    - 50% WFE threshold is industry standard for robustness

    Attributes:
        in_sample_pct: Percentage of data for in-sample training (default 70%)
        out_of_sample_pct: Percentage of data for out-of-sample testing (default 30%)
        min_trades_for_confidence: Minimum trades for 95% statistical confidence
        min_wfe_threshold: Minimum WFE ratio to consider strategy robust
        rolling_windows: Number of walk-forward periods for rolling analysis
        marginal_threshold_pct: Threshold below min_wfe to consider marginal (not overfit)
        risk_free_rate: Annual risk-free rate for Sharpe calculation
        trading_days_per_year: Trading days per year (365 for crypto 24/7 markets)
    """
    # Data split configuration
    in_sample_pct: float = 0.70           # 70% for training
    out_of_sample_pct: float = 0.30       # 30% for testing

    # Statistical confidence parameters
    min_trades_for_confidence: int = 385   # For 95% confidence level

    # Robustness thresholds
    min_wfe_threshold: float = 0.50        # 50% minimum WFE for robustness
    marginal_threshold_pct: float = 0.10   # Within 10% of threshold = marginal

    # Rolling window configuration
    rolling_windows: int = 5               # Number of walk-forward periods

    # Financial parameters
    risk_free_rate: float = 0.0            # Risk-free rate (default 0%)
    trading_days_per_year: int = 365       # Crypto markets are 24/7

    def __post_init__(self):
        """Validate configuration after initialization"""
        # Ensure split percentages sum to 1.0
        if not math.isclose(self.in_sample_pct + self.out_of_sample_pct, 1.0, rel_tol=1e-9):
            raise ValueError(
                f"IS ({self.in_sample_pct}) + OOS ({self.out_of_sample_pct}) "
                f"must equal 1.0"
            )

        # Validate percentage ranges
        if not 0.0 < self.in_sample_pct < 1.0:
            raise ValueError(f"in_sample_pct must be between 0 and 1: {self.in_sample_pct}")

        if not 0.0 < self.out_of_sample_pct < 1.0:
            raise ValueError(f"out_of_sample_pct must be between 0 and 1: {self.out_of_sample_pct}")

        # Validate other parameters
        if self.min_trades_for_confidence <= 0:
            raise ValueError(f"min_trades_for_confidence must be positive: {self.min_trades_for_confidence}")

        if not 0.0 < self.min_wfe_threshold <= 1.0:
            raise ValueError(f"min_wfe_threshold must be between 0 and 1: {self.min_wfe_threshold}")

        if self.rolling_windows < 1:
            raise ValueError(f"rolling_windows must be at least 1: {self.rolling_windows}")

        logger.debug(
            f"WFEConfig initialized: IS={self.in_sample_pct:.0%}, "
            f"OOS={self.out_of_sample_pct:.0%}, "
            f"min_trades={self.min_trades_for_confidence}, "
            f"wfe_threshold={self.min_wfe_threshold:.0%}"
        )


@dataclass
class TradeData:
    """
    Single trade record for walk-forward analysis

    Attributes:
        trade_id: Unique identifier for the trade
        symbol: Trading symbol (e.g., 'BTCUSDT')
        side: Trade direction ('long' or 'short')
        entry_time: Trade entry timestamp
        exit_time: Trade exit timestamp
        entry_price: Entry price
        exit_price: Exit price
        quantity: Trade size
        pnl: Profit/Loss in quote currency
        pnl_pct: Profit/Loss as percentage of entry
        fees: Total fees paid
        strategy: Strategy name that generated the trade
    """
    trade_id: str
    symbol: str
    side: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    fees: float = 0.0
    strategy: str = "unknown"


@dataclass
class PeriodMetrics:
    """
    Performance metrics for a single IS or OOS period

    Attributes:
        period_start: Start timestamp of the period
        period_end: End timestamp of the period
        trade_count: Number of trades in period
        total_return: Total return percentage
        sharpe_ratio: Annualized Sharpe ratio
        win_rate: Percentage of winning trades
        profit_factor: Gross profit / Gross loss
        avg_trade_pnl: Average P&L per trade
        max_drawdown: Maximum drawdown percentage
        volatility: Annualized volatility
        expectancy: Expected value per trade
    """
    period_start: datetime
    period_end: datetime
    trade_count: int
    total_return: float
    sharpe_ratio: float
    win_rate: float
    profit_factor: float
    avg_trade_pnl: float
    max_drawdown: float
    volatility: float
    expectancy: float


@dataclass
class WalkForwardResult:
    """
    Result of a single walk-forward test period

    Contains both IS and OOS metrics plus WFE calculations.

    Attributes:
        window_number: Index of this walk-forward window (1-based)
        in_sample_metrics: Metrics from training period
        out_of_sample_metrics: Metrics from testing period
        wfe_return: WFE based on total return ratio
        wfe_sharpe: WFE based on Sharpe ratio
        wfe_profit_factor: WFE based on profit factor
        is_robust: True if WFE exceeds threshold
        status: Overall status assessment
        trade_count: Total trades across both periods
        confidence_level: Statistical confidence based on sample size
        notes: Additional observations or warnings
    """
    window_number: int
    in_sample_metrics: PeriodMetrics
    out_of_sample_metrics: PeriodMetrics

    # WFE metrics (ratio of OOS to IS performance)
    wfe_return: float               # OOS Return / IS Return
    wfe_sharpe: float               # OOS Sharpe / IS Sharpe
    wfe_profit_factor: float        # OOS PF / IS PF

    # Robustness assessment
    is_robust: bool
    status: WFEStatus

    # Statistical confidence
    trade_count: int
    confidence_level: float

    # Additional info
    notes: List[str] = field(default_factory=list)


@dataclass
class RobustnessReport:
    """
    Comprehensive robustness report from walk-forward analysis

    Attributes:
        strategy_name: Name of the strategy being tested
        analysis_date: When the analysis was performed
        total_trades: Total number of trades analyzed
        total_windows: Number of walk-forward windows tested

        # Overall metrics
        avg_wfe_return: Average WFE based on returns across windows
        avg_wfe_sharpe: Average WFE based on Sharpe across windows
        avg_wfe_profit_factor: Average WFE based on profit factor

        # Robustness assessment
        overall_status: Combined status assessment
        robust_windows: Number of windows that passed robustness check
        robust_percentage: Percentage of windows that are robust

        # Statistical measures
        overall_confidence: Statistical confidence level
        wfe_consistency: Standard deviation of WFE across windows

        # Individual results
        window_results: Detailed results for each window

        # Recommendations
        recommendations: List of actionable recommendations
    """
    strategy_name: str
    analysis_date: datetime
    total_trades: int
    total_windows: int

    # Average WFE metrics across all windows
    avg_wfe_return: float
    avg_wfe_sharpe: float
    avg_wfe_profit_factor: float

    # Overall assessment
    overall_status: WFEStatus
    robust_windows: int
    robust_percentage: float

    # Statistical measures
    overall_confidence: float
    wfe_consistency: float          # Lower is better (more consistent)

    # Detailed results
    window_results: List[WalkForwardResult]

    # Recommendations
    recommendations: List[str] = field(default_factory=list)


class WalkForwardTester:
    """
    Walk Forward Efficiency Testing Engine

    RESEARCH-BACKED IMPLEMENTATION:
    - Walk-forward optimization validates strategy robustness
    - Compares in-sample (training) vs out-of-sample (testing) performance
    - WFE ratio indicates how well optimization translates to live trading
    - Multiple rolling windows provide continuous validation

    WFE Interpretation:
    - WFE > 60%: Excellent - strategy likely very robust
    - WFE 50-60%: Good - strategy is robust
    - WFE 40-50%: Marginal - strategy may degrade in live trading
    - WFE < 40%: Poor - strategy is likely overfit

    Usage:
        tester = WalkForwardTester(config)

        # Add historical trades
        for trade in historical_trades:
            tester.add_trade(trade)

        # Run walk-forward analysis
        results = tester.run_walk_forward_test()

        # Get robustness report
        report = tester.get_robustness_report()

        if report.overall_status == WFEStatus.ROBUST:
            print("Strategy is robust for live trading")
    """

    def __init__(
        self,
        config: Optional[WFEConfig] = None,
        strategy_name: str = "default"
    ):
        """
        Initialize Walk Forward Tester

        Args:
            config: WFE configuration (uses defaults if None)
            strategy_name: Name of strategy being tested
        """
        # Use default config if none provided
        self.config = config or WFEConfig()
        self.strategy_name = strategy_name

        # Trade storage
        self._trades: List[TradeData] = []

        # Results storage
        self._window_results: List[WalkForwardResult] = []
        self._last_analysis_date: Optional[datetime] = None

        logger.info(
            f"WalkForwardTester initialized for strategy '{strategy_name}': "
            f"IS={self.config.in_sample_pct:.0%}, "
            f"OOS={self.config.out_of_sample_pct:.0%}, "
            f"min_WFE={self.config.min_wfe_threshold:.0%}, "
            f"windows={self.config.rolling_windows}"
        )

    # =========================================================================
    # TRADE DATA MANAGEMENT
    # =========================================================================

    def add_trade(self, trade: TradeData) -> None:
        """
        Add a trade record for analysis

        Args:
            trade: Trade data to add
        """
        self._trades.append(trade)
        # Sort by exit time to ensure chronological order
        self._trades.sort(key=lambda t: t.exit_time)
        logger.debug(f"Added trade {trade.trade_id}, total trades: {len(self._trades)}")

    def add_trades(self, trades: List[TradeData]) -> None:
        """
        Add multiple trade records for analysis

        Args:
            trades: List of trades to add
        """
        for trade in trades:
            self._trades.append(trade)
        # Sort by exit time
        self._trades.sort(key=lambda t: t.exit_time)
        logger.info(f"Added {len(trades)} trades, total trades: {len(self._trades)}")

    def clear_trades(self) -> None:
        """Clear all trade data"""
        self._trades.clear()
        self._window_results.clear()
        self._last_analysis_date = None
        logger.info("Cleared all trade data")

    def get_trade_count(self) -> int:
        """Get current trade count"""
        return len(self._trades)

    # =========================================================================
    # DATA SPLITTING
    # =========================================================================

    def split_data(
        self,
        trades: List[TradeData],
        in_sample_pct: Optional[float] = None
    ) -> Tuple[List[TradeData], List[TradeData]]:
        """
        Split trades into in-sample and out-of-sample periods

        Args:
            trades: List of trades to split (should be sorted by time)
            in_sample_pct: Override config IS percentage

        Returns:
            Tuple of (in_sample_trades, out_of_sample_trades)
        """
        if not trades:
            logger.warning("No trades to split")
            return [], []

        # Use config value if not overridden
        is_pct = in_sample_pct or self.config.in_sample_pct

        # Calculate split index
        split_idx = int(len(trades) * is_pct)

        # Ensure we have at least 1 trade in each period
        split_idx = max(1, min(split_idx, len(trades) - 1))

        in_sample = trades[:split_idx]
        out_of_sample = trades[split_idx:]

        logger.debug(
            f"Split data: IS={len(in_sample)} trades, OOS={len(out_of_sample)} trades "
            f"({is_pct:.0%} / {1-is_pct:.0%})"
        )

        return in_sample, out_of_sample

    def create_rolling_windows(
        self,
        trades: List[TradeData],
        num_windows: Optional[int] = None
    ) -> List[Tuple[List[TradeData], List[TradeData]]]:
        """
        Create rolling walk-forward windows

        Each window advances the IS/OOS split point, providing multiple
        test periods for more robust analysis.

        Args:
            trades: All trades to split into windows
            num_windows: Number of windows (uses config if None)

        Returns:
            List of (in_sample, out_of_sample) tuples
        """
        if not trades:
            logger.warning("No trades for rolling windows")
            return []

        windows = num_windows or self.config.rolling_windows
        total_trades = len(trades)

        # Calculate minimum trades per window
        min_trades_per_window = total_trades // windows

        if min_trades_per_window < 10:
            logger.warning(
                f"Insufficient trades for {windows} windows "
                f"({total_trades} trades, {min_trades_per_window} per window)"
            )
            # Fall back to single window
            windows = 1

        results = []

        for i in range(windows):
            # Calculate window boundaries
            # Each subsequent window uses more data for IS and shifts OOS forward
            window_size = total_trades // windows
            window_end = (i + 1) * window_size if i < windows - 1 else total_trades
            window_start = max(0, window_end - window_size * 2)  # Overlap for continuity

            # Get trades for this window
            window_trades = trades[window_start:window_end]

            # Split into IS/OOS
            is_trades, oos_trades = self.split_data(window_trades)

            if is_trades and oos_trades:
                results.append((is_trades, oos_trades))
                logger.debug(
                    f"Window {i+1}: IS={len(is_trades)}, OOS={len(oos_trades)} "
                    f"[{window_start}:{window_end}]"
                )

        logger.info(f"Created {len(results)} rolling windows from {total_trades} trades")
        return results

    # =========================================================================
    # METRICS CALCULATION
    # =========================================================================

    def calculate_metrics(
        self,
        trades: List[TradeData]
    ) -> PeriodMetrics:
        """
        Calculate comprehensive performance metrics for a trade set

        Args:
            trades: List of trades to analyze

        Returns:
            PeriodMetrics with all calculated metrics
        """
        if not trades:
            # Return zero metrics for empty trade set
            now = datetime.now()
            return PeriodMetrics(
                period_start=now,
                period_end=now,
                trade_count=0,
                total_return=0.0,
                sharpe_ratio=0.0,
                win_rate=0.0,
                profit_factor=0.0,
                avg_trade_pnl=0.0,
                max_drawdown=0.0,
                volatility=0.0,
                expectancy=0.0
            )

        # Time period
        period_start = min(t.entry_time for t in trades)
        period_end = max(t.exit_time for t in trades)
        trade_count = len(trades)

        # Extract P&L data
        pnl_list = [t.pnl for t in trades]
        pnl_pct_list = [t.pnl_pct for t in trades]

        # Total return (compounded)
        cumulative = np.cumprod(1 + np.array(pnl_pct_list) / 100)
        total_return = (cumulative[-1] - 1) * 100 if len(cumulative) > 0 else 0.0

        # Win rate
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]
        win_rate = len(wins) / trade_count if trade_count > 0 else 0.0

        # Profit factor
        gross_profit = sum(t.pnl for t in wins) if wins else 0.0
        gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0.0

        # Average trade P&L
        avg_trade_pnl = np.mean(pnl_list) if pnl_list else 0.0

        # Volatility (annualized)
        if len(pnl_pct_list) > 1:
            daily_vol = np.std(pnl_pct_list, ddof=1)
            # Assume average trades per day for annualization
            days = max(1, (period_end - period_start).days)
            trades_per_day = trade_count / days
            volatility = daily_vol * np.sqrt(trades_per_day * self.config.trading_days_per_year)
        else:
            volatility = 0.0

        # Sharpe ratio
        sharpe_ratio = self._calculate_sharpe(pnl_pct_list)

        # Maximum drawdown
        max_drawdown = self._calculate_max_drawdown(pnl_pct_list)

        # Expectancy
        # E = (Win% * Avg Win) - (Loss% * Avg Loss)
        avg_win = np.mean([t.pnl for t in wins]) if wins else 0.0
        avg_loss = abs(np.mean([t.pnl for t in losses])) if losses else 0.0
        loss_rate = 1 - win_rate
        expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)

        metrics = PeriodMetrics(
            period_start=period_start,
            period_end=period_end,
            trade_count=trade_count,
            total_return=float(total_return),
            sharpe_ratio=float(sharpe_ratio),
            win_rate=float(win_rate),
            profit_factor=float(profit_factor) if not math.isinf(profit_factor) else 999.99,
            avg_trade_pnl=float(avg_trade_pnl),
            max_drawdown=float(max_drawdown),
            volatility=float(volatility),
            expectancy=float(expectancy)
        )

        logger.debug(
            f"Calculated metrics: trades={trade_count}, "
            f"return={total_return:.2f}%, sharpe={sharpe_ratio:.2f}, "
            f"win_rate={win_rate:.1%}, PF={profit_factor:.2f}"
        )

        return metrics

    def _calculate_sharpe(
        self,
        returns: List[float],
        annualize: bool = True
    ) -> float:
        """
        Calculate Sharpe ratio from trade returns

        Args:
            returns: List of return percentages
            annualize: Whether to annualize the ratio

        Returns:
            Sharpe ratio
        """
        if len(returns) < 2:
            return 0.0

        returns_arr = np.array(returns) / 100  # Convert to decimal

        # Excess returns over risk-free rate
        rf_daily = self.config.risk_free_rate / self.config.trading_days_per_year
        excess_returns = returns_arr - rf_daily

        mean_excess = np.mean(excess_returns)
        std_excess = np.std(excess_returns, ddof=1)

        if std_excess == 0:
            return 0.0

        sharpe = mean_excess / std_excess

        if annualize:
            # Annualize based on assumed trades per year
            sharpe *= np.sqrt(self.config.trading_days_per_year)

        return float(sharpe)

    def _calculate_max_drawdown(self, returns: List[float]) -> float:
        """
        Calculate maximum drawdown from trade returns

        Args:
            returns: List of return percentages

        Returns:
            Maximum drawdown as positive percentage
        """
        if len(returns) < 2:
            return 0.0

        # Calculate cumulative returns
        cumulative = np.cumprod(1 + np.array(returns) / 100)

        # Calculate running maximum
        running_max = np.maximum.accumulate(cumulative)

        # Calculate drawdown
        drawdown = (cumulative - running_max) / running_max

        # Return maximum drawdown as positive percentage
        max_dd = abs(np.min(drawdown)) * 100

        return float(max_dd)

    # =========================================================================
    # WFE CALCULATION
    # =========================================================================

    def calculate_wfe(
        self,
        in_sample_metrics: PeriodMetrics,
        out_sample_metrics: PeriodMetrics
    ) -> Dict[str, float]:
        """
        Calculate Walk Forward Efficiency ratios

        WFE = Out-of-Sample Performance / In-Sample Performance

        Higher WFE indicates better translation from optimization to live trading.

        Args:
            in_sample_metrics: Metrics from training period
            out_sample_metrics: Metrics from testing period

        Returns:
            Dictionary with WFE ratios for different metrics
        """
        # Calculate WFE for returns
        if abs(in_sample_metrics.total_return) > 0.001:
            wfe_return = out_sample_metrics.total_return / in_sample_metrics.total_return
        else:
            # IS return near zero - use OOS sign as indicator
            wfe_return = 1.0 if out_sample_metrics.total_return >= 0 else 0.0

        # Calculate WFE for Sharpe ratio
        if abs(in_sample_metrics.sharpe_ratio) > 0.001:
            wfe_sharpe = out_sample_metrics.sharpe_ratio / in_sample_metrics.sharpe_ratio
        else:
            wfe_sharpe = 1.0 if out_sample_metrics.sharpe_ratio >= 0 else 0.0

        # Calculate WFE for profit factor
        if in_sample_metrics.profit_factor > 0.001 and in_sample_metrics.profit_factor < 999:
            wfe_profit_factor = out_sample_metrics.profit_factor / in_sample_metrics.profit_factor
        else:
            wfe_profit_factor = 1.0 if out_sample_metrics.profit_factor >= 1.0 else 0.0

        # Clamp extreme values for interpretability
        wfe_return = max(0.0, min(wfe_return, 2.0))
        wfe_sharpe = max(0.0, min(wfe_sharpe, 2.0))
        wfe_profit_factor = max(0.0, min(wfe_profit_factor, 2.0))

        wfe_results = {
            'wfe_return': wfe_return,
            'wfe_sharpe': wfe_sharpe,
            'wfe_profit_factor': wfe_profit_factor
        }

        logger.debug(
            f"WFE calculated: return={wfe_return:.2%}, "
            f"sharpe={wfe_sharpe:.2%}, PF={wfe_profit_factor:.2%}"
        )

        return wfe_results

    def calculate_statistical_confidence(self, trade_count: int) -> float:
        """
        Calculate statistical confidence level based on trade count

        Uses approximation based on sample size theory:
        - 30 trades: ~80% confidence
        - 100 trades: ~90% confidence
        - 385 trades: ~95% confidence (Chebyshev bound)
        - 1000+ trades: ~99% confidence

        Args:
            trade_count: Number of trades in sample

        Returns:
            Confidence level as percentage (0-100)
        """
        if trade_count <= 0:
            return 0.0

        # Use sigmoid-like function for smooth confidence curve
        # Calibrated so 385 trades = 95% confidence
        # Formula: confidence = 100 * (1 - 1 / sqrt(n * k))
        # where k is calibration constant

        # Calibration: at n=385, we want confidence=95
        # 95 = 100 * (1 - 1/sqrt(385*k))
        # 0.05 = 1/sqrt(385*k)
        # sqrt(385*k) = 20
        # 385*k = 400
        # k = 400/385 = 1.039

        k = 1.039

        if trade_count < 10:
            # Very low sample - linear scaling
            confidence = trade_count * 5.0
        else:
            # Apply formula with calibration
            confidence = 100 * (1 - 1 / math.sqrt(trade_count * k))

        # Clamp to valid range
        confidence = max(0.0, min(confidence, 99.9))

        logger.debug(f"Statistical confidence for {trade_count} trades: {confidence:.1f}%")

        return confidence

    def _assess_robustness(
        self,
        wfe_values: Dict[str, float],
        trade_count: int
    ) -> Tuple[bool, WFEStatus, List[str]]:
        """
        Assess strategy robustness based on WFE values

        Args:
            wfe_values: Dictionary of WFE metrics
            trade_count: Total trade count for confidence

        Returns:
            Tuple of (is_robust, status, notes)
        """
        notes = []
        threshold = self.config.min_wfe_threshold
        marginal_threshold = threshold * (1 - self.config.marginal_threshold_pct)

        # Primary metric is WFE return
        primary_wfe = wfe_values.get('wfe_return', 0.0)
        secondary_wfe = wfe_values.get('wfe_sharpe', 0.0)

        # Check trade count confidence
        if trade_count < self.config.min_trades_for_confidence:
            notes.append(
                f"Insufficient trades ({trade_count}) for 95% confidence "
                f"(need {self.config.min_trades_for_confidence})"
            )

        # Assess based on primary WFE
        if primary_wfe >= threshold:
            is_robust = True
            status = WFEStatus.ROBUST
            notes.append(f"WFE return ({primary_wfe:.1%}) exceeds threshold ({threshold:.0%})")
        elif primary_wfe >= marginal_threshold:
            is_robust = False
            status = WFEStatus.MARGINAL
            notes.append(
                f"WFE return ({primary_wfe:.1%}) is marginal "
                f"(between {marginal_threshold:.0%} and {threshold:.0%})"
            )
        else:
            is_robust = False
            status = WFEStatus.OVERFIT
            notes.append(f"WFE return ({primary_wfe:.1%}) below threshold - likely overfit")

        # Add secondary metric insight
        if secondary_wfe < threshold * 0.8:
            notes.append(f"Warning: WFE Sharpe ({secondary_wfe:.1%}) is also low")
        elif secondary_wfe > threshold * 1.2:
            notes.append(f"Positive: WFE Sharpe ({secondary_wfe:.1%}) is strong")

        # Override status if insufficient data
        if trade_count < 30:
            status = WFEStatus.INSUFFICIENT_DATA
            is_robust = False
            notes.append("Insufficient data for reliable assessment")

        return is_robust, status, notes

    # =========================================================================
    # MAIN WALK FORWARD TEST
    # =========================================================================

    def run_walk_forward_test(
        self,
        trades: Optional[List[TradeData]] = None,
        windows: Optional[int] = None
    ) -> List[WalkForwardResult]:
        """
        Run complete walk-forward efficiency test

        Executes walk-forward analysis across multiple rolling windows,
        calculating WFE for each period.

        Args:
            trades: Trades to analyze (uses stored trades if None)
            windows: Number of windows (uses config if None)

        Returns:
            List of WalkForwardResult for each window
        """
        # Use stored trades if not provided
        test_trades = trades or self._trades

        if not test_trades:
            logger.warning("No trades available for walk-forward test")
            return []

        # Sort trades by exit time
        sorted_trades = sorted(test_trades, key=lambda t: t.exit_time)

        # Create rolling windows
        rolling_windows = self.create_rolling_windows(sorted_trades, windows)

        if not rolling_windows:
            logger.warning("Could not create rolling windows")
            return []

        results = []

        for idx, (is_trades, oos_trades) in enumerate(rolling_windows):
            window_num = idx + 1

            logger.info(
                f"Processing window {window_num}/{len(rolling_windows)}: "
                f"IS={len(is_trades)} trades, OOS={len(oos_trades)} trades"
            )

            # Calculate metrics for each period
            is_metrics = self.calculate_metrics(is_trades)
            oos_metrics = self.calculate_metrics(oos_trades)

            # Calculate WFE ratios
            wfe_values = self.calculate_wfe(is_metrics, oos_metrics)

            # Calculate total trade count and confidence
            total_trades = len(is_trades) + len(oos_trades)
            confidence = self.calculate_statistical_confidence(total_trades)

            # Assess robustness
            is_robust, status, notes = self._assess_robustness(wfe_values, total_trades)

            # Create result object
            result = WalkForwardResult(
                window_number=window_num,
                in_sample_metrics=is_metrics,
                out_of_sample_metrics=oos_metrics,
                wfe_return=wfe_values['wfe_return'],
                wfe_sharpe=wfe_values['wfe_sharpe'],
                wfe_profit_factor=wfe_values['wfe_profit_factor'],
                is_robust=is_robust,
                status=status,
                trade_count=total_trades,
                confidence_level=confidence,
                notes=notes
            )

            results.append(result)

            logger.info(
                f"Window {window_num} result: WFE={wfe_values['wfe_return']:.1%}, "
                f"status={status.value}, robust={is_robust}"
            )

        # Store results
        self._window_results = results
        self._last_analysis_date = datetime.now()

        logger.info(
            f"Walk-forward test complete: {len(results)} windows analyzed, "
            f"{sum(1 for r in results if r.is_robust)}/{len(results)} robust"
        )

        return results

    # =========================================================================
    # ROBUSTNESS REPORT
    # =========================================================================

    def get_robustness_report(
        self,
        results: Optional[List[WalkForwardResult]] = None
    ) -> RobustnessReport:
        """
        Generate comprehensive robustness report

        Aggregates results from all walk-forward windows into a single
        report with overall assessment and recommendations.

        Args:
            results: Results to report (uses stored results if None)

        Returns:
            RobustnessReport with complete analysis
        """
        # Use stored results if not provided
        window_results = results or self._window_results

        if not window_results:
            logger.warning("No results available for robustness report")
            # Return empty report
            return RobustnessReport(
                strategy_name=self.strategy_name,
                analysis_date=datetime.now(),
                total_trades=0,
                total_windows=0,
                avg_wfe_return=0.0,
                avg_wfe_sharpe=0.0,
                avg_wfe_profit_factor=0.0,
                overall_status=WFEStatus.INSUFFICIENT_DATA,
                robust_windows=0,
                robust_percentage=0.0,
                overall_confidence=0.0,
                wfe_consistency=0.0,
                window_results=[],
                recommendations=["Collect more trade data before analysis"]
            )

        # Calculate aggregate metrics
        total_trades = sum(r.trade_count for r in window_results)
        total_windows = len(window_results)
        robust_windows = sum(1 for r in window_results if r.is_robust)
        robust_percentage = robust_windows / total_windows * 100 if total_windows > 0 else 0.0

        # Average WFE metrics
        wfe_returns = [r.wfe_return for r in window_results]
        wfe_sharpes = [r.wfe_sharpe for r in window_results]
        wfe_pfs = [r.wfe_profit_factor for r in window_results]

        avg_wfe_return = np.mean(wfe_returns) if wfe_returns else 0.0
        avg_wfe_sharpe = np.mean(wfe_sharpes) if wfe_sharpes else 0.0
        avg_wfe_pf = np.mean(wfe_pfs) if wfe_pfs else 0.0

        # WFE consistency (standard deviation - lower is better)
        wfe_consistency = np.std(wfe_returns, ddof=1) if len(wfe_returns) > 1 else 0.0

        # Overall confidence
        overall_confidence = self.calculate_statistical_confidence(total_trades)

        # Determine overall status
        overall_status = self._determine_overall_status(
            avg_wfe_return, robust_percentage, overall_confidence
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            avg_wfe_return, robust_percentage, overall_confidence, wfe_consistency, total_trades
        )

        report = RobustnessReport(
            strategy_name=self.strategy_name,
            analysis_date=self._last_analysis_date or datetime.now(),
            total_trades=total_trades,
            total_windows=total_windows,
            avg_wfe_return=float(avg_wfe_return),
            avg_wfe_sharpe=float(avg_wfe_sharpe),
            avg_wfe_profit_factor=float(avg_wfe_pf),
            overall_status=overall_status,
            robust_windows=robust_windows,
            robust_percentage=float(robust_percentage),
            overall_confidence=float(overall_confidence),
            wfe_consistency=float(wfe_consistency),
            window_results=window_results,
            recommendations=recommendations
        )

        logger.info(
            f"Robustness report generated for '{self.strategy_name}': "
            f"status={overall_status.value}, "
            f"avg_WFE={avg_wfe_return:.1%}, "
            f"robust={robust_windows}/{total_windows} windows"
        )

        return report

    def _determine_overall_status(
        self,
        avg_wfe: float,
        robust_pct: float,
        confidence: float
    ) -> WFEStatus:
        """
        Determine overall strategy status based on aggregate metrics

        Args:
            avg_wfe: Average WFE across windows
            robust_pct: Percentage of robust windows
            confidence: Statistical confidence level

        Returns:
            Overall WFEStatus
        """
        threshold = self.config.min_wfe_threshold

        # Insufficient confidence
        if confidence < 80:
            return WFEStatus.INSUFFICIENT_DATA

        # Strong robustness: high WFE and most windows robust
        if avg_wfe >= threshold and robust_pct >= 60:
            return WFEStatus.ROBUST

        # Marginal: average WFE near threshold or mixed window results
        if avg_wfe >= threshold * 0.8 or robust_pct >= 40:
            return WFEStatus.MARGINAL

        # Overfit: low WFE and few robust windows
        return WFEStatus.OVERFIT

    def _generate_recommendations(
        self,
        avg_wfe: float,
        robust_pct: float,
        confidence: float,
        consistency: float,
        trade_count: int
    ) -> List[str]:
        """
        Generate actionable recommendations based on analysis

        Args:
            avg_wfe: Average WFE return
            robust_pct: Percentage of robust windows
            confidence: Statistical confidence
            consistency: WFE consistency (std dev)
            trade_count: Total trade count

        Returns:
            List of recommendation strings
        """
        recommendations = []
        threshold = self.config.min_wfe_threshold
        min_trades = self.config.min_trades_for_confidence

        # Confidence recommendations
        if trade_count < min_trades:
            remaining = min_trades - trade_count
            recommendations.append(
                f"Collect {remaining} more trades to reach 95% statistical confidence"
            )

        # WFE recommendations
        if avg_wfe >= threshold * 1.2:
            recommendations.append(
                f"Strategy shows excellent robustness (WFE={avg_wfe:.1%}). "
                "Consider increasing position sizes gradually."
            )
        elif avg_wfe >= threshold:
            recommendations.append(
                f"Strategy is robust (WFE={avg_wfe:.1%}). "
                "Monitor for degradation in changing market conditions."
            )
        elif avg_wfe >= threshold * 0.8:
            recommendations.append(
                f"Strategy is marginal (WFE={avg_wfe:.1%}). "
                "Consider reducing parameter optimization or using simpler rules."
            )
        else:
            recommendations.append(
                f"Strategy shows signs of overfitting (WFE={avg_wfe:.1%}). "
                "Simplify strategy rules, reduce indicators, or use out-of-sample validation."
            )

        # Consistency recommendations
        if consistency > 0.3:
            recommendations.append(
                f"High WFE variance ({consistency:.2f}) suggests inconsistent performance. "
                "Strategy may be sensitive to market regimes."
            )
        elif consistency < 0.1:
            recommendations.append(
                f"Low WFE variance ({consistency:.2f}) indicates consistent behavior across windows."
            )

        # Robust windows recommendations
        if robust_pct < 50:
            recommendations.append(
                f"Only {robust_pct:.0f}% of windows are robust. "
                "Strategy may not generalize well to different time periods."
            )
        elif robust_pct == 100:
            recommendations.append(
                "All windows show robust performance. Strategy is well-generalized."
            )

        return recommendations

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of current test state and results

        Returns:
            Dictionary with summary statistics
        """
        if not self._window_results:
            return {
                "strategy": self.strategy_name,
                "status": "no_analysis",
                "trade_count": len(self._trades),
                "config": {
                    "in_sample_pct": self.config.in_sample_pct,
                    "out_of_sample_pct": self.config.out_of_sample_pct,
                    "min_wfe_threshold": self.config.min_wfe_threshold,
                    "rolling_windows": self.config.rolling_windows
                }
            }

        # Generate report
        report = self.get_robustness_report()

        return {
            "strategy": self.strategy_name,
            "status": report.overall_status.value,
            "analysis_date": report.analysis_date.isoformat(),
            "trade_count": report.total_trades,
            "windows_analyzed": report.total_windows,
            "robust_windows": report.robust_windows,
            "robust_percentage": round(report.robust_percentage, 1),
            "wfe_metrics": {
                "avg_return": round(report.avg_wfe_return * 100, 1),
                "avg_sharpe": round(report.avg_wfe_sharpe * 100, 1),
                "avg_profit_factor": round(report.avg_wfe_profit_factor * 100, 1),
                "consistency": round(report.wfe_consistency, 3)
            },
            "confidence_level": round(report.overall_confidence, 1),
            "recommendations_count": len(report.recommendations)
        }

    def get_status(self) -> Dict[str, Any]:
        """
        Get current tester status

        Returns:
            Dictionary with status information
        """
        return {
            "strategy_name": self.strategy_name,
            "trades_loaded": len(self._trades),
            "results_available": len(self._window_results) > 0,
            "windows_analyzed": len(self._window_results),
            "last_analysis": self._last_analysis_date.isoformat() if self._last_analysis_date else None,
            "config": {
                "in_sample_pct": self.config.in_sample_pct,
                "out_of_sample_pct": self.config.out_of_sample_pct,
                "min_trades_for_confidence": self.config.min_trades_for_confidence,
                "min_wfe_threshold": self.config.min_wfe_threshold,
                "rolling_windows": self.config.rolling_windows
            }
        }


# =============================================================================
# GLOBAL INSTANCE MANAGEMENT
# =============================================================================

# Global instance for convenience
_walk_forward_tester: Optional[WalkForwardTester] = None


def get_walk_forward_tester(
    config: Optional[WFEConfig] = None,
    strategy_name: str = "default"
) -> WalkForwardTester:
    """
    Get or create global WalkForwardTester instance

    Args:
        config: Optional configuration
        strategy_name: Strategy name

    Returns:
        WalkForwardTester instance
    """
    global _walk_forward_tester
    if _walk_forward_tester is None:
        _walk_forward_tester = WalkForwardTester(config, strategy_name)
    return _walk_forward_tester


def reset_walk_forward_tester() -> None:
    """Reset global WalkForwardTester instance"""
    global _walk_forward_tester
    _walk_forward_tester = None
    logger.info("Global WalkForwardTester instance reset")
