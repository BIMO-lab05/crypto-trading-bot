# Phase 15: Planning-Tooling Hardening - Context

**Gathered:** 2026-05-22
**Status:** Ready for planning
**Mode:** Auto-generated (smart-discuss infrastructure detection — pure tooling phase, no user-facing behavior, all success criteria are technical: command exits, tests pass, files exist)

<domain>
## Phase Boundary

Three recurring frictions from v1.0 and v1.1 retros become structurally impossible in the GSD planning-tooling stack:

1. **TOOL-01 — One-liner discipline:** `plan.validate` rejects placeholder one-liners (`Rule N` / `Task N` / `<one-line summary>` / empty) at pre-commit + CI time so `summary-extract` cannot auto-generate garbage MILESTONES.md entries.
2. **TOOL-02 — Umbrella-phase supersession:** `roadmap.analyze` auto-detects when a decimal phase's REQ set covers its umbrella parent and marks the parent `Superseded by N.M [⊘]` in ROADMAP.md (idempotent, diff-to-stdout for operator review).
3. **TOOL-03 — Audit-timing drift:** `/gsd-complete-milestone` refuses to archive when the latest `v[X.Y]-MILESTONE-AUDIT.md` `audited_at` predates the most recent phase's `VERIFICATION.md` mtime by >1h (replays the v1.1 13h-gap scenario as a fixture).

Override flag `--accept-stale-audit` documented for emergency closes. All three contracts pinned by CI grep gates.

The phase touches `@gsd-build/sdk` source under `~/.claude/get-shit-done/` / `node_modules/@gsd-build/sdk/`, plus repo-local `tests/ci/` files. No trading-engine impact; runs in parallel with Phase 13/14 (now complete).

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — smart-discuss skipped per infrastructure-phase detection (pure tooling work, no UI / no user-facing behavior, all success criteria are mechanical: CLI exit codes, file presence, test pass/fail).

Use ROADMAP success criteria + REQUIREMENTS.md as the spec. Codebase conventions for the GSD SDK + tests/ci/ already established by prior phases (e.g., Phase 12 CI Recovery, Phase 13 BC-03 grep gate, Phase 14 anti-hidden grep gate) — follow those patterns.

### Recurring patterns to follow
- **Grep-gate tests under `tests/ci/test_*.py`** — pinning textual contracts in source/workflow files (Phase 12 + 13 + 14 precedent).
- **`@gsd-build/sdk` query verbs** — implementation lives under `~/.claude/get-shit-done/get-shit-done/bin/lib/` or `node_modules/@gsd-build/sdk/dist/`. Exact path depends on which clone is canonical for this repo's invocations.
- **Pre-commit hook hookup** — local hooks at `.git/hooks/pre-commit` already check various invariants; PLAN.validate hook should chain into the existing entrypoint without breaking other checks.
- **Fixture-based replays** — Phase 11/11.1 history is the v1.1 13h-gap scenario; pytest fixtures replay it.

</decisions>

<canonical_refs>
## Canonical References

Downstream agents MUST read these before planning or implementing:

### Planning-tooling ecosystem
- `~/.claude/get-shit-done/get-shit-done/bin/cli.js` — SDK entrypoint (if vendored locally)
- `node_modules/@gsd-build/sdk/dist/cli.js` — SDK CLI binary (live invocation surface)
- `~/.claude/get-shit-done/workflows/plan-phase.md` — current `plan.validate` consumers
- `~/.claude/get-shit-done/workflows/complete-milestone.md` — current `roadmap.analyze` + audit-timing consumers
- `~/.claude/get-shit-done/templates/plan.md` — the canonical PLAN.md template (placeholder strings to reject)

### Repo-local CI gate patterns to mirror
- `tests/ci/test_no_bybit_bypass.py` (Phase 13 BC-03) — grep gate template
- `tests/ci/test_no_mobile_hidden_data.py` (Phase 14, sibling: `tests/integration/test_no_mobile_hidden_data.py`) — alt allowlist + grep-gate pattern
- `.github/workflows/dashboard-smoke.yml` — workflow extension pattern for CI integration

### v1.1 13h-gap fixture source data
- `.planning/milestones/v1.1-MILESTONE-AUDIT.md` (audited_at frontmatter)
- `.planning/milestones/v1.1-phases/*/12-VERIFICATION.md` (most recent VERIFICATION.md mtime in v1.1 — anchor for the >1h replay)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets
- Grep-gate test template (mirror from Phase 13 / 14 — same shape: enumerate files, regex, allowlist, fail count).
- `gsd-sdk query <verb>` infrastructure — already wired; new verbs `plan.validate` and `roadmap.analyze --apply` are additive.
- Pre-commit hook chain — `.git/hooks/pre-commit` extends here.

### Established patterns
- All CI gates have an allowlist JSON sibling (one per gate) to handle the "intentional exceptions" case cleanly. TOOL-01 should adopt the same shape if any placeholder-like strings need to be retained (probably none, but consistent).
- ROADMAP.md edits are diff-to-stdout by default + `--apply` writes in place (per TOOL-02 spec). Mirror `audit_responsive.py` and the GSD plan-progress updater for idempotency.
- Audit fixtures live under `.planning/fixtures/` or `tests/fixtures/` — pick the existing convention.

### Integration points
- `/gsd-complete-milestone` (the workflow file) gets the audit-timing gate at archive-time. Override flag `--accept-stale-audit` propagates through.
- `plan-phase` orchestrator already invokes `plan.validate` per workflow (line 743) — the new rejection patterns plug in there.
- `audit-milestone` / `complete-milestone` orchestrator gets a `roadmap.analyze --apply` step before archiving (per TOOL-02 spec).

</code_context>

<specifics>
## Specific Ideas

- The 5 placeholder one-liner patterns to reject in TOOL-01: `^Rule \d`, `^Task \d`, `^one-liner:\s*$`, `<one-line summary>`, empty string. Wire all 5 into one validator that returns the offending pattern name on rejection (so error messages are precise).
- For TOOL-02, the supersession detection trigger is `requirements(N.M) ⊇ requirements(N)` where both are sets parsed from `**Requirements**:` lines in ROADMAP. Phase 11 → 11.1 is the canonical fixture (REQ set of 11.1 = LIVECLOSE-01..05; Phase 11 has no REQ set since it's superseded — confirm parser handles the empty-set umbrella correctly).
- For TOOL-03, the >1h threshold is per ROADMAP spec. The override flag MUST log into the archive (so future readers see the stale-audit was explicitly accepted, not silently bypassed).

</specifics>

<deferred>
## Deferred Ideas

- Auto-fix mode for placeholder one-liners — rejection-only for now. Auto-suggest the offending plan's `<objective>` block as a starting point would be a follow-up; not in Phase 15 scope.
- TOOL-02 hook into `/gsd-new-milestone` (proactively detect supersession on roadmap creation) — current scope is detection at `complete-milestone` time only.
- Bypass-flag telemetry — counting `--accept-stale-audit` invocations over time to inform whether the 1h threshold needs tuning. Out of scope.

</deferred>

---

*Phase: 15-planning-tooling-hardening*
*Context gathered: 2026-05-22 via smart-discuss infrastructure detection*
