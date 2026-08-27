---
type: module
path: "services/technical-analysis/"
status: active
language: python
port: 8004
purpose: "TA indicators + signal aggregator (no ML inference here despite CLAUDE.md tagline)"
maintainer: ""
linked_issues: []
depends_on: [market-data-service]
used_by: [trading-engine, api-gateway]
tags: [module, service, indicators, signals]
created: 2026-05-05
updated: 2026-08-26
---

# technical-analysis

**Port:** `8004`
**Path:** `services/technical-analysis/`
**Purpose:** Technical indicators (13) + multi-indicator signal aggregator + multi-timeframe consensus.

## Overview

FastAPI service that fetches OHLCV candles from [[market-data-service]] over HTTP, computes TA indicators on-demand with pandas/numpy, and exposes both raw indicator endpoints and a weighted aggregator. Stateless: no DB, no Redis client, no RabbitMQ publisher (RabbitMQ + Redis settings exist in `config.py` but are dead config knobs — see audit comment at `app/config.py:105-115`).

Despite the CLAUDE.md tagline ("TA indicators + GRU inference + signal aggregator"), **GRU inference does not run here** — it lives in [[ml-prediction-service]]. See [[../concepts/ML-Status]] and [[../concepts/Feature-Flags]].

## Endpoints

Routes use `/api/v1/` prefix (legacy; gateway proxies as-is). Health: `/health`, `/ready`. Prometheus: `/metrics`.

Indicators (`/api/v1/indicators/{name}/{symbol}`): `rsi`, `macd`, `bollinger`, `sma`, `ema`, `trend`, `volume`, `atr`, `adx`, `stochastic`, `rsi-divergence`, `ichimoku`, `sqzmom`, `sqzmom-enhanced`, `sqzmom/{symbol}/backtest`.

Strategy: `GET /api/v1/strategies/sqzmom/signal/{symbol}` — full BUY/SELL/HOLD with stop/take-profit.

Aggregation: `GET /api/v1/indicators/signal/{symbol}` (five-voter weighted vote plus a volume penalty - see *Signal aggregator*; **dashboard-only**), `GET /api/v1/analysis/multi-timeframe/{symbol}` (parallel analysis across `1,5,15,60,240,1440` min, alignment score, consensus).

## Signal aggregator

> **This endpoint is dashboard-only. The [[trading-engine]] never calls it.**
> `GET /api/v1/indicators/signal/{symbol}` is reached only through
> [[api-gateway]]'s proxy (`api-gateway/app/main.py:929`, `:2338`); grepping
> `services/trading-engine/app/` for `indicators/signal` returns zero hits.
> The traded signal is assembled independently in
> `trading-engine/app/signal_aggregator.py` from the *raw* indicator
> endpoints. **Divergence between this endpoint's output and what the bot
> actually trades is by construction, not a bug** - they are two different
> aggregators with different voters, different weights and different gates.
> Do not debug one by reading the other.
>
> **This applies to `/indicators/signal/{symbol}` ONLY.** The sibling
> `GET /api/v1/analysis/multi-timeframe/{symbol}` **is** consumed by the
> engine — `trading-engine/app/aggregation/enhanced_aggregator.py:242`,
> reached from `signal_aggregator.py:986`. Do not generalise "dashboard-only"
> across the whole aggregation family; a change to `analyze_timeframe` has
> live blast radius, a change to `get_aggregated_signal` does not.

Pure TA, five voters (`app/handlers/analysis.py::get_aggregated_signal`, `:25`). Each calculator's `generate_signal()` (or equivalent) produces a `(label, confidence)` tuple and the aggregator does a weighted vote using each indicator's *own derived* confidence (fixed in commit `2d2c524`, MACD branch unwedged in `af7fdd9`):

