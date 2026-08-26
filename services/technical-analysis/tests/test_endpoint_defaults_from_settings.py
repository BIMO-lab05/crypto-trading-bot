"""
Route defaults must come from Settings, not from duplicated literals.

The trading-engine calls /api/v1/indicators/macd with NO fast/slow/signal
params on purpose, treating this service's endpoint defaults as the single
source of truth (signal_aggregator.py:117-122). Until 2026-08-20 an
operator's DEFAULT_MACD_FAST reached the /analysis path but not the
endpoints - the two disagreed silently. Now BOTH layers (main.py routes and
the handler Query() signatures they delegate to) read Settings; the
parametrized tests below pin every wired param in both layers so drift in
either one fails loudly.
"""

import inspect
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.handlers import advanced as advanced_handlers
from app.handlers import indicators as indicator_handlers
from app.main import app

client = TestClient(app, raise_server_exceptions=False)
settings = get_settings()


def test_macd_route_defaults_come_from_settings():
    payload = {
        "timestamp": 1234567890000,
        "macd_line": 1.0,
        "signal_line": 0.5,
        "histogram": 0.5,
        "signal": "BUY",
        "confidence": 0.7,
    }
    with patch("app.handlers.indicators.IndicatorService") as mock_service:
        mock_service.calculate_macd = AsyncMock(return_value=payload)

        response = client.get("/api/v1/indicators/macd/BTCUSDT")

        assert response.status_code == 200, response.text
        kwargs = mock_service.calculate_macd.call_args.kwargs
        args = mock_service.calculate_macd.call_args.args
        received = (
            kwargs
            if kwargs
            else dict(
                zip(("symbol", "interval", "fast", "slow", "signal", "limit"), args)
            )
        )
        assert received["fast"] == settings.default_macd_fast
        assert received["slow"] == settings.default_macd_slow
        assert received["signal"] == settings.default_macd_signal


def test_bollinger_route_defaults_come_from_settings():
    payload = {
        "timestamp": 1234567890000,
        "upper_band": 2.0,
        "middle_band": 1.0,
        "lower_band": 0.5,
        "current_price": 1.0,
        "bandwidth": 1.5,
        "percent_b": 0.5,
        "signal": "HOLD",
        "confidence": 0.5,
    }
    with patch("app.handlers.indicators.IndicatorService") as mock_service:
        mock_service.calculate_bollinger_bands = AsyncMock(return_value=payload)

        response = client.get("/api/v1/indicators/bollinger/BTCUSDT")

        assert response.status_code == 200, response.text
        kwargs = mock_service.calculate_bollinger_bands.call_args.kwargs
        args = mock_service.calculate_bollinger_bands.call_args.args
        received = (
            kwargs
            if kwargs
            else dict(zip(("symbol", "interval", "period", "std_dev", "limit"), args))
        )
        assert received["period"] == settings.default_bb_period
        assert received["std_dev"] == settings.default_bb_std


def test_openapi_schema_defaults_track_settings():
    """The literal is gone from the schema, not merely shadowed at runtime."""
    schema = client.get("/openapi.json").json()
    macd_params = {
        p["name"]: p
        for p in schema["paths"]["/api/v1/indicators/macd/{symbol}"]["get"][
            "parameters"
        ]
    }
    assert macd_params["fast"]["schema"]["default"] == settings.default_macd_fast
    assert macd_params["slow"]["schema"]["default"] == settings.default_macd_slow


def test_rsi_bounds_and_description_survive_the_settings_rewire():
    """Only default= may move. ge/le and description are a live contract.

    Narrowing RSI's le from 200 to 100 turns ?period=150 from HTTP 200 into
    HTTP 422, and dropping description= rewrites the published OpenAPI schema.
    Neither is caught by the two route-default tests above, so pin them here.
    """
    schema = client.get("/openapi.json").json()
    rsi_params = {
        p["name"]: p
        for p in schema["paths"]["/api/v1/indicators/rsi/{symbol}"]["get"]["parameters"]
    }
    period = rsi_params["period"]["schema"]

    assert period["default"] == settings.default_rsi_period
    assert period["minimum"] == 2, f"RSI ge moved: {period}"
    assert period["maximum"] == 200, (
        f"RSI le narrowed to {period.get('maximum')} - it is 200; 100 is the "
        "Bollinger endpoint's bound"
    )
    assert period["description"] == "RSI period (optimized for crypto)", (
        f"RSI description changed: {period.get('description')!r}"
    )


