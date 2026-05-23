---
phase: 15-planning-tooling-hardening
reviewed: 2026-05-23T01:50:00Z
depth: deep
files_reviewed: 12
files_reviewed_list:
  - tests/ci/test_no_placeholder_one_liners.py
  - tests/ci/test_roadmap_analyze_supersession_wired.py
  - tests/ci/test_audit_freshness_gate.py
  - tests/fixtures/v11_13h_gap/scenario.json
  - tests/fixtures/v15_supersession/scenario.json
  - tests/fixtures/v15_supersession/roadmap-before.md
  - tests/fixtures/v15_supersession/roadmap-after.md
  - .planning/sdk-proposals/TOOL-01-spec.md
  - .planning/sdk-proposals/TOOL-02-spec.md
  - .planning/sdk-proposals/TOOL-03-spec.md
  - .github/workflows/planning-tooling-gate.yml
  - scripts/install-pre-commit.sh
findings:
  critical: 3
  warning: 6
  info: 5
  total: 14
status: clean
fix_iteration: 1
fix_applied_at: 2026-05-23T02:30:00Z
fixed:
  critical: 3
  warning: 6
  info: 0
skipped:
  info: 5
---

# Phase 15: Code Review Report

**Reviewed:** 2026-05-23T01:50:00Z
**Depth:** deep
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Phase 15 ships three CI grep gates (TOOL-01/02/03), three SDK proposal specs (documentation-only), a CI workflow, and an opt-in pre-commit installer. Empirical replay confirms:

- TOOL-01 grep gate is functionally correct: the documented intentional RED state at `.planning/phases/13-bybit-connector-market-data-centralization/13-04-SUMMARY.md:60` fires exactly once with `placeholder_task_n`, and the dual-form grep parity test produces an aligned set. The candidate-position extractor correctly strips YAML frontmatter, handles missing/empty frontmatter, and skips the heading line itself. Allowlist semantics drop entries without `reason` per the Phase 14 idiom.

- TOOL-02 fixture validators pass; the wiring test correctly RED-fails on the unported host SDK workflow (the `--apply` literal is absent). However, the `_ARCHIVE_PATTERN` and `_APPLY_PATTERN` regexes match unrelated prose `**Note:**` lines in the live workflow rather than the actual `gsd-sdk query milestone.complete` / `roadmap.analyze --apply` invocations — the eventual GREEN state will not validate what the contract claims.

- TOOL-03 fixture arithmetic is internally consistent (78890s ≈ 21.91h matches the timestamp delta exactly) and the field-name drift assertion is non-flaky. But the wiring test's token-presence assertion (`"audited" in text and "VERIFICATION.md" in text`) passes against the unmodified, unported host workflow — both tokens occur in unrelated prose. The test gives zero signal regardless of port state.

- The pre-commit installer's embedded hook unconditionally invokes the wiring tests, which RED-FAIL on any developer machine with the host SDK installed (the realistic operator profile). This blocks every commit on that machine until the operator-side SDK port lands — installing the hook makes commits impossible.

- CI workflow YAML is correct in shape but lacks explicit `permissions:`, `paths:` filter, and `concurrency:` group; these are operational hygiene, not correctness defects.

Three BLOCKERs below describe failures that defeat the TDD-discipline forcing functions the specs promise and one usability defect that breaks the opt-in installer for its intended operator profile. Severity ordering: CR-01 (TOOL-03 zero-signal) > CR-02 (TOOL-02 prose-matched regex) > CR-03 (installer blocks all commits on SDK-present machines).

## Critical Issues

### CR-01: TOOL-03 wiring test is structurally insensitive to port state — zero signal

- file: `tests/ci/test_audit_freshness_gate.py:109-115`
- issue: The token-presence assertion `assert "audited" in text and "VERIFICATION.md" in text` passes against the **unmodified** live host SDK workflow at `~/.claude/get-shit-done/workflows/complete-milestone.md`. Confirmed empirically — `pytest tests/ci/test_audit_freshness_gate.py::test_audit_freshness_check_unconditional_in_workflow -v` PASSES today against the unported workflow because:
  - `audited` appears in the unrelated prose `- [ ] Out of Scope reasoning audited`
  - `VERIFICATION.md` appears in extraction prose `From VERIFICATION.md files: Extract verification scores, gaps found`
  - None of the three FORBIDDEN_ESCAPE_HATCHES tokens are present in the unported workflow either.

  Per TOOL-03-spec.md "Port path" the correct port adds a new step ALSO containing both `audited` and `VERIFICATION.md` tokens. Therefore the test passes BOTH pre-port AND post-port. It cannot distinguish the contract states it claims to enforce, and the spec's promise that "this test fires once the SDK is upgraded" is false — there is no transition. The forcing function described in 15-CONTEXT.md and the TDD-discipline note at the top of the test file is broken at source.
