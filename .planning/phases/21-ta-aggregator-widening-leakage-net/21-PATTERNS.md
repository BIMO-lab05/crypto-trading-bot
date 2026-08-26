# Phase 21: TA Aggregator Widening + Leakage Net — Pattern Map

**Mapped:** 2026-08-26
**Files analyzed:** 26 (2 new source-adjacent test files, 4 further new test files/sections, 17 modified, 1 deleted, 1 doc, 1 build-config)
**Analogs found:** 22 / 26 with a concrete in-repo analog; 4 have **no analog** (§No Analog Found)
**Line refs:** every `file:line` below was **re-read from source in this session**, not copied from RESEARCH.md. Three corrections to RESEARCH.md are recorded in §RESEARCH.md Line-Ref Corrections.

> **Scope note for the planner.** RESEARCH.md §Open Questions poses four decisions (narrow-vs-broad MTF gating, `limit=200` disposition, `multi_indicator` diversity treatment, `rsi_divergence` build-failure policy). This document does **not** answer them — it supplies the analog for each option so the planner can choose. Where two analogs exist for one decision, both are listed.

---

## File Classification

Role uses the nearest standard value with the repo-native role in parentheses.

### services/technical-analysis

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/config.py` (P21-4/5: sma/ema→21, ichimoku→20/60/120) | config (pydantic `Settings`) | declaration | same file, `default_macd_fast/slow/signal` `:65-75` | exact (self-analog) |
| `app/main.py` (P21-5: Ichimoku Query descriptions `:568-570`) | route (FastAPI `Query` decl) | request-response | same file, MACD/RSI route `Query(default=settings.…, ge=, le=, description=)` | exact (self-analog) |
| `app/handlers/analysis.py` (P21-6: bare constructors → Settings) | controller (async handler) | request-response | same file `:40-45` (RSI/MACD already settings-sourced) | exact (self-analog) |
| `app/strategies/squeeze_momentum_strategy.py` (P21-8 dead code `:15`, `:87`, `:145`) | service (strategy wrapper) | transform | — (deletion only) | n/a |
| `.dockerignore` (P21-8: add `*.bak`) | config (build) | n/a | same file's existing globs | exact (self-analog) |
| `app/main.py.bak` (P21-8: **DELETE**) | artifact | n/a | — | n/a |
| `tests/test_leakage_regression.py` (**NEW**, TA-AGG-04) | test (property + AST guard) | batch/transform | tier-3 only: `tests/test_price_rounding_invariant.py`; tier-1/2 **none** | partial |
| `tests/test_aggregator_new_legs.py` (EXTEND: TA-AGG-01 residue + P21-6) | test (handler-namespace patch) | request-response | same file `_patched()` `:56-91` | exact (self-analog) |
| `tests/test_endpoint_defaults_from_settings.py` (EXTEND: description-vs-default) | test (parametrized drift table) | declaration | same file `:104-126` bounds/description test | exact (self-analog) |

### services/trading-engine

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/strategies/multi_strategy_ensemble.py` (P21-1 inject ATR; P21-2 diversity; P21-3 gate; P21-8 capital `:291`) | service (strategy orchestrator) | transform | same file `_atr_levels` `:235-285` (shape handling); `mean_reversion_strategy.py:100-122` (capital) | exact for shape+capital; **partial for the unit contract** |
| `app/strategies/simple_rsi_strategy.py` (P21-1 unit contract `:60-69`; P21-8 capital `:49`) | service (strategy leg) | transform | `mean_reversion_strategy.py:104,119-122` (capital); `risk_manager.py:88` (pct→fraction convention) | role-match; **no analog for the sanity-bounded unit contract** |
| `app/strategies/mean_reversion_strategy.py` (P21-1 consumer verification; P21-2 `indicators_aligned` source) | service (strategy leg) | transform | same file `:169-178` / `:201-209` (ATR-gated sub-signals) | exact (self-analog, read-mostly) |
| `app/signal_aggregator.py` (P21-4/5 omit params; P21-3 metadata key `:1134`; P21-7 ADX gate `:453/455`; P21-8 docstring `:143`) | service (REST client + MTF consolidation) | request-response | same file `fetch_macd` `:168-186` (omission); `fetch_adx` `:459-473` (metadata/role shape) | exact (self-analog) |
| `app/config.py` (P21-7 engine-side mirror fields) | config (pydantic `Settings`) | declaration | same file `adx_trending_threshold` `:309-330` | exact (self-analog) |
| `app/handlers/signals.py` (P21-7: read TA `regime` instead of re-deriving `:162`,`:164`) | controller (async handler) | request-response | `signal_aggregator.fetch_adx:448` (already reads `data["regime"]`) | exact |
| `app/aggregation/market_regime.py` (P21-7: `adx_period` `:126`/`:239`) | service (REST client) | request-response | `signal_aggregator.fetch_adx:442-443` (omits `period`) | exact |
| `app/strategies/sqzmom_strategy_integration.py` (P21-7: ADX `20.0` `:239`, volume `1.2` `:284`) | service (strategy gate) | request-response | `trading-engine/app/config.py:309-330` mirror `Field` | role-match |
| `app/strategies/hybrid_strategy_router.py` (P21-8: remove dead ATR fallback `:110-113`) | service (strategy router) | transform | — (deletion only; see the comment already at `:139`) | n/a |
| `app/trading_enhancements/advanced_position_sizing.py` (P21-8: docstring `capital=10000` `:107`) | service (risk sizing) | transform | `.claude/rules/money.md` docstring rule; `mean_reversion_strategy.py:112-114` docstring wording | role-match |
| `tests/strategies/test_ensemble_leg_wiring.py` (EXTEND: ATR unit contract — highest value) | test (payload builders) | transform | same file `_atr(value)` `:92-99`, `_atr_payload` `:34-51` | exact (self-analog) |
| `tests/strategies/test_ensemble_atr_levels.py` (EXTEND: real-ATR vs 2% fallback) | test (payload builders) | transform | same file `_atr_payload` `:45-57`, `ensemble_module` fixture `:29-35` | exact (self-analog) |
| `tests/test_mtf_confidence_consolidation.py` (EXTEND: `demoted_to_hold`) | test (pure-function) | transform | same file `_tf` / `_analysis` `:34-53` | exact (self-analog) |
| `tests/strategies/…` diversity tests (**NEW section or file**, P21-2) | test | transform | `tests/aggregation/test_indicator_categories.py` | exact |
| threshold-lock guard (**NEW**, P21-2/3) | test (constant guard) | declaration | `tests/strategies/test_ensemble_confidence_units.py:179-202` | exact |
| `tests/test_engine_param_omission.py` (**NEW**, P21-4/5) | test (outbound-request assertion) | request-response | **none in engine suite** — nearest is `signal_aggregator.fetch_macd:180-186` as the behavior under test | partial |

