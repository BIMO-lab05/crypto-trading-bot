---
phase: 08-pre-live-preflight
plan: 05
subsystem: docs
tags: [runbook, preflight, live-readiness, operator-checklist, cross-link]

requires:
  - phase: 08-pre-live-preflight
    provides: PREFLIGHT-01 CLI + PREFLIGHT-02 boot-rejection + PREFLIGHT-03 CI gate (sibling plans 08-01 .. 08-04 — referenced by the new RUNBOOK section, not depended on at write-time since this is a pure-docs plan in Wave 1)
provides:
  - "RUNBOOK.md `## Pre-LIVE Operator Checklist` section with 6 Diagnose/Action/Verification subsections (one per LIVE precondition)"
  - "PROJECT.md `### Out of Scope` cross-link sub-bullet pointing at the new RUNBOOK anchor"
affects: [09-mlgate, 10-dashlive, 11-liveclose]

tech-stack:
  added: []
  patterns:
    - "Diagnose / Action / Verification triple per precondition (mirrors the existing 6-symptom RUNBOOK template at lines 21-164)"

key-files:
  created: []
  modified:
    - RUNBOOK.md
    - .planning/PROJECT.md

key-decisions:
  - "Mirror the existing 6-symptom Diagnose/Action/Verification template verbatim; new section is symptom-family even though headings use 'Precondition N:' (proactive) instead of 'Symptom:' (reactive)"
  - "Each Action block uses `sed -i` on .env + `docker compose -f docker-compose.unified.yml restart trading-engine` so the operator never edits env files by hand and always reloads lifespan-time settings"
  - "Each Verification block re-runs the CLI plus curls /api/preflight/live-readiness — keeps the dual surfaces (CLI exit code + HTTP JSON) verified together"
  - "ADR-010 paper-relaxed 10% cap is preserved — Precondition 1 instructs to restore MAX_RISK_PER_TRADE=0.02 only before flipping LIVE, never as a config default change"
  - "Cross-link target chosen as the LIVE-default Out-of-Scope bullet (PROJECT.md line 65 in the worktree branch), not the v1.1 milestone note (worktree PROJECT.md is the older revision and does not yet carry the v1.1 line — sub-bullet under the LIVE-default note is the equivalent anchor)"

patterns-established:
  - "Precondition section format: `### Precondition N: <one-line statement>` followed by Diagnose / Action / Verification triple, separated by `---` rules — Phase 10 DASHLIVE-01 will mirror the same 6 rows on the dashboard tile"

requirements-completed:
  - PREFLIGHT-04

duration: 30 min
completed: 2026-05-16
---

# Phase 08 Plan 05: Pre-LIVE Operator Checklist (RUNBOOK section + PROJECT.md cross-link) Summary

**Operator-runnable Pre-LIVE checklist added to RUNBOOK.md (6 Diagnose/Action/Verification subsections, one per LIVE precondition) and cross-linked from PROJECT.md `### Out of Scope`, completing PREFLIGHT-04.**

## Performance

- **Duration:** 30 min
- **Started:** 2026-05-16T19:48:00Z
- **Completed:** 2026-05-16T20:19:00Z
- **Tasks:** 2 / 2
- **Files modified:** 2

## Accomplishments

- RUNBOOK.md gains a top-level `## Pre-LIVE Operator Checklist` section anchored at `#pre-live-operator-checklist`, placed immediately after the existing `## Symptom: EMERGENCY_STOP recovery` block and before `## INFRA-06 Bug Triage Outcomes`, keeping the symptom-family contiguous.
- All six LIVE preconditions covered with the same Diagnose / Action / Verification format used by the existing 6 symptoms: per-trade cap ≤ 2% (LIVE-strict), `PAPER_TRADING_MODE=false`, `TRADING_MODE=LIVE`, `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`, `EMERGENCY_STOP` file absent, and DSR > 0.95 evidence row (ML-conditional).
- Each precondition's Diagnose row names the targeted `python3 scripts/preflight_live.py --check=<name>` CLI invocation and the proxied HTTP endpoint `GET /api/preflight/live-readiness` (both surfaces are built by sibling plans 08-01..08-02).
- PROJECT.md `### Out of Scope` adds one sub-bullet under the existing "Real-money LIVE trading enabled by default" entry pointing at the new RUNBOOK anchor via the relative path `../RUNBOOK.md#pre-live-operator-checklist`.
- RUNBOOK Index TOC entry inserted between the EMERGENCY_STOP recovery line and the Tournament harness line so the symptom-family TOC remains contiguous.

