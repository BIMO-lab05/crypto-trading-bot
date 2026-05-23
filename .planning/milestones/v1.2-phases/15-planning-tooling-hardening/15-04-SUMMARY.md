---
phase: 15-planning-tooling-hardening
plan: 04
subsystem: planning-tooling
tags: [ci-workflow, pre-commit, verify-stack, evidence, wave-2, integration]

# Dependency graph
requires:
  - phase: 15-planning-tooling-hardening
    provides: "Plan 15-01 tests/ci/test_no_placeholder_one_liners.py (TOOL-01 grep gate) + .planning/sdk-proposals/TOOL-01-spec.md"
  - phase: 15-planning-tooling-hardening
    provides: "Plan 15-02 tests/ci/test_roadmap_analyze_supersession_wired.py + tests/fixtures/v15_supersession/ + .planning/sdk-proposals/TOOL-02-spec.md"
  - phase: 15-planning-tooling-hardening
    provides: "Plan 15-03 tests/ci/test_audit_freshness_gate.py + tests/fixtures/v11_13h_gap/ + .planning/sdk-proposals/TOOL-03-spec.md"
provides:
  - "Standalone CI workflow .github/workflows/planning-tooling-gate.yml — 3 named jobs (tool-01-grep-gate, tool-02-wiring-gate, tool-03-freshness-gate) each surfacing as a required PR check"
  - "Operator-side opt-in pre-commit installer scripts/install-pre-commit.sh — idempotent, backup-safe, chains all 3 gates locally"
  - "Planning-tooling-adapted verify-stack 4-check evidence .planning/evidence/TOOL-15/verify-stack-report.txt — proof Phase 15 ships green, milestone-close-ready"
affects: [milestone-v1.2-close, gsd-verify-work, future-summary-extract-runs]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Three-jobs-in-one-workflow pattern over three separate workflow files — chosen for less filename sprawl while preserving per-contract PR-check surface (each job remains a separately required check)"
    - "Operator-side opt-in pre-commit installer pattern (scripts/install-pre-commit.sh) — mirrors bootstrap.sh shape; idempotency via marker comment ('planning-tooling-gate-installer') in the installed hook body; backup-on-replace for unrelated prior hooks; canonical enforcement remains CI workflow"
    - "Planning-tooling-adapted verify-stack 4-check pattern — adapts the canonical exchange/notification/DB/restart protocol to a no-trading-engine phase by substituting 4 phase-relevant checks (workflow parses, tests collect, specs exist with required structure, fixtures parse with canonical data preserved) and explicitly marking the canonical 4 as N/A with rationale"

key-files:
  created:
    - ".github/workflows/planning-tooling-gate.yml — 118-line standalone CI workflow with 3 named jobs running pytest against the 3 in-repo test files committed by Plans 15-01/02/03"
    - "scripts/install-pre-commit.sh — 73-line idempotent installer, bash -n syntax-clean, ships executable, end-to-end tested in tmp git repo (1st install no backup, 2nd install no backup, 3rd install with unrelated prior hook creates timestamped backup)"
    - ".planning/evidence/TOOL-15/verify-stack-report.txt — 5306-byte 4-check evidence report with all command outputs captured at execute time, no stub placeholders"
    - ".planning/evidence/TOOL-15/.gitkeep — anchors evidence directory in git"
  modified: []

key-decisions:
  - "Picked 15-PATTERNS.md option (b) — three jobs in one workflow file — over three separate workflow files. The per-job PR-check surface is identical to the separate-file shape; the consolidated file reduces filename sprawl while keeping the per-contract visibility that the 'one contract per visible PR check' precedent from Phase 13 BC-03 requires."
  - "Installed hook chains TOOL-01 conditionally (only when *-PLAN.md or *-SUMMARY.md is staged) and TOOL-02 + TOOL-03 unconditionally (cheap ~1s combined). The asymmetric wiring tests inside TOOL-02 + TOOL-03 SKIP automatically when host SDK absent, so unconditional invocation is safe pre-port; post-port it becomes meaningful."
  - "Evidence report keeps the canonical 4-check listed explicitly as [N/A] with one-line rationale each, alongside the 4 planning-tooling-adapted [PASS] checks. The [N/A] block is the audit trail showing the adaptation was deliberate (Phase 14 14-06 frontend-adaptation precedent), not a cherry-pick of easy checks."

