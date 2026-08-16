---
phase: quick-260816-qjz
plan: 01
subsystem: bybit-connector
tags: [pagination, instruments-info, min-notional, RES-07, money-adjacent]
requires:
  - services/bybit-connector/app/bybit_rest_client.py::_request
  - services/bybit-connector/app/bybit_rest_client.py::_handle_response
provides:
  - "get_instruments_info: full-universe instrument list via nextPageCursor following"
  - "MAX_INSTRUMENTS_PAGES: module-level page cap constant"
affects:
  - services/trading-engine/app/services/instruments_cache.py
  - services/bybit-connector/app/main.py (route unchanged, behaviour widened)
tech-stack:
  added: []
  patterns:
    - "for/else cursor loop — else branch fires only on cap exhaustion (no break)"
    - "`or None` collapses empty-string / absent-key / explicit-None into one falsy termination case"
    - "per-page dict copy so each recorded call carries its own cursor state"
key-files:
  created: []
  modified:
    - services/bybit-connector/app/bybit_rest_client.py
    - services/bybit-connector/tests/test_rest_client_comprehensive.py
    - services/trading-engine/app/services/instruments_cache.py
decisions:
  - "limit=1000 kept an internal detail — not exposed as a public kwarg, so the signature is unchanged"
  - "No inter-page pacing and no retry logic added; tenacity (:105-111) and the circuit breaker already wrap every page"
  - "trading-engine per-symbol fallback retained as defence-in-depth rather than removed"
metrics:
  duration: ~15 min
  completed: 2026-08-16
  tasks: 1
  files_changed: 3
  commits: 1
---

# Quick Task 260816-qjz: Fix RES-07 bybit-connector instruments-info pagination Summary

Cursor-following pagination inside `get_instruments_info`, hard-bounded at 10 pages with a
WARNING on cap exhaustion, so the min-notional gate finally sees the whole 821-instrument
`linear` universe instead of the first alphabetical 500.

## What Was Built

`get_instruments_info` issued exactly one request. Bybit's default page size therefore capped
the `linear` response at 500 alphabetically-ordered instruments out of 821 — the response ended
mid-N, so SOLUSDT and everything after it never arrived. Because that data feeds the
trading-engine min-notional gate, a missing symbol silently failed the gate **open**, which on a
$100 account (per-trade budget $10, venue floor ~$5) is a money-path defect. The per-symbol
fallback added in `1c85781` had been masking it.

The fix is confined to the client method:

- `MAX_INSTRUMENTS_PAGES = 10` at module level (`bybit_rest_client.py:29`), so the tests import
  the bound rather than hardcoding it.
- A `for … else` loop over `range(MAX_INSTRUMENTS_PAGES)`. Each iteration builds a fresh
  `dict(params)` copy and adds `cursor` only when truthy — mirroring the house idiom at
  `get_order_history:516-517`. The copy is load-bearing: mock and httpx both retain a reference
  to the dict handed to them, so mutating one shared dict would rewrite the recorded first-page
  params.
- `cursor = result.get("nextPageCursor") or None` collapses three shapes into one falsy
  termination case: empty string (last `linear` page), absent key (`spot` never returns the
  field), and explicit `None`. Both real-world shapes therefore stop without an extra request.
- The `else` branch — reached only when the loop exhausts without `break`, i.e. the cursor is
  still truthy at the cap — logs a WARNING naming category, cap and collected count. Truncation
  is never silent.
- `limit=1000` is set internally. The signature stays `(self, category, symbol=None)` and the
  return type stays `List[Dict[str, Any]]`, so the `main.py` route passthrough and response shape
  are untouched.

`instruments_cache.py` got a **comment-only** reword: the stale claim that "bybit-connector does
not paginate" now says the connector paginates as of this fix and the per-symbol fallback is
retained as defence-in-depth. The historical SOLUSDT note survives, and the "no retries, no
backoff, no concurrency — do not add them" instruction is byte-identical. No executable line
changed (verified in the diff below).

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Cursor-following pagination in get_instruments_info | `c774638` | `bybit_rest_client.py`, `test_rest_client_comprehensive.py`, `instruments_cache.py` |

