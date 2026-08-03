---
paths:
  - "tests/**/*.py"
  - "services/*/tests/**/*.py"
  - "conftest.py"
  - "pytest.ini"
---

# Testing rules

- **trading-engine host tests are cwd-sensitive.** `config.py` sets `env_file=".env"` — **relative to cwd**. From repo root, collection dies with `SettingsError: error parsing value for field "cors_origins"`. From `services/trading-engine/`, a service-local `.env` sets `MAX_TOTAL_EXPOSURE_PCT=70.0`, while production (`docker-compose.unified.yml`) uses `80.0`. Any test asserting a value *derived* from settings flips on cwd alone. Run them as:
  ```
  cd services/trading-engine && MAX_TOTAL_EXPOSURE_PCT=80.0 PAPER_INITIAL_BALANCE=100.0 python3 -m pytest tests/ --no-cov
  ```
  Treat a derived-value failure as an env question before treating it as a code bug.
- **Always pass `--no-cov`** on targeted runs. `pytest.ini` injects `--cov --strict-config` into every invocation, which blows the time budget on this repo.
- **`git status` exceeds 60s here** (3.2 GB over an NTFS/WSL mount). Never `git status` bare or `git add -A` — enumerate paths.

- **api-gateway tests must run in the container**: `docker exec crypto-bot-api-gateway pytest`. The host has fastapi 0.136 (401 on `HTTPBearer`), the image pins 0.109 (403). Tests assert 403, so a host run shows fake failures.
- **Admin-guarded gateway routes need the `admin_client` fixture** (`services/api-gateway/tests/conftest.py`), which overrides `get_current_admin_user` and `get_current_active_user`. Plain `test_client` returns 403.
- **`pathlib.Path.write_text` / `read_text` bypass `builtins.open`.** Patch `pathlib.Path.write_text` directly when testing routes like `/api/portfolio/emergency-stop`.
- **trading-engine tests currently collect zero tests in-container** — 4 fatal collection errors: `tests/integration/conftest.py:47` imports `database` via a host-only `parents[5]/shared` path while `/app/shared` is empty; `test_bybit_adapter_wr01_wr04.py` and `test_exchanges.py` need PyJWT in the image; `test_config_default_on_gate.py:48` throws `IndexError` on `parents[3]`. Fix these before believing any trading-engine green run.
- **Restart the service after a config change** before re-running integration tests. Stale in-memory config is the number one false pass in this repo.
- Never write a test whose fixture hardcodes a `10000` balance. Import `ACCOUNT_EQUITY_USD`. `tests/test_account_size_invariant.py` enforces this.
- Do not mark a failing test `xfail` or `skip` to make a suite green. If it must be skipped, the skip reason must name the tracking requirement ID.
