"""Phase 12 CIRESTORE-03 — Billing-failure-detector workflow grep gates + detection-logic unit tests.

Twelve tests guard the contract of `.github/workflows/billing-failure-detector.yml`,
the cron-driven workflow that catches GitHub Actions billing-blocked runs and posts a
Telegram alert + opens a labelled GitHub Issue.

Two test classes:

1. **Grep gates** (tests 1-8, 12) — dual-form scan (pathlib + subprocess `grep`) over the
   single workflow file. These FAIL at RED phase because the workflow file does not yet
   exist; they PASS once Task 2 ships the workflow. Pattern lineage:
   `tests/integration/test_dashlive_grep_gates.py` and
   `tests/integration/test_preflight_grep_gates.py`.

2. **Pure-Python detection logic** (tests 9, 10, 11) — exercise the local
   `_detect_billing` helper which mirrors the workflow's jq pipeline. These PASS at
   RED phase already because they exercise the test-module's own helper, not the
   workflow file.

Self-trigger blocker (advisor-flagged during planning):
The workflow `name:` MUST NOT contain the literal `billing` (case-insensitive). If
it did, the detector's own failure rows would match its own substring filter and
recur every cron tick — infinite alert loop. Test 6 enforces the name constraint;
test 7 enforces the defense-in-depth jq `select(.name != ...)` filter.

Security rule (no event-payload interpolation):
The workflow has only `schedule` + `workflow_dispatch` triggers — no event payload
exists. Any `${{ github.event.* }}` reference in a `run:` shell block would be a
bug. Test 5 grep-gates against this regression.

Stdlib-only constraint:
`tests/integration/requirements.txt` does NOT list pyyaml. This module imports ONLY
`re`, `subprocess`, `pathlib`, `pytest` — matching the convention of
`test_dashlive_grep_gates.py` and `test_preflight_grep_gates.py`.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path



# ---------------------------------------------------------------------------
# Module-level constants — SCOPE IS LOAD-BEARING.
#
# REPO_ROOT resolves from this file's location. Scope is intentionally a single
# file: the billing-failure-detector workflow. Pattern from
# test_dashlive_grep_gates.py / test_preflight_grep_gates.py.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "billing-failure-detector.yml"
DETECTOR_OWN_NAME = "CI Health Monitor (CIRESTORE-03)"


# ---------------------------------------------------------------------------
# Pure-Python detection helper — mirrors the workflow's jq pipeline.
#
# jq form: [.[] | select(.name != own_name) | select(.displayTitle | ascii_downcase
#           | contains("billing"))] | length > 0
# ---------------------------------------------------------------------------


def _detect_billing(runs, own_name=DETECTOR_OWN_NAME):
    """Return True iff any run row's displayTitle (case-insensitive) contains
    'billing' AND that row's name is NOT the detector's own workflow name
    (self-trigger prevention via name-equality exclusion).
    """
    for r in runs:
        if (r.get("name") or "") == own_name:
            continue  # self-trigger prevention
        if "billing" in (r.get("displayTitle") or "").lower():
            return True
    return False


# ---------------------------------------------------------------------------
# Grep gates — Tests 1-8, 12. RED at first run (workflow file absent).
# ---------------------------------------------------------------------------


def test_workflow_file_exists():
    """Workflow file must exist at the expected path."""
    assert WORKFLOW_PATH.exists(), (
        f"Expected workflow at {WORKFLOW_PATH} — Task 2 (GREEN phase) must ship it."
    )


def test_workflow_cron_schedule_locked():
    """The cron schedule literal `cron: '0 */6 * * *'` is locked per CONTEXT.md
    Locked Decision #2 (every 6 hours, on the hour)."""
    assert WORKFLOW_PATH.exists()
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    literal = "cron: '0 */6 * * *'"
    assert literal in text, (
        f"Locked cron schedule {literal!r} missing from workflow — "
        "see 12-CONTEXT.md Locked Decision #2."
    )
    # Fidelity to the literal CI grep command. Scope MUST be WORKFLOW_PATH only.
    result = subprocess.run(
        ["grep", "-F", literal, str(WORKFLOW_PATH)],
        capture_output=True,
        text=True,
    )
    assert result.stdout, (
        f"subprocess grep returned no matches for {literal!r} under {WORKFLOW_PATH}."
    )


