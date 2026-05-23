"""AUDIT-01 merge completeness tests — Plan 16-06.

Eight load-bearing assertions per CONTEXT D-03. If any RED, the canonical
validated-reaudit.json is inconsistent and Plan 07 must not run.
"""

from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
EVIDENCE_DIR = HERE.parent
CANONICAL_PATH = EVIDENCE_DIR / "validated-reaudit.json"
SCHEMA_PATH = EVIDENCE_DIR / "_schema.json"

jsonschema = pytest.importorskip("jsonschema")

_MERGE_PATH = EVIDENCE_DIR / "tests" / "_merge_deltas.py"


def _load_merge_module():
    spec = spec_from_file_location("_merge_deltas", _MERGE_PATH)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def seed_baseline():
    """Sum of track-delta row counts is the row-count baseline.

    The pre-merge seed (validated-reaudit.json) starts at 81 rows; after Plan 06
    merge runs, the same file IS the canonical and its rows derive from the
    delta union. The baseline therefore comes from the delta files, not the
    in-place seed.
    """
    _merge_deltas = _load_merge_module()
    deltas = _merge_deltas.load_all_deltas()
    return {
        "delta_count": len(deltas),
        "delta_ids": {(d["req_id"], d["era"]) for d in deltas},
    }


@pytest.fixture(scope="module")
def canonical():
    return json.loads(CANONICAL_PATH.read_text())


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA_PATH.read_text())


def test_canonical_row_count_matches_delta_union(seed_baseline, canonical):
    assert len(canonical["rows"]) == seed_baseline["delta_count"], (
        f"canonical row count ({len(canonical['rows'])}) != "
        f"sum of delta rows ({seed_baseline['delta_count']})"
    )


def test_no_pending_rows(canonical):
    pending = [r["req_id"] for r in canonical["rows"] if r["status"] == "pending"]
    assert pending == [], f"Canonical still has pending rows: {pending}"


def test_every_canonical_id_in_delta_union(seed_baseline, canonical):
    canonical_ids = {(r["req_id"], r["era"]) for r in canonical["rows"]}
    extras = canonical_ids - seed_baseline["delta_ids"]
    assert extras == set(), f"Canonical has rows not in delta union: {extras}"


def test_every_delta_id_in_canonical(seed_baseline, canonical):
    canonical_ids = {(r["req_id"], r["era"]) for r in canonical["rows"]}
    missing = seed_baseline["delta_ids"] - canonical_ids
    assert missing == set(), f"Delta rows not present in canonical: {missing}"


def test_canonical_validates_against_schema(canonical, schema):
    jsonschema.validate(canonical, schema)


def test_satisfied_and_drift_rows_have_evidence_file(canonical):
    bad = [
        r["req_id"]
        for r in canonical["rows"]
        if r["status"] in ("satisfied", "drift") and not r.get("evidence_file")
    ]
    assert bad == [], f"satisfied/drift rows without evidence_file: {bad}"


def test_drift_and_missing_rows_have_notes(canonical):
    bad = [
        r["req_id"]
        for r in canonical["rows"]
        if r["status"] in ("drift", "missing") and not r.get("notes")
    ]
    assert bad == [], f"drift/missing rows without notes: {bad}"


def test_drift_missing_rows_have_phase_owner(canonical):
    import re

    # Per CONTEXT D-11 + D-12: every drift/missing row must cite a downstream
    # phase owner (Phase 17..24) or an explicit propose marker.
    owner_re = re.compile(
        r"(Phase\s*(17|18|19|20|21|22|23|24)\b|propose:demote-out-of-scope|propose:new-v1\.4-phase)"
    )
    unrouted = [
        r["req_id"]
        for r in canonical["rows"]
        if r["status"] in ("drift", "missing")
        and not owner_re.search(r.get("notes") or "")
    ]
    assert unrouted == [], (
        f"drift/missing rows without phase-owner proposal in notes: {unrouted}"
    )
