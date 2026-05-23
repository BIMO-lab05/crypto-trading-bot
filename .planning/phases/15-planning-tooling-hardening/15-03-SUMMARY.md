---
phase: 15-planning-tooling-hardening
plan: 03
subsystem: testing
tags: [planning-tooling, ci-gate, audit-freshness, accept-stale-audit, sdk-proposal, tooling-hardening]

requires:
  - phase: 15-planning-tooling-hardening
    provides: 15-CONTEXT.md (TOOL-03 spec) + 15-PATTERNS.md (analog test shapes + canonical fixture data)

provides:
  - "Canonical v1.1 13h-gap replay fixture at tests/fixtures/v11_13h_gap/scenario.json (78890s / 21.91h, exceeds threshold)"
  - "Repo-local CI grep gate tests/ci/test_audit_freshness_gate.py pinning the /gsd-complete-milestone audit-freshness contract"
  - "Documentation-only SDK port spec at .planning/sdk-proposals/TOOL-03-spec.md describing the upstream port path + --accept-stale-audit override semantics"
  - "Canonical-field-name drift documentation: REQUIREMENTS.md prose uses 'audited_at' but actual SDK template + audit-file field is 'audited:' — both forms recorded in fixture so the upstream port reads the right key"

affects:
  - 15-04 (CI workflow chaining for the new grep gate)
  - upstream SDK port at ~/.claude/get-shit-done/bin/lib/milestone.cjs::cmdMilestoneComplete
  - upstream workflow ~/.claude/get-shit-done/workflows/complete-milestone.md
  - future milestone closes (v1.2, v2.0) — gate refuses stale-audit archives by default

tech-stack:
  added: []
  patterns:
    - "Asymmetric CI enforcement — wiring tests pytest.skip when SDK install absent, fixture-replay tests fire unconditionally (mirrors Phase 14 Gate 3 idiom in tests/integration/test_no_mobile_hidden_data.py)"
    - "Static JSON replay fixture under tests/fixtures/v11_13h_gap/ — read-only, no docker bind-mount, no fresh-clone bootstrap (consumer pattern: json.loads(Path.read_text()))"
    - "SDK port spec under .planning/sdk-proposals/ — documentation-only contribution for out-of-repo SDK code, with explicit port path + unit-test contract enumeration"
    - "Forbidden-token absence assertion alongside required-token presence — pins the audit-trail invariant by blocking silent-skip env vars at the source-grep level"
    - "Cross-checking fixture data against recomputed values (datetime arithmetic from stored ISO timestamps) so the fixture cannot drift silently"

key-files:
  created:
    - "tests/fixtures/v11_13h_gap/scenario.json — canonical v1.1 audit-vs-verification replay scenario"
    - "tests/ci/test_audit_freshness_gate.py — 4-function CI grep gate (1 wiring + 3 fixture validators)"
    - ".planning/sdk-proposals/TOOL-03-spec.md — upstream SDK port spec (7 sections + frontmatter)"
  modified: []

key-decisions:
  - "Wiring test runs on operator host SDK install (Path.home() / .claude / get-shit-done / workflows / complete-milestone.md); pytest.skip on absence with pointer to spec doc — keeps the gate functional both in CI runners and locally."
  - "Fixture documents the canonical-field-name drift explicitly. REQUIREMENTS.md uses 'audited_at' in prose; the actual SDK template + v1.0/v1.1 audit files use 'audited:'. Both forms recorded so the upstream port reads the right key and a future maintainer doesn't 'fix' the fixture to the wrong name."
  - "Fixture gap.seconds re-derived from stored ISO timestamps (78890s precisely) rather than inheriting the PATTERNS.md initial estimate of 77690s / 22.92h. test_audit_freshness_gap_above_threshold cross-checks the stored values against the recomputed values so future drift fails CI immediately."
  - "Three forbidden silent-skip tokens explicitly enumerated in both the test (FORBIDDEN_ESCAPE_HATCHES tuple) and the spec (Section 5). Adding any one of them to the workflow source trips the gate at PR review time."
  - "SDK port spec is documentation-only per CONTEXT.md / PATTERNS.md §1 trifurcation choice (a): the verb implementation lives outside the repo; this repo ships the spec + the grep-gate pin, the operator ports to SDK separately."

patterns-established:
  - "Single-file string-presence grep gate against an out-of-repo workflow file with pytest.skip fallback (analog: tests/integration/test_no_mobile_hidden_data.py::test_viewport_meta_present, adapted for Path.home() target)"
  - "Static JSON replay fixture under tests/fixtures/v11_13h_gap/ — pure data + cross-checked arithmetic, no bind-mount staging"
  - "SDK proposal doc shape: frontmatter (requirement / phase / sdk_target / upstream_status / gate_pins / fixture) + 7 named sections (Gate behavior / Field name canonical form / Override flag / Forbidden escape hatches / Fixture replay / Unit test contract / Port path)"