- recommendation: Replace the loose substring tests with a structural assertion that pins the audit-freshness check is wired into the actual archive step block, not just present anywhere in the document. One concrete fix:
  ```python
  # Locate the archive-step block by an anchor that is unique to the archive step.
  archive_block_re = re.compile(
      r"<step name=\"archive_milestone\">(.*?)</step>", re.DOTALL
  )
  m = archive_block_re.search(text)
  assert m, "archive_milestone step block not found in workflow"
  block = m.group(1)
  # Require both tokens INSIDE the archive step block, plus a structural marker
  # the port must add (e.g., --accept-stale-audit, or a literal
  # function-call shape like `audit_freshness_check`).
  assert "--accept-stale-audit" in block, (
      "audit-freshness gate not wired: --accept-stale-audit override flag "
      "must appear inside the archive_milestone step block per TOOL-03-spec.md."
  )
  assert "audited" in block and "VERIFICATION.md" in block, (
      "audit-freshness gate not wired: both `audited` and `VERIFICATION.md` "
      "tokens must appear inside the archive_milestone step block."
  )
  ```
  Cross-reference the spec's "Port path" section so the test's structural markers match exactly what the port adds.

### CR-02: TOOL-02 wiring test `_ARCHIVE_PATTERN` (and `_APPLY_PATTERN`) match prose, not invocations

- file: `tests/ci/test_roadmap_analyze_supersession_wired.py:79-81,107-130`
- issue: The regex `_ARCHIVE_PATTERN = re.compile(r"^[^#<\n]*milestone\.complete", re.MULTILINE)` matches the FIRST line containing `milestone.complete` whose start does not begin with `#` or `<`. In the live host SDK workflow the first such occurrence is the prose line at line 221:
  ```
  **Note:** MILESTONES.md entry is now created automatically by `gsd-sdk query milestone.complete` in the archive_milestone step.
  ```
  The actual archive invocation is at line 415:
  ```
  ARCHIVE=$(gsd-sdk query milestone.complete "v[X.Y]" --name "[Milestone Name]")
  ```
  Reproduction: the failing test output during this review showed `archive_match = <re.Match object; span=(6501, 6596), match='**Note:** MILESTONES.md entry is now created auto'>` — the regex anchored on the prose `**Note:**` line, not the command.

  Today the test is RED on `apply_pos >= 0` (the `--apply` literal does not appear in the workflow at all). But once the operator inserts the new `--apply` step at the contractually correct location per TOOL-02-spec.md (between the existing readiness check and the line-415 archive command, i.e., at any line between ~222 and ~414), the test will:
  - flip `apply_pos` to point at the new step (real, correct), and
  - keep `archive_pos = 6501` (the prose note, wrong),
  - and then assert `apply_pos < archive_pos` → FAIL with a confusing message blaming step ordering that is actually correct.

  The companion `_APPLY_PATTERN` has the same root weakness — it does not pin a real command-invocation shape. It just doesn't false-fire today because `--apply` doesn't appear anywhere yet. As soon as a prose `**Note:** Use \`gsd-sdk query roadmap.analyze --apply\` to apply supersessions` is added (documenting the new step before the actual invocation), `apply_pos` will point at the prose mention instead.
