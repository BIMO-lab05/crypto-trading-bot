# Phase 16: Validated-Set Re-Audit — Context

**Gathered:** 2026-05-23
**Status:** Ready for planning
**Milestone:** v1.3 TA + Engine Correctness (paper-only)
**REQ-IDs covered:** AUDIT-01

<domain>
## Phase Boundary

Trust-no-docs forensic re-audit of every REQ in PROJECT.md `### Validated` (pre-v1, v1.0, v1.1, v1.2) plus the load-bearing project-rule claims in `CLAUDE.md`. For each REQ-ID, prove implementation against actual code with `file:line` evidence; classify as `satisfied | drift | missing`; produce a structured JSON artifact + a rewritten `### Validated` section + demotion entries + updated CLAUDE.md text where audit findings contradict it.

**This phase is a documentation-only audit. It MUST NOT touch service code.** If a REQ is found `drift` or `missing`, file the row, propose the downstream owner in Plan 06, and move on. Fixes happen in Phases 17–24:
- Phase 17 (TE-CAP-01..05) — RISK-04 cap enforcement, ADR-010 paper cap, RISK-06 maker/post-only, bare-except kill, emergency-stop admin auth
- Phase 18 (BC-FIX-01..03) — bybit_adapter endpoint paths, TapeReplayClient extension, connector router contract test
- Phase 19 (RECON-01..02) — order reconciliation loop, orderLinkId idempotency
- Phase 20 (PAPER-01..03) — paper-engine slippage, SL/TP triggers, Jan 2026 regression
- Phase 21 (TA-AGG-01..04) — aggregator widening (kills EXEC-03 "9-indicator" drift), MACD/BB param reconciliation, leakage net
- Phase 22 (PRICE-01..02) — round(price, 2) epidemic kill across 6 strategy files
- Phase 23 (ML-PURGE-01..05) — r2_score-on-prices removal (kills TOURN-07 drift), LSTM archive (kills CLAUDE-LSTM-ARCHIVED drift), feature_engineer.get_feature_names fix, marker-age check
- Phase 24 (HYG-01..04) — Sentiment-15% log kill, DSR staleness, TA CORS lockdown, legacy /api/v1/market deprecation

**In scope:**
- Every REQ-ID currently in PROJECT.md `### Validated` (pre-v1, v1.0, v1.1, v1.2 sub-headings — both `✓` shipped and `⚠`/`⏸` partial/blocked rows)
- Five synthetic `CLAUDE-*` REQ-IDs covering CLAUDE.md project-rule claims that are themselves Validated assertions (per advisor D-04, below)
- `file:line` evidence for every `satisfied` row — no "I saw it somewhere"
- `drift` vs `missing` distinction: `drift` = code exists but does not match the claim (e.g. RISK-04 cap is computed at `auto_trader.py:1697` but not enforced); `missing` = no implementing code found anywhere in repo
- Demotion proposal: every `drift`/`missing` row gets a proposed downstream phase owner OR `propose:demote-out-of-scope` verdict
- Rewrite of PROJECT.md `### Validated` section at phase close (Plan 07) preserving the four sub-headings (pre-v1, v1.0, v1.1, v1.2)
- Update of `## Key Decisions` table appending the audit-decisions row
- Flip of AUDIT-01 row in `.planning/REQUIREMENTS.md ## Traceability` from `Pending` → `Complete`
- Update of CLAUDE.md text where audit finds the claim is drift (e.g. "LSTM deleted, archived under `_archive_lstm/`" — if Phase 23 has not yet shipped the archive, CLAUDE.md text is corrected to match reality during Plan 07)

**Out of scope (defer or reject):**
- Fixing any code defect surfaced by the audit — Phases 17–24 own each fix
- Auditing v1.3 Active REQs (AUDIT-01, TE-CAP-*, BC-FIX-*, RECON-*, PAPER-*, TA-AGG-*, PRICE-*, ML-PURGE-*, HYG-*) — these are in-flight, not Validated
- Re-running tournament harness / forward-paper-test loops — operator wall-clock work, not audit work
- LIVECLOSE-* operator wall-clock execution — already documented as deferred operator action
- New deferred-item categories — STATE.md `## Deferred Items` is read-only input
- Updating `wiki/` — codebase map refresh is a separate workflow

</domain>

<acceptance_quote>
## AUDIT-01 Acceptance Criteria (verbatim from `.planning/REQUIREMENTS.md` lines 16-17)

