"""P21-7: the mirror-literal cluster must resolve from a declaration, never a literal.

Five sites in the trading-engine hardcoded a number the technical-analysis
service already declares, and one of them re-derived a classification TA
already returns. They agreed with their counterparts only by coincidence:
nothing read one from the other, so a single env override on the TA side
would have moved one number while the engine kept applying the old one, with
nothing in either service able to notice.

Source: `.planning/audits/2026-08-26-ta-signal-path-audit.md` (defect P21-7),
scoped by `.planning/phases/21-ta-aggregator-widening-leakage-net/21-CONTEXT.md`.

The five sites and how each was resolved:

| Site | Resolution |
|---|---|
| `signal_aggregator.fetch_adx` ADX vote gate | `settings.adx_weak_trend_threshold` |
| `sqzmom_strategy_integration` ADX demotion | `settings.adx_weak_trend_threshold` |
| `sqzmom_strategy_integration` volume demotion | `settings.sqzmom_volume_ratio_min` |
| `handlers/signals._fetch_market_regime` | reads TA's own `regime` field |
| `aggregation/market_regime._fetch_adx_data` | omits the TA-owned `period` |

NO THRESHOLD VALUE CHANGED. Every default asserted here equals the literal it
replaced (20.0, 1.2), and the omitted ADX period equals TA's already-declared
`default_adx_period` (14).

The behavioural assertions below are the load-bearing ones. A source grep
proves a literal is gone; it does not prove the setting is wired. Each
converted site therefore also has a test that moves the setting to a
non-default value and asserts the gate moves with it.

DEFER-21-03 (2026-08-27) closed the last three sites of the same class,
all of them request parameters the engine sends to technical-analysis:

| Site | Resolution |
|---|---|
| `signal_aggregator.fetch_rsi` lookback default | `settings.rsi_period` |
| `signal_aggregator.fetch_bollinger_bands` band width | `settings.bollinger_std_dev` |
| `signal_aggregator.fetch_trend_filter` kline count | `settings.trend_filter_kline_limit` |

Those three are the MIRROR of the omission contract in
`tests/test_engine_param_omission.py`, not an instance of it: 22.1-CONTEXT
item B has the engine keep sending them with an engine-side declaration.
NO VALUE CHANGED there either — 9, 2.5 and 300 are the literals replaced.

DEFER-21-05 (2026-08-28) closed the one member of this class that was NOT a
mirror: `_fetch_market_regime` returned a fixed `"confidence": 0.7` while
technical-analysis published a computed confidence on the very same response.
There was no counterpart to agree or disagree with — the number was invented
here and reported downstream as a measurement. A VALUE DID CHANGE for that
site, which is why it carries a committed before/after measurement
(`.planning/evidence/22.1-regime-confidence-measurement.json`) that the three
above do not need.

Run from `services/trading-engine` with `--no-cov` (see .claude/rules/testing.md).
"""

import logging
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import annotated_types
import pytest

from app.config import Settings, get_settings
from app.models import SignalAction
from app.signal_aggregator import SignalAggregator
from app.strategies.sqzmom_strategy_integration import SQZMOMStrategy

# The [SQZMOM_GATE] messages are emitted by this module's own logger; caplog
# must be pointed at it explicitly or the propagation config decides for us.
_SQZMOM_LOGGER = "app.strategies.sqzmom_strategy_integration"


def _bound(field_name: str, kind) -> float | None:
    """Read a declared ge/le off the pydantic Field metadata."""
    for meta in Settings.model_fields[field_name].metadata:
        if isinstance(meta, kind):
            return meta.ge if kind is annotated_types.Ge else meta.le
    return None


# ---------------------------------------------------------------------------
# Task 1 — the two engine-owned mirror fields are declared, bounded, documented
# ---------------------------------------------------------------------------


def test_adx_weak_trend_threshold_defaults_to_the_literal_it_replaced():
    """20.0 is the number lifted out of the two ADX gates. It must not move."""
    assert get_settings().adx_weak_trend_threshold == 20.0, (
        "20.0 was the inline literal in signal_aggregator.fetch_adx and in "
        "sqzmom_strategy_integration's ADX gate. Moving it changes the traded "
        "signal and needs operator approval (21-CONTEXT threshold lock)."
    )


def test_sqzmom_volume_ratio_min_defaults_to_the_literal_it_replaced():
    """1.2 is the number lifted out of the SQZMOM volume gate."""
    assert get_settings().sqzmom_volume_ratio_min == 1.2, (
        "1.2 was the inline literal in sqzmom_strategy_integration's volume "
        "gate. Moving it changes the traded signal and needs operator "
        "approval (21-CONTEXT threshold lock)."
    )



def test_rsi_period_defaults_to_the_literal_it_replaced():
    """9 is the lookback lifted out of fetch_rsi's parameter default."""
    assert get_settings().rsi_period == 9, (
        "9 was the inline default on signal_aggregator.fetch_rsi's `period` "
        "parameter, and it is the lookback the engine sends on every RSI "
        "request. Moving it changes the traded signal."
    )


