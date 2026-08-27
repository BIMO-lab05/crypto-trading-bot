---
phase: 21-ta-aggregator-widening-leakage-net
verified: 2026-08-27T15:30:00Z
status: passed
score: 10/10 phase-goal scope items verified
overrides_applied: 1
overrides:
  - must_have: "Live before/after admission comparison on BTC/ETH/SOL/BNB/ADA through the running stack (21-CONTEXT <specifics>)"
    reason: "Live funnel has emitted zero trades since 2026-08-16; the 60m timeframe resolved HOLD in every recomputed cycle at gate time, so a live before/after reads 'no change' for every fix and proves nothing. Substituted by a deterministic four-arm ablation (independently re-run in this verification session, byte-identical to the evidence table) plus a labelled five-symbol smoke (no crash, ATR present, sane stop distances). Operator approved this evidence package at the 21-09 checkpoint."
    accepted_by: "operator (verbatim response recorded in .planning/evidence/21-phase-gate-2026-08-26.md §7)"
    accepted_at: "2026-08-27"
re_verification: null
---

# Phase 21: TA Aggregator Widening + Leakage Net Verification Report

**Phase Goal (per dated re-scope note, authoritative over the stale 2026-05-23 ROADMAP text):** make the whole TA signal path correct — leakage regression suite (TA-AGG-04), TA-AGG-01 test/docs residue, param single-sourcing, ATR threading with percent→fraction unit contract, MTF demote-to-HOLD gating of all ensemble legs, leg source-diversity guard, mirror-literal cluster, hygiene. Explicit non-goal: profitability.

**Verified:** 2026-08-27
**Status:** passed
**Re-verification:** No — initial verification

## Method

This report does not trust SUMMARY.md claims. Every load-bearing number below was reproduced independently in this session: full test suites re-run from source, the ablation script re-executed and cross-checked byte-for-byte against the evidence table, `docker exec` reads taken directly against the running, force-recreated containers, and the "volume never votes" and "engine omits TA-owned params" claims re-derived by reading the actual source lines rather than accepting the SUMMARY's grep counts.

## Goal Achievement — 10 phase-goal scope items

| # | Scope item (21-CONTEXT) | Status | Evidence (independently reproduced) |
|---|---|---|---|
| 1 | TA-AGG-04 — leakage regression suite, 13 modules + aggregate path | ✓ VERIFIED | `services/technical-analysis/tests/test_leakage_regression.py` (1,149 lines) exists; re-ran: **122 passed**. Suite is falsifiable — SUMMARY's injected-mutation captures (`.shift(-1)` on RSI, `.shift(-2)` on ADX, `center=True` on ATR) are documented with RED output; found and fixed a real pre-existing leak in `EnhancedSqueezeMomentum.sqz_confidence` on first run. |
| 2 | TA-AGG-01 residue — gating tests + wiki doc, volume never a voter | ✓ VERIFIED | Re-ran `test_aggregator_new_legs.py`: **15 passed**. Independently read `handlers/analysis.py:110-251`: `final_signal` is computed at line ~190 from `signal_weights` before the volume block; volume (`:201-221`) only multiplies `confidence` via `volume_penalty`, never appended to `signals` or reassigning `final_signal`. `wiki/modules/technical-analysis.md` exists with a "Corrections 2026-08-26" section. |
| 3 | TA-AGG-02/03 closure evidence (MACD 5/35/5, BB std 2.5, settings-sourced) | ✓ VERIFIED | `.planning/evidence/21-TA-AGG-02-03-closure.md` exists with file:line citations. `test_endpoint_defaults_from_settings.py` re-ran: included in the 711-passed TA full suite. |
| 4 | P21-1 — ATR threading + percent→fraction unit contract | ✓ VERIFIED | Re-ran `test_ensemble_leg_wiring.py` + `test_ensemble_atr_levels.py`: **37 passed**. Container check: `docker exec crypto-bot-trading grep -c _resolve_atr_fraction app/strategies/simple_rsi_strategy.py` → **2**. The BTC/ETH/BNB negative-stop-price claim was not independently re-measured against live 60m ATR readings in this session — it is read from the phase-gate document's table, and the code path that produces it (`_resolve_atr_fraction`'s declared-contract read replacing the old `if atr_pct > 1.0` magnitude guess) was directly confirmed in source. |
| 5 | P21-2 — leg source-diversity guard | ✓ VERIFIED | Re-ran `test_ensemble_diversity_guard.py`: **22 passed** (part of the 123-passed combined run below). Container check: `grep -c MIN_LEG_CATEGORIES` → **6**. Mutation-checked in SUMMARY (guard deletion turns exactly its own test red); `multi_indicator`-alone-still-emits case is proven distinct from a naive `MIN_AGREEING_LEGS=2` rule. |
| 6 | P21-3 — MTF demote-to-HOLD gates all three ensemble legs | ✓ VERIFIED | Re-ran `test_mtf_confidence_consolidation.py`: **11 passed** (part of combined run). Container check: `demoted_to_hold` present **5x** in `multi_strategy_ensemble.py`, **2x** in `signal_aggregator.py`. Call-chain from `get_trading_signal_multi_timeframe` → `generate_signal` verified read-only (no reassignment) per SUMMARY's line citations. |
| 7 | P21-4/P21-5 — param single-sourcing (SMA/EMA 21, Ichimoku 20/60/120) | ✓ VERIFIED | Re-ran `test_engine_param_omission.py`: **4 passed**. Independently grepped `signal_aggregator.py`: `fetch_sma`/`fetch_ema` send `params = {"interval": interval}` only (no `period`); `fetch_macd` still sends its full param set unrelated to this fix. **Live container check** (ground truth, see caveat below): `docker exec crypto-bot-ta python3 -c "...get_settings()..."` → `21 21 20 60 120 200` — exact match to the plan's acceptance criterion. |
| 8 | P21-6 — dashboard aggregate + MTF handlers read Settings | ✓ VERIFIED | Re-ran `test_aggregator_new_legs.py` (15 passed, included above) — mutation-checked with a "moved-settings routing proof" catching two cases (volume signal type, ADX period) that a naive equality assertion would have missed. `default_aggregate_limit` wired into both `handlers/analysis.py` kline fetches. |
| 9 | P21-7 — mirror-literal cluster | ✓ VERIFIED | Re-ran `test_mirror_literals.py`: included in combined 123-passed run below. Regime re-derivation replaced with a read of TA's own `regime` field via an explicit `TA_REGIME_TO_ENGINE_REGIME` map; ADX period omitted from the engine's outbound `market_regime.py` request. |
| 10 | P21-8 — hygiene batch | ✓ VERIFIED | `.bak` file confirmed absent (`find services/technical-analysis -iname "*.bak"` → empty); `.dockerignore` contains `*.bak`. `python3 scripts/check_capital_literals.py` → exit 0. Dead ADX-from-ATR-metadata fallback deleted from `hybrid_strategy_router.py`. Docstring capital literal in `advanced_position_sizing.py` resolves from `Settings.paper_initial_balance` (grep for `capital=10000` returns nothing). |