def test_workflow_uses_gh_run_list_limit_5():
    """Detection query literal `gh run list --status failure --limit 5` is locked.
    Increasing the limit would widen the false-positive window; lowering would
    risk missing recent billing events between cron ticks."""
    assert WORKFLOW_PATH.exists()
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    literal = "gh run list --status failure --limit 5"
    assert literal in text, f"Locked detection query {literal!r} missing from workflow."
    result = subprocess.run(
        ["grep", "-F", literal, str(WORKFLOW_PATH)],
        capture_output=True,
        text=True,
    )
    assert result.stdout, (
        f"subprocess grep returned no matches for {literal!r} under {WORKFLOW_PATH}."
    )


def test_workflow_creates_issue_with_ops_billing_label():
    """The literal `ops: billing` must appear >= 2 times (label-create + issue-create).
    Locked per CONTEXT.md Locked Decision #3 — used by the existing alerting taxonomy."""
    assert WORKFLOW_PATH.exists()
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    literal = "ops: billing"
    count = text.count(literal)
    assert count >= 2, (
        f"Expected literal {literal!r} >= 2 occurrences (label-create + issue-create); "
        f"found {count}."
    )
    result = subprocess.run(
        ["grep", "-cF", literal, str(WORKFLOW_PATH)],
        capture_output=True,
        text=True,
    )
    grep_count = int((result.stdout or "0").strip() or 0)
    assert grep_count >= 2, (
        f"subprocess grep -cF returned {grep_count} occurrences of {literal!r}; "
        "expected >= 2."
    )


def test_workflow_no_user_controlled_event_interpolation():
    """Security regression detector. Workflow has only `schedule` + `workflow_dispatch`
    triggers — there is NO event payload to legitimately interpolate. Any
    `${{ github.event.* }}` reference in non-comment text is a command-injection
    surface and must be zero.

    Pure regex (no yaml import) — strips line comments first, then counts hits in
    the remainder. Matches the `preflight-live-readiness.yml` header-comment
    security convention (no event-payload interpolation in run: blocks)."""
    assert WORKFLOW_PATH.exists()
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # Strip line-comments (lines whose first non-whitespace char is '#').
    non_comment = "\n".join(
        ln for ln in text.splitlines() if not re.match(r"^\s*#", ln)
    )
    hits = re.findall(r"\$\{\{\s*github\.event\.", non_comment)
    assert hits == [], (
        f"Forbidden github.event.* interpolation found in non-comment text: "
        f"{len(hits)} match(es). Workflow has only schedule + workflow_dispatch "
        "triggers — no event payload exists to interpolate."
    )


def test_workflow_name_does_not_contain_billing_literal():
    """SELF-TRIGGER PREVENTION (advisor-flagged blocker during planning).

    The top-level workflow `name:` value MUST NOT contain the literal `billing`
    (case-insensitive). If it did, the detector's own scheduled-run failures would
    surface in `gh run list` with a displayTitle inheriting that name, match the
    detector's own substring filter, and post another alert — infinite loop.

    Parses the workflow text for the first top-level `name:` line via regex (no
    yaml import) and asserts the captured value does not lowercase-contain `billing`.
    """
    assert WORKFLOW_PATH.exists()
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    m = re.search(r"^name:\s*(.+?)\s*$", text, flags=re.MULTILINE)
    assert m, "workflow file has no top-level `name:` key"
    name_value = m.group(1).strip().strip("'\"")
    assert "billing" not in name_value.lower(), (
        f"Workflow name {name_value!r} contains 'billing' — detector will self-trigger "
        "on its own failures (advisor-flagged blocker). Rename to e.g. "
        "'CI Health Monitor (CIRESTORE-03)'."
    )


