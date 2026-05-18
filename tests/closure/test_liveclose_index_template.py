"""Tests for .planning/evidence/LIVECLOSE-INDEX.md template (Plan 11.1-01 Task 3).

The index template ships in Plan 11.1-01; Plan 11.1-07 (Wave 3) replaces the
`<filled-by-plan-7>` placeholders with real harness paths. These tests assert
the template invariants that survive both Wave 1 and Wave 3 — IDs present,
status enum documented, schema referenced, H1 on line 1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_INDEX = _REPO / ".planning" / "evidence" / "LIVECLOSE-INDEX.md"


@pytest.fixture(scope="module")
def index_text() -> str:
    if not _INDEX.exists():
        pytest.fail(f"LIVECLOSE-INDEX.md not found at {_INDEX}")
    return _INDEX.read_text()


def test_index_exists():
    """The template file is present at the canonical path."""
    assert _INDEX.exists(), f"LIVECLOSE-INDEX.md not found at {_INDEX}"


def test_index_lists_all_five_carry_ins(index_text: str):
    """All five LIVECLOSE-01..05 IDs appear in the index at least once."""
    for n in range(1, 6):
        liveclose_id = f"LIVECLOSE-0{n}"
        assert liveclose_id in index_text, f"missing {liveclose_id} row"


def test_index_status_enum_documented(index_text: str):
    """All four schema status enum strings are documented in the index."""
    for status in ("COMPLETE", "AWAITING_HUMAN", "INSUFFICIENT_DATA", "FAILED"):
        assert status in index_text, f"status '{status}' not documented"


def test_index_references_schema(index_text: str):
    """The index points operators at the JSON Schema."""
    assert "_schema.json" in index_text


def test_index_has_h1_heading(index_text: str):
    """First line of the file is the H1 (no leading blank lines, no frontmatter).

    Plan acceptance criterion uses `head -1` not 'first non-empty line', so the
    literal first line must start with `# LIVECLOSE`.
    """
    first_line = index_text.splitlines()[0]
    assert first_line.startswith("# LIVECLOSE"), (
        f"first line must start with '# LIVECLOSE', got: {first_line!r}"
    )
