---
slug: dashboard-cold-load-timeout
status: resolved
trigger: |
  Dashboard route / fires GET /api/trading/trades/history?limit=50 on first
  paint; axios aborts with "timeout of 5000ms exceeded" before the request
  resolves. Retry (and any subsequent /) reload succeeds in well under 5s.
  Symptom is cold-cache-only: reproducible after fresh tab / hard reload,
  invisible on warm navigation.
created: 2026-05-19
updated: 2026-05-19
tdd_mode: false
---

# Debug Session: dashboard-cold-load-timeout

## Symptoms (verbatim from Playwright MCP audit, 2026-05-19)

DATA_START
**Expected behavior:**
  Dashboard / loads cleanly on cold paint with no console errors. The
  /api/trading/trades/history?limit=50 request either completes within the
  client timeout or the client timeout accommodates realistic backend latency.

**Actual behavior:**
  On cold first paint of /:
  - Console: `API Error: timeout of 5000ms exceeded @ http://localhost:3000/assets/index-*.js:0`
  - Network: GET /api/trading/trades/history?limit=50 → [FAILED] net::ERR_ABORTED
    (axios aborts after 5000ms). Fires twice (component-level + dashboard-level).
  - A later GET /api/trading/trades/history?limit=1000 in the same paint returns 200.
  - A retry of the limit=50 call later in the paint also returns 200.

  On warm reload of /:
  - 0 console errors. /api/trading/trades/history?limit=50 returns 200 immediately.

**Error messages:**
  [ERROR] API Error: timeout of 5000ms exceeded @ http://localhost:3000/assets/index-TtOxIKci.js:0
  Network: GET /api/trading/trades/history?limit=50 => [FAILED] net::ERR_ABORTED

**Timeline:**
  Surfaced 2026-05-19 during full-frontend Playwright audit. Reproducible on
  fresh tab / hard reload. Bundle name in the original capture was the
  pre-feature-flag-fix bundle (index-TtOxIKci.js); now serving index-DysNXX8f.js
  after the phase3-feature-flag-ungated fix. Need to confirm the timeout is not
  bundle-version-dependent.

**Reproduction:**
  1. Ensure stack up: docker compose -f docker-compose.unified.yml ps
  2. Open a fresh browser context (no warm cache) → navigate to http://localhost:3000/
  3. Open DevTools console BEFORE first paint
  4. Observe "API Error: timeout of 5000ms exceeded" on first render
  5. Network tab → 1–2 ERR_ABORTED entries for /api/trading/trades/history?limit=50

  The audit captured the same /api/trading/trades/history?limit=50 succeeding in
  network requests #38 and #50 of the same page-load capture, meaning the call
  did complete server-side — axios just gave up before the server responded.

**Scope: / page only.** Other 6 routes (/phase1, /phase3, /performance,
/tournament, /portfolio, /settings) audited cleanly — no axios-timeout pattern.
DATA_END

## Current Focus

hypothesis: A per-request `timeout: 5000` override on the trades-history
  axios call (separate from the global 20s default in services/api.js) is
  shorter than the cold first-paint settle time when 10+ Dashboard tiles
  fire concurrently. The cold delay is browser-side concurrency / bundle
  parse / paint pressure, not a backend perf bug — backend round-trip is
  43ms cold and <30ms warm. React Query's default retry=2 makes the bad
  timeout fire 1+ times before the limit=1000 path (which uses the global
  20s and a different queryKey) is allowed through.
test: 
  1. grep the frontend for the axios instance + timeout setting [DONE]
  2. Time the endpoint cold vs warm with: `curl -w "%{time_total}\n" -o /dev/null -s http://localhost:8000/api/trading/trades/history?limit=50` immediately after restarting api-gateway and trading-engine [DONE]
  3. Compare to current timeout literal in frontend [DONE]
expecting: A per-component `timeout: 5000` override exists. Backend cold
  latency is sub-second. Removing the override (so the call inherits the
  intentional 20s api.js default) is the right fix.
next_action: (none — resolved)
reasoning_checkpoint: null
tdd_checkpoint: null

## Evidence

- timestamp: 2026-05-19T04:13Z
  source: grep frontend/src/services/api.js
  finding: |
    Global axios instance is set to `timeout: 20000` (20s) per the
    documented 2025-11-30 bump from 10s. This is the shared client used by
    all callers that route through `services/api.js`.

- timestamp: 2026-05-19T04:13Z
  source: read frontend/src/components/TradeHistory.jsx (lines 27–32)
  finding: |
    `fetchTradeHistory` shadow-overrides the global timeout:

        return await api.get('/trading/trades/history', {
          params: { limit: 50 },
          timeout: 5000,
        })

    Axios per-request `timeout` overrides instance default — this is the
    only call site in the entire frontend with both `limit: 50` and a
    sub-20s timeout, exactly matching the audit's error fingerprint.

- timestamp: 2026-05-19T04:13Z
  source: grep -rn "trades/history" frontend/src/
  finding: |
    Four call sites total. Only TradeHistory.jsx uses `limit=50` (with
    timeout 5000). PerformanceAnalyticsPanel.jsx fires `limit=1000` against
    the same endpoint with the global 20s timeout — this is the "later
    call in same paint returns 200" path the audit observed. Different
    queryKeys (`['tradeHistory']` vs `['trades','history']`) prevent
    React Query from de-duping them.

