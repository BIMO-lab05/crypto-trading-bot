# Phase 13: Bybit-Connector Market-Data Centralization - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-21
**Phase:** 13-Bybit-Connector Market-Data Centralization
**Areas discussed:** scope boundary, refactor target, operator friction, CI grep gate, gate target, Binance adapter, rotate_secrets.py

---

## Pre-discussion context

Phase 13 was originally "Real-Time WebSocket Push" (server `/ws/metrics` route + frontend `useWsSubscription` hook replacing 5s REST polling). Operator cancelled mid-Wave-1 execution on 2026-05-21 and rescoped the slot to bybit-connector centralization. Initial audit at commit `692c3c8` (anchored in ROADMAP §"Phase 13") found 9 in-scope code-path violations + 1 config defect + an open question about the active Binance exchange adapter.

---

## Scope boundary — which layers are in scope for the refactor?

| Option | Description | Selected |
|--------|-------------|----------|
| Services only (production runtime) | Refactor only `services/`. Leave scripts, backtesting, infra, tests untouched. Minimal scope. | |
| Services + scripts (default) | Services + `scripts/`. Operator scripts now need bybit-connector reachable. Backtesting + infra still untouched. | |
| Services + scripts + backtesting | Adds `backtesting/bybit_data_fetcher.py`. Backtests pull through bybit-connector for live-vs-backtest parity. | |
| Everything code-pathed to Bybit | Services + scripts + backtesting + tests + infra utils. Most rigorous, biggest blast radius. | ✓ |

**User's choice:** Everything code-pathed to Bybit.
**Notes:** User chose maximum scope — every Python file outside `services/bybit-connector/` that imports `pybit` or hits Bybit URLs is refactored. Implies `infrastructure/scripts/rotate_secrets.py` and `services/market-data-service/tests/test_pagination_fix.py` are in.

---

## Refactor target — which endpoint surface do bypass sites consume?

| Option | Description | Selected |
|--------|-------------|----------|
| Direct bybit-connector REST | Bypass sites call `bybit-connector:8001/api/v1/market/...` via httpx. Mirrors `market-data-service.fetcher.py`. No new caching layer. | ✓ |
| Via market-data-service intermediary | Bypass sites call `market-data:8002` which proxies + caches via TimescaleDB. Better cache locality, adds a hop. | |
| Mixed by use case | Per-site judgment: bulk historical → market-data; one-shot → bybit-connector. Risk: inconsistent. | |

**User's choice:** Direct bybit-connector REST.
**Notes:** Simplest contract, mirrors existing `BybitDataFetcher` pattern. Avoids coupling ml-prediction → market-data uptime.

---

## Operator friction — must bybit-connector container be running for scripts?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — scripts require compose stack up | Scripts fail-fast if `BYBIT_CONNECTOR_URL` unreachable. Consistent with production path. | ✓ |
| Allow `--direct-bybit` escape-hatch flag per script | Default through bybit-connector; `--direct-bybit` falls back to api.bybit.com. Allowlist site for gate. | |
| Helper that spins up bybit-connector ephemerally | Library helper launches bybit-connector via `docker run` if not already up. Highest engineering cost. | |

**User's choice:** Yes — scripts require compose stack up.
**Notes:** No escape hatches. Keeps the gate honest. Explicit error message points operator at `docker compose up bybit-connector`. Friction documented in RUNBOOK.

---

## CI grep gate — which patterns + which directories (round 1)?

| Option | Description | Selected |
|--------|-------------|----------|
| Strict everywhere except `services/bybit-connector/` | Single allowlist dir. Tests, docs, infra YAML all under the gate. Loudest enforcement. | ✓ |
| Code-only: gate `*.py` outside connector; ignore docs/yaml/markdown | Practical default. Recognizes helm/runbook URLs as documentation. | |
| Tiered: code-only + tests can hit live Bybit with `@pytest.mark.live_bybit` | Recognizes nightly-smoke tests as legitimate exception. | |

**User's choice:** Strict everywhere except `services/bybit-connector/`.
**Notes:** Initial answer. Refined in round 2 below.

---

## CI grep gate target — code only or also config/docs (round 2 follow-up)?

| Option | Description | Selected |
|--------|-------------|----------|
| Python code only (`**/*.py` outside `services/bybit-connector/`) | Gate trips on patterns in .py files. Config YAML and markdown docs that legitimately reference Bybit URLs for bybit-connector's own config don't trip. | ✓ |
| All files, with explicit allowlist for helm/k8s/runbook configs | Gate trips broadly; specific config paths added to allowlist. Most rigorous, more maintenance. | |
| All files, no allowlist — force every helm/doc reference through env-var indirection | Heaviest churn; literal URLs removed from entire repo. | |

**User's choice:** Python code only.
**Notes:** Refined the round-1 "strict" answer — the spirit is no-code-bypass, not no-mention. Helm values and runbook docs that LEGITIMATELY reference Bybit URLs for bybit-connector's own provisioning are documentation, not bypass.

---

## Binance adapter — `services/trading-engine/app/exchanges/binance.py` is active despite "Bybit-first" rule

| Option | Description | Selected |
|--------|-------------|----------|
| Out of scope for Phase 13 — flag for separate audit | Phase is market-data, not exchange-routing. Queue Binance question as backlog. | |
| Drop / archive within Phase 13 | Move to `_archive_exchanges/` similar to LSTM archival. Single commit, low risk. | |
| Investigate first — researcher determines if dead or live, then decide | Adds research subtask; defers actual decision to evidence. | |
| Other (free-text) | "i will not use binance just bybit " | ✓ |

**User's choice:** Free-text: "i will not use binance just bybit"
**Notes:** Interpreted as drop/archive within Phase 13. Operator policy: Bybit-only. Phase 13 archives Binance adapter so the codebase matches the policy. Touches `services/trading-engine/app/exchanges/binance.py` + `factory.py` + `__init__.py` + `tests/test_multi_exchange.py`.

---

## rotate_secrets.py — auth utility, not market-data; in scope?

| Option | Description | Selected |
|--------|-------------|----------|
| In scope — refactor to bybit-connector `/api/v1/account/balance` ping | User's full-scope answer earlier implies yes. Consistent gate enforcement. | ✓ |
| Out of scope — auth utility; explicit allowlist for this one file | Phase boundary is market-data. Auth is different concern. | |

**User's choice:** In scope.
**Notes:** Consistent with the "no escape hatches" pattern. Even though it's an auth ping (not market-data), refactoring keeps the gate clean and avoids the documented-exception-becomes-loophole anti-pattern.

---

## Claude's Discretion

- Refactor sequencing across services / scripts / backtesting / infra → planner waves
- Tape-mode fixture coverage gaps (orderbook tape data exists?) → researcher
- Whether bybit-connector needs new REST endpoints → likely no; planner confirms
- Wave grouping for parallel execution → planner
- Specific test patterns per refactored consumer → planner / executor

## Deferred Ideas

- WS-01..04 original phase 13 scope (server `/ws/metrics` push + `useWsSubscription` hook) — rejected by operator 2026-05-21; v2 candidate at earliest
- Trading-engine order placement centralization (`bybit_adapter.py` audit) — separate phase
- INTEGRATIONS.md codebase-map refresh (stale claim on market-data WS line 231) — rolled into phase 13 close
- Sentiment service's cryptocompare news fetch — sentiment ≠ market-data; future policy decision
- `tier1_monitor.py` CoinGecko cross-source divergence — NEVER migrate; deliberate non-Bybit safety guard
