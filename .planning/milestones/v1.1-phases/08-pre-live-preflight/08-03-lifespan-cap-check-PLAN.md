---
phase: 08-pre-live-preflight
plan: 03
type: execute
wave: 2
depends_on:
  - 08-01
files_modified:
  - services/trading-engine/app/main.py
  - services/trading-engine/tests/test_preflight_lifespan.py
  - tests/integration/test_preflight_grep_gates.py
autonomous: true
requirements:
  - PREFLIGHT-02
tags:
  - preflight
  - lifespan
  - boot-enforcement
  - grep-gates

must_haves:
  truths:
    - "trading-engine in TRADING_MODE=LIVE + MAX_RISK_PER_TRADE=0.03 + ACK present REFUSES to boot — raises RuntimeError with cap+limit in detail."
    - "trading-engine in TRADING_MODE=LIVE + MAX_RISK_PER_TRADE=0.02 + ACK present boots normally (cap-check passes)."
    - "trading-engine in TRADING_MODE=PAPER + MAX_RISK_PER_TRADE=0.10 boots normally (paper-relaxed cap allowed per ADR-010)."
    - "Boot rejection emits log line containing the literal string `LIVE_PREFLIGHT_REJECTED reason=cap_too_high` (the grep-gate target)."
    - "main.py imports `from app.preflight import run_all` (router-mount enables Plan 08-02's HTTP route at runtime)."
    - "Grep gate #1 fails the build if `LIVE_PREFLIGHT_REJECTED` literal is removed from `services/trading-engine/app/`."
    - "Grep gate #2 fails the build if `from app.preflight import` is removed from `services/trading-engine/app/main.py` (autoflake-survival regression guard)."
    - "Inline lifespan cap-check and `app.preflight.check_cap()` agree at the 0.02 boundary in both directions: 0.0200 → both PASS; 0.0201 → both FAIL. Asserted by `test_lifespan_and_check_cap_agree_at_boundary` so the two hard-coded 0.02 thresholds (inline at main.py per 08-CONTEXT.md decision; check_cap at app/preflight/checks.py per 08-01) cannot silently drift."
  artifacts:
    - path: "services/trading-engine/app/main.py"
      provides: "lifespan cap-check block (lines ~259-275) + router-mount + autoflake-survival import"
      contains: "LIVE_PREFLIGHT_REJECTED"
    - path: "services/trading-engine/tests/test_preflight_lifespan.py"
      provides: "source-level + runtime test that LIVE+0.03 raises RuntimeError + boundary-agreement test between inline lifespan check and check_cap()"
      contains: "test_lifespan_rejects_live_with_high_cap, test_lifespan_and_check_cap_agree_at_boundary"
    - path: "tests/integration/test_preflight_grep_gates.py"
      provides: "2 grep gates — log emission existence + import survival"
      contains: "test_live_preflight_rejected_log_exists"
  key_links:
    - from: "services/trading-engine/app/main.py"
      to: "services/trading-engine/app/preflight"
      via: "import + router include"
      pattern: "from app\\.preflight import run_all"
    - from: "services/trading-engine/app/main.py"
      to: "services/trading-engine/app/handlers/preflight.py"
      via: "app.include_router(preflight_router)"
      pattern: "from app\\.handlers\\.preflight import router"
    - from: "tests/integration/test_preflight_grep_gates.py"
      to: "services/trading-engine/app/"
      via: "pathlib + subprocess grep scan"
      pattern: "LIVE_PREFLIGHT_REJECTED"
    - from: "services/trading-engine/tests/test_preflight_lifespan.py::test_lifespan_and_check_cap_agree_at_boundary"
      to: "services/trading-engine/app/main.py + services/trading-engine/app/preflight/checks.py"
      via: "drift-detection — same Settings instance drives both paths, results must agree"
      pattern: "test_lifespan_and_check_cap_agree_at_boundary"
---

<objective>
Wire the boot-time cap-check enforcement into trading-engine lifespan AND mount the preflight router AND add the autoflake-survival import. All three edits are co-located in `services/trading-engine/app/main.py` to keep the grep-gate scope single-file. Plus the two CI grep gates that ensure neither the log emission nor the import can be silently removed by autoflake / future refactor.

Purpose: defence-in-depth. The cap-check is the most operator-visible LIVE gate; the grep gates are the regression detector that catches a future commit accidentally weakening it.

**Drift-detection note (locked by 08-CONTEXT.md):** The 2% threshold is hard-coded in two places by design — inline at `main.py` for lifespan locality (per 08-CONTEXT.md lines 36-53 "Per-trade cap enforcement point" decision) AND inside `check_cap()` at `app/preflight/checks.py` (per 08-01 to keep CLI/HTTP using the same logic). This is NOT a duplication bug to refactor away; the inline form is required so the boot-time enforcement is co-located with the existing `LIVE_TRADING_ACK` gate. To prevent silent drift between the two thresholds, Task 2 includes a boundary-agreement test `test_lifespan_and_check_cap_agree_at_boundary` (added during checker revision for W2).

Output:
- `services/trading-engine/app/main.py` — 3 small edits (cap-check block, router mount, F401 import)
- `services/trading-engine/tests/test_preflight_lifespan.py` — 5 tests (source-inspection + 3 runtime + boundary-agreement)
- `tests/integration/test_preflight_grep_gates.py` — 2 grep-gate tests