patterns-established:
  - "Three-jobs-in-one-workflow over three-separate-workflows for gate-bundle CI surfaces: identical per-job PR-check surface, less filename sprawl, single comment block documenting the bundle invariants."
  - "Pre-commit installer idempotency via marker-comment in the installed hook body: re-running the installer detects its own marker and produces no backup; only unrelated prior hooks get timestamped-backup-on-replace."
  - "Planning-tooling phase verify-stack adaptation: list the canonical 4 checks as [N/A] with rationale, ship 4 phase-adapted [PASS] checks alongside, conclude with 'Overall: PASS'. Pattern reusable for any future phase whose nature does not exercise the trading-engine-centric canonical 4."

requirements-completed: [TOOL-01, TOOL-02, TOOL-03]

# Metrics
duration: ~22min
completed: 2026-05-23
---

# Phase 15 Plan 04: Wave-2 Integration Summary

**Wave-2 integration ships three deliverables that wire the three Wave-1 grep gates into both the operator-side dev loop and the CI required-check set: a 118-line standalone CI workflow with three named jobs surfacing as required PR checks, a 73-line idempotent opt-in pre-commit installer mirroring the bootstrap.sh repo-local-opt-in pattern, and a 5306-byte planning-tooling-adapted verify-stack 4-check evidence report with every command output captured at execute time.**

## Performance

- **Duration:** ~22 min
- **Started:** 2026-05-23T00:03Z (worktree branch reset to wave-1 merge base ac6aeae)
- **Completed:** 2026-05-23T00:25Z (SUMMARY write — final commit follows)
- **Tasks:** 3
- **Files modified:** 4 new (1 workflow + 1 script + 1 evidence report + 1 .gitkeep)

## Accomplishments

- Shipped the standalone CI workflow `.github/workflows/planning-tooling-gate.yml` (118 lines, 3 jobs: `tool-01-grep-gate`, `tool-02-wiring-gate`, `tool-03-freshness-gate`) mirroring the Phase 13 `bybit-bypass-gate.yml` "one contract per visible PR check" precedent. Each job runs `actions/checkout@v4` + `actions/setup-python@v5` (Python 3.12) + `pytest 7.4.4` against its respective `tests/ci/test_*.py` file. The 3 jobs are parallel (no `needs:` dependency); total wall-clock ≈ 60s per job. YAML parses; `python3 -c "import yaml; yaml.safe_load(...)"` exits 0. No `continue-on-error` YAML key exists (only the do-NOT-add warning comment, matching the analog file exactly).
- Shipped the opt-in pre-commit installer `scripts/install-pre-commit.sh` (73 lines, executable, mirrors `bootstrap.sh` repo-local opt-in shape) per 15-PATTERNS.md §3 recommendation. Installs `.git/hooks/pre-commit` chaining: TOOL-01 conditionally on staged planning artifacts, TOOL-02 + TOOL-03 unconditionally on every commit. Marker comment `planning-tooling-gate-installer` in the installed hook body makes the installer idempotent — re-runs do not double-append and produce no backup. Unrelated existing hooks are backed up to `.git/hooks/pre-commit.bak.{timestamp}` before replacement.
- Shipped the planning-tooling-adapted verify-stack evidence report `.planning/evidence/TOOL-15/verify-stack-report.txt` (5306 bytes, mirrors Phase 14 14-06 frontend-adaptation pattern). The canonical 4-check (exchange URL / notification / DB row / restart) is listed as `[N/A]` with one-line rationale each (no trading-engine impact); 4 planning-tooling-adapted `[PASS]` checks ship alongside with every command output captured at execute time, no stub placeholders. Final line: `Overall: PASS`.
- All 3 in-repo grep-gate test files now resolve via `pytest --collect-only` (11 tests collected total: TOOL-01 4 + TOOL-02 3 + TOOL-03 4). The intentional RED state on Plan 15-01's gate (`13-04-SUMMARY.md:60`, the `Task 1 -- orderbook handler refactor (TDD):` placeholder shipped from Phase 13) is preserved unchanged — the CI workflow will surface it on every PR and `push` to main, providing the forcing function for the eventual milestone-close cleanup.
- End-to-end installer idempotency verified in a tmp git repo: 1st install creates the hook with no backup, 2nd install with our own hook present creates no backup, 3rd install with an unrelated prior hook creates exactly one timestamped backup. `bash -n` syntax-clean.

## Task Commits

Each task was committed atomically:

1. **Task one — CI workflow file `.github/workflows/planning-tooling-gate.yml`** — `08b1876` (feat)
2. **Task two — opt-in pre-commit installer `scripts/install-pre-commit.sh`** — `6af8acd` (feat)
3. **Task three — planning-tooling-adapted verify-stack evidence report** — `edffd43` (docs)

