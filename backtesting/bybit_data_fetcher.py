#!/usr/bin/env python3
"""
Bybit Historical Data Fetcher
Downloads OHLCV data for backtesting via the bybit-connector service.

Phase 13 (BC-02): routes through ``$BYBIT_CONNECTOR_URL/api/v1/market/kline``
(default ``http://localhost:8001``). bybit-connector handles testnet/mainnet
selection internally via its own ``BYBIT_TESTNET`` env, so this fetcher no
longer accepts a ``testnet`` constructor parameter.

NOTE on ``is_mainnet`` (CLAUDE.md backtest data-integrity rule). Two separate
things carry that name and only one of them is a filter:

* the ``klines`` **table** query filter (``run_walk_forward_ensemble.py:563``)
  — untouched by this module;
* the ``is_mainnet`` **column this fetcher writes** into the 11-column
  ``klines``-schema CSV, which ``backtesting/killtests/candles.py`` then
  refuses to load if any row is False.

The second is a taint stamp, and until 2026-08-07 it was stamped ``True``
unconditionally — so the consumer's guard could never fire, no matter which
network the connector was pointed at. This fetcher cannot observe that:
bybit-connector selects testnet vs mainnet from its own ``BYBIT_TESTNET`` env
and exposes it nowhere on its REST surface (it appears only in a startup log
line, ``bybit-connector/app/main.py:339,370``). So the stamp is now backed by
an explicit operator assertion — ``--assert-mainnet`` — that the writer must
make and that the error message tells them how to check. See
``_require_mainnet_assertion``.
"""

import asyncio
import os
import sys
import httpx
import pandas as pd
from datetime import datetime
import time
import logging
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Phase 13 BC-02: bybit-connector endpoint. Host-friendly default; the compose
# stack overrides this to ``http://bybit-connector:8001`` via environment.
BYBIT_CONNECTOR_URL = os.getenv("BYBIT_CONNECTOR_URL", "http://localhost:8001")


MAINNET_ASSERTION_ENV = "BACKTEST_MAINNET_ASSERTED"


def _require_mainnet_assertion(asserted: bool, target_url: str) -> None:
    """Refuse to stamp ``is_mainnet=True`` on data nobody vouched for.

    The stamp is a data-integrity claim consumed by
    ``backtesting/killtests/candles.py`` and by every backtest that trusts the
    CSV. bybit-connector does not expose its testnet flag on any endpoint, so
    this process cannot verify the claim itself and will not invent it.

    RESIDUAL GAP, stated plainly: this is an assertion, not a proof. A caller
    who passes ``--assert-mainnet`` while the connector is on testnet still
    produces poisoned CSVs. Closing it properly needs bybit-connector to
    publish its ``bybit_testnet`` setting (e.g. on ``/health``), which is a
    service change, deliberately out of scope here.
    """
    if asserted or os.getenv(MAINNET_ASSERTION_ENV) == "1":
        return
    raise SystemExit(
        "\nREFUSING to write klines-schema CSVs: nothing has asserted that "
        f"{target_url} is serving MAINNET data.\n"
        "  Why:   the is_mainnet column this writes is a taint stamp that "
        "downstream consumers trust and cannot re-derive.\n"
        "  Check: docker compose -f docker-compose.unified.yml exec "
        "bybit-connector env | grep BYBIT_TESTNET   (must be false)\n"
        "         docker compose -f docker-compose.unified.yml logs "
        "bybit-connector | grep BYBIT_PRICE_SOURCE   (must read "
        "mode=live testnet=False)\n"
        f"  Then:  re-run with --assert-mainnet (or {MAINNET_ASSERTION_ENV}=1).\n"
        "  Note:  the legacy 6-column schema writes no is_mainnet column and "
        "needs no assertion.\n"
    )


def _print_connector_unreachable(target_url: str, err: BaseException) -> None:
    """Shared operator-readable error block (used by both sync + async probes)."""
    print(
        f"\nERROR: bybit-connector is not reachable at {target_url}.\n"
        f"  Cause: {err!r}\n"
        f"  Fix:   Run `docker compose -f docker-compose.unified.yml up -d bybit-connector`\n"
        f"  (or set BYBIT_CONNECTOR_URL if running against a non-default host).\n",
        file=sys.stderr,
    )