def test_bollinger_std_dev_defaults_to_the_literal_it_replaced():
    """2.5 is the band-width multiplier lifted out of the Bollinger request."""
    assert get_settings().bollinger_std_dev == 2.5, (
        "2.5 was the inline multiplier in the request params of "
        "signal_aggregator.fetch_bollinger_bands (widened for crypto "
        "volatility). Moving it changes the traded signal."
    )


def test_trend_filter_kline_limit_defaults_to_the_literal_it_replaced():
    """300 is the kline count lifted out of the trend-filter request."""
    assert get_settings().trend_filter_kline_limit == 300, (
        "300 was the inline kline count in the request params of "
        "signal_aggregator.fetch_trend_filter; the 50/200 EMA pair needs that "
        "much history to be defined at all."
    )


@pytest.mark.parametrize(
    "field_name,ge,le",
    [
        ("adx_weak_trend_threshold", 0.0, 100.0),
        ("sqzmom_volume_ratio_min", 0.0, 10.0),
        # DEFER-21-03. 1.0-4.0 is the bound technical-analysis already
        # enforces on its own Bollinger route, so an engine-side override
        # TA would reject cannot even be declared here.
        ("bollinger_std_dev", 1.0, 4.0),
    ],
)
def test_mirror_field_is_a_bounded_float(field_name, ge, le):
    """An unbounded env override is how a gate silently stops firing.

    ASVS V14: config that reaches a money path is typed and range-checked at
    the declaration, not defensively re-checked at every use site.
    """
    field = Settings.model_fields[field_name]
    assert field.annotation is float, f"{field_name} must be a float Field"
    assert _bound(field_name, annotated_types.Ge) == ge, (
        f"{field_name} lost its ge bound — an override below {ge} would be accepted"
    )
    assert _bound(field_name, annotated_types.Le) == le, (
        f"{field_name} lost its le bound — an override above {le} would be accepted"
    )


@pytest.mark.parametrize(
    "field_name,ge,le",
    [
        ("rsi_period", 2, 100),
        # 200-1000 is technical-analysis's own trend-route bound.
        ("trend_filter_kline_limit", 200, 1000),
    ],
)
def test_mirror_field_is_a_bounded_int(field_name, ge, le):
    """Sibling of the bounded-float test for the two integer mirrors.

    These two cannot ride `test_mirror_field_is_a_bounded_float`'s parametrize:
    that test asserts `field.annotation is float`, so an int field would fail on
    the annotation rather than on the bound the test exists to check — a red
    test that proves nothing about the bound.

    Same ASVS V14 reasoning as the float case: config reaching a money path is
    range-checked at the declaration. An unbounded kline count is also a
    denial-of-service knob against technical-analysis.
    """
    field = Settings.model_fields[field_name]
    assert field.annotation is int, f"{field_name} must be an int Field"
    assert _bound(field_name, annotated_types.Ge) == ge, (
        f"{field_name} lost its ge bound — an override below {ge} would be accepted"
    )
    assert _bound(field_name, annotated_types.Le) == le, (
        f"{field_name} lost its le bound — an override above {le} would be accepted"
    )


@pytest.mark.parametrize(
    "field_name,expected_phrase",
    [
        # Mirrored: the description must name the TA field it must not diverge from.
        ("adx_weak_trend_threshold", "default_adx_weak_trend_threshold"),
        # Engine-owned: the description must say outright that there is no TA field,
        # so a reader does not go hunting for one that does not exist.
        ("sqzmom_volume_ratio_min", "no counterpart"),
        # DEFER-21-03: all three mirror a TA declaration and must name it.
        ("rsi_period", "default_rsi_period"),
        ("bollinger_std_dev", "default_bb_std"),
        ("trend_filter_kline_limit", "default_trend_limit"),
    ],
)
def test_mirror_field_description_names_its_ta_counterpart_or_says_there_is_none(
    field_name, expected_phrase
):
    description = Settings.model_fields[field_name].description or ""
    assert expected_phrase in description, (
        f"{field_name}'s description must state its technical-analysis "
        f"counterpart (or that none exists). Expected {expected_phrase!r} in:\n"
        f"{description!r}"
    )


# ---------------------------------------------------------------------------
# Task 2 — the three Settings-backed sites are wired, not merely de-literalled
#
# A source grep proves a literal is gone. It does not prove the setting reaches
# the comparison: `if adx_val < ADX_FLOOR` with a module constant would pass a
# grep and still be the same defect. Every assertion below therefore moves the
# setting to a non-default value and asserts the gate outcome moves with it.
# ---------------------------------------------------------------------------


def _adx_response(adx: float, direction: str = "BULLISH", regime: str = "TRENDING"):
    """A TA `/indicators/adx/{symbol}` response, in the shape fetch_adx parses."""
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(
        return_value={
            "success": True,
            "data": {
                "adx": adx,
                "direction": direction,
                "regime": regime,
                "confidence": 0.6,
                "plus_di": 30.0,
                "minus_di": 10.0,
            },
        }
    )
    return response


