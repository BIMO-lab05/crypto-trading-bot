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

Seeded 2026-08-20: pre-ledger-era historical trials (CLAUDE.md section-2
strategy table, the May-2026 walk-forward sweep enumerated in
run_walk_forward_ensemble.py N_TRIALS, the Dec-2025 RSI walk-forward
optimizer records) were appended so the ledger count reflects the
documented portion of the search actually spent (the Dec-2025 optimizer
grid widths were never recorded, so the true historical count is higher
and this ledger still understates it - anticonservative direction). The distinct count now exceeds the 45 CPCV paths, so the
ledger-derived floor binds on current batteries - the paragraph above
describes the mechanism, not a claim that it never binds.
"""

import json
import os
import tempfile
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
    # Atomic: write to a temp file in the same directory (so os.replace stays
    # on one filesystem) then rename over the target. A crash mid-write
    # leaves the temp file orphaned and the ledger untouched, instead of
    # truncating it.
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(combined, f, indent=2)
            f.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def effective_trial_count(
    new_variant_count: int = 0,
    path: Path | None = None,
) -> int:
    """Raw ledger component of the num_trials formula: distinct
    (candidate, variant) pairs already recorded plus the new variants the
    caller is about to spend. Verdict artifacts report this as
    `ledger_count`; `effective_trials_floor` is max(static floor, this).
    """
    path = Path(path) if path is not None else ledger_path()
    return distinct_variant_count(load_entries(path)) + new_variant_count


def effective_trials_floor(
    new_variant_count: int,
    path: Path | None = None,
    static_floor: int = NUM_TRIALS_FLOOR,
) -> int:
    path = Path(path) if path is not None else ledger_path()
    entries = load_entries(path)
    distinct_count = distinct_variant_count(entries)
    return max(static_floor, distinct_count + new_variant_count)
