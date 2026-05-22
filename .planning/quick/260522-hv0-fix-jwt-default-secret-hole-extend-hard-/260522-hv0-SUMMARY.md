---
phase: quick-260522-hv0
plan: 01
subsystem: api-gateway / auth
status: complete
tags: [security, jwt, api-gateway, auth, hardening]
requires: []
provides:
  - "auth_models._validate_jwt_secret() with TRADING_MODE=LIVE and PAPER_TRADING_MODE=false hard-fail conditions"
  - "Single JWT-secret code path (config.py Settings.jwt_secret_key dead field removed)"
affects:
  - "api-gateway boot behavior under any of: production env, staging env, LIVE trading mode, non-paper trading mode"
tech-stack:
  added: []
  patterns:
    - "Env-driven hard-fail predicate (read os.environ on every call so monkeypatch works in tests)"
    - "Trigger-aware logger.critical that surfaces which condition tripped the gate (ENVIRONMENT vs TRADING_MODE vs PAPER_TRADING_MODE)"
key-files:
  created: []
  modified:
    - "services/api-gateway/app/auth_models.py"
    - "services/api-gateway/app/config.py"
    - "services/api-gateway/tests/test_auth_models.py"
    - "services/api-gateway/tests/test_config.py"
decisions:
  - "Removed dead jwt_secret_key Pydantic field instead of making it required (Option A in scope would break dev boot — Settings() instantiates at module import in config.py:143, and a required field with no env var would ValidationError before auth_models._DEV_ONLY_SECRET ever gets a chance). Removal satisfies must_have #2 (no insecure default literal) and must_have #5 (single JWT-secret code path)."
  - "Existing in-memory SECRET_KEY in the running container is NOT updated by docker cp of source files — only the next container recreate picks up the fix. Operator action OP-05 captured below."
metrics:
  duration: "~25 min"
  completed: 2026-05-22
  tests_added: 5 (9 invocations with parametrize)
  tests_passing_new: 9/9
  total_passing: 60
  pre_existing_failures: 3 (logged in deferred-items.md, identical against baseline)
---

# Quick-260522-hv0: Fix JWT default-secret hole in api-gateway — Summary

**One-liner:** Extend `auth_models._validate_jwt_secret()` to hard-fail on
`TRADING_MODE=LIVE` or `PAPER_TRADING_MODE=false` regardless of `ENVIRONMENT`,
and delete the dead `Settings.jwt_secret_key` Pydantic field that shipped a
known-insecure literal default.

## Threat closed

`CONCERNS.md JWT-Default-Insecure-In-Dev` — api-gateway boots with the public
fallback secret `_DEV_ONLY_SECRET` whenever `ENVIRONMENT != production|staging`,
even if the operator has flipped `TRADING_MODE=LIVE` or `PAPER_TRADING_MODE=false`.
Tokens then become forgeable by anyone who knows the literal string (which is
checked into the public repo at `auth_models.py:49`). After this fix,
api-gateway refuses to boot in those modes without a strong `JWT_SECRET_KEY`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Harden `_validate_jwt_secret()` + remove dead Pydantic field + add 5 regression tests | `e0c4aa6` | `services/api-gateway/app/auth_models.py`, `services/api-gateway/app/config.py`, `services/api-gateway/tests/test_auth_models.py`, `services/api-gateway/tests/test_config.py` |

## Diff stats

```
 services/api-gateway/app/auth_models.py        | 38 +++++++++++---
 services/api-gateway/app/config.py             | 68 ++++++++++----------------
 services/api-gateway/tests/test_auth_models.py | 61 +++++++++++++++++++++++
 services/api-gateway/tests/test_config.py      | 24 ---------
 4 files changed, 117 insertions(+), 74 deletions(-)
```

- `auth_models.py`: +30 / -8 (predicate extension + trigger-aware logging)
- `config.py`: +26 / -42 (dead field removal; black reformatter collapsed Field() blocks onto fewer lines, hence -42 / +26 even though the semantic delta is just removing the 4-line jwt_secret_key block; net intentional surface deletion is 4 lines)
- `test_auth_models.py`: +61 / -0 (new `TestJWTSecretValidation` class — 5 cases, 3 parametrize variants → 9 invocations)
- `test_config.py`: -24 / +0 (dead `TestJWTSecretKeyWarning` class removed; that class also had a latent bug — assertions trapped inside a docstring on lines 154-161 never executed)

## What changed in code

### `auth_models._validate_jwt_secret()`

Extended the hard-fail predicate from:

```python
if IS_PRODUCTION or IS_STAGING:
    ...
```

to:

