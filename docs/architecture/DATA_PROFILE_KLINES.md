# Data Profile: `klines` (TimescaleDB hypertable)

**Date:** 2026-05-02 · **Source of truth:** `services/market-data-service/app/models.py:14` · **Method:** Static profile from schema + documented gotchas. No live data sampled — sandbox can't reach the host's TimescaleDB. SQL pack at the bottom is paste-ready for `psql` against the running stack.

## Overview

- **Type:** TimescaleDB hypertable, partitioned on `timestamp` with **1-day chunks** (86 400 000 ms)
- **Grain:** one row per `(timestamp, symbol, interval)` triple — composite primary key
- **Retention policy:** 90 days (`add_retention_policy('klines', INTERVAL '90 days')`)
- **Continuous aggregate:** `klines_1h` defined in `CREATE_HYPERTABLE_SQL` but **never executed** by `create_hypertables()` — dead view per `wiki/modules/market-data-service.md:75`. Querying it errors. Either wire it into the bootstrap or stop referencing it.
- **Source-of-truth flag:** `is_mainnet` (BOOLEAN, NOT NULL, default TRUE) — added 2026-04-29 after the testnet/mainnet contamination audit
- **Indexes:** `(symbol, interval, timestamp)`, `(timestamp)`, `(is_mainnet)`

## Column details

| Column | Type | Nullable | Role | Notes |
|---|---|---|---|---|
| `timestamp` | `BIGINT` | NO | PK / temporal | Unix milliseconds. Hypertable partition key. Watch for ms-vs-s confusion in incoming Bybit responses. |
| `symbol` | `VARCHAR(20)` | NO | PK / dimension | Trading pair, e.g. `BTCUSDT`. Should match the 5 validated symbols (BTC, ETH, SOL, BNB, ADA) plus any operator additions. |
| `interval` | `VARCHAR(10)` | NO | PK / dimension | Bybit-format interval string: `1`, `5`, `15`, `60`, `240`, `D`. Not minutes — beware. |
| `open` | `NUMERIC(20,8)` | NO | metric | OHLCV open. |
| `high` | `NUMERIC(20,8)` | NO | metric | OHLCV high. Invariant: `high >= max(open, close)` and `high >= low`. |
| `low` | `NUMERIC(20,8)` | NO | metric | OHLCV low. Invariant: `low <= min(open, close)` and `low <= high`. |
| `close` | `NUMERIC(20,8)` | NO | metric | OHLCV close. |
| `volume` | `NUMERIC(20,8)` | NO | metric | Trade volume in base asset. |
| `turnover` | `NUMERIC(30,8)` | YES | metric | Quote-asset volume ≈ `volume * vwap`. Nullable because older rows lack it. |
| `is_mainnet` | `BOOLEAN` | NO (default TRUE) | dimension | **The headline column.** False = testnet contamination. Default TRUE means rows that existed *before* 2026-04-29 ALTER TABLE got marked mainnet whether they were or not — the migration can't tell apart pre-flip rows. |
| `created_at` | `BIGINT` | NO | temporal | Record-insertion ms. Useful for detecting backfill batches. |

Column-type breakdown: 3 PK / 6 metric / 1 dimension flag / 1 audit timestamp.

## Documented quality issues (from CLAUDE.md + wiki)

1. **🔴 Testnet/mainnet contamination through 2026-04-25.** Mid-day flip from `BYBIT_TESTNET=true` to `false` happened that day; rows from before the flip are testnet prices wearing real `BTCUSDT` symbol. The 2026-04-29 ALTER added `is_mainnet` with default TRUE — so pre-2026-04-29 rows are **all flagged mainnet whether or not they were**. CLAUDE.md says: "Wipe `klines` / `tickers` tables if running historical analysis; live forward-going data fine." Static-analysis confirms — the `is_mainnet` flag does not reliably partition contaminated history.
2. **🟡 `klines_1h` continuous aggregate is dead code.** `models.CREATE_HYPERTABLE_SQL` defines it but `create_hypertables()` in `database.py` never runs it. Anything that joins or queries `klines_1h` will throw `relation "klines_1h" does not exist`.
3. **🟡 Stale data risk.** Bot has been dormant since January 2026. Latest `created_at` will be ~Jan or whenever the market-data-service last ran. The 90-day retention policy may have purged older rows in the meantime — check before assuming history depth.
4. **🟡 Symbol drift.** Per `CLAUDE.md`: BTC + ETH were re-added to `default_symbols` only on 2026-05-03. Before that, market-data-service was only collecting SOL/BNB/ADA even though trading-engine's `trading_symbols` already had BTC/ETH. Expect under-representation of BTC/ETH for the dormant gap.
5. **🟢 `turnover` nullable.** Older rows may have NULL turnover. Aggregations that average turnover will silently exclude those rows — use `COALESCE(turnover, volume * close)` if you need a complete series.
6. **🟢 `interval` is a string, not a duration.** Bybit returns `'D'` for daily and `'60'` for 1-hour. Sorting `interval` lexically gives nonsense (`'1'` < `'15'` < `'5'`). Always cast or whitelist.

## Recommended explorations (rank-ordered)

