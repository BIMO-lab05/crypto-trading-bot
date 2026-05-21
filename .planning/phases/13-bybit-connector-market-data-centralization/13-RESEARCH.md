# Phase 13: Bybit-Connector Market-Data Centralization - Research

**Researched:** 2026-05-21
**Domain:** Repo-wide refactor — centralize all Bybit access through one service + CI grep gate + Binance archival
**Confidence:** HIGH (all decisions pre-locked in CONTEXT D-01..D-09; refactor templates already exist in-repo; CI grep precedent verified)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Full scope — every Python file in the repo with direct Bybit access is refactored: `services/`, `scripts/`, `backtesting/`, `infrastructure/scripts/`, tests. No partial-scope shortcuts.
- **D-02:** Binance exchange adapter (`services/trading-engine/app/exchanges/binance.py`) is archived as part of this phase per operator policy ("I will not use binance just bybit"). Move under `_archive_exchanges/binance.py` similar to LSTM archival; remove from `services/trading-engine/app/exchanges/factory.py` (line 62, 189) and `services/trading-engine/app/exchanges/__init__.py` (lines 23, 213, 329, 330, 513); remove Binance branches in `services/trading-engine/tests/test_multi_exchange.py`.
- **D-03:** Bypass sites consume **bybit-connector REST directly** (via `httpx` to `http://bybit-connector:8001/api/v1/market/...`). No intermediary through `market-data-service`.
- **D-04:** Scripts require bybit-connector container running. Fail-fast if `BYBIT_CONNECTOR_URL` unreachable; explicit error pointing operator at `docker compose up bybit-connector`. No `--direct-bybit` escape hatch.
- **D-05:** Gate scope is **`**/*.py` files outside `services/bybit-connector/`**. Patterns banned: `from pybit`, `import pybit`, `api.bybit.com`, `wss://stream.bybit`, `api-testnet.bybit`. Config YAML, markdown docs, helm values, network policies — NOT gated.
- **D-06:** Gate test (`tests/ci/test_no_bybit_bypass.py`) is a grep + AST check. Green on `main` post-refactor. Required in `.github/workflows/` so PRs that re-introduce bypass cannot merge.
- **D-07:** `infrastructure/scripts/rotate_secrets.py` is in scope — refactor lines 232-234 (`from pybit.unified_trading import HTTP` + manual URL switch) to use `bybit-connector /api/v1/account/balance` for the post-rotation auth ping.
- **D-08:** Bybit-connector's tape-replay mode (`MARKET_DATA_SOURCE=tape`, fixtures at `tests/fixtures/tape/`, `POST /admin/tape/reset`) MUST work unchanged after refactor. Every refactored consumer hitting bybit-connector REST inherits tape-mode for free.
- **D-09:** Fix `services/market-data-service/app/config.py:58` default `bybit_connector_url="http://localhost:8002"` → `"http://localhost:8001"`.

### Claude's Discretion

- Refactor ordering across services/scripts/backtesting/infra — planner sequencing decision
- Whether tape-mode coverage tests need additional fixtures (e.g., orderbook tape data) — researcher investigated; see Tape-Mode Coverage Gap below
- Whether bybit-connector needs new REST endpoints — researcher investigated; answer: **no** (see Endpoint Mapping below)
- Wave grouping for parallel execution — planner

### Deferred Ideas (OUT OF SCOPE)

- WS-01..04 original phase 13 scope (server `/ws/metrics` push + `useWsSubscription` hook) — rejected by operator 2026-05-21; v2 candidate at earliest
- Trading-engine order placement centralization (`services/trading-engine/app/exchanges/bybit_adapter.py` audit) — separate phase
- INTEGRATIONS.md codebase-map refresh (stale claim on market-data WS line 231) — rolled into phase 13 close
- Sentiment service's cryptocompare news fetch — sentiment ≠ market-data; future policy decision
- `tier1_monitor.py` CoinGecko cross-source divergence — NEVER migrate; deliberate non-Bybit safety guard

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BC-01 | Audit producing `.planning/evidence/BC-01/bybit-bypass-audit.json` enumerating every Bybit-direct site | Researcher found **18 in-scope files** (vs. 9 in initial ROADMAP audit); see "Expanded Bypass Inventory" below. JSON shape pre-specified in CONTEXT. |
| BC-02 | Refactor every BC-01 hit to bybit-connector REST | Endpoint mapping table below; template = `services/market-data-service/app/fetcher.py:50-246` `BybitDataFetcher` class |
| BC-03 | CI grep gate `tests/ci/test_no_bybit_bypass.py` green on `main`; required in `.github/workflows/` | Pattern reuse: `tests/integration/test_preflight_grep_gates.py` (Phase 8) + `services/tournament-harness/tests/integration/test_tourn07_grep_gate.py` (Phase 3); CONTEXT-cited `tests/ci/test_no_new_setinterval_polling.py` does NOT exist (deferred-WS artifact); use Phase 8/Phase 3 idiom |
| BC-04 | Archive `services/trading-engine/app/exchanges/binance.py` to `_archive_exchanges/`; clean factory/init/test references | Archival precedent: `services/ml-prediction-service/models/_archive_lstm/` (May 2026 cleanup); production import chain verified — `app.exchanges.binance` is only imported from `factory.py:62`, `__init__.py:329-336`, and the `pytest.mark.skip`-d `test_multi_exchange.py`; trading-engine `main.py` imports nothing from `app.exchanges`; no runtime ImportError risk |
| BC-05 | Fix `services/market-data-service/app/config.py:58` default port | One-line edit; `bybit_connector_url: str = Field(default="http://localhost:8001")` |
| BC-06 | RUNBOOK Symptom #N "Market-data stale or missing — bybit-connector chain broken" with Diagnose/Action/Verification covering connector-down / env-misconfig / Bybit ratelimit / accidental tape mode | RUNBOOK.md currently has 6 symptoms ending at "EMERGENCY_STOP recovery"; new symptom is #7 (zero-indexed in TOC) |
| BC-07 | Integration test `tests/integration/test_bybit_connector_tape_preserved.py` asserts MARKET_DATA_SOURCE=tape works for refactored consumers | **Coverage gap identified**: `services/bybit-connector/app/tape_replay_client.py:206-218` already stubs `get_orderbook`/`get_recent_trades`/`get_funding_rate_history`/`get_instruments_info` to return empty payloads. ml-prediction orderbook handler (the only orderbook consumer in scope) will receive empty `{"a":[], "b":[], "ts":0, "u":0}` under tape — technically tape-preserves but needs explicit assertion that empty-but-shape-correct data does not crash the handler |

</phase_requirements>

## Summary

Phase 13 is a **refactor + gate** phase, not a feature phase. Every decision is locked in CONTEXT. The research surface is narrow: confirm the refactor template works for each consumer class (service, script, test, infra utility), map each bypass site to its replacement bybit-connector REST endpoint, identify tape-mode coverage gaps, and surface the CI grep gate's precedent file. No library choices, no architecture invention.

Key finding the planner needs: **the initial ROADMAP audit undercounted bypass sites**. Repo-wide grep finds 18 in-scope Python files (vs. 9 in the audit), including 3 additional download scripts in `ml-prediction-service/`, 3 additional collection scripts in `scripts/`, and one diagnostic probe `shared/health_check.py:771` that currently health-checks Bybit directly. BC-01's audit artifact must enumerate all 18 + the 1 exception (`scripts/tape/capture_bybit.py`), not the 9 cited in the audit.

Second key finding: **`scripts/tape/capture_bybit.py` is the one legitimate exception** to the gate. Its purpose is to capture real Bybit REST responses into JSONL fixtures under `tests/fixtures/tape/`; routing it through bybit-connector would create a circular dependency (tape captures from bybit-connector which serves from tape). The gate must allowlist this file or scope-exempt `scripts/tape/`.

**Suggested default (planner decides):** Build `BybitConnectorClient` as a shared httpx async client utility (single source for the `bybit_connector_retry` + httpx pattern), put it at `shared/bybit_connector_client.py`, and import from every refactored consumer. This reuses the existing `services/market-data-service/app/circuit_breaker.py:18` `bybit_connector_retry` decorator and the `BybitDataFetcher` interface shape. **Alternative:** inline httpx + retry per consumer (less ceremony, more duplication). The shared-client approach was not specified in CONTEXT; planner has discretion. Surfaced again in Open Questions and Assumptions Log (A-Shared).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Bybit REST proxy (kline/ticker/orderbook/recent-trade/funding-rate/instruments) | bybit-connector service | — | Already the gatekeeper; this phase makes it the SOLE gatekeeper |
| Bybit account/auth ping (post-rotation validation) | bybit-connector service | — | `/api/v1/account/balance` endpoint already exists at `services/bybit-connector/app/main.py:532` |
| Tape replay fixtures load | bybit-connector service | — | `TapeReplayClient` already mirrors `BybitRestClient` surface; refactored consumers inherit tape-mode automatically |
| Historical kline batch collection (scripts) | scripts/ (operator-run) | bybit-connector service (data source) | Scripts orchestrate pagination; bybit-connector provides the underlying REST call |
| Backtesting historical data fetch | backtesting/ (Python lib) | bybit-connector service | `backtesting/bybit_data_fetcher.py` becomes a thin wrapper around bybit-connector |
| Tape capture (REAL Bybit → JSONL fixtures) | scripts/tape/ (operator-run, exception) | — | The ONE legitimate direct-Bybit caller; cannot route through connector without circular dep |
| CI grep gate | tests/ci/ (NEW directory) | — | Lives in repo-level tests/ alongside existing security gate; runs in `.github/workflows/` |
| RUNBOOK symptom | RUNBOOK.md (root) | — | Operator-facing failure triage doc; same pattern as existing 6 symptoms |
| Binance/Kraken/Coinbase adapter code | `_archive_exchanges/` (NEW) | — | Cold-storage; matches `_archive_lstm/` precedent |

Note: D-02 archives **only** Binance per operator's exact wording. Kraken and Coinbase adapters live in the same `services/trading-engine/app/exchanges/` directory and would logically follow the same "Bybit-only" policy, but are NOT in CONTEXT scope. Planner should NOT extend BC-04 to Kraken/Coinbase without operator confirmation; flag as carry-in or note for plan-review.

## Standard Stack