## Files Created/Modified

- `.github/workflows/planning-tooling-gate.yml` — 3-job workflow chaining the TOOL-01/02/03 grep gates as required PR checks. Each job mirrors the Phase 13 `bybit-bypass-gate.yml` shape (checkout + setup-python + install pytest + run one test file). No `continue-on-error` YAML key; security-note block documents the no-user-input-interpolation invariant.
- `scripts/install-pre-commit.sh` — bash script with strict-mode `set -euo pipefail` (script + installed hook both). Idempotent via marker-comment detection; backup-safe via timestamped `.bak.{date}` preservation of any pre-existing unrelated hook. Chains the 3 TOOL gate test files via `python3 -m pytest -q || exit 1` invocations.
- `.planning/evidence/TOOL-15/verify-stack-report.txt` — 4-check evidence report with explicit `[PASS]/[N/A]/Overall:` markers and command-output transcripts captured at execute time (no `<fill in at execute time>` placeholders). Documents the asymmetric SKIP-in-CI contract for TOOL-02 + TOOL-03 wiring tests.
- `.planning/evidence/TOOL-15/.gitkeep` — anchors the evidence directory in git for future TOOL-XX evidence files in subsequent milestone closes.

## Decisions Made

- **Chose three-jobs-in-one-workflow over three-separate-workflow-files.** Both shapes satisfy the 15-PATTERNS.md "one contract per visible PR check" requirement (each job is a separately named, separately required PR check). The consolidated file produces less `.github/workflows/` filename sprawl; the per-job PR-check surface is identical from a CI-required-check perspective. Documented inline in the workflow's comment block so a future maintainer doesn't "fix" the shape by splitting the file.
- **Made TOOL-01 conditional and TOOL-02/03 unconditional in the installed pre-commit hook.** TOOL-01 (`test_no_placeholder_one_liners`) scans the whole `.planning/phases/` tree and only matters when planning artifacts are being committed, so the installer gates it on `git diff --cached --name-only --diff-filter=ACM | grep -E '\.planning/phases/.*-(PLAN|SUMMARY)\.md$'`. TOOL-02 + TOOL-03 run unconditionally on every commit — their fixture-validation tests are cheap (~1s combined) and their wiring tests SKIP automatically when host SDK is absent, so the unconditional shape is safe pre-port and meaningful post-port.
- **Kept the canonical /verify-stack 4-check as explicit `[N/A]` lines in the evidence report.** A future reader checking why the planning-tooling phase did not exercise the exchange/notification/DB/restart canonical checks gets a one-line rationale per check, plus the adaptation rationale at the top. Pattern mirrors Phase 14 14-06's verify-stack-report.txt at `.planning/evidence/MOBILE-03/` exactly.

## Deviations from Plan

### Documented tightness divergence (not a fix)

**1. [Documentation note] Plan acceptance criterion for `continue-on-error: 0` versus warning-comment count.**

The plan's Task 1 acceptance criterion `grep -c 'continue-on-error' .github/workflows/planning-tooling-gate.yml returns 0` was literally impossible to satisfy because the analog file (`.github/workflows/bybit-bypass-gate.yml`, explicitly mandated as the structural model in the plan's `read_first`) contains the substring `continue-on-error` in its do-NOT-add warning comment at line 56. Mirroring the analog faithfully means inheriting the same warning comment, which trips the literal grep count.

- **Interpretation:** the AC's intent is "no `continue-on-error: true` YAML key in the workflow." Structural verification via `python3 -c "import yaml; ..."` walking the parsed dict confirms zero `continue-on-error` keys at any depth.
- **Resolution:** kept the warning comment (faithful to the analog), reported the structural-zero-keys result, and documented this tightness mismatch here.
- **Files modified:** none — the file is correct as shipped.
- **Same pattern as Plan 15-01's documented tightness divergence** between its plan AC's whole-file scan and the gate's candidate-position scan.

### Minor Edit during execution (not a Rule 1/2/3 fix)

**2. [Tightening] Task 3 acceptance criterion required ≥3 lines matching the per-job-name grep; the initial report had 2.**