```python
trading_mode = os.environ.get("TRADING_MODE", "PAPER").upper()
paper_trading_mode = os.environ.get("PAPER_TRADING_MODE", "true").lower() == "true"
is_live_mode = trading_mode == "LIVE"
is_non_paper_mode = not paper_trading_mode

if IS_PRODUCTION or IS_STAGING or is_live_mode or is_non_paper_mode:
    if IS_PRODUCTION or IS_STAGING:
        trigger = f"ENVIRONMENT={ENVIRONMENT}"
    elif is_live_mode:
        trigger = f"TRADING_MODE={trading_mode}"
    else:
        trigger = f"PAPER_TRADING_MODE={os.environ.get('PAPER_TRADING_MODE')}"
    # ... same missing-key, short-key, weak-pattern checks, but logs reference {trigger} not {ENVIRONMENT}
```

Matches `main.py:1125-1126` convention for the two env-var reads. Reads `os.environ`
on every call (NOT module-time globals) so `monkeypatch.setenv` in tests is honored.

### `config.Settings`

Deleted the entire `jwt_secret_key: str = Field(default="your-secret-key-change-in-production", ...)` block. Replaced with a comment explaining why
a JWT secret field intentionally lives in `auth_models`, not `Settings`. Grep
confirms zero consumers in `app/` ever read `settings.jwt_secret_key`.

### Tests

Added `TestJWTSecretValidation` after `TestTokenDataModel`. 5 cases:

1. `test_dev_paper_no_env_returns_dev_fallback` — dev + PAPER + no secret → returns `_DEV_ONLY_SECRET`.
2. `test_dev_trading_mode_live_no_env_exits` — parametrized over `["LIVE","Live","live"]` → `SystemExit(1)`.
3. `test_dev_paper_trading_mode_false_no_env_exits` — parametrized over `["false","False","FALSE"]` → `SystemExit(1)`.
4. `test_prod_no_env_still_exits` — regression: production env + no secret → `SystemExit(1)` (existing behavior preserved).
5. `test_dev_live_with_valid_secret_succeeds` — dev + LIVE + valid 64-char key → returns the key (no exit).

Deleted `TestJWTSecretKeyWarning` from `test_config.py` (matches the removed field; also had a latent docstring-trap bug as noted in the plan).

## Verify Command Output

```text
docker exec crypto-bot-api-gateway pytest /app/tests/test_auth_models.py /app/tests/test_config.py -v
...
tests/test_auth_models.py::TestJWTSecretValidation::test_dev_paper_no_env_returns_dev_fallback PASSED [ 69%]
tests/test_auth_models.py::TestJWTSecretValidation::test_dev_trading_mode_live_no_env_exits[LIVE] PASSED [ 71%]
tests/test_auth_models.py::TestJWTSecretValidation::test_dev_trading_mode_live_no_env_exits[Live] PASSED [ 73%]
tests/test_auth_models.py::TestJWTSecretValidation::test_dev_trading_mode_live_no_env_exits[live] PASSED [ 74%]
tests/test_auth_models.py::TestJWTSecretValidation::test_dev_paper_trading_mode_false_no_env_exits[false] PASSED [ 76%]
tests/test_auth_models.py::TestJWTSecretValidation::test_dev_paper_trading_mode_false_no_env_exits[False] PASSED [ 77%]
tests/test_auth_models.py::TestJWTSecretValidation::test_dev_paper_trading_mode_false_no_env_exits[FALSE] PASSED [ 79%]
tests/test_auth_models.py::TestJWTSecretValidation::test_prod_no_env_still_exits PASSED [ 80%]
tests/test_auth_models.py::TestJWTSecretValidation::test_dev_live_with_valid_secret_succeeds PASSED [ 82%]
...
================= 3 failed, 60 passed, 2984 warnings in 29.70s =================
```

**All 9 new TestJWTSecretValidation invocations PASS.**

The 3 failures are pre-existing, container-env-driven (NOT regressions from this plan):

- `TestUserManagement::test_create_user_success` — container `ENVIRONMENT=development`, test docstring expects CI's `ENVIRONMENT=test`
- `TestSettingsValidation::test_default_settings` — container `LOG_LEVEL=DEBUG`, test expects Pydantic default `INFO`
- `TestSettingsValidation::test_backend_service_urls` — container `BYBIT_CONNECTOR_URL=http://bybit-connector:8001` (Docker DNS), test expects `http://localhost:8001`

Identical failures confirmed against the **baseline** (stash my edits, copy original files in, re-run). Logged to `deferred-items.md` per `<scope_boundary>` rule.

## Grep Gates (PLAN <verification> section)

```bash
$ grep -c "your-secret-key-change-in-production" services/api-gateway/app/config.py
0  # PASS (was 1 before, the insecure literal is gone)

$ grep -nE "TRADING_MODE|PAPER_TRADING_MODE" services/api-gateway/app/auth_models.py
59:    - TRADING_MODE=LIVE (any case): hard-fail if JWT_SECRET_KEY missing/weak,
61:    - PAPER_TRADING_MODE=false (any case): same hard-fail. Real-money traffic
76:    trading_mode = os.environ.get("TRADING_MODE", "PAPER").upper()
77:    paper_trading_mode = os.environ.get("PAPER_TRADING_MODE", "true").lower() == "true"
89:            trigger = f"TRADING_MODE={trading_mode}"
91:            trigger = f"PAPER_TRADING_MODE={os.environ.get('PAPER_TRADING_MODE')}"
# PASS (6 matches, 4 inside _validate_jwt_secret(), all via os.environ.get)

$ grep -rn "jwt_secret_key" services/api-gateway/app/
# (no output)
# PASS (0 matches — field removed, no remaining consumers)

$ grep -c "jwt_secret_key" services/api-gateway/tests/test_config.py
0  # PASS (TestJWTSecretKeyWarning class removed)
```

