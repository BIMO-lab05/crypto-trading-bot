---
phase: 15-planning-tooling-hardening
verified: 2026-05-22T04:00:00Z
status: human_needed
score: 4/5 must-haves verified
overrides_applied: 0
deferred:
  - truth: "v1.2 milestone close demonstrates all 3 planning-tooling gates in action (SC#5)"
    addressed_in: "v1.2 milestone close (/gsd-complete-milestone v1.2)"
    evidence: "ROADMAP.md SC#5: 'v1.2 milestone close itself demonstrates all three in action (SC#5 is operator-side at /gsd-complete-milestone v1.2)'"
  - truth: "Historical placeholder at 13-04-SUMMARY.md:60 cleaned (TOOL-01 RED flips GREEN)"
    addressed_in: "v1.2 milestone close cleanup"
    evidence: "ROADMAP.md Phase 15 annotation: 'milestone-close cleanup will flip it GREEN'; 15-PATTERNS.md §1: gate intentionally RED on main at Plan 15-01 landing on exactly one real Phase 13 placeholder'"
human_verification:
  - test: "Verify TOOL-01 placeholder gate flips GREEN after v1.2 milestone-close operator cleanup"
    expected: "After operator removes/rewrites placeholder at .planning/phases/13-bybit-connector-market-data-centralization/13-04-SUMMARY.md:60 (the **Task 1 —** bold span that matches placeholder_task_n), pytest tests/ci/test_no_placeholder_one_liners.py passes 4/4"
    why_human: "Forcing function — requires operator/human to edit historical Phase 13 artifact at v1.2 milestone close. Cannot be automated by CI."
  - test: "Verify TOOL-02 wiring test flips GREEN after SDK port lands --apply invocation"
    expected: "After ~/.claude/get-shit-done/workflows/complete-milestone.md is updated to invoke 'gsd-sdk query roadmap.analyze --apply' before 'gsd-sdk query milestone.complete', pytest tests/ci/test_roadmap_analyze_supersession_wired.py::test_roadmap_analyze_apply_wired_before_archive passes (currently FAILs with apply_pos=-1, archive_pos=11526)"
    why_human: "Operator-side SDK port — complete-milestone.md lives at ~/.claude/get-shit-done/, outside the repo. Cannot be merged or tested from CI without operator action."
  - test: "Verify TOOL-03 wiring test flips GREEN after SDK port adds --accept-stale-audit check"
    expected: "After complete-milestone.md is updated to include unconditional audit-freshness check with --accept-stale-audit override flag (no SKIP_AUDIT_FRESHNESS or FORCE_ARCHIVE escape hatches), pytest tests/ci/test_audit_freshness_gate.py::test_audit_freshness_check_unconditional_in_workflow passes"
    why_human: "Same SDK port requirement as TOOL-02 human item above. Operator must add step block to complete-milestone.md containing both 'audited' + 'VERIFICATION.md' references and the literal '--accept-stale-audit' flag."
---

# Phase 15: Planning-Tooling Hardening Verification Report