## Independently reproduced test evidence

| Check | Command | Result | Matches SUMMARY/gate claim? |
|---|---|---|---|
| TA leakage suite | `cd services/technical-analysis && pytest tests/test_leakage_regression.py --no-cov -q` | **122 passed** | Yes |
| TA full suite | `cd services/technical-analysis && pytest tests/ --no-cov -q` | **711 passed** | Yes (phase-gate: 711 passed) |
| Engine full suite | `cd services/trading-engine && pytest tests/ --no-cov -q` | **2122 passed, 795 skipped, 0 failed** | Yes (phase-gate: 2122 passed, 795 skipped, EXIT=0) |
| Repo-root invariants | `pytest tests/test_account_size_invariant.py tests/test_account_config_sync.py tests/test_price_rounding_invariant.py --no-cov -q` | 40 dots, 0 F/E | Yes (phase-gate: 40 dots) |
| Engine targeted (omission, MTF, ATR, threshold, diversity, mirror) | 7 files combined, `-k "not threshold_lock"` | **123 passed, 2 deselected** | Yes |
| Threshold lock | `pytest tests/ -k threshold_lock --no-cov -q` | **2 passed, 5 skipped, 2910 deselected** | Yes (matches phase-gate exactly) |
| TA build-hygiene + aggregator + endpoint-defaults | 3 files combined | **95 passed** | Yes |
| Capital literals guard | `python3 scripts/check_capital_literals.py` (repo root) | exit 0 | Yes |
| Ablation harness (reproducibility) | `python3 scripts/ablation_ensemble_admission.py --arms all --check-determinism` | baseline 9/12 admitted, +ATR 9/12, +gates 4/12, both 6/12; **determinism: True** | Byte-identical to `.planning/evidence/21-behavior-change-2026-08-26.md`'s table |
| Container settings (SMA/EMA/Ichimoku/limit) | `docker exec crypto-bot-ta python3 -c "...get_settings()..."` | `21 21 20 60 120 200` | Yes — reproduces phase-gate's live claim directly against the running, force-recreated container |
| Container gate markers | `docker exec crypto-bot-trading grep -c ...` | `demoted_to_hold=5+2`, `MIN_LEG_CATEGORIES=6`, `_resolve_atr_fraction=2` | Yes |

## Locked constraints (21-CONTEXT) — independently re-checked, not taken on SUMMARY authority

