---
phase: 02-integration-test-suite-runbook
plan: 07
subsystem: infra
tags: [runbook, ops-docs, failure-triage, wsl2, docker, markdown]

# Dependency graph
requires:
  - phase: 01-bootstrap-recorded-tape
    provides: bootstrap.sh (referenced from triage steps for re-verification)
provides:
  - Failure-triage-first RUNBOOK.md at repo root with 6 symptom sections (Diagnose / Action / Verification)
  - Bidirectional cross-link between docs/operations/RUNBOOK.md (nominal ops) and /RUNBOOK.md (failure triage)
affects:
  - 02-08-bug-triage (may extend RUNBOOK.md with one section per INFRA-06 deferred bug)
  - 02-10-makefile (provides the make build-no-buildkit target referenced from BuildKit-hang section)
  - 02-06-iter-fix (provides scripts/iter-fix.sh referenced from bootstrap-failure section)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Failure-triage-first runbook format (per CD-03): one section per symptom; Diagnose → Action → Verification subsections"
    - "Two-RUNBOOK split: root file = failure triage; docs/operations/ = nominal ops; cross-linked both ways"

key-files:
  created:
    - RUNBOOK.md
  modified:
    - docs/operations/RUNBOOK.md

key-decisions:
  - "CD-03 resolution: option (a) — two RUNBOOKs, cross-linked. Existing docs/operations content is kept verbatim; failure-triage-first format lives at repo root only."
  - "Symptom set sourced verbatim from CLAUDE.md Environment + Gotchas + INFRA-06 named bugs; no novel destructive operations invented (T-02-07-02 mitigation)."
  - "All commands are command-shapes (no real API keys, tokens, or DB credentials embedded) — T-02-07-01 mitigation."
  - "Forward-references to Plan 02-10 (make build-no-buildkit) and Plan 02-06 (scripts/iter-fix.sh) are permitted per plan; Plan 02-08 may extend RUNBOOK with deferred-bug rows."

patterns-established:
  - "Symptom heading format: ## Symptom: <one-line user-visible failure>"
  - "Triage subsection order: Diagnose (read-only checks) → Action (recovery commands) → Verification (post-action proof)"
  - "Cross-link convention: blockquote at top of each RUNBOOK pointing to its sibling (failure-triage / nominal ops)"

requirements-completed: [INFRA-05]

# Metrics
duration: ~30min
completed: 2026-05-07
---

# Phase 02 Plan 07: Failure-Triage RUNBOOK at Repo Root Summary

**Symptom-indexed RUNBOOK.md (163 lines, 6 mandated symptoms) at repo root in Diagnose/Action/Verification format, with bidirectional cross-link to existing nominal-ops runbook in docs/operations/.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-05-07T20:55Z (approx)
- **Completed:** 2026-05-07T21:26:04Z
- **Tasks:** 2 (both completed)
- **Files modified:** 2 (1 created, 1 edited)

## Accomplishments

- Created `RUNBOOK.md` at repo root (163 lines) with all 6 CD-03-mandated symptom sections — BuildKit hang, Docker context misconfig, bind-mount race, stale ML model, bootstrap.sh UNHEALTHY triage, EMERGENCY_STOP recovery — each with `Diagnose / Action / Verification` substructure and concrete shell commands (no aspirational placeholders).
- Added bidirectional cross-link: top of `docs/operations/RUNBOOK.md` now points to the new `/RUNBOOK.md`; the new root file links back to `docs/operations/RUNBOOK.md` for nominal-ops content. Operator can find failure-triage from either entry point.
- Forward-referenced Plan 02-10 (`make build-no-buildkit`) and Plan 02-06 (`scripts/iter-fix.sh`) so the runbook is internally complete before those plans land their artifacts.

## Task Commits

Each task was committed atomically:

1. **Task 1: Write RUNBOOK.md at repo root with all 6 mandatory symptom sections** — `24161a9` (feat)
2. **Task 2: Cross-link existing docs/operations/RUNBOOK.md to new root file** — `9eeab4d` (docs)

_No plan-metadata commit yet (orchestrator will batch metadata commits across the wave per parallel-execution policy)._

## Files Created/Modified

