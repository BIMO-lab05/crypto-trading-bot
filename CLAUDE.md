# Crypto Trading Bot

## 1. THE ACCOUNT IS $100

Not $10,000. Not $100,000. **One hundred US dollars.**

The repo contains ~1,000 occurrences of `10000` as a capital figure. They are wrong, they are being removed, and **they do not override this line**. If a file you are reading implies a different account size, the file is the defect — say so, do not silently adopt its number.

`shared/account.py` is the declaration of record. Never write an account-size literal.

**How to reference it depends on where the code runs:**

| Location | Rule |
|---|---|
| `services/*/app/**` (in container) | read the service's own `Settings` (`settings.paper_initial_balance`). **Never `import shared.account`** — repo-root `shared/` is outside every service's Docker build context and will `ImportError`. |
| `backtesting/**`, `tests/**` (host-run) | `from shared.account import ...` directly. |

Agreement is enforced by `tests/test_account_config_sync.py`, not by a shared import.

**Mechanical consequences of $100 — reason from these, not from intuition:**

- Per-trade cap 10% = **$10**. Bybit minimum notional ≈ **$5**. Headroom is thin.
- Round-trip taker fee ≈ 0.11% of notional. At the 2,000–4,600 trades/run seen in backtests, **fees alone exceed any observed edge**.
- The LIVE cap of 2% is **$2** — below the venue minimum at any sane stop distance. **LIVE trading is not mechanically viable at this account size regardless of edge.** Know this before flipping four flags.
- A trade below min-notional must be **rejected with a reason**, never clamped up. Clamping up turns a 10% cap into a 40% cap.

Deeper rules load automatically when you edit money code — see `.claude/rules/money.md`.

## 2. No strategy has a positive edge yet

Do not propose new features without confronting this table.

| Strategy | Win rate | Sharpe | Trades |
|---|---|---|---|
| RSIMomentum | 45.2% | **−0.28** | 1,986 |
| RSI_BB_Combo | 48.9% | **−0.47** | 2,993 |
| MACDHistogram | 32.5% | **−0.31** | 2,088 |
| BollingerMeanReversion | 43.1% | **−0.46** | 2,846 |
| StochasticRSI | 43.7% | **−0.47** | 4,658 |
| Grid (walk-forward) | 19.2% | **−0.50** | 0/3 positive windows |
| Trend-following | 0.0% | **−0.22** | 5 |
| GRU ensemble | chance-level | — | loses to naive persistence |

Two things make this **worse** than it looks: the paper engine has **no slippage model** (PAPER-01), so these are already optimistic; and all figures were produced at **$10,000**, which hides the min-notional constraint entirely.

Consequences for how you work here:

- Every backtest number in the repo predating 2026-08-03 answers a question about a $10,000 account. Re-run before citing.
- Label paper P&L *gross of slippage* wherever reported. Never present it as a realistic expectation.
- Adding a sixth indicator to five losing indicators produces a losing ensemble. The infrastructure's current value is **killing bad strategies cheaply** — treat "disproved in an afternoon" as a win.
- No edge claim without DSR/CPCV (`returns_metrics.py`, `sharpe_metrics.py`, `cpcv.py`). Raw R² on price levels is forbidden.

## 3. What this is

Autonomous Bybit crypto trading bot. 11 Python microservices + React frontend. **Paper-trading mode** — no real orders. Market data from **Bybit mainnet** (`BYBIT_TESTNET=false`) for real prices; orders simulated via `PAPER_TRADING_MODE=true`. v1.3 "TA + Engine Correctness" milestone executing (`.planning/STATE.md`).

- **Python 3.12** + FastAPI + asyncio per service. **React 18 + Vite** frontend.
- **TimescaleDB** (candles), **PostgreSQL** (app state), **Redis** (cache), **RabbitMQ** (deployed but *nothing wires AMQP* — the mesh is synchronous REST, see ADR-016).
- **Docker Compose** local; Kubernetes + Helm in `infrastructure/`.
- **ML gated off** (`ENABLE_ML_PREDICTIONS=false`). V0 directional-accuracy had look-ahead leakage; post-fix (`c56765c`) models score chance-level. Re-enable only after rebuild on a returns target with DSR > 0.95.
- **LSTM removal is incomplete.** `_archive_lstm/` **does exist** — at `services/ml-prediction-service/models/_archive_lstm/`, holding **27 `*_lstm.keras` files, 41 MB**. `ensemble_model.py:15` still does `from tensorflow.keras.layers import LSTM`, and `:192-195` still trains an LSTM leg. References span 10+ files (ML-PURGE-02, Phase 23). *(This file asserted the archive directory did not exist from an unverified claim until 2026-08-03 — corrected against the filesystem. Do not restore the old wording.)*

