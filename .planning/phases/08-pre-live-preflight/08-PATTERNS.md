# Phase 8: Pre-LIVE Preflight — Pattern Map

**Mapped:** 2026-05-16
**Files analyzed:** 15 (11 new + 4 modified)
**Analogs found:** 14 / 15 (one no-analog: CI workflow PR-label conditional)

> Consumed by `gsd-planner` for the Phase 8 plan set. Every "copy from" reference is a concrete file + line range to mirror — no abstract advice.

---

## File Classification

| New/Modified File | New? | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|------|-----------|----------------|---------------|
| `services/trading-engine/app/preflight/__init__.py` | NEW | package-marker | n/a | `services/trading-engine/app/lifespan/__init__.py` | exact (re-export shape) |
| `services/trading-engine/app/preflight/types.py` | NEW | model (dataclass) | transform | `services/trading-engine/app/handlers/risk_budget.py:44-83` (Pydantic response models) | role-match (dataclass instead of Pydantic — JSON-only) |
| `services/trading-engine/app/preflight/checks.py` | NEW | service (pure-fn) | request-response | `services/trading-engine/app/handlers/health.py:24-100` (gathers checks, returns dict) | role-match (no FastAPI dep — pure callable) |
| `services/trading-engine/app/handlers/preflight.py` *(new router file)* | NEW | route/controller | request-response | `services/trading-engine/app/handlers/risk_budget.py:36, 378-415` (router prefix + GET handler + try/except) | exact |
| `scripts/preflight_live.py` | NEW | CLI entry-point | batch / one-shot | `scripts/audit_tiles.py:1-310` (argparse + JSON output + exit-code semantics) | exact |
| `.github/workflows/preflight-live-readiness.yml` | NEW | CI workflow | event-driven | `.github/workflows/tournament-harness.yml:24-62` (two-job grep-gate + unit-tests structure) | role-match (no internal analog for PR-label conditional — see "No Analog Found") |
| `tests/integration/test_preflight_grep_gates.py` | NEW | test (grep gate) | static-scan | (a) `services/trading-engine/tests/test_lifespan.py:64-76` (inspect.getsource for import-survival gate #2); (b) `services/tournament-harness/tests/integration/test_tourn07_grep_gate.py:1-65` (subprocess grep gate #1) | exact for both halves |
| `services/trading-engine/tests/test_preflight_checks.py` | NEW | test (unit) | transform | `services/trading-engine/tests/test_monitoring_alerts.py:53-100` (monkeypatch.setenv + assert return) | exact |
| `services/trading-engine/tests/test_preflight_lifespan.py` | NEW | test (integration) | request-response | `services/trading-engine/tests/test_lifespan.py:13-76` (pytest.asyncio + inspect.getsource) | exact |
| `services/trading-engine/tests/test_preflight_route.py` | NEW | test (route) | request-response | `services/api-gateway/tests/test_safety_state.py:32-101` (JSONResponse mock + side_effect dispatcher) | exact |
| `services/api-gateway/tests/test_preflight_proxy.py` | NEW | test (route) | request-response | `services/api-gateway/tests/test_safety_state.py:104-end` (test_client + proxy mocking) | exact |
| `services/trading-engine/app/main.py` | MODIFY | lifespan + router-mount | startup | `services/trading-engine/app/main.py:243-258` (existing `LIVE_TRADING_ACK` block — extend, don't duplicate) | exact (in-file extension) |
| `services/api-gateway/app/main.py` | MODIFY | proxy route | request-response | `services/api-gateway/app/main.py:1049-1165` (`/api/config/safety-state` fan-out) | exact |
| `RUNBOOK.md` | MODIFY | docs | n/a | `RUNBOOK.md:21-42` (BuildKit hang Diagnose/Action/Verification template) | exact |
| `PROJECT.md` | MODIFY | docs | n/a | (cross-link only — one-line edit) | n/a |

---

## Pattern Assignments

### `services/trading-engine/app/preflight/__init__.py` (package marker)

**Analog:** `services/trading-engine/app/lifespan/__init__.py` (re-export pattern)

**Pattern to copy** — `from .checks import run_all, check_cap, check_paper_mode, ...` so callers do `from app.preflight import run_all` instead of `from app.preflight.checks import run_all`.

```python
# Mirror app/lifespan/__init__.py shape:
from app.preflight.checks import (
    run_all,
    check_cap,
    check_paper_mode,
    check_trading_mode,
    check_ack,
    check_emergency_stop,
    check_dsr_evidence,
)
from app.preflight.types import CheckResult, PreflightReport

__all__ = [
    "run_all",
    "check_cap",
    "check_paper_mode",
    "check_trading_mode",
    "check_ack",
    "check_emergency_stop",
    "check_dsr_evidence",
    "CheckResult",
    "PreflightReport",
]
```

**Why this exact shape:** Grep-gate #2 (`test_preflight_module_imports_at_lifespan`) asserts `from app.preflight import` appears in `services/trading-engine/app/main.py`. The re-export here is what makes that bare-package import legal. The existing `app.lifespan` package uses the identical pattern (see `services/trading-engine/app/main.py:151`: `from app.lifespan import init_data, init_ml, init_risk, init_strategy`).

---

### `services/trading-engine/app/preflight/types.py` (dataclasses)

**Analog:** `services/trading-engine/app/handlers/risk_budget.py:44-83` (Pydantic response models)

**Decision divergence from analog:** Use stdlib `@dataclass` + `dataclasses.asdict()` for JSON, NOT Pydantic. Rationale: the CLI must run without the trading-engine FastAPI deps installed (e.g. on a developer laptop running only `pytest tests/integration/test_preflight_grep_gates.py`); dataclasses have zero third-party deps. The HTTP route can `JSONResponse(asdict(report))`.

**Pattern to write:**

```python
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Literal

Status = Literal["PASS", "FAIL", "UNKNOWN"]

@dataclass(frozen=True)
class CheckResult:
    check: str
    status: Status
    detail: str

@dataclass(frozen=True)
class PreflightReport:
    overall: Status
    checks: list[CheckResult]
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    schema_version: int = 1

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        import json
        return json.dumps(asdict(self), indent=2)
```

**JSON shape pinned by `08-CONTEXT.md` lines 58-73** — schema_version + overall + evaluated_at + checks[]. The dashboard tile (Phase 10 DASHLIVE-01) reads this shape; do NOT change it without bumping `schema_version`.

---

### `services/trading-engine/app/preflight/checks.py` (per-check pure functions)

**Analog:** `services/trading-engine/app/handlers/health.py:24-100` (composes individual probes, returns aggregated dict)

**Imports pattern** (mirror health.py:1-22):

```python
"""
Preflight LIVE Readiness Checks (PREFLIGHT-01).

Pure functions — each returns a CheckResult. No FastAPI dependency.
Imported by:
  - services/trading-engine/app/handlers/preflight.py (HTTP route)
  - scripts/preflight_live.py (CLI entry point)

CRITICAL: keep this module dependency-free beyond stdlib + app.config +
sqlite3, so the CLI can run on a developer laptop without docker.
"""

import logging
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.config import get_settings
from app.preflight.types import CheckResult, PreflightReport

logger = logging.getLogger(__name__)
```

**Cap check pattern** (read `settings.max_risk_per_trade`, the field at `services/trading-engine/app/config.py:321`):

```python
def check_cap(settings=None) -> CheckResult:
    """Per-trade cap must be <= 0.02 (2%) in LIVE mode.

    PAPER skips the cap check by design (ADR-010 paper-relaxed 10%).
    """
    s = settings or get_settings()
    if s.trading_mode != "LIVE":
        return CheckResult(
            check="cap",
            status="PASS",
            detail=f"non-LIVE mode ({s.trading_mode}); cap check skipped per ADR-010",
        )
    if s.max_risk_per_trade > 0.02:
        return CheckResult(
            check="cap",
            status="FAIL",
            detail=f"max_risk_per_trade={s.max_risk_per_trade} > 0.02 (LIVE-strict)",
        )
    return CheckResult(
        check="cap",
        status="PASS",
        detail=f"max_risk_per_trade={s.max_risk_per_trade} <= 0.02",
    )
```

**EMERGENCY_STOP check — MUST use `.is_file()` not `.exists()`** (mirror `services/trading-engine/app/main.py:282-283`):

```python
def check_emergency_stop(settings=None) -> CheckResult:
    """EMERGENCY_STOP file must be absent.

    Uses .is_file() not .exists() to handle the WSL bind-mount edge case
    where Docker may create a *directory* at the mount point if the host
    file is absent (CLAUDE.md gotcha; see also main.py:282).
    """
    s = settings or get_settings()
    stop_file = Path(s.emergency_stop_file)
    if stop_file.is_file():
        return CheckResult(
            check="emergency_stop",
            status="FAIL",
            detail=f"file present at {stop_file}",
        )
    return CheckResult(
        check="emergency_stop",
        status="PASS",
        detail=f"no file at {stop_file}",
    )
```

**DSR-evidence check pattern** — read `leaderboard` table from tournament-harness sqlite (column at `services/tournament-harness/migrations/0001_initial.sql:23`):

```python
def check_dsr_evidence(db_path: str | None = None) -> CheckResult:
    """DSR > 0.95 row in the leaderboard table — best-effort in Phase 8.

    UNKNOWN if ML disabled, table empty/unreachable, or Phase 9's
    auto-flip marker (/run/mlgate_auto_flip.json) is absent.

    Phase 9 (MLGATE-01/02) owns the 14-day staleness rule and the
    psr_ci_published gate; Phase 8 reads the latest row and surfaces
    its DSR value only.
    """
    if os.environ.get("ENABLE_ML_PREDICTIONS", "false").lower() != "true":
        return CheckResult(
            check="dsr_evidence",
            status="PASS",
            detail="ML disabled (ENABLE_ML_PREDICTIONS=false); DSR check skipped",
        )
    if not Path("/run/mlgate_auto_flip.json").is_file():
        return CheckResult(
            check="dsr_evidence",
            status="UNKNOWN",
            detail="MLGATE-02 marker absent (Phase 9 not landed)",
        )
    # ... query SELECT dsr FROM leaderboard ORDER BY tournament_start_ts DESC LIMIT 1
```

**Aggregator pattern** (mirror `health.py:24` composing then returning):

```python
def run_all() -> PreflightReport:
    """Run all 6 checks. UNKNOWN/FAIL anywhere -> overall = FAIL (UNKNOWN
    is treated as not-PASS for the operator-blocking sense; the dashboard
    in Phase 10 renders UNKNOWN distinctly)."""
    checks = [
        check_cap(),
        check_paper_mode(),
        check_trading_mode(),
        check_ack(),
        check_emergency_stop(),
        check_dsr_evidence(),
    ]
    if any(c.status == "FAIL" for c in checks):
        overall = "FAIL"
    elif any(c.status == "UNKNOWN" for c in checks):
        overall = "UNKNOWN"
    else:
        overall = "PASS"
    return PreflightReport(overall=overall, checks=checks)
```

---

### `services/trading-engine/app/handlers/preflight.py` (HTTP route)

**Analog:** `services/trading-engine/app/handlers/risk_budget.py:36, 378-415` (router prefix + GET handler + try/except)

**Imports + router pattern** (mirror risk_budget.py:18-37):

```python
"""
Preflight LIVE-readiness HTTP route (PREFLIGHT-01).

Unauthenticated read-only (matches /api/config/safety-state per D-09).
Does NOT use admin_client / get_current_admin_user.
"""

import logging
from fastapi import APIRouter, HTTPException

from app.preflight import run_all

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/preflight", tags=["preflight"])


@router.get("/live-readiness")
async def get_live_readiness() -> dict:
    """Return per-check PASS/FAIL/UNKNOWN snapshot.

    Schema pinned at PreflightReport.schema_version=1.
    """
    try:
        report = run_all()
        return report.to_dict()
    except Exception as e:
        logger.error(f"Preflight live-readiness check failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Preflight check internal error: {e}",
        )
```

**Router-mount in main.py** (mirror existing pattern at `services/trading-engine/app/main.py:409-447`):

```python
# In services/trading-engine/app/main.py near line 447:
from app.handlers.preflight import router as preflight_router  # noqa: F401
app.include_router(preflight_router)
```

---

### `scripts/preflight_live.py` (CLI entry point)

**Analog:** `scripts/audit_tiles.py:1-310` (argparse + JSON output + tri-state exit code)

**Shebang + docstring** (mirror audit_tiles.py:1-29):

```python
#!/usr/bin/env python3
"""
Pre-LIVE Preflight CLI (PREFLIGHT-01).

Asserts the 6 LIVE preconditions and prints structured JSON per check.

Exits:
* 0 if overall == "PASS"
* 1 if overall == "FAIL" or "UNKNOWN"
* 2 on bad CLI args / unreachable config

Usage:
    python3 scripts/preflight_live.py                       # text output
    python3 scripts/preflight_live.py --json                # JSON output
    python3 scripts/preflight_live.py --check=cap           # single check
    python3 scripts/preflight_live.py --dry-run --target=HEAD  # CI variant
"""
```

**Argparse + main + exit pattern** (mirror audit_tiles.py:233-309):

```python
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

# Add services/trading-engine/app to sys.path so `from app.preflight import run_all`
# works without docker. Mirror the pattern at services/trading-engine/tests/unit/test_config.py:20-22.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "services" / "trading-engine"))

from app.preflight import run_all  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pre-LIVE Preflight CLI (PREFLIGHT-01)")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument("--check", default=None, help="Run only one check by name")
    parser.add_argument("--dry-run", action="store_true",
                        help="Read .env.example from --target ref instead of process env")
    parser.add_argument("--target", default=None,
                        help="git ref for --dry-run (e.g. HEAD, origin/main)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = run_all()  # or filter to args.check
    if args.json:
        print(report.to_json())
    else:
        for c in report.checks:
            print(f"  {c.status:8s}  {c.check:18s}  {c.detail}")
        print(f"\nOVERALL: {report.overall}")
    return 0 if report.overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
```

**Why this shape:** audit_tiles.py uses `sys.exit(0 if fails == 0 else 1)` at line 305; preflight_live.py mirrors it. The two-format output (text default + `--json` flag) is also from audit_tiles.py — no internal precedent for the `--dry-run --target=` flag pair, the planner picks shape during implementation.

---

### `.github/workflows/preflight-live-readiness.yml`

**Analog (overall structure):** `.github/workflows/tournament-harness.yml:24-62` (two-job: grep-gate then unit-tests)
**No internal analog:** the PR-label conditional (`contains(github.event.pull_request.labels.*.name, 'live: requested')`). Falls back to GitHub Actions docs; planner should reference `context7` for `actions/checkout` and the `pull_request.labels` event payload.

**Workflow trigger pattern** (mirror integration.yml:3-7):

```yaml
name: Preflight Live-Readiness Gate

on:
  pull_request:
    branches: [main, develop]

concurrency:
  group: preflight-${{ github.ref }}
  cancel-in-progress: true
```

**Two-job structure** (mirror tournament-harness.yml:25-62):

```yaml
jobs:
  unit-tests:
    name: Preflight unit tests (always)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install deps
        run: pip install -r services/trading-engine/requirements.txt
      - name: Run preflight tests
        run: |
          cd services/trading-engine
          pytest tests/test_preflight_*.py -v
      - name: Run grep gates
        run: pytest tests/integration/test_preflight_grep_gates.py -v

  gate:
    name: Live-readiness gate (labelled PRs only)
    needs: unit-tests
    if: contains(github.event.pull_request.labels.*.name, 'live: requested')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # required for --dry-run --target=HEAD to resolve .env.example
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Run preflight gate
        run: |
          python3 scripts/preflight_live.py --dry-run --target=HEAD --json
```

**Note:** The `if: contains(...labels...)` shape is GitHub Actions stdlib but unused in this repo. List as "external pattern" in the planner's research column.

---

### `tests/integration/test_preflight_grep_gates.py` (two grep gates)

**Analog (gate #1 — log-string scan):** `services/tournament-harness/tests/integration/test_tourn07_grep_gate.py:23-65`
**Analog (gate #2 — import-survival):** `services/trading-engine/tests/test_lifespan.py:64-76` (`test_lifespan_body_uses_async_with_phases`)

**Gate #1 pattern — `LIVE_PREFLIGHT_REJECTED` log emission must exist** (mirror tourn07 file):

```python
"""Phase 8 preflight grep gates (PREFLIGHT-02 defence-in-depth).

Two gates:
1. test_live_preflight_rejected_log_exists - grep -r "LIVE_PREFLIGHT_REJECTED"
   services/trading-engine/app/ must return >=1 match.
2. test_preflight_module_imports_at_lifespan - assert `from app.preflight`
   appears in services/trading-engine/app/main.py (autoflake-survival check).
"""

import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TE_APP = REPO_ROOT / "services" / "trading-engine" / "app"


def test_live_preflight_rejected_log_exists():
    """The LIVE_PREFLIGHT_REJECTED log emission must exist in production code
    (PREFLIGHT-02 success criterion #6 — silent removal blocked).

    Mirror tourn07 grep gate: pathlib scan + literal subprocess grep.
    """
    pattern = re.compile(r"LIVE_PREFLIGHT_REJECTED")
    matches = []
    for py in TE_APP.rglob("*.py"):
        if "/tests/" in py.as_posix():
            continue
        if pattern.search(py.read_text(errors="ignore")):
            matches.append(str(py.relative_to(REPO_ROOT)))
    assert matches, "LIVE_PREFLIGHT_REJECTED log emission removed from production code"

    # Fidelity to the literal CI grep command in the workflow file:
    result = subprocess.run(
        ["grep", "-r", "LIVE_PREFLIGHT_REJECTED", str(TE_APP)],
        capture_output=True, text=True,
    )
    assert result.stdout, "subprocess grep returned no matches"
```

**Gate #2 pattern — `from app.preflight` must appear in main.py** (mirror test_lifespan.py:64-76):

```python
def test_preflight_module_imports_at_lifespan():
    """The trading-engine boot path must import the preflight module so the
    cap-check block at main.py runs at lifespan startup.

    Defence against the metrics_bridge eager-import-swallowed-ImportError
    pattern flagged in v1.0 retrospective (CONTEXT.md "Grep gates" section).
    """
    import inspect
    import app.main as main_mod

    # Source-level guard - either the bare import OR the from-form is acceptable.
    src = inspect.getsource(main_mod)
    assert (
        "from app.preflight import" in src
        or "import app.preflight" in src
    ), "main.py must import app.preflight for cap-check enforcement"
```

**Why both shapes:** The `inspect.getsource` form catches the autoflake regression (test_lifespan.py's exact use case at line 64); the subprocess grep form gives CI fidelity to the literal command operators run.

---

### `services/trading-engine/tests/test_preflight_checks.py` (per-check unit tests)

**Analog:** `services/trading-engine/tests/test_monitoring_alerts.py:57-100` (monkeypatch.setenv + AsyncMock)

**Pydantic Settings override pattern** — pass kwargs directly to `Settings()`, no env var roundtrip needed:

```python
"""Unit tests for app.preflight.checks - each check tests PASS + FAIL + UNKNOWN."""
import pytest
from pathlib import Path

from app.config import Settings
from app.preflight.checks import (
    check_cap, check_paper_mode, check_trading_mode,
    check_ack, check_emergency_stop, check_dsr_evidence,
)


def test_check_cap_paper_allows_10pct():
    """PAPER mode skips the cap check per ADR-010 (10% allowed)."""
    settings = Settings(trading_mode="PAPER", max_risk_per_trade=0.10)
    result = check_cap(settings)
    assert result.status == "PASS"
    assert "non-LIVE mode" in result.detail or "skipped" in result.detail


def test_check_cap_live_rejects_3pct():
    """LIVE mode with cap > 2% must FAIL (PREFLIGHT-02 unit-test contract)."""
    settings = Settings(trading_mode="LIVE", max_risk_per_trade=0.03)
    result = check_cap(settings)
    assert result.status == "FAIL"
    assert "0.03" in result.detail
    assert "0.02" in result.detail


def test_check_cap_live_accepts_2pct():
    """LIVE mode with cap == 2% must PASS."""
    settings = Settings(trading_mode="LIVE", max_risk_per_trade=0.02)
    result = check_cap(settings)
    assert result.status == "PASS"


def test_check_ack_present(monkeypatch):
    """LIVE_TRADING_ACK with correct sentinel must PASS in LIVE mode."""
    monkeypatch.setenv("LIVE_TRADING_ACK", "I_UNDERSTAND_REAL_MONEY")
    settings = Settings(trading_mode="LIVE")
    result = check_ack(settings)
    assert result.status == "PASS"


def test_check_emergency_stop_file_present(tmp_path, monkeypatch):
    """EMERGENCY_STOP file must trigger FAIL."""
    stop_file = tmp_path / "EMERGENCY_STOP"
    stop_file.write_text("")
    settings = Settings(emergency_stop_file=str(stop_file))
    result = check_emergency_stop(settings)
    assert result.status == "FAIL"


def test_check_emergency_stop_directory_at_path_is_not_file(tmp_path):
    """WSL bind-mount edge case: dir at the path must NOT trigger FAIL
    (.is_file() rejects directories; .exists() would falsely trip)."""
    (tmp_path / "EMERGENCY_STOP").mkdir()
    settings = Settings(emergency_stop_file=str(tmp_path / "EMERGENCY_STOP"))
    result = check_emergency_stop(settings)
    assert result.status == "PASS"  # is_file() returns False for directories


def test_check_dsr_evidence_ml_disabled_passes(monkeypatch):
    """ENABLE_ML_PREDICTIONS=false short-circuits to PASS."""
    monkeypatch.setenv("ENABLE_ML_PREDICTIONS", "false")
    result = check_dsr_evidence()
    assert result.status == "PASS"
    assert "ML disabled" in result.detail


def test_check_dsr_evidence_ml_enabled_no_marker_is_unknown(monkeypatch):
    """ML on but Phase 9 marker absent -> UNKNOWN per CONTEXT.md decision."""
    monkeypatch.setenv("ENABLE_ML_PREDICTIONS", "true")
    monkeypatch.setattr("pathlib.Path.is_file", lambda self: False)
    result = check_dsr_evidence()
    assert result.status == "UNKNOWN"
```

---

### `services/trading-engine/tests/test_preflight_lifespan.py` (boot-rejection integration)

**Analog:** `services/trading-engine/tests/test_lifespan.py:13-76` (pytest.asyncio + inspect.getsource)

**Two test patterns:**

```python
"""Lifespan integration: the LIVE+cap>2% boot must be rejected."""
import os
import inspect
import pytest


def test_lifespan_source_contains_cap_check():
    """Source-level guard - the cap-check block must live next to the
    LIVE_TRADING_ACK check (CONTEXT.md "Per-trade cap enforcement point").

    Mirror test_lifespan_body_uses_async_with_phases pattern in test_lifespan.py:64.
    """
    import app.main as main_mod
    src = inspect.getsource(main_mod.lifespan)
    assert "LIVE_PREFLIGHT_REJECTED" in src
    assert "max_risk_per_trade" in src
    assert "0.02" in src  # the LIVE-strict cap as a literal


@pytest.mark.asyncio
async def test_lifespan_rejects_live_with_high_cap(monkeypatch):
    """LIVE + MAX_RISK_PER_TRADE=0.03 + ACK present must raise RuntimeError."""
    monkeypatch.setenv("TRADING_MODE", "LIVE")
    monkeypatch.setenv("MAX_RISK_PER_TRADE", "0.03")
    monkeypatch.setenv("LIVE_TRADING_ACK", "I_UNDERSTAND_REAL_MONEY")

    # Force settings reload to pick up monkeypatched env
    from app.config import reload_settings
    reload_settings()

    from app.main import lifespan
    from fastapi import FastAPI
    fake_app = FastAPI()
    with pytest.raises(RuntimeError, match="max_risk_per_trade.*0.03.*0.02"):
        async with lifespan(fake_app):
            pass
```

---

### `services/trading-engine/tests/test_preflight_route.py` (HTTP route test)

**Analog:** `services/trading-engine/tests/test_main.py:27-31` (TestClient on `app`)

**Use plain `TestClient(app)` — unauthenticated route per D-09:**

```python
"""Tests for GET /api/preflight/live-readiness route (trading-engine side).

Unauthenticated per CONTEXT.md (matches /api/config/safety-state D-09 pattern).
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_route_returns_schema_v1(client):
    resp = client.get("/api/preflight/live-readiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["schema_version"] == 1
    assert body["overall"] in {"PASS", "FAIL", "UNKNOWN"}
    assert isinstance(body["checks"], list)
    assert len(body["checks"]) == 6

    # Every check has the same shape (dashboard tile Phase 10 relies on this)
    check_names = {c["check"] for c in body["checks"]}
    assert check_names == {
        "cap", "paper_mode", "trading_mode",
        "ack", "emergency_stop", "dsr_evidence",
    }
    for c in body["checks"]:
        assert set(c.keys()) >= {"check", "status", "detail"}
        assert c["status"] in {"PASS", "FAIL", "UNKNOWN"}
```

---

### `services/api-gateway/tests/test_preflight_proxy.py` (gateway proxy test)

**Analog:** `services/api-gateway/tests/test_safety_state.py:32-101` (JSONResponse mock + route-dispatching side_effect)

**Use `test_client` NOT `admin_client`** — endpoint is unauthenticated read-only:

```python
"""Tests for api-gateway GET /api/preflight/live-readiness proxy route.

Unauthenticated per CONTEXT.md (D-09 pattern from safety-state).
Uses test_client (NOT admin_client) - the proxy route has no auth dep.
"""
import json
import pytest
from unittest.mock import patch
from fastapi.responses import JSONResponse


def _build_response(content, status_code=200):
    """Mimic ServiceProxy.proxy_request() - JSONResponse with populated .body.
    Mirror services/api-gateway/tests/test_safety_state.py:32-40."""
    r = JSONResponse(content=content, status_code=status_code)
    r.body = json.dumps(content).encode()
    return r


@pytest.fixture
def mock_proxy(mock_service_proxy):
    with patch("app.main.get_proxy", return_value=mock_service_proxy):
        yield mock_service_proxy


def _trading_engine_route(payload):
    async def _se(service_name, path, method="GET", **kwargs):
        assert service_name == "trading-engine"
        assert path == "/api/preflight/live-readiness"
        return _build_response(payload)
    return _se


def test_proxy_passes_through_preflight_report(test_client, mock_proxy):
    """Happy path - report from trading-engine is surfaced verbatim."""
    payload = {
        "schema_version": 1,
        "overall": "PASS",
        "evaluated_at": "2026-05-16T14:32:01Z",
        "checks": [
            {"check": "cap", "status": "PASS", "detail": "..."},
            {"check": "paper_mode", "status": "PASS", "detail": "..."},
            {"check": "trading_mode", "status": "PASS", "detail": "..."},
            {"check": "ack", "status": "PASS", "detail": "..."},
            {"check": "emergency_stop", "status": "PASS", "detail": "..."},
            {"check": "dsr_evidence", "status": "UNKNOWN", "detail": "..."},
        ],
    }
    mock_proxy.proxy_request.side_effect = _trading_engine_route(payload)
    resp = test_client.get("/api/preflight/live-readiness")
    assert resp.status_code == 200
    assert resp.json()["overall"] == "PASS"


def test_proxy_returns_unknown_when_trading_engine_unreachable(test_client, mock_proxy):
    """Graceful degradation - trading-engine down -> overall=UNKNOWN.

    Mirror safety-state pattern: never 500, return safe defaults.
    The unauthenticated-preflight endpoint MUST NOT fall back to PASS;
    UNKNOWN is the safe default (CONTEXT.md Open Question close).
    """
    async def _raise(*_, **__):
        raise Exception("connection refused")
    mock_proxy.proxy_request.side_effect = _raise
    resp = test_client.get("/api/preflight/live-readiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall"] == "UNKNOWN"
    assert all(c["status"] == "UNKNOWN" for c in body["checks"])
```

---

### `services/trading-engine/app/main.py` (MODIFY — add cap-check block)

**Existing analog (extend in place):** lines 243-258 (`LIVE_TRADING_ACK` block)

**Exact insertion point** — at line 259 (right after `logger.critical("LIVE trading mode acknowledged...")`):

```python
    # ... existing lines 243-258 (LIVE_TRADING_ACK check) ...
    if settings.trading_mode == "LIVE":
        ack = os.environ.get("LIVE_TRADING_ACK", "")
        if ack != "I_UNDERSTAND_REAL_MONEY":
            raise RuntimeError(
                "Refusing to boot: TRADING_MODE=LIVE without "
                "LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY. "
                "Set the ack env var explicitly to authorize live trading."
            )
        logger.critical("LIVE trading mode acknowledged via LIVE_TRADING_ACK")

        # >>> NEW Phase 8 block — PREFLIGHT-02 cap-strictness gate <<<
        if settings.max_risk_per_trade > 0.02:
            logger.critical(
                "LIVE_PREFLIGHT_REJECTED reason=cap_too_high "
                f"cap={settings.max_risk_per_trade} limit=0.02"
            )
            raise RuntimeError(
                f"Refusing to boot: TRADING_MODE=LIVE with "
                f"max_risk_per_trade={settings.max_risk_per_trade} > 0.02. "
                "Restore the LIVE-strict cap before flipping the mode."
            )
        logger.info(
            f"LIVE preflight cap check passed: max_risk_per_trade="
            f"{settings.max_risk_per_trade} <= 0.02"
        )
        # <<< END Phase 8 block >>>
```

**Router-mount addition** — at line 447 (last `app.include_router(...)`):

```python
# Phase 8 PREFLIGHT-01 - LIVE-readiness preflight route (unauthenticated read-only).
from app.handlers.preflight import router as preflight_router  # noqa: E402
app.include_router(preflight_router)
```

**Import addition near top of main.py** (mirror existing F401 pattern at line 157):

```python
# Phase 8 PREFLIGHT-02 import-survival - grep gate #2 asserts this stays.
from app.preflight import run_all  # noqa: F401
```

The `noqa: F401` is **load-bearing** — without it, autoflake strips the import on the next `make format` and grep gate #2 fails. See project memory `feedback_main_imports_autoflake.md`.

---

### `services/api-gateway/app/main.py` (MODIFY — add proxy route)

**Analog:** lines 1049-1165 (`/api/config/safety-state` fan-out)

**Insertion point** — immediately after line 1165 (end of `get_safety_state` return), before the tournament-snapshots block at line 1168:

```python
@app.get("/api/preflight/live-readiness")
async def get_preflight_live_readiness():
    """
    Pre-LIVE preflight snapshot (Phase 8 PREFLIGHT-01).

    Unauthenticated read-only (D-09 carryforward from /api/config/safety-state).
    Thin proxy to trading-engine - the check logic owns runtime env (D-10:
    only trading-engine reads MAX_RISK_PER_TRADE / LIVE_TRADING_ACK).

    Graceful degradation: trading-engine unreachable -> all 6 checks UNKNOWN,
    overall=UNKNOWN. Never falls back to PASS (CONTEXT.md Open Question close).

    Schema pinned at v1 - matches PreflightReport.to_dict().
    """
    # Local import (autoflake-survival - project memory
    # feedback_main_imports_autoflake.md; mirror line 1155 + 1209 pattern).
    from datetime import datetime, timezone as _tz
    import json

    proxy = get_proxy()
    try:
        resp = await proxy.proxy_request(
            service_name="trading-engine",
            path="/api/preflight/live-readiness",
            method="GET",
        )
        if getattr(resp, "status_code", 500) == 200:
            return json.loads(resp.body.decode())
        raise Exception(f"trading-engine returned {resp.status_code}")
    except Exception as e:
        logger.warning(
            f"/api/preflight/live-readiness: trading-engine proxy failed: {e}"
        )
        return {
            "schema_version": 1,
            "overall": "UNKNOWN",
            "evaluated_at": datetime.now(_tz.utc).isoformat(),
            "checks": [
                {"check": name, "status": "UNKNOWN",
                 "detail": "trading-engine unreachable"}
                for name in ("cap", "paper_mode", "trading_mode",
                             "ack", "emergency_stop", "dsr_evidence")
            ],
        }
```

**Critical excerpts to mirror from safety-state:**
- **Lines 1093-1104** — `try/except` around proxy call, `json.loads(resp.body.decode())` (NOT `.json()` — proxy returns JSONResponse not dict, F-03 fix at line 1081 docstring).
- **Lines 1066-1067** — "Unauthenticated (D-09): read-only config disclosure. No secrets, no balances, no positions." — copy docstring tone.
- **Lines 1069-1073** — "Graceful degradation: 200 with safe defaults". Preflight's safe default is `UNKNOWN` everywhere, NOT `PASS`.
- **Line 1155** — `from datetime import timezone as _tz` (autoflake-survival local import).

---

### `RUNBOOK.md` (MODIFY — append Pre-LIVE Operator Checklist section)

**Analog:** any of the 6 existing symptom sections, e.g. `RUNBOOK.md:21-42` (BuildKit hang)

**Format pattern** (mirror exactly):

```markdown
## Pre-LIVE Operator Checklist

Before flipping `TRADING_MODE=LIVE`, work through each of the 6 preconditions.
Each row pairs with a `preflight_live.py` check ID; the dashboard tile
(Phase 10) renders the same 6 rows.

### Precondition 1: Per-trade cap <= 2% (LIVE-strict)

**Diagnose:**
- `python3 scripts/preflight_live.py --check=cap --json` — reports `status: "FAIL"` if `MAX_RISK_PER_TRADE > 0.02` in the current env.
- `grep MAX_RISK_PER_TRADE .env` — shows the current setting (default 0.10 per ADR-010 paper-relaxed).
- `docker logs trading-engine | grep "LIVE_PREFLIGHT_REJECTED reason=cap_too_high"` — if the container failed to start, this is the line.

**Action:**
\`\`\`bash
# Edit .env to restore LIVE-strict cap
sed -i 's/^MAX_RISK_PER_TRADE=.*/MAX_RISK_PER_TRADE=0.02/' .env

# Verify
grep MAX_RISK_PER_TRADE .env  # expect: MAX_RISK_PER_TRADE=0.02
\`\`\`

**Verification:**
- `python3 scripts/preflight_live.py --check=cap` exits 0.
- Re-running `docker compose up trading-engine` reaches "LIVE preflight cap check passed" log line.

### Precondition 2: PAPER_TRADING_MODE=false
... (same Diagnose/Action/Verification structure for each of the 6 checks)

### Precondition 3: TRADING_MODE=LIVE
### Precondition 4: LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY
### Precondition 5: EMERGENCY_STOP file absent
### Precondition 6: DSR > 0.95 evidence row (if ML enabled)
```

**Anchor placement** — after line 165 (after the EMERGENCY_STOP recovery section), BEFORE the "INFRA-06 Bug Triage Outcomes" section at line 168. Heading `## Pre-LIVE Operator Checklist` so it gets a TOC entry alongside the 6 existing symptoms.

---

## Shared Patterns (apply to multiple files)

### Autoflake-survival local imports

**Source:** `services/api-gateway/app/main.py:1155` (`from datetime import timezone as _tz`) and `:1209` (`from pathlib import Path as _Path  # noqa: F401`) — project memory `feedback_main_imports_autoflake.md`.

**Apply to:** new gateway proxy route AND the `from app.preflight import run_all` line in trading-engine `main.py`.

**Pattern:**
```python
# Inside a route function (pin the use site):
from datetime import timezone as _tz
import json

# OR at module top with the noqa marker:
from app.preflight import run_all  # noqa: F401
```

**Why load-bearing:** autoflake runs on `make format`; unmarked unused imports are stripped silently. Project memory documents this regression pattern. Without the F401 marker on `from app.preflight`, grep gate #2 (`test_preflight_module_imports_at_lifespan`) fails after the next format pass.

### `Path.is_file()` for bind-mounted state files

**Source:** `services/trading-engine/app/main.py:282-283`

**Apply to:** `check_emergency_stop` and any other file-presence check on a path that might be a bind mount.

**Pattern:** Use `.is_file()` not `.exists()`. Docker may create a directory at a bind-mount path if the host file is absent; `.exists()` returns `True` for that directory, `.is_file()` correctly returns `False`.

### Unauthenticated read-only fixture choice

**Source:** `services/api-gateway/tests/conftest.py:61-64` (plain `test_client` fixture, no auth override).

**Apply to:** `test_preflight_route.py` and `test_preflight_proxy.py`. Per `08-CONTEXT.md` decision (matches safety-state D-09), the preflight endpoint is unauthenticated. Use `test_client`, NOT `admin_client`. Picking `admin_client` would mask an auth-leak regression — `admin_client` overrides the dep and would let an accidentally-added `Depends(get_current_admin_user)` slip through.

### JSON-response mocking with `.body.decode()`

**Source:** `services/api-gateway/tests/test_safety_state.py:32-40` (`_build_response`) — explicitly sets `.body` because the real handler decodes via `json.loads(resp.body.decode())` (F-03 fix at safety_state.py:1080-1084).

**Apply to:** `test_preflight_proxy.py`. Calling `.get()` or `.json()` on `JSONResponse` raises `AttributeError`; mocks must populate `.body` so the handler's decode path runs.

### Grep gate dual form (pathlib + subprocess)

**Source:** `services/tournament-harness/tests/integration/test_tourn07_grep_gate.py:23-65`.

**Apply to:** Grep gate #1 (`test_live_preflight_rejected_log_exists`).

**Pattern:** Provide both:
1. `pathlib.Path.rglob("*.py")` + `re.compile(...).search(text)` — works on any platform, deterministic.
2. `subprocess.run(["grep", "-r", PATTERN, str(dir_)])` — fidelity to the literal command operators run in CI / shell.

Both must pass; the divergence between them flags either a platform quirk or a forgotten directory exclusion.

### Pydantic Settings constructor for unit tests

**Source:** `services/trading-engine/tests/unit/test_config.py:62-66` (skipped but pattern still correct).

**Apply to:** all `test_preflight_checks.py` tests that need `trading_mode` / `max_risk_per_trade` permutations.

**Pattern:**
```python
from app.config import Settings
settings = Settings(trading_mode="LIVE", max_risk_per_trade=0.03)
result = check_cap(settings)
```

Pydantic v2 supports keyword-arg overrides on the model directly — no `os.environ` round-trip, no `reload_settings()` call (which has global side effects across tests).

### Lifespan source-inspection regression guard

**Source:** `services/trading-engine/tests/test_lifespan.py:64-76` (`test_lifespan_body_uses_async_with_phases`).

**Apply to:** `test_lifespan_source_contains_cap_check` in `test_preflight_lifespan.py`, and grep gate #2 in `test_preflight_grep_gates.py`.

**Pattern:** `inspect.getsource(main_mod.lifespan)` returns the function source; assert load-bearing substrings (`"LIVE_PREFLIGHT_REJECTED"`, `"max_risk_per_trade"`, `"0.02"`) are present. This is the **defence-in-depth** layer that catches a future refactor accidentally moving the check out of the lifespan body.

---

## No Analog Found

Files with no close internal match (planner references RESEARCH.md / external docs):

| File / Pattern | Reason | Fallback |
|----------------|--------|----------|
| `.github/workflows/preflight-live-readiness.yml` — PR-label conditional (`if: contains(github.event.pull_request.labels.*.name, 'live: requested')`) | No existing workflow filters jobs by PR label; existing workflows use path-globs or branch filters only | GitHub Actions docs via `context7`: search for `pull_request` event payload and `contains()` expression function. Reference snippet to put in PLAN.md verbatim. |
| `scripts/preflight_live.py` — `--dry-run --target=<git-ref>` flag pair reading `.env.example` from a ref | No internal script uses `git show <ref>:<path>` to load config from a non-HEAD ref | Planner shapes this from scratch. Suggested: `subprocess.run(["git", "show", f"{target}:.env.example"], capture_output=True, text=True)` + parse the output as a dotenv blob. |

---

## Metadata

**Analog search scope:**
- `services/trading-engine/app/` (handlers, lifespan, config, main)
- `services/api-gateway/app/main.py` + `tests/`
- `services/tournament-harness/migrations/` + `tests/integration/`
- `scripts/` (CLI patterns)
- `.github/workflows/` (CI patterns)
- `tests/integration/` (grep gate patterns)
- `RUNBOOK.md` (Diagnose/Action/Verification template)

**Files scanned:** 35
**Pattern extraction date:** 2026-05-16

**Key cross-cutting observations:**
1. The Phase 8 cap-check block at `trading-engine/app/main.py:259` co-locates with the existing `LIVE_TRADING_ACK` check. Both checks raise `RuntimeError` from inside `lifespan()` — FastAPI converts this into a non-zero exit, matching PREFLIGHT-02 success criterion #3.
2. The `/api/preflight/live-readiness` route lives on **trading-engine** (port 8005), not api-gateway. The gateway proxies. This avoids the D-09/D-10 split where api-gateway would otherwise need to read `MAX_RISK_PER_TRADE` from its own env (which it should not).
3. The "all checks UNKNOWN on trading-engine unreachable" safe-default at the gateway side is the **single most load-bearing line** in the proxy route — falling back to PASS would defeat the entire phase. Tests must assert this explicitly.
4. The two grep gates (`LIVE_PREFLIGHT_REJECTED` log + `from app.preflight` import) ARE the regression detector. They are the v1.0 retrospective lesson applied to v1.1: pair every "removed permanently" claim with a CI grep gate (TOURN-07 model).
