# TA Signal-Path Audit — 2026-08-26

**Method:** 8-agent workflow (`wf_a87a4cfd-394`): 4 read-only finders (vote wiring, param sourcing, price precision, leftovers), each adversarially verified by an independent second agent instructed to refute. Every verdict below survived verification; verifier corrections are folded in. ~1.09M tokens, 294 tool calls. Spec: `docs/superpowers/specs/2026-08-26-ta-signal-path-correctness-design.md`.

**Headline:** The 2026-07-29 defect table in STATE.md is mostly stale — TA-AGG-01/02/03 and 18-20 of the 22 price-rounding sites are already fixed and test-pinned. What remains open is a different, smaller, but live set of defects centred on the ensemble legs and cross-service parameter drift.

---

## 1. CLOSED — do not re-fix (evidence-verified)

| ID | Claim (2026-07-29) | Reality now |
|---|---|---|
| TA-AGG-01 | ADX/SQZMOM/Volume not in vote | ADX votes (TA `analysis.py:114`; engine `signal_aggregator.py:818`, gated ADX≥20), SQZMOM votes (weight 1.4, re-enabled 2026-08-17), volume is VALIDATOR-only penalty (`voter.py:65`, `validator.py:118-149`) — exactly the decided-correct state |
| TA-AGG-02 | MACD 5/35/5 hardcoded | Settings-sourced since 2026-08-20: `settings.default_macd_fast/slow/signal` (`main.py:303-305`, `config.py:65-75`), pinned by `test_endpoint_defaults_from_settings.py` |
| TA-AGG-03 | BB std 2.5 hardcoded | `settings.default_bb_std` (`main.py:326`, `config.py:81`), pinned |
| 260823-3j3 fixes | — | All landed: MACD→TREND bucket (`voter.py:56`), volume threshold wired (`volume_confirmation.py:89,107`), MTF consensus applied + demote-to-HOLD (`signal_aggregator.py:29-90,1132-1133`), ensemble confidence normalized over firing legs (`multi_strategy_ensemble.py:383-404`) |
| PRICE payload | TA rounds prices to engine | Every price field crosses TA→engine REST at full precision `float()`; live TA `main.py` has zero `round()` calls |
| PRICE s/r detector | 6 sites in `support_resistance_detector.py` | All fixed (WS1-B 2026-08-17), guard-enforced by `tests/test_price_rounding_invariant.py` |
| ML imports in TA | dead LSTM/TF imports | Zero `tensorflow/keras/lstm/torch/onnx` hits anywhere in `services/technical-analysis/` |

Also established (correcting CLAUDE.md §3 service table): **TA service does no GRU inference** — GRU loading lives entirely in ml-prediction-service (`gru_predictor.py:73-103`), off by default (compose `ml` profile + `enable_ml_predictions=false` honored at `enhanced_aggregator.py:88`). GRU vintages mixed: 6 models retrained 2026-04-25/26, 10 at 2025-12-05..10; all ≥4 months stale. BTC metadata still carries forbidden price-level R²=0.9929.

**Traded-path truth (ensemble mode):** voters per timeframe = RSI, MACD, BB, SMA(0.8), EMA, Stochastic, Ichimoku(1.3), SQZMOM_ENHANCED(1.4), ADX(1.0, gated ADX≥20). TREND_FILTER = gatekeeper; VOLUME = validator penalty; ATR = risk-only via `metadata['atr']`; RSI_DIVERGENCE deliberately disabled; ML off. Gate stack per timeframe: vote threshold 0.15 → agreement confidence → gatekeeper → volume penalty → regime modifier/hard-block → category diversity ≥2 → consensus ≥3 → confidence ≥0.30. Then engine-side MTF consolidation (15/60/240), then 3-leg ensemble (simple_rsi / multi_indicator / mean_reversion), then auto_trader gates (conviction floor 0.30, MIN_AGREEING_LEGS=1, threshold 0.10). TA's own `/api/v1/indicators/signal` endpoint is **dashboard-only** — the engine never calls it, and it diverges from the traded signal by construction (TrendFilter votes there; HOLD-vote handling differs).

---

## 2. OPEN — confirmed defects (Phase 21 scope: signal wiring + params)

