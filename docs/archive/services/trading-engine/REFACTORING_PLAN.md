# Trading Engine Service - God Class Refactoring Plan

**Date:** November 18, 2025
**Pattern:** Strangler Fig (Incremental Migration)
**Target:** Extract 606-line main.py into modular components
**Status:** 🚀 **PLANNING**

---

## Current State Analysis

### File: `app/main.py` (606 lines)

**Endpoint Breakdown:**
- **Health Endpoints** (2): `/health`, `/status`
- **Signal Endpoints** (2): `GET /api/v1/signals/{symbol}`, `POST /api/v1/signals/{symbol}/analyze`
- **Position Endpoints** (2): `GET /api/v1/positions`, `GET /api/v1/positions/{position_id}`
- **Performance Endpoints** (1): `GET /api/v1/performance`
- **Trading Control Endpoints** (3): `POST /api/v1/trading/start`, `POST /api/v1/trading/stop`, `GET /api/v1/trading/status`
- **Phase 1 Endpoints** (3): `GET /api/v1/phase1/metrics`, `GET /api/v1/phase1/health`, `GET /api/v1/phase1/latest`
- **Root Endpoint** (1): `GET /`

**Total:** 14 endpoints + 1 large helper function

### Problems Identified

1. **God Class Anti-Pattern**: All 14 endpoints defined inline in main.py
2. **Mixed Concerns**: HTTP routing + business logic + orchestration
3. **Large Helper Function**: `execute_signal_trade()` is 87 lines (lines 254-340)
4. **Hard to Test**: Business logic tightly coupled with FastAPI
5. **Hard to Navigate**: 606 lines of mixed responsibilities

---

## Target Architecture

```
services/trading-engine/app/
├── main.py (~150 lines)                  ← Thin routing layer
├── handlers/                             ← HTTP layer (6 modules)
│   ├── __init__.py
│   ├── health.py                         ← Health & status endpoints
│   ├── signals.py                        ← Signal fetching & analysis
│   ├── positions.py                      ← Position management
│   ├── performance.py                    ← Performance metrics
│   ├── trading_control.py                ← Trading start/stop
│   └── phase1.py                         ← Phase 1 metrics
└── services/                             ← Business logic layer
    ├── __init__.py
    └── trading_service.py                ← Core trading logic
```

---

## 3-Phase Refactoring Plan

### Phase 1: Foundation (40% complete)
**Goal:** Extract service layer + basic handlers

1. ✅ Analyze structure (606 lines)
2. ✅ Create refactoring plan document
3. Create directory: `app/handlers/`
4. Create directory: `app/services/`
5. Extract `services/trading_service.py`:
   - Move `execute_signal_trade()` function
   - Add `TradingService` class wrapper
   - Make testable (no FastAPI dependencies)
6. Extract `handlers/health.py`:
   - `health_check()` - Health endpoint
   - `get_status()` - Status endpoint
7. Extract `handlers/signals.py`:
   - `get_trading_signal()` - Get signal
   - `analyze_and_trade()` - Analyze & execute
8. Update `handlers/__init__.py` with exports

**Deliverables:** 4 new files (~250 lines)

---

### Phase 2: Full Extraction (50% complete)
**Goal:** Extract remaining handlers

9. Extract `handlers/positions.py`:
   - `get_positions()` - List positions
   - `get_position()` - Get single position
10. Extract `handlers/performance.py`:
    - `get_performance()` - Performance metrics
11. Extract `handlers/trading_control.py`:
    - `start_trading()` - Start auto trading
    - `stop_trading()` - Stop auto trading
    - `get_auto_trading_status()` - Trading status
12. Extract `handlers/phase1.py`:
    - `get_phase1_metrics_endpoint()` - Phase 1 metrics
    - `get_phase1_health()` - Phase 1 health
    - `get_latest_phase1_signal()` - Latest signal
13. Update `handlers/__init__.py` with all exports

**Deliverables:** 6 handler modules (~400 lines total)

---

### Phase 3: Main.py Migration (100% complete)
**Goal:** Reduce main.py to pure routing layer

