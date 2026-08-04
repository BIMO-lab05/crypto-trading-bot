# Comprehensive Fix Session — 2026-07-28

Full audit + repair of the trading engine, technical-analysis service, and
frontend, driven by three findings: the system was losing trades, the frontend
threw errors, and the TA service produced garbage signals.

**Headline: the paper book's cash accounting was so broken that results were
uncorrelated with strategy quality.** Every stop-loss exit silently opened a
full-size OPPOSITE position; winning SHORTs were booked as losses; take-profit
exits never returned cash to the balance. On top of that, every indicator was
computed over testnet-polluted candles (BTC @ $1.76M in the klines table).
Any strategy would have "lost" under those conditions.

---

## 1. Trading engine — critical accounting fixes

| # | Bug (verified in code) | Fix |
|---|---|---|
| 1 | **Stop-loss exits opened opposite positions.** After a filled engine close, `_close_position_with_limit_order` called `close_position` again → ValueError → misread as "limit failed" → market fallback → paper engine ignored `reduce_only` and opened a full-size counter-position with default stops. Every SL/trailing exit = stop + random counter-trade. | Paper engine now honors `reduce_only` (rejects instead of flipping) and `position_id`; the close paths never double-close. (`paper_trading.py`, `auto_trader.py`) |
| 2 | **SHORT cash accounting inverted.** Closing a SHORT credited `close_notional − commission`: a winning short REDUCED the balance, a losing short increased it. Leveraged LONG closes credited full notional while opens deducted only margin. | All closes credit `margin_returned + realized_pnl − commission`, both sides, any leverage. (`paper_trading.py`) |
| 3 | **Winning exits never paid out.** `_close_position` (take-profit / TP3 / max-hold path) marked positions closed WITHOUT any cash movement — margin + profit vanished from the book on every winner. | All closes route through the engine, which credits cash. (`auto_trader.py`) |
| 4 | **Partial exits (TP1/TP2) moved no cash** and P&L was overwritten at final close (double counting). | Engine-routed reduce-only partial closes with proportional margin+P&L credit; `close_position` realizes on remaining quantity and ACCUMULATES realized P&L. (`auto_trader.py`, `position_manager.py`, `models/position.py`) |
| 5 | **Kill switch measured cash, not equity** → opening one position (margin −10%) looked like an instant 10% "daily loss" ≥ the 5% trigger. And the consecutive-loss breaker was unreachable: every position OPEN reset the loss streak. | Kill switch fed equity; streak only updates on closes (`is_trade_close=True`). (`kill_switch.py`, `auto_trader.py`) |
| 6 | **48h max-hold close raised TypeError on every invocation** (invalid kwargs) and in LIVE would have OPENED an opposite exchange position. | Routes through `_close_position` (paper: engine reduce-only; LIVE: `live_engine.close_position`). (`auto_trader.py`) |
| 7 | **LIVE mode had NO working stop-loss path** — it deliberately raised RuntimeError and the position stayed open forever. | LIVE stop-loss exits now route through `LiveTradingEngine.close_position` (market, reduce-only). A true LIMIT-IOC close remains a TODO. (`auto_trader.py`) |
| 8 | **"Daily" loss cap was actually lifetime** (`reset_daily_pnl` had no caller) and reset on restart. | Auto-rolls on UTC date change. (`risk_manager.py`) |
| 9 | **Consensus gate counted HOLD votes** — 2 BUY + 3 HOLD passed a min-consensus-3 BUY gate. | Consensus = count of indicators voting the CHOSEN direction. (`aggregation/aggregator_core.py`) |
| 10 | **Per-trade cap starved the research/hybrid path** (symbol allocations 25–30% always exceeded the 10% cap → 100% rejects; only weaker-gated paths traded), and the 10% paper relaxation silently carried into LIVE. | Cap now CLAMPS size instead of rejecting; hard non-configurable 2% cap in LIVE (ADR-010). (`auto_trader.py`) |
| 11 | **Default ("standard") trade path had NO side gates** — `allowed_trade_sides`, `short_trading_enabled`, `short_min_confidence`, and the per-trade cap only existed on the research/hybrid path. | Gates added to the default path. (`auto_trader.py`) |
| 12 | **DCA safety orders opened DUPLICATE positions** with their own default stops instead of averaging in. | Engine scale-in: weighted-average entry on the SAME position. (`paper_trading.py`, `position_manager.py`, `auto_trader.py`) |
| 13 | **VP (volume-profile) mode never traded** — TypeError on an unexpected kwarg, swallowed by a catch-all. | `get_trading_signal_with_vp` accepts `regime_analysis`. (`signal_aggregator.py`) |
| 14 | **Mean-reversion leg risked 1.5R to make 1.0R** (inverted R/R — selected by the hybrid router whenever ADX<25). | Stop at 0.75× distance-to-mean (R/R ≈ 1.33). See §4 for backtest validation. (`strategies/mean_reversion_strategy.py`) |
| 15 | **Kelly sizing ran on fabricated stats** — `PerformanceTracker.add_trade` was never called, so sizing always used the optimistic fallback (50% WR). | Every close now feeds the tracker. (`auto_trader.py`) |
| 16 | **Exit checks could act on corrupt prices** (see §2) at fantasy levels. | Monitor-loop price sanity guard: skip the cycle if price moved >2×/<0.5× vs last known. (`auto_trader.py`) |
| 17 | Restart balance sync deducted full notional (inconsistent with margin-only opens); close notifications always showed +0.00%. | Margin-consistent sync; `pnl_percentage` reports realized P&L for closed positions. (`paper_trading.py`, `models/position.py`) |

