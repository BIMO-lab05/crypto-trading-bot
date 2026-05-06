# Phase 1: Bootstrap & Recorded Tape - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-06
**Phase:** 01-bootstrap-recorded-tape
**Areas discussed:** Tape format & coverage, Healthy-idle definition, Live-vs-recorded selector

---

## Tape format & coverage

### Storage format

| Option | Description | Selected |
|--------|-------------|----------|
| JSONL per feed | One file per (feed, symbol). Human-greppable, diffable, fits Bybit JSON payloads | ✓ |
| SQLite single file | All feeds in one .db; queryable; faster random-access | |
| Parquet columnar | Compact, fast for scans, but binary; needs pyarrow | |

**User's choice:** JSONL per feed (Recommended)

### Feed coverage

| Option | Description | Selected |
|--------|-------------|----------|
| Klines (OHLCV) | Required for technical-analysis + backtest | ✓ (Claude discretion) |
| Ticker / last price | Required for portfolio mark-to-market + UI | ✓ (Claude discretion) |
| Orderbook L2 snapshot | Maker-order path needs L2; default off, can skip v1 | |
| Funding rate history | ENABLE_FUNDING_GATE consumer; default off | |

**User's choice:** "shoose the best option for the project to get it done" → Claude discretion
**Notes:** Klines + Ticker chosen because their consumers are default-on; orderbook + funding deferred to Phase 5 forward-tests.

### Symbol + window scope

| Option | Description | Selected |
|--------|-------------|----------|
| 5 symbols × 7 days | BTC/ETH/SOL/BNB/ADA × 7d 5m klines + ticker | ✓ |
| 3 symbols × 24 hours | SOL/BNB/ADA × 24h; tiniest tape | |
| 5 symbols × 30 days | Full month; may need git-lfs | |

**User's choice:** 5 validated symbols × 7 days (Recommended)

### Storage location

| Option | Description | Selected |
|--------|-------------|----------|
| In-repo `tests/fixtures/tape/` | Checked in if <50 MB; works offline | ✓ |
| Git-LFS | Use if tape grows past 50 MB | |
| Generated on first bootstrap | Download from pinned URL | |

**User's choice:** In-repo (Recommended)

### Capture method

| Option | Description | Selected |
|--------|-------------|----------|
| Committed capture script | scripts/tape/capture_bybit.py against live mainnet REST | ✓ |
| Snapshot from running market-data-service | Dump TimescaleDB klines table | |
| Bybit historical CSV download | Use Bybit public dumps | |

**User's choice:** Committed capture script (Recommended)

### Refresh cadence

| Option | Description | Selected |
|--------|-------------|----------|
| Manual on demand | Tape ages until operator reruns capture script | ✓ |
| Nightly auto-refresh | CI re-captures + commits | |
| Pinned forever | Never refresh in this milestone | |

**User's choice:** Manual on demand (Recommended)

### Schema versioning

| Option | Description | Selected |
|--------|-------------|----------|
| `tape_version` field per file | Header line `{tape_version, captured_at, source, symbol, feed}` | ✓ |
| Filename-encoded version | tape/v1/klines/SOLUSDT.jsonl | |
| No version yet | Revisit later | |

**User's choice:** tape_version field (Recommended)

### Clock handling

| Option | Description | Selected |
|--------|-------------|----------|
| Replay timestamps as-is, no clock mock | Loader emits captured ts; wall-clock real | ✓ |
| Freeze wall clock to tape start | Mock time across services; invasive | |
| Wall clock real, speed multiplier | Replay 7d in 7m; breaks now()/candle-time compares | |

**User's choice:** Replay as-is (Recommended)

---

## Healthy-idle definition

### Idle bar at bootstrap exit

| Option | Description | Selected |
|--------|-------------|----------|
| All 15 services /health=200, no trade asserted | Lowest false-pass risk; trade in Phase 2 | ✓ |
| Health + paper trade round-trip <60s | Stronger but couples bootstrap to engine state | |
| Health + smoke (one tape kline ingested) | Cheap proof tape works | |

**User's choice:** All 15 /health=200 (Recommended)

### Flag state at bootstrap exit

