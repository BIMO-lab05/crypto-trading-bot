# Edge-Search v2 — Design Spec

**Date:** 2026-08-19
**Status:** Approved design, pending user spec review
**Branch:** work continues on `fix/ws1a-technical-analysis-correctness` lineage (new branch per phase at plan time).

## 1. Why this exists

Every kline-based signal family in this repo is dead. Batteries #1 (2026-08-17) and #2 (2026-08-18) killed `xs_momentum`, `lf_trend`, `funding_carry`, `pairs_statarb`, `vol_breakout`; H3/H4 ensembles died earlier (Phase-0 killtests). The 2026-08-19 gap audit and engine repairs (`b00e368`..`714a409`) then re-confirmed on an honest engine: baseline walk-forward 5/5 REJECT, DSR 0.000. The problem is not a bug or a config — it is that the raw material (hourly klines + funding) contains no edge this account can harvest at a 21–31bp round-trip cost floor.

Two honest moves remain, and this spec does both:

1. **Acquire new raw material** — orderbook depth and open interest, the only data classes Bybit offers that this repo has never collected. Data must accrue for weeks before it can be tested, so collection starts first.
2. **Exhaust the cheap remaining questions on existing data** while collection runs — an intraday-seasonality battery, and a maker-only re-gate that answers whether any prior REJECT was purely a cost artifact.

Explicitly NOT the premise: "find the hidden bug." That search is complete (`audit/FINDINGS-GAP.md`). A REJECT outcome from every part of this spec is a valid, expected result; the deliverable is verdicts and accruing data, not profit.

## 2. Phase A — data pipeline (build first; data accrues from day one)

### A1. Orderbook snapshot collection

- **Connector:** `services/bybit-connector` already exposes `get_orderbook(category, symbol, limit)` (`app/bybit_rest_client.py:620`, REST `/v5/market/orderbook`). No connector change needed for A1.
- **Collector:** new scheduler job `collect_orderbook_data` in `services/market-data-service/app/scheduler.py`, mirroring the existing `collect_ticker_data` pattern (same ownership claim, same error handling, same manual-trigger surface).
  - Symbols: the service's configured trading pairs (the 5 validated: BTC, ETH, SOL, BNB, ADA).
  - Cadence: **every 5 seconds** per symbol.
  - Depth: top **25** levels per side (connector default).
- **Storage:** the existing, currently empty `orderbook_snapshots` table in TimescaleDB `market_data`. Persist: `symbol`, `timestamp` (exchange ts, UTC), best bid/ask, and the full 25×2 ladder as JSONB (`bids`, `asks` arrays of [price, size]). Confirm/convert to hypertable; add a **90-day retention policy**.
  - Volume estimate: ~17,280 snapshots/day/symbol × 5 symbols ≈ 86k rows/day. JSONB ladder ≈ 1–2 KB/row → ~10–15 GB at 90d retention. Acceptable; retention policy is the guard.
- **Rate limits:** 5 symbols / 5s = 1 req/s to a public endpoint (Bybit public limit ≥ 10 req/s) — comfortable margin. Job must skip a tick rather than queue if the previous tick is still running.

### A2. Open-interest collection

- **Connector:** new method `get_open_interest(category, symbol, interval_time="5min", limit=...)` on `BybitRestClient`, REST `/v5/market/open-interest`. Public endpoint, no auth.
- **Collector:** new scheduler job `collect_open_interest_data`, cadence **every 5 minutes**, same 5 symbols.
- **Storage:** new table `open_interest` (`symbol`, `timestamp` UTC, `open_interest` numeric, `open_interest_value` numeric when provided). Hypertable, retention 730d (tiny table — one row/5min/symbol).
- Backfill: on first run, pull the endpoint's maximum history window per symbol (Bybit serves limited lookback; whatever it returns is recorded — no synthetic backfill).

### A3. Liquidations — explicitly deferred

Bybit serves liquidations only via WebSocket (`allLiquidation` topic). Persisting a WS stream is a materially bigger build (reconnect, dedupe, gap accounting) and is **out of scope**. Recorded as a follow-up candidate, nothing more.

### Phase A verification (repo standard — all four proofs)