| Constraint | Status | Evidence |
|---|---|---|
| No threshold value changed (`min_signal_confidence=0.30`, `AGGREGATION_THRESHOLD=0.10`, `MIN_AGREEING_LEGS=1`) | ✓ VERIFIED | `threshold_lock` tests pass (2 passed); container read confirms `MIN_AGREEING_LEGS=1`, `AGGREGATION_THRESHOLD=0.1`, `min_signal_confidence=0.3` live. |
| Volume never becomes a voter | ✓ VERIFIED | Independently read `handlers/analysis.py`: `final_signal` set before the volume block; volume only scales `confidence` via `volume_penalty`. No `signals.append` call reads from `volume_result`. |
| Narrow MTF gating (regime hard-block NOT folded in) | ✓ VERIFIED | `test_regime_hard_block_hold_is_not_recorded_as_an_mtf_demotion` exists and is part of the passing `test_mtf_confidence_consolidation.py` run; regime hard-block is explicitly named as DEFER-21-02, operator-accepted follow-up, not silently absorbed. |

## Requirements Coverage

| Requirement | Source plan(s) | Description | Status | Evidence |
|---|---|---|---|---|
| TA-AGG-01 | 21-04 | Aggregator vote residue (tests + docs); audit-superseded on the "widen the vote" clause | ✓ SATISFIED | Code-verified above; REQUIREMENTS.md checkbox still `[ ]`/"Pending" — see Traceability Gap below |
| TA-AGG-02 | 21-02 | MACD single-sourced (5/35/5) | ✓ SATISFIED (closure, no code change owed) | `.planning/evidence/21-TA-AGG-02-03-closure.md`; REQUIREMENTS.md checkbox still `[ ]`/"Pending" |
| TA-AGG-03 | 21-02 | BB std single-sourced (2.5) | ✓ SATISFIED (closure, no code change owed) | Same evidence file; REQUIREMENTS.md checkbox still `[ ]`/"Pending" |
| TA-AGG-04 | 21-01 | Leakage regression suite | ✓ SATISFIED | 122 tests, re-run and green; REQUIREMENTS.md checkbox correctly flipped to `[x]`/"Complete" |
| P21-1..P21-8 | 21-03 (P21-1, P21-8 partial), 21-06 (P21-2), 21-05 (P21-3), 21-02 (P21-4/5, P21-6 declared), 21-04 (P21-6 wired), 21-07 (P21-7), 21-08 (P21-8 residue) | Audit-defect IDs from `.planning/audits/2026-08-26-ta-signal-path-audit.md` | ✓ SATISFIED, by design not present in REQUIREMENTS.md | These are audit-defect IDs, not REQUIREMENTS.md-registered requirements — `grep -n "Phase 21" .planning/REQUIREMENTS.md` returns only the four TA-AGG-* rows, confirming P21-* were never expected there. No orphaned requirement. |

### Traceability gap (WARNING, not a code gap)

`.planning/REQUIREMENTS.md` lines 59-61 and 188-190 still show TA-AGG-01, TA-AGG-02, TA-AGG-03 as `[ ]` unchecked and "Pending" in the phase-tracking table, even though plans 21-02 and 21-04 declare `requirements-completed: [TA-AGG-01, TA-AGG-02, TA-AGG-03, ...]` in their frontmatter and the code/evidence back that up. Only TA-AGG-04's checkbox and traceability row were flipped (by plan 21-01). This is a documentation bookkeeping gap, not a code defect: `21-CONTEXT.md` explicitly states the 2026-08-26 audit is authoritative over REQUIREMENTS.md's stale 2026-05-23 text, and `ROADMAP.md` carries an explicit "Superseded 2026-08-26" note plus `[x]` completion for Phase 21 with `(completed 2026-08-27)`. Recommend a one-line follow-up: flip the three checkboxes and traceability-table rows in REQUIREMENTS.md to keep the two tracking documents consistent.

## Anti-Pattern Scan (Step 7)

Scanned every file this phase's diff touched (`git diff --name-only 80e6074..HEAD -- services/ scripts/`, 29 files):

- `TBD`/`FIXME`/`XXX` (debt-marker gate, BLOCKER if unreferenced): **0 matches** across all 29 files (`grep -cE` confirms 0 for every file).
- `TODO`/`HACK`/`PLACEHOLDER` (WARNING tier): 1 match — `services/trading-engine/app/auto_trader.py:3324` ("A LIMIT-IOC close for LIVE remains a TODO"). Confirmed **pre-existing**: `git log -S "LIMIT-IOC close for LIVE remains a TODO" -- app/auto_trader.py` resolves to commit `fb764d5`, well before this phase's base `80e6074`, and `git diff 80e6074..HEAD -- app/auto_trader.py` shows the phase's only change to this file is the per-cause rejection-telemetry block at line ~4756+, nowhere near line 3324. Not introduced by this phase — no action owed.
- No `return null`/empty-stub/hardcoded-empty-data patterns found in the reviewed diffs; SUMMARYs across all 9 plans self-report "Known Stubs: None" and the independently-run test suites corroborate (a stub would not produce the specific, non-trivial assertions that are failing/passing as documented).

