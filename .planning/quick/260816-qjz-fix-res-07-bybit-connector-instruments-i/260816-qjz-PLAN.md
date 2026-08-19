---
phase: quick-260816-qjz
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - services/bybit-connector/app/bybit_rest_client.py
  - services/bybit-connector/tests/test_rest_client_comprehensive.py
  - services/trading-engine/app/services/instruments_cache.py
autonomous: true
requirements: [RES-07]

must_haves:
  truths:
    - "A single bulk get_instruments_info(category='linear') call returns instruments past alphabetical position 500 (the SOLUSDT class), not just page 1"
    - "Pagination terminates on an empty/absent nextPageCursor without an extra request"
    - "Hitting the page cap emits a WARNING — the method never truncates silently"
    - "Spot shape (no nextPageCursor key in the result) issues exactly one request"
    - "Existing instruments-info tests and the main.py route test pass unchanged"
  artifacts:
    - path: "services/bybit-connector/app/bybit_rest_client.py"
      provides: "cursor-following loop inside get_instruments_info"
      contains: "MAX_INSTRUMENTS_PAGES"
    - path: "services/bybit-connector/tests/test_rest_client_comprehensive.py"
      provides: "multi-page aggregation, page-cap warning, and spot single-call tests"
      contains: "MAX_INSTRUMENTS_PAGES"
  key_links:
    - from: "get_instruments_info"
      to: "_request"
      via: "per-page params dict carrying cursor"
      pattern: "params\\[\"cursor\"\\]"
---

<objective>
Fix RES-07: `bybit-connector`'s `get_instruments_info` issues exactly one request, so Bybit's
default page size caps the `linear` response at 500 alphabetically-ordered instruments. 821 exist;
everything past mid-N (SOLUSDT included) never arrives. The trading-engine min-notional gate reads
this data, so a missing symbol silently failed the gate open until the per-symbol fallback
(`1c85781`) started masking it.

Purpose: money-adjacent correctness — instruments-info is the data source for the min-notional
gate on a $100 account, where per-trade budget ($10) sits close to the venue floor (~$5).
Output: cursor-following pagination inside the client method only. Signature, route, and response
shape unchanged.
</objective>

<execution_context>
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/workflows/execute-plan.md
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@services/bybit-connector/app/bybit_rest_client.py
@services/bybit-connector/tests/test_rest_client_comprehensive.py

<diagnosis>
Verified live 2026-08-16 — do NOT re-verify, the executor makes no live calls:
- Bulk `linear` call returns exactly 500 items, alphabetical page 1, ends mid-N, SOLUSDT absent.
- Bybit direct with `limit=1000` → 821 items, SOLUSDT present, `nextPageCursor` empty string.
- With `limit=500` the cursor chain is real: page 2 = 321 items including SOLUSDT, then empty cursor terminates.
- `spot` category result has NO `nextPageCursor` key at all.
- Route `services/bybit-connector/app/main.py:980-1013` is a passthrough. The defect is entirely
  inside the client method — do not touch the route.
</diagnosis>

<interfaces>
Relevant existing contracts in `services/bybit-connector/app/bybit_rest_client.py`
(read them in place; line refs are for orientation, no code is reproduced here):

- `_request(method, endpoint, params=None, data=None, auth_required=True) -> Dict[str, Any]`
  declared at :113, wrapped by the tenacity `@retry` decorator at :105-111
  (3 attempts, exponential backoff, reraise). Retries and the circuit breaker are therefore
  inherited for free by every page — add no retry logic of your own.
- `_handle_response` at :274 returns `data.get("result", {})` — i.e. `_request` hands back the
  full Bybit `result` object, so `nextPageCursor` sits as a sibling key next to `list`.
- `get_order_history` at :490-521 is the house cursor idiom: build a `params` dict, add
  `cursor` only when truthy (:516-517), pass `params=` as a keyword.
- `get_instruments_info` at :678-706 is the fix site. Current body builds `params`, optionally
  adds `symbol`, makes one `_request` call with `auth_required=False`, returns `result.get("list", [])`.
- Module logger is `logging.getLogger(__name__)` at :23 → logger name `app.bybit_rest_client`.

