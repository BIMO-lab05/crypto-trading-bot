"""
The engine must not send indicator parameters that TA Settings own.

Why this assertion exists, in engine terms: when this client sends its own
`period` / `tenkan_period` / ... on the outbound call, the engine's literal
wins on the *traded* path while a bare call to the same TA endpoint resolves
to the TA service's declared default. The two then disagree with nothing in
either service able to detect it — one number is traded, a different number is
published to the dashboard and to anyone reading `config.py`.

That is exactly the drift the 2026-08-20 MACD rewire closed for MACD
(`signal_aggregator.fetch_macd:168-186` — "No fast/slow/signal here on
purpose"). It was closed in one place and left everywhere else. This file pins
the contract for the remaining fetchers so the next re-introduction fails at
the introducing commit instead of silently splitting the traded parameters
from the declared ones.

`fetch_macd` is included as a regression guard on the already-closed fix.

This assertion cannot live in the technical-analysis suite: it is about the
trading-engine's *outbound* request params, and the two services share no
`Settings` object. The TA-side mirror of this contract is
`services/technical-analysis/tests/test_endpoint_defaults_from_settings.py`
(`WIRED_ROUTE_DEFAULTS` / `WIRED_HANDLER_DEFAULTS`), which pins the declared
value; this file pins that the engine does not override it.

As of DEFER-21-04 (2026-08-27) this file also pins a second, adjacent
contract: parameters the engine computes with LOCALLY that duplicated a
technical-analysis declaration. `strategies/trend_following.py` and
`strategies/trend_following_strategy.py` contain no HTTP client at all — both
compute ADX from OHLCV arrays in-process — so their `adx_period` declarations
were never sent anywhere. They were simply a second and third copy of TA's
`default_adx_period = 14`, agreeing by coincidence rather than by routing.

Those sites need a different assertion shape. With no outbound request there
are no captured params to inspect, so the observable is the SIGNATURE: the
parameter must be GONE, not merely disconnected. A parameter left on a
constructor after it stops reaching anything is worse than no parameter —
a caller can set it, see no error, and get no effect, which is the silent
divergence this whole file exists to prevent, wearing a different hat.

Run from `services/trading-engine` with `--no-cov` (see .claude/rules/testing.md).
"""

import dataclasses
import inspect
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.signal_aggregator import SignalAggregator

# One payload that satisfies every fetcher under test.
#
# sma/ema/macd read the JSON body directly; ichimoku reads `result["data"]`
# and tolerates either a dict or a [data, signal, confidence] list. A single
# superset dict keeps the parametrization readable — each fetcher picks out
# the keys it needs and ignores the rest.
_ICHIMOKU_DATA = {
    "signal": "BUY",
    "confidence": 0.7,
    "current_price": 100.0,
    "tenkan_sen": 100.0,
    "kijun_sen": 99.0,
    "senkou_span_a": 99.5,
    "senkou_span_b": 98.0,
    "chikou_span": 101.0,
    "cloud_color": "GREEN",
    "price_position": "ABOVE_CLOUD",
    "tk_cross": "BULLISH",
    "cloud_thickness": 1.5,
}

_PAYLOAD = {
    # sma / ema / macd
    "signal": "BUY",
    "confidence": 0.7,
    "value": 100.0,
    "current_price": 100.0,
    "histogram": 0.5,
    "macd_line": 1.0,
    "signal_line": 0.5,
    # ichimoku
    "data": _ICHIMOKU_DATA,
}


# (fetcher name, params the TA service owns and the engine must not send)
OMISSION_CONTRACT = [
    ("fetch_sma", {"period"}),
    ("fetch_ema", {"period"}),
    ("fetch_ichimoku", {"tenkan_period", "kijun_period", "senkou_b_period"}),
    ("fetch_macd", {"fast", "slow", "signal"}),
]


