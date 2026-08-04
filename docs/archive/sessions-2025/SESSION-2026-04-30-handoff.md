# Session Handoff — 2026-04-30

This document captures the state of the trading-bot project at end of the
2026-04-30 working session so the next session can pick up cold.

**TL;DR:** 17 commits shipped today across the V0 GRU finding, three Tier-1
trading-system improvements (T1.2 vol parity / T1.3 maker orders /
T2.3 funding gate), and the T0.2 evaluation harness foundation (PSR/DSR/CPCV).
Every new feature ships **default off** behind an env flag — paper-mode
behaviour is unchanged. Net new tests added today: ~88 passing.

---

## 1. What shipped today (chronological)

| # | Commit | Concern |
|--:|--------|---------|
|  1 | `c56765c` | fix(ml-prediction): correct directional_accuracy metric (look-ahead + degenerate ref) |
|  2 | `bf6fc4c` | docs(strategy): research plan + V0 evidence the GRU has no measurable edge |
|  3 | `2f29ca9` | fix(trading-engine): default `ENABLE_ML_PREDICTIONS=false` (no measured edge) |
|  4 | `fc3d9e9` | feat(trading-engine): add maker-order config flags (T1.3 prep, not yet wired) |
|  5 | `32d8805` | docs(strategy): T1.2 design doc — per-position vol parity |
|  6 | `c6cd5ae` | feat(trading-engine/risk): per-position vol-parity primitives (T1.2 chunks 1+2) |
|  7 | `9b62b1b` | feat(bybit-connector): expose funding-rate history and instruments-info |
|  8 | `2dba20d` | test(bybit-connector): fix stale assertion in test_get_kline_endpoint_with_params |
|  9 | `22b417f` | feat(ml-retraining): record honest skill-on-returns metrics on every train |
| 10 | `6ebebdc` | feat(risk-metrics): Probabilistic + Deflated Sharpe Ratio (T0.2 foundation) |
| 11 | `201526e` | feat(trading-engine): wire vol parity into auto_trader sizing path (T1.2 chunk 3) |
| 12 | `c3c89f6` | feat(trading-engine): wire T1.3 maker-order entry path with timeout fallback |
| 13 | `6f723c5` | fix(trading-engine): live_trading.py connector-shape parsing and Order construction |
| 14 | `1a94c69` | feat(trading-engine): T2.3 funding-rate gate on perp entries (default off) |
| 15 | `007a740` | fix(trading-engine): drop dead retCode arms in adapters facing bybit-connector |
| 16 | `f5ca632` | docs(strategy): T0.2 CPCV harness design plan |
| 17 | `da10409` | feat(risk-metrics): T0.2 CPCV harness with DSR bridge |

---

## 2. The V0 finding (most important context for tomorrow)

**Production GRU models have no measurable edge on log-returns and roughly
coin-flip directional accuracy.** The 79–84% directional-accuracy numbers
in `progress.md` from the 2026-04-26 session were a metric bug —
`y_test[:, -1]` referenced a future bar, leaking the answer.

After fixing the bug (commit `c56765c`):
- **Directional accuracy on returns** drops to ~50% (chance level).
- **R² on returns** is *negative* — naive persistence (next return = current
  return) beats the GRU on every symbol.

The original "R² ≈ 0.99 / Dir.Acc ≈ 79%" numbers measured *predicting price
levels at high autocorrelation*, which any persistence model passes. They
do **not** indicate trading skill.

**Consequences:**
- `ENABLE_ML_PREDICTIONS=false` is now the trading-engine default (commit `2f29ca9`).
- All hands-on evaluation should now go through the new PSR/DSR/CPCV stack
  (`services/risk-metrics-service/app/sharpe_metrics.py` + `cpcv.py`).
- Don't trust raw R² or Dir.Acc on price level for any model going forward —
  only `r2_returns` and the leak-corrected `dir_acc_corrected` (now also
  emitted by ml-retraining-service per commit `22b417f`).

**Reproducible evidence:**
- `docs/strategy/research-2026-04-29/V0-FINDINGS-gru-metric-bug.md` — what the bug was
- `docs/strategy/research-2026-04-29/V0-RESULTS-no-edge.md` — measured numbers
- `docs/strategy/research-2026-04-29/persistence_shootout.py` — script to re-run
- `docs/strategy/research-2026-04-29/V0-PERSISTENCE-results.json` — last run output

---

## 3. Feature flags — current defaults (everything below is OFF)

These flags exist in `services/trading-engine/app/config.py` and **all
default to off**. Paper-mode behaviour is identical to before this session.
Opt in one at a time, after a forward-paper-test.

