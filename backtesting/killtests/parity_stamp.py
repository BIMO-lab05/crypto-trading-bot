"""Golden-parity stamp: what it may claim, and the pure function that decides.

`.planning/evidence/killtests/golden-parity-stamp.json` is the gate
`h4_information.py:192` reads (`date == today and passed is True`). It has to
mean exactly one thing: *the golden-parity suite ran today and every one of
its checks passed*. Anything weaker lets an H4 verdict rest on a seam that
was never shown to be equivalent — and the design spec says a parity
mismatch invalidates any H4 run.

Until 2026-08-07 it meant something much weaker. `test_write_stamp` wrote
`passed: true` on a single condition — that the chain-action list was
non-empty — and pytest runs that test regardless of whether the parity
assertions above it failed. One symbol appending its action before a later
symbol's mismatch was enough to mint a "passed" stamp for a session that had
just proven the seam BROKEN.

Minting now happens once, from `pytest_sessionfinish` in
`tests/killtests/conftest.py`, which is the only place the session's own
failure count is visible. The rules:

* suite did not run — module-level skip (stack down), or collected but every
  parity test deselected (`-m "not golden"`, `-k`) -> touch nothing
* any failure/error anywhere in the session, or a required parity test that
  did not reach its end -> write `passed: false` with the reasons. A false
  stamp closes the H4 gate exactly as a missing one does, and unlike
  deleting the file it leaves the reason on disk, in an evidence directory
* all-HOLD across every symbol -> write nothing (unchanged, spec §7.1): the
  ensemble legs were never exercised, which is not a failure, so an earlier
  same-day pass stays valid
* otherwise -> `passed: true`, self-describing (see `mint_stamp`)

`mint_stamp` is pure so the rules can be unit-tested without the docker
stack the golden suite itself requires.
"""

import hashlib
import json
import os
from datetime import date

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))

EVIDENCE_DIR = os.path.join(_REPO, ".planning", "evidence", "killtests")
DEFAULT_STAMP_PATH = os.path.join(EVIDENCE_DIR, "golden-parity-stamp.json")
DEFAULT_MANIFEST_PATH = os.path.join(EVIDENCE_DIR, "backfill-manifest-2026-08.md")

# Every test that must reach its end before the stamp may claim parity.
# A test that fails, errors, or is deselected never records itself here.
REQUIRED_TESTS = (
    "test_candle_window_equality",
    "test_indicator_endpoint_parity",
    "test_full_chain_parity",
)

STAMP_SCHEMA_VERSION = 2


def sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def fingerprint_data_dir(data_dir: str) -> dict:
    """Content fingerprint of the backfill CSVs the offline leg reads.

    The stamp certifies code-path equivalence at the live latest bar, not the
    identity of a CSV snapshot (a parity copy is legitimate — see README), so
    this is recorded as provenance, never compared. Digest is over sorted
    `name:sha256` lines, so it is stable across filesystems and orderings.
    """
    try:
        names = sorted(n for n in os.listdir(data_dir) if n.endswith("_365d_bybit.csv"))
    except OSError as exc:
        return {"data_dir": data_dir, "error": str(exc), "files": 0, "sha256": None}
    lines = [f"{n}:{sha256_file(os.path.join(data_dir, n))}" for n in names]
    digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    return {"data_dir": data_dir, "files": len(names), "sha256": digest}


