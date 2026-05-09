# Phase 04: Tournament Significance & Auto-PR — Pattern Map

**Mapped:** 2026-05-09
**Files analyzed:** 12 new + 2 modified
**Analogs found:** 12 / 12 (one per new file plus two shared cross-cutting patterns)

## File Classification

### New files (Phase 4 creates)

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `services/tournament-harness/app/significance/__init__.py` | package marker | n/a | `services/tournament-harness/app/leaderboard/__init__.py` | exact |
| `services/tournament-harness/app/significance/ensemble.py` | service (selection + aggregation) | transform (snapshot rows → per-symbol top-3 + averaged log-returns) | `services/tournament-harness/app/runner/metrics_bridge.py` (imports-only-from-ml-retraining contract) + `services/tournament-harness/app/leaderboard/queries.py` (ALLOWED_FILTER_COLS / parse_where DSL) | role-match (transform-on-rows; no exact analog for ensemble construction yet) |
| `services/tournament-harness/app/significance/baseline.py` | utility (pure function) | transform (OOS bars → per-bar baseline log-returns array) | `services/ml-retraining-service/app/core/returns_metrics.py:compute_returns_metrics` (numpy/sklearn pure helper shape) | role-match |
| `services/tournament-harness/app/significance/bootstrap.py` | service (statistical kernel) | transform (paired return diffs → p-value + lifts) | `services/ml-retraining-service/app/cpcv.py:cpcv_to_dsr` (pure-numpy resampling kernel under `cpcv` library that Phase 4 imports rather than extends) | role-match |
| `services/tournament-harness/app/significance/win_gate.py` | utility (boolean gate) | transform (significance dict → per-symbol win bool) | `services/tournament-harness/app/orchestrator/ingest.py` (single-purpose dict→reason classifier) | role-match |
| `services/tournament-harness/app/significance/artifacts.py` | service (artifact writer) | file-I/O (atomic JSON / MD writes) | `services/tournament-harness/app/leaderboard/snapshot.py:export_snapshot` | exact (atomic write pattern) |
| `services/tournament-harness/app/pr/__init__.py` | package marker | n/a | `services/tournament-harness/app/leaderboard/__init__.py` | exact |
| `services/tournament-harness/app/pr/body.py` | utility (template renderer) | transform (significance + leaderboard rows → markdown body) | `services/tournament-harness/app/leaderboard/snapshot.py` (dict-build pattern) | role-match |
| `services/tournament-harness/app/pr/gh.py` | service (subprocess wrapper) | request-response (subprocess to `gh` CLI) | `services/tournament-harness/app/orchestrator/launcher.py:_git_sha,_git_is_dirty` (subprocess.check_output + clean error handling) | role-match |
| `services/tournament-harness/app/pr/reproduce.py` | service (orchestrator) | request-response (snapshot + git_sha → re-run pipeline + diff) | `services/tournament-harness/app/orchestrator/launcher.py:run_tournament` | role-match (calls back into launcher) |
| `services/tournament-harness/tests/integration/test_no_legacy_r2_criterion.py` | test (CI grep gate) | request-response (subprocess grep → assert empty) | `services/tournament-harness/tests/integration/test_tourn07_grep_gate.py` | exact |
| `services/tournament-harness/tests/integration/test_no_auto_merge.py` | test (CI grep gate) | request-response (subprocess grep → assert empty) | `services/tournament-harness/tests/integration/test_tourn07_grep_gate.py` | exact |
| `services/tournament-harness/tests/unit/test_significance_*.py` (one per module above) | test | unit | `services/tournament-harness/tests/unit/test_leaderboard_snapshot.py` | exact |
| `services/tournament-harness/tests/integration/test_reproduce_idempotent.py` | test (e2e) | request-response | `services/tournament-harness/tests/integration/test_end_to_end_tournament.py` | role-match |

### Modified files (Phase 4 extends)

