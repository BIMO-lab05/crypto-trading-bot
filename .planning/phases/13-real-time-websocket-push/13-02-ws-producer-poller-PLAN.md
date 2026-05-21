---
phase: 13-real-time-websocket-push
plan: 02
type: execute
wave: 2
depends_on:
  - 13-01
files_modified:
  - services/api-gateway/app/ws/snapshot_poller.py
  - services/api-gateway/app/ws/leader_lock.py
  - services/api-gateway/app/main.py
  - services/api-gateway/app/routes/ws_metrics.py
  - services/api-gateway/tests/unit/test_ws_snapshot_poller.py
  - services/api-gateway/tests/unit/test_ws_leader_lock.py
  - services/api-gateway/tests/integration/test_ws_multi_worker_coherence.py
autonomous: true
requirements:
  - WS-01
tags:
  - websocket
  - api-gateway
  - redis
  - producer

must_haves:
  truths:
    - "When safety-state JSON returned by /api/config/safety-state changes, a frame on the safety-state channel is published to Redis within 500ms"
    - "When carry-ins state file mutates and /api/preflight/carry-ins payload diffs, a frame on the carry-ins channel is published within 500ms"
    - "When live-readiness payload diffs, a frame on the live-readiness channel is published within 500ms"
    - "When dashboard-snapshot payload diffs, a frame on the dashboard-snapshot channel is published within 500ms"
    - "Two api-gateway workers running concurrently do NOT publish duplicate frames — Redis SETNX per (channel, poll-tick) leader lock ensures exactly one worker publishes per diff event"
    - "Both workers' subscribers receive the push within 500ms — the non-publishing worker's RedisFanout delivers the message to its locally connected WS clients (the actual cross-worker pub/sub proof, per ROADMAP success criterion 1)"
    - "If only one worker is healthy, it still publishes (leader lock with TTL prevents permanent lockout)"
    - "Heartbeat is emitted at most every 5s per channel even when payload is unchanged (so silent backend does not look like a stale connection)"
  artifacts:
    - path: "services/api-gateway/app/ws/snapshot_poller.py"
      provides: "SnapshotPoller — periodic poll-and-diff producer for the 4 channels"
      min_lines: 100
    - path: "services/api-gateway/app/ws/leader_lock.py"
      provides: "try_acquire_lock(redis, key, ttl_ms) coroutine using SET NX EX"
      min_lines: 30
  key_links:
    - from: "services/api-gateway/app/ws/snapshot_poller.py"
      to: "services/api-gateway/app/routes/ws_metrics.py"
      via: "in-process call into the four existing handler coroutines (NOT HTTP self-call — cheaper and avoids loopback rate-limit accounting)"
      pattern: "get_safety_state|get_preflight_live_readiness|get_dashboard_snapshot|carry_ins_endpoint"
    - from: "services/api-gateway/app/ws/snapshot_poller.py"
      to: "services/api-gateway/app/ws/redis_fanout.py"
      via: "fanout.publish(channel, frame)"
      pattern: "fanout.publish"
    - from: "services/api-gateway/app/ws/snapshot_poller.py"
      to: "redis://crypto-bot-redis:6379"
      via: "leader_lock SET ws:metrics:lock:<channel>:<tick> NX EX 1"
      pattern: "leader_lock"
---

<objective>
Land the producer side of `/ws/metrics`. A `SnapshotPoller` running in api-gateway's lifespan periodically (250ms cadence — chosen so worst-case latency stays under the 500ms ROADMAP criterion) computes each of the four channel snapshots, diffs against the last-published payload, and publishes via `RedisFanout.publish(channel, frame)` when the payload changes. Concurrent workers coordinate via a per-(channel, tick) Redis `SET NX EX` leader lock so duplicate frames never land on a client.

Purpose: Push events from server to clients. Plan 13-01 built the pipe; this plan turns on the tap.
Output: New `app/ws/snapshot_poller.py` + `app/ws/leader_lock.py` + lifespan wiring + multi-worker integration test.

Note: 4 tasks instead of the standard 2-3. Task 4 is intentionally a deploy + observe step (separated per the verify-stack project skill — "never declare working on HTTP 200 alone"). Tasks 1-3 are code; Task 4 is verification of the integrated producer side.

CONSTRAINT (architectural — non-negotiable): Phase 13 may NOT modify trading-engine or other backend services. Source-side mutation hooks are off the table. Centralized poll-and-diff inside api-gateway is the ONLY producer architecture available. The 250ms cadence is the design constraint that lets us hit the <500ms ROADMAP target (worst-case = one full poll period + Redis hop + client deserialize).
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