| Service | Port | Purpose |
|---|---|---|
| api-gateway | 8000 | Frontend → backend routing, auth |
| bybit-connector | 8001 | Bybit REST + WebSocket wrapper |
| market-data-service | 8002 | Candle ingest → TimescaleDB |
| portfolio-manager | 8003 | Positions, balances, P&L |
| technical-analysis | 8004 | TA indicators + GRU inference + signal aggregator |
| trading-engine | 8005 | Strategy + risk + order execution |
| notification-service | 8006 | Telegram + email alerts |
| ml-prediction-service | 8007 | Standalone ML inference (compose `ml` profile) |
| sentiment-analysis-service | 8008 | News / social sentiment (compose `analytics` profile) |
| risk-metrics-service | 8009 | Risk dashboards |
| ml-retraining-service | — | Cron GRU retrain (no HTTP) |

Frontend `:3000`. Prometheus `:9090`. Grafana `:3001`. Every service exposes `GET /health` and `GET /ready`.

Feature flags (compose defaults): `ENABLE_ML_PREDICTIONS=false`, `ENABLE_SENTIMENT_ANALYSIS=false`. The sentiment leg was removed from the signal pipeline; neither service starts by default.

## 4. Wiki knowledge base

`wiki/` — Obsidian vault co-located with the repo. When you need context not already in conversation:

1. `wiki/hot.md` (≤500 words, recent-context cache)
2. `wiki/index.md` (master catalog)
3. `wiki/<domain>/_index.md`
4. Only then individual pages

**ADRs live only in `wiki/decisions/`** (ADR-001 … ADR-028). The old `docs/decisions/` side-channel was merged 2026-07-30. `docs/architecture/DECISIONS.md` never existed — don't cite it.

Skip the wiki for general coding questions or anything already in this file. After significant code changes run `/wiki-lint`; after major commits `/wiki-ingest <path>`.

## 5. Safety rails (non-negotiable)

- **Risk caps.** Per-trade **2% in LIVE — no relaxation without explicit approval**. Paper is relaxed to **10%** per ADR-010 to clear min-notional on $100. Daily-loss breaker **12%** per ADR-028 (raised from 5%: at a 10% per-trade cap a 5% daily limit tripped on the *first* full loss, so it measured one trade rather than a day — this **allows more** daily loss; a coherence fix, not a tightening). Pre-live checklist must restore ≤2% before `TRADING_MODE=LIVE`.
- **Units are a live trap.** `max_risk_per_trade` is a **fraction** (`0.10`); `max_daily_loss_pct`, `max_position_size_pct`, `max_total_exposure_pct` are **percents** (`12.0`, `10.0`, `80.0`). Comparing across them without normalizing produces a check that silently never fires. This shipped once.
- **Four deliberate steps to LIVE.** `BYBIT_TESTNET` selects the *price source*. `PAPER_TRADING_MODE` / `TRADING_MODE` select whether *orders are simulated*. Real money needs all of: (1) `PAPER_TRADING_MODE=false`, (2) `TRADING_MODE=LIVE`, (3) mainnet keys with trade permissions, (4) `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` (engine refuses to boot without it).
- **Auto-trader is ARMED.** Compose default is `AUTO_TRADING_ENABLED=false`, but the operator override in `.env` is `true`. The loop fires once the kill-switch file is absent.
- **Kill switch.** Path `safety/EMERGENCY_STOP` (host) / `/app/safety/EMERGENCY_STOP` (container), dir-to-dir bind mount. Pause: `touch safety/EMERGENCY_STOP` or `POST /api/portfolio/emergency-stop`. **Resume takes two steps** — `rm safety/EMERGENCY_STOP` **then** `POST /api/trading/start` (or restart the service). A file-triggered halt sets `is_running=False` and exits the loop; it does **not** auto-restart. Only the *risk* kill-switch (equity/streak) keeps looping and auto-resumes. Full stop: `POST /api/trading/auto/stop`.
- **Validated symbols: BTC, ETH, SOL, BNB, ADA.** XRP/DOGE excluded by paper-trading data — no silent re-add. market-data ingests a wider 14-symbol universe for research; trading-engine still restricts position-taking to those 5.
- **Never commit `.env`** (gitignored). Secrets via env vars or Vault. Testnet keys only in repo. Never run `git clean -fdx` against the working tree.

