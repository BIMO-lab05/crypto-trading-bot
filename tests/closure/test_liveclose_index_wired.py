"""Integration tests for .planning/evidence/LIVECLOSE-INDEX.md (Phase 11.1 Plan 07).

Wave 3 wiring tests. These assert that the Wave-3 plan (11.1-07) has
populated the placeholder rows of the Wave-1 INDEX template with real
harness paths + evidence-target paths, that every referenced harness
exists on disk, and that the operator-facing sections (Orchestrator,
Wave-3 Closure Contract) are present and lint-clean.

The tests are intentionally markdown-parsing / filesystem-only — no
docker, no network, no `scripts.closure` imports. They collect from a
bare `pytest` invocation without needing `PYTHONPATH=.`.

Plan: .planning/phases/11.1-carry-in-closure-harnesses-liveclose-01-05/11.1-07-PLAN.md
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path resolution: tests/closure/test_liveclose_index_wired.py lives two
# directory levels below the repo root (parents[0]=tests/closure/,
# parents[1]=tests/, parents[2]=repo root).
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parents[2]
_INDEX = _REPO / ".planning" / "evidence" / "LIVECLOSE-INDEX.md"

# Five carry-in IDs Phase 11.1 closes.
_IDS = [f"LIVECLOSE-0{n}" for n in range(1, 6)]

# Canonical on-disk harness paths after Wave 2 lands. Hyphen-form for
# `.sh`, underscore-form for `.py` (Python import contract — documented
# deviation in 11.1-04-SUMMARY and 11.1-05-SUMMARY).
_HARNESS_PATHS = [
    "scripts/closure/liveclose-01-fresh-clone.sh",
    "scripts/closure/liveclose-02-record-ci.sh",
    "scripts/closure/liveclose_03_psr_evidence.py",
    "scripts/closure/liveclose_04_sweep_verdict.py",
    "scripts/closure/liveclose-05-live-flip-smoke.sh",
]


@pytest.fixture(scope="module")
def index_text() -> str:
    if not _INDEX.exists():
        pytest.fail(f"LIVECLOSE-INDEX.md not found at {_INDEX}")
    return _INDEX.read_text()


# ---------------------------------------------------------------------------
# Wave-3 wiring contract
# ---------------------------------------------------------------------------


def test_no_filled_by_plan_7_placeholders(index_text: str) -> None:
    """All `<filled-by-plan-7>` placeholders MUST be replaced by Plan 11.1-07.

    Mirrors plan acceptance criterion
    ``grep -c "<filled-by-plan-7>" .planning/evidence/LIVECLOSE-INDEX.md == 0``.
    """
    count = index_text.count("<filled-by-plan-7>")
    assert count == 0, (
        f"{count} <filled-by-plan-7> placeholder(s) remain in LIVECLOSE-INDEX.md; "
        "Plan 11.1-07 Task 1 has not populated all rows."
    )


def test_all_harness_paths_exist(index_text: str) -> None:
    """Every Wave-2 harness path referenced in INDEX must exist on disk.

    The plan's `contains:` frontmatter lines mention hyphen-form `.py` paths
    that do not exist on disk (Python import contract requires underscores).
    We assert the ACTUAL on-disk paths exist (underscore for `.py`, hyphen
    for `.sh`); the hyphen-form `.py` mismatch is a documented deviation in
    11.1-07-SUMMARY (Rule 3 — frontmatter follow-up).
    """
    for path_str in _HARNESS_PATHS:
        # The path must appear in the index text at least once.
        assert path_str in index_text, (
            f"harness path '{path_str}' not referenced in LIVECLOSE-INDEX.md"
        )
        # And it must exist on disk.
        on_disk = _REPO / path_str
        assert on_disk.exists(), (
            f"harness path '{path_str}' not found on disk at {on_disk}"
        )


def test_all_evidence_target_dirs_documented(index_text: str) -> None:
    """Each `.planning/evidence/LIVECLOSE-0X/` path must appear in the index.

    The five evidence directories are the destination of every harness;
    operators rely on the INDEX to know where to commit the artifacts.
    """
    for n in range(1, 6):
        target = f".planning/evidence/LIVECLOSE-0{n}/"
        assert target in index_text, (
            f"evidence target directory '{target}' not documented in INDEX"
        )


def test_index_lists_five_carry_ins(index_text: str) -> None:
    """Each of LIVECLOSE-01..05 appears in the index text body.

    Acceptance criterion #4 from Plan 11.1-07 Task 1.
    """
    for liveclose_id in _IDS:
        assert liveclose_id in index_text, (
            f"missing carry-in ID '{liveclose_id}' in INDEX"
        )


def test_orchestrator_section_present(index_text: str) -> None:
    """The INDEX must point operators at the run-all.sh orchestrator."""
    assert "## Orchestrator" in index_text, "missing '## Orchestrator' section heading"
    assert "run-all.sh" in index_text, (
        "Orchestrator section must reference scripts/closure/run-all.sh"
    )


def test_wave_3_closure_contract_section_present(index_text: str) -> None:
    """The INDEX must describe the operator closure protocol against carry_ins.json."""
    assert "## Wave-3 Closure Contract" in index_text, (
        "missing '## Wave-3 Closure Contract' section heading"
    )
    assert "carry_ins.json" in index_text, (
        "Wave-3 Closure Contract section must reference carry_ins.json"
    )


def test_index_markdown_lints_clean(index_text: str) -> None:
    """Heuristic markdown lint: no trailing whitespace, ends in `\\n`, no triple blank.

    The plan's `grep -c "^\\n\\n$"` is incoherent on line-based grep — we
    enforce the spirit of the gate (operator-readable, no formatting drift)
    using Python regex over `splitlines()`.
    """
    # 1. File ends with a newline.
    assert index_text.endswith("\n"), "LIVECLOSE-INDEX.md must end with a newline"

    # 2. No trailing whitespace on any line.
    bad_lines = [
        (i, line)
        for i, line in enumerate(index_text.splitlines(), start=1)
        if line != line.rstrip()
    ]
    assert not bad_lines, (
        f"{len(bad_lines)} line(s) with trailing whitespace: "
        f"{[i for i, _ in bad_lines[:5]]}"
    )

    # 3. No run of three or more consecutive blank lines.
    if re.search(r"\n[ \t]*\n[ \t]*\n[ \t]*\n", index_text):
        pytest.fail("LIVECLOSE-INDEX.md contains 3+ consecutive blank lines")
