# Phase 21: TA Aggregator Widening + Leakage Net - Context

**Gathered:** 2026-08-26
**Status:** Ready for planning
**Source:** Brainstorming session 2026-08-26 (operator-approved spec) + adversarially-verified signal-path audit

<domain>
## Phase Boundary

Make the whole TA signal path correct and honest: TA service (`services/technical-analysis/**`) plus trading-engine signal consumers (`signal_aggregator.py`, `aggregation/*`, `strategies/*`). Fix the confirmed-open defects from the 2026-08-26 audit, close the still-owed roadmap requirement TA-AGG-04 (leakage regression suite), and finish the TA-AGG-01 residue (tests + docs for the already-widened vote). **Profitability is explicitly not a goal of this phase** — correctness only; edge claims stay gated on DSR/CPCV elsewhere.

Price-precision residue (PRICE-01/02) is Phase 22, not this phase.
</domain>

<decisions>
## Implementation Decisions

### Authority and staleness
- The audit (`.planning/audits/2026-08-26-ta-signal-path-audit.md`) is **authoritative over the 2026-05-23 requirement text** where they conflict. The roadmap's premise ("aggregator votes only RSI+MACD+TrendFilter") is stale: ADX and SQZMOM vote today in both aggregators; volume is a post-vote penalty. Do NOT re-implement closed items.
- TA-AGG-02/03 are CLOSED (settings-sourced since 2026-08-20, pinned by `services/technical-analysis/tests/test_endpoint_defaults_from_settings.py`). Plans must only record closure evidence — no code change.

### TA-AGG-01 residue (dashboard aggregate endpoint)
- Vote-widening core is satisfied by evolution. Remaining work: unit tests pinning current gating behavior (ADX votes only when directional and conf>0, SQZMOM votes only when directional, volume scales confidence post-vote and never votes) + document the aggregate-endpoint vote in `wiki/modules/technical-analysis.md`.
- Do NOT add the `aggregator_mode = minimal|full` env from the old requirement text — YAGNI on a dashboard-only endpoint.
- Volume must NEVER become a voter (measured decision 2026-08-17). A veto/penalty is fine; a vote is a defect.

### TA-AGG-04 (fully owed)
- Look-ahead-leakage regression suite at `services/technical-analysis/tests/test_leakage_regression.py`: for each of the 13 indicator modules under `app/indicators/` plus the aggregate endpoint path, compute at time t with `df[:t+1]` vs full series; values at t must be identical. Ichimoku Senkou forward-shift asserted intentional (projection only, no future value used as input at t).

### P21-1 — ATR threading (top priority, live path)
- `simple_rsi_strategy.py` and `mean_reversion_strategy.py` must receive real ATR. Thread the aggregator's `metadata['atr']` payload into leg dispatch (or inject a synthetic `indicators['ATR']` entry before dispatching legs in `multi_strategy_ensemble.generate_signal`). Follow the already-fixed multi_indicator leg (`_atr_levels`) as the reference pattern.
- Regression test: legs see real ATR when the aggregator fetched one; fallback 2% only when ATR genuinely absent.

### P21-2 / P21-3 — leg correlation + MTF bypass (fix, operator-approved)
- Fix as **wiring correctness**, not threshold tuning:
  - MTF demotion must gate ALL ensemble legs: when `consolidate_mtf_confidence` demotes consensus to HOLD, simple_rsi and mean_reversion must not trade past it (today only multi_indicator is silenced).
  - Agreement counting must not present single-source information as multi-leg agreement: RSI-only agreement (simple_rsi + mean_reversion co-fire on the same RSI print) must not count as independent multi-leg confirmation. Mirror the category-diversity idea CoreAggregator already applies to its voters.
- **Locked constraint:** NO changes to threshold values — `min_signal_confidence=0.30`, `AGGREGATION_THRESHOLD=0.10`, `MIN_AGREEING_LEGS=1` stay as-is. Phase-3 verdict (no threshold change; IS/OOS rankings invert) stands.
- These fixes reduce trade admission; that is expected and accepted. Document expected behavior change in the plan's verification.