# ---------------------------------------------------------------------------
# Full coverage of the 2026-08-20 Settings rewire.
# (route path, query param, Settings field) - one row per wired default.
# ---------------------------------------------------------------------------
WIRED_ROUTE_DEFAULTS = [
    ("/api/v1/indicators/rsi/{symbol}", "period", "default_rsi_period"),
    ("/api/v1/indicators/macd/{symbol}", "fast", "default_macd_fast"),
    ("/api/v1/indicators/macd/{symbol}", "slow", "default_macd_slow"),
    ("/api/v1/indicators/macd/{symbol}", "signal", "default_macd_signal"),
    ("/api/v1/indicators/bollinger/{symbol}", "period", "default_bb_period"),
    ("/api/v1/indicators/bollinger/{symbol}", "std_dev", "default_bb_std"),
    ("/api/v1/indicators/sma/{symbol}", "period", "default_sma_period"),
    ("/api/v1/indicators/ema/{symbol}", "period", "default_ema_period"),
    ("/api/v1/indicators/trend/{symbol}", "fast_period", "default_trend_fast_period"),
    ("/api/v1/indicators/trend/{symbol}", "slow_period", "default_trend_slow_period"),
    ("/api/v1/indicators/trend/{symbol}", "limit", "default_trend_limit"),
    ("/api/v1/indicators/volume/{symbol}", "period", "default_volume_period"),
    ("/api/v1/indicators/volume/{symbol}", "signal_type", "default_volume_signal_type"),
    ("/api/v1/indicators/volume/{symbol}", "limit", "default_volume_limit"),
    ("/api/v1/indicators/atr/{symbol}", "period", "default_atr_period"),
    ("/api/v1/indicators/adx/{symbol}", "period", "default_adx_period"),
    (
        "/api/v1/indicators/adx/{symbol}",
        "trending_threshold",
        "default_adx_trending_threshold",
    ),
    (
        "/api/v1/indicators/adx/{symbol}",
        "weak_trend_threshold",
        "default_adx_weak_trend_threshold",
    ),
    (
        "/api/v1/indicators/adx/{symbol}",
        "strong_trend_threshold",
        "default_adx_strong_trend_threshold",
    ),
    ("/api/v1/indicators/stochastic/{symbol}", "period", "default_stochastic_period"),
    (
        "/api/v1/indicators/stochastic/{symbol}",
        "smooth_k",
        "default_stochastic_smooth_k",
    ),
    (
        "/api/v1/indicators/stochastic/{symbol}",
        "smooth_d",
        "default_stochastic_smooth_d",
    ),
    (
        "/api/v1/indicators/rsi-divergence/{symbol}",
        "period",
        "default_rsi_divergence_period",
    ),
    (
        "/api/v1/indicators/rsi-divergence/{symbol}",
        "lookback",
        "default_rsi_divergence_lookback",
    ),
    (
        "/api/v1/indicators/ichimoku/{symbol}",
        "tenkan_period",
        "default_ichimoku_tenkan",
    ),
    ("/api/v1/indicators/ichimoku/{symbol}", "kijun_period", "default_ichimoku_kijun"),
    (
        "/api/v1/indicators/ichimoku/{symbol}",
        "senkou_b_period",
        "default_ichimoku_senkou_b",
    ),
    (
        "/api/v1/indicators/sqzmom-enhanced/{symbol}",
        "bb_period",
        "default_sqzmom_bb_period",
    ),
    ("/api/v1/indicators/sqzmom-enhanced/{symbol}", "bb_mult", "default_sqzmom_bb_mult"),
    (
        "/api/v1/indicators/sqzmom-enhanced/{symbol}",
        "kc_period",
        "default_sqzmom_kc_period",
    ),
    ("/api/v1/indicators/sqzmom-enhanced/{symbol}", "kc_mult", "default_sqzmom_kc_mult"),
    (
        "/api/v1/indicators/sqzmom-enhanced/{symbol}",
        "mom_period",
        "default_sqzmom_mom_period",
    ),
]


@pytest.fixture(scope="module")
def openapi_schema():
    return client.get("/openapi.json").json()


@pytest.mark.parametrize("path,param,field", WIRED_ROUTE_DEFAULTS)
def test_route_schema_default_tracks_settings(openapi_schema, path, param, field):
    """main.py route layer: the published OpenAPI default IS the Settings value."""
    params = {
        p["name"]: p for p in openapi_schema["paths"][path]["get"]["parameters"]
    }
    assert params[param]["schema"]["default"] == getattr(settings, field), (
        f"{path} ?{param} default drifted from settings.{field}"
    )


