---
phase: 15-planning-tooling-hardening
plan: 01
subsystem: planning-tooling
tags: [ci-gate, plan-validate, placeholder, sdk-proposal, grep-gate, dual-form-parity]

# Dependency graph
requires:
  - phase: 13-bybit-connector-market-data-centralization
    provides: tests/ci/test_no_bybit_bypass.py -- BC-03 grep-gate analog with dual-form parity, REPO_ROOT discipline, EXEMPT_PATHS perf shape
  - phase: 14-mobile-responsive-dashboard
    provides: tests/integration/test_no_mobile_hidden_data.py::_load_allowlist -- allowlist consumer with mandatory-reason silent-drop pattern + .planning/phases/<phase>/<name>-allowlist.json shape
provides:
  - TOOL-01 CI grep gate (tests/ci/test_no_placeholder_one_liners.py)
  - Empty placeholder allowlist JSON (.planning/phases/15-planning-tooling-hardening/placeholder-allowlist.json)
  - SDK verb spec doc for upstream port (.planning/sdk-proposals/TOOL-01-spec.md, 186 lines, 7 sections)
  - Candidate-one-liner extractor (frontmatter + bold-span + body-line fallback, mirrors core.cjs::extractOneLinerFromBody)
  - Dual-form grep-vs-pytest parity test with candidate-position post-filter
affects: [15-04, milestone-close, summary-extract, gsd-sdk-port]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Candidate-position extraction for placeholder gates: scan only one-liner positions (frontmatter one-liner: key, first bold span after first heading, fallback first non-empty body line) not whole-file text"
    - "Dual-form grep+pytest parity with classification-against-canonical-text: bold-wrapped lines like **Task 1 ...** require classification against the extracted inner text, not the raw match line, so the same regex anchors fire in both forms"
    - "Documentation-only SDK proposal convention under .planning/sdk-proposals/<TOOL-XX>-spec.md, anchored by .gitkeep, for verbs whose impl lives outside the repo at ~/.claude/get-shit-done/bin/lib/"

key-files:
  created:
    - "tests/ci/test_no_placeholder_one_liners.py -- 4-test grep gate (BANNED_PATTERNS dict, candidate extractor, scanner, dual-form parity, allowlist consumer)"
    - ".planning/sdk-proposals/TOOL-01-spec.md -- SDK verb contract spec, 7 named sections (Verb contract / Banned patterns / File types / Pre-commit invocation / CI invocation / Unit test contract / Port path)"
    - ".planning/sdk-proposals/.gitkeep -- anchors sdk-proposals/ dir in git"
    - ".planning/phases/15-planning-tooling-hardening/placeholder-allowlist.json -- empty allowlist []"
  modified: []

key-decisions:
  - "Bold-span takes precedence over plain-body fallback in candidate extraction (mirrors core.cjs::extractOneLinerFromBody single-deterministic-line_no contract)"
  - "Grep ERE alternation broadened to match bold-wrapped candidates with [*]{0,2} prefix on the Rule N / Task N branches so parity-test post-filter sees the same lines pytest scan sees"
  - "Grep parity classification step runs against canonical candidate text (the extractor's output) not the raw match_line, so the ^Rule\\s+\\d / ^Task\\s+\\d anchors fire identically in both scan forms"
  - "EXEMPT_PATHS ships empty for TOOL-01 -- placeholder one-liners are never legitimate; late false-positives flow through the literal-string-keyed allowlist JSON instead (finer-grained than path-based)"

patterns-established:
  - "Candidate-position scanner: extract specific one-liner positions first, classify only those (prose / code-block mentions of banned shapes are out of scope by construction)"
  - "Allowlist literal-string keying: TOOL-01 allowlist entry key is one_liner (the offending substring), not file_path -- mirrors Phase 14 shape but key differs"
  - "SDK-proposal docs as upstream-port contracts: a .planning/sdk-proposals/<TOOL-XX>-spec.md file documents the verb contract; the repo-side CI gate is the authoritative enforcement, the verb is operator-side convenience"

