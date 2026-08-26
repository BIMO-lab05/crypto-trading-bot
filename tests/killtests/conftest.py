import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from kt_shared import _write_candles  # noqa: E402,F401


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
