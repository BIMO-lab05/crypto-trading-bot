---
phase: 09-ml-re-enablement-gate
reviewed: 2026-05-17T03:25:00Z
depth: standard
files_reviewed: 25
files_reviewed_list:
  - scripts/forward_paper_test/run_evidence_loop.py
  - scripts/forward_paper_test/tests/test_run_evidence_loop.py
  - services/notification-service/app/alert_manager.py
  - services/notification-service/app/main.py
  - services/notification-service/app/routers/alerts.py
  - services/notification-service/app/scheduler/__init__.py
  - services/notification-service/app/scheduler/ml_gate_digest.py
  - services/notification-service/tests/test_daily_digest_ml_gate.py
  - services/notification-service/tests/test_ml_gate_digest_scheduler.py
  - services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql
  - services/trading-engine/app/aggregation/__init__.py
  - services/trading-engine/app/aggregation/enhanced_aggregator.py
  - services/trading-engine/app/aggregation/ml_gate_reasons.py
  - services/trading-engine/app/handlers/ml_gate_reasons.py
  - services/trading-engine/app/lifespan/__init__.py
  - services/trading-engine/app/lifespan/ml.py
  - services/trading-engine/app/main.py
  - services/trading-engine/app/preflight/checks.py
  - services/trading-engine/app/signal_aggregator.py
  - services/trading-engine/tests/test_ml_gate_auto_flip.py
  - services/trading-engine/tests/test_ml_gate_reasons.py
  - services/trading-engine/tests/test_ml_gate_reasons_endpoint.py
  - services/trading-engine/tests/test_preflight_checks.py
  - tests/integration/test_mlgate_grep_gates.py
  - tests/integration/test_mlgate_reason_grep_gate.py
findings:
  critical: 0
  warning: 6
  info: 4
  total: 10
status: issues_found
---

# Phase 9: Code Review Report

**Reviewed:** 2026-05-17T03:25:00Z
**Depth:** standard
**Files Reviewed:** 25
**Status:** issues_found

## Summary

Phase 9 (ML Re-enablement Gate) ships three plans of interlocking work: an idempotent
PSR-CI evidence-loop driver (09-01), a trading-engine boot-time auto-flip of
`ENABLE_ML_PREDICTIONS` driven by the leaderboard table (09-02), and a 5-member
structured ML-gate reason enum + cross-service Telegram digest (09-03). The
implementation is **defensible overall** — SQL uses parameter binding throughout,
the new unauthenticated endpoint is structurally identical to the Phase 8 D-09
precedent, error paths are scoped to `type(e).__name__` to prevent path leakage,
and the log-before-mutate ordering for the auto-flip emission is honoured.

No **Critical** issues found. Six **Warning** findings concern (1) unreachable
emission sites in `enhanced_aggregator.py` that nonetheless count toward the
plan's "three emission sites" claim, (2) lost-data in the marker JSON for the
`evidence_stale` branch, (3) silent swallow of non-CancelledError exceptions in
the notification-service shutdown path that violates CLAUDE.md "no silent
failures", (4) a missing schema/version contract on the unauthenticated endpoint,
(5) an immediate-on-start scheduler tick that can spam digests, and (6) a
`detail` regex that does not survive a future format change in `checks.py`. Four
**Info** items flag operator-visibility nits.

## Warnings

### WR-01: ML-gate emission sites E1 and E2 in EnhancedAggregator are unreachable

**File:** `services/trading-engine/app/aggregation/enhanced_aggregator.py:87-88, 143`
**Issue:**
`EnhancedAggregator(...)` is only ever constructed inside
`signal_aggregator.aggregate_signals_enhanced` (line 893), which is itself only
called from `signal_aggregator.get_trading_signal_enhanced` at line 1127:

```python
if use_phase3 and self.settings.enable_ml_predictions:
    signal = await self.aggregate_signals_enhanced(...)
else:
    log_ml_disabled(detail="fallback_to_phase1")  # E3 — the only reachable site
    signal = self.aggregate_signals(...)
```

This means when `EnhancedAggregator.__init__` runs, `self.use_ml = settings.enable_ml_predictions`
is **always True**. The `if not self.use_ml:` blocks at lines 87-88 (init) and
143 (per-cycle parallel-fetch branch) are unreachable in the production routing
path.

Plan 09-03 explicitly claims three structured-reason emission sites (E1/E2/E3),
and the CI grep gate at `tests/integration/test_mlgate_reason_grep_gate.py:142`
enforces that `log_ml_disabled` is imported in `enhanced_aggregator.py` — both
to defend dead code. Either the reachability claim is wrong, or the
`enable_ml_predictions=False` short-circuit should be lifted out of
`get_trading_signal_enhanced` so the enhanced-path branches actually fire.