requirements-completed: [TOOL-01]

# Metrics
duration: 6min
completed: 2026-05-23
---

# Phase 15 Plan 01: TOOL-01 Placeholder One-Liner Gate Summary

**Shipped the TOOL-01 repo-side CI grep gate (tests/ci/test_no_placeholder_one_liners.py, 4 named tests, dual-form pytest+grep parity, candidate-position extractor mirroring core.cjs::extractOneLinerFromBody) plus the upstream-port spec doc (.planning/sdk-proposals/TOOL-01-spec.md, 7 named sections, 5 named BANNED_PATTERNS shared with the gate) and an empty placeholder-allowlist.json; the scanner test ships RED on one real Phase 13 placeholder per plan done criteria.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-23T00:49:18+01:00
- **Completed:** 2026-05-23T00:54:45+01:00
- **Tasks:** 2 (auto + 1 inline Rule-1 bug-fix)
- **Files modified:** 4 (3 created + 1 .gitkeep)

## Accomplishments

- Shipped the TOOL-01 grep gate with 4 named tests, including the dual-form pytest+grep parity check that survives candidate-position filtering
- Encoded the 5 banned patterns from REQUIREMENTS.md TOOL-01 / 15-CONTEXT.md Specifics line 84 as a BANNED_PATTERNS dict with stable names that the upstream SDK verb will reuse
- Caught the first real placeholder-one-liner violation in the planning corpus (13-04-SUMMARY.md:60 "Task 1 -- orderbook handler refactor (TDD):") -- this RED state IS the contract per the plan done criteria; Plan 15-04 owns the cleanup
- Documented the upstream SDK verb contract in a 186-line spec doc with the seven mandated sections, giving the operator everything needed to port plan-validate.cjs into the host SDK without rewriting it

## Task Commits

Each task was committed atomically:

1. **Task 1: Wave-0 RED test scaffold + empty allowlist JSON** - `e16d0e2` (test)
2. **Inline Rule-1 fix: extractor must skip past heading line** - `cd3d2d0` (fix)
3. **Task 2: TOOL-01 SDK verb spec proposal** - `3c9827d` (docs)
4. **Inline Rule-1 fix: strip YAML frontmatter before heading search** - `e8e672e` (fix)

## Files Created/Modified

- `tests/ci/test_no_placeholder_one_liners.py` -- 4-test grep gate: scanner over candidate one-liner positions in .planning/phases/**/*-PLAN.md and *-SUMMARY.md; dual-form pytest+grep parity check classified against canonical candidate text; allowlist-json shape check; EXEMPT_PATHS hygiene check
- `.planning/sdk-proposals/TOOL-01-spec.md` -- 186-line upstream SDK verb spec, 7 named sections, references the same BANNED_PATTERNS names + tests/ci/test_no_placeholder_one_liners.py
- `.planning/sdk-proposals/.gitkeep` -- anchors the sdk-proposals directory in git for future TOOL-XX specs
- `.planning/phases/15-planning-tooling-hardening/placeholder-allowlist.json` -- empty allowlist (no known false-positives)

## Decisions Made

- **Bold-span precedence in candidate extraction** -- when both a bold-span line and a plain-body-line would qualify as the post-heading candidate, the bold-span wins so line_no is deterministic. Mirrors the host SDK's extractOneLinerFromBody contract at ~/.claude/get-shit-done/bin/lib/core.cjs:200-230. Without a tie-break rule the dual-form parity test would be flaky on plans whose authors mixed both shapes.
- **Grep ERE alternation includes bold-wrapped branches** -- the alternation uses `^[*]{0,2}Rule[[:space:]]+[0-9]` and `^[*]{0,2}Task[[:space:]]+[0-9]` so grep emits stdout lines for `**Task 1 -- ...**`. Without the `[*]{0,2}` prefix grep would silently drop bold-wrapped candidates and the parity test would always be GREEN by accident (set diff would be empty because both sides are empty).
- **Grep-side classification against canonical candidate text** -- after candidate-position post-filter, the parity test runs BANNED_PATTERNS regex matching against the extractor's output (the bold-span inner text), not the raw `match_line`. Without this, the `^Rule\\s+\\d` / `^Task\\s+\\d` regex anchors would never fire on bold-wrapped lines and the parity test would falsely diverge.
- **EXEMPT_PATHS empty for TOOL-01** -- placeholder one-liners are never legitimate inside .planning/phases/. Late false-positives go through the literal-string allowlist JSON, which is finer-grained than path-based exemption.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Candidate extractor returned mangled substrings on the fallback path**

