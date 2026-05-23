"""TOOL-01 grep gate -- reject placeholder one-liners in planning artifacts.

Phase 15 contract per REQUIREMENTS.md TOOL-01 line 39 and 15-CONTEXT.md
Specifics line 84:

    The summary-extract / plan.validate verb feeds milestone-close auto-text.
    When a SUMMARY.md or PLAN.md ships with a placeholder one-liner --
    ``Rule N`` / ``Task N`` / empty / template-token -- the milestone close
    silently auto-generates garbage MILESTONES.md entries downstream. The
    five banned patterns below catch every shape observed in v1.0 + v1.1
    retro. (Pattern source strings are deliberately stored in raw-regex
    constructors so this docstring does not trip its own gate.)

Scope:

    Walks every ``.planning/phases/**/*-PLAN.md`` and ``*-SUMMARY.md`` in
    the repo. Extracts candidate one-liner positions per the
    ``extractOneLinerFromBody`` contract from the host SDK at
    ``~/.claude/get-shit-done/bin/lib/core.cjs`` (lines 200-230):

      * the value of any frontmatter line matching ``^one-liner:``;
      * the first bold-span line ``**...**`` after the first markdown
        heading (``# ...``);
      * the first non-empty body line after that same heading (used only
        when no bold span is found).

    Banned patterns run against extracted candidates only -- prose and
    code-block mentions of the banned shapes inside the body are
    deliberately out of scope (the SDK validator and the milestone-close
    auto-text both consume the one-liner position, not arbitrary body
    text).

TDD discipline:

    The two scanner tests are RED iff the existing planning corpus
    contains placeholder one-liners; that RED state IS the contract and
    forces the milestone-close cleanup in Plan 15-04. Do not insert
    ``pytest.xfail``, ``pytest.skip``, or weaken assertions.

Dual-form scan (pathlib + subprocess grep) -- Phase 13 BC-03 idiom:

    1. ``test_no_placeholder_one_liners_in_plans_and_summaries`` --
       pathlib ``rglob`` over ``REPO_ROOT/.planning/phases/**/*-PLAN.md``
       and ``*-SUMMARY.md``. Asserts the violations list is empty after
       allowlist filtering.
    2. ``test_grep_command_matches_pytest_scan`` -- runs ``grep -rEn``
       over the same tree, then post-filters with the same candidate
       extractor + ``_is_exempt`` helper. Asserts set equality with the
       pytest scan regardless of RED/GREEN state.
    3. ``test_exempt_paths_exist_or_are_known_future_paths`` -- prevents
       silent rot of the EXEMPT_PATHS allowlist (currently empty).
    4. ``test_allowlist_json_is_a_list`` -- the sibling allowlist JSON
       parses as a list (may be empty). Catches a broken file at source.

The companion SDK-verb spec lives at
``.planning/sdk-proposals/TOOL-01-spec.md`` and references the same
banned-pattern names so the operator-side port stays in sync.
"""

from __future__ import annotations

import re
import subprocess
import json
from pathlib import Path


# ---------------------------------------------------------------------------
# REPO_ROOT -- ``tests/ci/test_no_placeholder_one_liners.py`` -> ``parents[2]``
# == repo root. Resolved ONCE at module import (per BC-03 perf comment: WSL2
# filesystem stats are slow, and per-file ``.resolve()`` calls inflate the
# scan from ~4s to ~60s+).
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# EXEMPT_PATHS / EXEMPT_FILES -- TOOL-01 ships with empty slots.
#
# Placeholder one-liners are never legitimate inside
# ``.planning/phases/**/*-PLAN.md`` or ``*-SUMMARY.md``: the whole point of
# the one-liner is that ``summary-extract`` reads it as the milestone-close
# narrative. The allowlist slot is preserved per BC-03 + Phase 14 idiom
# for late-discovered false positives, but for TOOL-01 the canonical answer
# to a flagged line is "fix the one-liner", not "allowlist the bad string".
#
# Late false-positives flow through ``placeholder-allowlist.json`` instead
# (see ALLOWLIST_PATH below) which is keyed on the literal offending string,
# not a path -- finer-grained than EXEMPT_PATHS.
# ---------------------------------------------------------------------------
EXEMPT_PATHS: set[Path] = set()
EXEMPT_FILES: set[Path] = set()


