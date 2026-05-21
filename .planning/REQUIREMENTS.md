# Requirements: Crypto Trading Bot — v1.2 Polish & Real-Time

**Defined:** 2026-05-18
**Milestone:** v1.2 Polish & Real-Time
**Core Value:** The bot must never lose money it wasn't authorized to risk; every "edge" claim must be backed by DSR/CPCV evidence on returns, not raw R² on price levels.

## v1.2 Requirements

Requirements for this milestone. Each maps to exactly one roadmap phase.

### Bybit-Connector Market-Data Centralization (BC)

Make `services/bybit-connector/` the sole Bybit-facing service in the codebase. Audit identifies every direct Bybit API call (`pybit` imports, hardcoded `api.bybit.com` / `wss://stream.bybit` URLs) and alternate market-data source (CoinGecko, etc.) outside the connector; refactor each hit to consume bybit-connector REST endpoints. CI grep gate locks the new contract; RUNBOOK documents the chain.

<!-- Requirement IDs (BC-NN) populated by `/gsd-discuss-phase 13`. Initial audit landed in ROADMAP §"Phase 13" detail block on 2026-05-21. -->

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
| BC-NN (TBD) | Phase 13 | Pending (populated by `/gsd-discuss-phase 13`) |
| MOBILE-01 | Phase 14 | Pending |
| MOBILE-02 | Phase 14 | Pending |
| MOBILE-03 | Phase 14 | Pending |
| TOOL-01 | Phase 15 | Pending |
| TOOL-02 | Phase 15 | Pending |
| TOOL-03 | Phase 15 | Pending |
| WS-01..04 | — (rescoped, deferred to v2) | Deferred |

**Coverage:**
- v1.2 requirements (post-2026-05-21 rescope): 6 hard + BC-NN (TBD count, Phase 13)
- Mapped to phases: BC=Phase 13, MOBILE-01..03=Phase 14, TOOL-01..03=Phase 15
- Deferred: WS-01..04 (originally Phase 13, rescoped 2026-05-21)
- Unmapped: 0

---
*Requirements defined: 2026-05-18*
*Last updated: 2026-05-21 — Phase 13 repurposed to bybit-connector market-data centralization; WS-01..04 deferred to v2.*
