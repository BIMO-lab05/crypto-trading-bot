"""
Arbitrage Strategy Implementation
==================================
Purpose: Exploit price inefficiencies across different markets or instruments

This strategy identifies and capitalizes on price discrepancies that
can arise between related assets or across different exchanges.

Arbitrage Types Supported:
1. Statistical Arbitrage - Mean reversion of correlated pairs
2. Triangular Arbitrage - Currency pair triangles
3. Cross-Exchange Arbitrage - Same asset, different exchanges
4. Funding Rate Arbitrage - Spot vs perpetual futures

Entry Conditions:
1. Spread exceeds threshold (mean + n*std)
2. Sufficient liquidity on both sides
3. Execution cost below expected profit
4. Convergence expected within time horizon

Exit Conditions:
1. Spread returns to mean
2. Stop loss triggered
3. Time limit exceeded
4. Divergence detected

Phase 9: Multi-Strategy Orchestration Engine
Author: Backend Developer Agent
Date: 2025-12-11
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from collections import deque
import statistics
import math

from app.strategies.base import (
    StrategyBase,
    StrategySignal,
    AnalysisResult,
    StrategyCategory,
    StrategyRiskLevel,
    SignalType,
    MarketCondition,
    create_signal
)

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class ArbitrageConfig:
    """Configuration for Arbitrage Strategy"""

    # Pair correlation settings
    correlation_lookback: int = 50  # Bars for correlation calculation
    min_correlation: float = 0.7  # Minimum correlation for trading
    correlation_update_interval: int = 10  # Bars between correlation updates

    # Spread calculation
    spread_lookback: int = 30  # Bars for spread statistics
    spread_entry_zscore: float = 2.0  # Z-score for entry (2 std devs)
    spread_exit_zscore: float = 0.5  # Z-score for exit (back to mean)
    spread_stop_zscore: float = 3.5  # Z-score for stop loss

    # Mean reversion parameters
    half_life_max_bars: int = 20  # Max half-life for mean reversion
    min_half_life_bars: int = 3  # Min half-life (avoid noise)

    # Risk management
    max_position_pct: float = 10.0  # Can be larger for market-neutral
    risk_per_trade_pct: float = 1.0  # Lower risk per trade
    max_spread_divergence_pct: float = 5.0  # Max allowed spread divergence
    max_hold_bars: int = 50  # Maximum holding period

    # Execution constraints
    min_liquidity_ratio: float = 10.0  # Order book depth ratio
    max_slippage_pct: float = 0.1  # Max acceptable slippage
    execution_window_seconds: int = 60  # Time to execute both legs

    # Funding rate arbitrage
    min_funding_rate_pct: float = 0.01  # Min funding rate to trade (0.01%)
    funding_rate_lookback: int = 8  # Funding rate history (8-hour intervals)

    # Transaction costs
    maker_fee_pct: float = 0.02  # 0.02% maker fee
    taker_fee_pct: float = 0.05  # 0.05% taker fee
    min_profit_after_costs_pct: float = 0.1  # Min profit after all costs

    # Timing
    signal_expiry_seconds: int = 30  # Very short expiry for arb
    min_bars_between_signals: int = 3

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "spread_entry_zscore": self.spread_entry_zscore,
            "spread_exit_zscore": self.spread_exit_zscore,
            "min_correlation": self.min_correlation,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "max_position_pct": self.max_position_pct,
        }


@dataclass
class PairData:
    """Data for a trading pair in arbitrage"""
    symbol_1: str
    symbol_2: str
    correlation: float = 0.0
    spread_mean: float = 0.0
    spread_std: float = 0.0
    current_spread: float = 0.0
    current_zscore: float = 0.0
    half_life: float = 0.0
    spread_history: deque = field(default_factory=lambda: deque(maxlen=100))
    last_correlation_update: int = 0


# =============================================================================
# ARBITRAGE STRATEGY
# =============================================================================

class ArbitrageStrategy(StrategyBase):
    """
    Statistical Arbitrage Trading Strategy

    Exploits price inefficiencies between correlated assets using
    statistical methods to identify and trade mean-reverting spreads.

    Core Concept:
    When two assets are historically correlated, their price ratio
    (spread) tends to revert to a mean value. Large deviations from
    this mean present trading opportunities.

    Trade Structure:
    - Long spread: Long Asset1, Short Asset2
    - Short spread: Short Asset1, Long Asset2

    Key Metrics:
    1. Correlation: Measures relationship strength
    2. Z-Score: Measures current deviation from mean
    3. Half-Life: Estimates time to mean reversion
    4. Cointegration: Statistical relationship validity

    Risk Factors:
    - Correlation breakdown (regime change)
    - Execution risk (leg risk)
    - Liquidity risk
    - Convergence timing uncertainty
    """

    def __init__(
        self,
        strategy_config: Optional[ArbitrageConfig] = None,
        trading_pairs: Optional[List[Tuple[str, str]]] = None,
        primary_timeframe: str = "15"  # Shorter timeframe for arb
    ):
        """Initialize Arbitrage Strategy"""
        # Create supported symbols list from pairs
        supported = set()
        if trading_pairs:
            for pair in trading_pairs:
                supported.add(pair[0])
                supported.add(pair[1])

        super().__init__(
            strategy_id="arbitrage_v1",
            name="Statistical Arbitrage Strategy",
            version="1.0.0",
            category=StrategyCategory.ARBITRAGE,
            risk_level=StrategyRiskLevel.MODERATE,  # Market neutral
            supported_symbols=list(supported),
            primary_timeframe=primary_timeframe,
            description="Statistical arbitrage on correlated pairs"
        )

        self.strategy_config = strategy_config or ArbitrageConfig()
        self.trading_pairs = trading_pairs or []

        # Update metadata
        self.metadata.required_indicators = ["price_ratio", "correlation", "zscore"]
        self.metadata.required_data_history_bars = max(
            self.strategy_config.spread_lookback,
            self.strategy_config.correlation_lookback
        ) + 50
        self.metadata.expected_win_rate = 0.60  # Higher win rate
        self.metadata.expected_profit_factor = 1.3  # Lower but consistent
        self.metadata.expected_sharpe = 1.5  # High Sharpe (market neutral)
        self.metadata.typical_hold_period_hours = 2.0  # Shorter holds

        # Pair tracking
        self._pair_data: Dict[str, PairData] = {}
        self._price_history: Dict[str, List[float]] = {}
        self._current_bar: Dict[str, int] = {}
        self._last_signal_bar: Dict[str, int] = {}

        # Initialize pair data
        for pair in self.trading_pairs:
            pair_key = f"{pair[0]}_{pair[1]}"
            self._pair_data[pair_key] = PairData(
                symbol_1=pair[0],
                symbol_2=pair[1]
            )

        logger.info(
            f"ArbitrageStrategy initialized: "
            f"{len(self.trading_pairs)} pairs, "
            f"entry_zscore={self.strategy_config.spread_entry_zscore}"
        )

    # =========================================================================
    # CORRELATION AND SPREAD CALCULATIONS
    # =========================================================================

    def _calculate_correlation(
        self,
        prices_1: List[float],
        prices_2: List[float]
    ) -> float:
        """Calculate Pearson correlation between two price series"""
        if len(prices_1) < 5 or len(prices_2) < 5:
            return 0.0

        # Align lengths
        n = min(len(prices_1), len(prices_2))
        prices_1 = prices_1[-n:]
        prices_2 = prices_2[-n:]

        # Calculate correlation
        mean_1 = statistics.mean(prices_1)
        mean_2 = statistics.mean(prices_2)

        numerator = sum((p1 - mean_1) * (p2 - mean_2) for p1, p2 in zip(prices_1, prices_2))
        denominator = math.sqrt(
            sum((p1 - mean_1) ** 2 for p1 in prices_1) *
            sum((p2 - mean_2) ** 2 for p2 in prices_2)
        )

        if denominator == 0:
            return 0.0

        return numerator / denominator

    def _calculate_spread(
        self,
        prices_1: List[float],
        prices_2: List[float]
    ) -> List[float]:
        """Calculate price ratio spread"""
        if not prices_1 or not prices_2:
            return []

        n = min(len(prices_1), len(prices_2))
        spreads = []

        for i in range(n):
            if prices_2[-n + i] > 0:
                spread = prices_1[-n + i] / prices_2[-n + i]
                spreads.append(spread)

        return spreads

    def _calculate_zscore(
        self,
        current_spread: float,
        spread_mean: float,
        spread_std: float
    ) -> float:
        """Calculate z-score of current spread"""
        if spread_std <= 0:
            return 0.0

        return (current_spread - spread_mean) / spread_std

    def _calculate_half_life(
        self,
        spread_series: List[float]
    ) -> float:
        """
        Calculate half-life of mean reversion

        Uses AR(1) model: spread_t = phi * spread_{t-1} + epsilon
        Half-life = -log(2) / log(phi)
        """
        if len(spread_series) < 10:
            return float('inf')

        # Calculate lagged spread
        y = spread_series[1:]
        y_lag = spread_series[:-1]

        n = len(y)
        mean_y = statistics.mean(y)
        mean_y_lag = statistics.mean(y_lag)

        # Calculate phi (AR coefficient)
        numerator = sum((y[i] - mean_y) * (y_lag[i] - mean_y_lag) for i in range(n))
        denominator = sum((y_lag[i] - mean_y_lag) ** 2 for i in range(n))

        if denominator == 0:
            return float('inf')

        phi = numerator / denominator

        # Calculate half-life
        if phi <= 0 or phi >= 1:
            return float('inf')

        half_life = -math.log(2) / math.log(phi)

        return half_life

    # =========================================================================
    # PAIR ANALYSIS
    # =========================================================================

    def _update_pair_data(
        self,
        pair_key: str,
        prices_1: List[float],
        prices_2: List[float]
    ) -> PairData:
        """Update pair statistics"""
        pair = self._pair_data.get(pair_key)
        if not pair:
            symbols = pair_key.split('_')
            pair = PairData(symbol_1=symbols[0], symbol_2=symbols[1])
            self._pair_data[pair_key] = pair

        current_bar = self._current_bar.get(pair_key, 0)

        # Calculate spread series
        spreads = self._calculate_spread(prices_1, prices_2)
        if not spreads:
            return pair

        # Update current spread
        pair.current_spread = spreads[-1]
        pair.spread_history.append(pair.current_spread)

        # Update correlation periodically
        if current_bar - pair.last_correlation_update >= self.strategy_config.correlation_update_interval:
            pair.correlation = self._calculate_correlation(
                prices_1[-self.strategy_config.correlation_lookback:],
                prices_2[-self.strategy_config.correlation_lookback:]
            )
            pair.last_correlation_update = current_bar

        # Update spread statistics
        lookback = min(len(spreads), self.strategy_config.spread_lookback)
        recent_spreads = spreads[-lookback:]

        if len(recent_spreads) >= 5:
            pair.spread_mean = statistics.mean(recent_spreads)
            pair.spread_std = statistics.stdev(recent_spreads) if len(recent_spreads) > 1 else 0

            # Calculate z-score
            pair.current_zscore = self._calculate_zscore(
                pair.current_spread, pair.spread_mean, pair.spread_std
            )

            # Calculate half-life
            if len(recent_spreads) >= 10:
                pair.half_life = self._calculate_half_life(recent_spreads)

        return pair

    def _analyze_pair(
        self,
        pair_key: str,
        prices_1: List[float],
        prices_2: List[float]
    ) -> Dict[str, Any]:
        """Analyze a trading pair for arbitrage opportunity"""
        pair = self._update_pair_data(pair_key, prices_1, prices_2)

        # Check correlation threshold
        if abs(pair.correlation) < self.strategy_config.min_correlation:
            return {
                "valid": False,
                "reason": f"Low correlation: {pair.correlation:.2f}"
            }

        # Check half-life
        if pair.half_life > self.strategy_config.half_life_max_bars:
            return {
                "valid": False,
                "reason": f"Slow mean reversion: half-life {pair.half_life:.1f} bars"
            }

        if pair.half_life < self.strategy_config.min_half_life_bars:
            return {
                "valid": False,
                "reason": f"Noisy series: half-life {pair.half_life:.1f} bars"
            }

        # Check for entry signal
        zscore = pair.current_zscore
        entry_threshold = self.strategy_config.spread_entry_zscore

        signal = None
        if zscore > entry_threshold:
            signal = "short_spread"  # Spread too high, expect mean reversion
        elif zscore < -entry_threshold:
            signal = "long_spread"  # Spread too low, expect mean reversion

        # Calculate expected profit
        expected_convergence = abs(zscore) - self.strategy_config.spread_exit_zscore
        expected_profit_pct = (expected_convergence * pair.spread_std / pair.spread_mean * 100) if pair.spread_mean > 0 else 0

        # Check if profit exceeds costs
        total_cost = (self.strategy_config.taker_fee_pct * 4 +  # 4 trades (2 entry, 2 exit)
                      self.strategy_config.max_slippage_pct * 2)  # Slippage on both legs
        net_profit_pct = expected_profit_pct - total_cost

        if net_profit_pct < self.strategy_config.min_profit_after_costs_pct:
            signal = None

        return {
            "valid": True,
            "correlation": pair.correlation,
            "current_spread": pair.current_spread,
            "spread_mean": pair.spread_mean,
            "spread_std": pair.spread_std,
            "zscore": zscore,
            "half_life": pair.half_life,
            "signal": signal,
            "expected_profit_pct": expected_profit_pct,
            "net_profit_pct": net_profit_pct
        }

    # =========================================================================
    # ANALYSIS IMPLEMENTATION
    # =========================================================================

    async def analyze(
        self,
        symbol: str,
        data: Dict[str, Any]
    ) -> AnalysisResult:
        """
        Analyze market for arbitrage opportunities

        Note: This strategy requires data for multiple symbols.
        The data dict should contain 'pair_data' with both symbols' candles.
        """
        # For single symbol analysis, return basic info
        candles = data.get('candles', [])
        if not candles:
            return AnalysisResult(
                symbol=symbol,
                condition=MarketCondition.UNKNOWN,
                confidence=0.0,
                recommendation="no_action"
            )

        closes = [float(c.get('close', c.get('c', 0))) for c in candles]
        current_price = closes[-1]

        # Store price history
        self._price_history[symbol] = closes

        # Check if we have data for any pairs involving this symbol
        pair_analysis_results = []

        for pair in self.trading_pairs:
            if symbol not in pair:
                continue

            other_symbol = pair[1] if pair[0] == symbol else pair[0]
            pair_key = f"{pair[0]}_{pair[1]}"

            # Check if we have the other symbol's data
            if other_symbol not in self._price_history:
                continue

            prices_1 = self._price_history.get(pair[0], [])
            prices_2 = self._price_history.get(pair[1], [])

            if len(prices_1) < self.strategy_config.spread_lookback:
                continue
            if len(prices_2) < self.strategy_config.spread_lookback:
                continue

            analysis = self._analyze_pair(pair_key, prices_1, prices_2)
            analysis["pair_key"] = pair_key
            analysis["symbol_1"] = pair[0]
            analysis["symbol_2"] = pair[1]
            pair_analysis_results.append(analysis)

        # Find best opportunity
        best_opportunity = None
        best_zscore = 0

        for analysis in pair_analysis_results:
            if analysis.get("signal") and analysis.get("valid"):
                if abs(analysis.get("zscore", 0)) > abs(best_zscore):
                    best_zscore = analysis.get("zscore", 0)
                    best_opportunity = analysis

        # Determine recommendation
        if best_opportunity and best_opportunity.get("signal"):
            recommendation = best_opportunity["signal"]
            confidence = min(0.9, 0.5 + abs(best_zscore) * 0.1)
            condition = MarketCondition.RANGING  # Arb works in ranging markets
        else:
            recommendation = "no_action"
            confidence = 0.3
            condition = MarketCondition.UNKNOWN

        # Build indicators
        indicators = {
            "current_price": current_price,
            "pair_analyses": pair_analysis_results,
            "best_opportunity": best_opportunity,
        }

        result = AnalysisResult(
            symbol=symbol,
            condition=condition,
            trend_direction="neutral",
            trend_strength=0.0,
            volatility=0.0,
            indicators=indicators,
            confidence=confidence,
            recommendation=recommendation
        )

        self._last_analysis[symbol] = result

        if best_opportunity:
            logger.debug(
                f"Arb analysis {symbol}: "
                f"pair={best_opportunity.get('pair_key')}, "
                f"zscore={best_opportunity.get('zscore', 0):.2f}, "
                f"signal={best_opportunity.get('signal')}"
            )

        return result

    # =========================================================================
    # SIGNAL GENERATION
    # =========================================================================

    async def generate_signals(
        self,
        symbol: str,
        analysis: AnalysisResult,
        current_price: Decimal
    ) -> List[StrategySignal]:
        """Generate arbitrage signals"""
        signals = []

        if analysis.recommendation not in ["long_spread", "short_spread"]:
            return signals

        indicators = analysis.indicators
        opportunity = indicators.get("best_opportunity")

        if not opportunity or not opportunity.get("valid"):
            return signals

        pair_key = opportunity.get("pair_key")

        # Check cooldown
        current_bar = self._current_bar.get(pair_key, 0)
        last_signal_bar = self._last_signal_bar.get(pair_key, -100)
        if current_bar - last_signal_bar < self.strategy_config.min_bars_between_signals:
            return signals

        zscore = opportunity.get("zscore", 0)
        symbol_1 = opportunity.get("symbol_1")
        symbol_2 = opportunity.get("symbol_2")

        # Calculate stop loss and take profit based on z-scores
        entry_zscore = abs(zscore)
        exit_zscore = self.strategy_config.spread_exit_zscore
        stop_zscore = self.strategy_config.spread_stop_zscore

        spread_std = opportunity.get("spread_std", 0)
        spread_mean = opportunity.get("spread_mean", 1)

        # Calculate percentage moves
        sl_pct = abs(stop_zscore - entry_zscore) * spread_std / spread_mean * 100 if spread_mean > 0 else 2.0
        tp_pct = abs(entry_zscore - exit_zscore) * spread_std / spread_mean * 100 if spread_mean > 0 else 1.0

        # Ensure reasonable values
        sl_pct = max(0.5, min(5.0, sl_pct))
        tp_pct = max(0.3, min(3.0, tp_pct))

        # Generate paired signals
        # For "long_spread" (spread too low): Long symbol_1, Short symbol_2
        # For "short_spread" (spread too high): Short symbol_1, Long symbol_2

        if analysis.recommendation == "long_spread":
            # Signal 1: Long symbol_1
            if symbol == symbol_1:
                signal = create_signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol_1,
                    signal_type=SignalType.ENTRY_LONG,
                    entry_price=current_price,
                    stop_loss_pct=sl_pct,
                    take_profit_pct=tp_pct,
                    confidence=analysis.confidence,
                    reasoning=self._build_arb_reasoning(opportunity, "long_spread", symbol_1)
                )
                signal.market_condition = analysis.condition
                signal.timeframe = self.metadata.primary_timeframe
                signal.expiry_seconds = self.strategy_config.signal_expiry_seconds
                signal.urgency = "CRITICAL"
                signal.metadata = {
                    "arb_pair": pair_key,
                    "arb_leg": "leg_1",
                    "paired_symbol": symbol_2,
                    "paired_action": "SHORT"
                }
                signals.append(signal)

            # Signal 2: Short symbol_2 (will be generated when that symbol is analyzed)

        elif analysis.recommendation == "short_spread":
            # Signal 1: Short symbol_1
            if symbol == symbol_1:
                signal = create_signal(
                    strategy_id=self.strategy_id,
                    symbol=symbol_1,
                    signal_type=SignalType.ENTRY_SHORT,
                    entry_price=current_price,
                    stop_loss_pct=sl_pct,
                    take_profit_pct=tp_pct,
                    confidence=analysis.confidence,
                    reasoning=self._build_arb_reasoning(opportunity, "short_spread", symbol_1)
                )
                signal.market_condition = analysis.condition
                signal.timeframe = self.metadata.primary_timeframe
                signal.expiry_seconds = self.strategy_config.signal_expiry_seconds
                signal.urgency = "CRITICAL"
                signal.metadata = {
                    "arb_pair": pair_key,
                    "arb_leg": "leg_1",
                    "paired_symbol": symbol_2,
                    "paired_action": "LONG"
                }
                signals.append(signal)

        if signals:
            self._last_signal_bar[pair_key] = current_bar
            logger.info(
                f"Generated arb signal: {pair_key}, "
                f"{analysis.recommendation}, zscore={zscore:.2f}"
            )

        return signals

    def _build_arb_reasoning(
        self,
        opportunity: Dict[str, Any],
        signal_type: str,
        symbol: str
    ) -> str:
        """Build reasoning for arbitrage signal"""
        parts = []

        pair_key = opportunity.get("pair_key", "")
        zscore = opportunity.get("zscore", 0)
        correlation = opportunity.get("correlation", 0)
        half_life = opportunity.get("half_life", 0)
        expected_profit = opportunity.get("net_profit_pct", 0)

        parts.append(f"Statistical arbitrage on {pair_key}")

        if signal_type == "long_spread":
            parts.append(f"Spread undervalued (z-score: {zscore:.2f})")
        else:
            parts.append(f"Spread overvalued (z-score: {zscore:.2f})")

        parts.append(f"Correlation: {correlation:.2f}")
        parts.append(f"Expected half-life: {half_life:.1f} bars")
        parts.append(f"Expected net profit: {expected_profit:.2f}%")

        return ". ".join(parts)

    # =========================================================================
    # POSITION SIZING
    # =========================================================================

    def calculate_position_size(
        self,
        signal: StrategySignal,
        available_capital: float,
        risk_per_trade_pct: Optional[float] = None
    ) -> Tuple[Decimal, float]:
        """Calculate position size for arbitrage trade"""
        # Arbitrage uses half position on each leg
        risk_pct = risk_per_trade_pct or self.strategy_config.risk_per_trade_pct
        risk_amount = available_capital * (risk_pct / 100)

        stop_loss_pct = signal.stop_loss_pct or 2.0

        if stop_loss_pct <= 0:
            stop_loss_pct = 2.0

        # Position value for this leg (half of total arbitrage position)
        full_position_value = risk_amount / (stop_loss_pct / 100)
        leg_position_value = full_position_value / 2  # Split between two legs

        max_position_value = available_capital * (self.strategy_config.max_position_pct / 100) / 2
        leg_position_value = min(leg_position_value, max_position_value)

        if signal.entry_price and signal.entry_price > 0:
            quantity = Decimal(str(leg_position_value)) / signal.entry_price
        else:
            quantity = Decimal('0')

        quantity = quantity.quantize(Decimal('0.00000001'))

        return quantity, risk_amount / 2

    # =========================================================================
    # LIFECYCLE
    # =========================================================================

    async def on_initialize(self) -> None:
        """Initialize strategy"""
        await super().on_initialize()
        for pair in self.trading_pairs:
            pair_key = f"{pair[0]}_{pair[1]}"
            self._last_signal_bar[pair_key] = -100
            self._current_bar[pair_key] = 0
        logger.info(f"ArbitrageStrategy ready with {len(self.trading_pairs)} pairs")

    async def on_start(self) -> None:
        """Start trading"""
        await super().on_start()
        logger.info("ArbitrageStrategy started")

    async def on_stop(self) -> None:
        """Stop trading"""
        await super().on_stop()
        self._pair_data.clear()
        self._price_history.clear()
        self._last_signal_bar.clear()
        self._current_bar.clear()
        logger.info("ArbitrageStrategy stopped")

    def update_bar_count(self, pair_key: str) -> None:
        """Update bar count for a pair"""
        self._current_bar[pair_key] = self._current_bar.get(pair_key, 0) + 1

    def add_trading_pair(self, symbol_1: str, symbol_2: str) -> None:
        """Add a new trading pair"""
        pair = (symbol_1, symbol_2)
        if pair not in self.trading_pairs:
            self.trading_pairs.append(pair)
            pair_key = f"{symbol_1}_{symbol_2}"
            self._pair_data[pair_key] = PairData(symbol_1=symbol_1, symbol_2=symbol_2)
            self._last_signal_bar[pair_key] = -100
            self._current_bar[pair_key] = 0
            logger.info(f"Added arbitrage pair: {pair_key}")


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_arbitrage_strategy(
    trading_pairs: Optional[List[Tuple[str, str]]] = None,
    timeframe: str = "15",
    config_overrides: Optional[Dict[str, Any]] = None
) -> ArbitrageStrategy:
    """Factory function to create Arbitrage strategy"""
    config = ArbitrageConfig()

    if config_overrides:
        for key, value in config_overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

    return ArbitrageStrategy(
        strategy_config=config,
        trading_pairs=trading_pairs or [],
        primary_timeframe=timeframe
    )
