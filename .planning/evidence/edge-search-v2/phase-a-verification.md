# Edge-search v2 Phase A — deployment + four-proof verification

Date: 2026-08-19. Branch `feature/edge-search-v2`. Tasks 1–3 shipped the orderbook
(5s) and open-interest (5min) collection code; this records deployment and the
spec §2 verification #4 four-proof check for Task 4.

## Deploy

```
export DOCKER_CONFIG=$(mktemp -d)
DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml up -d --build bybit-connector market-data
```

Note: the compose service is named `market-data`, not `market-data-service` as the
brief's shorthand suggested — corrected before running.

Both containers rebuilt and came up healthy (`crypto-bot-bybit`, `crypto-bot-market-data`).
One transient DDL race on `open_interest`'s `BIGSERIAL` sequence
(`duplicate key value violates unique constraint "pg_class_relname_nsp_index"`)
occurred during boot; the app's own connection-retry logic (`Retrying in 2.0s...`)
recovered it automatically and hypertable/retention DDL completed on the next
attempt — no manual intervention.

## Proof 1 — job registration + live mainnet connector

```
docker compose -f docker-compose.unified.yml logs market-data | grep -i "orderbook\|open.interest"
```

Relevant lines:

```
app.database: Retention policy (open_interest, 730 days) applied
app.scheduler: ✅ Scheduled: Open interest collection every 5 minutes (offset +3min)
apscheduler.scheduler: Added job "Open Interest Collection" to job store "default"
app.scheduler: 📅 Job 'Open Interest Collection' next run: 2026-08-19 16:18:00+00:00
apscheduler.executors.default: Job "Orderbook Snapshot Collection (trigger: interval[0:00:05], ...)" executed successfully
```

Live mainnet base URL, from `bybit-connector` logs:

```
crypto-bot-bybit | HTTP Request: GET https://api.bybit.com/v5/market/orderbook?category=linear&limit=25&symbol=ADAUSDT "HTTP/1.1 200 OK"
```

`api.bybit.com` confirms mainnet (not testnet), consistent with `BYBIT_TESTNET=false`.

## Proof 2 — notification received

**N/A: no notification path in scope.** This is a collector, not a decisioning
service; nothing here triggers Telegram/email alerts.

## Proof 3 — DB rows persisted (taken 2026-08-19 16:21 UTC, ~7 min after deploy)

```sql
SELECT symbol, count(*), to_timestamp(max(timestamp)/1000) FROM orderbook_snapshots GROUP BY symbol;
```

```
  symbol  | count |      to_timestamp
----------+-------+------------------------
 ADAUSDT  |    67 | 2026-08-19 16:21:34+00
 APTUSDT  |    67 | 2026-08-19 16:21:36+00
 ARBUSDT  |    67 | 2026-08-19 16:21:35+00
 AVAXUSDT |    67 | 2026-08-19 16:21:34+00
 BNBUSDT  |    67 | 2026-08-19 16:21:33+00
 BTCUSDT  |    67 | 2026-08-19 16:21:32+00
 DOTUSDT  |    67 | 2026-08-19 16:21:37+00
 ETHUSDT  |    67 | 2026-08-19 16:21:32+00
 LINKUSDT |    67 | 2026-08-19 16:21:35+00
 LTCUSDT  |    67 | 2026-08-19 16:21:37+00
 OPUSDT   |    67 | 2026-08-19 16:21:35+00
 POLUSDT  |    67 | 2026-08-19 16:21:38+00
 SOLUSDT  |    67 | 2026-08-19 16:21:33+00
 SUIUSDT  |    67 | 2026-08-19 16:21:36+00
(14 rows)
```

```sql
SELECT symbol, count(*), to_timestamp(max(timestamp)/1000) FROM open_interest GROUP BY symbol;
```

```
  symbol  | count |      to_timestamp
----------+-------+------------------------
 ADAUSDT  |   200 | 2026-08-19 16:15:00+00
 APTUSDT  |   200 | 2026-08-19 16:15:00+00
 ARBUSDT  |   200 | 2026-08-19 16:15:00+00
 AVAXUSDT |   200 | 2026-08-19 16:15:00+00
 BNBUSDT  |   200 | 2026-08-19 16:15:00+00
 BTCUSDT  |   200 | 2026-08-19 16:15:00+00
 DOTUSDT  |   200 | 2026-08-19 16:15:00+00
 ETHUSDT  |   200 | 2026-08-19 16:15:00+00
 LINKUSDT |   200 | 2026-08-19 16:15:00+00
 LTCUSDT  |   200 | 2026-08-19 16:15:00+00
 OPUSDT   |   200 | 2026-08-19 16:15:00+00
 POLUSDT  |   200 | 2026-08-19 16:15:00+00
 SOLUSDT  |   200 | 2026-08-19 16:15:00+00
 SUIUSDT  |   200 | 2026-08-19 16:15:00+00
(14 rows)
```

All 14 collected symbols (the wider market-data research universe, per CLAUDE.md
§5) show rows in both tables, including the 5 validated trading symbols
(BTC, ETH, SOL, BNB, ADA). `open_interest` already carried history back to
2026-08-18 23:40:00 UTC — collection had been running continuously since the
prior (pre-restart) container instance; the redeploy did not reset it.

## Proof 4 — service restarted with the new code

```
docker inspect -f '{{.State.StartedAt}}' crypto-bot-market-data
2026-08-19T16:14:17.050449797Z

docker inspect -f '{{.State.StartedAt}}' crypto-bot-bybit
2026-08-19T16:14:04.37336696Z
```

Both containers were recreated (`Recreate` / `Recreated` in the compose output) by
the `--build` deploy above, so the running process is the freshly built image, not
stale in-memory state.

## Gap-check script

`scripts/check_collection_gaps.py` — psql-in-container gap check, thresholds:
orderbook ≤60s, open_interest ≤15min per symbol; exits 1 on any breach or empty
table.

### Smoke run (short window, 2026-08-19 16:21 UTC)

```
$ python3 scripts/check_collection_gaps.py
== orderbook_snapshots (size 32 kB, max gap allowed 60000ms)
  ADAUSDT: rows=69 ... max_gap_ms=11000 OK
  ... (all 14 symbols OK, max observed gap 12600ms)
== open_interest (size 24 kB, max gap allowed 900000ms)
  ADAUSDT: rows=200 ... max_gap_ms=300000 OK
  ... (all 14 symbols OK, max observed gap 300000ms)
RESULT: gap_breaches=0
EXIT=0
```

## Pending: 48-hour acceptance check

The smoke run above only covers a ~7-minute window. The real acceptance gate is
the 48-hour continuous run. Re-run on or after **2026-08-21 16:22 UTC**:

```
python3 scripts/check_collection_gaps.py
```

Append its full output below this line when run. A non-zero exit or any `BREACH`
line means the collectors dropped data (container restart, Bybit rate limit,
DB outage) sometime in the 48h window — investigate `docker compose -f
docker-compose.unified.yml logs market-data` around the breaching symbol's max
gap timestamp before accepting Phase A as durable.

<!-- 48h re-run output goes here -->
