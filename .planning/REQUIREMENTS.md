# Requirements: Crypto Trading Bot — v1.2 Polish & Real-Time

**Defined:** 2026-05-18
**Milestone:** v1.2 Polish & Real-Time
**Core Value:** The bot must never lose money it wasn't authorized to risk; every "edge" claim must be backed by DSR/CPCV evidence on returns, not raw R² on price levels.

## v1.2 Requirements

Requirements for this milestone. Each maps to exactly one roadmap phase.

### Bybit-Connector Market-Data Centralization (BC)

Make `services/bybit-connector/` the sole Bybit-facing service in the codebase. Audit identifies every direct Bybit API call (`pybit` imports, hardcoded `api.bybit.com` / `wss://stream.bybit` URLs) and alternate market-data source (CoinGecko, etc.) outside the connector; refactor each hit to consume bybit-connector REST endpoints. CI grep gate locks the new contract; RUNBOOK documents the chain. (Requirement IDs derived from Phase 13 CONTEXT.md decisions D-01 through D-09, 2026-05-21.)

- [x] **BC-01**: Repo-wide audit produces `.planning/evidence/BC-01/bybit-bypass-audit.json` enumerating every Python file outside `services/bybit-connector/` that matches any of: `from pybit`, `import pybit`, hardcoded `https://api.bybit.com`, hardcoded `https://api-testnet.bybit.com`, hardcoded `wss://stream.bybit`. Each entry is `{file, line, kind, current_call, replacement_path}` where `kind ∈ {pybit_import, mainnet_rest_url, testnet_rest_url, wss_stream_url}`. Audit covers `services/`, `scripts/`, `backtesting/`, `tests/`, `infrastructure/scripts/`. Non-Python files (helm YAML, network policies, markdown docs) are EXCLUDED.
- [x] **BC-02**: Every BC-01 hit is refactored to consume `bybit-connector` REST surface (`http://bybit-connector:8001/api/v1/market/{ticker,kline,orderbook,recent-trade,funding-rate/history,instruments-info}` for market-data; `http://bybit-connector:8001/api/v1/account/balance` for `infrastructure/scripts/rotate_secrets.py` auth-ping). Implementation mirrors `services/market-data-service/app/fetcher.py` (httpx + `bybit_connector_retry` tenacity decorator). Standalone scripts (`scripts/collect_*.py`, `scripts/fetch_*.py`, `backtesting/bybit_data_fetcher.py`) fail-fast with `BYBIT_CONNECTOR_URL` unreachable error pointing operator at `docker compose up bybit-connector`. No `--direct-bybit` escape hatch.
- [x] **BC-03**: CI grep gate `tests/ci/test_no_bybit_bypass.py` (Python pytest) is green on `main` post-refactor and fails on any new violation in `**/*.py` outside `services/bybit-connector/`. Patterns banned: `from pybit`, `import pybit`, `https?://api\.bybit\.com`, `https?://api-testnet\.bybit\.com`, `wss?://stream\.bybit`. Test is required in `.github/workflows/` (CI workflow PR check). No allowlist entries permitted after refactor.
- [x] **BC-04**: `services/trading-engine/app/exchanges/binance.py` and references are archived per operator policy ("Bybit-only"). File moves to `_archive_exchanges/binance.py`. `services/trading-engine/app/exchanges/factory.py` BinanceExchangeAdapter import + registration removed (lines 62, 189). `services/trading-engine/app/exchanges/__init__.py` Binance exports removed (lines 23, 213, 329, 330, 513). `services/trading-engine/tests/test_multi_exchange.py` Binance test branches deleted (lines 54, 161, 165). Trading-engine boots without ImportError; multi-exchange test file either deleted or down to Bybit-only branches.
- [x] **BC-05**: `services/market-data-service/app/config.py:58` default port fixed: `bybit_connector_url: str = Field(default="http://localhost:8001")` (was `:8002`). Compose-env behavior unchanged (env overrides default); fix prevents misroute when scripts read config without compose env.
- [x] **BC-06**: `RUNBOOK.md` gains Symptom #N "Market-data stale or missing — bybit-connector chain broken" with Diagnose/Action/Verification subsections covering: (a) bybit-connector container down, (b) `BYBIT_CONNECTOR_URL` env misconfigured, (c) bybit-connector hitting Bybit-side ratelimit, (d) `MARKET_DATA_SOURCE=tape` accidentally enabled in production. Verification steps reference concrete curl commands against `http://bybit-connector:8001/api/v1/market/ticker?symbol=BTCUSDT`.
- [x] **BC-07**: Tape-replay mode preserved end-to-end. Integration test (`tests/integration/test_bybit_connector_tape_preserved.py`) asserts that with `MARKET_DATA_SOURCE=tape` enabled on `crypto-bot-bybit-connector`, every refactored consumer (ml-prediction-service orderbook handler, market-data-service fetcher, refactored scripts) receives tape data — never live. `POST /admin/tape/reset` continues to work post-refactor.

