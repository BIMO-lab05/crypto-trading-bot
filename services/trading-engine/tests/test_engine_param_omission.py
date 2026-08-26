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

Run from `services/trading-engine` with `--no-cov` (see .claude/rules/testing.md).
"""

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
