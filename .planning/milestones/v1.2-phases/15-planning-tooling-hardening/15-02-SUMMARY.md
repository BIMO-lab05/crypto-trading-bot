---
phase: 15-planning-tooling-hardening
plan: 02
subsystem: testing
tags: [ci-gate, tooling, gsd-sdk, planning, roadmap-analyze, supersession, sdk-proposal, fixture]

# Dependency graph
requires:
  - phase: 13-bybit-connector-market-data-centralization
    provides: "tests/ci/test_no_bybit_bypass.py grep-gate template (analog for single-file string-presence pattern)"
  - phase: 14-mobile-responsive-dashboard
    provides: "tests/integration/test_no_mobile_hidden_data.py::test_viewport_meta_present (single-file string-presence + pytest.skip-on-absent analog)"
provides:
  - "Repo-side wiring assertion that pins the operator-side SDK port of `roadmap.analyze --apply` (asymmetric CI gate: SKIPs in CI runners, FAILs locally pre-port, PASSes post-port)"
  - "Canonical Phase 11 → 11.1 supersession fixture (.json scenario + before/after ROADMAP fragments) for upstream SDK unit tests"
  - "Documentation-only SDK port spec at .planning/sdk-proposals/TOOL-02-spec.md (114 lines, 7 sections + frontmatter, full verb contract + detection rule + port path)"
affects: [phase-15-03, phase-15-04, gsd-complete-milestone-workflow]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Asymmetric CI gate (SKIP-in-CI, FIRE-locally) — pinning operator-side SDK contracts in repo without depending on out-of-repo host paths in CI runners"
    - "SDK port proposal directory (.planning/sdk-proposals/) — documentation-only contributions for verbs that ship outside the repo"
    - "Static-fixture replay (tests/fixtures/v15_supersession/) — JSON scenario file + before/after ROADMAP markdown fragments as the canonical supersession-detection unit-test input"

key-files:
  created:
    - tests/ci/test_roadmap_analyze_supersession_wired.py
    - tests/fixtures/v15_supersession/scenario.json
    - tests/fixtures/v15_supersession/roadmap-before.md
    - tests/fixtures/v15_supersession/roadmap-after.md
    - .planning/sdk-proposals/TOOL-02-spec.md
  modified: []

key-decisions:
  - "Picked PATTERNS.md §2 recommendation (a) — grep the operator-host SDK workflow path with pytest.skip-on-absent — over the (b) vendored-copy or (c) overlay alternatives. Asymmetry is the contract: CI runners SKIP, developer-local FAILs/PASSes."
  - "Made roadmap-before.md / roadmap-after.md fixture titles identical so the unified diff between them is exactly 1 markdown row (the umbrella line); plan prose suggested distinct (BEFORE)/(AFTER) titles but those would have inflated the diff to 4 lines and contradicted the 'exactly 1 line changed' contract."
  - "Used a regex-based first-match position-comparison (apply_pos < archive_pos) rather than line-number ordering. The workflow file may shift line numbers across upstream edits; absolute byte-offset ordering is stable."

patterns-established:
  - "Asymmetric CI gate (SKIP-on-host-SDK-absent): tests targeting paths under Path.home() / '.claude/' must SKIP cleanly when the host install is not present, and FAIL with an actionable wiring message when present-but-not-yet-upgraded. This is the design contract, not a flakiness."
  - "SDK port spec convention: documentation-only proposals under .planning/sdk-proposals/{TOOL-ID}-spec.md with frontmatter (requirement, phase, sdk_target, upstream_status, gate_pins, fixture) and 7 sections (Verb contract, Detection rule, Idempotency, Diff format, Wiring, Unit test contract, Port path)."
  - "Static-fixture replay: ROADMAP/supersession test data lives at tests/fixtures/v15_supersession/ as committed static files — no docker bind-mount, no conftest staging, no fresh-clone bootstrap. The fixture IS the unit-test input."

requirements-completed: [TOOL-02]

# Metrics
duration: ~24min
completed: 2026-05-23
---

# Phase 15 Plan 02: TOOL-02 Wiring Assertion + Supersession Fixture + SDK Port Spec Summary

**Asymmetric CI gate pinning the upstream `gsd-sdk query roadmap.analyze --apply` umbrella-supersession verb contract, plus Phase 11 → 11.1 replay fixture and 114-line SDK port spec at `.planning/sdk-proposals/TOOL-02-spec.md`.**

## Performance

- **Duration:** ~24 min
- **Started:** 2026-05-23T00:24Z (worktree branch reset)
- **Completed:** 2026-05-23T00:50Z (SUMMARY write — final commit follows)
- **Tasks:** 2
- **Files modified:** 5 new (3 fixture + 1 test + 1 spec)

## Accomplishments

