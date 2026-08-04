"""BC-03 grep gate — no direct-Bybit references outside ``services/bybit-connector/``.

Phase 13 contract per CONTEXT.md D-05/D-06:

    Make ``services/bybit-connector/`` the sole Bybit-facing service in the
    codebase. Any ``**/*.py`` file outside that directory that imports
    ``pybit``, calls the Bybit mainnet / testnet REST host directly, or opens
    a Bybit WebSocket stream URL directly is a violation. (Literal URLs are
    deliberately not reproduced in this docstring per Pitfall 4 in
    13-RESEARCH.md — the gate would fire on itself.)

TDD discipline (per PLAN frontmatter ``type: tdd``):

    The gate IS the contract. On ``main`` at the moment Plan 13-02 lands, the
    bypass sites still exist — ``test_no_bybit_bypass_in_python_code`` is
    intentionally RED. It flips GREEN incrementally as Wave 1 (BC-02 refactor
    plans) and Wave 2 (BC-04 archival) close out. Do not insert ``xfail``,
    ``skip``, or weaken the assertion: the RED state IS the contract that
    forces future plans to land their refactors.

Dual-form scan (pathlib + subprocess grep) — Phase 8 PREFLIGHT-02 idiom from
``tests/integration/test_preflight_grep_gates.py``:

    1. ``test_no_bybit_bypass_in_python_code`` — pathlib ``rglob`` over
       ``REPO_ROOT/**/*.py`` filtered by EXEMPT_PATHS + EXEMPT_FILES.
       Asserts violations list is empty.

    2. ``test_grep_command_matches_pytest_scan`` — runs ``grep -rE`` from
       REPO_ROOT, post-filters with the same exempt logic (GNU grep's
       ``--exclude-dir`` matches basenames not paths, so post-filtering in
       Python guarantees parity between pytest scan and subprocess grep).
       Asserts the two scan sets are equal regardless of RED/GREEN state —
       defence-in-depth against scan-set drift.

    3. ``test_exempt_paths_exist_or_are_known_future_paths`` — every entry in
       EXEMPT_PATHS either resolves to an existing directory today OR is in
       the documented known-future set (BC-04 archive targets). Prevents
       silent rot of the allowlist.

    4. ``test_smoke_security_test_allowlisted`` — confirms
       ``tests/smoke/test_smoke.py`` is in EXEMPT_FILES. That file's
       ``test_no_testnet_url_in_root_env_example`` enumerates the literal
       ``api-testnet.bybit`` inside a forbidden-token list (line 68); the
       string is a security assertion, not a bypass call, so the file is
       explicitly allowlisted at the file-level.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# REPO_ROOT — ``tests/ci/test_no_bybit_bypass.py`` -> ``parents[2]`` == repo
# root. Resolved ONCE at module import time. Verified to resolve correctly
# under Claude Code worktree paths: ``.claude/worktrees/agent-<id>/tests/ci/
# test_no_bybit_bypass.py`` -> the worktree root, which is the right scan
# target. Per-file ``.resolve()`` calls are deliberately avoided in the hot
# loop (WSL2 filesystem stats are slow — calling resolve() per file pushed
# the gate from ~4s to ~60s+).
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# EXEMPT_PATHS — D-05 allowlist + tape-mode exception + future BC-04 archives.
#
# - services/bybit-connector/        : The connector itself. By D-05 the only
#                                      service authorised to talk to Bybit
#                                      directly.
# - scripts/tape/                    : Tape capture script. Routing it through
#                                      bybit-connector is circular (the
#                                      capture script PRODUCES the tape that
#                                      the connector replays in tape mode);
#                                      explicit exception per PATTERNS.md.
# - _archive_exchanges/              : KNOWN-FUTURE. Will be created by BC-04
#                                      (Plan 08) when the Binance adapter is
#                                      archived. Absent on current main —
#                                      Test 3 tolerates this via the
#                                      KNOWN_FUTURE set below.
# - services/ml-prediction-service/models/_archive_lstm/
#                                    : KNOWN-FUTURE. Documented in CLAUDE.md
#                                      (LSTM archive Apr 2026); does not yet
#                                      exist on this worktree base. Will land
#                                      in a future cleanup commit.
# ---------------------------------------------------------------------------
EXEMPT_PATHS: set[Path] = {
    REPO_ROOT / "services" / "bybit-connector",
    REPO_ROOT / "scripts" / "tape",
    REPO_ROOT / "_archive_exchanges",
    REPO_ROOT / "services" / "ml-prediction-service" / "models" / "_archive_lstm",
}


# ---------------------------------------------------------------------------
# EXEMPT_FILES — file-level allowlist for known-false-positive sites.
#
# tests/smoke/test_smoke.py line 68 contains the literal string
# ``api-testnet.bybit`` inside a forbidden-token list for a security
# assertion ("the root .env.example MUST NOT contain testnet URLs"). The
# token is being asserted-against, not used. File-level allowlist keeps the
# gate's regex simple and free of context-sensitive logic.
#
# tests/integration/test_bybit_connector_tape_preserved.py (BC-07) embeds
# the literal Bybit mainnet and testnet REST hosts in two legitimate roles:
#   (a) respx mock-target strings — the test registers catch-all routes for
#       those hosts and asserts the refactored consumer does NOT call them
#       under tape mode; the host strings are passed to respx, not invoked
#       outbound. (Literals deliberately not reproduced here — Pitfall 4 in
#       13-RESEARCH: the gate would fire on itself, as the legacy version of
#       this comment did pre-amendment.)
#   (b) RED-by-design documentation in the module docstring describing the
#       pre-refactor state of the orderbook handler.
# File-level allowlist preferred over restructuring the test — removing the
# host strings would weaken the BC-07 no-live-call contract.
# ---------------------------------------------------------------------------
EXEMPT_FILES: set[Path] = {
    REPO_ROOT / "tests" / "smoke" / "test_smoke.py",
    REPO_ROOT / "tests" / "integration" / "test_bybit_connector_tape_preserved.py",
}


# Pre-computed string forms for fast prefix-based exemption check.
# REPO_ROOT is already ``.resolve()``-d above, and EXEMPT_PATHS / EXEMPT_FILES
# are constructed from it via ``/`` — so the resulting strings are stable
# without per-file resolve. Trailing ``os.sep`` ensures we match directory
# containment rather than name-prefix collisions
# (e.g. ``scripts/tape_other.py`` must NOT match ``scripts/tape/`` exempt).
_EXEMPT_PREFIXES: tuple[str, ...] = tuple(sorted(str(p) + "/" for p in EXEMPT_PATHS))
_EXEMPT_FILE_STRS: frozenset[str] = frozenset(str(f) for f in EXEMPT_FILES)


# ---------------------------------------------------------------------------
# Skip parts (per-component) — any path containing one of these directory
# components is skipped. ``__pycache__`` is the universal byte-code cache;
# ``.venv``, ``venv``, ``env`` are local virtualenvs (a developer running
# ``pytest`` from a venv directory must not get false positives from
# pip-installed pybit's own ``.py`` files); ``.git`` is the repo metadata.
# ---------------------------------------------------------------------------
SKIP_PARTS: frozenset[str] = frozenset(
    {"__pycache__", ".venv", "venv", "env", ".git", ".tox", "node_modules"}
)


# ---------------------------------------------------------------------------
# BANNED_PATTERNS — per CONTEXT.md D-05. Four banned regexes; any match
# outside EXEMPT_PATHS + EXEMPT_FILES is a BC-03 violation.
# ---------------------------------------------------------------------------
BANNED_PATTERNS: dict[str, re.Pattern[str]] = {
    "pybit_import": re.compile(r"^\s*(from\s+pybit\b|import\s+pybit\b)", re.MULTILINE),
    "mainnet_rest_url": re.compile(r"https?://api\.bybit\.com"),
    "testnet_rest_url": re.compile(r"https?://api-testnet\.bybit\.com"),
    "wss_stream_url": re.compile(r"wss?://stream(?:-testnet)?\.bybit"),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_under(path: Path, root: Path) -> bool:
    """Return True if ``path`` is the same as or inside ``root``.

    Used only by ``test_exempt_paths_exist_or_are_known_future_paths`` and
    diagnostic code paths. The hot-loop scan in ``_scan_py_files`` does NOT
    call this — it uses ``_is_exempt`` with pre-computed string prefixes
    (much faster on WSL2).
    """
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _is_exempt(path: Path) -> bool:
    """A ``.py`` file is exempt iff:
      * any path component is in SKIP_PARTS (__pycache__, .venv, .git, ...),
      * the file's string form is itself in EXEMPT_FILES,
      * OR the file's string form starts with one of the EXEMPT_PATHS
        prefixes (string-prefix check, no per-file ``.resolve()`` syscall).

    Performance: this version runs in ~0s for 1000 files on WSL2 vs ~8s for
    a per-file ``resolve()`` version. ``REPO_ROOT`` is resolved once at
    module import; ``rglob`` returns absolute paths derived from it, so
    string-prefix comparison is reliable.
    """
    if any(part in SKIP_PARTS for part in path.parts):
        return True
    spath = str(path)
    if spath in _EXEMPT_FILE_STRS:
        return True
    return spath.startswith(_EXEMPT_PREFIXES)


def _scan_py_files() -> list[tuple[str, int, str, str]]:
    """Walk REPO_ROOT for ``*.py`` files outside the exempt set and return a
    list of ``(relative_path, line_no, kind, snippet)`` for every banned
    pattern hit. Sorted for stable output across runs.
    """
    violations: list[tuple[str, int, str, str]] = []
    for py in REPO_ROOT.rglob("*.py"):
        if _is_exempt(py):
            continue
        try:
            text = py.read_text(errors="ignore")
        except OSError:
            continue
        lines = text.splitlines()
        for kind, pattern in BANNED_PATTERNS.items():
            for m in pattern.finditer(text):
                line_no = text[: m.start()].count("\n") + 1
                snippet = (
                    lines[line_no - 1].strip() if 1 <= line_no <= len(lines) else ""
                )
                violations.append(
                    (str(py.relative_to(REPO_ROOT)), line_no, kind, snippet)
                )
    return sorted(violations)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_bybit_bypass_in_python_code() -> None:
    """BC-03 contract: no direct-Bybit references in ``**/*.py`` outside
    ``services/bybit-connector/`` (and the documented exempt set).

    Expected behaviour:
        * Pre-Wave-1 (today, on main): FAILS. The Initial Audit at
          ROADMAP.md §"Phase 13" enumerates ~17 bypass sites. This RED state
          IS the contract that forces Wave 1 (BC-02 refactor plans) to close
          them out.
        * Post-Wave-2 (BC-04 archival complete): PASSES. The gate locks the
          centralization invariant going forward.

    Do not insert ``pytest.xfail``, ``pytest.skip``, or weaken the
    assertion. The RED state IS the contract.
    """
    violations = _scan_py_files()
    assert violations == [], (
        "BC-03 violation — direct-Bybit references found outside "
        "services/bybit-connector/:\n  "
        + "\n  ".join(f"{p}:{ln}: [{k}] {snippet}" for p, ln, k, snippet in violations)
    )


def test_grep_command_matches_pytest_scan() -> None:
    """Defence-in-depth — the subprocess ``grep`` form must agree with the
    pathlib scan.

    Rationale:

    * GNU grep's ``--exclude-dir=PAT`` matches the directory basename, not a
      path-segment glob. ``--exclude-dir=services/bybit-connector`` excludes
      nothing (no directory is literally named ``services/bybit-connector``).
      We therefore post-filter the grep stdout in Python using the same
      ``_is_exempt`` helper — guaranteed parity by construction.
    * The two scans must agree regardless of RED/GREEN state: on RED main
      both sets are non-empty and equal; once Wave 1+2 land both are empty
      and equal. Set-equality (not "stdout is empty") is the right shape.
    """
    pytest_violations = {(p, ln, k) for p, ln, k, _ in _scan_py_files()}

    cmd = [
        "grep",
        "-rEn",
        "--include=*.py",
        # Combined alternation of the four banned patterns. The ``-n`` flag
        # prefixes each match line with its line number for stable parsing.
        r"(^[[:space:]]*(from[[:space:]]+pybit\b|import[[:space:]]+pybit\b))"
        r"|(https?://api\.bybit\.com)"
        r"|(https?://api-testnet\.bybit\.com)"
        r"|(wss?://stream(-testnet)?\.bybit)",
        str(REPO_ROOT),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    # grep exits 1 when there are no matches; that is success for the
    # GREEN state but not an error in either state.
    if result.returncode not in (0, 1):
        raise AssertionError(
            f"grep subprocess failed (rc={result.returncode}): {result.stderr[:500]}"
        )

    grep_violations: set[tuple[str, int, str]] = set()
    for line in result.stdout.splitlines():
        # grep -rn output shape: ``<absolute-path>:<line_no>:<match-line>``
        # On Windows-style absolute paths the second colon is the separator
        # we want; on POSIX it's the first. Split exactly twice from the
        # left because the match-line itself can contain colons.
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        abs_path, line_no_str, match_line = parts
        try:
            line_no = int(line_no_str)
        except ValueError:
            continue
        try:
            py_path = Path(abs_path)
            rel_path = py_path.resolve().relative_to(REPO_ROOT.resolve())
        except (ValueError, OSError):
            continue
        if _is_exempt(py_path):
            continue
        # Classify by the same banned-pattern logic. Walk the four patterns
        # and emit one entry per kind per line (mirrors the pathlib scan).
        for kind, pattern in BANNED_PATTERNS.items():
            if pattern.search(match_line):
                grep_violations.add((str(rel_path), line_no, kind))

    assert pytest_violations == grep_violations, (
        "BC-03 scan-set drift between pytest and subprocess grep:\n"
        f"  only in pytest scan: "
        f"{sorted(pytest_violations - grep_violations)}\n"
        f"  only in grep stdout: "
        f"{sorted(grep_violations - pytest_violations)}"
    )


def test_exempt_paths_exist_or_are_known_future_paths() -> None:
    """Every EXEMPT_PATHS entry either exists today or is documented as a
    known-future archive target (BC-04 Wave 2 lands them).

    Prevents silent rot of the allowlist: if a future refactor renames or
    deletes ``services/bybit-connector/``, this test trips and forces the
    gate to be re-aligned.
    """
    known_future: set[Path] = {
        REPO_ROOT / "_archive_exchanges",
        REPO_ROOT / "services" / "ml-prediction-service" / "models" / "_archive_lstm",
    }
    missing: list[Path] = [
        p for p in EXEMPT_PATHS if not p.exists() and p not in known_future
    ]
    assert not missing, (
        "EXEMPT_PATHS rot — entries neither exist nor are documented as "
        "known-future archive targets:\n  " + "\n  ".join(str(m) for m in missing)
    )


def test_smoke_security_test_allowlisted() -> None:
    """The forbidden-token list in ``tests/smoke/test_smoke.py`` line 68
    contains the literal ``api-testnet.bybit`` inside a security assertion
    that the project's ``.env.example`` does NOT contain testnet URLs. The
    string is being asserted-against, not used as a bypass call, so the file
    is explicitly allowlisted at the file-level via EXEMPT_FILES.
    """
    smoke_test = REPO_ROOT / "tests" / "smoke" / "test_smoke.py"
    assert smoke_test in EXEMPT_FILES, (
        "tests/smoke/test_smoke.py must be in EXEMPT_FILES — its "
        "forbidden-token list contains the literal 'api-testnet.bybit' for "
        "a security assertion (it asserts the token is NOT in "
        ".env.example), not as a bypass call. Without the allowlist, the "
        "BC-03 gate fires a false positive on the security test itself."
    )


def test_tape_preserved_test_allowlisted() -> None:
    """``tests/integration/test_bybit_connector_tape_preserved.py`` (BC-07)
    embeds the literal Bybit mainnet and testnet REST host strings in two
    legitimate roles (literals deliberately not reproduced in this docstring
    per Pitfall 4 in 13-RESEARCH — the gate would fire on itself):

      (a) respx mock-target strings — the BC-07 contract registers those
          hosts as catch-all routes that MUST NOT be called by the refactored
          consumer; the host strings are passed to respx, not invoked outbound.
      (b) RED-by-design documentation in the module docstring describing the
          pre-refactor state of the orderbook handler.

    File-level allowlist preferred over restructuring the test — the host
    strings are load-bearing for the BC-07 contract (their absence would
    weaken the no-live-call assertion). Without the allowlist, the BC-03
    gate fires four false positives on the BC-07 contract test itself.
    """
    tape_preserved_test = (
        REPO_ROOT / "tests" / "integration" / "test_bybit_connector_tape_preserved.py"
    )
    assert tape_preserved_test in EXEMPT_FILES, (
        "tests/integration/test_bybit_connector_tape_preserved.py must be in "
        "EXEMPT_FILES — its respx mock-target URLs and RED-by-design docstring "
        "reference the literal Bybit hosts as the URLs the refactored consumer "
        "MUST NOT call under tape mode. Without the allowlist, the BC-03 gate "
        "fires four false positives on the BC-07 contract test itself."
    )
