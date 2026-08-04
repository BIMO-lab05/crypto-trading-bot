---
paths:
  - "tests/**/*.py"
  - "services/*/tests/**/*.py"
  - "conftest.py"
  - "pytest.ini"
---

# Testing rules

- **trading-engine host tests still must run from `services/trading-engine/`**, but the env-var workaround is **retired** (2026-08-04). Run them as:
  ```
  cd services/trading-engine && python3 -m pytest tests/ --no-cov
  ```
  `config.py` sets `env_file=".env"` — **relative to cwd** — so from repo root collection dies with `SettingsError: error parsing value for field "cors_origins"`, and from the service dir it used to inherit whatever untracked operator `.env` sat there. That file is gitignored and in practice years stale: the one found on 2026-08-04 (dated 2026-05-06) declared an 11-symbol `TRADING_SYMBOLS` against a 5-key `SYMBOL_ALLOCATIONS`, failing `validate_allocations()` at lifespan startup, and silently disagreed with production on `max_total_exposure_pct` (70.0 vs 80.0), `max_daily_loss_pct` (10.0 vs ADR-028's 12.0), `default_leverage`, `leverage_enabled`, `auto_trading_enabled` and `default_symbol`.
  `tests/conftest.py` now sets `Settings.model_config["env_file"] = None` **at import time** (the singleton is built during collection, so a fixture is too late), pinning host tests to the config defaults — which *are* the production config, since the Dockerfile copies `app/` only and no `.env` enters the image.
  Do **not** try to override these by exporting env vars: pydantic-settings v2 **deep-merges `Dict` fields** across sources, so a `SYMBOL_ALLOCATIONS` env var unions with the dotenv value instead of replacing it and the allocations sum to 1.25.
  Treat a derived-value failure as an env question before treating it as a code bug.
- **Always pass `--no-cov`** on targeted runs. `pytest.ini` injects `--cov --strict-config` into every invocation, which blows the time budget on this repo.
- **`git status` exceeds 60s here** (3.2 GB over an NTFS/WSL mount). Never `git status` bare or `git add -A` — enumerate paths.

- **api-gateway tests must run in the container**: `docker exec crypto-bot-api-gateway pytest`. The host has fastapi 0.136 (401 on `HTTPBearer`), the image pins 0.109 (403). Tests assert 403, so a host run shows fake failures.
- **Admin-guarded gateway routes need the `admin_client` fixture** (`services/api-gateway/tests/conftest.py`), which overrides `get_current_admin_user` and `get_current_active_user`. Plain `test_client` returns 403.
- **`pathlib.Path.write_text` / `read_text` bypass `builtins.open`.** Patch `pathlib.Path.write_text` directly when testing routes like `/api/portfolio/emergency-stop`.
- **trading-engine tests cannot run in-container at all** — corrected 2026-08-04 against the running container. `docker exec crypto-bot-trading pytest tests/` returns `ERROR: file or directory not found: tests/`; there is **no `tests/` directory anywhere in the image**, because `services/trading-engine/Dockerfile` does `COPY app/ ./app/` and nothing else. The earlier "collects zero tests, 4 fatal collection errors" wording did not reproduce. The `.dockerignore` line excluding `tests/standalone/` is inert for the same reason — nothing under `tests/` is copied. `/app/shared` is likewise an empty `mkdir -p`. **Trading-engine is a host-test service; api-gateway is the in-container one.** (PyJWT was genuinely missing from the image and is now in `requirements.txt` — that was a real runtime gap in `app/exchanges/`, not only a test one.)
- **Restart the service after a config change** before re-running integration tests. Stale in-memory config is the number one false pass in this repo.
- Never write a test whose fixture hardcodes a `10000` balance. Import `ACCOUNT_EQUITY_USD`. `tests/test_account_size_invariant.py` enforces this.
- Do not mark a failing test `xfail` or `skip` to make a suite green. If it must be skipped, the skip reason must name the tracking requirement ID.
