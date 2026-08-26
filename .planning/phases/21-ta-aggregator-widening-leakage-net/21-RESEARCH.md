# Phase 21: TA Aggregator Widening + Leakage Net — Research

**Researched:** 2026-08-26
**Domain:** Intra-repo signal-path correctness (TA service indicators + trading-engine ensemble/aggregation wiring). No external libraries.
**Confidence:** HIGH (every finding read from source at `file:line` in this session; the highest-severity finding additionally confirmed against the live running service; zero training-data claims about this codebase)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Authority and staleness**
- The audit (`.planning/audits/2026-08-26-ta-signal-path-audit.md`) is **authoritative over the 2026-05-23 requirement text** where they conflict. The roadmap's premise ("aggregator votes only RSI+MACD+TrendFilter") is stale: ADX and SQZMOM vote today in both aggregators; volume is a post-vote penalty. Do NOT re-implement closed items.
- TA-AGG-02/03 are CLOSED (settings-sourced since 2026-08-20, pinned by `services/technical-analysis/tests/test_endpoint_defaults_from_settings.py`). Plans must only record closure evidence — no code change.

**TA-AGG-01 residue (dashboard aggregate endpoint)**
- Vote-widening core is satisfied by evolution. Remaining work: unit tests pinning current gating behavior (ADX votes only when directional and conf>0, SQZMOM votes only when directional, volume scales confidence post-vote and never votes) + document the aggregate-endpoint vote in `wiki/modules/technical-analysis.md`.
- Do NOT add the `aggregator_mode = minimal|full` env from the old requirement text — YAGNI on a dashboard-only endpoint.
- Volume must NEVER become a voter (measured decision 2026-08-17). A veto/penalty is fine; a vote is a defect.

**TA-AGG-04 (fully owed)**
- Look-ahead-leakage regression suite at `services/technical-analysis/tests/test_leakage_regression.py`: for each of the 13 indicator modules under `app/indicators/` plus the aggregate endpoint path, compute at time t with `df[:t+1]` vs full series; values at t must be identical. Ichimoku Senkou forward-shift asserted intentional (projection only, no future value used as input at t).

**P21-1 — ATR threading (top priority, live path)**
- `simple_rsi_strategy.py` and `mean_reversion_strategy.py` must receive real ATR. Thread the aggregator's `metadata['atr']` payload into leg dispatch (or inject a synthetic `indicators['ATR']` entry before dispatching legs in `multi_strategy_ensemble.generate_signal`). Follow the already-fixed multi_indicator leg (`_atr_levels`) as the reference pattern.
- Regression test: legs see real ATR when the aggregator fetched one; fallback 2% only when ATR genuinely absent.

**P21-2 / P21-3 — leg correlation + MTF bypass (fix, operator-approved)**
- Fix as **wiring correctness**, not threshold tuning:
  - MTF demotion must gate ALL ensemble legs: when `consolidate_mtf_confidence` demotes consensus to HOLD, simple_rsi and mean_reversion must not trade past it (today only multi_indicator is silenced).
  - Agreement counting must not present single-source information as multi-leg agreement: RSI-only agreement (simple_rsi + mean_reversion co-fire on the same RSI print) must not count as independent multi-leg confirmation. Mirror the category-diversity idea CoreAggregator already applies to its voters.
- **Locked constraint:** NO changes to threshold values — `min_signal_confidence=0.30`, `AGGREGATION_THRESHOLD=0.10`, `MIN_AGREEING_LEGS=1` stay as-is. Phase-3 verdict (no threshold change; IS/OOS rankings invert) stands.
- These fixes reduce trade admission; that is expected and accepted. Document expected behavior change in the plan's verification.

**P21-4 / P21-5 — parameter single-sourcing (MACD pattern)**
- **Canonical values = the LIVE values** (what the deployed signal actually runs on): SMA/EMA period **21**, Ichimoku **20/60/120**. Lift them into TA `Settings` (`default_sma_period`/`default_ema_period` → 21; `default_ichimoku_*` → 20/60/120), engine omits the params (adopting the MACD pattern at `signal_aggregator.py:174-186`), TA Settings become the single source. Rationale: changing the traded signal's parameters silently is worse than moving the declaration.
- Fix the misleading `main.py:568-570` Ichimoku descriptions so description and default agree.
- Extend `test_endpoint_defaults_from_settings.py` (or sibling) to pin engine-omission: engine request params for SMA/EMA/Ichimoku must not carry period overrides.

**P21-6 — dashboard aggregate + MTF handlers read Settings**
- `handlers/analysis.py` (`get_aggregated_signal` and `analyze_timeframe`): construct TrendFilter/ADXCalculator/EnhancedSqueezeMomentum/VolumeConfirmation from `settings.default_*`; route `'breakout'` through `settings.default_volume_signal_type`; keep `limit=200` literal or move to settings — planner's choice, but pin whatever wins with a test.