| Leg | Votes? | Gate |
|---|---|---|
| RSI | yes | present and non-`None` |
| MACD | yes | `calculate()` returned a dict |
| TrendFilter | yes | `calculate()` returned a result |
| ADX | yes | label is **BUY or SELL** *and* confidence **strictly > 0** (`analysis.py:142`) |
| Enhanced SQZMOM | yes | label is **BUY or SELL**, at any confidence (`analysis.py:148`) |
| Volume Confirmation | **no - never** | post-vote confidence penalty only (`analysis.py:204–221`) |

**The two directional-only gates are not stylistic.** Neither calculator's failure default is neutral: ADX returns `("HOLD", 0.3)` on failure (`adx.py:436–439`) and a SQZMOM HOLD is a flat 0.25 (`sqzmom_enhanced.py:690–692` — note the comment at `analysis.py:145` still cites the pre-move `:687–688`; re-verified against source 2026-08-26). A dead calculator therefore emits a *confident-looking* tuple, so the generic drop-zero-confidence filter at `analysis.py:158` cannot tell it apart from a genuine ranging read. ADX carries the extra `confidence > 0` clause because a BUY at 0.0 is a dead calculator, not a weak opinion; SQZMOM deliberately does **not**, because its HOLD confidence is a constant and carries no information. All three behaviours are regression-tested in `tests/test_aggregator_new_legs.py`.

**Volume never votes and never changes the label.** Its labels are CONFIRM/REJECT — directionally agnostic, and they would `KeyError` the weight dict. It multiplies the confidence of an already-decided directional signal (STRONG confirm 1.0, confirmed 0.9, MODERATE 0.8, WEAK 0.75, otherwise 0.5), mirroring the engine's `aggregation/validator.py`. This was a measured decision on 2026-08-17; promoting it to a voter is a defect, not an enhancement. A `volume_ratio` of exactly `0.0` is `VolumeConfirmation._reject_response()` (`volume_confirmation.py:129–142`) — fewer than `period` bars or a swallowed exception — and is read as **absence** of information, taking the pass-through 1.0 rather than the 0.5 disconfirmation penalty (`analysis.py:210`).

**Every parameter above resolves from `Settings`** (P21-6, 2026-08-26). No voter is built with a bare constructor and neither kline window is a literal; the window is `settings.default_aggregate_limit`, which carries a cross-field warm-up floor validator in `app/config.py`. `analyze_timeframe` (`analysis.py:296`) is the second copy of the same construction block and is wired identically — and unlike `get_aggregated_signal` it sits on a live engine path, so its parameters are not merely cosmetic.

**Confidence is agreement-based (audit 2026-07, `analysis.py:183–199`).** For a directional outcome, confidence = winning direction's share of the **directional** weight (`BUY + SELL`), excluding HOLD from the denominator. Previously HOLD voters diluted the denominator, structurally capping aggregated confidence around ~0.47 and keeping the service in near-permanent HOLD. The multi-timeframe consensus applies the same fix (`analysis.py:412–435`): directional confidence = winning timeframes / directional timeframes. Note the multi-timeframe path votes on RSI + MACD + trend only — it does **not** consult ADX or SQZMOM.

No sentiment leg, no ML leg in this aggregator — by file evidence, never had one. The sentiment removal commits (`c346483`, `acae081`, `fe941cf`, `c171bb0`) referenced in [[../decisions/ADR-001-LSTM-removed]] applied to the [[trading-engine]] signal pipeline, not here. See [[../flows/Signal-Pipeline]].

## Indicators

13 indicators in `app/indicators/`: `rsi`, `macd`, `bollinger_bands`, `moving_averages` (SMA+EMA), `trend_filter`, `volume_confirmation`, `atr`, `adx`, `stochastic`, `rsi_divergence`, `ichimoku`, `squeeze_momentum`, `sqzmom_enhanced`. Strategy wrapper in `app/strategies/squeeze_momentum_strategy.py`.

## GRU integration