# Handler layer: main.py routes pass values explicitly, so handler Query()
# defaults never surface over HTTP - but they are the defaults for any direct
# caller and must not drift back to literals either.
WIRED_HANDLER_DEFAULTS = [
    (indicator_handlers.get_rsi, "period", "default_rsi_period"),
    (indicator_handlers.get_macd, "fast", "default_macd_fast"),
    (indicator_handlers.get_macd, "slow", "default_macd_slow"),
    (indicator_handlers.get_macd, "signal", "default_macd_signal"),
    (indicator_handlers.get_bollinger_bands, "period", "default_bb_period"),
    (indicator_handlers.get_bollinger_bands, "std_dev", "default_bb_std"),
    (indicator_handlers.get_sma, "period", "default_sma_period"),
    (indicator_handlers.get_ema, "period", "default_ema_period"),
    (advanced_handlers.get_trend_filter, "fast_period", "default_trend_fast_period"),
    (advanced_handlers.get_trend_filter, "slow_period", "default_trend_slow_period"),
    (advanced_handlers.get_trend_filter, "limit", "default_trend_limit"),
    (advanced_handlers.get_volume_confirmation, "period", "default_volume_period"),
    (
        advanced_handlers.get_volume_confirmation,
        "signal_type",
        "default_volume_signal_type",
    ),
    (advanced_handlers.get_volume_confirmation, "limit", "default_volume_limit"),
    (advanced_handlers.get_atr, "period", "default_atr_period"),
    (advanced_handlers.get_adx, "period", "default_adx_period"),
    (
        advanced_handlers.get_adx,
        "trending_threshold",
        "default_adx_trending_threshold",
    ),
    (
        advanced_handlers.get_adx,
        "weak_trend_threshold",
        "default_adx_weak_trend_threshold",
    ),
    (
        advanced_handlers.get_adx,
        "strong_trend_threshold",
        "default_adx_strong_trend_threshold",
    ),
    (advanced_handlers.get_stochastic, "period", "default_stochastic_period"),
    (advanced_handlers.get_stochastic, "smooth_k", "default_stochastic_smooth_k"),
    (advanced_handlers.get_stochastic, "smooth_d", "default_stochastic_smooth_d"),
    (advanced_handlers.get_rsi_divergence, "period", "default_rsi_divergence_period"),
    (
        advanced_handlers.get_rsi_divergence,
        "lookback",
        "default_rsi_divergence_lookback",
    ),
    (advanced_handlers.get_ichimoku, "tenkan_period", "default_ichimoku_tenkan"),
    (advanced_handlers.get_ichimoku, "kijun_period", "default_ichimoku_kijun"),
    (advanced_handlers.get_ichimoku, "senkou_b_period", "default_ichimoku_senkou_b"),
    (advanced_handlers.get_enhanced_sqzmom, "bb_period", "default_sqzmom_bb_period"),
    (advanced_handlers.get_enhanced_sqzmom, "bb_mult", "default_sqzmom_bb_mult"),
    (advanced_handlers.get_enhanced_sqzmom, "kc_period", "default_sqzmom_kc_period"),
    (advanced_handlers.get_enhanced_sqzmom, "kc_mult", "default_sqzmom_kc_mult"),
    (advanced_handlers.get_enhanced_sqzmom, "mom_period", "default_sqzmom_mom_period"),
]


@pytest.mark.parametrize(
    "func,param,field",
    WIRED_HANDLER_DEFAULTS,
    ids=[f"{f.__name__}-{p}" for f, p, _ in WIRED_HANDLER_DEFAULTS],
)
def test_handler_query_default_tracks_settings(func, param, field):
    query_obj = inspect.signature(func).parameters[param].default
    assert query_obj.default == getattr(settings, field), (
        f"{func.__name__}({param}=...) default drifted from settings.{field}"
    )


# ---------------------------------------------------------------------------
# Phase 21 P21-4/P21-5: the canonical values moved into Settings (SMA/EMA 21,
# Ichimoku 20/60/120) and the engine stopped sending them.
#
# The WIRED_* tables above assert `== getattr(settings, field)`, so the value
# change is already covered. What they cannot see is (a) whether a route's
# prose still advertises the OLD number, and (b) whether a bound moved while
# the default did. Both are added here.
# ---------------------------------------------------------------------------

# (route path, query param, Settings field) - the params whose description
# states its own default in prose. Description and default must not disagree:
# main.py advertised "crypto optimized: 20/60/120" for over a year while the
# defaults resolved to 9/26/52.
DESCRIBED_DEFAULTS = [
    (
        "/api/v1/indicators/ichimoku/{symbol}",
        "tenkan_period",
        "default_ichimoku_tenkan",
    ),
    ("/api/v1/indicators/ichimoku/{symbol}", "kijun_period", "default_ichimoku_kijun"),
    (
        "/api/v1/indicators/ichimoku/{symbol}",
        "senkou_b_period",
        "default_ichimoku_senkou_b",
    ),
]