Test house pattern (`services/bybit-connector/tests/test_rest_client_comprehensive.py`):
`patch.object(client, '_request', new_callable=AsyncMock)`, then read
`mock_request.call_args[1]["params"]`. Existing instruments tests live at :748 and :778.
`pytest.ini` sets `asyncio_mode = auto`; existing tests still carry `@pytest.mark.asyncio` — match them.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Cursor-following pagination in get_instruments_info</name>

  <files>
services/bybit-connector/app/bybit_rest_client.py
services/bybit-connector/tests/test_rest_client_comprehensive.py
services/trading-engine/app/services/instruments_cache.py
  </files>

  <behavior>
Three new tests in `test_rest_client_comprehensive.py`, placed immediately after the existing
`test_get_instruments_info_no_symbol_filter` (:778-790), inside the same test class:

- Test A — multi-page aggregation. `_request` AsyncMock with a two-element `side_effect`:
  page 1 = `{"list": [{"symbol": "AAAUSDT"}], "nextPageCursor": "cur2"}`,
  page 2 = `{"list": [{"symbol": "SOLUSDT"}], "nextPageCursor": ""}`.
  Assert: `mock_request.await_count == 2`; `call_args_list[0][1]["params"]["limit"] == 1000` and
  `"cursor" not in call_args_list[0][1]["params"]`; `call_args_list[1][1]["params"]["cursor"] == "cur2"`;
  returned list has 2 entries with symbols `["AAAUSDT", "SOLUSDT"]` in page order.

- Test B — page cap emits a WARNING and stops. `_request` AsyncMock with a constant
  `return_value` of `{"list": [{"symbol": "X"}], "nextPageCursor": "always-more"}` (a never-ending
  chain). Assert: `mock_request.await_count == MAX_INSTRUMENTS_PAGES` (import the constant from
  `app.bybit_rest_client`, never hardcode 10), returned list length equals `MAX_INSTRUMENTS_PAGES`,
  and one WARNING was logged.

- Test C — spot shape, single call. `_request` AsyncMock returning
  `{"category": "spot", "list": [{"symbol": "BTCUSDT"}]}` with NO `nextPageCursor` key.
  Assert: `mock_request.await_count == 1` and the returned list has 1 entry.

Existing tests must keep passing untouched: :768-773 asserts a key subset of `params`
(the added `limit` key is invisible to it) and :788 asserts `"symbol" not in params`.
  </behavior>

  <action>
Implement in this order. Everything below is a hard constraint, not a preference.

STEP 1 — `services/bybit-connector/app/bybit_rest_client.py`.

Add a module-level constant `MAX_INSTRUMENTS_PAGES = 10` near the top of the module, after the
`logger = logging.getLogger(__name__)` line at :23 and before the `class BybitRestClient`
declaration. Module level, not a class attribute — the tests import it from the module.

Rewrite the body of `get_instruments_info` (:678-706) as a cursor-following loop. Keep the
signature exactly as it is: two parameters, `category: str` and `symbol: Optional[str] = None`.
Do NOT expose `limit` or `cursor` as public kwargs — `limit=1000` is an internal detail.
Keep the return type `List[Dict[str, Any]]`.

Loop mechanics:
- Build the base `params` dict once with `category`, `limit` set to 1000, and `symbol` only when
  truthy — same shape as today plus `limit`.
- Accumulate into a local list. Track `cursor`, initialised to `None`.
- Use a `for` loop bounded by `range(MAX_INSTRUMENTS_PAGES)` with an attached `else` clause.
- Inside each iteration build a fresh per-page dict via `dict(params)` (or `params.copy()`), and
  add `params_page["cursor"] = cursor` only when `cursor` is truthy — mirror the idiom at
  `get_order_history:516-517`. THE PER-PAGE COPY IS LOAD-BEARING, NOT STYLISTIC: `AsyncMock`
  records a reference to the dict it was called with, so mutating one shared dict in place would
  make `call_args_list[0]` show the final cursor state and silently break Test A's "call 1 carries
  no cursor" assertion. Do not "optimize" the copy away.
