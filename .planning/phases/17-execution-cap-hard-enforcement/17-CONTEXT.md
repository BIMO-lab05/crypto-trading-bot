# Phase 17: Execution-Cap Hard Enforcement — Context

**Gathered:** 2026-05-24
**Status:** Ready for planning
**Milestone:** v1.3 TA + Engine Correctness (paper-only)
**REQ-IDs covered:** TE-CAP-02, TE-CAP-05

<domain>
## Phase Boundary

Two surgical fixes in `services/trading-engine/`, both narrowed by the Phase 16 AUDIT-01 outcome that found per-trade cap, ADR-010 paper-cap, and RISK-06 emergency-stop file gate already satisfied:

1. **TE-CAP-02 — lock down `POST /api/v1/orchestrator/emergency-stop`.** Today the endpoint at `handlers/orchestration.py:591-622` is unauthenticated and host-exposed on port 8005 (`docker-compose.unified.yml` publishes `${TRADING_PORT:-8005}:8005`). Anyone on the host network can call it. The trading-engine has no auth middleware (`handlers/orchestration.py:725-727` explicitly documents this); the only admin-guarded emergency-stop entry already lives at api-gateway `main.py:1747-1804` (`Depends(get_current_admin_user)`). Phase 17 removes the trading-engine duplicate route entirely and verifies the api-gateway route remains the sole authenticated entry.

2. **TE-CAP-05 — kill bare/broad excepts in the cap-violation-adjacent order path of `auto_trader.py`.** Five named sites + siblings on the path from cap check (`auto_trader.py:1962-1986`) through order submission. Goal is that the existing `[RISK_GATE] PER_TRADE_CAP BREACH` CRITICAL log line at `auto_trader.py:1978-1984` survives in `caplog` whenever the path executes — no surrounding `except:` / `except Exception:` swallows it.

**In scope:**
- Delete `@router.post("/emergency-stop")` from `services/trading-engine/app/handlers/orchestration.py:591-622`
- Add negative test: `POST :8005/api/v1/orchestrator/emergency-stop` returns 404 (route removed)
- Verify existing api-gateway tests at `services/api-gateway/tests/test_gateway_80_coverage.py:263-278` and `services/api-gateway/tests/test_main.py:278-290` still cover the positive path (admin_client → kill-switch file write)
- Rewrite the 5 REQ-named bare/broad except sites in `auto_trader.py` (lines 1551, 1593, 1609, 2498, 3196) + sibling sites on the same file's order-submission path, classified per the D-04 taxonomy
- Land regression test: force `position_value > cap_value` along the order-submission path; assert `[RISK_GATE] PER_TRADE_CAP BREACH` appears in `caplog`; assert no surrounding except site swallowed it
- Update the comment at `handlers/orchestration.py:725-727` to reflect that emergency-stop now lives gateway-only

**Out of scope (defer or reject):**
- Adding any auth middleware / JWT validator / shared-token scheme to trading-engine (deferred — convention preserved; trading-engine has no auth surface)
- Auditing or modifying other unauthenticated trading-engine admin routes (`admin_indicator_router` at `:735`, `admin_force_signal_router` at `:839`) — they have their own protection model (rolling-confidence gate / TRADING_MODE=LIVE refusal gate); scope creep otherwise
- Bare-except cleanup in `live_trading.py`, `bybit_adapter.py`, `paper_trading.py` — those are not on the cap-check → order-submission path inside `auto_trader.py`; deferred to a future hygiene phase
- Adding a parallel kill-switch file writer in trading-engine (gateway remains the sole writer; trading-engine reads via `live_trading.py:290-360` per the existing satisfied RISK-06 gate)
- Any change to the kill-switch file path, format, or bind-mount layout (`safety/EMERGENCY_STOP` → `/app/safety/EMERGENCY_STOP`, per 2026-05-19 compose patch)
- Re-enabling `RSI_DIVERGENCE` / `SQZMOM_ENHANCED` indicators via the indicator-gate route
- Any change to RISK-04 / RISK-06 / ADR-010 cap configuration — all three are Phase-16-confirmed satisfied

</domain>

<decisions>
## Implementation Decisions

### TE-CAP-02 — Auth approach