| Modified File | Role | Data Flow | Pattern Source | Notes |
|---------------|------|-----------|----------------|-------|
| `services/tournament-harness/app/cli.py` | CLI dispatcher | request-response (argv → subcommand handler) | `services/tournament-harness/app/cli.py` (self-analog — extend in same shape) | Two new subcommands: `open-pr {tid}` and `reproduce {tid} --git-sha SHA`. Reuse `_setup_logging` and the `sub.add_parser → set_defaults(func=...)` shape verbatim. |
| `services/tournament-harness/tests/conftest.py` | test fixtures | n/a | `services/tournament-harness/tests/conftest.py` (self-analog) | May need a `synthetic_snapshot` fixture (mirrors `synthetic_klines` shape) for unit tests that need a snapshot dict input. |

---

## Pattern Assignments

### `services/tournament-harness/app/significance/artifacts.py` (artifact writer, file-I/O)

**Analog:** `services/tournament-harness/app/leaderboard/snapshot.py`

**Imports pattern** (lines 1-21 of analog):
```python
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)
```

**Atomic write pattern** (lines 65-87 of analog — copy verbatim per artifact, JSON path):
```python
out_path = Path(output_path)
out_path.parent.mkdir(parents=True, exist_ok=True)

# Atomic write (T-03-32)
fd, tmp_path = tempfile.mkstemp(
    prefix="snapshot.", suffix=".json.tmp", dir=str(out_path.parent)
)
try:
    with os.fdopen(fd, "w") as f:
        json.dump(snapshot, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, str(out_path))
    try:
        os.chmod(out_path, 0o644)
    except OSError:
        pass
except Exception:
    try:
        os.unlink(tmp_path)
    except OSError:
        pass
    raise
```

**For markdown output** (`{tournament_id}.leaderboard.md`): same shape, swap `json.dump(...)` for `f.write(markdown_text)`, swap prefix/suffix to `"leaderboard."` / `".md.tmp"`. Three artifacts → three calls to a shared `_atomic_write(path, payload, *, suffix)` helper in this file. **NEVER use `Path.write_text` here** — would defeat the atomic guarantee.

**Public API shape (mirror `export_snapshot`):**
```python
def write_ensemble(snapshot: Dict[str, Any], git_sha: str, output_path: str | os.PathLike) -> Dict[str, Any]: ...
def write_significance(ensemble: Dict[str, Any], significance_results: Dict[str, Any], git_sha: str, tournaments_evaluated_count: int, output_path: str | os.PathLike) -> Dict[str, Any]: ...
def write_leaderboard_markdown(snapshot: Dict[str, Any], significance: Dict[str, Any], output_path: str | os.PathLike) -> str: ...
```

Each returns the dict (or string) it wrote, mirroring `export_snapshot` returning the snapshot.

---

### `services/tournament-harness/app/significance/ensemble.py` (selection + aggregation)

**Analog (selection):** `services/tournament-harness/app/leaderboard/queries.py:run_query` for the safe filter pattern. Phase 4 ensemble selection works on the in-memory snapshot (`snapshot["rows"]`), NOT against SQLite — so it does NOT call `run_query`, but it MUST follow the same allowlist discipline (do not concatenate user input into Python attrgetters either).

**Selection pattern** — pure Python over `snapshot["rows"]`:
```python
from operator import itemgetter

# D-01: per-symbol top-3 by DSR, tie-break (cpcv_dsr, oos_sharpe, created_at asc).
def select_top_n_per_symbol(rows: list[dict], n: int = 3) -> dict[str, list[dict]]:
    successful = [r for r in rows if r.get("status") == "success"]
    by_symbol: dict[str, list[dict]] = {}
    for r in successful:
        by_symbol.setdefault(r["symbol"], []).append(r)
    selected: dict[str, list[dict]] = {}
    for symbol, srows in by_symbol.items():
        # Negate ascending tie-break field by sorting `created_at` ascending after the descending metrics.
        srows.sort(
            key=lambda r: (
                -float(r.get("dsr") or 0.0),
                -float(r.get("cpcv_dsr") or 0.0),
                -float(r.get("oos_sharpe") or 0.0),
                str(r.get("created_at") or ""),
            )
        )
        selected[symbol] = srows[:n]
    return selected
```

**Aggregation analog:** `services/tournament-harness/app/runner/metrics_bridge.py` (lines 14-28 — IMPORT pattern). Ensemble metric calls go through the bridge, NOT around it.