Single commit, pathspec-scoped (`git commit -F <msg> -- <3 paths>`) because a parallel executor
is working on `services/api-gateway` in the same tree and the git index is shared.

## Tests Added

Three tests appended to `TestMarketDataEndpoints`, after
`test_get_instruments_info_no_symbol_filter`:

| Test | Proves |
|------|--------|
| `test_get_instruments_info_follows_cursor_across_pages` | `await_count == 2`; call 1 carries `limit=1000` and **no** cursor; call 2 carries `cursor="cur2"`; result aggregates `["AAAUSDT", "SOLUSDT"]` in page order |
| `test_get_instruments_info_page_cap_warns` | Constant never-terminating `return_value` stops at `MAX_INSTRUMENTS_PAGES` (imported, not hardcoded) and emits a WARNING |
| `test_get_instruments_info_spot_single_call` | A result with no `nextPageCursor` key issues exactly one request |

Test A indexes `call_args_list[0]` / `[1]` rather than `call_args` — `call_args` is the *last*
call, which the single-call house pattern gets away with and a multi-page test does not.

`caplog.at_level(logging.WARNING, logger="app.bybit_rest_client")` worked as the primary path;
the plan's `patch.object(logger, "warning")` fallback was **not needed** — records propagate
fine in this suite.

## TDD Gate Compliance

The plan marks Task 1 `tdd="true"` but STEP 4 mandates exactly one `fix(...)` commit. The RED/GREEN
sequence was executed but **squashed into that single commit** per the plan, which governs over the
default two-commit TDD flow.

RED was proven empirically rather than asserted: the app file was reverted to HEAD with the new
tests in place, and the suite reported

```
FAILED ... test_get_instruments_info_follows_cursor_across_pages
FAILED ... test_get_instruments_info_page_cap_warns
2 failed, 3 passed
```

with test B failing on `ImportError: cannot import name 'MAX_INSTRUMENTS_PAGES'`. Test C (spot
single call) passes against the old code by construction — the pre-fix method made exactly one
request, so it is a **regression guard**, not a RED test. Recording that honestly rather than
claiming a 3/3 RED.

## Verification

Host run from `services/bybit-connector`, `--no-cov` mandatory (`pytest.ini` injects
`--cov --cov-branch --cov-report=html`).

```
python3 -m pytest tests/ --no-cov -q
3 failed, 373 passed, 25 skipped, 3 warnings in 19.53s
```

Targeted confirmations:

- All 5 instruments-info tests pass — the 2 pre-existing ones (`:748`, `:778`) **unmodified**,
  plus the 3 new.
- `tests/test_main.py::TestMarketDataEndpoints::test_get_instruments_info_endpoint` passes
  unmodified — the route is still a passthrough.
- `git diff --stat HEAD~1 HEAD` → exactly 3 files, 127 insertions / 10 deletions.
- `git diff --diff-filter=D HEAD~1 HEAD` → no deletions.
- `grep -n MAX_INSTRUMENTS_PAGES` → defined at `:29` (module level), referenced at `:719` and
  `:745` inside the method.
- `instruments_cache.py` diff inspected line by line: 5 comment lines out, 7 comment lines in,
  zero executable lines touched.

Per the plan, no container rebuild and no live HTTP calls were made; the post-rebuild engine
regression check belongs to the orchestrator.

## Deviations from Plan

None. The plan was executed exactly as written, including its negative constraints — no
`asyncio.sleep`, no own retry logic, no URL string-concatenation of the cursor, and no edit to
`main.py` or `tape_replay_client.py` (confirmed: `git diff --name-only` over both service trees
listed only the three intended files).

