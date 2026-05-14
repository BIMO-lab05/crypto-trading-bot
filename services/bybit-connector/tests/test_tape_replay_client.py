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


def test_reset_zeroes_cursors_after_init(fake_tape: Path) -> None:
    """D-04: post-init, calling reset() yields per-symbol cursor dicts at 0.

    Cursor dicts must contain one entry per loaded symbol (not empty), each
    initialised to fixture position 0. This is the post-init steady-state.
    """
    client = TapeReplayClient(fake_tape)
    client.reset()

    # Both cursor dicts must be populated AND zero-valued.
    assert client._kline_cursor == {sym: 0 for sym in client._klines}, (
        "kline cursor must zero-init for every loaded kline symbol"
    )
    assert client._ticker_cursor == {sym: 0 for sym in client._tickers}, (
        "ticker cursor must zero-init for every loaded ticker symbol"
    )
    # Sanity: fake_tape has SOLUSDT — confirm a non-empty dict was produced.
    assert "SOLUSDT" in client._kline_cursor
    assert "SOLUSDT" in client._ticker_cursor


def test_reset_rewinds_advanced_cursors(fake_tape: Path) -> None:
    """D-04: cursors that have been advanced are rewound to 0 by reset().

    Simulates a test that consumed 7 candles + 3 ticker snapshots and verifies
    the next test starts at fixture position 0.
    """
    client = TapeReplayClient(fake_tape)
    # Simulate cursor advance during a previous "test"
    client._kline_cursor["SOLUSDT"] = 7
    client._ticker_cursor["SOLUSDT"] = 3

    client.reset()

    assert client._kline_cursor["SOLUSDT"] == 0, (
        f"kline cursor must rewind to 0; got {client._kline_cursor['SOLUSDT']}"
    )
    assert client._ticker_cursor["SOLUSDT"] == 0, (
        f"ticker cursor must rewind to 0; got {client._ticker_cursor['SOLUSDT']}"
    )


def test_reset_with_empty_symbol_dicts_does_not_raise(fake_tape: Path) -> None:
    """D-04: reset() must be safe even when no symbols are loaded.

    Edge case: defensive coverage for paths where the loader hasn't yet
    populated symbol dicts. We construct via the normal loader (which
    requires fixtures) and then manually clear the dicts to exercise the
    empty path — direct construction with empty fixture dirs raises
    FileNotFoundError per landmine §6, so we cannot test "empty fixtures"
    via the public ctor.
    """
    client = TapeReplayClient(fake_tape)
    client._klines = {}
    client._tickers = {}

    # Must not raise — empty cursors are a valid steady-state.
    client.reset()

    assert client._kline_cursor == {}
    assert client._ticker_cursor == {}


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