- Call `_request("GET", "/v5/market/instruments-info", params=params_page, auth_required=False)`.
  `params=` and `auth_required=` MUST stay keyword arguments — the surviving tests at :770-773
  read `mock_request.call_args[1]["params"]`, and switching to positional args raises `KeyError`.
- Extend the accumulator with `result.get("list", [])` (use `or []` semantics so an explicit
  `None` cannot blow up `extend`).
- Read the next cursor as `cursor = result.get("nextPageCursor") or None`. The `or None` collapses
  empty-string, absent-key and explicit-`None` into one falsy case — this is why spot (no cursor
  field) and the last linear page (empty string) both terminate identically. `break` when falsy.
- On the `for ... else` branch (loop exhausted without `break`, i.e. cursor still truthy at the
  cap), emit `logger.warning(...)` naming `category`, `MAX_INSTRUMENTS_PAGES`, and the number of
  instruments collected, and state that the result may be truncated. Never truncate silently —
  a short instruments list is exactly how the min-notional gate fails open.
- Return the accumulated list.

Update the docstring to state that the method follows `nextPageCursor` and is capped at
`MAX_INSTRUMENTS_PAGES` pages. Keep the existing `fundingInterval` / tickSize / minOrderQty notes.

Explicitly forbidden in this step: any `asyncio.sleep` or other inter-page pacing (pacing lives in
callers, and the tenacity retry at :105-111 plus the circuit breaker already cover transport
failures); any retry/backoff logic of your own; string-concatenating the cursor into the URL
(pass it through the `params` dict — httpx encodes it, verified tolerant live); any edit to
`services/bybit-connector/app/main.py` (the route is a passthrough); any edit to
`services/bybit-connector/app/tape_replay_client.py:448` (its stub shape is pinned by
`tests/integration/test_bybit_connector_tape_preserved.py:289-291`).

STEP 2 — `services/bybit-connector/tests/test_rest_client_comprehensive.py`.

Add the three tests described in `<behavior>` directly after the existing
`test_get_instruments_info_no_symbol_filter` block ending at :790, inside the same class, using
the house pattern `patch.object(client, '_request', new_callable=AsyncMock)` and closing with
`await client.close()` like its neighbours. Carry `@pytest.mark.asyncio` on each for consistency
with the surrounding file.

Test-specific traps:
- Test A must assert against `mock_request.call_args_list[0]` and `[1]`, NOT `mock_request.call_args`.
  `call_args` is the LAST call; the single-call house pattern at :770 gets away with it, a
  multi-page test does not.
- Test B must use a constant `return_value`, not a ten-element `side_effect` list — a constant
  never-terminating page proves the cap actually bounds the loop rather than the fixture running dry.
  Import `MAX_INSTRUMENTS_PAGES` from `app.bybit_rest_client` and assert against it; hardcoding 10
  makes the test lie if the constant changes.
- Test B's warning assertion: use `caplog.at_level(logging.WARNING, logger="app.bybit_rest_client")`
  and assert a WARNING record was captured. If caplog comes back empty — `tests/conftest.py` does
  `from app.main import app` at import time, so app logging config runs during collection and may
  set `propagate=False`, which `caplog.set_level` cannot repair — fall back immediately to
  `patch.object(bybit_rest_client.logger, "warning")` and assert it was called once. Do not burn
  turns debugging caplog propagation; either assertion satisfies the requirement.
- Do NOT add a module-level `skip` or `xfail` to this file for any reason.

STEP 3 — `services/trading-engine/app/services/instruments_cache.py` (comment-only, note the
`/services/` path segment).

The comment at :190-194 asserts "bybit-connector does not paginate Bybit's instruments-info, so
the bulk response above is capped at page 1 (500 items)". That statement is now stale. Reword it
to say the connector paginates as of this fix and the per-symbol fallback is retained as
defence-in-depth for symbols still absent from the bulk response. Keep the historical note about
SOLUSDT-class symbols having been observed missing, and keep the "no retries, no backoff, no
concurrency — do not add them" instruction at :198-199 verbatim.

Change NOT ONE LINE OF EXECUTABLE CODE in this file. The per-symbol fallback loop stays exactly
as it is — do not weaken, shortcut, or delete it.