> **AUDIT-01**: For every REQ-ID in PROJECT.md `### Validated` (pre-v1, v1.0, v1.1, v1.2), produce `.planning/evidence/AUDIT-01/validated-reaudit.json` with `{req_id, claim, evidence_file, evidence_line_start, evidence_line_end, status}` where `status ∈ {satisfied, drift, missing}`. `satisfied` = literal code path enforces the REQ end-to-end. `drift` = partial implementation or divergence between docs and code (e.g. RISK-04 cap is advisory after boot, ADR-010 paper cap is 0.02 not 0.10, sentiment-removal log strings stale). `missing` = no implementing code found (e.g. RISK-06 maker-only `use_post_only=False` hard-coded). For every `drift` or `missing` row, file an issue ticket linking the audit row. PROJECT.md `### Validated` section is rewritten at AUDIT-01 close to reflect reality; demoted REQs move to Active or Out of Scope with reason.

Every plan in this phase MUST treat the above as the bar. The executor reads it from CONTEXT.md, not from a chain of references.
</acceptance_quote>

<decisions>
## Implementation Decisions

### Inventory + sharding model

- **D-01:** **Plan 1 emits the canonical seeded JSON.** Every REQ-ID inventoried up front, each row has `req_id` + `claim` + `status="pending"` + empty `evidence_file/line_start/line_end/notes` slots. Canonical artifact path: `.planning/evidence/AUDIT-01/validated-reaudit.json`. Plan 01 OWNS this file for the duration of the phase up until Plan 06 merges.
- **D-02:** **Track plans (02, 03, 04, 05) write deltas, not the canonical file.** Each track-audit plan writes its own `track-{A|B|C1|C2}-deltas.json` containing only the REQ rows it reviewed, with `status` filled to `satisfied`/`drift`/`missing` + `evidence_file` + `evidence_line_start` + `evidence_line_end` + `notes`. Same-wave plans have ZERO `files_modified` overlap. This avoids destructive concurrent writes and gives a clean per-track audit trail in git history.
- **D-03:** **Plan 06 merges all four delta files into the canonical `validated-reaudit.json`.** Merge logic: for each REQ-ID in canonical seed, find the matching delta entry across the four track files; overwrite the seed row with the delta. Assertion (TDD): every seed row is overwritten (zero `pending` rows remain after merge); row count after merge equals row count of the seed. Mismatch fails the plan.

### CLAUDE.md as a Validated source

- **D-04:** **CLAUDE.md project-rule claims are auditable** alongside PROJECT.md REQs. Five synthetic `CLAUDE-*` REQ-IDs are added to the inventory in Plan 1 to capture load-bearing claims that live in CLAUDE.md, not in PROJECT.md:
  - `CLAUDE-LSTM-ARCHIVED` — claim: "LSTM deleted May 2026 (archived under `_archive_lstm/`)" (from CLAUDE.md `## Stack` section)
  - `CLAUDE-SENTIMENT-REMOVED` — claim: "Sentiment leg removed from signal pipeline (commits `c346483`, `acae081`, `fe941cf`, `c171bb0`)" + `ENABLE_SENTIMENT_ANALYSIS=false`
  - `CLAUDE-VALIDATED-SYMBOLS` — claim: "Validated symbols: BTC, ETH, SOL, BNB, ADA (5 active as of 2026-05-03). XRP / DOGE excluded by paper-trading data"
  - `CLAUDE-PAPER-CAP-ADR010` — claim: "paper mode currently relaxed to 10%" per ADR-010 (this collides with the suspected `config.py:321` default of 0.02 — `drift` expected)
  - `CLAUDE-EXEC-MAINNET-PRICES` — claim: "Market data feed from Bybit mainnet (`BYBIT_TESTNET=false`) for real prices; orders simulated internally via `PAPER_TRADING_MODE=true`"
  - Owner-track assignment: `CLAUDE-PAPER-CAP-ADR010` → Track A; `CLAUDE-LSTM-ARCHIVED` + `CLAUDE-SENTIMENT-REMOVED` → Track B; `CLAUDE-VALIDATED-SYMBOLS` + `CLAUDE-EXEC-MAINNET-PRICES` → Track C1.
  - Era assignment: all 5 CLAUDE-* IDs get `era="pre-v1"` because they describe project-rule preconditions that pre-date v1.0 milestone shipping and live in CLAUDE.md as standing constraints, not milestone deliverables. (ADR-010 itself was filed 2026-05-06 during v1.0+, but the claim it underlies — paper-mode risk-cap policy — is a pre-v1 operator policy that ADR-010 formalized.)

