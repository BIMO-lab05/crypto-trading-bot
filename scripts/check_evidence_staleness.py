#!/usr/bin/env python3
"""Tripwire: alarm when the daily evidence tick has not run in >48h.

The kline collector once died silently for weeks; this is the same class of
guard for the MLGATE evidence loop. Checks marker AGE only — a tick that ran
and failed still counts as alive (its exit_code is printed for the operator).
Exit 0 = tick alive; exit 1 = missing/stale/unreadable marker.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MARKER = ".planning/state/evidence_loop_last_tick.json"
MAX_AGE_HOURS = 48

parser = argparse.ArgumentParser()
parser.add_argument("--marker", default=DEFAULT_MARKER)
args = parser.parse_args()

p = Path(args.marker)
if not p.exists():
    print(f"BREACH: evidence-tick marker missing at {p}")
    sys.exit(1)

try:
    data = json.loads(p.read_text())
    ts = datetime.fromisoformat(data["ts_utc"])
except (ValueError, KeyError) as e:
    print(f"BREACH: marker unreadable ({type(e).__name__})")
    sys.exit(1)

age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
print(f"last tick: {data['ts_utc']} (age {age_h:.1f}h, exit_code={data.get('exit_code')})")
if age_h > MAX_AGE_HOURS:
    print(f"BREACH: evidence tick stale (> {MAX_AGE_HOURS}h)")
    sys.exit(1)
print("OK")
sys.exit(0)
