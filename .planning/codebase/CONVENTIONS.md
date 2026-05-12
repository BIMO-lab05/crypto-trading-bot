# Coding Conventions

**Analysis Date:** 2026-05-12

## Naming Patterns

**Files:**
- Python: `snake_case.py` (e.g., `signal_aggregator.py`, `risk_engine.py`)
- Tests: `test_<module>.py` mirroring source module name
- React: `PascalCase.tsx` for components, `camelCase.ts` for hooks/utilities
- Config: `config.py` per service under `app/`

**Functions:**
- Python: `snake_case` for functions and methods
- Async handlers prefixed by intent (`get_`, `post_`, `handle_`, `process_`)
- Private helpers prefixed with `_`

**Variables:**
- Python: `snake_case` for locals/attrs, `UPPER_SNAKE` for module constants
- Pydantic settings fields mirror env-var names (e.g., `BYBIT_TESTNET`, `PAPER_TRADING_MODE`)

**Types:**
- Pydantic models: `PascalCase` (e.g., `TradeSignal`, `RiskConfig`)
- TypeScript interfaces / React props: `PascalCase`

## Code Style

**Formatting:**
- Python: `black` (line length project default), `isort` for imports
- Frontend: Prettier defaults; ESLint for React 18 + Vite

**Linting:**
- Python: `ruff` / `flake8`
- `autoflake` strips unused imports during cleanup — this removes test-patched imports from `app/main.py` when logic moves elsewhere. **Fix:** re-add the import with `# noqa: F401` so autoflake leaves it intact for `mock.patch("service.main.symbol")` to bind to.

## FastAPI Service Layout (per service)

```
services/<svc>/
├── app/
│   ├── main.py          # FastAPI app, lifespan, route registration
│   ├── config.py        # pydantic-settings Settings class
│   ├── routes/          # route modules
│   ├── models/          # pydantic schemas
│   ├── services/        # business logic
│   └── ...
├── tests/
└── Dockerfile
```

**`app/main.py`:**
- Constructs `FastAPI()` instance, registers routers, wires `lifespan` async context manager for startup/shutdown
- Imports needed for test patch surface kept with `# noqa: F401` (see autoflake note above)

**`app/config.py`:**
- `pydantic_settings.BaseSettings` subclass
- Loads env vars; never reads `.env` paths directly in code (Pydantic handles)
- Exposes singleton `settings = Settings()`

**Async handlers:** all FastAPI routes are `async def`. Sync I/O wrapped in `asyncio.to_thread` or run on dedicated executor.

## Import Organization

**Order (isort default):**
1. Stdlib
2. Third-party (`fastapi`, `pydantic`, `httpx`, etc.)
3. First-party (`app.*`, `services.*`)
4. Relative imports last (rare)

**Path Aliases:**
- Frontend: `@/` → `frontend/src/`
- Python: no aliases; imports relative to `app/` package root

## REST Surface

**Convention:** `/api/<domain>/<resource>` — **NO `/v1/` prefix** (per ADR-007).

**Domains:** `portfolio`, `trading`, `risk`, `market`, `analysis`, `ml`, `sentiment`, `dashboard`, `performance`

Live OpenAPI: `http://localhost:8000/openapi.json` (gateway authoritative). Snapshot `docs/api/openapi.yaml` removed 2026-04-26 — drift problem.

## Error Handling

**Patterns:**
- HTTP errors raised via `fastapi.HTTPException(status_code, detail)`
- Domain errors: custom exception classes in `app/exceptions.py`, mapped to HTTP via FastAPI exception handlers in `app/main.py`
- Never silently swallow — log + re-raise or surface to caller

## Logging

**Framework:** stdlib `logging` configured per service; structured JSON logs preferred (`logger.info(..., extra={...})`)

**Patterns:**
- One logger per module: `logger = logging.getLogger(__name__)`
- INFO for state transitions, WARNING for recoverable issues, ERROR for failures
- Never log secrets, API keys, or full request bodies containing credentials

## Comments

- Docstrings on public functions/classes (Google or numpy style)
- Inline comments only where intent isn't obvious from code
- TODO/FIXME with author + date when applicable

## Function Design

**Size:** keep handlers thin — delegate to `app/services/` modules.

**Parameters:** type-hint all signatures. Pydantic models for request bodies.

**Return Values:** explicit return types on public APIs. Use `Response` / pydantic model — never raw dict for documented endpoints.

## Module Design

**Exports:** no `__all__` enforcement; rely on convention (leading `_` = private).

**Barrel files:** sparse; only `__init__.py` re-exports where needed for cleaner imports.

## Risk & Trading-Mode Conventions

**Per-trade risk cap:**
- LIVE mode: **2% non-negotiable** — no relax without explicit operator approval and ADR amendment
- Paper mode: relaxed to **10%** per ADR-010 (filed 2026-05-06) to clear Bybit min-notional on $100 sandbox balance
- Pre-LIVE checklist: restore ≤2% before flipping `TRADING_MODE=LIVE`

**Daily-loss circuit-breaker:** 5% — always on, both modes.

**Mainnet + paper dual mode (current default state):**
- `BYBIT_TESTNET=false` → real prices from Bybit mainnet WebSocket
- `PAPER_TRADING_MODE=true` → orders simulated internally
- Path to LIVE = four deliberate steps (PAPER_TRADING_MODE=false, TRADING_MODE=LIVE, mainnet keys with trade perms, `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`)

## Test Fixtures Convention

**`admin_client` fixture** (`services/api-gateway/tests/conftest.py`):
- Required for admin-guarded routes — plain `test_client` returns 403
- Overrides `get_current_admin_user` and `get_current_active_user` via `app.dependency_overrides`
- Pattern reused for any role-gated endpoint testing

## Git & Commit Conventions

**Commits:** Conventional Commits.
- `feat(<service>): <description>` — new feature
- `fix(<service>): <description>` — bug fix
- `chore(<scope>): ...`, `docs(<scope>): ...`, `test(<scope>): ...`, `refactor(<scope>): ...`

**Branches:**
- `feature/<service>-<desc>` — new functionality
- `fix/<desc>` — bug fixes
- `chore/<desc>`, `docs/<desc>` for non-code

**Logical-chunk discipline:** one concern per commit; surface grouping proposal before each commit. No accumulating past ~10 unstaged files.

## Frontend Conventions

**Stack:** React 18 + Vite + TypeScript

**Layout:** `frontend/src/`
- `components/` — reusable UI components (`PascalCase.tsx`)
- `pages/` — route-level views
- `hooks/` — custom hooks (`useFoo.ts`)
- `lib/` — API clients, utilities
- `types/` — shared TS types

**State:** local React state + lightweight context; no Redux. Server state via fetch/SWR-style hooks against gateway.

## Architecture Decision Records (ADRs)

**Location:** `wiki/decisions/` (Obsidian vault).

**Active ADRs (2026-05):** ADR-001 through ADR-010.
- ADR-007: REST surface `/api/<domain>/<resource>` — no `/v1/` prefix
- ADR-010: Paper-mode per-trade risk relax to 10% (filed 2026-05-06)

**Stale reference:** `docs/architecture/DECISIONS.md` referenced in older CLAUDE.md is gone — do not recreate. New decisions land in `wiki/decisions/` as separate ADR pages with YAML frontmatter and wikilinks.

---

*Convention analysis: 2026-05-12*
