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
from pathlib import Path
from typing import Optional, List, Dict, Set
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.config import get_settings
from app.risk.vol_targeting import (
    RealizedVolEstimator,
    VolEstimatorConfig,
    VolParitySizingConfig,
    vol_parity_size,
)
from app.risk.funding_gate import (
    FundingGateConfig,
    FundingRateClient,
    funding_gate_decision,
)
from app.signal_aggregator import get_aggregator
from app.paper_trading import get_paper_engine
from app.live_trading import get_live_engine
from app.risk_manager import get_risk_manager
from app.position_manager import get_position_manager
from app.position_sizing import get_position_sizer, SizingMethod
from app.performance_tracker import get_performance_tracker
from app.models import OrderSide, OrderType, OrderCreate, OrderStatus
from app.models.enums import SignalAction
from app.aggregation.market_regime import get_market_regime_detector, MarketRegime

# Import hybrid strategy router (combines trend-following + mean reversion)
from app.strategies import TradeSetup
from app.strategies.hybrid_strategy_router import HybridStrategyRouter

# Phase 2.3: Grid Trading Integration (2025-12-08)
from app.strategies.grid_trading_strategy import GridTradingStrategy

# Research-backed trading enhancements (2025-11-30)
from app.trading_enhancements.circuit_breaker import (
    get_circuit_breaker,
    CircuitBreakerConfig,
)
from app.trading_enhancements.kill_switch import (
    get_kill_switch,
    KillSwitchConfig,
)
from app.services.notification_client import get_notification_client
from app.trading_enhancements.slippage_manager import (
    get_slippage_manager,
    SlippageConfig,
)
from app.trading_enhancements.execution_timer import (
    get_execution_timer,
    TimingConfig,
    TimingMode,
)
from app.trading_enhancements.order_state_machine import (
    get_order_state_machine,
)

# Advanced Trading Enhancements (2025-11-30 v2)
from app.trading_enhancements.advanced_position_sizing import (
    AdvancedPositionSizer,
    AdvancedSizingConfig,
)
from app.trading_enhancements.smart_order_execution import (
    SmartOrderExecutor,
)
from app.trading_enhancements.performance_analytics import (
    PerformanceAnalytics,
)

# DCA Manager for averaging down on losing positions (2025-12-02)
from app.trading_enhancements.dca_manager import get_dca_manager, DCAConfig

# Portfolio Heat Manager for total exposure control (2025-12-02)
from app.trading_enhancements.portfolio_heat import (
    get_portfolio_heat_manager,
    PortfolioHeatConfig,
)

# Adaptive RSI with dynamic thresholds (2025-12-02)
from app.trading_enhancements.adaptive_rsi import (
    get_adaptive_rsi,
    AdaptiveRSIConfig,
)

# Hurst Exponent for regime detection (2025-12-02)
from app.trading_enhancements.hurst_exponent import (
    create_hurst_calculator,
)

# Limit Order Executor for better execution (2025-12-02)
from app.trading_enhancements.limit_order_executor import (
    get_limit_order_executor,
    LimitOrderConfig,
)

# Walk Forward Efficiency tester (2025-12-02)
from app.trading_enhancements.walk_forward_tester import (
    get_walk_forward_tester,
    WFEConfig,
)

# Regime-Based Strategy Selection (2025-12-02)
from app.trading_enhancements.regime_strategy_selector import (
    get_regime_strategy_selector,
)

# ATR-Based Trailing Stops (2025-12-02)
from app.trading_enhancements.atr_trailing_stop import (
    get_atr_trailing_stop,
    ATRTrailingStopConfig,
    VolatilityRegime as TrailingStopVolatilityRegime,
)

# Partial Profit Taking (2025-12-02)
from app.trading_enhancements.partial_profit_taker import (
    get_partial_profit_taker,
    PartialProfitConfig,
)
# Phase1MetricsProvider recording is now handled by CoreAggregator