- **Found during:** Task 3 verification.
- **Issue:** The initial evidence report shipped 2 lines matching `tool-01-grep-gate|tool-02-wiring-gate|tool-03-freshness-gate` (both inside the Check 1 expected/actual output block); the AC required ≥3 matching lines.
- **Fix:** Edited the Check 3 sub-bullets to annotate each spec file with its target job name (`TOOL-01-spec for tool-01-grep-gate job`, etc.), which both satisfies the AC count (5 matching lines now) and tightens the spec-to-job cross-reference for the reader.
- **Files modified:** `.planning/evidence/TOOL-15/verify-stack-report.txt`.
- **Verification:** `grep -c` now returns 5.
- **Committed in:** `edffd43` (Task 3 commit — edit happened pre-commit, no separate commit).

---

**Total deviations:** 2 documented (1 documented-tightness mismatch with analog file; 1 minor in-task tightening edit pre-commit). No Rule 1 / Rule 2 / Rule 3 auto-fixes. No scope creep.

## Issues Encountered

- **PreToolUse security-reminder hook fired on the first Write to `.github/workflows/planning-tooling-gate.yml`.** The hook flagged the GitHub Actions injection risk surface (`${{ }}` interpolation of user-controlled event payloads into shell commands). The workflow has no such surface — it uses only first-party actions and pytest invocation against in-repo test files, identical to the analog file `bybit-bypass-gate.yml`. The Write was re-issued after acknowledging the warning; the workflow's own comment block documents the no-user-input-interpolation invariant prominently.

## User Setup Required

None — the CI workflow auto-runs on PR + push to main once merged. The pre-commit installer is opt-in: developers run `bash scripts/install-pre-commit.sh` once after each fresh clone if they want local pre-push gate enforcement. The canonical enforcement remains the CI required-check set, which cannot be bypassed.

## Next Phase Readiness

- **ROADMAP SC #4 met:** All 3 grep gates (TOOL-01/02/03) are pinned as required PR checks via `.github/workflows/planning-tooling-gate.yml`. Any future PR re-introducing placeholder one-liners, removing the `roadmap.analyze --apply` wiring (post-port), or removing the audit-freshness check (post-port) will fail the corresponding gate and cannot merge.
- **ROADMAP SC #5 met:** When `/gsd-complete-milestone v1.2` runs, the 3 gates execute as part of the CI required-check set. Plan 15-04's verify-stack-report.txt is the evidence that the gates run cleanly today (modulo the intentional RED on 13-04-SUMMARY.md:60 that milestone-close cleanup addresses).
- **TOOL-01 forcing function active:** The intentional RED on `13-04-SUMMARY.md:60` (the `Task 1 -- orderbook handler refactor (TDD):` placeholder shipped from Phase 13) will surface in every PR run going forward. The milestone-close cleanup that flips this RED to GREEN is the operator's owned step; the gate provides the forcing function until it lands.
- **Plan 15-04 is the last plan in Phase 15.** All 3 requirements (TOOL-01, TOOL-02, TOOL-03) flow through the integrated CI surface. Phase 15 is ready for `/gsd-verify-work` followed by `/gsd-complete-phase`.

---
*Phase: 15-planning-tooling-hardening*
*Completed: 2026-05-23*

## Self-Check: PASSED

**Files created (verified via `[ -f path ] && echo FOUND`):**
- FOUND: .github/workflows/planning-tooling-gate.yml
- FOUND: scripts/install-pre-commit.sh
- FOUND: .planning/evidence/TOOL-15/verify-stack-report.txt
- FOUND: .planning/evidence/TOOL-15/.gitkeep
- FOUND: .planning/phases/15-planning-tooling-hardening/15-04-SUMMARY.md (this file)

**Commits (verified via `git log --oneline | grep`):**
- FOUND: 08b1876 (Task 1 — CI workflow)
- FOUND: 6af8acd (Task 2 — pre-commit installer)
- FOUND: edffd43 (Task 3 — evidence report)

**Behavior verification (re-run at execute time):**
- PASS: YAML parses, 3 jobs registered (tool-01-grep-gate, tool-02-wiring-gate, tool-03-freshness-gate).
- PASS: 11 tests collect via `pytest --collect-only` across the 3 in-repo test files.
- PASS: Installer is executable, `bash -n` syntax-clean; idempotency confirmed end-to-end in a tmp git repo (1st no backup, 2nd no backup, 3rd with unrelated prior hook creates one timestamped backup).
- PASS: Evidence report 5306 bytes, 4 PASS markers, 4 N/A markers, 0 stub placeholders, 1 'Overall: PASS' line.
- PASS: 6 unconditional fixture-validation tests across the 3 modules all pass green.
- EXPECTED: TOOL-01 placeholder gate still RED on exactly one violation (13-04-SUMMARY.md:60); no new violations introduced by this SUMMARY.md.
