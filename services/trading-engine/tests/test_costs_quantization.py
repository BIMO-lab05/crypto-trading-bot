"""
costs.py quantization + venue gates.

CLAUDE.md section 1: a trade below min-notional must be REJECTED with a
reason, never clamped up. Clamping a \$10 per-trade cap up to clear BTC's
~\$62 floor turns a 10% cap into a 62% cap. This is also why snapping is
floor-only.

round(price, 2) is forbidden in the price domain here - it destroyed ADA
precision and caused 30+ flip-flop losses (487d1bd). Quantization is always
to the symbol's tick.
"""

from decimal import Decimal


from app.costs import (
    RejectReason,
    VenueSpec,
    check_tradeable,
    quantize_price,
    snap_quantity,
)


# Live Bybit values fetched 2026-08-04 (AUDIT.md section 3). Note BNBUSDT's
# tick is 0.10 at the venue while paper_slippage.DEFAULT_TICK_SIZE hardcodes
# 0.01 - defect E14. costs.py takes the spec as a parameter and inherits
# neither, which is the point.
BTC = VenueSpec(
    "BTCUSDT", Decimal("0.10"), Decimal("0.001"), Decimal("0.001"), Decimal("5")
)
SOL = VenueSpec(
    "SOLUSDT", Decimal("0.010"), Decimal("0.1"), Decimal("0.1"), Decimal("5")
)
ADA = VenueSpec("ADAUSDT", Decimal("0.0001"), Decimal("1"), Decimal("1"), Decimal("5"))
BNB = VenueSpec("BNBUSDT", Decimal("0.10"), Decimal("0.01"), Decimal("0.01"), None)


def test_quantity_floors_to_step_never_up():
    assert snap_quantity(Decimal("0.1387"), BNB) == Decimal("0.13")
    assert snap_quantity(Decimal("0.99"), SOL) == Decimal("0.9")
    assert snap_quantity(Decimal("0.0019"), BTC) == Decimal("0.001")


def test_quantity_already_on_step_is_unchanged():
    assert snap_quantity(Decimal("0.3"), SOL) == Decimal("0.3")


def test_quantity_below_one_step_floors_to_zero():
    """A zero quantity must be caught downstream, never become an order."""
    assert snap_quantity(Decimal("0.05"), SOL) == Decimal("0")


def test_price_quantizes_away_from_mid():
    """A buy fills at or above the reference; a sell at or below."""
    assert quantize_price(Decimal("62551.37"), BTC, adverse_for_buy=True) == Decimal(
        "62551.40"
    )
    assert quantize_price(Decimal("62551.37"), BTC, adverse_for_buy=False) == Decimal(
        "62551.30"
    )


def test_sub_dollar_price_keeps_its_precision():
    """round(price, 2) on ADA is the 487d1bd catastrophe."""
    got = quantize_price(Decimal("0.20234"), ADA, adverse_for_buy=True)
    assert got == Decimal("0.2024")
    assert got != Decimal("0.20")


def test_below_min_qty_is_rejected_not_clamped():
    reason = check_tradeable(Decimal("0.05"), Decimal("71.0"), SOL)
    assert reason is RejectReason.MIN_QTY


def test_zero_quantity_is_rejected():
    assert check_tradeable(Decimal("0"), Decimal("71.0"), SOL) is RejectReason.ZERO_QTY


def test_below_min_notional_is_rejected_not_clamped():
    """BTC min qty 0.001 at ~\$62,551 = \$62.55 notional - 62% of a \$100
    account against a \$10 per-trade cap. It must be rejected."""
    reason = check_tradeable(Decimal("0.0005"), Decimal("62551.0"), BTC)
    assert reason is RejectReason.MIN_QTY  # fails the qty floor first


def test_min_notional_gate_fires_when_qty_clears_but_value_does_not():
    reason = check_tradeable(Decimal("1"), Decimal("1.0"), ADA)
    assert reason is RejectReason.MIN_NOTIONAL


def test_absent_min_notional_skips_only_the_notional_check():
    """Bybit omits minNotionalValue on many perps. The live gate then skips
    the notional check entirely (auto_trader.py:1636) - there is no \$5
    fallback. Mirrored here so the two agree; the caller decides."""
    assert check_tradeable(Decimal("0.01"), Decimal("602.69"), BNB) is None
    assert (
        check_tradeable(Decimal("0.001"), Decimal("602.69"), BNB)
        is RejectReason.MIN_QTY
    )


def test_a_tradeable_order_returns_none():
    assert check_tradeable(Decimal("0.3"), Decimal("72.68"), SOL) is None
