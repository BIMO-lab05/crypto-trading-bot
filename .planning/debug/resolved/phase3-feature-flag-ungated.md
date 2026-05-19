---
slug: phase3-feature-flag-ungated
status: resolved
trigger: |
  Phase3 Dashboard at http://localhost:3000/phase3 fires API calls to ml-prediction
  and sentiment-analysis services even though they are intentionally disabled by
  the compose-level feature flags ENABLE_ML_PREDICTIONS=false and
  ENABLE_SENTIMENT_ANALYSIS=false (per CLAUDE.md). Gateway returns 503 for both,
  producing 4 console errors per page load.
created: 2026-05-19
updated: 2026-05-19
tdd_mode: false
---

# Debug Session: phase3-feature-flag-ungated

## Symptoms (verbatim from Playwright MCP audit, 2026-05-19)

DATA_START
**Expected behavior:**
  When ENABLE_ML_PREDICTIONS=false and ENABLE_SENTIMENT_ANALYSIS=false, the
  Phase3 Dashboard should either (a) not call the ml-prediction and
  sentiment-analysis endpoints at all, or (b) call a gated endpoint that returns
  a graceful empty/disabled envelope with HTTP 200. No console error noise.

**Actual behavior:**
  Phase3 page issues GET /api/ml/predict/price/BTCUSDT?interval=60 and
  GET /api/sentiment/combined/BTCUSDT?hours=24 on every load. Gateway returns
  503 Service Unavailable for both. Browser console reports 4 errors per load
  (one network 503 + one axios "API Error" entry per endpoint).

**Error messages:**
  [ERROR] Failed to load resource: the server responded with a status of 503 (Service Unavailable) @ http://localhost:3000/api/sentiment/combined/BTCUSDT?hours=24:0
  [ERROR] API Error: {detail: Service sentiment-analysis unavailable} @ http://localhost:3000/assets/index-TtOxIKci.js:0
  [ERROR] Failed to load resource: the server responded with a status of 503 (Service Unavailable) @ http://localhost:3000/api/ml/predict/price/BTCUSDT?interval=60:0
  [ERROR] API Error: {detail: Service ml-prediction unavailable} @ http://localhost:3000/assets/index-TtOxIKci.js:0

**Timeline:**
  Surfaced 2026-05-19 during full-frontend audit via Playwright MCP. Feature
  flags ENABLE_ML_PREDICTIONS=false and ENABLE_SENTIMENT_ANALYSIS=false have
  been compose defaults since 2026-05 sentiment-leg-removal commits
  (c346483, acae081, fe941cf, c171bb0). Phase3 UI predates that change and
  appears not to gate its calls on the flags.

**Reproduction:**
  1. docker compose -f docker-compose.unified.yml up -d  (with default flags)
  2. Open http://localhost:3000/phase3
  3. Open DevTools console → observe 4 errors on first render
  4. Network tab → 2× 503 responses on the ml + sentiment endpoints

**Other 6 routes (`/`, `/phase1`, `/performance`, `/tournament`, `/portfolio`,
`/settings`) audited cleanly — 0 console errors. Issue is Phase3-specific.**
DATA_END

## Current Focus

hypothesis: Phase3Dashboard.jsx fires 4 unconditional useQuery calls without
  reading the feature-flag state. Adopt the existing safety-state pattern
  (useSafetyState) to gate mlQuery + sentimentQuery via `enabled:`.
test: located unconditional useQuery hooks at Phase3Dashboard.jsx:152-216;
  located /api/config/safety-state at services/api-gateway/app/main.py:1049
  already publishing ml_predictions_enabled — needs parity for
  sentiment_analysis_enabled.
expecting: confirmed.
next_action: COMPLETE.
reasoning_checkpoint: null
tdd_checkpoint: null

## Evidence

- timestamp: 2026-05-19
  source: frontend/src/pages/Phase3Dashboard.jsx:152-216
  finding: |
    4 useQuery hooks fire on mount with no `enabled` gate. Only mlQuery
    (line ~152) and sentimentQuery (line ~176) hit gated downstream services.
    mtfQuery and enhancedSignalQuery target technical-analysis and
    trading-engine — both always on; they were NOT in the error list and
    must NOT be gated.
