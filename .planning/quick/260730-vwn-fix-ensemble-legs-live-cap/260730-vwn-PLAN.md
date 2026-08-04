---
quick_id: 260730-vwn
slug: fix-ensemble-legs-live-cap
date: 2026-07-30
status: complete
source: .planning/audits/2026-07-30-strategy-audit.md
must_haves:
  truths:
    - "SimpleRSIStrategy.generate_signal returns a non-None signal for a live-shaped RSI IndicatorSignal (value on .value, not in metadata)."
    - "MeanReversionStrategy no longer substitutes neutral defaults (RSI 50.0 / BB position 0.5) when an input is absent."
    - "Ensemble position_size_pct never exceeds settings.max_risk_per_trade, for any floor/confidence combination."
    - "A LIVE boot with ensemble_min_position_pct > 0.02 is refused."
  artifacts:
    - services/trading-engine/app/models/signal.py
    - services/trading-engine/app/strategies/simple_rsi_strategy.py
    - services/trading-engine/app/strategies/mean_reversion_strategy.py
    - services/trading-engine/app/strategies/multi_strategy_ensemble.py
    - services/trading-engine/app/preflight/checks.py
    - services/trading-engine/app/main.py
    - services/trading-engine/tests/strategies/test_ensemble_leg_wiring.py
    - services/trading-engine/tests/strategies/test_multi_strategy_ensemble_sizing.py
    - services/trading-engine/tests/test_preflight_checks.py
---

# Quick Task 260730-vwn — Fix F-1 (dead ensemble legs) and F-2 (LIVE cap escape)

Both defects are documented with live evidence in `.planning/audits/2026-07-30-strategy-audit.md`.

## Task 1 — F-1: ensemble legs read the wrong field (HIGH)

**Problem.** `signal_aggregator.py` stores an indicator's numeric reading on the
`IndicatorSignal.value` field. Two of three ensemble legs read
`indicator.metadata["value"]`, which is never populated. `simple_rsi` bails to
`None` every call; `mean_reversion` silently substitutes neutral defaults
(RSI `50.0`, Bollinger position `0.5`) and therefore never reaches a threshold.
Result: 126/126 live signals over 6h came from the `multi_indicator` leg alone.

**Files / actions.**

1. `app/models/signal.py` — add `IndicatorSignal.numeric_value()`: returns
   `self.value`, falling back to `metadata["value"]` for any producer that still
   writes there, else `None`. One definition, both legs use it.
2. `app/strategies/simple_rsi_strategy.py:51-56` — read via `numeric_value()`.
3. `app/strategies/mean_reversion_strategy.py:113-198` —
   - read RSI / SMA / ATR via `numeric_value()`;
   - **drop the neutral fallbacks.** Missing RSI → return `None` (cannot evaluate
     mean reversion without it). Missing Bollinger position → skip the BB checks
     entirely rather than scoring a fabricated 0.5;
   - derive BB position from the bands the producer actually emits
     (`upper_band` / `lower_band`) when no explicit `position` key is present;
   - fix the latent `UnboundLocalError`: `sma_value` / `atr_value` are read at
     the signal-construction site but only assigned inside a conditional block.
     Unreachable while the leg was dead; reachable the moment it fires.

**Verify.** New `tests/strategies/test_ensemble_leg_wiring.py`, written first and
watched fail: a live-shaped RSI payload (`value=77.95`, `metadata={"period":9,
"weight":1.0}`) must produce a SELL from the RSI leg, and the three-leg ensemble
must emit SELL where the multi-indicator leg alone says BUY. Plus an
absent-input test asserting no neutral-default fabrication.

**Done.** Both legs vote against real payloads; no silent defaults remain.

## Task 2 — F-2: sizing floor overrides the LIVE per-trade cap (HIGH)

**Problem.** `multi_strategy_ensemble.py:299` computes
`max(floor, min(cap, scaled))`. The floor is applied *after* the clamp, so
whenever `floor > cap` the cap is discarded. With the LIVE cap at 0.02 and the
default `ensemble_min_position_pct` at 0.05, every LIVE trade sizes at 5% — 2.5×
the non-negotiable cap — at any confidence. Neither the boot gate
(`main.py:284-292`) nor `preflight.check_cap` inspects the floor, so the breach
passes preflight.

**Files / actions.**

1. `app/strategies/multi_strategy_ensemble.py` — reorder to
   `min(cap, max(floor, scaled))` so the cap is the last word. Log when the floor
   is clamped by the cap, so a misconfiguration is visible rather than silent.
2. `app/preflight/checks.py` — extend `check_cap` to also FAIL when
   `ensemble_min_position_pct > _LIVE_STRICT_CAP` in LIVE.
3. `app/main.py` — mirror the same condition in the boot refusal, reusing the
   existing `LIVE_PREFLIGHT_REJECTED` grep-gate literal (must not be split).

**Verify.** New sizing test: `cap=0.02, floor=0.05` → `position_size_pct == 0.02`
for low, mid and high confidence. New preflight test: LIVE + floor 0.05 → FAIL;
LIVE + floor 0.02 → PASS; PAPER + floor 0.05 → PASS (ADR-010 relaxation intact).
Existing five sizing tests must stay green — the reorder is a no-op whenever
`floor <= cap`.

**Done.** Cap binds unconditionally; a LIVE flip with a too-high floor refuses to boot.

## Out of scope

F-3 (daily-loss cap measured against `paper_initial_balance`), F-4 (dead strategy
infra), F-5 (test packaging), F-6 (stale ADR reference). Filed in the audit,
not addressed here.

## Constraints honored

- Per-trade cap 2% LIVE is non-negotiable (CLAUDE.md); paper stays relaxed at 10% per ADR-010.
- Test-first per `.claude/skills/trading-strategy-dev` — failing test observed before implementation.
- No change to stop-loss derivation, SHORT enforcement, or risk-cap plumbing.