- **D-01:** **Deprecate the trading-engine route; api-gateway is the sole admin-guarded entry.** The trading-engine endpoint at `handlers/orchestration.py:591-622` is deleted outright. Rationale: (i) the existing api-gateway route at `services/api-gateway/app/main.py:1747-1804` is already admin-guarded via `Depends(get_current_admin_user)`, already writes the kill-switch file via `pathlib.Path.write_text` per the known gotcha, and is already covered by tests; (ii) the trading-engine has zero auth middleware today and the project convention (`handlers/orchestration.py:725-727`) is "admin routes are protected upstream at the api-gateway" — adding JWT validation here would duplicate the api-gateway stack; (iii) a repo-wide grep found ZERO non-doc callers of the trading-engine route, so deletion is safe with no compat shim.

- **D-02:** **Delete the route — no 410-Gone shim, no 403-always stub.** No backwards-compatibility surface. Matches the CLAUDE.md project rule against backwards-compat hacks. If any uncaptured external caller exists, it gets 404 from FastAPI's default unmatched-route handler — visible failure, not silent swallow.

- **D-03:** **Sibling trading-engine admin routes are out of scope.** `admin_indicator_router` (prefix `/api/v1/admin/indicators` at `handlers/orchestration.py:735`) is protected by its rolling-confidence gate + missing persistence layer (effectively no-op). `admin_force_signal_router` (prefix `/api/v1/admin/force-signal` at `:839`) is protected by a `TRADING_MODE=LIVE` refusal gate. Both have their own protection model documented inline. Phase 17 does not audit, modify, or lock them down further.

### TE-CAP-02 — Kill-switch file write behavior

- **D-04:** **api-gateway remains the sole writer; trading-engine never writes the file.** The bind-mount in `docker-compose.unified.yml` puts the same host file in front of both containers; api-gateway writes via `pathlib.Path.write_text` at `main.py:1782-1787`, trading-engine reads via the existing satisfied RISK-06 gate at `services/trading-engine/app/live_trading.py:290-360`. Adding a parallel writer in trading-engine would introduce dual-writer correctness questions for zero benefit.

### TE-CAP-02 — Test coverage

- **D-05:** **Negative test on trading-engine + positive coverage already exists on api-gateway.** Phase 17 ships ONE new test that POSTs (or GETs) `:8005/api/v1/orchestrator/emergency-stop` and asserts a 404 response. Positive coverage (admin_client → 200 + `pathlib.Path.write_text` invoked + file-write-error → 500) already lives in `services/api-gateway/tests/test_gateway_80_coverage.py:263-278` and `services/api-gateway/tests/test_main.py:278-290`. No need to duplicate. Phase 17 runs both suites and confirms green.

### TE-CAP-05 — Scope boundary

- **D-06:** **Strict-but-with-siblings boundary inside `auto_trader.py` only.** Fix the 5 REQ-named sites (`auto_trader.py:1551, 1593, 1609, 2498, 3196`) plus any sibling `except:` / `except Exception:` sites in `auto_trader.py` that sit on the path from cap check (`:1962-1986`) through order submission and that could swallow the `[RISK_GATE] PER_TRADE_CAP BREACH` log line or its sibling cap-rejection logs (`:1995-2003` min-qty / `:2008-2018` min-notional). `live_trading.py`, `bybit_adapter.py`, `paper_trading.py`: out of scope for Phase 17 (those files have their own broad-except patterns — ~50 sites combined — that warrant their own hygiene phase).

- **D-07:** **Audit row required for every broad-except site in the cap-violation-adjacent order path.** Plan emits an inline table: `file:line | category | rewrite | rationale`. Every broad-except in the scope above (D-06) appears in the table whether rewritten or intentionally left alone. Left-alone sites get a `notes` cell stating WHY (e.g. "Decimal parse on user inputs; controlled-return matches D-08 metrics-emit category").

### TE-CAP-05 — Rewrite taxonomy

