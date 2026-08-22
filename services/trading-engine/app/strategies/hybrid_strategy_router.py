"""
Hybrid Strategy Router
Created: 2026-01-03
Purpose: Route between trend-following and mean reversion based on market regime

Logic:
- Detects market regime using ADX indicator
- Routes to appropriate strategy:
  * ADX >= 25: TRENDING → Use trend-following strategy
  * ADX < 25: RANGING → Use mean reversion strategy
- Combines best of both worlds for all market conditions
"""

import logging
from typing import Dict, Optional
from enum import Enum

from app.config import get_settings
from app.models import IndicatorSignal
from app.monitoring.signal_funnel import get_signal_funnel
from app.strategies.research_optimized_strategy import (
    ResearchOptimizedStrategy,
    TradeSetup,
)
from app.strategies.mean_reversion_strategy import (
    MeanReversionStrategy,
    MeanReversionSignal,
)

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classification"""

    TRENDING = "TRENDING"  # ADX >= 25
    RANGING = "RANGING"  # ADX < 25
    UNKNOWN = "UNKNOWN"  # Cannot determine


class HybridStrategyRouter:
    """
    Hybrid strategy that switches between trend-following and mean reversion

    Features:
    - Automatic regime detection using ADX
    - Trend-following for trending markets (ADX >= 25)
    - Mean reversion for ranging markets (ADX < 25)
    - Seamless switching based on conditions
    """

    def __init__(self):
        """Initialize hybrid strategy router"""
        self.trend_strategy = ResearchOptimizedStrategy()
        self.mean_reversion_strategy = MeanReversionStrategy()

        # ADX threshold for regime classification.
        # 2026-08-21: lifted out of this constructor into Settings
        # (`adx_trending_threshold`). It was a bare 25.0 literal here while the
        # dashboard tile advertised "ADX >= 25" as the live routing rule — the
        # two agreed only by coincidence, and neither was reachable because the
        # router was never invoked. Config is now the single source.
        settings = get_settings()
        self.ADX_TRENDING_THRESHOLD = float(settings.adx_trending_threshold)

        # Statistics.
        #
        # `total_signals` counts ROUTING DECISIONS, executed and advisory
        # alike, and is the denominator the dashboard renders as "Total
        # Routing Decisions". `executed_signals` is the subset where the
        # router actually selected the strategy that traded; the remainder is
        # advisory observation on a path that some other strategy executes.
        # Keeping them apart is the difference between "the router ran" and
        # "the router decided" — conflating them is how a tile ends up
        # claiming a subsystem is steering the engine when it is only
        # watching it.
        self.total_signals = 0
        self.trend_signals = 0
        self.mean_reversion_signals = 0
        self.executed_signals = 0
        self.observed_signals = 0

        logger.info("HybridStrategyRouter initialized")
        logger.info(f"  ADX threshold: {self.ADX_TRENDING_THRESHOLD} (from config)")
        logger.info("  Trend strategy: ResearchOptimizedStrategy")
        logger.info("  Mean reversion strategy: MeanReversionStrategy")

    def detect_regime(self, indicators: Dict[str, IndicatorSignal]) -> MarketRegime:
        """Classify the market regime from ADX. See `classify` for the
        variant that also returns the ADX value and which source produced it.
        """
        regime, _adx, _source = self.classify(indicators)
        return regime

    @staticmethod
    def extract_adx(indicators: Dict[str, IndicatorSignal]) -> Optional[float]:
        """Pull the numeric ADX out of the aggregator indicator dict.

        Returns None when ADX is genuinely absent. It does NOT substitute a
        default — a missing ADX must be visible to the caller so the fallback
        classifier is entered deliberately and logged, rather than the router
        silently classifying every bar as RANGING (the 2026-05-06 bug).
        """
        adx_signal = indicators.get("ADX")
        adx_value = None
        if adx_signal is not None:
            adx_value = getattr(adx_signal, "value", None)
            if adx_value is None and getattr(adx_signal, "metadata", None):
                adx_value = adx_signal.metadata.get("adx")
        if adx_value is None:
            atr_signal = indicators.get("ATR")
            if atr_signal and getattr(atr_signal, "metadata", None):
                adx_value = atr_signal.metadata.get("adx")
        if adx_value is None:
            return None
        try:
            adx_value = float(adx_value)
        except (TypeError, ValueError):
            return None
        if adx_value != adx_value:  # NaN
            return None
        return adx_value

    def classify(
        self, indicators: Dict[str, IndicatorSignal]
    ) -> "tuple[MarketRegime, Optional[float], str]":
        """
        Detect current market regime using ADX.

        Args:
            indicators: Dict of indicator signals

        Returns:
            (regime, adx_value_or_None, source) where source is "adx" when the
            ADX leg drove the decision and "fallback" when it was absent.
        """
        # Primary path (2026-05-06): read the ADX leg the aggregator now
        # supplies. ADX is its own indicator, NOT nested in ATR.metadata.
        # Old code looked at atr_signal.metadata['adx'] which never existed,
        # so the router silently defaulted to RANGING every cycle regardless
        # of regime — a load-bearing bug for trend-following profitability.
        adx_value = self.extract_adx(indicators)

        if adx_value is not None:
            if adx_value >= self.ADX_TRENDING_THRESHOLD:
                logger.debug(
                    f"[HYBRID] ADX={adx_value:.2f} >= "
                    f"{self.ADX_TRENDING_THRESHOLD} → TRENDING"
                )
                return MarketRegime.TRENDING, adx_value, "adx"
            logger.debug(
                f"[HYBRID] ADX={adx_value:.2f} < "
                f"{self.ADX_TRENDING_THRESHOLD} → RANGING"
            )
            return MarketRegime.RANGING, adx_value, "adx"

        # Fallback only when ADX is genuinely unavailable (e.g. TA service
        # transient down). Treat conf > 0.5 instead of 0.7 so the fallback
        # has a non-zero chance of firing — old 0.7 floor never triggered
        # with current aggregator confidence regime (~0.16-0.30).
        trend_indicators = ["EMA", "SMA", "ICHIMOKU", "TREND_FILTER"]
        strong_trend_count = sum(
            1
            for name in trend_indicators
            if (sig := indicators.get(name)) and sig.confidence > 0.5
        )
        if strong_trend_count >= 2:
            logger.warning(
                f"[HYBRID] ADX unavailable; fallback says TRENDING "
                f"({strong_trend_count}/{len(trend_indicators)} legs strong)"
            )
            return MarketRegime.TRENDING, None, "fallback"
        logger.warning(
            f"[HYBRID] ADX unavailable; fallback says RANGING "
            f"({strong_trend_count}/{len(trend_indicators)} legs strong)"
        )
        return MarketRegime.RANGING, None, "fallback"

    def observe_regime(
        self,
        indicators: Dict[str, IndicatorSignal],
        symbol: Optional[str] = None,
    ) -> MarketRegime:
        """Advisory routing decision — classify and count, do NOT execute.

        Called on the ENSEMBLE path (auto_trader._check_and_trade_ensemble) so
        the routing counters reflect real evaluations while the ensemble keeps
        deciding what trades. This is the honest version of what the dashboard
        tile has claimed since 2026-01-06: the router IS running and IS making
        a decision every cycle, it just is not the thing that executes.

        Promoting this to an executing router is a strategy change and needs
        replay evidence first — see docs/PIPELINE_MAP.md §6 and the 10-20%
        position sizing defect in `_convert_mean_reversion_to_trade_setup`.
        """
        regime, adx_value, source = self.classify(indicators)
        self._record_route(regime, adx_value, source, executed=False)
        logger.info(
            "[HYBRID][ADVISORY] %s regime=%s adx=%s source=%s "
            "(ensemble executes; router observing)",
            symbol or "?",
            regime.value,
            f"{adx_value:.2f}" if adx_value is not None else "unavailable",
            source,
        )
        return regime

    def _record_route(
        self,
        regime: MarketRegime,
        adx_value: Optional[float],
        source: str,
        *,
        executed: bool,
    ) -> None:
        """Single increment site for every routing counter.

        Both `generate_signal` (executing) and `observe_regime` (advisory) go
        through here so the branch counts and the total can never drift apart
        — the previous code incremented `total_signals` in one place and the
        branch counters in two others.
        """
        self.total_signals += 1
        if executed:
            self.executed_signals += 1
        else:
            self.observed_signals += 1

        if regime == MarketRegime.TRENDING:
            self.trend_signals += 1
            branch = "trend_following"
        elif regime == MarketRegime.RANGING:
            self.mean_reversion_signals += 1
            branch = "mean_reversion"
        else:
            branch = "unknown"

        funnel = get_signal_funnel()
        funnel.gate("routing_decision_made", True)
        funnel.record_route(branch, adx_value)
        if source == "fallback":
            # Not a rejection — the decision was still made — but it must be
            # visible that ADX was missing, because the fallback classifier is
            # a different rule with different behaviour.
            logger.warning(
                "[HYBRID] routing decision made WITHOUT ADX (fallback rule): %s",
                branch,
            )

    def generate_signal(
        self,
        indicators: Dict[str, IndicatorSignal],
        current_price: float,
        capital: float,
    ) -> Optional[TradeSetup]:
        """
        Generate trading signal using appropriate strategy

        Args:
            indicators: Dict of indicator signals
            current_price: Current market price
            capital: Available capital. REQUIRED — the old 10000.0 default was
                100x the real account; both auto_trader call sites pass the
                live paper balance explicitly (AUDIT 2.5).

        Returns:
            TradeSetup or None
        """
        # Detect market regime
        regime, adx_value, source = self.classify(indicators)
        self._record_route(regime, adx_value, source, executed=True)

        logger.info(f"[HYBRID] Market regime: {regime.value}")

        # Route to appropriate strategy
        if regime == MarketRegime.TRENDING:
            # Use trend-following strategy
            logger.info("[HYBRID] Using TREND-FOLLOWING strategy")

            signal = self.trend_strategy.generate_signal(
                indicators=indicators, current_price=current_price, capital=capital
            )

            if signal:
                # Add regime info to reasoning
                signal.reasoning.insert(
                    0, "Market regime: TRENDING (using trend-following)"
                )

            return signal

        elif regime == MarketRegime.RANGING:
            # Use mean reversion strategy
            logger.info("[HYBRID] Using MEAN REVERSION strategy")

            mr_signal = self.mean_reversion_strategy.generate_signal(
                indicators=indicators, current_price=current_price, capital=capital
            )

            if mr_signal:
                # Convert MeanReversionSignal to TradeSetup format
                return self._convert_mean_reversion_to_trade_setup(
                    mr_signal=mr_signal, current_price=current_price, capital=capital
                )
            else:
                return None

        else:
            # Unknown regime - default to trend-following (safer)
            logger.warning("[HYBRID] Unknown regime, defaulting to trend-following")
            return self.trend_strategy.generate_signal(
                indicators=indicators, current_price=current_price, capital=capital
            )

    def _convert_mean_reversion_to_trade_setup(
        self, mr_signal: MeanReversionSignal, current_price: float, capital: float
    ) -> TradeSetup:
        """Convert MeanReversionSignal to TradeSetup format"""
        from app.strategies.research_optimized_strategy import (
            SignalStrength,
            MarketCondition,
        )

        # Map mean reversion strength to signal strength.
        #
        # 2026-08-22: MeanReversionSignalStrength has four members
        # (VERY_STRONG/STRONG/MODERATE/WEAK) but SignalStrength has no
        # VERY_STRONG — its members are STRONG/MODERATE/WEAK/NONE. The old
        # mapping referenced SignalStrength.VERY_STRONG, and because a dict
        # literal is evaluated eagerly this raised AttributeError on EVERY
        # call, not just on very-strong signals. The whole RANGING branch of
        # the router was therefore dead: it could only ever throw. It went
        # unnoticed because the executing path had never taken that branch
        # (ADX has stayed above the trending threshold), and the caller wraps
        # this in a broad `except Exception` that logs and returns no trade.
        # VERY_STRONG collapses onto STRONG, the strongest member that exists.
        strength_mapping = {
            "VERY_STRONG": SignalStrength.STRONG,
            "STRONG": SignalStrength.STRONG,
            "MODERATE": SignalStrength.MODERATE,
            "WEAK": SignalStrength.WEAK,
        }

        signal_strength = strength_mapping.get(
            mr_signal.strength.value, SignalStrength.MODERATE
        )

        # Position sizing, confidence-scaled but HARD-CAPPED.
        #
        # 2026-08-22: this read `0.10 + confidence * 0.10` (10-20% of capital),
        # which exceeds max_risk_per_trade at every confidence above zero — up
        # to 2x the 10% paper cap and 10x the 2% LIVE cap. CLAUDE.md §5 makes
        # the per-trade cap a hard invariant, so the cap is applied LAST and
        # always wins (same ordering as ADR-015 in MultiStrategyEnsemble).
        # Never write the cap as a literal here — it differs between paper and
        # LIVE and Settings is the single source.
        cap = float(get_settings().max_risk_per_trade)
        position_size_pct = min(cap, 0.10 + (mr_signal.confidence * 0.10))

        # 2026-08-22: `quantity=` and `metadata=` were passed here but are NOT
        # fields on TradeSetup, and the REQUIRED `trailing_stop_atr_mult` was
        # never passed — so this constructor raised TypeError on every call,
        # stacked behind the SignalStrength.VERY_STRONG AttributeError above.
        # Notional is derived downstream from position_size_pct, so no quantity
        # is carried here. The metadata that used to be dropped on the floor is
        # folded into `reasoning`, which is a real field and is what surfaces in
        # the trade log.
        reasoning = list(mr_signal.reasoning) + [
            "Strategy: mean_reversion (router RANGING branch)",
            f"Indicators triggered: {', '.join(mr_signal.indicators_aligned)}",
            f"Target mean: {mr_signal.target}",
            f"Size {position_size_pct:.2%} (cap {cap:.2%})",
        ]

        return TradeSetup(
            action=mr_signal.action,
            confidence=mr_signal.confidence,
            signal_strength=signal_strength,
            entry_price=mr_signal.entry_price,
            stop_loss=mr_signal.stop_loss,
            take_profit=mr_signal.target,  # Mean is the target
            position_size_pct=position_size_pct,
            trailing_stop_atr_mult=self.trend_strategy.ATR_TRAILING_MULTIPLIER,
            indicators_aligned=len(mr_signal.indicators_aligned),
            market_condition=MarketCondition.RANGING,  # Explicitly ranging
            reasoning=reasoning,
        )

    def get_stats(self) -> Dict[str, any]:
        """Routing statistics, as consumed by the dashboard tile.

        `routing_mode` is the field that stops this payload from lying:

          - "executing"  — the router selected the strategy that traded
          - "advisory"   — the router classified every evaluation but another
                           strategy (the ensemble) executed
          - "inactive"   — no routing decision has been made at all

        Percentages are None, never 0.0, when there is no denominator. A tile
        that renders None as "n/a" tells the truth; one that renders 0.0 as
        "0.0% — 0 signals routed" is indistinguishable from a working router
        seeing a one-sided market, which is exactly the failure this whole
        change exists to make impossible.
        """
        total = self.total_signals
        if total == 0:
            return {
                "routing_mode": "inactive",
                "adx_threshold": self.ADX_TRENDING_THRESHOLD,
                "total_signals": 0,
                "trend_signals": 0,
                "mean_reversion_signals": 0,
                "executed_signals": 0,
                "observed_signals": 0,
                "trend_pct": None,
                "mean_reversion_pct": None,
            }

        if self.executed_signals > 0:
            mode = "executing" if self.observed_signals == 0 else "mixed"
        else:
            mode = "advisory"

        return {
            "routing_mode": mode,
            "adx_threshold": self.ADX_TRENDING_THRESHOLD,
            "total_signals": total,
            "trend_signals": self.trend_signals,
            "mean_reversion_signals": self.mean_reversion_signals,
            "executed_signals": self.executed_signals,
            "observed_signals": self.observed_signals,
            "trend_pct": (self.trend_signals / total) * 100,
            "mean_reversion_pct": (self.mean_reversion_signals / total) * 100,
        }
