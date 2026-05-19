---
phase: 08-pre-live-preflight
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - services/trading-engine/app/preflight/__init__.py
  - services/trading-engine/app/preflight/types.py
  - services/trading-engine/app/preflight/checks.py
  - services/trading-engine/tests/test_preflight_checks.py
autonomous: true
requirements:
  - PREFLIGHT-01
tags:
  - preflight
  - trading-engine
  - foundation

must_haves:
  truths:
    - "`from app.preflight import run_all` returns a PreflightReport with exactly 6 CheckResult rows (cap, paper_mode, trading_mode, ack, emergency_stop, dsr_evidence)."
    - "PreflightReport.to_dict() serialises to the JSON schema_version=1 shape pinned in 08-CONTEXT.md (schema_version, overall, evaluated_at, checks[])."
    - "check_cap returns PASS for PAPER+0.10 (ADR-010), FAIL for LIVE+0.03, PASS for LIVE+0.02."
    - "check_emergency_stop returns PASS when a *directory* sits at the path (WSL bind-mount edge case)."
    - "check_dsr_evidence returns PASS when ENABLE_ML_PREDICTIONS=false, UNKNOWN when ML on + Phase 9 marker absent."
  artifacts:
    - path: "services/trading-engine/app/preflight/__init__.py"
      provides: "package re-exports (run_all, all 6 check fns, CheckResult, PreflightReport)"
      contains: "run_all"
    - path: "services/trading-engine/app/preflight/types.py"
      provides: "CheckResult + PreflightReport dataclasses + to_dict()/to_json()"
      contains: "schema_version"
    - path: "services/trading-engine/app/preflight/checks.py"
      provides: "6 pure check functions + run_all aggregator"
      contains: "LIVE_PREFLIGHT_REJECTED is NOT in this file (lives in main.py per 08-03)"
    - path: "services/trading-engine/tests/test_preflight_checks.py"
      provides: "≥9 unit tests covering PASS/FAIL/UNKNOWN paths for each check"
      contains: "test_check_cap_live_rejects_3pct"
  key_links:
    - from: "services/trading-engine/app/preflight/__init__.py"
      to: "services/trading-engine/app/preflight/checks.py"
      via: "re-export"
      pattern: "from app\\.preflight\\.checks import run_all"
    - from: "services/trading-engine/app/preflight/checks.py"
      to: "services/trading-engine/app/config.py"
      via: "settings dependency injection"
      pattern: "from app\\.config import (get_settings|Settings)"
    - from: "services/trading-engine/app/preflight/checks.py"
      to: "services/trading-engine/app/preflight/types.py"
      via: "type imports"
      pattern: "from app\\.preflight\\.types import"
---

<objective>
Create the shared preflight module that owns the 6 LIVE-readiness check functions plus an aggregator. This is the FOUNDATION layer — both the CLI (08-02) and the HTTP route (08-02) and the lifespan grep-gate test (08-03) all import from `app.preflight`.

Purpose: Single source of truth for check logic — no subprocess wrapping, no logic duplication between CLI/HTTP. Zero third-party deps beyond stdlib + app.config + sqlite3 so the CLI can run on a dev laptop without docker.

Output:
- `services/trading-engine/app/preflight/` package (3 files)
- ≥9 passing unit tests covering each check's PASS/FAIL/UNKNOWN paths
</objective>

<execution_context>
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/workflows/execute-plan.md
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/08-pre-live-preflight/08-CONTEXT.md
@.planning/phases/08-pre-live-preflight/08-PATTERNS.md

<!-- Existing files this plan reads (analogs + targets) -->
@services/trading-engine/app/lifespan/__init__.py
@services/trading-engine/app/handlers/health.py
@services/trading-engine/app/config.py
@services/trading-engine/app/main.py
@services/trading-engine/tests/test_monitoring_alerts.py
@services/tournament-harness/migrations/0001_initial.sql

<interfaces>
<!-- Pinned from 08-PATTERNS.md so no codebase scavenging needed. -->