@pytest.mark.parametrize("path,param,field", DESCRIBED_DEFAULTS)
def test_route_description_states_the_resolved_default(
    openapi_schema, path, param, field
):
    """A param whose description names a number must name the resolved one."""
    import re

    params = {p["name"]: p for p in openapi_schema["paths"][path]["get"]["parameters"]}
    schema = params[param]["schema"]
    description = params[param].get("description", "")
    expected = getattr(settings, field)

    assert schema["default"] == expected, (
        f"{path} ?{param} default drifted from settings.{field}"
    )

    stated = re.findall(r"\d+", description)
    assert stated, (
        f"{path} ?{param} description states no number to check: {description!r}"
    )
    assert str(expected) in stated, (
        f"{path} ?{param} description says {stated} but the default resolves to "
        f"{expected}. Description and default must agree - a description naming "
        f"a number the endpoint does not use is how 9/26/52 shipped while the "
        f"prose claimed 20/60/120. Description: {description!r}"
    )


# (route path, query param, expected ge, expected le) - bounds are a live
# contract exactly as in the RSI test above: narrowing one turns a
# previously-valid request into an HTTP 422. Only `default=` was allowed to
# move in P21-4/P21-5.
PRESERVED_BOUNDS = [
    ("/api/v1/indicators/sma/{symbol}", "period", 2, 200),
    ("/api/v1/indicators/ema/{symbol}", "period", 2, 200),
    ("/api/v1/indicators/ichimoku/{symbol}", "tenkan_period", 5, 30),
    ("/api/v1/indicators/ichimoku/{symbol}", "kijun_period", 20, 120),
    ("/api/v1/indicators/ichimoku/{symbol}", "senkou_b_period", 40, 200),
]


@pytest.mark.parametrize("path,param,minimum,maximum", PRESERVED_BOUNDS)
def test_bounds_survive_the_canonical_value_move(
    openapi_schema, path, param, minimum, maximum
):
    """SMA/EMA/Ichimoku bounds are unchanged by the Settings canon move."""
    params = {p["name"]: p for p in openapi_schema["paths"][path]["get"]["parameters"]}
    schema = params[param]["schema"]

    assert schema["minimum"] == minimum, (
        f"{path} ?{param} ge moved to {schema.get('minimum')} (expected {minimum})"
    )
    assert schema["maximum"] == maximum, (
        f"{path} ?{param} le moved to {schema.get('maximum')} (expected {maximum})"
    )
    # The new default must still be reachable through the untouched bounds.
    assert minimum <= schema["default"] <= maximum, (
        f"{path} ?{param} default {schema['default']} is outside its own "
        f"[{minimum}, {maximum}] bounds - every bare request would 422"
    )


def test_aggregate_limit_below_warmup_floor_is_rejected():
    """The aggregate window must clear the slowest indicator's warm-up.

    Under-feeding is silent by construction: IchimokuCalculator.calculate()
    returns None below min_periods and TrendFilter's 200-EMA simply reads a
    shorter history, so a too-small limit degrades signals without erroring.
    The floor is derived from the period fields, never hardcoded.

    `_env_file=None` pins this to the declared defaults - the TA Settings
    read `.env` relative to cwd, and a stray operator file under
    services/technical-analysis/ would otherwise poison the assertion.
    """
    from pydantic import ValidationError

    from app.config import Settings

    # 150 clears the field's own ge=100, so this exercises the cross-field
    # model validator rather than the bound (which would pass vacuously).
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, default_aggregate_limit=150)

    message = str(exc.value)
    assert "warm-up floor" in message, message
    # Both contributing floors must be named so the operator knows which
    # period to move.
    assert "default_trend_slow_period" in message, message
    assert "Ichimoku" in message, message
    assert "150" in message, message


def test_declared_aggregate_limit_clears_its_own_floor():
    """The shipped default must satisfy the validator it declares."""
    from app.config import (
        ICHIMOKU_CONSTRUCTOR_DEFAULT_DISPLACEMENT,
        ICHIMOKU_KUMO_BREAKOUT_LOOKBACK,
    )

    displacement = max(
        settings.default_ichimoku_kijun, ICHIMOKU_CONSTRUCTOR_DEFAULT_DISPLACEMENT
    )
    ichimoku_floor = (
        settings.default_ichimoku_senkou_b
        + displacement
        + ICHIMOKU_KUMO_BREAKOUT_LOOKBACK
    )
    floor = max(settings.default_trend_slow_period, ichimoku_floor)

    assert settings.default_aggregate_limit >= floor, (
        f"default_aggregate_limit={settings.default_aggregate_limit} is below "
        f"its own derived floor {floor}"
    )