**None in this service.** `grep -rn "gru\|ml_predict\|ENABLE_ML" services/technical-analysis/app/` returns zero hits. ML inference is the responsibility of [[ml-prediction-service]]. ML feature gating (`ENABLE_ML_PREDICTIONS=false`) is read by consumers, not here.

## Dependencies

- **Outbound**: [[market-data-service]] only — HTTP `GET /api/v1/klines/{symbol}` via `app/fetcher.py::MarketDataFetcher`. URL from `MARKET_DATA_URL` env (default `http://localhost:8002` post commit `4d46e17`; was wrongly `8003`). **Data-integrity guards (audit 2026-07, `fetcher.py`):** requests `mainnet_only=true` (`fetcher.py:111`); drops OHLC-invalid rows (low>high / non-positive) and candles with `|log return| > 0.35` per bar (~42% up / 30% down — testnet-pollution guard) (`fetcher.py:191–218`); drops the still-forming last candle (`fetcher.py:220–230`); **raises `ValueError` if fewer than 30 valid rows remain** (`fetcher.py:233–239`). Interval aliases normalized: `1440→D`, `10080→W`, `43200→M` (`fetcher.py:21–37`) — the 1d multi-timeframe leg previously queried "1440" and silently got 0 rows.
- **Configured-but-unused**: Redis (caching), RabbitMQ (signal publishing). See `app/config.py:105-115` audit note.

## Used by

- [[trading-engine]] — consumes ADX (market-regime classifier), ATR (dynamic stops), stochastic, multi-timeframe signal. References: `app/aggregation/market_regime.py`, `app/phase1_metrics.py`, `app/multi_timeframe.py`.
- [[api-gateway]] — proxies as `/api/analysis/*`.

## Messaging

**No RabbitMQ usage.** Despite RabbitMQ settings + `enable_signal_publishing` flag in config, no `aio_pika` import, no publisher, no exchange declaration. Downstream is HTTP-only. See [[../concepts/Message-Queue-Topics]] for what is and isn't on the bus.

## Persistence

**None.** No DB connection, no migrations, no cache. Every request recomputes from candles. Cache TTL knobs in config (`cache_ttl_indicator=300`, `cache_ttl_signal=60`) unused.

## Gotchas

- **MACD default reconciled (audit 2026-07)**: single source of truth restored at 5/35/5. `config.py:71–81` defaults are 5/35/5 AND the raw `/macd/{symbol}` route Query defaults are now 5/35/5 (`main.py:291–293`) — the old 8/17/9 route drift is gone. (Bollinger std may still differ config 2.5 vs route — not re-verified this pass.)
- **MACD signal key (`af7fdd9`)**: `MACDCalculator.calculate()` returns `{macd_line, signal_line, histogram}` — no `signal` key. Old code calling `macd.get('signal')` always returned `None`, silently dropping MACD votes. Use `MACDCalculator.generate_signal(macd)` instead.
- **Enhanced SQZMOM columns (`fc345e8`)**: indicator writes `sqz_*` columns; `indicator_service` was reading non-prefixed names → silent zero defaults across every response.
- **Port-default fix (`4d46e17`)**: `market_data_url` default was `8003`; broke local pytest, masked in compose by `MARKET_DATA_URL` override.
- **RabbitMQ + Redis dead config**: env-validated, never connected.

## Key files

- `app/main.py` — FastAPI app + Prometheus metrics + 18 routes
- `app/config.py` — settings, audit annotations
- `app/fetcher.py` — market-data-service HTTP client
- `app/handlers/analysis.py` — aggregator + multi-timeframe
- `app/handlers/sqzmom.py` — SQZMOM raw + strategy handlers
- `app/services/indicator_service.py` — shared compute layer
- `app/indicators/*.py` — 13 indicator implementations
- `app/strategies/squeeze_momentum_strategy.py` — SQZMOM entry/exit rules

## Related

