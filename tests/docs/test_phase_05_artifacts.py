"""Doc-existence gates for Phase 5 (ml-cleanup-post-v0) plan-mandated artifacts.

Phase 5 plans 03 (MLCL-03) and 04 (MLCL-04) require five documentation artifacts
on disk: two phase DECISION.md files, two ADRs, and a monitoring README section.
The phase's behavioral test suite (51/51 passing) does not pin the existence,
minimum size, or load-bearing substrings of these documents. Without these
gates, a future PR can silently delete or shrink them and no test catches it.

Each test below asserts:
  (a) the file exists at the plan-mandated path,
  (b) the file has at least the plan-mandated number of non-blank lines, and
  (c) the file contains the load-bearing substrings the plan calls out.

Pure file-IO + regex — no Docker, no network, no monkeypatching.
Expected runtime: <1 second.

Mirrors the doc-existence pattern of:
  services/tournament-harness/tests/integration/test_t0_1_x_experiment_shipped.py
  tests/security/test_no_unattended_claude_p_in_ci.py

Path discovery: tests/docs/ -> tests/ -> repo root, so parents[2].
"""

from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo layout
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

# Phase 05 plan-artifact paths
DECISION_05_03 = (
    REPO_ROOT / ".planning" / "phases" / "05-ml-cleanup-post-v0" / "05-03-DECISION.md"
)
DECISION_05_04 = (
    REPO_ROOT / ".planning" / "phases" / "05-ml-cleanup-post-v0" / "05-04-DECISION.md"
)
ADR_011 = REPO_ROOT / "docs" / "decisions" / "ADR-011-monitoring-disposition.md"
ADR_012 = REPO_ROOT / "docs" / "decisions" / "ADR-012-extended-backtest-disposition.md"
MONITORING_README = REPO_ROOT / "scripts" / "monitoring" / "README.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _non_blank_line_count(path: Path) -> int:
    """Return the number of non-blank lines in a text file."""
    return sum(1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())


# ---------------------------------------------------------------------------
# Gap 1: 05-03-DECISION.md exists, >=100 non-blank lines, names the disposition
# ---------------------------------------------------------------------------


def test_phase_05_03_decision_md_exists_with_min_lines_and_disposition_heading():
    """MLCL-03 plan must_have: 05-03-DECISION.md exists, >=100 lines, names disposition.

    Plan: .planning/phases/05-ml-cleanup-post-v0/05-03-PLAN.md (must_haves.artifacts,
    min_lines: 100). The decision heading must name exactly one disposition_id —
    we pin the verbatim chosen value (keep_tier1_delete_tier2) so a silent flip
    of the disposition without re-running the planning workflow is caught.
    """
    assert DECISION_05_03.exists(), (
        f"MLCL-03 plan artifact missing: {DECISION_05_03}\n"
        "The Phase 05 Plan 03 (MLCL-03) requires this DECISION.md analyzing the "
        "two viable monitoring dispositions. Restore from git history if deleted."
    )

    line_count = _non_blank_line_count(DECISION_05_03)
    assert line_count >= 100, (
        f"05-03-DECISION.md has only {line_count} non-blank lines; "
        f"plan requires >=100.\nFile: {DECISION_05_03}"
    )

    text = DECISION_05_03.read_text(encoding="utf-8")
    assert "## Decision: keep_tier1_delete_tier2" in text, (
        "05-03-DECISION.md must contain the binding decision heading "
        "'## Decision: keep_tier1_delete_tier2' (the executed disposition).\n"
        f"File: {DECISION_05_03}"
    )


# ---------------------------------------------------------------------------
# Gap 2: ADR-011 exists, >=40 non-blank lines, has ADR sections
# ---------------------------------------------------------------------------


def test_adr_011_exists_with_min_lines_and_required_sections():
    """MLCL-03 plan must_have: ADR-011 exists, >=40 lines, has Title/Status/Decision.

    Plan: .planning/phases/05-ml-cleanup-post-v0/05-03-PLAN.md (must_haves.artifacts,
    min_lines: 40). Acceptance criterion: 'follows the standard ADR sections
    (Title, Status, Context, Decision, Consequences)'.

    We assert: filename-derived ADR-011 marker in title, '**Status:**' field, and
    a '## Decision' (or '## Decision:') heading. The Status/Decision sections are
    the load-bearing ones — Context and Consequences are convention but not
    independently load-bearing for the disposition record.
    """
    assert ADR_011.exists(), (
        f"MLCL-03 plan artifact missing: {ADR_011}\n"
        "The Phase 05 Plan 03 (MLCL-03) requires this ADR codifying the "
        "monitoring disposition. Restore from git history if deleted."
    )

    line_count = _non_blank_line_count(ADR_011)
    assert line_count >= 40, (
        f"ADR-011 has only {line_count} non-blank lines; plan requires >=40.\n"
        f"File: {ADR_011}"
    )

    text = ADR_011.read_text(encoding="utf-8")
    assert "ADR-011" in text, (
        f"ADR-011 must self-identify (substring 'ADR-011' missing).\nFile: {ADR_011}"
    )
    assert "Status:" in text, (
        f"ADR-011 must contain a 'Status:' field "
        f"(per standard ADR template).\n"
        f"File: {ADR_011}"
    )
    has_decision_heading = re.search(r"(?m)^## Decision\b", text) is not None
    assert has_decision_heading, (
        "ADR-011 must contain a '## Decision' heading (per standard ADR sections).\n"
        f"File: {ADR_011}"
    )


