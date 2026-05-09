#!/usr/bin/env bash
# Closes auto-monitor PRs older than $STALE_HOURS (default 24).
# Idempotent; safe to run on every cron tick.

set -uo pipefail

STALE_HOURS="${STALE_HOURS:-24}"
LOG_FILE="${LOG_FILE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/logs/monitor_janitor.log}"
mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "$(date -u +%FT%TZ) $*" >> "$LOG_FILE"; }

if ! command -v gh >/dev/null 2>&1; then
    log "janitor: gh not installed — skipping"
    exit 0
fi

prs="$(gh pr list --label auto-monitor --state open \
        --json number,createdAt,url --limit 50 2>/dev/null)" || {
    log "janitor: gh pr list failed"
    exit 0
}

PRS="$prs" STALE_HOURS="$STALE_HOURS" python3 <<'PY' | while IFS=$'\t' read -r num url; do
import os, json
from datetime import datetime, timezone, timedelta
stale_hours = int(os.environ["STALE_HOURS"])
prs = json.loads(os.environ["PRS"] or "[]")
cutoff = datetime.now(timezone.utc) - timedelta(hours=stale_hours)
for pr in prs:
    created = datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))
    if created < cutoff:
        print(f'{pr["number"]}\t{pr["url"]}')
PY
    log "janitor: closing stale auto-monitor PR #$num ($url)"
    gh pr close "$num" --comment "Auto-closed: not reviewed within ${STALE_HOURS}h. Re-open if still relevant." \
        >/dev/null 2>&1 || log "janitor: failed to close PR #$num"
done