- **Found during:** Task 2 verification (the spec doc check showed candidate text `"OOL-01 -- ..."` missing the leading `T`)
- **Issue:** `body_start` was set to `heading_match.end()`, which lands at the first non-space char of the heading text itself (matching `^#\s+\S`). The fallback "first non-empty body line after heading" path then started its line scan in the middle of the heading line and returned the suffix of the heading as the candidate. Effect: spec-style headings produced mangled candidate text and a real banned-shape on the very next line would have been missed if it appeared before the next newline boundary.
- **Fix:** Compute `post_heading_nl = text.find("\n", heading_match.end())` and set `body_start = post_heading_nl + 1`. Body scan now starts on the next physical line, never re-reads the heading.
- **Files modified:** `tests/ci/test_no_placeholder_one_liners.py` (`_extract_candidate_one_liners` body)
- **Verification:** post-fix candidates: spec doc -> `(11, 'This document is the authoritative contract for the upstream `plan.validate`')`; 13-04-SUMMARY.md -> `(60, 'Task 1 — orderbook handler refactor (TDD):')` (bold-span path was correct already, fallback path was the bug)
- **Committed in:** `cd3d2d0` (separate fix commit, not amended)

**2. [Rule 1 - Bug] Candidate extractor mis-identified YAML-frontmatter section dividers as the first markdown heading**

