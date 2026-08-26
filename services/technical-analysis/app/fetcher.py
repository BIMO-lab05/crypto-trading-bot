"""
Technical Analysis Service - Market Data Fetcher
Purpose: Fetch kline data from Market Data Service
"""

import asyncio
import httpx
import logging
import time
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from fastapi import HTTPException

from app.config import get_settings
from app.models import Kline

logger = logging.getLogger(__name__)

# Market-data stores daily/weekly/monthly candles under Bybit's letter
# intervals ("D"/"W"/"M"), never under their minute equivalents. Callers
# (multi-timeframe, strategy configs) sometimes pass minutes — normalize
# before querying or the DB lookup silently returns 0 rows.
_INTERVAL_ALIASES = {
    "1440": "D",  # daily
    "10080": "W",  # weekly
    "43200": "M",  # monthly (approximate)
}

# Max absolute log-return per bar; anything above is treated as corrupt data
# (testnet pollution, bad prints). 0.35 ≈ 42% up / 30% down in one bar.
MAX_ABS_LOG_RETURN = 0.35

# Minimum number of validated candles needed for meaningful TA output.
MIN_VALID_ROWS = 30

# Valid Bybit V5 kline intervals (post-normalization). Mirrors market-data's
# VALID_INTERVALS; agreement pinned by tests/test_interval_validation.py.
VALID_INTERVALS = frozenset(
    {"1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"}
)


def normalize_interval(interval: str) -> str:
    """Map minute-denominated aliases (1440/10080/43200) to D/W/M."""
    return _INTERVAL_ALIASES.get(str(interval), str(interval))


def _interval_ms(interval: str) -> int:
    """Interval duration in milliseconds (for still-forming candle check)."""
    interval = normalize_interval(interval)
    if interval.isdigit():
        minutes = int(interval)
    else:
        minutes = {"D": 1440, "W": 10080, "M": 43200}.get(interval.upper(), 60)
    return minutes * 60 * 1000