## 2. Data integrity (root cause of "TA not working well")

The 2026-04-25 testnet→mainnet flip left testnet candles (BTC @ $1,759,541) in
TimescaleDB, and the `is_mainnet` migration tagged those old rows
`is_mainnet=true` — so the filter filtered nothing. That is exactly what
produced the logged `MACD 428 vs Signal 43171` and SELL-conf-1.0 signals.
The MACD math itself was verified correct; the input data was poisoned.

- **`scripts/repair_testnet_pollution.sql` + `.sh`** — one-time DB repair:
  demotes pre-flip rows and >5× price outliers. **RUN THIS FIRST** (see §5).
- `market-data-service`: `get_latest_kline` now also filters `is_mainnet`;
  still-forming candles are dropped at ingest (no more repainting signals).
- `technical-analysis` fetcher: requests mainnet-only, validates candles
  (drops OHLC-invalid rows and >35%-per-bar jumps), drops the unclosed
  candle, and refuses to compute on <30 valid rows.
- Interval fix: daily candles are stored as "D" but TA requested "1440" → the
  1d leg of multi-timeframe consensus silently returned 0 rows for months.
  Now normalized.

## 3. Signal quality fixes (TA service)

- **Aggregated-signal confidence structurally capped ~0.47** (HOLD votes
  diluted the denominator, and the 0.6 threshold made near-permanent HOLD).
  Directional confidence is now agreement-among-directional-voters.
- **MACD confidence** rewarded corruption (|hist|/|macd| → 1.0 exactly at
  crossovers/garbage). Now scaled by price (0.2% of price = full confidence).
- **SMA/EMA** emitted SELL conf 1.0 on polluted data; >30% price-vs-MA gaps
  are now treated as data errors (HOLD conf 0).
- **Bollinger** strong-BUY zone had an inverted/discontinuous confidence
  curve (edge of "strong" zone scored 0.4 vs 0.68 just outside). Monotone now.
- **MACD parameter drift**: trading-engine requested 8-17-9 while TA's
  documented default is 5-35-5. Single source of truth restored.
- TA Dockerfile was unbuildable (missing `COPY requirements.txt`) — the
  running container could never pick up fixes. Fixed.

## 4. Frontend fixes

- Command palette (⌘K) trading controls called `/api/api/...` → 404 on
  Start/Stop/Emergency-stop. Fixed.
