"""
Append-only record of every strategy variant ever put through the gates.

Why: the operator chose open-ended iteration - keep running batteries until
something passes. Unbounded candidate mining makes a lucky false positive
inevitable unless the selection bar accounts for every trial ever spent, so
DSR is deflated against the ledger count rather than the current battery's.

WHERE THIS ACTUALLY BINDS - read before quoting it as a guarantee:
gate2 uses num_trials = max(num_trials_floor, n_paths), and n_paths reaches 45
at the pinned CPCV 10/2 config (the H4 verdict records num_trials_used: 45).
A ledger-derived floor therefore changes nothing until it exceeds 45, or when
a short series yields few variance-valid paths. The rail binds where mining is
cheapest, but the bar does NOT rise on every battery. Do not claim it does.

Counting rule: a trial is a distinct (candidate, variant) pair. Re-running the
same variant on a later date is recorded as a second row but counts once - it
is the same hypothesis re-measured, not a new one drawn.
"""

import json
from pathlib import Path

from edge_lab.config import NUM_TRIALS_FLOOR


def ledger_path() -> Path:
    return Path(__file__).resolve().parent / "trial_ledger.json"


def load_entries(path: Path | None = None) -> list[dict]:
    path = Path(path) if path is not None else ledger_path()
    if not path.exists():
        return []
    with path.open("r") as f:
        return json.load(f)


def distinct_variant_count(entries: list[dict]) -> int:
    return len({(e["candidate"], e["variant"]) for e in entries})


def append_entries(entries: list[dict], path: Path | None = None) -> None:
    path = Path(path) if path is not None else ledger_path()
    existing = load_entries(path)
    combined = existing + entries
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(combined, f, indent=2)
        f.write("\n")


def effective_trials_floor(
    new_variant_count: int,
    path: Path | None = None,
    static_floor: int = NUM_TRIALS_FLOOR,
) -> int:
    path = Path(path) if path is not None else ledger_path()
    entries = load_entries(path)
    distinct_count = distinct_variant_count(entries)
    return max(static_floor, distinct_count + new_variant_count)