- **Asymmetric wiring assertion** at `tests/ci/test_roadmap_analyze_supersession_wired.py` (208 lines, 3 tests) pins the TOOL-02 contract: the operator-side SDK workflow at `~/.claude/get-shit-done/workflows/complete-milestone.md` MUST invoke `gsd-sdk query roadmap.analyze --apply` before the `gsd-sdk query milestone.complete` archive step. The test SKIPs cleanly in CI (where `Path.home()/.claude/` is absent) and FAILs with an actionable wiring message locally pre-port (today's state) — the forcing function that pushes the upstream SDK port per `.planning/sdk-proposals/TOOL-02-spec.md`.
- **Defense-in-depth fixture-validation tests** (`test_supersession_fixture_present`, `test_supersession_fixture_diff_is_one_line`) ship as unconditional in-repo tests that exercise the supersession data shape regardless of host SDK presence — they pass on every run, anchoring the contract even when the wiring test SKIPs in CI.
- **Phase 11 → 11.1 supersession fixture** at `tests/fixtures/v15_supersession/` captures the canonical replay scenario from the v1.1 milestone close: Phase 11 (umbrella, empty REQ set) superseded by Phase 11.1 (decimal child, REQ set LIVECLOSE-01..05). The fixture exercises the empty-umbrella-REQ-set edge case (∅ ⊆ any → trivially satisfies the superset check) plus the idempotency contract (re-applying produces a no-op diff).
- **Upstream-portable SDK spec** at `.planning/sdk-proposals/TOOL-02-spec.md` (114 lines, 7 named sections — Verb contract, Detection rule, Idempotency, Diff format, Wiring, Unit test contract, Port path — plus frontmatter) gives the operator everything needed to port the verb into `~/.claude/get-shit-done/bin/lib/roadmap.cjs` and wire the new step into `complete-milestone.md`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Phase 11 → 11.1 supersession fixture** — `ea0e3cb` (test) — 3 fixture files (scenario.json + roadmap-before.md + roadmap-after.md).
2. **Task 2: Wiring assertion test + SDK port spec** — `9e0d5d8` (test) — `tests/ci/test_roadmap_analyze_supersession_wired.py` + `.planning/sdk-proposals/TOOL-02-spec.md`.

## Files Created/Modified

- `tests/ci/test_roadmap_analyze_supersession_wired.py` — Asymmetric wiring assertion + 2 unconditional fixture-validation tests. 208 lines. Module docstring explains the SKIP/FAIL/PASS terminal-state contract.
- `tests/fixtures/v15_supersession/scenario.json` — Phase 11 → 11.1 supersession scenario as JSON (umbrella + decimal_child + expected_outcome + idempotency + coverage_invariant + source_anchors).
- `tests/fixtures/v15_supersession/roadmap-before.md` — Pre-supersession ROADMAP fragment (Phase 11 marked `[ ]`, no REQ set).
- `tests/fixtures/v15_supersession/roadmap-after.md` — Post-supersession ROADMAP fragment (Phase 11 marked `[⊘]`, annotated `superseded by Phase 11.1`).
- `.planning/sdk-proposals/TOOL-02-spec.md` — 114-line upstream-portable spec with frontmatter (requirement: TOOL-02, sdk_target, upstream_status, gate_pins, fixture).

## Decisions Made

- **Picked PATTERNS.md §2 recommendation (a)** — grep the host SDK workflow path and `pytest.skip` if absent — over the alternatives (b) vendored copy in repo or (c) overlay directory. The asymmetric SKIP-in-CI behavior IS the contract per PATTERNS.md, not a workaround. Documented prominently in the test module docstring so a future maintainer doesn't "fix" the SKIP by adding the workflow file to the repo (which would couple the repo to operator-host paths).
- **Identical titles in the before/after ROADMAP fragments** — the plan prose suggested `(BEFORE)` / `(AFTER)` title differentiation but that would inflate the unified diff to 4 changed lines (1 title pair + 1 umbrella pair), contradicting the explicit "exactly 1 line changed" contract in the acceptance criteria. Fixed during execution before commit. Advisor confirmed the conflict and resolution.
- **Regex-based byte-offset ordering** for the wiring assertion (`apply_pos < archive_pos`) rather than line-number ordering. Upstream edits to the workflow file may shift line numbers; byte-offset ordering is stable across edits. The regex deliberately rejects lines starting with `#` (shell comment) or `<` (HTML comment) so that commented-out invocations in the workflow source don't accidentally satisfy the assertion.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed self-contradictory acceptance criterion for fixture diff**
- **Found during:** Task 1 (Phase 11 → 11.1 fixture)
- **Issue:** Plan prose suggested before/after files have different titles (`(BEFORE)` / `(AFTER)`) while the acceptance criterion mandated "exactly 1 line changed" in the unified diff. Distinct titles would produce a 4-line diff (1 title pair + 1 umbrella pair), causing the AC's `xargs test {} = 2` shell command to fail with count=4.
- **Fix:** Made the titles identical (`# Roadmap: Fixture v15-phase-11-supersession`) in both files. Filenames already distinguish them, so the prose distinction was redundant. The unified diff now contains exactly 1 line removed + 1 line added on the umbrella row, matching the contract.
- **Files modified:** `tests/fixtures/v15_supersession/roadmap-before.md`, `tests/fixtures/v15_supersession/roadmap-after.md`
- **Verification:** `python3 -c "..."` Python splitlines comparison confirms exactly 1 differing line index (line 4); the changed line in the after file contains both `⊘` and `superseded by Phase 11.1`. The two Python fixture-validation tests (`test_supersession_fixture_diff_is_one_line`) pass green.
- **Committed in:** `ea0e3cb` (Task 1 commit)

**2. [Rule 2 - Missing critical] Added missing position-extraction null-handling**
- **Found during:** Task 2 (wiring test implementation)
- **Issue:** The plan's pseudocode used `text.find("roadmap.analyze --apply")` which returns -1 on miss, but specified a regex-based search via `re.compile(...)`. `re.search()` returns `None` (not `-1`) on miss, and `.start()` on `None` raises `AttributeError`. Without explicit null-handling, the wiring test would crash instead of producing a clean FAIL message.
- **Fix:** Explicit null-safe extraction: `apply_pos = apply_match.start() if apply_match else -1` (same for archive). The downstream `assert apply_pos >= 0` then catches the absent-invocation case with a clear actionable error message.
- **Files modified:** `tests/ci/test_roadmap_analyze_supersession_wired.py`
- **Verification:** Running the wiring test against the present-but-unupgraded workflow file produces the documented FAIL with the wiring message (apply_pos=-1, clean assertion error pointing at the spec doc).
- **Committed in:** `9e0d5d8` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 Rule 1 bug, 1 Rule 2 missing critical)
**Impact on plan:** Both fixes were required for the plan's own acceptance criteria to pass; no scope creep, no behavior changes vs. plan intent. The advisor flagged deviation 1 before any write, so no work was wasted.