1. **Confirm contamination scope.** Run the pack below. If pre-2026-04-25 rows exist with `is_mainnet=TRUE`, those are the contaminated set the flag can't identify. Decide: keep + tag manually by `created_at`, or wipe.
2. **Detect mid-candle anomalies.** Negative volumes, `high < low`, `high < max(open,close)`, etc. Static schema can't enforce these — should be checked.
3. **Symbol/interval coverage matrix.** How many candles per `(symbol, interval)`, what's the date range, where are the gaps. Will reveal when each service stopped writing.
4. **Last-write timestamp per symbol.** How dormant is the table? Drives whether you can trust the existing data or need to backfill.
5. **`klines_1h` decision.** Either wire it into `create_hypertables()` (one-line fix) or strip it from `CREATE_HYPERTABLE_SQL` and remove the references. Don't leave it dead.

## Profiling SQL pack

Paste these into `psql` against the running stack (`docker compose -f docker-compose.unified.yml exec timescaledb psql -U postgres -d trading_bot`).

```sql
-- ─── Section 1: Shape & coverage ──────────────────────────────────────────

-- Total rows
SELECT count(*) AS rows FROM klines;

-- Date range (timestamp is BIGINT ms — convert to TIMESTAMPTZ for sanity)
SELECT
  to_timestamp(min(timestamp)/1000.0) AS earliest,
  to_timestamp(max(timestamp)/1000.0) AS latest,
  to_timestamp(max(created_at)/1000.0) AS last_insert
FROM klines;

-- Coverage per (symbol, interval)
SELECT
  symbol,
  interval,
  count(*) AS candles,
  to_timestamp(min(timestamp)/1000.0) AS first_candle,
  to_timestamp(max(timestamp)/1000.0) AS last_candle,
  count(*) FILTER (WHERE is_mainnet)        AS mainnet_rows,
  count(*) FILTER (WHERE NOT is_mainnet)    AS testnet_rows
FROM klines
GROUP BY symbol, interval
ORDER BY symbol, interval;

-- ─── Section 2: Contamination forensics (the headline issue) ──────────────

-- Rows that PRE-DATE the 2026-04-29 ALTER but are flagged mainnet by default.
-- These are the indistinguishable contamination — flag them or wipe them.
SELECT
  symbol,
  count(*) AS suspect_rows,
  to_timestamp(min(timestamp)/1000.0) AS earliest,
  to_timestamp(max(timestamp)/1000.0) AS latest
FROM klines
WHERE created_at < extract(epoch FROM TIMESTAMP '2026-04-29 00:00:00') * 1000
  AND is_mainnet = TRUE
GROUP BY symbol
ORDER BY suspect_rows DESC;

-- Distribution of created_at by day — spot the mainnet flip and the dormancy gap
SELECT
  date_trunc('day', to_timestamp(created_at/1000.0)) AS insert_day,
  count(*) AS inserted
FROM klines
GROUP BY insert_day
ORDER BY insert_day;

-- ─── Section 3: Cross-column / business-rule violations ──────────────────

-- Bad OHLC: any row where high/low don't envelope open/close
SELECT count(*) AS bad_ohlc FROM klines
WHERE high < GREATEST(open, close)
   OR low  > LEAST(open, close)
   OR high < low;

-- Negative or zero volume on what should be a real-market candle
SELECT count(*) AS zero_or_negative_volume FROM klines WHERE volume <= 0;

-- Negative turnover (impossible)
SELECT count(*) AS negative_turnover FROM klines WHERE turnover < 0;

-- Future-dated rows
SELECT count(*) AS future_rows FROM klines
WHERE timestamp > extract(epoch FROM now()) * 1000;

-- Null turnover rate (older rows missing this field)
SELECT
  count(*) FILTER (WHERE turnover IS NULL) * 1.0 / count(*) AS null_turnover_rate
FROM klines;

-- ─── Section 4: Time-series gap detection (per symbol/interval) ───────────

-- 1-minute candles for BTCUSDT — find gaps > 2× the expected interval (60s)
WITH lag_t AS (
  SELECT
    timestamp,
    lag(timestamp) OVER (ORDER BY timestamp) AS prev_ts
  FROM klines
  WHERE symbol = 'BTCUSDT' AND interval = '1'
)
SELECT
  to_timestamp(prev_ts/1000.0)  AS gap_start,
  to_timestamp(timestamp/1000.0) AS gap_end,
  (timestamp - prev_ts) / 60000  AS gap_minutes
FROM lag_t
WHERE timestamp - prev_ts > 120000  -- > 2 minutes
ORDER BY gap_minutes DESC
LIMIT 50;

-- ─── Section 5: Hypertable / chunk health ─────────────────────────────────

-- Chunk count and per-chunk row distribution
SELECT
  hypertable_name,
  count(*) AS chunks,
  pg_size_pretty(sum(total_bytes)) AS total_size
FROM timescaledb_information.chunks
WHERE hypertable_name = 'klines'
GROUP BY hypertable_name;

-- Verify the dead `klines_1h` continuous aggregate isn't there
SELECT view_name FROM timescaledb_information.continuous_aggregates
WHERE view_name = 'klines_1h';
-- Expect 0 rows. If 1 row, someone wired it up — good. If 0, it's dead code.

-- Active retention policies on klines
SELECT job_id, application_name, schedule_interval, config
FROM timescaledb_information.jobs
WHERE hypertable_name = 'klines';
```

## Header-line summary for the next analysis

If you want one number to anchor the next conversation around: **percentage of `klines` rows where `is_mainnet=TRUE` AND `created_at` predates 2026-04-29**. That's the false-positive rate of the contamination flag. Anything > 0% means the flag is unreliable for historical analysis — and you have two clean choices: (a) wipe pre-2026-04-29 rows, (b) hand-tag a contamination cutoff in a new column based on the actual 2026-04-25 flip time.