From services/trading-engine/app/config.py (already exists, line ~321):
```python
class Settings(BaseSettings):
    trading_mode: Literal["PAPER", "LIVE"] = "PAPER"
    max_risk_per_trade: float = 0.10            # ADR-010 paper-relaxed default
    emergency_stop_file: str = "/app/EMERGENCY_STOP"
    # ... (Pydantic v2 — keyword kwargs accepted directly on Settings(...))
```

NEW (this plan creates):
```python
# services/trading-engine/app/preflight/types.py
@dataclass(frozen=True)
class CheckResult:
    check: str              # one of: cap | paper_mode | trading_mode | ack | emergency_stop | dsr_evidence
    status: Literal["PASS", "FAIL", "UNKNOWN"]
    detail: str

@dataclass(frozen=True)
class PreflightReport:
    overall: Literal["PASS", "FAIL", "UNKNOWN"]
    checks: list[CheckResult]
    evaluated_at: str       # ISO-8601 UTC, factory-defaulted
    schema_version: int = 1
    def to_dict(self) -> dict: ...
    def to_json(self) -> str: ...

# services/trading-engine/app/preflight/checks.py
def check_cap(settings: Settings | None = None) -> CheckResult: ...
def check_paper_mode(settings: Settings | None = None) -> CheckResult: ...
def check_trading_mode(settings: Settings | None = None) -> CheckResult: ...
def check_ack(settings: Settings | None = None) -> CheckResult: ...
def check_emergency_stop(settings: Settings | None = None) -> CheckResult: ...
def check_dsr_evidence(db_path: str | None = None) -> CheckResult: ...
def run_all(settings: Settings | None = None) -> PreflightReport: ...
```

Production `leaderboard` schema (services/tournament-harness/migrations/0001_initial.sql:9-38, abridged to columns the DSR check reads):
```sql
CREATE TABLE leaderboard (
    run_id              TEXT NOT NULL,
    tournament_id       TEXT NOT NULL,
    architecture        TEXT NOT NULL,
    symbol              TEXT NOT NULL,
    horizon             INTEGER NOT NULL,
    target_mode         TEXT NOT NULL,
    hp_hash             TEXT NOT NULL,
    dsr                 REAL,
    git_sha             TEXT NOT NULL,
    tournament_start_ts TEXT NOT NULL,    -- <<< TEXT, not INTEGER. ISO-8601 strings.
    status              TEXT NOT NULL,
    -- ...other columns omitted; test fixture only needs the columns it reads/writes.
    PRIMARY KEY (architecture, symbol, horizon, target_mode, hp_hash, run_id)
);
```