@pytest.mark.parametrize(
    "method_name,forbidden_keys",
    OMISSION_CONTRACT,
    ids=[name for name, _ in OMISSION_CONTRACT],
)
async def test_engine_omits_params_owned_by_ta_settings(method_name, forbidden_keys):
    """The outbound GET must carry no parameter the TA service declares."""
    agg = SignalAggregator()
    captured = {}

    async def _capture(url, params=None, **kwargs):
        captured["url"] = url
        captured["params"] = params
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(return_value=_PAYLOAD)
        return response

    agg.client.get = AsyncMock(side_effect=_capture)

    try:
        result = await getattr(agg, method_name)("BTCUSDT", "60")
    finally:
        await agg.close()

    assert result is not None, (
        f"{method_name} returned None — the fetcher raised before/while "
        f"issuing the request, so the param assertion below would be vacuous. "
        f"Captured: {captured}"
    )

    params = captured.get("params") or {}
    leaking = forbidden_keys & set(params)

    assert not leaking, (
        f"{method_name} sent {sorted(leaking)}, which the technical-analysis "
        f"service declares in its Settings. The engine's literal would win on "
        f"the traded path while a bare call to {captured.get('url')} resolves "
        f"to the TA default — the two disagree silently. Omit the parameter "
        f"(see fetch_macd for the pattern).\n"
        f"Full captured params: {params}"
    )


# ---------------------------------------------------------------------------
# DEFER-21-04 — the ADX lookback is declared once, in engine Settings
#
# These are plain test functions, NOT `OMISSION_CONTRACT` rows. That
# parametrization drives a fetcher and inspects the params it put on the wire;
# the two trend-following modules issue no request, so routing them through it
# would assert nothing at all while looking like it asserted something.
# ---------------------------------------------------------------------------


def test_trend_following_strategy_no_longer_accepts_a_dead_adx_period_argument():
    """A parameter that no longer reaches anything is worse than no parameter.

    Leaving `adx_period` on the constructor after single-sourcing the lookback
    to Settings means a caller can pass it, get no error, and get no effect —
    the strategy would keep computing with the declared setting while the
    caller believes it honoured the argument. Deleting it makes the same
    mistake a TypeError at the call site.
    """
    from app.strategies.trend_following_strategy import TrendFollowingStrategy

    params = inspect.signature(TrendFollowingStrategy.__init__).parameters
    assert "adx_period" not in params, (
        "TrendFollowingStrategy.__init__ still accepts adx_period, but nothing "
        "in the class reads it: _calculate_adx and the warm-up check both "
        "resolve get_settings().adx_period. An accepted-and-ignored argument "
        "is a silent divergence, not a compatibility shim.\n"
        f"Current parameters: {sorted(params)}"
    )


def test_trend_following_config_no_longer_declares_an_adx_period_field():
    """The dataclass copy is gone too — deleting one of three is not a fix.

    `TrendFollowingConfig.adx_period` was the third declaration of the same
    number (TA's `default_adx_period`, this dataclass, and the sibling
    module's `ADX_PERIOD` constant). Removing only the constructor parameter
    would have left the dataclass free to drift on its own.
    """
    from app.strategies.trend_following import TrendFollowingConfig

    field_names = {f.name for f in dataclasses.fields(TrendFollowingConfig)}
    assert "adx_period" not in field_names, (
        "TrendFollowingConfig still declares an adx_period field. The ADX "
        "lookback is declared once, as Settings.adx_period; a dataclass "
        "default here would agree with it only by coincidence.\n"
        f"Current fields: {sorted(field_names)}"
    )


def test_engine_declares_the_adx_lookback_once_at_the_value_it_replaced():
    """14 is the number lifted out of both trend-following modules.

    It must not move as a side effect of the de-duplication: the point of
    DEFER-21-04 was to make the number single-sourced, not to change it.
    """
    from app.config import get_settings

    assert get_settings().adx_period == 14, (
        "14 was the literal in TrendFollowingConfig.adx_period "
        "(app/strategies/trend_following.py) and in the ADX_PERIOD module "
        "constant (app/strategies/trend_following_strategy.py), and it is the "
        "value technical-analysis declares as default_adx_period. Moving it "
        "changes what both dormant strategies compute and needs a recorded "
        "decision, not a drive-by edit."
    )