1. Live mainnet URL visible in market-data-service logs for both new jobs.
2. `SELECT count(*), min(timestamp), max(timestamp) FROM orderbook_snapshots / open_interest` pasted, showing rows for all 5 symbols.
3. Service restarted after config/schema change (stale in-memory config is the repo's #1 false pass).
4. 48-hour gap check: no inter-snapshot gap > 60s (orderbook) / > 15min (OI) per symbol, measured by SQL and pasted. The kline collector once silently died for weeks — the gap check is the tripwire, and it should be re-runnable as a script (`scripts/` or `audit/`).

## 3. Phase B — interim batteries on existing klines (parallel with A)

Both candidates run through the existing `backtesting/edge_lab/` kill-funnel unchanged: gate1/gate2, DSR ≥ 0.95, CPCV (10 groups, 2 test, 1% embargo), hurdle 2.0×, min positive path fraction 0.70, `shared.account` capital. **Pre-registration first**: a battery #3 manifest (like `battery_2026-08-18_manifest.md`) is committed before any candidate code, and the trial ledger is appended so n_trials keeps growing honestly (currently 30 ledger entries + the 2026-08-19 baseline walk-forward).

### B1. Battery #3 manifest

Pins: universe (`universe_2026-08-17.json` top-30 unless staleness check fails), cost tables, clean-data epoch (≥ 2026-04-25), candidate list (B2, B3 variants), and the exact gate constants read live from `edge_lab/config.py`. Committed before implementation.

### B2. Candidate: intraday seasonality

- **Hypothesis:** systematic hour-of-day or funding-window (00:00/08:00/16:00 UTC) return patterns in perps, driven by funding-settlement positioning flows.
- **Implementation:** new `backtesting/edge_lab/candidates/intraday_seasonality.py` following the existing candidate module shape (`xs_momentum.py` as template). Variants (pre-registered, no post-hoc additions): (a) pre-funding-window drift long/short, (b) hour-of-day long at historically strongest hour vs short at weakest, computed on a rolling in-sample window — no full-history stats (leakage rule).
- **Expected outcome:** fast REJECT — heavily arbed effect. Cheap to ask; the verdict is the deliverable.

### B3. Candidate mode: maker-only re-gate of the 6 killed candidates

- **Question answered:** were any of the REJECTs (`xs_momentum`, `lf_trend`, `funding_carry`, `pairs_statarb`, `vol_breakout`, baseline) purely artifacts of the taker cost floor?
- **Maker fill model** (new, in edge_lab's cost layer — costs may only ever go up in realism, never down in rate-fudging):
  - Fee: maker 2bp/side (from `shared.account.MAKER_FEE_PER_SIDE` / costs model — never a literal).
  - Fill rule: a limit entry at bar *t*'s close fills only if bar *t+1* **trades through** the level (its range extends beyond the limit price, not merely touches it). No touch-fills — the gap audit documented touch-fill as a phantom-profit source.
  - Unfilled entry = missed trade (signal expires after 1 bar). Missed trades are counted and reported — a strategy that only "works" on the fills it misses is a fill-model artifact.
  - Exits: stops remain taker (conditional stops trigger as market orders — engine fix `714a409` semantics); take-profits may be maker.
- **Gates unchanged.** Same DSR/CPCV thresholds. Result recorded per candidate in the trial ledger (each re-gate is a new trial — n_trials grows by 6).

## 4. Phase C — microstructure battery (gated, ~4 weeks out)

- **Gate:** ≥ 21 consecutive days of orderbook data passing the Phase A gap check.
- Candidate design happens **then**, not now — pre-registering signal designs before seeing the data's actual shape (snapshot cadence achieved, depth stability, spread distribution) would just encode hope. This spec commits only to the gate and the process: battery #4 manifest, edge_lab funnel, same thresholds.
- Sketch of the plausible family space, for orientation only (not commitments): top-of-book imbalance drift, spread-capture viability given achieved queue assumptions, depth-slope regime filters for existing candidates.

## 5. Hard rules (inherited, non-negotiable)

1. Account is $10,000 via `shared.account` (changed from $100 on 2026-08-25 per ADR-029); money rules (`.claude/rules/money.md`) apply to every new file.
2. No gate weakening: DSR 0.95, CPCV params, hurdle 2.0×, pre-registration. Costs only go up.
3. No tuning of killed candidates beyond the pre-registered maker-mode re-run.
4. LIVE trading is blocked ONLY by the four deliberate flags (`PAPER_TRADING_MODE`, `TRADING_MODE`, mainnet trade keys, `LIVE_TRADING_ACK`); nothing in this spec changes live-path config. *(Changed 2026-08-25, ADR-029: at $10,000 the 2% LIVE cap is $200 and clears min notional, so the old arithmetic block no longer exists — the flags are the only barrier.)*
5. Every claim in battery reports cites executed output; REJECT verdicts are recorded in the trial ledger like always.
6. New collector code follows the four-proof verification standard before any "shipped" claim.

## 6. Deliverables summary

| # | Deliverable | Phase |
|---|---|---|
| 1 | `collect_orderbook_data` scheduler job + hypertable/retention on `orderbook_snapshots` | A1 |
| 2 | `get_open_interest` connector method + `collect_open_interest_data` job + `open_interest` table | A2 |
| 3 | Gap-check script (re-runnable) + 48h verification evidence | A |
| 4 | Battery #3 manifest (pre-registered) | B1 |
| 5 | `intraday_seasonality.py` candidate + funnel verdicts in trial ledger | B2 |
| 6 | Maker-fill mode in edge_lab cost layer + 6 re-gate verdicts in trial ledger | B3 |
| 7 | Phase C gate definition recorded in battery #3 manifest (data-readiness criteria) | C |

## 7. Success criteria

- Phase A: both tables filling for 5 symbols, 48h gap-free, four-proof verified.
- Phase B: ≥ 8 new ledger-registered verdicts (2 seasonality variants + 6 re-gates). PROMOTE or REJECT both count as success; unverdicted candidates do not.
- Phase C gate objectively checkable by script, no judgment call.

## 8. Out of scope

Liquidation WS ingest, sentiment-service revival, ML re-enable (`ENABLE_ML_PREDICTIONS` stays false), any live-trading enablement, frontend changes, parameter tuning of any killed candidate, new symbols beyond the validated 5 (collection) / pinned top-30 (batteries).

## 9. Risks / open questions

1. **Bybit OI history lookback** is limited (endpoint serves a bounded window) — OI-based candidates may need their own accumulation period like orderbook. Accepted; recorded at backfill time.
2. **5s REST snapshots are not a tick feed.** Microstructure signals needing sub-second resolution are out of reach of this pipeline; Phase C candidates must respect the achieved cadence. Disclosed now to prevent later scope drift.
3. **Disk growth on the NTFS/WSL mount** — retention policy is the control; the gap-check script also reports table size.
4. **Scheduler ownership**: market-data-service uses a scheduler-ownership claim (`scheduler.py:43`); new jobs must register under the same claim to avoid double-collection on multi-replica runs.
