# Phase 13: Bybit-Connector Market-Data Centralization - Pattern Map

**Mapped:** 2026-05-21
**Files analyzed:** ~25 (new + refactor + archive + docs)
**Analogs found:** 23 / 25 (2 net-new with no in-repo precedent — see "No Analog Found")

This file maps each phase-13 file to its closest existing analog and quotes the
exact excerpt to copy/adapt. **Do not re-summarise RESEARCH.md** — see that file
for design rationale, pitfalls, and assumptions. This file is "where to look in
the repo when you sit down to edit each file."

---

## File Classification

| Phase-13 File (new / modified / archived) | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `services/ml-prediction-service/app/handlers/orderbook.py` (refactor) | service-runtime caller | request-response | `services/market-data-service/app/fetcher.py:50-246` | exact (both call bybit-connector REST) |
| `services/ml-prediction-service/download_missing_symbols_data.py` (refactor) | standalone script | batch / request-response | `services/market-data-service/app/fetcher.py:106-201` + D-04 fail-fast | role-match (aiohttp→httpx conversion) |
| `services/ml-prediction-service/download_{final_4,op_sui_6months,suiusdt_12months}.py` (refactor) | standalone script | batch / request-response | same as above | role-match |
| `scripts/collect_180_days_data.py` (refactor) | standalone script | batch / request-response | `services/market-data-service/app/fetcher.py:248-391` (paginated klines) + D-04 fail-fast | exact |
| `scripts/collect_6months_for_ml.py`, `collect_6months_historical.py`, `collect_bybit_direct_180days.py`, `collect_ml_training_data_simple.py`, `data_quality_enhancement.py`, `fetch_real_historical_data.py`, `test_public_bybit_api.py` (refactor or delete) | standalone script | batch / request-response | same as above | exact / role-match |
| `backtesting/bybit_data_fetcher.py` (refactor — preserve `is_mainnet` filter semantics) | library wrapper | request-response | `services/market-data-service/app/fetcher.py:50-110` | exact |
| `infrastructure/scripts/rotate_secrets.py` (refactor auth-ping) | infra utility | request-response | `services/bybit-connector/app/main.py:532-557` (account/balance endpoint) | role-match (Pattern 3 in RESEARCH) |
| `services/market-data-service/tests/test_pagination_fix.py` (refactor or delete) | diagnostic test | request-response | `services/trading-engine/tests/test_instruments_cache.py` (respx idiom) | role-match (delete preferred) |
| `services/market-data-service/app/config.py` (line 58 default-port fix) | config | static | n/a — one-line edit | exact |
| `services/market-data-service/tests/test_config.py` or **new** `tests/test_config_defaults.py` (BC-05 assertion) | unit test | static | `services/market-data-service/tests/test_config.py:46-49` (existing port-default assertion shape) | role-match — **BUT existing file is `pytest.mark.skip` wholesale; see WARNING in BC-05 row below** |
| `services/trading-engine/app/exchanges/factory.py` (remove Binance) | refactor | static | (deletion only — see BC-04 excerpt) | exact |
| `services/trading-engine/app/exchanges/__init__.py` (remove Binance re-exports) | refactor | static | (deletion only) | exact |
| `services/trading-engine/tests/test_multi_exchange.py` (delete file) | unit test | n/a | n/a — file is wholesale `pytest.mark.skip` already; deletion is cleanest | exact |
| `services/trading-engine/app/exchanges/binance.py` → `_archive_exchanges/binance.py` (archive) | archival | static | `services/ml-prediction-service/models/_archive_lstm/` (precedent for "unreachable from sys.path") | partial — **see CAVEAT in BC-04 row** |
| `scripts/audit_bybit_bypass.py` (NEW — Wave 0 audit) | script | batch / scan | `tests/integration/test_preflight_grep_gates.py:50-95` (rglob+regex scan idiom) | role-match (test→script adaptation) |
| `tests/ci/__init__.py` (NEW — empty for pytest collection) | scaffolding | static | n/a — empty file convention | n/a |
| `tests/ci/test_no_bybit_bypass.py` (NEW — BC-03 grep gate) | unit test (gate) | scan | `tests/integration/test_preflight_grep_gates.py` (Phase 8) + `services/tournament-harness/tests/integration/test_tourn07_grep_gate.py` (Phase 3) | exact |
| `tests/integration/test_bybit_connector_tape_preserved.py` (NEW — BC-07) | integration test | request-response | `services/bybit-connector/app/tape_replay_client.py:200-218` (stub shapes) + Pattern 1 in RESEARCH | role-match |
| `tests/integration/test_scripts_fail_fast.py` (NEW — BC-02/D-04 contract) | integration test | request-response | RESEARCH Pattern 2 (D-04 fail-fast) + subprocess invocation idiom | role-match — no direct in-repo analog |
| Per-consumer respx unit tests in service test dirs (NEW) | unit test | request-response | `services/trading-engine/tests/test_instruments_cache.py:107-149` (respx mock against bybit-connector REST) | exact |
| `.planning/evidence/BC-01/.gitkeep` (NEW — directory marker) | scaffolding | static | `.planning/evidence/CIRESTORE-02/`, `.planning/evidence/OP-04/`, `.planning/evidence/forward_paper_test/` (directory presence convention) | exact |
| `.planning/evidence/BC-01/bybit-bypass-audit.json` (NEW — emitted by audit script) | data artifact | n/a — script output | n/a — schema specified in RESEARCH BC-01 row | n/a |
| `.github/workflows/bybit-bypass-gate.yml` OR extension of `.github/workflows/ci.yml` | CI workflow | scan | `.github/workflows/tournament-harness.yml:24-41` (standalone job) OR `.github/workflows/preflight-live-readiness.yml:25-43` (extend existing) | exact — planner picks pattern |
| `RUNBOOK.md` (BC-06 append) | docs | static | `RUNBOOK.md:22-105` (existing 6 symptoms — Diagnose / Action / Verification triad) | exact |
| `.planning/codebase/INTEGRATIONS.md:231` (D-10 close edit) | docs | static | n/a — one-line edit | exact |