class StrategyMode(Enum):
    """Trading strategy mode selection"""

    STANDARD = "standard"  # Original multi-timeframe signal aggregation
    RESEARCH = "research"  # Research-optimized strategy (2025-11-28)
    HYBRID = "hybrid"  # Combine both for confirmation
    GRID_TRADING = "grid_trading"  # Grid Trading strategy (Phase 2.3 - 2025-12-08)
    ENSEMBLE = "ensemble"  # SimpleRSI + multi-indicator + mean-reversion, performance-weighted (2026-04-25)


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
        position_sizing_method: SizingMethod = SizingMethod.FIXED,  # 2026-05-06: predictable 10%-per-trade sizing on $100 paper balance
        use_performance_data: bool = True,  # Use performance tracker for Kelly
        enable_market_regime: bool = True,  # Enable ADX-based market regime detection
        strategy_mode: StrategyMode = StrategyMode.HYBRID,  # Default to hybrid strategy - mixes research + standard for dual confirmation (2026-02-17)
        enable_ml_predictions: Optional[
            bool
        ] = None,  # Phase 3 ML Integration (2025-12-01)
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
            enable_ml_predictions: Enable ML predictions in signal aggregation (default: from config)
        """
        # Store settings as instance attribute for access throughout the class
        # CRITICAL FIX 2025-12-11: Previously only module-level settings was available,
        # but line 1284 uses self.settings.symbol_allocations which requires instance attr
        self.settings = settings

        self.symbols = symbols or settings.trading_symbols
        # FIXED: Warn if no symbols configured (code review 2025-11-28)
        if not self.symbols:
            logger.warning(
                "No trading symbols configured - AutoTrader will not trade any pairs"
            )
        self.interval = interval
        # Use config value if not specified
        self.check_frequency = check_frequency_seconds or getattr(
            settings, "check_frequency_seconds", 30
        )
        self.enable_vp = enable_volume_profile
        self.position_sizing_method = position_sizing_method
        self.use_performance_data = use_performance_data
        self.enable_market_regime = enable_market_regime
        self.strategy_mode = strategy_mode
        # Phase 3 ML Integration: Use config setting if not explicitly provided
        self.enable_ml = (
            enable_ml_predictions
            if enable_ml_predictions is not None
            else settings.enable_ml_predictions
        )
        self.is_running = False
        self.task: Optional[asyncio.Task] = None

        # File-based emergency stop (operator kill switch).
        # Halts auto-trader at the top of every loop cycle when the file is present.
        self.emergency_stop_file = Path(self.settings.emergency_stop_file)
        self.emergency_stop_active = False
        self.emergency_stop_last_checked: Optional[datetime] = None

        # Concurrent-open dedup (2026-05-06).
        # Multiple signal paths can race past the has_position check before
        # either commits its position row, producing twin positions for the
        # same (symbol, side) at near-identical entry. Claim per-symbol slot
        # atomically before the existence check; release after persist or
        # rejection. Pair with a short cooldown to absorb stale-cache reads
        # from position_mgr.get_open_positions() right after a close.
        self._opening_symbols: Set[str] = set()
        self._opening_lock = asyncio.Lock()
        self._last_open_at: Dict[str, datetime] = {}
        self.open_cooldown_seconds: int = int(
            getattr(self.settings, "open_cooldown_seconds", 60)
        )

        # Stop-loss cooldown (2026-05-15).
        # After a position closes via stop-loss, freeze new entries on the same
        # symbol for sl_cooldown_seconds. Counters the whipsaw pattern observed
        # May 6-7: ADA LONG stop → ADA LONG re-entry within minutes → stop →
        # repeat (7× same setup in 6 hours, all losses). Cleared on bot restart
        # — short-lived in-memory state is acceptable since restart implies
        # operator intervention.
        self._sl_cooldown_until: Dict[str, datetime] = {}
        self.sl_cooldown_seconds: int = int(
            getattr(self.settings, "sl_cooldown_seconds", 14400)  # 4 hours
        )

        # Get the regime detector
        self.regime_detector = get_market_regime_detector(enabled=enable_market_regime)

        # Initialize hybrid strategy router (2026-01-04)
        # Automatically switches between:
        #   - Trend-following (ADX >= 25, trending market)
        #   - Mean reversion (ADX < 25, ranging market)
        self.hybrid_strategy = HybridStrategyRouter()

        # Keep research strategy for backward compatibility
        self.research_strategy = self.hybrid_strategy.trend_strategy

        # Initialize Grid Trading strategy (Phase 2.3 - 2025-12-08)
        # NOTE: Grid Trading showed poor walk-forward validation results:
        #   - Avg Return: -0.00%, Avg Sharpe: -0.49, Avg Win Rate: 32.6%
        #   - Use with caution in live trading
        self.grid_strategies: Dict[
            str, GridTradingStrategy
        ] = {}  # One strategy per symbol

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
        self.max_daily_trades = getattr(settings, "max_daily_trades", 20)
        self.last_trade_time_per_symbol: dict = {}  # Track last trade time per symbol
        self.min_time_between_trades = getattr(
            settings, "min_time_between_trades_same_symbol", 60
        )
        self.allow_same_symbol_reentry = getattr(
            settings, "allow_same_symbol_reentry", True
        )

        # ============================================================================
        # RESEARCH-BACKED TRADING ENHANCEMENTS (2025-11-30)
        # ============================================================================

        # Circuit Breaker: Protect against API failures
        # Research: FIA Best Practices for Automated Trading Risk Controls
        self.circuit_breaker = get_circuit_breaker(
            "aggregator_api",
            CircuitBreakerConfig(
                failure_threshold=5,  # Open after 5 consecutive failures
                success_threshold=3,  # Close after 3 successes in half-open
                timeout_seconds=60.0,  # Wait 60s before attempting recovery
                half_open_max_calls=3,  # Allow 3 test calls in half-open state
            ),
        )

        # Kill Switch: Multi-threshold emergency stop.
        # Daily-loss threshold is operator-tunable via MAX_DAILY_LOSS_PCT
        # (settings.max_daily_loss_pct, default 5%). Drawdown, consecutive-loss,
        # auto-reset and trigger-mode use the research-backed defaults from
        # KillSwitchConfig (drawdown 20%, consec 5, reset 24h, single-threshold
        # trigger). Earlier code hard-coded 50%/50%/20 with the comment
        # "RELAXED FOR SAMPLE COLLECTION" — that left CLAUDE.md's documented
        # 5%/10% safety claims as fiction. Restored 2026-04-28.
        self.kill_switch = get_kill_switch(
            KillSwitchConfig(
                max_daily_loss_pct=self.settings.max_daily_loss_pct,
            )
        )

        # Vol Parity Sizing (T1.2 chunk 3, 2026-04-30, default off)
        # Outer overlay above the per-trade cap. When enabled and the
        # estimator is warm (>= min_samples hourly bars per symbol), sizes
        # new entries inversely to realised vol so each contributes equal
        # expected risk. With default cap_multiplier=1.0 this is downside-
        # only — vol parity may shrink positions but never grows them past
        # the existing baseline, so the per-trade-cap REJECT idiom is
        # untouched. See docs/strategy/research-2026-04-29/T1.2-design.md.
        self._vol_last_hour: Dict[str, datetime] = {}
        if self.settings.enable_vol_targeting:
            self.vol_estimator: Optional[RealizedVolEstimator] = RealizedVolEstimator(
                VolEstimatorConfig(
                    window_bars=self.settings.vol_estimator_window_bars,
                )
            )
            logger.info(
                f"[VOL_PARITY] enabled: target={self.settings.vol_target_annualised:.0%} ann, "
                f"window={self.settings.vol_estimator_window_bars}h, "
                f"cap_multiplier={self.settings.vol_target_cap_multiplier}"
            )
        else:
            self.vol_estimator = None
            logger.info(
                "[VOL_PARITY] disabled (set ENABLE_VOL_TARGETING=true to opt in)"
            )

        # Funding-Rate Gate (T2.3, 2026-04-30) — perp-only entry filter.
        # Lazy-built (None until first signal-check call site that needs it)
        # so tests and PAPER mode don't open an httpx session up-front.
        self._funding_gate_config: Optional[FundingGateConfig] = None
        self._funding_client: Optional[FundingRateClient] = None
        if self.settings.enable_funding_gate:
            self._funding_gate_config = FundingGateConfig(
                threshold_bps=self.settings.funding_gate_threshold_bps,
                cache_ttl_seconds=self.settings.funding_cache_ttl_seconds,
            )
            logger.info(
                f"[FUNDING_GATE] enabled: threshold=±{self.settings.funding_gate_threshold_bps:.1f}bps, "
                f"ttl={self.settings.funding_cache_ttl_seconds}s"
            )
        else:
            logger.info(
                "[FUNDING_GATE] disabled (set ENABLE_FUNDING_GATE=true to opt in)"
            )

        # Slippage Manager: Execution quality control
        # Research: LuxAlgo Trading Slippage Analysis
        self.slippage_manager = get_slippage_manager(
            SlippageConfig(
                base_tolerance_pct=0.15,  # 0.15% normal slippage tolerance
                volatile_tolerance_pct=0.30,  # 0.30% during volatile markets
                rejection_threshold_pct=0.50,  # Reject trades with > 0.5% slippage
                use_limit_orders=True,  # Prefer limit orders
                order_splitting_enabled=True,  # Split large orders
                max_order_value_for_market=1000.0,  # Use limit for orders > $1000
            )
        )

        # Notification Client: Trade alerts via Telegram/Email (2025-12-01)
        self.notification_client = get_notification_client()

        # Execution Timer: Position monitoring intervals
        # Research: Low-Latency Trading Systems best practices
        self.execution_timer = get_execution_timer(
            TimingConfig(
                position_check_interval=15.0,  # 15s between position checks
                price_update_interval=10.0,  # 10s between price updates
                trailing_stop_interval=15.0,  # 15s for trailing stop updates
                signal_check_interval=30.0,  # 30s between signal checks
                min_interval=5.0,  # Min 5s between any operations
                max_interval=300.0,  # Max 5 min interval
                adaptive_factor=1.5,  # Adaptive multiplier
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
                max_position_pct=0.25,  # Max 25% per position
                kelly_fraction=0.25,  # Use Quarter Kelly (safer)
                min_win_rate=0.35,  # Min 35% win rate for Kelly
                min_profit_factor=1.2,  # Min 1.2 profit factor
                atr_risk_multiplier=2.0,  # 2x ATR for volatility sizing
                anti_martingale_factor=1.5,  # 50% increase after wins
                max_consecutive_increases=3,  # Cap consecutive increases
                use_drawdown_adjustment=True,  # Reduce during drawdown
            )
        )

        # Smart Order Executor: TWAP, VWAP, Iceberg algorithms
        # Research: Institutional order execution strategies
        from app.trading_enhancements.smart_order_execution import ExecutionConfig

        self.smart_order_executor = SmartOrderExecutor(
            config=ExecutionConfig(
                twap_duration_minutes=5,  # 5-minute TWAP default
                vwap_participation_rate=0.15,  # 15% of volume
                iceberg_visible_pct=0.20,  # Show 20% of order
                twap_max_slices=10,  # Max 10 order slices
            )
        )

        # Performance Analytics: Sharpe, Sortino, VaR, CVaR
        # Research: Professional risk metrics
        self.performance_analytics = PerformanceAnalytics(
            risk_free_rate=0.05,  # 5% risk-free rate (annualized)
            trading_days_per_year=365,  # Crypto markets are 24/7
        )

        # ============================================================================
        # DCA MANAGER - Dollar Cost Averaging (2025-12-02)
        # Research: Pionex/3Commas/TradeSanta best practices
        # ============================================================================
        self.dca_manager = get_dca_manager()
        # Reconfigure DCA with research-backed defaults
        self.dca_manager.config = DCAConfig(
            enabled=True,
            safety_order_deviation_pct=[
                5.0,
                10.0,
                15.0,
                20.0,
                25.0,
            ],  # Trigger at 5%, 10%, etc.
            safety_order_volume_scale=[1.0, 1.5, 2.0, 2.5, 3.0],  # Scale up each layer
            max_safety_orders=5,  # Max 5 DCA orders
            min_time_between_orders=300,  # 5 minutes between orders
            base_safety_order_pct=100.0,  # Same size as original
            recalculate_tp_on_dca=True,  # Update TP after DCA
            tp_after_dca_pct=2.0,  # 2% TP after averaging
            max_total_position_pct=10.0,  # Max 10% of capital
            stop_loss_after_max_dca_pct=10.0,  # 10% SL after max DCA
        )
        self.dca_orders_executed = 0  # Track DCA executions

        # ============================================================================
        # PORTFOLIO HEAT MANAGER - Total Exposure Control (2025-12-02)
        # Research: Hedge Fund Best Practices - 6-8% max portfolio heat
        # ============================================================================
        self.portfolio_heat_manager = get_portfolio_heat_manager(
            PortfolioHeatConfig(
                max_portfolio_heat_pct=8.0,  # Max 8% total risk exposure
                max_per_trade_pct=2.0,  # Max 2% risk per trade
                max_correlated_exposure_pct=5.0,  # Max 5% in correlated assets
                max_single_asset_pct=10.0,  # Max 10% in single asset
                low_heat_threshold=4.0,  # Below = low heat
                moderate_heat_threshold=6.0,  # Below = moderate
                elevated_heat_threshold=8.0,  # Below = elevated
                critical_heat_threshold=10.0,  # Above = critical
            )
        )

        # ============================================================================
        # ADAPTIVE RSI - Volatility-adjusted indicators (2025-12-02)
        # Research: 6-period RSI with dynamic 15/85, 25/75, 30/70 thresholds
        # ============================================================================
        self.adaptive_rsi = get_adaptive_rsi(
            AdaptiveRSIConfig(
                rsi_period=6,  # Short period for crypto
                high_vol_oversold=15,  # Extreme oversold threshold
                high_vol_overbought=85,  # Extreme overbought threshold
                normal_vol_oversold=25,  # Standard oversold threshold
                normal_vol_overbought=75,  # Standard overbought threshold
                low_vol_oversold=30,  # Conservative oversold threshold
                low_vol_overbought=70,  # Conservative overbought threshold
                high_volatility_threshold=3.0,  # ATR > 3% = high volatility
                low_volatility_threshold=1.0,  # ATR < 1% = low volatility
                use_trend_filter=True,  # Filter signals with trend
                trend_ema_period=50,  # 50-period EMA for trend
            )
        )

        # ============================================================================
        # HURST EXPONENT - Market regime detection (2025-12-02)
        # Research: H > 0.55 trending, H < 0.45 mean-reverting
        # ============================================================================
        self.hurst_calculator = create_hurst_calculator(
            trending_threshold=0.55,
            mean_reversion_threshold=0.45,
            lookback_periods=[20, 50, 100],
        )

        # ============================================================================
        # LIMIT ORDER EXECUTOR - Better execution (2025-12-02)
        # Research: Saves 2-10 bps on slippage
        # ============================================================================
        self.limit_order_executor = get_limit_order_executor(
            LimitOrderConfig(
                default_offset_pct=0.05,  # 0.05% inside spread
                timeout_seconds=30,  # 30s before fallback
                use_post_only=False,  # Allow taker orders
                max_retries=2,  # Retry twice
                fallback_to_market=True,  # Fallback to market order
                aggressive_offset_pct=0.02,  # Near price for fast fill
                passive_offset_pct=0.10,  # Further for better price
            )
        )

        # ============================================================================
        # WALK FORWARD EFFICIENCY TESTER - Strategy validation (2025-12-02)
        # Research: WFE > 50% for robust strategies
        # ============================================================================
        self.wfe_tester = get_walk_forward_tester(
            WFEConfig(
                in_sample_pct=0.70,  # 70% training
                out_of_sample_pct=0.30,  # 30% testing
                min_trades_for_confidence=385,  # 95% confidence
                min_wfe_threshold=0.50,  # 50% minimum WFE
                rolling_windows=5,  # 5 walk-forward periods
            ),
            strategy_name="research_optimized",
        )

        # ============================================================================
        # REGIME STRATEGY SELECTOR - Hurst-based parameter adjustment (2025-12-02)
        # Research: Mandelbrot's Fractal Market Hypothesis
        # ============================================================================
        self.regime_strategy_selector = get_regime_strategy_selector()
        # Configures: TRENDING: 1.5x stop, 2.0x TP | MEAN_REVERTING: 0.8x stop, 1.2x TP

        # ============================================================================
        # ATR TRAILING STOP - Volatility-adjusted trailing stops (2025-12-02)
        # Research: Chandelier Exit methodology
        # ============================================================================
        self.atr_trailing_stop = get_atr_trailing_stop(
            ATRTrailingStopConfig(
                base_atr_multiplier=2.5,  # 2.5x ATR distance
                min_atr_multiplier=1.5,  # Minimum 1.5x for tight markets
                max_atr_multiplier=4.0,  # Maximum 4x for extreme volatility
                activation_profit_pct=1.0,  # Activate after 1% profit
                step_pct=0.5,  # Update when price moves 0.5%
                use_chandelier_exit=True,  # Trail from highest/lowest
            )
        )

        # ============================================================================
        # PARTIAL PROFIT TAKER - Scale-out strategy (2025-12-02)
        # Research: Professional trading best practices
        # ============================================================================
        self.partial_profit_taker = get_partial_profit_taker(
            PartialProfitConfig(
                profit_levels=[1.0, 2.0, 3.0],  # 1%, 2%, 3% profit targets
                exit_percentages=[25.0, 25.0, 25.0],  # Exit 25% at each level
                move_stop_to_breakeven_after=1,  # Breakeven after first partial
                min_position_value=10.0,  # Don't split below $10
                enabled=True,
            )
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
        logger.info(
            f"Trade Limits: max_daily={self.max_daily_trades}, reentry_cooldown={self.min_time_between_trades}s"
        )
        logger.info(f"Trading symbols: {self.symbols}")
        logger.info(
            "Hybrid Strategy: TREND-FOLLOWING + MEAN REVERSION (ADX threshold: 25.0)"
        )
        logger.info(
            f"Trend Strategy Parameters: {self.research_strategy.get_strategy_params()}"
        )

        # Log enhancement configuration
        logger.info("=" * 70)
        logger.info("RESEARCH-BACKED TRADING ENHANCEMENTS ENABLED (2025-11-30)")
        logger.info("=" * 70)
        logger.info("  Circuit Breaker: failure_threshold=5, timeout=60s")
        ks_cfg = self.kill_switch.config
        logger.info(
            f"  Kill Switch: daily_loss={ks_cfg.max_daily_loss_pct}%, "
            f"drawdown={ks_cfg.max_drawdown_pct}%, "
            f"consecutive_losses={ks_cfg.max_consecutive_losses}"
        )
        logger.info("  Slippage Manager: base=0.15%, volatile=0.30%, reject=0.50%")
        logger.info("  Execution Timer: position=15s, price=10s, trailing=15s")
        logger.info("  Order State Machine: FIX protocol style tracking")
        logger.info("=" * 70)
        logger.info("ADVANCED TRADING ENHANCEMENTS ENABLED (2025-11-30 v2)")
        logger.info("=" * 70)
        logger.info("  Advanced Position Sizer: Quarter Kelly, max=25%, ATR-based")
        logger.info("  Smart Order Executor: TWAP/VWAP/Iceberg, 5-min duration")
        logger.info("  Performance Analytics: Sharpe, Sortino, VaR@95%, CVaR")
        logger.info("=" * 70)
        logger.info("DCA MANAGER ENABLED (2025-12-02) - Research: Pionex/3Commas")
        logger.info("=" * 70)
        logger.info(f"  DCA Layers: {self.dca_manager.config.max_safety_orders}")
        logger.info(
            f"  DCA Triggers: {self.dca_manager.config.safety_order_deviation_pct}"
        )
        logger.info(
            f"  DCA Volume Scale: {self.dca_manager.config.safety_order_volume_scale}"
        )
        logger.info(f"  TP After DCA: {self.dca_manager.config.tp_after_dca_pct}%")
        logger.info("=" * 70)
        logger.info(
            "PORTFOLIO HEAT MANAGER ENABLED (2025-12-02) - Research: Hedge Fund Best Practices"
        )
        logger.info("=" * 70)
        logger.info(
            f"  Max Portfolio Heat: {self.portfolio_heat_manager.config.max_portfolio_heat_pct}%"
        )
        logger.info(
            f"  Max Per Trade Risk: {self.portfolio_heat_manager.config.max_per_trade_pct}%"
        )
        logger.info(
            f"  Max Correlated Exposure: {self.portfolio_heat_manager.config.max_correlated_exposure_pct}%"
        )
        logger.info(
            "  Heat Levels: LOW(<4%) MODERATE(<6%) ELEVATED(<8%) HIGH(>8%) CRITICAL(>10%)"
        )
        logger.info("=" * 70)
        logger.info(
            "ADAPTIVE RSI ENABLED (2025-12-02) - Research: 6-period with dynamic thresholds"
        )
        logger.info("=" * 70)
        logger.info(f"  RSI Period: {self.adaptive_rsi.config.rsi_period}")
        logger.info(
            f"  High Vol Thresholds: ({self.adaptive_rsi.config.high_vol_oversold}, {self.adaptive_rsi.config.high_vol_overbought})"
        )
        logger.info(
            f"  Normal Thresholds: ({self.adaptive_rsi.config.normal_vol_oversold}, {self.adaptive_rsi.config.normal_vol_overbought})"
        )
        logger.info(
            f"  Low Vol Thresholds: ({self.adaptive_rsi.config.low_vol_oversold}, {self.adaptive_rsi.config.low_vol_overbought})"
        )
        logger.info(f"  Trend Filter: {self.adaptive_rsi.config.use_trend_filter}")
        logger.info("=" * 70)
        logger.info(
            "HURST EXPONENT ENABLED (2025-12-02) - Research: Market Regime Detection"
        )
        logger.info("=" * 70)
        logger.info(
            f"  Trending Threshold: > {self.hurst_calculator.config.trending_threshold}"
        )
        logger.info(
            f"  Mean Reversion Threshold: < {self.hurst_calculator.config.mean_reversion_threshold}"
        )
        logger.info(
            f"  Lookback Periods: {self.hurst_calculator.config.lookback_periods}"
        )
        logger.info("=" * 70)
        logger.info(
            "LIMIT ORDER EXECUTOR ENABLED (2025-12-02) - Research: 2-10 bps slippage savings"
        )
        logger.info("=" * 70)
        logger.info(
            f"  Default Offset: {self.limit_order_executor.config.default_offset_pct}%"
        )
        logger.info(f"  Timeout: {self.limit_order_executor.config.timeout_seconds}s")
        logger.info(
            f"  Fallback to Market: {self.limit_order_executor.config.fallback_to_market}"
        )
        logger.info("=" * 70)
        logger.info(
            "WALK FORWARD TESTER ENABLED (2025-12-02) - Research: Strategy Validation"
        )
        logger.info("=" * 70)
        logger.info(f"  In-Sample: {self.wfe_tester.config.in_sample_pct:.0%}")
        logger.info(f"  Out-of-Sample: {self.wfe_tester.config.out_of_sample_pct:.0%}")
        logger.info(
            f"  Min WFE Threshold: {self.wfe_tester.config.min_wfe_threshold:.0%}"
        )
        logger.info(
            f"  Min Trades for Confidence: {self.wfe_tester.config.min_trades_for_confidence}"
        )
        logger.info("=" * 70)
        logger.info(
            "REGIME STRATEGY SELECTOR ENABLED (2025-12-02) - Research: Mandelbrot's FMH"
        )
        logger.info("=" * 70)
        logger.info("  TRENDING: SL mult=1.5x, TP mult=2.0x, pos mult=1.0x")
        logger.info("  MEAN_REVERTING: SL mult=0.8x, TP mult=1.2x, pos mult=0.9x")
        logger.info("  RANDOM_WALK: SL mult=1.0x, TP mult=1.0x, pos mult=0.5x")
        logger.info("=" * 70)
        logger.info(
            "ATR TRAILING STOP ENABLED (2025-12-02) - Research: Chandelier Exit"
        )
        logger.info("=" * 70)
        logger.info(
            f"  Base ATR Multiplier: {self.atr_trailing_stop.config.base_atr_multiplier}x"
        )
        logger.info(
            f"  Min/Max Multipliers: {self.atr_trailing_stop.config.min_atr_multiplier}x - {self.atr_trailing_stop.config.max_atr_multiplier}x"
        )
        logger.info(
            f"  Activation Profit: {self.atr_trailing_stop.config.activation_profit_pct}%"
        )
        logger.info(f"  Step Update: {self.atr_trailing_stop.config.step_pct}%")
        logger.info(
            f"  Chandelier Exit: {self.atr_trailing_stop.config.use_chandelier_exit}"
        )
        logger.info("=" * 70)
        logger.info(
            "PARTIAL PROFIT TAKER ENABLED (2025-12-02) - Research: Scale-Out Strategy"
        )
        logger.info("=" * 70)
        logger.info(
            f"  Profit Levels: {self.partial_profit_taker.config.profit_levels}%"
        )
        logger.info(
            f"  Exit Percentages: {self.partial_profit_taker.config.exit_percentages}%"
        )
        logger.info(
            f"  Breakeven After: {self.partial_profit_taker.config.move_stop_to_breakeven_after} partial(s)"
        )
        logger.info(
            f"  Min Position Value: ${self.partial_profit_taker.config.min_position_value}"
        )
        logger.info("=" * 70)

    async def start(self):
        """Start the automated trading loop"""
        if self.is_running:
            logger.warning("AutoTrader is already running")
            return False

        logger.info("=" * 60)
        logger.info("STARTING AUTOMATED TRADING LOOP")
        logger.info(f"  Symbols: {self.symbols}")
        logger.info(f"  Interval: {self.interval}m")
        logger.info(f"  Strategy Mode: {self.strategy_mode.value}")
        logger.info(
            f"  ML Predictions: {'ENABLED (Phase 3)' if self.enable_ml else 'DISABLED'}"
        )
        logger.info(f"  Volume Profile: {'ENABLED' if self.enable_vp else 'DISABLED'}")
        logger.info(
            f"  Market Regime: {'ENABLED' if self.enable_market_regime else 'DISABLED'}"
        )
        logger.info("=" * 60)
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

    def _update_vol_estimator(self, symbol: str, current_price: float) -> None:
        """
        Feed the vol-parity estimator one (symbol, ts, close) sample.

        No-op when ENABLE_VOL_TARGETING is False. Deduped by hour boundary
        so the trading loop's sub-bar polling collapses to one bar per hour
        — keeps the estimator's annualisation factor (sqrt(8760)) honest.
        """
        if self.vol_estimator is None:
            return
        if current_price is None or current_price <= 0:
            return
        hour_key = datetime.now().replace(minute=0, second=0, microsecond=0)
        if self._vol_last_hour.get(symbol) == hour_key:
            return
        self.vol_estimator.update(symbol, hour_key, current_price)
        self._vol_last_hour[symbol] = hour_key

    async def _trading_loop(self):
        """Main trading loop - runs continuously until stopped"""
        logger.info("Automated trading loop started")
        logger.info(f"Strategy Mode: {self.strategy_mode.value}")
        logger.info("Position monitoring enabled: trailing stops + partial exits")
        logger.info(
            "Research-backed enhancements: Circuit Breaker, Kill Switch, Slippage Manager"
        )

        # Initialize kill switch with starting balance
        paper_engine = get_paper_engine()
        starting_balance = paper_engine.get_balance()
        self.kill_switch.initialize_balance(float(starting_balance))

        # Detect broken EMERGENCY_STOP bind-mount at loop start.
        # Docker auto-creates a *directory* at the mount point if the host file
        # was missing at compose-up time. Path.is_file() then returns False
        # forever, silently disabling the operator kill switch. Surface this
        # state loudly so the operator can fix the mount before relying on it.
        if self.emergency_stop_file.exists() and not self.emergency_stop_file.is_file():
            try:
                from app.core.metrics import risk_limit_breaches_total

                risk_limit_breaches_total.labels(
                    breach_type="emergency_stop_mount_broken"
                ).inc()
            except Exception:
                pass
            logger.critical(
                f"EMERGENCY_STOP mount is broken: {self.emergency_stop_file} exists but "
                f"is not a regular file (likely a directory created by Docker when the host "
                f"file was missing at compose-up). Kill switch is non-functional. To fix: "
                f"stop trading-engine, on host run `rmdir EMERGENCY_STOP && touch EMERGENCY_STOP`, "
                f"then `docker compose up -d --force-recreate trading-engine api-gateway`."
            )

        while self.is_running:
            try:
                # ================================================================
                # STEP 0a: FILE-BASED EMERGENCY STOP (operator kill switch)
                # ================================================================
                # Cheap stat check; out-ranks balance kill switch, signal fetch,
                # and order submit. Uses is_file() (not exists()) to handle the
                # WSL bind-mount edge case where Docker may create a directory at
                # the mount point if the host file is absent.
                self.emergency_stop_last_checked = datetime.now()
                if self.emergency_stop_file.is_file():
                    if not self.emergency_stop_active:
                        logger.critical(
                            f"EMERGENCY_STOP file detected at {self.emergency_stop_file} - "
                            f"halting auto-trader. Open positions left for operator review. "
                            f"Delete the file and restart the service to resume."
                        )
                        self.emergency_stop_active = True
                    self.is_running = False
                    break
                elif self.emergency_stop_active:
                    logger.info(
                        f"EMERGENCY_STOP file no longer present at {self.emergency_stop_file} - "
                        f"clearing stale emergency_stop_active flag."
                    )
                    self.emergency_stop_active = False

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
                            elif self.strategy_mode == StrategyMode.GRID_TRADING:
                                # Use Grid Trading strategy (Phase 2.3 - 2025-12-08)
                                await self._check_and_trade_grid(symbol)
                            elif self.strategy_mode == StrategyMode.ENSEMBLE:
                                # Combined RSI + multi-indicator + mean-reversion with performance weighting (2026-04-25)
                                await self._check_and_trade_ensemble(symbol)
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
                logger.warning(
                    f"[HYBRID] Trading halted due to risk limits for {symbol}"
                )
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
                if hasattr(indicator_signal, "metadata") and indicator_signal.metadata:
                    if "current_price" in indicator_signal.metadata:
                        current_price = float(
                            indicator_signal.metadata["current_price"]
                        )
                        break

            if not current_price:
                logger.warning(f"[HYBRID] No current price found for {symbol}")
                return

            self._update_vol_estimator(symbol, current_price)

            # Get paper trading engine for balance
            paper_engine = get_paper_engine()
            balance = paper_engine.get_balance()

            # Generate hybrid strategy signal (auto-switches between trend/mean reversion)
            trade_setup = self.hybrid_strategy.generate_signal(
                indicators=signal.indicators,
                current_price=current_price,
                capital=float(balance),
            )

            research_action = trade_setup.action.value if trade_setup else "HOLD"
            research_confidence = trade_setup.confidence if trade_setup else 0.0

            # Log both signals
            logger.info(
                f"[HYBRID] Standard: {standard_action} ({standard_confidence:.2%})"
            )
            logger.info(
                f"[HYBRID] Research: {research_action} ({research_confidence:.2%})"
            )

            # Check for agreement
            if standard_action == research_action and standard_action in [
                "BUY",
                "SELL",
            ]:
                if meets_requirements and trade_setup:
                    logger.info(
                        f"[HYBRID] AGREEMENT: Both strategies say {standard_action}"
                    )
                    await self._execute_trade_with_setup(symbol, trade_setup)
                    self.research_trades += 1
                    self.standard_trades += 1
                else:
                    logger.info(
                        f"[HYBRID] Agreement on {standard_action} but requirements not met"
                    )
                    self.total_trades_rejected += 1
            else:
                logger.info(
                    f"[HYBRID] DISAGREEMENT: Standard={standard_action}, Research={research_action}"
                )
                logger.info(f"[HYBRID] Holding position for {symbol}")

        except Exception as e:
            logger.error(
                f"[HYBRID] Error checking signal for {symbol}: {e}", exc_info=True
            )

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
                    symbol=symbol, interval=self.interval
                )
                # Track regime counts
                self.regime_counts[regime_analysis.regime] += 1

                # Log regime information
                self._log_market_regime(symbol, regime_analysis)

            # Get aggregated signal with appropriate enhancements
            # Phase 3 adds ML predictions, VP analysis, and sentiment
            aggregator = await get_aggregator()

            if self.enable_ml:
                # Phase 3: Use ML-enhanced signals (Technical 40% + ML 30% + Sentiment 15% + MTF 15%)
                logger.info(f"Using ML-ENHANCED signal aggregation for {symbol}")
                signal = await aggregator.get_trading_signal_enhanced(
                    symbol=symbol, interval=self.interval, use_phase3=True
                )
            elif self.enable_vp:
                # Use VP-enhanced signals (Phase 3 - VP only)
                signal = await aggregator.get_trading_signal_with_vp(
                    symbol=symbol,
                    primary_interval=self.interval,
                    timeframes=["15", self.interval, "240"],
                    enable_vp=True,
                    vp_lookback=100,
                    regime_analysis=regime_analysis,
                )
            else:
                # Use multi-timeframe only (Phase 2)
                signal = await aggregator.get_trading_signal_multi_timeframe(
                    symbol=symbol,
                    primary_interval=self.interval,
                    timeframes=["15", self.interval, "240"],  # Short, medium, long-term
                    regime_analysis=regime_analysis,
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
                logger.info(
                    f"   Strategy: {regime_data.get('strategy_recommendation', 'N/A')}"
                )

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
                logger.warning(
                    f"[RESEARCH] Trading halted due to risk limits for {symbol}"
                )
                return

            # Get aggregated signal with ML enhancement if enabled
            aggregator = await get_aggregator()
            if self.enable_ml:
                # Phase 3: Use ML-enhanced signals (Technical 40% + ML 30% + Sentiment 15% + MTF 15%)
                logger.info(
                    f"[RESEARCH] Using ML-ENHANCED signal aggregation for {symbol}"
                )
                signal = await aggregator.get_trading_signal_enhanced(
                    symbol=symbol, interval=self.interval, use_phase3=True
                )
            else:
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
                if hasattr(indicator_signal, "metadata") and indicator_signal.metadata:
                    if "current_price" in indicator_signal.metadata:
                        current_price = float(
                            indicator_signal.metadata["current_price"]
                        )
                        break

            if not current_price:
                logger.warning(f"[RESEARCH] No current price found for {symbol}")
                return

            self._update_vol_estimator(symbol, current_price)

            # Get paper trading engine for balance
            paper_engine = get_paper_engine()
            balance = paper_engine.get_balance()

            # Generate hybrid strategy signal (auto-switches between trend/mean reversion)
            trade_setup = self.hybrid_strategy.generate_signal(
                indicators=signal.indicators,
                current_price=current_price,
                capital=float(balance),
            )

            if not trade_setup:
                logger.info(
                    f"[RESEARCH] No valid trade setup for {symbol} (insufficient indicator alignment)"
                )
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

            # ================================================================
            # MULTI-TIMEFRAME ALIGNMENT CHECK (2025-12-01)
            # Only trade when 15m/60m/4h timeframes agree to reduce false signals
            # ================================================================
            mtf_passed = True
            mtf_alignment_score = 0.0
            mtf_consensus = "N/A"

            # Get settings for MTF configuration
            from app.config import get_settings

            settings = get_settings()

            if settings.enable_multi_timeframe and settings.mtf_require_alignment:
                # Check for MTF metadata in signal
                mtf_data = (
                    signal.metadata.get("multi_timeframe", {})
                    if signal.metadata
                    else {}
                )

                if mtf_data:
                    mtf_alignment_score = mtf_data.get("alignment_score", 0) or 0
                    mtf_consensus = mtf_data.get("consensus_signal", "N/A")
                    min_alignment = settings.mtf_min_alignment_score

                    logger.info(
                        f"  [MTF] Alignment Score: {mtf_alignment_score:.1f}% (min: {min_alignment}%)"
                    )
                    logger.info(f"  [MTF] Consensus: {mtf_consensus}")
                    logger.info(
                        f"  [MTF] Timeframes: 15m={mtf_data.get('short_term', 'N/A')}, "
                        f"60m={mtf_data.get('medium_term', 'N/A')}, 4h={mtf_data.get('long_term', 'N/A')}"
                    )

                    # Check if signal action matches MTF consensus
                    action_matches_consensus = (
                        mtf_consensus == trade_setup.action.value
                        or mtf_consensus == "HOLD"  # HOLD is neutral, allow trade
                    )

                    if mtf_alignment_score < min_alignment:
                        logger.warning(
                            f"  [MTF REJECTED] Alignment {mtf_alignment_score:.1f}% < {min_alignment}% threshold"
                        )
                        mtf_passed = False
                    elif not action_matches_consensus:
                        logger.warning(
                            f"  [MTF REJECTED] Signal {trade_setup.action.value} conflicts with MTF consensus {mtf_consensus}"
                        )
                        mtf_passed = False
                    else:
                        logger.info(
                            f"  [MTF PASSED] Timeframes aligned for {trade_setup.action.value}"
                        )
                else:
                    logger.info(
                        "  [MTF] No MTF data available - proceeding without MTF filter"
                    )

            logger.info("=" * 70)

            # Execute trade if action is BUY or SELL and MTF alignment passes
            if trade_setup.action.value in ["BUY", "SELL"] and mtf_passed:
                await self._execute_trade_with_setup(symbol, trade_setup)
                self.research_trades += 1
            elif trade_setup.action.value in ["BUY", "SELL"] and not mtf_passed:
                self.total_trades_rejected += 1
                logger.info(
                    f"[RESEARCH] Trade REJECTED for {symbol} - MTF alignment failed"
                )
            else:
                logger.info(f"[RESEARCH] Holding position for {symbol}")

        except Exception as e:
            logger.error(
                f"[RESEARCH] Error checking signal for {symbol}: {e}", exc_info=True
            )

    def _check_daily_trade_limit(self) -> bool:
        """
        Check if daily trade limit has been reached

        Returns:
            True if can trade, False if limit reached
        """
        # Reset counter if new day
        today = datetime.now().date()
        if today != self.daily_trades_date:
            logger.info(
                f"New trading day - resetting daily trade count from {self.daily_trades_count}"
            )
            self.daily_trades_count = 0
            self.daily_trades_date = today

        if self.daily_trades_count >= self.max_daily_trades:
            logger.info(
                f"Daily trade limit reached: {self.daily_trades_count}/{self.max_daily_trades}"
            )
            return False
        return True

    def _check_symbol_cooldown(self, symbol: str) -> bool:
        """
        Check if symbol is in cooldown period after last trade

        Args:
            symbol: Trading symbol to check

        Returns:
            True if can trade (no cooldown or cooldown expired), False if in cooldown

        Two cooldowns are checked:
        1. General post-trade cooldown (min_time_between_trades) — short, applies
           to every close regardless of outcome.
        2. Stop-loss cooldown (sl_cooldown_seconds, default 4h) — long, applies
           only after an SL exit. Counters the whipsaw re-entry pattern. Set
           by _record_sl_hit() from the close-position paths.
        """
        # Stop-loss cooldown (2026-05-15) — checked unconditionally; takes
        # precedence over reentry toggle because the whole point is to *prevent*
        # immediate same-symbol reentry after an SL hit.
        sl_until = self._sl_cooldown_until.get(symbol)
        if sl_until is not None:
            now = datetime.now()
            if now < sl_until:
                remaining = (sl_until - now).total_seconds()
                logger.info(
                    f"{symbol} in SL cooldown: {remaining:.0f}s remaining "
                    f"(of {self.sl_cooldown_seconds}s)"
                )
                return False
            # Expired — clean up so the registry doesn't grow unbounded.
            self._sl_cooldown_until.pop(symbol, None)

        if not self.allow_same_symbol_reentry:
            return True  # No cooldown tracking if reentry disabled

        last_trade_time = self.last_trade_time_per_symbol.get(symbol)
        if last_trade_time:
            elapsed = (datetime.now() - last_trade_time).total_seconds()
            if elapsed < self.min_time_between_trades:
                logger.debug(
                    f"{symbol} in cooldown: {elapsed:.0f}s < {self.min_time_between_trades}s"
                )
                return False
        return True

    def _record_sl_hit(self, symbol: str, reason: str) -> None:
        """
        Register a stop-loss cooldown for a symbol.

        Called from close-position paths when the exit reason indicates a
        stop-loss event. The cooldown blocks new entries on this symbol for
        sl_cooldown_seconds via _check_symbol_cooldown().
        """
        from datetime import timedelta

        until = datetime.now() + timedelta(seconds=self.sl_cooldown_seconds)
        self._sl_cooldown_until[symbol] = until
        logger.warning(
            f"[SL_COOLDOWN] {symbol}: cooldown armed for {self.sl_cooldown_seconds}s "
            f"(until {until.isoformat(timespec='seconds')}) — reason: {reason}"
        )

    def _record_trade(self, symbol: str):
        """Record a trade for daily limit and cooldown tracking"""
        self.daily_trades_count += 1
        self.last_trade_time_per_symbol[symbol] = datetime.now()
        logger.info(
            f"Trade recorded: {symbol} | Daily count: {self.daily_trades_count}/{self.max_daily_trades}"
        )

    async def _passes_min_notional(
        self,
        symbol: str,
        quantity,
        price,
        balance,
    ):
        """Pre-submit gate: reject orders below the exchange's min-notional.

        Returns ``(True, None)`` to proceed, ``(False, reason)`` to reject.
        ``reason`` is one of ``"min_qty"`` / ``"min_notional"`` and matches
        the Prometheus counter label.

        Fail-open: if the instruments cache has no entry for the symbol
        (connector outage at boot, symbol not yet refreshed), this returns
        ``(True, None)`` with a WARN log — refusing to trade because the
        metadata service is down would be a worse failure mode than letting
        the order through. Paper engine fills any quantity; LIVE mode would
        surface Bybit's own rejection.

        We deliberately do NOT auto-upround the quantity here. On a $100
        balance × 2% per-trade cap, forcing a $5 alt min-notional would
        silently breach the risk cap (5% notional). Surface the reject so
        the operator sees the cap configuration is incompatible with
        live-mode minimums.

        PAPER mode short-circuit: paper-engine fills any quantity
        deterministically — exchange minimums don't apply. Enforcing the
        gate in PAPER would zero out trading on small paper balances
        ($100 × 2% = $2 cap, all crypto mins above). Gate's purpose is
        LIVE-mode protection; in PAPER we let the order through and rely
        on the paper-engine to fill it.
        """
        from decimal import Decimal as _Decimal

        try:
            from app.config import get_settings

            if get_settings().trading_mode != "LIVE":
                return True, None
        except Exception as e:
            logger.warning(
                f"min-notional gate: could not read trading_mode ({e!r}), enforcing gate"
            )

        # Normalise call-site types (Decimal vs float vs int) to Decimal once.
        try:
            qty_d = _Decimal(str(quantity))
            price_d = _Decimal(str(price))
            balance_d = _Decimal(str(balance))
        except Exception:
            # Defensive — bad inputs shouldn't crash the gate.
            logger.warning(
                f"min-notional gate: could not parse qty/price/balance for {symbol}, allowing"
            )
            return True, None

        # Deferred import: avoids a circular at module load and lets tests
        # monkeypatch app.main.get_instruments_cache cleanly.
        try:
            from app.main import get_instruments_cache
        except Exception as e:
            logger.warning(
                f"min-notional gate: instruments cache import failed for {symbol} ({e!r}), allowing"
            )
            return True, None

        try:
            spec = await get_instruments_cache().get(symbol)
        except Exception as e:
            logger.warning(
                f"min-notional gate: cache.get({symbol}) raised {e!r}, allowing"
            )
            return True, None

        if spec is None:
            logger.warning(
                f"min-notional cache miss for {symbol}, allowing trade "
                f"(connector outage or symbol unlisted)"
            )
            return True, None

        notional = qty_d * price_d
        cap = balance_d * _Decimal("0.02")

        if qty_d < spec.min_order_qty:
            try:
                from app.core.metrics import trades_rejected_min_notional_total

                trades_rejected_min_notional_total.labels(
                    symbol=symbol, reason="min_qty"
                ).inc()
            except Exception:
                pass
            logger.info(
                f"rejecting {symbol}: qty {qty_d} below min {spec.min_order_qty} "
                f"(notional ${notional:.2f}, balance ${balance_d:.2f}, "
                f"cap 2% = ${cap:.2f})"
            )
            return False, "min_qty"

        if spec.min_notional is not None and notional < spec.min_notional:
            try:
                from app.core.metrics import trades_rejected_min_notional_total

                trades_rejected_min_notional_total.labels(
                    symbol=symbol, reason="min_notional"
                ).inc()
            except Exception:
                pass
            logger.info(
                f"rejecting {symbol}: notional ${notional:.2f} below min "
                f"${spec.min_notional} (qty {qty_d}, balance ${balance_d:.2f}, "
                f"cap 2% = ${cap:.2f})"
            )
            return False, "min_notional"

        return True, None

    async def _claim_open_slot(self, symbol: str) -> bool:
        """
        Atomically claim a per-symbol open slot. Prevents twin positions when
        two signal paths race past the position_mgr.get_open_positions()
        existence check before either commits its row.

        Returns False if (a) another open is already in flight for this symbol
        or (b) we just opened one within the cooldown window.
        """
        async with self._opening_lock:
            if symbol in self._opening_symbols:
                logger.info(
                    f"[DEDUP] {symbol}: open already in flight, skipping duplicate"
                )
                self.total_trades_rejected += 1
                return False
            last = self._last_open_at.get(symbol)
            if last is not None:
                elapsed = (datetime.now() - last).total_seconds()
                if elapsed < self.open_cooldown_seconds:
                    logger.info(
                        f"[DEDUP] {symbol}: open cooldown "
                        f"{elapsed:.1f}s/{self.open_cooldown_seconds}s, "
                        f"skipping duplicate"
                    )
                    self.total_trades_rejected += 1
                    return False
            self._opening_symbols.add(symbol)
            return True

    def _release_open_slot(self, symbol: str, *, opened: bool) -> None:
        """Release the slot. Stamp last_open_at iff a position was opened."""
        self._opening_symbols.discard(symbol)
        if opened:
            self._last_open_at[symbol] = datetime.now()

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
        # Concurrent-open dedup gate (2026-05-06). MUST be first — otherwise
        # twin signals race past has_position before either persists.
        if not await self._claim_open_slot(symbol):
            return
        opened = False
        try:
            # ================================================================
            # PRE-TRADE CHECKS (Enhanced 2025-11-30)
            # ================================================================

            # Check kill switch first
            if self.kill_switch.should_halt_trading():
                logger.warning(
                    f"[RESEARCH] Kill switch active, rejecting trade for {symbol}"
                )
                self.total_trades_rejected += 1
                return

            # ================================================================
            # PORTFOLIO HEAT CHECK (2025-12-02)
            # Block trades if portfolio heat is too high
            # ================================================================
            paper_engine = get_paper_engine()
            current_equity = float(paper_engine.get_balance())

            # Calculate proposed risk for this trade
            proposed_risk_pct = (
                trade_setup.position_size_pct
                * 100
                * (settings.default_stop_loss_pct / 100)
            )  # Risk = position size * stop distance

            can_trade, heat_reason, heat_multiplier = (
                self.portfolio_heat_manager.can_open_trade(
                    symbol=symbol,
                    proposed_risk_pct=proposed_risk_pct,
                    equity=current_equity,
                )
            )

            if not can_trade:
                logger.warning(f"[HEAT] Trade BLOCKED for {symbol}: {heat_reason}")
                self.total_trades_rejected += 1
                return

            # ================================================================
            # CORRELATION-BASED POSITION SIZING (2025-12-02)
            # Get combined multiplier: heat + correlation adjustments
            # ================================================================
            combined_multiplier, size_breakdown = (
                self.portfolio_heat_manager.get_combined_size_multiplier(
                    symbol=symbol, equity=current_equity
                )
            )

            # Log heat and correlation status
            heat_status = self.portfolio_heat_manager.get_summary_dict()
            logger.info(
                f"[HEAT] Trade ALLOWED: {symbol} | "
                f"Current heat: {heat_status['total_heat_pct']:.1f}%/{heat_status['limits']['max_portfolio_heat']}% | "
                f"Level: {heat_status['heat_level']}"
            )
            logger.info(
                f"[CORRELATION] Size adjustment: heat={size_breakdown['heat_multiplier']:.0%} x "
                f"corr={size_breakdown['correlation_multiplier']:.0%} ({size_breakdown['correlation_level']}) = "
                f"{combined_multiplier:.0%} final"
            )

            # Use combined multiplier instead of just heat multiplier
            heat_multiplier = combined_multiplier

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

            # ================================================================
            # CRITICAL: Enforce Trade Side Restrictions (Added 2026-01-16)
            # ================================================================
            # Problem: SHORT trading disabled in config but was still executing
            # Impact: -$14.33 loss from SOLUSDT SHORT with 0% win rate
            # Solution: Validate trade side against allowed_trade_sides config
            # ================================================================
            side = "LONG" if action == "BUY" else "SHORT"

            # Check #1: Validate side is in allowed_trade_sides list
            if side not in self.settings.allowed_trade_sides:
                logger.warning(
                    f"[RISK_GATE] ❌ Trade side {side} NOT in allowed_trade_sides: "
                    f"{self.settings.allowed_trade_sides} | Symbol: {symbol} | "
                    f"Action: {action} | Confidence: {trade_setup.confidence:.2%} - REJECTING"
                )
                self.total_trades_rejected += 1
                return

            # Check #2: Additional backward compatibility check for SHORT trading flag
            if side == "SHORT" and not self.settings.short_trading_enabled:
                logger.warning(
                    f"[RISK_GATE] ❌ SHORT trading DISABLED (short_trading_enabled=False) | "
                    f"Symbol: {symbol} | Action: {action} | Confidence: {trade_setup.confidence:.2%} - REJECTING"
                )
                self.total_trades_rejected += 1
                return

            logger.info(
                f"[RISK_GATE] ✅ Trade side validation PASSED | "
                f"Side: {side} | Allowed: {self.settings.allowed_trade_sides}"
            )

            # ================================================================
            # FUNDING-RATE GATE (T2.3, 2026-04-30) — perp-only entry filter.
            # Cheap gate: runs before allocation/sizing so we don't compute
            # quantities for trades that won't survive the gate. Fail-open
            # on any fetch error; gate disabled in PAPER mode.
            # ================================================================
            if self._funding_gate_config is not None and trading_mode == "LIVE":
                if self._funding_client is None:
                    self._funding_client = FundingRateClient(
                        connector_base_url=self.settings.bybit_connector_url,
                        config=self._funding_gate_config,
                    )
                rate = await self._funding_client.get_latest_rate(symbol)
                decision = funding_gate_decision(
                    rate_per_period=rate,
                    is_long=(side == "LONG"),
                    config=self._funding_gate_config,
                )
                if not decision.allow:
                    logger.warning(
                        f"[FUNDING_GATE] ❌ Rejecting {side} on {symbol}: {decision.reason}"
                    )
                    self.total_trades_rejected += 1
                    return
                logger.info(f"[FUNDING_GATE] ✅ {symbol} {side}: {decision.reason}")

            logger.info(f"[{trading_mode}] Executing {action} trade for {symbol}")

            # ================================================================
            # SLIPPAGE CHECK (Enhanced 2025-11-30)
            # ================================================================
            # Check if limit order should be used based on order value
            position_value_estimate = (
                trade_setup.entry_price * trade_setup.position_size_pct * 10000
            )  # Rough estimate
            should_use_limit, limit_reason = (
                self.slippage_manager.should_use_limit_order(
                    position_value_estimate, symbol
                )
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
                # Use paper trading engine for simulation (already fetched above)
                trading_engine = paper_engine
                balance = current_equity
                logger.info(f"[PAPER] Simulated balance: ${balance:.2f}")

            # Check if we already have an open position for this symbol
            open_positions = position_mgr.get_open_positions()
            has_position = any(p.symbol == symbol for p in open_positions)

            if has_position:
                logger.info(
                    f"[RESEARCH] Already have open position for {symbol}, skipping"
                )
                self.total_trades_rejected += 1
                return

            # =================================================================
            # SYMBOL-SPECIFIC ALLOCATION (2025-12-06)
            # Apply SOL-heavy allocation strategy based on backtest results
            # - SOLUSDT: 60% (profitable +0.66%)
            # - BNBUSDT: 20% (marginal -0.14%)
            # - ADAUSDT: 20% (marginal -0.48%)
            #
            # CRITICAL FIX 2025-12-15: Use initial balance for allocation calculations
            # instead of current balance so all symbols get consistent allocation
            # regardless of how many positions have been opened
            # =================================================================
            symbol_allocation = self.settings.symbol_allocations.get(
                symbol, 1.0 / len(self.settings.trading_symbols)
            )

            # Use initial balance for paper trading allocations, current balance for live trading
            allocation_base = (
                self.settings.paper_initial_balance
                if trading_mode == "PAPER"
                else balance
            )
            allocated_capital = float(allocation_base) * symbol_allocation

            # =================================================================
            # LEVERAGE CALCULATION - BYBIT STYLE (Added 2025-12-15)
            # =================================================================
            # Formula: Initial Margin = Position Value / Leverage
            # Example: $100 position with 10x leverage requires only $10 margin
            #
            # allocated_capital = margin allocated to this symbol (e.g., $10)
            # With 10x leverage: Can control $10 × 10 = $100 position
            # Margin used: $100 / 10 = $10 ✓
            # =================================================================
            leverage = 1.0  # Default no leverage
            if self.settings.leverage_enabled:
                leverage = max(
                    self.settings.min_leverage,
                    min(self.settings.default_leverage, self.settings.max_leverage),
                )

            # Calculate leveraged position size
            # With leverage: margin × leverage = position size
            # Without leverage: margin = position size (leverage = 1.0)
            leveraged_position_value = allocated_capital * leverage

            # Apply heat multiplier to reduce size during high heat
            # This reduces BOTH the position size AND the margin required
            position_value = leveraged_position_value * heat_multiplier
            margin_required = position_value / leverage
            quantity = position_value / trade_setup.entry_price

            logger.info(
                f"[RESEARCH] Symbol allocation: {symbol} = {symbol_allocation:.0%} of ${allocation_base:.2f} = ${allocated_capital:.2f} margin"
            )
            if self.settings.leverage_enabled:
                logger.info(
                    f"[LEVERAGE] ${allocated_capital:.2f} margin × {leverage:.0f}x leverage = ${leveraged_position_value:.2f} position size"
                )
            logger.info(
                f"[RESEARCH] Position sizing: ${leveraged_position_value:.2f} * {heat_multiplier:.0%} heat adj "
                f"= ${position_value:.2f} position ({quantity:.4f} units @ ${trade_setup.entry_price:.2f})"
            )
            logger.info(
                f"[MARGIN] Margin required: ${margin_required:.2f} (Position: ${position_value:.2f} / Leverage: {leverage:.0f}x)"
            )

            # ================================================================
            # VOL PARITY OVERLAY (T1.2 chunk 3, default off)
            # ================================================================
            # Outer overlay above the per-trade cap. With cap_multiplier=1.0
            # (default) this is downside-only: shrinks positions when realised
            # vol exceeds target, leaves baseline alone when below — never
            # grows past baseline so the cap REJECT below stays intact. With
            # cap_multiplier=3.0 the user can opt into Carver-style symmetric
            # vol targeting; in that case vol parity may exceed the per-trade
            # cap and the existing REJECT idiom kicks in (still safe — just
            # surfaces a tension to investigate).
            if self.vol_estimator is not None:
                realized_vol = self.vol_estimator.get_realized_vol_annualized(symbol)
                pre_parity_value = position_value
                position_value = float(
                    vol_parity_size(
                        Decimal(str(position_value)),
                        realized_vol,
                        VolParitySizingConfig(
                            target_vol_annualised=self.settings.vol_target_annualised,
                            cap_multiplier=self.settings.vol_target_cap_multiplier,
                        ),
                    )
                )
                if abs(position_value - pre_parity_value) > 1e-6:
                    rv_str = (
                        f"{realized_vol:.2%}"
                        if realized_vol is not None
                        else "warming-up"
                    )
                    logger.info(
                        f"[VOL_PARITY] {symbol}: realised_vol={rv_str}, "
                        f"baseline=${pre_parity_value:.2f} → post=${position_value:.2f} "
                        f"(target={self.settings.vol_target_annualised:.0%})"
                    )
                    margin_required = position_value / leverage
                    quantity = position_value / trade_setup.entry_price

            # ================================================================
            # PER-TRADE CAP (MAX_RISK_PER_TRADE, default 0.02)
            # ================================================================
            # CLAUDE.md historically claimed "max 2% capital per trade", but
            # the sizing path above (symbol_allocation × leverage × heat) had
            # no runtime check — a 30% allocation × 1x leverage produced a
            # 30% trade. This gate validates the final notional against the
            # cap and rejects-and-skips (matching the kill-switch / heat /
            # daily-limit idiom) so the breach is observable rather than
            # silently smoothed over by a resize.
            cap_fraction = self.settings.max_risk_per_trade
            cap_value = float(balance) * cap_fraction
            if position_value > cap_value:
                from app.core.metrics import risk_limit_breaches_total

                risk_limit_breaches_total.labels(breach_type="position_size").inc()
                logger.critical(
                    f"[RISK_GATE] PER_TRADE_CAP BREACH | symbol={symbol} "
                    f"attempted=${position_value:.2f} cap=${cap_value:.2f} "
                    f"({cap_fraction:.1%} of ${float(balance):.2f}) "
                    f"leverage={leverage:.1f}x allocation={symbol_allocation:.0%} "
                    f"- REJECTING. Reduce symbol_allocations[{symbol}] or leverage."
                )
                self.total_trades_rejected += 1
                return

            # Min-notional / min-qty gate (added 2026-05-06).
            # Sub-cap sizing on small balances often produces qty < exchange min;
            # paper engine fills any quantity, but LIVE Bybit will reject.
            # We REJECT (not upround) — auto-upround would silently breach
            # max_risk_per_trade.
            ok, _reason = await self._passes_min_notional(
                symbol=symbol,
                quantity=quantity,
                price=trade_setup.entry_price,
                balance=balance,
            )
            if not ok:
                self.total_trades_rejected += 1
                return

            # Execute the trade
            side = OrderSide.BUY if action == "BUY" else OrderSide.SELL

            order = OrderCreate(
                symbol=symbol,
                side=side,
                type=OrderType.MARKET,
                quantity=Decimal(str(quantity)),
                strategy="research_optimized",
                # CRITICAL FIX 2025-12-07: Pass confidence for position analysis
                entry_signal_confidence=trade_setup.confidence,
            )

            # Execute through appropriate engine (paper or live).
            # T1.3: in LIVE mode, prefer_maker_orders routes the entry through
            # a PostOnly limit at best bid/ask with timeout-based fallback.
            # Paper engine has no maker/taker distinction — keep market path.
            use_maker = (
                trading_mode == "LIVE"
                and self.settings.prefer_maker_orders
                and hasattr(trading_engine, "execute_maker_order_with_fallback")
            )
            if use_maker:
                (
                    executed_order,
                    error,
                ) = await trading_engine.execute_maker_order_with_fallback(
                    order, Decimal(str(trade_setup.entry_price))
                )
            else:
                executed_order, error = await trading_engine.execute_market_order(
                    order, Decimal(str(trade_setup.entry_price))
                )

            # FIXED: Null check for executed_order (code review 2025-11-28)
            if executed_order is None:
                self.total_trades_rejected += 1
                logger.warning(
                    f"[{trading_mode}] Trade execution returned None for {symbol}: {error}"
                )
                return

            if executed_order.status == OrderStatus.FILLED:
                self.total_trades_executed += 1
                opened = True  # arm cooldown so a duplicate signal in the next 60s short-circuits
                self._record_trade(symbol)  # Track for daily limit and cooldown

                # ================================================================
                # POST-TRADE: Update Kill Switch Metrics (2025-11-30)
                # ================================================================
                # Get updated balance for kill switch tracking
                current_balance = (
                    trading_engine.get_balance()
                    if trading_mode == "PAPER"
                    else await trading_engine.get_balance()
                )
                triggered = self.kill_switch.update_metrics(
                    current_balance=float(current_balance),
                    trade_pnl=0.0,  # Will be updated on position close
                    was_loss=False,  # New position, not a loss yet
                    position_value=float(position_value),
                )
                if triggered:
                    logger.warning(
                        f"[RESEARCH] Kill switch thresholds triggered: {triggered}"
                    )

                # Record expected vs actual for slippage tracking
                # (Actual price is same as expected for market orders in simulation)
                self.slippage_manager.record_execution(
                    symbol=symbol,
                    expected_price=Decimal(str(trade_setup.entry_price)),
                    actual_price=Decimal(
                        str(trade_setup.entry_price)
                    ),  # Same for simulated market orders
                    side=action,
                    quantity=Decimal(str(quantity)),
                )

                # ================================================================
                # REGIME-BASED SL/TP ADJUSTMENT (2025-12-02)
                # Adjust stop loss and take profit based on Hurst market regime
                # TRENDING: wider SL (1.5x), larger TP (2.0x)
                # MEAN_REVERTING: tighter SL (0.8x), smaller TP (1.2x)
                # RANDOM_WALK: reduced position (0.5x)
                # ================================================================
                adjusted_sl = trade_setup.stop_loss
                adjusted_tp = trade_setup.take_profit
                regime_multiplier = 1.0

                try:
                    # Get historical prices for Hurst calculation
                    aggregator = await get_aggregator()
                    signal = await aggregator.get_trading_signal_multi_timeframe(
                        symbol=symbol,
                        primary_interval=self.interval,
                        timeframes=[self.interval],
                    )

                    # Extract price history from signal metadata if available
                    if (
                        signal
                        and signal.metadata
                        and "price_history" in signal.metadata
                    ):
                        prices = signal.metadata["price_history"]
                        if len(prices) >= 50:  # Need minimum 50 prices for Hurst
                            hurst_result = self.hurst_calculator.calculate(prices)
                            regime = hurst_result.regime

                            # Get regime-specific multipliers
                            sl_multiplier = (
                                self.regime_strategy_selector.get_stop_loss_multiplier(
                                    regime
                                )
                            )
                            tp_multiplier = self.regime_strategy_selector.get_take_profit_multiplier(
                                regime
                            )
                            regime_multiplier = self.regime_strategy_selector.get_position_size_multiplier(
                                regime
                            )

                            # Calculate SL/TP distances from entry
                            sl_distance = abs(
                                trade_setup.entry_price - trade_setup.stop_loss
                            )
                            tp_distance = abs(
                                trade_setup.take_profit - trade_setup.entry_price
                            )

                            # Adjust distances based on regime
                            adjusted_sl_distance = sl_distance * sl_multiplier
                            adjusted_tp_distance = tp_distance * tp_multiplier

                            # Apply adjustments based on trade direction
                            if action == "BUY":
                                adjusted_sl = (
                                    trade_setup.entry_price - adjusted_sl_distance
                                )
                                adjusted_tp = (
                                    trade_setup.entry_price + adjusted_tp_distance
                                )
                            else:  # SELL
                                adjusted_sl = (
                                    trade_setup.entry_price + adjusted_sl_distance
                                )
                                adjusted_tp = (
                                    trade_setup.entry_price - adjusted_tp_distance
                                )

                            logger.info(
                                f"[REGIME] Hurst={hurst_result.hurst_exponent:.3f} ({regime.value}) | "
                                f"SL: ${trade_setup.stop_loss:.2f} -> ${adjusted_sl:.2f} ({sl_multiplier:.1f}x) | "
                                f"TP: ${trade_setup.take_profit:.2f} -> ${adjusted_tp:.2f} ({tp_multiplier:.1f}x)"
                            )

                except Exception as regime_err:
                    logger.debug(
                        f"[REGIME] Could not calculate Hurst regime: {regime_err}"
                    )
                    # Use original values if Hurst calculation fails

                # ================================================================
                # CREATE PARTIAL PROFIT STATE (2025-12-02)
                # Track position for scale-out exits at 1%, 2%, 3% profit
                # ================================================================
                try:
                    partial_state = self.partial_profit_taker.create_position_state(
                        symbol=symbol,
                        entry_price=float(trade_setup.entry_price),
                        quantity=float(quantity),
                        side="LONG" if action == "BUY" else "SHORT",
                        stop_loss=float(adjusted_sl),
                    )
                    logger.info(
                        f"[PARTIAL] Profit taking initialized: {symbol} | "
                        f"Levels: {self.partial_profit_taker.config.profit_levels}% | "
                        f"Exit: {self.partial_profit_taker.config.exit_percentages}%"
                    )
                except Exception as partial_err:
                    logger.debug(
                        f"[PARTIAL] Could not create partial profit state: {partial_err}"
                    )

                # ================================================================
                # POST-TRADE: Apply ATR-Based Stops from TradeSetup (2025-12-01)
                # Enables trailing stop activation after TP1
                # ================================================================
                if executed_order.position_id:
                    try:
                        # Extract TP1/TP2/TP3 from trade_setup.partial_exits if available
                        tp1, tp2, tp3 = None, None, None
                        if trade_setup.partial_exits:
                            for exit_level in trade_setup.partial_exits:
                                if exit_level.label == "TP1":
                                    tp1 = Decimal(str(exit_level.price))
                                elif exit_level.label == "TP2":
                                    tp2 = Decimal(str(exit_level.price))
                                elif exit_level.label == "TP3":
                                    tp3 = Decimal(str(exit_level.price))

                        # Update position with ATR-based stops (using regime-adjusted values)
                        position_mgr.set_position_stops(
                            position_id=executed_order.position_id,
                            stop_loss=Decimal(str(adjusted_sl)),
                            take_profit=Decimal(str(adjusted_tp)),
                            tp1=tp1,
                            tp2=tp2,
                            tp3=tp3,
                            enable_trailing=False,  # Enabled automatically after TP1 hit
                        )

                        logger.info(
                            f"[{trading_mode}] ATR-based stops applied (regime-adjusted): "
                            f"SL=${adjusted_sl:.2f}, "
                            f"TP1=${float(tp1) if tp1 else 'N/A':.2f}, "
                            f"TP2=${float(tp2) if tp2 else 'N/A':.2f}, "
                            f"TP3=${float(tp3) if tp3 else adjusted_tp:.2f}"
                        )
                        logger.info(
                            f"[{trading_mode}] Trailing stop will activate after TP1 "
                            f"(ATR mult: {trade_setup.trailing_stop_atr_mult}x)"
                        )

                    except Exception as stop_error:
                        logger.warning(
                            f"[{trading_mode}] Failed to apply ATR stops: {stop_error}"
                        )

                logger.info(
                    f"[{trading_mode}] Trade executed successfully for {symbol}"
                )
                logger.info(
                    f"[{trading_mode}] Stops (regime-adjusted): SL=${adjusted_sl:.2f}, "
                    f"TP=${adjusted_tp:.2f}"
                )

                # ================================================================
                # CREATE DCA POSITION (2025-12-02)
                # Track position for DCA averaging if price drops
                # ================================================================
                try:
                    dca_position = self.dca_manager.create_dca_position(
                        symbol=symbol,
                        side="LONG" if action == "BUY" else "SHORT",
                        entry_price=float(trade_setup.entry_price),
                        quantity=float(quantity),
                        take_profit=float(adjusted_tp),
                        stop_loss=float(adjusted_sl),
                    )
                    logger.info(
                        f"[DCA] Position created for {symbol}: "
                        f"entry=${trade_setup.entry_price:.2f}, "
                        f"max_layers={self.dca_manager.config.max_safety_orders}"
                    )
                except Exception as dca_err:
                    logger.warning(f"[DCA] Failed to create DCA position: {dca_err}")

                # ================================================================
                # ADD TO PORTFOLIO HEAT MANAGER (2025-12-02)
                # ================================================================
                try:
                    position_risk = self.portfolio_heat_manager.calculate_position_risk(
                        symbol=symbol,
                        side="LONG" if action == "BUY" else "SHORT",
                        entry_price=float(trade_setup.entry_price),
                        quantity=float(quantity),
                        stop_loss=float(adjusted_sl),
                        current_price=float(trade_setup.entry_price),
                        equity=float(balance),
                    )
                    self.portfolio_heat_manager.add_position(position_risk)
                    new_heat = self.portfolio_heat_manager.get_summary_dict()
                    logger.info(
                        f"[HEAT] Position added to tracking: {symbol} | "
                        f"Position risk: {position_risk.risk_pct:.2f}% | "
                        f"New total heat: {new_heat['total_heat_pct']:.2f}%"
                    )
                except Exception as heat_err:
                    logger.warning(
                        f"[HEAT] Failed to add position to heat manager: {heat_err}"
                    )

                logger.info(
                    f"[{trading_mode}] Stats: Checked={self.total_signals_checked}, "
                    f"Executed={self.total_trades_executed}, "
                    f"Daily={self.daily_trades_count}/{self.max_daily_trades}, "
                    f"Rejected={self.total_trades_rejected}"
                )

                # Send trade open notification (2025-12-01)
                # Audit 2026-04-27: failures here used to be logged at debug
                # and the result dict ignored, so silent delivery failures
                # looked identical to successes. Now we inspect the dict.
                try:
                    notify_result = await self.notification_client.notify_trade_open(
                        symbol=symbol,
                        action=action,
                        quantity=float(quantity),
                        price=float(trade_setup.entry_price),
                        confidence=trade_setup.confidence,
                        stop_loss=adjusted_sl,
                        take_profit=adjusted_tp,
                    )
                    if not (
                        isinstance(notify_result, dict) and notify_result.get("success")
                    ):
                        logger.warning(
                            "Trade-open notification NOT DELIVERED for %s: %s",
                            symbol,
                            notify_result,
                        )
                except Exception as notify_err:
                    logger.warning(
                        "Trade-open notification raised for %s: %s",
                        symbol,
                        notify_err,
                    )
            else:
                self.total_trades_rejected += 1
                logger.warning(
                    f"[{trading_mode}] Trade execution failed for {symbol}: {error}"
                )

        except Exception as e:
            logger.error(
                f"[RESEARCH] Error executing trade for {symbol}: {e}", exc_info=True
            )
            self.total_trades_rejected += 1
        finally:
            # Release per-symbol open slot. `opened` is True only on the path
            # that actually persisted a fill above; every other return / raise
            # falls through with opened=False, releasing the claim without
            # arming the cooldown.
            self._release_open_slot(symbol, opened=opened)

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
        logger.info(
            f"  Confidence Modifier: {regime_analysis.confidence_modifier:.2f}x"
        )
        logger.info(f"  Description: {regime_analysis.description}")
        logger.info(f"  Strategy: {regime_analysis.strategy_recommendation}")
        logger.info("=" * 60)

    # ============================================================================
    # RESEARCH-BACKED: Position Monitoring (2025-11-29)
    # ============================================================================

    async def _check_position_hold_time(self, position, current_price: float) -> bool:
        """
        Check if position exceeds max hold time and force close if needed

        CRITICAL FIX (Added 2026-01-16):
        - Problem: SOLUSDT SHORT held 185 hours instead of 48 hour max
        - Impact: Small loss compounded into -$14.33 catastrophic loss
        - Solution: Force close positions that exceed max_position_hold_hours

        Args:
            position: Position object from database
            current_price: Current market price for the symbol

        Returns:
            True if position was force closed, False if still open
        """
        # Check if feature is enabled
        if not self.settings.enable_max_hold_time:
            return False

        max_hours = self.settings.max_position_hold_hours
        now = datetime.now(position.opened_at.tzinfo)
        time_held = now - position.opened_at
        hours_held = time_held.total_seconds() / 3600

        # Check if position exceeds max hold time
        if hours_held <= max_hours:
            return False

        # Position exceeds max hold time - FORCE CLOSE
        logger.warning(
            f"[MAX_HOLD] ⚠️ Position {position.symbol} held {hours_held:.1f}h > {max_hours}h max | "
            f"Entry: ${position.entry_price} | Current: ${current_price:.2f} | "
            f"Unrealized P&L: ${position.unrealized_pnl:.2f} | "
            f"Side: {position.side} | FORCE CLOSING"
        )

        try:
            # Determine exit action (opposite of position side)
            exit_action = "SELL" if position.side.value == "LONG" else "BUY"

            # Get trading engine (paper or live)
            trading_mode = self.settings.trading_mode
            if trading_mode == "LIVE":
                trading_engine = get_live_engine()
            else:
                trading_engine = get_paper_engine()

            # Create market order to close position immediately
            # FIX (audit 2026-05-01): OrderCreate field is `type`, not `order_type`
            # — passing order_type would raise pydantic ValidationError on every
            # max-hold-time forced close. Also: paper/live engines expose
            # execute_market_order, not place_order — calling place_order would
            # raise AttributeError immediately after the ValidationError. Both
            # bugs were dead-on-first-invocation, so the max-hold force-close
            # path has never executed since 2026-01-16.
            exit_order = OrderCreate(
                symbol=position.symbol,
                side=OrderSide.SELL if exit_action == "SELL" else OrderSide.BUY,
                type=OrderType.MARKET,
                quantity=position.quantity,
                position_id=position.id,
                reduce_only=True,
                # 2026-05-15: tag close rows for post-hoc attribution.
                strategy="max_hold_force_close",
            )

            # Execute force close
            executed_order, exec_err = await trading_engine.execute_market_order(
                exit_order, Decimal(str(current_price))
            )
            if exec_err:
                logger.warning(
                    f"[MAX_HOLD] execute error for {position.symbol}: {exec_err}"
                )

            if executed_order and executed_order.status == OrderStatus.FILLED:
                # Update position manager
                position_mgr = get_position_manager()
                position_mgr.close_position(
                    position_id=position.id,
                    exit_price=Decimal(str(current_price)),
                    exit_reason=f"MAX_HOLD_TIME_EXCEEDED ({hours_held:.1f}h > {max_hours}h)",
                )

                logger.info(
                    f"[MAX_HOLD] ✅ Successfully closed {position.symbol} after {hours_held:.1f}h | "
                    f"Exit: ${current_price:.2f} | P&L: ${position.unrealized_pnl:.2f}"
                )

                # Send critical notification
                try:
                    notification_client = get_notification_client()
                    await notification_client.send_notification(
                        title="⏱️ MAX HOLD TIME - Position Force Closed",
                        message=f"Closed {position.symbol} {position.side} after {hours_held:.1f}h\n"
                        f"Max allowed: {max_hours}h\n"
                        f"Entry: ${position.entry_price}\n"
                        f"Exit: ${current_price:.2f}\n"
                        f"P&L: ${position.unrealized_pnl:.2f}",
                        severity="high",
                    )
                except Exception as notif_err:
                    logger.debug(f"[MAX_HOLD] Notification note: {notif_err}")

                return True  # Position was closed
            else:
                logger.error(
                    f"[MAX_HOLD] ❌ Failed to close {position.symbol} - order status: "
                    f"{executed_order.status if executed_order else 'None'}"
                )
                return False

        except Exception as e:
            logger.error(
                f"[MAX_HOLD] ❌ Exception closing {position.symbol} after {hours_held:.1f}h: {e}",
                exc_info=True,
            )

            # Send critical alert about failure
            try:
                notification_client = get_notification_client()
                await notification_client.send_notification(
                    title="🚨 CRITICAL - Failed to Force Close Position",
                    message=f"Failed to close {position.symbol} after {hours_held:.1f}h\n"
                    f"Error: {str(e)}\n"
                    f"MANUAL INTERVENTION REQUIRED",
                    severity="critical",
                )
            except:
                pass

            return False

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

            # ================================================================
            # SYNC PORTFOLIO HEAT MANAGER (2025-12-02)
            # Keep heat calculations updated with current prices
            # ================================================================
            try:
                current_equity = float(paper_engine.get_balance())
                self.portfolio_heat_manager.sync_with_positions(
                    open_positions, current_equity
                )
            except Exception as sync_err:
                logger.debug(f"[HEAT] Sync note: {sync_err}")

            for position in open_positions:
                try:
                    # Get current price for this symbol
                    current_price = await self._get_current_price(position.symbol)

                    if not current_price:
                        logger.warning(f"[MONITOR] No price for {position.symbol}")
                        continue

                    # ================================================================
                    # CRITICAL: Check Max Hold Time (Added 2026-01-16)
                    # ================================================================
                    # Force close positions that exceed max_position_hold_hours
                    # Prevents catastrophic losses from positions held too long
                    # Example: SOLUSDT SHORT held 185h instead of 48h max -> -$14.33 loss
                    # ================================================================
                    was_closed = await self._check_position_hold_time(
                        position, current_price
                    )
                    if was_closed:
                        # Position was force closed due to max hold time
                        # Skip remaining monitoring for this position
                        continue

                    # Get ATR value for trailing stop distance
                    atr_value = await self._get_atr_value(position.symbol)

                    # ================================================================
                    # ATR TRAILING STOP UPDATE (2025-12-02)
                    # Use Chandelier Exit methodology for volatility-adjusted stops
                    # ================================================================
                    if atr_value and position.stop_loss:
                        try:
                            # Build position dict for ATR trailing stop
                            position_side = (
                                "LONG"
                                if str(position.side).upper() in ["LONG", "BUY"]
                                else "SHORT"
                            )
                            pos_dict = {
                                "symbol": position.symbol,
                                "entry_price": float(position.entry_price),
                                "side": position_side,
                                "current_stop": float(position.stop_loss),
                            }

                            # Calculate new trailing stop using ATR-based methodology
                            new_atr_stop = self.atr_trailing_stop.update_position_stop(
                                position=pos_dict,
                                current_price=current_price,
                                atr_value=atr_value,
                                volatility_regime=TrailingStopVolatilityRegime.NORMAL,
                            )

                            if new_atr_stop and new_atr_stop != float(
                                position.stop_loss
                            ):
                                logger.info(
                                    f"[ATR_TRAIL] {position.symbol}: Stop updated "
                                    f"${float(position.stop_loss):.2f} -> ${new_atr_stop:.2f} "
                                    f"(ATR={atr_value:.2f})"
                                )
                                # Update position stop in manager
                                position_mgr.set_position_stops(
                                    position_id=position.id,
                                    stop_loss=Decimal(str(new_atr_stop)),
                                    take_profit=position.take_profit,
                                )

                        except Exception as atr_trail_err:
                            logger.debug(
                                f"[ATR_TRAIL] Update note for {position.symbol}: {atr_trail_err}"
                            )

                    # ================================================================
                    # PARTIAL PROFIT TAKER CHECK (2025-12-02)
                    # Scale out at 1%, 2%, 3% profit levels
                    # ================================================================
                    try:
                        partial_state = self.partial_profit_taker.positions.get(
                            position.symbol
                        )
                        if partial_state:
                            # Check for partial exits
                            exits_to_execute = (
                                self.partial_profit_taker.check_partial_exits(
                                    partial_state, current_price
                                )
                            )

                            for partial_exit_order in exits_to_execute:
                                logger.info(
                                    f"[PARTIAL] Level {partial_exit_order.level_number} triggered for "
                                    f"{position.symbol}: exit {partial_exit_order.quantity_to_exit:.6f} "
                                    f"@ ${partial_exit_order.exit_price:.2f} ({partial_exit_order.profit_pct:.2f}% profit)"
                                )

                                # Execute the partial exit
                                await self._execute_partial_profit_exit(
                                    position, partial_exit_order, current_price
                                )

                                # Update partial profit state
                                self.partial_profit_taker.execute_partial_exit(
                                    partial_state,
                                    partial_exit_order.level_number,
                                    current_price,
                                )

                                # Check if should move stop to breakeven
                                if self.partial_profit_taker.should_move_to_breakeven(
                                    partial_state
                                ):
                                    breakeven_price = (
                                        self.partial_profit_taker.get_breakeven_stop(
                                            partial_state
                                        )
                                    )
                                    position_mgr.set_position_stops(
                                        position_id=position.id,
                                        stop_loss=Decimal(str(breakeven_price)),
                                        take_profit=position.take_profit,
                                    )
                                    logger.info(
                                        f"[PARTIAL] Breakeven stop activated for {position.symbol}: "
                                        f"${breakeven_price:.2f}"
                                    )

                    except Exception as partial_err:
                        logger.debug(
                            f"[PARTIAL] Check note for {position.symbol}: {partial_err}"
                        )

                    # Update position with trailing and check exits
                    position, partial_exit = position_mgr.update_position_with_trailing(
                        position.id, Decimal(str(current_price)), atr_value
                    )

                    # Check all exit conditions
                    should_exit, reason, exit_info = (
                        position_mgr.check_all_exit_conditions(
                            position.id, Decimal(str(current_price))
                        )
                    )

                    if should_exit:
                        # Full exit - also clean up partial profit state
                        logger.info(
                            f"[MONITOR] Exit triggered for {position.symbol}: {reason}"
                        )
                        self.partial_profit_taker.remove_position(position.symbol)
                        self.atr_trailing_stop.remove_position_state(position.symbol)

                        # ================================================================
                        # CRITICAL: Use limit orders for stop loss exits (Added 2026-01-16)
                        # ================================================================
                        # Fix #3: Prevent stop loss slippage by using limit orders
                        # Problem: SOLUSDT SHORT stop loss at -3% executed at -4.8% (+60% slippage)
                        # Solution: Use limit order with 0.5% buffer, fallback to market if not filled
                        # ================================================================
                        if "stop" in reason.lower() or "loss" in reason.lower():
                            await self._close_position_with_limit_order(
                                position, current_price, reason
                            )
                        else:
                            await self._close_position(position, current_price, reason)

                    # ================================================================
                    # DCA CHECK - Add safety order if price dropped enough (2025-12-02)
                    # ================================================================
                    elif self.dca_manager.should_add_safety_order(
                        position.symbol, current_price
                    ):
                        await self._execute_dca_order(position, current_price)

                    elif exit_info:
                        # Partial exit
                        logger.info(
                            f"[MONITOR] Partial exit for {position.symbol}: "
                            f"{exit_info['level']} - {exit_info['exit_percentage']:.0f}%"
                        )
                        await self._execute_partial_exit(
                            position, exit_info, current_price
                        )

                except Exception as e:
                    logger.error(
                        f"[MONITOR] Error processing position {position.symbol}: {e}",
                        exc_info=True,
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
                timeframes=[self.interval],
            )

            if signal and signal.indicators:
                for ind in signal.indicators.values():
                    if hasattr(ind, "metadata") and ind.metadata:
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
                timeframes=[self.interval],
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
                position.id, Decimal(str(current_price)), reason
            )

            # Arm SL cooldown if this close was a stop-loss event (2026-05-15)
            if "stop" in reason.lower() or "loss" in reason.lower():
                self._record_sl_hit(position.symbol, reason)

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
                position_value=0.0,  # Position is closed
            )

            if triggered:
                logger.warning(
                    f"[MONITOR] Kill switch thresholds triggered after close: {triggered}"
                )

            # Record trade return for performance analytics (2025-11-30 v2)
            if closed.pnl_percentage is not None:
                self._record_trade_return(
                    closed.pnl_percentage / 100
                )  # Convert to decimal

            logger.info(
                f"[MONITOR] Position closed: {position.symbol} | "
                f"P&L: ${float(closed.realized_pnl):.2f} ({closed.pnl_percentage:+.2f}%) | "
                f"Reason: {reason}"
            )

            # ================================================================
            # REMOVE DCA TRACKING (2025-12-02)
            # ================================================================
            try:
                dca_status = self.dca_manager.get_position_status(position.symbol)
                if dca_status:
                    logger.info(
                        f"[DCA] Position closed with {dca_status['current_layer']} DCA layers | "
                        f"Avg entry: ${dca_status['average_entry']:.4f}"
                    )
                self.dca_manager.remove_position(position.symbol)
            except Exception as dca_err:
                logger.debug(f"[DCA] Cleanup note: {dca_err}")

            # ================================================================
            # REMOVE FROM PORTFOLIO HEAT MANAGER (2025-12-02)
            # ================================================================
            try:
                self.portfolio_heat_manager.remove_position(position.symbol)
                new_heat = self.portfolio_heat_manager.get_summary_dict()
                logger.info(
                    f"[HEAT] Position removed: {position.symbol} | "
                    f"Remaining heat: {new_heat['total_heat_pct']:.2f}% | "
                    f"Open positions: {new_heat['position_count']}"
                )
            except Exception as heat_err:
                logger.debug(f"[HEAT] Cleanup note: {heat_err}")

            # Send trade close notification (2025-12-01)
            try:
                # FIX (audit 2026-05-01): position.side is the app.models
                # PositionSide enum (LONG/SHORT), never the string "BUY".
                # Previously the close side always evaluated to "BUY" — every
                # close notification showed action=BUY even for LONG closes.
                # Compare via .value rather than the enum because this file
                # imports a *different* PositionSide from atr_trailing_stop
                # (lowercase values) at the top, shadowing the right one.
                _pos_side_str = (
                    position.side.value
                    if hasattr(position.side, "value")
                    else str(position.side)
                ).upper()
                side = "SELL" if _pos_side_str == "LONG" else "BUY"
                await self.notification_client.notify_trade_close(
                    symbol=position.symbol,
                    action=side,
                    quantity=float(position.quantity),
                    entry_price=float(position.entry_price),
                    exit_price=float(current_price),
                    pnl=float(closed.realized_pnl) if closed.realized_pnl else 0.0,
                    pnl_pct=float(closed.pnl_percentage)
                    if closed.pnl_percentage
                    else 0.0,
                )
            except Exception as notify_err:
                logger.debug(f"Notification failed (non-critical): {notify_err}")

        except Exception as e:
            logger.error(f"[MONITOR] Failed to close position: {e}", exc_info=True)

    async def _close_position_with_limit_order(
        self,
        position,
        current_price: float,
        reason: str,
        limit_buffer_pct: float = 0.005,  # 0.5% buffer
        timeout_seconds: int = 10,
    ):
        """
        Close a position using a limit order to minimize slippage

        CRITICAL FIX #3 (Added 2026-01-16):
        - Problem: Stop loss configured at -3% but executed at -4.8% (+60% slippage)
        - Root Cause: Using market orders which fill at any price
        - Solution: Use limit orders with small buffer, fallback to market if not filled
        - Expected Impact: Reduce slippage from 60% to <5%

        Flow:
        1. Calculate limit price with buffer (0.5% beyond stop loss)
        2. Place limit order (IOC - Immediate or Cancel)
        3. If not filled within timeout, place market order as fallback
        4. Update position manager with final execution price

        Args:
            position: Position to close
            current_price: Current market price
            reason: Reason for closing (e.g., "stop_loss")
            limit_buffer_pct: Buffer percentage for limit order (default 0.5%)
            timeout_seconds: Max wait time for limit order (default 10s)
        """
        # FIX (T12, 2026-05-01): Loud-failure guard for LIVE mode.
        # LiveTradingEngine does not yet expose a LIMIT IOC reduce_only
        # close-order method (see the in-block comment in STEP 2 below).
        # Both the inner except Exception as limit_err at the limit-order
        # fallthrough and the outer except Exception as e would otherwise
        # swallow our RuntimeError and silently route a LIVE stop-loss exit
        # through the paper engine or through execute_market_order (which
        # ignores reduce_only=True and would OPEN a new opposite position
        # on Bybit instead of closing). Raise BEFORE entering the outer try
        # so the failure propagates to the caller untouched.
        if self.settings.trading_mode == "LIVE":
            raise RuntimeError(
                "LIVE limit-order stop-loss path requires "
                "LiveTradingEngine.close_position_with_limit (LIMIT IOC "
                "reduce_only) — not yet implemented; T1.3 maker-order "
                "test cannot run in LIVE mode. See "
                "app/auto_trader.py:_close_position_with_limit_order."
            )

        # Arm SL cooldown (2026-05-15). This path is invoked only for stop-loss
        # exits (callers gate on "stop"/"loss" in reason — see _monitor loop).
        # Done before close attempt so even if the close path partially fails
        # the cooldown still blocks re-entry whipsaw.
        self._record_sl_hit(position.symbol, reason)

        try:
            from app.models import (
                OrderCreate,
                OrderSide,
                OrderType,
                OrderStatus,
                TimeInForce,
            )

            position_mgr = get_position_manager()

            # Determine exit side (opposite of position)
            exit_side = (
                OrderSide.SELL if position.side.value == "LONG" else OrderSide.BUY
            )

            # ================================================================
            # STEP 1: Calculate limit price with buffer
            # ================================================================
            # For LONG: Sell at limit slightly below current price
            # For SHORT: Buy at limit slightly above current price
            # This ensures we get filled quickly but with controlled slippage
            # ================================================================
            if position.side.value == "LONG":
                # LONG stop loss: Sell at limit slightly below stop loss
                # Buffer allows faster fill while preventing excessive slippage
                limit_price = (
                    float(position.stop_loss) * (1 - limit_buffer_pct)
                    if position.stop_loss
                    else current_price * (1 - limit_buffer_pct)
                )
            else:  # SHORT
                # SHORT stop loss: Buy at limit slightly above stop loss
                limit_price = (
                    float(position.stop_loss) * (1 + limit_buffer_pct)
                    if position.stop_loss
                    else current_price * (1 + limit_buffer_pct)
                )

            logger.info(
                f"[LIMIT_STOP] {position.symbol} {position.side.value} | "
                f"Stop: ${position.stop_loss} | Current: ${current_price:.2f} | "
                f"Limit: ${limit_price:.2f} (buffer: {limit_buffer_pct * 100:.1f}%)"
            )

            # ================================================================
            # STEP 2: Attempt limit order execution
            # ================================================================
            try:
                # Get trading engine (paper or live)
                trading_mode = self.settings.trading_mode
                if trading_mode == "LIVE":
                    # FIX (T12, 2026-05-01): Previously this branch silently fell back
                    # to the paper engine, which would log a paper-trading fill and
                    # leave the LIVE position OPEN on Bybit while updating local
                    # PositionManager as if it were closed. That is the worst
                    # possible failure mode in LIVE.
                    #
                    # The correct fix is a real LIMIT IOC reduce_only call, but
                    # LiveTradingEngine (app/live_trading.py) does not expose
                    # one yet:
                    #   - execute_market_order hardcodes order_type="Market"
                    #     and reduce_only=False, so it ignores both the LIMIT
                    #     type and the reduce_only=True flag on
                    #     OrderCreate and would OPEN a new opposite position
                    #     instead of closing.
                    #   - execute_maker_order_with_fallback is for ENTRY
                    #     (PostOnly + create_position), not for stop-loss
                    #     exits.
                    # The bybit-connector itself supports LIMIT/IOC/reduce_only
                    # (see services/bybit-connector/app/bybit_rest_client.py
                    # place_order), so the fix is to add a
                    # close_position_with_limit method on
                    # LiveTradingEngine that wires those parameters through.
                    # Until that exists, fail LOUD instead of silently routing
                    # LIVE stop-loss exits through the paper engine.
                    raise RuntimeError(
                        "LIVE limit-order stop-loss path requires "
                        "LiveTradingEngine.close_position_with_limit (LIMIT IOC "
                        "reduce_only) — not yet implemented; T1.3 maker-order "
                        "test cannot run in LIVE mode. See "
                        "app/auto_trader.py:_close_position_with_limit_order."
                    )
                else:
                    trading_engine = get_paper_engine()

                # Create limit order (IOC = Immediate or Cancel)
                # FIX (audit 2026-05-01): OrderCreate field is `type`, not `order_type`.
                limit_order = OrderCreate(
                    symbol=position.symbol,
                    side=exit_side,
                    type=OrderType.LIMIT,
                    price=Decimal(str(limit_price)),
                    quantity=position.quantity,
                    time_in_force=TimeInForce.IOC
                    if hasattr(TimeInForce, "IOC")
                    else None,
                    reduce_only=True,
                    position_id=position.id,
                    # 2026-05-15: tag close rows for post-hoc attribution.
                    strategy="stop_loss_limit",
                )

                # Execute limit order
                logger.info(
                    f"[LIMIT_STOP] Placing limit order: {exit_side.value} {position.quantity} {position.symbol} @ ${limit_price:.2f}"
                )

                # For paper trading, simulate limit order execution
                # In real trading, this would use the exchange's limit order API
                limit_result = await trading_engine.execute_market_order(
                    limit_order,
                    Decimal(str(limit_price)),  # Paper trading: use limit price
                )

                if limit_result and limit_result[0].status == OrderStatus.FILLED:
                    # Limit order filled successfully
                    actual_fill_price = float(limit_result[0].filled_price)
                    slippage_pct = abs(
                        (actual_fill_price - limit_price) / limit_price * 100
                    )

                    logger.info(
                        f"[LIMIT_STOP] ✅ Limit order FILLED | "
                        f"{position.symbol} @ ${actual_fill_price:.2f} | "
                        f"Slippage: {slippage_pct:.2f}% | "
                        f"Saved vs market order: ~{0.005 * 100 - slippage_pct:.2f}%"
                    )

                    # Update position manager
                    closed_position = position_mgr.close_position(
                        position_id=position.id,
                        close_price=Decimal(str(actual_fill_price)),
                        reason=f"{reason} (limit order @ ${actual_fill_price:.2f})",
                    )

                    # Send notification
                    try:
                        await self.notification_client.send_notification(
                            title="🎯 Stop Loss Limit Order Filled",
                            message=f"Closed {position.symbol} {position.side.value}\n"
                            f"Limit: ${limit_price:.2f}\n"
                            f"Filled: ${actual_fill_price:.2f}\n"
                            f"Slippage: {slippage_pct:.2f}%\n"
                            f"P&L: ${closed_position.realized_pnl:.2f}",
                            severity="medium",
                        )
                    except Exception as notif_err:
                        logger.debug(f"[LIMIT_STOP] Notification note: {notif_err}")

                    return

            except Exception as limit_err:
                logger.warning(f"[LIMIT_STOP] Limit order failed: {limit_err}")

            # ================================================================
            # STEP 3: Fallback to market order if limit order not filled
            # ================================================================
            logger.warning(
                f"[LIMIT_STOP] ⚠️ Limit order not filled, falling back to MARKET order | "
                f"{position.symbol}"
            )

            # Create market order as fallback
            # FIX (audit 2026-05-01): OrderCreate field is `type`, not `order_type`.
            market_order = OrderCreate(
                symbol=position.symbol,
                side=exit_side,
                type=OrderType.MARKET,
                quantity=position.quantity,
                reduce_only=True,
                position_id=position.id,
                # 2026-05-15: tag close rows for post-hoc attribution.
                strategy="stop_loss_market_fallback",
            )

            # Execute market order
            trading_engine = (
                get_paper_engine()
                if self.settings.trading_mode != "LIVE"
                else get_live_engine()
            )
            market_result = await trading_engine.execute_market_order(
                market_order, Decimal(str(current_price))
            )

            if market_result and market_result[0].status == OrderStatus.FILLED:
                actual_fill_price = float(market_result[0].filled_price)
                slippage_pct = (
                    abs(
                        (actual_fill_price - float(position.stop_loss))
                        / float(position.stop_loss)
                        * 100
                    )
                    if position.stop_loss
                    else 0
                )

                logger.info(
                    f"[LIMIT_STOP] ⚡ Market order FILLED (fallback) | "
                    f"{position.symbol} @ ${actual_fill_price:.2f} | "
                    f"Slippage from stop: {slippage_pct:.2f}%"
                )

                # Update position manager
                closed_position = position_mgr.close_position(
                    position_id=position.id,
                    close_price=Decimal(str(actual_fill_price)),
                    reason=f"{reason} (market fallback @ ${actual_fill_price:.2f})",
                )

                # Send alert about fallback
                try:
                    await self.notification_client.send_notification(
                        title="⚠️ Stop Loss Market Fallback",
                        message=f"Limit order failed, used market order\n"
                        f"{position.symbol} {position.side.value}\n"
                        f"Filled: ${actual_fill_price:.2f}\n"
                        f"Slippage: {slippage_pct:.2f}%\n"
                        f"P&L: ${closed_position.realized_pnl:.2f}",
                        severity="high",
                    )
                except Exception as notif_err:
                    logger.debug(f"[LIMIT_STOP] Notification note: {notif_err}")
            else:
                logger.error(
                    f"[LIMIT_STOP] ❌ Both limit and market orders failed for {position.symbol}"
                )
                # Send critical alert
                try:
                    await self.notification_client.send_notification(
                        title="🚨 CRITICAL - Stop Loss Failed to Execute",
                        message=f"Failed to close {position.symbol}\n"
                        f"Both limit and market orders failed\n"
                        f"MANUAL INTERVENTION REQUIRED",
                        severity="critical",
                    )
                except:
                    pass

        except Exception as e:
            logger.error(
                f"[LIMIT_STOP] ❌ Exception in limit order close for {position.symbol}: {e}",
                exc_info=True,
            )
            # Last resort: call regular close_position
            await self._close_position(position, current_price, reason)

    async def _execute_partial_exit(
        self, position, exit_info: dict, current_price: float
    ):
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
                position.id, exit_info, Decimal(str(current_price))
            )

            level = exit_info["level"]
            logger.info(
                f"[MONITOR] Partial exit executed: {position.symbol} {level} | "
                f"P&L: ${float(partial_pnl):.2f} | "
                f"Remaining: {float(updated_pos.remaining_quantity):.4f}"
            )

            # Send notification for partial exit (2025-12-16 FIX)
            try:
                exit_action = "SELL" if position.side.value == "LONG" else "BUY"
                pnl_pct = (
                    (
                        float(partial_pnl)
                        / (float(position.entry_price) * exit_info["exit_quantity"])
                    )
                    * 100
                    if position.entry_price
                    else 0.0
                )
                await self.notification_client.notify_trade_close(
                    symbol=position.symbol,
                    action=f"{exit_action} ({level})",
                    quantity=float(exit_info["exit_quantity"]),
                    entry_price=float(position.entry_price),
                    exit_price=current_price,
                    pnl=float(partial_pnl),
                    pnl_pct=pnl_pct,
                )
            except Exception as notify_err:
                logger.debug(
                    f"Notification failed for partial exit (non-critical): {notify_err}"
                )

            # Enable trailing stop after TP1
            if exit_info.get("enable_trailing", False):
                logger.info(f"[MONITOR] Trailing stop enabled for {position.symbol}")

        except Exception as e:
            logger.error(
                f"[MONITOR] Failed to execute partial exit: {e}", exc_info=True
            )

    async def _execute_partial_profit_exit(
        self, position, partial_exit, current_price: float
    ):
        """
        Execute a partial profit exit from the PartialProfitTaker (2025-12-02)

        This is a scale-out exit at profit levels (1%, 2%, 3%).

        Args:
            position: Current position
            partial_exit: PartialExitToExecute object from PartialProfitTaker
            current_price: Current market price
        """
        try:
            paper_engine = get_paper_engine()
            position_mgr = get_position_manager()
            trading_mode = settings.trading_mode

            # Create exit order (opposite side to close)
            exit_side = OrderSide.SELL if partial_exit.side == "LONG" else OrderSide.BUY

            order = OrderCreate(
                symbol=partial_exit.symbol,
                side=exit_side,
                type=OrderType.MARKET,
                quantity=Decimal(str(partial_exit.quantity_to_exit)),
                strategy="partial_profit_taker",
            )

            # Execute through paper engine
            executed_order, error = await paper_engine.execute_market_order(
                order, Decimal(str(current_price))
            )

            if executed_order and executed_order.status == OrderStatus.FILLED:
                # Calculate PnL for this partial
                entry_price = float(position.entry_price)
                if partial_exit.side == "LONG":
                    pnl = (current_price - entry_price) * partial_exit.quantity_to_exit
                else:
                    pnl = (entry_price - current_price) * partial_exit.quantity_to_exit

                logger.info(
                    f"[{trading_mode}] Partial profit exit executed: {partial_exit.symbol} | "
                    f"Level {partial_exit.level_number} | "
                    f"Qty: {partial_exit.quantity_to_exit:.6f} @ ${current_price:.2f} | "
                    f"PnL: ${pnl:.2f} ({partial_exit.profit_pct:.2f}%)"
                )

                # Send notification for partial exit (2025-12-16 FIX)
                try:
                    exit_action = "SELL" if partial_exit.side == "LONG" else "BUY"
                    await self.notification_client.notify_trade_close(
                        symbol=partial_exit.symbol,
                        action=f"{exit_action} (TP{partial_exit.level_number})",
                        quantity=float(partial_exit.quantity_to_exit),
                        entry_price=entry_price,
                        exit_price=current_price,
                        pnl=float(pnl),
                        pnl_pct=float(partial_exit.profit_pct),
                    )
                except Exception as notify_err:
                    logger.debug(
                        f"Notification failed for partial exit (non-critical): {notify_err}"
                    )

                # Record trade return for analytics
                if entry_price > 0:
                    return_pct = pnl / (entry_price * partial_exit.quantity_to_exit)
                    self._record_trade_return(return_pct)

            else:
                logger.warning(
                    f"[{trading_mode}] Failed to execute partial profit exit for "
                    f"{partial_exit.symbol}: {error}"
                )

        except Exception as e:
            logger.error(
                f"[MONITOR] Failed to execute partial profit exit: {e}", exc_info=True
            )

    async def _execute_dca_order(self, position, current_price: float):
        """
        Execute a DCA safety order to average down on a losing position

        Research-backed implementation (2025-12-02):
        - Pionex: DCA needs only 1.02% recovery after 5% drop (vs 4.2% for grid)
        - 3Commas: Safety orders with volume scaling
        - TradeSanta: Recalculates TP with each new order

        Args:
            position: The losing position to average down
            current_price: Current market price
        """
        try:
            trading_mode = settings.trading_mode
            paper_engine = get_paper_engine()
            balance = paper_engine.get_balance()

            # Create safety order
            safety_order = self.dca_manager.create_safety_order(
                symbol=position.symbol,
                current_price=current_price,
                capital=float(balance),
            )

            if not safety_order:
                logger.warning(
                    f"[DCA] Could not create safety order for {position.symbol}"
                )
                return

            logger.info("=" * 70)
            logger.info(f"[DCA] SAFETY ORDER for {position.symbol}")
            logger.info("=" * 70)
            logger.info(f"  Layer: {safety_order.layer}")
            logger.info(f"  Price: ${current_price:.4f}")
            logger.info(f"  Quantity: {safety_order.quantity:.6f}")
            logger.info(f"  Deviation: {safety_order.deviation_pct:.2f}%")
            logger.info("=" * 70)

            # Execute the safety order.
            # FIX (audit 2026-05-01): position.side is app.models PositionSide
            # (LONG/SHORT). Comparing to "BUY" was always False, so the DCA
            # safety order would always SELL — adding to a SHORT averages
            # correctly but inverts the LONG case. Compare on LONG/SHORT.
            _pos_side_str = (
                position.side.value
                if hasattr(position.side, "value")
                else str(position.side)
            ).upper()
            side = OrderSide.BUY if _pos_side_str == "LONG" else OrderSide.SELL

            order = OrderCreate(
                symbol=position.symbol,
                side=side,
                type=OrderType.MARKET,
                quantity=Decimal(str(safety_order.quantity)),
                strategy="dca_safety_order",
            )

            executed_order, error = await paper_engine.execute_market_order(
                order, Decimal(str(current_price))
            )

            if executed_order and executed_order.status == OrderStatus.FILLED:
                # Process the filled order with DCA manager
                result = self.dca_manager.process_filled_order(
                    symbol=position.symbol, order=safety_order, fill_price=current_price
                )

                self.dca_orders_executed += 1

                # Log new average entry and TP
                if result:
                    logger.info(
                        f"[DCA] Position averaged: "
                        f"new avg=${result['average_entry']:.4f}, "
                        f"total qty={result['total_quantity']:.6f}"
                    )
                    if "new_take_profit" in result:
                        logger.info(f"[DCA] New TP: ${result['new_take_profit']:.4f}")
                    if "new_stop_loss" in result:
                        logger.warning(
                            f"[DCA] Max layers reached - new SL: ${result['new_stop_loss']:.4f}"
                        )

                # Update position manager with new TP/SL if applicable
                if result and "new_take_profit" in result:
                    try:
                        position_mgr = get_position_manager()
                        position_mgr.set_position_stops(
                            position_id=position.id,
                            stop_loss=Decimal(
                                str(result.get("new_stop_loss", position.stop_loss))
                            ),
                            take_profit=Decimal(str(result["new_take_profit"])),
                        )
                    except Exception as update_err:
                        logger.warning(
                            f"[DCA] Failed to update position stops: {update_err}"
                        )

                logger.info(
                    f"[DCA] Safety order executed successfully for {position.symbol}"
                )

            else:
                logger.warning(
                    f"[DCA] Safety order execution failed for {position.symbol}: {error}"
                )

        except Exception as e:
            logger.error(
                f"[DCA] Error executing safety order for {position.symbol}: {e}",
                exc_info=True,
            )

    async def _execute_trade(self, symbol: str, action: str, confidence: float, signal):
        """
        Execute a trade based on the signal

        Args:
            symbol: Trading symbol
            action: BUY or SELL
            confidence: Signal confidence score
            signal: TradingSignal object
        """
        # SL cooldown check (2026-05-15). Block re-entry on same symbol within
        # sl_cooldown_seconds after a stop-loss exit. Mirrors the check in
        # _execute_trade_with_setup; placed before the open-slot claim so we
        # don't burn a slot on a guaranteed rejection.
        if not self._check_symbol_cooldown(symbol):
            self.total_trades_rejected += 1
            return

        # Concurrent-open dedup gate (2026-05-06). Race-safe per-symbol claim
        # so two signal paths can't both pass has_position before either commits.
        if not await self._claim_open_slot(symbol):
            return
        opened = False
        try:
            logger.info(
                f"Executing {action} trade for {symbol} (confidence: {confidence:.2f})"
            )

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
                if hasattr(indicator_signal, "metadata") and indicator_signal.metadata:
                    if "current_price" in indicator_signal.metadata:
                        current_price = float(
                            indicator_signal.metadata["current_price"]
                        )
                        break

            if not current_price:
                logger.warning(f"No current price found for {symbol}, skipping trade")
                self.total_trades_rejected += 1
                return

            self._update_vol_estimator(symbol, current_price)

            # Get performance stats for Kelly calculation
            performance_stats = None
            if self.use_performance_data:
                try:
                    perf_tracker = get_performance_tracker()
                    performance_stats = (
                        position_sizer.get_performance_stats_from_tracker(perf_tracker)
                    )
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
                logger.debug(
                    f"VP Stop Loss: ${stop_loss_price:.2f} ({stop_loss_pct:.2%})"
                )

            # Calculate dynamic position size
            size_result = position_sizer.calculate_position_size(
                method=self.position_sizing_method,
                current_balance=Decimal(str(balance)),
                current_price=Decimal(str(current_price)),
                signal_confidence=confidence,
                performance_stats=performance_stats,
                stop_loss_pct=stop_loss_pct,
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
            open_positions = (
                position_mgr.get_open_positions()
            )  # Fixed: get_open_positions() is synchronous
            has_position = any(p.symbol == symbol for p in open_positions)

            if has_position:
                logger.info(f"Already have open position for {symbol}, skipping")
                self.total_trades_rejected += 1
                return

            # Min-notional / min-qty gate (added 2026-05-06).
            # See _passes_min_notional docstring; reject-not-upround keeps
            # the 2% per-trade cap intact.
            ok, _reason = await self._passes_min_notional(
                symbol=symbol,
                quantity=quantity,
                price=current_price,
                balance=balance,
            )
            if not ok:
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
                strategy="auto_trader",
                # 2026-05-15: persist confidence so trades table can be analyzed
                # post-hoc. Previously NULL on 29/31 rows blocked debugging the
                # May 6-7 whipsaw run.
                entry_signal_confidence=float(confidence),
            )

            executed_order, error = await paper_engine.execute_market_order(
                order, Decimal(str(current_price))
            )

            # HIGH FIX 2025-12-11: Add null check before accessing status
            if executed_order is None:
                self.total_trades_rejected += 1
                logger.warning(f"Trade execution returned None for {symbol}: {error}")
                return

            if executed_order.status == OrderStatus.FILLED:
                self.total_trades_executed += 1
                opened = True  # arm dedup cooldown for this symbol
                logger.info(f"Trade executed successfully for {symbol}")
                logger.info(
                    f"Stats: Checked={self.total_signals_checked}, "
                    f"Executed={self.total_trades_executed}, "
                    f"Rejected={self.total_trades_rejected}"
                )

                # Pass through the signal confidence (and any SL/TP from signal metadata).
                # 2026-04-25: was hardcoded to 0.0 with stale comment "standard mode doesn't have
                # confidence score" — but _execute_trade receives confidence as a parameter.
                vp = (
                    signal.metadata.get("volume_profile", {})
                    if hasattr(signal, "metadata")
                    else {}
                )
                try:
                    await self.notification_client.notify_trade_open(
                        symbol=symbol,
                        action=action,
                        quantity=float(quantity),
                        price=float(current_price),
                        confidence=float(confidence),
                        stop_loss=float(vp.get("stop_loss") or 0.0),
                        take_profit=float(vp.get("take_profit") or 0.0),
                    )
                except Exception as notify_err:
                    logger.warning(f"Notification failed (non-critical): {notify_err}")
            else:
                self.total_trades_rejected += 1
                logger.warning(f"Trade execution failed for {symbol}: {error}")

        except Exception as e:
            logger.error(f"Error executing trade for {symbol}: {e}", exc_info=True)
            self.total_trades_rejected += 1
        finally:
            # Release per-symbol open slot. Arms cooldown only on `opened=True`.
            self._release_open_slot(symbol, opened=opened)

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
                    "message": "Need at least 2 trade returns for analytics",
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
                    "avg_r_multiple": report.trade_statistics.avg_r_multiple,
                },
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
        logger.debug(
            f"Trade return recorded: {pnl_pct:.2%} | Total: {len(self.trade_returns)}"
        )

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
            "emergency_stop": {
                "file_path": str(self.emergency_stop_file),
                "active": self.emergency_stop_active,
                "last_checked": (
                    self.emergency_stop_last_checked.isoformat()
                    if self.emergency_stop_last_checked
                    else None
                ),
            },
            "symbols": self.symbols,
            "symbols_count": len(self.symbols),
            "interval": self.interval,
            "check_frequency_seconds": self.check_frequency,
            "total_signals_checked": self.total_signals_checked,
            "total_trades_executed": self.total_trades_executed,
            "total_trades_rejected": self.total_trades_rejected,
            "last_check_time": self.last_check_time.isoformat()
            if self.last_check_time
            else None,
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
                "reentry_cooldown_seconds": self.min_time_between_trades,
            },
            # Position monitoring status (2025-11-29)
            "position_monitoring": {
                "enabled": True,
                "open_positions": len(open_positions),
                "trailing_stops_active": sum(
                    1 for p in open_positions if p.trailing_stop_enabled
                ),
                "partial_exits_enabled": True,
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
                    "slippage_rejections": self.slippage_rejections,
                },
            },
            # ================================================================
            # ADVANCED ENHANCEMENTS STATUS (2025-11-30 v2)
            # ================================================================
            "advanced_enhancements": {
                "position_sizer": {
                    "method": self.advanced_position_sizer.config.default_method.value
                    if hasattr(self.advanced_position_sizer.config, "default_method")
                    else "half_kelly",
                    "max_position_pct": self.advanced_position_sizer.config.max_position_pct,
                    "kelly_fraction": self.advanced_position_sizer.config.kelly_fraction,
                    "sizing_adjustments": self.position_sizing_adjustments,
                },
                "smart_executor": {
                    "default_algorithm": "TWAP",  # Default algorithm
                    "execution_count": self.smart_execution_count,
                    "twap_duration_minutes": self.smart_order_executor.config.twap_duration_minutes,
                    "max_slices": self.smart_order_executor.config.twap_max_slices,
                },
                "performance_analytics": self._get_performance_summary(),
            },
            # ================================================================
            # DCA MANAGER STATUS (2025-12-02)
            # ================================================================
            "dca_manager": {
                "enabled": self.dca_manager.config.enabled,
                "max_layers": self.dca_manager.config.max_safety_orders,
                "deviation_triggers_pct": self.dca_manager.config.safety_order_deviation_pct,
                "volume_scale": self.dca_manager.config.safety_order_volume_scale,
                "tp_after_dca_pct": self.dca_manager.config.tp_after_dca_pct,
                "orders_executed": self.dca_orders_executed,
                "active_dca_positions": len(self.dca_manager.positions),
                "positions": {
                    symbol: self.dca_manager.get_position_status(symbol)
                    for symbol in self.dca_manager.positions.keys()
                },
            },
            # ================================================================
            # PORTFOLIO HEAT MANAGER STATUS (2025-12-02)
            # ================================================================
            "portfolio_heat_manager": self.portfolio_heat_manager.get_summary_dict(),
            # ================================================================
            # ADAPTIVE RSI STATUS (2025-12-02)
            # ================================================================
            "adaptive_rsi": {
                "enabled": True,
                "rsi_period": self.adaptive_rsi.config.rsi_period,
                "trend_filter": self.adaptive_rsi.config.use_trend_filter,
                "thresholds": {
                    "high_volatility": (
                        self.adaptive_rsi.config.high_vol_oversold,
                        self.adaptive_rsi.config.high_vol_overbought,
                    ),
                    "normal": (
                        self.adaptive_rsi.config.normal_vol_oversold,
                        self.adaptive_rsi.config.normal_vol_overbought,
                    ),
                    "low_volatility": (
                        self.adaptive_rsi.config.low_vol_oversold,
                        self.adaptive_rsi.config.low_vol_overbought,
                    ),
                },
            },
            # ================================================================
            # HURST EXPONENT STATUS (2025-12-02)
            # ================================================================
            "hurst_exponent": {
                "enabled": True,
                "trending_threshold": self.hurst_calculator.config.trending_threshold,
                "mean_reversion_threshold": self.hurst_calculator.config.mean_reversion_threshold,
                "lookback_periods": self.hurst_calculator.config.lookback_periods,
            },
            # ================================================================
            # LIMIT ORDER EXECUTOR STATUS (2025-12-02)
            # ================================================================
            "limit_order_executor": self.limit_order_executor.get_status(),
            # ================================================================
            # WALK FORWARD EFFICIENCY STATUS (2025-12-02)
            # ================================================================
            "walk_forward_tester": {
                "enabled": True,
                "strategy_name": self.wfe_tester.strategy_name,
                "in_sample_pct": self.wfe_tester.config.in_sample_pct,
                "out_of_sample_pct": self.wfe_tester.config.out_of_sample_pct,
                "min_wfe_threshold": self.wfe_tester.config.min_wfe_threshold,
                "min_trades_for_confidence": self.wfe_tester.config.min_trades_for_confidence,
                "trades_recorded": len(self.wfe_tester._trades),
            },
            # ================================================================
            # REGIME STRATEGY SELECTOR STATUS (2025-12-02)
            # ================================================================
            "regime_strategy_selector": {
                "enabled": True,
                "trending_params": {"sl_mult": 1.5, "tp_mult": 2.0, "pos_mult": 1.0},
                "mean_reverting_params": {
                    "sl_mult": 0.8,
                    "tp_mult": 1.2,
                    "pos_mult": 0.9,
                },
                "random_walk_params": {"sl_mult": 1.0, "tp_mult": 1.0, "pos_mult": 0.5},
            },
            # ================================================================
            # ATR TRAILING STOP STATUS (2025-12-02)
            # ================================================================
            "atr_trailing_stop": {
                "enabled": True,
                "base_atr_multiplier": self.atr_trailing_stop.config.base_atr_multiplier,
                "min_atr_multiplier": self.atr_trailing_stop.config.min_atr_multiplier,
                "max_atr_multiplier": self.atr_trailing_stop.config.max_atr_multiplier,
                "activation_profit_pct": self.atr_trailing_stop.config.activation_profit_pct,
                "step_pct": self.atr_trailing_stop.config.step_pct,
                "use_chandelier_exit": self.atr_trailing_stop.config.use_chandelier_exit,
                "positions_tracked": len(self.atr_trailing_stop._position_states),
            },
            # ================================================================
            # PARTIAL PROFIT TAKER STATUS (2025-12-02)
            # ================================================================
            "partial_profit_taker": {
                "enabled": self.partial_profit_taker.config.enabled,
                "profit_levels_pct": self.partial_profit_taker.config.profit_levels,
                "exit_percentages": self.partial_profit_taker.config.exit_percentages,
                "move_stop_to_breakeven_after": self.partial_profit_taker.config.move_stop_to_breakeven_after,
                "min_position_value": self.partial_profit_taker.config.min_position_value,
                "positions_tracked": len(self.partial_profit_taker.positions),
                "positions": {
                    symbol: self.partial_profit_taker.get_position_summary(symbol)
                    for symbol in self.partial_profit_taker.positions.keys()
                },
            },
        }

        # Add regime distribution if market regime is enabled
        if self.enable_market_regime:
            status["regime_distribution"] = {
                regime.value: count
                for regime, count in self.regime_counts.items()
                if count > 0
            }
            status["regime_detector_stats"] = self.regime_detector.get_stats()

        # Add hybrid strategy statistics
        if self.strategy_mode in [StrategyMode.RESEARCH, StrategyMode.HYBRID]:
            status["hybrid_strategy_stats"] = self.hybrid_strategy.get_stats()
            status["research_strategy_params"] = (
                self.research_strategy.get_strategy_params()
            )

        return status

    async def _check_and_trade_ensemble(self, symbol: str):
        """ENSEMBLE mode: SimpleRSI + multi-indicator + mean-reversion with performance weighting.

        Picks the largest weighted-vote winner across the three legs, sizes by ensemble
        confidence, attaches per-leg attribution to the position so PerformanceTracker can
        update each leg's win rate when the trade closes.
        """
        from app.strategies.multi_strategy_ensemble import get_ensemble

        try:
            self.total_signals_checked += 1
            risk_mgr = get_risk_manager()
            if risk_mgr.should_halt_trading():
                logger.warning(f"[ENSEMBLE] Trading halted for {symbol}")
                return

            aggregator = await get_aggregator()
            base_signal = await aggregator.get_trading_signal_multi_timeframe(
                symbol=symbol,
                primary_interval=self.interval,
                timeframes=["15", self.interval, "240"],
            )
            if not base_signal:
                logger.warning(f"[ENSEMBLE] No base signal for {symbol}")
                return

            current_price = None
            for _, ind in base_signal.indicators.items():
                if (
                    hasattr(ind, "metadata")
                    and ind.metadata
                    and "current_price" in ind.metadata
                ):
                    current_price = float(ind.metadata["current_price"])
                    break
            if not current_price:
                logger.warning(f"[ENSEMBLE] No current price for {symbol}")
                return

            paper_engine = get_paper_engine()
            balance = paper_engine.get_balance()

            ensemble = get_ensemble()
            ens_signal = ensemble.generate_signal(
                base_signal, current_price, capital=float(balance)
            )
            if not ens_signal:
                self.total_trades_rejected += 1
                return

            logger.info(
                f"[ENSEMBLE] {symbol}: {ens_signal.action.value} conf={ens_signal.confidence:.2%} "
                f"size={ens_signal.position_size_pct * 100:.2f}% legs={ens_signal.leg_actions}"
            )

            position_mgr = get_position_manager()
            if any(p.symbol == symbol for p in position_mgr.get_open_positions()):
                logger.info(f"[ENSEMBLE] Already have position on {symbol}, skipping")
                self.total_trades_rejected += 1
                return

            # Apply leverage to ensemble sizing (fix 2026-05-19).
            # ensemble.position_size_pct sets the MARGIN fraction (already capped
            # at max_risk_per_trade by ensemble's own cascade). Multiplying by
            # leverage converts margin to notional position value. paper_engine
            # then divides notional by default_leverage to compute margin
            # deducted, so cash impact = balance × position_size_pct regardless
            # of leverage; leverage only scales notional (P&L exposure).
            leverage = 1.0
            if self.settings.leverage_enabled:
                leverage = max(
                    self.settings.min_leverage,
                    min(self.settings.default_leverage, self.settings.max_leverage),
                )
            margin_value = float(balance) * ens_signal.position_size_pct
            position_value = margin_value * leverage
            quantity = position_value / current_price

            if self.settings.leverage_enabled:
                logger.info(
                    f"[ENSEMBLE][LEVERAGE] {symbol}: margin=${margin_value:.2f} × "
                    f"{leverage:.0f}x = notional ${position_value:.2f}"
                )

            from decimal import Decimal

            order = OrderCreate(
                symbol=symbol,
                side=OrderSide.BUY
                if ens_signal.action == SignalAction.BUY
                else OrderSide.SELL,
                type=OrderType.MARKET,
                quantity=Decimal(str(quantity)),
                strategy="ensemble",
                # 2026-05-15: persist confidence for post-hoc analysis.
                entry_signal_confidence=float(ens_signal.confidence),
            )
            executed_order, error = await paper_engine.execute_market_order(
                order, Decimal(str(current_price))
            )
            if executed_order is None or executed_order.status != OrderStatus.FILLED:
                self.total_trades_rejected += 1
                logger.warning(f"[ENSEMBLE] Execution failed for {symbol}: {error}")
                return

            self.total_trades_executed += 1
            logger.info(
                f"[ENSEMBLE] Trade executed for {symbol}: ${position_value:.2f} ({quantity:.6f} units)"
            )

            # Tag latest position with leg contributions so we can attribute outcome at close.
            try:
                latest_positions = [
                    p for p in position_mgr.get_open_positions() if p.symbol == symbol
                ]
                if latest_positions:
                    latest_positions[-1].metadata = (
                        getattr(latest_positions[-1], "metadata", {}) or {}
                    )
                    latest_positions[-1].metadata["ensemble_attribution"] = (
                        ens_signal.leg_contributions
                    )
            except Exception as attr_err:
                logger.debug(f"[ENSEMBLE] Could not tag attribution: {attr_err}")

            try:
                await self.notification_client.notify_trade_open(
                    symbol=symbol,
                    action=ens_signal.action.value,
                    quantity=float(quantity),
                    price=current_price,
                    confidence=float(ens_signal.confidence),
                    stop_loss=float(ens_signal.stop_loss),
                    take_profit=float(ens_signal.take_profit),
                )
            except Exception as notify_err:
                logger.warning(
                    f"[ENSEMBLE] Notification failed (non-critical): {notify_err}"
                )

        except Exception as e:
            logger.error(f"[ENSEMBLE] Error for {symbol}: {e}", exc_info=True)
            self.total_trades_rejected += 1

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
            "aggressive": TimingMode.AGGRESSIVE,
            "normal": TimingMode.NORMAL,
            "conservative": TimingMode.CONSERVATIVE,
            "adaptive": TimingMode.ADAPTIVE,
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
        logger.info(
            f"Slippage tolerance updated: base={base_pct}%, volatile={volatile_pct}%"
        )

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
        settings = get_settings()
        # Map config string to StrategyMode enum
        mode_map = {
            "standard": StrategyMode.STANDARD,
            "research": StrategyMode.RESEARCH,
            "hybrid": StrategyMode.HYBRID,
            "grid_trading": StrategyMode.GRID_TRADING,
            "ensemble": StrategyMode.ENSEMBLE,
        }
        strategy_mode = mode_map.get(
            settings.strategy_mode.lower(), StrategyMode.HYBRID
        )
        _auto_trader = AutoTrader(strategy_mode=strategy_mode)
    return _auto_trader


def reset_auto_trader():
    """Reset the global auto trader instance (for testing)"""
    global _auto_trader
    _auto_trader = None
