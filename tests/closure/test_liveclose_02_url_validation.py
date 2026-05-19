"""Unit tests for scripts/closure/liveclose-02-record-ci.sh URL-validation harness.

Phase 11.1 Plan 03 (Wave 2). Covers the LIVECLOSE-02 CI-URL recorder harness:
valid integration-ml-on.yml URLs are accepted, six rejection branches are
enforced, and the helper writes both ci-url.txt and a schema-valid evidence
JSON file. All tests pass ``--skip-gh-api`` so no network calls reach GitHub;
the ``gh api`` branch is exercised by integration tests outside this file.

Plan: .planning/phases/11.1-carry-in-closure-harnesses-liveclose-01-05/11.1-03-PLAN.md
Harness: scripts/closure/liveclose-02-record-ci.sh
Schema:  .planning/evidence/_schema.json
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

# ---------------------------------------------------------------------------
# Module-level paths — resolved against the repo root that owns this test
# file (two parents up from tests/closure/). Mirrors scripts/closure/_common
# resolution idiom so the test is invariant to pytest's cwd.
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parents[2]
_HARNESS = _REPO / "scripts" / "closure" / "liveclose-02-record-ci.sh"
_SCHEMA_PATH = _REPO / ".planning" / "evidence" / "_schema.json"

# Canonical valid run URL for the project's integration-ml-on.yml workflow.
_VALID_URL = (
    "https://github.com/MohammedSiradj/crypto-trading-bot/actions/runs/9999999999"
)

# Tests are bash-driven; skip on platforms without a POSIX shell.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="LIVECLOSE-02 harness is a bash script; Windows native shells skip.",
)


def _run_harness(
    *args: str,
    env_overrides: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> subprocess.CompletedProcess:
    """Invoke the bash harness with the supplied args.

    A clean env is used (no ``TRADING_MODE`` inherited from the caller); each
    test that needs ``TRADING_MODE=LIVE`` sets it explicitly via
    ``env_overrides``.
    """
    env = {
        # Minimal env so the harness can locate python and bash.
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "PYTHONPATH": str(_REPO),
    }
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        ["bash", str(_HARNESS), *args],
        env=env,
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _read_evidence(target_path: Path) -> dict:
    """Load and return the parsed evidence JSON."""
    return json.loads(target_path.read_text())


def _load_schema() -> dict:
    """Load the LIVECLOSE evidence schema as a dict."""
    return json.loads(_SCHEMA_PATH.read_text())


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_integration_ml_on_url(tmp_path: Path):
    """Valid integration-ml-on.yml URL with --skip-gh-api exits 0 and emits evidence."""
    target = tmp_path / "evidence.json"
    ci_url_txt = tmp_path / "ci-url.txt"

    res = _run_harness(
        "--url",
        _VALID_URL,
        "--skip-gh-api",
        "--target-path",
        str(target),
        "--ci-url-txt-path",
        str(ci_url_txt),
    )

    assert res.returncode == 0, (
        f"harness exited {res.returncode}\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    )
    assert ci_url_txt.exists(), "ci-url.txt should be written on success"
    assert ci_url_txt.read_text().strip() == _VALID_URL
    assert target.exists(), "evidence JSON should be written on success"
    payload = _read_evidence(target)
    jsonschema.validate(payload, _load_schema())
    assert payload["liveclose_id"] == "LIVECLOSE-02"
    assert payload["status"] == "AWAITING_HUMAN"
    assert payload["human_needed"] is True
    assert payload["extra"]["run_id"] == 9999999999
    assert payload["extra"]["ci_url"] == _VALID_URL
    assert payload["extra"]["owner_repo"] == "MohammedSiradj/crypto-trading-bot"


# ---------------------------------------------------------------------------
# Rejection branches (regex enforcement runs even with --skip-gh-api)
# ---------------------------------------------------------------------------


def test_url_format_invalid_non_github(tmp_path: Path):
    """Non-github.com URL is rejected with URL_FORMAT_INVALID (exit 2)."""
    res = _run_harness(
        "--url",
        "https://example.com/foo/bar/actions/runs/1",
        "--skip-gh-api",
        "--target-path",
        str(tmp_path / "ev.json"),
        "--ci-url-txt-path",
        str(tmp_path / "ci.txt"),
    )
    assert res.returncode == 2, (
        f"expected exit 2, got {res.returncode}\nstderr: {res.stderr}"
    )
    assert "URL_FORMAT_INVALID" in res.stderr
    assert not (tmp_path / "ev.json").exists(), (
        "no evidence should be written on format failure"
    )


def test_url_format_invalid_missing_run_id(tmp_path: Path):
    """URL ending in /runs/ with no run_id is rejected (exit 2)."""
    res = _run_harness(
        "--url",
        "https://github.com/x/y/actions/runs/",
        "--skip-gh-api",
        "--target-path",
        str(tmp_path / "ev.json"),
        "--ci-url-txt-path",
        str(tmp_path / "ci.txt"),
    )
    assert res.returncode == 2
    assert "URL_FORMAT_INVALID" in res.stderr


def test_url_format_invalid_non_numeric_run_id(tmp_path: Path):
    """URL with non-numeric run_id segment is rejected (exit 2)."""
    res = _run_harness(
        "--url",
        "https://github.com/x/y/actions/runs/abc",
        "--skip-gh-api",
        "--target-path",
        str(tmp_path / "ev.json"),
        "--ci-url-txt-path",
        str(tmp_path / "ci.txt"),
    )
    assert res.returncode == 2
    assert "URL_FORMAT_INVALID" in res.stderr


def test_url_format_accepts_with_query_string(tmp_path: Path):
    """URL with ?check_suite_focus=true query string still passes regex."""
    url = (
        "https://github.com/MohammedSiradj/crypto-trading-bot/"
        "actions/runs/9999999999?check_suite_focus=true"
    )
    target = tmp_path / "ev.json"
    res = _run_harness(
        "--url",
        url,
        "--skip-gh-api",
        "--target-path",
        str(target),
        "--ci-url-txt-path",
        str(tmp_path / "ci.txt"),
    )
    assert res.returncode == 0, f"stderr:\n{res.stderr}"
    payload = _read_evidence(target)
    assert payload["extra"]["run_id"] == 9999999999


def test_url_format_accepts_with_subpath(tmp_path: Path):
    """URL with /job/<id> subpath still passes regex."""
    url = (
        "https://github.com/MohammedSiradj/crypto-trading-bot/"
        "actions/runs/9999999999/job/12345"
    )
    target = tmp_path / "ev.json"
    res = _run_harness(
        "--url",
        url,
        "--skip-gh-api",
        "--target-path",
        str(target),
        "--ci-url-txt-path",
        str(tmp_path / "ci.txt"),
    )
    assert res.returncode == 0, f"stderr:\n{res.stderr}"
    payload = _read_evidence(target)
    assert payload["extra"]["run_id"] == 9999999999


# ---------------------------------------------------------------------------
# Paper-only refusal
# ---------------------------------------------------------------------------


def test_paper_only_refusal_under_trading_mode_live(tmp_path: Path):
    """TRADING_MODE=LIVE aborts the harness with exit 1, even on a valid URL.

    Paper-only refusal must fire BEFORE URL regex validation — exit code 1, not 2.
    """
    res = _run_harness(
        "--url",
        _VALID_URL,
        "--skip-gh-api",
        "--target-path",
        str(tmp_path / "ev.json"),
        "--ci-url-txt-path",
        str(tmp_path / "ci.txt"),
        env_overrides={"TRADING_MODE": "LIVE"},
    )
    assert res.returncode == 1, (
        f"expected exit 1 (paper-only refusal), got {res.returncode}\nstderr: {res.stderr}"
    )
    assert "TRADING_MODE" in res.stderr
    assert "LIVE" in res.stderr or "paper-only" in res.stderr.lower()
    assert not (tmp_path / "ev.json").exists()


# ---------------------------------------------------------------------------
# Schema + ci-url.txt + skip-gh-api recording
# ---------------------------------------------------------------------------


def test_evidence_json_validates_against_schema(tmp_path: Path):
    """After a successful --skip-gh-api run, evidence JSON satisfies the schema."""
    target = tmp_path / "evidence.json"
    res = _run_harness(
        "--url",
        _VALID_URL,
        "--skip-gh-api",
        "--target-path",
        str(target),
        "--ci-url-txt-path",
        str(tmp_path / "ci.txt"),
    )
    assert res.returncode == 0, res.stderr
    payload = _read_evidence(target)
    schema = _load_schema()
    # Must not raise.
    jsonschema.validate(payload, schema)
    # Spot-check required fields are typed correctly.
    assert payload["schema_version"] == 1
    assert isinstance(payload["timestamp"], str)
    assert isinstance(payload["evidence_paths"], list)
    assert isinstance(payload["human_needed"], bool)


def test_writes_ci_url_txt(tmp_path: Path):
    """The harness writes the URL to --ci-url-txt-path verbatim with a single trailing newline."""
    ci_url_txt = tmp_path / "ci-url.txt"
    res = _run_harness(
        "--url",
        _VALID_URL,
        "--skip-gh-api",
        "--target-path",
        str(tmp_path / "ev.json"),
        "--ci-url-txt-path",
        str(ci_url_txt),
    )
    assert res.returncode == 0, res.stderr
    raw = ci_url_txt.read_text()
    # Must equal URL + exactly one newline.
    assert raw == _VALID_URL + "\n", f"unexpected ci-url.txt contents: {raw!r}"


def test_gh_api_skip_records_in_extra(tmp_path: Path):
    """After a --skip-gh-api success, evidence JSON extra.skip_gh_api == true."""
    target = tmp_path / "ev.json"
    res = _run_harness(
        "--url",
        _VALID_URL,
        "--skip-gh-api",
        "--target-path",
        str(target),
        "--ci-url-txt-path",
        str(tmp_path / "ci.txt"),
    )
    assert res.returncode == 0, res.stderr
    payload = _read_evidence(target)
    assert payload["extra"]["skip_gh_api"] is True, (
        f"extra.skip_gh_api should be true when --skip-gh-api was passed; got {payload['extra']}"
    )
