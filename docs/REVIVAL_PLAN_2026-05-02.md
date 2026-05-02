# Revival Plan — 2026-05-02

Goal: bring core trading loop back to life on a 3 GB WSL host without rebuilding heavy ML images. Last green: ~`06208b3` (Dec 2025). HEAD: `f777537` (May 2026).

## Host reality

- WSL: 3 GB RAM, 4 procs, 8 GB swap (`/mnt/c/Users/moham/.wslconfig`). Free at session start: ~200 MB.
- Docker bloat: 66 GB images + 29 GB build cache = 95 GB reclaimable.
- Compose `deploy.limits` for the **core stack only** (no `ml`, no `analytics` profile) sums to ~7.5 GB but reservations only ~1.6 GB. With swap this fits — barely.

## Audit results (4 services in scope)

| Service | Ready | Top issue |
|---|---|---|
| portfolio-manager | conditional | `/health` always returns 200 (false-positive) |
| technical-analysis | yes | clean — no GRU on boot, no sentiment leftovers |
| risk-metrics-service | yes | clean — no deadlocks, graceful Redis fallback |
| trading-engine | yes (with flag flip) | `ENABLE_ML_PREDICTIONS` compose default is `true` but ml-prediction will be off |

Aggregator degrades gracefully when ml-prediction / sentiment-analysis are unreachable (returns 0.0 score, signal still produced from TA). Risk caps intact (2 % per trade, 5 % daily DD).

## Heaviness root causes

1. **trading-engine/requirements.txt:18** ships `tensorflow==2.16.1` for LSTM models that were deleted in commits `324e162` / `9a0f584`. Zero `tensorflow` imports remain in `services/trading-engine/app/`. Dead weight — ~600 MB image bloat and minutes of build time.
2. Docker holds 95 GB reclaimable (images + build cache). Every rebuild re-resolves dependency graph against bloated cache.
3. ml-prediction and sentiment-analysis images do exist but are gated behind `--profile ml` / `--profile analytics` — no need to build/run them.

## Tree of work

```
PHASE 0 — safety
  0.1 commit unstaged Pydantic v2 migrations (4 files, mechanical)
  0.2 advisor sanity-check before destructive ops
  0.3 docker system prune -a -f  (NO --volumes, preserve crypto-bot-* data)

PHASE 1 — strip dead weight
  1.1 remove tensorflow==2.16.1 from services/trading-engine/requirements.txt
  1.2 grep again to confirm zero TF imports → safe
  1.3 audit scikit-learn / scipy usage in trading-engine — keep if still imported

PHASE 2 — config
  2.1 patch docker-compose.unified.yml trading-engine env:
      ENABLE_ML_PREDICTIONS=false
      ENABLE_SENTIMENT_ANALYSIS=false
  2.2 verify .env files for the 4 focus services match .env.example
  2.3 confirm EMERGENCY_STOP file exists at repo root (bind-mount source)

PHASE 3 — bring up infra (no build)
  3.1 docker compose -f docker-compose.unified.yml up -d postgres timescaledb redis rabbitmq
  3.2 wait for all 4 healthy (pg_isready, redis ping, rabbitmq diagnostics)
  3.3 confirm migrations 001 + 002 ran (init-db.sql mounts them)

PHASE 4 — build core services one at a time, BUILDKIT=0
  Order minimises peer waits:
  4.1 bybit-connector
  4.2 market-data-service
  4.3 portfolio-manager
  4.4 technical-analysis
  4.5 trading-engine          (rebuilt slim after TF removal)
  4.6 api-gateway
  4.7 notification-service
  Each: build → up -d → wait healthy → log spot-check → next

PHASE 5 — verify (per CLAUDE.md /verify-stack)
  5.1 all 12 containers healthy in docker compose ps
  5.2 GET /health on each app service returns 200
  5.3 GET /ready returns 200 (deeper check)
  5.4 market-data has Bybit MAINNET URL in logs (not testnet)
  5.5 portfolio-manager DB shows portfolio row
  5.6 trading-engine signal aggregator log: "ml_prediction unavailable, degrading"
       (proves graceful degradation path is hit)

PHASE 6 — proof of life
  6.1 trigger trading-engine signal evaluation on SOL / BNB / ADA
  6.2 confirm: paper order created → position written to portfolio DB
  6.3 confirm: notification dispatched (Telegram delivery, not just sent=True)
  6.4 leave running 10 min, check no crash loop, no OOM kill in dmesg
```

## What NOT to do

- Do **not** activate `--profile ml` (ml-prediction needs TF, won't fit RAM).
- Do **not** activate `--profile analytics` (sentiment-analysis was already removed from signal flow).
- Do **not** prune `--volumes` — that wipes postgres / timescale data.
- Do **not** rebuild ml-prediction or sentiment-analysis images.
- Do **not** relax 2 % per-trade / 5 % daily DD risk caps.
- Do **not** flip `PAPER_TRADING_MODE=false` — paper mode stays on.

## Rollback

If a service won't come up:
1. `docker compose logs <svc> --tail 200` first.
2. If image build is the issue, `DOCKER_BUILDKIT=0 docker compose build <svc> --no-cache`.
3. If bind-mount race (CLAUDE.md gotcha): `docker compose up -d --force-recreate <svc>`.
4. Last resort: `git checkout 06208b3 -- services/<svc>/` for that one service, document delta in `progress.md`.

## Open questions for user

- Confirm OK to `docker system prune -a -f` (no `--volumes`, data preserved). Reclaims 95 GB.
- Confirm OK to remove `tensorflow==2.16.1` from `services/trading-engine/requirements.txt`. No TF imports in app/.
- Confirm OK to commit the 4 unstaged Pydantic v2 migration files (mechanical, follows pattern of merged f777537).
