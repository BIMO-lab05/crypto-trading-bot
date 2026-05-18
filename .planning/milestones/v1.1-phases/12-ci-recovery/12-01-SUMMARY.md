---
phase: 12-ci-recovery
plan: 01
subsystem: infra
tags: [github-actions, ci, telegram, billing, cron, workflow, regression-net]

# Dependency graph
requires:
  - phase: 11.1
    provides: ".planning/evidence/ directory convention + REQUIREMENTS.md taxonomy (CIRESTORE-*)"
provides:
  - "Cron-driven billing-failure detector workflow (CIRESTORE-03) — every 6h gh run list scan, ops: billing label, Telegram alert via direct curl"
  - "Self-trigger-safe workflow naming convention (CI Health Monitor) for any future detector that scans gh run list for its own substring"
  - "Stdlib-only grep-gate test pattern extended (no pyyaml) — tests/integration/test_billing_failure_detector.py joins test_dashlive_grep_gates.py / test_preflight_grep_gates.py"
  - ".planning/evidence/OP-04/ + .planning/evidence/CIRESTORE-02/ scaffolds — schema READMEs documenting what the operator commits upon OP-04 resolution"
affects: [phase-12-ci-recovery, OP-04, LIVECLOSE-02, CIRESTORE-01, CIRESTORE-02]

# Tech tracking
tech-stack:
  added: ["gh CLI (existing GH Actions runner)", "jq (existing GH Actions runner)", "curl direct-to-Telegram pattern"]
  patterns:
    - "Self-trigger prevention via name-avoidance + jq defense-in-depth filter for cron workflows that monitor their own surface"
    - "Idempotent gh label create via trailing || true — first-run on fresh repo + re-run on existing label both succeed"
    - "No event-payload interpolation — workflow has only schedule + workflow_dispatch triggers, so any ${{ github.event.* }} reference is a bug (regression-gated via test 5)"
    - "Stdlib-only grep-gate scope to a single workflow file (not a directory) — extends the test_dashlive_grep_gates.py pattern to single-file scope"
    - "Evidence-scaffold pattern: README schema doc + .gitkeep + closure procedure for operator-blocked carry-ins"

key-files:
  created:
    - ".github/workflows/billing-failure-detector.yml — 130 lines (header comment + 5 steps)"
    - "tests/integration/test_billing_failure_detector.py — 306 lines (12 tests + helper + module docstring)"
    - ".planning/evidence/OP-04/README.md — 27 lines"
    - ".planning/evidence/OP-04/.gitkeep — 0 bytes"
    - ".planning/evidence/CIRESTORE-02/README.md — 35 lines"
    - ".planning/evidence/CIRESTORE-02/.gitkeep — 0 bytes"
  modified: []

key-decisions:
  - "Workflow name is `CI Health Monitor (CIRESTORE-03)` — deliberately omits the literal `billing` to prevent self-trigger feedback loop (advisor-flagged blocker)"
  - "Telegram alert via direct curl to api.telegram.org — in-cluster notification-service (port 8006) is unreachable from GitHub-hosted runners (forced design)"
  - "jq self-trigger guard `select(.name != \"CI Health Monitor (CIRESTORE-03)\")` repeated 4 times (detect + summary + issue-body jq calls) for defense-in-depth"
  - "Only CIRESTORE-03 marked complete in REQUIREMENTS.md — CIRESTORE-01 and CIRESTORE-02 are operator-blocked human_needed checkpoints that remain open until operator resolves OP-04 (per plan objective lines 92-93, 109-111)"
  - "Workflow header comment reworded mid-execution (Rule 1 fix) — original wording contained the literal `gh label create` which tripped test 12's per-line idempotency scan"

patterns-established:
  - "Self-trigger-safe cron-monitor pattern: workflow name must not contain the substring it filters for; jq pipeline must explicitly exclude .name == own_name"
  - "Single-file grep-gate scope: when guarding a single workflow file (vs. a directory tree), pass the file path directly to both pathlib and subprocess grep — narrower than the production-code-directory scope used in test_preflight_grep_gates.py"
  - "Evidence-scaffold convention for operator-blocked carry-ins: ship .gitkeep + schema README ≤40 lines documenting the file the operator commits + closure procedure; do NOT ship the operator-fillable evidence itself"

requirements-completed: [CIRESTORE-03]
# Note: PLAN.md frontmatter lists CIRESTORE-01, CIRESTORE-02, CIRESTORE-03 because
# this plan ADDRESSES all three (CIRESTORE-01/02 via evidence-dir scaffolds,
# CIRESTORE-03 via detector workflow). Only CIRESTORE-03 is code-complete here.
# CIRESTORE-01 + CIRESTORE-02 close only after operator resolves OP-04.

