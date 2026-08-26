# TA Signal-Path Correctness — Design (Phases 21 + 22)

- **Date:** 2026-08-26
- **Status:** Approved by operator 2026-08-26 (brainstorming session)
- **Scope decision:** Whole TA signal path — `services/technical-analysis/**` plus trading-engine signal consumers (`enhanced_aggregator`, strategies). Not TA service strictly.
- **Process decision:** GSD phases 21 + 22, preceded by a read-only verification audit.
- **Goal ordering decision:** Correctness first. Edge research is a separate follow-on effort through `backtesting/edge_lab/` — explicitly not this work.

## Goal

Make the TA signal path fully correct and honest: every indicator leg computes correctly, votes (or deliberately does not vote) as designed, parameters come from settings rather than scattered literals, and no price-domain value is destroyed by fixed-precision rounding. End state: signals mean what they say.

**Explicit non-goal: profitability.** Twelve strategy families tested across two eras, zero survivors; latest battery (2026-08-26, $10k, full cost stack) posts OOS Sharpe −0.58, 5/5 walk-forward FAIL. Correctness work cannot and does not claim to create edge. Any future edge claim goes through `edge_lab` with DSR/CPCV proof.

## Section 1 — Pre-phase audit (read-only, no code changes)

The defect table in `.planning/STATE.md` is dated 2026-07-29. The aggregator changed 2026-08-23 (quick task 260823-3j3: MACD re-bucketed to TREND, MTF confidence derivation, volume threshold wiring, ensemble confidence normalization). Memory (2026-08-17) contradicts STATE.md on TA-AGG-01 ("ADX already votes" vs "0 ADX refs in handlers/analysis.py").

Audit dimensions, each run by a read-only agent and adversarially verified by a second:

1. **Vote wiring** — which indicator legs actually vote today, in TA `handlers/analysis.py` and trading-engine `enhanced_aggregator`; adjudicate TA-AGG-01.
2. **Param sourcing** — MACD 5/35/5 and BB std 2.5 hardcoded as `Query(default=…)` vs settings-sourced; full inventory of hardcoded indicator params; adjudicate TA-AGG-02/03.
3. **Price precision** — enumerate all current price-domain `round(price, 2)` sites across both services (was 22 across 7 files); adjudicate PRICE-01/02 scope.
4. **Leftovers** — HYG-03 CORS hardening state, dead ML imports in the TA path, GRU model staleness (report only), account-size literals.

Output: confirmed-open defect list with `file:line` evidence, written to `.planning/audits/2026-08-26-ta-signal-path-audit.md`. Items found already closed get closed with evidence, not re-fixed. This list feeds both phase plans.

## Section 2 — Phase 21: aggregator correctness

Scope comes from the audit. Expected shape:

- Source MACD/BB (and any other drifted) indicator params from `Settings`; remove `Query(default=…)` literals as the effective source of truth.
- Close any confirmed vote-wiring gaps (legs computed but silently dropped, or double-counted).

Constraints (measured decisions — do not relitigate):

- Volume stays a confirmation gate, never a voter (2026-08-17 decision).
- No threshold tuning. Phase-3 verdict stands: IS/OOS rankings invert; threshold changes are not correctness fixes.
- Live mode stays `ensemble`; hybrid router stays advisory.

Behavior verified by before/after signal comparison on the 5 validated symbols (BTC, ETH, SOL, BNB, ADA).

## Section 3 — Phase 22: price precision

- Replace confirmed price-domain `round(price, 2)` sites with tick-size-aware handling or `float()` passthrough (pattern from commit `487d1bd`, the ADA fix).
- Pinned regression test: sub-$1 asset (ADA) price survives the full signal path without precision loss.
- Min-notional rejection paths untouched: reject with reason, never clamp up.

## Section 4 — Verification (per CLAUDE.md §7)

Per phase, all of:

1. Host tests green (trading-engine from `services/trading-engine` cwd with `--no-cov`; TA suite).
2. Rebuild + `--force-recreate` every changed service (stale in-memory state is the most common false pass).
3. Live signal pull on the 5 validated symbols through the running stack.
4. DB row proof where applicable (paste the SELECT).
5. `/verify-stack` before any "done" claim.

## Out of scope

GRU retrain (stale since 2025-12-10 but gated off — inert), LSTM purge (Phase 23 owns it), new indicators or strategies, edge research, threshold changes, ML gate flip, any LIVE-mode work.

## Flow

Audit → `/gsd:plan-phase 21` (audit findings as context) → execute → verify → `/gsd:plan-phase 22` → execute → verify. Roadmap phases 21/22 get re-scoped from audit evidence per GSD discipline.
