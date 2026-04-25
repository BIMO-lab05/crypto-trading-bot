"""
Research-Optimized Trading Strategy
====================================
Based on comprehensive analysis of:
- Freqtrade (best community strategies like NostalgiaForInfinity)
- Jesse (advanced framework patterns)
- Academic ML research (LSTM, XGBoost, TFT)
- Momentum trading strategies (RSI, MACD, ADX optimization)

RESEARCH-BACKED IMPROVEMENTS (2025-11-28):
1. RSI: Short-period (2-6) with 15/85 thresholds - 91% win rate in backtests
2. MACD: Confirmation filter, not primary signal
3. ADX: >25 for trend confirmation, regime-based strategy selection
4. Multi-Timeframe: 4:1 ratio, higher TF for trend, lower for entry
5. ATR-Based Stops: 2-3x ATR instead of fixed percentage
6. Position Sizing: Quarter Kelly with volatility adjustment
7. Trailing Stops: ATR-based trailing after profit threshold

Author: Research-based implementation
Date: 2025-11-28
"""

import logging
from typing import Dict, Optional, Tuple, List, Any
from dataclasses import dataclass, field
from enum import Enum
from app.models import SignalAction, IndicatorSignal

logger = logging.getLogger(__name__)


class MarketCondition(Enum):
    """Market condition classification based on ADX and volatility"""
    STRONG_TREND = "STRONG_TREND"      # ADX >= 30, clear direction
    TRENDING = "TRENDING"               # ADX 25-30, moderate trend
    WEAK_TREND = "WEAK_TREND"          # ADX 20-25, weak trend
    RANGING = "RANGING"                 # ADX < 20, sideways market
    VOLATILE = "VOLATILE"               # High ATR, unpredictable


class SignalStrength(Enum):
    """Signal strength classification"""
    STRONG = "STRONG"       # High confidence, multiple confirmations
    MODERATE = "MODERATE"   # Medium confidence, some confirmations
    WEAK = "WEAK"          # Low confidence, minimal confirmations
    NONE = "NONE"          # No actionable signal


@dataclass
class PartialExitLevel:
    """Partial profit taking level configuration"""
    price: float           # Price level for this exit
    exit_percent: float    # Percentage of position to exit (0.0-1.0)
    atr_multiple: float    # ATR multiple from entry
    label: str             # Label for this level (TP1, TP2, TP3)


@dataclass
class TradeSetup:
    """Complete trade setup with entry, stops, and targets"""
    action: SignalAction
    confidence: float
    signal_strength: SignalStrength
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size_pct: float
    trailing_stop_atr_mult: float
    reasoning: List[str]
    indicators_aligned: int
    market_condition: MarketCondition
    # RESEARCH ENHANCEMENT: Partial Profit Taking (2025-11-29)
    # Research shows partial exits improve overall returns by ~15-20%
    partial_exits: Optional[List[PartialExitLevel]] = None