```python
# Canonical implementations — IMPORTED, not redefined (TOURN-07).
from app.core.returns_metrics import compute_returns_metrics  # noqa: F401
from app.core.cpcv_evaluation import evaluate_with_cpcv  # noqa: F401
from app.sharpe_metrics import (  # noqa: F401
    probabilistic_sharpe_ratio,
    deflated_sharpe_ratio,
)
from app.cpcv import cpcv_to_dsr  # noqa: F401
```

`compute_returns_metrics` signature for the planner:
```python
compute_returns_metrics(
    actual_prices: np.ndarray,   # shape (N,)
    pred_prices:   np.ndarray,   # shape (N,)
    last_close:    np.ndarray,   # shape (N,)
    dataset_name:  str,          # e.g. "ensemble"
) -> Dict[str, float]
# Returns {f"{dataset_name}_r2_returns": ..., f"{dataset_name}_dir_acc_corrected": ...}
```

For ensemble Sharpe: convert averaged log-returns to per-bar returns and pass to `probabilistic_sharpe_ratio(returns, benchmark_sr=0.0)` (signature at `services/ml-retraining-service/app/sharpe_metrics.py:148`). Re-use the same prefix-strip pattern from `metrics_bridge.compute_all_metrics` (lines 73-81) when consuming `compute_returns_metrics` output.

---

### `services/tournament-harness/app/significance/baseline.py` (persistence reference)

**Analog:** `services/ml-retraining-service/app/core/returns_metrics.py` — the load-bearing comment on line 7 ("a persistence baseline gets the same number") is the entire rationale for D-04.

**Pattern:** pure-numpy helper, no class, no I/O.
```python
from __future__ import annotations
import numpy as np

def persistence_log_returns(n_oos_bars: int) -> np.ndarray:
    """Persistence baseline: predict next-bar close = current close → log-return = 0.

    Returns an all-zeros array of shape (n_oos_bars,). Kept as a function (not
    a constant) so future Phase-5 baselines (production-aggregator) can swap in
    without changing call sites.
    """
    return np.zeros(int(n_oos_bars), dtype=float)
```

**Why a function and not `np.zeros(N)` inline:** `significance.json` already carries `baseline: "persistence"` (D-14) so a future swap to `production_aggregator_log_returns(...)` keeps the call site stable.

---

### `services/tournament-harness/app/significance/bootstrap.py` (block bootstrap kernel)

**Analog:** `services/ml-retraining-service/app/cpcv.py` — Phase 4 imports `cpcv_to_dsr` but does NOT extend `cpcv.py` itself (D-07: "tournament-specific concern stays in tournament-harness").

**Pattern:** pure-numpy paired stationary block bootstrap. Imports + signature shape:
```python
from __future__ import annotations

import hashlib
from typing import Dict

import numpy as np

# D-05: stationary block (Politis-Romano), one-tailed (D-06), additive smoothing.
def stationary_block_bootstrap_pvalue(
    paired_diffs: np.ndarray,       # d_t = ensemble_log_ret_t - baseline_log_ret_t
    *,
    metric_fn,                      # callable: (returns_array) -> float (e.g. lambda r: r.mean()/r.std(ddof=1))
    n_resamples: int = 10_000,
    seed: int,                      # CD-07: tournament-id-derived
) -> Dict[str, float]:
    """Returns {observed_metric, p_value, lift, n_oos_bars, block_size}."""
    n = len(paired_diffs)
    block_size = max(2, int(np.floor(np.sqrt(n))))
    rng = np.random.default_rng(seed)
    # ... resample loop, additive-smoothed p = (1 + count(stat <= 0)) / (n_resamples + 1) ...
```

**RNG seed pattern (CD-07):**
```python
def derive_seed(tournament_id: str, symbol: str) -> int:
    digest = hashlib.blake2b(
        f"{tournament_id}|sig|{symbol}".encode(), digest_size=8
    ).hexdigest()
    return int(digest, 16) & 0x7FFFFFFF
```

Stamped into `significance.json[per_symbol][SYM]["bootstrap_seed"]` per D-14.

---

### `services/tournament-harness/app/significance/win_gate.py` (per-symbol win classifier)

**Analog:** `services/tournament-harness/app/orchestrator/ingest.py` (single-purpose dict-classifier returning a string reason). Not read in detail above — the planner can mirror its shape: pure function, no I/O, returns structured result.

