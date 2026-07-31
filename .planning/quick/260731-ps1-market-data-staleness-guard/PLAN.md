---
id: 260731-ps1
slug: market-data-staleness-guard
date: 2026-07-31
status: in-progress
---

# Market-data staleness guard (audit DL-1 follow-up)

## Why this exists

`66779e2` fixed *why* ingest stopped. It did nothing about *why nobody noticed
for 17 hours*. The service served 17-hour-old prices as current, with
`"source": "database"`, HTTP 200, and a green `/health`, while the trading
engine marked live positions against them (BTC 64,706.6 stored vs 62,848.40
actual — a 2.9% error on an open book).

Fixing the scheduler fixes one instance. This fixes the class.

## The deeper bug: a stale row blocks its own repair

`handlers/query.py:146-161`:

```python
ticker = await TickerRepository.get_latest_ticker(symbol)
if not ticker:
    ticker_data = await fetcher.get_ticker(symbol)   # live fallback
    ...
return {"data": ticker.to_dict(), "source": "database"}
```

The live-fetch fallback fires **only when there is no row at all**. Any row —
however old — short-circuits it. So the stale row is a poison pill: it is both
the wrong answer and the reason the right answer is never fetched. Had age been
checked, the 17-hour outage would have self-healed on the very first read.

## Changes

1. **Treat a stale row as a cache miss** (`handlers/query.py`). If the newest
   row is older than the freshness budget, fall through to the live fetch and
   persist the result, exactly as for a missing row. Self-healing.
2. **Never serve an age you did not disclose.** Add `age_seconds` and
   `is_stale` to ticker responses, and log at WARNING when a stale value is
   served anyway (live fetch also failed — better a disclosed stale price than
   a 500, but it must be loud).
3. **`/ready` reports data freshness**, returning 503 when ingest has stalled.

## Why `/ready` and NOT `/health`

`docker-compose.unified.yml:459` wires the container healthcheck to `/health`,
and `:552-554` makes **trading-engine `depends_on: market-data:
service_healthy`** (ml-prediction too, at `:757`). Failing `/health` on stale
data would stop the trading engine from *booting* — the wrong failure mode
entirely. Stale data should make the engine refuse to *trade*, not refuse to
start, and a service whose process is alive is by definition live.

So `/health` stays liveness. `/ready` becomes readiness — nothing in the compose
files consumes `/ready`, so this carries no boot-ordering blast radius while
still giving Prometheus and any operator a real signal.

## Freshness budget

Ticker collection runs every 5 minutes. Three missed cycles is unambiguous
failure, not jitter, so the default budget is **900 s**, configurable via
`MARKET_DATA_STALENESS_SECONDS`.

## Out of scope

- Making the trading engine *refuse to trade* on stale prices. That is the
  consumer-side half and belongs in trading-engine; it also interacts with the
  open-position marking path. Filed, not done here.
- Klines. Same defect shape, but the kline read path has a different cache
  contract; keeping this change reviewable.

## Verification

- Baseline `pytest services/market-data-service/tests` is 9 failed / 186 passed
  / 278 skipped. Must not regress.
- Unit tests: fresh row served normally; stale row triggers live fetch; stale
  row with a failing fetcher is served but flagged and logged; `/ready` 503s
  when the newest row exceeds the budget.
- Live: confirm `/ready` is 200 with ingest healthy, and that a normal ticker
  read reports a small `age_seconds`.
