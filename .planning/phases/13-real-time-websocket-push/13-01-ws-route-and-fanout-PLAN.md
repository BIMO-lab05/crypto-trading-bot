---
phase: 13-real-time-websocket-push
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - services/api-gateway/app/ws/__init__.py
  - services/api-gateway/app/ws/channels.py
  - services/api-gateway/app/ws/connection_manager.py
  - services/api-gateway/app/ws/redis_fanout.py
  - services/api-gateway/app/routes/ws_metrics.py
  - services/api-gateway/app/main.py
  - services/api-gateway/tests/unit/test_ws_connection_manager.py
  - services/api-gateway/tests/unit/test_ws_redis_fanout.py
  - services/api-gateway/tests/unit/test_ws_metrics_route.py
autonomous: true
requirements:
  - WS-01
tags:
  - websocket
  - api-gateway
  - redis

must_haves:
  truths:
    - "GET /ws/metrics WebSocket route accepts a connection on api-gateway:8000"
    - "Subscribe frame {action:'subscribe', channels:[…], token:'<bearer>'} authenticates against get_current_active_user; bad/absent token closes connection with code 4401"
    - "Unknown action in client frame closes connection with code 4400"
    - "After subscribe, server emits one snapshot frame per requested channel within 1s; frame schema is {channel, schema_version:1, data, ts:ISO-8601}"
    - "Heartbeat frame {channel, schema_version:1, data:{heartbeat:true}, ts} emitted at most every 5s per subscribed channel when state is steady"
    - "Local Redis subscriber on channels ws:metrics:<name> fans out incoming messages to all locally connected subscribers of that channel"
    - "Client {action:'pause'} suspends all pushes for that connection; {action:'resume'} re-enables; pause/resume is per-connection state in ConnectionManager"
  artifacts:
    - path: "services/api-gateway/app/ws/channels.py"
      provides: "CHANNELS constant (closed enum) and REDIS_CHANNEL_PREFIX"
      contains: "CHANNELS"
    - path: "services/api-gateway/app/ws/connection_manager.py"
      provides: "WsMetricsConnectionManager class with subscribe/unsubscribe/pause/resume/broadcast_channel"
      min_lines: 80
    - path: "services/api-gateway/app/ws/redis_fanout.py"
      provides: "RedisFanout class — start_subscriber(loop) + publish(channel, payload)"
      min_lines: 60
    - path: "services/api-gateway/app/routes/ws_metrics.py"
      provides: "/ws/metrics route handler + frame parser"
      min_lines: 100
  key_links:
    - from: "services/api-gateway/app/main.py"
      to: "services/api-gateway/app/routes/ws_metrics.py"
      via: "app.include_router or @app.websocket('/ws/metrics')"
      pattern: "ws_metrics"
    - from: "services/api-gateway/app/routes/ws_metrics.py"
      to: "services/api-gateway/app/auth_middleware.py"
      via: "manual token validation via verify_token (HTTPBearer Depends not usable on WebSocket)"
      pattern: "verify_token"
    - from: "services/api-gateway/app/ws/redis_fanout.py"
      to: "redis://crypto-bot-redis:6379"
      via: "redis.asyncio (aioredis 2.0.1 already in requirements.txt) pubsub.subscribe('ws:metrics:*')"
      pattern: "psubscribe"
---

<objective>
Land the server-side `/ws/metrics` WebSocket route on api-gateway with a per-connection ConnectionManager, a closed channel enum, and a Redis pub/sub subscriber that fans incoming messages from `ws:metrics:<channel>` to local WebSocket subscribers. Bearer-token auth runs in the subscribe handler (NOT via FastAPI `Depends` — that dependency form is not supported on WebSocket endpoints). The existing `/ws` ticker-broadcast route at `main.py:294` (WebSocketManager) is left untouched.

Purpose: Provide the pipe. Plan 13-02 will plug producers into it; plan 13-03 will plug the client into it.
Output: New `app/ws/` package + `app/routes/ws_metrics.py` route + main.py lifespan wiring + 3 unit-test files.

