---
quick_id: 260730-vwn
slug: fix-ensemble-legs-live-cap
date_planned: 2026-07-30
date_completed: 2026-08-04
status: complete
source: .planning/audits/2026-07-30-strategy-audit.md
commit: (see git log — committed 2026-08-04)
---

# Quick Task 260730-vwn — SUMMARY

Both audit findings fixed. Implementation was written 2026-07-30 but sat uncommitted
in the working tree through the 2026-07-31 → 2026-08-03 capital-audit work; the
2026-08-04 resume session found it, re-verified it, and committed it.

## What shipped

### F-1 — dead ensemble legs (HIGH)

`SignalAggregator` publishes an indicator's numeric reading on
`IndicatorSignal.value` and reserves `metadata` for bookkeeping (period, weight).
Two of three ensemble legs read `metadata["value"]`, which is never populated.

- `app/models/signal.py:20` — new `IndicatorSignal.numeric_value()`. Returns
  `self.value`, falls back to `metadata["value"]` for any producer that still
  writes there, returns `None` when there is no reading anywhere. One definition,
  both legs use it.
- `app/strategies/simple_rsi_strategy.py:56,65` — reads via `numeric_value()`.
  Previously bailed to `None` on **every** call, so the leg never voted.
- `app/strategies/mean_reversion_strategy.py` — the substantive change:
  - RSI read via `numeric_value()`; **missing RSI now returns `None`** instead of
    substituting `50.0`. A payload the leg could not read used to score as a calm
    market rather than surfacing as unreadable.
  - Bollinger position derived from the `upper_band` / `lower_band` the producer
    actually emits (new `_bollinger_position()`), honouring an explicit `position`
    key if some producer supplies one. Absent bands → **skip the BB checks**
    rather than scoring a fabricated mid-band `0.5`. Values outside `[0, 1]` are
    returned as-is: price beyond a band is meaningful.
  - Latent `UnboundLocalError` fixed. `sma_value` / `atr_value` were read at the
    signal-construction site but only bound inside a conditional deviation branch —
    unreachable while the leg was dead, reachable the moment it fired. Both are now
    resolved once, up front.
  - Stop/target anchoring corrected while fixing the above. The old fallback
    anchored the reversion target to `current_price`, which collapses the
    distance-to-mean to zero and yields a target equal to entry plus a degenerate
    stop. Now prefers the Bollinger **middle** band when SMA is absent (it *is* an
    SMA, new `_bollinger_middle()`) and **refuses to signal** when neither is
    available or when the anchor equals entry.

Live evidence from the audit: 126/126 signals over 6h came from the
`multi_indicator` leg alone. Both other legs were inert.

### F-2 — sizing floor overrode the LIVE per-trade cap (HIGH)

`multi_strategy_ensemble.py` computed `max(floor, min(cap, scaled))` — the floor
applied *after* the clamp, so whenever `floor > cap` the cap was discarded. With
the LIVE-strict cap at `0.02` and the shipped `ensemble_min_position_pct` default
at `0.05`, **every LIVE ensemble trade would have sized at 5% — 2.5× the
non-negotiable cap — at any confidence.** Neither the boot gate nor
`preflight.check_cap` inspected the floor, so the breach passed preflight.

- `multi_strategy_ensemble.py:305` — reordered to `min(cap, max(floor, scaled))`.
  The cap is applied last so it always wins. No-op whenever `floor <= cap`.
- `multi_strategy_ensemble.py:309` — warns when the floor is clamped by the cap,
  so a misconfiguration is visible rather than silent.
- `app/preflight/checks.py:106` — `check_cap` now FAILs in LIVE when
  `ensemble_min_position_pct > _LIVE_STRICT_CAP`. PAPER still skips both knobs by
  design (ADR-010 paper-relaxed 10%).
- `app/main.py:291` — boot refusal mirrors the same condition, reusing the
  existing `LIVE_PREFLIGHT_REJECTED` grep-gate literal unsplit.

## Verification

Host, from `services/trading-engine`, `--no-cov`,
`MAX_TOTAL_EXPOSURE_PCT=80.0 PAPER_INITIAL_BALANCE=100.0`:

**Targeted — 48/48 pass.**

