"""
One cost model, called by the live paper engine AND the research backtester.

WHY THIS EXISTS. Before it, seven different commission values were live in
this repo, the research backtester's default path charged 0.1%/side (1.8x the
real Bybit taker rate), stop and take-profit exits in that backtester were
classified as MAKER with a NEGATIVE fee so every stop-out CREDITED the
account, funding was charged to longs only at a hardcoded worst-case rate and
was off by default, and nothing anywhere modelled tick or lot quantization.
Every published P&L figure in the repo was produced under some subset of that.

TWO HARD RULES, both load-bearing:

1. STDLIB ONLY. `from app.config import get_settings` raises SettingsError when
   executed from the repo root (env_file=".env" is cwd-relative), and
   `instruments_cache.get()` performs an HTTP GET and FAILS OPEN — it returns
   None on a connector outage and never raises. A costs.py that reached for
   either would work in-container and silently lose all quantization host-side,
   with every assertion still passing. Enforced by a test.

2. NOTHING IS FETCHED. Every rate, tick size, lot step and min-notional arrives
   as an explicit parameter. Callers resolve them: in-container from Settings
   plus instruments_cache; host-side from a fixture or a manifest. This is also
   why the duplicated tick table in paper_slippage.py is NOT collapsed here —
   that duplication is deliberate (paper_slippage.py:38-40), because a network
   call in the fill path was explicitly rejected.

IMPORT PATHS.
  in-container:  from app.costs import FeeSchedule, Liquidity, ...
  host-side:     load by file path under a NON-`app` module name. `app` is a
                 regular package claimed by technical-analysis in the
                 backtesting process, so `from app.costs import ...` resolves
                 to the wrong package or raises ModuleNotFoundError. See
                 backtesting/costs_loader.py.

UNITS. Fee rates are FRACTIONS (0.00055 = 5.5 bps). Slippage is BASIS POINTS.
Conflating fraction and percent is the single most common defect in this
codebase — `max_risk_per_trade` is a fraction while its `*_pct` neighbours are
percents, and that shipped once. Every public name here says which it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Mapping, Optional

_BPS = Decimal("10000")


class Liquidity(str, Enum):
    """Which side of the book an order took."""

    MAKER = "MAKER"
    TAKER = "TAKER"


@dataclass(frozen=True)
class FeeSchedule:
    """Per-side fee rates as FRACTIONS of notional. Both are charges."""

    taker: Decimal
    maker: Decimal

    @classmethod
    def bybit_linear_perp(cls) -> "FeeSchedule":
        """Bybit USDT-perpetual standard (non-VIP) schedule.

        taker 0.055%, maker 0.020% — BOTH CHARGES. Recorded at
        services/trading-engine/app/config.py:176.

        backtesting/backtest_engine.py:140 declares `bybit_maker_fee = -0.0001`
        with the comment "maker rebate". That is wrong for this account: Bybit
        pays maker rebates only at market-maker / high-VIP tiers, which $100
        cannot reach. Combined with that file classifying every stop and
        take-profit exit as LIMIT => maker, it made every backtested stop-out
        credit the account. Resolved here in favour of config.py:176.
        """
        return cls(taker=Decimal("0.00055"), maker=Decimal("0.00020"))

    def rate(self, liquidity: Liquidity) -> Decimal:
        return self.taker if liquidity is Liquidity.TAKER else self.maker


@dataclass(frozen=True)
class VenueSpec:
    """Venue constraints for one symbol. Supplied by the caller, never fetched.

    min_notional is Optional BY DESIGN: Bybit omits
    lotSizeFilter.minNotionalValue on many perps, and the live enforced gate
    (auto_trader.py:1636) therefore skips the notional check entirely when it
    is absent — there is no $5 fallback in that path, despite
    shared/account.MIN_NOTIONAL_USD existing. Making the absent case explicit
    here forces the caller to decide rather than inherit a silent skip.
    """

    symbol: str
    tick_size: Decimal
    qty_step: Decimal
    min_order_qty: Decimal
    min_notional: Optional[Decimal] = None


def fee(notional: Decimal, liquidity: Liquidity, schedule: FeeSchedule) -> Decimal:
    """Commission on one leg. `notional` is price x quantity, quote currency."""
    if notional < 0:
        raise ValueError(f"notional must be non-negative, got {notional}")
    return notional * schedule.rate(liquidity)


def slippage_bps(
    symbol: str,
    table: Mapping[str, Decimal],
    fallback: Decimal,
) -> Decimal:
    """One-way slippage in BASIS POINTS.

    An unlisted symbol gets `fallback`, which callers should set to the wider
    alt bucket rather than the majors bucket: being wrong conservatively
    understates P&L, which is the safe direction (paper_slippage.py:105-107).

    These figures are ESTIMATES. paper_slippage.py's own docstring flags the
    taker-impact component as never measured on this account and names
    SOLUSDT@5bps as the least-supported value.
    """
    return table.get(symbol, fallback)


def round_trip_cost_bps(
    symbol: str,
    *,
    entry_liquidity: Liquidity,
    exit_liquidity: Liquidity,
    schedule: FeeSchedule,
    slippage_table: Mapping[str, Decimal],
    slippage_fallback: Decimal,
) -> Decimal:
    """Fees + slippage for one full round trip, in BASIS POINTS of notional.

    Funding is deliberately NOT included: it is signed, per-symbol and
    dependent on side and holding period, so it cannot be a constant adder.
    See `funding_cost`.

    A MAKER leg pays no adverse slippage — a PostOnly order fills at the price
    it posted. It does NOT follow that maker execution is free: adverse
    selection and non-fill are real costs this function cannot express, which
    is why a maker-only hurdle carries a fill-realism caveat rather than a
    straight 5x cost reduction.
    """
    slip = slippage_bps(symbol, slippage_table, slippage_fallback)
    fee_bps = (schedule.rate(entry_liquidity) + schedule.rate(exit_liquidity)) * _BPS
    slip_bps = Decimal("0")
    if entry_liquidity is Liquidity.TAKER:
        slip_bps += slip
    if exit_liquidity is Liquidity.TAKER:
        slip_bps += slip
    return fee_bps + slip_bps
