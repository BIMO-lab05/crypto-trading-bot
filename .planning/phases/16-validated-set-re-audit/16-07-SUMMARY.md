---
phase: 16-validated-set-re-audit
plan: 07
subsystem: planning
tags: [audit, docs-rewrite, demotion, claude-md-correction, te-cap-demotion, phase-16-close]
requires:
  - .planning/evidence/AUDIT-01/validated-reaudit.json
  - .planning/evidence/AUDIT-01/validated-reaudit.md
  - .planning/phases/16-validated-set-re-audit/16-06-SUMMARY.md
provides:
  - PROJECT.md Validated section rewritten with file:line citations + drift annotations
  - CLAUDE.md text reconciled for CLAUDE-VALIDATED-SYMBOLS
  - DASH-01 + DASH-06 path references restored to canonical archive
  - REQUIREMENTS.md TE-CAP-01/03/04 demoted (audit-satisfied)
  - ROADMAP.md Phase 17 scope shrunk to TE-CAP-02 + TE-CAP-05
  - 16-07-SUMMARY.md closing Phase 16
affects:
  - Phase 17 v1.3 scope (5 REQs → 2 REQs)
  - Phase 21 (inherits EXEC-03 drift via TA-AGG-01)
  - Phase 23 (inherits TOURN-07 + CLAUDE-LSTM-ARCHIVED drift via ML-PURGE-02/05)
  - Phase 24 (inherits CLAUDE-SENTIMENT-REMOVED drift via HYG-01)
tech-stack:
  patterns:
    - "Trust-no-docs audit reconciliation: every Validated REQ ends carrying file:line proof or strike-through demotion"
    - "Drift-in-place annotation: drift items stay in Validated with ⚠ + downstream-owner pointer rather than silently moving to Active"
    - "Inline-fix-where-cheap: 3 NEW drift findings (CLAUDE-VALIDATED-SYMBOLS, DASH-01, DASH-06) reconciled in this plan to avoid spawning a phase for tiny diffs"
key-files:
  modified:
    - .planning/PROJECT.md
    - .planning/REQUIREMENTS.md
    - .planning/ROADMAP.md
    - CLAUDE.md
    - scripts/audit_tiles.py
    - tests/integration/test_dashboard_smoke.py
  created:
    - .planning/milestones/v1.0-phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.json
    - .planning/phases/16-validated-set-re-audit/16-07-SUMMARY.md
decisions:
  - "Approve-all on the 4 pre-existing-Validated drift routings: EXEC-03 → Phase 21 (TA-AGG-01); TOURN-07 → Phase 23 (ML-PURGE-05); CLAUDE-LSTM-ARCHIVED → Phase 23 (ML-PURGE-02); CLAUDE-SENTIMENT-REMOVED → Phase 24 (HYG-01)"
  - "Quick-fix inline for 3 NEW drift findings: DASH-01 + DASH-06 (restore 06-TILE-AUDIT.json to canonical archive path; update both consumers); CLAUDE-VALIDATED-SYMBOLS (CLAUDE.md text amended to reflect dual-symbol reality)"
  - "Demote TE-CAP-01 + TE-CAP-03 + TE-CAP-04 as audit-satisfied (Track A audit found execution-cap enforcement + ADR-010 paper cap + RISK-06 file gate already satisfied with file:line evidence); Phase 17 scope shrinks from 5 REQs to 2 REQs (TE-CAP-02 + TE-CAP-05)"
  - "Annotate drift items in-place under their original ✓/⚠ sub-headings rather than physically moving them out of Validated — preserves the audit trail in the document itself"
metrics:
  duration: "~1 hour (executor wall-clock)"
  tasks_completed: 6
  files_modified: 6
  files_created: 2
  commits: 6
  completed_date: "2026-05-23"
---

# Phase 16 Plan 07: AUDIT-01 reconciliation + Phase 16 close

## One-liner

PROJECT.md Validated section rewritten with 74 file:line citations + 4 drift annotations + 3 inline drift fixes; CLAUDE.md reconciled for the dual-symbol reality; REQUIREMENTS + ROADMAP demote TE-CAP-01/03/04; Phase 16 closed.

## What landed

### Operator decisions captured at the 16-07 checkpoint

