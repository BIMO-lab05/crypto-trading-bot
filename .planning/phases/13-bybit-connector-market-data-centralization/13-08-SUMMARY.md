---
phase: 13-bybit-connector-market-data-centralization
plan: 08
subsystem: trading-engine, ci
tags: [bybit-connector, trading-engine, archive, binance, bc-04, bc-03-gate]
requirements_completed: [BC-04]
dependency_graph:
  requires:
    - 13-02 (BC-03 gate exists and was RED-by-design pre-plan)
    - 13-04..13-07 (Wave 1 refactors reduced bypass set to the four tape-preserved.py respx mock-target sites)
  provides:
    - Binance adapter archived at REPO ROOT under _archive_exchanges/
    - factory.py + __init__.py cleaned of Binance imports, registrations, and docstring references (lines 23 + 213)
    - test_multi_exchange.py removed (BC-04 cascade)
    - BC-03 grep gate FULLY GREEN
  affects:
    - services/trading-engine/app/exchanges/{factory,__init__}.py (reduced adapter set)
    - tests/ci/test_no_bybit_bypass.py (EXEMPT_FILES extended + mirror lock test)
tech_stack:
  added: []
  patterns:
    - Archive-at-repo-root convention extended (`_archive_exchanges/` joins `_archive_lstm/`; placement differs per CONTEXT D-02 intentional choice — repo root, not nested under a service)
    - EXEMPT_FILES pattern (file-level allowlist) extended for BC-07 respx mock-target false-positive — mirror lock test `test_tape_preserved_test_allowlisted` pins the exemption (same idiom as `test_smoke_security_test_allowlisted`)