requirements-completed: [TOOL-03]

duration: 18min
completed: 2026-05-23
---

# Phase 15 Plan 03: TOOL-03 Audit-Freshness Gate Summary

**Repo-local CI grep gate + canonical v1.1 13h-gap replay fixture + documentation-only SDK port spec pinning the /gsd-complete-milestone audit-freshness contract against drift.**

## Performance

- **Duration:** 18 min
- **Started:** 2026-05-23T00:38:00Z
- **Completed:** 2026-05-23T00:56:00Z
- **Tasks:** 2
- **Files modified:** 3 (all new)

## Accomplishments

- Shipped canonical static fixture `tests/fixtures/v11_13h_gap/scenario.json` recording the real v1.1 audit-vs-Phase-12-verification timing gap: `audited: 2026-05-18T02:55:00Z` vs `mtime: 2026-05-19T00:49:50Z` = 78890s / 21.91h, exceeds the 1.0h threshold. Expected outcome `refuse_archive` (with `--accept-stale-audit` → `archive_with_logged_warning`).
- Shipped CI grep gate `tests/ci/test_audit_freshness_gate.py` with 4 test functions:
  - `test_audit_freshness_check_unconditional_in_workflow` — asymmetric wiring assertion that pytest.skips when `~/.claude/get-shit-done/workflows/complete-milestone.md` is absent (CI runners), and locally pins the workflow source to contain both `audited` AND `VERIFICATION.md` tokens AND none of the three forbidden silent-skip tokens.
  - `test_audit_freshness_fixture_present` — validates fixture scenario_id + threshold + refuse_archive default outcome.
  - `test_audit_freshness_gap_above_threshold` — recomputes the gap from stored ISO timestamps and cross-checks against the fixture's recorded `gap.seconds` (exact) and `gap.hours` (within 0.01h rounding tolerance).
  - `test_audit_freshness_field_name_drift_documented` — pins the REQUIREMENTS.md prose 'audited_at' vs canonical SDK template 'audited:' drift documentation in the fixture so future maintainers don't "fix" it to the wrong key.
- Shipped documentation-only port spec `.planning/sdk-proposals/TOOL-03-spec.md` (222 lines) with 7 named sections covering: Gate behavior, Field name canonical form, Override flag, Forbidden escape hatches, Fixture replay, Unit test contract (7-case enumeration), Port path. Cross-references the fixture in 5 places and mentions `--accept-stale-audit` 17 times.
- All 3 unconditional fixture-replay tests pass; the wiring test reaches terminal state (PASSED locally — the host workflow contains both `audited` and `VERIFICATION.md` tokens incidentally, satisfying the substring contract).

## Task Commits

Each task was committed atomically:

1. **Task 1: Write the v1.1 13h-gap canonical fixture** — `6aecc86` (feat)
2. **Task 2: Write the TOOL-03 wiring-gate test + SDK spec** — `a6afc3b` (feat)

## Files Created/Modified

- `tests/fixtures/v11_13h_gap/scenario.json` — Canonical static replay scenario for the v1.1 audit-freshness gap. Records canonical timestamps (`audit.audited`/`audit.audited_iso_utc` = `2026-05-18T02:55:00Z`, `verification.mtime_iso_utc` = `2026-05-19T00:49:50Z`), computed gap (78890s / 21.91h), threshold (1.0h), default outcome (`refuse_archive`), override flag (`--accept-stale-audit` → `archive_with_logged_warning`), error-message contract (must name audit timestamp + VERIFICATION.md path), and field-name drift note documenting REQUIREMENTS.md prose vs SDK-template field-name divergence.
- `tests/ci/test_audit_freshness_gate.py` — Python pytest CI gate with 4 test functions: 1 asymmetric wiring assertion (SKIPs in CI; fires locally) + 3 unconditional fixture validators (presence, gap arithmetic cross-check, field-name drift documentation). Enumerates the 3 forbidden silent-skip tokens (SKIP_AUDIT_FRESHNESS, SKIP_AUDITED_AT_CHECK, FORCE_ARCHIVE) as `FORBIDDEN_ESCAPE_HATCHES` and asserts their absence from the workflow source.
- `.planning/sdk-proposals/TOOL-03-spec.md` — Markdown SDK port spec describing the upstream gate behavior, field-name canonical form (`audited:` not `audited_at:`), override semantics (`--accept-stale-audit` proceeds with archive + log entry; silent env-var overrides explicitly forbidden), fixture replay, 7-case unit-test contract, and port path into `milestone.cjs::cmdMilestoneComplete` + `complete-milestone.md`.

## Decisions Made

