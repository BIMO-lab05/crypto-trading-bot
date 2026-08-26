# Report Error Repair — 2026-08-18

Approved design (session 2026-08-18). Scope: errors surfaced by the 2026-08-17/18 daily
reports and current service logs, plus landing the finished-but-uncommitted WS1-B work.

## Findings

1. **Trade-history 500** — `GET /api/v1/trading/trades/history` fails with
   `'Position' object has no attribute 'id'`. Root causes in
   `services/trading-engine/app/handlers/performance_dashboard.py`:
   - `pos.id` (line ~947): DB model `app/database/models.py` uses `position_id` as PK.
   - `position_repo.get_positions_by_status(...)` (line ~927): method does not exist in
     `app/repositories.py` — the `status=ALL` path always crashes.
   This endpoint is what the nightly daily-report script calls; every daily summary's
   "trade history unavailable, best/worst=0" note traces here.
2. **TA 500 on `interval=invalid`** — market-data returns 400; TA advanced-indicator
   handlers (stochastic/ATR/ADX) surface it as 500. Should be a 422 client error.
3. **WS1-B dormant-strategy precision work** — implemented in working tree, 12 new tests
   green, uncommitted.

Explicitly out of scope: portfolio-manager↔trading-engine sync ReadTimeouts (transient,
self-healing); edge-battery 4× REJECT (verdicts, not defects).

## Design

1. **trading-engine**: use `pos.position_id`; replace the phantom `get_positions_by_status`
   call with existing lenient display reads (ALL = open-or-empty + closed). Regression
   test covers ALL/OPEN/CLOSED paths against a stub repo. Redeploy; prove with a live
   200 and populated trades.
2. **technical-analysis**: validate `interval` against the service's accepted set at the
   handler layer; unknown values return 422 before any upstream fetch. Test added.
   Redeploy.
3. **Commit WS1-B dormant work** as its own conventional commit on
   `fix/ws1a-technical-analysis-correctness`.

Verification: host tests green per suite; both images rebuilt (BuildKit off) and
containers recreated; live curl of the failing endpoints shows 200 / 422 respectively.
