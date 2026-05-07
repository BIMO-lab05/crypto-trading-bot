#!/bin/bash
# ============================================================================
# iter-fix-check-diff.sh — D-12 anti-mock refusal logic (Phase 2 Plan 02-06).
# Reusable from scripts/iter-fix.sh AND .github/workflows/integration.yml (02-09).
# Reads a unified diff from stdin (or file path in $1) and exits 1 if it adds
# banned patterns inside `tests/`:
#   - unittest.mock import / usage
#   - mocker.patch
#   - pytest.skip
#   - pytest.mark.xfail
#   - threshold-lowering inside paired -/+ assert lines
# Exits 0 (silent) on clean diffs and on banned patterns confined to non-test files.
# ============================================================================

set -u  # NOT -e; we collect refusals across the whole diff before exiting

RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

# ---- Read diff source ----------------------------------------------------
if [ "${1:-}" != "" ]; then
    if [ ! -f "$1" ]; then
        echo "iter-fix-check-diff.sh: file not found: $1" >&2
        exit 2
    fi
    DIFF=$(cat -- "$1")
else
    # No arg: read stdin
    DIFF=$(cat)
fi

# ---- State machine: walk the diff line-by-line ---------------------------
# Track current target file via `+++ b/<path>` markers.
# Only enforce when the active file path starts with tests/.
# For threshold-lowering, we look at adjacent -/+ pairs where both contain
# `assert ... < <numeric>` and the + numeric is greater than the - numeric.

refused=()
current_file=""
in_tests=false
prev_line=""        # previous diff line (used for threshold pairing)
prev_was_minus=false  # whether prev_line was a minus assert

# Patterns we refuse — assembled at runtime so this script's own source
# does not contain naked banned tokens that a future grep over scripts/
# could false-positive on. (The grep below sees the constructed string.)
P_UNITTEST_MOCK="unittest"".""mock"
P_MOCKER_PATCH="mocker"".""patch"
P_PYTEST_SKIP="pytest"".""skip"
P_PYTEST_XFAIL="pytest"".""mark.xfail"
BANNED_RE="(${P_UNITTEST_MOCK}|${P_MOCKER_PATCH}|${P_PYTEST_SKIP}|${P_PYTEST_XFAIL})"
# Note: dots in the pattern are intentional — grep -E treats them as "any char",
# slightly broader than literal but safe for this purpose; D-12 wording allows it
# (e.g., `unittest_mock` would also match — overzealous, surfaces for human review).

# Threshold extractor — match `assert ... < <numeric>` (with optional <=).
# Captures the numeric in BASH_REMATCH[1].
THRESHOLD_RE='assert.*<=?[[:space:]]*([0-9]+(\.[0-9]+)?)'

while IFS= read -r line; do
    # File header — update scope
    if [[ "$line" =~ ^\+\+\+\ b/(.+)$ ]]; then
        current_file="${BASH_REMATCH[1]}"
        if [[ "$current_file" == tests/* ]]; then
            in_tests=true
        else
            in_tests=false
        fi
        prev_line=""
        prev_was_minus=false
        continue
    fi

    # Skip hunk headers and the `--- a/...` line; reset pairing state on hunk boundary
    if [[ "$line" == @@* ]] || [[ "$line" == ---\ * ]]; then
        prev_line=""
        prev_was_minus=false
        continue
    fi

    # Outside tests/ → allow everything (D-12 is scoped to tests/)
    if [ "$in_tests" = false ]; then
        prev_line="$line"
        prev_was_minus=false
        continue
    fi

    # Banned-token check on additions
    if [[ "$line" =~ ^\+ ]]; then
        # Skip the file-header line we already handled above (handled by ^\+\+\+ check earlier)
        if echo "$line" | grep -qE -- "$BANNED_RE"; then
            # Pull a stable label of which token matched, for the report
            label=""
            if echo "$line" | grep -qE -- "$P_UNITTEST_MOCK"; then label="$P_UNITTEST_MOCK"; fi
            if echo "$line" | grep -qE -- "$P_MOCKER_PATCH"; then label="$P_MOCKER_PATCH"; fi
            if echo "$line" | grep -qE -- "$P_PYTEST_SKIP"; then label="$P_PYTEST_SKIP"; fi
            if echo "$line" | grep -qE -- "$P_PYTEST_XFAIL"; then label="$P_PYTEST_XFAIL"; fi
            refused+=("$current_file: [$label] $line")
        fi
    fi

    # Threshold-lowering check: paired -/+ where both match `assert ... < <num>` and
    # the + numeric is strictly greater than the - numeric.
    if [[ "$line" =~ ^- ]] && ! [[ "$line" =~ ^--- ]]; then
        if [[ "$line" =~ $THRESHOLD_RE ]]; then
            prev_line="$line"
            prev_was_minus=true
        else
            prev_line="$line"
            prev_was_minus=false
        fi
    elif [[ "$line" =~ ^\+ ]] && ! [[ "$line" =~ ^\+\+\+ ]]; then
        if [ "$prev_was_minus" = true ] && [[ "$line" =~ $THRESHOLD_RE ]]; then
            new_num="${BASH_REMATCH[1]}"
            if [[ "$prev_line" =~ $THRESHOLD_RE ]]; then
                old_num="${BASH_REMATCH[1]}"
                # Numeric compare via awk (handles floats; bash arith doesn't)
                if awk -v n="$new_num" -v o="$old_num" 'BEGIN{exit !(n+0 > o+0)}'; then
                    refused+=("$current_file: [threshold lowering] $prev_line -> $line")
                fi
            fi
        fi
        prev_line="$line"
        prev_was_minus=false
    else
        # Context line (` `) or other — break pairing
        prev_line="$line"
        prev_was_minus=false
    fi
done <<< "$DIFF"

# ---- Report --------------------------------------------------------------
if [ ${#refused[@]} -gt 0 ]; then
    echo -e "${RED}[REFUSED] D-12 anti-mock guard hit:${NC}" >&2
    for r in "${refused[@]}"; do
        echo -e "  ${YELLOW}${r}${NC}" >&2
    done
    echo "Refusal patterns: ${P_UNITTEST_MOCK} | ${P_MOCKER_PATCH} | ${P_PYTEST_SKIP} | ${P_PYTEST_XFAIL} | threshold-lowering" >&2
    # Echo banned tokens once on stdout so callers (and tests) can grep cleanly
    # whichever stream they prefer.
    for r in "${refused[@]}"; do
        echo "$r"
    done
    echo "Refusal patterns: ${P_UNITTEST_MOCK} | ${P_MOCKER_PATCH} | ${P_PYTEST_SKIP} | ${P_PYTEST_XFAIL} | threshold-lowering"
    exit 1
fi
exit 0