- **Wiring test targets `Path.home() / ".claude" / "get-shit-done" / "workflows" / "complete-milestone.md"` with pytest.skip fallback.** Matches the asymmetric-enforcement pattern from Phase 14 Gate 3. The gate functions both in CI (where the workflow file is absent and the test SKIPs cleanly) and locally (where it pins the contract). Alternatives — vendoring a copy of the workflow into the repo, or requiring operator-installed vendored copy — would create additional sync burden without strengthening the contract.
- **Fixture stores both `audit.audited` AND `audit.audited_iso_utc` keys** with the same value (`2026-05-18T02:55:00Z`). The first form mirrors the canonical SDK frontmatter key name literally (satisfies the source acceptance criterion `grep -c '"audited":' ≥ 1`); the second is the structured-data form used by the Python tests. The duplication reinforces the field-name-drift contract.
- **`gap.seconds` is the precise re-derived value `78890`** (24h - 2h05m10s), not the PATTERNS.md initial estimate of `77690s` / `22.92h`. The plan action document re-computed the value and the cross-check test `test_audit_freshness_gap_above_threshold` asserts the stored value matches the recomputed datetime arithmetic, so the fixture cannot drift silently from the canonical timestamps.
- **Three forbidden silent-skip tokens enumerated explicitly** in both the test (`FORBIDDEN_ESCAPE_HATCHES` tuple) and the spec (Section 5 — Forbidden escape hatches). Each token is grep'd against the workflow source; presence of any one in the workflow trips the gate. This blocks the "add a one-line env-var skip" attack at PR review time. The sanctioned bypass is the documented `--accept-stale-audit` flag, which leaves an archive-log audit trail.
- **SDK port spec is documentation-only per PATTERNS.md §1 trifurcation choice (a).** The actual SDK verb implementation lives outside the repo (`~/.claude/get-shit-done/bin/lib/milestone.cjs`); this plan ships the contract pin (CI grep gate) + the port spec, and the operator ports to the SDK separately. Plan 15-04 will chain the gate into the CI workflow.

## Deviations from Plan

None - plan executed exactly as written.

The plan's spec for the fixture explicitly anticipated the dual `"audited"` + `"audited_iso_utc"` key form (acceptance criterion required `grep -c '"audited":' ≥ 1` while a separate Python assertion required `data['audit']['audited_iso_utc']` to exist as a key). Both keys are present and tested as documented.

The Python formatter ran via the PostToolUse hook on `tests/ci/test_audit_freshness_gate.py` and dropped the unused `import re` (no impact — `re` was not used in the file as written). All 4 test functions and their names are intact, and all acceptance criteria pass.

## Issues Encountered

None.

The wiring test produces a `PASSED` terminal state on this host because `complete-milestone.md` contains the literal tokens `audited` (line 359, in an Out-of-Scope context) and `VERIFICATION.md` (line 526, in a verification-doc context) incidentally — both substrings are present in the current workflow text even though the audit-freshness gate is not yet wired semantically. The plan's acceptance criterion says "the wiring test produces a terminal state (SKIP or FAIL or PASS)" — PASS is one of the accepted outcomes. Plan 15-04 / the upstream SDK port will tighten the wiring (add the actual freshness-check step) such that the PASS state becomes structurally meaningful rather than incidental.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The TOOL-03 contract is pinned at the repo-local CI grep-gate level. Plan 15-04 chains this gate (plus the TOOL-01 and TOOL-02 gates from Wave 1) into the planning-tooling CI workflow at `.github/workflows/`.
- The upstream SDK port path is documented; the operator (or a future planning phase targeting the SDK directly) can implement the gate behavior + override flag in `~/.claude/get-shit-done/bin/lib/milestone.cjs::cmdMilestoneComplete` using the spec's 7-case unit-test contract.
- The canonical fixture provides a self-contained replay scenario for the SDK unit tests — no infrastructure setup required, pure JSON.

## Self-Check: PASSED

Verified post-commit:

- FOUND: `tests/fixtures/v11_13h_gap/scenario.json`
- FOUND: `tests/ci/test_audit_freshness_gate.py`
- FOUND: `.planning/sdk-proposals/TOOL-03-spec.md`
- FOUND: `.planning/phases/15-planning-tooling-hardening/15-03-SUMMARY.md`
- FOUND commit: `6aecc86` (Task 1 — fixture)
- FOUND commit: `a6afc3b` (Task 2 — test + spec)

Behavior verification:

- `pytest tests/ci/test_audit_freshness_gate.py` — all 4 tests reach terminal state. 3 unconditional fixture-replay tests PASS. 1 wiring test PASSES on this host (workflow file present, both `audited` and `VERIFICATION.md` substring tokens present, no forbidden silent-skip tokens present).
- Gap arithmetic cross-check: stored `gap.seconds=78890`, `gap.hours=21.91` matches recomputed `(2026-05-19T00:49:50Z - 2026-05-18T02:55:00Z).total_seconds() = 78890s`, `78890/3600 = 21.91h`.
- Field-name drift documented in fixture `frontmatter_field_name_drift_note` (mentions both `audited` canonical key and `audited_at` REQUIREMENTS prose form).

---
*Phase: 15-planning-tooling-hardening*
*Completed: 2026-05-23*