---

## Pattern Assignments

### `services/ml-prediction-service/app/handlers/orderbook.py` (BC-02 service consumer)

**Analog:** `services/market-data-service/app/fetcher.py:204-246` (`get_ticker`) + `:105-201` (`get_kline`).

**TDD discipline:** RED-first — add respx test asserting the consumer hits `bybit-connector` URL with correct wrapper-parse BEFORE editing the handler.

**Two coupled swaps (do not skip either):**

1. **URL swap.** `https://api.bybit.com/v5/market/orderbook` → `${BYBIT_CONNECTOR_URL}/api/v1/market/orderbook`.
2. **Parser swap.** Bybit raw shape `{retCode, retMsg, result: {a, b, ts}}` → bybit-connector wrapper `{success, data: {a, b, ts, u}}`. Pitfall 2 in RESEARCH catches this exact mistake.

**Before (orderbook.py:245-303 — VERBATIM):**
```python
# url = "https://api.bybit.com/v5/market/orderbook"                        ← swap to bybit-connector
# params = {"category": "linear", "symbol": symbol.upper(), "limit": min(limit, 500)}
# response = await _http_client.get(url, params=params)
# response.raise_for_status()
# data = response.json()
# if data.get("retCode") != 0:                                              ← swap to data.get("success") is False
#     raise HTTPException(status_code=502, detail=f"Bybit API error: ...")
# result = data.get("result", {})                                            ← swap to data["data"]
# bids = [[float(b[0]), float(b[1])] for b in result.get("b", [])]
# asks = [[float(a[0]), float(a[1])] for a in result.get("a", [])]
# return {"bids": bids, "asks": asks, "timestamp": result.get("ts", ...)}
```

**After-pattern source:** RESEARCH.md "Pattern 1: Refactored Service-Runtime Caller" (already a 30-line example). Adapt from `services/market-data-service/app/fetcher.py:204-246` (ticker) — same `if not payload.get("success"): raise ...; result = payload["data"]` shape.

**Imports pattern** (`fetcher.py:10-18`):
```python
import httpx
import asyncio
import logging
from typing import List, Dict, Any, Optional
from app.config import get_settings
from app.circuit_breaker import bybit_connector_retry   # ← if shared client lands per Open Q #5, swap to shared
```

**Retry decorator** (`fetcher.py:105`):
```python
@bybit_connector_retry
async def get_kline(self, symbol: str, ...) -> List[Dict[str, Any]]:
```

**Test seam** — use respx, mock `${CONNECTOR_URL}/api/v1/market/orderbook`. Template: `services/trading-engine/tests/test_instruments_cache.py:107-149`.

---

### `services/ml-prediction-service/download_*.py` and `scripts/collect_*.py`, `scripts/fetch_*.py` (BC-02 standalone scripts)

**Analog:** `services/market-data-service/app/fetcher.py:248-391` (paginated historical klines) + RESEARCH "Pattern 2" (D-04 fail-fast).

