"""
Tests for TapeReplayClient — guards the three live-only assumptions (landmines):

  §3  /ready calls get_ticker("linear", "SOLUSDT") → non-empty result (200 not 503)
  §4  unknown symbol (e.g. XRPUSDT) returns [] / empty list, NOT raise
  §6  missing/empty fixtures dir refuses init with FileNotFoundError (loud failure)

Plus:
  D-07  header tape_version mismatch → ValueError at init
  D-15  kline shape is List[List[str]] of [ts, o, h, l, c, v, turnover] (7 elements)

All tests use tmp_path fixtures — NO dependency on tests/fixtures/tape/ files
created by the parallel plan 01-01 (per plan rules §5).
"""

import json
import pytest
from pathlib import Path

from app.tape_replay_client import TapeReplayClient, EXPECTED_TAPE_VERSION


# ===========================================================================
# Helpers
# ===========================================================================


def _write_fixture(path: Path, header: dict, lines: list) -> None:
    """Write a JSONL fixture file: header on line 1, data on subsequent lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(json.dumps(header) + "\n")
        for line in lines:
            f.write(json.dumps(line) + "\n")


# ===========================================================================
# Shared fixture: minimal valid tape with one symbol (SOLUSDT)
# ===========================================================================


@pytest.fixture
def fake_tape(tmp_path: Path) -> Path:
    """Minimal valid tape directory with SOLUSDT klines + ticker."""
    kline_header = {
        "tape_version": EXPECTED_TAPE_VERSION,
        "captured_at": "2026-05-06T00:00:00Z",
        "source": "bybit-mainnet",
        "symbol": "SOLUSDT",
        "feed": "klines",
    }
    # 7-element row: [ts, open, high, low, close, volume, turnover]
    kline_rows = [
        ["1700000000000", "100.0", "101.0", "99.0", "100.5", "1000", "100500"],
        ["1700000060000", "100.5", "102.0", "100.0", "101.0", "1200", "121200"],
    ]
    _write_fixture(tmp_path / "klines" / "SOLUSDT.jsonl", kline_header, kline_rows)

    ticker_header = {
        "tape_version": EXPECTED_TAPE_VERSION,
        "captured_at": "2026-05-06T00:00:00Z",
        "source": "bybit-mainnet",
        "symbol": "SOLUSDT",
        "feed": "ticker",
    }
    ticker_rows = [{"symbol": "SOLUSDT", "lastPrice": "100.5", "volume24h": "1000000"}]
    _write_fixture(tmp_path / "ticker" / "SOLUSDT.jsonl", ticker_header, ticker_rows)

    return tmp_path


# ===========================================================================
# Landmine §3: /ready ticker shape
# ===========================================================================


async def test_get_ticker_returns_dict_with_list_key(fake_tape: Path) -> None:
    """Landmine §3: /ready in main.py awaits get_ticker(SOLUSDT); must return
    non-empty list with 'list' key so HTTPException(503) is NOT raised."""
    client = TapeReplayClient(fake_tape)
    result = await client.get_ticker(category="linear", symbol="SOLUSDT")

    assert isinstance(result, dict), "get_ticker must return a dict"
    assert "list" in result, "result must have 'list' key (Bybit V5 shape)"
    assert len(result["list"]) == 1, "SOLUSDT must have exactly one ticker entry"
    assert result["list"][0]["symbol"] == "SOLUSDT"


# ===========================================================================
# Landmine §4: unknown symbol returns empty, does NOT raise
# ===========================================================================


async def test_unknown_symbol_get_ticker_returns_empty_not_raises(
    fake_tape: Path,
) -> None:
    """Landmine §4: scheduler.py iterates 7 symbols; v1 tape covers 5.
    XRPUSDT / DOGEUSDT not in tape → must return {'list': []}, not raise."""
    client = TapeReplayClient(fake_tape)

    result = await client.get_ticker(category="linear", symbol="DOGEUSDT")
    assert isinstance(result, dict)
    assert result.get("list") == [], (
        f"Expected empty list for unknown symbol, got {result}"
    )


async def test_unknown_symbol_get_kline_returns_empty_not_raises(
    fake_tape: Path,
) -> None:
    """Landmine §4: get_kline for unknown symbol must return [], not raise."""
    client = TapeReplayClient(fake_tape)

    klines = await client.get_kline(category="linear", symbol="XRPUSDT", interval="5")
    assert klines == [], f"Expected [] for unknown symbol, got {klines}"


# ===========================================================================
# Landmine §6: missing fixtures dir refuses init
# ===========================================================================


def test_missing_fixtures_dir_refuses_init(tmp_path: Path) -> None:
    """Landmine §6: WSL bind-mount race — empty fixtures dir (no sub-dirs)
    must raise FileNotFoundError at init, not silently serve empty data."""
    empty = tmp_path / "empty_tape"
    empty.mkdir()

    with pytest.raises(FileNotFoundError):
        TapeReplayClient(empty)


def test_fixtures_dir_with_no_files_refuses_init(tmp_path: Path) -> None:
    """Landmine §6: sub-dirs present but empty → FileNotFoundError (no fixtures loaded)."""
    (tmp_path / "klines").mkdir(parents=True)
    (tmp_path / "ticker").mkdir(parents=True)

    with pytest.raises(FileNotFoundError):
        TapeReplayClient(tmp_path)


# ===========================================================================
# D-07: tape_version header validation
# ===========================================================================


def test_wrong_tape_version_in_klines_rejected(tmp_path: Path) -> None:
    """D-07: loader rejects mismatched tape_version on klines file."""
    bad_kline_header = {
        "tape_version": 99,  # wrong version
        "captured_at": "x",
        "source": "bybit-mainnet",
        "symbol": "SOLUSDT",
        "feed": "klines",
    }
    _write_fixture(tmp_path / "klines" / "SOLUSDT.jsonl", bad_kline_header, [])

    # ticker must be valid (otherwise we'd fail on ticker, not klines)
    good_ticker_header = {
        "tape_version": EXPECTED_TAPE_VERSION,
        "captured_at": "x",
        "source": "bybit-mainnet",
        "symbol": "SOLUSDT",
        "feed": "ticker",
    }
    _write_fixture(
        tmp_path / "ticker" / "SOLUSDT.jsonl",
        good_ticker_header,
        [{"symbol": "SOLUSDT", "lastPrice": "1.0"}],
    )

    with pytest.raises(ValueError, match="tape_version"):
        TapeReplayClient(tmp_path)


# ===========================================================================
# D-15: kline return shape (List[List[str]], 7 elements per row)
# ===========================================================================


async def test_get_kline_returns_list_of_lists_v5_shape(fake_tape: Path) -> None:
    """D-15: downstream fetcher.py expects List[List[str]] of
    [ts, open, high, low, close, volume, turnover] (7 elements).
    Bybit V5 returns newest-first; tape client must mirror that ordering."""
    client = TapeReplayClient(fake_tape)
    klines = await client.get_kline(category="linear", symbol="SOLUSDT", interval="5")

    assert isinstance(klines, list), "get_kline must return a list"
    assert len(klines) == 2, "Fixture has 2 rows"
    for row in klines:
        assert isinstance(row, list), f"Each kline must be a list, got {type(row)}"
        assert len(row) == 7, (
            f"Each kline must have 7 elements [ts,o,h,l,c,v,t], got {len(row)}"
        )

    # Verify descending order (newest first) — Bybit V5 wire format convention
    ts0, ts1 = int(klines[0][0]), int(klines[1][0])
    assert ts0 > ts1, f"Klines must be newest-first (got {ts0} <= {ts1})"


# ===========================================================================
# D-04: per-test cursor reset (Phase 2 plan 02-01 contract)
#
# These tests exercise TapeReplayClient.reset() — called by the new
# POST /admin/tape/reset endpoint between integration tests so the recorded
# tape's data clock rewinds without restarting the connector.
# ===========================================================================


def test_reset_clears_session_state_after_init(fake_tape_with_wallet: Path) -> None:
    """D-04 (post-WR-05): post-init, calling reset() leaves the session
    state at its zero baseline (empty order log, counter=0, wallet lazy).

    Phase 18 WR-05 removed the unused kline/ticker cursor fields — they
    were populated and reset by this method but never read by get_kline/
    get_ticker. The remaining reset() contract is order-path session
    state (D-08) + wallet lazy-reload.
    """
    client = TapeReplayClient(fake_tape_with_wallet)
    client.reset()

    assert client._order_log == [], "post-init reset(): order log must be empty"
    assert client._open_orders == {}, "post-init reset(): open orders must be empty"
    assert client._order_counter == 0, "post-init reset(): counter must be 0"
    # Wallet is lazy-reloaded — reset() arms the reload but does not touch disk.
    assert client._wallet_balance is None, (
        "post-init reset(): wallet balance must be armed for lazy reload"
    )
    # Sanity: fixture dicts still loaded (reset() must NOT touch _klines/_tickers).
    assert "SOLUSDT" in client._klines
    assert "SOLUSDT" in client._tickers


async def test_reset_rewinds_session_state_after_activity(
    fake_tape_with_wallet: Path,
) -> None:
    """D-04 (post-WR-05): after place_order activity, reset() rewinds to baseline.

    Simulates a test that ran some orders and verifies the next test starts
    at counter=0 with an empty order log.
    """
    client = TapeReplayClient(fake_tape_with_wallet)

    await client.place_order(
        category="linear",
        symbol="SOLUSDT",
        side="Buy",
        order_type="Market",
        qty="1",
    )
    assert client._order_counter == 1, "Precondition: counter should have incremented"
    assert len(client._order_log) == 1, "Precondition: order log should have 1 entry"

    client.reset()

    assert client._order_counter == 0, (
        f"counter must rewind to 0; got {client._order_counter}"
    )
    assert client._order_log == [], "order log must be cleared by reset()"


def test_reset_does_not_touch_fixture_dicts(fake_tape: Path) -> None:
    """D-04 (post-WR-05): reset() must not disturb the loaded kline/ticker
    fixtures — those are the immutable seed data for the test session.
    """
    client = TapeReplayClient(fake_tape)
    kline_snapshot = {k: list(v) for k, v in client._klines.items()}
    ticker_snapshot = dict(client._tickers)

    client.reset()

    assert client._klines == kline_snapshot, (
        "reset() must not mutate the loaded kline fixtures"
    )
    assert client._tickers == ticker_snapshot, (
        "reset() must not mutate the loaded ticker fixtures"
    )


def test_reset_emits_grep_able_log_line(fake_tape: Path, caplog) -> None:
    """D-04: reset() emits a single grep-able log line at WARNING level.

    State-transition log convention from main.py:314 — operator log audits +
    RUNBOOK triage rely on the prefix `TAPE_REPLAY: cursors reset`.
    """
    import logging

    client = TapeReplayClient(fake_tape)

    # Ensure caplog captures the tape_replay_client logger at WARNING.
    with caplog.at_level(logging.WARNING, logger="app.tape_replay_client"):
        client.reset()

    matching = [
        rec
        for rec in caplog.records
        if "TAPE_REPLAY: cursors reset" in rec.getMessage()
    ]
    assert len(matching) >= 1, (
        f"Expected at least one log record with prefix "
        f"'TAPE_REPLAY: cursors reset' at WARNING level; "
        f"saw: {[r.getMessage() for r in caplog.records]}"
    )
    assert matching[0].levelno >= logging.WARNING, (
        f"reset() log line must be WARNING or higher; got {matching[0].levelname}"
    )


# ===========================================================================
# Phase 18 BC-FIX-02: order-path stubs (D-05/D-06/D-07/D-08)
# These tests lock in the locked semantics from 18-CONTEXT.md so future
# refactors of place_order/cancel_order/get_wallet_balance cannot silently
# weaken the integration-test contract the trading-engine LIVE adapter
# relies on in tape mode.
# ===========================================================================


@pytest.fixture
def fake_tape_with_wallet(fake_tape: Path) -> Path:
    """Extends fake_tape with the D-07 wallet balance fixture file."""
    import json as _json

    wallet_path = fake_tape / "wallet_balance.json"
    wallet_path.write_text(_json.dumps({"USDT": 100.0}) + "\n")
    return fake_tape


# ---- D-05: place_order returns deterministic FILLED order -----------------


async def test_place_order_returns_filled_order(fake_tape_with_wallet: Path) -> None:
    """D-05: place_order returns a Filled order dict at the current tape
    ticker price. fake_tape SOLUSDT ticker has lastPrice="100.5".
    """
    from app.tape_replay_client import TapeReplayClient

    client = TapeReplayClient(fake_tape_with_wallet)
    result = await client.place_order(
        category="linear",
        symbol="SOLUSDT",
        side="Buy",
        order_type="Market",
        qty="1",
    )
    assert result["orderStatus"] == "Filled", (
        f"D-05: status must be 'Filled', got {result.get('orderStatus')!r}"
    )
    assert result["avgPrice"] == "100.5", (
        f"D-05: fill price must equal tape ticker lastPrice 100.5, got {result.get('avgPrice')!r}"
    )
    assert result["cumExecQty"] == "1", (
        f"D-05: filled qty must equal requested qty (1), got {result.get('cumExecQty')!r}"
    )
    assert result["symbol"] == "SOLUSDT"
    assert result["side"] == "Buy"
    assert result["orderId"].startswith("TAPE_SOLUSDT_Buy_"), (
        f"D-05: order ID must start with TAPE_SOLUSDT_Buy_, got {result.get('orderId')!r}"
    )


async def test_place_order_id_is_deterministic_and_monotonic(
    fake_tape_with_wallet: Path,
) -> None:
    """D-05 + advisor note: two consecutive place_order calls in the same
    millisecond must produce DIFFERENT order IDs.
    """
    from app.tape_replay_client import TapeReplayClient

    client = TapeReplayClient(fake_tape_with_wallet)
    r1 = await client.place_order(
        category="linear", symbol="SOLUSDT", side="Buy", order_type="Market", qty="1"
    )
    r2 = await client.place_order(
        category="linear", symbol="SOLUSDT", side="Buy", order_type="Market", qty="1"
    )
    assert r1["orderId"] != r2["orderId"], (
        f"D-05: two place_order calls must produce distinct order IDs "
        f"(got {r1['orderId']} == {r2['orderId']})"
    )
    parts1 = r1["orderId"].split("_")
    parts2 = r2["orderId"].split("_")
    assert len(parts1) == 5 and len(parts2) == 5, (
        f"D-05: order ID shape must be TAPE_<symbol>_<side>_<ts_ms>_<counter>, "
        f"got {r1['orderId']!r} / {r2['orderId']!r}"
    )
    counter1 = int(parts1[-1])
    counter2 = int(parts2[-1])
    assert counter2 > counter1, (
        f"D-05: counter must be monotonic (r2={counter2} > r1={counter1})"
    )


async def test_place_order_decrements_balance(
    fake_tape_with_wallet: Path,
) -> None:
    """D-07: place_order decrements in-memory USDT balance by fill_price*qty.
    Starting balance 100 USDT, BUY 0.5 SOLUSDT at fill price 100.5 -> new
    balance 100 - 50.25 = 49.75.
    """
    from app.tape_replay_client import TapeReplayClient

    client = TapeReplayClient(fake_tape_with_wallet)
    await client.place_order(
        category="linear", symbol="SOLUSDT", side="Buy", order_type="Market", qty="0.5"
    )
    balance = await client.get_wallet_balance(account_type="UNIFIED", coin="USDT")
    coin_entry = balance["list"][0]["coin"][0]
    assert coin_entry["coin"] == "USDT"
    assert float(coin_entry["walletBalance"]) == pytest.approx(49.75, abs=0.01), (
        f"D-07: balance must decrement by qty*price (100 - 0.5*100.5 = 49.75), "
        f"got {coin_entry['walletBalance']!r}"
    )


# ---- D-06: cancel_order is a no-op success --------------------------------


async def test_cancel_order_is_no_op_success(fake_tape_with_wallet: Path) -> None:
    """D-06: cancel_order returns success no-op without mutating order log or balance."""
    from app.tape_replay_client import TapeReplayClient

    client = TapeReplayClient(fake_tape_with_wallet)
    placed = await client.place_order(
        category="linear", symbol="SOLUSDT", side="Buy", order_type="Market", qty="1"
    )
    log_len_before = len(client._order_log)
    balance_before = (
        client._wallet_balance.get("USDT") if client._wallet_balance else None
    )

    result = await client.cancel_order(
        category="linear", symbol="SOLUSDT", order_id=placed["orderId"]
    )
    assert result == {
        "success": True,
        "order_id": placed["orderId"],
        "symbol": "SOLUSDT",
    }, f"D-06: cancel_order must return success no-op shape, got {result!r}"
    assert len(client._order_log) == log_len_before, (
        "D-06: cancel_order must not mutate _order_log"
    )
    assert (
        client._wallet_balance.get("USDT") if client._wallet_balance else None
    ) == balance_before, "D-06: cancel_order must not mutate balance"


# ---- D-07: get_wallet_balance fixture load + lazy-write ------------------


async def test_get_wallet_balance_loads_from_fixture(
    fake_tape_with_wallet: Path,
) -> None:
    """D-07: get_wallet_balance returns the seeded $100 USDT default from the fixture."""
    from app.tape_replay_client import TapeReplayClient

    client = TapeReplayClient(fake_tape_with_wallet)
    balance = await client.get_wallet_balance()
    coin_entries = balance["list"][0]["coin"]
    usdt_entries = [c for c in coin_entries if c["coin"] == "USDT"]
    assert len(usdt_entries) == 1, (
        f"D-07: expected exactly one USDT entry, got {coin_entries!r}"
    )
    assert float(usdt_entries[0]["walletBalance"]) == 100.0, (
        f"D-07: fixture default must be 100 USDT, got {usdt_entries[0]['walletBalance']!r}"
    )


async def test_get_wallet_balance_raises_when_fixture_missing(
    fake_tape: Path,
) -> None:
    """BL-01: when wallet_balance.json is absent, first call raises
    FileNotFoundError instead of silently writing a default.

    Previous behaviour lazy-wrote the D-07 default to disk on first call.
    That crashed at runtime because docker-compose.unified.yml:409 mounts
    tests/fixtures/tape as :ro. Loud FileNotFoundError beats an OSError
    inside the request path — mirrors _load_fixtures() policy.
    """
    from app.tape_replay_client import TapeReplayClient

    wallet_path = fake_tape / "wallet_balance.json"
    assert not wallet_path.exists(), (
        "Precondition: fake_tape (without _with_wallet) must NOT have wallet json"
    )

    client = TapeReplayClient(fake_tape)
    with pytest.raises(FileNotFoundError, match="wallet_balance"):
        await client.get_wallet_balance()

    # Fixture must NOT have been created by the failed call — the read-only
    # mount policy means the loader must never touch disk on the write path.
    assert not wallet_path.exists(), (
        "BL-01: failed load must NOT write the fixture (read-only bind-mount)"
    )


# ---- D-08: reset() clears order-path state -------------------------------


async def test_reset_clears_order_state(fake_tape_with_wallet: Path) -> None:
    """D-08: after place_order mutates state, reset() clears _order_log,
    _open_orders, _order_counter, and reloads _wallet_balance from fixture.
    """
    from app.tape_replay_client import TapeReplayClient

    client = TapeReplayClient(fake_tape_with_wallet)
    await client.place_order(
        category="linear", symbol="SOLUSDT", side="Buy", order_type="Market", qty="0.5"
    )

    assert len(client._order_log) == 1, "Precondition: order should be in log"
    assert client._order_counter == 1, "Precondition: counter incremented"
    assert client._wallet_balance is not None
    assert client._wallet_balance["USDT"] != 100.0, (
        "Precondition: balance should have been decremented from default"
    )

    client.reset()

    assert client._order_log == [], "D-08: reset() must clear _order_log"
    assert client._open_orders == {}, "D-08: reset() must clear _open_orders"
    assert client._order_counter == 0, "D-08: reset() must reset _order_counter to 0"

    balance = await client.get_wallet_balance(account_type="UNIFIED", coin="USDT")
    usdt = float(balance["list"][0]["coin"][0]["walletBalance"])
    assert usdt == 100.0, (
        f"D-08: reset() must reload wallet to fixture default 100; got {usdt}"
    )