## Task Commits

Each task was committed atomically on the per-agent worktree branch `worktree-agent-af35c8fc2f9dc3179`:

1. **Task 1: Append Pre-LIVE Operator Checklist section to RUNBOOK.md** — `451961a` (docs)
2. **Task 2: Cross-link from PROJECT.md Out of Scope to the new RUNBOOK section** — `f8705b4` (docs)

**Plan metadata commit:** _written immediately after this SUMMARY.md as a single atomic block per execute-plan.md `git_commit_metadata` step._

## Files Created/Modified

- `RUNBOOK.md` — Added `## Pre-LIVE Operator Checklist` section (149 lines inserted) after the EMERGENCY_STOP recovery symptom, and added the matching Index TOC entry. New section location: inserted at original line 166 (between the closing `---` of the EMERGENCY_STOP section and the `## INFRA-06 Bug Triage Outcomes` heading); current section spans lines 168..324 in the post-edit file. The new top-level heading anchor is `#pre-live-operator-checklist`.
- `.planning/PROJECT.md` — Added one sub-bullet under the existing `### Out of Scope` "Real-money LIVE trading enabled by default" entry (1 line inserted at line 66). The link target is `../RUNBOOK.md#pre-live-operator-checklist` (PROJECT.md is one level deep under the repo root, so the relative path resolves correctly).

## PROJECT.md Edit — Before / After

Before (line 65 in the worktree branch):

```
- Real-money LIVE trading enabled by default — paper-mode is the safety boundary; LIVE requires three explicit flag flips and is not part of this milestone
- 30+ parallel LLM subagents for tournament — ...
```

After:

```
- Real-money LIVE trading enabled by default — paper-mode is the safety boundary; LIVE requires three explicit flag flips and is not part of this milestone
  - When flipping LIVE is in scope, the 6-precondition Diagnose/Action/Verification path lives in [RUNBOOK.md "Pre-LIVE Operator Checklist"](../RUNBOOK.md#pre-live-operator-checklist). Phase 8 enforces these in code; v1.1 does not flip LIVE.
- 30+ parallel LLM subagents for tournament — ...
```

## Decisions Made

- **Section header naming:** Used `### Precondition N: <statement>` (proactive checks) rather than `## Symptom: <thing went wrong>` (reactive recoveries) — keeps the new section visually distinct from the 6 symptom blocks while preserving the Diagnose/Action/Verification body format.
- **Restart cadence:** Every Action block ends with `docker compose -f docker-compose.unified.yml restart trading-engine` so the operator never relies on stale in-memory settings — matches the verification-standards line in CLAUDE.md ("Stale in-memory state = most common false-pass; when config changes, restart service before re-running integration tests").
- **CLI vs HTTP parity:** Each Verification block re-runs the CLI AND curls the proxied HTTP endpoint, ensuring both surfaces produce the same `status` value before the operator advances to the next precondition. Locks in the "CLI and HTTP must not drift" invariant from 08-CONTEXT.md.
- **Cross-link wording:** Used the longer Task-2 step-2 wording from the plan ("Phase 8 enforces these in code; v1.1 does not flip LIVE") rather than the generic Task-2 step-3 fallback wording, per advisor guidance — matches 08-CONTEXT.md's "cross-linked from PROJECT.md's Out of Scope LIVE-default note" intent.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Initial commit landed on the main repo's branch instead of the worktree branch**
- **Found during:** Task 1 commit (commit `4f67803` on `sync/cherry-picks-2026-05-05`)
- **Issue:** I used `cd /mnt/d/Bimo_max/crypto-trading-bot && ...` in Bash commands, which the agent thread reset between calls. The shell ended up in the main repo (where `.git` is a directory) instead of the worktree at `.claude/worktrees/agent-af35c8fc2f9dc3179/` (where `.git` is a worktree pointer file). The pre-commit HEAD-namespace assertion is guarded by `if [ -f .git ]; then`, so it silently skipped in the main repo and let the commit land on `sync/cherry-picks-2026-05-05` — a non-worktree branch. The Edit tool also targeted `/mnt/d/Bimo_max/crypto-trading-bot/RUNBOOK.md` (main repo path) instead of the worktree path.
- **Fix:** Soft-reset the main repo to `HEAD~1` (back to `75a7989`) and `git checkout HEAD -- RUNBOOK.md` to restore the file. Then re-applied both Edits against the worktree file at `/mnt/d/Bimo_max/crypto-trading-bot/.claude/worktrees/agent-af35c8fc2f9dc3179/RUNBOOK.md`. Re-staged and re-committed using `git -C <worktree-path>` so the commit landed on `worktree-agent-af35c8fc2f9dc3179`. Used `git -C` and absolute worktree paths for every subsequent git command and tool invocation.
- **Files modified:** None — the same RUNBOOK.md content was authored, just relocated from the main repo to the worktree.
- **Verification:** `git -C <worktree> log --oneline -3` confirmed commit `451961a` landed on `worktree-agent-af35c8fc2f9dc3179` (not on `sync/cherry-picks-2026-05-05`). `git -C /mnt/d/Bimo_max/crypto-trading-bot log --oneline -1` confirmed the main repo HEAD is back at `75a7989` with no spurious commit.
- **Committed in:** N/A (recovery did not produce a new commit on either branch beyond the corrected Task 1 commit `451961a`).

