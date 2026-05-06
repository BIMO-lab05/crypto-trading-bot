"""
Instruments cache — pre-submit min-notional / min-qty gate.

Pulls per-symbol exchange filters (lotSizeFilter.minOrderQty / qtyStep /
minNotionalValue, priceFilter.tickSize) from the bybit-connector's
``/api/v1/market/instruments-info`` endpoint and caches them with a 1-hour
TTL. Used by ``auto_trader._passes_min_notional()`` to reject orders that
would be auto-rejected by Bybit in LIVE mode.

Design notes
============
* **Fail-open on connector outage.** If the connector is unreachable, ``get()``
  returns ``None`` and the gate becomes a no-op for that symbol. Refusing to
  trade because the metadata service is down would be a worse failure mode
  than letting an order through (paper engine fills any quantity; LIVE mode
  would just see Bybit's own min-notional rejection which is already loud).
* **No auto-upround.** This module *only* surfaces the spec. The decision to
  reject vs round-up lives in ``auto_trader``, which rejects — auto-uprounding
  silently breaches the 2% per-trade cap (e.g. on a $100 balance, a $5 alt
  min-notional would force 5% notional).
* **Single source of exchange metadata.** Calls go through bybit-connector
  rather than directly to Bybit, matching the architecture rule that the
  connector owns all exchange I/O.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


DEFAULT_TTL_SECONDS = 3600  # 1 hour
DEFAULT_HTTP_TIMEOUT = 10.0


@dataclass(frozen=True)
class InstrumentSpec:
    """Snapshot of exchange filters for a single perp symbol."""

    symbol: str
    min_order_qty: Decimal
    qty_step: Decimal
    tick_size: Decimal
    fetched_at: datetime
    min_notional: Optional[Decimal] = None


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Bybit returns numeric filters as strings; coerce safely."""
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _parse_instrument(item: Dict[str, Any]) -> Optional[InstrumentSpec]:
    """Convert a raw Bybit instruments-info item into an ``InstrumentSpec``.

    Returns ``None`` when required fields are missing or unparseable — the
    caller treats that as a cache miss (gate becomes no-op for the symbol).
    """
    symbol = item.get("symbol")
    lot_filter = item.get("lotSizeFilter") or {}
    price_filter = item.get("priceFilter") or {}

    if not symbol:
        return None

    min_order_qty = _to_decimal(lot_filter.get("minOrderQty"))
    qty_step = _to_decimal(lot_filter.get("qtyStep"))
    tick_size = _to_decimal(price_filter.get("tickSize"))

    if min_order_qty is None or qty_step is None or tick_size is None:
        # Required fields missing — refuse to construct a partial spec.
        return None

    # minNotionalValue is optional on Bybit perps (present on some symbols,
    # absent on others). An empty string also counts as absent.
    min_notional_raw = lot_filter.get("minNotionalValue")
    min_notional = (
        _to_decimal(min_notional_raw) if min_notional_raw not in (None, "") else None
    )

    return InstrumentSpec(
        symbol=str(symbol),
        min_order_qty=min_order_qty,
        qty_step=qty_step,
        tick_size=tick_size,
        min_notional=min_notional,
        fetched_at=datetime.now(timezone.utc),
    )


class InstrumentsCache:
    """Async TTL cache of per-symbol Bybit instrument filters."""

    def __init__(
        self,
        connector_url: Optional[str] = None,
        category: str = "linear",
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        http_timeout: float = DEFAULT_HTTP_TIMEOUT,
    ) -> None:
        settings = get_settings()
        self._connector_url = (connector_url or settings.bybit_connector_url).rstrip(
            "/"
        )
        self._category = category
        self._ttl = timedelta(seconds=ttl_seconds)
        self._http_timeout = http_timeout
        self._cache: Dict[str, InstrumentSpec] = {}

    # ------------------------------------------------------------------ HTTP

    async def _fetch(self, symbol: Optional[str]) -> List[Dict[str, Any]]:
        """Hit the connector and return the raw ``data`` list.

        Raises ``httpx.HTTPError`` (or subclasses) — the calling refresh/get
        path catches and converts to a fail-open WARN.
        """
        url = f"{self._connector_url}/api/v1/market/instruments-info"
        params: Dict[str, str] = {"category": self._category}
        if symbol:
            params["symbol"] = symbol

        async with httpx.AsyncClient(timeout=self._http_timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()

        if not isinstance(payload, dict) or not payload.get("success"):
            logger.warning(
                "instruments-info responded without success=true: %s", payload
            )
            return []
        data = payload.get("data") or []
        if not isinstance(data, list):
            return []
        return data

    # ------------------------------------------------------------------ public

    async def refresh(self, symbols: List[str]) -> None:
        """Fetch and cache filters for ``symbols``.

        Fail-open: a connector outage logs WARN, leaves any existing cache
        entries in place, and does not raise.
        """
        if not symbols:
            return

        try:
            # Single bulk call (no symbol filter) is cheapest — Bybit returns
            # ~500 perps which is fine to filter client-side. If the connector
            # is hot-restarted with a wrong category etc. we still capture
            # whatever we can.
            items = await self._fetch(symbol=None)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "InstrumentsCache.refresh(%s) failed (%s) — gate fails open",
                symbols,
                exc,
            )
            return

        wanted = set(symbols)
        loaded = 0
        for raw in items:
            sym = raw.get("symbol")
            if sym not in wanted:
                continue
            spec = _parse_instrument(raw)
            if spec is None:
                logger.debug("Could not parse instrument spec for %s: %s", sym, raw)
                continue
            self._cache[spec.symbol] = spec
            loaded += 1

        logger.info(
            "InstrumentsCache: refreshed %d/%d symbols (category=%s)",
            loaded,
            len(symbols),
            self._category,
        )

    async def get(self, symbol: str) -> Optional[InstrumentSpec]:
        """Return cached spec for ``symbol``, refreshing on TTL expiry.

        Returns ``None`` on connector outage or if the symbol is not listed
        — caller treats as fail-open (no gate).
        """
        spec = self._cache.get(symbol)
        if (
            spec is not None
            and (datetime.now(timezone.utc) - spec.fetched_at) < self._ttl
        ):
            return spec

        # Either missing or stale — re-fetch.
        try:
            items = await self._fetch(symbol=symbol)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "InstrumentsCache.get(%s) refetch failed (%s) — returning stale=%s",
                symbol,
                exc,
                spec is not None,
            )
            # Return stale entry rather than nothing if available; better than
            # losing the gate entirely on transient connector blips.
            return spec

        for raw in items:
            if raw.get("symbol") != symbol:
                continue
            fresh = _parse_instrument(raw)
            if fresh is None:
                logger.debug("Could not parse instrument spec for %s", symbol)
                return spec
            self._cache[symbol] = fresh
            return fresh

        # Symbol not present in connector response.
        logger.debug(
            "InstrumentsCache.get(%s): symbol not in connector response", symbol
        )
        return spec  # may be None

    def clear(self) -> None:
        """Drop all cached entries (test helper)."""
        self._cache.clear()


# ---------------------------------------------------------------- singleton

_instruments_cache: Optional[InstrumentsCache] = None


def get_instruments_cache() -> InstrumentsCache:
    """Module-level singleton accessor (matches the project's other accessors)."""
    global _instruments_cache
    if _instruments_cache is None:
        _instruments_cache = InstrumentsCache()
    return _instruments_cache


def reset_instruments_cache() -> None:
    """Reset the singleton (test helper)."""
    global _instruments_cache
    _instruments_cache = None
