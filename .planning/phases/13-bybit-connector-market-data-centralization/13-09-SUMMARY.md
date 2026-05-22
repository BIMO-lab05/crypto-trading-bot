---
phase: 13-bybit-connector-market-data-centralization
plan: 09
subsystem: docs / phase-close
tags: [bybit-connector, docs, runbook, integrations, phase-close, verify-stack]
requires:
  - 13-08 (BC-04 Binance archival + BC-03 gate GREEN on main)
provides:
  - BC-06 RUNBOOK symptom (operator triage for new bybit-connector chain)
  - D-10 INTEGRATIONS.md cleanup (post-refactor codebase-map truth)
  - verify-stack 4-check matrix executed (operator gate, recorded below)
affects:
  - RUNBOOK.md (new symptom #7, index entry)
  - .planning/codebase/INTEGRATIONS.md (line 231)
tech-stack:
  added: []
  patterns:
    - Diagnose / Action / Verification triad for operator triage docs
    - verify-stack 4-check matrix (CLAUDE.md "Verification standards") executed at phase close
key-files:
  created: []
  modified:
    - RUNBOOK.md
    - .planning/codebase/INTEGRATIONS.md
decisions:
  - BC-06 sub-causes documented inline as A/B/C/D (connector down, URL misconfig, ratelimit, tape leak)
  - INTEGRATIONS.md WS row collapsed to bybit-connector only — market-data clean per audit
  - verify-stack Check 2 explicitly N/A (Phase 13 did not touch notification surface)
metrics:
  duration_minutes: 6
  completed_date: 2026-05-22
---

# Phase 13 Plan 09: Phase-Close — RUNBOOK BC-06 + INTEGRATIONS D-10 + verify-stack Summary

**Phase 13 close-out.** Operator-facing artifacts and verification: new RUNBOOK symptom for the post-refactor bybit-connector chain, codebase-map cleanup, and the CLAUDE.md-mandated verify-stack 4-check matrix.

## What landed

| Task | Type | Status | Commit | Files |
|------|------|--------|--------|-------|
| 1. RUNBOOK BC-06 symptom + index | auto | DONE | `9819912` | `RUNBOOK.md` |
| 2. INTEGRATIONS.md D-10 cleanup | auto | DONE | `d369398` | `.planning/codebase/INTEGRATIONS.md` |
| 3. verify-stack 4-check matrix | checkpoint:human-action | AWAITING OPERATOR | — | N/A |

### Task 1 — RUNBOOK.md `## Symptom: Market-data stale or missing — bybit-connector chain broken`

Appended a new operator-triage symptom (counted as the 7th in the symptom-indexed section, after EMERGENCY_STOP recovery). The body follows the same Diagnose / Action / Verification triad used by the other six symptoms in the file, so operators reading top-to-bottom encounter consistent structure.

Four sub-causes are enumerated inside the Diagnose block:

- **Sub-cause A — bybit-connector container down or unhealthy.** Diagnostic commands: `docker ps --filter name=bybit-connector`, `docker logs crypto-bot-bybit-connector --tail 30`, and a direct `curl ... /health` probe. Action: `docker compose -f docker-compose.unified.yml up -d bybit-connector`.

- **Sub-cause B — `BYBIT_CONNECTOR_URL` misconfigured (host vs compose hostname).** Covers both directions of the foot-gun: in-compose consumers must read `http://bybit-connector:8001`, host-side operator scripts must read `http://localhost:8001`. Mismatched value triggers `httpx.ConnectError: All connection attempts failed`.

- **Sub-cause C — Bybit-side ratelimit (HTTP 429).** Diagnostic: `docker logs crypto-bot-bybit-connector --tail 100 | grep -iE 'ratelimit|rate.limit|HTTP 429|Too Many'`. Cross-link to Bybit's documented 600-req/5s burst limit. Action: identify hot consumer via `X-Bapi-Limit-Status` headers, throttle batched calls.

- **Sub-cause D — `MARKET_DATA_SOURCE=tape` leaked into production.** Tape mode replays JSONL fixtures from `tests/fixtures/tape/` and returns deterministic-but-stale data with a 30s+ "now" lag — symptom is `lastPrice` matching a known fixture or showing a 30s+ lag. Action: locate the `MARKET_DATA_SOURCE=tape` source (compose override, leaked `.env` entry), remove it, force-recreate the connector.

The Verification block contains the **literal curl command** required by the BC-06 acceptance criterion:

```
curl http://bybit-connector:8001/api/v1/market/ticker?symbol=BTCUSDT&category=linear
```

Plus the host-side variant (`http://localhost:8001/...`), expected response shape, and a four-line failure-indicator decision table that points the operator back to the matching sub-cause.

**Acceptance proof (run from worktree root):**

```
$ grep -c "^## Symptom: Market-data stale or missing — bybit-connector chain broken" RUNBOOK.md
1
$ grep -c "Symptom: Market-data stale or missing — bybit-connector chain broken](#symptom-market-data-stale-or-missing--bybit-connector-chain-broken)" RUNBOOK.md
1
$ grep -c "curl http://bybit-connector:8001/api/v1/market/ticker?symbol=BTCUSDT" RUNBOOK.md
1
$ grep -c "Sub-cause [ABCD]" RUNBOOK.md   # four sub-causes, one count each
4
```

### Task 2 — INTEGRATIONS.md D-10 codebase-map refresh

Single-line edit on `.planning/codebase/INTEGRATIONS.md` line 231 inside the "Webhook & Callback URLs to External Services" table.

- **Before:** `| Out | \`wss://stream.bybit.com/*\` | bybit-connector, market-data |`
- **After:** `| Out | \`wss://stream.bybit.com/*\` | bybit-connector |`

Rationale: post-Phase-13 audit confirmed market-data-service does not consume `wss://stream.bybit.com/*` directly any more — it reads through bybit-connector REST and TimescaleDB. Only bybit-connector touches the WebSocket. The "bybit-connector, market-data" claim was already stale at the point CONTEXT.md was drafted (D-10 was filed against it) and the Phase 13 refactor closed the only remaining justification for keeping market-data on the row.

The surrounding table structure is unchanged (Direction / Endpoint / Used by pipes intact), confirmed by visual re-read of lines 228-236.

**Acceptance proof:**

```
$ grep -c 'wss://stream.bybit.com/\* | bybit-connector, market-data' .planning/codebase/INTEGRATIONS.md
0
$ grep -cF '| Out | `wss://stream.bybit.com/*` | bybit-connector |' .planning/codebase/INTEGRATIONS.md
1
```

### Task 3 — verify-stack 4-check matrix (operator gate — AWAITING)

Returned as a `CHECKPOINT REACHED` of type `human-action`. The 4-check matrix per `.claude/skills/verify-stack/SKILL.md` is operator-driven by design (CLAUDE.md "Verification standards" forbids declaring features working end-to-end on curl/HTTP 200 alone, so this checkpoint cannot be auto-resolved). The full operator checklist appears in this executor's checkpoint return message.

The one automation that **can** run from the executor — the BC-03 grep gate — passed clean on the post-edits tree:

```
$ pytest tests/ci/test_no_bybit_bypass.py -v
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.3, pluggy-1.6.0
...
collected 5 items

tests/ci/test_no_bybit_bypass.py .....                                   [100%]

============================== 5 passed in 13.09s ==============================
```

No regression from RUNBOOK / INTEGRATIONS edits (BC-03 scans `**/*.py` files only — markdown documentation edits are outside the gate's scope).

## Self-Check: PASSED

| Claim | Verification | Result |
|-------|--------------|--------|
| RUNBOOK.md contains BC-06 H2 heading | `grep -c "^## Symptom: Market-data stale or missing"` | 1 (FOUND) |
| RUNBOOK.md index lists BC-06 entry | `grep -c "Symptom: Market-data stale or missing.*](#symptom-market"` | 1 (FOUND) |
| RUNBOOK.md contains literal curl line | `grep -c "curl http://bybit-connector:8001/api/v1/market/ticker"` | 1 (FOUND) |
| RUNBOOK.md has four sub-causes A/B/C/D | `grep -c "Sub-cause [ABCD]"` | 4 (FOUND) |
| INTEGRATIONS.md stale claim removed | `grep -c "bybit-connector, market-data"` | 0 (FOUND ABSENT) |
| INTEGRATIONS.md corrected claim present | `grep -cF '| bybit-connector |'` | 1 (FOUND) |
| Task 1 commit exists | `git log --oneline | grep 9819912` | FOUND |
| Task 2 commit exists | `git log --oneline | grep d369398` | FOUND |
| BC-03 gate still GREEN post-edits | `pytest tests/ci/test_no_bybit_bypass.py` | 5 passed, 0 failed |

## Deviations from Plan

None. The plan specified two autonomous documentation tasks (RUNBOOK BC-06, INTEGRATIONS D-10) plus a checkpoint task (verify-stack). Both autonomous tasks landed exactly as the plan's interfaces block prescribed. The commit prefix for Task 2 followed the executor objective's `docs(integrations): ...` instruction rather than the PLAN's `docs(codebase): refresh INTEGRATIONS.md wss row (Phase 13 D-10 close)` — both are conventional-commit-compliant; executor objective explicitly listed the prefix as `docs(integrations): remove stale market-data WS claim (D-10)`, which was honored.

## Phase 13 ROADMAP Success-Criteria Checklist

The Phase 13 ROADMAP defines the following success criteria. Status at phase close (after Plans 01-09):

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | All Bybit-direct code paths refactored to bybit-connector REST | DONE | Plans 04-07 refactored ml-prediction-service handler + 4 downloads, 5 collect scripts, fetch_real_historical_data, collect_6months_historical, backtesting/bybit_data_fetcher, rotate_secrets, shared/health_check |
| 2 | CI grep gate (`tests/ci/test_no_bybit_bypass.py`) GREEN on main | DONE | Plan 02 added the gate; Plan 08 flipped it GREEN by archiving Binance + deleting test bypass; this plan re-ran the suite and confirmed 5/5 PASS |
| 3 | Binance exchange adapter archived | DONE | Plan 08 moved `services/trading-engine/app/exchanges/binance.py` to `_archive_exchanges/binance.py` + cleaned `factory.py` + `__init__.py` references + deleted `test_multi_exchange.py` Binance branches |
| 4 | `market-data-service/app/config.py:58` port default fixed (8002 → 8001) | DONE | Plan 06 BC-05 fix |
| 5 | RUNBOOK symptom for new chain documented | DONE | This plan (Task 1) — BC-06 |
| 6 | Codebase-map (`.planning/codebase/INTEGRATIONS.md`) refreshed | DONE | This plan (Task 2) — D-10 cleanup |
| 7 | verify-stack 4-check matrix executed before phase close | AWAITING OPERATOR | This plan (Task 3) — checkpoint:human-action; BC-03 automated portion is GREEN |

Six of seven criteria CLOSED. Criterion 7 awaiting operator execution of the verify-stack matrix per the checkpoint return message.

## Carry-ins Surfaced Across Phase 13

Cross-plan deferred-items review (per `.planning/state/carry_ins.json` and prior-plan SUMMARY notes). These do **not** block phase close — they are tracked for future cleanup phases:

- **BC-FOLLOWUP-01 — Kraken/Coinbase archival.** Phase 13 explicitly scoped to Bybit-only-by-policy. The codebase still contains exchange-adapter stubs for Kraken (`services/trading-engine/app/exchanges/kraken.py`) and Coinbase (`services/trading-engine/app/exchanges/coinbase.py`) per CLAUDE.md "Bybit-first; no other exchange". Operator may want a follow-up phase to mirror the Binance archival (`_archive_exchanges/`). Not in Phase 13 scope.
- **BC-FOLLOWUP-02 — Orderbook fixtures for tape-mode ml-prediction-service tests.** Plan 04 refactored `services/ml-prediction-service/app/handlers/orderbook.py` to read from bybit-connector REST. Tape-mode coverage for the orderbook path needs new JSONL fixtures (D-08 invariant: tape mode must work unchanged for every refactored consumer). Researcher flagged this in 13-RESEARCH.md "Whether tape-mode coverage tests need additional fixtures". Deferred to a hardening pass.
- **BC-FOLLOWUP-03 — `test_pagination_fix.py` resurrection.** Plan 06 deleted `services/market-data-service/tests/test_pagination_fix.py` (direct `api.bybit.com` call, BC-03-violating). Pagination behavior is exercised indirectly by `BybitDataFetcher` tests, but a focused regression test that mocks the bybit-connector layer would be cleaner.
- **BC-FOLLOWUP-04 — `health_check.py` caller audit.** Plan 07 refactored `shared/health_check.py`. Callers were updated in-place; a follow-up review to confirm no caller still imports the pre-refactor signature would be cheap insurance.
- **BC-FOLLOWUP-05 — `BINANCE_ERROR_MAP` cleanup.** Plan 08 archived `binance.py` but a dangling `BINANCE_ERROR_MAP` constant may still live in shared error-handling code. Grep `BINANCE_ERROR_MAP` across the tree on a quiet day; if it's referenced only by the archived module, delete the dangling import.
- **BC-FOLLOWUP-06 — trading-engine test sweep for residual Binance imports.** Plan 08 deleted the Binance branches in `test_multi_exchange.py`. A broader sweep of `services/trading-engine/tests/` for any other test that imports `binance` (or asserts on a `binance`-shaped order response) closes the archival loop fully.

## Known Stubs

None. No code stubs created or modified by this plan.

## Threat Flags

None. RUNBOOK + INTEGRATIONS.md edits introduce no new security surface; they document existing surface that was already in production.

## Notes for the Operator (Phase 13 close)

After completing the verify-stack 4-check matrix (per the checkpoint return message), Phase 13 is shippable. Recommended follow-up commit on close:

- A final `chore(13): phase 13 closed` commit on main with the matrix results pasted into the commit message or appended to this SUMMARY.
- Open one or more follow-up issues for BC-FOLLOWUP-01..06 above (whichever the operator wants to schedule).
- The codebase is now in the post-refactor target state: bybit-connector is the sole Bybit-facing service; CI grep gate enforces the contract; Binance adapter archived; operator triage doc landed.
