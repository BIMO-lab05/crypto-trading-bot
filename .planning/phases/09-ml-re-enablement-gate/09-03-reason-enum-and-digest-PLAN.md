---
id: 09-03-reason-enum-and-digest
phase: 09-ml-re-enablement-gate
plan: 03
wave: 1
type: execute
mode: standard
depends_on: []  # Wave 1; this plan OWNS `app.aggregation.ml_gate_reasons` (including the new `set_current_reason`/`get_current_reason` helpers consumed by Plan 09-02). Plan 09-02 IMPORTS from this plan's module — the dep arrow runs 09-02 → 09-03, not the reverse. No `files_modified` overlap with 09-02 or 09-01.
autonomous: true
requirements:
  - MLGATE-03
files_modified:
  - services/trading-engine/app/aggregation/ml_gate_reasons.py
  - services/trading-engine/app/aggregation/enhanced_aggregator.py
  - services/trading-engine/app/signal_aggregator.py
  - services/trading-engine/app/handlers/ml_gate_reasons.py  # NEW unauthenticated read-only observability endpoint per D-09-03-07 (Phase 8 D-09 precedent) (Path A — closes checker Blocker 2)
  - services/trading-engine/app/main.py  # router include + F401 import for the new handler
  - services/notification-service/app/alert_manager.py
  - services/notification-service/app/routers/alerts.py
  - services/notification-service/app/scheduler/ml_gate_digest.py  # NEW notification-service-side scheduled fetcher (Path A — closes checker Blocker 2)
  - services/notification-service/tests/test_daily_digest_ml_gate.py
  - services/notification-service/tests/test_ml_gate_digest_scheduler.py  # NEW — integration test for the cross-service fetch + dispatch (closes checker Blocker 2 delivery clause)
  - services/trading-engine/tests/test_ml_gate_reasons.py
  - services/trading-engine/tests/test_ml_gate_reasons_endpoint.py  # NEW — endpoint unit test
  - tests/integration/test_mlgate_reason_grep_gate.py
tags:
  - mlgate
  - reason-enum
  - logging
  - telegram-digest
  - notification-service
  - grep-gates
  - cross-service-wiring
  - phase-9
