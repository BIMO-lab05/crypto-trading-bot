"""
Unit tests for Phase C auto-trader smart-mode helpers.

These tests exercise the three smart-mode gates in isolation, without
spinning up the full _trading_loop:

* `_smart_should_skip_for_heat`     — early heat-critical gate
* `_smart_resolve_strategy`         — per-cycle regime → strategy choice
* `_smart_check_ml_disagreement`    — ML floor / direction guard

The tests construct an `AutoTrader` then poke individual collaborators
(``portfolio_heat_manager``, ``regime_detector``) so we don't have to stand
up databases, brokers, or signal aggregators.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.auto_trader import AutoTrader, StrategyMode
from app.aggregation.market_regime import MarketRegime, RegimeAnalysis, TrendDirection


@pytest.fixture
def trader_baseline():
    """AutoTrader with smart-mode OFF — every helper is a no-op."""
    with patch.object(AutoTrader, "__init__", lambda self, *a, **kw: None):
        t = AutoTrader()
    t.smart_mode = False
    t.ml_confidence_floor = 0.6
    t.enable_ml = True
    t.smart_mode_heat_skips = 0
    t.smart_mode_ml_rejections = 0
    t.smart_mode_regime_overrides = 0
    t.strategy_mode = StrategyMode.HYBRID
    t.interval = "60"
    return t


@pytest.fixture
def trader_smart(trader_baseline):
    """AutoTrader with smart_mode ON."""
    trader_baseline.smart_mode = True
    return trader_baseline


# ---------------------------------------------------------------------------
# Heat early gate
# ---------------------------------------------------------------------------

class TestSmartHeatGate:
    def test_baseline_never_skips(self, trader_baseline):
        trader_baseline.portfolio_heat_manager = SimpleNamespace(
            get_summary_dict=lambda: {
                "total_heat_pct": 99.0,
                "limits": {"critical_heat_threshold": 10.0},
            }
        )
        # smart_mode=False → never skip, regardless of heat
        assert trader_baseline._smart_should_skip_for_heat() is False
        assert trader_baseline.smart_mode_heat_skips == 0

    def test_smart_skips_when_critical(self, trader_smart):
        trader_smart.portfolio_heat_manager = SimpleNamespace(
            get_summary_dict=lambda: {
                "total_heat_pct": 12.5,
                "limits": {"critical_heat_threshold": 10.0},
            }
        )
        assert trader_smart._smart_should_skip_for_heat() is True
        assert trader_smart.smart_mode_heat_skips == 1

    def test_smart_does_not_skip_below_critical(self, trader_smart):
        trader_smart.portfolio_heat_manager = SimpleNamespace(
            get_summary_dict=lambda: {
                "total_heat_pct": 3.0,
                "limits": {"critical_heat_threshold": 10.0},
            }
        )
        assert trader_smart._smart_should_skip_for_heat() is False
        assert trader_smart.smart_mode_heat_skips == 0

    def test_smart_swallows_heat_manager_errors(self, trader_smart):
        # If heat manager raises, smart-mode should fail open (no skip)
        def raise_(*_a, **_kw):
            raise RuntimeError("heat manager exploded")
        trader_smart.portfolio_heat_manager = SimpleNamespace(get_summary_dict=raise_)
        assert trader_smart._smart_should_skip_for_heat() is False


# ---------------------------------------------------------------------------
# Regime → strategy resolution
# ---------------------------------------------------------------------------

class TestSmartResolveStrategy:
    @pytest.mark.asyncio
    async def test_baseline_returns_construction_strategy(self, trader_baseline):
        trader_baseline.regime_detector = SimpleNamespace(
            detect_regime=AsyncMock(return_value=_regime(MarketRegime.RANGING))
        )
        # smart_mode=False → construction-time strategy_mode
        resolved = await trader_baseline._smart_resolve_strategy("SOLUSDT")
        assert resolved == StrategyMode.HYBRID

    @pytest.mark.asyncio
    async def test_smart_promotes_trending_to_research(self, trader_smart):
        trader_smart.regime_detector = SimpleNamespace(
            detect_regime=AsyncMock(return_value=_regime(MarketRegime.TRENDING))
        )
        resolved = await trader_smart._smart_resolve_strategy("SOLUSDT")
        assert resolved == StrategyMode.RESEARCH
        assert trader_smart.smart_mode_regime_overrides == 1

    @pytest.mark.asyncio
    async def test_smart_keeps_hybrid_for_ranging(self, trader_smart):
        trader_smart.regime_detector = SimpleNamespace(
            detect_regime=AsyncMock(return_value=_regime(MarketRegime.RANGING))
        )
        # baseline is HYBRID → resolved HYBRID → no override counted
        resolved = await trader_smart._smart_resolve_strategy("SOLUSDT")
        assert resolved == StrategyMode.HYBRID
        assert trader_smart.smart_mode_regime_overrides == 0

    @pytest.mark.asyncio
    async def test_smart_falls_back_for_unknown_regime(self, trader_smart):
        trader_smart.strategy_mode = StrategyMode.ENSEMBLE
        trader_smart.regime_detector = SimpleNamespace(
            detect_regime=AsyncMock(return_value=_regime(MarketRegime.UNKNOWN))
        )
        resolved = await trader_smart._smart_resolve_strategy("SOLUSDT")
        assert resolved == StrategyMode.ENSEMBLE


# ---------------------------------------------------------------------------
# ML disagreement floor
# ---------------------------------------------------------------------------

class TestSmartMLFloor:
    def test_baseline_never_rejects(self, trader_baseline):
        signal = SimpleNamespace(indicators={
            "ml_prediction": SimpleNamespace(action="SELL", confidence=0.9)
        })
        # Even with a clear disagreement, baseline returns None.
        assert trader_baseline._smart_check_ml_disagreement(signal, "BUY") is None

    def test_smart_rejects_low_confidence(self, trader_smart):
        signal = SimpleNamespace(indicators={
            "ml_prediction": SimpleNamespace(action="BUY", confidence=0.3)
        })
        reason = trader_smart._smart_check_ml_disagreement(signal, "BUY")
        assert reason is not None and "ml_disagreement" in reason
        assert trader_smart.smart_mode_ml_rejections == 1

    def test_smart_rejects_direction_mismatch(self, trader_smart):
        signal = SimpleNamespace(indicators={
            "ml_prediction": SimpleNamespace(action="SELL", confidence=0.9)
        })
        reason = trader_smart._smart_check_ml_disagreement(signal, "BUY")
        assert reason is not None and "ml_disagreement" in reason
        assert trader_smart.smart_mode_ml_rejections == 1

    def test_smart_accepts_aligned_high_confidence(self, trader_smart):
        signal = SimpleNamespace(indicators={
            "ml_prediction": SimpleNamespace(action="BUY", confidence=0.85)
        })
        assert trader_smart._smart_check_ml_disagreement(signal, "BUY") is None
        assert trader_smart.smart_mode_ml_rejections == 0

    def test_smart_no_op_when_no_ml_signal(self, trader_smart):
        signal = SimpleNamespace(indicators={"rsi": SimpleNamespace(action="BUY")})
        # No ml_prediction key → don't gate.
        assert trader_smart._smart_check_ml_disagreement(signal, "BUY") is None

    def test_smart_no_op_when_enable_ml_off(self, trader_smart):
        trader_smart.enable_ml = False
        signal = SimpleNamespace(indicators={
            "ml_prediction": SimpleNamespace(action="SELL", confidence=0.1)
        })
        assert trader_smart._smart_check_ml_disagreement(signal, "BUY") is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _regime(regime: MarketRegime) -> RegimeAnalysis:
    return RegimeAnalysis(
        regime=regime,
        direction=TrendDirection.NEUTRAL,
        adx=20.0,
        plus_di=20.0,
        minus_di=20.0,
        confidence=0.5,
        confidence_modifier=1.0,
        description="test",
        strategy_recommendation="test",
    )