- `RUNBOOK.md` — **CREATED.** 163 lines. 6 `## Symptom:` sections; each with `**Diagnose:**` / `**Action:**` / `**Verification:**` blocks. Concrete shell commands sourced from CLAUDE.md Environment + Gotchas. Cross-links: down to `docs/operations/RUNBOOK.md` and `docs/development/SETUP.md`; forward to `make build-no-buildkit` (Plan 02-10) and `scripts/iter-fix.sh` (Plan 02-06).
- `docs/operations/RUNBOOK.md` — **MODIFIED** (+3 lines, well within plan's +5 cap). Inserted blockquote after the H1 title block (line 6) pointing to `../../RUNBOOK.md` for failure-triage. Existing 698-line nominal-ops content preserved verbatim.

## Decisions Made

- **Two-RUNBOOK split kept** per CD-03 default — root file is failure-triage-first; existing `docs/operations/RUNBOOK.md` retains its 6-section nominal-ops layout. No content from the existing file was deleted, rewritten, or relocated. The acknowledged staleness in `docs/operations/RUNBOOK.md` (references `docker-compose.yml` instead of canonical `docker-compose.unified.yml`) is explicitly out-of-scope for this plan and deferred to a future maintenance task.
- **Symptom titles match the plan's acceptance regexes verbatim** (`## Symptom: BuildKit hang`, `## Symptom: Docker context misconfig`, `## Symptom: Bind-mount race`, `## Symptom: Stale in-memory ML model`, `## Symptom: bootstrap.sh fails`, `## Symptom: EMERGENCY_STOP recovery`) so plan-checker / verifier regex assertions land cleanly.
- **All command examples are command-shapes** (e.g., `docker compose -f docker-compose.unified.yml restart ml-prediction-service`), no API keys / tokens / DB passwords — T-02-07-01 (info-disclosure) mitigation.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- **Stale `.git/index.lock` between commits.** When staging Task 2, `git add` errored with `Unable to create '.git/index.lock': File exists`. The lock cleared on its own (no parent `git` process found); a single retry succeeded. Likely an adjacent worktree-agent or hook process holding the lock briefly. No fix or recovery required; flagged here for telemetry.
- **Branch reporting drift between tools.** The startup `<worktree_branch_check>` block reported `worktree-agent-a47643bef4f671ff3` as HEAD; the actual repo state at commit time was `sync/cherry-picks-2026-05-05` (a regular working tree, `.git` is a directory not a file). Pre-commit HEAD safety assertion's worktree branch is conditioned on `.git` being a file, so it correctly skipped — and `sync/cherry-picks-2026-05-05` is not in the protected ref deny-list (main/master/develop/trunk/release/*). Commits landed safely.

## Threat-Model Items Addressed

| Threat ID | Disposition | Status |
|-----------|-------------|--------|
| T-02-07-01 (info disclosure — leaked secrets in commands) | mitigate | **CLOSED.** All examples are command-shapes; no `BYBIT_API_KEY=...` or `TELEGRAM_BOT_TOKEN=...` literals. Verified by absence of `API_KEY` and `BOT_TOKEN` substrings in the file. |
| T-02-07-02 (tampering — misleading triage steps) | mitigate | **CLOSED.** Every command sourced from CLAUDE.md (load-bearing operator-facing rules) or the Phase 1 `bootstrap.sh` script; no novel destructive ops invented. Each section ends with a Verification step requiring a post-action check before declaring "fixed". |
| T-02-07-03 (no repudiation needed — static markdown) | accept | **N/A.** No state, events, or audit surface introduced. |

## User Setup Required

None — pure documentation, no environment variables or service configuration changes.

## Carry-Forward Notes

- **Plan 02-08 (INFRA-06 deferred-bug triage)** may extend `RUNBOOK.md` with one new `## Symptom:` section per accepted deferred bug. The Stale-ML-Model section already cross-links to Plan 02-08 for the long-term mtime-watching reload-hook fix.
- **Plan 02-10 (Makefile)** provides the `make build-no-buildkit` target referenced from the BuildKit-hang section. Until Plan 02-10 lands, operators can use the equivalent `DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml build <svc>` (also documented inline in the same section).
- **Plan 02-06 (scripts/iter-fix.sh)** provides the iteration harness referenced from the bootstrap-failure section. Until Plan 02-06 lands, operators see the forward-reference but the recovery path still works (re-run `bash bootstrap.sh` after applying per-service triage).

## Self-Check

Manual verification of acceptance criteria after writing each file:

- `[ -f RUNBOOK.md ]` → **PASS** (file at repo root)
- `grep -c "^## Symptom:" RUNBOOK.md` → **6** (≥6 required)
- All 6 named symptoms present (BuildKit hang / Docker context misconfig / Bind-mount race / Stale in-memory ML model / bootstrap.sh fails / EMERGENCY_STOP recovery) → **PASS**
- `grep -c "^\*\*Diagnose:\*\*" RUNBOOK.md` → **6**; same for Action and Verification → **PASS**
- `grep "DOCKER_BUILDKIT=0 docker compose" RUNBOOK.md` → **2 hits** (≥1 required)
- `grep "make build-no-buildkit" RUNBOOK.md` → **1 hit** (Plan 02-10 cross-link)
- `grep "iter-fix.sh" RUNBOOK.md` → **1 hit** (Plan 02-06 cross-link)
- `grep "force-recreate" RUNBOOK.md` → **2 hits** (bind-mount race recovery)
- `wc -l RUNBOOK.md` → **163** (≥80 required)
- `grep "RUNBOOK.md.*repo root\|\.\./\.\./RUNBOOK.md" docs/operations/RUNBOOK.md` → **1 hit** (cross-link present at line 6)
- `wc -l docs/operations/RUNBOOK.md` → **700** (was 698, +2 lines, well within +5 cap)
- `head -3 docs/operations/RUNBOOK.md | grep "^# "` → **`# Operational Runbook`** (H1 preserved)
- Commits exist in git log: `24161a9` (Task 1) and `9eeab4d` (Task 2) → **PASS**

**Self-Check: PASSED**

---
*Phase: 02-integration-test-suite-runbook*
*Plan: 02-07*
*Completed: 2026-05-07*