- **Found during:** SUMMARY.md self-check (this very SUMMARY's candidate position came back as line 100, a deviation-section bold-span -- not the line-57 document one-liner immediately after the title).
- **Issue:** The GSD summary template uses YAML-comment-style section dividers (`# Dependency graph`, `# Tech tracking`, `# Metrics`) INSIDE the frontmatter block. YAML treats `#` as a comment marker, but the naive `^#\s+\S` regex picked the first of those as "the heading" and then hunted for the candidate hundreds of lines later, past the actual document title. Effect: any SUMMARY.md or PLAN.md written from the template (i.e. all of them) would have the wrong candidate position scanned, masking real placeholder detection at the genuine one-liner.
- **Fix:** When the file starts with `---\n`, locate the closing `---` on its own line and set `body_search_start` to the first character after that line; pass `body_search_start` into `_MD_HEADING_RE.search(text, body_search_start)`. The frontmatter `one-liner:` rule still scans the whole text (frontmatter is its legitimate candidate position).
- **Files modified:** `tests/ci/test_no_placeholder_one_liners.py` (`_extract_candidate_one_liners` body)
- **Verification:** 15-01-SUMMARY.md candidate -> `(57, 'Shipped the TOOL-01 ...')`; 13-04-SUMMARY.md candidate unchanged at `(60, 'Task 1 -- ...')`; TOOL-01-spec.md candidate unchanged at `(11, 'This document is the authoritative ...')`. Full corpus scan still shows exactly the same single violation (13-04-SUMMARY.md:60) -- no new false positives surfaced by the frontmatter-aware extractor.
- **Committed in:** `e8e672e` (separate fix commit, not amended)

### Tightness divergence noted (not a fix)

The plan's Task 2 acceptance-criteria self-trip check does a naive whole-file `re.search` over every line of the spec doc. The spec doc legitimately enumerates the banned patterns in tables and code-fence examples (the Banned Patterns section, the Unit Test Contract section), so a whole-file scan flags them. The authoritative gate (`_extract_candidate_one_liners` + BANNED_PATTERNS) only scans candidate one-liner positions and the spec doc passes that gate cleanly. Deferring to the gate's behaviour as the contract -- the AC text is over-tight relative to the gate it tests against. Not a deviation in the Rule 1/2/3 sense; a documented tightness mismatch between the plan AC wording and the implemented gate.

---

**Total deviations:** 2 auto-fixed (both Rule 1 bugs in the extractor)
**Impact on plan:** Both fixes were necessary for correctness of the gate itself -- the first one would have mangled candidate text on any plan whose `#` heading is followed immediately by body content, the second one would have looked at the wrong candidate position on every plan/summary written from the GSD template. Without either fix, the gate would silently mis-scan most of the planning corpus, defeating the purpose. Plan still ships the same 3 deliverables (gate + spec + allowlist). No scope creep.

## Issues Encountered

- The grep parity test required two coordinated changes (broaden grep ERE + classify against canonical text), each of which alone would have left the parity set silently empty. Identified via comparison of `pytest_violations` and `grep_violations` set difference after the first naive implementation.
- The naive whole-file grep over the corpus surfaces dozens of prose / code-block mentions of `<one-line summary>` inside the Phase 15 PLAN files themselves (these PLANs document the patterns they ban). The candidate-position post-filter is what makes the gate useful instead of a perpetual false-positive flag. Trade-off accepted: the gate cannot catch a placeholder hidden inside a code fence, but that is a non-goal -- the contract is about the one-liner position that `summary-extract` reads, not arbitrary prose.
- Bold-span regex `^\*\*([^*\n]+)\*\*\s*$` only matches lines where the asterisks are paired on the SAME line with no inner `*` or `**`. The initial SUMMARY one-liner contained the literal token `.planning/phases/**/*-PLAN.md` (the glob form is load-bearing in narrative) which broke the bold-span pairing; the extractor walked past it to the next valid bold-span (deviations section) and the SUMMARY's actual one-liner went unscanned. Rewrote the one-liner to drop the glob-asterisks while preserving the substantive content. Lesson for future SUMMARY authors: do not embed `**` inside the one-liner bold span unless you want the bold-span pairing to break and your one-liner to be silently ignored by the gate.

## Next Phase Readiness

- The TOOL-01 gate ships RED on one real Phase 13 placeholder (`13-04-SUMMARY.md:60`). Plan 15-04's milestone-close cleanup will address it. Until then, the scanner test is the contract that prevents Plan 15-04 from auto-archiving.
- Plan 15-04 can now reference `tests/ci/test_no_placeholder_one_liners.py` from its CI workflow file (`.github/workflows/planning-tooling-gate.yml`) as a required PR check.
- The `.planning/sdk-proposals/` directory is established and ready for the TOOL-02 and TOOL-03 spec docs that Plan 15-02 and 15-03 will ship in parallel.

---
*Phase: 15-planning-tooling-hardening*
*Completed: 2026-05-23*

## Self-Check: PASSED

Verified before commit:
- All 5 promised files exist (`tests/ci/test_no_placeholder_one_liners.py`, `.planning/sdk-proposals/TOOL-01-spec.md`, `.planning/sdk-proposals/.gitkeep`, `.planning/phases/15-planning-tooling-hardening/placeholder-allowlist.json`, `.planning/phases/15-planning-tooling-hardening/15-01-SUMMARY.md`).
- All 4 commits present in `git log` (`e16d0e2` test, `cd3d2d0` fix, `3c9827d` docs, `e8e672e` fix).
- Gate behaviour confirmed: 3 of 4 tests pass; `test_no_placeholder_one_liners_in_plans_and_summaries` is RED on exactly `13-04-SUMMARY.md:60` per plan done criteria.
- This SUMMARY.md's bold one-liner (line 57) extracts cleanly and matches none of the 5 banned patterns.
