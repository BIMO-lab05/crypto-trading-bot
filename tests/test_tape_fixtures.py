"""Phase 01-01 gap test: JSONL tape fixture schema and coverage.

Validates the 10 committed fixture files (5 symbols x 2 feeds) against
ROADMAP Phase 1 success criterion 2 and decisions D-03, D-04, D-07, D-15.

No Docker, no imports from services/ — pure filesystem + json parsing.
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TAPE_ROOT = REPO_ROOT / "tests" / "fixtures" / "tape"
KLINES_DIR = TAPE_ROOT / "klines"
TICKER_DIR = TAPE_ROOT / "ticker"

REQUIRED_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"}
EXCLUDED_SYMBOLS = {"XRPUSDT", "DOGEUSDT"}
EXPECTED_TAPE_VERSION = 1


def _load_lines(path: Path):
    """Return all non-empty lines from a JSONL file as parsed dicts/lists."""
    lines = []
    with open(path) as f:
        for raw in f:
            raw = raw.strip()
            if raw:
                lines.append(json.loads(raw))
    return lines


# ---------------------------------------------------------------------------
# D-03: 5 required symbols present in both feeds
# ---------------------------------------------------------------------------


def test_all_five_kline_symbols_present():
    """ROADMAP §2: tape must cover BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, ADAUSDT klines."""
    present = {p.stem for p in KLINES_DIR.glob("*.jsonl")}
    missing = REQUIRED_SYMBOLS - present
    assert not missing, f"Missing kline fixtures for symbols: {missing}"


def test_all_five_ticker_symbols_present():
    """ROADMAP §2: tape must cover the same 5 symbols in ticker feed."""
    present = {p.stem for p in TICKER_DIR.glob("*.jsonl")}
    missing = REQUIRED_SYMBOLS - present
    assert not missing, f"Missing ticker fixtures for symbols: {missing}"


def test_no_excluded_symbols_in_klines():
    """CLAUDE.md: XRP/DOGE excluded by paper-trading data — must not appear in tape."""
    present = {p.stem for p in KLINES_DIR.glob("*.jsonl")}
    intruders = EXCLUDED_SYMBOLS & present
    assert not intruders, f"Excluded symbols found in klines: {intruders}"


def test_no_excluded_symbols_in_ticker():
    """CLAUDE.md: XRP/DOGE excluded by paper-trading data — must not appear in tape."""
    present = {p.stem for p in TICKER_DIR.glob("*.jsonl")}
    intruders = EXCLUDED_SYMBOLS & present
    assert not intruders, f"Excluded symbols found in ticker: {intruders}"


# ---------------------------------------------------------------------------
# D-07: tape_version=1 header on line 1 of every JSONL file
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("symbol", sorted(REQUIRED_SYMBOLS))
def test_kline_file_has_correct_tape_version_header(symbol: str):
    """D-07: line 1 must be JSON header with tape_version == EXPECTED_TAPE_VERSION."""
    path = KLINES_DIR / f"{symbol}.jsonl"
    assert path.exists(), f"Fixture not found: {path}"
    with open(path) as f:
        header = json.loads(f.readline())
    assert "tape_version" in header, f"{symbol} klines header missing 'tape_version'"
    assert header["tape_version"] == EXPECTED_TAPE_VERSION, (
        f"{symbol} klines tape_version={header['tape_version']} != {EXPECTED_TAPE_VERSION}"
    )


@pytest.mark.parametrize("symbol", sorted(REQUIRED_SYMBOLS))
def test_ticker_file_has_correct_tape_version_header(symbol: str):
    """D-07: line 1 must be JSON header with tape_version == EXPECTED_TAPE_VERSION."""
    path = TICKER_DIR / f"{symbol}.jsonl"
    assert path.exists(), f"Fixture not found: {path}"
    with open(path) as f:
        header = json.loads(f.readline())
    assert "tape_version" in header, f"{symbol} ticker header missing 'tape_version'"
    assert header["tape_version"] == EXPECTED_TAPE_VERSION, (
        f"{symbol} ticker tape_version={header['tape_version']} != {EXPECTED_TAPE_VERSION}"
    )


# ---------------------------------------------------------------------------
# D-15: kline data rows — List[str] with 7 elements, >= 2000 rows per symbol
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("symbol", sorted(REQUIRED_SYMBOLS))
def test_kline_file_has_at_least_2000_data_rows(symbol: str):
    """D-04/plan 01-01: 7-day window at 5m cadence = 2016 candles. Minimum 2000 asserted."""
    path = KLINES_DIR / f"{symbol}.jsonl"
    lines = _load_lines(path)
    data_rows = lines[1:]  # skip header
    assert len(data_rows) >= 2000, (
        f"{symbol} klines has {len(data_rows)} rows, expected >= 2000 "
        f"(7-day window at 5m = 2016 candles)"
    )


@pytest.mark.parametrize("symbol", sorted(REQUIRED_SYMBOLS))
def test_kline_rows_are_7_element_lists_of_strings(symbol: str):
    """D-15: Bybit V5 kline shape = List[List[str]], 7 elements [ts,o,h,l,c,v,turnover]."""
    path = KLINES_DIR / f"{symbol}.jsonl"
    lines = _load_lines(path)
    data_rows = lines[1:]
    assert data_rows, f"{symbol} klines has no data rows"
    for i, row in enumerate(data_rows[:10]):  # spot-check first 10
        assert isinstance(row, list), (
            f"{symbol} klines row {i + 1} is {type(row).__name__}, expected list"
        )
        assert len(row) == 7, (
            f"{symbol} klines row {i + 1} has {len(row)} elements, expected 7 "
            f"[ts, open, high, low, close, volume, turnover]"
        )
        for j, val in enumerate(row):
            assert isinstance(val, str), (
                f"{symbol} klines row {i + 1} element {j} is {type(val).__name__}, expected str"
            )


# ---------------------------------------------------------------------------
# Ticker: exactly 1 data row per symbol (snapshot), with 'symbol' key
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("symbol", sorted(REQUIRED_SYMBOLS))
def test_ticker_file_has_exactly_one_data_row(symbol: str):
    """Ticker tape = single snapshot per symbol (line 1 = header, line 2 = snapshot)."""
    path = TICKER_DIR / f"{symbol}.jsonl"
    lines = _load_lines(path)
    data_rows = lines[1:]
    assert len(data_rows) == 1, (
        f"{symbol} ticker has {len(data_rows)} data rows, expected exactly 1"
    )
    assert "symbol" in data_rows[0], (
        f"{symbol} ticker data row missing 'symbol' key: {data_rows[0]}"
    )
    assert data_rows[0]["symbol"] == symbol, (
        f"{symbol} ticker row has symbol={data_rows[0]['symbol']!r}, expected {symbol!r}"
    )


# ---------------------------------------------------------------------------
# Size cap: total tape must be < 50MB (no git-lfs needed per plan 01-01)
# ---------------------------------------------------------------------------


def test_tape_total_size_under_50mb():
    """Plan 01-01: fixtures must fit under 50MB to avoid mandatory git-lfs."""
    total_bytes = sum(p.stat().st_size for p in TAPE_ROOT.rglob("*.jsonl"))
    total_mb = total_bytes / (1024 * 1024)
    assert total_mb < 50, (
        f"Tape fixtures {total_mb:.1f}MB exceeds 50MB cap — git-lfs required"
    )


# ---------------------------------------------------------------------------
# Header metadata: source must be 'bybit-mainnet' (not testnet)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("symbol", sorted(REQUIRED_SYMBOLS))
def test_kline_header_source_is_mainnet(symbol: str):
    """CLAUDE.md: market data from Bybit mainnet, not testnet."""
    path = KLINES_DIR / f"{symbol}.jsonl"
    with open(path) as f:
        header = json.loads(f.readline())
    assert header.get("source") == "bybit-mainnet", (
        f"{symbol} klines header source={header.get('source')!r}, expected 'bybit-mainnet'"
    )