# Pre-computed string forms for fast prefix-based exemption (BC-03 perf
# discipline). Trailing ``/`` ensures we match directory containment rather
# than name-prefix collisions (e.g. ``.planning/phases-archive/`` must NOT
# match ``.planning/phases/`` exempt). Empty today; ready for late-added
# entries.
_EXEMPT_PREFIXES: tuple[str, ...] = tuple(sorted(str(p) + "/" for p in EXEMPT_PATHS))
_EXEMPT_FILE_STRS: frozenset[str] = frozenset(str(f) for f in EXEMPT_FILES)


# Per-component skip set -- universal byte-code / venv / vcs / package noise.
SKIP_PARTS: frozenset[str] = frozenset(
    {"__pycache__", ".venv", "venv", "env", ".git", ".tox", "node_modules"}
)


# Late false-positive handling -- mirrors the Phase 14 _load_allowlist shape
# in ``tests/integration/test_no_mobile_hidden_data.py:77-103``, keyed on the
# literal offending ``one_liner`` string (not ``data_testid``).
ALLOWLIST_PATH = (
    REPO_ROOT
    / ".planning"
    / "phases"
    / "15-planning-tooling-hardening"
    / "placeholder-allowlist.json"
)


# ---------------------------------------------------------------------------
# BANNED_PATTERNS -- per 15-CONTEXT.md Specifics line 84.
#
# Five named patterns; the names are the SDK-verb contract surface (the
# companion ``.planning/sdk-proposals/TOOL-01-spec.md`` references these
# exact keys, and so does the eventual ``plan.validate`` verb output JSON).
# ---------------------------------------------------------------------------
BANNED_PATTERNS: dict[str, re.Pattern[str]] = {
    "placeholder_rule_n": re.compile(r"^Rule\s+\d", re.MULTILINE),
    "placeholder_task_n": re.compile(r"^Task\s+\d", re.MULTILINE),
    "placeholder_one_liner_empty": re.compile(r"^one-liner:\s*$", re.MULTILINE),
    "placeholder_template_token": re.compile(r"<one-line summary>"),
    "placeholder_empty_string": re.compile(r'^one-liner:\s*""\s*$', re.MULTILINE),
}


# ---------------------------------------------------------------------------
# Markdown candidate-position regexes (extractor inputs)
# ---------------------------------------------------------------------------

# Match a level-1 markdown heading line: ``# Title``. Requires at least one
# whitespace char after ``#`` and at least one non-space char after that
# (so ``# ---`` separator lines don't qualify as headings).
_MD_HEADING_RE = re.compile(r"^#\s+\S", re.MULTILINE)

# Match a frontmatter one-liner key line: ``one-liner: <value>`` or
# ``one-liner:`` (empty). Captures the full line including value.
_ONE_LINER_FRONTMATTER_RE = re.compile(r"^one-liner:.*$", re.MULTILINE)