**Fix:** Choose one:

Option A (recommended) — remove the dead emission sites in `enhanced_aggregator.py`
and update the plan/grep-gate scope. The aggregator's init-time log is informational
only; `get_trading_signal_enhanced`'s fallback already produces the structured
emission.

Option B — drop the gating in `get_trading_signal_enhanced` so the enhanced-aggregator
is constructed unconditionally and its own `if not self.use_ml:` branches
actually fire. Higher risk; would change the per-cycle code path.

Whichever path is chosen, the grep-gate enforcement must match where the
emission actually fires.

---

### WR-02: Marker JSON drops `dsr_value` for the `evidence_stale` branch

**File:** `services/trading-engine/app/lifespan/ml.py:74-89` (regex) + `services/trading-engine/app/preflight/checks.py:343-351` (detail-string author)
**Issue:**
The marker-JSON `dsr_value` field is extracted from the `CheckResult.detail`
string via `_DSR_VALUE_RE = re.compile(r"dsr=([0-9]+(?:\.[0-9]+)?)")`. For the
`evidence_stale` branch in `check_dsr_evidence`, the detail string is:

```
"evidence stale: run_date=2026-04-27T00:00:00+00:00 age_days=20 > 14"
```

There is no `dsr=` token, so `_extract_dsr_from_detail` returns `None` even
though the underlying DSR is **known to be above 0.95** (the branch ordering at
`checks.py:333-341` already gated on it). The marker JSON schema accepts `float | null`,
so the contract is not strictly violated, but a downstream consumer (Phase 10
dashboard tile) cannot tell whether `dsr_value=null` means "row missing" or "row
present but evidence stale". The information disappears at the lossy regex
boundary.

**Fix:** Either extend the `evidence_stale` detail string to carry the dsr
value, or have `check_dsr_evidence` return a structured side-channel (e.g.
`CheckResult.context: dict | None`) so the marker writer does not have to
re-parse English prose:

```python
# In checks.py at the stale branch:
return CheckResult(
    check="dsr_evidence",
    status="FAIL",
    detail=(
        f"evidence stale: dsr={dsr_value} run_date={run_date_raw} "
        f"age_days={age.days} > {_DSR_EVIDENCE_STALENESS_DAYS}"
    ),
)
```

This both lets the regex round-trip the dsr value AND surfaces it to operators
reading the CLI report.

---

### WR-03: Silent swallow of shutdown exceptions in notification-service lifespan

**File:** `services/notification-service/app/main.py:218-223`
**Issue:**
```python
if app.state.ml_gate_digest_task is not None:
    app.state.ml_gate_digest_task.cancel()
    try:
        await app.state.ml_gate_digest_task
    except (asyncio.CancelledError, Exception):
        pass
    logger.info("ML-gate digest scheduler stopped")
```

Catching bare `Exception` and `pass`-ing it violates CLAUDE.md's "no silent
failures" rule. `CancelledError` is the *expected* outcome after `.cancel()`,
but any other exception (e.g. a producer goroutine that raised on shutdown,
a transient logger failure) is silently lost, while the next line cheerfully
claims the scheduler "stopped". The "Scheduler stopped" log line then misleads
the operator into thinking shutdown was clean.

**Fix:**

```python
if app.state.ml_gate_digest_task is not None:
    app.state.ml_gate_digest_task.cancel()
    try:
        await app.state.ml_gate_digest_task
    except asyncio.CancelledError:
        pass  # expected — task was cancelled
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "ml-gate digest scheduler shutdown raised: %s",
            type(e).__name__,
            exc_info=True,
        )
    logger.info("ML-gate digest scheduler stopped")
```

---

### WR-04: ml-gate-reason-counts endpoint has no schema/version envelope

**File:** `services/trading-engine/app/handlers/ml_gate_reasons.py:28-47` + `services/notification-service/app/scheduler/ml_gate_digest.py:81-92`
**Issue:**
The endpoint returns the raw counter dict (`return snapshot_reasons()`), i.e.
`{"no_evidence": 3, "dsr_below_gate": 1}` with no `schema_version`, no
canonical-key list, and no `generated_at` timestamp. The cross-service consumer
(`_fetch_reason_counts`) only checks that the body parses to a dict, but never
verifies the keys belong to `ML_GATE_REASONS`. A future producer drift —
adding a sixth reason, renaming one, accidentally surfacing internal Counter
state — would not be caught by the consumer; instead, the digest would silently
ship an unknown key.

