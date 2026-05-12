# Codebase Concerns

**Analysis Date:** 2026-05-12

This document anchors known issues, technical debt, risks, dormant code, and evaluation-hygiene rules across the crypto-trading-bot stack. Each entry carries a **severity** (critical / high / medium / low) and **mitigation status**.

---

## ML / Signal Hygiene

### GRU models stale (4+ months)

- **Severity:** high
- **Issue:** All 16 GRU price-prediction models were trained 2025-12-10. Today is 2026-05-12 — models are 5+ months stale.
- **Files:** `services/technical-analysis/models/`, `services/ml-prediction-service/`, `services/ml-retraining-service/`
- **Impact:** Predictions drift; market regimes since Dec 2025 are out-of-distribution.
- **Mitigation status:** **Gated off.** `ENABLE_ML_PREDICTIONS=false` (compose default) — predictions are not feeding signals. Re-enable only after retrain.
- **Fix approach:** Run `ml-retraining-service` cron after bumping container memory limits (see "ML training memory OOM" below for BTC), validate via DSR > 0.95 acceptance gate, then flip flag.

### V0 directional-accuracy metric had look-ahead leakage

- **Severity:** critical
- **Issue:** Original V0 evaluation reported high directional accuracy because of look-ahead leakage in the metric.
- **Files:** Evaluation code referenced by commit `c56765c` (leakage fix).
- **Impact:** Prior "edge" claims based on V0 metric are invalid. Rebuilt on log-returns target, models score **chance-level vs. naive persistence** — actual loss.
- **Mitigation status:** **Fix shipped** (commit `c56765c`). Acceptance gate added: re-enable predictions only after **DSR > 0.95** on the corrected metric.
- **Fix approach:** Treat any future ML signal as forbidden in production until DSR/PSR/CPCV evidence (not raw R²) clears the gate.

### Sentiment leg removed from signal pipeline

- **Severity:** medium
- **Issue:** Sentiment leg of the 9-indicator aggregator was removed across commits `c346483`, `acae081`, `fe941cf`, `c171bb0` after producing more noise than signal.
- **Files:** `services/technical-analysis/`, `services/sentiment-analysis-service/` (idle), aggregator config
- **Impact:** `sentiment-analysis-service` still runs in compose but is **idle** — wasted CPU, RAM, build time.
- **Mitigation status:** **Flag-gated off.** `ENABLE_SENTIMENT_ANALYSIS=false` (compose default).
- **Fix approach:** Either decommission `sentiment-analysis-service` from `docker-compose.unified.yml`, or rebuild its scoring on a validated dataset before re-wiring into the aggregator. Document choice in a new ADR.

### LSTM models deleted, archive retained

- **Severity:** low
- **Issue:** LSTM model code/weights were removed May 2026; archive lives under `_archive_lstm/`.
- **Impact:** Dormant code adds repo weight and search noise but is not loaded.
- **Mitigation status:** **Archived only**; not in any import path.
- **Fix approach:** After 1 release cycle of no-LSTM stability, drop the archive from the tree (keep git history).

### Raw R² on price levels is FORBIDDEN

- **Severity:** critical (process rule)
- **Issue:** Raw R² on price levels measures persistence of the price series, not predictive edge. Any ML edge claim based on price-level R² is invalid.
- **Files:** `evaluation/returns_metrics.py`, `evaluation/sharpe_metrics.py`, `evaluation/cpcv.py`
- **Impact:** Repeating the V0 leak class — false confidence in dead models.
- **Mitigation status:** **Rule enforced via project conventions** (CLAUDE.md "Evaluation" constraint).
- **Fix approach:** All ML edge work must go through `returns_metrics.py` + PSR/DSR (`sharpe_metrics.py`) + CPCV (`cpcv.py`). Reject PRs that report R² on price.

### Profit Factor (PF) metric — pool over trades, not mean-of-folds

- **Severity:** high
- **Issue:** Backtest engine returns `PF = 0` on folds with zero losses. Computing PF as **mean of per-fold PFs** drags small-fold averages toward ~1.0 and hides edge.
- **Files:** Backtest engine PF aggregator, CPCV reporting.
- **Impact:** Gate criteria built on `mean(fold_PFs)` will under-report PF; strategies may be rejected (or accepted) on wrong grounds.
- **Mitigation status:** **Documented gotcha**; ensure all PF gates use pooled `sum(wins) / sum(losses)`.
- **Fix approach:** Audit any code using `mean(fold_PFs)`; replace with pooled formula. Add a unit test asserting pooled behavior on a synthetic zero-loss fold.