def assert_connector_reachable_sync(target_url: Optional[str] = None) -> None:
    """D-04 sync probe — used at ``__main__`` startup.

    Calls ``sys.exit(2)`` with an operator-readable error if the bybit-connector
    health endpoint is unreachable. Synchronous (uses ``httpx.Client``) so it can
    run before ``asyncio.run(main())`` without leaking a running loop.
    """
    target = target_url or BYBIT_CONNECTOR_URL
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{target}/health")
            response.raise_for_status()
    except Exception as e:
        _print_connector_unreachable(target, e)
        sys.exit(2)


async def assert_connector_reachable(target_url: Optional[str] = None) -> None:
    """D-04 async probe — used inside async library callers (e.g. fetch_klines).

    Calls ``sys.exit(2)`` with an operator-readable error if the bybit-connector
    health endpoint is unreachable. Async to share the caller's event loop.
    """
    target = target_url or BYBIT_CONNECTOR_URL
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{target}/health")
            response.raise_for_status()
    except Exception as e:
        _print_connector_unreachable(target, e)
        sys.exit(2)


async def assert_connector_live(
    fetcher: "BybitDataFetcher", symbol: str = "BTCUSDT", interval: str = "60"
) -> None:
    """Refuse to backfill from a connector serving frozen tape fixtures.

    A connector in MARKET_DATA_SOURCE=tape mode answers /health and serves
    klines, but the newest candle is weeks old. Fresh mainnet data must have
    a candle newer than 3 intervals ago.
    """
    rows = await fetcher.fetch_klines(symbol=symbol, interval=interval, limit=5)
    if not rows:
        raise RuntimeError("connector returned no candles; cannot verify liveness")
    newest_ms = max(int(r[0]) for r in rows)
    interval_ms = (
        fetcher.convert_interval_to_minutes(interval) * 60 * 1000
    )  # instance method (bybit_data_fetcher.py:193)
    age = int(time.time() * 1000) - newest_ms
    if age > 3 * interval_ms:
        raise RuntimeError(
            f"connector data is stale: newest {symbol}/{interval} candle is "
            f"{age / 3600000:.1f}h old — is bybit-connector in tape mode? "
            f"(MARKET_DATA_SOURCE must be 'live', see docker-compose.unified.yml:453)"
        )


