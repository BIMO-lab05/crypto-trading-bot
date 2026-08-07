import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))


def _write_candles(tmp_path, symbol, interval, n, start):
    freq = {"15": "15min", "60": "60min", "240": "240min", "1440": "D"}[interval]
    ts = pd.date_range(start, periods=n, freq=freq)
    rng = np.random.default_rng(42)
    closes = 100 + np.cumsum(rng.normal(0, 0.5, n))
    df = pd.DataFrame(
        {
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "interval": interval,
            "open": closes,
            "high": closes + 0.6,
            "low": closes - 0.6,
            "close": closes,
            "volume": 10.0,
            "turnover": 1000.0,
            "is_mainnet": True,
            "created_at": 1,
        }
    )
    df.to_csv(tmp_path / f"{symbol}_{interval}m_365d_bybit.csv", index=False)


@pytest.fixture
def write_candles():
    return _write_candles


def pytest_sessionfinish(session, exitstatus):
    """Mint the golden-parity stamp — the ONLY place it is ever written.

    It lives here rather than in `test_golden_parity.py` for two reasons:
    pytest collects hook implementations from conftest files, not from test
    modules; and the session-wide failure count (which is the whole point —
    a failing parity run must not be able to mint a passing stamp) is only
    available once every test has reported.

    Guarded twice so an ordinary `pytest tests/killtests/` run can never
    touch the stamp: the golden module sets `RUN.suite_ran` at import, and
    that import only happens after its live-stack probe passes.

    Note the conservative edge: if the golden suite runs as part of a WIDER
    pytest invocation, an unrelated failure elsewhere in that session also
    produces `passed: false`. Run the stamp command on its own (see
    backtesting/killtests/README.md).
    """
    from killtests import parity_stamp

    if not parity_stamp.RUN.suite_ran:
        return
    if not any(m.endswith("test_golden_parity") for m in sys.modules):
        return

    stamp, reason = parity_stamp.mint_stamp(
        parity_stamp.RUN.state(),
        session_failures=session.testsfailed,
        exitstatus=int(exitstatus),
    )
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")

    def _say(line):
        if reporter is not None:
            reporter.write_line(line)
        else:
            print(line)

    if stamp is None:
        _say(f"GOLDEN PARITY: stamp not written — {reason}")
        return
    path = parity_stamp.write_stamp(stamp)
    verdict = "PASSED" if stamp["passed"] else "FAILED"
    _say(f"GOLDEN PARITY {verdict}: stamp written to {path} — {reason}")