| Option | Description | Selected |
|--------|-------------|----------|
| Safe defaults: paper, auto-trader off, ML off, sentiment off | Operator must explicitly arm | ✓ (with override) |
| Match operator override: auto-trader armed, EMERGENCY_STOP touched | Mirror real .env | |
| Everything OFF including paper trading | Strictest; loop never fires | |

**User's choice:** Safe defaults — but overrode `AUTO_TRADING_ENABLED=true` to match operator-override per CLAUDE.md.
**Notes:** Final flag set: `PAPER_TRADING_MODE=true`, `TRADING_MODE=PAPER`, `AUTO_TRADING_ENABLED=true`, `ENABLE_ML_PREDICTIONS=false`, `ENABLE_SENTIMENT_ANALYSIS=false`.

### EMERGENCY_STOP at boot (follow-up)

| Option | Description | Selected |
|--------|-------------|----------|
| Touch EMERGENCY_STOP by default | Loop holds at STEP-0 until operator removes | ✓ |
| Leave absent | Loop fires immediately on tape data | |
| Configurable via flag | bootstrap.sh --arm-trader | |

**User's choice:** Touch EMERGENCY_STOP (Recommended)
**Notes:** Reconciles armed auto-trader with "explicitly arm anything" stance.

### Health probe

| Option | Description | Selected |
|--------|-------------|----------|
| Existing health_check.sh + /health per port | Reuse repo pattern; ~120s timeout | ✓ |
| docker compose --wait | Requires HEALTHCHECK in every Dockerfile | |
| Custom Python probe | Polls /health + /ready + DB + RabbitMQ | |

**User's choice:** health_check.sh (Recommended)

### Failure behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Fail loud, leave stack up | Print last 50 log lines; no teardown | ✓ |
| Fail loud + tear down | Clean slate; loses post-mortem context | |
| Auto-retry up to N times | Goodhart trap | |

**User's choice:** Fail loud, leave up (Recommended)

---

## Live-vs-recorded selector

### Selector mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Single env var `MARKET_DATA_SOURCE=tape\|live` | Read by bybit-connector; default tape | ✓ |
| Compose override file docker-compose.tape.yml | Bootstrap composes -f -f; swap container | |
| bootstrap.sh --live flag | Default tape; --live flips env + skips mount | |

**User's choice:** Single env var (Recommended)

### Loader location

| Option | Description | Selected |
|--------|-------------|----------|
| Inside bybit-connector behind flag | One service; downstream is mode-agnostic | ✓ |
| New tape-replayer container, replaces bybit-connector | Stronger isolation, more code | |
| Pre-seed TimescaleDB, skip bybit-connector | Fast for static; breaks WS-dependent paths | |

**User's choice:** Inside bybit-connector (Recommended)

### Live-smoke path

| Option | Description | Selected |
|--------|-------------|----------|
| Same compose, `MARKET_DATA_SOURCE=live`, separate nightly CI | Failure notifies but doesn't block deterministic CI | ✓ |
| Separate scripts/live-smoke.sh, no CI | Operator runs by hand | |
| Defer live-smoke to Phase 2 | Phase 2 owns it | |

**User's choice:** Nightly CI workflow (Recommended)

### Tape-mode credentials

| Option | Description | Selected |
|--------|-------------|----------|
| Tape mode bypasses Bybit auth check | Empty creds OK; removes #1 fresh-clone friction | ✓ |
| Tape mode requires placeholder creds | Bootstrap writes dummy keys; format-validate only | |
| Tape mode reuses .env if present | Loosest; risk of subtle drift | |

**User's choice:** Bypass auth in tape mode (Recommended)

---

## Claude's Discretion

- **Feed selection in v1 tape**: User delegated. Chose **Klines + Ticker only** because their consumers are default-on; Orderbook + Funding deferred to Phase 5 when their consumer flags forward-test.

## Deferred Ideas

- Orderbook L2 + funding-rate tape capture → Phase 5
- Speed-multiplier replay → revisit if Phase 2 integration tests need it
- git-lfs for tape → only if v1 tape >50 MB
- Custom Python health probe (DB + RabbitMQ depth) → revisit in Phase 2
- DB migrations on bootstrap → assume compose init scripts cover v1; revisit in Phase 2 if drift
- Vault dev-mode init / Telegram bot stub for bootstrap → surface in Phase 2 RUNBOOK if missing from compose defaults