- **D-08:** **Per-site decision with a locked taxonomy.** Three categories drive the rewrite at each site:
  - **Category M (metrics-emit / log-write / non-load-bearing import)** — example sites: `auto_trader.py:1593-1594`, `:1609-1610`, the inner `try/except` around `risk_limit_breaches_total.labels(...).inc()`-style metric increments. **Allowed pattern:** `except (OSError, ImportError) as e: logger.warning("metrics emit failed: %r", e)` followed by controlled-continue. Must NOT silently `pass` — `logger.warning` is mandatory so the swallow is observable.
  - **Category P (Decimal / parse / cache-lookup on inputs)** — example sites: `auto_trader.py:1551-1556` (Decimal parse on qty/price/balance), `:1562-1569` (instruments-cache import), `:1571-1577` (cache.get). **Allowed pattern:** `except (InvalidOperation, ValueError, TypeError, KeyError) as e: logger.warning("parse failed for {symbol}: %r", e); return <safe_default>`. The safe default must NOT widen the breach surface — e.g. `return True, None` on the min-notional gate when parse fails is acceptable per the existing "Defensive — bad inputs shouldn't crash the gate" comment, but the rewrite must explicitly log + cite that comment.
  - **Category R (RPC / order-submission failure)** — example sites: `auto_trader.py:2498` (notification path inside critical-error branch), `:3196` (notification path inside limit-stop close). **Allowed pattern:** `except (httpx.HTTPError, asyncio.TimeoutError, RuntimeError) as e: logger.error("notif emit failed: %r", e)` — the outer order-submission `except Exception as e` that wraps this stays as-is (it already logs `.error` with `exc_info=True`). The inner notification swallow is the unsafe one; tightening it stops "silently swallowed" from masking the real outer error.
  - **Default if uncertain:** `except Exception as e: logger.exception("..."); raise` — log + re-raise wins ties.

- **D-09:** **The site-by-site classification table is part of the Plan, not the executor's discretion.** Plan-phase reads `auto_trader.py` end-to-end in the cap-check → order-submit range (roughly `:1500-:3210`), enumerates every broad-except, classifies it M/P/R/default, and writes the table into PLAN.md before any code edit. Executor rewrites against the locked classification; if a site doesn't fit M/P/R cleanly, the default (log + re-raise) wins and the rewrite is noted.

### TE-CAP-05 — Regression test target

- **D-10:** **Force `position_value > cap_value`; assert `[RISK_GATE] PER_TRADE_CAP BREACH` reaches `caplog`.** The test sets up an auto-trader instance, drives `quantity = position_value / trade_setup.entry_price` such that `position_value > balance * settings.max_risk_per_trade`, executes the order-submission path, and asserts the CRITICAL log line at `auto_trader.py:1978-1984` appears in `caplog.records`. A second assertion confirms `risk_limit_breaches_total.labels(breach_type="position_size").inc()` was called (mock the metric counter). The test lives at `services/trading-engine/tests/test_te_cap_05_log_survival.py`.

- **D-11:** **REQ text's "TE-CAP-01 log line" interpretation locked.** TE-CAP-01 is demoted by AUDIT-01 (per-trade cap enforcement satisfied at `auto_trader.py:332-344, 1962-1986`). The cap-violation log line REQ-CAP-05 wants asserted is the `[RISK_GATE] PER_TRADE_CAP BREACH` CRITICAL emit at `:1978-1984`. This is the only cap-violation log line in the order-submission path; D-10's assertion is its specific target.

### Documentation update

- **D-12:** **The comment at `handlers/orchestration.py:725-727` is rewritten** to acknowledge that emergency-stop now lives gateway-only and to drop the dangling "all admin routes are protected upstream at the api-gateway" claim that was historically false for the deleted route. Single-file doc edit, no other touch-up.

### Claude's Discretion

- Exact `logger.warning` / `logger.error` wording per rewritten site, within the D-08 category constraints
- Order of edit application (delete route first, then auto_trader.py cleanup, vs reverse) — purely tactical
- Whether to include the 5 REQ-named sites table inline in PLAN.md or as an appendix — Plan-phase author's call
- Choice of pytest fixture style for the cap-breach regression test (parameterized vs single test) — within the D-10 assertion contract

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 17 REQ + audit upstream

- `.planning/REQUIREMENTS.md` §"Execution-Cap Hard Enforcement (TE-CAP)" — TE-CAP-02 + TE-CAP-05 acceptance text; TE-CAP-01/03/04 demotion rationale
- `.planning/ROADMAP.md` §"Phase 17: Execution-Cap Hard Enforcement" — narrowed goal post-AUDIT-01
- `.planning/phases/16-validated-set-re-audit/16-CONTEXT.md` — Phase 16 D-NN audit decisions; reads the same auto_trader.py / orchestration.py files
- `.planning/evidence/AUDIT-01/validated-reaudit.json` (when Plan 07 of Phase 16 finalizes) — `satisfied` rows for RISK-02/03/04/06, ADR-010 paper-cap, the per-trade cap enforcement gate

### Project policy