- recommendation: Anchor both regexes on a command-invocation shape that excludes inline-code/prose mentions. A reasonable approximation:
  ```python
  # Match only invocations that begin a shell command line, not prose backticks.
  # Accepts $(...) capture forms, leading whitespace before the command, and
  # the bare gsd-sdk invocation. Rejects lines that have the token inside
  # backtick-quoted prose by requiring `gsd-sdk query` to start a token sequence
  # at or near beginning-of-line.
  _APPLY_PATTERN = re.compile(
      r"^[ \t]*(?:[A-Z_]+=\$\()?\s*gsd-sdk\s+query\s+roadmap\.analyze\s+--apply\b",
      re.MULTILINE,
  )
  _ARCHIVE_PATTERN = re.compile(
      r"^[ \t]*(?:[A-Z_]+=\$\()?\s*gsd-sdk\s+query\s+milestone\.complete\b",
      re.MULTILINE,
  )
  ```
  Alternatively (more robust): locate both matches inside a fenced code block (```` ```bash ... ``` ````) by first extracting code-fence regions, then searching within them only. Cross-check the regex by adding a unit-style assertion in this same module that re-runs the regex against a known-good port fixture and confirms `apply_pos` and `archive_pos` both land on `gsd-sdk query` lines, not prose.

### CR-03: Pre-commit installer's embedded hook blocks ALL commits on machines with the host SDK installed