@pytest.mark.parametrize(
    "threshold,expected",
    [
        # Declared default is 20.0, so an ADX of 25 clears it and ADX votes.
        (None, SignalAction.BUY),
        # Raised above the reading: the same bar must stop producing a vote.
        (30.0, SignalAction.HOLD),
    ],
    ids=["default_threshold_votes", "raised_threshold_silences_the_vote"],
)
async def test_adx_vote_gate_resolves_from_settings(monkeypatch, threshold, expected):
    """fetch_adx's directional gate must move when adx_weak_trend_threshold moves."""
    if threshold is not None:
        monkeypatch.setattr(get_settings(), "adx_weak_trend_threshold", threshold)

    agg = SignalAggregator()
    agg.client.get = AsyncMock(return_value=_adx_response(25.0))
    try:
        result = await agg.fetch_adx("BTCUSDT", "60")
    finally:
        await agg.close()

    assert result is not None, "fetch_adx raised — the assertion below would be vacuous"
    assert result.signal == expected, (
        f"ADX 25.0 with adx_weak_trend_threshold="
        f"{threshold if threshold is not None else 20.0} should vote {expected}, "
        f"got {result.signal}. The gate is not reading the setting."
    )


def _sqzmom_http(
    adx: float = 30.0,
    direction: str = "BULLISH",
    ratio: float = 2.0,
    confirmed: bool = True,
    action: str = "BUY",
):
    """Route SQZMOMStrategy's four outbound calls by URL.

    `get_signal` hits the sqzmom signal endpoint, then ATR, then ADX, then
    volume. Returning one payload for all four (as the pre-existing, currently
    skipped tests do) silently lands ADX at 0.0 and demotes every signal.
    """
    base = {
        "symbol": "SOLUSDT",
        "interval": "60",
        "timestamp": 0,
        "action": action,
        "confidence": 0.85,
        "entry_price": 100.0,
        "stop_loss": 98.0,
        "take_profit": 104.0,
        "reason": "test",
        "momentum": 0.45,
        "squeeze_state": "OFF",
        "momentum_color": "lime",
    }

    async def _get(url, params=None, **kwargs):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        if "/indicators/adx/" in url:
            payload = {"data": {"adx": adx, "direction": direction}}
        elif "/indicators/volume/" in url:
            payload = {"data": {"confirmed": confirmed, "ratio": ratio}}
        elif "/indicators/atr/" in url:
            payload = {"data": {}}
        else:
            payload = base
        response.json = MagicMock(return_value=payload)
        return response

    return _get


@pytest.mark.parametrize(
    "threshold,expected_action",
    [
        # Default 20.0: an ADX of 25 survives the trend-strength gate.
        (None, "BUY"),
        # Raised to 30.0: the same bar is demoted to HOLD.
        (30.0, "HOLD"),
    ],
    ids=["default_threshold_admits", "raised_threshold_demotes"],
)
async def test_sqzmom_adx_gate_resolves_from_settings(
    monkeypatch, caplog, threshold, expected_action
):
    """The SQZMOM ADX demotion must share the engine's declared weak-trend floor."""
    if threshold is not None:
        monkeypatch.setattr(get_settings(), "adx_weak_trend_threshold", threshold)

    strategy = SQZMOMStrategy()
    strategy.http_client.get = AsyncMock(side_effect=_sqzmom_http(adx=25.0))
    try:
        with caplog.at_level(logging.INFO, logger=_SQZMOM_LOGGER):
            signal = await strategy.get_signal("SOLUSDT", "60")
    finally:
        await strategy.close()

    assert signal is not None, "get_signal returned None — assertion would be vacuous"
    assert signal["action"] == expected_action, (
        f"ADX 25.0 with adx_weak_trend_threshold="
        f"{threshold if threshold is not None else 20.0} should resolve to "
        f"{expected_action}, got {signal['action']} "
        f"(gate_rejection={signal.get('gate_rejection')})"
    )
    if expected_action == "HOLD":
        assert signal["gate_rejection"] == "adx_weak_trend"
        assert "30.0" in caplog.text, (
            "the [SQZMOM_GATE] log must report the RESOLVED threshold. A message "
            "reading '< 20' while the setting says 30 is the same defect wearing "
            "a different hat — it is how an operator debugs against a value the "
            f"code no longer applies.\nCaptured log:\n{caplog.text}"
        )