### Non-classifiable

| Item | Why | Handling |
|---|---|---|
| `services/technical-analysis/app/main.py.bak` | file deletion, not a code change | no role, no analog; P21-8 deletes it and adds `*.bak` to `.dockerignore` — **both, not either** |
| `wiki/modules/technical-analysis.md` | prose | doc analog in §TA-AGG-01 below (§`## Signal aggregator` at `:39` is the stale section; `## Corrections 2026-07-29` at `:104` is the repo's correction-record convention) |

---

## Pattern Assignments

Grouped by work item — files sharing an analog share a section.

---

### P21-1 — ATR threading + unit contract

**Targets:** `app/strategies/multi_strategy_ensemble.py`, `app/strategies/simple_rsi_strategy.py`
**Analog (shape handling only):** `services/trading-engine/app/strategies/multi_strategy_ensemble.py:235-285` (`_atr_levels`)

> ⚠️ **Do not read this as a copy job.** `_atr_levels` is the analog for *nested-dict shape handling, absence detection, and loud logging* — nothing more. The **percent→fraction unit contract has no analog in this repo** (§No Analog Found #1). Shipping the shape-copy alone puts BTC/ETH/BNB on negative stop-losses at measured 2026-08-26 ATR values (RESEARCH.md §Pitfall 1). The unit contract must land in the **same task and same commit**.

**Shape-handling pattern to copy** (`multi_strategy_ensemble.py:250-285`) — non-dict guard, side-aware key read, `try/except (TypeError, ValueError)`, sentinel-not-fabrication:

```python
        symbol = getattr(aggregator_signal, "symbol", "?")
        action = aggregator_signal.action
        atr_data = (aggregator_signal.metadata or {}).get("atr")

        if not isinstance(atr_data, dict):
            logger.warning(
                f"[ENSEMBLE][ATR] {symbol}: aggregator emitted no metadata['atr'] "
                f"(got {type(atr_data).__name__}) for a {getattr(action, 'value', action)} "
                f"signal — {LEG_MULTI} leg has no stop/target. The ATR fetch in "
                f"signal_aggregator.fetch_atr most likely failed."
            )
            return UNUSABLE_LEVEL, UNUSABLE_LEVEL
        ...
        try:
            if raw_sl is None or raw_tp is None:
                raise ValueError("missing key")
            return float(raw_sl), float(raw_tp)
        except (TypeError, ValueError):
            logger.warning(...)
            return UNUSABLE_LEVEL, UNUSABLE_LEVEL
```

**The sentinel doctrine to preserve** (`multi_strategy_ensemble.py:37-56`) — the module already documents *why* absence must not be filled with a plausible number. The new `_atr_indicator` helper must return `None` (not a fabricated ATR) for the same reason:

```python
# When the levels are genuinely absent we must not invent one. A plausible
# fabricated level (entry x 0.98, say) is indistinguishable downstream from a
# real ATR level: it would override the risk manager's own default with a
# number nobody chose, and it would look correct in the Telegram message and
# in the DB row.
UNUSABLE_LEVEL = 0.0
```

**IndicatorSignal construction pattern** for the synthetic ATR entry — copy the metadata/role convention from `signal_aggregator.fetch_adx:459-473` (the only non-voting-by-role indicator the engine already builds):

```python
            return IndicatorSignal(
                name="ADX",
                signal=signal_action,
                confidence=confidence,
                value=adx_val,
                metadata={
                    "adx": adx_val,
                    "plus_di": data.get("plus_di"),
                    "minus_di": data.get("minus_di"),
                    "regime": regime,
                    "direction": direction,
                    "role": "TREND_GATE",
                    "weight": 1.0,
                },
            )
```

⚠️ **`role: "RISK"` does not make an indicator non-voting — it makes it *more* likely to vote.** The consumer is `voter._is_non_voting` (`voter.py:370-383`), verified this session:

```python
    def _is_non_voting(self, name: str, indicator: IndicatorSignal) -> bool:
        role = (indicator.metadata or {}).get("role")
        if role is not None:
            return role in NON_VOTING_ROLES
        return name in NON_VOTING_NAMES
```

It keys off `metadata["role"]` **first**, and `NON_VOTING_ROLES = {"GATEKEEPER", "VALIDATOR"}` (`voter.py:65`) does not contain `"RISK"`. Worse: because a *present* role short-circuits the return, the `NON_VOTING_NAMES` name-list fallback (`voter.py:68`) is **never reached** — so stamping `role: "RISK"` actively disables the defensive name check rather than adding one. `"ATR"` is not in `NON_VOTING_NAMES` either way. Neither `role` nor `weight: 0.0` keeps a synthetic ATR out of the voter if it lands in a dict the voter can see. This is the concrete, mechanical reason the **local-copy** approach (RESEARCH Pattern 1) matters — surface it in the plan, and do not let `role: "RISK"` be mistaken for the guard.

**The wire contract the consumer must honour** (`signal_aggregator.fetch_atr:409-419`) — `atr` is absolute, `atr_pct` is a **percent**:

```python
            return {
                "atr": data["atr"],
                "atr_pct": data["atr_pct"],
                "stop_loss_long": data["stop_loss_long"],
                "stop_loss_short": data["stop_loss_short"],
                "take_profit_long": data["take_profit_long"],
                "take_profit_short": data["take_profit_short"],
                "volatility": data["volatility"],
                "confidence": data["confidence"],
                "risk_reward_ratio": data["risk_reward_ratio"],
            }
```

**The consumer to fix** (`simple_rsi_strategy.py:60-69`, current source, verbatim):

```python
        atr_sig = indicators.get("ATR")
        atr_pct = 0.02
        if atr_sig:
            atr_pct = float(
                (atr_sig.metadata or {}).get("atr_pct")
                or atr_sig.numeric_value()
                or 0.02
            )
            if atr_pct > 1.0:
                atr_pct = atr_pct / 100.0
```

Consumed at `:105` (`stop_distance = current_price * atr_pct * self.ATR_STOP_MULT`) and reported at `:113-115`. **Do not assert on `:121-122`'s `round(..., 4)` output** — that is Phase 22 and will be rewritten; assert on the resolved fraction / `stop_distance`.

**The other consumer, already correct — verify, do not change** (`mean_reversion_strategy.py:143`, `:169`, `:201`): it reads `atr_signal.numeric_value()` (absolute units) and gates the SMA-deviation sub-signals on `atr_value > 0`:

```python
        atr_value = atr_signal.numeric_value() if atr_signal else None
        ...
        if sma_value and atr_value and atr_value > 0:
            deviation = (current_price - sma_value) / atr_value
            if deviation <= -self.EXTREME_DEVIATION_THRESHOLD:
                oversold_signals.append("PRICE_EXTREME_BELOW_SMA")
                oversold_confidence += 0.25
            elif deviation <= -self.MEAN_DEVIATION_THRESHOLD:
                oversold_signals.append("PRICE_BELOW_SMA")
                oversold_confidence += 0.15
```

One `IndicatorSignal` serves both legs: `.value` = absolute (mean_reversion), `metadata` = fraction/percent (simple_rsi).

**Test analog** — `tests/strategies/test_ensemble_leg_wiring.py:92-99`. The existing `_atr()` builder carries **no `atr_pct` metadata** and must be extended:

```python
def _atr(value: float):
    return IndicatorSignal(
        name="ATR",
        signal=SignalAction.HOLD,
        confidence=0.3,
        value=value,
        metadata={"weight": 1.0},
    )
```

Wire-shaped payload builder to reuse for the metadata side — `test_ensemble_leg_wiring.py:34-51` and the identical `test_ensemble_atr_levels.py:45-57` (note `"atr_pct": 2.0` — a **percent**, matching the wire). Parametrize the unit test with the measured live values `0.6658` (below-1 branch) and `1.1065` (above-1 branch).

---

### P21-2 / P21-3 — leg diversity guard + MTF demotion gate

**Targets:** `app/strategies/multi_strategy_ensemble.py`, `app/signal_aggregator.py`

**Analog for the diversity taxonomy — reuse, do not redefine** (`app/aggregation/voter.py:36-59`):

```python
INDICATOR_CATEGORIES = {
    "MOMENTUM": {"RSI", "STOCHASTIC", "RSI_DIVERGENCE"},
    # MACD moved here from MOMENTUM on 2026-08-23. It is a moving-average
    # crossover ... Bucketing it as MOMENTUM let the diversity gate report
    # "trend + momentum confirmation" when it had trend + trend ...
    "TREND": {"SMA", "EMA", "ICHIMOKU", "ADX", "MACD"},
    "VOLATILITY": {"BOLLINGER_BANDS", "SQZMOM_ENHANCED"},
}
```

**Analog for the guard's shape** (`voter.py:549-586`, `check_category_diversity`) — HOLD short-circuit, `>= min_categories`, and a human-readable `reason` returned alongside the boolean:

```python
        if action == SignalAction.HOLD:
            return True, 0, "HOLD signals don't require category diversity"

        category_count, agreeing_categories, _ = self.calculate_category_consensus(
            voting_indicators, action
        )
        passes = category_count >= min_categories
        if passes:
            reason = f"Category diversity OK: {category_count} categories agree ({', '.join(agreeing_categories)})"
        else:
            reason = f"Insufficient diversity: {category_count}/{min_categories} categories (need {min_categories})"
        logger.info(f"Category diversity check: {reason}")
        return passes, category_count, reason
```

Category lookup helper to reuse: `voter.get_indicator_category` (`voter.py:476-492`) — returns `"OTHER"` for unknown names.

**Data source for the mean_reversion leg's categories** (`mean_reversion_strategy.py:47`): the `MeanReversionSignal` dataclass already carries `indicators_aligned: List[str]`. Values observed in source: `RSI_EXTREME`, `RSI_OVERSOLD`/`RSI_OVERBOUGHT`, `BB_LOWER`/`BB_NEAR_LOWER`/`BB_UPPER`/`BB_NEAR_UPPER`, `PRICE_EXTREME_BELOW_SMA`/`PRICE_BELOW_SMA` (+ ABOVE mirrors) — `:151-209`. The simple_rsi leg reads exactly one key (`simple_rsi_strategy.py:51`) so its category set is structurally `{MOMENTUM}`.

**Insertion point** — the guard belongs between `:406-411` (`agreeing_legs` count) and `:412-417` (`MIN_AGREEING_LEGS` check) in `generate_signal`. Copy the existing rejection-logging shape verbatim so the funnel reads consistently (`multi_strategy_ensemble.py:412-424`):

```python
        if agreeing_legs < self.MIN_AGREEING_LEGS:
            logger.info(
                f"[ENSEMBLE] HOLD — only {agreeing_legs} legs agree (need {self.MIN_AGREEING_LEGS}). "
                f"Score={weighted_score:+.3f}, actions={leg_actions}"
            )
            return None

        if abs(weighted_score) < self.AGGREGATION_THRESHOLD:
            logger.info(
                f"[ENSEMBLE] HOLD — weighted score {weighted_score:+.3f} below threshold "
                f"{self.AGGREGATION_THRESHOLD}. Actions={leg_actions}"
            )
            return None
```

**P21-3 metadata write site** (`signal_aggregator.py:1132-1150`, verified current) — the demoted action already reaches the ensemble at `:1133`; `consensus_action` at `:1137` is the **pre**-demotion value:

```python
        primary_signal.confidence = adjusted_confidence
        primary_signal.action = consolidated_action
        primary_signal.metadata["multi_timeframe"] = {
            "enabled": True,
            "timeframes": timeframes,
            "consensus_action": mtf_analysis.consensus_action.value,
            "alignment_strength": mtf_analysis.alignment_strength.value,
            "confidence_modifier": mtf_analysis.confidence_modifier,
            "agreement_pct": mtf_analysis.agreement_pct,
            "reasoning": mtf_analysis.reasoning,
            "timeframe_signals": {...},
        }
```

**Both Open-Question options have an analog** (planner chooses):
- *Narrow* (new `demoted_to_hold` key): additive dict entry in the block above; the surrounding comment block `:1108-1131` is the repo's convention for recording *why* a metadata key exists — match its density.
- *Broad* (`aggregator_signal.action == SignalAction.HOLD`): the analog is the multi_indicator leg's existing guard, `multi_strategy_ensemble.py:314-317`:
  ```python
        if (
            aggregator_signal.action != SignalAction.HOLD
            and aggregator_signal.confidence > 0
        ):
  ```
  Broad also captures the regime hard-block at `:1158+`, which CONTEXT does not authorize — flag the scope delta if chosen.

**Test analogs:**
- Diversity: `services/trading-engine/tests/aggregation/test_indicator_categories.py` — `voter` fixture, one assertion per claim, and the "no live voter falls through to OTHER" completeness test (`:33-40`) is directly reusable in spirit for "no firing leg falls through to OTHER".
- MTF: `tests/test_mtf_confidence_consolidation.py:34-53` builders (`_tf`, `_analysis`) drive `consolidate_mtf_confidence` as a pure function, no HTTP:
  ```python
  def _tf(interval, action, confidence, weight, score=0.0):
      return TimeframeSignal(interval=interval, action=action, confidence=confidence, score=score, weight=weight)

  def _analysis(tfs, consensus, modifier=1.0):
      return MultiTimeframeAnalysis(
          primary_action=tfs.get("60").action if "60" in tfs else SignalAction.HOLD,
          consensus_action=consensus, alignment_strength=AlignmentStrength.MODERATE,
          confidence_modifier=modifier, timeframe_signals=tfs,
          agreement_pct=0.0, reasoning="test",
      )
  ```
  The demotion case is already pinned at `:86-103` (`test_consensus_with_no_agreeing_timeframe_is_forced_to_hold`) — extend from there.
- **Threshold-lock guard analog:** `tests/strategies/test_ensemble_confidence_units.py:179-202` already asserts against the two constants and is the natural host (or the shape to copy into a new file):
  ```python
      monkeypatch.setattr(ens, "MIN_AGREEING_LEGS", 2, raising=False)
      ...
      assert out is None, "one firing leg must not satisfy MIN_AGREEING_LEGS=2"
  ```
  Its `ensemble_module` reload fixture pattern is at `test_ensemble_leg_wiring.py:102-107` / `test_ensemble_atr_levels.py:29-35` — required because the module holds a weights singleton.

---

### P21-4 / P21-5 — parameter single-sourcing (SMA / EMA / Ichimoku)

**Targets:** TA `app/config.py`, TA `app/main.py`, engine `app/signal_aggregator.py`, new `services/trading-engine/tests/test_engine_param_omission.py`

**Analog — the omission pattern the engine must adopt** (`signal_aggregator.py:168-186`, verbatim). Note the docstring names the drift it fixes **and** the value that won:

```python
    async def fetch_macd(
        self, symbol: str, interval: str = "60"
    ) -> Optional[IndicatorSignal]:
        """
        Fetch MACD indicator using the TA service's research-optimized defaults

        Parameter drift fix (audit 2026-07): this client previously forced
        8-17-9 while the TA service default is the Kang-2021 5-35-5
        (see technical-analysis app/config.py and handlers/indicators.py).
        We now omit fast/slow/signal so the single source of truth for MACD
        parameters is the TA service's defaults (currently 5-35-5).
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/macd/{symbol}"
            # No fast/slow/signal here on purpose — use TA service defaults
            # (Kang 2021: 5-35-5) instead of drifting local overrides.
            params = {
                "interval": interval,
            }
```

**Sites to convert**, all in `signal_aggregator.py`:
- `fetch_sma:250-259` — `period: int = 21` at `:254`, sent at `:259`
- `fetch_ema` — same shape immediately below
- `fetch_ichimoku` (~`:601-680`) — tenkan/kijun/senkou_b
- Contrast `fetch_bollinger_bands:221-227`, which is a **partial** omission (period omitted, `std_dev: 2.5` still sent at `:226`) — a numerically-agreeing mirror, not a drift. Out of CONTEXT's P21-7 list; do not silently expand.

**Analog — TA `Settings` declaration** (`technical-analysis/app/config.py:59-75`). Copy the "previous value / current value / why" comment density when moving sma/ema 20→21 and ichimoku 9/26/52→20/60/120:

```python
    # MACD Settings (RESEARCH-OPTIMIZED 2025-11-29)
    # Kang 2021 Study Results:
    #   - Default 12-26-9: -3.6% annual return
    #   - Optimized 5-35-5: +11% annual return (+14.6% improvement)
    # Previous: 8/17/9 (earlier crypto optimization)
    # Current: 5/35/5 (research-backed optimal for crypto)
    default_macd_fast: int = Field(
        default=5,
        description="MACD fast EMA - research-optimized 5-35-5 (prev: 8, std: 12)",
    )
```

Current values to change: `default_sma_period` `:87` = 20, `default_ema_period` `:88` = 20, `default_ichimoku_tenkan/kijun/senkou_b` `:126-128` = 9/26/52.

**The description-vs-default mismatch to fix** (`technical-analysis/app/main.py:566-570`, verbatim) — the descriptions already claim 20/60/120 while the defaults resolve to 9/26/52. Bounds confirmed to accommodate the new canon (`ge=5 le=30`, `ge=20 le=120`, `ge=40 le=200`):

```python
    tenkan_period: int = Query(default=settings.default_ichimoku_tenkan, ge=5, le=30, description="Tenkan-sen (conversion) period - crypto optimized: 20"),
    kijun_period: int = Query(default=settings.default_ichimoku_kijun, ge=20, le=120, description="Kijun-sen (base) period - crypto optimized: 60"),
    senkou_b_period: int = Query(default=settings.default_ichimoku_senkou_b, ge=40, le=200, description="Senkou Span B period - crypto optimized: 120"),
```

**Analog — the bounds/description contract test to extend** (`test_endpoint_defaults_from_settings.py:104-126`):

```python
def test_rsi_bounds_and_description_survive_the_settings_rewire():
    """Only default= may move. ge/le and description are a live contract.

    Narrowing RSI's le from 200 to 100 turns ?period=150 from HTTP 200 into
    HTTP 422, and dropping description= rewrites the published OpenAPI schema.
    """
    schema = client.get("/openapi.json").json()
    rsi_params = {p["name"]: p for p in schema["paths"]["/api/v1/indicators/rsi/{symbol}"]["get"]["parameters"]}
    period = rsi_params["period"]["schema"]
    assert period["default"] == settings.default_rsi_period
    assert period["minimum"] == 2, f"RSI ge moved: {period}"
    assert period["maximum"] == 200, ...
    assert period["description"] == "RSI period (optimized for crypto)", ...
```

The Ichimoku rows already exist in `WIRED_ROUTE_DEFAULTS:186-196` and `WIRED_HANDLER_DEFAULTS:281-283` — they assert against `settings`, so the value change is **auto-covered** and the table needs no edit. What it cannot see is the engine side.

**Engine-omission test (`tests/test_engine_param_omission.py`) — no direct analog in the engine suite.** Nearest patterns to compose from: the outbound-call capture idiom in `test_endpoint_defaults_from_settings.py:42-59` (mock the collaborator, read `call_args.kwargs`), applied to `agg.client.get`. Run from `services/trading-engine` with `--no-cov`.

---

### P21-6 — dashboard aggregate + MTF handlers read Settings

**Target:** `services/technical-analysis/app/handlers/analysis.py`

**Analog — same file, `:39-45`** (RSI/MACD are already settings-sourced; this is the shape the other four constructors must adopt):

```python
        # Calculate multiple indicators
        # RESEARCH-OPTIMIZED 2025-11-29: Use settings for optimal parameters
        rsi_calc = RSICalculator(period=settings.default_rsi_period)
        macd_calc = MACDCalculator(
            fast_period=settings.default_macd_fast,
            slow_period=settings.default_macd_slow,
            signal_period=settings.default_macd_signal,
        )
```

**Sites to fix in the same function** — verified current source:

| Line | Current | Settings field(s) available |
|---|---|---|
| `:46` | `trend_filter = TrendFilter()` | `default_trend_fast_period` (50), `default_trend_slow_period` (200) |
| `:57` | `ADXCalculator().calculate_with_signal(...)` | `default_adx_period` (14), `default_adx_*_threshold` |
| `:60` | `EnhancedSqueezeMomentum().calculate(df)` | `default_sqzmom_bb_period/bb_mult/kc_period/kc_mult/mom_period` |
| `:64-66` | `VolumeConfirmation().calculate(df["volume"].tolist(), "breakout")` | `default_volume_period` (20), `default_volume_signal_type` ("breakout") |
| `:33` | `limit=200` literal | *Open Question* — no `default_aggregate_limit` field exists yet |

Module-level binding to respect: `settings = get_settings()` executes at import (`analysis.py:22`), and the calculators are imported into this namespace at `:12-19` — hence the patch-target rule in §Shared Patterns #4.

**Gating comments to preserve verbatim while editing around them** (`analysis.py:111-123`) — they encode the non-neutral failure defaults that make the P21-6 change risky:

```python
        # ADX's failure default is HOLD at confidence 0.3 (adx.py:436-439), not
        # 0.0, so the weight > 0.0 filter below cannot tell a dead ADX from a
        # genuine ranging read. Only its directional labels may vote.
        if adx_signal in ("BUY", "SELL") and float(adx_conf) > 0.0:
            signals.append((str(adx_signal), float(adx_conf)))

        # Same for SQZMOM: HOLD is a flat 0.25 (sqzmom_enhanced.py:687-688).
        if sqz_df is not None and not sqz_df.empty:
            last_row = sqz_df.iloc[-1]
            if str(last_row["sqz_signal"]) in ("BUY", "SELL"):
                signals.append(...)
```

Also `:61-66` — the standing "Volume is NOT a voter" comment. CONTEXT: volume must never become a voter; keep this comment intact.

**Test analog:** `tests/test_aggregator_new_legs.py:56-91` `_patched()`. To assert *constructor arguments*, keep the `patch.multiple` targets and read `MagicMock.call_args` on the class mock (the fixture currently discards constructor args by returning a pre-built instance mock) — that is the one extension the analog does not already cover.

---

### P21-7 — mirror-literal cluster

**Targets:** `signal_aggregator.py:453,455`, `handlers/signals.py:162,164`, `sqzmom_strategy_integration.py:239,284`, `aggregation/market_regime.py:126,239`, engine `app/config.py`

**Analog A — engine-side mirror `Field`** (`services/trading-engine/app/config.py:309-330`, verbatim). This is the shape for every site resolved to "engine Settings": a typed `Field` with bounds, a description naming the TA counterpart, and an explicit **"Do NOT diverge"** comment:

```python
    # Regime routing threshold (2026-08-21). Previously hardcoded at
    # HybridStrategyRouter.__init__ as `self.ADX_TRENDING_THRESHOLD = 25.0`,
    # which the dashboard advertised as the routing rule while the router
    # itself was never invoked (docs/PIPELINE_MAP.md §0). Lifted to config so
    # the value the UI claims and the value the code applies are the same
    # object, and so Phase-3 recalibration can move it without a code edit.
    #
    # 25.0 is the conventional Wilder ADX trend threshold and matches
    # technical-analysis `default_adx_trending_threshold`. Do NOT diverge the
    # two without recording why — the TA service classifies the regime string
    # the confidence-modifier path consumes, this one classifies the routing
    # branch, and a split would make the tile disagree with the engine.
    adx_trending_threshold: float = Field(
        default=25.0,
        ge=0.0,
        le=100.0,
        description=(
            "ADX at or above which the strategy router classifies TRENDING "
            "(trend-following branch); below it, RANGING (mean-reversion "
            "branch). Mirrors technical-analysis default_adx_trending_threshold."
        ),
    )
```

**Analog B — read what TA already returns** (`signal_aggregator.py:445-448`). The ADX response's `regime` field is already parsed here, which is the precedent for `handlers/signals.py` to stop re-deriving it:

```python
            data = response.json().get("data", {})
            adx_val = float(data.get("adx", 0.0))
            direction = data.get("direction", "NEUTRAL")
            regime = data.get("regime", "UNKNOWN")
```

**Analog C — omit the param the TA Settings own** (`signal_aggregator.py:442-443`) — `fetch_adx` sends only `interval`, which is the model for `market_regime.py:239`:

```python
            url = f"{self.base_url}/api/v1/indicators/adx/{symbol}"
            response = await self.client.get(url, params={"interval": interval})
```

**Site inventory, re-verified this session** (planner picks A / B / C per site — CONTEXT leaves this to discretion):

| Site | Current source | Suggested analog |
|---|---|---|
| `signal_aggregator.py:453,455` | `if adx_val >= 20.0 and direction == "BULLISH":` / `elif adx_val >= 20.0 and direction == "BEARISH":` (comment at `:450-452` explains the gate) | A (new `adx_weak_trend_threshold` engine field) |
| `handlers/signals.py:162,164` | `if adx_value >= 25:` … `elif adx_value < 20:` … `else: regime = "WEAK_TREND"` (block `:161-167`; `adx_value` read at `:159` with a `25` default) | **B** — TA already returns `regime` on this exact endpoint |
| `sqzmom_strategy_integration.py:239` | `if adx_val < 20.0:` → demote to HOLD | A |
| `sqzmom_strategy_integration.py:284` | `if not confirmed or ratio < 1.2:` → demote to HOLD | A — **no TA settings field exists for this**; needs a new engine field |
| `market_regime.py:126` / `:239` | `adx_period: int = 14` ctor default; `params = {"interval": interval, "period": self.adx_period, "limit": 100}` | **C** — omit `period`; TA `default_adx_period` is already 14 |

**Test analog:** `services/trading-engine/tests/aggregation/test_indicator_categories.py` is the closest existing engine-side "declaration guard" test — one file, one defect, one assertion per claim, docstring citing the measured evidence.

---

### P21-8 — hygiene batch

**Capital literals.** **Analog — `mean_reversion_strategy.py:100-122`, the sanctioned pattern** (`Optional[float] = None`, resolved *in the body*, never as a default arg):

```python
    def generate_signal(
        self,
        indicators: Dict[str, IndicatorSignal],
        current_price: float,
        capital: Optional[float] = None,
    ) -> Optional[MeanReversionSignal]:
        """
        Args:
            capital: Available capital. None (default) resolves to
                Settings.paper_initial_balance — the old hardcoded 10000.0
                default was reachable by callers omitting capital (AUDIT 2.5).
        """
        if capital is None:
            from app.config import get_settings

            capital = get_settings().paper_initial_balance
```

Sites: `multi_strategy_ensemble.py:291` (`capital: float = 100.0`), `simple_rsi_strategy.py:49` (`capital: float = 100.0`). Both are passed through at `multi_strategy_ensemble.py:303` and `:336`. A second in-file analog for the settings-via-property shape is `multi_strategy_ensemble.py:224-233` (`MAX_POSITION_PCT`), which does the deferred `from app.config import get_settings` import inside the accessor.

**Docstring literal** — `services/trading-engine/app/trading_enhancements/advanced_position_sizing.py:104-108` (⚠ **path correction**, see §RESEARCH.md Line-Ref Corrections):

```python
        result = sizer.calculate_kelly(
            win_rate=0.55,
            reward_risk_ratio=2.0,
            capital=10000,
            price=50000
        )
```

`money.md` applies to docstrings explicitly ("a docstring showing `initial_capital=10000.0` is how the wrong number keeps propagating back into new code"). The wording analog is the `mean_reversion_strategy.py:112-114` docstring above — name the settings field, not a number.

**Dead-code deletions** (all verified present):
- `hybrid_strategy_router.py:110-113` — the ATR-metadata ADX fallback:
  ```python
        if adx_value is None:
            atr_signal = indicators.get("ATR")
            if atr_signal and getattr(atr_signal, "metadata", None):
                adx_value = atr_signal.metadata.get("adx")
  ```
  Note the file already carries a comment at `:139` (`# Old code looked at atr_signal.metadata['adx'] which never existed,`) — check whether it needs re-wording after the deletion. Also note the docstring at `:99-102` explaining the deliberate no-default behavior must survive.
- `squeeze_momentum_strategy.py:15` (`from app.models import SignalType`), `:87` (`self.momentum_exhaustion_count = 0` — write-only; `:88` `exhaustion_threshold` is its only companion), `:145` (`no_squeeze = latest['no_squeeze']`).

**Stale docstring** — `signal_aggregator.py:143`, verified verbatim: `- Research thresholds: 75/25 (not 70/30) for reduced false signals`. Actual TA thresholds are 80/20 (`rsi.py:80-81`).

**`.bak` removal — both halves.** Delete `services/technical-analysis/app/main.py.bak` (present, 32,865 B, mtime 2025-11-10) **and** add `*.bak` to `services/technical-analysis/.dockerignore`. Current `.dockerignore` contents (the pattern is one glob per line, with the file-level rationale comment on top):

```
# Keep the build context small and avoid tar failures on giant log files
logs/
htmlcov/
.pytest_cache/
__pycache__/
**/__pycache__/
*.log
coverage.json
.coverage*
tests/standalone/
```

---

### TA-AGG-01 — residue: gating tests + wiki doc

**Test analog — `tests/test_aggregator_new_legs.py:56-91`, `_patched()`.** All three new cases (ADX `("BUY", 0.0)`, SQZMOM `("HOLD", 0.9)`, volume-absence `volume_ratio == 0.0`) are parameter changes to this existing fixture:

```python
def _patched(
    adx=("BUY", 0.8), sqz=("BUY", 0.9), volume_confirmed=True, volume_strength="STRONG"
):
    """Patch every leg so only the ones under test carry weight."""
    fetcher = AsyncMock()
    fetcher.get_klines_as_dataframe = AsyncMock(return_value=_make_df())
    ...
    vol_inst.calculate.return_value = {
        "confirmed": volume_confirmed,
        "strength": volume_strength,
        "volume_ratio": 1.6,
        "confidence": 1.0,
    }

    return patch.multiple(
        "app.handlers.analysis",
        get_fetcher=MagicMock(return_value=fetcher),
        RSICalculator=MagicMock(return_value=rsi_inst),
        MACDCalculator=MagicMock(return_value=macd_inst),
        TrendFilter=MagicMock(return_value=trend_inst),
        ADXCalculator=MagicMock(return_value=adx_inst),
        EnhancedSqueezeMomentum=MagicMock(return_value=sqz_inst),
        VolumeConfirmation=MagicMock(return_value=vol_inst),
    )
```

Note `volume_ratio` is currently **hardcoded to 1.6** in the fixture — the absence-vs-disconfirmation case requires parametrizing it. Assertion style to copy (`:142-149`): compare a confirmed run against an unconfirmed run and assert the **label is unchanged** while confidence moves.

**Wiki analog — `wiki/modules/technical-analysis.md`.** The stale section is `## Signal aggregator` at `:39`, which currently opens:

> Pure TA: **RSI + MACD + trend filter only** (`app/handlers/analysis.py::get_aggregated_signal`).

Three in-file conventions to follow: (1) YAML frontmatter `updated:` field (`:14`, currently `2026-07-29`) must move; (2) the file records supersessions in a dated `## Corrections 2026-07-29` section at `:104` — add a `## Corrections 2026-08-26` rather than silently rewriting history; (3) `[[wiki-link]]` cross-refs. CONTEXT also requires an explicit note that this endpoint is **dashboard-only and diverges from the traded signal by construction** — the file's existing habit of correcting CLAUDE.md's tagline (`:27`) is the tone analog.

---

### TA-AGG-04 — leakage regression suite

**Target:** `services/technical-analysis/tests/test_leakage_regression.py` (**NEW**)

**Tier 1 (series prefix-vs-full) and Tier 2 (scalar↔series agreement, suffix-independence): no analog exists** in either service's test suite — see §No Analog Found #2. Use the fixture/parametrize shapes in RESEARCH.md §Code Examples as the starting point, with a ≥250-bar (RESEARCH recommends 400) non-degenerate random walk. All 13 modules confirmed present under `services/technical-analysis/app/indicators/`: `adx, atr, bollinger_bands, ichimoku, macd, moving_averages, rsi, rsi_divergence, squeeze_momentum, sqzmom_enhanced, stochastic, trend_filter, volume_confirmation`.

**Tier 3 (AST structural guard) — analog `tests/test_price_rounding_invariant.py`** (repo root). Copy four things: the `SCANNED_FILES` tuple with its append-only discipline, the "not yet covered, tracked deliberately" comment block, the per-line `ALLOW_MARKER` opt-out, and the docstring that states *why the guard exists and why it must not be disabled*:

```python
REPO_ROOT = Path(__file__).resolve().parents[1]

# Files cleaned of price-domain rounding. Append only alongside a fix.
SCANNED_FILES: tuple[str, ...] = (
    "services/technical-analysis/app/strategies/squeeze_momentum_strategy.py",
    "services/technical-analysis/app/indicators/sqzmom_enhanced.py",
    ...
)

# Line-level opt-out. A banned round() whose own source line carries this
# comment is a declared dimensionless value. WS1-B reuses this exact string -
# do not respell it, and do not add a second escape mechanism.
ALLOW_MARKER = "# non-price-round"
```

Its `_ndigits_of` docstring (`:63-76`) is the analog for the failure-mode *reasoning* the leakage guard needs — *"a detector that silently misses one fails GREEN: the guard would pass while a price rounding sat in a file it claims to protect."* The same argument applies to a `shift(-` detector that misses `.shift(-n)` written with a variable.

**Copy the discipline, not the code.** `_ndigits_of` / `_is_round_call` (`:63-108`) match `round()` **calls** and inspect an integer `ndigits` argument. The leakage guard needs a different node shape: `.shift()` with a *negative constant* (`ast.UnaryOp(op=ast.USub)`) or a non-constant argument it cannot prove non-negative, plus a `center=True` keyword match. Reuse `SCANNED_FILES`, `ALLOW_MARKER`, the append-only comment block and the docstring discipline; write the matcher fresh.

**Note on placement:** `test_price_rounding_invariant.py` lives at **repo root** `tests/` and resolves paths via `REPO_ROOT`. The leakage guard is specified for `services/technical-analysis/tests/`, whose `pytest.ini` sets `pythonpath = .` — path resolution must be re-anchored (`Path(__file__).resolve().parents[1] / "app" / "indicators"`), not copied.

**Aggregate-path leakage test:** drive `get_aggregated_signal` directly with the `_patched()`-style `AsyncMock` fetcher (analog above). `analysis.py:32-33` confirms it is a plain async function with no HTTP dependency:

```python
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit=200)
```

---

## Shared Patterns

### 1. Mirror `Field` with bounds + "Do NOT diverge" comment
**Source:** `services/trading-engine/app/config.py:309-330`
**Apply to:** every P21-7 site resolved to "engine Settings"; any new engine field (`adx_weak_trend_threshold`, `sqzmom_volume_ratio_min`)
**Requirements:** typed `Field(default=…, ge=…, le=…)`, a description naming the TA counterpart, and the explicit "Do NOT diverge … without recording why" sentence. Excerpt in §P21-7 Analog A.

### 2. `Optional[float] = None` → `get_settings().paper_initial_balance`
**Source:** `services/trading-engine/app/strategies/mean_reversion_strategy.py:104, 112-114, 119-122`
**Apply to:** `multi_strategy_ensemble.py:291`, `simple_rsi_strategy.py:49`, and every new engine test fixture
**Non-negotiable (`.claude/rules/money.md`):** never `def f(x = get_settings().y)` — default args evaluate once at import, freezing the value and hiding it from `tests/test_account_size_invariant.py`. In-container code (`services/*/app/**`) reads the service's own `Settings`; it must **never** `import shared.account`. Excerpt in §P21-8.

### 3. Parametrized drift-pinning table
**Source:** `services/technical-analysis/tests/test_endpoint_defaults_from_settings.py:133-231` (`WIRED_ROUTE_DEFAULTS`, OpenAPI layer) and `:236-301` (`WIRED_HANDLER_DEFAULTS`, handler `Query` layer)
**Apply to:** P21-4/5 (TA side — rows already exist, no edit needed), P21-6 (add rows, not files)
**Key property:** rows assert `== getattr(settings, field)`, never a literal, so a canonical-value change is auto-covered. Failure message names the drifting field:
```python
    assert params[param]["schema"]["default"] == getattr(settings, field), (
        f"{path} ?{param} default drifted from settings.{field}"
    )
```

### 4. Patch in the `app.handlers.analysis` namespace, never the indicator module
**Source:** `services/technical-analysis/tests/test_aggregator_new_legs.py:1-20` (module docstring) + `:82-91` (`patch.multiple`)
**Apply to:** every new TA test touching the aggregate path (P21-6, TA-AGG-01 residue, TA-AGG-04 aggregate case)
**Why it is load-bearing** — from the docstring itself: the calculators are bound into `handlers.analysis` at import (`analysis.py:12-19`), and the failure defaults are **not neutral** — ADX returns `("HOLD", 0.3)` and `VolumeConfirmation` returns `_reject_response()` with `volume_ratio 0.0`, so an unpatched leg casts a real vote.

### 5. AST guard over an append-only `SCANNED_FILES` list
**Source:** `tests/test_price_rounding_invariant.py:29-60`
**Apply to:** TA-AGG-04 tier-3 (`shift(-`, `center=True` ban over `app/indicators/*.py`)
**Discipline to copy:** "Adding a file here is a commitment that it is clean NOW … never add a file you have not just cleaned, or this guard lands red and gets disabled instead of obeyed." Per-line allowlist, single escape mechanism, no second one. RESEARCH confirms the intended allowlist entry: `rsi_divergence._find_pivot_{lows,highs}`.

### 6. Test-execution environment
**Source:** `.claude/rules/testing.md`, `services/trading-engine/tests/conftest.py`, `services/technical-analysis/pytest.ini`
**Apply to:** every test command in every plan
- engine: `cd services/trading-engine && python3 -m pytest <target> --no-cov` — cwd-sensitive (`env_file=".env"` relative to cwd); **never** export env vars to override (pydantic-settings v2 deep-merges `Dict` fields → `SYMBOL_ALLOCATIONS` sums to 1.25); there is **no in-container engine test path**.
- TA: `cd services/technical-analysis && python3 -m pytest <target> --no-cov` (`pythonpath = .`, `asyncio_mode = auto`).
- Always `--no-cov` (both `pytest.ini` files inject `--cov`).
- **New fixtures must not hardcode any balance literal — `10000` included.** `scripts/check_capital_literals.py` scopes to `services/<name>/app/…` and `tests/test_account_size_invariant.py` uses an explicit `SCANNED_FILES` list that excludes `services/*/tests/`, so this is enforced **by convention only**. Note the existing violation at `test_ensemble_leg_wiring.py:279` (`capital=100.0`) — prefer `capital=None` in new ensemble tests.

### 7. Module-reload fixture for ensemble tests
**Source:** `tests/strategies/test_ensemble_leg_wiring.py:102-107`, identical at `test_ensemble_atr_levels.py:29-35`
**Apply to:** every new/extended test constructing `MultiStrategyEnsemble`
```python
@pytest.fixture
def ensemble_module():
    """Fresh class binding per test (the module holds a weights singleton)."""
    import app.strategies.multi_strategy_ensemble as mod

    importlib.reload(mod)
    return mod
```
Required because `StrategyPerformanceWeights` is a module-level singleton persisted to `/app/data/ensemble_weights.json` (`multi_strategy_ensemble.py:84`) and feeds `normalized_weights()` into every leg contribution.

### 8. Comment-density convention for behavior-changing money/signal code
**Source:** `multi_strategy_ensemble.py:37-56` (UNUSABLE_LEVEL), `:358-382` (directional denominator), `signal_aggregator.py:1108-1131` (MTF action application), `voter.py:39-55` (MACD re-bucketing)
**Apply to:** every behavior-changing edit in P21-1/2/3
**Shape:** date-stamped, states the defect, cites the **measured** evidence (`.planning/evidence/…` or a log count), and explicitly says what did *not* change ("No threshold value changed."). Given CONTEXT's threshold lock, that last clause is required on the diversity guard and the MTF gate so a reviewer does not read them as smuggled threshold changes.

---

## No Analog Found

Planner should use RESEARCH.md's designed patterns for these — there is nothing in the codebase to copy.

| Item | Role | Data Flow | Reason |
|------|------|-----------|--------|
| **ATR percent→fraction unit contract** (`simple_rsi_strategy.py:60-69` replacement: explicit `atr_fraction` key, `0 < f < 1` sanity bound, WARNING-and-fallback) | service (strategy leg) | transform | Grep across `services/trading-engine/app/` found **no named percent→fraction helper**. The only convention is inline division at the point of use — `risk_manager.py:88` (`str(self.settings.max_daily_loss_pct / 100)`), `auto_trader.py:375` (`* (self.settings.max_total_exposure_pct / 100.0)`). None of them carries a sanity bound or a fallback. This is **new code**; use RESEARCH.md §Pattern 2. It is also the phase's highest-severity item — see §P21-1 warning. |
| **Leakage tier-1 / tier-2 tests** (series prefix-vs-full; scalar↔series agreement; suffix-independence with a poisoned tail) | test | batch/transform | No prefix-vs-full or property-style test exists in either service. Only the **tier-3** AST guard has an analog. Use RESEARCH.md §Code Examples; do not let the tautological tier-2 formulation (10 of 13 modules) close the requirement with always-green tests. |
| **`tests/test_engine_param_omission.py`** (assert the engine's *outbound* request params omit a key) | test | request-response | No engine test asserts on outbound REST params today. Nearest composable idiom is `test_endpoint_defaults_from_settings.py:42-59` (mock collaborator, inspect `call_args.kwargs`) — but that lives in the TA suite and the two services share no `Settings`, so it cannot host the assertion. |
| **`default_aggregate_limit` Settings field** (if the planner moves `analysis.py:33`'s `limit=200`) | config | declaration | No such field exists. If added, the analog is any `default_*_limit` in `technical-analysis/app/config.py` (`default_trend_limit` `:105`, `default_volume_limit` `:111`) — but RESEARCH flags a floor-validation need: post-P21-5 Ichimoku requires 146 bars, leaving 54 bars of headroom at 200. |

---

## RESEARCH.md Line-Ref Corrections

Verified against source this session. RESEARCH.md line 1112 asked for exactly this check; `git log` confirms no commit has touched `signal_aggregator.py` (last `42e2250`, 2026-08-23), `multi_strategy_ensemble.py` (last `b4cb894`, 2026-08-23) or `handlers/analysis.py` (last `7fd7c53`, 2026-08-18) since research. All quoted line numbers hold, with three exceptions:

| RESEARCH.md claim | Verified reality | Impact |
|---|---|---|
| `services/trading-engine/app/risk/advanced_position_sizing.py` (§Recommended change surface, and CONTEXT P21-8) | File is at **`services/trading-engine/app/trading_enhancements/advanced_position_sizing.py`**. Line `:107` (`capital=10000`) is correct. There is no `app/risk/advanced_position_sizing.py`; `app/risk/` holds `kelly_position_sizing.py`. | A plan action naming `app/risk/…` will fail to find the file. |
| `handlers/signals.py:162-164` / `:161-166` (two different spans given) | The `if adx_value >= 25:` is at **`:162`**, `elif adx_value < 20:` at **`:164`**; the full block including the `else: regime = "WEAK_TREND"` runs `:161-167`. `adx_value` is read at `:159` with a `25` default. | Cosmetic; both spans point at the right code. |
| §Recommended change surface lists `mean_reversion_strategy.py` only implicitly | It is a genuine P21-1 **verification** target (its ATR consumption at `:143`, `:169`, `:201` is already correct and must be pinned, not changed) and the P21-2 **data source** (`indicators_aligned`, `:47`). | Include it in the file list so the planner does not treat it as untouched. |
| C10 cites the unguarded balance literal at `test_ensemble_leg_wiring.py:280` | It is at **`:279`**. The call spans `:278-280`: `generate_signal(` on `:278`, `agg, current_price=price, capital=100.0` on `:279`, `)` on `:280`. | Cosmetic, but §Shared Patterns #6 cites `:279` — recorded here so the two documents do not read as disagreeing. |

Two further facts worth carrying into the plan:

- **`voter.py:63-68`:** `NON_VOTING_ROLES = {"GATEKEEPER", "VALIDATOR"}`, `NON_VOTING_NAMES = {"TREND_FILTER", "VOLUME_CONFIRMATION"}`. A synthetic ATR tagged `role: "RISK"` is **not** excluded by either set. This strengthens the case for RESEARCH Pattern 1's local-copy approach.
- **`test_ensemble_confidence_units.py` already exists** and already asserts against `MIN_AGREEING_LEGS` and `AGGREGATION_THRESHOLD` (`:179-202`). The threshold-lock guard listed as a Wave-0 gap may be an *extension* of this file rather than a new one — planner's call.

---

## Metadata

**Analog search scope:**
`services/trading-engine/app/{strategies,aggregation,handlers,risk,trading_enhancements}/`, `services/trading-engine/app/{config,signal_aggregator}.py`, `services/trading-engine/tests/{,strategies/,aggregation/}`, `services/technical-analysis/app/{config.py,main.py,handlers/,indicators/,strategies/}`, `services/technical-analysis/tests/`, repo-root `tests/`, `wiki/modules/`, `.claude/rules/`

**Files read this session (full or targeted, no re-reads):** 18 source/test files + 2 planning docs + 2 rules files
**Files scanned via grep/sed for line verification:** 9
**Pattern extraction date:** 2026-08-26
**Git HEAD at extraction:** `c6efb98`