# Metrics
duration: ~52 min
completed: 2026-05-18
---

# Phase 12 Plan 01: CI Recovery — Billing-Failure Detector + Evidence Scaffolds Summary

**Cron-driven billing-failure detector (CIRESTORE-03) shipped with 12-test grep-gate net, self-trigger-safe naming, and direct-curl Telegram path; plus evidence-dir scaffolds for the two operator-blocked carry-ins (CIRESTORE-01/02).**

## Performance

- **Duration:** ~52 min
- **Started:** 2026-05-18T15:20:00Z (approx — plan execution start)
- **Completed:** 2026-05-18T16:12:06Z
- **Tasks:** 3
- **Files created:** 6 (1 workflow + 1 test + 2 README + 2 .gitkeep)
- **Files modified:** 0

## Accomplishments

- `.github/workflows/billing-failure-detector.yml` — cron `0 */6 * * *` + workflow_dispatch; scans last 5 failed runs via `gh run list`; filters displayTitle for `billing` substring (case-insensitive); excludes detector's own failure rows (self-trigger guard via name-equality jq filter); on detection posts Telegram alert (direct curl to api.telegram.org) + creates GitHub Issue with idempotent `ops: billing` label.
- `tests/integration/test_billing_failure_detector.py` — 12 tests (9 grep gates + 3 pure-Python detection-logic on local `_detect_billing` helper). Stdlib-only (re, subprocess, pathlib, pytest) — no pyyaml, matching project convention. Dual-form scan pattern (pathlib + subprocess grep) lifted from `test_dashlive_grep_gates.py` / `test_preflight_grep_gates.py`.
- Evidence scaffolds — `.planning/evidence/OP-04/` + `.planning/evidence/CIRESTORE-02/` each contain `.gitkeep` + `README.md`. READMEs document the schema (what file the operator commits + closure procedure) without overprescribing operator workflow.

## Task Commits

1. **Task 1: RED tests** — `1b00178` (feat) — 12 tests created; 9 failed + 3 passed at commit (workflow file absent; pure-Python detection helper tests pass).
2. **Task 2: GREEN workflow** — `d99be43` (feat) — workflow file ships; all 12 tests pass; Rule 1 fix applied mid-task (see Deviations).
3. **Task 3: Evidence scaffolds** — `5765359` (chore) — 4 files created (2 .gitkeep + 2 README); all 6 Task 3 verify gates pass.

**Plan metadata:** _(to be created in the docs(planning) commit after this SUMMARY lands)_

## Files Created/Modified

### Created

- `.github/workflows/billing-failure-detector.yml` (130 lines) — cron-driven detector workflow with header comment block, 5 steps (mask, label-create, detect, post Telegram, create Issue), self-trigger filter in jq pipeline.
- `tests/integration/test_billing_failure_detector.py` (306 lines) — 12 tests + `_detect_billing` helper + 35-line module docstring.
- `.planning/evidence/OP-04/README.md` (27 lines) — schema doc: operator commits `billing-screenshot.png` upon OP-04 resolution.
- `.planning/evidence/OP-04/.gitkeep` (empty) — forces git to track the directory pre-operator-fill.
- `.planning/evidence/CIRESTORE-02/README.md` (35 lines) — schema doc: operator commits three `.url` files (integration-ml-on, tournament-harness, dashboard-smoke) after OP-04.
- `.planning/evidence/CIRESTORE-02/.gitkeep` (empty) — same purpose.

### Modified

None.

## Decisions Made

1. **Self-trigger-safe workflow naming** (advisor-flagged blocker): The workflow `name:` is `CI Health Monitor (CIRESTORE-03)` — deliberately omits the literal `billing` (case-insensitive). Rationale: if the detector itself fails (Telegram 5xx, jq error, transient `gh api` flake), the next cron tick would read its own failure row whose displayTitle inherits the workflow name, the substring match would trip, and a new alert would post — infinite loop. Defense-in-depth: jq pipeline carries explicit `select(.name != "CI Health Monitor (CIRESTORE-03)")` clause across all three jq invocations (detect, summary, issue-body), surviving any future rename. Test 6 (name constraint) + test 7 (jq filter constraint) + test 11 (own-name-row silent) form the regression net.

2. **Telegram path is direct curl to api.telegram.org** (forced design — no choice): the in-cluster `notification-service` (port 8006) runs inside the operator's docker-compose host and is unreachable from GitHub-hosted runners without VPN/tunnel. Direct curl is the only viable option AND the smaller blast radius (no service dependency, no networking surface). Documented verbatim in workflow header comment. URL constant + payload shape mirror `services/notification-service/app/telegram_notifier.py` but the Python module is NOT imported (runner is outside docker-compose).

