"""Repo-wide anti-reimplementation gate for the DSR kernel.

The canonical Deflated Sharpe kernel lives in
`services/risk-metrics-service/app/sharpe_metrics.py` and its byte-identical
twin `services/ml-retraining-service/app/sharpe_metrics.py`. Every other
DEFINITION of `deflated_sharpe*` / `probabilistic_sharpe*` must be a thin
wrapper that routes through `killtests.offline_ensemble._load_kernels` (the
sanctioned host-side loader of the canonical kernel, the same mechanism
`edge_lab/gate2.py` uses). A def that does not is a rogue re-implementation:
it drifts, and it was invisible to the tournament-harness grep gate
(`services/tournament-harness/tests/integration/test_tourn07_grep_gate.py`),
whose HARNESS_ROOT scopes the search to the harness only — which is exactly
how the pre-2026-08-20 `backtesting/run_walk_forward*.py` local copies
survived (they paired an annualized Sharpe with a per-bar z-statistic,
making DSR a 0-or-1 step function).

Host-run from the repo root:

    pytest tests/test_no_dsr_reimplementation.py --no-cov
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The only files allowed to DEFINE the kernel itself. Byte-identity between
# the two copies is enforced elsewhere; this gate polices where definitions
# live and that everything else delegates.
ALLOWED = {
    Path("services/risk-metrics-service/app/sharpe_metrics.py"),
    Path("services/ml-retraining-service/app/sharpe_metrics.py"),
}

# Trees never scanned: evidence archives, VCS/tooling internals, vendored
# and generated code, and the canonical copies' own test suites (which may
# quote the def signatures in fixtures or strings).
PRUNE_DIRS = {
    ".git",
    ".planning",
    ".claude",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
PRUNE_PREFIXES = (
    Path("services/risk-metrics-service/tests"),
    Path("services/ml-retraining-service/tests"),
)

# `^[ \t]*` (not `^\s*`): \s eats preceding newlines, shifting match.start()
# onto blank lines above the def and breaking body extraction.
PATTERN = re.compile(
    r"^[ \t]*def\s+\w*(deflated_sharpe|probabilistic_sharpe)\w*\s*\(",
    re.MULTILINE,
)

# A non-canonical def is tolerated only when its body calls the canonical
# kernel through the sanctioned loader. Anything else — including math
# copied inline — is an offender.
DELEGATION_MARKER = "_load_kernels"


def _python_files():
    stack = [REPO]
    while stack:
        directory = stack.pop()
        for entry in sorted(directory.iterdir()):
            rel = entry.relative_to(REPO)
            if entry.is_dir():
                if entry.name in PRUNE_DIRS:
                    continue
                if any(rel == p or p in rel.parents for p in PRUNE_PREFIXES):
                    continue
                stack.append(entry)
            elif entry.suffix == ".py":
                yield entry, rel


def _def_body(text: str, start: int) -> str:
    """Source of the def starting at `start`, up to the next top-level
    (column-0) statement after the def line — enough scope to see whether
    it delegates."""
    line_end = text.find("\n", start)
    if line_end == -1:
        return text[start:]
    # Next top-level statement, not merely a column-0 character: a
    # multi-line signature puts its closing ") -> float:" at column 0, and
    # that must not terminate the scope before the body is seen.
    nxt = re.compile(r"^[A-Za-z_@]", re.MULTILINE)
    m = nxt.search(text, pos=line_end + 1)
    return text[start : m.start()] if m else text[start:]


def test_no_dsr_reimplementation_outside_canonical_copies():
    offenders = []
    for path, rel in _python_files():
        if rel in ALLOWED:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in PATTERN.finditer(text):
            body = _def_body(text, m.start())
            if DELEGATION_MARKER in body:
                continue  # thin wrapper over the canonical kernel — allowed
            line_no = text[: m.start()].count("\n") + 1
            offenders.append(f"{rel}:{line_no}: {m.group(0).strip()}")

    assert offenders == [], (
        "Rogue DSR/PSR definitions found outside the canonical "
        "services/*/app/sharpe_metrics.py copies (and not delegating via "
        "_load_kernels). Import the kernel; never re-implement it:\n  "
        + "\n  ".join(offenders)
    )


def test_canonical_copies_exist_and_define_the_kernel():
    """The gate above is meaningless if the allowlist rots: both canonical
    files must exist and actually define the kernel functions."""
    for rel in sorted(ALLOWED):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert PATTERN.search(text), f"{rel} no longer defines the DSR kernel"


def test_gate_catches_a_rogue_def(tmp_path):
    """Self-test of the detector on a synthetic rogue file: the pattern must
    hit a bare re-implementation and spare a delegating wrapper."""
    rogue = (
        "def deflated_sharpe(sr, n):\n"
        "    return sr * n  # fake math\n"
    )
    wrapper = (
        "def deflated_sharpe_wrapped(rets, n):\n"
        "    from killtests.offline_ensemble import _load_kernels\n"
        "    return _load_kernels()[\"deflated_sharpe_ratio\"](rets, n)\n"
    )
    hits = list(PATTERN.finditer(rogue + "\n\n" + wrapper))
    assert len(hits) == 2
    text = rogue + "\n\n" + wrapper
    verdicts = [DELEGATION_MARKER in _def_body(text, h.start()) for h in hits]
    assert verdicts == [False, True]
