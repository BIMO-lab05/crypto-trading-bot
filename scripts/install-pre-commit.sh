#!/usr/bin/env bash
# Phase 15 (TOOL-01/02/03): operator-side opt-in pre-commit hook installer.
#
# CANONICAL enforcement of the planning-tooling gates is the CI workflow
# .github/workflows/planning-tooling-gate.yml (always runs on PR + push).
# This script is the developer-side convenience: a pre-commit hook that
# runs the 3 grep gates locally so the operator catches placeholder
# one-liners and out-of-sync workflow assertions BEFORE pushing.
#
# Per .planning/phases/15-planning-tooling-hardening/15-PATTERNS.md §3 the
# choice was scripts/install-pre-commit.sh (mirrors bootstrap.sh repo-local
# opt-in install pattern) over .pre-commit-config.yaml (would add a tool
# dependency this repo doesn't already use) or husky (Node-only ecosystem).
#
# Idempotent: safe to re-run. The installed hook carries the marker comment
# `planning-tooling-gate-installer` so re-running this script does not
# double-append; the existing hook (whether ours or a prior unrelated hook)
# is backed up to .git/hooks/pre-commit.bak.{timestamp} before replacement.
# Uninstall: rm .git/hooks/pre-commit (or restore the timestamped backup).

set -euo pipefail

HOOK_PATH=".git/hooks/pre-commit"
BACKUP_PATH=".git/hooks/pre-commit.bak.$(date +%Y%m%d-%H%M%S)"
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if [[ ! -e .git ]]; then
  echo "[install-pre-commit] ERROR: not in a git repo (.git/ missing)." >&2
  exit 1
fi

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

# TOOL-01 placeholder-one-liner gate runs only when a *-PLAN.md or
# *-SUMMARY.md is staged, so non-planning commits are not slowed by the
# pytest collect cost.
STAGED_PLANS=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.planning/phases/.*-(PLAN|SUMMARY)\.md$' || true)
if [[ -n "${STAGED_PLANS}" ]]; then
  python3 -m pytest tests/ci/test_no_placeholder_one_liners.py -q || exit 1
fi

# TOOL-02 + TOOL-03 fixture-validation tests run unconditionally on every
# commit (cheap, ~1s each combined). The wiring tests within those modules
# SKIP automatically if the host SDK is absent — that's the documented
# asymmetric contract per 15-PATTERNS.md §2 — so unconditional invocation
# is safe even when the operator has not installed the SDK.
python3 -m pytest tests/ci/test_roadmap_analyze_supersession_wired.py tests/ci/test_audit_freshness_gate.py -q || exit 1

exit 0
HOOK

chmod +x "$HOOK_PATH"
echo "[install-pre-commit] hook installed at $HOOK_PATH"
echo "[install-pre-commit] re-run this script after every git clone to re-arm the hook."
echo "[install-pre-commit] uninstall: rm $HOOK_PATH"
