# Gap Audit — Design Spec

**Date:** 2026-08-19
**Status:** Approved design, pending user spec review
**Branch context:** work is read-only; scripts land under `audit/`, independent of `fix/ws1a-technical-analysis-correctness` code changes.

## 1. Purpose

A forensic-audit master prompt (Phases 0–6: system map, data integrity, leakage, execution realism, risk math, strategy cards, statistical validity) was submitted. Most of it has already been executed in this repo:

- **Verdict committed:** economic non-viability + statistical illusion. H4 killtest REJECT (49.07% directional accuracy, DSR 0.0); gross edge 0.0488%/trade vs 21–31 bp round-trip cost (Phase-0 audit 2026-08-04, `.planning/evidence/killtests/`).
- **Implementation-defect pass done:** 16 money-path defects fixed 2026-08-12 (`63595b0`..`2a48846`, `.planning/evidence/profit-path-audit-2026-08-12.md`); 29 minors deferred.
- **Edge batteries:** 2026-08-17 (4× REJECT) and 2026-08-18 (5× REJECT) via `backtesting/edge_lab/` kill-funnel with trial ledger.
- **Capital audit:** 2026-08-03 (`.planning/audits/2026-08-03-capital-audit.md`).

This engagement is therefore a **gap audit**: run only the checks from the master prompt that no existing evidence file covers, and answer one remaining question — *does a hidden implementation defect make the committed verdict itself untrustworthy?*

The "results change every time I touch something" symptom in the master prompt is **template boilerplate, not observed here** (user confirmed). The determinism check runs once, cheaply, to settle it empirically; it is not the priority.

## 2. Coverage diff (what is a gap, what is not)

| Master-prompt item | Status | Evidence |
|---|---|---|
| Component map, single-trade trace, sizing math derivation | DONE | profit-path-audit-2026-08-12; 2026-07-31 full-system diagnostic |
| Cost decomposition (gross vs round-trip cost) | DONE | Phase-0 killtests; edge_lab gate outputs |
| DSR / CPCV / walk-forward / multiple-testing correction | DONE | edge_lab batteries + `trial_ledger.json` |
| Capital-size assumption audit | DONE | 2026-08-03 capital audit |
| Synthetic random-walk detector | **ABSENT** | — |
| Determinism run (byte-identical reruns) | **ABSENT** | — |
| Invariant A proof (signal at bar t close → fill at t+1 open, cited line) | **UNVERIFIED** | — |
| Invariant B (intrabar SL+TP both in range → resolution rule) | **UNVERIFIED** | — |
| Leakage grep sweep over full feature/signal path | PARTIAL | ta-indicator-audit-2026-08-08 covered indicators only |
| Backtest equity reconciliation identity | PARTIAL | cash-ledger recon 2026-08-07/08 covered the live paper ledger, not the backtest engine |
| Funding application + sign for shorts | **UNVERIFIED** | CSVs exist in `backtesting/data/funding/`; application unproven |
| Inverted-strategy sign check | **ABSENT** | — |
| Realized-risk distribution + stop-vs-ATR | **ABSENT** | — |
| Repeatable audit harness (`run_all.py`) | **ABSENT** | — |

Anything marked DONE is cited, not re-derived (per CLAUDE.md §2 and memory records).

## 3. Deliverables

All new files, all read-only with respect to production code, under `audit/`:

| # | Script | Check | Pass condition |
|---|---|---|---|
| 1 | `gap_leakage_grep.py` | Sweep feature/signal path (`backtesting/`, `services/technical-analysis/`, `services/trading-engine/app/strategies/`) for `shift(-`, `bfill`/`backfill`, `interpolate`, `fillna(method=`, `rolling(... center=True`, full-series normalizers (fit/mean/std over whole array), and every `.resample(` call's `label=`/`closed=` args. Emit file:line + verdict per hit. | Zero unexplained future-facing operations in the signal path |
| 2 | `gap_invariants.py` | Static citation + dynamic probe of Invariant A (signal from bar *t* fills no earlier than *t+1* open) and Invariant B (when SL and TP both lie inside one bar, resolution is worst-case or explicitly documented). Counts trades affected by B in a reference run. | A: enforcing line cited and probe confirms one-bar lag. B: worst-case (or documented conservative) resolution |
| 3 | `gap_determinism.py` | Same backtest twice in one process, once in fresh process; byte-diff serialized outputs. | Byte-identical across all three runs |
| 4 | `gap_reconcile.py` | Run reference backtest; assert `final_equity == initial + Σ realized PnL − Σ fees − Σ funding` to the cent; verify funding sign on at least one held short against the historical funding CSV. | Identity holds to $0.01; short funding sign correct |
| 5 | `gap_randomwalk.py` | GBM/bootstrapped series volatility-matched to BTCUSDT; run the unmodified backtest engine on ≥3 existing strategies × ≥20 seeds. | Mean PnL ≈ −(modelled costs); no consistent positive expectancy on random data |
| 6 | `gap_signcheck.py` | Invert one representative strategy's signals; compare inverted PnL to costs. | Inverted PnL ≈ −(costs) ⇒ no sign/shift defect (no edge either direction). Inverted profit materially > costs ⇒ CRITICAL defect flag |
| 7 | `gap_risk_realized.py` | From reference-run trade ledger: distribution of realized loss as fraction of equity (mean/p95/max) vs configured 10% paper cap; stop distance vs entry ATR distribution. | p95 realized loss ≤ configured cap; stops not systematically inside 1 ATR without documented intent |
| 8 | `run_all.py` | Runs 1–7 in order, regenerates the data section of `FINDINGS-GAP.md`. | Single command reproduces the whole audit |
| 9 | `FINDINGS-GAP.md` | Report (see §5) | — |

## 4. Hard rules (inherited from master prompt, adapted)

1. **No production or test-suite code changes** in this engagement. Only `audit/` additions.
2. Every claim cites `path:line` or pasted executed output. Unchecked ⇒ "not verified".
3. No fabricated numbers. No parameter tuning. Costs may only go up, never down.
4. Account size comes from `shared.account` (host-run code) — never a literal. All runs at $100.
5. Prior DONE items are cited, not re-run.
6. Known environment traps honored: host runs from correct cwd with `--no-cov` where pytest is involved; pandas 3 `datetime64[us]` behavior; funding CSVs under `backtesting/data/funding/`.

## 5. Report format (`audit/FINDINGS-GAP.md`)

1. **Verdict statement** — confirm or overturn the committed verdict (non-viability + statistical illusion), with the new evidence.
2. **Defect table** sorted by expected PnL impact: `# | Severity | Component | File:line | Defect | Measured evidence | Est. impact | Proposed fix | Risk of fix`. Severity CRITICAL/HIGH/MEDIUM/LOW.
3. **Minimal reproduction** for each CRITICAL/HIGH (≤20-line script or failing assertion).
4. **What is NOT broken** — explicit list of checks that passed.
5. **Open questions**, numbered.
6. **Promotion list** — which checks graduate to permanent regression tests under `tests/` (expected: random-walk, determinism, reconciliation identity), pending user approval. Promotion is a separate follow-up engagement.

## 6. Execution sequence

Static and cheap first, expensive last:

1. `gap_leakage_grep.py` + `gap_invariants.py` (static analysis, minutes)
2. `gap_determinism.py` (one cheap run)
3. `gap_reconcile.py` (reference run + identity + funding sign)
4. `gap_randomwalk.py` (most compute)
5. `gap_signcheck.py`
6. `gap_risk_realized.py`
7. Write `FINDINGS-GAP.md`, **stop for user approval** before any fix or test promotion.

## 7. Out of scope

- Re-running edge batteries, Monte Carlo permutation tests, parameter surfaces (edge question is closed).
- WS1-A branch work (TA correctness) — separate stream; repaint checks belong there.
- Any strategy fix, parameter change, or cost-model change.
- Test promotion (follow-up after findings approval).

## 8. Error handling

- A gap script that cannot run (missing data, engine import failure) reports the blocker in `FINDINGS-GAP.md` as "not verified — blocked by X" rather than silently passing.
- Random-walk or reconciliation failures are treated as CRITICAL findings, not as reasons to adjust the harness until it passes.
