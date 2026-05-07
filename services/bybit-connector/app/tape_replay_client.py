"""
Tape replay client for bybit-connector.

Streams JSONL fixtures from tests/fixtures/tape/ in place of real Bybit REST calls.
Mirrors the public async surface of BybitRestClient byte-identically so downstream
services and the DI seam in main.py see no difference (D-15).

Fixture layout (D-01, D-07):
  tests/fixtures/tape/klines/<SYMBOL>USDT.jsonl
  tests/fixtures/tape/ticker/<SYMBOL>USDT.jsonl

Line 1 of each JSONL is a header: {"tape_version": 1, "captured_at": "...",
  "source": "bybit-mainnet", "symbol": "...", "feed": "klines"|"ticker"}
Lines 2..N:
  klines: ["<ts_ms>", "<open>", "<high>", "<low>", "<close>", "<volume>", "<turnover>"]
  ticker: the ticker dict from /v5/market/tickers result.list[0]
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

EXPECTED_TAPE_VERSION = 1


class TapeReplayClient:
    """
    In-process JSONL fixture replay client.

    Mirrors the public coroutine surface of BybitRestClient (get_ticker,
    get_kline, get_orderbook, get_recent_trades, get_funding_rate_history,
    get_instruments_info, close) so the DI seam at main.py:385-393 and
    all downstream consumers work without modification (D-15).

    Unknown symbols -> return empty list/dict (NOT raise) per landmine §4:
    scheduler.py iterates 7 symbols; v1 tape covers only 5.

    Missing/empty fixtures dir -> FileNotFoundError at init per landmine §6:
    bind-mount race must fail loud, not silently serve empty data.
    """

    def __init__(self, fixtures_path: Path):
        self.fixtures_path = Path(fixtures_path)
        self._klines: Dict[str, List[List[str]]] = {}  # symbol -> list of klines
        self._tickers: Dict[str, Dict[str, Any]] = {}  # symbol -> ticker dict
        self._load_fixtures()
        # Cursor fields populated after _load_fixtures() so symbol keys are available.
        # Per-test reset semantics (D-04): POST /admin/tape/reset zeroes these so the
        # next test starts at fixture position 0 without restarting the connector.
        self._kline_cursor: Dict[str, int] = {sym: 0 for sym in self._klines}
        self._ticker_cursor: Dict[str, int] = {sym: 0 for sym in self._tickers}

    def _load_fixtures(self) -> None:
        """Eagerly load all JSONL fixtures into memory at init.

        Refuses init (raises FileNotFoundError) if the fixtures dir is missing
        or empty — guards against the WSL bind-mount race (landmine §6).
        """
        klines_dir = self.fixtures_path / "klines"
        ticker_dir = self.fixtures_path / "ticker"

        if not klines_dir.is_dir() or not ticker_dir.is_dir():
            raise FileNotFoundError(
                f"Tape fixtures missing or unreadable: {self.fixtures_path}. "
                "Expected sub-directories 'klines/' and 'ticker/'. "
                "Bind-mount may have silently failed (CLAUDE.md WSL bind-mount race)."
            )

        for kline_file in sorted(klines_dir.glob("*.jsonl")):
            symbol = kline_file.stem  # e.g. SOLUSDT
            with open(kline_file, "r") as f:
                raw_header = f.readline()
                if not raw_header.strip():
                    raise FileNotFoundError(
                        f"{kline_file}: file is empty (no header line)"
                    )
                header = json.loads(raw_header)
                if header.get("tape_version") != EXPECTED_TAPE_VERSION:
                    raise ValueError(
                        f"{kline_file}: tape_version={header.get('tape_version')} "
                        f"expected {EXPECTED_TAPE_VERSION}"
                    )
                self._klines[symbol] = [json.loads(line) for line in f if line.strip()]

        for ticker_file in sorted(ticker_dir.glob("*.jsonl")):
            symbol = ticker_file.stem
            with open(ticker_file, "r") as f:
                raw_header = f.readline()
                if not raw_header.strip():
                    raise FileNotFoundError(
                        f"{ticker_file}: file is empty (no header line)"
                    )
                header = json.loads(raw_header)
                if header.get("tape_version") != EXPECTED_TAPE_VERSION:
                    raise ValueError(
                        f"{ticker_file}: tape_version={header.get('tape_version')} "
                        f"expected {EXPECTED_TAPE_VERSION}"
                    )
                snapshots = [json.loads(line) for line in f if line.strip()]
                if snapshots:
                    self._tickers[symbol] = snapshots[0]

        if not self._klines or not self._tickers:
            raise FileNotFoundError(
                f"No tape fixtures loaded under {self.fixtures_path} "
                f"(klines={len(self._klines)}, tickers={len(self._tickers)}). "
                "Bind-mount may have silently failed (CLAUDE.md WSL bind-mount race)."
            )

        logger.warning(
            "TAPE_REPLAY_LOADED: klines_symbols=%s ticker_symbols=%s tape_version=%d",
            sorted(self._klines.keys()),
            sorted(self._tickers.keys()),
            EXPECTED_TAPE_VERSION,
        )

    # =========================================================================
    # ASYNC LIFECYCLE (mirrors BybitRestClient)
    # =========================================================================

    def reset(self) -> None:
        """Reset all in-memory cursors to fixture position 0 (D-04).

        Called by POST /admin/tape/reset between integration tests so the
        recorded-tape data clock rewinds without restarting the connector.
        """
        self._kline_cursor = {sym: 0 for sym in self._klines}
        self._ticker_cursor = {sym: 0 for sym in self._tickers}
        logger.warning(
            "TAPE_REPLAY: cursors reset (klines=%d, tickers=%d)",
            len(self._kline_cursor),
            len(self._ticker_cursor),
        )

    async def close(self) -> None:
        """No-op: no HTTP client to close. Mirrors BybitRestClient.close()."""
        logger.info("TapeReplayClient closed (no-op)")

    # =========================================================================
    # MARKET DATA ENDPOINTS (mirrors BybitRestClient public surface)
    # =========================================================================

    async def get_ticker(
        self, category: str = "linear", symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """Mirror BybitRestClient.get_ticker — return {'list': [...], ...} V5 shape.

        Landmine §3: /ready in main.py awaits get_ticker("linear", "SOLUSDT");
        must return non-empty result so /ready returns 200 in tape mode.

        Landmine §4: unknown symbol (e.g. XRPUSDT not in v1 tape) -> {'list': []}
        instead of raising — scheduler.py iterates 7 symbols, tape covers 5.
        """
        if symbol and symbol in self._tickers:
            return {"category": category, "list": [self._tickers[symbol]]}
        return {"category": category, "list": []}

    async def get_kline(
        self,
        category: str,
        symbol: str,
        interval: str,
        limit: int = 200,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[List[str]]:
        """Mirror BybitRestClient.get_kline — return List[List[str]] of
        [ts, open, high, low, close, volume, turnover].

        Landmine §4: unknown symbol -> [] (not raise).
        D-08: replay timestamps as-is, no clock mock.
        Bybit V5 returns klines descending (latest first); mirror that.
        """
        klines = self._klines.get(symbol, [])
        if not klines:
            logger.warning(
                "TAPE_REPLAY: no kline data for symbol=%s (returning empty)", symbol
            )
            return []

        # Optional window filter (mimics live Bybit start/end behaviour)
        if start_time is not None or end_time is not None:

            def in_window(k: List[str]) -> bool:
                ts = int(k[0])
                if start_time is not None and ts < int(start_time):
                    return False
                if end_time is not None and ts > int(end_time):
                    return False
                return True

            klines = [k for k in klines if in_window(k)]

        # Bybit V5 returns descending (newest first); stored ascending -> reverse
        return list(reversed(klines))[:limit]

    # =========================================================================
    # OUT-OF-SCOPE FEEDS (D-02 — orderbook + funding deferred to Phase 5)
    # Expose as empty stubs so existing routes don't 500. Default-off consumers
    # (PREFER_MAKER_ORDERS, ENABLE_FUNDING_GATE) won't read them.
    # =========================================================================

    async def get_orderbook(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        return {"a": [], "b": [], "ts": 0, "u": 0}

    async def get_recent_trades(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        return {"list": []}

    async def get_funding_rate_history(
        self, *args: Any, **kwargs: Any
    ) -> Dict[str, Any]:
        return {"list": []}

    async def get_instruments_info(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        return {"list": []}
