---
requirement: TOOL-02
phase: 15-planning-tooling-hardening
sdk_target: "~/.claude/get-shit-done/bin/lib/"
upstream_status: "proposal — not yet ported"
gate_pins: "tests/ci/test_roadmap_analyze_supersession_wired.py"
fixture: "tests/fixtures/v15_supersession/"
---

# TOOL-02 — `roadmap.analyze --apply` Umbrella-Supersession Verb

Upstream-portable spec for the `gsd-sdk query roadmap.analyze --apply` mode. The repo-side CI gate at `tests/ci/test_roadmap_analyze_supersession_wired.py` pins this contract; the upstream SDK port lives in `~/.claude/get-shit-done/bin/lib/roadmap.cjs` on the operator's host.

The canonical replay scenario is the Phase 11 → Phase 11.1 supersession captured in `tests/fixtures/v15_supersession/` — Phase 11 ("Carry-In Closure") was wholly subsumed by Phase 11.1 ("Carry-In Closure Harnesses") during v1.1, but the umbrella row was marked `[⊘]` manually. This verb automates that detection and rewrite.

## Verb contract

Invocation: `gsd-sdk query roadmap.analyze --apply`

Modes:

- **Without `--apply` (existing readiness mode, unchanged)**: emit the readiness report to stdout, exit 0. Detection logic still runs and surfaces proposed supersessions in the report, but ROADMAP.md is NOT modified.
- **With `--apply` (new mode)**: detect umbrella→decimal supersessions and write the rewrites directly into `.planning/ROADMAP.md`. Emit the unified diff that was applied to stdout for the operator's audit trail. Re-running with `--apply` is a no-op once supersessions are landed (idempotency, see below).

Exit codes:

- `0` on success (regardless of whether any supersessions were applied — a no-op is still success).
- Non-zero on parse failure or filesystem write error, with a descriptive message on stderr.

## Detection rule

For each umbrella phase `N` listed in the ROADMAP's phase detail blocks:

1. Locate the immediate-decimal child `N.M` (where `M` is digits — `11.1`, `11.2`, never `12` or `110`).
2. Parse the umbrella's `**Requirements**:` line into a set `R_N` (empty set if the line is empty or missing).
3. Parse the decimal child's `**Requirements**:` line into a set `R_NM`.
4. Check the child's checkbox: it must be `[x]` (complete).
5. If `R_NM ⊇ R_N` AND child is `[x]`, propose rewriting the umbrella's row:

   ```
   - [ ] Phase N: <title>                          (before)
   - [⊘] Phase N: <title> — superseded by Phase N.M   (after)
   ```