| Flag | Default | Where wired | Test gate before turning on |
|------|--------:|-------------|-----------------------------|
| `ENABLE_ML_PREDICTIONS` | `false` | technical-analysis aggregator | Stays off until V0 follow-up GRU rebuild lands |
| `ENABLE_VOL_TARGETING` | `false` | `auto_trader._execute_trade_with_setup` | Forward-paper-test ≥7 days |
| `vol_target_annualised` | `0.30` | (ditto) | n/a |
| `vol_estimator_window_bars` | `168` | (ditto) | n/a (7d hourly) |
| `vol_target_cap_multiplier` | `1.0` | (ditto) | 1.0 = downside-only; safest |
| `PREFER_MAKER_ORDERS` | `false` | `live_trading.execute_maker_order_with_fallback` (LIVE only) | LIVE-mode-only forward-paper-test |
| `maker_quote_timeout_seconds` | `30` | (ditto) | n/a |
| `maker_fallback_to_taker` | `true` | (ditto) | Keep true unless we want to hard-skip on no-fill |
| `ENABLE_FUNDING_GATE` | `false` | `auto_trader._execute_trade_with_setup` (LIVE only) | LIVE forward-paper-test |
| `funding_gate_threshold_bps` | `5.0` | (ditto) | 5 bps/8h ≈ 5.5%/yr |
| `funding_cache_ttl_seconds` | `300` | (ditto) | n/a |

**The gating pipeline order in `_execute_trade_with_setup`:**
1. Kill switch check
2. Portfolio heat / correlation
3. Daily trade limit + symbol cooldown
4. Side validation (LONG/SHORT allowed lists)
5. **Funding gate (T2.3)** — new, LIVE-only
6. Slippage / order-type recommendation
7. Allocation / leverage / quantity calc
8. **Vol parity overlay (T1.2 chunk 3)** — new, between baseline & per-trade cap
9. Per-trade cap REJECT
10. Order placement — **maker (T1.3) or taker** depending on flag

---

## 4. New modules added today

```
services/trading-engine/app/risk/
├── vol_targeting.py          ← NEW (T1.2): RealizedVolEstimator, vol_parity_size
└── funding_gate.py           ← NEW (T2.3): FundingRateClient, funding_gate_decision

services/trading-engine/app/live_trading.py
└── execute_maker_order_with_fallback()   ← NEW (T1.3) method on LiveTradingEngine

services/risk-metrics-service/app/
├── sharpe_metrics.py         ← NEW (T0.2): PSR, DSR, Acklam inv-CDF, sample skew/kurt
└── cpcv.py                   ← NEW (T0.2): CombinatorialPurgedCV, cpcv_to_dsr

services/ml-retraining-service/app/core/
└── returns_metrics.py        ← NEW: compute_returns_metrics (r2_returns + dir_acc_corrected)

services/bybit-connector/app/main.py
├── /api/v1/market/funding-rate/history    ← NEW endpoint
└── /api/v1/market/instruments-info        ← NEW endpoint
```

---

## 5. Test status

All new tests pass. Pre-existing test breakages are unrelated to this session
(missing `aiohttp` in local venv blocks `test_auto_trader.py` collection but
those tests run in the container/CI).

| File | Tests | Status |
|------|------:|--------|
| `services/risk-metrics-service/tests/test_sharpe_metrics.py` | 29 | pass |
| `services/risk-metrics-service/tests/test_cpcv.py` | 30 | pass |
| `services/trading-engine/tests/risk/test_vol_targeting.py` | 16 | pass |
| `services/trading-engine/tests/risk/test_funding_gate.py` | 17 | pass |
| `services/trading-engine/tests/unit/test_live_trading_maker.py` | 9 | pass |

**~101 tests** added or maintained today. The 5 vol-parity wiring tests in
`test_auto_trader.py` (`TestVolTargetingWiring`) are present but require
container/CI to run (heavy import dep stack).

---

## 6. Latent bugs found and fixed

The audit fork found four pre-existing bugs that would have hit the first
LIVE-mode trade. All shipped in `6f723c5` and `007a740`. All four had the
same root cause: the `bybit-connector` was rewritten to strip Bybit's V5
envelope (returning `{"success": True, "data": <inner>}`) but consumers
were still reading the old `result` field and gating on `retCode`.

| File | Site | Bug | Fix |
|------|------|-----|-----|
| `live_trading.py` | `execute_market_order` | `retCode != 0` always true on success | dropped dead check |
| `live_trading.py` | `execute_market_order` | read `result`, set `order_id` post-construction (Pydantic v2 ValueError) | use `data`; set `bybit_order_id` at construction |
| `live_trading.py` | `close_position` | same `retCode` bug | dropped check |
| `live_trading.py` | `get_total_equity` | wrong envelope key | use `data` |
| `live_trading.py` | `sync_positions_with_exchange` | wrong envelope shape | use `data` (already a list) |
| `bybit_adapter.py` | `_request` | `result.get(retCode)` always 0; `result` as success key | dropped retCode arm; use `data`; map detail-as-retCode on 4xx |
| `live_trading.py` | maker method | leftover `retCode` arm I shipped (audit caught) | removed |

These were all dormant in PAPER mode (paper engine never invokes any of these
paths). Worth grepping for similar mistakes if any new adapter pops up.