**TDD discipline:** RED-first — add a `tests/integration/test_scripts_fail_fast.py` case asserting `python <script>` exits 2 with operator-readable error when `BYBIT_CONNECTOR_URL` unreachable, BEFORE editing each script. One shared test for fail-fast covers the contract; per-script respx tests cover the success path.

**aiohttp→httpx note:** 4 download scripts currently use `aiohttp`. Pitfall 6 in RESEARCH: `response.json()` is **sync** in httpx (drop the `await`). Conversion cost ~10 LOC per script. RESEARCH Open Question #6 leaves conversion vs leave-as-is to plan-phase — if leaving aiohttp, replace only the URL and shape, don't touch the client.

**Hostname rule:** Default URL `http://localhost:8001` (host-friendly); compose env override sets `http://bybit-connector:8001`. See RESEARCH Pitfall 1.

**Fail-fast scaffold** (RESEARCH "Pattern 2", lines 297-311 — verbatim, copy into every script):
```python
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
```

**Pagination shape** (preserve from `fetcher.py:248-391`): every script that fetches > 1000 candles must call `/api/v1/market/kline` in batch-back-from-end-time loop, dedupe by timestamp, sort ascending. bybit-connector preserves Bybit V5's `data["list"]` shape so the dedupe/sort code from `fetcher.py:330-360` can be lifted verbatim.

---

### `backtesting/bybit_data_fetcher.py` (BC-02 — preserve `is_mainnet` filter semantics)

**Analog:** `services/market-data-service/app/fetcher.py:50-201`.

**Before (verbatim, `bybit_data_fetcher.py:27-40`):**
```python
def __init__(self, testnet: bool = False):
    if testnet:
        self.base_url = "https://api-testnet.bybit.com"
    else:
        self.base_url = "https://api.bybit.com"
    self.client = httpx.AsyncClient(timeout=30.0)
    self.rate_limit_delay = 0.15
```

**After:** drop the `testnet` parameter entirely — bybit-connector chooses testnet vs mainnet via its own `BYBIT_TESTNET` env. The `is_mainnet=true` data-integrity filter (CLAUDE.md "Backtest must filter `is_mainnet=true`") is a *DB query filter on the `klines` table*, not on the fetcher constructor — that filter stays in the backtest query layer, not here. **Do not delete the `is_mainnet` filter elsewhere in the backtest pipeline.**

**Replace constructor with:**
```python
def __init__(self, base_url: Optional[str] = None):
    self.base_url = base_url or os.getenv("BYBIT_CONNECTOR_URL", "http://localhost:8001")
    self.client = httpx.AsyncClient(timeout=30.0, base_url=self.base_url)
```

---

### `infrastructure/scripts/rotate_secrets.py` (BC-02 D-07 auth-ping refactor)

**Analog:** `services/bybit-connector/app/main.py:532-557` (existing `/api/v1/account/balance` endpoint — the auth-ping target).

**Before (rotate_secrets.py:230-254 — VERBATIM):**
```python
try:
    from pybit.unified_trading import HTTP                                  # ← REMOVE
    base_url = "https://api-testnet.bybit.com" if testnet else "https://api.bybit.com"   # ← REMOVE
    session = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret) # ← REMOVE
    result = session.get_wallet_balance(accountType="UNIFIED")
    if result.get('retCode') == 0:
        logger.info("✓ New credentials validated successfully")
        return True
    else:
        logger.error(f"Credential validation failed: {result.get('retMsg')}")
        return False
```

**Pattern 3 Option A (RESEARCH default):** `docker compose restart bybit-connector` BEFORE the auth-ping, then `httpx.get("${CONNECTOR_URL}/api/v1/account/balance")`, then check `payload.get("success") is True`. RESEARCH Open Q #2 surfaces Option B (new connector endpoint) as the alternative — **planner decides; default Option A**.

**Important nuance** (RESEARCH §"Pattern 3" + Pitfall 3): bybit-connector reads creds at boot, not per-request. So the restart-then-ping order is load-bearing. If skipped, the ping validates the OLD creds and silently passes.

---

### `services/market-data-service/app/config.py` (BC-05 — one-line fix)

**Current line 58:**
```python
bybit_connector_url: str = Field(default="http://localhost:8002")
```

**Target:**
```python
bybit_connector_url: str = Field(default="http://localhost:8001")
```

