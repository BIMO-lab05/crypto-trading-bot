"""Dated verdict files for kill-test runs (spec §9).

Verdict language is the audit criterion verbatim — never an edge claim.
"""

import glob
import json
import os
from datetime import date

EVIDENCE_DIR = ".planning/evidence/killtests"


def write_verdict(
    test_id,
    verdict,
    criterion,
    metrics,
    caveats,
    config,
    input_hashes,
    out_dir=EVIDENCE_DIR,
    tables=None,
):
    """tables: optional {name: list-of-row-dicts} — written to the .json only
    (per-trade / per-symbol detail per spec §5/§9)."""
    if verdict not in ("ACCEPT", "REJECT"):
        raise ValueError(f"verdict must be ACCEPT or REJECT, got {verdict!r}")
    os.makedirs(out_dir, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    base = os.path.join(out_dir, f"{test_id}-verdict-{stamp}")
    doc = {
        "test_id": test_id,
        "verdict": verdict,
        "criterion": criterion,
        "metrics": metrics,
        "caveats": caveats,
        "config": config,
        "input_hashes": input_hashes,
        "date": stamp,
        "tables": tables or {},
    }
    with open(base + ".json", "w") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
    lines = [
        f"# {test_id} verdict: {verdict}",
        "",
        f"**Criterion (AUDIT.md §7, verbatim):** {criterion}",
        "",
        "## Metrics",
        "",
    ]
    lines += [f"- {k}: {v}" for k, v in sorted(metrics.items())]
    lines += ["", "## Caveats", ""] + [f"- {c}" for c in caveats]
    lines += [
        "",
        "## Config",
        "",
        "```json",
        json.dumps(config, indent=2, sort_keys=True),
        "```",
    ]
    lines += ["", "## Input hashes", ""] + [
        f"- {k}: {v}" for k, v in sorted(input_hashes.items())
    ]
    with open(base + ".md", "w") as f:
        f.write("\n".join(lines) + "\n")
    return base + ".md"


def latest_verdict(test_id, out_dir=EVIDENCE_DIR):
    paths = sorted(glob.glob(os.path.join(out_dir, f"{test_id}-verdict-*.json")))
    if not paths:
        return None
    with open(paths[-1]) as f:
        return json.load(f)
