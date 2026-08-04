"""Declaration of record for account equity and risk caps.

THE ACCOUNT IS $100 USDT.

Why this file exists
--------------------
The repository accumulated at least five independent notions of "account size"
with no shared module: trading-engine ``Settings.paper_initial_balance``,
portfolio-manager ``Settings.initial_capital``, risk-metrics-service's per-call
``portfolio.get("total_value", 10000)`` fallback, the ``portfolios`` Postgres
table's ``initial_balance`` column, and a scattering of dataclass defaults at
``10000.0`` / ``100000.0``. A strategy that looks flat on $10,000 can be firmly
negative on $100 once Bybit's minimum notional and round-trip fees apply,
because the fee-to-equity ratio and the position-size floor are ~100x more
binding. The two are not the same experiment, so the number must be declared in
exactly one place.

IMPORTANT LIMITATION — this module is NOT importable from any service container
-------------------------------------------------------------------------------
Every service in ``docker-compose.unified.yml`` builds with
``context: ./services/<name>``, so repo-root ``shared/`` is outside the build
context and cannot be ``COPY``d. ``services/trading-engine/Dockerfile``,
``services/risk-metrics-service/Dockerfile`` and
``services/technical-analysis/Dockerfile`` copy only ``app/``. No compose volume
mounts ``shared/`` into any service, and ``PYTHONPATH=/app``. The one apparent
precedent (``portfolio-manager/app/handlers/health.py`` importing
``shared.database.connection``) is a silently-dead import: that Dockerfile does
``RUN mkdir -p ./shared``, creating an EMPTY directory, and the import sits
inside ``except ImportError``.

Consequence, stated plainly rather than pretended away:

    | Location                                         | In container? | Rule                                      |
    |--------------------------------------------------|---------------|-------------------------------------------|
    | ``services/*/app/**``                            | YES           | Read the service's own ``Settings``.      |
    |                                                  |               | NEVER import ``shared.account``.          |
    | ``backtesting/``,                                | NO            | Import ``shared.account`` directly.       |
    | ``services/technical-analysis/backtesting/``,    | (host-run)    |                                           |
    | ``tests/``, ``services/*/tests/``                |               |                                           |

Agreement between this module and in-container ``Settings`` defaults is enforced
at TEST time by ``tests/test_account_config_sync.py``, not at BOOT time. A boot
assert would require the import above and therefore a Dockerfile/compose change.
That is weaker than a boot assert; it is recorded here so the weakness is not
mistaken for a guarantee.

Packaging note
--------------
``shared/`` has no ``__init__.py`` — it is an implicit namespace package.
``import shared.account`` therefore resolves only when the repository root is on
``sys.path`` (which it is under pytest, whose rootdir is the repo root). Do not
add an ``__init__.py``; other code relies on the current layout.

UNITS ARE NOT UNIFORM — this is deliberate, and it is why every constant carries
its unit in its name. ``MAX_RISK_PER_TRADE`` is a FRACTION (0.10 = 10%) while
``MAX_DAILY_LOSS_PCT`` and ``MAX_POSITION_SIZE_PCT`` are PERCENTS (5.0 = 5%).
This mirrors ``services/trading-engine/app/config.py`` exactly so the sync test
is a like-for-like comparison. Every cross-cap comparison in this module
normalises to a common unit FIRST — comparing ``0.10 > 5.0`` is a silent no-op
that would hide the single most consequential finding in the capital audit.
"""

from __future__ import annotations

import os
import warnings
from decimal import Decimal

__all__ = [
    "PAPER_INITIAL_BALANCE",
    "ACCOUNT_EQUITY_USD",
    "MAX_RISK_PER_TRADE",
    "MAX_DAILY_LOSS_PCT",
    "MAX_POSITION_SIZE_PCT",
    "LIVE_MAX_RISK_PER_TRADE",
    "MIN_NOTIONAL_USD",
    "TAKER_FEE_PER_SIDE",
    "DEFAULTS",
    "max_daily_loss_fraction",
    "max_position_size_fraction",
    "risk_budget_usd",
    "assert_capital_is_sane",
    "capital_config_warnings",
]