## 6. Commands

Use `docker-compose.unified.yml` — plain `docker-compose.yml` is **incomplete** (missing postgres/timescaledb/redis/rabbitmq) and disagrees on values.

```
docker compose -f docker-compose.unified.yml up -d
docker compose -f docker-compose.unified.yml logs -f <service>
docker compose -f docker-compose.unified.yml down
```

Tests — see `.claude/rules/testing.md`, which loads automatically when you touch test files. Short version: always `--no-cov`; trading-engine host runs are cwd-sensitive; api-gateway tests must run in-container.

Scripts at repo root: `health_check.sh`, `monitor_paper_trading.sh`, `check_services.sh`, `build-all.sh`.

REST: gateway routes are `/api/<domain>/<resource>` — **no `v1` prefix** despite older docs. Domains: `portfolio`, `trading`, `risk`, `market`, `analysis`, `ml`, `sentiment`, `dashboard`, `performance`. Live surface: `http://localhost:8000/openapi.json`.

## 7. Verification standards

**Never declare a feature "working end-to-end" on an HTTP 200 alone.** Real proof needs all four:

1. Live exchange URL visible in service logs (not testnet)
2. A notification actually received downstream (Telegram/email arriving — not `sent: True`)
3. A DB row persisted (paste the `SELECT` result)
4. Any service whose config just changed was **restarted**

**Stale in-memory state is the most common false pass.** `/verify-stack` encodes this; use it before any "shipped" claim.

## 8. How to work here

- **Search rule.** Before searching for anything non-trivial — code, docs, config, a prior decision, an integration option — run `/graphify` first, read the audit, *then* pick a targeted tool (serena for internal symbols, context7 for library docs, grep, web). **Skip only** for exact lookups where the path/symbol/string is already known and one call resolves it. When in doubt, graphify.
- **GSD workflow.** Start file-changing work through a GSD command so planning artifacts stay in sync: `/gsd-quick` (small fixes), `/gsd-debug` (investigation), `/gsd-execute-phase` (planned work). Don't edit outside a GSD workflow unless explicitly told to bypass.
- **Parallel agents for broad exploration.** Dispatch real subagents; 3–5 is the practical ceiling. Do NOT use `TaskUpdate` as a stand-in — it tracks tasks, it doesn't dispatch work.
- **Confirm the git root** before writing path-sensitive files (`git rev-parse --show-toplevel`). `.github/`, `.claude/`, CI config land in the active repo, not the workspace parent.
- **Commit in logical chunks.** One concern per commit, conventional messages (`feat(service):`, `fix(service):`), branches `feature/<service>-<desc>` or `fix/<desc>`. Propose groupings and wait for approval; don't accumulate past ~10 unstaged files.
- **`progress.md`** at repo root is a running session log. Architecture decisions do **not** go there — file them as ADRs in `wiki/decisions/`.

## 9. Agents and rules

`.claude/agents/` holds 16 task-specific agents plus 33 `gsd-*` agents that are **load-bearing for the GSD workflow — do not remove them.** 43 generic personas were parked to `.claude/_parked/2026-08-03/agents/` on 2026-08-03 (restore any with `git mv`).

Purpose-built for this repo: `capital-auditor` (finds wrong account-size assumptions), `quant-skeptic` (hostile reviewer of edge claims — default verdict *no edge*), `engine-surgeon` (one localized money-code repair, test-first), `doc-archivist` (doc triage; never deletes, emits a `git mv` script), `verifier` (proves things actually work).

`.claude/rules/*.md` load **only** when you touch matching paths — `money.md`, `testing.md`, `docker-env.md`. That is why this file is short: deep guidance arrives when relevant and costs nothing otherwise.

## 10. Gotchas that have bitten before