### `round(price, 2)` catastrophic for sub-$1 assets

- **Severity:** high (regression risk)
- **Issue:** TA service rounded prices to 2 decimal places; for sub-$1 assets (ADAUSDT ~$0.30), this collapsed price distinctions and produced 30+ flip-flop losses.
- **Files:** Technical-analysis service price-domain handlers (fix at commit `487d1bd`).
- **Impact:** Real paper-trading losses observed.
- **Mitigation status:** **Fix shipped** (commit `487d1bd`) — use `float(_)` not `round(_, 2)` on price-domain fields.
- **Fix approach:** Add a lint rule / grep guard against `round(*, 2)` on any field named `price`/`close`/`open`/`high`/`low`/`stop`/`tp`/`entry`. Backstop with a parametric test covering one sub-$1 symbol.

---

## Trading-Mode Safety

### Four deliberate flag flips required to reach LIVE

- **Severity:** critical (intentional friction)
- **Constraint:** LIVE trading requires **all four** of:
  1. `PAPER_TRADING_MODE=false`
  2. `TRADING_MODE=LIVE`
  3. Mainnet Bybit keys with **trade permissions**
  4. `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`
- **Files:** `services/trading-engine/` boot-time guard.
- **Impact:** `trading-engine` **refuses to boot in LIVE mode** without the ACK string — catches env drift on cloud hosts.
- **Mitigation status:** **Enforced in code.** Do not weaken or remove this guard.

### Per-trade risk cap: 2% LIVE, 10% paper (ADR-010)

- **Severity:** critical
- **Issue:** Paper-trading cap was relaxed to **10%** per ADR-010 (filed 2026-05-06) to clear Bybit min-notional on a $100 balance. LIVE cap remains **2%, non-negotiable**.
- **Files:** Trading-engine risk config; `wiki/decisions/ADR-010-*`
- **Impact:** Forgetting to restore ≤2% before flipping to LIVE → uncapped real-money loss.
- **Mitigation status:** **Pre-live checklist required.** Must restore cap to ≤2% before `TRADING_MODE=LIVE`.
- **Fix approach:** Add a boot-time assertion in trading-engine: if `TRADING_MODE == "LIVE"` and `per_trade_cap > 0.02`, refuse to start.

### 5% daily-loss circuit-breaker (always-on)

- **Severity:** critical
- **Status:** **Always-on** in trading-engine. Do not gate behind feature flags.
- **Files:** Trading-engine risk module.
- **Fix approach:** Leave alone. Add an integration test that simulates a 5% loss day and verifies trading halts.

### Auto-trader armed by operator override

- **Severity:** high
- **Issue:** Compose default is `AUTO_TRADING_ENABLED=false`, but the operator override in `.env` is `AUTO_TRADING_ENABLED=true` (set 2026-05-05). The auto-trader loop runs unless gated.
- **Files:** Trading-engine main loop; `EMERGENCY_STOP` file at repo root (RO bind-mount in trading-engine container).
- **Impact:** Stack boots with auto-trader armed; the only thing keeping it idle is the presence of `EMERGENCY_STOP`.
- **Mitigation status:** **Gated by `EMERGENCY_STOP` file** + admin endpoint `POST /api/portfolio/emergency-stop` + full-stop endpoint `POST /api/trading/auto/stop`.
- **Fix approach:** Document the dependency on `EMERGENCY_STOP` prominently. Add monitoring that alerts if the file is deleted unexpectedly. Confirm RO bind-mount semantics survive `compose down`.

### Validated symbols: BTC ETH SOL BNB ADA

- **Severity:** medium
- **Issue:** Only 5 symbols are validated for paper trading. **XRP / DOGE are excluded** due to insufficient paper-trading data — no silent re-add.
- **Files:** Trading-engine `trading_symbols`, market-data `default_symbols`.
- **Impact:** Re-adding unvalidated symbols would route uncalibrated signals to real (mainnet-priced) decisions.
- **Mitigation status:** **List frozen.** BTC + ETH were re-added 2026-05-03 per operator request; market-data `default_symbols` was reconciled the same day.
- **Fix approach:** Any new symbol requires a fresh paper-trading validation pass before being added.

---

## Data Integrity

### TimescaleDB mixed testnet/mainnet history pre-2026-04-25