# ---------------------------------------------------------------------------
# Declared defaults, resolved INDEPENDENTLY of os.environ.
#
# `tests/test_account_config_sync.py` compares trading-engine
# `Settings.model_fields[...].default` against THIS mapping, not against the
# env-resolved constants below — otherwise the drift test would assert against
# whatever the operator currently has in `.env` instead of declared-default
# drift, which is the thing it exists to catch.
# ---------------------------------------------------------------------------
DEFAULTS: dict[str, float] = {
    # env key                  # declared default   # unit
    "PAPER_INITIAL_BALANCE": 100.0,  # USD
    "MAX_RISK_PER_TRADE": 0.10,  # fraction
    "MAX_DAILY_LOSS_PCT": 12.0,  # percent -- ADR-028, was 5.0
    "MAX_POSITION_SIZE_PCT": 10.0,  # percent
    "MIN_NOTIONAL_USD": 5.0,  # USD
    "TAKER_FEE_PER_SIDE": 0.00055,  # fraction
}


def _env_float(key: str) -> float:
    """Read `key` from the environment, falling back to its declared default."""
    raw = os.getenv(key)
    if raw is None or str(raw).strip() == "":
        return DEFAULTS[key]
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:  # config errors must be loud
        raise ValueError(f"{key}={raw!r} is not a valid number") from exc


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------

#: Real paper-trading account equity, USD. Env key `PAPER_INITIAL_BALANCE`
#: (trading-engine `Settings.paper_initial_balance`, config.py:557, `ge=100.0`).
PAPER_INITIAL_BALANCE: float = _env_float("PAPER_INITIAL_BALANCE")

#: Readable alias for call sites. Same value, same env key — NOT a second knob.
ACCOUNT_EQUITY_USD: float = PAPER_INITIAL_BALANCE


# ---------------------------------------------------------------------------
# Risk caps
# ---------------------------------------------------------------------------

#: Per-trade cap as a FRACTION of balance (0.10 = 10%). config.py:321,
#: `ge=0.001 le=0.5`. The 10% value is an ADR-010 workaround to clear Bybit's
#: minimum notional on a $100 balance — it is NOT a strategy parameter and must
#: be restored to `LIVE_MAX_RISK_PER_TRADE` before `TRADING_MODE=LIVE`.
MAX_RISK_PER_TRADE: float = _env_float("MAX_RISK_PER_TRADE")

#: Hard per-trade cap in LIVE mode, FRACTION. Non-negotiable per CLAUDE.md.
#: No env key — it is not operator-tunable by design.
LIVE_MAX_RISK_PER_TRADE: float = 0.02

#: Daily-loss circuit breaker as a PERCENT (5.0 = 5%). config.py:364,
#: `ge=1.0 le=20.0`. NOTE the unit differs from `MAX_RISK_PER_TRADE`.
MAX_DAILY_LOSS_PCT: float = _env_float("MAX_DAILY_LOSS_PCT")

#: Max notional of any single position as a PERCENT of equity (10.0 = 10%).
#: config.py:311, `ge=0.1 le=50.0`.
MAX_POSITION_SIZE_PCT: float = _env_float("MAX_POSITION_SIZE_PCT")


# ---------------------------------------------------------------------------
# Venue reality
# ---------------------------------------------------------------------------

#: Bybit linear-perp minimum order value, USD. Conservative default; the real
#: value is per-symbol and should come from instrument info when available.
MIN_NOTIONAL_USD: float = _env_float("MIN_NOTIONAL_USD")

#: Bybit taker fee per side, FRACTION. A round trip is 2x this.
TAKER_FEE_PER_SIDE: float = _env_float("TAKER_FEE_PER_SIDE")


# ---------------------------------------------------------------------------
# Unit normalisation
#
# Every cross-cap comparison MUST go through these. Comparing a fraction to a
# percent directly (`MAX_RISK_PER_TRADE > MAX_DAILY_LOSS_PCT` -> `0.10 > 5.0`
# -> False) silently never fires, which is exactly how the risk-cap conflict
# stayed invisible.
# ---------------------------------------------------------------------------


def max_daily_loss_fraction() -> float:
    """`MAX_DAILY_LOSS_PCT` expressed as a fraction (5.0 percent -> 0.05)."""
    return MAX_DAILY_LOSS_PCT / 100.0


