#!/bin/bash
# ============================================================================
# Test harness for scripts/iter-fix-check-diff.sh (Phase 2 Plan 02-06, INFRA-04 / D-12)
# Purpose: prove the anti-mock refusal regex set rejects each banned pattern
#          inside `tests/`, and allows clean diffs and non-test changes.
# Inline PASS/FAIL fallback (bats not installed in this repo).
# Usage: bash tests/scripts/test_iter_fix.sh
# Exit: 0 if all cases pass, 1 if any case fails.
# ============================================================================

set -u  # NOT -e — we need to inspect failures and continue

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CHECK_DIFF="$REPO_ROOT/scripts/iter-fix-check-diff.sh"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

PASS=0
FAIL=0
FAILURES=()

# ---- Test helpers --------------------------------------------------------

# run_case <name> <expected_exit> <expected_substring_in_output|""> <diff>
# - Pipes <diff> into $CHECK_DIFF
# - Asserts exit code == <expected_exit>
# - If <expected_substring_in_output> non-empty, asserts output contains it
run_case() {
    local name="$1"
    local expected_exit="$2"
    local expected_substr="$3"
    local diff_input="$4"

    local actual_output actual_exit
    # Capture stdout+stderr and exit code; do NOT let pipefail kill the test
    actual_output=$(printf '%s' "$diff_input" | bash "$CHECK_DIFF" 2>&1)
    actual_exit=$?

    local err=""
    if [ "$actual_exit" != "$expected_exit" ]; then
        err+="\n    exit: expected=$expected_exit actual=$actual_exit"
    fi
    if [ -n "$expected_substr" ] && ! echo "$actual_output" | grep -qF -- "$expected_substr"; then
        err+="\n    stdout: missing substring '$expected_substr'\n    full output:\n$actual_output"
    fi

    if [ -z "$err" ]; then
        echo -e "  ${GREEN}PASS${NC}  $name"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC}  $name${err}"
        FAIL=$((FAIL + 1))
        FAILURES+=("$name")
    fi
}

# ---- Pre-flight ----------------------------------------------------------

echo -e "${YELLOW}[iter-fix-check-diff.sh test harness]${NC}"
echo -e "  CHECK_DIFF=$CHECK_DIFF"

if [ ! -f "$CHECK_DIFF" ]; then
    echo -e "${RED}MISSING: $CHECK_DIFF does not exist${NC}"
    echo -e "${RED}All 8 cases will fail (RED phase — expected if running before GREEN)${NC}"
fi

# ---- Test fixtures (heredoc'd as plain strings to avoid in-source banned-pattern false positives) ----
# Each test fixture is a small unified diff. The key marker for the script is `+++ b/<path>`
# to identify file scope, and `^+` lines for additions.
#
# NB: file paths inside fixtures are placeholder paths (e.g., tests/foo.py) — these are
# passed to the script as bytes in the diff, never read from disk.
#
# Banned tokens are assembled from variable parts where possible, but at the end of
# the day the test fixtures must contain the literal banned strings — that is the
# whole point of the test.

UNITTEST_MOCK="unittest"".""mock"   # pieces to dodge any future grep on this file itself; reassembled at runtime
MOCKER_PATCH="mocker"".""patch"
PYTEST_SKIP="pytest"".""skip"
PYTEST_XFAIL="pytest"".""mark.xfail"

# Test 1: +import unittest.mock inside tests/ → exit 1, output contains "unittest.mock"
DIFF_T1="--- a/tests/foo.py
+++ b/tests/foo.py
@@ -1 +1 @@
+import ${UNITTEST_MOCK}
"

