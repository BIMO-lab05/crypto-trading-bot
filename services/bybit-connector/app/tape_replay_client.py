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
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

EXPECTED_TAPE_VERSION = 1

# Phase 18 BC-FIX-02 (D-07) — wallet balance fixture (co-located with tape root)
WALLET_BALANCE_FIXTURE_NAME = "wallet_balance.json"
DEFAULT_WALLET_BALANCE = {
    "USDT": 100.0
}  # D-07 locked default (per ADR-010 paper wallet)


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
        # Phase 18 WR-05: kline/ticker cursors were declared, reset by
        # reset(), and asserted by D-04 tests but never read by get_kline /
        # get_ticker (which return the full loaded fixture on every call).
        # Removed to avoid dead state that could mislead future readers into
        # thinking there's a consumer-side advance.
        # ------------------------------------------------------------------
        # Phase 18 BC-FIX-02 — order-path state (D-05/D-06/D-07/D-08)
        # Lazy-loaded balance: first get_wallet_balance / place_order call
        # initialises from the on-disk fixture (BL-01: refuses init if
        # missing — the runtime bind-mount is read-only) and tracks balance
        # in-memory thereafter.
        # ------------------------------------------------------------------
        self._order_log: List[
            Dict[str, Any]
        ] = []  # D-08 in-memory order history (this session)
        self._open_orders: Dict[
            str, Dict[str, Any]
        ] = {}  # order_id -> order dict (post-fill)
        self._order_counter: int = (
            0  # monotonic tie-breaker for sub-ms place_order calls (advisor note)
        )
        self._wallet_balance: Optional[Dict[str, float]] = (
            None  # lazy-loaded from fixture
        )

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
    # WALLET STATE — Phase 18 BC-FIX-02 (D-07)
    # =========================================================================

    def _wallet_fixture_path(self) -> Path:
        """Return the on-disk path of the wallet_balance.json fixture.

        Lives next to the kline/ticker fixtures so tape-replay state for a
        given test run is colocated. Path mirrors the tape root layout the
        `--fixtures` flag (or settings.tape_fixtures_path) already points at.
        """
        return self.fixtures_path / WALLET_BALANCE_FIXTURE_NAME

    def _load_wallet_balance(self) -> None:
        """Initialise self._wallet_balance from the on-disk fixture.

        Called lazily on first balance-touching method (get_wallet_balance /
        place_order) so __init__ remains synchronous and inexpensive.

        Phase 18 BL-01 fix: refuses init if the fixture is missing rather
        than lazy-writing a default. The runtime bind-mount is read-only
        (docker-compose.unified.yml:409 mounts tests/fixtures/tape as :ro),
        so a lazy write would raise OSError inside the first request.
        Mirrors the kline/ticker loader policy in _load_fixtures() — loud
        FileNotFoundError beats a silent runtime crash later.
        """
        path = self._wallet_fixture_path()
        if not path.exists():
            raise FileNotFoundError(
                f"Wallet balance fixture missing at {path}. "
                "Seed the file at tests/fixtures/tape/wallet_balance.json "
                f"(e.g. {json.dumps(DEFAULT_WALLET_BALANCE)}). "
                "The runtime bind-mount is read-only so this file must exist "
                "on disk before tape-mode requests are served."
            )
        with open(path, "r") as fh:
            self._wallet_balance = json.load(fh)
        logger.info(
            "TAPE_REPLAY: loaded wallet balance %s from %s",
            self._wallet_balance,
            path,
        )

    # =========================================================================
    # ASYNC LIFECYCLE (mirrors BybitRestClient)
    # =========================================================================

    def reset(self) -> None:
        """Reset all in-memory session state to fixture-load defaults (D-04, D-08).

        Called by POST /admin/tape/reset between integration tests so the
        connector state rewinds without a restart. Phase 18 WR-05 removed
        the unused kline/ticker cursors, so reset() now only touches the
        order-path session state (D-08) and forces a wallet reload from
        the on-disk fixture.
        """
        # Phase 18 BC-FIX-02 (D-08) — clear order-path session state
        self._order_log = []
        self._open_orders = {}
        self._order_counter = 0
        # Reload wallet balance from fixture (operator may have edited the
        # JSON between tests to seed a different starting position).
        self._wallet_balance = None  # force lazy reload on next access
        logger.warning(
            "TAPE_REPLAY: cursors reset (order_log cleared, wallet lazy-reload armed)"
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
    # ORDER PATH — Phase 18 BC-FIX-02 (D-05/D-06/D-07/D-08)
    # Stub implementations so the LIVE adapter code path can be exercised
    # against a recorded tape without reaching Bybit.
    # =========================================================================

    async def place_order(
        self,
        category: str,
        symbol: str,
        side: str,
        order_type: str,
        qty: str,
        price: Optional[str] = None,
        time_in_force: Optional[str] = None,
        reduce_only: bool = False,
        order_link_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Deterministic fake FILLED order per Phase 18 D-05.

        Behaviour:
          * Order ID shape: f"TAPE_{symbol}_{side}_{int(time*1000)}_{counter}"
            — counter is monotonic per-instance so two sub-ms calls cannot
            collide (advisor note + D-05).
          * Fill price = self._tickers[symbol]["lastPrice"]; if symbol is not
            in the loaded tickers, falls back to the limit `price` argument.
          * Status returned as the literal string "Filled" — Bybit V5 wire
            format. Downstream `bybit_adapter._parse_order` maps this to
            OrderStatus.FILLED.
          * Balance decremented by float(fill_price) * float(qty) on USDT
            (D-07; all v1.3 paper-validated symbols are USDT-quoted).
        """
        ticker_entry = self._tickers.get(symbol, {})
        fill_price_str = ticker_entry.get("lastPrice") or price
        if fill_price_str is None:
            logger.warning(
                "TAPE_REPLAY place_order: no ticker for %s and no price given; "
                "rejecting with empty result (mirrors unknown-symbol semantics)",
                symbol,
            )
            return {
                "orderId": "",
                "orderLinkId": order_link_id,
                "orderStatus": "Rejected",
            }

        if self._wallet_balance is None:
            self._load_wallet_balance()

        self._order_counter += 1
        timestamp_ms = int(time.time() * 1000)
        order_id = f"TAPE_{symbol}_{side}_{timestamp_ms}_{self._order_counter}"

        fill_price_d = Decimal(str(fill_price_str))
        qty_d = Decimal(str(qty))
        notional = float(fill_price_d * qty_d)
        if self._wallet_balance is not None and "USDT" in self._wallet_balance:
            self._wallet_balance["USDT"] = float(
                Decimal(str(self._wallet_balance["USDT"])) - Decimal(str(notional))
            )

        order_result = {
            "orderId": order_id,
            "orderLinkId": order_link_id,
            "symbol": symbol,
            "side": side,
            "orderStatus": "Filled",
            "avgPrice": str(fill_price_d),
            "cumExecQty": str(qty_d),
            "qty": str(qty_d),
            "orderType": order_type,
            "category": category,
            "reduceOnly": reduce_only,
            "timeInForce": time_in_force or "GTC",
        }

        self._order_log.append({**order_result, "kwargs": dict(kwargs)})
        self._open_orders[order_id] = order_result

        logger.info(
            "TAPE_REPLAY place_order: %s %s qty=%s @ %s -> %s",
            symbol,
            side,
            qty,
            fill_price_d,
            order_id,
        )
        return order_result

    async def cancel_order(
        self,
        category: str,
        symbol: str,
        order_id: Optional[str] = None,
        order_link_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """No-op cancellation per Phase 18 D-06.

        Cancellation makes no sense in deterministic replay (all orders fill
        immediately at the tape ticker), so return success without mutating
        the order log or wallet balance.
        """
        target = order_id or order_link_id or ""
        logger.info(
            "TAPE_REPLAY cancel_order: no-op for %s (order_id=%s, link_id=%s)",
            symbol,
            order_id,
            order_link_id,
        )
        return {"success": True, "order_id": target, "symbol": symbol}

    async def get_wallet_balance(
        self,
        account_type: str = "UNIFIED",
        coin: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return Bybit-V5-shaped wallet balance per Phase 18 D-07.

        Lazy-loads the in-memory balance dict from
        tests/fixtures/tape/wallet_balance.json on first call.
        BL-01: raises FileNotFoundError if the fixture is missing (the
        runtime bind-mount is read-only, so lazy-writing a default would
        fail with OSError inside the request path).
        """
        if self._wallet_balance is None:
            self._load_wallet_balance()
        balance_view = dict(self._wallet_balance or DEFAULT_WALLET_BALANCE)
        if coin:
            coin_upper = coin.upper()
            balance_view = {k: v for k, v in balance_view.items() if k == coin_upper}

        coin_entries = [
            {
                "coin": k,
                "walletBalance": str(v),
                "availableToWithdraw": str(v),
                "locked": "0",
            }
            for k, v in balance_view.items()
        ]
        return {
            "list": [
                {
                    "accountType": account_type,
                    "totalEquity": str(sum(balance_view.values())),
                    "availableBalance": str(sum(balance_view.values())),
                    "totalPositionIM": "0",
                    "totalPerpUPL": "0",
                    "coin": coin_entries,
                }
            ]
        }

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
