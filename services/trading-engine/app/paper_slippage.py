"""
Paper-engine slippage model (PAPER-01).

Why this exists
===============
Until this module, ``PaperTradingEngine.execute_market_order`` filled at
exactly the reference price it was handed -- ADR-011's "zero slippage, zero
latency, always filled" contract. Every strategy Sharpe measured through the
paper engine (currently -0.22 to -0.50 across seven strategies) was therefore
*gross of the spread the venue would actually have charged*. The honest
numbers are worse than the recorded ones, and the size of the gap was
unknown. This module makes it measurable. Enabling it is expected to make
reported P&L worse; that is the point, not a regression.

Model
=====
``fill_price = reference_price * (1 +/- bps / 10_000)``, then quantized to the
symbol's tick size **away from mid** (BUY rounds up, SELL rounds down), so the
adverse move is never rounded back in the trader's favour and is always at
least one tick.

The sign is taken from the ORDER side, not the position side, which makes it
adverse on all four legs:

    LONG entry   (BUY)   -> pay up
    LONG exit    (SELL)  -> get less
    SHORT entry  (SELL)  -> get less
    SHORT exit   (BUY)   -> pay up

Per-symbol figures and their sources
====================================
Two components, kept separate on purpose:

1. **Tick-derived half-spread floor** -- the tightest the book can physically
   be is one tick wide, so half a tick is the arithmetic minimum. Tick sizes
   below are Bybit linear-perp ``priceFilter.tickSize`` values as published in
   the instrument spec (the live authority in this service is
   ``app/services/instruments_cache.py``, which is network-backed and
   fail-open -- deliberately NOT called from the fill path). At mid-2026
   reference prices these floors are roughly:

       BTCUSDT  tick 0.1     @ ~60,000  -> ~0.01 bps
       ETHUSDT  tick 0.01    @  ~3,000  -> ~0.02 bps
       BNBUSDT  tick 0.01    @    ~600  -> ~0.08 bps
       SOLUSDT  tick 0.01    @    ~140  -> ~0.36 bps
       ADAUSDT  tick 0.0001  @   ~0.40  -> ~1.25 bps

   That ordering alone already refutes a flat constant: ADA's floor is two
   orders of magnitude wider than BTC's in relative terms.

2. **Taker impact + latency allowance** -- the part that dominates in
   practice: the market order walks the book, and the reference price this
   engine receives is a cached ticker, not the touch. This component is an
   **ESTIMATE AND NEEDS CALIBRATION** against real Bybit fills; it has NOT
   been measured on this account. Do not present it as measured.

The totals below are the defaults blessed in ``.planning/REQUIREMENTS.md``
(PAPER-01): 5 bps for the majors, 10 bps for ADA and BNB. They are
deliberately more conservative than the tick floors.

Least-supported figure: **SOLUSDT at 5 bps**. Its tick floor (~0.36 bps) is
~25x BTC's, so the case for grouping it with the majors is weaker than for
ETH. Calibrate it first.

Calibration path when real fills exist: compare
``auto_trader``'s recorded expected-vs-actual fills (it already feeds
``trading_enhancements/slippage_manager.record_execution``) against these
constants, per symbol, and replace them via
``PAPER_SLIPPAGE_BPS_BY_SYMBOL``.

Config
======
``PAPER_SLIPPAGE_ENABLED``          default ``true``  -- slippage is ON by default
``PAPER_SLIPPAGE_BPS_BY_SYMBOL``    JSON dict override, merged over the table below
``PAPER_SLIPPAGE_DEFAULT_BPS``      bps for symbols absent from the table

Set ``PAPER_SLIPPAGE_ENABLED=false`` for an explicit frictionless A/B run.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from typing import Any, Dict, Mapping, Optional

logger = logging.getLogger(__name__)


# Total one-way slippage in basis points. Sources and caveats: module docstring.
# Components: tick-derived half-spread floor (spec-recorded) + taker impact and
# latency allowance (ESTIMATE -- NEEDS CALIBRATION, not measured on this account).
DEFAULT_SLIPPAGE_BPS: Dict[str, Decimal] = {
    "BTCUSDT": Decimal("5"),
    "ETHUSDT": Decimal("5"),
    "SOLUSDT": Decimal("5"),  # least-supported figure; calibrate first
    "BNBUSDT": Decimal("10"),
    "ADAUSDT": Decimal("10"),
}

# Symbols outside the validated set: assume the wider (alt) bucket rather than
# the majors bucket. Being wrong in the conservative direction understates P&L,
# which is the safe error here.
FALLBACK_SLIPPAGE_BPS: Decimal = Decimal("10")

# Bybit linear-perp priceFilter.tickSize (spec-recorded -- re-verify against
# instruments-info when the connector is up). Used to quantize the fill price:
# `round(price, 2)` is forbidden here, it erases ADA/SOL precision (487d1bd).
DEFAULT_TICK_SIZE: Dict[str, Decimal] = {
    "BTCUSDT": Decimal("0.1"),
    "ETHUSDT": Decimal("0.01"),
    "SOLUSDT": Decimal("0.01"),
    "BNBUSDT": Decimal("0.01"),
    "ADAUSDT": Decimal("0.0001"),
}


def _side_is_buy(side: Any) -> Optional[bool]:
    """True for BUY, False for SELL, None if unrecognisable."""
    raw = getattr(side, "value", side)
    if not isinstance(raw, str):
        return None
    normalized = raw.strip().upper()
    if normalized == "BUY":
        return True
    if normalized == "SELL":
        return False
    return None


class PaperSlippageModel:
    """Per-symbol adverse-fill model for the paper engine.

    All arithmetic is ``Decimal``; callers pass ``Decimal`` prices and get a
    ``Decimal`` back. No float ever enters an expression with a price.
    """

    def __init__(
        self,
        enabled: bool = True,
        bps_by_symbol: Optional[Mapping[str, Decimal]] = None,
        default_bps: Optional[Decimal] = None,
        tick_by_symbol: Optional[Mapping[str, Decimal]] = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.bps_by_symbol: Dict[str, Decimal] = dict(
            DEFAULT_SLIPPAGE_BPS if bps_by_symbol is None else bps_by_symbol
        )
        self.default_bps: Decimal = (
            FALLBACK_SLIPPAGE_BPS if default_bps is None else default_bps
        )
        self.tick_by_symbol: Dict[str, Decimal] = dict(
            DEFAULT_TICK_SIZE if tick_by_symbol is None else tick_by_symbol
        )

    # ---------------------------------------------------------------- lookups

    def bps_for(self, symbol: str) -> Decimal:
        return self.bps_by_symbol.get(symbol, self.default_bps)

    def tick_for(self, symbol: str) -> Optional[Decimal]:
        """Tick size for ``symbol``, or None when unknown (then no quantization)."""
        return self.tick_by_symbol.get(symbol)

    # ------------------------------------------------------------------ model

    def fill_price(self, symbol: str, side: Any, reference_price: Decimal) -> Decimal:
        """Adverse fill price for a market order.

        Returns ``reference_price`` unchanged when the model is disabled, the
        side is unrecognisable, or the configured slippage is zero.
        """
        if not self.enabled:
            return reference_price

        is_buy = _side_is_buy(side)
        if is_buy is None:
            logger.warning(
                "PaperSlippageModel: unrecognised order side %r for %s — "
                "filling at reference price",
                side,
                symbol,
            )
            return reference_price

        if not isinstance(reference_price, Decimal):
            reference_price = Decimal(str(reference_price))
        if reference_price <= 0:
            return reference_price

        bps = self.bps_for(symbol)
        if bps <= 0:
            return reference_price

        factor = bps / Decimal("10000")
        raw = (
            reference_price * (Decimal("1") + factor)
            if is_buy
            else reference_price * (Decimal("1") - factor)
        )

        tick = self.tick_for(symbol)
        if tick is None or tick <= 0:
            return raw

        # Quantize AWAY from mid so rounding can never give back a better fill,
        # and so the adverse move is at least one tick.
        steps = (raw / tick).to_integral_value(
            rounding=ROUND_CEILING if is_buy else ROUND_FLOOR
        )
        quantized = (steps * tick).quantize(tick)

        if quantized <= 0:
            # Sub-tick asset; do not manufacture a zero or negative fill.
            return raw
        return quantized

    def describe(self) -> str:
        if not self.enabled:
            return "DISABLED (frictionless fills — A/B mode, not realistic)"
        listed = ", ".join(
            f"{sym}={bps}bps" for sym, bps in sorted(self.bps_by_symbol.items())
        )
        return f"ENABLED ({listed}, other={self.default_bps}bps)"


def _coerce_bps(value: Any) -> Optional[Decimal]:
    try:
        bps = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if bps < 0:
        return None
    return bps


def build_slippage_model(settings: Any) -> PaperSlippageModel:
    """Build the model from a Settings object.

    Defensive by design: this runs inside the fill path, and several test
    fixtures hand the engine a bare ``Mock()`` whose attributes are Mocks.
    A malformed value falls back to the built-in table with a WARN rather
    than raising mid-order — but it never silently disables slippage, which
    would reintroduce the exact defect this module fixes.
    """
    raw_enabled = getattr(settings, "paper_slippage_enabled", True)
    enabled = raw_enabled if isinstance(raw_enabled, bool) else True

    bps_by_symbol: Dict[str, Decimal] = dict(DEFAULT_SLIPPAGE_BPS)
    overrides = getattr(settings, "paper_slippage_bps_by_symbol", None)
    if overrides:
        if isinstance(overrides, Mapping):
            for symbol, value in overrides.items():
                bps = _coerce_bps(value)
                if bps is None:
                    logger.warning(
                        "Ignoring invalid paper slippage override for %s: %r",
                        symbol,
                        value,
                    )
                    continue
                bps_by_symbol[str(symbol).upper()] = bps
        else:
            logger.warning(
                "paper_slippage_bps_by_symbol is not a mapping (%r) — "
                "using built-in per-symbol table",
                type(overrides).__name__,
            )

    default_bps = _coerce_bps(
        getattr(settings, "paper_slippage_default_bps", FALLBACK_SLIPPAGE_BPS)
    )
    if default_bps is None:
        default_bps = FALLBACK_SLIPPAGE_BPS

    return PaperSlippageModel(
        enabled=enabled,
        bps_by_symbol=bps_by_symbol,
        default_bps=default_bps,
        tick_by_symbol=DEFAULT_TICK_SIZE,
    )
