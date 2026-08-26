# Wait-Window Work Plan (2026-08-20 → ~2026-09-09) — Design Spec

**Date:** 2026-08-20
**Status:** Approved design, pending user spec review
**Branch:** spec lands on `feature/edge-search-v2`; Phase 19 work gets its own branch at plan time per repo convention.

## 1. Why this exists

Edge-search v2 is fully executed: orderbook/OI collectors live since 2026-08-19, battery #3 all-REJECT (including the corrected maker re-gate — the cost floor was never the binding constraint; the statistical bar is). The next edge-research step, Phase C (microstructure battery), is gated on **≥21 consecutive gap-free days of orderbook data — earliest ~2026-09-09**. That leaves a ~3-week window where edge research has nothing to run.

This spec fills the window with three streams, chosen deliberately (battery #4 on klines was considered and **excluded** — nine families dead across three batteries; remaining kline families are thin pickings with expected REJECTs):

1. **Forward-paper evidence: repair + start accrual** — wall-clock-bound, starts first.
2. **Debt cleanup** — bounded-smalls batch first (clears test noise before the big change), mediums trail.
3. **Phase 19, reframed** — order-path consolidation + reconciliation. The main engineering block.

Ordering principle (same as edge-search v2 §2): **anything that converts calendar time into value starts on day one.** Evidence accrual and orderbook collection are the only two such things in the repo; both must run while engineering happens, not after.

## 2. Stream 0 — obligatory collection monitoring (no decisions, listed for completeness)

- 48-hour collection acceptance re-run due **2026-08-21 17:30 UTC**: `scripts/check_collection_gaps.py`, result recorded in `.planning/evidence/`.
- Weekly gap checks thereafter. Phase C gate check on ~2026-09-09: ≥21 consecutive gap-free days, objectively scriptable, no judgment call.
- Any gap found = collection incident, fixed before anything else in this plan (a broken day resets the 21-day clock).

## 3. Stream 1 — forward-paper evidence: repair + start accrual (days 1–2, then background)

### 3.1 Findings this stream answers (scan 2026-08-20, file:line-cited)

- `scripts/forward_paper_test/run_evidence_loop.py:51` hardcodes `/data/tournament.db`; `services/trading-engine/app/preflight/checks.py:49` reads the same literal. **No deployed container and no host path satisfies it** — trading-engine has no `/data` mount, the DB exists nowhere. The harness shipped 2026-05-19 and has **never executed once**: zero isolation runs, zero `run.json`, zero PSR artifacts.
- Trade rate since clean epoch (2026-08-12T13:47:20Z): **2 round trips in 8 days** (SOLUSDT LONG +0.251, BNBUSDT LONG −0.030, both MAX_HOLD exits). PSR-CI needs ≥30 per-trade observations (`psr_ci.py:188-191`) → **~4 months wall-clock at this rate.** Accepted; the deliverable is running discipline, not a verdict.
- carry-ins `DO_NOT_FLIP` is structural in paper mode: the `trading_mode` preflight check FAILs by design when `TRADING_MODE=PAPER`. This is intended semantics — documented, not changed.

### 3.2 Deliverables

1. **DB path fix.** `TOURNAMENT_DB_PATH` env var (default preserving the current literal), read by both `run_evidence_loop.py` and `checks.py`. Compose bind-mounts one host directory into trading-engine so host scripts and the in-container check see the same file. No account-size or gate constants touched.
2. **Epoch filter codified.** Clean-paper analyses filter `opened_at >= '2026-08-12T13:47:20Z'` AND exclude the 2 post-epoch legacy sweep closes (13:47:27/35Z). Codified as: a named constant in `scripts/forward_paper_test/` + a SQL view (`clean_epoch_positions`) created by boot DDL, so no analysis ever re-derives the WHERE clause.
3. **First isolation run started.** Flag: **`prefer_maker_orders`** — pinned here because battery #3's maker re-gate showed maker execution roughly halves the cost floor; it is the only flag with fresh evidence motivating it. Baseline capture uses the epoch window as-is (2 trades is a thin baseline; the run records that honestly rather than waiting).
4. **Daily cadence automated + staleness tripwire.** Daily `run_evidence_loop` invocation (host cron under WSL; mechanism finalized at plan time). The loop writes a last-run marker; `check_collection_gaps.py` (or a sibling check) alarms if the marker is >48h stale. Zero-runs-in-3-months must be impossible to repeat silently.
5. **Evidence unit unchanged.** Per-trade returns, 30-observation floor, `psr_ci_low > 0` publish gate — all stand. No redefinition to daily returns (rejected option; would change the statistical claim).

### 3.3 Success criteria

- `tournament.db` reachable by both consumers (proved by one preflight check pass + one loop run against the same file).
- ≥1 isolation run recorded with `run.json` under `.planning/evidence/forward_paper_test/`.
- Daily loop automated; tripwire demonstrably fires on a simulated stale marker.
- Epoch view exists and returns exactly the clean-epoch rows (paste the SELECT).

## 4. Stream 2 — debt cleanup

### 4.1 Bounded-smalls batch (days 1–2, parallel with Stream 1)

| Item | Fix | Pinned decision |
|---|---|---|
| pairs_trading 11 test failures | pandas 3 `freq='H'` → `'h'` | Fix **all 6 sites**: 2 collected (`tests/strategies/test_pairs_trading.py:43,142`) + 4 latent (`app/utils/statistical/tests/test_cointegration.py:53,63,80,103`) |
| connector-envelope 2 failures | stale mocks in `tests/integration/test_connector_contract.py` | mock `check_position_limits` returning 2-tuple; make `engine.client` awaitable |
| RES-11 format churn | add `[tool.ruff]` `line-length = 100` (+ isort agreement) to `pyproject.toml` | Config fix only; verify by editing a Python file and grepping the diff for churn |
| RES-12 duplicate retention job | operator one-liner `SELECT delete_job(1001);` (verified still live: jobs 1000+1001 identical) | **One-liner only**; boot-DDL single-worker hardening filed as follow-up, out of scope |
| TA `test_comprehensive_80.py` 2 failures | update tests to expect fail-loud fetcher (raises on empty/<30 candles per `app/fetcher.py:222+`) | In scope — same stale-test-vs-fail-loud class |

Expected result: trading-engine host suite 13 known-red → 0 unexplained red; TA 2 → 0. This is what makes Phase 19 verification cheap — "did I break something" becomes a yes/no question again.

### 4.2 Mediums (trail into Phase 19 gaps; drop without guilt if window closes)

- **Conftest collision** (`tests/edge_lab/` + `tests/killtests/` cannot share one pytest invocation): requirement = both suites runnable standalone **and** combined, CLI unchanged. Leaning: extract shared helpers into a real importable module and stop `from conftest import …`; mechanism finalized at plan time.
- **`validate_risk_limits.py` residual tautologies** (stop-loss expected-equals-same-formula `:440-512`, 3 unconditional-PASS leverage checks `:592-606`, emergency-stop endpoints asserted without any request `:640-655`): **delete the tautological sections.** A check that cannot fail is worse than no check. Replace with a real assertion only where one is cheap.
- **RES-10**: make the in-container gateway-test rule true — Dockerfile `COPY tests/` (+ conftest deps) so `docker exec … pytest` works; repair `test_tournament_snapshots.py`'s `Path.stat` monkeypatch RecursionError; update `.claude/rules/testing.md` to match the now-true reality.
- **RES-09** (PM trade history in-memory only): genuine design fork — hydrate PM from the shared `trades` table vs proxy the engine's history endpoint. Leaning: **hydrate from DB** (services already share postgres; a runtime proxy adds a synchronous dependency on engine availability for a read path). Needs its own mini-design at plan time; last in priority.

## 5. Stream 3 — Phase 19 reframed: Order-Path Consolidation + Reconciliation (~2.5 weeks, main block)

### 5.1 Why the reframe (recorded so ROADMAP amendment has a basis)

Scan findings (2026-08-20): the planned RECON-01/02 target a path that cannot run and isn't the runtime path.

- `app/exchanges/BybitAdapter` — where `orderLinkId` already passes through and is **already retry-stable** (payload built once at `bybit_adapter.py:628-639`, before the retry loop) — has **zero imports outside its own package**. Phase 18 fixed code nothing calls.
- The runtime LIVE path is `live_trading.py` raw httpx: no `orderLinkId`, no retry, marks orders unconditionally FILLED at reference price (`:176-224`); maker flow infers "no longer open == filled" (`:389-393`). And `LiveTradingEngine.__init__` unconditionally raises (2026-08-17 fence) — the path is unconstructible.
- Paper fills are synchronous (`paper_trading.py:340-342`) — nothing to reconcile in paper mode.
- No orders table exists; in-flight orders die on restart. `adapter.get_order_status` queries only `/order/open`, so a filled order raises `OrderNotFoundError` — fill and cancel are indistinguishable today.

Executing the phase as written would produce reconciliation for dead code. The reframe makes the adapter canonical first, then builds reconciliation on it, verified in tape mode.

### 5.2 Scope (ROADMAP/REQUIREMENTS amendment is the phase's first commit)

1. **Consolidation (new requirement, CONSOL-01).** `BybitAdapter` becomes the single order-submission path. `live_trading.py`'s raw-httpx submission/maker code is replaced by adapter calls or deleted. **The constructor fence stays** — consolidation changes what the path *would* do, never whether it can run. Nothing in this phase touches live-enablement config, the four-flag sequence, or the kill switch.
2. **RECON-02 — deterministic `orderLinkId`.** Generator `f"{strategy_id}-{symbol}-{side}-{monotonic_seq}"`; `monotonic_seq` persisted (DB-backed) so restarts never reuse a sequence number. Pass-through adapter→connector→Bybit already exists; the deliverable is the generator + a tape-mode test proving the same id is reused across the 5xx-retry window. Coordinate with Phase 20's monotonic paper-ID requirement — one sequence design, not two.
3. **Minimal orders table.** `order_id`, `order_link_id`, `symbol`, `side`, `status`, `created_at`, `updated_at`. In scope because it is the substrate of reconciliation: without persisted local state, a recon loop after restart has nothing to reconcile against. Not an order-management system — the minimum for the state machine.
4. **RECON-01 — reconciliation loop.** **Poll-based** (pinned: connector has zero WS consumers; a private-WS build-out is its own phase and is out of scope). Polls `/order/open` + `/order/history`, compares against the orders table, emits `ORDER_RECONCILE local=X remote=Y action=Z` logs, drives the state machine. Integration test against Phase 18 tape stubs.
5. **Fill-vs-cancel distinguishable.** `get_order_status` extended to consult order history when not found in open orders; the maker flow's "not-open == filled" inference replaced by reconciled status.
6. **State machine.** Wire or replace the existing unwired `trading_enhancements/order_state_machine.py` (currently stats-only) — decided at plan time; either way `services/trading-engine/docs/order_state_machine.md` ships (RECON-01 doc deliverable).
7. **Out of this phase:** `sync_positions_with_exchange` (zero callers, log-only) stays unwired — positions already rehydrate fail-loud from DB; filed as a note, not fixed here. Paper-fill `PAPER_{sym}_{side}` id collision = Phase 20 scope, untouched.

### 5.3 Verification

Tape-mode integration tests for submission-retry-reuse, recon actions, and fill-vs-cancel; four-proof standard for any deployed service change (live log line, downstream effect, DB row pasted, restart after config change); explicit negative proof that `LiveTradingEngine` still refuses to construct after consolidation.

### 5.4 Workflow

Phase 19 runs through GSD (`/gsd:plan-phase` → `/gsd:execute-phase`) on its own branch. This spec feeds the phase's CONTEXT; the poll-vs-WS and canonical-path decisions are pinned here so plan-phase doesn't re-litigate them.

## 6. Hard rules (inherited, non-negotiable)

1. Account is $100 via `shared.account`; money rules apply to every touched file.
2. LIVE stays mechanically blocked and fenced; nothing here changes live-path config, the 2% LIVE cap, or kill-switch semantics.
3. No gate weakening anywhere: DSR 0.95, PSR-CI floors, publish gates, pre-registration discipline all stand. Costs only go up.
4. No battery #4, no tuning of killed candidates, no ML re-enable.
5. Every "shipped" claim follows the four-proof standard; REJECT/failure outcomes are recorded, not massaged.

## 7. Timeline sketch

| When | What |
|---|---|
| Day 1–2 (08-20/21) | Stream 1 plumbing + Stream 2 smalls batch; 48h acceptance check (08-21 17:30 UTC) |
| Day 3–18 | Phase 19: plan-phase → execute waves → review/verify; debt mediums in gaps; evidence loop accrues daily in background |
| ~09-08 | Window close-out: suite status, evidence accrual count, Phase 19 verification |
| ~09-09 | Phase C gate check (21 gap-free days) → Phase C microstructure-battery manifest work begins if PASS |

## 8. Success criteria (whole window)

- Collection: 48h acceptance PASS recorded; no gap incident unresolved; Phase C gate checkable by script on 09-09.
- Evidence: harness runs end-to-end on a reachable DB; ≥1 isolation run recorded; daily automation + staleness tripwire live; epoch view codified.
- Debt: 15 known-red tests (13 TE + 2 TA) → 0 unexplained; ruff churn gone; duplicate retention job gone.
- Phase 19: single order path (grep proves no raw order POST outside the adapter), deterministic persisted-sequence `orderLinkId` with retry-reuse test, recon loop with `ORDER_RECONCILE` logs passing tape-mode integration tests, fill-vs-cancel distinguishable, state-machine doc shipped, fence intact.

## 9. Out of scope

Battery #4 (klines), Phase C candidate design (gated on data), private-WS order channel, liquidation ingest, live enablement, ML re-enable, sentiment revival, RES-12 boot-DDL hardening, `sync_positions_with_exchange` wiring, Phase 20 paper-ID collision, frontend changes.

## 10. Risks / open questions

1. **Trade-rate risk**: at ~1 entry-pair per 4 days, the evidence stream may show near-zero accrual even by 09-09. Accepted and disclosed; the alternative (loosening confidence gates to trade more) is gate-weakening and is forbidden.
2. **Phase 19 consolidation touches money code** — every step through `.claude/rules/money.md`, engine-surgeon-style narrow diffs, tests first.
3. **WSL cron reliability** for the daily evidence loop is unproven; the staleness tripwire exists precisely because the scheduler may silently die (the kline collector precedent).
4. **RES-09 and conftest mechanisms** deliberately deferred to plan time — bounded decisions, not design gaps.
