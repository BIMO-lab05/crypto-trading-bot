"""Staleness tripwire for the daily evidence tick."""

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = "scripts/check_evidence_staleness.py"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPT_ABS = REPO_ROOT / SCRIPT
DEFAULT_MARKER = REPO_ROOT / ".planning/state/evidence_loop_last_tick.json"


def _run(marker_path):
    return subprocess.run(
        [sys.executable, SCRIPT, "--marker", str(marker_path)],
        capture_output=True,
        text=True,
    )


def _run_from_cwd(cwd, marker_arg=None):
    """Run script from a specific cwd, optionally with --marker argument."""
    cmd = [sys.executable, str(SCRIPT_ABS)]
    if marker_arg:
        cmd.extend(["--marker", marker_arg])
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)


def test_missing_marker_exits_1(tmp_path):
    r = _run(tmp_path / "absent.json")
    assert r.returncode == 1
    assert "missing" in (r.stdout + r.stderr).lower()


def test_fresh_marker_exits_0(tmp_path):
    m = tmp_path / "m.json"
    m.write_text(
        json.dumps(
            {
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "exit_code": 0,
            }
        )
    )
    r = _run(m)
    assert r.returncode == 0


def test_stale_marker_exits_1(tmp_path):
    m = tmp_path / "m.json"
    stale = datetime.now(timezone.utc) - timedelta(hours=49)
    m.write_text(json.dumps({"ts_utc": stale.isoformat(), "exit_code": 0}))
    r = _run(m)
    assert r.returncode == 1
    assert "stale" in (r.stdout + r.stderr).lower()


def test_default_marker_repo_anchored():
    """Verify script finds default marker at repo root even when run from /tmp."""
    # Write a fresh marker at the real repo location
    DEFAULT_MARKER.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_MARKER.write_text(
        json.dumps(
            {
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "exit_code": 0,
            }
        )
    )
    try:
        # Run from /tmp with NO --marker argument (uses default)
        r = _run_from_cwd("/tmp", marker_arg=None)
        assert r.returncode == 0, f"Failed: {r.stdout}\n{r.stderr}"
        # Verify it found the repo-anchored marker
        assert "last tick:" in r.stdout
    finally:
        # Clean up the marker file
        if DEFAULT_MARKER.exists():
            DEFAULT_MARKER.unlink()
