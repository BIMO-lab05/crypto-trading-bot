---
type: meta
title: "Hot Cache"
status: current
created: 2026-05-05
updated: 2026-08-19
tags: [meta, hot]
---

# Recent Context

## Last Updated
2026-08-19. WS1-C shipped (research layer + edge loop); **battery #2 = 5× REJECT**; trial ledger live as the anti-p-hacking rail.

## State (v1.3, executing, 3/9 phases)
- Paper mode, $100 account, auto-trader armed. **Clean-data epoch 2026-08-12T13:47:20Z**; the 08-12..16 Docker outage was repaired (`.planning/evidence/resume-2026-08-16.md`) and produced no trades, so the epoch stands.
- Phases 16–18 complete. Next: Phase 19 (order reconciliation + idempotency).
- 8/9 services healthy; ml-prediction behind `ml` profile, sentiment behind `analytics` — neither starts by default.

## Edge status — twelve families, zero survivors
- **Two pre-registered batteries, all REJECT.** #1 (2026-08-17, 8 variants): xs_momentum, vol_breakout, funding_carry, lf_trend. #2 (2026-08-18, 17 variants): those four plus pairs_statarb.
- **Two gates.** Gate 1: gross edge ≥ 2× taker cost. Gate 2: DSR ≥ 0.95 **and** ≥ 0.7 of CPCV paths positive. `lf_trend` cleared Gate 1 on 4/5 variants (best `ratio_taker` 15.511) and still died on Gate 2 — outlier trades, not a distribution. **Clearing Gate 1 is not a result.**
- **Trials floor ratchets.** `trial_ledger.json` is append-only; DSR deflates at `max(effective_floor, n_paths)`. Floor 16 → 21; battery #2 ran floor 21 vs 45 CPCV paths (paths bound). 30 rows now. Never reset it.
- Evidence: `.planning/evidence/killtests/`. Every documented caveat points **optimistic**.

## Cost model — date every P&L figure
Three legs, three commits: slippage `fb45efe` (08-03), correct fees from the clean-data epoch (08-12), perp funding on closes `b9fadc0` (08-18, `paper_funding_enabled` default **true**). A figure is only net of what had shipped when it was measured; averaging across those boundaries is a measurement error.

## Key facts (details: ADR-018..028 + [[log]])
- Paper accounting overhauled (side-aware closes; `reduce_only` rejects). Kill switch fed **equity**, streak advances on closes only. Portfolio-manager mirrors engine.
- **2026-08-12 profit-path audit**: 16 defects fixed (`63595b0`..`2a48846`). No "profitability bug" existed — the strategy is chance-level. Backtest costs went **up**; old in-service backtest figures do not reproduce.
- **`DEFAULT_LEVERAGE` 10.0 → 1.0** (2026-08-04, AUDIT §6.4/H1). At 10× the sizing formula multiplied the 10% per-trade cap back to ~100% of balance per trade. Do not raise it to clear min-notional.
- RES-01 repaired: `sum(trades) = positions = portfolio = 0.37103039` exactly.

## Correction to the 2026-07-30 entry
**`_archive_lstm/` does not exist** was environment-dependent, not true-or-false: `.gitignore:248` excludes it, so it exists in the operator's working copy (27 files, 41 MB) and is absent from fresh clones, containers, and CI. The claim has flipped twice — check `.gitignore`, and say which environment you looked in. Either way the purge is incomplete: `app/models/ensemble_model.py:15` imports `LSTM`, `:192-195` trains a leg (ML-PURGE-02, Phase 23).

## Architecture
- **No live event bus.** Synchronous REST only; RabbitMQ deployed but nothing wires AMQP — [[modules/Architecture-Overview]], ADR-016.

## Open items / next
- Twelve families deep (7 legacy + 5 battery) with no edge. The infrastructure's value is **killing candidates cheaply** — "disproved in an afternoon" is a win.
- **LIVE is not mechanically viable at $100** regardless of edge: the 2% LIVE cap is $2, under the ≈$5 venue minimum at any sane stop distance. Frontend also has no login flow.
- Open minors: RES-09 (PM trade history in-memory), RES-10 (in-container gateway test rule impossible — image has no `tests/`), RES-11 (ruff 88-col hook), RES-12 (duplicate tickers retention job). Unrotated logs: api-gateway 834 MB, portfolio-manager 941 MB (2026-05-20).