- `CLAUDE.md` §"Project rules" — risk caps wired into trading-engine (2% LIVE non-negotiable, paper 10% via ADR-010); kill-switch file path `safety/EMERGENCY_STOP` ↔ `/app/safety/EMERGENCY_STOP`
- `CLAUDE.md` §"Gotchas" — `pathlib.Path.write_text` / `read_text` bypass `builtins.open`; patch `pathlib.Path.write_text` directly in tests
- `CLAUDE.md` §"Gotchas" — api-gateway tests must run inside container (fastapi 0.109 → 403; host fastapi 0.136 → 401)
- `CLAUDE.md` §"Gotchas" — api-gateway admin-guarded routes need `admin_client` fixture; `services/api-gateway/tests/conftest.py` overrides `get_current_admin_user` + `get_current_active_user`

### Code targets (read directly during planning)

- `services/trading-engine/app/handlers/orchestration.py:36` — orchestration router prefix `/api/v1/orchestrator`
- `services/trading-engine/app/handlers/orchestration.py:591-622` — **DELETE TARGET**: unauthenticated `@router.post("/emergency-stop")` handler
- `services/trading-engine/app/handlers/orchestration.py:725-727` — auth-note comment to update
- `services/trading-engine/app/auto_trader.py:332-344, 1962-1986` — satisfied per-trade cap enforcement (read-only reference; Phase 17 must not change)
- `services/trading-engine/app/auto_trader.py:1978-1984` — `[RISK_GATE] PER_TRADE_CAP BREACH` log line; D-10 assertion target
- `services/trading-engine/app/auto_trader.py:1551, 1593, 1609, 2498, 3196` — REQ-named TE-CAP-05 sites
- `services/trading-engine/app/auto_trader.py:1500-3210` — broad scope for sibling-site enumeration per D-06/D-09
- `services/trading-engine/app/live_trading.py:290-360` — satisfied RISK-06 emergency-stop file gate (read-only reference)

### Comparison surface (gateway-side admin pattern)

- `services/api-gateway/app/auth_middleware.py:94` — `get_current_admin_user` dependency (reference only; Phase 17 does not port this)
- `services/api-gateway/app/main.py:1747-1804` — the admin-guarded emergency-stop route that survives Phase 17 as the sole entry
- `services/api-gateway/app/main.py:1782-1787` — `pathlib.Path.write_text` kill-switch file writer
- `services/api-gateway/tests/conftest.py:30-80` — `admin_client` fixture overriding `get_current_admin_user` + `get_current_active_user` via `app.dependency_overrides`
- `services/api-gateway/tests/test_gateway_80_coverage.py:263-278` — existing positive-path tests (200 + Path.write_text invoked; 500 on OSError)
- `services/api-gateway/tests/test_main.py:278-290` — additional emergency-stop coverage

### Infrastructure

- `docker-compose.unified.yml` §"trading-engine" — port `${TRADING_PORT:-8005}:8005` exposed to host; bind-mount of `./safety/` for kill-switch file; `EMERGENCY_STOP_FILE=/app/safety/EMERGENCY_STOP`
- `services/trading-engine/requirements.txt` — `fastapi==0.109.0` pin (matches deployed api-gateway; same 403-on-missing-token contract)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **api-gateway emergency-stop route + tests are a working template** at `services/api-gateway/app/main.py:1747-1804` + `services/api-gateway/tests/test_gateway_80_coverage.py:263-278`. The route writes the kill-switch file via `pathlib.Path.write_text`, handles the WSL bind-mount-as-directory edge case, returns 500 on `OSError`. Tests patch `pathlib.Path.write_text` directly per the CLAUDE.md gotcha. Phase 17 leaves this template untouched and just verifies it stays green.
- **`admin_client` fixture pattern** at `services/api-gateway/tests/conftest.py:30-80` overrides `get_current_admin_user` + `get_current_active_user` via `app.dependency_overrides`. Phase 17's negative test on trading-engine doesn't need this (trading-engine has no auth deps to override), but the pattern is canonical for future admin tests.
- **Force-signal route's `TRADING_MODE=LIVE` refusal gate** at `handlers/orchestration.py:831-833,839-849` is the precedent for "lightweight protection without auth middleware". Phase 17 does NOT add a similar gate to emergency-stop (D-01 chose deletion instead), but the pattern is documented for sibling routes.

### Established Patterns