# ---------------------------------------------------------------------------
# Gap 3: scripts/monitoring/README.md has a Blast-radius bounds section
# ---------------------------------------------------------------------------


def test_monitoring_readme_has_blast_radius_bounds_section():
    """MLCL-03 acceptance criterion: README.md contains 'Blast-radius bounds' section.

    Plan: .planning/phases/05-ml-cleanup-post-v0/05-03-PLAN.md (acceptance_criteria,
    line 211): 'Whatever survives in scripts/monitoring/README.md contains a
    "Blast-radius bounds" section (grep -i "blast.radius" returns >=1 match)'.

    We assert case-insensitive presence of the literal phrase 'blast-radius bounds'
    in the README. This is the operator-facing artifact documenting what the
    surviving tier-1 monitor CAN and CANNOT do.
    """
    assert MONITORING_README.exists(), (
        f"MLCL-03 plan artifact missing: {MONITORING_README}\n"
        "scripts/monitoring/README.md must exist (the chosen disposition was "
        "keep_tier1_delete_tier2, so the directory and its README are retained)."
    )

    text = MONITORING_README.read_text(encoding="utf-8")
    # Case-insensitive search for the section title; the plan accepts any
    # phrasing matching the regex 'blast.radius' (dot is grep's any-char).
    assert re.search(r"blast.radius", text, re.IGNORECASE), (
        "scripts/monitoring/README.md must contain a 'Blast-radius bounds' section "
        "(case-insensitive; plan acceptance criterion).\n"
        f"File: {MONITORING_README}"
    )


# ---------------------------------------------------------------------------
# Gap 4: 05-04-DECISION.md exists, >=60 non-blank lines, names the disposition
# ---------------------------------------------------------------------------


def test_phase_05_04_decision_md_exists_with_min_lines_and_disposition_heading():
    """MLCL-04 plan must_have: 05-04-DECISION.md exists, >=60 lines, names disposition.

    Plan: .planning/phases/05-ml-cleanup-post-v0/05-04-PLAN.md (must_haves.artifacts,
    min_lines: 60). The decision heading must name exactly one option_id — we pin
    the verbatim chosen value (document_divergence_permanently) so a silent flip
    of the disposition without re-running the planning workflow is caught.
    """
    assert DECISION_05_04.exists(), (
        f"MLCL-04 plan artifact missing: {DECISION_05_04}\n"
        "The Phase 05 Plan 04 (MLCL-04) requires this DECISION.md analyzing the "
        "two extended-backtest disposition options. Restore from git history if deleted."
    )

    line_count = _non_blank_line_count(DECISION_05_04)
    assert line_count >= 60, (
        f"05-04-DECISION.md has only {line_count} non-blank lines; "
        f"plan requires >=60.\nFile: {DECISION_05_04}"
    )

    text = DECISION_05_04.read_text(encoding="utf-8")
    assert "## Decision: document_divergence_permanently" in text, (
        "05-04-DECISION.md must contain the binding decision heading "
        "'## Decision: document_divergence_permanently' (the executed disposition).\n"
        f"File: {DECISION_05_04}"
    )


# ---------------------------------------------------------------------------
# Gap 5: ADR-012 exists, >=30 non-blank lines, has ADR sections
# ---------------------------------------------------------------------------


def test_adr_012_exists_with_min_lines_and_required_sections():
    """MLCL-04 plan must_have: ADR-012 exists, >=30 lines, has Title/Status/Decision.

    Plan: .planning/phases/05-ml-cleanup-post-v0/05-04-PLAN.md (must_haves.artifacts,
    min_lines: 30). Acceptance criterion: 'follows the standard ADR sections
    (Title, Status, Context, Decision, Consequences)'.

    We assert: filename-derived ADR-012 marker in title, '**Status:**' field, and
    a '## Decision' heading. Same shape as the ADR-011 gate.
    """
    assert ADR_012.exists(), (
        f"MLCL-04 plan artifact missing: {ADR_012}\n"
        "The Phase 05 Plan 04 (MLCL-04) requires this ADR codifying the "
        "extended-backtest disposition. Restore from git history if deleted."
    )

    line_count = _non_blank_line_count(ADR_012)
    assert line_count >= 30, (
        f"ADR-012 has only {line_count} non-blank lines; plan requires >=30.\n"
        f"File: {ADR_012}"
    )

    text = ADR_012.read_text(encoding="utf-8")
    assert "ADR-012" in text, (
        f"ADR-012 must self-identify (substring 'ADR-012' missing).\nFile: {ADR_012}"
    )
    assert "Status:" in text, (
        f"ADR-012 must contain a 'Status:' field "
        f"(per standard ADR template).\n"
        f"File: {ADR_012}"
    )
    has_decision_heading = re.search(r"(?m)^## Decision\b", text) is not None
    assert has_decision_heading, (
        "ADR-012 must contain a '## Decision' heading (per standard ADR sections).\n"
        f"File: {ADR_012}"
    )