| Suite | Count |
|---|---|
| `tests/strategies/test_ensemble_leg_wiring.py` (new) | 8 |
| `tests/strategies/test_multi_strategy_ensemble_sizing.py` | 8 (3 new via parametrised `test_cap_wins_when_floor_exceeds_it`) |
| `tests/test_preflight_checks.py` | 25 (+`test_check_cap_live_rejects_floor_above_cap`, `test_check_cap_paper_allows_floor_above_cap`) |
| `tests/test_preflight_lifespan.py` | 7 (+`test_lifespan_rejects_live_with_high_sizing_floor`) |

New wiring tests, written against the live-shaped payload from the audit
(`value=77.95`, `metadata={"period": 9, "weight": 1.0}`):

- `test_simple_rsi_leg_fires_on_live_shaped_payload`
- `test_simple_rsi_leg_still_reads_metadata_value_if_producer_uses_it`
- `test_simple_rsi_leg_returns_none_when_reading_absent`
- `test_mean_reversion_reads_value_field_and_fires_when_overbought`
- `test_mean_reversion_returns_none_when_rsi_reading_absent`
- `test_mean_reversion_skips_bollinger_when_bands_absent`
- `test_mean_reversion_does_not_raise_when_sma_atr_missing`
- `test_ensemble_votes_sell_when_rsi_leg_opposes_a_weak_multi_buy`

**Full suite — 36 failed / 1542 passed / 795 skipped.** No failure is traceable to
this work. Proven, not assumed:

- Stashed **only** `services/trading-engine/app` (HEAD app code, same `.env`, same
  tests, same cwd) and re-ran the failing set. `test_main.py::TestLifespan::test_lifespan_startup`
  fails **identically** at HEAD → pre-existing, filed as OP-16.
- `tests/unit/test_repositories.py` (21) and `tests/test_handler_endpoints.py` (1)
  fail only in whole-suite runs and **pass in a 5-file run** → cross-test
  pollution, pre-existing.
- `tests/strategies/test_pairs_trading.py` (11) and
  `tests/integration/test_connector_contract.py` (2) fail at clean HEAD in a
  separate worktree → pre-existing (consistent with OP-12).

## Constraints honored

- Per-trade cap 2% LIVE non-negotiable (CLAUDE.md §5). This change makes the cap
  *bind*, where before it was silently discarded.
- Paper stays relaxed at 10% per ADR-010 — the PAPER preflight path is unchanged
  and `test_check_cap_paper_allows_floor_above_cap` pins it.
- No change to stop-loss derivation, SHORT enforcement, or risk-cap plumbing. The
  mean-reversion anchor change touches target/stop *inputs* only, and only on paths
  that previously produced a degenerate (target == entry) setup or raised.

## Out of scope, from the plan

F-3 (daily-loss cap measured against `paper_initial_balance`), F-4 (dead strategy
infra), F-5 (test packaging), F-6 (stale ADR reference). Filed in the audit,
not addressed here. Note F-3 has since been partly overtaken by ADR-028
(`56d3f8d`, breaker 5% → 12%).

## Found during this work, NOT fixed — follow-ups

1. **11 surviving `10000.0` capital literals in `app/strategies/`** — the
   260803-4mt AST invariant test (`tests/test_account_size_invariant.py`) does not
   catch *function default parameters* or *hardcoded call arguments*, so these
   passed the new gate:
   - defaults: `mean_reversion_strategy.py:104`, `hybrid_strategy_router.py:141`,
     `momentum_breakout_strategy.py:1239,1473`, `support_resistance_strategy.py:783,1175`,
     `research_optimized_strategy.py:883`, `funding_rate_arbitrage.py:252`
     (`portfolio_value`), `pairs_trading.py:259` (`portfolio_value`)
   - **actual call arguments, worse than defaults**: `momentum_breakout_strategy.py:300`
     `capital=10000.0`, `support_resistance_strategy.py:201` `capital=10000.0`
   - **inert safety arm**: `grid_trading_strategy_v2.py:105`
     `MAX_POSITION_VALUE_USD = 10000.0` — a $10k per-position ceiling on a $100
     account can never fire. Same shape as the kill-switch arm 260803-4mt fixed at
     `trading_enhancements/kill_switch.py:65`.

   Mitigation today: every in-tree caller of the two ensemble legs passes `capital`
   explicitly (`multi_strategy_ensemble.py:193,221`; `hybrid_strategy_router.py:184`),
   so the defaults are dead on the live path. They are a trap for the next caller.

2. **OP-16** — `.env` carries `trading_symbols` entries with no matching
   `symbol_allocations`; `app/config.py:688` raises at lifespan startup via
   `app/lifespan/data.py:33`. Pre-existing, unrelated to this task.