class BybitDataFetcher:
    """
    Fetches historical market data via the bybit-connector service.
    Uses the V5 kline list shape that bybit-connector preserves through its
    JSON wrapper.
    """

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize fetcher routed to bybit-connector.

        Args:
            base_url: Optional override of ``$BYBIT_CONNECTOR_URL``. Falls back
                to the env var, then to ``http://localhost:8001``.
        """
        self.base_url = base_url or BYBIT_CONNECTOR_URL
        self.client = httpx.AsyncClient(timeout=30.0, base_url=self.base_url)

        # Bybit rate limits: 10 requests per second for public endpoints.
        # bybit-connector adds an extra hop but the upstream cap still applies.
        self.rate_limit_delay = 0.15  # 150ms between requests (safe margin)

        # D-04 fail-fast: gate so we only probe the connector ONCE per fetcher
        # instance. The probe runs lazily on the first call to ``fetch_klines``
        # (which is the entry point library callers hit) — keeps construction
        # cheap while still surfacing an operator-readable error before any
        # business-critical I/O.
        self._reachability_checked = False

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

    async def fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000,
    ) -> list:
        """
        Get kline/candlestick data via bybit-connector.

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Kline interval (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)
            start_time: Start timestamp in milliseconds (optional)
            end_time: End timestamp in milliseconds (optional)
            limit: Number of candles to fetch (max 1000, Bybit v5 hard cap)

        Returns:
            List of kline rows (Bybit V5 shape preserved by the connector wrapper).
        """
        # D-04 fail-fast on first use (class-level path). Library callers that
        # import this class directly get the same operator-readable hint as
        # ``__main__`` callers — without re-probing on every batch.
        if not self._reachability_checked:
            await assert_connector_reachable(self.base_url)
            self._reachability_checked = True

        endpoint = "/api/v1/market/kline"

        params = {
            "category": "linear",  # USDT perpetual
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start_time is not None:
            params["start"] = start_time
        if end_time is not None:
            params["end"] = end_time

        try:
            response = await self.client.get(endpoint, params=params)
            response.raise_for_status()

            data = response.json()

            # bybit-connector wrapper shape: {"success": bool, "data": [...]}.
            # The connector's own get_kline() already unwraps Bybit's nested
            # {"result": {"list": [...]}} server-side (bybit_rest_client.py:581
            # `return result.get("list", [])`), so "data" here is already the
            # flat V5 row list — NOT {"list": [...]} again. Confirmed live via
            # `curl .../api/v1/market/kline` during Task 2 (2026-08-05); a prior
            # double-unwrap here silently returned [] on every call since 57b0d72.
            if not data.get("success"):
                logger.error(f"bybit-connector kline error: {data}")
                return []

            # Extract klines (flat V5 row list; see comment above)
            klines = data.get("data", [])

            return klines

        except Exception as e:
            logger.error(f"Error fetching klines: {e}")
            return []

    # Backwards-compatible alias — older download_*.py call sites use get_klines().
    # Keeps the public surface intact while routing through fetch_klines (which
    # also runs the first-call reachability probe).
    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        limit: int = 1000,
    ) -> list:
        return await self.fetch_klines(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

    def convert_interval_to_minutes(self, interval: str) -> int:
        """
        Convert interval string to minutes

        Args:
            interval: Interval string (60, 240, D, etc.)

        Returns:
            Number of minutes
        """
        if interval == "D":
            return 24 * 60
        elif interval == "W":
            return 7 * 24 * 60
        elif interval == "M":
            return 30 * 24 * 60
        else:
            return int(interval)

    async def download_historical_data(
        self,
        symbol: str,
        interval: str = "60",  # 1 hour
        days: int = 90,
        output_file: Optional[str] = None,
        schema: str = "legacy",
        mainnet_asserted: bool = False,
    ) -> pd.DataFrame:
        """
        Download historical OHLCV data from Bybit

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Candle interval in minutes (1, 5, 15, 30, 60, 240, D)
            days: Number of days of historical data
            output_file: Optional CSV file to save data
            schema: 'legacy' (timestamp, open, high, low, close, volume) or
                'klines' (11-col: adds symbol, interval, turnover, is_mainnet,
                created_at) for CSV output
            mainnet_asserted: caller vouches that the connector is on mainnet.
                Required to write the klines schema — see
                ``_require_mainnet_assertion``.

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        if schema == "klines" and output_file:
            _require_mainnet_assertion(mainnet_asserted, self.base_url)
        logger.info(
            f"Downloading {days} days of {symbol} data at {interval}m interval from Bybit..."
        )

        # Calculate time range
        end_time = int(time.time() * 1000)  # Current time in ms
        interval_minutes = self.convert_interval_to_minutes(interval)
        start_time = end_time - (days * 24 * 60 * 60 * 1000)  # days ago in ms

        logger.info(
            f"Time range: {datetime.fromtimestamp(start_time / 1000)} to {datetime.fromtimestamp(end_time / 1000)}"
        )

        all_klines = []
        current_end = end_time
        max_candles_per_request = (
            1000  # Bybit v5 hard cap (connector clamps via min(limit, 1000))
        )

        # Calculate total candles needed
        total_candles_needed = int((days * 24 * 60) / interval_minutes)
        candles_downloaded = 0

        logger.info(f"Expecting approximately {total_candles_needed} candles...")

        # Fetch data in batches (working backwards from present)
        while current_end > start_time and candles_downloaded < total_candles_needed:
            # Calculate batch start time
            batch_duration_ms = max_candles_per_request * interval_minutes * 60 * 1000
            batch_start = max(start_time, current_end - batch_duration_ms)

            logger.info(
                f"Fetching batch: {datetime.fromtimestamp(batch_start / 1000)} to {datetime.fromtimestamp(current_end / 1000)}"
            )

            # Fetch klines
            klines = await self.get_klines(
                symbol=symbol,
                interval=interval,
                start_time=batch_start,
                end_time=current_end,
                limit=max_candles_per_request,
            )

            if not klines:
                logger.warning("No data received, stopping download")
                break

            # Bybit returns data in reverse order (newest first), so we need to reverse it
            klines.reverse()

            all_klines.extend(klines)
            candles_downloaded += len(klines)

            logger.info(
                f"Downloaded {len(klines)} candles (total: {candles_downloaded})"
            )

            # Move to next batch (go backwards in time)
            # Use the timestamp of the oldest candle in this batch
            if klines:
                oldest_candle_time = int(klines[0][0])  # First element is start time
                current_end = oldest_candle_time - 1  # Move just before this candle

            # Rate limiting
            await asyncio.sleep(self.rate_limit_delay)

            # Safety check to prevent infinite loops
            if len(klines) < 10 and current_end > start_time:
                logger.warning(
                    "Received very few candles, might have reached data limit"
                )
                break

        if not all_klines:
            logger.error("No data downloaded")
            return pd.DataFrame()

        # Convert to DataFrame
        # Bybit kline format: [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
        df = pd.DataFrame(
            all_klines,
            columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"],
        )

        # Convert data types
        df["timestamp"] = pd.to_numeric(df["timestamp"])
        df["open"] = pd.to_numeric(df["open"])
        df["high"] = pd.to_numeric(df["high"])
        df["low"] = pd.to_numeric(df["low"])
        df["close"] = pd.to_numeric(df["close"])
        df["volume"] = pd.to_numeric(df["volume"])

        # Remove duplicates and sort
        df = df.drop_duplicates(subset=["timestamp"])
        df = df.sort_values("timestamp")

        # Convert timestamp to datetime
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        # Keep only required columns
        turnover_series = df["turnover"].copy()
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]

        logger.info(f"Total candles downloaded: {len(df)}")
        logger.info(
            f"Date range: {df.iloc[0]['timestamp']} to {df.iloc[-1]['timestamp']}"
        )
        logger.info(
            f"Price range: ${df['close'].min():.2f} to ${df['close'].max():.2f}"
        )

        # Save to CSV if requested
        if output_file:
            if schema == "klines":
                fetch_time_ms = int(time.time() * 1000)
                out = df.copy()
                out["symbol"] = symbol
                out["interval"] = interval
                out["turnover"] = turnover_series.values  # kept from pre-trim df
                # Certified by the caller's --assert-mainnet, checked above.
                # Never stamp this from nothing: candles.py refuses False rows,
                # so an unconditional True makes that guard unfalsifiable.
                out["is_mainnet"] = True
                out["created_at"] = fetch_time_ms
                out = out[
                    [
                        "timestamp",
                        "symbol",
                        "interval",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                        "turnover",
                        "is_mainnet",
                        "created_at",
                    ]
                ]
                # Drop trailing forming/in-progress bar(s): Bybit V5 always
                # returns the newest bar even when it hasn't closed yet.
                # Consumers that walk the full frame (e.g. H3's replay
                # driver) must never see a still-forming close price, so
                # keep only rows whose bar has actually closed as of write
                # time. Legacy schema is intentionally left untouched.
                interval_ms = interval_minutes * 60 * 1000
                # Epoch-anchored subtraction rather than `.astype("int64")`:
                # pandas' datetime64 storage resolution (ns/us/ms) varies by
                # version and by how the column was constructed, so a raw
                # int64 cast is not reliably milliseconds. This division is
                # resolution-independent.
                ts_ms = (out["timestamp"] - pd.Timestamp("1970-01-01")) // pd.Timedelta(
                    milliseconds=1
                )
                out = out[ts_ms + interval_ms <= fetch_time_ms]
                out.to_csv(output_file, index=False)
            else:
                df.to_csv(output_file, index=False)
            logger.info(f"Data saved to: {output_file} (schema={schema})")

        return df

    async def download_multiple_symbols(
        self,
        symbols: list,
        interval: str = "60",
        days: int = 90,
        output_dir: str = "backtesting/data",
        schema: str = "legacy",
        mainnet_asserted: bool = False,
    ):
        """
        Download data for multiple symbols

        Args:
            symbols: List of trading pairs
            interval: Candle interval
            days: Days of historical data
            output_dir: Directory to save CSV files
            schema: 'legacy' or 'klines' — forwarded to download_historical_data
            mainnet_asserted: forwarded; required for the klines schema
        """
        import os

        os.makedirs(output_dir, exist_ok=True)

        for symbol in symbols:
            logger.info(f"\n{'=' * 80}")
            logger.info(f"Downloading {symbol}")
            logger.info(f"{'=' * 80}\n")

            output_file = f"{output_dir}/{symbol}_{interval}m_{days}d_bybit.csv"

            df = await self.download_historical_data(
                symbol=symbol,
                interval=interval,
                days=days,
                output_file=output_file,
                schema=schema,
                mainnet_asserted=mainnet_asserted,
            )

            logger.info(f"✓ {symbol} complete: {len(df)} candles\n")

            # Longer delay between symbols
            await asyncio.sleep(1.0)


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Download historical data via bybit-connector "
            "(routed at $BYBIT_CONNECTOR_URL, default http://localhost:8001)."
        )
    )
    parser.add_argument(
        "--symbol", type=str, default="BTCUSDT", help="Trading pair (default: BTCUSDT)"
    )
    parser.add_argument(
        "--interval", type=str, default="60", help="Interval in minutes (default: 60)"
    )
    parser.add_argument(
        "--days", type=int, default=90, help="Days of historical data (default: 90)"
    )
    parser.add_argument("--output", type=str, help="Output CSV file")
    parser.add_argument(
        "--connector-url",
        type=str,
        default=None,
        help=(
            "Override $BYBIT_CONNECTOR_URL for this run. bybit-connector chooses "
            "testnet vs mainnet via its own BYBIT_TESTNET env — there is no "
            "--testnet flag here any more."
        ),
    )
    parser.add_argument("--multiple", nargs="+", help="Download multiple symbols")
    parser.add_argument(
        "--schema",
        choices=["legacy", "klines"],
        default="legacy",
        help="CSV schema: 'legacy' (6-col) or 'klines' (11-col, default: legacy)",
    )
    parser.add_argument(
        "--assert-mainnet",
        action="store_true",
        help=(
            "Assert that the connector is serving MAINNET data. Required to "
            "write the klines schema, whose is_mainnet column downstream "
            "consumers trust and cannot re-derive. bybit-connector does not "
            "expose its BYBIT_TESTNET setting on any endpoint, so this cannot "
            "be verified here — check it yourself first (the refusal message "
            "lists the two commands)."
        ),
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="backtesting/data",
        help=(
            "Output directory for downloaded CSVs, single-symbol or --multiple "
            "(overridden by --output for the single-symbol path; default: "
            "backtesting/data)"
        ),
    )

    args = parser.parse_args()

    fetcher = BybitDataFetcher(base_url=args.connector_url)

    # Refuse at arg-parse time rather than after a 20-minute download.
    if args.schema == "klines":
        _require_mainnet_assertion(args.assert_mainnet, fetcher.base_url)

    try:
        await assert_connector_live(fetcher)

        if args.multiple:
            # Download multiple symbols
            await fetcher.download_multiple_symbols(
                symbols=args.multiple,
                interval=args.interval,
                days=args.days,
                output_dir=args.out_dir,
                schema=args.schema,
                mainnet_asserted=args.assert_mainnet,
            )
        else:
            # Download single symbol
            output_file = (
                args.output
                or f"{args.out_dir}/{args.symbol}_{args.interval}m_{args.days}d_bybit.csv"
            )

            df = await fetcher.download_historical_data(
                symbol=args.symbol,
                interval=args.interval,
                days=args.days,
                output_file=output_file,
                schema=args.schema,
                mainnet_asserted=args.assert_mainnet,
            )

            if not df.empty:
                print("\n" + "=" * 80)
                print("DOWNLOAD COMPLETE")
                print("=" * 80)
                print(f"Symbol: {args.symbol}")
                print(f"Interval: {args.interval} minutes")
                print(f"Total Candles: {len(df)}")
                print(
                    f"Date Range: {df.iloc[0]['timestamp']} to {df.iloc[-1]['timestamp']}"
                )
                print(
                    f"Price Range: ${df['close'].min():.2f} to ${df['close'].max():.2f}"
                )
                print(f"File: {output_file}")
                print("=" * 80)

                # Show first and last few rows
                print("\nFirst 5 candles:")
                print(df.head())
                print("\nLast 5 candles:")
                print(df.tail())

    finally:
        await fetcher.close()


if __name__ == "__main__":
    # D-04 fail-fast (CLI path): probe the bybit-connector before doing any work.
    # The class-level path (BybitDataFetcher.fetch_klines) also runs a
    # first-call probe for library callers that import the class directly.
    assert_connector_reachable_sync()
    asyncio.run(main())