3. **Only CIRESTORE-03 marked complete in REQUIREMENTS.md** — CIRESTORE-01 and CIRESTORE-02 stay open. PLAN.md frontmatter lists all three because the plan ADDRESSES them (detector for CIRESTORE-03; scaffolds for CIRESTORE-01/02). But per plan objective lines 92-93 + 109-111 the operator action remains a wall-clock checkpoint, so the carry-in is genuinely not closed by this phase. Documenting in `requirements-completed: [CIRESTORE-03]` only — flagged here for visibility.

4. **Header comment reworded mid-Task-2** (Rule 1 deviation — see below).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Workflow header comment originally tripped test 12's per-line idempotency scan**

- **Found during:** Task 2 (first GREEN run of `pytest tests/integration/test_billing_failure_detector.py`)
- **Issue:** Original header comment line read `# `gh label create` runs unconditionally with a trailing `|| true` so the` — the comment contained the literal substring `gh label create` (used to explain idempotency to a human reader). Test 12 iterates ALL lines containing `gh label create` and asserts each ends with `|| true`. The comment line broke across two lines for prose readability, so the first line ended in `the` not `|| true` — test failed.
- **Fix:** Reworded the header comment from "`gh label create` runs unconditionally..." to "The label-create step runs unconditionally..." — semantic equivalent, no literal match for `gh label create` in the comment text. The actual command line is unchanged.
- **Files modified:** `.github/workflows/billing-failure-detector.yml` (comment line, no behavior change)
- **Verification:** Re-ran `pytest tests/integration/test_billing_failure_detector.py -q` → 12 passed, 0 failed (GREEN).
- **Committed in:** `d99be43` (part of Task 2 commit — fix was applied before staging).

**Was the test 12 design too strict?** No — the test is doing its job. Catching a documentation reference to a CLI command without idempotency guards would, in a worse-faith refactor, also catch someone uncommenting a debug line. The test correctly enforces "any invocation reference must be idempotent". The fix is to write the comment without the literal substring.

---

**Total deviations:** 1 auto-fixed (Rule 1: bug — caught by RED-then-GREEN test cycle exactly as TDD intends).
**Impact on plan:** None on scope or contract. The Rule 1 fix was a wording change in a comment block, applied before committing Task 2. The actual workflow behavior is identical to the plan spec.

## Authentication Gates

None. This plan ships GitHub Actions workflow YAML + test code + markdown scaffolds — no Telegram/GH API authentication exercised during execution. The workflow itself uses `${{ secrets.TELEGRAM_BOT_TOKEN }}` + `${{ secrets.GITHUB_TOKEN }}` (auto-injected) at CI runtime, NOT at plan-execution time.

## Issues Encountered

**Hook artefact (informational, not a real issue):** The `PreToolUse` `security_reminder_hook.py` fired once during the first `Write` call for `billing-failure-detector.yml`, surfacing an advisory about command-injection risks in GitHub Actions workflows. The advisory does not match our workflow's pattern (we use only `schedule` + `workflow_dispatch` triggers, so no event payload exists to interpolate — exactly the SAFE pattern the advisory describes). Retried the Write; succeeded. Workflow does not contain any `${{ github.event.* }}` interpolation in `run:` blocks — test 5 (`test_workflow_no_user_controlled_event_interpolation`) grep-gates against the regression.

## Gate Evidence

### Per-task verify-block exit codes

| Task | Verify command | Exit code |
| --- | --- | --- |
| Task 1 | `python3 -m py_compile tests/integration/test_billing_failure_detector.py && pytest ... --collect-only -q \| grep -c '::test_' \| awk '$1 >= 12 {exit 0} {exit 1}'` | 0 |
| Task 2 | `test -f .github/workflows/billing-failure-detector.yml && pytest tests/integration/test_billing_failure_detector.py -q` | 0 (12 passed) |
| Task 3 | `test -f ... .gitkeep && test -f ... README.md && grep -F "CIRESTORE-01" ... && ...` (10-grep compound) | 0 |

### Plan-level `<verification>` block (9 commands, all PASS)

