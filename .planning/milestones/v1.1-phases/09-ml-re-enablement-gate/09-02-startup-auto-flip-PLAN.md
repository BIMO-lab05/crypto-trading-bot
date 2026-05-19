---
id: 09-02-startup-auto-flip
phase: 09-ml-re-enablement-gate
plan: 02
wave: 2
type: execute
mode: standard
depends_on:
  - 09-03-reason-enum-and-digest  # imports `set_current_reason` from `app.aggregation.ml_gate_reasons` (added in Plan 09-03 Task 1); runtime deploy dep on Plan 09-01 migration 0002 is asserted in deploy notes only (graceful degradation if missing — see operator deploy-order note in `<output>`)
autonomous: true
requirements:
  - MLGATE-02
files_modified:
  - services/trading-engine/app/lifespan/ml.py
  - services/trading-engine/app/lifespan/__init__.py
  - services/trading-engine/app/preflight/checks.py
  - services/trading-engine/app/main.py
  - services/trading-engine/tests/test_ml_gate_auto_flip.py
  - services/trading-engine/tests/test_preflight_checks.py  # in-place updates to 4 named Phase 8 DSR-evidence tests — fixtures must seed psr_ci_published=1 + fresh run_date (per Task 1 action step 8)
  - tests/integration/test_mlgate_grep_gates.py
tags:
  - mlgate
  - lifespan
  - auto-flip
  - boot-enforcement
  - grep-gates
  - phase-9
decisions:
  - D-09-02-01 — **Path A locked**: extend Phase 8's `check_dsr_evidence()` in `services/trading-engine/app/preflight/checks.py` to apply the 14-day staleness rule using the new `run_date` column (added by Plan 09-01 migration 0002). This is the single source of truth for "is DSR evidence good?"; the lifespan auto-flip phase READS from `check_dsr_evidence()` and translates the verdict into an enum reason. Rejected: Path B (duplicate the DSR query inside `lifespan/ml.py`), because it would split the read surface and cause silent drift the next time the DSR floor changes.
  - D-09-02-02 — **Marker JSON schema** (`/run/mlgate_auto_flip.json`) is pinned at:
    ```json
    {
      "schema_version": 1,
      "direction": "enabled" | "disabled",
      "reason": "dsr_above_gate" | "no_evidence" | "evidence_stale" | "dsr_below_gate" | "regime_shift" | "manual_override",
      "evaluated_at": "ISO-8601 UTC",
      "dsr_value": <float or null>,
      "run_date": "ISO-8601 UTC or null"
    }
    ```
    The marker is the cross-phase interface for Phase 10's PathToLiveTile (DASHLIVE-01); freezing schema_version=1 here so Phase 10 can render without re-discovering it. Phase 8's `check_dsr_evidence` already references this marker path at `services/trading-engine/app/preflight/checks.py:45` (`_MLGATE_MARKER_PATH = "/run/mlgate_auto_flip.json"`).
  - D-09-02-03 — **Lifespan insertion point**: the auto-flip block lives at the very start of `init_ml()` in `services/trading-engine/app/lifespan/ml.py` BEFORE the aggregator-health probe. Rationale: `signal_aggregator.py:1125` and `aggregation/enhanced_aggregator.py:59` read `settings.enable_ml_predictions` at INIT TIME of the aggregator; the auto-flip must mutate `os.environ["ENABLE_ML_PREDICTIONS"]` AND reload settings BEFORE the aggregator is constructed. Phase 8 analog at `services/trading-engine/app/main.py:271` (LIVE-strict cap-check) is the structural template — but lives in main.py because the LIVE_TRADING_ACK pair is also there. The ML auto-flip belongs in `lifespan/ml.py` because that's where ML-phase initialization is gated.
  - D-09-02-04 — **Log emission ordering** is load-bearing per `08-CONTEXT.md` "Per-trade cap enforcement point": the `MLGATE_AUTO_FLIP` log line is emitted by `logger.critical(...)` BEFORE `os.environ["ENABLE_ML_PREDICTIONS"]` is mutated. The grep gate (Task 3) anchors on the log literal at a stable line; mutating env first would create a window where the gate could pass against a no-op code path.
  - D-09-02-05 — **Wording-bug carry-in (no Phase 9 work)**: REQUIREMENTS.md and ROADMAP Phase 9 success criterion #2 reference `tournament_results` — actual table is `leaderboard` (same bug as PREFLIGHT-01). All acceptance criteria below use the literal `leaderboard`. Cleanup of REQUIREMENTS.md wording is deferred to a follow-up docs commit (same precedent as Phase 8).
  - D-09-02-06 — **Cross-plan reason-state wiring (closes checker Blocker 1)**: after writing the marker JSON, `auto_flip_ml_predictions()` ALSO calls `set_current_reason(reason)` on Plan 09-03's `services/trading-engine/app/aggregation/ml_gate_reasons.py` module. This makes the live truthful reason a single in-process value that every signal-aggregator emission site reads at zero file-IO cost. Without this wiring, the 5-member enum in Plan 09-03 is reachable only through hardcoded `"manual_override"` values and ROADMAP SC#3's example `(e.g., no_evidence: 3, dsr_below_gate: 1)` is impossible to reproduce in production. Plan 09-02 imports `set_current_reason` from Plan 09-03's module (one-way import — Plan 09-03 has no reverse dep on 09-02; this is the only cross-plan import in Phase 9). Wave bumped from 1 to 2 to reflect the dep.
