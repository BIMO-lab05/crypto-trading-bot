"""Static sweep of the feature/signal path for future-facing operations."""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCAN_DIRS = [
    REPO_ROOT / "backtesting",
    REPO_ROOT / "services" / "technical-analysis" / "app",
    REPO_ROOT / "services" / "trading-engine" / "app" / "strategies",
]
SKIP_PARTS = {"__pycache__", "tests", "data", "results"}

PATTERNS = {
    "negative_shift": re.compile(r"\.shift\(\s*-"),
    "bfill": re.compile(r"\.bfill\(|method\s*=\s*['\"]b(ack)?fill['\"]"),
    "interpolate": re.compile(r"\.interpolate\("),
    "center_rolling": re.compile(r"rolling\([^)]*center\s*=\s*True"),
    "full_series_norm": re.compile(
        r"StandardScaler\(\)\.fit\(|MinMaxScaler\(\)\.fit\("
    ),
    "forward_index": re.compile(r"\.iloc\[\s*\w+\s*\+\s*\d|\[\s*i\s*\+\s*1\s*\]"),
    "resample": re.compile(r"\.resample\("),
}

hits = 0
resample_calls = 0
for d in SCAN_DIRS:
    for f in sorted(d.rglob("*.py")):
        if any(p in f.parts for p in SKIP_PARTS):
            continue
        for lineno, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            for name, pat in PATTERNS.items():
                if pat.search(line):
                    rel = f.relative_to(REPO_ROOT)
                    print(f"{rel}:{lineno} | {name} | {line.strip()[:120]}")
                    hits += 1
                    if name == "resample":
                        resample_calls += 1

print(f"RESULT: leakage_hits={hits} resample_calls={resample_calls}")
sys.exit(0)
