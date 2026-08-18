"""
Route defaults must come from Settings, not from duplicated literals.

The trading-engine calls /api/v1/indicators/macd with NO fast/slow/signal
params on purpose, treating this service's endpoint defaults as the single
source of truth (signal_aggregator.py:117-122). While main.py hardcodes
5/35/5, an operator's DEFAULT_MACD_FAST reaches the /analyze path but not the
endpoint the engine calls - the two disagree silently.
"""

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.config import get_settings
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