@pytest.mark.parametrize(
    "floor,expected_action",
    [
        # Default 1.2: a ratio of 1.5 confirms.
        (None, "BUY"),
        # Raised to 2.0: the same bar is demoted to HOLD.
        (2.0, "HOLD"),
    ],
    ids=["default_floor_admits", "raised_floor_demotes"],
)
async def test_sqzmom_volume_gate_resolves_from_settings(
    monkeypatch, caplog, floor, expected_action
):
    """The SQZMOM volume demotion must read sqzmom_volume_ratio_min."""
    if floor is not None:
        monkeypatch.setattr(get_settings(), "sqzmom_volume_ratio_min", floor)

    strategy = SQZMOMStrategy()
    # ADX 30 with a matching direction clears the trend gate in every case, so
    # only the volume gate can be responsible for a demotion here.
    strategy.http_client.get = AsyncMock(side_effect=_sqzmom_http(adx=30.0, ratio=1.5))
    try:
        with caplog.at_level(logging.INFO, logger=_SQZMOM_LOGGER):
            signal = await strategy.get_signal("SOLUSDT", "60")
    finally:
        await strategy.close()

    assert signal is not None, "get_signal returned None — assertion would be vacuous"
    assert signal["action"] == expected_action, (
        f"volume_ratio 1.5 with sqzmom_volume_ratio_min="
        f"{floor if floor is not None else 1.2} should resolve to "
        f"{expected_action}, got {signal['action']} "
        f"(gate_rejection={signal.get('gate_rejection')})"
    )
    if expected_action == "HOLD":
        assert signal["gate_rejection"] == "weak_volume"
        assert "2.0" in caplog.text, (
            "the [SQZMOM_GATE] volume log must report the RESOLVED floor, not a "
            f"baked-in '<1.2'.\nCaptured log:\n{caplog.text}"
        )


# ---------------------------------------------------------------------------
# DEFER-21-03 — the three request params are wired, not merely de-literalled
#
# Same doctrine as the block above, one layer out: these sites do not feed a
# comparison, they feed the OUTBOUND REQUEST. So the observable that has to
# move is the captured `params` dict, not a returned SignalAction.
#
# Vacuity guard: every fetcher below wraps its body in `except Exception:
# return None`, and `captured` is written before the payload is parsed. A stub
# missing one key would therefore leave the params assertion passing while the
# call silently failed. Each test asserts the fetcher returned non-None FIRST,
# exactly as `test_adx_vote_gate_resolves_from_settings` does above.
# ---------------------------------------------------------------------------


def _capturing_client(captured, payload):
    """AsyncMock that records the outbound params and replies with `payload`."""

    async def _capture(url, params=None, **kwargs):
        captured["url"] = url
        captured["params"] = params
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(return_value=payload)
        return response

    return AsyncMock(side_effect=_capture)


# Payloads in the exact shape each fetcher parses. Note the envelopes differ:
# fetch_trend_filter reads `result["data"]`, the other two read the top level.
# Reusing one shape across all three would make the fetcher swallow a KeyError,
# return None, and leave the params assertion vacuous.
_RSI_PAYLOAD = {"signal": "BUY", "confidence": 0.85, "rsi": 35.5}

_BOLLINGER_PAYLOAD = {
    "signal": "BUY",
    "confidence": 0.80,
    "current_price": 50000.0,
    "upper_band": 52000.0,
    "middle_band": 50000.0,
    "lower_band": 48000.0,
}

_TREND_PAYLOAD = {
    "data": {
        "signal": "BUY",
        "confidence": 0.90,
        "spread_pct": 5.2,
        "trend": "UPTREND",
        "fast_ema": 50500.0,
        "slow_ema": 48000.0,
    }
}


async def _captured_params(monkeypatch, field, value, payload, call):
    """Move `field` off its default, run `call`, return the outbound params.

    `SignalAggregator.__init__` does `self.settings = get_settings()` — the
    cached singleton — so patching an attribute on that object is what the
    instance reads. This is the mechanism the ADX wiring test above already
    uses; do not swap in a freshly constructed Settings, which the aggregator
    would never consult.
    """
    monkeypatch.setattr(get_settings(), field, value)

    captured = {}
    agg = SignalAggregator()
    agg.client.get = _capturing_client(captured, payload)
    try:
        result = await call(agg)
    finally:
        await agg.close()

    assert result is not None, (
        f"the fetcher returned None, so it swallowed an exception before "
        f"parsing — the assertion on {field} reaching the wire would be vacuous"
    )
    return captured.get("params") or {}


async def test_rsi_period_reaches_the_outbound_request(monkeypatch):
    """With no caller-supplied period, the setting must be what gets sent."""
    params = await _captured_params(
        monkeypatch, "rsi_period", 11, _RSI_PAYLOAD,
        lambda agg: agg.fetch_rsi("BTCUSDT", "60"),
    )
    assert params.get("period") == 11, (
        f"fetch_rsi put period={params.get('period')!r} on the wire while "
        f"settings.rsi_period was 11. The request is not reading the setting; "
        f"deleting the literal alone would pass a source grep and still be the "
        f"same defect. Full captured params: {params}"
    )