This is the contract drift the project's "schema_version=1" marker JSON pattern
(see `lifespan/ml.py:188`) was explicitly designed to prevent — the auto-flip
marker carries `schema_version`, but this cross-service contract does not.

**Fix:** Wrap the endpoint in a versioned envelope and verify it on the
consumer side:

```python
# handlers/ml_gate_reasons.py
return {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "counts": snapshot_reasons(),
}
```

```python
# scheduler/ml_gate_digest.py — _fetch_reason_counts
if body.get("schema_version") != 1:
    logger.warning("unsupported ml-gate-reason-counts schema_version=%s",
                   body.get("schema_version"))
    return None
counts = body.get("counts", {})
unknown = set(counts) - set(ML_GATE_REASONS)  # imported from a shared constant
if unknown:
    logger.warning("ml-gate-reason-counts has unknown keys: %s", unknown)
```

The `ML_GATE_REASONS` tuple is currently duplicated locally inside `alert_manager.send_daily_summary`
(per D-09-03-04) — at minimum, hoist it to a module-level constant alongside the
duplication so the consumer can validate keys without re-importing the trading-engine
package.

---

### WR-05: ML-gate digest scheduler fires immediately on startup with no leading sleep

**File:** `services/notification-service/app/scheduler/ml_gate_digest.py:154-170`
**Issue:**
```python
while True:
    try:
        summary = await fetch_and_dispatch_digest()
        ...
    await asyncio.sleep(period_seconds)
```

The first `fetch_and_dispatch_digest()` call runs the instant the scheduler
starts, then sleeps 24h. Combined with container restart loops (deploys,
OOM kills, host reboots), an operator who restarts the notification service
several times in a day will see redundant Telegram digests within seconds of
each restart. The CLAUDE.md "Notifications: real proof" discipline assumes
deliveries are intentional events; the current design lets a deploy spam users.

**Fix:** Either compute the time-to-next-daily-boundary and sleep until that
first, or honour a `ML_GATE_DIGEST_FIRST_TICK_DELAY_SECONDS` env override that
defaults to a sensible window (e.g., 1 hour). The simplest variant:

```python
async def _scheduler_loop(period_seconds: int, *, initial_delay_seconds: int = 3600) -> None:
    logger.info("ml-gate-digest scheduler started (delay=%ss, period=%ss)",
                initial_delay_seconds, period_seconds)
    try:
        await asyncio.sleep(initial_delay_seconds)
        while True:
            ...
            await asyncio.sleep(period_seconds)
    except asyncio.CancelledError:
        logger.info("ml-gate-digest scheduler cancelled")
        raise
```

A dedup check on the AlertManager side (suppress duplicate "Daily Summary"
alerts within 6h) would also catch this.

---

### WR-06: Auto-flip marker writer parses `CheckResult.detail` with brittle regex

**File:** `services/trading-engine/app/lifespan/ml.py:70-71`
**Issue:**
```python
_DSR_VALUE_RE = re.compile(r"dsr=([0-9]+(?:\.[0-9]+)?)")
_RUN_DATE_RE = re.compile(r"run_date=([0-9T:+\-Z\.]+)")
```

The marker-JSON writer reads the `detail` field of `CheckResult` — an English
prose string authored by `check_dsr_evidence` — through these regexes. The
docstring at line 67-69 admits the format is owned by another module: *"The
detail-string format is owned by `check_dsr_evidence` in `app/preflight/checks.py`;
if that format changes, update both regexes."* This is exactly the kind of
cross-module string-format coupling that drifts silently. There is no test that
checks `_DSR_VALUE_RE` and `_RUN_DATE_RE` keep parsing the actual outputs of
`check_dsr_evidence` — the unit tests at `test_ml_gate_auto_flip.py` only
assert `payload["dsr_value"] == 0.97`, which would pass equally well if the
regex extracted "9.7" instead of "0.97" (no negative test for the failure
modes).

This is the same root cause as WR-02. Combined with the fragile-detail-string
issue there, the safer fix is to **stop using the detail string as an
inter-module data channel**: extend `CheckResult` with an optional structured
`context: dict | None` field that `check_dsr_evidence` populates, and have
`auto_flip_ml_predictions` read from `result.context` instead of regexing
`result.detail`.

**Fix:** Add structured context to `CheckResult` (see WR-02 for the
prose-extraction problem on the stale branch); replace the regex extraction
in `lifespan/ml.py:189-193` with direct dict lookup. Bonus: add a regression
test that explicitly checks `_DSR_VALUE_RE.search(check_dsr_evidence(...).detail).group(1) == "0.97"`
for every branch of `check_dsr_evidence` so a future detail-string refactor
fails fast.

