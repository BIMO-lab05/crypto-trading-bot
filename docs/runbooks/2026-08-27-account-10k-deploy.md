# Runbook: deploy the $10,000 account (after the 2026-08-27 isolation harvest)

**Do NOT run before harvesting the prefer_maker isolation run (due 2026-08-27).**
The running containers still carry `PAPER_INITIAL_BALANCE=100.0` on purpose — the
isolation window must finish on the config it started with. Code and compose on
branch `feature/account-10k` already carry 10000.0; this runbook makes the *live
stack and DB* match.

Also outstanding (found 2026-08-25): `crypto-bot-postgres` and
`crypto-bot-timescaledb` are `Exited (127)` — the known host-suspend
staged-directory outage. Fix them first (step 0); the session sandbox cannot run
docker state changes.

## 0. Restore the dead DB containers (do now, independent of the flip)

```bash
docker compose -f docker-compose.unified.yml up -d --no-deps --force-recreate postgres timescaledb
docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'postgres|timescale'   # both Up (healthy)
```

Then check the kline hole that accumulated while timescaledb was down
(market-data backfills ≤ a few minutes; multi-hour holes need
`POST :8002/api/v1/collect/klines/...` backfill — see the 2026-08-22 outage notes).

## 1. Backup (before anything else)

```bash
docker exec crypto-bot-postgres pg_dump -U cryptobot -d cryptobot > backups/cryptobot_pre10k_$(date +%Y%m%d_%H%M%S).sql
```

No backup ⇒ stop. Do not proceed.

## 2. Harvest + stop the trader

1. Harvest the isolation-run results first (its own procedure).
2. `curl -X POST http://localhost:8000/api/trading/auto/stop`
3. `touch safety/EMERGENCY_STOP` (belt and braces while the DB is reseeded).

## 3. Archive old paper state + reseed at $10,000

**Schema drift warning:** the live `trades` table does not match `models.py`
(side/total_value/metadata JSONB, naive-UTC timestamps). `\d` every table before
running SQL; adapt column names to what the live DB actually has.

```sql
-- inside: docker exec -it crypto-bot-postgres psql -U cryptobot -d cryptobot
\d portfolios
\d trades
\d positions

BEGIN;
-- archive, don't delete
CREATE TABLE IF NOT EXISTS trades_archive_100usd    (LIKE trades    INCLUDING ALL);
CREATE TABLE IF NOT EXISTS positions_archive_100usd (LIKE positions INCLUDING ALL);
INSERT INTO trades_archive_100usd    SELECT * FROM trades;
INSERT INTO positions_archive_100usd SELECT * FROM positions;
DELETE FROM positions;
DELETE FROM trades;

-- reseed the portfolio row (adapt column list to \d portfolios)
UPDATE portfolios
   SET initial_balance = 10000.00,
       cash_balance    = 10000.00,
       total_value     = 10000.00,
       updated_at      = now();
SELECT portfolio_id, initial_balance, cash_balance, total_value FROM portfolios;  -- paste this in the report
COMMIT;
```

If the engine keeps a separate cash-ledger table (check `\dt *ledger*`), reseed
it the same way — the 2026-08-04 audit found ledger-vs-portfolio drift once.

## 4. Recreate services with the new env

```bash
git checkout feature/account-10k   # or the merged main
docker compose -f docker-compose.unified.yml up -d --force-recreate trading-engine portfolio-manager
# WSL bind-mount race: add --no-deps per service if PermissionError on /app/logs appears
```

Every service whose env changed must be RECREATED (restart is not enough —
compose env is baked at create time). Only trading-engine (PAPER_INITIAL_BALANCE)
and portfolio-manager (INITIAL_CAPITAL) changed.

## 5. Verify (CLAUDE.md §7 — all four proofs)

```bash
docker exec crypto-bot-trading printenv PAPER_INITIAL_BALANCE          # 10000.0
docker exec crypto-bot-portfolio printenv INITIAL_CAPITAL              # 10000.0
docker logs crypto-bot-trading --tail 50 | grep -i "api.bybit.com"     # mainnet prices
docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c \
  "SELECT portfolio_id, initial_balance, cash_balance FROM portfolios;" # 10000.00 row — paste it
curl -s http://localhost:8000/api/portfolio/summary | head -c 400      # equity 10000
# frontend at :3000 shows $10,000 baseline
```

## 6. Resume

```bash
rm safety/EMERGENCY_STOP
curl -X POST http://localhost:8000/api/trading/start
```

(Resume is two steps by design — removing the file does not restart the loop.)
