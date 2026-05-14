---
phase: 01-bootstrap-recorded-tape
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - services/bybit-connector/app/config.py
  - services/bybit-connector/app/tape_replay_client.py
  - services/bybit-connector/app/main.py
  - services/bybit-connector/tests/test_tape_replay_client.py
autonomous: true
requirements: [INFRA-03]

must_haves:
  truths:
    - "Bybit-connector can boot in tape mode with EMPTY BYBIT_API_KEY and BYBIT_API_SECRET (no validation error)"
    - "GET /health and GET /ready both return 200 in tape mode against on-disk fixtures (no live Bybit API call)"
    - "TapeReplayClient.get_ticker / get_kline mirror BybitRestClient signatures byte-for-byte (no downstream change required)"
    - "Unknown symbols (e.g. XRPUSDT, DOGEUSDT) return [] / empty result instead of raising — symbol-set drift between v1 tape (5 symbols) and market-data scheduler (7 symbols) does NOT crash the connector"
    - "Tape mode startup logs an unambiguous, grep-able line: 'BYBIT_PRICE_SOURCE: mode=tape source_dir=/app/tests/fixtures/tape tape_version=1'"
    - "Tape-mode auth bypass does NOT open any order-execution path — orders remain gated by PAPER_TRADING_MODE / TRADING_MODE / EMERGENCY_STOP / LIVE_TRADING_ACK (unchanged)"
    - "D-02: feeds in v1 tape = klines + ticker only; orderbook L2 + funding-rate deferred (their consumers PREFER_MAKER_ORDERS / ENABLE_FUNDING_GATE default off and forward-test in Phase 5)"
    - "D-08: clock handling = replay timestamps as-is, no clock mock; loader emits original captured timestamp; services see real wall-clock for now() but candle timestamps are pinned"
    - "D-14: selector = single env var MARKET_DATA_SOURCE=tape|live in .env; default tape for fresh bootstrap"
    - "D-15: replay logic lives inside bybit-connector behind the flag; live branch hits real REST/WS; tape branch streams JSONL fixtures preserving same downstream contract — market-data-service does not know it is on tape"
    - "D-17: tape-mode credentials = bypass auth check; when MARKET_DATA_SOURCE=tape, bybit-connector skips BYBIT_API_KEY/BYBIT_API_SECRET validation; bootstrap can run with empty creds"
  artifacts:
    - path: "services/bybit-connector/app/config.py"
      provides: "MARKET_DATA_SOURCE + tape_fixtures_path settings; conditional credential validator"
      contains: "market_data_source"
    - path: "services/bybit-connector/app/tape_replay_client.py"
      provides: "JSONL replay client mirroring BybitRestClient async surface"
      contains: "class TapeReplayClient"
    - path: "services/bybit-connector/app/main.py"
      provides: "Lifespan branches on settings.market_data_source; tape branch enumerates fixtures and refuses /ready if any expected JSONL missing"
      contains: "market_data_source"
    - path: "services/bybit-connector/tests/test_tape_replay_client.py"
      provides: "Unit tests covering /ready ticker shape (landmine §3), unknown-symbol fallback (landmine §4), header tape_version validation"
      contains: "test_get_ticker_returns_dict_with_list_key"
  key_links:
    - from: "services/bybit-connector/app/main.py"
      to: "services/bybit-connector/app/tape_replay_client.py"
      via: "lifespan: app.state.rest_client = TapeReplayClient(...) when settings.market_data_source == 'tape'"
      pattern: "TapeReplayClient\\("
    - from: "services/bybit-connector/app/tape_replay_client.py"
      to: "tests/fixtures/tape/{klines,ticker}/<SYMBOL>USDT.jsonl"
      via: "json.loads(line) per JSONL line in __init__ / on demand"
      pattern: "tests/fixtures/tape"
---

<objective>
Add a `MARKET_DATA_SOURCE=tape|live` selector inside `bybit-connector` (D-14, D-15, D-17) so the service can boot offline against the JSONL fixtures from plan 01. Ship a `TapeReplayClient` that mirrors the public coroutine surface of `BybitRestClient`; relax the credential validator to allow empty keys when mode is tape; branch the lifespan to install the right client. Add unit tests covering the three live-only assumptions (landmines §3 /ready ticker, §4 unknown symbol, §6 missing fixtures) so they fail loud before bootstrap probes them.

