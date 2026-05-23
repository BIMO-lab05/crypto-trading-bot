"""AUDIT-01 schema + seed validation tests. Per Phase 16 Plan 01."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
EVIDENCE_DIR = HERE.parent  # .planning/evidence/AUDIT-01/
SCHEMA_PATH = EVIDENCE_DIR / "_schema.json"
SEED_PATH = EVIDENCE_DIR / "validated-reaudit.json"

jsonschema = pytest.importorskip("jsonschema")


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA_PATH.read_text())


def test_empty_rows_validates(schema):
    jsonschema.validate({"schema_version": 1, "rows": []}, schema)


def test_valid_pending_row_validates(schema):
    doc = {
        "schema_version": 1,
        "rows": [
            {
                "req_id": "RISK-04",
                "era": "pre-v1",
                "source": "PROJECT.md",
                "claim": "Per-trade risk cap 2% LIVE / 10% paper",
                "status": "pending",
                "evidence_file": None,
                "evidence_line_start": None,
                "evidence_line_end": None,
                "notes": None,
            }
        ],
    }
    jsonschema.validate(doc, schema)


def test_row_missing_req_id_rejected(schema):
    doc = {
        "schema_version": 1,
        "rows": [
            {
                "era": "pre-v1",
                "source": "PROJECT.md",
                "claim": "x" * 10,
                "status": "pending",
            }
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, schema)


def test_bogus_status_rejected(schema):
    doc = {
        "schema_version": 1,
        "rows": [
            {
                "req_id": "X-01",
                "era": "pre-v1",
                "source": "PROJECT.md",
                "claim": "x" * 10,
                "status": "bogus",
            }
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, schema)


def test_unknown_era_rejected(schema):
    doc = {
        "schema_version": 1,
        "rows": [
            {
                "req_id": "X-01",
                "era": "v1.3",
                "source": "PROJECT.md",
                "claim": "x" * 10,
                "status": "pending",
            }
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, schema)


@pytest.mark.skipif(
    not SEED_PATH.exists(), reason="Seed not yet written (Task 2/3 produce it)"
)
def test_seed_validates(schema):
    doc = json.loads(SEED_PATH.read_text())
    jsonschema.validate(doc, schema)


@pytest.mark.skipif(not SEED_PATH.exists(), reason="Seed not yet written")
def test_seed_row_count_in_band():
    doc = json.loads(SEED_PATH.read_text())
    n = len(doc["rows"])
    assert 75 <= n <= 90, f"Seed row count {n} outside D-06 estimate band [75, 90]"


@pytest.mark.skipif(not SEED_PATH.exists(), reason="Seed not yet written")
def test_every_era_represented():
    doc = json.loads(SEED_PATH.read_text())
    eras = {r["era"] for r in doc["rows"]}
    assert eras == {"pre-v1", "v1.0", "v1.1", "v1.2"}, (
        f"Missing eras: expected {{'pre-v1','v1.0','v1.1','v1.2'}}, got {eras}"
    )


def _seed_is_post_merge() -> bool:
    """True once Plan 06 has merged in-place — SEED_PATH then IS the canonical."""
    if not SEED_PATH.exists():
        return False
    try:
        doc = json.loads(SEED_PATH.read_text())
    except Exception:
        return False
    return any(r.get("status") != "pending" for r in doc.get("rows", []))


@pytest.mark.skipif(not SEED_PATH.exists(), reason="Seed not yet written")
@pytest.mark.skipif(
    _seed_is_post_merge(),
    reason="Plan 06 merged in-place — SEED_PATH is now the canonical (status != pending by design)",
)
def test_every_seed_row_is_pending():
    doc = json.loads(SEED_PATH.read_text())
    non_pending = [r["req_id"] for r in doc["rows"] if r["status"] != "pending"]
    assert non_pending == [], (
        f"Seed rows already classified (should be pending): {non_pending}"
    )


@pytest.mark.skipif(not SEED_PATH.exists(), reason="Seed not yet written")
def test_no_duplicate_req_ids():
    doc = json.loads(SEED_PATH.read_text())
    ids = [r["req_id"] for r in doc["rows"]]
    dupes = sorted({x for x in ids if ids.count(x) > 1})
    assert dupes == [], f"Duplicate req_id in seed: {dupes}"


@pytest.mark.skipif(not SEED_PATH.exists(), reason="Seed not yet written")
def test_claude_synthetic_ids_present():
    doc = json.loads(SEED_PATH.read_text())
    ids = {r["req_id"] for r in doc["rows"]}
    required = {
        "CLAUDE-LSTM-ARCHIVED",
        "CLAUDE-SENTIMENT-REMOVED",
        "CLAUDE-VALIDATED-SYMBOLS",
        "CLAUDE-PAPER-CAP-ADR010",
        "CLAUDE-EXEC-MAINNET-PRICES",
    }
    missing = required - ids
    assert missing == set(), (
        f"Missing CLAUDE-* synthetic IDs (per CONTEXT D-04): {missing}"
    )