14. Update `main.py`:
    - Import all handlers from `app.handlers`
    - Replace inline implementations with handler calls
    - Keep only FastAPI routing decorators
    - Remove `execute_signal_trade()` function
15. Test all endpoints for backward compatibility
16. Fix any import errors
17. Rebuild Docker image
18. Create completion documentation

**Target:** main.py reduced from 606 → ~150 lines (75% reduction)

---

## Success Criteria

- [x] **Modularity:** 6+ focused handler modules created
- [ ] **SRP:** Each module has single responsibility
- [ ] **Testability:** Business logic isolated in service layer
- [ ] **Documentation:** Complete refactoring guide
- [ ] **No Duplication:** DRY principle applied
- [ ] **Clean Architecture:** 3-layer separation (HTTP → Service → Domain)
- [ ] **Main.py < 200 lines:** Thin routing layer achieved
- [ ] **Backward Compatible:** All endpoints working

**Overall:** 1/8 criteria met (12.5%)

---

## Module Responsibilities

### 1. `handlers/health.py`
**Endpoints:**
- `GET /health` → health_check()
- `GET /status` → get_status()

**Responsibility:** Service health monitoring

---

### 2. `handlers/signals.py`
**Endpoints:**
- `GET /api/v1/signals/{symbol}` → get_trading_signal()
- `POST /api/v1/signals/{symbol}/analyze` → analyze_and_trade()

**Responsibility:** Signal fetching and analysis
**Delegates to:** TradingService for execution logic

---

### 3. `handlers/positions.py`
**Endpoints:**
- `GET /api/v1/positions` → get_positions()
- `GET /api/v1/positions/{position_id}` → get_position()

**Responsibility:** Position querying and management

---

### 4. `handlers/performance.py`
**Endpoints:**
- `GET /api/v1/performance` → get_performance()

**Responsibility:** Performance metrics and analytics

---

### 5. `handlers/trading_control.py`
**Endpoints:**
- `POST /api/v1/trading/start` → start_trading()
- `POST /api/v1/trading/stop` → stop_trading()
- `GET /api/v1/trading/status` → get_auto_trading_status()

**Responsibility:** Automated trading lifecycle management

---

### 6. `handlers/phase1.py`
**Endpoints:**
- `GET /api/v1/phase1/metrics` → get_phase1_metrics_endpoint()
- `GET /api/v1/phase1/health` → get_phase1_health()
- `GET /api/v1/phase1/latest` → get_latest_phase1_signal()

**Responsibility:** Phase 1 enhancement metrics

---

### 7. `services/trading_service.py`
**Methods:**
- `execute_signal_trade(signal)` - Core trading execution logic

**Responsibility:** Pure business logic (no HTTP dependencies)

**Benefits:**
- Unit testable without FastAPI
- Reusable in auto trader
- No request/response coupling

---

## Expected Metrics

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Files** | 1 monolith | 8 modules | +700% modularity |
| **Lines in main.py** | 606 | ~150 | -75% size |
| **Max File Size** | 606 lines | ~200 lines | -67% complexity |
| **Endpoints per File** | 14 | ~2-3 | +500% focus |
| **Testable Units** | 1 | 8 | +700% testability |
| **SRP Compliance** | ❌ No | ✅ Yes | 100% compliance |

---

## Risk Mitigation

**Risk:** Breaking existing endpoints during migration
**Mitigation:** Strangler Fig pattern - keep original code until handlers proven

**Risk:** Import errors from circular dependencies
**Mitigation:** Clear dependency direction (handlers → services, never reverse)

**Risk:** Missing test coverage
**Mitigation:** Test each endpoint after extraction

---

## Next Steps

1. Start Phase 1: Create directory structure
2. Extract TradingService with execute_signal_trade()
3. Extract health & signal handlers
4. Update exports in handlers/__init__.py

---

**Prepared By:** Claude Code (God Class Destroyer Mode)
**Estimated Effort:** ~2-3 hours
**Pattern:** Strangler Fig
**Status:** 🚀 **READY TO START**
