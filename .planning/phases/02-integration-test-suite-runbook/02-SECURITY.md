---
phase: 02
slug: integration-test-suite-runbook
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-08
---

# Phase 02 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Verified by `gsd-security-auditor` against implementation files at HEAD on 2026-05-08.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| docker network → bybit-connector :8001 | Test fixture / container-internal callers reach the new admin route | HTTP POST (no body) |
| operator env (.env) → settings.market_data_source | Mode flag controls whether `/admin/tape/reset` accepts traffic | Env var (string) |
| docker network → trading-engine :8005 | Test fixtures reach `/api/v1/admin/force-signal` admin endpoint | HTTP JSON (SignalSubmissionRequest) |
| operator env → settings.trading_mode | LIVE/PAPER flag controls 403 refusal in force-signal | Env var (string) |
| HTTP body → SignalSubmissionRequest | Untrusted scalar inputs enter the signal pipeline | JSON body |
| filesystem → tmp_fresh_clone | Fixture writes to `/tmp/cb-test-<sha>`; subprocess inherits operator env | git clone, file writes |
| network → docker compose stack | Fixtures call admin endpoints over the network seam | HTTP |
| postgres / timescaledb → db_truncate | Test-only DDL via asyncpg pool against test ports | TRUNCATE SQL |
| pytest → docker stack | Tests call admin endpoints over HTTP | HTTP |
| pytest → postgres / timescaledb | Tests read DB rows directly | SELECT SQL |
| operator env → notification-service | NOTIFICATION_TEST_MODE flag controls record vs live | Env var |
| .env.test.example (committed) | Becomes a vector if a real token is accidentally committed | Static file |
| notification-service → tests/.notifications.log (record mode) | Service writes through bind-mount to host filesystem | File append (JSON line) |
| notification-service → api.telegram.org (live mode) | TEST_TELEGRAM_BOT_TOKEN reaches the wire | HTTPS POST |
| docker-compose.unified.yml → container env | Compose passthrough is the only path host env reaches the container | Env var passthrough |
| operator shell → iter-fix.sh | Operator-supplied commit messages and fix diffs | stdin/argv |
| stdin → iter-fix-check-diff.sh | Untrusted diff content (could come from a wrapped Claude `-p` invocation) | unified diff text |
| docs → operator | Documentation only — no code surface | static markdown |
| filesystem → ml-prediction-service | Model files watched via mtime; an attacker writing the model file injects predictions | file mtime + bytes |
| signal pipeline → aggregator | Filter at aggregator-side defends against bad-confidence injectors | tuple (label, weight) |
| GitHub Actions secrets → CI runner env | `secrets.TEST_TELEGRAM_*` reaches the workflow as env vars | encrypted env |
| CI runner → api.telegram.org | Live notification verification path POSTs to Telegram | HTTPS |
| CI runner artifact upload | docker compose logs + integration-logs.txt uploaded | log file |
| GitHub branch protection → PR enforcement | Operator-configured; the only structural defense against direct-push bypass of the anti-mock guard | repo policy |
| operator shell → make | Operator-supplied SVC variable interpolated into compose command | Make variable |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-02-01-01 | E (elevation) | POST /admin/tape/reset | mitigate | HTTP 403 when `settings.market_data_source != "tape"` — `services/bybit-connector/app/main.py:1039`; gate runs before client lookup at line 1051 | closed |
| T-02-01-02 | T (tampering) | TapeReplayClient state | mitigate | `reset()` touches only in-memory cursors at `services/bybit-connector/app/tape_replay_client.py:124`; fixtures bind-mounted RO at `docker-compose.unified.yml:363` (`./tests/fixtures/tape:...:ro`) | closed |
| T-02-01-03 | D (DoS) | rate-limit | mitigate | `@limiter.limit("60/minute")` on tape reset endpoint — `services/bybit-connector/app/main.py:1027` | closed |
| T-02-01-04 | I (info disclosure) | log injection | mitigate | Static log line `TAPE_REPLAY: cursor reset` at `services/bybit-connector/app/main.py:1050` — parameter-free, no operator input | closed |
| T-02-01-05 | R (repudiation) | unaudited reset | accept | In-memory cursor zeroing; uvicorn access logs sufficient | closed |
| T-02-01-06 | S (spoofing) | no-auth network exposure | accept | bybit-connector has no auth middleware (project pattern); MARKET_DATA_SOURCE gate is the boundary | closed |
| T-02-02-01 | E (elevation) | force-signal in LIVE mode | mitigate | HTTP 403 when `settings.trading_mode == "LIVE"` at `services/trading-engine/app/handlers/orchestration.py:859`; gate fires BEFORE `get_strategy_orchestrator()` call at line 865 | closed |
| T-02-02-02 | T (tampering) | synthetic signal in real-money pipeline | mitigate | Same gate as T-02-02-01; project's three-flag LIVE checklist (PAPER_TRADING_MODE/TRADING_MODE/LIVE_TRADING_ACK) | closed |
| T-02-02-03 | I (log injection) | request.reasoning is free-form text | mitigate | logger.warning at `services/trading-engine/app/handlers/orchestration.py:895-901` excludes `request.reasoning`; only controlled scalars (strategy_id, symbol, action, direction) | closed |
| T-02-02-04 | D (DoS) | rate-limit on admin endpoint | accept | trading-engine has no slowapi installed; per-test cadence ≤10/run; LIVE gate refuses before orchestrator | closed |
| T-02-02-05 | R (repudiation) | unaudited admin call | mitigate | Single WARNING-level log line `FORCE_SIGNAL: strategy_id=...` at `services/trading-engine/app/handlers/orchestration.py:896` | closed |
| T-02-02-06 | S (spoofing) | no-auth network exposure | accept | Consistent with project pattern; TRADING_MODE gate is the boundary | closed |
| T-02-03-01 | T (data destruction) | TRUNCATE on production DB | accept | DB URLs default to localhost test ports; CI sets explicit POSTGRES_URL/TIMESCALE_URL | closed |
| T-02-03-02 | I (info disclosure) | leaked secrets in tmp clone | mitigate | `tmp_fresh_clone` writes empty `.env` at `tests/integration/conftest.py:83` (`(tmp / ".env").write_text("")`) | closed |
| T-02-03-03 | T (port-mapping confusion) | wrong service hit | mitigate | Port mapping fixed: `bybit_connector=8001` and `trading_engine=8005` at `tests/integration/conftest.py:34,38` | closed |
| T-02-03-04 | D (DoS hang) | bootstrap.sh infinite hang | mitigate | `subprocess.run([...], timeout=300)` at `tests/integration/conftest.py:131` | closed |
| T-02-03-05 | E (privilege) | subprocess inherits operator env | accept | Repo-relative paths; no eval; no sudo | closed |
| T-02-04-01 | T (test mutation) | banned-pattern reintroduction | mitigate | `grep -rE "pytest\.skip\|pytest\.mark\.xfail\|unittest\.mock\|mocker\.patch" tests/integration/` returns 0 hits; CI guard in 02-09 enforces on PR | closed |
| T-02-04-02 | I (info disclosure) | DB URL placeholder password | accept | postgres URL contains placeholder; production deploys must use a different password (operator) | closed |
| T-02-04-03 | T (race condition) | position row read before commit | mitigate | Fresh asyncpg pool per test at `tests/integration/test_fresh_clone_round_trip.py:85`; `created_at IS NOT NULL` filter at lines 91-96 | closed |
| T-02-04-04 | D (DoS poll) | unbounded poll loop | mitigate | Hard 60s deadline via `time.monotonic()` at `tests/integration/test_fresh_clone_round_trip.py:74,107`; `elapsed < 60.0` assertion | closed |
| T-02-04-05 | E (privilege via XRPUSDT) | unknown-symbol bypass | mitigate | `test_unknown_symbol_does_not_500` at `tests/integration/test_fresh_clone_round_trip.py:140` asserts 200+empty list, not 500 | closed |
| T-02-05-01 | I (info disclosure) | bot token committed to .env.test.example | mitigate | `.env.test.example` placeholder-only (`TEST_TELEGRAM_BOT_TOKEN=` empty); `.env.test` gitignored at `.gitignore:55`; regression test `test_env_test_example_has_no_real_token` in `tests/integration/test_notification_delivery.py` | closed |
| T-02-05-02 | I (info disclosure) | bot token in CI logs | mitigate | Workflows pass via `env:` from `${{ secrets.TEST_TELEGRAM_BOT_TOKEN }}` at `.github/workflows/integration.yml:43,53` and `.github/workflows/integration-ml-on.yml:40`; never echoed; GitHub Actions auto-masks secrets | closed |
| T-02-05-03 | T (record-mode log injection) | message body free-form text | accept | Message JSON-serialized via `json.dumps(...)` at `services/notification-service/app/telegram_notifier.py:74`; no shell metacharacters; fixture reads via `Path.read_text` (no eval) | closed |
| T-02-05-04 | E (escape from record mode) | bug routes record-mode to live API | mitigate | `if config.notification_test_mode == "record":` short-circuit at `services/notification-service/app/telegram_notifier.py:65`; emits `NOTIFICATION_RECORD: path=` log at line 73 BEFORE writing JSON line; live API path never reached in record mode | closed |
| T-02-05-05 | D (unbounded log growth) | record file growth | accept | Fixture truncates `tests/.notifications.log` before-each at `tests/integration/conftest.py:261` (`log_path.write_text("")`) | closed |
| T-02-05-06 | R (no audit) | record-mode bypasses Telegram audit | accept | Record mode is test-only; production must not set NOTIFICATION_TEST_MODE | closed |
| T-02-05-07 | T (host attacker via tests bind-mount) | container writes to host tests/ | accept | Host write to tests/ already controls developer checkout; production must not mount tests/ | closed |
| T-02-06-01 | T (base64 bypass) | obfuscated banned-pattern import | accept | Literal-string grep; D-11 operator review at Apply prompt is second defense | closed |
| T-02-06-02 | T (command injection via commit msg) | shell metachar in $msg | mitigate | `read -p "Commit message..."` at `scripts/iter-fix.sh:78`; passed quoted to `git commit -m "$msg"` at line 85; no eval | closed |
| T-02-06-03 | T (auto-iteration via misuse) | shell `while`/`watch` wrapping | accept | Cannot prevent shell-level wrapping; CI repeats diff-check on PR (02-09 guard) | closed |
| T-02-06-04 | E (privilege escalation) | script writes outside repo | accept | `cd "$REPO_ROOT"` at script start; no sudo; all git ops scoped | closed |
| T-02-06-05 | I (info disclosure in failure log) | secrets in pytest output | accept | Failure log local-only `/tmp/<xxx>`; not uploaded by this script | closed |
| T-02-06-06 | E (escape via diff format) | crafted diff hits file-path parser | mitigate | Anchored bash regex `^\+\+\+ b/(.+)$` at `scripts/iter-fix-check-diff.sh:65`; 8 fixture cases pass | closed |
| T-02-07-01 | I (leaked secrets in examples) | API keys/tokens in RUNBOOK | mitigate | `grep -i "API_KEY\|BOT_TOKEN" RUNBOOK.md` returns 0 hits; all examples are command shapes | closed |
| T-02-07-02 | T (misleading triage steps) | operator harm from bad commands | mitigate | Every command sourced from CLAUDE.md or bootstrap.sh; 6 `## Symptom:` sections all carry Diagnose/Action/Verification | closed |
| T-02-07-03 | R (no repudiation needed) | static markdown | accept | No state, events, audit surface | closed |
| T-02-08-01 | T (model file tampering) | mtime watch trusts file content | accept | Operator owns model file; mtime watch only removes restart requirement | closed |
| T-02-08-02 | T (confidence=0 bypass aggregator) | tuple (sig, weight) with weight=0 reaches weighted-sum | mitigate | Filter at aggregator chokepoint `services/technical-analysis/app/handlers/analysis.py:95` (`weight > 0.0`) BEFORE weighted-sum at line 104; `AGGREGATOR_CONFIDENCE_FILTER` log at line 99 (note: plan key_link `confidence.*==.*0` retargeted to `weight > 0.0` per 02-08-SUMMARY operator-approved retarget) | closed |
| T-02-08-03 | I (path leaked in log) | MODEL_RELOAD path disclosure | accept | Path is non-secret; matches compose volume mount | closed |
| T-02-08-04 | D (mtime syscall on hot path) | hot-path overhead | mitigate | `model_path.stat().st_mtime` single syscall in `_reload_if_stale()` at `services/ml-prediction-service/app/ml_models/gru_predictor.py:152,168`; called at `predict()` line 482; sub-microsecond (note: plan key_link `model_loader.get_current_model` retargeted to `_reload_if_stale` per 02-08-SUMMARY operator-approved retarget) | closed |
| T-02-09-01 | I (bot token in CI logs) | secret leakage | mitigate | Tokens pass via `env:` from `${{ secrets.* }}` at `.github/workflows/integration.yml:43,53`; never echoed; GitHub Actions auto-masks | closed |
| T-02-09-02 | I (bot token in artifacts) | docker compose logs contain token | accept | notification-service logs `bot_token_set=True` boolean only; never the token itself (per 02-09-SUMMARY disposition) | closed |
| T-02-09-03 | T (direct-push bypass) | iter-fix-check-diff.sh runs only on PR | mitigate | Anti-mock step gated to `if: github.event_name == 'pull_request'` at `.github/workflows/integration.yml:59`; runs against `origin/main..HEAD` at line 66; branch protection is operator action documented in 02-09-SUMMARY | closed |
| T-02-09-04 | E (PR-from-fork attack) | malicious test mutation | mitigate | `fetch-depth: 0` at `.github/workflows/integration.yml:22`; anti-mock guard runs against `origin/main..HEAD`; Actions reads forked-PR secrets read-only by default | closed |
| T-02-09-05 | D (runaway CI) | unbounded workflow time | mitigate | `timeout-minutes: 30` at `.github/workflows/integration.yml:17`; `timeout-minutes: 45` at `.github/workflows/integration-ml-on.yml:16` | closed |
| T-02-09-06 | T (artifact tampering) | log modified post-upload | accept | GitHub Actions artifacts immutable post-upload | closed |
| T-02-10-01 | T (command injection via SVC) | shell metachar in $(SVC) | accept | Local-developer scope; CI uses bash bootstrap.sh directly (Plan 02-09) — does not invoke this Make target | closed |
| T-02-10-02 | I (secrets in build context) | leaked .env in build logs | accept | Same risk as direct `docker compose build`; `.env` gitignore + `BYBIT_API_KEY=` defaults are the control | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-02-01 | T-02-01-05 | Reset is non-destructive (in-memory cursor zeroing only); uvicorn access logs are sufficient audit. No PII / financial impact. | gsd-planner via 02-01-PLAN | 2026-05-07 |
| AR-02-02 | T-02-01-06 | bybit-connector has no auth middleware (existing project pattern; protected upstream at api-gateway). Route reachable only inside docker network when MARKET_DATA_SOURCE=tape. Production deploys MUST NOT set MARKET_DATA_SOURCE=tape (operator runbook responsibility — RUNBOOK.md). | gsd-planner via 02-01-PLAN | 2026-05-07 |
| AR-02-03 | T-02-02-04 | trading-engine has no slowapi installed; per-test cadence (≤10 calls/run) does not warrant the dep. LIVE gate refuses BEFORE orchestrator call (no DoS vector through submit_signal). | gsd-planner via 02-02-PLAN | 2026-05-07 |
| AR-02-04 | T-02-02-06 | trading-engine has no auth middleware (project pattern); TRADING_MODE gate is the security boundary. Operator/deploy errors that expose :8005 outside docker network tracked separately. | gsd-planner via 02-02-PLAN | 2026-05-07 |
| AR-02-05 | T-02-03-01 | DB URLs default to localhost test ports (5432/5433); production DB on separate network. CI sets explicit POSTGRES_URL/TIMESCALE_URL pointing at the test stack. Operator running pytest against prod is operator error. | gsd-planner via 02-03-PLAN | 2026-05-07 |
| AR-02-06 | T-02-03-05 | All shelled commands use absolute or repo-relative paths (./bootstrap.sh, git via PATH). No eval. Operator running pytest against their own system is accepted threat surface. | gsd-planner via 02-03-PLAN | 2026-05-07 |
| AR-02-07 | T-02-04-02 | postgres URL contains placeholder password (`postgres:postgres` / `cryptobot:cryptobot_dev_password` per compose). Production deploys MUST use a different password (operator responsibility). Test env uses default localhost ports. | gsd-planner via 02-04-PLAN | 2026-05-08 |
| AR-02-08 | T-02-05-03 | Operator-supplied `message` is JSON-serialized via `json.dumps(...)`; no shell metacharacters. Fixture reads log via `Path.read_text` (no eval). Worst case: attacker controls own message text written to log file they already had access to. | gsd-planner via 02-05-PLAN | 2026-05-07 |
| AR-02-09 | T-02-05-05 | Each test truncates `tests/.notifications.log` via fixture before-each (record mode; Plan 02-03). Local dev can manually clear; production never hits this branch (NOTIFICATION_TEST_MODE empty by default). | gsd-planner via 02-05-PLAN | 2026-05-07 |
| AR-02-10 | T-02-05-06 | Record mode is for test contexts only. Production deploys MUST NOT set NOTIFICATION_TEST_MODE; default empty string preserves today's behavior. | gsd-planner via 02-05-PLAN | 2026-05-07 |
| AR-02-11 | T-02-05-07 | The `./tests:/app/tests:rw` bind-mount lets the container write to host tests/. An attacker with write to host tests/ already controls the developer's checkout. Production deploys MUST NOT mount tests/. | gsd-planner via 02-05-PLAN | 2026-05-07 |
| AR-02-12 | T-02-06-01 | Grep regex is literal-string. A determined operator who base64-encodes `unittest.mock` evades the script. D-11 (per-fix human review at the Apply prompt) is the second line of defense. The script's job is to catch obvious cases, not adversarial ones. | gsd-planner via 02-06-PLAN | 2026-05-07 |
| AR-02-13 | T-02-06-03 | Cannot prevent shell-level wrapping (`while`/`watch`). The script as written exits cleanly after one cycle; D-13 carry-forward + INFRA-04 are aspirational anti-Goodhart guardrails. CI repeats the diff-check on PR (02-09), which is the second structural defense. | gsd-planner via 02-06-PLAN | 2026-05-07 |
| AR-02-14 | T-02-06-04 | `cd "$REPO_ROOT"` at script start; all `git` ops are scoped. No `sudo`, no system writes. | gsd-planner via 02-06-PLAN | 2026-05-07 |
| AR-02-15 | T-02-06-05 | `pytest tests/integration` may print env vars or DB URLs. Failure log is local-only (`/tmp/<xxx>`); not uploaded by this script. CI workflow (02-09) uploads `integration-logs.txt` as artifact — that path masks env vars via Actions secrets. | gsd-planner via 02-06-PLAN | 2026-05-07 |
| AR-02-16 | T-02-07-03 | No state, no events, no audit surface introduced (static markdown). | gsd-planner via 02-07-PLAN | 2026-05-07 |
| AR-02-17 | T-02-08-01 | Operator owns the model file via `scripts/train_ml.*`. An attacker with filesystem write to `/app/models/` already controls the service entirely. The mtime watch does not introduce a new vector — it removes the requirement to restart. | gsd-planner via 02-08-PLAN | 2026-05-08 |
| AR-02-18 | T-02-08-03 | Log line `MODEL_RELOAD: path=/app/models/<file>` discloses internal path. Path is non-secret (compose file shows the volume mount). | gsd-planner via 02-08-PLAN | 2026-05-08 |
| AR-02-19 | T-02-09-02 | docker compose logs artifact does not contain bot token. notification-service logs `bot_token_set=True` boolean only, never the token itself (per 02-09-SUMMARY disposition; plan-level mitigate marker re-recorded as accept to match implementation summary). | gsd-planner via 02-09-PLAN/SUMMARY reconcile | 2026-05-08 |
| AR-02-20 | T-02-09-06 | GitHub Actions artifacts are immutable post-upload. Verifying their integrity is GitHub's job. | gsd-planner via 02-09-PLAN | 2026-05-08 |
| AR-02-21 | T-02-10-01 | Make's `$(SVC)` is shell variable expansion; an operator who deliberately injects `;`, `\``, `$()` is attacking themselves. Local-developer scope; CI uses `bash bootstrap.sh` directly (Plan 02-09 does not invoke this Make target). | gsd-planner via 02-10-PLAN | 2026-05-07 |
| AR-02-22 | T-02-10-02 | Same risk as direct `docker compose build` invocation. CLAUDE.md's `.env` gitignore + `BYBIT_API_KEY=` defaults handle this. | gsd-planner via 02-10-PLAN | 2026-05-07 |

