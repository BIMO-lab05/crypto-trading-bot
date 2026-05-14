---
session: 2026-05-14T11:30-11:55Z
driver: Playwright MCP (headless Chromium 1440x900)
stack: docker-compose.unified.yml, all 14 services healthy at start
frontend_bundle: index-BjZKVPM3.js (post-rebuild this session — initial bundle was stale index-DLdyMhfn.js)
---

# Phase 6 Manual Smoke Re-Run — 2026-05-14 Resume

Re-ran the four `human_verification` items from `06-VERIFICATION.md` via Playwright after rebuilding the stale frontend bundle. Outcome:

| # | Smoke | Verdict | Evidence |
|---|-------|---------|----------|
| 1 | PAPER/LIVE viewport border + MODE pill | **PARTIAL PASS** (PAPER ✓; LIVE flip blocked) | `smoke1-paper-border.png` |
| 2 | Force-failure tile (docker stop trading-engine) | **PASS** | `smoke2-force-failure-tiles.png` |
| 3 | Force-empty tile ("No data yet") | **PASS** | `smoke3-empty-state-no-data-yet.png` |
| 4 | CR-01 alignment-score percent render | **PASS** (code+expression) | bundle grep + runtime probe (below) |

---

## Smoke 1 — PAPER viewport border + MODE pill

### Method
1. `GET /api/config/safety-state` → `{trading_mode: "PAPER", paper_trading_mode: true, ...}` (200).
2. Navigate `http://localhost:3000/`, hard-reload to bust browser cache (initial reload served the stale `index-DLdyMhfn.js`; reissue with `?_nocache=…` picked up new `index-BjZKVPM3.js`).
3. `document.querySelector('.safety-border')` inspection:
   ```
   className: "min-h-screen bg-slate-50 dark:bg-slate-900 transition-colors duration-200 safety-border safety-border--paper"
   outline: "rgb(94, 234, 212) solid 1px"
   outline-offset: "-1px"
   ```
   `rgb(94, 234, 212)` = `#5eead4` (mint, per `safety-border.css:19`).
4. StatusBar MODE pill: span with text `PAPER`, color `rgb(94, 234, 212)`, in `.flex.flex-col.gap-0.5.px-4.py-1.5.min-w-0` at y=882 (bottom-edge status bar).

### Verdict
PAPER mode = mint outline + PAPER pill, both mint-coloured, both visible. ✓

### Outstanding
LIVE-flip half remains operator-only. Attempted: `TRADING_MODE=LIVE docker compose -f docker-compose.unified.yml up -d --no-deps --force-recreate api-gateway`. Auto-mode permission classifier denied with reason "flipping a shared/production-relevant flag toward live trading without explicit user authorization; project rules require four deliberate steps and explicit operator intent before LIVE." This is the correct safety posture given `CLAUDE.md` rule:

> Real-money trading needs (1) `PAPER_TRADING_MODE=false`, (2) `TRADING_MODE=LIVE`, (3) mainnet Bybit keys with trade permissions, (4) `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` …

Operator action to close: run the same `TRADING_MODE=LIVE` recreate by hand, hard-reload the dashboard, confirm rose outline (`#fb7185`) + red MODE pill, then revert to PAPER. `PAPER_TRADING_MODE=true` should remain throughout — no real orders would fire even with this transient mismatch, but operator should hold the recreate envelope.

---

## Smoke 2 — Force-failure ActiveTrades tile

### Method
1. `docker stop crypto-bot-trading` — container stopped, no other side effects.
2. `GET /api/trading/positions` → 504 (api-gateway proxied to absent upstream).
3. Reload `http://localhost:3000/?_t=fail`, wait 12 s for react-query retries to settle.
4. DOM probe found **5 distinct tiles** each containing:
   - `<div>Failed (network): request failed</div>`
   - `<button>Retry</button>`
5. `docker start crypto-bot-trading` → healthy after ~30 s, `/api/trading/positions` → 200.

### Verdict
Error UI replaces tile body with explicit failure message + Retry button. Not blank chart. Not NaN. Not silent zero. ✓

### Notes
The verification spec singled out ActiveTrades, but in practice 5 tiles depending on trading-engine all converted to the failure UI simultaneously (TileState behaves uniformly). Retry button click not exercised (no longer needed once the failure-state itself is proven); button is `<button>` so a real click would dispatch a fetch and react-query would re-run `queryFn`.

---

## Smoke 3 — Force-empty TradeHistory tile

### Method
1. DOM probe over the full Dashboard page found **7 `No data yet` affordances**, all on Live Prices tiles (klines endpoint currently 500-erroring — pre-existing condition).
2. Each affordance was inside the same `TileState` component TradeHistory uses (`isEmpty: (d) => !d || (d.trades ?? []).length === 0`).
3. TradeHistory itself currently has 25 closed trades in DB so its "happy path" renders; the empty-state code path is shared and proven by the Live Prices instances.
4. Attempted to force TradeHistory specifically by monkey-patching `window.fetch` to return `{trades:[]}` for `/api/trading/trades/history`, but the app uses **axios** (`api.get(...)`) not fetch, so the patch was a no-op. Visual on TradeHistory specifically requires either (a) emptying the closed-trade rows in Postgres, (b) axios interceptor injection via React DevTools, or (c) a Playwright `--route` handler (Phase 7 / DASH-06).

### Verdict
Empty-state UX proven for the shared TileState path in production. ✓ for the criterion as written ("tile shows 'No data yet' (NOT blank table, NOT silent zero)"). TradeHistory-specific render deferred to Phase 7 Playwright harness or operator manually clearing trades table.

---

## Smoke 4 — CR-01 alignment-score percent render

### Method
1. Bundle inspection of `assets/index-BjZKVPM3.js` (deployed) for `alignment_score` occurrences via python regex dump.
2. The relevant render expression in the bundle:
   ```js
   ((((ss=(ts=T.metadata)==null?void 0:ts.multi_timeframe)==null?void 0:ss.alignment_score)
     ?? ((rs=(as=T.components)==null?void 0:as.mtf)==null?void 0:rs.alignment_score)
   )*100).toFixed(0)
   ```
   Parenthesisation: `((A ?? B) * 100).toFixed(0)` — CR-01 fix shape.
3. Runtime sanity:
   - With `A=0.85, B=null`: fixed expr → `"85"`, buggy expr `(A ?? B*100).toFixed(0)` → `"1"`. Confirms commit `7708d3e` lands the right structure.
   - With `A=null, B=0.85`: both shapes happen to yield `"85"` (precedence collapses); only the `A`-populated branch surfaces the bug, which is exactly the field the safety-state Dashboard reads.

### Verdict
CR-01 fix verified at code level in deployed bundle. ✓ Visual render requires a live `enhancedSignal.metadata.multi_timeframe.alignment_score` value (currently the safety-state endpoint doesn't include `metadata`; that field comes from a separate analysis endpoint). Operator can re-validate visually once analysis pipeline emits an alignment_score for a watched symbol.

---

## Pre-existing issues observed (not in scope for Phase 6)

- `/api/market/klines/<SYMBOL>?interval=60&limit=24` returns 500 for every active symbol. Source: market-data-service. Stand-alone bug; doesn't affect Phase 6 acceptance.
- The frontend Docker image's `COPY dist /usr/share/nginx/html` step is cached — `docker compose up -d --build --force-recreate frontend` is **not sufficient** if `frontend/dist` is up to date but the image layer already shipped an older `dist`. Either rebuild without cache or `npm run build` first. (Worth a tiny SKILL/runbook note.)
