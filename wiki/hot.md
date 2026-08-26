---
type: meta
title: "Hot Cache"
status: current
created: 2026-05-05
updated: 2026-08-26
tags: [meta, hot]
---

# Recent Context

## Last Updated
2026-08-26. **Account is $10,000 and DEPLOYED** per [[decisions/ADR-029-account-size-10k-research-scale|ADR-029]]: DB reseeded (old $100-era trades archived in `trades_archive_100usd`/`positions_archive_100usd` + pg_dump), trading-engine/portfolio-manager recreated with the new env, auto-trader RUNNING at $10,000 (5 symbols, 60m). Risk knobs UNCHANGED: 10%/trade ($1,000), 12% daily ($1,200), 5% ensemble floor ($500), LIVE 2% untouched ($200). Bare `10000` literals are STILL defects (routing, not arithmetic). First $10k cost-on battery: **no edge** (`docs/BACKTEST_BATTERY_2026-08-26_10K.md` — ensemble analog DSR 0.002 under bybit_perp+ATR-slippage+funding). prefer_maker isolation run harvested early: 3 trades, all taker, zero maker evidence (`.planning/evidence/isolation-run-harvest-2026-08-26.md`). DB outage 08-23→08-26 repaired; 52h kline hole verified closed.

## State (v1.3, executing, 3/9 phases)
- Paper mode, **$10,000 declared baseline (ADR-029; was $100)**, auto-trader RUNNING, kill-switch clear. Clean-data epoch 2026-08-12T13:47:20Z stands; a NEW measurement epoch starts at the 2026-08-26 reseed.
- Phases 16–18 complete. Next: Phase 19 (order reconciliation + idempotency).
- Services 14/14 healthy after the 2026-08-26 infra repair; ml-prediction behind `ml` profile, sentiment behind `analytics` — neither starts by default.

## Edge status — twelve families, zero survivors
- **Two pre-registered batteries, all REJECT.** #1 (2026-08-17, 8 variants): xs_momentum, vol_breakout, funding_carry, lf_trend. #2 (2026-08-18, 17 variants): those four plus pairs_statarb. **Plus the 2026-08-26 $10k battery: phase-1 stack fires 0–1 trades/yr; ensemble walk-forward FAILs every ADR-013 gate.**
- **Two gates.** Gate 1: gross edge ≥ 2× taker cost. Gate 2: DSR ≥ 0.95 **and** ≥ 0.7 of CPCV paths positive. `lf_trend` cleared Gate 1 on 4/5 variants (best `ratio_taker` 15.511) and still died on Gate 2 — outlier trades, not a distribution. **Clearing Gate 1 is not a result.**
- **Trials floor ratchets.** `trial_ledger.json` is append-only; DSR deflates at `max(effective_floor, n_paths)`. Floor 16 → 21; battery #2 ran floor 21 vs 45 CPCV paths. 30 rows now. Never reset it.
- Evidence: `.planning/evidence/killtests/`. Every documented caveat points **optimistic**. Golden-parity killtest GREEN 2026-08-26 (offline replay ≡ live TA).

## Cost model — date every P&L figure
Three legs, three commits: slippage `fb45efe` (08-03), correct fees from the clean-data epoch (08-12), perp funding on closes `b9fadc0` (08-18, `paper_funding_enabled` default **true**). A figure is only net of what had shipped when it was measured; averaging across those boundaries is a measurement error. Account-size provenance: pre-08-03 = frictionless $10k; 08-03→08-25 = $100 floor-bound; 08-26 onward = $10k full-cost (the only citable era for current config).

## Key facts (details: ADR-018..029 + [[log]])
- Paper accounting overhauled (side-aware closes; `reduce_only` rejects). Kill switch fed **equity**, streak advances on closes only. Portfolio-manager mirrors engine.
- **2026-08-12 profit-path audit**: 16 defects fixed (`63595b0`..`2a48846`). No "profitability bug" existed — the strategy is chance-level. Backtest costs went **up**; old in-service backtest figures do not reproduce.
- **`DEFAULT_LEVERAGE` 10.0 → 1.0** (2026-08-04, AUDIT §6.4/H1). At 10× the sizing formula multiplied the 10% per-trade cap back to ~100% of balance per trade. Do not raise it to clear min-notional.
- PR #142 line merged 2026-08-26: never record a fill the connector did not confirm (fail-closed on missing `success` AND missing `orderId`).

## Correction to the 2026-07-30 entry
**`_archive_lstm/` does not exist** was environment-dependent, not true-or-false: `.gitignore:248` excludes it, so it exists in the operator's working copy (27 files, 41 MB) and is absent from fresh clones, containers, and CI. The claim has flipped twice — check `.gitignore`, and say which environment you looked in. Either way the purge is incomplete: `app/models/ensemble_model.py:15` imports `LSTM`, `:192-195` trains a leg (ML-PURGE-02, Phase 23).

## Architecture
- **No live event bus.** Synchronous REST only; RabbitMQ deployed but nothing wires AMQP — [[modules/Architecture-Overview]], ADR-016.

## Open items / next
- Twelve+ families deep with no edge. The infrastructure's value is **killing candidates cheaply** — "disproved in an afternoon" is a win.
- **LIVE is no longer arithmetically blocked at $10,000** (2% = $200 clears every venue floor). The ONLY barrier is the four deliberate flags — never cite account arithmetic as a LIVE safeguard. Frontend still has no login flow.
- Maker-cost question OPEN: the prefer_maker run produced zero maker fills — needs an instrumented order path logging attempt/fallback.
- Open minors: RES-09 (PM trade history in-memory), RES-12 (duplicate tickers retention job). RES-10 fixed (gateway image ships tests/, baseline 3f/440p), RES-11 fixed (hook at 100 cols). Unrotated logs: api-gateway 834 MB, portfolio-manager 941 MB (2026-05-20).
