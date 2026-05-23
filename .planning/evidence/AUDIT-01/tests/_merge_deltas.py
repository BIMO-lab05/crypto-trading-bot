"""AUDIT-01 merge module — Plan 16-06.

Merges per-track delta files (track-A, track-B, track-C1, track-C2) into the
canonical validated-reaudit.json. Per CONTEXT D-03: zero pending rows after
merge; row count preserved; every (req_id, era) tuple from seed appears
exactly once in canonical.

Seed snapshot (captured pre-merge from validated-reaudit.json):
  seed_count = 81
  era distribution = {pre-v1: 26, v1.0: 23, v1.1: 19, v1.2: 13}
Delta union row count (track A 17 + B 19 + C1 24 + C2 21) = 81.

Merge contract:
  - seed (req_id, era, source, claim) preserved verbatim
  - delta (status, evidence_file, evidence_line_start, evidence_line_end, notes) overlaid
  - duplicate req_id across tracks → ValueError (two tracks claimed ownership)
  - seed REQ without a delta entry → ValueError (missing-from-deltas)
  - delta REQ without a seed entry → ValueError (spurious delta)
  - era/source/claim mismatch between seed and delta → ValueError (audit drift)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EVIDENCE_DIR = Path(__file__).resolve().parents[1]  # .planning/evidence/AUDIT-01/
SEED_PATH = EVIDENCE_DIR / "validated-reaudit.json"  # initially seed; finally canonical
DELTA_PATHS = [
    EVIDENCE_DIR / "track-A-deltas.json",
    EVIDENCE_DIR / "track-B-deltas.json",
    EVIDENCE_DIR / "track-C1-deltas.json",
    EVIDENCE_DIR / "track-C2-deltas.json",
]
SCHEMA_PATH = EVIDENCE_DIR / "_schema.json"


def load_seed() -> dict[str, Any]:
    return json.loads(SEED_PATH.read_text())


def load_all_deltas() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in DELTA_PATHS:
        d = json.loads(p.read_text())
        rows.extend(d["rows"])
    return rows


def merge() -> dict[str, Any]:
    seed = load_seed()
    seed_rows = seed["rows"]
    deltas = load_all_deltas()

    # Index deltas by req_id. req_id is the merge key; era is auxiliary.
    # Duplicate req_id across tracks => two tracks claimed ownership => raise.
    delta_by_id: dict[str, dict[str, Any]] = {}
    for d in deltas:
        if d["req_id"] in delta_by_id:
            raise ValueError(
                f"Duplicate delta row for {d['req_id']!r} — two tracks claimed ownership"
            )
        delta_by_id[d["req_id"]] = d

    # Apply deltas to seed.
    merged_rows: list[dict[str, Any]] = []
    unrouted: list[str] = []
    for sr in seed_rows:
        d = delta_by_id.pop(sr["req_id"], None)
        if d is None:
            unrouted.append(sr["req_id"])
            merged_rows.append(sr)  # keep as pending (completeness test will fire RED)
            continue
        # Sanity: era + source + claim echoed verbatim by the delta.
        for k in ("era", "source", "claim"):
            if d.get(k) != sr.get(k):
                raise ValueError(
                    f"Delta for {sr['req_id']!r} does not echo seed {k!r}: "
                    f"seed={sr.get(k)!r} delta={d.get(k)!r}"
                )
        merged_row = {
            "req_id": sr["req_id"],
            "era": sr["era"],
            "source": sr["source"],
            "claim": sr["claim"],
            "evidence_file": d.get("evidence_file"),
            "evidence_line_start": d.get("evidence_line_start"),
            "evidence_line_end": d.get("evidence_line_end"),
            "status": d["status"],
            "notes": d.get("notes"),
        }
        merged_rows.append(merged_row)

    if unrouted:
        raise ValueError(f"Seed REQs without a delta entry: {unrouted}")
    if delta_by_id:
        raise ValueError(
            f"Delta rows without a seed entry (spurious): {list(delta_by_id)}"
        )

    return {"schema_version": 1, "rows": merged_rows}


def write_canonical() -> int:
    merged = merge()
    SEED_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
    return len(merged["rows"])


if __name__ == "__main__":
    n = write_canonical()
    print(f"Merged {n} rows into {SEED_PATH}")