- **Severity:** high (for any historical analysis)
- **Issue:** The Bybit source flipped from testnet → mainnet **mid-day on 2026-04-25**. All `klines` / `tickers` rows from before that point are mixed-origin and **polluted by testnet prices**.
- **Files:** TimescaleDB `klines`, `tickers` tables.
- **Impact:** Backtests or TA over pre-2026-04-25 candles produce invalid edge claims.
- **Mitigation status:** **Documented.** Forward-going (post-flip) data is clean.
- **Fix approach:** Either (a) wipe `klines` / `tickers` before historical analysis, or (b) ensure backtest SQL **filters `is_mainnet=true`**. Add an `is_mainnet` index if not present. Encode this filter in any new backtest helper as a default-on guard.

### Market-data caches in TimescaleDB, not Redis

- **Severity:** medium
- **Issue:** `market-data-service` caches in TimescaleDB. Redis is **empty** in testing — the DB *is* the cache.
- **Files:** `services/market-data-service/`
- **Impact:** Redis as a cache layer is misleading documentation; debugging stale prices means checking TSDB, not Redis. Also a single-point-of-load on TSDB.
- **Mitigation status:** **Documented behavior.**
- **Fix approach:** If prices look stuck: hit `POST /api/v1/collect/ticker/{symbol}` on market-data (port 8002) to force-refresh, or wait up to 5 min for the scheduler. Longer-term, decide: actually use Redis, or remove the misleading dependency.

---

## Build / Infra

### Two compose files (one canonical, one incomplete)

- **Severity:** high
- **Issue:** `docker-compose.unified.yml` is canonical (16 services incl. DBs). `docker-compose.yml` is **missing** postgres, timescaledb, redis, rabbitmq.
- **Files:** `docker-compose.yml`, `docker-compose.unified.yml`
- **Impact:** Anyone running plain `docker compose up -d` (default file) gets a half-broken stack and sees mysterious connection errors.
- **Mitigation status:** **Documented in CLAUDE.md.** Standard command: `docker compose -f docker-compose.unified.yml up -d`.
- **Fix approach:** Delete or replace `docker-compose.yml` with a stub that errors out with a helpful message pointing to the unified file. Or rename the unified one to be the default.

### sentiment-analysis image build flakiness

- **Severity:** medium
- **Issue:** `sentiment-analysis-service` image fails to build via pip (PyPI read timeouts). The other 10 service images cache fine.
- **Files:** `services/sentiment-analysis-service/Dockerfile`, `requirements.txt`
- **Impact:** Full `compose up --build` fails on the slowest link.
- **Mitigation status:** **Workaround documented.** Retry build of just that one, or `--no-deps` skip.
- **Fix approach:** Since sentiment is flag-gated off and idle (see "Sentiment leg removed" above), consider removing the service from the compose file entirely. Or pin a wheel mirror / pre-build a base image.

### BuildKit hangs on WSL2

- **Severity:** medium
- **Issue:** BuildKit frequently hangs during `docker compose build` on WSL2.
- **Mitigation status:** **Workaround documented.** Use `DOCKER_BUILDKIT=0 docker compose up -d --build <svc>`.
- **Fix approach:** Test latest Docker Desktop / WSL2 versions; investigate `buildx` driver alternatives. Keep workaround in the README until upstream fix lands.

### WSL bind-mount race

- **Severity:** medium
- **Issue:** `docker inspect` reports a `bind` mount, but the path inside the container is **empty and root-owned** — the mount silently failed at create time. Symptom: `PermissionError` writing to `/app/logs`.
- **Mitigation status:** **Workaround documented.** Fix: `docker compose up -d --force-recreate <service>`.
- **Fix approach:** Add a startup probe in each service entrypoint that verifies `/app/logs` is writable; fail-fast with a clear message instead of cryptic permission errors mid-run.

### ML training memory: BTC OOM at default container limits

- **Severity:** high (blocks ML retrain workflow)
- **Issue:** BTC training has been OOM-killed at default container memory limits.
- **Files:** `docker-compose.unified.yml` → `ml-retraining-service.deploy.resources.limits`
- **Impact:** Cannot retrain the BTC GRU model without bumping limits — which directly blocks lifting the ML-prediction flag.
- **Mitigation status:** **Documented.** Bump memory in `deploy.resources.limits` for `ml-retraining-service` before retrain.
- **Fix approach:** Codify a "retrain profile" override compose file with elevated limits, e.g. `docker-compose.retrain.yml`, so the production compose file isn't permanently over-provisioned.

---

## Docs Drift

### `docs/architecture/SYSTEM_OVERVIEW.md` + `SERVICE_CONTRACTS.md` are STALE

- **Severity:** high (misleads new contributors / AI agents)
- **Issue:** Both files date to October 2025 and contain:
  - **Wrong ports** for services.
  - The retired **`/v1/` prefix** in REST examples.
  - Only **6 of 11 services** documented.
