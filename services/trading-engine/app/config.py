"""
Configuration Module for Trading Engine
Purpose: Centralized configuration management using Pydantic settings

SECURITY UPDATE (2025-12-12): Added strict CORS configuration
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, List, Dict


class Settings(BaseSettings):
    """Trading Engine Service Configuration"""

    # Service Configuration
    service_name: str = Field(default="trading-engine", description="Service name")
    service_host: str = Field(default="0.0.0.0", description="Host to bind to")
    service_port: int = Field(default=8005, description="Port to bind to")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # Service URLs
    technical_analysis_url: str = Field(
        default="http://localhost:8004", description="Technical Analysis Service URL"
    )
    market_data_url: str = Field(
        default="http://localhost:8002",
        description="Market Data Service URL for fetching live prices",
    )
    bybit_connector_url: str = Field(
        default="http://bybit-connector:8001", description="Bybit Connector Service URL"
    )
    portfolio_manager_url: str = Field(
        default="http://localhost:8006", description="Portfolio Manager Service URL"
    )

    # Phase 3 ML/AI Service URLs
    ml_prediction_url: str = Field(
        default="http://localhost:8007",
        description="ML Prediction Service URL for trend/price predictions",
    )
    notification_service_url: str = Field(
        default="http://localhost:8006",
        description="Notification Service URL for trade alerts",
    )

    # Notification Settings
    enable_notifications: bool = Field(
        default=True, description="Enable trade notifications via Telegram/Email"
    )
    notify_on_trade_open: bool = Field(
        default=True, description="Send notification when trade is opened"
    )
    notify_on_trade_close: bool = Field(
        default=True, description="Send notification when trade is closed"
    )
    notify_on_daily_summary: bool = Field(
        default=True, description="Send daily PnL summary notification"
    )

    # Phase C smart-mode flag (auto-trader, 2026-05-05).
    # When enabled, the auto-trader uses three additional gates per cycle:
    #   1) regime_strategy_selector chooses the strategy mode per cycle
    #   2) portfolio_heat_manager skips the cycle entirely if heat is critical
    #   3) ML predicted direction must match the signal direction with
    #      confidence >= ml_confidence_floor; otherwise the trade is rejected
    # Default off so the existing baseline behaviour is unchanged. Flip to
    # true via AUTO_TRADER_SMART_MODE=true to opt in.
    auto_trader_smart_mode: bool = Field(
        default=False,
        description="Enable Phase C smart-mode gates in auto_trader",
    )
    ml_confidence_floor: float = Field(
        default=0.6,
        description=(
            "Minimum ML directional confidence to allow a trade in smart-mode "
            "(0.0..1.0). Below this, smart-mode rejects with reason "
            "'ml_disagreement'."
        ),
    )

    # Phase 3 Feature Flags
    # ML predictions DISABLED by default 2026-04-29 — V0 persistence shootout
    # showed production GRUs have negative R² on log-returns and coin-flip
    # directional accuracy on the corrected metric. See
    # docs/strategy/research-2026-04-29/V0-RESULTS-no-edge.md.
    # Re-enable only after retraining with returns target + CPCV evaluation +
    # gates: r2_returns > 0, dir_acc_corrected > 0.55, isolated paper Sharpe > 0.5.
    enable_ml_predictions: bool = Field(
        default=False,
        description="Enable ML predictions in signal aggregation (30% weight). Off until GRU is rebuilt — see Tier 0 of RESEARCH_PLAN_2026-04-29.",
    )
    enable_multi_timeframe: bool = Field(
        default=False, description="Enable multi-timeframe analysis (15% weight)"
    )

    # Ensemble Predictor (2025-12-07) - Combines all signals in ML service
    use_ensemble_predictor: bool = Field(
        default=True,
        description="Use ensemble predictor endpoint (combines TA+ML+Sentiment+MTF with optimal weights)",
    )

    # Multi-Timeframe Alignment Requirements (2025-12-01)
    # ADJUSTED 2026-01-02: Lowered from 60.0 to 40.0 for 2/3 timeframe agreement
    # ADJUSTED 2026-01-02: Temporarily disabled to test single-timeframe trading
    mtf_require_alignment: bool = Field(
        default=False,  # Disabled to allow single-timeframe trading
        description="Require TF alignment before trading (reduces false signals)",
    )
    mtf_min_alignment_score: float = Field(
        default=40.0,  # Lowered from 60.0 to allow 2/3 timeframe agreement
        ge=0.0,
        le=100.0,
        description="Minimum MTF alignment score (0-100) to execute trades. 40% allows solid 2/3 agreement.",
    )

    # Per-Position Vol Parity Sizing (T1.2 chunk 3, 2026-04-30)
    # Outer overlay above the per-trade cap. When enabled and the estimator
    # is warm, sizes new entries inversely to the symbol's realised volatility
    # so each position contributes roughly equal expected vol. Default OFF
    # — opt in via env, then forward-paper-test ≥7 days before judging.
    # See docs/strategy/research-2026-04-29/T1.2-design.md.
    enable_vol_targeting: bool = Field(
        default=False,
        description="Apply per-position vol-parity sizing on entries. Off until forward-paper-tested.",
    )
    vol_target_annualised: float = Field(
        default=0.30,
        ge=0.05,
        le=2.0,
        description="Target annualised vol per position (e.g. 0.30 = 30%).",
    )
    vol_estimator_window_bars: int = Field(
        default=168,
        ge=24,
        le=2160,
        description="Rolling window in hourly bars for the realised-vol estimator (168 = 7 days).",
    )
    vol_target_cap_multiplier: float = Field(
        default=1.0,
        ge=1.0,
        le=5.0,
        description="Max scale factor over baseline. 1.0 = downside-only (safest); 3.0 = full Carver-style symmetric.",
    )

    # Funding-Rate Gate (T2.3, 2026-04-30)
    # Reject perp entries that would pay funding above a threshold so we
    # don't bleed ~5%/yr on persistent funding drag. Fail-open: if the
    # rate fetch breaks, the gate allows the trade rather than blocking.
    # Default off — opt in via env after a forward-paper-test confirms
    # the gate doesn't reject the profitable side of a real edge.
    enable_funding_gate: bool = Field(
        default=False,
        description="Block perp entries when current funding rate works against the intended direction by more than funding_gate_threshold_bps.",
    )
    funding_gate_threshold_bps: float = Field(
        default=5.0,
        ge=0.0,
        le=50.0,
        description="Per-settlement funding-rate threshold in bps. 5 bps/8h ≈ 5.5%/yr cost; longs blocked above +threshold, shorts below -threshold.",
    )
    funding_cache_ttl_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="How long a fetched funding rate is cached in-memory. Settlements are 8h on most pairs so 5min is plenty.",
    )

    # Order Execution Configuration
    # T1.3 prep 2026-04-29 — flags only, not yet wired into live_trading.py.
    # Default off so this commit is plumbing only. When wiring lands and a
    # forward-paper-test of maker behaviour passes, opt in via env var.
    # Bybit perp economics: taker 0.055% / maker 0.020% → ~7 bps round-trip
    # saved → ~140 bps/yr at 200 round-trips/yr. Spot is flat 0.1%/0.1%
    # — no benefit on spot. See docs/strategy/RESEARCH_PLAN_2026-04-29 T1.3.
    prefer_maker_orders: bool = Field(
        default=False,
        description="Place perp entries as PostOnly limit at best bid/ask to harvest the maker fee. Off until forward-paper-tested.",
    )
    maker_quote_timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=600,
        description="If a maker quote isn't filled within this window, cancel and decide based on maker_fallback_to_taker.",
    )
    maker_fallback_to_taker: bool = Field(
        default=True,
        description="On maker timeout, fall back to a taker market order if the signal is still valid; otherwise abort.",
    )

    # Trading Configuration
    trading_mode: Literal["PAPER", "LIVE"] = Field(
        default="PAPER", description="Trading mode: PAPER or LIVE"
    )
    auto_trading_enabled: bool = Field(
        default=False, description="Enable automatic trading"
    )
    emergency_stop_file: str = Field(
        default="/app/EMERGENCY_STOP",
        description="Path to file-based kill switch. If file exists, auto-trader refuses to start and halts the loop.",
    )
    default_strategy: str = Field(
        default="consensus", description="Default trading strategy"
    )
    default_symbol: str = Field(default="BTCUSDT", description="Default trading symbol")
    trading_symbols: List[str] = Field(
        default=[
            # =============================================================================
            # OPTIMIZED SYMBOL LIST (2026-01-19) - TIER 1 ONLY (5 SYMBOLS)
            # Rationale: Focus on symbols with excellent historical data (250+ days)
            #
            # REMOVED: DOT, ARB, OP (insufficient data: 41 days, 1k candles)
            # REMOVED: AVAX, LINK (limited data: 64-70 days, 4k candles)
            # REMOVED: MATIC (data quality issues)
            #
            # ALLOCATION STRATEGY:
            # - 50% Major caps (BTC, ETH) - Market leaders, highest liquidity
            # - 50% Proven performers (SOL, BNB, ADA) - Historical winners
            #
            # DATA QUALITY (All Tier 1 - Excellent):
            # - BTCUSDT: 66,293 candles (253 days) ✅
            # - ETHUSDT: 66,295 candles (253 days) ✅
            # - SOLUSDT: 66,294 candles (253 days) ✅
            # - BNBUSDT: 66,786 candles (253 days) ✅
            # - ADAUSDT: 61,840 candles (251 days) ✅
            # =============================================================================
            # === TIER 1: MAJOR CAPS (50% allocation) ===
            "BTCUSDT",  # Bitcoin - Flagship, most liquid, market leader (66k candles)
            "ETHUSDT",  # Ethereum - 2nd most liquid, DeFi/smart contracts (66k candles)
            # === TIER 1: PROVEN PERFORMERS (50% allocation) ===
            "SOLUSDT",  # Solana - BEST: 60% WR, +$55.90 profit in 15 trades ✅ (66k candles)
            "BNBUSDT",  # Binance Coin - 2nd: 64.3% WR, +$44.22 profit in 14 trades ✅ (66k candles)
            "ADAUSDT",  # Cardano - 3rd: 75% WR, +$27.43 profit in 4 trades ✅ (61k candles)
        ],
        description="5 ACTIVE SYMBOLS - Tier 1 only with excellent data (250+ days) - OPTIMIZED 2026-01-19",
    )

    # =============================================================================
    # SYMBOL ALLOCATION WEIGHTS (2026-01-19) - OPTIMIZED TO 5 TIER 1 SYMBOLS
    # Focused allocation on highest quality data symbols
    #
    # ALLOCATION PHILOSOPHY:
    # - 50% Major caps (BTC/ETH) - Market leaders, highest liquidity
    # - 50% Proven performers (SOL/BNB/ADA) - Historical winners
    #
    # RATIONALE:
    # - Focus capital on symbols with 250+ days of excellent data
    # - Higher allocation per symbol (20-25% vs 3-15% previously)
    # - Proven historical performance (60-75% win rates)
    # - Removes noise from low-quality data symbols
    # =============================================================================
    symbol_allocations: Dict[str, float] = Field(
        default={
            # ===========================================================================
            # BACKTEST-OPTIMIZED ALLOCATION (2026-01-19) - Based on 30d + 90d Results
            # ===========================================================================
            # Rationale: Allocate more to consistent winners, less to underperformers
            # Performance basis:
            #   - SOLUSDT: #1 both periods (50% WR, +0.01-0.02%, Sharpe +0.24-0.52) ✅
            #   - ADAUSDT: #2 in 90d (49.3% WR, +0.01%, profitable) ✅
            #   - BTCUSDT: Break-even, market leader (keep core holding)
            #   - BNBUSDT: Moderate (44-48% WR, break-even to slight loss)
            #   - ETHUSDT: #5 both periods (25-33% WR, -0.01-0.04%, worst) ❌
            "SOLUSDT": 0.30,  # ⬆️ 30% (was 20%) - BEST performer, consistent winner
            "BTCUSDT": 0.25,  # ➡️ 25% (same) - Market leader, core holding
            "BNBUSDT": 0.20,  # ➡️ 20% (same) - Moderate performer, stable
            "ADAUSDT": 0.15,  # ⬆️ 15% (was 10%) - 2nd best in 90d, improving
            "ETHUSDT": 0.10,  # ⬇️ 10% (was 25%) - WORST performer, reduced risk
        },
        description="BACKTEST-OPTIMIZED: Increased SOL (30%), ADA (15%), decreased ETH (10%). "
        "Focus capital on proven winners. Updated 2026-01-19 based on 30d/90d backtests.",
    )

    default_interval: str = Field(
        default="60", description="Default candlestick interval"
    )

    # Strategy Mode - STANDARD for more trading opportunities (2026-02-24)
    # Options: standard, research, hybrid, grid_trading
    # CHANGED: From 'hybrid' to 'standard' to enable trading in ranging market conditions
    strategy_mode: str = Field(
        default="standard",
        description="Trading strategy mode: standard (more active), research, hybrid (dual confirmation), or grid_trading",
    )

    # Trade Frequency Settings - ADJUSTED for 11 symbols (2026-01-07)
    max_daily_trades: int = Field(
        default=50,
        ge=1,
        le=150,
        description="Maximum trades per day (adjusted for 11 symbols - ~4-5 trades per symbol)",
    )
    check_frequency_seconds: int = Field(
        default=30,
        ge=10,
        le=300,
        description="How often to check for signals (seconds)",
    )
    allow_same_symbol_reentry: bool = Field(
        default=True, description="Allow re-entry on same symbol after position closed"
    )
    min_time_between_trades_same_symbol: int = Field(
        default=60,
        ge=0,
        le=3600,
        description="Minimum seconds between trades on same symbol",
    )

    # Risk Management
    max_position_size_pct: float = Field(
        default=10.0,
        ge=0.1,
        le=50.0,
        description=(
            "Maximum position size as % of capital. "
            "Bumped 2026-05-06 from 5% to 10% to align with per-trade "
            "10% target on $100 paper balance."
        ),
    )
    max_risk_per_trade: float = Field(
        default=0.10,
        ge=0.001,
        le=0.5,
        description=(
            "Maximum per-trade notional cap as a fraction of balance "
            "(0.10 = 10%). Stored as fraction, not percent — distinct from "
            "the neighboring *_pct fields. Reads MAX_RISK_PER_TRADE env. "
            "Bumped 2026-05-06 from 0.02 to 0.10 per operator request: "
            "$100 paper balance × 10% = $10/trade for meaningful test sizing."
        ),
    )
    # Ensemble sizing cascade (2026-05-07) — see ADR-015.
    # Replaces hardcoded constants in multi_strategy_ensemble.py that ignored
    # max_risk_per_trade and clamped trades to 1-3% of capital.
    # Formula: max(min_pos, min(cap, confidence × cap × multiplier))
    # where cap = max_risk_per_trade.
    # Default multiplier 3.7 chosen so confidence ≈ 0.27 (the documented
    # ensemble ceiling per ADR-013 — 7 voting legs × typical conf 0.16-0.50)
    # produces a trade at the cap. Default min 0.05 ensures a single fired
    # trade is meaningful at $100 balance ($5 not $1).
    ensemble_min_position_pct: float = Field(
        default=0.05,
        ge=0.0,
        le=0.5,
        description=(
            "Floor for ensemble position sizing as a fraction of capital. "
            "When the confidence-scaled formula produces a smaller value, "
            "this floor is used instead. Defaults to 0.05 = 5% (was 0.01)."
        ),
    )
    ensemble_confidence_size_multiplier: float = Field(
        default=3.7,
        ge=1.0,
        le=10.0,
        description=(
            "Multiplier on confidence × max_risk_per_trade in the ensemble "
            "sizing formula. Higher = trades reach the cap at lower "
            "confidence. Default 3.7 hits the cap at conf ≈ 0.27 (the "
            "documented ensemble ceiling per ADR-013). Was 1.5 — required "
            "conf 0.67 to hit cap, which the ensemble cannot produce."
        ),
    )
    max_daily_loss_pct: float = Field(
        default=5.0, ge=1.0, le=20.0, description="Maximum daily loss as % of capital"
    )
    max_total_exposure_pct: float = Field(
        default=80.0,
        ge=5.0,
        le=100.0,
        description="Maximum total exposure as % of capital (80% to allow 20+ positions)",
    )
    default_stop_loss_pct: float = Field(
        default=2.0,  # TIGHTENED 2026-01-14: Reduced from 3% to 2% to prevent large losses
        ge=0.5,
        le=10.0,
        description="Default stop loss as % from entry (2% TIGHTER protection after -$14.33 loss)",
    )
    default_take_profit_pct: float = Field(
        default=4.0,  # ADJUSTED 2026-01-20: Changed from 6% to 4% for better trade completion in volatile market
        ge=1.0,
        le=50.0,
        description="Default take profit as % from entry (4% for 2:1 R/R ratio with 2% SL, better for current market)",
    )

    # Signal Thresholds - RESEARCH-BACKED (2025-12-23)
    # Professional standard: 65-75% confidence for automated trading
    # Research shows: 75-85% win rate at 65%+ confidence
    # ADJUSTED 2026-02-25: Lowered to 40% to sync with aggregator and enable trading
    min_signal_confidence: float = Field(
        default=0.40,  # SYNCED to 40% to match aggregator (enables trading in current market)
        ge=0.0,
        le=1.0,
        description="SYNCED: 40% to match aggregator - enables trading while filtering noise",
    )
    # Need 3 indicators from different categories for consensus
    min_consensus_indicators: int = Field(
        default=3,
        ge=1,
        le=10,
        description="USER CONFIG: 3 indicators minimum for balanced consensus",
    )
    # Per-indicator rolling-confidence gate (2026-05-06)
    # When an operator flips an indicator from disabled -> enabled via the
    # admin endpoint, the registry's rolling-mean confidence over the last
    # 200 calls must be >= this value or the enable is refused. This stops
    # silent re-enablement of stuck indicators (RSI_DIVERGENCE @ 0.20,
    # SQZMOM_ENHANCED @ 0.50). Does NOT affect voting for currently-active
    # indicators. See app/services/indicator_registry.py.
    min_indicator_confidence: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum rolling-mean confidence (window=200) required before an "
            "indicator may be re-enabled by the admin endpoint."
        ),
    )

    # Time-Based Trading Filters (RESEARCH-BACKED 2025-12-01)
    # Best trading hours: 14:00-17:00 UTC (London/NY overlap)
    # Avoid: weekends, early morning UTC, low volume periods
    enable_time_filters: bool = Field(
        default=True, description="Enable time-based trade filtering for quality"
    )
    trading_start_hour_utc: int = Field(
        default=1,
        ge=0,
        le=23,
        description="Start trading hour UTC (1:00 = Asia/Europe overlap - OPTIMIZED 2026-01-19)",
    )
    trading_end_hour_utc: int = Field(
        default=21, ge=0, le=23, description="End trading hour UTC (21:00 = US close)"
    )
    avoid_weekends: bool = Field(
        default=True, description="Avoid trading on weekends (lower volume)"
    )

    # ===========================================================================
    # POSITION HOLD TIME LIMITS (Added 2026-01-14) - CRITICAL FIX
    # ===========================================================================
    # Problem: SOLUSDT SHORT held for 185 hours (7.7 days) resulting in -$14.33 loss
    # Solution: Force close positions after 48 hours to prevent catastrophic losses
    max_position_hold_hours: int = Field(
        default=48,  # Force exit after 48 hours (2 days)
        ge=1,
        le=720,  # Max 30 days
        description="Maximum hours to hold a position before forced exit (prevents holding losers)",
    )
    enable_max_hold_time: bool = Field(
        default=True,
        description="Enable automatic position closure after max hold time",
    )

    # ===========================================================================
    # TRADE SIDE RESTRICTIONS (Updated 2026-01-19) - OPTION C: HYBRID CIRCUIT BREAKER
    # ===========================================================================
    # Analysis: Backtest shows SHORT trading has +2-4% monthly profit potential in current bearish conditions
    # Recent analysis (Jan 19, 2026) confirms SHORT trades are profitable in current market
    # Solution: Enable SHORT with TIGHTER risk controls + automatic circuit breaker
    allowed_trade_sides: List[str] = Field(
        default=["LONG", "SHORT"],  # Both sides enabled for market adaptability
        description="Allowed trade sides: ['LONG', 'SHORT'] for market adaptability",
    )
    short_trading_enabled: bool = Field(
        default=True,  # SHORT trading enabled based on recent profitable analysis
        description="Enable SHORT trading for current market conditions",
    )

    # ===========================================================================
    # SHORT TRADING RISK CONTROLS (Added 2026-01-19) - TIGHTER THAN LONG
    # ===========================================================================
    # Rationale: SHORT trading has higher risk, requires stricter controls
    # Backtest basis: 30d LONG strategies had 41.3% WR, -0.002% return
    #                 SHORT expected: 57-59% WR, +2-4% return (inverse conditions)
    short_stop_loss_pct: float = Field(
        default=1.5,  # TIGHTER: 1.5% vs 2.0% for LONG (25% tighter)
        ge=0.5,
        le=5.0,
        description="SHORT stop loss: 1.5% (tighter than LONG's 2.0%)",
    )
    short_min_confidence: float = Field(
        default=0.70,  # HIGHER: 70% vs 65% for LONG (higher bar)
        ge=0.5,
        le=1.0,
        description="SHORT minimum confidence: 70% (higher than LONG's 65%)",
    )
    short_max_position_pct: float = Field(
        default=3.0,  # SMALLER: 3% vs 5% for LONG (40% smaller)
        ge=0.5,
        le=10.0,
        description="SHORT max position size: 3% (smaller than LONG's 5%)",
    )

    # ===========================================================================
    # CIRCUIT BREAKER (Added 2026-01-19) - AUTOMATIC SHORT SAFETY SHUTDOWN
    # ===========================================================================
    # Purpose: Automatically disable SHORT if underperforms, protecting capital
    # Trigger: If ANY condition breached during evaluation period → disable SHORT
    # Recovery: Requires manual re-enable after review
    circuit_breaker_enabled: bool = Field(
        default=True, description="Enable automatic SHORT shutdown on poor performance"
    )
    circuit_breaker_max_consecutive_losses: int = Field(
        default=3,  # Disable after 3 losses in a row
        ge=2,
        le=10,
        description="Auto-disable SHORT after N consecutive losses",
    )
    circuit_breaker_max_drawdown_pct: float = Field(
        default=10.0,  # Disable if portfolio drops 10%
        ge=3.0,
        le=25.0,
        description="Auto-disable SHORT if drawdown exceeds %",
    )
    circuit_breaker_min_win_rate_pct: float = Field(
        default=45.0,  # Disable if win rate falls below 45%
        ge=30.0,
        le=60.0,
        description="Auto-disable SHORT if win rate below % (after evaluation period)",
    )
    circuit_breaker_evaluation_trades: int = Field(
        default=30,  # Evaluate after 30 trades
        ge=10,
        le=100,
        description="Number of SHORT trades before evaluating circuit breaker",
    )
    circuit_breaker_check_interval_minutes: int = Field(
        default=60,  # Check every hour
        ge=15,
        le=1440,
        description="How often to check circuit breaker conditions (minutes)",
    )

    # Database Configuration
    # Port 5432 is the in-container TimescaleDB port. The host-mapped port
    # (5433 in docker-compose.unified.yml) is for tooling on the host only —
    # never the right value when this service runs inside the docker network.
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="trading_engine")
    postgres_user: str = Field(default="cryptobot")
    postgres_password: str = Field(default="")

    # Redis Configuration
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=2)
    redis_password: str = Field(default="")

    # Paper Trading
    paper_initial_balance: float = Field(
        default=100.0,
        ge=100.0,
        description="Initial balance for paper trading (matches portfolio-manager initial_capital and risk-budget base_equity)",
    )
    paper_commission_pct: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Commission percentage for paper trading",
    )

    # =========================================================================
    # LEVERAGE CONFIGURATION (Added 2025-12-15)
    # =========================================================================
    # Bybit-style leverage: Initial Margin = Position Value / Leverage
    # Example: $100 position with 10x leverage = $10 margin required
    leverage_enabled: bool = Field(
        default=False, description="Enable leverage trading (Bybit style)"
    )
    default_leverage: float = Field(
        default=1.0,
        ge=1.0,
        le=100.0,
        description="Default leverage multiplier (1x = no leverage, 10x = 10x leverage)",
    )
    max_leverage: float = Field(
        default=20.0, ge=1.0, le=100.0, description="Maximum allowed leverage"
    )
    min_leverage: float = Field(default=1.0, ge=1.0, description="Minimum leverage")

    # =========================================================================
    # SECURITY CONFIGURATION (Added 2025-12-12)
    # =========================================================================

    # CORS Configuration - Strict mode for production
    cors_origins: List[str] = Field(
        default=[
            "http://localhost:3000",  # React frontend development
            "http://localhost:8000",  # API Gateway
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
        ],
        description="Allowed CORS origins (no wildcards in production)",
    )

    # Internal service origins (for microservice communication)
    internal_service_origins: List[str] = Field(
        default=[
            "http://api-gateway:8000",
            "http://localhost:8000",
            "http://localhost:8001",
            "http://localhost:8002",
            "http://localhost:8003",
            "http://localhost:8004",
            "http://localhost:8005",
            "http://localhost:8006",
            "http://localhost:8007",
            "http://localhost:8008",
        ],
        description="Internal microservice origins for inter-service communication",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.upper()

    @field_validator("trading_mode")
    @classmethod
    def validate_trading_mode(cls, v):
        """Validate trading mode"""
        if v.upper() not in ["PAPER", "LIVE"]:
            raise ValueError("Trading mode must be PAPER or LIVE")
        return v.upper()

    def validate_allocations(self) -> None:
        """
        Validate symbol allocations sum to 1.0 and all trading symbols have allocations

        Raises:
            ValueError: If allocations are invalid
        """
        # Check allocations sum to 1.0 (with small tolerance for floating point)
        total = sum(self.symbol_allocations.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"Symbol allocations sum to {total:.4f}, must equal 1.0. "
                f"Current allocations: {self.symbol_allocations}"
            )

        # Ensure all trading symbols have allocations
        for symbol in self.trading_symbols:
            if symbol not in self.symbol_allocations:
                raise ValueError(
                    f"Symbol '{symbol}' in trading_symbols but missing from "
                    f"symbol_allocations. Please add allocation for '{symbol}' "
                    f"or remove it from trading_symbols."
                )

        # Warn if there are allocations for symbols not in trading list
        extra_symbols = set(self.symbol_allocations.keys()) - set(self.trading_symbols)
        if extra_symbols:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"Allocations defined for symbols not in trading_symbols: {extra_symbols}. "
                f"These allocations will be ignored."
            )

    @property
    def all_cors_origins(self) -> List[str]:
        """Get combined list of all allowed CORS origins"""
        return list(set(self.cors_origins + self.internal_service_origins))

    @property
    def database_url(self) -> str:
        """Get database connection URL"""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        """Get Redis connection URL"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create settings instance"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment"""
    global _settings
    _settings = Settings()
    return _settings
