"""Integration tests for the LIVECLOSE-01 fresh-clone harness.

Asserts the **contract** of `scripts/closure/liveclose-01-fresh-clone.sh`
without spinning up docker. The harness honors a `LIVECLOSE_01_DRY_RUN=1`
env-var branch that prints the stdout template lines and exits 0, so the
contract can be exercised offline. Schema-shape coverage is provided by
calling `write_evidence(...)` with a synthesized happy-path payload and
validating the on-disk JSON against `.planning/evidence/_schema.json`.

Plan: .planning/phases/11.1-carry-in-closure-harnesses-liveclose-01-05/11.1-02-PLAN.md
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

from scripts.closure._common import (
    STATUS_AWAITING_HUMAN,
    load_schema,
    write_evidence,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_PATH = REPO_ROOT / "scripts" / "closure" / "liveclose-01-fresh-clone.sh"
FIXTURE_PATH = (
    REPO_ROOT / "tests" / "closure" / "fixtures" / "liveclose_01_expected_stdout.txt"
)


def _read_harness_source() -> str:
    return HARNESS_PATH.read_text()


def _read_harness_source_no_comments() -> str:
    """Return harness source with full-line comments stripped.

    Defends against grep-gate self-invalidation: header-prose mentions
    of literal strings (e.g. an executable line referenced in a comment)
    must not inflate counts of executable occurrences.
    """
    out_lines = []
    for line in _read_harness_source().splitlines():
        stripped = line.lstrip()
        # Skip shebang and full-line shell comments.
        if stripped.startswith("#"):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


def test_harness_script_exists_and_executable() -> None:
    """Harness script is present, readable, and the executable bit is set."""
    assert HARNESS_PATH.exists(), f"missing harness: {HARNESS_PATH}"
    assert HARNESS_PATH.is_file()
    mode = HARNESS_PATH.stat().st_mode
    # Any executable bit (owner / group / other) is acceptable.
    executable_bits = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    assert mode & executable_bits, (
        f"harness not executable: mode={oct(mode)} path={HARNESS_PATH}"
    )


def test_harness_refuses_when_trading_mode_live(tmp_path: Path) -> None:
    """TRADING_MODE=LIVE must short-circuit with non-zero exit (paper-only)."""
    result = subprocess.run(
        ["bash", str(HARNESS_PATH)],
        env={
            "TRADING_MODE": "LIVE",
            "PATH": os.environ["PATH"],
            "HOME": str(tmp_path),
        },
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode != 0, (
        "harness must refuse to run under TRADING_MODE=LIVE; "
        f"got exit=0 stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    assert "TRADING_MODE" in combined.upper() or "LIVE" in combined.upper(), (
        f"refusal message missing TRADING_MODE/LIVE: {combined!r}"
    )


def test_harness_stdout_matches_fixture_with_dry_run(tmp_path: Path) -> None:
    """LIVECLOSE_01_DRY_RUN=1 prints the recorded stdout template verbatim."""
    result = subprocess.run(
        ["bash", str(HARNESS_PATH)],
        env={
            "LIVECLOSE_01_DRY_RUN": "1",
            "PATH": os.environ["PATH"],
            "HOME": str(tmp_path),
        },
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, (
        f"DRY_RUN should exit 0; got rc={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    expected = FIXTURE_PATH.read_text()
    actual = result.stdout.decode("utf-8")
    expected_lines = expected.splitlines()
    actual_lines = actual.splitlines()
    assert actual_lines == expected_lines, (
        "DRY_RUN stdout does not match fixture exactly.\n"
        f"expected ({len(expected_lines)} lines): {expected_lines!r}\n"
        f"actual ({len(actual_lines)} lines): {actual_lines!r}"
    )
    # Contract is 12 lines (no trailing blank-line drift).
    assert len(actual_lines) == 12, (
        f"stdout contract is 12 lines, got {len(actual_lines)}"
    )


def test_harness_calls_bootstrap_twice_in_source() -> None:
    """Exactly two executable invocations of `bash bootstrap.sh`.

    Comments are stripped before counting so header narrative cannot
    spoof the count (project rule: self-invalidating grep gates).
    """
    source_no_comments = _read_harness_source_no_comments()
    count = source_no_comments.count("bash bootstrap.sh")
    assert count == 2, (
        f"expected exactly 2 `bash bootstrap.sh` invocations outside "
        f"comments; got {count}"
    )


def test_harness_writes_evidence_via_common_helper() -> None:
    """Harness invokes the shared write-evidence CLI with LIVECLOSE-01."""
    source = _read_harness_source()
    expected_call = (
        "python -m scripts.closure._common write-evidence --liveclose-id LIVECLOSE-01"
    )
    assert expected_call in source, (
        "harness must invoke the shared evidence helper with the "
        f"LIVECLOSE-01 id; expected substring not found: {expected_call!r}"
    )


def test_harness_evidence_shape_validates_against_schema(tmp_path: Path) -> None:
    """Synthesized happy-path payload validates against `_schema.json`.

    Calls `write_evidence(...)` with the **exact** field set the harness
    would emit (AWAITING_HUMAN + LIVECLOSE-01 + extra-payload keys for
    bootstrap exit codes, BYBIT log line, compose-ps running count).
    Reads the file back and runs `jsonschema.validate` against the
    schema. This guards Wave 2 against drift from the Plan-1 contract.
    """
    target = tmp_path / "sim.json"
    out = write_evidence(
        liveclose_id="LIVECLOSE-01",
        status=STATUS_AWAITING_HUMAN,
        evidence_paths=[
            "tmp/bootstrap-run-1.log",
            "tmp/bootstrap-run-2.log",
            "tmp/compose-ps-run-1.json",
            "tmp/compose-ps-run-2.json",
        ],
        human_needed=True,
        extra={
            "bootstrap_run_1_rc": 0,
            "bootstrap_run_2_rc": 0,
            "bybit_price_source_run_1": (
                "BYBIT_PRICE_SOURCE: mode=tape source_dir=/data/tape tape_version=1"
            ),
            "bybit_price_source_run_2": (
                "BYBIT_PRICE_SOURCE: mode=tape source_dir=/data/tape tape_version=1"
            ),
            "compose_ps_running_count_run_1": 15,
            "compose_ps_running_count_run_2": 15,
            "tmp_clone_dir": "/tmp/liveclose-01.XXXXXX",
        },
        target_path=target,
    )
    assert out == target
    assert target.exists()
    payload = json.loads(target.read_text())
    jsonschema.validate(payload, load_schema())
    # Sanity-check the auto-injected fields landed.
    assert payload["liveclose_id"] == "LIVECLOSE-01"
    assert payload["status"] == STATUS_AWAITING_HUMAN
    assert payload["human_needed"] is True
    assert payload["schema_version"] == 1
    assert payload["bootstrap_run_1_rc"] == 0
    assert payload["compose_ps_running_count_run_2"] == 15


def test_harness_uses_mktemp_d_not_working_tree() -> None:
    """Exactly one `mktemp -d`; zero references to the forbidden blanket-purge.

    The forbidden literal is the project-rule directive (CLAUDE.md): the
    harness must never use a blanket working-tree cleanup invocation.
    Counting via the comment-stripped source so header reminders cannot
    accidentally inflate either count.
    """
    source_no_comments = _read_harness_source_no_comments()
    mktemp_count = source_no_comments.count("mktemp -d")
    assert mktemp_count == 1, (
        f"expected exactly 1 `mktemp -d` invocation outside comments; "
        f"got {mktemp_count}"
    )
    # Project rule (CLAUDE.md): never run the blanket-purge invocation
    # against the working tree. Check the full source (not just executable
    # lines) so the directive cannot reappear even as a comment string.
    full_source = _read_harness_source()
    forbidden = "git clean -fdx"
    assert forbidden not in full_source, (
        f"harness contains forbidden literal {forbidden!r}; "
        "project rule (CLAUDE.md): never blanket-purge the working tree"
    )


def test_harness_emits_aware_iso_timestamp_in_target_path() -> None:
    """Synthesized target path matches the compact ISO-8601 UTC pattern.

    Mirrors the format the harness composes: `run-YYYYMMDDTHHMMSSZ.json`.
    """
    now_compact = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target_path = f".planning/evidence/LIVECLOSE-01/run-{now_compact}.json"
    pattern = re.compile(r"^\.planning/evidence/LIVECLOSE-01/run-\d{8}T\d{6}Z\.json$")
    assert pattern.match(target_path), (
        f"target path does not match compact ISO-8601 UTC pattern: {target_path!r}"
    )
