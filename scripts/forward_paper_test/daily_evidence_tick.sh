#!/usr/bin/env bash
# Daily MLGATE evidence tick. Cron-invoked (Task 9). Runs the evidence loop
# against the harness leaderboard DB and ALWAYS writes the liveness marker —
# the marker records that the tick ran; exit_code inside records how it went.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

DB="${TOURNAMENT_DB_PATH:-$REPO/services/tournament-harness/data/leaderboard/leaderboard.db}"
LOG="$REPO/.planning/state/evidence_loop_last_tick.log"

python3 -m scripts.forward_paper_test.run_evidence_loop --db-path "$DB" >"$LOG" 2>&1
EC=$?

python3 - "$EC" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
Path(".planning/state").mkdir(parents=True, exist_ok=True)
Path(".planning/state/evidence_loop_last_tick.json").write_text(json.dumps({
    "ts_utc": datetime.now(timezone.utc).isoformat(),
    "exit_code": int(sys.argv[1]),
}))
PY
exit "$EC"