**Phase Goal:** Address three recurring friction points in the GSD planning workflow — placeholder one-liners in PLAN/SUMMARY artifacts (TOOL-01), undetected umbrella→decimal phase supersession in ROADMAP.md (TOOL-02), and stale-audit drift where /gsd-complete-milestone archives against an audit that predates the latest VERIFICATION.md (TOOL-03).
**Verified:** 2026-05-22T04:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC#1 | plan.validate verb rejects 5 banned patterns in PLAN.md + SUMMARY.md; pre-commit/CI runs; 5+1 unit tests exist | VERIFIED | `tests/ci/test_no_placeholder_one_liners.py` — 4 test functions, 5 BANNED_PATTERNS dict entries, EXEMPT_PATHS list; CI job `tool-01-grep-gate` in `planning-tooling-gate.yml`; pre-commit hook installs via `scripts/install-pre-commit.sh` |
| SC#2 | roadmap.analyze detects umbrella→decimal supersession, emits diff to stdout, --apply rewrites idempotently, wired into /gsd-complete-milestone | VERIFIED (in-repo spec + fixture verified; SDK port is human_verification item) | `tests/ci/test_roadmap_analyze_supersession_wired.py` — fixture-replay tests pass (8/11); `.planning/sdk-proposals/TOOL-02-spec.md` 114 lines with full verb contract; `tests/fixtures/v15_supersession/` — scenario.json + roadmap-before.md + roadmap-after.md (1-line diff confirmed); CI job `tool-02-wiring-gate` in workflow |
| SC#3 | /gsd-complete-milestone refuses archive when audit.audited_at predates most-recent VERIFICATION.md mtime by >1h; names timestamps in error; --accept-stale-audit flag; v1.1 13h-gap fixture asserts refusal | VERIFIED (in-repo spec + fixture verified; SDK port is human_verification item) | `tests/ci/test_audit_freshness_gate.py` — 4 test functions, 3 unconditional fixture-replay tests pass; `tests/fixtures/v11_13h_gap/scenario.json` — gap.seconds=78890, exceeds_threshold=true, correct field name "audited" (not "audited_at"); `.planning/sdk-proposals/TOOL-03-spec.md` 222 lines with all sections; CI job `tool-03-freshness-gate` in workflow |
| SC#4 | CI grep gates pin all 3 contracts (3 test files, 3 named CI jobs, one workflow file) | VERIFIED | `.github/workflows/planning-tooling-gate.yml` — 3 jobs (tool-01-grep-gate, tool-02-wiring-gate, tool-03-freshness-gate); no `continue-on-error`; `permissions: contents: read`; `paths:` filter (WR-06); Python 3.12 + actions/checkout@v4 + actions/setup-python@v5; asymmetric SKIP behavior documented inline |
| SC#5 | v1.2 milestone close demonstrates all 3 in action | DEFERRED | Operator-side at /gsd-complete-milestone v1.2 — Phase 15 ships prerequisites; demonstration happens at milestone close. See deferred section. |