@.planning/phases/13-real-time-websocket-push/13-01-SUMMARY.md

@services/api-gateway/app/main.py
@services/api-gateway/app/ws/channels.py
@services/api-gateway/app/ws/redis_fanout.py
@services/api-gateway/app/ws/connection_manager.py
@services/api-gateway/app/routes/preflight_carry_ins.py

<interfaces>
<!-- From Plan 13-01 (already landed). -->

From services/api-gateway/app/ws/redis_fanout.py:
```python
class RedisFanout:
    async def publish(self, channel: str, frame: dict) -> None
    # Publishes JSON-encoded frame to ws:metrics:<channel>
```

From services/api-gateway/app/ws/channels.py:
```python
CHANNELS: frozenset[str]
SCHEMA_VERSION: int = 1
def make_frame(channel: str, data: dict, ts: Optional[str] = None) -> dict
```

From services/api-gateway/app/main.py (handler functions to call IN-PROCESS):
- `async def get_safety_state() -> dict`           at line 1050 (no path params; returns dict)
- `async def get_preflight_live_readiness() -> dict` at line 1175 (no params; returns dict)

From services/api-gateway/app/routes/preflight_carry_ins.py:
- Read the file fully on first task — confirm the handler function name + signature; current file is small (created Phase 10).

For dashboard-snapshot: the new aggregator endpoint `/api/dashboard/snapshot` does not exist yet (will land in Plan 13-04). For THIS plan: implement a placeholder `compute_dashboard_snapshot()` async function inside snapshot_poller.py that returns `{"data": None, "note": "dashboard-snapshot pending Plan 13-04"}`. Plan 13-04 will replace this with a real call into the new endpoint.

