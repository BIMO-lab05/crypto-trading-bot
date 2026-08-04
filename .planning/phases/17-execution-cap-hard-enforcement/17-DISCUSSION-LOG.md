# Phase 17: Execution-Cap Hard Enforcement - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-24
**Phase:** 17-execution-cap-hard-enforcement
**Areas discussed:** Auth approach for trading-engine emergency-stop, Kill-switch file write behavior, TE-CAP-05 scope boundary, Exception taxonomy + regression test target

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Auth approach for trading-engine emergency-stop | Add JWT auth dep vs internal-token header vs deprecate route + force gateway-only | ✓ |
| Kill-switch file write behavior | Should trading-engine endpoint ALSO write safety/EMERGENCY_STOP? Dual-writer vs single-writer vs deprecate | ✓ |
| TE-CAP-05 scope boundary | Strict (5 sites) vs wide (live_trading/bybit_adapter) vs risk-cap-adjacent only | ✓ |
| Exception taxonomy + regression test target | Define known-recoverable vs must re-raise; clarify which log line REQ means | ✓ |

**User's choice:** All four areas selected for discussion.

---

## Area 1 — Auth approach for trading-engine emergency-stop

### Q1.1 — How to lock down POST /api/v1/orchestrator/emergency-stop?

| Option | Description | Selected |
|--------|-------------|----------|
| Deprecate trading-engine route; gateway-only | Remove or 410-Gone the trading-engine endpoint. All emergency-stop traffic flows through api-gateway. Single source of truth. Zero new auth code. | ✓ |
| Add JWT admin dep to trading-engine | Port get_current_admin_user pattern from api-gateway/app/auth_middleware.py. Requires duplicating JWT secret validation, User model, HTTPBearer. | |
| Shared-secret internal token header | Require X-Internal-Token header matching env-injected secret. Lighter than full JWT. Secret rotation + storage is new. | |

**User's choice:** Deprecate trading-engine route; gateway-only.
**Notes:** Aligns with existing project convention (`handlers/orchestration.py:725-727`) that admin routes are protected upstream at api-gateway. Zero non-doc callers found in repo grep — safe to delete.

### Q1.2 — How should the trading-engine emergency-stop route be removed?

| Option | Description | Selected |
|--------|-------------|----------|
| Delete the route entirely | Remove the @router.post('/emergency-stop') handler. Zero callers exist. No backwards-compat shim. Matches CLAUDE.md project rule against backwards-compat hacks. | ✓ |
| Return 410 Gone with deprecation note | Keep path but reply 410 with X-Deprecated header pointing to gateway route. Safer if uncaptured script polls it. | |
| Return 403 always + log warning | Effectively reject all calls. Operator-visible if anything tries. | |

**User's choice:** Delete the route entirely.
**Notes:** Repo-wide grep confirmed zero non-doc references. Hard deletion is correct per project rule.

### Q1.3 — Test coverage to prove the deprecation?

| Option | Description | Selected |
|--------|-------------|----------|
| Both negative (404 on trading-engine) + positive (gateway route still admin-guarded) | Test 1: 404 from trading-engine. Test 2: gateway route 403 without admin. Test 3: with admin_client + pathlib.Path.write_text patched, gateway writes file. | ✓ |
| Negative only (404 on trading-engine) | Only assert route gone. Rely on existing api-gateway tests for positive path. | |
| Positive only (api-gateway full path) | Just test gateway route end-to-end. Skip 404 assertion on trading-engine. | |

**User's choice:** Both negative + positive.
**Notes:** Existing api-gateway tests at `test_gateway_80_coverage.py:263-278` and `test_main.py:278-290` already cover the positive path patching `pathlib.Path.write_text`. Phase 17 adds only the 404-on-trading-engine negative test.

### Q1.4 — Should Phase 17 also audit sibling unauthenticated trading-engine admin routes?