The test fixture in Task 3 MUST match `tournament_start_ts TEXT NOT NULL`. The DSR check orders by this column DESC — a fixture with INTEGER timestamps would still sort, but pytest then validates against the wrong column type and a future schema-aware refactor (e.g., bound-param `datetime` comparisons) would silently break.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create preflight package skeleton + dataclass types</name>
  <files>services/trading-engine/app/preflight/__init__.py, services/trading-engine/app/preflight/types.py</files>
  <read_first>
    - services/trading-engine/app/lifespan/__init__.py (analog re-export shape — mirror exactly)
    - services/trading-engine/app/handlers/risk_budget.py:44-83 (Pydantic response model analog — but use @dataclass, not Pydantic, per 08-PATTERNS.md decision)
    - .planning/phases/08-pre-live-preflight/08-PATTERNS.md (lines 35-110 — full pattern + copy-ready code)
    - .planning/phases/08-pre-live-preflight/08-CONTEXT.md (lines 58-73 — locked JSON schema)
  </read_first>
  <behavior>
    - PreflightReport(overall="PASS", checks=[]) serialises to dict with keys: schema_version=1, overall, evaluated_at, checks.
    - CheckResult instances are frozen (immutable) — `result.status = "FAIL"` raises FrozenInstanceError.
    - `from app.preflight import run_all, CheckResult, PreflightReport, check_cap, check_paper_mode, check_trading_mode, check_ack, check_emergency_stop, check_dsr_evidence` succeeds (all 9 names re-exported).
    - `PreflightReport(...).to_json()` returns a valid JSON string parseable by `json.loads`.
  </behavior>
  <action>
    1. Create `services/trading-engine/app/preflight/__init__.py` mirroring `app/lifespan/__init__.py` shape (per 08-PATTERNS.md lines 41-65). Re-export: `run_all`, `check_cap`, `check_paper_mode`, `check_trading_mode`, `check_ack`, `check_emergency_stop`, `check_dsr_evidence`, `CheckResult`, `PreflightReport`. Populate `__all__`.

    2. Create `services/trading-engine/app/preflight/types.py` per 08-PATTERNS.md lines 79-108. Stdlib-only: `dataclasses.dataclass`, `dataclasses.asdict`, `dataclasses.field`, `datetime`, `typing.Literal`. Define:
       - `Status = Literal["PASS", "FAIL", "UNKNOWN"]`
       - `@dataclass(frozen=True) class CheckResult` with fields `check: str`, `status: Status`, `detail: str`
       - `@dataclass(frozen=True) class PreflightReport` with fields `overall: Status`, `checks: list[CheckResult]`, `evaluated_at: str` (default_factory = `lambda: datetime.now(timezone.utc).isoformat()`), `schema_version: int = 1`
       - `to_dict(self) -> dict` returns `asdict(self)`
       - `to_json(self) -> str` returns `json.dumps(asdict(self), indent=2)`

    3. NOTE: checks.py is created in Task 2; checks.py's symbols are referenced by __init__.py but the re-export only resolves once Task 2 lands. That's OK — `app.preflight` is not imported by anything in this plan's test suite until Task 3, so the import will resolve when needed. Optional: temporarily comment the checks-related re-exports in __init__.py; uncomment after Task 2.
  </action>
  <verify>
    <automated>cd services/trading-engine &amp;&amp; python -c "from dataclasses import asdict; from app.preflight.types import CheckResult, PreflightReport; r = PreflightReport(overall='PASS', checks=[CheckResult(check='cap', status='PASS', detail='ok')]); d = asdict(r); assert d['schema_version'] == 1; assert d['overall'] == 'PASS'; assert d['checks'][0]['check'] == 'cap'; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - Source assertion: `grep -c "schema_version" services/trading-engine/app/preflight/types.py` returns ≥1.
    - Source assertion: `grep -c "frozen=True" services/trading-engine/app/preflight/types.py` returns ≥2 (CheckResult + PreflightReport).
    - Source assertion: `grep -c "Literal" services/trading-engine/app/preflight/types.py` returns ≥1.
    - Behavior assertion: the python one-liner in `<verify>` exits 0 and prints `OK`.
  </acceptance_criteria>
  <done>types.py + __init__.py exist, types are frozen dataclasses, schema_version=1 pinned, all 9 symbols re-exported through `app.preflight`.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement 6 check functions + run_all aggregator</name>
  <files>services/trading-engine/app/preflight/checks.py</files>
  <read_first>
    - services/trading-engine/app/handlers/health.py (lines 24-100 — aggregator analog: compose checks, return dict)
    - services/trading-engine/app/main.py (lines 250-258 — existing LIVE_TRADING_ACK check, line 282-283 — `.is_file()` over `.exists()` for bind-mount safety)
    - services/trading-engine/app/config.py (line ~321 — `max_risk_per_trade` field)
    - services/tournament-harness/migrations/0001_initial.sql (line 23 — `leaderboard.dsr` column; line 28 — `tournament_start_ts TEXT NOT NULL`; line 41 — index)
    - .planning/phases/08-pre-live-preflight/08-PATTERNS.md (lines 114-248 — full pattern, copy-ready code per check)
    - .planning/phases/08-pre-live-preflight/08-CONTEXT.md (lines 95-101 — REQUIREMENTS.md says `tournament_results`, schema actually defines `leaderboard`; read from leaderboard, this is a wording bug, not a schema requirement)
  </read_first>
  <behavior>
    - check_cap: PAPER→PASS (any cap), LIVE+cap>0.02→FAIL with both numbers in detail, LIVE+cap≤0.02→PASS.
    - check_paper_mode: PAPER_TRADING_MODE=true→FAIL in LIVE, false→PASS; non-LIVE→PASS regardless.
    - check_trading_mode: TRADING_MODE=LIVE→PASS, anything else→FAIL with detected mode in detail.
    - check_ack: LIVE_TRADING_ACK exact match "I_UNDERSTAND_REAL_MONEY"→PASS, anything else→FAIL; non-LIVE→PASS (skipped).
    - check_emergency_stop: `.is_file()` returns False (no file, or directory at path)→PASS; `.is_file()` returns True→FAIL.
    - check_dsr_evidence: ENABLE_ML_PREDICTIONS≠true→PASS (skipped); ML on + `/run/mlgate_auto_flip.json` absent→UNKNOWN; ML on + marker present + leaderboard empty/unreachable→UNKNOWN; marker present + leaderboard row with dsr>0.95→PASS; row with dsr≤0.95→FAIL.
    - run_all: returns PreflightReport with 6 checks in the order [cap, paper_mode, trading_mode, ack, emergency_stop, dsr_evidence]. overall=FAIL if any FAIL, else UNKNOWN if any UNKNOWN, else PASS.
  </behavior>
  <action>
    1. Create `services/trading-engine/app/preflight/checks.py` matching 08-PATTERNS.md lines 114-248. Module docstring per lines 121-131.

    2. Implement each function per the patterns:
       - `check_cap(settings=None)` per lines 148-170. Use `settings or get_settings()`. Read `s.max_risk_per_trade` (config.py:321) and `s.trading_mode`.
       - `check_paper_mode(settings=None)`: read `s.paper_trading_mode` (defaults vary by mode). In LIVE: True→FAIL("PAPER_TRADING_MODE=true while LIVE"), False→PASS. In PAPER: PASS (skipped).
       - `check_trading_mode(settings=None)`: `s.trading_mode == "LIVE"` → PASS; else FAIL.
       - `check_ack(settings=None)`: in LIVE only, read `os.environ.get("LIVE_TRADING_ACK", "")` and compare to literal `"I_UNDERSTAND_REAL_MONEY"`. (Do NOT read from settings — main.py:251 also reads from `os.environ` directly; mirror the same source-of-truth.)
       - `check_emergency_stop(settings=None)` per lines 176-196. **Use `.is_file()` not `.exists()`** — this is load-bearing for the WSL bind-mount gotcha (CLAUDE.md + main.py:282).
       - `check_dsr_evidence(db_path=None)` per lines 201-224. Short-circuit to PASS if `ENABLE_ML_PREDICTIONS!=true`. Else check `/run/mlgate_auto_flip.json`: absent→UNKNOWN("MLGATE-02 marker absent (Phase 9 not landed)"). If present, open SQLite at `db_path or "/data/tournament.db"` (use a sensible default; fail-soft to UNKNOWN on connection error), run `SELECT dsr FROM leaderboard ORDER BY tournament_start_ts DESC LIMIT 1` with bound parameters (no string interpolation), report PASS if dsr>0.95 else FAIL. If table empty or query errors → UNKNOWN with the cause in detail.
         - **IMPORTANT (CONTEXT.md decision):** REQUIREMENTS.md wording says `tournament_results`; actual schema defines `leaderboard`. Read from `leaderboard`. Add comment referencing 08-CONTEXT.md lines 95-101 and tournament-harness migration 0001:23. Do NOT create a new table — Phase 9 owns evidence-row schema.
         - **Column type note (load-bearing for Task 3 fixture):** `tournament_start_ts` is `TEXT NOT NULL` (ISO-8601 string), not INTEGER. SQLite's lexicographic `ORDER BY ... DESC` over ISO-8601 strings is equivalent to chronological descending — no implementation work needed in checks.py beyond reading the column, but Task 3's seeded fixture MUST match this column type.

    3. Implement `run_all(settings=None) -> PreflightReport` per lines 229-247. Compose all 6 in the fixed order. Compute `overall` per the precedence: any FAIL → FAIL; else any UNKNOWN → UNKNOWN; else PASS.

    4. Confirm `services/trading-engine/app/preflight/__init__.py` re-exports work after this file lands (if Task 1 commented them out, uncomment now).
  </action>
  <verify>
    <automated>cd services/trading-engine &amp;&amp; python -c "from app.preflight import run_all, check_cap; from app.config import Settings; r = check_cap(Settings(trading_mode='LIVE', max_risk_per_trade=0.03)); assert r.status == 'FAIL' and '0.03' in r.detail and '0.02' in r.detail, r; r2 = check_cap(Settings(trading_mode='PAPER', max_risk_per_trade=0.10)); assert r2.status == 'PASS', r2; rep = run_all(); assert len(rep.checks) == 6; assert {c.check for c in rep.checks} == {'cap','paper_mode','trading_mode','ack','emergency_stop','dsr_evidence'}; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - Source assertion: `grep -c "is_file()" services/trading-engine/app/preflight/checks.py` returns ≥1 (bind-mount safety).
    - Source assertion: `grep -c "FROM leaderboard" services/trading-engine/app/preflight/checks.py` returns ≥1 (correct table per CONTEXT.md decision).
    - Source assertion: `grep -cE "^def (check_cap|check_paper_mode|check_trading_mode|check_ack|check_emergency_stop|check_dsr_evidence|run_all)" services/trading-engine/app/preflight/checks.py` returns 7.
    - Source assertion: `grep -c "LIVE_PREFLIGHT_REJECTED" services/trading-engine/app/preflight/checks.py` returns 0 — this literal lives in main.py only (08-03 owns it; grep-gate scope is `app/`, so a stray copy here would still pass the gate but pollute scope).
    - Behavior assertion: the python one-liner in `<verify>` exits 0 and prints `OK`.
  </acceptance_criteria>
  <done>All 6 check functions + run_all implemented; LIVE+0.03 cap returns FAIL with both numbers in detail; PAPER allows 10%; emergency_stop uses .is_file(); dsr_evidence reads from `leaderboard` table with bound params and returns UNKNOWN when ML disabled marker absent.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Unit tests for every check + run_all</name>
  <files>services/trading-engine/tests/test_preflight_checks.py</files>
  <read_first>
    - services/trading-engine/tests/test_monitoring_alerts.py (lines 53-100 — monkeypatch.setenv + Settings override analog)
    - services/trading-engine/tests/unit/test_config.py (lines 62-66 — Pydantic Settings keyword-arg pattern)
    - services/tournament-harness/migrations/0001_initial.sql (lines 9-38 — production `leaderboard` schema. Line 28: `tournament_start_ts TEXT NOT NULL`. The test fixture below MUST match this column type, not INTEGER.)
    - .planning/phases/08-pre-live-preflight/08-PATTERNS.md (lines 512-594 — copy-ready test patterns)
  </read_first>
  <behavior>
    - test_check_cap_paper_allows_10pct: Settings(trading_mode="PAPER", max_risk_per_trade=0.10) → status=PASS.
    - test_check_cap_live_rejects_3pct: Settings(trading_mode="LIVE", max_risk_per_trade=0.03) → status=FAIL, "0.03" and "0.02" in detail.
    - test_check_cap_live_accepts_2pct: Settings(trading_mode="LIVE", max_risk_per_trade=0.02) → status=PASS.
    - test_check_ack_present: monkeypatch.setenv("LIVE_TRADING_ACK","I_UNDERSTAND_REAL_MONEY"), Settings(trading_mode="LIVE") → status=PASS.
    - test_check_ack_missing_in_live: monkeypatch.delenv("LIVE_TRADING_ACK", raising=False), Settings(trading_mode="LIVE") → status=FAIL.
    - test_check_emergency_stop_file_present: tmp_path/"EMERGENCY_STOP".write_text(""), Settings(emergency_stop_file=...) → status=FAIL.
    - test_check_emergency_stop_directory_at_path_is_not_file: (tmp_path/"EMERGENCY_STOP").mkdir() → status=PASS (WSL bind-mount edge case — `.is_file()` returns False).
    - test_check_emergency_stop_absent: empty tmp_path → status=PASS.
    - test_check_dsr_evidence_ml_disabled_passes: monkeypatch.setenv("ENABLE_ML_PREDICTIONS","false") → status=PASS.
    - test_check_dsr_evidence_ml_enabled_no_marker_is_unknown: ENABLE_ML_PREDICTIONS=true + no marker → status=UNKNOWN, "Phase 9" or "marker" in detail.
    - test_check_dsr_evidence_ml_enabled_with_row_above_gate_passes: ML on + marker present + seeded sqlite leaderboard row with dsr=0.97 → status=PASS, "0.97" in detail. Fixture column types match production schema (see action step 3 below).
    - test_dsr_fixture_schema_matches_production: source-inspection guard — assert the CREATE TABLE statement in this test file declares `tournament_start_ts TEXT NOT NULL` (not INTEGER) so the fixture column type matches services/tournament-harness/migrations/0001_initial.sql:28. Catches a future copy-paste regression where someone "fixes" the fixture back to INTEGER.
    - test_run_all_returns_six_checks_in_order: `run_all()` returns `len(report.checks) == 6`, names in fixed order.
    - test_run_all_overall_precedence: any FAIL → overall=FAIL; UNKNOWN-without-FAIL → overall=UNKNOWN; all PASS → overall=PASS (three sub-assertions or three tests).
  </behavior>
  <action>
    1. Create `services/trading-engine/tests/test_preflight_checks.py`. Use Pydantic Settings keyword-arg pattern (no env-var roundtrip, no `reload_settings()`).

    2. Write tests per the `<behavior>` list. Cover the 3 cap permutations (PAPER+10%, LIVE+3%, LIVE+2%), both ACK paths, all 3 emergency_stop paths (file present / directory at path / absent), all 4 DSR paths (ML off / marker absent / row above gate / row at-or-below gate via seeded sqlite using `sqlite3.connect(tmp_path/"tournament.db")`), and run_all's 6-check ordering + precedence.

    3. **DSR sqlite-seeded test — fixture schema MUST mirror production** (services/tournament-harness/migrations/0001_initial.sql:9-38). The fixture only needs the columns the DSR check reads (`dsr`) plus the `ORDER BY` column and a minimal PK-satisfying subset, but every included column's type MUST match production:

       ```python
       # Defined once at module/fixture level, used by every DSR-seed test.
       LEADERBOARD_SCHEMA_SQL = """
       CREATE TABLE leaderboard (
           run_id              TEXT NOT NULL,
           tournament_id       TEXT NOT NULL,
           architecture        TEXT NOT NULL,
           symbol              TEXT NOT NULL,
           horizon             INTEGER NOT NULL,
           target_mode         TEXT NOT NULL,
           hp_hash             TEXT NOT NULL,
           dsr                 REAL,
           git_sha             TEXT NOT NULL,
           tournament_start_ts TEXT NOT NULL,    -- ISO-8601 string, matches production
           status              TEXT NOT NULL,
           PRIMARY KEY (architecture, symbol, horizon, target_mode, hp_hash, run_id)
       );
       """
       # ...
       cur.execute(LEADERBOARD_SCHEMA_SQL)
       cur.execute(
           "INSERT INTO leaderboard "
           "(run_id, tournament_id, architecture, symbol, horizon, target_mode, "
           " hp_hash, dsr, git_sha, tournament_start_ts, status) "
           "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
           (
               "run-001", "tourn-001", "gru", "BTCUSDT", 24, "log_returns",
               "deadbeef", 0.97, "abc123", "2026-05-16T14:32:01Z", "success",
           ),
       )
       ```

       **Why this matters:** The production schema declares `tournament_start_ts TEXT NOT NULL` (services/tournament-harness/migrations/0001_initial.sql:28). The DSR check's `ORDER BY tournament_start_ts DESC` relies on lexicographic ordering of ISO-8601 strings (which is also chronological for fixed-format ISO-8601). A fixture using `INTEGER` epoch timestamps would still order correctly today, but would silently diverge from production type semantics — and any future migration to bound `datetime` comparisons (e.g., adding a 14-day staleness filter per MLGATE-02) would pass the test against the fixture but fail in production.

    4. Patch `/run/mlgate_auto_flip.json` presence via `monkeypatch.setattr("pathlib.Path.is_file", ...)` scoped to the marker path only (or use `monkeypatch.setattr` on the module-level constant if the implementation uses one).

    5. Add `test_dsr_fixture_schema_matches_production` — a meta-test that source-inspects this very test file via `inspect.getsource(...)` (or reads it back via `Path(__file__).read_text()`) and asserts:
       - `"tournament_start_ts TEXT NOT NULL"` substring appears in the file.
       - `"tournament_start_ts INTEGER"` substring does NOT appear in the file.

       This is the regression detector that catches a future "fix" reverting the fixture to INTEGER timestamps.

    6. NOTE per 08-PATTERNS.md "Pydantic Settings constructor for unit tests" — `Settings(trading_mode="LIVE", max_risk_per_trade=0.03)` is supported by Pydantic v2 directly; no env-roundtrip needed.
  </action>
  <verify>
    <automated>cd services/trading-engine &amp;&amp; pytest tests/test_preflight_checks.py -v --tb=short</automated>
  </verify>
  <acceptance_criteria>
    - Source assertion: `grep -cE "^def test_" services/trading-engine/tests/test_preflight_checks.py` returns ≥13 (12 behavior tests + the new fixture-schema meta-test; parametrised precedence test counts as one).
    - Source assertion: `grep -c "test_check_emergency_stop_directory_at_path_is_not_file" services/trading-engine/tests/test_preflight_checks.py` returns 1 (the WSL bind-mount edge-case test is present, not silently dropped).
    - Source assertion: `grep -c "test_check_dsr_evidence_ml_enabled_with_row_above_gate_passes" services/trading-engine/tests/test_preflight_checks.py` returns 1.
    - Source assertion (fixture-schema correctness, addresses checker W1): `grep -c "tournament_start_ts TEXT NOT NULL" services/trading-engine/tests/test_preflight_checks.py` returns ≥1.
    - Source assertion (regression guard, addresses checker W1): `grep -c "tournament_start_ts INTEGER" services/trading-engine/tests/test_preflight_checks.py` returns 0 — the INTEGER form is FORBIDDEN; production schema is TEXT NOT NULL.
    - Source assertion: `grep -c "test_dsr_fixture_schema_matches_production" services/trading-engine/tests/test_preflight_checks.py` returns 1 (the meta-test is present).
    - Source assertion: `grep -c "'2026-05-16T14:32:01Z'\|\"2026-05-16T14:32:01Z\"" services/trading-engine/tests/test_preflight_checks.py` returns ≥1 — INSERT uses an ISO-8601 string timestamp, not an integer literal.
    - Behavior assertion: `pytest services/trading-engine/tests/test_preflight_checks.py -v` exits 0 with all tests passing; final line matches `passed` count ≥13.
  </acceptance_criteria>
  <done>≥13 unit tests pass against the preflight module; LIVE+3% FAILs, PAPER+10% PASSes, WSL-dir-at-EMERGENCY_STOP doesn't false-FAIL, DSR seeds + reads from leaderboard correctly, fixture `tournament_start_ts` is TEXT NOT NULL (matches production schema 0001_initial.sql:28), meta-test guards against future INTEGER regression.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| process env → preflight module | trading-engine env vars (MAX_RISK_PER_TRADE, LIVE_TRADING_ACK, ENABLE_ML_PREDICTIONS, TRADING_MODE) — same trust domain, sourced from operator-controlled `.env` |