Redis lock pattern (SET NX EX):
```python
# redis.asyncio 2.x
ok = await redis.set(key, value, nx=True, ex=1)  # returns True if acquired, None/False if held
```
</interfaces>
</context>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| api-gateway worker → its own handler functions | trusted, in-process function call |
| api-gateway worker A → Redis (leader lock + publish) | trusted intra-cluster |
| api-gateway worker B → Redis (leader lock + publish) | trusted intra-cluster |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-13-07 | DoS | SnapshotPoller loop | mitigate | each poll cycle wrapped in try/except logging the failure and continuing; one handler raising must NOT crash the poller. Each handler call has a 2s asyncio.wait_for timeout so a stuck backend cannot freeze the poller. |
| T-13-08 | DoS via duplicate publish | RedisFanout.publish | mitigate | Redis `SET ws:metrics:lock:<channel>:<tick> 1 NX EX 1` leader lock. Tick = `int(time.time() * 4)` (250ms buckets). Only the worker that wins the SET NX publishes. If lock acquisition fails (lost the race) the worker still records its computed snapshot locally so the next change-detection works correctly — it just skips the publish step. |
| T-13-09 | Tampering | Frame data | mitigate | snapshot is computed by calling the existing handler functions directly — same code that powers the REST endpoint, so the data shape is identical. No untrusted input is admixed. |
| T-13-10 | Info disclosure | Lock key namespace | accept | lock keys are operational metadata, not sensitive. Redis is internal-only network. |
</threat_model>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Leader-lock helper (Redis SET NX EX)</name>
  <files>services/api-gateway/app/ws/leader_lock.py, services/api-gateway/tests/unit/test_ws_leader_lock.py</files>
  <read_first>
    - services/api-gateway/app/ws/redis_fanout.py (the redis.asyncio import pattern used in Plan 13-01)
    - services/api-gateway/app/config.py:80-95 (settings.redis_url)
  </read_first>
  <behavior>
    - `async def try_acquire_lock(redis, key: str, ttl_seconds: float) -> bool` returns True if SET NX EX acquired, False otherwise
    - `async def lock_key_for_tick(channel: str, tick: int) -> str` returns f"ws:metrics:lock:{channel}:{tick}"
    - When two concurrent calls race on the same key, exactly one returns True

    Tests:
    - Acquire a fresh key → True; second acquire of same key inside TTL → False
    - After TTL expires, lock can be re-acquired (use a 100ms TTL + asyncio.sleep(0.15))
    - Two concurrent asyncio.gather'd acquires on the same key → exactly one True, one False
  </behavior>
  <action>
    Create services/api-gateway/app/ws/leader_lock.py exporting:
    - `async def try_acquire_lock(redis, key: str, ttl_seconds: float) -> bool` — uses `redis.set(key, "1", nx=True, ex=max(1, int(ttl_seconds)))`. Note: redis.asyncio 2.x SET EX accepts seconds (integer). For sub-second TTL (which we want — 250ms tick + 1s safety margin), use `px=int(ttl_seconds * 1000)` instead of `ex=`. Implement as `px=int(ttl_seconds * 1000)`.
    - `def lock_key_for_tick(channel: str, tick: int) -> str` — returns f"ws:metrics:lock:{channel}:{tick}"
    - `def current_tick(now: Optional[float] = None, bucket_ms: int = 250) -> int` — returns int((now or time.time()) * 1000 // bucket_ms); pure function for tests.
    Create test_ws_leader_lock.py — use the same fake-Redis approach as Plan 13-01's fanout tests; for the live tests, an `@pytest.mark.integration` real-Redis test against the local crypto-bot-redis container is fine (skip if Redis unreachable).
  </action>
  <verify>
    <automated>docker exec crypto-bot-api-gateway pytest services/api-gateway/tests/unit/test_ws_leader_lock.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File services/api-gateway/app/ws/leader_lock.py exports `try_acquire_lock`, `lock_key_for_tick`, `current_tick` (verify: `grep -c '^\(async \)\?def \(try_acquire_lock\|lock_key_for_tick\|current_tick\)' services/api-gateway/app/ws/leader_lock.py` returns 3)
    - pytest reports >=3 tests passed
    - `python -c "from app.ws.leader_lock import lock_key_for_tick; print(lock_key_for_tick('safety-state', 12345))"` run inside the container prints `ws:metrics:lock:safety-state:12345`
  </acceptance_criteria>
  <done>Leader-lock helper exists, sub-second TTL works, tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: SnapshotPoller — poll-diff-publish loop</name>
  <files>services/api-gateway/app/ws/snapshot_poller.py, services/api-gateway/app/main.py, services/api-gateway/tests/unit/test_ws_snapshot_poller.py</files>
  <read_first>
    - services/api-gateway/app/main.py:1050-1172 (get_safety_state handler shape)
    - services/api-gateway/app/main.py:1175-1238 (get_preflight_live_readiness handler shape)
    - services/api-gateway/app/routes/preflight_carry_ins.py — read fully; confirm the handler function name (likely `get_carry_ins` or similar)
    - services/api-gateway/app/ws/channels.py (CHANNELS, make_frame)
    - services/api-gateway/app/ws/leader_lock.py (from Task 1)
    - services/api-gateway/app/ws/redis_fanout.py (publish signature)
  </read_first>
  <behavior>
    SnapshotPoller class:
    - __init__(fanout: RedisFanout, redis_client, poll_interval_ms: int = 250, heartbeat_interval_s: int = 5)
    - async start() → spawns the poll loop as an asyncio.Task; idempotent (no double-start)
    - async stop() → cancels the task, awaits cancellation
    - last_payload: dict[str, dict] — per-channel last snapshot we ATTEMPTED to publish (or successfully published when alone)
    - last_publish_at: dict[str, float] — per-channel last send timestamp (real or heartbeat)
    - Poll loop body, every poll_interval_ms:
        1. tick = current_tick()
        2. For each channel in CHANNELS:
            a. snapshot = await self._fetch(channel)  (calls the right handler; on exception → log + skip channel for this tick)
            b. changed = (snapshot != self.last_payload.get(channel))
            c. due_heartbeat = (time.time() - self.last_publish_at.get(channel, 0)) >= self.heartbeat_interval_s
            d. if changed OR due_heartbeat:
                lock_key = lock_key_for_tick(channel, tick)
                won = await try_acquire_lock(self.redis, lock_key, ttl_seconds=1.0)
                if won:
                    frame = make_frame(channel, snapshot if changed else {"heartbeat": True, "last_seen": self.last_payload.get(channel)})
                    await self.fanout.publish(channel, frame)
                    self.last_publish_at[channel] = time.time()
                # ALWAYS update last_payload locally so the local diff stays accurate
                if changed:
                    self.last_payload[channel] = snapshot
        3. await asyncio.sleep(poll_interval_ms / 1000)
    - _fetch(channel) maps:
        "safety-state" → await get_safety_state()
        "live-readiness" → await get_preflight_live_readiness()
        "carry-ins" → call the function exported from app/routes/preflight_carry_ins.py (resolve actual name during read_first)
        "dashboard-snapshot" → await self._fetch_dashboard_snapshot() — placeholder returning {"data": None, "note": "pending Plan 13-04"}; Plan 13-04 will override this method when it lands the real endpoint

    Tests (test_ws_snapshot_poller.py):
    - Inject a mock fanout (spy on publish); mock the 4 handler functions
    - First tick: all 4 handlers return their snapshot; poller publishes 4 frames (one per channel)
    - Second tick: handlers return the SAME data; poller publishes 0 frames (no change, heartbeat not yet due)
    - After heartbeat_interval_s sleep with handlers returning same data: poller publishes a heartbeat frame for each channel
    - Tick where one handler raises: other 3 channels still publish; raising channel logs warning, no crash
    - Two SnapshotPoller instances sharing the same Redis (use fakeredis or real container Redis): only one publish per (channel, tick) — leader lock works
  </behavior>
  <action>
    Create services/api-gateway/app/ws/snapshot_poller.py per the behavior spec above.
    For the in-process handler calls: import the handlers DIRECTLY from `app.main` and `app.routes.preflight_carry_ins`. This creates a circular-import risk because main.py also imports from app.ws — break the cycle by doing the import LATE (inside _fetch, or at module top guarded by `if TYPE_CHECKING`). Inline-import pattern is the same as the autoflake-survival pattern used elsewhere in main.py.
    Modify services/api-gateway/app/main.py lifespan: AFTER the RedisFanout.start() block, instantiate SnapshotPoller(fanout=fanout, redis_client=fanout._redis), call `await poller.start()`, store on app.state as `ws_snapshot_poller`. On shutdown, `await app.state.ws_snapshot_poller.stop()` BEFORE fanout.stop().
    Use `redis.asyncio.from_url(settings.redis_url)` to get the redis client for the lock — or expose `fanout._redis` as a public attribute `fanout.redis` so the poller can reuse it (preferred — one connection).

    For the carry-ins handler: read services/api-gateway/app/routes/preflight_carry_ins.py before writing this code and pin the exact function name. If the function reads request state from FastAPI Depends, write a thin wrapper `async def _call_carry_ins_internal() -> dict` that bypasses Depends by invoking the underlying business logic directly. If the handler does NOT use Depends (simple async function returning dict), call it directly.
  </action>
  <verify>
    <automated>docker exec crypto-bot-api-gateway pytest services/api-gateway/tests/unit/test_ws_snapshot_poller.py -v</automated>
  </verify>
  <acceptance_criteria>
    - File services/api-gateway/app/ws/snapshot_poller.py exists with `class SnapshotPoller`
    - `grep -c "async def _fetch\|fanout.publish\|try_acquire_lock" services/api-gateway/app/ws/snapshot_poller.py` returns >=3 (one per concern)
    - main.py lifespan: `grep -n "SnapshotPoller\|ws_snapshot_poller" services/api-gateway/app/main.py` returns >=3 hits (import + start + stop)
    - pytest reports >=5 tests passed for the poller
    - No syntax error introduced into main.py: `docker exec crypto-bot-api-gateway python -c "import app.main"` exits 0
  </acceptance_criteria>
  <done>Poller class running in lifespan, diff-and-publish logic verified by unit tests.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Multi-worker coherence integration test</name>
  <files>services/api-gateway/tests/integration/test_ws_multi_worker_coherence.py</files>
  <read_first>
    - services/api-gateway/app/ws/snapshot_poller.py (Task 2)
    - services/api-gateway/app/ws/leader_lock.py (Task 1)
    - docker-compose.unified.yml (verify api-gateway service definition; confirm Redis is at crypto-bot-redis:6379 on the docker network)
  </read_first>
  <behavior>
    The integration test does NOT spin up two uvicorn workers (too heavyweight). Instead it simulates two workers IN-PROCESS, each with its OWN RedisFanout + WsMetricsConnectionManager, both connected to the same real Redis (crypto-bot-redis:6379). This setup proves the ROADMAP criterion exactly: "mutate state on worker A and assert both A's and B's subscribers receive the push within 500ms via Redis pub/sub fanout".

    Test fixtures per "worker":
    - workerA: RedisFanout_A + WsMetricsConnectionManager_A + SnapshotPoller_A + a StubWebSocket_A (test double that records every send_json call with a wall-clock timestamp). Stub subscribed to safety-state via WsMetricsConnectionManager_A.subscribe(stub, {"safety-state"}).
    - workerB: RedisFanout_B + WsMetricsConnectionManager_B + SnapshotPoller_B + StubWebSocket_B. Stub subscribed to safety-state via WsMetricsConnectionManager_B.subscribe(stub, {"safety-state"}).
    - Both fanouts share the same Redis URL — Redis is the bus.

    The test proves three assertions in one run:
    1. **Leader-lock dedup**: across a 1s window of both pollers polling at 250ms cadence, a single state change is PUBLISHED exactly once across both pollers (not duplicated). Verify by spying on Redis-side publish call counts via `MONITOR` or a publish-side counter.
    2. **Cross-worker delivery (the real ROADMAP criterion)**: after the state change, BOTH StubWebSocket_A and StubWebSocket_B have received the frame within 500ms wall-clock. Each stub records its receive timestamp; assert `t_received - t_state_change < 0.500` for BOTH stubs. The non-publisher worker proves cross-fanout delivery is working — that is what pub/sub buys us.
    3. **No-publisher-elected-still-progresses**: when one poller is cancelled mid-test, the other still publishes; both stubs still see the change.

    The state-change injection: each SnapshotPoller's _fetch is monkey-patched to return v1 for the first 500ms then v2 — the change-detection diff fires on the next tick.

    The test requires the running crypto-bot-redis container. Mark as `@pytest.mark.integration` and skip if Redis unreachable. Cleanup: drain Redis pub/sub `ws:metrics:lock:*` keys and `ws:metrics:*` channel state before/after the test.
  </behavior>
  <action>
    Create services/api-gateway/tests/integration/test_ws_multi_worker_coherence.py.
    Use `redis.asyncio.from_url("redis://crypto-bot-redis:6379")` if RUN_IN_CONTAINER else "redis://localhost:6379". Provide both via env so the test runs both from inside the container (via `docker exec ... pytest`) and from host CI.
    StubWebSocket double: a class with an async `send_json(self, payload)` method that appends `(time.monotonic(), payload)` to a list. NO real WebSocket — the assertion is on what the ConnectionManager actually delivered.
    Wire pair A and pair B in the test setup:
      manager_A = WsMetricsConnectionManager(); fanout_A = RedisFanout(redis_url, manager_A); await fanout_A.start()
      stub_A = StubWebSocket(); await manager_A.subscribe(stub_A, {"safety-state"})
      (mirror for B)
    For the publish-count assertion: install a counting wrapper around each RedisFanout's publish (or use a Redis-side `MONITOR` parse — the wrapper is simpler).
    State change injection: each SnapshotPoller._fetch is monkey-patched to return safety-state-v1 for the first 500ms, then v2. Use shared `nonlocal` ref.
    Assertions:
      - assert publish_count[fanout_A] + publish_count[fanout_B] == 1   # leader-lock dedup
      - assert len(stub_A.received) >= 1 AND last received payload's data.emergency_stop.active == v2_value  # delivery to publisher's worker
      - assert len(stub_B.received) >= 1 AND last received payload's data.emergency_stop.active == v2_value  # delivery to NON-publisher's worker (the cross-fanout proof)
      - assert (stub_A.received[-1][0] - t_state_change) < 0.500 AND (stub_B.received[-1][0] - t_state_change) < 0.500  # both within 500ms
    Cleanup in `finally:`: cancel both pollers, stop both fanouts, flush `ws:metrics:lock:*` keys via `redis-cli --scan --pattern 'ws:metrics:lock:*' | xargs redis-cli del` or equivalent (in Python: scan iter + delete).
  </action>
  <verify>
    <automated>docker exec crypto-bot-api-gateway pytest services/api-gateway/tests/integration/test_ws_multi_worker_coherence.py -v --tb=short</automated>
  </verify>
  <acceptance_criteria>
    - Test file exists and is marked `@pytest.mark.integration`
    - Test passes inside the container (assumes crypto-bot-redis is running, which it is in the normal stack)
    - Three assertions are present (verify via `grep -cE 'publish_count|stub_A.received|stub_B.received' services/api-gateway/tests/integration/test_ws_multi_worker_coherence.py` returns >=4): publish_count dedup, stub_A delivery, stub_B delivery (cross-fanout), per-stub <500ms timing
    - On test cleanup, Redis lock keys with prefix `ws:metrics:lock:*` are flushed; failure to clean up is non-blocking (TTL evicts them)
    - Test output (use `-s`) records the measured stub_A and stub_B receive latencies in ms; capture in SUMMARY
  </acceptance_criteria>
  <done>Multi-worker coherence proven; leader lock validates the no-duplicate-publish contract.</done>
</task>

<task type="auto">
  <name>Task 4: Rebuild api-gateway and observe producer on Redis</name>
  <files>(no source files — deploy + verify)</files>
  <read_first>
    - .claude/skills/deploy/SKILL.md
    - .claude/skills/verify-stack/SKILL.md
  </read_first>
  <action>
    Use the `deploy` skill to rebuild + recreate api-gateway with the new SnapshotPoller wired in.

    Then verify the producer with two parallel observations:

    1. Subscribe to Redis pub/sub from outside api-gateway and watch for frames:
       `docker exec crypto-bot-redis redis-cli PSUBSCRIBE 'ws:metrics:*'`
       Run in one terminal; within 5s expect to see a message on `ws:metrics:safety-state` (heartbeat at least; also a real frame if any state changed during boot).

    2. Trigger a state mutation and confirm a frame is published within 500ms:
       From a second terminal: `touch safety/EMERGENCY_STOP` (this changes /api/config/safety-state's `emergency_stop.active` from false→true).
       In the first terminal (PSUBSCRIBE session), capture a wall-clock timestamp BEFORE the touch and after the next message arrives. Compute the delta. Expected: delta_ms < 500.
       Then `rm safety/EMERGENCY_STOP` to restore.

    3. Confirm no traceback in logs:
       `docker logs crypto-bot-api-gateway 2>&1 | tail -100 | grep -iE 'SnapshotPoller|RedisFanout' | grep -iv 'started\|connected' | head -10`
       Expected: empty output (no error/warning beyond startup info).
  </action>
  <verify>
    <automated>timeout 6 docker exec crypto-bot-redis redis-cli --timeout 5 PSUBSCRIBE 'ws:metrics:*' 2>&1 | grep -m1 'safety-state\|live-readiness\|carry-ins\|dashboard-snapshot' | head -1</automated>
  </verify>
  <acceptance_criteria>
    - The PSUBSCRIBE one-liner returns at least one matching channel name within 6 seconds (heartbeat alone is sufficient — proves producer is alive and publishing to Redis)
    - Manual EMERGENCY_STOP toggle observation: delta between touch and observed frame < 500ms (record the actual measured delta in SUMMARY)
    - `docker logs crypto-bot-api-gateway 2>&1 | grep -i 'SnapshotPoller'` contains a "started" log line and zero traceback lines
    - `docker exec crypto-bot-redis redis-cli KEYS 'ws:metrics:lock:*'` returns at most a handful of keys (per-tick locks expire in 1s); confirms lock is being acquired
  </acceptance_criteria>
  <done>Producer is alive on Redis; state mutations propagate to Redis within 500ms; multi-worker coordination validated by Task 3.</done>
</task>

</tasks>

<verification>
- WS-01 producer side is functional: state changes on backing endpoints → Redis pub/sub message within 500ms.
- Two-poller coherence proven via integration test.
- Heartbeat at most every 5s per channel.
- Leader lock prevents duplicate publishes across workers.
</verification>

<success_criteria>
- [ ] services/api-gateway/app/ws/snapshot_poller.py exists with SnapshotPoller class running in lifespan
- [ ] services/api-gateway/app/ws/leader_lock.py exists with try_acquire_lock + lock_key_for_tick + current_tick
- [ ] Unit tests for poller + leader-lock green inside container
- [ ] Integration test test_ws_multi_worker_coherence.py green inside container
- [ ] Manual smoke: redis-cli PSUBSCRIBE 'ws:metrics:*' shows messages within 6s of container boot
- [ ] Manual smoke: EMERGENCY_STOP toggle observed on Redis pub/sub within 500ms
- [ ] WS-01 fully satisfied (server route + producer both operational)
</success_criteria>

<output>
After completion, create `.planning/phases/13-real-time-websocket-push/13-02-SUMMARY.md` documenting:
- SnapshotPoller cadence (250ms confirmed)
- Heartbeat interval (5s confirmed)
- Measured push-to-Redis latency from the EMERGENCY_STOP toggle smoke (raw ms number)
- Number of locks acquired during a 10s observation window (proves coordination active)
- Any handler-function name resolutions for carry-ins endpoint
</output>
</content>
</invoke>