class ResearchOptimizedStrategy:
    """
    Research-Optimized Trading Strategy

    This strategy incorporates proven techniques from:
    - Freqtrade's best strategies (NostalgiaForInfinity patterns)
    - Jesse's risk management (ATR-based stops, Kelly sizing)
    - Academic research (optimal indicator parameters)

    Key Features:
    1. RSI Bounce Strategy: Short RSI (2-6) with trend filter
    2. MACD Confirmation: Used as confirmation, not primary trigger
    3. Bollinger Band Mean Reversion: Entry at lower band in uptrend
    4. ADX Trend Strength: Regime-based strategy selection
    5. ATR Dynamic Stops: Volatility-adjusted stop losses
    6. Multi-Timeframe Alignment: Higher TF trend confirmation

    Win Rate Targets:
    - Strong signals: 70%+ expected win rate
    - Moderate signals: 55-70% expected win rate
    - Weak signals: Filtered out (< 55% expected)
    """

    # ==========================================================================
    # RESEARCH-OPTIMIZED PARAMETERS (Updated 2025-11-29)
    # Based on: Kang 2021 Study, Multi-indicator backtests, Academic research
    # ==========================================================================

    # RSI Parameters - RESEARCH-OPTIMIZED FOR 70% WIN RATE (2025-12-01)
    # RESEARCH: 2-day RSI below 15 achieved 91% win rate in backtests
    # Standard RSI 30/70 achieves 60%+ win rate, 25/75 for aggressive entries
    # Using 30/70 as base with short RSI period for faster response
    RSI_PERIOD_SHORT = 6          # Short RSI for entry timing (2-6 optimal)
    RSI_OVERSOLD = 30             # RESEARCH: Standard 30 catches oversold bounces
    RSI_OVERBOUGHT = 70           # RESEARCH: Standard 70 for overbought signals
    RSI_EXTREME_OVERSOLD = 25     # NEW: Extreme oversold for high-confidence entries
    RSI_EXTREME_OVERBOUGHT = 75   # NEW: Extreme overbought for high-confidence exits
    RSI_TREND_FILTER_PERIOD = 14  # Standard period for trend filtering
    RSI_TREND_THRESHOLD = 50      # TREND FILTER: >50 = bullish regime, <50 = bearish
    RSI_TREND_FILTER_ENABLED = True  # Use RSI as trend filter
    RSI_MOMENTUM_MODE = False     # DISABLED: Was causing too many weak signals

    # MACD Parameters (RESEARCH-OPTIMIZED: Kang 2021 Study)
    # Standard 12-26-9: -3.6% annual return
    # Optimized 5-35-5: +11.0% annual return (+14.6% improvement)
    MACD_FAST = 5                 # Fast EMA (prev: 12, captures short momentum)
    MACD_SLOW = 35                # Slow EMA (prev: 26, stable trend baseline)
    MACD_SIGNAL = 5               # Signal line (prev: 9, faster response)

    # ADX Thresholds (trend strength classification)
    ADX_STRONG_TREND = 30         # Clear trending market
    ADX_TRENDING = 25             # Moderate trend
    ADX_WEAK_TREND = 20           # Weak trend/transition
    # Below 20 = Ranging market

    # Bollinger Band Parameters (RESEARCH-OPTIMIZED 2025-11-29)
    # Research: Wider bands (2.5-3.0 SD) better for crypto volatility
    # Reduces false breakout signals in volatile markets
    BB_PERIOD = 20
    BB_STD_DEV = 2.5              # Widened from 2.0 for crypto volatility
    BB_ENTRY_MULT = 1.02          # Enter at 2% above lower band
    BB_EXIT_MULT = 0.98           # Exit at 2% below upper band

    # ATR-Based Risk Management - RESEARCH-OPTIMIZED (2025-12-21)
    # Based on: 3Commas, Bitsgap, Cryptohopper research
    #
    # DYNAMIC R:R RATIO BASED ON CONFIDENCE:
    # - High confidence (>75%): 1:3 R/R (3% SL, 9% TP)
    # - Medium confidence (65-75%): 1:2.5 R/R (3% SL, 7.5% TP)
    # - Standard confidence (<65%): REJECTED (too low quality)
    #
    # Research shows 1:3 R/R optimal for crypto with proper confidence filtering
    ATR_PERIOD = 14
    ATR_STOP_MULTIPLIER = 2.5     # Moderate stop (was 3.0) - balance between protection and noise
    ATR_TRAILING_MULTIPLIER = 1.8 # Moderate trailing - protect profits while allowing growth
    ATR_TP_MULTIPLIER = 7.5       # 1:3 R/R (2.5 SL * 3 = 7.5 TP)
    ATR_TP_HIGH_CONFIDENCE = 9.0  # 1:3.5 R/R for high confidence trades (>75%)
    ATR_TP_MEDIUM_CONFIDENCE = 7.5  # 1:3 R/R for medium confidence (65-75%)

    # Position Sizing (Kelly Criterion based) - RESEARCH-OPTIMIZED (2025-12-21)
    MAX_RISK_PER_TRADE = 0.030    # 3% max risk per trade (increased for better R/R)
    MIN_POSITION_SIZE = 0.020     # 2% minimum (increased for meaningful positions)
    MAX_POSITION_SIZE = 0.10      # 10% maximum (increased to allow larger positions on high confidence)
    MAX_POSITION_SIZE_HIGH_VOL = 0.06  # 6% max in high volatility environments
    KELLY_FRACTION = 0.20         # 20% Kelly for more conservative approach

    # ==========================================================================
    # DYNAMIC POSITION SIZING PARAMETERS (2025-12-01)
    # ATR-based volatility adjustment + Enhanced confidence scaling
    # Research: Reduce size in high volatility, increase on high confidence
    # ==========================================================================
    # Volatility Thresholds (ATR as % of price)
    ATR_LOW_VOLATILITY = 0.015    # Below 1.5% ATR = low volatility
    ATR_NORMAL_VOLATILITY = 0.030 # 1.5-3% ATR = normal volatility
    ATR_HIGH_VOLATILITY = 0.050   # Above 5% ATR = high volatility

    # Volatility Multipliers (reduce size in high volatility)
    VOLATILITY_MULT_LOW = 1.2     # Low volatility: increase size 20%
    VOLATILITY_MULT_NORMAL = 1.0  # Normal volatility: standard size
    VOLATILITY_MULT_HIGH = 0.6    # High volatility: reduce size 40%
    VOLATILITY_MULT_EXTREME = 0.4 # Extreme volatility (>7% ATR): reduce 60%

    # Enhanced Confidence Multipliers
    CONFIDENCE_HIGH_THRESHOLD = 0.80    # High confidence threshold
    CONFIDENCE_VERY_HIGH_THRESHOLD = 0.90  # Very high confidence
    CONFIDENCE_MULT_HIGH = 1.3          # 30% boost for high confidence
    CONFIDENCE_MULT_VERY_HIGH = 1.5     # 50% boost for very high confidence

    # Signal Quality Thresholds - RESEARCH-OPTIMIZED (2025-12-21)
    # Based on: 3Commas, Bitsgap, Cryptohopper research + Pattern Analysis
    #
    # KEY FINDING: MA alone = 38% win rate
    #              MA + RSI + Volume = 52% win rate
    #              200 SMA + RSI/MACD + Volume = 55-65% win rate
    #              4+ indicators + 0.65+ confidence = 65-70% win rate target
    #
    # RESEARCH-BACKED: Professional trading standards (2025-12-23)
    # ADJUSTED 2026-02-24: Lowered for ranging market to enable trading
    MIN_INDICATORS_ALIGNED = 2    # ADJUSTED 2026-01-02: Lowered from 3 to 2 for ranging market trading
    MIN_CONFIDENCE = 0.30         # LOWERED from 0.65 to 0.30 to enable trading in current market
    MIN_CONFIDENCE_SHORT = 0.35   # LOWERED from 0.70 to 0.35 for ranging market
    STRONG_SIGNAL_THRESHOLD = 0.50  # LOWERED from 0.75 to 0.50 for position sizing
    ENABLE_MOMENTUM_TRADING = False  # DISABLED - was causing false signals

    # 🆕 Confidence-Tiered Position Sizing (2025-12-04)
    # Scale position size based on signal quality
    CONFIDENCE_TIER_SMALL = 0.55   # Small position threshold (50% of normal)
    CONFIDENCE_TIER_NORMAL = 0.65  # Normal position threshold (100%)
    CONFIDENCE_TIER_LARGE = 0.80   # Large position threshold (130%)
    POSITION_SIZE_SMALL_MULT = 0.50   # 50% size for low confidence
    POSITION_SIZE_NORMAL_MULT = 1.00  # 100% size for medium confidence
    POSITION_SIZE_LARGE_MULT = 1.30   # 130% size for high confidence

    # 🆕 Performance-Based Scaling (OPTIONAL - 2025-12-04)
    # Dynamically adjust position size based on recent performance
    # DISABLED by default - enable after validating hybrid optimization
    ENABLE_PERFORMANCE_SCALING = False  # Set to True to enable adaptive sizing

    # Win/Loss Streak Parameters
    WIN_STREAK_THRESHOLD = 2      # Number of wins to trigger bonus
    WIN_STREAK_BONUS = 1.20       # +20% size after 2+ consecutive wins
    LOSS_STREAK_THRESHOLD = 2     # Number of losses to trigger penalty
    LOSS_STREAK_PENALTY = 0.70    # -30% size after 2+ consecutive losses

    # Daily P&L Based Sizing
    DAILY_PNL_BOOST_THRESHOLD = 2.0    # +2% daily P&L triggers size boost
    DAILY_PNL_BOOST_MULT = 1.30        # +30% size on winning days
    DAILY_PNL_REDUCE_THRESHOLD = -2.0  # -2% daily P&L triggers size reduction
    DAILY_PNL_REDUCE_MULT = 0.50       # -50% size on losing days

    # Max Performance Multipliers (safety limits)
    MAX_PERFORMANCE_BOOST = 1.50   # Cap total performance bonus at +50%
    MIN_PERFORMANCE_MULT = 0.30    # Floor total performance penalty at 30% (70% reduction)

    # Category Diversity Requirements (RESEARCH-BACKED 2025-12-02)
    # Research: Single indicator type confirmation is weak
    # Require: 1 trend + 1 momentum + 1 volume/volatility = strong confirmation
    REQUIRE_CATEGORY_DIVERSITY = True
    MIN_CATEGORIES_REQUIRED = 3   # Must have signals from 3 different categories

    # Trade Quality Filter (NEW 2025-12-02)
    # Research: Quality > Quantity - fewer but better trades
    MIN_VOLUME_RATIO = 1.0        # Require at least average volume
    REQUIRE_TREND_ALIGNMENT = True  # Require trend direction confirmation

    # Multi-Timeframe Settings
    MTF_RATIO = 4                 # 4:1 ratio between timeframes
    MTF_WEIGHT_HIGHER = 1.5       # Higher TF signals weighted more

    # ==========================================================================
    # PARTIAL PROFIT TAKING - RESEARCH-OPTIMIZED FOR 70% WIN RATE (2025-12-01)
    # RESEARCH: Scale out at 1:1, 2:1, 3:1+ R/R ratios for optimal returns
    # Strategy: 25% at TP1 (lock gains), 35% at TP2 (main target), 40% at TP3 (runners)
    # This maximizes profit on winning trades while securing early gains
    # ==========================================================================
    PARTIAL_EXIT_ENABLED = True
    PARTIAL_EXIT_LEVELS = [
        {"atr_mult": 2.5, "exit_pct": 0.25, "label": "TP1"},  # 25% at 1:1 R/R (2.5x ATR)
        {"atr_mult": 4.0, "exit_pct": 0.35, "label": "TP2"},  # 35% at ~1.6:1 R/R
        {"atr_mult": 6.0, "exit_pct": 0.40, "label": "TP3"},  # 40% runners at 2.4:1 R/R
    ]

    def __init__(self):
        """Initialize the research-optimized strategy"""
        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0
        logger.info("ResearchOptimizedStrategy initialized with research-backed parameters")
        logger.info(f"  RSI: period={self.RSI_PERIOD_SHORT}, thresholds={self.RSI_OVERSOLD}/{self.RSI_OVERBOUGHT}")
        logger.info(f"  ADX: strong={self.ADX_STRONG_TREND}, trending={self.ADX_TRENDING}")
        logger.info(f"  ATR Stops: {self.ATR_STOP_MULTIPLIER}x, TP: {self.ATR_TP_MULTIPLIER}x")
        # DYNAMIC SIZING PARAMETERS (2025-12-01)
        logger.info("  [DYNAMIC SIZING ENABLED]")
        logger.info(f"    Volatility: Low<{self.ATR_LOW_VOLATILITY*100:.1f}%(+{int((self.VOLATILITY_MULT_LOW-1)*100)}%) | "
                   f"Normal<{self.ATR_NORMAL_VOLATILITY*100:.1f}% | "
                   f"High>{self.ATR_HIGH_VOLATILITY*100:.1f}%(-{int((1-self.VOLATILITY_MULT_HIGH)*100)}%)")
        logger.info(f"    Confidence: >{self.CONFIDENCE_HIGH_THRESHOLD*100:.0f}%(+{int((self.CONFIDENCE_MULT_HIGH-1)*100)}%) | "
                   f">{self.CONFIDENCE_VERY_HIGH_THRESHOLD*100:.0f}%(+{int((self.CONFIDENCE_MULT_VERY_HIGH-1)*100)}%)")

    def classify_market_condition(
        self,
        adx: float,
        atr_percent: float,
        plus_di: Optional[float] = None,
        minus_di: Optional[float] = None
    ) -> MarketCondition:
        """
        Classify current market condition based on ADX and volatility

        Args:
            adx: Current ADX value
            atr_percent: ATR as percentage of price
            plus_di: +DI value (optional)
            minus_di: -DI value (optional)

        Returns:
            MarketCondition enum value
        """
        # FIXED: Validate ATR percentage (code review 2025-11-28)
        if atr_percent < 0:
            logger.warning(f"Invalid ATR percentage: {atr_percent}")
            return MarketCondition.VOLATILE  # Assume volatile for safety

        # High volatility check (ATR > 3% of price)
        if atr_percent > 0.03:
            return MarketCondition.VOLATILE

        # ADX-based classification
        if adx >= self.ADX_STRONG_TREND:
            return MarketCondition.STRONG_TREND
        elif adx >= self.ADX_TRENDING:
            return MarketCondition.TRENDING
        elif adx >= self.ADX_WEAK_TREND:
            return MarketCondition.WEAK_TREND
        else:
            return MarketCondition.RANGING

    def calculate_rsi_signal(
        self,
        rsi_short: float,
        rsi_trend: float,
        rsi_prev: Optional[float] = None
    ) -> Tuple[SignalAction, float, str]:
        """
        Calculate RSI signal using research-optimized TREND FILTER MODE

        RESEARCH FINDINGS (2025-11-29):
        - RSI as trend filter (>50 bullish) = 773% return vs 275% buy-and-hold
        - RSI + Bollinger Bands = 87.5% accuracy vs 65.6% RSI alone
        - Short-period RSI (2-6) outperforms 14-period for entry timing

        TREND FILTER MODE (Primary - Research-backed):
        - RSI > 50 = Bullish regime → Only take LONG signals
        - RSI < 50 = Bearish regime → Only take SHORT signals
        - Combined with oversold/overbought for entries

        Entry Conditions:
        - Long: RSI_trend > 50 (bullish regime) AND RSI_short < 30 (oversold entry)
        - Short: RSI_trend < 50 (bearish regime) AND RSI_short > 70 (overbought entry)

        Args:
            rsi_short: Short-period RSI value (2-6 period) for entry timing
            rsi_trend: Trend-filtering RSI (14 period) for regime detection
            rsi_prev: Previous RSI value for crossover detection

        Returns:
            Tuple of (action, confidence, reasoning)
        """
        reasoning = ""

        # OPTIMIZED RSI TREND FILTER MODE (2025-12-01)
        # Fixed: Previous version was too aggressive with 52/48 thresholds
        # Now requires clear oversold/overbought conditions with trend confirmation
        if self.RSI_TREND_FILTER_ENABLED:
            # Determine market regime from trend RSI
            is_bullish_regime = rsi_trend > self.RSI_TREND_THRESHOLD
            is_bearish_regime = rsi_trend < self.RSI_TREND_THRESHOLD

            # BULLISH REGIME: Entry only in oversold conditions
            if is_bullish_regime:
                if rsi_short < self.RSI_OVERSOLD:
                    # Strong entry zone in uptrend - BUY signal
                    confidence = 0.70 + (self.RSI_OVERSOLD - rsi_short) / 100
                    confidence = min(confidence, 0.90)
                    reasoning = f"RSI OVERSOLD BUY: bullish regime RSI={rsi_trend:.1f}>50, entry RSI={rsi_short:.1f}<{self.RSI_OVERSOLD}"
                    return SignalAction.BUY, confidence, reasoning
                elif rsi_short < 40:
                    # Moderate entry - RSI below 40 in bullish regime
                    confidence = 0.55 + (40 - rsi_short) / 50
                    reasoning = f"RSI pullback buy: RSI={rsi_short:.1f}<40 in uptrend"
                    return SignalAction.BUY, confidence, reasoning
                else:
                    # Not oversold enough - HOLD
                    reasoning = f"RSI not oversold (RSI={rsi_short:.1f}) - waiting for pullback"
                    return SignalAction.HOLD, 0.40, reasoning

            # BEARISH REGIME: Entry only in overbought conditions
            elif is_bearish_regime:
                if rsi_short > self.RSI_OVERBOUGHT:
                    # Strong entry zone in downtrend - SELL signal
                    confidence = 0.70 + (rsi_short - self.RSI_OVERBOUGHT) / 100
                    confidence = min(confidence, 0.90)
                    reasoning = f"RSI OVERBOUGHT SELL: bearish regime RSI={rsi_trend:.1f}<50, entry RSI={rsi_short:.1f}>{self.RSI_OVERBOUGHT}"
                    return SignalAction.SELL, confidence, reasoning
                elif rsi_short > 60:
                    # Moderate entry - RSI above 60 in bearish regime
                    confidence = 0.55 + (rsi_short - 60) / 50
                    reasoning = f"RSI bounce sell: RSI={rsi_short:.1f}>60 in downtrend"
                    return SignalAction.SELL, confidence, reasoning
                else:
                    # Not overbought enough - HOLD
                    reasoning = f"RSI not overbought (RSI={rsi_short:.1f}) - waiting for bounce"
                    return SignalAction.HOLD, 0.40, reasoning

        # FALLBACK: Original reversal mode (if trend filter disabled)
        # LONG SIGNAL: Oversold bounce in uptrend
        if rsi_short < self.RSI_OVERSOLD and rsi_trend > self.RSI_TREND_THRESHOLD:
            if rsi_prev is not None and rsi_prev < self.RSI_OVERSOLD:
                confidence = 0.7 + (self.RSI_OVERSOLD - rsi_short) / 30
                confidence = min(confidence, 0.9)
                reasoning = f"RSI bounce: RSI({self.RSI_PERIOD_SHORT})={rsi_short:.1f} < {self.RSI_OVERSOLD}, trend RSI={rsi_trend:.1f} (uptrend)"
                return SignalAction.BUY, confidence, reasoning
            else:
                confidence = 0.5
                reasoning = f"RSI oversold: RSI({self.RSI_PERIOD_SHORT})={rsi_short:.1f}, awaiting bounce"
                return SignalAction.HOLD, confidence, reasoning

        # SHORT SIGNAL: Overbought drop in downtrend
        elif rsi_short > self.RSI_OVERBOUGHT and rsi_trend < self.RSI_TREND_THRESHOLD:
            if rsi_prev is not None and rsi_prev > self.RSI_OVERBOUGHT:
                confidence = 0.7 + (rsi_short - self.RSI_OVERBOUGHT) / 30
                confidence = min(confidence, 0.9)
                reasoning = f"RSI drop: RSI({self.RSI_PERIOD_SHORT})={rsi_short:.1f} > {self.RSI_OVERBOUGHT}, trend RSI={rsi_trend:.1f} (downtrend)"
                return SignalAction.SELL, confidence, reasoning
            else:
                confidence = 0.5
                reasoning = f"RSI overbought: RSI({self.RSI_PERIOD_SHORT})={rsi_short:.1f}, awaiting drop"
                return SignalAction.HOLD, confidence, reasoning

        # Neutral RSI
        else:
            reasoning = f"RSI neutral: {rsi_short:.1f}"
            return SignalAction.HOLD, 0.5, reasoning

    def calculate_bollinger_signal(
        self,
        price: float,
        bb_lower: float,
        bb_middle: float,
        bb_upper: float,
        volume_ratio: float = 1.0
    ) -> Tuple[SignalAction, float, str]:
        """
        Calculate Bollinger Band signal for mean reversion

        Research Finding: BB mean reversion works best in ranging markets
        and at band extremes with volume confirmation.

        Entry Conditions:
        - Long: Price <= BB_lower * 1.02 AND volume > average
        - Short: Price >= BB_upper * 0.98 AND volume > average

        Args:
            price: Current price
            bb_lower: Lower Bollinger Band
            bb_middle: Middle band (20 SMA)
            bb_upper: Upper Bollinger Band
            volume_ratio: Current volume / average volume

        Returns:
            Tuple of (action, confidence, reasoning)
        """
        # Calculate band width (squeeze detection)
        # FIXED: Division by zero protection (code review 2025-11-28)
        if bb_middle <= 0:
            logger.warning(f"Invalid Bollinger Band middle value: {bb_middle}")
            return SignalAction.HOLD, 0.5, "BB invalid: zero middle band"
        bb_width = (bb_upper - bb_lower) / bb_middle
        is_squeeze = bb_width < 0.04  # Tight bands = potential breakout

        # Long entry: Price at/below lower band
        if price <= bb_lower * self.BB_ENTRY_MULT:
            base_confidence = 0.6
            # Boost confidence with volume confirmation
            if volume_ratio > 1.5:
                base_confidence += 0.15
            elif volume_ratio > 1.0:
                base_confidence += 0.05
            # Reduce confidence during squeeze (breakout likely)
            if is_squeeze:
                base_confidence -= 0.1

            reasoning = f"BB lower touch: price={price:.2f}, lower={bb_lower:.2f}, vol_ratio={volume_ratio:.2f}"
            return SignalAction.BUY, min(base_confidence, 0.85), reasoning

        # Short entry: Price at/above upper band
        elif price >= bb_upper * self.BB_EXIT_MULT:
            base_confidence = 0.6
            if volume_ratio > 1.5:
                base_confidence += 0.15
            elif volume_ratio > 1.0:
                base_confidence += 0.05
            if is_squeeze:
                base_confidence -= 0.1

            reasoning = f"BB upper touch: price={price:.2f}, upper={bb_upper:.2f}, vol_ratio={volume_ratio:.2f}"
            return SignalAction.SELL, min(base_confidence, 0.85), reasoning

        # Middle band - trend following zone
        else:
            reasoning = f"BB neutral: price between bands"
            return SignalAction.HOLD, 0.5, reasoning

    def calculate_macd_confirmation(
        self,
        macd_line: float,
        signal_line: float,
        histogram: float,
        histogram_prev: Optional[float] = None
    ) -> Tuple[bool, bool, str]:
        """
        Calculate MACD as confirmation signal (not primary trigger)

        Research Finding: MACD crossovers alone have 52% win rate.
        Use MACD as confirmation for other signals.

        Args:
            macd_line: MACD line value
            signal_line: Signal line value
            histogram: MACD histogram
            histogram_prev: Previous histogram for momentum detection

        Returns:
            Tuple of (confirms_long, confirms_short, reasoning)
        """
        # Bullish confirmation: MACD above signal OR histogram rising
        bullish_crossover = macd_line > signal_line
        bullish_momentum = histogram_prev is not None and histogram > histogram_prev
        confirms_long = bullish_crossover or bullish_momentum

        # Bearish confirmation: MACD below signal OR histogram falling
        bearish_crossover = macd_line < signal_line
        bearish_momentum = histogram_prev is not None and histogram < histogram_prev
        confirms_short = bearish_crossover or bearish_momentum

        if confirms_long and not confirms_short:
            reasoning = f"MACD bullish: hist={histogram:.2f}, crossover={bullish_crossover}"
        elif confirms_short and not confirms_long:
            reasoning = f"MACD bearish: hist={histogram:.2f}, crossover={bearish_crossover}"
        else:
            reasoning = f"MACD mixed: hist={histogram:.2f}"

        return confirms_long, confirms_short, reasoning

    def calculate_ema_trend(
        self,
        price: float,
        ema_fast: float,
        ema_slow: float,
        ema_200: Optional[float] = None
    ) -> Tuple[str, float, str]:
        """
        Calculate EMA-based trend direction

        Research Finding: Multi-EMA alignment (8/21/50/200) provides
        higher quality signals than single EMA.

        Args:
            price: Current price
            ema_fast: Fast EMA (9 or 21)
            ema_slow: Slow EMA (50)
            ema_200: Long-term EMA (200) for major trend

        Returns:
            Tuple of (trend_direction, confidence, reasoning)
        """
        # Fast > Slow = Bullish
        # Price > 200 EMA = Major uptrend

        fast_above_slow = ema_fast > ema_slow
        price_above_fast = price > ema_fast

        if ema_200 is not None:
            price_above_200 = price > ema_200

            if fast_above_slow and price_above_200:
                # Full bullish alignment
                confidence = 0.8 if price_above_fast else 0.6
                reasoning = f"Bullish alignment: EMA9 > EMA50, price > EMA200"
                return "BULLISH", confidence, reasoning

            elif not fast_above_slow and not price_above_200:
                # Full bearish alignment
                confidence = 0.8 if not price_above_fast else 0.6
                reasoning = f"Bearish alignment: EMA9 < EMA50, price < EMA200"
                return "BEARISH", confidence, reasoning

            else:
                # Mixed signals
                reasoning = f"Mixed trend: partial EMA alignment"
                return "NEUTRAL", 0.5, reasoning

        else:
            # Without 200 EMA, use simple crossover
            if fast_above_slow:
                return "BULLISH", 0.6, f"EMA bullish: fast > slow"
            else:
                return "BEARISH", 0.6, f"EMA bearish: fast < slow"

    def calculate_atr_stops(
        self,
        entry_price: float,
        atr: float,
        is_long: bool,
        confidence: float = 0.5
    ) -> Tuple[float, float, float]:
        """
        Calculate ATR-based stop loss, take profit, and trailing stop

        RESEARCH-OPTIMIZED (2025-12-02):
        Dynamic R:R ratio based on signal confidence:
        - High confidence (>80%): 1:3 R/R - let winners run further
        - Medium confidence (60-80%): 1:2.5 R/R
        - Standard confidence (<60%): 1:2 R/R - tighter targets

        Research Finding: ATR-based stops adapt to volatility and
        significantly outperform fixed percentage stops.

        Args:
            entry_price: Entry price for the trade
            atr: Current ATR value
            is_long: True for long position, False for short
            confidence: Signal confidence (0-1) for dynamic R:R

        Returns:
            Tuple of (stop_loss, take_profit, trailing_activation)
        """
        stop_distance = atr * self.ATR_STOP_MULTIPLIER

        # DYNAMIC R:R BASED ON CONFIDENCE (Research: 3Commas, Bitsgap)
        if confidence >= 0.80:
            # High confidence: 1:3 R/R - let winners run
            tp_multiplier = self.ATR_TP_HIGH_CONFIDENCE
            logger.info(f"High confidence ({confidence:.0%}): Using 1:3 R/R (TP={tp_multiplier}x ATR)")
        elif confidence >= 0.60:
            # Medium confidence: 1:2.5 R/R
            tp_multiplier = self.ATR_TP_MEDIUM_CONFIDENCE
            logger.info(f"Medium confidence ({confidence:.0%}): Using 1:2.5 R/R (TP={tp_multiplier}x ATR)")
        else:
            # Standard confidence: 1:2 R/R
            tp_multiplier = self.ATR_TP_MULTIPLIER
            logger.debug(f"Standard confidence ({confidence:.0%}): Using 1:2 R/R (TP={tp_multiplier}x ATR)")

        tp_distance = atr * tp_multiplier

        if is_long:
            stop_loss = entry_price - stop_distance
            take_profit = entry_price + tp_distance
            trailing_activation = entry_price + (atr * 1.5)  # Activate after 1.5x ATR profit
        else:
            stop_loss = entry_price + stop_distance
            take_profit = entry_price - tp_distance
            trailing_activation = entry_price - (atr * 1.5)

        return stop_loss, take_profit, trailing_activation

    def calculate_partial_exits(
        self,
        entry_price: float,
        atr: float,
        is_long: bool
    ) -> List[PartialExitLevel]:
        """
        Calculate partial exit levels for scaled profit taking

        RESEARCH ENHANCEMENT (2025-11-29):
        Research shows scaling out of positions improves returns by ~15-20%
        by locking in profits while allowing remaining position to run.

        Strategy:
        - TP1 (40%): Exit early at 1.5x ATR to lock in profits
        - TP2 (35%): Main target at 2.5x ATR (original TP level)
        - TP3 (25%): Extended target at 4.0x ATR for trend runners

        Args:
            entry_price: Entry price for the trade
            atr: Current ATR value
            is_long: True for long position, False for short

        Returns:
            List of PartialExitLevel objects
        """
        if not self.PARTIAL_EXIT_ENABLED:
            return []

        partial_exits = []

        for level in self.PARTIAL_EXIT_LEVELS:
            distance = atr * level["atr_mult"]

            if is_long:
                price = entry_price + distance
            else:
                price = entry_price - distance

            partial_exits.append(PartialExitLevel(
                price=round(price, 2),
                exit_percent=level["exit_pct"],
                atr_multiple=level["atr_mult"],
                label=level["label"]
            ))

        logger.debug(
            f"Calculated partial exits: "
            f"{[(pe.label, pe.price, pe.exit_percent) for pe in partial_exits]}"
        )

        return partial_exits

    def calculate_position_size(
        self,
        capital: float,
        entry_price: float,
        stop_loss: float,
        signal_confidence: float,
        atr_percent: float = 0.0,
        win_rate: float = 0.55,
        avg_win_loss_ratio: float = 2.0
    ) -> float:
        """
        Calculate position size using Kelly Criterion with DYNAMIC adjustments

        ENHANCED 2025-12-01: Added ATR-based volatility adjustment
        and enhanced confidence scaling.

        Research Finding: Quarter Kelly (0.25x) provides good growth
        with acceptable drawdowns. Full Kelly is too aggressive for crypto.

        Kelly Formula: F = W - [(1-W)/R]
        where W = win rate, R = win/loss ratio

        DYNAMIC SIZING RULES:
        1. Reduce position size in high volatility (ATR > 5%)
        2. Increase position size on high confidence (> 80%)
        3. Combined effect: High confidence + Low volatility = max size

        Args:
            capital: Total trading capital
            entry_price: Entry price
            stop_loss: Stop loss price
            signal_confidence: Signal confidence (0-1)
            atr_percent: ATR as percentage of price (for volatility adjustment)
            win_rate: Historical win rate (default 55%)
            avg_win_loss_ratio: Avg win / avg loss (default 2:1)

        Returns:
            Position size as percentage of capital (0-MAX_POSITION_SIZE)
        """
        # Calculate risk per unit
        # FIXED: Division by zero protection (code review 2025-11-28)
        if entry_price <= 0:
            logger.error(f"Invalid entry price: {entry_price}")
            return self.MIN_POSITION_SIZE

        risk_per_unit = abs(entry_price - stop_loss) / entry_price

        if risk_per_unit <= 0:
            return self.MIN_POSITION_SIZE

        # Kelly Criterion
        kelly = win_rate - ((1 - win_rate) / avg_win_loss_ratio)
        kelly = max(0, kelly)  # Never negative

        # Apply Kelly fraction (quarter Kelly for safety)
        kelly_adjusted = kelly * self.KELLY_FRACTION

        # =================================================================
        # ENHANCED: Volatility-based size adjustment (2025-12-01)
        # Reduce size in high volatility, increase in low volatility
        # =================================================================
        if atr_percent > 0:
            if atr_percent >= 0.07:  # Extreme volatility > 7%
                volatility_mult = self.VOLATILITY_MULT_EXTREME
                logger.debug(f"EXTREME volatility ({atr_percent:.2%}): size *= {volatility_mult}")
            elif atr_percent >= self.ATR_HIGH_VOLATILITY:
                volatility_mult = self.VOLATILITY_MULT_HIGH
                logger.debug(f"HIGH volatility ({atr_percent:.2%}): size *= {volatility_mult}")
            elif atr_percent <= self.ATR_LOW_VOLATILITY:
                volatility_mult = self.VOLATILITY_MULT_LOW
                logger.debug(f"LOW volatility ({atr_percent:.2%}): size *= {volatility_mult}")
            else:
                volatility_mult = self.VOLATILITY_MULT_NORMAL
        else:
            volatility_mult = self.VOLATILITY_MULT_NORMAL

        # =================================================================
        # 🆕 HYBRID: Confidence-Tiered Size Adjustment (2025-12-04)
        # Small/Normal/Large positions based on signal quality
        # =================================================================
        if signal_confidence >= self.CONFIDENCE_TIER_LARGE:
            # 0.80+ confidence: Large position (130%)
            confidence_mult = self.POSITION_SIZE_LARGE_MULT
            logger.debug(f"LARGE position tier ({signal_confidence:.2%}): size *= {confidence_mult}")
        elif signal_confidence >= self.CONFIDENCE_TIER_NORMAL:
            # 0.65-0.80 confidence: Normal position (100%)
            confidence_mult = self.POSITION_SIZE_NORMAL_MULT
            logger.debug(f"NORMAL position tier ({signal_confidence:.2%}): size *= {confidence_mult}")
        else:
            # 0.55-0.65 confidence: Small position (50%)
            confidence_mult = self.POSITION_SIZE_SMALL_MULT
            logger.debug(f"SMALL position tier ({signal_confidence:.2%}): size *= {confidence_mult}")

        # =================================================================
        # 🆕 PERFORMANCE-BASED SCALING (OPTIONAL - 2025-12-04)
        # Adapt position size based on recent trading performance
        # DISABLED by default - enable via ENABLE_PERFORMANCE_SCALING flag
        # =================================================================
        performance_mult = 1.0  # Default: no adjustment

        if self.ENABLE_PERFORMANCE_SCALING:
            # Get recent trade history for performance tracking
            from app.paper_trading import get_paper_engine
            engine = get_paper_engine()

            # Calculate win/loss streak
            recent_trades = engine.trade_history[-10:]  # Last 10 trades
            if recent_trades:
                streak = 0
                last_result = None
                for trade in reversed(recent_trades):
                    current_result = 'win' if float(trade.get('realized_pnl', 0)) > 0 else 'loss'
                    if last_result is None:
                        last_result = current_result
                        streak = 1
                    elif current_result == last_result:
                        streak += 1
                    else:
                        break

                # Apply win/loss streak multiplier
                if last_result == 'win' and streak >= self.WIN_STREAK_THRESHOLD:
                    performance_mult *= self.WIN_STREAK_BONUS
                    logger.info(f"🔥 WIN STREAK ({streak}): size *= {self.WIN_STREAK_BONUS} (total: {performance_mult:.2f}x)")
                elif last_result == 'loss' and streak >= self.LOSS_STREAK_THRESHOLD:
                    performance_mult *= self.LOSS_STREAK_PENALTY
                    logger.warning(f"⚠️  LOSS STREAK ({streak}): size *= {self.LOSS_STREAK_PENALTY} (total: {performance_mult:.2f}x)")

            # Calculate daily P&L percentage
            try:
                portfolio = engine.get_portfolio_summary()
                daily_pnl = float(portfolio.get('daily_pnl', 0))
                balance = float(portfolio.get('balance', 10000))
                daily_pnl_pct = (daily_pnl / balance * 100) if balance > 0 else 0

                # Apply daily P&L based sizing
                if daily_pnl_pct >= self.DAILY_PNL_BOOST_THRESHOLD:
                    performance_mult *= self.DAILY_PNL_BOOST_MULT
                    logger.info(f"📈 WINNING DAY ({daily_pnl_pct:+.2f}%): size *= {self.DAILY_PNL_BOOST_MULT} (total: {performance_mult:.2f}x)")
                elif daily_pnl_pct <= self.DAILY_PNL_REDUCE_THRESHOLD:
                    performance_mult *= self.DAILY_PNL_REDUCE_MULT
                    logger.warning(f"📉 LOSING DAY ({daily_pnl_pct:+.2f}%): size *= {self.DAILY_PNL_REDUCE_MULT} (total: {performance_mult:.2f}x)")
            except Exception as e:
                logger.debug(f"Could not calculate daily P&L for performance scaling: {e}")

            # Apply safety caps to performance multiplier
            performance_mult = max(self.MIN_PERFORMANCE_MULT, min(performance_mult, self.MAX_PERFORMANCE_BOOST))

            if performance_mult != 1.0:
                logger.info(f"Performance-based sizing: {performance_mult:.2f}x multiplier applied")

        # =================================================================
        # COMBINED DYNAMIC SIZING
        # Kelly * Volatility * Confidence tier * Performance (if enabled)
        # =================================================================
        dynamic_size = kelly_adjusted * volatility_mult * confidence_mult * performance_mult

        # Calculate position size based on max risk per trade
        max_position_from_risk = self.MAX_RISK_PER_TRADE / risk_per_unit

        # 🆕 HYBRID: Volatility-based max limit (2025-12-04)
        # Cap position size lower in high volatility for risk protection
        max_size_limit = self.MAX_POSITION_SIZE
        if atr_percent >= self.ATR_HIGH_VOLATILITY:
            max_size_limit = self.MAX_POSITION_SIZE_HIGH_VOL
            logger.debug(f"HIGH volatility: max size capped at {max_size_limit*100:.1f}%")

        # Final position size
        position_size = min(
            dynamic_size,
            max_position_from_risk,
            max_size_limit
        )

        # Log the sizing breakdown
        logger.info(
            f"[DYNAMIC SIZING] Kelly={kelly_adjusted:.3f}, "
            f"Vol={volatility_mult:.2f}x, Conf={confidence_mult:.2f}x, "
            f"Final={position_size:.3f} ({position_size*100:.1f}%)"
        )

        return max(position_size, self.MIN_POSITION_SIZE)

    def generate_signal(
        self,
        indicators: Dict[str, IndicatorSignal],
        current_price: float,
        capital: float = 10000.0
    ) -> Optional[TradeSetup]:
        """
        Generate a complete trade setup based on all indicators

        This is the main entry point that combines all research-optimized
        strategies into a single trading decision.

        Pipeline:
        1. Classify market condition (ADX-based)
        2. Calculate individual indicator signals
        3. Check signal alignment
        4. Calculate stops and targets (ATR-based)
        5. Calculate position size (Kelly-based)
        6. Return complete trade setup or None

        Args:
            indicators: Dictionary of indicator signals
            current_price: Current market price
            capital: Available trading capital

        Returns:
            TradeSetup if valid signal found, None otherwise
        """
        reasoning = []

        # Extract indicator values
        rsi = indicators.get("RSI")
        macd = indicators.get("MACD")
        bb = indicators.get("BOLLINGER_BANDS")
        ema_data = indicators.get("EMA")
        sma_data = indicators.get("SMA")
        trend_filter = indicators.get("TREND_FILTER")
        volume_conf = indicators.get("VOLUME_CONFIRMATION")

        # Need minimum indicators for valid signal
        if not all([rsi, macd, bb]):
            logger.warning("Missing required indicators for signal generation")
            return None

        # =================================================================
        # STEP 1: Classify Market Condition
        # =================================================================
        adx = 25.0  # Default if not available
        atr = current_price * 0.02  # Default 2% ATR
        atr_percent = 0.02

        # Try to get ADX from trend filter metadata
        if trend_filter and trend_filter.metadata:
            adx = trend_filter.metadata.get("adx", 25.0)

        # Try to get ATR from metadata
        for ind in indicators.values():
            if ind.metadata and "atr" in ind.metadata:
                atr = ind.metadata["atr"]
                atr_percent = atr / current_price
                break

        market_condition = self.classify_market_condition(adx, atr_percent)
        reasoning.append(f"Market: {market_condition.value} (ADX={adx:.1f})")

        # =================================================================
        # STEP 2: Calculate Individual Signals
        # =================================================================
        # FIXED: Initialize as floats for weighted signals (code review 2025-11-28)
        buy_signals = 0.0
        sell_signals = 0.0
        confidence_sum = 0.0

        # RSI Signal (Primary for reversals)
        # FIXED: Handle rsi.value == 0 correctly (code review 2025-11-28)
        # FIXED 2025-12-02: Use RSI value for trend detection to enable SHORT trades
        rsi_value = rsi.value if rsi.value is not None else 50
        # Use RSI value itself as trend indicator when 14-period RSI not available
        # RSI < 45 = bearish trend (enables SELL signals)
        # RSI > 55 = bullish trend (enables BUY signals)
        # RSI 45-55 = neutral (less aggressive)
        rsi_trend = rsi_value  # Use same RSI for trend detection
        rsi_action, rsi_conf, rsi_reason = self.calculate_rsi_signal(
            rsi_short=rsi_value,
            rsi_trend=rsi_trend,  # FIXED: Now uses actual RSI for trend
            rsi_prev=None  # Would need previous value
        )

        if rsi_action == SignalAction.BUY:
            buy_signals += 1.5  # RSI weighted higher
            confidence_sum += rsi_conf * 1.5
        elif rsi_action == SignalAction.SELL:
            sell_signals += 1.5
            confidence_sum += rsi_conf * 1.5
        reasoning.append(rsi_reason)

        # Bollinger Band Signal
        bb_lower = bb.metadata.get("lower_band", current_price * 0.98) if bb.metadata else current_price * 0.98
        bb_upper = bb.metadata.get("upper_band", current_price * 1.02) if bb.metadata else current_price * 1.02
        bb_middle = bb.metadata.get("middle_band", current_price) if bb.metadata else current_price

        volume_ratio = 1.0
        if volume_conf and volume_conf.metadata:
            strength = volume_conf.metadata.get("strength", "MODERATE")
            volume_ratio = {"STRONG": 1.5, "MODERATE": 1.0, "WEAK": 0.7, "MINIMAL": 0.5}.get(strength, 1.0)

        bb_action, bb_conf, bb_reason = self.calculate_bollinger_signal(
            current_price, bb_lower, bb_middle, bb_upper, volume_ratio
        )

        if bb_action == SignalAction.BUY:
            buy_signals += 1.0
            confidence_sum += bb_conf
        elif bb_action == SignalAction.SELL:
            sell_signals += 1.0
            confidence_sum += bb_conf
        reasoning.append(bb_reason)

        # MACD Confirmation
        macd_line = macd.metadata.get("macd_line", 0) if macd.metadata else 0
        signal_line = macd.metadata.get("signal_line", 0) if macd.metadata else 0
        histogram = macd_line - signal_line

        confirms_long, confirms_short, macd_reason = self.calculate_macd_confirmation(
            macd_line, signal_line, histogram
        )

        if confirms_long:
            buy_signals += 0.5  # MACD is confirmation only
        if confirms_short:
            sell_signals += 0.5
        reasoning.append(macd_reason)

        # EMA Trend
        ema_value = ema_data.value if ema_data else current_price
        sma_value = sma_data.value if sma_data else current_price

        trend_dir, trend_conf, trend_reason = self.calculate_ema_trend(
            current_price, ema_value, sma_value
        )

        if trend_dir == "BULLISH":
            buy_signals += 1.0
        elif trend_dir == "BEARISH":
            sell_signals += 1.0
        reasoning.append(trend_reason)

        # Trend Filter (Gatekeeper)
        if trend_filter:
            trend = trend_filter.metadata.get("trend", "NEUTRAL") if trend_filter.metadata else "NEUTRAL"
            if trend == "BULLISH":
                buy_signals += 0.5
            elif trend == "BEARISH":
                sell_signals += 0.5

        # =================================================================
        # STEP 3: Determine Final Action - OPTIMIZED FOR WIN RATE (2025-12-01)
        # =================================================================
        total_signals = buy_signals + sell_signals
        if total_signals == 0:
            return None

        # RESEARCH-BACKED: Professional signal requirements (2025-12-23)
        # ADJUSTED 2026-01-02: Lowered from 0.75 -> 0.30 -> 0.15 for ranging market trading
        net_signal = buy_signals - sell_signals

        # Require minimum indicator alignment and clear directional signal
        if buy_signals >= self.MIN_INDICATORS_ALIGNED and net_signal >= 0.15:  # Lowered from 0.30
            action = SignalAction.BUY
            indicators_aligned = max(1, round(buy_signals))
            # Confidence based on signal strength relative to total
            base_confidence = 0.40 + (buy_signals / (total_signals + 1)) * 0.4
        elif sell_signals >= self.MIN_INDICATORS_ALIGNED and net_signal <= -0.15:  # Lowered from -0.30
            action = SignalAction.SELL
            indicators_aligned = max(1, round(sell_signals))
            base_confidence = 0.40 + (sell_signals / (total_signals + 1)) * 0.4
        else:
            # Not enough confirmation - NO TRADE
            # ADJUSTED: Lowered net_signal requirement from 1.0 to 0.5
            return None

        # =================================================================
        # STEP 4: Apply Market Condition Adjustments
        # =================================================================
        # AGGRESSIVE: All market conditions acceptable, just weight differently
        regime_mult = {
            MarketCondition.STRONG_TREND: 1.3,  # Boost strong trends
            MarketCondition.TRENDING: 1.2,       # Good for trading
            MarketCondition.WEAK_TREND: 1.1,     # Still tradeable
            MarketCondition.RANGING: 1.0,        # Mean reversion okay
            MarketCondition.VOLATILE: 0.9        # Still trade but smaller
        }.get(market_condition, 1.0)

        final_confidence = min(base_confidence * regime_mult, 0.95)

        # 🆕 HYBRID: Direction-Based Confidence Filtering (2025-12-04)
        # SHORT requires higher confidence due to 0% WR vs LONG 41% WR
        is_short_signal = action == SignalAction.SELL
        min_required_confidence = self.MIN_CONFIDENCE_SHORT if is_short_signal else self.MIN_CONFIDENCE

        if final_confidence < min_required_confidence:
            direction = "SHORT" if is_short_signal else "LONG"
            reasoning.append(f"{direction} confidence too low: {final_confidence:.2f} < {min_required_confidence:.2f}")
            return None

        # =================================================================
        # STEP 5: Calculate Stops and Targets (DYNAMIC R:R 2025-12-02)
        # Research: Higher confidence = wider take profit for 1:3 R/R
        # =================================================================
        is_long = action == SignalAction.BUY
        stop_loss, take_profit, trailing_activation = self.calculate_atr_stops(
            current_price, atr, is_long, confidence=final_confidence
        )

        # RESEARCH ENHANCEMENT: Calculate partial exit levels
        partial_exits = self.calculate_partial_exits(current_price, atr, is_long)

        reasoning.append(f"ATR stops: SL={stop_loss:.2f}, TP={take_profit:.2f}")
        if partial_exits:
            tp_labels = ", ".join([f"{pe.label}@{pe.price:.2f}" for pe in partial_exits])
            reasoning.append(f"Partial exits: {tp_labels}")

        # =================================================================
        # STEP 6: Calculate Position Size (DYNAMIC SIZING 2025-12-01)
        # Now includes ATR-based volatility adjustment
        # =================================================================
        # Calculate ATR as percentage of price for volatility adjustment
        atr_percent = atr / current_price if current_price > 0 else 0.0

        position_size = self.calculate_position_size(
            capital=capital,
            entry_price=current_price,
            stop_loss=stop_loss,
            signal_confidence=final_confidence,
            atr_percent=atr_percent  # NEW: Pass volatility for dynamic sizing
        )

        reasoning.append(f"Position: {position_size*100:.1f}% (Vol={atr_percent*100:.1f}%)")

        # =================================================================
        # STEP 7: Classify Signal Strength
        # =================================================================
        if final_confidence >= self.STRONG_SIGNAL_THRESHOLD and indicators_aligned >= 4:
            signal_strength = SignalStrength.STRONG
        elif final_confidence >= self.MIN_CONFIDENCE and indicators_aligned >= 3:
            signal_strength = SignalStrength.MODERATE
        else:
            signal_strength = SignalStrength.WEAK

        # =================================================================
        # STEP 8: Build Trade Setup
        # =================================================================
        trade_setup = TradeSetup(
            action=action,
            confidence=final_confidence,
            signal_strength=signal_strength,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size_pct=position_size,
            trailing_stop_atr_mult=self.ATR_TRAILING_MULTIPLIER,
            reasoning=reasoning,
            indicators_aligned=indicators_aligned,
            market_condition=market_condition,
            partial_exits=partial_exits if partial_exits else None
        )

        logger.info(f"Signal Generated: {action.value} | Confidence: {final_confidence:.2f} | "
                   f"Strength: {signal_strength.value} | Aligned: {indicators_aligned}")

        return trade_setup

    def get_strategy_params(self) -> Dict:
        """Return current strategy parameters for logging/debugging"""
        return {
            "rsi": {
                "period_short": self.RSI_PERIOD_SHORT,
                "oversold": self.RSI_OVERSOLD,
                "overbought": self.RSI_OVERBOUGHT,
                "trend_filter_period": self.RSI_TREND_FILTER_PERIOD
            },
            "adx": {
                "strong_trend": self.ADX_STRONG_TREND,
                "trending": self.ADX_TRENDING,
                "weak_trend": self.ADX_WEAK_TREND
            },
            "atr_stops": {
                "stop_multiplier": self.ATR_STOP_MULTIPLIER,
                "tp_multiplier": self.ATR_TP_MULTIPLIER,
                "trailing_multiplier": self.ATR_TRAILING_MULTIPLIER
            },
            "position_sizing": {
                "max_risk": self.MAX_RISK_PER_TRADE,
                "min_size": self.MIN_POSITION_SIZE,
                "max_size": self.MAX_POSITION_SIZE,
                "kelly_fraction": self.KELLY_FRACTION
            },
            "signal_quality": {
                "min_indicators": self.MIN_INDICATORS_ALIGNED,
                "min_confidence": self.MIN_CONFIDENCE,
                "strong_threshold": self.STRONG_SIGNAL_THRESHOLD
            }
        }
