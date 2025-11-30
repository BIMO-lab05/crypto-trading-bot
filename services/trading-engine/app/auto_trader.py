"""
Auto Trader - Automated Trading Loop
Purpose: Background task that monitors signals and executes trades automatically

Updated 2025-11-28:
- Added market regime detection logging
- Integrated ResearchOptimizedStrategy for research-backed trading decisions
- ATR-based stops, Kelly position sizing, multi-indicator alignment

UPDATED 2025-11-29: Research-backed position management
- Added position monitoring for trailing stops and partial exits
- Integrated new position manager with ATR-based multi-level TPs
- Category-enforced consensus for signal quality

UPDATED 2025-11-30: Research-backed trading enhancements
- Circuit Breaker pattern for API resilience (FIA Best Practices)
- Enhanced Kill Switch with multi-threshold protection
- Slippage Manager for execution quality control
- Execution Timer for controlled position monitoring intervals
- Order State Machine for FIX protocol style order lifecycle

UPDATED 2025-11-30 v2: Advanced trading enhancements
- Advanced Position Sizing (Kelly Criterion, Optimal F, ATR-based, Risk Parity)
- Smart Order Execution (TWAP, VWAP, Iceberg, POV algorithms)
- Performance Analytics Engine (Sharpe, Sortino, VaR, CVaR metrics)
"""

import asyncio
import logging
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.config import get_settings
from app.signal_aggregator import get_aggregator
from app.paper_trading import get_paper_engine
from app.live_trading import get_live_engine
from app.risk_manager import get_risk_manager
from app.position_manager import get_position_manager
from app.position_sizing import get_position_sizer, SizingMethod
from app.performance_tracker import get_performance_tracker
from app.models import OrderSide, OrderType, OrderCreate, OrderStatus
from app.aggregation.market_regime import (
    get_market_regime_detector,
    MarketRegime
)
from app.strategies import ResearchOptimizedStrategy, TradeSetup

# Research-backed trading enhancements (2025-11-30)
from app.trading_enhancements.circuit_breaker import (
    get_circuit_breaker,
    CircuitBreakerOpenError,
    CircuitBreakerConfig
)
from app.trading_enhancements.kill_switch import (
    get_kill_switch,
    KillSwitchConfig,
    KillSwitchReason
)
from app.trading_enhancements.slippage_manager import (
    get_slippage_manager,
    SlippageConfig,
    MarketCondition
)
from app.trading_enhancements.execution_timer import (
    get_execution_timer,
    TimingConfig,
    TimingMode
)
from app.trading_enhancements.order_state_machine import (
    get_order_state_machine,
    OrderState,
    OrderEvent
)

# Advanced Trading Enhancements (2025-11-30 v2)
from app.trading_enhancements.advanced_position_sizing import (
    AdvancedPositionSizer,
    AdvancedSizingMethod,
    AdvancedSizingConfig
)
from app.trading_enhancements.smart_order_execution import (
    SmartOrderExecutor,
    ExecutionAlgorithm,
    ExecutionPlan
)
from app.trading_enhancements.performance_analytics import (
    PerformanceAnalytics,
    RiskMetricMethod
)
# Phase1MetricsProvider recording is now handled by CoreAggregator


class StrategyMode(Enum):
    """Trading strategy mode selection"""
    STANDARD = "standard"       # Original multi-timeframe signal aggregation
    RESEARCH = "research"       # Research-optimized strategy (2025-11-28)
    HYBRID = "hybrid"          # Combine both for confirmation

logger = logging.getLogger(__name__)
settings = get_settings()


