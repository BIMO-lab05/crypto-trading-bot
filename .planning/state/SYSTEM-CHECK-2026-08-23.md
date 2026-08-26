# System Check — 2026-08-23 14:35 UTC

Read-only. Isolation window live (started 2026-08-20, harvest 2026-08-27). No state mutated.

## Verdict: system UP and TRADING. Two real defects, neither fatal to the harvest.

## 1. Liveness — PASS
- 16/16 containers healthy. RestartCount=0 on all.
- `crypto-bot-trading` + `crypto-bot-ta` recreated 2026-08-23T02:08Z (deploy of 2cd7e76/8a62a38). postgres/timescale/prometheus/harness up since 2026-08-22T14:07 (bind-mount outage fix).
- Auto-loop ALIVE: `is_running=true`, 1220 cycles, last_check 14:31:16Z. Kill switch absent, circuit breaker `closed`, kill_switch not tripped.
- **Recreation did NOT hole the window**: SOL position opened 01:42 (pre-recreate), stop-loss fired 05:00 (post-recreate). Monitoring survived.

## 2. Trading activity — 7-day drought BROKE
| when | symbol | side | conf | strategy | realized |
|---|---|---|---|---|---|
| 08-23 01:42 | SOL | BUY | 0.306 | ensemble | — |
| 08-23 05:00 | SOL | SELL | — | stop_loss_limit | **-0.3404** |
| 08-23 06:00 | ADA | BUY | 0.455 | ensemble | open |

ADA LONG open: entry 0.2151, now 0.2293, unrealized **+$0.653**. SL 0.2062 / TP 0.232.

## 3. Ledger — COHERENT (the +$177 break from 2026-08-04 is gone)
cash 100.25118662 | unrealized 0.6532 | realized 0.25118662 | total 100.90438662
`sum(trades.realized_pnl)` = 0.25118662 — **exact match** to cash delta. 
`realized_pnl` is **net of fees** (verified: SOL 9.311-9.641-0.01042 = -0.34042 = stored value exactly).

## 4. Fee accounting (descriptive — NOT an edge measurement)
50 trade rows ≈ 25 round trips since 2026-07-29. **fees $2.0858, net P&L +$0.2512.**
Gross-before-fees = $2.337; fees consumed **89%** of it. That ratio is the sound figure.
No per-trade edge is claimed: n≈25 round trips supports no inference, and CLAUDE.md §2 forbids
edge claims without DSR/CPCV. Net return +0.25% over 26 days.

## 5. DEFECT A — funnel has an uninstrumented 566-signal sink (observability)
Funnel: `passed_portfolio_heat` 567 passed → `order_intent_emitted` **1**. No stage attributes the other 566.

Cause, `services/trading-engine/app/auto_trader.py` — three `return` paths between the
`funnel.gate("passed_portfolio_heat")` call (:4925) and `funnel.gate("order_intent_emitted")` (:5047):
- `_passes_exposure_gate` fail → `total_trades_rejected += 1; return`  (~:4991)
- `_passes_min_notional` fail → `total_trades_rejected += 1; return`  (~:5014)
- `quantity <= 0` after qty_step snap → `total_trades_rejected += 1; return`  (~:5024)

All three bump the counter, none call `funnel.gate()`. Commit 42e2250 ("make funnel attribution real")
did not cover the sizing block. **Rejection behavior is CORRECT** (min-notional rejected, never clamped
up, per CLAUDE.md §1) — only the attribution is missing.

**Arithmetic does NOT close, and cannot from logs:**
- min-notional path: **204** rejects in the surviving log — the only demonstrated sink.
- `quantity <= 0` after qty_step: **0** occurrences.
- `_passes_exposure_gate`: **0** occurrences (it *does* `logger.warning` before returning False — verified
  in the function body — so zero lines means it never fired, not that it failed silently).
- Remaining ~362 of the 566 are **unattributable**: the container log was rotated and now begins at
  **07:47**, while the funnel window opens at **02:08** — 5.6h of evidence is gone.