## Issues Encountered

- **Shell-grep regex in acceptance criterion does not match markdown bullets** — The plan's AC `diff -u ... | grep -c '^[-+][^-+]'` was intended to count non-context changed lines, but markdown list rows start with `-` (the bullet), so an added markdown row appears as `+- [ ]` (plus, then dash) in unified diff; the second character matches `[-+]`, not `[^-+]`. The shell command returns 0 even though the fixture is semantically correct (1 line changed). This is a regex limitation in the plan's AC, not a fixture defect. The Python-based test (`test_supersession_fixture_diff_is_one_line`, implemented in Task 2) uses `splitlines()` index-by-index comparison which validates the contract correctly — and that's the authoritative test, not the shell-grep AC. The fixture data is correct; the issue is purely in how the AC's shell command was specified. Not committed-around (no code change); flagged in this Issues section so a future PLAN.md edit can refine the shell AC if revisited.

## User Setup Required

None — no external service configuration required. The TOOL-02 verb itself lives in the upstream SDK and ships outside this repo; the port-path instructions are documented in `.planning/sdk-proposals/TOOL-02-spec.md` for the operator to action when porting.

## Self-Check: PASSED

**Files created (verified via `[ -f path ] && echo FOUND`):**
- FOUND: tests/ci/test_roadmap_analyze_supersession_wired.py
- FOUND: tests/fixtures/v15_supersession/scenario.json
- FOUND: tests/fixtures/v15_supersession/roadmap-before.md
- FOUND: tests/fixtures/v15_supersession/roadmap-after.md
- FOUND: .planning/sdk-proposals/TOOL-02-spec.md

**Commits (verified via `git log | grep`):**
- FOUND: ea0e3cb (Task 1 — fixture)
- FOUND: 9e0d5d8 (Task 2 — test + spec)

**Test runs:**
- PASS: `test_supersession_fixture_present`
- PASS: `test_supersession_fixture_diff_is_one_line`
- FAIL (expected per contract — workflow file present but `--apply` not yet wired): `test_roadmap_analyze_apply_wired_before_archive`

## Next Phase Readiness

Plan 15-04 will chain `tests/ci/test_roadmap_analyze_supersession_wired.py` into the planning-tooling CI workflow alongside the TOOL-01 and TOOL-03 gates. The asymmetric SKIP-in-CI behavior is the design contract per PATTERNS.md §2 — Plan 15-04 must not "fix" the SKIP by vendoring the workflow file into the repo.

Operator action for the upstream port is fully spec'd at `.planning/sdk-proposals/TOOL-02-spec.md` (Section 8: Port path) — extends `~/.claude/get-shit-done/bin/lib/roadmap.cjs` with a new `detectUmbrellaSupersession()` function, wires into the existing `cmdRoadmapAnalyze` dispatch in `roadmap-command-router.cjs`, adds the `<step name="apply_supersession">` block to `complete-milestone.md`, and adds 5 SDK-side unit tests covering the cases in Section 7 of the spec.

---
*Phase: 15-planning-tooling-hardening*
*Completed: 2026-05-23*