def test_workflow_self_trigger_filter_present():
    """Defense-in-depth: the jq pipeline must filter out the detector's own
    workflow rows. Even if Test 6 misses a future rename that re-adds `billing`
    to the name, this filter still prevents the loop.

    The literal `select(.name != "CI Health Monitor (CIRESTORE-03)")` must appear
    (and is expected >=2 times across the detect + summary + issue-body jq calls,
    per Task 2 spec). This test asserts >=1 (lower bound); the plan-level
    verification asserts >=2."""
    assert WORKFLOW_PATH.exists()
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    literal = 'select(.name != "CI Health Monitor (CIRESTORE-03)")'
    assert literal in text, (
        f"Self-trigger guard {literal!r} missing from jq pipeline — workflow would "
        "alert on its own failures."
    )
    result = subprocess.run(
        ["grep", "-F", literal, str(WORKFLOW_PATH)],
        capture_output=True,
        text=True,
    )
    assert result.stdout, (
        "subprocess grep returned no matches for the self-trigger guard literal."
    )


def test_workflow_telegram_secret_env_injected_and_masked():
    """Telegram bot token must be (a) env-injected via secrets, (b) masked via
    `::add-mask::` before any other step. Additionally, any line containing the
    expansion `$TELEGRAM_BOT_TOKEN` (unbraced form — the leak vector) MUST appear
    only in curl / api.telegram.org contexts, OR be the env-injection mapping
    line itself, OR be the mask step itself.

    The workflow uses the braced form `${TELEGRAM_BOT_TOKEN}` everywhere, so the
    unbraced-form check is a defense-in-depth gate against future regressions that
    forget the braces."""
    assert WORKFLOW_PATH.exists()
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "${{ secrets.TELEGRAM_BOT_TOKEN }}" in text, (
        "Telegram bot token must be env-injected via `${{ secrets.TELEGRAM_BOT_TOKEN }}`."
    )
    assert "::add-mask::" in text, (
        "Telegram bot token must be masked via `::add-mask::` before any other step."
    )
    for ln in text.splitlines():
        if "$TELEGRAM_BOT_TOKEN" not in ln:
            continue
        # Allow the env-injection mapping line itself + the mask step.
        if "::add-mask::" in ln or "TELEGRAM_BOT_TOKEN: ${{ secrets" in ln:
            continue
        assert ("curl" in ln) or ("api.telegram.org" in ln), (
            f"Bare $TELEGRAM_BOT_TOKEN expansion outside curl / api.telegram.org "
            f"context: {ln!r}"
        )


# ---------------------------------------------------------------------------
# Pure-Python detection logic — Tests 9, 10, 11. PASS at RED phase already.
# ---------------------------------------------------------------------------


def test_detection_substring_matches_billing_case_insensitive():
    """A foreign workflow's failure row whose displayTitle (case-insensitive) contains
    `billing` MUST be detected."""
    rows = [
        {"displayTitle": "Billing blocked", "name": "Some Other Workflow"},
    ]
    assert _detect_billing(rows) is True


def test_detection_silent_on_no_billing_payload():
    """A payload with no `billing` substring in any displayTitle MUST NOT detect."""
    rows = [
        {"displayTitle": "Test failure: assertion error", "name": "CI Build"},
        {"displayTitle": "Timeout in step 4", "name": "Nightly Suite"},
        {"displayTitle": "Linter caught unused import", "name": "Lint"},
    ]
    assert _detect_billing(rows) is False


def test_detection_silent_on_detector_own_failure_row():
    """A payload containing only the detector's own failure row MUST NOT detect
    (self-trigger prevention)."""
    rows = [
        {
            "displayTitle": "billing failure during cron",
            "name": "CI Health Monitor (CIRESTORE-03)",
        },
    ]
    assert _detect_billing(rows, "CI Health Monitor (CIRESTORE-03)") is False


# ---------------------------------------------------------------------------
# Grep gate — Test 12. Idempotent label-create.
# ---------------------------------------------------------------------------


def test_ops_billing_label_created_idempotently():
    """Every `gh label create` line must end with `|| true` so first-run on a fresh
    repo (label doesn't exist) and re-run on a repo with the label already created
    (422 from gh) both succeed silently."""
    assert WORKFLOW_PATH.exists()
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    label_create_lines = [ln for ln in text.splitlines() if "gh label create" in ln]
    assert label_create_lines, "no `gh label create` invocation found in workflow"
    for ln in label_create_lines:
        assert re.search(r"\|\|\s*true\s*$", ln), (
            f"label-create line missing `|| true` idempotency guard: {ln!r}"
        )