### P21-1 · VOTE-DROP-ATR — two ensemble legs read a never-populated ATR key **(top severity, live path)**
`fetch_all_indicators` diverts ATR into a separate `atr_data` return (`signal_aggregator.py:832-841`) exposed only as `TradingSignal.metadata['atr']`. The multi_indicator leg was fixed to read that (`multi_strategy_ensemble._atr_levels:236-285`); **simple_rsi (`simple_rsi_strategy.py:60`) and mean_reversion (`mean_reversion_strategy.py:127`) still read `indicators.get("ATR")` — written nowhere** (`auto_trader.py:4718-4724` documents the key as always absent). Consequences: SimpleRSI stops/targets always assume 2% volatility regardless of real ATR; MeanReversion's PRICE_BELOW/ABOVE_SMA deviation sub-signals **can never fire** (silently removes up to 0.25 of its confidence budget) and its stop anchor falls back to 2%. Fix: thread the aggregator's `metadata['atr']` into both legs (or inject synthetic `indicators['ATR']` pre-dispatch) + regression test.

### P21-2 · VOTE-DOUBLE-RSI — single-indicator information passes as multi-leg agreement
RSI is the entirety of the simple_rsi leg (conf up to 0.80), one of 9 voters in multi_indicator, and the mandatory first check of mean_reversion. Under `MIN_AGREEING_LEGS=1` + firing-leg normalization, **simple_rsi alone clears every ensemble gate**. Verifier correction: mean_reversion cannot fire on RSI alone (`MIN_INDICATORS_ALIGNED=2` at `:91` needs a BB co-signal — correlated but distinct). Structural concentration defect; options: correlation/diversity guard across legs (mirroring the category-diversity gate CoreAggregator already applies), or distinct parameterization for the simple_rsi leg. Design decision needed at plan time; not a mechanical fix.

### P21-3 · MTF bypass — consolidation constrains only one of three legs
When MTF demotes consensus to HOLD, only the multi_indicator leg is silenced (`multi_strategy_ensemble.py:314-317`); simple_rsi and mean_reversion generate from the primary-60m indicator dict and can still trade under MIN_AGREEING_LEGS=1 — bypassing the whole MTF agreement machinery (`multi_strategy_ensemble.py:298-336`). Combined with P21-2: one RSI print can trade past an MTF HOLD. Same design-decision bucket as P21-2.

### P21-4 · PARAM-DRIFT-SMA-EMA — engine sends 21, Settings say 20
`signal_aggregator.py:254/285` send `period=21` ("research-optimized") while `config.py:87-88` declare 20. Live votes run on 21; any bare endpoint call gets 20. Fix: engine omits the param (MACD pattern, `sa.py:174-186`) and Settings become single source — after deciding which value is canonical.

### P21-5 · PARAM-DRIFT-ICHIMOKU — engine sends 20/60/120, Settings say 9/26/52
Largest live divergence: the 1.3-weight Ichimoku leg runs 20/60/120 (`sa.py:605-607,634-639`); Settings/endpoint default 9/26/52 (`config.py:126-128`); `main.py:568-570` descriptions advertise the engine's numbers beside defaults that resolve differently — actively misleading in /docs. Same fix pattern as P21-4.

### P21-6 · PARAM-DRIFT-AGG-CONSTRUCTORS — dashboard aggregate path ignores Settings for 4 of 6 voters
`handlers/analysis.py` builds `TrendFilter()/ADXCalculator()/EnhancedSqueezeMomentum()/VolumeConfirmation()` from bare constructors (`:46,57,60,64`) + literals `limit=200`, `'breakout'`; RSI/MACD are settings-sourced (`:40-45`). Values equal today, but env overrides reach the individual endpoints and silently not the aggregate signal — the pre-2026-08-20 MACD bug in mirror image. Same shape in the MTF handler (`analysis.py:284`). Fix: pass `settings.default_*` into constructors.

### P21-7 · Mirror-literal cluster (engine hardcodes what Settings own)
Cross-service gate mirrors, numerically agreeing today, that split behavior on any env override: ADX vote gate 20.0 (`sa.py:453/455`); ADX 25/20 regime re-derivation ignoring TA's regime field (`handlers/signals.py:162-164`); ADX 20.0 + volume-ratio 1.2 trade-admission gates (`sqzmom_strategy_integration.py:239/284`); `market_regime.py:126/239` sends `adx_period=14` explicitly while `fetch_adx` omits it. Treat as one fix family (read TA's returned regime/params or route through engine Settings).