- file: `scripts/install-pre-commit.sh:60-65` (the embedded hook section)
- issue: The embedded pre-commit hook invokes the TOOL-02 and TOOL-03 modules unconditionally on every commit:
  ```bash
  python3 -m pytest tests/ci/test_roadmap_analyze_supersession_wired.py tests/ci/test_audit_freshness_gate.py -q || exit 1
  ```
  The installer's comment at lines 60-64 reasons about the SDK-absent case ("The wiring tests within those modules SKIP automatically if the host SDK is absent — that's the documented asymmetric contract per 15-PATTERNS.md §2 — so unconditional invocation is safe even when the operator has not installed the SDK").

  The reasoning is asymmetric in the wrong direction. The realistic profile of an operator who runs the opt-in installer is one who DOES have the host SDK installed (otherwise they would not be aware of the gates' purpose). On such a machine — including this review's reproduction environment — the TOOL-02 wiring test RED-FAILS unconditionally because the SDK workflow has not yet been ported. Result: installing the hook makes EVERY subsequent `git commit` fail with the TOOL-02 wiring assertion. The operator's only escape is `git commit --no-verify` on every commit, which defeats the gate they just installed.

  Reproduction: `python3 -m pytest tests/ci/test_roadmap_analyze_supersession_wired.py -q` on this machine (SDK at `/home/moha/.claude/get-shit-done/`) produces `1 failed, 2 passed`. Adding the same invocation as a pre-commit hook would block every commit attempted on this machine.

  This also interacts with CR-01 / CR-02 — the TOOL-03 wiring test would not block (it incorrectly passes per CR-01), but the TOOL-02 wiring test will block reliably.
- recommendation: Either (a) restrict the hook to the unconditional fixture-replay tests only, leaving wiring tests for CI and ad-hoc local runs:
  ```bash
  # Skip wiring tests in the commit hook -- they require an operator-side
  # SDK port that this hook cannot drive. CI workflow remains authoritative
  # for the wiring contract.
  python3 -m pytest \
    tests/ci/test_roadmap_analyze_supersession_wired.py \
    tests/ci/test_audit_freshness_gate.py \
    -q -k "fixture or field_name or supersession" || exit 1
  ```
  Or (b) deselect the wiring tests explicitly:
  ```bash
  python3 -m pytest \
    tests/ci/test_roadmap_analyze_supersession_wired.py \
    tests/ci/test_audit_freshness_gate.py \
    -q --deselect tests/ci/test_roadmap_analyze_supersession_wired.py::test_roadmap_analyze_apply_wired_before_archive \
       --deselect tests/ci/test_audit_freshness_gate.py::test_audit_freshness_check_unconditional_in_workflow \
    || exit 1
  ```
  Option (a) is cleaner. Document in the installer's header comment that wiring tests run in CI only because they require the operator-side port to land before they can flip GREEN.

## Warnings

### WR-01: Pre-commit installer's `.git` existence check is unreachable after `cd "$REPO_ROOT"`

- file: `scripts/install-pre-commit.sh:25-31`
- issue: The script computes `REPO_ROOT="$(git rev-parse --show-toplevel)"` then runs `cd "$REPO_ROOT"`. Under `set -euo pipefail`, when invoked outside any git repo, `git rev-parse` fails with a `fatal:` message and exit 128. Bash does NOT propagate command-substitution failure to `set -e` by default, so `REPO_ROOT=""` is silently assigned. The subsequent `cd ""` then succeeds (changes to `$HOME` in many bash versions) or fails depending on bash version. In both cases the explicit `if [[ ! -e .git ]]` check at lines 28-31 is unreachable in the intended scenario (operator runs the installer outside a git repo). Empirical reproduction in this review showed the script exits 128 from the `cd` line, never reaching the explicit error message.

  Symptom: an operator running the installer outside a git repo sees git's terse `fatal: not a git repository ...` instead of the friendly `[install-pre-commit] ERROR: not in a git repo (.git/ missing).` message intended by the author.
- recommendation: Move the precondition check before the `git rev-parse` call:
  ```bash
  if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
    echo "[install-pre-commit] ERROR: not in a git repo. Run from inside the repo tree." >&2
    exit 1
  fi
  REPO_ROOT="$(git rev-parse --show-toplevel)"
  cd "$REPO_ROOT"
  ```

### WR-02: Pre-commit installer's embedded hook assumes `python3 -m pytest` is available with no install guidance

- file: `scripts/install-pre-commit.sh:57,65`
- issue: The embedded pre-commit hook invokes `python3 -m pytest tests/ci/...`. If the operator does not have `pytest` installed in the resolvable Python environment, the hook fails with `No module named pytest` — and the operator cannot commit at all (the hook returns non-zero, blocking the commit). No diagnostic, no install hint, no opt-out. The script's own header acknowledges this is an "opt-in" install, but does not guard against the dependency gap.
- recommendation: Add a pytest-availability probe inside the embedded hook with a clear remediation message:
  ```bash
  if ! python3 -c "import pytest" 2>/dev/null; then
    echo "[pre-commit] pytest not installed -- skipping planning-tooling gates" >&2
    echo "  install with: python3 -m pip install pytest==7.4.4" >&2
    exit 0
  fi
  ```
  Or have the outer installer print a "verify pytest is installed before this hook fires" warning on completion.

### WR-03: TOOL-03 fixture's `audit.audited` field duplicates `audited_iso_utc` redundantly

- file: `tests/fixtures/v11_13h_gap/scenario.json:8-9`
- issue: The fixture stores the same UTC timestamp `2026-05-18T02:55:00Z` in two distinct keys: `audit.audited` and `audit.audited_iso_utc`. The intent is unclear from context — is `audit.audited` meant to mirror the actual frontmatter key (`audited:`) and therefore could legitimately drift to a non-ISO format in a future fixture? Or is it a leftover from refactoring?

  If they must always be equal, the duplication invites drift (someone updates one and not the other). If they can legitimately differ, the test assertions never check this — `test_audit_freshness_gap_above_threshold` reads only `audited_iso_utc`. Either way, the fixture's truth is split across two fields without a guard.
- recommendation: Either (a) consolidate to a single canonical field `audited_iso_utc` and drop `audit.audited`, OR (b) add a fixture-validation test that asserts `fixture["audit"]["audited"] == fixture["audit"]["audited_iso_utc"]` to lock the invariant.

### WR-04: CI workflow lacks explicit `permissions:` block

- file: `.github/workflows/planning-tooling-gate.yml:1-119`
- issue: No `permissions:` block is declared. The workflow inherits the repo-default token permissions, which on public repos and many org configurations grants `write` access to multiple scopes (contents, issues, PRs, etc.). For a read-only test workflow, this is over-permissioned. The workflow comment block at lines 30-35 claims "no command-injection surface" which is correct, but token over-permission is a separate concern that should be locked down.
- recommendation: Add an explicit top-level permissions block:
  ```yaml
  permissions:
    contents: read
  ```
  Each individual job inherits this unless overridden, satisfying the principle of least privilege.

### WR-05: TOOL-01 candidate extractor silently misses indented bold-span one-liners

- file: `tests/ci/test_no_placeholder_one_liners.py:154,276-282`
- issue: `_BOLD_SPAN_RE = re.compile(r"^\*\*([^*\n]+)\*\*\s*$", re.MULTILINE)` requires the line to START with `**` (no leading whitespace allowed). An indented bold-wrapped one-liner like `  **Task 1 — title**` falls through to the plain-body fallback path. The fallback's `raw_line.strip()` produces `**Task 1 — title**` (asterisks preserved). The banned-pattern regex `^Task\s+\d` then does NOT match because the candidate string starts with `*`, not `T`.

  Result: an indented placeholder one-liner silently passes the gate. The Phase 15 spec authors likely assumed the GSD plan template puts one-liners flush-left, which is the common case, but defensive coverage is incomplete.
- recommendation: Strip leading whitespace before bold-span detection, or relax the bold-span regex to allow indented bolds:
  ```python
  _BOLD_SPAN_RE = re.compile(r"^[ \t]*\*\*([^*\n]+)\*\*\s*$", re.MULTILINE)
  ```
  Then `bold_match.group(1).strip()` will return the inner text without asterisks, and the banned-pattern regexes will fire as intended.

### WR-06: CI workflow has no `paths:` filter — fires on every PR including doc-only changes

- file: `.github/workflows/planning-tooling-gate.yml:39-43`
- issue: The `on: pull_request: branches: [main]` trigger fires on every PR regardless of whether the planning corpus or the test files were touched. A PR that only touches `services/*/` source code, `docs/*`, or `README.md` will still run all 3 jobs (each installing pytest, running tests). At ~3s per job × 3 jobs the cost is trivial today, but at scale this is wasted CI minutes and noise in the PR-check list. The shape also makes the gate a required check for unrelated PRs, which is friction the gate doesn't earn unless planning artifacts changed.
- recommendation: Add a `paths:` filter to limit the workflow to plan/test/workflow changes:
  ```yaml
  on:
    pull_request:
      branches: [main]
      paths:
        - '.planning/phases/**'
        - '.planning/sdk-proposals/**'
        - 'tests/ci/test_no_placeholder_one_liners.py'
        - 'tests/ci/test_roadmap_analyze_supersession_wired.py'
        - 'tests/ci/test_audit_freshness_gate.py'
        - 'tests/fixtures/v11_13h_gap/**'
        - 'tests/fixtures/v15_supersession/**'
        - '.github/workflows/planning-tooling-gate.yml'
    push:
      branches: [main]
      paths: [same as above]
  ```

## Info

### IN-01: Documentation/code drift — TOOL-01 spec example uses ASCII `--`, live placeholder uses em-dash `—`

- file: `.planning/sdk-proposals/TOOL-01-spec.md:147-148`
- issue: The unit-test contract table has the example `Task 2 -- refactor module X` (ASCII double-hyphen) but the canonical RED hit in the real corpus is `Task 1 — orderbook handler refactor (TDD):` (em-dash, U+2014). Both correctly match `^Task\s+\d` because the regex constrains only the prefix, not the trailing delimiter. The drift is documentation-only and does not affect test correctness, but a reader cross-checking the spec against the live hit may briefly wonder which is canonical.
- recommendation: Note in the spec that the regex is delimiter-agnostic (matches both ASCII and Unicode dashes/em-dashes), and update the example to use the em-dash form that mirrors the GSD plan template defaults.

### IN-02: TOOL-01 allowlist test does not validate per-entry shape

- file: `tests/ci/test_no_placeholder_one_liners.py:512-531`
- issue: `test_allowlist_json_is_a_list` validates only that the top-level value is a list. Per-entry shape (the `_load_allowlist` requirement of `one_liner` + `reason` fields, both non-empty) is enforced silently at load time — entries without `reason` are dropped without any test signal. If an operator adds an entry intending to allowlist a violation but forgets `reason`, the violation reports as unsuppressed and the operator has no signal that their entry is malformed.
- recommendation: Add a per-entry validation test that asserts every entry has both `one_liner` and `reason` as non-empty strings:
  ```python
  def test_allowlist_entries_have_reason() -> None:
      if not ALLOWLIST_PATH.exists():
          return
      entries = json.loads(ALLOWLIST_PATH.read_text())
      for i, e in enumerate(entries):
          assert isinstance(e, dict), f"entry {i} is not a dict: {e!r}"
          assert e.get("one_liner"), f"entry {i} missing one_liner: {e!r}"
          assert e.get("reason"), (
              f"entry {i} missing reason -- drive-by allowlisting forbidden: {e!r}"
          )
  ```

### IN-03: CI workflow lacks `concurrency:` group — concurrent push CI runs are not cancelled

- file: `.github/workflows/planning-tooling-gate.yml:1-119`
- issue: No `concurrency` block. Rapid-fire pushes to a branch will queue multiple runs of this workflow simultaneously, wasting GitHub minutes. Minor operational concern; CI usage on this repo is currently low.
- recommendation:
  ```yaml
  concurrency:
    group: ${{ github.workflow }}-${{ github.ref }}
    cancel-in-progress: true
  ```

### IN-04: TOOL-01 test's `_archive_*` dir exclusion is dead today

- file: `tests/ci/test_no_placeholder_one_liners.py:311-315`
- issue: The defensive `_archive_*` dir filter at lines 311-315 has no live consumers — there are no `_archive_*` directories under `.planning/phases/` today. The code comment correctly notes this is "Defense-in-depth: skip ``_archive_*`` dirs if any planning system introduces them later." Acceptable as forward-looking hygiene but worth tagging as currently dead.
- recommendation: No action required. Optional: tag the comment with "TODO(future-archive): revisit when planning system introduces archive directories."

### IN-05: Marker-comment-based idempotency in installer could false-negate on unrelated hooks containing the marker substring

- file: `scripts/install-pre-commit.sh:37`
- issue: The idempotency guard `grep -q 'planning-tooling-gate-installer' "$HOOK_PATH"` checks for a marker string anywhere in the hook file. If an operator has an existing custom hook that happens to contain the string `planning-tooling-gate-installer` (for example, a comment referencing this installer in passing), the installer will skip backing it up and overwrite it. Highly unlikely in practice, but the guard is permissive.
- recommendation: Tighten the marker match to require it appears as a fenced header marker. For example, check for the exact header line `# planning-tooling-gate-installer — Phase 15 TOOL-01/02/03 pre-commit hook`:
  ```bash
  if [[ -f "$HOOK_PATH" ]] && ! head -5 "$HOOK_PATH" | grep -qF '# planning-tooling-gate-installer' 2>/dev/null; then
    cp "$HOOK_PATH" "$BACKUP_PATH"
  fi
  ```

---

## Fix Log

**Fix iteration:** 1
**Applied at:** 2026-05-23T02:30:00Z
**Scope:** BLOCKER (CR-*) + WARNING (WR-*). Info-level findings (IN-01..05) skipped per `fix_scope=critical_warning`.

| Finding | Commit | Files | Status | Rationale |
|---|---|---|---|---|
| CR-01 | `28bb0ff` | `tests/ci/test_audit_freshness_gate.py` | fixed | Replaced zero-signal `audited`+`VERIFICATION.md` token check with `--accept-stale-audit` literal discriminator (spec-mandated override flag, absent pre-port, required by port per TOOL-03-spec.md §"Override flag") + step-block structural anchor requiring both tokens to co-occur INSIDE a `<step name="...">` body. Test now RED-fails meaningfully against the unported workflow; post-port (per TOOL-03-spec.md §"Port path") it flips GREEN. Advisor flagged that REVIEW.md's proposed `<step name="archive_milestone">` anchor would over-pin since the port INSERTS a new step before `archive_milestone`, not inside it — switched to agnostic step-name match (any step body carrying both tokens). |
| CR-02 | `ea3593e` | `tests/ci/test_roadmap_analyze_supersession_wired.py` | fixed | Anchored `_APPLY_PATTERN` and `_ARCHIVE_PATTERN` on real command-invocation shapes (`^[ \t]*(?:[A-Za-z_][A-Za-z0-9_]*=\$\()?\s*gsd-sdk\s+query\s+<verb>\s+...\b`) instead of `^[^#<\n]*<verb>`. Empirically verified post-fix: `archive_match` now anchors on the real line-415 `ARCHIVE=$(gsd-sdk query milestone.complete` invocation at offset 11526, not the line-221 prose `**Note:**` at offset 6501. Eliminates the post-port misleading-ordering-error failure mode. |
| CR-03 | `4b7e181` | `scripts/install-pre-commit.sh` | fixed | Restricted pre-commit hook to in-repo symmetric tests: TOOL-01 placeholder gate + fixture-validation tests from TOOL-02/TOOL-03 modules. Operator-side wiring tests (`test_roadmap_analyze_apply_wired_before_archive`, `test_audit_freshness_check_unconditional_in_workflow`) deselected via explicit `--deselect` flags — they are CI-only by design since they require an operator-side SDK port that the pre-commit hook cannot drive. Without this, installing the hook on a developer machine with the host SDK installed (the realistic operator profile) would RED-FAIL every commit on the unported workflow, defeating the gate the operator just installed. |
| WR-01 | `4b7e181` | `scripts/install-pre-commit.sh` | fixed | Moved the `.git` precondition check ahead of `git rev-parse --show-toplevel`. Bash does not propagate command-substitution failure to `set -e`, so the prior check sequence silently assigned empty `REPO_ROOT` outside a git tree, then `cd ""` did bash-version-dependent things. Operators outside a git tree now see the intended friendly error message instead of git's terse `fatal:` output. (Co-committed with CR-03 — same script.) |
| WR-02 | `4b7e181` | `scripts/install-pre-commit.sh` | fixed | Added pytest-availability probe inside the embedded hook. Without it, an operator without pytest in their resolvable Python environment would have every commit blocked by `No module named pytest` — including the commit that installs pytest. Now the hook prints `python3 -m pip install pytest==7.4.4` as remediation and exits 0 (CI remains authoritative). (Co-committed with CR-03 — same script.) |
| WR-03 | `2d947a6` | `tests/fixtures/v11_13h_gap/scenario.json` | fixed | Consolidated fixture's duplicate `audit.audited` field into the canonical `audit.audited_iso_utc`. No test consumed the duplicate field (verified via grep across `tests/ scripts/ services/`); only `audit.frontmatter_field_name` is read (the SDK key NAME string, orthogonal to the timestamp value). The drift-risk-without-purpose was the issue. |
| WR-04 | `92d3a23` | `.github/workflows/planning-tooling-gate.yml` | fixed | Added `permissions: contents: read` top-level block. Workflow is read-only (clones repo, runs pytest); the default inherited token had broader write-scope across multiple surfaces on public/org repos. Principle-of-least-privilege baseline now locked. |
| WR-05 | `8156ac9` | `tests/ci/test_no_placeholder_one_liners.py` | fixed | Relaxed `_BOLD_SPAN_RE` from `^\*\*([^*\n]+)\*\*\s*$` to `^[ \t]*\*\*([^*\n]+)\*\*\s*$` so indented bold-span one-liners (`  **Task 1 -- title**`, common in list items / admonition blocks) enter the bold-span path properly. Without it, indented placeholders fell through to the plain-body fallback, where `raw_line.strip()` preserved the asterisks and the banned-pattern regex `^Task\s+\d` failed to fire — indented placeholders silently passed. Also updated the dual-form grep ERE in `test_grep_command_matches_pytest_scan` to mirror the change (added `^[ \t]*` allowance to the Rule/Task alternatives) so the parity set-equality assertion stays consistent. |
| WR-06 | `92d3a23` | `.github/workflows/planning-tooling-gate.yml` | fixed | Added a `paths:` filter to the workflow's `pull_request` and `push` triggers, restricting fires to changes touching `.planning/phases/**`, `.planning/sdk-proposals/**`, the 3 `tests/ci/test_*.py` files, the two fixture directories, or the workflow file itself. Eliminates wasted CI minutes on PRs touching only `services/*/`, `docs/*`, or `README.md`. The gate is no longer a required check for unrelated PRs. (Co-committed with WR-04 — same workflow file.) |

**Deferred:** IN-01 through IN-05 (5 Info-level findings) intentionally skipped per `fix_scope=critical_warning` — orchestrator policy. These are documentation/cosmetic concerns (TOOL-01 spec em-dash drift, allowlist per-entry validation test, missing `concurrency:` block, dead `_archive_*` filter, marker-comment tightening) and do not block phase progression. Recorded in original review body above for future iterations.

**Empirical verification (post-fix):** `pytest tests/ci/test_no_placeholder_one_liners.py tests/ci/test_roadmap_analyze_supersession_wired.py tests/ci/test_audit_freshness_gate.py -v` → 8 passed, 3 failed. The 3 RED-fails are the intentional contract pre-port: TOOL-01 on `13-04-SUMMARY.md:60` (per spec, milestone-close cleanup flips GREEN), TOOL-02 on missing `--apply` (per TOOL-02-spec.md §"Port path"), TOOL-03 on missing `--accept-stale-audit` (per TOOL-03-spec.md §"Port path"). All 8 unconditional fixture-replay + parity tests pass.

---

_Reviewed: 2026-05-23T01:50:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
_Fix iteration 1 applied: 2026-05-23T02:30:00Z_
_Fixer: Claude (gsd-code-fixer)_