async def test_an_explicit_rsi_period_still_outranks_the_setting(monkeypatch):
    """The setting is a DEFAULT, not an override.

    `tests/unit/test_signal_aggregator.py` calls `fetch_rsi(..., period=14)`
    and asserts on the result. If the body resolution ignored the argument, the
    engine would silently send its own lookback for every explicit caller.
    """
    params = await _captured_params(
        monkeypatch, "rsi_period", 11, _RSI_PAYLOAD,
        lambda agg: agg.fetch_rsi("BTCUSDT", "60", period=14),
    )
    assert params.get("period") == 14, (
        f"an explicit period=14 was overwritten by settings.rsi_period=11 "
        f"(sent {params.get('period')!r}). Resolution order is wrong: the "
        f"setting may only fill in when the caller passes None."
    )


async def test_bollinger_std_dev_reaches_the_outbound_request(monkeypatch):
    """The band-width multiplier on the wire must track the setting."""
    params = await _captured_params(
        monkeypatch, "bollinger_std_dev", 3.0, _BOLLINGER_PAYLOAD,
        lambda agg: agg.fetch_bollinger_bands("BTCUSDT", "60"),
    )
    assert params.get("std_dev") == 3.0, (
        f"fetch_bollinger_bands put std_dev={params.get('std_dev')!r} on the "
        f"wire while settings.bollinger_std_dev was 3.0. Band width decides "
        f"every BOLLINGER_BANDS vote, so a stuck value is a stuck voter. "
        f"Full captured params: {params}"
    )


async def test_trend_filter_kline_limit_reaches_the_outbound_request(monkeypatch):
    """The kline count on the wire must track the setting."""
    params = await _captured_params(
        monkeypatch, "trend_filter_kline_limit", 500, _TREND_PAYLOAD,
        lambda agg: agg.fetch_trend_filter("BTCUSDT", "60"),
    )
    assert params.get("limit") == 500, (
        f"fetch_trend_filter put limit={params.get('limit')!r} on the wire "
        f"while settings.trend_filter_kline_limit was 500. Too few klines and "
        f"the 200 EMA is undefined, which silences the GATEKEEPER leg. "
        f"Full captured params: {params}"
    )


# ---------------------------------------------------------------------------
# Source guard — a converted site must not silently regain an inline literal
# ---------------------------------------------------------------------------

_APP = Path(__file__).resolve().parents[2] / "app"

# (relative path under app/, banned regex, why it is banned)
BANNED_LITERALS = [
    (
        "signal_aggregator.py",
        r"adx_val\s*(>=|<)\s*20(\.0)?\b",
        "the ADX vote gate must compare against settings.adx_weak_trend_threshold",
    ),
    (
        "strategies/sqzmom_strategy_integration.py",
        r"adx_val\s*(>=|<)\s*20(\.0)?\b",
        "the SQZMOM trend gate must compare against settings.adx_weak_trend_threshold",
    ),
    (
        "strategies/sqzmom_strategy_integration.py",
        r"ratio\s*<\s*1\.2",
        "the SQZMOM volume gate must compare against settings.sqzmom_volume_ratio_min",
    ),
    (
        "strategies/sqzmom_strategy_integration.py",
        r"<\s*20 |<1\.2",
        "the [SQZMOM_GATE] log messages must interpolate the resolved threshold",
    ),
    (
        "handlers/signals.py",
        r"adx_value\s*>=\s*25|adx_value\s*<\s*20",
        "the handler must read TA's regime label, not re-derive it from thresholds",
    ),
    (
        "handlers/signals.py",
        r'\.get\("adx",\s*25\)|"adx":\s*25',
        "a missing ADX must stay absent, never be back-filled with a plausible 25",
    ),
    # DEFER-21-05. Narrow by design: it matches the key-and-value form only, so
    # neither the rationale comment left at the site (which names 0.7 in prose)
    # nor the degraded path's declared `"confidence": 0.5` can trip it.
    (
        "handlers/signals.py",
        r'"confidence":\s*0\.7',
        "the success path must report the confidence technical-analysis "
        "computed, never a fixed stand-in for it",
    ),
    (
        "aggregation/market_regime.py",
        r'"period"\s*:',
        "the ADX request must omit the period technical-analysis Settings own",
    ),
    (
        "aggregation/market_regime.py",
        r"adx_period",
        "the dead adx_period parameter must be gone, not merely disconnected",
    ),
    # DEFER-21-03. These three are deliberately narrow: they match the
    # assignment/param form only, so the removal-rationale comments left at
    # each site (which name the settings, never the numbers) cannot trip them.
    (
        "signal_aggregator.py",
        r"period:\s*int\s*=\s*9\b",
        "fetch_rsi's lookback must resolve from settings.rsi_period in the "
        "method body; a Settings read in a parameter default freezes at import",
    ),
    (
        "signal_aggregator.py",
        r'"std_dev":\s*2\.5',
        "the Bollinger request must send settings.bollinger_std_dev",
    ),
    (
        "signal_aggregator.py",
        r'"limit":\s*300',
        "the trend-filter request must send settings.trend_filter_kline_limit",
    ),
]