def max_position_size_fraction() -> float:
    """`MAX_POSITION_SIZE_PCT` expressed as a fraction (10.0 percent -> 0.10)."""
    return MAX_POSITION_SIZE_PCT / 100.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def risk_budget_usd(
    equity: float | Decimal | None = None, *, live: bool = False
) -> Decimal:
    """USD at risk on a single trade, given the active per-trade cap.

    >>> risk_budget_usd()          # paper, $100 account, 10% cap
    Decimal('10.00')
    >>> risk_budget_usd(live=True)  # LIVE, $100 account, 2% cap
    Decimal('2.00')
    """
    eq = Decimal(str(PAPER_INITIAL_BALANCE if equity is None else equity))
    cap = Decimal(str(LIVE_MAX_RISK_PER_TRADE if live else MAX_RISK_PER_TRADE))
    return (eq * cap).quantize(Decimal("0.01"))


def assert_capital_is_sane() -> None:
    """Raise on a structurally nonsensical capital configuration.

    Bounds mirror `services/trading-engine/app/config.py` Field constraints
    EXACTLY, each in its own unit. This function deliberately does NOT raise on
    the 10%-per-trade vs 5%-daily conflict: that is a real risk-policy conflict
    reserved for an operator ADR (recovery-plan step 5), and turning it into a
    boot-blocker here would be an out-of-scope change to trading behaviour. It
    is surfaced through `capital_config_warnings()` instead.
    """
    if PAPER_INITIAL_BALANCE < 100.0:
        raise ValueError(
            f"PAPER_INITIAL_BALANCE={PAPER_INITIAL_BALANCE} violates config.py "
            "Field(ge=100.0)"
        )
    if not (0.001 <= MAX_RISK_PER_TRADE <= 0.5):
        raise ValueError(
            f"MAX_RISK_PER_TRADE={MAX_RISK_PER_TRADE} (fraction) outside "
            "config.py bounds [0.001, 0.5]"
        )
    if not (1.0 <= MAX_DAILY_LOSS_PCT <= 20.0):
        raise ValueError(
            f"MAX_DAILY_LOSS_PCT={MAX_DAILY_LOSS_PCT} (percent) outside "
            "config.py bounds [1.0, 20.0]"
        )
    if not (0.1 <= MAX_POSITION_SIZE_PCT <= 50.0):
        raise ValueError(
            f"MAX_POSITION_SIZE_PCT={MAX_POSITION_SIZE_PCT} (percent) outside "
            "config.py bounds [0.1, 50.0]"
        )
    for message in capital_config_warnings():
        warnings.warn(message, RuntimeWarning, stacklevel=2)


def capital_config_warnings() -> list[str]:
    """Known-bad-but-not-fatal capital configurations, as human-readable strings.

    These are design conflicts rather than typos, so they warn instead of
    raising — but they should be resolved, not ignored.
    """
    problems: list[str] = []

    # UNIT NORMALISATION IS THE WHOLE POINT HERE. 0.10 > 0.05 -> True.
    if MAX_RISK_PER_TRADE > max_daily_loss_fraction():
        problems.append(
            f"RISK CAP CONFLICT: MAX_RISK_PER_TRADE={MAX_RISK_PER_TRADE} "
            f"(fraction, ={MAX_RISK_PER_TRADE * 100:.1f}%) exceeds "
            f"MAX_DAILY_LOSS_PCT={MAX_DAILY_LOSS_PCT}% "
            f"(={max_daily_loss_fraction()} as a fraction). A single losing "
            "trade can trip the daily circuit breaker, so the breaker is not "
            "really a breaker. This is the direct consequence of the ADR-010 "
            "relaxation to 10% to clear Bybit min-notional on a $100 account — "
            "the two rules were never reconciled. Resolve by raising equity, "
            "lowering the per-trade cap, or widening the daily cap deliberately "
            "and recording the decision as an ADR. DEFERRED: recovery-plan "
            "step 5, operator decision."
        )

    budget = risk_budget_usd()
    if budget < Decimal(str(MIN_NOTIONAL_USD)):
        problems.append(
            f"SIZING FLOOR: risk budget {budget} USD is below the "
            f"{MIN_NOTIONAL_USD} USD venue minimum. Any trade that clears "
            "min-notional necessarily exceeds the per-trade risk cap. Trades "
            "must be REJECTED here, never clamped up to the minimum."
        )

    round_trip_fee = TAKER_FEE_PER_SIDE * 2
    if round_trip_fee * 500 > 0.10:
        problems.append(
            f"FEE DRAG: round-trip cost is {round_trip_fee:.4%} of notional. At "
            "the trade counts seen in backtests (2,000-4,600 per run) fees alone "
            "exceed any observed edge. Any strategy evaluation must be net of "
            "fees."
        )

    return problems