must_haves:
  truths:
    - "Trading-engine startup with a `leaderboard` row where `dsr > 0.95`, `psr_ci_published = 1`, and `run_date` within 14 days logs the literal `MLGATE_AUTO_FLIP direction=enabled reason=dsr_above_gate`."
    - "Trading-engine startup with no qualifying row logs `MLGATE_AUTO_FLIP direction=disabled reason=no_evidence`."
    - "Trading-engine startup with a qualifying-DSR row but `run_date` older than 14 days logs `MLGATE_AUTO_FLIP direction=disabled reason=evidence_stale`."
    - "Trading-engine startup with a `psr_ci_published=1` row whose `dsr <= 0.95` logs `MLGATE_AUTO_FLIP direction=disabled reason=dsr_below_gate`."
    - "After auto-flip, the marker file `/run/mlgate_auto_flip.json` exists and parses to JSON with schema_version=1 and the corresponding `direction` + `reason` matching the log line."
    - "The CI grep gate `test_mlgate_auto_flip_log_exists` FAILS if the `MLGATE_AUTO_FLIP` log emission is removed from `services/trading-engine/app/lifespan/ml.py`."
    - "Phase 8's `check_dsr_evidence()` now applies the 14-day staleness rule from `run_date` (NOT `tournament_start_ts`) and only considers rows with `psr_ci_published = 1`."
    - "After `auto_flip_ml_predictions()` returns, `get_current_reason()` (from `app.aggregation.ml_gate_reasons` — Plan 09-03 module) returns the same reason as the marker JSON; this is the value that downstream signal-aggregator `log_ml_disabled()` calls read at zero file-IO cost (per D-09-02-06)."
    - "Each of the 5 disabled-event enum reasons (`no_evidence`, `dsr_below_gate`, `evidence_stale`, `regime_shift`, `manual_override`) is reachable in production: a unit test seeds the leaderboard to produce each of the first 3 reasons (`no_evidence`, `dsr_below_gate`, `evidence_stale`) and asserts `get_current_reason()` matches; `regime_shift` is reserved for v1.2 (no production path in Phase 9 — documented in SUMMARY.md follow-ups); `manual_override` is the default before any auto-flip fires."
  artifacts:
    - path: "services/trading-engine/app/lifespan/ml.py"
      provides: "Lifespan-stage auto-flip of ENABLE_ML_PREDICTIONS based on DSR evidence + marker writer + set_current_reason cross-plan wiring"
      contains: "MLGATE_AUTO_FLIP"
      contains_2: "def auto_flip_ml_predictions"
      contains_6: "set_current_reason"
    - path: "services/trading-engine/app/preflight/checks.py"
      provides: "Updated check_dsr_evidence with 14-day staleness rule (Path A — single source of truth)"
      contains_3: "psr_ci_published"
      contains_4: "timedelta(days=14)"
    - path: "services/trading-engine/tests/test_ml_gate_auto_flip.py"
      provides: "Unit tests asserting both directions of MLGATE_AUTO_FLIP against seeded SQLite rows + cross-plan reason-state propagation (≥7 cases — adds reason-state propagation test)"
      min_tests: 7
    - path: "tests/integration/test_mlgate_grep_gates.py"
      provides: "CI grep gate for MLGATE_AUTO_FLIP log emission survival (sibling to test_preflight_grep_gates.py)"
      contains_5: "MLGATE_AUTO_FLIP"
  key_links:
    - from: "services/trading-engine/app/lifespan/ml.py"
      to: "services/trading-engine/app/preflight/checks.py::check_dsr_evidence"
      via: "function call inside auto_flip_ml_predictions()"
      pattern: "check_dsr_evidence"
    - from: "services/trading-engine/app/lifespan/ml.py"
      to: "/run/mlgate_auto_flip.json"
      via: "json.dumps + Path.write_text"
      pattern: "_MLGATE_MARKER_PATH|mlgate_auto_flip.json"
    - from: "services/trading-engine/app/lifespan/ml.py"
      to: "services/trading-engine/app/aggregation/ml_gate_reasons.py::set_current_reason"
      via: "function call after marker JSON write (D-09-02-06 cross-plan wiring)"
      pattern: "set_current_reason\\("
    - from: "services/trading-engine/app/preflight/checks.py::check_dsr_evidence"
      to: "leaderboard.run_date column (added by migration 0002 from Plan 09-01)"
      via: "SELECT ... ORDER BY run_date DESC"
      pattern: "ORDER BY run_date DESC"
    - from: "tests/integration/test_mlgate_grep_gates.py"
      to: "services/trading-engine/app/lifespan/ml.py"
      via: "subprocess grep + pathlib rglob (dual-form, mirrored from test_preflight_grep_gates.py)"
      pattern: "MLGATE_AUTO_FLIP"

coverage_trace:
  - id: MLGATE-02
    source: "REQUIREMENTS.md MLGATE-02 + ROADMAP Phase 9 success criteria #2 and #5"
    tasks: [task-1, task-2, task-3]
---

