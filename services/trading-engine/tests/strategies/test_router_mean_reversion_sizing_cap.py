"""HybridStrategyRouter's mean-reversion conversion must honour the per-trade cap.

`_convert_mean_reversion_to_trade_setup` sized positions as:

    position_size_pct = 0.10 + (mr_signal.confidence * 0.10)   # 10-20%

which exceeds `max_risk_per_trade` (0.10 paper / 0.02 LIVE) for every
confidence above zero — up to 2x the paper cap and 10x the LIVE cap. The
router's own docstring flagged this as a blocker on promoting it from advisory
to executing (2026-08-22), because the defect is only reachable on the RANGING
branch (ADX < 25) which the executing path had never taken.

Per CLAUDE.md §5 the cap is a hard invariant, and per ADR-015 the cap is applied
LAST so it always wins — the same ordering the ensemble uses in
`MultiStrategyEnsemble.generate_signal`.

These tests pin the invariant, not the sizing curve: whatever the formula, the
result may never exceed the configured cap.
"""

import pytest

from app.config import get_settings
from app.models.enums import SignalAction
from app.strategies.hybrid_strategy_router import HybridStrategyRouter
from app.strategies.mean_reversion_strategy import (
    MeanReversionSignal,
    MeanReversionSignalStrength,
)


def _mr_signal(confidence: float, price: float = 100.0) -> MeanReversionSignal:
    return MeanReversionSignal(
        action=SignalAction.BUY,
        confidence=confidence,
        strength=MeanReversionSignalStrength.MODERATE,
        entry_price=price,
        target=price * 1.02,
        stop_loss=price * 0.98,
        indicators_aligned=["RSI", "BOLLINGER_BANDS"],
        reasoning=["test"],
    )


@pytest.mark.parametrize("confidence", [0.0, 0.25, 0.5, 0.75, 0.9, 1.0])
def test_position_size_never_exceeds_cap(confidence):
    """No confidence value may size a trade above max_risk_per_trade."""
    router = HybridStrategyRouter()
    cap = float(get_settings().max_risk_per_trade)

    setup = router._convert_mean_reversion_to_trade_setup(
        mr_signal=_mr_signal(confidence), current_price=100.0, capital=100.0
    )

    assert setup.position_size_pct <= cap + 1e-9, (
        f"confidence={confidence} produced position_size_pct="
        f"{setup.position_size_pct:.4f}, above the {cap:.4f} per-trade cap"
    )


@pytest.mark.parametrize(
    "strength",
    list(MeanReversionSignalStrength),
)
def test_every_strength_constructs_a_valid_setup(strength):
    """The conversion must not raise for ANY MeanReversionSignalStrength.

    Regression guard for two stacked defects that made this whole branch dead:
    `SignalStrength.VERY_STRONG` did not exist (AttributeError on every call,
    because the mapping is a dict literal evaluated eagerly), and TradeSetup was
    built with `quantity=`/`metadata=` — neither is a field — while the REQUIRED
    `trailing_stop_atr_mult` was omitted (TypeError). Both went unnoticed because
    the executing path had never taken the RANGING branch.
    """
    router = HybridStrategyRouter()
    sig = _mr_signal(0.5)
    sig.strength = strength

    setup = router._convert_mean_reversion_to_trade_setup(
        mr_signal=sig, current_price=100.0, capital=100.0
    )

    assert setup.signal_strength is not None
    assert setup.trailing_stop_atr_mult > 0
    assert setup.market_condition.value == "RANGING"


def test_cap_binds_at_the_configured_value():
    """At high confidence the cap must be what binds, not the 0.20 formula ceiling."""
    router = HybridStrategyRouter()
    cap = float(get_settings().max_risk_per_trade)

    setup = router._convert_mean_reversion_to_trade_setup(
        mr_signal=_mr_signal(1.0), current_price=100.0, capital=100.0
    )

    # Pre-fix this returned 0.20 regardless of the cap.
    assert setup.position_size_pct == pytest.approx(min(cap, 0.20))
    assert setup.position_size_pct <= cap