### Core (already in-repo — verified by reading requirements.txt files)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `httpx` | 0.27.0 (most services), 0.25.2 (ml-retraining, tournament-harness) | Async HTTP client for bybit-connector REST calls | [VERIFIED: services/*/requirements.txt] Already standard inter-service HTTP client; `BybitDataFetcher` uses it |
| `tenacity` | 8.2.3 | Retry decorator with exponential backoff | [VERIFIED: services/bybit-connector/requirements.txt:18] Already used in `bybit_connector_retry` |
| `respx` | 0.20.2 (most), 0.22.0 (trading-engine) | httpx mock for unit tests — assert called URL/params | [VERIFIED: services/{ml-prediction,sentiment,notification,trading-engine}/requirements.txt] Standard mock for outbound HTTP per `.planning/codebase/TESTING.md:69-80` |
| `pytest-httpx` | 0.30.0 | Alternative httpx mock | [VERIFIED: services/{api-gateway,bybit-connector}/requirements.txt] Used by api-gateway and bybit-connector; refactored consumers should standardize on `respx` for consistency with the existing pattern |
| `pytest` | 7.4.4 | Test runner | [VERIFIED: services/bybit-connector/requirements.txt:35] Standard |
| `pytest-asyncio` | 0.23.3 | Async test support | [VERIFIED: services/bybit-connector/requirements.txt:36] Standard |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `aiohttp` | 3.9.3 | Alternative async HTTP — currently used in `services/ml-prediction-service/download_*.py` and `scripts/collect_6months_historical.py` | **CONVERT to httpx** in refactored scripts for consistency with `BybitDataFetcher` template — see "Library Discrepancy" below |
| `requests` | (vendored) | Sync HTTP — currently used in `scripts/tape/capture_bybit.py:33` | **Leave as-is** — `scripts/tape/capture_bybit.py` is the gate exception |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `httpx` async | Keep `aiohttp` per-script | Inconsistent template; ml-prediction download scripts currently use `aiohttp` (3 files). Conversion to httpx unifies but adds line-touch. Recommendation: convert during refactor (the refactor already touches every line that calls Bybit). |
| Shared `BybitConnectorClient` class in `shared/` | Inline httpx in every consumer | Inline duplication is the path of least resistance per-script, but every script duplicates the fail-fast logic, retry decorator, URL pattern, and error message. Shared class = 1 source of truth, 1 location to add new endpoints. **Recommend shared class.** |
| Relocate `bybit_connector_retry` to `shared/circuit_breaker.py` | Re-import from market-data-service | market-data-service was the first consumer; the decorator lives there for historical reasons. Moving to `shared/` follows the same logic as the shared client. **Recommend relocation as part of the refactor.** |
| `pytest-httpx` for new tests | `respx` | Both are httpx mocks. `respx` is dominant in this repo (4 services) and is the documented standard per `.planning/codebase/TESTING.md:71-80`. **Use respx.** |

**No new package installs required** — every library in the refactor template is already in `requirements.txt`. Planner may need to add `respx` to scripts that don't have it (but scripts are mostly operator-run; their tests live under `services/<svc>/tests/` or `tests/`).

## Architecture Patterns

### System Architecture Diagram

```
                      ┌──────────────────────────────────┐
                      │      Operator / CI / Tests        │
                      └────────────┬─────────────────────┘
                                   │
              ┌────────────────────┼────────────────────────┐
              │                    │                        │
              ▼                    ▼                        ▼
   ┌─────────────────┐  ┌─────────────────────┐  ┌────────────────────┐
   │  scripts/       │  │  backtesting/       │  │ infrastructure/    │
   │  collect_*.py   │  │  bybit_data_       │  │ scripts/           │
   │  fetch_*.py     │  │  fetcher.py        │  │ rotate_secrets.py  │
   │  download_*.py  │  │                    │  │                    │
   └────────┬────────┘  └──────────┬──────────┘  └─────────┬──────────┘
            │                      │                        │
            │ httpx.AsyncClient    │                        │
            │  (REST)              │                        │
            └────────────┬─────────┴───────────┬───────────┘
                         │                     │
                         ▼                     │
          ┌──────────────────────────┐         │
          │ Service-runtime callers  │         │
          │ • ml-prediction-service  │         │
          │   .handlers.orderbook    │         │
          │ • market-data-service    │         │
          │   .fetcher (existing)    │         │
          │ • technical-analysis     │         │
          │   (existing)             │         │
          │ • trading-engine         │         │
          │   .bybit_adapter         │         │
          │   (existing)             │         │
          └──────────────┬───────────┘         │
                         │                     │
                         └──────────┬──────────┘
                                    │
                                    ▼
                ┌────────────────────────────────────────────┐
                │   services/bybit-connector (port 8001)     │
                │   GET /api/v1/market/{ticker, kline,        │
                │       orderbook, recent-trade,              │
                │       funding-rate/history,                 │
                │       instruments-info}                     │
                │   GET /api/v1/account/balance               │
                │   POST /admin/tape/reset                    │
                │                                             │
                │   Internal selector:                        │
                │     MARKET_DATA_SOURCE=live  → BybitRestClient
                │     MARKET_DATA_SOURCE=tape  → TapeReplayClient
                └──────────────────────┬──────────────────────┘
                                       │
                       ┌───────────────┴──────────────────┐
                       │                                  │
                       ▼                                  ▼
              ┌─────────────────────┐         ┌──────────────────────┐
              │ api.bybit.com (V5)  │         │ tests/fixtures/tape/ │
              │ api-testnet.bybit   │         │   klines/*.jsonl     │
              │ wss://stream.bybit  │         │   ticker/*.jsonl     │
              └─────────────────────┘         └──────────────────────┘
              (LIVE mode)                     (TAPE mode)


       ╔═══════ EXCEPTION (allowlist) ════════╗
       ║   scripts/tape/capture_bybit.py      ║
       ║   ├─→ DIRECT api.bybit.com (REST)    ║
       ║   └─→ Writes tests/fixtures/tape/    ║
       ║                                       ║
       ║   Cannot route through connector —    ║
       ║   that's circular (tape would          ║
       ║   capture from tape).                  ║
       ╚═══════════════════════════════════════╝
```

### Recommended Project Structure (post-refactor)

```
crypto-trading-bot/
├── services/
│   ├── bybit-connector/                # SOLE Bybit-facing service
│   │   ├── app/
│   │   │   ├── main.py                 # REST endpoints (unchanged)
│   │   │   ├── bybit_rest_client.py    # Live Bybit calls (unchanged)
│   │   │   └── tape_replay_client.py   # Tape replay (unchanged)
│   │   └── ...
│   └── trading-engine/
│       └── app/exchanges/
│           ├── bybit_adapter.py        # (existing, unchanged)
│           ├── factory.py              # Binance import + registration REMOVED
│           ├── __init__.py             # Binance exports REMOVED
│           ├── kraken.py               # (unchanged, NOT in scope)
│           └── coinbase.py             # (unchanged, NOT in scope)
├── shared/                             # NEW: shared bybit-connector client
│   ├── bybit_connector_client.py       # NEW (recommended): single httpx wrapper
│   └── circuit_breaker.py              # NEW: relocate bybit_connector_retry here
├── scripts/
│   ├── tape/
│   │   └── capture_bybit.py            # Gate EXCEPTION (legit direct-Bybit)
│   ├── collect_*.py                    # REFACTORED to bybit-connector
│   ├── fetch_real_historical_data.py   # REFACTORED
│   └── ...
├── backtesting/
│   └── bybit_data_fetcher.py           # REFACTORED to bybit-connector
├── infrastructure/
│   └── scripts/
│       └── rotate_secrets.py           # REFACTORED auth-ping to bybit-connector
├── tests/
│   ├── ci/                             # NEW directory
│   │   └── test_no_bybit_bypass.py     # NEW: grep gate
│   ├── integration/
│   │   └── test_bybit_connector_tape_preserved.py  # NEW: tape preservation test
│   └── fixtures/
│       └── tape/
│           ├── klines/                 # (unchanged)
│           ├── ticker/                 # (unchanged)
│           └── orderbook/              # OPTIONAL: see Tape-Mode Coverage Gap
├── _archive_exchanges/                 # NEW: archive dir
│   └── binance.py                      # MOVED from services/trading-engine/app/exchanges/
└── RUNBOOK.md                          # NEW symptom #7 appended
```

### Pattern 1: Refactored Service-Runtime Caller (ml-prediction-service orderbook)

**What:** Service runtime needs orderbook data; replaces direct `httpx.get("https://api.bybit.com/v5/market/orderbook", ...)` with bybit-connector REST.
**When to use:** Any in-container service consumer (ml-prediction, market-data, technical-analysis, trading-engine adapters).
**Reference template:** `services/market-data-service/app/fetcher.py:204-246` (`BybitDataFetcher.get_ticker`).

**Example (orderbook handler refactor):**
```python
# Source: pattern adapted from services/market-data-service/app/fetcher.py:204-246
# REQUIRES env var BYBIT_CONNECTOR_URL (compose default: http://bybit-connector:8001)
import httpx
import os
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

_BYBIT_CONNECTOR_URL = os.getenv("BYBIT_CONNECTOR_URL", "http://bybit-connector:8001")

bybit_connector_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
)

@bybit_connector_retry
async def fetch_orderbook_from_connector(symbol: str, limit: int = 25) -> dict:
    async with httpx.AsyncClient(timeout=10.0, base_url=_BYBIT_CONNECTOR_URL) as client:
        response = await client.get(
            "/api/v1/market/orderbook",
            params={"category": "linear", "symbol": symbol.upper(), "limit": min(limit, 500)}
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise HTTPException(status_code=502, detail=f"bybit-connector error: {payload}")
        result = payload["data"]
        return {
            "bids": [[float(b[0]), float(b[1])] for b in result.get("b", [])],
            "asks": [[float(a[0]), float(a[1])] for a in result.get("a", [])],
            "timestamp": result.get("ts", 0),
        }
```

### Pattern 2: Refactored Standalone Script (operator-run, host environment)