- [[../flows/Signal-Pipeline]]
- [[../concepts/ML-Status]]
- [[../concepts/Feature-Flags]]
- [[../concepts/Message-Queue-Topics]]
- [[../decisions/ADR-001-LSTM-removed]]
- [[market-data-service]]
- [[ml-prediction-service]]
- [[trading-engine]]
- Raw report: `[[../.raw/agent-reports/technical-analysis|agent report 2026-05-05]]`

## Corrections 2026-08-26

Phase 21 (TA-AGG-01 residue + P21-6), verified against source:

- **The *Signal aggregator* section was stale.** It claimed "RSI + MACD +
  trend filter only". ADX and Enhanced SQZMOM have voted in
  `get_aggregated_signal` since the leg-widening commit, and Volume
  Confirmation has been a post-vote penalty throughout. The roadmap
  requirement text carrying the same three-voter premise (dated 2026-05-23)
  is stale as of this date; the 2026-08-26 signal-path audit is
  authoritative where the two disagree. **No vote was widened by this
  phase** — the widening had already happened, and what was owed was tests
  and this page.
- **The three gating behaviours are now regression-tested** rather than
  documented by comment: ADX directional-and-confidence>0, SQZMOM
  directional-label-only, and volume absence (`volume_ratio == 0.0`)
  distinguished from disconfirmation. See
  `tests/test_aggregator_new_legs.py`. Each was mutation-checked — deleting
  its gate in `analysis.py` turns exactly its own test red.
- **Every voter parameter now resolves from `Settings`** (P21-6): TrendFilter,
  ADXCalculator, EnhancedSqueezeMomentum and VolumeConfirmation were bare
  constructors, the volume signal type was a literal, and both kline windows
  were `limit=200`. No numeric value changed — each settings default already
  equalled the constructor default it replaced, which is precisely why the
  drift would have stayed invisible.
- **Dashboard-only status recorded explicitly, and scoped.** The
  trading-engine has never consumed `/indicators/signal/{symbol}`; only
  [[api-gateway]] proxies it. This was implicit before and invited reading a
  dashboard number as the traded signal. The scope matters: the sibling
  multi-timeframe endpoint **is** engine-consumed
  (`enhanced_aggregator.py:242`), so the two must not be lumped together.
- **Line anchors in the *Signal aggregator* section were re-derived** against
  post-P21-6 source. The `analysis.py:114–136` / `:293–314` refs recorded in
  *Corrections 2026-07-29* below are correct for that date and are left as
  written; the code they describe is unchanged, only its line numbers moved.

## Corrections 2026-07-29

Reflects the 2026-07-28 data-integrity + signal-quality fix campaign (verified in source):

- **Data integrity** (`fetcher.py`): mainnet-only requests, OHLC-invalid + >35%/bar drop, still-forming-candle drop, raise on <30 valid rows, interval normalization `1440→D`/`10080→W`. See *Dependencies*.
- **Indicator confidence:** MACD confidence is now **price-scaled** (histogram = 0.2% of price → full confidence; `macd.py:203–219`) — the old `|hist|/|macd|` formula pinned to 1.0 at crossovers on garbage data. SMA/EMA return **HOLD conf 0** on >30% price-vs-MA gaps (`moving_averages.py:84–90`, `221–227`) — was emitting SELL conf 1.0 on polluted candles. Bollinger strong-buy zone is now **monotone/continuous** (strong-zone floor 0.7 tied to moderate-zone ceiling; `bollinger_bands.py:138–148`).
- **Aggregated-signal confidence** is now agreement-based over directional voters (`analysis.py:114–136`, multi-timeframe `293–314`). See *Signal aggregator*.
- **MACD default 5-35-5** everywhere (`config.py:71–81`, `main.py:291–293`).
- **Dockerfile fixed**: `COPY requirements.txt` is present (`Dockerfile:18`) — the build previously failed to copy it, so the running container could never pick up fixes.