- **Files:** `docs/architecture/SYSTEM_OVERVIEW.md`, `docs/architecture/SERVICE_CONTRACTS.md`
- **Impact:** Following these docs leads to broken curls and wrong assumptions about the surface area.
- **Mitigation status:** **Not mitigated.** Live truth is in `wiki/modules/*` and `http://localhost:8000/openapi.json`.
- **Fix approach:** Either (a) replace these files with pointers to the wiki + live OpenAPI, or (b) regenerate from current code and add a CI freshness check.

### `docs/architecture/DECISIONS.md` referenced but does not exist

- **Severity:** medium
- **Issue:** CLAUDE.md (historically) and other docs referenced this file as the home of architecture decisions. The file does not exist; decisions live in `wiki/decisions/` as ADR-001 through ADR-010.
- **Files:** `wiki/decisions/`, scattered references in older docs.
- **Mitigation status:** **CLAUDE.md updated** to flag the stale reference.
- **Fix approach:** `grep -r "docs/architecture/DECISIONS.md"` and update every remaining reference to point at `wiki/decisions/`.

### `docs/api/openapi.yaml` removed

- **Severity:** low
- **Issue:** Snapshot was removed 2026-04-26 because it had drifted from the live surface.
- **Mitigation status:** **Resolved.** Live spec: `http://localhost:8000/openapi.json` (gateway).
- **Fix approach:** If a versioned snapshot is genuinely needed (e.g., for client SDK generation), wire a CI job that dumps `openapi.json` per release tag — never hand-edit.

---

## Jan 2026 Fixes — Do Not Regress (commit `380a674`)

These three fixes were shipped together to address an inverted risk/reward ratio bug. They are interdependent — regressing any one of them re-opens the R/R issue.

### SHORT enforcement

- **Severity:** critical (regression risk)
- **Fix:** Short-side trades now honor the same risk caps and execution path as longs.
- **Files:** Trading-engine order builder.
- **Mitigation status:** **Shipped.** Any change to order construction must keep SHORT-side branches symmetric.

### 48-hour max-hold

- **Severity:** high
- **Fix:** Positions auto-close at 48h to bound exposure regardless of signal state.
- **Files:** Trading-engine position lifecycle.
- **Mitigation status:** **Shipped.** Test it stays wired after any refactor of the lifecycle loop.

### Stop-loss limit-orders

- **Severity:** critical
- **Fix:** Stops are placed as **limit orders** (not market) to avoid worst-case slippage during thin-book moves.
- **Files:** Trading-engine SL placement.
- **Mitigation status:** **Shipped.** Do not "simplify" back to market stops without an ADR.

---

## Cross-Cutting Test-Coverage Gaps

### api-gateway tests must run inside the container

- **Severity:** medium
- **Issue:** Host pip carries fastapi 0.136 (HTTPBearer returns **401**, RFC 6750); deployed container pins fastapi 0.109 (returns **403**). Tests assert **403**, so host runs show spurious failures.
- **Files:** `services/api-gateway/tests/`, `services/api-gateway/tests/conftest.py`
- **Mitigation status:** **Documented.** Run via `docker exec crypto-bot-api-gateway pytest`.
- **Fix approach:** Either bump the container's fastapi pin and update assertions to 401, or add a pytest skip marker for host runs with a clear message.

### `pathlib.Path.write_text` bypasses `builtins.open` mocks

- **Severity:** medium (test correctness)
- **Issue:** `Path.write_text` / `read_text` / `Path.open` go through C-level `_io.open` and are **not** intercepted by `mock.patch("builtins.open")`. Tests that try to mock file writes via `builtins.open` silently do nothing.
- **Impact:** Tests for routes like `/api/portfolio/emergency-stop` (which writes the `EMERGENCY_STOP` file via `Path.write_text`) appear to pass while actually touching the real filesystem.
- **Mitigation status:** **Documented.**
- **Fix approach:** Patch `pathlib.Path.write_text` directly. Audit existing tests that mock `builtins.open` for file-creation endpoints — they may be silently no-op.

### admin-guarded routes need `admin_client` fixture

- **Severity:** low (test ergonomics)
- **Issue:** Plain `test_client` returns 403 on admin routes. The `admin_client` fixture (in `services/api-gateway/tests/conftest.py`) overrides `get_current_admin_user` + `get_current_active_user` via `app.dependency_overrides`.
- **Mitigation status:** **Fixture exists.** Use it.

---

*Concerns audit: 2026-05-12*