Note: 4 tasks instead of the standard 2-3. Task 4 is intentionally a deploy + observe step (separated per the verify-stack project skill — "never declare working on HTTP 200 alone"). Tasks 1-3 are code; Task 4 is verification of the integrated boot.
</objective>

<execution_context>
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/workflows/execute-plan.md
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@./CLAUDE.md

@services/api-gateway/app/main.py
@services/api-gateway/app/auth_middleware.py
@services/api-gateway/app/config.py
@services/api-gateway/requirements.txt

<interfaces>
<!-- Contracts the executor needs. Do not search the codebase — use these. -->

From services/api-gateway/app/auth_middleware.py (already present):
```python
async def verify_token(token: str) -> Optional[TokenData]
# Returns TokenData with .username, or None for invalid/expired token.
# Note: this is the function used internally by get_current_active_user.
# Token comes from the subscribe frame, NOT from an Authorization header,
# so we cannot use the HTTPBearer Depends form here.
```

From services/api-gateway/app/auth_models.py:
```python
def get_user(username: str) -> Optional[User]    # sync, in-memory lookup
```

From services/api-gateway/app/config.py:
```python
settings.redis_url  # str, default "redis://localhost:6379"; compose env: redis://crypto-bot-redis:6379
```

From services/api-gateway/requirements.txt:
```
aioredis==2.0.1          # already declared, currently unused; this plan uses it
redis==5.0.1             # sync client used by slowapi
```

From services/api-gateway/app/main.py (existing patterns):
- Line 184: `class WebSocketManager` — DO NOT MODIFY. Existing /ws route for tickers stays as-is.
- Line 297: `async def lifespan(app)` — extend by adding RedisFanout startup + shutdown.
- Line 1052: `/api/config/safety-state` handler — exact shape consumed by the safety-state channel snapshot.
- Line 1174: `/api/preflight/live-readiness` handler — exact shape consumed by the live-readiness channel snapshot.
- Line 1241: `from app.routes.preflight_carry_ins import router as preflight_carry_ins_router` — pattern for include_router from routes/ subdir.

Frame schema (from ROADMAP success criterion 1):
```json
{"channel": "safety-state", "schema_version": 1, "data": { ... }, "ts": "2026-05-21T12:34:56.789012+00:00"}
```

Channel enum (CLOSED — reject any subscribe to an unknown channel):
```
"safety-state", "live-readiness", "carry-ins", "dashboard-snapshot"
```