# Test 2: +    mocker.patch("foo") inside tests/ → exit 1, output contains "mocker.patch"
DIFF_T2="--- a/tests/foo.py
+++ b/tests/foo.py
@@ -1 +1 @@
+    ${MOCKER_PATCH}(\"foo\")
"

# Test 3: +    pytest.skip("services down") inside tests/ → exit 1, output contains "pytest.skip"
DIFF_T3="--- a/tests/foo.py
+++ b/tests/foo.py
@@ -1 +1 @@
+    ${PYTEST_SKIP}(\"services down\")
"

# Test 4: +@pytest.mark.xfail(reason="known") inside tests/ → exit 1, output contains "pytest.mark.xfail"
DIFF_T4="--- a/tests/foo.py
+++ b/tests/foo.py
@@ -1 +1 @@
+@${PYTEST_XFAIL}(reason=\"known\")
"

# Test 5: paired -/+ assert lowering threshold inside tests/ → exit 1, output contains "threshold"
DIFF_T5="--- a/tests/foo.py
+++ b/tests/foo.py
@@ -10,2 +10,2 @@
-    assert elapsed < 60.0
+    assert elapsed < 120.0
"

# Test 5b (WR-01): paired -/+ assert lowering on `>` threshold (e.g., win_rate
# minimum was 0.5, relaxed to 0.3) → exit 1. The original regex only caught
# `<`/`<=`; this case verifies the inverse-comparison branch.
DIFF_T5B="--- a/tests/foo.py
+++ b/tests/foo.py
@@ -10,2 +10,2 @@
-    assert win_rate > 0.5
+    assert win_rate > 0.3
"

# Test 6: clean diff inside tests/ (no banned patterns) → exit 0, silent
DIFF_T6="--- a/tests/foo.py
+++ b/tests/foo.py
@@ -1 +1 @@
+    assert x == 5
"

# Test 6b: legitimate raise on `>` threshold (e.g., win_rate minimum tightened
# from 0.5 to 0.6) → exit 0. Confirms direction-aware logic does not
# false-positive on tightening.
DIFF_T6B="--- a/tests/foo.py
+++ b/tests/foo.py
@@ -10,2 +10,2 @@
-    assert win_rate > 0.5
+    assert win_rate > 0.6
"

# Test 7: ADDS unittest.mock to non-test file → exit 0 (rule scoped to tests/)
DIFF_T7="--- a/services/foo/main.py
+++ b/services/foo/main.py
@@ -1 +1 @@
+import ${UNITTEST_MOCK}
"

# Test 8: refusal message includes offending file path (cited from `+++ b/<path>` line)
DIFF_T8="--- a/tests/integration/test_specific.py
+++ b/tests/integration/test_specific.py
@@ -1 +1 @@
+    ${PYTEST_SKIP}(\"services down\")
"

# ---- Run cases -----------------------------------------------------------

echo -e "${YELLOW}--- Refusal cases (banned patterns inside tests/) ---${NC}"
run_case "T1: +import unittest.mock in tests/ -> refused" 1 "unittest.mock" "$DIFF_T1"
run_case "T2: +mocker.patch in tests/ -> refused"          1 "mocker.patch"   "$DIFF_T2"
run_case "T3: +pytest.skip in tests/ -> refused"           1 "pytest.skip"    "$DIFF_T3"
run_case "T4: +pytest.mark.xfail in tests/ -> refused"     1 "pytest.mark.xfail" "$DIFF_T4"
run_case "T5: paired assert lowering in tests/ -> refused" 1 "threshold"      "$DIFF_T5"
run_case "T5b: paired assert > lowering in tests/ -> refused" 1 "threshold"   "$DIFF_T5B"

echo -e "${YELLOW}--- Allow cases ---${NC}"
run_case "T6: clean diff in tests/ -> allowed"             0 ""                "$DIFF_T6"
run_case "T6b: paired assert > tightening in tests/ -> allowed" 0 ""          "$DIFF_T6B"
run_case "T7: unittest.mock in services/ (not tests/) -> allowed" 0 ""        "$DIFF_T7"

echo -e "${YELLOW}--- File-path citation case ---${NC}"
run_case "T8: refusal output cites offending file path"    1 "tests/integration/test_specific.py" "$DIFF_T8"

# ---- Report --------------------------------------------------------------

echo
echo -e "${YELLOW}========================================${NC}"
echo -e "  Passed: ${GREEN}$PASS${NC}"
echo -e "  Failed: ${RED}$FAIL${NC}"
echo -e "${YELLOW}========================================${NC}"

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}FAILED:${NC}"
    for f in "${FAILURES[@]}"; do
        echo "  - $f"
    done
    exit 1
fi
exit 0
