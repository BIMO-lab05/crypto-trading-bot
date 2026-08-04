# Coding Conventions

**Analysis Date:** 2026-05-22

## Naming Patterns

**Files:**
- Python modules: `snake_case.py` (e.g., `service_proxy.py`, `auth_middleware.py`)
- Test files: `test_<module>.py` (must start with `test_` — enforced by pre-commit `name-tests-test --pytest-test-first`)
- Config: `config.py` per service (Pydantic Settings singleton)
- Exceptions: `exceptions.py` per service
- Models: `models.py` (Pydantic schemas) or `auth_models.py` per service

**Functions:**
- `snake_case` throughout. Async handlers prefixed with context: `async def get_ticker(...)`, `async def create_order(...)`
- Private helpers: `_snake_case` (e.g., `_fake_admin()` in conftest)
- Properties on Settings: `rest_api_url`, `websocket_url`, `redis_url`, `rabbitmq_url`, `is_production`, `is_testnet`, `is_tape_mode`

**Variables:**
- `snake_case`. Constants: `UPPER_SNAKE_CASE`. Settings fields use lowercase names that auto-map from env vars (e.g., `bybit_testnet` ← `BYBIT_TESTNET`).

**Types / Classes:**
- `PascalCase`. Pydantic models: `Settings`, `User`, `ServiceProxy`. Exception classes: `ConfigurationException`, `CircuitBreakerException`. Test service clients: `MarketDataClient`, `TradingEngineClient`.

**Branches:**
- `feature/<service>-<desc>` (e.g., `feature/bybit-connector-ws-reconnect`)
- `fix/<desc>` (e.g., `fix/auth-token-expiry`)
- `gsd/v<N>-<desc>` (GSD workflow branches, e.g., `gsd/v1.2-polish-real-time`)

## Code Style

**Formatter: Black 23.12.1**
- `line-length = 100` (not PEP 8's 79)
- `target-version = ['py312']`
- Config: `pyproject.toml` `[tool.black]`

**Import sorter: isort 5.13.2**
- `profile = "black"` (Black-compatible mode)
- `line_length = 100`
- `multi_line_output = 3` (vertical hanging indent)
- `include_trailing_comma = true`
- `import-order-style = google`; `application-import-names = services, shared`
- Config: `pyproject.toml` `[tool.isort]` and `.flake8`

**Linter: flake8 7.0.0**
- `max-line-length = 100`; `max-complexity = 10`
- Plugins active: `flake8-docstrings` (google convention), `flake8-bugbear`, `flake8-comprehensions`
- Ignored: E203, W503, E501, E266 (Black-compatibility + docstring noise)
- Per-file ignores: `__init__.py:F401,F403`, `test_*.py:F401,F811`, `conftest.py:F401,F811`
- Config: `.flake8`

**Type checker: mypy v1.8.0 (strict)**
- `disallow_untyped_defs = true`
- Plugins: `pydantic.mypy`, `sqlalchemy.ext.mypy.plugin`
- Config: `pyproject.toml` `[tool.mypy]`

**Security scanner: bandit**
- Applied to `services/` directory only
- Runs as pre-commit hook

**Not used:** ruff (no `.ruff.toml` present)

## Import Organization

**Order (isort google profile):**
1. stdlib (`from pathlib import Path`, `import asyncio`, `from typing import ...`)
2. third-party (`from fastapi import FastAPI`, `from pydantic import Field`, `import httpx`)
3. local application (`from app.config import get_settings`, `from app.exceptions import ...`)

**Path aliases:** None — direct relative/absolute imports within each service package.

**Circular import guard:** Lazy import inside functions used for exception module only:
```python
def get_settings() -> Settings:
    ...
    except Exception as e:
        from app.exceptions import ConfigurationException  # lazy to avoid circular
        raise ConfigurationException(...)
```

## Environment Variable / Config Pattern

Every service has `services/<svc>/app/config.py` with a `Settings(BaseSettings)` singleton:

```python
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, model_validator
from typing import Optional, List, Literal

class Settings(BaseSettings):
    environment: str = Field(default="development", description="...")
    bybit_testnet: bool = Field(default=False, description="...")
    market_data_source: Literal["tape", "live"] = Field(default="tape", description="...")
    redis_password: Optional[str] = Field(default=None, description="...")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v): ...

    @model_validator(mode="after")
    def validate_api_credentials(self): ...

    @property
    def rest_api_url(self) -> str: ...

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }

settings: Optional[Settings] = None

def get_settings() -> Settings:
    global settings
    if settings is None:
        settings = Settings()
    return settings
```

- Env vars auto-mapped from field names (case-insensitive): `BYBIT_TESTNET` → `bybit_testnet`
- Singleton via module-level `settings` global + `get_settings()` accessor
- `reload_settings()` sets global to `None` then calls `get_settings()` — used in tests
- Reference: `services/bybit-connector/app/config.py`

## Async Patterns

**FastAPI lifespan pattern** (all services):
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    await initialize_connections()
    yield
    # shutdown
    await cleanup_connections()

app = FastAPI(lifespan=lifespan)
```

**Async handler convention:**
```python
@router.get("/ticker/{symbol}")
async def get_ticker(symbol: str, settings: Settings = Depends(get_settings)):
    async with httpx.AsyncClient() as client:
        response = await client.get(...)
    return response.json()
```

**No sync-in-async:** Never call blocking IO in async handlers. DB calls via asyncpg/SQLAlchemy async sessions. HTTP calls via `httpx.AsyncClient`.

**SQLAlchemy async session:** `AsyncSession` from `sqlalchemy.ext.asyncio`. Sessions injected via FastAPI `Depends()`.

## Error Handling

**Per-service exception hierarchy:**
- Base: `{ServiceName}Exception` or domain-specific e.g. `ConfigurationException`, `CircuitBreakerException`
- Defined in `services/<svc>/app/exceptions.py`
- FastAPI exception handlers registered in `app/main.py` via `@app.exception_handler(ExceptionType)`

**Pattern:**
```python
try:
    result = await some_operation()
except SpecificException as e:
    raise DomainException(message=str(e), config_field="relevant_field")
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail="Internal server error")
```

**Circuit breaker:** `services/bybit-connector/` has `circuit_breaker_failure_threshold`, `circuit_breaker_recovery_timeout` in Settings. Failures tracked before opening circuit.

**FastAPI HTTP errors:** `raise HTTPException(status_code=..., detail=...)` for client-facing errors.

## Logging

**Framework:** Python stdlib `logging` — NOT loguru.

**Pattern:**
```python
import logging
logger = logging.getLogger(__name__)

