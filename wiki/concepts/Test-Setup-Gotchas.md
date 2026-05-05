---
type: concept
status: active
tags: [concept, testing, gotcha]
created: 2026-05-05
updated: 2026-05-05
---

# Test Setup Gotchas

Battle-scars in the test infrastructure. Forget these and chase ghosts.

## 1. api-gateway tests must run **inside** the container

```bash
docker exec crypto-bot-api-gateway pytest
```

Why: host pip has fastapi 0.136 (returns 401 from `HTTPBearer` per RFC 6750). Deployed container pins fastapi 0.109 (returns 403). Tests assert 403. Spurious failures only on host.

## 2. Patch `pathlib.Path.write_text`, not `builtins.open`

`pathlib.Path.write_text` / `read_text` / `Path.open()` go through C-level `_io.open`, **not** `builtins.open`. `mock.patch("builtins.open")` silently does nothing.

When a route writes via `Path`:
```python
with mock.patch("pathlib.Path.write_text") as mw:  # ✓
    ...
# NOT
with mock.patch("builtins.open") as mo:  # ✗ — never intercepts
    ...
```

Same applies to `Path.read_text`, `Path.touch`. Affected route: `POST /api/portfolio/emergency-stop` → see [[../flows/Emergency-Stop]].

## 3. `admin_client` fixture for admin-guarded routes

Plain `test_client` returns 403 on routes guarded by `get_current_admin_user`. Use the `admin_client` fixture in `services/api-gateway/tests/conftest.py` — it overrides both `get_current_admin_user` and `get_current_active_user` via `app.dependency_overrides` and tears down on yield.

Works for any future admin-guarded route test, no JWT forging required.

## 4. Stale in-memory state = #1 cause of false-passes

When config changes, restart the service before integration tests. Else tests pass against old in-memory copy.

## 5. WSL bind-mount race

`docker inspect` can show `bind` mount while path inside container is empty + root-owned (mount silently failed at create time). Symptom: `PermissionError` writing to `/app/logs`. Fix: `docker compose up -d --force-recreate <service>`.

## 6. `main.py` autoflake strips test-patched imports

After refactors that move logic out of `main.py`, re-add re-exports with `# noqa: F401` for symbols that tests monkeypatch (e.g. `db_manager`, `get_aggregator`, `get_portfolio_repository`, `get_paper_engine`).

## 7. Local pytest needs

```bash
pip install --user --break-system-packages tensorflow-cpu==2.16.1 respx aiohttp
```

Required to run lifespan / ML tests outside docker.

## Related

- [[../decisions/ADR-002-trading-engine-lifespan-refactor]]
- [[../flows/Emergency-Stop]]