- **Conventional commits**: `fix(trading-engine):` for the route deletion + `auto_trader.py` cleanup, `test(trading-engine):` for the new regression + 404 tests, `docs(trading-engine):` for the `:725-727` comment update.
- **TDD mode is enabled** project-wide: write the 404 test on the trading-engine route FIRST (RED — route still exists, returns 200), then delete the route (GREEN — 404). Write the `[RISK_GATE] PER_TRADE_CAP BREACH` caplog assertion FIRST (RED — bare except may or may not swallow), then walk the bare-except taxonomy (GREEN — log reaches caplog).
- **No backwards-compat shims** — CLAUDE.md project rule. Route deletion is hard; no 410-Gone, no rewrite of unused import re-exports.
- **`# noqa: F401`** on test-patched imports per memory file `feedback_main_imports_autoflake.md` — relevant if any import in `handlers/orchestration.py` is now unused after the route deletion.

### Integration Points

- **api-gateway → trading-engine emergency-stop coupling is removed.** The api-gateway route at `main.py:1747` writes the kill-switch file; trading-engine reads it at `live_trading.py:290-360`. No HTTP call from gateway to trading-engine for the emergency-stop flow — coordination is filesystem-only via the bind-mount.
- **Existing `risk_limit_breaches_total` metric** at `services/trading-engine/app/core/metrics.py` (imported deferred at `auto_trader.py:1975`) is the assertion target for D-10's secondary mock; Phase 17 does not modify the metric definition.
- **Test execution environment** matters: api-gateway tests must run via `docker exec crypto-bot-api-gateway pytest` (CLAUDE.md gotcha). The new trading-engine 404 test can run host-side via the standard `pytest services/trading-engine/tests/`, but the existing api-gateway tests this phase verifies stay green must run in-container.

</code_context>

<specifics>
## Specific Ideas

- Plan-phase should batch all `auto_trader.py` broad-except enumeration into ONE read of `:1500-:3210`. Re-reading the same file multiple times wastes context. Generate the M/P/R/default classification table in a single pass.
- The 404 test on the trading-engine route is the cheapest TDD anchor — write it before any deletion, watch it fail (current 200), then delete the route. Use `TestClient` against the trading-engine FastAPI app, not a network round-trip to port 8005.
- The cap-breach regression test (D-10) should reuse any existing auto-trader test fixture from `services/trading-engine/tests/`. Check for `test_auto_trader_*` fixtures before writing one from scratch; if `position_value > cap_value` is already exercised in an existing test, just extend the assertion list.
- The `handlers/orchestration.py:725-727` comment update is a one-line edit — bundle it in the same commit as the route deletion to keep history clean.
- Plan-phase author: prefer `serena find_referencing_symbols` on `emergency_stop` / `coordinator.emergency_stop` to confirm no in-repo caller; raw grep covered docs already (zero non-doc hits).

</specifics>

<deferred>
## Deferred Ideas (NOT in Phase 17 scope)

- **Future hygiene phase: broad-except cleanup in `live_trading.py`, `bybit_adapter.py`, `paper_trading.py`** — ~50 sites combined. Same M/P/R taxonomy from D-08 would apply but the scope balloons Phase 17 beyond TE-CAP-05's literal text.
- **Future security phase: audit + lock down sibling trading-engine admin routes** (`admin_indicator_router`, `admin_force_signal_router`). Both have their own current protection model documented inline; Phase 17 leaves them as-is.
- **JWT auth middleware in trading-engine** — discussed in Area 1, rejected per D-01. Reopen only if a future requirement demands trading-engine routes be callable from outside the api-gateway proxy with admin identity.
- **Bare-except cleanup as a CI grep gate** (similar to the planned Phase 22 PRICE-02 / Phase 23 ML-PURGE-05 grep gates) — possible future regression-prevention step once the M/P/R taxonomy is proven on the auto_trader.py rewrite.
- **Indicator master-switch persistence layer** mentioned in `handlers/orchestration.py:787-790` TODO — out of phase scope.
- **Re-enabling `RSI_DIVERGENCE` / `SQZMOM_ENHANCED`** via the indicator-gate route — orthogonal to Phase 17; tracked elsewhere.

</deferred>

---

*Phase: 17-execution-cap-hard-enforcement*
*Context gathered: 2026-05-24*
*Scope: 2 REQ-IDs (TE-CAP-02, TE-CAP-05); strict trading-engine surface, no api-gateway code edits*
