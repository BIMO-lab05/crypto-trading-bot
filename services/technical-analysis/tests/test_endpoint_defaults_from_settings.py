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