| Decision | Resolution | Implementation |
| --- | --- | --- |
| Routing for 4 pre-existing-Validated drift items | approve-all on the Plan 06 proposals | EXEC-03 → Phase 21 (TA-AGG-01); TOURN-07 → Phase 23 (ML-PURGE-05); CLAUDE-LSTM-ARCHIVED → Phase 23 (ML-PURGE-02); CLAUDE-SENTIMENT-REMOVED → Phase 24 (HYG-01). Annotated in-place in PROJECT.md ### Validated with ⚠ + downstream-owner pointer. |
| Routing for 3 NEW drift findings | quick-fix inline (do not spawn new phases) | DASH-01 + DASH-06: 06-TILE-AUDIT.json restored from git history (commit `dab40de`) to canonical archive path under `.planning/milestones/v1.0-phases/06-dashboard-audit-safety-state/`; consumer references in `scripts/audit_tiles.py:43-54` and `tests/integration/test_dashboard_smoke.py:83-104` updated. CLAUDE-VALIDATED-SYMBOLS: CLAUDE.md "Validated symbols" rule appended with one clarifying sentence covering the market-data-service 14-symbol research-ingest universe vs trading-engine 5-symbol position-taking restriction. |
| TE-CAP-01 + TE-CAP-03 + TE-CAP-04 demotion | demote as audit-satisfied | REQUIREMENTS.md: REQ checkboxes flipped `[ ]` → `[~]` with strike-through + DEMOTED note citing the satisfying file:line evidence. Traceability table rows flipped `Pending` → `Demoted (audit-satisfied)`. PROJECT.md Active block: TE-CAP-01..05 → TE-CAP-02, TE-CAP-05. ROADMAP.md Phase 17 detail block: goal text rewritten to enumerate surviving scope. |

### PROJECT.md ### Validated rewrite

- All 74 satisfied REQs carry `— verified at \`{file}:{line}\` per AUDIT-01` citation
- 4 sub-headings preserved (Pre-v1, v1.0 shipped, v1.0 partial, v1.1 shipped, v1.1 harness-delivered, v1.1 operator-blocked) + 1 new sub-heading added (**v1.2 (shipped 2026-05-23)**) with 13 REQs (BC-01..07, MOBILE-01..03, TOOL-01..03)
- 4 pre-existing drift items annotated ⚠ in-place with downstream-owner pointer
- 3 NEW drift items reconciled inline and marked ✓ with `(reconciled inline in 16-07)`
- v1.0 partial sub-section reclassified: harness code is satisfied; wall-clock execution lives under v1.1 carry-in sub-sections (INFRA-01 / INFRA-02 / MLCL-01 / MLCL-02 no longer dangle as "partial")
- Current State block: CRITICAL/HIGH/MEDIUM findings collapsed into a single pointer at `validated-reaudit.{json,md}`
- v1.3 Active block: TE-CAP scope reduced to TE-CAP-02 + TE-CAP-05
- ## Key Decisions: new row recording the AUDIT-01 reconciliation outcome
- *Last updated:* footer refreshed

### CLAUDE.md edit

- Only CLAUDE-VALIDATED-SYMBOLS triggered a text correction. Existing "Validated symbols" rule retained; one clarifying sentence appended explaining the dual-symbol reality (trading-engine 5 / market-data-service 14)
- CLAUDE-LSTM-ARCHIVED and CLAUDE-SENTIMENT-REMOVED drift items were routed to Phase 23 / Phase 24 (no inline CLAUDE.md edit; the text will be revisited when those phases ship)
- CLAUDE-PAPER-CAP-ADR010 and CLAUDE-EXEC-MAINNET-PRICES came back satisfied — no edit

### DASH-01 + DASH-06 inline fix

- `.planning/milestones/v1.0-phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.json` restored (308 lines, content recovered from commit `dab40de`)
- `scripts/audit_tiles.py:_AUDIT_JSON` updated to point at archive path + docstring added explaining the relocation
- `tests/integration/test_dashboard_smoke.py:tile_audit` fixture updated to point at archive path + docstring added
- Verdicts inside the JSON unchanged — this is a path-only fix; the v1.0 regression gate semantics are preserved

### REQUIREMENTS.md updates

- TE-CAP-01 / TE-CAP-03 / TE-CAP-04 checkboxes flipped `[ ]` → `[~]` with strike-through + DEMOTED note citing the file:line evidence that satisfies the underlying claim
- Traceability table: those three rows flipped `Pending` → `Demoted (audit-satisfied)`
- AUDIT-01 row had already been flipped to `Complete` at Plan 06 close (no edit needed)
- Coverage math: v1.3 still has 29 REQs total; 26 Pending + 3 Demoted (down from 29 Pending)

### ROADMAP.md Phase 17 scope shrinkage

- One-line summary at top updated to flag the demotion
- Phase 17 detail block goal text rewritten to point at the AUDIT-01 evidence and enumerate the surviving REQs
- Requirements line trimmed: `TE-CAP-01, TE-CAP-02, TE-CAP-03, TE-CAP-04, TE-CAP-05` → `TE-CAP-02, TE-CAP-05`

## Verification

| Check | Result |
| --- | --- |
| PROJECT.md ### Validated has AUDIT-01 mentioned 93 times (74 file:line citations + 7 drift annotations + Key Decisions row + footer + Current State pointer + sub-heading lead-in) | ✓ |
| PROJECT.md sub-headings preserved (Pre-v1 / v1.0 / v1.0 partial / v1.1 / v1.1 harness / v1.1 operator-blocked / v1.2) | ✓ — 7 sub-heading instances detected |
| CLAUDE.md "Validated symbols" rule reflects the dual-symbol reality | ✓ |
| `.planning/milestones/v1.0-phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.json` exists and parses | ✓ — 308 lines; `tiles` key present |
| `scripts/audit_tiles.py` module-level `_AUDIT_JSON` resolves to the restored file | ✓ |
| `tests/integration/test_dashboard_smoke.py` `tile_audit` fixture path resolves | ✓ |
| `.planning/REQUIREMENTS.md` AUDIT-01 row reads `Complete` | ✓ |
| TE-CAP-01/03/04 REQ checkboxes are `[~]` with DEMOTED note | ✓ |
| TE-CAP-01/03/04 traceability rows read `Demoted (audit-satisfied)` | ✓ |
| ROADMAP.md Phase 17 detail block reflects the scope shrink | ✓ |