- One failing symbol blanked the whole signals tile every 5s
  (`Promise.all` → `allSettled`).
- Buy/sell sent a JSON body where the gateway requires query params
  (422 on every call) and never sent `price`. Fixed.
- WebSocket wrote a wrong-shaped payload into the portfolio cache,
  corrupting the Portfolio page between polls. Now invalidates instead.
- Performance page crashed (`trades is not iterable`) on enveloped API
  responses. Array guards added.
- Console-noise flood (per-poll logs + unthrottled error logs across 5 axios
  instances) throttled/removed; Phase1Dashboard now shares the main API client.
- `eslint-plugin-react-hooks` was referenced but not installed → lint aborted.
  Added to devDependencies.
- Gateway: multi-timeframe route now forwards `timeframes`; ML model route
  default fixed LSTM→GRU (LSTM was deleted).

## 5. What YOU need to run on your machine (in order)

```bash
# 0. (once) install the new frontend dev dep
cd frontend && npm install && cd ..

# 1. REPAIR THE DATABASE (removes testnet-polluted candles) — do this before
#    trusting any signal or backtest:
bash scripts/repair_testnet_pollution.sh

# 2. Rebuild + restart the changed services (stale in-memory state = false pass):
DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml up -d --build \
  trading-engine technical-analysis market-data api-gateway frontend

# 3. Standalone verification harnesses (no deps beyond pandas/numpy/pydantic):
cd services/trading-engine  && python3 tests/standalone/test_accounting_fixes.py   # 28 checks
cd ../technical-analysis    && python3 tests/standalone/test_indicator_fixes.py    # 16 checks

# 4. Full service test suites (inside containers, per CLAUDE.md):
docker exec crypto-bot-trading pytest tests/ -x -q
docker exec crypto-bot-api-gateway pytest -q

# 5. Frontend build + lint:
cd frontend && npm run build && npm run lint
```

## 6. Validation evidence produced in this session

- **28/28 accounting checks pass** (`services/trading-engine/tests/standalone/
  test_accounting_fixes.py`): LONG/SHORT round trips, reduce-only rejection,
  partial closes, scale-in, leverage math, kill-switch semantics, daily
  rollover, position-targeted closes.
- **16/16 TA checks pass** (`services/technical-analysis/tests/standalone/
  test_indicator_fixes.py`): MACD magnitudes + confidence, candle validation
  (drops the exact 1.76M BTC artefact), MA guards, Bollinger monotonicity,
  interval normalization, directional confidence.
- **Mean-reversion R/R fix backtested** on cached Bybit 90d hourly data
  (BTC/SOL/ADA/BNB, ADX<25 regime filter, fees+slippage):
  aggregate bleed cut from −92.9% to −67.5% summed across symbols, profit
  factor up on 3/4 symbols. ⚠️ **Honest caveat: even after the fix, the naive
  mean-reversion entry is still negative-expectancy on that (strongly
  trending) sample.** Recommendation: keep the MR leg small or disabled until
  it passes a walk-forward test on repaired, current data — the full entry
  filter stack (RSI+BB+volume) is stricter than this replay, but the burden
  of proof is on the strategy. Reproduce with
  `python3 backtesting/validate_mr_rr_fix.py`.

## 7. Known remaining work (deliberately not done here)

1. LIVE limit-IOC reduce-only close (interim: market reduce-only close).
2. `tickers` table has no `is_mainnet` column — pre-flip ticker rows can't be
   tagged without a migration (repair script skips them safely).
3. Several old test suites remain `pytest.mark.skip` ("stale after PR #86") —
   the new standalone harnesses cover the rewritten accounting; un-skipping
   and rewriting those suites is follow-up work.
4. Redis caching for TA (config exists, unused) and moving CPU-bound indicator
   math off the event loop.
5. Strategy-level profitability: with accounting and data now truthful, run
   2–4 weeks of paper trading and evaluate with the DSR/CPCV tooling before
   any live-mode discussion. **No system change here guarantees profits.**