**Score:** 4/5 truths verified (SC#5 deferred as operator-side)

### Deferred Items

Items not yet met but explicitly addressed in later milestone phases.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | SC#5: v1.2 milestone close demonstrates all 3 in action | v1.2 milestone close | ROADMAP.md SC#5 annotation; 15-CONTEXT.md "SDK-deliverable mode" |
| 2 | TOOL-01 RED flips GREEN (historical 13-04-SUMMARY.md:60 cleanup) | v1.2 milestone close | 15-PATTERNS.md §1: "gate intentionally RED on main at Plan 15-01 landing"; CI workflow comment line 27-29 |

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/ci/test_no_placeholder_one_liners.py` | TOOL-01 grep gate (5 banned patterns, 4 tests) | VERIFIED | 5 BANNED_PATTERNS entries confirmed; BOLD_SPAN_RE with `^[ \t]*` indentation allowance (WR-05 fix); EXEMPT_PATHS list; allowlist JSON integration |
| `tests/ci/test_roadmap_analyze_supersession_wired.py` | TOOL-02 wiring + fixture gate (3 tests) | VERIFIED | Command-invocation-anchored _APPLY_PATTERN + _ARCHIVE_PATTERN (CR-02 fix); test_supersession_fixture_present + test_supersession_fixture_diff_is_one_line unconditionally GREEN |
| `tests/ci/test_audit_freshness_gate.py` | TOOL-03 freshness + fixture gate (4 tests) | VERIFIED | --accept-stale-audit literal discriminator + step-block structural anchor (CR-01 fix); FORBIDDEN_ESCAPE_HATCHES tuple; 3 unconditional fixture-replay tests GREEN |
| `tests/fixtures/v15_supersession/scenario.json` | Phase 11→11.1 supersession fixture | VERIFIED | umbrella.phase_id="11", decimal_child.phase_id="11.1"; expected_outcome.umbrella_post_supersession_status="⊘" |
| `tests/fixtures/v15_supersession/roadmap-before.md` | Roadmap before supersession | VERIFIED | `- [ ] Phase 11: Carry-In Closure` |
| `tests/fixtures/v15_supersession/roadmap-after.md` | Roadmap after supersession (1-line diff) | VERIFIED | `- [⊘] Phase 11: Carry-In Closure — superseded by Phase 11.1`; diff is exactly 1 line changed |
| `tests/fixtures/v11_13h_gap/scenario.json` | v1.1 13h-gap canonical fixture | VERIFIED | gap.seconds=78890, gap.hours=21.91, exceeds_threshold=true; field "audited" (not "audited_at") — drift documented; single audited_iso_utc field (WR-03 fix) |
| `.planning/sdk-proposals/TOOL-01-spec.md` | SDK port spec for plan.validate | VERIFIED | 186 lines; 7 sections including verb contract, 5 banned patterns, pre-commit invocation, CI invocation, 5+1 unit test contract, port path |
| `.planning/sdk-proposals/TOOL-02-spec.md` | SDK port spec for roadmap.analyze | VERIFIED | 114 lines; all required sections including verb contract, detection rule, idempotency, diff format, wiring into complete-milestone, test contract, port path |
| `.planning/sdk-proposals/TOOL-03-spec.md` | SDK port spec for audit-freshness gate | VERIFIED | 222 lines; --accept-stale-audit documented; archive_log_required; FORBIDDEN_ESCAPE_HATCHES; field-name drift documented; fixture-replay contract |
| `.github/workflows/planning-tooling-gate.yml` | CI workflow with 3 named jobs | VERIFIED | 3 jobs; no continue-on-error; permissions: contents: read (WR-04 fix); paths: filter (WR-06 fix); asymmetric SKIP documented |
| `scripts/install-pre-commit.sh` | Pre-commit hook installer | VERIFIED | Precondition check before git rev-parse (WR-01 fix); pytest availability probe (WR-02 fix); wiring tests deselected via --deselect (CR-03 fix); idempotent via marker comment |
| `tests/ci/placeholder-allowlist.json` | Allowlist for known-legitimate one-liners | VERIFIED | Content: `[]` (empty array — no allowlisted entries; Phase 13 placeholder is documented intentional RED, not allowlisted) |
| `.planning/evidence/TOOL-15/verify-stack-report.txt` | Adapted verify-stack evidence report | VERIFIED | 4-check planning-tooling-adapted report; all [PASS]; 11 tests collected confirmed |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `test_no_placeholder_one_liners.py` | `.planning/phases/` tree | `PHASES_DIR` glob scan | WIRED | Scans `**/*-PLAN.md` + `**/*-SUMMARY.md` at runtime; EXEMPT_PATHS excludes test files themselves |
| `test_roadmap_analyze_supersession_wired.py` | `tests/fixtures/v15_supersession/` | `FIXTURE_DIR` constant | WIRED | fixture_present and diff_is_one_line tests load scenario.json + diff files directly |
| `test_audit_freshness_gate.py` | `tests/fixtures/v11_13h_gap/scenario.json` | `FIXTURE_PATH` constant | WIRED | 3 fixture-replay tests load and assert against gap.seconds, gap.exceeds_threshold, audit.frontmatter_field_name |
| `test_roadmap_analyze_supersession_wired.py` | `~/.claude/get-shit-done/workflows/complete-milestone.md` | `WORKFLOW_FILE` constant | PARTIAL (intentional) | SKIPs if file absent (CI); FAILs if present but unported (operator host). Asymmetric SKIP IS the contract. |
| `test_audit_freshness_gate.py` | `~/.claude/get-shit-done/workflows/complete-milestone.md` | `WORKFLOW_FILE` constant | PARTIAL (intentional) | Same asymmetric SKIP contract as TOOL-02 wiring link. |
| `planning-tooling-gate.yml` | `tests/ci/test_no_placeholder_one_liners.py` | `pytest` invocation | WIRED | `run: pytest tests/ci/test_no_placeholder_one_liners.py -v` in tool-01-grep-gate job |
| `planning-tooling-gate.yml` | `tests/ci/test_roadmap_analyze_supersession_wired.py` | `pytest` invocation | WIRED | `run: pytest tests/ci/test_roadmap_analyze_supersession_wired.py -v` in tool-02-wiring-gate job |
| `planning-tooling-gate.yml` | `tests/ci/test_audit_freshness_gate.py` | `pytest` invocation | WIRED | `run: pytest tests/ci/test_audit_freshness_gate.py -v` in tool-03-freshness-gate job |
| `scripts/install-pre-commit.sh` | `tests/ci/test_no_placeholder_one_liners.py` | pre-commit hook body | WIRED | Hook runs `python3 -m pytest tests/ci/test_no_placeholder_one_liners.py -q` when planning files staged |
| `scripts/install-pre-commit.sh` | TOOL-02/03 fixture tests | `--deselect` filtering | WIRED (fixture only) | Deselects wiring tests; runs only fixture-validation tests in pre-commit (CR-03 fix) |

---

### Data-Flow Trace (Level 4)

Phase 15 produces CI test infrastructure and SDK proposal specs — no dynamic data rendering components. Level 4 data-flow trace not applicable (no React components, no API routes fetching DB data).

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `test_no_placeholder_one_liners.py` | `hits` (dict of pattern → [(file, line)]) | `glob` scan of `.planning/phases/` filesystem | Yes — real filesystem scan at pytest runtime | FLOWING |
| `test_roadmap_analyze_supersession_wired.py` (fixture tests) | `scenario` (dict from JSON) | `tests/fixtures/v15_supersession/scenario.json` | Yes — static fixture with real recorded values | FLOWING |
| `test_audit_freshness_gate.py` (fixture tests) | `data` (dict from JSON) | `tests/fixtures/v11_13h_gap/scenario.json` | Yes — static fixture with real recorded v1.1 gap (78890s) | FLOWING |

---

### Behavioral Spot-Checks

Pytest run output (observed during verification):

```
FAILED tests/ci/test_no_placeholder_one_liners.py::test_no_placeholder_one_liners_in_plans_and_summaries
  .planning/phases/13-bybit-connector-market-data-centralization/13-04-SUMMARY.md:60: [placeholder_task_n] Task 1 — orderbook handler refactor (TDD):
FAILED tests/ci/test_roadmap_analyze_supersession_wired.py::test_roadmap_analyze_apply_wired_before_archive
  apply_pos = -1 (gsd-sdk query roadmap.analyze --apply not in host SDK workflow)
  archive_pos = 11526 (milestone.complete command found at correct position)
FAILED tests/ci/test_audit_freshness_gate.py::test_audit_freshness_check_unconditional_in_workflow
  --accept-stale-audit not in ~/.claude/get-shit-done/workflows/complete-milestone.md
3 failed, 8 passed in 0.96s
```

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 8 unconditional tests pass | `pytest tests/ci/ -v` | 8 passed | PASS |
| Exactly 3 intentional RED tests fail | `pytest tests/ci/ -v` | 3 failed matching documented forcing functions | PASS (RED = contract) |
| TOOL-01 RED matches documented placeholder | grep `13-04-SUMMARY.md:60` | `**Task 1 — orderbook handler refactor (TDD):**` — matches `placeholder_task_n` regex | PASS |
| TOOL-02 RED: --apply not in host SDK | apply_pos check | apply_pos = -1 | PASS (forcing function) |
| TOOL-03 RED: --accept-stale-audit not in SDK | literal check | not in complete-milestone.md | PASS (forcing function) |
| Fixture v11_13h_gap threshold check | fixture assertion | gap.seconds=78890 > 3600s (1h) | PASS |
| Fixture v15_supersession 1-line diff | diff comparison | roadmap-before → roadmap-after = 1 line changed | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| TOOL-01 | 15-01-PLAN.md | plan.validate rejects 5 patterns, pre-commit/CI step, 5+1 unit tests | SATISFIED | `test_no_placeholder_one_liners.py` 5 BANNED_PATTERNS + 4 tests; CI job; pre-commit installer |
| TOOL-02 | 15-02-PLAN.md | roadmap.analyze supersession, idempotent --apply, diff-to-stdout, wired into /gsd-complete-milestone | SATISFIED (spec + fixture + CI; SDK port pending operator action) | `test_roadmap_analyze_supersession_wired.py`; `TOOL-02-spec.md`; v15_supersession fixture; CI job |
| TOOL-03 | 15-03-PLAN.md | refuses archive if audit predates verification >1h, --accept-stale-audit override, fixture replays v1.1 | SATISFIED (spec + fixture + CI; SDK port pending operator action) | `test_audit_freshness_gate.py`; `TOOL-03-spec.md`; v11_13h_gap fixture; CI job |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/ci/test_no_placeholder_one_liners.py` | (regex strings) | BANNED_PATTERNS regex literals contain `placeholder` patterns | Info | EXEMPT — test file explicitly excluded from EXEMPT_PATHS scan; regex strings are the definitions not violations |
| None (other files) | — | No TODO/FIXME/placeholder in implementation files | — | No blockers found |

No blockers. No implementation stubs. All placeholders in test file are the defining pattern literals (not violations).

---

### Human Verification Required

**3 items require human/operator action:**

#### 1. TOOL-01 RED: Historical placeholder cleanup at v1.2 milestone close

**Test:** After v1.2 milestone close, operator edits `.planning/phases/13-bybit-connector-market-data-centralization/13-04-SUMMARY.md` line 60 — rewrites or removes `**Task 1 — orderbook handler refactor (TDD):**` bold span that matches `placeholder_task_n` regex (`^Task\s+\d`). Then run `pytest tests/ci/test_no_placeholder_one_liners.py -v`.

**Expected:** All 4 tests pass (including previously-RED `test_no_placeholder_one_liners_in_plans_and_summaries` and `test_grep_command_matches_pytest_scan`).

**Why human:** Forcing function by design — the RED state pins existing Phase 13 placeholder as a visible contract until milestone-close cleanup. CI comment (line 27-29 of workflow) explicitly documents "that RED state IS the contract — milestone-close cleanup will flip it GREEN."

#### 2. TOOL-02 RED: SDK port lands --apply invocation in complete-milestone.md

**Test:** After operator ports `gsd-sdk query roadmap.analyze --apply` invocation into `~/.claude/get-shit-done/workflows/complete-milestone.md` (before `gsd-sdk query milestone.complete`), run `pytest tests/ci/test_roadmap_analyze_supersession_wired.py -v`.

**Expected:** `test_roadmap_analyze_apply_wired_before_archive` passes — `apply_pos` > 0 AND `apply_pos` < `archive_pos`.

**Why human:** `complete-milestone.md` lives at `~/.claude/get-shit-done/` on operator's host machine — outside the repo, not deployable via CI. Requires operator to perform SDK port per `TOOL-02-spec.md` port path section.

#### 3. TOOL-03 RED: SDK port adds unconditional audit-freshness check in complete-milestone.md

**Test:** After operator adds audit-freshness step block to `complete-milestone.md` with: (a) `--accept-stale-audit` literal, (b) references to `audited` field and `VERIFICATION.md`, (c) none of FORBIDDEN_ESCAPE_HATCHES (`SKIP_AUDIT_FRESHNESS`, `SKIP_AUDITED_AT_CHECK`, `FORCE_ARCHIVE`). Run `pytest tests/ci/test_audit_freshness_gate.py -v`.

**Expected:** `test_audit_freshness_check_unconditional_in_workflow` passes — all assertions satisfied.

**Why human:** Same SDK port requirement as TOOL-02 item above. Operator must edit `~/.claude/get-shit-done/workflows/complete-milestone.md` per `TOOL-03-spec.md` port path section.

---

### Gaps Summary

No genuine implementation gaps found.

All 3 failing tests are documented intentional RED states functioning as forcing functions:
- TOOL-01 RED: pins historical Phase 13 artifact visible to operator until v1.2 milestone-close cleanup
- TOOL-02 RED: forces SDK port of `roadmap.analyze --apply` into host workflow before milestone archiving can proceed
- TOOL-03 RED: forces SDK port of audit-freshness gate + `--accept-stale-audit` flag into host workflow

Phase 15 ships everything required to repo: CI grep gates, SDK proposal specs with full port contracts, replay fixtures, pre-commit installer, evidence report. The 3 pending items are all operator-side SDK ports + historical cleanup — by design, not gaps.

---

_Verified: 2026-05-22T04:00:00Z_
_Verifier: Claude (gsd-verifier)_