Purpose: Decouple the deterministic stack from live Bybit auth + availability — the #1 fresh-clone friction (CONTEXT.md "Specifics").
Output: Modified `config.py` + `main.py`, new `tape_replay_client.py`, new pytest test module.
</objective>

<execution_context>
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/workflows/execute-plan.md
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/01-bootstrap-recorded-tape/01-CONTEXT.md
@.planning/phases/01-bootstrap-recorded-tape/01-PATTERNS.md

<interfaces>
<!-- Coroutine surface TapeReplayClient MUST mirror byte-identically (per PATTERNS.md, bybit_rest_client.py:509-563): -->

class TapeReplayClient:
    def __init__(self, fixtures_path: Path): ...
    async def close(self) -> None: ...
    async def get_ticker(self, category: str = "linear", symbol: Optional[str] = None) -> Dict[str, Any]: ...
        # MUST return {"list": [<ticker_dict>], ...} matching Bybit V5 /v5/market/tickers shape
        # MUST NOT raise on unknown symbol — return {"list": []} instead (landmine §4)
    async def get_kline(self, category: str, symbol: str, interval: str, limit: int = 200,
                        start_time: Optional[int] = None, end_time: Optional[int] = None) -> List[List[str]]: ...
        # MUST return List[List[str]] of [ts, open, high, low, close, volume, turnover]
        # MUST return [] (empty list, not raise) on unknown symbol (landmine §4)
    # Out-of-scope feeds (D-02 — orderbook + funding deferred to Phase 5) — return empty stubs that don't 500:
    async def get_orderbook(self, *args, **kwargs) -> Dict[str, Any]: return {"a": [], "b": []}
    async def get_recent_trades(self, *args, **kwargs) -> List[Any]: return []
    async def get_funding_rate_history(self, *args, **kwargs) -> List[Any]: return []
    async def get_instruments_info(self, *args, **kwargs) -> Dict[str, Any]: return {"list": []}

<!-- JSONL fixture format (from plan 01, D-07): -->
<!--   line 1: {"tape_version": 1, "captured_at": "...", "source": "bybit-mainnet", "symbol": "<S>USDT", "feed": "klines"|"ticker"} -->
<!--   line 2..N (klines): ["<ts_ms>", "<open>", "<high>", "<low>", "<close>", "<volume>", "<turnover>"] -->
<!--   line 2 (ticker): the ticker dict from /v5/market/tickers result.list[0] -->

<!-- Existing config.py validator that MUST become conditional (PATTERNS landmine §2, file:121-127): -->
@field_validator("bybit_api_key", "bybit_api_secret")
@classmethod
def validate_api_credentials(cls, v, info):
    if not v or v == f"your_{info.field_name}_here":
        raise ValueError(f"{info.field_name} must be set with valid credentials")
    return v
<!-- field_validator does NOT see other fields — must convert to model_validator(mode="after") to gate on market_data_source. -->

<!-- /ready endpoint that probes get_ticker (PATTERNS landmine §3, main.py:432-451): -->
async def readiness_check(...):
    await client.get_ticker(category="linear", symbol="SOLUSDT")
