"""TOOL-03 audit-freshness wiring gate — pin the /gsd-complete-milestone contract.

Phase 15-03 contract per REQUIREMENTS.md TOOL-03 + ROADMAP success criterion 3:

    /gsd-complete-milestone MUST refuse to archive when the latest
    v[X.Y]-MILESTONE-AUDIT.md `audited:` frontmatter timestamp predates the
    most recent phase VERIFICATION.md mtime by >1 hour. Error message names
    the stale audit timestamp + the offending VERIFICATION.md path. Override
    flag --accept-stale-audit is documented and supported; it produces an
    archive log entry recording the deliberate override. Silent-skip env vars
    (SKIP_AUDIT_FRESHNESS, SKIP_AUDITED_AT_CHECK, FORCE_ARCHIVE) are
    explicitly forbidden — the only way to bypass is the documented flag,
    which leaves an audit trail.

Asymmetric enforcement (per PATTERNS.md §2):

    The wiring test ``test_audit_freshness_check_unconditional_in_workflow``
    targets ``~/.claude/get-shit-done/workflows/complete-milestone.md`` which
    lives on the operator's host outside the repo. In CI runners that file is
    absent — the wiring test ``pytest.skip``s with a clear message pointing
    at .planning/sdk-proposals/TOOL-03-spec.md. Locally, with the SDK
    installed, the test fires and pins the workflow source against drift
    (token presence + forbidden-token absence).

    The three fixture-replay tests are unconditional — they validate the
    in-repo canonical fixture data regardless of the operator's SDK install
    state. They guarantee the audit-vs-verification gap arithmetic and the
    field-name drift documentation stay consistent forever.

Field-name canonical form:

    The frontmatter field name is ``audited:`` (per
    ``~/.claude/get-shit-done/templates/audit-milestone.md:172`` and both v1.0
    and v1.1 audit files). REQUIREMENTS.md TOOL-03 uses the generic English
    prose term ``audited_at`` but the upstream SDK port must read the
    ``audited:`` key. ``test_audit_freshness_field_name_drift_documented``
    asserts both forms are recorded in the fixture so future maintainers
    don't "fix" the fixture to the wrong key.

See:
    - ``tests/fixtures/v11_13h_gap/scenario.json`` — canonical replay fixture.
    - ``.planning/sdk-proposals/TOOL-03-spec.md`` — upstream SDK port spec.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Paths. REPO_ROOT — ``tests/ci/test_audit_freshness_gate.py`` -> ``parents[2]``
# == repo root. Resolved ONCE at module import time (same perf discipline as
# tests/ci/test_no_bybit_bypass.py — per-file ``.resolve()`` calls are
# expensive on WSL2 filesystems).
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_FILE = (
    Path.home() / ".claude" / "get-shit-done" / "workflows" / "complete-milestone.md"
)
FIXTURE_SCENARIO = REPO_ROOT / "tests" / "fixtures" / "v11_13h_gap" / "scenario.json"

# ---------------------------------------------------------------------------
# Forbidden escape-hatch tokens. Silent-skip env vars are NOT permitted —
# the only sanctioned bypass is the ``--accept-stale-audit`` CLI flag, which
# logs the override into the milestone archive output (audit trail
# invariant per CONTEXT.md §Specifics line 86).
# ---------------------------------------------------------------------------
FORBIDDEN_ESCAPE_HATCHES: tuple[str, ...] = (
    "SKIP_AUDIT_FRESHNESS",
    "SKIP_AUDITED_AT_CHECK",
    "FORCE_ARCHIVE",
)

# 1.0h threshold per ROADMAP spec.
THRESHOLD_HOURS: float = 1.0


# ---------------------------------------------------------------------------
# Wiring test (asymmetric — SKIPs in CI when SDK workflow absent; fires
# locally and pins the workflow source against drift).
# ---------------------------------------------------------------------------


def test_audit_freshness_check_unconditional_in_workflow() -> None:
    """The /gsd-complete-milestone workflow MUST wire an unconditional audit-
    freshness check that reads the ``audited:`` field from the latest
    MILESTONE-AUDIT.md frontmatter and compares it against the most recent
    phase VERIFICATION.md mtime. No silent-skip env vars permitted.

    SKIPs in CI runners where the operator SDK install is absent.
    """
    if not WORKFLOW_FILE.exists():
        pytest.skip(
            f"complete-milestone workflow not present at {WORKFLOW_FILE} — "
            "operator-side SDK install not detected. The TOOL-03 wiring "
            "contract is documented in .planning/sdk-proposals/TOOL-03-spec.md; "
            "this test fires once the SDK is upgraded."
        )

    text = WORKFLOW_FILE.read_text()

    # Primary discriminator — the `--accept-stale-audit` override flag is the
    # spec-mandated literal that distinguishes the unported workflow (token
    # ABSENT, gate not wired) from the ported workflow (token PRESENT,
    # operator-facing override flag in place per TOOL-03-spec.md §"Override
    # flag" + §"Port path"). The previous token-only check using `audited` +
    # `VERIFICATION.md` was a zero-signal assertion — both tokens already
    # appear in unrelated prose elsewhere in the workflow (the "Out of Scope
    # reasoning audited" success-criteria checkbox and the "From
    # VERIFICATION.md files" retrospective-extraction prose), so the
    # assertion passed both pre-port and post-port. The forcing function the
    # spec promises was broken at source. Switching to `--accept-stale-audit`
    # gives us a real RED→GREEN transition tied to the port.
    assert "--accept-stale-audit" in text, (
        "audit-freshness gate not wired in complete-milestone workflow — "
        "the `--accept-stale-audit` override flag is absent. Per "
        ".planning/sdk-proposals/TOOL-03-spec.md §'Override flag' the "
        "workflow MUST expose this flag as the sole sanctioned bypass for "
        "the audit-freshness gate; it produces an archive log entry "
        "recording the deliberate override. Silent-skip env vars are "
        "forbidden — the only sanctioned bypass is this flag. Port the "
        "workflow per TOOL-03-spec.md §'Port path' to flip this test GREEN."
    )

    # Structural anchor — locate at least one `<step name="...">…</step>`
    # block whose body contains BOTH `audited` AND `VERIFICATION.md`. This
    # pins the wiring to a real workflow step (not to any prose elsewhere in
    # the document) while staying agnostic about the step's exact name (the
    # spec says "Insert a step between" lines 87 and 415 but does not pin
    # the step's `name=` attribute, so we cannot anchor on a literal step
    # name without over-pinning). The unported workflow has no step block
    # carrying both tokens together; the ported workflow MUST have one per
    # TOOL-03-spec.md §"Port path".
    step_block_re = re.compile(r'<step\s+name="[^"]+"\s*>(.*?)</step>', re.DOTALL)
    step_bodies = [m.group(1) for m in step_block_re.finditer(text)]
    audit_steps = [
        body for body in step_bodies if "audited" in body and "VERIFICATION.md" in body
    ]
    assert audit_steps, (
        "audit-freshness gate not wired in complete-milestone workflow — "
        'no `<step name="...">` block contains BOTH the `audited` and '
        "`VERIFICATION.md` tokens together. Per "
        ".planning/sdk-proposals/TOOL-03-spec.md §'Port path' the workflow "
        "MUST insert a new step (between the line-87 `roadmap.analyze` "
        "readiness check and the line-415 `milestone.complete` archival) "
        "whose body reads the `audited:` frontmatter field from the latest "
        "MILESTONE-AUDIT.md and compares it against the most recent "
        "VERIFICATION.md mtime. The two tokens must co-occur INSIDE the "
        "step body — not scattered across unrelated prose."
    )

    # Forbidden-token absence assertion. Silent-skip env vars defeat the
    # audit-trail purpose of the gate — the only sanctioned bypass is the
    # ``--accept-stale-audit`` flag, which logs the override into the
    # archive output.
    for token in FORBIDDEN_ESCAPE_HATCHES:
        assert token not in text, (
            f"escape hatch {token!r} present in complete-milestone workflow — "
            "silent-skip env vars are forbidden by TOOL-03. The only "
            "sanctioned override is the documented --accept-stale-audit flag, "
            "which leaves an archive-log audit trail."
        )


# ---------------------------------------------------------------------------
# Fixture-replay tests (unconditional — fire in CI and locally).
# ---------------------------------------------------------------------------


def test_audit_freshness_fixture_present() -> None:
    """The canonical v1.1 13h-gap fixture exists with the expected scenario_id
    and refuse_archive default outcome."""
    assert FIXTURE_SCENARIO.exists(), (
        f"canonical fixture missing at {FIXTURE_SCENARIO} — Plan 15-03 Task 1 "
        "must produce this file."
    )
    fixture = json.loads(FIXTURE_SCENARIO.read_text())
    assert fixture["scenario_id"] == "v11-13h-gap", (
        f"scenario_id drift: expected 'v11-13h-gap', got {fixture.get('scenario_id')!r}"
    )
    assert fixture["gap"]["exceeds_threshold"] is True, (
        "fixture must record gap.exceeds_threshold=true — the v1.1 audit "
        "vs Phase 12 verification gap is ~21.91h, far above the 1h threshold."
    )
    assert fixture["expected_outcome"]["default_invocation"] == "refuse_archive", (
        "fixture must record default_invocation='refuse_archive' — the gate "
        "refuses to archive when the gap exceeds the threshold and no "
        "override flag is passed."
    )


def test_audit_freshness_gap_above_threshold() -> None:
    """Recompute the gap from canonical ISO timestamps in the fixture and
    assert it exceeds the 1h threshold. Cross-check the fixture's recorded
    gap.hours value matches the recomputed value (within rounding tolerance).
    """
    fixture = json.loads(FIXTURE_SCENARIO.read_text())
    audit_iso = fixture["audit"]["audited_iso_utc"]
    verification_iso = fixture["verification"]["mtime_iso_utc"]
    audit_ts = datetime.fromisoformat(audit_iso.replace("Z", "+00:00"))
    verification_ts = datetime.fromisoformat(verification_iso.replace("Z", "+00:00"))
    assert audit_ts.tzinfo == timezone.utc, "audit timestamp must be tz-aware UTC"
    assert verification_ts.tzinfo == timezone.utc, (
        "verification timestamp must be tz-aware UTC"
    )
    gap_seconds = (verification_ts - audit_ts).total_seconds()
    gap_hours = gap_seconds / 3600.0
    assert gap_hours > THRESHOLD_HOURS, (
        f"computed gap {gap_hours:.2f}h does not exceed threshold "
        f"{THRESHOLD_HOURS}h — the v1.1 13h-gap fixture is supposed to "
        "trigger refuse_archive."
    )
    # Cross-check fixture's recorded gap.hours matches recomputed value within
    # 0.01h tolerance (rounding floor).
    recorded_hours = float(fixture["gap"]["hours"])
    assert abs(recorded_hours - round(gap_hours, 2)) < 0.01, (
        f"fixture gap.hours={recorded_hours} does not match recomputed "
        f"{round(gap_hours, 2)}h. Update fixture or the canonical timestamps "
        "are inconsistent."
    )
    # Cross-check fixture's recorded gap.seconds matches recomputed value
    # exactly (integer seconds).
    recorded_seconds = int(fixture["gap"]["seconds"])
    assert recorded_seconds == int(gap_seconds), (
        f"fixture gap.seconds={recorded_seconds} does not match recomputed "
        f"{int(gap_seconds)}s."
    )


def test_audit_freshness_field_name_drift_documented() -> None:
    """The fixture MUST document the canonical-field-name drift between
    REQUIREMENTS.md TOOL-03 prose ('audited_at') and the actual
    SDK-template frontmatter field name ('audited:'). Catches future
    regressions where someone "fixes" the fixture to use 'audited_at'
    (the wrong name) thinking the spec is the authority."""
    fixture = json.loads(FIXTURE_SCENARIO.read_text())
    assert fixture["audit"]["frontmatter_field_name"] == "audited", (
        f"fixture frontmatter_field_name drift — expected 'audited', got "
        f"{fixture['audit'].get('frontmatter_field_name')!r}. The actual "
        "SDK template + v1.0/v1.1 audit files use 'audited:' as the key. "
        "If someone 'fixed' this to 'audited_at', that's the regression "
        "this test catches."
    )
    drift_note = fixture["audit"].get("frontmatter_field_name_drift_note", "")
    assert "audited_at" in drift_note, (
        "fixture frontmatter_field_name_drift_note must mention 'audited_at' "
        "explicitly to document the REQUIREMENTS.md prose drift vs. the "
        "canonical SDK field name 'audited:'."
    )