class AutoTrader:
    """
    Automated trading loop that monitors signals and executes trades

    Features:
    - Periodic signal monitoring (configurable interval)
    - Automatic trade execution based on signal strength
    - Risk management integration
    - Position tracking
    - Emergency halt on risk limits
    - Market regime detection and logging (2025-11-28)
    - Daily trade limit tracking (2025-11-29)
    """

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        interval: str = "60",
        check_frequency_seconds: Optional[int] = None,  # Use config default
        enable_volume_profile: bool = False,  # Enable VP analysis (Phase 3)
        position_sizing_method: SizingMethod = SizingMethod.CONFIDENCE_ADJUSTED,  # Dynamic sizing
        use_performance_data: bool = True,  # Use performance tracker for Kelly
        enable_market_regime: bool = True,  # Enable ADX-based market regime detection
        strategy_mode: StrategyMode = StrategyMode.RESEARCH,  # Default to research strategy (2025-11-28)
    ):
        """
        Initialize the automated trader

        Args:
            symbols: List of trading symbols (default: from config)
            interval: Timeframe for analysis (default: 60 minutes)
            check_frequency_seconds: How often to check signals (default: from config)
            enable_volume_profile: Enable Volume Profile analysis (default: False)
            position_sizing_method: Position sizing method (default: CONFIDENCE_ADJUSTED)
            use_performance_data: Use performance tracker for Kelly calculation
            enable_market_regime: Enable ADX-based market regime detection (default: True)
            strategy_mode: Trading strategy mode (default: RESEARCH for research-backed decisions)
        """
        self.symbols = symbols or settings.trading_symbols
        # FIXED: Warn if no symbols configured (code review 2025-11-28)
        if not self.symbols:
            logger.warning("No trading symbols configured - AutoTrader will not trade any pairs")
        self.interval = interval
        # Use config value if not specified
        self.check_frequency = check_frequency_seconds or getattr(settings, 'check_frequency_seconds', 30)
        self.enable_vp = enable_volume_profile
        self.position_sizing_method = position_sizing_method
        self.use_performance_data = use_performance_data
        self.enable_market_regime = enable_market_regime
        self.strategy_mode = strategy_mode
        self.is_running = False
        self.task: Optional[asyncio.Task] = None

        # Get the regime detector
        self.regime_detector = get_market_regime_detector(enabled=enable_market_regime)

        # Initialize research-optimized strategy (2025-11-28)
        self.research_strategy = ResearchOptimizedStrategy()

        # Statistics
        self.total_signals_checked = 0
        self.total_trades_executed = 0
        self.total_trades_rejected = 0
        self.last_check_time: Optional[datetime] = None

        # Regime statistics
        self.regime_counts = {regime: 0 for regime in MarketRegime}

        # Research strategy statistics
        self.research_trades = 0
        self.standard_trades = 0

        # Daily trade tracking (2025-11-29)
        self.daily_trades_count = 0
        self.daily_trades_date = datetime.now().date()
        self.max_daily_trades = getattr(settings, 'max_daily_trades', 20)
        self.last_trade_time_per_symbol: dict = {}  # Track last trade time per symbol
        self.min_time_between_trades = getattr(settings, 'min_time_between_trades_same_symbol', 60)
        self.allow_same_symbol_reentry = getattr(settings, 'allow_same_symbol_reentry', True)

        # ============================================================================
        # RESEARCH-BACKED TRADING ENHANCEMENTS (2025-11-30)
        # ============================================================================

        # Circuit Breaker: Protect against API failures
        # Research: FIA Best Practices for Automated Trading Risk Controls
        self.circuit_breaker = get_circuit_breaker(
            "aggregator_api",
            CircuitBreakerConfig(
                failure_threshold=5,       # Open after 5 consecutive failures
                success_threshold=3,       # Close after 3 successes in half-open
                timeout_seconds=60.0,      # Wait 60s before attempting recovery
                half_open_max_calls=3      # Allow 3 test calls in half-open state
            )
        )

        # Kill Switch: Multi-threshold emergency stop
        # Research: Industry standard risk controls
        self.kill_switch = get_kill_switch(
            KillSwitchConfig(
                max_daily_loss_pct=5.0,        # Stop if daily loss > 5%
                max_drawdown_pct=10.0,         # Stop if drawdown > 10%
                max_position_value=100000.0,   # Stop if position > $100k
                max_consecutive_losses=5,      # Stop after 5 consecutive losses
                confirmation_delay_seconds=5,  # 5s delay for manual activation
                auto_reset_hours=24,           # Auto-reset after 24h
                require_multi_threshold=True   # Require 2+ thresholds for auto-activate
            )
        )

        # Slippage Manager: Execution quality control
        # Research: LuxAlgo Trading Slippage Analysis
        self.slippage_manager = get_slippage_manager(
            SlippageConfig(
                base_tolerance_pct=0.15,       # 0.15% normal slippage tolerance
                volatile_tolerance_pct=0.30,   # 0.30% during volatile markets
                rejection_threshold_pct=0.50,  # Reject trades with > 0.5% slippage
                use_limit_orders=True,         # Prefer limit orders
                order_splitting_enabled=True,  # Split large orders
                max_order_value_for_market=1000.0  # Use limit for orders > $1000
            )
        )

        # Execution Timer: Position monitoring intervals
        # Research: Low-Latency Trading Systems best practices
        self.execution_timer = get_execution_timer(
            TimingConfig(
                position_check_interval=15.0,   # 15s between position checks
                price_update_interval=10.0,     # 10s between price updates
                trailing_stop_interval=15.0,    # 15s for trailing stop updates
                signal_check_interval=30.0,     # 30s between signal checks
                min_interval=5.0,               # Min 5s between any operations
                max_interval=300.0,             # Max 5 min interval
                adaptive_factor=1.5             # Adaptive multiplier
            )
        )

        # Order State Machine: FIX protocol style order lifecycle
        self.order_state_machine = get_order_state_machine()

        # ============================================================================
        # ADVANCED TRADING ENHANCEMENTS (2025-11-30 v2)
        # ============================================================================

        # Advanced Position Sizer: Kelly Criterion, Optimal F, Risk Parity
        # Research: Professional trading position sizing algorithms
        self.advanced_position_sizer = AdvancedPositionSizer(
            AdvancedSizingConfig(
                max_position_pct=0.25,         # Max 25% per position
                kelly_fraction=0.25,           # Use Quarter Kelly (safer)
                min_win_rate=0.35,             # Min 35% win rate for Kelly
                min_profit_factor=1.2,         # Min 1.2 profit factor
                atr_risk_multiplier=2.0,       # 2x ATR for volatility sizing
                anti_martingale_factor=1.5,    # 50% increase after wins
                max_consecutive_increases=3,   # Cap consecutive increases
                use_drawdown_adjustment=True   # Reduce during drawdown
            )
        )

        # Smart Order Executor: TWAP, VWAP, Iceberg algorithms
        # Research: Institutional order execution strategies
        self.smart_order_executor = SmartOrderExecutor(
            default_algorithm=ExecutionAlgorithm.TWAP,
            twap_duration_minutes=5,           # 5-minute TWAP default
            vwap_participation_rate=0.15,      # 15% of volume
            iceberg_visible_pct=0.20,          # Show 20% of order
            min_slice_value=100.0,             # Min $100 per slice
            max_slices=10                      # Max 10 order slices
        )

        # Performance Analytics: Sharpe, Sortino, VaR, CVaR
        # Research: Professional risk metrics
        self.performance_analytics = PerformanceAnalytics(
            risk_free_rate=0.05,               # 5% risk-free rate (annualized)
            var_confidence=0.95,               # 95% VaR confidence level
            var_method=RiskMetricMethod.HISTORICAL,
            target_return=0.0,                 # For Sortino ratio
            monte_carlo_simulations=10000      # For Monte Carlo VaR
        )

        # Trade history for analytics (stores returns)
        self.trade_returns: List[float] = []
        self.equity_history: List[float] = []

        # Enhancement statistics
        self.circuit_breaker_triggers = 0
        self.kill_switch_triggers = 0
        self.slippage_rejections = 0
        self.smart_execution_count = 0
        self.position_sizing_adjustments = 0

        logger.info(
            f"AutoTrader initialized: symbols={len(self.symbols)} pairs, "
            f"interval={self.interval}, frequency={self.check_frequency}s, "
            f"VP={'ENABLED' if self.enable_vp else 'DISABLED'}, "
            f"Sizing={self.position_sizing_method.value}, "
            f"MarketRegime={'ENABLED' if self.enable_market_regime else 'DISABLED'}, "
            f"StrategyMode={self.strategy_mode.value}"
        )
        logger.info(f"Trade Limits: max_daily={self.max_daily_trades}, reentry_cooldown={self.min_time_between_trades}s")
        logger.info(f"Trading symbols: {self.symbols}")
        logger.info(f"Research Strategy Parameters: {self.research_strategy.get_strategy_params()}")

        # Log enhancement configuration
        logger.info("=" * 70)
        logger.info("RESEARCH-BACKED TRADING ENHANCEMENTS ENABLED (2025-11-30)")
        logger.info("=" * 70)
        logger.info(f"  Circuit Breaker: failure_threshold=5, timeout=60s")
        logger.info(f"  Kill Switch: daily_loss=5%, drawdown=10%, consecutive_losses=5")
        logger.info(f"  Slippage Manager: base=0.15%, volatile=0.30%, reject=0.50%")
        logger.info(f"  Execution Timer: position=15s, price=10s, trailing=15s")
        logger.info(f"  Order State Machine: FIX protocol style tracking")
        logger.info("=" * 70)
        logger.info("ADVANCED TRADING ENHANCEMENTS ENABLED (2025-11-30 v2)")
        logger.info("=" * 70)
        logger.info(f"  Advanced Position Sizer: Quarter Kelly, max=25%, ATR-based")
        logger.info(f"  Smart Order Executor: TWAP/VWAP/Iceberg, 5-min duration")
        logger.info(f"  Performance Analytics: Sharpe, Sortino, VaR@95%, CVaR")
        logger.info("=" * 70)

    async def start(self):
        """Start the automated trading loop"""
        if self.is_running:
            logger.warning("AutoTrader is already running")
            return False

        logger.info("Starting automated trading loop")
        self.is_running = True
        self.task = asyncio.create_task(self._trading_loop())
        return True

    async def stop(self):
        """Stop the automated trading loop"""
        if not self.is_running:
            logger.warning("AutoTrader is not running")
            return False

        logger.info("Stopping automated trading loop")
        self.is_running = False

        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                logger.info("Trading loop task cancelled successfully")

        return True

    async def _trading_loop(self):
        """Main trading loop - runs continuously until stopped"""
        logger.info("Automated trading loop started")
        logger.info(f"Strategy Mode: {self.strategy_mode.value}")
        logger.info("Position monitoring enabled: trailing stops + partial exits")
        logger.info("Research-backed enhancements: Circuit Breaker, Kill Switch, Slippage Manager")

        # Initialize kill switch with starting balance
        paper_engine = get_paper_engine()
        starting_balance = paper_engine.get_balance()
        self.kill_switch.initialize_balance(float(starting_balance))

        while self.is_running:
            try:
                # ================================================================
                # STEP 0: CHECK KILL SWITCH (2025-11-30)
                # ================================================================
                # Multi-threshold emergency stop check
                if self.kill_switch.should_halt_trading():
                    self.kill_switch_triggers += 1
                    logger.critical(
                        f"KILL SWITCH ACTIVE - Trading halted | "
                        f"Reason: {self.kill_switch.state.activation_reason.value if self.kill_switch.state.activation_reason else 'Unknown'}"
                    )
                    # Still monitor positions but don't open new trades
                    if self.execution_timer.should_check_positions():
                        await self._monitor_positions()
                        self.execution_timer.record_check("positions")
                    await asyncio.sleep(60)  # Check less frequently when halted
                    continue

                # ================================================================
                # STEP 1: Monitor existing positions (2025-11-29)
                # ================================================================
                # Use execution timer to control position monitoring frequency
                if self.execution_timer.should_check_positions():
                    await self._monitor_positions()
                    self.execution_timer.record_check("positions")

                # ================================================================
                # STEP 2: Check for new trading signals
                # ================================================================
                # Only check signals if timer allows (prevents excessive API calls)
                if self.execution_timer.should_check_signals():
                    for symbol in self.symbols:
                        # Check circuit breaker before making API calls
                        if not self.circuit_breaker.can_execute():
                            self.circuit_breaker_triggers += 1
                            logger.warning(
                                f"Circuit breaker OPEN for aggregator_api - skipping {symbol}"
                            )
                            continue

                        try:
                            if self.strategy_mode == StrategyMode.RESEARCH:
                                # Use research-optimized strategy (2025-11-28)
                                await self._check_and_trade_research(symbol)
                            elif self.strategy_mode == StrategyMode.HYBRID:
                                # Use both strategies and trade only if both agree
                                await self._check_and_trade_hybrid(symbol)
                            else:
                                # Standard multi-timeframe strategy
                                await self._check_and_trade(symbol)

                            # Record success for circuit breaker
                            self.circuit_breaker.record_success()

                        except Exception as symbol_error:
                            # Record failure for circuit breaker
                            self.circuit_breaker.record_failure(symbol_error)
                            logger.error(f"Error checking {symbol}: {symbol_error}")

                    self.execution_timer.record_check("signals")

                # Update last check time
                self.last_check_time = datetime.now()

                # Wait before next check (use configured frequency)
                logger.info(f"Waiting {self.check_frequency}s until next check")
                logger.debug(
                    f"Enhancement stats: CB_triggers={self.circuit_breaker_triggers}, "
                    f"KS_triggers={self.kill_switch_triggers}, "
                    f"Slippage_rejects={self.slippage_rejections}"
                )
                await asyncio.sleep(self.check_frequency)

            except asyncio.CancelledError:
                logger.info("Trading loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in trading loop: {e}", exc_info=True)
                # Wait a bit before retrying to avoid rapid error loops
                await asyncio.sleep(60)

    async def _check_and_trade_hybrid(self, symbol: str):
        """
        Check signals using both standard and research strategies

        Only executes trade if both strategies agree on direction.
        Uses research strategy's position sizing and stops when trading.

        Args:
            symbol: Trading symbol to check
        """
        try:
            logger.info(f"[HYBRID] Checking signal for {symbol}")
            self.total_signals_checked += 1

            # Get risk manager
            risk_mgr = get_risk_manager()
            if risk_mgr.should_halt_trading():
                logger.warning(f"[HYBRID] Trading halted due to risk limits for {symbol}")
                return

            # Get aggregated signal for standard strategy
            aggregator = await get_aggregator()
            signal = await aggregator.get_trading_signal_multi_timeframe(
                symbol=symbol,
                primary_interval=self.interval,
                timeframes=["15", self.interval, "240"],
            )

            if not signal:
                logger.warning(f"[HYBRID] No signal data returned for {symbol}")
                return

            # Get standard signal action
            standard_action = signal.action.value
            standard_confidence = signal.confidence
            meets_requirements = signal.metadata.get("meets_requirements", False)

            # Get current price from indicators
            current_price = None
            for indicator_name, indicator_signal in signal.indicators.items():
                if hasattr(indicator_signal, 'metadata') and indicator_signal.metadata:
                    if "current_price" in indicator_signal.metadata:
                        current_price = float(indicator_signal.metadata["current_price"])
                        break

            if not current_price:
                logger.warning(f"[HYBRID] No current price found for {symbol}")
                return

            # Get paper trading engine for balance
            paper_engine = get_paper_engine()
            balance = paper_engine.get_balance()

            # Generate research-based signal
            trade_setup = self.research_strategy.generate_signal(
                indicators=signal.indicators,
                current_price=current_price,
                capital=float(balance)
            )

            research_action = trade_setup.action.value if trade_setup else "HOLD"
            research_confidence = trade_setup.confidence if trade_setup else 0.0

            # Log both signals
            logger.info(f"[HYBRID] Standard: {standard_action} ({standard_confidence:.2%})")
            logger.info(f"[HYBRID] Research: {research_action} ({research_confidence:.2%})")

            # Check for agreement
            if standard_action == research_action and standard_action in ["BUY", "SELL"]:
                if meets_requirements and trade_setup:
                    logger.info(f"[HYBRID] AGREEMENT: Both strategies say {standard_action}")
                    await self._execute_trade_with_setup(symbol, trade_setup)
                    self.research_trades += 1
                    self.standard_trades += 1
                else:
                    logger.info(f"[HYBRID] Agreement on {standard_action} but requirements not met")
                    self.total_trades_rejected += 1
            else:
                logger.info(f"[HYBRID] DISAGREEMENT: Standard={standard_action}, Research={research_action}")
                logger.info(f"[HYBRID] Holding position for {symbol}")

        except Exception as e:
            logger.error(f"[HYBRID] Error checking signal for {symbol}: {e}", exc_info=True)

    async def _check_and_trade(self, symbol: str):
        """
        Check signal for a symbol and execute trade if conditions are met

        Args:
            symbol: Trading symbol to check
        """
        try:
            logger.info(f"Checking signal for {symbol}")
            self.total_signals_checked += 1

            # Get risk manager
            risk_mgr = get_risk_manager()

            # Check if trading is halted
            if risk_mgr.should_halt_trading():
                logger.warning(f"Trading halted due to risk limits for {symbol}")
                return

            # Detect market regime if enabled
            regime_analysis = None
            if self.enable_market_regime:
                regime_analysis = await self.regime_detector.detect_regime(
                    symbol=symbol,
                    interval=self.interval
                )
                # Track regime counts
                self.regime_counts[regime_analysis.regime] += 1

                # Log regime information
                self._log_market_regime(symbol, regime_analysis)

            # Get aggregated signal with multi-timeframe confirmation (Phase 2)
            # and Volume Profile analysis (Phase 3) if enabled
            aggregator = await get_aggregator()

            if self.enable_vp:
                # Use VP-enhanced signals (Phase 3)
                signal = await aggregator.get_trading_signal_with_vp(
                    symbol=symbol,
                    primary_interval=self.interval,
                    timeframes=["15", self.interval, "240"],
                    enable_vp=True,
                    vp_lookback=100,
                    regime_analysis=regime_analysis
                )
            else:
                # Use multi-timeframe only (Phase 2)
                signal = await aggregator.get_trading_signal_multi_timeframe(
                    symbol=symbol,
                    primary_interval=self.interval,
                    timeframes=["15", self.interval, "240"],  # Short, medium, long-term
                    regime_analysis=regime_analysis
                )

            if not signal:
                logger.warning(f"No signal data returned for {symbol}")
                return

            # Extract signal information
            action = signal.action.value  # Convert enum to string
            confidence = signal.confidence
            aggregated_score = signal.aggregated_score

            # Note: Signal recording is now handled by CoreAggregator.aggregate_signals()
            # with real filter data from gatekeeper/validator modules

            # Log multi-timeframe analysis if available (Phase 2)
            mtf_data = signal.metadata.get("multi_timeframe", {})
            vp_data = signal.metadata.get("volume_profile", {})
            regime_data = signal.metadata.get("market_regime", {})

            # Build comprehensive log message
            if self.enable_vp and vp_data:
                # Show VP-enhanced signal (Phase 3)
                logger.info(
                    f"Signal for {symbol}: {action} "
                    f"(confidence: {confidence:.2%}, score: {aggregated_score:.2f})"
                )
                logger.info(
                    f"   MTF: {mtf_data.get('alignment_strength', 'N/A')} "
                    f"(modifier: {mtf_data.get('confidence_modifier', 1.0):.2f}x)"
                )
                logger.info(
                    f"   VP: {vp_data.get('strategy', 'N/A')} | {vp_data.get('position', 'N/A')} "
                    f"| POC=${vp_data.get('poc', 0):.2f} | SL=${vp_data.get('stop_loss', 0):.2f}"
                )
            elif mtf_data and mtf_data.get("enabled"):
                # Show MTF-only signal (Phase 2)
                logger.info(
                    f"Signal for {symbol}: {action} "
                    f"(confidence: {confidence:.2%}, score: {aggregated_score:.2f}) "
                    f"[MTF: {mtf_data.get('alignment_strength')} "
                    f"modifier: {mtf_data.get('confidence_modifier', 1.0):.2f}x]"
                )
            else:
                # Fallback logging
                logger.info(
                    f"Signal for {symbol}: {action} "
                    f"(confidence: {confidence:.2f}, score: {aggregated_score:.2f})"
                )

            # Log market regime impact on signal if available
            if regime_data:
                logger.info(
                    f"   REGIME: {regime_data.get('regime', 'N/A')} | "
                    f"ADX: {regime_data.get('adx', 0):.1f} | "
                    f"Direction: {regime_data.get('direction', 'N/A')} | "
                    f"Modifier: {regime_data.get('confidence_modifier', 1.0):.2f}x"
                )
                logger.info(f"   Strategy: {regime_data.get('strategy_recommendation', 'N/A')}")

            # Check if signal meets requirements
            meets_requirements = signal.metadata.get("meets_requirements", False)

            if not meets_requirements:
                logger.info(f"Signal doesn't meet minimum requirements for {symbol}")
                self.total_trades_rejected += 1
                return

            # Check if we should trade
            if action in ["BUY", "SELL"]:
                await self._execute_trade(symbol, action, confidence, signal)
            else:
                logger.info(f"Holding position for {symbol}")

        except Exception as e:
            logger.error(f"Error checking signal for {symbol}: {e}", exc_info=True)

    async def _check_and_trade_research(self, symbol: str):
        """
        Check signal using research-optimized strategy and execute trade

        This method uses the ResearchOptimizedStrategy which incorporates:
        - Short-period RSI (6) with 15/85 thresholds
        - MACD as confirmation, not primary trigger
        - ADX-based market regime classification
        - ATR-based stops (2x ATR for stop, 4x for TP)
        - Quarter Kelly position sizing

        Args:
            symbol: Trading symbol to check
        """
        try:
            logger.info(f"[RESEARCH] Checking signal for {symbol}")
            self.total_signals_checked += 1

            # Get risk manager
            risk_mgr = get_risk_manager()

            # Check if trading is halted
            if risk_mgr.should_halt_trading():
                logger.warning(f"[RESEARCH] Trading halted due to risk limits for {symbol}")
                return

            # Get aggregated signal to get indicator data
            aggregator = await get_aggregator()
            signal = await aggregator.get_trading_signal_multi_timeframe(
                symbol=symbol,
                primary_interval=self.interval,
                timeframes=["15", self.interval, "240"],
            )

            if not signal:
                logger.warning(f"[RESEARCH] No signal data returned for {symbol}")
                return

            # Get current price from indicators
            current_price = None
            for indicator_name, indicator_signal in signal.indicators.items():
                if hasattr(indicator_signal, 'metadata') and indicator_signal.metadata:
                    if "current_price" in indicator_signal.metadata:
                        current_price = float(indicator_signal.metadata["current_price"])
                        break

            if not current_price:
                logger.warning(f"[RESEARCH] No current price found for {symbol}")
                return

            # Get paper trading engine for balance
            paper_engine = get_paper_engine()
            balance = paper_engine.get_balance()

            # Generate research-based signal
            trade_setup = self.research_strategy.generate_signal(
                indicators=signal.indicators,
                current_price=current_price,
                capital=float(balance)
            )

            if not trade_setup:
                logger.info(f"[RESEARCH] No valid trade setup for {symbol} (insufficient indicator alignment)")
                return

            # Log research signal details
            logger.info("=" * 70)
            logger.info(f"[RESEARCH SIGNAL] {symbol}")
            logger.info("=" * 70)
            logger.info(f"  Action: {trade_setup.action.value}")
            logger.info(f"  Confidence: {trade_setup.confidence:.2%}")
            logger.info(f"  Signal Strength: {trade_setup.signal_strength.value}")
            logger.info(f"  Indicators Aligned: {trade_setup.indicators_aligned}")
            logger.info(f"  Market Condition: {trade_setup.market_condition.value}")
            logger.info(f"  Entry: ${trade_setup.entry_price:.2f}")
            logger.info(f"  Stop Loss: ${trade_setup.stop_loss:.2f}")
            logger.info(f"  Take Profit: ${trade_setup.take_profit:.2f}")
            logger.info(f"  Position Size: {trade_setup.position_size_pct:.2%}")
            for reason in trade_setup.reasoning:
                logger.info(f"  - {reason}")
            logger.info("=" * 70)

            # Execute trade if action is BUY or SELL
            if trade_setup.action.value in ["BUY", "SELL"]:
                await self._execute_trade_with_setup(symbol, trade_setup)
                self.research_trades += 1
            else:
                logger.info(f"[RESEARCH] Holding position for {symbol}")

        except Exception as e:
            logger.error(f"[RESEARCH] Error checking signal for {symbol}: {e}", exc_info=True)

    def _check_daily_trade_limit(self) -> bool:
        """
        Check if daily trade limit has been reached

        Returns:
            True if can trade, False if limit reached
        """
        # Reset counter if new day
        today = datetime.now().date()
        if today != self.daily_trades_date:
            logger.info(f"New trading day - resetting daily trade count from {self.daily_trades_count}")
            self.daily_trades_count = 0
            self.daily_trades_date = today

        if self.daily_trades_count >= self.max_daily_trades:
            logger.info(f"Daily trade limit reached: {self.daily_trades_count}/{self.max_daily_trades}")
            return False
        return True

    def _check_symbol_cooldown(self, symbol: str) -> bool:
        """
        Check if symbol is in cooldown period after last trade

        Args:
            symbol: Trading symbol to check

        Returns:
            True if can trade (no cooldown or cooldown expired), False if in cooldown
        """
        if not self.allow_same_symbol_reentry:
            return True  # No cooldown tracking if reentry disabled

        last_trade_time = self.last_trade_time_per_symbol.get(symbol)
        if last_trade_time:
            elapsed = (datetime.now() - last_trade_time).total_seconds()
            if elapsed < self.min_time_between_trades:
                logger.debug(f"{symbol} in cooldown: {elapsed:.0f}s < {self.min_time_between_trades}s")
                return False
        return True

    def _record_trade(self, symbol: str):
        """Record a trade for daily limit and cooldown tracking"""
        self.daily_trades_count += 1
        self.last_trade_time_per_symbol[symbol] = datetime.now()
        logger.info(f"Trade recorded: {symbol} | Daily count: {self.daily_trades_count}/{self.max_daily_trades}")

    async def _execute_trade_with_setup(self, symbol: str, trade_setup: TradeSetup):
        """
        Execute a trade using the research strategy TradeSetup

        This uses the ATR-based stops and Kelly position sizing from the strategy.
        Supports both PAPER and LIVE trading modes based on configuration.

        ENHANCED 2025-11-30:
        - Kill switch metrics tracking
        - Slippage validation before execution
        - Order state machine tracking

        Args:
            symbol: Trading symbol
            trade_setup: Complete trade setup from ResearchOptimizedStrategy
        """
        try:
            # ================================================================
            # PRE-TRADE CHECKS (Enhanced 2025-11-30)
            # ================================================================

            # Check kill switch first
            if self.kill_switch.should_halt_trading():
                logger.warning(f"[RESEARCH] Kill switch active, rejecting trade for {symbol}")
                self.total_trades_rejected += 1
                return

            # Check daily trade limit first
            if not self._check_daily_trade_limit():
                logger.info(f"[RESEARCH] Daily trade limit reached, skipping {symbol}")
                self.total_trades_rejected += 1
                return

            # Check symbol cooldown
            if not self._check_symbol_cooldown(symbol):
                logger.debug(f"[RESEARCH] {symbol} in cooldown period, skipping")
                return

            action = trade_setup.action.value
            trading_mode = settings.trading_mode

            logger.info(f"[{trading_mode}] Executing {action} trade for {symbol}")

            # ================================================================
            # SLIPPAGE CHECK (Enhanced 2025-11-30)
            # ================================================================
            # Check if limit order should be used based on order value
            position_value_estimate = trade_setup.entry_price * trade_setup.position_size_pct * 10000  # Rough estimate
            should_use_limit, limit_reason = self.slippage_manager.should_use_limit_order(
                position_value_estimate, symbol
            )
            if should_use_limit:
                logger.info(f"[RESEARCH] Limit order recommended: {limit_reason}")

            # Get appropriate trading engine based on mode
            position_mgr = get_position_manager()

            if trading_mode == "LIVE":
                # Use live trading engine for real Bybit orders
                trading_engine = get_live_engine()
                balance = await trading_engine.get_balance()
                logger.info(f"[LIVE] Real Bybit balance: ${balance:.2f}")
            else:
                # Use paper trading engine for simulation
                trading_engine = get_paper_engine()
                balance = trading_engine.get_balance()
                logger.info(f"[PAPER] Simulated balance: ${balance:.2f}")

            # Check if we already have an open position for this symbol
            open_positions = position_mgr.get_open_positions()
            has_position = any(p.symbol == symbol for p in open_positions)

            if has_position:
                logger.info(f"[RESEARCH] Already have open position for {symbol}, skipping")
                self.total_trades_rejected += 1
                return

            # Calculate position value using strategy's position sizing
            position_value = float(balance) * trade_setup.position_size_pct
            quantity = position_value / trade_setup.entry_price

            logger.info(
                f"[RESEARCH] Position sizing: {trade_setup.position_size_pct:.2%} of ${balance:.2f} "
                f"= ${position_value:.2f} ({quantity:.4f} units)"
            )

            # Execute the trade
            side = OrderSide.BUY if action == "BUY" else OrderSide.SELL

            order = OrderCreate(
                symbol=symbol,
                side=side,
                type=OrderType.MARKET,
                quantity=Decimal(str(quantity)),
                strategy="research_optimized"
            )

            # Execute through appropriate engine (paper or live)
            executed_order, error = await trading_engine.execute_market_order(
                order, Decimal(str(trade_setup.entry_price))
            )

            # FIXED: Null check for executed_order (code review 2025-11-28)
            if executed_order is None:
                self.total_trades_rejected += 1
                logger.warning(f"[{trading_mode}] Trade execution returned None for {symbol}: {error}")
                return

            if executed_order.status == OrderStatus.FILLED:
                self.total_trades_executed += 1
                self._record_trade(symbol)  # Track for daily limit and cooldown

                # ================================================================
                # POST-TRADE: Update Kill Switch Metrics (2025-11-30)
                # ================================================================
                # Get updated balance for kill switch tracking
                current_balance = trading_engine.get_balance() if trading_mode == "PAPER" else await trading_engine.get_balance()
                triggered = self.kill_switch.update_metrics(
                    current_balance=float(current_balance),
                    trade_pnl=0.0,  # Will be updated on position close
                    was_loss=False,  # New position, not a loss yet
                    position_value=float(position_value)
                )
                if triggered:
                    logger.warning(f"[RESEARCH] Kill switch thresholds triggered: {triggered}")

                # Record expected vs actual for slippage tracking
                # (Actual price is same as expected for market orders in simulation)
                self.slippage_manager.record_execution(
                    symbol=symbol,
                    expected_price=Decimal(str(trade_setup.entry_price)),
                    actual_price=Decimal(str(trade_setup.entry_price)),  # Same for simulated market orders
                    side=action,
                    quantity=Decimal(str(quantity))
                )

                logger.info(f"[{trading_mode}] Trade executed successfully for {symbol}")
                logger.info(
                    f"[{trading_mode}] Stops: SL=${trade_setup.stop_loss:.2f}, "
                    f"TP=${trade_setup.take_profit:.2f}"
                )
                logger.info(
                    f"[{trading_mode}] Stats: Checked={self.total_signals_checked}, "
                    f"Executed={self.total_trades_executed}, "
                    f"Daily={self.daily_trades_count}/{self.max_daily_trades}, "
                    f"Rejected={self.total_trades_rejected}"
                )
            else:
                self.total_trades_rejected += 1
                logger.warning(f"[{trading_mode}] Trade execution failed for {symbol}: {error}")

        except Exception as e:
            logger.error(f"[RESEARCH] Error executing trade for {symbol}: {e}", exc_info=True)
            self.total_trades_rejected += 1

    def _log_market_regime(self, symbol: str, regime_analysis) -> None:
        """
        Log detailed market regime information

        Args:
            symbol: Trading symbol
            regime_analysis: RegimeAnalysis object from detector
        """
        logger.info("=" * 60)
        logger.info(f"MARKET REGIME for {symbol}")
        logger.info("=" * 60)
        logger.info(f"  Regime: {regime_analysis.regime.value}")
        logger.info(f"  Direction: {regime_analysis.direction.value}")
        logger.info(
            f"  ADX: {regime_analysis.adx:.1f} | "
            f"+DI: {regime_analysis.plus_di:.1f} | "
            f"-DI: {regime_analysis.minus_di:.1f}"
        )
        logger.info(f"  Confidence Modifier: {regime_analysis.confidence_modifier:.2f}x")
        logger.info(f"  Description: {regime_analysis.description}")
        logger.info(f"  Strategy: {regime_analysis.strategy_recommendation}")
        logger.info("=" * 60)

    # ============================================================================
    # RESEARCH-BACKED: Position Monitoring (2025-11-29)
    # ============================================================================

    async def _monitor_positions(self):
        """
        Monitor open positions for trailing stops and partial exits

        RESEARCH-BACKED POSITION MANAGEMENT:
        1. Update trailing stops as price moves favorably
        2. Execute partial exits at TP1, TP2, TP3 levels
        3. Close positions when full exit triggered

        This method should be called periodically alongside signal checking.
        """
        try:
            position_mgr = get_position_manager()
            paper_engine = get_paper_engine()

            open_positions = position_mgr.get_open_positions()

            if not open_positions:
                return

            logger.debug(f"[MONITOR] Checking {len(open_positions)} open positions")

            for position in open_positions:
                try:
                    # Get current price for this symbol
                    current_price = await self._get_current_price(position.symbol)

                    if not current_price:
                        logger.warning(f"[MONITOR] No price for {position.symbol}")
                        continue

                    # Get ATR value for trailing stop distance
                    atr_value = await self._get_atr_value(position.symbol)

                    # Update position with trailing and check exits
                    position, partial_exit = position_mgr.update_position_with_trailing(
                        position.id,
                        Decimal(str(current_price)),
                        atr_value
                    )

                    # Check all exit conditions
                    should_exit, reason, exit_info = position_mgr.check_all_exit_conditions(
                        position.id,
                        Decimal(str(current_price))
                    )

                    if should_exit:
                        # Full exit
                        logger.info(f"[MONITOR] Exit triggered for {position.symbol}: {reason}")
                        await self._close_position(position, current_price, reason)

                    elif exit_info:
                        # Partial exit
                        logger.info(
                            f"[MONITOR] Partial exit for {position.symbol}: "
                            f"{exit_info['level']} - {exit_info['exit_percentage']:.0f}%"
                        )
                        await self._execute_partial_exit(position, exit_info, current_price)

                except Exception as e:
                    logger.error(
                        f"[MONITOR] Error processing position {position.symbol}: {e}",
                        exc_info=True
                    )

        except Exception as e:
            logger.error(f"[MONITOR] Error in position monitoring: {e}", exc_info=True)

    async def _get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current price for a symbol

        Args:
            symbol: Trading symbol

        Returns:
            Current price or None if unavailable
        """
        try:
            aggregator = await get_aggregator()
            signal = await aggregator.get_trading_signal_multi_timeframe(
                symbol=symbol,
                primary_interval=self.interval,
                timeframes=[self.interval]
            )

            if signal and signal.indicators:
                for ind in signal.indicators.values():
                    if hasattr(ind, 'metadata') and ind.metadata:
                        if "current_price" in ind.metadata:
                            return float(ind.metadata["current_price"])

            return None
        except Exception as e:
            logger.warning(f"[MONITOR] Failed to get price for {symbol}: {e}")
            return None

    async def _get_atr_value(self, symbol: str) -> Optional[float]:
        """
        Get ATR value for a symbol

        Args:
            symbol: Trading symbol

        Returns:
            ATR value or None if unavailable
        """
        try:
            aggregator = await get_aggregator()
            signal = await aggregator.get_trading_signal_multi_timeframe(
                symbol=symbol,
                primary_interval=self.interval,
                timeframes=[self.interval]
            )

            if signal and signal.metadata:
                atr_data = signal.metadata.get("atr", {})
                if atr_data:
                    return atr_data.get("atr_value")

            return None
        except Exception as e:
            logger.warning(f"[MONITOR] Failed to get ATR for {symbol}: {e}")
            return None

    async def _close_position(self, position, current_price: float, reason: str):
        """
        Close a position completely

        ENHANCED 2025-11-30:
        - Update kill switch metrics with trade P&L

        Args:
            position: Position to close
            current_price: Current market price
            reason: Reason for closing
        """
        try:
            position_mgr = get_position_manager()
            paper_engine = get_paper_engine()

            # Close the position
            closed = position_mgr.close_position(
                position.id,
                Decimal(str(current_price)),
                reason
            )

            # ================================================================
            # UPDATE KILL SWITCH METRICS (Enhanced 2025-11-30)
            # ================================================================
            trade_pnl = float(closed.realized_pnl) if closed.realized_pnl else 0.0
            was_loss = trade_pnl < 0
            current_balance = paper_engine.get_balance()

            triggered = self.kill_switch.update_metrics(
                current_balance=float(current_balance),
                trade_pnl=trade_pnl,
                was_loss=was_loss,
                position_value=0.0  # Position is closed
            )

            if triggered:
                logger.warning(f"[MONITOR] Kill switch thresholds triggered after close: {triggered}")

            # Record trade return for performance analytics (2025-11-30 v2)
            if closed.pnl_percentage is not None:
                self._record_trade_return(closed.pnl_percentage / 100)  # Convert to decimal

            logger.info(
                f"[MONITOR] Position closed: {position.symbol} | "
                f"P&L: ${float(closed.realized_pnl):.2f} ({closed.pnl_percentage:+.2f}%) | "
                f"Reason: {reason}"
            )

        except Exception as e:
            logger.error(f"[MONITOR] Failed to close position: {e}", exc_info=True)

    async def _execute_partial_exit(self, position, exit_info: dict, current_price: float):
        """
        Execute a partial exit for a position

        Args:
            position: Position with partial exit
            exit_info: Exit info from check_partial_exit
            current_price: Current market price
        """
        try:
            position_mgr = get_position_manager()
            paper_engine = get_paper_engine()

            # Execute the partial exit
            updated_pos, partial_pnl = position_mgr.execute_partial_exit(
                position.id,
                exit_info,
                Decimal(str(current_price))
            )

            level = exit_info["level"]
            logger.info(
                f"[MONITOR] Partial exit executed: {position.symbol} {level} | "
                f"P&L: ${float(partial_pnl):.2f} | "
                f"Remaining: {float(updated_pos.remaining_quantity):.4f}"
            )

            # Enable trailing stop after TP1
            if exit_info.get("enable_trailing", False):
                logger.info(f"[MONITOR] Trailing stop enabled for {position.symbol}")

        except Exception as e:
            logger.error(f"[MONITOR] Failed to execute partial exit: {e}", exc_info=True)

    async def _execute_trade(
        self,
        symbol: str,
        action: str,
        confidence: float,
        signal
    ):
        """
        Execute a trade based on the signal

        Args:
            symbol: Trading symbol
            action: BUY or SELL
            confidence: Signal confidence score
            signal: TradingSignal object
        """
        try:
            logger.info(f"Executing {action} trade for {symbol} (confidence: {confidence:.2f})")

            # Get paper trading engine
            paper_engine = get_paper_engine()
            position_mgr = get_position_manager()
            risk_mgr = get_risk_manager()
            position_sizer = get_position_sizer()

            # Get current balance
            balance = paper_engine.get_balance()  # Fixed: get_balance() is synchronous
            logger.info(f"Current balance: ${balance:.2f}")

            # Get current price from signal indicators
            current_price = None

            # Try to get price from indicators (dict of IndicatorSignal objects)
            for indicator_name, indicator_signal in signal.indicators.items():
                if hasattr(indicator_signal, 'metadata') and indicator_signal.metadata:
                    if "current_price" in indicator_signal.metadata:
                        current_price = float(indicator_signal.metadata["current_price"])
                        break

            if not current_price:
                logger.warning(f"No current price found for {symbol}, skipping trade")
                self.total_trades_rejected += 1
                return

            # Get performance stats for Kelly calculation
            performance_stats = None
            if self.use_performance_data:
                try:
                    perf_tracker = get_performance_tracker()
                    performance_stats = position_sizer.get_performance_stats_from_tracker(perf_tracker)
                    logger.debug(
                        f"Performance stats: win_rate={performance_stats.get('win_rate', 0):.2%}, "
                        f"trades={performance_stats.get('total_trades', 0)}"
                    )
                except Exception as e:
                    logger.warning(f"Could not get performance stats: {e}")

            # Get stop loss from VP data if available
            stop_loss_pct = None
            vp_data = signal.metadata.get("volume_profile", {})
            if vp_data and vp_data.get("stop_loss"):
                stop_loss_price = vp_data.get("stop_loss", 0)
                stop_loss_pct = abs(current_price - stop_loss_price) / current_price
                logger.debug(f"VP Stop Loss: ${stop_loss_price:.2f} ({stop_loss_pct:.2%})")

            # Calculate dynamic position size
            size_result = position_sizer.calculate_position_size(
                method=self.position_sizing_method,
                current_balance=Decimal(str(balance)),
                current_price=Decimal(str(current_price)),
                signal_confidence=confidence,
                performance_stats=performance_stats,
                stop_loss_pct=stop_loss_pct
            )

            # Use calculated position size
            quantity = size_result.quantity
            position_value = size_result.position_value

            logger.info(
                f"Position sizing: {size_result.method.value} "
                f"| Size: {size_result.position_size_pct:.2f}% "
                f"| Value: ${position_value:.2f} "
                f"| Qty: {quantity:.4f}"
            )
            logger.info(f"Reasoning: {size_result.reasoning}")

            # Check if we already have an open position
            open_positions = position_mgr.get_open_positions()  # Fixed: get_open_positions() is synchronous
            has_position = any(p.symbol == symbol for p in open_positions)

            if has_position:
                logger.info(f"Already have open position for {symbol}, skipping")
                self.total_trades_rejected += 1
                return

            # Execute the trade
            side = OrderSide.BUY if action == "BUY" else OrderSide.SELL

            # Fixed: Use execute_market_order() with proper OrderCreate object
            order = OrderCreate(
                symbol=symbol,
                side=side,
                type=OrderType.MARKET,  # Field name is 'type', not 'order_type'
                quantity=Decimal(str(quantity)),
                strategy="auto_trader"
            )

            executed_order, error = await paper_engine.execute_market_order(order, Decimal(str(current_price)))

            if executed_order.status == OrderStatus.FILLED:
                self.total_trades_executed += 1
                logger.info(f"Trade executed successfully for {symbol}")
                logger.info(f"Stats: Checked={self.total_signals_checked}, "
                          f"Executed={self.total_trades_executed}, "
                          f"Rejected={self.total_trades_rejected}")
            else:
                self.total_trades_rejected += 1
                logger.warning(f"Trade execution failed for {symbol}: {error}")

        except Exception as e:
            logger.error(f"Error executing trade for {symbol}: {e}", exc_info=True)
            self.total_trades_rejected += 1

    def _get_performance_summary(self) -> dict:
        """
        Get performance analytics summary

        Returns:
            Dictionary with key performance metrics
        """
        try:
            if not self.trade_returns:
                return {
                    "status": "insufficient_data",
                    "message": "Need at least 2 trade returns for analytics"
                }

            report = self.performance_analytics.generate_report(self.trade_returns)
            return {
                "status": "active",
                "sharpe_ratio": report.sharpe_ratio,
                "sortino_ratio": report.sortino_ratio,
                "calmar_ratio": report.calmar_ratio,
                "omega_ratio": report.omega_ratio,
                "var_95": report.risk_metrics.var,
                "cvar_95": report.risk_metrics.cvar,
                "max_drawdown_pct": report.risk_metrics.max_drawdown_pct,
                "trade_stats": {
                    "total_trades": report.trade_statistics.total_trades,
                    "win_rate": report.trade_statistics.win_rate,
                    "profit_factor": report.trade_statistics.profit_factor,
                    "expectancy": report.trade_statistics.expectancy,
                    "avg_r_multiple": report.trade_statistics.avg_r_multiple
                }
            }
        except Exception as e:
            logger.warning(f"Error generating performance summary: {e}")
            return {"status": "error", "message": str(e)}

    def _record_trade_return(self, pnl_pct: float) -> None:
        """
        Record a trade return for performance analytics

        Args:
            pnl_pct: Trade P&L percentage (e.g., 0.05 for 5% profit)
        """
        self.trade_returns.append(pnl_pct)
        logger.debug(f"Trade return recorded: {pnl_pct:.2%} | Total: {len(self.trade_returns)}")

    def _record_equity(self, balance: float) -> None:
        """
        Record equity value for drawdown tracking

        Args:
            balance: Current account balance
        """
        self.equity_history.append(balance)

    def get_status(self) -> dict:
        """Get current status of the auto trader"""
        # Get position monitoring stats
        position_mgr = get_position_manager()
        open_positions = position_mgr.get_open_positions()

        status = {
            "is_running": self.is_running,
            "symbols": self.symbols,
            "symbols_count": len(self.symbols),
            "interval": self.interval,
            "check_frequency_seconds": self.check_frequency,
            "total_signals_checked": self.total_signals_checked,
            "total_trades_executed": self.total_trades_executed,
            "total_trades_rejected": self.total_trades_rejected,
            "last_check_time": self.last_check_time.isoformat() if self.last_check_time else None,
            "market_regime_enabled": self.enable_market_regime,
            # Research strategy status (2025-11-28)
            "strategy_mode": self.strategy_mode.value,
            "research_trades": self.research_trades,
            "standard_trades": self.standard_trades,
            # Daily trade tracking (2025-11-29)
            "daily_trades": {
                "count": self.daily_trades_count,
                "limit": self.max_daily_trades,
                "remaining": self.max_daily_trades - self.daily_trades_count,
                "date": str(self.daily_trades_date),
                "reentry_cooldown_seconds": self.min_time_between_trades
            },
            # Position monitoring status (2025-11-29)
            "position_monitoring": {
                "enabled": True,
                "open_positions": len(open_positions),
                "trailing_stops_active": sum(1 for p in open_positions if p.trailing_stop_enabled),
                "partial_exits_enabled": True
            },
            # ================================================================
            # RESEARCH-BACKED ENHANCEMENTS STATUS (2025-11-30)
            # ================================================================
            "trading_enhancements": {
                "circuit_breaker": self.circuit_breaker.get_status(),
                "kill_switch": self.kill_switch.get_status(),
                "slippage_manager": self.slippage_manager.get_status(),
                "execution_timer": self.execution_timer.get_status(),
                "order_state_machine": self.order_state_machine.get_stats(),
                "enhancement_triggers": {
                    "circuit_breaker_triggers": self.circuit_breaker_triggers,
                    "kill_switch_triggers": self.kill_switch_triggers,
                    "slippage_rejections": self.slippage_rejections
                }
            },
            # ================================================================
            # ADVANCED ENHANCEMENTS STATUS (2025-11-30 v2)
            # ================================================================
            "advanced_enhancements": {
                "position_sizer": {
                    "method": self.advanced_position_sizer.config.default_method.value if hasattr(self.advanced_position_sizer.config, 'default_method') else "half_kelly",
                    "max_position_pct": self.advanced_position_sizer.config.max_position_pct,
                    "kelly_fraction": self.advanced_position_sizer.config.kelly_fraction,
                    "sizing_adjustments": self.position_sizing_adjustments
                },
                "smart_executor": {
                    "default_algorithm": self.smart_order_executor.default_algorithm.value,
                    "execution_count": self.smart_execution_count,
                    "twap_duration_minutes": self.smart_order_executor.twap_duration_minutes,
                    "max_slices": self.smart_order_executor.max_slices
                },
                "performance_analytics": self._get_performance_summary()
            }
        }

        # Add regime distribution if market regime is enabled
        if self.enable_market_regime:
            status["regime_distribution"] = {
                regime.value: count
                for regime, count in self.regime_counts.items()
                if count > 0
            }
            status["regime_detector_stats"] = self.regime_detector.get_stats()

        # Add research strategy parameters
        if self.strategy_mode in [StrategyMode.RESEARCH, StrategyMode.HYBRID]:
            status["research_strategy_params"] = self.research_strategy.get_strategy_params()

        return status

    def set_strategy_mode(self, mode: StrategyMode) -> None:
        """
        Change the trading strategy mode

        Args:
            mode: New strategy mode to use
        """
        self.strategy_mode = mode
        logger.info(f"Strategy mode changed to: {mode.value}")

    def set_market_regime_enabled(self, enabled: bool) -> None:
        """
        Enable or disable market regime detection

        Args:
            enabled: True to enable, False to disable
        """
        self.enable_market_regime = enabled
        logger.info(f"Market regime detection {'ENABLED' if enabled else 'DISABLED'}")

    # ============================================================================
    # RESEARCH-BACKED ENHANCEMENT CONTROLS (2025-11-30)
    # ============================================================================

    def activate_kill_switch(self, reason: str = "Manual activation") -> bool:
        """
        Manually activate the kill switch

        Args:
            reason: Reason for activation

        Returns:
            True if activation started
        """
        return self.kill_switch.activate_manual(reason)

    def deactivate_kill_switch(self, force: bool = False) -> bool:
        """
        Deactivate the kill switch

        Args:
            force: Force deactivation even if conditions still met

        Returns:
            True if deactivated successfully
        """
        return self.kill_switch.deactivate(force)

    def set_timing_mode(self, mode: str) -> None:
        """
        Set execution timer mode

        Args:
            mode: One of 'aggressive', 'normal', 'conservative', 'adaptive'
        """
        mode_map = {
            'aggressive': TimingMode.AGGRESSIVE,
            'normal': TimingMode.NORMAL,
            'conservative': TimingMode.CONSERVATIVE,
            'adaptive': TimingMode.ADAPTIVE
        }
        if mode.lower() in mode_map:
            self.execution_timer.set_mode(mode_map[mode.lower()])
            logger.info(f"Execution timer mode set to: {mode}")
        else:
            logger.warning(f"Invalid timing mode: {mode}")

    def force_circuit_breaker_open(self) -> None:
        """Force circuit breaker to open state"""
        self.circuit_breaker.force_open()

    def force_circuit_breaker_close(self) -> None:
        """Force circuit breaker to closed state"""
        self.circuit_breaker.force_close()

    def set_slippage_tolerance(self, base_pct: float, volatile_pct: float) -> None:
        """
        Update slippage tolerance thresholds

        Args:
            base_pct: Base tolerance percentage
            volatile_pct: Volatile market tolerance percentage
        """
        self.slippage_manager.config.base_tolerance_pct = base_pct
        self.slippage_manager.config.volatile_tolerance_pct = volatile_pct
        logger.info(f"Slippage tolerance updated: base={base_pct}%, volatile={volatile_pct}%")

    def reset_daily_metrics(self) -> None:
        """Reset daily trading metrics including kill switch"""
        # Reset daily trade count
        self.daily_trades_count = 0
        self.daily_trades_date = datetime.now().date()

        # Reset kill switch daily metrics
        self.kill_switch.reset_daily_metrics()

        logger.info("Daily trading metrics reset")


# Global instance
_auto_trader: Optional[AutoTrader] = None


def get_auto_trader() -> AutoTrader:
    """Get or create the global auto trader instance"""
    global _auto_trader
    if _auto_trader is None:
        _auto_trader = AutoTrader()
    return _auto_trader


def reset_auto_trader():
    """Reset the global auto trader instance (for testing)"""
    global _auto_trader
    _auto_trader = None