## Container smoke

```bash
$ docker exec crypto-bot-api-gateway curl -sS http://localhost:8000/health
{"status":"degraded","service":"api-gateway",...,"backend_services":{...}}
# Healthy. ml_prediction and sentiment_analysis already degraded pre-plan (compose flags off).
```

## Deviations from Plan

**1. [Rule 3 - Blocking issue] Container `app/` package layout means `docker cp` target path is `/app/app/`, not `/app/`.**
- **Found during:** Task 1 verify step (in-container pytest)
- **Issue:** First `docker cp` run placed files at `/app/auth_models.py` and `/app/config.py`. Python actually imports `app.auth_models` from `/app/app/auth_models.py` (Python package), so the new code wasn't being exercised. All 6 new LIVE/non-paper tests `Failed: DID NOT RAISE` because the import resolved to the un-modified module.
- **Fix:** Re-copied to correct package path: `docker cp ... crypto-bot-api-gateway:/app/app/auth_models.py` (and same for config.py). Test files at `/app/tests/test_*.py` are correct (pytest rootdir is `/app` with `tests/` as test dir).
- **Tracked:** Not committed code change — just an executor-side test-environment fix. No regression introduced.

**2. [Rule 2 - Defense-in-depth tweak] `config.py` NOTE comment originally referenced `jwt_secret_key` by name for clarity, which would have caused PLAN grep gate #3 to register a match.**
- **Found during:** Initial grep-gate check after first edit
- **Issue:** Plan's verification gate says `grep -rn "jwt_secret_key" services/api-gateway/app/` must return zero matches; my explanatory NOTE used the literal name "jwt_secret_key" so it would have matched.
- **Fix:** Rephrased the NOTE to say "a JWT secret field intentionally lives in auth_models, not here" without naming the absent field. Documentation intent preserved, grep gate now passes.
- **Tracked:** Inline rewrite, no separate commit.

No Rule 4 architectural decisions hit. No auth gates.

## Deferred Issues

See `deferred-items.md` — 3 pre-existing env-driven test failures (`test_create_user_success`, `test_default_settings`, `test_backend_service_urls`). All container-env artifacts, all confirmed against baseline, none caused by this plan.

## Operator Next-Action Note

**OP-05 (required before flipping `TRADING_MODE=LIVE` or `PAPER_TRADING_MODE=false` in any deployment):**

```bash
docker compose -f docker-compose.unified.yml up -d --force-recreate api-gateway
```

The hard-fail predicate runs only at module import time (`SECRET_KEY = _validate_jwt_secret()` at `auth_models.py:120`). The currently-running `crypto-bot-api-gateway` container computed its `SECRET_KEY` BEFORE this patch landed — it is using whatever it had at last boot (dev fallback if `JWT_SECRET_KEY` was unset). The fix takes effect on next deploy / container recreate. Recreate is non-destructive (no DB writes lost; only the in-memory `USERS_DB` clears, and that's the in-memory dev store that's not used in prod anyway).

Pre-flip checklist (in addition to existing 4-step LIVE checklist in CLAUDE.md):

```bash
export JWT_SECRET_KEY=$(openssl rand -hex 64)  # 64-byte cryptographic random
docker compose -f docker-compose.unified.yml up -d --force-recreate api-gateway
docker logs --tail 20 crypto-bot-api-gateway | grep -E "JWT secret key validated|SECURITY FAILURE"
# expect: "JWT secret key validated (TRADING_MODE=LIVE)" or "(ENVIRONMENT=production)"
```

## Self-Check: PASSED

- File exists: `services/api-gateway/app/auth_models.py` — FOUND (modified)
- File exists: `services/api-gateway/app/config.py` — FOUND (modified)
- File exists: `services/api-gateway/tests/test_auth_models.py` — FOUND (modified)
- File exists: `services/api-gateway/tests/test_config.py` — FOUND (modified)
- File exists: `.planning/quick/260522-hv0-fix-jwt-default-secret-hole-extend-hard-/deferred-items.md` — FOUND (created)
- All 4 grep gates from PLAN `<verification>` section return expected counts (0 / 6+ / 0 / 0)
- All 9 invocations of `TestJWTSecretValidation` PASS in-container
- Pre-existing 3 failures confirmed identical against baseline (not regressions)
- Commit hash recorded in this Summary (see Tasks Completed table)