One **frontmatter discrepancy** worth flagging for a verifier: the plan's
`must_haves.key_links` entry specifies `pattern: "params\\[\"cursor\"\\]"`, but the
implementation writes `params_page["cursor"] = cursor`. The pattern predates STEP 4's per-page-copy
mandate, which explicitly requires `dict(params)` and calls the copy load-bearing. The code follows
the `<action>` text, which governs; the link is satisfied as `params_page["cursor"]`. Code was
deliberately **not** changed to match the stale regex.

One **procedural** adaptation, not a plan deviation: the PostToolUse format hook
(`.claude/scripts/format-python.sh` → `ruff format` + `ruff check --fix`) would have rewritten
these files wholesale, since none is ruff-formatted at HEAD. Measured churn before starting:

| File | Lines `ruff format` would change |
|---|---|
| `bybit_rest_client.py` | 250 |
| `test_rest_client_comprehensive.py` | 198 |
| `instruments_cache.py` | 6 |

The hook matches `Write|Edit` only, so all five edits were applied via a Bash + `pathlib`
exact-replacement script with a `count == 1` assertion per replacement. Result: 127 insertions
across three files with zero cosmetic churn and zero import-line movement
(`git diff | grep -E '^[+-](import|from)'` returned empty). Note that the repo has **no
`[tool.ruff]` section** in `pyproject.toml`, so the hook runs ruff defaults (88 cols) against a
codebase whose `pyproject.toml` configures black/isort at 100 — the two disagree, which is why
the churn is so large.

## Deferred Issues

Three pre-existing failures in the suite, **none traceable to this change** — proven by reverting
both modified `bybit-connector` files to HEAD and re-running, where all three fail identically.
Out of scope per the executor scope boundary; logged to `deferred-items.md`, not fixed.

| Test | Failure |
|---|---|
| `test_rest_client_comprehensive.py::TestCoreRequestMethods::test_make_request_success` | `TypeError: _make_request() got an unexpected keyword argument 'json_data'` — stale test against a refactored signature |
| `test_config.py::TestSettingsInitialization::test_settings_default_values` | default-value assertions vs. env |
| `test_main.py::TestErrorHandling::test_validation_exception_handling` | pre-existing |

## Known Stubs

None. No placeholder values, empty returns, or unwired data paths were introduced.

## Threat Flags

None. No new network endpoint, auth path, file access, or schema change was introduced — the
route surface is unchanged. The three threats in the plan's register are all mitigated as
specified: the loop is hard-bounded (T-qjz-01), the cursor is opaque and passed only through the
`params` dict for httpx to encode rather than concatenated into the URL (T-qjz-02), and cap
exhaustion warns instead of truncating silently while the trading-engine fallback stays in place
(T-qjz-03).

## Follow-Ups for the Orchestrator

- `bybit-connector` needs a rebuild + restart before the fix is live; the running container still
  serves the single-request method. Stale in-memory state is the top false-pass in this repo.
- Post-rebuild, the natural runtime proof is that `InstrumentsCache` populates SOLUSDT from the
  **bulk** path with zero per-symbol fallback calls.
- STATE.md was intentionally **not** updated and ROADMAP.md was **not** touched, per the launch
  constraints. This SUMMARY is left uncommitted.

## Self-Check: PASSED

- `services/bybit-connector/app/bybit_rest_client.py` — FOUND, contains `MAX_INSTRUMENTS_PAGES`
  at module level
- `services/bybit-connector/tests/test_rest_client_comprehensive.py` — FOUND, contains
  `MAX_INSTRUMENTS_PAGES` and all three new tests
- `services/trading-engine/app/services/instruments_cache.py` — FOUND, comment-only diff
- `.planning/quick/260816-qjz-fix-res-07-bybit-connector-instruments-i/260816-qjz-SUMMARY.md` — FOUND
- Commit `c774638` — FOUND in `git log`, 3 files, 127 insertions / 10 deletions
