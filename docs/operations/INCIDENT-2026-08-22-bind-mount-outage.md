# Incident 2026-08-22 — Docker Desktop bind-mount corruption took both databases down

**Status:** RESOLVED 2026-08-22 14:09 UTC · **Outage:** 07:10:43 → 14:09:19 UTC (~7.0 h)
**Reported as:** "a lot of error messages" in the frontend.
**Data lost:** orderbook + ticker snapshots for the window (unbackfillable). Klines/OI recovered except a 1m hole — see §5.

---

## 1. What actually failed

Four containers died at the *same second* — `2026-08-22T07:10:43Z` — all with `exit=127`:

| Container | Failed file bind-mount |
|---|---|
| `crypto-bot-postgres` | `/docker-entrypoint-initdb.d/01-init.sql` |
| `crypto-bot-timescaledb` | `/docker-entrypoint-initdb.d/01-init.sql` |
| `crypto-bot-prometheus` | `/etc/prometheus/alerts.yml` |
| `crypto-bot-tournament-harness` | `/var/run/docker.sock` |

Identical error on each:

```
error mounting "/run/desktop/mnt/host/wsl/docker-desktop-bind-mounts/Ubuntu/<hash>"
to rootfs at "<container path>": not a directory:
Are you trying to mount a directory onto a file (or vice-versa)?
```

**Root cause.** Docker Desktop stages every host bind-mount under
`/run/desktop/mnt/host/wsl/docker-desktop-bind-mounts/Ubuntu/<hash>`. After a host
suspend/resume, Docker Desktop attempted to restart the containers while the WSL host
paths were not yet mounted, and created **directories** at those staging hashes. Every
container that mounts a *single file* then failed `runc create` — you cannot bind a
directory onto a file target.

Only file-mounting containers died. Services with directory-only or named-volume mounts
survived, which is why 12 of 16 containers stayed up and the failure looked partial.

This is the same family as the documented WSL bind-mount race in `CLAUDE.md` §10
("`docker inspect` shows a `bind` mount while the path inside is empty and root-owned"),
different symptom: *wrong type* rather than *empty*.

**Not the cause:** all eight host paths were verified present and correct-type on disk
throughout. The corruption was entirely inside Docker Desktop's staging area.

## 2. Why the frontend showed errors

```
timescaledb container removed from network
  → market-data DNS: "Name or service not known" (10 retry attempts, exponential backoff)
  → market-data uvicorn workers exit; :8002 stops listening (connection refused, not a 500)
postgres container removed from network
  → trading-engine asyncpg socket.gaierror → /api/v1/performance 500
  → api-gateway aggregate /health = "degraded" (market_data:false) → HTTP 503
  → every dashboard panel that fans out through the gateway errored in the browser
```

The frontend itself was never broken. It was rendering real upstream failures — confirmed
after repair across REST (browser path), per-symbol routes, and the WebSocket stream.

**Caveat on this verification:** the Claude browser extension was not connected, so every
request path the browser makes was exercised directly, but the page was never rendered
visually. Reload `localhost:3000` to confirm the panels draw clean.

## 3. Repair performed

```bash
# 1. Rebuild the corrupted mount staging entries (named volumes untouched)
docker compose -f docker-compose.unified.yml up -d --no-deps --force-recreate \
  postgres timescaledb prometheus tournament-harness

# 2. Restart DB-dependent services so they re-resolve DNS to the new container IPs
docker compose -f docker-compose.unified.yml restart \
  market-data portfolio-manager trading-engine api-gateway grafana
```

`--no-deps` prevented compose from cascading into unrelated services.
`restart` (not `up`) was used for `trading-engine` so its `.Created` stamp and env stay stable.

**Recreating postgres is safe and does not re-run migrations:** `/docker-entrypoint-initdb.d/*`
executes only when `PGDATA` is empty, and `crypto-bot-postgres-data` is populated. All six
init/migration scripts were skipped. **Corollary: never add `-v` to a `down` here** — that
deletes the volume and *would* re-run them against an empty database.

## 4. Verification (per CLAUDE.md §7 — not health-200s alone)

| Check | Result |
|---|---|
| 16/16 containers | `healthy` |
| 11/11 ports (8000-8009, 3000, 3001, 9090) | `200` |
| api-gateway aggregate status | `degraded` → **`healthy`**, all 7 required backends `true` |
| Gateway routes probed (real routes from `openapi.json`) | 37/38 → `200` |
| Same routes through the **browser path** (`:3000` nginx `/api/` proxy) | **32/32 → `200`, zero failures** |
| Per-symbol sweep, 7 routes x 5 validated symbols, browser path | **35/35 → `200`** |
| **WebSocket** `/ws` (nginx proxy *and* direct to gateway) | **`101 Switching Protocols`**, streaming `dashboard_update` every ~5 s with live health + portfolio |
| Postgres data | intact — 47 trades, 21 positions |
| TimescaleDB data | intact — 861,233 klines preserved, now 865,419 |
| Ingest resumed | orderbook writing every 5 s; tickers, klines, OI all current |
| Auto-trader | running — 12/12 indicators OK, 0 failed, ensemble + advisory router live |
| Kill switch | absent (armed, as intended) |
| Paper balance | `$100.59` — plausible, no corruption |

