"""RED tests for Task 2: Live launch, evidence schema, publish-evidence, runbook.

All tests in this file FAIL until Task 2 implementation is in place.

Tests
-----
Test 0  — PAPER_TRADING_MODE precondition: live launch refuses when env says LIVE.
Test 1  — Live launch docker compose argv is plain (no -e); env overrides ride
          the subprocess environment instead.
Test 2  — Evidence path directory + meta.json created before docker invocation.
Test 3  — README.md documents run.json schema and operator workflow.
Test 4  — publish-evidence subcommand validates presence of run.json + psr_ci.json
          and psr_ci_low > 0.0; writes PSR_CI_PUBLISHED marker; refuses without
          --force when CI brackets zero; --force writes force_override.txt.
Test 5  — docs/runbooks/forward-paper-test.md exists, is ≥60 lines, and contains
          required section headings.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_MODULE = "scripts.forward_paper_test.run_isolation"
_RUN_ISOLATION = [sys.executable, "-m", _MODULE]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_valid_meta(tmp_path: Path, flag: str = "enable_vol_targeting") -> dict:
    """Return a meta.json dict that passes all validations."""
    return {
        "flag": flag,
        "run_id": "20260101T000000Z",
        "planned_start_utc": "2026-01-01T00:00:00+00:00",
        "planned_end_utc": "2026-01-08T00:00:00+00:00",
        "duration_days": 7,
        "git_sha": "abc1234",
        "baseline_env_overrides": {
            "ENABLE_VOL_TARGETING": "false",
            "PREFER_MAKER_ORDERS": "false",
            "ENABLE_FUNDING_GATE": "false",
        },
        "flag_env_overrides": {
            "ENABLE_VOL_TARGETING": "true",
            "PREFER_MAKER_ORDERS": "false",
            "ENABLE_FUNDING_GATE": "false",
        },
        "paper_trade_log_path": str(tmp_path / "paper_trade.log"),
    }


def _write_evidence_dir(
    tmp_path: Path,
    flag: str = "enable_vol_targeting",
    *,
    psr_ci_low: float = 0.05,
    include_run_json: bool = True,
    include_psr_ci_json: bool = True,
    include_meta_json: bool = True,
) -> Path:
    """Write a complete evidence directory for publish-evidence tests."""
    ev_dir = tmp_path / "evidence" / flag / "20260101T000000Z"
    ev_dir.mkdir(parents=True)

    if include_meta_json:
        meta = _make_valid_meta(tmp_path, flag)
        (ev_dir / "meta.json").write_text(json.dumps(meta))

    if include_run_json:
        run_json = {
            "run_id": "20260101T000000Z",
            "flag": flag,
            "started_at_utc": "2026-01-01T00:00:00+00:00",
            "completed_at_utc": "2026-01-08T00:00:00+00:00",
            "returns": [0.001, 0.002, -0.0005, 0.003] * 25,  # 100 trade returns
            "trades": [],
            "notes": "",
            "git_sha": "abc1234",
        }
        (ev_dir / "run.json").write_text(json.dumps(run_json))

    if include_psr_ci_json:
        psr_ci_json = {
            "psr_point": 0.72,
            "psr_ci_low": psr_ci_low,
            "psr_ci_high": 0.91,
            "n_resamples": 1000,
            "n_resamples_valid": 998,
            "block_size": 10,
            "seed": 42,
            "n_bars": 100,
        }
        (ev_dir / "psr_ci.json").write_text(json.dumps(psr_ci_json))

    return ev_dir


# ---------------------------------------------------------------------------
# Test 0: PAPER_TRADING_MODE precondition
# ---------------------------------------------------------------------------


def test_live_launch_refuses_when_trading_mode_live(tmp_path: Path, monkeypatch):
    """Test 0: live launch exits non-zero when TRADING_MODE=LIVE in env."""
    # Import the run_isolation module and call run_isolation() with
    # TRADING_MODE=LIVE injected via monkeypatch.
    monkeypatch.setenv("TRADING_MODE", "LIVE")
    monkeypatch.setenv("PAPER_TRADING_MODE", "true")

    sys.path.insert(0, str(_REPO))
    from scripts.forward_paper_test.run_isolation import run_isolation

    with pytest.raises((SystemExit, RuntimeError, ValueError)) as exc_info:
        run_isolation(
            flag="enable_vol_targeting",
            duration_days=7,
            run_id="test_run",
            paper_trade_log=None,
            dry_run=False,
            subprocess_runner=lambda argv, **kw: None,  # won't be reached
        )

    # Should exit non-zero or raise with a meaningful message
    exc = exc_info.value
    if isinstance(exc, SystemExit):
        assert exc.code != 0, "Should exit non-zero for TRADING_MODE=LIVE"


def test_live_launch_refuses_when_paper_trading_mode_false(tmp_path: Path, monkeypatch):
    """Test 0b: live launch exits non-zero when PAPER_TRADING_MODE=false."""
    monkeypatch.delenv("TRADING_MODE", raising=False)
    monkeypatch.setenv("PAPER_TRADING_MODE", "false")

    sys.path.insert(0, str(_REPO))
    from scripts.forward_paper_test.run_isolation import run_isolation

    with pytest.raises((SystemExit, RuntimeError, ValueError)) as exc_info:
        run_isolation(
            flag="enable_vol_targeting",
            duration_days=7,
            run_id="test_run_b",
            paper_trade_log=None,
            dry_run=False,
            subprocess_runner=lambda argv, **kw: None,
        )

    exc = exc_info.value
    if isinstance(exc, SystemExit):
        assert exc.code != 0


# ---------------------------------------------------------------------------
# Test 1: Live launch docker compose argv
# ---------------------------------------------------------------------------


def test_live_launch_argv_contains_correct_env_overrides(tmp_path: Path, monkeypatch):
    """Test 1: live launch builds a plain docker compose argv (no -e — that
    flag does not exist on `docker compose up`); env overrides ride the
    subprocess environment instead.

    Corrected 2026-08-20 (Task 10): this test previously asserted the old
    broken `-e KEY=VALUE` argv shape, which pinned a defect that made the
    launcher unable to invoke docker at all (`docker compose up` has no -e
    flag). Updated to the real contract.
    """
    monkeypatch.delenv("TRADING_MODE", raising=False)
    monkeypatch.setenv("PAPER_TRADING_MODE", "true")

    captured_argv: list = []
    captured_env: dict = {}

    def fake_runner(argv, **kw):
        captured_argv.extend(argv)
        captured_env.update(kw.get("env") or {})
        return subprocess.CompletedProcess(argv, returncode=0)

    sys.path.insert(0, str(_REPO))
    from scripts.forward_paper_test import run_isolation as ri_module

    # Override evidence base to tmp_path so mkdir doesn't fail in real repo
    monkeypatch.setattr(ri_module, "_EVIDENCE_BASE", tmp_path / "evidence")

    from scripts.forward_paper_test.run_isolation import run_isolation

    run_isolation(
        flag="enable_vol_targeting",
        duration_days=7,
        run_id="test_argv",
        paper_trade_log=None,
        dry_run=False,
        subprocess_runner=fake_runner,
    )

    # Must use the unified compose file
    assert "-f" in captured_argv
    compose_file_idx = captured_argv.index("-f")
    assert "docker-compose.unified.yml" in captured_argv[compose_file_idx + 1], (
        f"Expected docker-compose.unified.yml in argv, got: {captured_argv}"
    )

    # Must reference trading-engine service as the final argv element
    assert captured_argv[-1] == "trading-engine", (
        f"trading-engine not the final argv element: {captured_argv}"
    )

    # docker compose up has no -e flag — must NOT appear in argv
    assert "-e" not in captured_argv, f"-e must not appear in argv: {captured_argv}"

    # Flag env overrides must ride the subprocess environment instead
    assert captured_env["ENABLE_VOL_TARGETING"] == "true"
    # Other flags must be explicitly set to false (isolation guarantee)
    assert captured_env["PREFER_MAKER_ORDERS"] == "false"
    assert captured_env["ENABLE_FUNDING_GATE"] == "false"
    # Sanity: the rest of the operator environment is preserved (os.environ
    # merged in), not replaced outright.
    assert "PATH" in captured_env


def test_launcher_passes_overrides_via_env_not_argv(tmp_path: Path, monkeypatch):
    """Task 10: docker compose up has no -e flag; overrides must ride the
    subprocess env, not argv. Regression test for the launcher defect that
    made every isolation run fail to launch since it shipped.
    """
    monkeypatch.delenv("TRADING_MODE", raising=False)
    monkeypatch.setenv("PAPER_TRADING_MODE", "true")

    captured = {}

    def fake_runner(argv, cwd=None, env=None):
        captured["argv"] = argv
        captured["env"] = env
        return subprocess.CompletedProcess(argv, returncode=0)

    sys.path.insert(0, str(_REPO))
    from scripts.forward_paper_test import run_isolation as ri_module
    from scripts.forward_paper_test.run_isolation import run_isolation

    # Override evidence base to tmp_path so mkdir doesn't fail in real repo
    monkeypatch.setattr(ri_module, "_EVIDENCE_BASE", tmp_path / "evidence")

    run_isolation(
        flag="prefer_maker_orders",
        duration_days=7,
        run_id="test-run",
        paper_trade_log=None,
        dry_run=False,
        subprocess_runner=fake_runner,
    )

    assert "-e" not in captured["argv"]
    assert captured["argv"][-1] == "trading-engine"
    assert captured["env"]["PREFER_MAKER_ORDERS"] == "true"
    assert captured["env"]["ENABLE_VOL_TARGETING"] == "false"
    assert captured["env"]["ENABLE_FUNDING_GATE"] == "false"
    # sanity: the rest of the operator environment is preserved
    assert "PATH" in captured["env"]


# ---------------------------------------------------------------------------
# Test 2: Evidence path and meta.json
# ---------------------------------------------------------------------------


def test_live_launch_creates_evidence_dir_and_meta_json(tmp_path: Path, monkeypatch):
    """Test 2: live launch creates evidence dir + meta.json before docker call."""
    monkeypatch.delenv("TRADING_MODE", raising=False)
    monkeypatch.setenv("PAPER_TRADING_MODE", "true")

    call_order: list[str] = []

    def fake_runner(argv, **kw):
        call_order.append("docker")
        return subprocess.CompletedProcess(argv, returncode=0)

    sys.path.insert(0, str(_REPO))
    from scripts.forward_paper_test import run_isolation as ri_module

    evidence_base = tmp_path / "evidence"
    monkeypatch.setattr(ri_module, "_EVIDENCE_BASE", evidence_base)

    from scripts.forward_paper_test.run_isolation import run_isolation

    def checking_runner(argv, **kw):
        # At the time docker is called, evidence dir must already exist
        ev_dir = evidence_base / "enable_vol_targeting" / "test_meta_run"
        assert ev_dir.exists(), f"Evidence dir not created before docker: {ev_dir}"
        meta_path = ev_dir / "meta.json"
        assert meta_path.exists(), f"meta.json not created before docker: {meta_path}"
        call_order.append("docker")
        return subprocess.CompletedProcess(argv, returncode=0)

    run_isolation(
        flag="enable_vol_targeting",
        duration_days=7,
        run_id="test_meta_run",
        paper_trade_log="/tmp/paper.log",
        dry_run=False,
        subprocess_runner=checking_runner,
    )

    assert "docker" in call_order, "Docker was never called"

    # Verify meta.json structure
    meta_path = evidence_base / "enable_vol_targeting" / "test_meta_run" / "meta.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())

    required_keys = {
        "flag",
        "run_id",
        "planned_start_utc",
        "planned_end_utc",
        "duration_days",
        "git_sha",
        "baseline_env_overrides",
        "flag_env_overrides",
        "paper_trade_log_path",
    }
    missing = required_keys - set(meta.keys())
    assert not missing, f"meta.json missing keys: {missing}"

    assert meta["flag"] == "enable_vol_targeting"
    assert meta["run_id"] == "test_meta_run"
    assert meta["duration_days"] == 7
    assert meta["paper_trade_log_path"] == "/tmp/paper.log"
    assert meta["flag_env_overrides"]["ENABLE_VOL_TARGETING"] == "true"


# ---------------------------------------------------------------------------
# Test 3: README documents run.json schema
# ---------------------------------------------------------------------------


def test_readme_documents_run_json_schema():
    """Test 3: README.md documents run.json schema and operator workflow."""
    readme_path = _REPO / "scripts" / "forward_paper_test" / "README.md"
    assert readme_path.exists(), f"README.md not found at {readme_path}"

    content = readme_path.read_text()

    # Required schema fields documented
    for field in [
        "run_id",
        "flag",
        "started_at_utc",
        "completed_at_utc",
        "returns",
        "trades",
        "notes",
        "git_sha",
    ]:
        assert field in content, f"README.md missing run.json field: {field}"

    # Must mention the complete_run step
    assert "complete_run" in content or "complete-run" in content, (
        "README.md must document the complete_run operator step"
    )


# ---------------------------------------------------------------------------
# Test 4: publish-evidence subcommand
# ---------------------------------------------------------------------------


def test_publish_evidence_writes_marker_on_valid_evidence(tmp_path: Path):
    """Test 4a: publish-evidence writes PSR_CI_PUBLISHED marker when evidence is valid."""
    ev_dir = _write_evidence_dir(tmp_path, psr_ci_low=0.05)

    result = subprocess.run(
        _RUN_ISOLATION + ["publish-evidence", str(ev_dir)],
        capture_output=True,
        text=True,
        cwd=str(_REPO),
    )
    assert result.returncode == 0, (
        f"publish-evidence failed unexpectedly:\n{result.stdout}\n{result.stderr}"
    )
    marker = ev_dir / "PSR_CI_PUBLISHED"
    assert marker.exists(), f"PSR_CI_PUBLISHED marker not written to {ev_dir}"


def test_publish_evidence_refuses_when_psr_ci_low_lte_zero(tmp_path: Path):
    """Test 4b: publish-evidence refuses (non-zero exit) when psr_ci_low <= 0.0."""
    ev_dir = _write_evidence_dir(tmp_path, psr_ci_low=-0.10)

    result = subprocess.run(
        _RUN_ISOLATION + ["publish-evidence", str(ev_dir)],
        capture_output=True,
        text=True,
        cwd=str(_REPO),
    )
    assert result.returncode != 0, "publish-evidence should exit non-zero when psr_ci_low <= 0.0"
    marker = ev_dir / "PSR_CI_PUBLISHED"
    assert not marker.exists(), "Marker should NOT be written when CI brackets zero"


def test_publish_evidence_force_flag_bypasses_ci_guard(tmp_path: Path):
    """Test 4c: publish-evidence --force writes marker and force_override.txt."""
    ev_dir = _write_evidence_dir(tmp_path, psr_ci_low=-0.10)

    result = subprocess.run(
        _RUN_ISOLATION + ["publish-evidence", str(ev_dir), "--force"],
        capture_output=True,
        text=True,
        cwd=str(_REPO),
    )
    assert result.returncode == 0, (
        f"publish-evidence --force failed:\n{result.stdout}\n{result.stderr}"
    )
    marker = ev_dir / "PSR_CI_PUBLISHED"
    assert marker.exists(), "Marker not written even with --force"

    force_log = ev_dir / "force_override.txt"
    assert force_log.exists(), "force_override.txt not written by --force"


def test_publish_evidence_refuses_when_run_json_missing(tmp_path: Path):
    """Test 4d: publish-evidence refuses when run.json is missing."""
    ev_dir = _write_evidence_dir(tmp_path, include_run_json=False)

    result = subprocess.run(
        _RUN_ISOLATION + ["publish-evidence", str(ev_dir)],
        capture_output=True,
        text=True,
        cwd=str(_REPO),
    )
    assert result.returncode != 0, "publish-evidence should refuse when run.json is missing"
    assert not (ev_dir / "PSR_CI_PUBLISHED").exists()


def test_publish_evidence_refuses_when_psr_ci_json_missing(tmp_path: Path):
    """Test 4e: publish-evidence refuses when psr_ci.json is missing."""
    ev_dir = _write_evidence_dir(tmp_path, include_psr_ci_json=False)

    result = subprocess.run(
        _RUN_ISOLATION + ["publish-evidence", str(ev_dir)],
        capture_output=True,
        text=True,
        cwd=str(_REPO),
    )
    assert result.returncode != 0, "publish-evidence should refuse when psr_ci.json is missing"
    assert not (ev_dir / "PSR_CI_PUBLISHED").exists()


# ---------------------------------------------------------------------------
# Test 5: Runbook presence and structure
# ---------------------------------------------------------------------------


def test_runbook_exists_and_is_at_least_60_lines():
    """Test 5a: docs/runbooks/forward-paper-test.md exists and is ≥60 lines."""
    runbook = _REPO / "docs" / "runbooks" / "forward-paper-test.md"
    assert runbook.exists(), f"Runbook not found at {runbook}"

    lines = runbook.read_text().splitlines()
    assert len(lines) >= 60, f"Runbook is only {len(lines)} lines; need ≥60"


def test_runbook_contains_required_sections():
    """Test 5b: Runbook contains all seven required section headings."""
    runbook = _REPO / "docs" / "runbooks" / "forward-paper-test.md"
    assert runbook.exists(), f"Runbook not found at {runbook}"

    content = runbook.read_text().lower()

    required_sections = [
        "goal",
        "prerequisites",
        "step 1",
        "step 2",
        "step 3",
        "default-on gate",
        "troubleshooting",
    ]
    for section in required_sections:
        assert section in content, f"Runbook missing section heading: '{section}'"


# ---------------------------------------------------------------------------
# Test 6: complete-run subcommand (Task 11)
# ---------------------------------------------------------------------------
#
# meta.json keys below match the REAL _write_meta_json output (verified by
# reading run_isolation.py before writing these tests), not the brief's
# sketch: the launch timestamp key is "planned_start_utc", not
# "launched_at_utc".


def test_complete_run_writes_run_json(tmp_path, monkeypatch):
    """complete-run derives per-trade returns from closed positions and writes run.json."""
    import scripts.forward_paper_test.run_isolation as ri

    ev = tmp_path / "prefer_maker_orders" / "r1"
    ev.mkdir(parents=True)
    (ev / "meta.json").write_text(
        json.dumps(
            {
                "flag": "prefer_maker_orders",
                "run_id": "r1",
                "planned_start_utc": "2026-08-20T12:00:00+00:00",
                "planned_end_utc": "2026-08-27T12:00:00+00:00",
                "duration_days": 7,
                "git_sha": "abc1234",
                "baseline_env_overrides": {},
                "flag_env_overrides": {},
                "paper_trade_log_path": "",
            }
        )
    )

    rows = [
        # (symbol, side, entry_price, quantity, realized_pnl, opened_at, closed_at)
        (
            "SOLUSDT",
            "LONG",
            "180.0",
            "0.05",
            "0.25",
            "2026-08-21T01:00:00+00:00",
            "2026-08-22T01:00:00+00:00",
        ),
        (
            "BNBUSDT",
            "LONG",
            "700.0",
            "0.012",
            "-0.03",
            "2026-08-21T02:00:00+00:00",
            "2026-08-23T02:00:00+00:00",
        ),
    ]
    monkeypatch.setattr(ri, "_fetch_closed_positions", lambda since_iso: rows)

    rc = ri.complete_run(ev)
    assert rc == 0
    data = json.loads((ev / "run.json").read_text())
    assert len(data["returns"]) == 2
    assert abs(data["returns"][0] - 0.25 / (180.0 * 0.05)) < 1e-12
    assert abs(data["returns"][1] - (-0.03) / (700.0 * 0.012)) < 1e-12
    assert data["n_positions"] == 2
    assert data["run_id"] == "r1"
    assert data["flag"] == "prefer_maker_orders"


def test_complete_run_refuses_empty_window(tmp_path, monkeypatch):
    """complete-run refuses to write an empty run.json (would poison psr_ci)."""
    import scripts.forward_paper_test.run_isolation as ri

    ev = tmp_path / "prefer_maker_orders" / "r2"
    ev.mkdir(parents=True)
    (ev / "meta.json").write_text(
        json.dumps(
            {
                "flag": "prefer_maker_orders",
                "run_id": "r2",
                "planned_start_utc": "2026-08-20T12:00:00+00:00",
                "planned_end_utc": "2026-08-27T12:00:00+00:00",
                "duration_days": 7,
                "git_sha": "abc1234",
                "baseline_env_overrides": {},
                "flag_env_overrides": {},
                "paper_trade_log_path": "",
            }
        )
    )
    monkeypatch.setattr(ri, "_fetch_closed_positions", lambda since_iso: [])

    rc = ri.complete_run(ev)
    assert rc != 0
    assert not (ev / "run.json").exists()


def test_complete_run_rejects_garbage_iso_timestamp(tmp_path):
    """The ISO-parse guard in _fetch_closed_positions must reject an
    unparseable planned_start_utc BEFORE any SQL string is built — this is
    the injection-surface guard called out in the task brief; it must never
    be skipped. complete_run does not wrap the call in try/except, so the
    ValueError from datetime.fromisoformat propagates uncaught (documented
    contract: raised ValueError, not a routed clean-exit path). Deliberately
    does NOT monkeypatch _fetch_closed_positions, so the real ISO-parse
    guard runs; if it were skipped, this test would instead see a
    subprocess/docker failure (no docker available in CI) rather than
    ValueError, which would also fail the assertion below.
    """
    import scripts.forward_paper_test.run_isolation as ri

    ev = tmp_path / "prefer_maker_orders" / "r3"
    ev.mkdir(parents=True)
    (ev / "meta.json").write_text(
        json.dumps(
            {
                "flag": "prefer_maker_orders",
                "run_id": "r3",
                "planned_start_utc": "2026-13-99 nonsense'; DROP TABLE positions;--",
                "planned_end_utc": "2026-08-27T12:00:00+00:00",
                "duration_days": 7,
                "git_sha": "abc1234",
                "baseline_env_overrides": {},
                "flag_env_overrides": {},
                "paper_trade_log_path": "",
            }
        )
    )

    with pytest.raises(ValueError):
        ri.complete_run(ev)

    assert not (ev / "run.json").exists()


def test_fetch_closed_positions_parses_psql_output_and_builds_argv(monkeypatch):
    """Direct test of _fetch_closed_positions (not routed through
    complete_run): monkeypatches subprocess.run itself — NOT
    _fetch_closed_positions — with canned pipe-delimited psql stdout, so
    this pins two contracts at once: (1) the 7-field split('|') parsing of
    psql's -t -A -F| output into tuples, and (2) the docker-exec argv shape
    (container name, clean_epoch_positions view, psql flags) actually sent
    to subprocess.run.
    """
    import scripts.forward_paper_test.run_isolation as ri

    canned_stdout = (
        "SOLUSDT|LONG|180.00000000|0.05000000|0.25105825|"
        "2026-08-21 01:00:00|2026-08-22 01:00:00\n"
        "BNBUSDT|LONG|700.00000000|0.01200000|-0.03047842|"
        "2026-08-21 02:00:00|2026-08-23 02:00:00\n"
    )

    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, returncode=0, stdout=canned_stdout, stderr="")

    monkeypatch.setattr(ri.subprocess, "run", fake_run)

    rows = ri._fetch_closed_positions("2026-08-20T12:00:00+00:00")

    assert rows == [
        (
            "SOLUSDT",
            "LONG",
            "180.00000000",
            "0.05000000",
            "0.25105825",
            "2026-08-21 01:00:00",
            "2026-08-22 01:00:00",
        ),
        (
            "BNBUSDT",
            "LONG",
            "700.00000000",
            "0.01200000",
            "-0.03047842",
            "2026-08-21 02:00:00",
            "2026-08-23 02:00:00",
        ),
    ]

    argv = captured["argv"]
    assert argv[:2] == ["docker", "exec"]
    assert "crypto-bot-postgres" in argv
    assert "psql" in argv
    assert "-t" in argv
    assert "-A" in argv
    f_idx = argv.index("-F")
    assert argv[f_idx + 1] == "|"
    sql = argv[argv.index("-c") + 1]
    assert "clean_epoch_positions" in sql
    assert "status = 'CLOSED'" in sql
    assert "2026-08-20T12:00:00+00:00" in sql
    # subprocess.run was invoked with check=True (surfaces psql failures loudly)
    assert captured["kwargs"].get("check") is True
