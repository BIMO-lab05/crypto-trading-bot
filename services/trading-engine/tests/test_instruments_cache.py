"""
Tests for ``app.services.instruments_cache.InstrumentsCache``.

Uses respx to mock the bybit-connector ``/api/v1/market/instruments-info``
endpoint. Validates:

* refresh() populates the cache for the requested symbols
* get() returns from cache when fresh, re-fetches on TTL expiry
* connector outage / non-2xx fail open (return None / log WARN)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
import respx

from app.services.instruments_cache import (
    InstrumentSpec,
    InstrumentsCache,
    _parse_instrument,
    reset_instruments_cache,
)


CONNECTOR_URL = "http://bybit-connector:8001"


def _btc_item(min_qty="0.001", qty_step="0.001", tick="0.10", min_notional="5"):
    """Bybit-shaped instruments-info item for BTCUSDT (linear)."""
    item = {
        "symbol": "BTCUSDT",
        "contractType": "LinearPerpetual",
        "lotSizeFilter": {
            "minOrderQty": min_qty,
            "qtyStep": qty_step,
            "maxOrderQty": "100.000",
        },
        "priceFilter": {"tickSize": tick},
    }
    if min_notional is not None:
        item["lotSizeFilter"]["minNotionalValue"] = min_notional
    return item


def _eth_item(min_qty="0.01", qty_step="0.01", tick="0.05"):
    """ETH item without minNotionalValue (some perps omit it)."""
    return {
        "symbol": "ETHUSDT",
        "contractType": "LinearPerpetual",
        "lotSizeFilter": {
            "minOrderQty": min_qty,
            "qtyStep": qty_step,
            "maxOrderQty": "1000.00",
        },
        "priceFilter": {"tickSize": tick},
    }


def _payload(items):
    return {"success": True, "data": items}


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_instruments_cache()
    yield
    reset_instruments_cache()


# ---------------------------------------------------------------- _parse_instrument


def test_parse_instrument_full():
    spec = _parse_instrument(_btc_item())
    assert spec is not None
    assert spec.symbol == "BTCUSDT"
    assert spec.min_order_qty == Decimal("0.001")
    assert spec.qty_step == Decimal("0.001")
    assert spec.tick_size == Decimal("0.10")
    assert spec.min_notional == Decimal("5")


def test_parse_instrument_missing_min_notional_is_none():
    spec = _parse_instrument(_eth_item())
    assert spec is not None
    assert spec.min_notional is None


def test_parse_instrument_empty_min_notional_string_is_none():
    spec = _parse_instrument(_btc_item(min_notional=""))
    assert spec is not None
    assert spec.min_notional is None


def test_parse_instrument_missing_required_returns_none():
    bad = {"symbol": "FOO", "lotSizeFilter": {}, "priceFilter": {}}
    assert _parse_instrument(bad) is None


# ---------------------------------------------------------------- refresh


@pytest.mark.asyncio
@respx.mock
async def test_refresh_populates_cache():
    cache = InstrumentsCache(connector_url=CONNECTOR_URL)

    route = respx.get(f"{CONNECTOR_URL}/api/v1/market/instruments-info").mock(
        return_value=httpx.Response(200, json=_payload([_btc_item(), _eth_item()]))
    )

    await cache.refresh(["BTCUSDT", "ETHUSDT"])

    assert route.called
    btc = await cache.get("BTCUSDT")
    eth = await cache.get("ETHUSDT")
    assert btc is not None and btc.min_order_qty == Decimal("0.001")
    assert eth is not None and eth.min_notional is None


@pytest.mark.asyncio
@respx.mock
async def test_refresh_filters_to_requested_symbols():
    """Cache should only retain symbols the caller asked about."""
    cache = InstrumentsCache(connector_url=CONNECTOR_URL)

    respx.get(f"{CONNECTOR_URL}/api/v1/market/instruments-info").mock(
        return_value=httpx.Response(
            200,
            json=_payload(
                [
                    _btc_item(),
                    _eth_item(),
                    {  # noise: not requested
                        "symbol": "DOGEUSDT",
                        "lotSizeFilter": {"minOrderQty": "1", "qtyStep": "1"},
                        "priceFilter": {"tickSize": "0.0001"},
                    },
                ]
            ),
        )
    )

    await cache.refresh(["BTCUSDT"])
    assert cache._cache.keys() == {"BTCUSDT"}


# ---------------------------------------------------------------- TTL


@pytest.mark.asyncio
@respx.mock
async def test_get_uses_cache_when_fresh():
    cache = InstrumentsCache(connector_url=CONNECTOR_URL, ttl_seconds=3600)

    route = respx.get(f"{CONNECTOR_URL}/api/v1/market/instruments-info").mock(
        return_value=httpx.Response(200, json=_payload([_btc_item()]))
    )

    await cache.refresh(["BTCUSDT"])
    assert route.call_count == 1

    # Hot read — no second call.
    await cache.get("BTCUSDT")
    await cache.get("BTCUSDT")
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_get_refetches_on_ttl_expiry():
    cache = InstrumentsCache(connector_url=CONNECTOR_URL, ttl_seconds=3600)

    route = respx.get(f"{CONNECTOR_URL}/api/v1/market/instruments-info").mock(
        side_effect=[
            httpx.Response(200, json=_payload([_btc_item(min_qty="0.001")])),
            httpx.Response(200, json=_payload([_btc_item(min_qty="0.002")])),
        ]
    )

    await cache.refresh(["BTCUSDT"])
    first = await cache.get("BTCUSDT")
    assert first.min_order_qty == Decimal("0.001")

    # Force expiry by rewinding fetched_at.
    stale = first  # frozen dataclass; replace via _cache directly
    expired = InstrumentSpec(
        symbol=stale.symbol,
        min_order_qty=stale.min_order_qty,
        qty_step=stale.qty_step,
        tick_size=stale.tick_size,
        min_notional=stale.min_notional,
        fetched_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    cache._cache["BTCUSDT"] = expired

    second = await cache.get("BTCUSDT")
    assert second.min_order_qty == Decimal("0.002")
    assert route.call_count == 2


# ---------------------------------------------------------------- fail-open


@pytest.mark.asyncio
@respx.mock
async def test_refresh_fails_open_on_connector_500():
    cache = InstrumentsCache(connector_url=CONNECTOR_URL)

    respx.get(f"{CONNECTOR_URL}/api/v1/market/instruments-info").mock(
        return_value=httpx.Response(500, text="boom")
    )

    # Must not raise. Cache stays empty.
    await cache.refresh(["BTCUSDT"])
    assert cache._cache == {}
    assert (await cache.get("BTCUSDT")) is None


@pytest.mark.asyncio
@respx.mock
async def test_refresh_fails_open_on_connect_error():
    cache = InstrumentsCache(connector_url=CONNECTOR_URL)

    respx.get(f"{CONNECTOR_URL}/api/v1/market/instruments-info").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    await cache.refresh(["BTCUSDT"])
    assert cache._cache == {}


@pytest.mark.asyncio
@respx.mock
async def test_get_unknown_symbol_returns_none():
    cache = InstrumentsCache(connector_url=CONNECTOR_URL)

    respx.get(f"{CONNECTOR_URL}/api/v1/market/instruments-info").mock(
        return_value=httpx.Response(200, json=_payload([]))
    )

    assert (await cache.get("ZZZUSDT")) is None