### Claim-text extraction

- **D-05:** **Claim text is extracted from the richest available source.** Pre-v1 REQs (RISK-*, ML-*, EXEC-*, DATA-*, OBS-*, UI-*, TEST-*) have claim text only in PROJECT.md `### Validated` bullets — Plan 1 extracts verbatim. v1.0 REQs (INFRA-*, TOURN-*, MLCL-*, DASH-*) have richer text in `.planning/milestones/v1.0-REQUIREMENTS.md` — Plan 1 uses that. Same for v1.1 (`.planning/milestones/v1.1-REQUIREMENTS.md`) and v1.2 (`.planning/milestones/v1.2-REQUIREMENTS.md`). Whichever is more specific wins; if conflict, use the milestone archive (richer + closer to the originating plan).

### Track rebalance + count

- **D-06:** **Four audit tracks, not three.** Counted REQ rows: pre-v1 = 21, v1.0 = 23, v1.1 = 19, v1.2 = 13, CLAUDE = 5. Total = 17 + 19 + 24 + 21 = 81 rows exactly. Three-track split (~17 + ~19 + ~45) made Track C bloat. Final split (re-counted during planning):
  - **Track A (Execution + Risk)** ≈ 17 rows: RISK-01..07 + PREFLIGHT-01..04 + MLGATE-01..03 + OBS-01..02 + CLAUDE-PAPER-CAP-ADR010
  - **Track B (Signal + ML)** ≈ 19 rows: ML-01..05 + MLCL-01..04 + TOURN-01..07 + EXEC-03 + CLAUDE-LSTM-ARCHIVED + CLAUDE-SENTIMENT-REMOVED
  - **Track C1 (Infra + Dashboard + Data + Misc)** = 24 rows: EXEC-01,02 (2) + DATA-01,02 (2) + UI-01 (1) + TEST-01 (1) + INFRA-01..06 (6) + DASH-01..06 (6) + DASHLIVE-01..04 (4) + CLAUDE-VALIDATED-SYMBOLS + CLAUDE-EXEC-MAINNET-PRICES (2)
  - **Track C2 (BC + Mobile + Tool + LIVECLOSE + CIRESTORE)** = 21 rows: BC-01..07 (7) + MOBILE-01..03 (3) + TOOL-01..03 (3) + LIVECLOSE-01..05 (5) + CIRESTORE-01..03 (3)
  - Plan 1's inventory task must re-count exactly and update CONTEXT.md if reality diverges from this estimate.

### Verdict rules

- **D-07:** **`satisfied` requires `file:line` evidence in the same row.** `evidence_file` is a repo-relative POSIX path; `evidence_line_start` + `evidence_line_end` form an inclusive line range (`line_start == line_end` for single-line evidence). If a REQ is satisfied across multiple files, pick the most load-bearing one and list secondaries in `notes`.
- **D-08:** **`drift` requires `notes` to explain the divergence.** Example: `"auto_trader.py:1697 computes proposed_risk but no enforcement gate; rejected by code-read of order-submission path"`. Without `notes`, a `drift` row is incomplete.
- **D-09:** **`missing` requires evidence of absence.** `notes` must cite the grep/scan that turned up zero hits. Example: `"grep -rn 'post_only' services/trading-engine/app/ → only line is auto_trader.py:544 use_post_only=False hard-coded; no toggle, no PostOnly tIF flow"`. `evidence_file` can be the file where the impl would live if present; `evidence_line_start`/`end` may both be `0` for true `missing`.
- **D-10:** **Operator-blocked carry-ins are NOT automatically `satisfied`.** LIVECLOSE-01..05 and CIRESTORE-01,02 have harness code shipped but evidence accrual pending. They should be classified `satisfied` if the harness code matches the v1.1 claim (the claim was "harness shipped"), with a `notes` field stating the evidence accrual is wall-clock-bound and tracked in STATE.md `## Open Operator Actions`. If audit finds the harness code itself is incomplete or doesn't match claim, status is `drift`.

### Demotion proposal vs apply