@pytest.mark.parametrize(
    "relpath,pattern,why",
    BANNED_LITERALS,
    ids=[f"{rel}::{pat}" for rel, pat, _ in BANNED_LITERALS],
)
def test_no_p21_7_site_regained_an_inline_literal(relpath, pattern, why):
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


# ---------------------------------------------------------------------------
# Task 3 — stop re-deriving what TA returns, stop sending what TA owns
# ---------------------------------------------------------------------------

# technical-analysis owns this vocabulary
# (`services/technical-analysis/app/indicators/adx.py::MarketRegime`). The two
# services share no code, so the engine test has to restate it; that is the
# REST-mesh reality this whole defect class lives in. If TA ever adds a fifth
# label, this list is the thing that must be updated alongside the engine map.
TA_REGIME_LABELS = ("STRONG_TREND", "TRENDING", "WEAK_TREND", "RANGING")


def _legacy_rederivation(adx: float) -> str:
    """The three-branch classifier P21-7 deleted from handlers/signals.py.

    Kept here, and ONLY here, so the equivalence claim in the summary is a
    executable assertion rather than prose: for every ADX value TA can report,
    reading TA's label must produce what the engine used to compute itself.
    """
    if adx >= 25:
        return "TRENDING"
    if adx < 20:
        return "RANGING"
    return "WEAK_TREND"


async def _drive_market_regime(monkeypatch, payload=None, raises=None):
    """Run `_fetch_market_regime` against a stubbed technical-analysis reply."""
    from app.handlers import signals as signals_handler

    async def _get(url, params=None, **kwargs):
        if raises is not None:
            raise raises
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(return_value=payload)
        return response

    monkeypatch.setattr(signals_handler.ml_client, "get", _get)
    return await signals_handler._fetch_market_regime("BTCUSDT", "60")


@pytest.mark.parametrize(
    "ta_regime,adx",
    [
        ("STRONG_TREND", 35.0),
        ("TRENDING", 27.0),
        ("WEAK_TREND", 22.0),
        ("RANGING", 12.0),
    ],
)
async def test_handler_returns_the_regime_ta_computed(monkeypatch, ta_regime, adx):
    """The engine must report TA's label, and it must equal the old derivation.

    TA's vocabulary is wider than the engine's was: STRONG_TREND (ADX >= 30)
    has no consumer in `_calculate_enhanced_signal` or in
    `_get_risk_adjusted_signal`, so passing it through raw would silently drop
    every ADX >= 30 bar onto the neutral branch. It is mapped onto TRENDING,
    which is exactly what the deleted re-derivation produced for those bars.
    """
    result = await _drive_market_regime(
        monkeypatch, payload={"data": {"adx": adx, "regime": ta_regime}}
    )
    expected = _legacy_rederivation(adx)
    assert result["regime"] == expected, (
        f"TA said {ta_regime!r} at ADX {adx}; the engine used to derive "
        f"{expected!r}. Reading TA's label must not change the answer."
    )
    assert result["adx"] == adx
    # DEFER-21-05: these payloads carry no `confidence`, and the handler used to
    # answer 0.7 anyway. A constant reported where a measurement is expected is
    # indistinguishable downstream from a real one, which is the whole defect.
    assert "confidence" not in result, (
        f"technical-analysis sent no confidence, so the engine must report none; "
        f"it reported {result.get('confidence')!r}. Removing that fabricated "
        f"number is what DEFER-21-05 is"
    )


# ---------------------------------------------------------------------------
# DEFER-21-05 — report the confidence TA computed; absence stays absent
# ---------------------------------------------------------------------------


class _EnhancedSignalDouble:
    """The `base_signal.signal.*` shape `_calculate_enhanced_signal` reads.

    Production hands that function a bare `TradingSignal` (the aggregator's
    declared return type), which has NO `.signal` attribute — so the real call
    raises AttributeError on its first statement and the enhanced endpoint
    falls back to the basic signal. Verified 2026-08-28 and recorded as an
    out-of-scope finding by plan 22.1-05; repairing that wiring would turn a
    dead money-adjacent endpoint live and is deliberately not done here.

    This double supplies the shape the function is written against, which is
    the only way to exercise the arithmetic the omitted key must survive.
    """

    def __init__(self, action: str = "BUY", confidence: float = 0.6):
        self.signal = SimpleNamespace(
            action=SimpleNamespace(value=action),
            confidence=confidence,
            metadata={},
        )


async def test_handler_reports_the_confidence_ta_computed(monkeypatch):
    """The reported confidence must be TA's own, not a stand-in for it.

    Source of the number: technical-analysis
    `app/indicators/adx.py::ADXCalculator._calculate_confidence`, published as
    the `confidence` key of the same `/indicators/adx/{symbol}` response this
    handler already reads the regime label from. `signal_aggregator.fetch_adx`
    has been reading that key all along; this handler was not.
    """
    result = await _drive_market_regime(
        monkeypatch,
        payload={"data": {"adx": 27.0, "regime": "TRENDING", "confidence": 0.6}},
    )
    assert result["confidence"] == 0.6, (
        f"technical-analysis computed 0.6 and the engine reported "
        f"{result.get('confidence')!r}. 0.7 is the removed constant and 0.5 is "
        f"the degraded-path default — neither may stand in for a real value"
    )