**Public API:**
```python
from typing import Dict

def evaluate_win_gate(per_symbol_significance: Dict[str, Dict]) -> Dict[str, Dict]:
    """D-08: all four conditions per symbol — both p-values < 0.05 AND both raw lifts > 0.

    Returns dict augmenting per-symbol entries with `win_gate_passed: bool`,
    `n_winning_symbols`, and `gate_failure_reasons: dict[symbol, list[str]]`.
    """
    out = {}
    n_wins = 0
    for sym, sig in per_symbol_significance.items():
        passed = (
            sig.get("sharpe_pvalue", 1.0) < 0.05
            and sig.get("dir_acc_pvalue", 1.0) < 0.05
            and sig.get("sharpe_lift", 0.0) > 0
            and sig.get("dir_acc_lift", 0.0) > 0
            and sig.get("n_members", 0) >= 3   # CD-08: insufficient-runs guard
        )
        out[sym] = {**sig, "win_gate_passed": passed}
        if passed:
            n_wins += 1
    return {"per_symbol": out, "n_winning_symbols": n_wins}
```

---

### `services/tournament-harness/app/pr/gh.py` (gh CLI wrapper)

**Analog:** `services/tournament-harness/app/orchestrator/launcher.py:_git_sha,_git_is_dirty` (lines 34-51). Same `subprocess.check_output` + try/except idiom; same "log warning, return sentinel" failure mode for soft-fail paths, hard-fail (raise) for required ops.

**Pattern (mirror lines 34-51):**
```python
import logging
import os
import subprocess
from typing import Sequence

logger = logging.getLogger(__name__)

def _check_gh_installed() -> None:
    """CD-09: hard-fail with exit 2 if gh missing."""
    try:
        subprocess.check_output(["gh", "--version"], stderr=subprocess.STDOUT)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        raise SystemExit(
            "gh CLI not found on PATH. Install: https://cli.github.com/  "
            f"(underlying error: {e})"
        )  # exit 2 via SystemExit(int) is fine, but D-11 specifies exit 2 — use sys.exit(2)

def _check_gh_token() -> None:
    """D-11: hard-fail with exit 2 if GH_TOKEN unset."""
    if not os.environ.get("GH_TOKEN"):
        raise SystemExit("GH_TOKEN env var not set — refusing to invoke gh pr create. "
                         "(D-11: missing PR after winning tournament is the worst silent failure.)")
```

**`gh pr create` invocation pattern:**
```python
def open_draft_pr(
    *,
    title: str,
    body: str,
    head: str,         # branch (CD-02: tournament/{tournament_id})
    base: str = "main",
    labels: Sequence[str] = ("tournament", "evaluation-gate"),
    dry_run: bool = False,
) -> str:
    """Returns the PR URL on success. dry_run=True writes inputs to stdout, no gh call."""
    cmd = [
        "gh", "pr", "create", "--draft",
        "--title", title,
        "--body", body,
        "--head", head,
        "--base", base,
    ]
    for label in labels:
        cmd += ["--label", label]
    if dry_run:
        logger.info("dry-run gh pr create: %s", cmd)
        return "(dry-run)"
    # NEVER log GH_TOKEN; subprocess inherits env which is fine (no need to forward explicitly).
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"gh pr create failed: rc={result.returncode} stderr={result.stderr}")
    return result.stdout.strip()
```

**Hard rule (CD-10):** this file MUST NOT contain the literal `gh pr merge` anywhere — `test_no_auto_merge.py` greps for it.

---

### `services/tournament-harness/app/pr/body.py` (PR body templating)

No direct analog — closest is `snapshot.py`'s dict-build pattern. Pure function: takes (snapshot, ensemble, significance, tournaments_evaluated_count, leaderboard_markdown) → returns string.

**Length guard (CD-12):**
```python
MAX_BODY_CHARS = 60_000  # GitHub limit ~65k

def render_pr_body(*, snapshot, ensemble, significance, tournaments_evaluated_count, leaderboard_markdown_path: str, leaderboard_markdown: str) -> str:
    body = _render_full(...)
    if len(body) > MAX_BODY_CHARS:
        body = _render_summary_with_link(leaderboard_markdown_path, ...)
    return body
```

