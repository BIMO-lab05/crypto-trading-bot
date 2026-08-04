---
requirement: TOOL-03
phase: 15-planning-tooling-hardening
sdk_target: "~/.claude/get-shit-done/bin/lib/milestone.cjs::cmdMilestoneComplete + ~/.claude/get-shit-done/workflows/complete-milestone.md"
upstream_status: "proposal — not yet ported"
gate_pins: "tests/ci/test_audit_freshness_gate.py"
fixture: "tests/fixtures/v11_13h_gap/"
---

# TOOL-03: Audit-Freshness Gate + `--accept-stale-audit` Override

Spec for the `/gsd-complete-milestone` audit-freshness gate. The verb refuses
to archive a milestone when the most recent MILESTONE-AUDIT.md predates the
most recent phase VERIFICATION.md mtime by more than 1 hour. Override flag
`--accept-stale-audit` is documented and supported; it logs the override into
the archive output so future readers see the deliberate bypass.

This document is the canonical port-target for the upstream SDK
(`~/.claude/get-shit-done/`). The wiring gate at
`tests/ci/test_audit_freshness_gate.py` pins the contract; the canonical
replay fixture at `tests/fixtures/v11_13h_gap/scenario.json` pins the
arithmetic.

## Gate behavior

Before the `archive_milestone` step (currently `~/.claude/get-shit-done/bin/lib/milestone.cjs::cmdMilestoneComplete`), the workflow runs the freshness check:

1. Resolve the latest `v[X.Y]-MILESTONE-AUDIT.md` under
   `.planning/milestones/` (path template, with `[X.Y]` = the milestone
   version being closed).
2. Parse YAML frontmatter; read the `audited:` field as an ISO-8601 UTC
   timestamp.
3. Glob `.planning/phases/*/VERIFICATION.md` (current-milestone phase
   directory) and compute the maximum filesystem mtime across all matches.
4. Compute `gap_seconds = max_verification_mtime - audited`.
5. If `gap_seconds > 3600` (1.0 hour) AND `--accept-stale-audit` was NOT
   passed: refuse archive with a structured error.
6. If `gap_seconds > 3600` AND `--accept-stale-audit` WAS passed: proceed with
   archive AND record a log entry in the archive output noting the deliberate
   override + the gap value + the audit timestamp + the offending
   VERIFICATION.md path.
7. If `gap_seconds <= 3600`: proceed with archive normally (no log entry,
   no warning — the gate is satisfied).

The structured error message MUST contain:

- The audit timestamp value (`2026-05-18T02:55:00Z` form).
- The path of the most-recent VERIFICATION.md that pushed the gap over the
  threshold.
- The computed gap in human-readable form (hours, to 2 decimals).
- A pointer to the `--accept-stale-audit` flag as the sanctioned override
  with a one-line explanation that the override is logged into the archive.

Threshold edge case: the comparison is strict `>`, not `>=`. A gap of exactly
1.0h does NOT trigger refusal — only `>1h` does. This matches the ROADMAP
spec wording "predates the most recent phase's VERIFICATION.md modification
time by >1h".

## Field name canonical form

The frontmatter field is `audited:` (per
`~/.claude/get-shit-done/templates/audit-milestone.md:172` and both the v1.0
and v1.1 MILESTONE-AUDIT.md frontmatters). REQUIREMENTS.md TOOL-03 uses the
generic English term `audited_at` in prose, but the actual implementation
MUST read the `audited:` key.

The upstream SDK port reads `fm.audited`, NOT `fm.audited_at`. If the
frontmatter `audited:` field is missing or unparseable, the gate must refuse
with an explicit error pointing at the missing field — silent passes are
forbidden.

This drift between the requirement-doc prose and the canonical implementation
key is recorded in the canonical replay fixture
(`tests/fixtures/v11_13h_gap/scenario.json` — see `audit.frontmatter_field_name`
and `audit.frontmatter_field_name_drift_note`) and pinned by
`test_audit_freshness_field_name_drift_documented`.

## Override flag

`--accept-stale-audit` is the operator escape valve for emergency closes. Its
exact behavior:

- The workflow proceeds with archive (exit code 0).
- The stale-audit fact is logged INTO the archive output. The log entry
  MUST include: the audit timestamp (ISO-8601 UTC), the offending
  VERIFICATION.md path, the computed gap in hours (2 decimals), and a marker
  that the override was passed explicitly (e.g. `override: --accept-stale-audit`).
- The override does NOT silently disable the check. The check still runs;
  only the refusal-on-gap behavior is suppressed in favor of a logged
  warning.
- The override flag DOES NOT affect any other behavior in the workflow. It
  is a one-shot override; subsequent milestone closes re-run the check.

Per CONTEXT.md §Specifics line 86: "the override flag MUST log into the
archive so future readers see the stale-audit was explicitly accepted, not
silently bypassed." This is the audit-trail invariant — `--accept-stale-audit`
is the ONLY way to bypass the gate, and using it leaves a permanent record.

## Forbidden escape hatches

The following silent-skip tokens MUST NOT appear in the workflow source at
`~/.claude/get-shit-done/workflows/complete-milestone.md`:

- `SKIP_AUDIT_FRESHNESS`
- `SKIP_AUDITED_AT_CHECK`
- `FORCE_ARCHIVE`

And no `if FORCE_*` / `if SKIP_*` env-var-checked silent-skip patterns are
permitted. The intent: the only way to bypass the gate is the explicit
`--accept-stale-audit` flag, which produces an archive log entry. Silent
env-var overrides defeat the audit-trail purpose of the gate and are
forbidden by the CI grep gate at
`tests/ci/test_audit_freshness_gate.py::test_audit_freshness_check_unconditional_in_workflow`.

