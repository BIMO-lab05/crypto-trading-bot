#!/usr/bin/env bash
# Phase 15 (TOOL-01/02/03): operator-side opt-in pre-commit hook installer.
#
# CANONICAL enforcement of the planning-tooling gates is the CI workflow
# .github/workflows/planning-tooling-gate.yml (always runs on PR + push).
# This script is the developer-side convenience: a pre-commit hook that
# runs the IN-REPO portion of the 3 grep gates locally so the operator
# catches placeholder one-liners + fixture drift BEFORE pushing.
#
# Per .planning/phases/15-planning-tooling-hardening/15-PATTERNS.md §3 the
# choice was scripts/install-pre-commit.sh (mirrors bootstrap.sh repo-local
# opt-in install pattern) over .pre-commit-config.yaml (would add a tool
# dependency this repo doesn't already use) or husky (Node-only ecosystem).
#
# Scope -- the hook runs ONLY the tests that are symmetric across machines:
#
#   1. TOOL-01 placeholder gate (tests/ci/test_no_placeholder_one_liners.py)
#      -- scans in-repo .planning/phases/ tree; same result regardless of
#      whether the host SDK is installed.
#
#   2. TOOL-02 / TOOL-03 fixture-replay tests -- selected by `-k` filter so
#      ONLY the unconditional fixture-validation tests run, NOT the wiring
#      tests. The wiring tests target ~/.claude/get-shit-done/workflows/
#      complete-milestone.md, which is the operator's host SDK workflow:
#
#        * On a developer machine WITHOUT the host SDK: wiring tests SKIP
#          (asymmetric-pass per 15-PATTERNS.md §2). Safe to invoke.
#        * On a developer machine WITH the host SDK installed (the
#          realistic operator profile -- they wouldn't be running this
#          installer otherwise): wiring tests RED-FAIL because the SDK
#          workflow has not yet been ported per the SDK-proposal specs.
#          Invoking them in pre-commit would BLOCK every commit on that
#          machine; the operator's only escape is `git commit --no-verify`,
#          which defeats the gate they just installed.
#
#      The wiring tests are CI-only by design: they require an
#      operator-side SDK port to land before they can flip GREEN, and the
#      pre-commit hook cannot drive that port. Local invocation is
#      available via `pytest tests/ci/` when the operator wants to check
#      port progress explicitly.
#
# Idempotent: safe to re-run. The installed hook carries the marker comment
# `planning-tooling-gate-installer` so re-running this script does not
# double-append; the existing hook (whether ours or a prior unrelated hook)
# is backed up to .git/hooks/pre-commit.bak.{timestamp} before replacement.
# Uninstall: rm .git/hooks/pre-commit (or restore the timestamped backup).

set -euo pipefail

# Precondition check FIRST -- before any `git rev-parse` call. Bash does not
# propagate command-substitution failure to `set -e` by default, so
# `REPO_ROOT=$(git rev-parse --show-toplevel)` invoked outside a git repo
# would silently assign REPO_ROOT="" and the subsequent `cd ""` would
# either change to $HOME or fail depending on bash version. The explicit
# `if [[ ! -e .git ]]` check that used to live below was UNREACHABLE in
# the intended scenario (operator runs installer outside a git repo) --
# `git rev-parse` would have already printed its terse `fatal:` message
# and `cd ""` would have done whatever it does. Move the check ahead of
# `git rev-parse` so operators outside a git tree see the friendly error.
if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "[install-pre-commit] ERROR: not in a git repo. Run from inside the repo tree." >&2
  exit 1
fi

HOOK_PATH=".git/hooks/pre-commit"
BACKUP_PATH=".git/hooks/pre-commit.bak.$(date +%Y%m%d-%H%M%S)"
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Idempotent backup: only back up if there is an existing hook that is NOT
# already our installer's output (marker comment absent). Re-running this
# script with our own installed hook in place produces no backup file (safe
# re-install).
if [[ -f "$HOOK_PATH" ]] && ! grep -q 'planning-tooling-gate-installer' "$HOOK_PATH" 2>/dev/null; then
  cp "$HOOK_PATH" "$BACKUP_PATH"
  echo "[install-pre-commit] backed up existing hook to $BACKUP_PATH"
fi

cat > "$HOOK_PATH" <<'HOOK'
#!/usr/bin/env bash
# planning-tooling-gate-installer — Phase 15 TOOL-01/02/03 pre-commit hook
# Installed by scripts/install-pre-commit.sh. Re-installable; safe to delete.
# Canonical CI enforcement is .github/workflows/planning-tooling-gate.yml.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Pytest availability probe -- the hook gracefully no-ops with a clear
# remediation message when pytest is not installed in the resolvable Python
# environment. Without this probe, the hook would fail with `No module
# named pytest` and block every commit; the operator couldn't even commit
# the fix that installs pytest.
if ! python3 -c "import pytest" 2>/dev/null; then
  echo "[pre-commit] pytest not installed -- skipping planning-tooling gates" >&2
  echo "  install with: python3 -m pip install pytest==7.4.4" >&2
  echo "  (CI workflow remains authoritative; this is just the local convenience hook)" >&2
  exit 0
fi

# TOOL-01 placeholder-one-liner gate runs only when a *-PLAN.md or
# *-SUMMARY.md is staged, so non-planning commits are not slowed by the
# pytest collect cost.
STAGED_PLANS=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.planning/phases/.*-(PLAN|SUMMARY)\.md$' || true)
if [[ -n "${STAGED_PLANS}" ]]; then
  python3 -m pytest tests/ci/test_no_placeholder_one_liners.py -q || exit 1
fi

# TOOL-02 + TOOL-03 IN-REPO fixture-validation tests run on every commit
# (cheap, ~1s combined). The two wiring tests are deliberately --deselect-ed
# below because they target the host SDK workflow at
# ~/.claude/get-shit-done/workflows/complete-milestone.md, which is
# expected to be unported on a developer machine that has the host SDK
# installed (the realistic operator profile for this hook). Invoking the
# wiring tests in pre-commit would RED-FAIL on every commit until the
# operator-side SDK port lands -- which the pre-commit hook cannot drive.
# CI is the authoritative surface for the wiring contract.
#
# To check wiring status explicitly:
#   pytest tests/ci/test_roadmap_analyze_supersession_wired.py \
#          tests/ci/test_audit_freshness_gate.py -v
python3 -m pytest \
  tests/ci/test_roadmap_analyze_supersession_wired.py \
  tests/ci/test_audit_freshness_gate.py \
  --deselect tests/ci/test_roadmap_analyze_supersession_wired.py::test_roadmap_analyze_apply_wired_before_archive \
  --deselect tests/ci/test_audit_freshness_gate.py::test_audit_freshness_check_unconditional_in_workflow \
  -q || exit 1

exit 0
HOOK

chmod +x "$HOOK_PATH"
echo "[install-pre-commit] hook installed at $HOOK_PATH"
echo "[install-pre-commit] re-run this script after every git clone to re-arm the hook."
echo "[install-pre-commit] uninstall: rm $HOOK_PATH"
