#!/bin/bash
# ============================================================================
# iter-fix.sh — checkpointed iteration harness (Phase 2 Plan 02-06, INFRA-04).
# Decisions: D-09 (terminal git diff + Apply prompt), D-10 (entry point at
# scripts/iter-fix.sh), D-11 (per-fix granularity), D-12 (anti-mock refusal),
# D-13 carry-forward (NO auto-retry, NO iterate-until-green Goodhart loop).
#
# Flow (one cycle, hand control back to operator after):
#   1. Run pytest tests/integration -x; capture failure log on first red.
#   2. Hand control to operator (or wrapped Claude `-p`) — they propose a fix
#      and `git add` the relevant files.
#   3. Pipe staged diff into iter-fix-check-diff.sh; refuse on D-12 banned patterns.
#   4. Print the staged diff and prompt `Apply? [y/N]`.
#   5. On approval: prompt for `fix(<service>): <one-line>`; commit atomically.
#
# To iterate, the operator re-runs the script. Wrapping in `while`/`watch` is a
# T-02-06-03 risk (operator-side anti-pattern) — D-13 calls this out explicitly.
#
# Note (deferred): tagging failed-attempt branches with `wip(iter)` is mentioned
# in 02-PATTERNS.md as a future ergonomic; not implemented here to keep this
# script under 100 lines and the surface small.
# ============================================================================

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

CHECK_DIFF="$SCRIPT_DIR/iter-fix-check-diff.sh"
if [ ! -x "$CHECK_DIFF" ]; then
    echo -e "${RED}MISSING: $CHECK_DIFF (D-12 helper)${NC}" >&2
    exit 2
fi

# ---- Step 1: Run integration suite, stop on first red --------------------
echo -e "${YELLOW}[1/5] Running integration suite (pytest tests/integration -x)...${NC}"
PYTEST_LOG="$(mktemp -t iter-fix-pytest.XXXXXX.log)"
set +e
pytest tests/integration -x 2>&1 | tee "$PYTEST_LOG"
PYTEST_EXIT=${PIPESTATUS[0]}
set -e
if [ "$PYTEST_EXIT" -eq 0 ]; then
    echo -e "${GREEN}[2/5] All tests green. No fix needed. Exit.${NC}"
    rm -f "$PYTEST_LOG"
    exit 0
fi
echo -e "${RED}[2/5] First red at exit=$PYTEST_EXIT. Failure log saved to $PYTEST_LOG.${NC}"

# ---- Step 2: Hand control to operator ------------------------------------
echo -e "${YELLOW}[3/5] Make a fix. Stage it with 'git add <files>'. Press ENTER when ready, or Ctrl-C to abort.${NC}"
read -r _

# ---- Step 3: D-12 refusal check on staged diff ---------------------------
echo -e "${YELLOW}[4/5] Checking staged diff against D-12 refusal patterns...${NC}"
STAGED_DIFF=$(git diff --cached)
if [ -z "$STAGED_DIFF" ]; then
    echo -e "${RED}[REFUSED] Nothing staged. Run 'git add <files>' and re-invoke.${NC}" >&2
    exit 1
fi
if ! echo "$STAGED_DIFF" | bash "$CHECK_DIFF"; then
    echo -e "${RED}[REFUSED] Staged diff hit D-12 anti-mock guard. Unstage and retry.${NC}" >&2
    echo "  Run: git reset HEAD <files>" >&2
    exit 1
fi
echo -e "${GREEN}        diff cleared D-12 guard.${NC}"

# ---- Step 4: Operator review + approval gate -----------------------------
echo -e "${YELLOW}[5/5] Review the diff and confirm:${NC}"
git --no-pager diff --cached
echo
read -p "Apply? [y/N]: " ans
case "$ans" in
    [yY]|[yY][eE][sS])
        # Step 5: prompt for one-line commit message + atomic commit (D-11)
        read -p "Commit message (fix(<service>): <one-line>): " msg
        if [ -z "$msg" ]; then
            echo -e "${RED}Empty commit message — aborting${NC}" >&2
            exit 1
        fi
        # T-02-06-02 mitigation: $msg passed as a single quoted arg to git commit -m;
        # shell does not re-evaluate the variable.
        git commit -m "$msg"
        echo -e "${GREEN}Committed. Re-run pytest to verify.${NC}"
        ;;
    *)
        echo -e "${YELLOW}Skipped. Diff still staged. Run 'git reset HEAD' to unstage.${NC}"
        exit 1
        ;;
esac

# D-13 carry-forward — exit cleanly after one cycle. No auto-retry loop.
echo -e "${GREEN}[done] One fix applied. Re-run scripts/iter-fix.sh to continue.${NC}"