### P21-8 · Small wiring/hygiene residue
- Stale capital literals: `capital: float = 100.0` defaults on `multi_strategy_ensemble.py:291` and `simple_rsi_strategy.py:49` (latent — live path always passes balance; mean_reversion already migrated to the sanctioned `None → get_settings().paper_initial_balance` pattern). Docstring literal `capital=10000` at `advanced_position_sizing.py:107` (money.md docstring rule).
- Dead fallback: `hybrid_strategy_router.py:110-113` ATR-metadata ADX read that can never succeed.
- Dead code in `squeeze_momentum_strategy.py`: unused `SignalType` import (:15), unused `no_squeeze` local (:145), write-only `momentum_exhaustion_count` (:87).
- `app/main.py.bak`: gitignored but **not dockerignored** — local builds COPY it into the image (`Dockerfile:60`) carrying the pre-fix credentialed-wildcard CORS text. Runtime-inert; delete it.
- Doc drift: `sa.py:143` claims RSI thresholds 75/25; actual `rsi.py:80-81` = 80/20.
- HYG-03: TA CORS = `["*"]` + `allow_credentials=False` (`main.py:236-237`) — credential hole closed by `e091826` (git -L proven); wildcard-origin hardening optional, documented in-code as deliberate for an internal service.

---

## 3. OPEN — price-precision residue (Phase 22 scope — **shrunk hard**)

The 22-sites/7-files inventory is ~18-20/22 repaired (WS1-B 2026-08-17) and AST-guard-enforced (`tests/test_price_rounding_invariant.py`, bans `round(...,2|4)` in SCANNED_FILES). Confirmed residue:

1. **`simple_rsi_strategy.py:121-122`** — `round(stop_loss/take_profit, 4)` on the **live** ensemble path (only remaining computation-path price rounding). Bounded today (4dp = ADA tick; lossless for BTC/ETH/SOL/BNB) but fixed-precision, not tick-aware. Fix: `float()` + add file to SCANNED_FILES.
2. **`handlers/sqzmom.py:109`** — 4dp price-unit momentum in `/indicators/sqzmom` payload (no in-repo machine consumer; direction computed from unrounded value).
3. **`indicators/squeeze_momentum.py:541`** — same 4dp momentum in `get_signal` dict (verifier: the rounded key currently reaches no payload — handler reads only `strength`).
4. INFO-severity 4dp serialization rounds with no trade-path consumer: `adaptive_rsi.py:162` (atr_value), `post_trade_analysis.py:151` (price_improvement). 8dp/6dp sites (10) are non-destructive at any supported tick.
5. Guard hygiene: grow SCANNED_FILES with each fixed file; delete `main.py.bak` (11 dead legacy sites polluting counts).

No test pins wrong rounding; four test files pin the fix. Correct tick-aware machinery exists at order time (`costs.py:183`, `paper_slippage.py:210`, `trading_enhancements/limit_order_executor.py:383-392`).

**Recommendation:** Phase 22 as scoped in the roadmap is nearly done already — residue fits a single quick task or a 1-plan phase.

---

## 4. Out-of-scope findings surfaced (route separately)

- **SECURITY (latent): sentiment-analysis-service still has the credentialed-wildcard CORS hole** the 2026-07-29 fix propagated to 8 sibling services but skipped: `config.py:63` `cors_origins=["*"]` + `main.py:241-242` `allow_credentials=True`. Mitigated: behind the off-by-default `analytics` profile and out of the signal pipeline. One-line fix; recommend a standalone quick task.
- **`grid_trading_strategy_v2.py:107/:1438`** — executable `MAX_POSITION_VALUE_USD = 10000.0` feeding `min()` sizing; known and allowlisted in `scripts/check_capital_literals.py:117-124` as an owned defect. Since ADR-029 it numerically equals the whole account (vacuous vs the 10% cap). Trading-engine work, not TA.
- **CLAUDE.md §3 stale**: service table says TA does "GRU inference" — it does not; fix the line when CLAUDE.md is next edited.
- Orphaned engine `app/multi_timeframe.py` (dead module) carries divergent `limit=200`; revival trap only.

---

## 5. Consequence for phase planning

- **Phase 21** re-scopes from "wire ADX/SQZMOM/volume into the vote" (already done) to: **P21-1 ATR threading (mechanical, highest value), P21-4/5 param single-sourcing, P21-6 constructor sourcing, P21-7 mirror cluster, P21-8 hygiene** — plus a **design decision** on P21-2/P21-3 (leg correlation / MTF bypass): fix, or record as accepted design in an ADR. That decision gates whether Phase 21 changes trading behavior beyond stop-sizing.
- **Phase 22** shrinks to §3 (one live site + guard growth) — quick-task-sized.
- Load-bearing fix-routing rule from PARAM-AGG-PATH: engine-sent params are fixed in `signal_aggregator.py`; engine-omitted params are fixed in TA Settings; constructor defaults govern only the dashboard aggregate path. A fix landed in the wrong layer silently does nothing to live trading.