<!-- TapeReplayClient.get_ticker MUST return a non-empty result for SOLUSDT or /ready 503s. -->
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Extend config.py — MARKET_DATA_SOURCE field, tape_fixtures_path, conditional validator (D-14, D-17, landmine §2)</name>
  <files>services/bybit-connector/app/config.py</files>
  <read_first>
    - services/bybit-connector/app/config.py (existing Settings class — see lines 121-127 for the validator that must change, lines 140-149 for the property style to mirror)
    - .planning/phases/01-bootstrap-recorded-tape/01-CONTEXT.md (D-14: env var name `MARKET_DATA_SOURCE=tape|live` defaulting to `tape`; D-17: tape mode bypasses BYBIT_API_KEY/SECRET validation)
    - .planning/phases/01-bootstrap-recorded-tape/01-PATTERNS.md (section "services/bybit-connector/app/config.py" + landmine §2 — MUST convert @field_validator to @model_validator)
  </read_first>
  <action>
    Edit `services/bybit-connector/app/config.py`:

    1. Add `from typing import Literal` (if not already imported) and `from pathlib import Path` (probably already there).
    2. Add `from pydantic import model_validator` to the pydantic imports (alongside existing `field_validator`).
    3. Add two new fields on the Settings class (place them next to `bybit_testnet`):

        market_data_source: Literal["tape", "live"] = Field(
            default="tape",
            description="Source for Bybit market data: 'tape' replays JSONL fixtures, 'live' hits real Bybit REST/WS"
        )
        tape_fixtures_path: Path = Field(
            default=Path("/app/tests/fixtures/tape"),
            description="In-container path to tape JSONL fixtures (bind-mounted RO from repo tests/fixtures/tape)"
        )

    4. REPLACE the existing `@field_validator("bybit_api_key", "bybit_api_secret")` block (lines ~121-127) with a single `@model_validator(mode="after")` that runs AFTER all fields are populated:

        @model_validator(mode="after")
        def validate_api_credentials(self):
            """Require non-empty Bybit credentials only in live mode (D-17 — tape mode bypasses auth)."""
            if self.market_data_source == "live":
                for field_name in ("bybit_api_key", "bybit_api_secret"):
                    v = getattr(self, field_name)
                    if not v or v == f"your_{field_name}_here":
                        raise ValueError(f"{field_name} must be set with valid credentials when market_data_source='live'")
            return self

    5. Add a property mirroring the `is_testnet` style at lines ~169-171:

        @property
        def is_tape_mode(self) -> bool:
            """True when market data is replayed from JSONL fixtures."""
            return self.market_data_source == "tape"

    Do NOT remove or rename any existing field. Do NOT change `bybit_testnet` semantics — `BYBIT_TESTNET` still selects price source for the live branch (CLAUDE.md "Trading-mode flags").
  </action>
  <verify>
    <automated>cd services/bybit-connector && python3 -c "import sys; sys.path.insert(0, '.'); from app.config import Settings; s = Settings(market_data_source='tape', bybit_api_key='', bybit_api_secret=''); assert s.is_tape_mode; assert s.market_data_source == 'tape'; print('tape OK')" && python3 - <<'PYEOF'
import sys
sys.path.insert(0, 'services/bybit-connector')
from app.config import Settings
ok = False
try:
    Settings(market_data_source='live', bybit_api_key='', bybit_api_secret='')
except Exception as e:
    ok = 'must be set' in str(e)
assert ok, 'live mode should reject empty creds'
print('live-rejects-empty OK')
PYEOF</automated>
  </verify>
  <done>
    Settings class accepts empty BYBIT_API_KEY/SECRET when `market_data_source='tape'`; rejects them with a clear ValueError when `market_data_source='live'`. Default is `tape`. The `is_tape_mode` property is callable and returns the expected boolean.
  </done>
</task>