### P21-4 / P21-5 — parameter single-sourcing (MACD pattern)
- **Canonical values = the LIVE values** (what the deployed signal actually runs on): SMA/EMA period **21**, Ichimoku **20/60/120**. Lift them into TA `Settings` (`default_sma_period`/`default_ema_period` → 21; `default_ichimoku_*` → 20/60/120), engine omits the params (adopting the MACD pattern at `signal_aggregator.py:174-186`), TA Settings become the single source. Rationale: changing the traded signal's parameters silently is worse than moving the declaration.
- Fix the misleading `main.py:568-570` Ichimoku descriptions so description and default agree.
- Extend `test_endpoint_defaults_from_settings.py` (or sibling) to pin engine-omission: engine request params for SMA/EMA/Ichimoku must not carry period overrides.

### P21-6 — dashboard aggregate + MTF handlers read Settings
- `handlers/analysis.py` (`get_aggregated_signal` and `analyze_timeframe`): construct TrendFilter/ADXCalculator/EnhancedSqueezeMomentum/VolumeConfirmation from `settings.default_*`; route `'breakout'` through `settings.default_volume_signal_type`; keep `limit=200` literal or move to settings — planner's choice, but pin whatever wins with a test.

### P21-7 — mirror-literal cluster
- Prefer reading what TA already returns (e.g., ADX response's `regime` field) over re-deriving from mirrored literals. Where a mirror must stay (REST-mesh reality), route it through the engine's own Settings so env overrides move both sides deliberately. Sites: `signal_aggregator.py:453/455` (ADX 20.0 vote gate), `handlers/signals.py:162-164` (25/20 regime re-derivation), `sqzmom_strategy_integration.py:239/284` (ADX 20.0, volume 1.2), `market_regime.py:126/239` (explicit adx_period=14 vs fetch_adx omitting).

### P21-8 — hygiene batch
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

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Audit + spec (the source of truth for this phase)
- `.planning/audits/2026-08-26-ta-signal-path-audit.md` — verified defect list, per-leg vote table, fix-routing rule (engine-sent vs engine-omitted vs constructor-default layers)
- `docs/superpowers/specs/2026-08-26-ta-signal-path-correctness-design.md` — approved design, constraints, verification standards

### Code (live path)
- `services/trading-engine/app/signal_aggregator.py` — fetch layer, MTF consolidation, MACD omission pattern (:174-186)
- `services/trading-engine/app/aggregation/voter.py`, `aggregator_core.py`, `validator.py`, `multi_timeframe.py` — vote/gate stack
- `services/trading-engine/app/strategies/multi_strategy_ensemble.py`, `simple_rsi_strategy.py`, `mean_reversion_strategy.py` — ensemble legs
- `services/technical-analysis/app/handlers/analysis.py`, `app/config.py`, `app/main.py` — TA aggregate endpoint + settings
- `services/technical-analysis/tests/test_endpoint_defaults_from_settings.py` — the drift-pinning pattern to extend

### Rules
- `.claude/rules/money.md` (loads on money-code edits), `.claude/rules/testing.md` — trading-engine host tests run from `services/trading-engine` with `--no-cov`; api-gateway tests in-container
- CLAUDE.md §5 (units trap, risk caps), §7 (verification standards — no "working" claim on HTTP 200 alone)

</canonical_refs>

<specifics>
## Specific Ideas

- Verification must include a before/after signal comparison on BTC/ETH/SOL/BNB/ADA through the running stack, plus rebuild + `--force-recreate` of changed services (stale in-memory state is the known false-pass mode).
- Every behavior-changing fix (ATR threading, MTF gating, diversity guard) needs a test that pins the OLD broken behavior is gone (e.g., "mean_reversion SMA-deviation sub-signals fire when ATR present").
- Commit in logical chunks, conventional messages, pathspec commits (`git commit -- <paths>`) per shared-index rule.
</specifics>

<deferred>
## Deferred Ideas

- Price-precision residue → Phase 22 (`simple_rsi_strategy.py:121-122` SL/TP rounding, sqzmom momentum 4dp sites, guard growth, main.py.bak deletion overlaps — coordinate: the .bak deletion lands here in P21-8, guard growth lands in 22).
- sentiment-analysis-service credentialed-wildcard CORS hole — standalone quick task after this phase (security, one line).
- CLAUDE.md §3 service-table correction ("TA + GRU inference" is wrong) — next CLAUDE.md edit.
- `grid_trading_strategy_v2.py` MAX_POSITION_VALUE_USD literal — owned trading-engine defect, tracked by `scripts/check_capital_literals.py` allowlist.
- GRU retrain, LSTM purge (Phase 23), edge research — out of scope.
</deferred>

---

*Phase: 21-ta-aggregator-widening-leakage-net*
*Context gathered: 2026-08-26 via brainstorming session + 8-agent adversarially-verified audit*
