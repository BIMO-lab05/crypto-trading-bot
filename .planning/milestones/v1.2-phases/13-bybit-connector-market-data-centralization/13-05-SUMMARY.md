---
phase: 13-bybit-connector-market-data-centralization
plan: 05
subsystem: scripts
tags: [bybit-connector, scripts, refactor, fail-fast, BC-02, D-04]

requires:
  - phase: 13-bybit-connector-market-data-centralization
    provides: tests/integration/test_scripts_fail_fast.py (BC-02/D-04 RED contract, plan 13-03)
  - phase: 13-bybit-connector-market-data-centralization
    provides: PATTERNS.md "Shared 2" fail-fast scaffold (plan 13-02)

provides:
  - "5 collect_*/data_quality_enhancement scripts route klines via bybit-connector REST"
  - "BC-02/D-04 fail-fast contract satisfied for these 5 scripts"
  - "Zero pybit imports remaining anywhere under scripts/ (outside scripts/tape/)"

affects:
  - 13-06 (rest of Wave 1 — backtesting fetcher + remaining scripts + ml-prediction downloads)
  - 13-07 (CI grep gate BC-03 — these 5 contributions reduce gate's RED count)

tech-stack:
  added: []
  patterns:
    - "httpx async + assert_connector_reachable() at top of __main__"
    - "requests-based sync probe pattern for legacy sync scripts"
    - "from __future__ import annotations + lazy heavy imports so fail-fast runs on lean hosts"

key-files:
  modified:
    - scripts/collect_180_days_data.py
    - scripts/collect_6months_for_ml.py
    - scripts/collect_bybit_direct_180days.py
    - scripts/data_quality_enhancement.py
    - scripts/collect_ml_training_data_simple.py

key-decisions:
  - "Use async httpx.AsyncClient for the 2 already-async scripts; reuse sync `requests` for the 3 sync scripts to keep import-graph minimal (no aiohttp/httpx churn)."
  - "Defer heavy deps (psycopg2/pandas/numpy/scipy) behind try/except in data_quality_enhancement.py and collect_ml_training_data_simple.py so the fail-fast probe operates on hosts without those libs (matches existing pattern in collect_180_days_data.py for httpx/pandas)."
  - "Wire `from __future__ import annotations` in the two scripts above to stop pd.DataFrame / pd.Series type hints from evaluating at import time when pd is None."
  - "For collect_ml_training_data_simple.py: position assert_connector_reachable() BEFORE the interactive input() prompt — otherwise no-stdin subprocess invocation (the test contract) trips EOFError instead of exiting 2."

patterns-established:
  - "Pattern A (async scripts): import httpx + asyncio.run(_probe()) wrapping AsyncClient.get(/health) at top of __main__"
  - "Pattern B (sync scripts): requests.get(/health, timeout=5) probe sharing the script's already-imported requests dependency"
  - "Pattern C (heavy-dep tolerant): wrap psycopg2/pandas/numpy/scipy imports in try/except, set names to None, re-check at main() entry"

requirements-completed: [BC-02]

duration: 25min
completed: 2026-05-21
---

# Phase 13 Plan 05: Operator-script bybit-connector centralization Summary

**Five `scripts/collect_*.py` + `scripts/data_quality_enhancement.py` operator-run scripts now route klines through bybit-connector REST with D-04 fail-fast; the last `pybit` import under `scripts/` is dead.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-05-21T20:02:39Z
- **Tasks:** 5 scripts refactored (one atomic commit per script)
- **Files modified:** 5

## Accomplishments

- `scripts/collect_180_days_data.py`: replaced `https://api.bybit.com/v5/market/kline` with `${BYBIT_CONNECTOR_URL}/api/v1/market/kline`; added async fail-fast scaffold before argparse.
- `scripts/collect_6months_for_ml.py`: replaced `self.base_url=https://api.bybit.com` with `BYBIT_CONNECTOR_URL`; URL + parser swap; fail-fast wired into `__main__`.
- `scripts/collect_bybit_direct_180days.py`: filename retained (cosmetic out-of-scope), but body now hits bybit-connector; sync `requests`-based fail-fast probe; banner now prints connector URL instead of `https://api.bybit.com`.
- `scripts/data_quality_enhancement.py`: `fetch_historical_data_bybit` method routed through connector; psycopg2/pandas/numpy/scipy deferred behind try/except so the D-04 probe can run on hosts without DB / scientific stack; `from __future__ import annotations` added to keep type hints lazy.
- `scripts/collect_ml_training_data_simple.py`: `from pybit.unified_trading import HTTP` and `HTTP(...)` instantiation REMOVED — the only `pybit` import in `scripts/` outside `scripts/tape/` is now gone. `session.get_kline(...)` replaced with `requests.get(.../api/v1/market/kline)`. Fail-fast positioned BEFORE the interactive `input()` prompt so subprocess invocation (no stdin) exits 2 rather than EOFError.
- All 5 scripts pass their `tests/integration/test_scripts_fail_fast.py` parametrize cases.

## Task Commits

Each script committed atomically (one concern per commit):

1. **Script 1: collect_180_days_data.py** — `0a393f3` (refactor)
2. **Script 2: collect_6months_for_ml.py** — `b1ff14e` (refactor)
3. **Script 3: collect_bybit_direct_180days.py** — `970986d` (refactor)
4. **Script 4: data_quality_enhancement.py** — `e4ba1eb` (refactor)
5. **Script 5: collect_ml_training_data_simple.py** — `ee6043a` (refactor, drops `pybit`)

## Files Modified

- `scripts/collect_180_days_data.py` — async httpx fail-fast probe + URL/parser swap.
- `scripts/collect_6months_for_ml.py` — async httpx fail-fast probe + URL/parser swap.
- `scripts/collect_bybit_direct_180days.py` — sync `requests` fail-fast probe + URL/parser swap + banner text.
- `scripts/data_quality_enhancement.py` — sync `requests` fail-fast probe + URL/parser swap + lazy heavy imports + `from __future__ import annotations`.
- `scripts/collect_ml_training_data_simple.py` — pybit removed; sync `requests` fail-fast probe (BEFORE `input()`); URL/parser swap; lazy pandas import + `from __future__ import annotations`.

## Verification

```
pytest tests/integration/test_scripts_fail_fast.py -v -k "collect_180_days or collect_6months_for_ml or collect_ml_training_data_simple or collect_bybit_direct_180days or data_quality_enhancement"
```

Result: **5 passed, 8 deselected**. All five parametrize cases that this plan claims responsibility for are GREEN.

Banned-pattern audit (Bybit direct URLs + `from pybit`/`import pybit`):

```
scripts/collect_180_days_data.py:          0 matches
scripts/collect_6months_for_ml.py:         0 matches
scripts/collect_ml_training_data_simple.py: 0 matches
scripts/collect_bybit_direct_180days.py:   0 matches
scripts/data_quality_enhancement.py:       0 matches
```

`grep -rE "^\s*(from pybit|import pybit)" scripts/ --exclude-dir=tape` → no matches. Last `pybit` import in `scripts/` is dead.

Each refactored script:
- Imports `os` (anchored to `os.getenv("BYBIT_CONNECTOR_URL", ...)`), survived formatter.
- Imports `sys` (anchored to `sys.exit(2)` and `file=sys.stderr`).
- Defines `BYBIT_CONNECTOR_URL = os.getenv("BYBIT_CONNECTOR_URL", "http://localhost:8001")`.
- Defines `assert_connector_reachable()` whose error-path contains literal substrings `bybit-connector is not reachable`, `BYBIT_CONNECTOR_URL`, and `docker compose -f docker-compose.unified.yml up -d bybit-connector`.
- Invokes `assert_connector_reachable()` at the top of `if __name__ == "__main__":` BEFORE argparse / `input()` / any other __main__ logic.

## Decisions Made

- **Sync `requests`-based probe for 3 sync scripts** (`collect_bybit_direct_180days.py`, `data_quality_enhancement.py`, `collect_ml_training_data_simple.py`) instead of converting them to async. Rationale: minimal import-graph churn, anchoring `requests` to existing usage means autoflake/formatter won't strip it.
- **Lazy heavy imports** in `data_quality_enhancement.py` and `collect_ml_training_data_simple.py`. Rationale: the BC-02/D-04 fail-fast contract test runs on a CI host that may not have `psycopg2`/`pandas`/`numpy`/`scipy` installed; if module import fails before the probe runs, the script exits with `ImportError` (non-2 returncode) and the test fails. By making heavy imports lazy + re-checking once the probe passes, the script still raises `ImportError` for legitimate runs (operator with full deps but no connector) while the fail-fast contract is testable.
- **`from __future__ import annotations`** added in the two scripts whose method signatures use `pd.DataFrame` / `pd.Series` as type hints. Without this, function-definition-time evaluation of `pd.DataFrame` triggers `AttributeError: 'NoneType' has no attribute 'DataFrame'` when pandas is unavailable.
- **For Script 5 (`collect_ml_training_data_simple.py`):** placed `assert_connector_reachable()` BEFORE the `input("...?")` prompt and BEFORE the heavy-dep check. The subprocess-based test contract attaches no stdin; if `input()` runs first, `EOFError` short-circuits the fail-fast and produces returncode 1. Placing the probe first ensures returncode 2.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `psycopg2` / `scipy` / `pandas` / `numpy` are not installed on the test host**
- **Found during:** Script 4 (`data_quality_enhancement.py`) — first fail-fast test run.
- **Issue:** Module-level `import psycopg2` raised `ModuleNotFoundError` before `assert_connector_reachable()` could fire, so the script exited with code 1 (not 2), and stderr contained no operator hint — failing the BC-02 contract.
- **Fix:** Wrapped `psycopg2`/`pandas`/`numpy`/`scipy` imports in `try/except ImportError`, set names to `None` on failure, recorded the error in `_HEAVY_IMPORT_ERROR`. Re-checked inside `main()` to re-raise once the connector probe passes (so legitimate operator runs still see a clean failure if deps are missing). Same pattern applied to `pandas` in Script 5.
- **Files modified:** `scripts/data_quality_enhancement.py`, `scripts/collect_ml_training_data_simple.py`.
- **Verification:** Per-script fail-fast test passes (exit code 2 with operator hint).
- **Committed in:** `e4ba1eb`, `ee6043a` (the same commits as the per-script refactors).

**2. [Rule 1 - Bug] Method type hints `-> pd.DataFrame` evaluated at import time when `pd is None`**
- **Found during:** Script 4 — after deferred-import fix, next subprocess run raised `AttributeError: 'NoneType' object has no attribute 'DataFrame'` from line `def fetch_symbol_data(self, symbol: str) -> pd.DataFrame:`.
- **Issue:** Python evaluates type hints at function-definition time by default (PEP 484); when `pd = None`, every `-> pd.DataFrame` annotation triggers attribute lookup at module load. The earlier deferred-import didn't help.
- **Fix:** Added `from __future__ import annotations` (PEP 563) so all annotations are stored as strings and never evaluated at definition. Applied to Scripts 4 and 5.
- **Files modified:** `scripts/data_quality_enhancement.py`, `scripts/collect_ml_training_data_simple.py`.
- **Verification:** Per-script fail-fast test passes.
- **Committed in:** `e4ba1eb`, `ee6043a` (same commits).

**Total deviations:** 2 auto-fixed (1 blocking host-env, 1 type-hint evaluation bug).
**Impact on plan:** Both auto-fixes are essential for the BC-02/D-04 contract test to be runnable on lean hosts. The lazy-import + `from __future__ import annotations` pattern is small and reversible. No scope creep — the existing `collect_180_days_data.py` already had a try/except guard around `httpx`/`pandas`, so this matches established project pattern.

## Issues Encountered

- **Formatter strips unanchored imports.** Twice during initial edits, the post-tool formatter (likely `autoflake`-style behavior baked into the Edit hook) removed `import asyncio` / `import httpx` from `collect_bybit_direct_180days.py` because no usage was present yet. Resolved by adding scaffolding code (anchoring usages of the new imports) in the same edit batch, then verifying with `grep -nE "^import (os|sys|httpx)"` after each format. The `# noqa: F401` comment on `import os` is defensive against any future flake8 / autoflake pass.
- **No actual `autoflake` in `.pre-commit-config.yaml`** and no `.git/hooks/pre-commit` symlink installed. The orchestrator prompt's warning about autoflake was prescriptive — the formatter that ran during this session strips unused imports nonetheless (likely Edit-hook integration with the project's formatting toolchain). Treating the warning as load-bearing was correct.