## Human Verification

**None required — `passed`, not `human_needed`.** No frontend/UI change in this phase (backend-only: `services/technical-analysis/**`, `services/trading-engine/**`). No `<human-check>` blocks were deferred from `checkpoint:human-verify` in any of the 9 plans except 21-09's own operator-approval checkpoint, which is a phase-closure gate (not a deferred technical check) and has already been satisfied: the operator's verbatim sign-off is recorded in `.planning/evidence/21-phase-gate-2026-08-26.md §7` and `.planning/phases/.../deferred-items.md`, dated 2026-08-27, approving the phase-gate evidence and ratifying the ATR-fetch-failure mechanism.

The one item that could otherwise read as an open real-time-behavior verification gap — the admission-decrease effect from P21-3/P21-2 not yet observed on live production signals (live funnel emitted zero trades since 2026-08-16) — is handled via the **override recorded in this report's frontmatter**, not left as an unresolved human-verification item. It is a market-dormancy limitation, not a verification-method limitation: no human, any more than an automated check, can observe an effect that requires a directional signal that has not recurred. The phase's own evidence transparently labels the five-symbol live pull "smoke evidence only, not behaviour proof," and substitutes a reproducible, deterministic four-arm ablation (independently re-run in this session, byte-identical to the evidence table) as the mechanism for measuring the per-fix admission delta instead. The operator reviewed and approved this specific evidence package at the 21-09 checkpoint, which is the accepted-by basis for the override above.

## Non-blocking notes

1. **Stale host `.env` verification hazard (not a code defect).** `services/technical-analysis/.env` (gitignored, untracked, mtime 2026-06-04 — pre-dates this phase) shadows `default_sma_period`/`default_ema_period` to `20`/`20` when Python or pytest is run with `cwd=services/technical-analysis` **from the main checkout**. This makes plan 21-02's literal acceptance-criterion command (`python3 -c "...get_settings()..."` expecting `21 21 20 60 120 200`) unreproducible from the main checkout today, even though it reproduced correctly in the isolated worktree the executor used at the time (untracked files do not propagate to `git worktree` checkouts). **This does not affect the deployed system**: the Dockerfile only `COPY`s the `app/` subdirectory (verified — no `.env` inside `app/`), and no volume mount brings this file into the container. The `docker exec` read against the live, force-recreated container (`21 21 20 60 120 200`) is the canonical proof and is recorded above; a future auditor re-running the plan's literal one-liner from the main checkout should not read a `20 20` result as a regression. Recommend deleting or renaming the stale `services/technical-analysis/.env` to prevent this false-negative trap recurring.
2. **DEFER-21-01 (`EnhancedSqueezeMomentum.calculate` returns `None` on a duplicate index label) is a real, silent-voter-dropout defect**, verified pre-existing against base `80e6074` and correctly out of this phase's scope (not introduced or caused by phase 21; plan 21-01 fixed only its own contribution to the pattern). It is **not** in the operator-accepted DEFER-21-02..05 set — it was found and recorded independently in plan 21-01's SUMMARY addendum. Flagging as an unowned follow-up worth a tracked ticket, since a silent SQZMOM leg dropout on any duplicate-timestamp kline (a documented live possibility per TimescaleDB's kline-hole history) degrades the aggregate vote without any error surfaced.

## Gaps Summary

None blocking. All 10 phase-goal scope items are verified against the actual codebase — not merely claimed by SUMMARY.md — via full re-execution of both services' test suites (711 + 2122 passed, 0 failures), the repo-root invariant guards, the deterministic four-arm ablation, and direct reads against the live, rebuilt, force-recreated containers. All 9 plans' declared artifacts were confirmed present on disk and their associated test files re-run green. Locked constraints (no threshold change, volume never votes, narrow MTF gating) were independently re-derived from source rather than accepted on SUMMARY authority. One explicit override is recorded (live before/after admission comparison, superseded by the ablation + smoke evidence with operator sign-off — see frontmatter). The one real discrepancy surfaced during verification (stale host `.env` shadowing SMA/EMA to 20/20) was traced to ground truth and confirmed **not** to affect the deployed system. The one documentation-tracking gap (REQUIREMENTS.md checkboxes for TA-AGG-01/02/03 not flipped) is cosmetic and does not affect code correctness, given the audit-authoritative override is explicitly documented in both `21-CONTEXT.md` and `ROADMAP.md`.

---

*Verified: 2026-08-27*
*Verifier: Claude (gsd-verifier)*
