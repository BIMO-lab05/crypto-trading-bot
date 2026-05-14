---
phase: 02-integration-test-suite-runbook
reviewed: 2026-05-08T00:00:00Z
depth: standard
files_reviewed: 28
files_reviewed_list:
  - .env.test.example
  - .github/workflows/integration-ml-on.yml
  - .github/workflows/integration.yml
  - .gitignore
  - RUNBOOK.md
  - docker-compose.unified.yml
  - docs/operations/RUNBOOK.md
  - scripts/iter-fix-check-diff.sh
  - scripts/iter-fix.sh
  - services/bybit-connector/app/main.py
  - services/bybit-connector/app/tape_replay_client.py
  - services/bybit-connector/tests/test_main.py
  - services/bybit-connector/tests/test_tape_replay_client.py
  - services/ml-prediction-service/app/ml_models/gru_model.py
  - services/ml-prediction-service/app/ml_models/gru_predictor.py
  - services/ml-prediction-service/tests/test_model_reload.py
  - services/notification-service/app/config.py
  - services/notification-service/app/telegram_notifier.py
  - services/technical-analysis/app/handlers/analysis.py
  - services/technical-analysis/tests/test_signal_aggregator_confidence_zero.py
  - services/trading-engine/app/handlers/orchestration.py
  - services/trading-engine/app/main.py
  - services/trading-engine/tests/test_force_signal.py
  - tests/integration/conftest.py
  - tests/integration/test_fresh_clone_round_trip.py
  - tests/integration/test_ml_on_variant.py
  - tests/integration/test_notification_delivery.py
  - tests/integration/test_pre_existing_bug_regressions.py
  - tests/scripts/test_iter_fix.sh