- **D-11:** **Plan 06 proposes demotions; Plan 07 applies them after operator confirmation.** Plan 06 emits a table mapping each `drift`/`missing` row → proposed downstream phase (17, 18, 19, 20, 21, 22, 23, 24) OR `propose:demote-out-of-scope` with rationale. Plan 07 has a `checkpoint:decision` task where the operator reviews the proposals and confirms or overrides each one before the PROJECT.md `### Validated` section is rewritten. `autonomous: false` on Plan 07.
- **D-12:** **Drift items expected to be picked up by existing v1.3 phase scope are auto-mapped.** The known-findings table in this CONTEXT.md (below) already maps the seven anticipated drift items to Phases 17/22/23/24. Plan 06's proposal for those rows pre-fills the downstream-phase owner; the operator only confirms (or moves) at the Plan 07 checkpoint. New drift items surfaced by the audit need fresh mapping.

### Code-read methodology

- **D-13:** **Use serena over grep when semantic.** Per project rule, `mcp__serena__*` tools (find_symbol, find_referencing_symbols, search_for_pattern) are preferred for symbol-level proof. Raw grep is acceptable for absence-proof or string-presence proof. Document the tool used in `notes` so the audit is reproducible (e.g. `notes: "verified via serena find_referencing_symbols on RiskManager.check_per_trade_cap; 1 caller in auto_trader.py:1697 computes but does not enforce"`).
- **D-14:** **Read the suspect files in the known-findings table directly.** Do not trust the audit summary in PROJECT.md — re-read the file at the line range and produce an independent verdict. The Phase 16 output IS the truthful baseline for Phases 17–24; if the audit copies the 2026-05-23 summary verbatim, downstream phases will be sized against the same lie.
- **D-15:** **CLAUDE.md correction is in scope for Plan 07.** If audit finds (e.g.) `CLAUDE-LSTM-ARCHIVED` is drift, Plan 07 corrects CLAUDE.md text to match reality (e.g. "LSTM removal in flight, archive landing in Phase 23"). CLAUDE.md is documentation; fixing documentation text is in-scope for an audit phase. Service code is OUT of scope.

### Schema + validation

- **D-16:** **Plan 1 writes `.planning/evidence/AUDIT-01/_schema.json`** with the row schema locked. Subsequent plans validate against it. Schema fields:
  - `req_id` (string, required) — e.g. `RISK-04`, `CLAUDE-LSTM-ARCHIVED`
  - `era` (enum: `pre-v1` | `v1.0` | `v1.1` | `v1.2`, required)
  - `source` (enum: `PROJECT.md` | `v1.0-REQUIREMENTS.md` | `v1.1-REQUIREMENTS.md` | `v1.2-REQUIREMENTS.md` | `CLAUDE.md`, required)
  - `claim` (string, required) — verbatim text from source
  - `evidence_file` (string, nullable; required when status=satisfied or drift) — repo-relative POSIX path
  - `evidence_line_start` (integer, nullable) — 1-based, inclusive
  - `evidence_line_end` (integer, nullable) — 1-based, inclusive
  - `status` (enum: `pending` | `satisfied` | `drift` | `missing`, required; `pending` only allowed in seed)
  - `notes` (string, nullable; required when status=drift or missing) — divergence explanation, methodology, secondary refs
- **D-17:** **Schema validation is a TDD task in Plan 1.** Write the schema; write a test that asserts the seeded JSON validates against it; populate the JSON; re-run the test. RED→GREEN cycle.

### Claude's Discretion

- Wave grouping inside each track-audit plan (i.e. order of REQ-IDs reviewed within Track A) — Plan executor's call
- Tooling choice between serena vs raw grep for each individual REQ row, per D-13
- Exact wording of demotion proposals in Plan 06 — Plan 06 author's call within D-11 constraints
- Whether to add additional CLAUDE.md correction tasks in Plan 07 beyond the ones surfaced by audit — Plan 07 author's call

</decisions>

<known_findings_table>
## Known Starting Findings (from 2026-05-23 forensic audit)

These are the seed hypotheses. **The audit MUST produce its own `file:line` evidence — do not copy the table.** Each row below is what the audit is expected to confirm; if the audit reaches a different verdict, that is the load-bearing finding and the row count below is wrong.