# ---------------------------------------------------------------------------
# Source guard — a deleted declaration must not come back silently
#
# Deliberately NARROW. These patterns match declaration and assignment forms
# only, never the bare token. The removal-rationale comments this fix left at
# every site all contain the word `adx_period` on purpose — they are how the
# next reader learns where the number went. A bare-token guard would fail on
# its own documentation and teach the next person to delete the explanation,
# which is the opposite of what a guard is for.
# ---------------------------------------------------------------------------

_APP = Path(__file__).resolve().parents[1] / "app"

_ADX_DECLARATION_FORMS = [
    (
        r"adx_period\s*:\s*int\s*=",
        "an annotated adx_period declaration (dataclass field or constructor "
        "parameter) re-introduces a second copy of Settings.adx_period",
    ),
    (
        r"self\.adx_period\b",
        "a per-instance adx_period attribute is a snapshot: it freezes the "
        "setting at construction time, so an override applied later is "
        "invisible to an already-built strategy",
    ),
    (
        r"^ADX_PERIOD\s*=",
        "a module-level ADX lookback constant is the exact declaration "
        "DEFER-21-04 deleted; it agreed with TA's default_adx_period by "
        "coincidence",
    ),
    (
        r"strategy_config\.adx_period",
        "reading the lookback back off the config dataclass restores the "
        "declaration this fix removed from it",
    ),
]

BANNED_ADX_DECLARATIONS = [
    (relpath, pattern, why)
    for relpath in (
        "strategies/trend_following.py",
        "strategies/trend_following_strategy.py",
    )
    for pattern, why in _ADX_DECLARATION_FORMS
]


@pytest.mark.parametrize(
    "relpath,pattern,why",
    BANNED_ADX_DECLARATIONS,
    ids=[f"{rel}::{pat}" for rel, pat, _ in BANNED_ADX_DECLARATIONS],
)
def test_no_trend_following_file_regained_a_local_adx_declaration(
    relpath, pattern, why
):
    source = (_APP / relpath).read_text(encoding="utf-8")
    hits = [
        f"{i}: {line.strip()}"
        for i, line in enumerate(source.splitlines(), start=1)
        if re.search(pattern, line)
    ]
    assert not hits, (
        f"app/{relpath} matched the banned pattern {pattern!r} — {why}.\n"
        + "\n".join(hits)
    )


# (regex, a line it MUST match, a rationale comment it MUST NOT match)
_GUARD_DISCRIMINATION = [
    (
        r"adx_period\s*:\s*int\s*=",
        "    adx_period: int = 14",
        "# the adx_period lookback now lives in Settings",
    ),
    (
        r"self\.adx_period\b",
        "        self.adx_period = adx_period",
        "# no caller ever passed adx_period, so nothing broke",
    ),
    (
        r"^ADX_PERIOD\s*=",
        "ADX_PERIOD = 14  # ADX calculation period",
        "# there is no ADX-lookback constant here; see Settings adx_period",
    ),
    (
        r"strategy_config\.adx_period",
        "        period = period or self.strategy_config.adx_period",
        "# the dataclass no longer carries an adx_period field",
    ),
]


@pytest.mark.parametrize(
    "pattern,declaration,comment",
    _GUARD_DISCRIMINATION,
    ids=[pat for pat, _, _ in _GUARD_DISCRIMINATION],
)
def test_adx_guard_patterns_discriminate_declarations_from_documentation(
    pattern, declaration, comment
):
    """The guard must catch the defect and spare the explanation of the defect.

    Checked against throwaway strings rather than by re-adding the declaration
    to the real source: the ruff format hook reflows on write, so a
    temporarily-restored line does not come back byte-identical.
    """
    assert re.search(pattern, declaration), (
        f"{pattern!r} does not match {declaration!r} — the guard is inert and "
        f"would let the declaration return unnoticed"
    )
    assert not re.search(pattern, comment), (
        f"{pattern!r} matches the rationale comment {comment!r}. A guard that "
        f"fires on its own documentation gets 'fixed' by deleting the "
        f"documentation, which is how the reason for a removal gets lost"
    )