- **TimescaleDB holds mixed testnet/mainnet history** — the flip happened mid-day **2026-04-25**. Any backtest or TA over earlier candles is polluted by testnet prices. Wipe `klines`/`tickers` for historical work; forward-going data is fine.
- **Market-data caches in TimescaleDB, not Redis** (Redis is empty). The DB *is* the cache. Prices stuck? `POST /api/v1/collect/ticker/{symbol}` on `:8002`, or wait ≤5 min for the scheduler.
- **`round(price, 2)` is catastrophic for sub-$1 assets** — it destroyed ADA precision and caused 30+ flip-flop losses (fixed in `487d1bd`). Use the symbol's tick size. 22 known offending sites remain across 7 files (PRICE-01/02).
- **GRU models stale since 2025-12-10.** Retrain before relying on predictions.
- **sentiment-analysis-service image** historically fails to build (PyPI timeouts). Retry that one alone or `--no-deps` skip it.
- **BuildKit hangs on WSL2** — `DOCKER_BUILDKIT=0 docker compose up -d --build <svc>`.
- **WSL bind-mount race** — `docker inspect` shows a `bind` mount while the path inside is empty and root-owned. Symptom: `PermissionError` writing `/app/logs`. Fix: `docker compose up -d --force-recreate <service>`.
- **Docker context must be `default`** (Unix socket), not `desktop-linux`. Check `docker context show`.
- **ML training OOMs** — BTC training gets OOM-killed at default limits. Raise `deploy.resources.limits` before retraining BTC.
- **Jan 2026 fixes** (`380a674`): SHORT enforcement, 48h max-hold, stop-loss limit-orders. Fixed an inverted R/R bug — do not regress.
- **Unrotated logs** — api-gateway 834 MB, portfolio-manager 941 MB (2026-05-20). No rotation configured.

---

## Strategic review modes (opt-in only)

Off by default. Default behavior: execute the technical task, concisely. Activate only when a message **opens with the exact trigger**. Mode ends on "exit mode" or a new technical task.

| Trigger | Behavior |
|---|---|
| `Challenge mode: <topic>` | Challenge every assumption. Break the logic, expose bias, present opposing views. Truth over comfort — but if the reasoning is sound, say so. Sycophancy and contrarianism are equally useless. |
| `Psych mode: <problem>` | Analyze the psychology behind the approach — subconscious patterns, fears, loops repeating across sessions. Frame as hypothesis, never diagnosis. |
| `Insights mode: <topic>` | 5 non-obvious, actionable insights. Philosopher *and* strategist: abstract enough to reframe, concrete enough to act on tomorrow. |
| `Limits mode: <area>` | Where am I limiting myself? Which constraints are self-created vs real? Design a concrete strategy to break the most binding one. |
| `Jobs mode: <situation>` | Steve Jobs's product instincts: ruthless prioritization, taste as forcing function, willingness to throw out 90%, leverage over effort. Specific to the situation, not generic startup advice. |
| `Trajectory mode` | Given current actions: where does this land in 3 years if nothing changes? Which mistakes compound most? What changes this week? No sugarcoating. |

**Inside any mode, the rules above still hold.** Never suggest "just remove the 2% risk cap" as a bold move. Boldness inside the rails, not against them. In Psych and Trajectory mode especially: these are readings of available evidence, not pronouncements.

## Voice

**Caveman full** by default. Drop articles, filler, pleasantries, hedging. Fragments fine. Pattern: `[thing] [action] [reason]. [next step].`

Keep in normal English: code, commits, PRs, error strings, security warnings, irreversible-action confirmations, and any multi-step sequence where fragment order risks misreading. Resume after.

Levels `lite | full | ultra` via `/caveman <level>`. Disable with "stop caveman" / "normal mode". The `caveman` plugin's SessionStart hook injects the active level — **trust the injected level over anything assumed here.**

## Session start

1. **Read the SessionStart reminders first.** MCP servers, skills, and agents drift between sessions. The injected lists are the source of truth for `/<name>` triggers and `subagent_type` values — not this file.
2. **Graphify before searching** (§8).
3. When something new is installed and you're asked to integrate it: confirm it appears in the SessionStart lists, `/graphify` its docs, then propose the CLAUDE.md edit (trigger phrase, when-to-use, conflicts) *before* writing. Hooks and automation need the `update-config` skill — memory alone cannot enforce automated behavior.

| Need | Use |
|---|---|
| Boot the stack cold | `/start-system` |
| Build a knowledge graph | `/graphify` |
| Live library docs | `mcp__context7__*` |
| Semantic code search here | `mcp__serena__*` |
| Static security scan | `mcp__plugin_semgrep_semgrep__*` |
| Backtest a strategy change | `/backtest <symbols> [--days N]` |
| Rebuild one service | `/deploy <service>` |
| Pre-completion proof | `/verify-stack`, `superpowers:verification-before-completion` |
| Bug / test failure | `superpowers:systematic-debugging` |
| Plan a multi-step feature | `superpowers:brainstorming` → `writing-plans` → `executing-plans` |
| Recurring background work | `schedule` (cron) or `loop` (in-session) |

## Deeper docs

Architecture `docs/architecture/SYSTEM_OVERVIEW.md` · Dev setup `docs/development/SETUP.md` · Live API `http://localhost:8000/openapi.json`