---

**Total deviations:** 1 auto-fixed (1 blocking — worktree cwd recovery).
**Impact on plan:** No content or scope change. The two final commits (`451961a` for Task 1, `f8705b4` for Task 2) land on the per-agent worktree branch as required by the orchestrator's parallel-merge model. The main repo's user branch `sync/cherry-picks-2026-05-05` is untouched.

## Issues Encountered

- Worktree-vs-main-repo cwd confusion — see Deviation #1 above. Resolved by switching to `git -C <worktree-path>` and absolute worktree paths for every subsequent operation.

## Threat Flags

None — pure documentation edits introduce no new trust boundaries, no new network endpoints, no new auth paths, and no new file-access patterns at security-relevant locations. The threat register's T-08-05-01 / T-08-05-02 dispositions (n/a for STRIDE; accept for info-disclosure of env-var names) remain intact.

## User Setup Required

None - no external service configuration required.

## Manual TOC-Render Check

Verified the rendered Markdown TOC: the new `## Pre-LIVE Operator Checklist` heading produces anchor `#pre-live-operator-checklist`; the Index entry on line 17 (`- [Pre-LIVE Operator Checklist](#pre-live-operator-checklist)`) links to that anchor. PROJECT.md sub-bullet's relative link `../RUNBOOK.md#pre-live-operator-checklist` resolves to the RUNBOOK section from `.planning/PROJECT.md`. Anchor `#pre-live-operator-checklist` resolves; Index entry links to section.

## Wave 1 Note

This plan ran in Wave 1 in parallel with 08-01 (foundation module). Zero code dependencies, zero test changes — pure docs plan, so safe to run alongside 08-01's code-heavy module work without merge conflicts (no shared files, no shared dependencies).

## Self-Check

- `[ -f /mnt/d/Bimo_max/crypto-trading-bot/.claude/worktrees/agent-af35c8fc2f9dc3179/RUNBOOK.md ]` → FOUND (modified, not created).
- `[ -f /mnt/d/Bimo_max/crypto-trading-bot/.claude/worktrees/agent-af35c8fc2f9dc3179/.planning/PROJECT.md ]` → FOUND (modified, not created).
- `git -C <worktree> log --oneline | grep -q 451961a` → FOUND (Task 1 commit).
- `git -C <worktree> log --oneline | grep -q f8705b4` → FOUND (Task 2 commit).
- Plan-level `<verification>` block: all 7 grep checks PASS (see Performance section grep output).

## Self-Check: PASSED

## Next Phase Readiness

PREFLIGHT-04 is complete; the operator-runnable surface for the LIVE gate is now in tree. PREFLIGHT-01..03 still need to land (sibling plans 08-01..08-04) for the CLI / endpoint / boot-rejection / CI-gate that the new RUNBOOK section references. Once 08-01..08-04 are merged, the RUNBOOK section becomes immediately actionable — no further edits to this section are required for Phase 8 close-out.

---
*Phase: 08-pre-live-preflight*
*Completed: 2026-05-16*
