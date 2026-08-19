# Tournament Page Real Data — Design

**Date:** 2026-08-06
**Status:** Approved (user, this session)
**Goal:** `http://localhost:3000/tournament` renders a real leaderboard from a real tournament run. No mocks, no hand-written snapshots.

## Problem

The `/tournament` page shows no data. Investigation (2026-08-06):

- Frontend page, gateway endpoints (`GET /api/tournament/snapshots[/{id}]`), and
  tournament-harness API (`:8010`) all respond 200 and all correctly return empty.
- Root cause: **zero tournaments have ever run**. `services/tournament-harness/data/snapshots/`
  contains only `.gitkeep`. The entire feature (frontend Phases 6/7/14, harness Phases 1–14)
  was built but never exercised end-to-end.
- Four real defects block a real run:
  1. **Runner image mismatch** — compose sets `RUNNER_IMAGE=crypto-bot-tournament-harness:latest`;
     the built image is `crypto-trading-bot-tournament-harness:latest`. Orchestrator cannot
     launch experiment containers.
  2. **SQL type bug** — `app/runner/data.py` queries `timestamp BETWEEN %s AND %s` with Python
     datetimes; `klines.timestamp` is bigint ms-epoch. Every experiment dies at data load.
  3. **Interval convention mismatch** — config uses `"5m"`; the `klines.interval` column stores
     Bybit convention (`"5"`, `"15"`, `"60"`, `"240"`, `"D"`). Zero rows returned even after
     the type fix.
  4. **Data floor unreachable** — `MIN_ROWS_FLOOR = 50_000` (D-07), but 5m data on disk is
     ~6.5K patchy rows/symbol.

## Decisions (user-approved)

- **Scope:** minimal real run — GRU only, 3 symbols, ~6 experiments. Other architectures later.
- **Data:** backfill 5m to 365 days (~105K bars/symbol) from Bybit mainnet REST. The D-07
  50K floor stays untouched.
- **Approach:** fix the designed pipeline in place (orchestrator → Docker containers →
  leaderboard SQLite → export-snapshot → gateway → page). No in-process bypass.

## Design

### 1. Data backfill

New `scripts/backfill_klines_5m.py`:

- Fetch 365 days of 5m klines for `SOLUSDT`, `BNBUSDT`, `ADAUSDT` via bybit-connector
  `GET /api/v1/market/kline` (mainnet; connector selects network via its own env).
- Insert into TimescaleDB `klines` with `is_mainnet=true`, `interval='5'`,
  batched `execute_values`, `ON CONFLICT DO NOTHING` (never overwrites collector rows).
- Modeled on `backtesting/bybit_data_fetcher.py` (fetch loop, connector-unreachable probe)
  and `scripts/backfill_klines_from_csv.py` (insert pattern).
- Acceptance: `SELECT count(*)` ≥ 100K per symbol for `interval='5'`, `is_mainnet=true`.

### 2. Harness fixes

`services/tournament-harness/app/runner/data.py`:

- **Interval map** at the SQL boundary: `{"1m":"1","5m":"5","15m":"15","1h":"60","4h":"240","1d":"D"}`
  plus pass-through for already-converted values; raise `ValueError` on unknown. Applied to the
  query parameter only — config/YAML keeps human-readable `"5m"`.
- **Timestamp conversion**: `int(dt.timestamp() * 1000)` for both `BETWEEN` params so they
  compare against the bigint ms-epoch column.
- Unit tests for both (extend `tests/unit/`); `MIN_ROWS_FLOOR` unchanged.

`docker-compose.unified.yml`:

- `RUNNER_IMAGE` default → `crypto-trading-bot-tournament-harness:latest`.

### 3. Real run config

New `services/tournament-harness/app/config/tournament_gru_v1.yaml`:

- `symbols: [SOLUSDT, BNBUSDT, ADAUSDT]`, `intervals: ["5m"]`, `target_modes: ["log_returns"]`.
- GRU only: units `[[64], [128, 64]]`, dropout `[0.2]`, lr `[0.001]`, batch `[64]`,
  lookback `[60]`, horizon `[5]` → 2 cells × 3 symbols = **6 experiments**, sequential,
  est. 1–3h wallclock at 2 CPUs / 4G per experiment.
- LSTM excluded (ML-PURGE-02 in progress); transformer/TCN deferred.

### 4. Execution

1. Recreate harness container (picks up `RUNNER_IMAGE` fix): `docker compose ... --profile tournament up -d --force-recreate tournament-harness` (rebuild first so the image contains the data.py fix — the runner containers use the same image).
2. `docker exec crypto-bot-tournament-harness python -m app.cli run app/config/tournament_gru_v1.yaml`
3. `docker exec crypto-bot-tournament-harness python -m app.cli export-snapshot <tournament_id>`
4. Snapshot JSON lands in `/app/data/snapshots` → host `services/tournament-harness/data/snapshots/`
   → gateway RO mount `/app/snapshots`.

### 5. Error handling / honesty

- Experiments that legitimately fail stay on the leaderboard as `status=failed` with
  `failure_reason`; the page renders them. Not suppressed.
- The 365d window predates the 2026-04-25 contamination cutoff, so rows carry
  `train_window_includes_contaminated=true` and the page shows ContaminatedWindowWarning.
  Honest labeling — backfilled bars themselves are genuine mainnet via REST; the flag is
  window-based by design (D-08).
- Expected outcome per repo history: DSR ≈ 0, chance-level accuracy. **Page working ≠ edge
  found.** The leaderboard reports whatever the metrics say.

### 6. Verification (CLAUDE.md §7 standard)

- Leaderboard SQLite `SELECT` output pasted (runs with metrics).
- Snapshot JSON present on host disk.
- `curl http://localhost:8000/api/tournament/snapshots` non-empty; per-id endpoint returns
  merged snapshot.
- Harness API `:8010` `/api/v1/tournaments` and `/{id}/runs` non-empty.
- Browser check of `http://localhost:3000/tournament`: rows render, selector auto-picks
  latest tournament, filter chips + sort work, mobile cards render, console clean.
  Any real rendering error found with real data is fixed in this effort. Screenshot captured.

## Out of scope

- `open-pr` / `reproduce` flows (local dev — snapshot on disk suffices; gateway reads disk).
- LSTM / transformer / TCN architectures.
- Ensemble / significance artifacts beyond what `export-snapshot` already emits
  (page renders null gracefully).
- Any change to `MIN_ROWS_FLOOR` (D-07) or risk/trading code.
