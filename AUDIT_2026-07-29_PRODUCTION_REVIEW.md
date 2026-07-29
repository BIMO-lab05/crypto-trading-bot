# Production Audit — Round 2 (2026-07-29)

Full production-readiness audit across the areas not covered by the 2026-07-28
pass (which fixed the trading engine, technical-analysis, and frontend API
layer — see `FIXES_2026-07-28_COMPREHENSIVE.md`). Four parallel audits
(security, money-services, data-pipeline, frontend UI/UX), an adversarial
second-pass verification, and full validation against **freshly rebuilt
containers on the operator's machine**.

Everything below was verified — not assumed. Test evidence at the end.

---

## 1. Bugs found & 2. Bugs fixed

### Critical

- **Bybit HMAC signature never matched the transmitted body.** The signature
  was computed over `json.dumps(data)` (spaces) but httpx sent compact JSON, so
  Bybit rejected **every authenticated POST** with retCode 10004 — all live
  order placement and cancellation was broken. GET signatures had the same
  drift when param order differed. *Fixed:* sign the exact compact bytes and
  send them verbatim via `content=`; send GET params in signed order.
  (`bybit-connector/app/bybit_rest_client.py`)

- **State-changing endpoints had no authentication.** `trading/start`,
  `trading/stop`, `portfolio/buy`, `portfolio/sell`, `risk/circuit-breaker/reset`,
  `trading/signals/{s}/analyze` (can execute a trade), `ml/models/train` — all
  drivable by anyone on the network. *Fixed:* auth added, **mode-gated** (see §7).

### High

- **Rate limiting was advertised but never enforced** — the middleware only
  tagged a header; `/auth/login` brute-force protection was a no-op. *Fixed:*
  real per-client fixed-window enforcement (429 + `Retry-After`), method-aware
  so the dashboard's ~300 read-polls/min are never throttled (see §7).
- **Manual circuit-breaker reset never resumed trading** — it cleared a legacy
  flag but left the state machine `OPEN`, so an admin reset silently did
  nothing until cooldown expired. *Fixed:* calls `engine.reset_circuit_breaker()`.
  (`risk-metrics-service/app/main.py`)
- **market-data graceful-shutdown crashed** on a bad logger kwarg (`TypeError`
  at INFO), aborting scheduler/fetcher/Redis/DB cleanup → resource leaks every
  shutdown. *Fixed.* (`market-data-service/app/main.py`)
- **httpx connection-pool leak** in the market-data scheduler — every 5-min job
  built a 100-connection pool and never closed it → eventual socket/FD
  exhaustion. *Fixed* with `try/finally: await fetcher.close()`.

### Medium

- NaN/inf `qty`/`price` bypassed the `<= 0` order guard and could reach the
  exchange. *Fixed* with `math.isfinite`. (`bybit-connector/app/models.py`)
- ML predict path had no NaN/inf guards and a possible divide-by-zero on
  `current_price`. *Fixed:* reject non-finite input/output, guard the divisor.
  (`ml-prediction-service/app/ml_models/gru_model.py`)
- `/ready` on ml-prediction reported "models loaded" even when the model file
  was missing. *Fixed* to reflect real availability.
- Portfolio optimization endpoints masked intended 503/400 as 500 (broke
  caller retry/backoff). *Fixed* with `except HTTPException: raise`.
- Blocking SMTP with no timeout could hang the event loop. *Fixed:* `timeout=30`.
  (`notification-service/app/email_notifier.py`)
- Missing interval validation on market-data query endpoints (bad interval →
  silent empty series). *Fixed:* whitelist → 400.

### Low

- CORS `allow_origins=["*"]` + `allow_credentials=True` on 8 internal services
  (spec-invalid, reflects caller origin). *Fixed:* `allow_credentials=False`
  (these are cookieless server-to-server services behind the gateway).
- `ml-retraining-service` container ran as root. *Fixed:* drops to `appuser`.
- `risk-metrics` hardcoded `reload=True`. *Fixed:* env-gated, defaults off.
- Frontend: debug `console.log` firing in render/poll hot paths (console flood
  + serialization overhead every 5–60s). *Removed.*

### Test defects fixed (mine + latent)

- `test_te_cap_05_log_survival` hardcoded a 2% cap; the deployed container
  correctly runs the ADR-010 10% paper cap. *Fixed:* derive expected clamp from
  actual settings.
- `test_performance_dashboard_tz` was a **time-bomb** — asserted a fixed May
  date `>=` a rolling now-minus-30-days cutoff, which broke as the wall clock
  advanced. *Fixed:* assert the naive-vs-aware comparison evaluates without
  raising (its stated intent).

## 3. Files modified

25 files across api-gateway (auth_middleware, main, rate_limiter, 4 test
files), bybit-connector (rest client, models), market-data (main, scheduler,
handlers/query), ml-prediction (main, gru_model), risk-metrics (main),
portfolio-manager (optimization), notification (main, email_notifier),
technical-analysis (main), tournament-harness (main), ml-retraining
(Dockerfile), 3 frontend files, plus 2 trading-engine test fixes. Full list in
`git log`.