class ParityRun:
    """Accumulator the golden suite fills in as it goes.

    Deliberately an instance, not module globals: `RUN` below is the one the
    conftest hook reads, and unit tests build their own so they can never
    cause a stamp to be written by an ordinary (non-golden) test run.
    """

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.suite_ran = False
        self.symbols: list = []
        self.data_dir: str | None = None
        self.started_tests: list = []
        self.passed_tests: list = []
        self.chain_actions: dict = {}
        self.manifest_sha256: str | None = None
        self.manifest_path: str | None = None
        self.data_dir_fingerprint: dict = {}

    def begin(
        self,
        symbols,
        data_dir: str,
        manifest_path: str = DEFAULT_MANIFEST_PATH,
    ) -> None:
        """Called at golden-module import, i.e. only once the stack probe passed.

        Deliberately cheap: pytest imports this module during collection even
        when `-m "not golden"` deselects every test in it, and hashing the
        backfill CSVs on every unrelated run would be pure waste. The input
        snapshot is taken by the first `record_start`.
        """
        self.reset()
        self.suite_ran = True
        self.symbols = list(symbols)
        self.data_dir = data_dir
        self.manifest_path = manifest_path

    def record_start(self, test_name: str) -> None:
        """Called on the FIRST line of a parity test — proves it executed.

        Without this, a run that only *collected* the module (marker
        deselection, `-k` filter) looks identical to a run whose first parity
        test failed before recording anything, and the stamp of an earlier
        genuine pass would be invalidated by an unrelated test run.
        """
        if test_name in self.started_tests:
            return
        if not self.started_tests:
            if self.manifest_path and os.path.exists(self.manifest_path):
                self.manifest_sha256 = sha256_file(self.manifest_path)
            self.data_dir_fingerprint = fingerprint_data_dir(self.data_dir)
        self.started_tests.append(test_name)

    def record_pass(self, test_name: str) -> None:
        """Called on the LAST line of a parity test — unreachable if it failed."""
        if test_name not in self.passed_tests:
            self.passed_tests.append(test_name)

    def record_chain_action(self, symbol: str, action: str) -> None:
        self.chain_actions[symbol] = action

    def state(self) -> dict:
        return {
            "suite_ran": self.suite_ran,
            "symbols": list(self.symbols),
            "data_dir": self.data_dir,
            "started_tests": list(self.started_tests),
            "passed_tests": list(self.passed_tests),
            "chain_actions": dict(self.chain_actions),
            "manifest_sha256": self.manifest_sha256,
            "manifest_path": self.manifest_path,
            "data_dir_fingerprint": dict(self.data_dir_fingerprint),
        }


RUN = ParityRun()


def mint_stamp(run_state: dict, session_failures: int, exitstatus: int, today=None):
    """Decide what (if anything) the stamp may say. Pure — no filesystem.

    Returns `(stamp_or_None, reason)`. `None` means "leave the stamp file
    alone": the golden suite never executed, or it ran clean but all-HOLD.
    """
    today = today or date.today().strftime("%Y%m%d")
    if not run_state.get("suite_ran"):
        return None, "golden-parity suite did not run — stamp untouched"
    if not any(t in run_state.get("started_tests", []) for t in REQUIRED_TESTS):
        return None, (
            "golden-parity module was collected but no parity test executed "
            "(marker deselection or -k filter) — stamp untouched"
        )

    reasons = []
    if exitstatus != 0:
        reasons.append(f"pytest exit status {exitstatus} (non-zero)")
    if session_failures:
        reasons.append(f"{session_failures} failure(s)/error(s) in the pytest session")
    missing = [t for t in REQUIRED_TESTS if t not in run_state.get("passed_tests", [])]
    if missing:
        reasons.append("parity test(s) did not pass: " + ", ".join(missing))

    chain_actions = run_state.get("chain_actions", {})
    non_hold = sorted({a for a in chain_actions.values() if a != "HOLD"})

    stamp = {
        "schema_version": STAMP_SCHEMA_VERSION,
        "date": today,
        "passed": not reasons,
        "refused_because": reasons,
        "required_tests": list(REQUIRED_TESTS),
        "started_tests": list(run_state.get("started_tests", [])),
        "passed_tests": list(run_state.get("passed_tests", [])),
        "session_failures": session_failures,
        "pytest_exit_status": exitstatus,
        "symbols": list(run_state.get("symbols", [])),
        "chain_actions": dict(chain_actions),
        "non_hold_actions": non_hold,
        "data_dir": run_state.get("data_dir"),
        "data_dir_fingerprint": dict(run_state.get("data_dir_fingerprint", {})),
        "backfill_manifest_path": run_state.get("manifest_path"),
        # Full digest. Verdict `input_hashes` carry the first 12 chars of the
        # same manifest hash — compare by prefix.
        "backfill_manifest_sha256": run_state.get("manifest_sha256"),
    }

    if reasons:
        return stamp, "; ".join(reasons)
    if not non_hold:
        return None, (
            "all-HOLD across all symbols — stamp NOT written; the ensemble legs "
            "were never exercised (spec §7.1). Re-run when the live market "
            "produces a non-HOLD signal (H4 stays gated)."
        )
    return stamp, f"parity passed; non-HOLD action(s) observed: {', '.join(non_hold)}"


def write_stamp(stamp: dict, path: str = DEFAULT_STAMP_PATH) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(stamp, f, indent=2, sort_keys=True)
    return path
