# Crypto Trading Bot

Autonomous Bybit crypto trading bot. 11 Python microservices + React frontend. **Paper-trading mode** (no real orders). Market data feeds from **Bybit mainnet** (`BYBIT_TESTNET=false`) for real prices; orders are simulated internally via `PAPER_TRADING_MODE=true`. Last active Jan 2026 — currently resuming after dormancy.

## Stack

- **Python 3.12** + FastAPI + asyncio per service. **React 18 + Vite** frontend.
- **TimescaleDB** (candles), **PostgreSQL** (app state), **Redis** (cache), **RabbitMQ** (events).
- **Docker Compose** for local. Kubernetes manifests + Helm in `infrastructure/` for prod.
- **ML**: 16 GRU price-prediction models (avg R²=0.92). Replaced LSTM in late 2025.

## Services (`services/<name>/`)

| Service | Port | Purpose |
|---|---|---|
| api-gateway | 8000 | Frontend → backend routing, auth |
| bybit-connector | 8001 | Bybit REST + WebSocket wrapper |
| market-data-service | 8002 | Candle ingest → TimescaleDB |
| portfolio-manager | 8003 | Positions, balances, P&L |
| technical-analysis | 8004 | TA indicators + GRU inference + signal aggregator |
| trading-engine | 8005 | Strategy + risk + order execution |
| notification-service | 8006 | Telegram + email alerts |
| ml-prediction-service | 8007 | Standalone ML inference endpoints |
| sentiment-analysis-service | 8008 | News / social sentiment |
| risk-metrics-service | 8009 | Risk dashboards |
| ml-retraining-service | — | Cron-driven GRU retrain (no HTTP) |

Frontend `:3000`. Prometheus `:9090`. Grafana `:3001`.

## Commands

Stack up/down (use `docker-compose.unified.yml` — `docker-compose.yml` is incomplete, missing DBs):
```
docker compose -f docker-compose.unified.yml up -d
docker compose -f docker-compose.unified.yml logs -f <service>
docker compose -f docker-compose.unified.yml down
```

Tests:
```
pytest tests/                       # repo-level integration + e2e
pytest services/<svc>/tests/        # service unit tests
pytest --cov=services --cov-report=term
```

Health: every service exposes `GET /health` and `GET /ready`.

Useful scripts at repo root: `health_check.sh`, `monitor_paper_trading.sh`, `check_services.sh`, `build-all.sh`.

## Project rules (load-bearing)

- **Search rule (mandatory, always-on):** any time I'm about to *search* for something — code, docs, config, concept, prior decision, library, integration option — the **first** action is `/graphify` (skill: `graphify`) over the relevant input. Build graph, read audit, then pick targeted tool (serena / context7 / grep / web) informed by what graphify surfaced. Applies to every session, every search, no exceptions outside the explicit skip below. Skipping = regression, self-correct.
  - **Skip allowed only for:** trivially exact lookups where path/symbol/string is already known (user said "open file X" or "grep for literal Y") and one-shot tool call resolves it. When in doubt, graphify.
- **Risk caps are wired into trading-engine**: max 2% capital per trade, 5% daily-loss circuit-breaker. Don't relax without explicit approval.
- **Two independent flags** — don't confuse them: `BYBIT_TESTNET` selects price source (testnet=fake prices, mainnet=real). `PAPER_TRADING_MODE` / `TRADING_MODE` selects whether orders are simulated. Current state: mainnet prices + simulated orders. Real-money trading requires `PAPER_TRADING_MODE=false` *and* `TRADING_MODE=LIVE` *and* mainnet API keys with trading permissions — three deliberate steps.
- **Validated symbols**: BTC, ETH, SOL, BNB, ADA (5 active as of 2026-05-03). XRP / DOGE remain excluded by paper-trading data — do not silently re-add. BTC + ETH re-added 2026-05-03 per operator request; trading-engine `trading_symbols` already had them, market-data `default_symbols` did not until this date.
- **Never commit `.env`** (already gitignored). Secrets via env vars or Vault. Bybit testnet keys only in repo.
- **REST**: gateway routes are `/api/<domain>/<resource>` (no `v1` prefix despite older docs). Domains: `portfolio`, `trading`, `risk`, `market`, `analysis`, `ml`, `sentiment`, `dashboard`, `performance`. See `http://localhost:8000/openapi.json` for the live surface. Async handlers throughout.
- **Commits**: conventional (`feat(service): ...`, `fix(service): ...`); branches `feature/<service>-<desc>`, `fix/<desc>`.