**P21-7 — mirror-literal cluster**
- Prefer reading what TA already returns (e.g., ADX response's `regime` field) over re-deriving from mirrored literals. Where a mirror must stay (REST-mesh reality), route it through the engine's own Settings so env overrides move both sides deliberately. Sites: `signal_aggregator.py:453/455` (ADX 20.0 vote gate), `handlers/signals.py:162-164` (25/20 regime re-derivation), `sqzmom_strategy_integration.py:239/284` (ADX 20.0, volume 1.2), `market_regime.py:126/239` (explicit adx_period=14 vs fetch_adx omitting).

**P21-8 — hygiene batch**
- Capital literals: `capital: float = 100.0` defaults on `multi_strategy_ensemble.py:291` and `simple_rsi_strategy.py:49` → the sanctioned `None → get_settings().paper_initial_balance` pattern (mean_reversion is the reference). Docstring `capital=10000` at `advanced_position_sizing.py:107` → reference settings per money.md.
- Remove dead ATR-metadata ADX fallback `hybrid_strategy_router.py:110-113`.
- Remove dead code in `squeeze_momentum_strategy.py` (unused `SignalType` import :15, unused `no_squeeze` local :145, write-only `momentum_exhaustion_count` :87).
- Delete `services/technical-analysis/app/main.py.bak`; add `*.bak` to that service's `.dockerignore`.
- Fix stale RSI-threshold docstring at `signal_aggregator.py:143` (claims 75/25; actual 80/20 in `rsi.py:80-81`).
- TA CORS wildcard: NO change this phase (documented deliberate for internal service; credential hole already closed).

### Claude's Discretion
- Exact mechanism for ATR threading (metadata pass-through vs synthetic indicator entry) — pick the one with the smallest blast radius and best testability.
- Exact mechanism for the leg source-diversity guard — as long as no threshold value changes and behavior is test-pinned.
- Test file organization for the leakage suite (single file per requirement is fine).
- Whether P21-7 mirrors resolve to "read TA response field" or "engine Settings" per site.

### Deferred Ideas (OUT OF SCOPE)
- Price-precision residue → Phase 22 (`simple_rsi_strategy.py:121-122` SL/TP rounding, sqzmom momentum 4dp sites, guard growth, main.py.bak deletion overlaps — coordinate: the .bak deletion lands here in P21-8, guard growth lands in 22).
- sentiment-analysis-service credentialed-wildcard CORS hole — standalone quick task after this phase (security, one line).
- CLAUDE.md §3 service-table correction ("TA + GRU inference" is wrong) — next CLAUDE.md edit.
- `grid_trading_strategy_v2.py` MAX_POSITION_VALUE_USD literal — owned trading-engine defect, tracked by `scripts/check_capital_literals.py` allowlist.
- GRU retrain, LSTM purge (Phase 23), edge research — out of scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description (REQUIREMENTS.md, as superseded by CONTEXT.md) | Research Support |
|----|------------|------------------|
| **TA-AGG-01** | Aggregator extends vote to ADX / SQZMOM / Volume + unit tests + wiki doc. **CONTEXT reduces to:** vote-widening already landed; owe *test residue* + wiki doc. `aggregator_mode` env explicitly dropped. | §"TA-AGG-01 Residue — What Actually Exists" — 4 of ~6 required tests **already exist** in `tests/test_aggregator_new_legs.py`. Exact gaps enumerated with the `_patched()` fixture pattern to extend. Wiki page exists at `wiki/modules/technical-analysis.md` (8,507 B, last touched 2026-07-30). |
| **TA-AGG-02** | MACD params single-sourced from `settings.default_macd_*`. **CLOSED.** | §"Closure Evidence" — `config.py:65-75`, `main.py` route Query defaults, pinned by `test_endpoint_defaults_from_settings.py` rows `WIRED_ROUTE_DEFAULTS[1..3]` + `WIRED_HANDLER_DEFAULTS`. Engine omits at `signal_aggregator.py:182-186`. No code change. |
| **TA-AGG-03** | BB std single-sourced from `settings.default_bb_std`. **CLOSED.** | §"Closure Evidence" — `config.py:81`, pinned by same test file. **Caveat found:** engine still *sends* `std_dev: 2.5` (`signal_aggregator.py:226`) — a mirror, not a drift. Documented in §"Mirror Inventory". |
| **TA-AGG-04** | Look-ahead leakage regression suite over 13 indicator modules + aggregate path. **Fully owed.** | §"Leakage Suite Design" — per-module entry-point/signature/warm-up table, the **tier-1 vs tier-2 test-formulation problem** (prefix-vs-full is tautological for scalar-returning calculators), one real repainting site found (`rsi_divergence.py:176-186`), Ichimoku shift semantics resolved. |

</phase_requirements>

---

## Summary

This is a **pure intra-repo correctness phase**. No new dependencies, no new services, no external APIs. Every planning input is a `file:line` fact in this repository, and every one below was read from source during this research session. The 2026-08-26 audit's confirmed-open list survived re-verification without correction, but research surfaced **four material facts the audit did not state** that change how P21-1 and TA-AGG-04 must be planned.

**The single most important finding is a unit trap in P21-1 — and it is measured, not hypothetical.** `simple_rsi_strategy.py:60-69` reads ATR via `metadata['atr_pct']` and guesses the unit with `if atr_pct > 1.0: atr_pct /= 100`. The TA service produces `atr_pct` as a **percent** (`atr.py:91` — `(atr / current_price) * 100`), and sub-1% hourly ATR is a *normal, explicitly-modelled* regime (`atr.py:94` buckets `atr_pct < 1.0` as LOW volatility). Live values pulled from the running TA service on 2026-08-26 show **3 of the 5 validated symbols are below 1.0 right now**:

| Symbol | live `atr_pct` (60m) | `> 1.0` heuristic fires? | Fraction `simple_rsi` would use | Resulting stop distance (×2.0 mult) |
|---|---|---|---|---|
| BTCUSDT | **0.6658** | ❌ no | **0.666** (= 66.6%) | **133% of price → negative stop** |
| ETHUSDT | **0.8376** | ❌ no | **0.838** (= 83.8%) | **168% of price → negative stop** |
| BNBUSDT | **0.7182** | ❌ no | **0.718** (= 71.8%) | **144% of price → negative stop** |
| SOLUSDT | 1.1065 | ✅ yes | 0.01107 | 2.2% — correct |
| ADAUSDT | 1.4043 | ✅ yes | 0.01404 | 2.8% — correct |

So threading real ATR in without fixing the unit contract puts BTC, ETH and BNB on **negative stop-losses for every BUY**, at current market conditions, on the live paper path. The defect is invisible today only because `indicators["ATR"]` is never populated. **P21-1 as literally specified ships a catastrophic sizing bug unless the unit contract is fixed in the same task.** The `or`-chain fallback to `numeric_value()` (absolute ATR — 522.1 for BTC → `> 1.0` → 5.22 → 522% volatility) is the same trap by a second route, reachable whenever `atr_pct` is `0.0` (which is `atr.py:136`'s failure default, not a reading).

The second finding reshapes TA-AGG-04. The requirement text prescribes "compute at t with `df[:t+1]` vs full series; values at t must be identical." That test is **non-trivial only for series-returning entry points**. Ten of the thirteen modules return a scalar/dict describing *the last supplied bar*, for which `f(df[:t+1])` is definitionally leakage-free and the comparison is tautological. A suite built naively on the requirement's wording would be ~10 always-green tests — completeness theater. The genuinely valuable assertions are enumerated in §"Leakage Suite Design", and one **real repainting site** was found: `rsi_divergence.py:176-186/215-225` confirms a pivot at index `i` using `series.iloc[i+1:i+threshold+1]`.

Third: `primary_signal.action` **already carries** the MTF-demoted action (`signal_aggregator.py:1133`) into the object the ensemble receives — so P21-3 is a one-place fix inside `generate_signal`, not a plumbing job. But `action == HOLD` is overloaded across four upstream causes and current metadata **cannot** distinguish MTF demotion (the stored `consensus_action` is the *pre*-demotion value), so the narrow fix needs one new metadata key.

Fourth: P21-1 and P21-2/3 push trade admission in **opposite directions** and must be measured together, not sequentially. Threading ATR unlocks mean_reversion's `PRICE_BELOW/ABOVE_SMA` sub-signals (`mean_reversion_strategy.py:169-208`, gated on `atr_value > 0`), *increasing* its confidence budget by up to 0.25 and giving it a second firing route. The MTF gate and diversity guard *decrease* admission. Net direction is unknown a priori.

**Primary recommendation:** Sequence as `[P21-8 hygiene + TA-AGG-02/03 closure evidence] → [P21-4/5/6/7 param sourcing] → [TA-AGG-04 leakage suite] → [P21-1 ATR threading **with** the unit-contract fix] → [P21-2/3 gating] → combined before/after measurement`. Land P21-1 and P21-2/3 in the same measurement window. Use a **synthetic replay harness** for the behavior comparison, not live signal pulls — the live funnel has emitted zero trades since 2026-08-16, so a live before/after will show "no change" for every fix and prove nothing.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Indicator math (RSI, MACD, ATR, Ichimoku, …) | **TA service** `app/indicators/**` | — | Pure computation; TA owns it. Leakage suite belongs here. |
| Indicator **parameter declaration** | **TA service** `app/config.py` Settings | — | Post-2026-08-20 rule. Engine-omitted params resolve here. Confirmed by `test_endpoint_defaults_from_settings.py`. |
| Dashboard aggregate vote | **TA service** `handlers/analysis.py` | — | `/api/v1/indicators/signal/{symbol}` (`main.py:794`). **Engine never calls it** — divergence from the traded signal is by construction. |
| Per-timeframe indicator vote (traded) | **trading-engine** `aggregation/voter.py` + `aggregator_core.py` | TA (supplies values over REST) | Engine owns the vote; TA supplies inputs. |
| Cross-timeframe consolidation | **trading-engine** `signal_aggregator.consolidate_mtf_confidence` + `:1096-1133` | `aggregation/multi_timeframe.py` | Owns MTF demote-to-HOLD. **P21-3's gating decision belongs here or one level down.** |
| 3-leg ensemble decision | **trading-engine** `strategies/multi_strategy_ensemble.py` | legs: `simple_rsi_strategy.py`, `mean_reversion_strategy.py` | **P21-1, P21-2, P21-3 all land here.** Single dispatch point at `:298-344`. |
| Risk-level derivation (SL/TP from ATR) | **trading-engine** `_atr_levels` (multi leg) / per-leg (rsi, mean-rev) | — | Reference pattern for P21-1 is `multi_strategy_ensemble.py:236-285`. |
| Trade admission gates | **trading-engine** `auto_trader._check_and_trade_ensemble:4649+` | `signal_funnel` | Gates are downstream of the ensemble; **do not touch** (thresholds locked). |
| Engine-side param **mirrors** of TA settings | **trading-engine** `app/config.py` | — | Precedent exists: `config.py:321 adx_trending_threshold` with an explicit "Do NOT diverge" comment. **This is the P21-7 target pattern.** |

**Fix-routing rule (load-bearing, from the audit §5, re-verified):** engine-**sent** params are fixed in `signal_aggregator.py`; engine-**omitted** params are fixed in TA `Settings`; **constructor defaults** govern *only* the dashboard aggregate path. A fix landed in the wrong layer silently does nothing to live trading.

---

## Standard Stack

**No new packages are introduced by this phase.** All work is intra-repo wiring, parameter sourcing, and test authoring using the stack already installed.

### Core (already present — versions verified in this session)

| Component | Version | Purpose | Why Standard |
|-----------|---------|---------|--------------|
| Python | 3.12.3 | Runtime (host + containers) | `python3 --version` [VERIFIED: local shell] |
| pytest | 9.0.3 | Both services' test runner | `python3 -m pytest --version` [VERIFIED: local shell] |
| pandas / numpy | (in TA `requirements.txt`) | Indicator math substrate — all `calculate(df)` entry points are DataFrame-in | [VERIFIED: source reads of `app/indicators/*.py`] |
| pydantic / pydantic-settings v2 | (both services) | `Settings`, `IndicatorSignal`, `TradingSignal` | [VERIFIED: `config.py:23-24`, `models/signal.py:6`] |
| FastAPI + `TestClient` | — | TA route-default tests drive `/openapi.json` | [VERIFIED: `test_endpoint_defaults_from_settings.py:22,29`] |
| httpx `AsyncClient` | — | Engine→TA REST mesh (`signal_aggregator.py:114`) | [VERIFIED: source] |

### Supporting (test-side patterns already in the repo)

| Pattern | Location | When to Use |
|---------|----------|-------------|
| `unittest.mock.patch` on `app.handlers.analysis.<Calculator>` | `test_aggregator_new_legs.py:_patched()` | Any test of the TA aggregate path. **Must patch in the `handlers.analysis` namespace**, not the indicator module. |
| `AsyncMock` fetcher (`get_klines_as_dataframe`) | same | Drives `get_aggregated_signal` with **no HTTP** — direct `await` of the handler function. |
| `importlib.reload(mod)` fixture | `test_ensemble_leg_wiring.py:103-108` | Ensemble tests needing a fresh module (weights singleton). |
| Parametrized `(route, param, settings_field)` table | `test_endpoint_defaults_from_settings.py:133-231` | The drift-pinning pattern to extend for P21-4/5. |
| AST guard over a `SCANNED_FILES` list | `tests/test_price_rounding_invariant.py` | Structural bans. **Recommended for the leakage suite's tier-2.** |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Synthetic `IndicatorSignal("ATR")` injected into a local dict | Change both legs' signatures to accept `atr_data: dict` | Signature change touches 2 legs + 3 call sites + 6 existing tests; the synthetic entry reuses the `_atr(value)` builder **already present** at `test_ensemble_leg_wiring.py:92`. **Recommend the synthetic entry.** |
| New metadata key `mtf_demoted_to_hold` | Gate all legs on bare `action == HOLD` | Bare-HOLD is broader than CONTEXT authorizes (see §Fork 2). |
| Extending `test_endpoint_defaults_from_settings.py` | New sibling file `test_engine_param_omission.py` | The engine-omission assertion lives in **trading-engine**, whose tests cannot import TA `Settings`. **A sibling file in `services/trading-engine/tests/` is required** — the TA file cannot host it. |

**Installation:** none. Confirm with `git diff --stat` that no `requirements.txt` is touched.

---

## Package Legitimacy Audit

**Not applicable — this phase installs zero external packages.**

Verified by: the entire scope is edits to existing `.py` files under `services/technical-analysis/` and `services/trading-engine/`, plus new test files using `pytest` / `unittest.mock` / `pandas`, all already in both services' `requirements.txt`. No `npm install`, `pip install`, or `cargo add` appears anywhere in the audit, the design spec, or CONTEXT.md.

**slopcheck: not run (no packages to check).** If the planner introduces any new dependency, the Package Legitimacy Gate must be run before that task is approved, and the package tagged `[ASSUMED]` until it passes.

**Packages removed due to slopcheck [SLOP] verdict:** none (N/A)
**Packages flagged as suspicious [SUS]:** none (N/A)

---

## Architecture Patterns

### System Architecture Diagram — the live (ensemble) signal path

```
                        ┌──────────────────────────────────────────┐
   Bybit mainnet ──────▶│ market-data-service :8002 → TimescaleDB   │
                        └────────────────────┬─────────────────────┘
                                             │ klines
                                             ▼
   ┌─────────────────────────────────────────────────────────────────────────┐
   │ technical-analysis :8004                                                │
   │                                                                          │
   │  fetcher.get_klines_as_dataframe(symbol, interval, limit)               │
   │            │                                                             │
   │            ├──▶ app/indicators/*.py  (13 modules)  ◀── TA-AGG-04 SCOPE   │
   │            │       params ← app/config.py Settings  ◀── P21-4/5 SCOPE    │
   │            │                                                             │
   │            ├──▶ /api/v1/indicators/{rsi,macd,…}  ── engine reads these   │
   │            │                                                             │
   │            └──▶ handlers/analysis.get_aggregated_signal                  │
   │                   (bare constructors) ◀── P21-6 SCOPE                    │
   │                        │                                                 │
   │                        ▼  /api/v1/indicators/signal/{symbol}             │
   │                   DASHBOARD ONLY — engine never calls this               │
   └────────────┬────────────────────────────────────────────────────────────┘
                │ REST (per-indicator endpoints, 12 concurrent)
                ▼
   ┌─────────────────────────────────────────────────────────────────────────┐
   │ trading-engine :8005                                                    │
   │                                                                          │
   │  signal_aggregator.fetch_all_indicators(symbol, interval)     :769       │
   │     │   ┌── 11 IndicatorSignal → indicators{}                            │
   │     └───┤                                                                │
   │         └── ATR → separate atr_data dict  ────────────┐      :832-841    │
   │                                                        │                 │
   │  CoreAggregator: vote(0.15) → agreement → gatekeeper   │                 │
   │     → volume penalty → regime → category-diversity ≥2  │                 │
   │     → consensus ≥3 → confidence ≥0.30                  │                 │
   │                     │                                  │                 │
   │                     ▼    ×3 timeframes (15 / 60 / 240) │                 │
   │  get_trading_signal_multi_timeframe                    │                 │
   │     consolidate_mtf_confidence()                :29-90 │                 │
   │       demote-to-HOLD when no TF's gated action agrees  │                 │
   │     primary_signal.action = consolidated_action  :1133 │                 │
   │     primary_signal.metadata["multi_timeframe"]   :1134 │                 │
   │                     │                                  │                 │
   │                     ▼  TradingSignal ──── metadata["atr"] ◀──────────────┘
   │                                                                          │
   │  auto_trader._check_and_trade_ensemble(symbol)         :4649             │
   │     ├─ observe_regime(base_signal.indicators)          :4703             │
   │     ├─ current_price ← indicator metadata scan         :4734             │
   │     └─ ensemble.generate_signal(base_signal, price, capital)  :4756      │
   │                     │                                                    │
   │        ┌────────────┴──────────────────────────────────────┐             │
   │        ▼ multi_strategy_ensemble.generate_signal      :287  │             │
   │        │   indicators = aggregator_signal.indicators  :298  │             │
   │        │                                                    │             │
   │        │  leg1 simple_rsi     ← indicators  (ignores action) ◀ P21-3     │
   │        │       reads indicators["ATR"] :60  ── NEVER WRITTEN  ◀ P21-1    │
   │        │  leg2 multi_indicator ← gated on action != HOLD :314            │
   │        │       _atr_levels(metadata["atr"])  :236  ✅ REFERENCE PATTERN  │
   │        │  leg3 mean_reversion ← indicators  (ignores action) ◀ P21-3     │
   │        │       reads indicators["ATR"] :127 ── NEVER WRITTEN  ◀ P21-1    │
   │        │                                                    │             │
   │        │  weighted_score / directional_weight         :399  │             │
   │        │  agreeing_legs ≥ MIN_AGREEING_LEGS(1)        :412  ◀ P21-2      │
   │        │  |score| ≥ AGGREGATION_THRESHOLD(0.10)       :419  │             │
   │        └────────────────────────────────────────────────────┘             │
   │                     │ EnsembleSignal                                      │
   │                     ▼                                                     │
   │  auto_trader gates: conviction ≥0.30 → dedupe → cooldown → sizing → order │
   └─────────────────────────────────────────────────────────────────────────┘
```

### Recommended change surface (no new files in `app/`)

```
services/technical-analysis/
├── app/config.py                    # P21-4/5: sma/ema 20→21, ichimoku 9/26/52→20/60/120
├── app/main.py                      # P21-5: fix Ichimoku Query descriptions (:568-570)
├── app/main.py.bak                  # P21-8: DELETE
├── .dockerignore                    # P21-8: add *.bak
├── app/handlers/analysis.py         # P21-6: constructors ← settings.default_*
├── app/strategies/squeeze_momentum_strategy.py  # P21-8: dead code :15, :87, :145
└── tests/
    ├── test_leakage_regression.py   # TA-AGG-04 — NEW
    ├── test_aggregator_new_legs.py  # TA-AGG-01 — EXTEND (4 tests exist)
    └── test_endpoint_defaults_from_settings.py  # P21-6 — EXTEND

services/trading-engine/
├── app/signal_aggregator.py         # P21-4/5 omit params; P21-7 ADX gate; :143 docstring
├── app/config.py                    # P21-7: engine-side mirror fields (adx_weak_trend_threshold, …)
├── app/handlers/signals.py          # P21-7: read TA `regime` field (:162-164)
├── app/aggregation/market_regime.py # P21-7: adx_period (:126/:239)
├── app/strategies/multi_strategy_ensemble.py    # P21-1 inject ATR; P21-2 diversity; P21-3 gate; P21-8 capital
├── app/strategies/simple_rsi_strategy.py        # P21-1 unit contract; P21-8 capital (:49)
├── app/strategies/hybrid_strategy_router.py     # P21-8: remove :110-113
├── app/strategies/sqzmom_strategy_integration.py# P21-7: :239/:284
├── app/risk/advanced_position_sizing.py         # P21-8: docstring :107
└── tests/
    ├── strategies/test_ensemble_leg_wiring.py   # EXTEND — has _atr() builder at :92
    ├── strategies/test_ensemble_atr_levels.py   # EXTEND
    ├── test_mtf_confidence_consolidation.py     # EXTEND for P21-3
    └── test_engine_param_omission.py            # P21-4/5 — NEW (TA file cannot host this)
```

---

### Pattern 1 — ATR threading via a synthetic `IndicatorSignal` into a **local** dict

**What:** Build one `IndicatorSignal(name="ATR", …)` from `aggregator_signal.metadata["atr"]` inside `generate_signal`, and dispatch legs against a **copy** of the indicator dict.

**When to use:** P21-1. This is the recommended mechanism (Claude's-discretion item).

**Why a local copy, not in-place mutation:** `aggregator_signal.indicators` is the same object handed to `hybrid_strategy.observe_regime` (`auto_trader.py:4703-4705`) and reachable from `aggregation/signal_cache.py`. ATR is deliberately **non-voting** (`fetch_all_indicators` diverts it at `:832-841` precisely so it never reaches the voter). Mutating the shared dict risks ATR re-entering a voter set or a `weights` lookup. The audit's phrasing "inject synthetic `indicators['ATR']` entry" is satisfied by a copy.

**Why one signal serves both legs (unit-verified):**
- `mean_reversion_strategy.py:143` → `atr_signal.numeric_value()` → wants **absolute price units** → served by `.value`.
- `simple_rsi_strategy.py:63-67` → `metadata["atr_pct"]` → wants a **fraction after its heuristic** → served by metadata.

```python
# services/trading-engine/app/strategies/multi_strategy_ensemble.py
# Source: verified against signal_aggregator.fetch_atr:409-419 and
#         technical-analysis app/indicators/atr.py:91,113
#
# atr.py:91  ->  atr_pct = (atr / current_price) * 100      # PERCENT, e.g. 1.85
# atr.py:113 ->  "atr_pct": float(atr_pct)                  # crosses the wire as a percent
# atr.py:136 ->  failure default is atr_pct == 0.0          # ABSENCE, not "zero volatility"

@staticmethod
def _atr_indicator(aggregator_signal: TradingSignal) -> Optional[IndicatorSignal]:
    """Rebuild the aggregator's risk-only ATR payload as an IndicatorSignal so
    the simple_rsi and mean_reversion legs can consume it.

    Returns None when the aggregator produced no usable ATR — the legs then
    keep their documented 2% fallback (CONTEXT: "fallback 2% only when ATR
    genuinely absent").
    """
    atr_data = (aggregator_signal.metadata or {}).get("atr")
    if not isinstance(atr_data, dict):
        return None

    try:
        atr_abs = float(atr_data["atr"])
        atr_pct = float(atr_data["atr_pct"])          # PERCENT, per atr.py:91
    except (KeyError, TypeError, ValueError):
        return None

    # atr.py:134-146 (_default_response) emits BOTH atr == 0.0 AND atr_pct == 0.0
    # as its failure default. Treating either as a real reading gives a
    # zero-width stop. BUT SEE THE PRESENCE-PREDICATE WARNING BELOW — returning
    # None here is NOT symmetric with what the multi_indicator leg does.
    if atr_abs <= 0.0 or atr_pct <= 0.0:
        return None

    return IndicatorSignal(
        name="ATR",
        signal=SignalAction.HOLD,          # never directional; ATR does not vote
        confidence=min(1.0, max(0.0, float(atr_data.get("confidence", 0.5)))),
        value=atr_abs,                     # mean_reversion reads this via numeric_value()
        metadata={
            "atr_pct": atr_pct,            # percent — kept verbatim from the wire
            "atr_fraction": atr_pct / 100.0,   # EXPLICIT contract; see Pitfall 1
            "role": "RISK",                # mirrors fetch_adx's role convention
            "weight": 0.0,                 # defensive: never contributes to a vote
        },
    )

# inside generate_signal(), replacing line 298:
    indicators = dict(aggregator_signal.indicators or {})   # local copy — do NOT mutate
    atr_ind = self._atr_indicator(aggregator_signal)
    if atr_ind is not None:
        indicators["ATR"] = atr_ind
```

---

### Pattern 2 — the unit contract on the consuming side (mandatory companion to Pattern 1)

**What:** `simple_rsi_strategy.py` must read an unambiguously-scaled key. Its current heuristic is wrong for the common sub-1% regime.

**Why this is safe to change now:** `indicators.get("ATR")` returns `None` on every production call today (`auto_trader.py:4718-4724` documents the key as always absent), so the entire `if atr_sig:` block at `:62-69` is **currently dead**. Editing it changes nothing live until Pattern 1 lands — this is the safest possible moment.

```python
# services/trading-engine/app/strategies/simple_rsi_strategy.py:60-69
# BEFORE (verified, current source):
#   atr_sig = indicators.get("ATR")
#   atr_pct = 0.02
#   if atr_sig:
#       atr_pct = float((atr_sig.metadata or {}).get("atr_pct")
#                       or atr_sig.numeric_value() or 0.02)
#       if atr_pct > 1.0:
#           atr_pct = atr_pct / 100.0
#
# Two defects, both live the instant real ATR arrives:
#   (a) a genuine 0.8% ATR is NOT > 1.0, so it is read as 80% volatility
#       -> stop_distance = price * 0.8 * 2.0 = 160% of price -> negative stop.
#       atr.py:94 buckets atr_pct < 1.0 as LOW volatility: this is the COMMON case.
#   (b) the `or` chain falls through to numeric_value() (ABSOLUTE atr, e.g. 1200
#       for BTC) whenever atr_pct is 0.0/None -> 1200 > 1.0 -> 12.0 -> 1200%.

# AFTER — read the declared contract, fall back to the heuristic only for
# producers that predate it:
    atr_sig = indicators.get("ATR")
    atr_pct = self.DEFAULT_ATR_FRACTION            # 0.02, named not literal
    if atr_sig:
        meta = atr_sig.metadata or {}
        fraction = meta.get("atr_fraction")
        if fraction is None and meta.get("atr_pct") is not None:
            fraction = float(meta["atr_pct"]) / 100.0   # producer contract: PERCENT
        if fraction is not None and 0.0 < float(fraction) < 1.0:
            atr_pct = float(fraction)
        else:
            logger.warning(
                "[SIMPLE_RSI] unusable ATR payload %r — falling back to %.2f%%",
                meta, self.DEFAULT_ATR_FRACTION * 100,
            )
```

**Sanity bound to pin with a test:** a resolved fraction outside `(0, 1)` is never a real hourly-crypto ATR and must fall back with a WARNING rather than size a trade.

#### ⚠️ The ATR-presence predicate is not symmetric across legs — resolve this explicitly

`atr.py:129-146` `_default_response()` is the failure path, and it is **not** an empty payload:

```python
return {
    "atr": 0.0,          # <- the two legs' presence check keys on this
    "atr_pct": 0.0,      # <- and this
    "stop_loss_long":  float(current_price * (1 - 0.03)),   # <- POPULATED, 3%
    "stop_loss_short": float(current_price * (1 + 0.03)),   # <- POPULATED, 3%
    "take_profit_long":  float(current_price * (1 + 0.06)),
    "take_profit_short": float(current_price * (1 - 0.06)),
    "volatility": "UNKNOWN", "confidence": 0.3,
    "description": "Insufficient data - using default 3% SL",
}
```

So on an ATR fetch failure the **same payload** yields three different answers:

| Leg | Reads | Verdict | Stop used |
|---|---|---|---|
| `multi_indicator` | `_atr_levels` → `stop_loss_long/short` | **"ATR present"** — keys are populated and float-castable | **3%** (`atr.py:131`) |
| `simple_rsi` (post-P21-1) | `atr`/`atr_pct` → both 0.0 | **"ATR absent"** | **2%** (`DEFAULT_ATR_FRACTION`) |
| `mean_reversion` (post-P21-1) | `numeric_value()` → 0.0 | **"ATR absent"** | **2%** (`:224` `current_price * 0.02`) |

Three legs, one payload, three different risk models — and a **third** undeclared constant (3%) that neither leg's fallback mentions. CONTEXT locks "fallback 2% only when ATR **genuinely** absent"; under `_default_response` the honest answer is that ATR *is* genuinely absent, so `multi_indicator`'s 3% is the outlier.

**The plan must pick one and state it.** Options, cheapest first:

1. **Shared predicate (recommended).** Extract `_atr_is_usable(atr_data) -> bool` and have `_atr_levels` and `_atr_indicator` both call it, keying on `atr > 0 and atr_pct > 0`. `multi_indicator` then returns `UNUSABLE_LEVEL` on the failure payload — which `AutoTrader._ensemble_stops_are_consistent` already rejects pre-fill with an ERROR (`multi_strategy_ensemble.py:50-55`). Consistent, and it surfaces the fetch failure loudly instead of silently trading a 3% stop nobody chose.
2. **Derive the missing half.** `generate_signal` has `current_price` in scope, so `atr_pct = atr_abs / current_price * 100` can repair a partial payload. Only helps the genuinely-partial case, not `_default_response` (where *both* are 0.0).
3. **Accept the divergence and log it.** Acceptable only if written down — an undocumented 2%-vs-3% split across legs is exactly the class of defect this phase exists to remove.

**Pin whichever wins with a test** that feeds `_default_response`'s exact dict to all three legs and asserts they agree on presence.

---

### Pattern 3 — MTF demotion gate on all legs (P21-3)

**What:** Mark the demotion at the consolidation site, gate all legs on the mark.

**The key fact:** `signal_aggregator.py:1133` already writes `primary_signal.action = consolidated_action`, so the demoted action *is* on the object the ensemble receives. Legs 1 and 3 simply never read `.action` (`multi_strategy_ensemble.py:303, 336`). One-place fix.

**The complication:** `action == HOLD` arrives from **four** distinct upstream causes:

| Cause | Site | In CONTEXT scope? |
|---|---|---|
| MTF consensus demoted (no TF's gated action agrees) | `signal_aggregator.py:71-78` | **YES — this is P21-3** |
| Raw MTF consensus was genuinely HOLD | `multi_timeframe._calculate_weighted_consensus` | Ambiguous |
| Regime hard-block (post-MTF) | `signal_aggregator.py:1189` | No |
| Per-timeframe requirements gate → HOLD upstream | `aggregator_core` | No |

And `metadata["multi_timeframe"]["consensus_action"]` (`:1137`) stores `mtf_analysis.consensus_action` — the **pre-demotion** value. **Demotion is therefore not detectable from current metadata.** One new key is required for the narrow fix.

```python
# services/trading-engine/app/signal_aggregator.py — extend the metadata write at :1134
        primary_signal.metadata["multi_timeframe"] = {
            "enabled": True,
            ...
            "consensus_action": mtf_analysis.consensus_action.value,   # pre-demotion (unchanged)
            # NEW: the post-consolidation action, and whether consolidation
            # DEMOTED a directional consensus. `consensus_action` above is the
            # raw pre-gate blend, so demotion was previously unobservable
            # downstream — which is exactly why only the multi_indicator leg
            # (guarded on action != HOLD) honoured it.
            "consolidated_action": consolidated_action.value,
            "demoted_to_hold": (
                mtf_analysis.consensus_action != SignalAction.HOLD
                and consolidated_action == SignalAction.HOLD
            ),
            ...
        }

# services/trading-engine/app/strategies/multi_strategy_ensemble.py — in generate_signal,
# before dispatching any leg:
        mtf_meta = (aggregator_signal.metadata or {}).get("multi_timeframe") or {}
        if mtf_meta.get("demoted_to_hold") is True:
            logger.info(
                "[ENSEMBLE] HOLD — MTF consolidation demoted the consensus to HOLD; "
                "all three legs suppressed. Previously only %s honoured this.", LEG_MULTI
            )
            return None
```

**Alternative (broader) reading:** gate on bare `aggregator_signal.action == SignalAction.HOLD`. Simpler and needs no new key, but it also suppresses the regime hard-block and upstream-requirements cases — **more than CONTEXT authorizes**. Planner decides; flag the scope delta if choosing broad.

---

### Pattern 4 — leg source-diversity guard (P21-2), mirroring `check_category_diversity`

**What CoreAggregator already does** (`aggregation/voter.py:549-586`, verified): `check_category_diversity(voting_indicators, action, min_categories=2)` counts how many of `{MOMENTUM, TREND, VOLATILITY, OTHER}` contain at least one *agreeing* indicator, and requires ≥2. Categories at `voter.py:36-63`:

```
MOMENTUM   = {RSI, STOCHASTIC, RSI_DIVERGENCE}
TREND      = {SMA, EMA, ICHIMOKU, ADX, MACD}      # MACD moved here 2026-08-23
VOLATILITY = {BOLLINGER_BANDS, SQZMOM_ENHANCED}
```

**The ensemble-level mirror:** map each *directionally-agreeing leg* to the indicator categories it actually consumed, union them, require ≥2. Reuse `INDICATOR_CATEGORIES` — do not redefine it.

| Leg | Category source | Available today? |
|---|---|---|
| `simple_rsi` | RSI only → `{MOMENTUM}` | Structural — hardcode `{"RSI"}`. `SimpleRSIStrategy.generate_signal` reads exactly one key (`:51`). |
| `mean_reversion` | `MeanReversionSignal.indicators_aligned: List[str]` | **YES** — structured field already exists (`mean_reversion_strategy.py:44`). Values: `RSI_EXTREME`, `RSI_OVERSOLD`, `BB_LOWER`, `BB_NEAR_LOWER`, `PRICE_EXTREME_BELOW_SMA`, `PRICE_BELOW_SMA` (+ overbought mirrors). Map prefix → `RSI` / `BOLLINGER_BANDS` / `SMA`. |
| `multi_indicator` | Already passed CoreAggregator's ≥2-category gate | Treat as ≥2 by construction, or read `aggregator_signal.consensus_count`. |

**Why this is the right framing (and the tension the planner must see):** the audit's verifier correction established that `mean_reversion` **cannot** fire on RSI alone — `MIN_INDICATORS_ALIGNED = 2` (`:91`) needs a BB or SMA co-signal. So the actual concentration case reduces to **`simple_rsi` firing alone**. A guard that blocks it is, *in the single-leg case*, functionally equivalent to `MIN_AGREEING_LEGS = 2` — while leaving the constant at `1`, which is what the lock literally requires.

The category framing is nonetheless the **defensible** one, and materially different from a leg count: `simple_rsi + mean_reversion` co-firing yields `{MOMENTUM} ∪ {MOMENTUM, VOLATILITY}` = 2 categories → **passes**, whereas `MIN_AGREEING_LEGS=2` would also pass it. The two rules diverge where it matters: `multi_indicator` alone (1 leg, ≥2 categories) → category guard **passes**, `MIN_AGREEING_LEGS=2` **blocks**. Since `multi_indicator` is the leg carrying the full 9-voter gate stack, blocking it would be a serious regression. **Surface this comparison in the plan** so the reviewer does not read the guard as a smuggled threshold change.

**Interaction with P21-1 (important):** threading ATR unlocks `PRICE_BELOW/ABOVE_SMA` (`mean_reversion_strategy.py:169`, gated on `sma_value and atr_value and atr_value > 0`). Post-P21-1, `mean_reversion` gains a **second** firing route — `RSI + SMA-deviation`, no BB — whose categories are `{MOMENTUM, TREND}`. The guard must be written against `indicators_aligned`, not against an assumption that BB is always present.

---

### Anti-Patterns to Avoid

- **Mutating `aggregator_signal.indicators` in place** — shared with `observe_regime` and the signal cache; risks ATR entering a voter set. Copy.
- **Passing ATR as a bare float through a new leg parameter** — breaks 6 existing tests and both legs' signatures; the synthetic-`IndicatorSignal` route reuses the `_atr(value)` builder already at `test_ensemble_leg_wiring.py:92`.
- **Landing the leakage suite as 13 uniform prefix-vs-full tests** — 10 of them are tautological (see §Leakage Suite Design). Green tests that cannot fail are worse than no tests: they retire the requirement without buying safety.
- **Blanket `pytest.approx` in the leakage suite** — masks real leakage. Demand exact equality; relax **per-indicator** with a written reason. **The one anticipated exception:** `sqzmom_enhanced.py:408` `calculate_linreg_value` runs a least-squares fit per rolling window. Float accumulation order in a least-squares solve can differ between a length-`t+1` frame and a length-`N` frame depending on how pandas dispatches `.rolling().apply()`. If that single test fails, the **first** diagnostic is "is the delta at machine epsilon (~1e-16)?" — not "we found leakage." A relative tolerance scoped to that one indicator, with this reason in the docstring, is correct; widening it to the whole suite is not.
- **Fixing a mirror in the wrong layer** — changing `config.py:default_sma_period` while `signal_aggregator.py:254` still sends `period=21` changes nothing live. Verify with the omission test, not by reading the Settings diff.
- **Asserting P21-1 tests on `simple_rsi` SL/TP output values** — `simple_rsi_strategy.py:121-122` `round(..., 4)` is **Phase 22** and will be rewritten. Assert on the resolved ATR **fraction** / stop **distance**, not the 4dp output.
- **Measuring behavior change on live signal pulls only** — the funnel has emitted zero trades since 2026-08-16; every fix will read "no change."

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Indicator category taxonomy for the diversity guard | A new leg→category map | `voter.INDICATOR_CATEGORIES` + `SignalVoter.get_indicator_category` (`voter.py:36-63, 476-492`) | A second taxonomy will drift from the first. MACD's 2026-08-23 re-bucketing is exactly this hazard, with measured evidence. |
| Reading the ATR payload | A new parser | `_atr_levels`'s shape handling (`multi_strategy_ensemble.py:236-285`) | Already the CONTEXT-designated reference pattern; handles the non-dict and missing-key cases with loud logging. |
| Route-default drift detection | Bespoke asserts | The parametrized `WIRED_ROUTE_DEFAULTS` / `WIRED_HANDLER_DEFAULTS` tables (`test_endpoint_defaults_from_settings.py:133, 236`) | Two layers (OpenAPI schema + handler `Query` default) already covered; add rows, not files. |
| Driving the TA aggregate path in tests | An HTTP client / live stack | `await get_aggregated_signal(symbol=…, interval=…)` with an `AsyncMock` fetcher — `test_aggregator_new_legs.py:_patched()` | It is a plain async function; no HTTP, no TestClient, no running stack. |
| Structural bans (e.g. "no `.shift(-n)` in indicators") | Grep in CI | The AST-guard pattern in `tests/test_price_rounding_invariant.py` with a `SCANNED_FILES` list | Already the repo's sanctioned mechanism; grep produces false positives on comments and docstrings — `ichimoku.py` has 20 lines containing the word "future" that are all benign. |
| Account-size defaults | `capital: float = 100.0` or `= 10000.0` | `capital: Optional[float] = None` → `get_settings().paper_initial_balance` (reference: `mean_reversion_strategy.py:104,119-122`) | money.md: default args evaluate **once at import**, freezing the value and hiding it from the AST detector in `tests/test_account_size_invariant.py`. |

**Key insight:** every abstraction this phase needs already exists in the repo, built for exactly this purpose, with the failure it prevents documented in a comment. The phase's risk is not "what to build" — it is landing a fix in the wrong architectural layer, where it is silently inert.

---

## Leakage Suite Design (TA-AGG-04)

### The formulation problem — read this before writing any test

The requirement says: *"compute indicator at time `t` using `df[:t+1]`; compute again using full series; assert values at time `t` are identical."*

That works **only when the entry point returns a value per bar.** Ten of the thirteen modules return a scalar or dict describing **the last supplied bar**. For those, `f(df[:t+1])` is *definitionally* computed from data ≤ t, and there is no "value at t" to extract from `f(df_full)` — `f(df_full)` describes bar N. Comparing them is a category error; comparing `f(df[:t+1])` to itself is a tautology.

**Consequence:** a suite written literally to the requirement produces ~10 always-green tests. The planner must be told this explicitly, or TA-AGG-04 gets closed by a test that cannot fail.

### Tier 1 — series-returning entry points (genuinely non-trivial) ✅ the real leakage net

Assert `full.iloc[t] == prefix.iloc[-1]` for several `t` well past warm-up. This directly catches `.shift(-n)`, `center=True`, backward-fill, and whole-series normalization.

| Module | Series entry point | Output |
|---|---|---|
| `rsi.py` | `RSICalculator.calculate_series(df)` :271 | `pd.Series` |
| `macd.py` | `MACDCalculator.calculate_series(df)` :319 | `pd.DataFrame` |
| `bollinger_bands.py` | `BollingerBandsCalculator.calculate_series(df)` :271 | `pd.DataFrame` |
| `ichimoku.py` | `IchimokuCalculator.calculate_series(df)` :588 | `pd.DataFrame` |
| `squeeze_momentum.py` | `SqueezeMomentumIndicator.calculate(df)` :300 | `pd.DataFrame` |
| `sqzmom_enhanced.py` | `EnhancedSqueezeMomentum.calculate(df)` :830 | `pd.DataFrame` |

### Tier 2 — scalar/dict entry points (prefix-vs-full is tautological)

| Module | Entry point | Input shape | Output | Warm-up minimum |
|---|---|---|---|---|
| `rsi.py` | `RSICalculator.calculate(df)` :93 | DataFrame | `Optional[float]` | `period + 1` (:103) |
| `macd.py` | `MACDCalculator.calculate(df)` :138 | DataFrame | `Optional[Dict]` | `slow + signal` (:127,148) |
| `bollinger_bands.py` | `.calculate(df)` :55 | DataFrame | `Optional[Dict]` | `period` (:66) |
| `moving_averages.py` | `SMACalculator.calculate(df)` :33 / `EMACalculator.calculate(df)` :177 | DataFrame | `Optional[float]` | `period` (:43, :187) |
| `ichimoku.py` | `.calculate(df)` :113 | DataFrame | `Optional[Dict]` | `senkou_b + displacement` (:75,132) |
| `adx.py` | `.calculate(h, l, c)` :120 / `.calculate_with_signal(h,l,c)` :395 | 3 × `List[float]` | `Dict` / `(Dict,str,float)` | `min_required` (:148) |
| `atr.py` | `ATR.calculate(h, l, c, current_price)` :34 | 3 × list + float | `Dict` | `period + 1` (:64) |
| `stochastic.py` | `Stochastic.calculate(h, l, c)` :47 | 3 × `List[float]` | `Dict` | `period` |
| `trend_filter.py` | `TrendFilter.calculate(prices)` :36 | `List[float]` | `Dict` | `slow_period` (200) |
| `volume_confirmation.py` | `VolumeConfirmation.calculate(volumes, signal_type)` :35 | `List[float]` + str | `Dict` | `period` (20) |
| `rsi_divergence.py` | `RSIDivergenceCalculator.calculate(...)` :458 | see below | `Dict` | `period + lookback` |

**What to assert for tier 2 instead — three genuinely-falsifiable tests:**

1. **Scalar↔series agreement (where a series path exists):** `RSICalculator().calculate(df[:t+1]) == RSICalculator().calculate_series(df).iloc[t]`. Transitively pins the scalar path to a leakage-free series and would catch a scalar path that reads `iloc[-1]` of a whole-series transform.
2. **Suffix-independence:** `f(df[:t+1]) == f(df_poisoned[:t+1])` where `df_poisoned` is identical for bars `≤ t` and garbage after. Trivially true for a correct implementation, but it **fails loudly** if the function ever closes over an outer frame, caches globally, or mutates its input — all real hazards in a 12-concurrent-fetch service with a 30 s kline cache (`config.py:148`).
3. **AST structural guard:** no `.shift(-N)`, no `center=True`, no `rolling(...).mean().shift(-` in `app/indicators/*.py`, with an explicit allowlist for the audited `rsi_divergence` pivot windows. Use the `SCANNED_FILES` pattern from `tests/test_price_rounding_invariant.py`. **Verified clean today:** grep across all 13 modules found **zero** `shift(-`, `center=True`, or forward `.iloc[i+` reads outside `rsi_divergence.py:181,220`.

### Ichimoku — shift semantics resolved [VERIFIED: source read]

`IchimokuCalculator.calculate` does **not** forward-shift. It builds `senkou_span_a/b` as series and reads `iloc[cloud_index]` where `cloud_index = -self.displacement` (`:170-173`) — i.e. the cloud in force *now* was computed `displacement` bars **ago**, a strictly backward read. `chikou_span = df['close'].iloc[-1]` (`:178`) and `chikou_comparison_price = df['close'].iloc[-displacement-1]` (`:181-183`) are likewise backward. `_detect_*` at `:505-506` applies `.shift(self.displacement)` — a **positive** shift, which moves values later in time, again backward-looking. `calculate_series` (`:588`) documents at `:596` that spans are *"not shifted forward. Apply .shift(displacement) for actual"* — i.e. it returns spans aligned to their compute bar, leaving projection to the caller.

**Therefore:** the CONTEXT assertion "Senkou forward-shift is intentional (projection only, no future value used as input at t)" is **satisfied and testable as a positive assertion**: `calculate(df[:t+1])["senkou_span_a"]` must equal the value derivable from bars `≤ t - displacement`, and `calculate_series(df).iloc[t]` must equal `calculate_series(df[:t+1]).iloc[-1]`. Note `min_periods = senkou_b_period + displacement` (`:75`) — with the **new** P21-5 canonical `senkou_b = 120` and `displacement = 26`, Ichimoku needs **146 bars**, so the leakage fixture must supply ≥ 200 bars or Ichimoku silently returns `None` (`:132-135`) and its tests pass vacuously.

### `rsi_divergence` — the one real repainting site found ⚠️

`_find_pivot_lows` (`:176-186`) and `_find_pivot_highs` (`:215-225`) confirm a pivot at index `i` using **`series.iloc[i+1:i+threshold+1]`** — bars *after* `i` — and loop `range(threshold, len(series) - threshold)`.

**Is it leakage?** Within a single `f(df[:t+1])` call, no: all confirming bars are ≤ t, and the loop bound means the newest `threshold` bars are never reported as pivots. The signal is **lagged, not leaky** — which is correct behavior.

**But it is a repainting pattern**, and it is the one place in the suite where a prefix-vs-full comparison is both meaningful and expected to show a difference. The test that earns its keep:

```python
# Pivots at indices <= t - threshold must be IDENTICAL between prefix and full.
# Pivots at indices in (t - threshold, t] must be ABSENT from the prefix result —
# proving the calculator does not claim a pivot it cannot yet confirm.
```

If the first assertion ever fails, that *is* leakage. If the second fails, the calculator is reporting unconfirmed pivots. Neither is currently expected to fail; both are worth pinning. **This module is disabled as a voter** (`signal_aggregator.py:809`), so a finding here is correctness debt, not a live defect — say so in the test docstring so nobody escalates it.

### Aggregate-path leakage test — no HTTP required

`get_aggregated_signal` is a plain async function (`handlers/analysis.py:25`) that calls `get_fetcher().get_klines_as_dataframe(symbol, interval, limit=200)`. Drive it directly:

```python
# Source: services/technical-analysis/tests/test_aggregator_new_legs.py:_patched()
fetcher = AsyncMock()
fetcher.get_klines_as_dataframe = AsyncMock(return_value=df_prefix)
with patch("app.handlers.analysis.get_fetcher", return_value=fetcher):
    result = await get_aggregated_signal(symbol="SOLUSDT", interval="60")
```

Note the module-import binding: `handlers/analysis.py:22` executes `settings = get_settings()` **at import time**, and `get_fetcher` is imported into the `app.handlers.analysis` namespace at `:11`. Patch targets must therefore be `app.handlers.analysis.*` — the same namespace rule the existing test file documents in its module docstring (with the reason: an unpatched leg casts a *real* vote because ADX's failure default is `("HOLD", 0.3)`, not neutral).

**Fixture warm-up floor for the aggregate test:** ADX ≥ 29 bars, SQZMOM ≥ 25, Volume period 20, TrendFilter slow EMA 200, Ichimoku 146. **Use ≥ 250 bars** for any test intended to exercise real indicator math; use the existing 10-bar frame only when every leg is patched.

---

## TA-AGG-01 Residue — What Actually Exists

`services/technical-analysis/tests/test_aggregator_new_legs.py` **already contains 4 tests** [VERIFIED: file read]:

| Existing test | Covers |
|---|---|
| `test_adx_alone_can_carry_the_signal` | ADX reaches the vote |
| `test_sqzmom_alone_can_carry_the_signal` | SQZMOM reaches the vote |
| `test_unconfirmed_volume_penalizes_but_does_not_vote` | Volume scales confidence, never the label |
| `test_empty_vote_still_holds_with_the_new_legs_present` | Neutral fallback survives (HOLD @ 0.5) |

**Gaps against CONTEXT's residue list:**

1. **"ADX votes only when directional AND `conf > 0`"** — the `conf > 0` half is untested. `analysis.py:114` gates on `adx_signal in ("BUY","SELL") and float(adx_conf) > 0.0`; the comment at `:111-113` explains ADX's failure default is `("HOLD", 0.3)`, so a `("BUY", 0.0)` payload must be **rejected**. Add a case with `adx=("BUY", 0.0)`.
2. **"SQZMOM votes only when directional"** — the HOLD-suppression branch (`analysis.py:120`) is exercised only incidentally. Add an explicit `sqz=("HOLD", 0.9)` case asserting the high-confidence HOLD does **not** enter `signals`.
3. **Volume-absence vs volume-disconfirmation** — `analysis.py:182` treats `volume_ratio == 0.0` as *absence* (penalty 1.0, pass-through) per `_reject_response()`, distinct from a genuine sub-1.0 reading (penalty 0.5). Untested and easy to regress.
4. **Wiki documentation** — `wiki/modules/technical-analysis.md` exists (8,507 B, mtime 2026-07-30). It predates the ADX/SQZMOM vote wiring and the volume-penalty ladder. Needs a section describing the aggregate-endpoint vote **and** an explicit note that this endpoint is dashboard-only and diverges from the traded signal by construction.

---

## Closure Evidence — TA-AGG-02 / TA-AGG-03 (no code change)

| Requirement | Evidence (all verified this session) |
|---|---|
| **TA-AGG-02** (MACD 5/35/5 single-sourced) | Declaration: `services/technical-analysis/app/config.py:65-75` (`default_macd_fast=5`, `default_macd_slow=35`, `default_macd_signal=5`). Aggregate path: `handlers/analysis.py:41-45` constructs `MACDCalculator` from those fields. Route + handler layers pinned: `test_endpoint_defaults_from_settings.py:33-59` (call-arg assertion), `:91-101` (OpenAPI schema), `WIRED_ROUTE_DEFAULTS:135-137`, `WIRED_HANDLER_DEFAULTS:238-240`. Engine omits: `signal_aggregator.py:182-186` with the reason in the docstring at `:174-178`. |
| **TA-AGG-03** (BB std single-sourced) | Declaration: `config.py:81` (`default_bb_std=2.5`). Route pinned: `test_endpoint_defaults_from_settings.py:62-88`, `WIRED_ROUTE_DEFAULTS:139`, `WIRED_HANDLER_DEFAULTS:242`. **Caveat:** the engine still *sends* `std_dev: 2.5` explicitly (`signal_aggregator.py:224-227`) while omitting BB *period* — a partial omission and a numerically-agreeing mirror. Not a drift today; see §Mirror Inventory. |

---

## Mirror Inventory — larger than the audit's P21-7 list

The audit's P21-7 site list is the authoritative **minimum**. Research found three additional sites of the same drift class (numerically agreeing today, split on any env override). Presented for planner scoping — **do not silently expand scope**.

| Site | Literal | Mirrors | In audit P21-7? |
|---|---|---|---|
| `signal_aggregator.py:453,455` | `adx_val >= 20.0` (vote gate) | TA `default_adx_weak_trend_threshold=20.0` (`config.py:140`) | **Yes** |
| `handlers/signals.py:161-166` | `>= 25` / `< 20` regime re-derivation | TA `default_adx_trending_threshold=25.0` / `weak=20.0`; **TA already returns a `regime` field** (`fetch_adx` reads it at `signal_aggregator.py:448`) | **Yes** — prefer reading the returned field |
| `sqzmom_strategy_integration.py:239` | `adx_val < 20.0` | same as above | **Yes** |
| `sqzmom_strategy_integration.py:~284` | `ratio < 1.2` | volume-ratio gate; no TA settings field exists — needs a new **engine** Settings field | **Yes** |
| `market_regime.py:126,239` | `adx_period: int = 14` sent explicitly | `fetch_adx` **omits** period; TA `default_adx_period=14` | **Yes** |
| `signal_aggregator.py:226` | `std_dev: 2.5` sent | TA `default_bb_std=2.5`; BB *period* is omitted → partial omission | **No — new** |
| `signal_aggregator.py:135` | `period: int = 9` (RSI) | TA `default_rsi_period=9` | **No — new** |
| `signal_aggregator.py:324` | `limit: 300` (trend filter) | TA `default_trend_limit=300` | **No — new** |

**The engine-side mirror pattern already exists and is the model to copy** — `services/trading-engine/app/config.py:315-331`:

```python
    # 25.0 is the conventional Wilder ADX trend threshold and matches
    # technical-analysis `default_adx_trending_threshold`. Do NOT diverge the
    # two without recording why — ...
    adx_trending_threshold: float = Field(
        default=25.0, ge=0.0, le=100.0,
        description="... Mirrors technical-analysis default_adx_trending_threshold.",
    )
```

Every P21-7 site resolved to "engine Settings" should follow this shape: a `Field` with bounds, a description naming the TA counterpart, and a "Do NOT diverge" comment.

---

## Common Pitfalls

### Pitfall 1: ATR percent-vs-fraction — the phase's highest-severity trap ⚠️ [VERIFIED: live TA service, 2026-08-26]
**What goes wrong:** Threading real ATR into `simple_rsi` produces stop distances 100× too large whenever hourly ATR < 1%, yielding negative stop-losses on BUY.
**Why it happens:** `atr.py:91` emits `atr_pct` as a **percent**; `simple_rsi_strategy.py:68` guesses the unit with `if atr_pct > 1.0`. Sub-1% ATR is an explicitly-modelled regime (`atr.py:94` labels it LOW volatility), so the guess is wrong precisely in the calm-market case.
**Measured, not theoretical** — `GET :8004/api/v1/indicators/atr/{symbol}?interval=60`, 2026-08-26:

| Symbol | live `atr_pct` (60m) | `> 1.0` heuristic fires? | Fraction `simple_rsi` would use | Resulting stop distance (×2.0 mult) |
|---|---|---|---|---|
| BTCUSDT | **0.6658** | ❌ no | **0.666** (= 66.6%) | **133% of price → negative stop** |
| ETHUSDT | **0.8376** | ❌ no | **0.838** (= 83.8%) | **168% of price → negative stop** |
| BNBUSDT | **0.7182** | ❌ no | **0.718** (= 71.8%) | **144% of price → negative stop** |
| SOLUSDT | 1.1065 | ✅ yes | 0.01107 | 2.2% — correct |
| ADAUSDT | 1.4043 | ✅ yes | 0.01404 | 2.8% — correct |

Three of the five tradeable symbols are in the broken branch **at this moment**, and they are the three largest by notional. The `or`-chain at `:63-67` compounds it by falling through to `numeric_value()` (absolute ATR — BTC 522.1) when `atr_pct` is `0.0`, and `0.0` is precisely `atr.py:136`'s *failure* default, not a reading.
**How to avoid:** Ship Pattern 2 (explicit `atr_fraction` contract + `0 < fraction < 1` sanity bound + WARNING fallback) in the **same task** as Pattern 1 — never in a later task, and never behind a separate commit that could ship alone.
**Warning signs:** a computed `stop_loss <= 0`; `stop_distance / current_price > 0.20`; `[SIMPLE_RSI] ATR-based stop 66.58% × 2.0x` in the reasoning string.
**Test values to use:** parametrize the unit-contract test with the five measured values above — `0.6658` and `1.1065` alone cover both branches of the heuristic with real data.

### Pitfall 2: fixing a mirror in the layer that isn't live
**What goes wrong:** Changing `config.py:default_sma_period` to 21 while `signal_aggregator.py:254` still sends `period=21` looks correct and changes nothing; changing only the engine leaves bare-endpoint callers on 20.
**Why it happens:** Three layers (engine-sent / engine-omitted / TA constructor-default) look interchangeable in a diff.
**How to avoid:** For every P21-4/5/6/7 task, name the layer in the task title, and pin it with the **matching** test: engine-omission → a trading-engine test asserting `params` has no `period` key; TA declaration → a row in `WIRED_ROUTE_DEFAULTS`; constructor default → a `handlers.analysis` patch test.
**Warning signs:** a task whose only test is "Settings value equals 21."

### Pitfall 3: P21-4/5 is a two-sided change, not an engine deletion
**What goes wrong:** Planning it as "engine stops sending the param" and missing that TA's **defaults move** (`default_sma_period` 20→21, `default_ema_period` 20→21, Ichimoku 9/26/52→20/60/120).
**Why it happens:** CONTEXT frames it as adopting the MACD pattern; MACD's values already agreed, these do not.
**How to avoid:** Every dashboard caller, every bare `/api/v1/indicators/sma/{symbol}` call, and `analyze_timeframe` change output. Ichimoku's `min_periods` rises from 78 to **146** (`ichimoku.py:75`) — any fixture or caller supplying < 146 bars starts getting `None`. Audit fixture sizes across the TA test suite before landing.
**Warning signs:** Ichimoku tests going green-but-vacuous; `"Insufficient data for Ichimoku: need 146"` in logs.

### Pitfall 4: measuring behavior change against a dead funnel
**What goes wrong:** Before/after signal comparison on the 5 symbols shows zero difference; the phase is declared verified having proven nothing.
**Why it happens:** The live funnel has emitted **0 trades since 2026-08-16**; the 60m timeframe was HOLD in 2,820/2,820 evaluations and MTF consensus resolved HOLD in 90/90 recomputed cycles (`signal_aggregator.py:1114-1126`).
**How to avoid:** Drive the comparison through **constructed payloads** (the `test_ensemble_leg_wiring.py` builders) and/or `services/trading-engine/scripts/backtest_ensemble.py`. Use the live 5-symbol pull as a *smoke test* (no crash, ATR present in `metadata['atr']`), not as the behavior evidence.
**Warning signs:** a verification step whose success criterion is "signals unchanged."

### Pitfall 5: P21-1 and P21-2/3 pull in opposite directions
**What goes wrong:** Landing them in separate measurement windows and attributing the net delta to the wrong fix.
**Why it happens:** P21-1 **increases** admission (unlocks mean_reversion's SMA-deviation sub-signals, up to +0.25 confidence and a second firing route); P21-2/3 **decrease** it.
**How to avoid:** Land both, then measure once with per-fix ablation in the harness (four runs: baseline / +ATR / +gates / both).
**Warning signs:** a plan that verifies P21-1 with "trade count unchanged."

**Blocker for the ablation — the funnel cannot currently distinguish the causes.** `generate_signal` signals every rejection by returning `None`; the reason survives only in a log line. `auto_trader.py:4759-4767` records that as a single gate with a **fixed** `reason="ensemble_returned_hold"` and a `detail` naming only two causes ("weighted score below AGGREGATION_THRESHOLD or fewer than MIN_AGREEING_LEGS fired"). After P21-2/3 there will be **four** distinct causes — score, leg count, diversity block, MTF demotion — collapsing into one bucket whose detail string misdescribes two of them. The ablation cannot attribute a delta it cannot separate. **The plan must choose one:**
- **(a)** Give `generate_signal` a structured rejection reason (return a reason alongside `None`, or set it on a caller-visible attribute) and widen the funnel `reason`/`detail` per cause. Better telemetry, slightly larger blast radius.
- **(b)** Drive the ablation off log lines (`[ENSEMBLE] HOLD — …`, which already differ per cause) rather than funnel counters. Zero production change, but the measurement is text-parsing.

Option (a) is preferable — the funnel exists precisely to prevent "decorative telemetry" (see the module's own comment at `auto_trader.py:4718-4731`) — but (b) is legitimate if the planner wants zero behavior surface beyond the locked fixes. **State the choice in the plan; do not leave it implicit.**

### Pitfall 6: stale in-memory state and persisted leg weights
**What goes wrong:** A before/after delta that is really a restart artifact.
**Why it happens:** `StrategyPerformanceWeights.STATE_PATH = "/app/data/ensemble_weights.json"` (`multi_strategy_ensemble.py:84`) persists per-leg win rates **across restarts** and feeds `normalized_weights()` → every leg contribution. `aggregation/signal_cache.py` and the 30 s TA kline cache (`config.py:148`) add two more.
**How to avoid:** Snapshot `ensemble_weights.json` before and after; assert unchanged across the comparison, or pin weights in the harness. Rebuild + `--force-recreate` every changed service (CLAUDE.md §7 item 4).
**Warning signs:** leg contributions shifting with no code change on that leg.

### Pitfall 7: patching the indicator module instead of the handler namespace
**What goes wrong:** Unpatched legs cast real votes; the test measures the wrong thing.
**Why it happens:** `handlers/analysis.py:12-19` imports the calculators **into its own namespace**; patching `app.indicators.adx.ADXCalculator` does not affect the already-bound name. Compounded by non-neutral failure defaults: ADX `("HOLD", 0.3)`, SQZMOM HOLD `0.25`, Volume `_reject_response()` with `volume_ratio 0.0`.
**How to avoid:** Always `patch("app.handlers.analysis.<Name>")`. This is documented in `test_aggregator_new_legs.py`'s module docstring — read it before writing new TA tests.

### Pitfall 8: host-run test environment (repo-specific, has bitten before)
**What goes wrong:** trading-engine tests die at collection with `SettingsError: error parsing value for field "cors_origins"`.
**Why it happens:** `config.py` sets `env_file=".env"` **relative to cwd**.
**How to avoid:** `cd services/trading-engine && python3 -m pytest tests/ --no-cov`. **Never export env vars to override** — pydantic-settings v2 deep-merges `Dict` fields, so `SYMBOL_ALLOCATIONS` unions instead of replacing and allocations sum to 1.25. `tests/conftest.py` pins `env_file=None` at import time. Always `--no-cov`. TA tests run from `services/technical-analysis` (`pytest.ini` sets `pythonpath = .`, `asyncio_mode = auto`).

---

## Runtime State Inventory

This phase changes **declared parameter defaults** and **persisted-state consumers**, so runtime state must be checked even though it is not a rename.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| **Stored data** | `/app/data/ensemble_weights.json` (`multi_strategy_ensemble.py:84`) — per-leg win rates + trade counts, survives restarts, feeds `normalized_weights()` into every leg contribution. | **No migration.** Snapshot before/after the behavior comparison and assert unchanged, or pin weights in the harness. A drifting weight file is indistinguishable from a code-caused delta. |
| **Live service config** | Container **environment** overrides for the params being re-declared. Any `DEFAULT_SMA_PERIOD` / `DEFAULT_EMA_PERIOD` / `DEFAULT_ICHIMOKU_*` set in `.env` or `docker-compose.unified.yml` would **shadow** the new Settings defaults and silently defeat P21-4/5. | **Verify before landing:** `grep -iE 'DEFAULT_(SMA|EMA|ICHIMOKU)' docker-compose.unified.yml .env` (`.env` is gitignored — check the operator copy). If set, the plan must update or remove them. |
| **OS-registered state** | None — no scheduled tasks, cron, or pm2 entries touch TA indicator params. Verified: the only cron-like service is ml-retraining (no HTTP, GRU only, out of scope). | None. |
| **Secrets / env vars** | None. No secret name changes; no new env keys required unless P21-7 adds engine Settings fields (which are `Field(default=…)`, env-overridable but not required). | None. |
| **Build artifacts** | `services/technical-analysis/app/main.py.bak` (32,865 B, mtime 2025-11-10) is **gitignored but not dockerignored** — `.dockerignore` currently lists only `logs/ htmlcov/ .pytest_cache/ __pycache__/ *.log coverage.json .coverage* tests/standalone/`. Local builds COPY it into the image with pre-fix credentialed-wildcard CORS text. Runtime-inert. | **P21-8:** delete the file **and** add `*.bak` to `services/technical-analysis/.dockerignore`. Both, not either. |
| **Caches (extra)** | TA kline cache TTL 30 s (`config.py:148`); engine `aggregation/signal_cache.py`. | Wait ≥ 30 s or force-recreate between before/after pulls, or the "after" reads the "before" frame. |

---

## Code Examples

### Extending the drift-pinning table for P21-4/5 (TA side)

```python
# services/technical-analysis/tests/test_endpoint_defaults_from_settings.py
# Source: existing WIRED_ROUTE_DEFAULTS rows :140-141, :186-196 — already present.
# After P21-4/5 these rows keep passing with NEW values because they assert
# against settings, not literals. That is the point: the table needs no edit for
# the value change. What it CANNOT see is whether the ENGINE stopped sending
# overrides — that assertion must live in the trading-engine suite (below).
```

### Pinning engine omission for P21-4/5 (engine side — new file)

```python
# services/trading-engine/tests/test_engine_param_omission.py  (NEW)
# Run: cd services/trading-engine && python3 -m pytest tests/test_engine_param_omission.py --no-cov
#
# The TA test file cannot host this: it asserts on the trading-engine's
# outbound request params, and the two services do not share a Settings object.
# Pattern mirrors the MACD omission already in force at signal_aggregator.py:182-186.

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.signal_aggregator import SignalAggregator


@pytest.mark.parametrize(
    "method,forbidden",
    [
        ("fetch_sma",      {"period"}),
        ("fetch_ema",      {"period"}),
        ("fetch_ichimoku", {"tenkan_period", "kijun_period", "senkou_b_period"}),
        ("fetch_macd",     {"fast", "slow", "signal"}),   # regression guard on the closed fix
    ],
)
@pytest.mark.asyncio
async def test_engine_omits_params_owned_by_ta_settings(monkeypatch, method, forbidden):
    """TA Settings are the single source of truth for these params.

    Sending them from the engine re-creates the pre-2026-08-20 MACD drift in a
    new place: the engine's literal wins on the traded path while a bare
    endpoint call resolves to the TA default, and the two disagree silently.
    """
    agg = SignalAggregator()
    captured = {}

    async def _fake_get(url, params=None):
        captured["params"] = params or {}
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={...})   # minimal shape per endpoint
        return resp

    monkeypatch.setattr(agg.client, "get", AsyncMock(side_effect=_fake_get))
    await getattr(agg, method)("BTCUSDT", "60")

    leaked = forbidden & set(captured["params"])
    assert not leaked, (
        f"{method} still sends {sorted(leaked)} — TA Settings are no longer the "
        f"single source. params={captured['params']}"
    )
```

### Tier-1 leakage test shape (TA-AGG-04)

```python
# services/technical-analysis/tests/test_leakage_regression.py  (NEW)
# Run: cd services/technical-analysis && python3 -m pytest tests/test_leakage_regression.py --no-cov
import numpy as np
import pandas as pd
import pytest

BARS = 400          # > Ichimoku's post-P21-5 min_periods (120 + 26 = 146) with margin
PROBE_TS = (200, 275, 340)


def _synthetic_ohlcv(seed: int = 42, n: int = BARS) -> pd.DataFrame:
    """Deterministic, non-degenerate. A constant series makes every indicator
    agree trivially and hides leakage — use a real random walk."""
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    high = close * (1 + rng.uniform(0.000, 0.006, n))
    low = close * (1 - rng.uniform(0.000, 0.006, n))
    return pd.DataFrame(
        {"open": np.r_[close[0], close[:-1]], "high": high, "low": low,
         "close": close, "volume": rng.uniform(800, 1500, n)},
        index=pd.date_range("2026-01-01", periods=n, freq="1h"),
    )


@pytest.mark.parametrize("t", PROBE_TS)
def test_rsi_series_value_at_t_is_independent_of_future_bars(t):
    """A value at t that changes when bars t+1..N arrive is look-ahead leakage."""
    from app.indicators.rsi import RSICalculator

    df = _synthetic_ohlcv()
    calc = RSICalculator(period=9)

    full = calc.calculate_series(df)
    prefix = calc.calculate_series(df.iloc[: t + 1])

    # Exact equality, not approx: both are the same trailing computation over
    # identical inputs. A tolerance here would mask a real forward read.
    assert full.iloc[t] == prefix.iloc[-1], (
        f"RSI at t={t} moved when future bars were added: "
        f"{full.iloc[t]!r} (full) vs {prefix.iloc[-1]!r} (prefix)"
    )
```

### Structural guard (tier 3) — mirrors `test_price_rounding_invariant.py`

```python
# Bans forward-looking constructs across app/indicators/*.py.
# ALLOWLIST: rsi_divergence._find_pivot_{lows,highs} — audited 2026-08-26; its
# iloc[i+1:i+threshold+1] confirmation window is bounded by the input's last bar,
# so it lags rather than leaks. Any NEW forward read must be justified here.
FORWARD_SMELLS = ("shift(-", "center=True")
```

---

## State of the Art

| Old approach (as documented in STATE.md 2026-07-29 / REQUIREMENTS.md 2026-05-23) | Current reality | When changed | Impact on this phase |
|---|---|---|---|
| Aggregator votes RSI + MACD + TrendFilter only | ADX votes (gated directional + conf>0), SQZMOM votes, Volume is a post-vote penalty | 2026-04/05 → 2026-08-17 | **TA-AGG-01 re-scoped to test+doc residue.** Do not re-implement. |
| MACD 5/35/5 and BB std 2.5 hardcoded in route signatures | Settings-sourced, dual-layer pinned | 2026-08-20 | **TA-AGG-02/03 CLOSED** — evidence only. |
| MACD bucketed as MOMENTUM in the diversity gate | MACD → TREND | 2026-08-23 (`voter.py:56`) | The diversity gate is **stricter** than older docs imply; the P21-2 mirror must use the current map. |
| Ensemble confidence normalized over all three legs | Normalized over **directional** legs only | 2026-08-23 (`multi_strategy_ensemble.py:383-404`) | A single leg can now clear 0.30 — which is exactly why P21-2 matters. |
| MTF `consensus_action` computed and never read | Applied to `.action` at `:1133` | 2026-08-22 (`2cd7e76`) | **P21-3 becomes a one-place fix** — the demoted action already reaches the ensemble. |
| `metadata["atr_stop_loss"]` flat keys | Nested `metadata["atr"]` with `stop_loss_long/short` | 2026-08-08 | `_atr_levels` is the reference; the flat-key shape has **no** production writer. |
| RSI thresholds 75/25 | 80/20 (`rsi.py:80-81`) | — | `signal_aggregator.py:143` docstring still says 75/25 → P21-8. |

**Deprecated / do not use:**
- `aggregator_mode = 'minimal' | 'full'` env from TA-AGG-01's original text — explicitly dropped by CONTEXT (YAGNI on a dashboard-only endpoint).
- `settings.bollinger_std_dev` — attribute never existed; the real field is `default_bb_std`.
- Engine `app/multi_timeframe.py` — orphaned dead module carrying a divergent `limit=200`; revival trap only, out of scope.
- `RSI_DIVERGENCE` as a voter — deliberately disabled (`signal_aggregator.py:809`). Still in scope for the leakage suite as a module.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| ~~A1~~ | ~~`atr_pct < 1.0` is frequent enough to make Pitfall 1 a live hazard~~ **RESOLVED — no longer an assumption.** Measured against the running TA service 2026-08-26: BTC 0.666, ETH 0.838, BNB 0.718 are all in the broken branch; SOL 1.107 and ADA 1.404 are not. | Pitfall 1 | — (verified) |
| A2 | `Stochastic.calculate` warm-up is `period` bars. Signature and list-input shape verified; the exact guard line was not read. | Leakage table | A too-short fixture makes the Stochastic leakage test vacuous. Mitigated by the 400-bar fixture. |
| A3 | No container env var currently overrides `DEFAULT_SMA_PERIOD` / `DEFAULT_EMA_PERIOD` / `DEFAULT_ICHIMOKU_*`. `.env` is gitignored and was not read. | Runtime State Inventory | An existing override silently defeats P21-4/5. Listed as a required pre-check, not an assumption to build on. |
| A4 | `wiki/modules/technical-analysis.md` does not yet document the ADX/SQZMOM vote or the volume-penalty ladder. Inferred from mtime 2026-07-30 predating the 2026-08-17 SQZMOM re-enable; file contents not read. | TA-AGG-01 residue | If already documented, the doc task shrinks. Planner should read the file first. |
| A5 | `services/trading-engine/scripts/backtest_ensemble.py` is a viable offline harness for the ablation measurement. Its existence and `MultiStrategyEnsemble(...)` usage at `:348` are verified; its current runnability is not. | Environment Availability | If stale, fall back to constructed-payload tests using the `test_ensemble_leg_wiring.py` builders — which are verified working. |

---

## Open Questions (RESOLVED)

1. **Does the P21-2 diversity guard need to survive `multi_indicator` firing alone?** — RESOLVED: treated as diverse by construction (upstream ≥2-category gate), implemented in 21-06.
   - *Known:* `multi_indicator` alone has already cleared CoreAggregator's own ≥2-category gate, so blocking it would be a double-jeopardy regression on the strongest leg.
   - *Unclear:* whether the planner wants the guard to treat `multi_indicator` as automatically ≥2 categories, or to read `consensus_count` / re-derive from `aggregator_signal.indicators`.
   - *Recommendation:* treat `multi_indicator` as satisfying diversity by construction, and say so in a code comment naming the upstream gate. Re-deriving invites the two gates to drift.

2. **Narrow (`demoted_to_hold` key) vs broad (`action == HOLD`) MTF gating.** — RESOLVED: narrow `demoted_to_hold` route, implemented in 21-05; regime hard-block recorded as candidate follow-up at the 21-09 checkpoint.
   - *Known:* narrow matches CONTEXT's locked wording exactly and costs one metadata key; broad is simpler and needs no schema change.
   - *Unclear:* whether the operator would also want the regime hard-block (`:1189`) to gate all legs — it is arguably the same class of defect but is **not** in CONTEXT.
   - *Recommendation:* implement narrow; record the regime-block case as a candidate follow-up rather than silently widening scope.

3. **`limit=200` in `handlers/analysis.py:33` and `:271` — settings field or documented literal?** — RESOLVED: `default_aggregate_limit` settings field with derived Ichimoku floor validation, implemented in 21-02.
   - *Known:* CONTEXT explicitly leaves this to the planner, requiring only that whichever wins is pinned by a test.
   - *Recommendation:* move to `default_aggregate_limit` for consistency with the 2026-08-20 rewire — **but** note the Ichimoku interaction: post-P21-5, Ichimoku needs 146 bars, so 200 leaves only 54 bars of headroom. If the limit becomes env-overridable, add a floor validation.

4. **Should the leakage suite fail the build on `rsi_divergence` repainting?** — RESOLVED: positive assertions on correct behavior (stable confirmed pivots, absent unconfirmed), no xfail, implemented in 21-01.
   - *Known:* it is lagged, not leaky, and the module is disabled as a voter.
   - *Recommendation:* assert the *correct* behavior (stable confirmed pivots, absent unconfirmed pivots) so a future change to centered-and-reported would fail. Do not mark it xfail — `.claude/rules/testing.md` forbids skip/xfail without a tracking requirement ID.

---

## Environment Availability

Probed 2026-08-26 in this session.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 | All host tests | ✓ | 3.12.3 | — |
| pytest | TA + engine suites | ✓ | 9.0.3 | — |
| Docker (context `default`) | Rebuild + `--force-recreate` (CLAUDE.md §7) | ✓ | context = `default` (correct — not `desktop-linux`) | — |
| `crypto-bot-ta` :8004 | Live 5-symbol smoke pull; A1 resolution | ✓ | Up 26 h (healthy) | Direct handler call with mocked fetcher |
| `crypto-bot-trading` :8005 | Live ensemble smoke | ✓ | Up 2 h (healthy) | `scripts/backtest_ensemble.py` / constructed payloads |
| `crypto-bot-timescaledb` | Kline source for live pulls | ✓ | Up 20 h (healthy) | Synthetic OHLCV fixture |
| `crypto-bot-postgres` | Engine app state | ✓ | Up 20 h (healthy) | — |
| `crypto-bot-market-data` :8002 | Candle ingest | ✓ | Up 20 h (healthy) | — |
| Full 14-container stack | End-to-end verification | ✓ | all healthy | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none currently — but note the recurring hazard: host suspend has repeatedly caused Docker Desktop to stage **directories** over single-file bind mounts, killing postgres/timescale with `exit=127 "not a directory"` (2026-08-22, and again around 2026-08-25). If that recurs mid-phase, the fix is `docker compose -f docker-compose.unified.yml up -d --no-deps --force-recreate <svc>`, and the plan must not hard-depend on the stack: **every correctness assertion in this phase is provable by host-run tests with mocked I/O.** Only the §7 smoke evidence needs the stack.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 (both services) |
| TA config file | `services/technical-analysis/pytest.ini` (`pythonpath = .`, `asyncio_mode = auto`, `--strict-markers`, `-p no:warnings`) |
| Engine config file | `services/trading-engine/pytest.ini` (injects `--cov --strict-config` — **must pass `--no-cov`**) + `tests/conftest.py` pinning `Settings.model_config["env_file"] = None` at import time |
| TA quick run | `cd services/technical-analysis && python3 -m pytest tests/test_leakage_regression.py tests/test_aggregator_new_legs.py --no-cov -q` |
| TA full suite | `cd services/technical-analysis && python3 -m pytest tests/ --no-cov -q` |
| Engine quick run | `cd services/trading-engine && python3 -m pytest tests/strategies/ --no-cov -q` |
| Engine full suite | `cd services/trading-engine && python3 -m pytest tests/ --no-cov -q` |

**Non-negotiable:** trading-engine tests run from `services/trading-engine` (cwd-sensitive `env_file`), always `--no-cov`, and **never** with env-var overrides (pydantic-settings v2 deep-merges `Dict` fields → `SYMBOL_ALLOCATIONS` sums to 1.25). trading-engine has **no** in-container test path (`Dockerfile` copies `app/` only). api-gateway is unaffected by this phase.

### Phase Requirements → Test Map

| Req ID | Behavior | Test type | Automated command | File exists? |
|--------|----------|-----------|-------------------|--------------|
| TA-AGG-01 | ADX votes only when directional **and** conf > 0 | unit | `cd services/technical-analysis && python3 -m pytest tests/test_aggregator_new_legs.py -k adx --no-cov` | ✅ file exists — **add** zero-confidence case |
| TA-AGG-01 | SQZMOM HOLD (conf 0.9) does not vote | unit | `... -k sqzmom --no-cov` | ✅ file exists — **add** case |
| TA-AGG-01 | Volume scales confidence, never the label; ratio 0.0 = absence (penalty 1.0) | unit | `... -k volume --no-cov` | ✅ partial — **add** absence-vs-disconfirmation case |
| TA-AGG-01 | Aggregate-endpoint vote documented | manual-only | doc review of `wiki/modules/technical-analysis.md` | ❌ Wave 0 — prose, not automatable |
| TA-AGG-02 | MACD route + handler defaults track Settings; engine omits | unit | `cd services/technical-analysis && python3 -m pytest tests/test_endpoint_defaults_from_settings.py --no-cov` | ✅ exists, passing — closure evidence only |
| TA-AGG-03 | BB std default tracks Settings | unit | same command | ✅ exists, passing — closure evidence only |
| TA-AGG-04 | Series indicators: value at t independent of bars > t | unit | `cd services/technical-analysis && python3 -m pytest tests/test_leakage_regression.py --no-cov` | ❌ Wave 0 |
| TA-AGG-04 | Ichimoku Senkou uses only bars ≤ t − displacement | unit | `... -k ichimoku --no-cov` | ❌ Wave 0 |
| TA-AGG-04 | `rsi_divergence` confirmed pivots stable; unconfirmed absent | unit | `... -k divergence --no-cov` | ❌ Wave 0 |
| TA-AGG-04 | Aggregate path prefix-stable (mocked fetcher, no HTTP) | integration | `... -k aggregate --no-cov` | ❌ Wave 0 |
| TA-AGG-04 | AST guard: no `shift(-`/`center=True` in `app/indicators/` | unit | `... -k structural --no-cov` | ❌ Wave 0 |
| P21-1 | Legs resolve real ATR when `metadata['atr']` present | unit | `cd services/trading-engine && python3 -m pytest tests/strategies/test_ensemble_atr_levels.py --no-cov` | ✅ file exists — **extend** |
| P21-1 | 2% fallback **only** when ATR genuinely absent | unit | same file | ✅ file exists — **extend** |
| P21-1 | **Unit contract:** `atr_pct = 0.8` (percent) → fraction 0.008, **not** 0.8 | unit | `cd services/trading-engine && python3 -m pytest tests/strategies/test_ensemble_leg_wiring.py -k atr_unit --no-cov` | ❌ Wave 0 — **highest-value new test in the phase** |
| P21-1 | mean_reversion `PRICE_BELOW_SMA` sub-signals fire when ATR present | unit | `... -k mean_reversion --no-cov` | ✅ file exists — **extend** (pins the old broken behavior is gone) |
| P21-2 | Single-source (RSI-only) agreement does not clear the ensemble | unit | `cd services/trading-engine && python3 -m pytest tests/strategies/ -k diversity --no-cov` | ❌ Wave 0 |
| P21-2 | `multi_indicator` alone still clears (no double jeopardy) | unit | same | ❌ Wave 0 |
| P21-2/3 | **Behavioral lock:** `multi_indicator` as the sole directional leg at conviction ≥ 0.30 must still produce a signal | unit (guard) | `cd services/trading-engine && python3 -m pytest tests/ -k threshold_lock --no-cov` | ❌ Wave 0 — **this is the load-bearing lock assertion** |
| P21-2/3 | Constants `MIN_AGREEING_LEGS=1`, `AGGREGATION_THRESHOLD=0.10`, `min_signal_confidence=0.30` unchanged | unit (guard) | same | ❌ Wave 0 — cheap, but **not sufficient alone** (see note) |
| P21-3 | MTF demotion suppresses all three legs | unit | `cd services/trading-engine && python3 -m pytest tests/test_mtf_confidence_consolidation.py --no-cov` | ✅ file exists — **extend** |
| P21-3 | `demoted_to_hold` written when and only when consensus is demoted | unit | same file | ❌ Wave 0 |
| P21-4/5 | Engine omits SMA/EMA/Ichimoku period params | unit | `cd services/trading-engine && python3 -m pytest tests/test_engine_param_omission.py --no-cov` | ❌ Wave 0 (new file — TA suite cannot host it) |
| P21-4/5 | TA Settings carry canonical 21 / 20-60-120; OpenAPI descriptions agree with defaults | unit | `cd services/technical-analysis && python3 -m pytest tests/test_endpoint_defaults_from_settings.py --no-cov` | ✅ exists — value change auto-covered; **add** description-vs-default assertion |
| P21-6 | Aggregate + MTF handlers construct voters from `settings.default_*` | unit | `cd services/technical-analysis && python3 -m pytest tests/test_aggregator_new_legs.py -k settings --no-cov` | ❌ Wave 0 |
| P21-7 | ADX gate threshold resolves from engine Settings / TA `regime` field | unit | `cd services/trading-engine && python3 -m pytest tests/aggregation/ -k adx --no-cov` | ❌ Wave 0 |
| P21-8 | No capital literals; account-size invariant holds | unit (guard) | `python3 -m pytest tests/test_account_size_invariant.py --no-cov` (repo root) | ✅ exists — must stay green |
| P21-8 | `main.py.bak` absent; `*.bak` dockerignored | unit | `cd services/technical-analysis && python3 -m pytest tests/ -k dockerignore --no-cov` | ❌ Wave 0 (or verify by inspection) |

### Sampling Rate

- **Per task commit:** the task's own targeted file, e.g. `cd services/technical-analysis && python3 -m pytest tests/test_leakage_regression.py --no-cov -q` (< 30 s).
- **Per wave merge:** the changed service's full suite — `cd services/technical-analysis && python3 -m pytest tests/ --no-cov -q` and/or `cd services/trading-engine && python3 -m pytest tests/ --no-cov -q`.
- **Phase gate:** both full suites green + repo-root `tests/test_account_size_invariant.py` + `tests/test_account_config_sync.py` + `tests/test_price_rounding_invariant.py`, then rebuild + `--force-recreate` of `technical-analysis` and `trading-engine`, then `/verify-stack`.

### Wave 0 Gaps

- [ ] `services/technical-analysis/tests/test_leakage_regression.py` — TA-AGG-04 (new file; needs the 400-bar `_synthetic_ohlcv` fixture)
- [ ] `services/trading-engine/tests/test_engine_param_omission.py` — P21-4/5 (new file; TA suite structurally cannot host it)
- [ ] ATR **unit-contract** test in `tests/strategies/test_ensemble_leg_wiring.py` — P21-1 (highest value; the `_atr(value)` builder at `:92` exists but carries no `atr_pct` metadata and must be extended)
- [ ] Threshold-lock guard test — **must assert behavior, not just constants.** A constants-only test passes in *both* worlds and proves nothing: a diversity guard that blocks the single-firing-leg case leaves all three constants untouched while changing the effective gate. The load-bearing assertion is *`multi_indicator` alone at conviction ≥ 0.30 still fires* — that is what would fail if someone smuggled `MIN_AGREEING_LEGS=2` in behind the diversity guard, and it is what distinguishes the category framing from a threshold change. Keep the constants assertion as a cheap companion.
- [ ] **Suite non-uniformity is deliberate.** The leakage suite has different assertions per module by design (tier 1 / tier 2 / structural). A reviewer or plan-checker asking for "13 matching tests" should be pointed at §"The formulation problem" — uniformity here would mean ~10 tests that cannot fail.
- [ ] Leg source-diversity tests — P21-2 (both the block case and the `multi_indicator`-alone pass case)
- [ ] `demoted_to_hold` metadata + all-leg suppression tests — P21-3
- [ ] P21-6 constructor-sourcing tests in `test_aggregator_new_legs.py`
- [ ] No framework install needed — pytest 9.0.3 present, both `pytest.ini` files present, no new `conftest.py` required.

---

## Security Domain

`security_enforcement: true`, `security_asvs_level: 1` (`.planning/config.json`).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard control |
|---------------|---------|------------------|
| V2 Authentication | **no** | Phase touches no auth path. TA and trading-engine are internal-mesh services behind api-gateway; no credential handling changes. |
| V3 Session Management | **no** | No sessions involved. |
| V4 Access Control | **no** | No endpoint is added, removed, or re-permissioned. `/api/v1/indicators/signal/{symbol}` already exists (`main.py:794`). |
| V5 Input Validation | **yes** | Query params already bounded via FastAPI `Query(ge=…, le=…)`. **P21-5 must preserve bounds:** Ichimoku's `tenkan ge=5 le=30`, `kijun ge=20 le=120`, `senkou_b ge=40 le=200` (`main.py:568-570`). New canonical 20/60/120 fits all three — verified. `test_endpoint_defaults_from_settings.py:104-126` already pins that "only `default=` may move; `ge`/`le`/`description` are a live contract." |
| V6 Cryptography | **no** | No crypto in scope. |
| V7 Error Handling / Logging | **yes (advisory)** | New WARNING logs for unusable ATR payloads must not log secrets — they log only numeric indicator metadata. Safe. |
| V12 Files & Resources | **yes (minor)** | P21-8 deletes `app/main.py.bak` and adds `*.bak` to `.dockerignore` — **reduces** image contents. Strictly a hardening win. |
| V14 Configuration | **yes** | P21-4/5 move parameter declarations into `Settings`, increasing env-override surface. All fields are typed `Field(default=…)` with bounds; no secret is introduced. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard mitigation | Status in this phase |
|---|---|---|---|
| Config drift between mesh services causing divergent enforcement | Tampering | Single source of truth + drift-pinning tests | **This is literally the phase's subject** (P21-4/5/6/7) |
| Stale artifact baked into an image (`main.py.bak` with pre-fix CORS text) | Information Disclosure | `.dockerignore` + delete | P21-8; runtime-inert today, fixed here |
| Credentialed wildcard CORS | Spoofing | `allow_credentials=False` with `["*"]`, or explicit origins | TA: **already closed** (`e091826`); wildcard retained deliberately for an internal service — CONTEXT: no change. sentiment-analysis-service still holds the hole → **deferred, out of scope** |
| Unbounded query params → resource exhaustion | DoS | `Query(ge=, le=)` bounds | Preserved; pinned by existing test |
| Env-override widening the config attack surface | Tampering | Typed `Field` with bounds + explicit "Do NOT diverge" documentation | Follow the `config.py:315-331` precedent for every new engine mirror field |

**No `security_block_on: high` finding is expected from this phase** — it removes a stale artifact and reduces config drift. If the planner adds any new endpoint or relaxes a `Query` bound, that changes and must be re-reviewed.

---

## Project Constraints (from CLAUDE.md)

Directives extracted from `./CLAUDE.md` and `.claude/rules/*.md` that bind this phase. Treat with the same authority as CONTEXT.md locked decisions.

| # | Directive | Source | Binding on |
|---|---|---|---|
| C1 | Account is **$10,000** (ADR-029). Never write an account-size literal — **a bare `10000` is numerically correct and still a defect.** `100.0` is doubly wrong (stale size). | CLAUDE.md §1, money.md | **P21-8** — `multi_strategy_ensemble.py:291`, `simple_rsi_strategy.py:49`, `advanced_position_sizing.py:107` docstring |
| C2 | In-container code (`services/*/app/**`) reads the service's own `Settings` (`settings.paper_initial_balance`). **Never `import shared.account`** — repo-root `shared/` is outside every Docker build context and will `ImportError`. Host-run code (`tests/`, `backtesting/`) imports `shared.account` directly. | CLAUDE.md §1, money.md | P21-8 fix shape; every new test fixture |
| C3 | Never `def f(x = get_settings().y)` — Python evaluates defaults **once at import**, freezing the value and hiding it from the AST detector in `tests/test_account_size_invariant.py`. Use `Optional[float] = None` → resolve in the body. | money.md | P21-8 (`mean_reversion_strategy.py:104,119-122` is the reference) |
| C4 | **Units trap:** `max_risk_per_trade` is a **fraction** (0.10); `max_daily_loss_pct`/`max_position_size_pct`/`max_total_exposure_pct` are **percents**. Comparing across them without normalizing produces a check that silently never fires. **This shipped once.** | CLAUDE.md §5, money.md | Directly analogous to **Pitfall 1** — the ATR percent/fraction confusion is the same class of defect in the indicator domain |
| C5 | **No threshold relaxation.** Per-trade 2% LIVE; paper 10%; daily breaker 12%. | CLAUDE.md §5 | Reinforces CONTEXT's threshold lock; the diversity guard must not become a threshold change |
| C6 | `round(price, 2)` is catastrophic for sub-$1 assets. Fix sites when touched; add no new ones. | CLAUDE.md §10, money.md | **Scope note:** `simple_rsi_strategy.py:121-122` `round(…, 4)` is **Phase 22**. P21-1 changes the ATR feeding those exact lines — assert on stop *distance*, not the 4dp output |
| C7 | **Verification standards:** never declare "working end-to-end" on HTTP 200 alone. Need live exchange URL in logs, a downstream notification actually received, a persisted DB row, and a **restart** of any service whose config changed. | CLAUDE.md §7 | Phase gate. Note: this phase changes **no** persisted trade rows — the DB-row leg is N/A; state that explicitly rather than faking it |
| C8 | Use `docker-compose.unified.yml`; plain `docker-compose.yml` is incomplete and disagrees on values. | CLAUDE.md §6 | Every rebuild/recreate command in the plan |
| C9 | Always `--no-cov`; trading-engine host tests from `services/trading-engine`; **never** export env vars to override settings; api-gateway in-container (not touched here). | .claude/rules/testing.md | Every test command |
| C10 | Never write a test whose fixture hardcodes **any** balance literal — `10000` included. | .claude/rules/testing.md | All new tests. **Enforcement gap verified:** `scripts/check_capital_literals.py:202` scopes to `services/<name>/app/...` only ("a service's tests/ and scripts/ are not"), and `tests/test_account_size_invariant.py:42-69` uses an explicit `SCANNED_FILES` list that excludes `services/*/tests/` — with a comment at `:81-89` acknowledging this. So `test_ensemble_leg_wiring.py:280`'s `capital=100.0` is **unguarded, not allowlisted**. New tests must follow the rule **by convention** — no guard will catch a violation. Prefer `capital=None` (resolves from Settings) in new ensemble tests. |
| C11 | Parallel agents share one git index — commit with a pathspec (`git commit -- <paths>`); never `git add -A`; `git status` exceeds 60 s on this NTFS/WSL mount. | .claude/rules/testing.md, CLAUDE.md §8 | Every commit task |
| C12 | Commit in logical chunks, one concern per commit, conventional messages (`fix(technical-analysis):`, `test(trading-engine):`). | CLAUDE.md §8, CONTEXT specifics | Commit granularity |
| C13 | ADRs live **only** in `wiki/decisions/`. `progress.md` is a session log, not a decision record. | CLAUDE.md §4, §8 | If P21-2/3's design is recorded as a decision, it is an ADR in `wiki/decisions/` |
| C14 | Never commit `.env`; never `git clean -fdx`. | CLAUDE.md §5 | The `.env` pre-check in Runtime State Inventory is **read-only** |
| C15 | No edge/profitability claim without DSR/CPCV. **Profitability is explicitly not a goal of this phase.** | CLAUDE.md §2, design spec §Goal | The behavior-change measurement reports *admission counts and signal deltas* — never P&L, never "improved" |

---

## Sources

### Primary (HIGH confidence) — all read at `file:line` in this session

- `.planning/phases/21-ta-aggregator-widening-leakage-net/21-CONTEXT.md` — locked decisions (copied verbatim above)
- `.planning/audits/2026-08-26-ta-signal-path-audit.md` — confirmed-open defect list, fix-routing rule
- `docs/superpowers/specs/2026-08-26-ta-signal-path-correctness-design.md` — approved design, constraints, verification standards
- `.planning/REQUIREMENTS.md:59-62, 188-191` — TA-AGG-01..04 original text
- `.planning/config.json` — `nyquist_validation: true`, `security_enforcement: true`, `security_asvs_level: 1`, `tdd_mode: true`
- `services/trading-engine/app/signal_aggregator.py` — `:29-90` MTF consolidation, `:131-166` fetch_rsi, `:168-209` MACD omission pattern, `:211-248` BB, `:250-310` SMA/EMA, `:393-424` **fetch_atr**, `:425-476` fetch_adx, `:601-680` Ichimoku, `:769-878` fetch_all_indicators, `:1060-1192` MTF path
- `services/trading-engine/app/strategies/multi_strategy_ensemble.py` — `:33-56` constants, `:59-72` EnsembleSignal, `:75-201` weights, `:204-233` class, `:235-285` `_atr_levels`, `:287-440` generate_signal
- `services/trading-engine/app/strategies/simple_rsi_strategy.py` — full file (124 lines)
- `services/trading-engine/app/strategies/mean_reversion_strategy.py` — `:20-50` dataclass, `:104-258` generate_signal
- `services/trading-engine/app/auto_trader.py:4649-4808` — ensemble entry, funnel gates, the ATR-absence comment at `:4718-4724`
- `services/trading-engine/app/models/signal.py` — `IndicatorSignal`, `numeric_value()`, `TradingSignal`
- `services/trading-engine/app/aggregation/voter.py` — `:36-63` categories, `:476-492` `get_indicator_category`, `:494-586` category consensus + diversity
- `services/trading-engine/app/config.py:315-331` — the engine-side mirror precedent
- `services/trading-engine/app/strategies/hybrid_strategy_router.py:100-120` — dead ATR fallback
- `services/trading-engine/app/handlers/signals.py:155-172` — ADX regime re-derivation
- `services/trading-engine/app/aggregation/market_regime.py:120-132, 232-245`
- `services/trading-engine/app/strategies/sqzmom_strategy_integration.py:235-245, 280-290`
- `services/technical-analysis/app/config.py` — full file (167 lines)
- `services/technical-analysis/app/handlers/analysis.py:1-300` — aggregate + MTF handlers
- `services/technical-analysis/app/main.py:563-575, 794-810` — Ichimoku route, aggregate route
- `services/technical-analysis/app/indicators/*.py` — all 13 modules: class/entry-point/signature enumeration, warm-up guards, forward-smell grep
- `services/technical-analysis/app/indicators/atr.py:91,94,113,136` — **the percent-unit fact**
- `services/technical-analysis/app/indicators/ichimoku.py:75,113-185,442,491,505-506,588-596,655-701` — shift semantics
- `services/technical-analysis/app/indicators/rsi_divergence.py:155-232, 300-320, 390-400` — **the repainting pivot windows**
- `services/technical-analysis/tests/test_endpoint_defaults_from_settings.py` — full file (301 lines)
- `services/technical-analysis/tests/test_aggregator_new_legs.py` — full file
- `services/technical-analysis/pytest.ini`, `services/technical-analysis/.dockerignore`
- `services/trading-engine/tests/strategies/test_ensemble_leg_wiring.py` — builders + tests
- `./CLAUDE.md`, `.claude/rules/money.md`, `.claude/rules/testing.md`

### Secondary (MEDIUM confidence)

- **Live ATR probe, 2026-08-26** — `GET http://localhost:8004/api/v1/indicators/atr/{BTC,ETH,SOL,BNB,ADA}USDT?interval=60` against the running `crypto-bot-ta` container. Resolves A1 and upgrades Pitfall 1 to VERIFIED. Point-in-time market data: re-measuring on another day will give different values, but `atr.py:94`'s explicit `< 1.0` LOW-volatility bucket means the broken branch is a *designed-for* regime, not an outlier.
- `scripts/check_capital_literals.py:100-202` + `tests/test_account_size_invariant.py:42-89` — guard scoping (service `app/` only; `services/*/tests/` explicitly uncovered)
- `docker ps` output 2026-08-26 — 14 containers healthy; `docker context show` → `default` (point-in-time; the bind-mount hazard is documented in the operator's memory index)
- `python3 --version` → 3.12.3; `python3 -m pytest --version` → 9.0.3

### Tertiary (LOW confidence)

- None. **No WebSearch, Context7, or external documentation was consulted, and none was needed** — this phase has zero external-library surface. Every claim above resolves to a file in this repository or a command run in this session.

---

## Metadata

**Confidence breakdown:**

| Area | Level | Reason |
|------|-------|--------|
| Standard stack | **HIGH** | No new packages. Existing versions verified by direct command execution. |
| Architecture / call graph | **HIGH** | Every edge in the diagram read at `file:line` this session; no inference. |
| ATR unit trap (Pitfall 1) | **HIGH** — code path *and* live frequency both verified. Code: `atr.py:91` percent, `simple_rsi:68` heuristic, `atr.py:94` sub-1% bucket, `atr.py:136` zero-default. Frequency: measured 3/5 symbols in the broken branch on 2026-08-26. |
| MTF gating mechanism | **HIGH** | `:1133` assignment and `:1137` pre-demotion storage both read directly. |
| Leg diversity mechanism | **HIGH** for available data (`indicators_aligned` field exists; `INDICATOR_CATEGORIES` reusable); **MEDIUM** for design choice (Claude's-discretion; the `MIN_AGREEING_LEGS=2` tension is surfaced, not resolved) |
| Leakage suite feasibility | **HIGH** | All 13 entry points + warm-up guards enumerated; forward-smell grep run across every module; Ichimoku and rsi_divergence semantics read in full. |
| TA-AGG-01/02/03 closure | **HIGH** | Existing tests read line-by-line; the 4 present tests and the specific gaps are file-verified. |
| Pitfalls | **HIGH** | Six of eight are documented in the repo's own code comments with measured evidence; two (1 and 5) are new derivations from source. |
| Environment | **HIGH** (point-in-time) | Probed this session; stack healthy. Known-recurring bind-mount hazard flagged with its fix. |

**Research date:** 2026-08-26
**Valid until:** 2026-09-26 for the architectural findings (intra-repo, no external drift). **Re-verify `file:line` references if any commit lands on `signal_aggregator.py`, `multi_strategy_ensemble.py`, or `handlers/analysis.py` before planning** — all three are actively edited (the newest referenced change is 2026-08-23).
