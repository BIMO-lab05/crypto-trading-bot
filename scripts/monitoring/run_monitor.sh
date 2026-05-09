#!/usr/bin/env bash
# Cron entry point. Chains tier-1 → (tier-2 if needed) → janitor.
# One global flock so concurrent cron ticks never overlap.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

LOCK="/tmp/crypto-monitor.lock"
exec 8>"$LOCK"
flock -n 8 || { echo "monitor: previous tick still running, skipping" >&2; exit 0; }

REPORT="$(mktemp -t tier1.XXXXXX.json)"
trap 'rm -f "$REPORT"' EXIT

python3 "$SCRIPT_DIR/tier1_monitor.py" --out "$REPORT" >/dev/null
rc=$?

case "$rc" in
    0) ;;  # all green
    1) "$SCRIPT_DIR/tier2_escalate.sh" "$REPORT" || true ;;
    2) echo "monitor: tier-1 self-error, NOT escalating" >&2 ;;
    *) echo "monitor: unexpected tier-1 rc=$rc" >&2 ;;
esac

"$SCRIPT_DIR/auto_pr_janitor.sh" || true