<objective>
Deliver MLGATE-02: a trading-engine startup auto-flip of `ENABLE_ML_PREDICTIONS` based on DSR evidence in the `leaderboard` table, with a structured log emission, a marker JSON file for downstream consumers, a cross-plan in-process reason-state cache (set via Plan 09-03's `set_current_reason`), and a CI grep gate that detects silent removal.

Purpose: This is the load-bearing gate that turns ML predictions back on ONLY when evidence justifies it. Without this auto-flip, the operator must remember the flag manually — the exact "code, not human memory" failure mode that Phase 9 closes. The grep gate makes the enforcement a permanent contract: a future refactor that drops the log emission fails CI. Per D-09-02-06, the cross-plan reason-state wiring ensures all 5 enum reasons in Plan 09-03 are actually reachable at runtime (closes checker Blocker 1: without this wiring, every signal-aggregator emission would log `manual_override` regardless of true cause).

Output:
- `auto_flip_ml_predictions()` function in `services/trading-engine/app/lifespan/ml.py` invoked at the start of `init_ml()`.
- Marker JSON file write to `/run/mlgate_auto_flip.json` (schema pinned in D-09-02-02).
- Cross-plan call to `set_current_reason(reason)` on Plan 09-03's `app.aggregation.ml_gate_reasons` module after the marker write (D-09-02-06).
- Extended `check_dsr_evidence()` in `services/trading-engine/app/preflight/checks.py` honoring the 14-day staleness rule (Path A — single source of truth).
- Unit tests `services/trading-engine/tests/test_ml_gate_auto_flip.py` (≥7 cases against seeded SQLite — includes reason-state propagation assertion).
- In-place updates to 4 named Phase 8 DSR-evidence tests in `test_preflight_checks.py` to seed `psr_ci_published=1` + fresh `run_date` (Task 1 action step 8 — promoted from "may need" to "MUST update").
- CI grep gate `tests/integration/test_mlgate_grep_gates.py` (mirrors `test_preflight_grep_gates.py` shape).
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
@.planning/phases/08-pre-live-preflight/08-03-SUMMARY.md
@.planning/phases/09-ml-re-enablement-gate/09-03-reason-enum-and-digest-PLAN.md  # Plan 09-03 owns the ml_gate_reasons module — this plan IMPORTS from it (one-way; see D-09-02-06)

@services/trading-engine/app/lifespan/ml.py
@services/trading-engine/app/lifespan/__init__.py
@services/trading-engine/app/lifespan/risk.py
@services/trading-engine/app/preflight/checks.py
@services/trading-engine/app/main.py
@tests/integration/test_preflight_grep_gates.py
@services/tournament-harness/migrations/0001_initial.sql

<interfaces>
<!-- Contracts the executor will consume — extracted from codebase -->

From `services/trading-engine/app/preflight/checks.py:43-58` (existing constants — REUSE, do not redefine):
```python
_MLGATE_MARKER_PATH = "/run/mlgate_auto_flip.json"   # Phase 8 already references this
_DEFAULT_TOURNAMENT_DB_PATH = "/data/tournament.db"
_LIVE_STRICT_CAP = 0.02
_DSR_FLOOR = 0.95
```

From `services/trading-engine/app/preflight/checks.py:198-271` (existing check_dsr_evidence to EXTEND, not replace):
```python
def check_dsr_evidence(db_path: str | None = None) -> CheckResult:
    """DSR > 0.95 row in the `leaderboard` table — best-effort in Phase 8.
    Returns UNKNOWN if ML disabled, table empty/unreachable, or Phase 9's
    auto-flip marker (/run/mlgate_auto_flip.json) is absent."""
    if os.environ.get("ENABLE_ML_PREDICTIONS", "false").lower() != "true":
        return CheckResult(check="dsr_evidence", status="PASS", detail="...")
    if not Path(_MLGATE_MARKER_PATH).is_file():
        return CheckResult(check="dsr_evidence", status="UNKNOWN", detail="...")
    # ... current query is "SELECT dsr FROM leaderboard ORDER BY tournament_start_ts DESC LIMIT 1"
    # Phase 9 must extend with 14-day staleness rule via run_date + psr_ci_published.
```

From `services/trading-engine/tests/test_preflight_checks.py` — Phase 8 DSR-evidence tests this plan MUST update (Task 1 step 8 — promoted from "may need" to "MUST update"; tests at file-search-verified line numbers):
```python
# Line 244: def test_check_dsr_evidence_ml_disabled_passes(monkeypatch)
#   → ML-disabled short-circuit; no leaderboard read. NO seed-fixture change needed (already passes ML-disabled branch).
# Line 252: def test_check_dsr_evidence_ml_enabled_no_marker_is_unknown(monkeypatch, tmp_path)
#   → Marker-absent path; no leaderboard read. NO seed-fixture change needed.
# Line 266: def test_check_dsr_evidence_ml_enabled_with_row_above_gate_passes(...)
#   → MUST UPDATE: row insert MUST include psr_ci_published=1 AND run_date=<ISO-8601 within 14 days of test now>.
# Line 288: def test_check_dsr_evidence_ml_enabled_with_row_at_or_below_gate_fails(...)
#   → MUST UPDATE: row insert MUST include psr_ci_published=1 AND run_date=<ISO-8601 within 14 days of test now>.
```

From `services/trading-engine/app/lifespan/ml.py:15-25` (existing init_ml entry point — insertion site for auto-flip):
```python
@asynccontextmanager
async def init_ml():
    """TA aggregator health probe + attribution analyzer init."""
    logger.info("init_ml: enter")
    settings = get_settings()
    # >>> Phase 9 auto-flip inserts HERE, BEFORE aggregator construction <<<
    from app.main import ta_service_health
    try:
        aggregator = await get_aggregator()  # reads settings.enable_ml_predictions
```

From `services/trading-engine/app/config.py:90` (Pydantic field that the auto-flip mutates via os.environ + reload):
```python
enable_ml_predictions: bool = Field(default=False, ...)  # env var ENABLE_ML_PREDICTIONS
```

From `tests/integration/test_preflight_grep_gates.py:50-95` — exact shape to clone for `test_mlgate_grep_gates.py`:
```python
REPO_ROOT = Path(__file__).resolve().parents[2]
TE_APP = REPO_ROOT / "services" / "trading-engine" / "app"
# Dual-form scan: pathlib rglob + subprocess grep; scope is TE_APP (not REPO_ROOT)
# so docs prose containing the literal cannot satisfy the gate.
```

From `services/trading-engine/app/main.py:271-284` — structural template for log-then-act pattern (mirror, do not import):
```python
if settings.max_risk_per_trade > 0.02:
    logger.critical(
        "LIVE_PREFLIGHT_REJECTED reason=cap_too_high "
        f"cap={settings.max_risk_per_trade} limit=0.02"
    )
    raise RuntimeError(...)  # log FIRST, then act
```

From Plan 09-03's `services/trading-engine/app/aggregation/ml_gate_reasons.py` (NEW module — exists by the time this plan runs because Plan 09-03 is Wave 1 and this plan is Wave 2):
```python
# Module-level state set by Plan 09-02's auto_flip_ml_predictions().
# Read by Plan 09-03's log_ml_disabled() default-reason path.
_current_reason: MLGateReason = "manual_override"  # default before any auto-flip fires

def set_current_reason(reason: MLGateReason) -> None: ...
def get_current_reason() -> MLGateReason: ...
```

From the new migration 0002 (Plan 09-01) — these columns exist on `leaderboard` at deploy time:
```sql
ALTER TABLE leaderboard ADD COLUMN run_date TEXT;
ALTER TABLE leaderboard ADD COLUMN psr_ci_published INTEGER NOT NULL DEFAULT 0;
CREATE INDEX idx_leaderboard_psr_published ON leaderboard(psr_ci_published, run_date DESC);
```
For unit tests in Task 2, apply both migrations inline via `pathlib.Path.read_text() + conn.executescript(...)` so the test fixture does not depend on the runtime migration runner.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Extend `check_dsr_evidence()` with 14-day staleness rule + psr_ci_published filter + update Phase 8 fixtures</name>
  <read_first>
    - services/trading-engine/app/preflight/checks.py (entire file — D-09-02-01 commits to Path A: this function is the single source of truth)
    - .planning/phases/08-pre-live-preflight/08-01-SUMMARY.md "DSR sqlite error handling" decision (preserve the `type(e).__name__` info-disclosure constraint)
    - services/trading-engine/tests/test_preflight_checks.py (the existing DSR-evidence tests — `test_check_dsr_evidence_ml_enabled_with_row_above_gate_passes` and friends; Task 2 unit tests will augment these without breaking)
    - The new migration 0002 from Plan 09-01 (the new columns this rule depends on)
  </read_first>
  <behavior>
    - When `ENABLE_ML_PREDICTIONS != "true"`: function still returns `CheckResult("dsr_evidence", "PASS", "ML disabled ...")` unchanged.
    - When marker file `/run/mlgate_auto_flip.json` absent: returns `UNKNOWN` (unchanged from Phase 8).
    - When marker present AND the leaderboard query yields zero rows: returns `UNKNOWN` with detail `"leaderboard empty (after psr_ci_published filter)"`.
    - When the latest qualifying row has `dsr > 0.95` AND `run_date` within 14 days of `now_utc`: returns `PASS` with detail including the dsr value AND the run_date age in days.
    - When the latest qualifying row has `dsr > 0.95` BUT `run_date` older than 14 days: returns `FAIL` with detail `"evidence stale: run_date=<iso> age_days=<N> > 14"`.
    - When the latest qualifying row has `dsr <= 0.95`: returns `FAIL` with detail `"dsr=<value> <= 0.95"`.
    - SQL query is: `SELECT dsr, run_date FROM leaderboard WHERE psr_ci_published = 1 AND status = 'success' AND run_date IS NOT NULL ORDER BY run_date DESC LIMIT 1` (uses the index added by Plan 09-01).
    - sqlite3.Error path still leaks only `type(e).__name__` — preserves Phase 8's info-disclosure decision.
    - **Phase 8 test backward-compat (UPDATED per checker WARNING 4)**: the 4 named Phase 8 DSR-evidence tests at `test_preflight_checks.py` lines 244, 252, 266, 288 still PASS after this plan's edits. The two tests that READ a leaderboard row (`test_check_dsr_evidence_ml_enabled_with_row_above_gate_passes` line 266, `test_check_dsr_evidence_ml_enabled_with_row_at_or_below_gate_fails` line 288) MUST have their seed-fixtures updated in this task to set `psr_ci_published=1` AND `run_date` within the 14-day window. The two tests that short-circuit before the leaderboard read (`test_check_dsr_evidence_ml_disabled_passes` line 244, `test_check_dsr_evidence_ml_enabled_no_marker_is_unknown` line 252) need NO seed change.
  </behavior>
  <action>
    Per D-09-02-01 and checker WARNING 4, modify `services/trading-engine/app/preflight/checks.py::check_dsr_evidence`:
    1. **Add a new module constant** at top of file (near `_DSR_FLOOR`): `_DSR_EVIDENCE_STALENESS_DAYS = 14`. Naming mirrors `_LIVE_STRICT_CAP` and `_DSR_FLOOR` styles already in the file.
    2. **Replace the SQL query**: the current line reading `SELECT dsr FROM leaderboard ORDER BY tournament_start_ts DESC LIMIT 1` becomes `SELECT dsr, run_date FROM leaderboard WHERE psr_ci_published = 1 AND status = 'success' AND run_date IS NOT NULL ORDER BY run_date DESC LIMIT 1`.
    3. **Add an optional injectable `now` parameter** to the function signature: `def check_dsr_evidence(db_path: str | None = None, *, now: datetime | None = None) -> CheckResult`. Default to `datetime.now(timezone.utc)`. This is for deterministic unit testing; Phase 8's existing tests pass `now=None` (default) implicitly.
    4. **After fetching `(dsr, run_date)`**: parse `run_date` as ISO-8601 UTC via `datetime.fromisoformat(run_date.replace("Z", "+00:00"))`; compute `age = now - run_date_dt`; if `age > timedelta(days=_DSR_EVIDENCE_STALENESS_DAYS)` AND `dsr > _DSR_FLOOR`, return `FAIL` with detail `f"evidence stale: run_date={run_date} age_days={age.days} > {_DSR_EVIDENCE_STALENESS_DAYS}"`.
    5. **Preserve all existing return paths**: ML-disabled PASS, marker-absent UNKNOWN, sqlite-error UNKNOWN with `type(e).__name__`, empty-result UNKNOWN. The new staleness path is a tightening of the FAIL/PASS branches only.
    6. **Update the module docstring** for the function to mention the new contract: "DSR > 0.95 AND psr_ci_published=1 AND run_date within 14 days (Phase 9 MLGATE-02)".
    7. **Do NOT** add any new threats to the existing Phase 8 grep-gate scope — this file already passes `test_preflight_module_imports_at_lifespan` (Phase 8 gate #2), and the literal `LIVE_PREFLIGHT_REJECTED` MUST still not appear in this file (Phase 8 grep gate #1 scope is satisfied by absence). Mutations are limited to the function body.
    8. **MUST update Phase 8 fixtures (promoted from "may need" per checker WARNING 4)**: the 4 named Phase 8 DSR-evidence tests must be addressed explicitly:
       - **`test_check_dsr_evidence_ml_disabled_passes`** (line 244): NO change required — short-circuits before leaderboard read.
       - **`test_check_dsr_evidence_ml_enabled_no_marker_is_unknown`** (line 252): NO change required — short-circuits before leaderboard read.
       - **`test_check_dsr_evidence_ml_enabled_with_row_above_gate_passes`** (line 266): **MUST UPDATE** — the row INSERT MUST include `psr_ci_published=1` (so the new `WHERE psr_ci_published = 1` filter passes) AND `run_date` as an ISO-8601 UTC string within 14 days of the test `now` (so the new staleness rule passes). Existing INSERT columns and `dsr` value are preserved; only the two new columns are added. If the test does not currently apply migration 0002 inline, that step is added (read `0002_mlgate_evidence_columns.sql` via `pathlib.Path.read_text()` and `conn.executescript(...)` after the 0001 apply — same pattern Plan 09-01's tests use).
       - **`test_check_dsr_evidence_ml_enabled_with_row_at_or_below_gate_fails`** (line 288): **MUST UPDATE** — same as above (`psr_ci_published=1` + fresh `run_date`), preserving the at-or-below `dsr` value so the FAIL path still fires for the right reason (`dsr_below_gate`, not `evidence_stale`).
       Acceptance criterion below verifies these per-test fixture updates by greps for the new column names in the test bodies.
    9. The Task 2 unit tests in `test_ml_gate_auto_flip.py` cover the new behavior surface (staleness FAIL, dsr-below FAIL, no-row UNKNOWN, fresh-PASS) — they do NOT replace the Phase 8 tests; they augment.
  </action>
  <verify>
    <automated>cd /mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine &amp;&amp; pytest tests/test_preflight_checks.py -v -k "dsr_evidence" 2&gt;&amp;1 | tail -25</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "psr_ci_published = 1" services/trading-engine/app/preflight/checks.py` returns ≥1.
    - `grep -c "ORDER BY run_date DESC" services/trading-engine/app/preflight/checks.py` returns 1.
    - `grep -c "_DSR_EVIDENCE_STALENESS_DAYS" services/trading-engine/app/preflight/checks.py` returns ≥3 (constant definition + at least one use in the check + the detail message).
    - `grep -c "timedelta(days=" services/trading-engine/app/preflight/checks.py` returns ≥1.
    - All existing Phase 8 DSR-evidence unit tests still PASS: `pytest tests/test_preflight_checks.py -v -k "dsr_evidence" 2&gt;&amp;1 | grep -c "PASSED"` returns ≥4 (the four DSR-evidence tests Phase 8 shipped).
    - **Per-test fixture updates verified (checker WARNING 4)**: each of the two row-inserting Phase 8 tests now seeds the new columns. Run `awk '/^def test_check_dsr_evidence_ml_enabled_with_row_above_gate_passes/,/^def /' services/trading-engine/tests/test_preflight_checks.py | grep -c "psr_ci_published"` returns ≥1; same for `test_check_dsr_evidence_ml_enabled_with_row_at_or_below_gate_fails`. Run `awk '/^def test_check_dsr_evidence_ml_enabled_with_row_above_gate_passes/,/^def /' services/trading-engine/tests/test_preflight_checks.py | grep -c "run_date"` returns ≥1; same for the other test.
    - Both updated Phase 8 tests also reference migration 0002: `awk '/^def test_check_dsr_evidence_ml_enabled_with_row_above_gate_passes/,/^def /' services/trading-engine/tests/test_preflight_checks.py | grep -cE "0002|mlgate_evidence_columns"` returns ≥1 (or the inline ALTER TABLE columns appear in the fixture build).
    - The literal `LIVE_PREFLIGHT_REJECTED` still does NOT appear in `services/trading-engine/app/preflight/checks.py` (Phase 8 grep gate #1 scope unchanged): `grep -c "LIVE_PREFLIGHT_REJECTED" services/trading-engine/app/preflight/checks.py` returns 0.
    - The literal `tournament_start_ts` is no longer used for ORDER BY: `grep -c "ORDER BY tournament_start_ts" services/trading-engine/app/preflight/checks.py` returns 0 (the column may still be selected/referenced for other purposes, but ORDER BY moves to `run_date`).
  </acceptance_criteria>
  <done>
    `check_dsr_evidence()` honors 14-day staleness + `psr_ci_published=1` filter; the two row-inserting Phase 8 DSR-evidence tests have their seed-fixtures updated to set `psr_ci_published=1` AND `run_date` within 14 days; all 4 Phase 8 DSR-evidence tests still pass; new constant `_DSR_EVIDENCE_STALENESS_DAYS=14` is in place; no Phase 8 grep gate scope violations.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Lifespan auto-flip phase + marker writer + cross-plan reason-state wiring + unit tests against seeded SQLite</name>
  <read_first>
    - services/trading-engine/app/lifespan/ml.py (full file — insertion point at start of `init_ml()`)
    - services/trading-engine/app/lifespan/__init__.py (re-export pattern — extend with `auto_flip_ml_predictions` if exposed)
    - services/trading-engine/app/lifespan/risk.py (analog: simple lifespan phase with cap-honoring logic — same shape applies)
    - services/trading-engine/app/main.py lines 268-284 (the analog: log-FIRST-then-act pattern for the LIVE-strict cap check; same ordering applies here per D-09-02-04)
    - services/trading-engine/app/preflight/checks.py (the new check_dsr_evidence from Task 1 — auto-flip will CALL this function)
    - **services/trading-engine/app/aggregation/ml_gate_reasons.py** (NEW module from Plan 09-03 — Task 2 here calls `set_current_reason()` exported by Plan 09-03 Task 1)
    - services/trading-engine/tests/test_preflight_checks.py (sqlite fixture pattern with `_insert_row` helper — clone for the new test file)
    - services/trading-engine/tests/test_preflight_lifespan.py (Phase 8 lifespan test patterns — for source-inspection regression guard)
  </read_first>
  <behavior>
    - `auto_flip_ml_predictions()` is a sync function (NOT async) — called once from `init_ml()` BEFORE the `await get_aggregator()` line, BEFORE `from app.main import ta_service_health`. It maps the verdict of `check_dsr_evidence()` to an enum reason and:
      - On PASS: sets `os.environ["ENABLE_ML_PREDICTIONS"] = "true"` AFTER emitting the log line; writes marker with `direction="enabled" reason="dsr_above_gate"`.
      - On FAIL with stale detail: sets `os.environ["ENABLE_ML_PREDICTIONS"] = "false"`; writes marker with `direction="disabled" reason="evidence_stale"`.
      - On FAIL with dsr-below detail: same env mutation; reason `dsr_below_gate`.
      - On UNKNOWN with marker-absent (Phase 8 path) → first-boot case: reason `no_evidence`, direction `disabled`.
      - On UNKNOWN with sqlite/empty: same — `no_evidence`.
    - Log emission MUST appear at `logger.critical(...)` level with the literal substring `MLGATE_AUTO_FLIP direction=<value> reason=<value>` (no f-string fragments that split the literal; the substring must be one contiguous string in the source).
    - Settings reload: `from app.config import reload_settings; reload_settings()` is called AFTER env mutation so `signal_aggregator.py:1125` and `aggregation/enhanced_aggregator.py:59` see the new value at construction time.
    - Marker write: `Path("/run/mlgate_auto_flip.json").write_text(json.dumps({...}))` — schema per D-09-02-02. Use `os.makedirs("/run", exist_ok=True)` for first-boot safety; if the path is not writable (read-only mount), log a warning and continue WITHOUT raising — the gate must not crash the trading engine on a marker-write failure.
    - **Cross-plan reason-state propagation (D-09-02-06 — closes checker Blocker 1)**: AFTER the marker JSON write (whether the write succeeded or failed), `auto_flip_ml_predictions()` MUST also call `set_current_reason(reason)` from `app.aggregation.ml_gate_reasons`. This makes the truthful reason visible to Plan 09-03's `log_ml_disabled()` calls at every signal-aggregator emission site. The `set_current_reason()` call MUST be wrapped in a `try/except Exception` block — failure to update the in-process cache MUST NOT crash the trading engine (best-effort cross-plan contract; the marker JSON is the durable source of truth).
    - The function MUST NOT raise on any error path; trading-engine boot continues even if marker write OR `set_current_reason` call fails. The log emission is the load-bearing contract; the marker is best-effort cross-process state; `set_current_reason` is best-effort in-process state for the signal-aggregator emissions.
  </behavior>
  <action>
    Per D-09-02-03, D-09-02-04, D-09-02-05, and D-09-02-06:
    1. **Add to `services/trading-engine/app/lifespan/ml.py`** a sync function `auto_flip_ml_predictions(now: datetime | None = None, marker_path: str | None = None) -> dict`:
       - Imports added at top: `import json`, `import os`, `from datetime import datetime, timezone`, `from pathlib import Path`, `from app.preflight import check_dsr_evidence`, `from app.preflight.checks import _MLGATE_MARKER_PATH`, **`from app.aggregation.ml_gate_reasons import set_current_reason`** (NEW per D-09-02-06 — module owned by Plan 09-03; this is the ONLY cross-plan import in Phase 9).
       - Reason enum module constant: `_MLGATE_REASONS = ("no_evidence", "dsr_below_gate", "evidence_stale", "regime_shift", "manual_override", "dsr_above_gate")` — used for runtime guard against typos. This 6-member tuple is intentionally a superset of Plan 09-03's 5-member `ML_GATE_REASONS` (adds `dsr_above_gate` for the enabled direction).
       - Body:
         ```
         result = check_dsr_evidence(now=now)
         # Map verdict → (direction, reason)
         if result.status == "PASS" and "ML disabled" in result.detail:
             # ENABLE_ML_PREDICTIONS already off; nothing to flip. Treat as manual_override.
             direction, reason = "disabled", "manual_override"
         elif result.status == "PASS":
             direction, reason = "enabled", "dsr_above_gate"
         elif result.status == "FAIL" and "stale" in result.detail:
             direction, reason = "disabled", "evidence_stale"
         elif result.status == "FAIL":
             direction, reason = "disabled", "dsr_below_gate"
         else:  # UNKNOWN
             direction, reason = "disabled", "no_evidence"
         assert reason in _MLGATE_REASONS  # internal contract — typo guard
         # LOG FIRST (per D-09-02-04 ordering)
         logger.critical(f"MLGATE_AUTO_FLIP direction={direction} reason={reason}")
         # THEN mutate env
         os.environ["ENABLE_ML_PREDICTIONS"] = "true" if direction == "enabled" else "false"
         from app.config import reload_settings
         reload_settings()
         # Best-effort marker write
         try:
             marker = Path(marker_path or _MLGATE_MARKER_PATH)
             marker.parent.mkdir(parents=True, exist_ok=True)
             payload = {
                 "schema_version": 1,
                 "direction": direction,
                 "reason": reason,
                 "evaluated_at": (now or datetime.now(timezone.utc)).isoformat(),
                 "dsr_value": _extract_dsr_from_detail(result.detail),  # helper; None if absent
                 "run_date": _extract_run_date_from_detail(result.detail),
             }
             marker.write_text(json.dumps(payload))
         except OSError as e:
             logger.warning(f"MLGATE marker write failed: {type(e).__name__}")
         # D-09-02-06 cross-plan reason-state propagation (closes checker Blocker 1):
         # Cache the truthful reason in Plan 09-03's module so every signal-aggregator
         # emission site reads the live reason at zero file-IO cost. Best-effort — if the
         # cache update fails, trading-engine boot continues (the marker JSON above is the
         # durable source of truth).
         try:
             # set_current_reason only accepts Plan 09-03's 5-member disabled-event vocab.
             # For the enabled direction (reason="dsr_above_gate"), we do NOT propagate
             # via this cache — Plan 09-03's log_ml_disabled() is by definition the
             # disabled-event emission path; when ML is enabled, no disabled-event fires.
             if reason in ("no_evidence", "dsr_below_gate", "evidence_stale", "regime_shift", "manual_override"):
                 set_current_reason(reason)
         except Exception as e:  # noqa: BLE001 — best-effort cross-plan cache; never crash boot
             logger.warning(f"MLGATE set_current_reason failed: {type(e).__name__}")
         return {"direction": direction, "reason": reason}
         ```
       - Place this function ABOVE `init_ml` so it's available for unit tests via plain `from app.lifespan.ml import auto_flip_ml_predictions`.
    2. **Call `auto_flip_ml_predictions()` from `init_ml`** as the very first line after `settings = get_settings()` and BEFORE `from app.main import ta_service_health`. Note: `auto_flip_ml_predictions()` is sync, so just call it directly (no await).
    3. **Re-export from `lifespan/__init__.py`**: add `auto_flip_ml_predictions` to the imports and `__all__` list so callers can do `from app.lifespan import auto_flip_ml_predictions` (mirrors the existing `init_data, init_ml, init_risk, init_strategy` pattern).
    4. **Add autoflake-survival F401 import in `services/trading-engine/app/main.py`**: near the existing `from app.preflight import run_all  # noqa: F401` line, add `from app.lifespan import auto_flip_ml_predictions  # noqa: F401` so the package-level import is referenced and grep gate #2 from Phase 8 (which asserts `from app.preflight import` survives) is extended in spirit. This new import is what grep gate #3 in Task 3 anchors on.
    5. **Create unit tests** at `services/trading-engine/tests/test_ml_gate_auto_flip.py` (≥7 cases — adds reason-state propagation test per D-09-02-06):
       - `test_auto_flip_enabled_when_fresh_dsr_above_gate`: seed leaderboard with `dsr=0.97, psr_ci_published=1, run_date=now-3d`; set `ENABLE_ML_PREDICTIONS=true` in env so the ML-disabled short-circuit does NOT fire; call `auto_flip_ml_predictions(now=fixed_now, marker_path=tmp_marker)`; assert returned `{"direction": "enabled", "reason": "dsr_above_gate"}`; assert log captured `"MLGATE_AUTO_FLIP direction=enabled reason=dsr_above_gate"`; assert marker JSON parses with `schema_version=1, direction="enabled", reason="dsr_above_gate"`; assert `os.environ["ENABLE_ML_PREDICTIONS"] == "true"`.
       - `test_auto_flip_disabled_when_no_evidence`: empty leaderboard + marker absent in tmp path; expect `direction="disabled", reason="no_evidence"`; log + marker assertions parallel above.
       - `test_auto_flip_disabled_when_evidence_stale`: seed with `dsr=0.97, psr_ci_published=1, run_date=now-20d`; expect `direction="disabled", reason="evidence_stale"`.
       - `test_auto_flip_disabled_when_dsr_below_gate`: seed with `dsr=0.90, psr_ci_published=1, run_date=now-3d`; expect `direction="disabled", reason="dsr_below_gate"`.
       - `test_auto_flip_ignores_unpublished_rows`: seed with `dsr=0.99, psr_ci_published=0, run_date=now-3d`; expect `direction="disabled", reason="no_evidence"` (psr_ci_published filter excludes the row).
       - `test_auto_flip_marker_write_failure_does_not_raise`: monkeypatch `Path.write_text` to raise OSError; call `auto_flip_ml_predictions`; assert it returns normally and emits a warning log; the trading engine boot must not crash on marker failures.
       - **NEW** `test_auto_flip_sets_current_reason_for_disabled_branches` (closes checker Blocker 1 — reachability proof for ≥3 enum members): parametrize over the three reachable disabled reasons (`no_evidence`, `dsr_below_gate`, `evidence_stale`); for each, seed the leaderboard to produce that exact reason (empty / dsr=0.90 fresh / dsr=0.97 stale); call `auto_flip_ml_predictions(...)`; import `get_current_reason` from `app.aggregation.ml_gate_reasons`; assert `get_current_reason() == expected_reason`. This is the production-side reachability assertion that ROADMAP SC#3 demands — every disabled-event reason must be reachable from the auto-flip outcome.
       - **NEW** `test_auto_flip_does_not_crash_when_set_current_reason_raises` (D-09-02-06 best-effort contract): monkeypatch `app.lifespan.ml.set_current_reason` to raise `RuntimeError`; call `auto_flip_ml_predictions`; assert it returns normally with the expected direction/reason; assert a warning log contains `"set_current_reason failed"`; assert the marker JSON was still written (cross-plan failure does NOT block durable state).
    6. Tests MUST run under `services/trading-engine/tests/` pytest layout (matches Phase 8 conventions). Use monkeypatch to set `ENABLE_ML_PREDICTIONS=true` in env so the ML-disabled short-circuit in `check_dsr_evidence` does not fire (per memory `feedback_api_gateway_test_env.md`-style: run host pytest under the local trading-engine virtualenv; if FastAPI version mismatch surfaces, defer to in-container `docker exec crypto-bot-trading pytest ...`).
    7. Tests MUST `reset_counter()` and re-import the `app.aggregation.ml_gate_reasons` state at the start of `test_auto_flip_sets_current_reason_for_disabled_branches` to prevent cross-test contamination of the module-level `_current_reason` cache.
  </action>
  <verify>
    <automated>cd /mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine &amp;&amp; pytest tests/test_ml_gate_auto_flip.py -v 2&gt;&amp;1 | tail -30</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "def auto_flip_ml_predictions" services/trading-engine/app/lifespan/ml.py` returns 1.
    - `grep -c "MLGATE_AUTO_FLIP direction=" services/trading-engine/app/lifespan/ml.py` returns ≥1 (the literal f-string template).
    - `grep -c "reload_settings" services/trading-engine/app/lifespan/ml.py` returns ≥1 (settings reload after env mutation).
    - `grep -c "schema_version" services/trading-engine/app/lifespan/ml.py` returns ≥1 (marker JSON includes schema_version=1).
    - **`grep -c "set_current_reason" services/trading-engine/app/lifespan/ml.py` returns ≥2** (import + call site per D-09-02-06).
    - **`grep -c "from app.aggregation.ml_gate_reasons import set_current_reason" services/trading-engine/app/lifespan/ml.py` returns 1** (the canonical cross-plan import).
    - `grep -c "auto_flip_ml_predictions" services/trading-engine/app/lifespan/__init__.py` returns ≥1 (re-exported).
    - `grep -c "auto_flip_ml_predictions" services/trading-engine/app/main.py` returns ≥1 (F401 autoflake-survival import).
    - All ≥7 unit tests PASS: `pytest services/trading-engine/tests/test_ml_gate_auto_flip.py -v 2&gt;&amp;1 | grep -c "PASSED"` returns ≥7 (6 original + 1 reason-state propagation + 1 set_current_reason failure-safety = 8 functions; parametrize counts increase further if pytest expands).
    - Existing Phase 8 lifespan tests still PASS (no regressions): `pytest services/trading-engine/tests/test_preflight_lifespan.py -v 2&gt;&amp;1 | grep -c "PASSED"` returns 6 (the 6 invocations Phase 8 shipped).
    - Log emission verified via caplog: `grep -c "caplog" services/trading-engine/tests/test_ml_gate_auto_flip.py` returns ≥4.
    - Function order in source: `awk '/^def auto_flip_ml_predictions/{a=NR} /^async def init_ml/{b=NR} END{print (a&lt;b)?"OK":"WRONG"}' services/trading-engine/app/lifespan/ml.py` prints `OK` (auto_flip_ml_predictions defined ABOVE init_ml so unit tests can import it directly).
    - **Reason-reachability proof**: `pytest services/trading-engine/tests/test_ml_gate_auto_flip.py::test_auto_flip_sets_current_reason_for_disabled_branches -v 2&gt;&amp;1 | grep -c "PASSED"` returns ≥3 (parametrized over `no_evidence`, `dsr_below_gate`, `evidence_stale`).
  </acceptance_criteria>
  <done>
    Auto-flip phase wired into `init_ml`; settings reload after env mutation; marker JSON written per schema; `set_current_reason()` called after marker write (best-effort, per D-09-02-06 — closes checker Blocker 1); ≥7 unit tests pass including reason-state propagation for 3 disabled-event reasons; Phase 8 lifespan tests still pass (no regressions). `MLGATE_AUTO_FLIP direction=<value> reason=<value>` log literal appears in production code.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: CI grep gate — `MLGATE_AUTO_FLIP` log emission survival (sibling to Phase 8 gates)</name>
  <read_first>
    - tests/integration/test_preflight_grep_gates.py (the EXACT shape to mirror — dual-form pathlib + subprocess; scope narrowed to TE_APP; assertion-message-doesn't-self-trigger pattern)
    - .planning/phases/08-pre-live-preflight/08-03-SUMMARY.md "Boundary-Agreement Test Detail" + "Manual Verification Records" (the failure-mode-mutation discipline Phase 8 used; Phase 9 mirrors)
    - services/trading-engine/app/lifespan/ml.py (the new code from Task 2 — verify the grep target literal is there)
    - The new test file from Task 2 (so the grep gate scope can be tested as enforcing the production-code emission, not the test-code copy)
  </read_first>
  <behavior>
    - `test_mlgate_auto_flip_log_exists` (gate #3): subprocess `grep -r "MLGATE_AUTO_FLIP" services/trading-engine/app/` returns ≥1 match. The grep scope is strictly `services/trading-engine/app/` (NOT REPO_ROOT) per Phase 8 lesson — otherwise this PLAN.md prose containing the literal would satisfy the gate.
    - `test_mlgate_module_imports_at_main` (gate #4): `services/trading-engine/app/main.py` source contains `from app.lifespan import auto_flip_ml_predictions` OR `import app.lifespan.ml` — defends against autoflake stripping the F401 import. Mirrors Phase 8's `test_preflight_module_imports_at_lifespan`.
    - Both gates DUAL-FORM: pathlib rglob (cross-platform) + subprocess grep (CI-command fidelity). Both must pass; divergence flags either a path-resolution bug or a missed exclusion.
    - The test file itself MUST NOT contain the literal `MLGATE_AUTO_FLIP` outside the subprocess command argument and the regex pattern — the assertion message must avoid the literal (Phase 8 lesson: the meta-test self-tripped on its own assertion message in 08-01-SUMMARY.md issue #2).
    - Failure-mode verification (manual, documented in SUMMARY.md): mutating the log literal in `lifespan/ml.py` causes the gate to FAIL with a clear diagnostic message naming `lifespan/ml.py`.
  </behavior>
  <action>
    Per D-09-02-04 and Phase 8 patterns:
    1. Create `tests/integration/test_mlgate_grep_gates.py` by CLONING the shape of `tests/integration/test_preflight_grep_gates.py` exactly (the module-level docstring style, REPO_ROOT + TE_APP constants, dual-form scan with subprocess scope narrowed to TE_APP, assertion messages that do not contain the literal grep target).
    2. **Module-level constants**: `REPO_ROOT = Path(__file__).resolve().parents[2]`; `TE_APP = REPO_ROOT / "services" / "trading-engine" / "app"`. Scope is TE_APP only — Plan PLAN.md and CONTEXT.md may contain the `MLGATE_AUTO_FLIP` literal as prose; a docs-only match must NOT satisfy the gate.
    3. **`test_mlgate_auto_flip_log_exists`**:
       - pathlib pass: build the pattern via re.compile on the literal token (not via an f-string that splits the literal), iterate `TE_APP.rglob("*.py")` excluding `/tests/`, collect matches. Assert `matches` is non-empty with a message that names the expected file path (`services/trading-engine/app/lifespan/ml.py`) but does NOT include the bare literal `MLGATE_AUTO_FLIP` as a contiguous substring — assemble the diagnostic from variables so the test file does not self-satisfy the gate.
       - subprocess pass: `subprocess.run(["grep", "-r", "MLGATE_AUTO_FLIP", str(TE_APP)])`; assert stdout non-empty. Scope MUST be `TE_APP`, not `REPO_ROOT`.
    4. **`test_mlgate_module_imports_at_main`**: `inspect.getsource(main_mod)` returns the trading-engine main.py source; assert `"from app.lifespan import" in src AND ("auto_flip_ml_predictions" in src OR "ml" in src)` — accept either the named import OR the bare module reference, mirror Phase 8 gate #2's permissive form.
    5. **Manual failure-mode verification step** (executor performs and records in SUMMARY.md):
       - Mutate `MLGATE_AUTO_FLIP` to `DISABLED_FOR_FAIL_TEST` in `services/trading-engine/app/lifespan/ml.py` via `sed` to a backup-then-restore pattern.
       - Run `pytest tests/integration/test_mlgate_grep_gates.py::test_mlgate_auto_flip_log_exists -v` — confirm FAILS with the diagnostic naming `lifespan/ml.py`.
       - Restore original via the `/tmp/ml.py.orig` backup; re-run; confirm PASSES.
       - Record before/after `grep -c` counts in SUMMARY.md "Manual Verification Records" section (mirror 08-03-SUMMARY.md lines 104-116 format).
    6. **Co-existence with Phase 8 grep gates**: the new file `test_mlgate_grep_gates.py` is a SIBLING file to `test_preflight_grep_gates.py`, NOT a combined file (advisor's note: bundling them lets a future edit blur scope). The Phase 8 file is unmodified by this task; both pytest test files run independently in CI.
    7. **CI wiring** (deferred to Phase 12 or operator follow-up): no GitHub Actions workflow changes in this plan — the existing `.github/workflows/preflight-live-readiness.yml` runs `pytest tests/integration/test_preflight_grep_gates.py` (Phase 8 line 42); adding `test_mlgate_grep_gates.py` to that same step is a single-line CI workflow edit and is documented as a follow-up in this plan's SUMMARY.md (NOT executed here to keep scope sharp).
  </action>
  <verify>
    <automated>cd /mnt/d/Bimo_max/crypto-trading-bot &amp;&amp; pytest tests/integration/test_mlgate_grep_gates.py -v 2&gt;&amp;1 | tail -15</automated>
  </verify>
  <acceptance_criteria>
    - File `tests/integration/test_mlgate_grep_gates.py` exists.
    - Both grep gate tests PASS: `pytest tests/integration/test_mlgate_grep_gates.py -v 2&gt;&amp;1 | grep -c "PASSED"` returns 2.
    - `grep -c "TE_APP = REPO_ROOT" tests/integration/test_mlgate_grep_gates.py` returns 1 (scope-narrowed pattern from Phase 8).
    - `grep -c "subprocess.run" tests/integration/test_mlgate_grep_gates.py` returns ≥1 (dual-form: pathlib + subprocess).
    - The test file does NOT pass scope=REPO_ROOT into its subprocess grep: `grep -A 5 "subprocess.run" tests/integration/test_mlgate_grep_gates.py | grep -c "REPO_ROOT" | awk '{print ($1==0)?"OK":"WRONG"}'` prints OK (scope locality enforced).
    - The grep target literal appears in the test file ONLY inside the subprocess argument list and the re.compile call (never in an assertion message or docstring as a contiguous substring): `grep -c "MLGATE_AUTO_FLIP" tests/integration/test_mlgate_grep_gates.py` returns ≤3 (typical: one in `re.compile`, one in `subprocess.run` arg, optionally one in a module docstring without other concerning context).
    - Phase 8 grep gates STILL pass (no co-existence regression): `pytest tests/integration/test_preflight_grep_gates.py -v 2&gt;&amp;1 | grep -c "PASSED"` returns 2.
    - The SUMMARY.md (per `<output>` block) contains a "Manual Verification Records" section with before/after grep counts showing the failure-mode verification was performed.
  </acceptance_criteria>
  <done>
    Two new CI grep gates pass; the failure-mode mutation verification is recorded in SUMMARY.md; Phase 8 grep gates still pass; the test file scope is TE_APP only (never REPO_ROOT in subprocess calls). The `MLGATE_AUTO_FLIP` log emission is now a permanent contract — silent removal fails CI.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Trading-engine startup → leaderboard sqlite | Reading-only via `check_dsr_evidence()`; mutates `os.environ` based on read result. SQL injection surface = zero (parameter-free literal query). |
| Trading-engine process → `/run/mlgate_auto_flip.json` | Writes a non-secret marker file; readable by all processes in the trading-engine container. No PII / secrets in the marker. |
| Trading-engine process → `app.aggregation.ml_gate_reasons` (in-process state) | Module-level cache set by lifespan; read by signal-aggregator emission sites. Same-process state only; no cross-container coherence claim. |
| CI grep gate → production code | Read-only static scan; no execution. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-09-02-01 | Tampering | Forged DSR row inserted to enable ML auto-flip | mitigate | Per T-09-01-01 (Plan 09-01): leaderboard writes go through tournament-harness orchestrator only; this plan READS the leaderboard and writes only the marker file. The `psr_ci_published=1` filter further requires the canonical kernel path to have run (Plan 09-01 driver). |
| T-09-02-02 | Tampering | Future-dated `run_date` to bypass 14-day staleness | mitigate | `run_date` is written by tournament-harness when the row is created (per Plan 09-01 D-09-01-02). This plan READS `run_date` and applies the staleness rule against `now_utc` (injectable for tests, defaults to system clock). The leaderboard PK includes git_sha + tournament_start_ts, both stamped by CI, so a forged future date contradicts the audit trail. |
| T-09-02-03 | Repudiation | Operator silently removes `MLGATE_AUTO_FLIP` log to avoid audit | mitigate | CI grep gate `test_mlgate_auto_flip_log_exists` (Task 3) blocks merge if the literal is removed from `services/trading-engine/app/lifespan/ml.py`. Mirrors Phase 8's `test_live_preflight_rejected_log_exists` enforcement model. |
| T-09-02-04 | Information Disclosure | Marker file leaks DSR value to unauthenticated readers | accept | DSR value is a public metric (already exposed via `/api/preflight/live-readiness` per Phase 8 D-09 unauthenticated read-only decision). No secrets in the marker. |
| T-09-02-05 | Denial of Service | Marker write fails on read-only mount and crashes trading-engine boot | mitigate | Task 2 action step 6: marker write wrapped in try/except OSError; logs warning and continues. Trading-engine boot is NEVER blocked by marker failure (verified by `test_auto_flip_marker_write_failure_does_not_raise`). |
| T-09-02-06 | Elevation of Privilege | Auto-flip enables ML in LIVE mode where it should not | accept | This phase's gate is `dsr > 0.95 AND psr_ci_published=1 AND run_date within 14d` — the same evidence floor `dsr > 0.95` is the LIVE-readiness gate per CLAUDE.md + Phase 8. There is no path where the auto-flip enables ML without the evidence row already satisfying the LIVE-ready criterion. Phase 8 PREFLIGHT-02 still gates LIVE bootup with the cap-check; auto-flip in PAPER mode is the only consequence of an incorrect enable, and PAPER mode never trades real money per ADR-010 + CLAUDE.md. |
| T-09-02-07 | Denial of Service | `set_current_reason()` raises and crashes trading-engine boot | mitigate | D-09-02-06 best-effort contract: the call is wrapped in `try/except Exception`; failure logs a warning and the function continues. Verified by `test_auto_flip_does_not_crash_when_set_current_reason_raises` in Task 2 step 5. The marker JSON remains the durable source of truth — a failed in-process cache update has no operator-visible impact beyond a stale `manual_override` default in signal-aggregator emissions until the next boot. |
</threat_model>

<verification>
1. **Phase 8 backward compatibility**: `pytest services/trading-engine/tests/test_preflight_checks.py -v` returns ≥23 PASSED (Phase 8 shipped 23 — see 08-01-SUMMARY.md lines 96-125); the new staleness rule does not regress.
2. **Phase 8 lifespan tests still pass**: `pytest services/trading-engine/tests/test_preflight_lifespan.py -v` shows 6 PASSED (Phase 8 shipped 6 — see 08-03-SUMMARY.md line 141).
3. **New auto-flip unit tests pass**: `pytest services/trading-engine/tests/test_ml_gate_auto_flip.py -v` shows ≥7 PASSED.
4. **New grep gates pass**: `pytest tests/integration/test_mlgate_grep_gates.py -v` shows 2 PASSED; manual failure-mode mutation FAILED the gate before restore.
5. **Phase 8 grep gates still pass**: `pytest tests/integration/test_preflight_grep_gates.py -v` shows 2 PASSED.
6. **Marker JSON schema** validates against D-09-02-02: the unit tests assert `schema_version=1, direction ∈ {enabled, disabled}, reason ∈ enum`.
7. **Log literal is a contiguous substring**: `grep -c "MLGATE_AUTO_FLIP direction=" services/trading-engine/app/lifespan/ml.py` returns ≥1 (no f-string fragmentation).
8. **Cross-plan reason-state propagation** (D-09-02-06): `pytest services/trading-engine/tests/test_ml_gate_auto_flip.py::test_auto_flip_sets_current_reason_for_disabled_branches -v` shows ≥3 PASSED (one per parametrized reason: `no_evidence`, `dsr_below_gate`, `evidence_stale`).
9. **`set_current_reason()` failure does not crash boot**: `pytest services/trading-engine/tests/test_ml_gate_auto_flip.py::test_auto_flip_does_not_crash_when_set_current_reason_raises -v` shows 1 PASSED.
</verification>

<success_criteria>
- All 3 tasks' acceptance criteria pass.
- ROADMAP Phase 9 success criterion #2 holds: seeded SQLite + `dsr>0.95 + run_date within 14d` → log `MLGATE_AUTO_FLIP direction=enabled reason=dsr_above_gate`; no qualifying row → `direction=disabled reason=no_evidence`. Both directions asserted in unit tests.
- ROADMAP Phase 9 success criterion #5 holds: removing the log literal from `lifespan/ml.py` causes `test_mlgate_auto_flip_log_exists` to fail (manually verified, recorded in SUMMARY.md).
- ROADMAP Phase 9 success criterion #3 (enum reachability — partial; full coverage delivered with Plan 09-03): the 3 evidence-driven disabled reasons (`no_evidence`, `dsr_below_gate`, `evidence_stale`) are demonstrably reachable from the auto-flip outcome and propagate to Plan 09-03's `get_current_reason()` (D-09-02-06).
- Phase 8's `check_dsr_evidence()` is the single source of truth (Path A per D-09-02-01) — no duplicate DSR-row query lives in `lifespan/ml.py`.
- `/run/mlgate_auto_flip.json` marker JSON schema is pinned at `schema_version=1` with the exact field set in D-09-02-02 — Phase 10 dashboard tile reads this without re-discovery.
- Cross-plan reason-state wiring (D-09-02-06): `set_current_reason()` is called on every auto-flip with a 5-member-enum-compatible reason; the in-process cache is the live source for Plan 09-03's `log_ml_disabled()` default-reason fallback.
</success_criteria>

<output>
After completion, create `.planning/phases/09-ml-re-enablement-gate/09-02-SUMMARY.md` with:
- `requires`: [09-03-reason-enum-and-digest] (Wave 2; the cross-plan import of `set_current_reason` from Plan 09-03's `app.aggregation.ml_gate_reasons` module is the only Phase 9 cross-plan code dep. Runtime deploy dependency on Plan 09-01's migration 0002 is documented in the operator deploy-order note below but is NOT enforced at test-time — fixtures apply both SQL files inline.)
- `provides`: auto_flip_ml_predictions lifespan phase; MLGATE_AUTO_FLIP log emission contract; `/run/mlgate_auto_flip.json` marker schema_version=1 (cross-phase interface); `set_current_reason()` cross-plan wiring closing checker Blocker 1 (every disabled-event signal-aggregator emission now reads the truthful reason from in-process state, not hardcoded `manual_override`); two new CI grep gates
- `affects`: phase 09-03 MLGATE-03 (Plan 09-03's `log_ml_disabled` reads `get_current_reason()` populated by THIS plan; without this wiring, the 5-member enum collapses to one reachable value — see checker Blocker 1); phase 10 DASHLIVE-01 (reads marker JSON for tile rendering); Phase 8 `check_dsr_evidence()` (extended in-place, not duplicated); Phase 8 tests `test_check_dsr_evidence_ml_enabled_with_row_above_gate_passes` + `test_check_dsr_evidence_ml_enabled_with_row_at_or_below_gate_fails` (fixtures updated in-place per Task 1 step 8)
- Decisions made (D-09-02-01 through D-09-02-06) carried forward
- Manual failure-mode verification record (mutation → FAIL → restore → PASS) — mirror 08-03-SUMMARY.md lines 104-116
- Three commit hashes (one per task)

**Operator deploy-order note (checker WARNING 3)**: Apply Plan 09-01's tournament-harness migration 0002 BEFORE booting trading-engine with `ENABLE_ML_PREDICTIONS=true`. If migration 0002 has not landed, the `psr_ci_published` and `run_date` columns are missing on `leaderboard`; `check_dsr_evidence` will raise `sqlite3.OperationalError`, the existing Phase 8 sqlite-error path returns `UNKNOWN`, and the auto-flip maps `UNKNOWN → direction=disabled reason=no_evidence`. This is **graceful degradation** — the trading engine does NOT crash on boot; ML stays off as the safe default. But the auto-flip gate is non-functional until the migration runs. Recommended sequence on a fresh deploy:
  1. Apply migration 0002 (Plan 09-01 — `services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql`).
  2. Run `python -m scripts.forward_paper_test.run_evidence_loop` to populate `psr_ci_published=1` on qualifying rows (Plan 09-01).
  3. Boot trading-engine — `auto_flip_ml_predictions()` will now see the populated `leaderboard` and either flip ML on (if `dsr > 0.95 AND run_date within 14d`) or emit a truthful `reason=` (`dsr_below_gate` / `evidence_stale`).
  Record this sequence in the SUMMARY.md "Deploy Order" subsection so a future operator does not need to re-discover it.
</output>