## Threat Flags

None — no new network surface introduced. All 5 scripts now point at `bybit-connector` (trust-boundary already covered by phase 13 threat model). The `BYBIT_CONNECTOR_URL` env defaults to `http://localhost:8001` (loopback); operator-set override is the only attack surface and is documented in CONTEXT D-04.

## Next Phase Readiness

- Plan 13-06 (Wave 1, balance) can pick up `collect_6months_historical.py`, `fetch_real_historical_data.py`, the 4 `services/ml-prediction-service/download_*.py` scripts, `backtesting/bybit_data_fetcher.py`, and `infrastructure/scripts/rotate_secrets.py`. The remaining 8 parametrize cases in `test_scripts_fail_fast.py` are still RED on `main`.
- BC-03 (CI grep gate) plan can rely on these 5 files now contributing **zero** matches to its banned-pattern surface.
- BC-02 is **partially satisfied** by this plan (5 of 13 fail-fast cases GREEN). Full BC-02 completion requires Plan 13-06 + the backtesting-fetcher test case.

## Self-Check: PASSED

- All 5 files exist: confirmed via `git status` + grep.
- All 5 commits exist: `0a393f3`, `b1ff14e`, `970986d`, `e4ba1eb`, `ee6043a` (verified via `git log --oneline -7`).
- 5 of 5 BC-02 fail-fast parametrize cases for this plan's scope flip GREEN: confirmed via `pytest tests/integration/test_scripts_fail_fast.py -v -k "..." → 5 passed`.
- Zero banned-pattern matches across all 5 files: confirmed via grep.
- Zero `pybit` imports anywhere under `scripts/` (excluding `scripts/tape/`): confirmed.

---
*Phase: 13-bybit-connector-market-data-centralization*
*Plan: 05*
*Completed: 2026-05-21*