| # | Command | Result |
| --- | --- | --- |
| 1 | `pytest tests/integration/test_billing_failure_detector.py -q` | 12 passed, exit 0 |
| 2 | `grep -F "name: CI Health Monitor (CIRESTORE-03)" ...` | 1 match, exit 0 |
| 3 | `grep -F "cron: '0 */6 * * *'" ...` | 1 match, exit 0 |
| 4 | `grep -F "gh run list --status failure --limit 5" ...` | 1 match, exit 0 |
| 5 | `grep -cF "ops: billing" ...` (>=2) | 5 matches, exit 0 |
| 6 | `grep -cF '::add-mask::' ...` (>=1) | 2 matches, exit 0 |
| 7 | `grep -cF 'select(.name != "CI Health Monitor (CIRESTORE-03)")' ...` (>=2) | 4 matches, exit 0 |
| 8 | `grep -v '^[[:space:]]*#' ... \| grep -cF '${{ github.event.'` (==0) | 0 matches, exit 0 |
| 9 | `test -f .planning/evidence/OP-04/README.md && test -f .planning/evidence/CIRESTORE-02/README.md` | both exist, exit 0 |
| (optional) | `actionlint ...` | skipped — actionlint not installed locally per plan's optional gate |

### TDD gate compliance

- RED: `1b00178` (feat) — at this commit, `pytest tests/integration/test_billing_failure_detector.py -q` returned `9 failed, 3 passed` (workflow absent).
- GREEN: `d99be43` (feat) — at this commit, same command returns `12 passed` after the Rule 1 fix.
- REFACTOR: Not exercised — the GREEN implementation was already minimal and clean; no separate refactor commit warranted.

Note on per-task TDD vs plan-type=execute: This plan is `type: execute` (not `type: tdd`) and Task 1 is `tdd="true"` (TDD-flagged). The two commits 1b00178 (test) + d99be43 (feat) together form the RED-GREEN pair for the detector workflow. No plan-level TDD gate enforcement applies.

## User Setup Required

None. Workflow ships ready-to-fire; operator action required only for the two existing repo-secrets it depends on:

- `TELEGRAM_BOT_TOKEN` — already in repo secrets (used by notification-service); no new secret needed.
- `TELEGRAM_CHAT_ID` — already in repo secrets.
- `GITHUB_TOKEN` — auto-injected by GitHub Actions, no setup.

The `ops: billing` label is created idempotently by the workflow itself on first run (`gh label create ... || true`).

If `TELEGRAM_CHAT_ID` is unset, the curl payload will POST with empty `chat_id` and Telegram will return 400; the `--fail` flag causes the step to exit non-zero (visible failure in CI, not a silent miss). This is acceptable behavior per the threat-acceptance row T-12-08.

## Next Phase Readiness

- **CIRESTORE-03 fully shipped.** The detector workflow will fire on the next scheduled cron tick (`0 */6 * * *` UTC) after this commit lands on main. No further code work for Phase 12.
- **CIRESTORE-01 + CIRESTORE-02 remain open** awaiting operator OP-04 resolution. The evidence-dir scaffolds + READMEs are in place — when the operator resolves billing, they have a documented schema to fill (`.planning/evidence/OP-04/billing-screenshot.png` and `.planning/evidence/CIRESTORE-02/*.url`).
- **Phase 12 is the terminal v1.1 code phase.** After this plan lands, v1.1 has zero unplanned phases and the remaining v1.1 work is:
  - Operator wall-clock: OP-01..04 + INFRA-02 + LIVECLOSE harness runs (already shipped in Phase 11.1).
  - Operator wall-clock: CIRESTORE-01 + CIRESTORE-02 evidence (gated on OP-04).

## Self-Check: PASSED

- `.github/workflows/billing-failure-detector.yml` exists on disk (verified `[ -f ]`).
- `tests/integration/test_billing_failure_detector.py` exists on disk.
- `.planning/evidence/OP-04/.gitkeep` + `README.md` exist.
- `.planning/evidence/CIRESTORE-02/.gitkeep` + `README.md` exist.
- `git log --oneline --all --grep="12.01"` returns commits `1b00178`, `d99be43`, `5765359` (verified — see `## Task Commits`).
- All per-task `<verify><automated>` blocks exit 0 (see Gate Evidence).
- All 9 plan-level `<verification>` commands exit 0 (see Gate Evidence).
- All per-task `<acceptance_criteria>` re-verified PASS via plan-level verification (every literal asserted by the criteria is grep-confirmed in either the workflow file or the test file).
- Pre-existing working-tree dirt (`M .planning/v1.1-MILESTONE-AUDIT.md`, `?? docker-compose.live.override.yml`) was NEVER staged in any Phase-12 commit — verified via `git diff --cached --name-only` before each commit.
- No `${{ github.event.* }}` interpolation introduced (verified via plan-level verification command 8).

---

*Phase: 12-ci-recovery*
*Completed: 2026-05-18*