PR title format (CD-01): single-line f-string, ≤90 chars. Truncate `tournament_id` to 12 chars if needed:
```python
short_tid = tournament_id[:12]
title = f"Tournament {short_tid}: ensemble wins {n_winning_symbols}/{n_total_symbols} symbols (p<0.05 vs persistence)"
```

---

### `services/tournament-harness/app/pr/reproduce.py` (reproducer entry)

**Analog:** `services/tournament-harness/app/orchestrator/launcher.py:run_tournament` (lines 188-298). Reuses the same dirty-tree refusal pattern (lines 204-208) and git-sha capture (line 234), plus calls back into the launcher.

**Hard-fail pattern (D-12 conditions 1+2):**
```python
def reproduce(tournament_id: str, *, git_sha_expected: str) -> int:
    if _git_is_dirty():
        raise SystemExit(
            "git tree is dirty — `reproduce` REFUSES (no --allow-dirty here; "
            "reproducibility is the whole point)."
        )  # exit 3
    head = _git_sha()
    if head != git_sha_expected:
        raise SystemExit(
            f"HEAD ({head}) != requested git_sha ({git_sha_expected}). "
            "Run: git checkout {git_sha_expected}"
        )  # exit 3
    # ... CD-06: build temp SQLite under data/leaderboard/reproduce_{tid}.db ...
    # ... call run_tournament with the snapshot's recovered yaml + same tid ...
    # ... re-run open-pr in --dry-run mode ...
    # ... diff significance.json — exit 4 if outside FP-noise tolerance ...
```

Reuse `_git_sha` and `_git_is_dirty` by import from `app.orchestrator.launcher`, NOT by duplication.

---

### `services/tournament-harness/app/cli.py` (modify — extend existing)

**Self-analog:** `services/tournament-harness/app/cli.py` (lines 81-119). Two new subcommands follow the exact same shape:

```python
# After the existing p_snap block in build_parser():
p_pr = sub.add_parser("open-pr", help="Build ensemble + significance + draft PR for a tournament")
p_pr.add_argument("tournament_id")
p_pr.add_argument("--allow-dirty", action="store_true", help="Allow dirty tree (mirrors `tournament run`)")
p_pr.add_argument("--dry-run", action="store_true", help="Write artifacts but do NOT invoke gh pr create")
p_pr.set_defaults(func=cmd_open_pr)

p_repro = sub.add_parser("reproduce", help="Re-derive significance from snapshot at the same git_sha")
p_repro.add_argument("tournament_id")
p_repro.add_argument("--git-sha", required=True, help="Expected HEAD; refuses if HEAD doesn't match")
p_repro.add_argument("--force", action="store_true", help="Drop existing tournament_id row before re-running")
p_repro.set_defaults(func=cmd_reproduce)
```

Handler functions follow the `cmd_run` / `cmd_export_snapshot` shape (lines 34-78): lazy import the implementation module inside the handler; call it; print a JSON summary to stdout; return int exit code.

---

### `services/tournament-harness/tests/integration/test_no_legacy_r2_criterion.py` (R² grep gate)

**Analog:** `services/tournament-harness/tests/integration/test_tourn07_grep_gate.py` — the canonical Phase 3 grep-gate-as-pytest. **Mirror its shape exactly.**

**Imports + path discovery** (lines 12-20 of analog):
```python
import re
import subprocess
from pathlib import Path

import pytest

# Find services/tournament-harness from the test file location.
HARNESS_ROOT = Path(__file__).resolve().parents[2]
```

**Two-test pattern** (file already proves the convention — copy it):
1. `test_no_metric_definitions_in_production_code` — Python-side regex over `HARNESS_ROOT.rglob("*.py")` with `if "/tests/" in str(py.as_posix()): continue` skip. Build a list of (path, line_no, snippet) triples and assert `matches == []`.
2. `test_grep_command_from_roadmap_returns_zero` — run the literal `grep` command via `subprocess.run(...)`, filter `/tests/` from stdout, assert `output_lines == []`.