| REQ candidate | Suspected status | Suspect file:line | Likely owner phase |
|---|---|---|---|
| RISK-04 (per-trade cap 2% LIVE / 10% paper) | drift | `services/trading-engine/app/auto_trader.py:1697`, `app/config.py:321`, `app/main.py:277-290` | Phase 17 (TE-CAP-01, TE-CAP-04) |
| RISK-06 (maker-only / post-only) | missing | `services/trading-engine/app/auto_trader.py:544` (`use_post_only=False` hard-coded) | Phase 17 (TE-CAP-03) |
| CLAUDE-PAPER-CAP-ADR010 (paper 10% cap) | drift | `services/trading-engine/app/config.py:321` (default 0.02) | Phase 17 (TE-CAP-04) |
| CLAUDE-LSTM-ARCHIVED | drift/missing | `services/ml-prediction-service/app/models/ensemble_model.py:15` (live LSTM import); `services/ml-retraining-service/app/core/models/lstm.py` (file exists) | Phase 23 (ML-PURGE-02) |
| EXEC-03 ("9-indicator voting aggregator") | drift | `services/technical-analysis/app/handlers/analysis.py:19-132` (3 of 13 indicators voted) | Phase 21 (TA-AGG-01) |
| TOURN-07 ("Canonical metrics imports only — CI grep gate") | drift | `services/ml-retraining-service/app/core/model_trainer.py:430,623`; `verify_all_gru_models.py` | Phase 23 (ML-PURGE-01, ML-PURGE-05) |
| CLAUDE-SENTIMENT-REMOVED | drift | `services/trading-engine/app/auto_trader.py:1130,1261` (stale "Sentiment 15%" log) | Phase 24 (HYG-01) |

The audit may surface additional drift/missing rows not in this table. Plan 06 must enumerate them all with downstream-phase proposals.

The audit may also reverse one of these hypotheses (e.g. find that RISK-06 is in fact implemented elsewhere and `use_post_only=False` at `:544` is dead code overridden somewhere). Trust the audit, not the table.

</known_findings_table>

<canonical_refs>
## Canonical References

**Downstream executors MUST read these before producing any audit row.**

### Project policy + planning
- `CLAUDE.md` — project rules; risk caps, paper/live mode boundaries, validated symbols, LSTM-archive claim, sentiment-removal claim, paper-cap ADR-010 claim
- `.planning/PROJECT.md` `### Validated` (lines 65-128) — primary source of REQ inventory and claim text for pre-v1 REQs
- `.planning/REQUIREMENTS.md` — v1.3 active REQs (TE-CAP, BC-FIX, RECON, PAPER, TA-AGG, PRICE, ML-PURGE, HYG); `## Traceability` table for AUDIT-01 row to flip on close
- `.planning/ROADMAP.md` §"Phase 16" — phase goal + dependency block

### Milestone archives (richer claim text for shipped REQs)
- `.planning/milestones/v1.0-REQUIREMENTS.md` — INFRA-01..06, TOURN-01..07, MLCL-01..04, DASH-01..06 claim text + per-REQ shipped-marker file:line
- `.planning/milestones/v1.1-REQUIREMENTS.md` — PREFLIGHT-01..04, MLGATE-01..03, DASHLIVE-01..04, CIRESTORE-01..03, LIVECLOSE-01..05 claim text + 3-state taxonomy
- `.planning/milestones/v1.2-REQUIREMENTS.md` — BC-01..07, MOBILE-01..03, TOOL-01..03 claim text

### Audit-surface code paths (read directly during track plans — D-14)
- `services/trading-engine/app/auto_trader.py:544,1130,1261,1697` — RISK-04, RISK-06, CLAUDE-SENTIMENT-REMOVED suspects
- `services/trading-engine/app/config.py:321` — CLAUDE-PAPER-CAP-ADR010 / RISK-04 suspect
- `services/trading-engine/app/main.py:277-290` — RISK-04 boot-path suspect
- `services/trading-engine/app/handlers/orchestration.py:591` — RISK-06 / emergency-stop adjacency
- `services/technical-analysis/app/handlers/analysis.py:19-132` — EXEC-03 suspect
- `services/ml-prediction-service/app/models/ensemble_model.py:15` — CLAUDE-LSTM-ARCHIVED suspect
- `services/ml-retraining-service/app/core/model_trainer.py:430,623` + `verify_all_gru_models.py` — TOURN-07 suspect
- `services/ml-retraining-service/app/core/models/lstm.py` — CLAUDE-LSTM-ARCHIVED suspect (file existence)