---

## 7. Where things live

### Strategy / planning docs
- `docs/strategy/RESEARCH_PLAN_2026-04-29.md` — Tier 0/1/2 ranked plan
- `docs/strategy/research-2026-04-29/01-crypto-factors.md` … `06-execution-sizing.md` — agent research outputs
- `docs/strategy/research-2026-04-29/V0-*.md` — GRU verification artifacts
- `docs/strategy/research-2026-04-29/T1.2-design.md` — vol parity design
- `docs/strategy/research-2026-04-29/T0.2-cpcv-design.md` — CPCV design (the agent plan)
- `docs/strategy/research-2026-04-29/SESSION-2026-04-30-handoff.md` — this doc

### Test commands
```bash
# risk-metrics-service tests (numpy-only, fast)
cd services/risk-metrics-service && python3 -m pytest tests/test_sharpe_metrics.py tests/test_cpcv.py -q --no-cov

# trading-engine risk tests (no heavy deps)
cd services/trading-engine && python3 -m pytest tests/risk/test_funding_gate.py tests/risk/test_vol_targeting.py tests/unit/test_live_trading_maker.py -q --no-cov

# Full trading-engine tests (needs aiohttp + full env — run in container)
docker compose -f docker-compose.unified.yml exec trading-engine pytest tests/
```

### Stack control
```bash
# Up
docker compose -f docker-compose.unified.yml up -d
# Logs for one service
docker compose -f docker-compose.unified.yml logs -f trading-engine
# Kill switch (file-based)
touch services/trading-engine/EMERGENCY_STOP   # halts auto-trader
```

---

## 8. Open threads / pending tasks

Ranked by readiness to act on tomorrow.

### Ready to start

1. **Wire CPCV into ml-retraining-service.** The harness exists; the natural
   consumer is `ml-retraining-service/app/core/model_validator.py`. Persist
   `(y_pred, y_true, timestamps)` from `model_trainer.train()` to the model
   artifact, then have validator call `cpcv_to_dsr` and emit the DSR into
   the model card. Plan section 4 of `T0.2-cpcv-design.md` recommends
   evaluation-time CPCV (no retraining loop).

2. **GRU rebuild** with returns target + CPCV evaluation gate. The V0
   finding says the current GRUs have no edge on returns — rebuilding with
   `target=log_returns` and an acceptance criterion of `DSR > 0.95` would
   be the honest path. This is bigger work; needs design first.

3. **Forward-paper-test gate kickoff.** To validate any of the three new
   Tier-1 features (T1.2 / T1.3 / T2.3), set `ENABLE_VOL_TARGETING=true`
   in the trading-engine env, run for ≥7 days, compare vs baseline run
   from the same seed/period using PSR. T1.3 + T2.3 require LIVE mode
   (paper has no maker concept and no funding cost).

### Blocked / parked

4. **Untracked `scripts/monitoring/*`** — 6 files staged but not committed.
   Pending user decision on the autonomous tier-2 system.
5. **Sentiment-analysis-service** image build occasionally fails on PyPI
   timeouts (CLAUDE.md gotcha). Not new; flagging for awareness.

### Tier-2 + low-priority

- T2.1 cross-sectional momentum overlay (research item from agent #1)
- T2.2 mean-reversion regime detector (research item from agent #1)
- Cleaning up the latent bug found 2026-04-28 audit (#16 in MEMORY): "ML
  pipeline stale-model + decorative-confidence chains"

---

## 9. Important caveats

- **Vol parity, maker, and funding gate are all default OFF.** The
  trading-engine starts with the exact behaviour it had before this session.
  Forward-paper-test each one before judging.
- **ML predictions default off.** Until a follow-up GRU rebuild lands and
  passes `DSR > 0.95`, treat the technical-analysis service's confidence
  output as decorative.
- **Trading-engine tests don't run in the local venv** (missing aiohttp,
  psutil, etc.). Run them in the container or CI.
- **Pydantic v2 mutation pattern.** Don't set `model_instance.X = ...` for
  `X` that isn't a defined field on the model. Use construction kwargs.
- **Bybit-connector contract.** Success = `{"success": True, "data": <bybit_inner>}`
  with no `retCode`. Errors = HTTP 4xx with `{"detail": "..."}`. Code
  reading `result` or `retCode` from a connector response is broken.

---

## 10. Quick recovery checklist for tomorrow

1. `git -C /mnt/d/Bimo_max/crypto-trading-bot status` — should be clean
   except for the 6 untracked `scripts/monitoring/*` files (parked).
2. `git -C /mnt/d/Bimo_max/crypto-trading-bot log --oneline -17` — should
   start with `da10409 feat(risk-metrics): T0.2 CPCV harness …`.
3. Read `MEMORY.md` (auto-loaded) — it points at the project status memory.
4. Open this file (`SESSION-2026-04-30-handoff.md`) and pick a thread from
   §8 above.
5. If unsure, ask: "What's the next thing per the handoff doc?"
