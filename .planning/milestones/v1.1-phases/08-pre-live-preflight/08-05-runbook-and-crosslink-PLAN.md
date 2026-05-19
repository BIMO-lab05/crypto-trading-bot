---
phase: 08-pre-live-preflight
plan: 05
type: execute
wave: 1
depends_on: []
files_modified:
  - RUNBOOK.md
  - .planning/PROJECT.md
autonomous: true
requirements:
  - PREFLIGHT-04
tags:
  - preflight
  - documentation
  - runbook

must_haves:
  truths:
    - "RUNBOOK.md contains a top-level section `## Pre-LIVE Operator Checklist` after the existing 6-symptom blocks."
    - "The new section has 6 sub-headings — one per LIVE precondition (cap, paper_mode, trading_mode, ack, emergency_stop, dsr_evidence) — each with Diagnose/Action/Verification rows matching the existing RUNBOOK template."
    - "RUNBOOK.md Index includes the new section as a TOC entry."
    - "PROJECT.md Out of Scope section gains one new line cross-linking to the RUNBOOK section."
  artifacts:
    - path: "RUNBOOK.md"
      provides: "Pre-LIVE Operator Checklist section (~120 lines added)"
      contains: "## Pre-LIVE Operator Checklist"
    - path: ".planning/PROJECT.md"
      provides: "Cross-link from Out of Scope section to RUNBOOK checklist (1-line edit)"
      contains: "Pre-LIVE Operator Checklist"
  key_links:
    - from: "RUNBOOK.md ## Pre-LIVE Operator Checklist"
      to: "scripts/preflight_live.py"
      via: "Diagnose rows reference the CLI"
      pattern: "preflight_live\\.py"
    - from: ".planning/PROJECT.md Out of Scope"
      to: "RUNBOOK.md ## Pre-LIVE Operator Checklist"
      via: "markdown link"
      pattern: "RUNBOOK.md#pre-live-operator-checklist"
---

<objective>
Add the operator-runnable Diagnose/Action/Verification checklist for each of the 6 LIVE preconditions to RUNBOOK.md, mirroring the existing 6-symptom template. Cross-link from PROJECT.md Out of Scope section so the operator can navigate from "we are not actually live" to "here's how to actually go live, step by step".

Purpose: human-facing surface of the LIVE gate. The CLI (08-02), HTTP endpoint (08-02), and boot-enforcement (08-03) tell the operator WHAT is wrong; the RUNBOOK tells them HOW to fix it.

Output:
- Approximately 120 lines appended to RUNBOOK.md (one new top-level section, 6 sub-sections, Index entry).
- 1-line edit to .planning/PROJECT.md Out of Scope section.

This plan is pure docs and runs in Wave 1 in parallel with 08-01 (no code dependencies).
</objective>

<execution_context>
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/workflows/execute-plan.md
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/08-pre-live-preflight/08-CONTEXT.md
@.planning/phases/08-pre-live-preflight/08-PATTERNS.md
@CLAUDE.md

<!-- Target file and template source -->
@RUNBOOK.md

<interfaces>
RUNBOOK.md existing structure (lines 1-50 already read):
- Title + intro (lines 1-9)
- Index with 6 existing symptom entries (lines 9-17)
- Symptom 1: BuildKit hang (lines 21-42) — exemplar template
- Symptom 2 onwards through line ~165
- Tournament harness — first-time setup (line ~168, sits after symptoms)

The new "## Pre-LIVE Operator Checklist" section is inserted AFTER the last symptom (EMERGENCY_STOP recovery, around line 165) and BEFORE the Tournament harness section. This places the new section in the symptom-checklist family.

Each existing symptom uses this exact format:
```
## Symptom: <one-line summary>

<one-line context paragraph>.

**Diagnose:**
- `command 1` — note about output.
- `command 2`.

**Action:**
` ` `bash
shell command(s)
` ` `

**Verification:**
- `command` reports expected outcome.

---
```