| sqlite leaderboard → check_dsr_evidence | tournament-harness DB write boundary; reads only `dsr` and ordering column |
| filesystem (`/app/EMERGENCY_STOP`, `/run/mlgate_auto_flip.json`) → preflight | bind-mount paths under operator control |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-08-01-01 | I (Info disclosure) | check_dsr_evidence sqlite query | mitigate | Use parameterised query (`cursor.execute("SELECT dsr FROM leaderboard ORDER BY tournament_start_ts DESC LIMIT 1")` — no string interpolation, bound params only). Read column is numeric `dsr` (REAL); no string fields surfaced. |
| T-08-01-02 | D (DoS) | check_emergency_stop file lookup | mitigate | `.is_file()` not `.exists()` — handles WSL bind-mount race where Docker creates a directory at the mount path. Without this, false-FAIL on every boot in that environment. |
| T-08-01-03 | T (Tampering) | check_dsr_evidence — Phase 9 marker `/run/mlgate_auto_flip.json` | accept | Marker file is in same trust domain (operator-controlled host). If forged, dashboard surfaces PASS but trading-engine's own checks still gate LIVE boot. Phase 9 (MLGATE-02) will harden the marker semantics. |
| T-08-01-04 | E (Elevation) | check_ack reads `os.environ["LIVE_TRADING_ACK"]` not `settings.live_trading_ack` | accept | Same source as main.py:251 (LIVE_TRADING_ACK lifespan check). Reading from `os.environ` directly avoids a config-reload race where Settings caches a stale value; trade-off is intentional. |
| T-08-01-05 | I (Info disclosure) | CheckResult.detail strings include env values (e.g. `max_risk_per_trade=0.03`) | accept | These are configuration values, not secrets. Same disclosure level as `/api/config/safety-state` (D-09). No API keys, no balances. |
| T-08-01-06 | T (Tampering) | test fixture schema drifts from production `leaderboard` | mitigate | `test_dsr_fixture_schema_matches_production` meta-test asserts the CREATE TABLE in test file declares `tournament_start_ts TEXT NOT NULL` (matches services/tournament-harness/migrations/0001_initial.sql:28). Catches a future "fix" reverting fixture to INTEGER timestamps — that change would compile and pass today but silently diverge from production type semantics. |
</threat_model>

