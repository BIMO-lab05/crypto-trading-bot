#!/usr/bin/env bash
# Cron entry point. Runs tier-1 health checks and notifies operator on failure.
# No claude invocation. No gh invocation. No git write. Tier-2 deleted per ADR-011.
# One global flock so concurrent cron ticks never overlap.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

LOCK="/tmp/crypto-monitor.lock"
exec 8>"$LOCK"
flock -n 8 || { echo "monitor: previous tick still running, skipping" >&2; exit 0; }

LOG_DIR="$REPO_ROOT/logs"
mkdir -p "$LOG_DIR"

FAILURES_JSONL="$LOG_DIR/monitor_tier1_failures.jsonl"

# ---------------------------------------------------------------------------
# notify_operator_only: log structured failure and optionally POST to Telegram.
# Blast radius: local log append + HTTP POST to TELEGRAM_WEBHOOK_URL (if set).
# No claude. No gh. No git.
# ---------------------------------------------------------------------------
notify_operator_only() {
    local report_path="$1"
    local ts
    ts="$(date -u +%FT%TZ)"

    # Build a one-line JSONL entry with timestamp and full report content.
    local report_content
    report_content="$(cat "$report_path" 2>/dev/null || echo '{}')"

    printf '%s\n' "$(printf '{"timestamp":"%s","report":%s}' "$ts" "$report_content")" \
        >> "$FAILURES_JSONL"

    echo "monitor: tier-1 failure logged to $FAILURES_JSONL" >&2

    # Optional Telegram notification. Requires TELEGRAM_WEBHOOK_URL in env.
    if [ -n "${TELEGRAM_WEBHOOK_URL:-}" ]; then
        local failure_count
        failure_count="$(python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('failure_count',0))" < "$report_path" 2>/dev/null || echo "?")"
        local payload
        payload="{\"text\":\"crypto-bot tier-1 monitor: $failure_count failure(s) at $ts. Check $FAILURES_JSONL for details.\"}"
        if command -v curl >/dev/null 2>&1; then
            curl -s -X POST "$TELEGRAM_WEBHOOK_URL" \
                -H "Content-Type: application/json" \
                -d "$payload" >/dev/null 2>&1 \
                || echo "monitor: Telegram notify failed (non-fatal)" >&2
        fi
    fi
}

# ---------------------------------------------------------------------------
# Main: run tier-1, notify on failure.
# ---------------------------------------------------------------------------
REPORT="$(mktemp -t tier1.XXXXXX.json)"
trap 'rm -f "$REPORT"' EXIT

python3 "$SCRIPT_DIR/tier1_monitor.py" --out "$REPORT" >/dev/null
rc=$?

case "$rc" in
    0) ;;  # all green
    1) notify_operator_only "$REPORT" ;;
    2) echo "monitor: tier-1 self-error, not notifying" >&2 ;;
    *) echo "monitor: unexpected tier-1 rc=$rc" >&2 ;;
esac