The Pre-LIVE checklist DOES NOT prefix sections with "Symptom:" — it uses "Precondition N:" because these are proactive checks rather than reactive symptoms. The Diagnose/Action/Verification triple is preserved.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Append Pre-LIVE Operator Checklist section to RUNBOOK.md</name>
  <files>RUNBOOK.md</files>
  <read_first>
    - RUNBOOK.md (full file — lines 1-50 for Index, lines 21-42 for BuildKit-hang Diagnose/Action/Verification exemplar; find the line number after the last symptom block and before any non-symptom section like "Tournament harness")
    - .planning/phases/08-pre-live-preflight/08-PATTERNS.md (lines 885-927 — copy-ready section structure with literal Diagnose/Action/Verification format for Precondition 1; expand the other 5 to match)
    - .planning/phases/08-pre-live-preflight/08-CONTEXT.md (lines 17-23 — the 6 preconditions with literal env var names + ACK literal `I_UNDERSTAND_REAL_MONEY`)
    - CLAUDE.md "Trading-mode flags" section — four deliberate steps to LIVE (do NOT contradict; the checklist enforces preconditions, does NOT replace the four-flag friction)
  </read_first>
  <action>
    Use the Edit tool, not Write — RUNBOOK.md is a multi-section file and Write would clobber existing content.

    1. Read RUNBOOK.md fully and locate three insertion points:
       - The Index block (around lines 9-17) — add one new entry.
       - The end of the last symptom section (around line 165, after "Symptom: EMERGENCY_STOP recovery") — insert new section BEFORE the Tournament harness anchor (or before the next non-symptom heading).
       - Note the exact line number for the Edit tool's `old_string` anchor.

    2. **Edit #1 — Add Index entry.** Use Edit tool to find the existing line `- [Symptom: EMERGENCY_STOP recovery — auto-trader will not arm after stop](#symptom-emergency_stop-recovery--auto-trader-will-not-arm-after-stop)` (or the last symptom Index line) and replace it with that same line followed by the new Index entry on the next line:
       ```
       - [Pre-LIVE Operator Checklist](#pre-live-operator-checklist)
       ```

    3. **Edit #2 — Append the new section.** Find the closing horizontal rule of the last symptom section (the `---` line immediately before the Tournament harness heading, or before whichever next non-symptom section is found). Use Edit to insert the full new section between that `---` and the next heading. The new section content (copy verbatim — keep the markdown structure):

       Section header:
       ```
       ## Pre-LIVE Operator Checklist

       Before flipping `TRADING_MODE=LIVE`, work through each of the 6 preconditions
       below. Each pairs with a `preflight_live.py` check ID; the dashboard tile
       (Phase 10 DASHLIVE-01, not yet shipped) will render the same 6 rows.

       Run `python3 scripts/preflight_live.py --json` for a snapshot of all 6 at once.
       The CLI exits 0 on PASS, 1 on any FAIL or UNKNOWN.
       ```

       Precondition 1 (cap):
       ```
       ### Precondition 1: Per-trade cap <= 2% (LIVE-strict)

       **Diagnose:**
       - `python3 scripts/preflight_live.py --check=cap --json` — reports `"status": "FAIL"` when `MAX_RISK_PER_TRADE > 0.02` in the current env.
       - `grep MAX_RISK_PER_TRADE .env` — shows the current setting (default 0.10 per ADR-010 paper-relaxed).
       - `docker logs trading-engine | grep "LIVE_PREFLIGHT_REJECTED reason=cap_too_high"` — if the container failed to start, this line names the cause.

       **Action:**

           sed -i 's/^MAX_RISK_PER_TRADE=.*/MAX_RISK_PER_TRADE=0.02/' .env
           grep MAX_RISK_PER_TRADE .env   # expect: MAX_RISK_PER_TRADE=0.02

       **Verification:**
       - `python3 scripts/preflight_live.py --check=cap` exits 0.
       - `docker compose -f docker-compose.unified.yml up trading-engine` reaches log line `LIVE preflight cap check passed: max_risk_per_trade=0.02 <= 0.02`.
       ```

       Precondition 2 (paper_mode):
       ```
       ### Precondition 2: PAPER_TRADING_MODE=false

       **Diagnose:**
       - `python3 scripts/preflight_live.py --check=paper_mode --json` — reports `"status": "FAIL"` when `PAPER_TRADING_MODE=true` in `.env`.
       - `grep PAPER_TRADING_MODE .env`.

       **Action:**

           sed -i 's/^PAPER_TRADING_MODE=.*/PAPER_TRADING_MODE=false/' .env
           grep PAPER_TRADING_MODE .env   # expect: PAPER_TRADING_MODE=false

       **Verification:**
       - `python3 scripts/preflight_live.py --check=paper_mode` exits 0.
       ```

       Precondition 3 (trading_mode):
       ```
       ### Precondition 3: TRADING_MODE=LIVE

       **Diagnose:**
       - `python3 scripts/preflight_live.py --check=trading_mode --json` — reports the detected value.
       - `grep TRADING_MODE .env`.

       **Action:**

           sed -i 's/^TRADING_MODE=.*/TRADING_MODE=LIVE/' .env
           grep TRADING_MODE .env   # expect: TRADING_MODE=LIVE

       **Verification:**
       - `python3 scripts/preflight_live.py --check=trading_mode` exits 0.
       ```

       Precondition 4 (ack):
       ```
       ### Precondition 4: LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY

       **Diagnose:**
       - `python3 scripts/preflight_live.py --check=ack --json` — reports `"status": "FAIL"` when ACK is absent or wrong.
       - `grep LIVE_TRADING_ACK .env`.
       - This sentinel is the deliberate-friction gate from CLAUDE.md "Trading-mode flags". Do NOT shortcut it.

       **Action:**

           # Add the literal sentinel exactly — no variations accepted by main.py:252
           echo 'LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY' >> .env
           grep LIVE_TRADING_ACK .env

       **Verification:**
       - `python3 scripts/preflight_live.py --check=ack` exits 0.
       - On startup, trading-engine logs `LIVE trading mode acknowledged via LIVE_TRADING_ACK` (existing main.py:258 line).
       ```

       Precondition 5 (emergency_stop):
       ```
       ### Precondition 5: EMERGENCY_STOP file absent

       **Diagnose:**
       - `python3 scripts/preflight_live.py --check=emergency_stop --json` — reports `"status": "FAIL"` if the file is present at the configured path.
       - `ls -la EMERGENCY_STOP` (from repo root).

       **Action:**

           rm -f EMERGENCY_STOP
           ls -la EMERGENCY_STOP   # expect: No such file or directory

       Note (CLAUDE.md gotcha): a *directory* at the path also reads as absent for the preflight check (`Path.is_file()` returns False for directories). If you encounter an empty directory there (WSL bind-mount race), `rmdir EMERGENCY_STOP` cleans it up.

       **Verification:**
       - `python3 scripts/preflight_live.py --check=emergency_stop` exits 0.
       ```

       Precondition 6 (dsr_evidence):
       ```
       ### Precondition 6: DSR > 0.95 evidence row (only when ML enabled)

       **Diagnose:**
       - `python3 scripts/preflight_live.py --check=dsr_evidence --json` — reports `"status": "UNKNOWN"` when `ENABLE_ML_PREDICTIONS=true` but Phase 9's auto-flip marker `/run/mlgate_auto_flip.json` is absent.
       - With `ENABLE_ML_PREDICTIONS=false`, this check short-circuits to PASS (ML is disabled by default; the gate does not apply).
       - Query the leaderboard directly: `sqlite3 /data/tournament.db "SELECT dsr FROM leaderboard ORDER BY tournament_start_ts DESC LIMIT 1"` — shows the latest DSR.

       **Action:**
       - LIVE without ML: leave `ENABLE_ML_PREDICTIONS=false` and the check passes automatically.
       - LIVE with ML on: Phase 9 (MLGATE-01/02) must land first; it owns the 7-day evidence accrual + auto-flip marker. As of 2026-05-16, Phase 9 has not shipped — `dsr_evidence` returns UNKNOWN whenever ML is enabled.

       **Verification:**
       - `python3 scripts/preflight_live.py --check=dsr_evidence` exits 0 (ML disabled path) or pending Phase 9 (ML enabled path).
       ```

       Close section with a horizontal-rule separator:
       ```
       ---
       ```

    4. Preserve the existing horizontal-rule separators between symptoms. Match the existing terse tone (no marketing prose). Indented code blocks (4 spaces) are used here instead of fenced triple-backticks to avoid nesting backticks inside this plan file; the executor should convert these to fenced bash code blocks using triple-backticks during actual edit (the existing RUNBOOK uses triple-backtick fences, see lines 31-35). Pick the fence style matching the surrounding file.

    5. Do NOT remove or modify any existing symptom section.
  </action>
  <verify>
    <automated>cd /mnt/d/Bimo_max/crypto-trading-bot &amp;&amp; test "$(grep -c '^## Pre-LIVE Operator Checklist' RUNBOOK.md)" = "1" &amp;&amp; test "$(grep -c '^### Precondition ' RUNBOOK.md)" = "6" &amp;&amp; grep -q 'pre-live-operator-checklist' RUNBOOK.md &amp;&amp; echo "RUNBOOK OK"</automated>
  </verify>
  <acceptance_criteria>
    - Source assertion: `grep -c '^## Pre-LIVE Operator Checklist' RUNBOOK.md` returns exactly 1.
    - Source assertion: `grep -c '^### Precondition ' RUNBOOK.md` returns exactly 6.
    - Source assertion: `grep -c 'pre-live-operator-checklist' RUNBOOK.md` returns ≥1 (Index TOC anchor).
    - Source assertion: each precondition references its CLI invocation — `grep -c 'preflight_live.py --check=' RUNBOOK.md` returns ≥6.
    - Source assertion (literal correctness): `grep -c 'I_UNDERSTAND_REAL_MONEY' RUNBOOK.md` returns ≥1 (the load-bearing ACK sentinel).
    - Source assertion (literal correctness): `grep -c 'LIVE_PREFLIGHT_REJECTED' RUNBOOK.md` returns ≥1 — appears in Precondition 1 Diagnose. Confirms operator can grep `docker logs` for this string (matches what 08-03 emits).
    - Source assertion (no regression): `grep -c '^## Symptom: ' RUNBOOK.md` returns ≥6 (the existing symptom sections are still present).
    - Behavior assertion: the `<verify>` one-liner exits 0 and prints `RUNBOOK OK`.
  </acceptance_criteria>
  <done>RUNBOOK.md has 6 new precondition sections with Diagnose/Action/Verification format; Index includes the new TOC entry; existing symptom sections untouched.</done>