| Option | Description | Selected |
|--------|-------------|----------|
| No — strict TE-CAP-02 scope only | Force-signal has TRADING_MODE=LIVE refusal gate. Indicator-gate has rolling-confidence gate (no-op without persistence). Both have own protection. Scope creep otherwise. | ✓ |
| Audit-only — file findings, no code work | Plan emits short audit appendix listing each /api/v1/admin/* route + current protection model. | |
| Lock down all of them now | Apply same gateway-only treatment to every /api/v1/admin/* route on trading-engine. Largest scope. | |

**User's choice:** Strict TE-CAP-02 scope only.

---

## Area 2 — Kill-switch file write behavior (mooted by Area 1)

### Q2.1 — Confirm consequence: trading-engine never writes the kill-switch file; gateway remains sole writer?

| Option | Description | Selected |
|--------|-------------|----------|
| Confirmed — gateway-only writer | Single writer at api-gateway main.py:1782-1787 (already pathlib.Path.write_text + bind-mounted /app/safety/). Trading-engine continues to READ via live_trading.py:290-360 gate. No new code beyond Area 1 deletion. | ✓ |
| Add parallel writer in trading-engine via internal IPC | Trading-engine offers internal-only write path callable by api-gateway. Unnecessary complexity. | |

**User's choice:** Confirmed — gateway-only writer.
**Notes:** Bind-mount of `./safety/` already gives both containers the same file. No dual-writer correctness concerns to introduce.

---

## Area 3 — TE-CAP-05 scope boundary

### Q3.1 — What's the boundary for 'order-submission path' cleanup?

| Option | Description | Selected |
|--------|-------------|----------|
| REQ-named + cap-violation-adjacent in auto_trader.py only | Fix 5 named sites (1551, 1593, 1609, 2498, 3196) + sibling sites in auto_trader.py on the path from cap check to order submission. Excludes live_trading.py / bybit_adapter.py / paper_trading.py. | ✓ |
| Wide — auto_trader + live_trading + bybit_adapter order paths | Extend to ~50 broad-except sites across three files. Balloons phase. | |
| Narrowest — only the 5 named sites, no siblings | Literal REQ list only. Risks leaving sibling sites that swallow same kinds of errors. | |

**User's choice:** REQ-named + cap-violation-adjacent in auto_trader.py only.

### Q3.2 — Default rewrite pattern for each bare/broad except site?

| Option | Description | Selected |
|--------|-------------|----------|
| Per-site decision with taxonomy lock | Phase plan emits taxonomy: (M) metrics-emit/log-write → catch OSError+ImportError, log .warning, continue. (P) Decimal/parse → catch InvalidOperation+ValueError+TypeError, log .warning, return safe default. (R) Order-submission RPC → catch httpx.HTTPError+asyncio.TimeoutError, log .error, re-raise. Default: log + re-raise. | ✓ |
| Always log + re-raise (no controlled-return) | Simpler but breaks current metrics-emit + import-fallback sites that genuinely want to swallow + continue. | |
| Mechanical replace 'except Exception:' → 'except Exception as e: logger.exception(...); raise' | Preserves stack trace via logger.exception. Loses controlled-return for metrics paths. | |

**User's choice:** Per-site decision with taxonomy lock.

---

## Area 4 — Regression test target

### Q4.1 — Pin which log line must survive in caplog

| Option | Description | Selected |
|--------|-------------|----------|
| [RISK_GATE] PER_TRADE_CAP BREACH (auto_trader.py:1978-1984) | Test forces position_value > cap_value, executes the order path, asserts caplog captures the CRITICAL log line, asserts no surrounding bare/broad except swallowed it. | ✓ |
| Both PER_TRADE_CAP BREACH + kill-switch trip log | Add second assertion that kill_switch.check_*() log lines also survive. Wider but couples tests to two code paths. | |
| Generic logger.critical / logger.error coverage | Any CRITICAL or ERROR-level log from order path. Weak — doesn't pin a specific failure mode. | |

**User's choice:** [RISK_GATE] PER_TRADE_CAP BREACH (auto_trader.py:1978-1984).
**Notes:** TE-CAP-01 is demoted by AUDIT-01; REQ-text's "TE-CAP-01 log line" mapped to this concrete log emit at the per-trade cap enforcement gate.

---

## Wrap

| Option | Description | Selected |
|--------|-------------|----------|
| I'm ready for context | Write CONTEXT.md with the 8 decisions + canonical refs + code context. | ✓ |
| Explore more gray areas | Still unclear about TE-CAP-02 or TE-CAP-05 implementation choices. | |

**User's choice:** Ready for context.

---

## Claude's Discretion

- Exact `logger.warning` / `logger.error` wording per rewritten site, within the D-08 category constraints
- Order of edit application (delete route first vs auto_trader.py cleanup first) — tactical
- Whether to include the 5 REQ-named sites table inline in PLAN.md or as an appendix
- Choice of pytest fixture style for the cap-breach regression test (parameterized vs single test) — within D-10 assertion contract
- Wave grouping inside the M/P/R rewrite passes

## Deferred Ideas

- Future hygiene phase: broad-except cleanup in `live_trading.py`, `bybit_adapter.py`, `paper_trading.py` (~50 sites combined)
- Future security phase: audit + lock down sibling trading-engine admin routes (`admin_indicator_router`, `admin_force_signal_router`)
- JWT auth middleware in trading-engine — reopen only if future requirement demands trading-engine routes be admin-callable outside the api-gateway proxy
- Bare-except cleanup as a CI grep gate (similar to planned Phase 22 PRICE-02 / Phase 23 ML-PURGE-05 patterns)
- Indicator master-switch persistence layer (TODO at `handlers/orchestration.py:787-790`)
- Re-enabling `RSI_DIVERGENCE` / `SQZMOM_ENHANCED` via indicator-gate route