logger.info("Ticker fetched", extra={"symbol": symbol, "price": price})
logger.error("Connection failed", exc_info=True)
```

**JSON output:** `pythonjsonlogger.JsonFormatter` configured in some services for structured log shipping (production). Dev output is plain text.

**Log level:** Controlled via `LOG_LEVEL` env var → `Settings.log_level`. Validated to: DEBUG, INFO, WARNING, ERROR, CRITICAL.

## Comments and Docstrings

**Docstring convention:** Google style (enforced by `flake8-docstrings`):
```python
def get_settings() -> Settings:
    """
    Get application settings (singleton pattern)

    Returns:
        Settings instance

    Raises:
        ConfigurationException: If settings cannot be loaded
    """
```

**Inline comments:** Used for section headers in Settings classes (dashed blocks):
```python
# ========================================================================
# BYBIT API CONFIGURATION
# ========================================================================
```

**Decision markers:** Design decisions referenced by code label: `D-14`, `D-15`, `D-17`, `BL-04`, `OP-04`. These cross-reference wiki ADRs in `wiki/decisions/`.

## Module Design

**Per-service layout:**
```
services/<svc>/
├── app/
│   ├── main.py          # FastAPI app + lifespan
│   ├── config.py        # Pydantic Settings singleton
│   ├── exceptions.py    # Service exception hierarchy
│   ├── models.py        # Pydantic request/response models
│   ├── routes/          # FastAPI routers (one file per domain)
│   └── services/        # Business logic (no HTTP concerns)
├── tests/
│   ├── conftest.py
│   └── test_*.py
├── requirements.txt
└── pytest.ini
```

**Exports:** No barrel `__init__.py` re-exports — import directly from submodule path.

**Barrel files:** Not used; `__init__.py` files are empty or minimal (F401 ignored by flake8 per-file rule).

## Frontend Conventions

**Stack:** React 18 + Vite. **Mixed JSX + TSX** — not pure TypeScript. Component files are `.jsx`; some context/provider files are `.tsx`.

**Test framework:** Vitest 1.6.0 + `@testing-library/react` 14.

**Component pattern:**
```jsx
// vi.mock for module stubbing
vi.mock('../api/marketData', () => ({ fetchTicker: vi.fn() }));

describe('ComponentName', () => {
  it('renders correctly', () => {
    render(<Component />);
    expect(screen.getByText('...')).toBeInTheDocument();
  });
});
```

**Test location:** `frontend/src/__tests__/` (co-located with src, not separate `tests/` dir).
- Reference: `frontend/src/__tests__/App.test.jsx`

**CSS/styling:** Not strictly enforced by linter. Tailwind or plain CSS (per component).

**State management:** React context (`frontend/src/contexts/ThemeContext.tsx`). No Redux.

## Commit Conventions

**Format:** Conventional commits with service scope:
- `feat(bybit-connector): add tape-replay market data source`
- `fix(trading-engine): enforce SHORT position 48h max-hold`
- `docs(phase-13): mark complete in roadmap/state/requirements`
- `refactor(api-gateway): extract auth middleware`
- `chore(13): merge wave-3 executor worktree`
- `test(portfolio-manager): add position repository unit tests`

**Scope:** service name (e.g., `bybit-connector`, `trading-engine`, `api-gateway`) or phase number for docs commits.

## ADR Location

Architecture Decision Records: `wiki/decisions/` as ADR-001 through ADR-010+.

**Not** `docs/architecture/DECISIONS.md` — that file does not exist (stale reference).

## Feature Flags (load-bearing, not convention)

These env vars gate runtime behavior — always set explicitly, never rely on defaults in production:

| Flag | Default | Current operator override |
|------|---------|--------------------------|
| `ENABLE_ML_PREDICTIONS` | `false` | `false` (off; GRU models unvalidated) |
| `ENABLE_SENTIMENT_ANALYSIS` | `false` | `false` (idle service) |
| `AUTO_TRADING_ENABLED` | `false` | `true` in `.env` |
| `PAPER_TRADING_MODE` | `true` | `true` |
| `BYBIT_TESTNET` | `false` | `false` (mainnet prices) |
| `MARKET_DATA_SOURCE` | `tape` | set per environment |

---

*Convention analysis: 2026-05-22*