- timestamp: 2026-05-19
  source: frontend/src/services/api.js:32-39
  finding: |
    The axios response interceptor calls `console.error('API Error:', ...)`
    on every rejected response, producing the second console-error line
    per failed request. Even with `retry: false` on 503, react-query
    settles the rejection through the interceptor once.
- timestamp: 2026-05-19
  source: services/api-gateway/app/main.py:1049-1165 (safety-state handler)
  finding: |
    /api/config/safety-state already reads ENABLE_ML_PREDICTIONS but did
    not publish a sentiment_analysis_enabled key. Added one-line env read
    mirroring the ml branch, plus a new response field. Compose
    api-gateway env block needed the ENABLE_SENTIMENT_ANALYSIS line for
    the gateway to see the flag (was only set on the trading-engine block).
- timestamp: 2026-05-19
  source: frontend/src/hooks/useSafetyState.js
  finding: |
    Pattern already in production — StatusBar.jsx:79 consumes
    safety.ml_predictions_enabled. Phase3Dashboard simply did not import
    it. The hook polls /api/config/safety-state every 5s (D-11 cadence).
- timestamp: 2026-05-19
  source: frontend/package.json
  finding: |
    @tanstack/react-query v5.12.2 — `enabled: false` blocks fetch entirely,
    re-evaluated synchronously on every render. Safe to use directly
    against a possibly-undefined `safety` value. Explicit `=== true`
    chosen over `!!` per advisor: only literal true opens the gate (no
    stringified envelopes, no accidental truthy coercion).
