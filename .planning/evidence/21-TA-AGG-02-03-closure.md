# TA-AGG-02 / TA-AGG-03 — closure evidence

**Requirements:** TA-AGG-02 (MACD 5/35/5 single-sourced), TA-AGG-03 (Bollinger std_dev single-sourced)
**Recorded:** 2026-08-27
**Phase:** 21-ta-aggregator-widening-leakage-net, plan 21-02
**Verdict:** **CLOSED — no code change owed.** Both were satisfied by the 2026-08-20 Settings rewire.

This record exists because the phase roadmap still listed both as open. 21-CONTEXT.md
(§"Authority and staleness") declares them CLOSED and instructs plans to record closure
evidence rather than re-implement. This is that evidence.

**Reproduce:**

```
cd services/technical-analysis && python3 -m pytest tests/test_endpoint_defaults_from_settings.py --no-cov -q
```

Result on this branch: **68 passed**.

---

## TA-AGG-02 — MACD parameters single-sourced (5/35/5)

The declaration, the aggregate path, both HTTP layers, and the engine's omission all
resolve to one object: `Settings.default_macd_fast/slow/signal`.

| Layer | Evidence | What it proves |
|---|---|---|
| Declaration | `services/technical-analysis/app/config.py:65-75` | `default_macd_fast=5`, `default_macd_slow=35`, `default_macd_signal=5` — the single source, env-overridable |
| Aggregate path | `services/technical-analysis/app/handlers/analysis.py:41-45` | `MACDCalculator(fast_period=settings.default_macd_fast, slow_period=..., signal_period=...)` — constructed from the fields, no literals |
| Route layer (call args) | `services/technical-analysis/tests/test_endpoint_defaults_from_settings.py:33-59` | A bare `GET /api/v1/indicators/macd/BTCUSDT` reaches `calculate_macd` with the Settings values |
| Route layer (published schema) | `services/technical-analysis/tests/test_endpoint_defaults_from_settings.py:91-101` | The literal is gone from the OpenAPI schema, not merely shadowed at runtime |
| Route drift table | `services/technical-analysis/tests/test_endpoint_defaults_from_settings.py:135-137` | `WIRED_ROUTE_DEFAULTS` rows assert `== getattr(settings, field)`, never a literal |
| Handler drift table | `services/technical-analysis/tests/test_endpoint_defaults_from_settings.py:238-240` | `WIRED_HANDLER_DEFAULTS` pins the handler `Query()` defaults for direct callers |
| Engine omission | `services/trading-engine/app/signal_aggregator.py:182-186` | `params = {"interval": interval}` — "No fast/slow/signal here on purpose" |
| Engine omission rationale | `services/trading-engine/app/signal_aggregator.py:174-178` | Docstring names the drift fixed (client forced 8-17-9 against a 5-35-5 default) and which value won |
| Engine omission guard (**new, this plan**) | `services/trading-engine/tests/test_engine_param_omission.py` (`fetch_macd` row) | The omission is now pinned by an outbound-request assertion, not only by a docstring |

Before this plan the engine-side omission was enforced only by convention. The
`fetch_macd` row of the new `test_engine_param_omission.py` passes **today** — it is a
regression guard on an already-closed fix, not a new requirement.

## TA-AGG-03 — Bollinger `std_dev` single-sourced (2.5)

| Layer | Evidence | What it proves |
|---|---|---|
| Declaration | `services/technical-analysis/app/config.py:81-84` | `default_bb_std = 2.5` (widened for crypto volatility; prev 2.0) |
| Route layer (call args) | `services/technical-analysis/tests/test_endpoint_defaults_from_settings.py:62-88` | A bare Bollinger call reaches the service with `period == settings.default_bb_period` and `std_dev == settings.default_bb_std` |
| Route drift table | `services/technical-analysis/tests/test_endpoint_defaults_from_settings.py:139` | `("/api/v1/indicators/bollinger/{symbol}", "std_dev", "default_bb_std")` |
| Handler drift table | `services/technical-analysis/tests/test_endpoint_defaults_from_settings.py:242` | `(get_bollinger_bands, "std_dev", "default_bb_std")` |

## Known mirror — deliberately out of scope

**The engine still sends `std_dev: 2.5` at `services/trading-engine/app/signal_aggregator.py:226` while omitting the Bollinger `period` — a partial omission and a numerically-agreeing mirror, not a drift today.**

It agrees with `config.py:81` by value, so nothing disagrees at runtime and no signal is
affected. It is nonetheless a mirror literal: an operator moving `DEFAULT_BB_STD` would
move the bare endpoint and the dashboard while the traded path kept 2.5.

It is **not** in 21-CONTEXT.md's P21-7 site list (which names `signal_aggregator.py:453/455`,
`handlers/signals.py:162-164`, `sqzmom_strategy_integration.py:239/284`, and
`market_regime.py:126/239`). Recorded here as a known mirror; see
`.planning/phases/21-ta-aggregator-widening-leakage-net/21-RESEARCH.md` §"Mirror Inventory".
Scope was deliberately not expanded to fix it in plan 21-02.
