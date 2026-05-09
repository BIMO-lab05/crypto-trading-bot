#!/usr/bin/env bash
# Tier 2 escalation: invokes `claude -p` to diagnose + fix + open PR.
# Single-flight (flock). Budget-capped. Open-PR-capped.
#
# Inputs:
#   $1  path to tier-1 JSON failure report
# Env (override as needed):
#   CLAUDE_BIN        path to claude CLI (default: claude)
#   CLAUDE_MAX_TURNS  cap on agent turns (default: 40)
#   DAILY_BUDGET      max tier-2 invocations per UTC day (default: 8)
#   MAX_OPEN_AUTO_PRS max concurrent open auto-monitor PRs (default: 1)
#   BACKTEST_CMD      backtest entry point exported to the agent (required)

set -uo pipefail

FAILURE_JSON="${1:-}"
if [ -z "$FAILURE_JSON" ] || [ ! -f "$FAILURE_JSON" ]; then
    echo "tier2: missing or unreadable failure JSON: $FAILURE_JSON" >&2
    exit 64
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$REPO_ROOT/logs"
mkdir -p "$LOG_DIR"

CLAUDE_BIN="${CLAUDE_BIN:-claude}"
CLAUDE_MAX_TURNS="${CLAUDE_MAX_TURNS:-40}"
DAILY_BUDGET="${DAILY_BUDGET:-8}"
MAX_OPEN_AUTO_PRS="${MAX_OPEN_AUTO_PRS:-1}"

LOCK_FILE="/tmp/crypto-monitor-tier2.lock"
TODAY="$(date -u +%Y-%m-%d)"
BUDGET_FILE="/tmp/crypto-monitor-budget-$TODAY"
LOG_FILE="$LOG_DIR/monitor_tier2.log"

log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG_FILE" >&2; }

# Single-flight: bail if another tier-2 run is in progress.
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "tier2: another instance is running — exiting"
    exit 0
fi

# Budget: count invocations today.
count="$(cat "$BUDGET_FILE" 2>/dev/null || echo 0)"
if [ "$count" -ge "$DAILY_BUDGET" ]; then
    log "tier2: daily budget exhausted ($count/$DAILY_BUDGET) — alerting only"
    if command -v gh >/dev/null 2>&1; then
        gh issue create \
            --title "auto-monitor: daily budget exhausted, manual triage needed" \
            --label "auto-monitor,needs-triage" \
            --body "Tier-1 reported failures but tier-2 has hit the daily cap. Latest report:
\`\`\`json
$(cat "$FAILURE_JSON")
\`\`\`" >/dev/null 2>&1 || log "tier2: gh issue create failed"
    fi
    exit 0
fi

# Open-PR cap.
if command -v gh >/dev/null 2>&1; then
    open_count="$(gh pr list --label auto-monitor --state open --json number --limit 50 2>/dev/null \
                  | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))' 2>/dev/null || echo 0)"
    if [ "$open_count" -ge "$MAX_OPEN_AUTO_PRS" ]; then
        log "tier2: $open_count open auto-monitor PR(s) — appending failure to existing PR instead"
        pr_num="$(gh pr list --label auto-monitor --state open --json number --limit 1 2>/dev/null \
                  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d[0]["number"] if d else "")' 2>/dev/null)"
        if [ -n "$pr_num" ]; then
            gh pr comment "$pr_num" --body "New tier-1 failure while this PR is open:
\`\`\`json
$(cat "$FAILURE_JSON")
\`\`\`" >/dev/null 2>&1 || log "tier2: gh pr comment failed"
        fi
        exit 0
    fi
fi

# Pre-flight: backtest entry point must be set; otherwise the gate is a no-op.
if [ -z "${BACKTEST_CMD:-}" ]; then
    log "tier2: BACKTEST_CMD not set — refusing to run without backtest gate"
    if command -v gh >/dev/null 2>&1; then
        gh issue create \
            --title "auto-monitor: BACKTEST_CMD unset, gate disabled" \
            --label "auto-monitor,needs-triage" \
            --body "Tier-2 will not run autonomous fixes without a backtest gate. Set BACKTEST_CMD in the cron env (see scripts/monitoring/README.md). Latest tier-1 report:
\`\`\`json
$(cat "$FAILURE_JSON")
\`\`\`" >/dev/null 2>&1 || log "tier2: gh issue create failed"
    fi
    exit 0
fi

# Increment budget *before* spending — fail-closed on crash.
echo "$((count + 1))" > "$BUDGET_FILE"

log "tier2: invoking claude -p (turns<=$CLAUDE_MAX_TURNS, budget $((count+1))/$DAILY_BUDGET)"

mission="$(cat "$SCRIPT_DIR/tier2_mission.md")"

FAILURE_JSON="$FAILURE_JSON" \
REPO_ROOT="$REPO_ROOT" \
BACKTEST_CMD="$BACKTEST_CMD" \
"$CLAUDE_BIN" -p "$mission" \
    --max-turns "$CLAUDE_MAX_TURNS" \
    >> "$LOG_FILE" 2>&1
rc=$?
log "tier2: claude exited rc=$rc"
exit "$rc"
