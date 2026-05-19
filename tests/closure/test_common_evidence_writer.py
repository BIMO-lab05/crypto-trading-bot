"""Unit tests for scripts.closure._common evidence-write helper.

Covers schema-pass / schema-fail branches of write_evidence() plus the CLI
subcommand smoke. All filesystem writes use the pytest ``tmp_path`` fixture —
no test writes into the repo ``.planning/evidence/`` tree.

Plan: .planning/phases/11.1-carry-in-closure-harnesses-liveclose-01-05/11.1-01-PLAN.md
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from scripts.closure._common import (
    SCHEMA_VERSION,
    STATUS_AWAITING_HUMAN,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_INSUFFICIENT_DATA,
    load_schema,
    main,
    write_evidence,
)


def test_load_schema_returns_dict():
    """load_schema() returns the parsed JSON Schema as a dict with `required`."""
    schema = load_schema()
    assert isinstance(schema, dict)
    assert "required" in schema
    assert "schema_version" in schema["required"]
    assert "status" in schema["required"]
    assert "liveclose_id" in schema["required"]


def test_status_constants_match_schema_enum():
    """The STATUS_* module constants must equal the schema's status enum strings."""
    schema = load_schema()
    enum = schema["properties"]["status"]["enum"]
    assert STATUS_COMPLETE in enum
    assert STATUS_AWAITING_HUMAN in enum
    assert STATUS_INSUFFICIENT_DATA in enum
    assert STATUS_FAILED in enum
    assert {
        STATUS_COMPLETE,
        STATUS_AWAITING_HUMAN,
        STATUS_INSUFFICIENT_DATA,
        STATUS_FAILED,
    } == set(enum)


def test_schema_version_constant_is_one():
    """SCHEMA_VERSION is the integer 1, matching schema['properties']['schema_version']['const']."""
    assert SCHEMA_VERSION == 1


def test_write_evidence_valid_complete_status(tmp_path: Path):
    """Writing a COMPLETE-status payload returns a Path and the file validates."""
    target = tmp_path / "complete.json"
    out = write_evidence(
        liveclose_id="LIVECLOSE-01",
        status=STATUS_COMPLETE,
        evidence_paths=[".planning/evidence/LIVECLOSE-01/run.md"],
        human_needed=False,
        target_path=target,
    )
    assert out == target
    assert target.exists()
    payload = json.loads(target.read_text())
    # Validate against schema — must not raise.
    jsonschema.validate(payload, load_schema())
    assert payload["status"] == STATUS_COMPLETE
    assert payload["liveclose_id"] == "LIVECLOSE-01"
    assert payload["human_needed"] is False
    assert payload["schema_version"] == 1
    assert payload["evidence_paths"] == [".planning/evidence/LIVECLOSE-01/run.md"]


def test_write_evidence_valid_awaiting_human(tmp_path: Path):
    """AWAITING_HUMAN status with human_needed=True validates and round-trips."""
    target = tmp_path / "awaiting.json"
    write_evidence(
        liveclose_id="LIVECLOSE-05",
        status=STATUS_AWAITING_HUMAN,
        evidence_paths=[],
        human_needed=True,
        target_path=target,
    )
    payload = json.loads(target.read_text())
    jsonschema.validate(payload, load_schema())
    assert payload["status"] == STATUS_AWAITING_HUMAN
    assert payload["human_needed"] is True
    assert payload["evidence_paths"] == []


def test_write_evidence_rejects_bad_status(tmp_path: Path):
    """Bad status string must raise jsonschema.ValidationError (not ValueError)."""
    with pytest.raises(jsonschema.exceptions.ValidationError):
        write_evidence(
            liveclose_id="LIVECLOSE-01",
            status="BOGUS",  # not in the enum
            evidence_paths=[],
            human_needed=False,
            target_path=tmp_path / "bad.json",
        )


def test_write_evidence_rejects_bad_liveclose_id(tmp_path: Path):
    """Bad liveclose_id must raise jsonschema.ValidationError."""
    with pytest.raises(jsonschema.exceptions.ValidationError):
        write_evidence(
            liveclose_id="LIVECLOSE-99",  # not in the enum
            status=STATUS_COMPLETE,
            evidence_paths=[],
            human_needed=False,
            target_path=tmp_path / "bad.json",
        )


def test_write_evidence_extra_merges_into_payload(tmp_path: Path):
    """extra dict (with a non-reserved key) merges into the written payload."""
    target = tmp_path / "extra.json"
    write_evidence(
        liveclose_id="LIVECLOSE-02",
        status=STATUS_COMPLETE,
        evidence_paths=[".planning/evidence/LIVECLOSE-02/ci-url.txt"],
        human_needed=False,
        extra={"ci_url": "https://github.com/owner/repo/actions/runs/123"},
        target_path=target,
    )
    payload = json.loads(target.read_text())
    jsonschema.validate(payload, load_schema())
    assert payload["ci_url"] == "https://github.com/owner/repo/actions/runs/123"


def test_write_evidence_extra_collision_raises(tmp_path: Path):
    """extra colliding with a required field raises ValueError before jsonschema runs.

    Per plan: 'key collision with required fields raises ValueError'. The
    helper must check for collision and raise *before* jsonschema sees the
    payload (so the test asserts ValueError, not ValidationError).
    """
    with pytest.raises(ValueError, match="collides with required field"):
        write_evidence(
            liveclose_id="LIVECLOSE-01",
            status=STATUS_COMPLETE,
            evidence_paths=[],
            human_needed=False,
            extra={"status": "X"},  # collides with required status field
            target_path=tmp_path / "bad.json",
        )


def test_main_cli_writes_evidence_smoke(tmp_path: Path):
    """CLI subcommand `write-evidence` writes a valid evidence file and exits 0."""
    target = tmp_path / "cli_smoke.json"
    rc = main(
        [
            "write-evidence",
            "--liveclose-id",
            "LIVECLOSE-01",
            "--status",
            "COMPLETE",
            "--target-path",
            str(target),
            "--no-human-needed",
            "--evidence-path",
            "/tmp/foo.txt",
        ]
    )
    assert rc == 0
    assert target.exists()
    payload = json.loads(target.read_text())
    jsonschema.validate(payload, load_schema())
    assert payload["liveclose_id"] == "LIVECLOSE-01"
    assert payload["status"] == STATUS_COMPLETE
    assert payload["evidence_paths"] == ["/tmp/foo.txt"]
    assert payload["human_needed"] is False


def test_main_cli_rejects_bad_status(tmp_path: Path):
    """CLI subcommand with BOGUS status returns a non-zero exit code."""
    target = tmp_path / "cli_bad.json"
    rc = main(
        [
            "write-evidence",
            "--liveclose-id",
            "LIVECLOSE-01",
            "--status",
            "BOGUS",
            "--target-path",
            str(target),
            "--no-human-needed",
        ]
    )
    assert rc != 0
    assert not target.exists()
