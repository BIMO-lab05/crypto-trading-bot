# Crypto Trading Bot

Autonomous Bybit crypto trading bot. 11 Python microservices + React frontend. Currently runs in **paper-trading mode** — real Bybit mainnet prices, simulated orders.

**Last updated:** 2026-08-19 · **Mode:** paper-trading · **Account: $100 USDT** · **Status:** actively developed — v1.3 milestone executing (living guides in [docs/](docs/README.md), history in docs/archive/)

> **No strategy in this repo has a demonstrated edge.** Twelve strategy families have been tested — seven legacy, five pre-registered — and every one was rejected; the GRU ensemble scores chance-level. See [Strategy status](#strategy-status). The working software is a measurement instrument, not a profitable trader.

---

## Stack

- **Backend:** Python 3.12, FastAPI, asyncio (one process per service)
- **Frontend:** React 18 + Vite + Tailwind, dark theme
- **Data:** TimescaleDB (candles), PostgreSQL (app state), Redis (cache), RabbitMQ (deployed but unused — nothing wires AMQP; the service mesh is synchronous REST, see ADR-016)
- **Orchestration:** Docker Compose (local), Kubernetes + Helm (prod, `infrastructure/`)
- **ML:** 16 GRU price-prediction models, currently gated **off** by default (see ML status below)
- **Observability:** Prometheus + Grafana (opt-in via `--profile monitoring`)

---

## Services

17 containers total: 10 app services + 4 infrastructure + 2 monitoring + frontend. ML-retraining service is cron-triggered and has no HTTP port.

| Service | Port | Purpose |
|---|---|---|
| api-gateway | 8000 | Frontend → backend routing, auth, admin endpoints |
| bybit-connector | 8001 | Bybit REST + WebSocket wrapper |
| market-data-service | 8002 | Candle ingest → TimescaleDB |
| portfolio-manager | 8003 | Positions, balances, P&L |
| technical-analysis | 8004 | TA indicators + GRU inference + signal aggregator |
| trading-engine | 8005 | Strategy + risk + order execution |
| notification-service | 8006 | Alerts — telegram / email / slack / sms / dashboard channels |
| ml-prediction-service | 8007 | Standalone GRU inference (gated, see below) |
| sentiment-analysis-service | 8008 | News / social sentiment (idle by default, see below) |
| risk-metrics-service | 8009 | Risk dashboards |
| ml-retraining-service | — | Cron-driven GRU retrain (no HTTP) |
| frontend | 3000 | React dashboard |
| postgres / timescaledb / redis / rabbitmq | — | Infrastructure |
| prometheus / grafana | 9090 / 3001 | Metrics + dashboards (opt-in) |

---

## Quick start

Prereqs: Docker + Compose, ~8 GB RAM, ~20 GB disk. WSL2 supported.

```bash
# Boot the stack (paper-trading defaults)
docker compose -f docker-compose.unified.yml up -d

# Tail logs for one service
docker compose -f docker-compose.unified.yml logs -f trading-engine

# Stop
docker compose -f docker-compose.unified.yml down
```

After boot:

- Dashboard: http://localhost:3000
- API gateway: http://localhost:8000 (OpenAPI: `/openapi.json`)
- RabbitMQ management: http://localhost:15672
- Prometheus / Grafana (if `--profile monitoring`): http://localhost:9090, http://localhost:3001

A scripted boot path with health probes is in `.claude/skills/start-system/SKILL.md`.

---

## Frontend

React + Vite single-page app at port 3000.

- **Command palette** (`Cmd/Ctrl+K`) — fuzzy-search symbols, trading actions, page routes
- **Vim-style shortcuts** — `g d` Dashboard, `g o` Portfolio, `g p` Performance, `g 1`/`g 3` Phase 1 / Phase 3, `g s` Settings
- **Dark / light theme toggle** — respects `prefers-color-scheme`
- **Status bar** (bottom) — live trading state, signals checked, trades, open positions, cash/P&L, emergency state
- **Performance dashboard** — equity curve, daily P&L, drawdown, correlation heatmap, returns distribution
- **Pages:** Main · Phase 1 · Phase 3 · Portfolio · Performance · Settings

Accessibility audit `docs/archive/audits/accessibility-audit-2026-05-02.md` documents WCAG 2.1 AA findings; remediation in progress.

---

## Configuration

Required env vars at the repo root `.env` (gitignored). All compose vars have `${VAR:-default}` fallbacks, so missing keys fall back safely.

### Trading-mode flags

Two **independent** flags control real-money behavior. Mixing them up is a footgun; both are required separately.

| Flag | Effect |
|---|---|
| `BYBIT_TESTNET` | Selects price source. `false` = real Bybit mainnet prices. `true` = testnet (mock prices). |
| `PAPER_TRADING_MODE` / `TRADING_MODE` | Selects whether orders are simulated. `true` / `PAPER` = simulated. `false` / `LIVE` = real orders. |
| `LIVE_TRADING_ACK` | Required to boot in LIVE mode. Must equal `I_UNDERSTAND_REAL_MONEY`. Catches env drift on cloud hosts. |

Default state: `BYBIT_TESTNET=false` + `PAPER_TRADING_MODE=true` → real prices, simulated orders.

**Going LIVE requires four deliberate steps:**

1. `PAPER_TRADING_MODE=false`
2. `TRADING_MODE=LIVE`
3. Mainnet Bybit API keys with trading permissions
4. `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`

### Feature flags (default OFF)

| Flag | Default | What it gates |
|---|---|---|
| `ENABLE_ML_PREDICTIONS` | `false` | GRU inference call from trading-engine. Off because the V0 GRU directional-accuracy metric was found to have look-ahead leakage (May 2026); models score chance-level on returns. Re-enable after rebuild on returns target with DSR > 0.95 acceptance. |
| `ENABLE_SENTIMENT_ANALYSIS` | `false` | Sentiment leg in signal aggregator. Sentiment-analysis-service still runs but is idle (no callers in the default pipeline). |
| `AUTO_TRADING_ENABLED` | `false` (compose) / **`true` (operator `.env`)** | Trading-engine's auto-trader loop. Currently armed by operator override. Loop only fires once the kill-switch file is absent. Kill-switch path: `safety/EMERGENCY_STOP` (host) → `/app/safety/EMERGENCY_STOP` (container) via dir-to-dir bind-mount of `./safety/`. Pause: `touch safety/EMERGENCY_STOP` or `POST /api/portfolio/emergency-stop`. Resume: `rm safety/EMERGENCY_STOP` (+ `POST /api/trading/start` if halted at boot). Stop: `POST /api/trading/auto/stop`. |

### Emergency stop

Kill-switch file is **`safety/EMERGENCY_STOP`** (host) → **`/app/safety/EMERGENCY_STOP`** (container), via a
read-only dir-to-dir bind mount of `./safety/`. It is not at the repo root.

- **Pause:** `touch safety/EMERGENCY_STOP`, or `POST /api/portfolio/emergency-stop` (admin-guarded).
- **Resume takes two steps:** `rm safety/EMERGENCY_STOP` **then** `POST /api/trading/start` (or restart the
  service). A file-triggered halt sets `is_running=False` and exits the loop — it does **not** auto-restart.
  Removing the file alone leaves the trader stopped. Only the *risk* kill-switch (equity / loss streak) keeps
  looping and auto-resumes.
- **Full stop:** `POST /api/trading/auto/stop`.

---

## Risk management

The account is **$100 USDT**. `shared/account.py` is the declaration of record; services read their own
`Settings` (repo-root `shared/` is outside every service's Docker build context, so it is not importable
in-container). Defaults below are from `services/trading-engine/app/config.py`.

| Cap | Setting | Paper (default) | LIVE |
|---|---|---|---|
| Per-trade notional cap | `max_risk_per_trade` | **0.10** = 10 % = $10 | hard **0.02** = 2 % = $2 |
| Max position size | `max_position_size_pct` | **10.0** % | 10.0 % |
| Daily-loss circuit-breaker | `max_daily_loss_pct` | **12.0** % = $12 | 12.0 % |
| Max total exposure | `max_total_exposure_pct` | **80.0** % | 80.0 % |
| Default stop-loss / take-profit | `default_stop_loss_pct` / `..._take_profit_pct` | 2.0 % / 4.0 % | same |
| Max hold | — | 48 h | 48 h |
| Leverage | `default_leverage` | **1.0×** (compose) | 1.0× |

Separately, `trading_enhancements/kill_switch.py` carries tiered drawdown triggers — alert 5 %, reduce
size 10 %, pause new trades 15 %, hard stop 20 % — plus a 5-consecutive-loss trigger and a 24 h auto-reset.
It is fed **equity** (cash + unrealized), not cash, and the loss streak only advances on trade *closes*.

There is **no fixed cap on concurrent positions**; concurrency is bounded by `max_total_exposure_pct` (80 %),
checked on *remaining* quantity so a partially-exited position frees the room it gave up.

`DEFAULT_LEVERAGE` was dropped 10.0 → 1.0 on 2026-08-04 (AUDIT.md §6.4/H1). At 10× the notional formula
`balance × position_size_pct × leverage` multiplied the 10 % per-trade cap back up to ~100 % of balance per
trade. Do not raise it again to clear min-notional — sub-minimum trades get rejected, never levered up.

**Units are a trap:** `max_risk_per_trade` is a **fraction** (`0.10`); every `*_pct` field is a **percent**
(`12.0`, `10.0`, `80.0`). Comparing across them without normalizing produces a check that silently never
fires. That has shipped once already.

Two figures moved from their long-standing values and the reasons matter:

- **Per-trade 2 % → 10 % in paper** ([ADR-010](wiki/decisions/ADR-010-max-risk-per-trade-paper-bump.md)).
  On $100, 2 % is $2 — under Bybit's ≈$5 minimum notional, so no trade could clear the venue floor. The 2 %
  cap remains **hard in LIVE**, and a sub-minimum trade must be **rejected with a reason, never clamped up**.
- **Daily loss 5 % → 12 %** ([ADR-028](wiki/decisions/ADR-028-daily-loss-breaker-reconciliation.md)). At a
  10 % per-trade cap, a 5 % daily limit tripped on the *first* full loss — it measured one trade, not a day.
  This **allows more** daily loss; it is a coherence fix, not a tightening. Reconcile it before LIVE.

**LIVE is not mechanically viable at this account size.** The 2 % LIVE cap is $2, below the venue minimum at
any sane stop distance — that holds regardless of whether a strategy ever finds an edge. The pre-live
checklist must restore ≤2 % before `TRADING_MODE=LIVE`.

These are project rules — relaxing requires explicit approval (see `CLAUDE.md`).

---

## Validated symbols

Three different universes are in play — do not confuse them:

| Universe | Size | Where | What it is |
|---|---|---|---|
| **Traded** | 5 | trading-engine `trading_symbols` | BTC, ETH, SOL, BNB, ADA — the only symbols that may take a position |
| **Ingested** | 14 | market-data-service `default_symbols` | Above + AVAX, LINK, ARB, OP, SUI, APT, DOT, LTC, POL — candles only, for research |
| **Research-pinned** | 30 | `backtesting/edge_lab/universe_2026-08-17.json` | Top-30 by turnover, ≥730-day listing — kill-test batteries only, never traded |

XRP / DOGE are excluded from the traded set by paper-trading loss profile — **no silent re-add**. Ingesting a
symbol does not authorize trading it; the engine restricts position-taking to the 5 regardless of what
market-data collects.

---

## Strategy status

**Twelve strategy families tested. Twelve rejected. No demonstrated edge.**

Five legacy indicator strategies (RSIMomentum, RSI_BB_Combo, MACDHistogram, BollingerMeanReversion,
StochasticRSI) plus grid and trend-following all returned negative Sharpe (−0.22 to −0.50) in in-house
backtests. Those figures were produced at $10,000 through a frictionless engine, so they are optimistic
by an unmeasured amount and understate nothing.

Two pre-registered kill-test batteries (`backtesting/edge_lab/`) then tested five structurally different
candidates against a pinned top-30-by-turnover universe (≥730-day listing; Gate 0 passed 30/30 on both
intervals with zero gaps):

| Candidate | Battery #1 (2026-08-17) | Battery #2 (2026-08-18) | Best `ratio_taker` (#2) |
|---|---|---|---|
| lf_trend (regime-gated trend) | REJECT | REJECT | 15.511 |
| funding_carry (percentile) | REJECT | REJECT | 2.603 |
| xs_momentum (cross-sectional) | REJECT | REJECT | 1.246 |
| vol_breakout (squeeze) | REJECT | REJECT | 0.966 |
| pairs_statarb | — | REJECT | 0.088 |

Candidates must clear **two** gates. Gate 1 is a cost hurdle — gross edge ≥ 2× modelled taker cost. Gate 2
is statistical — deflated Sharpe ratio ≥ 0.95 *and* ≥ 70 % of CPCV paths positive. `lf_trend` cleared Gate 1
on 4 of 5 variants and still failed: its profit came from a few outlier trades rather than a repeatable
distribution. **Clearing Gate 1 is not a result.**

`backtesting/edge_lab/trial_ledger.json` is an append-only record of every variant ever scored, and the
DSR trials floor is derived from it (16 → 21 so far; 30 rows recorded). Every new variant raises the bar for
every future candidate. That is the anti-p-hacking rail — it is meant to ratchet, and it must not be reset.

Evidence: `.planning/evidence/killtests/battery-summary-20260817.md`, `battery-summary-20260818.md`, and the
per-candidate verdict files beside them. Each carries its own caveat block (survivorship, variant warm-up
asymmetry, CPCV path correlation) and every documented caveat points optimistic. Read them before citing.

The value delivered here is **killing bad strategies cheaply** — twelve families disproved for ~$0 of live
risk. Adding a sixth indicator to five losing indicators produces a losing ensemble.

---

## ML status

16 GRU models exist (`services/ml-prediction-service/models/*.keras`), trained **2025-12-10 — now ~8 months
stale**. Retrain before relying on any prediction. The V0 directional-accuracy figures (79–84 %) were a
metric bug — `y_test[:, -1]` referenced a future bar. Fixed in commit `c56765c`. After the fix, models score
chance-level on log-returns and lose to a naive persistence baseline. Reproducer:
`docs/strategy/research-2026-04-29/persistence_shootout.py`.

Consequence: `ENABLE_ML_PREDICTIONS=false` by default. Rebuild on a returns target with a DSR (Deflated
Sharpe Ratio) > 0.95 acceptance gate before re-enabling. Raw R² on price levels is not acceptable evidence.

BTC training gets OOM-killed at default container limits — raise `deploy.resources.limits` before retraining
BTC.

**LSTM removal is incomplete.** The May 2026 deletion (`25ca9ab` … `324e162`) did not finish:
`services/ml-prediction-service/app/models/ensemble_model.py:15` still imports
`from tensorflow.keras.layers import LSTM` and `:192-195` still trains an LSTM leg;
`services/ml-retraining-service/app/core/models/lstm.py` is still present. The footprint spans 10+ files
(tracked as ML-PURGE-02, Phase 23).

The `_archive_lstm/` rollback directory is **gitignored** (`.gitignore:248`), so it exists in the operator's
working copy (27 `*_lstm.keras` files, 41 MB) but is absent from fresh clones, containers, and CI. Docs have
flipped twice on whether it exists — check `.gitignore` and say which environment you looked in.

---

## Testing

```bash
# All services
pytest --cov=services --cov-report=term

# One service
pytest services/trading-engine/tests/

# Repo-level integration / e2e
pytest tests/
```

Per-service coverage targets ≥80 %. Most services hit it; api-gateway, trading-engine, technical-analysis, risk-metrics are the focus areas.

Always pass `--no-cov` on targeted runs. Trading-engine host runs are cwd-sensitive.

**Gotcha (api-gateway), and the standing contradiction:** host pip pulls fastapi 0.136 (returns 401 from
`HTTPBearer`) while the deployed image pins 0.109 (returns 403), and the tests assert 403 — which is why the
rule says run them in-container. **But the gateway image copies only `app/` + `pytest.ini`**, so
`docker exec crypto-bot-api-gateway pytest tests/` errors with *file or directory not found*. Neither path
works as documented today; targeted host runs are the only thing that actually runs. Tracked as RES-10
(`.planning/evidence/resume-2026-08-16.md`) — do not treat the in-container rule as verified.

---

## CI/CD

`.github/workflows/` ships 10 active workflows:

| Workflow | Trigger | Purpose |
|---|---|---|
| ci.yml | push / PR | Lint, type-check, per-service tests, Docker build with Trivy |
| build-service.yml | reusable | Parameterized service image build |
| cd-dev.yml | push to `develop` | Build → push to ghcr.io → deploy to dev K8s |
| cd-prod.yml | push to `main` | Blue-green prod deploy with rollback + GitHub Release |
| deploy-k8s.yml | reusable | Generic K8s deploy (rolling / blue-green / canary) |
| security-scan.yml | daily + push / PR | Safety, pip-audit, Trivy, Grype, Bandit, Semgrep, TruffleHog, Gitleaks, Checkov, KICS |
| ml-retrain.yml | weekly cron | One-shot GRU retrain on Oracle VM (headless fallback for ml-retraining-service) |
| performance-test.yml | weekly cron + PR | Load + perf benchmarks |
| release.yml | tag `v*.*.*` | Changelog + GitHub Release |
| claude.yml | issue / PR mention `@claude` | Claude Code AI-assisted review |

Dependabot tracks pip (10 services), docker (10 services), npm (frontend), github-actions — weekly.

GitHub secrets required for CI/CD are listed in `.github/CICD_README.md`.

---

## Project layout

```
crypto-trading-bot/
├── services/                       # 11 Python microservices
│   └── <service>/app/             # FastAPI app, lifespan phases, handlers
├── frontend/                       # React + Vite SPA
├── infrastructure/                 # K8s manifests, Helm charts, DB migrations
│   └── migrations/                # 003_portfolios_orm_align.sql, 004_positions_orm_align.sql
├── docs/
│   ├── architecture/              # System overview, service contracts
│   ├── development/               # SETUP.md, TESTING.md
│   ├── operations/                # RUNBOOK.md, alerting, disaster recovery
│   ├── strategy/                  # Research plans, CPCV / DSR / vol-parity / funding-gate
│   ├── archive/               # historical reports (Nov 2025 – May 2026)
│   └── archive/audits/accessibility-audit-2026-05-02.md
├── backtesting/
│   ├── edge_lab/                  # Pre-registered kill-test battery + append-only trial_ledger.json
│   └── killtests/                 # Hurdle-first cost screen
├── tests/                          # Repo-level integration + e2e
├── .claude/                        # Agents, hooks, skills (start-system, graphify, …)
├── .github/                        # Workflows, dependabot, CI/CD docs
├── docker-compose.unified.yml      # Canonical compose (16 services + DBs, ADR-009)
├── docker-compose.legacy.yml.DISABLED  # Retired — could not boot standalone
├── shared/account.py               # Declaration of record for account size ($100) — host-run code only
├── safety/EMERGENCY_STOP           # Kill-switch file (absent = trading allowed)
├── progress.md                     # Running session log
├── CLAUDE.md                       # Project-specific Claude Code instructions
└── README.md
```

---

## Documentation

| Topic | File |
|---|---|
| Project rules + Claude Code instructions | [CLAUDE.md](CLAUDE.md) |
| Docs map (living guides) | [docs/README.md](docs/README.md) |
| Accessibility audit | [docs/archive/audits/accessibility-audit-2026-05-02.md](docs/archive/audits/accessibility-audit-2026-05-02.md) |
| System architecture | [docs/architecture/SYSTEM_OVERVIEW.md](docs/architecture/SYSTEM_OVERVIEW.md) |
| Dev setup | [docs/development/SETUP.md](docs/development/SETUP.md) |
| Operational runbook | [docs/operations/RUNBOOK.md](docs/operations/RUNBOOK.md) |
| Strategy status + edge results | [CLAUDE.md §2](CLAUDE.md) · `backtesting/edge_lab/` · `.planning/evidence/killtests/` |
| Strategy research artifacts | [docs/strategy/](docs/strategy/) (`research-2026-04-29/`, `research-2026-05-21/`) |
| CI/CD overview | [.github/CICD_README.md](.github/CICD_README.md) |
| Live API surface | http://localhost:8000/openapi.json (after boot) |
| Session log | [progress.md](progress.md) |

---

## Disclaimers

Educational software. Crypto trading carries significant risk; do not commit capital you cannot afford to lose. Test thoroughly in paper-trading mode before considering LIVE mode. Risk caps are enforced automatically but the operator must monitor.

GRU models in this repo currently lose to a naive persistence baseline on out-of-sample log-returns; do not act on their predictions until rebuilt and re-validated.

---

## License

Proprietary. Copyright © 2025 Mohammed Siradj. All rights reserved. See [LICENSE](LICENSE) for terms. No permission is granted to use, copy, modify, or distribute without explicit written consent.