If a future operator-side need emerges for a non-flag bypass (e.g.
automation-driven archive in a CI environment), the gate's
`--accept-stale-audit` flag is the right answer — the CI invocation can pass
it explicitly, and the archive log entry will record the automation as the
override source. Adding a silent env-var escape hatch is not acceptable.

## Fixture replay

The canonical replay scenario is `tests/fixtures/v11_13h_gap/scenario.json`.
Its timestamps are extracted from the real v1.1 milestone:

- `audit.audited_iso_utc`: `2026-05-18T02:55:00Z` (v1.1 MILESTONE-AUDIT.md
  frontmatter line 3, field name `audited:`).
- `verification.mtime_iso_utc`: `2026-05-19T00:49:50Z` (Phase 12 CI Recovery
  VERIFICATION.md filesystem mtime, captured pre-worktree-reset).
- `gap.seconds`: `78890` (precisely `(verification - audit).total_seconds()`).
- `gap.hours`: `21.91`.
- `gap.exceeds_threshold`: `true` (well above the 1.0h threshold).
- `expected_outcome.default_invocation`: `refuse_archive`.
- `expected_outcome.with_override_flag`: `--accept-stale-audit`.
- `expected_outcome.with_override_outcome`: `archive_with_logged_warning`.

The historical "v1.1 13h-gap" label is from an initial planning estimate; the
precise computed gap is 21.91h. The label is retained as the scenario ID
(`v11-13h-gap`) for cross-reference continuity.

The fixture is read-only static JSON — no docker bind-mount, no fresh-clone
bootstrap. Consumer pattern: load via `json.loads(scenario_path.read_text())`.

## Unit test contract

The upstream SDK verb's unit tests must cover all of the following cases.
Each case asserts both the exit code and the archive output content
(presence or absence of the log warning entry).

(a) **Standard refuse**: gap > 1h, no override flag → exit non-zero, error
    message names the audit timestamp + VERIFICATION.md path + the gap in
    hours, mentions `--accept-stale-audit` as the override. No archive
    produced.

(b) **Standard override**: gap > 1h, `--accept-stale-audit` passed → exit 0,
    archive proceeds, archive output contains a log entry recording the
    audit timestamp + VERIFICATION.md path + gap_hours + an explicit
    `override` marker. Test asserts the log entry text contains all four
    fields.

(c) **No gap, no override**: gap < 1h → exit 0, archive produced, NO log
    warning entry in archive output (the gate was satisfied silently).

(d) **Threshold edge**: gap == 1.0h exactly → exit 0, archive produced, NO
    log warning (strict `>`, not `>=`).

(e) **Missing `audited:` frontmatter field**: the latest MILESTONE-AUDIT.md
    lacks the `audited:` key → exit non-zero with an explicit error pointing
    at the missing field. NOT a silent pass.

(f) **Missing VERIFICATION.md files**: the
    `.planning/phases/*/VERIFICATION.md` glob returns empty → exit non-zero
    with an explicit error noting that the freshness comparison cannot run
    without verification artifacts. NOT a silent pass.

(g) **Canonical fixture replay**: load
    `tests/fixtures/v11_13h_gap/scenario.json`, replay the scenario by
    setting up a temporary `.planning/milestones/v1.1-MILESTONE-AUDIT.md`
    with `audited: 2026-05-18T02:55:00Z` and a `.planning/phases/*/VERIFICATION.md`
    with mtime forced to `2026-05-19T00:49:50Z`, run `cmdMilestoneComplete`
    without the override flag, assert refusal. Then re-run with
    `--accept-stale-audit`, assert exit 0 and the logged warning entry is
    present in the archive output.

## Port path

The upstream SDK port lands in two files:

1. **`~/.claude/get-shit-done/bin/lib/milestone.cjs::cmdMilestoneComplete`**.
   Currently archives unconditionally (per PATTERNS.md §1, lines 91-271 of
   the analog file). Add a pre-archive freshness check:
   - Read `audited:` from the latest MILESTONE-AUDIT.md frontmatter.
   - Walk `.planning/phases/*/VERIFICATION.md` for the max mtime.
   - Compute the gap; refuse with a structured error unless
     `--accept-stale-audit` is passed.
   - On override, write the log entry into the archive output.

2. **`~/.claude/get-shit-done/workflows/complete-milestone.md`**. Currently
   has no pre-archive freshness step. Insert a step between the existing
   `gsd-sdk query roadmap.analyze` invocation (current line 87) and the
   `gsd-sdk query milestone.complete` invocation (current line 415).

   The new step text MUST contain both the literal token `audited` AND the
   literal token `VERIFICATION.md` so the TOOL-03 wiring gate's grep search
   in `tests/ci/test_audit_freshness_gate.py::test_audit_freshness_check_unconditional_in_workflow`
   succeeds. The step text MUST NOT contain any of the forbidden
   escape-hatch tokens (`SKIP_AUDIT_FRESHNESS`, `SKIP_AUDITED_AT_CHECK`,
   `FORCE_ARCHIVE`).

   The override flag `--accept-stale-audit` propagates from the workflow's
   user-facing args through `gsd-sdk query milestone.complete --accept-stale-audit`
   into `cmdMilestoneComplete`.

The repo-local CI grep gate
(`tests/ci/test_audit_freshness_gate.py::test_audit_freshness_check_unconditional_in_workflow`)
SKIPs when the workflow file is absent (CI runners have no SDK install)
and fires locally to pin the contract against drift. The three other tests
in the file are unconditional fixture-replay validators that fire in CI and
locally.

Plan 15-04 will chain the CI grep gate into the planning-tooling CI workflow
so PR-time checks fail on any workflow-source drift.
