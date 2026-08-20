"""Staleness tripwire for the daily evidence tick."""

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

SCRIPT = "scripts/check_evidence_staleness.py"


def _run(marker_path):
    return subprocess.run(
        [sys.executable, SCRIPT, "--marker", str(marker_path)],
        capture_output=True,
        text=True,
    )


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
