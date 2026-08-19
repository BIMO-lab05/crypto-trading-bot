"""Regenerate the full gap audit in one command (spec §3 item 8)."""

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = [
    "gap_leakage_grep.py",
    "gap_invariants.py",
    "gap_determinism.py",
    "gap_reconcile.py",
    "gap_randomwalk.py",
    "gap_signcheck.py",
    "gap_risk_realized.py",
]

results, failures = [], 0
for script in SCRIPTS:
    proc = subprocess.run(
        [sys.executable, str(HERE / script)], capture_output=True, text=True
    )
    line = next(
        (l for l in proc.stdout.splitlines() if l.startswith("RESULT:")),
        f"RESULT: {script}=NOT_VERIFIED rc={proc.returncode}",
    )
    results.append(
        f"- `{script}` → {line[len('RESULT: ') :]}"
        + (" **[FAIL]**" if proc.returncode else "")
    )
    failures += 1 if proc.returncode else 0
    print(line)

findings = HERE / "FINDINGS-GAP.md"
text = findings.read_text()
block = "<!-- results:start -->\n" + "\n".join(results) + "\n<!-- results:end -->"
text = re.sub(r"<!-- results:start -->.*?<!-- results:end -->", block, text, flags=re.S)
findings.write_text(text)
print(f"{failures} failing check(s); FINDINGS-GAP.md results section updated")
sys.exit(failures)