@pytest.mark.parametrize(
    "bad_confidence",
    ["high", None, {}, [], float("nan"), float("inf")],
    ids=["string", "null", "dict", "list", "nan", "inf"],
)
async def test_a_malformed_confidence_is_omitted_not_propagated(
    monkeypatch, caplog, bad_confidence
):
    """T-22.1-05-01: an untrusted payload supplies a number that becomes a weight.

    `_calculate_enhanced_signal` multiplies this value by 0.15 without
    inspecting it. NaN and inf are in the grid on purpose: they coerce through
    `float()` cleanly and then poison every weight they touch, so "coercible"
    is not the same test as "usable".
    """
    from app.handlers import signals as signals_handler

    with caplog.at_level(logging.WARNING, logger=signals_handler.__name__):
        result = await _drive_market_regime(
            monkeypatch,
            payload={
                "data": {
                    "adx": 27.0,
                    "regime": "TRENDING",
                    "confidence": bad_confidence,
                }
            },
        )

    # Reaching here at all is half the assertion: nothing escaped the handler.
    assert "confidence" not in result, (
        f"{bad_confidence!r} reached the returned dict, where the enhanced-signal "
        f"risk leg would multiply it by 0.15"
    )
    assert result["regime"] == "TRENDING", (
        "a malformed confidence must not damage the regime read from the same "
        "payload"
    )
    assert result["adx"] == 27.0
    assert "BTCUSDT" in caplog.text, (
        f"a present-but-unusable confidence must log a warning naming the symbol "
        f"it came from; captured: {caplog.text!r}"
    )


async def test_an_absent_confidence_is_not_logged_as_malformed(monkeypatch, caplog):
    """Absence is TA's normal 'no measurement', not a defect worth a warning."""
    from app.handlers import signals as signals_handler

    with caplog.at_level(logging.WARNING, logger=signals_handler.__name__):
        result = await _drive_market_regime(
            monkeypatch, payload={"data": {"adx": 27.0, "regime": "TRENDING"}}
        )

    assert "confidence" not in result
    assert "confidence" not in caplog.text.lower(), (
        f"an absent key must not warn — every TA reply would log on every call "
        f"and the real malformed-value warning would be unfindable. Captured: "
        f"{caplog.text!r}"
    )


async def test_enhanced_signal_survives_an_omitted_regime_confidence(caplog):
    """T-22.1-05-02: why the key is OMITTED rather than returned as None.

    `_calculate_enhanced_signal` wraps its whole body in `except Exception` and
    returns the unmodified signal, so "nothing raised" is NOT evidence — a
    poisoned risk leg looks identical from the outside. The discriminating
    proof is that the arithmetic COMPLETED: the enhanced metadata block is
    written, and the risk leg carries the consumer's own declared 0.5 neutral.
    """
    from app.handlers import signals as signals_handler

    double = _EnhancedSignalDouble()
    with caplog.at_level(logging.ERROR, logger=signals_handler.__name__):
        result = await signals_handler._calculate_enhanced_signal(
            double,
            {"signal": "BUY", "confidence": 0.7},
            # No `confidence` key — exactly what the handler now returns when
            # technical-analysis supplies none.
            {"regime": "TRENDING", "adx": 27.0},
        )

    assert result.metadata.get("enhanced") is True, (
        "the enhanced block was never written, so the arithmetic degraded "
        "through the function's own `except Exception` — which is precisely "
        "what a present-None confidence causes"
    )
    assert result.metadata["individual_signals"]["risk_adjustment"]["confidence"] == 0.5, (
        "an omitted key must land on `market_regime.get('confidence', 0.5)`, "
        "the neutral the consumer declares for itself"
    )
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR], (
        f"the enhanced path logged an error: "
        f"{[r.getMessage() for r in caplog.records]}"
    )


async def test_a_present_none_confidence_would_have_degraded_the_enhanced_path(caplog):
    """The counter-case that makes the omission rule load-bearing, not stylistic.

    `dict.get(key, default)` returns None for a PRESENT null — the default
    never fires — and `None * 0.15` raises. Pinning this here is what stops a
    future edit from "tidying" the omission into the present-None convention
    `adx` uses two lines above it.
    """
    from app.handlers import signals as signals_handler

    double = _EnhancedSignalDouble()
    with caplog.at_level(logging.ERROR, logger=signals_handler.__name__):
        result = await signals_handler._calculate_enhanced_signal(
            double,
            {"signal": "BUY", "confidence": 0.7},
            {"regime": "TRENDING", "adx": 27.0, "confidence": None},
        )

    assert result.metadata.get("enhanced") is not True, (
        "a present None was expected to break the risk-leg multiply; if it no "
        "longer does, the reason DEFER-21-05 omits the key has changed and the "
        "comment at the site must be revisited"
    )
    assert [r for r in caplog.records if r.levelno >= logging.ERROR], (
        "the degradation must at least be logged"
    )


