---
plan: quick-260522-hv0
title: Deferred Items
created: 2026-05-22
---

# Deferred Items (out of scope for this plan)

Pre-existing test failures discovered while running the in-container pytest verify
step. Confirmed identical against the **baseline** (`git stash`/restored, ran the
same test) — these failures predate the plan's edits and are caused by the running
`crypto-bot-api-gateway` container being configured for live-dev usage rather
than test-suite CI invariants.

## 1. `tests/test_auth_models.py::TestUserManagement::test_create_user_success`

**Cause:** Container has `ENVIRONMENT` unset (defaults to `"development"`). The
test's docstring asserts `ENVIRONMENT=test` (CI invariant) so first user gets
`is_admin=False`. In the dev container, first user gets `is_admin=True` per the
auto-admin branch at `auth_models.py:451-454`.

**Fix path (future):** Either run the suite with `ENVIRONMENT=test` (matches CI)
or change the test to monkeypatch `auth_models.IS_DEVELOPMENT=False` before the
assertion. Out of scope for the JWT-secret hardening.

## 2. `tests/test_config.py::TestSettingsValidation::test_default_settings`

**Cause:** Container has `LOG_LEVEL=DEBUG` in its env. The test asserts the
Pydantic default `INFO`. `Settings()` instantiates from env first, so
`settings.log_level == "DEBUG"` in-container.

**Fix path (future):** Use `monkeypatch.delenv("LOG_LEVEL", raising=False)` at
the top of `test_default_settings` (same pattern already used by
`test_caching_settings` for `REDIS_URL`).

## 3. `tests/test_config.py::TestSettingsValidation::test_backend_service_urls`

**Cause:** Container has `BYBIT_CONNECTOR_URL=http://bybit-connector:8001`
(Docker-internal DNS) in its env. The test asserts the Pydantic default
`http://localhost:8001`. Same root cause as #2 — `Settings()` reads env first.

**Fix path (future):** Same pattern — `monkeypatch.delenv` on each of the
asserted env vars at test top.

---

# Confirmation method

```bash
# Run with my edits applied:
docker exec crypto-bot-api-gateway pytest /app/tests/test_auth_models.py /app/tests/test_config.py -v
# 60 passed, 3 failed (the 3 listed above)

# Run with baseline (git stash, copy original files into container):
docker exec crypto-bot-api-gateway pytest /app/tests/test_auth_models.py::TestUserManagement::test_create_user_success -v
# 1 failed, identical assertion error — proves pre-existing.
```

All 9 invocations of the new `TestJWTSecretValidation` class (5 cases × parametrize)
PASS in-container — that's the plan's success gate.
