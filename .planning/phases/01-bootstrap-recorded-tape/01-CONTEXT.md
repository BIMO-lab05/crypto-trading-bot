# Phase 1: Bootstrap & Recorded Tape - Context

**Gathered:** 2026-05-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Reproducible bring-up + deterministic exchange-data fixtures. A new operator clones the repo into a fresh tmp directory, runs `bootstrap.sh` against an empty `.env`, and ends up with all 15 services healthy, idling against recorded Bybit data — no live-API dependence in the deterministic path. Live-data smoke runs in a separate nightly CI workflow.

**In scope:**
- `bootstrap.sh` provisioning (`.env` template, compose up, health probe)
- Recorded-tape fixtures (klines + ticker, 5 symbols × 7 days)
- Tape capture script + replay loader inside `bybit-connector`
- `MARKET_DATA_SOURCE=tape|live` selector
- Live-smoke CI workflow scaffold

**Out of scope (other phases):**
- pytest+testcontainers integration suite — Phase 2 (INFRA-01)
- RUNBOOK.md — Phase 2 (INFRA-05)
- Checkpointed iteration harness — Phase 2 (INFRA-04)
- Tournament harness — Phase 3
- Forward-paper-test of opt-in features — Phase 5
- Orderbook + funding tape capture — deferred until Phase 5 forward-tests `PREFER_MAKER_ORDERS` / `ENABLE_FUNDING_GATE`

</domain>

<decisions>
## Implementation Decisions

### Tape format & coverage
- **D-01:** Storage format = JSONL per `(feed, symbol)` — one file per pair (e.g. `tests/fixtures/tape/klines/SOLUSDT.jsonl`). Human-greppable, diffable, matches Bybit REST/WS payload shape.
- **D-02:** Feeds in v1 tape = **klines + ticker only**. Orderbook L2 + funding-rate are deferred — their consumers (`PREFER_MAKER_ORDERS`, `ENABLE_FUNDING_GATE`) default off and forward-test in Phase 5.
- **D-03:** Symbol/window scope = **5 validated symbols × 7 days** (BTC, ETH, SOL, BNB, ADA). 5m kline cadence + ticker snapshots. Target tape size <50 MB so it stays in-repo.
- **D-04:** Storage location = `tests/fixtures/tape/` checked into git. No git-lfs in v1; revisit if size grows.
- **D-05:** Capture method = committed script `scripts/tape/capture_bybit.py` that hits live Bybit mainnet REST (`/v5/market/kline`, `/v5/market/tickers`) and writes JSONL. Operator runs it manually, commits output. Reproducible from script + window timestamps.
- **D-06:** Refresh cadence = **manual on demand**. No nightly auto-refresh (would break replay determinism for older test runs). Tape SHA tracked in git.
- **D-07:** Schema versioning = first line of every JSONL file is a header object `{"tape_version": 1, "captured_at": "...", "source": "bybit-mainnet", "symbol": "...", "feed": "..."}`. Loader rejects mismatched `tape_version`.
- **D-08:** Clock handling = **replay timestamps as-is, no clock mock**. Loader emits original captured `timestamp` field; services see real wall-clock for `now()` but candle timestamps are pinned. Avoids invasive time-injection seam across 15 services.

### Healthy-idle definition
- **D-09:** Idle bar at bootstrap exit = **all 15 services /health=200 within timeout**. No paper-trade round-trip asserted; that lives in Phase 2 integration tests.
- **D-10:** Flag state at bootstrap exit:
  - `PAPER_TRADING_MODE=true`
  - `TRADING_MODE=PAPER`
  - `AUTO_TRADING_ENABLED=true` (matches operator override per `crypto-trading-bot/CLAUDE.md` § Project rules)
  - `ENABLE_ML_PREDICTIONS=false`
  - `ENABLE_SENTIMENT_ANALYSIS=false`
