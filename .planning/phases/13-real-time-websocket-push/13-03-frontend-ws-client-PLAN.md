---
phase: 13-real-time-websocket-push
plan: 03
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/lib/wsClient.ts
  - frontend/src/hooks/useWsSubscription.ts
  - frontend/src/lib/__tests__/wsClient.test.ts
  - frontend/src/hooks/__tests__/useWsSubscription.test.tsx
autonomous: true
requirements:
  - WS-02
tags:
  - websocket
  - frontend
  - hooks

must_haves:
  truths:
    - "wsClient is a single tab-scoped singleton; multiple useWsSubscription calls reuse the same WebSocket"
    - "When tab is not yet visible at hook mount, the client still connects but sends {action:'pause'} immediately; visible mount sends {action:'resume'}"
    - "document.visibilityState transitions: hidden → {action:'pause'} frame sent; visible → {action:'resume'} frame sent; next frame arrives within 1s of visible (assertion driven by mock server)"
    - "Reconnect after server-close follows exponential backoff: 1s, 2s, 4s, 8s, 16s, then capped at 30s indefinitely (each attempt logs an Info-level message including the attempted delay)"
    - "On first successful onopen after a fresh connect, useWsSubscription primes its cache via a REST GET (uses the same /api/<path> as the existing hook would have) BEFORE waiting for the first push frame — render does not show empty state on initial mount"
    - "Token is sent ONLY inside the subscribe frame body; never as a URL query string"
  artifacts:
    - path: "frontend/src/lib/wsClient.ts"
      provides: "createWsClient singleton, exponential-backoff reconnect, visibility-aware pause, subscribe/unsubscribe API"
      min_lines: 200
    - path: "frontend/src/hooks/useWsSubscription.ts"
      provides: "useWsSubscription(channel, restPrimeUrl) hook returning {data, isLive, lastUpdatedAt, restFallbackActive}"
      min_lines: 80
  key_links:
    - from: "frontend/src/hooks/useWsSubscription.ts"
      to: "frontend/src/lib/wsClient.ts"
      via: "import { wsClient } from '../lib/wsClient'"
      pattern: "from.*wsClient"
    - from: "frontend/src/lib/wsClient.ts"
      to: "document.visibilityState"
      via: "document.addEventListener('visibilitychange', ...)"
      pattern: "visibilitychange"
---

<objective>
Land the frontend WebSocket client layer that Plans 13-04 (hook migration) will consume. Two artifacts:
1. `frontend/src/lib/wsClient.ts` — a single tab-scoped WebSocket connection to `/ws/metrics`, with exponential-backoff reconnect (1s → 30s cap), visibility-aware pause/resume, and per-channel subscriber bookkeeping.
2. `frontend/src/hooks/useWsSubscription.ts` — the React hook that components will call. It registers a per-channel callback against wsClient, primes the React Query cache with a REST snapshot fetch on first mount, and exposes a `restFallbackActive` flag that flips to `true` after 30s of WS silence (the actual REST poll re-arm happens in plan 13-04 inside each migrated hook — this plan exposes the flag).

Plan 13-03 does NOT modify any production hooks; that is Plan 13-04. The existing `useGatewayWebSocket.js` (the /ws ticker subscription) stays untouched.

Output: 2 new TS files + 2 vitest test files. No `.test.jsx`/`.test.tsx` in `components/__tests__/` is touched.
</objective>

<execution_context>
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/workflows/execute-plan.md
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@./CLAUDE.md

@frontend/src/hooks/useGatewayWebSocket.js
@frontend/src/hooks/useSafetyState.js
@frontend/src/services/api.js
@frontend/package.json

<interfaces>
<!-- Existing patterns the executor must align with. -->

From frontend/src/hooks/useGatewayWebSocket.js (existing — DO NOT MODIFY):
- Module-scoped singleton with `subscribers: Set<callback>`
- Lifecycle sentinel `wsLifecycle: 'idle' | 'connecting' | 'open' | 'closed'`
- Heartbeat via setInterval(ping, 30000)  ← NOTE: this is allowlisted; do not refactor in this plan
- WebSocket URL: `${protocol}//${window.location.host}/ws` (the /ws ticker route, different from our new /ws/metrics)

From frontend/src/services/api.js:
- Default axios client with baseURL `/api` and a response interceptor that unwraps `.data`
- Resolved value of `api.get(path)` is the body itself