</task>

<task type="auto">
  <name>Task 2: Cross-link from PROJECT.md Out of Scope to the new RUNBOOK section</name>
  <files>.planning/PROJECT.md</files>
  <read_first>
    - .planning/PROJECT.md (`Out of Scope` section is at line 93 per the bash grep already run; read lines 85-120 for context and find the LIVE-default-related entry — the four-flag friction note)
    - 08-CONTEXT.md (lines 21 — "cross-linked from PROJECT.md's Out of Scope LIVE-default note")
  </read_first>
  <action>
    1. Read `.planning/PROJECT.md` lines 85-130 to identify the Out of Scope section's LIVE-default entry. Look for an item mentioning "LIVE" or "TRADING_MODE" or the four-flag gate, typically a bullet under `### Out of Scope`.

    2. Append (or insert immediately under) the LIVE-default item one new sub-line referencing the RUNBOOK checklist:
       ```
         - When flipping LIVE is in scope, the 6-precondition Diagnose/Action/Verification path lives in [RUNBOOK.md "Pre-LIVE Operator Checklist"](../RUNBOOK.md#pre-live-operator-checklist). Phase 8 enforces these in code; v1.1 does not flip LIVE.
       ```

       Path notes: `.planning/PROJECT.md` lives one level deep under repo root, so the relative path `../RUNBOOK.md#pre-live-operator-checklist` resolves correctly.

    3. If the Out of Scope entry doesn't exist as a clear "LIVE-default" bullet (the section may be a numbered/bulleted list without obvious matching bullet), append the new line as a new bullet at the END of the Out of Scope section instead:
       ```
       - [Pre-LIVE Operator Checklist](../RUNBOOK.md#pre-live-operator-checklist) — Phase 8 codifies the 6 LIVE preconditions; v1.1 does not flip LIVE.
       ```

    4. Use Edit tool with a specific `old_string` anchor (e.g. the line immediately before insertion point) — never Write, which would clobber the file.
  </action>
  <verify>
    <automated>grep -c "Pre-LIVE Operator Checklist" .planning/PROJECT.md | xargs -I{} test {} -ge 1 &amp;&amp; grep -c "RUNBOOK.md#pre-live-operator-checklist" .planning/PROJECT.md | xargs -I{} test {} -ge 1 &amp;&amp; echo "PROJECT.md crosslink OK"</automated>
  </verify>
  <acceptance_criteria>
    - Source assertion: `grep -c "Pre-LIVE Operator Checklist" .planning/PROJECT.md` returns ≥1.
    - Source assertion: `grep -c "RUNBOOK.md#pre-live-operator-checklist" .planning/PROJECT.md` returns ≥1.
    - Source assertion (negative — no accidental file move): `grep -c "^# Project Context\\|^# .* Bot\\|^# Trading" .planning/PROJECT.md` returns ≥1 (the file's top-level heading is still present — sanity check that the Edit did not corrupt the file).
    - Behavior assertion: the `<verify>` one-liner exits 0 and prints `PROJECT.md crosslink OK`.
  </acceptance_criteria>
  <done>PROJECT.md Out of Scope section now references the RUNBOOK Pre-LIVE checklist via a markdown link with anchor; the rest of the file is unchanged.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| documentation → operator | informational artifact; no code execution, no state change |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-08-05-01 | n/a | RUNBOOK.md and PROJECT.md edits | n/a | Pure documentation: no STRIDE surface, no executable code, no network/process boundary. Informational artifact. ASVS L1 does not apply to documentation files. |
| T-08-05-02 | I (Info disclosure) | RUNBOOK shows command examples including grep on .env | accept | .env contents are operator-local; RUNBOOK does not display secret values, only env-var NAMES (MAX_RISK_PER_TRADE, LIVE_TRADING_ACK). The ACK literal `I_UNDERSTAND_REAL_MONEY` is a public sentinel (already documented in CLAUDE.md), not a secret. |
</threat_model>

<verification>
- `grep -c '^## Pre-LIVE Operator Checklist' RUNBOOK.md` returns 1.
- `grep -c '^### Precondition ' RUNBOOK.md` returns 6.
- `grep -c 'preflight_live.py --check=' RUNBOOK.md` returns ≥6.
- `grep -c 'I_UNDERSTAND_REAL_MONEY' RUNBOOK.md` returns ≥1.
- `grep -c 'LIVE_PREFLIGHT_REJECTED' RUNBOOK.md` returns ≥1 (so the grep gate from 08-03 still scopes only to `services/trading-engine/app/`, which it does per advisor guidance).
- `grep -c 'Pre-LIVE Operator Checklist' .planning/PROJECT.md` returns ≥1.
- Manual verification (record in SUMMARY): opening the rendered RUNBOOK.md in an editor that supports markdown TOC, the new section appears with anchor `#pre-live-operator-checklist` and Index links resolve.
</verification>

<success_criteria>
- RUNBOOK.md gains the new section with all 6 sub-sections in Diagnose/Action/Verification format.
- Index TOC has the new entry.
- PROJECT.md Out of Scope cross-links to the new section.
- Existing RUNBOOK symptom sections are unchanged.
- 08-03's grep gate scope is `services/trading-engine/app/` ONLY — so RUNBOOK.md's mention of `LIVE_PREFLIGHT_REJECTED` does not pollute the gate. (This is enforced by 08-03's test code, not by this plan — but documented here as the rationale for the scope choice.)
</success_criteria>

<output>
After completion, create `.planning/phases/08-pre-live-preflight/08-05-SUMMARY.md` capturing:
- Number of lines added to RUNBOOK.md.
- Line number where the new section was inserted.
- The one-line PROJECT.md edit (before/after diff).
- Manual TOC-render check confirmation (one line: "Anchor `#pre-live-operator-checklist` resolves; Index entry links to section.").
- Note: this plan runs in Wave 1 in parallel with 08-01 (foundation module); has no code dependencies and produces no test changes.
</output>