- **D-11:** **bootstrap.sh touches `EMERGENCY_STOP` at repo root by default.** Auto-trader is armed but loop holds at STEP-0 until operator removes the file. Honors "operator must explicitly arm anything" stance while staying compatible with the live `.env` override.
- **D-12:** Health probe = reuse existing `health_check.sh` pattern (curl `/health` per service port with retry/backoff, ~120s timeout). Don't introduce a new probe stack in this phase.
- **D-13:** Failure behavior = **fail loud, leave stack up**. `bootstrap.sh` exits non-zero, prints last 50 log lines per failed service, leaves containers running for `docker logs` post-mortem. **No auto-teardown, no auto-retry** (auto-retry is Goodhart trap per project rules).

### Live-vs-recorded selector
- **D-14:** Selector = single env var **`MARKET_DATA_SOURCE=tape|live`** in `.env`. Default `tape` for fresh bootstrap.
- **D-15:** Replay logic lives **inside `bybit-connector`** behind the flag. `live` branch hits real REST/WS; `tape` branch streams JSONL fixtures while preserving the same downstream contract (HTTP responses + WS frames). Downstream services (`market-data-service`, etc.) don't know they're on tape.
- **D-16:** Live-smoke path = **same compose, `MARKET_DATA_SOURCE=live`, separate nightly CI workflow** (`.github/workflows/live-smoke.yml`). Failure notifies but does NOT block the deterministic CI lane. Allowed to be flaky per requirements.
- **D-17:** Tape-mode credentials = **bypass auth check**. When `MARKET_DATA_SOURCE=tape`, `bybit-connector` skips `BYBIT_API_KEY`/`BYBIT_API_SECRET` validation. Bootstrap can run with empty creds — removes the #1 fresh-clone friction.

### Claude's Discretion
- Feed selection within "Tape format & coverage" (user delegated): chose **klines + ticker only** for v1 to keep tape lean and align with default-on consumers. Orderbook + funding can be additive without breaking the v1 schema.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project context
- `.planning/PROJECT.md` — milestone scope, validated capability, key decisions, out-of-scope guardrails
- `.planning/REQUIREMENTS.md` — INFRA-02 + INFRA-03 acceptance criteria
- `.planning/ROADMAP.md` § "Phase 1: Bootstrap & Recorded Tape" — goal, depends-on, success criteria

### Operator-facing rules (load-bearing)
- `crypto-trading-bot/CLAUDE.md` § "Project rules (load-bearing)" — flag semantics (`PAPER_TRADING_MODE`, `TRADING_MODE`, `LIVE_TRADING_ACK`, `AUTO_TRADING_ENABLED`), EMERGENCY_STOP wiring, validated symbol set
- `crypto-trading-bot/CLAUDE.md` § "Verification standards" — no "working" claims on HTTP-200 alone; bind-mount race; restart-on-config-change rule
- `crypto-trading-bot/CLAUDE.md` § "Environment" — WSL2 Docker context (`default` vs `desktop-linux`), BuildKit hangs, bind-mount race
- `crypto-trading-bot/CLAUDE.md` § "Gotchas" — two compose files (`docker-compose.unified.yml` is canonical), TimescaleDB testnet/mainnet contamination pre-2026-04-25

### Existing assets to reuse
- `crypto-trading-bot/docker-compose.unified.yml` — canonical 15+1 service compose (NOT `docker-compose.yml` — incomplete)
- `crypto-trading-bot/health_check.sh` — health probe pattern (reuse; do not reinvent)
- `crypto-trading-bot/.env.example` — template baseline for bootstrap-generated `.env`
- `crypto-trading-bot/services/bybit-connector/` — tape-replay branch lands here
- `crypto-trading-bot/services/market-data-service/app/fetcher.py` + `scheduler.py` — downstream consumer; must not need code changes for tape mode

### V0 / safety baseline
- Memory: `project_v0_finding_2026-04-30.md` — why `ENABLE_ML_PREDICTIONS=false` is the bootstrap default
- Memory: `project_audit_2026-04-28.md` — open audit items the bootstrap path must not regress

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`health_check.sh`** at repo root — health-probe shell pattern; bootstrap should call/source rather than re-implement.
- **`docker-compose.unified.yml`** — 15+1 service definition; canonical compose (per CLAUDE.md gotcha — `docker-compose.yml` is missing DBs).
- **`.env.example`** — template starting point for bootstrap-generated `.env`.
- **`services/bybit-connector/`** — natural home for the `MARKET_DATA_SOURCE` branch + tape-replay loader (avoids new container in compose).
- **`tests/e2e/fixtures/`** + **`shared/tests/fixtures/`** — existing fixture-tree convention; `tests/fixtures/tape/` slots in alongside.
- **`build-all.sh`, `check_services.sh`, `monitor_*.sh`** — adjacent operational scripts; bootstrap.sh follows the same shell-script style.