## Verification standards

- **Don't declare features "working end-to-end" on curl/HTTP 200 alone.** Real proof needs: live exchange URL visible in service logs (not testnet), at least one notification actually received downstream (Telegram/email arriving, not just `sent: True`), the relevant DB row persisted (paste the `SELECT` result), and any service whose config just changed restarted.
- **Stale in-memory state is the most common false-pass.** When config changes, restart the service before re-running integration tests — otherwise tests pass against the old in-memory copy.
- The `/verify-stack` skill encodes this checklist; use it before any "shipped" claim.

## Workflow

- **Parallel agents for broad exploration.** When asked to "analyze the project" or audit across services, dispatch real `Task` subagents in parallel. Do NOT use `TaskUpdate` as a stand-in — it tracks tasks, it doesn't dispatch work.
- **Confirm the git root before writing path-sensitive files.** Run `git rev-parse --show-toplevel` if there's any ambiguity. Workflow files (`.github/workflows/`), Claude config (`.claude/`), CI config, etc. land in the active git repo, not the workspace parent.
- **Commit in logical chunks.** One concern per commit; don't accumulate past ~10 unstaged files; propose groupings before each commit and wait for approval.

## Environment

- **WSL2 + Docker Desktop**: Docker context must be `default` (Unix socket), not `desktop-linux` (Windows named pipe). Verify with `docker context show`.
- **BuildKit hangs on WSL2** are common — `DOCKER_BUILDKIT=0 docker compose up -d --build <svc>` works around stalls.
- **WSL bind-mount race**: `docker inspect` can show a `bind` mount while the path inside the container is empty + root-owned (the mount silently failed at create time). Symptom: `PermissionError` writing to `/app/logs`. Fix: `docker compose up -d --force-recreate <service>`.
- **ML training memory**: BTC training has been OOM-killed at default container limits. Bump memory in the relevant compose `deploy.resources.limits` block before retraining BTC.

## Gotchas

- **Two compose files**: `docker-compose.unified.yml` is canonical (16 services incl. DBs). `docker-compose.yml` is missing postgres/timescaledb/redis/rabbitmq.
- **Sentiment-analysis-service image** has historically failed to build via pip (PyPI read timeouts). Other 10 service images cache fine. If a full `compose up` fails, retry the build of just that one or `--no-deps` skip it.
- **GRU models are 4+ months stale** (trained Dec 10, 2025). Retrain before relying on predictions.
- **`.claude/agents/` ships 54 agent personas** (api-designer, code-reviewer, security-engineer, etc.) and `.claude/hooks/` provides an intelligent-router that auto-suggests an agent for each prompt. See `.claude/hooks/README.md` for the install + customize guide. Built-in subagents (Explore, Plan, general-purpose) still work alongside them.
- **Jan 2026 fixes** (commit `380a674`): SHORT enforcement, 48h max-hold, stop-loss limit-orders. These addressed an inverted R/R ratio bug. Don't regress them.
- **TimescaleDB has mixed testnet/mainnet history** as of 2026-04-25 (the flip from testnet→mainnet was mid-day). Any backtest or TA over candles from before that point will be polluted by testnet prices. Wipe `klines` / `tickers` tables if running historical analysis; live forward-going data is fine.
- **Market-data-service caches in TimescaleDB**, not Redis (Redis was empty in testing). The DB *is* the cache. If prices look stuck, hit `POST /api/v1/collect/ticker/{symbol}` on market-data-service (port 8002) to force-refresh, or wait up to 5 min for the scheduler.
- **`progress.md`** at repo root is the running session log — append at end of session; don't put architecture decisions there (those go in `docs/architecture/DECISIONS.md`).

## Deeper docs

- Architecture: `docs/architecture/SYSTEM_OVERVIEW.md`
- Dev setup: `docs/development/SETUP.md`
- Live API spec: `http://localhost:8000/openapi.json` (gateway exposes it directly; the
  `docs/api/openapi.yaml` snapshot was removed during the 2026-04-26 cleanup since it
  drifted from the live surface)

