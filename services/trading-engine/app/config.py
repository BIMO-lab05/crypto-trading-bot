"""
Configuration Module for Trading Engine
Purpose: Centralized configuration management using Pydantic settings

SECURITY UPDATE (2025-12-12): Added strict CORS configuration
"""

import json
import os

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, EnvSettingsSource, SettingsConfigDict
from typing import Literal, List, Dict

# Fields where a BLANK env value means "operator did not set it" — the compose
# passthrough is `TRADING_SYMBOLS=${TRADING_SYMBOLS:-}`, so an unset .env key
# arrives as "". pydantic-settings JSON-decodes complex fields at the SOURCE
# layer, before any field validator runs, so "" raised SettingsError and the
# container never booted. NoDecode would fix this but exists only in
# pydantic-settings >= 2.6; the image pins 2.1.0, so the blank-handling lives
# in a source subclass instead (decode_complex_value exists in both).
_BLANK_MEANS_DEFAULT_FIELDS = frozenset({"trading_symbols", "symbol_allocations"})


class _BlankTolerantEnvSource(EnvSettingsSource):
    def decode_complex_value(self, field_name, field, value):
        if (
            field_name in _BLANK_MEANS_DEFAULT_FIELDS
            and isinstance(value, str)
            and not value.strip()
        ):
            return field.default
        return super().decode_complex_value(field_name, field, value)


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
        default="http://localhost:8003", description="Portfolio Manager Service URL"
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
    auto_trading_enabled: bool = Field(default=False, description="Enable automatic trading")
    emergency_stop_file: str = Field(
        default="/app/EMERGENCY_STOP",
        description="Path to file-based kill switch. If file exists, auto-trader refuses to start and halts the loop.",
    )
    default_strategy: str = Field(default="consensus", description="Default trading strategy")
    default_symbol: str = Field(default="BTCUSDT", description="Default trading symbol")
    # Blank env value maps to this default via _BlankTolerantEnvSource above;
    # non-blank values are JSON-decoded normally and still face
    # validate_allocations().
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
    # Blank-tolerant for the same reason as trading_symbols above — the two
    # must be overridable together or the pair goes incoherent.
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

    default_interval: str = Field(default="60", description="Default candlestick interval")

    # Strategy Mode - STANDARD for more trading opportunities (2026-02-24)
    # Options: standard, research, hybrid, grid_trading
    # CHANGED: From 'hybrid' to 'standard' to enable trading in ranging market conditions
    strategy_mode: str = Field(
        default="standard",
        description="Trading strategy mode: standard (more active), research, hybrid (dual confirmation), or grid_trading",
    )

    # Regime routing threshold (2026-08-21). Previously hardcoded at
    # HybridStrategyRouter.__init__ as `self.ADX_TRENDING_THRESHOLD = 25.0`,
    # which the dashboard advertised as the routing rule while the router
    # itself was never invoked (docs/PIPELINE_MAP.md §0). Lifted to config so
    # the value the UI claims and the value the code applies are the same
    # object, and so Phase-3 recalibration can move it without a code edit.
    #
    # 25.0 is the conventional Wilder ADX trend threshold and matches
    # technical-analysis `default_adx_trending_threshold`. Do NOT diverge the
    # two without recording why — the TA service classifies the regime string
    # the confidence-modifier path consumes, this one classifies the routing
    # branch, and a split would make the tile disagree with the engine.
    adx_trending_threshold: float = Field(
        default=25.0,
        ge=0.0,
        le=100.0,
        description=(
            "ADX at or above which the strategy router classifies TRENDING "
            "(trend-following branch); below it, RANGING (mean-reversion "
            "branch). Mirrors technical-analysis default_adx_trending_threshold."
        ),
    )

    # Mirror-literal cluster (P21-7, 2026-08-27; audit
    # `.planning/audits/2026-08-26-ta-signal-path-audit.md`). The two fields
    # below lift numbers that engine code hardcoded while the
    # technical-analysis service declared its own copy:
    #   - `signal_aggregator.fetch_adx` — `adx_val >= 20.0`, the gate deciding
    #     whether ADX may emit a directional vote at all.
    #   - `sqzmom_strategy_integration` — `adx_val < 20.0`, the SQZMOM
    #     demote-to-HOLD trend-strength gate.
    #   - `sqzmom_strategy_integration` — `ratio < 1.2`, the SQZMOM
    #     volume-confirmation gate.
    # Each agreed with its counterpart only by coincidence: nothing read one
    # from the other, so a single env override on the TA side would have moved
    # one number and left the engine applying the old one, silently. Lifting
    # them to declared fields makes any override deliberate on both sides.
    # NO THRESHOLD VALUE CHANGED — 20.0 and 1.2 are the literals they replace.

    # 20.0 is the conventional Wilder weak-trend floor and matches
    # technical-analysis `default_adx_weak_trend_threshold`. Do NOT diverge the
    # two without recording why — TA uses it to label the regime string it
    # publishes (`RANGING` below it, `WEAK_TREND` at or above), while the engine
    # uses it to decide whether ADX votes and whether a SQZMOM signal survives
    # its trend gate. A split would let the engine trade a bar the dashboard is
    # simultaneously calling RANGING.
    adx_weak_trend_threshold: float = Field(
        default=20.0,
        ge=0.0,
        le=100.0,
        description=(
            "ADX at or above which the engine lets ADX emit a directional "
            "BUY/SELL vote, and at or above which the SQZMOM gate accepts a "
            "directional action instead of demoting it to HOLD. Mirrors "
            "technical-analysis default_adx_weak_trend_threshold."
        ),
    )

    # Mirror-literal cluster, second tranche (DEFER-21-03, 2026-08-27; recorded
    # in `.planning/phases/21-ta-aggregator-widening-leakage-net/deferred-items.md`).
    # Three more numbers the engine hardcoded while technical-analysis declared
    # its own copy, all on the traded signal path:
    #   - `signal_aggregator.fetch_rsi` — the RSI lookback default the engine
    #     sent on every RSI request. TA declares `default_rsi_period`.
    #   - `signal_aggregator.fetch_bollinger_bands` — the band-width multiplier
    #     on the outbound request params. TA declares `default_bb_std`.
    #   - `signal_aggregator.fetch_trend_filter` — the kline count on the
    #     outbound request params. TA declares `default_trend_limit`.
    # Same defect shape as the tranche above: each agreed with its counterpart
    # only by coincidence, so a single TA-side override would have moved the TA
    # number and left the engine sending the old one, silently.
    #
    # These three requests deliberately KEEP sending their parameters. That is
    # the opposite of the contract `tests/test_engine_param_omission.py` holds
    # for fetch_sma/fetch_ema/fetch_macd/fetch_ichimoku (where the engine must
    # NOT send what TA owns); 22.1-CONTEXT item B locks engine-Settings routing
    # here instead, so do not "fix" these into omission.
    #
    # The ge/le bounds on `bollinger_std_dev` and `trend_filter_kline_limit`
    # are deliberately the bounds technical-analysis already enforces on its
    # own routes (band multiplier 1.0-4.0 in TA `handlers/indicators.py`,
    # trend kline count 200-1000 in TA `main.py`), so an engine-side override
    # that TA's endpoint would reject cannot even be declared: it fails here,
    # at Settings construction, instead of arriving as a 422 from a service
    # that is not this one. `rsi_period` is the exception: TA's RSI routes
    # accept ge=2/le=200 while the engine caps at le=100 — TIGHTER than TA,
    # so every engine-legal value is still TA-legal, but a TA-legal override
    # like RSI_PERIOD=150 fails engine Settings construction (review 22.1
    # IN-01; widen le if such an override is ever actually wanted).
    # NO VALUE CHANGED — 9, 2.5 and 300 are the literals they replace.
    rsi_period: int = Field(
        default=9,
        ge=2,
        le=100,
        description=(
            "RSI lookback the engine sends on its outbound RSI request. "
            "Mirrors technical-analysis default_rsi_period. An explicit "
            "caller-supplied period still outranks this default."
        ),
    )

    bollinger_std_dev: float = Field(
        default=2.5,
        ge=1.0,
        le=4.0,
        description=(
            "Standard-deviation multiplier the engine sends on its outbound "
            "Bollinger Bands request (widened for crypto volatility). Mirrors "
            "technical-analysis default_bb_std; the bounds are TA's own route "
            "bounds."
        ),
    )

    trend_filter_kline_limit: int = Field(
        default=300,
        ge=200,
        le=1000,
        description=(
            "Number of klines the engine asks the trend-filter endpoint to "
            "load; the 50/200 EMA pair needs that much history to be defined. "
            "Mirrors technical-analysis default_trend_limit; the bounds are "
            "TA's own route bounds."
        ),
    )

    # Mirror-literal cluster, third tranche (DEFER-21-04, 2026-08-27; recorded
    # in `.planning/phases/21-ta-aggregator-widening-leakage-net/deferred-items.md`).
    # One number, declared three times. The ADX lookback the two dormant
    # trend-following strategies compute with was:
    #   - `strategies/trend_following.py` — an `adx_period` field on the
    #     `TrendFollowingConfig` dataclass, read by that file's local ADX
    #     calculation.
    #   - `strategies/trend_following_strategy.py` — a module constant
    #     `ADX_PERIOD`, which in turn defaulted a constructor parameter no
    #     caller ever passed, that file's own local ADX calculation, and its
    #     warm-up length check.
    #
    # READ THIS BEFORE TREATING IT LIKE THE TRANCHE ABOVE: this is NOT a
    # request parameter. Neither trend-following file contains an HTTP client
    # — both compute ADX LOCALLY from OHLCV arrays, so there is no outbound
    # ADX request here to omit anything from, and the omission contract in
    # `tests/test_engine_param_omission.py` does not apply to these sites.
    # This field is the engine-side declaration of the same lookback
    # technical-analysis declares for its own /indicators/adx endpoint
    # (`default_adx_period`). Both were 14 and nothing read one from the
    # other: they agreed by coincidence, which means a single deliberate
    # change on the TA side would have moved TA's number and left the engine
    # computing with the old one, silently.
    #
    # Consequence worth knowing: `create_trend_following_strategy` applies
    # `config_overrides` behind a `hasattr` guard, so an `adx_period` key
    # passed there is no longer an accepted override — it would be dropped
    # without an error. Move this Settings field instead.
    # NO VALUE CHANGED — 14 is the literal it replaces.
    adx_period: int = Field(
        default=14,
        ge=2,
        le=200,
        description=(
            "ADX lookback the engine's trend-following strategies compute "
            "with locally. Mirrors technical-analysis default_adx_period, "
            "which that service resolves for its own ADX endpoint. An "
            "explicit caller-supplied period still outranks this default."
        ),
    )

    # `sqzmom_volume_ratio_min` has NO technical-analysis counterpart. The TA
    # volume endpoint returns `ratio` and `confirmed` but declares no
    # minimum-ratio setting, so this threshold is engine-owned rather than
    # mirrored — do not go looking for a `default_volume_ratio_min` in the TA
    # Settings, there is none. If one is ever added there, wire it through here
    # in the same commit; declaring it on both sides unwired would recreate the
    # exact split this block exists to close.
    sqzmom_volume_ratio_min: float = Field(
        default=1.2,
        ge=0.0,
        le=10.0,
        description=(
            "Minimum volume ratio (release-bar volume / volume SMA) the SQZMOM "
            "gate requires before allowing a directional action; below it the "
            "action is demoted to HOLD. Engine-owned: the technical-analysis "
            "service declares no counterpart for this value."
        ),
    )

    # Strategy routing mode (2026-08-21).
    #   advisory  — the router classifies the regime and records the branch it
    #               WOULD have taken on every evaluation, but execution is
    #               unchanged (the configured strategy_mode still decides).
    #   off       — no routing observation at all.
    # `executing` is NOT a value here: a router that actually selects the
    # sub-strategy is what STRATEGY_MODE=hybrid already does, and promoting
    # the observer to an executor is a strategy change that must go through
    # replay evidence, not a flag. See docs/PIPELINE_MAP.md §6.
    # Gatekeeper (counter-trend trend-filter) knobs — 2026-08-21.
    # Previously bare literals in TrendGatekeeper.check_signal, and the class
    # docstring claimed 0.9 while the code applied 0.95. Lifted to config so
    # the funnel can report "observed trend_confidence vs the threshold that
    # rejected it" against a value that actually exists, and so Phase-3
    # recalibration does not require a code edit.
    #
    # Reachability note before changing this: TREND_FILTER confidence is
    # min(abs(ema50_ema200_spread_pct) / 0.05, 1.0), so 0.95 needs a 4.75%
    # EMA50/EMA200 spread. The block branch is close to unreachable in
    # practice — the penalty branch is what actually fires.
    gatekeeper_block_threshold: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description=(
            "TREND_FILTER confidence at or above which a counter-trend signal "
            "is blocked outright rather than penalised."
        ),
    )
    gatekeeper_block_penalty: float = Field(
        default=0.30,
        gt=0.0,
        le=1.0,
        description="Confidence multiplier applied to a blocked counter-trend signal.",
    )
    gatekeeper_counter_trend_penalty: float = Field(
        default=0.95,
        gt=0.0,
        le=1.0,
        description=(
            "Confidence multiplier applied to a counter-trend signal that is "
            "penalised but not blocked."
        ),
    )

    strategy_routing_mode: str = Field(
        default="advisory",
        description=(
            "advisory: record the regime branch the router would pick on every "
            "evaluation without changing execution. off: disable observation."
        ),
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
            "Bumped 2026-05-06 from 5% to 10% to align with the per-trade "
            "10% target; retained at the $10,000 balance per ADR-029."
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
            "Bumped 2026-05-06 from 0.02 to 0.10 (then a $100 min-notional "
            "workaround); retained at $10,000 as deliberate operator choice "
            "per ADR-029 — 10% = $1,000/trade. Restore 0.02 before LIVE."
        ),
    )
    # Ensemble sizing cascade (2026-05-07) — see ADR-015.
    # Replaces hardcoded constants in multi_strategy_ensemble.py that ignored
    # max_risk_per_trade and clamped trades to 1-3% of capital.
    # Formula: max(min_pos, min(cap, confidence × cap × multiplier))
    # where cap = max_risk_per_trade.
    # Default multiplier 3.7 chosen so confidence ≈ 0.27 (the documented
    # ensemble ceiling per ADR-013 — 7 voting legs × typical conf 0.16-0.50)
    # produces a trade at the cap. Default min 0.05 originally ensured a fired
    # trade cleared min-notional on the old $100 balance; retained at $10,000
    # per ADR-029 (floor = $500/trade).
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
        default=12.0,
        ge=1.0,
        le=20.0,
        description=(
            "Maximum daily loss as % of capital. Reads MAX_DAILY_LOSS_PCT env. "
            "Raised 2026-08-03 from 5.0 to 12.0 per ADR-028: at the ADR-010 "
            "per-trade cap of 10% ($10 on a $100 balance), a 5% daily limit "
            "($5) tripped on the FIRST full loss, so the breaker measured one "
            "trade rather than a day. 12% ($12) lets it fire on ~2 losers. "
            "This ALLOWS MORE daily loss -- it is a coherence fix, not a "
            "tightening. Reconcile with max_risk_per_trade before LIVE."
        ),
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
    # ADJUSTED 2026-05-20: Lowered to 30% to re-sync with aggregator after 2026-05-15
    # raised aggregator min_confidence 0.20→0.30 (commit b53a0ae) without touching
    # this downstream gate. Symptom: 5+ months zero fills despite signals computing;
    # aggregator could not emit anything ≥ this 0.40 floor after the cascade
    # (multi-timeframe WEAK alignment shaves another 0.90x post-aggregator).
    min_signal_confidence: float = Field(
        default=0.30,  # SYNCED to aggregator floor (raised 2026-05-15 to 0.30)
        ge=0.0,
        le=1.0,
        description="SYNCED: 30% to match aggregator (raised 2026-05-15) - cascade reachability fix",
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
    # TRADE SIDE RESTRICTIONS (Updated 2026-01-19)
    # ===========================================================================
    # Analysis: Backtest shows SHORT trading has +2-4% monthly profit potential in current bearish conditions
    # Recent analysis (Jan 19, 2026) confirms SHORT trades are profitable in current market
    # Solution: Enable SHORT with TIGHTER risk controls
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
    # short_min_confidence history: shipped 2026-01-19 at 0.70 claiming "higher
    # than LONG's 0.65" — but the live LONG floor is min_signal_confidence=0.30,
    # and the 3-leg ensemble's structural SELL ceiling is ~0.60 (leg SELL caps:
    # simple_rsi 0.80, mean_reversion 1.00, aggregator observed 0; weights
    # frozen at 1/3 each), so 0.70 was mathematically unreachable — 379 of 623
    # SELL signals died at this gate in one run, all-time max recorded ensemble
    # confidence 0.3804. Lowered to 0.35 on 2026-08-20.
    short_min_confidence: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description=(
            "SHORT minimum confidence: 0.35 — modestly above the LONG floor "
            "(min_signal_confidence=0.30) to demand extra conviction for "
            "shorts, below the ~0.60 structural ensemble SELL ceiling so the "
            "gate is reachable."
        ),
    )
    # DELETED 2026-08-12 (audit finding 6): short_max_position_pct and the six
    # circuit_breaker_* fields were declared 2026-01-19 and read by no code in
    # the repo. short_max_position_pct is not resurrected: 3% of a $100 account
    # is $3, under the ~$5 venue minimum, so enforcing it under
    # reject-don't-clamp would silently end all SHORT trading. The equity /
    # consecutive-loss halt that these breaker fields described is implemented
    # by KillSwitchConfig (auto_trader.py), on its own thresholds.

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
        default=10000.0,
        ge=100.0,
        description="Initial balance for paper trading (ADR-029, was 100.0; matches portfolio-manager initial_capital and risk-budget base_equity)",
    )
    paper_commission_pct: float = Field(
        default=0.055,
        ge=0.0,
        le=1.0,
        description=(
            "Commission percentage per side for paper trading. "
            "0.055 = Bybit linear-perp taker fee (0.055%/side). "
            "Was 0.1 until 2026-08-04 (AUDIT.md §6.2): the engine over-charged "
            "fees ~1.8x vs the real venue, distorting every net-P&L figure."
        ),
    )
    paper_maker_commission_pct: float = Field(
        default=0.02,
        ge=0.0,
        le=1.0,
        description=(
            "Bybit linear-perp MAKER fee percentage per side (0.02%/side). "
            "Used ONLY by the paper maker simulation "
            "(execute_maker_order_with_fallback, quick-260826-o2h); the taker "
            "path keeps paper_commission_pct (0.055). A fee RATE as a config "
            "default is sanctioned; never an account-size literal."
        ),
    )

    # Paper slippage (PAPER-01, 2026-08-03). ON by default: a frictionless
    # paper fill overstates every P&L figure the engine reports. Set
    # PAPER_SLIPPAGE_ENABLED=false only for an explicit A/B comparison against
    # the old zero-slippage behaviour. Per-symbol figures and their sourcing
    # live in app/paper_slippage.py.
    paper_slippage_enabled: bool = Field(
        default=True,
        description="Apply an adverse per-symbol slippage model to paper fills",
    )
    paper_slippage_bps_by_symbol: Dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Per-symbol one-way slippage in basis points, merged over the "
            "built-in table in app/paper_slippage.py (JSON env override)"
        ),
    )
    paper_slippage_default_bps: float = Field(
        default=10.0,
        ge=0.0,
        description="Slippage in bps for symbols absent from the per-symbol table",
    )

    # Paper funding (PAPER-02). ON by default: a position held across an 8h
    # Bybit settlement pays or receives funding on the real venue, and omitting
    # it overstates P&L for longs in positive-funding regimes. Fetch failure
    # fails open to zero and LOGS that the leg is gross of funding - silence
    # must never become an assumed rate (costs.py:257-260).
    paper_funding_enabled: bool = Field(
        default=True,
        description=(
            "Charge/credit perp funding on paper closes for each settlement crossed during the hold"
        ),
    )

    # =========================================================================
    # EXECUTION / SMART ORDER ROUTER (RES-05, 2026-08-16)
    # =========================================================================
    # Grouped with the paper-slippage block above because both concern fill
    # mechanics rather than capital allocation.
    smart_router_small_order_threshold_usd: float = Field(
        default=1000.0,
        gt=0,
        description=(
            "Order notional in USD below which a single market order is the "
            "cheapest execution; above it the smart router prefers "
            "limit/TWAP/iceberg strategies. This is a MARKET-MICROSTRUCTURE "
            "CALIBRATION against Bybit order-book depth — it is NOT an "
            "account-size figure and must never be derived from one. Deriving "
            "it from equity would silently reclassify large orders as small as "
            "the account grows, which is the opposite of what the threshold is "
            "for. Env key: SMART_ROUTER_SMALL_ORDER_THRESHOLD_USD (Settings "
            "declares no env_prefix, so the key is the upper-cased field name)."
        ),
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

    @field_validator("trading_symbols", "symbol_allocations", mode="before")
    @classmethod
    def _blank_symbol_env_uses_default(cls, v, info):
        """Blank value means "operator did not set it" — use the default.

        The env path is handled earlier by _BlankTolerantEnvSource (the source
        layer decodes complex fields before validators run); this validator
        covers direct construction, e.g. Settings(trading_symbols=""). A
        malformed non-blank value still raises: silently trading an unintended
        symbol set is worse than refusing to boot.
        """
        if isinstance(v, str):
            if not v.strip():
                return cls.model_fields[info.field_name].default
            return json.loads(v)
        return v

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

    def warn_if_short_gate_unreachable(self) -> None:
        """Boot-time sanity check (log-only, never aborts startup).

        Under DEFAULT 1/3 leg weights the 3-leg ensemble's structural SELL
        confidence ceiling is ~0.60 (leg SELL caps: simple_rsi 0.80,
        mean_reversion 1.00, aggregator observed 0). Adaptive weights can
        raise that ceiling, so a floor >= 0.60 is flagged as unreachable
        under default weights rather than impossible outright. A floor at
        or below the general min_signal_confidence is inert - the general
        floor rejects first.
        """
        import logging

        logger = logging.getLogger(__name__)
        if self.short_min_confidence >= 0.60:
            logger.warning(
                f"short_min_confidence={self.short_min_confidence:.2f} >= 0.60 - "
                f"under default 1/3 ensemble weights, SELL ceiling ~0.60, so "
                f"SHORT entries cannot pass the ensemble gate (adaptive "
                f"weights can raise the ceiling). Lower it below 0.60 for "
                f"shorts to fire under default weights."
            )
        elif self.short_min_confidence <= self.min_signal_confidence:
            logger.warning(
                f"short_min_confidence={self.short_min_confidence:.2f} <= "
                f"min_signal_confidence={self.min_signal_confidence:.2f} - "
                f"SHORT-specific floor is inert; the general floor rejects "
                f"first."
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

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # Same precedence order as stock pydantic-settings; only the plain env
        # source is swapped for the blank-tolerant subclass defined above.
        return (
            init_settings,
            _BlankTolerantEnvSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )


# =============================================================================
# BOOT-TIME CAPITAL-ENV VALIDATION (2026-08-04, AUDIT.md workstream B task 5)
# =============================================================================
# Owner spec: missing capital/risk config must raise, never fall back to a
# default. Making these five Settings fields *required* (no default) was
# attempted first and rejected with evidence:
#   * tests/test_account_config_sync.py compares DECLARED defaults against
#     shared/account.py — required fields have default=PydanticUndefined, so
#     that mandated-green test fails by construction (4/4 parametrized cases).
#   * tests/conftest.py pins env_file=None and the host-test runbook
#     (.claude/rules/testing.md) does not export these env vars, so every
#     module importing app.main dies at collection with
#     "ValidationError: 5 validation errors for Settings ... Field required".
# So instead: defaults stay (they are the production values, enforced by the
# sync test), and any *containerized* boot must receive all five explicitly
# from the environment (docker-compose.unified.yml injects them — verified in
# AUDIT.md §2.1). A container missing one refuses to construct Settings.

REQUIRED_CAPITAL_ENV_VARS = (
    "PAPER_INITIAL_BALANCE",
    "MAX_RISK_PER_TRADE",
    "MAX_DAILY_LOSS_PCT",
    "MAX_POSITION_SIZE_PCT",
    "MAX_TOTAL_EXPOSURE_PCT",
)


def _running_in_container() -> bool:
    """True when executing inside a Docker container (/.dockerenv marker)."""
    return os.path.exists("/.dockerenv")


def assert_capital_env_present() -> None:
    """Raise loudly if any required capital/risk env var is absent.

    Called on every Settings construction when running in a container. Host
    runs (tests, backtests) are exempt: there the config-default path IS the
    production configuration (see tests/conftest.py).
    """
    missing = [key for key in REQUIRED_CAPITAL_ENV_VARS if not os.environ.get(key)]
    if missing:
        raise RuntimeError(
            "Refusing to boot: required capital/risk environment variables "
            f"are not set: {', '.join(missing)}. These must be injected "
            "explicitly (docker-compose.unified.yml does so); silently "
            "falling back to code defaults for money parameters is forbidden. "
            "See AUDIT.md §2.1 and CLAUDE.md §1."
        )


# Global settings instance
_settings: Settings | None = None


def _build_settings() -> Settings:
    """Construct Settings, enforcing capital-env presence inside containers."""
    if _running_in_container():
        assert_capital_env_present()
    return Settings()


def get_settings() -> Settings:
    """Get or create settings instance"""
    global _settings
    if _settings is None:
        _settings = _build_settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment"""
    global _settings
    _settings = _build_settings()
    return _settings