key_files:
  created:
    - _archive_exchanges/binance.py (moved from services/trading-engine/app/exchanges/binance.py via `git mv`, R100 rename)
    - _archive_exchanges/.gitkeep
  modified:
    - services/trading-engine/app/exchanges/factory.py (-26 lines: import + Binance adapter registration block)
    - services/trading-engine/app/exchanges/__init__.py (-12 lines: import block, four __all__ adapter entries, docstring lines 23 + 213)
    - tests/ci/test_no_bybit_bypass.py (+43 lines: EXEMPT_FILES entry for tape-preserved.py + mirror lock test + paraphrased URL comments)
  deleted:
    - services/trading-engine/tests/test_multi_exchange.py (861 lines — wholesale pytest.mark.skip dead test code; PR #86 stale-tests note)
decisions:
  - "Used EXEMPT_FILES (file-level) for tape-preserved.py exemption, not EXEMPT_PATHS (directory-level). Same idiom as smoke security test allowlist. Reads idiomatically; prefix-match would also work but signals scope creep."
  - "Documentation comments in the allowlist describe the URL roles via paraphrase rather than reproducing the literal hosts. The legacy version of this commit reproduced the URLs in comments, which caused the gate to fire on itself (Pitfall 4 in 13-RESEARCH.md). Caught + fixed before final commit."
  - "BINANCE_ERROR_MAP + map_binance_error left as __all__ orphans (carry-in BC-FOLLOWUP-05). Verified no external consumers via repo-wide grep; only references are in binance.py (now archived) and __init__.py itself."
  - "test_multi_exchange.py deleted (not refactored, not import-guarded). PATTERNS.md W#2: module-level imports fail at collection time before pytest.mark.skip can take effect. The file's own skip-reason ('stale tests after PR #86 refactor; needs rewrite') signals dead code."
  - "Architecture ASCII diagram at line 56 (post-edit; was 58 pre-edit) still contains `| - Binance        |` row. BC-04 named only lines 23 + 213; this row is in a separate ASCII art block at the top of the module docstring. Out-of-scope for BC-04 per the explicit line numbers in the requirement text; surfaced as carry-in BC-FOLLOWUP-07."
metrics:
  duration: "~50 minutes"
  completed: "2026-05-22"
  commits: 3 (plus this metadata commit)
  tests_added: 1 (test_tape_preserved_test_allowlisted)
  tests_deleted: ~32 (all in test_multi_exchange.py, all wholesale-skipped)
---

# Phase 13 Plan 08: Archive Binance Adapter + Flip BC-03 Gate GREEN

## One-Liner

Archived `services/trading-engine/app/exchanges/binance.py` to `_archive_exchanges/binance.py` per operator policy (CONTEXT D-02), cleaned factory.py and __init__.py (imports + registration + docstring lines 23 and 213), deleted `test_multi_exchange.py` (wholesale-skipped dead code that would ImportError at collection time after archival), and amended the BC-03 grep gate's EXEMPT_FILES to allowlist `tests/integration/test_bybit_connector_tape_preserved.py` (whose four literal Bybit URLs are load-bearing respx mock targets, not bypass calls). BC-03 grep gate now FULLY GREEN.

## Objective vs Outcome

| Plan task | Outcome |
|-----------|---------|
| Task 1: `git mv` binance.py to `_archive_exchanges/` at REPO ROOT; clean factory.py + __init__.py (imports, registration, __all__, docstring lines 23 + 213) | Done; commit `afb8c42`. R100 rename detected (no content change). Both files ast.parse OK. |
| Task 2: Delete `services/trading-engine/tests/test_multi_exchange.py` (collection-time import failure after Binance archival) | Done; commit `1c208e6`. `git rm` (not refactor). |
| Task 3 (extension scope): Amend BC-03 gate to exempt `tests/integration/test_bybit_connector_tape_preserved.py` | Done; commit `f7c431d`. Added file to `EXEMPT_FILES` + mirror lock test `test_tape_preserved_test_allowlisted`. |

## What was archived / removed

### Archived (preserved in git history at `_archive_exchanges/`)
- `_archive_exchanges/binance.py` — 1207 lines. The full Binance adapter (`BinanceExchangeAdapter`, `BinanceAdapterConfig`, `BinanceRateLimiter`, `create_binance_adapter`, `BINANCE_ERROR_MAP`, `map_binance_error`). Reachable only via `git show` / `git log -- _archive_exchanges/binance.py`. NOT on `sys.path` (no `__init__.py` in `_archive_exchanges/`). NOT subject to BC-03 grep gate (directory in `EXEMPT_PATHS`).

### Removed (no longer in tree)
- `services/trading-engine/tests/test_multi_exchange.py` — 861 lines. Every test was `pytest.mark.skip(reason="stale tests after PR #86 refactor; needs rewrite")`. The file's top-level imports (`BinanceExchangeAdapter, KrakenExchangeAdapter, CoinbaseExchangeAdapter` from `app.exchanges`) would have failed at pytest collection time after Task 1 archived binance.py, breaking CI even though every test inside is skipped. Per PATTERNS.md W#2: deletion preferred over try/except-import-guarding because the skip-reason signals dead code that should be rewritten from scratch when multi-exchange testing returns to scope.

### Cleaned (Binance references removed from live code)

`services/trading-engine/app/exchanges/factory.py`:
- Line 62 (pre-edit): `from app.exchanges.binance import BinanceExchangeAdapter` — DELETED
- Lines 185-210 (pre-edit): The `if ExchangeName.BINANCE not in self._registry: self.register(...)` block with `adapter_class=BinanceExchangeAdapter` + full `ExchangeCapabilities(...)` block — DELETED

`services/trading-engine/app/exchanges/__init__.py`:
- Line 23 (pre-edit) docstring bullet: `   - BinanceExchangeAdapter: Direct Binance API integration` — DELETED (BC-04 explicit requirement coverage)
- Line 213 (pre-edit) Module Structure tree row: `    binance.py          # Binance exchange adapter` — DELETED (BC-04 explicit requirement coverage)
- Lines 329-336 (pre-edit) import block: `# Binance Adapter` comment + `from app.exchanges.binance import (...)` — DELETED
- Lines 512-516 (pre-edit) `__all__` section comment + four entries (`BinanceExchangeAdapter`, `BinanceAdapterConfig`, `BinanceRateLimiter`, `create_binance_adapter`) — DELETED
- `BINANCE_ERROR_MAP` (line 501 pre-edit) and `map_binance_error` (line 502 pre-edit) in `__all__` — PRESERVED as orphan strings per plan (carry-in `BC-FOLLOWUP-05`). Verified via repo-wide grep that no consumer does `from app.exchanges import BINANCE_ERROR_MAP` or `from app.exchanges import map_binance_error`.

### Preserved (intentional — out of BC-04 scope)
- `services/trading-engine/app/exchanges/base.py:62` `ExchangeName.BINANCE = "binance"` — PRESERVED per RESEARCH Anti-Pattern. Removing this enum value cascades into `manager.py:256` docstring + `router.py:400` default-fees dict edits which are explicitly out of CONTEXT scope.
- `services/trading-engine/app/exchanges/__init__.py` line ~56 (post-edit): the Architecture ASCII diagram row `| - Binance        |` — PRESERVED. BC-04 explicitly names ONLY lines 23 + 213; the ASCII diagram is a separate site documented as `BC-FOLLOWUP-07`.

## BC-03 grep gate state transition

**Pre-plan (Wave 1 close):** RED on `tests/ci/test_no_bybit_bypass.py::test_no_bybit_bypass_in_python_code` with four violations, all in `tests/integration/test_bybit_connector_tape_preserved.py`:
- Line 18: `mainnet_rest_url` in module docstring describing pre-refactor handler state
- Line 109: `mainnet_rest_url` in Test 1 docstring (RED-by-design note)
- Line 147: `mainnet_rest_url` in `mock_router.get("https://api.bybit.com/v5/market/orderbook").mock(...)` respx target
- Line 151: `testnet_rest_url` in matching respx target for `api-testnet.bybit.com`

**Post-plan:** GREEN — all 5 tests in `tests/ci/test_no_bybit_bypass.py` pass:
```
tests/ci/test_no_bybit_bypass.py .....                                   [100%]
============================== 5 passed in 13.72s ==============================
```

The fifth test (`test_tape_preserved_test_allowlisted`) is the new mirror lock added in Task 3 — same idiom as `test_smoke_security_test_allowlisted`, pins the EXEMPT_FILES entry against silent removal.

## Deviations from Plan

### Plan-as-written deviations

**1. [Rule 1 - Bug] Gate fired on its own allowlist documentation comments**
- **Found during:** Task 3 post-edit gate run
- **Issue:** First version of the allowlist documentation reproduced the literal Bybit hosts inside comments (`# (a) respx mock-target strings — \`mock_router.get("https://api.bybit.com/...`). The BC-03 grep gate then fired four false positives on its own source file, exactly the failure mode the gate's own module docstring warns about (Pitfall 4 in 13-RESEARCH.md).
- **Fix:** Paraphrased the URLs in both the EXEMPT_FILES comment block AND the `test_tape_preserved_test_allowlisted` docstring. Kept the substantive meaning ("Bybit mainnet and testnet REST host strings", "respx mock-target strings", "RED-by-design documentation") without reproducing the literal regex-matching strings.
- **Files modified:** tests/ci/test_no_bybit_bypass.py
- **Commit:** f7c431d (the buggy first-pass and the fix are squashed in the single Task 3 commit; the gate's own GREEN run is the regression test)

### Plan-text deviations (extension scope reality vs prompt)

**2. [Scope] `data/ml_training/fetch_xrp_365d.py` does not exist**
- **Prompt said:** "Gate caught a 5th violation at `data/ml_training/fetch_xrp_365d.py:24` — refactor or delete."
- **Reality:** Repo-wide search (`find . -name "fetch_xrp_365d*"`, `find . -path '*ml_training*'`) returns no matches. The `data/ml_training/` directory does not exist on this worktree. Gate run pre-plan showed exactly 4 violations, all in tape-preserved.py.
- **Action:** Skipped the planned `refactor(data/ml_training):` commit. Documented finding here so future planners do not chase the phantom site.

**3. [Plan-line-numbers vs reality] Docstring docstring tree-row line was at file line 213 in CONTEXT but the deletion shifted upstream lines; post-edit position differs**
- The original PLAN.md cited lines 23 and 213 as the docstring sites. After deleting the line-23 bullet, the Module Structure tree row shifts to file line 212. The plan's text correctly described the targets by content (`"- BinanceExchangeAdapter: Direct Binance API integration"` and `"binance.py          # Binance exchange adapter"`) so the Edit operations targeted the strings, not the line numbers. Both sites are now gone (verified by grep returning 0 for both exact strings).

## Carry-Ins Surfaced

| ID | Description | Why surfaced | Plan to address |
|----|-------------|--------------|-----------------|
| `BC-FOLLOWUP-05` | `BINANCE_ERROR_MAP` + `map_binance_error` orphan strings remain in `services/trading-engine/app/exchanges/__init__.py:458-459` (post-edit position) `__all__` list | Plan explicitly opted to leave these as carry-in pending future audit. Verified no external consumers via grep; orphans are safe (Python does not validate `__all__` content at import time; only `from app.exchanges import *` would AttributeError, and no caller does that). | Optional cleanup commit in Wave 3 phase close — drop the two strings from `__all__`. |
| `BC-FOLLOWUP-07` | Architecture ASCII diagram in `__init__.py` upper docstring still contains `| - Binance        |` row at file line ~56 post-edit | BC-04 requirement text named ONLY lines 23 and 213; the ASCII diagram is a separate site. Operator may prefer symmetry cleanup but it is out of strict requirement scope. | Optional one-line edit in Wave 3 phase close. |

## Verification Evidence

### Acceptance criteria from PLAN.md

| Criterion | Status | Evidence |
|-----------|--------|----------|
| `_archive_exchanges/binance.py` exists at REPO ROOT | PASS | `test -f _archive_exchanges/binance.py` exit 0; `ls -la _archive_exchanges/` shows 39171-byte file |
| `services/trading-engine/app/exchanges/binance.py` does NOT exist | PASS | `test -f services/trading-engine/app/exchanges/binance.py` exit 1 |
| `grep -c "from app.exchanges.binance" services/trading-engine/app/exchanges/factory.py` returns 0 | PASS | output: 0 |
| `grep -c "BinanceExchangeAdapter" services/trading-engine/app/exchanges/factory.py` returns 0 | PASS | output: 0 |
| `grep -c "from app.exchanges.binance" services/trading-engine/app/exchanges/__init__.py` returns 0 | PASS | output: 0 |
| `grep -c "BinanceExchangeAdapter: Direct Binance API integration" services/trading-engine/app/exchanges/__init__.py` returns 0 | PASS | output: 0 |
| `grep -c "binance.py          # Binance exchange adapter" services/trading-engine/app/exchanges/__init__.py` returns 0 | PASS | output: 0 |
| Both files ast.parse OK | PASS | `python3 -c "import ast; ast.parse(...)"` prints `both parse OK` |
| `ExchangeName.BINANCE` enum preserved | PASS | `grep -c "BINANCE" services/trading-engine/app/exchanges/base.py` returns 1 |
| `services/trading-engine/tests/test_multi_exchange.py` does NOT exist | PASS | `test -f` exit 1; `git rm` recorded in commit `1c208e6` |
| `pytest tests/ci/test_no_bybit_bypass.py -v` exits 0 | PASS | 5 passed in 13.72s |

### Docker import smoke (Plan Step 5b — `docker exec crypto-bot-trading-engine python -c "import app.main"`)

Deferred — trading-engine container is not running in this worktree session. `docker ps` shows only the host stack containers (rabbitmq, timescale, etc.) up; the per-service containers including trading-engine are down. Per advisor guidance, ast.parse + grep gate GREEN is sufficient evidence for the worktree commit because:
- Python's import system loads `__init__.py` first; ast.parse on `__init__.py` validates that the module is syntactically valid and that no `from X import ...` statements reference deleted modules (such a statement would survive ast.parse since the import is not resolved until runtime — but grep already confirmed zero `from app.exchanges.binance` references remain).
- The two import-time failure modes that `import app.main` would catch are (a) syntax error and (b) `ImportError` from `from app.exchanges.binance import ...`. (a) is ruled out by ast.parse; (b) is ruled out by `grep -c "from app.exchanges.binance" __init__.py factory.py main.py` returning 0 in all files.
- Wave 3 should restart trading-engine container as part of the RUNBOOK verification cycle and run the docker smoke at that point.

### Commits

| Order | Commit | Subject |
|-------|--------|---------|
| 1 | `afb8c42` | chore(exchanges): archive Binance adapter per operator policy (BC-04) |
| 2 | `1c208e6` | chore(test): delete test_multi_exchange.py (BC-04 cascade) |
| 3 | `f7c431d` | feat(ci): exempt tape-preserved test from BC-03 gate (respx mock targets) |
| 4 | (this metadata commit) | docs(13-08): plan summary |

## Threat Flags

None. No new network surface, auth path, file access pattern, or schema change introduced. The plan removes surface (Binance adapter) and tightens the BC-03 gate's allowlist with a documented mirror lock — net reduction in attack surface and net increase in invariant enforcement.

## Known Stubs

None.

## TDD Gate Compliance

Plan type is `execute`, not `tdd`. RED/GREEN/REFACTOR gates not required by the plan frontmatter. The BC-03 grep gate itself follows the TDD pattern at the phase level: it was authored RED in Plan 13-02 and flips GREEN in this Plan 13-08 — visible in the commit log progression from `caa44f8` (RED-by-design merge of Wave 1) to `f7c431d` (GREEN gate). The BC-07 contract (`tests/integration/test_bybit_connector_tape_preserved.py`) remains RED-by-design per its own docstring; that contract flips GREEN when Wave 1 Plan 04 refactor lands (separate plan).

## Self-Check: PASSED

- File `_archive_exchanges/binance.py` at REPO ROOT — FOUND
- File `_archive_exchanges/.gitkeep` — FOUND
- File `services/trading-engine/app/exchanges/binance.py` — ABSENT (expected)
- File `services/trading-engine/tests/test_multi_exchange.py` — ABSENT (expected)
- Commit `afb8c42` in git log — FOUND
- Commit `1c208e6` in git log — FOUND
- Commit `f7c431d` in git log — FOUND
- `pytest tests/ci/test_no_bybit_bypass.py -v` exits 0 — VERIFIED
- ast.parse on factory.py + __init__.py — VERIFIED
- All BC-04 must_haves truths in 13-08-PLAN.md verified