<task type="auto">
  <name>Task 2: Create tape_replay_client.py mirroring BybitRestClient surface (D-15, landmines §3, §4, §6)</name>
  <files>services/bybit-connector/app/tape_replay_client.py, services/bybit-connector/tests/test_tape_replay_client.py</files>
  <read_first>
    - services/bybit-connector/app/bybit_rest_client.py (lines 26-99 for class shape + close(); lines 509-563 for get_ticker / get_kline signatures the tape client MUST mirror byte-identically)
    - services/market-data-service/app/fetcher.py (lines 159-188 — downstream consumer's expected shape; the tape client returns Bybit V5 wire format, NOT the parsed dict)
    - services/market-data-service/app/scheduler.py (lines 25-33 — hardcodes 7 symbols including XRPUSDT/DOGEUSDT not in v1 tape; landmine §4 — tape client must return [] for unknown symbol, NOT raise)
    - services/bybit-connector/app/main.py (lines 432-451 — /ready calls client.get_ticker("linear", "SOLUSDT"); landmine §3 — tape client's get_ticker MUST return non-empty for SOLUSDT)
    - .planning/phases/01-bootstrap-recorded-tape/01-CONTEXT.md (D-08 replay timestamps as-is; D-15 same downstream contract on port 8001)
    - .planning/phases/01-bootstrap-recorded-tape/01-PATTERNS.md (section "services/bybit-connector/app/<NEW tape replay loader>" + landmines §3, §4, §6)
  </read_first>
  <action>
    Create `services/bybit-connector/app/tape_replay_client.py`:

    ```python
    """
    Tape replay client for bybit-connector.

    Streams JSONL fixtures from tests/fixtures/tape/ in place of real Bybit REST calls.
    Mirrors the public async surface of BybitRestClient byte-identically so downstream
    services and the DI seam in main.py see no difference (D-15).
    """
    import json
    import logging
    from pathlib import Path
    from typing import Any, Dict, List, Optional

    logger = logging.getLogger(__name__)

    EXPECTED_TAPE_VERSION = 1


    class TapeReplayClient:
        def __init__(self, fixtures_path: Path):
            self.fixtures_path = Path(fixtures_path)
            self._klines: Dict[str, List[List[str]]] = {}    # symbol -> list of klines
            self._tickers: Dict[str, Dict[str, Any]] = {}    # symbol -> ticker dict
            self._load_fixtures()

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
                    "Bind-mount may have silently failed (CLAUDE.md WSL bind-mount race)."
                )

            for kline_file in klines_dir.glob("*.jsonl"):
                symbol = kline_file.stem  # e.g. SOLUSDT
                with open(kline_file, "r") as f:
                    header = json.loads(f.readline())
                    if header.get("tape_version") != EXPECTED_TAPE_VERSION:
                        raise ValueError(
                            f"{kline_file}: tape_version={header.get('tape_version')} "
                            f"expected {EXPECTED_TAPE_VERSION}"
                        )
                    self._klines[symbol] = [json.loads(line) for line in f if line.strip()]

            for ticker_file in ticker_dir.glob("*.jsonl"):
                symbol = ticker_file.stem
                with open(ticker_file, "r") as f:
                    header = json.loads(f.readline())
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
                    f"(klines={len(self._klines)}, tickers={len(self._tickers)})"
                )
            logger.warning(
                "TAPE_REPLAY_LOADED: klines_symbols=%s ticker_symbols=%s tape_version=%d",
                sorted(self._klines.keys()), sorted(self._tickers.keys()), EXPECTED_TAPE_VERSION,
            )

        async def close(self) -> None:
            logger.info("Closed TapeReplayClient")

        async def get_ticker(self, category: str = "linear", symbol: Optional[str] = None) -> Dict[str, Any]:
            """Mirror BybitRestClient.get_ticker — return {'list': [...], ...} V5 shape.

            Unknown symbol -> {'list': []} (landmine §4: do NOT raise; scheduler.py iterates 7 symbols, tape covers 5).
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
            """Mirror BybitRestClient.get_kline — return List[List[str]] of [ts, o, h, l, c, v, turnover].

            Unknown symbol -> [] (landmine §4).
            Replays timestamps as-is per D-08 (no clock mock).
            """
            klines = self._klines.get(symbol, [])
            if not klines:
                logger.warning("TAPE_REPLAY: no kline data for symbol=%s (returning empty)", symbol)
                return []
            # Optional window filter (mimics live Bybit's start/end behavior)
            if start_time is not None or end_time is not None:
                def in_window(k):
                    ts = int(k[0])
                    if start_time is not None and ts < int(start_time):
                        return False
                    if end_time is not None and ts > int(end_time):
                        return False
                    return True
                klines = [k for k in klines if in_window(k)]
            # Bybit V5 returns klines sorted descending (latest first); mirror that.
            return list(reversed(klines))[:limit]

        # Out-of-scope feeds (D-02 — orderbook + funding deferred to Phase 5).
        async def get_orderbook(self, *args, **kwargs) -> Dict[str, Any]:
            return {"a": [], "b": [], "ts": 0, "u": 0}

        async def get_recent_trades(self, *args, **kwargs) -> Dict[str, Any]:
            return {"list": []}

        async def get_funding_rate_history(self, *args, **kwargs) -> Dict[str, Any]:
            return {"list": []}

        async def get_instruments_info(self, *args, **kwargs) -> Dict[str, Any]:
            return {"list": []}
    ```

    Then create `services/bybit-connector/tests/test_tape_replay_client.py` with these tests (use pytest + tmp_path fixture):

    ```python
    """
    Tests for TapeReplayClient — guards the three live-only assumptions:
    - landmine §3: /ready calls get_ticker("linear", "SOLUSDT") -> non-empty result
    - landmine §4: unknown symbol (e.g. XRPUSDT) returns [] / empty list, NOT raise
    - landmine §6: missing/empty fixtures dir refuses init
    Plus header tape_version validation per D-07.
    """
    import json
    import pytest
    from pathlib import Path
    from app.tape_replay_client import TapeReplayClient


    def _write_fixture(path: Path, header: dict, lines: list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(json.dumps(header) + "\n")
            for line in lines:
                f.write(json.dumps(line) + "\n")


    @pytest.fixture
    def fake_tape(tmp_path: Path) -> Path:
        kline_header = {"tape_version": 1, "captured_at": "2026-05-06T00:00:00Z",
                        "source": "bybit-mainnet", "symbol": "SOLUSDT", "feed": "klines"}
        kline_lines = [["1700000000000", "100.0", "101.0", "99.0", "100.5", "1000", "100500"]]
        _write_fixture(tmp_path / "klines" / "SOLUSDT.jsonl", kline_header, kline_lines)

        ticker_header = {"tape_version": 1, "captured_at": "2026-05-06T00:00:00Z",
                         "source": "bybit-mainnet", "symbol": "SOLUSDT", "feed": "ticker"}
        ticker_lines = [{"symbol": "SOLUSDT", "lastPrice": "100.5", "volume24h": "1000000"}]
        _write_fixture(tmp_path / "ticker" / "SOLUSDT.jsonl", ticker_header, ticker_lines)
        return tmp_path


    @pytest.mark.asyncio
    async def test_get_ticker_returns_dict_with_list_key(fake_tape):
        """Landmine §3: /ready in main.py awaits get_ticker(SOLUSDT); must return non-empty list shape."""
        client = TapeReplayClient(fake_tape)
        result = await client.get_ticker(category="linear", symbol="SOLUSDT")
        assert isinstance(result, dict)
        assert "list" in result
        assert len(result["list"]) == 1
        assert result["list"][0]["symbol"] == "SOLUSDT"


    @pytest.mark.asyncio
    async def test_unknown_symbol_returns_empty_not_raises(fake_tape):
        """Landmine §4: scheduler.py iterates 7 symbols; v1 tape covers 5. Unknown must return [] / empty, NOT raise."""
        client = TapeReplayClient(fake_tape)
        klines = await client.get_kline(category="linear", symbol="XRPUSDT", interval="5")
        assert klines == []
        ticker = await client.get_ticker(category="linear", symbol="DOGEUSDT")
        assert ticker == {"category": "linear", "list": []}


    @pytest.mark.asyncio
    async def test_get_kline_returns_list_of_lists_v5_shape(fake_tape):
        """Downstream fetcher.py expects List[List[str]] of [ts, o, h, l, c, v, turnover]."""
        client = TapeReplayClient(fake_tape)
        klines = await client.get_kline(category="linear", symbol="SOLUSDT", interval="5")
        assert isinstance(klines, list)
        assert len(klines) == 1
        assert isinstance(klines[0], list)
        assert len(klines[0]) == 7  # ts, o, h, l, c, v, turnover


    def test_missing_fixtures_dir_refuses_init(tmp_path):
        """Landmine §6: WSL bind-mount race — empty fixtures dir must refuse init, not silently serve nothing."""
        empty = tmp_path / "empty_tape"
        empty.mkdir()
        with pytest.raises(FileNotFoundError):
            TapeReplayClient(empty)


    def test_wrong_tape_version_rejected(tmp_path):
        """D-07: loader rejects mismatched tape_version."""
        kline_header = {"tape_version": 99, "captured_at": "x", "source": "bybit-mainnet",
                        "symbol": "SOLUSDT", "feed": "klines"}
        _write_fixture(tmp_path / "klines" / "SOLUSDT.jsonl", kline_header, [])
        ticker_header = {"tape_version": 1, "captured_at": "x", "source": "bybit-mainnet",
                         "symbol": "SOLUSDT", "feed": "ticker"}
        _write_fixture(tmp_path / "ticker" / "SOLUSDT.jsonl", ticker_header, [{"symbol": "SOLUSDT"}])
        with pytest.raises(ValueError, match="tape_version"):
            TapeReplayClient(tmp_path)
    ```
  </action>
  <verify>
    <automated>cd services/bybit-connector && python3 -c "import ast; ast.parse(open('app/tape_replay_client.py').read())" && python3 -m pytest tests/test_tape_replay_client.py -x -q 2>&1 | tail -20</automated>
  </verify>
  <done>
    `tape_replay_client.py` parses cleanly. All 5 unit tests pass: get_ticker returns the expected shape for SOLUSDT; unknown symbol (XRPUSDT, DOGEUSDT) returns empty without raising; get_kline returns List[List[str]] V5 shape; empty fixtures dir refuses init; mismatched tape_version is rejected.
  </done>
</task>

<task type="auto">
  <name>Task 3: Branch lifespan in main.py — install TapeReplayClient when settings.market_data_source == 'tape' (D-15, landmine §6)</name>
  <files>services/bybit-connector/app/main.py</files>
  <read_first>
    - services/bybit-connector/app/main.py (lines 288-336 — existing lifespan; lines 385-393 — DI seam; lines 421-451 — health/ready that probe ticker)
    - services/bybit-connector/app/tape_replay_client.py (just created in Task 2)
    - services/bybit-connector/app/config.py (just modified in Task 1)
    - .planning/phases/01-bootstrap-recorded-tape/01-CONTEXT.md (D-15: replay logic inside bybit-connector behind the flag; downstream services unchanged on port 8001)
    - .planning/phases/01-bootstrap-recorded-tape/01-PATTERNS.md (section "services/bybit-connector/app/main.py" + landmine §6 — refuse /ready if fixtures missing; "Loud, grep-able startup log line" pattern at main.py:310-313 must gain `mode=tape|live`)
  </read_first>
  <action>
    Edit `services/bybit-connector/app/main.py`:

    1. At the top of the file, add the import alongside existing imports:
        from app.tape_replay_client import TapeReplayClient

    2. In `lifespan()` (around line 288), AFTER `settings = get_settings()` and BEFORE the existing `app.state.rest_client = create_rest_client(...)` block:

        # D-14/D-15: branch on market_data_source. Tape mode skips live REST + clock sync.
        if settings.market_data_source == "tape":
            logger.warning(
                "BYBIT_PRICE_SOURCE: mode=tape source_dir=%s tape_version=1",
                settings.tape_fixtures_path,
            )
            try:
                app.state.rest_client = TapeReplayClient(settings.tape_fixtures_path)
                _update_breaker_gauge(CircuitState.CLOSED)
                logger.info("Tape replay client initialized successfully")
            except FileNotFoundError as exc:
                # Landmine §6 — bind-mount race. Refuse to come up rather than silently serve empty.
                logger.error("TAPE_REPLAY_INIT_FAILED: %s", exc)
                raise
            yield
            await app.state.rest_client.close()
            return

    3. The existing `try: app.state.rest_client = create_rest_client(...)` block (live branch) stays. ALSO modify the existing log line near line 310:

        logger.warning(
            "BYBIT_PRICE_SOURCE: mode=live testnet=%s rest_url=%s ws_url=%s",
            settings.bybit_testnet, settings.rest_api_url, settings.websocket_url,
        )

    Move this log line into the live branch (keep tape branch's distinct log line). Result: every startup logs ONE `BYBIT_PRICE_SOURCE:` line whose `mode=` field is unambiguous.

    4. Do NOT modify the `/health`, `/ready`, `/api/v1/market/*` route handlers, or the `get_rest_client` DI dependency. The whole point of D-15 is downstream code sees no difference. The DI seam at lines 385-393 already accepts `app.state.rest_client` of any type with the BybitRestClient async method surface — TapeReplayClient mirrors that surface.

    5. Do NOT delete `app/main.py.bak` (operator's backup, not in scope).
  </action>
  <verify>
    <automated>python3 -c "import ast; ast.parse(open('services/bybit-connector/app/main.py').read())" && grep -q "from app.tape_replay_client import TapeReplayClient" services/bybit-connector/app/main.py && grep -q "if settings.market_data_source == \"tape\":" services/bybit-connector/app/main.py && grep -q "BYBIT_PRICE_SOURCE: mode=tape" services/bybit-connector/app/main.py && grep -q "BYBIT_PRICE_SOURCE: mode=live" services/bybit-connector/app/main.py</automated>
  </verify>
  <done>
    main.py parses cleanly, imports TapeReplayClient, branches on `settings.market_data_source == "tape"` to install the replay client (and skip live REST + clock sync), and emits a distinct `BYBIT_PRICE_SOURCE: mode=tape|live` log line on startup so log audits can grep the active mode.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| .env -> bybit-connector Settings | Empty BYBIT_API_KEY / BYBIT_API_SECRET allowed in tape mode (D-17); creds REQUIRED in live mode |
| TapeReplayClient -> tests/fixtures/tape/*.jsonl | Read-only file I/O at startup; refuses init if dir missing/empty (landmine §6) |
| bybit-connector -> downstream services (port 8001) | Same HTTP/WS contract regardless of mode (D-15); no new auth surface |
| tape-mode auth bypass -> trading paths | Order execution still gated by PAPER_TRADING_MODE + TRADING_MODE + EMERGENCY_STOP + LIVE_TRADING_ACK — UNCHANGED |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-02-01 | E (Elevation of privilege) | config.py credential validator | mitigate | Tape-mode auth bypass is read-only data access. The validator change ONLY removes the BYBIT_API_KEY non-empty check; it does NOT touch PAPER_TRADING_MODE / TRADING_MODE / EMERGENCY_STOP / LIVE_TRADING_ACK gating in trading-engine. Confirmed by grep gate: `! grep -E "PAPER_TRADING_MODE\|TRADING_MODE\|EMERGENCY_STOP\|LIVE_TRADING_ACK" services/bybit-connector/app/config.py` returns success (these flags do NOT live in bybit-connector config — they live in trading-engine and are unchanged). |
| T-02-02 | T (Tampering) | tape JSONL fixtures | mitigate | TapeReplayClient validates `tape_version == 1` on every fixture file at init; mismatched / corrupted header -> ValueError (covered by `test_wrong_tape_version_rejected`). |
| T-02-03 | D (Denial of service) | TapeReplayClient init failure | mitigate | Bind-mount race (landmine §6) -> empty fixtures dir -> `FileNotFoundError` raised in lifespan -> service refuses to come `ready`. Loud failure beats silent empty data. |
| T-02-04 | S (Spoofing) | log audit grep | mitigate | Single grep-able startup line `BYBIT_PRICE_SOURCE: mode=tape\|live` so verify-stack skill can confirm active mode without ambiguity. Live and tape branches emit DIFFERENT prefixes; impossible to spoof one from the other. |
</threat_model>

<verification>
- `cd services/bybit-connector && python3 -m pytest tests/test_tape_replay_client.py -x -q` returns 5 passed.
- Settings instantiates with `market_data_source='tape'` and empty Bybit creds; raises ValueError with `market_data_source='live'` and empty creds.
- `python3 -c "import ast; ast.parse(open('services/bybit-connector/app/main.py').read())"` succeeds.
- `grep -c "BYBIT_PRICE_SOURCE: mode=" services/bybit-connector/app/main.py` returns at least 2 (one tape, one live).
- `grep -q "TapeReplayClient" services/bybit-connector/app/main.py` succeeds (import + instantiation present).
</verification>

<success_criteria>
- Setting `MARKET_DATA_SOURCE=tape` + leaving BYBIT_API_KEY/SECRET empty boots bybit-connector without ValueError.
- `/health` and `/ready` (which probes `client.get_ticker("linear", "SOLUSDT")`) both return 200 in tape mode against the fixtures from plan 01.
- Calling `client.get_kline(symbol="XRPUSDT", ...)` returns `[]` (not 500, not raise) — scheduler.py's 7-symbol iteration does not crash the connector despite tape covering only 5 symbols.
- A grep over startup logs unambiguously identifies the active mode via the `BYBIT_PRICE_SOURCE: mode=...` line.
</success_criteria>

<output>
After completion, create `.planning/phases/01-bootstrap-recorded-tape/01-02-SUMMARY.md` documenting the public method coverage of TapeReplayClient vs BybitRestClient, the test count, and any gaps deferred to Phase 5 (orderbook + funding stubs).
</output>