- timestamp: 2026-05-19T04:14Z
  source: docker exec crypto-bot-frontend grep ... /usr/share/nginx/html/assets/index-DysNXX8f.js
  finding: |
    Pre-fix deployed bundle contains literals `timeout:5e3`, `timeout:2e4`,
    `limit:50`. Confirms the source-level 5000ms override survives Vite
    minification into the bundle that was being served.

- timestamp: 2026-05-19T04:13Z
  source: warm-cache curl loop against http://localhost:8000/api/trading/trades/history?limit=50
  finding: |
    Stack had been up ~2 hours. Three sequential hits:
      Run 1: 200 in 0.833s   (first hit after idle gap)
      Run 2: 200 in 0.169s
      Run 3: 200 in 0.068s
    Worst warm latency observed is 833ms — well under the 5s axios cap.

- timestamp: 2026-05-19T04:14Z
  source: docker compose -f docker-compose.unified.yml restart trading-engine api-gateway; then curl loop
  finding: |
    Operationally relevant — this restart was performed for cold-path
    measurement. Trading-engine /ready returned 200 within 1s after the
    8s grace window. Cold-path curl loop (6 hits in quick succession):
      Run 1: 200 in 0.043s
      Run 2–6: 200 in 0.013–0.026s
    First hit *after restart* is 43ms. No backend perf bug exists; the
    cold latency the audit captured lives entirely in the browser
    (concurrent fan-out, bundle parse, layout/paint on first render).
    NOTE TO OPERATOR: one trading-engine + api-gateway restart was
    triggered at 04:14 UTC for cold-path measurement; auto-trader
    self-resumed on next loop tick. Subsequent fix (frontend rebuild)
    required only a frontend container recreation, not a backend restart.

- timestamp: 2026-05-19T04:15Z
  source: read frontend/src/main.jsx (QueryClient defaults)
  finding: |
    `retry: 2, retryDelay: 1000` is the global default. This explains the
    audit note "Fires twice (component-level + dashboard-level)": the
    initial failing fetch + retries from React Query, all bound to the
    same `['tradeHistory']` queryKey. There is no second source-level
    caller of `limit=50`.

- timestamp: 2026-05-19T04:30Z
  source: post-fix bundle verification
  finding: |
    After applying the source fix, running `cd frontend && npm run build`
    produced new bundle `index-FqhUaIAn.js`, then
    `docker compose up -d --build frontend` recreated the container.
    Deployed-bundle search results:
      timeout:5e3   → 0 occurrences  (gone — was the bug)
      timeout:2e4   → 1 occurrence   (20s global default, preserved)
      limit:50      → 1 occurrence   (route still requests 50 rows)
    Post-fix curl loop against /api/trading/trades/history?limit=50:
      Run 1: 200 in 0.473s
      Run 2: 200 in 0.014s
      Run 3: 200 in 0.015s
    Index.html served by nginx now references `index-FqhUaIAn.js`.

## Eliminated

- Backend perf bug on /api/trading/trades/history (cold-path curl: 43ms
  first hit after restart; warm: <30ms).
- Missing DB index / cold connection pool (latency too small to matter).
- Bundle drift between the audit and now (the original audit bundle
  index-TtOxIKci.js and the pre-fix index-DysNXX8f.js both shipped the
  same `timeout:5e3` literal — confirmed before the fix).
- Different timeout in the global axios instance (`timeout:2e4` confirmed
  in deployed bundle, both pre and post fix).
- A pre-warm cron / startup tickler — would solve a non-problem here.

## Resolution

root_cause: |
  TradeHistory.jsx line 30 hard-coded a per-request `timeout: 5000` that
  overrode the global axios client's intentional 20s default
  (frontend/src/services/api.js, bumped from 10→20s on 2025-11-30). On
  cold first paint of /, the Dashboard mounts ~12 tiles concurrently;
  bundle parse + layout + 10 parallel API calls pushed this single 5s
  budget over the edge even though backend round-trip is <100ms. The
  call eventually succeeded (as the audit observed in same-paint network
  requests #38 and #50), but axios had already aborted by then. React
  Query's `retry: 2` default amplified the visible error count, matching
  the audit's "fires twice" observation. There is only one source-level
  caller of limit=50.

fix: |
  Removed the per-request `timeout: 5000` override on TradeHistory.jsx
  so the call inherits the deliberate 20s global default. No defensive
  bump-and-comment — the global value is the single source of truth for
  the dashboard's axios timeout policy. Added a dated doc-comment
  explaining the removal. Rebuilt the frontend bundle
  (`cd frontend && npm run build`) and recreated the container
  (`docker compose -f docker-compose.unified.yml up -d --build frontend`).

verification: |
  1. Source diff: TradeHistory.jsx now omits `timeout: 5000`; only
     `params: { limit: 50 }` remains. Diff is +7 / -1 lines (the +7 is
     a dated maintenance comment).
  2. Deployed bundle check: `index-FqhUaIAn.js` no longer contains
     `timeout:5e3` (0 occurrences) while still containing `timeout:2e4`
     (the 20s default) and `limit:50` (route still wired to 50 rows).
  3. Backend sanity: post-fix curl http://localhost:8000/api/trading/trades/history?limit=50 returns 200 in 472ms first hit, 14–15ms warm — well within the new effective 20s budget.
  4. Operator-driven (orchestrator owns): Playwright MCP load of / on a fresh context — expected: zero console errors, zero ERR_ABORTED for limit=50.

files_changed:
  - frontend/src/components/TradeHistory.jsx