*Accepted risks do not resurface in future audit runs.*

---

## Operator Actions Required (out-of-code controls)

These are not threats with code mitigations — they are operational prerequisites the security model assumes. Recorded here for audit traceability.

| Action | Rationale | Plan | Owner |
|--------|-----------|------|-------|
| Configure GitHub branch protection on `main`/`master` (require PR + status check `Integration Suite (Phase 2)`) | T-02-09-03 anti-mock guard runs only on `pull_request` events. Direct pushes to main bypass it; branch protection is the structural defense. Without it, the guard is advisory. | 02-09 | repo admin |
| Configure GitHub repo secrets `TEST_TELEGRAM_BOT_TOKEN` and `TEST_TELEGRAM_CHAT_ID` | CI workflow injects these via `${{ secrets.* }}`; absent secrets cause notification-verification step to fail. | 02-09 | repo admin |
| Production deploys MUST NOT set `MARKET_DATA_SOURCE=tape` | Tape mode unlocks `/admin/tape/reset`. Production must run with `live` value so the gate rejects with 403. | 02-01 | release operator |
| Production deploys MUST NOT set `NOTIFICATION_TEST_MODE` (leave empty / unset) | Record mode bypasses Telegram audit trail. Production needs the live API path. | 02-05 | release operator |
| Production deploys MUST NOT bind-mount `./tests:/app/tests:rw` on notification-service | Test-only mount grants container write to host. | 02-05 | release operator |
| LIVE trading flip requires three-flag checklist: `PAPER_TRADING_MODE=false`, `TRADING_MODE=LIVE`, `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` | Defense-in-depth around the force-signal LIVE gate. | 02-02 | release operator |

---

## Unregistered Flags

None. SUMMARY files for plans 02-09 and 02-10 explicitly declare empty `## Threat Flags` sections; remaining plans (01–08) did not introduce attack surface beyond what was registered at plan time.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-08 | 50 | 50 | 0 | gsd-security-auditor |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-08
