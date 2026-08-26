---
quick_id: 260823-3j3
slug: fix-ensemble-confidence-units
status: in-progress
created: 2026-08-23
---

# Fix the ensemble confidence unit mismatch that blocks all trading

Source investigation: `.planning/evidence/hold-funnel-2026-08-22.md`

## Problem

`MultiStrategyEnsemble.generate_signal` scaled each leg's contribution by its
share of ALL THREE legs' weight, then handed the result to
`auto_trader._ensemble_passes_signal_gates`, which compares it against
`min_signal_confidence = 0.30` — a CONVICTION floor, the same constant
`RiskManager.validate_signal` applies to an aggregator confidence on the REST
path. A vote-share was being measured against a conviction bar.

Two knobs contradicted each other: `MIN_AGREEING_LEGS = 1` says one leg
suffices, while the all-legs denominator capped a lone leg at 1/3 and so
demanded post-MTF conviction >= 0.90 against a scale topping out near 0.62.

## Tasks

| # | Task | Status |
|---|---|---|
| 1 | Normalise ensemble score over firing legs | **done** — `b4cb894`, deployed + verified |
| 2 | MTF forwards a confidence matching the consensus action | pending |
| 3 | Clamp post-MTF confidence via `validate_confidence` | pending |
| 4 | Re-bucket MACD out of MOMENTUM | pending — makes diversity HARDER |
| 5 | Volume `signal_type` / WEAK band reachable | pending |
| 6 | Funnel: symbol attribution, terminal_stage, cycles | pending |

## Constraints

- Account is $100. No account-size literals. Services read their own `Settings`.
- TDD. Run from `services/trading-engine` with `--no-cov`; conftest pins
  `env_file=None` so do NOT export env vars.
- Format hook runs ruff at 88 cols vs the repo's 100 and strips imports — edit
  via Bash + pathlib, then grep the diff for import churn.
- No threshold value may change.

## Verification standard

CLAUDE.md section 7: order log line + persisted DB row + service restart.