**Patterns to grep for (D-13):**
```python
PATTERNS = [
    r">\s*5\s*%",
    r"5\s*percent\s*R[²2]",
    r"r2[_\s]*returns?\s*>\s*0\.0?5",
    r"R[²2]\s*>\s*0?\.0?5",
]
LITERAL_STRINGS = ["5% R2", "5% R²", "five percent R"]
SCAN_DIRS = [
    "services/tournament-harness/app/",
    "services/tournament-harness/tests/",   # but skip THIS file (allowlist self)
    ".github/workflows/",                    # tournament*.yml only
]
```

Self-exclusion: this test file references the patterns it's grepping for, so it must allowlist itself OR put the patterns in a sibling `_patterns.py` constants file imported here (cleaner — copy the analog's strategy of putting test-data outside the test body).

---

### `services/tournament-harness/tests/integration/test_no_auto_merge.py` (gh-pr-merge grep gate)

**Analog:** `services/tournament-harness/tests/integration/test_tourn07_grep_gate.py` — same shape as above.

**Pattern (CD-10):**
```python
PATTERN = r"gh\s+pr\s+merge"
SCAN_DIRS = [
    "services/tournament-harness/",
    ".github/workflows/",
]

def test_no_auto_merge_invocation():
    cmd = ["grep", "-rEn", PATTERN, *[str(HARNESS_ROOT.parent.parent / d) for d in SCAN_DIRS]]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # Self-exclude this file (it contains the literal pattern in a string).
    output_lines = [
        ln for ln in result.stdout.splitlines()
        if "/tests/integration/test_no_auto_merge.py" not in ln
        and "/tests/" not in ln  # exclude all tests by the same convention as TOURN-07
    ]
    assert output_lines == [], "auto-merge invocation found:\n" + "\n".join(output_lines)
```

---

### `services/tournament-harness/tests/unit/test_significance_*.py` (per-module unit tests)

**Analog:** `services/tournament-harness/tests/unit/test_leaderboard_snapshot.py`

**Imports + tmp_path pattern** (lines 1-13):
```python
import json
from pathlib import Path

import pytest

from app.significance.bootstrap import stationary_block_bootstrap_pvalue
# (or whichever module under test)
```

**Atomic write verification** (lines 69-79 of analog — copy for `test_artifacts_writes_atomically`):
```python
def test_write_significance_atomic(tmp_path):
    out = tmp_path / "t1.significance.json"
    write_significance(...)
    leftovers = list(tmp_path.glob("*.json.tmp"))
    assert leftovers == []
```

---

## Shared Patterns