findings:
  blocker: 4
  warning: 9
  total: 13
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-05-08
**Depth:** standard
**Files Reviewed:** 28 (note: `.env.test.example` blocked by sandbox permissions; the regression test in `tests/integration/test_notification_delivery.py:45-56` validates the file's safety contract — its content is therefore covered indirectly)
**Status:** issues_found

## Summary

The Phase 2 integration test suite, runbook, and CI plumbing are mostly correctly wired, but there are four hard wiring bugs that will cause the suite to fail at boot or fixture-setup time, plus a CORS spec violation that should not ship. The two highest-impact defects are: (1) the integration test calls a Bybit endpoint URL that does not exist (route is `/api/v1/market/ticker` singular; tests call `/tickers` plural — the headline `test_fresh_clone_round_trip` cannot pass), and (2) `bootstrap.sh` does not pass `--profile ml --profile analytics`, but the `bootstrap_stack` fixture and the script's own `[5/6]` health probe both demand `ml-prediction:8007` and `sentiment:8008` to return 200 — those services are profile-gated in compose and never start, so bootstrap exits 1 and every integration test fails at fixture setup. Add to that an env-var name mismatch (`TEST_TELEGRAM_*` vs `TELEGRAM_TEST_*`) that prevents CI's Telegram secrets from ever reaching the container in `live` notification mode, and the suite has no green path on first run. Several smaller defects (anti-mock guard one-sided regex, debug log spam in production, `notification_test_mode` host/container default mismatch, EMERGENCY_STOP/auto-trader coupling) are also flagged.

## Blocker Issues

### BL-01: Integration test calls a non-existent Bybit endpoint — headline test cannot pass

**File:** `tests/integration/test_fresh_clone_round_trip.py:44, 141`
**Issue:** The test builds the URL `f"{services_config['bybit_connector']}/api/v1/market/tickers"` (plural). The bybit-connector route declared at `services/bybit-connector/app/main.py:741` is `@app.get("/api/v1/market/ticker", ...)` (singular). FastAPI returns 404 for the plural form. The first assertion at line 48 (`assert r.status_code == 200`) will fail, so the headline `test_fresh_clone_round_trip` ROADMAP success-criterion test never reaches the round-trip step. The `test_unknown_symbol_does_not_500` test at line 141 has the same bug.
**Fix:**
```python
# tests/integration/test_fresh_clone_round_trip.py
# Line 44
tickers_url = f"{services_config['bybit_connector']}/api/v1/market/ticker"
# Line 141
url = f"{services_config['bybit_connector']}/api/v1/market/ticker"
```

### BL-02: bootstrap.sh and integration suite require profile-gated services that bootstrap never starts

**File:** `bootstrap.sh:78-79`, `tests/integration/conftest.py:40-41,116-128`, `docker-compose.unified.yml:710-711,757-758`
**Issue:** `bootstrap.sh:64-79` enumerates 10 services in `SERVICES` (including `ml-prediction:8007` and `sentiment:8008`), and `[5/6]` will mark them UNHEALTHY because `docker compose -f $COMPOSE_FILE up -d` (line 65/67) is invoked WITHOUT `--profile ml --profile analytics`. In `docker-compose.unified.yml`, `ml-prediction` is declared with `profiles: [ml]` (line 710-711) and `sentiment-analysis` with `profiles: [analytics]` (line 757-758) — they will never be started by the default `compose up`. Bootstrap then exits 1 (line 130), the CI workflow's `bash bootstrap.sh` step fails, and pytest never runs. Even if pytest did run, the `bootstrap_stack` fixture in conftest.py:116-128 iterates `services_config` (which includes those two URLs from lines 40-41) and `pytest.fail`s on any non-200. The standalone test `test_pre_existing_bug_regressions.py:139-180` shows the maintainers were aware of profile-gating for `ml-prediction` (it shells out `docker compose --profile ml up -d ml-prediction` at line 152-167), but the same fix was never applied at the bootstrap layer.
**Fix:** Choose one of:
```bash
# Option A: bootstrap.sh — bring profile-gated services up alongside the rest
docker compose -f "$COMPOSE_FILE" --profile ml --profile analytics up -d
# (or only --profile ml if the integration suite tolerates sentiment being absent)
```
or
```python
# Option B: conftest.py — drop ml_prediction + sentiment from default services_config
# and gate them behind explicit @pytest.mark.ml_on / @pytest.mark.sentiment_on markers.
# This is what test_ml_on_variant.py already does conceptually — extend the same
# pattern to bootstrap.sh's health probe (skip those two services unless the
# corresponding profile flag was passed).
```
The integration-ml-on workflow (`integration-ml-on.yml:42-44`) calls plain `bash bootstrap.sh` and would need the same fix even though `ENABLE_ML_PREDICTIONS=true` is set in env — env flags do NOT activate compose profiles.

### BL-03: CI Telegram secrets never reach the notification container — env var name mismatch

**File:** `.github/workflows/integration.yml:43-44,53-54`, `.github/workflows/integration-ml-on.yml:40-41`, `docker-compose.unified.yml:641-642`, `tests/integration/conftest.py:250`
**Issue:** GitHub workflows export `TEST_TELEGRAM_BOT_TOKEN` and `TEST_TELEGRAM_CHAT_ID` (T-E-S-T prefix). Compose at lines 641-642 reads `${TELEGRAM_TEST_BOT_TOKEN:-}` and `${TELEGRAM_TEST_CHAT_ID:-}` (T-E-L-E-G-R-A-M prefix — opposite word order). The host shell exports are not what compose looks up, so both env vars expand to the empty default and never reach the notification-service container. With `NOTIFICATION_TEST_MODE=live` and empty creds, the telegram_notifier path at `services/notification-service/app/telegram_notifier.py:60-66` returns False ("Telegram bot token or chat ID not configured"), no message is sent, and the host conftest fixture's getUpdates polling at `tests/integration/conftest.py:256-269` returns False. `test_notification_delivery_via_trade_endpoint` and `test_fresh_clone_round_trip` both fail. Note conftest.py:250 reads `TEST_TELEGRAM_BOT_TOKEN` (matching the workflow), so the host side is fine — the bug is purely in the host→container translation.
**Fix:**
```yaml
# docker-compose.unified.yml — lines 641-642 (align names with the workflow / conftest)
- TEST_TELEGRAM_BOT_TOKEN=${TEST_TELEGRAM_BOT_TOKEN:-}
- TEST_TELEGRAM_CHAT_ID=${TEST_TELEGRAM_CHAT_ID:-}
```
Then verify `services/notification-service/app/config.py` reads the same names; the field names in config.py are not in scope for this review but a one-line `Field(alias=...)` may also be needed.

### BL-04: bybit-connector CORS — `allow_origins=["*"]` with `allow_credentials=True` is spec-violating and overrides the strict pattern used elsewhere

**File:** `services/bybit-connector/app/main.py:427-438`
**Issue:** The CORS middleware is configured with `allow_origins=["*"]` AND `allow_credentials=True`. The CORS spec (and Starlette's middleware) forbids this combination — modern browsers refuse to send credentials when `Access-Control-Allow-Origin: *` is returned. Starlette will silently echo the request Origin back when both flags are set, which negates the security intent of CORS entirely (any site can issue credentialed requests). The trading-engine got this right at `services/trading-engine/app/main.py:383-402` using `settings.all_cors_origins` (configured allowlist). The bybit-connector is the inconsistency; the comment on line 429 ("Allow all origins for dashboard access") suggests the author wanted `allow_origins=settings.all_cors_origins` but pasted a wildcard. This is a credential-leak surface: if the connector ever holds a session cookie or auth header, any site can probe it from a browser context.
**Fix:**
```python
# services/bybit-connector/app/main.py — replace lines 427-438
settings_instance = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings_instance.all_cors_origins,  # never "*" with credentials
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "Origin"],
)
```
If `all_cors_origins` doesn't yet exist on the bybit-connector Settings, copy the trading-engine pattern (see `services/trading-engine/app/config.py` for `all_cors_origins`). If the dashboard truly must work from any origin, set `allow_credentials=False` instead — but never both `*` + `True`.

## Warnings

### WR-01: `iter-fix-check-diff.sh` threshold-lowering regex is one-sided — Goodhart move on `>` thresholds slips through

**File:** `scripts/iter-fix-check-diff.sh:57`
**Issue:** `THRESHOLD_RE='assert.*<=?[[:space:]]*([0-9]+(\.[0-9]+)?)'` matches only `<` and `<=`. A real Goodhart pattern on quality gates uses `>` / `>=` — e.g., a test that asserted `assert win_rate > 0.5` and was relaxed to `assert win_rate > 0.3` is undetectable by this guard. The integration suite already has `>` assertions at `test_fresh_clone_round_trip.py:100` (`assert elapsed < 60.0`, this one is the right direction) and `test_force_signal.py:127` (`status_code == 200`). Future contributors lowering a `>` minimum threshold is the exact regression D-12 was meant to prevent.
**Fix:**
```bash
# scripts/iter-fix-check-diff.sh — extend regex + add inverse comparison branch
THRESHOLD_RE='assert.*[<>]=?[[:space:]]*([0-9]+(\.[0-9]+)?)'
# In the `+` branch where new_num/old_num are compared, branch on whether
# the operator was `<`/`<=` (raise = relax) or `>`/`>=` (lower = relax).
# An `assert x < N` lowered to `< M` where M > N is a relax. An
# `assert x > N` lowered to `> M` where M < N is also a relax.
```
Add a test case in `tests/scripts/test_iter_fix.sh` that exercises `>` lowering.

### WR-02: telegram_notifier.py — `[DEBUGGER:...]` print-style logger calls left in production code

**File:** `services/notification-service/app/telegram_notifier.py:27, 48, 55, 63, 101, 108, 115, 123`
**Issue:** Eight `logger.info`/`logger.warning`/`logger.error` calls embed `[DEBUGGER:TelegramNotifier:...]` prefixes with method names, line numbers, internal flags. They are debug scaffolding from a triage session that was never cleaned up. Not actively secret-leaking (they print `bool(self.bot_token)` and `chat_id` only — and chat_id is a logical identifier, not a secret), but they are noise in CI logs, raise eyebrows in code review, and the line numbers in the strings (e.g. "send_message:42") are stale relative to the actual line numbers in the file. Project convention per CLAUDE.md is structured JSON logging without ad-hoc print scaffolding.
**Fix:** Remove all 8 `[DEBUGGER:...]` lines, or, if any are still load-bearing for prod triage, convert them to a single concise structured log line per code path:
```python
# services/notification-service/app/telegram_notifier.py:27
# Replace the entire init's [DEBUGGER] block + the existing two info lines with:
logger.info(
    "TelegramNotifier initialized",
    extra={"enabled": self.enabled, "chat_id_set": bool(self.chat_id), "token_set": bool(self.bot_token)},
)
```
Apply the same to send_message — drop entry/exit/before/after debugger spam.

### WR-03: `tests/integration/test_notification_delivery.py:49` — file handle leak on `open()`

**File:** `tests/integration/test_notification_delivery.py:49`
**Issue:** `text_content = open(p, encoding="utf-8").read()` does not use a context manager; the file handle is closed only when garbage-collected. Trivial in a one-shot test but a project-convention violation and a flaky-test hazard on Windows hosts (the gitignore at line 95 explicitly mentions Windows artifacts).
**Fix:**
```python
# tests/integration/test_notification_delivery.py:49
with open(p, encoding="utf-8") as fh:
    text_content = fh.read()
# or
from pathlib import Path
text_content = Path(p).read_text(encoding="utf-8")
```

### WR-04: bybit-connector `/metrics` endpoint has dead `try: pass except: pass` block

**File:** `services/bybit-connector/app/main.py:478-484`
**Issue:** The `/metrics` endpoint contains:
```python
try:
    # This will be updated when we access the circuit breaker status
    pass
except:
    pass
```
This is unreachable dead code with a bare `except:` that would swallow `KeyboardInterrupt` / `SystemExit` if anything ever ran inside it. The comment makes it clear this was a forgotten TODO. Worse, bare `except:` is on the project ban list per the anti-mock guard's intent (catches too broadly).
**Fix:**
```python
# services/bybit-connector/app/main.py:471-484 — remove the entire try/except
@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
```
The breaker gauge is already kept in sync via the on-state-change callback (line 222-224 + line 998-1001 comment); no in-endpoint refresh is needed.

### WR-05: `notification_test_mode` host fixture defaults to "record", container defaults to "" — out-of-the-box local test hangs

**File:** `tests/integration/conftest.py:230`, `docker-compose.unified.yml:639`, `services/notification-service/app/config.py:99-102`
**Issue:** The host conftest fixture defaults `mode = os.getenv("NOTIFICATION_TEST_MODE", "record")` and creates/expects `tests/.notifications.log`. The container compose default is `${NOTIFICATION_TEST_MODE:-}` (empty string). The container's `telegram_notifier.py:69` only enters record mode on `== "record"` — empty string falls through to the live POST path. So when a developer runs `pytest tests/integration` locally without setting NOTIFICATION_TEST_MODE explicitly, the host watches a log file that the container never writes to, and the test hangs until the 10-15s timeout. The CI workflow at `.github/workflows/integration.yml:42` exports `NOTIFICATION_TEST_MODE: live` so the CI path works, but a local developer's first run is broken.
**Fix:**
```yaml
# docker-compose.unified.yml — change line 639 default to "record" so local out-of-box matches host fixture
- NOTIFICATION_TEST_MODE=${NOTIFICATION_TEST_MODE:-record}
```
Or, equivalently, change the host fixture default to `""` and document that NOTIFICATION_TEST_MODE must be explicitly set.

### WR-06: `force_signal` integration test sends `"action": "buy"` (lowercase) — unit test uses `"BUY"`

**File:** `tests/integration/test_fresh_clone_round_trip.py:64`, `services/trading-engine/tests/test_force_signal.py:62,185`, `services/trading-engine/app/handlers/orchestration.py:77`
**Issue:** The `SignalSubmissionRequest.action` Pydantic field at orchestration.py:77 has description `"Action: BUY, SELL, CLOSE_LONG, CLOSE_SHORT"` (uppercase). The unit tests in test_force_signal.py:62,185 send `"BUY"`. The integration test at line 64 sends `"buy"` (lowercase). Pydantic does not normalize string fields by default; downstream consumers (`StrategySignal.action`, the orchestrator's submit logic, the notification message at `notify_trade_executed`) compare against `"BUY"`/`"SELL"` literals. The integration test will reach the orchestrator with a value the strategy code does not recognize. Whether it 200s or silently drops depends on consumer paths not in this review's scope — but the divergence between the unit test (uppercase) and the integration test (lowercase) is itself a smell that should be settled.
**Fix:**
```python
# tests/integration/test_fresh_clone_round_trip.py:64 — match casing convention
"action": "BUY",
# or, in orchestration.py:77, add a Pydantic validator that uppercases:
from pydantic import field_validator
@field_validator("action")
@classmethod
def _upper(cls, v: str) -> str:
    return v.upper()
```

### WR-07: `_load_model` returns falsy (None) on success-without-metadata path — `_reload_if_stale` reports "no reload" on a successful reload

**File:** `services/ml-prediction-service/app/ml_models/gru_predictor.py:86-138`, `gru_model.py:102-155`
**Issue:** `_load_model` only `return True` inside the `if metadata_path.exists()` block at line 134 (gru_predictor.py) and line 151 (gru_model.py). When the model file exists but the metadata sidecar doesn't (a real failure mode after partial retrain — model file written, metadata still pending), the function loads the model successfully, sets `self.model_loaded_at = ...` (line 104), but falls through to the implicit `None` return. `_reload_if_stale` at line 182 returns `self._load_model()` — so it returns None (falsy) even though a reload DID happen. Telemetry / log audit reads "reload returned False" → operator believes nothing changed → debugging confusion. The regression test at `test_model_reload.py:55-56` notes this same trap explicitly ("the function only returns True inside the metadata block").
**Fix:**
```python
# gru_predictor.py:86-138 — set a success flag and return at end-of-try
def _load_model(self) -> bool:
    try:
        if not TENSORFLOW_AVAILABLE:
            return False
        model_path = self._get_model_path()
        if not model_path.exists():
            return False
        self.model = keras.models.load_model(str(model_path))
        self.model_loaded_at = model_path.stat().st_mtime
        # ... metadata block (no early return inside) ...
        return True   # <-- success path always returns True
    except Exception as e:
        logger.error(...)
        return False
```
Apply the same shape to `gru_model.py:102-155`.

### WR-08: Notification config `notification_test_mode` accepts arbitrary strings; case-sensitive equality silently breaks `RECORD`/`Record`

**File:** `services/notification-service/app/config.py:99-102`, `services/notification-service/app/telegram_notifier.py:69`
**Issue:** `notification_test_mode: str = Field(default="", description="record|live; ...")` — no `Literal[]` or validator constraints the value. The compare at telegram_notifier.py:69 is `if config.notification_test_mode == "record":`. An operator or CI workflow that exports `NOTIFICATION_TEST_MODE=Record` or `RECORD` (likely typo) will silently drop into the production POST path. With validated channels (telegram_enabled=True + creds set), this would actually deliver real messages from a test run. With test creds, no harm — but the trap is an avoidable foot-gun.
**Fix:**
```python
# services/notification-service/app/config.py
from typing import Literal
notification_test_mode: Literal["", "record", "live"] = Field(
    default="",
    description="record|live; empty string = default production behavior",
)
```
Or, cheaper, normalize at read time: `if config.notification_test_mode.strip().lower() == "record":` in telegram_notifier.py:69. The Literal approach is preferred — it surfaces the typo at startup, not at runtime.

### WR-09: bootstrap.sh creates EMERGENCY_STOP, integration suite never removes it — undocumented coupling, latent hazard for future tests

**File:** `bootstrap.sh:54`, `services/trading-engine/app/main.py:282-289`, `tests/integration/conftest.py:95-130`
**Issue:** `bootstrap.sh:54` calls `touch "$REPO_ROOT/EMERGENCY_STOP"` to leave the auto-trader in STEP-0 hold (intentional per D-11). The trading-engine's lifespan check at `main.py:282-289` then logs `EMERGENCY_STOP file present ... REFUSING to start auto-trader` and `auto_trader_status.set(0)`. The `bootstrap_stack` fixture in conftest.py never removes the file. This currently has no proven failure mode in the in-scope tests:
  - `test_fresh_clone_round_trip` calls `force_signal` → `orchestrator.submit_signal` directly (orchestration.py:903), bypassing the auto-trader.
  - `test_notification_delivery_via_trade_endpoint` POSTs to `/api/v1/notify/trade` directly.
But the coupling is undocumented — any future test that depends on the auto-trader actually firing periodic signals (or assumes a "freshly-booted, ready-to-trade" stack) will silently wait for the 60s deadline before surfacing the issue. Worse: per the comment in `services/trading-engine/app/main.py:267-272`, if the WSL bind-mount race fires, Docker may create a *directory* at the EMERGENCY_STOP mount point — `is_file()` returns False, but the in-container check at line 282 still reports "present" via the bootstrap-created file on the host. Document the coupling or clear the file before yield.
**Fix:**
```python
# tests/integration/conftest.py — extend bootstrap_stack to clear EMERGENCY_STOP
# AFTER the health probe but BEFORE yield, so tests run with auto-trader armed:
@pytest.fixture(scope="session")
def bootstrap_stack(tmp_fresh_clone, services_config):
    # ... existing health-probe loop ...
    # Phase 2 — clear EMERGENCY_STOP so trading-engine arms auto-trader for
    # round-trip tests. CD-04 force-signal bypasses this, but other tests
    # depend on the loop being live.
    stop_file = tmp_fresh_clone / "EMERGENCY_STOP"
    if stop_file.exists():
        stop_file.unlink()
    # ... yield ...
```
Or, equivalently, document in conftest.py that the suite intentionally runs with auto-trader off and only `force-signal` is exercised — and the trading-engine restart path remains untested by this suite.

## Notes / Out of Scope

The following items were considered but NOT raised as findings:

- **`_reload_if_stale` does NOT update `model_loaded_at` on `_load_model` failure** — could thrash one stat() per predict on a permanently broken file. Performance impact only; out of scope per review rules ("Performance issues are NOT in scope for v1").
- **`shell` invocation in iter-fix.sh:85 (`git commit -m "$msg"`)** — the inline comment T-02-06-02 mitigation is correct: `$msg` is a single quoted argument, not re-evaluated by the shell. No shell-injection bug here. Stays as-is.
- **Bare `assert` statements in test files** — pytest convention; not a finding.
- **Hardcoded test credentials in fixtures (e.g. `bybit_api_key="test"`)** — fine for unit tests; not real keys.
- **`docker-compose.unified.yml:19` `version: '3.8'` is obsolete in Docker Compose v2** — Docker emits a warning but it still works; cosmetic, not in scope.
- **`tests/integration/conftest.py:53-60` `_repo_root()` walks up looking for `.git`** — works inside a fresh-clone tmp dir; correct.
- **`scripts/iter-fix.sh` uses `set -e` and `set +e` toggles** — correctly scoped around the pytest line that's allowed to non-zero exit. Defensive.
- **Tape replay log-line wording: `tape_replay_client.py:132-136` emits "TAPE_REPLAY: cursors reset (klines=%d, tickers=%d)"; `main.py:1052` emits "TAPE_REPLAY: cursor reset"** — both forms exist; the tests grep on "TAPE_REPLAY: cursor reset" (singular) which matches the main.py line. Cosmetic inconsistency; tests pass.

---

_Reviewed: 2026-05-08T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
