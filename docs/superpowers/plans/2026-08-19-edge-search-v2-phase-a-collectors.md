# Edge-Search v2 Phase A — Orderbook + OI Collectors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** market-data-service persists Bybit orderbook snapshots (5s, top-25) and open interest (5min) for the 5 validated symbols into TimescaleDB, gap-checked and four-proof verified.

**Architecture:** Mirror the existing ticker/kline collection pattern exactly: `fetcher.py` method (HTTP → bybit-connector) → `repository.py` insert → `scheduler.py` APScheduler job under the existing ownership claim. OI additionally needs one new REST passthrough in bybit-connector. Retention via boot DDL in `database.py` (the established atomic-DDL pattern).

**Tech Stack:** Python 3.12, FastAPI services, APScheduler, SQLAlchemy async, TimescaleDB, httpx.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-19-edge-search-v2-design.md` (§2). Cadence: orderbook **5 seconds**, depth **25**; OI **5 minutes**. Symbols: the service's configured trading pairs.
- Retention: orderbook **90 days**; OI **730 days**.
- Jobs use `max_instances=1, coalesce=True` (skip-not-queue, spec §2 A1) and register inside `start_scheduler()` under the existing ownership claim (spec §9.4).
- market-data-service tests run on host: `cd services/market-data-service && python3 -m pytest tests/ --no-cov` (always `--no-cov`).
- Never `import shared.account` in `services/*/app/**` (containers). No account-size literals anywhere.
- Deploy per service: `docker compose -f docker-compose.unified.yml up -d --build market-data-service bybit-connector` (WSL: prefix `DOCKER_BUILDKIT=0` if build hangs). **Restart before any integration claim.**
- Timestamps stored as epoch **milliseconds** BigInteger (matches existing `orderbook_snapshots.timestamp` and klines convention).
- Bybit v5 endpoints via connector: orderbook `/v5/market/orderbook` (exists, `bybit_rest_client.py:620`); open interest `/v5/market/open-interest` (new).

---

### Task 1: Orderbook fetcher method + repository

**Files:**
- Modify: `services/market-data-service/app/fetcher.py` (add method after `get_ticker`, ~line 270)
- Modify: `services/market-data-service/app/repository.py` (new `OrderbookRepository`)
- Test: `services/market-data-service/tests/test_orderbook_collection.py` (new)

**Interfaces:**
- Consumes: existing `BybitDataFetcher` (httpx client at `self.client`, connector base URL), existing `OrderbookSnapshot` model (`models.py:145`: `timestamp` BigInteger ms, `symbol` String, `snapshot_data` String JSON, `created_at` BigInteger).
- Produces: `BybitDataFetcher.get_orderbook(symbol: str, limit: int = 25) -> Optional[Dict[str, Any]]` returning `{"symbol", "timestamp_ms", "bids", "asks"}` (bids/asks: list of `[price_str, size_str]`); `OrderbookRepository.save_snapshot(snapshot: dict) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for orderbook snapshot collection (edge-search v2 phase A1)."""

import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.fetcher import BybitDataFetcher
from app.repository import OrderbookRepository

CONNECTOR_PAYLOAD = {
    "success": True,
    "data": {
        "s": "BTCUSDT",
        "ts": 1755600000000,
        "b": [["118000.5", "1.25"], ["118000.0", "0.5"]],
        "a": [["118001.0", "0.8"], ["118001.5", "2.0"]],
    },
}


@pytest.mark.asyncio
async def test_get_orderbook_normalizes_connector_payload():
    fetcher = BybitDataFetcher()
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json = lambda: CONNECTOR_PAYLOAD
    with patch.object(fetcher.client, "get", return_value=mock_resp) as g:
        ob = await fetcher.get_orderbook("BTCUSDT")
    await fetcher.close()
    assert g.call_args.kwargs["params"]["limit"] == 25
    assert ob["symbol"] == "BTCUSDT"
    assert ob["timestamp_ms"] == 1755600000000
    assert ob["bids"][0] == ["118000.5", "1.25"]
    assert len(ob["asks"]) == 2


@pytest.mark.asyncio
async def test_get_orderbook_returns_none_on_error():
    fetcher = BybitDataFetcher()
    with patch.object(fetcher.client, "get", side_effect=Exception("boom")):
        assert await fetcher.get_orderbook("BTCUSDT") is None
    await fetcher.close()


@pytest.mark.asyncio
async def test_save_snapshot_writes_row(db_session_or_mock):
    # Follow the persistence-test convention already used in this suite for
    # TickerRepository.save_ticker (see tests/test_database.py) — session
    # mocked the same way; assert the ORM object handed to session.add.
    repo = OrderbookRepository()
    snap = {
        "symbol": "BTCUSDT",
        "timestamp_ms": 1755600000000,
        "bids": [["118000.5", "1.25"]],
        "asks": [["118001.0", "0.8"]],
    }
    ok = await repo.save_snapshot(snap)
    assert ok is True
```

(Adapt the third test's fixture to the repo's existing DB-test convention in `tests/test_database.py` — reuse its session fixture/mocking style verbatim rather than inventing a new one. The assertion that matters: a row object with `symbol="BTCUSDT"`, `timestamp=1755600000000`, and `snapshot_data` containing both ladders reaches `session.add`.)

- [ ] **Step 2: Run tests, verify failure**

Run: `cd services/market-data-service && python3 -m pytest tests/test_orderbook_collection.py -v --no-cov`
Expected: FAIL — `AttributeError: 'BybitDataFetcher' object has no attribute 'get_orderbook'`.

- [ ] **Step 3: Implement fetcher method**

Add to `BybitDataFetcher` (mirror `get_ticker`'s shape, including the error-swallow-and-None convention):

```python
    async def get_orderbook(
        self, symbol: str, limit: int = 25
    ) -> Optional[Dict[str, Any]]:
        """Fetch top-of-book depth via bybit-connector /api/v1/market/orderbook."""
        params = {"category": "linear", "symbol": symbol, "limit": limit}
        try:
            response = await self.client.get(
                "/api/v1/market/orderbook", params=params
            )
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                ob = data.get("data", {})
                if ob.get("b") is not None and ob.get("a") is not None:
                    return {
                        "symbol": ob.get("s", symbol),
                        "timestamp_ms": int(ob.get("ts", 0)),
                        "bids": ob.get("b", []),
                        "asks": ob.get("a", []),
                    }
            logger.warning(f"No orderbook data for {symbol}")
            return None
        except Exception as e:
            logger.error(f"Error fetching orderbook for {symbol}: {e}")
            return None
```

First verify the connector route path: `grep -n "orderbook" services/bybit-connector/app/main.py`. If the connector exposes a different path than `/api/v1/market/orderbook`, use the real one and note it in the commit message. If the connector has NO orderbook HTTP route (only the client method at `bybit_rest_client.py:620`), add one to `services/bybit-connector/app/main.py` mirroring its ticker route: handler calls `client.get_orderbook(category, symbol, limit)` and returns the standard `{"success": True, "data": ...}` envelope — include that file in this task's tests-and-commit.

- [ ] **Step 4: Implement repository**

Add to `repository.py` (mirror `TickerRepository` structure and its session-handling style exactly):

```python
class OrderbookRepository:
    """Insert-only persistence for orderbook_snapshots."""

    @staticmethod
    async def save_snapshot(snapshot: dict) -> bool:
        try:
            async with get_session() as session:  # same helper TickerRepository uses
                row = OrderbookSnapshot(
                    timestamp=int(snapshot["timestamp_ms"]),
                    symbol=snapshot["symbol"],
                    snapshot_data=json.dumps(
                        {"bids": snapshot["bids"], "asks": snapshot["asks"]},
                        separators=(",", ":"),
                    ),
                    created_at=int(time.time() * 1000),
                )
                session.add(row)
                await session.commit()
                return True
        except Exception as e:
            logger.error(f"Error saving orderbook snapshot: {e}")
            return False
```

(Use whatever session acquisition `TickerRepository.save_ticker` at `repository.py:206` actually uses — copy that pattern, do not invent. Import `OrderbookSnapshot` from `app.models`, plus `json`, `time`.)

- [ ] **Step 5: Run tests, verify pass**

Run: `cd services/market-data-service && python3 -m pytest tests/test_orderbook_collection.py -v --no-cov`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add services/market-data-service/app/fetcher.py services/market-data-service/app/repository.py services/market-data-service/tests/test_orderbook_collection.py
git commit -m "feat(market-data): orderbook fetcher + repository (edge-search v2 A1)" -- services/market-data-service/app/fetcher.py services/market-data-service/app/repository.py services/market-data-service/tests/test_orderbook_collection.py services/bybit-connector/app/main.py
```

(Drop the connector path from the pathspec if it was untouched.)

---

### Task 2: Orderbook scheduler job + retention DDL

**Files:**
- Modify: `services/market-data-service/app/scheduler.py` (new job + registration in `start_scheduler()`, after the kline job block ~line 313)
- Modify: `services/market-data-service/app/database.py` (append one DDL entry to `DDL_STATEMENTS`)
- Test: `services/market-data-service/tests/test_orderbook_collection.py` (extend)

**Interfaces:**
- Consumes: `BybitDataFetcher.get_orderbook(symbol, limit=25)`, `OrderbookRepository.save_snapshot(dict)` from Task 1; `_trading_pairs()`, `_scheduler`, `IntervalTrigger`, `_INTERVAL_JOB_GRACE_SECONDS` from `scheduler.py`.
- Produces: `collect_orderbook_data() -> None` coroutine; APScheduler job id `orderbook_collection` (5s interval).

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_collect_orderbook_data_fetches_and_saves_all_pairs():
    from app import scheduler as sched

    fake_ob = {"symbol": "X", "timestamp_ms": 1, "bids": [], "asks": []}
    with (
        patch.object(sched, "_trading_pairs", return_value=["BTCUSDT", "ETHUSDT"]),
        patch("app.scheduler.BybitDataFetcher") as F,
        patch("app.scheduler.OrderbookRepository") as R,
    ):
        F.return_value.get_orderbook = AsyncMock(return_value=fake_ob)
        F.return_value.close = AsyncMock()
        R.return_value.save_snapshot = AsyncMock(return_value=True)
        await sched.collect_orderbook_data()
    assert F.return_value.get_orderbook.await_count == 2
    assert R.return_value.save_snapshot.await_count == 2
    F.return_value.close.assert_awaited()  # pool leak guard, same as ticker job
```

- [ ] **Step 2: Run, verify failure** — `AttributeError: module 'app.scheduler' has no attribute 'collect_orderbook_data'`.

- [ ] **Step 3: Implement the job**

Mirror `collect_ticker_data` exactly (including the `finally: await fetcher.close()` pool-leak guard, success/error counters, log style):

```python
async def collect_orderbook_data():
    """Scheduled job: top-25 orderbook snapshot per pair. Runs every 5 seconds.

    max_instances=1 + coalesce=True at registration make a slow tick SKIP
    the next rather than queue (spec A1 rate-limit rule).
    """
    fetcher = BybitDataFetcher()
    repo = OrderbookRepository()
    success_count = 0
    error_count = 0
    try:
        for symbol in _trading_pairs():
            try:
                snapshot = await fetcher.get_orderbook(symbol, limit=25)
                if snapshot and await repo.save_snapshot(snapshot):
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                logger.error(f"❌ Error collecting orderbook for {symbol}: {e}")
                error_count += 1
    finally:
        await fetcher.close()
    if error_count:
        logger.warning(
            f"📖 Orderbook collection: {success_count} ok, {error_count} errors"
        )
```

(No per-tick info log at 5s cadence — that is 17k log lines/day. Log warnings only; the gap-check script is the liveness monitor.)

Register inside `start_scheduler()` after the kline job:

```python
    # Job: orderbook snapshots every 5 seconds (edge-search v2 A1)
    _scheduler.add_job(
        collect_orderbook_data,
        trigger=IntervalTrigger(seconds=5),
        id="orderbook_collection",
        name="Orderbook Snapshot Collection",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=4,  # < interval: a missed tick is dropped, not queued
        coalesce=True,
    )
    logger.info("✅ Scheduled: Orderbook snapshots every 5 seconds")
```

- [ ] **Step 4: Add retention DDL**

Append to `DDL_STATEMENTS` in `database.py`, following the file's `(label, sql, level)` convention and its integer-time-dimension pattern (the `unix_now_ms` function already exists at entry 1; the hypertable conversion already exists at entry 4):

```python
    (
        "Retention policy (orderbook_snapshots, 90 days)",
        "SELECT add_retention_policy('public.orderbook_snapshots', "
        "drop_after => (90::bigint * 24 * 3600 * 1000), if_not_exists => TRUE)",
        "warning",
    ),
```

(`drop_after` is in the integer time dimension's unit — ms. `if_not_exists` makes boot idempotent. Level "warning" not "error": retention is not boot-critical.)

- [ ] **Step 5: Run all service tests**

Run: `cd services/market-data-service && python3 -m pytest tests/ --no-cov -q`
Expected: no new failures vs a pre-task baseline run (record both counts in the report).

- [ ] **Step 6: Commit**

```bash
git add services/market-data-service/app/scheduler.py services/market-data-service/app/database.py services/market-data-service/tests/test_orderbook_collection.py
git commit -m "feat(market-data): 5s orderbook snapshot job + 90d retention (edge-search v2 A1)" -- services/market-data-service/app/scheduler.py services/market-data-service/app/database.py services/market-data-service/tests/test_orderbook_collection.py
```

---

### Task 3: Open-interest end-to-end (connector method + route, model, repo, fetcher, job, DDL)

**Files:**
- Modify: `services/bybit-connector/app/bybit_rest_client.py` (new method after `get_orderbook`, ~line 640)
- Modify: `services/bybit-connector/app/main.py` (new route mirroring the orderbook/ticker route)
- Modify: `services/market-data-service/app/models.py` (new `OpenInterest` model)
- Modify: `services/market-data-service/app/fetcher.py`, `app/repository.py`, `app/scheduler.py`, `app/database.py`
- Test: `services/market-data-service/tests/test_open_interest_collection.py` (new)

**Interfaces:**
- Consumes: same patterns as Tasks 1–2.
- Produces: connector `get_open_interest(category: str, symbol: str, interval_time: str = "5min", limit: int = 200) -> Dict`; market-data `BybitDataFetcher.get_open_interest(symbol) -> Optional[List[Dict]]` (each: `{"symbol", "timestamp_ms", "open_interest"}`); `OpenInterestRepository.bulk_upsert(rows: List[dict]) -> int`; job `collect_open_interest_data()` (5min interval, id `open_interest_collection`).

- [ ] **Step 1: Connector method**

```python
    async def get_open_interest(
        self, category: str, symbol: str, interval_time: str = "5min", limit: int = 200
    ) -> Dict[str, Any]:
        """Open interest history. Public endpoint /v5/market/open-interest."""
        params = {
            "category": category,
            "symbol": symbol,
            "intervalTime": interval_time,
            "limit": limit,
        }
        return await self._request(
            "GET", "/v5/market/open-interest", params=params, auth_required=False
        )
```

Add the HTTP route in connector `main.py` mirroring its existing market routes (same envelope, same error handling): path `/api/v1/market/open-interest`, query params `symbol`, `interval_time`, `limit`.

- [ ] **Step 2: Model + boot DDL**

`models.py` (next to `OrderbookSnapshot`, same conventions — BigInteger ms timestamps, insert-only):

```python
class OpenInterest(Base):
    """Open-interest history (edge-search v2 A2). Insert-only; unique on
    (symbol, timestamp) so 5min polls of an overlapping window upsert clean."""
    __tablename__ = "open_interest"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(BigInteger, nullable=False)
    symbol = Column(String(20), nullable=False)
    open_interest = Column(Numeric(38, 8), nullable=False)
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("idx_oi_symbol_time", "symbol", "timestamp", unique=True),
        {"comment": "Open interest history"},
    )
```

`database.py` DDL entries (after the orderbook retention entry): hypertable conversion + 730d retention, following the existing atomic-DO-block pattern used for `orderbook_snapshots` at entry 4 (same runtime PK resolution, same `hypertable_schema='public'` guard), then:

```python
    (
        "Retention policy (open_interest, 730 days)",
        "SELECT add_retention_policy('public.open_interest', "
        "drop_after => (730::bigint * 24 * 3600 * 1000), if_not_exists => TRUE)",
        "warning",
    ),
```

- [ ] **Step 3: Fetcher + repository + job (write tests first, same style as Tasks 1–2)**

Tests (`test_open_interest_collection.py`): normalize-payload test (connector returns `{"list": [{"openInterest": "12345.5", "timestamp": "1755600000000"}], "symbol": ...}` shape — assert numeric conversion and ms int), error→None test, job fetch-and-upsert test with mocked fetcher/repo (mirror Task 2's test verbatim in structure).

Fetcher method returns the full page normalized; repository `bulk_upsert` follows `KlineRepository.bulk_upsert` (`repository.py:23`) — copy its ON CONFLICT style against the `(symbol, timestamp)` unique index. Job:

```python
async def collect_open_interest_data():
    """Scheduled job: OI history page per pair. Runs every 5 minutes.
    First run per symbol naturally backfills the endpoint's max window (spec A2)."""
    fetcher = BybitDataFetcher()
    repo = OpenInterestRepository()
    try:
        for symbol in _trading_pairs():
            try:
                rows = await fetcher.get_open_interest(symbol)
                if rows:
                    n = await repo.bulk_upsert(rows)
                    logger.info(f"📈 OI {symbol}: upserted {n} rows")
            except Exception as e:
                logger.error(f"❌ Error collecting OI for {symbol}: {e}")
    finally:
        await fetcher.close()
```

Registration: `IntervalTrigger(minutes=5, start_date="2024-01-01 00:03:00")` (offset from ticker/kline jobs), id `open_interest_collection`, `max_instances=1`, `misfire_grace_time=_INTERVAL_JOB_GRACE_SECONDS`, `coalesce=True`.

- [ ] **Step 4: Run tests**

`cd services/market-data-service && python3 -m pytest tests/test_open_interest_collection.py tests/ --no-cov -q` — new tests pass, no new failures elsewhere. Connector tests if present: run that service's suite too.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(market-data): open-interest collection end-to-end (edge-search v2 A2)" -- services/bybit-connector/app services/market-data-service/app services/market-data-service/tests/test_open_interest_collection.py
```

---

### Task 4: Deploy + gap-check script + four-proof verification

**Files:**
- Create: `scripts/check_collection_gaps.py`
- Evidence: `.planning/evidence/edge-search-v2/phase-a-verification.md` (new)

**Interfaces:**
- Consumes: live TimescaleDB (`docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data`), both new tables.
- Produces: re-runnable gap report; exit 1 when any gap breaches threshold.

- [ ] **Step 1: Deploy both services**

```bash
docker compose -f docker-compose.unified.yml up -d --build bybit-connector market-data-service
```

(WSL BuildKit hang → prefix `DOCKER_BUILDKIT=0`. Bind-mount PermissionError → `--force-recreate`.)

- [ ] **Step 2: Write the gap-check script**

```python
#!/usr/bin/env python3
"""Gap check for edge-search v2 collections (spec §2 verification #4).

Thresholds: orderbook inter-snapshot gap <= 60s; OI gap <= 15min, per symbol.
Runs psql inside the timescaledb container so it needs no host DB driver.
Exit 0 clean, 1 on any breach or empty table. Also prints table sizes
(spec §9.3 disk watch).
"""

import json
import subprocess
import sys

PSQL = [
    "docker", "exec", "crypto-bot-timescaledb",
    "psql", "-U", "cryptobot", "-d", "market_data", "-t", "-A", "-F", "|",
]

CHECKS = [
    ("orderbook_snapshots", 60_000),
    ("open_interest", 900_000),
]

def q(sql: str) -> list[list[str]]:
    out = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, check=True)
    return [line.split("|") for line in out.stdout.strip().splitlines() if line]

breaches = 0
for table, max_gap_ms in CHECKS:
    rows = q(
        f"SELECT symbol, count(*), min(timestamp), max(timestamp), "
        f"COALESCE(max(gap),0) FROM (SELECT symbol, timestamp, "
        f"timestamp - lag(timestamp) OVER (PARTITION BY symbol ORDER BY timestamp) "
        f"AS gap FROM {table}) g GROUP BY symbol ORDER BY symbol"
    )
    size = q(f"SELECT pg_size_pretty(pg_total_relation_size('{table}'))")[0][0]
    print(f"== {table} (size {size}, max gap allowed {max_gap_ms}ms)")
    if not rows:
        print("  EMPTY TABLE — breach")
        breaches += 1
        continue
    for symbol, n, tmin, tmax, maxgap in rows:
        ok = int(maxgap) <= max_gap_ms
        print(f"  {symbol}: rows={n} span={tmin}..{tmax} max_gap_ms={maxgap} {'OK' if ok else 'BREACH'}")
        breaches += 0 if ok else 1

print(f"RESULT: gap_breaches={breaches}")
sys.exit(1 if breaches else 0)
```

- [ ] **Step 3: Immediate verification (proofs 1–3)**

- Proof 1: `docker compose -f docker-compose.unified.yml logs market-data-service | grep -i "orderbook\|open.interest" | head` — job registration lines + live mainnet connector base URL visible.
- Proof 3: after ≥2 minutes, paste into the evidence file:
  `docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -c "SELECT symbol, count(*), to_timestamp(max(timestamp)/1000) FROM orderbook_snapshots GROUP BY symbol;"` and the same for `open_interest`. All 5 symbols must show rows.
- Proof 4: restart already happened via `--build` recreate — state the container start time (`docker inspect -f '{{.State.StartedAt}}' crypto-bot-market-data`) in the evidence file.
- (Proof 2, notification-received, is N/A for a collector — record "N/A: no notification path in scope" explicitly rather than silently skipping.)

- [ ] **Step 4: Run the gap check now (short-window smoke), then schedule the 48h check**

Run: `python3 scripts/check_collection_gaps.py` — expect OK rows (short span). The **48-hour** run is the real acceptance: record in the evidence file the command and a date 48h out; the executing human/agent re-runs it then and appends output. Task is complete when the smoke check passes and the evidence file documents the pending 48h step.

- [ ] **Step 5: Commit**

```bash
git add scripts/check_collection_gaps.py .planning/evidence/edge-search-v2/phase-a-verification.md
git commit -m "feat(edge-lab): collection gap-check script + phase A verification evidence" -- scripts/check_collection_gaps.py .planning/evidence/edge-search-v2/phase-a-verification.md
```

---

## Self-review notes

- Spec §2 A1 → Tasks 1–2; A2 → Task 3; A3 deferred (no task, per spec); §2 verification → Task 4. §9.4 ownership: jobs registered inside `start_scheduler()` after `_claim_scheduler_ownership()` — inherited automatically.
- Connector orderbook HTTP route existence is verified in Task 1 Step 3 with an explicit fallback instruction — not assumed.
- All repository/session/test conventions defer to named existing code (`TickerRepository.save_ticker:206`, `KlineRepository.bulk_upsert:23`, `tests/test_database.py`) rather than invented patterns.
