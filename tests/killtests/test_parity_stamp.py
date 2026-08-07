"""The golden-parity stamp's minting rules — the H4 gate's only guarantee.

These tests never touch `parity_stamp.RUN` (the singleton the conftest hook
reads) and never require the docker stack: every case builds its own
`ParityRun`, and `mint_stamp` is pure.

Regression under test: before 2026-08-07 the stamp was written by a plain
pytest test whose only condition was "some chain action was recorded", so a
session in which a parity assertion FAILED could still mint `passed: true`
and open the H4 gate.
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from killtests.parity_stamp import (  # noqa: E402
    REQUIRED_TESTS,
    ParityRun,
    mint_stamp,
    write_stamp,
)


def _passing_run(tmp_path, actions=None):
    run = ParityRun()
    run.begin(
        symbols=["BTCUSDT", "SOLUSDT", "ADAUSDT"],
        data_dir=str(tmp_path),
        manifest_path=str(tmp_path / "manifest.md"),
    )
    for name in REQUIRED_TESTS:
        run.record_start(name)
        run.record_pass(name)
    for sym, action in (actions or {"BTCUSDT": "BUY", "SOLUSDT": "HOLD"}).items():
        run.record_chain_action(sym, action)
    return run


def test_clean_session_with_non_hold_mints_a_passing_stamp(tmp_path):
    (tmp_path / "manifest.md").write_text("# manifest\n")
    run = _passing_run(tmp_path)
    stamp, reason = mint_stamp(run.state(), session_failures=0, exitstatus=0)
    assert stamp["passed"] is True
    assert stamp["refused_because"] == []
    assert stamp["non_hold_actions"] == ["BUY"]
    assert "BUY" in reason


def test_failing_session_cannot_mint_a_passing_stamp(tmp_path):
    """The load-bearing case: chain actions recorded, then something failed."""
    run = _passing_run(tmp_path)
    stamp, reason = mint_stamp(run.state(), session_failures=1, exitstatus=1)
    assert stamp["passed"] is False
    assert "1 failure(s)/error(s)" in reason


def test_nonzero_exit_status_alone_blocks_the_stamp(tmp_path):
    """Collection errors and interrupts can show up as exitstatus without a
    per-test failure report — either signal is disqualifying on its own."""
    run = _passing_run(tmp_path)
    stamp, _ = mint_stamp(run.state(), session_failures=0, exitstatus=2)
    assert stamp["passed"] is False


@pytest.mark.parametrize("dropped", REQUIRED_TESTS)
def test_stamp_refuses_when_a_required_test_did_not_pass(tmp_path, dropped):
    """A test that fails, errors, or is deselected never records itself, so
    an early-exiting or `-k`-filtered run cannot certify parity either."""
    run = _passing_run(tmp_path)
    run.passed_tests.remove(dropped)
    stamp, reason = mint_stamp(run.state(), session_failures=0, exitstatus=0)
    assert stamp["passed"] is False
    assert dropped in reason


def test_partial_chain_actions_from_an_aborted_loop_do_not_certify(tmp_path):
    """The exact 2026-08-06 defect: symbol 1 appends its action, symbol 2
    mismatches. The loop dies before `record_pass`, so parity is not claimed
    even though a non-HOLD action is on the books."""
    run = ParityRun()
    run.begin(symbols=["BTCUSDT", "SOLUSDT"], data_dir=str(tmp_path))
    for name in REQUIRED_TESTS:
        run.record_start(name)
    run.record_pass("test_candle_window_equality")
    run.record_pass("test_indicator_endpoint_parity")
    run.record_chain_action("BTCUSDT", "BUY")  # symbol 2 asserts and dies here
    stamp, reason = mint_stamp(run.state(), session_failures=1, exitstatus=1)
    assert stamp["passed"] is False
    assert "test_full_chain_parity" in reason


def test_all_hold_writes_nothing(tmp_path):
    run = _passing_run(tmp_path, actions={"BTCUSDT": "HOLD", "SOLUSDT": "HOLD"})
    stamp, reason = mint_stamp(run.state(), session_failures=0, exitstatus=0)
    assert stamp is None
    assert "all-HOLD" in reason


def test_suite_not_run_leaves_the_stamp_alone(tmp_path):
    """An ordinary `pytest tests/killtests/` run (stack down, golden module
    skipped at import) must not be able to write or invalidate a stamp."""
    stamp, reason = mint_stamp(ParityRun().state(), session_failures=3, exitstatus=1)
    assert stamp is None
    assert "did not run" in reason


def test_deselected_golden_module_leaves_the_stamp_alone(tmp_path):
    """`pytest tests/killtests/ -m "not golden"` with the stack UP still
    IMPORTS the golden module during collection, so "armed" is not the same
    as "executed". Only a test that actually started may invalidate a stamp
    — otherwise every unrelated suite run would clobber a genuine pass.
    """
    run = ParityRun()
    run.begin(symbols=["BTCUSDT"], data_dir=str(tmp_path))  # import-time arming
    stamp, reason = mint_stamp(run.state(), session_failures=2, exitstatus=1)
    assert stamp is None
    assert "no parity test executed" in reason


def test_first_test_failing_still_invalidates(tmp_path):
    """The mirror case: a parity test that started and died before recording
    a pass MUST write `passed: false`, not be mistaken for deselection."""
    run = ParityRun()
    run.begin(symbols=["BTCUSDT"], data_dir=str(tmp_path))
    run.record_start("test_candle_window_equality")
    stamp, _ = mint_stamp(run.state(), session_failures=1, exitstatus=1)
    assert stamp is not None
    assert stamp["passed"] is False


def test_stamp_is_self_describing(tmp_path):
    (tmp_path / "manifest.md").write_text("# manifest\n")
    (tmp_path / "BTCUSDT_60m_365d_bybit.csv").write_text("timestamp\n1\n")
    run = _passing_run(tmp_path)
    stamp, _ = mint_stamp(run.state(), session_failures=0, exitstatus=0)
    assert stamp["symbols"] == ["BTCUSDT", "SOLUSDT", "ADAUSDT"]
    assert stamp["data_dir"] == str(tmp_path)
    assert stamp["data_dir_fingerprint"]["files"] == 1
    assert stamp["data_dir_fingerprint"]["sha256"]
    assert len(stamp["backfill_manifest_sha256"]) == 64
    assert stamp["chain_actions"]["BTCUSDT"] == "BUY"
    assert stamp["passed_tests"] == list(REQUIRED_TESTS)


def test_h4_gate_shape_is_preserved(tmp_path):
    """h4_information.py:192 reads exactly these two keys — a schema change
    here silently un-gates or permanently gates H4."""
    run = _passing_run(tmp_path)
    stamp, _ = mint_stamp(
        run.state(), session_failures=0, exitstatus=0, today="20260807"
    )
    assert stamp["date"] == "20260807"
    assert stamp["passed"] is True


def test_write_stamp_roundtrips(tmp_path):
    run = _passing_run(tmp_path)
    stamp, _ = mint_stamp(run.state(), session_failures=0, exitstatus=0)
    path = write_stamp(stamp, str(tmp_path / "nested" / "stamp.json"))
    assert json.loads(Path(path).read_text()) == stamp


def test_failed_stamp_overwrites_an_earlier_passing_one(tmp_path):
    """A pass earlier today then a failure now must close the gate. Writing
    `passed: false` (rather than deleting) closes it just as hard and keeps
    the reason on disk — this is an evidence directory."""
    path = str(tmp_path / "stamp.json")
    good = _passing_run(tmp_path)
    write_stamp(mint_stamp(good.state(), session_failures=0, exitstatus=0)[0], path)
    bad, _ = mint_stamp(good.state(), session_failures=2, exitstatus=1)
    write_stamp(bad, path)
    on_disk = json.loads(Path(path).read_text())
    assert on_disk["passed"] is False
    assert on_disk["refused_because"]