WebSocket close codes:
- 4400 — unknown action / malformed frame (close code, custom range 4000-4999)
- 4401 — auth failure (custom range; do NOT use 1008 because that is reserved for policy violation)
</interfaces>
</context>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser → api-gateway /ws/metrics | untrusted WebSocket client; bearer token in subscribe frame |
| api-gateway worker A → Redis pub/sub | trusted intra-cluster; Redis is internal-only (docker network 172.28.0.0/16) |
| api-gateway worker B → Redis pub/sub | same as worker A |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-13-01 | Spoofing | /ws/metrics subscribe handler | mitigate | call verify_token() on the token field of the subscribe frame; on None or User inactive, close with code 4401 BEFORE any data is sent. Token is NEVER read from URL query string (avoids logging the token in nginx/uvicorn access logs). |
| T-13-02 | Tampering | client → server frame | mitigate | parse incoming frame as JSON, validate action against closed enum {"subscribe","unsubscribe","pause","resume"} in ws_metrics.py; unknown action → close with code 4400. Validate channels list elements against CHANNELS enum in channels.py; unknown channel → ignore (do not subscribe) and log warning. |
| T-13-03 | DoS | ConnectionManager.subscribe | mitigate | per-connection: cap channels at len(CHANNELS) (4). Reject subscribe frames that exceed it. Per-connection: drop client if pong is not received within 30s of a server-initiated ping (FastAPI WebSocket has receive_timeout). |
| T-13-04 | Info disclosure | Redis pub/sub | mitigate | confirm Redis bind in docker-compose.unified.yml is internal-only (no `ports:` expose to host except 6379 dev-only). Redis channel namespace `ws:metrics:<name>` so an attacker who lands inside the network cannot trivially confuse channels with other pubsub topics. On the subscriber, validate `<name>` against CHANNELS before broadcasting locally; drop and log otherwise. |
| T-13-05 | DoS | Redis subscriber loop | mitigate | wrap pubsub.get_message() in try/except + asyncio.sleep(0.01) backoff so a malformed message cannot kill the loop; on exception log and continue. On Redis disconnect (ConnectionError), schedule reconnect with exponential backoff (1s → 30s cap) inside the lifespan task. |
| T-13-06 | Privilege Escalation | subscribe frame token | accept | token validates against existing JWT secret; this phase does NOT add a per-user channel filter — all four channels are operator-global data. Documented limitation: if per-user data is added later, ConnectionManager.broadcast_channel must gain a user-id filter. Recorded for v1.3+. |
</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Define channel registry and WS frame primitives</name>
  <files>services/api-gateway/app/ws/__init__.py, services/api-gateway/app/ws/channels.py, services/api-gateway/tests/unit/test_ws_channels.py</files>
  <read_first>
    - services/api-gateway/app/main.py (lines 1049-1170 for safety-state schema, lines 1174-1238 for live-readiness schema)
    - services/api-gateway/app/routes/preflight_carry_ins.py (for carry-ins schema — read full file)
    - .planning/REQUIREMENTS.md (WS-01 frame shape)
  </read_first>
  <behavior>
    - CHANNELS is a frozenset of four strings: "safety-state", "live-readiness", "carry-ins", "dashboard-snapshot"
    - REDIS_CHANNEL_PREFIX is the string "ws:metrics:"
    - redis_channel_name("safety-state") returns "ws:metrics:safety-state"
    - parse_channel_from_redis_name("ws:metrics:safety-state") returns "safety-state"
    - parse_channel_from_redis_name("ws:metrics:unknown") returns None (validates against CHANNELS)
    - parse_channel_from_redis_name("not-a-prefixed-name") returns None
    - make_frame("safety-state", {"trading_mode": "PAPER"}, ts="2026-05-21T00:00:00+00:00") returns {"channel": "safety-state", "schema_version": 1, "data": {"trading_mode": "PAPER"}, "ts": "2026-05-21T00:00:00+00:00"}
    - make_frame raises ValueError if channel not in CHANNELS
  </behavior>
  <action>
    Create services/api-gateway/app/ws/__init__.py as empty file.
    Create services/api-gateway/app/ws/channels.py exporting:
    - CHANNELS: frozenset[str] = frozenset({"safety-state","live-readiness","carry-ins","dashboard-snapshot"})
    - REDIS_CHANNEL_PREFIX: str = "ws:metrics:"
    - SCHEMA_VERSION: int = 1
    - redis_channel_name(channel: str) -> str — returns f"{REDIS_CHANNEL_PREFIX}{channel}"; raises ValueError if channel not in CHANNELS
    - parse_channel_from_redis_name(name: str) -> Optional[str] — strips prefix; returns the suffix only if it is in CHANNELS, else None
    - make_frame(channel: str, data: dict, ts: Optional[str] = None) -> dict — returns the {channel, schema_version, data, ts} shape; ts defaults to datetime.now(timezone.utc).isoformat(); raises ValueError if channel not in CHANNELS
    Create tests/unit/test_ws_channels.py with one test per behavior bullet above.
  </action>
  <verify>
    <automated>docker exec crypto-bot-api-gateway pytest services/api-gateway/tests/unit/test_ws_channels.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File services/api-gateway/app/ws/channels.py exists with `CHANNELS = frozenset({"safety-state","live-readiness","carry-ins","dashboard-snapshot"})`
    - `python -c "from app.ws.channels import CHANNELS, redis_channel_name; print(sorted(CHANNELS)); print(redis_channel_name('safety-state'))"` run inside crypto-bot-api-gateway prints `['carry-ins', 'dashboard-snapshot', 'live-readiness', 'safety-state']` and `ws:metrics:safety-state`
    - pytest test_ws_channels.py reports >=6 tests passed, 0 failed
  </acceptance_criteria>
  <done>Channel registry module exists and all unit tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: WsMetricsConnectionManager + RedisFanout</name>
  <files>services/api-gateway/app/ws/connection_manager.py, services/api-gateway/app/ws/redis_fanout.py, services/api-gateway/tests/unit/test_ws_connection_manager.py, services/api-gateway/tests/unit/test_ws_redis_fanout.py</files>
  <read_first>
    - services/api-gateway/app/ws/channels.py (the file created in Task 1)
    - services/api-gateway/app/main.py:184-294 (WebSocketManager — pattern for connection-set bookkeeping; this Task creates a SEPARATE class, leave WebSocketManager untouched)
    - services/api-gateway/requirements.txt (verify aioredis==2.0.1 line 40 — this is the redis.asyncio import surface in 2.x: `import redis.asyncio as aioredis`)
  </read_first>
  <behavior>
    WsMetricsConnectionManager:
    - subscribe(ws, channels: set[str]) records the (ws → channels) mapping; rejects channels not in CHANNELS (drops unknowns + logs warning); records a paused: bool defaulting to False per ws
    - unsubscribe(ws, channels: set[str]) removes channels from mapping; if remaining empty, drop ws entirely
    - pause(ws) / resume(ws) toggle the paused flag without touching the subscription set
    - broadcast_channel(channel, frame_dict) iterates all ws currently subscribed to `channel` AND not paused, sends frame_dict via ws.send_json(); on send failure removes ws
    - drop(ws) removes ws from all internal state (used on disconnect)
    - size() returns total connection count for the Prometheus gauge

    RedisFanout:
    - __init__(redis_url, connection_manager) stores both refs
    - async start(): connect to redis.asyncio, psubscribe to f"{REDIS_CHANNEL_PREFIX}*", spawn the asyncio reader task; expose the task as self._reader_task
    - async stop(): cancel reader task, close pubsub + connection
    - reader loop: on message → parse channel name via parse_channel_from_redis_name; if valid, deserialize the message body as JSON, call connection_manager.broadcast_channel(channel, frame); on JSON decode or unknown channel → log + drop
    - async publish(channel: str, frame: dict): publishes frame as JSON to f"{REDIS_CHANNEL_PREFIX}{channel}"; used by plan 13-02

    Tests (test_ws_connection_manager.py):
    - subscribe with valid channels then broadcast reaches the ws
    - subscribe with one valid + one invalid channel → only valid is recorded
    - paused ws does not receive broadcast; resumed ws does
    - unsubscribe to last channel drops ws from manager
    - send-failure during broadcast removes ws from manager

    Tests (test_ws_redis_fanout.py):
    - mock redis client; publish to ws:metrics:safety-state with a JSON body; reader loop calls broadcast_channel("safety-state", parsed_frame) exactly once
    - publish to ws:metrics:bogus → broadcast_channel NOT called; warning logged
    - reader loop handles JSONDecodeError gracefully (continues running)
  </behavior>
  <action>
    Create services/api-gateway/app/ws/connection_manager.py with WsMetricsConnectionManager class. Use a plain `dict[WebSocket, set[str]]` for subscriptions and a `set[WebSocket]` for paused; guard with `asyncio.Lock` only around modifications to keep semantics simple.
    Create services/api-gateway/app/ws/redis_fanout.py:
    - import redis.asyncio as aioredis  (aioredis 2.0.1 ships under redis.asyncio module)
    - RedisFanout.start() uses `await aioredis.from_url(self.redis_url).pubsub()` then `await pubsub.psubscribe(f"{REDIS_CHANNEL_PREFIX}*")`
    - Reader loop: `async for message in pubsub.listen():` with the `if message["type"] == "pmessage"` guard
    - On exceptions inside reader loop (any aioredis ConnectionError), schedule reconnect with exponential backoff 1s→30s cap; log every retry
    Create both test files using pytest-asyncio (`@pytest.mark.asyncio`). Use unittest.mock to stub WebSocket.send_json. For the fanout tests, monkey-patch aioredis.from_url to return a fake pubsub yielding pre-staged messages.
    Use `# noqa: F401` on any imports that other modules patch via `mock.patch("app.ws.redis_fanout.aioredis")` (project memory feedback_main_imports_autoflake.md).
  </action>
  <verify>
    <automated>docker exec crypto-bot-api-gateway pytest services/api-gateway/tests/unit/test_ws_connection_manager.py services/api-gateway/tests/unit/test_ws_redis_fanout.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File services/api-gateway/app/ws/connection_manager.py defines `class WsMetricsConnectionManager` with methods subscribe, unsubscribe, pause, resume, broadcast_channel, drop, size (verify with `grep -c "def \(subscribe\|unsubscribe\|pause\|resume\|broadcast_channel\|drop\|size\)" services/api-gateway/app/ws/connection_manager.py` returns 7)
    - File services/api-gateway/app/ws/redis_fanout.py defines `class RedisFanout` with start, stop, publish methods
    - pytest reports >=8 tests passed across both files (5 connection-manager + 3 fanout)
    - `grep -n "psubscribe.*ws:metrics" services/api-gateway/app/ws/redis_fanout.py` returns at least one hit
    - No modification to services/api-gateway/app/main.py:184-294 WebSocketManager class (verify with `git diff --stat services/api-gateway/app/main.py` showing only additions, not modifications to those lines)
  </acceptance_criteria>
  <done>ConnectionManager + RedisFanout exist with passing unit tests; no impact on existing /ws ticker route.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: /ws/metrics route + main.py lifespan wiring</name>
  <files>services/api-gateway/app/routes/ws_metrics.py, services/api-gateway/app/main.py, services/api-gateway/tests/unit/test_ws_metrics_route.py</files>
  <read_first>
    - services/api-gateway/app/ws/channels.py, connection_manager.py, redis_fanout.py (all from Task 1+2)
    - services/api-gateway/app/main.py:297-349 (lifespan function — the executor will add RedisFanout startup/shutdown here)
    - services/api-gateway/app/main.py:1241-1243 (router-include pattern)
    - services/api-gateway/app/auth_middleware.py:22-68 (token validation — verify_token returns Optional[TokenData])
    - services/api-gateway/app/auth_models.py — confirm verify_token import path
  </read_first>
  <behavior>
    /ws/metrics route handler (websocket endpoint):
    1. Accept connection (`await ws.accept()`)
    2. Read first frame; expect JSON {"action": "subscribe", "channels": [...], "token": "<bearer>"} within 5s (asyncio.wait_for); on timeout / non-JSON → close with 4400
    3. Validate token via verify_token(token); on None → close with 4401
    4. Look up user via get_user(token_data.username); on None or inactive → close with 4401
    5. Filter requested channels against CHANNELS enum (drop unknown, log warning); if zero valid → close with 4400
    6. connection_manager.subscribe(ws, valid_channels)
    7. Fetch one snapshot per subscribed channel via IN-PROCESS calls to the existing handler coroutines (NOT httpx self-call — cheaper, avoids loopback rate-limit accounting, matches the pattern Plan 13-02 SnapshotPoller uses). LATE imports inside the function body to break circular-import risk: `from app.main import get_safety_state, get_preflight_live_readiness` and `from app.routes.preflight_carry_ins import <handler_name_pinned_in_read_first>`; for dashboard-snapshot (does not yet exist before Plan 13-04 lands), emit a placeholder `make_frame(channel, {"data": None, "note": "snapshot endpoint not yet available"})` and log warning. Send each via ws.send_json wrapped in make_frame.
    8. Enter receive loop; accept further action frames {pause | resume | unsubscribe}. On any other action → close with 4400.
    9. Heartbeat: an asyncio.create_task running every 5s sends a heartbeat frame per subscribed-not-paused channel ONLY IF no real frame was sent for that channel in the last 5s. Track via per-(ws, channel) timestamp.
    10. On WebSocketDisconnect → connection_manager.drop(ws), cancel heartbeat task.

    main.py wiring:
    1. Import the new router at module top: `from app.routes.ws_metrics import router as ws_metrics_router, get_connection_manager, get_redis_fanout` with `# noqa: F401` if needed.
    2. In lifespan startup: instantiate WsMetricsConnectionManager(), instantiate RedisFanout(settings.redis_url, manager), await fanout.start(); store both on app.state.
    3. In lifespan shutdown: await fanout.stop().
    4. app.include_router(ws_metrics_router)

    Tests:
    - Connect to /ws/metrics, send subscribe with valid token + valid channels; receive >=1 snapshot frame within 1s
    - Connect with no first frame for >5s → server closes with 4400
    - Connect with invalid token in subscribe → server closes with 4401
    - Connect with subscribe containing 0 valid channels → server closes with 4400
    - After subscribe, send {"action":"pause"}; broadcast_channel is called but ws does not receive (verify via mock manager spy)
    - After {"action":"resume"}, ws receives next broadcast
    - Send {"action":"banana"} → server closes with 4400
  </behavior>
  <action>
    Create services/api-gateway/app/routes/ws_metrics.py:
    - `router = APIRouter()` and `@router.websocket("/ws/metrics")` handler implementing the 10-step protocol above.
    - Module-level singletons `_connection_manager` and `_redis_fanout` set by lifespan in main.py via `set_connection_manager(...)` / `set_redis_fanout(...)` helpers (or read from app.state via the websocket's `ws.app.state.ws_connection_manager`). Prefer reading from `ws.app.state` to avoid global mutation.
    - Token verification uses `from app.auth_middleware import verify_token` if exposed there, otherwise `from app.auth_models import verify_token` (both modules currently expose it; verify the existing import path with grep before writing — pin whichever exists today).
    - Self-call snapshots use in-process imports per behavior step 7 (LATE imports inside the handler body). On ImportError or AttributeError (dashboard-snapshot not yet wired before Plan 13-04 lands) emit `make_frame(channel, {"data": None, "note": "snapshot endpoint not yet available"})` and continue. Wrap each in-process call in `asyncio.wait_for(..., timeout=2.0)` so a stuck handler cannot freeze the WS subscribe path.
    - Heartbeat tracked via a `dict[tuple[id(ws), str], float]` of last-send times.

    Modify services/api-gateway/app/main.py:
    - Inside `lifespan` AFTER service_proxy.initialize(): instantiate manager, instantiate fanout, await fanout.start(), set both on app.state as `ws_connection_manager` and `ws_redis_fanout`. Log success.
    - In shutdown: await app.state.ws_redis_fanout.stop().
    - At module bottom near other include_router calls: `from app.routes.ws_metrics import router as ws_metrics_router` and `app.include_router(ws_metrics_router)`.
    - The router import line needs `# noqa: F401` if autoflake removes it (project rule from feedback_main_imports_autoflake.md).

    Create tests/unit/test_ws_metrics_route.py using fastapi.testclient.TestClient.websocket_connect (sync). For token: create a real token via `create_access_token({"sub": "testuser"})` and ensure a `testuser` exists in the in-memory user store via the conftest admin_client fixture or a direct create_user call.

    CRITICAL: Run pytest INSIDE the container — host pip has fastapi 0.136 which broke HTTPBearer auto_error (project memory note: container pins 0.109).
  </action>
  <verify>
    <automated>docker exec crypto-bot-api-gateway pytest services/api-gateway/tests/unit/test_ws_metrics_route.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File services/api-gateway/app/routes/ws_metrics.py exists and `grep -c "@router.websocket" services/api-gateway/app/routes/ws_metrics.py` returns >=1
    - File services/api-gateway/app/main.py contains the line `from app.routes.ws_metrics import router as ws_metrics_router` (with or without `# noqa: F401`) — verify with `grep -n "ws_metrics_router" services/api-gateway/app/main.py` returning >=2 hits (import + include)
    - main.py lifespan startup contains `await app.state.ws_redis_fanout.start()` or equivalent
    - pytest reports >=7 tests passed for the route
    - Boot smoke: after the plan's deploy step (Task 4), `docker logs crypto-bot-api-gateway 2>&1 | grep -i "RedisFanout"` shows a "started" or "connected" log line; no traceback
  </acceptance_criteria>
  <done>/ws/metrics route exists, wired into main.py lifespan, all unit tests green, container boots without errors.</done>
</task>

<task type="auto">
  <name>Task 4: Rebuild api-gateway image and verify lifespan boot</name>
  <files>(no source files — verification + deploy)</files>
  <read_first>
    - .claude/skills/deploy/SKILL.md
    - .claude/skills/verify-stack/SKILL.md
  </read_first>
  <action>
    Use the `deploy` skill: rebuild and recreate `api-gateway` so the new app/ws/ module + route + lifespan changes ship inside the container.
    Then verify the lifespan integration:
    1. Health check: `curl -s http://localhost:8000/health | python -m json.tool` — expect `"status": "healthy"` or `"status": "degraded"` (degraded acceptable if a backend is down) AND 200 response code.
    2. Log inspection: `docker logs crypto-bot-api-gateway 2>&1 | tail -50` — expect to see RedisFanout connect + pubsub subscribe log lines; NO traceback containing `RedisFanout`, `WsMetricsConnectionManager`, or `ws_metrics`.
    3. Negative WS smoke (auth path): `python3 -c "import asyncio, websockets, json; asyncio.run(websockets.connect('ws://localhost:8000/ws/metrics').__aenter__().send(json.dumps({'action':'subscribe','channels':['safety-state'],'token':'bogus'})))"` should observe the server close with code 4401 (use the websockets library that the host already has, or `wscat -c ws://localhost:8000/ws/metrics` then paste the subscribe frame manually).
    4. Redis subscriber proof: `docker exec crypto-bot-redis redis-cli PUBSUB CHANNELS 'ws:metrics:*'` returns at least one matched pattern OR `docker exec crypto-bot-redis redis-cli PUBSUB NUMSUB ws:metrics:safety-state` returns a number ≥ 0 without error (confirms the subscriber is connected to Redis pubsub).
  </action>
  <verify>
    <automated>curl -sf http://localhost:8000/health && docker logs crypto-bot-api-gateway 2>&1 | grep -iE 'RedisFanout|ws_metrics' | grep -iv 'error\|traceback' | head -3</automated>
  </verify>
  <acceptance_criteria>
    - `curl -sf http://localhost:8000/health` returns HTTP 200 with valid JSON
    - `docker logs crypto-bot-api-gateway` contains a log line matching `RedisFanout` AND does NOT contain a traceback containing `RedisFanout` or `ws_metrics`
    - Bogus-token subscribe closes with code 4401 (record close code from the websockets client or wscat session and paste into SUMMARY.md)
    - `docker exec crypto-bot-redis redis-cli PUBSUB NUMSUB ws:metrics:safety-state` returns without error (number itself may be 0 — no publisher yet)
  </acceptance_criteria>
  <done>api-gateway image rebuilt; /ws/metrics route reachable; RedisFanout connected to Redis; auth gate works.</done>
</task>

</tasks>

<verification>
- All unit tests (test_ws_channels.py + test_ws_connection_manager.py + test_ws_redis_fanout.py + test_ws_metrics_route.py) pass inside the container.
- api-gateway boots cleanly with RedisFanout running.
- /ws/metrics rejects unauthenticated subscriptions.
- Existing /ws ticker broadcast route at main.py:294 still works (regression check): `docker exec crypto-bot-api-gateway pytest services/api-gateway/tests/ -k "websocket" -v` shows pre-existing tests still green.
</verification>

<success_criteria>
- [ ] services/api-gateway/app/ws/ package exists with channels.py, connection_manager.py, redis_fanout.py
- [ ] /ws/metrics route accepts subscribe frame with valid token, emits snapshot frames matching `{channel, schema_version:1, data, ts}` schema
- [ ] Invalid token → close 4401; unknown action → close 4400; unknown channel → silently dropped from subscribe with warning log
- [ ] RedisFanout connected to redis://crypto-bot-redis:6379; psubscribes ws:metrics:*
- [ ] api-gateway container restarts cleanly via deploy skill, no traceback in logs
- [ ] WS-01 partially satisfied (publish side comes in Plan 13-02)
</success_criteria>

<output>
After completion, create `.planning/phases/13-real-time-websocket-push/13-01-SUMMARY.md` documenting:
- Files created and key class APIs
- Frame schema exactly as implemented (paste from channels.py)
- Sample subscribe + response frames (paste from manual wscat smoke)
- The bogus-token close code captured from Task 4
- Any deviations from this plan with justification
</output>
</content>
</invoke>