### Established Patterns
- **Service health = `GET /health` + `GET /ready`** on each port (per CLAUDE.md § Services).
- **Conventional Commits** (`feat(service): ...`, `fix(service): ...`); branches `feature/<service>-<desc>`.
- **No `git clean -fdx` against working tree** — would delete `.env` (real keys) and uncommitted model weights.
- **Two-flag trading-mode safety:** `BYBIT_TESTNET` selects price source, `PAPER_TRADING_MODE`/`TRADING_MODE` selects whether orders simulated. Bootstrap must not re-introduce ambiguity.
- **EMERGENCY_STOP file at repo root** — RO bind-mount in trading-engine; touch to pause auto-trader loop at STEP-0.

### Integration Points
- **bootstrap.sh ↔ docker-compose.unified.yml** — bootstrap drives compose up/down; must export `MARKET_DATA_SOURCE` to compose env.
- **bootstrap.sh ↔ `.env`** — generate or copy from `.env.example`; touch `EMERGENCY_STOP` at repo root.
- **bybit-connector ↔ tape fixtures** — bind-mount `tests/fixtures/tape/` into the connector container in tape mode (read-only), or `COPY` at build time. Bind-mount preferred for fast iteration.
- **bybit-connector ↔ market-data-service** — same HTTP/WS contract on port 8001 in either mode; downstream is mode-agnostic.
- **CI (.github/workflows/) ↔ bootstrap.sh** — deterministic CI uses default tape; nightly live-smoke flips `MARKET_DATA_SOURCE=live` and runs `bootstrap.sh` + minimal trade probe.

</code_context>

<specifics>
## Specific Ideas

- "Trust no docs" applies — every bootstrap claim ("services healthy", "tape loaded") must verify against code (`file:line`) and exit-code, not log strings.
- Bootstrap-tests run against a fresh `git clone` into a tmp directory (per PROJECT.md § Constraints). `bootstrap.sh` itself must not assume anything from the working-copy environment; rely only on what the script provisions.
- WSL2 BuildKit hangs are a known friction (CLAUDE.md). bootstrap.sh should default to `DOCKER_BUILDKIT=0` on Linux/WSL2 unless the operator overrides.
- Sentiment-analysis-service image historically fails pip build (PyPI timeouts); bootstrap.sh should consider `--no-deps` retry or document the workaround inline (cross-link to RUNBOOK in Phase 2).

</specifics>

<deferred>
## Deferred Ideas

- **Orderbook L2 + funding-rate tape capture** — add in Phase 5 when forward-paper-tests for `PREFER_MAKER_ORDERS` and `ENABLE_FUNDING_GATE` need deterministic data. v1 tape schema (JSONL, `tape_version` header) is forward-compatible.
- **Speed-multiplier replay** (replay 7d in 7m) — useful for fast paper-trade tests but breaks any service comparing wall-clock to candle-time. Revisit only if Phase 2 integration tests need it.
- **git-lfs for tape** — only if v1 tape exceeds ~50 MB. Add when symbol-set or window grows.
- **Custom Python health probe** (DB connectivity + RabbitMQ queue depth) — reuse `health_check.sh` for Phase 1; promote to a richer probe if Phase 2 integration suite needs it.
- **DB migrations on bootstrap** — not asked; assume compose-managed init scripts cover v1. Revisit in Phase 2 if integration suite hits schema drift.
- **Vault dev-mode init / Telegram bot stub for bootstrap** — out of scope here; if absent in `docker-compose.unified.yml` defaults, surface in Phase 2 RUNBOOK.

</deferred>

---

*Phase: 01-bootstrap-recorded-tape*
*Context gathered: 2026-05-06*