The one 404, `/api/analysis/all/{symbol}`, is **pre-existing and unrelated to this outage**:
the gateway advertises the route and proxies to `/api/v1/analysis/all/{symbol}` on
technical-analysis, which has no such handler (it exposes `multi-timeframe` instead).
Reproduced directly against `:8004`. Tracked separately; not called by the dashboard.

## 5. Permanent data loss — the part the green dashboard hides

| Table | Hole | Recoverable? |
|---|---|---|
| `orderbook_snapshots` | 07:02:05 → 14:09:19 UTC (**427 min**) | **No.** Bybit serves no snapshot history. |
| `tickers` | 07:00:05 → 14:11:23 UTC (**431 min**) | **No.** |
| `klines` 5m / 15m / 60m / 240m | — | **Already auto-backfilled.** Complete. |
| `open_interest` | — | **Already auto-backfilled** (+1,218 rows). Endpoint serves history. |
| `klines` **1m** | 07:01 → 10:53 UTC (**232 min**) | **Yes, but NOT done.** See below. |

**The 1m kline hole does not affect live trading.** Verified against live traffic, not assumed:
the engine requests **only `interval=240` and `interval=60`** from technical-analysis — every
indicator including ATR is fetched at `interval=240` (`default_interval="60"`,
`config.py:303`), and multi-timeframe uses 15m/60m/240m. **No consumer requests `interval=1`.**
All of those intervals backfilled complete. BACKFILL-1M is therefore a research-data
follow-up, not an urgent trading-correctness repair.

**The 1m kline hole is still open.** The collector's restart backfill is capped at Bybit's
200-bar-per-request limit, so it recovered only the most recent 199 minutes and stopped.
The hole spans **all 16 tracked symbols** (~230 bars each, ≈3,700 bars total). It is
backfillable via paginated requests — precedent: the 174,776-bar repair of 2026-08-06.
**This has not been repaired; it needs an explicit paginated backfill run.**

### Phase C microstructure clock reset — again

Per the wait-window record, the microstructure battery requires **21 gap-free days** of
orderbook data, and orderbook holes cannot be backfilled. The clock was already reset once
by the 2026-08-20 host suspend (to ~2026-09-10). This outage resets it a second time:

> **21 gap-free days now count from 2026-08-22 14:09 UTC → earliest battery ≈ 2026-09-12.**

`GAPCHK-01` (weekly cron gap check red-lines forever on historical holes via full-table
max-gap) gets one more permanent hole to trip on.

## 6. Prevention

1. **Disable Windows sleep/hibernate on this host.** This is the second suspend-triggered
   reset in three days and it is the only thing that keeps moving the Phase C date. Already
   flagged as an operator action on 2026-08-20 and still not done.
2. On any future `exit=127` + `not a directory`, the fix is
   `up -d --no-deps --force-recreate <containers>`. If that returns the *same* mount error,
   Docker Desktop's staging area needs rebuilding — **restart Docker Desktop from the tray**.
   Do not run `wsl.exe --shutdown` from inside a WSL session.
3. Distinguish before re-running: a **DNS** error (`Name or service not known`) is this
   incident. An **auth** error (`password authentication failed for user "cryptobot"`,
   as logged 2026-08-21 21:18–21:26) is env-vs-volume password drift — the password is
   fixed in the volume at initdb, and recreate will not fix it. Different problem.

## 7. Follow-ups opened

- **BACKFILL-1M** — paginated backfill of the 232-min 1m kline hole, all 16 symbols. Open.
- **Phase C date** — ~2026-09-10 → **~2026-09-12**.
- **timescaledb checkpoint latency** — pre-crash logs show checkpoints writing ~3k buffers
  in **255–270 s** (should be sub-second), and the container reported `oom=true` at exit.
  Worth a look at `deploy.resources.limits` and WSL2 memory. Not investigated here.

## 8. Not affected

- No live isolation run existed to damage. Both `prefer_maker_orders` runs
  (`20260820T151351Z`, `20260821T165830Z`) were already abandoned before this outage —
  the second carries `ABANDONED.md` dated 2026-08-21. `PREFER_MAKER_ORDERS=false` in the
  running engine is the correct post-abandonment state, not a new regression.
- No code changed. No config changed. No migrations ran. Repair was container lifecycle only.
