"""TOOL-02 wiring assertion — `roadmap.analyze --apply` must precede archive.

Phase 15 contract per REQUIREMENTS.md TOOL-02:

    The SDK workflow file at
    ``~/.claude/get-shit-done/workflows/complete-milestone.md`` MUST invoke
    ``gsd-sdk query roadmap.analyze --apply`` BEFORE the
    ``gsd-sdk query milestone.complete`` archive step, so any
    umbrella→decimal supersessions land in ROADMAP.md before the
    milestone is archived and shipped read-only.

Asymmetric design per Phase 15 PATTERNS.md §2 recommendation (a):

    The workflow file lives on the OPERATOR'S host filesystem outside
    this repo. In a GitHub Actions runner, ``Path.home()`` resolves to
    ``/root`` (or whatever the runner user is) — the ``.claude/`` SDK
    install is not present. The wiring test SKIPs cleanly in that
    environment (the asymmetric-enforcement pattern of PATTERNS.md §2).

    For a developer running locally with the host SDK installed, the
    test fires:

      - PASS if the workflow has been upgraded to invoke ``--apply``
        before ``milestone.complete``;
      - FAIL with a clear wiring-violation message if the workflow file
        is present but unupgraded (today's state) — this failure is the
        forcing function that pushes the operator to port the SDK side
        per ``.planning/sdk-proposals/TOOL-02-spec.md``.

    All three terminal states (SKIP / FAIL / PASS) are valid per the
    contract — the test is asymmetric by design, not flaky.

Repo-side defence-in-depth — the two fixture-validation tests
(``test_supersession_fixture_present``,
``test_supersession_fixture_diff_is_one_line``) are unconditional:
they exercise the fixture data shape locally regardless of whether
the host SDK is installed, so the supersession detection rule is
pinned in this repo's CI even when the wiring test SKIPs.

Cross-references:
- Fixture data: ``tests/fixtures/v15_supersession/`` (Plan 15-02 Task 1)
- SDK spec: ``.planning/sdk-proposals/TOOL-02-spec.md`` (Plan 15-02 Task 2)
- Plan 15-04 will chain this test into ``.github/workflows/`` as a
  required PR check (Tampering mitigation T-15-04).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Paths.
#
# WORKFLOW_FILE: operator-host SDK install. Absent in CI runners.
# REPO_ROOT:     tests/ci/test_*.py -> parents[2] resolves to the repo root,
#                including under Claude Code worktree layouts
#                (.claude/worktrees/agent-<id>/tests/ci/...).
# FIXTURE_*:     in-repo, always present once Plan 15-02 Task 1 lands.
# ---------------------------------------------------------------------------
WORKFLOW_FILE = (
    Path.home() / ".claude" / "get-shit-done" / "workflows" / "complete-milestone.md"
)
REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "v15_supersession"
FIXTURE_SCENARIO = FIXTURE_DIR / "scenario.json"
FIXTURE_BEFORE = FIXTURE_DIR / "roadmap-before.md"
FIXTURE_AFTER = FIXTURE_DIR / "roadmap-after.md"
SDK_SPEC = REPO_ROOT / ".planning" / "sdk-proposals" / "TOOL-02-spec.md"


# Match a `gsd-sdk query roadmap.analyze --apply` invocation that begins a
# real shell-command line — not a prose mention inside backticks or admonition
# blocks. The previous loose regex (`^[^#<\n]*roadmap\.analyze\s+--apply`)
# matched any line whose start character was not `#` or `<`, which silently
# anchored on prose `**Note:**` lines that mentioned the command in inline
# backticks (e.g., the line-221 note in the current host workflow:
# `**Note:** MILESTONES.md entry is now created automatically by
# `gsd-sdk query milestone.complete`...`). Once the operator ports the SDK
# and the `--apply` step lands at a position AFTER the line-221 prose mention
# of `milestone.complete`, the ordering check would FAIL with a misleading
# error blaming step order — even though the order is correct.
#
# New shape: require the line to BEGIN (after optional leading whitespace and
# an optional shell variable-capture prefix like `RESULT=$(`) with literal
# `gsd-sdk query roadmap.analyze --apply`. This excludes prose mentions
# (where the command is wrapped in backticks somewhere in the middle of an
# English sentence) but accepts both bare invocations and command-substitution
# captures, which are the only two shapes the spec sanctions. `\b` after
# `--apply` prevents accidentally matching a longer flag like
# `--apply-nothing`.
_APPLY_PATTERN = re.compile(
    r"^[ \t]*(?:[A-Za-z_][A-Za-z0-9_]*=\$\()?\s*gsd-sdk\s+query\s+roadmap\.analyze\s+--apply\b",
    re.MULTILINE,
)
# Same shape for the archival invocation. The `milestone.complete` literal is
# followed by a positional argument (e.g. `"v1.0"`) in the spec; we accept any
# trailing content after the command name. Excludes prose mentions of
# `milestone.complete` inside backticks in admonition blocks.
_ARCHIVE_PATTERN = re.compile(
    r"^[ \t]*(?:[A-Za-z_][A-Za-z0-9_]*=\$\()?\s*gsd-sdk\s+query\s+milestone\.complete\b",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Wiring assertion — SKIP if workflow absent, else assert ordering.
# ---------------------------------------------------------------------------
def test_roadmap_analyze_apply_wired_before_archive() -> None:
    """``--apply`` must invoke before the ``milestone.complete`` archive.

    SKIP when the operator-side SDK workflow file is not installed (the
    CI-runner case). FAIL with a clear wiring message when the file is
    present but the ``--apply`` step is missing or follows the archive
    (the developer-local-pre-port case). PASS when the workflow has been
    upgraded per ``.planning/sdk-proposals/TOOL-02-spec.md``.
    """
    if not WORKFLOW_FILE.exists():
        pytest.skip(
            f"complete-milestone workflow not present at {WORKFLOW_FILE} — "
            "operator-side SDK install not detected. The TOOL-02 wiring "
            "contract is documented in "
            ".planning/sdk-proposals/TOOL-02-spec.md; this test fires once "
            "the SDK is upgraded."
        )

    text = WORKFLOW_FILE.read_text()

    apply_match = _APPLY_PATTERN.search(text)
    archive_match = _ARCHIVE_PATTERN.search(text)
    apply_pos = apply_match.start() if apply_match else -1
    archive_pos = archive_match.start() if archive_match else -1

    assert apply_pos >= 0, (
        f"`gsd-sdk query roadmap.analyze --apply` invocation not found in "
        f"{WORKFLOW_FILE}. The TOOL-02 contract requires this step before "
        f"the archive — see .planning/sdk-proposals/TOOL-02-spec.md for "
        f"the verb spec and the wiring step to add to the workflow."
    )
    assert archive_pos >= 0, (
        f"`gsd-sdk query milestone.complete` invocation not found in "
        f"{WORKFLOW_FILE}. The wiring test cannot verify ordering without "
        f"both anchors; check the workflow source."
    )
    assert apply_pos < archive_pos, (
        f"`roadmap.analyze --apply` must invoke before `milestone.complete` "
        f"in {WORKFLOW_FILE} (apply_pos={apply_pos}, archive_pos="
        f"{archive_pos}). Re-order the steps so umbrella supersessions are "
        f"applied to ROADMAP.md before the milestone is archived read-only.\n"
        f"  --apply context  : {text[max(0, apply_pos) : apply_pos + 200]!r}\n"
        f"  archive context  : {text[max(0, archive_pos) : archive_pos + 200]!r}"
    )


# ---------------------------------------------------------------------------
# Defence-in-depth: fixture data ships in-repo and is exercised
# unconditionally regardless of host-SDK presence.
# ---------------------------------------------------------------------------
def test_supersession_fixture_present() -> None:
    """The v15_supersession fixture ships in-repo with the canonical shape.

    The fixture replays the Phase 11 → Phase 11.1 supersession scenario
    that motivated TOOL-02. The decimal child's REQ set (LIVECLOSE-01..05)
    fully covers the umbrella's empty REQ set, so the detection rule
    fires.
    """
    assert FIXTURE_SCENARIO.exists(), (
        f"v15_supersession fixture scenario missing at {FIXTURE_SCENARIO}; "
        "Plan 15-02 Task 1 must create it before this test can run."
    )
    data = json.loads(FIXTURE_SCENARIO.read_text())

    assert data["umbrella"]["phase_id"] == "11", (
        f"umbrella.phase_id must be '11' (Phase 11 Carry-In Closure); "
        f"got {data['umbrella']['phase_id']!r}"
    )
    assert data["decimal_child"]["phase_id"] == "11.1", (
        f"decimal_child.phase_id must be '11.1' (Phase 11.1 Carry-In "
        f"Closure Harnesses); got {data['decimal_child']['phase_id']!r}"
    )
    assert len(data["decimal_child"]["requirements"]) == 5, (
        f"decimal_child.requirements must list LIVECLOSE-01..05 (5 entries); "
        f"got {len(data['decimal_child']['requirements'])} entries: "
        f"{data['decimal_child']['requirements']!r}"
    )


def test_supersession_fixture_diff_is_one_line() -> None:
    """The before/after fixture pair encodes exactly one line of change.

    The unified diff between ``roadmap-before.md`` and ``roadmap-after.md``
    IS the verb's expected output when invoked on the BEFORE state — the
    umbrella row is rewritten to ``[⊘] ... — superseded by Phase 11.1``
    and nothing else changes. The decimal-child row is untouched.
    """
    assert FIXTURE_BEFORE.exists(), (
        f"v15_supersession before fixture missing at {FIXTURE_BEFORE}; "
        "Plan 15-02 Task 1 must create it."
    )
    assert FIXTURE_AFTER.exists(), (
        f"v15_supersession after fixture missing at {FIXTURE_AFTER}; "
        "Plan 15-02 Task 1 must create it."
    )

    before = FIXTURE_BEFORE.read_text().splitlines()
    after = FIXTURE_AFTER.read_text().splitlines()

    assert len(before) == len(after), (
        f"before and after fixtures must have the same line count "
        f"(the umbrella row is REWRITTEN, not added/removed). "
        f"before={len(before)} lines, after={len(after)} lines."
    )

    differing = [i for i, (b, a) in enumerate(zip(before, after)) if b != a]
    assert len(differing) == 1, (
        f"before vs after must differ in exactly 1 line (the umbrella row); "
        f"got {len(differing)} differing lines at indices {differing}: "
        f"{[(i, before[i], after[i]) for i in differing]!r}"
    )

    changed_line = after[differing[0]]
    assert "⊘" in changed_line, (
        f"the rewritten umbrella line in roadmap-after.md must contain the "
        f"`⊘` status marker; got {changed_line!r}"
    )
    assert "superseded by Phase 11.1" in changed_line, (
        f"the rewritten umbrella line must include the supersession "
        f"annotation `superseded by Phase 11.1`; got {changed_line!r}"
    )