- timestamp: 2026-05-19
  source: live verification (curl + docker logs)
  finding: |
    1. curl http://localhost:8000/api/config/safety-state →
       contains "sentiment_analysis_enabled":false alongside
       "ml_predictions_enabled":false. Gateway env wiring works.
    2. New frontend bundle hash index-DysNXX8f.js (replacing the broken
       index-TtOxIKci.js named in the original audit) contains both
       safety-state key references and both /ml/predict/price + /sentiment/combined
       URLs (gated, not removed — still callable when operator flips flags ON).
    3. docker logs --since=60s crypto-bot-api-gateway → unique /api endpoints
       accessed include /api/config/safety-state, /api/trading/*,
       /api/market/*, /api/portfolio, /api/preflight/* — and ZERO hits on
       /api/ml/* or /api/sentiment/* with the active browser session.
       Gate is effective end-to-end.
    4. services/api-gateway tests/test_safety_state.py: 13 passed
       (11 existing + 2 new env-read regression guards).

## Eliminated

- gateway-routing bug: gateway routes were correctly declared; 503 originated
  from downstream services refusing requests when their service-level flag
  is off. Confirmed by error-body shape `{detail: "Service X unavailable"}`.
- mtf + enhanced signal queries: not in error list; backed by
  technical-analysis and trading-engine respectively, both always on. Not
  gated by the fix (would be a regression).

## Resolution

root_cause: |
  Phase3Dashboard.jsx fired ml-prediction + sentiment-analysis useQuery calls
  unconditionally on mount, with no read of the operator's feature-flag state.
  The gateway propagated the downstream 503s, and the frontend axios
  interceptor surfaced a `console.error` per rejected response — yielding
  4 console errors per page load (one browser network-error line + one axios
  "API Error" line per failed endpoint). The /api/config/safety-state
  endpoint already published ml_predictions_enabled (consumed by StatusBar)
  but lacked sentiment_analysis_enabled, and Phase3Dashboard did not import
  useSafetyState at all.

fix: |
  Frontend gate + gateway envelope (defense-in-depth via the existing
  safety-state pattern).

  1. services/api-gateway/app/main.py — /api/config/safety-state handler:
     - Added local env read `sentiment_analysis_enabled = os.getenv("ENABLE_SENTIMENT_ANALYSIS", "false").lower() == "true"`
     - Added `"sentiment_analysis_enabled": sentiment_analysis_enabled` to
       the response dict.
     - Updated ownership-split docstring to mention the new flag.

  2. docker-compose.unified.yml — api-gateway env block (line 293):
     - Added `- ENABLE_SENTIMENT_ANALYSIS=${ENABLE_SENTIMENT_ANALYSIS:-false}`
       so the gateway sees the flag (was only set on trading-engine block).
     - Removed an accidental duplicate that the initial patch introduced.

  3. services/api-gateway/tests/test_safety_state.py:
     - Added `sentiment_analysis_enabled` to the D-08 schema-key tuple.
     - Added test_sentiment_analysis_enabled_reads_env_true.
     - Added test_sentiment_analysis_enabled_defaults_false.

  4. frontend/src/hooks/useSafetyState.js — docstring:
     - Added `sentiment_analysis_enabled: boolean` to the documented
       D-08 schema shape.

  5. frontend/src/pages/Phase3Dashboard.jsx:
     - Imported useSafetyState.
     - Right after `queryClient`: read `{ data: safety } = useSafetyState()`
       and derive `mlPredictionsEnabled = safety?.ml_predictions_enabled === true`
       and `sentimentAnalysisEnabled = safety?.sentiment_analysis_enabled === true`
       (explicit `=== true` to refuse any non-literal-true value per advisor).
     - Added `enabled: mlPredictionsEnabled` to mlQuery (line ~180).
     - Added `enabled: sentimentAnalysisEnabled` to sentimentQuery (line ~208).
     - mtfQuery and enhancedSignalQuery deliberately left ungated (their
       downstream services are always on).

verification: |
  - 13/13 tests pass in services/api-gateway/tests/test_safety_state.py
    (11 existing + 2 new). Pre-existing unrelated test failures in
    frontend/__tests__/performance.test.jsx etc. confirmed identical
    fail count (51/183) on unmodified tree via git-stash bisection.
  - GET http://localhost:8000/api/config/safety-state returns
    sentiment_analysis_enabled:false alongside ml_predictions_enabled:false.
  - New frontend bundle (index-DysNXX8f.js) deployed and serving from
    crypto-bot-frontend container (recreated 2026-05-19 02:25 UTC).
  - api-gateway recreated after compose env change to pick up the new
    ENABLE_SENTIMENT_ANALYSIS var (os.getenv reads at process start).
  - docker logs --since=60s on crypto-bot-api-gateway after a Phase3 page
    load shows ZERO hits to /api/ml/* or /api/sentiment/*. Only the
    /api/config/safety-state poll fires (every 5s, as expected from
    useSafetyState's refetchInterval).
  - DEFERRED: a final Playwright MCP re-check of /phase3 showing 0 console
    errors. The session-manager subagent does not have Playwright tools in
    its toolset (Read/Write/Bash/advisor only). The fix is validated by
    bundle inspection, gateway access-log absence, and unit tests. A
    follow-up `/verify-stack` or operator-side Playwright run is
    recommended to close the visual loop.

files_changed:
  - services/api-gateway/app/main.py (+8 lines)
  - services/api-gateway/tests/test_safety_state.py (+41 lines)
  - docker-compose.unified.yml (+1 line; api-gateway env block)
  - frontend/src/hooks/useSafetyState.js (+1 docstring line)
  - frontend/src/pages/Phase3Dashboard.jsx (+26 lines)

specialist_review: |
  advisor-pre-fix consultation surfaced 4 blind spots, all addressed:
  1. Added regression-guard tests for sentiment_analysis_enabled env read
     (test_sentiment_analysis_enabled_reads_env_true +
     test_sentiment_analysis_enabled_defaults_false).
  2. Used explicit `=== true` not `!!` for the gate predicate.
  3. Did NOT gate mtfQuery / enhancedSignalQuery (their downstreams are
     always on).
  4. Acknowledged Playwright-MCP verification deferred (tool not available
     in session-manager harness).

  No engineering:debug specialist invoked — task is a frontend+gateway
  integration fix (not Python/TS/iOS-specific), and the project already
  has a mature safety-state pattern that the fix mirrors directly.