<verification>
- `cd services/trading-engine && pytest tests/test_preflight_checks.py -v` — all ≥13 tests pass.
- `python -c "from app.preflight import run_all; r = run_all(); assert len(r.checks) == 6"` — module callable from the package re-export surface.
- `grep -c "schema_version" services/trading-engine/app/preflight/types.py` returns ≥1.
- `grep -c "is_file()" services/trading-engine/app/preflight/checks.py` returns ≥1.
- `grep -c "FROM leaderboard" services/trading-engine/app/preflight/checks.py` returns ≥1.
- `grep -c "tournament_start_ts TEXT NOT NULL" services/trading-engine/tests/test_preflight_checks.py` returns ≥1.
- `grep -c "tournament_start_ts INTEGER" services/trading-engine/tests/test_preflight_checks.py` returns 0.
</verification>

<success_criteria>
- 3 source files created (`__init__.py`, `types.py`, `checks.py`) totalling roughly 200–300 lines.
- 1 test file with ≥13 passing tests.
- The bare-package import `from app.preflight import run_all` is legal (re-exports work) — this is what grep gate #2 in 08-03 will assert against main.py.
- No FastAPI dep in `checks.py` or `types.py` (stdlib + app.config + sqlite3 only) — verified by `grep -c "fastapi" services/trading-engine/app/preflight/` returning 0.
- `schema_version=1` baked into PreflightReport; never changed without bumping it (downstream contract for Phase 10 dashboard tile).
- Test fixture `leaderboard` schema matches production: `tournament_start_ts TEXT NOT NULL` (services/tournament-harness/migrations/0001_initial.sql:28) — checked by both an explicit grep gate AND a meta-test inside the test file.
</success_criteria>

<output>
After completion, create `.planning/phases/08-pre-live-preflight/08-01-SUMMARY.md` capturing:
- File list + line counts
- Test count (passed) + sample output of `run_all()` from a `python -c` invocation
- Decision note: REQUIREMENTS.md says `tournament_results`, actual schema is `leaderboard`; this plan reads from `leaderboard` per 08-CONTEXT.md decision. Flag for follow-up update to REQUIREMENTS.md wording (not a separate phase, can be a docs-only cleanup commit).
- Fixture-schema note: `tournament_start_ts` is `TEXT NOT NULL` (ISO-8601 string) per production `services/tournament-harness/migrations/0001_initial.sql:28`. Earlier draft of Task 3 declared it `INTEGER`; corrected during plan revision (checker W1). Meta-test `test_dsr_fixture_schema_matches_production` guards against regression.
- Any deviations from 08-PATTERNS.md code excerpts (e.g. if a default `db_path` was chosen — note the value).
</output>
</content>
</invoke>