---

## Info

### IN-01: `published` counter in dry-run mode counts non-events

**File:** `scripts/forward_paper_test/run_evidence_loop.py:293-301`
**Issue:**
In dry-run mode, `counters["published"]` is incremented even though no UPDATE
happens — the counter name implies "rows actually flipped to
`psr_ci_published=1`" but in dry-run it means "rows that *would* have been
published". Test 7 (`test_evidence_loop_dry_run_does_not_mutate`) explicitly
asserts this is the intended contract, so this is a naming nit, not a behaviour
bug.

**Fix:** Rename to `would_publish` / `published` based on `dry_run`, or add a
`mode` field to the returned summary dict so callers can disambiguate:

```python
counters = {"published": 0, "skipped": 0, "errors": 0, "dry_run": dry_run}
```

---

### IN-02: `_resolve_returns` returns first match on duplicate run_id across flag subdirs

**File:** `scripts/forward_paper_test/run_evidence_loop.py:140-145`
**Issue:**
```python
for flag_dir in _EVIDENCE_BASE.iterdir():
    ...
    candidate = flag_dir / run_id
    if (candidate / "run.json").is_file():
        return load_run_returns(candidate)
```

If the same `run_id` appears under two `<flag>` subdirectories (e.g. an A/B
test seeded by the wrong driver, or a copy-paste mistake during evidence
backfill), the first match returned by `Path.iterdir()` wins — iteration order
is platform-dependent. Probability is low, but the failure mode is silent: the
"wrong" returns array gets fed to the PSR-CI computation, the marker flips, and
nothing surfaces the ambiguity.

**Fix:** Collect all matches, error if more than one, log all paths on
ambiguity:

```python
matches = [
    flag_dir / run_id
    for flag_dir in _EVIDENCE_BASE.iterdir()
    if flag_dir.is_dir() and (flag_dir / run_id / "run.json").is_file()
]
if len(matches) > 1:
    logger.error(
        "MLGATE_EVIDENCE_LOOP action=error reason=ambiguous_returns "
        "run_id=%s matches=%s",
        run_id, [str(m) for m in matches],
    )
    return None
return load_run_returns(matches[0]) if matches else None
```

---

### IN-03: Cross-service unauthenticated endpoint relies on network-level trust only

**File:** `services/trading-engine/app/handlers/ml_gate_reasons.py:28-47`
**Issue:**
The endpoint is unauthenticated by design (per `08-CONTEXT.md` D-09 carry-forward).
The justification in the docstring is sound — counts are observability data,
no secrets — but the endpoint is reachable by anything that can talk to the
trading-engine on port 8005. In the current docker-compose deployment the
docker network is the only gate. If the trading-engine port is ever exposed
externally (deploy mistake, debug expose, NodePort in k8s), this endpoint
surfaces the operational pattern of ML gating decisions (counts of
`no_evidence` vs `dsr_below_gate`) which is signal an attacker can use to time
attempts. Low severity but worth a deploy-time guard.

**Fix:** Document the trust boundary explicitly in the route docstring (and
ideally bind the route to a private blueprint that the gateway does NOT
proxy). At minimum, the docstring should name the deployment-level invariant:

```
SECURITY NOTE: this endpoint is reachable on the docker-internal network ONLY.
It MUST NOT be exposed via the api-gateway or any external ingress.
api-gateway routing config: confirm /api/preflight/* is not in the proxy table.
```

---

### IN-04: Hardcoded service host `http://trading-engine:8005` is fine for compose, surprising elsewhere

**File:** `services/notification-service/app/scheduler/ml_gate_digest.py:37`
**Issue:**
```python
_DEFAULT_TRADING_ENGINE_URL = "http://trading-engine:8005"
```

The default is the docker-compose service hostname, which is fine when running
under `docker-compose.unified.yml`. Outside that environment (host-mode pytest,
k8s, dev laptop), the scheduler would silently fail (`httpx.ConnectError`),
which the graceful-degradation path correctly handles — but the operator would
never know the *cause* (no DNS resolution) from the warning log. The log line
already includes the URL, so this is more of an operability nit than a bug.

**Fix:** When the connection error fires, suggest the env override in the log:

```python
except (httpx.TimeoutException, httpx.RequestError) as e:
    logger.warning(
        "ml-gate-reason-counts fetch failed: %s (url=%s) "
        "[set TRADING_ENGINE_URL to override]",
        type(e).__name__, url,
    )
```

---

_Reviewed: 2026-05-17T03:25:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