Edge cases (the fixture exercises these; the verb's unit tests must cover them):

- **Empty umbrella REQ set** (the canonical Phase 11 case in `tests/fixtures/v15_supersession/`): `∅ ⊆ any` — the rule trivially applies. No special-casing needed; the subset check just returns true.
- **Multiple decimal children**: pick the smallest `M` whose REQ set fully covers the umbrella. Report any additional covering children as a diff comment (informational only — they do not block the rewrite).
- **Non-decimal child**: integer phases `N+1`, `N+2` are unrelated to umbrella `N` even if numerically adjacent. Only `N.M` siblings count.
- **Already-superseded umbrella** (status already `[⊘]`): skip — no rewrite proposed. This is the idempotency guard.

## Idempotency

Re-running `gsd-sdk query roadmap.analyze --apply` on an already-superseded ROADMAP must produce a no-op diff (empty stdout, ROADMAP unchanged). The verb's unit tests must replay `tests/fixtures/v15_supersession/roadmap-after.md` as input and assert that the second `--apply` invocation produces zero changes.

Idempotency is enforced by the detection rule's "already-superseded umbrella" edge case: rows where the status is already `[⊘]` are skipped entirely.

## Diff format

The verb emits standard unified-diff format (`diff -u`-style) on the operator's `.planning/ROADMAP.md`. When `--apply` is absent, the diff is the entire stdout payload. When `--apply` is present, the diff is applied silently to the file and additionally emitted to stdout for the audit trail.

The diff is structured so that `git apply` would replay it cleanly against the BEFORE state — i.e., the verb's emitted diff is a valid input to standard diff-tooling, not a custom format.

For the Phase 11 → 11.1 canonical case the emitted diff is exactly one hunk with one line removed and one line added — see the diff between `tests/fixtures/v15_supersession/roadmap-before.md` and `tests/fixtures/v15_supersession/roadmap-after.md`.

## Wiring into complete-milestone workflow

The workflow file `~/.claude/get-shit-done/workflows/complete-milestone.md` must contain a new step between the current line-87 `roadmap.analyze` readiness check and the line-415 `milestone.complete` archival invocation. Proposed step text (to insert at approximately line 200 of the workflow, after the existing `<step name="verify_phases">` block and before the milestone-complete archival step):

```
<step name="apply_supersession">
Detect umbrella phases superseded by complete decimal children. Run:

```bash
APPLY_DIFF=$(gsd-sdk query roadmap.analyze --apply)
```

Output: any umbrella → decimal supersessions are auto-rewritten into ROADMAP.md as `[⊘] Phase N — superseded by Phase N.M`. Re-running with `--apply` is idempotent (no-op on already-superseded rows). The emitted diff is recorded in the milestone-complete archive output for the audit trail.

If `APPLY_DIFF` is non-empty, stage the ROADMAP.md change and include it in the milestone-archive commit.
</step>
```

The TOOL-02 CI gate (`tests/ci/test_roadmap_analyze_supersession_wired.py::test_roadmap_analyze_apply_wired_before_archive`) asserts both that the literal string `roadmap.analyze --apply` appears in the workflow source AND that it appears textually BEFORE the first occurrence of `milestone.complete`. The gate SKIPs cleanly when the workflow file is absent (the CI-runner case) and FAILs with a clear wiring message when the file is present but the step is missing (the developer-local-pre-port case).

## Unit test contract

The SDK verb's unit-test suite must cover these five cases, all derived from the `tests/fixtures/v15_supersession/` data:

(a) **Standard supersession**: umbrella has REQ set `{X, Y}` ⊆ decimal child REQ set `{X, Y, Z}` and child is `[x]` → propose supersession.
(b) **Empty umbrella REQ set** (Phase 11 canonical from the v15_supersession fixture): umbrella REQ set is `∅` ⊆ decimal child REQ set `{LIVECLOSE-01..05}` and child is `[x]` → propose supersession. The detection rule trivially fires (`∅` is a subset of every set).
(c) **Decimal child incomplete**: umbrella REQ set ⊆ child REQ set BUT child is `[ ]` (incomplete) → DO NOT propose supersession (precondition fails).
(d) **Strict-subset child**: decimal child REQ set is a STRICT subset of umbrella REQ set (i.e., umbrella has requirements the child doesn't cover) → DO NOT propose supersession (the rule requires `R_NM ⊇ R_N`, not the reverse).
(e) **Idempotency**: replay `tests/fixtures/v15_supersession/roadmap-after.md` as input → produce empty diff (no changes proposed).

Each test must assert both the diff content (when one is expected) and the exit code (always `0` for the cases above; non-zero is reserved for parse failures).

## Port path

Operator-side instructions for porting this verb into the host SDK:

1. **Extend `~/.claude/get-shit-done/bin/lib/roadmap.cjs`** (currently ~621 lines, no `supersed` logic — confirmed by host grep). Add a new function `detectUmbrellaSupersession(roadmapMarkdown, options)` that takes the full ROADMAP markdown plus an `{apply: bool}` object and returns either:
   - A unified-diff string (when `apply` is false), or
   - An object `{applied: true, diff: <string>}` after writing the file in place (when `apply` is true).

2. **Wire into `cmdRoadmapAnalyze`** in `~/.claude/get-shit-done/bin/lib/roadmap-command-router.cjs`. The existing readiness-mode path stays unchanged; add the `--apply` branch that calls `detectUmbrellaSupersession(..., {apply: true})` and writes the file.

3. **Update `~/.claude/get-shit-done/workflows/complete-milestone.md`** per the wiring section above — insert the `<step name="apply_supersession">` block between the existing readiness check and the archival step.

4. **Add the SDK-side unit tests** covering all 5 cases from the "Unit test contract" section. The test data is the v15_supersession fixture in this repo; the SDK tests can either symlink or copy the fixture files.

5. **Re-run `pytest tests/ci/test_roadmap_analyze_supersession_wired.py -v`** locally. The wiring assertion `test_roadmap_analyze_apply_wired_before_archive` should flip from FAIL to PASS once the workflow contains the new step. The two fixture-validation tests pass unconditionally (no port required).

The repo-side gate is asymmetric by design: it SKIPs in CI runners (no `.claude/get-shit-done/` install in the runner's HOME) and fires only for developers running locally with the host SDK present. This asymmetry is documented in Phase 15 PATTERNS.md §2 recommendation (a) and is the pinning mechanism for the operator-side port.