Conclusion: min-notional is the only proven sink; whether it accounts for all 566 is undetermined.

## 6. DEFECT B — BTC/ETH burn 40% of every cycle for structurally impossible trades
197 min-lot rejects in 12.5h: **BTC 118, ETH 57, SOL 22**.
| sym | min lot | price | min notional | vs $10 cap |
|---|---|---|---|---|
| BTC | 0.001 | 77,424 | **$77.42** | 7.7x over — impossible |
| ETH | 0.01 | 2,454 | **$24.54** | 2.5x over — impossible |
| SOL | 0.1 | 93.11 | $9.31 | **blocked while any position is open** — see below |
| BNB | 0.01 | ~602 | $6.02 | ok |
| ADA | 1 | 0.229 | $0.23 | ok |
BTC+ETH are pure waste in the symbol loop — 40% of every cycle spent on trades that cannot exist.

### B2 — the tradeable set SHRINKS to {BNB, ADA} once ~10% of capital is deployed
Sizing reads `paper_engine.get_balance()` (auto_trader.py:4751) = **cash net of posted margin = $90.35**,
not equity $100.90. So the 10% cap yields 10% x $90.35 = **$9.035**, below SOL's $9.311 min notional
-> qty 0.097 -> floors to 0.0 -> the exact captured line `rejecting SOLUSDT: qty 0.0 below min 0.1`.

Falsified against the clock: SOL **filled** at 01:42 for $9.641 (no position open, balance ~$100.25,
10% = $10.02 > $9.311). All **22** SOL rejects occur later, with the ADA position open and
`balance $90.35` printed in every line.

Consequence: SOL is tradeable only from a flat book. **The isolation harvest will structurally
under-count SOL trades**, and the effective universe is {BNB, ADA} whenever anything is open.

## 7. Data integrity
- **60m (engine decision tf): 24/24 bars/day, zero gaps** across all 5 trading symbols since isolation
  start — *as the DB stands now*. NOT verified: whether the engine was reading complete data live during
  the 08-20/21/22 collector outages (backfill would hide that).
- **1m: holes still OPEN, never backfilled** — 08-20 (367min), 08-21 (687min), 08-22 (232min) = ~21.4h missing. Research/Phase-C concern only, not engine.
- All 16 symbols fresh (1-2 min lag). XRP/DOGE stale since 2026-05-15 (excluded symbols — expected).
- Phase C collectors LIVE: orderbook 613,455 rows, open_interest 18,634, both current. First data 2026-08-19 → gate ~2026-09-09.

## 8. Minor
- ADA exposure 10.45% vs 10% cap — mark-to-market drift on an entry sized at 9.89%, not a sizing violation. Flagged by `/api/risk/exposure` as `concentrated_positions`.
- Live readiness FAIL (expected: TRADING_MODE=PAPER). Carry-ins `DO_NOT_FLIP`, 5 open (OP-01..04, INFRA-02).
- Disk fine: /mnt/d 42%, / 3%. repo logs/ 8.9M. No rotation risk this window.
- Aggregator running hot on `Volume INSUFFICIENT → 0.5x penalty` + `category diversity 1/2` — the two dominant HOLD causes.
- **MTF degraded 1360x in 12.5h**: `Insufficient timeframes for multi-timeframe analysis, using primary only`.
  Signal quality is degraded *inside the isolation window*; the MTF leg is frequently not contributing.
- **Two different "balance" notions.** portfolio-manager `cash_balance` $100.25 does NOT net posted margin;
  the engine's sizing balance $90.35 DOES. Totals reconcile — not a ledger break — but **sizing reads $90.35**.
- **Docker log rotation is eating harvest evidence**: 5.6h of engine log already lost in a 12.5h window.
  By the 08-27 harvest, little log history will survive. No rotation policy configured.
- Router confirmed ADVISORY (`[HYBRID][ADVISORY] ... ensemble executes; router observing`).
- Uncommitted: `.claude/skills/trading-strategy-dev/SKILL.md`, `.planning/state/carry_ins.json`.
