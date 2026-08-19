"""Same backtest twice in-process + once fresh-process; byte-compare canonical JSON."""

import json
import subprocess
import sys

from audit._harness import load_candles, make_engine, baseline_strategy, result_summary


def run_once() -> str:
    res = make_engine().run_backtest(load_candles(), baseline_strategy, "det")
    return json.dumps(result_summary(res), sort_keys=True)


if "--emit" in sys.argv:
    print(run_once())
    sys.exit(0)

a, b = run_once(), run_once()
fresh = (
    subprocess.run(
        [sys.executable, __file__, "--emit"], capture_output=True, text=True, check=True
    )
    .stdout.strip()
    .splitlines()[-1]
)

ok = a == b == fresh
print(f"in-process run 1: {a}")
print(f"in-process run 2: {b}")
print(f"fresh process   : {fresh}")
print(f"RESULT: determinism={'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