### Real-Time WebSocket (WS) — rescoped, deferred to v2

> Rescoped 2026-05-21. Phase 13 was repurposed to bybit-connector centralization; WS-01..04 deferred to a future milestone. Original requirement text preserved in commit history (see `git log -- .planning/REQUIREMENTS.md`).

### Mobile Responsive (MOBILE)

Dashboard is currently built for ≥1280px viewports. Operator increasingly checks paper-trading state from phone; horizontal-scroll-to-find-tile is the dominant pain. Scope is responsive layout only, no native app, no PWA.

- [ ] **MOBILE-01**: Viewport meta tag + responsive Tailwind tokens established (breakpoints `sm:640`, `md:768`, `lg:1024`, `xl:1280` standardized; `tailwind.config.cjs` audited for hardcoded widths). Layout audit (`scripts/audit_responsive.py` or inline grep) of every `frontend/src/components/**/*.jsx` identifies fixed-width violations; `responsive-audit.json` artifact lists each violation with file:line.
- [ ] **MOBILE-02**: Single-column reflow ≤768px implemented for: `Dashboard.jsx` grid (collapses to stacked tiles), `PathToLiveTile.jsx` (6 PREFLIGHT chip rows + 5 carry-in rows wrap to 1-col), `KeyMetricsStrip` (horizontal scroll → 2-col grid), `TournamentDashboard.jsx` (filter chips wrap, table converts to card list). No tile loses information; only layout changes.
- [ ] **MOBILE-03**: pytest-playwright Chromium smoke at iPhone SE (375×667) and iPad portrait (768×1024) viewports asserts: every dashboard tile rendered with `data-testid` visible without horizontal scroll, no element overflows `window.innerWidth`, PathToLiveTile banner state-token still visible, navigation tappable (≥44px touch targets per WCAG). Runs under `.github/workflows/dashboard-smoke.yml` matrix.

### Planning Tooling (TOOL)

Three recurring frictions from v1.0 and v1.1 retros — fix them in the tooling so they cannot regress. Pure planning-side code; no trading-engine impact.

- [ ] **TOOL-01**: `gsd-sdk query plan.validate <plan-path>` rejects one-liner content matching `/^Rule \d/`, `/^Task \d/`, `/^one-liner:\s*$/`, `/<one-line summary>/`, or empty string. Pre-commit hook (or PR-time CI step) runs validator on every `*-PLAN.md` modified in diff; commit/CI fails with explicit error pointing at the bad line. Unit tests cover all 5 rejection patterns + 1 happy path.
- [ ] **TOOL-02**: `gsd-sdk query roadmap.analyze` detects umbrella→decimal supersession: if Phase N.M's requirement set ⊇ Phase N's requirement set and Phase N.M is complete, ROADMAP.md auto-updates Phase N row to `Superseded by N.M` (status `[⊘]`). Idempotent. Output diff goes to stdout so the operator can review before commit. Wired into `/gsd-complete-milestone` workflow.
- [ ] **TOOL-03**: `/gsd-complete-milestone` workflow refuses to archive if the latest `v[X.Y]-MILESTONE-AUDIT.md` `audited_at` timestamp predates the most recent phase's `VERIFICATION.md` modification time by >1h. Error names the stale audit timestamp and the offending phase. Override flag `--accept-stale-audit` for emergency closes (documented). Test fixture replays the v1.1 13h-gap scenario and asserts refusal.