This plan addresses PREFLIGHT-02 in full and Phase 8 success criteria #3 + #6.
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
@.planning/phases/08-pre-live-preflight/08-01-SUMMARY.md
@.planning/phases/08-pre-live-preflight/08-02-SUMMARY.md

<!-- Existing files (target + analogs) -->
@services/trading-engine/app/main.py
@services/trading-engine/app/config.py
@services/trading-engine/tests/test_lifespan.py
@services/tournament-harness/tests/integration/test_tourn07_grep_gate.py
@services/trading-engine/app/handlers/preflight.py

<interfaces>
<!-- Existing main.py lifespan (lines 235-258) — extend in place. -->

```python
# Existing block (DO NOT REMOVE) at services/trading-engine/app/main.py:250-258
if settings.trading_mode == "LIVE":
    ack = os.environ.get("LIVE_TRADING_ACK", "")
    if ack != "I_UNDERSTAND_REAL_MONEY":
        raise RuntimeError(
            "Refusing to boot: TRADING_MODE=LIVE without "
            "LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY. ..."
        )
    logger.critical("LIVE trading mode acknowledged via LIVE_TRADING_ACK")
    # >>> NEW Phase 8 block goes HERE (line 259) <<<
```

The new Phase 8 block (per 08-PATTERNS.md lines 786-802):
```python
        if settings.max_risk_per_trade > 0.02:
            logger.critical(
                "LIVE_PREFLIGHT_REJECTED reason=cap_too_high "
                f"cap={settings.max_risk_per_trade} limit=0.02"
            )
            raise RuntimeError(
                f"Refusing to boot: TRADING_MODE=LIVE with "
                f"max_risk_per_trade={settings.max_risk_per_trade} > 0.02. "
                "Restore the LIVE-strict cap before flipping the mode."
            )
        logger.info(
            f"LIVE preflight cap check passed: max_risk_per_trade="
            f"{settings.max_risk_per_trade} <= 0.02"
        )
```

`check_cap()` shape (from Plan 08-01 Task 2, in `services/trading-engine/app/preflight/checks.py`):
```python
def check_cap(settings: Settings | None = None) -> CheckResult:
    # PAPER → PASS (any cap).
    # LIVE + cap > 0.02 → FAIL (detail contains cap and 0.02).
    # LIVE + cap <= 0.02 → PASS.
```