---

## Strategic review modes (opt-in only)

These modes are **off by default**. Default behavior remains: execute the technical task asked, concisely. Activate a mode only when I open a message with the exact trigger phrase. Mode ends when I say "exit mode" or start a new technical task.

### Trigger: "Challenge mode: <topic>"
Challenge every assumption I have about the topic. Break my logic, expose cognitive biases, present opposing views, suggest better frameworks. No agreement-for-its-own-sake. Truth over comfort. If my reasoning is sound, say so — sycophancy and contrarianism are equally useless.

### Trigger: "Psych mode: <problem>"
Analyze the psychology behind my approach. What subconscious patterns might be driving me? What fears could be influencing decisions? What loops keep repeating across sessions/decisions in this project? Stay grounded — flag this as hypothesis, not diagnosis.

### Trigger: "Insights mode: <topic>"
Extract 5 non-obvious insights about the topic. Focus on depth, not surface-level knowledge. Make each one actionable. Think like a philosopher *and* a strategist — abstract enough to reframe, concrete enough to act on tomorrow.

### Trigger: "Limits mode: <area>"
Identify where I'm limiting myself in this area. What patterns hold me back? What constraints are self-created vs. real? What's the breakthrough move? Design a concrete strategy to break the most binding constraint.

### Trigger: "Jobs mode: <situation>"
Show me how someone with Steve Jobs's product instincts would attack this situation: ruthless prioritization, taste as a forcing function, willingness to throw out 90% of work, leverage over effort. Make it unconventional and specific to the situation, not generic startup advice.

### Trigger: "Trajectory mode"
Based on my current actions and decisions visible in this project: where am I likely to be in 3 years if nothing changes? Which mistakes will compound the most? What should I change this week? Direct. No sugarcoating, no hedging into mush.

### Notes on these modes

- **Scope discipline.** Inside a strategic mode, focus on the question; don't pivot back to writing code unless I ask. Outside these triggers, stay technical.
- **Project context applies.** When discussing this codebase under any mode, the constraints in "Project rules" still hold — don't suggest "just remove the 2% risk cap" as a "bold move." Boldness inside the rails, not against them.
- **Hypothesis, not verdict.** Especially in Psych mode and Trajectory mode, I'm a partial signal at best. Frame inferences as readings of the available evidence, not pronouncements about who I am.

---

## Session bootstrap (run every new session)

These steps are **mandatory at session start**, before answering the first non-trivial question. Skip only for one-line questions that need no project context.

### 1. Caveman mode is the default voice

- Speak in **caveman full** style by default: drop articles (a/an/the), filler (just/really/basically), pleasantries (sure/of course), hedging. Fragments OK. Pattern: `[thing] [action] [reason]. [next step].`
- Keep technical substance, error strings, code, commits, PRs, security warnings, and irreversible-action confirmations in **normal English** — caveman is for prose, not artifacts.
- Auto-clarity: drop caveman for multi-step destructive sequences and anywhere fragment order risks misread. Resume after.
- Levels: `lite | full | ultra`. Default `full`. Switch via `/caveman lite|full|ultra`. Disable with "stop caveman" / "normal mode" — persists till changed.
- The `caveman` plugin's SessionStart hook injects the active level. Trust the injected level over assumptions.

### 2. Query the knowledge graph first

- **Search rule (mandatory):** any time I'm about to *search* for something — code, docs, config, concept, prior decision, integration option — the **first** step is `/graphify` (or invoke the `graphify` skill) over the relevant input set. Build the graph, read the audit, then choose the targeted tool (serena / context7 / grep / web) informed by what graphify surfaced. Do not jump straight to grep/WebSearch for non-trivial queries.
  - **Skip allowed only for:** trivially exact lookups where the path/symbol/string is already known (e.g. user said "open file X" or "grep for literal Y") and a single one-shot tool call resolves it. When in doubt, graphify.