# Match a bold-span only line: ``**Some prose.**`` with no nested asterisks
# inside the span (the host SDK's extractOneLinerFromBody reads only the
# outer bold span, per core.cjs:200-230).
_BOLD_SPAN_RE = re.compile(r"^\*\*([^*\n]+)\*\*\s*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_exempt(path: Path) -> bool:
    """Mirror of BC-03 ``_is_exempt`` -- string-prefix check, no per-file
    ``.resolve()`` syscall.
    """
    if any(part in SKIP_PARTS for part in path.parts):
        return True
    spath = str(path)
    if spath in _EXEMPT_FILE_STRS:
        return True
    return spath.startswith(_EXEMPT_PREFIXES)


def _load_allowlist() -> set[str]:
    """Load the placeholder allowlist as a set of literal offending strings.

    Mirrors ``tests/integration/test_no_mobile_hidden_data.py::_load_allowlist``
    discipline (Phase 14 WR-04 graceful-degrade pattern):

      * Missing file -> empty set.
      * OSError / JSONDecodeError -> empty set.
      * Non-list root -> empty set.
      * Per-entry: drops anything missing a non-empty ``reason`` field --
        prevents drive-by allowlisting without justification.

    For TOOL-01 the entry key is ``one_liner`` (the literal offending
    candidate string).
    """
    if not ALLOWLIST_PATH.exists():
        return set()
    try:
        entries = json.loads(ALLOWLIST_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(entries, list):
        return set()
    return {
        e["one_liner"]
        for e in entries
        if isinstance(e, dict) and e.get("one_liner") and e.get("reason")
    }


def _extract_candidate_one_liners(text: str) -> list[tuple[int, str]]:
    """Return (line_no, candidate_text) pairs at candidate one-liner positions.

    Candidate positions per the host SDK's extractOneLinerFromBody contract
    (~/.claude/get-shit-done/bin/lib/core.cjs:200-230) plus the frontmatter
    one-liner key common to GSD plan template:

      1. Every frontmatter line matching ``^one-liner:`` (the full line is
         the candidate so the banned-pattern regexes that anchor on
         ``^one-liner:`` can fire).
      2. The first bold-span line ``**...**`` after the first ``# `` heading,
         if any (the span's inner text is the candidate -- the SDK strips
         the asterisks before classifying).
      3. The first non-empty, non-bold body line after the first ``# ``
         heading, ONLY if no bold-span was found between the heading and
         that line (the SDK's fallback path when no bold span is present).

    Tie-break rule (per ``extractOneLinerFromBody``): a bold span takes
    precedence over the plain-body-line fallback. If both would qualify,
    only the bold-span position is reported -- guarantees a single
    deterministic line_no per (file, position-kind).

    Line numbers are 1-indexed.
    """
    candidates: list[tuple[int, str]] = []

    # 1. Frontmatter one-liner lines (anywhere in file -- the GSD plan
    # template lives at the top of the file but the regex is intentionally
    # position-agnostic so a stray ``one-liner:`` lower in the doc would
    # still be caught).
    for m in _ONE_LINER_FRONTMATTER_RE.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        candidates.append((line_no, m.group(0)))

    # 2. + 3. First bold-span OR first body line after first ``# `` heading.
    #
    # Strip YAML frontmatter before searching for the body heading. The
    # frontmatter ``one-liner:`` rule above already scanned the whole text;
    # here we want only the body's first ``# `` heading, which lives after
    # the closing ``---`` of the frontmatter block. YAML uses ``#`` for
    # comments (e.g. the GSD summary template uses ``# Dependency graph``,
    # ``# Tech tracking``, ``# Metrics`` as section dividers inside the
    # frontmatter); these look identical to markdown headings to a naive
    # regex and would otherwise hijack the candidate-position search.
    body_search_start = 0
    if text.startswith("---\n") or text.startswith("---\r\n"):
        # Find the closing ``---`` on its own line; allow trailing
        # whitespace defensively.
        closer = re.search(r"^---\s*$", text[4:], re.MULTILINE)
        if closer is not None:
            # ``closer.end()`` is relative to the slice starting at offset 4.
            post_closer = 4 + closer.end()
            next_nl = text.find("\n", post_closer)
            if next_nl != -1:
                body_search_start = next_nl + 1

    heading_match = _MD_HEADING_RE.search(text, body_search_start)
    if heading_match is None:
        return sorted(candidates)

    # Skip to the start of the line AFTER the heading. ``heading_match.end()``
    # lands at the first non-space char of the heading text itself; we want
    # everything past the newline that terminates the heading line, so the
    # body scan starts on the next physical line and never re-reads the
    # heading text.
    post_heading_nl = text.find("\n", heading_match.end())
    if post_heading_nl == -1:
        # Heading is the final line of the file -- nothing to scan.
        return sorted(candidates)
    body_start = post_heading_nl + 1
    body = text[body_start:]

    bold_match = _BOLD_SPAN_RE.search(body)
    if bold_match is not None:
        # Bold-span path -- the candidate is the inner text (sans asterisks)
        # per extractOneLinerFromBody.
        abs_start = body_start + bold_match.start()
        line_no = text[:abs_start].count("\n") + 1
        candidates.append((line_no, bold_match.group(1).strip()))
    else:
        # Plain-body fallback -- first non-empty line after the heading.
        for raw_line in body.splitlines():
            if raw_line.strip() == "":
                continue
            # Locate the absolute line_no for this raw_line.
            abs_idx = text.find(raw_line, body_start)
            if abs_idx == -1:
                # Should not happen, but defensive: fall through.
                break
            line_no = text[:abs_idx].count("\n") + 1
            candidates.append((line_no, raw_line.strip()))
            break

    return sorted(candidates)


def _planning_files() -> list[Path]:
    """All ``*-PLAN.md`` and ``*-SUMMARY.md`` under
    ``REPO_ROOT/.planning/phases/`` -- the corpus the gate scans.
    """
    root = REPO_ROOT / ".planning" / "phases"
    if not root.exists():
        return []
    plan_files = list(root.rglob("*-PLAN.md"))
    summary_files = list(root.rglob("*-SUMMARY.md"))
    out: list[Path] = []
    for f in plan_files + summary_files:
        # Defense-in-depth: skip ``_archive_*`` dirs if any planning system
        # introduces them later. None present today under .planning/phases/.
        if any(part.startswith("_archive_") for part in f.parts):
            continue
        out.append(f)
    return out


def _scan_planning_files() -> list[tuple[str, int, str, str]]:
    """Return ``(rel_path, line_no, pattern_name, candidate_text)`` tuples
    for every banned-pattern hit across candidate one-liner positions in
    the planning corpus.

    Does NOT apply the allowlist -- callers do that. (Keeps the function
    composable for the dual-form grep parity test which compares the
    pre-allowlist set.)

    Sorted for stable output.
    """
    violations: list[tuple[str, int, str, str]] = []
    for path in _planning_files():
        if _is_exempt(path):
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        candidates = _extract_candidate_one_liners(text)
        for line_no, candidate_text in candidates:
            for pattern_name, pattern in BANNED_PATTERNS.items():
                if pattern.search(candidate_text):
                    violations.append(
                        (
                            str(path.relative_to(REPO_ROOT)),
                            line_no,
                            pattern_name,
                            candidate_text.strip(),
                        )
                    )
    return sorted(violations)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_placeholder_one_liners_in_plans_and_summaries() -> None:
    """TOOL-01 contract: no placeholder one-liners in
    ``.planning/phases/**/*-PLAN.md`` or ``*-SUMMARY.md``.

    Expected behaviour:
        * If the corpus is clean at runtime: PASSES.
        * If the corpus has any placeholder one-liner shape (per the 5
          patterns in BANNED_PATTERNS): FAILS. That RED state IS the
          contract and forces SUMMARY.md / PLAN.md cleanup before the
          milestone-close step in Plan 15-04.

    Late false-positive escape hatch: add an entry to
    ``placeholder-allowlist.json`` with a non-empty ``reason`` field.
    Entries without ``reason`` are silently dropped.

    Do not insert ``pytest.xfail`` / ``pytest.skip`` / weaken the
    assertion. The RED state IS the contract.
    """
    allowlist = _load_allowlist()
    raw_violations = _scan_planning_files()
    violations = [
        (p, ln, k, snippet)
        for (p, ln, k, snippet) in raw_violations
        if snippet not in allowlist
    ]
    assert violations == [], (
        "TOOL-01 violation -- placeholder one-liner detected in planning "
        "artifacts:\n  "
        + "\n  ".join(f"{p}:{ln}: [{k}] {snippet}" for p, ln, k, snippet in violations)
    )


def test_grep_command_matches_pytest_scan() -> None:
    """Defence-in-depth -- subprocess ``grep`` form must agree with the
    pathlib scan, candidate-position-filtered.

    Critical design note: a naive whole-line ``grep -E`` over the corpus
    would flag every prose / code-block / regex-source mention of the
    banned shapes (these PLAN.md files themselves contain ``<one-line
    summary>`` inside backticks in the scaffolding instructions, for
    example). The pytest scan only flags banned shapes at candidate
    one-liner positions. To compare apples to apples, post-filter the
    grep stdout by the same candidate-position set per file.

    Both scans must agree regardless of RED/GREEN state; the
    pre-allowlist set is used so the parity check is not muddled by the
    operator-side allowlist.
    """
    pytest_violations = {(p, ln, k) for p, ln, k, _ in _scan_planning_files()}

    cmd = [
        "grep",
        "-rEn",
        "--include=*-PLAN.md",
        "--include=*-SUMMARY.md",
        # Combined ERE alternation of the 5 patterns. GNU grep ERE does
        # NOT support ``\s`` / ``\d`` -- use POSIX bracket classes instead.
        # The angle brackets in ``<one-line summary>`` have no special
        # meaning in ERE so the literal travels through unmodified.
        #
        # The Rule N / Task N alternatives allow zero or two leading
        # asterisks so the grep emits bold-span-wrapped candidate lines
        # like ``**Task 1 -- title**``. The pytest scan extracts the inner
        # text (sans asterisks) via _extract_candidate_one_liners and
        # classifies against THAT, so the parity test below classifies
        # grep hits against the same canonical extractor output to keep
        # the two scans aligned. Inside ``[...]`` the ``*`` is literal --
        # no shell-quoting headache.
        r"(^[*]{0,2}Rule[[:space:]]+[0-9])|(^[*]{0,2}Task[[:space:]]+[0-9])|"
        r"(^one-liner:[[:space:]]*$)|(<one-line summary>)|"
        r'(^one-liner:[[:space:]]*""[[:space:]]*$)',
        str(REPO_ROOT / ".planning" / "phases"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    # grep exit code 1 = "no matches" = success in the GREEN state.
    if result.returncode not in (0, 1):
        raise AssertionError(
            f"grep subprocess failed (rc={result.returncode}): {result.stderr[:500]}"
        )

    grep_violations: set[tuple[str, int, str]] = set()
    # Per-file candidate cache mapping line_no -> canonical candidate text
    # (the inner span text for bold-span candidates, the full line for
    # frontmatter / fallback candidates). Classification runs against this
    # canonical text, NOT the raw grep match_line, so the same banned
    # regexes that the pytest scan applies fire here too -- otherwise the
    # bold-wrapped ``**Task 1 ...**`` grep line would not match the
    # ``^Task\s+\d`` regex which anchors on raw line start.
    candidate_text_cache: dict[Path, dict[int, str]] = {}

    for line in result.stdout.splitlines():
        # grep -rn shape: ``<absolute-path>:<line_no>:<match-line>``.
        # Split at most twice so colons inside the match line are
        # preserved in the third field.
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        abs_path, line_no_str, _match_line = parts
        try:
            line_no = int(line_no_str)
        except ValueError:
            continue
        try:
            md_path = Path(abs_path)
            rel_path = md_path.resolve().relative_to(REPO_ROOT.resolve())
        except (ValueError, OSError):
            continue
        if _is_exempt(md_path):
            continue
        # Build / re-use the candidate map for this file.
        if md_path not in candidate_text_cache:
            try:
                file_text = md_path.read_text(errors="ignore")
            except OSError:
                candidate_text_cache[md_path] = {}
                continue
            candidate_text_cache[md_path] = {
                ln: text for ln, text in _extract_candidate_one_liners(file_text)
            }
        if line_no not in candidate_text_cache[md_path]:
            # grep flagged a body / code-block line that is NOT a
            # candidate one-liner position -- out of scope for the gate.
            continue
        canonical = candidate_text_cache[md_path][line_no]
        # Classify the grep hit by the same five banned-pattern regexes,
        # applied to the canonical candidate text (mirrors _scan_planning_files).
        for pattern_name, pattern in BANNED_PATTERNS.items():
            if pattern.search(canonical):
                grep_violations.add((str(rel_path), line_no, pattern_name))

    assert pytest_violations == grep_violations, (
        "TOOL-01 scan-set drift between pytest and subprocess grep "
        "(after candidate-position post-filter):\n"
        f"  only in pytest scan: {sorted(pytest_violations - grep_violations)}\n"
        f"  only in grep stdout: {sorted(grep_violations - pytest_violations)}"
    )


def test_exempt_paths_exist_or_are_known_future_paths() -> None:
    """Every EXEMPT_PATHS entry either exists today or is in a documented
    known-future set. Trivially passes while EXEMPT_PATHS is empty (the
    common case for TOOL-01), but the test slot stays so the structure
    matches BC-03 and the gate stays hygienic if entries are added later.
    """
    known_future: set[Path] = set()
    missing: list[Path] = [
        p for p in EXEMPT_PATHS if not p.exists() and p not in known_future
    ]
    assert not missing, (
        "EXEMPT_PATHS rot -- entries neither exist nor are documented as "
        "known-future paths:\n  " + "\n  ".join(str(m) for m in missing)
    )


def test_allowlist_json_is_a_list() -> None:
    """``placeholder-allowlist.json`` parses as JSON and its top-level
    value is a list (may be empty). Catches a broken file at source --
    ``_load_allowlist`` silently degrades to an empty set on malformed
    JSON / non-list root, which is the right runtime behaviour but
    would mask a genuine corruption from operators eyeballing CI logs.
    """
    assert ALLOWLIST_PATH.exists(), (
        f"placeholder-allowlist.json not found at {ALLOWLIST_PATH}"
    )
    try:
        parsed = json.loads(ALLOWLIST_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"placeholder-allowlist.json is not valid JSON: {exc}"
        ) from exc
    assert isinstance(parsed, list), (
        f"placeholder-allowlist.json top-level must be a list, got "
        f"{type(parsed).__name__}"
    )