WebSocket URL for /ws/metrics:
- Dev (Vite): `import.meta.env.VITE_WS_METRICS_URL` (default `ws://localhost:8000/ws/metrics`)
- Prod: `${protocol}//${window.location.host}/ws/metrics`

Subscribe frame schema (must match server):
```json
{"action": "subscribe", "channels": ["safety-state", ...], "token": "<bearer>"}
```

Server-emitted frame schema:
```json
{"channel": "safety-state", "schema_version": 1, "data": {...}, "ts": "..."}
```

Server close codes the client must recognize:
- 4400 — protocol error (our subscribe was malformed); do NOT reconnect (config error, retry would loop)
- 4401 — auth failure; do NOT reconnect (token expired/invalid; user must re-login)
- 1000 — normal closure; do NOT reconnect
- 1006 / others — abnormal; reconnect with backoff

Auth token source:
- Existing patterns use localStorage `auth_token` or similar — read frontend/src/services/api.js to confirm exact key name and use the same.

Vitest setup (frontend already has it):
- `frontend/package.json` declares `vitest ^1.6.0` + `@testing-library/react ^14.2.0` + `jsdom ^24.0.0`
- Test files live alongside src OR under `__tests__/` directories
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: wsClient singleton (connection, reconnect, visibility)</name>
  <files>frontend/src/lib/wsClient.ts, frontend/src/lib/__tests__/wsClient.test.ts</files>
  <read_first>
    - frontend/src/hooks/useGatewayWebSocket.js (singleton + lifecycle sentinel + backoff pattern to mirror, NOT to import)
    - frontend/src/services/api.js (find the auth token key — likely `localStorage.getItem('auth_token')` or via axios interceptor; pin exact location)
    - frontend/package.json (confirm vitest, @testing-library/react, jsdom versions)
  </read_first>
  <behavior>
    Public API (from wsClient.ts):
    ```ts
    export type WsChannel = 'safety-state' | 'live-readiness' | 'carry-ins' | 'dashboard-snapshot'
    export type WsFrame<T = unknown> = { channel: WsChannel; schema_version: 1; data: T; ts: string }
    export type WsListener<T = unknown> = (frame: WsFrame<T>) => void

    export interface WsClient {
      subscribe<T = unknown>(channel: WsChannel, listener: WsListener<T>): () => void  // returns unsubscribe fn
      isLive(): boolean
      lastFrameAt(channel: WsChannel): number | null  // unix ms, or null if never
      __forTest_setVisibility?: (state: 'hidden' | 'visible') => void  // injected in test mode
    }

    export const wsClient: WsClient = createWsClient()  // singleton
    ```

    Internal lifecycle:
    - On first subscribe() call ever: open WebSocket to `${protocol}//${host}/ws/metrics` (or VITE_WS_METRICS_URL in dev)
    - onopen: send subscribe frame with the union of all currently-subscribed channels + token from localStorage
    - onmessage: parse JSON; route to all listeners registered for frame.channel; update lastFrameAt[channel] = Date.now()
    - onclose: if close code is 1000/4400/4401 → do NOT reconnect (final). Otherwise → scheduleReconnect with exponential backoff starting at 1s, doubling per attempt, capped at 30s.
    - visibilitychange listener: hidden → ws.send({action:"pause"}) AND clear the WS-silence detection timer; visible → ws.send({action:"resume"})
    - On 100% subscriber unsubscribe (subscribers map becomes empty across all channels): close ws with code 1000 and reset state.

    Reconnect behavior:
    - reconnectAttempts counter, reset to 0 on successful onopen
    - backoff delay = Math.min(1000 * 2 ** (attempts - 1), 30000)
    - Each scheduleReconnect logs `console.info('[wsClient] reconnect attempt N in Xms')`
    - Reconnect timer cleared on visibilitychange → hidden (we don't reconnect while tab is in the background)

    Tests (wsClient.test.ts) — use a mock WebSocket harness (custom class that implements the WebSocket interface and lets tests step its lifecycle manually):
    1. First subscribe() opens exactly one WebSocket
    2. Second subscribe() to a DIFFERENT channel reuses the same WebSocket (subscribers count goes 1 → 2; no new connection)
    3. Listener for channel X receives the next frame whose `frame.channel === 'X'`; listener for channel Y is NOT called
    4. After onopen, the mock receives a subscribe frame whose `channels` array contains all registered channels
    5. Server close code 1006: scheduleReconnect fires after 1000ms (use vi.useFakeTimers + vi.advanceTimersByTime)
    6. Server close code 4401: NO reconnect (timer never scheduled); subsequent vi.advanceTimersByTime(60000) sees no new connect
    7. Exponential backoff: attempt 1 → 1s, attempt 2 → 2s, attempt 3 → 4s, attempt 5 → 16s, attempt 6 → 30s, attempt 10 → 30s (cap)
    8. visibilitychange → 'hidden': mock receives `{action: "pause"}` frame
    9. visibilitychange → 'visible': mock receives `{action: "resume"}` frame
    10. Last subscriber's unsubscribe() closes the WebSocket with code 1000 (use a spy on ws.close)
  </behavior>
  <action>
    Create frontend/src/lib/wsClient.ts implementing the public API and internal lifecycle above. Mirror the singleton + sentinel pattern from useGatewayWebSocket.js but DO NOT import or modify that file.
    Resolve the URL via a `resolveWsMetricsUrl()` helper:
      - test env: `__WS_URL_OVERRIDE` global (let tests inject a mock URL)
      - dev (`import.meta.env.DEV`): `import.meta.env.VITE_WS_METRICS_URL || 'ws://localhost:8000/ws/metrics'`
      - prod: `${protocol}//${window.location.host}/ws/metrics` where protocol = 'wss:' if `window.location.protocol === 'https:'` else 'ws:'
    Resolve the token via the existing pattern in services/api.js (localStorage key — pin the exact name during read_first).
    Create frontend/src/lib/__tests__/wsClient.test.ts implementing the 10 tests above with vitest + fake timers. Use a hand-rolled MockWebSocket class assigned to `global.WebSocket` per-test; tests step its lifecycle by directly invoking `mock.onopen()`, `mock.onmessage({data: JSON.stringify(frame)})`, `mock.onclose({code: N})`.
    Drive visibility transitions via `Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' })` plus `document.dispatchEvent(new Event('visibilitychange'))`.
  </action>
  <verify>
    <automated>cd frontend && npx vitest run src/lib/__tests__/wsClient.test.ts</automated>
  </verify>
  <acceptance_criteria>
    - File frontend/src/lib/wsClient.ts exists and exports `wsClient` named export
    - `grep -c "export " frontend/src/lib/wsClient.ts` returns >=4 (WsChannel, WsFrame, WsListener, wsClient)
    - vitest reports 10 tests passed, 0 failed
    - `grep -n "1000.*\\*\\*.*30000\\|Math.min.*1000.*\\*\\*\\|Math.pow" frontend/src/lib/wsClient.ts` returns >=1 hit (proves exponential-backoff math is in source, not external)
    - `grep -n "visibilitychange" frontend/src/lib/wsClient.ts` returns >=1 hit (proves listener is wired)
    - File contains NO `setInterval(.*[0-9]{4,})` for the primary connection logic (heartbeat is sent BY the server, not the client, for /ws/metrics; client may use setInterval ONLY for visibility-pause-check if needed — but should not poll)
  </acceptance_criteria>
  <done>wsClient singleton implements connect/reconnect/visibility per the contract; vitest green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: useWsSubscription hook with REST priming</name>
  <files>frontend/src/hooks/useWsSubscription.ts, frontend/src/hooks/__tests__/useWsSubscription.test.tsx</files>
  <read_first>
    - frontend/src/lib/wsClient.ts (from Task 1)
    - frontend/src/hooks/useSafetyState.js (the value-contract any migrated hook must preserve — refer to its doc comments for the data shape)
    - frontend/src/services/api.js (the axios client)
  </read_first>
  <behavior>
    Public API:
    ```ts
    export interface UseWsSubscriptionResult<T> {
      data: T | undefined
      isLive: boolean
      lastUpdatedAt: string | null   // ISO from frame.ts
      restFallbackActive: boolean
      error: Error | null
    }
    export function useWsSubscription<T = unknown>(
      channel: WsChannel,
      restPrimeUrl: string,           // e.g. '/config/safety-state' (path relative to api base; passed to existing axios instance)
      options?: { silenceTimeoutMs?: number }   // default 30000
    ): UseWsSubscriptionResult<T>
    ```

    Behavior:
    1. On mount: subscribe via wsClient.subscribe(channel, listener) and immediately fire `api.get(restPrimeUrl)` to seed `data` BEFORE the first push arrives. If api.get resolves before the first push, set data to the response. If a push arrives first, it wins and the api.get response is discarded.
    2. On each frame: setState({ data: frame.data, lastUpdatedAt: frame.ts }).
    3. Silence detector: a setTimeout for `silenceTimeoutMs` (default 30000) reset on every frame received. If it fires → setState({ restFallbackActive: true }). The actual REST poll re-arm is the responsibility of the consuming hook in Plan 13-04 — useWsSubscription only SIGNALS the condition. Once any new push arrives, restFallbackActive flips back to false.
    4. isLive returns true when wsClient.isLive() === true.
    5. On unmount: unsubscribe (returned cleanup from wsClient.subscribe).
    6. The hook MUST be stable across rerenders — wsClient.subscribe is called once per channel per component instance (use useEffect with [channel, restPrimeUrl] deps).

    Tests (useWsSubscription.test.tsx) — use @testing-library/react render + waitFor:
    1. Mount with a primed channel: data populates from REST first (mock api.get returns {trading_mode:"PAPER"}); within 50ms the first WS push overrides it
    2. After mount, simulate frame on the SAME channel: data updates with frame.data, lastUpdatedAt updates with frame.ts
    3. After mount, simulate frame on a DIFFERENT channel: hook's data does NOT update
    4. No frame for `silenceTimeoutMs` (mock with fake timers): restFallbackActive flips to true
    5. After flipping to restFallbackActive, a new frame arrives: restFallbackActive flips back to false AND data updates
    6. Two components mount the same channel: wsClient.subscribe is called twice (once per instance) but the underlying WebSocket connection is opened only once (this is wsClient's job — assert by spying on wsClient.subscribe call count + global.WebSocket constructor call count)
    7. Unmount: cleanup unsubscribes (next frame on that channel does not trigger setState — use renderHook + act)
  </behavior>
  <action>
    Create frontend/src/hooks/useWsSubscription.ts with the API above.
    Use React's useState + useEffect; the REST prime is `api.get(restPrimeUrl).then(setData)` with a `cancelled` flag captured in the effect's cleanup so the response is dropped if the component unmounted before the GET resolved.
    Silence detector: use `useRef` for the timer handle and `setTimeout` (not setInterval). Clear-and-reset on every frame.
    Create frontend/src/hooks/__tests__/useWsSubscription.test.tsx.
    Mock wsClient via `vi.mock('../../lib/wsClient', () => ({...stub with controllable emit function...}))` so tests can drive frames manually.
    Mock the axios `api` instance via `vi.mock('../../services/api', () => ({ default: { get: vi.fn() } }))`.
  </action>
  <verify>
    <automated>cd frontend && npx vitest run src/hooks/__tests__/useWsSubscription.test.tsx</automated>
  </verify>
  <acceptance_criteria>
    - File frontend/src/hooks/useWsSubscription.ts exists and exports `useWsSubscription` named export
    - `grep -c "export " frontend/src/hooks/useWsSubscription.ts` returns >=2 (interface + function)
    - vitest reports 7 tests passed
    - Hook file contains NO `setInterval` call (uses setTimeout for silence detection — verify with `grep -c setInterval frontend/src/hooks/useWsSubscription.ts` returning 0)
    - `grep -n "restFallbackActive\|silenceTimeoutMs\|wsClient.subscribe" frontend/src/hooks/useWsSubscription.ts` returns >=3 hits
  </acceptance_criteria>
  <done>Hook implements channel subscribe + REST priming + silence detection; all tests green.</done>
</task>

</tasks>

<verification>
- WS-02 implemented: wsClient handles reconnect/backoff/visibility; useWsSubscription delivers data + flags to consumers
- Tests prove: exponential backoff math correct, visibility pause/resume frames sent, REST priming + silence detection in hook
- No production hook is modified yet (Plan 13-04's job)
</verification>

<success_criteria>
- [ ] frontend/src/lib/wsClient.ts exists with full singleton lifecycle
- [ ] frontend/src/hooks/useWsSubscription.ts exists with REST priming + silence detection
- [ ] vitest green across both new test files (~17 tests total)
- [ ] No production hook (.js files in frontend/src/hooks/use*.js) modified
- [ ] useGatewayWebSocket.js (existing /ws ticker client) untouched
- [ ] WS-02 satisfied
</success_criteria>

<output>
After completion, create `.planning/phases/13-real-time-websocket-push/13-03-SUMMARY.md` documenting:
- Public API exports from wsClient and useWsSubscription
- Auth token source (localStorage key name pinned during read_first)
- Backoff schedule table (attempt N → delay)
- Number of vitest tests passing
</output>
</content>
</invoke>