Both forms test the SAME predicate: `settings.max_risk_per_trade > 0.02` in LIVE. The boundary test in Task 2 drives both paths with the same `Settings(...)` and asserts they agree.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Insert cap-check block into trading-engine lifespan + mount router + add F401 import</name>
  <files>services/trading-engine/app/main.py</files>
  <read_first>
    - services/trading-engine/app/main.py (lines 235-258 — existing LIVE_TRADING_ACK block; lines 145-160 — existing imports; line ~447 — last `app.include_router` call; lines 282-283 — `.is_file()` pattern reference)
    - services/trading-engine/app/config.py (line ~321 — `max_risk_per_trade` field)
    - .planning/phases/08-pre-live-preflight/08-PATTERNS.md (lines 769-820 — exact insertion-point + copy-ready code; "Autoflake-survival local imports" shared pattern)
    - .planning/phases/08-pre-live-preflight/08-CONTEXT.md (lines 36-53 — locked enforcement-point decision)
    - Project memory `feedback_main_imports_autoflake.md` — autoflake strips test-patched imports; re-add with `# noqa: F401`. **This is load-bearing for grep gate #2.**
  </read_first>
  <behavior>
    - After this task: trading-engine running with `TRADING_MODE=LIVE`, `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`, and `MAX_RISK_PER_TRADE=0.03` raises `RuntimeError` from lifespan (logs `LIVE_PREFLIGHT_REJECTED reason=cap_too_high cap=0.03 limit=0.02` at CRITICAL).
    - LIVE + 0.02 cap: lifespan emits info log `LIVE preflight cap check passed: max_risk_per_trade=0.02 <= 0.02` and proceeds.
    - PAPER + 0.10 cap: the new block is skipped (it's inside the `if settings.trading_mode == "LIVE":` branch); existing PAPER-mode boot path unchanged.
    - `app.include_router(preflight_router)` mounts the route added in 08-02; `GET /api/preflight/live-readiness` is reachable on port 8005.
    - `from app.preflight import run_all  # noqa: F401` survives `make format` (autoflake will not strip).
  </behavior>
  <action>
    1. **Insert cap-check block** at line 259 (immediately after `logger.critical("LIVE trading mode acknowledged via LIVE_TRADING_ACK")` at the end of the existing LIVE_TRADING_ACK block). The new block is INSIDE the existing `if settings.trading_mode == "LIVE":` branch (so PAPER skips it entirely per ADR-010). Copy verbatim from 08-PATTERNS.md lines 787-802:
       ```python
       # Phase 8 PREFLIGHT-02 — LIVE-strict per-trade cap gate.
       # PAPER skips this entirely (ADR-010 paper-relaxed 10%). LIVE-only.
       if settings.max_risk_per_trade > 0.02:
           logger.critical(
               "LIVE_PREFLIGHT_REJECTED reason=cap_too_high "
               f"cap={settings.max_risk_per_trade} limit=0.02"
           )
           raise RuntimeError(
               f"Refusing to boot: TRADING_MODE=LIVE with "
               f"max_risk_per_trade={settings.max_risk_per_trade} > 0.02. "
               "Restore the LIVE-strict cap before flipping the mode."
           )
       logger.info(
           f"LIVE preflight cap check passed: max_risk_per_trade="
           f"{settings.max_risk_per_trade} <= 0.02"
       )
       ```
       The literal `"LIVE_PREFLIGHT_REJECTED"` substring MUST appear in the source — it is the grep-gate target. Do NOT split the string with concatenation; the substring must be searchable verbatim.

    2. **Add autoflake-survival import** near the top of main.py (after existing imports around line 145-160). Use the F401 marker exactly as 08-PATTERNS.md line 817 specifies:
       ```python
       # Phase 8 PREFLIGHT-02 import-survival — grep gate #2 asserts this stays.
       # Without F401, autoflake strips it on next `make format` and the gate fails.
       from app.preflight import run_all  # noqa: F401
       ```
       This import is currently NOT USED in main.py body (the cap-check uses `settings.max_risk_per_trade` directly, not the preflight module). The F401 marker is intentional and load-bearing per project memory.

    3. **Mount the router** at line ~447 (immediately after the last existing `app.include_router(...)` call). Per 08-PATTERNS.md lines 808-810:
       ```python
       # Phase 8 PREFLIGHT-01 — unauthenticated read-only preflight route (D-09 pattern).
       from app.handlers.preflight import router as preflight_router  # noqa: E402
       app.include_router(preflight_router)
       ```

    4. Verify both grep-gate targets visually:
       - `LIVE_PREFLIGHT_REJECTED` appears verbatim in main.py (no concatenation, no f-string split).
       - `from app.preflight import` appears verbatim in main.py.
  </action>
  <verify>
    <automated>cd services/trading-engine &amp;&amp; python -c "import inspect, app.main; src = inspect.getsource(app.main); assert 'LIVE_PREFLIGHT_REJECTED' in src, 'log literal missing'; assert 'from app.preflight import' in src, 'preflight import missing'; assert 'app.include_router(preflight_router)' in src or 'include_router(preflight_router)' in src, 'router mount missing'; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - Source assertion: `grep -c "LIVE_PREFLIGHT_REJECTED" services/trading-engine/app/main.py` returns ≥1.
    - Source assertion: `grep -c "reason=cap_too_high" services/trading-engine/app/main.py` returns ≥1.
    - Source assertion: `grep -c "from app.preflight import" services/trading-engine/app/main.py` returns ≥1.
    - Source assertion: `grep -c "noqa: F401" services/trading-engine/app/main.py` returns ≥1 (the autoflake-survival marker on the preflight import — likely already present for other imports too, but ≥1 is sufficient).
    - Source assertion: `grep -c "preflight_router" services/trading-engine/app/main.py` returns ≥1.
    - Source assertion (negative — paper not regressed): `grep -B5 "max_risk_per_trade > 0.02" services/trading-engine/app/main.py | grep -c 'trading_mode == "LIVE"'` returns ≥1 (cap-check is INSIDE the LIVE branch, not at module top-level).
    - Behavior assertion: the python one-liner in `<verify>` exits 0 and prints `OK`.
  </acceptance_criteria>
  <done>main.py has 3 edits — cap-check block (with LIVE_PREFLIGHT_REJECTED literal), autoflake-survival F401 import, router mount. Module still imports cleanly. PAPER mode boot path unchanged.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Lifespan integration tests (source-inspection + runtime rejection + boundary-agreement)</name>
  <files>services/trading-engine/tests/test_preflight_lifespan.py</files>
  <read_first>
    - services/trading-engine/tests/test_lifespan.py (lines 13-76 — pytest.asyncio + inspect.getsource pattern; specifically lines 64-76 test_lifespan_body_uses_async_with_phases as the source-inspection analog)
    - services/trading-engine/app/preflight/checks.py (from 08-01 — `check_cap(settings) -> CheckResult` signature; used by boundary-agreement test)
    - .planning/phases/08-pre-live-preflight/08-PATTERNS.md (lines 598-641 — copy-ready test pattern)
    - .planning/phases/08-pre-live-preflight/08-CONTEXT.md (lines 36-53 — locked decision: inline cap-check stays at main.py:259, NOT extracted; boundary test is the drift detector)
  </read_first>
  <behavior>
    - test_lifespan_source_contains_cap_check: `inspect.getsource(main.lifespan)` contains the three load-bearing substrings: `"LIVE_PREFLIGHT_REJECTED"`, `"max_risk_per_trade"`, `"0.02"`. This catches a future refactor accidentally moving the check OUT of the lifespan body (the function's source no longer contains it).
    - test_lifespan_rejects_live_with_high_cap (`@pytest.mark.asyncio`): monkeypatch.setenv TRADING_MODE=LIVE, MAX_RISK_PER_TRADE=0.03, LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY; force reload settings; entering `async with lifespan(fake_app):` raises `RuntimeError` whose message matches regex `r"max_risk_per_trade.*0.03.*0.02"`.
    - test_lifespan_accepts_live_with_strict_cap (`@pytest.mark.asyncio`): same env but MAX_RISK_PER_TRADE=0.02 — `async with lifespan(fake_app):` does NOT raise for the cap check (may raise downstream for missing DB/services in a test app, but should pass the cap gate; assert by capturing logs and checking the `"LIVE preflight cap check passed"` line is emitted).
    - test_lifespan_paper_mode_skips_cap_check (`@pytest.mark.asyncio`): TRADING_MODE=PAPER (or default), MAX_RISK_PER_TRADE=0.10 — no LIVE_PREFLIGHT_REJECTED log emitted, lifespan reaches phase init.
    - **test_lifespan_and_check_cap_agree_at_boundary** (`@pytest.mark.asyncio`, drift detector — addresses checker W2):
      Two-case parametrised test asserting the inline lifespan cap-check and `app.preflight.check_cap()` agree at the 0.02 boundary for the same Settings input.

      Case A — boundary exact (0.0200):
      - Drive lifespan with `Settings(trading_mode="LIVE", max_risk_per_trade=0.0200)` + `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`.
      - Assert: `async with lifespan(fake_app):` does NOT raise `RuntimeError` (cap exactly at limit; `0.0200 > 0.02` is False).
      - Assert: `check_cap(Settings(trading_mode="LIVE", max_risk_per_trade=0.0200)).status == "PASS"`.
      - Both paths agree: PASS.

      Case B — boundary +epsilon (0.0201):
      - Drive lifespan with `Settings(trading_mode="LIVE", max_risk_per_trade=0.0201)` + `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`.
      - Assert: `async with lifespan(fake_app):` raises `RuntimeError` matching `r"max_risk_per_trade.*0.0201.*0.02"`.
      - Assert: `check_cap(Settings(trading_mode="LIVE", max_risk_per_trade=0.0201))` returns `CheckResult(status="FAIL", ...)` whose `detail` contains `"0.0201"` and `"0.02"`.
      - Both paths agree: FAIL.

      Rationale: the 2% threshold is hard-coded in two places by 08-CONTEXT.md locked decision (inline at main.py for lifespan locality; `check_cap` for CLI/HTTP). This test fails the build if either threshold drifts to 0.025, 0.03, or is moved to a config field without updating the other path.
  </behavior>
  <action>
    1. Create `services/trading-engine/tests/test_preflight_lifespan.py` per 08-PATTERNS.md lines 604-641. Imports: `os`, `inspect`, `pytest`, plus `from app.preflight.checks import check_cap` and `from app.config import Settings` for the boundary-agreement test.

    2. Implement `test_lifespan_source_contains_cap_check` per 08-PATTERNS.md lines 611-621. Use `inspect.getsource(main_mod.lifespan)` and assert all three substrings present.

    3. Implement `test_lifespan_rejects_live_with_high_cap` per 08-PATTERNS.md lines 624-641. Use monkeypatch.setenv for TRADING_MODE/MAX_RISK_PER_TRADE/LIVE_TRADING_ACK; force settings reload (`from app.config import reload_settings; reload_settings()` or equivalent — check config.py for the exact helper name in the codebase; if absent, instantiate `Settings()` afresh inside the test and monkeypatch the module-level `settings` reference).

    4. Add `test_lifespan_accepts_live_with_strict_cap` — same env-setup but cap=0.02. Use `caplog` fixture to capture log records; after entering `async with lifespan(fake_app):` (may need to mock DB init phases — see test_lifespan.py for analog of mocking `init_data, init_ml, ...`), assert no `LIVE_PREFLIGHT_REJECTED` in caplog.text AND `LIVE preflight cap check passed` is present.

    5. Add `test_lifespan_paper_mode_skips_cap_check` — TRADING_MODE=PAPER, MAX_RISK_PER_TRADE=0.10. Assert no `LIVE_PREFLIGHT_REJECTED` in caplog.text AND no `LIVE preflight cap check passed` (because PAPER skips the check entirely — the `if settings.trading_mode == "LIVE":` branch is not entered).

    6. **Add `test_lifespan_and_check_cap_agree_at_boundary` (NEW — addresses checker W2):**

       Implement as a parametrised test driving both paths with each of the two boundary values. Skeleton:

       ```python
       import pytest
       from app.preflight.checks import check_cap
       from app.config import Settings

       @pytest.mark.asyncio
       @pytest.mark.parametrize(
           "cap, expect_lifespan_raises, expect_check_cap_status",
           [
               # Case A — 0.0200 exactly at limit: both PASS.
               (0.0200, False, "PASS"),
               # Case B — 0.0201 just above limit: both FAIL (lifespan raises; check_cap FAIL).
               (0.0201, True, "FAIL"),
           ],
           ids=["boundary_exact_0.0200", "boundary_plus_epsilon_0.0201"],
       )
       async def test_lifespan_and_check_cap_agree_at_boundary(
           cap, expect_lifespan_raises, expect_check_cap_status, monkeypatch, caplog
       ):
           # Set env so both paths see the same trading mode + ack.
           monkeypatch.setenv("TRADING_MODE", "LIVE")
           monkeypatch.setenv("MAX_RISK_PER_TRADE", str(cap))
           monkeypatch.setenv("LIVE_TRADING_ACK", "I_UNDERSTAND_REAL_MONEY")
           # Mock downstream phase managers (DB / ML / strategy / risk init) per
           # test_lifespan.py analog so the test isolates the cap-check branch.
           # ... (see test_lifespan.py for the AsyncContextManagerMock pattern)

           # Reload settings to pick up the patched env (use whichever helper
           # config.py exposes — `reload_settings()` if present, else patch the
           # module-level `settings` reference with a fresh `Settings()`).
           settings = Settings(trading_mode="LIVE", max_risk_per_trade=cap)

           # --- Path 1: inline lifespan check ---
           import app.main as main_mod
           # Patch the module-level settings the lifespan reads, mirroring tests 2-4.
           monkeypatch.setattr(main_mod, "settings", settings, raising=False)
           if expect_lifespan_raises:
               with pytest.raises(RuntimeError, match=rf"max_risk_per_trade.*{cap}.*0\.02"):
                   async with main_mod.lifespan(_fake_app_for_lifespan()):
                       pass
           else:
               # Cap exactly at limit — lifespan must NOT raise for the cap check.
               # (Downstream phases mocked above; if they raise, the test catches
               # the wrong failure and reports the cap branch as buggy.)
               async with main_mod.lifespan(_fake_app_for_lifespan()):
                   pass
               assert "LIVE preflight cap check passed" in caplog.text

           # --- Path 2: check_cap() from app.preflight ---
           result = check_cap(settings)
           assert result.status == expect_check_cap_status, (
               f"check_cap disagrees with lifespan at cap={cap}: "
               f"lifespan_raises={expect_lifespan_raises}, "
               f"check_cap.status={result.status} (expected {expect_check_cap_status})"
           )

           # --- Cross-agreement assertion: both paths must produce the same verdict ---
           lifespan_verdict = "FAIL" if expect_lifespan_raises else "PASS"
           assert result.status == lifespan_verdict, (
               f"DRIFT DETECTED at cap={cap}: lifespan says {lifespan_verdict} "
               f"but check_cap says {result.status}. The two hard-coded 0.02 "
               f"thresholds (main.py inline + app/preflight/checks.py check_cap) "
               f"have diverged. Fix both to match — they are intentional duplicates "
               f"per 08-CONTEXT.md locked decision."
           )

           # For the FAIL case, also assert the detail strings contain both values
           # (matching test_check_cap_live_rejects_3pct's contract in 08-01).
           if expect_check_cap_status == "FAIL":
               assert str(cap) in result.detail and "0.02" in result.detail
       ```

       Notes:
       - Use the same `_fake_app_for_lifespan()` / `AsyncContextManagerMock` pattern as the other 4 tests in this file. Do NOT create a new fixture — extend the existing mocking.
       - The test placement is INSIDE `services/trading-engine/tests/test_preflight_lifespan.py` (the file created in steps 1-5 above), NOT a new file. This is per the checker's W2 fix-text: "extend, do not create new file."
       - Float-equality care: `0.0200 > 0.02` evaluates to False in Python (`0.02 == 0.0200` is True; both are the same `float`). `0.0201 > 0.02` evaluates to True. These are the precise comparisons the inline `if settings.max_risk_per_trade > 0.02:` check uses; the test exercises them directly.

    7. Mocking note: if the lifespan body's downstream phase managers (init_data, init_ml, init_strategy, init_risk) fail in a test app due to missing DBs/services, mock them via `monkeypatch.setattr("app.main.init_data", lambda: AsyncContextManagerMock())` etc. Pattern from test_lifespan.py. This applies to ALL tests in this file (3, 4, 5, and the new boundary test).
  </action>
  <verify>
    <automated>cd services/trading-engine &amp;&amp; pytest tests/test_preflight_lifespan.py -v --tb=short</automated>
  </verify>
  <acceptance_criteria>
    - Source assertion: `grep -c "test_lifespan_source_contains_cap_check" services/trading-engine/tests/test_preflight_lifespan.py` returns 1.
    - Source assertion: `grep -c "test_lifespan_rejects_live_with_high_cap" services/trading-engine/tests/test_preflight_lifespan.py` returns 1.
    - Source assertion: `grep -c "test_lifespan_paper_mode_skips_cap_check" services/trading-engine/tests/test_preflight_lifespan.py` returns 1.
    - Source assertion: `grep -c "0.03" services/trading-engine/tests/test_preflight_lifespan.py` returns ≥1 (the FAIL-direction test uses 0.03 literal).
    - **Source assertion (addresses checker W2): `grep -c "test_lifespan_and_check_cap_agree_at_boundary" services/trading-engine/tests/test_preflight_lifespan.py` returns 1.**
    - **Source assertion (boundary values present): `grep -c "0.0200" services/trading-engine/tests/test_preflight_lifespan.py` returns ≥1 AND `grep -c "0.0201" services/trading-engine/tests/test_preflight_lifespan.py` returns ≥1.**
    - **Source assertion (boundary test imports check_cap from preflight, so it actually exercises both paths): `grep -c "from app.preflight" services/trading-engine/tests/test_preflight_lifespan.py` returns ≥1 AND `grep -c "check_cap" services/trading-engine/tests/test_preflight_lifespan.py` returns ≥1.**
    - **Source assertion (drift-detection assertion message present, for grep-gate-style regression catch): `grep -c "DRIFT DETECTED" services/trading-engine/tests/test_preflight_lifespan.py` returns ≥1.**
    - Behavior assertion: `pytest services/trading-engine/tests/test_preflight_lifespan.py -v` exits 0; ≥5 test cases pass (4 base tests + the boundary test, which is parametrised across 2 cases = 6 collected test cases total; the parametrised test counts as one `def` but two pytest invocations).
    - Behavior assertion: the rejection test (`test_lifespan_rejects_live_with_high_cap`) specifically demonstrates `RuntimeError` is raised — captured by `pytest.raises(RuntimeError, match="max_risk_per_trade.*0.03.*0.02")`.
    - Behavior assertion (boundary test specific): `pytest services/trading-engine/tests/test_preflight_lifespan.py::test_lifespan_and_check_cap_agree_at_boundary -v` shows 2 cases pass — `boundary_exact_0.0200` and `boundary_plus_epsilon_0.0201`.
  </acceptance_criteria>
  <done>≥5 lifespan tests pass (= 4 def + 1 parametrised def with 2 cases = 6 pytest invocations) — source-inspection guard against refactor-out, runtime rejection at LIVE+0.03, runtime acceptance at LIVE+0.02, runtime PAPER+0.10 skip, AND boundary-agreement between inline lifespan check and check_cap() at 0.0200 (both PASS) and 0.0201 (both FAIL). The two hard-coded 0.02 thresholds cannot silently drift.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Two CI grep gates — log emission + import survival</name>
  <files>tests/integration/test_preflight_grep_gates.py</files>
  <read_first>
    - services/tournament-harness/tests/integration/test_tourn07_grep_gate.py (lines 1-65 — subprocess grep pattern; pathlib scan fallback)
    - services/trading-engine/tests/test_lifespan.py (lines 64-76 — inspect.getsource(main_mod) source-survival pattern)
    - .planning/phases/08-pre-live-preflight/08-PATTERNS.md (lines 438-509 — both grep gates copy-ready, plus the "scope-to-TE_APP" warning per advisor note)
    - Advisor note on this plan: grep gate #1 MUST scope to `services/trading-engine/app/` ONLY — never the repo root. Otherwise RUNBOOK.md prose from 08-05 (which contains the LIVE_PREFLIGHT_REJECTED literal as documentation) would satisfy the gate even if the production code emission was deleted.
  </read_first>
  <behavior>
    - test_live_preflight_rejected_log_exists: pathlib-recursive scan of `services/trading-engine/app/` (excluding `tests/`) for `re.compile(r"LIVE_PREFLIGHT_REJECTED")` matches; assert ≥1 file matches. ALSO run `subprocess.run(["grep", "-r", "LIVE_PREFLIGHT_REJECTED", "services/trading-engine/app/"])` (scoped to app/, not repo root) — assert stdout non-empty. Both halves of the dual-form gate must pass.
    - test_preflight_module_imports_at_lifespan: `inspect.getsource(app.main)` contains either `"from app.preflight import"` OR `"import app.preflight"`. Catches autoflake stripping the F401-marked import.
  </behavior>
  <action>
    1. Create `tests/integration/test_preflight_grep_gates.py` per 08-PATTERNS.md lines 446-509.

    2. Module-level constants:
       ```python
       import re
       import subprocess
       import inspect
       from pathlib import Path

       REPO_ROOT = Path(__file__).resolve().parents[2]
       TE_APP = REPO_ROOT / "services" / "trading-engine" / "app"
       ```

    3. Implement `test_live_preflight_rejected_log_exists`:
       - Use `re.compile(r"LIVE_PREFLIGHT_REJECTED")` and iterate `TE_APP.rglob("*.py")`, skipping any path with `/tests/` in `as_posix()`. Collect matches. Assert non-empty with a clear failure message: `"LIVE_PREFLIGHT_REJECTED log emission removed from production code"`.
       - Then run `subprocess.run(["grep", "-r", "LIVE_PREFLIGHT_REJECTED", str(TE_APP)], capture_output=True, text=True)`. Assert `result.stdout` is non-empty. **Scope is TE_APP, NOT REPO_ROOT** — this is the load-bearing point advisor flagged. RUNBOOK.md prose containing the literal must NOT satisfy the gate.

    4. Implement `test_preflight_module_imports_at_lifespan` per 08-PATTERNS.md lines 490-506:
       ```python
       def test_preflight_module_imports_at_lifespan():
           import app.main as main_mod
           src = inspect.getsource(main_mod)
           assert (
               "from app.preflight import" in src
               or "import app.preflight" in src
           ), "main.py must import app.preflight for cap-check enforcement"
       ```

    5. Ensure the test file is discoverable by `pytest tests/integration/test_preflight_grep_gates.py` from repo root (no special pythonpath needed since `app.main` is imported via `services/trading-engine` package — the test runs in an env where trading-engine is importable; either add `conftest.py` adjustment or note in SUMMARY that the grep gate runs inside the trading-engine container in CI).

    6. Add docstring to the file noting both gates are CI-enforced regression detectors per 08-CONTEXT.md "Grep gates (defence-in-depth)" decision.
  </action>
  <verify>
    <automated>cd /mnt/d/Bimo_max/crypto-trading-bot &amp;&amp; pytest tests/integration/test_preflight_grep_gates.py -v --tb=short</automated>
  </verify>
  <acceptance_criteria>
    - Source assertion: `grep -c "test_live_preflight_rejected_log_exists" tests/integration/test_preflight_grep_gates.py` returns 1.
    - Source assertion: `grep -c "test_preflight_module_imports_at_lifespan" tests/integration/test_preflight_grep_gates.py` returns 1.
    - Source assertion: `grep -c "TE_APP" tests/integration/test_preflight_grep_gates.py` returns ≥3 (constant defined + used in both pathlib scan + subprocess scope).
    - Source assertion (scope-correctness, load-bearing per advisor): `grep -A30 "def test_live_preflight_rejected_log_exists" tests/integration/test_preflight_grep_gates.py | grep -c "REPO_ROOT"` returns 0 — the subprocess grep MUST NOT use REPO_ROOT (which would let RUNBOOK.md's prose satisfy it).
    - Behavior assertion: `pytest tests/integration/test_preflight_grep_gates.py -v` exits 0; 2 tests pass.
    - Failure-mode behavior assertion (record in SUMMARY, do NOT commit the test of this): if you temporarily comment out the `logger.critical("LIVE_PREFLIGHT_REJECTED ...")` line in main.py, `pytest tests/integration/test_preflight_grep_gates.py::test_live_preflight_rejected_log_exists` fails with the assertion-message about removed log emission. Then revert the comment. Document the manual verification in SUMMARY.
  </acceptance_criteria>
  <done>Both grep gates pass on current code; scope is `services/trading-engine/app/` only; manual failure-mode verification recorded in SUMMARY.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| operator env → trading-engine lifespan | env vars TRADING_MODE, MAX_RISK_PER_TRADE, LIVE_TRADING_ACK; same trust domain |
| source code → CI grep gates | static-scan boundary; gates fail if production source is mutated to remove enforcement |
| inline lifespan threshold ↔ check_cap() threshold | drift boundary — two hard-coded 0.02 literals must agree; locked decision per 08-CONTEXT.md keeps both; boundary-agreement test detects divergence |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-08-03-01 | T (Tampering) | silent removal of `LIVE_PREFLIGHT_REJECTED` log emission | mitigate | Grep gate #1 (`test_live_preflight_rejected_log_exists`) — dual-form scan (pathlib + subprocess grep) scoped to `services/trading-engine/app/` only. RUNBOOK.md prose containing the literal does NOT satisfy the gate. Failure-mode manually verified by commenting the log line. |
| T-08-03-02 | T (Tampering) | autoflake strips `from app.preflight import run_all` on `make format` | mitigate | F401 marker `# noqa: F401` on the import line; grep gate #2 (`test_preflight_module_imports_at_lifespan`) asserts the import survives. Project memory `feedback_main_imports_autoflake.md` documents this exact regression pattern. |
| T-08-03-03 | T (Tampering) | future refactor moves cap-check OUT of `lifespan()` body | mitigate | `test_lifespan_source_contains_cap_check` uses `inspect.getsource(main_mod.lifespan)` — if the check is relocated to a helper module, the lifespan source no longer contains the three load-bearing literals (`LIVE_PREFLIGHT_REJECTED`, `max_risk_per_trade`, `0.02`) and the test fails. Defence-in-depth layer 3. |
| T-08-03-04 | E (Elevation) | operator with shell access edits .env to MAX_RISK_PER_TRADE=10 in LIVE | mitigate | This is exactly what this phase blocks. Boot-time enforcement raises RuntimeError before any trading loop starts. Test `test_lifespan_rejects_live_with_high_cap` asserts this. |
| T-08-03-05 | I (Info disclosure) | RuntimeError messages include the cap value | accept | Cap values are not secrets; same disclosure level as the existing LIVE_TRADING_ACK error message (which already references the env-var name). |
| T-08-03-06 | D (DoS) | adversary forces LIVE+invalid-cap to crash the trading-engine container in a boot loop | accept | This IS the intended behavior — refuse to operate when misconfigured for LIVE. Docker-compose `restart: unless-stopped` will retry, but the boot will keep failing until the cap is fixed. Operator sees a crash-loop and the LIVE_PREFLIGHT_REJECTED log line — that is the desired outcome. |
| T-08-03-07 | T (Tampering) | inline lifespan 0.02 threshold drifts from `check_cap()` 0.02 threshold (e.g., a future commit relaxes inline to 0.025 to "fix a flaky test" while leaving CLI/HTTP strict) | mitigate | `test_lifespan_and_check_cap_agree_at_boundary` drives both paths with the same `Settings(...)` at 0.0200 and 0.0201 and asserts they agree. If either threshold changes, one of the two cases produces a different verdict and the test fails with a "DRIFT DETECTED" assertion message naming both files. 08-CONTEXT.md (lines 36-53) explicitly keeps the two thresholds as intentional duplicates rather than extracting a shared constant — the boundary test is the safety net for that decision. |
</threat_model>

<verification>
- `pytest services/trading-engine/tests/test_preflight_lifespan.py -v` — ≥5 test defs (= 6 pytest invocations counting the parametrised boundary test) pass.
- `pytest services/trading-engine/tests/test_preflight_lifespan.py::test_lifespan_and_check_cap_agree_at_boundary -v` — both parametrised cases pass: `boundary_exact_0.0200` and `boundary_plus_epsilon_0.0201`.
- `pytest tests/integration/test_preflight_grep_gates.py -v` — 2 tests pass.
- `grep -c "LIVE_PREFLIGHT_REJECTED" services/trading-engine/app/main.py` returns ≥1.
- `grep -c "from app.preflight import" services/trading-engine/app/main.py` returns ≥1.
- `grep -c "preflight_router" services/trading-engine/app/main.py` returns ≥1.
- `grep -c "test_lifespan_and_check_cap_agree_at_boundary" services/trading-engine/tests/test_preflight_lifespan.py` returns 1.
- `grep -c "0.0200" services/trading-engine/tests/test_preflight_lifespan.py` returns ≥1.
- `grep -c "0.0201" services/trading-engine/tests/test_preflight_lifespan.py` returns ≥1.
- Drift-detection manual verification (record in SUMMARY): temporarily change the inline lifespan threshold from `> 0.02` to `> 0.025` — `pytest ::test_lifespan_and_check_cap_agree_at_boundary[boundary_plus_epsilon_0.0201]` fails (lifespan no longer raises at 0.0201, but check_cap still says FAIL). Revert. Documents the drift-detection mechanism actually catches drift.
- Failure-mode (manual, record in SUMMARY): comment out the `logger.critical("LIVE_PREFLIGHT_REJECTED ...")` block → grep gate #1 fails. Revert.
- End-to-end smoke (post-Phase 8 integration, record in SUMMARY): `docker compose -f docker-compose.unified.yml up trading-engine` with `.env` set to `TRADING_MODE=LIVE`, `MAX_RISK_PER_TRADE=0.03`, `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` — container exits non-zero, `docker logs trading-engine | grep "LIVE_PREFLIGHT_REJECTED reason=cap_too_high"` returns the line. Per CLAUDE.md Verification standards (real proof requires service restart + log line in container logs after config change). **Revert .env afterwards** — leaving cap=0.03 in .env would block subsequent legitimate LIVE flips.
</verification>

<success_criteria>
- main.py contains the cap-check block, the F401 preflight import, and the router mount.
- 5 lifespan tests pass (= 6 pytest invocations): source-inspection, LIVE+0.03 rejection, LIVE+0.02 acceptance, PAPER skip, AND the boundary-agreement test at 0.0200 + 0.0201.
- 2 grep gates pass: log emission + import survival, scoped to `services/trading-engine/app/`.
- Boundary-agreement test (`test_lifespan_and_check_cap_agree_at_boundary`) asserts the inline lifespan check and `check_cap()` produce the same verdict for the same `Settings(...)` at 0.0200 (both PASS) and 0.0201 (both FAIL). Addresses checker W2 — drift detector for the two hard-coded 0.02 thresholds preserved by 08-CONTEXT.md locked decision.
- Failure-mode of grep gate #1 manually verified (comment-out test) and recorded in SUMMARY.
- Drift-detection mechanism of `test_lifespan_and_check_cap_agree_at_boundary` manually verified (temporarily change one threshold; test fails; revert) and recorded in SUMMARY.
- Container-restart smoke recorded in SUMMARY satisfying CLAUDE.md "Verification standards" (live log line visible after restart).
- PAPER mode boot path unchanged: existing paper-relaxed 10% cap continues to work per ADR-010.
</success_criteria>

<output>
After completion, create `.planning/phases/08-pre-live-preflight/08-03-SUMMARY.md` capturing:
- Diff summary for main.py (3 edits, ~25 added lines).
- Test counts (passed) for both lifespan tests and grep gates. Call out the boundary-agreement test explicitly: 2 parametrised cases (0.0200 PASS / 0.0201 FAIL), both asserting inline lifespan + check_cap agree.
- Manual failure-mode verification record for grep gate #1 (one-line: "verified by commenting log line, gate failed as expected; reverted").
- Manual drift-detection verification record for `test_lifespan_and_check_cap_agree_at_boundary` (one-line: "verified by changing inline threshold to 0.025; boundary_plus_epsilon_0.0201 case failed with DRIFT DETECTED message naming both main.py and checks.py; reverted").
- Container-restart smoke evidence per CLAUDE.md Verification standards: log line snippet showing `LIVE_PREFLIGHT_REJECTED reason=cap_too_high cap=0.03 limit=0.02` from a real `docker logs` call. **Note in SUMMARY: .env was reverted to pre-test state.**
- Forward-link: the CI workflow in 08-04 will invoke both `pytest services/trading-engine/tests/test_preflight_*` AND `pytest tests/integration/test_preflight_grep_gates.py`.
</output>
</content>
</invoke>