- Before designing or recommending how to wire in a new MCP server, skill, agent, or plugin, run `/graphify` over the relevant docs/configs to build a knowledge graph of the option space.
- Use the resulting graph + audit report to pick the *best* integration pattern (where it slots into CLAUDE.md, which trigger phrases to wire up, which existing rules it conflicts with) instead of guessing from the tool name.
- After graphify narrows the target: for library/SDK questions (Pinecone, Mintlify, Wix, Figma, Anthropic SDK, Astronomer, etc.) prefer **context7** (`mcp__context7__resolve-library-id` → `query-docs`) over web search — it pulls current docs.
- After graphify narrows the target: for project-internal symbol/file lookups prefer **serena** (`find_symbol`, `find_referencing_symbols`, `search_for_pattern`) over raw grep when the question is semantic.

### 3. Discover what's actually installed

- The set of MCP servers, skills, and agents drifts between sessions. **Read the SessionStart system reminders first** — they enumerate the live surface (deferred tools list, available skills list, MCP server instructions). Do not assume from this CLAUDE.md alone.
- Skill list is the source of truth for `/<name>` triggers. Agent list (in the Agent tool description) is the source of truth for `subagent_type`.
- When the user adds a new MCP server / skill / agent and asks me to integrate it: graphify the new component's docs, then propose the CLAUDE.md edit (trigger phrase, when-to-use, conflicts) before writing.

### 4. Routing cheatsheet

| Need | Use |
|---|---|
| Caveman voice toggle | `/caveman lite\|full\|ultra`, "stop caveman" |
| Build knowledge graph from input | `/graphify` (skill: `graphify`) |
| Live library docs | `mcp__context7__*` |
| Semantic code search in this repo | `mcp__serena__*` |
| Browser-driven UI test | `mcp__plugin_playwright_playwright__*` or skill `document-skills:webapp-testing` |
| Static security scan | `mcp__plugin_semgrep_semgrep__*` (already installed; SessionStart confirms `Semgrep 1.161.0`) |
| Vector store ops | `mcp__plugin_pinecone_pinecone__*` + skills `pinecone:*` |
| Slack ops | `mcp__plugin_slack_slack__*` + skills `slack:*` |
| Figma read/write | `mcp__plugin_figma_figma__*` + skills `figma:*` |
| Plan + execute multi-step feature | skills `superpowers:brainstorming` → `superpowers:writing-plans` → `superpowers:executing-plans` |
| Bug / test failure | skill `superpowers:systematic-debugging` |
| Pre-completion proof | skill `superpowers:verification-before-completion` (pairs with this repo's `/verify-stack` rule) |
| Code review on diff | skill `code-review:code-review` or `pr-review-toolkit:review-pr` |
| Recurring or scheduled background work | skill `schedule` (cron) or `loop` (in-session) |
| Compress this CLAUDE.md / memory file | skill `caveman:compress` |
| Subagent for broad parallel exploration | `Agent` tool with `subagent_type: Explore` (or `general-purpose` / `feature-dev:code-explorer`) |
| Surgical 1-2 file edit by subagent | `caveman:cavecrew-builder` |
| Read-only code locator subagent | `caveman:cavecrew-investigator` |
| Diff/PR review subagent | `caveman:cavecrew-reviewer` or `pr-review-toolkit:*` |

### 5. Adding a new MCP / skill / agent later

When I install something new and tell you about it:

1. Confirm it appears in the SessionStart deferred-tools or skills list — if not, the install didn't take.
2. `/graphify` its docs (or `mcp__context7__query-docs` for the underlying library) to map capabilities.
3. Decide: does it deserve a row in the routing cheatsheet above? A trigger phrase? A conflict callout against existing project rules?
4. Edit *this* file (`crypto-trading-bot/CLAUDE.md`) to record it. Keep entries short — link out for detail.
5. If it's a hook/automation that should fire on events (PreToolUse, Stop, etc.), use the `update-config` skill — memory alone can't enforce automated behavior.

### 6. Don't drift

- This bootstrap section is load-bearing. If a future session shows me speaking in normal English unprompted, or skipping graphify before integrating a new feature, treat that as a regression and self-correct.
- The strategic-review modes above remain opt-in only; caveman voice is orthogonal to them and applies inside those modes too (unless I explicitly want florid prose for a Jobs/Trajectory answer — then I'll say so).