STEP 4 — commit. Pathspec-scoped (parallel agents share one git index; a bare `git add` sweeps in
siblings' staged files):

  git commit -m "fix(bybit-connector): paginate instruments-info with cursor following" -- services/bybit-connector/app/bybit_rest_client.py services/bybit-connector/tests/test_rest_client_comprehensive.py services/trading-engine/app/services/instruments_cache.py

Never `git add -A`. Never run bare `git status` in this repo — 3.2 GB over an NTFS/WSL mount, it
exceeds 60s. Do not rebuild any container and do not make live HTTP calls; the post-rebuild engine
regression check belongs to the orchestrator, not to this task.
  </action>

  <verify>
    <automated>cd services/bybit-connector && python3 -m pytest tests/ --no-cov -q</automated>
  </verify>

  <done>
- `MAX_INSTRUMENTS_PAGES = 10` exists at module level in `bybit_rest_client.py`.
- `get_instruments_info` follows `nextPageCursor`, signature still `(self, category, symbol=None)`.
- Three new tests pass: multi-page aggregation (await_count 2, call-1 limit 1000 with no cursor,
  call-2 carries the cursor, aggregated list), page cap (await_count == MAX_INSTRUMENTS_PAGES +
  WARNING emitted), spot single call.
- Pre-existing tests at :748 and :778 pass unmodified; `tests/test_main.py` route test at :612-636
  passes unmodified; whole `services/bybit-connector` suite is green with `--no-cov`.
- `instruments_cache.py` diff is comment-only (verify with `git diff --stat` — no executable line changed).
- One commit landed with message `fix(bybit-connector): paginate instruments-info with cursor following`.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| bybit-connector → Bybit public REST | Untrusted remote response body; `list` and `nextPageCursor` are attacker-shaped from the client's perspective |
| bybit-connector → trading-engine min-notional gate | Instrument specs sourced here size real (paper) orders on a $100 account |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-qjz-01 | Denial of Service | `get_instruments_info` cursor loop | mitigate | `MAX_INSTRUMENTS_PAGES = 10` hard-bounds the loop; a malformed or adversarial never-terminating cursor chain cannot spin the connector indefinitely |
| T-qjz-02 | Tampering | `nextPageCursor` value from the remote body | mitigate | Cursor treated as opaque and passed only through the `params` dict for httpx to encode — never string-concatenated into the URL, so it cannot inject query parameters |
| T-qjz-03 | Information Disclosure (silent data loss) | truncated instruments list → min-notional gate | mitigate | `for/else` emits a WARNING naming category and collected count when the cap is hit; truncation is never silent, and the trading-engine per-symbol fallback is retained as defence-in-depth |

No package-manager installs in this plan — no `T-qjz-SC` row required.
</threat_model>

<verification>
1. `cd services/bybit-connector && python3 -m pytest tests/ --no-cov -q` — whole suite green.
   `--no-cov` is MANDATORY: `pytest.ini` injects `--cov --cov-branch --cov-report=html`, which
   blows the time budget. If the full-suite runtime is excessive, narrow to
   `python3 -m pytest tests/test_rest_client_comprehensive.py tests/test_main.py --no-cov -q`.
2. `git diff --stat HEAD~1` shows exactly three files; `instruments_cache.py` changes are
   comment lines only.
3. `grep -n "MAX_INSTRUMENTS_PAGES" services/bybit-connector/app/bybit_rest_client.py` shows the
   constant defined at module level and referenced inside `get_instruments_info`.
</verification>

<success_criteria>
- One bulk `linear` call now aggregates every page instead of stopping at 500 items, so
  SOLUSDT-class symbols reach the min-notional gate through the bulk path.
- Termination is correct for both shapes: empty-string cursor (linear last page) and absent
  cursor key (spot) each stop without an extra request.
- Cap exhaustion warns rather than truncating silently.
- No change to the method signature, the `main.py` route, the tape-replay stub, or the
  trading-engine fallback logic.
- Single pathspec-scoped commit.
</success_criteria>

<output>
Create `.planning/quick/260816-qjz-fix-res-07-bybit-connector-instruments-i/260816-qjz-SUMMARY.md` when done.
</output>