### Atomic file write
**Source:** `services/tournament-harness/app/leaderboard/snapshot.py` lines 65-87
**Apply to:** `app/significance/artifacts.py` (3 artifacts), `app/pr/body.py` if it writes an MD file directly (it shouldn't — body.py returns a string; artifacts.py writes the leaderboard.md)

```python
fd, tmp_path = tempfile.mkstemp(prefix="...", suffix="...tmp", dir=str(out_path.parent))
try:
    with os.fdopen(fd, "w") as f:
        # write payload
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, str(out_path))
    try:
        os.chmod(out_path, 0o644)
    except OSError:
        pass
except Exception:
    try:
        os.unlink(tmp_path)
    except OSError:
        pass
    raise
```

### Subprocess with logged-warning fallback (soft-fail)
**Source:** `services/tournament-harness/app/orchestrator/launcher.py:_git_sha,_git_is_dirty` (lines 34-51)
**Apply to:** `app/pr/reproduce.py` (reuse by import — DO NOT duplicate)

```python
def _git_sha() -> str:
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd="/app").strip()
        return out.decode()
    except Exception as e:
        logger.warning("git_sha unavailable: %s", e)
        return "unknown"
```

### Subprocess with hard-fail (required ops)
**Source:** `services/tournament-harness/app/orchestrator/launcher.py` lines 204-208 (dirty-tree raise) + lines 217-221 (TIMESCALE_PASSWORD raise)
**Apply to:** `app/pr/gh.py` (`_check_gh_installed`, `_check_gh_token`), `app/pr/reproduce.py` (dirty-tree refusal — no --allow-dirty here)

```python
if not allow_dirty and _git_is_dirty():
    raise RuntimeError(
        "git tree is dirty — refusing to ... "
        "Commit or pass --allow-dirty if this is intentional."
    )
```

### Argparse subcommand
**Source:** `services/tournament-harness/app/cli.py` lines 85-117
**Apply to:** the two new subcommands `open-pr` and `reproduce` in the same file

```python
p_X = sub.add_parser("X", help="...")
p_X.add_argument("required_arg")
p_X.add_argument("--optional-flag", action="store_true")
p_X.set_defaults(func=cmd_X)

# Handler:
def cmd_X(args: argparse.Namespace) -> int:
    from app.X.module import implementation  # lazy import
    result = implementation(args.required_arg, optional=args.optional_flag)
    print(json.dumps(result, indent=2, default=str))
    return 0
```

### Imports-only-from-ml-retraining (TOURN-07)
**Source:** `services/tournament-harness/app/runner/metrics_bridge.py` lines 14-28
**Apply to:** `app/significance/ensemble.py` (Sharpe + dir_acc on averaged log-returns), `app/significance/bootstrap.py` (only the metric callable, not redefinitions)

```python
from app.core.returns_metrics import compute_returns_metrics  # noqa: F401
from app.sharpe_metrics import probabilistic_sharpe_ratio  # noqa: F401
```

**The grep gate (TOURN-07 + new R² grep gate D-13) means:** no `def directional_accuracy`, `def sharpe`, `def deflated`, and no R²-on-price-levels patterns ANYWHERE in `services/tournament-harness/app/`. Both gates run in the same nightly CI step.

### Test path-import shim (already present in conftest)
**Source:** `services/tournament-harness/tests/conftest.py` lines 17-29
**Apply to:** any new test that imports from `app.significance.*` or `app.pr.*` — the shim already covers them; no conftest changes needed for imports. Add only fixtures (e.g., `synthetic_snapshot` mirroring `synthetic_klines`).

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | | | Every Phase 4 file has at least a role-match analog within `services/tournament-harness/` or `services/ml-retraining-service/`. The bootstrap-test kernel itself has no precedent in this repo, but its pure-numpy/seeded shape mirrors `cpcv.cpcv_to_dsr` closely enough that the planner has a template. |

---

## Cross-Phase Contracts (load-bearing for the planner)

- **Phase 3 snapshot is the input contract** (`services/tournament-harness/app/leaderboard/snapshot.py` writes it; Phase 4 is read-only on it). Snapshot fields the planner must consume: `rows[*].run_id`, `rows[*].symbol`, `rows[*].dsr`, `rows[*].cpcv_dsr`, `rows[*].oos_sharpe`, `rows[*].status`, `rows[*].architecture`, `rows[*].hp_hash`, `rows[*].created_at`, `summary.symbols`, `config.config_yaml`, `config.git_sha`, `config.seed`, `tournament_id`, `schema_version`.
- **Reproducer (D-12)** calls `app.orchestrator.launcher.run_tournament` with the recovered YAML — that function already has `allow_dirty=False` default. Reproducer passes `allow_dirty=False` (refuses dirty per D-12).
- **`tournaments_evaluated_count`** (D-09) — single read query on the existing leaderboard SQLite. Use `LeaderboardDB(...).conn.execute("SELECT COUNT(DISTINCT tournament_id) FROM tournaments")`. Do NOT add a method to `LeaderboardDB` for this — the existing public surface is sufficient (`conn` attribute is already used externally; if a method is preferred for cleanliness, add a one-liner `count_tournaments() -> int` to `db.py` and have it return the int — minimal modification).

---

## Metadata

**Analog search scope:**
- `services/tournament-harness/app/` (full read of cli.py, snapshot.py, db.py, queries.py, launcher.py, metrics_bridge.py, conftest.py)
- `services/tournament-harness/tests/integration/test_tourn07_grep_gate.py` (full read — exact analog for both new grep gates)
- `services/tournament-harness/tests/unit/test_leaderboard_snapshot.py` (head — atomic write verification pattern)
- `services/ml-retraining-service/app/core/returns_metrics.py` (head — public function signature)
- `services/ml-retraining-service/app/sharpe_metrics.py` (PSR signature)
- `services/ml-retraining-service/app/cpcv.py` (cpcv_to_dsr signature)

**Files scanned:** ~10 source files + 4 test files (targeted reads only; no full-file re-reads)

**Pattern extraction date:** 2026-05-09