### Evidence-schema precedent
- `.planning/evidence/_schema.json` — LIVECLOSE harness evidence schema; Plan 1's `_schema.json` should follow the same JSON-Schema draft 2020-12 idiom (independent file, distinct from this one)
- `.planning/evidence/BC-01/bybit-bypass-audit.json` — BC-01 audit shape precedent (`{file, line, kind, current_call, replacement_path}`)

### Tools (per CLAUDE.md project rules)
- `mcp__serena__*` (find_symbol, find_referencing_symbols, search_for_pattern) — preferred for semantic code-reads per D-13
- Raw grep — acceptable for absence-proof + string-presence proof
- No edits to service code under any track plan

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `.planning/evidence/BC-01/` directory layout — directory-per-REQ-ID convention; AUDIT-01 will mirror this with its own subdirectory
- `.planning/evidence/_schema.json` JSON-Schema draft 2020-12 idiom — copy for `.planning/evidence/AUDIT-01/_schema.json`
- Phase 13 `13-CONTEXT.md` shape — D-NN decisions, in/out of scope, canonical refs, code context, deferred ideas — this file mirrors that

### Established Patterns
- One audit row per REQ-ID; multi-line claim text preserved verbatim in `claim` field
- Conventional commits: `docs(audit):` for evidence-JSON writes, `docs(phase-16):` for PROJECT.md / CLAUDE.md / REQUIREMENTS.md edits
- TDD mode is enabled — apply `type: tdd` to schema-validation + merge-completeness tasks
- Filename convention: `{padded_phase}-{NN}-PLAN.md` strict — `16-01-PLAN.md` through `16-07-PLAN.md`

### Integration Points
- `validated-reaudit.json` is read by future milestone-audit workflow as a snapshot — schema must be stable + machine-parseable
- AUDIT-01 traceability row in `.planning/REQUIREMENTS.md` (line 141) flipped on Plan 07 close
- PROJECT.md `### Validated` section rewritten on Plan 07 close — preserves four sub-headings, replaces per-REQ entries with audit-verdict-driven rows
- CLAUDE.md text corrected where audit found drift (Plan 07)
- `## Key Decisions` table appended (Plan 07) with row capturing the audit reconciliation decision

</code_context>

<specifics>
## Specific Ideas

- Plan 1 should pre-load the inventory from PROJECT.md + the three milestone archives + CLAUDE.md grep, then emit the seeded JSON in a single pass. Re-counting REQ rows during Plan 1 may reveal the D-06 estimate is off — if a track lands outside the 17–25 row band, rebalance.
- Track plans should batch reads by service: review all RISK-* in one auto_trader.py read; all TOURN-* in one model_trainer.py read; all DASH-* in one frontend read. Avoid re-reading the same file.
- Use serena `find_symbol` on suspected enforcement points (e.g. `RiskManager.check_per_trade_cap`) and `find_referencing_symbols` to prove enforcement IS or ISN'T wired into the order path. This is the methodology that surfaces `drift` (caller computes but does not act on the result).
- Plan 06's row-count-completeness TDD assertion is the load-bearing check: `len(canonical) == len(seed) AND zero rows with status='pending' AND every (req_id, era) tuple from seed appears exactly once in canonical`.
- Plan 07's checkpoint is the natural break between machine-produced audit and human-confirmed taxonomy. Make the checkpoint specific: present the proposed-demotion table inline and ask "approve all / override specific rows / abort".

</specifics>

<deferred>
## Deferred Ideas (NOT in Phase 16 scope)

- Fixing any service code surfaced by the audit (Phases 17–24)
- Re-running LIVECLOSE-* operator harnesses (wall-clock-bound, tracked in STATE.md)
- Tournament-harness expansion or new ML evidence accrual (deferred to v1.4+)
- Codebase-map / wiki refresh after audit (separate workflow)
- New Validated-set claims beyond the 81-row inventory — only existing claims are audited; if new validated capability emerged since v1.2 close it's an `Active` REQ in v1.3, not a Phase 16 input
- ML re-enablement gate changes (still blocked behind DSR > 0.95 evidence)
- LIVE-flip work (paper-only milestone)

</deferred>

---

*Phase: 16-validated-set-re-audit*
*Context gathered: 2026-05-23*
*Estimated inventory: ~81 REQ rows across 5 sources (pre-v1, v1.0, v1.1, v1.2, CLAUDE)*
