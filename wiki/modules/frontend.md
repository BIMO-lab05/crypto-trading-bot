---
type: module
path: "frontend/"
status: active
language: typescript
port: 3000
purpose: "React 18 + Vite dashboard for the trading stack"
maintainer: ""
linked_issues: []
depends_on: [api-gateway]
used_by: []
tags: [module, frontend]
created: 2026-05-05
updated: 2026-07-30
---

# frontend

React 18 + Vite, port `3000`. All backend traffic goes through [[api-gateway]] (`:8000`, `/api/<domain>/...` — no `/v1/`). Pages: dashboard, performance, portfolio, settings (plus phase/tournament views). Components in `src/components/`; PriceChart is React + Recharts with 24h history (integrated Nov 2025).

## 2026-07-28 fix campaign (frontend leg)

- **TileState pattern** added — dashboard tiles now have explicit error / empty / loading states instead of rendering blank or stale data.
- **⌘K command-palette 404s fixed** — palette entries pointed at routes that didn't exist.
- **Hot-path `console.log` removal** — logging stripped from render-critical paths.
- API/UX fixes rode along with the backend accounting overhaul (see [[../decisions/ADR-018-paper-engine-accounting-overhaul|ADR-018]] era work; source: `FIXES_2026-07-28_COMPREHENSIVE.md`).

## Load-bearing gaps

- **No login flow.** Auth is open in local paper mode ([[../decisions/ADR-022-mode-gated-api-auth|ADR-022]]) so the dashboard works today, but LIVE mode enforces auth — **a login UI must exist before any LIVE flip** (operator backlog OP-11; also in [[../hot|hot.md]]).
- **Accessibility debt** (audit 2026-05-02, archived in `docs/archive/audits/`): charts invisible to screen readers, primary CTA contrast 2.43:1, unlabeled Settings inputs. Re-check alongside the login work.
- Performance dashboards render numbers from [[risk-metrics-service]], which still uses insufficient-data fallbacks — treat displayed Sharpe/VaR as placeholders until returns ingestion is wired.

## Related

- [[api-gateway]] — sole backend entry point
- [[risk-metrics-service]] — performance/risk numbers consumed via gateway
- [[../concepts/Trading-Mode-Flags]] — why missing login blocks LIVE
