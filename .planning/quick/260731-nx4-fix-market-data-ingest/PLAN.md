---
id: 260731-nx4
slug: fix-market-data-ingest
date: 2026-07-31
status: complete-verified-uncommitted
---

# Fix dead market-data ingest (audit DL-1)

## Symptom

Zero rows written to `tickers` or `klines` since 2026-07-30 22:10, across a
stack restart at 2026-07-31 14:26. The service kept serving reads with `200 OK`
and a green `/health` the entire time, so every indicator, signal, and position
mark in the trading engine ran on ~17-hour-old candles.

## Root cause — two compounding defects

### A. Every scheduled run is silently discarded (CRITICAL, the actual blocker)

`services/market-data-service/app/scheduler.py:216-245` registers all three jobs
with **no `misfire_grace_time`**. APScheduler's default is **1 second**. The
service serves heavy kline read traffic from technical-analysis, so each fire
slips past its deadline and APScheduler drops the run instead of executing it:

```
Run time of job "Ticker Data Collection ..." was missed by 0:00:16.899979
Run time of job "Kline Data Collection ..."  was missed by 0:00:02.107381
Run time of job "Hourly Full Data Collection ..." was missed by 0:00:14.086112
```

Every fire, forever. `/api/v1/scheduler/status` still reports
`"running": true` with three healthy jobs and future `next_run` times, which is
why this was invisible.

### B. Two schedulers, one per uvicorn worker (MEDIUM)

```
$ docker inspect crypto-bot-market-data --format '{{.Config.Cmd}}'
[python -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --workers 2]
```

`--workers 2` forks two processes; each runs `start_scheduler()` in its own
lifespan, so every job is registered twice (confirmed: paired log lines with
distinct `taskName`, and 6 "Scheduler started successfully" lines across 3
boots). The `if _scheduler is not None` guard at `scheduler.py:206` is
per-process and cannot see the sibling.

Not corrupting — `repository.py:71` uses `on_conflict_do_update` for klines —
but it doubles Bybit API load and duplicates ticker rows, and it worsens the
event-loop contention that triggers defect A.

## Proof the collection code itself is fine

```
$ curl -X POST http://localhost:8002/api/v1/collect/ticker/BTCUSDT
{"success":true,"message":"Ticker data saved","data":{"symbol":"BTCUSDT","last_price":"62848.40",...}}

market_data=# SELECT symbol, last_price, to_timestamp(created_at/1000) FROM tickers ORDER BY created_at DESC LIMIT 2;
 BTCUSDT | 62848.40000000 | 2026-07-31 16:11:55+00
 POLUSDT |     0.07125000 | 2026-07-30 22:10:27+00
```

Purely a scheduling failure. Note the live price **62,848.40** against the
**64,706.6** the trading engine was marking BTC positions at — a ~2.9%
divergence on a live book.

## Changes

1. `scheduler.py` — add `misfire_grace_time` and `coalesce=True` to all three
   jobs. Grace generous relative to interval (5-min jobs tolerate 4 min; the
   hourly backup tolerates 30 min) so a busy loop delays a run instead of
   cancelling it. `coalesce=True` collapses a backlog into one run rather than
   firing N catch-ups.
2. `scheduler.py` — elect a single scheduler owner with an `fcntl` lock so the
   jobs run in exactly one process regardless of worker count. Chosen over
   dropping to `--workers 1` because this service is read-heavy and the extra
   worker is carrying real traffic.
3. Log loudly when a process declines ownership, so "no scheduler here" is never
   silent again.

## Out of scope

- The staleness guard on `/health` (recommended in the audit as §6.3 item 1)
  is a separate behavioral change to the health contract — filed, not done here.
- Trading-engine restart. Not required by this change.

## Verification

- `pytest services/market-data-service/tests/` — capture baseline first.
- Rebuild + restart **market-data-service only**; the trading engine must not be
  restarted (audit T-8/T-9/DL-2: a restart corrupts the paper book).
- Confirm `SELECT max(created_at) FROM tickers` advances within 5 minutes.
- Confirm exactly one "Scheduler started" per boot in the logs.