## 4. Why each fix was needed

Each item in §1–2 states the concrete failure mode it prevents. The theme:
the system's *trust boundaries* (exchange auth, API auth, rate limits) and its
*failure paths* (shutdown, empty data, unconfigured channels, non-finite
numbers) were the weak spots — the happy path was mostly sound after round 1.

## 5. Remaining risks

- **No frontend login flow.** Auth is gated open in local paper mode (§7), so
  the dashboard works now. Before going LIVE you must build a login screen +
  token handling (or set `REQUIRE_API_AUTH=false` only if the bot is never
  network-exposed — not recommended for real money).
- **Single-process rate limiter.** Correct for the current single-gateway
  deployment; a multi-replica deploy needs the Redis-backed limiter.
- **9 pre-existing trading-engine test failures** (untouched baseline files, not
  caused by this work and not runtime app bugs): 2 Bybit-adapter *source-contract*
  governance tests, 5 backtest *source-marker* governance tests, 2 health-check
  tests with **stale `mock.patch` targets** (fail at patch setup, not on an
  assertion). These are test-quality debt — recommend fixing the stale mock
  targets and converting the source-marker governance tests to run in CI only.
- **ML predictions remain disabled** by design (V0 models scored chance-level;
  no proven edge). Don't enable without a DSR/CPCV-gated rebuild.
- **Strategy profitability is still unproven.** The engine now *measures*
  reality correctly and the data is clean — that's the prerequisite for
  profitability, not a guarantee. Paper-trade 2–4 weeks and evaluate with the
  DSR/CPCV tooling before any LIVE discussion.

## 6. Performance improvements

- Removed per-render / per-poll debug logging and duplicate console overhead in
  the dashboard.
- Closed the market-data httpx pool leak (was accumulating 100 conns / 5 min).
- Rate-limit ceilings recalibrated so legitimate dashboard polling is never
  throttled while abuse (thousands/min) is still blocked.

## 7. Security improvements

- **Mode-gated API auth** (operator-chosen): enforced in LIVE / non-paper /
  production / staging (fails closed); open in local paper mode so the
  tokenless dashboard works. Override anywhere with `REQUIRE_API_AUTH=true|false`.
  Verified across 11 mode combinations. `/auth/me` and `/auth/logout` stay
  strict (always require a real token).
- **Real rate-limit enforcement**, method-aware: only mutating trade actions
  get the strict 60/min bucket; reads and health get 1200/min; auth 10/min
  (brute-force guard). Verified across 15 path/method cases.
- **Bybit request signing** now cryptographically correct (was 100% failing).
- Finite-value guards on order qty/price and ML I/O.
- CORS credentialed-wildcard closed on 8 services; ml-retraining de-rooted.

## 8. UX improvements

- Dashboard controls (start/stop/emergency/buy/sell) keep working with **no
  login friction** in local paper mode while being secured for LIVE.
- Cleaner console (no debug flood) → easier real-error spotting.
- (Round 1 already added the loud error/empty/loading `TileState` states, fixed
  the ⌘K 404s, and the whole-tile crash fan-out.)

## 9. Refactoring completed

- Auth resolved through a single `get_current_user_gated` sub-dependency so the
  active/admin dependencies keep their original `User`-typed contract (no test
  churn).
- Rate-limit categorization made method-aware and self-consistent
  (`trading_write` bucket, no stale field references).
- Frontend hot-path logging removed; orphaned destructures cleaned.

## 10. Suggestions for future enhancements

1. Build the frontend login flow (unlocks LIVE with hard auth everywhere).
2. Move rate limiting + any shared state to the Redis-backed limiter for
   multi-replica.
3. Fix the 9 pre-existing test-quality failures (stale mock targets; gate the
   source-marker governance tests to CI).
4. Offload the synchronous Keras inference and legacy SMTP calls to threads
   (`asyncio.to_thread`) so they never block the event loop.
5. Rebuild the ML models on a returns target with a DSR > 0.95 acceptance gate
   before re-enabling predictions.
6. Add a real WebSocket ingest path (market-data + bybit-connector are
   REST-poll only today).

---

## Validation evidence (against freshly rebuilt containers, operator's machine)

- **8/9 services HTTP 200** after rebuild+recreate (ml-prediction intentionally
  absent — feature-gated off).
- **Accounting harness: 28/28** in `crypto-bot-trading`.
- **Indicator harness: 16/16** in `crypto-bot-ta`.
- **api-gateway pytest: 437/437** (with `ENVIRONMENT=test` to disable the newly
  live rate limiter during the suite's rapid-fire requests).
- **trading-engine pytest: 1403 passed, 628 skipped**, plus the 2 test-fixes
  above now green (7/7 on re-run). 9 pre-existing governance/infra failures
  documented in §5 (not caused by this work, not runtime bugs).
- **Auth mode-gate logic: 11/11** standalone cases. **Rate-limit
  categorization: 15/15** standalone cases (dashboard ~300 reads/min < 1200
  limit → never throttled).
- Data sanity: max mainnet BTC close **$82,791** (was $1.76M of testnet
  pollution before the round-1 DB repair).