(Bybit-connector runs on `:8001` per CLAUDE.md service table; market-data-service is `:8002` — the existing default was a copy-paste of the service's own port, harmless under compose because env overrides, harmful for any host-side script that reads the config without compose env.)

---

### BC-05 test assertion — **WARNING: host file is wholesale-skipped**

**Analog (shape only):** `services/market-data-service/tests/test_config.py:46-49`:
```python
def test_default_service_port(self):
    """Test default service port is 8002 (matches compose / project port table)."""
    settings = Settings()
    assert settings.service_port == 8002
```

**Critical:** `services/market-data-service/tests/test_config.py:15` is `pytestmark = pytest.mark.skip(reason="stale tests after PR #86 refactor; needs rewrite")` — every test in the file is skipped wholesale. Adding the new BC-05 case inside that file means the new test never runs.

**Planner options (pick one):**
1. **NEW file** `services/market-data-service/tests/test_config_defaults.py` — clean, runs in CI, isolated from the PR-#86 skip. **Recommended.**
2. Un-skip `test_config.py` entirely — drags ~10 unrelated broken tests into scope; out-of-scope cleanup. **Not recommended.**
3. New test class inside `test_config.py` with its own `pytestmark = []` reset — brittle; pytest mark resolution at module-level is the wrong layer to override.

Same caveat applies if BC-02 surfaces an analog respx test inside `services/market-data-service/tests/test_fetcher.py:15` — it is also wholesale-skipped.

---

### `services/trading-engine/app/exchanges/factory.py` (BC-04 — remove Binance registration)

**Lines to delete:**
- Line 62: `from app.exchanges.binance import BinanceExchangeAdapter`
- Lines 186-210: Binance adapter registration block (the `if ExchangeName.BINANCE not in self._registry: self.register(... adapter_class=BinanceExchangeAdapter, capabilities=...)`)

**What to KEEP:**
- `ExchangeName.BINANCE` enum value at `services/trading-engine/app/exchanges/base.py:62` — D-02 archives the adapter, not the enum (RESEARCH Anti-Pattern note: removing enum value forces unrelated edits in `manager.py:256` docstring and `router.py:400` default-fees dict).

---

### `services/trading-engine/app/exchanges/__init__.py` (BC-04 — remove Binance re-exports)

**Lines to delete:**
- Lines 329-336 (the `from app.exchanges.binance import (...)` block — `BinanceExchangeAdapter`, `BinanceAdapterConfig`, `BinanceRateLimiter`, `create_binance_adapter`, `map_binance_error`, `BINANCE_ERROR_MAP`)
- Lines 513-516 (the `__all__` entries for `"BinanceExchangeAdapter"`, `"BinanceAdapterConfig"`, `"BinanceRateLimiter"`, `"create_binance_adapter"`)
- Line 501 (`"BINANCE_ERROR_MAP"`) and line 502 (`"map_binance_error"`) if present in `__all__` — verify exact lines after the line-329 deletion shifts numbering.

**Verification gate** (RESEARCH Security Domain): post-edit, run `python -c "import app.main"` inside `crypto-bot-trading-engine` — must not raise ImportError. Then `docker compose -f docker-compose.unified.yml up -d trading-engine` and confirm `/health` returns 200.

---

### `services/trading-engine/tests/test_multi_exchange.py` (BC-04 — file deletion)

**Current state:** Line 24 is `pytestmark = pytest.mark.skip(reason="stale tests after PR #86 refactor; needs rewrite")` — entire file skipped. Lines 54-56 import `BinanceExchangeAdapter`, `KrakenExchangeAdapter`, `CoinbaseExchangeAdapter`. After BC-04 archival, those imports will fail at **collection time** (before the skip takes effect), so CI breaks even though tests are skipped.

**Recommendation (RESEARCH §"Binance Archival Call-Graph Verification" planner action #4):** delete the file. It's already dead test code; deletion signals intent and removes the import-time landmine.

---

### `services/trading-engine/app/exchanges/binance.py` → `_archive_exchanges/binance.py` (BC-04 archive)

**Operation:**
```bash
git mv services/trading-engine/app/exchanges/binance.py _archive_exchanges/binance.py
```

**Precedent caveat (advisor flagged):** `services/ml-prediction-service/models/_archive_lstm/` is the in-repo *unreachability* precedent (no `__init__.py`, not on `sys.path`), but it sits **nested under a service's models dir**, not at **repo root**. CONTEXT D-02's `_archive_exchanges/binance.py` choice puts the archive at **repo root** — that's a CONTEXT decision, not a precedent claim. Both placements share the same "unreachable from sys.path" property; the location difference is intentional per CONTEXT.

**Add directory marker:** `_archive_exchanges/.gitkeep` (so the dir tracks even if its single file is the only content).

---

### `scripts/audit_bybit_bypass.py` (BC-01 — NEW Wave 0 audit script)

**Analog (shape):** `tests/integration/test_preflight_grep_gates.py:50-95` (the dual-form rglob + regex scan).

**Differences from the analog:**
- Outputs `bybit-bypass-audit.json` to `.planning/evidence/BC-01/` (artifact, not pass/fail).
- JSON schema per CONTEXT BC-01: `[{file, line, kind, current_call, replacement_path}]` where `kind ∈ {pybit_import, mainnet_rest_url, testnet_rest_url, wss_stream_url}`.
- Scope is repo-wide `.py` files; same EXEMPT set as BC-03 grep gate.

**Pattern excerpt to copy (rglob + regex scan, `test_preflight_grep_gates.py:65-75` — adapt for script form):**
```python
pattern = re.compile(r"YOUR_PATTERN_HERE")
matches: list[str] = []
for py in TE_APP.rglob("*.py"):
    if "/tests/" in py.as_posix():
        continue
    try:
        text = py.read_text(errors="ignore")
    except OSError:
        continue
    if pattern.search(text):
        matches.append(str(py.relative_to(TE_APP)))
```

**EXEMPT_PATHS to copy verbatim into both the audit script AND the BC-03 grep gate test:**
```python
EXEMPT_PATHS = {
    REPO_ROOT / "services" / "bybit-connector",                              # D-05: connector itself
    REPO_ROOT / "scripts" / "tape",                                          # gate exception (RESEARCH §scripts/tape/capture_bybit.py)
    REPO_ROOT / "_archive_exchanges",                                        # post-BC-04 archive (D-02)
    REPO_ROOT / "services" / "ml-prediction-service" / "models" / "_archive_lstm",  # existing archive (NOTE: full nested path, not bare _archive_lstm)
}
# Also exclude __pycache__ entries
```

---

### `tests/ci/test_no_bybit_bypass.py` (BC-03 — NEW grep gate)

**Analog (verbatim idiom):** `tests/integration/test_preflight_grep_gates.py:50-95` (Phase 8 PREFLIGHT-02) + `services/tournament-harness/tests/integration/test_tourn07_grep_gate.py:23-65` (Phase 3 TOURN-07).

**TDD discipline:** RED-first. **Write the gate; it must be RED on `main` *now* (because bypass sites still exist). The gate GOES GREEN only when BC-02 completes.** This is the natural TDD ordering for BC-03.

**Banned patterns** (per CONTEXT D-05):
```python
BANNED_PATTERNS = {
    "pybit_import":      re.compile(r"^\s*(from\s+pybit\b|import\s+pybit\b)", re.MULTILINE),
    "mainnet_rest_url":  re.compile(r"https?://api\.bybit\.com"),
    "testnet_rest_url":  re.compile(r"https?://api-testnet\.bybit\.com"),
    "wss_stream_url":    re.compile(r"wss?://stream(?:-testnet)?\.bybit"),
}
```

**Dual-form scan pattern** (copy from `test_preflight_grep_gates.py` lines 65-95 — pathlib rglob *and* subprocess grep). RESEARCH §"Pattern 5" already shows the full ~70-line file.

**Pitfall 4 in RESEARCH:** if any in-repo docstring uses the literal `api.bybit.com`, gate fires false-positive. Simplest fix: rewrite the docstring to say "the Bybit REST API" (no URL literal). The gate is intentionally simple-grep; AST scanning is heavier and brittle.

---

### `tests/ci/__init__.py` (NEW — empty file)

One-line file: `"""Phase 13: CI-only test gates (BC-03)."""` or empty. Needed because `tests/ci/` does not currently exist. Follow `services/tournament-harness/tests/__init__.py` pattern (single docstring line). Without the `__init__.py`, pytest collection on the new directory is path-dependent.

---

### `tests/integration/test_bybit_connector_tape_preserved.py` (BC-07 — NEW)

**Analog:** `services/bybit-connector/app/tape_replay_client.py:200-218` (the stub shapes) + RESEARCH "Pattern 1".

**TDD discipline:** RED-first — write the test asserting refactored orderbook handler does not crash on `{"a": [], "b": [], "ts": 0, "u": 0}` BEFORE editing the handler. Test goes GREEN once handler's `result.get("a", [])` / `result.get("b", [])` returns empty lists without raising.

**Tape stub shapes to assert against (`tape_replay_client.py:206-218` — VERBATIM):**
```python
async def get_orderbook(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
    return {"a": [], "b": [], "ts": 0, "u": 0}
async def get_recent_trades(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
    return {"list": []}
async def get_funding_rate_history(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
    return {"list": []}
async def get_instruments_info(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
    return {"list": []}
```

**Option A vs B (RESEARCH §"Tape-Mode Coverage Gap" / Open Q #3):** Planner decides. Default Option A — assert shape, accept empty.

---

### `tests/integration/test_scripts_fail_fast.py` (BC-02 D-04 contract — NEW)

**Analog:** RESEARCH §"Pattern 2" fail-fast scaffold (no direct in-repo precedent for "script exits 2 with operator-readable error when env unreachable" — closest is subprocess invocation pattern from `test_tourn07_grep_gate.py:51-64`).

**Test shape (no analog file — sketch only):**
```python
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

def test_collect_180_days_data_fails_fast_when_connector_unreachable():
    """BC-02/D-04: scripts must exit 2 with operator-readable error when bybit-connector down."""
    env = {"BYBIT_CONNECTOR_URL": "http://localhost:65535"}  # unreachable port
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "collect_180_days_data.py"), "--help"],
        capture_output=True, text=True, env=env, timeout=15,
    )
    assert result.returncode == 2, (
        f"Expected exit 2 (D-04 fail-fast), got {result.returncode}.\n"
        f"stderr: {result.stderr[:500]}"
    )
    assert "docker compose" in result.stderr, "Error must point operator at compose up command"
```

(Repeat per refactored script. Planner may parametrize over the script list.)

---

### Per-consumer respx unit tests (BC-02 RED-first)

**Analog (exact, verbatim — this is the template):** `services/trading-engine/tests/test_instruments_cache.py:29-150`.

```python
# services/trading-engine/tests/test_instruments_cache.py:29-149 — VERBATIM key excerpts
CONNECTOR_URL = "http://bybit-connector:8001"

@pytest.mark.asyncio
@respx.mock
async def test_refresh_populates_cache():
    cache = InstrumentsCache(connector_url=CONNECTOR_URL)
    route = respx.get(f"{CONNECTOR_URL}/api/v1/market/instruments-info").mock(
        return_value=httpx.Response(200, json=_payload([_btc_item(), _eth_item()]))
    )
    await cache.refresh(["BTCUSDT", "ETHUSDT"])
    assert route.called
    btc = await cache.get("BTCUSDT")
    eth = await cache.get("ETHUSDT")
    assert btc is not None and btc.min_order_qty == Decimal("0.001")
```

**Key idioms to copy:**
- `@pytest.mark.asyncio` + `@respx.mock` decorator stack.
- `respx.get(URL).mock(return_value=httpx.Response(200, json=...))` — assert `route.called` after.
- `route.calls.last.request.url.params["symbol"]` for assert-called-with-correct-params (see RESEARCH §"respx mock for unit test" example).
- Wrapper-shape JSON helper `_payload(items)` returning `{"success": True, "data": items}` — copy this exact helper into ml-prediction tests.

**Second `respx` reference for the patterns:** `services/notification-service/tests/test_slack_client.py:11-32` — for asserting **request headers** and **request body shape** in addition to URL/params.

---

### `.github/workflows/bybit-bypass-gate.yml` OR extend `.github/workflows/ci.yml`

**Planner picks one of two in-repo precedents:**

**Pattern A — standalone workflow.** Analog: `.github/workflows/tournament-harness.yml:24-41` (TOURN-07 grep gate is its own top-level job in the harness workflow). For BC-03 this would mean a new `bybit-bypass-gate.yml` with one job that runs `pytest tests/ci/test_no_bybit_bypass.py -v`. Pros: isolated, fast, easy to read in PR check list.

```yaml
# Source: .github/workflows/tournament-harness.yml:24-41 — VERBATIM
jobs:
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

**Pattern B — extend existing workflow.** Analog: `.github/workflows/preflight-live-readiness.yml:41-43` (Phase 8 PREFLIGHT runs grep-gate pytest files as a *step* inside the unit-tests job, not a separate job).

```yaml
# Source: .github/workflows/preflight-live-readiness.yml:41-43 — VERBATIM
- name: Grep gates
  working-directory: services/trading-engine
  run: pytest ../../tests/integration/test_preflight_grep_gates.py ../../tests/integration/test_mlgate_grep_gates.py ../../tests/integration/test_mlgate_reason_grep_gate.py -v
```

For BC-03 this would mean adding `pytest tests/ci/test_no_bybit_bypass.py -v` as a step inside an existing CI job (e.g., `ci.yml`'s `code-quality` job or its test job). Pros: no new workflow file; consolidated CI list.

**Recommendation:** Planner picks based on whether `bybit-bypass-gate.yml` warrants standalone PR check (yes if operator wants the gate visible/required separately; no if happy folding into the master CI run).

---

### `RUNBOOK.md` (BC-06 — append new symptom)

**Analog:** `RUNBOOK.md:22-105` (existing 6 symptoms — all follow the same `## Symptom: ...` / `**Diagnose:**` / `**Action:**` / `**Verification:**` triad). The most directly analogous one to copy structure from is `RUNBOOK.md:88-105` "Stale in-memory ML model after retrain" — three terse subsections with concrete CLI commands.

**Pattern to copy (RUNBOOK.md:88-105 — VERBATIM structure, replace content):**
```markdown
## Symptom: Stale in-memory ML model after retrain

`ml-retraining-service` ran a successful retrain (new model file present in `models/`), but `ml-prediction-service` continues to return predictions matching the pre-retrain model. The service has not picked up the new artifact.

**Diagnose:**
- `docker logs ml-prediction-service | grep -i "model loaded"` — last line shows the OLD model file path (not the just-retrained one).
- `ls -la models/<symbol>/` on the host — newest file is more recent than the timestamp in the `model loaded` log line.
- `curl http://localhost:8007/api/v1/predictions/SOLUSDT` — returns predictions identical to pre-retrain values (compare against a saved sample).

**Action:**
```bash
docker compose -f docker-compose.unified.yml restart ml-prediction-service
```

**Verification:**
- `docker logs ml-prediction-service --tail 20 | grep -i "model loaded"` — shows the new model file path / mtime matching the retrain output.
...
```

**BC-06 symptom must cover the 4 sub-causes** (per BC-06 requirement):
(a) bybit-connector container down
(b) `BYBIT_CONNECTOR_URL` env misconfigured (host vs compose — see Pitfall 1)
(c) bybit-connector hitting Bybit-side ratelimit
(d) `MARKET_DATA_SOURCE=tape` accidentally enabled in production

**Concrete verification command** (BC-06 explicit requirement): `curl http://bybit-connector:8001/api/v1/market/ticker?symbol=BTCUSDT`.

**Also update the Index** at `RUNBOOK.md:9-19` to add a new bullet pointing at the new anchor.

---

### `.planning/codebase/INTEGRATIONS.md:231` (D-10 one-line edit)

**Before:** `| Out | wss://stream.bybit.com/* | bybit-connector, market-data |`
**After:** `| Out | wss://stream.bybit.com/* | bybit-connector |`

(Confirmed in RESEARCH §"Phase-Close Cleanup".)

---

### `.planning/evidence/BC-01/.gitkeep` (NEW — directory marker)

**Analog:** any directory inside `.planning/evidence/` (e.g., `CIRESTORE-02/`, `OP-04/`, `forward_paper_test/` — all exist but contain files; convention is "dir tracked when it has content"). For BC-01 the dir will be populated by the audit script run, so `.gitkeep` may be unnecessary if the JSON artifact is committed in the same step. Planner may skip `.gitkeep` and rely on the audit-output commit.

---

## Shared Patterns

### Shared 1 — httpx + retry decorator (applies to: all BC-02 consumers)

**Source:** `services/market-data-service/app/circuit_breaker.py:5-25`. Excerpt VERBATIM:
```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import httpx
import logging

logger = logging.getLogger(__name__)

bybit_connector_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    before_sleep=lambda retry_state: logger.warning(
        f"Retrying Bybit Connector call (attempt {retry_state.attempt_number})"
    ),
)
```

**Apply to:** every refactored consumer that calls bybit-connector REST.

**Open question for planner (RESEARCH Open Q #5):** shared `BybitConnectorClient` in `shared/` (relocate decorator + httpx client) vs inline-per-consumer. RESEARCH recommends shared; CONTEXT is silent. **PATTERNS.md surfaces the analog excerpt; planner picks the shape.**

### Shared 2 — wrapper-shape response parsing (applies to: all BC-02 consumers)

**Source:** `services/market-data-service/app/fetcher.py:159-201` (kline) and `:219-246` (ticker).
```python
response = await self.client.get("/api/v1/market/kline", params=params)
response.raise_for_status()
data = response.json()
if data.get("success"):
    raw_data = data.get("data", [])
    # ... process
else:
    logger.error(f"Failed to fetch klines: {data}")
    return []
```

**Apply to:** every refactored consumer. Pitfall 2 in RESEARCH catches the mechanical-refactor regression where the Bybit `retCode` parser survives.

### Shared 3 — respx unit test scaffold (applies to: every BC-02 consumer's unit test)

**Source:** `services/trading-engine/tests/test_instruments_cache.py:29-149`. Already excerpted above under "Per-consumer respx unit tests."

### Shared 4 — dual-form grep scan (applies to: BC-01 audit script + BC-03 grep gate)

**Source:** `tests/integration/test_preflight_grep_gates.py:50-95` (pathlib rglob + subprocess grep, both must agree). Already excerpted above under "BC-03 grep gate."

### Shared 5 — conventional commit prefixes (applies to: every task)

Per CLAUDE.md "Commits: conventional (`feat(service): ...`, `fix(service): ...`)". Suggested per-BC prefixes from RESEARCH §"Project Constraints":
- `refactor(<svc>): centralize via bybit-connector for <consumer>` — BC-02 per-consumer commits
- `feat(ci): add tests/ci/test_no_bybit_bypass.py grep gate` — BC-03
- `chore(exchanges): archive Binance adapter per operator policy` — BC-04
- `fix(market-data): correct bybit_connector_url default port` — BC-05
- `docs(runbook): add bybit-connector chain symptom` — BC-06
- `test(integration): assert tape mode preserved across refactored consumers` — BC-07

---

## No Analog Found

| File | Role | Data Flow | Reason | Suggested Fallback |
|------|------|-----------|--------|--------------------|
| `tests/integration/test_scripts_fail_fast.py` | integration test | subprocess invocation + env override | No in-repo test currently asserts "script exits N with operator-readable error when env unreachable." Closest shape is `test_tourn07_grep_gate.py:51-64` subprocess pattern, but it asserts grep output rather than exit code + stderr substring. | Build from scratch using RESEARCH §"Pattern 2" fail-fast scaffold + the subprocess + assert exit code idiom; sketch provided above. |
| `.planning/evidence/BC-01/bybit-bypass-audit.json` | data artifact | n/a — script-emitted JSON | New schema (defined in CONTEXT BC-01: `[{file, line, kind, current_call, replacement_path}]`); not produced by any existing audit tool in repo. | Hand-roll inside `scripts/audit_bybit_bypass.py`. Schema is specified; no analog needed. |

---

## Metadata

**Analog search scope:**
- `services/market-data-service/app/{fetcher.py, circuit_breaker.py, config.py}`
- `services/market-data-service/tests/{test_config.py, test_fetcher.py, test_pagination_fix.py}`
- `services/bybit-connector/app/{tape_replay_client.py, main.py}`
- `services/ml-prediction-service/{app/handlers/orderbook.py, download_*.py}`
- `services/trading-engine/{app/exchanges/{factory,base,binance,__init__}.py, tests/test_multi_exchange.py, tests/test_instruments_cache.py}`
- `services/notification-service/tests/test_slack_client.py`
- `services/tournament-harness/tests/integration/test_tourn07_grep_gate.py`
- `tests/integration/test_preflight_grep_gates.py`
- `scripts/{collect_180_days_data.py, tape/capture_bybit.py}`
- `backtesting/bybit_data_fetcher.py`
- `infrastructure/scripts/rotate_secrets.py`
- `RUNBOOK.md`
- `.github/workflows/{tournament-harness.yml, preflight-live-readiness.yml, ci.yml}`
- `.planning/evidence/` (directory convention check)

**Files scanned (Read tool):** 21
**Pattern extraction date:** 2026-05-21
**Cross-references:** RESEARCH.md §§ "Architectural Responsibility Map", "Standard Stack", "Architecture Patterns (1-5)", "Endpoint Mapping", "Tape-Mode Coverage Gap", "Common Pitfalls", "Code Examples", "Open Questions", "Project Constraints"

**Open questions the planner inherits (cross-ref RESEARCH §"Open Questions"):**
1. Kraken/Coinbase: archive alongside Binance? (Open Q #1)
2. rotate_secrets Option A (restart) vs B (new endpoint)? (Open Q #2)
3. BC-07 Option A (empty stubs) vs B (orderbook fixtures)? (Open Q #3)
4. Delete `test_pagination_fix.py`? Verify `test_fetcher.py` coverage. (Open Q #4 — note test_fetcher.py also wholesale-skipped)
5. Shared `BybitConnectorClient` vs inline httpx per consumer? (Open Q #5)
6. aiohttp→httpx universal vs per-script judgement? (Open Q #6)
7. `scripts/test_public_bybit_api.py` referenced anywhere? (Open Q #7)

PATTERNS.md does not resolve any of these — it surfaces analog excerpts both branches of each question would use. Resolution belongs to plan-phase.