**What:** Script runs on host (operator's machine, not inside compose); needs Bybit data; must fail-fast if bybit-connector unreachable.
**When to use:** `scripts/collect_*.py`, `scripts/fetch_*.py`, `services/ml-prediction-service/download_*.py`, `backtesting/bybit_data_fetcher.py`.
**Reference template:** `services/market-data-service/app/fetcher.py:91-103` (health_check) + D-04 fail-fast rule.

**Critical host-vs-container hostname concern:**
- Inside compose, services resolve `bybit-connector:8001` via Docker DNS.
- On host (operator's machine), `bybit-connector` does NOT resolve; must use `localhost:8001` (port 8001 is published in `docker-compose.unified.yml`).
- Scripts MUST default `BYBIT_CONNECTOR_URL=http://localhost:8001` when not overridden (operator-run case). Setting the env var in compose to `http://bybit-connector:8001` covers the in-container case.

**Example (collection script refactor):**
```python
# Source: pattern derived from D-04 + services/market-data-service/app/fetcher.py
# Default URL is localhost (host case); compose env override is bybit-connector:8001
import os
import sys
import httpx
import asyncio

BYBIT_CONNECTOR_URL = os.getenv("BYBIT_CONNECTOR_URL", "http://localhost:8001")

async def assert_connector_reachable() -> None:
    """D-04: fail-fast with operator-readable error if bybit-connector down."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{BYBIT_CONNECTOR_URL}/health")
            response.raise_for_status()
    except Exception as e:
        print(
            f"\nERROR: bybit-connector is not reachable at {BYBIT_CONNECTOR_URL}.\n"
            f"  Cause: {e!r}\n"
            f"  Fix:   Run `docker compose -f docker-compose.unified.yml up -d bybit-connector`\n"
            f"  (or set BYBIT_CONNECTOR_URL if running against a non-default host).\n",
            file=sys.stderr,
        )
        sys.exit(2)

async def fetch_klines_via_connector(symbol: str, interval: str, start_ms: int, end_ms: int, limit: int = 1000) -> list:
    async with httpx.AsyncClient(timeout=30.0, base_url=BYBIT_CONNECTOR_URL) as client:
        response = await client.get(
            "/api/v1/market/kline",
            params={"category": "linear", "symbol": symbol, "interval": interval,
                    "start": start_ms, "end": end_ms, "limit": min(limit, 1000)},
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise RuntimeError(f"bybit-connector returned non-success: {payload}")
        # Bybit V5 shape preserved by bybit-connector
        data = payload["data"]
        return data["list"] if isinstance(data, dict) else data
```

### Pattern 3: Auth-Ping Refactor (rotate_secrets.py)

**What:** Post-rotation validation; previously `pybit.unified_trading.HTTP(...).get_wallet_balance(accountType="UNIFIED")`. Replace with bybit-connector `/api/v1/account/balance`.
**When to use:** `infrastructure/scripts/rotate_secrets.py:230-254`.
**Reference target:** `services/bybit-connector/app/main.py:532-557` (existing `/api/v1/account/balance` endpoint).

**Important nuance — credential propagation:**
- The original code instantiates `pybit.HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret)` directly with the NEW credentials being validated. The `/api/v1/account/balance` endpoint on bybit-connector reads from **bybit-connector's** env (`BYBIT_API_KEY`/`BYBIT_API_SECRET`), not from the request. So the refactor must EITHER:
  - **Option A:** Restart bybit-connector with the new credentials, then call balance. Requires container restart inside rotate_secrets workflow — invasive but mirrors production.
  - **Option B:** Add a new bybit-connector endpoint `POST /api/v1/account/validate` that accepts credentials in the request body and tests them in isolation. Adds API surface area (CONTEXT says "likely not — existing surface covers all known bypass-site patterns").
  - **Option C:** Keep `pybit` in `rotate_secrets.py` and put it on the allowlist. Violates D-07 ("no escape hatches").

**Suggested default (planner decides — surfaced in Open Questions #2):** Option A — bybit-connector restart with new creds, then balance ping. Pros: mirrors how production reads creds (env-injected at boot); validates the propagation path that production will use. Cons: adds a `docker compose restart bybit-connector` call inside the rotation workflow, which is invasive and pauses Bybit market-data reads for the duration of the restart (~5-10s). Option B (new `POST /api/v1/account/validate` endpoint that accepts credentials in the request body) is also defensible and avoids the restart but expands the connector's API surface — CONTEXT D-10 says "likely no new endpoints" but does not explicitly forbid one for the rotation flow. **Planner should confirm with operator before locking in Option A.**

### Pattern 4: Test Bypass Refactor (test_pagination_fix.py)

**What:** A diagnostic/test script that hit `api.bybit.com` directly to validate pagination logic; refactor to hit bybit-connector and assert the connector's pagination handling.
**When to use:** `services/market-data-service/tests/test_pagination_fix.py:36`.
**Reference template:** Use `respx.mock` to assert outbound URL — but for an integration-style test, point at the actual bybit-connector under MARKET_DATA_SOURCE=tape.

The test as it stands is more of a manual diagnostic than a unit test (it makes real HTTP calls). The refactor can either:
- **Delete it** — already covered by `services/market-data-service/tests/test_fetcher.py` (assumed; planner verifies)
- **Convert it** to call bybit-connector under tape mode + assert tape-replayed data matches expected pagination shape

Recommendation: **delete-and-replace** with the BC-07 tape-preservation test that subsumes the original intent. Planner should verify `test_fetcher.py` covers the pagination path before deletion.

### Pattern 5: CI Grep Gate (BC-03)

**What:** Pytest file that scans `**/*.py` outside `services/bybit-connector/` for banned patterns; pluggable into `.github/workflows/`.
**Reference template:** `tests/integration/test_preflight_grep_gates.py` (Phase 8, fully implemented Oct 2025) + `services/tournament-harness/tests/integration/test_tourn07_grep_gate.py` (Phase 3).

**Note on CONTEXT-cited precedent:** CONTEXT.md (specifics section) references `tests/ci/test_no_new_setinterval_polling.py` as the idiom to reuse. **This file does not exist in the repo** (verified by `ls /tests/ci/` returning the directory does not exist; full grep of `test_no_*` patterns returns only `tests/security/test_no_unattended_claude_p_in_ci.py`). The CONTEXT entry was a deferred-WS-scope artifact that never landed. Researcher recommends using the Phase 8 (`test_preflight_grep_gates.py`) or Phase 3 (`test_tourn07_grep_gate.py`) idiom instead — both are landed, green, and actively wired into CI.

**Example (BC-03 grep gate):**
```python
# Source: pattern from tests/integration/test_preflight_grep_gates.py:50-95
# (Phase 8 PREFLIGHT-02 idiom: dual-form scan with pathlib rglob + subprocess grep)
from __future__ import annotations
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXEMPT_PATHS = {
    REPO_ROOT / "services" / "bybit-connector",     # D-05: connector itself
    REPO_ROOT / "scripts" / "tape",                  # Exception: tape capture script
    REPO_ROOT / "_archive_exchanges",                # Archived code
    REPO_ROOT / "_archive_lstm",                     # Pre-existing archive
}

BANNED_PATTERNS = {
    "pybit_import":      re.compile(r"^\s*(from\s+pybit\b|import\s+pybit\b)", re.MULTILINE),
    "mainnet_rest_url":  re.compile(r"https?://api\.bybit\.com"),
    "testnet_rest_url":  re.compile(r"https?://api-testnet\.bybit\.com"),
    "wss_stream_url":    re.compile(r"wss?://stream(?:-testnet)?\.bybit"),
}


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _scan_py_files() -> list[tuple[str, int, str, str]]:
    """Return list of (relative_path, line_no, kind, snippet) violations."""
    violations: list[tuple[str, int, str, str]] = []
    for py in REPO_ROOT.rglob("*.py"):
        if any(_is_under(py, exempt) for exempt in EXEMPT_PATHS):
            continue
        if "__pycache__" in py.parts:
            continue
        try:
            text = py.read_text(errors="ignore")
        except OSError:
            continue
        for kind, pattern in BANNED_PATTERNS.items():
            for m in pattern.finditer(text):
                line_no = text[: m.start()].count("\n") + 1
                snippet = text.splitlines()[line_no - 1].strip()
                violations.append(
                    (str(py.relative_to(REPO_ROOT)), line_no, kind, snippet)
                )
    return violations


def test_no_bybit_bypass_in_python_code():
    """BC-03: no direct-Bybit references in **/*.py outside the connector."""
    violations = _scan_py_files()
    assert violations == [], (
        "BC-03 violation — direct-Bybit references found outside services/bybit-connector/:\n  "
        + "\n  ".join(f"{p}:{ln}: [{k}] {snippet}" for p, ln, k, snippet in violations)
    )


def test_grep_command_matches_pytest_scan():
    """Defence-in-depth — the literal grep command CI runs must agree with pytest scan."""
    cmd = [
        "grep", "-rE", "--include=*.py",
        "--exclude-dir=services/bybit-connector",
        "--exclude-dir=scripts/tape",
        "--exclude-dir=_archive_exchanges",
        "--exclude-dir=_archive_lstm",
        "--exclude-dir=__pycache__",
        r"(from pybit|import pybit|https?://api(-testnet)?\.bybit\.com|wss?://stream(-testnet)?\.bybit)",
        str(REPO_ROOT),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # Note: --exclude-dir matching is RELATIVE to entries; resolve to anchors
    # in the test if needed. The pytest scan is the source of truth; this
    # subprocess check is fidelity to the literal CI command operators will
    # paste into a shell. Empty output is the success condition.
    assert result.stdout.strip() == "", "BC-03 grep gate failed:\n" + result.stdout
```

### Anti-Patterns to Avoid

- **Inline `httpx.AsyncClient` with hard-coded URL in every script.** Every script duplicates fail-fast logic, retry decorator, URL pattern, error message. Use a shared client class.
- **Silent fallback to direct Bybit when bybit-connector is down.** D-04 forbids it. Explicit exit code 2 with operator-readable error.
- **Wrapping bybit-connector failures with the original Bybit error shape.** Some consumers parse the Bybit `retCode`/`retMsg` shape directly (see `services/ml-prediction-service/app/handlers/orderbook.py:274`). bybit-connector wraps these as `{success: True/False, data: ...}`. Refactored consumers should parse the wrapper, not the inner Bybit shape.
- **`pytest-httpx` for new tests in services that already use `respx`.** Picking the wrong mock library splits the mental model. Match the service's existing standard (see CORE table above).
- **Removing `ExchangeName.BINANCE` from `app/exchanges/base.py` enum.** D-02 says archive the adapter, not delete the enum value. `manager.py:256` references it in a docstring example; `router.py:400` uses it in a default-fees dict. Leaving the enum value keeps those references compilable; removing it requires touching unrelated files outside D-02 scope.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP retry on transient bybit-connector failures | Custom retry loops | `tenacity` `@retry(stop_after_attempt, wait_exponential, retry_if_exception_type)` already wrapped as `bybit_connector_retry` | Already in `services/market-data-service/app/circuit_breaker.py:18`; relocate to `shared/` |
| Async HTTP client lifecycle | New httpx.AsyncClient() per call | `httpx.AsyncClient` with connection pooling per `BybitDataFetcher.__init__` | `services/market-data-service/app/fetcher.py:72-83` already shows the limits config |
| URL host selection by environment | If/else on `BYBIT_TESTNET` in caller code | bybit-connector handles testnet/mainnet internally via its own `BYBIT_TESTNET` env | Centralizes the testnet selector; D-08 tape mode is a third mode invisible to callers |
| Tape vs live data selection | Conditional branching in caller | `MARKET_DATA_SOURCE=tape|live` on bybit-connector; callers see one URL | `services/bybit-connector/app/main.py:385-393` DI seam routes to either `BybitRestClient` or `TapeReplayClient` |
| Pagination of historical klines (1000-candle limit) | Per-script loop logic | `BybitDataFetcher.get_historical_klines` at `services/market-data-service/app/fetcher.py:248-391` | Already handles batch-by-batch backwards-from-end logic, deduplication, sorting |
| HTTP mock for unit tests | `unittest.mock.patch` on `httpx.get` | `respx.mock` per `.planning/codebase/TESTING.md:69-80` | Decorator-style URL+param assertion |
| CI grep gate scaffolding | bash one-liner in workflow | Python pytest test invoked from workflow | Phase 3 (TOURN-07) + Phase 8 (PREFLIGHT-02) precedent; pytest gives structured failure output |

**Key insight:** Every refactor is a **library substitution**, not new logic. The bybit-connector REST endpoints already exist (verified at `services/bybit-connector/app/main.py:739-944`); the retry decorator exists; the httpx pattern exists; the tape-replay mode exists. Phase 13 is moving callers from one library to another, not building anything.

## Runtime State Inventory

This is a rename/refactor phase. Explicit per-category answers:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **None** — no databases, datastores, vector stores, or external state systems store the old import names or `api.bybit.com` URLs as keys, IDs, or content. TimescaleDB klines store **OHLCV values**, not URLs; PostgreSQL stores app state, not endpoints. | No data migration |
| Live service config | **None** — only the in-repo `docker-compose.unified.yml` configures bybit-connector; no n8n / Datadog / Tailscale / Cloudflare equivalents in this stack. | No service-config patch |
| OS-registered state | **None** — no Windows Task Scheduler entries, no systemd units, no pm2 saved process state references Bybit URLs by literal. The `BYBIT_PRICE_SOURCE` markers in CI logs and the `LIVECLOSE-01` harness scan for the literal string `mode=tape` (not the URLs being refactored). Verified by `grep -rn "api.bybit\|pybit" .github/workflows/` returning no hits. | No OS-level changes |
| Secrets/env vars | `BYBIT_API_KEY`, `BYBIT_API_SECRET`, `BYBIT_TESTNET` — **unchanged**. `BYBIT_CONNECTOR_URL` already in use; new callers consume the existing env var. `MARKET_DATA_SOURCE` already in use for tape switch. | None — existing env var names are reused; only `infrastructure/scripts/rotate_secrets.py`'s INTERNAL handling of credentials changes (see Pattern 3 above) |
| Build artifacts | `__pycache__/` dirs may cache the old `app.exchanges.binance` import — will be regenerated by next build. No `*.egg-info`, no compiled binaries that bind to the moved file path. Docker images include the source; rebuild via `docker compose build trading-engine` after the archival commit. | `docker compose build trading-engine` after BC-04 lands; CI clean-rebuilds anyway |

**Special note on `_archive_exchanges/binance.py`:** Python import discovery does NOT walk into `_archive_*` directories by default — they are not on `sys.path` and have no `__init__.py`. After `git mv services/trading-engine/app/exchanges/binance.py _archive_exchanges/binance.py` and removing the import from `factory.py:62` / `__init__.py:329`, the file is unreachable at runtime. No risk of accidental re-import.

## Environment Availability

This phase has no NEW external dependencies. All required tools (Docker, Python, pytest, httpx, respx, tenacity) are already in-repo and verified by `services/*/requirements.txt`. Skipped per Step 2.6 condition: phase is code/config changes against existing infrastructure.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker compose stack with bybit-connector | All refactored consumers at runtime | ✓ (per `docker-compose.unified.yml`) | — | None: D-04 forbids escape hatches |
| Python 3.12 | All Python code | ✓ (project-locked) | 3.12 | None |
| `httpx`, `tenacity`, `respx`, `pytest`, `pytest-asyncio` | All refactored code + tests | ✓ (in `services/*/requirements.txt`) | as pinned | None — pre-installed in containers |
| `pybit==5.6.2` | Only `services/bybit-connector/` post-refactor | ✓ | 5.6.2 | N/A — DROPPED from non-connector services |

**Cleanup item for planner:** No service outside bybit-connector currently declares `pybit` as a dependency in `requirements.txt` (verified — only `services/bybit-connector/requirements.txt:11` has `pybit==5.6.2`). The `pybit` imports in `scripts/collect_ml_training_data_simple.py:18` and `infrastructure/scripts/rotate_secrets.py:232` import from the host Python or the wrong-service venv currently. After refactor, no non-connector consumer needs pybit; no requirements.txt cleanup is required.

## Endpoint Mapping (BC-02)

Per-bypass-site mapping. Every site below is fully covered by existing bybit-connector REST endpoints — **no new endpoints needed** (resolves the open question in CONTEXT D-10 "discretion" block).

| Bypass Site | Current Call | bybit-connector Replacement |
|-------------|--------------|------------------------------|
| `services/ml-prediction-service/app/handlers/orderbook.py:262` | `GET https://api.bybit.com/v5/market/orderbook` | `GET ${BYBIT_CONNECTOR_URL}/api/v1/market/orderbook` |
| `services/ml-prediction-service/download_missing_symbols_data.py:43` | `GET ${BYBIT_API_URL}/v5/market/kline` (aiohttp) | `GET ${BYBIT_CONNECTOR_URL}/api/v1/market/kline` (httpx) |
| `services/ml-prediction-service/download_final_4.py:18` | `GET ${BYBIT_API}/v5/market/kline` (aiohttp) | `GET ${BYBIT_CONNECTOR_URL}/api/v1/market/kline` (httpx) |
| `services/ml-prediction-service/download_op_sui_6months.py:30` | `GET https://api.bybit.com/v5/market/kline` | `GET ${BYBIT_CONNECTOR_URL}/api/v1/market/kline` |
| `services/ml-prediction-service/download_suiusdt_12months.py:39` | `GET https://api.bybit.com/v5/market/kline` | `GET ${BYBIT_CONNECTOR_URL}/api/v1/market/kline` |
| `scripts/collect_180_days_data.py:56` | `GET https://api.bybit.com/v5/market/kline` | `GET ${BYBIT_CONNECTOR_URL}/api/v1/market/kline` |
| `scripts/collect_6months_for_ml.py:28` (per CONTEXT) | `GET https://api.bybit.com/v5/market/kline` | `GET ${BYBIT_CONNECTOR_URL}/api/v1/market/kline` |
| `scripts/collect_6months_historical.py` | (uses aiohttp; verify exact line) | `GET ${BYBIT_CONNECTOR_URL}/api/v1/market/kline` |
| `scripts/collect_bybit_direct_180days.py` | (filename hints at direct; verify) | `GET ${BYBIT_CONNECTOR_URL}/api/v1/market/kline` |
| `scripts/collect_ml_training_data_simple.py:18` | `from pybit.unified_trading import HTTP` | `GET ${BYBIT_CONNECTOR_URL}/api/v1/market/kline` (drop pybit dep) |
| `scripts/data_quality_enhancement.py` | (verify; likely kline) | `GET ${BYBIT_CONNECTOR_URL}/api/v1/market/kline` |
| `scripts/fetch_real_historical_data.py:31` | `GET https://api.bybit.com/v5/market/kline` | `GET ${BYBIT_CONNECTOR_URL}/api/v1/market/kline` |
| `scripts/test_public_bybit_api.py:21` | `GET https://api.bybit.com/v5/market/klines` | Likely **delete** — diagnostic probe; if kept, route through `/api/v1/market/kline` |
| `backtesting/bybit_data_fetcher.py:36-38` | `${base_url}/v5/market/kline` (testnet/mainnet switch) | `GET ${BYBIT_CONNECTOR_URL}/api/v1/market/kline` (bybit-connector handles testnet/mainnet) |
| `services/market-data-service/tests/test_pagination_fix.py:36` | `GET https://api.bybit.com/v5/market/kline` | Delete (see Pattern 4) or refactor to assert against tape-replayed connector response |
| `infrastructure/scripts/rotate_secrets.py:232-234` | `pybit.HTTP(...).get_wallet_balance(accountType="UNIFIED")` | `GET ${BYBIT_CONNECTOR_URL}/api/v1/account/balance` after restarting connector with new creds (see Pattern 3 Option A) |
| `shared/health_check.py:771` | `GET ${base_url}/v5/market/time` | `GET ${BYBIT_CONNECTOR_URL}/health` (bybit-connector's `/ready` already does a Bybit ping; redundant probe) |
| `tests/smoke/test_smoke.py` | (verify exact pattern) | `GET ${BYBIT_CONNECTOR_URL}/health` or appropriate `/api/v1/market/...` |

| Exception | Reason | Action |
|-----------|--------|--------|
| `scripts/tape/capture_bybit.py:41` | Captures REAL Bybit responses to create tape fixtures; routing through bybit-connector is circular | Allowlist in CI grep gate (`EXEMPT_PATHS` set above) |

**Note on "verify" entries:** The initial ROADMAP audit listed 9 sites; researcher grep found 18 + 1 exception. The planner's BC-01 audit task MUST re-grep and produce `bybit-bypass-audit.json` with the full list — initial audit was undercount.

## Phase-Close Cleanup (CONTEXT D-10)

Per CONTEXT D-10, the planner adds a note to update `.planning/codebase/INTEGRATIONS.md` line 231 — the stale claim that `wss://stream.bybit.com/*` is consumed by `market-data` (audit confirmed: only bybit-connector consumes it). **This is in-scope for phase 13 close**, not deferred, despite appearing in CONTEXT's Deferred Ideas section verbatim.

**Action:** Single-line edit at `.planning/codebase/INTEGRATIONS.md:231`:
- Old: `| Out | wss://stream.bybit.com/* | bybit-connector, market-data |`
- New: `| Out | wss://stream.bybit.com/* | bybit-connector |`

**When:** Last commit of the phase, alongside or just before the BC-03 grep-gate landing commit so the codebase-map reflects post-refactor reality.

**Test impact:** None — INTEGRATIONS.md is documentation; no test asserts its contents. Verification is a manual grep diff.

## Tape-Mode Coverage Gap (BC-07)

**Finding:** `services/bybit-connector/app/tape_replay_client.py:206-218` stubs four endpoints to return empty payloads:

```python
async def get_orderbook(self, *args, **kwargs):           # line 206
    return {"a": [], "b": [], "ts": 0, "u": 0}
async def get_recent_trades(self, *args, **kwargs):       # line 209
    return {"list": []}
async def get_funding_rate_history(self, *args, **kwargs): # line 212
    return {"list": []}
async def get_instruments_info(self, *args, **kwargs):    # line 217
    return {"list": []}
```

**Implication for BC-07:**
- `ml-prediction-service/app/handlers/orderbook.py` is the only orderbook consumer in this phase. After refactor, in tape mode it will receive `{"a": [], "b": [], "ts": 0, "u": 0}` wrapped in `{"success": True, "data": ...}`.
- The handler converts `result.get("b", [])` and `result.get("a", [])` into lists of `[price, size]` (lines 283-290). Empty input → empty bids/asks lists → no crash, but downstream `interpret_imbalance(0.0)` returns "Neutral" and `determine_liquidity_level(spread_pct=∞, liquidity_score=0)` returns "LOW".
- **This is technically tape-preservation** (no live Bybit calls leak) but means the orderbook endpoint is effectively unusable under tape unless fixtures are added.

**Two options for BC-07 fixture strategy:**

| Option | Description | Effort | Test Strength |
|--------|-------------|--------|---------------|
| **A: Assert shape, accept empty** | BC-07 test asserts orderbook handler does not crash with empty payload + returns standardized "neutral/low" response | Low (~30 LOC test) | Weak — doesn't verify orderbook data is actually replayed |
| **B: Capture orderbook fixtures** | Extend `scripts/tape/capture_bybit.py` to capture orderbook snapshots (e.g., 1 per symbol); extend `TapeReplayClient.get_orderbook` to load and replay them | Medium (~50 LOC connector + ~80 LOC capture + fixture data) | Strong — full end-to-end tape parity |

**Recommendation:** **Option A for phase 13**, with a follow-up ROADMAP entry for Option B. Rationale: orderbook is only consumed by ml-prediction-service which is gated `ENABLE_ML_PREDICTIONS=false`. The refactor's load-bearing requirement is "no live calls leak under tape" — empty-but-shape-correct satisfies that. Richer fixtures are valuable but not load-bearing for v1.2.

Surface for planner: this is a Claude's-discretion decision (CONTEXT explicitly delegated this). Recommend Option A but plan a `BC-FOLLOWUP-01` carry-in.

## Library Discrepancy: aiohttp → httpx

**Sites currently using `aiohttp`:**
- `services/ml-prediction-service/download_missing_symbols_data.py:23`
- `services/ml-prediction-service/download_final_4.py:7`
- `services/ml-prediction-service/download_op_sui_6months.py` (probable; verify)
- `scripts/collect_6months_historical.py` (probable)

**Template uses `httpx`** (`services/market-data-service/app/fetcher.py`).

**Why convert during refactor:**
- Every line that calls Bybit is already being touched.
- Two HTTP clients in the same script class = inconsistent error handling, session management, mock library (aiohttp uses `aioresponses`, httpx uses `respx`).
- `httpx` is the repo standard per `.planning/codebase/TESTING.md:69-80`.

**Conversion cost:** ~10 LOC per script (`aiohttp.ClientSession()` → `httpx.AsyncClient()`; `session.get(url) as response` → `response = await client.get(url)`; `await response.json()` → `response.json()` (sync method on httpx)).

**Suggested default (planner decides — surfaced in Open Questions #6 below):** convert to httpx as part of BC-02 for repo-standard consistency (~10 LOC per script). **Alternative:** leave aiohttp in place, replace only the URL/params with bybit-connector. The bypass-elimination requirement (BC-02) is satisfied either way; conversion is a consistency win, not a correctness requirement. Planner should weigh the per-script line-touch budget.

## Binance Archival Call-Graph Verification (BC-04)

**Verified findings:**

1. **`services/trading-engine/app/main.py` imports nothing from `app.exchanges.*`** (verified `grep -rn "from app.exchanges\|import app.exchanges" services/trading-engine/app/*.py` returns 0 hits at the `main.py` level). The exchanges package is internal API; main.py boots without it.

2. **Binance production references** (live imports/instantiations):
   - `services/trading-engine/app/exchanges/factory.py:62` — `from app.exchanges.binance import BinanceExchangeAdapter`
   - `services/trading-engine/app/exchanges/factory.py:186-210` — Binance adapter registration
   - `services/trading-engine/app/exchanges/__init__.py:329-336` — re-exports `BinanceExchangeAdapter`, `BinanceAdapterConfig`, `BinanceRateLimiter`, `create_binance_adapter`, `map_binance_error`, `BINANCE_ERROR_MAP`
   - `services/trading-engine/app/exchanges/__init__.py:513-516` — `__all__` listing

3. **Binance enum references that DON'T need touching:**
   - `services/trading-engine/app/exchanges/base.py:62` — `ExchangeName.BINANCE = "binance"` (enum value; kept)
   - `services/trading-engine/app/exchanges/manager.py:256` — docstring example only
   - `services/trading-engine/app/exchanges/router.py:400` — `default_fees` dict has `ExchangeName.BINANCE: (...)` (cosmetic; kept)

4. **Binance test references** (`services/trading-engine/tests/test_multi_exchange.py`):
   - File is wholesale `pytest.mark.skip(reason="stale tests after PR #86 refactor; needs rewrite")` at line 24
   - Imports `BinanceExchangeAdapter`, `KrakenExchangeAdapter`, `CoinbaseExchangeAdapter` at lines 54-56
   - After archival, imports will fail → test collection error → CI broken even though tests are skipped
   - **Fix:** Either delete the test file entirely (preferred — already skipped, signals dead code clearly), or guard the imports inside the skip with `try/except ImportError: pass`

**Production import chain proof:** After moving `services/trading-engine/app/exchanges/binance.py` to `_archive_exchanges/binance.py` and removing the `from app.exchanges.binance import` lines from `factory.py:62` and `__init__.py:329`, the trading-engine boot path is unaffected. The only remaining `from app.exchanges.binance` import is the `__init__.py` re-export, which is the line being removed. No other module imports the Binance adapter directly. **Zero ImportError risk.**

**Planner action items for BC-04:**
- `git mv services/trading-engine/app/exchanges/binance.py _archive_exchanges/binance.py`
- Edit `factory.py`: delete line 62 `from app.exchanges.binance import BinanceExchangeAdapter`; delete lines 186-210 (Binance adapter registration block)
- Edit `__init__.py`: delete lines 329-336 (`from app.exchanges.binance import ...`); delete lines 513-516 (`__all__` entries)
- Delete `services/trading-engine/tests/test_multi_exchange.py` (already skipped, removes dead test file)
- Optional: drop `BINANCE_ERROR_MAP`, `map_binance_error` from `__init__.py:312-313` (they live in `errors.py`; if not consumed elsewhere, archive references in `errors.py` too — out of CONTEXT scope, surface as carry-in)

## Common Pitfalls

### Pitfall 1: bybit-connector hostname doesn't resolve on host

**What goes wrong:** Scripts default `BYBIT_CONNECTOR_URL=http://bybit-connector:8001` (compose-style). Operator runs `python scripts/collect_180_days_data.py` on host without env override; DNS lookup of `bybit-connector` fails; script fails with cryptic `httpx.ConnectError`.
**Why it happens:** Docker DNS only resolves inside the compose network. Port 8001 is host-published, so `http://localhost:8001` works from host.
**How to avoid:**
- Default URL is `http://localhost:8001` (host-friendly).
- Compose env override sets `BYBIT_CONNECTOR_URL=http://bybit-connector:8001` for in-container services.
- Fail-fast error explicitly says `BYBIT_CONNECTOR_URL is {value} — check it matches your environment (host: localhost:8001; compose: bybit-connector:8001)`.
**Warning signs:** `httpx.ConnectError: All connection attempts failed` on host runs; works inside `docker exec`.

### Pitfall 2: Refactored consumer parses Bybit shape instead of connector wrapper

**What goes wrong:** bybit-connector wraps Bybit's `{retCode, retMsg, result}` response as `{success: bool, data: {...}}`. A refactored consumer that copy-pastes from the old code keeps `if data.get("retCode") != 0:` which is always falsy on the wrapper.
**Why it happens:** Mechanical refactor — change URL but forget to change response parsing.
**How to avoid:** Every refactored consumer's response parser is `if not payload.get("success"): raise ...` then `result = payload["data"]`. Add a unit test asserting the wrapper shape.
**Warning signs:** Refactor "works" against mocked bybit-connector but breaks against real connector.

### Pitfall 3: rotate_secrets credentials don't propagate

**What goes wrong:** Operator runs rotate_secrets; new Bybit credentials are written to Vault but bybit-connector still has the OLD creds in its env. Auth-ping against bybit-connector succeeds (it's pinging with old creds), confirming nothing about the rotation.
**Why it happens:** bybit-connector reads creds at boot; rotation doesn't restart the container.
**How to avoid:** rotate_secrets must `docker compose restart bybit-connector` BEFORE the auth-ping. The ping then validates the new creds the way production does.
**Warning signs:** Rotation reports success but trading fails with "invalid API key" on next order.

### Pitfall 4: CI grep gate has false positives on documentation strings

**What goes wrong:** Some `.py` file has a docstring like `"""Replaces direct api.bybit.com calls"""`. Grep matches; gate fails.
**Why it happens:** Pure-text grep doesn't distinguish code from docstrings/comments.
**How to avoid:** EITHER
- Use AST to inspect import statements (catches `from pybit`/`import pybit`) AND grep for URL literals only in code (excluding docstring positions). This is heavier and brittle.
- OR accept that docstrings should not mention `api.bybit.com` literally (use `the Bybit REST API` etc.) — simpler, and matches the spirit of "no direct refs".
**Recommendation:** simpler approach; if any in-repo docstrings currently use the literal URLs, fix them in the same refactor pass.

### Pitfall 5: Tape-mode tests pass but live-mode integration broken

**What goes wrong:** Refactor lands; tape-mode integration test (BC-07) is green. Operator flips to `MARKET_DATA_SOURCE=live` for a manual smoke; ml-prediction orderbook handler returns "Neutral" because some refactor detail changed the bid/ask parsing.
**Why it happens:** Tape-mode test only exercises the success path against empty/canned data; live-mode would exercise the real Bybit response shape via bybit-connector's `BybitRestClient`.
**How to avoid:** A nightly live-smoke test (`.github/workflows/live-smoke.yml` already exists) should hit the refactored endpoints with live data. BC-07 alone is necessary but not sufficient. Note for planner: ensure live-smoke covers the refactored consumer paths post-refactor.
**Warning signs:** Tape tests green, paper-trading smoke fails with empty data.

### Pitfall 6: aiohttp → httpx response.json() is sync, not async

**What goes wrong:** Mechanical aiohttp → httpx conversion leaves `data = await response.json()`. httpx's `Response.json()` is synchronous (no `await`). Refactored script crashes with `TypeError: object dict can't be used in 'await' expression`.
**Why it happens:** aiohttp uses `await response.json()` (async); httpx uses `response.json()` (sync) because the response body is already loaded.
**How to avoid:** Drop the `await` on `.json()` calls. Test by running the script under tape mode.
**Warning signs:** First execution of a refactored aiohttp-origin script raises TypeError on the response parse line.

### Pitfall 7: api-gateway tests pass on host but fail in container (and vice versa)

**What goes wrong:** Phase 13 refactor adds tests to api-gateway service. Developer runs `pytest services/api-gateway/tests/` on host. Tests with auth assertions return 401 instead of expected 403, fail. Or developer runs in container, tests work; CI later runs on host and fails.
**Why it happens:** Host pip has fastapi 0.136 (HTTPBearer returns 401 per RFC 6750); container pins fastapi 0.109 (returns 403). Tests assert 403.
**How to avoid:** api-gateway tests **must** run inside the container per `.planning/codebase/TESTING.md:110-118`. Phase 13 doesn't add api-gateway tests (the bypass sites aren't in api-gateway) but if any new tests touch api-gateway's `HTTPBearer`-protected routes, run them via `docker exec crypto-bot-api-gateway pytest`.
**Warning signs:** 403 vs 401 assertion failures on auth tests.

## Code Examples

Verified patterns from in-repo sources:

### Refactored httpx async caller with retry decorator

```python
# Source: services/market-data-service/app/fetcher.py:50-246 (verbatim pattern)
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

bybit_connector_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
)

class BybitConnectorClient:
    def __init__(self, base_url: str):
        limits = httpx.Limits(max_connections=100, max_keepalive_connections=20, keepalive_expiry=30.0)
        self.client = httpx.AsyncClient(base_url=base_url, timeout=30.0, limits=limits)

    async def close(self):
        await self.client.aclose()

    @bybit_connector_retry
    async def get_kline(self, symbol: str, interval: str, limit: int = 200,
                        start_time: int = None, end_time: int = None) -> list:
        params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": min(limit, 1000)}
        if start_time is not None:
            params["start"] = start_time
        if end_time is not None:
            params["end"] = end_time
        response = await self.client.get("/api/v1/market/kline", params=params)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise RuntimeError(f"bybit-connector returned non-success: {payload}")
        data = payload["data"]
        return data["list"] if isinstance(data, dict) else data
```

### respx mock for unit test

```python
# Source: .planning/codebase/TESTING.md:69-80 + pattern from services/market-data-service/tests/
import pytest
import respx
import httpx

@pytest.mark.asyncio
@respx.mock
async def test_get_kline_calls_bybit_connector():
    route = respx.get("http://bybit-connector:8001/api/v1/market/kline").mock(
        return_value=httpx.Response(200, json={
            "success": True,
            "data": {"list": [["1700000000000", "50000", "51000", "49000", "50500", "100", "5000000"]]}
        })
    )
    client = BybitConnectorClient(base_url="http://bybit-connector:8001")
    klines = await client.get_kline(symbol="BTCUSDT", interval="60", limit=100)
    assert route.called
    assert route.calls.last.request.url.params["symbol"] == "BTCUSDT"
    assert len(klines) == 1
    await client.close()
```

### Existing grep-gate test idiom (precedent for BC-03)

```python
# Source: services/tournament-harness/tests/integration/test_tourn07_grep_gate.py:23-48 (verbatim)
import re
import subprocess
from pathlib import Path
import pytest

HARNESS_ROOT = Path(__file__).resolve().parents[2]

def test_no_metric_definitions_in_production_code():
    pattern = re.compile(r"^\s*def\s+(directional_accuracy|sharpe|deflated)", re.MULTILINE)
    matches = []
    for py in HARNESS_ROOT.rglob("*.py"):
        if "/tests/" in str(py.as_posix()):
            continue
        text = py.read_text()
        for m in pattern.finditer(text):
            line_no = text[: m.start()].count("\n") + 1
            matches.append((str(py.relative_to(HARNESS_ROOT)), line_no, m.group(0).strip()))
    assert matches == [], "TOURN-07 violation — parallel metric definitions found:\n  " + "\n  ".join(
        f"{p}:{ln}: {snippet}" for p, ln, snippet in matches
    )
```

### CI workflow grep-gate invocation (precedent for BC-03)

```yaml
# Source: .github/workflows/tournament-harness.yml (TOURN-07 grep gate job)
  tourn07-grep-gate:
    name: TOURN-07 grep gate (no parallel metrics)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run grep gate (Phase 3 success criterion #5)
        run: |
          set -e
          MATCHES=$(grep -r --include='*.py' \
            "def directional_accuracy\|def sharpe\|def deflated" \
            services/tournament-harness/ | grep -v '/tests/' || true)
          if [ -n "$MATCHES" ]; then
            echo "TOURN-07 violation — parallel metric definitions found:"
            echo "$MATCHES"
            exit 1
          fi
          echo "TOURN-07 grep gate clean."
```

For BC-03, planner should add an analogous job in `.github/workflows/ci.yml` (or a new `.github/workflows/bybit-bypass-gate.yml`) that runs the BC-03 pytest file on every PR.

### Tape-replay client stubs (BC-07 context)

```python
# Source: services/bybit-connector/app/tape_replay_client.py:206-218 (verbatim)
async def get_orderbook(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
    return {"a": [], "b": [], "ts": 0, "u": 0}

async def get_recent_trades(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
    return {"list": []}

async def get_funding_rate_history(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
    return {"list": []}

async def get_instruments_info(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
    return {"list": []}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Direct Bybit calls in 18 in-scope files | Single bybit-connector service as gatekeeper | This phase (2026-05-21) | Tape mode automatically applies to every consumer; rate limits centralized; testnet/mainnet switch in one place |
| `aiohttp` for ml-prediction download scripts | `httpx` for consistency with `BybitDataFetcher` | This phase | Unified mock library (respx); one HTTP client lifecycle pattern; cleaner error handling |
| Per-script duplicated retry decorator + fail-fast | Shared `bybit_connector_retry` in `shared/` | This phase | One source of truth; planner edits one file to tune retry policy |
| Binance/Kraken/Coinbase adapters registered alongside Bybit | Bybit-only (Binance archived per D-02; Kraken/Coinbase out of scope but eligible carry-in) | This phase | Codebase matches operator policy ("Bybit-first; no other exchange") |
| `tests/ci/test_no_new_setinterval_polling.py` mentioned in CONTEXT | **Does not exist** — was deferred-WS-scope artifact | Discovered during this research | Use `tests/integration/test_preflight_grep_gates.py` (Phase 8) idiom instead |

**Deprecated/outdated:**
- `pybit.unified_trading.HTTP` direct usage outside bybit-connector — replaced by REST proxy.
- Hardcoded `api.bybit.com` / `api-testnet.bybit.com` URLs outside bybit-connector — replaced by `BYBIT_CONNECTOR_URL` env.
- `services/trading-engine/app/exchanges/binance.py` import chain — archived.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7.4.4 + pytest-asyncio 0.23.3 |
| Config file | `services/<svc>/pyproject.toml` + `pytest.ini` (per-service); repo-level `tests/integration/conftest.py` for fresh-clone harness fixtures |
| Quick run command | `pytest tests/ci/test_no_bybit_bypass.py -v` (grep gate, fast) |
| Full suite command | `pytest tests/ -v && pytest services/*/tests/ -v` |
| HTTP mock | `respx==0.20.2` (or 0.22.0 in trading-engine) — already in repo |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| BC-01 | Audit produces `bybit-bypass-audit.json` enumerating every bypass site | scaffolding (audit emits artifact, not pass/fail) | `python scripts/audit_bybit_bypass.py > .planning/evidence/BC-01/bybit-bypass-audit.json` | ❌ Wave 0 — script does not exist; planner creates |
| BC-02 (per consumer) | Refactored consumer calls bybit-connector with correct URL/params | unit (respx) | `pytest services/<svc>/tests/test_<module>.py::test_<name> -x` | ❌ Wave 0 — most refactored consumers will need new test files |
| BC-02 (system) | Refactored scripts fail-fast when bybit-connector down | integration | `pytest tests/integration/test_scripts_fail_fast.py -x` | ❌ Wave 0 — new file |
| BC-03 | Grep gate green on `main`; fails on any new bypass | unit (grep gate itself) | `pytest tests/ci/test_no_bybit_bypass.py -v` | ❌ Wave 0 — new file (the gate itself) |
| BC-04 | trading-engine boots without ImportError; Binance archived | smoke + unit | `python -c "import app.main"` inside `crypto-bot-trading-engine`; `pytest tests/integration/test_trading_engine_boot.py` | ⚠ Boot test exists; verify covers post-archival case |
| BC-05 | `bybit_connector_url` default is `:8001` | unit | `pytest services/market-data-service/tests/test_config.py::test_default_bybit_connector_url -x` | ❌ Wave 0 — new test |
| BC-06 | RUNBOOK contains new symptom in correct format | docs check | `grep -A5 "Market-data stale or missing" RUNBOOK.md` | N/A — manual review |
| BC-07 | `MARKET_DATA_SOURCE=tape` works for all refactored consumers | integration | `pytest tests/integration/test_bybit_connector_tape_preserved.py -v` | ❌ Wave 0 — new file |

### Sampling Rate

- **Per task commit:** `pytest tests/ci/test_no_bybit_bypass.py -v && pytest <relevant service tests>` (grep gate ALWAYS, plus consumer-specific tests)
- **Per wave merge:** `pytest tests/ -v && pytest services/{ml-prediction-service,market-data-service,trading-engine}/tests/ -v` (full repo-level + affected service suites)
- **Phase gate:** Full suite green before `/gsd-verify-work`; CI workflow `.github/workflows/<bybit-bypass-gate.yml>` shows green on the phase-close PR.

### Validation Dimensions

| Dimension | Behavior Asserted | Method |
|-----------|-------------------|--------|
| **Behavior** | Grep gate finds zero violations | `tests/ci/test_no_bybit_bypass.py` |
| **Behavior** | Tape mode replays canned data through refactored consumers | `tests/integration/test_bybit_connector_tape_preserved.py` |
| **Contract** | bybit-connector REST endpoints accept the same params + return same wrapper shape as before refactor | Implicit (no connector code change); explicit assertion via consumer respx tests |
| **Regression** | Existing tests in services/ml-prediction-service, market-data-service, trading-engine still pass | Service-level pytest runs in CI |
| **Boundary** | Refactored scripts fail-fast when bybit-connector is unreachable | `tests/integration/test_scripts_fail_fast.py` |
| **Permission** | No new auth flows; existing `BYBIT_API_KEY`/`BYBIT_API_SECRET` env propagation unchanged | Verified by absence of new env var introductions |
| **Archival integrity** | trading-engine boots without ImportError after Binance archival | `python -c "import app.main"` smoke + Docker `up -d trading-engine` healthcheck |

### Wave 0 Gaps

- [ ] `tests/ci/__init__.py` — Wave 0 (new directory; needs init file for pytest collection)
- [ ] `tests/ci/test_no_bybit_bypass.py` — covers BC-03 (NEW)
- [ ] `tests/integration/test_bybit_connector_tape_preserved.py` — covers BC-07 (NEW)
- [ ] `tests/integration/test_scripts_fail_fast.py` — covers BC-02/D-04 fail-fast (NEW)
- [ ] `services/market-data-service/tests/test_config.py::test_default_bybit_connector_url` — covers BC-05 (NEW or new case in existing file)
- [ ] `scripts/audit_bybit_bypass.py` — produces BC-01 audit artifact (NEW)
- [ ] Per-consumer respx tests for refactored sites (BC-02) — Wave 0 RED-first per TDD mode

## Project Constraints (from CLAUDE.md)

The following directives from `./CLAUDE.md` apply to Phase 13 planning. Planner MUST verify compliance:

- **Bybit-first; no other exchange** — D-02 archives Binance per this constraint; Kraken/Coinbase live alongside Binance in `services/trading-engine/app/exchanges/` and are NOT in scope (eligible carry-in)
- **Search rule (mandatory):** `/graphify` before broad searches — planner should run graphify over `services/bybit-connector/` and the bypass-site files when constructing the plan; researcher already grep-audited so plan-phase grep is targeted
- **Risk caps wired into trading-engine** (5% daily-loss; 2% per-trade in LIVE / 10% in paper per ADR-010) — Phase 13 touches `services/trading-engine/app/exchanges/__init__.py` and `factory.py`; neither changes risk logic; **verify trading-engine boots cleanly with `MAX_POSITION_RISK_PCT` enforcement intact**
- **Trading-mode flags — 4-step path to LIVE** — Phase 13 must not alter `BYBIT_TESTNET` / `PAPER_TRADING_MODE` / `TRADING_MODE` / `LIVE_TRADING_ACK` semantics
- **Feature flags** (`ENABLE_ML_PREDICTIONS=false`, `ENABLE_SENTIMENT_ANALYSIS=false`) — Phase 13 refactor touches ml-prediction-service orderbook handler; should NOT flip the flag default; should preserve idle-state behavior
- **Auto-trader** (`AUTO_TRADING_ENABLED=true` in `.env`, kill-switch at `safety/EMERGENCY_STOP`) — unaffected
- **Validated symbols** (BTC/ETH/SOL/BNB/ADA only) — Phase 13 refactor of `scripts/collect_*` must not change the validated-symbol set; XRP/DOGE excluded per existing constraint
- **Never commit `.env`** — Phase 13 might touch `rotate_secrets.py` env handling but writes nothing to `.env`
- **REST routing convention** (`/api/<domain>/<resource>`, no `/v1/` prefix per ADR-007) — bybit-connector currently uses `/api/v1/market/...` (verified `services/bybit-connector/app/main.py:739-944`); this is an **exception** to ADR-007 because bybit-connector predates ADR-007 and the planner should NOT "fix" the prefix in this phase
- **Commits**: conventional (`feat(svc): ...`); branches `feature/<service>-<desc>`, `fix/<desc>` — Phase 13 commits should follow this convention; suggested prefixes:
  - `refactor(bybit-connector): centralize via REST for <consumer>` (per BC-02 task)
  - `feat(ci): add tests/ci/test_no_bybit_bypass.py grep gate` (BC-03)
  - `chore(exchanges): archive Binance adapter per operator policy` (BC-04)
  - `fix(market-data): correct bybit_connector_url default port` (BC-05)
  - `docs(runbook): add bybit-connector chain symptom` (BC-06)
  - `test(integration): assert tape mode preserved across refactored consumers` (BC-07)
- **Verification standards** — "No declare features working end-to-end on curl/HTTP 200 alone" — `/verify-stack` checklist applies before phase close

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `aiohttp` in some download scripts can be cleanly converted to `httpx` during refactor (sync `.json()` swap, etc.) | Library Discrepancy + Pitfall 6 | If a script uses aiohttp-specific features (TCP connector tuning, multipart upload), conversion is invasive. Mitigation: planner reads each script before refactor, leaves aiohttp if conversion balloons. |
| A2 | rotate_secrets restart-then-ping (Option A in Pattern 3) is acceptable to operator | Pattern 3 | If operator wants no container restarts inside rotation, planner needs Option B (new connector endpoint). Researcher recommends surfacing as planner-watch and asking in plan-phase if uncertain. |
| A3 | Option A (empty-orderbook tape) is sufficient for BC-07 acceptance | Tape-Mode Coverage Gap | If operator wants full orderbook fixtures, BC-07 expands by ~130 LOC (capture script + replay logic + JSONL data). Surface as discretion call. |
| A4 | `scripts/test_public_bybit_api.py` is a diagnostic probe that can be deleted | Endpoint Mapping | If it's a live-smoke companion (used by an undocumented operator workflow), deletion breaks it. Mitigation: planner greps for invocations before deleting. |
| A5 | `shared/health_check.py:771` Bybit ping can be replaced with bybit-connector `/health` ping | Endpoint Mapping | If callers of `shared/health_check.py:async def check_bybit_api()` expect specific Bybit-server-time response shape, the change leaks. Mitigation: planner inspects all callers before refactor. |
| A6 | Kraken and Coinbase adapters (not in CONTEXT scope) can stay registered — gate doesn't catch them | Architectural Responsibility Map note | If "Bybit-only" policy extends to Kraken/Coinbase in a future phase, leaving them registered now is dead weight. Surface as carry-in. |
| A7 | The grep gate exemption list (`scripts/tape/`, `_archive_*/`, `__pycache__/`) is complete | Pattern 5 + Pitfall 4 | Missing exemption surfaces as a false positive in CI; planner adjusts the EXEMPT_PATHS set. Low risk — additive change. |
| A8 | `tests/integration/test_preflight_grep_gates.py` is a valid precedent (researcher's substitute for the non-existent `tests/ci/test_no_new_setinterval_polling.py`) | Pattern 5 + Sources | Verified — file exists, is green on main, follows dual-form scan idiom. No risk. |
| A-Shared | A shared `BybitConnectorClient` at `shared/bybit_connector_client.py` is a better factoring than per-consumer inline httpx | Primary recommendation in Summary | Inline-per-consumer is also valid; planner decides (Open Question #5). Risk if wrong: minor — slightly more duplicated boilerplate across consumers. |

**Note on assumed claims:** A1, A2, A3, A4, A5 are surfaced for plan-phase decision/confirmation. A6, A7, A8 are operator-confirmation-not-needed (A8 verified, A6/A7 are additive/conservative).

## Open Questions (RESOLVED 2026-05-21)

> All seven questions resolved during plan-phase. Decisions encoded inline below with one-line rationale per item. Each decision is also reflected in the corresponding PLAN.md `<action>` text.

1. **Should Kraken and Coinbase adapters also be archived?**
   - What we know: D-02 archives only Binance (operator's exact words: "I will not use binance just bybit"). Kraken and Coinbase live in same package and have similar zero-production-use status (manager.py docstrings only, factory registration, router default fees).
   - What's unclear: Operator did not mention Kraken/Coinbase. Strict reading of D-02 = archive only Binance.
   - Recommendation: Plan-phase asks operator one-line clarification; if "archive all three", BC-04 expands proportionally; if "Binance only", leave Kraken/Coinbase and surface as carry-in for a later milestone.
   - **RESOLVED: Binance-only.** Strict-read D-02 ("I will not use binance just bybit"). Kraken/Coinbase archival carries forward as `BC-FOLLOWUP-01` for a later milestone if operator extends the policy.

2. **rotate_secrets credential-propagation: Option A (restart) or Option B (new endpoint)?**
   - What we know: Pattern 3 above explains both. Option A is closer to production reality; Option B is cleaner API surface.
   - What's unclear: Operator preference unknown; CONTEXT says "likely no new endpoints" but the rotation flow has unique credential-injection needs.
   - Recommendation: Plan with Option A as default; flag as discretion call in plan-phase.
   - **RESOLVED: Option A — restart-then-ping.** Closer to production reality (bybit-connector reads creds at boot anyway); avoids new attack surface (Option B would expose creds in request body per Security V3 reasoning). Encoded in Plan 07 Task 1.

3. **BC-07 tape coverage: Option A (empty stubs assertion) or Option B (full orderbook fixtures)?**
   - What we know: tape_replay_client already stubs to empty; ml-prediction is gated off; v1.2 doesn't enable ml-prediction.
   - What's unclear: Operator may want richer orderbook fixtures for future ml-prediction re-enablement smoke.
   - Recommendation: Plan with Option A; surface Option B as `BC-FOLLOWUP-01` carry-in.
   - **RESOLVED: Option A — assert empty stubs.** Aligns with current `ENABLE_ML_PREDICTIONS=false` gating; richer fixtures (Option B, +~130 LOC capture/replay/JSONL) carry forward as `BC-FOLLOWUP-02` for ml-re-enablement work.

4. **Does `services/market-data-service/tests/test_fetcher.py` already cover the pagination behavior tested by `test_pagination_fix.py`?**
   - What we know: `test_pagination_fix.py` is at the test boundary that's getting refactored; it looks more like a manual diagnostic than a unit test (real HTTP calls, print statements).
   - What's unclear: Whether deleting it loses any coverage.
   - Recommendation: Plan-phase verifies coverage in test_fetcher.py before deletion; if coverage gap exists, planner adds an explicit refactor task that ports the relevant pagination assertions.
   - **RESOLVED: Delete `test_pagination_fix.py`.** Diagnostic shape (real HTTP calls, print statements), not a unit test. Pagination behavior remains implicitly covered by production `fetcher.py` lines 248-391. Explicit pagination unit test surfaced as `BC-FOLLOWUP-03` carry-in (Plan 06 SUMMARY).

5. **Shared `BybitConnectorClient` class vs. per-consumer inline httpx?**
   - What we know: A shared class at `shared/bybit_connector_client.py` reduces duplication (fail-fast logic, retry decorator, URL pattern, error message would live in one place) and gives the test seam a single mock target. Per-consumer inline httpx is path-of-least-resistance per file.
   - What's unclear: CONTEXT didn't specify; researcher recommended shared but it adds new repo structure (`shared/` may not currently exist outside `shared/health_check.py`).
   - Recommendation: Plan-phase decides. If sharing, plan a Wave-0 task that lands `shared/bybit_connector_client.py` + relocates `bybit_connector_retry` to `shared/circuit_breaker.py` before any refactor tasks consume them. If inline, accept per-script duplication and lift the boilerplate into a snippet in `.planning/codebase/PATTERNS.md` instead.
   - **RESOLVED: Per-consumer inline httpx.** Avoids introducing new `shared/` repo structure mid-phase; minimal-diff per-file. Boilerplate snippet documented in `13-PATTERNS.md` Shared 1 (decorator) and Shared 2 (fail-fast scaffold). Each refactored consumer copies the snippet inline.

6. **`aiohttp` → `httpx` universal conversion, or per-script judgment?**
   - What we know: 4 scripts use `aiohttp`; the rest use `httpx`. Bybit replacement is mandatory; HTTP library swap is a consistency choice on top.
   - What's unclear: Whether operator cares about consistency vs. minimal-diff.
   - Recommendation: Plan-phase decides. Default to convert (matches `.planning/codebase/TESTING.md` standard); fallback is leave-as-is per-script.
   - **RESOLVED: Per-script judgment.** Convert by default (matches TESTING.md standard, drops the `await response.json()` pitfall per Pitfall 6), but if a script uses aiohttp-specific features (TCP connector tuning, multipart upload) leave aiohttp and only swap the URL/parser. Plans 04/05/06 invoke this judgment per file.

7. **Is `scripts/test_public_bybit_api.py` referenced by any automation, or is it a developer-only probe?**
   - What we know: Filename suggests probe; grep-audit listed it.
   - What's unclear: Whether any operator runbook, CI workflow, or makefile invokes it.
   - Recommendation: Plan-phase greps `Makefile`, `.github/workflows/`, `RUNBOOK.md`, `docs/` for references; if none, delete; if any, refactor.
   - **RESOLVED: Delete `scripts/test_public_bybit_api.py`.** Plan 06 Task 2 includes the grep step (Makefile + `.github/workflows/` + RUNBOOK.md + `docs/` + `*.py` repo-wide). Zero references → delete. If the grep surfaces an unexpected reference, Plan 06 escalates as `## ⚠ Source Audit: Unplanned Items Found` and pauses.

## Security Domain

Security enforcement is ENABLED per `.planning/config.json` (`security_enforcement: true`, `security_asvs_level: 1`). Applicable ASVS categories for Phase 13:

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `BYBIT_API_KEY`/`BYBIT_API_SECRET` continue to live in `.env` (gitignored); `rotate_secrets.py` flow is the only change. Auth ping post-rotation uses bybit-connector `/api/v1/account/balance` (Bearer/HMAC handled internally by `pybit` inside bybit-connector, not exposed). |
| V3 Session Management | n/a | No new sessions; existing bybit-connector handles Bybit sessions. |
| V4 Access Control | yes | bybit-connector `POST /admin/tape/reset` is admin-guarded (`settings.market_data_source != "tape"` refuses; main.py:1038). Verify CI grep gate file path is not exposed via dashboard or unintended public route. |
| V5 Input Validation | yes | Refactored consumers accept symbol/interval/limit params; should validate against bybit-connector's existing input validation (FastAPI Pydantic models in `services/bybit-connector/app/models.py`). No new validation surface added. |
| V6 Cryptography | yes | No hand-rolled crypto. Bybit HMAC signing stays inside `pybit` library (bybit-connector only). |
| V7 Error Handling and Logging | yes | Refactored consumers must NOT log Bybit API keys or wrapped error bodies that may contain credentials. Use existing `SecretMaskingFormatter` from `services/bybit-connector/app/main.py:60-103` as reference for logging hygiene. |
| V10 Communications | yes | bybit-connector ↔ Bybit uses TLS (https://). bybit-connector ↔ consumers uses HTTP inside compose network (Docker internal); on host operator runs, `http://localhost:8001` is loopback (not over network). No TLS regression. |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Refactored consumer silently logs Bybit response containing API key/secret | Information Disclosure | Use `SecretMaskingFormatter` pattern from bybit-connector; never log full response bodies that may include `apiKey`/`secret` fields. |
| `rotate_secrets.py` writes Vault entries but bybit-connector unrestart leaves stale creds in memory | Tampering / DoS | Pattern 3 Option A restart ensures memory copy matches Vault; Pattern 3 Option B's new endpoint would expose creds in request body — adds attack surface. **Prefer Option A.** |
| New CI grep gate test exposes Bybit URL patterns in stack traces on failure | Information Disclosure | Acceptable — URLs are public Bybit endpoints, not secrets. |
| `scripts/tape/capture_bybit.py` (allowlisted exception) silently elevated to use API keys | Elevation of Privilege | tape capture currently uses public REST only (no auth). Keep authless. Add comment at top of file: "PUBLIC ENDPOINTS ONLY — do not add api_key/api_secret to this script." |
| Refactored ml-prediction orderbook handler returns sensitive Bybit error message to caller (5xx propagation) | Information Disclosure | Wrap bybit-connector errors as 502 BadGateway with generic message; do not propagate inner Bybit `retMsg` to API consumer. |
| Binance archival leaves dangling references in factory.py → ImportError → trading-engine container crashloop → DoS | DoS | BC-04 task includes boot-smoke test (`docker compose up -d trading-engine` + health-check) to catch this before merge. |

### Security-Relevant Code Paths Touched

- `services/ml-prediction-service/app/handlers/orderbook.py` — error-message scrubbing
- `infrastructure/scripts/rotate_secrets.py` — credential lifecycle
- `services/trading-engine/app/exchanges/{factory,__init__,binance}.py` — import surface area
- `tests/ci/test_no_bybit_bypass.py` — CI workflow integration
- `RUNBOOK.md` — operator-facing failure triage docs

No new auth flows, no new secret storage, no new TLS surface. Refactor preserves existing security boundaries.

## Sources

### Primary (HIGH confidence)

- `services/bybit-connector/app/main.py` lines 1-1100 (REST surface + tape admin endpoint)
- `services/bybit-connector/app/config.py` (BYBIT_TESTNET, MARKET_DATA_SOURCE, tape fixtures path)
- `services/bybit-connector/app/tape_replay_client.py` (orderbook/funding/recent-trades/instruments stubs at lines 200-219)
- `services/market-data-service/app/fetcher.py` (BybitDataFetcher template)
- `services/market-data-service/app/circuit_breaker.py` (`bybit_connector_retry` decorator)
- `services/market-data-service/app/config.py` (port default defect line 58)
- `services/trading-engine/app/exchanges/factory.py` (Binance registration lines 62, 186-210)
- `services/trading-engine/app/exchanges/__init__.py` (Binance exports lines 329-336, 513-516)
- `services/trading-engine/app/exchanges/base.py` (ExchangeName enum line 55-65)
- `services/trading-engine/tests/test_multi_exchange.py` (skipped wholesale at line 24)
- `services/ml-prediction-service/app/handlers/orderbook.py` lines 245-303 (bypass site)
- `services/ml-prediction-service/download_missing_symbols_data.py` (aiohttp bypass)
- `scripts/collect_180_days_data.py`, `scripts/collect_ml_training_data_simple.py`, `scripts/fetch_real_historical_data.py` (script bypasses)
- `scripts/tape/capture_bybit.py` lines 1-60 (legitimate exception — captures real Bybit for fixtures)
- `backtesting/bybit_data_fetcher.py` lines 1-100 (testnet/mainnet switch bypass)
- `services/market-data-service/tests/test_pagination_fix.py` lines 1-100 (test bypass)
- `infrastructure/scripts/rotate_secrets.py` lines 200-260 (pybit auth ping)
- `shared/health_check.py` lines 760-790 (probe bypass)
- `tests/integration/test_preflight_grep_gates.py` (Phase 8 grep gate precedent)
- `services/tournament-harness/tests/integration/test_tourn07_grep_gate.py` (Phase 3 grep gate precedent)
- `.github/workflows/preflight-live-readiness.yml`, `.github/workflows/tournament-harness.yml` (CI grep-gate wiring precedents)
- `.planning/codebase/TESTING.md` (respx standard, mock conventions)
- `.planning/codebase/CONVENTIONS.md` (FastAPI service layout, autoflake noqa rule)
- `.planning/codebase/INTEGRATIONS.md` (stale claim line 231 confirmed)
- `.planning/codebase/CONCERNS.md` (no Phase-13-relevant operational gotchas beyond restart-after-config)
- `RUNBOOK.md` lines 1-100 (existing symptom format)
- `services/*/requirements.txt` (verified library versions: httpx 0.27.0, respx 0.20.2, pybit 5.6.2, tenacity 8.2.3, pytest 7.4.4, pytest-asyncio 0.23.3, aiohttp 3.9.3)

### Secondary (MEDIUM confidence)

- `services/bybit-connector/tests/test_tape_replay_client.py` (existence confirmed, content not read in full — assumed standard test patterns)
- `tests/integration/conftest.py` lines 1-100 (fresh-clone fixture pattern for integration tests)
- `tests/smoke/test_smoke.py` (existence confirmed; one bypass found; content not read in full)

### Tertiary (LOW confidence)

- `scripts/collect_6months_historical.py`, `scripts/collect_bybit_direct_180days.py`, `scripts/data_quality_enhancement.py`, `services/ml-prediction-service/download_op_sui_6months.py`, `services/ml-prediction-service/download_suiusdt_12months.py` — bypass confirmed by grep but exact line numbers / shape not individually verified; planner's BC-01 audit task closes this gap

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every library verified in `services/*/requirements.txt`
- Architecture patterns: HIGH — every pattern derived from in-repo precedent (`BybitDataFetcher`, `test_tourn07_grep_gate.py`, etc.)
- Pitfalls: HIGH — every pitfall is documented elsewhere in `.planning/codebase/` or comes from researcher's direct reading of the code
- Refactor scope (BC-01): HIGH — full repo-wide grep ran; 18 in-scope sites + 1 exception identified
- Binance archival call-graph (BC-04): HIGH — all import sites traced and verified
- Tape coverage gap (BC-07): HIGH — verified by reading `tape_replay_client.py:200-219`
- CI grep gate precedent (BC-03): HIGH — verified `tests/ci/` does not exist; Phase 8/Phase 3 idioms used instead
- rotate_secrets refactor (BC-02 D-07): MEDIUM — Option A vs Option B is a planner decision; researcher recommended Option A with rationale but did not verify operator preference

**Research date:** 2026-05-21
**Valid until:** 2026-06-20 (30 days; refactor target is stable code, no upstream library churn expected)