async def test_missing_regime_field_resolves_to_unknown(monkeypatch):
    """A response with no `regime` must not be classified at all."""
    result = await _drive_market_regime(monkeypatch, payload={"data": {}})
    assert result["regime"] == "UNKNOWN"


async def test_a_failed_adx_read_can_no_longer_masquerade_as_trending(monkeypatch):
    """T-21-07-02: the `.get("adx", 25)` default landed in the TRENDING branch.

    A missing ADX was replaced by 25, which satisfied `adx_value >= 25`, so an
    empty technical-analysis reply was reported as TRENDING at confidence 0.7 —
    indistinguishable downstream from a real measurement. Absence must stay
    absent.
    """
    result = await _drive_market_regime(monkeypatch, payload={"data": {}})
    assert result["regime"] != "TRENDING"
    assert result["adx"] != 25, (
        "a missing ADX must not be back-filled with a plausible number; it is "
        "reported to the API response and reads as a real measurement"
    )
    assert result["adx"] is None


async def test_regime_fetch_failure_does_not_fabricate_an_adx(monkeypatch):
    """The exception path fabricated the same 25. Same doctrine applies."""
    result = await _drive_market_regime(
        monkeypatch, raises=RuntimeError("technical-analysis unreachable")
    )
    assert result["regime"] == "UNKNOWN"
    assert result["adx"] is None
    assert "reason" in result


async def test_unmapped_ta_regime_label_fails_loud_not_silent(monkeypatch, caplog):
    """A label TA adds later must log, not fall through to the neutral branch."""
    from app.handlers import signals as signals_handler

    with caplog.at_level(logging.WARNING, logger=signals_handler.__name__):
        result = await _drive_market_regime(
            monkeypatch, payload={"data": {"adx": 40.0, "regime": "BLOW_OFF_TOP"}}
        )
    assert result["regime"] == "UNKNOWN"
    assert "BLOW_OFF_TOP" in caplog.text, (
        "an unmapped regime label must name itself in the log; otherwise the "
        "engine silently applies the neutral multiplier and nobody finds out"
    )


def test_engine_maps_every_regime_label_ta_can_emit():
    from app.handlers.signals import TA_REGIME_TO_ENGINE_REGIME

    missing = set(TA_REGIME_LABELS) - set(TA_REGIME_TO_ENGINE_REGIME)
    assert not missing, (
        f"technical-analysis can emit {sorted(missing)} and the engine has no "
        f"row for it — those bars would resolve to UNKNOWN and lose the regime "
        f"multiplier they used to get"
    )


class _FakeAsyncClient:
    """Minimal stand-in for the `async with httpx.AsyncClient()` in market_regime."""

    def __init__(self, captured, payload):
        self._captured = captured
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def get(self, url, params=None, **kwargs):
        self._captured["url"] = url
        self._captured["params"] = params
        response = MagicMock()
        response.status_code = 200
        response.json = MagicMock(return_value=self._payload)
        return response


async def test_market_regime_omits_the_adx_period_ta_settings_own(monkeypatch):
    """`period` must not ride along on the outbound ADX request.

    technical-analysis declares `default_adx_period` (14) and its
    `/indicators/adx` route resolves the query default from it, so sending an
    engine-side copy was a second declaration agreeing only by coincidence.
    `signal_aggregator.fetch_adx` already omits it — this is the same contract
    as `tests/test_engine_param_omission.py`, one layer down.
    """
    from app.aggregation import market_regime as mr

    captured = {}
    payload = {
        "success": True,
        "data": {
            "adx": 30.0,
            "plus_di": 25.0,
            "minus_di": 10.0,
            "regime": "STRONG_TREND",
            "direction": "BULLISH",
            "confidence": 0.8,
        },
    }
    monkeypatch.setattr(
        mr.httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(captured, payload)
    )

    detector = mr.MarketRegimeDetector(enabled=True)
    data = await detector._fetch_adx_data("BTCUSDT", "60")

    assert data is not None, "the fetch failed — the param assertion would be vacuous"
    params = captured.get("params") or {}
    assert "period" not in params, (
        f"market_regime sent 'period', which technical-analysis declares in its "
        f"Settings. Full captured params: {params}"
    )
    assert params.get("interval") == "60"


def test_market_regime_no_longer_accepts_a_dead_adx_period_argument():
    """A parameter that no longer reaches the request is worse than none.

    Leaving `adx_period` on the constructor after removing it from the request
    means a caller can set it, see no error, and get no effect — the exact
    silent-divergence shape P21-7 exists to remove.
    """
    import inspect

    from app.aggregation.market_regime import MarketRegimeDetector

    params = inspect.signature(MarketRegimeDetector.__init__).parameters
    assert "adx_period" not in params, (
        "adx_period no longer reaches the outbound request; accepting it would "
        "be an argument that silently does nothing"
    )