class MarketDataFetcher:
    """Fetches market data from Market Data Service"""

    def __init__(self):
        """Initialize fetcher with Market Data Service URL"""
        self.settings = get_settings()
        self.base_url = self.settings.market_data_url
        self.client = httpx.AsyncClient(timeout=30.0)
        # (symbol, interval, limit) -> (monotonic expiry, klines). One signal
        # cycle asks ~12 indicator endpoints for the same candle window;
        # without this each ask is its own market-data -> TimescaleDB query,
        # and the 2026-08-12 auto-trader resume stampede drove the DB to
        # 173% CPU and client-timeout bursts. The per-key lock makes the
        # refresh single-flight — a burst of identical requests costs one
        # upstream query, not twelve. TTL is far under the collector's
        # 5-minute cadence, so a cached window is never staler than the DB.
        self._kline_cache: Dict[Tuple[str, str, int], Tuple[float, List[Kline]]] = {}
        self._kline_locks: Dict[Tuple[str, str, int], asyncio.Lock] = {}
        logger.info(f"MarketDataFetcher initialized with base_url: {self.base_url}")

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
        logger.info("MarketDataFetcher closed")

    async def health_check(self) -> bool:
        """
        Check if Market Data Service is healthy

        Returns:
            True if healthy, False otherwise
        """
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception as e:
            # exc_info deliberately omitted: the health probe fires
            # frequently and {e!r} suffices.
            logger.error(f"Health check failed: {e!r}")
            return False

    async def get_klines(
        self, symbol: str, interval: str = "60", limit: int = 200
    ) -> List[Kline]:
        """
        Fetch kline data for analysis, TTL-cached and single-flight per
        (symbol, interval, limit). Set kline_cache_ttl_seconds <= 0 to bypass.

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Candlestick interval (default: 60 = 1 hour)
            limit: Number of candles to fetch

        Returns:
            List of Kline objects sorted by timestamp ascending

        Raises:
            Exception if fetch fails
        """
        interval = normalize_interval(interval)
        if interval not in VALID_INTERVALS:
            # Client error, not a computation failure: without this, the
            # upstream 400 from market-data surfaced as a 500 on every
            # indicator endpoint (seen live 2026-08-18, interval=invalid).
            raise HTTPException(
                status_code=422, detail=f"Invalid interval '{interval}'"
            )
        ttl = getattr(self.settings, "kline_cache_ttl_seconds", 30)
        if ttl <= 0:
            return await self._fetch_klines_uncached(symbol, interval, limit)

        key = (symbol, interval, limit)
        cached = self._kline_cache.get(key)
        if cached and cached[0] > time.monotonic():
            return list(cached[1])

        lock = self._kline_locks.setdefault(key, asyncio.Lock())
        async with lock:
            # Re-check: a concurrent caller may have refreshed while we waited.
            cached = self._kline_cache.get(key)
            if cached and cached[0] > time.monotonic():
                return list(cached[1])
            klines = await self._fetch_klines_uncached(symbol, interval, limit)
            # An empty window is not cached — pinning a transient failure for
            # a full TTL would blank every indicator on the pair.
            if klines:
                self._kline_cache[key] = (time.monotonic() + ttl, klines)
            return list(klines)

    async def _fetch_klines_uncached(
        self, symbol: str, interval: str, limit: int
    ) -> List[Kline]:
        try:
            # Normalize minute-denominated aliases (1440 -> D, 10080 -> W):
            # market-data stores daily/weekly candles under the letter codes.
            interval = normalize_interval(interval)

            params = {
                "interval": interval,
                "limit": limit,
                # Explicitly request mainnet-only rows. The market-data
                # endpoint defaults to True, but being explicit protects
                # against a future default change re-introducing testnet
                # pollution into TA inputs.
                "mainnet_only": "true",
            }

            response = await self.client.get(
                f"{self.base_url}/api/v1/klines/{symbol}", params=params
            )
            response.raise_for_status()

            data = response.json()
            if data.get("success"):
                klines_data = data.get("data", [])

                # Convert to Kline objects
                klines = [
                    Kline(
                        timestamp=k["timestamp"],
                        open=float(k["open"]),
                        high=float(k["high"]),
                        low=float(k["low"]),
                        close=float(k["close"]),
                        volume=float(k["volume"]),
                    )
                    for k in klines_data
                ]

                # Sort by timestamp ascending (oldest first) for TA calculations
                klines.sort(key=lambda x: x.timestamp)

                logger.info(f"Fetched {len(klines)} klines for {symbol} ({interval})")
                return klines
            else:
                logger.error(f"Failed to fetch klines: {data}")
                return []

        except Exception as e:
            # {e!r} + exc_info: httpx timeout exceptions str() to "" - the
            # bare {e} form produced 71 undiagnosable blank-message errors.
            logger.error(
                f"Error fetching klines for {symbol}: {e!r}", exc_info=True
            )
            raise

    async def get_klines_as_dataframe(
        self, symbol: str, interval: str = "60", limit: int = 200
    ) -> pd.DataFrame:
        """
        Fetch klines and return as pandas DataFrame for analysis

        Args:
            symbol: Trading pair
            interval: Candlestick interval
            limit: Number of candles

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume

        Raises:
            ValueError: if fewer than MIN_VALID_ROWS (30) valid candles
                remain after validation — callers should surface this as an
                error instead of computing indicators on garbage.
        """
        interval = normalize_interval(interval)
        klines = await self.get_klines(symbol, interval, limit)

        if not klines:
            raise ValueError(
                f"No kline data available for {symbol} ({interval}); "
                f"cannot compute technical analysis"
            )

        # Convert to DataFrame
        df = pd.DataFrame([k.model_dump() for k in klines])

        # ------------------------------------------------------------------
        # Candle validation (audit 2026-07): protect indicators from corrupt
        # or partial data.
        # ------------------------------------------------------------------
        n_initial = len(df)

        # (b1) Structurally invalid candles: low > high, or non-positive OHLC.
        valid_mask = (
            (df["low"] <= df["high"])
            & (df["open"] > 0)
            & (df["high"] > 0)
            & (df["low"] > 0)
            & (df["close"] > 0)
        )
        n_invalid = int((~valid_mask).sum())
        if n_invalid:
            logger.warning(
                f"Dropped {n_invalid} structurally invalid candle(s) for "
                f"{symbol} ({interval}): low>high or OHLC<=0"
            )
            df = df[valid_mask]

        # (b2) Corrupt jumps: |ln(close/prev_close)| > 0.35 (35% per bar) is
        # not a plausible single-bar move for the traded universe — treat as
        # data corruption (e.g. testnet pollution) and drop the offending row.
        if len(df) > 1:
            log_ret = np.log(df["close"] / df["close"].shift(1)).abs()
            jump_mask = log_ret > MAX_ABS_LOG_RETURN
            n_jumps = int(jump_mask.sum())
            if n_jumps:
                logger.warning(
                    f"Dropped {n_jumps} corrupt candle(s) for {symbol} "
                    f"({interval}): |log return| > {MAX_ABS_LOG_RETURN}"
                )
                df = df[~jump_mask.fillna(False)]

        # (c) Drop the last row if its candle is still forming
        # (timestamp + interval > now): partial candles skew indicators.
        if len(df) > 0:
            now_ms = int(time.time() * 1000)
            last_ts = int(df["timestamp"].iloc[-1])
            if last_ts + _interval_ms(interval) > now_ms:
                logger.debug(
                    f"Dropped still-forming last candle for {symbol} ({interval})"
                )
                df = df.iloc[:-1]

        # (d) Refuse to compute indicators on too little data.
        if len(df) < MIN_VALID_ROWS:
            raise ValueError(
                f"Only {len(df)} valid candles remain for {symbol} "
                f"({interval}) after validation (started with {n_initial}, "
                f"need >= {MIN_VALID_ROWS}); refusing to compute indicators "
                f"on insufficient data"
            )

        # Set timestamp as index for time-series operations
        df = df.copy()
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("datetime", inplace=True)

        logger.info(f"Created DataFrame with {len(df)} rows for {symbol}")
        return df

    async def get_latest_price(
        self, symbol: str, interval: str = "60"
    ) -> Optional[float]:
        """
        Get the most recent closing price

        Args:
            symbol: Trading pair
            interval: Candlestick interval

        Returns:
            Latest close price or None
        """
        try:
            klines = await self.get_klines(symbol, interval, limit=1)
            if klines:
                return klines[-1].close
            return None
        except Exception as e:
            logger.error(
                f"Error getting latest price for {symbol}: {e!r}", exc_info=True
            )
            return None


# Global fetcher instance
_fetcher: Optional[MarketDataFetcher] = None


def get_fetcher() -> MarketDataFetcher:
    """Get fetcher singleton"""
    global _fetcher
    if _fetcher is None:
        _fetcher = MarketDataFetcher()
    return _fetcher


async def close_fetcher():
    """Close fetcher"""
    global _fetcher
    if _fetcher is not None:
        await _fetcher.close()
        _fetcher = None