## Future Requirements

Deferred to v1.3+:

### Operator-Action Carry-Overs (no code work)

- **LIVECLOSE-01..05**: Operator execution of v1.1 closure harnesses (wall-clock-bound; harness code already shipped)
- **CIRESTORE-01..02**: First green CI runs after OP-04 GH Actions billing resolves

### ML / Tournament Expansion

- **TOURN-EXP-01**: Cross-symbol tournament expansion (XRP/AVAX) — gated on production-validation review
- **TOURN-EXP-02**: Multi-horizon production deployment (1h/4h/24h) — depends on MLGATE evidence accrual landing first
- **SENT-01..N**: Sentiment-as-filter integration — gated on T0.1.x evidence (INSUFFICIENT_DATA pending OP-02 + OP-03)
- **CLS-01..N**: Classification head + calibration

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Native mobile app (iOS/Android) | Solo operator; web dashboard sufficient. Responsive web covers phone access. |
| Full PWA (offline, installable, service worker) | Out of scope for v1.2 polish. Could revisit in v2.x. |
| Push notifications to phone (web push API) | Telegram digest already covers operator alert path. |
| Client-side state-management library swap (Redux/Zustand) | React-query already adequate; WS frames update same cache keys. |
| CSS framework swap (Tailwind → other) | Tailwind locked; mobile work uses existing tokens. |
| WS authentication via JWT refresh flow | v1.2 uses existing bearer token; refresh flow out of scope. |
| Multi-tenant WS subscriptions (per-user channels) | Solo operator; single-tenant scope. |
| `gsd-sdk` rewrite | Tooling fixes additive; no refactor. |
| Live-trading enablement | Same gates as v1.1 still apply (4-flag flip + pre-LIVE checklist). v1.2 does not flip LIVE. |
| Real-money order routing | Paper-mode boundary remains in force. |
| New trading symbols beyond BTC/ETH/SOL/BNB/ADA | Validated symbol set locked. |
| K8s deployment | docker-compose only for v1.x. |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| BC-01 | Phase 13 | Complete |
| BC-02 | Phase 13 | Complete |
| BC-03 | Phase 13 | Complete |
| BC-04 | Phase 13 | Complete |
| BC-05 | Phase 13 | Complete |
| BC-06 | Phase 13 | Complete |
| BC-07 | Phase 13 | Complete |
| MOBILE-01 | Phase 14 | Pending |
| MOBILE-02 | Phase 14 | Pending |
| MOBILE-03 | Phase 14 | Pending |
| TOOL-01 | Phase 15 | Pending |
| TOOL-02 | Phase 15 | Pending |
| TOOL-03 | Phase 15 | Pending |
| WS-01..04 | — (rescoped, deferred to v2) | Deferred |

**Coverage:**
- v1.2 requirements (post-2026-05-21 rescope): 13 total (BC-01..07 + MOBILE-01..03 + TOOL-01..03)
- Mapped to phases: BC-01..07 = Phase 13; MOBILE-01..03 = Phase 14; TOOL-01..03 = Phase 15
- Deferred: WS-01..04 (originally Phase 13, rescoped 2026-05-21)
- Unmapped: 0

---
*Requirements defined: 2026-05-18*
*Last updated: 2026-05-21 — Phase 13 BC-01..07 derived from CONTEXT.md decisions D-01..D-09.*