## Self-Check: PASSED

All expected files created/modified; all 6 commits exist on `gsd/v1.3-ta-engine-correctness`:

- `90ce0f6` fix(16-07): restore 06-TILE-AUDIT.json refs for DASH-01/06
- `f2018ea` docs(16-07): CLAUDE.md — clarify market-data 14-symbol ingest vs trading-engine 5-symbol restriction (audit AUDIT-01)
- `7fe66a1` docs(16-07): PROJECT.md ### Validated rewrite + Key Decisions + TE-CAP demotions per AUDIT-01
- `24f3fd2` docs(16-07): REQUIREMENTS.md — demote TE-CAP-01/03/04 (audit-satisfied)
- `75cff45` docs(16-07): ROADMAP Phase 17 scope shrink — TE-CAP-02 + TE-CAP-05 only
- (this commit) docs(16-07): summary + Phase 16 close

## Phase 16 closing notes

- Phase 16 is **ready for /gsd-transition** to Phase 17 (or whichever Track A/B/cross-cutting phase the orchestrator dispatches next)
- v1.3 baseline is now truthful: every Validated REQ carries either file:line proof or a downstream-owner pointer
- Phase 17 scope shrunk from 5 REQs to 2 REQs
- Phase 21 inherits EXEC-03 drift (TA-AGG-01 already covers it)
- Phase 23 inherits TOURN-07 + CLAUDE-LSTM-ARCHIVED drift (ML-PURGE-02 + ML-PURGE-05 already cover them)
- Phase 24 inherits CLAUDE-SENTIMENT-REMOVED drift (HYG-01 already covers it)
- Three NEW drift findings (DASH-01, DASH-06, CLAUDE-VALIDATED-SYMBOLS) closed in-plan; no downstream debt
- TE-CAP-01/03/04 demotions are documented; if a future audit finds the underlying RISK-02/06 satisfactions were incorrectly read, the demotions can be reversed by editing REQUIREMENTS.md status back to Pending — the REQ definitions remain intact under strike-through

## Deviations from Plan

### Plan-task vs operator-task reconciliation

The original 16-07-PLAN.md had 4 tasks (Task 1 checkpoint:decision → Task 2 PROJECT.md → Task 3 CLAUDE.md → Task 4 REQUIREMENTS + summary). The operator's prompt overrode the checkpoint and supplied 6 atomic tasks. This executor followed the operator's task list verbatim:

1. Quick-fix DASH-01 + DASH-06 (TILE-AUDIT.json restore) — landed as commit `90ce0f6`
2. CLAUDE.md edit for CLAUDE-VALIDATED-SYMBOLS — landed as commit `f2018ea`
3. PROJECT.md ### Validated rewrite + Key Decisions + TE-CAP demotions — landed as commit `7fe66a1`
4. REQUIREMENTS.md TE-CAP-01/03/04 demotion — landed as commit `24f3fd2`
5. ROADMAP.md Phase 17 scope shrink — landed as commit `75cff45`
6. SUMMARY + Phase 16 close — this commit

All operator decisions captured in the table above; no implicit auto-fixes (Rules 1-3) needed.

### REQUIREMENTS.md AUDIT-01 row was already Complete

The original plan Task 4 specified flipping `| AUDIT-01 | Phase 16 | Pending |` → `Complete`. On reading the file, the row already read `Complete` (flipped at Plan 06 close). No edit needed; the SUMMARY notes this for the trail.

### v1.0 partial sub-section reclassification

The original v1.0 partial sub-section listed INFRA-01 / INFRA-02 / MLCL-01 / MLCL-02 as `⚠` partial. AUDIT-01 found all four satisfied at file:line. They are now listed under the canonical v1.0 sub-heading with their citations; the partial sub-section now carries an explanatory note rather than dangling REQs. This avoids double-listing the same REQs.

## Audit-trail artifacts

- Canonical machine ledger: `.planning/evidence/AUDIT-01/validated-reaudit.json` (74 satisfied / 7 drift / 0 missing across 81 Validated REQs)
- Human summary: `.planning/evidence/AUDIT-01/validated-reaudit.md` (drift / coverage / methodology / implications)
- Per-track delta files retained per CONTEXT D-03: `track-A-deltas.json`, `track-B-deltas.json`, `track-C1-deltas.json`, `track-C2-deltas.json`
- Phase 16 plans + summaries: `.planning/phases/16-validated-set-re-audit/16-{01..07}-{PLAN,SUMMARY}.md`