decisions:
  - D-09-03-01 — **Wording-bug locus correction**: ROADMAP Phase 9 success criterion #3 and REQUIREMENTS.md MLGATE-03 reference `technical-analysis` service emissions, but verified grep over `services/technical-analysis/` returns ZERO matches for `enable_ml`, `ENABLE_ML`, or `ml_predictions`. The actual `enable_ml_predictions` Pydantic field lives in `services/trading-engine/app/config.py:90`; the only branch points where `use_ml = False` are taken live in `services/trading-engine/app/aggregation/enhanced_aggregator.py` and `services/trading-engine/app/signal_aggregator.py:1125`. Emissions land where the toggle is actually consumed (trading-engine), NOT in TA service. Same pattern as Phase 8's `tournament_results` → `leaderboard` correction (08-01-SUMMARY.md "Decisions Made"). REQUIREMENTS.md wording cleanup deferred to follow-up docs commit. All acceptance criteria below reference trading-engine emission sites.
  - D-09-03-02 — **Reason enum module path**: enum lives at `services/trading-engine/app/aggregation/ml_gate_reasons.py` (next to the consumer aggregators). Defined as a `typing.Literal` for type-checking AND a tuple constant for runtime guard. Mirror of `services/trading-engine/app/preflight/types.py::Status` (Phase 8 pattern). Scope is **disabled-event emissions only** — Plan 09-02's lifespan auto-flip event uses a separate local tuple that includes `dsr_above_gate` (six members vs this module's five); the two enums share five members but are intentionally split because the auto-flip carries a `direction` field (enabled/disabled) that the per-cycle emissions do not. See interfaces block for the full two-enum rationale.
  - D-09-03-03 — **Log literal contract**: every emission MUST contain the contiguous substring `"ML predictions disabled reason=<value>"` where `<value>` is one of the 5 enum members. This is the literal that the CI grep gate anchors on. f-string fragmentation (`f"ML predictions disabled reason={r}"`) is acceptable because the f-string starts with the literal `"ML predictions disabled reason="` as a continuous substring; the runtime-formatted value just appends. Concatenation patterns that break the literal (e.g. `"ML predictions " + "disabled reason=" + r`) are FORBIDDEN — the grep gate would not match.
  - D-09-03-04 — **Digest aggregation source — UPDATED to deliver cross-service wiring this phase (closes checker Blocker 2)**: the daily digest reads reason counts from a NEW in-process counter populated by the emission sites AND auto-flip outcomes. The counter is exposed via a new unauthenticated read-only observability endpoint `GET /api/preflight/ml-gate-reason-counts` on the trading-engine (handler module `services/trading-engine/app/handlers/ml_gate_reasons.py` — sibling to `handlers/preflight.py`). The notification-service's daily-digest scheduler fetches this dict via `httpx.AsyncClient` (existing inter-service HTTP pattern at `notification-service/app/telegram_notifier.py:96` and `channels/telegram_client.py:135`), then passes the result as the `ml_gate_reason_counts` kwarg to `send_daily_summary()`. The integration test seeds counter state via the new endpoint (or via direct module-level injection where mocking the HTTP call is cleaner), triggers the digest tick, asserts a Telegram dispatch capture (mocked at the telegram_client layer) with the rendered reason-counts payload. Per checker Blocker 2 Path A recommendation: HTTP-pull pattern matches notification-service's existing inbound integration shape; no new auth surface — extends the existing unauthenticated read-only observability precedent at `services/trading-engine/app/handlers/preflight.py:35` (unauthenticated read-only because reason counts are public-grade observability data, same disclosure level as DSR values per Phase 8 D-09).
  - D-09-03-05 — **Wording-bug carry-in (same as 09-01, 09-02)**: `tournament_results` table reference is a documentation bug; this plan does not touch that table at all (no DSR query in this plan — all queries live in Plan 09-02's extended `check_dsr_evidence`).
  - D-09-03-06 — **Cross-plan reason-state contract with 09-02 (closes checker Blocker 1)**: `services/trading-engine/app/aggregation/ml_gate_reasons.py` exposes a module-level state cache via `set_current_reason(reason: MLGateReason) -> None` and `get_current_reason() -> MLGateReason`. The state defaults to `"manual_override"` at module-import time (no auto-flip has fired yet) and is updated exactly once per `auto_flip_ml_predictions()` call by Plan 09-02 (the ONLY writer of this state — Plan 09-02 imports `set_current_reason` from this module). The signal-aggregator emission sites (E1, E2, E3 — see interfaces block) use `get_current_reason()` as the DEFAULT reason argument to `log_ml_disabled()`; callers may pass an explicit `reason=` to override for test-only manual disables. This wires the truthful auto-flip outcome through to every per-cycle emission, making ROADMAP SC#3's example `(e.g., no_evidence: 3, dsr_below_gate: 1)` reproducible in production. Without this contract, every per-cycle emission would log `"manual_override"` regardless of true cause (the original checker Blocker 1 — dimension-7b scope reduction).
  - D-09-03-07 — **Cross-service wiring contract for daily digest (closes checker Blocker 2)**: the trading-engine exposes `GET /api/preflight/ml-gate-reason-counts` as an unauthenticated read-only observability endpoint returning `snapshot_reasons() -> dict[str, int]`. The notification-service runs a scheduled fetcher in a background task (`services/notification-service/app/scheduler/ml_gate_digest.py`) that:
    1. Wakes once per digest period (default: 24h cron via existing notification-service scheduler — uses `apscheduler.schedulers.asyncio.AsyncIOScheduler` if present, else a simple `asyncio.create_task` loop).
    2. Calls `httpx.AsyncClient().get("http://trading-engine:8005/api/preflight/ml-gate-reason-counts")` (URL configurable via env var `TRADING_ENGINE_URL`, default `http://trading-engine:8005` matching the docker-compose service name).
    3. On 200: parses the JSON body into `dict[str, int]`; calls `alert_manager.send_daily_summary(..., ml_gate_reason_counts=parsed)`.
    4. On any non-200 / connection error: logs a warning and calls `send_daily_summary(..., ml_gate_reason_counts=None)` — the digest still ships, just without the ML-gate section (graceful degradation; same safe-default discipline as Phase 8).
    5. Uses a short timeout (≤5s — matches the existing `telegram_client.py:135` pattern) so a slow trading-engine cannot block the digest.
    The integration test `test_ml_gate_digest_scheduler.py` seeds counter state on the trading-engine side (via direct `record_ml_gate_event` calls or via FastAPI TestClient on the new endpoint), triggers the scheduled fetcher, intercepts the Telegram dispatch via `monkeypatch.setattr` on `telegram_client.TelegramClient.send_message`, and asserts the captured payload contains the rendered `ml_gate_reasons:` block with the correct counts. Per checker Blocker 2's Path A locked recommendation.
must_haves:
  truths:
    - "Every emission of `ENABLE_ML_PREDICTIONS=false` in trading-engine's signal-aggregation path logs a contiguous literal `\"ML predictions disabled reason=<value>\"` where `<value>` is one of the 5-member enum."
    - "The disabled-event reason enum is defined in exactly ONE place (`services/trading-engine/app/aggregation/ml_gate_reasons.py`) and imported by all disabled-event emission sites in trading-engine."
    - "CI grep gate `test_mlgate_reason_field_present` FAILS if a literal `\"ML predictions disabled\"` substring exists in `services/trading-engine/app/` without a `reason=` field on the same line."
    - "Telegram daily digest template renders a `ML Gate Reasons (24h): no_evidence: <N>, dsr_below_gate: <M>, ...` line when `ml_gate_reason_counts` kwarg is provided; unit test asserts the rendered text contains all 5 enum members when each has count ≥1."
    - "Reason enum tuple in `ml_gate_reasons.py` is exactly `(\"no_evidence\", \"dsr_below_gate\", \"evidence_stale\", \"regime_shift\", \"manual_override\")` — five members, no more, no fewer."
    - "**All 5 enum reasons are reachable in production (closes checker Blocker 1)**: a unit test parametrized over `(no_evidence, dsr_below_gate, evidence_stale, regime_shift, manual_override)` seeds each cause path (auto-flip outcomes for the first 3; explicit `reason=` argument for `regime_shift` and `manual_override`) and asserts `log_ml_disabled()` emits the matching literal AND `snapshot_reasons()[reason] >= 1` after the call."
    - "**Cross-plan reason-state propagation (D-09-03-06)**: when Plan 09-02's `auto_flip_ml_predictions()` calls `set_current_reason(\"dsr_below_gate\")` (or any disabled-event reason), a subsequent signal-aggregator emission site call to `log_ml_disabled()` (with no explicit reason argument) emits `\"ML predictions disabled reason=dsr_below_gate\"` — verified by a unit test that exercises this propagation."
    - "**SC#4 cross-service delivery (closes checker Blocker 2)**: when `snapshot_reasons()` returns a non-empty dict on the daily-digest tick, the notification-service scheduled fetcher pulls the dict via HTTP from the trading-engine's `/api/preflight/ml-gate-reason-counts` endpoint, forwards it to `send_daily_summary`, and the rendered Telegram digest contains an `ML Gate Reasons (24h):` block reflecting those counts. An integration test captures the Telegram dispatch (mocked at the `TelegramClient.send_message` layer) and asserts the payload contains the correct counts in canonical reason order."
  artifacts:
    - path: "services/trading-engine/app/aggregation/ml_gate_reasons.py"
      provides: "Reason enum (Literal + tuple), in-process counter, current-reason cache (D-09-03-06), helper functions"
      exports: ["MLGateReason", "ML_GATE_REASONS", "record_ml_gate_event", "snapshot_reasons", "log_ml_disabled", "set_current_reason", "get_current_reason", "reset_counter"]
      min_lines: 80
    - path: "services/trading-engine/app/aggregation/enhanced_aggregator.py"
      provides: "ML-disabled-branch log emissions that read the live truthful reason from get_current_reason()"
      contains: "ML predictions disabled reason="
    - path: "services/trading-engine/app/signal_aggregator.py"
      provides: "ML-disabled-branch log emission on the fallback Phase-1 aggregation path; reads get_current_reason()"
      contains_2: "ML predictions disabled reason="
    - path: "services/trading-engine/app/handlers/ml_gate_reasons.py"
      provides: "NEW unauthenticated read-only GET /api/preflight/ml-gate-reason-counts observability endpoint (D-09-03-07 — Path A cross-service wiring)"
      contains_6: "snapshot_reasons"
      contains_7: "/api/preflight"
    - path: "services/notification-service/app/alert_manager.py"
      provides: "send_daily_summary extended with ml_gate_reason_counts kwarg + rendered digest section"
      contains_3: "ml_gate_reason_counts"
    - path: "services/notification-service/app/scheduler/ml_gate_digest.py"
      provides: "NEW scheduled fetcher: cron-driven httpx.AsyncClient GET against trading-engine; forwards reason counts to send_daily_summary (D-09-03-07 — closes checker Blocker 2 delivery clause)"
      contains_8: "ml-gate-reason-counts"
    - path: "services/notification-service/tests/test_daily_digest_ml_gate.py"
      provides: "Unit test asserting the digest renders ML-gate reason counts correctly (≥4 cases)"
      min_tests: 4
    - path: "services/notification-service/tests/test_ml_gate_digest_scheduler.py"
      provides: "Integration test: fetch counts via HTTP from trading-engine endpoint, dispatch Telegram (mocked), assert payload (closes checker Blocker 2 SC#4 delivery clause)"
      min_tests: 3
    - path: "tests/integration/test_mlgate_reason_grep_gate.py"
      provides: "CI grep gate enforcing every `ML predictions disabled` literal carries a `reason=` field"
  key_links:
    - from: "services/trading-engine/app/aggregation/enhanced_aggregator.py"
      to: "services/trading-engine/app/aggregation/ml_gate_reasons.py::log_ml_disabled"
      via: "function call inside the `if not self.use_ml` branch — reason defaults to get_current_reason()"
      pattern: "log_ml_disabled\\(.*\\)"
    - from: "services/trading-engine/app/signal_aggregator.py"
      to: "services/trading-engine/app/aggregation/ml_gate_reasons.py::log_ml_disabled"
      via: "function call on the fallback-to-Phase-1 branch at line 1125"
      pattern: "log_ml_disabled"
    - from: "services/trading-engine/app/handlers/ml_gate_reasons.py"
      to: "services/trading-engine/app/aggregation/ml_gate_reasons.py::snapshot_reasons"
      via: "GET /api/preflight/ml-gate-reason-counts handler — returns snapshot_reasons() as JSON dict"
      pattern: "snapshot_reasons\\(\\)"
    - from: "services/notification-service/app/scheduler/ml_gate_digest.py"
      to: "services/trading-engine/app/handlers/ml_gate_reasons.py::/api/preflight/ml-gate-reason-counts"
      via: "httpx.AsyncClient().get(... TRADING_ENGINE_URL + '/api/preflight/ml-gate-reason-counts' ...)"
      pattern: "ml-gate-reason-counts"
    - from: "services/notification-service/app/scheduler/ml_gate_digest.py"
      to: "services/notification-service/app/alert_manager.py::send_daily_summary"
      via: "alert_manager.send_daily_summary(..., ml_gate_reason_counts=<fetched dict>)"
      pattern: "ml_gate_reason_counts="
    - from: "services/notification-service/app/alert_manager.py::send_daily_summary"
      to: "ml_gate_reason_counts kwarg → digest message body"
      via: "f-string interpolation in the message template"
      pattern: "ml_gate_reason_counts"
    - from: "Plan 09-02's `app/lifespan/ml.py::auto_flip_ml_predictions`"
      to: "services/trading-engine/app/aggregation/ml_gate_reasons.py::set_current_reason"
      via: "cross-plan import: `from app.aggregation.ml_gate_reasons import set_current_reason` (Plan 09-02 IMPORTS — D-09-03-06)"
      pattern: "set_current_reason\\("

coverage_trace:
  - id: MLGATE-03
    source: "REQUIREMENTS.md MLGATE-03 + ROADMAP Phase 9 success criteria #3 and #4"
    tasks: [task-1, task-2, task-3]
---

<objective>
Deliver MLGATE-03: a structured-reason enum for every "ML predictions disabled" event in trading-engine's signal-aggregation path; a cross-plan in-process reason-state cache that lets Plan 09-02's auto-flip outcome flow into every per-cycle emission (closes checker Blocker 1); a CI grep gate that blocks any bare `"ML predictions disabled"` literal without a `reason=` field; an unauthenticated read-only observability endpoint on the trading-engine exposing the reason counts (extends Phase 8 D-09 precedent); a scheduled fetcher in notification-service that pulls the counts and ships a daily Telegram digest aggregating them (closes checker Blocker 2 — SC#4 cross-service delivery).

Purpose: the 5-member enum (`no_evidence`, `dsr_below_gate`, `evidence_stale`, `regime_shift`, `manual_override`) turns "ML is off" from a single bit into actionable diagnostic state — the operator can see WHY ML is off without log-grepping by hand. Plan 09-02's `MLGATE_AUTO_FLIP` event vocabulary is a superset (6 members — adds `dsr_above_gate` for the enabled direction); the two enums share 5 members and Plan 09-02 IMPORTS `set_current_reason` from this plan's module to propagate the truthful reason into the per-cycle emission sites. The daily-digest cross-service wiring (D-09-03-07) closes the loop end-to-end: from auto-flip → in-process cache → per-cycle log emission + counter increment → HTTP endpoint → notification-service scheduled fetcher → Telegram digest delivery. This is the **deliver-this-phase** scope per checker Blocker 2 (no "v1.2 follow-up" deferral).

Output:
- New module `services/trading-engine/app/aggregation/ml_gate_reasons.py` — single source of truth for the enum + in-process counter + `log_ml_disabled` helper + `set_current_reason`/`get_current_reason` cross-plan cache (D-09-03-06).
- Edits to `enhanced_aggregator.py` and `signal_aggregator.py` to call `log_ml_disabled()` on every `use_ml=False` branch — default reason argument reads from `get_current_reason()` so the auto-flip outcome propagates (closes Blocker 1).
- New handler `services/trading-engine/app/handlers/ml_gate_reasons.py` — unauthenticated read-only `GET /api/preflight/ml-gate-reason-counts` endpoint (sibling to `handlers/preflight.py`; extends Phase 8 D-09 precedent).
- New scheduler `services/notification-service/app/scheduler/ml_gate_digest.py` — cron-driven httpx fetcher; forwards counts to `send_daily_summary` (closes Blocker 2).
- Extended `notification-service/app/alert_manager.py::send_daily_summary` with `ml_gate_reason_counts` kwarg + digest template tweak.
- Unit tests in `services/trading-engine/tests/test_ml_gate_reasons.py` (5-reason-reachability parametrize + cross-plan propagation), `services/trading-engine/tests/test_ml_gate_reasons_endpoint.py` (endpoint smoke), `services/notification-service/tests/test_daily_digest_ml_gate.py` (template render), and `services/notification-service/tests/test_ml_gate_digest_scheduler.py` (cross-service integration with Telegram mock).
- CI grep gate `tests/integration/test_mlgate_reason_grep_gate.py`.
</objective>

<execution_context>
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/workflows/execute-plan.md
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/STATE.md
@.planning/phases/08-pre-live-preflight/08-CONTEXT.md
@.planning/phases/08-pre-live-preflight/08-01-SUMMARY.md

@services/trading-engine/app/aggregation/enhanced_aggregator.py
@services/trading-engine/app/signal_aggregator.py
@services/trading-engine/app/config.py
@services/trading-engine/app/handlers/preflight.py
@services/trading-engine/app/main.py
@services/notification-service/app/alert_manager.py
@services/notification-service/app/routers/alerts.py
@services/notification-service/app/main.py
@services/notification-service/app/telegram_notifier.py
@services/notification-service/app/channels/telegram_client.py
@tests/integration/test_preflight_grep_gates.py
@services/trading-engine/app/preflight/types.py

<interfaces>
<!-- Contracts the executor will consume — extracted from codebase -->

From `services/trading-engine/app/aggregation/enhanced_aggregator.py:55-78` (existing init — emission site #1):
```python
self.use_ml = self.settings.enable_ml_predictions
...
logger.info(
    f"EnhancedAggregator initialized "
    f"(ML={self.use_ml}, MTF={self.use_multi_timeframe})"
)
```

From `services/trading-engine/app/aggregation/enhanced_aggregator.py:122-135` (the False-branch — emission site #2; currently appends `"ML_DISABLED"` to task_names but emits no structured-reason log):
```python
if self.use_ml:
    tasks.append(self._fetch_ml_prediction(symbol, interval))
    task_names.append("ML")
else:
    tasks.append(asyncio.sleep(0))  # Dummy task
    task_names.append("ML_DISABLED")
```

From `services/trading-engine/app/signal_aggregator.py:1118-1138` (emission site #3 — the fallback path when `enable_ml_predictions=False` is taken):
```python
# Use enhanced aggregation if enabled
if use_phase3 and self.settings.enable_ml_predictions:
    signal = await self.aggregate_signals_enhanced(...)
else:
    # Fallback to Phase 1 aggregation
    signal = self.aggregate_signals(indicators, timestamp, atr_data)
```

From `services/notification-service/app/alert_manager.py:670-706` (existing send_daily_summary — to extend with the new kwarg):
```python
async def send_daily_summary(
    self,
    total_pnl: float,
    total_trades: int,
    win_rate: float,
    balance: float,
    **kwargs,
) -> AlertResponse:
    """Send daily performance summary"""
    emoji = "+" if total_pnl >= 0 else "-"
    message = f"""
Performance Summary:
- Total P&L: ${total_pnl:,.2f}
- Trades: {total_trades}
- Win Rate: {win_rate:.1%}
- Balance: ${balance:,.2f}
"""
    return await self.send_alert(
        AlertCreate(
            alert_type=AlertType.PERFORMANCE,
            severity=AlertSeverity.LOW,
            title=f"{emoji} Daily Summary: ${total_pnl:,.2f}",
            message=message,
            ...
```

From `services/notification-service/app/routers/alerts.py:435-463` (existing /daily-summary endpoint — extend with new optional kwarg):
```python
@router.post("/daily-summary", response_model=AlertResponse)
async def send_daily_summary(
    total_pnl: float,
    total_trades: int,
    win_rate: float,
    best_trade: float,
    worst_trade: float,
    balance: float,
    open_positions: int = 0
):
    """Send daily trading summary — convenience endpoint."""
    try:
        response = await alert_manager.send_daily_summary(...)
```

From `services/trading-engine/app/preflight/types.py` (Phase 8 enum precedent — Literal + tuple pattern to mirror):
```python
Status = Literal["PASS", "FAIL", "UNKNOWN"]
```

From `services/trading-engine/app/handlers/preflight.py:32-65` — the EXACT shape to mirror for the new unauthenticated read-only observability endpoint per D-09-03-07 (sibling handler file, sibling router prefix, unauthenticated read-only per Phase 8 D-09):
```python
router = APIRouter(prefix="/api/preflight", tags=["preflight"])

@router.get("/live-readiness")
async def get_live_readiness() -> dict:
    """Return the schema_version=1 :class:`PreflightReport` as a JSON dict."""
    try:
        report = run_all()
        return report.to_dict()
    except Exception as e:
        logger.error(f"Preflight live-readiness check failed: {e}", exc_info=True)
        raise HTTPException(...)
```

From `services/notification-service/app/telegram_notifier.py:96` and `services/notification-service/app/channels/telegram_client.py:135` (existing inter-service httpx pattern — REUSE for the scheduled fetcher per D-09-03-07):
```python
async with httpx.AsyncClient(timeout=10.0) as client:
    response = await client.get(url, ...)
```

From `tests/integration/test_preflight_grep_gates.py` (analog for the new grep gate file):
```python
REPO_ROOT = Path(__file__).resolve().parents[2]
TE_APP = REPO_ROOT / "services" / "trading-engine" / "app"
# dual-form scan; assert subprocess stdout non-empty
```

Cross-plan note on enum scope (Plan 09-02 vs Plan 09-03):
- Plan 09-03 OWNS `services/trading-engine/app/aggregation/ml_gate_reasons.py` with a FIVE-member tuple `ML_GATE_REASONS = ("no_evidence", "dsr_below_gate", "evidence_stale", "regime_shift", "manual_override")` — these are the reasons for **disabled** events (emissions when `use_ml=False`).
- Plan 09-02's `lifespan/ml.py` defines a SEPARATE local tuple `_MLGATE_REASONS` that ALSO includes `"dsr_above_gate"` (the auto-flip-enabled direction's reason) — six members total. This is intentional: the auto-flip event has direction `enabled` or `disabled` and uses a slightly broader vocabulary than the per-cycle disabled-event emissions.
- The two enums share 5 of 6 members but are scoped to different log literals (`MLGATE_AUTO_FLIP` vs `ML predictions disabled reason=`).
- **D-09-03-06 cross-plan wiring**: Plan 09-02 IMPORTS `set_current_reason` from this plan's `ml_gate_reasons.py` module (one-way arrow — 09-02 depends on 09-03). After auto-flip, Plan 09-02 calls `set_current_reason(reason)` to propagate the truthful reason into the in-process cache that this plan's `log_ml_disabled()` reads as its default reason argument. Plan 09-02's Wave is 2 to reflect this dep; Plan 09-03 is Wave 1.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create reason enum module + helper + in-process counter + cross-plan reason-state cache (+ unit tests)</name>
  <read_first>
    - services/trading-engine/app/preflight/types.py (Phase 8 enum precedent — `Literal` + tuple constants — copy this shape)
    - services/trading-engine/app/aggregation/__init__.py (the aggregation package — verify the new module slots in cleanly; if no __init__.py exists in aggregation/, check whether one is needed)
    - services/trading-engine/app/aggregation/enhanced_aggregator.py lines 1-50 (existing imports + logger pattern — mirror)
    - .planning/phases/09-ml-re-enablement-gate/09-02-startup-auto-flip-PLAN.md (Plan 09-02's `auto_flip_ml_predictions()` IMPORTS `set_current_reason` from this plan's module — D-09-03-06; ensure the function signature accepted by 09-02 matches what's defined here)
  </read_first>
  <behavior>
    - Module exposes:
      - `MLGateReason = Literal["no_evidence", "dsr_below_gate", "evidence_stale", "regime_shift", "manual_override"]` — five members exactly, no more.
      - `ML_GATE_REASONS = ("no_evidence", "dsr_below_gate", "evidence_stale", "regime_shift", "manual_override")` — same five, tuple form for runtime `in` checks.
      - `def log_ml_disabled(reason: MLGateReason | None = None, *, detail: str = "") -> None`: when `reason is None`, calls `get_current_reason()` to fetch the live truthful reason (D-09-03-06 default-fallback); validates `reason in ML_GATE_REASONS` (raises ValueError if not); emits `logger.info(f"ML predictions disabled reason={reason} detail={detail}")`; increments the in-process counter.
      - `def set_current_reason(reason: MLGateReason) -> None` (NEW — D-09-03-06): validates `reason in ML_GATE_REASONS`; assigns to module-level `_current_reason`. Called by Plan 09-02 after auto-flip outcome.
      - `def get_current_reason() -> MLGateReason` (NEW — D-09-03-06): returns the current cached reason; defaults to `"manual_override"` if `set_current_reason` has never been called.
      - `def record_ml_gate_event(reason: MLGateReason) -> None`: lower-level counter increment exposed for direct counter writes (used by Plan 09-02 indirectly via the `log_ml_disabled` calls in this plan's emission sites).
      - `def snapshot_reasons() -> dict[str, int]`: returns a copy of the counter; safe for concurrent reads. Consumed by the new endpoint handler (Task 2) and by integration tests.
      - `def reset_counter() -> None`: testing helper to clear state between tests; ALSO resets `_current_reason` to `"manual_override"` so tests start from a clean cross-plan-cache state.
    - The log literal `"ML predictions disabled reason="` is a contiguous substring inside the f-string (D-09-03-03 ordering).
    - Module is dependency-free beyond stdlib + `logging` — same constraint as Phase 8's `app.preflight` package (so it can be imported by both trading-engine lifespan and aggregator modules without circular-import risk).
    - **Threading note**: the module-level `_current_reason` is a plain `str` assignment; Python's GIL makes the single-attribute write atomic. No `threading.Lock` is required for the read-mostly access pattern (write once per auto-flip; read once per signal-aggregation cycle). If a future operator surfaces a race during a hot-reload sequence, the lock is a one-line follow-up; not needed for v1.1.
  </behavior>
  <action>
    Per D-09-03-02, D-09-03-03, D-09-03-04, and D-09-03-06:
    1. Create `services/trading-engine/app/aggregation/ml_gate_reasons.py` with:
       - Module docstring referencing MLGATE-03 + the 5-member enum + the log-literal contract + D-09-03-06 cross-plan reason-state contract.
       - Imports: stdlib only — `import logging`, `from collections import Counter`, `from typing import Literal`.
       - `MLGateReason` Literal alias as described.
       - `ML_GATE_REASONS` tuple constant — define the tuple EXPLICITLY (not derived from the Literal via `__args__` — the explicit tuple is clearer for grep gates and runtime use).
       - Module-level `_counter: Counter[str] = Counter()` (Counter is hashable-friendly, supports `+=` increment, and `.copy()` returns a snapshot).
       - **Module-level `_current_reason: str = "manual_override"`** (D-09-03-06 — default before any auto-flip fires; written by Plan 09-02 after auto-flip; read by `log_ml_disabled()` default-fallback).
       - `set_current_reason` function:
         ```python
         def set_current_reason(reason: MLGateReason) -> None:
             """Cache the live truthful reason for downstream emissions (D-09-03-06).

             Called by Plan 09-02's auto_flip_ml_predictions() after the auto-flip
             outcome is determined. The cached value is read by log_ml_disabled() as
             the default reason argument so per-cycle emissions reflect the auto-flip
             outcome rather than a hardcoded fallback.
             """
             if reason not in ML_GATE_REASONS:
                 raise ValueError(f"unknown ML gate reason: {reason!r}")
             global _current_reason
             _current_reason = reason
         ```
       - `get_current_reason` function:
         ```python
         def get_current_reason() -> MLGateReason:
             """Return the cached live reason; defaults to 'manual_override' before first auto-flip."""
             return _current_reason  # type: ignore[return-value]
         ```
       - `log_ml_disabled` function (D-09-03-06 default-fallback):
         ```python
         def log_ml_disabled(reason: MLGateReason | None = None, *, detail: str = "") -> None:
             """Emit structured ML-disabled log + increment counter (MLGATE-03).

             When `reason` is None, uses get_current_reason() — i.e. the truthful
             reason cached by Plan 09-02's auto-flip outcome (D-09-03-06). Callers
             with a more specific local cause (e.g. test-only manual disables) may
             pass an explicit reason to override.
             """
             if reason is None:
                 reason = get_current_reason()
             if reason not in ML_GATE_REASONS:
                 raise ValueError(f"unknown ML gate reason: {reason!r}")
             # Literal substring is "ML predictions disabled reason=" — load-bearing for grep gate.
             logger.info(f"ML predictions disabled reason={reason} detail={detail}")
             _counter[reason] += 1
         ```
       - `record_ml_gate_event`, `snapshot_reasons` per behavior spec.
       - `reset_counter` function:
         ```python
         def reset_counter() -> None:
             """Testing helper: clear counter AND reset _current_reason to default."""
             global _current_reason
             _counter.clear()
             _current_reason = "manual_override"
         ```
       - `__all__ = ["MLGateReason", "ML_GATE_REASONS", "log_ml_disabled", "record_ml_gate_event", "snapshot_reasons", "reset_counter", "set_current_reason", "get_current_reason"]`.
    2. Verify `services/trading-engine/app/aggregation/__init__.py` exists — if absent, create one with a header docstring matching the existing pattern in `app/preflight/__init__.py` (re-export shape). If present, append the new module's exports to its `__all__`.
    3. Create `services/trading-engine/tests/test_ml_gate_reasons.py` (≥10 cases — expanded from ≥6 to cover the new cross-plan cache + reachability proofs):
       - `test_enum_tuple_has_exactly_five_members`: assert `len(ML_GATE_REASONS) == 5`.
       - `test_enum_tuple_members_match_spec`: assert `set(ML_GATE_REASONS) == {"no_evidence", "dsr_below_gate", "evidence_stale", "regime_shift", "manual_override"}`.
       - `test_log_ml_disabled_emits_literal_with_reason` (caplog assertion): call `log_ml_disabled("no_evidence")`; assert `"ML predictions disabled reason=no_evidence"` appears in `caplog.text` as a contiguous substring.
       - `test_log_ml_disabled_rejects_unknown_reason`: `pytest.raises(ValueError) as ei: log_ml_disabled("bogus_reason")`; assert `"unknown ML gate reason"` in `str(ei.value)`.
       - `test_record_ml_gate_event_increments_counter`: `reset_counter(); record_ml_gate_event("dsr_below_gate"); record_ml_gate_event("dsr_below_gate")`; assert `snapshot_reasons()["dsr_below_gate"] == 2`.
       - `test_snapshot_returns_copy_not_reference`: snapshot, mutate it externally, take another snapshot, assert the internal state survived (counter is encapsulated).
       - **NEW** `test_get_current_reason_defaults_to_manual_override`: call `reset_counter()`; assert `get_current_reason() == "manual_override"` (D-09-03-06 default).
       - **NEW** `test_set_current_reason_propagates_to_get`: `reset_counter(); set_current_reason("dsr_below_gate")`; assert `get_current_reason() == "dsr_below_gate"`.
       - **NEW** `test_set_current_reason_rejects_unknown`: `pytest.raises(ValueError): set_current_reason("bogus")`.
       - **NEW** `test_log_ml_disabled_reads_current_reason_default` (cross-plan propagation proof — closes Blocker 1 enum-reachability): `reset_counter(); set_current_reason("evidence_stale"); log_ml_disabled()`; assert `caplog.text` contains `"ML predictions disabled reason=evidence_stale"` AND `snapshot_reasons()["evidence_stale"] == 1`.
       - **NEW PARAMETRIZED** `test_all_five_reasons_reachable_via_explicit_arg` (closes Blocker 1 enum-reachability — full coverage): `@pytest.mark.parametrize("reason", list(ML_GATE_REASONS))` — for each of the 5 reasons, `reset_counter(); log_ml_disabled(reason); assert snapshot_reasons()[reason] == 1; assert f"reason={reason}" in caplog.text`. This is the production-side proof that ROADMAP SC#3's example `(e.g., no_evidence: 3, dsr_below_gate: 1)` is reproducible.
       - **NEW PARAMETRIZED** `test_all_five_reasons_reachable_via_set_current_reason` (closes Blocker 1 — auto-flip-propagation form): `@pytest.mark.parametrize("reason", list(ML_GATE_REASONS))` — for each of the 5 reasons, `reset_counter(); set_current_reason(reason); log_ml_disabled()  # no explicit arg; assert snapshot_reasons()[reason] == 1`. This exercises the cross-plan default-fallback path end-to-end.
  </action>
  <verify>
    <automated>cd /mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine &amp;&amp; pytest tests/test_ml_gate_reasons.py -v 2&gt;&amp;1 | tail -25</automated>
  </verify>
  <acceptance_criteria>
    - File `services/trading-engine/app/aggregation/ml_gate_reasons.py` exists.
    - `grep -c "^ML_GATE_REASONS = " services/trading-engine/app/aggregation/ml_gate_reasons.py` returns 1.
    - `grep -c "MLGateReason = Literal" services/trading-engine/app/aggregation/ml_gate_reasons.py` returns 1.
    - `grep -c "no_evidence.*dsr_below_gate.*evidence_stale.*regime_shift.*manual_override" services/trading-engine/app/aggregation/ml_gate_reasons.py` returns ≥1 (all 5 members present in either the Literal or the tuple — both lines should match the multi-token regex).
    - The literal `"ML predictions disabled reason="` appears as a contiguous substring: `grep -c "ML predictions disabled reason=" services/trading-engine/app/aggregation/ml_gate_reasons.py` returns ≥1.
    - **`grep -c "def set_current_reason" services/trading-engine/app/aggregation/ml_gate_reasons.py` returns 1** (D-09-03-06).
    - **`grep -c "def get_current_reason" services/trading-engine/app/aggregation/ml_gate_reasons.py` returns 1**.
    - **`grep -c "_current_reason" services/trading-engine/app/aggregation/ml_gate_reasons.py` returns ≥4** (module-level var + set + get + reset_counter).
    - All ≥10 unit tests PASS (parametrized counts may inflate this further): `pytest services/trading-engine/tests/test_ml_gate_reasons.py -v 2&gt;&amp;1 | grep -c "PASSED"` returns ≥10.
    - Parametrized 5-reason-reachability proof passes: `pytest services/trading-engine/tests/test_ml_gate_reasons.py::test_all_five_reasons_reachable_via_explicit_arg -v 2&gt;&amp;1 | grep -c "PASSED"` returns 5; same for `test_all_five_reasons_reachable_via_set_current_reason` returns 5.
    - Module has NO non-stdlib imports: `grep -E "^(from|import)" services/trading-engine/app/aggregation/ml_gate_reasons.py | grep -vE "(logging|collections|typing|__future__)"` returns nothing.
  </acceptance_criteria>
  <done>
    Module with 5-member enum, log helper with default-fallback to `get_current_reason()`, in-process counter, cross-plan reason-state cache (D-09-03-06 — closes checker Blocker 1), ≥10 passing unit tests including parametrized 5-reason-reachability proofs for both the explicit-arg and the auto-flip-propagation paths. Stdlib-only — safe for any future v1.2 consolidation.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wire emissions at every `use_ml=False` branch (default-reason fallback) + unauthenticated read-only observability endpoint + CI grep gate</name>
  <read_first>
    - services/trading-engine/app/aggregation/enhanced_aggregator.py (entire file — locate every `use_ml` branch: init at line 59, parallel-fetch at line 123, score-log at line 160)
    - services/trading-engine/app/signal_aggregator.py lines 1118-1138 (the routing condition — emission needed on the `else` branch)
    - services/trading-engine/app/handlers/preflight.py (the analog endpoint handler — SAME router-registration pattern; sibling file convention)
    - services/trading-engine/app/main.py (existing handler-router include shape — extend to include the new handler)
    - tests/integration/test_preflight_grep_gates.py (exact shape to mirror for the new grep gate)
    - .planning/phases/08-pre-live-preflight/08-03-SUMMARY.md "Manual Verification Records" (failure-mode mutation discipline — same applies here)
  </read_first>
  <behavior>
    - **Emission site E1** (`enhanced_aggregator.py:__init__`): when `self.use_ml = False`, emit `log_ml_disabled(detail="enable_ml_predictions=false at aggregator init")` — **no explicit `reason` arg**; the helper defaults to `get_current_reason()` which returns the live auto-flip reason (D-09-03-06 — closes Blocker 1). If the aggregator is initialized BEFORE the auto-flip has fired (test-only path), `get_current_reason()` returns `"manual_override"` — same default as before, but now scope-correctly named.
    - **Emission site E2** (`enhanced_aggregator.py:aggregate_signals_enhanced` — the parallel-fetch False branch around line 126): keep the `task_names.append("ML_DISABLED")` line but ALSO call `log_ml_disabled(detail=f"symbol={symbol} interval={interval}")` exactly once per call when `not self.use_ml` — **no explicit `reason` arg**; defaults to `get_current_reason()`. Per-cycle visibility into the live truthful reason — operator sees `reason=evidence_stale` (or whatever the auto-flip wrote) on every cycle.
    - **Emission site E3** (`signal_aggregator.py:1125` fallback branch): on the `else` branch (the Phase-1 fallback when `not self.settings.enable_ml_predictions`), call `log_ml_disabled(detail="fallback_to_phase1")` — **no explicit `reason` arg**; defaults to `get_current_reason()`.
    - **NEW emission rule (updated from prior plan revision)**: log emission is ALWAYS via `log_ml_disabled` — never a direct `logger.info(f"ML predictions disabled ...")` open-coded. The default-reason fallback to `get_current_reason()` means callers do NOT hardcode `"manual_override"` anymore (this was the original checker Blocker 1 — dimension-7b scope reduction). Explicit `reason=` is only used in tests for parametrized reachability proofs or for the rare local cause where the caller has more specific information.
    - **NEW unauthenticated read-only observability endpoint** `GET /api/preflight/ml-gate-reason-counts` (D-09-03-07 — Path A cross-service wiring per checker Blocker 2): handler module `services/trading-engine/app/handlers/ml_gate_reasons.py`; returns `snapshot_reasons()` as a JSON dict; mirrors `handlers/preflight.py:38` shape (unauthenticated read-only per Phase 8 D-09 — reason counts are public-grade observability data).
    - **CI grep gate** (Task 2 deliverable): `test_mlgate_reason_field_present` — scans `services/trading-engine/app/` for the literal `"ML predictions disabled"`; for every match, asserts the SAME line also contains `"reason="`. Implementation: pathlib rglob + per-line scan + assertion.
    - **NOTE on prior-plan emission action**: the previous revision of this plan had the emission sites pass `"manual_override"` as an explicit positional argument. This task UPDATES that wiring to call `log_ml_disabled(detail=...)` without the explicit reason — the function's default-reason fallback to `get_current_reason()` is the canonical Phase 9 contract. This is the surgical fix for checker Blocker 1: every emission now reads the truthful reason at zero file-IO cost.
  </behavior>
  <action>
    Per D-09-03-03, D-09-03-06, D-09-03-07, and locked emission sites E1, E2, E3:
    1. **`enhanced_aggregator.py` edits**:
       - Add import at top (with other `app.*` imports): `from app.aggregation.ml_gate_reasons import log_ml_disabled`.
       - At line ~78 (after the existing `logger.info(f"EnhancedAggregator initialized ...")`): add a guarded emission:
         ```python
         if not self.use_ml:
             # D-09-03-06: no explicit reason arg — helper reads get_current_reason()
             # which returns the live auto-flip outcome (Plan 09-02 wrote it via
             # set_current_reason()). This is the surgical fix for checker Blocker 1.
             log_ml_disabled(detail="enable_ml_predictions=false at aggregator init")
         ```
       - At line ~128 (inside the `else:` of the `if self.use_ml:` block in `aggregate_signals_enhanced`), AFTER `task_names.append("ML_DISABLED")`: add `log_ml_disabled(detail=f"symbol={symbol} interval={interval}")` — no explicit reason arg.
    2. **`signal_aggregator.py` edits**:
       - Add the same import.
       - At line ~1133 (the `else:` branch of the Phase-3 routing check at line 1125), AFTER the existing `# Fallback to Phase 1 aggregation` comment: add `log_ml_disabled(detail="fallback_to_phase1")` — no explicit reason arg.
    3. **Create `services/trading-engine/app/handlers/ml_gate_reasons.py`** (per D-09-03-07 — closes checker Blocker 2 Path A wiring):
       ```python
       """Admin-guarded read-only endpoint exposing snapshot_reasons() as JSON.

       Closes ROADMAP Phase 9 SC#4 cross-service delivery clause (D-09-03-07):
       notification-service's daily-digest scheduler fetches this dict and forwards
       it to send_daily_summary().

       Sibling to handlers/preflight.py — same shape (no auth, read-only, public-grade
       observability data per Phase 8 D-09 unauthenticated read-only decision).
       """
       import logging
       from fastapi import APIRouter, HTTPException
       from app.aggregation.ml_gate_reasons import snapshot_reasons

       logger = logging.getLogger(__name__)
       router = APIRouter(prefix="/api/preflight", tags=["preflight"])

       @router.get("/ml-gate-reason-counts")
       async def get_ml_gate_reason_counts() -> dict[str, int]:
           """Return current ML-gate reason counter as a JSON dict."""
           try:
               return snapshot_reasons()
           except Exception as e:
               logger.error(f"ml-gate-reason-counts handler failed: {type(e).__name__}", exc_info=True)
               raise HTTPException(status_code=500, detail="ml-gate-reason-counts read failed")
       ```
       - Register the router in `services/trading-engine/app/main.py` — find the existing `app.include_router(preflight_router)` line (Phase 8) and add a sibling `app.include_router(ml_gate_reasons_router)` line + the corresponding F401-safe `from app.handlers.ml_gate_reasons import router as ml_gate_reasons_router` import.
    4. **Create `tests/integration/test_mlgate_reason_grep_gate.py`**:
       - Module docstring references MLGATE-03 success criterion #3.
       - Module-level constants from Phase 8 pattern: `REPO_ROOT`, `TE_APP`.
       - Test 1: `test_mlgate_reason_field_present` — for every `.py` under `TE_APP` (excluding `/tests/`), iterate lines; for each line containing `"ML predictions disabled"`, assert the same line also contains `"reason="`. Build the diagnostic message from variables (assemble at runtime) so the assertion message itself does NOT include the bare literal — same self-avoidance pattern Phase 8 used (08-01-SUMMARY.md issue #2).
       - Test 2: `test_mlgate_reason_helper_imported_at_emission_sites` — read `enhanced_aggregator.py` and `signal_aggregator.py` source; assert `"from app.aggregation.ml_gate_reasons import log_ml_disabled"` appears in BOTH files. Defends against the autoflake regression pattern.
    5. **Create `services/trading-engine/tests/test_ml_gate_reasons_endpoint.py`** (≥3 endpoint smoke tests per D-09-03-07):
       - `test_endpoint_returns_empty_dict_on_fresh_state`: FastAPI TestClient against the trading-engine app; `reset_counter()`; `GET /api/preflight/ml-gate-reason-counts`; expect 200 + `{}` (Counter().copy() returns empty dict).
       - `test_endpoint_returns_populated_dict_after_record_calls`: `reset_counter(); record_ml_gate_event("no_evidence"); record_ml_gate_event("no_evidence"); record_ml_gate_event("dsr_below_gate")`; GET; expect `{"no_evidence": 2, "dsr_below_gate": 1}`.
       - `test_endpoint_returns_500_on_internal_error`: monkeypatch `snapshot_reasons` to raise; GET; expect 500 with the public detail string (no info disclosure beyond `type(e).__name__` — same discipline as Phase 8 sqlite-error path).
    6. **Manual failure-mode verification** (record in SUMMARY.md — mirror 08-03-SUMMARY.md lines 104-116):
       - Mutate one of the `log_ml_disabled(...)` lines to a bare `logger.info("ML predictions disabled")` (no reason= field) via `sed`.
       - Run `pytest tests/integration/test_mlgate_reason_grep_gate.py::test_mlgate_reason_field_present -v` — assert it FAILS with a diagnostic that names the mutated file.
       - Restore via the backup; re-run; confirm PASSES.
       - Record counts and exit codes in SUMMARY.md.
    7. **Existing test compatibility**: trading-engine has aggregator tests in `services/trading-engine/tests/` — running them as part of this task's `<verify>` block confirms the new log calls do not break aggregator behavior. If a test asserts on the EXACT log line set, update it minimally to expect the new line.
  </action>
  <verify>
    <automated>cd /mnt/d/Bimo_max/crypto-trading-bot &amp;&amp; pytest tests/integration/test_mlgate_reason_grep_gate.py -v 2&gt;&amp;1 | tail -10 &amp;&amp; pytest services/trading-engine/tests/test_ml_gate_reasons.py services/trading-engine/tests/test_ml_gate_reasons_endpoint.py -v 2&gt;&amp;1 | tail -20</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "from app.aggregation.ml_gate_reasons import log_ml_disabled" services/trading-engine/app/aggregation/enhanced_aggregator.py` returns 1.
    - `grep -c "from app.aggregation.ml_gate_reasons import log_ml_disabled" services/trading-engine/app/signal_aggregator.py` returns 1.
    - `grep -c "log_ml_disabled(" services/trading-engine/app/aggregation/enhanced_aggregator.py` returns ≥2 (E1 + E2 sites).
    - `grep -c "log_ml_disabled(" services/trading-engine/app/signal_aggregator.py` returns ≥1 (E3 site).
    - **No hardcoded `"manual_override"` arg at emission sites (D-09-03-06 — closes Blocker 1)**: `grep -E 'log_ml_disabled\("manual_override"' services/trading-engine/app/aggregation/enhanced_aggregator.py services/trading-engine/app/signal_aggregator.py | wc -l` returns 0. Emission sites call `log_ml_disabled(detail=...)` without an explicit positional reason arg.
    - Every line in `services/trading-engine/app/` (excluding tests/) containing the substring `"ML predictions disabled"` also contains `"reason="`. Verified by: `grep -rn "ML predictions disabled" services/trading-engine/app/ --include="*.py" | grep -v "/tests/" | grep -vE "reason=" | wc -l` returns 0.
    - File `services/trading-engine/app/handlers/ml_gate_reasons.py` exists.
    - `grep -c "/api/preflight/ml-gate-reason-counts" services/trading-engine/app/handlers/ml_gate_reasons.py` returns ≥1 (router path).
    - `grep -c "snapshot_reasons()" services/trading-engine/app/handlers/ml_gate_reasons.py` returns ≥1.
    - Endpoint smoke tests PASS: `pytest services/trading-engine/tests/test_ml_gate_reasons_endpoint.py -v 2&gt;&amp;1 | grep -c "PASSED"` returns ≥3.
    - Router registered in `app/main.py`: `grep -c "ml_gate_reasons" services/trading-engine/app/main.py` returns ≥2 (router import + include_router call).
    - Both grep-gate tests PASS: `pytest tests/integration/test_mlgate_reason_grep_gate.py -v 2&gt;&amp;1 | grep -c "PASSED"` returns 2.
    - Phase 8 grep gates still pass: `pytest tests/integration/test_preflight_grep_gates.py -v 2&gt;&amp;1 | grep -c "PASSED"` returns 2.
    - SUMMARY.md contains a "Manual Verification Records" section per Phase 8 precedent (failure-mode mutation, before/after grep counts).
  </acceptance_criteria>
  <done>
    Reason enum imported at all three emission sites; every `"ML predictions disabled"` literal in `services/trading-engine/app/` carries a `reason=` field on the same line; emission sites delegate the reason to `get_current_reason()` (no hardcoded `"manual_override"` — closes checker Blocker 1); new unauthenticated read-only `/api/preflight/ml-gate-reason-counts` endpoint exists, returns `snapshot_reasons()`, has ≥3 passing smoke tests; new CI grep gate passes; failure-mode mutation verified; Phase 8 grep gates still pass.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Cross-service daily-digest wiring — notification-service scheduled fetcher + template render + integration test (closes checker Blocker 2)</name>
  <read_first>
    - services/notification-service/app/alert_manager.py lines 670-710 (existing `send_daily_summary` — exact signature to extend)
    - services/notification-service/app/routers/alerts.py lines 435-463 (existing `/daily-summary` endpoint — extend signature with the new optional kwarg)
    - services/notification-service/app/models.py (the `AlertCreate` shape — for the `metadata` field where the reason counts can also be embedded for downstream consumers)
    - services/notification-service/app/main.py (find the existing scheduler bootstrap / lifespan hook — apscheduler or asyncio.create_task pattern)
    - services/notification-service/app/telegram_notifier.py lines 90-110 (existing httpx.AsyncClient pattern — REUSE shape for the scheduled fetcher per D-09-03-07)
    - services/notification-service/app/channels/telegram_client.py lines 130-180 (TelegramClient.send_message — the dispatch target the integration test mocks)
    - services/notification-service/tests/ (existing test layout — confirm pytest fixture pattern for the notification service; per CLAUDE.md `feedback_api_gateway_test_env.md`-style: prefer `docker exec` if host fastapi version drifts, but the notification-service tests should run host-side for simple template + scheduler assertions)
    - services/trading-engine/app/handlers/ml_gate_reasons.py (Task 2's new endpoint — the URL the scheduler fetches)
    - .planning/phases/09-ml-re-enablement-gate/09-03-reason-enum-and-digest-PLAN.md D-09-03-07 (locked: HTTP-pull pattern, Path A; cross-service delivery clause DELIVERED THIS PHASE — no v1.2 deferral)
  </read_first>
  <behavior>
    - **`send_daily_summary` extension**:
      - Accepts a new optional kwarg `ml_gate_reason_counts: dict[str, int] | None = None`.
      - When `ml_gate_reason_counts` is None or empty: the digest message is rendered UNCHANGED from current behavior (Phase 8-compatible — backward-compatible signature extension).
      - When `ml_gate_reason_counts` is a non-empty dict: the rendered message body includes a new line group:
        ```
        ML Gate Reasons (24h):
        - no_evidence: 3
        - dsr_below_gate: 1
        ```
      - Reason ordering in the rendered message follows the canonical `ML_GATE_REASONS` tuple order (`no_evidence`, `dsr_below_gate`, `evidence_stale`, `regime_shift`, `manual_override`) — operator gets a stable layout regardless of dict insertion order.
      - The `AlertCreate.metadata` dict ALSO gains a `"ml_gate_reason_counts"` key when the kwarg is non-None, so downstream consumers (Phase 10 dashboard tile, structured-data scraping) can read counts directly.
      - The `/daily-summary` HTTP endpoint forwards the new kwarg as a top-level body parameter `ml_gate_reason_counts: dict[str, int] | None = None`.
    - **NEW scheduled fetcher** (D-09-03-07 — closes checker Blocker 2 delivery clause):
      - Module `services/notification-service/app/scheduler/ml_gate_digest.py` exposes `async def fetch_and_dispatch_digest(*, trading_engine_url: str | None = None, alert_manager=None, now=None) -> dict`:
        - Reads `TRADING_ENGINE_URL` env var (default `http://trading-engine:8005` — matches docker-compose service name in `docker-compose.unified.yml`).
        - `httpx.AsyncClient(timeout=5.0)` GET against `<base>/api/preflight/ml-gate-reason-counts`.
        - On 200: parses JSON dict; on non-200 or connection error: logs warning, sets `reason_counts = None`.
        - Builds a stub daily-summary payload (zeros for total_pnl/total_trades/win_rate/balance — the v1.1 scheduler ships a `summary header + ML gate block` message; in v1.2 the trading-engine balance/PnL endpoints can be fetched the same way to fill the rest).
        - Calls `alert_manager.send_daily_summary(total_pnl=0.0, total_trades=0, win_rate=0.0, balance=0.0, ml_gate_reason_counts=reason_counts)`.
        - Returns a dispatch summary dict: `{"reason_counts": reason_counts, "fetch_status": "ok" | "error", "dispatched": True | False}`.
      - Module ALSO exposes `async def start_scheduler(*, period_seconds: int = 86400) -> asyncio.Task` for bootstrap from notification-service `main.py` lifespan — `asyncio.create_task` loop that awaits `period_seconds` between calls. For v1.1, no apscheduler dependency is added; an asyncio loop is sufficient. (apscheduler is a v1.2 follow-up if the operator wants cron-string scheduling.)
    - **Bootstrap wiring**: in `services/notification-service/app/main.py` lifespan (the existing FastAPI lifespan / startup hook), if env var `ML_GATE_DIGEST_ENABLED=true`, call `await start_scheduler()` and store the returned task on `app.state`. Default for `ML_GATE_DIGEST_ENABLED` is `false` (operator opts in per CLAUDE.md feature-flag discipline — same shape as `ENABLE_SENTIMENT_ANALYSIS`).
  </behavior>
  <action>
    Per D-09-03-04 (UPDATED) and D-09-03-07:
    1. **`services/notification-service/app/alert_manager.py` edit** — modify `send_daily_summary`:
       - Add parameter: `ml_gate_reason_counts: dict[str, int] | None = None` AFTER `balance` and BEFORE `**kwargs`.
       - In the function body, build a `ml_section_lines` list:
         ```python
         ml_section = ""
         if ml_gate_reason_counts:
             # Canonical reason ordering from the trading-engine source of truth.
             reason_order = ("no_evidence", "dsr_below_gate", "evidence_stale", "regime_shift", "manual_override")
             present = [(r, ml_gate_reason_counts[r]) for r in reason_order if r in ml_gate_reason_counts]
             if present:
                 ml_section_lines = ["", "ML Gate Reasons (24h):"]
                 ml_section_lines.extend(f"- {reason}: {count}" for reason, count in present)
                 ml_section = "\n".join(ml_section_lines)
         ```
       - Insert `ml_section` at the end of the existing message body f-string (append, do not replace).
       - Add `"ml_gate_reason_counts": ml_gate_reason_counts` to the `metadata={...}` dict (only when not None; if None, omit the key).
       - **Constraint**: do NOT import from `services.trading-engine` — the notification-service must remain decoupled from trading-engine source. The reason_order tuple is duplicated here as a literal (same five strings); CI grep gate from Task 2 ensures the trading-engine side stays canonical. Acceptable per D-09-03-04 scope.
    2. **`services/notification-service/app/routers/alerts.py` edit** — modify the `/daily-summary` endpoint:
       - Add parameter `ml_gate_reason_counts: Optional[dict[str, int]] = None` (use `Optional` for FastAPI 0.109 compatibility per CLAUDE.md `feedback_api_gateway_test_env.md`).
       - Forward it to `alert_manager.send_daily_summary(..., ml_gate_reason_counts=ml_gate_reason_counts)`.
    3. **Create `services/notification-service/app/scheduler/__init__.py`** (empty package init) and `services/notification-service/app/scheduler/ml_gate_digest.py` per the behavior spec above. Constants:
       - `_DEFAULT_TRADING_ENGINE_URL = "http://trading-engine:8005"` (docker-compose service hostname).
       - `_FETCH_TIMEOUT_SECONDS = 5.0`.
       - `_ENDPOINT_PATH = "/api/preflight/ml-gate-reason-counts"`.
    4. **Bootstrap wiring in `services/notification-service/app/main.py`**: find the existing FastAPI lifespan hook (or `@app.on_event("startup")` if older shape); add a guarded `if os.environ.get("ML_GATE_DIGEST_ENABLED", "false").lower() == "true": app.state.ml_gate_digest_task = await start_scheduler()`. On shutdown, cancel the task (`app.state.ml_gate_digest_task.cancel()`). Use the existing pattern in main.py for parallel constructs.
    5. **Create `services/notification-service/tests/test_daily_digest_ml_gate.py`** (≥4 cases — template render):
       - `test_digest_message_unchanged_when_ml_counts_absent`: call `alert_manager.send_daily_summary(..., ml_gate_reason_counts=None)` via mocked `send_alert`; assert the captured `AlertCreate.message` does NOT contain the substring `"ML Gate Reasons"`.
       - `test_digest_message_includes_ml_counts_section`: pass `{"no_evidence": 3, "dsr_below_gate": 1}`; assert message contains `"ML Gate Reasons (24h):"` AND `"- no_evidence: 3"` AND `"- dsr_below_gate: 1"`.
       - `test_digest_message_reason_order_is_canonical`: pass dict with reverse insertion order `{"manual_override": 1, "no_evidence": 2}`; assert in the rendered message, the index of `"no_evidence:"` is LESS than the index of `"manual_override:"` (canonical ordering preserved).
       - `test_digest_metadata_carries_reason_counts`: pass `{"no_evidence": 5}`; assert `AlertCreate.metadata["ml_gate_reason_counts"] == {"no_evidence": 5}`.
       - Mock the actual Telegram dispatch via `monkeypatch.setattr` on the notification provider — do NOT make real HTTP calls. Pattern mirrors existing notification-service tests.
    6. **Create `services/notification-service/tests/test_ml_gate_digest_scheduler.py`** (≥3 integration cases — closes checker Blocker 2 SC#4 delivery clause):
       **Mocking discipline — respx-only (advisor note)**: these integration tests run inside the `services/notification-service/` package and MUST NOT cross-import from `services/trading-engine/app/` (the two service packages both name themselves `app`, which collides on PYTHONPATH without custom sys.path munging). The trading-engine endpoint is exercised end-to-end by Task 2's `test_ml_gate_reasons_endpoint.py`. Here, the contract surface is the mocked HTTP response — use `respx` (already a project dep per memory `feedback_local_test_setup.md`) to intercept the `httpx.AsyncClient.get()` call inside `fetch_and_dispatch_digest()` and return a synthetic response body. No TestClient cross-import, no PYTHONPATH munging.
       - `test_scheduler_fetches_counts_and_dispatches_telegram`: use `@respx.mock` to register `GET http://trading-engine:8005/api/preflight/ml-gate-reason-counts` → 200 with JSON body `{"no_evidence": 1, "dsr_below_gate": 1}`. Monkeypatch `TelegramClient.send_message` to capture the dispatched payload into a list. Call `await fetch_and_dispatch_digest(trading_engine_url="http://trading-engine:8005", alert_manager=<real or mocked>)`. Assert: (a) the returned dict has `fetch_status="ok"` and `reason_counts={"no_evidence": 1, "dsr_below_gate": 1}`; (b) the captured Telegram payload contains `"ML Gate Reasons (24h):"` AND `"- no_evidence: 1"` AND `"- dsr_below_gate: 1"`.
       - `test_scheduler_handles_trading_engine_unreachable`: `@respx.mock` registers the same URL with `side_effect=httpx.ConnectError("connection refused")`; monkeypatch `TelegramClient.send_message`; call `await fetch_and_dispatch_digest(...)`. Assert: (a) `fetch_status="error"`, `reason_counts=None`; (b) Telegram dispatch STILL happened (graceful degradation per D-09-03-07 step 4); (c) the captured Telegram payload does NOT contain `"ML Gate Reasons"`.
       - `test_scheduler_handles_non_200_response`: `@respx.mock` registers the URL → 500 response with empty body; same graceful-degradation assertions as above.
    7. **CLAUDE.md compatibility note** for the executor:
       - The notification-service is the `services/notification-service/` directory; its tests run under `services/notification-service/tests/`. Per CLAUDE.md "api-gateway test suite must run inside the container": if FastAPI version mismatch surfaces (host has 0.136, container has 0.109), tests should run via `docker exec crypto-bot-notification pytest tests/test_daily_digest_ml_gate.py tests/test_ml_gate_digest_scheduler.py -xvs` (if a `crypto-bot-notification` container is up) OR rely on the local pytest run for pure-Python template assertions (no FastAPI HTTPBearer involvement, so the version mismatch is unlikely to bite these tests). Default to host pytest first; document any divergence in SUMMARY.md.
       - Per memory `feedback_local_test_setup.md`: tests use `respx` for httpx mocking (already installed when running locally without docker).
  </action>
  <verify>
    <automated>cd /mnt/d/Bimo_max/crypto-trading-bot/services/notification-service &amp;&amp; pytest tests/test_daily_digest_ml_gate.py tests/test_ml_gate_digest_scheduler.py -v 2&gt;&amp;1 | tail -30</automated>
  </verify>
  <acceptance_criteria>
    - File `services/notification-service/tests/test_daily_digest_ml_gate.py` exists.
    - File `services/notification-service/tests/test_ml_gate_digest_scheduler.py` exists.
    - File `services/notification-service/app/scheduler/ml_gate_digest.py` exists.
    - `grep -c "ml_gate_reason_counts" services/notification-service/app/alert_manager.py` returns ≥3 (signature param, conditional check, metadata dict).
    - `grep -c "ML Gate Reasons" services/notification-service/app/alert_manager.py` returns ≥1 (the rendered section header).
    - `grep -c "ml_gate_reason_counts" services/notification-service/app/routers/alerts.py` returns ≥1 (router param wiring).
    - `grep -cE "no_evidence.*dsr_below_gate.*evidence_stale.*regime_shift.*manual_override" services/notification-service/app/alert_manager.py` returns ≥1 (canonical ordering tuple present).
    - `grep -c "/api/preflight/ml-gate-reason-counts" services/notification-service/app/scheduler/ml_gate_digest.py` returns ≥1 (the URL path under fetch).
    - `grep -c "httpx.AsyncClient" services/notification-service/app/scheduler/ml_gate_digest.py` returns ≥1 (existing-pattern reuse).
    - `grep -c "ML_GATE_DIGEST_ENABLED" services/notification-service/app/main.py` returns ≥1 (feature-flag bootstrap guard).
    - All ≥4 template-render unit tests PASS: `pytest services/notification-service/tests/test_daily_digest_ml_gate.py -v 2&gt;&amp;1 | grep -c "PASSED"` returns ≥4.
    - All ≥3 scheduler integration tests PASS: `pytest services/notification-service/tests/test_ml_gate_digest_scheduler.py -v 2&gt;&amp;1 | grep -c "PASSED"` returns ≥3.
    - Telegram dispatch capture verified by `monkeypatch`-mocked `TelegramClient.send_message`: `grep -c "send_message" services/notification-service/tests/test_ml_gate_digest_scheduler.py` returns ≥3 (one mock setup per scheduler test).
    - Existing notification-service tests have no regressions (smoke run on the broader test directory; allow Telegram-mock related skips): `pytest services/notification-service/tests/ -v --co 2&gt;&amp;1 | tail -5` collects without ERRORS.
    - Backward compatibility verified: omitting `ml_gate_reason_counts` produces a digest message identical to current behavior (asserted by `test_digest_message_unchanged_when_ml_counts_absent`).
  </acceptance_criteria>
  <done>
    `send_daily_summary` accepts `ml_gate_reason_counts` kwarg; renders a canonical-ordered ML Gate Reasons section; new scheduled fetcher in `notification-service/app/scheduler/ml_gate_digest.py` pulls counts via httpx from the trading-engine's `/api/preflight/ml-gate-reason-counts` endpoint and forwards them to `send_daily_summary`; bootstrap is feature-flagged via `ML_GATE_DIGEST_ENABLED`; ≥4 template render tests pass; ≥3 integration tests pass including the cross-service path (counts seeded on trading-engine → fetched via mocked httpx → Telegram dispatch captured with the rendered payload). SC#4 cross-service delivery clause is DELIVERED THIS PHASE — no v1.2 deferral remains (closes checker Blocker 2).
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| trading-engine signal-aggregation path → log subsystem | Structured-reason emissions are local logger calls; no network. |
| trading-engine signal-aggregation path → in-process counter | Module-level Counter; same-process state shared across async tasks. No multi-process coherence claim. |
| trading-engine in-process reason cache → signal-aggregation reads | Module-level `_current_reason: str`; written by Plan 09-02 (single writer), read by every emission site. Python GIL makes the single-attribute write atomic; no lock needed for read-mostly access. |
| trading-engine → notification-service (NEW HTTP cross-service path) | NEW endpoint `GET /api/preflight/ml-gate-reason-counts`; unauthenticated read-only per Phase 8 D-09 (reason counts are public-grade observability data, same disclosure level as DSR values exposed via `/api/preflight/live-readiness`). |
| notification-service `send_daily_summary` → Telegram | Existing trust boundary; no new auth surface. The new kwarg is operator-controlled. |
| CI grep gate → production code | Read-only static scan; no execution. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-09-03-01 | Tampering | Reason-enum drift (new emission site adds a string outside the enum) | mitigate | `log_ml_disabled` raises ValueError if `reason not in ML_GATE_REASONS`. Task 1's unit test `test_log_ml_disabled_rejects_unknown_reason` enforces. CI grep gate (Task 2) ALSO catches direct `logger.info("ML predictions disabled")` calls that bypass the helper. |
| T-09-03-02 | Information Disclosure | Log emissions leak symbol/interval to log subsystem | accept | Symbol + interval are public (price feed is mainnet, ticker visible on Bybit). No secrets, no PII. Same disclosure level as `services/api-gateway/app/main.py:1049` `/api/config/safety-state`. |
| T-09-03-03 | Denial of Service | Per-cycle emission floods log subsystem | accept | The signal-aggregation path runs at the auto-trader cadence (per `auto_trader.check_frequency` — typically ≥30s). Five validated symbols × one emission per cycle × 1/30s = ~10 lines/min, well below any rate-limit concern. |
| T-09-03-04 | Tampering | Notification-service kwarg duplicates the reason-order tuple from trading-engine, allowing drift | mitigate | Task 3 action step 1 explicitly notes the duplication is intentional (decoupling — notification-service must not import from trading-engine). CI grep gate `test_mlgate_reason_field_present` (Task 2) anchors the canonical enum at the trading-engine side. A follow-up wiki ADR documents the duplication; future drift would surface as a unit-test failure in `test_daily_digest_ml_gate.py::test_digest_message_reason_order_is_canonical`. |
| T-09-03-05 | Spoofing | Operator passes a forged `ml_gate_reason_counts` to the `/daily-summary` endpoint | mitigate | The endpoint is admin-guarded per existing notification-service auth (matches alert_manager precedent); a forged dict at most produces a misleading digest entry. The trading-engine in-process counter (Task 1) is the authoritative source, surfaced via the new unauthenticated read-only endpoint (Task 2) — the scheduled fetcher (Task 3) uses this canonical path, NOT the operator-facing `/daily-summary` kwarg. The kwarg surface is retained for testing/manual triggering. |
| T-09-03-06 | Repudiation | Operator removes `log_ml_disabled` call to hide a reason emission | mitigate | CI grep gate `test_mlgate_reason_field_present` (Task 2) scans for the literal `"ML predictions disabled"` — if an emission is removed, the literal disappears from production code; if it's open-coded (no `reason=`), the gate fails. Combined with Task 2's failure-mode mutation verification, silent removal is detectable. |
| T-09-03-07 | Information Disclosure | NEW endpoint `GET /api/preflight/ml-gate-reason-counts` leaks reason counts to unauthenticated readers | accept | Reason counts are public-grade observability data — they reveal that ML predictions are gated, but do NOT reveal credentials, DSR thresholds, position sizes, or any secret material. Same disclosure level as the existing Phase 8 `/api/preflight/live-readiness` endpoint (Phase 8 D-09 unauthenticated read-only decision). The endpoint returns a small dict (max 5 keys); request rate is bounded by the daily-digest period (1 fetch per 24h in production). |
| T-09-03-08 | Denial of Service | NEW scheduled fetcher in notification-service hangs on slow trading-engine | mitigate | `httpx.AsyncClient(timeout=5.0)` — same timeout shape as `services/notification-service/app/channels/telegram_client.py:135`. On timeout or any non-200 response, fetcher logs warning and dispatches the digest with `ml_gate_reason_counts=None` (graceful degradation per D-09-03-07 step 4). Verified by `test_scheduler_handles_trading_engine_unreachable` and `test_scheduler_handles_non_200_response`. |
| T-09-03-09 | Tampering | NEW endpoint mutated to return forged counts | mitigate | The endpoint returns `snapshot_reasons()` directly — a read-only view over the in-process counter. No write surface, no input validation surface. CI grep gate (Task 2) covers the underlying emission discipline; the endpoint just exposes what the production emissions already wrote. A future test asserting `pytest services/trading-engine/tests/test_ml_gate_reasons_endpoint.py::test_endpoint_returns_populated_dict_after_record_calls` would catch any handler-side tampering. |
</threat_model>

<verification>
1. **Reason enum is single-sourced**: only one `ML_GATE_REASONS = (` line in `services/trading-engine/app/`. Verified by `grep -rc "ML_GATE_REASONS = " services/trading-engine/app/ | grep ":1$" | wc -l` returns 1.
2. **Every disabled emission carries a reason**: `grep -rn "ML predictions disabled" services/trading-engine/app/ --include="*.py" | grep -v "/tests/" | grep -vE "reason=" | wc -l` returns 0.
3. **All 5 enum reasons are reachable in production** (closes Blocker 1): Task 1's parametrized tests pass for both `test_all_five_reasons_reachable_via_explicit_arg` (5 PASSED) and `test_all_five_reasons_reachable_via_set_current_reason` (5 PASSED).
4. **Cross-plan reason-state propagation works** (D-09-03-06 — closes Blocker 1): Task 1's `test_log_ml_disabled_reads_current_reason_default` PASSES; emission sites call `log_ml_disabled(detail=...)` WITHOUT explicit `reason=` (grep-verified: no hardcoded `log_ml_disabled("manual_override"` strings in emission files).
5. **Cross-service wiring delivers SC#4** (closes Blocker 2): Task 3's `test_scheduler_fetches_counts_and_dispatches_telegram` PASSES — seeded counter state on the trading-engine → fetched via mocked httpx → Telegram dispatch captured with the rendered `ML Gate Reasons (24h):` payload.
6. **Notification-service digest renders the new section** when given counts: `test_digest_message_includes_ml_counts_section` PASSES.
7. **Backward compatibility holds**: `test_digest_message_unchanged_when_ml_counts_absent` PASSES.
8. **CI grep gate covers all emission sites**: `pytest tests/integration/test_mlgate_reason_grep_gate.py -v` shows 2 PASSED.
9. **NEW unauthenticated read-only endpoint smoke tests pass**: `pytest services/trading-engine/tests/test_ml_gate_reasons_endpoint.py -v` shows ≥3 PASSED.
10. **Graceful degradation on trading-engine unreachable**: `test_scheduler_handles_trading_engine_unreachable` PASSES (Telegram still dispatched, ML section absent).
11. **Phase 8 and Plan 09-02 grep gates still pass**: `pytest tests/integration/test_preflight_grep_gates.py tests/integration/test_mlgate_grep_gates.py -v` shows ≥4 PASSED total (assuming 09-02 has landed; if not, just the 2 Phase 8 gates).
</verification>

<success_criteria>
- All 3 tasks' acceptance criteria pass.
- ROADMAP Phase 9 success criterion #3 holds: every `"ML predictions disabled"` emission in trading-engine carries a `reason=<enum>` field, AND all 5 enum members are demonstrably reachable in production via the cross-plan reason-state cache (closes checker Blocker 1 — no hardcoded `manual_override` survives at emission sites; `get_current_reason()` is the default).
- **ROADMAP Phase 9 success criterion #4 holds — DELIVERED THIS PHASE (closes checker Blocker 2)**: the Telegram daily digest aggregates ML-disabled reason counts (e.g., `no_evidence: 3, dsr_below_gate: 1`) AND delivers to the configured Telegram chat. The aggregation+delivery clause is exercised by `test_scheduler_fetches_counts_and_dispatches_telegram` end-to-end (counter seeded → HTTP fetch → Telegram dispatch with rendered payload). The digest format is confirmed by `test_digest_message_includes_ml_counts_section`. NO v1.2 deferral remains.
- The 5-member disabled-event enum is defined exactly once (`services/trading-engine/app/aggregation/ml_gate_reasons.py`) within trading-engine's signal-aggregation path. Plan 09-02 keeps a separate 6-member auto-flip tuple by design (sharing 5 members; see interfaces block). The notification-service duplication of the reason-order tuple is the only other intentional duplication, documented in D-09-03-04 + threat T-09-03-04.
- Cross-plan reason-state contract (D-09-03-06): `set_current_reason()` is exported from this plan's module and called once per auto-flip by Plan 09-02 (the only writer); `get_current_reason()` is the default-reason fallback for `log_ml_disabled()`.
- Cross-service wiring contract (D-09-03-07): `GET /api/preflight/ml-gate-reason-counts` is an unauthenticated read-only endpoint on the trading-engine (same disclosure level as Phase 8's `/api/preflight/live-readiness`); the notification-service scheduled fetcher pulls from this endpoint and forwards to `send_daily_summary`; graceful degradation on fetch failure is verified by integration test.
</success_criteria>

<output>
After completion, create `.planning/phases/09-ml-re-enablement-gate/09-03-SUMMARY.md` with:
- `requires`: [] (Wave 1; this plan EXPORTS to Plan 09-02 via the `set_current_reason` cross-plan import — 09-02 → 09-03 dep direction, no reverse dep)
- `provides`:
  - `app.aggregation.ml_gate_reasons` module (single source of truth for the 5-member enum + log helper + in-process counter + `set_current_reason`/`get_current_reason` cross-plan cache — D-09-03-06 closes checker Blocker 1)
  - Structured-reason emissions at all 3 trading-engine ML-disabled branch points; emissions delegate `reason` to `get_current_reason()` (no hardcoded `"manual_override"` survives at emission sites)
  - NEW unauthenticated read-only observability endpoint `GET /api/preflight/ml-gate-reason-counts` returning `snapshot_reasons()` as JSON dict — D-09-03-07 Path A cross-service wiring
  - NEW notification-service scheduled fetcher (`scheduler/ml_gate_digest.py`) that pulls counts via httpx and forwards to `send_daily_summary` — closes checker Blocker 2 SC#4 delivery clause
  - `send_daily_summary(ml_gate_reason_counts=...)` extension + canonical-ordered template render
  - CI grep gate `test_mlgate_reason_field_present`
- `affects`:
  - phase 09-02 (auto-flip imports `set_current_reason` from THIS plan's module — D-09-03-06; without that import, every per-cycle emission would default to `manual_override` regardless of auto-flip outcome — the original checker Blocker 1)
  - phase 10 DASHLIVE (dashboard tile can read `AlertCreate.metadata.ml_gate_reason_counts` for visual rendering AND can poll the new `/api/preflight/ml-gate-reason-counts` endpoint directly)
  - phase 11 LIVECLOSE (operator-visible reason counts in the daily digest contribute to the pre-LIVE-flip evidence audit)
- Decisions made (D-09-03-01 through D-09-03-07) — especially the technical-analysis wording-bug locus correction (D-09-03-01), the cross-plan reason-state contract (D-09-03-06), and the cross-service wiring contract (D-09-03-07)
- Manual failure-mode verification record (Task 2 mutation → FAIL → restore → PASS)
- Three commit hashes (one per task)
- Follow-ups:
  - (a) Wire trading-engine balance / PnL / win-rate endpoints into the digest scheduler so the daily summary is fully populated (currently the v1.1 scheduler ships ML-gate counts only; total_pnl/total_trades/win_rate/balance are zero placeholders).
  - (b) wiki ADR documenting the reason-order tuple duplication between trading-engine and notification-service.
  - (c) REQUIREMENTS.md MLGATE-03 wording cleanup (locus is trading-engine, not technical-analysis).
  - (d) Optional v1.2 apscheduler dep for cron-string scheduling (the v1.1 implementation uses a plain asyncio loop — sufficient for the 24h cadence).
</output>
